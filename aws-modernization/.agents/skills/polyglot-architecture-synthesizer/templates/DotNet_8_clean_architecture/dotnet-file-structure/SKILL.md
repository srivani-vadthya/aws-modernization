---
name: dotnet-file-structure
description: "Canonical .NET 8 Web API folder structure: Controllers, Models, DTOs, Data/Repository (Interfaces+Implementations), Services (Interfaces+Implementations), Program.cs"
tags: ["structure", "folder", "namespace", "csproj", "project", "architecture", "clean"]
trigger: always
---

# .NET File & Folder Structure — Golden Pattern

## Canonical Layout

```
{ProjectName}/
├── Controllers/                      ← API endpoints only — no business logic
├── Models/                           ← Domain entities (EF Core mapped)
├── DTOs/                             ← Request/Response classes per entity
├── Data/
│   ├── {ProjectName}DbContext.cs     ← EF Core DbContext with OnModelCreating
│   └── Repository/
│       ├── Interfaces/               ← I{Entity}Repository.cs
│       └── Implementations/          ← {Entity}Repository.cs
├── Services/
│   ├── Interfaces/                   ← I{Entity}Service.cs
│   └── Implementations/              ← {Entity}Service.cs
├── Program.cs                        ← DI registration + middleware pipeline
├── appsettings.json
└── {ProjectName}.csproj
```

## Namespace Convention

```
{ProjectName}.Controllers
{ProjectName}.Models
{ProjectName}.DTOs
{ProjectName}.Data
{ProjectName}.Data.Repository.Interfaces
{ProjectName}.Data.Repository.Implementations
{ProjectName}.Services.Interfaces
{ProjectName}.Services.Implementations
```

## .csproj — Golden Pattern

```xml
<!-- filepath: {ProjectName}/{ProjectName}.csproj -->
<Project Sdk="Microsoft.NET.Sdk.Web">
  <PropertyGroup>
    <TargetFramework>net8.0</TargetFramework>
    <Nullable>enable</Nullable>
    <ImplicitUsings>enable</ImplicitUsings>
  </PropertyGroup>
  <ItemGroup>
    <PackageReference Include="Microsoft.EntityFrameworkCore" Version="8.0.0" />
    <PackageReference Include="Microsoft.EntityFrameworkCore.SqlServer" Version="8.0.0" />
    <PackageReference Include="Microsoft.EntityFrameworkCore.Tools" Version="8.0.0">
      <PrivateAssets>all</PrivateAssets>
      <IncludeAssets>runtime; build; native; contentfiles; analyzers; buildtransitive</IncludeAssets>
    </PackageReference>
    <PackageReference Include="Swashbuckle.AspNetCore" Version="6.5.0" />
  </ItemGroup>
</Project>
```

## Program.cs — Golden Pattern

```csharp
// filepath: {ProjectName}/Program.cs
using {ProjectName}.Data;
using {ProjectName}.Data.Repository.Implementations;
using {ProjectName}.Data.Repository.Interfaces;
using {ProjectName}.Services.Implementations;
using {ProjectName}.Services.Interfaces;
using Microsoft.EntityFrameworkCore;

var builder = WebApplication.CreateBuilder(args);

builder.Services.AddControllers();
builder.Services.AddEndpointsApiExplorer();
builder.Services.AddSwaggerGen();

builder.Services.AddDbContext<{ProjectName}DbContext>(options =>
    options.UseSqlServer(builder.Configuration.GetConnectionString("DefaultConnection")));

// Register repositories (Scoped lifetime)
builder.Services.AddScoped<I{Entity}Repository, {Entity}Repository>();

// Register services (Scoped lifetime)
builder.Services.AddScoped<I{Entity}Service, {Entity}Service>();

var app = builder.Build();

if (app.Environment.IsDevelopment())
{
    app.UseSwagger();
    app.UseSwaggerUI();
}

app.UseHttpsRedirection();
app.UseAuthorization();
app.MapControllers();

app.Run();
```

## Rules
1. **Every** new repository and service MUST be registered in `Program.cs` with `AddScoped`
2. `Nullable` and `ImplicitUsings` MUST be `enable` — no nullable warnings allowed
3. Target framework is **net8.0** — never net6.0, net7.0, or net10.0
4. Swagger always registered — never remove it
5. `DeleteBehavior.Restrict` on all foreign keys — never `Cascade`
