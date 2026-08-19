---
id: BUG-021-GROUNDED-CONTEXT
type: bug
kind: event
title: BUG-021 — grounded fix spec
status: open
applies_to:
  phases: []
  modules:
  - app
  - chat
  - useRunChat
  globs:
  - frontend/src/hooks/useRunChat.ts
  - useRunChat.ts
  - page.tsx
  - frontend/src/app/dashboard/page.tsx
  requirements: []
locked_constraints: []
verification:
  type: manual
  status: required
  test_files: []
compact_summary: 'useRunChat.messages was never cleared on a fresh non-revision launch, so the prior run''s transcript bled through until new frames streamed; seedRunChatTranscript([]) now resets it.'
last_updated: '2026-08-14'
author: 'Imran Yousaf <imrany@hexaware.com>'
author_source: code-commit
---

# BUG-021 — grounded fix spec (left chat transcript BODY carries over the previous run on a fresh launch)

> **FRONTEND-ONLY, ~1 line.** The BUG-019/020 header fixes are done; this fixes the remaining half — the chat transcript BODY. Root cause pinned by the BUG-019 investigation + orchestrator spot-checks (seedTranscript primitive + the onStartPipeline reset block both read directly). Executable spec for a `gsd-quick`.

## The bug (verified)
On a fresh top-level launch performed IN-SESSION after viewing another run, the left chat lane's HEADER correctly shows the new run (BUG-019/020 fixed), but the transcript BODY still renders the PREVIOUS run's messages (e.g. a fresh user_stories launch showed residual prototype text "IBM-inspired design… / Status: In Progress (Build phase active)") until the new run's own frames stream in. Visually confirmed in `bug019-freshlaunch-title.png`. Transient (self-heals once the new run streams) but visible.

## Root cause (verified to file:line)
`frontend/src/hooks/useRunChat.ts` holds the transcript in `messages` (a `useState`, init `[]`). It is reset ONLY inside `seedTranscript` (`useRunChat.ts:387-395`: clears `seenRef`, sets `lastSeqRef=0`, `setMessages([])`, then folds the passed frames), which `page.tsx` calls ONLY on history-open (`page.tsx:1336` `seedRunChatTranscript(durableFrames)`). The fresh-launch handler `onStartPipeline` (`page.tsx:1508`) NEVER resets the transcript: its `if (!isRevision)` fresh-run reset block (`page.tsx:1518-1533`) clears the preview content + `setContentSourceRunId(null)` (:1529) + `setContentSourceRunType(null)` (:1532) — but not `useRunChat.messages`. So the transcript retains the last-viewed run's turns until the new run's frames fold in. Same "reset-on-fresh-launch" family as BUG-019, but on the transcript instead of the header.

## The fix (one line)
In `onStartPipeline`'s fresh-run block, `frontend/src/app/dashboard/page.tsx` — inside the existing `if (!isRevision) { … }` (`:1518-1533`), alongside `setContentSourceRunId(null)` / `setContentSourceRunType(null)`, add:
```ts
// BUG-021: a fresh run starts a NEW conversation — clear the last-viewed run's
// transcript so its turns don't bleed into the new run's chat lane (the new run's
// frames fold into the empty transcript via handleFrame as they stream).
seedRunChatTranscript([]);
```
`seedRunChatTranscript` is already in scope (destructured from `useRunChat` at `page.tsx:1014`). Calling it with `[]` reuses the existing reset primitive: it clears `messages`, `seenRef`, and resets `lastSeqRef=0` (correct for a brand-new run), and folds no frames. The new run's streamed frames then populate the now-empty transcript.

**Scope of the reset — non-revision ONLY (deliberate):** place it INSIDE `if (!isRevision)`. Revisions deliberately "keep existing content visible until new output arrives" (`page.tsx:1534` comment) and continue the conversation, so a `*_revision` launch must NOT clear the transcript. BUG-021 is specifically the fresh TOP-LEVEL (non-revision) launch carrying over the previous VIEWED run — exactly the `!isRevision` path.

**Why safe:**
- History-open UNAFFECTED — it calls `seedRunChatTranscript(durableFrames)` on its own path (`page.tsx:1336`); this adds a reset only to the launch path.
- Revisions UNAFFECTED — outside the `!isRevision` block.
- No content loss — `onStartPipeline` does not add any chat turn itself; the transcript is populated purely by the run's streamed frames (via `handleFrame`), which arrive AFTER the reset and fold into the empty list.
- Resetting `lastSeqRef=0` is correct for a fresh run (its re-fetch/dedup cursor starts at 0).

## Verification
- `npx tsc --noEmit` clean (from `frontend/`).
- **Primitive (unit, if not already covered):** a `useRunChat` test that `seedTranscript([])` empties a previously-populated `messages` (and clears `seenRef`/`lastSeqRef`). Likely already covered by the DEF-44-12-4 seed tests — confirm; add only if missing.
- **Wiring (the real fix) — prefer a mocked Playwright e2e (RED→GREEN):** reproduce the carryover — open/seed a run whose chat lane shows a transcript, then trigger a FRESH (non-revision) launch, and assert the chat transcript is EMPTY/cleared at launch (before the new run's frames). Fail-before: without the reset the previous turns persist. If a faithful mocked e2e for launch-after-view is impractical in the harness, fall back to a component/integration test that spies `seedRunChatTranscript` is called with `[]` on a fresh `onStartPipeline` and NOT on a revision — plus the orchestrator live proof below. (Note: the fix is a one-line wiring inside `page.tsx`'s inline `onStartPipeline`, which — like the BUG-017 adapter — resists isolated unit import; the e2e / live proof is the load-bearing check.)
- **Deferred to the orchestrator — live proof:** view a run (its chat populated), then launch a fresh non-revision run in the same session → the chat BODY clears immediately (no stale previous-run text); a REVISION launch still keeps its content. Executor must NOT run live Bedrock.

## Scope fences (STRICT)
- **FRONTEND ONLY.** One line in `page.tsx` `onStartPipeline`'s `if (!isRevision)` block (+ a test). Do NOT reset on revisions. Do NOT modify `seedTranscript` itself, the header (BUG-019/020), the other launch resets, the SSE parser, the reducer, or any BUG-017/018 change.
- SC-001: `page.tsx` is exempt; keep any guarded component workflow-name-literal-free.

## Constraints
- Branch **feat/ui-2** (NEVER main/staging). Worktrees OFF → sequential. **NO commit trailer.** **NEVER push.**
- FE cwd-sensitive: vitest/Playwright from inside `frontend/`; kill :3000 before mocked Playwright. Use `localhost:3000` (NOT 127.0.0.1) for any browser check.
- Executor: verify via `tsc` + vitest (+ a mocked Playwright spec IF it authors one and :3000 is free). Do NOT run live Bedrock; do NOT kill the orchestrator's :3000 dev server unless it needs Playwright — coordinate by deferring the live proof to the orchestrator. STATE.md quirk: prefer the quick-task table; if `progress:` clobbered restore total_phases:37 completed_phases:35 total_plans:208 completed_plans:207 percent:95.
