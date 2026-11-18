using IMS.Modernized.WebAPI.Data;
using IMS.Modernized.WebAPI.Domain;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace IMS.Modernized.WebAPI.Controllers;

[ApiController]
[Route("api/[controller]")]
[Produces("application/json")]
public class ClaimsController : ControllerBase
{
    private readonly ModernImsDbContext _db;

    public ClaimsController(ModernImsDbContext db)
    {
        _db = db;
    }

    [HttpGet]
    public async Task<ActionResult<IEnumerable<Claim>>> GetAll()
    {
        return await _db.Claims.AsNoTracking().ToListAsync();
    }

    [HttpPost]
    public async Task<ActionResult<Claim>> Submit([FromBody] Claim claim)
    {
        claim.ReportedDate = DateTime.UtcNow;
        claim.ClaimNumber = $"CLM-{DateTime.UtcNow.Ticks % 1000000:D6}";
        _db.Claims.Add(claim);
        await _db.SaveChangesAsync();
        return Ok(claim);
    }
}
