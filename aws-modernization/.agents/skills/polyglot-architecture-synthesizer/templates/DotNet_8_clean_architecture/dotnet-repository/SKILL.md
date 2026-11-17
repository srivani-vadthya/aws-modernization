---
name: dotnet-repository
description: "Repository pattern: IRepository interface with async CRUD + domain queries, EF Core implementation injecting DbContext via constructor — no business logic in repositories"
tags: ["repository", "data", "dbcontext", "ef", "entityframework", "crud", "async", "database", "sql"]
trigger: repository
---

# Repository Pattern — Golden Pattern

## When to Apply
Every entity that is persisted to the database needs an interface and implementation pair.

## Interface — Golden Pattern

```csharp
// filepath: {ProjectName}/Data/Repository/Interfaces/ICustomerRepository.cs
using {ProjectName}.Models;

namespace {ProjectName}.Data.Repository.Interfaces;

public interface ICustomerRepository
{
    Task<IEnumerable<Customer>> GetAllAsync();
    Task<Customer?> GetByIdAsync(int id);
    Task<Customer?> GetByEmailAsync(string email);     // ← domain-specific query
    Task<Customer> CreateAsync(Customer customer);
    Task<Customer> UpdateAsync(Customer customer);
    Task<bool> DeleteAsync(int id);
    Task<bool> ExistsAsync(int id);                    // ← used by services for FK validation
}
```

## Domain-Specific Query Example (child entity)

```csharp
// filepath: {ProjectName}/Data/Repository/Interfaces/IClaimRepository.cs
using {ProjectName}.Models;

namespace {ProjectName}.Data.Repository.Interfaces;

public interface IClaimRepository
{
    Task<IEnumerable<Claim>> GetAllAsync();
    Task<Claim?> GetByIdAsync(int id);
    Task<IEnumerable<Claim>> GetByPolicyIdAsync(int policyId);   // ← filter by FK
    Task<Claim> CreateAsync(Claim claim);
    Task<Claim> UpdateAsync(Claim claim);
    Task<bool> DeleteAsync(int id);
}
```

## Implementation — Golden Pattern

```csharp
// filepath: {ProjectName}/Data/Repository/Implementations/CustomerRepository.cs
using {ProjectName}.Data.Repository.Interfaces;
using {ProjectName}.Models;
using Microsoft.EntityFrameworkCore;

namespace {ProjectName}.Data.Repository.Implementations;

public class CustomerRepository : ICustomerRepository
{
    private readonly {ProjectName}DbContext _context;

    public CustomerRepository({ProjectName}DbContext context)
    {
        _context = context;
    }

    public async Task<IEnumerable<Customer>> GetAllAsync()
        => await _context.Customers.ToListAsync();

    public async Task<Customer?> GetByIdAsync(int id)
        => await _context.Customers.FindAsync(id);

    public async Task<Customer?> GetByEmailAsync(string email)
        => await _context.Customers.FirstOrDefaultAsync(c => c.Email == email);

    public async Task<Customer> CreateAsync(Customer customer)
    {
        _context.Customers.Add(customer);
        await _context.SaveChangesAsync();
        return customer;
    }

    public async Task<Customer> UpdateAsync(Customer customer)
    {
        _context.Customers.Update(customer);
        await _context.SaveChangesAsync();
        return customer;
    }

    public async Task<bool> DeleteAsync(int id)
    {
        var entity = await _context.Customers.FindAsync(id);
        if (entity == null) return false;

        _context.Customers.Remove(entity);
        await _context.SaveChangesAsync();
        return true;
    }

    public async Task<bool> ExistsAsync(int id)
        => await _context.Customers.AnyAsync(c => c.Id == id);
}
```

## Rules
1. **No business logic** in repositories — only data access (no validation, no exceptions for business rules)
2. Expression-body methods for single-line operations (`=> await ...`)
3. `FindAsync(id)` for PK lookup — faster than `FirstOrDefault`
4. `FirstOrDefaultAsync(lambda)` for non-PK queries
5. Always `await _context.SaveChangesAsync()` after Add/Update/Remove
6. `DeleteAsync` pattern: fetch first, check null, then remove — return `false` if not found
7. `ExistsAsync` using `AnyAsync` — never fetch the full entity just to check existence
