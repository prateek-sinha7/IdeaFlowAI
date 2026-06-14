---
phase: 22-capability-surfacing-and-user-empowerment-universal-runtime
reviewed: 2026-06-14T00:00:00Z
depth: standard
files_reviewed: 20
files_reviewed_list:
  - backend/agents/workflows/compiler.py
  - backend/agents/workflows/plan.py
  - backend/agents/workflows/selections.py
  - backend/agents/factory.py
  - backend/agents/execution_engine/engine.py
  - backend/agents/capabilities/registry.py
  - backend/app/api/capabilities.py
  - backend/app/api/user_workflows.py
  - backend/app/api/websocket.py
  - backend/app/models/workflow.py
  - backend/alembic/versions/0022_workflow_run_deliverable_mimetype.py
  - backend/agents/capabilities/gates/security.py
  - backend/agents/capabilities/strategies/single_shot.py
  - frontend/src/components/workflow/AgentsPopup.tsx
  - frontend/src/components/workflow/AgentModelPicker.tsx
  - frontend/src/components/workflow/IdeaInputPage.tsx
  - frontend/src/components/preview/PreviewPanel.tsx
  - frontend/src/components/layout/DashboardLayout.tsx
  - frontend/src/lib/api.ts
  - frontend/src/types/index.ts
findings:
  critical: 2
  warning: 5
  info: 4
  total: 11
status: issues_found
---

# Phase 22: Code Review Report

**Reviewed:** 2026-06-14
**Depth:** standard
**Files Reviewed:** 20
**Status:** issues_found

## Summary

Reviewed the Phase 22 capability-surfacing + user-empowerment surface with an adversarial
focus on the `trust="user"` activation, the engine `_apply_selections` overlay, the compiler
WIRE materialization, migration 0022, and the FE composer/palette/preview.

**The CAP-03 trust gate itself is sound.** A smuggled `user_allowed=False` capability
(security gate, exec/spawn/secrets, powerful MCP server) is rejected at BOTH the SAVE
(`user_workflows._compile_selections_trust_user`) and LAUNCH
(`websocket._revalidate_selections_trust_user`) sites; the engine `_apply_selections` adds a
third defense-in-depth re-compile. IDOR resolves to 404 (`_owned`). The compiler's strict
step-key / nested-key rejection (`_ALLOWED_*`) is intact and fail-loud. Migration 0022 is
additive-only and reversible. The PreviewPanel generic HTML path preserves the
`sandbox="allow-scripts"` (no `allow-same-origin`) contract.

However, this surface has **two BLOCKERs** and several quality/faithfulness defects:

1. A selection-supplied **per-step model id bypasses the `ModelCatalog` allow-list**
   entirely (the exact cost-abuse / unknown-provider threat `_validate_model_overrides`
   exists to stop), reachable via a crafted WebSocket `run_pipeline` payload.
2. The end-to-end EMP-01 feature is **broken on the live FE path**: launch never sends
   `selections`, and the retry lever emits a shape the backend compiler rejects with a 422.

## Critical Issues

### CR-01: Selection-supplied per-step model id bypasses the ModelCatalog allow-list

**File:** `backend/app/api/websocket.py:1503-1537`, `backend/agents/execution_engine/engine.py:4582-4583`, `backend/agents/model_policy.py:95-110`
**Issue:** The launch path validates the separate `model_overrides` field against
`ModelCatalog.ids()` (`_validate_model_overrides`, the MODEL-03 chokepoint for threat
T-06-06: unknown-provider / cost-abuse / invalid-model-crash). But a per-step **model**
supplied via the `selections` map takes a completely different route that is **never**
catalog-validated:

- `selections.py::_synthesize_step` projects `{"model": {"model": <id>}}` onto the raw step.
- `compiler._compile_model_policy` accepts any string model id (no catalog check — and model
  is not a registered `(kind,name)`, so `_check_trust` does not apply either).
- `engine._apply_selections` sets `patch["model"] = user_step.model` (line 4582-4583).
- `model_policy.py:95-110` resolves tier-2 `step.model` and **explicitly skips** the
  `is_allowed` catalog check (only tier-3 `AgentSpec.model` is validated, and only when it
  wins). The id flows straight into `build_model(...)`.

`_revalidate_selections_trust_user` only checks capability *trust*, not model ids. A crafted
WebSocket `run_pipeline` payload (`selections: {"<agent>": {"model": "arbitrary-or-disallowed-id"}}`)
therefore reaches `build_model` with an unvalidated id — routing to an unintended/expensive
provider or crashing the run. This is reachable today (the WS handler accepts and applies
`selections`).

**Fix:** Validate selection-supplied model ids against the catalog at the same launch
chokepoint, before execute. In `_revalidate_selections_trust_user` (and the SAVE-side
`_compile_selections_trust_user`), after synthesis, walk the selections and reject any
`model` not in `ModelCatalog().ids()` — reusing the existing allow-list:
```python
from agents.capabilities.model_catalog import ModelCatalog
allowed = set(ModelCatalog().ids())
for aid, sel in (selections or {}).items():
    m = sel.get("model") if isinstance(sel, dict) else None
    if isinstance(m, str) and m not in allowed:
        return f"selection for {aid!r} requests model {m!r}, which is not an allowed model"
```
(Defense-in-depth: also make `model_policy.py` catalog-validate tier-2 `step.model` so the
kernel never trusts an unvalidated id regardless of caller.)

### CR-02: Retry lever produces a shape the backend rejects — save fails with 422

**File:** `frontend/src/components/workflow/AgentsPopup.tsx:1016-1021,1312-1319`, `backend/agents/workflows/selections.py:87-89`, `backend/agents/workflows/compiler.py:627-633`
**Issue:** The FE `StepSelection.retry` type is a bare `number` and the AdvancedExpander
emits `retry: 2` (confirmed by `AdvancedExpander.test.tsx:134` asserting `retry: 2`).
`selections.py::_synthesize_step` passes the value through verbatim
(`step["retry"] = retry`). The compiler's `_compile_retry_policy` then runs
`if not isinstance(raw_retry, dict): raise CompilerError("step 'retry' must be a mapping ...")`.
So any saved workflow with a Retry lever set fails `_compile_selections_trust_user` →
**HTTP 422 "Rejected selection"** at save, and would be rejected with `code=invalid_selection`
at launch. The retry lever is unusable end-to-end.

**Fix:** Reconcile the shapes. Either transform on the FE before sending —
`retry: { max_attempts: n }` — or coerce in `selections.py`:
```python
retry = sel.get("retry")
if retry is not None:
    step["retry"] = {"max_attempts": int(retry)} if isinstance(retry, (int, float)) else retry
```
Update the `StepSelection` type and the `AdvancedExpander.test.tsx` expectation accordingly.

## Warnings

### WR-01: Launch never sends `selections` — the entire EMP-01 overlay is dead on the live FE path

**File:** `frontend/src/components/workflow/IdeaInputPage.tsx:261-282`, `frontend/src/components/layout/DashboardLayout.tsx:666,693,1196-1197`
**Issue:** The backend launch plumbing is complete (`websocket.py` reads
`message_data.get("selections")`, re-validates trust=user, and `engine._apply_selections`
overlays it). But **no FE code ever puts `selections` into a `run_pipeline` payload**:
- `IdeaInputPage.handleRun` (261-282) only threads `gate_agent_ids` and `model_overrides`
  into `extraParams`; `selectionsRef.current` is used solely in `handleSaveWorkflow`.
- `DashboardLayout.savedComposition` is typed `{agentIds, modelOverrides}` (line 666) and
  `IdeaInputPage` is seeded with `initialAgentIds`/`initialModelOverrides` but **not**
  `initialSelections` (1196-1197). A grep confirms `selections` appears in the FE only in the
  save API type, the composer, and a test — never a launch payload.

Net effect: a user can compose Advanced levers and Save them, but launching (from scratch OR
from a saved workflow) silently applies none of them. The persisted `manifest_json`
selections never affect any run. This is a primary-feature gap, not just dead code.

**Fix:** (a) Thread `selectionsRef.current` into `handleRun`'s `extraParams` (mirroring
`model_overrides`); (b) carry `selections` on `savedComposition` and pass it as
`initialSelections` to `IdeaInputPage` / `AgentsPopup` so a launched saved workflow re-loads
and re-sends them. Add an e2e/integration test asserting the `run_pipeline` payload carries
`selections`.

### WR-02: `resume_run` drops `selections` — a restart-resumed run loses its user-composed levers

**File:** `backend/agents/execution_engine/engine.py:5114-5124`
**Issue:** `resume_run` rebuilds the run via `_execute_impl(...)` but never passes
`selections` (it reconstructs only `agents`/`pipeline_type`/`user_id`/etc. from the
`workflow_runs` row). The launch-time `selections` are not persisted on the run row either,
so after a backend restart a resumed run re-drives the **bare file-compiled plan** — the
user-selected validators/gates/model/retry that were active pre-crash silently vanish. (Not
a security issue: resume can only ever apply less privilege than the engineer authored.)

**Fix:** Persist the launch `selections` on the run (e.g. an additive nullable column or the
existing run JSON) and re-thread them through `resume_run → _execute_impl → _apply_selections`,
or document the resume-loses-selections limitation explicitly. Once CR-01/WR-01 land this
becomes a faithfulness defect on a real path.

### WR-03: `_apply_selections` degrades silently on a trust=user re-compile failure

**File:** `backend/agents/execution_engine/engine.py:4548-4560`
**Issue:** When the engine's defense-in-depth `trust="user"` re-compile raises, it logs a
warning and **proceeds with the unmodified plan** (`except Exception: ... return compiled`).
This is acceptable as a backstop ONLY because the WS layer is the authoritative gate — but it
swallows ALL exceptions (`BLE001`), including programmer errors (e.g. an
`AttributeError`/`TypeError` from a future refactor), masking real bugs and producing a run
that silently ignores the user's composition without any user-visible signal. If the WS gate
is ever bypassed (CR-01 demonstrates the selection surface is not fully gated), this becomes a
silent fail-open of the overlay.

**Fix:** Narrow the catch to `CompilerError` (the only expected rejection); let unexpected
exception types propagate (or surface a `selection_ignored` event) so the silent-drop is not
indefinitely invisible.

### WR-04: Selection-supplied model id is unvalidated at SAVE too (orphan-config + later launch surprise)

**File:** `backend/app/api/user_workflows.py:150-190`
**Issue:** `_compile_selections_trust_user` re-validates capability trust but, like the
launch path (CR-01), does not validate a selection `model` against the catalog. A saved
workflow can therefore persist a `model` id that is not (or no longer) an allowed model; the
row saves "clean" and the failure (if/when launch wiring lands) surfaces far from the save.

**Fix:** Same catalog check as CR-01, applied in `_compile_selections_trust_user` so save and
launch reject identically (save == launch invariant the module documents).

### WR-05: PATCH route silently ignores a possible stale agent set when re-validating selections

**File:** `backend/app/api/user_workflows.py:394-409`
**Issue:** `update_user_workflow` re-validates a `selections` edit against the row's
**stored** `agents` and falls back to `row.base_pipeline_type or "custom"`. If a selections
edit targets an agent id NOT in the stored composition, nothing rejects it — the synthesized
manifest only includes the stored `agent_ids`, so the extra selection entry is simply never
synthesized into a step (silently dropped) and persists as dead config in `manifest_json`.
The user gets a 200 for a partially-ineffective edit.

**Fix:** Reject (422) when `body.selections` contains an `agent_id` not in the stored
composition — mirroring the `_validate_model_overrides` "targets agent not part of this
workflow" rejection so selection keys and model_override keys behave consistently.

## Info

### IN-01: `renameUserWorkflow` cannot edit `model_overrides` / `selections` though the backend PATCH supports them

**File:** `frontend/src/lib/api.ts:651-661`
**Issue:** The PATCH endpoint (`user_workflows.py:351-413`) accepts `model_overrides` and
`selections`, but the FE `renameUserWorkflow` body type only exposes `{name?, description?}`.
There is no FE affordance to edit a saved workflow's composition/levers after creation.
**Fix:** Extend the body type + add an edit UI if post-save composition edits are intended;
otherwise document the create-only intent.

### IN-02: AgentModelPicker offers every catalog model relying solely on server validation that lacks a `user_allowed` check

**File:** `frontend/src/components/workflow/AgentModelPicker.tsx:77-82`, `backend/app/api/websocket.py:139-154`
**Issue:** DECIDE-02 intentionally drops the FE tier filter and offers all
`model_catalog` entries, delegating enforcement to the server. But
`_validate_model_overrides` checks only `model_id ∈ ModelCatalog.ids()` — it does NOT check
`user_allowed`. Today every catalog entry is `user_allowed=True`
(`model_catalog.py:16-17`), so there is no current exposure. The moment a
`user_allowed=False` model is added, the picker will offer it and the server will accept it.
**Fix:** Make `_validate_model_overrides` (and the CR-01 selection-model check) also require
`ModelCatalog().is_allowed(model_id)` (which already consults `user_allowed`) so the gate is
correct by construction before any restricted model exists.

### IN-03: Stray `print()` debug statements on the WS hot path

**File:** `backend/app/api/websocket.py:519,535,576`
**Issue:** `print(f"[WS] Connection accepted ...")`, `print(f"[WS] Authenticated user=...")`,
and `print(f"[WS] Received run_pipeline ...")` write to stdout on every connection/message
(the surrounding code otherwise uses `logger`). Pre-existing, but in scope for this file.
**Fix:** Replace with `logger.debug(...)` so they respect log configuration and don't pollute
stdout in production.

### IN-04: `_synthesize_step` invalid-selection sentinel relies on a downstream raise that may not name the agent clearly

**File:** `backend/agents/workflows/selections.py:61-65`
**Issue:** A non-dict per-agent selection is carried through as
`step["__invalid_selection__"] = sel` so the compiler's strict-key rejection raises. This
works, but the resulting `CompilerError` names the unknown step key
(`__invalid_selection__`), not "agent X has a malformed selection", so the API 422 detail is
less actionable than the module's docstring implies ("NAMING the offending agent"). Minor
DX/observability gap.
**Fix:** Raise a clear `CompilerError`/422 directly when a per-agent selection is not a dict,
naming the agent, rather than smuggling a sentinel key.

---

_Reviewed: 2026-06-14_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
