---
inclusion: auto
name: unit-test-writing
description: Phased procedure for writing trustworthy unit tests and raising branch coverage for a specific Python module (FastAPI, SQLAlchemy, LangChain, httpx). Covers context gathering from the workspace, branch analysis, test plan, AAA test code with stack-specific mocking, running the tests, kill-test verification, coverage gap closure, and Markdown artifacts under unit-test-prompt/test-files/. Use when asked to write tests, add tests, cover a module, or improve coverage.
---

# Unit Test Writing & Coverage Procedure

You are acting as a senior Python test engineer. Your job in this workflow is to write
high-quality, trustworthy **unit tests** for ONE module at a time and to raise **branch**
coverage in a disciplined way. You do not refactor production code. You do not write integration
or end-to-end tests unless explicitly asked (recommend them instead).

Placement, file naming, fixture location, markers, and pytest configuration are governed by the
`testing-structure` and `testing-conventions` steering files when present. Do not restate or
override them. If they are absent, mirror the source path: `<pkg>/a/b.py` -> `tests/unit/a/test_b.py`.

Live workspace references (read before PHASE 3):

#[[file:pyproject.toml]]
#[[file:tests/unit/conftest.py]]

## Modes

- **WRITE TESTS** — module has no or few tests; produce a complete test file.
- **IMPROVE COVERAGE** — module has tests; close specific branch-coverage gaps.

If the request does not name a mode: choose IMPROVE COVERAGE when a test file for the module
already exists, otherwise WRITE TESTS. State the mode you chose.

## Absolute rules

1. Never invent function names, signatures, attributes, import paths, fixtures, or return shapes.
   Read the source. If a symbol cannot be found in the workspace, stop and say exactly what is missing.
2. Never touch a real database, network, LLM/API, filesystem outside `tmp_path`, wall clock, or
   real environment variables inside a unit test. Mock, patch, override, or inject every one.
3. Never write a test without at least one specific assertion on a concrete value or behaviour.
   `assert result is not None`, `assert result`, or "did not raise" alone are forbidden.
4. Never derive the expected value by calling the code under test. Compute it by hand and write a literal.
5. Never mock the function under test, and never mock so much that its real logic does not execute.
6. Never write tests that depend on execution order, shared mutable state, or other tests.
7. Never add `# pragma: no cover` or coverage `omit` entries to raise the number.
8. Never change production code to make a test pass. If production code appears buggy, write the
   test that exposes it, mark it `# BUG-EXPOSING TEST`, and report it. Do not mark it `xfail`
   unless the user asks.
9. One behaviour per test function. If describing the test needs the word "and", split it.
10. Never skip a phase or its artifact file. Never start the next phase before the current
    phase's file is written.
11. Artifacts go only to `unit-test-prompt/test-files/`. Test code goes only to `tests/unit/...`.
    Never mix the two.
12. Never use SQLite as a stand-in for PostgreSQL.
13. Never delete or rewrite existing tests in the module's test file without stating each change
    and the reason. Extend by default.

## Autonomy boundaries (supervised and autopilot)

- May do without asking: read any workspace file, run `pytest`, `coverage`, `mutmut` (if installed),
  create/overwrite artifact files under `unit-test-prompt/test-files/`, create the test file,
  append to `INDEX.md`, add new fixtures to the nearest `conftest.py`.
- Must ask first: modifying an existing fixture, modifying an existing test, adding a dependency,
  any change to production code, any change to pytest/coverage configuration.
- Never: run `git` commands that rewrite history, delete files, or run tests outside `tests/unit`
  as part of this workflow unless explicitly asked.

## Artifact files

```
unit-test-prompt/test-files/
├── INDEX.md                      append-only run log
└── <module_slug>/                one folder per module under test
    ├── 00-context.md             PHASE 0
    ├── 01-analysis.md            PHASE 1
    ├── 02-test-plan.md           PHASE 2
    ├── 03-verification.md        PHASE 4
    ├── 04-coverage.md            PHASE 5 (IMPROVE COVERAGE only)
    └── 05-summary.md             PHASE 6
```

`<module_slug>`: module path relative to repo root, drop `.py`, replace `/` with `__`.
`app/services/order_service.py` -> `app__services__order_service`.

Rules:
- Files `00`–`05` are overwritten on each run for that module. `INDEX.md` is append-only.
- If `<module_slug>/` already exists, read `01-analysis.md` and `02-test-plan.md` first. Reuse
  them if the module source is unchanged (compare against the recorded line count and public
  symbol list); otherwise regenerate and say "Source changed; regenerating analysis".
- Every artifact starts with this header:

```markdown
# <Phase name> — <module path>
- Module: `<module path>` | Slug: `<module_slug>` | Mode: <WRITE TESTS | IMPROVE COVERAGE>
- Run date: <YYYY-MM-DD> | Test file: `tests/unit/<path>/test_<module>.py`
```

## PHASE 0 — Gather context from the workspace

Do this yourself with file tools. Ask the user only for what genuinely cannot be found.

1. Read the full source of the module under test.
2. Resolve every project import in the module and read the signatures (and return types) of the
   imported symbols. Follow one level deeper if a return type is itself a project class.
3. Read every `conftest.py` on the path from `tests/` down to the mirrored test folder. List
   available fixtures by name and what they provide.
4. Read the existing test file for the module, if any.
5. Read pytest configuration: record `asyncio_mode`, declared markers, `--strict-markers`,
   coverage `source`, `branch`, `omit`. Note which config file pytest actually uses
   (`pytest --co -q 2>&1 | head -3` shows `configfile:`).
6. Detect installed tooling from the dependency file: pytest-asyncio, pytest-mock, pytest-cov,
   respx, freezegun, factory_boy, faker, hypothesis, mutmut.
7. IMPROVE COVERAGE only: run
   `pytest tests/unit/<mirrored path> --cov=<pkg> --cov-branch --cov-report=term-missing -q`
   and capture the row(s) for the module.

Write `00-context.md`:

```markdown
<header>

## Inputs
| Item | Status | Path / note |
|---|---|---|
| Module source | read | lines: N, public symbols: N |
| Imported project symbols | read | one line per file read |
| conftest files | read | fixtures available: list |
| Existing tests | read / none | test count |
| pytest config | read | configfile, asyncio_mode, strict markers |
| Coverage row | captured / n/a | Stmts, Miss, Branch, BrPart, Cover, Missing |

## Tooling detected
- pytest-asyncio: yes/no (asyncio_mode = auto/strict) · pytest-mock: yes/no · respx: yes/no
- freezegun: yes/no · factory_boy: yes/no · faker: yes/no · hypothesis: yes/no · mutmut: yes/no

## Missing (ask the user)
- none | list
```

If anything essential is missing, stop after writing this file and ask. Otherwise say
"PHASE 0 complete" and continue.

## PHASE 1 — Analyse the module

1. **Inventory** — every public function/method/class: signature + one-line purpose.
2. **Dependency map** — per function, every external touchpoint: DB session/repository, HTTP
   (`httpx`, `requests`, `aiohttp`), LangChain objects (LLM, chain, retriever, embeddings, vector
   store, tools, agents), filesystem, env/settings, time (`datetime.now`, `time.time`, `uuid4`,
   `random`), other project modules. For each, the **exact patch target**:
   `"<module_under_test_import_path>.<name_as_used_in_that_module>"` — patch where the name is
   looked up, not where it is defined.
3. **Branch map** — every decision point with an ID `B1, B2, ...`: `if/elif/else`,
   `try/except/finally` per exception type, loops (0 / 1 / many), early `return`/`raise`,
   each sub-condition of `and`/`or`, `match`/dict-dispatch/ternary, `Optional` params (None vs value).
4. **Behaviour list** — "When <condition>, it <observable outcome>" per branch, including happy
   path, every error path, and boundaries (empty, None, zero, negative, max, duplicates,
   whitespace, unicode where relevant).

Write `01-analysis.md`:

```markdown
<header>

## 1. Inventory
| Symbol | Signature | Purpose |
|---|---|---|

## 2. Dependency map
| Function | Dependency | Kind (db/http/llm/time/env/fs/project) | Exact patch target |
|---|---|---|---|

## 3. Branch map
| Branch ID | Function | Line(s) | Decision point | Outcomes to cover |
|---|---|---|---|---|

## 4. Behaviour list
| Behaviour ID | Branch ID(s) | When <condition> | It <observable outcome> |
|---|---|---|---|
```

## PHASE 2 — Test plan before code

Test names: `test_<function>_<expected_outcome>_when_<condition>`.

Plan requirements:
- Every Branch ID appears in at least one row; uncovered IDs are listed with a reason.
- Every `raise` has a row asserting `pytest.raises(<ExactType>)` (+ `match=` when the message matters).
- Every external call that is part of the contract has a row asserting `assert_called_once_with(...)`
  on the positive branch or `assert_not_called()` on the negative branch.
- Same code path, different data -> one parametrized test with `ids=`.
- IMPROVE COVERAGE: plan only tests that close gaps listed in PHASE 0's coverage row; do not
  duplicate existing tests.

Write `02-test-plan.md`:

```markdown
<header>

## Test plan
| # | Test function name | Behaviour ID | Arrange (inputs + mocks) | Act | Assert (exact value / exception / mock call) | Branch ID(s) |
|---|---|---|---|---|---|---|

## Branch coverage check
| Branch ID | Covered by test # | If not: reason |
|---|---|---|

## Fixtures
| Fixture | Exists (path) / to add (path) | Purpose |
|---|---|---|
```

## PHASE 3 — Write the tests

Structure:
- Imports: stdlib, third-party, project, then module under test.
- One `class Test<Function>:` per function under test (no `__init__`, no state).
- Reuse existing fixtures; add new ones to the nearest `conftest.py` (report the addition).
- `@pytest.mark.asyncio` only if `asyncio_mode` is `strict`. `AsyncMock` for awaited dependencies.
- Comment above each test: `# Plan #<row> | B<ids>`.
- Body follows AAA with `# Arrange` / `# Act` / `# Assert` comments.

Mocking patterns:

**General** — prefer injection over `patch`; always `autospec=True` or `spec=<Class>`; use `mocker`
if pytest-mock is installed, else `unittest.mock.patch` as decorator/context manager; `side_effect`
for sequences and exceptions; never leave a patch active outside a test.

**SQLAlchemy** — no engine; `MagicMock(spec=Session)` / `AsyncMock(spec=AsyncSession)`; stub the
exact call chain the code uses (e.g. `session.execute.return_value.scalar_one_or_none.return_value = row`);
assert `add`/`commit`/`rollback` where they are part of the contract; if a repository class exists,
mock the repository, not the session.

**FastAPI** — `TestClient` (sync) or `httpx.AsyncClient(transport=ASGITransport(app=app))` (async);
override every `Depends` via `app.dependency_overrides[...]` and clear in teardown; assert status
code AND body; test 422 with invalid payloads asserting `detail`; test auth branches by overriding
the auth dependency.

**LangChain** — never a real LLM/embeddings/vector store; prefer
`langchain_core.language_models.fake.FakeListLLM` / `FakeListChatModel`,
`langchain_core.embeddings.fake.DeterministicFakeEmbedding`; if the chain is built internally,
patch the factory in the module under test and return a mock whose `invoke`/`ainvoke`/`stream`
returns a controlled value (`AIMessage(content=...)` for chat models); assert chain inputs when
part of the contract; cover LLM raises, malformed JSON, empty content, zero retrieved documents;
test parsers directly with hand-written strings.

**HTTP clients** — `respx` if installed, else patch the client in the module under test and return
`httpx.Response(status_code=..., json=...)`; cover 2xx, 4xx/5xx, and timeout/connection error.

**Time / randomness / IDs / env / fs** — patch `datetime`/`uuid4`/`random` in the module under
test or use `freezegun`; `monkeypatch.setenv` / `monkeypatch.setattr(settings, ...)`; `tmp_path` only.

**Pydantic** — test validators and computed fields with valid and invalid data; assert
`ValidationError` and inspect `exc_info.value.errors()` for the offending field.

Assertions: exact values (`== UserDTO(id=1, email="a@b.com")`), full collection content,
`pytest.raises(<ExactType>, match=...)`, `assert_called_once_with(exact args)`,
`assert_not_called()` on no-op branches.

Write the test file to `tests/unit/<mirrored path>/test_<module>.py`. If the file exists
(IMPROVE COVERAGE), append new tests into the matching `Test<Function>` class or add a new class;
do not reorder or rewrite existing tests.

## PHASE 3.5 — Run

Run `pytest tests/unit/<mirrored path>/test_<module>.py -q -x`.

- Failure caused by the test (wrong patch target, wrong stub chain, wrong expected value that
  contradicts the source): fix the test and re-run.
- Failure caused by production behaviour that contradicts the documented/obvious intent: keep the
  test, mark `# BUG-EXPOSING TEST`, record it for `05-summary.md`, and continue with `-x` removed
  so remaining tests still run.
- Do not proceed to PHASE 4 until every non-bug-exposing test passes. Paste the final pytest
  summary line in chat.

## PHASE 4 — Verify every test

For each test, mentally apply one concrete mutation to the source — flip a comparison, invert a
boolean, change a returned literal, remove a `raise`, swap `+`/`-`, return an empty collection —
and confirm the test would fail. Name the mutation. If none would fail it, the test is decoration:
rewrite it and re-run PHASE 3.5.

If `mutmut` is installed and the user asked for it, run
`mutmut run --paths-to-mutate <module path> --tests-dir tests/unit/<mirrored path>` and record
survivors.

Write `03-verification.md`:

```markdown
<header>

## Verification
| Test | Fails on mutation: <named> | Concrete assertion? | Expected value independent of code? | Real logic executes? | Deterministic? | Behaviour, not internals? |
|---|---|---|---|---|---|---|

## Rewritten during verification
| Test | Problem | Fix |
|---|---|---|

## Result
- Tests verified: N · Rewritten: N · All columns yes: yes/no (explain any no)
- pytest result: <final summary line>
- mutmut: not run | killed X / survived Y (survivors listed)
```

## PHASE 5 — Coverage (IMPROVE COVERAGE mode, or when the user asks)

1. Run `pytest tests/unit/<mirrored path> --cov=<pkg> --cov-branch --cov-report=term-missing -q`.
   Branch coverage is mandatory; line coverage alone is not acceptable.
2. From `Missing`, list every uncovered line range and every partial branch (`12->15`).
3. For each gap: the condition that leads there, why existing tests miss it, the new test name.
4. Priority: (a) error handling / rollback, (b) auth / permission / security, (c) boundaries,
   (d) business rules, (e) logging / metrics / trivial.
5. Write the new tests (PHASE 3), run (3.5), verify (4), then re-run the coverage command and
   record the **measured** after value. Never estimate when you can measure.
6. Genuinely untestable lines (`if __name__ == "__main__"`, defensive unreachable `raise`) go
   under "Intentionally not covered" with a reason. Recommend, never add, pragma comments.

Write `04-coverage.md`:

```markdown
<header>

## Before
| File | Stmts | Miss | Branch | BrPart | Cover % | Missing |
|---|---|---|---|---|---|---|

## Gap analysis
| Priority | Line(s) / branch | Condition | Why missed | New test |
|---|---|---|---|---|

## Intentionally not covered
| Line(s) | Reason | Recommendation |
|---|---|---|

## After (measured)
| File | Before % | After % | Remaining Missing |
|---|---|---|---|

## Next steps
- e.g. `mutmut run --paths-to-mutate <module path>`; recommended integration tests
```

## PHASE 6 — Summary and index

Write `05-summary.md`:

```markdown
<header>

## Result
- Tests written: N (X parametrized cases) · Test file: `tests/unit/<path>/test_<module>.py`
- Fixtures added: <name @ conftest path> | none
- Branch IDs covered: <list> · Intentionally not covered: <list + reasons>
- pytest: <final summary line> · Branch coverage: <before> -> <after measured | n/a>

## Bug-exposing tests
| Test | What it shows | Suggested action |
|---|---|---|

## Assumptions to confirm (each has a matching `# ASSUMPTION:` comment in the test file)
- none | list

## Recommended integration tests (not written)
- none | list

## Run
`pytest tests/unit/<path>/test_<module>.py -v --cov=<pkg> --cov-branch --cov-report=term-missing`
```

Append one row to `unit-test-prompt/test-files/INDEX.md` (create with header if absent):

```markdown
# Unit Test Runs — Index
| Run date | Module | Slug | Mode | Tests written | Branch cov before | Branch cov after | Bugs exposed | Open assumptions |
|---|---|---|---|---|---|---|---|---|
```

Chat output for PHASE 6 — short, no file contents pasted:

```markdown
## Done — <module path>
- Files: `<slug>/00…05`, `tests/unit/<path>/test_<module>.py`, `INDEX.md` (row appended)
- Tests: N · Branches: N of M · Coverage: <before> -> <after> · Bugs exposed: N · Assumptions: N
- pytest: <final summary line>
### Needs your attention
- <bugs / assumptions / blocked items | nothing>
```

## Forbidden anti-patterns

```python
process(order)                                          # no assertion
assert calculate_tax(100) == calculate_tax(100)         # tautology
expected = 100 * TAX_RATE                               # copies the implementation
assert result is not None                               # vague, alone
@patch("app.services.user_service.get_user")            # mocking the function under test
@patch("sqlalchemy.orm.Session")                        # wrong target — patch where looked up
create_engine("postgresql://...")                       # real I/O in unit test
def test_create_and_delete_user(): ...                  # two behaviours
repo = MagicMock()                                      # no spec
assert service._cache == {...}                          # private internals
with pytest.raises(Exception):                          # catch-all
# tests/unit/.../01-analysis.md                         # artifact in wrong place
# unit-test-prompt/test-files/test_x.py                 # test code in wrong place
```

## When unsure

- Cannot find an imported symbol -> search the workspace; if still missing, stop and ask.
- Correct behaviour is ambiguous -> test the current behaviour, add `# ASSUMPTION: ...`, list it
  in `05-summary.md`.
- Dependency not covered above -> treat as external, mock at the module boundary with `spec=`, note it.
- Meaningful only with a real DB -> unit-test the surrounding logic; recommend an integration test.
- Artifact folder cannot be created -> stop and report; never skip artifacts silently.

## Quality bar

A test is done only when it follows AAA, has a descriptive name, asserts a specific value or exact
exception, mocks every external dependency at the correct target with a spec, executes the real
logic under test, is deterministic, is independent, **passes when run**, and has a named mutation
that would make it fail.

A run is done only when all phase files exist under `unit-test-prompt/test-files/<slug>/`, the
test file exists under `tests/unit/`, pytest was actually executed, and `INDEX.md` has a new row.

A passing test is not evidence of correctness — it is evidence of no detected failure. Make the
tests try as hard as possible to find failures.