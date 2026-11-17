using Microsoft.AspNetCore.Mvc;
using Tickets.Api.Services;

namespace Tickets.Api.Controllers;

[ApiController]
[Route("api/[controller]")]
public class TicketsController : ControllerBase
{
    private readonly TicketService _service;
    private readonly GeoClient _geo;

    public TicketsController(TicketService service, GeoClient geo)
    {
        _service = service;
        _geo = geo;
    }

    [HttpGet("{id:int}")]
    public async Task<IActionResult> Get(int id)
    {
        var t = await _service.Find(id);
        return t is null ? NotFound() : Ok(t);
    }

    [HttpPost]
    public async Task<IActionResult> Create(CreateTicket body)
    {
        var city = await _geo.Lookup(body.City);
        return Ok(await _service.Open(body.Title + city));
    }

    [HttpPost("{id:int}/archive")]
    public IActionResult Archive(int id)
    {
        _service.Archive(id);
        return NoContent();
    }
}

public record CreateTicket(string Title, string City);
