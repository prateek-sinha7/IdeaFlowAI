---
phase: quick-260717-t9i
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - frontend/src/app/dashboard/page.tsx
  - frontend/src/app/dashboard/freshLaunchTranscriptReset.source.test.ts
  - frontend/src/hooks/useRunChat.test.ts
autonomous: true
requirements:
  - BUG-021
must_haves:
  truths:
    - "BUG-021 (a fresh NON-REVISION launch clears the previous run's transcript): inside `onStartPipeline`'s `if (!isRevision)` fresh-run block (page.tsx:1518-1533), alongside `setContentSourceRunId(null)` (:1529) and `setContentSourceRunType(null)` (:1532), a new `seedRunChatTranscript([]);` reuses the useRunChat reset primitive (`seedTranscript`, useRunChat.ts:387-395 — clears `seenRef`, sets `lastSeqRef=0`, `setMessages([])`, folds no frames) so the last-VIEWED run's turns don't bleed into the new run's chat lane. The new run's streamed frames (via `handleFrame`) fold into the now-empty transcript AFTER the reset. `seedRunChatTranscript` is already in scope (destructured from `useRunChat` as `seedTranscript: seedRunChatTranscript`, page.tsx:1014)."
    - "BUG-021 (NON-REVISION ONLY — deliberate): the reset sits INSIDE `if (!isRevision)` (gated by `const isRevision = type.endsWith(\"_revision\")`, page.tsx:1509). A `*_revision` launch deliberately keeps existing content visible until new output arrives (page.tsx:1534) and continues the conversation, so it MUST NOT clear the transcript — the reset stays out of the revision path."
    - "BUG-021 (history-open + no content loss UNCHANGED): the history-open path calls `seedRunChatTranscript(durableFrames)` on its own seam (page.tsx:1336) and is untouched — this adds a reset only to the launch path with an EMPTY array. `onStartPipeline` adds no chat turn itself, so the transcript is populated purely by the run's streamed frames arriving AFTER the reset; resetting `lastSeqRef=0` is correct for a brand-new run (its re-fetch/dedup cursor starts at 0)."
    - "Proof: the inline `onStartPipeline` handler resists an isolated unit render (a giant inline arrow in a JSX prop inside the 1500+-line page.tsx), so the wiring is pinned by the sanctioned grep-style SOURCE-LOCK test (mirrors contentSourceRunType.source.test.ts / contentSourceRunScope.source.test.ts, which already lock THIS reset block): `seedRunChatTranscript([]);` is present, sits INSIDE the `!isRevision` block (bounded by the `For revisions, keep existing content` comment), and appears EXACTLY ONCE (never on the revision path). The reset PRIMITIVE (`seedTranscript([])` empties a previously-populated transcript) is separately locked by a useRunChat unit case — confirmed NOT already covered by a runnable vitest (the only DEF-44-12-4 seed reference is the deferred live e2e `ts-live-state.spec.ts`)."
    - "Scope (STRICT): FRONTEND-ONLY, ONE ~1-line production edit (page.tsx, inside the :1518-1533 block) + one NEW source-lock test + one useRunChat characterization case. NON-REVISION ONLY. Do NOT modify `seedTranscript` itself, the header (BUG-019/020), the other launch resets, history-open, the SSE parser, the reducer, or any BUG-017/018 change. SC-001: page.tsx exempt; the reset reuses the EXISTING generic `seedTranscript` primitive — no workflow-name literal."
  artifacts:
    - path: "frontend/src/app/dashboard/page.tsx"
      provides: "the fresh-run `if (!isRevision)` block (:1518-1533) gains `seedRunChatTranscript([]);` alongside the content-source clears, so a fresh non-revision launch starts with an EMPTY chat transcript"
      contains: "seedRunChatTranscript([]);"
    - path: "frontend/src/app/dashboard/freshLaunchTranscriptReset.source.test.ts"
      provides: "NEW source-lock gate (RED->GREEN, mirrors contentSourceRunType.source.test.ts): reads page.tsx as text and asserts the reset is PRESENT, sits INSIDE the `!isRevision` block, and appears EXACTLY once"
      contains: "seedRunChatTranscript"
    - path: "frontend/src/hooks/useRunChat.test.ts"
      provides: "ADD one characterization case (add-if-missing; confirmed missing) — `seedTranscript([])` empties a previously-populated transcript, locking the primitive the wiring reuses"
      contains: "seedTranscript(["
  key_links:
    - from: "a fresh top-level launch (type does NOT end `_revision`)"
      to: "an EMPTY chat transcript at launch (previous run's turns cleared)"
      via: "seedRunChatTranscript([]) inside `if (!isRevision)` (page.tsx:1518-1533)"
      pattern: "seedRunChatTranscript\\(\\[\\]\\)"
    - from: "seedRunChatTranscript([])"
      to: "setMessages([]) + seenRef cleared + lastSeqRef=0 (empty transcript, fresh cursor)"
      via: "the existing seedTranscript reset primitive (useRunChat.ts:387-395)"
      pattern: "setMessages\\(\\[\\]\\)"
---

<objective>
Fix BUG-021 — a FRONTEND-ONLY, ~1-line change — EXACTLY per the grounded spec
`.planning/BUG-021-GROUNDED-CONTEXT.md`. The root cause is VERIFIED to file:line (the `seedTranscript`
reset primitive and the `onStartPipeline` fresh-run reset block were both read directly by the
BUG-019 investigation + orchestrator spot-checks) — do NOT re-investigate or re-debug.

The bug: on a fresh top-level launch performed IN-SESSION after viewing another run, the left chat
lane's HEADER correctly shows the new run (BUG-019/020 already fixed), but the transcript BODY still
renders the PREVIOUS run's messages until the new run's own frames stream in. Root cause: `useRunChat`
holds the transcript in `messages` (useState, init `[]`) and resets it ONLY inside `seedTranscript`
(useRunChat.ts:387-395), which page.tsx calls ONLY on history-open (`seedRunChatTranscript(durableFrames)`,
page.tsx:1336). The fresh-launch handler `onStartPipeline` (page.tsx:1508) NEVER resets the transcript:
its `if (!isRevision)` reset block (page.tsx:1518-1533) clears the preview content +
`setContentSourceRunId(null)` (:1529) + `setContentSourceRunType(null)` (:1532) — but not
`useRunChat.messages`. So the transcript retains the last-VIEWED run's turns until the new run's frames
fold in.

The fix (one line): inside that `if (!isRevision)` block, alongside the content-source clears, add
`seedRunChatTranscript([]);` (already in scope — destructured from `useRunChat` as
`seedTranscript: seedRunChatTranscript` at page.tsx:1014). Calling it with `[]` reuses the existing
reset primitive — clears `messages`/`seenRef`, resets `lastSeqRef=0` — and folds no frames; the new
run's streamed frames then populate the now-empty transcript. NON-REVISION ONLY: a `*_revision` launch
deliberately keeps its content (page.tsx:1534) and continues the conversation, so the reset MUST stay
inside `if (!isRevision)`.

Purpose: a fresh non-revision launch starts a NEW conversation with an EMPTY chat lane — the previous
VIEWED run's turns don't bleed into it; a revision launch still keeps its content.
Output: one ~1-line production edit + one NEW source-lock RED->GREEN test + one useRunChat
characterization case (add-if-missing) + a regression gate. The mocked Playwright carryover repro + the
live Bedrock proof are DEFERRED to the orchestrator (:3000 is the user's).
</objective>

<execution_context>
@/Users/1000060523/Documents/Work/UKI/Flowin/flowin/.claude/gsd-core/workflows/execute-plan.md
</execution_context>

<context>
@.planning/BUG-021-GROUNDED-CONTEXT.md

# FIX SITE. `onStartPipeline` is the inline arrow at page.tsx:1508. `const isRevision =
# type.endsWith("_revision")` is :1509. The fresh-run reset block is `if (!isRevision) { … }` at
# :1518-1533; `setContentSourceRunId(null)` :1529, `setContentSourceRunType(null)` :1532; the block
# CLOSES then `// For revisions, keep existing content visible until new output arrives.` is :1534.
# `seedRunChatTranscript` is destructured from useRunChat as `seedTranscript: seedRunChatTranscript`
# at :1014. History-open calls `seedRunChatTranscript(durableFrames)` at :1336 — do NOT touch it. The
# ONLY production line to ADD is `seedRunChatTranscript([]);` INSIDE the :1518-1533 block. Do NOT touch
# the header derivation (BUG-019/020), the other launch resets, the :1534 revision comment, or anything
# else in this file.
@frontend/src/app/dashboard/page.tsx

# THE RESET PRIMITIVE. `seedTranscript` (useRunChat.ts:387-395) clears `seenRef`, sets
# `lastSeqRef.current = 0`, `setMessages([])`, then folds the passed frames (none for `[]`). It is
# returned from the hook (:397). Do NOT modify this primitive.
@frontend/src/hooks/useRunChat.ts

# THE SANCTIONED SOURCE-LOCK PATTERN to MIRROR for the new wiring test. These read page.tsx via
# readFileSync + `pageSource.replace(/\s+/g, " ")` (collapse whitespace) and assert grep-style on the
# SAME `onStartPipeline` reset block (`setContentSourceRunType(null);` on the fresh-launch reset). The
# comment at the top explains WHY (impractical to exercise in a full render of the huge page.tsx). Copy
# this shape for `freshLaunchTranscriptReset.source.test.ts`.
@frontend/src/app/dashboard/contentSourceRunType.source.test.ts

# THE useRunChat TEST HARNESS to EXTEND (do NOT rewrite existing cases). `makeConn()` (:27-44) exposes
# `subscribe`/`sendCommand`/`emit`; `frame(type, data)` (:47-49) builds a frame with an auto event_id;
# tests `renderHook(() => useRunChat({ runId, subscribe, sendCommand }))` and assert on
# `result.current.messages`. Test 3 (:95-110) already proves the transcript ACCUMULATES (no wipe on
# pipeline_complete) — the seed-empties primitive is NOT covered. ADD one case per Task 2.
@frontend/src/hooks/useRunChat.test.ts
</context>

<constraints>
- Branch feat/ui-2. Verify with `git rev-parse --abbrev-ref HEAD`; DO NOT switch. NO commit trailer
  (no Co-Authored-By / Claude-Session). NEVER push. Worktrees OFF (sequential).
- STRICT SCOPE — exactly THREE files: `page.tsx` (ADD one line INSIDE the :1518-1533 `!isRevision`
  block), `freshLaunchTranscriptReset.source.test.ts` (NEW source-lock test), `useRunChat.test.ts`
  (ADD one characterization case). Nothing else.
- NON-REVISION ONLY: the reset MUST live INSIDE `if (!isRevision)`. Do NOT reset on revisions
  (page.tsx:1534 deliberately keeps content). Do NOT modify `seedTranscript` itself (useRunChat.ts).
  Do NOT touch history-open (`seedRunChatTranscript(durableFrames)`, :1336), the header (BUG-019/020),
  the other launch resets, the SSE parser, the reducer, or the BUG-017/018 changes.
- CAVEAT (flagged): the fix is a one-line WIRING inside page.tsx's inline `onStartPipeline`, which —
  like the BUG-017 adapter — resists an isolated unit import. The runnable RED->GREEN gate is therefore
  the grep-style SOURCE-LOCK test (the established convention here); the faithful mocked-Playwright
  carryover repro + the live proof are the load-bearing checks and are DEFERRED to the orchestrator.
- SC-001: page.tsx is exempt; the reset reuses the EXISTING generic `seedTranscript` primitive — no
  workflow-name literal in the fix or either test.
- FE is cwd-sensitive: run all `tsc` / vitest from INSIDE `frontend/`.
- :3000 IS THE USER'S. The executor MUST NOT run the mocked Playwright suite (it needs :3000) and MUST
  NOT kill/restart the :3000 dev server. Verify ONLY with `npx tsc --noEmit` + vitest (jsdom, no
  server). If the executor authors a mocked Playwright carryover spec it MAY write it, but MUST DEFER
  running the Playwright suite + the live Bedrock proof to the ORCHESTRATOR. Do NOT run live Bedrock.
  Use `localhost:3000` (NOT 127.0.0.1) in any browser note.
- STATE.md quirk: prefer the quick-task table; if `progress:` gets clobbered, restore
  `total_phases:37 completed_phases:35 total_plans:208 completed_plans:207 percent:95`.
</constraints>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: BUG-021 — add `seedRunChatTranscript([]);` inside `onStartPipeline`'s `!isRevision` block; lock the wiring with a source-lock RED->GREEN test</name>
  <files>frontend/src/app/dashboard/page.tsx, frontend/src/app/dashboard/freshLaunchTranscriptReset.source.test.ts</files>
  <behavior>
    One RED source-lock test, then one production line flips it GREEN. Because the inline
    `onStartPipeline` resists an isolated unit render (the reason contentSourceRunType.source.test.ts /
    contentSourceRunScope.source.test.ts exist), the gate is a grep-style source assertion on page.tsx.

    RED — CREATE `freshLaunchTranscriptReset.source.test.ts` (mirror contentSourceRunType.source.test.ts:
    `readFileSync` page.tsx into `pageSource`; `const pageCollapsed = pageSource.replace(/\s+/g, " ")`).
    Three assertions:
      1. PRESENT: `pageSource` contains the exact string `seedRunChatTranscript([]);`.
      2. INSIDE the fresh-run block: on `pageCollapsed`, the substring BETWEEN the marker
         `if (!isRevision) {` and the marker `// For revisions, keep existing content` contains
         `seedRunChatTranscript([]);` — proving the reset sits inside `if (!isRevision)`, not on the
         revision path. (Slice the collapsed string between those two markers and assert
         `.toContain("seedRunChatTranscript([]);")`.)
      3. EXACTLY ONCE: the global-match count of `seedRunChatTranscript([]` in `pageSource` is `1`
         (the history-open call at :1336 uses `durableFrames`, not `[]`, so it does NOT match) —
         proving the reset was not duplicated onto the revision path.
    FAIL-BEFORE: today page.tsx has NO `seedRunChatTranscript([])` anywhere, so assertion 1 (and 2, 3)
    are RED on a `toContain`/count mismatch — NOT a compile/import error.

    GREEN — after the one-line production fix (below), all three assertions pass.
  </behavior>
  <action>
STEP 1 (RED): create `frontend/src/app/dashboard/freshLaunchTranscriptReset.source.test.ts` per the
behavior block, mirroring the imports + `readFileSync` + whitespace-collapse shape of
`contentSourceRunType.source.test.ts`. Run it FIRST — it MUST be RED because page.tsx does not yet
contain `seedRunChatTranscript([])` (a `toContain` / count failure), NOT a compile or import error.
Do NOT edit any existing source-lock test.

STEP 2 (GREEN): apply the ONE-LINE production fix in `page.tsx` — INSIDE the existing `if (!isRevision)`
fresh-run block (:1518-1533), alongside `setContentSourceRunId(null);` (:1529) and
`setContentSourceRunType(null);` (:1532), add `seedRunChatTranscript([]);` (place it after
`setContentSourceRunType(null);`, still INSIDE the block, before the closing brace). Add a short
`// BUG-021:` comment explaining a fresh run starts a NEW conversation so the last-viewed run's
transcript is cleared and the new run's frames fold into the empty list. `seedRunChatTranscript` is
already in scope (destructured as `seedTranscript: seedRunChatTranscript` at :1014). Change NOTHING
else — do NOT reset outside `if (!isRevision)`, do NOT touch the :1534 revision comment, the header
derivation, the other launch resets, or history-open (:1336). Do NOT modify `seedTranscript` in
useRunChat.ts.

Re-run: the source-lock test GREEN, `npx tsc --noEmit` clean. SC-001: reuses the generic
`seedTranscript` primitive — no workflow-name literal.
  </action>
  <verify>
    <automated>cd frontend && npx tsc --noEmit 2>&1 | tail -15</automated>
    <automated>cd frontend && npx vitest --run src/app/dashboard/freshLaunchTranscriptReset.source.test.ts 2>&1 | tail -30</automated>
  </verify>
  <done>page.tsx has `seedRunChatTranscript([]);` INSIDE the `if (!isRevision)` block (:1518-1533), alongside the content-source clears, appearing EXACTLY once (history-open's `seedRunChatTranscript(durableFrames)` at :1336 unchanged). The new source-lock test asserts PRESENT + INSIDE-the-`!isRevision`-block + EXACTLY-once — GREEN (was RED before the fix). tsc clean. No revision-path reset, no `seedTranscript` edit, no other-file change. No workflow-name literal.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Lock the reset PRIMITIVE — add a useRunChat case proving `seedTranscript([])` empties a previously-populated transcript</name>
  <files>frontend/src/hooks/useRunChat.test.ts</files>
  <behavior>
    Characterization of the primitive the wiring reuses (confirmed NOT already covered — the only
    DEF-44-12-4 seed reference is the deferred live e2e `ts-live-state.spec.ts`). This case is GREEN
    both before and after the page.tsx fix (the primitive already works); it locks the contract that a
    fresh-launch `seedRunChatTranscript([])` empties the transcript.

    ADD one case to the `useRunChat — family-anchored transcript reducer` describe block (near Test 3,
    the accumulation case): `renderHook(() => useRunChat({ runId: "run-prev", subscribe: conn.subscribe,
    sendCommand: conn.sendCommand }))`; `conn.emit` two frames from a PREVIOUS run (a `chat_message`
    and a `chat_reply` with `run_id: "run-prev"`); assert `result.current.messages` has length 2; then
    `act(() => result.current.seedTranscript([]))`; assert `result.current.messages` has length 0
    (the fresh-launch reset empties the last-viewed run's turns). Reuse the file's existing `makeConn()`
    + `frame(...)` helpers + `act`/`renderHook` imports.
    FAIL-BEFORE: N/A for the BUG-021 wiring — this is a supporting characterization; it is GREEN
    immediately because `seedTranscript([])` already calls `setMessages([])`. (If it is somehow RED,
    that is a real primitive regression to REPORT, not to force green.)
  </behavior>
  <action>
Add the case per the behavior block. Do NOT rewrite or reorder any existing case (Tests 1-13 + Test 8).
Name it clearly (e.g. "Test 14: seedTranscript([]) empties a previously-populated transcript
(fresh-launch reset)"). Reuse `makeConn`, `frame`, `renderHook`, `act` already imported at the top of
the file. This documents the primitive that Task 1's `seedRunChatTranscript([])` reuses; it is NOT the
RED->GREEN gate for the wiring (that is Task 1's source-lock test).

Run: the new case GREEN, all existing useRunChat cases green, `npx tsc --noEmit` clean. SC-001: keys on
generic run ids / frame types — no workflow-name literal.
  </action>
  <verify>
    <automated>cd frontend && npx tsc --noEmit 2>&1 | tail -15</automated>
    <automated>cd frontend && npx vitest --run src/hooks/useRunChat.test.ts 2>&1 | tail -30</automated>
  </verify>
  <done>useRunChat.test.ts has a new case proving `seedTranscript([])` empties a previously-populated transcript (length 2 -> 0); it is GREEN and all pre-existing useRunChat cases stay green. tsc clean. No existing case rewritten; no `seedTranscript` production edit. No workflow-name literal.</done>
</task>

<task type="auto">
  <name>Task 3: Regression gate — tsc + targeted vitest green; mocked Playwright + live proof DEFERRED to the orchestrator</name>
  <files>(no source edits — acceptance gate; vitest ONLY, NO Playwright, do NOT touch :3000)</files>
  <action>
Prove the fix without regressing, using vitest ONLY (jsdom, needs no server). Do NOT edit source; a real
red here is a problem to REPORT, not to force green.

From `frontend/`:
  - `npx tsc --noEmit` clean.
  - `npx vitest --run src/app/dashboard/freshLaunchTranscriptReset.source.test.ts src/hooks/useRunChat.test.ts`
    — all green (the BUG-021 source-lock wiring gate + the new seed-primitive characterization case +
    the pre-existing useRunChat cases). Note: the ~8 pre-Phase-42 vitest reds in UNTOUCHED files are NOT
    regressions — do not chase them.
  - Sanity: `grep -n "seedRunChatTranscript(\[\])" src/app/dashboard/page.tsx` — confirm EXACTLY one
    match, and that it is inside the `if (!isRevision)` block (before the `// For revisions, keep
    existing content` comment at :1534). The history-open `seedRunChatTranscript(durableFrames)` at
    :1336 must be UNCHANGED.

DO NOT run the mocked Playwright suite and DO NOT kill/restart :3000 — the user is on :3000. If the
executor authored a mocked Playwright carryover spec, it MAY leave it in place but MUST NOT run it.
Running the full Playwright suite (the faithful launch-after-view carryover repro) + the live Bedrock
proof are DEFERRED to the ORCHESTRATOR (after the user finishes checking the app). The orchestrator's
live proof (on localhost:3000): VIEW a run so its chat lane shows a transcript, then launch a FRESH
NON-REVISION run in the same session -> the chat BODY clears immediately (no stale previous-run text);
a REVISION launch still KEEPS its content.

If a vitest goes RED: (1) a flake in an untouched pre-Phase-42 file -> note it as pre-existing;
(2) a REAL BUG-021 failure -> the fix is incomplete, investigate within the declared scope — do NOT
delete/loosen/fixme any test.
  </action>
  <verify>
    <automated>cd frontend && npx tsc --noEmit 2>&1 | tail -10 && npx vitest --run src/app/dashboard/freshLaunchTranscriptReset.source.test.ts src/hooks/useRunChat.test.ts 2>&1 | tail -30</automated>
  </verify>
  <done>tsc clean; both targeted vitest files green (the BUG-021 source-lock wiring gate + the seed-primitive case + all pre-existing useRunChat cases). `seedRunChatTranscript([])` appears exactly once in page.tsx, inside `if (!isRevision)`; history-open at :1336 unchanged. Playwright + the live proof explicitly DEFERRED to the orchestrator — the executor did NOT run Playwright and did NOT touch :3000. Exactly three files changed; no file outside the declared scope; no test deleted/loosened/fixme'd.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| the last-VIEWED run's transcript (`useRunChat.messages`) -> the chat lane on a fresh launch | On a fresh non-revision launch the transcript is NOT reset, so the previous run's turns cross into the new run's conversation until its own frames stream in — an identity boundary keyed on whether the launch is a fresh (`!isRevision`) run vs a revision that continues the same conversation |
| the revision-vs-fresh gate (`type.endsWith("_revision")`) | The reset must fire ONLY on the fresh path; a `*_revision` launch deliberately keeps its content — misplacing the reset outside `if (!isRevision)` would wipe an in-progress revision conversation |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-t9i-01 | Spoofing (identity confusion) | the fresh-run reset block (page.tsx:1518-1533) leaving `useRunChat.messages` populated, so the chat lane MISREPRESENTS the previous run's turns as the new run's conversation | mitigate | Add `seedRunChatTranscript([]);` inside `if (!isRevision)` (reuses the `seedTranscript` primitive: `setMessages([])` + `seenRef` clear + `lastSeqRef=0`); the new run's streamed frames fold into the empty transcript. Guarded by the source-lock RED->GREEN test (present + inside-block + exactly-once) |
| T-t9i-02 | Tampering (revision content loss) | placing the reset outside `if (!isRevision)` would clear an in-progress `*_revision` conversation that deliberately keeps its content (page.tsx:1534) | mitigate | The reset lives INSIDE `if (!isRevision)`; the source-lock test asserts it appears EXACTLY once and only within the fresh-run block (bounded by the `For revisions, keep existing content` comment) — never on the revision path |
| T-t9i-03 | Tampering (regression) | history-open (`seedRunChatTranscript(durableFrames)`, :1336) or the `seedTranscript` primitive being disturbed | accept | History-open and `seedTranscript` are untouched (the new call passes `[]`, not `durableFrames`); the useRunChat characterization case + the exactly-once source-lock count guard against duplication/edit |
| T-t9i-04 | Information disclosure (SC-001) | the fix introducing a workflow-name literal into page.tsx | accept | The reset reuses the EXISTING generic `seedTranscript` primitive; no workflow-name branch is added; tests key on generic run ids / frame types only. page.tsx is SC-001-exempt regardless |
| T-t9i-SC | Tampering | npm/pip installs | accept | No new dependencies — one ~1-line edit to an existing file + two test additions; no package install |
</threat_model>

<verification>
- `cd frontend && npx tsc --noEmit` clean (no backend / SSE / reducer / header change).
- BUG-021 wiring: the NEW source-lock test (`freshLaunchTranscriptReset.source.test.ts`) RED->GREEN —
  asserts `seedRunChatTranscript([]);` is PRESENT, sits INSIDE the `if (!isRevision)` block (bounded by
  the `For revisions, keep existing content` comment), and appears EXACTLY once. RED before the fix
  (page.tsx had no `seedRunChatTranscript([])`), GREEN after.
- Primitive: the NEW useRunChat case proves `seedTranscript([])` empties a previously-populated
  transcript (length 2 -> 0); GREEN, with all pre-existing useRunChat cases green.
- NON-REVISION ONLY: the reset is inside `if (!isRevision)`; history-open (:1336) and the revision path
  (:1534) are unchanged.
- SC-001: no workflow-name literal in the fix or either test — reuses the existing generic
  `seedTranscript` primitive.
- Scope: exactly THREE files changed (page.tsx, freshLaunchTranscriptReset.source.test.ts,
  useRunChat.test.ts). No backend / SSE parser / reducer / header (BUG-019/020) / BUG-017/018 change;
  no `seedTranscript` edit; no revision-path reset.
- :3000 IS THE USER'S — the executor does NOT run the mocked Playwright suite and does NOT kill/restart
  :3000. The faithful mocked-Playwright carryover repro + the LIVE Bedrock proof are DEFERRED to the
  ORCHESTRATOR. Live proof (localhost:3000): view a run (chat populated) -> launch a fresh NON-REVISION
  run in the same session -> the chat BODY clears immediately (no stale previous-run text); a REVISION
  launch still keeps its content. If it still fails, report it — do not silently pass.
</verification>

<success_criteria>
- page.tsx: `seedRunChatTranscript([]);` added INSIDE the `if (!isRevision)` fresh-run block
  (:1518-1533), alongside the content-source clears — a fresh non-revision launch starts with an EMPTY
  chat transcript; the new run's frames fold in afterward.
- The reset appears EXACTLY once and NOT on the revision path; history-open
  (`seedRunChatTranscript(durableFrames)`, :1336) and the `seedTranscript` primitive are unchanged.
- The BUG-021 source-lock wiring test RED->GREEN; the new useRunChat seed-primitive case GREEN; all
  pre-existing useRunChat cases green; tsc clean.
- Exactly three files changed; branch stays feat/ui-2; no push; no commit trailer.
- No backend / SSE parser / reducer / header (BUG-019/020) / BUG-017/018 / `seedTranscript` /
  revision-path change. SC-001: no workflow-name literal.
- The mocked Playwright carryover repro + the live proof DEFERRED to the orchestrator; :3000 never
  touched by the executor.
</success_criteria>

<output>
Create `.planning/quick/260717-t9i-fix-bug-021-frontend-only-1-line-the-lef/SUMMARY.md` when done.
</output>
