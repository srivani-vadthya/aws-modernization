---
name: dotnet-controller
description: "ASP.NET Core ApiController pattern: [ApiController][Route] attributes, constructor injection of service only, ActionResult<T> return types, CreatedAtAction for POST, BadRequest for InvalidOperationException, NoContent for DELETE"
tags: ["controller", "endpoint", "route", "http", "get", "post", "put", "patch", "delete", "api", "mvc", "rest"]
trigger: controller
---

# ASP.NET Core Controller — Golden Pattern

## When to Apply
Every entity exposed via HTTP needs one controller. Controllers contain **no business logic** — they only translate HTTP ↔ service calls.

## Standard CRUD Controller

```csharp
// filepath: {ProjectName}/Controllers/CustomersController.cs
using {ProjectName}.DTOs;
using {ProjectName}.Services.Interfaces;
using Microsoft.AspNetCore.Mvc;

namespace {ProjectName}.Controllers;

[ApiController]
[Route("api/[controller]")]
public class CustomersController : ControllerBase
{
    private readonly ICustomerService _customerService;

    public CustomersController(ICustomerService customerService)
    {
        _customerService = customerService;
    }

    // GET api/customers
    [HttpGet]
    public async Task<ActionResult<IEnumerable<CustomerResponse>>> GetAll()
    {
        var items = await _customerService.GetAllCustomersAsync();
        return Ok(items);
    }

    // GET api/customers/{id}
    [HttpGet("{id}")]
    public async Task<ActionResult<CustomerResponse>> GetById(int id)
    {
        var item = await _customerService.GetCustomerByIdAsync(id);
        if (item == null)
            return NotFound();

        return Ok(item);
    }

    // POST api/customers
    [HttpPost]
    public async Task<ActionResult<CustomerResponse>> Create(CreateCustomerRequest request)
    {
        try
        {
            var created = await _customerService.CreateCustomerAsync(request);
            return CreatedAtAction(nameof(GetById), new { id = created.Id }, created);
        }
        catch (InvalidOperationException ex)
        {
            return BadRequest(ex.Message);
        }
    }

    // PUT api/customers/{id}
    [HttpPut("{id}")]
    public async Task<ActionResult<CustomerResponse>> Update(int id, UpdateCustomerRequest request)
    {
        var updated = await _customerService.UpdateCustomerAsync(id, request);
        if (updated == null)
            return NotFound();

        return Ok(updated);
    }

    // DELETE api/customers/{id}
    [HttpDelete("{id}")]
    public async Task<IActionResult> Delete(int id)
    {
        var result = await _customerService.DeleteCustomerAsync(id);
        if (!result)
            return NotFound();

        return NoContent();   // ← 204 No Content for successful deletes
    }
}
```

## Controller with Domain Sub-Routes (child entity)

```csharp
// filepath: {ProjectName}/Controllers/ClaimsController.cs
using {ProjectName}.DTOs;
using {ProjectName}.Services.Interfaces;
using Microsoft.AspNetCore.Mvc;

namespace {ProjectName}.Controllers;

[ApiController]
[Route("api/[controller]")]
public class ClaimsController : ControllerBase
{
    private readonly IClaimService _claimService;

    public ClaimsController(IClaimService claimService)
    {
        _claimService = claimService;
    }

    // GET api/claims/policy/{policyId}  ← filter by parent FK
    [HttpGet("policy/{policyId}")]
    public async Task<ActionResult<IEnumerable<ClaimResponse>>> GetByPolicyId(int policyId)
    {
        var claims = await _claimService.GetClaimsByPolicyIdAsync(policyId);
        return Ok(claims);
    }

    // PATCH api/claims/{id}/status  ← partial update with sub-path
    [HttpPatch("{id}/status")]
    public async Task<ActionResult<ClaimResponse>> UpdateStatus(int id, UpdateClaimRequest request)
    {
        var updated = await _claimService.UpdateClaimStatusAsync(id, request);
        if (updated == null)
            return NotFound();

        return Ok(updated);
    }
}
```

## HTTP Verb → Return Type Rules

| Verb | Success Return | Not Found | Business Error |
|------|---------------|-----------|----------------|
| GET (list) | `Ok(items)` — 200 | N/A | N/A |
| GET (single) | `Ok(item)` — 200 | `NotFound()` — 404 | N/A |
| POST | `CreatedAtAction(nameof(GetById), new { id }, item)` — 201 | N/A | `BadRequest(ex.Message)` — 400 |
| PUT | `Ok(updated)` — 200 | `NotFound()` — 404 | `BadRequest(ex.Message)` — 400 |
| PATCH | `Ok(updated)` — 200 | `NotFound()` — 404 | N/A |
| DELETE | `NoContent()` — 204 | `NotFound()` — 404 | N/A |

## Rules
1. Inject **service interface only** — never inject repositories directly into controllers
2. `[ApiController]` + `[Route("api/[controller]")]` on EVERY controller — no exceptions
3. `ControllerBase` not `Controller` — we don't serve views
4. `CreatedAtAction` for POST — never `Created("/api/...", item)`
5. Catch only `InvalidOperationException` — let other exceptions bubble to middleware
6. `IActionResult` for DELETE (no response body); `ActionResult<T>` for all others
