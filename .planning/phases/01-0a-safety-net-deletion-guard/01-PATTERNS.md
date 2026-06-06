# Phase 1: [0A] Safety Net + Deletion Guard - Pattern Map

**Mapped:** 2026-06-06
**Files analyzed:** 8 (5 new test modules + golden dir, 3 modified config/CI)
**Analogs found:** 8 / 8

This phase adds **tests + CI config only** — no runtime code. Every new file has a strong
in-repo analog: the existing offline characterization-style suites (`test_phase3/4/5_*.py`)
and the existing config/CI blocks. The keystone is `tests/agents/_scripted_model.py::_drive()`,
which already runs `ExecutionEngine.execute()` end-to-end offline and returns ordered event
dicts — the exact SAFE-02 capture mechanism.

> Path note: `pyproject.toml` declares `testpaths = ["tests"]` and `python_files = ["test_*.py"]`,
> so any `tests/agents/test_*.py` is auto-collected. **CI does not run `tests/agents` today**
> (`backend:test` runs only `tests/unit`) — D-16/D-17 wire it in explicitly.

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `backend/tests/agents/test_characterization_<pipeline>.py` (×5) | test (characterization) | event-driven capture + byte-snapshot | `tests/agents/test_phase3_cutover_verify.py` (`TestNewEngineEventVocabulary`) + `test_phase4_build_loop.py` | exact |
| `backend/tests/agents/characterization/golden/` (+ `_normalize()` helper) | test fixture | snapshot/transform | `_DOCUMENTED_EVENT_TYPES` / `_REQUIRED_DATA_KEYS` contract dicts in `test_phase3_cutover_verify.py` (lines 182-225) | role-match |
| `backend/tests/agents/_scripted_model.py` (extend `_scripts_for`) | test harness | event-driven driver | the file itself (D-01/D-02 — extend, don't fork) | exact (self) |
| `backend/tests/agents/test_migration_ledger.py` | test (CI guard) | file-I/O + grep | no in-repo analog (new ratchet pattern) | no analog |
| `backend/tests/agents/test_banned_patterns.py` | test (CI guard) | grep | no in-repo analog (new ratchet pattern) | no analog |
| `specs/003-workflow-engine-decoupling/migration-ledger.md` | config (SoT doc) | static data | plan.md §31 ledger table (lines 1002-1023) | exact (mirror) |
| `backend/pyproject.toml` (`[tool.importlinter]` + `[tool.vulture]`) | config | static | existing `[tool.ruff]` + `[tool.pytest.ini_options]` blocks | exact |
| `backend/requirements-dev.txt` (add import-linter, vulture) | config | static | existing ruff/pyright/pre-commit pins | exact |
| `.gitlab-ci.yml` (lint gates + `backend:characterization` job) | config (CI) | request-response | existing `backend:lint` + `backend:test` jobs | exact |

---

## Shared Patterns (apply to ALL characterization tests)

### S1. The offline driver — the SAFE-02 capture mechanism
**Source:** `backend/tests/agents/_scripted_model.py` (lines 271-385)
**Apply to:** every `test_characterization_<pipeline>.py`

`_drive(pipeline_type, "new")` runs the public `engine.execute()` end-to-end offline (no
network/Bedrock/DB) and returns the ordered list of yielded engine event dicts — the real
outbound WS vocabulary. It already installs every neutralizer needed (scripted `ctx.model`
per agent, planner→PROCEED, `ALWAYS_CLARIFY=False`, no-op `ArtifactStore.store`, no-op
`_run_review_gate`, temp `RUNS_ROOT`, unique `run_id`, `od_context` for prototype/od_prototype).

Canonical usage (from `test_phase3_cutover_verify.py:40` + `:235`):
```python
from tests.agents._scripted_model import ScriptedFakeChatModel, _ScriptedTurn, _drive

@pytest.mark.asyncio
async def test_...(self) -> None:
    events = await _drive("prototype", "new")
    assert events, "prototype build produced no events"
    seen_types = {e.get("type") for e in events}
```

**Adaptation:** call `_drive(<pipeline>)` once per pipeline, then snapshot. Do NOT rebuild a
harness (D-01). For the deliverable byte-snapshot (kind a, D-05) you need the produced file
off disk — see S4 for reading the sandbox path the driver wrote to.

### S2. Extend `_scripts_for`, don't fork `_drive`
**Source:** `_scripted_model.py::_scripts_for(agent_id)` (lines 166-263)
**Apply to:** D-02 — pipelines whose agents aren't yet scripted

`_scripts_for` is a per-`agent_id` registry returning `list[_ScriptedTurn]`. It already
covers `user_stories` text agents, `prototype-*` (specify/plan/build/validate),
`prototype-revision-agent`, `app-code-generator`, and the `app_builder` text agents. For a
new characterization pipeline (e.g. `ppt`/`od_ppt`, the chosen code-gen pipeline), **add
branches here** keyed by that pipeline's agent ids (from `agents/registry.py PIPELINE_AGENTS`).
Pattern for a text agent vs a tool-emitting agent:
```python
# text-only agent → one turn, text + usage, no tool calls
return [_ScriptedTurn(texts=[f"{agent_id} output line one. ", "line two."], usage=(12, 7))]

# file-writing agent → write_file tool call + final text
def mk(p, c):
    return ("write_file", _j.dumps({"file_path": p, "content": c}), f"c_{p}")
return [
    _ScriptedTurn(texts=["Generating. "], tool_calls=[mk("src/app.py", "print('hi')\n")], usage=(60, 25)),
    _ScriptedTurn(texts=["done."], usage=(10, 5)),
]
```
The five pipeline families to cover (per ROADMAP + D-02): `prototype`, `od_prototype`,
`prototype_revision`, `ppt`/`od_ppt`, one code-gen (`app_builder`). Confirmed pipeline keys
live in `agents/registry.py` (`ppt`, `od_ppt`, `prototype`, `prototype_revision`, `app_builder`, …)
and `agents/loader.py SUPPORTED_PIPELINE_TYPES` (lines 29-40). **Note:** `_drive` only seeds
`od_context` for `("prototype","od_prototype")` (line 356) — if `od_ppt` needs injects, extend
that block too.

### S3. The event-contract dicts — copy the structure for `_normalize()` / event snapshots
**Source:** `test_phase3_cutover_verify.py` — `_DOCUMENTED_EVENT_TYPES` (lines 182-207) +
`_REQUIRED_DATA_KEYS` (lines 212-225)
**Apply to:** the semantic event snapshot (kind b, D-05) + `_normalize()` field list (D-06)

These two module-level constants ARE the existing semantic-event contract. The event snapshot
(D-05b) asserts type/order/required-fields; `_REQUIRED_DATA_KEYS` is the authoritative
required-fields-per-type map to assert against. The volatile fields `_normalize()` must strip
(D-06) are exactly the keys NOT in `_REQUIRED_DATA_KEYS` plus the known-volatile ones:
`timestamp`, `usage_metadata`/token counts, `duration`, generated ids, streamed-chunk
boundaries. The monotonic `seq` is asserted **contiguous**, not by value (D-06).
```python
_DOCUMENTED_EVENT_TYPES = frozenset({"workflow_validated","pipeline_start","agent_start",
    "agent_chunk","tool_call","tool_result","task_progress","task_loop_progress",
    "agent_complete","pipeline_complete", ...})
_REQUIRED_DATA_KEYS = {
    "agent_start": {"agent_id","name","role","icon","index","total"},
    "agent_complete": {"agent_id","name","duration","output_length",
                       "input_tokens","output_tokens","total_tokens"},  # ← duration/tokens = volatile, normalize out
    ...
}
```
Existing subset-assertion idiom to reuse (lines 247-257):
```python
for ev in events:
    required = _REQUIRED_DATA_KEYS.get(ev.get("type"))
    if required is None: continue
    missing = required - set(ev.get("data", {}).keys())
    assert not missing, f"event '{ev['type']}' dropped required keys {sorted(missing)}"
```

### S4. Reading deliverables off the sandbox disk (for byte-snapshots)
**Source:** `test_phase4_build_loop.py` — `RunSandbox.read(...)` (lines 294-303) and
`sandbox.path_for("prototype.html")` (line 719)
**Apply to:** D-05a deliverable byte-snapshot

```python
from app.agents.sandbox import RunSandbox
final_html = sandbox.read("prototype.html") or ""        # text deliverable
html_path  = sandbox.path_for("prototype.html")          # Path for static_check/render_check
```
For code-gen deliverables the engine uses `serialize_sandbox_deliverable()` (the `filename:`-block
format). `_drive` uses a fresh temp `RUNS_ROOT` per run; if a test needs the on-disk file it
should drive the loop with an explicit sandbox like `test_phase4` does, or read the
`pipeline_complete` event's `final_output` (in `_REQUIRED_DATA_KEYS["pipeline_complete"]`) for
the byte-snapshot when output is captured in the event stream.

### S5. Offline = unmarked (no `requires_api_key`)
**Source:** `pyproject.toml` markers (lines 13-15) + D-07
All characterization tests must be **offline and unmarked** so they run in CI. The only marker
in the project is `requires_api_key` (live LLM) — characterization tests must NOT carry it.

---

## Pattern Assignments

### `backend/tests/agents/test_characterization_<pipeline>.py` (×5) — test, event-driven + byte-snapshot

**Analog:** `test_phase3_cutover_verify.py::TestNewEngineEventVocabulary` (lines 228-296) +
`test_phase4_build_loop.py::test_event_vocabulary_matches_pre_phase4_prototype_set` (lines 489-518)

**Imports pattern** (from `test_phase3_cutover_verify.py:31-40`):
```python
from __future__ import annotations
import json
import pytest
from tests.agents._scripted_model import ScriptedFakeChatModel, _ScriptedTurn, _drive
```

**Module-docstring convention:** every existing `test_phaseN_*.py` opens with a substantial
docstring stating what contract it locks and that it "survives the Phase-7 deletion." Mirror
this — state the 003 SAFE-0x requirement + that it is the characterization baseline.

**Core capture+snapshot pattern** (adapt `test_phase3:234-257`):
```python
@pytest.mark.asyncio
@pytest.mark.parametrize("pipeline_type", ["prototype", "od_prototype",
                                           "prototype_revision", "od_ppt", "app_builder"])
async def test_event_snapshot(self, pipeline_type: str) -> None:
    events = await _drive(pipeline_type)
    normalized = _normalize(events)          # strip volatile fields (D-06)
    golden = _load_golden(f"{pipeline_type}.events.json")
    assert normalized == golden              # full semantic snapshot (D-05b)
```
**`--snapshot-update` flag** (D-07): gate regeneration behind an env var, e.g.
`if os.environ.get("SNAPSHOT_UPDATE"): _write_golden(...)` — write the golden then assert.

**Deliverable byte-snapshot** (D-05a): read the produced file (S4) and assert byte-for-byte
against `golden/<pipeline>.<ext>` where output is deterministic; rely on the event snapshot
(text-drift-robust) for the rest (per `<specifics>`: INV-3 semantic parity, not pure bytes).
The captured deliverable bytes MUST be non-empty — assert `len(golden_bytes) > 0` before/at
byte-equality so a zero-byte deliverable cannot pass vacuously.

**Naming (D-03):** use `test_characterization_<pipeline>.py`. Do NOT collide with the existing
`test_phaseN_*.py` (002-deepagents numbering — unrelated to 003's `[0A]…[6]`).

---

### `backend/tests/agents/characterization/golden/` + `_normalize()` helper — test fixture

**Analog:** `_REQUIRED_DATA_KEYS` / `_DOCUMENTED_EVENT_TYPES` (S3) define what `_normalize()` keeps.

**Layout (Claude's discretion, within D-06):**
```
backend/tests/agents/characterization/
├── __init__.py
├── _normalize.py            # _normalize(events) + VOLATILE_SENTINEL + _load_golden/_write_golden helpers
└── golden/
    ├── prototype.events.json        # normalized semantic event snapshot
    ├── prototype.html               # deliverable byte-snapshot (deterministic)
    ├── od_ppt.events.json
    ├── app_builder.events.json
    └── ...
```

**`_normalize()` contract (D-06)** — strip/normalize these volatile fields per event `data`:
- `timestamp`, `duration`, `*_tokens` / `usage_metadata` (token+usage counts)
- generated ids (run_id, artifact-id, call ids), streamed-text chunk boundaries (coalesce
  `agent_chunk` text or drop per-chunk granularity)
- assert per-run `seq` **contiguous** (no gaps), do not pin absolute values
Keep: event `type`, order, and the `_REQUIRED_DATA_KEYS` keys. Volatile-but-required keys
(duration/tokens) keep their KEY but get their VALUE replaced by the named constant
`VOLATILE_SENTINEL = "<normalized>"` (exported from `_normalize.py`) — single-sourced, not
inlined per call site.

---

### `backend/tests/agents/test_migration_ledger.py` — test (CI ratchet), file-I/O + grep

**Analog:** none in-repo (new pattern). Ground against: ledger SoT
`specs/003-workflow-engine-decoupling/migration-ledger.md` + the path-resolution idiom in
`_scripted_model.py:49` (`Path(__file__).resolve().parents[2]` → backend root).

**Pattern to author (D-09/D-10):**
```python
from __future__ import annotations
import re, subprocess
from pathlib import Path
import pytest

_REPO = Path(__file__).resolve().parents[3]          # repo root (tests/agents → backend → repo)
_LEDGER = _REPO / "specs/003-workflow-engine-decoupling/migration-ledger.md"
_BACKEND = _REPO / "backend"

def _checked_rows() -> list[tuple[str, str | None]]:
    """Parse markdown table rows; return (item_id, grep_pattern) for ☑ rows ONLY.
    CHECK-rows (gate cell is a CHECK / test: / metacharacter-free prose, not a grep
    pattern) are yielded as (item, None) so the parametrized test skips them."""
    rows = []
    for line in _LEDGER.read_text().splitlines():
        if not line.startswith("|") or "Status" in line or "---" in line: continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        # columns: Item | Legacy | New home | Phase | Deletion gate (grep / CHECK) | Status
        if len(cells) >= 6 and "☑" in cells[-1]:
            gate = cells[-2]
            pattern = None if _is_check_gate(gate) else gate   # CHECK rows → None
            rows.append((cells[0], pattern))
    return rows

@pytest.mark.parametrize("item,pattern", _checked_rows() or [("__none__", None)])
def test_deleted_pattern_absent_from_backend(item, pattern):
    if pattern is None:
        pytest.skip("no ☑ grep rows yet — green/empty in Phase 1 (D-10), or a CHECK-row gate")
    res = subprocess.run(["grep", "-rnE", pattern, str(_BACKEND), "--include=*.py"],
                         capture_output=True, text=True)
    assert res.returncode != 0, f"{item}: banned pattern still present:\n{res.stdout}"
```
**Phase-1 state (D-10):** all rows `☐` → the parametrize is empty → guard is green/empty. As
later phases flip rows to `☑`, the pattern becomes a permanent ratchet. CHECK-rows (L16/F4/F5)
are recognized via their gate-cell marker (`CHECK`/`test:`/metacharacter-free prose) and
yielded as `(item, None)` → skipped (their assertion lives in a dedicated test, not the grep
ratchet).

---

### `backend/tests/agents/test_banned_patterns.py` — test (CI ratchet), grep

**Analog:** none in-repo. Allow-list anchor: `app/agents/deep_agent_runner.py:53`
(`from deepagents import create_deep_agent`) and `:240` (`self._graph = create_deep_agent(`)
— the ONE sanctioned call site (verified). INV-13/R15.

**Pattern (D-14/D-15):**
```python
_ALLOWED_CREATE_DEEP_AGENT = {"app/agents/deep_agent_runner.py"}  # the langchain_deepagents adapter

_HARD_BANS = {
    "hand_rolled_deep_agent_class": r"class\s+DeepAgent\b",      # zero matches expected — see note
    "hand_rolled_deep_agent_fn":    r"def\s+deep_agent\b",
    "local_deepagents_module":      None,                        # assert no NEW deepagents/ pkg under our src
    "bespoke_agent_loop":           r"for\s+_\s+in\s+range\(\s*max_iterations",
}
# create_deep_agent allowed ONLY in the adapter file
# INV-1 reservation (if pipeline_type == / spec.id ==) → WARN-ONLY in Phase 1 (still in engine.py);
# becomes hard-fail in Phase 7 when L7 deletes. (D-15)
```
- **VERIFIED ABSENT — no legacy `deep_agent.py`:** the legacy `app/agents/deep_agent.py`
  (with `class DeepAgent` / `def deep_agent`) was **removed in the 002 migration** and does
  NOT exist today. Confirm it is absent before coding. Therefore do **NOT** add an allow-list
  entry for `app/agents/deep_agent.py` and do **NOT** scope the grep to exclude it — there is
  nothing to exclude. The `class DeepAgent` / `def deep_agent` hard-bans MUST return **zero
  matches** on the current tree (no allow-list needed). Prove the gate is non-vacuous by
  INJECTING a known-bad fixture (write `class DeepAgent:` into a `tmp_path` and assert the
  scanner reports a violation) — NOT by allow-listing a (non-existent) legacy file.
- Keep the deepagents allow-list MINIMAL: the single real `from deepagents import create_deep_agent`
  site in `app/agents/deep_agent_runner.py` is the ONLY sanctioned import — nothing else.
- INV-1 (`if pipeline_type ==` / `spec.id ==`) is **warn-only/documented** in Phase 1 (it
  still lives in `engine.py`); hard-fail deferred to Phase 7 (D-15, ROADMAP `<deferred>`).

---

### `specs/003-workflow-engine-decoupling/migration-ledger.md` — config (single source of truth)

**Analog:** plan.md §31 table (lines 1002-1023) — mirror it faithfully (D-08; user directive:
"nothing can be missed out").

**Required columns** (match §31 exactly so the parser in `test_migration_ledger.py` is stable):
`| Item | Legacy (file:line) | New home | Phase | Deletion gate (grep → 0 / check) | Status |`

**All rows to mirror** (every L#/F#/D# from §31, all start `☐` per D-10):
`L14, L16, D1` (Phase 0B) · `L13` (0C→2) · `L1, L2/L9, L3, L4/L8, L5, L6, L7, L10, L11, L12`
(Phase 2) · `L15` (1A→1B) · `F1, F2, F3, F4, F5` (Phase 3).
Copy each row's grep pattern verbatim from §31 (e.g. L1 → `_PROTOTYPE_PIPELINE_TYPES|_PPT_PIPELINE_TYPES`;
L7 → `spec.id == "prototype-build"`; F5 → `create_deep_agent` called only inside the adapter).
For CHECK-rows (L16 "cross-owner denial test passes", F4 "constitution-injected-in-prod test
passes", F5 "create_deep_agent called only inside the adapter"), write the gate cell as a CHECK
(literal `CHECK`/`test:` or metacharacter-free prose, NOT a grep pattern) so the parser yields
them as `(item, None)`.

---

### `backend/pyproject.toml` — config (add `[tool.importlinter]` + `[tool.vulture]`)

**Analog:** existing `[tool.ruff]` (lines 34-87) + `[tool.pytest.ini_options]` (lines 7-15) —
match the heavy-comment, rationale-first style (every block explains WHY).

**`[tool.importlinter]` (D-11/D-12 — scaffold green now, tighten later):**
```toml
[tool.importlinter]
root_package = "agents"

# Scaffold contract (D-12): holds on the CURRENT tree (kernel == engine.py) and is
# designed to TIGHTEN — never rewrite — when kernel.py + capabilities/base.py land
# (Phase 2/8). Intended final form documented inline: the kernel module must not
# import legacy factory/engine internals; it depends only on capability ports.
[[tool.importlinter.contracts]]
name = "kernel imports only capability ports (scaffold)"
type = "forbidden"
source_modules = ["agents.execution_engine.engine"]
forbidden_modules = []   # ← empty today (green); Phase 8 adds factory/engine-internals here
```
Pick `forbidden` vs `layers` at discretion (D-12 caveat: must satisfy tighten-don't-rewrite).
**Empty-`forbidden_modules` portability:** some import-linter versions reject an empty
`forbidden_modules = []`. If `lint-imports` errors, use a `layers`-type contract over the
current single-layer tree OR a documentation-only TOML comment block (no active forbidden rule
yet) — whichever keeps `lint-imports` exit 0 for the green scaffold (D-12).

**`[tool.vulture]` (D-13):**
```toml
[tool.vulture]
paths = ["app", "agents"]
min_confidence = 80
# Allow-list framework entrypoints (FastAPI routes, pytest fixtures, registry self-registration)
# via an in-repo whitelist file to avoid false positives. (Claude's discretion: pyproject vs CLI.)
exclude = ["alembic/versions", "tests"]
```

---

### `backend/requirements-dev.txt` — config (add import-linter, vulture)

**Analog:** existing pins (lines 24-39: `ruff==0.8.4`, `pyright==1.1.391`, `pre-commit==4.0.1`).
Match the style: a comment block explaining what the tool catches, then an **exact** pin
(file header: "pinned exactly … Bump deliberately, never with a range").
```python
# Import boundary enforcement (Ports & Adapters). Configured in pyproject.toml
# under [tool.importlinter]. Asserts the kernel depends only on capability ports,
# never legacy engine/factory internals. (003 §31 / D-11)
import-linter==2.1
# Dead-code / orphaned-function detection (the §31 "ruff / vulture" dead-code gate).
# Allow-listed to avoid false positives on framework entrypoints. (D-13)
vulture==2.14
```
(Pin to the latest exact versions at author time; the values above are placeholders — verify.
The CI verify installs `-r requirements-dev.txt` so it tests these exact pins, not unpinned tools.)

---

### `.gitlab-ci.yml` — config (CI: lint gates + `backend:characterization` job)

**Analog:** `backend:lint` (lines 28-41) + `backend:test` (lines 43-62). Match the `image:`,
`cache:` (`key: pip-py313`, `paths: [.pip-cache/]`), `before_script` pip-install, and the
`rules:` (`merge_request_event` OR `main`) of the existing backend jobs exactly.

**Lint stage additions (D-17)** — extend `backend:lint.script` (currently `cd backend && ruff check app/`):
```yaml
  before_script:
    - pip install --cache-dir .pip-cache -r backend/requirements.txt
    - pip install --cache-dir .pip-cache -r backend/requirements-dev.txt   # ← brings import-linter + vulture
  script:
    - cd backend && ruff check app/
    - cd backend && lint-imports                       # import-linter (reads pyproject [tool.importlinter])
    - cd backend && vulture app/ agents/               # dead-code scan (allow-listed)
```

**New test-stage job (D-17)** — clone the `backend:test` skeleton (same image/cache/rules), but
**offline** (no DB/API key needed) and run ONLY the 003 safety-net tests:
```yaml
backend:characterization:
  stage: test
  image: python:3.13-slim
  cache: { key: pip-py313, paths: [.pip-cache/] }
  variables:
    ENV: "test"
  before_script:
    - pip install --cache-dir .pip-cache -r backend/requirements.txt
  script:
    - cd backend && python -m pytest tests/agents/test_characterization_*.py
        tests/agents/test_migration_ledger.py tests/agents/test_banned_patterns.py -q
  rules:
    - if: $CI_PIPELINE_SOURCE == "merge_request_event"
    - if: $CI_COMMIT_BRANCH == "main"
```
> Critical (D-16): the existing `backend:test` runs only `tests/unit` — these `tests/agents`
> tests are NOT in CI today and MUST be wired in via this dedicated job. Keeping the ledger +
> banned-pattern tests in the **test** stage keeps them as hard ratchets.

---

## No Analog Found

| File | Role | Data Flow | Reason / Mitigation |
|------|------|-----------|---------------------|
| `test_migration_ledger.py` | test (CI guard) | file-I/O + grep | No grep-the-tree ratchet test exists yet. Ground against §31/ledger SoT + the `_scripted_model.py:49` path-root idiom. New pattern this phase establishes. |
| `test_banned_patterns.py` | test (CI guard) | grep | Same — first banned-pattern ratchet. Allow-list anchored on the verified `deep_agent_runner.py:53/240` call site (no legacy `deep_agent.py` exists). |

---

## Metadata

**Analog search scope:** `backend/tests/agents/`, `backend/pyproject.toml`,
`backend/requirements-dev.txt`, `.gitlab-ci.yml`, `backend/agents/registry.py`,
`backend/agents/loader.py`, `backend/app/agents/deep_agent_runner.py`, `plan.md §31`.
**Files scanned:** ~12 (read in full or targeted).
**Pattern extraction date:** 2026-06-06
