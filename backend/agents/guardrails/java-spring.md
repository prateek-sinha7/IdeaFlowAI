# Java Spring Boot Rules

## Project Setup

- Use Spring Boot 3.2+ with Java 21 as the minimum baseline.
- Declare dependencies in `pom.xml` with explicit versions; use the Spring Boot BOM for managed dependencies.
- Include Spring Web, Spring Data JPA, Micrometer + OpenTelemetry, and springdoc-openapi as standard dependencies.
- Use Testcontainers for integration tests against real databases and message brokers.

## Dependency Injection

- Use constructor injection exclusively; never use field injection (`@Autowired` on fields).
- Declare beans in `@Configuration` classes; avoid component-scan abuse.
- Use Java 21 records for immutable DTOs and value objects.

## REST Controllers

- Annotate controllers with `@RestController`; keep them thin — delegate all logic to the service layer.
- Use `@RequestMapping` at class level for the base path; use method-level `@GetMapping`, `@PostMapping`, etc.
- Annotate every endpoint with OpenAPI annotations (`@Operation`, `@ApiResponse`, `@Parameter`).
- Return `ResponseEntity<T>` when the status code or headers vary; use direct return types for fixed-status endpoints.
- Handle validation errors via `@RestControllerAdvice` and `MethodArgumentNotValidException`.

## Service and Repository Layers

- Define service interfaces; provide a single `@Service` implementation per interface.
- Use Spring Data JPA repositories; avoid raw `EntityManager` unless the query cannot be expressed otherwise.
- Annotate service methods with `@Transactional`; set `readOnly = true` on read-only methods.
- Use `Optional<T>` for single-entity lookups that may return nothing.

## Error Handling and Logging

- Use a global `@RestControllerAdvice` to map exceptions to consistent error envelopes.
- Log with SLF4J; add MDC context (request ID, user ID) at the filter layer.
- Emit OpenTelemetry spans for every service-layer operation; include relevant attributes.

## Configuration

- Externalise all environment-specific values in `application.yml`; use Spring Cloud AWS or Secrets Manager references for secrets.
- Never hardcode credentials, URLs, or feature flags in source code.
- Use `@ConfigurationProperties` for typed, validated configuration blocks.
