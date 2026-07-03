using Microsoft.EntityFrameworkCore;
using TaskDesk.Api.Data;
using TaskDesk.Api.Models;

namespace TaskDesk.Api.Api;

// ---- Request DTOs ----
public record CreateProject(string Key, string Name, string CustomerKey, string Type, string ServiceType, string Lead);
public record CreateWorkItem(string ProjectKey, string Type, string Title, string Description, string Priority, string Requester, string? Assignee);
public record Transition(string Status);
public record AddComment(string Author, string Body, bool IsInternal);
public record ToggleModule(bool Enabled, string? CustomerKey);

public static class Endpoints
{
    public static void MapApi(this WebApplication app)
    {
        var v1 = app.MapGroup("/api/v1").WithTags("TaskDesk");

        // ---- Customers ----
        v1.MapGet("/customers", async (AppDbContext db) =>
            await db.Customers.OrderBy(c => c.Name)
                .Select(c => new { c.Key, c.Name, c.Plan, projects = c.Projects.Count })
                .ToListAsync());

        // ---- Projects ----
        v1.MapGet("/projects", async (AppDbContext db, string? customer) =>
        {
            var q = db.Projects.Include(p => p.Customer).Include(p => p.WorkItems).AsQueryable();
            if (!string.IsNullOrEmpty(customer)) q = q.Where(p => p.Customer!.Key == customer);
            return await q.OrderBy(p => p.Key).Select(p => ProjectDto(p)).ToListAsync();
        });

        v1.MapGet("/projects/{key}", async (AppDbContext db, string key) =>
        {
            var p = await db.Projects.Include(x => x.Customer).Include(x => x.WorkItems)
                .FirstOrDefaultAsync(x => x.Key == key);
            return p is null ? Results.NotFound() : Results.Ok(ProjectDto(p));
        });

        v1.MapPost("/projects", async (AppDbContext db, CreateProject req) =>
        {
            var cust = await db.Customers.FirstOrDefaultAsync(c => c.Key == req.CustomerKey);
            if (cust is null) return Results.BadRequest(new { error = "unknown customer" });
            if (await db.Projects.AnyAsync(p => p.Key == req.Key)) return Results.Conflict(new { error = "project key exists" });
            var p = new Project { Key = req.Key, Name = req.Name, CustomerId = cust.Id, Type = req.Type, ServiceType = req.ServiceType, Lead = req.Lead };
            db.Projects.Add(p);
            await db.SaveChangesAsync();
            return Results.Created($"/api/v1/projects/{p.Key}", new { p.Key, p.Name });
        });

        // ---- Work items ----
        v1.MapGet("/projects/{key}/workitems", async (AppDbContext db, string key) =>
        {
            var items = await db.WorkItems.Include(w => w.Project)
                .Where(w => w.Project!.Key == key).OrderByDescending(w => w.CreatedAt)
                .Select(w => WorkItemDto(w)).ToListAsync();
            return Results.Ok(items);
        });

        v1.MapGet("/workitems/{key}", async (AppDbContext db, string key) =>
        {
            var w = await db.WorkItems.Include(x => x.Project).Include(x => x.Comments).Include(x => x.Activity)
                .FirstOrDefaultAsync(x => x.Key == key);
            return w is null ? Results.NotFound() : Results.Ok(WorkItemDetailDto(w));
        });

        v1.MapPost("/workitems", async (AppDbContext db, CreateWorkItem req) =>
        {
            if (!WorkItemType.All.Contains(req.Type)) return Results.BadRequest(new { error = "bad type" });
            if (!Priority.All.Contains(req.Priority)) return Results.BadRequest(new { error = "bad priority" });
            var p = await db.Projects.FirstOrDefaultAsync(x => x.Key == req.ProjectKey);
            if (p is null) return Results.BadRequest(new { error = "unknown project" });
            p.Seq++;
            var w = new WorkItem
            {
                Key = $"{p.Key}-{p.Seq}", ProjectId = p.Id, Type = req.Type, Title = req.Title,
                Description = req.Description, PriorityLevel = req.Priority, Requester = req.Requester, Assignee = req.Assignee,
                Activity = { new ActivityEntry { Actor = req.Requester, Verb = "created", Detail = "created this item" } }
            };
            db.WorkItems.Add(w);
            await db.SaveChangesAsync();
            return Results.Created($"/api/v1/workitems/{w.Key}", new { w.Key });
        });

        v1.MapPost("/workitems/{key}/transition", async (AppDbContext db, string key, Transition req) =>
        {
            if (!WorkItemStatus.All.Contains(req.Status)) return Results.BadRequest(new { error = "bad status" });
            var w = await db.WorkItems.FirstOrDefaultAsync(x => x.Key == key);
            if (w is null) return Results.NotFound();
            var from = w.Status;
            w.Status = req.Status; w.UpdatedAt = DateTime.UtcNow;
            db.Activity.Add(new ActivityEntry { WorkItemId = w.Id, Actor = "system", Verb = "transition", Detail = $"{from} → {req.Status}" });
            await db.SaveChangesAsync();
            return Results.Ok(new { w.Key, w.Status });
        });

        v1.MapPost("/workitems/{key}/comments", async (AppDbContext db, string key, AddComment req) =>
        {
            var w = await db.WorkItems.FirstOrDefaultAsync(x => x.Key == key);
            if (w is null) return Results.NotFound();
            db.Comments.Add(new Comment { WorkItemId = w.Id, Author = req.Author, Body = req.Body, IsInternal = req.IsInternal });
            db.Activity.Add(new ActivityEntry { WorkItemId = w.Id, Actor = req.Author, Verb = "comment", Detail = req.IsInternal ? "added an internal note" : "commented" });
            w.UpdatedAt = DateTime.UtcNow;
            await db.SaveChangesAsync();
            return Results.Ok(new { ok = true });
        });

        // ---- Reports (gated by the managed_service module — demonstrates §14 enforcement) ----
        v1.MapGet("/reports/overview", async (AppDbContext db, string? customer) =>
        {
            Guid? custId = string.IsNullOrEmpty(customer) ? null
                : (await db.Customers.FirstOrDefaultAsync(c => c.Key == customer))?.Id;
            if (!await ModuleEnabled(db, "managed_service", custId))
                return Results.Json(new { error = "module_disabled", module = "managed_service" }, statusCode: 403);

            var items = db.WorkItems.AsQueryable();
            if (custId is not null) items = items.Where(w => w.Project!.CustomerId == custId);
            return Results.Ok(new
            {
                open = await items.CountAsync(w => w.Status != WorkItemStatus.Done),
                resolved = await items.CountAsync(w => w.Status == WorkItemStatus.Done),
                unassigned = await items.CountAsync(w => w.Assignee == null && w.Status != WorkItemStatus.Done),
                byStatus = await items.GroupBy(w => w.Status).Select(g => new { status = g.Key, count = g.Count() }).ToListAsync()
            });
        });

        // ---- Modules (registry + toggle; the plugin contract, §14/§20) ----
        v1.MapGet("/modules", async (AppDbContext db, string? customer) =>
        {
            Guid? custId = string.IsNullOrEmpty(customer) ? null
                : (await db.Customers.FirstOrDefaultAsync(c => c.Key == customer))?.Id;
            var mods = await db.Modules.ToListAsync();
            var result = new List<object>();
            foreach (var m in mods)
                result.Add(new { m.Key, m.Name, m.Description, enabled = await ModuleEnabled(db, m.Key, custId) });
            return Results.Ok(result);
        });

        v1.MapPost("/modules/{key}/toggle", async (AppDbContext db, string key, ToggleModule req) =>
        {
            var mod = await db.Modules.FindAsync(key);
            if (mod is null) return Results.NotFound();
            Guid? custId = string.IsNullOrEmpty(req.CustomerKey) ? null
                : (await db.Customers.FirstOrDefaultAsync(c => c.Key == req.CustomerKey))?.Id;
            var state = await db.ModuleStates.FirstOrDefaultAsync(s => s.ModuleKey == key && s.CustomerId == custId);
            if (state is null) db.ModuleStates.Add(new ModuleState { ModuleKey = key, CustomerId = custId, Enabled = req.Enabled });
            else state.Enabled = req.Enabled;
            await db.SaveChangesAsync();
            return Results.Ok(new { key, scope = custId is null ? "global" : req.CustomerKey, req.Enabled });
        });
    }

    // Effective module state: customer override → global override → module default.
    static async Task<bool> ModuleEnabled(AppDbContext db, string moduleKey, Guid? customerId)
    {
        if (customerId is not null)
        {
            var cust = await db.ModuleStates.FirstOrDefaultAsync(s => s.ModuleKey == moduleKey && s.CustomerId == customerId);
            if (cust is not null) return cust.Enabled;
        }
        var global = await db.ModuleStates.FirstOrDefaultAsync(s => s.ModuleKey == moduleKey && s.CustomerId == null);
        if (global is not null) return global.Enabled;
        var mod = await db.Modules.FindAsync(moduleKey);
        return mod?.DefaultEnabled ?? false;
    }

    static object ProjectDto(Project p) => new
    {
        p.Key, p.Name, customer = p.Customer?.Name, customerKey = p.Customer?.Key,
        p.Type, p.ServiceType, p.Lead,
        open = p.WorkItems.Count(w => w.Status != WorkItemStatus.Done),
        resolved = p.WorkItems.Count(w => w.Status == WorkItemStatus.Done)
    };

    static object WorkItemDto(WorkItem w) => new
    {
        w.Key, project = w.Project?.Key, w.Type, w.Title, w.Status,
        priority = w.PriorityLevel, w.Assignee, w.Requester, w.UpdatedAt
    };

    static object WorkItemDetailDto(WorkItem w) => new
    {
        w.Key, project = w.Project?.Key, w.Type, w.Title, w.Description, w.Status,
        priority = w.PriorityLevel, w.Assignee, w.Requester, w.CreatedAt, w.UpdatedAt,
        comments = w.Comments.OrderBy(c => c.CreatedAt).Select(c => new { c.Author, c.Body, c.IsInternal, c.CreatedAt }),
        activity = w.Activity.OrderByDescending(a => a.CreatedAt).Select(a => new { a.Actor, a.Verb, a.Detail, a.CreatedAt })
    };
}
