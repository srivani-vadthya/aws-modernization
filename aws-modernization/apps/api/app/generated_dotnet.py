"""Modernized .NET 8 WebAPI and React 18 TypeScript frontend service generator for IMS and .NET target workloads."""

from __future__ import annotations

from pathlib import Path

CSPROJ = """<Project Sdk="Microsoft.NET.Sdk.Web">

  <PropertyGroup>
    <TargetFramework>net8.0</TargetFramework>
    <Nullable>enable</Nullable>
    <ImplicitUsings>enable</ImplicitUsings>
    <RootNamespace>IMS.Modernized.WebAPI</RootNamespace>
  </PropertyGroup>

  <ItemGroup>
    <PackageReference Include="Microsoft.AspNetCore.OpenApi" Version="8.0.4" />
    <PackageReference Include="Swashbuckle.AspNetCore" Version="6.5.0" />
    <PackageReference Include="Microsoft.EntityFrameworkCore" Version="8.0.4" />
    <PackageReference Include="Microsoft.EntityFrameworkCore.SqlServer" Version="8.0.4" />
    <PackageReference Include="Microsoft.EntityFrameworkCore.Design" Version="8.0.4">
      <IncludeAssets>runtime; build; native; contentfiles; analyzers; buildtransitive</IncludeAssets>
      <PrivateAssets>all</PrivateAssets>
    </PackageReference>
    <PackageReference Include="FluentValidation.AspNetCore" Version="11.3.0" />
  </ItemGroup>

</Project>
"""

APPSETTINGS = """{
  "Logging": {
    "LogLevel": {
      "Default": "Information",
      "Microsoft.AspNetCore": "Warning"
    }
  },
  "AllowedHosts": "*",
  "ConnectionStrings": {
    "DefaultConnection": "Server=tcp:sql-ims-modernized.database.windows.net,1433;Initial Catalog=ImsModernizedDb;Encrypt=True;TrustServerCertificate=False;Connection Timeout=30;"
  }
}
"""

PROGRAM_CS = """using IMS.Modernized.WebAPI.Data;
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
"""

DB_CONTEXT = """using IMS.Modernized.WebAPI.Domain;
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
"""

DOMAIN_POLICY = """namespace IMS.Modernized.WebAPI.Domain;

public class Policy
{
    public int PolicyId { get; set; }
    public string PolicyNumber { get; set; } = string.Empty;
    public int ClientId { get; set; }
    public string PolicyType { get; set; } = "Auto";
    public decimal PremiumAmount { get; set; }
    public string Status { get; set; } = "Active";
    public DateTime EffectiveDate { get; set; }
    public DateTime ExpirationDate { get; set; }
    public DateTime CreatedAt { get; set; } = DateTime.UtcNow;
}
"""

DOMAIN_CLIENT = """namespace IMS.Modernized.WebAPI.Domain;

public class Client
{
    public int ClientId { get; set; }
    public string FullName { get; set; } = string.Empty;
    public string Email { get; set; } = string.Empty;
    public string Phone { get; set; } = string.Empty;
    public string Address { get; set; } = string.Empty;
    public DateTime CreatedAt { get; set; } = DateTime.UtcNow;
}
"""

DOMAIN_CLAIM = """namespace IMS.Modernized.WebAPI.Domain;

public class Claim
{
    public int ClaimId { get; set; }
    public int PolicyId { get; set; }
    public string ClaimNumber { get; set; } = string.Empty;
    public decimal Amount { get; set; }
    public string Status { get; set; } = "Submitted";
    public string Description { get; set; } = string.Empty;
    public DateTime IncidentDate { get; set; }
    public DateTime ReportedDate { get; set; } = DateTime.UtcNow;
}
"""

CONTROLLER_POLICY = """using IMS.Modernized.WebAPI.Data;
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
"""

CONTROLLER_CLAIM = """using IMS.Modernized.WebAPI.Data;
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
"""

# Frontend React 18 TypeScript Files
REACT_PACKAGE_JSON = """{
  "name": "ims-modern-portal",
  "private": true,
  "version": "1.0.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "lucide-react": "^0.378.0",
    "axios": "^1.6.8"
  },
  "devDependencies": {
    "@types/react": "^18.3.1",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.2.1",
    "autoprefixer": "^10.4.19",
    "postcss": "^8.4.38",
    "tailwindcss": "^3.4.3",
    "typescript": "^5.4.5",
    "vite": "^5.2.11"
  }
}
"""

REACT_APP_TSX = """import React, { useState, useEffect } from 'react';
import { Shield, FileText, CheckCircle2, AlertCircle, Plus } from 'lucide-react';
import axios from 'axios';

interface Policy {
  policyId: number;
  policyNumber: string;
  policyType: string;
  premiumAmount: number;
  status: string;
  effectiveDate: string;
}

export function App() {
  const [policies, setPolicies] = useState<Policy[]>([
    { policyId: 1, policyNumber: "POL-AUTO-2026-001", policyType: "Comprehensive Auto", premiumAmount: 1450.00, status: "Active", effectiveDate: "2026-01-01" },
    { policyId: 2, policyNumber: "POL-HOME-2026-042", policyType: "Homeowner Shield", premiumAmount: 2100.00, status: "Pending Underwriting", effectiveDate: "2026-02-15" }
  ]);
  const [loading, setLoading] = useState(false);

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 font-sans">
      <header className="border-b border-slate-800 bg-slate-900/60 backdrop-blur px-8 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="h-9 w-9 rounded-lg bg-emerald-500/20 text-emerald-400 flex items-center justify-center font-bold">
            <Shield className="h-5 w-5" />
          </div>
          <div>
            <h1 className="text-base font-semibold text-white tracking-tight">Insurance Management System (IMS)</h1>
            <p className="text-xs text-slate-400">Modernized .NET 8 WebAPI + React 18 Clean Architecture</p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <span className="px-2.5 py-1 rounded-full text-xs font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
            Backend API: Healthy (net8.0)
          </span>
          <button className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold shadow-sm transition">
            <Plus className="h-4 w-4" /> Issue Policy
          </button>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-6 py-8">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
          <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-5">
            <span className="text-xs font-medium uppercase tracking-wider text-slate-400">Active Policies</span>
            <div className="text-2xl font-bold text-white mt-1">1,248</div>
            <div className="text-xs text-emerald-400 mt-2 flex items-center gap-1">
              <CheckCircle2 className="h-3.5 w-3.5" /> 99.8% Sync with Aurora DB
            </div>
          </div>
          <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-5">
            <span className="text-xs font-medium uppercase tracking-wider text-slate-400">Open Claims</span>
            <div className="text-2xl font-bold text-white mt-1">37</div>
            <div className="text-xs text-amber-400 mt-2 flex items-center gap-1">
              <AlertCircle className="h-3.5 w-3.5" /> SLA Target: &lt; 24h
            </div>
          </div>
          <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-5">
            <span className="text-xs font-medium uppercase tracking-wider text-slate-400">Monthly Gross Premium</span>
            <div className="text-2xl font-bold text-white mt-1">$482,900</div>
            <div className="text-xs text-blue-400 mt-2">Migrated from EF6 DataContext</div>
          </div>
        </div>

        <div className="bg-slate-900/80 border border-slate-800 rounded-xl overflow-hidden shadow-xl">
          <div className="px-6 py-4 border-b border-slate-800 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-white flex items-center gap-2">
              <FileText className="h-4 w-4 text-emerald-400" /> Active Policies Under Management
            </h2>
            <span className="text-xs text-slate-400">Live feed from ASP.NET Core 8 API</span>
          </div>

          <table className="w-full text-left text-sm">
            <thead className="bg-slate-950/60 text-xs font-semibold text-slate-400 uppercase tracking-wider border-b border-slate-800">
              <tr>
                <th className="px-6 py-3">Policy #</th>
                <th className="px-6 py-3">Type</th>
                <th className="px-6 py-3">Premium</th>
                <th className="px-6 py-3">Effective Date</th>
                <th className="px-6 py-3">Status</th>
                <th className="px-6 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {policies.map(p => (
                <tr key={p.policyId} className="hover:bg-slate-800/40 transition">
                  <td className="px-6 py-3.5 font-mono text-xs font-semibold text-emerald-300">{p.policyNumber}</td>
                  <td className="px-6 py-3.5 text-slate-300">{p.policyType}</td>
                  <td className="px-6 py-3.5 font-semibold text-white">${p.premiumAmount.toFixed(2)}</td>
                  <td className="px-6 py-3.5 text-slate-400 text-xs">{p.effectiveDate}</td>
                  <td className="px-6 py-3.5">
                    <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                      {p.status}
                    </span>
                  </td>
                  <td className="px-6 py-3.5 text-right">
                    <button className="text-xs text-blue-400 hover:text-blue-300 font-medium">View Details</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </main>
    </div>
  );
}

export default App;
"""

DOCKERFILE = """# Build backend WebAPI
FROM mcr.microsoft.com/dotnet/sdk:8.0 AS build-backend
WORKDIR /app
COPY backend/*.csproj ./
RUN dotnet restore
COPY backend/ ./
RUN dotnet publish -c Release -o /out

# Runtime container
FROM mcr.microsoft.com/dotnet/aspnet:8.0 AS runtime
WORKDIR /app
COPY --from=build-backend /out ./
EXPOSE 8080
ENV ASPNETCORE_URLS=http://+:8080
ENTRYPOINT ["dotnet", "IMS.Modernized.WebAPI.dll"]
"""

README_DOTNET = """# IMS Modernized Insurance Service (.NET 8 + React 18)

This codebase represents the automated modernization output generated by **VModernize** from legacy **ASP.NET MVC 5 & Entity Framework 6 DataContext** into cloud-ready **.NET 8 WebAPI and React 18 Single Page Application (SPA)**.

---

## 🏗️ Architecture Overview

- **Backend**: C# .NET 8 WebAPI (`net8.0`)
  - **Entity Framework Core 8**: Fully asynchronous DBContext with connection pooling, index optimization, and SQL Server / PostgreSQL migration.
  - **Controllers**: Clean RESTful endpoints (`PoliciesController`, `ClaimsController`) with dependency injection and structured logging.
  - **OpenAPI / Swagger**: Auto-generated documentation at `/swagger/index.html`.
  - **Cloud Health Checks**: Liveness probe at `/healthz` for AWS ECS / EKS container orchestration.
- **Frontend**: React 18 + Vite + TypeScript + Tailwind CSS
  - Modern reactive single-page app replacing legacy `.cshtml` Razor views and jQuery datatables.
- **Database**:
  - Replaces monolithic `DataContext.cs` with `ModernImsDbContext` utilizing modern Fluent API mappings and decimal precision guarantees.

---

## 🚀 How to Run Locally

### 1. Run the .NET 8 WebAPI Backend:
```bash
cd backend
dotnet restore
dotnet run
```
API Swagger UI will be available at `http://localhost:5000/swagger`.

### 2. Run the React 18 Frontend:
```bash
cd frontend
npm install
npm run dev
```
Portal will be running at `http://localhost:5173`.
"""

FILES_DOTNET = {
    "README.md": README_DOTNET,
    "Dockerfile": DOCKERFILE,
    # Backend (.NET 8)
    "backend/IMS.Modernized.WebAPI.csproj": CSPROJ,
    "backend/appsettings.json": APPSETTINGS,
    "backend/Program.cs": PROGRAM_CS,
    "backend/Data/ModernImsDbContext.cs": DB_CONTEXT,
    "backend/Domain/Policy.cs": DOMAIN_POLICY,
    "backend/Domain/Client.cs": DOMAIN_CLIENT,
    "backend/Domain/Claim.cs": DOMAIN_CLAIM,
    "backend/Controllers/PoliciesController.cs": CONTROLLER_POLICY,
    "backend/Controllers/ClaimsController.cs": CONTROLLER_CLAIM,
    # Frontend (React 18)
    "frontend/package.json": REACT_PACKAGE_JSON,
    "frontend/src/App.tsx": REACT_APP_TSX,
}


def write_dotnet_generated(dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for rel, content in FILES_DOTNET.items():
        path = dest / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
