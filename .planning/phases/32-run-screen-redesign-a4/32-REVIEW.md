---
phase: 32-run-screen-redesign-a4
reviewed: 2026-07-08T00:00:00Z
depth: deep
diff_base: 7d5a467d..HEAD
files_reviewed: 20
files_reviewed_list:
  - backend/agents/execution_engine/engine.py
  - backend/app/api/runs.py
  - backend/tests/agents/characterization/_normalize.py
  - frontend/src/app/dashboard/page.tsx
  - frontend/src/app/layout.tsx
  - frontend/src/components/chat/RunChatLane.tsx
  - frontend/src/components/layout/DashboardLayout.tsx
  - frontend/src/components/preview/PreviewPanel.tsx
  - frontend/src/components/preview/ReviewGatePanel.tsx
  - frontend/src/components/results/AgentThinkingTab.tsx
  - frontend/src/components/results/AuditTab.tsx
  - frontend/src/components/results/PrototypePipelineView.tsx (deleted)
  - frontend/src/components/ui/Badge.tsx
  - frontend/src/components/ui/Button.tsx
  - frontend/src/components/ui/Card.tsx
  - frontend/src/components/ui/Pill.tsx
  - frontend/src/components/ui/Tabs.tsx
  - frontend/src/components/workflow/WaveTreePanel.tsx
  - frontend/src/hooks/useWorkflow.ts
  - frontend/src/lib/api.ts
  - frontend/src/lib/exporters/auditExporter.ts
  - frontend/src/styles/globals.css
  - frontend/src/types/index.ts
findings:
  critical: 0
  high: 0
  medium: 2
  low: 3
  total: 5
status: issues_found
fix039_sensitive_touched: true
---

# Phase 32: Run-Screen Redesign [A4] — Code Review Report

**Reviewed:** 2026-07-08
**Depth:** deep (cross-file, invariant-focused)
**Range:** `7d5a467d..HEAD`
**Files reviewed:** 20 source + deletions
**Status:** issues_found (2 medium, 3 low — no critical/high)

## Summary

This is a reskin + additive-read-only-backend phase with hard invariants (SC-001, FIX-039,
LOCK-B, owner-scope, INV-13, ND-6). All of the security- and invariant-sensitive surfaces
hold up under adversarial review:

- **SC-001 (no workflow-name literals in render/gate paths):** VERIFIED clean. The
  `prototype-analyze`/`prototype-specify`/`prototype-plan` literals were replaced by generic
  discriminators — `updateSpecsEligible`/`artifactKind` (engine → gate event → FE) in
  `ReviewGatePanel.tsx:266-271` and a content-tag sniff fallback, and the cancelled/failed/
  degraded terminal render keys off generic `pipelineState` markers (`RunChatLane.tsx:320-322`).
  Grep of the render/gate paths found only comments + test fixtures, no live literals.
- **FIX-039 (unconditional agent_start accumulator reset):** PRESERVED. The reset block
  (`useWorkflow.ts:296-317`) still runs unconditionally before the `isSpecRevisionRerun`
  computation; the rename only changed which branch bumps `specRevisionCount` (see WR-02).
- **LOCK-B (legacy WS active, SSE dormant):** VERIFIED. `useWebSocket.ts` + `/ws/chat` intact,
  `RunConnectionProvider` NOT mounted (`dashboard/page.tsx:900` inert default,
  `enabled === false`), no `NEXT_PUBLIC_SSE_TRANSPORT` activation. `PrototypePipelineView.tsx`
  deletion is expected.
- **Owner-scope audit endpoints:** VERIFIED. `_owner_gate_or_404` gates on
  `WorkflowRun.user_id == user_id` (NOT the nullable `owner_id`), IDOR → 404 never 403
  (`runs.py:1068-1085`); child rows re-filtered by `owner_id` (defense-in-depth); `exec-runs`
  exposes only `output_digest` (`runs.py:1204`). FE fetchers map 404 → empty envelope
  (`api.ts`).
- **INV-13 (engine metadata-only):** VERIFIED. engine.py diff adds two event-metadata keys +
  an eligibility frozenset; no `create_deep_agent`/runner/agent-loop change. `_normalize.py`
  strips both new keys so the 5 goldens stay byte-identical (INV-3).
- **ND-6 / CSV injection:** VERIFIED. `auditExporter.ts` is client-side Blob only (no network,
  no PDF, no backend route); `escapeCsvCell` (`auditExporter.ts:63-77`) neutralizes leading
  `= + - @ \t \r` and quote-wraps separators/newlines. AuditTab renders all cells as escaped
  text (no `dangerouslySetInnerHTML`).
- **XSS (reskinned preview iframe):** VERIFIED. `GenericDeliverablePreview`
  (`PreviewPanel.tsx:184-189`) uses `sandbox="allow-scripts"` with NO `allow-same-origin`.
- **"What went wrong" / degraded cards:** VERIFIED. `sanitizeError` (`RunChatLane.tsx:142-147`)
  takes the first line only, caps at 200 chars — never surfaces multi-line stack frames.
- **KAN-99 N-1 cap:** PRESERVED (`AgentThinkingTab.tsx:635-638`).

Two medium findings are behavior/quality concerns (not security), and both are about the same
generalization of the KAN-101 update-specs discriminator. **WR-02 touches the FIX-039-sensitive
`useWorkflow.ts`** — flagged for orchestrator routing rather than auto-fix.

---

## Structural Findings (fallow)

No `<structural_findings>` block was provided with this review. The cross-file substrate below
was derived directly (grep + git):

- `specRevisionCount` has exactly ONE consumer, and it was DELETED this phase: the sole reader
  was `PrototypePipelineView.tsx:396` (`git show 7d5a467d:.../PrototypePipelineView.tsx`), which
  no longer exists. It is now write-only state (see WR-02).
- All plan-01 status/brand tokens referenced by the new primitives + WaveTreePanel are defined
  in `globals.css` (verified: `status-*`, `status-*-fill/-border`, `brand-fill`, `brand-pressed`,
  `radius-tag/-button`, `surface-card/-warm`, `line-control`).

---

## Narrative Findings (AI reviewer)

## Medium

### MD-01: "Update the Specs" affordance broadened from analyze-gate-only to spec + task_list + summary gates

**File:** `backend/agents/execution_engine/engine.py:5263-5265` (+ `ReviewGatePanel.tsx:441-446`, `DashboardLayout.tsx:1311`)
**Issue:** The SC-001 generalization replaced the `agentId === "prototype-analyze"` FE literal
with a server flag `update_specs_eligible`, driven by
`_UPDATE_SPECS_ELIGIBLE_KINDS = {"spec", "task_list", "summary"}`. In the prototype pipeline
`prototype-specify → kind "spec"`, `prototype-plan → kind "task_list"`, and the unmapped
`prototype-analyze → "summary"` — and **all three declare `gate: Human_Gate`** (verified in
their `AGENT.md`) and flow through the inline gate call sites (`engine.py:2713`, `:3542`) that
stamp the flag. Result: the "Update the Specs" button — which triggers a spec-revision
sub-pipeline — now renders on the **specify** and **plan** gates, where the pre-phase code
(`ReviewGatePanel.tsx` old `isAnalysis && !!onUpdateSpecs`) showed it ONLY on the analyze gate.
The locked KAN-101 decision (32-CONTEXT.md §decisions) describes this affordance as being "on
analyze gates". Offering a spec-revision trigger from the spec/plan gate itself is a behavior
change that can confuse users or re-enter the specify→plan→analyze loop from an unexpected
entry point.
**Fix:** Confirm intent. If the affordance is meant to remain analyze-only, narrow the set to
the analyze artifact kind (e.g. `frozenset({"summary"})`, or introduce a dedicated
`analysis`-style kind so `spec`/`task_list` gates are excluded). If the broadening is
intentional, record the decision explicitly in the phase SUMMARY so it is not mistaken for a
literal-removal regression.

### MD-02: `specRevisionCount` is now write-only dead state and its bump was silently generalized (FIX-039-sensitive file)

**File:** `frontend/src/hooks/useWorkflow.ts:294-295, 323-327`
**Issue:** Two coupled problems in the FIX-039 reducer:
1. **Dead state.** `specRevisionCount` is still computed and bumped, but its ONLY consumer —
   `PrototypePipelineView.tsx:396` — was deleted in this phase. Grep confirms no other reader
   in `src/` (only the type declaration `types/index.ts:629` + tests). The phase deleted the
   consumer without retiring or re-homing the producer, leaving write-only state (contra the
   project's no-dual/INV-3 "delete what you supersede" posture).
2. **Semantic change while dead.** The guard changed from
   `isSpecifyRerun = wasAlreadyDone && agentId === "prototype-specify"` to
   `isSpecRevisionRerun = wasAlreadyDone`. Any already-`done` agent that re-starts now bumps
   the counter, so a KAN-101 spec-revision cycle that re-runs specify→plan→analyze increments
   `specRevisionCount` by ~3 per cycle instead of once. This mis-count is currently masked only
   because nothing reads the value — it becomes a live bug the moment a "revision cycle" badge
   is re-wired.

The FIX-039 unconditional accumulator reset itself is INTACT (the reset block at lines 296-317
runs before this branch) — the regression is confined to the counter semantics, not the reset
ordering.
**Fix (route, do NOT auto-fix — FIX-039-sensitive):** Either delete `specRevisionCount` + the
`isSpecRevisionRerun` bump entirely (its consumer is gone), or, if a future revision badge needs
it, gate the bump so it counts cycles not per-agent restarts (e.g. bump only on the first
re-started agent of a sub-pipeline). Preserve the unconditional reset block verbatim.

## Low

### LW-01: `Button` renders no default `type`, defaulting to `type="submit"`

**File:** `frontend/src/components/ui/Button.tsx:44-57`
**Issue:** The shared primitive spreads `{...rest}` but sets no default `type`. A native
`<button>` without `type` defaults to `submit`; if any consumer mounts a `Button` inside a
`<form>` without passing `type="button"`, a click submits the form. Callers currently pass
`type` explicitly (e.g. `RunChatLane.tsx:329`), so this is latent, not active.
**Fix:** Default it: `type={rest.type ?? "button"}` (or destructure `type = "button"`).

### LW-02: `Badge` falls back to raw `status` string as its label

**File:** `frontend/src/components/ui/Badge.tsx:62`
**Issue:** `{label ?? status}` — when `label` is omitted, the raw (possibly lowercase/free-form)
`status` prop is rendered verbatim rather than the normalized key, so a caller passing
`status="completed"` with no label shows "COMPLETED" while the color ramp is the `done` ramp.
Cosmetic only.
**Fix:** Render `label ?? normalizeStatus(status)` (or a display-name map) for label-free usage.

### LW-03: cancelled status color is inconsistent across surfaces

**File:** `frontend/src/components/workflow/WaveTreePanel.tsx:44-56` vs `frontend/src/components/ui/Badge.tsx:27-28`
**Issue:** The canonical palette (§B3) maps `cancelled → amber`, and `Badge` honors that. But
`WaveTreePanel.statusKind` routes `cancelled` into the `failed` bucket (red), documented as
IN-05. A cancelled run thus shows amber in the lane/badge and red in the wave tree. Documented,
but a user-visible inconsistency against the one-status-palette rule.
**Fix:** If deliberate, leave as-is (it is annotated). If not, give `cancelled` its own amber
chip in `STATUS_STYLE` and a `cancelled` branch in `statusKind`.

---

_Reviewed: 2026-07-08_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: deep_
