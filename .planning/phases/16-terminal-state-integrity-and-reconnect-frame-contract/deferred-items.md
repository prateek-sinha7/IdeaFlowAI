# Phase 16 — Deferred Items (out-of-scope discoveries)

## 16-04 (ISS-017)

- **Pre-existing failing test (NOT introduced by 16-04):**
  `frontend/src/components/workflow/AgentProgressPanel.test.tsx:176`
  > `AgentProgressPanel — Suggested next steps > hides the chain panel when every base type is already complete`
  - **Scope:** Out of scope for 16-04. The file `AgentProgressPanel.tsx`/`.test.tsx` was
    NOT touched by this plan (verified `git diff e6530025 HEAD`); it only imports an
    additive-optional `type` from `@/types/index`, which cannot be affected by the
    additive `failed?`/`failedAgents?` fields added here.
  - **History:** The test text is unchanged since base commit `a219fade` (and the
    plan's pre-work tip `e6530025`), so it predates 16-04.
  - **Action:** Logged, not fixed (execute-plan.md scope boundary — do not auto-fix
    pre-existing failures in unrelated files). Hand to the phase verifier / a separate
    fix task.
