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
public record LogTime(string Author, int Minutes, string? Note);
public record AssignWorkItem(string? Assignee);

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
                .Where(w => w.Project!.Key == key).OrderByDescending(w => w.CreatedAt).ToListAsync();
            var sla = await SlaForProject(db, key);
            return Results.Ok(items.Select(w => WorkItemDto(w, Sla.Compute(w, sla))));
        });

        v1.MapGet("/workitems/{key}", async (AppDbContext db, string key) =>
        {
            var w = await db.WorkItems.Include(x => x.Project).Include(x => x.Comments).Include(x => x.Activity)
                .FirstOrDefaultAsync(x => x.Key == key);
            if (w is null) return Results.NotFound();
            var sla = await SlaForProject(db, w.Project!.Key);
            return Results.Ok(WorkItemDetailDto(w, Sla.Compute(w, sla)));
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
            w.ResolvedAt = req.Status == WorkItemStatus.Done ? DateTime.UtcNow : null;   // for SLA compliance
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

        v1.MapPost("/workitems/{key}/assign", async (AppDbContext db, string key, AssignWorkItem req) =>
        {
            var w = await db.WorkItems.FirstOrDefaultAsync(x => x.Key == key);
            if (w is null) return Results.NotFound();
            w.Assignee = string.IsNullOrWhiteSpace(req.Assignee) ? null : req.Assignee.Trim();
            w.UpdatedAt = DateTime.UtcNow;
            db.Activity.Add(new ActivityEntry { WorkItemId = w.Id, Actor = "system", Verb = "assign",
                Detail = w.Assignee is null ? "unassigned" : $"assigned to {w.Assignee}" });
            await db.SaveChangesAsync();
            return Results.Ok(new { w.Key, w.Assignee });
        });

        // Time logging deducts from the hour bank → a managed-service capability (§7), module-gated.
        v1.MapPost("/workitems/{key}/time", async (AppDbContext db, string key, LogTime req) =>
        {
            if (req.Minutes <= 0) return Results.BadRequest(new { error = "minutes must be positive" });
            var w = await db.WorkItems.Include(x => x.Project).FirstOrDefaultAsync(x => x.Key == key);
            if (w is null) return Results.NotFound();
            if (!await ModuleEnabled(db, "managed_service", w.Project!.CustomerId))
                return Results.Json(new { error = "module_disabled", module = "managed_service" }, statusCode: 403);
            db.TimeLogs.Add(new TimeLog { WorkItemId = w.Id, ProjectId = w.ProjectId, Author = req.Author, Minutes = req.Minutes, Note = req.Note ?? "" });
            db.Activity.Add(new ActivityEntry { WorkItemId = w.Id, Actor = req.Author, Verb = "time", Detail = $"logged {Hours(req.Minutes)}h" });
            w.UpdatedAt = DateTime.UtcNow;
            await db.SaveChangesAsync();
            var usedMin = await db.TimeLogs.Where(t => t.ProjectId == w.ProjectId).SumAsync(t => t.Minutes);
            var contracted = (await db.Contracts.FirstOrDefaultAsync(c => c.ProjectId == w.ProjectId))?.ContractedHours ?? 0;
            return Results.Ok(new { ok = true, usedHours = Hours(usedMin), remainingHours = Math.Round(contracted - Hours(usedMin), 1) });
        });

        // ---- Reports (gated by the managed_service module — demonstrates §14 enforcement) ----
        v1.MapGet("/reports/overview", async (AppDbContext db, string? customer) =>
        {
            Guid? custId = string.IsNullOrEmpty(customer) ? null
                : (await db.Customers.FirstOrDefaultAsync(c => c.Key == customer))?.Id;
            if (!await ModuleEnabled(db, "managed_service", custId))
                return Results.Json(new { error = "module_disabled", module = "managed_service" }, statusCode: 403);

            var items = db.WorkItems.Include(w => w.Project).AsQueryable();
            if (custId is not null) items = items.Where(w => w.Project!.CustomerId == custId);
            var list = await items.ToListAsync();
            var sla = await SlaLookup(db, custId);
            var open = list.Where(w => w.Status != WorkItemStatus.Done).ToList();
            var breaching = open.Count(w => Sla.Compute(w, sla).State == "breached");
            return Results.Ok(new
            {
                open = open.Count,
                resolved = list.Count(w => w.Status == WorkItemStatus.Done),
                unassigned = open.Count(w => w.Assignee == null),
                slaBreaching = breaching,
                slaAtRisk = open.Count(w => Sla.Compute(w, sla).State == "risk"),
                slaCompliancePct = open.Count == 0 ? 100 : (int)Math.Round(100.0 * (open.Count - breaching) / open.Count),
                byStatus = list.GroupBy(w => w.Status).Select(g => new { status = g.Key, count = g.Count() }).ToList()
            });
        });

        // ---- Managed service / AMC: contract + hour bank (§7), module-gated ----
        v1.MapGet("/projects/{key}/contract", async (AppDbContext db, string key) =>
        {
            var p = await db.Projects.Include(x => x.Customer).FirstOrDefaultAsync(x => x.Key == key);
            if (p is null) return Results.NotFound();
            if (!await ModuleEnabled(db, "managed_service", p.CustomerId))
                return Results.Json(new { error = "module_disabled", module = "managed_service" }, statusCode: 403);
            var c = await db.Contracts.FirstOrDefaultAsync(x => x.ProjectId == p.Id);
            if (c is null) return Results.Ok(new { project = p.Key, hasContract = false });

            var usedMin = await db.TimeLogs.Where(t => t.ProjectId == p.Id).SumAsync(t => (int?)t.Minutes) ?? 0;
            var used = Hours(usedMin);
            var recent = await db.TimeLogs.Where(t => t.ProjectId == p.Id).OrderByDescending(t => t.CreatedAt).Take(5)
                .Select(t => new { t.Author, hours = t.Minutes / 60.0, t.Note, t.CreatedAt }).ToListAsync();
            var now = DateTime.UtcNow;
            var daysRemaining = (int)Math.Ceiling((c.EndDate - now).TotalDays);
            var status = now > c.EndDate ? "Expired"
                : c.KickoffStatusValue != KickoffStatus.Completed ? "Kickoff pending"
                : daysRemaining <= 30 ? "Expiring"
                : "Active";
            return Results.Ok(new
            {
                project = p.Key, projectName = p.Name, customer = p.Customer?.Name, serviceType = p.ServiceType,
                hasContract = true, status,
                period = new { start = c.StartDate, end = c.EndDate, daysRemaining },
                kickoff = new { status = c.KickoffStatusValue, date = c.KickoffDate },
                coverage = c.Coverage,
                hourBank = new { contracted = c.ContractedHours, used = Math.Round(used, 1), remaining = Math.Round(c.ContractedHours - used, 1),
                    usedPct = c.ContractedHours <= 0 ? 0 : (int)Math.Round(100.0 * used / c.ContractedHours) },
                recentDeductions = recent
            });
        });

        v1.MapGet("/projects/{key}/sla-policies", async (AppDbContext db, string key) =>
        {
            var p = await db.Projects.FirstOrDefaultAsync(x => x.Key == key);
            if (p is null) return Results.NotFound();
            return Results.Ok(await db.SlaPolicies.Where(s => s.ProjectId == p.Id)
                .Select(s => new { s.Priority, s.ResponseMinutes, s.ResolutionMinutes }).ToListAsync());
        });

        // Open items past (or nearing) their resolution SLA — consumed by the Go worker + dashboard.
        v1.MapGet("/sla/breaches", async (AppDbContext db, string? customer) =>
        {
            Guid? custId = string.IsNullOrEmpty(customer) ? null
                : (await db.Customers.FirstOrDefaultAsync(c => c.Key == customer))?.Id;
            var q = db.WorkItems.Include(w => w.Project).Where(w => w.Status != WorkItemStatus.Done);
            if (custId is not null) q = q.Where(w => w.Project!.CustomerId == custId);
            var open = await q.ToListAsync();
            var sla = await SlaLookup(db, custId);
            var rows = open.Select(w => new { w, s = Sla.Compute(w, sla) })
                .Where(x => x.s.State is "breached" or "risk")
                .OrderBy(x => x.s.DueAt)
                .Select(x => new { x.w.Key, project = x.w.Project!.Key, x.w.Title, priority = x.w.PriorityLevel,
                    x.w.Assignee, state = x.s.State, dueAt = x.s.DueAt }).ToList();
            return Results.Ok(new { breaching = rows.Count(r => r.state == "breached"), atRisk = rows.Count(r => r.state == "risk"), items = rows });
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

    static double Hours(int minutes) => Math.Round(minutes / 60.0, 1);

    // Resolution-SLA lookup keyed by (project, priority). custId null = all customers.
    static async Task<Dictionary<(Guid, string), int>> SlaLookup(AppDbContext db, Guid? custId)
    {
        var q = db.SlaPolicies.AsQueryable();
        if (custId is not null)
            q = q.Where(s => db.Projects.Any(p => p.Id == s.ProjectId && p.CustomerId == custId));
        var pols = await q.ToListAsync();
        return pols.ToDictionary(s => (s.ProjectId, s.Priority), s => s.ResolutionMinutes);
    }

    static async Task<Dictionary<(Guid, string), int>> SlaForProject(AppDbContext db, string projectKey)
    {
        var pols = await db.SlaPolicies.Where(s => db.Projects.Any(p => p.Id == s.ProjectId && p.Key == projectKey)).ToListAsync();
        return pols.ToDictionary(s => (s.ProjectId, s.Priority), s => s.ResolutionMinutes);
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

    static object WorkItemDto(WorkItem w, SlaInfo sla) => new
    {
        w.Key, project = w.Project?.Key, w.Type, w.Title, w.Status,
        priority = w.PriorityLevel, w.Assignee, w.Requester, w.UpdatedAt,
        slaState = sla.State, slaDueAt = sla.DueAt
    };

    static object WorkItemDetailDto(WorkItem w, SlaInfo sla) => new
    {
        w.Key, project = w.Project?.Key, w.Type, w.Title, w.Description, w.Status,
        priority = w.PriorityLevel, w.Assignee, w.Requester, w.CreatedAt, w.UpdatedAt,
        slaState = sla.State, slaDueAt = sla.DueAt,
        comments = w.Comments.OrderBy(c => c.CreatedAt).Select(c => new { c.Author, c.Body, c.IsInternal, c.CreatedAt }),
        activity = w.Activity.OrderByDescending(a => a.CreatedAt).Select(a => new { a.Actor, a.Verb, a.Detail, a.CreatedAt })
    };
}

// Lazy resolution-SLA: due = created + policy resolution; state derived from now (no stored timers — pause is P2, §7).
public record SlaInfo(DateTime? DueAt, string State);

public static class Sla
{
    public static SlaInfo Compute(WorkItem w, Dictionary<(Guid, string), int> lookup)
    {
        if (!lookup.TryGetValue((w.ProjectId, w.PriorityLevel), out var resMin))
            return new SlaInfo(null, "none");                    // no policy (e.g. Delivery project)
        var due = w.CreatedAt.AddMinutes(resMin);
        if (w.Status == WorkItemStatus.Done)
            return new SlaInfo(due, (w.ResolvedAt ?? w.UpdatedAt) <= due ? "met" : "missed");
        var now = DateTime.UtcNow;
        if (now >= due) return new SlaInfo(due, "breached");
        if (now >= due.AddMinutes(-resMin * 0.25)) return new SlaInfo(due, "risk");  // within last 25% of window
        return new SlaInfo(due, "ok");
    }
}
