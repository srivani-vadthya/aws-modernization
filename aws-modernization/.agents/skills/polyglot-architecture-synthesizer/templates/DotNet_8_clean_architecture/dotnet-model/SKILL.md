---
name: dotnet-model
description: "Domain entity (Model) pattern: file-scoped namespaces, auto-properties with default initializers, navigation properties, no data annotations on model — constraints go in DbContext"
tags: ["model", "entity", "domain", "class", "property", "navigation", "poco"]
trigger: model
---

# Domain Model — Golden Pattern

## When to Apply
Every legacy C# entity class, data model, or table-mapped object.

## Rules
1. Use **file-scoped namespaces** — `namespace X;` not `namespace X { }`
2. All string properties default to `string.Empty` — never `null`
3. Navigation collections initialize to `new List<T>()` — never null
4. Required navigation properties use `null!` (null-forgiving) — no `?` on required refs
5. **No** `[Required]`, `[MaxLength]`, `[Column]` annotations on models — ALL constraints go in `DbContext.OnModelCreating`
6. Always include `CreatedAt = DateTime.UtcNow` on root entities

## Exact Golden Pattern — Simple Entity

```csharp
// filepath: {ProjectName}/Models/Customer.cs
namespace {ProjectName}.Models;

public class Customer
{
    public int Id { get; set; }
    public string FirstName { get; set; } = string.Empty;
    public string LastName { get; set; } = string.Empty;
    public string Email { get; set; } = string.Empty;
    public string Phone { get; set; } = string.Empty;
    public DateTime DateOfBirth { get; set; }
    public DateTime CreatedAt { get; set; } = DateTime.UtcNow;

    // Navigation — one-to-many
    public ICollection<Policy> Policies { get; set; } = new List<Policy>();
}
```

## Exact Golden Pattern — Entity with FK

```csharp
// filepath: {ProjectName}/Models/Policy.cs
namespace {ProjectName}.Models;

public class Policy
{
    public int Id { get; set; }
    public string PolicyNumber { get; set; } = string.Empty;
    public string Type { get; set; } = string.Empty;
    public decimal Premium { get; set; }
    public decimal CoverageAmount { get; set; }
    public DateTime StartDate { get; set; }
    public DateTime EndDate { get; set; }
    public string Status { get; set; } = "Active";   // ← default status string

    // Foreign key
    public int CustomerId { get; set; }

    // Required navigation — use null! not null
    public Customer Customer { get; set; } = null!;

    // Child collection
    public ICollection<Claim> Claims { get; set; } = new List<Claim>();
}
```

## Status Field Convention
When an entity has a status field, always default it to the initial active state:
```csharp
public string Status { get; set; } = "Active";  // or "Pending", "Open" etc.
```
