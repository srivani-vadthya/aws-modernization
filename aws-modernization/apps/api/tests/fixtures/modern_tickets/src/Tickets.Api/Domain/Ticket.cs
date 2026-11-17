namespace Tickets.Api.Domain;

public class Ticket
{
    public int Id { get; set; }
    public string Title { get; set; } = "";
    public int? AssigneeId { get; set; }
    public Agent? Assignee { get; set; }
    public List<TicketNote> Notes { get; set; } = new();
}

public class TicketNote
{
    public int Id { get; set; }
    public string Text { get; set; } = "";
    public int TicketId { get; set; }
    public Ticket Ticket { get; set; } = null!;
}

public class Agent
{
    public int Id { get; set; }
    public string Name { get; set; } = "";
}

public record TicketOpened(int TicketId) : MediatR.INotification;
