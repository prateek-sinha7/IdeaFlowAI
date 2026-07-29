# Spec Index

| Spec | Title | Status |
|------|-------|--------|
| [001-ai-workflow-os](001-ai-workflow-os/spec.md) | Universal Workflow Orchestration Engine | In Progress |
| [002-deepagents-migration](002-deepagents-migration/plan.md) | Deepagents runtime migration | In Progress |
| [003-workflow-engine-decoupling](003-workflow-engine-decoupling/plan.md) | Workflow engine decoupling | In Progress |
| [004-mistral-eval-provider](004-mistral-eval-provider/spec.md) | Mistral as the free-tier eval provider — `build_model(provider="mistral")`, tier ordering, no silent fallback | **Implemented** — in production use by both eval packages |
| [005-prompt-eval-scoring](005-prompt-eval-scoring/spec.md) | Agent-Output Grading (`evals/grading/`) — two tracks, per-dimension sub-scores, run configs, noise-guarded comparison | **Built, uncalibrated** — 253 offline tests, no live run; 7 open decisions |
| [006-hybrid-eval-suite](006-hybrid-eval-suite/spec.md) | Revision Fulfilment & the Hybrid Eval Suite (`evals/hybrid/`) — a revision can report "done" without fixing what you asked | **Suite built (Phases 0–2), fix not started** — Phase 3 paused by instruction |
