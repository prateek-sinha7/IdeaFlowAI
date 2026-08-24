---
inclusion: always
---

# Backend Coding Guardrails — Python · Web · GenAI · Agentic AI

Mandatory design and coding rules for backend work (Python, FastAPI/web APIs,
GenAI, and agentic-AI runtimes). When a request conflicts with a rule here, flag
the conflict and propose a compliant alternative instead of silently breaking it.
These rules complement the security standards in `code-security` and the
project structure in `structure`/`tech`; they do not override them.

---

## 1. Low-Level Design (LLD)

Design at the class/module level before writing code. The goal is code that
"accommodates change, isolates risk, and exposes intent."

- **Model the domain, not the framework.** Business rules live in plain Python
  objects/services, independent of FastAPI, the ORM, or the LLM SDK. Frameworks
  are details at the edges.
- **Separate concerns into layers**: API/transport → service/business logic →
  data access → integrations. A change in one layer must not ripple into others.
- **Depend on abstractions (ports), not concretions.** Define an interface
  (`Protocol`/ABC) for anything that talks to the outside world (DB, LLM
  provider, message bus) and inject the implementation. This matches the
  project's Ports & Adapters rule — the kernel depends only on ports.
- **Composition over inheritance.** Prefer wiring small objects together over
  deep class hierarchies. Use inheritance only for genuine "is-a" relationships.
- **Make illegal states unrepresentable.** Use enums, typed dataclasses/Pydantic
  models, and narrow types instead of loose dicts and stringly-typed flags.
- **Keep functions small and single-purpose.** One reason to change, one level
  of abstraction per function, few parameters (group related args into a value
  object). Prefer pure functions where possible for testability.
- **Explicit dependencies.** No hidden globals or singletons for stateful
  collaborators — pass them in (constructor or FastAPI `Depends`).

## 2. SOLID Principles

- **S — Single Responsibility.** A class/module has one reason to change. If you
  describe it with "and", split it (e.g. don't mix HTTP parsing, business rules,
  and DB writes in one class).
- **O — Open/Closed.** Open for extension, closed for modification. Add new
  behavior by adding a new implementation/strategy + registration, not by editing
  a growing `if/elif` switch. (Mirrors the name-free-kernel invariant INV-1.)
- **L — Liskov Substitution.** Any implementation of an interface must be usable
  wherever that interface is expected, without surprising behavior, stricter
  preconditions, or weaker postconditions.
- **I — Interface Segregation.** Prefer several small, focused interfaces over
  one fat interface. Clients should not depend on methods they never call.
- **D — Dependency Inversion.** High-level policy depends on abstractions;
  low-level details depend on those same abstractions. Wire concretions at the
  composition root (app startup / factory), not deep inside business logic.

## 3. Core Design Principles (DRY · KISS · YAGNI + friends)

- **DRY** — every piece of knowledge has a single authoritative representation.
  De-duplicate *knowledge*, not coincidentally-similar lines. Two things that
  look alike but change for different reasons should stay separate.
- **KISS** — pick the straightforward approach. If a simple conditional solves
  it, don't reach for a Strategy pattern; if one clean class does the job, don't
  split it prematurely.
- **YAGNI** — don't build for speculative future requirements. Add abstraction
  when a second real use case arrives, not before.
- **Law of Demeter** — talk to immediate collaborators; avoid long
  `a.b.c.d` train-wreck chains that couple you to internal structure.
- **Fail fast, validate at the boundary** — reject bad input early with clear
  errors; keep the core assuming valid data.
- **Design patterns are tools, not goals** — use a pattern only when it removes
  real pain (duplication, rigidity, fragility). Naming a pattern is not a reason
  to introduce it.

## 4. Python-Specific Standards

- **Target Python 3.12+.** Use modern syntax: `match` where it clarifies,
  built-in generics (`list[str]`, `dict[str, int]`), `X | None` unions.
- **Type-hint everything** public: parameters, returns, attributes. Keep the
  import-resolution / type check green (`pyright`). No untyped `Any` leaking
  across module boundaries.
- **Prefer immutability**: `@dataclass(frozen=True)`, tuples, and Pydantic models
  over mutable shared state. Never use mutable default arguments.
- **EAFP + specific exceptions.** Catch narrow exception types, never bare
  `except:`. Define a small domain exception hierarchy; don't use exceptions for
  normal control flow.
- **Context managers** for every resource (files, sessions, locks, clients) so
  cleanup is guaranteed.
- **Structure by feature/domain**, not by technical type dumping-ground. Keep
  modules cohesive; avoid circular imports (respect the `lint-imports`
  boundaries — they must stay green).
- **f-strings** for formatting; **`logging`** (never `print`) for diagnostics.
- **Comprehensions/generators** for transforms, but stop when it hurts
  readability — a plain loop can be clearer.
- **Tooling is law**: `ruff check` (correctness) must pass; keep functions within
  reasonable complexity; run `vulture` to catch dead code. Pin dependencies to
  exact versions — no floating ranges.

## 5. Web / API (FastAPI) Standards

- **Layered structure**: routers (transport only) → services (business logic) →
  repositories/data access. Route handlers stay thin: validate, delegate, shape
  response.
- **Pydantic v2 everywhere** for request/response schemas and settings. Separate
  input models from ORM models; never expose ORM objects directly.
- **Dependency injection via `Depends`** for DB sessions, auth, and shared
  clients. No module-level mutable singletons for per-request state.
- **Async correctly.** Use `async def` for I/O-bound handlers and async DB
  sessions. Never call blocking I/O inside an async path — offload to a worker/
  thread. Don't mix sync and async DB sessions.
- **Explicit status codes and typed error responses.** Use `HTTPException` (or an
  exception handler) with generic, non-leaking messages. Never return stack
  traces, SQL errors, or internal paths to clients.
- **Validate all external input** (body, query, headers, uploads). Prefer
  allow-lists. Enforce auth on every non-public endpoint and authorization
  (ownership/role/scope) on every protected resource.
- **Parameterized queries / ORM binding only** — never string-concatenate SQL.
- **Pagination, timeouts, and limits** on list endpoints and outbound calls.
- **Versioned, documented APIs** — keep OpenAPI accurate; use consistent
  resource-oriented naming.
- **Migrations are additive** (Alembic); every new table carries `owner_id` +
  `workspace_id` per project persistence rules.

## 6. GenAI / LLM Standards

- **Treat every model output as untrusted.** Validate and constrain it before it
  drives an action, a query, or a downstream call. Never `eval`/exec model text.
- **Structured outputs**: request JSON/schema-constrained responses and validate
  with Pydantic; reject or repair on parse failure rather than trusting free text.
- **Guardrails on both sides**: validate inputs (prompt-injection, PII, policy)
  and outputs (schema, safety, groundedness) at runtime on every request — not
  just in tests.
- **Prompts are versioned artifacts**, not inline string literals scattered
  through code. Keep them in dedicated files/templates; parameterize inputs; keep
  user content clearly separated from system instructions.
- **Ground with retrieval (RAG) for factual tasks**; cite/return sources.
  Prefer grounding over relying on parametric memory for anything factual.
- **Provider abstraction.** Talk to LLMs through a port/factory so providers
  (Bedrock, Anthropic, etc.) are swappable and configured via settings/env — never
  hardcode model IDs, endpoints, or keys in business logic.
- **Determinism & cost control**: set explicit temperature/token limits, add
  timeouts, retries with backoff, and fallbacks. Cache where safe.
- **Never log prompts/completions containing secrets or PII** by value; redact.
- **Observability**: emit traces/metrics (latency, tokens, cost, failure rate)
  for every model call (OpenTelemetry).

## 7. Agentic AI Standards

- **Deterministic control, probabilistic reasoning.** An orchestration layer
  decides *which* step runs; the LLM reasons *within* a step. The model must not
  freely choose control flow. (Mirrors the project's ExecutionEngine rule — the
  LLM never chooses which agent runs next.)
- **Tools are typed, validated, and least-privilege.** Each tool has a strict
  input schema, validates arguments, and does the minimum necessary. Dangerous
  capabilities (`exec`, `network`, `secrets`, subprocess/`spawn_subagents`) stay
  **off by default** and are enabled only behind an explicit gate.
- **Human-in-the-loop gates** for irreversible or high-impact actions (writes,
  external side effects, spend). Require approval before the agent commits them.
- **Bound the loop.** Enforce max steps/iterations, wall-clock timeouts, and
  budget caps so an agent cannot spin forever or run away on cost.
- **Durable, resumable state.** Persist checkpoints so a run survives crashes/
  disconnects and can resume without redoing side effects (idempotency keys).
- **Isolate side effects** behind well-defined capabilities/ports; the reasoning
  loop should not touch DBs or networks directly.
- **Fail safe.** On error or low confidence, halt and hand control back rather
  than guessing; make every external action retry-safe.
- **Evaluate + observe.** Trace each agent decision and tool call; keep eval
  loops/regression checks so behavior changes are caught before release.

## 8. Testing & Verification

- **Test behavior, not implementation.** Unit-test business logic in isolation
  with dependencies stubbed via their ports/interfaces.
- **Use `pytest` + `pytest-asyncio`**; add property-based tests (`hypothesis`)
  for pure logic and parsers. Use `httpx` for API tests.
- **Deterministic tests for non-deterministic systems**: mock LLM/provider calls;
  assert on structure, schema, and guardrail behavior — not exact model prose.
- **Preserve characterization goldens** (INV-3): don't regenerate deterministic
  golden outputs unless the change is intentionally output-changing — and say so.
- After any change, run the relevant suite, `ruff check`, `pyright`, and
  `lint-imports` (must stay green) before declaring done.

## 9. Naming, Documentation & Readability

- **Names carry meaning.** Functions are verbs (`load_workflow`, `resolve_dag`);
  variables/attributes are nouns (`workflow`, `resized_image`). Booleans read as
  predicates (`is_ready`, `has_gate`). Avoid abbreviations and single letters
  except tight loop counters/math.
- **Follow PEP 8 naming**: `snake_case` for functions/variables/modules,
  `PascalCase` for classes, `UPPER_SNAKE_CASE` for constants, leading `_` for
  internal/private. Consistency over personal preference — the linter is the
  arbiter.
- **Docstrings on every public module, class, and function** (what it does,
  args, returns, raises). Keep them accurate; a wrong docstring is worse than
  none. Reserve inline comments for *why*, not *what* — the code says what.
- **Explicit over clever.** Prefer readable code to terse tricks. Avoid deep
  nesting: use guard clauses / early returns to keep the happy path flat.
- **Keep the public surface small.** Export intentionally (`__all__` where it
  helps); don't leak internals across module boundaries.

## 10. Concurrency, Performance & Data Access

- **Know your bound.** Use `async` for I/O-bound work; offload CPU-bound work to
  a process pool / worker, never block the event loop. Don't add threads/async
  where a simple synchronous path suffices.
- **Kill N+1 queries.** Use eager loading / joins and batch fetches; profile
  before optimizing. Add DB indexes for real query patterns, not guesses.
- **Pool and reuse connections/clients** (DB, HTTP, LLM). Set explicit timeouts
  on every outbound call; add retries with exponential backoff + jitter only for
  idempotent operations.
- **Cache deliberately** with clear invalidation and TTLs; never cache
  per-user/sensitive data in a shared scope. A wrong cache is a correctness bug.
- **Stream large payloads**; paginate large result sets; bound in-memory
  accumulation. Use background tasks/queues for slow work instead of blocking
  the request.
- **Measure, then optimize.** Profile the proven bottleneck; don't
  micro-optimize on intuition.

## 11. Configuration, Secrets & Observability

- **Config through settings/env** (`pydantic-settings`), validated at startup —
  fail fast on missing/invalid config. Never scatter `os.getenv` calls through
  business logic. No environment-specific values baked into code.
- **Secrets never in code, logs, or fixtures.** Load from env or a secrets
  manager; reference by key name, never by value. Keep `.env` out of git;
  provide `.env.example` with placeholders.
- **Structured logging** (JSON where possible) with levels and a correlation/
  request ID threaded through a run. Never log secrets, tokens, or PII by value.
- **Metrics & traces** for every meaningful operation (latency, error rate,
  throughput; for LLM: tokens/cost) via OpenTelemetry. Health/readiness
  endpoints reflect real dependency state.
- **Errors are actionable.** Log enough server-side context to debug; return
  generic, non-leaking messages to clients.

## 12. Retrieval / RAG Standards

- **Treat every retrieved chunk as untrusted input**, exactly like user input.
  A poisoned or adversarial document in the store can carry hidden instructions
  that hijack the model when retrieved — defend in layers, don't trust the
  retriever.
- **Enforce authorization inside the query.** Apply per-user/workspace document
  permissions as a metadata filter within the vector search, so a user can only
  retrieve chunks they may see — never as post-generation filtering.
- **Vet the ingestion pipeline.** Validate and sanitize documents before
  embedding; watch for near-duplicate/anomalous embeddings that signal poisoning.
  Secure the vector store itself (auth on, encryption, network-restricted).
- **Chunking is a first-class decision**, not a default. Tune chunk size/overlap
  and splitting strategy to the content; it affects retrieval quality as much as
  the embedding model. Record the config so results are reproducible.
- **Ground and cite.** Return sources with answers; prefer retrieved context over
  parametric memory for factual claims, and handle "no relevant context" cleanly
  instead of hallucinating.

## 13. Dependencies, Git & Review Discipline

- **Pin exact versions** (no floating ranges); prefer well-maintained packages;
  watch for typosquatting. Keep dependencies patched; flag known-vulnerable ones.
- **Small, focused commits** with clear messages. Stage specific files; never
  commit secrets or state. Branch off, don't push to main directly.
- **PRs stay reviewable**: one concern per PR, description of what/why/how-tested.
  Keep the diff minimal — no unrelated "cleanup" riding along a fix.
- **Green before merge**: `ruff check`, `pyright`, `lint-imports`, relevant tests,
  and security scans (Checkov/Trivy/Gitleaks where applicable) must pass.

---

## References

Content below was researched from public sources and rephrased for compliance
with licensing restrictions.

- [Real Python — SOLID principles in Python](https://realpython.com/solid-principles-python/)
- [SOLID, DRY, KISS, YAGNI + GRASP overview](https://harpsichord-lute-eaks.squarespace.com/de-blog/engineering-with-solid-dry-kiss-yagni-and-grasp)
- [Hello Interview — LLD design principles](https://www.hellointerview.com/learn/low-level-design/in-a-hurry/design-principles)
- [DRY, KISS, YAGNI — essential design principles](https://softwarepatternslexicon.com/mastering-design-patterns/principles-of-software-design/dry-kiss-and-yagni/)
- [FastAPI best practices (zhanymkanov)](https://github.com/zhanymkanov/fastapi-best-practices)
- [OpenAI — how to implement LLM guardrails](https://developers.openai.com/cookbook/examples/how_to_use_guardrails/)
- [OpenAI — a practical guide to building agents](https://openai.com/business/guides-and-resources/a-practical-guide-to-building-ai-agents/)
- [Building production-grade AI guardrails](https://www.freecodecamp.org/news/how-to-build-production-grade-ai-guardrails-for-enterprise-applications-a-practical-guide/)
- [Agentic AI in production — guardrails & eval loops](https://gothartech.hashnode.dev/agentic-ai-in-production-guardrails-eval-loops-and-the-architecture-of-trust)
- [PEP 8 — style guide for Python code](https://pep8.org/)
- [Real Python — Python code quality best practices](https://realpython.com/python-code-quality/)
- [Securing RAG — prompt injection & access control](https://theroadtoenterprise.com/blog/securing-rag-prompt-injection-access-control)
- [RAG security — attacks, defenses & architecture](https://aminrj.com/posts/rag-security-architecture/)
- [Chunking strategy and RAG quality](https://tianpan.co/blog/2026-04-20-chunking-strategy-rag-quality)