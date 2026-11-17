using Microsoft.AspNetCore.Mvc;
using Tickets.Api.Data;
using Tickets.Api.Domain;

namespace Tickets.Api.Controllers;

[ApiController]
[Route("api/agents")]
public class AgentsController : ControllerBase
{
    private readonly AppDbContext _db;

    public AgentsController(AppDbContext db) => _db = db;

    [HttpPost]
    public async Task<IActionResult> Create(Agent agent)
    {
        _db.Agents.Add(agent);
        await _db.SaveChangesAsync();
        return Ok(agent.Id);
    }
}
