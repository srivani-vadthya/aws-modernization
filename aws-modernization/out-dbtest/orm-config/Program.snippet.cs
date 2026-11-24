// Program.cs — register Npgsql EF Core
// Add NuGet: Npgsql.EntityFrameworkCore.PostgreSQL

builder.Services.AddDbContext<ModernDbContext>(options =>
    options.UseNpgsql(builder.Configuration.GetConnectionString("DefaultConnection")));
