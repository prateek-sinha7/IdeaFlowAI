---
phase: quick-260716-uhe
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - frontend/src/components/workflow/LaunchWizard.tsx
  - frontend/src/components/workflow/LaunchWizard.test.tsx
autonomous: true
requirements:
  - BUG-014
must_haves:
  truths:
    - "A FRESH launch (no chain.from → isChaining=false), even with a stale chain.source_run_id lingering in sessionStorage, emits a launch draft with NO sourceRunId → the created run is top-level (no parent_run_id) → live clarify + review gates bind and surface on the live run screen."
    - "chain.source_run_id is consume-once: it is removed from sessionStorage after EVERY launch (fresh or chained), matching its sibling chain.from / chain.brief / chain.context_block keys, so it can never leak into a later launch."
    - "A GENUINE chain (chain.from + chain.source_run_id set → isChaining=true) still threads the source id into the draft (revision-family linkage preserved) AND clears the key afterward."
  artifacts:
    - path: "frontend/src/components/workflow/LaunchWizard.tsx"
      provides: "handleLaunch reads chain.source_run_id ONLY when isChaining, and removes the key consume-once"
      contains: "sessionStorage.removeItem(\"chain.source_run_id\")"
    - path: "frontend/src/components/workflow/LaunchWizard.test.tsx"
      provides: "RED->GREEN: fresh launch does not leak a stale source id + key cleared; genuine chain still threads the id + key cleared"
      contains: "chain.source_run_id"
  key_links:
    - from: "LaunchWizard.handleLaunch (:438)"
      to: "buildLaunchDraft sourceRunId"
      via: "isChaining ? getItem(chain.source_run_id) : undefined, then removeItem"
      pattern: "isChaining \\?"
---

<objective>
Fix BUG-014 (a FRESH "Build interactive prototype" launch from Home leaks a stale
`chain.source_run_id` left in sessionStorage from a previously-viewed/chained run →
every fresh run is created as a CHILD (`parent_run_id` = the stale run) → live clarify
questions + review gates never surface on the live run screen, Stop no-ops, and the run
is hidden from "My Workflows"). Implement EXACTLY the grounded fix from
`.planning/BUG-014-GROUNDED-CONTEXT.md`: gate the `chain.source_run_id` read on the
real-chain flag `isChaining` and make the key consume-once (removeItem), matching its
three sibling chain keys which are already consume-once.

Root cause is orchestrator-verified from the user's live network trace. Do NOT
re-investigate, do NOT touch the DashboardLayout chain writers, page.tsx, the reducer, or
the SSE path.

Purpose: a fresh launch becomes a normal top-level run (clarify + gates surface live); a
genuine chain still passes its source (revision-family linkage) and no longer leaks it.
Output: a 1-line source fix (LaunchWizard.tsx:438) + two RED->GREEN tests.
</objective>

<execution_context>
@/Users/1000060523/Documents/Work/UKI/Flowin/flowin/.claude/gsd-core/workflows/execute-plan.md
</execution_context>

<context>
@.planning/BUG-014-GROUNDED-CONTEXT.md

# Source under change (the ONLY production file)
@frontend/src/components/workflow/LaunchWizard.tsx

# Test harness to extend (clone the WR-07 chain idiom + the base-launch idiom)
@frontend/src/components/workflow/LaunchWizard.test.tsx

# The draft serializer — proves `sourceRunId` is OMITTED from the JSON when falsy
# (`...(sourceRunId ? { sourceRunId } : {})`), so a fresh draft has no sourceRunId key.
@frontend/src/lib/launchDraft.ts

# At-risk source-lock — a genuine chain must STILL send source_workflow_run_id (untouched files)
@frontend/src/app/dashboard/revisionFamilyLinkage.source.test.ts
</context>

<constraints>
- Branch feat/ui-2. Verify with `git rev-parse --abbrev-ref HEAD`; DO NOT switch. NO commit trailer. NEVER push.
- Frontend only, ONE production file: `LaunchWizard.tsx` (+ its test). Do NOT change `DashboardLayout.tsx` chain writers, `page.tsx`, the reducer, the SSE path, or the other chain keys' handling (they are already correct consume-once).
- Do NOT alter the genuine-chain behavior: when `isChaining` is true, the draft MUST still include `sourceRunId` (revision-family linkage).
- Implement the spec's line-438 change EXACTLY: `const sourceRunId = isChaining ? (sessionStorage.getItem("chain.source_run_id") ?? undefined) : undefined;` then `sessionStorage.removeItem("chain.source_run_id");`.
- The spec also says "add `isChaining` to handleLaunch's dependency array" — but `isChaining` is ALREADY in the deps array (LaunchWizard.tsx:480, since :443 already reads it). VERIFY it is present; do NOT add a duplicate. No eslint exhaustive-deps change needed.
- FE is cwd-sensitive: run all vitest/tsc from `frontend/`. (This is a unit-level launch-payload change; mocked Playwright is NOT required — the orchestrator does the live proof. If you do run Playwright, kill anything on :3000 first.)
- SC-001: the fix keys on the `isChaining` flag + the `chain.source_run_id` sessionStorage key only — introduce NO workflow-name literal in the fix or its tests.
- Keep at-risk green: `LaunchWizard.test.tsx` (all existing base/parity/chain tests) and `revisionFamilyLinkage.source.test.ts`. The 8 pre-Phase-42 vitest reds in untouched files are NOT regressions. Executor does NOT run live Bedrock.
</constraints>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: RED — fresh launch must not leak a stale chain.source_run_id (+ genuine chain still threads it and clears the key)</name>
  <files>frontend/src/components/workflow/LaunchWizard.test.tsx</files>
  <behavior>
    Add a new describe block `LaunchWizard — BUG-014: chain.source_run_id must not leak into a fresh launch` with two tests. Clone the existing idioms in this file: `sessionStorage.clear()` runs in beforeEach; the base-prototype launch drives `findByLabelText("Brief")` → type → `getByTestId("pick-web")` → `findByTestId("pick-ds")` → `getByRole("button", { name: "Continue" })`; the launch payload is read via `JSON.parse(sessionStorage.getItem("prototype.draft")!)` (see the base-launch test :120-132 and the WR-07 chain test :337-353).

    Test (a) — FRESH launch leaks a stale id (the PRIMARY red):
    - Seed a STALE key only: `sessionStorage.setItem("chain.source_run_id", "stale-run")`. Do NOT set `chain.from` → the wizard mounts with `isChaining=false` (fresh Home entry).
    - Render `initialMode="prototype"`, type a brief, `pick-web`, `pick-ds`, click Continue.
    - Parse `prototype.draft`. Assert `expect(draft.sourceRunId).toBeUndefined()` — FAIL-BEFORE: line 438 reads the stale id unconditionally → `draft.sourceRunId === "stale-run"` (buildLaunchDraft includes it because it's truthy) → RED.
    - Assert `expect(sessionStorage.getItem("chain.source_run_id")).toBeNull()` — FAIL-BEFORE: the key is never removed → still "stale-run" → RED.

    Test (b) — GENUINE chain still threads the source id AND clears the key (no regression):
    - Seed `chain.from="user_stories"`, `chain.context_block="PRIOR CONTEXT"`, `chain.source_run_id="run-42"` (mirrors WR-07). This makes `isChaining=true` (brief editor hidden).
    - Render `initialMode="prototype"`; `await waitFor` the Brief editor is absent; `findByTestId("pick-ds")`; click Continue.
    - Parse `prototype.draft`. Assert `expect(draft.sourceRunId).toBe("run-42")` — passes before AND after (genuine chaining preserved; this is the anti-regression guard).
    - Assert `expect(sessionStorage.getItem("chain.source_run_id")).toBeNull()` — FAIL-BEFORE: key never cleared → still "run-42" → RED; GREEN after.

    Leave WR-07 and every other existing test UNTOUCHED (they are at-risk and already green).
  </behavior>
  <action>Add the new describe block per the behavior block to LaunchWizard.test.tsx. Do NOT modify LaunchWizard.tsx in this task — both new tests MUST be RED against current source, failing on the SPECIFIED assertions (leaked id / un-cleared key), not on compile or import errors. SC-001: fixtures key on sessionStorage keys + the "stale-run"/"run-42" ids only, never a workflow-name literal.</action>
  <verify>
    <automated>cd frontend && npx vitest --run src/components/workflow/LaunchWizard.test.tsx 2>&1 | tail -30</automated>
  </verify>
  <done>Both new BUG-014 tests exist and FAIL against current code: (a) draft.sourceRunId === "stale-run" (leak) + key not removed; (b) key not removed after a genuine chain. Failures are the specified assertions, not compile errors. All PRE-EXISTING tests in the file still pass.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: GREEN — gate the chain.source_run_id read on isChaining + consume-once removeItem</name>
  <files>frontend/src/components/workflow/LaunchWizard.tsx</files>
  <behavior>Both Task-1 tests GREEN; every pre-existing LaunchWizard.test.tsx test and the revisionFamilyLinkage.source lock stay green.</behavior>
  <action>
In `handleLaunch` (LaunchWizard.tsx:436), REPLACE line 438
  `const sourceRunId = sessionStorage.getItem("chain.source_run_id") ?? undefined;`
with the gated-read + consume-once removeItem EXACTLY as the spec states:
  `const sourceRunId = isChaining ? (sessionStorage.getItem("chain.source_run_id") ?? undefined) : undefined;`
  then on the next line `sessionStorage.removeItem("chain.source_run_id");`
Place the `removeItem` immediately after the read (before the existing `chain.context_block` read at :439) so it always runs on every launch — mirroring how the three sibling chain keys (`chain.from` :186/:201, `chain.brief` :200, `chain.context_block` :440) are consume-once. The read gated on `isChaining` runs BEFORE the removeItem, so a genuine chain still captures "run-42" into `sourceRunId` and then clears the key.
VERIFY `isChaining` is already in the handleLaunch useCallback dependency array (:480) — it is (line 443 already reads it); do NOT add a duplicate and do NOT otherwise touch the deps array.
Change NOTHING else — not the finalBrief composition (:442-445), not buildLaunchDraft wiring, not the discovery hand-off, not any other file.
  </action>
  <verify>
    <automated>cd frontend && npx tsc --noEmit 2>&1 | tail -15</automated>
    <automated>cd frontend && npx vitest --run src/components/workflow/LaunchWizard.test.tsx src/app/dashboard/revisionFamilyLinkage.source.test.ts 2>&1 | tail -25</automated>
  </verify>
  <done>`tsc --noEmit` clean. Both BUG-014 tests GREEN (fresh: no sourceRunId + key cleared; genuine chain: sourceRunId="run-42" + key cleared). All pre-existing LaunchWizard.test.tsx tests (base/parity/WR-07 chain/toggle/discovery/save/restore) stay green. revisionFamilyLinkage.source stays green. No new workflow-name literal introduced (SC-001).</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| sessionStorage (cross-run persisted state) → POST /api/runs body | A stale, run-scoped `chain.source_run_id` persists across navigations and crosses into a launch it does not belong to |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-uhe-01 | Tampering | LaunchWizard.handleLaunch chain.source_run_id read (:438) | mitigate | Gate the read on the real-chain flag `isChaining` + make the key consume-once (removeItem after read), so a stale id can never mislink a fresh launch as a child run |
| T-uhe-02 | Information Disclosure | cross-run parent linkage leaking into an unrelated fresh run | mitigate | Same fix — a fresh launch emits NO sourceRunId → top-level run → correct clarify/gate binding + "My Workflows" visibility |
| T-uhe-SC | Tampering | npm installs | accept | No new dependencies; frontend-only edit to one existing file + its test |
</threat_model>

<verification>
- `cd frontend && npx tsc --noEmit` clean.
- The two new BUG-014 tests are RED before Task 2, GREEN after.
- All pre-existing LaunchWizard.test.tsx tests + revisionFamilyLinkage.source stay green.
- SC-001: no workflow-name literal introduced (the change keys on `isChaining` + the `chain.source_run_id` key only).
- Live proof is the ORCHESTRATOR's, not the executor's: press "Build interactive prototype" FRESH from Home → the created run has NO `parent_run_id`; its clarify questions surface on the LIVE run screen (no reopen) → answer → it builds → the review gate surfaces LIVE → approve → it continues → the run appears in "My Workflows". If gates still fail to surface live for a top-level run, a separate live-binding bug exists — report it, do not silently pass.
</verification>

<success_criteria>
- LaunchWizard.tsx:438 reads `chain.source_run_id` ONLY when `isChaining`, and removes the key consume-once on every launch.
- Fresh launch (isChaining=false) with a stale key present → draft has no sourceRunId + key cleared.
- Genuine chain (isChaining=true) → draft still carries the source id + key cleared afterward (revision-family linkage intact).
- `isChaining` remains in the handleLaunch deps array (already present); no other file changed.
- Branch stays feat/ui-2; no push; no commit trailer.
</success_criteria>

<output>
Create `.planning/quick/260716-uhe-fix-bug-014-a-fresh-home-build-interacti/SUMMARY.md` when done.
</output>
