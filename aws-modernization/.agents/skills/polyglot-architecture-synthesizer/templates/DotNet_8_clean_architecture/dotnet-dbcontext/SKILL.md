---
name: dotnet-dbcontext
description: "EF Core DbContext pattern: OnModelCreating with Fluent API constraints, decimal precision, unique indexes, HasOne/WithMany relationships, DeleteBehavior.Restrict — no data annotations on models"
tags: ["dbcontext", "ef", "entityframework", "database", "migration", "fluent", "onmodelcreating", "schema", "index", "foreign-key"]
trigger: dbcontext
---

# EF Core DbContext — Golden Pattern

## When to Apply
One `DbContext` per project, one `OnModelCreating` containing ALL entity configurations.

## Exact Golden Pattern

```csharp
// filepath: {ProjectName}/Data/{ProjectName}DbContext.cs
using {ProjectName}.Models;
using Microsoft.EntityFrameworkCore;

namespace {ProjectName}.Data;

public class {ProjectName}DbContext : DbContext
{
    public {ProjectName}DbContext(DbContextOptions<{ProjectName}DbContext> options) : base(options) { }

    // One DbSet per entity
    public DbSet<Customer> Customers { get; set; }
    public DbSet<Policy> Policies { get; set; }
    public DbSet<Claim> Claims { get; set; }

    protected override void OnModelCreating(ModelBuilder modelBuilder)
    {
        base.OnModelCreating(modelBuilder);

        // ── Customer ─────────────────────────────────────────────────────────
        modelBuilder.Entity<Customer>(entity =>
        {
            entity.HasKey(e => e.Id);
            entity.Property(e => e.FirstName).IsRequired().HasMaxLength(100);
            entity.Property(e => e.LastName).IsRequired().HasMaxLength(100);
            entity.Property(e => e.Email).IsRequired().HasMaxLength(200);
            entity.HasIndex(e => e.Email).IsUnique();               // ← unique constraint
            entity.Property(e => e.Phone).HasMaxLength(20);
        });

        // ── Policy ───────────────────────────────────────────────────────────
        modelBuilder.Entity<Policy>(entity =>
        {
            entity.HasKey(e => e.Id);
            entity.Property(e => e.PolicyNumber).IsRequired().HasMaxLength(50);
            entity.HasIndex(e => e.PolicyNumber).IsUnique();
            entity.Property(e => e.Type).IsRequired().HasMaxLength(50);
            entity.Property(e => e.Premium).HasColumnType("decimal(18,2)");         // ← always specify decimal precision
            entity.Property(e => e.CoverageAmount).HasColumnType("decimal(18,2)");
            entity.Property(e => e.Status).HasMaxLength(20);

            // Relationship: Policy → Customer (many-to-one)
            entity.HasOne(e => e.Customer)
                .WithMany(c => c.Policies)
                .HasForeignKey(e => e.CustomerId)
                .OnDelete(DeleteBehavior.Restrict);                 // ← ALWAYS Restrict, never Cascade
        });

        // ── Claim ────────────────────────────────────────────────────────────
        modelBuilder.Entity<Claim>(entity =>
        {
            entity.HasKey(e => e.Id);
            entity.Property(e => e.ClaimNumber).IsRequired().HasMaxLength(50);
            entity.HasIndex(e => e.ClaimNumber).IsUnique();
            entity.Property(e => e.ClaimAmount).HasColumnType("decimal(18,2)");
            entity.Property(e => e.Description).HasMaxLength(500);
            entity.Property(e => e.Status).HasMaxLength(20);

            entity.HasOne(e => e.Policy)
                .WithMany(p => p.Claims)
                .HasForeignKey(e => e.PolicyId)
                .OnDelete(DeleteBehavior.Restrict);
        });
    }
}
```

## appsettings.json — Connection String

```json
// filepath: {ProjectName}/appsettings.json
{
  "ConnectionStrings": {
    "DefaultConnection": "Server=(localdb)\\mssqllocaldb;Database={ProjectName}Db;Trusted_Connection=true;MultipleActiveResultSets=true"
  },
  "Logging": {
    "LogLevel": {
      "Default": "Information",
      "Microsoft.AspNetCore": "Warning"
    }
  },
  "AllowedHosts": "*"
}
```

## Rules
1. ALL constraints in `OnModelCreating` — zero data annotations on models
2. `decimal(18,2)` for all money/price/amount fields — never `decimal` without precision
3. `HasIndex(...).IsUnique()` for business-unique fields (email, number, code)
4. `OnDelete(DeleteBehavior.Restrict)` on ALL foreign keys — never `Cascade` or `NoAction`
5. `HasMaxLength` on all strings — never unlimited string columns
6. One `DbContext` per project — never multiple contexts
