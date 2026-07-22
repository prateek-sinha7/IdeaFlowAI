# Deferred Items — quick-260703-byv

Out-of-scope discoveries logged during execution. NOT fixed (scope fence: prototype Thinking-view FE only).

## Pre-existing baseline red (unrelated to this change)

- **Suite:** `frontend/src/components/workflow/AgentProgressPanel.test.tsx`
- **Failing case:** `:133` — `expect(screen.queryByText("Presentation")).not.toBeInTheDocument()` (the suggested-next-steps / workflow-catalog panel still renders "Presentation").
- **Status:** PRE-EXISTING at base HEAD `03e5e0ae`. Reproduced by reverting both changed source files to base and re-running the suite → identical `1 failed | 6 passed`. Zero import linkage to `AgentThinkingTab.tsx` / `PrototypePipelineView.tsx`.
- **Family:** same workflow-catalog "Presentation" filtering baseline as the known-red WorkflowCatalog×5 exclusion — do NOT chase here.
- **Disposition:** deferred (not a regression introduced by byv).
