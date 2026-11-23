using MediatR;
using Microsoft.EntityFrameworkCore;
using Tickets.Api.Data;
using Tickets.Api.Domain;

namespace Tickets.Api.Services;

public class TicketService
{
    private readonly AppDbContext _db;
    private readonly IMediator _mediator;
    private readonly EventBridgeClient _bridge;

    public TicketService(AppDbContext db, IMediator mediator, EventBridgeClient bridge)
    {
        _db = db;
        _mediator = mediator;
        _bridge = bridge;
    }

    public async Task<Ticket?> Find(int id)
    {
        return await _db.Tickets.FirstOrDefaultAsync(t => t.Id == id);
    }

    public async Task<int> Open(string title)
    {
        var ticket = new Ticket { Title = title };
        _db.Tickets.Add(ticket);
        ticket.Notes.Add(new TicketNote { Text = "opened" });
        _db.Notes.Add(ticket.Notes[0]);
        await _db.SaveChangesAsync();
        await _mediator.Publish(new TicketOpened(ticket.Id));
        return ticket.Id;
    }

    public void Archive(int id)
    {
        // "Publish TicketArchived to Amazon EventBridge" -- this comment must not create an event
        _bridge.Send(id);
    }
}
