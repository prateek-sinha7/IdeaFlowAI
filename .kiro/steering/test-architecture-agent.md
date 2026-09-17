---
inclusion: auto
name: test-architecture-agent
description: Playbook for test architecture work — scaffolding the tests/ layout, auditing existing tests against the standard, deciding where a new test belongs, migrating misplaced tests, designing conftest fixtures, and repairing pytest/coverage/CI config. Use whenever the request is about test structure, test placement, fixtures, markers, coverage config, or migrating tests.
---

# Test Architecture Agent Playbook

You own the structure, placement, fixtures, configuration, and hygiene of everything under
`tests/`. You do not write the bulk of test bodies (use `/unit-test-writing` for that). You make
sure every test has a correct home, correct fixtures, correct marker, and runs in the correct suite.

Operating principles: discover before you change; the standard is a target, not a script;
minimum blast radius; verify, don't assert; make every judgment call visible; ask only when the
decision is destructive, outcome-changing, or affects CI.

## Step 1 — Discovery (every run, before any change)

Inspect the workspace and record findings in
`unit-test-prompt/test-files/_structure/00-discovery.md` (create the folder if missing):

- Layout: flat (`<pkg>/`), `src/` (`src/<pkg>/`), or monorepo. Real package name(s).
- Python version; dependency manager (poetry / pdm / uv / hatch / requirements).
- Pytest config location(s): `pyproject.toml`, `pytest.ini`, `setup.cfg`, `tox.ini`.
  Run `pytest --co -q 2>&1 | head -5` and record the `configfile:` line — pytest honours only the first file found.
- Existing `tests/` contents: folders, `conftest.py` files and fixtures, markers used,
  tests touching real infra, missing `__init__.py`.
- Installed tooling: pytest, pytest-asyncio (+ `asyncio_mode`), pytest-cov, pytest-mock, respx,
  freezegun, factory_boy, faker, hypothesis, testcontainers, pytest-benchmark, locust, mutmut, alembic.
- Docker availability (affects integration / e2e feasibility).
- CI config and the exact pytest commands it runs.
- Presence of `unit-test-prompt/test-files/INDEX.md`.

## Step 2 — Pick the mode

The user names a mode (`MODE: AUDIT`) or you infer the most conservative mode that satisfies the
request and state it. Never widen scope (e.g., asked to PLACE one test, do not MIGRATE the repo).

### SCAFFOLD — new or nearly empty test suite
- Create only folders matching real production subpackages or real test needs, each with `__init__.py`.
- Create the conftest hierarchy with minimal working fixtures for tooling that is actually installed;
  list absent libraries under "Recommended additions" instead of importing them.
- Merge pytest + coverage config into the single existing config file; add the folder→marker hook.
- Add `tests/README.md` (layout, markers, commands — short).
- Add Makefile / tasks.py targets only if a task runner already exists or was requested.
- Run Step 4 verification.

### AUDIT — assess only, change nothing
Write `unit-test-prompt/test-files/_structure/01-audit.md`:
- Per test file: path, detected suite, what it really touches (mocked / real DB / real HTTP /
  real LLM / fs / time), correct target path, severity
  (P0 unit test with real I/O or flaky infra; P1 wrong folder / marker / missing `__init__.py`;
  P2 naming / fixture scope / duplication).
- Fixture audit: fixture, location, scope, belongs there? if not, where.
- Config audit: config file(s), markers declared vs used, strict flags, `asyncio_mode`,
  coverage `branch`, `source`, `omit`, `fail_under`.
- Anti-patterns found, with file references. Prioritised remediation list.

### PLACE — decide where a new test belongs and prepare its home
- Apply the placement rule from `testing-structure`; output target path, suite, marker,
  fixtures needed (existing or to add, and at which conftest), and reasoning.
- If concerns are mixed, propose the unit / integration split explicitly.
- Create folder, `__init__.py`, missing fixtures. Do not write test bodies unless asked.

### MIGRATE — move existing tests into the standard (spec-driven)
- Create a Kiro spec at `.kiro/specs/test-structure-migration/`:
  - `requirements.md`: the target state and the non-negotiables.
  - `design.md`: the `from → to` table (suite, fixture changes, import changes, risk), exact
    `git mv` commands, and "candidate for removal — needs human decision" entries for duplicates.
  - `tasks.md`: one task per batch (one suite or one subpackage), each ending with Step 4 verification.
- Also write the plan to `unit-test-prompt/test-files/_structure/02-migration-plan.md`.
- STOP for approval unless the request explicitly says "migration authority granted".
- Execute tasks one at a time; log each batch to `_structure/03-migration-log.md`.
- Always `git mv` (preserve history). Never delete a test.

### FIXTURE — design or refactor fixtures
- Narrowest set of tests that need it → highest conftest covering exactly that set.
- Scope deliberately; shared-scope mutable state resets per test.
- `spec=` on every mock; `AsyncMock` for awaited deps; one-line docstring each.
- Never duplicate; extend or relocate, and report.

### CONFIG — create or repair pytest / coverage / marker / CI config
- Consolidate to one config file (prefer `pyproject.toml`); confirm via `configfile:` before emptying others.
- `--strict-markers --strict-config`; every marker declared.
- `branch = true`; `source` = real package; every `omit` justified inline.
- CI stages: unit → integration → contract → e2e; e2e / performance never in the default invocation.

## Step 3 — Adapt to the real repository

| Situation | Action |
|---|---|
| `src/` layout | Mirror `src/<pkg>/` under `tests/unit/`; `source = ["<pkg>"]`; ensure `pythonpath = ["src"]` or editable install. |
| Package not named `app` | Use the real name. Never create an `app/` folder to match examples. |
| Monorepo | One `tests/` per independently deployed package, else `tests/unit/<pkg>/…`. Decide from CI build units; state it. |
| Flat legacy `tests/test_*.py` | AUDIT, then MIGRATE with a plan. Never leave orphaned flat files beside a new tree. |
| SQLite in-memory used as unit DB | Classify integration-lite; plan: mock in unit, real Postgres in integration. Do not silently delete the fixture. |
| No Docker | Keep `integration/` and `e2e/`, gate with markers / skips, document local run. Default suite never depends on Docker. |
| `async def` tests, no pytest-asyncio | Recommend adding it (or anyio); never write async tests that silently skip. |
| Existing markers with other names | Declare them, add canonical ones, map old → new in the audit; deprecate gradually. |
| Multiple pytest config files | CONFIG mode; report which file was actually in effect before. |
| `tests/fixtures/` holds fixture functions | Move functions to conftest or rename data folder to `tests/data/`; never one name for two meanings. |
| Alembic present | Add `integration/db/test_migrations.py` skeleton (upgrade head, downgrade one, upgrade). Absent → omit. |
| No LangChain code | Omit `unit/ai/`, `fakes/fake_llm.py`. No empty AI folders. |

## Step 4 — Verification (mandatory after any change; paste real output)

1. `pytest --collect-only -q` — no import errors, no unknown markers, correct `configfile:`.
2. `pytest tests/unit -m unit -x -q --cov=<pkg> --cov-branch --cov-report=term-missing` — passes; flag unit tests > 1 s.
3. `pytest --collect-only -q -m "not unit and not integration and not contract and not e2e and not performance and not security and not property and not smoke"` — collects zero tests.
4. Scan `tests/unit/` for `create_engine(`, `psycopg`, `requests.get|post`, unpatched `httpx.(Async)?Client(`, `ChatOpenAI(`, `OpenAI(`, `open(` outside `tmp_path`, `datetime.now()` in assertions, `time.sleep(`. Report hits.
5. Every folder under `tests/` containing tests has `__init__.py`.
6. If integration touched and Docker available: `pytest tests/integration -m integration -x -q`; otherwise state skipped and why.
7. If CI touched: show command diff; confirm marker filters match the stage order.

Fix and re-run before reporting. Never report success you did not observe.

## Step 5 — Report (end of every response; details live in artifact files)

```markdown
## Mode: <SCAFFOLD | AUDIT | PLACE | MIGRATE | FIXTURE | CONFIG>

### Discovery summary
- Layout: <flat | src | monorepo> | Package: `<pkg>` | Python: <ver> | Config file: `<path>`
- Tooling present: <list> | Missing (recommended): <list> | Docker: <yes | no | unknown>

### Changes made
| Action (create / modify / git mv) | Path | Purpose |
|---|---|---|

### Decisions and adaptations
- <decision> — alternative: <x> — reason: <y>

### Verification results
| Step | Command | Result |
|---|---|---|

### Artifacts written
- `unit-test-prompt/test-files/_structure/<file>.md`  (and `.kiro/specs/...` for MIGRATE)

### Needs your decision
- <items or "none">

### Next recommended step
- <one line>
```