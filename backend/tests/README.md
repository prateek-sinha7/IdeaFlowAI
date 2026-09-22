# Backend Test Suite

Tests are organised **by suite first, then mirrored by production package**. The folder a test
lives in defines how it runs, what it may touch, and which marker it receives (assigned
automatically by the hook in `tests/conftest.py` — no manual suite decorators).

## Layout

```
tests/
├── conftest.py          root: marker hook, ISS-102 live-model guard, zero-I/O autouse resets, pytest_plugins
├── plugins/             shared fixture modules (agents_fixtures.py, ci_fixtures.py) — not tests
├── factories/           test-data builders — not tests
├── fakes/               in-memory fakes — not tests
├── fixtures/            STATIC DATA only (YAML, sample repos) — excluded from collection
├── unit/                fast, isolated; CANNOT reach a database (sentinel DATABASE_URL)
│   ├── agents/          mirrors backend/agents/
│   ├── app/             mirrors backend/app/
│   ├── tools/ci/        mirrors backend/tools/ci/
│   └── evals/
├── integration/         touches a database, an external binary, or several components at once
│   ├── db/              alembic + migration tests, Postgres-only tests
│   ├── repositories/    ScopedStore / repository persistence (`*_db.py`)
│   ├── api/             router + DB through TestClient (`*_api.py`)
│   ├── external/        real external binary or stubbed third-party service (`*_external.py`)
│   ├── agents/  app/    mirrored
├── property/            Hypothesis invariants (tools/ci/…)
├── security/            auth boundaries, IDOR, route contracts
├── performance/         latency/throughput budgets — opt-in
└── e2e/                 live-provider / production-contract tests — opt-in, never in default run
```

Mirror rule: the test for `backend/<pkg>/a/b.py` lives at `tests/<suite>/<pkg>/a/test_b.py`.

## Suite semantics

| Suite | Marker | May touch | Default run? | Needs |
|---|---|---|---|---|
| `unit/` | `unit` | nothing external; DB access fails immediately | yes | — |
| `integration/` | `integration` | hermetic SQLite (per worker); real Postgres when `requires_postgres*` | yes (SQLite part) | `PYTEST_DATABASE_URL` for Postgres tests |
| `property/` | `property` | nothing external | yes | — |
| `security/` | `security` | TestClient / hermetic DB | yes | — |
| `performance/` | `performance` | whatever it measures | **no** | — |
| `e2e/` | `e2e` (+ `live`) | live LLM providers, network | **no** | `RUN_LIVE_BEDROCK=1`, provider credentials, `CI_OFFLINE` unset |

Secondary markers (explicit decorators): `asyncio`, `requires_postgres`,
`requires_postgres_populated_migration`, `requires_api_key`, `live`, `slow`.

## Commands (run from `backend/`)

```bash
uv run pytest -m "not e2e and not performance and not live"      # default full run (CI / PR)
uv run pytest                                                    # everything (needs creds + Postgres)
uv run pytest tests/unit                                         # unit only
uv run pytest -m "integration and not requires_postgres and not requires_postgres_populated_migration"
PYTEST_DATABASE_URL=postgresql://… uv run pytest tests/integration
uv run pytest tests/property tests/security
RUN_LIVE_BEDROCK=1 uv run pytest tests/e2e                       # opt-in live
uv run pytest tests/unit/agents/workflows/test_compiler.py -k compile
uv run pytest -m "not e2e and not performance and not live" --cov=app --cov=agents --cov=tools --cov-branch --cov-report=term-missing
uv run pytest --lf                                               # re-run last failures
```

Or via Makefile: `make test`, `make test-unit`, `make test-integration`, `make test-cov`, `make test-check`.

## Where does a new test go? (first match wins)

1. Builder / fake / static data → `factories/`, `fakes/`, `fixtures/`
2. Hits a live provider or production endpoint → `e2e/`
3. Needs Postgres, or tests Alembic / migrations → `integration/db/`
4. Measures latency / throughput → `performance/`
5. Uses Hypothesis → `property/`
6. Adversarial intent (auth bypass, IDOR, injection) → `security/`
7. Opens a DB session, uses `SessionLocal` / `Base.metadata`, or drives the app through
   `TestClient` without overriding the DB dependency → `integration/<pkg mirror>/`
8. **Spawns a process or needs an external binary** (`git`, `ruff`, Chromium/Playwright,
   a stdio MCP server) → `integration/` — `external/` for a third-party service,
   `<pkg mirror>/` when it is our own code doing the spawning
9. **Drives a whole workflow end to end** through `execute()` / `resume_run()` across
   several agents — even offline with a scripted model → `integration/agents/`
10. Everything else → `unit/<pkg mirror>/test_<module>.py`

### Integration file-name suffixes

| Suffix | Means |
|---|---|
| `_db` | needs a real engine / persisted rows |
| `_api` | router + DB through `TestClient` |
| `_external` | needs an external binary or process (git, ruff, Chromium, stdio server) |
| *(none)* | multi-component in-process drive, no external dependency |

## Rules

- File name = module under test: `test_<module>.py`. Ticket IDs go in docstrings, not file names.
- Test name = behaviour: `test_<function>_<outcome>_when_<condition>`.
- Unit tests never reach a DB, network, LLM, external process, browser, or filesystem outside
  `tmp_path`. `tests/unit/conftest.py::_unit_io_guard` enforces this at the connect/spawn
  layer — a SQLAlchemy `Engine` "connect" listener, `subprocess.Popen.__init__`, and
  `socket.connect`/`connect_ex` — so a by-value `from sqlalchemy import create_engine`
  cannot slip past it. A violation raises `UnitIsolationError` naming the suite to move to.
  Its own tests live in `tests/unit/test_unit_io_guard.py`.
- **Deliberate exception:** `@pytest.mark.allow_io("why")` disables the guard for one test.
  There is exactly ONE in the suite (the guard's own escape-hatch test). Adding a second
  needs a reason that survives review — usually the honest answer is
  `tests/integration/`. `socket.socketpair` is exempt unconditionally: Windows event-loop
  setup needs it, and a pair can only talk to itself.
- Async tests need an explicit `@pytest.mark.asyncio` (strict mode).
- Fixtures live at the highest `conftest.py` where they are valid. Cross-suite fixtures go in
  `tests/plugins/` and are registered via `pytest_plugins` in the root conftest.
- Every mock has `spec=` / `autospec=True`.
- Never add `# pragma: no cover` or coverage `omit` entries without a justification comment.

## Fixtures

| Where | What |
|---|---|
| `tests/conftest.py` | marker hook, ISS-102 guard (`_forbid_live_model_clients`), autouse cache/latch resets |
| `tests/plugins/agents_fixtures.py` | `in_process_checkpointer` (autouse, suite-wide), `tmp_agent_dir`, `local_git_fixture`, `make_agent_md`, `create_agent_file` |
| `tests/plugins/ci_fixtures.py` | `ci_canary_session_config`, `ci_test_result_factory` |
| `tests/unit/conftest.py` | event-loop isolation, DB sentinel, network sentinel |
| `tests/integration/conftest.py` | `postgres_container` / `engine` / `db_session` (testcontainers Postgres), `alembic_upgrade` |
| `tests/integration/db/conftest.py` | `alembic_config_for(url)`, `fresh_db_url` (throwaway file-backed SQLite) |
| `tests/integration/repositories/conftest.py` | `db_session` — hermetic in-memory SQLite; **shadows** the Postgres one above for that folder |
| `tests/fakes/gate_runner.py` | `FakeGateRunner`, `FakeGateEventRow`, `seed_gate_reentry_ectx` |
| `tests/fakes/validation_stubs.py` | static/render result stubs, deliverable target, recording validation runner |

A shared fake or harness must NOT live in a test module. If two suites need it, it goes in
`tests/fakes/` (objects) or `tests/plugins/` (fixtures) — a unit test importing from an
integration test module is a layering break.

# Unit Suite

Fast, isolated tests. Mirrors production packages: `unit/<pkg>/<path>/test_<module>.py`.

- **No database.** `conftest.py` sets `DATABASE_URL` to an unreachable sentinel; any DB access
  fails with a connection error. If that happens, move the test to `tests/integration/`.
- No network, no live LLM clients (blocked by the ISS-102 guard), no filesystem outside `tmp_path`.
- Async tests: `@pytest.mark.asyncio` required (strict mode); each test gets a fresh event loop.
- Run: `uv run pytest tests/unit` · one package: `uv run pytest tests/unit/agents`

# Integration Suite

Tests that touch a database or exercise several components together.

- Default DB: **hermetic SQLite**, one file per worker, pinned in `conftest.py`.
- Real PostgreSQL: set `PYTEST_DATABASE_URL`; tests marked `requires_postgres` /
  `requires_postgres_populated_migration` are skipped without it.
- `db/` holds Alembic and migration tests. Other folders mirror production packages.
- Run offline: `uv run pytest -m "integration and not requires_postgres and not requires_postgres_populated_migration"`
- Run with Postgres: `PYTEST_DATABASE_URL=postgresql://… uv run pytest tests/integration`

# E2E / Live Suite

Live-provider and production-contract tests. **Never part of the default run.**

- Requires `RUN_LIVE_BEDROCK=1`, valid provider credentials, and `CI_OFFLINE` unset.
- Slow (30–45 s per file is normal). Run deliberately: `RUN_LIVE_BEDROCK=1 uv run pytest tests/e2e`
- Files: `*_live.py`, `*_prod.py`. Marked `e2e` by folder; keep the explicit `live` /
  `requires_api_key` markers so CI filters continue to work.

# fixtures/ — static data only

YAML workflows, sample repositories, recorded payloads. **Not pytest fixtures, not tests.**
This folder is excluded from collection (`norecursedirs`). Pytest fixture *functions* live in
`conftest.py` files or `tests/plugins/`; data builders live in `tests/factories/`.

## Environment variables

| Variable | Effect |
|---|---|
| `PYTEST_DATABASE_URL` | Use this DB instead of hermetic SQLite (integration) |
| `CI_OFFLINE=1` | Fail if provider credentials are present; ensures offline run |
| `RUN_LIVE_BEDROCK=1` | Opt in to live provider calls (`e2e/`) |
| `PYTEST_XDIST_WORKER` | Set by pytest-xdist; selects the per-worker SQLite file |

## Known debt

- **`tests/unit/{api,app,services}` still contains ~45 files that build a real
  `create_engine(...)`**, plus 2 Alembic chains, 11 `subprocess` spawns, one real socket
  and one live `httpx.AsyncClient`. They belong in `integration/`. `tests/unit/agents/`
  was cleared of all of this in Batch 6 — see
  `unit-test-prompt/test-files/_structure/03-migration-log.md`.
- **63 files / 599 tests are known to trip the unit I/O guard** and are queued for
  eviction — inventory in `unit-test-prompt/test-files/_structure/03-migration-log.md`
  §7.3. Until they move, `pytest tests/unit` is red by design: every `UnitIsolationError`
  is a misplaced test, not a broken one.
- Path roots are computed as `Path(__file__).resolve().parents[N]`, so **N depends on the
  file's depth** — a move must recompute it. Batch 6 repaired 43 sites broken this way by
  earlier moves; a wrong root silently EMPTIES manifest-driven `parametrize` lists rather
  than failing, which hid 69 tests from CI.
- Integration suite is a mix: `integration/conftest.py` offers a testcontainers Postgres,
  while `repositories/` and most relocated suites use hermetic in-memory SQLite.
  Dialect-specific behaviour is only covered by `requires_postgres*` tests.
- Several files keep legacy ticket-ID names (`test_iss0xx_*`, `test_db002_*`); rename to module
  names when touched.
- Very large files (`integration/agents/test_restart_resume_db.py` at 5 400 lines,
  `unit/app/test_sse_stream.py`) are candidates for splitting.
- `tools/ci` classes `TestNode`, `TestCase`, `Partition` trigger collection warnings until
  `__test__ = False` is added.
- Known reds unmasked by the Batch 6 path repair (they were vacuous, not green):
  `test_validators_import_the_single_map_severity`,
  `test_compiled_agent_sequence_matches_registry_order[prototype_*revision]` ×3,
  `test_compiled_clarify_defaults_match_engine_dict[sc001-test-fixture]`.