# Phase 39 — Deferred Items

Out-of-scope discoveries logged during execution (not fixed in the discovering plan).

## From 39-07 (Wave 1, harness repair)

### D-39-07-1 — The mocked e2e suite is broadly stale against the feat/ui-2 UI redesign (systemic, beyond the three named crashes)

**Discovered:** 39-07 Task 1, while verifying `npm run e2e` exits 0.

**What:** Plan 39-07's scope fence named exactly three known-red breakages
(`GET /api/workflows` home-grid crash, the "Provide the brief" launch flow, and
`/api/runs/{id}/family` not-iterable). All three are **fixed** — 0 occurrences of
their crash signatures in a full run. But fixing them unblocked the launch flow
and revealed that the suite is **systemically stale** against the whole feat/ui-2
redesign (Phase 32 run-screen, Phase 36 fused Home + data-driven HomeLaunchGrid,
plan-06 lane absorption, composer/gate/questionnaire restyles). Specs now reach
their post-launch assertions and fail there on **redesigned-layout locators**,
not on the three crashes.

**Evidence (representative, from a full mocked run):** failures span ~all spec
files — e.g. `ts-i.agent-panels` (AgentProgressPanel's run-lane mount was removed
in plan-06 and absorbed into `RunChatLane`), `ts-k.wave-tree` (`WaveTreePanel`
now mounts INSIDE the Steps drilldown, not the default view), `ts-j.streaming`,
`ts-l.token-usage`, `ts-g/n.review-gate(s)`, `ts-m.questionnaire`,
`ts-e.model-picker`, `ts-f.skills-hooks`, `ts-t.history`, `ts-b.selection`
(home grid now renders per-row "Inspect …" buttons → strict-mode ambiguity;
`ts-b-05` migration NEW-pill / 2-tile behavior), `ts-c-10` (the view now swaps
input→execution on the server `pipeline_start`, not optimistically on send).

**Why deferred (not fixed here):** These are the **surface work of Waves 1-6**
(39-01..39-06) plus adjacent redesign spec-maintenance — explicitly outside this
harness-repair plan's scope fence, and outside the SCOPE BOUNDARY rule (only
issues directly caused by this task's changes are auto-fixed). Rewriting ~90
run-view/composer/gate assertions to the new layout blind (before the surfaces
are even built/approved) would pre-empt and likely contradict those waves.

**Recommendation:** As each surface wave (39-01..06) lands its redesigned surface,
it should re-anchor the corresponding stale spec assertions (the same pattern as
Phase 32's `test(32-10): re-anchor brittle … e2e assertions`). A dedicated
"e2e re-green" pass (or folding it into 39-06's close) is the natural home for
the residual cross-cutting specs (auth/history/composer/model-picker) that no
single surface wave owns.

**RUNUI-09 status:** The requirement has two halves — (a) the fidelity harness +
side-by-side gallery under `frontend/e2e` (DELIVERED + validated in 39-07), and
(b) the mocked suite green again. Half (a) is done; half (b) ("green again")
cannot be met until the surface waves re-anchor the redesigned-layout specs, so
RUNUI-09 should not be marked fully complete until then.
