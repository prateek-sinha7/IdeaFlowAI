---
phase: quick-260707-1p8
status: passed
verified_by: orchestrator (independent gate re-run)
date: 2026-07-07
---

# Verification — quick-260707-1p8 (FIX-039: reset per-run agent accumulators on agent_start)

**Status: passed** — plan-checker PASSED pre-exec; all gates independently re-run.

## Root cause fixed
`useWorkflow.ts` `agent_start` set `status:"running"` but never reset the agent's run-scoped accumulators, and `agent_chunk` appends → a regenerate (2nd `agent_start`, new `event_id`) concatenated v2 onto v1, so `PrototypePipelineView.parseTasks` read the stale first `<tasks>` block → wrong count (showed 1 for a regenerated 9-task plan). Fix: reset the run-scoped `AgentRunState` fields (`output/thinking/thinkingText`→"", `toolCalls/validationIssues`→[], `error/validationPassed`→cleared) in `agent_start` before flipping to running — regenerate now REPLACES not appends. Identity fields (`id/name/role/icon/index`) + pipeline-level state untouched.

## Gates (independent re-run)
- `vitest run useWorkflow` → **12 passed / 3 files** (incl. new `useWorkflow.regenerateReset.test.ts`: replace-not-append, thinkingText reset, replay-safety, first-run no-op, cross-agent isolation). Executor confirmed TDD-RED first.
- `tsc -p tsconfig.json --noEmit` → **0 NEW errors** (baseline clean).
- Scope: `git show --stat 650b0064` = ONLY `useWorkflow.ts` (+31) + the new test (+173) + FIX-REGISTER (+1). No `PrototypePipelineView`, no backend. Trailer-free.

## Invariants
- **Replay-safe (verified):** `agent_start` carries `event_id` (stamped `engine.py:834`), deduped upstream by `shouldApplyEvent` (`page.tsx:272-278`) → a replayed `agent_start` is dropped, never re-fires the reset; a live output survives reconnect. Test 3 models this.
- **No band-aid:** `parseTasks` untouched (the "last `<tasks>` block" idea was rejected — it would mask the concatenation). Root-cause state reset only.
- FE-only, no INV-3 golden impact.

## Commit
`650b0064` (fix + FIX-039).

## Note (separate defects, NOT in this fix)
The reason a regenerate was needed at all — the spec-writer emitting a full HTML prototype → degenerate 1-task v1 — plus the `ibm` design-system overriding the template palette, and the content re-authored-from-spec (not reused from `example.html`), are distinct upstream defects tracked separately.
