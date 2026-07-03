namespace TaskDesk.Api.Models;

// ---- Reference values (stored as text; validated at the edge) ----
public static class WorkItemStatus { public const string Todo = "todo", Prog = "prog", Wait = "wait", Done = "done";
    public static readonly string[] All = [Todo, Prog, Wait, Done]; }
public static class WorkItemType { public static readonly string[] All = ["ticket", "task", "bug"]; }
public static class Priority { public static readonly string[] All = ["low", "med", "high", "urgent"]; }

// ---- Core domain (system of record) ----
public class Customer
{
    public Guid Id { get; set; } = Guid.NewGuid();
    public string Key { get; set; } = "";        // e.g. ACME
    public string Name { get; set; } = "";
    public string Plan { get; set; } = "Business";
    public List<Project> Projects { get; set; } = [];
}

public class Project
{
    public Guid Id { get; set; } = Guid.NewGuid();
    public string Key { get; set; } = "";        // e.g. ACME-SUP
    public string Name { get; set; } = "";
    public Guid CustomerId { get; set; }
    public Customer? Customer { get; set; }
    public string Type { get; set; } = "Service desk";        // Service desk | Delivery
    public string ServiceType { get; set; } = "Managed Service (AMC)";
    public string Lead { get; set; } = "";
    public int Seq { get; set; }                 // running counter for work-item keys
    public List<WorkItem> WorkItems { get; set; } = [];
}

public class WorkItem
{
    public Guid Id { get; set; } = Guid.NewGuid();
    public string Key { get; set; } = "";        // e.g. ACME-SUP-42
    public Guid ProjectId { get; set; }
    public Project? Project { get; set; }
    public string Type { get; set; } = "ticket";
    public string Title { get; set; } = "";
    public string Description { get; set; } = "";
    public string Status { get; set; } = WorkItemStatus.Todo;
    public string PriorityLevel { get; set; } = "med";
    public string? Assignee { get; set; }
    public string Requester { get; set; } = "";
    public DateTime CreatedAt { get; set; } = DateTime.UtcNow;
    public DateTime UpdatedAt { get; set; } = DateTime.UtcNow;
    public List<Comment> Comments { get; set; } = [];
    public List<ActivityEntry> Activity { get; set; } = [];
}

public class Comment
{
    public Guid Id { get; set; } = Guid.NewGuid();
    public Guid WorkItemId { get; set; }
    public string Author { get; set; } = "";
    public string Body { get; set; } = "";
    public bool IsInternal { get; set; }
    public DateTime CreatedAt { get; set; } = DateTime.UtcNow;
}

public class ActivityEntry
{
    public Guid Id { get; set; } = Guid.NewGuid();
    public Guid WorkItemId { get; set; }
    public string Actor { get; set; } = "";
    public string Verb { get; set; } = "";
    public string Detail { get; set; } = "";
    public DateTime CreatedAt { get; set; } = DateTime.UtcNow;
}

// ---- Module / plugin contract (§14/§20) ----
public class Module
{
    public string Key { get; set; } = "";        // PK, e.g. managed_service
    public string Name { get; set; } = "";
    public string Description { get; set; } = "";
    public bool DefaultEnabled { get; set; } = true;
}

public class ModuleState
{
    public Guid Id { get; set; } = Guid.NewGuid();
    public string ModuleKey { get; set; } = "";
    public Guid? CustomerId { get; set; }        // null = global default
    public bool Enabled { get; set; }
}
