# Spec Index

Ordered by spec id. **Status audited 2026-08-10** against the code, not against checkboxes —
several specs built packages that were later deleted, and their task lists still read "done"
for code that no longer exists. Those are marked OBSOLETE, with the spec that replaced them.

> **Numbering note.** Two specs share the id `007` (`007-minimal-eval`, `007-prompt-versioning`)
> — they were authored in parallel sessions on 2026-07-30. `010-minimal-eval` is an earlier
> draft of `007-minimal-eval` and was never executed under its own number. Both collisions are
> historical; ids are not renumbered because commit messages and cross-links reference them.

| Spec | Title | Status |
|------|-------|--------|
| [001-ai-workflow-os](001-ai-workflow-os/spec.md) | Universal Workflow Orchestration Engine | **Done** — 91/91 tasks |
| [002-deepagents-migration](002-deepagents-migration/plan.md) | Deepagents runtime migration | **Done, pending live verification** — Phase 8 harness present and green offline; the live Bedrock run ([`PHASE8_VERIFY.md`](002-deepagents-migration/PHASE8_VERIFY.md), `RUN_LIVE_BEDROCK=1`) has never been executed. Operator task — costs money |
| [003-workflow-engine-decoupling](003-workflow-engine-decoupling/plan.md) | Workflow engine decoupling | **Done** — 37/39 ledger rows ☑; the 2 remaining ☐ are deliberate: `D1` is live code retained on purpose, `AUDIT` is a CHECK row already covered by `tests/agents/test_exec_runs.py::test_0018_reversible_offline` |
| [004-mistral-eval-provider](004-mistral-eval-provider/spec.md) | Mistral as the free-tier eval provider | **Done** — implemented and in production use |
| [005-prompt-eval-scoring](005-prompt-eval-scoring/spec.md) | Agent-Output Grading (`evals/grading/`) | **OBSOLETE.** Built but uncalibrated; `evals/grading/` deleted by [007-minimal-eval](007-minimal-eval/spec.md). The 7 open decisions in [`outstanding.md`](005-prompt-eval-scoring/outstanding.md) are moot — the package is gone |
| [006-hybrid-eval-suite](006-hybrid-eval-suite/spec.md) | Revision Fulfilment & the Hybrid Eval Suite (`evals/hybrid/`) | **OBSOLETE.** Phases 0–2 built; Phase 3 (the fix) was halted by instruction on 2026-07-22 and never resumed. `evals/hybrid/` deleted by [007-minimal-eval](007-minimal-eval/spec.md), so the suite that reproduced the defect no longer exists. Any revival needs re-scoping against current code |
| [007-minimal-eval](007-minimal-eval/spec.md) | The Minimal Eval System — 7 files · 1,500 LOC · 5 commands | **Done** — shipped at `backend/evals/minimal/`; all 7 modules present, `_source/` scaffolding removed, budget test in place. Replaced `evals/grading` + `evals/hybrid` + `evals/model_graded` (~18k LOC) |
| [007-prompt-versioning](007-prompt-versioning/spec.md) | Applying Advisor Prompt Edits | **OBSOLETE.** All 68 tasks completed against `evals/grading/`, which was then deleted by [007-minimal-eval](007-minimal-eval/spec.md). No live code remains |
| [008-grading-calibration](008-grading-calibration/spec.md) | Grading Calibration — severity-priced judge findings | **OBSOLETE.** All 127 tasks done and calibrated live 2026-07-30; `evals/grading/` subsequently deleted by [007-minimal-eval](007-minimal-eval/spec.md) |
| [009-grading-dashboard](009-grading-dashboard/spec.md) | The Grading Dashboard — a static site over all runs | **OBSOLETE.** 184/185 tasks; the one open item (`site/` coverage > 80%) is moot because `evals/grading/site/` no longer exists |
| [010-minimal-eval](010-minimal-eval/plan.md) | The Minimal Eval System (earlier draft) | **OBSOLETE.** Never executed under this number; shipped as [007-minimal-eval](007-minimal-eval/spec.md). Retained for the reasoning in §1 |
| [011-native-deepagents-skills](011-native-deepagents-skills/spec.md) | Native `deepagents` Skills — progressive disclosure, run-level attach, staged into the sandbox | **Done** — 22/23 tasks. T21 (live activation measurement, frontier + `qwen3.5:4b`) is the user's live run and remains unrun. D-02 closed as superseded by [012](012-per-agent-skills-custom-agents/spec.md) R-22 |
| [012-per-agent-skills-custom-agents](012-per-agent-skills-custom-agents/spec.md) | Per-Agent Skills & Composable Custom Agents — skills per step, a reusable blank custom agent, engine-scheduled sub-agent trees | **Specified** — Q1–Q17 resolved ([clarifications.md](012-per-agent-skills-custom-agents/clarifications.md)); plan not yet written |
| [013-reusable-custom-agents](013-reusable-custom-agents/spec.md) | Reusable Custom Agents — save a composed agent to a personal library, version it, reuse it across workflows | **Draft** — specified 2026-08-13, ready for `/clarify`. Backend (`user_agents`, `0032`, `/api/user-agents`, the `/api/agents/library` merge) is already built and unreachable from the UI; GAP-01 is why. RISK-02 is an open product decision |
