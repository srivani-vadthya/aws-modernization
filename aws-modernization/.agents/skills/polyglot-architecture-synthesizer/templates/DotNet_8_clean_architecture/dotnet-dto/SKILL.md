---
name: dotnet-dto
description: "DTO pattern: separate CreateRequest, UpdateRequest, and Response records per entity — no model exposure in API contracts"
tags: ["dto", "request", "response", "contract", "create", "update", "api", "payload"]
trigger: dto
---

# DTO (Data Transfer Objects) — Golden Pattern

## When to Apply
Every entity exposed through the API needs 3 DTO classes in one file — never expose the Model directly.

## File per Entity Convention
One file: `DTOs/{Entity}Dto.cs` containing all 3 classes.

## Exact Golden Pattern

```csharp
// filepath: {ProjectName}/DTOs/CustomerDto.cs
namespace {ProjectName}.DTOs;

// Used for POST (create) — no Id, no audit fields
public class CreateCustomerRequest
{
    public string FirstName { get; set; } = string.Empty;
    public string LastName { get; set; } = string.Empty;
    public string Email { get; set; } = string.Empty;
    public string Phone { get; set; } = string.Empty;
    public DateTime DateOfBirth { get; set; }
}

// Used for PUT (update) — only mutable fields
public class UpdateCustomerRequest
{
    public string FirstName { get; set; } = string.Empty;
    public string LastName { get; set; } = string.Empty;
    public string Email { get; set; } = string.Empty;
    public string Phone { get; set; } = string.Empty;
}

// Used for GET responses — includes Id, audit fields, computed fields
public class CustomerResponse
{
    public int Id { get; set; }
    public string FirstName { get; set; } = string.Empty;
    public string LastName { get; set; } = string.Empty;
    public string Email { get; set; } = string.Empty;
    public string Phone { get; set; } = string.Empty;
    public DateTime DateOfBirth { get; set; }
    public DateTime CreatedAt { get; set; }
}
```

## Pattern for PATCH (partial update — status-only)

```csharp
// filepath: {ProjectName}/DTOs/ClaimDto.cs
namespace {ProjectName}.DTOs;

public class CreateClaimRequest
{
    public int PolicyId { get; set; }
    public decimal ClaimAmount { get; set; }
    public string Description { get; set; } = string.Empty;
    public DateTime ClaimDate { get; set; }
}

// Minimal update DTO — only the status field (used with PATCH)
public class UpdateClaimRequest
{
    public string Status { get; set; } = string.Empty;
}

public class ClaimResponse
{
    public int Id { get; set; }
    public string ClaimNumber { get; set; } = string.Empty;
    public int PolicyId { get; set; }
    public string PolicyNumber { get; set; } = string.Empty;  // ← denormalized from related entity
    public decimal ClaimAmount { get; set; }
    public string Description { get; set; } = string.Empty;
    public DateTime ClaimDate { get; set; }
    public string Status { get; set; } = string.Empty;
    public DateTime CreatedAt { get; set; }
}
```

## Rules
1. **Never** expose `Model` classes directly from controllers — always use DTOs
2. `CreateRequest` — no `Id`, no `CreatedAt`
3. `UpdateRequest` — only the fields that can be changed; omit system fields
4. `Response` — includes `Id`, `CreatedAt`, and any denormalized fields from related entities
5. Denormalized fields in Response (e.g., `PolicyNumber` on `ClaimResponse`) are fine and preferred over nested objects
