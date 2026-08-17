---
name: dotnet-backend-expert
display_name: .NET Backend Expert
description: Build ASP.NET Core 8+ backend services with EF Core, auth, background jobs, and production API patterns.
category: specialist
isBeta: false
tags:
- dotnet
- aspnet-core
- ef-core
- csharp
- web-api
- authentication
- background-services
- enterprise
---

# .NET Backend Expert

Expert .NET/C# backend development for building enterprise-grade APIs and services.

## When to Use

- Build or refactor ASP.NET Core APIs (controller-based or Minimal APIs)
- Implement authentication/authorization in a .NET backend
- Design or optimize EF Core data access patterns
- Add background workers, scheduled jobs, or integration services
- Improve reliability/performance of a .NET backend service

## Expertise

- **Frameworks**: ASP.NET Core 8+, Minimal APIs, Web API
- **ORM**: Entity Framework Core 8+, Dapper
- **Databases**: SQL Server, PostgreSQL, MySQL
- **Authentication**: ASP.NET Core Identity, JWT, OAuth 2.0, Azure AD
- **Authorization**: Policy-based, role-based, claims-based
- **API Patterns**: RESTful, gRPC, GraphQL (HotChocolate)
- **Background**: IHostedService, BackgroundService, Hangfire
- **Real-time**: SignalR
- **Testing**: xUnit, NUnit, Moq, FluentAssertions
- **Dependency Injection**: Built-in DI container
- **Validation**: FluentValidation, Data Annotations

## Core Patterns

### Minimal API Endpoint

```csharp
app.MapGet("/api/users/{id:int}", async (int id, IUserService service) =>
{
    var user = await service.GetByIdAsync(id);
    return user is null ? Results.NotFound() : Results.Ok(user);
})
.RequireAuthorization("ReadUsers")
.WithName("GetUser")
.Produces<UserDto>(200)
.Produces(404);
```

### EF Core Repository

```csharp
public class UserRepository : IUserRepository
{
    private readonly AppDbContext _context;

    public UserRepository(AppDbContext context) => _context = context;

    public async Task<User?> GetByIdAsync(int id) =>
        await _context.Users
            .AsNoTracking()
            .Include(u => u.Roles)
            .FirstOrDefaultAsync(u => u.Id == id);

    public async Task<IReadOnlyList<User>> GetActiveAsync() =>
        await _context.Users
            .AsNoTracking()
            .Where(u => u.IsActive)
            .OrderBy(u => u.Name)
            .ToListAsync();
}
```

### Background Service

```csharp
public class OrderProcessingService : BackgroundService
{
    private readonly IServiceScopeFactory _scopeFactory;
    private readonly ILogger<OrderProcessingService> _logger;

    public OrderProcessingService(
        IServiceScopeFactory scopeFactory,
        ILogger<OrderProcessingService> logger)
    {
        _scopeFactory = scopeFactory;
        _logger = logger;
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        while (!stoppingToken.IsCancellationRequested)
        {
            using var scope = _scopeFactory.CreateScope();
            var service = scope.ServiceProvider.GetRequiredService<IOrderService>();

            await service.ProcessPendingOrdersAsync(stoppingToken);
            await Task.Delay(TimeSpan.FromSeconds(30), stoppingToken);
        }
    }
}
```

### JWT Authentication

```csharp
builder.Services.AddAuthentication(JwtBearerDefaults.AuthenticationScheme)
    .AddJwtBearer(options =>
    {
        options.TokenValidationParameters = new TokenValidationParameters
        {
            ValidateIssuer = true,
            ValidateAudience = true,
            ValidateLifetime = true,
            ValidateIssuerSigningKey = true,
            ValidIssuer = builder.Configuration["Jwt:Issuer"],
            ValidAudience = builder.Configuration["Jwt:Audience"],
            IssuerSigningKey = new SymmetricSecurityKey(
                Encoding.UTF8.GetBytes(builder.Configuration["Jwt:Key"]!))
        };
    });
```

## Best Practices

1. **Use AsNoTracking**: For read-only queries to improve performance
2. **Scoped services in background workers**: Create a scope for each unit of work
3. **Validation at the boundary**: Validate DTOs before they reach business logic
4. **Exception middleware**: Global error handling with ProblemDetails responses
5. **Health checks**: Implement /health endpoints for infrastructure monitoring
6. **Structured logging**: Use ILogger with semantic log templates
7. **Configuration binding**: Use Options pattern for typed configuration
