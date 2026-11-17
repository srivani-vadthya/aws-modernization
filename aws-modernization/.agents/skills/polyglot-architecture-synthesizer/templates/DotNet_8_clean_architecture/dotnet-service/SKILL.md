---
name: dotnet-service
description: "Service layer pattern: interface returning DTOs (never Models), implementation injecting repositories, MapToResponse private static method, business rule validation via InvalidOperationException, generated identifiers"
tags: ["service", "business", "logic", "mapping", "dto", "validation", "interface", "implementation"]
trigger: service
---

# Service Layer — Golden Pattern

## When to Apply
Every entity needs an `I{Entity}Service` interface and `{Entity}Service` implementation.

## Key Principles
- Services speak **DTOs** — inputs are `Request` DTOs, outputs are `Response` DTOs
- Services know nothing about HTTP — no `IActionResult`, no status codes
- Business rule violations throw `InvalidOperationException` — controllers catch and return `BadRequest`
- `MapToResponse` is a `private static` method — never public, never in the Model

## Interface — Golden Pattern

```csharp
// filepath: {ProjectName}/Services/Interfaces/ICustomerService.cs
using {ProjectName}.DTOs;

namespace {ProjectName}.Services.Interfaces;

public interface ICustomerService
{
    Task<IEnumerable<CustomerResponse>> GetAllCustomersAsync();
    Task<CustomerResponse?> GetCustomerByIdAsync(int id);
    Task<CustomerResponse> CreateCustomerAsync(CreateCustomerRequest request);
    Task<CustomerResponse?> UpdateCustomerAsync(int id, UpdateCustomerRequest request);
    Task<bool> DeleteCustomerAsync(int id);
}
```

## Implementation — Simple Entity Service

```csharp
// filepath: {ProjectName}/Services/Implementations/CustomerService.cs
using {ProjectName}.Data.Repository.Interfaces;
using {ProjectName}.DTOs;
using {ProjectName}.Models;
using {ProjectName}.Services.Interfaces;

namespace {ProjectName}.Services.Implementations;

public class CustomerService : ICustomerService
{
    private readonly ICustomerRepository _customerRepository;

    public CustomerService(ICustomerRepository customerRepository)
    {
        _customerRepository = customerRepository;
    }

    public async Task<IEnumerable<CustomerResponse>> GetAllCustomersAsync()
    {
        var customers = await _customerRepository.GetAllAsync();
        return customers.Select(MapToResponse);
    }

    public async Task<CustomerResponse?> GetCustomerByIdAsync(int id)
    {
        var customer = await _customerRepository.GetByIdAsync(id);
        return customer == null ? null : MapToResponse(customer);
    }

    public async Task<CustomerResponse> CreateCustomerAsync(CreateCustomerRequest request)
    {
        // Business rule: uniqueness check — throw for duplicates
        var existing = await _customerRepository.GetByEmailAsync(request.Email);
        if (existing != null)
            throw new InvalidOperationException("Customer with this email already exists");

        var customer = new Customer
        {
            FirstName = request.FirstName,
            LastName = request.LastName,
            Email = request.Email,
            Phone = request.Phone,
            DateOfBirth = request.DateOfBirth
        };

        var created = await _customerRepository.CreateAsync(customer);
        return MapToResponse(created);
    }

    public async Task<CustomerResponse?> UpdateCustomerAsync(int id, UpdateCustomerRequest request)
    {
        var customer = await _customerRepository.GetByIdAsync(id);
        if (customer == null) return null;   // ← null = not found; controller returns NotFound

        customer.FirstName = request.FirstName;
        customer.LastName = request.LastName;
        customer.Email = request.Email;
        customer.Phone = request.Phone;

        var updated = await _customerRepository.UpdateAsync(customer);
        return MapToResponse(updated);
    }

    public async Task<bool> DeleteCustomerAsync(int id)
        => await _customerRepository.DeleteAsync(id);

    // Private static mapper — never instance method, never public
    private static CustomerResponse MapToResponse(Customer customer) => new()
    {
        Id = customer.Id,
        FirstName = customer.FirstName,
        LastName = customer.LastName,
        Email = customer.Email,
        Phone = customer.Phone,
        DateOfBirth = customer.DateOfBirth,
        CreatedAt = customer.CreatedAt
    };
}
```

## Implementation — Service with Cross-Entity Validation + Generated ID

```csharp
// filepath: {ProjectName}/Services/Implementations/ClaimService.cs
using {ProjectName}.Data.Repository.Interfaces;
using {ProjectName}.DTOs;
using {ProjectName}.Models;
using {ProjectName}.Services.Interfaces;

namespace {ProjectName}.Services.Implementations;

public class ClaimService : IClaimService
{
    private readonly IClaimRepository _claimRepository;
    private readonly IPolicyRepository _policyRepository;   // ← inject related repo for FK check

    public ClaimService(IClaimRepository claimRepository, IPolicyRepository policyRepository)
    {
        _claimRepository = claimRepository;
        _policyRepository = policyRepository;
    }

    public async Task<ClaimResponse> CreateClaimAsync(CreateClaimRequest request)
    {
        // Cross-entity validation via ExistsAsync — don't fetch full object
        var policyExists = await _policyRepository.ExistsAsync(request.PolicyId);
        if (!policyExists)
            throw new InvalidOperationException("Policy not found");

        var claim = new Claim
        {
            ClaimNumber = GenerateClaimNumber(),   // ← generated identifier
            PolicyId = request.PolicyId,
            ClaimAmount = request.ClaimAmount,
            Description = request.Description,
            ClaimDate = request.ClaimDate
        };

        var created = await _claimRepository.CreateAsync(claim);
        return MapToResponse(created);
    }

    // Business number generation — always static private
    private static string GenerateClaimNumber()
        => $"CLM-{DateTime.UtcNow:yyyyMMdd}-{Guid.NewGuid().ToString()[..8].ToUpper()}";

    private static ClaimResponse MapToResponse(Claim claim) => new()
    {
        Id = claim.Id,
        ClaimNumber = claim.ClaimNumber,
        PolicyId = claim.PolicyId,
        PolicyNumber = claim.Policy?.PolicyNumber ?? string.Empty,
        ClaimAmount = claim.ClaimAmount,
        Description = claim.Description,
        ClaimDate = claim.ClaimDate,
        Status = claim.Status,
        CreatedAt = claim.CreatedAt
    };
}
```

## Rules
1. Methods return `null` when not found — **never** throw `NotFoundException` — controllers handle that
2. `InvalidOperationException` for business rule violations only
3. `MapToResponse` is always `private static` — target-typed `new()` syntax
4. Cross-entity validation via `ExistsAsync` — never fetch full object just to check existence
5. Generated identifiers (claim numbers, order numbers) live in `private static` methods in the service
