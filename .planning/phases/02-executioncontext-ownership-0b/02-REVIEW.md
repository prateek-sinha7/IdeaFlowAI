---
phase: 02-executioncontext-ownership-0b
reviewed: 2026-06-07T00:00:00Z
depth: standard
files_reviewed: 11
files_reviewed_list:
  - backend/agents/execution_engine/authz.py
  - backend/agents/execution_engine/context.py
  - backend/agents/execution_engine/engine.py
  - backend/tests/agents/test_execution_context.py
  - backend/tests/agents/test_migration_ledger.py
  - backend/tests/agents/test_parent_run_ownership.py
  - backend/tests/agents/test_phase3_cutover_verify.py
  - backend/tests/agents/test_phase4_build_loop.py
  - backend/tests/agents/test_phase5_revision_validation.py
  - backend/tests/unit/test_agent_input_event.py
  - specs/003-workflow-engine-decoupling/migration-ledger.md
findings:
  critical: 2
  warning: 3
  info: 4
  total: 9
status: issues_found
---

# Phase 02: Code Review Report — ExecutionContext + Ownership (0B)

**Reviewed:** 2026-06-07T00:00:00Z
**Depth:** standard
**Files Reviewed:** 11
**Status:** issues_found

## Summary

Phase 0B delivers three changes: (1) per-run state lifted off the singleton into `ExecutionContext`, (2) `assert_owns` ownership gate for cross-owner parent seeding, and (3) behavior proven unchanged by the characterization suite.

The state lift (`context.py`) is clean and correct. `authz.py` is correct and pure. The wiring in `engine.py` has two security-relevant issues: the ownership check has a conditional bypass path (the check is only reached when `existing_html` is truthy — a client can supply `parent_run_id` with no HTML block to skip both the check and the seeding, which is consistent but means the authz guard's coverage guarantee does not extend to the presence of the parameter itself), and `_derive_parent_owner` always returns the caller's own identity, making the guard a no-op in all real-world 0B invocations. Additionally, a dead timeout path in `_run_agent` would crash if reactivated. Three quality/test issues round out the report.

---

## Critical Issues

### CR-01: Ownership check bypassed when `existing_html` is absent — cross-owner `parent_run_id` is accepted without authorization

**File:** `backend/agents/execution_engine/engine.py:555-602`

**Issue:** The `assert_owns` call at line 598 is nested inside `if existing_html:` (line 557), which in turn is inside `if pipeline_type == "prototype_revision":` (line 555). When a `prototype_revision` request supplies a `parent_run_id` (e.g. from a malicious or misbehaving client) **without** the `=== EXISTING PROTOTYPE HTML ===` block, neither the ownership check nor the seeding block executes. The `parent_run_id` is stored on `ectx.parent_run_id` (line 490) without any authorization check.

In 0B the seeding itself is also gated by the same `if existing_html:` condition, so no files are actually copied across an owner boundary in the no-HTML path. This means the impact is currently limited — a cross-owner `parent_run_id` with no HTML causes no data leakage in 0B. However, the design contract says `assert_owns` is the hard gate for the `parent_run_id` parameter; future code that reads `ectx.parent_run_id` (e.g. Phase 5 store lookups) could operate on an unvalidated cross-owner ID.

The ownership check should be moved up to guard the `parent_run_id` parameter unconditionally whenever it is set, regardless of whether `existing_html` is present:

```python
# Immediately after ectx is constructed (before the prototype_revision block):
if parent_run_id is not None:
    _parent_owner = self._derive_parent_owner(user_id, parent_run_id)
    assert_owns(
        owner_id=ectx.owner_id,
        parent_run_id=parent_run_id,
        parent_owner_id=_parent_owner,
    )
```

This keeps the check unconditional on the parameter and ensures `ectx.parent_run_id` is only ever populated with an authorized value.

---

### CR-02: `_derive_parent_owner` always returns the caller's own identity — `assert_owns` is a no-op in all real 0B invocations

**File:** `backend/agents/execution_engine/engine.py:2551-2565`

**Issue:** `_derive_parent_owner(user_id, parent_run_id)` returns `user_id or "anon"` — the same value assigned to `ectx.owner_id`. Therefore `assert_owns(owner_id, parent_run_id, parent_owner_id)` is always called as `assert_owns("alice", ..., "alice")` (same-owner match) for every real production invocation, and the cross-owner denial path can never be reached without test-level monkey-patching.

This is explicitly documented as the Phase 0B by-convention design (D-06), with Phase 5 AUTHZ-02 designated to replace it with a real store lookup. The authz.py docstring, engine comment at line 597, and `_derive_parent_owner` docstring all acknowledge this. However, the consequence must be stated clearly for downstream phases: **the L16 ownership gate is structurally wired but provides zero enforcement in 0B production code**. Any user who knows another user's `parent_run_id` can supply it and pass the ownership check today, because the derived owner is always their own identity.

The migration-ledger marks L16 as `☑` and the test suite verifies the check fires correctly when `_derive_parent_owner` is overridden. The concern is that the `☑` status implies enforcement that does not yet exist in production. Phase 5 AUTHZ-02 must land before L16 provides real protection.

**Minimum required action:** Add a prominent warning comment at the `assert_owns` call site in `execute()` (or in `_derive_parent_owner`) stating that the check is currently unconditionally same-owner and is not a security boundary until Phase 5 AUTHZ-02 lands. Consider also adding a direct test assertion that verifies `_derive_parent_owner` returns `ectx.owner_id` (making the by-convention nature explicit in the characterization suite rather than only discoverable by code reading).

---

## Warnings

### WR-01: Timeout crash path — `agent_timeout` is `None` but used with `%.0f` and `:.0f` format specifiers

**File:** `backend/agents/execution_engine/engine.py:1254,1322-1342`

**Issue:** `agent_timeout` is assigned `None` at line 1254 with an explicit comment that per-agent timeouts are disabled. If `timed_out` ever becomes `True` (the only path is `asyncio.TimeoutError` from `asyncio.timeout(None)`, which can never fire), both the logger call and the f-string format would crash:

- Line 1324: `logger.warning("... %.0fs ...", spec.id, agent_timeout)` → `TypeError: a float is required`
- Line 1342: `f"Agent timed out after {agent_timeout:.0f}s"` → `ValueError: unsupported format character`

`asyncio.timeout(None)` is documented as a no-op deadline, so this is currently dead code. However, if a developer re-enables the timeout (e.g. sets `agent_timeout` to a real value), the surrounding error-handling code will crash before the fallback logic runs, turning a recoverable timeout into an unhandled exception. The dead code should either be removed or the format specifiers corrected to handle `None`.

**Fix:**
```python
# Line 1254 — if timeout is ever re-enabled, pass a float:
agent_timeout = None  # disabled
...
if timed_out:
    timeout_label = f"{agent_timeout:.0f}s" if agent_timeout is not None else "unknown"
    logger.warning("Agent %s timed out after %s", spec.id, timeout_label)
    ...
    yield {
        "type": "agent_error",
        "data": {
            "agent_id": spec.id,
            "error": f"Agent timed out after {timeout_label} — using best available output",
            "recoverable": True,
        },
    }
```

---

### WR-02: Stale docstring in `test_agent_input_event.py` documents incorrect event ordering

**File:** `backend/tests/unit/test_agent_input_event.py:4`

**Issue:** The module docstring states "agent_input event is emitted for every agent before agent_start". The actual implementation in `_run_agent` yields `agent_start` first (line 1166) and then `agent_input` (line 1182). The docstring describes the opposite ordering. No test in the file actually asserts on event ordering, so this is a documentation bug rather than a test-reliability issue — but misleading docstrings in a security-relevant test module actively mislead future reviewers about what is guaranteed.

**Fix:** Correct the docstring to match the actual implementation:

```python
"""T047 — Unit tests for the agent_input WS event (Phase 3 / FR-015).

Tests:
  - agent_input event is emitted for every agent (after agent_start)
  ...
"""
```

And optionally add an ordering assertion to the end-to-end tests in `test_phase3_cutover_verify.py`:

```python
types = [ev["type"] for ev in events]
start_idx = types.index("agent_start")
input_idx = types.index("agent_input")
assert start_idx < input_idx, "agent_start must precede agent_input"
```

---

### WR-03: `ectx.accumulated_outputs` field is declared but never read or written in `engine.py`

**File:** `backend/agents/execution_engine/context.py:85`, `backend/agents/execution_engine/engine.py:878`

**Issue:** `ExecutionContext` declares `accumulated_outputs: dict[str, str] = field(default_factory=dict)` (context.py line 85). The engine uses a separate local `accumulated_outputs: dict[str, str] = {}` (engine.py line 878). The two are never synchronized — `ectx.accumulated_outputs` is populated by no code path in the reviewed implementation.

This is acknowledged in the migration ledger as L15 ("sanctioned temporary mirror — removed in Phase 1B"). However, the field's presence in `ExecutionContext` creates a semantic trap: code reading `ectx.accumulated_outputs` to query agent outputs (e.g. in a future capability or test) will always see an empty dict, silently returning incorrect results. The field is also included in `test_execution_context.py` as part of the required empty-container defaults, cementing the illusion that it is operative state.

Until Phase 1B removes it, the field should carry an explicit deprecation comment in `context.py` making its non-operative status clear, and `test_execution_context.py` should note it as a sanctioned mirror:

```python
# context.py — accumulated_outputs field
# SANCTIONED DEAD FIELD (L15): the live map is the local dict in execute().
# Removed in Phase 1B per INV-3/migration-ledger L15.
accumulated_outputs: dict[str, str] = field(default_factory=dict)
```

---

## Info

### IN-01: Redundant `import json` inside `_log_event` — `json` already imported at module level

**File:** `backend/agents/execution_engine/engine.py:61`

**Issue:** `_log_event` performs `import json as _json` on every call (line 61), despite `json` already being imported at module scope (line 24). Python caches module imports in `sys.modules`, so there is no correctness issue, but the per-call import is unnecessary noise and slightly misleading (suggests the function is self-contained in a way it isn't).

**Fix:** Remove the local import and use the module-level `json` directly:

```python
# Remove line 61: import json as _json
# Change line 74:
    logger.info("LIFECYCLE %s", json.dumps(entry))
```

---

### IN-02: `open()` without context manager in import-boundary test

**File:** `backend/tests/agents/test_execution_context.py:80`

**Issue:** `src = open(mod.__file__, encoding="utf-8").read()` leaves the file handle unclosed until garbage collection. On CPython with reference counting this is deterministic, but on other runtimes (PyPy, GraalPy) or in test isolation contexts with mocked filesystems it is a resource leak.

**Fix:**
```python
with open(mod.__file__, encoding="utf-8") as fh:
    src = fh.read()
```

---

### IN-03: Import-boundary offender check uses overly broad `"engine" in ln` token

**File:** `backend/tests/agents/test_execution_context.py:90`

**Issue:** The offender filter in `test_module_imports_no_legacy_factory_or_engine_internals` includes the condition `"engine" in ln`, which would match any import line containing the substring "engine" — including future stdlib or third-party imports whose names coincidentally contain that string. The plan's acceptance grep (`from agents\\.factory|execution_engine\\.engine`) is more precise.

**Fix:** Replace the broad `"engine" in ln` condition with the precise pattern from the plan:

```python
offenders = [
    ln
    for ln in import_lines
    if "agents.factory" in ln or "execution_engine.engine" in ln
]
```

---

### IN-04: `_parse_rows` uses `is` identity comparison on strings in ledger parser

**File:** `backend/tests/agents/test_migration_ledger.py:85`

**Issue:** Line 85 uses `c is status or c == status` to find the index of the status cell. The `is` identity check on strings is an implementation detail (CPython interns small/interned strings but makes no guarantee for dynamically constructed strings like those produced by `.strip().replace(...)`). The `== status` fallback makes this work correctly in practice, but the `is` check adds confusion and could theoretically produce incorrect `max()` results if two distinct cell strings are equal but at different indices.

**Fix:** Remove the `is` arm and use only value equality:

```python
status_idx = max(i for i, c in enumerate(cells) if c == status)
```

---

_Reviewed: 2026-06-07T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
