---
id: BUG-010-sse
type: bug
status: open
area: [sse]
summary: >-
  Run-scope ref mistracks when a background build is active while viewing a different
  run (j1u WARNING-2)
source: .planning/SSE-QA-BUG-LOG.md#bug-010
campaign: sse
---

### BUG-010 — Run-scope ref mistracks when a background build is active while viewing a different run (j1u WARNING-2)  [🟢 NON-ISSUE — no fix needed]

**Class:** run-screen live state not bound to the viewed run (same family as BUG-001/002/003/005/006).
**Severity:** 🟢 minor / effectively NON-ISSUE as framed (see Reachability verdict).
**Status:** INVESTIGATED — do NOT fix (a priority flip regresses BUG-005's primary case). Evidence below.
**Branch:** feat/ui-2. All cited fix sites are from commit `8eec694c` (quick-260716-j1u BUG-005), 2026-07-16.

---

#### Found
Plan-checker WARNING-2, logged in `.planning/quick/260716-j1u-.../deferred-items.md:15-17` and `260716-j1u-SUMMARY.md:100`: BUG-005's `trackedRunIdRef` syncs from priority `activePipelineRunId ?? contentSourceRunId`; the checker feared that a background build A (claimed `activePipelineRunId = A`) plus opening a different completed run C from history (`contentSourceRunId = C`) resolves `tracked = A`, so a later revision of C is guard-skipped and C's clarify/seen-set corrupted.

The actual j1u fix (all commit `8eec694c`, verified via `git blame`):
- **Declaration** — `frontend/src/app/dashboard/page.tsx:156` `const trackedRunIdRef = useRef<string | null>(null);`
- **Sync effect** — `page.tsx:941-943`
  `trackedRunIdRef.current = activePipelineRunId ?? contentSourceRunId ?? trackedRunIdRef.current;` deps `[activePipelineRunId, contentSourceRunId]`. Priority + the exclusion of `pipelineState.pipelineRunId` **confirmed**. (Exclusion is justified: `useWorkflow.ts:243` `pipelineRunId: pipelineRunIdFromStart ?? prev.pipelineRunId` adopts *any* pipeline_start id, including a foreign concurrent run's — tracking it would hijack the id.)
- **Launch set** — `page.tsx:1489` `trackedRunIdRef.current = launchedRunId;` inside the `onStartPipeline` handler (`page.tsx:1451`), in `startPipeline(...).then(launchedRunId => { attachRun; trackedRunIdRef.current = launchedRunId })`.
- **Guard** — `page.tsx:485-495`: `isForeignRun = !!incomingRunId && !!trackedRunIdRef.current && incomingRunId !== trackedRunIdRef.current`; if foreign → skip the reset block (`resetReplayState` + `setReviewGateData(null)` + `setQuestionnaireData(null)` + `setActivePipelineRunId(null)`, lines 496-515); else run it.

#### Symptom
None reproduced. The feared symptom (a revised/rebuilt C's legitimate `pipeline_start` reset skipped → C's clarify/seen-set corrupted) does not occur for the reasons below.

#### Reachability verdict — LARGELY A NON-ISSUE (headline case resolves CORRECTLY)
The headline premise "A **actively building**, `activePipelineRunId = A`" is **not a real state**. `activePipelineRunId` is:
- SET **only** at `questionnaire_ready` (`page.tsx:830`), i.e. when a run is **paused at the clarify gate**; and
- CLEARED **only** inside the non-foreign reset (`page.tsx:515 setActivePipelineRunId(null)`), which fires on the run's **own** `pipeline_start` as it leaves clarify.

So while A is **building**, `activePipelineRunId` is **null**. Opening C then resolves `tracked = null ?? C = C` — **correct**, no divergence. (`grep` confirms only two writers of `setActivePipelineRunId`: `:515` null and `:830` set.)

The divergence `tracked = A while viewing C` is only reachable in the **narrower, transient** window "A **paused at the clarify gate** while the user opens a different run C." `handleSelectWorkflowRun` (`page.tsx:1210-1232`) sets `contentSourceRunId = C` and does **not** clear `activePipelineRunId`, so A's clarify id survives and the `??` picks A. Verdict: reachable but narrow; and even there it does not produce the claimed failure (next section).

#### Root cause file:line + mechanism (why the narrow window still doesn't fail)
A revision **always creates a new run R with a new id** (R ≠ C, R ≠ A) — it never re-emits C's id. Behaviour splits by revise path:

1. **user_stories / prototype / app_builder revise** — `DashboardLayout.tsx:548 / 564 / 580` call `onStartPipeline(...)` → `page.tsx:1451` handler → `page.tsx:1489` sets `trackedRunIdRef.current = launchedRunId (= R)`. R's `pipeline_start` (id = R) then matches `tracked = R` → **reset runs correctly**. The divergence is **self-healed**. No bug.

2. **od_ppt revise** — `handleRevisePpt` REST path `DashboardLayout.tsx:512-524`: `postRevision(contentSourceRunId)` → new run R, `attachRun(R)`, but it does **not** call `onStartPipeline`, so `trackedRunIdRef` is **not** updated. R's `pipeline_start` (id = R) is foreign to `tracked` — **but this is true whether `tracked = C` or `tracked = A`** (R ≠ both), so the divergence is **not** the operative cause. The skip is largely benign: `onResetPipeline()` (`:523`) already reset the reducer; R's fresh `event_id`s don't collide with the seen-set; the only residue is a stale `lastSeqRef` (`page.tsx:498`) that matters solely on a **mid-revision SSE reconnect** (after_seq too high → R's early frames skipped on replay). This is a pre-existing od_ppt-revise/reconnect edge, independent of WARNING-2.

The one genuinely real (but **racy + minor**) divergence-window issue is the **inverse** of WARNING-2: if A's **own** `pipeline_start` arrives while the user is viewing C (user submitted A's clarify, then quickly opened C), the reset — correctly self-recognized since `incoming(A) == tracked(A)` — has **global** side effects (`resetReplayState` at `:496-502`) that wipe **C's** seeded replay state (seen-set / `lastSeqRef` / `waveGroups`, seeded at `page.tsx:1252-1272`), a transient Steps-panel glitch on C. Not the WARNING-2 mechanism, and the proposed priority flip would make it worse.

#### Fix — NON-ISSUE (do NOT apply the proposed priority flip)
Recommendation: **close as won't-fix / non-issue as framed.** The proposed "prioritize `contentSourceRunId` over `activePipelineRunId` when they diverge" is a **regression**: with `tracked = C`, A's own clarify→build `pipeline_start` (id = A) becomes `foreign` → its reset (`setActivePipelineRunId(null)` etc.) is **skipped** → A's `activePipelineRunId`/questionnaire stay stuck, and if the user returns to A it shows stale clarify — i.e. **re-introducing BUG-005 for the launched run A**. The launch-set at `:1489` and the `??` order exist precisely to keep the primary launch / clarify-advance reset working; flipping them breaks it.

Root truth: a **single global `trackedRunIdRef` cannot serve both "the run I'm driving (A)" and "the run I'm viewing (C)"** once they diverge — any single-ref priority is a heuristic with a losing case. The only correct durable fix is the **systemic per-run subscriber scoping already logged in the BUG-005 investigation** (`.planning/SSE-QA-BUG-LOG.md:192`, option #2): at the `runSubscribe → handleWebSocketMessage` bridge (`page.tsx:909-912`) drop frames whose `pipeline_run_id` ≠ the viewed/active run, making the whole reducer + reset per-run and deleting the ref heuristic entirely. That is a larger change, out of this quick's scope, and would also subsume the adjacent observation below.

**Adjacent (separate bug, not WARNING-2, worth a follow-up):** `pipeline_complete → setContentSourceRunId(pipeline_run_id)` at `page.tsx:530` is **also not run-scoped** — a background run A completing while the user views C flips `contentSourceRunId` C→A and hijacks the viewed content-source/preview. Same "global state not bound to the viewed run" class; distinct from WARNING-2.

#### Verify
- **Disprove headline:** launch A **without** a clarify gate (or let A pass clarify) so A is *building*; open C from history → `trackedRunIdRef === C` (because `activePipelineRunId` is null). Confirms the "background build" case resolves correctly.
- **Narrow window, 3 run_pipeline types:** launch A **with** clarify, let it reach `questionnaire_ready` (`activePipelineRunId = A`); open a different completed **user_stories/prototype/app_builder** run C; revise C → observe `trackedRunIdRef` flip to the new revision run at `:1489` and its `pipeline_start` reset **run** (GREEN, no corruption).
- **Narrow window, od_ppt:** same but C is od_ppt → R's `pipeline_start` reset is skipped, yet the revision still streams (reducer reset by `onResetPipeline`); the only observable degradation requires forcing a **mid-revision SSE reconnect** to surface the stale-`after_seq` frame skip.
- **Regression check on the proposed flip (to justify rejecting it):** temporarily set the sync to `contentSourceRunId ?? activePipelineRunId`; repro A-at-clarify + view C, then submit A → A's `pipeline_start` is now `foreign` → A's clarify never clears (BUG-005 re-appears for A). Revert.
- **Unit-level (optional):** a `page.tsx` vitest asserting the sync resolves `tracked = C` when `{activePipelineRunId: null, contentSourceRunId: C}` (build case) and `tracked = A` when `{activePipelineRunId: A, contentSourceRunId: C}` (clarify case) — documents the semantics without a code change.

---
