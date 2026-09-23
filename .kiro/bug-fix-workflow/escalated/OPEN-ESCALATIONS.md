# Open Escalations — Team Handover Document

**Last updated:** 2026-09-04  
**Status:** 11 items open out of 29 original escalations (18 closed ✓)  
**Purpose:** This document is the single reference for every remaining open escalation. Each
entry explains the issue in plain terms, what investigation or decision is needed, who needs
to act, and exactly what code changes would follow from that decision.

---

## How to read this document

Each escalation has:
- **What the issue is** — plain description, no assumed context
- **Current state** — what is broken or missing right now
- **Blocked by** — the specific decision or design gap preventing a fix
- **Fix path** — what code changes are needed once the decision is made
- **Risk** — how risky the code change is

Items are grouped by theme, ordered from simplest to most complex.

---

## GROUP 1 — Gate seeding & exclusivity (3 linked cards)

> These three cards share the same root question. **Decide ISS-419 first** — ISS-362 and ISS-377 follow from that decision.

---

### ISS-419 — Engineer-only gates (`approval`/`security`) have no UI affordance

**Domain:** 14-backend-api → `frontend/src/components/workflow/ReviewGatesSection.tsx`  
**Severity:** Minor UX gap

#### What the issue is

The "Review gates" checklist in the launch wizard lists every agent as a user-toggleable
checkbox. When a workflow step declares an `approval` or `security` gate in its manifest,
the checklist shows that agent as unchecked and toggleable — identical to every other agent.
There is no visual signal that the step already has a gate, and no indication that the gate
is engineer-only (not user-controlled).

The practical problem: a `custom-agent` step has no `AGENT.md`, so `AgentDef.gate` is always
`null`. The manifest `gates: [...]` array is its ONLY gate declaration. Without reading it,
the step looks gated-by-nothing on load.

#### Current state

- Two `it.fails` tests exist in `ReviewGatesSection.test.tsx:234,247` asserting that
  `approval`/`security` steps render their checkbox CHECKED on load.
- Those tests currently fail (expected-fail). Baseline: 12 passed + 2 expected-fail.
- **No production code is broken** — the current UI is just incomplete. Nothing crashes.

#### Why a naive fix (checking the box) is wrong

1. `FIX-377` locked: *"only `human`/`before-human` seed the checkbox; `approval`/`security` do not"*
2. If the user checks an `approval` step then unchecks it, `withHumanGate()` writes
   `gates: ["approval", "human"]` → the compiler (`compiler.py:806-811`, ADR-0013) throws a
   hard error. Two gates on one step is forbidden.
3. `approval` and `security` are `user_allowed=False` (engineer-only). The established
   convention for those in this codebase is **visible-but-locked**, not checked.
4. `security` is a policy gate (auto-fires without human interaction) — showing it as a
   "human review" checkbox is factually wrong.

#### Decision needed — pick one option

> **Option A (recommended):** Render a read-only LOCKED row for engineer-only gates.
> Show a lock icon, `aria-disabled`, excluded from `checkedIds`/`gatedCount`/`gate_agent_ids`.
> Satisfies the real complaint (user can see the gate exists), matches the `user_allowed=false`
> convention, breaks nothing.  
> → Requires a new UI affordance design decision + rewrite of the 2 `it.fails` tests.

> **Option B:** Close as working-as-intended. `approval`/`security` are out of scope for
> this checklist by design. `FIX-377` already covers the two human-review names.  
> → Requires only fixing the 2 `it.fails` test assertions to match working-as-intended.

> **Option C:** Reverse ADR-0013 and make the checklist a general gate display.  
> → Rejected — requires `gate_key` changes and breaks the compiler contract. Too large.

#### Fix path once decided

- **Option A:** ~30 lines in `ReviewGatesSection.tsx` (new locked-row render path) + rewrite
  2 test assertions. No backend change. Low risk.
- **Option B:** Rewrite 2 test assertions only. Zero production code change. Zero risk.

---

### ISS-362 — Setting Gate=Human in Advanced modal doesn't check the Review-gates checkbox

**Domain:** 12-frontend-workflow → `CanvasConfigRail.tsx` + `ReviewGatesSection.tsx`  
**Severity:** Minor UX inconsistency  
**Status:** INFERRED — not yet browser-reproduced. Needs verification first.

#### What the issue is

This is the inverse of ISS-247 (which was fixed by FIX-346). ISS-247: checking an agent in
the Review-gates checklist didn't update the Advanced modal's Gate dropdown. FIX-346 fixed
that direction. ISS-362: setting Gate=Human in the Advanced modal should also check that
agent in the Review-gates checklist — but the reverse synchronisation was never implemented.

#### Root cause (code-traced, not browser-verified)

`CanvasConfigRail.tsx`'s `selectGate` → `patch()` → `onSelection()` only updates the
`selections` map. It has zero connection to `ReviewGatesSection`'s `checkedIds` state.
There is no synchronisation in either direction between the Gate dropdown and the checklist.

#### Decision needed

1. **First: browser repro (5 minutes).** Open Advanced modal → Config tab for an agent →
   set Gate = "Human gate" → close modal → check if Review-gates checkbox is now ticked.
   - If TICKED → card is already fixed, close it.
   - If NOT TICKED → confirmed, proceed to fix.

2. **If confirmed broken:** The fix is ~5 lines in `CanvasConfigRail.tsx` — call
   `ReviewGatesSection`'s toggle callback when `selectGate` writes a human gate.
   Depends on ISS-419's decision: if Option A (locked rows), the fix must also handle
   `approval`/`security` correctly (don't trigger the toggle for engineer-only gates).

#### Fix path

- `CanvasConfigRail.tsx`: when `selectGate` sets `gate === "human"` or `gate === "before-human"`,
  call `onSelectionsChange` with a mutation that also triggers `ReviewGatesSection`'s check.
- ~5 lines, one file, no backend change. Low risk.
- **Prerequisite:** confirm ISS-419 Option A or B first to avoid conflicting with the
  locked-row behaviour.

---

### ISS-377 — "Save as my version" can't round-trip templateId/designSystemId/brief

**Domain:** 12-frontend-workflow → `LaunchWizard.tsx` + `user_workflows.py` + `manifest.py`  
**Severity:** Real UX regression — data saved but not restored  
**Depends on:** ISS-189, ISS-197 share the same root

#### What the issue is

`FIX-336` stopped "Save as my version" from discarding the user's brief/template/design-system
at save time. But reopening `/create/ppt` (or any panel) after saving still shows an **empty
brief and no template pre-selected**, even when an override exists.

The "Save workflow" button on the same screen does not have this problem because it writes
`selections._wizard` which `DashboardLayout.tsx` and `page.tsx` read back to pre-fill those
fields. "Save as my version" can't use that path because it must send `manifest` (override),
and the backend's `_reject_both` check makes `manifest` and `selections` mutually exclusive.

#### Why it's a schema decision

Two hard blockers in `user_workflows.py`:

1. `_reject_both` (line 66): `manifest` and `selections` are mutually exclusive. An override
   save must send `manifest`. So `_wizard` can't ride with it.
2. `manifest.py:266`: `build_manifest_from_dict` rejects any key outside `_ALLOWED_TOP_KEYS`
   (INV-5). Adding `_wizard`/`brief`/`template` to a manifest 422s the save.

#### Decision needed — pick one option

> **Option 1 (add a presentation-only manifest key):** Add `_wizard` (or similar) to
> `_ALLOWED_TOP_KEYS` so it can ride alongside the manifest steps. Touches
> `backend/agents/workflows/manifest.py`, `_ALLOWED_TOP_KEYS`, the FE `WorkflowManifest`
> TypeScript type, and every manifest reader.  
> → Medium effort, additive, but widest surface area.

> **Option 2 (new DB column — separate storage):** Stop making `manifest` and `selections`
> mutually exclusive by adding a dedicated `wizard_config` column. The save stores wizard
> data there; the load reads it independently. Requires an additive Alembic migration.  
> → Clean architecture, additive migration (safe), medium effort.

> **Option 3 (recommended — scope down):** Accept that a per-run brief is not part of a
> reusable override. Persist only `templateId` and `designSystemId` (which ARE
> workflow-level choices), and leave the brief as a per-run field. Update docs/UX copy
> accordingly.  
> → Smallest code change. Most honest about what a "saved workflow" is.

#### Fix path once decided

- **Option 1:** `manifest.py` `_ALLOWED_TOP_KEYS` + FE `WorkflowManifest` type + readers.
  Moderate risk (touches manifest parsing).
- **Option 2:** Alembic migration (0041) + `user_workflows.py` save/load + FE store.
  Low production risk (additive).
- **Option 3:** `user_workflows.py` save path — write `template_id` and `design_system_id`
  into existing manifest or a lightweight sidecar. FE read-back updated. ~1 day of work.

---

### ISS-189 + ISS-197 — LaunchWizard ISS-228 family (depends on ISS-377)

**Domain:** 12-frontend-workflow → `LaunchWizard.tsx`  
**Severity:** Bug — saved workflow override doesn't restore correctly  
**Blocked by:** ISS-377 schema decision

#### What the issue is

ISS-189 and ISS-197 are both part of the ISS-228 family: a "Save as my version" override
discards the `handleLaunchSaved` fetch, so re-opening a saved workflow shows the base
manifest instead of the user's override.

Both cards were escalated from the domain fixer because the fix requires touching
`DashboardLayout.tsx` and `IdeaInputPage` as secondaries — outside the single-file domain
boundary for LaunchWizard.

#### Decision needed

**No new decision needed** — these unblock automatically once ISS-377 is decided.
The fix is a multi-file wiring change in `LaunchWizard.tsx` + `DashboardLayout.tsx` +
`IdeaInputPage` to properly round-trip the saved data that ISS-377's fix makes available.

#### Fix path

Once ISS-377 is resolved, assign a single developer to fix ISS-189 + ISS-197 together in
one PR. The change is FE-only, no backend edit needed beyond what ISS-377 delivers.

---

## GROUP 2 — Model tier entitlement gap (1 card)

---

### ISS-398 — Per-agent model overrides bypass subscription tier check

**Domain:** 14-backend-api → `run_engine.py` + `run_commands.py` + `user_workflows.py`  
**Severity:** Security/billing gap — basic-tier accounts can use premium models via override  
**Note:** `run_engine.py` is load-bearing — proceed with care

#### What the issue is

The account-level model setting (`/settings/ai-model`) was already fixed by ISS-292/FIX-361:
basic-tier accounts can no longer select Claude Opus from the settings page. But there is a
second door: the **per-agent model override** path in the Composer/Canvas. A basic-tier
account can send:

```json
PATCH /api/user-workflows/{id}
{"model_overrides": {"prototype-build": "eu.anthropic.claude-opus-4-6-v1"}}
```

This returns **200 OK** — the premium model is saved and will be used on every subsequent
launch. The validation function `_validate_model_overrides` in `run_engine.py` only checks
that the model ID exists in the catalog; it never checks whether the requesting user's
subscription tier allows that model.

#### Current state

- `entitlements.py` already has `TIER_MODEL_COST_CLASSES` and `can_use_model()` — added by
  the ISS-292 fix for the settings page. The infrastructure is already there.
- `_validate_model_overrides(model_overrides, run_agent_ids)` signature has no `user_tier`
  parameter. It structurally cannot do a tier check.
- Three live call sites: `run_commands.py:2900` (launch), `user_workflows.py:566` (save),
  `user_workflows.py:807` (update).

#### Decision needed

**Approval to touch `run_engine.py`.** This file is load-bearing. The fix is well-understood
and the blast radius is small, but the team has a standing rule to be careful with
`run_engine.py` edits.

> **If approved:** The fix is 3 call sites + 1 new parameter. See fix path below.  
> **If not approved:** Leave parked. Accept the billing gap until a safe window.

#### Fix path (if approved)

**1. `backend/app/api/run_engine.py` — add `user_tier` param:**
```python
# Before
def _validate_model_overrides(model_overrides: dict, run_agent_ids: set[str]) -> str | None:

# After
def _validate_model_overrides(
    model_overrides: dict, run_agent_ids: set[str], *, user_tier: str
) -> str | None:
    ...
    # after catalog membership check, add:
    allowed, reason = can_use_model(user_tier, model_id)
    if not allowed:
        return f"model_overrides for agent {agent_id!r}: {reason}"
```

**2. `backend/app/api/run_commands.py:2900`** — pass `user_tier=current_user.tier`

**3. `backend/app/api/user_workflows.py:566` and `:807`** — same

**No schema changes. No migrations. No frontend changes.**  
AST-clean, SC-001 safe. Estimated effort: 30 minutes.  
**Risk: Low** — no engine logic changes, only a new validation parameter.

---

## GROUP 3 — Workflow save/launch correctness (3 cards)

---

### ISS-181 — Override saves clean but 422s at launch

**Domain:** 14-backend-api → `user_workflows.py` + `composition_order.py`  
**Severity:** Confusing UX — silent failure at wrong time

#### What the issue is

When a user saves a composed override, the save succeeds (200 OK) and the override appears in
the Advanced panel. But when they try to launch, they get a 422:

```
Workflow DAG is unsatisfiable: Agent 'prototype-build' consumes 'prototype-plan'
but no agent in the workflow produces it.
```

The problem is two validators that disagree:
- **At save:** `merge_override_steps` runs `WorkflowCompiler(trust="db")` → passes
- **At launch:** `presort_specs` in `composition_order.py` checks produces/consumes DAG → fails

The user finds out only when they run. They see no error during save.

#### Decision needed

> **Option A:** Run the `presort_specs` DAG check at save time too, so the canvas can reject
> the incompatible selection before the user saves. The save endpoint would return 422 with
> a useful error message ("Agent X needs Y but Y is not in your selection").  
> → `user_workflows.py` save path + `composition_order.py`. Medium effort.

> **Option B:** Accept the current behaviour — the user gets an error at launch rather than
> save. Add a clearer error message so the failure is understandable.  
> → Minimal change, low risk.

#### Fix path (Option A)

Import `presort_specs` into `user_workflows.py`'s save/update handlers and call it before
committing. No engine change needed. No migration.

---

### ISS-180 — `base_version` column written but never read

**Domain:** 14-backend-api → `user_workflows.py` + `workflow_definition.py`  
**Severity:** Missing feature — saved overrides silently go stale

#### What the issue is

Migration 0039 added a `base_version` column that stores the base manifest's `version` when
an override is saved. No code reads it. If the built-in workflow changes after the user saved
their override (new step added, deliverable changed), the override silently keeps running the
old steps with no warning and no way to see it from the UI.

#### Decision needed

This is a **new feature request**, not a regression. The column exists and is populated;
the comparison + UI signal are missing.

> Define: what does the UI show when an override is behind the base manifest?
> Options: a warning badge in the Advanced panel, a "Refresh to latest" button, a
> non-blocking info toast on launch, or nothing (document as known limitation).

Once the UX is decided, the implementation is:
1. `user_workflows.py` GET endpoint: compare `override.base_version` with current
   `load_manifest(pipeline_type).version` and add an `is_stale: bool` field to the response.
2. FE: render the staleness signal wherever the saved workflow is displayed.

**No migration needed** (column already exists). Medium frontend + small backend work.

---

### ISS-381 — "Save workflow" on conditional-gate examples always 422s

**Domain:** 14-backend-api → `user_workflows.py`  
**Severity:** Feature broken — "Save workflow" completely fails on `ex_A*` examples

#### What the issue is

When a user opens a conditional-gate example (`ex_A4_human_divert`, `ex_A1_loop`, etc.) and
clicks "Save workflow", they always get a 422:

```
agent_ids not allowed for 'ex_A4_human_divert':
['custom-agent:ask', 'custom-agent:pick-language', 'custom-agent:a-english']
```

The roster validator at `user_workflows.py:562` rejects the workflow's **own** composed step
IDs because the `base_pipeline_type` is a non-`custom` built-in. The rule was written assuming
only `custom` pipelines have user-composed agent IDs — the `ex_A*` family breaks that
assumption.

This is the **actual defect** that ISS-263 was trying to describe (ISS-263 was inferred and
refuted; ISS-381 measured the real behaviour).

#### Decision needed — pick one option

> **Option 1 (fix the roster validator — recommended):** The validator at `user_workflows.py:562`
> should also accept agent IDs that belong to the built-in's own roster. Specifically, when
> `base_pipeline_type` is a known built-in, allow IDs that appear in
> `get_pipeline_agents(base_pipeline_type)`. This is the defect the user actually meets.  
> → `user_workflows.py` only. ~10 lines. Low risk.

> **Option 2 (extend the selections map to represent conditional steps):** Make the compact
> selections map carry `route` + `produces` through `_synthesize_step`. This is larger,
> needs an ADR, and is inert at run time (the engine reads the base manifest file anyway).  
> → Not recommended — complex, large blast radius.

#### Fix path (Option 1)

In `user_workflows.py`'s roster validation, add: *"if the submitted agent IDs are a subset
of `get_pipeline_agents(base_pipeline_type)` agent IDs, allow them."*  
Single file, no migration, no engine change. ~10 lines. Low risk.

---

## GROUP 4 — Backend architecture (2 cards)

These require an infrastructure/architecture decision before any code moves.

---

### ISS-134 — Cancel-liveness breaks in multi-container ECS deployment

**Domain:** 14-backend-api → `run_engine.py` + `run_commands.py`  
**Severity:** Architecture gap — not broken today, will break at ECS scale

#### What the issue is

The run cancel mechanism stores cancel signals in a **process-local in-memory dict**
(`_CANCEL_EVENTS` in `run_engine.py`). This works when all runs live in the same process.

In a multi-container ECS deployment, a cancel request hits one container but the run lives
in another. The cancel signal never crosses the process boundary. The run keeps going; the
user thinks it was cancelled.

#### Current state

Not broken in the current single-process deployment. Will break when ECS is deployed.

#### Architecture decision needed

Choose the shared cancel-signal mechanism:

| Option | Description | Complexity | Notes |
|---|---|---|---|
| **DB flag** | Add `cancel_requested` column to `workflow_runs`; engine polls it | Low | Polling latency (~1–5s). Already have DB. |
| **Redis pub/sub** | Publish cancel to a Redis channel; each worker subscribes | Medium | Fast propagation. Requires Redis infra. |
| **SSE/queue** | Route cancel commands through a message queue | High | Most robust but most infrastructure |

Once chosen, the implementation in `run_engine.py` + `run_commands.py` is mechanical.

#### Fix path

1. Decide the shared mechanism
2. Replace `_CANCEL_EVENTS[run_id].set()` (in-memory) with the shared signal write
3. Replace `cancel_event.is_set()` polls in the engine with reads from the shared store

---

### ISS-105 — SSE transport race: uvicorn cancels SSE tasks on shutdown

**Domain:** 14-backend-api → `run_stream.py`  
**Severity:** Correctness — SSE streams may not drain cleanly on server shutdown

#### What the issue is

When uvicorn shuts down (e.g. during a deployment), it cancels in-flight async tasks
including SSE streaming generators. This can leave client streams in an inconsistent state:
the client is still connected and waiting for events, but the server has silently dropped
the generator.

There is also a snapshot race: if a pipeline_complete event is in-flight at shutdown, the
client may never receive it and the run appears stuck.

#### Architecture review needed

Before landing a fix on `run_stream.py` (the SSE down-channel), the team must review the
proposed approach:

> **Proposed fix:** In `run_stream.py`, catch `asyncio.CancelledError` in the streaming
> generator and emit a `stream_closed` synthetic event before re-raising, so the client
> knows to reconnect. Also: use `--timeout-graceful-shutdown` on uvicorn (already documented
> in the live test setup) to give in-flight SSE streams time to drain.

> **Risk:** A wrong edit here is a runtime regression in the SSE down-channel — all
> connected clients are affected. Needs review from whoever owns the transport layer.

---

## GROUP 5 — Frontend new features (2 cards)

These cannot be implemented until the backend defines new data shapes.

---

### ISS-112 — FE has no data source for attachment references

**Domain:** 06-frontend-components → frontend·components (mixed)  
**Severity:** Feature gap — UI component cannot be built without backend data

#### What the issue is

A frontend component needs to display attachment reference data (which attachments were
included in a run's input). There is no backend endpoint or store field currently surfacing
this data. The `run_events` table stores attachment refs, but no API exposes them in a form
the FE component can consume.

#### Decision needed

Define the backend API shape:
- New field on `GET /api/runs/{id}/summary`? New endpoint `GET /api/runs/{id}/attachments`?
- What shape: array of `{name, kind, retained, truncated}`?

Once defined, the backend change lands first (likely `runs.py` or `run_stream.py`), then the
FE component is unblocked.

---

### ISS-434 — `PipelineRunState.deliverableMimetype` missing from SSE run-state

**Domain:** 06-frontend-components → frontend·components (mixed)  
**Severity:** Feature gap — FE component needs a field that doesn't exist in the payload

#### What the issue is

A FE component needs `deliverableMimetype` from `PipelineRunState` (the run-state shape
carried in the SSE stream). The field does not exist. The deliverable's MIME type is known
server-side (from the manifest's deliverable spec) but is never emitted in any SSE event.

#### Decision needed

Coordinate backend + frontend:
1. Agree on the field name (`deliverableMimetype`, `deliverable_mime_type`, or similar)
2. Decide which SSE event carries it (likely `pipeline_start` or a new `run_metadata` event)
3. Backend lands first (add to `run_stream.py` or `run_commands.py` emit path)
4. FE component is unblocked once field appears in the event

---

## Triage priority order

| Priority | Card(s) | Why |
|---|---|---|
| 🔴 **Do first** | ISS-419 → then ISS-362 + ISS-377 | One decision resolves 3 cards. ISS-362 is a 5-line fix once confirmed. ISS-377 unblocks ISS-189/197. |
| 🟠 **High** | ISS-381 | Users actively hitting this — "Save workflow" completely broken on ex_A* examples. ~10-line fix once decided. |
| 🟠 **High** | ISS-398 | Silent billing gap. ~30-min fix, infrastructure already exists. Needs run_engine.py approval. |
| 🟡 **Medium** | ISS-181 | Confusing UX — errors at launch instead of save. Medium effort. |
| 🟡 **Medium** | ISS-189 + ISS-197 | Unblocks after ISS-377. FE-only. |
| 🟡 **Medium** | ISS-134 | Not broken today, will break at ECS scale. Needs infrastructure decision. |
| 🔵 **Low / Plan** | ISS-180 | Missing staleness signal. New feature, not regression. |
| 🔵 **Low / Plan** | ISS-105 | SSE shutdown race. Architecture review needed before touching transport layer. |
| 🔵 **Low / Plan** | ISS-112 + ISS-434 | Need new backend API shape defined first. |

---

## Summary counts

| Status | Count |
|---|---|
| Open — needs product/architecture decision | 6 |
| Open — needs investigation/verification first | 1 (ISS-362) |
| Open — needs run_engine.py approval | 1 (ISS-398) |
| Open — blocked on other card | 2 (ISS-189, ISS-197) |
| Open — new feature/infrastructure | 3 (ISS-180, ISS-134, ISS-105, ISS-112, ISS-434) |
| **Total open** | **11** |
| Closed ✓ | 18 |
| **Grand total** | **29** |
