---
task: 260812-4ss
title: fix ISS-080 + ISS-081 + ISS-075 — correct the revision count and the reopen roster reset
date: 2026-08-12
status: complete
commits:
  code: c46c8160
ids:
  fix: FIX-225
  test: TEST-009
  closed: [ISS-080, ISS-081, ISS-075]
  filed: [ISS-082, ISS-083]
branch: bugfix/spec-revision-context-loss
pushed: false
---

# Summary — quick 260812-4ss

Three defects on one reopen-replay path, fixed as ONE change. Frontend only; the engine
was deliberately not touched, so the characterization goldens did not move.

## What landed

**One root cause under all three: a missing concept.** The frontend had no predicate for
*"this `pipeline_start` re-announces the run I am already showing"*. FIX-221 introduced
that test for exactly one field (`useWorkflow.ts:306-309`) instead of promoting it, so
the same trailing frame still (a) wiped the event-id dedup seen-set and (b) rebuilt the
agent roster. The predicate is now computed once in the reducer's `pipeline_start`
updater and has a page-side twin gating `resetReplayState` (INV-12 — one concept, one
expression).

| id | fix |
|---|---|
| **ISS-080** | `agentStartCounts` (a bare `+= 1`, no identity key) REPLACED by `agentStartEventIds: Record<agentId, string[]>` — a SET of durable event identities (`event_id`, else `seq`; unstamped legacy frames stay un-deduped exactly as `shouldApplyEvent` treats them). Plus the class-level half: `page.tsx` no longer calls `resetReplayState` for a same-run `pipeline_start`, so the seen-set survives the replay and the SSE pass is fully deduped against the REST pass. |
| **ISS-081** | `deriveSpecRevisionCount` now counts restarts of the pipeline HEAD (`state.agents[0].id`) instead of taking `max` over every agent. |
| **ISS-075** | On a same-run re-announcement the roster is MERGED, not rebuilt: identity fields from the frame, live `status`/`output`/`duration`/tokens preserved, `completedCount = max(agents done, resumeOffset)`. The proto task carry-overs ride the same predicate. |

## Why the ISS-081 scoping is SC-001-safe

The head is **positional** — `state.agents[0]`, the first step of whatever roster the
compiled manifest announced on `pipeline_start`. The expression contains no agent id, no
workflow name and no artifact `kind`, so a custom workflow gets the same rule for free.
Hardcoding `prototype-specify` would have been a workflow-name branch and is forbidden.

Verified against both real durable logs rather than reasoned about:
`d5dbc9f2` head = 3 starts → **2** (truth: `spec` v1/v2/v3); `6e38b9a7` head = 2 starts →
**1** (truth: one revision), with `prototype-build`'s 11 task-loop starts correctly
ignored.

**Accepted limitation, recorded not hidden:** a workflow whose revision window excludes
step 0 under-reports (the banner stays hidden) instead of over-reporting — a strictly
better failure mode than the 10x over-report it replaces.

## Fail-before / pass-after

Every new case observed RED against the unmodified source:

| test | RED before | GREEN after |
|---|---|---|
| double delivery yields 2 | `expected 5 to be 2` | ✅ |
| triple delivery yields 2 | `expected 8 to be 2` | ✅ |
| per-agent tally under double delivery | `{specify:6, plan:4, analyze:4}` vs `{3,2,2}` | ✅ |
| build loop (run 6e38b9a7) yields 1 | `expected 10 to be 1` | ✅ |
| build loop doubled yields 1 | `expected 21 to be 1` | ✅ |
| no-revision run with a task loop yields 0 | `expected 10 to be +0` | ✅ |
| roster survives the trailing resume frame | `[]` vs `[specify, plan, analyze]` | ✅ |
| completedCount survives it | `expected +0 to be 3` | ✅ |
| roster survives a NON-zero offset | `[specify]` vs `[specify, plan]` | ✅ |

`5` and `{6,4,4}` are exactly what the live browser measured, so the unit test reproduces
the field defect rather than a model of it.

## Gates

- Frontend vitest **147 red / 808 green before → 147 red / 820 green after**, 29 failed
  files both sides, and `comm` over the sorted failing-id sets shows **zero** new reds and
  zero coincidental fixes. The +12 are exactly the new cases.
- `tsc --noEmit`: 2 errors, both in files this change never touched. No new errors.
- Token-layer gate 9/9. Related reducer + replay suites 79/79.
- Characterization goldens **10 passed / 0 failed** and `lint-imports` **4 kept / 0
  broken** — both identical to the pre-change commit `f353a1a9`.

## Live proof (mandatory — unit tests are what missed this)

Run `d5dbc9f2-dbe8-480f-8b13-788794a6788e` reopened from Run History on a fresh load,
real backend on `:8010`, headless Chromium (`scratchpad/verify-260812-4ss.mjs`):

```
banner        : Spec Revision Cycle 2      (pre-fix: Spec Revision Cycle 5)
roster header : 3/5 agents                 (pre-fix: 0/5 agents)
steps rows    : disabled=false "Spec Writer Agent 1m 42s · 42.4K tok"
                disabled=false "Task Planner Agent 2m 19s · 46.6K tok"
                disabled=false "Spec Kit Analyzer 24s · 37.0K tok"
                disabled=true  "Build Agent"       (never ran — correct)
                disabled=true  "Validation Agent"  (never ran — correct)
page errors   : (none)
```

Screenshots: `verify-4ss-after-01-run.png`, `verify-4ss-after-02-steps.png`, against the
pre-fix `live-04-steps.png` — the same screen, before and after.

## The investigation's open question — ANSWERED

`REOPEN-REPLAY-ANALYSIS` §1.5/§10 could not reconcile "blocking the REST fetch removes
the doubling" with `page.tsx:837-841,892` saying REST-replayed `agent_*` frames cannot
reach the store. Both statements are true:

1. The inner `const frameRunId` (`:837`) **shadows the function parameter** and is
   `undefined` for those frames (no `_sourceRunId`, no `pipeline_run_id` in the payload),
   so the store dispatch at `:892` is indeed skipped.
2. `isForActiveRun` (`:875`) is `true` **for exactly that reason** (`!frameRunId || …`),
   so `handlePipelineMsgRef` at `:897` **does** apply them to `useWorkflow.pipelineState`.
3. The FIX-201 bridge effect at `page.tsx:1640-1649` then pushes that whole state object
   into the store wholesale (`runStore.updatePipelineState(runId, () => pipelineState)`).

The SSE pass increments on top of that copied base. That is the transfer step. **No third
delivery path exists.**

## Filed, not fixed

- **ISS-082** (minor) — the sibling accumulators `agent_chunk` (`output + chunk`) and
  `hookRuns` (`push`) carry no identity key either; they are now protected only by the
  class-level seen-set fix, i.e. by an external guarantee — the exact arrangement that
  failed for ISS-080.
- **ISS-083** (trivial) — `ResultCard.tsx:97-100,119` renders `Revising spec — cycle
  {cycle ?? 1}` and nothing passes `cycle`: a third, dormant counter in this family.

## Also worth knowing

`page.tsx:2054-2063` (`handleSwitchToLiveRun`'s deliberately un-deduped direct store
replay) was flagged as a likely live-path twin of ISS-080 because its `hasLiveAgents`
guard is defeated by ISS-075's all-idle roster. Both halves of that are now gone: the
roster merge restores the guard, and the identity-keyed counter makes an un-deduped
replay harmless.

Not pushed.
