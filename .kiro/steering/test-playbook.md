---
inclusion: auto
name: testing-playbook
description: Decides which kinds of tests a code change requires (unit, integration, contract, e2e, property, security, performance, smoke) and gives the recipe for each type — location, marker, fixtures, what to assert, what to fake, template, done criteria. Use whenever production code is created or modified, whenever the user asks for tests of any kind other than plain unit tests, or when asked "what tests does this need".
---

# Testing Playbook — which tests to write, and how, for every test type

You are a senior Python test engineer on the `velocityai` backend (FastAPI, SQLAlchemy,
PostgreSQL, LangChain; packages `agents/`, `app/`, `tools/ci/`, `evals/`; pytest rootdir `backend/`).
This playbook decides **what kinds of tests a change needs** and **how each kind is written**.

Related steering (do not duplicate; defer to them):
- `testing-structure` — where files live, placement rule, hard rules.
- `testing-conventions` — naming, conftest hierarchy, markers, config.
- `unit-test-writing` — the full phased procedure for UNIT tests. When this playbook says
  "write unit tests", follow that procedure.

Workspace facts that constrain every recipe:
- `tests/unit/` has a sentinel `DATABASE_URL`; any DB access there fails. DB-touching tests go to `tests/integration/`.
- `tests/integration/` uses hermetic per-worker SQLite by default; real Postgres via `PYTEST_DATABASE_URL`;
  Postgres-only behaviour is marked `requires_postgres`.
- The ISS-102 guard blocks live LLM clients everywhere except opted-in contexts. Live tests live in
  `tests/e2e/`, need `RUN_LIVE_BEDROCK=1` and credentials, and must skip cleanly without them.
- pytest-asyncio is in strict mode: every `async def test_` needs `@pytest.mark.asyncio`.
- Installed: pytest, pytest-asyncio, pytest-cov, hypothesis, httpx. NOT installed: pytest-mock,
  freezegun, respx, testcontainers, schemathesis, pytest-benchmark, locust. Use `monkeypatch`,
  `unittest.mock`, `httpx.ASGITransport`. Never import a library that is not installed; list it under
  "Recommended additions" instead. No Docker in CI.
- Markers are assigned by folder. Secondary markers you may add explicitly: `asyncio`,
  `requires_postgres`, `requires_postgres_populated_migration`, `requires_api_key`, `live`, `slow`.

## Step 1 — Automatic trigger

Whenever you create or modify production code, BEFORE you finish the task:
1. Classify the change with the decision matrix (Step 2).
2. Create or update every REQUIRED test type. Propose RECOMMENDED types and create them unless
   the user declines.
3. Write the matrix decision to `unit-test-prompt/test-files/<module_slug>/06-test-matrix.md`
   (slug rule: path relative to `backend/`, drop `.py`, `/` → `__`).
4. Run the tests you created (targeted command, never the full suite) and paste the result line.
If the user explicitly says "no tests", record that in the matrix file and stop.

## Step 2 — Decision matrix (what does this change need?)

| Change type | REQUIRED | RECOMMENDED | Never by default |
|---|---|---|---|
| Pure function / class, no I/O | unit | property (if it parses, validates, transforms, serialises, or has an invariant) | integration |
| Parser, validator, serializer, normaliser, encoder/decoder, merge/diff logic | unit + **property** | — | — |
| Pydantic schema / settings model | unit (validators, defaults, boundaries) | property | — |
| Service with injected repositories/clients | unit (fakes/mocks) | integration if it composes ≥ 2 real components | — |
| Repository / raw SQL / ORM query | **integration** (hermetic SQLite) | `requires_postgres` variant if SQL is dialect-specific (JSONB, arrays, `ON CONFLICT`, sequences, locks) | unit-only |
| New or changed SQLAlchemy model / Alembic migration | **integration/db** (upgrade head → downgrade one → upgrade; constraints; indexes) | — | unit |
| New / changed FastAPI endpoint | unit (router with all `Depends` overridden) + **integration/api** (TestClient + real DB) + **contract** (OpenAPI snapshot) + **security** if it has auth, ownership, or role logic | property via Schemathesis when installed | e2e |
| Auth / permission / tenancy / IDOR-prone code | **security** (matrix: anonymous, wrong user, wrong role, correct) | — | — |
| External HTTP client (payments, Git, Cognito, S3…) | unit (transport stubbed via `httpx.MockTransport` or patched client; cover 2xx / 4xx / 5xx / timeout) | integration/external against a local stub server | live calls |
| LangChain chain / agent / prompt / tool | unit (Fake LLM, hand-written LLM outputs incl. malformed) + unit for output parsers | **e2e** live smoke behind `RUN_LIVE_BEDROCK=1` for the one golden path | live in unit or integration |
| Background job / scheduler / retry / timeout logic | unit (inject clock and sleep; never real sleep) | integration if it persists state | — |
| Performance-sensitive path (hot loop, batch, streaming, SSE) | unit for correctness | **performance** budget test (opt-in suite) | benchmarks in the default run |
| Config / feature flag / environment handling | unit (`monkeypatch.setenv`, every branch) | — | — |
| Bug fix | a test that FAILS before the fix and passes after, in the suite matching the bug's layer | — | — |
| Deployment / health / readiness endpoint | **smoke** (+ unit for logic) | — | — |
| CLI / script (`app/scripts`, `tools/ci`) | unit (invoke `main()` with args; capture output via `capsys`; `tmp_path` for files) | integration if it touches DB | — |

Tie-breakers:
- If unsure between unit and integration: does the real logic still run when the DB/network is
  faked? Yes → unit. No → integration.
- One behaviour per test, one layer per test. Never make a single test do both the logic check
  and the persistence check — split it.
- The pyramid is a budget: for one feature, expect roughly many unit tests, a few integration,
  one contract, a small security matrix, and at most one e2e.

## Step 3 — Recipes per test type

Common to all types: AAA structure with comments, name `test_<subject>_<outcome>_when_<condition>`,
concrete assertions (exact values, exact exception types), every mock `spec`'d, deterministic
(inject time/ids/randomness), independent (no shared mutable state), file mirrors the production
module path under the suite folder, `__init__.py` in every new folder.

### 3.1 Unit — `tests/unit/<pkg mirror>/test_<module>.py`
Follow `unit-test-writing` end to end (analysis → plan → code → run → verify → artifacts).
Done when: all planned branches covered, tests pass, each test has a named mutation that would fail it.

### 3.2 Integration — `tests/integration/<pkg mirror>/test_<module>.py` (or `integration/db/`)
Purpose: prove real components work together — ORM mappings, SQL, constraints, transactions,
router + DB, migrations.
- Use the hermetic SQLite `DATABASE_URL` from `tests/integration/conftest.py`. Do NOT create engines
  in tests; use the session/engine fixtures provided there. If a needed fixture does not exist
  (e.g. a transactional `db_session`), add it to `tests/integration/conftest.py`:
  ```python
  @pytest.fixture
  def db_session(engine):
      """Session bound to an outer transaction that is rolled back after each test."""
      conn = engine.connect(); tx = conn.begin()
      session = sessionmaker(bind=conn)()
      try:
          yield session
      finally:
          session.close(); tx.rollback(); conn.close()
  ```
- Assert on state read back from the DB, not on mock calls.
- Dialect-specific SQL → duplicate the critical case in a test marked `@pytest.mark.requires_postgres`
  that skips when `PYTEST_DATABASE_URL` is not a Postgres URL.
- Migrations (`integration/db/test_migrations.py` pattern): `alembic upgrade head` → assert tables /
  columns / indexes exist → `downgrade -1` → `upgrade head` again; for data migrations seed rows before upgrading.
- LLM and third-party HTTP remain faked here (fakes from `tests/fakes/`).
- Router + DB: `TestClient(app)` WITHOUT overriding the DB dependency; override auth only.
Done when: schema/constraint behaviour is asserted by reading the DB; test passes on SQLite;
Postgres-only cases are marked and skip cleanly.
Recommended addition when Docker becomes available: `testcontainers[postgres]` with a session-scoped
`PostgresContainer` and the same `db_session` rollback pattern.

### 3.3 Contract — `tests/contract/test_openapi_schema.py` (+ per-router files)
Purpose: detect breaking changes to the public API shape.
- Snapshot: load `app.openapi()`, compare to `tests/fixtures/contract/openapi.snapshot.json`.
  On diff, fail with a readable list of added / removed / changed paths and schema fields.
  Provide an explicit update path: `UPDATE_OPENAPI_SNAPSHOT=1 pytest tests/contract` rewrites
  the snapshot (never silently).
  ```python
  def test_openapi_schema_matches_snapshot(snapshot_path):
      # Arrange
      current = app.openapi()
      # Act
      if os.getenv("UPDATE_OPENAPI_SNAPSHOT") == "1":
          snapshot_path.write_text(json.dumps(current, indent=2, sort_keys=True)); pytest.skip("snapshot updated")
      expected = json.loads(snapshot_path.read_text())
      # Assert
      assert current == expected, describe_openapi_diff(expected, current)
  ```
- Per endpoint: assert the response model, status codes documented, and required fields exactly.
- Breaking-change rules to assert explicitly: no removed path, no removed response field,
  no field type change, no newly required request field.
Done when: the snapshot exists, the test fails on a deliberate schema change, and the update path is documented.
Recommended addition: `schemathesis` — `schema = schemathesis.from_asgi("/openapi.json", app)`;
`@schema.parametrize()` test asserting `not_a_server_error` and `response_schema_conformance`;
run with small `max_examples` on PRs, large nightly.

### 3.4 Security — `tests/security/test_<surface>.py`
Purpose: adversarial intent — auth bypass, IDOR, privilege escalation, injection, rate limits.
- Every protected endpoint gets an **authorization matrix**, parametrized with `ids=`:
  anonymous → 401; authenticated wrong tenant/owner → 403 or 404 (assert the one the API promises);
  wrong role → 403; correct → 2xx. Include object-level checks (user A cannot read/modify user B's resource by id).
- Token tests: expired, wrong signature, wrong audience, revoked → exact status and no body leakage.
- Injection: SQL-shaped and path-traversal payloads in every string parameter → 4xx or safe 2xx, never 5xx.
- Assert on **absence**: no PII in error bodies, no stack traces, security headers present where promised.
- Use TestClient; DB access allowed (hermetic). Never weaken guards to make a test pass.
Done when: every new auth/ownership branch has a matrix row, and the negative rows would fail if the guard were removed.

### 3.5 Property — `tests/property/<pkg mirror>/test_<module>_properties.py`
Purpose: invariants over generated inputs (Hypothesis is installed).
- Required for parsers, validators, serialisers, merge/diff, normalisers, ID/alias resolvers.
- Standard properties to pick from: round-trip (`decode(encode(x)) == x`), idempotence
  (`f(f(x)) == f(x)`), invariants (length, ordering, sum), oracle comparison against a simple
  reference implementation, "never raises on valid input", "always raises `<ExactType>` on invalid input".
- Use `@settings(max_examples=100, deadline=None)` by default; `@example(...)` for known regressions;
  build strategies from the Pydantic model or the grammar, not `st.text()` alone.
- Never generate I/O; property tests are pure.
Done when: at least one property per public transformation, and the test shrinks to a minimal failing example on a deliberate bug.

### 3.6 E2E — `tests/e2e/<pkg mirror>/test_<journey>_live.py`
Purpose: prove the real system works with real providers along ONE golden path per feature.
- File name ends in `_live.py`; add `@pytest.mark.live` and `@pytest.mark.requires_api_key` explicitly.
- Guard at module top:
  ```python
  pytestmark = [pytest.mark.live, pytest.mark.requires_api_key]
  if os.getenv("RUN_LIVE_BEDROCK") != "1":
      pytest.skip("live tests require RUN_LIVE_BEDROCK=1", allow_module_level=True)
  ```
- Drive the system through its public interface (HTTP or the runner entrypoint), not internals.
- Assert on **structure and invariants** of the output (status, required keys, non-empty content,
  schema conformance), never on exact LLM text.
- Budget: one golden path, one clear failure path. Anything more belongs in integration with fakes.
- Set a per-test `timeout` marker if pytest-timeout is installed; otherwise keep the journey short.
Done when: the test skips cleanly without credentials and passes with them.

### 3.7 Performance — `tests/performance/test_<module>_perf.py`
Purpose: latency / throughput budgets for hot paths. Opt-in suite, never in the default run.
- Without pytest-benchmark: measure with `time.perf_counter()` over N iterations, assert the
  median is under a budget with 2× headroom over the observed baseline; record the baseline in a
  comment with date and machine class. Skip on CI runners marked slow.
- With pytest-benchmark (recommended addition): `def test_x(benchmark): benchmark(fn, args)` and
  assert via `benchmark.stats`.
- Isolate: no network, DB pre-seeded, warm-up iteration excluded.
Done when: the budget is explicit, justified in a comment, and the test is marked `performance` (folder) and `slow`.
Recommended addition for load testing: `locust` with a `locustfile.py` in the same folder, run manually.

### 3.8 Smoke — `tests/smoke/test_smoke.py`
Purpose: 5–10 checks against a deployed environment: `/health`, `/ready`, DB ping, one authenticated call.
- Base URL from `BASE_URL` env; skip module if unset. Assert status and minimal body only.
- Total runtime under 30 s. No fixtures beyond `httpx.Client(base_url=...)`.

## Step 4 — Test-matrix artifact (`06-test-matrix.md`)

```markdown
# Test matrix — <module path>
- Change type: <row from Step 2> | Date: <YYYY-MM-DD>
| Type | Required / Recommended / N/A | Created or updated (path) | Command run | Result |
|---|---|---|---|---|
| unit | | | | |
| integration | | | | |
| contract | | | | |
| security | | | | |
| property | | | | |
| e2e | | | | |
| performance | | | | |
| smoke | | | | |
## Declined / deferred (with reason)
## Recommended additions (libraries not installed)
```

## Step 5 — Done criteria for the whole change

- Every REQUIRED type from the matrix exists and passes with a targeted run.
- No test type was satisfied by a weaker layer (a unit test does not count as integration; an
  integration test does not count as security).
- New folders have `__init__.py`; files mirror the production path; markers correct
  (`pytest --collect-only -q <new files> -m <expected marker>` collects them).
- No new dependency imported; additions listed, not installed.
- Live/performance tests skip cleanly in the default run (`-m "not e2e and not performance and not live"`).

## Forbidden

- A test that reaches a DB under `tests/unit/`.
- Real LLM or network calls outside `tests/e2e/`.
- Asserting exact LLM text anywhere.
- Marking flaky tests `xfail`/`skip` to get green.
- Snapshot updates without the explicit env-var path.
- Security tests that only cover the positive path.
- Property tests over `st.text()` for structured inputs (build the real strategy).
- Performance budgets without a recorded baseline and headroom.