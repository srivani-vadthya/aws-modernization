using IMS.Modernized.WebAPI.Data;
using IMS.Modernized.WebAPI.Domain;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace IMS.Modernized.WebAPI.Controllers;

[ApiController]
[Route("api/[controller]")]
[Produces("application/json")]
public class PoliciesController : ControllerBase
{
    private readonly ModernImsDbContext _db;
    private readonly ILogger<PoliciesController> _logger;

    public PoliciesController(ModernImsDbContext db, ILogger<PoliciesController> logger)
    {
        _db = db;
        _logger = logger;
    }

    [HttpGet]
    public async Task<ActionResult<IEnumerable<Policy>>> GetAll([FromQuery] string? status)
    {
        _logger.LogInformation("Querying modernized policies with status filter: {Status}", status);
        var query = _db.Policies.AsNoTracking();
        if (!string.IsNullOrEmpty(status))
        {
            query = query.Where(p => p.Status == status);
        }
        return await query.ToListAsync();
    }

    [HttpGet("{id}")]
    public async Task<ActionResult<Policy>> GetById(int id)
    {
        var policy = await _db.Policies.FindAsync(id);
        if (policy == null) return NotFound(new { message = $"Policy {id} not found" });
        return Ok(policy);
    }

    [HttpPost]
    public async Task<ActionResult<Policy>> Create([FromBody] Policy policy)
    {
        policy.CreatedAt = DateTime.UtcNow;
        _db.Policies.Add(policy);
        await _db.SaveChangesAsync();

        _logger.LogInformation("Created modernized policy {PolicyNumber} (ID: {PolicyId})", policy.PolicyNumber, policy.PolicyId);
        return CreatedAtAction(nameof(GetById), new { id = policy.PolicyId }, policy);
    }

    [HttpPut("{id}/bind")]
    public async Task<IActionResult> BindPolicy(int id)
    {
        var policy = await _db.Policies.FindAsync(id);
        if (policy == null) return NotFound();

        policy.Status = "Bound";
        await _db.SaveChangesAsync();
        return Ok(new { message = "Policy successfully bound under modernized underwriting rules", policy });
    }
}
