using Microsoft.EntityFrameworkCore;
using TaskDesk.Api.Api;
using TaskDesk.Api.Data;

var builder = WebApplication.CreateBuilder(args);

// --- Database ---
// Provider chosen at runtime via DB_PROVIDER: "sqlite" (default, zero-dependency for `dotnet run`)
// or "sqlserver"/"mssql" (the docker-compose stack). (PLAN §19 Q7)
var provider = (builder.Configuration["DB_PROVIDER"] ?? "sqlite").ToLowerInvariant();
builder.Services.AddDbContext<AppDbContext>(o =>
{
    if (provider is "sqlserver" or "mssql")
    {
        var cs = builder.Configuration["DB_CONNECTION"]
            ?? "Server=localhost,1433;Database=taskdesk;User Id=sa;Password=1qaz!QAZ;TrustServerCertificate=True;Encrypt=False";
        o.UseSqlServer(cs, sql => sql.EnableRetryOnFailure());
    }
    else
    {
        var dbPath = builder.Configuration["DB_PATH"] ?? "taskdesk.db";
        o.UseSqlite($"Data Source={dbPath}");
    }
});

builder.Services.AddOpenApi();
builder.Services.AddCors(o => o.AddDefaultPolicy(p => p.AllowAnyOrigin().AllowAnyHeader().AllowAnyMethod()));

var app = builder.Build();
app.UseCors();

// OpenAPI document: JSON (live, auto-generated) at /openapi/v1.json, YAML snapshot at /api/docs.yaml
app.MapOpenApi();
app.MapGet("/api/docs.yaml", () =>
{
    var path = Path.Combine(AppContext.BaseDirectory, "openapi.yaml");
    return File.Exists(path)
        ? Results.File(path, "application/yaml")
        : Results.NotFound();
}).ExcludeFromDescription();

// --- Create schema + seed demo data on boot (retry: the DB container may still be starting) ---
using (var scope = app.Services.CreateScope())
{
    var db = scope.ServiceProvider.GetRequiredService<AppDbContext>();
    for (var attempt = 1; ; attempt++)
    {
        try { db.Database.EnsureCreated(); Seeder.Seed(db); break; }
        catch (Exception ex) when (attempt < 20)
        {
            Console.WriteLine($"[startup] database not ready (attempt {attempt}): {ex.Message} — retrying in 3s");
            Thread.Sleep(3000);
        }
    }
}

// --- Health probes ---
app.MapGet("/healthz", () => Results.Ok(new { status = "ok" })).ExcludeFromDescription();
app.MapGet("/readyz", async (AppDbContext db) =>
    await db.Database.CanConnectAsync() ? Results.Ok(new { status = "ready" }) : Results.StatusCode(503))
   .ExcludeFromDescription();

// --- API ---
app.MapApi();

app.Run();
