# .NET / C# Rules

## Project Setup

- Target .NET 8 as the minimum baseline; use SDK-style `.csproj` files with `PackageReference` entries.
- Use the minimal-hosting model in `Program.cs`; wire DI, middleware order, and authentication in a single file.
- Prefer `System.Text.Json` over Newtonsoft.Json unless polymorphic deserialisation is required.
- Replace `HttpWebRequest` / `WebClient` with `HttpClient` via `IHttpClientFactory`.

## C# Conventions

- Use primary constructors for services and controllers where the constructor body is empty.
- Use `async`/`await` end-to-end; never block on async code with `.Result` or `.Wait()`.
- Use `Result<T>` or `OneOf<TSuccess, TError>` for business-validation failures instead of exceptions.
- Use `record` types for immutable DTOs and value objects.
- Replace `ConfigurationManager` with `IConfiguration`; replace `HostingEnvironment.MapPath` with `IWebHostEnvironment.ContentRootPath`.

## ASP.NET Core

- Keep controllers thin; delegate all business logic to injected services.
- Use `IHttpContextAccessor` instead of `HttpContext.Current`.
- Register middleware in the correct order: exception handling, HTTPS redirection, authentication, authorisation, routing, endpoints.
- Use `[ApiController]` and `[Route]` attributes; return `IActionResult` or `ActionResult<T>`.
- Handle validation errors via `ModelState` and the built-in `ValidationProblemDetails` response shape.

## Entity Framework Core

- Use EF Core migrations for schema management; never apply schema changes manually in production.
- Configure entities via `IEntityTypeConfiguration<T>` classes; avoid data annotations on domain models.
- Use `AsNoTracking()` for read-only queries; only track entities that will be modified.
- Tag every query with a comment using `TagWith()` to aid slow-query diagnosis.

## Azure Integration

- Use managed identities for all Azure service authentication; never store connection strings with keys in source code.
- Store secrets in Azure Key Vault; reference them via Key Vault references in App Service configuration.
- Use `Azure.AI.OpenAI`, `Azure.Search.Documents`, or `Microsoft.SemanticKernel` for AI integrations.
- Register Azure SDK clients as singletons via the `AddAzureClients` extension; configure retry and timeout policies centrally.
- Emit token usage, latency, and quality signals to Application Insights for all AI service calls.

## Testing

- Use xUnit with FluentAssertions and NSubstitute for unit tests.
- Use `WebApplicationFactory<TProgram>` for integration tests against the real ASP.NET Core pipeline.
- Use Bogus or AutoFixture for realistic, PII-free test data.
