# Phase 45: Resume Completeness Bug Fix [R0] - Context

**Gathered:** 2026-07-19
**Status:** Ready for planning
**Source:** POR Ingest Express Path (`.planning/RESUME-CAPABILITY-DESIGN-DRAFT.md` — the milestone v3.0 plan of record; all design decisions pre-LOCKED by the user, §8)

<domain>
## Phase Boundary

Fix ONE root-caused engine bug, standalone and first in milestone v3.0: `_first_incomplete_step` classifies a task-granular build step as "complete" as soon as its FIRST per-task artifact persists (`engine.py:6002` — `if agent_id in produced_agents or agent_id in completed_step_events: continue`), so a run that crashes mid-build (task N of M done, N < M) resumes by SKIPPING the build step entirely → silently truncated deliverable = real data loss on the live auto-resume path (`restore_non_terminal_runs` branch (b) → `resume_run`).

IN scope: the completeness classification only (strategy-conditional), plus the RED→GREEN restart-resume regression proving it. OUT of scope (later v3.0 phases — do NOT build here): per-task skip/cursor (Phase 46 owns `task_id`/`worker_index` on `subagent_runs`), durable→disk re-materialization (46), generic per-task capture (46), uploads durability (47), task identity/reconciliation (48), gate re-arm (49), user resume-from-failed (50). A correct-but-wasteful outcome is ACCEPTABLE here: after this fix a partial build RE-ENTERS the build step and may redo tasks from task 1 — Phase 46's cursor optimizes that; Phase 45's contract is only "never silently skip".

</domain>

<decisions>
## Implementation Decisions

### Fix site & shape (LOCKED — POR §5.4/§6 R0)
- The fix lives in the kernel resume tier's completeness classification (`_first_incomplete_step`, `engine.py:5909-6007`, the disjunct at `:6002`). Modify IN PLACE — no parallel resume path, no second dispatch loop (INV-12: the `for i, spec in enumerate(ordered_agents)` pin stays exactly 1).
- Completeness becomes STRATEGY-CONDITIONAL, keyed generically on the compiled plan (`step.strategy` / `task_source` from the compiled manifest) — NEVER a workflow-name/agent-id literal (INV-1/SC-001; the kernel banned-pattern gate must stay green).
- Task-granular steps (task_loop / wave_scheduler / fanout_batch — anything with per-task/per-worker production): a step counts as complete ONLY when its completion is actually terminal — per the POR criterion "every task in the current list has a completed artifact" (count/identity-based). The exact durable signal is Claude's discretion (below) but the acceptance bar is fixed: a partial build must classify INCOMPLETE; a genuinely completed build must still classify complete (no infinite re-run).
- `single_shot` steps keep the EXISTING produced-ref / `step_completed` semantics byte-unchanged.
- `step_reused` (input_hash reuse, `engine.py:5639-5733`) and `step_completed` event handling must not change behavior for completed steps.

### Guardrails (LOCKED — POR §7, register invariants)
- INV-3: the 5 characterization goldens stay byte/event-identical (`SNAPSHOT_UPDATE` unset; resume paths are dormant on scripted golden runs — prove it by running them, 10 passed expected). Any new event would need `_VOLATILE_STRIP_KEYS`/vocabulary treatment — prefer NO new events in this phase.
- INV-2: no per-run state on the engine singleton; anything transient lives on `ExecutionContext` or is derived from durable rows.
- Q3: NO migration in this phase (pure engine-logic fix; schema work is Phase 46).
- Do NOT touch the engine's terminal emission, `restore_non_terminal_runs` classification branches, `resume_run`'s dispatch re-entry, or `_hydrate_artifacts_from_store` beyond what the completeness fix strictly requires.
- `lint-imports` stays 4 kept / 0 broken; banned-pattern suite stays green.

### RED→GREEN proof (LOCKED — POR/ROADMAP SC4)
- A restart-resume regression that FAILS on current HEAD (partial build silently skipped → deliverable truncated / build step never re-entered) and PASSES after the fix. Extend the existing restart/resume test surface (`backend/tests/agents/test_restart_resume.py` idioms) rather than inventing a new harness.
- A companion no-regression case: a FULLY completed build step still classifies complete on resume (skipped, hydrated) — guards against over-correction/infinite re-run.
- The known pre-existing red `test_restart_resume::test_waiting_for_user_run_is_rearmed_not_driven` (the KAN-88/F4 gate limitation) is Phase 49's anchor — do NOT fix it, do NOT delete it, do NOT let it confuse the delta (verify-by-delta against pre-phase baseline).

### Execution constraints (LOCKED — session/project standing rules)
- Branch `feat/ui-2` ONLY (never main/dev/staging). NO commit trailers (no Co-Authored-By / Claude-Session). NEVER push.
- python3.11, no venv. The FULL backend pytest suite hangs offline (Chromium/Bedrock/Postgres-gated) — verify with TARGETED suites only (the restart/resume tests + the 5 `test_characterization_*.py` + any suite touching edited files) + `/opt/homebrew/bin/lint-imports`.
- Do NOT run live Bedrock in executors — the orchestrator owns live proofs (defer-live-verification convention; the milestone-end live pass covers the ladder).
- Worktrees OFF → sequential execution.
- Register-first: consult `.planning/IMPLEMENTATION-REGISTER.md` (Phase 12 section + the Phase 43/44 reconciliation entries) before contradicting any locked decision.

### Claude's Discretion
- The exact durable completeness signal for task-granular steps, chosen after research verifies what is reliably durable TODAY (Phase 45 predates the Phase-46 schema): e.g. requiring the step's own terminal signal (`step_completed` durable event) for task-granular steps, or counting per-task `artifact_refs` rows (`task_id`-tagged `html_file` rows from `persist_task_html`) against the task total parsed from the plan/task_list artifact. Pick the simplest mechanism that meets the locked acceptance bar and is provably INV-3-dormant; document why in the plan.
- Test-construction details (fixtures, scripted-model driving, how the partial state is synthesized) — follow the existing `test_restart_resume.py` / characterization harness idioms.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Plan of record + tracking
- `.planning/RESUME-CAPABILITY-DESIGN-DRAFT.md` — the v3.0 POR: §2 (durable substrate, resume tier anchors), §4 Gap B, §5.4 (the strategy-conditional completeness fix), §6 (R0 scope), §7 (guardrails), §9 (verified anchor index). READ FULLY.
- `.planning/ROADMAP.md` — "### Phase 45: Resume Completeness Bug Fix [R0]" (goal + 4 success criteria).
- `.planning/REQUIREMENTS.md` — RESUME-05 (the single REQ this phase must satisfy).
- `.planning/IMPLEMENTATION-REGISTER.md` — Phase 12 section (resume tier: D-06..D-12 locked decisions, CR-03 whole-wave rationale, the "no new step-status table" lock) + Phase 43/44 entries (current transport reality: SSE-only, `run_engine.py` bridge).

### Code under change / at risk
- `backend/agents/execution_engine/engine.py` — `_first_incomplete_step` (`:5909-6007`, bug at `:6002`), `resume_run` (`:6031-6237`), `_hydrate_artifacts_from_store` (`:5865-5907`), `restore_non_terminal_runs` (`:4815-4998`), input_hash reuse (`:5639-5733`). (Line numbers verified 2026-07-18 — re-verify, they drift.)
- `backend/agents/capabilities/strategies/task_loop.py` — `:233` (task loop start, no offset), `:290-296`/`:358-366` (per-task persist call sites).
- `backend/agents/execution_engine/kernel_services.py` — `persist_task_html` (`:1313-1339`; single-declared-file, `kind="html_file"` hardcoded).
- `backend/tests/agents/test_restart_resume.py` — the restart/resume test surface (incl. the pre-existing red to leave alone).
- `backend/tests/agents/test_characterization_*.py` (5 files) — the INV-3 gate (10 passed, no SNAPSHOT_UPDATE).

</canonical_refs>

<specifics>
## Specific Ideas

- The bug's exact mechanics (verified this session): `persist_task_html` dual-writes an `html_file` ref with `producer_agent=<build agent>` after EVERY task, so `produced_agents` contains the build agent from task 1 onward — the membership test can't distinguish partial from complete.
- Wave context for the discretion call: `wave_runs` rows carry `step`, `wave_index`, `task_ids` (JSON), `status` — a wave step's terminality is derivable from wave rows; `subagent_runs` has NO task identity until Phase 46.
- The fix must also hold for the `resume_run` → `_execute_impl` skip path (`if i < _resume_from: continue`) — the returned first-incomplete index is the single consumer of this classification.

</specifics>

<deferred>
## Deferred Ideas

- Per-task cursor / skip-completed-tasks inside the re-entered step → Phase 46 (RESUME-09).
- Durable→disk re-materialization + merge re-entry → Phase 46 (RESUME-08).
- Generic per-task capture (multi-file) → Phase 46 (RESUME-07).
- Task identity / user-edited task lists → Phase 48.
- Gate re-arm (the `waiting_for_user` red test) → Phase 49.
- User resume-from-failed endpoint → Phase 50.

</deferred>

---

*Phase: 45-resume-completeness-bug-fix-r0*
*Context gathered: 2026-07-19 via POR Ingest Express Path (decisions pre-locked by the user in the POR §8; no interactive discuss round needed)*
