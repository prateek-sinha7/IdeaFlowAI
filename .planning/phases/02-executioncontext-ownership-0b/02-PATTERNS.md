# Phase 2: ExecutionContext + Ownership [0B] - Pattern Map

**Mapped:** 2026-06-07
**Files analyzed:** 3 (2 new, 1 modified)
**Analogs found:** 3 / 3

> Brownfield REFACTOR phase: pure per-run state relocation + one security point-fix
> (L16 ownership check) + one dead-code deletion (D1). No RESEARCH.md — file list
> derived from 02-CONTEXT.md + 02-SPEC.md. All line numbers below are CURRENT (file
> has grown to 2643 lines; some CONTEXT refs were stale by a few lines — use these).

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `backend/agents/execution_engine/context.py` | model (per-run value object / state container) | transform (holds run state, no I/O) | `backend/agents/factory.py::AgentContext` (`@dataclass`, lines 30-55) | exact (same idiom, distinct level) |
| `backend/agents/execution_engine/authz.py` | utility (small pure helper module) | request-response (assert/raise) | `backend/agents/execution_engine/state_machine.py` (module-level pure funcs) + `app/agents/types.py::TemplateMissingError` exception idiom | role-match |
| `backend/agents/execution_engine/engine.py` | controller/sequencer (modified) | event-driven (async generator) | itself — relocate `self._*` → threaded `ctx` | n/a (in-place refactor) |

## Pattern Assignments

### `backend/agents/execution_engine/context.py` (NEW — per-run value object)

**Analog:** `backend/agents/factory.py::AgentContext` (`agents/factory.py:30-55`).
This is the canonical engine-adjacent dataclass idiom. **Do NOT conflate**: the
factory's `AgentContext` is per-AGENT (rebuilt for every `create_runner` call); the
new `ExecutionContext` is per-RUN (built once in `execute()`, threaded down). They
coexist — `_run_validation_fix_loop` already has a param named `ctx: AgentContext`
(`engine.py:1709`), so name the engine param distinctly or be explicit in signatures.

**Dataclass idiom to copy** (`agents/factory.py:13-55`):
```python
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AgentContext:
    """Runtime context passed to create_runner()."""

    user_request: str                          # required field first
    agent_outputs: dict[str, str] = field(default_factory=dict)
    attached_skills: list[dict] = field(default_factory=list)
    model: str | None = None                   # optional with default
    od_context: dict | None = None
    user_id: str | None = None
    run_id: str | None = None
```

**Conventions the new dataclass MUST replicate:**
- `from __future__ import annotations` at top (every module in this tree uses it).
- Plain mutable `@dataclass` (NOT frozen) — `AgentContext`, `WorkflowState`
  (`app/agents/types.py:60`), and the resolver dataclasses (`resolver.py:37-59`) are
  all mutable. The engine appends to `_completed_tasks` mid-run, so mutability is
  required here.
- `field(default_factory=...)` for mutable defaults (dict/list/set) — see
  `AgentContext:41-43` and `WorkflowState:75-78`. **Critical** for the `revision_*`
  set fields (`_revision_baseline_static: set[str] = set()` → `field(default_factory=set)`).
- Required fields first, then optional `x: T | None = None` / defaulted fields. Modern
  union syntax `str | None` (not `Optional[str]`), consistent with all four analogs.
- Inline `#` comments per field documenting purpose (heavily used in all analogs).
- `WorkflowState` (`app/agents/types.py:84-89`) shows the precedent for a
  `pipeline_run_id` / `parent_run_id` field pair on a run-state dataclass — mirror its
  naming (`run_id`, `parent_run_id`, `owner_id`).

**D-01 field set to lay down (and ONLY this set — INV-12, no speculative fields):**
run identity (`run_id`, `owner_id` from `user_id or "anon"` per D-04), migrated run
state (`od_context`, `completed_tasks`, `gate_agent_ids`, `parent_run_id`,
`checkpointer`, `current_task_block` [D-02 temp home], the `revision_*` group:
`original_html`, `instruction`, `baseline_static`, `baseline_console`), the
`accumulated_outputs` legacy mirror, `cancel_event`, `depth: int = 0`. Do NOT add
`plan`/`workspace`/`artifacts`/`budget`/`models` (types don't exist until later phases).

**Claude's discretion (per D-07/CONTEXT):** flat `revision_*` fields vs a nested
`RevisionState` value object — if nested, follow the same `@dataclass` + `field(default_factory=set)`
idiom; the `TokenUsage` dataclass (`app/agents/types.py:26-52`) is the precedent for a
small composable nested value object.

**Import-direction constraint (CONTEXT integration point):** `context.py` defines data
only — it must NOT import legacy factory/engine internals (keeps the Phase 1
import-linter kernel→ports scaffold green). Stdlib + `__future__` only is ideal.

---

### `backend/agents/execution_engine/authz.py` (NEW candidate — D-06 — tiny pure helper)

**Analog (module shape):** `backend/agents/execution_engine/state_machine.py:1-30` —
the established pattern for a small pure helper module in this package: module docstring,
`from __future__ import annotations`, `logging`, module-level frozenset constants, plain
free functions. Keep `authz.py` this lean so Phase 5's store-layer scoped-query helper
(AUTHZ-02) can absorb it as a **move, not a rewrite** (D-06 + INV-12).

**Analog (exception idiom):** `app/agents/types.py:58-61`:
```python
class TemplateMissingError(Exception):
    """Raised when an agent declares `injects` but the referenced template
    cannot be located. The ExecutionEngine catches this and halts ..."""
```
The codebase raises **plain stdlib `Exception` subclasses** (`TemplateMissingError`,
`AgentSpecError`) or bare `ValueError` (`sandbox.py:66,81` "path escapes run sandbox";
`engine.py:2156` "Revision instruction must not be empty"). There is **no** central
errors/exceptions module and no custom base error class. For the D-07 denial:
- `PermissionError` (a builtin) is the natural fit and is what CONTEXT/D-07 names as the
  example — it reads as a denial and a test can assert `pytest.raises(PermissionError)`.
- Discretion (D-07): any typed exception that propagates out of `execute()` works; if a
  named class is preferred, follow the `TemplateMissingError` idiom (subclass `Exception`,
  docstring states who raises and that it is NOT swallowed).

**Suggested helper shape (pure, no I/O, mechanical to relocate):**
```python
def assert_owns(owner_id: str, parent_run_id: str, parent_owner_id: str) -> None:
    """Raise if owner_id does not own parent_run_id. Pure check — no store access
    here in 0B (Phase 5 AUTHZ-02 relocates this into the scoped-query helper)."""
    if parent_owner_id != owner_id:
        raise PermissionError(
            f"owner {owner_id!r} may not seed from parent run {parent_run_id!r}"
        )
```
**Anonymous-principal constraint (SPEC line 74):** `owner_id` is a real principal
(`user_id or "anon"` in 0B), never `None` — the check compares strings, treat `"anon"`
as a real owner.

---

### `backend/agents/execution_engine/engine.py` (MODIFIED — relocate state, thread ctx)

**`__init__` — the immutability target** (`engine.py:403-406`):
```python
def __init__(self) -> None:
    self._resolver = WorkflowResolver()
    self._store = get_artifact_store()
    self._state_machine = get_state_machine()
```
After the refactor these three construction-time singletons are the ONLY instance
attributes; CTX-02/NFR-001 requires no per-run `self._*` write survives. Construct
`ExecutionContext` inside `execute()` and thread it; do not stash run state on `self`.

**Per-run state init block to LIFT** (`execute()` signature `:408`; init block
`:472-550`). Every `self._<x> = ...` below moves onto the ctx the planner constructs
right after `sandbox = RunSandbox(user_id or "anon", pipeline_run_id)` (`:472`):

| Current write site | Attribute | Notes |
|--------------------|-----------|-------|
| `:474` | `self._od_context = od_context` | flows engine → AgentContext per agent |
| `:475` | `self._user_id = user_id` | becomes `ctx.owner_id = user_id or "anon"` (D-04) |
| `:481` | `self._gate_agent_ids = gate_agent_ids` | read in `_should_gate:1904` |
| `:486` | `self._parent_run_id = parent_run_id` | read by post-revision fix-loop |
| `:503` | `self._checkpointer = await get_checkpointer()` | acquire stays identical; reference moves to ctx (do NOT close per-run — `:494-501` docstring; singleton) |
| `:517` | `self._completed_tasks: list[dict] = []` | appended `:1267`, read `:1285-1286`; MUST stay run-level (build loop calls `_run_agent` once per task — see `:505-516` rationale) |
| `:532,548,549,550` | `self._revision_original_html / _revision_instruction / _revision_baseline_static / _revision_baseline_console` | set defaults then conditionally populated `:554-644`; the `set[str] = set()` defaults need `field(default_factory=set)` on the dataclass |
| `:1536` | `self._current_task_block = self._extract_task_block(...)` | D-02 temp home on ctx; Phase 7 reclaims into `TaskLoopStrategy` — call out in SUMMARY |

**Checkpointer acquisition (unchanged)** — `app/agents/checkpointer.py:25` cached
process-wide singleton; `engine.py:502-503` does `from app.agents.checkpointer import
get_checkpointer; self._checkpointer = await get_checkpointer()`. Keep the `await
get_checkpointer()` call; only the *storage location* of the returned reference moves to
`ctx.checkpointer`.

**L16 ownership-check seam — insert BEFORE the graceful-degrade try** (`engine.py:583-610`):
```python
if parent_run_id:
    try:                                            # ← graceful-degrade try
        parent_sb = RunSandbox(user_id or "anon", parent_run_id)
        seeded: list[str] = []
        for _name in ("spec.md", "design.md", "tasks.md"):
            try:
                _content = parent_sb.read(_name)
            except Exception as _read_exc:          # noqa: BLE001
                logger.warning("... could not read parent %s (%s) — skipping", ...)
                continue
            ...
    except Exception as _seed_exc:                  # noqa: BLE001 — never break a revision
        logger.warning("... parent reference seeding ... failed (%s) ...", ...)
```
**D-07 fix:** the `assert_owns(...)` call goes ABOVE the `try` at `:583` so a cross-owner
`parent_run_id` raises `PermissionError` and is NOT swallowed (the broad `except
Exception` at `:605` currently swallows ANY failure → silent skip). Same-owner
missing/TTL-swept parents must STILL hit the graceful-degrade try and proceed. Cross-owner
is a brand-new path (no 0A snapshot exercises it) → raising is not a CTX-05 behavior change.
**Note (D-05):** `RunSandbox(user_id or "anon", parent_run_id)` keying is unchanged — the
L16 fix is about WHO may seed, not renaming disk dirs.

**The 6 read-site methods to thread `ctx` through** (D-03 — explicit param, no contextvars):

| Method | Line | Current self._ reads | Threading note |
|--------|------|----------------------|----------------|
| `_run_agent` | `1108` | `_user_id` (`:926` comment), `_completed_tasks` (`:1267,1285,1286`), `_od_context` (via `_build_context_message`) | add `ctx` param; many call sites |
| `_run_build_task_loop` | `1450` | writes `_current_task_block` (`:1536`); calls `_run_agent` once per task | thread `ctx` into the per-task `_run_agent` calls |
| `_run_validation_fix_loop` | `1706` | already takes `ctx: AgentContext` (`:1709`) — distinct from engine ctx; reads `_revision_baseline_*` via params already (`baseline_static` `:1717`) | DISAMBIGUATE: don't shadow the existing `ctx`; pass engine state explicitly or rename |
| `_should_gate` | `1890` | `getattr(self, "_gate_agent_ids", None)` (`:1904`) | replace with `ctx.gate_agent_ids` |
| `_build_context_message` | `2315` | `_od_context` (`:1507` comment region), `getattr(self, "_current_task_block", "")` (`:2480`) | add `ctx`; pure method, simplest thread |

`~28 references across these 6 methods + their call sites` (D-03 estimate). Use a single
explicit `ctx` parameter; `getattr(self, "_x", default)` reads (`:1904`, `:2480`) become
`ctx.x`.

**D1 — delete dead `_handle_revision`** (`engine.py:2138`, ledger range `:2138-2251`):
superseded by inline revision handling (`:551-644`), never reached. Delete the whole
method. Note it currently contains a `raise ValueError("Revision instruction must not be
empty.")` (`:2156`) — that validation is dead too; deletion is total.

## Shared Patterns

### Dataclass value-object idiom
**Source:** `agents/factory.py:30-55` (`AgentContext`), reinforced by
`app/agents/types.py:26-89` (`TokenUsage`, `WorkflowState`) and
`agents/execution_engine/resolver.py:37-59`.
**Apply to:** `context.py`.
- `from __future__ import annotations` + `from dataclasses import dataclass, field`
- mutable `@dataclass`; required fields first; `str | None = None` for optionals;
  `field(default_factory=dict|list|set)` for mutable defaults; per-field `#` comments.

### Exception / denial idiom
**Source:** `app/agents/types.py:58-61` (`TemplateMissingError(Exception)`);
`app/agents/sandbox.py:66,81` + `engine.py:2156` (`raise ValueError(...)`).
**Apply to:** `authz.py` denial (D-07).
- No central errors module — raise a stdlib exception (`PermissionError` recommended) or a
  small `Exception` subclass with a docstring stating who raises and that it propagates.

### Pure-helper-module shape
**Source:** `agents/execution_engine/state_machine.py:1-30`.
**Apply to:** `authz.py`.
- Module docstring, `from __future__ import annotations`, `logging`, module-level
  constants, plain free functions — no class needed; keep it relocatable (D-06 → Phase 5).

### Threading style (explicit ctx, no ambient state)
**Source:** the existing `_run_validation_fix_loop(*, ctx: AgentContext, ...)` keyword-only
signature (`engine.py:1706-1717`) — the precedent for passing a context object explicitly
rather than via `self`. Mirrors plan port signatures `run(step, ctx)` / `evaluate(step, ctx)`.
**Apply to:** all 6 read-site methods.

## No Analog Found

None. Every new file has a close in-repo analog (the project is mid-refactor toward exactly
this shape). The only genuinely new code is the cross-owner denial *path* (no 0A snapshot
exercises it) — but its idiom (raise a stdlib exception before a try/except) is well-precedented.

## Metadata

**Analog search scope:** `backend/agents/`, `backend/agents/execution_engine/`,
`backend/app/agents/`.
**Files scanned:** `factory.py`, `app/agents/types.py`, `resolver.py`, `state_machine.py`,
`sandbox.py`, `checkpointer.py`, `engine.py` (targeted ranges).
**Pattern extraction date:** 2026-06-07
**Commit scopes (backend/CLAUDE.md):** `engine` for `execution_engine/` (incl. new
`context.py`/`authz.py`), `tests` for the L16 denial test.
