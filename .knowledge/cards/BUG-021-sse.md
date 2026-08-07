---
id: BUG-021-sse
type: bug
status: done
area: [frontend, auth]
files:
  - frontend/src/hooks/useRunChat.ts
summary: >-
  Left chat transcript BODY shows the PREVIOUS run's messages on a fresh launch (until
  the new run's frames arrive)
source: .planning/SSE-QA-BUG-LOG.md#bug-021
campaign: sse
severity: "🟡 minor"
---

### BUG-021 — Left chat transcript BODY shows the PREVIOUS run's messages on a fresh launch (until the new run's frames arrive)  [🟡 minor] [FIXED ✅ — LIVE-PROVEN]
- **RESOLVED:** FIXED + LIVE-PROVEN (quick 260717-t9i; commit `6cede3af`; feat/ui-2, NOT pushed). Fix (1 line): `frontend/src/app/dashboard/page.tsx:1538` — added `seedRunChatTranscript([]);` inside `onStartPipeline`'s `if (!isRevision)` fresh-run block (alongside the `setContentSourceRunId/Type(null)` clears), reusing the in-scope `seedTranscript` reset primitive to empty `useRunChat.messages` on a fresh non-revision launch. Revisions (`:1534` "keep existing content") + history-open (`:1336` `seedRunChatTranscript(durableFrames)`) untouched; `seedRunChatTranscript(` now has EXACTLY 2 call sites. RED→GREEN: `freshLaunchTranscriptReset.source.test.ts` (source-lock, mirrors contentSourceRunType.source.test.ts — reset PRESENT + INSIDE `!isRevision` + EXACTLY ONCE) + `useRunChat` Test 16 (seedTranscript([]) empties a populated transcript); tsc clean; vitest 19/2-files. Regression: mocked Playwright ts-chat/ts-t.history/ts-j.streaming **19/19**. **LIVE-PROVEN (orchestrator-verified via screenshots + DOM):** reopened od_prototype `2774f80c` (chat body showed prototype content — IBM / "Build phase active" / `prototype.html`) → fresh user_stories launch IN-SESSION → the chat body was EMPTY (`innerText=""`, no IBM/prototype content); header still correct (title = new brief, eyebrow "USER STORIES"). Screenshots `bug021-before-reopened.png` / `bug021-after-freshlaunch.png`; zero console errors. Closes the lane-header/chat stale-on-fresh-launch family (BUG-019 header title / BUG-020 type / BUG-021 transcript body).
- **Found:** 2026-07-17 (observed during the BUG-019 live proof). On a fresh launch performed IN-SESSION after viewing another run, the left chat lane's HEADER correctly shows the new run (BUG-019/020 fixed), but the transcript BODY still renders the PREVIOUS run's content (a fresh user_stories launch showed residual prototype text "IBM-inspired design… / Status: In Progress (Build phase active)") until the new run's own frames stream in. Screenshot `bug019-freshlaunch-title.png`.
- **Root cause (from the BUG-019 investigation):** `frontend/src/hooks/useRunChat.ts` `messages` state is NOT reset on a fresh launch — it resets ONLY via the imperative `seedTranscript` (called on history-open, `useRunChat.ts:387`); `onStartPipeline` / the fresh-launch path never resets it. So the transcript retains the last-viewed run's turns. Same "reset-on-fresh-launch" family as BUG-019, but on the transcript rather than the header.
- **Fix (PROPOSED, FE-only, NOT applied):** reset `useRunChat.messages` to `[]` on a fresh top-level launch (when the hook's `runId` transitions to a newly-launched run, or an explicit reset from `onStartPipeline`), mirroring the `seedTranscript` reset for the launch path. Needs a RED→GREEN test + a live re-prove (cold + in-session). Transient (self-heals once the new run streams) but visible.
