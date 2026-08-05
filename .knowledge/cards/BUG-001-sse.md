---
id: BUG-001-sse
type: bug
status: done
area: [agents]
summary: >-
  Run-screen left-lane title shows the most-recent run's title, not the viewed run's
source: .planning/SSE-QA-BUG-LOG.md#bug-001
campaign: sse
severity: "🟠 major"
---

### BUG-001 — Run-screen left-lane title shows the most-recent run's title, not the viewed run's  [🟠 major] [FIXED ✅]
- **RESOLVED:** FIXED (quick 260716-j1u, cc2f98f7) — live-proven

- **Found:** 2026-07-16 · test DEF-44-12-4 B3/B5 live-verification (history-open path) · surface run screen → left conversation lane header (`LaneRunHeader`, `data-testid="lane-run-title"`).
- **Symptom:** Opening three different runs from the Home "Jump back in" recents, the left-lane title heading showed the WRONG run's title while all other lane/Steps content was correct for the opened run:
  - user_stories `ab90f5f4` (brief "A shift-scheduling app for cafes…") → heading "An interactive analytics dashboard for a fitness app: active" (WRONG). Starting-point card + pipeline correct.
  - app_builder `bb6dc438` (brief "A URL shortener web app…") → same fitness heading (WRONG). Content correct (URL-shortener 15-agent build).
  - od_prototype `4cd2f478` (brief "An interactive analytics dashboard for a fitness app…") → heading correct — but only *coincidentally*, because od_prototype was the LAST run launched (= `recents[0]`).
  - Shots: `~/.claude/jobs/e660aea4/tmp/shots-qa/{user_stories,app_builder,od_prototype}-steps.png`.
- **Root cause (investigation agent — read `.planning/IMPLEMENTATION-REGISTER.md` global + all FE run-screen phase sections 25/31/32/36–39/41/42; grep-confirmed no run-title architecture in the backend engine phases):**
  - **Symptom site → cause site.** Heading is rendered by `frontend/src/components/chat/LaneRunHeader.tsx:241-248` (`{runTitle}`). Feed chain: `frontend/src/components/layout/DashboardLayout.tsx:1323-1325` computes `runHeaderTitle` → passed as `runTitle={runHeaderTitle}` at `DashboardLayout.tsx:1713` → `frontend/src/components/chat/RunChatLane.tsx:1173` `runTitle={runTitle ?? firstUserTurn}` → `LaneRunHeader`.
  - **The mechanism (`DashboardLayout.tsx:1323-1325`):**
    ```
    const latestRunTitle = recentRuns?.[0]?.title;
    const runHeaderTitle =
      latestRunTitle && latestRunTitle !== "Untitled" ? latestRunTitle : submittedBrief;
    ```
    `recentRuns?.[0]` is **unconditionally the most-recently-created run** (the Home recents list, `page.tsx:150` + prepend/update at `page.tsx:294/557/585/753`), never the run being VIEWED. The ternary prefers `latestRunTitle` whenever it is a real (non-"Untitled") title — which it almost always is — so `submittedBrief` (the fallback) is never reached, and the title never tracks the viewed run. The viewed-run identity `contentSourceRunId` (`page.tsx:156`; set to `data.pipeline_run_id` on `pipeline_complete` at `page.tsx:496`, to `fullRun.id` on history-open at `page.tsx:1187`, cleared to `null` on fresh launch at `page.tsx:1427`) — already destructured into this component at `DashboardLayout.tsx:210` and used everywhere else for run identity — is simply not consulted by the title expression.
  - **Root-cause assumption that broke:** the Phase-39 title code assumed "the active/on-screen run is always `recents[0]`." That holds for the *primary launch flow* (a fresh build clears `contentSourceRunId` to null and the just-launched run is `recents[0]`), but is false the moment you view a **non-latest** run from history/recents, where the on-screen run is `contentSourceRunId`, not `recents[0]`.
  - **PRE-EXISTING, not introduced by DEF-44-12-4 — 12-4 EXPOSED it.** `git blame -L1319,1326` → the whole block is commit **`5003aca47` "feat(39-05): wire the lane Back-to-history + run metadata into the run shell" (2026-07-11, Phase 39 / RUNUI-06)**. The DEF-44-12-4 quick-task range **`396ae3db..8f7d9e9b` (2026-07-16) never touched `DashboardLayout.tsx`** (`git log … -- DashboardLayout.tsx` in that range = empty). What 12-4 *did* do (Piece 1, commit `349e5038`, `page.tsx:1189-1202`) is seed the viewed run's Steps trace + set `submittedBrief = fullRun.input` on history-open — i.e. it made a history-opened run actually RENDER its own content instead of the old empty "Start a pipeline…" placeholder (comment at `page.tsx:1191-1193`). That is exactly what made the always-`recents[0]` title *visibly* wrong: before 12-4 the run screen showed almost nothing for a non-latest run so nobody saw the title; after 12-4 the correct content renders beside the stale title. This is a sibling of DEF-44-12-4 (same "bound to launched run, not viewed run" class — 12-4 rebound the reducer/transcript/runInput; the lane-header *title* is a separate binding 12-4 did not cover).
- **Fix (PROPOSED — investigation only, not applied):** bind the title to the VIEWED run at `DashboardLayout.tsx:1323`. Replace the single line
  ```
  const latestRunTitle = recentRuns?.[0]?.title;
  ```
  with a viewed-run lookup (both `contentSourceRunId` and `recentRuns` are already props in scope — `DashboardLayout.tsx:209-210`):
  ```
  const viewedRun =
    contentSourceRunId != null
      ? recentRuns?.find((r) => r.id === contentSourceRunId)
      : recentRuns?.[0];
  const latestRunTitle = viewedRun?.title;
  ```
  Keep the existing ternary unchanged (`… ? latestRunTitle : submittedBrief`). Behaviour by flow:
  - **Fresh live build** (`contentSourceRunId` null) → `recents[0]` = the just-launched run → title correct (byte-identical to today's primary flow; no regression).
  - **Live complete** (`contentSourceRunId` = completed run) & **history/recents reopen** (`contentSourceRunId` = viewed run) → `find(...)` resolves the viewed run's clean async title → **correct (bug fixed)**.
  - **Viewed run older than the recents window** (`find` → undefined) → falls back to `submittedBrief`, which on reopen is the VIEWED run's own `fullRun.input` (12-4 Piece 1) → still the viewed run, never a foreign run's title (strictly better than today).
  - Coherent with revisions: an inline-revise keeps `contentSourceRunId` = the source/parent run and keeps the parent's deliverable on screen until new output arrives (`page.tsx:1429`), so the title correctly matches the on-screen content, then re-points to the revision run on its `pipeline_complete` (`page.tsx:496`).
  - Minimal + SC-001-safe: one contiguous edit in a guarded component, no page.tsx change, no new prop/state, keys only on generic run identity (`contentSourceRunId` / `run.id`) — zero workflow-name literal. Rejected alternative: threading a dedicated `viewedRunTitle` state from `page.tsx` (larger diff, redundant — `recents.find` already yields the same clean async title the launch flow uses).
- **Verify (fail-before / pass-after):**
  1. **Fail-before:** with ≥2 runs of different types, open a non-latest run from Home recents; assert `data-testid="lane-run-title"` == `recents[0].title` (reproduced live: user_stories `ab90f5f4` and app_builder `bb6dc438` both showed the fitness title). 
  2. **Pass-after:** after the fix, `lane-run-title` == the OPENED run's title for `ab90f5f4` (shift-scheduling) and `bb6dc438` (URL-shortener); `od_prototype 4cd2f478` stays correct.
  3. **No launch regression:** a fresh live run shows its own title throughout the build (`contentSourceRunId` null → `recents[0]`).
  4. **Unit:** add a `DashboardLayout` (or `LaneRunHeader`) vitest asserting `lane-run-title` tracks `contentSourceRunId` across a 3-element `recentRuns`; `tsc --noEmit` clean.

---
