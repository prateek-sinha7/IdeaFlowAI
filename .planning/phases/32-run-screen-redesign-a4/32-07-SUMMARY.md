---
phase: 32-run-screen-redesign-a4
plan: 07
subsystem: ui
tags: [sc-1, sc-2, sc-001, d-15, run-screen, preview-panel, tabs, renderer-dispatch, tdd]

# Dependency graph
requires:
  - phase: 32-run-screen-redesign-a4 (plan 01)
    provides: "canonical token layer (@theme inline brand/ink/surface/line ramp + radius ladder)"
  - phase: 32-run-screen-redesign-a4 (plan 02)
    provides: "token-consuming primitives (underline Tabs / Button)"
  - phase: 32-run-screen-redesign-a4 (plan 06)
    provides: "PreviewPanel additive optional gate/clarify passthrough props (interface + DashboardLayout mount wiring)"
provides:
  - "Right-panel tab host (Preview / Steps / Files / Audit) reskinned to the plan-02 underline Tabs primitive + plan-01 tokens (SC-1, SC-2)"
  - "The 'Thinking' tab is RELABELLED to 'Steps' (internal id stays 'thinking' → deep-link/testid stable)"
  - "PreviewPanel forwards the plan-06 gate/clarify/pipelineState props to AgentThinkingTab (Steps) as OPTIONAL dormant passthroughs so plan 08 can render inline gate/clarify"
  - "A MANUAL typed-renderer switcher layered ON TOP of the generic FIRST_PARTY_RENDERERS dispatch (which stays PRIMARY) — override keys on renderType/mimetype tokens, never a workflow name (SC-001)"
affects: [plan-08 (Steps inline gate/clarify consumption), plan-09 (AuditTab internals), plan-10 (color-class re-anchor)]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Tab host renders via the shared underline Tabs primitive fed a generic {id,label,icon} list (SC-001, no workflow name)"
    - "Renderer switcher = a local override state that FORCES a renderType/mimetype renderer; unset ('auto') → the generic dispatch runs UNCHANGED as PRIMARY (override never replaces/reorders the route)"
    - "Mimetype overrides re-run GenericDeliverablePreview with a forced mimetype, preserving the P18 sandboxed-iframe contract (allow-scripts, NOT allow-same-origin)"
    - "Optional dormant passthrough props threaded to a child (AgentThinkingTab) ahead of the consuming plan — declared + forwarded, not yet consumed (tsc-identity)"

key-files:
  created:
    - frontend/src/components/preview/__tests__/PreviewPanel.switcher.test.tsx
  modified:
    - frontend/src/components/preview/PreviewPanel.tsx
    - frontend/src/components/results/AgentThinkingTab.tsx
    - frontend/src/components/preview/PreviewPanel.revisionChip.test.tsx

key-decisions:
  - "The 'thinking' internal tab id is KEPT (only the visible label changed to 'Steps') — the deep-link targets + data-testid=tab-thinking stay stable, avoiding churn across the deep-link consumer + test suites."
  - "The typed-renderer switcher is surfaced ONLY for a GENERIC (mimetype-routed) deliverable (hasGenericDeliverable), not for first-party renders. A first-party deliverable's bespoke renderer is authoritative, so no override is meaningful — and this keeps the switcher <select> (which exposes role=option elements) out of the a11y tree on first-party renders, avoiding an option-role collision with the LiveVersionChip listbox. Generic dispatch stays PRIMARY either way."
  - "The switcher override forces a renderType/mimetype token (auto/html/markdown/zip/user_stories/ppt/prototype/app_builder) — the same structural render-shape keys the file already dispatches on (SC-001-clean); never od_prototype/od_ppt/*_revision workflow names."
  - "AgentThinkingTabProps gained the matching optional gate/clarify props so the passthrough type-checks (tsc-identity) — additive + dormant (not consumed here), owned by plan 08."

patterns-established:
  - "Manual-override-over-generic-dispatch: renderDeliverable checks the override FIRST, then falls through to the unchanged generic FIRST_PARTY_RENDERERS route as PRIMARY."

requirements-completed: [SC-2, SC-1]

# Metrics
duration: ~14min
completed: 2026-07-08
---

# Phase 32 Plan 07: Right-Panel Tab Host Reskin + Steps Relabel + Typed-Renderer Switcher Summary

**The Preview / Steps / Files / Audit tab host is reskinned to the plan-02 underline Tabs primitive + plan-01 tokens, the "Thinking" tab is relabelled "Steps" (id stable), PreviewPanel forwards the plan-06 gate/clarify/pipelineState props to AgentThinkingTab as optional dormant passthroughs for plan 08, and the Preview gains a MANUAL typed-renderer switcher layered on top of the generic FIRST_PARTY_RENDERERS dispatch — which stays PRIMARY — keyed on renderType/mimetype tokens (SC-001), with the AuditTab mount signature untouched.**

## Performance
- **Duration:** ~14 min
- **Tasks:** 2 (Task 2 TDD: RED → GREEN)
- **Files:** 4 (1 created, 3 modified)

## Accomplishments
- **Task 1 — tab-host reskin + Steps relabel + Steps passthrough (SC-1/SC-2):** swapped the legacy gray pill tab row for the shared underline `Tabs` primitive (active ink `#15161A` text + 2px brand `#3C2CDA` underline, all token-routed — no raw hex introduced), fed a generic `{id,label,icon}` list (SC-001). Relabelled the third tab `Thinking → Steps` (internal id kept `thinking` so `data-testid=tab-thinking` + deep-link targets stay stable). Destructured the plan-06 `laneGate`/gate-callbacks/`clarifyQuestions`/clarify-callbacks props and forwarded them to `AgentThinkingTab` as OPTIONAL props; added the matching optional dormant props to `AgentThinkingTabProps` so the passthrough type-checks. **AuditTab mount signature left untouched** (plan 09 owns its internals).
- **Task 2 — typed-renderer switcher (SC-2/SC-001, TDD):** wrote the switcher tests FIRST (observed RED — 3 failing, 2 already-green proving generic-primary), then added a manual override: a `rendererOverride` state (Auto-reset on `renderType` change) that `renderDeliverable` applies BEFORE falling through to the UNCHANGED generic `FIRST_PARTY_RENDERERS` dispatch. Mimetype overrides re-run `GenericDeliverablePreview` with a forced mimetype (preserving the sandboxed-iframe contract). Added a token-styled `RendererSwitcher` `<select>`, surfaced only for generic (mimetype-routed) deliverables. Options are generic renderType/mimetype tokens — never a workflow name.

## Task Commits

1. **Task 1: reskin + relabel + Steps passthrough** — `dd386881` (feat)
2. **Task 2 (RED): failing switcher tests** — `15c85869` (test)
3. **Task 2 (GREEN): typed-renderer switcher override** — `44607c44` (feat)

_Task 2 followed the RED→GREEN TDD gate; no separate refactor commit needed._

## Files Created/Modified
- `frontend/src/components/preview/__tests__/PreviewPanel.switcher.test.tsx` (created) — 5 tests: 2 default/generic-primary (unchanged dispatch), override-forces-chosen-renderer (markdown auto → HTML iframe), clear-returns-to-generic, SC-001 option-values-are-generic-tokens.
- `frontend/src/components/preview/PreviewPanel.tsx` (modified) — Tabs-primitive tab bar; `Thinking→Steps` label; AgentThinkingTab gate/clarify passthrough; `rendererOverride` state + reset effect; `rendererOptions`/`renderRendererOverride`; override-first `renderDeliverable`; `RendererSwitcher` component.
- `frontend/src/components/results/AgentThinkingTab.tsx` (modified) — additive optional dormant `laneGate`/gate-callbacks/`clarifyQuestions`/clarify-callbacks props on `AgentThinkingTabProps` (not consumed here; plan 08).
- `frontend/src/components/preview/PreviewPanel.revisionChip.test.tsx` (modified) — re-anchored the two tab clicks `getByText("Thinking")` → `getByText("Steps")` (label relabel delta).

## Decisions Made
See `key-decisions` frontmatter. Key: switcher gated to generic deliverables (a11y + semantic), internal tab id kept, override keyed on structural render-shape/mimetype tokens (SC-001).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Optional dormant props added to AgentThinkingTabProps (outside files_modified)**
- **Found during:** Task 1 (Steps passthrough).
- **Issue:** The acceptance requires the gate/clarify props be "present in the JSX" on the `AgentThinkingTab` mount, but `AgentThinkingTabProps` did not declare them → passing them is a tsc excess-property error, breaking the required tsc-identity. `AgentThinkingTab.tsx` is not in the plan's `files_modified`.
- **Fix:** Added the eight matching optional props to `AgentThinkingTabProps` (additive, dormant, not consumed) so the passthrough type-checks. This is the minimal change that satisfies "AgentThinkingTab receives the props" AND tsc = 0; it also stages the exact interface plan 08 will consume.
- **Files modified:** `frontend/src/components/results/AgentThinkingTab.tsx`.
- **Verification:** tsc 0; preview suite 43/43.
- **Committed in:** `dd386881` (Task 1 commit).

**2. [Rule 1 - Bug] LiveVersionChip option-role collision from the switcher <select>**
- **Found during:** Task 2 GREEN (full preview-suite verify).
- **Issue:** An initial always-on switcher (`hasContent && options>1`) rendered a native `<select>` whose `<option>` elements expose `role="option"` in the a11y tree even when collapsed. On first-party renders that also mount a `LiveVersionChip`, this broke `PreviewPanel.versionChip.test.tsx` (`getAllByRole("option")` count 3 → 5; per-option `aria-selected` assertion) — 2 failures.
- **Fix:** Gated the switcher to `hasGenericDeliverable` (generic mimetype-routed deliverables), where multiple typed renderers genuinely apply. First-party renders no longer mount the switcher → no option-role pollution. Generic dispatch stays PRIMARY; the switcher tests (all generic deliverables) stay green.
- **Files modified:** `frontend/src/components/preview/PreviewPanel.tsx`.
- **Verification:** Full preview suite 43/43 green (versionChip 5/5 restored).
- **Committed in:** `44607c44` (Task 2 GREEN commit).

**3. [Rule 1 - Bug] revisionChip test tab-click coupled to the old "Thinking" label**
- **Found during:** Task 1 (relabel).
- **Issue:** `PreviewPanel.revisionChip.test.tsx` reaches the Steps tab via `getByText("Thinking")` — the relabel to "Steps" breaks that lookup.
- **Fix:** Re-anchored the two clicks to `getByText("Steps")` (a direct consequence of the intentional relabel).
- **Files modified:** `frontend/src/components/preview/PreviewPanel.revisionChip.test.tsx`.
- **Verification:** revisionChip 2/2 green.
- **Committed in:** `dd386881` (Task 1 commit).

---

**Total deviations:** 3 auto-fixed (1 blocking, 2 bug). **Impact:** all necessary for tsc-identity + no-regression; no scope creep — the generic dispatch, AuditTab signature, and sandboxed-iframe contract are all preserved.

## Issues Encountered
None beyond the auto-fixed items above.

## Verification Observed
- **Preview vitest (plan scope):** `npx vitest run src/components/preview/` → **7 files / 43 tests passed** (was 6/38 at baseline; +1 file / +5 tests = the new switcher suite). Verified by delta: the reskin changed color classes but no existing suite regressed.
- **Switcher + genericDeliverable (Task 2 verify):** `npx vitest run …switcher.test.tsx …genericDeliverable.test.tsx` → **2 files / 16 passed**.
- **tsc identity:** `npx tsc --noEmit | grep -v mockApi.ts | grep -c "error TS"` = **0** (baseline 0 preserved).
- **SC-001 (switcher/dispatch path):** no workflow-name literal — the SC-001 test asserts every switcher option value ∈ the generic renderType/mimetype set and none is a workflow name (`od_prototype`/`od_ppt`/`*_revision`/the raw `workflowType`). Grep of the override/switcher path = 0 workflow-name literals.
- **Generic dispatch remains PRIMARY:** the 2 default tests (first-party `user_stories` → bespoke renderer; generic `text/html` → sandboxed iframe) pass with NO override active, proving the switcher is override-only.
- **AuditTab mount unchanged:** `<AuditTab hookRuns={pipelineState?.hookRuns} workflowRunId={pipelineState?.pipelineRunId} />` byte-unchanged (plan 09 owns internals).
- **Sandboxed-iframe contract:** preserved — mimetype overrides route through `GenericDeliverablePreview` (`sandbox="allow-scripts"`, NOT `allow-same-origin`); the switcher adds no new injection path. Asserted in the override test.
- **Tab label:** the third tab reads **"Steps"** (`grep 'label: "Steps"'` = 1).

## Residual legacy raw-hex (noted per plan verification)
- `frontend/src/components/preview/PreviewPanel.tsx` still has 2 `#1B2A4A` sites at the PPT **Download** buttons inside `PPTTabActions` (L1070/L1079). These are OUTSIDE the tab-host regions this plan touched (a separate PPT-action component) — legacy sites left for a later reskin pass, exactly as the plan's verification permits ("legacy sites outside the tab host may remain for later; note any residual in SUMMARY"). No `#2563eb` remains in the tab-host regions touched.

## Known Stubs
None that block the plan goal. The AgentThinkingTab gate/clarify passthrough props are declared-and-forwarded-but-unconsumed plumbing (interface + JSX with LIVE values) intentionally prepared for plan 08 Steps — additive, tsc-identity; not an empty-data UI stub.

## Threat Flags
None — no new trust boundary. T-32-07-01 mitigated (sandboxed-iframe contract preserved; switcher selects among existing renderers, no new injection path); T-32-07-02 mitigated (dispatch/switcher keyed on renderType/mimetype, SC-001 grep + test clean); T-32-07-03 accepted (Steps passthrough is the same owner-scoped gate/clarify state, no new data source).

## Next Phase Readiness
- The tab host is reskinned + relabelled; plan 08 can consume the AgentThinkingTab gate/clarify passthrough to render the inline gate/clarify in Steps. Plan 09 owns AuditTab internals (signature untouched here). Plan 10 re-anchors any color-class assertions changed by the reskin.

## Self-Check: PASSED

- Files: PreviewPanel.tsx, AgentThinkingTab.tsx, PreviewPanel.switcher.test.tsx, PreviewPanel.revisionChip.test.tsx, 32-07-SUMMARY.md — all FOUND.
- Commits: `dd386881`, `15c85869`, `44607c44` — all FOUND in git log.
- Guardrails: preview 43/43 green (by delta); tsc 0; third tab "Steps"; generic FIRST_PARTY_RENDERERS dispatch PRIMARY (switcher override-only); no workflow-name literal in switcher/dispatch path (SC-001 test + grep); AuditTab mount signature unchanged; sandboxed-iframe contract preserved.

---
*Phase: 32-run-screen-redesign-a4*
*Completed: 2026-07-08*
