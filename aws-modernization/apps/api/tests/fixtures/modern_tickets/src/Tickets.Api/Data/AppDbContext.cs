using Microsoft.EntityFrameworkCore;
using Tickets.Api.Domain;

namespace Tickets.Api.Data;

public class AppDbContext : DbContext
{
    public AppDbContext(DbContextOptions<AppDbContext> options) : base(options) { }

    public DbSet<Ticket> Tickets => Set<Ticket>();
    public DbSet<TicketNote> Notes => Set<TicketNote>();
    public DbSet<Agent> Agents => Set<Agent>();
}
