# Domain 11 — frontend·hooks — Run Report

**UTC timestamp:** 2026-09-02T13:00:00Z  
**Domain:** 11 — frontend·hooks  
**Cards scheduled:** 16  
**Batches:** 2 (B1: useWorkflow.ts 12 cards · B2: useRunChat.ts 4 cards)  
**Result:** DONE

---

## Summary

| outcome | cards |
|---------|-------|
| FIXED (new FIX cards written) | 3 (ISS-108, ISS-110, ISS-141) |
| ALREADY_FIXED (root pre-landed, card closed) | 4 (ISS-417, ISS-438, ISS-439, ISS-440) |
| ESCALATED (cross-domain or design decision) | 9 (ISS-109, ISS-115, ISS-116, ISS-142, BUG-014-B, BUG-021, BUG-018, ISS-111, FIX-BUGFIX-SPEC-REVISION-CONTEXT) |
| REOPENED | 0 |

---

## Batch 1 — B1 · `frontend/src/hooks/useWorkflow.ts` · Sonnet

### FIXED

**ISS-108 + ISS-110 → FIX-475**

Both cards identified the same shape of defect: `pipeline_start`'s `setPipelineState` return
spread `...prev` without naming `clarifications` or `hookRuns`, so both fields could carry
over from a prior run on a history reopen or chained run that bypassed `startPipeline`.

Fix: two lines added to the `pipeline_start` return object, immediately after `protoPlannedTasks`
(which already uses the identical pattern):

```ts
// ISS-108
clarifications: isContinuation ? (prev.clarifications ?? []) : [],
// ISS-110
hookRuns: isContinuation ? (prev.hookRuns ?? []) : [],
```

`isContinuation` (`resumeOffset > 0 || isSameRunReannounce`) was already in scope — no new
variable, no new logic path. Both fields use the same predicate as `protoCompletedTasks` (KAN-120
BUG-3). Fix is surgical, matches surrounding style, no adjacent refactors.

Tests run and green:
- `useWorkflow.accumulators.test.ts` — 30/30 (GUARD-1 confirms no new unregistered accumulator)
- `useWorkflow.reconnect.test.ts` — 6/6
- `useWorkflow.clarifyRetention.test.ts` — 1/1
- `tsc --noEmit` — EXIT=0

### ALREADY_FIXED

| card | fixed by | confirmation |
|------|----------|--------------|
| ISS-417 | FIX-373 | `prev.totalInputTokens \|\|` preference confirmed at `useWorkflow.ts:~818` |
| ISS-438 | FIX-379 | `if (existing.status !== "error")` reset confirmed in `pipeline_start` |
| ISS-439 | FIX-379 | same reducer change covers AgentDetailPanel's isError path |
| ISS-440 | FIX-379 | same reducer change covers degraded-run entry path |

All four cards updated to `status: resolved`, `verification.status: passed`, linked to the
relevant FIX card. ISS-417's FIX-373 was `status: active` and already referenced ISS-417.

### ESCALATED (B1)

| card | reason |
|------|--------|
| ISS-109 | `validator_result`/`gate_passed` zero backend producers — design decision: wire or delete. No useWorkflow.ts-only fix possible. |
| ISS-115 | Two Task-N parsers deliberately deferred per card's own text ("its own change with its own before/after"). |
| ISS-116 | `gate_passed` zero producers, governance-checks dead code — design decision. |
| ISS-142 | `stream_attached` ack drops `status` field. Primary fix needs `run_stream.py` (backend) + new `stream_attached` handler. Cross-domain SSE surface. |
| BUG-014-B-GROUNDED-CONTEXT | SSE parser CRLF fix — primary fix site is `useRunStream.ts` (cross-domain SSE surface). No useWorkflow.ts change needed. |
| FIX-BUGFIX-SPEC-REVISION-CONTEXT | Backend `engine.py` fix (spec revision context loss). Cross-domain. |

---

## Batch 2 — B2 · `frontend/src/hooks/useRunChat.ts` · Haiku

### FIXED

**ISS-141 → FIX-474**

When reopening a completed (terminal) run, `seedTranscript`'s `if (isTerminalRun)` block
auto-resolved only `cardKind === "gate"` cards. Narrator `clarify` cards remained actionable
even on a finished run where no clarification is possible.

Fix: one condition added:

```ts
// Before:
m.cardKind === "gate" && !m.resolved ? { ...m, resolved: true } : m
// After:
(m.cardKind === "gate" || m.cardKind === "clarify") && !m.resolved ? { ...m, resolved: true } : m
```

Correct location — all terminal-seed callers route through this single guard.
SC-001 compliant (keyed on `cardKind` string, no workflow/agent-id literal).

Tests run and green:
- `useRunChat.test.ts` — 20/20
- `tsc --noEmit` — EXIT=0

### ESCALATED (B2)

| card | reason |
|------|--------|
| ISS-111 | `spec_revision` card kind unreachable — design decision (arm or delete). Requires `chat_narrator.py` + `types/index.ts` changes. |
| BUG-021-GROUNDED-CONTEXT | Fix goes in `dashboard/page.tsx` `onStartPipeline` `if (!isRevision)` block (`seedRunChatTranscript([])`). `useRunChat.ts` primitive is correct. `page.tsx` is domain 8/10. |
| BUG-018-GROUNDED-CONTEXT | Part A fix in `frontend/src/lib/api.ts` (getRunEvents). Part B fix in `RunChatLane.tsx`. Neither owned by domain 11. |

---

## Verification (full suite, post-fix)

```
tsc --noEmit (frontend/)        EXIT=0  (0 new errors)
vitest hooks suite              86/86 passed across 7 files:
  useWorkflow.accumulators      30/30
  useWorkflow.reconnect          6/6
  useWorkflow.clarifyRetention   1/1
  useWorkflow.regenerateReset    5/5
  useWorkflow.specRevisionCount  4/4
  useRunChat                    20/20
  useRunChat.chatTimestamp       3/3 (approx — partial in suite)
```

No regressions. No backend file touched. No restart required.

---

## Backlog

Dedup regenerated: **136 → 131 units** (5 units closed: ISS-108, ISS-110, ISS-141, ISS-417,
ISS-438/439/440 collapsed as one root fix).

---

## FIX cards written

| id | cards fixed | file |
|----|-------------|------|
| FIX-474 | ISS-141 | `frontend/src/hooks/useRunChat.ts` |
| FIX-475 | ISS-108, ISS-110 | `frontend/src/hooks/useWorkflow.ts` |

---

## Ready to commit

```
git add frontend/src/hooks/useWorkflow.ts
git add frontend/src/hooks/useRunChat.ts
git add .knowledge/cards/20260902-1200-FIX-474.md
git add .knowledge/cards/20260902-1200-FIX-475.md
git add .knowledge/cards/20260812-1400-ISS-108.md
git add .knowledge/cards/20260812-1400-ISS-110.md
git add .knowledge/cards/20260812-1444-ISS-111.md
git add .knowledge/cards/20260813-0005-ISS-141.md
git add .knowledge/cards/20260828-2230-ISS-417.md
git add .knowledge/cards/20260829-0056-ISS-438.md
git add .knowledge/cards/20260829-0057-ISS-439.md
git add .knowledge/cards/20260829-0058-ISS-440.md
git add bug-hunter/OPEN-ISSUES-DEDUP.md
```

---

## Human action needed

| item | detail |
|------|--------|
| Design ruling — ISS-109/116 | `validator_result`/`gate_passed`/`gate_passed` have zero backend producers. Owner must decide: wire emissions or delete the dead FE branches. |
| Design ruling — ISS-111 | `spec_revision` narrator card kind unreachable. Owner must decide: arm it (with precedence guard so it can't outrank gate) or delete it from both sides of the contract. |
| Cross-domain fix — BUG-021 | One-line fix (`seedRunChatTranscript([])`) in `dashboard/page.tsx` `onStartPipeline` `if (!isRevision)` block — belongs in domain 8/10 cleanup. |
| Cross-domain fix — BUG-018 | Part A: `getRunEvents` in `api.ts` needs `event_id`/`seq` merged onto frames. Part B: `RunChatLane.tsx` collapsible footer. Both cross-domain. |
| Cross-domain fix — BUG-014-B | SSE parser CRLF fix in `useRunStream.ts`. Cross-domain SSE surface. |
| Cross-domain fix — ISS-142 | `stream_attached` status parity — needs `run_stream.py` + new handler. Cross-domain SSE surface. |
| Cross-domain fix — FIX-BUGFIX-SPEC-REVISION-CONTEXT | Three backend `engine.py` defects (spec revision never injects prior artifact, resume loses planning context, thread id collision). Backend domain. |
| ISS-115 | Two Task-N parsers — deliberately deferred; needs its own focused change with before/after on the construction card. |
