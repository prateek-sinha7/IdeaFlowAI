# OpenAPI / REST API Design Rules

## RESTful Conventions

- Use nouns for resource paths, not verbs: `/orders/{id}` not `/getOrder`.
- Use plural resource names: `/users`, `/products`, `/orders`.
- Nest sub-resources at most one level deep: `/users/{id}/orders`.
- HTTP methods map to operations: GET (read), POST (create), PUT (replace), PATCH (partial update), DELETE (remove).
- Never tunnel actions through query parameters; use sub-resources or action endpoints sparingly (`/orders/{id}/cancel`).

## Versioning

- Version via URI prefix: `/v1/`, `/v2/`. Do not use headers or query params as the primary versioning mechanism.
- Maintain at least one prior major version during a deprecation window.
- Communicate deprecation via a `Deprecation` response header and document the sunset date.

## Status Codes

- 200 OK for successful reads and updates that return a body.
- 201 Created for successful resource creation; include a `Location` header pointing to the new resource.
- 204 No Content for successful deletes or updates with no response body.
- 400 Bad Request for client validation failures; include field-level error details.
- 401 Unauthorized when authentication is missing or invalid.
- 403 Forbidden when the caller is authenticated but lacks permission.
- 404 Not Found when the resource does not exist.
- 409 Conflict for duplicate-creation or optimistic-lock violations.
- 422 Unprocessable Entity for semantic validation failures.
- 429 Too Many Requests with a `Retry-After` header.
- 500 Internal Server Error for unexpected server faults; never leak stack traces.

## Request and Response Schemas

- Use a consistent error envelope: `{ "error": { "code": "...", "message": "...", "details": [...] } }`.
- Use `camelCase` for JSON field names.
- Use ISO 8601 for all date and datetime fields.
- Paginate list endpoints with `limit`, `offset` (or cursor-based `after`), and a `total` count in the response.
- Include an `idempotency-key` header contract for all mutating endpoints.

## OpenAPI Document

- Produce an OpenAPI 3.1 document covering every endpoint.
- Define shared types in `components/schemas`; do not inline complex objects.
- Include at least one realistic `example` per endpoint request and response.
- Annotate every field with `description`, `format`, and nullability.
- Declare `securitySchemes` and apply them at the operation level.
