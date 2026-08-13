---
id: 260812-iqh
slug: iss-082-reducer-frame-identity-for-accum
mode: quick
date: 2026-08-12
branch: bugfix/spec-revision-context-loss
base_commit: 07197b0e
issue: ISS-082
---

# ISS-082 — the reducer's accumulating fields get an identity of their own

## Problem (verified at HEAD `07197b0e`, not recalled)

`handlePipelineMessage` (`frontend/src/hooks/useWorkflow.ts`) owns **seven** fields that
GROW out of their previous value rather than overwrite it. Six have no identity of their
own, so a second delivery of one frame appends a second copy. Correctness is a property
of the reducer's *callers*, not of the reducer — which is exactly the arrangement ISS-080
died of (a wrong number on screen behind 15 green tests).

The ISS-082 register row is right about the concern and wrong about three facts:

1. It names **2** accumulating fields; there are **7** (6 unprotected).
2. Its cited evidence command finds **neither field it names**. Re-run verbatim at HEAD:
   ```
   $ grep -nE '\+= 1|\.push\(|\.concat\(' src/hooks/useWorkflow.ts
   431:        // ... a tally (`+= 1`) cannot tell those      ← a COMMENT
   954:                if (num > 0 && title) allTitles.push(...)  ← a LOCAL array
   ```
   Every real accumulator uses `[...prev.x, y]` or string `+`, which that regex cannot see.
3. `hook_run` was never protected by anything: `kernel_services.py:397-414` pushes the
   frame straight onto the live queue, bypassing the engine's stamping chokepoint
   (`engine.py:1058-1065`), so it arrives with **no `event_id`** — and `wsReplayState.ts:36`
   returns `true` unconditionally for unstamped frames *by design*.

### The seven

| # | field | site | idiom | identity at HEAD |
|---|---|---|---|---|
| 1 | `agents[].thinkingText` | `useWorkflow.ts:461` | string `+` | none |
| 2 | `agents[].output` | `:481` | string `+` | none |
| 3 | `agents[].toolCalls` | `:796` | `[...x, y]` | none |
| 4 | `hookRuns` | `:837` | `[...x, y]` | **none, and un-dedupable end to end** |
| 5 | `agents[].validationIssues` | `:1000` | `[...x, ...y]` | none |
| 6 | `agentStartEventIds` | `:441` | `[...x, y]` | **YES — FIX-225** (the exemplar) |
| 7 | `clarifications` | `:168` | `[...x, y]` | none (UI-driven, not a frame → F5, filed) |

The token totals (`:518-519`) are the **correct** pattern: `agent_complete` overwrites the
per-agent value and recomputes the run total by `reduce`, so they are idempotent by
construction. `protoCompletedTasks` (Map on `t.number` + `Math.max`) likewise — explicitly
out of scope (ISS-087 owns it and supplies its own replay-twice assertion).

### Why it is reachable, not theoretical

- A **partial** redelivery (an SSE resume from `Last-Event-ID` with no intervening
  `agent_start`) duplicates fields 1-5.
- A **full** replay self-heals for the per-agent fields only because `agent_start`'s FIX-039
  reset is a fixed point — but `hookRuns` doubles even then, because nothing resets it.
- `page.tsx:2078-2081` **deliberately replays every durable frame into the reducer a second
  time with the dedup bypassed**, and says so in its own comment at `:2066-2071`.

That bypass exists to work around a latent defect: an inner `const frameRunId` at
`page.tsx:855` **shadows the function parameter** declared at `:501`, so the store-routing
branch at `:910` never fires for a REST-replayed `agent_*` frame.

## Approach — Option A, three layers (Option B rejected)

Option B (five more per-field identity keys) is rejected: it reproduces the anti-pattern
FIX-225's own root-cause note criticises ("introduced it for ONE field instead of promoting
it") and forces a ~25k-entry id set for `agent_chunk` with none of A2a's O(1) escape.

### A1 — backend: stamp `hook_run` (`kernel_services.py`)

Put a uuid `event_id` in the frame's `data`. Keep it **TRANSIENT** — routing it through
`execute()`'s chokepoint would persist a `run_events` row and add a frame to the engine's
yield stream, **changing the golden event multiset (INV-3)**; `_VOLATILE_STRIP_KEYS`
(`_normalize.py:129-130`) strips `seq`/`event_id` but cannot strip a new row.
Verified: `hook_run` appears in **0** of the 10 golden files, so A1 cannot move them.

Trade-off, stated: `hook_run` stays absent from the durable log, so the security bullets
still vanish on reload. Separate gap, deliberately not fixed here.

### A2a — reducer: a per-run monotonic `seq` cursor (`useWorkflow.ts`, `types/index.ts`)

One gate at the top of `handlePipelineMessage`, covering every accumulating case at once by
decorating the dispatcher — not six open-coded checks.

- `lastAppliedSeq?: number` — skip an accumulating frame when `msg.seq <= prev.lastAppliedSeq`.
  **O(1) time and space**, which matters because `agent_chunk` is the highest-volume frame
  in the system (~24,791 events on run `d5dbc9f2`). Chosen over A2b (a `Set` of
  `frameIdentity`), which would copy a 25k-entry set immutably on every frame — O(n²) on replay.
- `appliedUnsequencedIds?: string[]` — the fallback for frames the engine never stamps with a
  `seq`. Only `hook_run` reaches it, so it stays small. **A1 is a prerequisite**: without an
  `event_id` there is nothing to key on, and a frame with no identity must always apply.

Verified preconditions:
- `seq` is allocated by ONE monotonic per-run counter (`engine.py:1028` `next_seq = 1`).
- Both transports carry it: live SSE stamps `data.seq`; `getRunEvents` merges the
  authoritative `seq`/`event_id` **columns** onto the replayed payload (`api.ts:585`).
- Both replay passes are seq-ordered.

Per-run boundary: both fields reset on a `pipeline_start` that is NOT `isSameRunReannounce`
— the same predicate `agentStartEventIds` already uses at `:369` (INV-2).

**INV-12 obligation, precise.** `agentStartEventIds` plays TWO roles: dedup key AND the data
`deriveSpecRevisionCount` reads. Under A2a the `.includes(startIdentity)` guard at `:439`
becomes redundant and **MUST be deleted**; the **array itself STAYS** — it is the derivation
source for the spec-revision banner, and ISS-083 (queued next) reads a value derived from it.

### A3 — page.tsx: un-shadow `:855`, delete the bypass at `:2078-2081`

Ships **with** A2a, never after it: a run-level seq cursor would skip the `:2078` second pass
wholesale, and with the shadow still in place the store would then never receive the
REST-replayed state → regression on history reopen. One change.

**Blast radius is larger than the investigation modelled — measure, do not reason.**
`page.tsx:1682` reconstructs the live message as `{ type, data }`, dropping `_sourceRunId`,
so the inner shadow is `undefined` for **live** agent frames too, not only replayed ones.
A full un-shadow therefore also tightens `isForeignFrame` (`:870`) and `isForActiveRun`
(`:893`) on the live path. If measurement shows a regression, fall back to the narrow
variant — route `:910` on the effective run id and leave both guard verdicts byte-identical
— and file the rest.

## Tasks

### T1 — the new spec, seen RED first
`frontend/src/hooks/useWorkflow.accumulators.test.ts`, built on the **existing** `runFrames`
harness (`useWorkflow.specRevisionCount.test.ts:137`) — do not write a second harness.
- **Part 1**: a declared registry, one row per accumulating field (all 7).
- **Part 2**: three multiplicities per row via `describe.each` — partial redelivery, full
  replay, **triple** delivery (guards a fix correct only at n=2).
- **Part 3 (GUARD-1)**: a source-level assertion that a new accumulator cannot be added
  without a registry row, in the shape this repo already sanctions
  (`deadRevisionRefs.source.test.ts` — "the sanctioned grep-style source assertion").
  Write the regex against the seven known sites FIRST and assert it finds **all seven**;
  the row's own regex is the cautionary example — it matched a comment and a local variable
  and zero real accumulators.

Expected RED (the investigation observed these, at `fab9b646`, on identical frontend files):
`output "Hello worldHello world"`, `thinkingText "step one\nstep one\n"`, `toolCalls 2`,
`validationIssues 2`, `hookRuns 2`; and full-log-×2 → `hookRuns 2`.

### T2 — A1 + A2a + A3 (one commit each, in that order; A2a and A3 ship together)

### T3 — re-measure every baseline, compare IDs not counts

## Verification — measured before, must be re-measured after

| gate | BEFORE (measured on this tree) |
|---|---|
| characterization goldens | **10 passed**; 0 golden files moved |
| `lint-imports` from `backend/` | **4 kept / 0 broken** |
| known pre-existing backend reds | **11 failed / 54 passed** — `test_gates.py` 3, `test_declared_gate_streaming.py` 3, `test_wire_parity.py` 4, `test_prompt_contracts.py` 1 |
| 5 reducer specs | **39 passed / 39** |
| full `npx vitest run` from `frontend/` | **Test Files 29 failed \| 94 passed (123); Tests 147 failed \| 824 passed (971); 34 errors** |
| mocked Playwright | taken on this tree, compare failing **IDs** |

Traps respected: vitest is run **from `frontend/`**; `lint-imports` **from `backend/`**;
`playwright.config.ts:45` sets `reuseExistingServer: true` and a next-server (pid 998) is
live on :3000 with cwd = **this** tree, so the reuse is correct here (it is a worktree
baseline that would silently lie).

## Out of scope — file, do not fold

- F5 `clarifications` accumulates with no per-run reset outside `startPipeline`.
- F6 `validator_result` / `gate_passed` have **zero producers** in non-test backend code, so
  `validationIssues` may be dead on the wire (`gate_blocked` has 3 real producers). Fix the
  accumulator anyway for consistency; the ISS-087 fixer needs to know.
- F7 `hookRuns` has no per-run boundary in the reducer (**unobserved** — flag, do not claim).
- F2 (the deliberate bypass) and F3 (the `frameRunId` shadow) are FIXED here, not filed.

## Invariants

- **INV-3** — additive optional state fields; `undefined` baseline keeps fresh runs
  byte-identical. A1 stays out of the engine's yield stream.
- **INV-12** — A2a supersedes FIX-225's per-field guard: the `.includes` check is DELETED,
  the array is KEPT as the derivation source. A3 deletes `:2078-2081` rather than adding a
  third path. No dual implementation survives.
- **SC-001 / INV-1** — every predicate keys on frame identity (`event_id`/`seq`) and frame
  *type*; never a workflow name, agent id, or artifact kind.
- **INV-2** — the cursor lives in `PipelineRunState`, which is per-run in the store.
- **Ports & Adapters** — A1 touches `kernel_services` (already the `hook_run` emit owner).

## The rule, in one line for the register

*A reducer field that accumulates is not done until a test has fed it the same input twice
and it did not change.*
