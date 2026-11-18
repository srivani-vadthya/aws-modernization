using IMS.Modernized.WebAPI.Domain;
using Microsoft.EntityFrameworkCore;

namespace IMS.Modernized.WebAPI.Data;

public class ModernImsDbContext : DbContext
{
    public ModernImsDbContext(DbContextOptions<ModernImsDbContext> options) : base(options) { }

    public DbSet<Policy> Policies => Set<Policy>();
    public DbSet<Client> Clients => Set<Client>();
    public DbSet<Claim> Claims => Set<Claim>();

    protected override void OnModelCreating(ModelBuilder modelBuilder)
    {
        base.OnModelCreating(modelBuilder);

        // Fluent API configuration migrating from legacy EF6 edmx / DataContext
        modelBuilder.Entity<Policy>(b =>
        {
            b.HasKey(p => p.PolicyId);
            b.Property(p => p.PolicyNumber).IsRequired().HasMaxLength(50);
            b.Property(p => p.PremiumAmount).HasPrecision(18, 2);
            b.Property(p => p.Status).HasMaxLength(20);
            b.HasIndex(p => p.PolicyNumber).IsUnique();
        });

        modelBuilder.Entity<Client>(b =>
        {
            b.HasKey(c => c.ClientId);
            b.Property(c => c.FullName).IsRequired().HasMaxLength(150);
            b.Property(c => c.Email).HasMaxLength(100);
        });

        modelBuilder.Entity<Claim>(b =>
        {
            b.HasKey(c => c.ClaimId);
            b.Property(c => c.Amount).HasPrecision(18, 2);
            b.HasOne<Policy>()
             .WithMany()
             .HasForeignKey(c => c.PolicyId)
             .OnDelete(DeleteBehavior.Restrict);
        });
    }
}
