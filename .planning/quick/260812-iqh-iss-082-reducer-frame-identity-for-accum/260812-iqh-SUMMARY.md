---
id: 260812-iqh
slug: iss-082-reducer-frame-identity-for-accum
status: complete
date: 2026-08-12
branch: bugfix/spec-revision-context-loss
base_commit: 07197b0e
issue: ISS-082
commits:
  - 4c006e24 test(hooks): every accumulating reducer field, fed its input twice (ISS-082, red)
  - 46d567a0 fix(engine): stamp the transient hook_run frame with an event_id (ISS-082)
  - e1ce97a4 fix(hooks): the reducer keeps its own frame identity (ISS-082)
---

# ISS-082 — the reducer's accumulating fields got an identity of their own

## What shipped

**A1 — `backend/agents/execution_engine/kernel_services.py`.** `emit_hook_event` now stamps
the transient `hook_run` frame with a uuid `event_id`. It stays out of `execute()`'s
chokepoint on purpose: routing it there would persist a `run_events` row and add a frame to
the engine's yield stream, changing the golden event multiset (INV-3). `emit_hook_event` is
the single emitter, so one stamp covers every producer.

**A2a — `frontend/src/hooks/useWorkflow.ts` + `types/index.ts`.** One identity gate,
installed by decorating the dispatcher rather than open-coded six times, so a future
accumulating case is protected by adding its type to `ACCUMULATING_FRAME_TYPES` and nothing
else. `lastAppliedSeq` (an O(1) per-run monotonic cursor) decides every persisted frame;
`appliedUnsequencedIds` catches the one frame the engine never stamps. Both reset on a
`pipeline_start` that is not a same-run re-announcement.

**A3 — `frontend/src/lib/wsReplayState.ts` + `app/dashboard/page.tsx`.** The shadowed
`frameRunId` is replaced by `resolveFrameRunId(msg, sourceRunId)`, a pure function beside
its siblings, and FIX-201's second, undeduped replay loop is deleted.

**The generalised rule, made mechanical** — `useWorkflow.accumulators.test.ts`: a declared
registry of all seven accumulating fields, three multiplicities each, plus GUARD-1, a
source assertion that fails if the reducer grows an accumulator with no registry row.

## The register row was right about the concern and wrong about three facts

1. It names **2** accumulating fields. There are **7** (6 unprotected).
2. Its cited command finds **neither field it names**. Re-run verbatim at HEAD `07197b0e`:
   `grep -nE '\+= 1|\.push\(|\.concat\(' src/hooks/useWorkflow.ts` returns a **comment**
   (`:431`) and a **local array** (`:954`). Every real accumulator uses `[...prev.x, y]` or
   string `+`, which that regex cannot see — a 3.5× under-report.
3. `hook_run` was never protected by anything, not "protected only by the class-level fix".

GUARD-1's detector keys on the structural invariant instead — **a property whose value both
READS its own previous value and GROWS it** — validated against the seven known sites before
being trusted. It finds exactly 7 and zero false positives. The one growth-only line it
correctly excludes is `totalTokens: totalInput + totalOutput`, which recomputes from
overwritten values: the pattern the six broken fields should have imitated.

## Seen RED first — 12 failures, matching the investigation's observed values

| field | partial redelivery | full replay | triple |
|---|---|---|---|
| `output` | `"Hello worldHello world"` | converges | `…×3` |
| `thinkingText` | `"step one\nstep one\n"` | converges | `…×3` |
| `toolCalls` | 2 | converges | 3 |
| `validationIssues` | 2 | converges | 3 |
| `hookRuns` | 2 | **2** | 3 |
| `agentStartEventIds` | 1 (control, FIX-225) | 1 | 1 |

Plus "a genuinely NEW frame after a re-delivery still applies" → `"Hello worldHello world!"`.
`hookRuns` is the only field that also doubles on a FULL replay: `agent_start`'s FIX-039
reset is what makes the others converge, and nothing resets `hookRuns`.

## INV-12

FIX-225's per-field `.includes(startIdentity)` guard is **DELETED**; the
`agentStartEventIds` **array SURVIVES** — it is what `deriveSpecRevisionCount` reads, and
ISS-083 (queued next) reads a value derived from it. `deadRevisionRefs.source.test.ts`,
which source-locks that field, is green.

`liveRunSwitch.fix201.test.ts`'s `expect(body).toContain("runStore.get(runId)")` source-locked
the deleted bypass. **Reconciled, not relaxed, and now tighter** — it forbids the second pass
instead of requiring it. Proved non-vacuous by re-injecting the bypass (red) and removing it
again (green).

## Measured — before and after, on this tree

| gate | BEFORE | AFTER |
|---|---|---|
| characterization goldens | 10 passed, 0 files moved | **10 passed, 0 files moved** |
| `lint-imports` (from `backend/`) | 4 kept / 0 broken | **4 kept / 0 broken** |
| backend known reds | 11 failed / 54 passed | **11 failed / 54 passed — IDENTICAL ID set** |
| `npx vitest run` (from `frontend/`) | 147 failed \| 824 passed (971); 34 errors | **147 failed \| 860 passed (1007); 34 errors** |
| vitest newly-red / newly-green | — | **0 / 0** |
| mocked Playwright | 33 failed / 43 skipped / 108 passed | **33 failed / 43 skipped / 108 passed** |
| `tsc --noEmit` | 2 errors (pre-existing test files) | **same 2; none in any file touched** |

Three mutation tests confirm the new assertions are load-bearing, not decoration:
removing the per-run cursor reset, re-injecting the deleted bypass, and dropping the
`sourceRunId` fallback each turn the corresponding test red.

**A3's safety is measured, not reasoned** — which is why the run-id decision was extracted
into `wsReplayState` at all. `resolveFrameRunId` has 6 direct unit tests, and reverting it
to the pre-ISS-082 behaviour turns exactly three red, including the two that pin what the
old code returned for a live and a REST-replayed agent frame (`undefined` in both cases).

One Playwright ID pair (`ts-l.token-usage` `:38` ↔ `:65`) swapped between full-suite runs.
Chased rather than waved away: run in isolation three times on the **reverted** tree and
three times on the changed tree, the file gives the identical result both ways
(`:65`+`:77` fail, `:38` passes). Full-suite parallelism noise, not this change.

## New findings — filed, not folded

- `clarifications` accumulates with no per-run reset outside `startPipeline`. Registered in
  the accumulator registry as `driver: "ui"`; it is grown by a direct UI call, so there is
  no frame identity for this mechanism to gate on.
- `validator_result` and `gate_passed` have **zero producers** in non-test backend code
  (`gate_blocked` has 3 real ones), so `validationIssues` may be dead on the wire. The
  accumulator is fixed anyway, for consistency. **The ISS-087 fixer needs this.**
- `hookRuns` has no per-run boundary in the reducer (`pipeline_start` spreads `...prev`).
  **Unobserved** — flagged, not claimed.
- **NEW, empirically verified here:** `hook_run`'s payload never reaches the reducer.
  `page.tsx` dispatches `{ type, ...msg.data }` while the `hook_run` case reads `msg.data`,
  so every entry collapses to its defaults — observed
  `{hook:"audit_logger", event:"", outcome:"continue", detail:{}}` for a
  `secret_scan`/`block` frame. `RunChatLane.deriveSecurityBullets` filters
  `outcome === "block"`, so the **only live consumer of `hookRuns` is structurally dead**.

## Disagreement with the investigation

It puts the user-visible blast radius of duplicated `hookRuns` at "a repeated 'Secret scan
blocked a write…' line". Measured, it is **zero**: that bullet can never render, for the
reason above. The duplication was real; that particular consequence was not.

## The rule, for the register

*A reducer field that accumulates is not done until a test has fed it the same input twice
and it did not change.*
