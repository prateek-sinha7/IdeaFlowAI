# Phase 18 — Deferred / Out-of-Scope Items

Discovered during execution but NOT in scope for the introducing task. Logged
per the executor scope boundary (do not fix issues unrelated to the current
task's changes).

## Pre-existing FE test failures (out of scope — NOT introduced by 18-04)

Found during 18-04 Task 2 (the full-suite vitest gate after deleting
WorkflowComposer + CapabilityPalette). These 7 failures are present BOTH with
the deleted files restored and after deletion (identical failures), and the
failing test sources were last touched in old commits (4889e3a8, a219fade) —
never by phase 18. They are unrelated to the deletion and to the model-picker
relocation.

- `src/lib/workflowChaining.test.ts` — `availableChainTargets` (6 failing cases:
  removes current type; removes base form for a revision; removes completedTypes;
  collapses revision+base completions; empty list when every base done; works for
  a non-chainable type).
- `src/components/workflow/AgentProgressPanel.test.tsx` — "Suggested next steps >
  hides the chain panel when every base type is already complete".

Both clusters look like the same underlying `availableChainTargets` /
chain-exclusion logic drift (AgentProgressPanel renders the chain panel off the
same helper). Suggested owner: a dedicated FE-health / workflow-chaining fix in a
future plan or the post-phase UI pass. Not blocking 18-04 (the deletion is
import-clean: zero NEW failures, tsc green).
