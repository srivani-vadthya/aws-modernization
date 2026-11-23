using IMS.Modernized.WebAPI.Data;
using Microsoft.EntityFrameworkCore;

var builder = WebApplication.CreateBuilder(args);

// Add services to the container.
builder.Services.AddControllers();
builder.Services.AddEndpointsApiExplorer();
builder.Services.AddSwaggerGen(c =>
{
    c.SwaggerDoc("v1", new() { Title = "IMS Modernized Insurance API", Version = "v1", Description = "Modernized from Legacy ASP.NET MVC to .NET 8 Microservice Architecture" });
});

// Configure Entity Framework Core with modern connection pooling
var connectionString = builder.Configuration.GetConnectionString("DefaultConnection") 
    ?? "Data Source=ims_modern.db";
builder.Services.AddDbContext<ModernImsDbContext>(options =>
    options.UseSqlServer(connectionString));

// Modern CORS policy for React 18 SPA
builder.Services.AddCors(options =>
{
    options.AddPolicy("AllowReactApp", policy =>
    {
        policy.WithOrigins("http://localhost:5173", "http://localhost:3000")
              .AllowAnyHeader()
              .AllowAnyMethod();
    });
});

var app = builder.Build();

// Configure the HTTP request pipeline.
if (app.Environment.IsDevelopment())
{
    app.UseSwagger();
    app.UseSwaggerUI(c => c.SwaggerEndpoint("/swagger/v1/swagger.json", "IMS Modernized API v1"));
}

app.UseHttpsRedirection();
app.UseCors("AllowReactApp");
app.UseAuthorization();
app.MapControllers();

// Health check endpoint for container orchestrator (ECS / Kubernetes)
app.MapGet("/healthz", () => Results.Ok(new { status = "Healthy", timestamp = DateTime.UtcNow }));

app.Run();
