---
phase: quick-260717-rs7
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - frontend/src/components/layout/DashboardLayout.tsx
  - frontend/src/components/layout/DashboardLayout.laneTitle.test.tsx
  - frontend/src/components/chat/LaneRunHeader.tsx
  - frontend/src/components/chat/LaneRunHeader.test.tsx
autonomous: true
requirements:
  - BUG-019
  - BUG-020
must_haves:
  truths:
    - "BUG-019 (fresh launch shows the NEW brief, not the previous run's name): on a fresh top-level launch `contentSourceRunId == null`, so `viewedRun` (DashboardLayout.tsx:1381-1384) resolves to `undefined` (was `recentRuns?.[0]` = the PREVIOUS run) → `latestRunTitle` is undefined → `runHeaderTitle` (:1386-1387) resolves to `submittedBrief` (the new brief) instead of the previous run's title. The reopen path (`contentSourceRunId != null`, page.tsx:1279) and the completion path (page.tsx:560) are UNCHANGED — both take the `!= null` branch (keys on `run.id`, SC-001-safe; preserves the BUG-001 reopen decision)."
    - "BUG-019 (no regression): the two BUG-001 cases (laneTitle.test :155, :161 — reopen via a set `contentSourceRunId`) and the BUG-006 type cases (:177, :183, :187) exercise the `!= null` branch (or the type chip, not the title) and stay green. Only the launch title case (:166-169), which ENCODED the bug by asserting `recents[0]`, is rewritten RED->GREEN to assert the title EQUALS `submittedBrief` and does NOT contain `RUN_A.title`."
    - "BUG-020 (the type eyebrow is humanized, not raw snake_case): `LaneRunHeader.tsx:184` humanizes the raw `runType` (`const type = humanizeRunType(runType || pipelineState?.pipeline_type)`) so a reopened/history prototype run whose `runType='od_prototype'` renders the eyebrow 'Prototype' (title-cased, leading 'od' dropped) instead of the CSS-uppercased raw 'OD_PROTOTYPE'. General: every raw type now humanizes (`user_stories`->'User Stories', `app_builder`->'App Builder', `od_prototype_revision`->'Prototype Revision')."
    - "BUG-020 (no regression + locks respected): `humanizeRunType` itself is UNCHANGED (the `od_ppt`->'Ppt' lock at LaneRunHeader.test :38 and the `od_prototype`->'Prototype' unit at :37 stay green). The existing `runType='Prototype'` case (:221-229) stays green because `humanizeRunType` is idempotent on its own title-cased output. The `pipeline_type`-only fallback case (:100-123) stays green (undefined runType -> humanize(pipeline_type) unchanged). The DashboardLayout.laneTitle suite is unaffected because it MOCKS RunChatLane and echoes the RAW `runType` into `lane-run-type` (never rendering the real LaneRunHeader)."
    - "Scope (STRICT): FRONTEND-ONLY, two ~1-line production edits (DashboardLayout.tsx:1384, LaneRunHeader.tsx:184) + two test edits (rewrite one laneTitle case, add one LaneRunHeader case). No backend, no SSE parser, no reducer, no BUG-017/018 changes, no call-site humanize (option a), no transcript reset (the BUG-019 secondary), no `humanizeRunType` edit. SC-001: both fixes use the EXISTING generic transforms — no workflow-name literal."
  artifacts:
    - path: "frontend/src/components/layout/DashboardLayout.tsx"
      provides: "fresh-launch fallback flips from `recentRuns?.[0]` to `undefined` (line 1384) so runHeaderTitle resolves to submittedBrief on a fresh launch; reopen/completion `!= null` branch untouched"
      contains: ": undefined"
    - path: "frontend/src/components/layout/DashboardLayout.laneTitle.test.tsx"
      provides: "the launch title case (:166-169) rewritten RED->GREEN: pass a `submittedBrief`, assert `lane-run-title` EQUALS it and does NOT contain `RUN_A.title` (was asserting `recents[0]` = the bug)"
      contains: "submittedBrief"
    - path: "frontend/src/components/chat/LaneRunHeader.tsx"
      provides: "line 184 humanizes the raw type: `const type = humanizeRunType(runType || pipelineState?.pipeline_type)` so the eyebrow is a humanized label, not raw snake_case"
      contains: "humanizeRunType(runType"
    - path: "frontend/src/components/chat/LaneRunHeader.test.tsx"
      provides: "NEW case (direct RED->GREEN gate): a raw `runType='od_prototype'` renders the `lane-run-type` eyebrow 'Prototype' (RED before: 'od_prototype'); the `od_ppt`->'Ppt' and `od_prototype`->'Prototype' humanizeRunType units + the `runType='Prototype'` idempotent case stay green"
      contains: "od_prototype"
  key_links:
    - from: "fresh top-level launch (contentSourceRunId == null)"
      to: "runHeaderTitle = submittedBrief (the new brief)"
      via: "viewedRun -> undefined -> latestRunTitle undefined -> the `? : submittedBrief` fallback (DashboardLayout.tsx:1384-1387)"
      pattern: ": undefined"
    - from: "raw runType (e.g. 'od_prototype' on the reopened/history path)"
      to: "the humanized `lane-run-type` eyebrow ('Prototype')"
      via: "humanizeRunType wrapping the run) fallback expression (LaneRunHeader.tsx:184)"
      pattern: "humanizeRunType\\(runType"
---

<objective>
Fix TWO FRONTEND-ONLY left-lane-header bugs, each a ~1-line change, EXACTLY per the grounded spec
`.planning/BUG-019-020-GROUNDED-CONTEXT.md`. Both root causes are verified to file:line by
deep-investigation agents + orchestrator spot-checks — do NOT re-investigate or re-debug.

BUG-019 (stale name on a fresh launch): `DashboardLayout.tsx:1381-1387` computes
`viewedRun = contentSourceRunId != null ? recentRuns.find(...) : recentRuns?.[0]`. On a fresh
top-level launch `contentSourceRunId` is null, so `viewedRun` lands on `recentRuns?.[0]` — the
PREVIOUS run (nothing inserts the just-launched run into `recentRuns` at launch). Its real
non-"Untitled" title SHADOWS `submittedBrief` (the new brief) in `runHeaderTitle` (:1386-1387), so
the lane header shows the previous run's name. Fix (:1384): flip the fresh-launch fallback from
`: recentRuns?.[0]` to `: undefined`, so `viewedRun` is undefined on a fresh launch and
`runHeaderTitle` falls through to `submittedBrief`. Reopen (`contentSourceRunId != null`, page.tsx:1279)
and completion (page.tsx:560) are UNCHANGED — they take the `!= null` branch (keys on `run.id`,
preserves the BUG-001 reopen decision).

BUG-020 (raw type eyebrow): `LaneRunHeader.tsx:184` reads
`const type = runType || humanizeRunType(pipelineState?.pipeline_type)` — `runType` is used VERBATIM
and `humanizeRunType` is a dead fallback (production always passes a non-empty `runType`). The raw
snake_case (`od_prototype`) is then CSS-uppercased to "OD_PROTOTYPE". Fix (:184): wrap the whole
fallback in the existing humanizer — `const type = humanizeRunType(runType || pipelineState?.pipeline_type)`
— so the raw type renders "Prototype". Do NOT edit `humanizeRunType` (the `od_ppt`->"Ppt" lock at
LaneRunHeader.test:38) and do NOT humanize at the `DashboardLayout:1777` call site (option a — breaks
5 raw-string assertions in the laneTitle suite that MOCKS RunChatLane). The in-component fix breaks
ZERO tests.

Purpose: a fresh launch shows the NEW brief in the lane header (not the previous run's name), and the
type eyebrow reads a humanized label ("Prototype") instead of raw "OD_PROTOTYPE".
Output: two ~1-line production edits + one rewritten laneTitle case (RED->GREEN) + one new
LaneRunHeader case (RED->GREEN) + a regression gate. Playwright + the live Bedrock proof are DEFERRED
to the orchestrator (:3000 is the user's).
</objective>

<execution_context>
@/Users/1000060523/Documents/Work/UKI/Flowin/flowin/.claude/gsd-core/workflows/execute-plan.md
</execution_context>

<context>
@.planning/BUG-019-020-GROUNDED-CONTEXT.md

# BUG-019 FIX SITE. The `viewedRun` derivation is :1381-1384; `latestRunTitle` :1385; `runHeaderTitle`
# :1386-1387 (`latestRunTitle && latestRunTitle !== "Untitled" ? latestRunTitle : submittedBrief`).
# The ONLY production line to change is :1384 (`: recentRuns?.[0]` -> `: undefined`). `submittedBrief`
# is a DashboardLayoutProps field (:162), passed through at :233; `runHeaderTitle` flows to the lane
# via `runTitle={runHeaderTitle}` (:1776). Do NOT touch the `!= null` branch (:1382-1383) or the
# :1777 `runType={...}` call site. Do NOT touch anything else in this file.
@frontend/src/components/layout/DashboardLayout.tsx

# BUG-019 AT-RISK TEST to REWRITE (do NOT delete/loosen). The launch case is :166-169 — it renders
# `{ recentRuns: [RUN_A, RUN_B, RUN_C], contentSourceRunId: null }` and asserts the title ==
# `RUN_A.title` (recents[0]) — that ENCODES the bug and goes RED after the fix. Rewrite it per Task 1.
# The helper `renderLayout(overrides: Partial<DashboardLayoutProps>)` (:119-143) accepts
# `submittedBrief`. The mock echoes `runTitle`/`runType` into `lane-run-title`/`lane-run-type`
# (:61-68). The BUG-001 reopen cases (:155, :161) and the BUG-006 type cases (:177-190, :219-238) stay
# green — do NOT edit them.
@frontend/src/components/layout/DashboardLayout.laneTitle.test.tsx

# BUG-020 FIX SITE. Line :184 `const type = runType || humanizeRunType(pipelineState?.pipeline_type)`
# is the ONLY production line to change (wrap the fallback expression in `humanizeRunType(...)`).
# `humanizeRunType` (:28-37) splits on _/-/space, DROPS a leading "od", title-cases — it is IDEMPOTENT
# on its own output. The eyebrow renders at :229 with a CSS `uppercase` class (which does NOT turn "_"
# into a space — why raw snake_case looks like "OD_PROTOTYPE"). Do NOT edit `humanizeRunType`. Do NOT
# touch any other line.
@frontend/src/components/chat/LaneRunHeader.tsx

# BUG-020 TEST to EXTEND (do NOT rewrite existing cases). The humanizeRunType units (:30-43) lock
# `od_prototype`->"Prototype" (:37) and `od_ppt`->"Ppt" (:38) — leave them. The settled-header case
# (:94-133) passes `pipeline_type:"od_prototype"` (no runType) and already asserts "Prototype" (:123)
# — stays green. The "prefers an explicit runType" case (:221-229) passes `runType="Prototype"` and
# asserts "Prototype" — stays green (humanize is idempotent). ADD one case per Task 2: raw
# `runType="od_prototype"` -> the `lane-run-type` eyebrow reads "Prototype".
@frontend/src/components/chat/LaneRunHeader.test.tsx
</context>

<constraints>
- Branch feat/ui-2. Verify with `git rev-parse --abbrev-ref HEAD`; DO NOT switch. NO commit trailer
  (no Co-Authored-By / Claude-Session). NEVER push. Worktrees OFF (sequential).
- STRICT SCOPE — exactly FOUR files: BUG-019 touches `DashboardLayout.tsx` (1 line at :1384) +
  `DashboardLayout.laneTitle.test.tsx` (rewrite the ONE launch case :166-169). BUG-020 touches
  `LaneRunHeader.tsx` (1 line at :184) + `LaneRunHeader.test.tsx` (ADD one case). Nothing else.
- Do NOT change `humanizeRunType` (respects the `od_ppt`->"Ppt" lock at LaneRunHeader.test:38). Do NOT
  humanize at the `DashboardLayout:1777` call site (option a — breaks 5 raw-string assertions in the
  laneTitle suite). Do NOT reset the chat transcript (the flagged BUG-019 secondary — the
  `useRunChat.messages`/`firstUserTurn` staleness is MASKED post-fix and is out of scope). Do NOT
  touch the backend, the SSE parser, the reducer, or the BUG-017/018 changes. The migration-flow
  labels (`mulesoft_to_springboot`->"MULESOFT TO SPRINGBOOT") and a nicer PPT/"Presentation" label are
  awkward-but-rare product polish — OUT OF SCOPE.
- SC-001: both fixes use the EXISTING generic transforms (`humanizeRunType` / key-on-`run.id`) —
  compliant; no workflow-name literal in any fix or test.
- FE is cwd-sensitive: run all `tsc` / vitest from INSIDE `frontend/`.
- :3000 IS THE USER'S. The executor MUST NOT run the mocked Playwright suite (it needs :3000) and MUST
  NOT kill/restart the :3000 dev server. Verify ONLY with `npx tsc --noEmit` + vitest (jsdom, no
  server). Running the full Playwright suite + the live Bedrock proof is DEFERRED to the ORCHESTRATOR
  (after the user finishes checking the app). Use `localhost:3000` (NOT 127.0.0.1) in any browser note.
- STATE.md quirk: prefer the quick-task table; if `progress:` gets clobbered, restore
  `total_phases:37 completed_phases:35 total_plans:208 completed_plans:207 percent:95`.
</constraints>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: BUG-019 — flip the fresh-launch fallback to `undefined` so the lane header shows the new brief; rewrite the launch title case RED->GREEN</name>
  <files>frontend/src/components/layout/DashboardLayout.tsx, frontend/src/components/layout/DashboardLayout.laneTitle.test.tsx</files>
  <behavior>
    One RED test, then one production line flips it GREEN; every other laneTitle case stays green.

    RED — REWRITE the existing launch case `DashboardLayout.laneTitle.test.tsx:166-169` ("launch flow
    (contentSourceRunId null) keeps the recents[0] title — byte-identical"). It currently renders
    `{ recentRuns: [RUN_A, RUN_B, RUN_C], contentSourceRunId: null }` and asserts
    `lane-run-title` toHaveTextContent(`RUN_A.title`) — that ENCODES the bug. Rewrite it to:
      - rename the case to describe the FIXED behavior (e.g. "launch flow (contentSourceRunId null)
        shows the submitted brief, NOT the previous run (recents[0])");
      - render `renderLayout({ recentRuns: [RUN_A, RUN_B, RUN_C], contentSourceRunId: null,
        submittedBrief: "Fresh brand-new brief for a task tracker" })` (a string that does NOT contain
        `RUN_A.title` = "Analytics dashboard for a fitness app");
      - assert `screen.getByTestId("lane-run-title")` toHaveTextContent the submittedBrief string AND
        `.not.toHaveTextContent(RUN_A.title)`.
    FAIL-BEFORE: with today's `: recentRuns?.[0]`, `viewedRun = RUN_A`, `latestRunTitle = RUN_A.title`
    (non-"Untitled") so `runHeaderTitle = RUN_A.title` -> the title contains `RUN_A.title` and NOT the
    brief -> RED on both new assertions (not a compile/import error).

    GREEN — after the one-line production fix (below), `viewedRun = undefined` on the null branch ->
    `latestRunTitle` undefined -> `runHeaderTitle = submittedBrief` -> the title equals the brief and
    excludes `RUN_A.title` -> GREEN. The BUG-001 reopen cases (:155, :161) and the BUG-006 type cases
    (:177-190, :219-238) exercise the `!= null` branch (or the type chip, not the title) -> stay green.
  </behavior>
  <action>
STEP 1 (RED): rewrite the launch case at `DashboardLayout.laneTitle.test.tsx:166-169` per the behavior
block and run it FIRST — it MUST be RED on the SPECIFIED assertions (title == the submittedBrief, not
`RUN_A.title`), NOT on a compile/import error. `renderLayout` (:119-143) already accepts
`submittedBrief` (it is a DashboardLayoutProps field, :162). Do NOT edit any other case in the file.

STEP 2 (GREEN): apply the ONE-LINE production fix in `DashboardLayout.tsx`, the `viewedRun` fallback
(:1384):
  FROM  `: recentRuns?.[0];`
  TO    `: undefined;`
This makes a fresh launch (`contentSourceRunId == null`) resolve `viewedRun = undefined` ->
`latestRunTitle` undefined -> `runHeaderTitle = submittedBrief`. The `!= null` branch (:1382-1383,
reopen + completion) is UNCHANGED — it still finds the viewed run by id (SC-001-safe, preserves the
BUG-001 reopen decision). Change NOTHING else in the file — not the `!= null` branch, not the :1386
ternary, not the :1776/:1777 call site. (Pure idle with no submittedBrief now yields an empty title
instead of a foreign run's title — acceptable / arguably more correct; do NOT add extra handling.)

Re-run: the rewritten launch case GREEN, all other laneTitle cases green, `npx tsc --noEmit` clean.
SC-001: keys on `contentSourceRunId`/`run.id` + `submittedBrief` — no workflow-name literal.
  </action>
  <verify>
    <automated>cd frontend && npx tsc --noEmit 2>&1 | tail -15</automated>
    <automated>cd frontend && npx vitest --run src/components/layout/DashboardLayout.laneTitle.test.tsx 2>&1 | tail -30</automated>
  </verify>
  <done>DashboardLayout.tsx:1384 reads `: undefined;`. The rewritten launch case asserts `lane-run-title` == the submittedBrief and NOT `RUN_A.title` — GREEN (was RED before the fix). The BUG-001 reopen cases (:155, :161) and the BUG-006 type cases stay green. tsc clean. No `!= null` branch / call-site / other-file change. No workflow-name literal.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: BUG-020 — humanize the raw type at LaneRunHeader.tsx:184; add a raw-runType RED->GREEN case</name>
  <files>frontend/src/components/chat/LaneRunHeader.tsx, frontend/src/components/chat/LaneRunHeader.test.tsx</files>
  <behavior>
    One RED test, then one production line flips it GREEN; the locked humanizeRunType units and the
    existing header cases stay green.

    RED — ADD a new `LaneRunHeader` case (near the "prefers an explicit runType" case :221-229): render
    `<LaneRunHeader runState="complete" runType="od_prototype" pipelineState={ps({ pipeline_type:
    "od_prototype" })} />` and assert `screen.getByTestId("lane-run-type")` toHaveTextContent
    "Prototype" (name it e.g. "humanizes a RAW snake_case runType in the eyebrow"). Reuse the file's
    existing `ps(...)` helper + imports.
    FAIL-BEFORE: today `const type = runType || humanizeRunType(...)` uses `runType` VERBATIM -> the
    eyebrow textContent is the raw "od_prototype" (CSS uppercase does not change textContent, and does
    not convert "_" to a space) -> asserting "Prototype" -> RED (not a compile/import error).

    GREEN — after the one-line production fix (below), `humanizeRunType("od_prototype")` = "Prototype"
    -> GREEN. No-regression: the humanizeRunType units (:30-43, incl. `od_ppt`->"Ppt" :38 and
    `od_prototype`->"Prototype" :37) are untouched; the settled-header case (:94-133, undefined runType
    -> humanize(pipeline_type) "Prototype") stays green; the "prefers an explicit runType" case
    (:221-229, `runType="Prototype"`) stays green because `humanizeRunType` is idempotent on its own
    title-cased output.
  </behavior>
  <action>
STEP 1 (RED): add the new case per the behavior block and run it FIRST — it MUST be RED because the
raw "od_prototype" renders instead of "Prototype", NOT a compile error. Do NOT edit the humanizeRunType
units (:30-43) or any existing LaneRunHeader case.

STEP 2 (GREEN): apply the ONE-LINE production fix in `LaneRunHeader.tsx:184` (option b — least blast
radius, verified ZERO test breakage):
  FROM  `const type = runType || humanizeRunType(pipelineState?.pipeline_type);`
  TO    `const type = humanizeRunType(runType || pipelineState?.pipeline_type);`
This humanizes the raw `runType` (dropping a leading "od", splitting on "_", title-casing) before the
existing CSS uppercase at :229. Change NOTHING else — do NOT edit `humanizeRunType` itself (the
`od_ppt`->"Ppt" lock), do NOT humanize at the `DashboardLayout:1777` call site (option a), do NOT touch
any other line in this file.

Re-run: the new case GREEN, the humanizeRunType units + the two existing header cases green,
`npx tsc --noEmit` clean. SC-001: `humanizeRunType` is a generic transform — no workflow-name literal.
  </action>
  <verify>
    <automated>cd frontend && npx tsc --noEmit 2>&1 | tail -15</automated>
    <automated>cd frontend && npx vitest --run src/components/chat/LaneRunHeader.test.tsx 2>&1 | tail -30</automated>
  </verify>
  <done>LaneRunHeader.tsx:184 reads `const type = humanizeRunType(runType || pipelineState?.pipeline_type);`. The new raw-runType case (`runType="od_prototype"` -> eyebrow "Prototype") is GREEN (RED before). The humanizeRunType units (incl. `od_ppt`->"Ppt", `od_prototype`->"Prototype"), the settled-header case, and the `runType="Prototype"` idempotent case stay green. tsc clean. No `humanizeRunType` edit, no call-site change. No workflow-name literal.</done>
</task>

<task type="auto">
  <name>Task 3: Regression gate — tsc + targeted vitest green; Playwright + live proof DEFERRED to the orchestrator</name>
  <files>(no source edits — acceptance gate; vitest ONLY, NO Playwright, do NOT touch :3000)</files>
  <action>
Prove both fixes without regressing the lane header, using vitest ONLY (jsdom, needs no server). Do
NOT edit source; a real red here is a problem to REPORT, not to force green.

From `frontend/`:
  - `npx tsc --noEmit` clean.
  - `npx vitest --run src/components/layout/DashboardLayout.laneTitle.test.tsx src/components/chat/LaneRunHeader.test.tsx`
    — all green (BUG-019 rewritten launch case + the BUG-001/BUG-006 cases; BUG-020 new raw-runType
    case + the humanizeRunType units + the existing header cases). Note: the ~8 pre-Phase-42 vitest
    reds in UNTOUCHED files are NOT regressions — do not chase them.
  - Optional sanity: `grep -rn "recentRuns?.\[0\]" src/components/layout/DashboardLayout.tsx` — confirm
    line 1384 no longer matches inside the `viewedRun` ternary (the :476 `latestRun = recentRuns?.[0]`
    is a DIFFERENT, unrelated derivation — leave it).

DO NOT run the mocked Playwright suite and DO NOT kill/restart :3000 — the user is on :3000. Running
the full Playwright transport/chat/history suite (e.g. ts-chat, ts-t.history) + establishing the real
before/after green counts + the live Bedrock proof are ALL DEFERRED to the ORCHESTRATOR (after the
user finishes checking the app). The orchestrator's live proof (on localhost:3000): a FRESH
`user_stories` launch -> the lane header shows the NEW brief, not the previous run's title; a prototype
REOPEN from history -> the type eyebrow reads "PROTOTYPE" (humanized), not "OD_PROTOTYPE".

If a vitest goes RED: (1) a flake in an untouched pre-Phase-42 file -> note it as pre-existing;
(2) a REAL BUG-019/BUG-020 failure -> the fix is incomplete, investigate within the declared scope —
do NOT delete/loosen/fixme any test.
  </action>
  <verify>
    <automated>cd frontend && npx tsc --noEmit 2>&1 | tail -10 && npx vitest --run src/components/layout/DashboardLayout.laneTitle.test.tsx src/components/chat/LaneRunHeader.test.tsx 2>&1 | tail -30</automated>
  </verify>
  <done>tsc clean; both targeted vitest files green (BUG-019 rewritten launch case + BUG-020 new raw-runType case + all pre-existing cases in those two files). Playwright + the live proof explicitly DEFERRED to the orchestrator — the executor did NOT run Playwright and did NOT touch :3000. Exactly four files changed; no file outside the declared scope; no test deleted/loosened/fixme'd.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| the run-lane header title derivation (`DashboardLayout` `runHeaderTitle`) -> the LaneRunHeader `lane-run-title` | On a fresh launch the fallback picks a run from `recentRuns` that is NOT the just-launched run; the identity boundary is whether `contentSourceRunId` is set — an unset id must NOT silently borrow the previous run's title |
| the raw workflow-type string (`runType`) -> the presented `lane-run-type` eyebrow | The raw snake_case engine-domain string (`od_prototype`) crosses into a user-facing label; it must pass through the generic `humanizeRunType` transform (never a workflow-name branch) before display |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-rs7-01 | Spoofing (identity confusion) | `viewedRun` fallback (DashboardLayout.tsx:1381-1384) — a fresh launch borrows `recentRuns?.[0]`'s title, so the header MISREPRESENTS the new run as the previous one | mitigate | Flip the fresh-launch fallback to `undefined` so `runHeaderTitle` resolves to `submittedBrief` (the actual new brief); the `!= null` reopen/completion branch is untouched. Guarded by the rewritten laneTitle launch case (RED->GREEN: title == submittedBrief, != RUN_A.title) |
| T-rs7-02 | Tampering (raw data leak into UI) | the `lane-run-type` eyebrow (LaneRunHeader.tsx:184) rendering the raw snake_case type instead of a humanized label | mitigate | Wrap the fallback in the existing `humanizeRunType` (drops leading "od", splits "_", title-cases); guarded by the new raw-`runType` RED->GREEN case. `humanizeRunType` itself is unchanged (the `od_ppt`->"Ppt" lock preserved) |
| T-rs7-03 | Tampering (regression) | the reopen/completion title path + the locked humanizeRunType units + the laneTitle type chips | accept | The `!= null` branch and `humanizeRunType` are untouched; the laneTitle suite MOCKS RunChatLane (raw-string echo) so the eyebrow humanize never reaches it; idempotent humanize keeps the `runType="Prototype"` case green. Existing cases guard all of this |
| T-rs7-04 | Information disclosure (SC-001) | either fix introducing a workflow-name literal into a guarded FE component | accept | Both fixes reuse EXISTING generic transforms (key-on-`run.id`/`contentSourceRunId`; `humanizeRunType`) — no workflow-name branch is added; tests key on generic ids/type strings only |
| T-rs7-SC | Tampering | npm/pip installs | accept | No new dependencies — two ~1-line edits to existing files + two test edits; no package install |
</threat_model>

<verification>
- `cd frontend && npx tsc --noEmit` clean (no backend / SSE / reducer change).
- BUG-019: the laneTitle launch case (:166-169) rewritten RED->GREEN — asserts `lane-run-title` ==
  `submittedBrief` and NOT `RUN_A.title`; RED before the `: undefined` fix (title was RUN_A.title),
  GREEN after. The BUG-001 reopen cases (:155, :161) and the BUG-006 type cases stay green.
- BUG-020: the NEW `LaneRunHeader` case (raw `runType="od_prototype"` -> eyebrow "Prototype")
  RED->GREEN; RED before the `humanizeRunType(...)` wrap (raw "od_prototype"), GREEN after. The
  humanizeRunType units (incl. `od_ppt`->"Ppt" :38, `od_prototype`->"Prototype" :37), the
  settled-header case (:94-133), and the `runType="Prototype"` idempotent case (:221-229) stay green.
- SC-001: no workflow-name literal in either fix or test — both use the existing generic transforms.
- Scope: exactly FOUR files changed (DashboardLayout.tsx, DashboardLayout.laneTitle.test.tsx,
  LaneRunHeader.tsx, LaneRunHeader.test.tsx). No backend / SSE parser / reducer / BUG-017/018 change;
  no call-site humanize (option a); no transcript reset; no `humanizeRunType` edit.
- :3000 IS THE USER'S — the executor does NOT run the mocked Playwright suite and does NOT kill/restart
  :3000. The full Playwright transport/chat/history suite + the real before/after counts + the LIVE
  Bedrock proof are ALL DEFERRED to the ORCHESTRATOR (after the user finishes checking the app). Live
  proof (localhost:3000): a fresh `user_stories` launch -> the header shows the NEW brief, not the
  previous run; a prototype reopen -> the eyebrow reads "PROTOTYPE" not "OD_PROTOTYPE". If it still
  fails, report it — do not silently pass.
</verification>

<success_criteria>
- DashboardLayout.tsx:1384: `: undefined;` — a fresh launch (`contentSourceRunId == null`) resolves
  `viewedRun = undefined` so `runHeaderTitle = submittedBrief` (the new brief), not the previous run's
  title; the reopen/completion `!= null` branch is unchanged.
- LaneRunHeader.tsx:184: `const type = humanizeRunType(runType || pipelineState?.pipeline_type);` — the
  type eyebrow renders a humanized label ("Prototype") instead of raw "OD_PROTOTYPE"; `humanizeRunType`
  itself is unchanged (the `od_ppt`->"Ppt" lock preserved).
- BUG-019 launch case rewritten RED->GREEN; BUG-020 new raw-runType case RED->GREEN; all pre-existing
  cases in both targeted files green; tsc clean.
- Exactly four files changed; branch stays feat/ui-2; no push; no commit trailer.
- No backend / SSE parser / reducer / BUG-017/018 / call-site (option a) / transcript-reset /
  `humanizeRunType` change. SC-001: no workflow-name literal.
- Playwright + the live proof DEFERRED to the orchestrator; :3000 never touched by the executor.
</success_criteria>

<output>
Create `.planning/quick/260717-rs7-fix-bug-019-bug-020-frontend-only-lane-h/SUMMARY.md` when done.
</output>
