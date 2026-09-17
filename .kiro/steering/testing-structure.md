---
inclusion: always
---

# Test Structure Standard

This workspace follows a fixed test layout. Every test you create, move, or reference MUST
conform to it. Detailed conventions load automatically when you touch `tests/**`
(see `testing-conventions`). For structural work (scaffold, audit, migrate, fixtures, config)
use the `/test-architecture-agent` steering.

## Canonical layout (mirror the REAL package name and subpackages, not the example)

```
tests/
├── conftest.py            # root: zero-I/O fixtures + folder->marker hook
├── factories/             # data builders (<Model>Factory) — not tests
├── fakes/                 # Fake<Thing> in-memory fakes, LLM fakes — not tests
├── fixtures/              # STATIC DATA files only (json/txt) — not pytest fixtures
├── unit/                  # ms, zero real I/O, mirrors <pkg>/ exactly
├── integration/           # real Postgres (testcontainers); LLM + 3rd-party HTTP faked
│   ├── db/  repositories/  api/  ai/  external/
├── contract/              # OpenAPI snapshot, consumer contracts
├── e2e/                   # full stack over HTTP, few, slow
├── performance/           # benchmarks / load, opt-in only
├── security/              # auth bypass, injection, rate limits
├── property/              # hypothesis invariants
└── smoke/                 # 5–10 post-deploy liveness checks
unit-test-prompt/test-files/   # AI test-generation artifacts (md only, never test code)
```

Every folder under `tests/` that contains tests has an `__init__.py`.
Unit test for `<pkg>/a/b/c.py` lives at `tests/unit/a/b/test_c.py` — no exceptions.

## Placement rule (first "yes" wins)

1. Builder / fake / static data, no assert → `factories/` `fakes/` `fixtures/`
2. All external deps mockable AND real logic still runs → `unit/<mirror>/`
3. Needs real SQL, ORM mapping, constraints, migrations → `integration/db/` or `integration/repositories/` (`_db` suffix)
4. Router + real DB, LLM/external HTTP faked → `integration/api/` (`_api` suffix)
5. Real vector store with fake embeddings → `integration/ai/`
6. Stubbed third-party service → `integration/external/` (`_external` suffix)
7. Guards public API shape → `contract/`
8. Multi-step journey over HTTP → `e2e/`
9. Invariants over generated inputs → `property/`
10. Adversarial intent (auth, injection, rate limit) → `security/`
11. Latency / throughput budget → `performance/`
12. "Is the deployed system alive" → `smoke/`

If a test needs a real DB AND has heavy logic, split it: logic → unit (mock repo), persistence → integration.

## Hard rules

- Never real I/O in `tests/unit/` (DB, network, LLM, filesystem outside `tmp_path`, wall clock).
- Never SQLite as a stand-in for PostgreSQL, in any suite.
- Never delete or rename a test without an approved migration plan.
- Never modify production code to make tests fit the structure (adding a missing `__init__.py` is the only exception; report it).
- Never add `# pragma: no cover` or coverage `omit` without a written justification beside it.
- Never create empty placeholder folders for subpackages that do not exist in production code.
- Never write test artifacts outside `unit-test-prompt/test-files/`; never write test code inside it.
- Every test carries exactly one suite marker, applied automatically by the folder hook in `tests/conftest.py`.
- Test function names: `test_<function>_<outcome>_when_<condition>`.
- Before claiming any structural change works, run `pytest --collect-only -q` and show the result.