# Implementation Plan: AI Workflow Builder

## Overview

This plan implements `design.md` in Python for the backend (FastAPI, SQLAlchemy, Alembic, `deepagents==0.6.7`, hypothesis) and TypeScript for the frontend (React 19, Next.js 16, Vitest, React Testing Library, fast-check, Playwright). The skill folder comes first because every later layer reads it. Then come the settings and catalog flags, the additive `DeepAgentRunner` change, persistence, the pure agent-layer modules, the agent tools and the Server_Gate, the turn runner and the API, the frontend, and the cross-cutting test suites. Each task ends wired into code that an earlier task built or that a later task names.

Conventions used in the tasks:


- `[pending G-NN]` or `[pending Q-NN]` marks code that implements a design proposal that is not yet confirmed. Revisit that task if the answer changes.
- Backend commands run from `backend/` with `uv run`, frontend commands from `frontend/` with `npm`, in PowerShell, single pass, with no watch mode and no dev server.
- Backend unit tests mirror the module path under `tests/unit/`. Integration tests go under `tests/integration/{db,repositories,api,ai,external}` with the `_db`, `_api` or `_external` suffix, on testcontainers PostgreSQL with the LLM faked, never SQLite. Test names follow `test_<function>_<outcome>_when_<condition>`. Every test sub-task creates any missing `__init__.py` on its path. The folder hook in `tests/conftest.py` applies the suite marker.
- Property tests carry the comment `# Feature: ai-workflow-builder, Property N: <title>` and run at least 100 examples (`@settings(max_examples=100)` for hypothesis, `numRuns: 100` for fast-check).
- Frontend tests are colocated under `frontend/src/**` as `.test.ts(x)`, `.property.test.ts(x)` or `.integration.test.tsx`. Playwright specs go under `frontend/e2e/tests/` and run in the `mocked` project.
- Integration tests need Docker for testcontainers. Docker is not installed locally, so they run on the Docker-capable CI runner. Locally, checkpoints only confirm that they collect.
- Do not ask questions. If the spec leaves a point open, pick the simplest option, add an entry to `open-decisions.md` in this spec folder (task id, choice made, who must confirm it), and finish the task. Do not end with a list of pending questions.

## Tasks

- [x] 1. Ship the skill with the backend
  - Revised 2026-11-10: the skill lives in `app/agents/workflow_builder/skills/` and has no copy, lock file or settings. Task titles 1.2 to 1.9 were renamed to match, and their run history in `tasks.meta.json` was moved to the new titles.
  - [x] 1.1 Create the skill package module
    - Create `backend/app/agents/workflow_builder/__init__.py` with no imports, so the package stays light.
    - Create `backend/app/agents/workflow_builder/skill_package.py` (standard library only) with `SKILLS_ROOT` and `SKILL_DIR`, fixed in code from the module's location, and `read_skill_facts()`, which returns the skill hash and each file's line count from disk [pending G-20]. `missing_files()` and `required_files()` support the startup check [pending G-21].
    - Removed 2026-11-10: `read_lock`, `write_lock`, `verify`, the `verify` command line and the `SKILLS.lock.json` file.
    - _Requirements: 20.9, 32.6, 32.8, 32.9_

  - [x] 1.2 Fix the skill path (replaces the skill-root settings)
    - Removed 2026-11-10: `BUILDER_SKILLS_ROOT` and `BUILDER_SKILL_IDS` from `backend/app/core/config.py`, the Dockerfile `ENV` line and `app.env.example`. The skill id is `BUILDER_SKILL_ID` in `script_policy.py`.
    - _Requirements: 18.4, 32.8_

  - [x] 1.3 Remove the sync and copy-check tool
    - Removed 2026-11-10: `backend/tools/ci/builder_skill_copy.py` with its `--sync`, `--check`, `--drift` and `--deps` modes. There is one copy, so nothing syncs.
    - _Requirements: 32.3, 32.4, 32.12_

  - [x] 1.4 Keep one copy of the skill
    - The skill is `backend/app/agents/workflow_builder/skills/velocity-workflow-creator/`, edited in place and committed there.
    - The folder sits outside the global skills root, so the Skills library does not list it.
    - _Requirements: 18.3, 32.2, 32.10_

  - [x] 1.5 Ship the skill in the image and keep it out of analysis tools
    - `backend/Dockerfile`: the skill arrives with `COPY app/`. The build checks the key files exist. Task 13.9 adds the prompt-file check.
    - `backend/.dockerignore`: `!app/agents/workflow_builder/skills/**` below the `*.md` line and above the final secrets block.
    - Exclude the folder from ruff, pyright, vulture, bandit, compileall and coverage (`backend/pyproject.toml`, `backend/pyrightconfig.json`, `ci/backend-static-checks.json`).
    - _Requirements: 32.5, 32.6, 32.7_

  - [x] 1.6 Add the selftest and step-model checks and wire them into CI
    - `backend/tools/ci/builder_skill_checks.py` with `--selftest`: `selftest.py` in the Skill_Folder, plain and with `--compiler .`, under `PYTHONDONTWRITEBYTECODE=1`, then `git status --porcelain` of the Skill_Folder must show no new file.
    - `--step-models`: every `builder_step=True` model is in the skill's `references/catalog.json`.
    - `.github/workflows/ci.yml`: a step in the backend static-checks job runs `--selftest`, `--step-models` and `builder_pattern_fixtures --check`, following the job's existing evaluator and finalizer split.
    - Removed 2026-11-10: `--check`, `--drift` and `--deps`, with their Req 32.12 and 33.2 to 33.7 checks.
    - _Requirements: 33.1, 33.4, 33.8, 49.8, 49.10_

  - [x] 1.7 Write unit tests for the skill package and the CI checks
    - `tests/unit/app/agents/workflow_builder/test_skill_package.py`: the fixed path, hashing, file listing, facts read from disk and the required-file check, on trees under `tmp_path`.
    - `tests/unit/tools/ci/test_builder_skill_checks.py`: the `--step-models` cases and the mode registry.
    - The sync, deps and drift unit tests were deleted on 2026-11-10 with the modes they covered.
    - _Requirements: 20.1, 32.9, 33.8_

  - [x] 1.8 Write property test for skill integrity
    - **Property 6: Skill integrity**
    - **Validates: Requirements 32.6, 32.9**
    - `tests/property/app/agents/workflow_builder/test_skill_package_properties.py`: the hash ignores line endings and file order and changes when a file's content changes or a file is added, removed or renamed; `missing_files` names exactly the absent required files.
    - Build file trees with `tempfile.TemporaryDirectory` inside each example, because hypothesis does not reset the function-scoped `tmp_path` between examples.
    - The copy-tree property tests were deleted on 2026-11-10.

  - [x] 1.9 Catalog drift comparison property (withdrawn)
    - Removed 2026-11-10 with the `--drift` check. Property 7 (Req 33.2, 33.6) no longer applies, and `tests/property/tools/ci/test_builder_skill_copy_drift_properties.py` was deleted.

- [x] 2. Checkpoint: skill packaging
  - From `backend/`: `uv run python -m tools.ci.builder_skill_checks --selftest`, `uv run python -m tools.ci.builder_skill_checks --step-models`, `uv run pytest tests/unit/app/agents/workflow_builder tests/unit/tools/ci tests/property/app/agents/workflow_builder`, `uv run pytest --collect-only -q`, `uv run ruff check`, `uv run pyright`, `uv run lint-imports`.
  - From the repository root: `git status --porcelain --ignored -- backend/app/agents/workflow_builder/skills` shows no new file after the selftest.
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. Add the builder settings and model catalog flags
  - [x] 3.1 Add the remaining builder settings
    - `backend/app/core/config.py`: add every other setting in design §4.8 with its default, including the three token budgets as `None` (unenforced until the Spike).
    - Comment on `BUILDER_SANDBOX_ROOT`: `""` resolves to `<RUNS_ROOT>/_builder`, and any future sweep of `RUNS_ROOT` must skip `_builder/` (Q-41).
    - _Requirements: 2.1, 2.2, 28.5, 28.11, 36.5, 36.6, 45.4, 47.1, 47.2, 47.3, 47.6, 47.7, 47.8, 47.9, 47.10, 47.11, 47.12, 47.13, 47.14, 47.15_

  - [x] 3.2 Add the builder flags to `ModelEntry`
    - `backend/agents/capabilities/model_catalog.py`: append `builder_chat`, `builder_step` and `builder_default_chat`, all defaulting to `False`, after `reasoning`.
    - Set Sonnet 5.5 to all three; Opus 4.6 to `builder_chat` [pending Q-59] and `builder_step`; Haiku 5.5 to `builder_step` only until the Spike (Q-56, Q-60). No GPT entry gets a flag.
    - _Requirements: 41.1, 41.2, 41.3, 41.4, 41.5, 41.9, 45.1_

  - [x] 3.3 Extract the shared capability projection
    - `backend/app/api/capabilities.py`: extract `project_model_entry(m) -> ModelCatalogEntry` and use it at the existing call site. The `/api/capabilities` response stays identical and `ModelCatalogEntry` gains no field.
    - _Requirements: 41.7, 41.14_

  - [x] 3.4 Build the builder model view
    - Create `backend/app/agents/workflow_builder/model_catalog_view.py` with `BuilderModelView`, `builder_models(tier)` filtered by `TIER_MODEL_COST_CLASSES`, the default-model choice (the Settings preference when offered, else Sonnet 5.5, else the first offered entry) and `assert_builder_catalog_valid(entries)`.
    - Add `check_chat_choice(entries, view, model_id, effort)`, the pure helper behind admission checks 9 and 10: an unknown or GPT model gives `model_not_allowed` (422), an unentitled one `model_not_entitled` (403) [pending G-06], and an effort outside the model's levels, or a non-null effort for a model with none, gives `effort_not_allowed` (422).
    - _Requirements: 6.2, 6.8, 26.1, 26.3, 41.6, 41.8, 41.10, 41.13, 45.1, 48.4_

  - [x] 3.5 Add the step-model CI check
    - `backend/tools/ci/builder_skill_checks.py`: add `--step-models`, which fails when an entry with `builder_step=True` is missing from the skill's catalog snapshot's model ids. Add it to the CI step in `.github/workflows/ci.yml`.
    - _Requirements: 33.8, 41.4, 49.10_

  - [x] 3.6 Write unit tests for the catalog flags and the model view
    - `tests/unit/agents/capabilities/test_model_catalog.py`: pinned flags per 41.2 to 41.5, and no GPT entry carries a builder flag.
    - `tests/unit/app/api/test_capabilities.py`: `ModelCatalogEntry.model_fields` has no `builder_` key and the projection output is unchanged.
    - `tests/unit/app/agents/workflow_builder/test_model_catalog_view.py`: tier filtering, the default fallback when the tier lacks `standard`, and `assert_builder_catalog_valid` passing on the real catalog.
    - _Requirements: 41.2, 41.3, 41.4, 41.5, 41.7, 41.8, 49.2_

  - [x] 3.7 Write property test for model and effort checks
    - **Property 19: Model and effort checks follow the filtered catalog**
    - **Validates: Requirements 26.1, 26.3, 41.13, 45.1**
    - `tests/property/app/agents/workflow_builder/test_model_catalog_view_choice_properties.py`.

  - [x] 3.8 Write property test for catalog flag validity
    - **Property 20: Catalog flags are valid or startup fails**
    - **Validates: Requirements 41.8, 41.9**
    - `tests/property/app/agents/workflow_builder/test_model_catalog_view_flags_properties.py`.

- [x] 4. Extend `DeepAgentRunner` additively
  - [x] 4.1 Add the optional `backend`, `extra_middleware` and `history` parameters
    - `backend/app/agents/deep_agent_runner.py`, per design §2.4: passing both `backend` and `run_sandbox` raises `ValueError`; `extra_middleware` is appended after the reserved-path guard; `history` messages go before the single `HumanMessage` in `astream_events` and `_astream_events_once`.
    - With none of the new arguments, the graph, the middleware list and the input messages are the same as today.
    - _Requirements: 18.1, 20.2, 25.1, 28.1, 48.2, 48.8_

  - [x] 4.2 Write unit tests for the additive change
    - Add the cases to the existing `tests/unit/app/agents/test_deep_agent_runner.py`. This is the mirrored path; the design's `test_deep_agent_runner_additive.py` would split one module's tests across two files.
    - Cases: without the new arguments the middleware class list and the first-call messages match today's; `backend` plus `run_sandbox` raises; `history` order is preserved.
    - _Requirements: 48.8_

- [ ] 5. Checkpoint: settings, catalog and runner, with the INV-3 golden check
  - From `backend/`: `uv run pytest tests/unit/agents/capabilities tests/unit/app/agents tests/unit/app/api tests/property/app/agents/workflow_builder` and `uv run python -m tools.ci.builder_skill_checks --step-models`.
  - INV-3: run `Remove-Item Env:SNAPSHOT_UPDATE -ErrorAction SilentlyContinue`, then `uv run pytest tests/agents/test_characterization_*.py` together with `tests/contract/agents/test_characterization_*.py`. PowerShell does not expand wildcards for native commands, so pass the files as `uv run pytest (Get-ChildItem tests/agents/test_characterization_*.py, tests/contract/agents/test_characterization_*.py).FullName`. Then `git status --porcelain tests/agents/characterization/golden/` must print nothing.
  - `uv run pytest --collect-only -q`, `uv run ruff check`, `uv run pyright`, `uv run lint-imports`.
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Add persistence
  - [x] 6.1 Create the ORM models
    - Create `backend/app/models/workflow_builder.py` with `WorkflowBuilderSession`, `WorkflowBuilderMessage` (user, assistant and tool rows) and `WorkflowBuilderDraft`, columns per design §4.2 to §4.4. `workflow_id` is a foreign key with `ON DELETE SET NULL`. `owner_id` and `workspace_id` are not null and are stamped with the user id; user messages use status `accepted` [pending G-37].
    - Register the models in `backend/app/models/__init__.py`.
    - _Requirements: 20.1, 20.16, 24.1, 24.2, 24.3, 24.6, 24.7_

  - [x] 6.2 Write migration `0051`
    - Create `backend/alembic/versions/0051_workflow_builder.py` with `revision = "0051"` and `down_revision = "0050"`: the three tables, `uq_wb_messages_session_seq`, the partial unique `uq_wb_messages_client_id`, the partial unique `uq_wb_messages_one_running` (`role = 'assistant' AND status = 'running'`), `ix_wb_messages_user_role_created`, `ix_wb_messages_turn`, `uq_wb_drafts_session_revision` and `ix_wb_sessions_user_updated`.
    - Additive only. `downgrade()` drops the three tables in reverse order.
    - _Requirements: 21.8, 21.10, 24.6, 24.8, 48.7_

  - [x] 6.3 Implement the session sandbox
    - Create `backend/app/agents/workflow_builder/sandbox.py` with `BuilderSandbox`: root under `BUILDER_SANDBOX_ROOT` (default `<RUNS_ROOT>/_builder`), user segment through `app.agents.sandbox._safe_segment`, `is_relative_to` containment, the folder layout in design §4.5, `call_temp_dir(call_id)`, `rebuild(latest_draft, latest_unproposed)`, `delete_session()` and `delete_user()`.
    - No git repository is created, and nothing in the module deletes files on a timer.
    - _Requirements: 20.4, 20.5, 20.11, 20.12, 31.2, 31.5_

  - [x] 6.4 Implement the session store
    - Create `backend/app/api/workflow_builder/__init__.py` (no router export yet) and `backend/app/api/workflow_builder/store.py`. Every query filters on `user_id`.
    - Operations: create, get, keyset list on `(updated_at, id)` with a default page of 20 and a maximum of 50 [pending G-24], delete; insert the user message and the running assistant message in one transaction using `next_seq`; insert tool rows; finalize the assistant row; insert revisions numbered `max + 1` inside the inserting transaction; read and write the summary and clarify-count fields; read the latest seed, accepted, undo and unproposed revisions; count a user's messages in the rolling 60 s window and their running turns; list and mark running assistant rows for the startup sweep.
    - Provide the store through a `get_builder_store` dependency, so tests can substitute `InMemoryBuilderStore`.
    - _Requirements: 2.6, 2.8, 12.1, 21.3, 21.8, 21.10, 24.1, 24.2, 24.3, 24.4, 24.5, 24.7, 24.9, 31.1, 31.2_

  - [x] 6.5 Remove builder data on account deletion
    - `backend/app/core/user_deletion.py`: in `delete_user_dependents`, delete `workflow_builder_messages`, then `workflow_builder_drafts`, then `workflow_builder_sessions` by `user_id` before the `workflows` delete, each counted in the audit dictionary.
    - `backend/app/api/admin.py`: after the caller's commit in `delete_user`, remove the user's sandbox folder through `BuilderSandbox.delete_user`. Task 16.10 adds stopping the user's running turns first.
    - _Requirements: 31.7_

  - [x] 6.6 Write the in-memory store fake and the session factory
    - `tests/fakes/builder_store.py`: `InMemoryBuilderStore` with the same interface as `store.py`, reusing its cursor helpers.
    - `tests/factories/builder_session_factory.py`: `BuilderSessionFactory` plus builders for messages, tool rows and revisions.
    - _Requirements: 49.1_

  - [x] 6.7 Write the migration integration test
    - `tests/integration/db/test_migration_0051_db.py`: upgrade a testcontainers PostgreSQL from `0050`, then assert the tables, columns, the partial unique index and a single head.
    - _Requirements: 24.6, 24.8, 48.7_

  - [x] 6.8 Write the store integration test
    - `tests/integration/repositories/test_workflow_builder_store_db.py`: owner filters, `client_message_id` uniqueness, the running-turn index under concurrent inserts, revision numbering, `ON DELETE SET NULL` on the link, a pagination walk with fixed examples, and account deletion through `delete_user_dependents`.
    - _Requirements: 2.6, 2.8, 20.16, 21.8, 21.10, 24.8, 31.7_

  - [x] 6.9 Write unit tests for the sandbox
    - `tests/unit/app/agents/workflow_builder/test_sandbox.py` with `tmp_path`: the folder layout, the containment refusal, rebuild contents, the temp folder path and deletion.
    - _Requirements: 20.4, 20.5, 20.12_

  - [x] 6.10 Write property test for session pagination
    - **Property 27: Pagination is complete and ordered**
    - **Validates: Requirements 2.8, 12.1, 31.1**
    - `tests/property/app/api/workflow_builder/test_store_pagination_properties.py` against `InMemoryBuilderStore`. Create `tests/property/app/api/__init__.py` and `tests/property/app/api/workflow_builder/__init__.py`.

- [ ] 7. Checkpoint: persistence
  - From `backend/`: `uv run alembic heads` prints exactly `0051 (head)`; `uv run alembic upgrade head` succeeds against the local PostgreSQL in `backend/.env`.
  - `uv run pytest tests/unit/app/agents/workflow_builder tests/property/app/api/workflow_builder`.
  - `uv run pytest tests/integration/db/test_migration_0051_db.py tests/integration/repositories/test_workflow_builder_store_db.py --collect-only -q`. These tests run on the Docker-capable CI runner.
  - `uv run pytest --collect-only -q`, `uv run ruff check`, `uv run pyright`, `uv run lint-imports`.
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. Implement stages, event models and the canonical form
  - [x] 8.1 Implement stage derivation
    - Create `backend/app/agents/workflow_builder/stages.py` with the `Stage` enum, the label table and `derive_stage(signal, current) -> Stage | None` per design §3.3.3. Signals: turn accepted, thinking or text while no tool call runs, tool start (by tool name, path, script and subcommand), dry-run start and gate acceptance.
    - _Requirements: 39.1, 39.2, 39.3, 39.4, 39.5, 39.6, 39.7, 39.8, 39.9, 39.10_

  - [x] 8.2 Write property test for stage derivation
    - **Property 13: Stage derivation follows the table**
    - **Validates: Requirements 39.2, 39.3, 39.4, 39.5, 39.6, 39.7, 39.8, 39.9, 39.10**
    - `tests/property/app/agents/workflow_builder/test_stages_properties.py`.

  - [x] 8.3 Define the event and shared value models
    - Create `backend/app/agents/workflow_builder/events.py` with `TurnStatus`, `StopReason`, `Outcome`, `RevisionKind` and `TargetTrust`, plus the value models shared by events and API schemas (`ToolActivity`, `CheckResult`, `ChangeSummary`, `LaunchNeed`, `RunningTurnSnapshot`, `TokenUsage`). Keeping them here means the agent layer never imports `app.api`.
    - Add every event model in design §3.3.2, including `Snapshot` with `through_seq` [pending G-14] and `DraftRestored` [pending G-16], the `BuilderEvent` discriminated union, and `to_wire(event) -> (type, data)` and `from_wire(type, data)` for the existing `{"type", "data"}` envelope.
    - Event type names avoid the five retired WebSocket tokens checked by `tests/unit/agents/test_sse_cutover_banned_patterns.py`.
    - _Requirements: 38.2, 38.3, 38.4, 38.5, 38.6, 38.7, 38.8, 38.11, 38.12, 38.13, 38.14, 38.15, 38.16, 38.17, 48.3_

  - [x] 8.4 Write property test for event round trips
    - **Property 22: Events round-trip through JSON**
    - **Validates: Requirements 38.3, 38.4, 38.5, 38.6, 38.7, 38.8, 38.11, 38.12, 38.13, 38.14**
    - `tests/property/app/agents/workflow_builder/test_events_properties.py`.

  - [x] 8.5 Implement the canonical manifest form
    - Create `backend/app/agents/workflow_builder/canonical.py`: remove the documented composer defaults (`tools.exec: false`, `tools.read_files: true`, `tools.write_files: true`, `gates: []`, and `depends_on` when it equals the sequential order), drop `null` values, serialise with sorted keys, compact separators and UTF-8 without ASCII escaping, and provide `canonical_hash(manifest)` [pending G-34].
    - _Requirements: 10.9, 37.2_

  - [x] 8.6 Write property test for the canonical form
    - **Property 30: The canonical manifest form is stable**
    - **Validates: Requirements 10.9, 37.2**
    - `tests/property/app/agents/workflow_builder/test_canonical_properties.py`.

  - [x] 8.7 Write unit tests for stages, events and the canonical form
    - `tests/unit/app/agents/workflow_builder/test_stages.py` (labels per stage), `test_events.py` (discriminator, `extra="forbid"`, no `type` key inside `data`), `test_canonical.py` (each documented default and `agent_ids` order kept).
    - _Requirements: 38.2, 39.1, 10.9_

- [x] 9. Define the ports, builder rules, change summary and launch needs
  - [x] 9.1 Define the gate and turn ports
    - Create `backend/app/agents/workflow_builder/ports.py` with `GatePort`, `GateIssue` and `GateResult` from design §3.5.1.
    - Add `TurnPort`, the protocol through which the observer middleware, the script tool and `propose_draft` reach the live turn without importing `app.api`: publish an event, report a stage signal, `stop(reason)`, `stopping`, count a tool call, record a finished tool call, record a `/workflows/` write, report a gate rejection, accept a draft (returns the revision number), and read the turn's `canvas_state` and limits.
    - _Requirements: 48.5, 48.6_

  - [x] 9.2 Implement the builder rules and the single feature list
    - Create `backend/app/agents/workflow_builder/builder_rules.py` with `ForbiddenFeature`, `FORBIDDEN_FEATURES` holding exactly the six entries in design §3.5.3, step walkers through nested `subagents.steps` up to the compiler's depth limit, and `check(manifest, *, step_models, allowed_agent_ids) -> list[GateIssue]`.
    - `check` reports forbidden features with their path and reason, step agents outside the allow-list, step models and fallbacks outside the Step_List (naming the allowed ids), and efforts outside the model's levels.
    - _Requirements: 23.4, 23.5, 23.6, 23.7, 23.8, 41.11, 41.12, 42.3_

  - [x] 9.3 Write property test for the builder rules
    - **Property 8: Builder rules are sound and complete**
    - **Validates: Requirements 23.4, 23.5, 23.8, 41.11, 41.12, 42.3**
    - `tests/property/app/agents/workflow_builder/test_builder_rules_properties.py`, with nested manifests that place features at random depth and instruction-like text in string fields.

  - [x] 9.4 Implement the change summary and launch needs
    - Create `backend/app/agents/workflow_builder/change_summary.py` with `summarize(baseline, draft) -> ChangeSummary`: steps keyed by `instance_id` for `custom-agent` steps and by `agent` otherwise, nested steps keyed by path, and field comparison through `canonical.py`. The baseline is the turn's `canvas_state` [pending G-08].
    - Create `backend/app/agents/workflow_builder/launch_needs.py` with `derive(manifest) -> list[LaunchNeed]` per the table in design §3.5.4.
    - _Requirements: 7.7, 7.13, 23.17_

  - [x] 9.5 Write property test for the change summary and launch needs
    - **Property 10: Change summary and launch needs are exact**
    - **Validates: Requirements 7.7, 7.13, 23.17**
    - `tests/property/app/agents/workflow_builder/test_change_summary_properties.py`.

  - [x] 9.6 Write unit tests for the builder rules, change summary and launch needs
    - `tests/unit/app/agents/workflow_builder/test_builder_rules.py` (the feature list is pinned to the six ids, rejection texts name the feature and the allowed models), `test_change_summary.py`, `test_launch_needs.py`.
    - _Requirements: 23.5, 23.7, 41.12, 49.2_

- [x] 10. Implement adherence, transcript replay and the Turn_Context
  - [x] 10.1 Implement the adherence record
    - Create `backend/app/agents/workflow_builder/adherence.py` with `AdherenceRecord` and `record(tool_calls, line_counts)`. A mandatory file counts as read in full when the union of its `[offset, offset + limit)` ranges covers its line count from the skill package.
    - _Requirements: 28.10_

  - [x] 10.2 Write property test for the adherence record
    - **Property 28: Adherence is derived from what was read and run**
    - **Validates: Requirements 28.10**
    - `tests/property/app/agents/workflow_builder/test_adherence_properties.py`.

  - [x] 10.3 Implement transcript replay, the summary rules and the session projections
    - Create `backend/app/agents/workflow_builder/transcript.py` and `backend/app/agents/workflow_builder/prompts/transcript_summary.v1.md`.
    - Replay: build exchanges from stored rows (newest reply per user message, tool rows and thinking left out, "(no reply: the turn failed)" for a failed reply with no text); `select(exchanges, budget, keep_verbatim, summary_tokens)` counting with `count_tokens_approximately`, where the summary counts inside the budget and the current message is not one of the four kept exchanges; `summary_needed`; `summary_input` from the previous summary plus omitted messages after `summary_through_seq`; `has_required_headings` for the four headings; `history_messages` that prepends `<summary_of_earlier_turns>` to the oldest selected user message [pending G-22].
    - Projections: the display transcript (each user message once with its newest reply, earlier failed replies as "failed, retried"), `skill_updated`, `counts_toward_clarify(status, outcome, before_first_accepted)` that counts only `completed` turns with outcome `reply`, where seeds and undos do not end the count [pending G-09, G-10], `latest_unproposed(revisions)`, and `make_title(first_message)` (first line, whitespace collapsed, 60 characters plus an ellipsis) [pending G-24].
    - _Requirements: 12.2, 13.1, 16.3, 20.10, 25.2, 25.3, 25.4, 25.5, 25.6, 25.7, 25.8, 25.9, 37.3, 47.12, 47.13_

  - [x] 10.4 Write property test for replay selection
    - **Property 11: Replay selection invariants**
    - **Validates: Requirements 25.2, 25.3, 25.4, 25.5, 25.6, 25.8, 25.9, 47.12, 47.13**
    - `tests/property/app/agents/workflow_builder/test_transcript_replay_properties.py`, with transcripts that include retries, tool rows and long messages for Opus-sized and Sonnet-sized windows.

  - [x] 10.5 Write property test for the session projections
    - **Property 26: Session projections**
    - **Validates: Requirements 12.2, 12.6, 13.1, 16.3, 20.10, 23.13, 37.3, 47.7**
    - `tests/property/app/agents/workflow_builder/test_transcript_projection_properties.py`.

  - [x] 10.6 Render the Turn_Context
    - Create `backend/app/agents/workflow_builder/turn_context.py` with `render(inputs) -> str` producing the `<turn_context>` and `<user_message>` blocks in design §3.6.2: mode, Canvas_File and step count, whether the canvas changed since the latest seed, accepted or undo revision (canonical hash), unfinished work, the Target_Trust rule [pending G-13], product facts and premium permission, step models from the model view, forbidden features rendered from `FORBIDDEN_FEATURES`, the clarify count and the two-turn rule, limits read from settings, the skill path and the English rule.
    - _Requirements: 8.1, 8.2, 16.4, 16.5, 37.2, 37.3, 37.4, 37.5, 37.6, 37.7, 37.8, 37.9, 37.10, 45.2_

  - [x] 10.7 Write unit tests for adherence, transcript and the Turn_Context
    - `tests/unit/app/agents/workflow_builder/test_adherence.py`, `test_transcript.py` (heading check and the single-retry rule input), `test_turn_context.py` (each line present, values from settings, user text only inside `<user_message>`).
    - _Requirements: 25.7, 28.10, 37.2, 37.9, 49.2_

- [ ] 11. Checkpoint: pure agent-layer modules
  - From `backend/`: `uv run pytest tests/unit/app/agents/workflow_builder tests/property/app/agents/workflow_builder`, `uv run pytest --collect-only -q`, `uv run ruff check`, `uv run pyright`, `uv run lint-imports`.
  - Ensure all tests pass, ask the user if questions arise.

- [x] 12. Implement the script runner
  - [x] 12.1 Encode the allow-list policy as data
    - Create `backend/app/agents/workflow_builder/script_policy.py` with `OptionSpec`, `ScriptRule` and `POLICY` keyed by skill id, holding every row of the table in design §3.4.4 with its refusal text and alternative.
    - `selftest.py` takes no options, `export_manifest.py` takes exactly one output option and writes only under `/exports/`, and `refresh_catalog.py --check` refuses its path options [pending G-02, G-18].
    - _Requirements: 35.1, 35.2, 35.3, 35.5, 35.6, 35.7, 35.8, 35.9, 35.10, 35.11, 35.12_

  - [x] 12.2 Implement command parsing and path mapping
    - Create `backend/app/agents/workflow_builder/script_runner.py` with `parse_command(command, roots) -> ParsedCommand | Refusal` and `map_path(raw, slot, roots)`.
    - A shell-free tokenizer keeps backslashes. Unquoted `&&`, `||`, `;`, `|`, `&`, `<`, `>`, backtick, `$(` and newline are refused; the same characters inside quotes are literal [pending G-18]. One optional launcher is dropped; `-c`, `-m` and other interpreter options are refused. The script and its arguments are checked against `POLICY` by slot.
    - Skill prefixes map to the Skill_Folder; every other path resolves against the sandbox root, then `resolve()` and `is_relative_to` decide containment.
    - _Requirements: 27.9, 34.1, 34.2, 34.3, 34.4, 34.6, 34.7, 34.8, 35.4, 35.11, 35.12_

  - [x] 12.3 Write property test for shell-free parsing
    - **Property 2: Parsing is shell-free and independent of the form used**
    - **Validates: Requirements 34.2, 34.4, 34.6**
    - `tests/property/app/agents/workflow_builder/test_script_runner_parsing_properties.py`.

  - [x] 12.4 Implement subprocess execution and the `run_skill_script` tool
    - Extend `script_runner.py` with `script_env(tmp)` built from an allow-list, and `execute(parsed, ctx)` running `sys.executable -B -s -X utf8` with the sandbox as working directory, stdin closed, stdout and stderr merged, `BUILDER_SCRIPT_TIMEOUT_SECONDS`, a module-level `asyncio.Semaphore(BUILDER_MAX_CONCURRENT_SCRIPTS)` where a 9th call waits [pending G-18], kill and wait on timeout or cancel, and the call's temp folder removed in `finally`.
    - `read_capped` keeps a 60,000-character head and a 15,000-character tail with a cut note; the verdict is parsed from the uncut tail or the `--json` report; the result starts with `$ <command>` and `exit code: <n>` and stays within `BUILDER_SCRIPT_OUTPUT_CAP_CHARS` in total. Status mapping: validator exit 0 or 1 is `ok`, other non-zero exits are `error`, plus `timed_out`, `refused` and the stop statuses in design §3.4.6 [pending G-18].
    - The `--compiler` intercept runs the validator without it, emits `check_result` with source `skill_validator`, signals the `platform_check` stage, calls `GatePort.dry_run`, appends the dry-run section, emits `check_result` with source `platform_dry_run`, and exits 0 only when both pass. `file` and `builtin` trust get an `unknown` verdict.
    - `build_script_tool(ctx: ScriptContext)` returns the `run_skill_script` closure. `ScriptContext` carries the sandbox, the skill root, the gate port, the `TurnPort`, the semaphore and an injectable process spawner.
    - _Requirements: 18.3, 20.11, 27.4, 27.5, 31.6, 32.11, 34.5, 36.1, 36.2, 36.3, 36.4, 36.5, 36.6, 36.7, 36.8, 36.9, 36.11, 36.12, 47.14, 47.15, 48.15_

  - [x] 12.5 Write the process and gate fakes
    - `tests/fakes/process_factory.py`: `FakeProcessFactory`, which records each start with its argv, env and cwd, and plays back exit codes, output, delays and hangs.
    - `tests/fakes/builder_gate.py`: `FakeGate` implementing `GatePort` with scripted verdicts.
    - _Requirements: 49.3_

  - [x] 12.6 Write property test for script containment
    - **Property 1: Script commands cannot escape**
    - **Validates: Requirements 34.2, 34.3, 34.7, 34.8, 35.1, 35.2, 35.3, 35.4, 35.5, 35.6, 35.7, 35.8, 35.9, 35.10, 35.11, 35.12, 27.9, 49.3**
    - `tests/property/app/agents/workflow_builder/test_script_runner_escape_properties.py`, with command strings that mix allowed and forbidden tokens, quotes, backslashes, `..` segments, unicode and operators, and symlinked escapes under a temporary root.

  - [x] 12.7 Write property test for output handling
    - **Property 3: The output cap keeps the verdict, and the exit code reflects both checks**
    - **Validates: Requirements 36.1, 36.5, 36.7, 36.9, 36.11, 47.14**
    - `tests/property/app/agents/workflow_builder/test_script_runner_output_properties.py`.

  - [x] 12.8 Write property test for the script environment
    - **Property 4: The script environment is an allow-list**
    - **Validates: Requirements 36.3, 36.4**
    - `tests/property/app/agents/workflow_builder/test_script_runner_env_properties.py`.

  - [x] 12.9 Write property test for bounded concurrency and cleanup
    - **Property 5: Script calls are bounded and clean up after themselves**
    - **Validates: Requirements 31.6, 36.6, 47.15, 20.11**
    - `tests/property/app/agents/workflow_builder/test_script_runner_concurrency_properties.py`.

  - [x] 12.10 Write unit tests for the policy and the runner
    - `tests/unit/app/agents/workflow_builder/test_script_policy.py` (each table row, each refusal text) and `test_script_runner.py` (status mapping, tool result header, the `--compiler` intercept with `FakeGate`, runner `OSError` handling).
    - _Requirements: 35.12, 36.1, 36.9, 49.2_

- [x] 13. Build the file backend, middleware, `propose_draft`, the Server_Gate, read tools and the agent factory
  - [x] 13.1 Implement the composite file backend with the read-only skills route
    - Create `backend/app/agents/workflow_builder/backend_fs.py` with `ReadOnlySkillsBackend(FilesystemBackend)`, whose `write`, `awrite`, `edit`, `aedit`, `upload_files` and `aupload_files` return "The skill is read-only. Write your manifest under /workflows/." and whose `ls`, `glob` and `grep` show only the configured skill folders.
    - Add `build_builder_backend(sandbox_root, skills_root, skill_ids)` returning a `CompositeBackend` with `ValidatingFilesystemBackend` as default and the skills route at `/skills/`. No skill file is copied into the sandbox.
    - _Requirements: 20.6, 20.7, 20.8, 27.1, 27.2_

  - [x] 13.2 Implement the observer and pinning middleware
    - Create `backend/app/agents/workflow_builder/middleware.py` with `BuilderToolObserverMiddleware.awrap_tool_call`: take the call id, count the call through `TurnPort`, refuse the 61st call and stop the turn with `tool_calls` [pending G-04], emit `limit_warning` at 80 %, refuse `write_file` and `edit_file` outside `/workflows/` (and give the read-only message under `/skills/`), emit `tool_started` with the kind and label table, signal the stage, call the handler, emit `tool_finished` with a templated summary of at most 280 characters [pending G-19], record the tool row, record `/workflows/*.workflow.json` writes, and append the one-time limit notice to the ToolMessage. Refusals still emit a paired `tool_started` and `tool_finished`.
    - Add `PinnedTurnMessageMiddleware.awrap_model_call`, which re-inserts the message with id `turn:<turn_id>` after any leading summary message when summarisation removed it, changing the request only.
    - _Requirements: 20.7, 23.9, 24.5, 27.3, 28.3, 28.7, 28.9, 36.10, 36.13, 38.7, 38.8, 38.9, 39.4, 39.5, 39.6, 39.7, 39.8, 47.8_

  - [x] 13.3 Write property test for the write scope
    - **Property 21: Writes stay in `/workflows/` and the skill stays read-only**
    - **Validates: Requirements 18.8, 20.7, 27.2, 27.3**
    - `tests/property/app/agents/workflow_builder/test_write_scope_properties.py`, covering the middleware path check and `ReadOnlySkillsBackend` against a copy of the Skill_Folder in a temporary folder, with the skill hash compared before and after.

  - [x] 13.4 Write property test for the pinned turn message
    - **Property 12: The turn's message survives summarisation**
    - **Validates: Requirements 28.3**
    - `tests/property/app/agents/workflow_builder/test_pinned_message_properties.py`.

  - [x] 13.5 Implement `propose_draft`
    - Create `backend/app/agents/workflow_builder/draft_tool.py` with `build_draft_tool(ctx)` returning `propose_draft(path, target_trust="user", trust_reason=None)` [pending G-13].
    - Order of work per design §3.5.2: refuse when the turn is stopping; refuse a second draft in a turn and a path outside `/workflows/*.workflow.json`, a missing file, invalid JSON or a non-object, none of which count as rejections [pending G-11]; signal `platform_check`; call `GatePort.check`; on rejection count it, emit `check_result` with attempt and attempts left, return the numbered issues, and stop the turn with `gate_rejections` after the second [pending G-12]; on acceptance check `stopping` again, compute the change summary against `canvas_state` and the launch needs, accept the draft through `TurnPort`, emit `check_result` (valid), signal `applying`, then emit `draft_applied`.
    - _Requirements: 7.1, 7.6, 7.11, 23.1, 23.2, 23.10, 23.11, 23.12, 23.13, 23.14, 23.16, 23.17, 27.6, 30.4, 42.1, 47.3_

  - [x] 13.6 Implement the Server_Gate adapter
    - Create `backend/app/api/workflow_builder/gate.py` with `ServerGate(tier, max_trust, step_models, label, validate=_validated_manifest)` implementing `GatePort`. `check` runs `builder_rules.check` and `_model_entitlement_error` in `asyncio.to_thread`, then the trust check; `dry_run` reads the file and runs the same check without storing anything.
    - Trust check: accept at `user` when the save check passes there; accept at `db` only when it fails at `user`, passes at `db`, `db` was requested and `max_trust` is `db` (`_saved_row_trust(tier)`); otherwise reject, adding the "compiles at db trust" hint when it would compile at `db` [pending G-13]. `HTTPException(422)` becomes a `save_check` issue.
    - The validate callable is injectable so the property test can stub it; production always uses `_validated_manifest`, so the engine import stays inside `_compile_check_manifest`.
    - _Requirements: 7.11, 23.3, 23.4, 23.8, 36.1, 36.2, 48.5, 48.6, 48.13_

  - [x] 13.7 Write property test for least trust
    - **Property 9: The draft's trust is the least that works**
    - **Validates: Requirements 7.11, 37.4**
    - `tests/property/app/api/workflow_builder/test_gate_trust_properties.py`, with the validate callable stubbed per generated case.

  - [x] 13.8 Add the read-tool port and placeholder tools
    - Create `backend/app/agents/workflow_builder/read_tools.py` with `BuilderReadPort` (design §3.7) and placeholder tools `list_my_agents`, `list_my_skills`, `list_my_workflow_names`, `list_my_connectors`, `list_handoff_targets` and `get_builder_models`, each a closure over the caller's `user_id` and tier that returns bounded JSON with fixed fields [pending Q-18].
    - Add `PlaceholderReadPort`, which serves `builder_models` from `model_catalog_view` and answers the other calls with "not available yet". No user-data adapter is built until Q-18 supplies the tool list.
    - _Requirements: 27.7, 27.8, 39.5_

  - [x] 13.9 Write the versioned system prompt
    - Create `backend/app/agents/workflow_builder/prompts/system_prompt.v1.md` with exactly the six parts in design §3.6.1, including the read rule with `limit=1000` and the warning not to read `docs/catalog.md`, the schema, `references/catalog.json` or an example file whole [pending G-38].
    - `backend/.dockerignore`: add `!app/agents/workflow_builder/prompts/*.md`. `backend/Dockerfile`: extend the verify step with `test -f /app/app/agents/workflow_builder/prompts/system_prompt.v1.md`.
    - _Requirements: 15.4, 15.5, 19.1, 19.2, 19.3, 19.4, 19.5, 19.6, 19.7, 19.8, 19.9, 42.2_

  - [x] 13.10 Implement the agent factory
    - Create `backend/app/agents/workflow_builder/agent.py`: load `SYSTEM_PROMPT` once, compute `SYSTEM_PROMPT_SHA256` and `prompt_version = "v1:<first 12 hex>"`, and add `build_builder_runner(turn_inputs, sandbox, ports) -> DeepAgentRunner` per design §3.6.4.
    - Tools: `run_skill_script`, `propose_draft` and the read tools. Runner arguments: the composite backend, `checkpointer=None`, `interrupt_on=None`, `thread_id=f"builder:{session_id}"`, `skills_sources=["/skills/"]` (which excludes `task` and `execute`), the selected model and effort, and `extra_middleware=[PinnedTurnMessageMiddleware, BuilderToolObserverMiddleware]`. Nothing here imports the ExecutionEngine.
    - _Requirements: 5.3, 6.10, 10.4, 18.1, 18.2, 18.4, 18.5, 18.7, 18.8, 20.2, 20.3, 27.9, 27.10, 27.11, 28.1, 28.2, 28.3, 28.4, 48.1, 48.2, 48.11, 48.12_

  - [x] 13.11 Write unit tests for the agent-layer tools and the gate
    - `tests/unit/app/agents/workflow_builder/test_backend_fs.py`, `test_middleware.py` (labels table, write scope, pairing on refusal, limit notice once), `test_draft_tool.py` (path errors not counted, second draft refused, stopping turn), `test_read_tools.py`, `test_agent.py` (prompt file content per Req 19.3 to 19.9, bound tools exclude `task` and `execute`, `prompt_version` format).
    - `tests/unit/app/api/workflow_builder/__init__.py` and `tests/unit/app/api/workflow_builder/test_gate.py` (`HTTPException(422)` mapped to a `save_check` issue, entitlement issue, rules before compile).
    - _Requirements: 19.3, 19.4, 19.5, 19.6, 19.7, 19.8, 19.9, 23.10, 27.9, 49.2_

- [ ] 14. Checkpoint: agent layer
  - From `backend/`: `uv run pytest tests/unit/app/agents tests/unit/app/api/workflow_builder tests/property/app/agents/workflow_builder tests/property/app/api/workflow_builder`.
  - `uv run python -m tools.ci.builder_skill_checks --selftest` and, from the repository root, `git status --porcelain --ignored -- backend/app/agents/workflow_builder/skills` shows no new file.
  - `uv run pytest --collect-only -q`, `uv run ruff check`, `uv run pyright`, `uv run lint-imports`.
  - Ensure all tests pass, ask the user if questions arise.

- [x] 15. Implement the event bus and the turn runner
  - [x] 15.1 Implement the session event bus
    - Create `backend/app/api/workflow_builder/bus.py` with `SessionEventBus`: `subscribe(session_id, snapshot_fn)` registers the queue and builds the snapshot in one synchronous block [pending G-14], `unsubscribe`, non-blocking `publish` that evicts a full queue with a `None`, `close_session(session_id, final)` and `close_all()`. Queues use `SSE_SUBSCRIBER_QUEUE_MAXSIZE`. The bus never touches `_PIPELINE_QUEUES` or `_SUBSCRIBERS`.
    - _Requirements: 31.4, 40.4, 40.5_

  - [x] 15.2 Implement the live turn, the registries and the turn port adapter
    - Create `backend/app/api/workflow_builder/turns.py` with `LiveTurn` (single `stop_reason`, first stop wins, task cancel), `_LIVE_TURNS`, `_TURN_TASKS`, and `TurnRunner` implementing `TurnPort`: per-turn `seq` assigned before publish, stage changes through `derive_stage`, tool rows stored through `asyncio.to_thread` with the stored result cut to 3,000 head and 1,000 tail characters [pending G-19], accepted drafts stored as revisions, and gate rejection counting.
    - Add `build_snapshot(session_id)` from the in-process turn state (stage, activity, checks, `through_seq`) and the latest stored ids.
    - _Requirements: 21.8, 24.5, 36.13, 38.2, 38.3, 40.6, 48.16_

  - [x] 15.3 Add builder telemetry
    - Create `backend/app/api/workflow_builder/telemetry.py` with turn metrics (latency, time per stage, tokens, adherence, status, skill hash), script call metrics (duration, exit code, refused) and gate rejection metrics, emitted as structured log records that carry the session id and turn id and never message text.
    - The repository has no OpenTelemetry setup under `backend/app/` today, so this task does not add an exporter. Connecting these records to OpenTelemetry is a separate decision to confirm.
    - _Requirements: 42.4, 44.2, 44.3, 44.4, 44.5_

  - [x] 15.4 Implement `run_turn`, the agent input and `finalize_turn`
    - Extend `turns.py` with `run_turn(turn, request)` per design §3.1.4: time cap and 80 % warning timers from settings; `turn_started` and the `starting` stage; `BuilderSandbox` rebuild when the folder is missing; `/canvas/current.workflow.json` written without touching `/workflows/`; the agent input from `transcript.select`, a summary written or updated through `build_model(model_id, effort=None)` with one retry on missing headings, and `turn_context.render`, with the final message id `turn:<turn_id>`; `build_builder_runner`; event handling for thinking, text, usage (token budgets when set) and errors (recursion text stops with `recursion`).
    - `finalize_turn` runs under `asyncio.shield` with writes in `asyncio.to_thread`: one terminal status from the stop reason, with tool-call, token and recursion stops stored as `timed_out` [pending G-04]; the unproposed revision rule, including outcome `unfinished` after the second rejection [pending G-12]; the clarify count; adherence; usage including summary tokens; skill hash and `prompt_version`; telemetry; `turn_completed`; registry cleanup. Nothing stops a turn at 180 s.
    - _Requirements: 5.4, 8.1, 16.3, 20.2, 20.3, 20.9, 20.12, 21.5, 21.6, 21.9, 22.3, 23.18, 25.1, 25.8, 25.9, 25.10, 28.4, 28.5, 28.6, 28.8, 28.10, 28.11, 37.1, 43.5, 44.1, 44.2, 47.4, 47.5, 47.9, 48.16_

  - [x] 15.5 Implement cancel and the stop functions
    - Extend `turns.py` with `cancel_turn(session_id, turn_id)` returning `cancelling` or `not_running` [pending G-35], `stop_session_turn(session_id, reason="deleted")`, `stop_user_turns(user_id)` and `stop_all(reason="shutdown", persist_seconds)`. A draft accepted before a cancel stays, with `turn_completed` carrying `status: cancelled` and `outcome: draft`.
    - _Requirements: 22.1, 30.2, 30.3, 30.4, 30.5, 31.3_

  - [x] 15.6 Write the scripted chat model fake
    - `tests/fakes/scripted_chat_model.py`: `FakeChatModel`, a `BaseChatModel` that plays back scripted tool calls, thinking, text, usage and errors, used verbatim by `DeepAgentRunner`.
    - _Requirements: 49.4_

  - [x] 15.7 Write property test for turn event streams
    - **Property 14: Turn event streams are well formed**
    - **Validates: Requirements 7.1, 23.10, 23.11, 23.12, 30.4, 36.2, 36.10, 38.2, 38.9, 38.10, 38.14, 42.1, 47.3**
    - `tests/property/app/api/workflow_builder/test_turn_events_properties.py`, driving scripted turns through `TurnRunner` with `FakeChatModel`, `FakeGate`, `FakeProcessFactory` and `InMemoryBuilderStore`.

  - [x] 15.8 Write property test for terminal status
    - **Property 15: A turn ends with exactly one status**
    - **Validates: Requirements 21.9, 22.1, 22.3, 23.18, 30.3, 30.5, 48.16**
    - `tests/property/app/api/workflow_builder/test_turn_status_properties.py`.

  - [x] 15.9 Write property test for limits
    - **Property 16: Limits warn once and stop at the cap**
    - **Validates: Requirements 28.4, 28.7, 28.8, 28.9, 47.8**
    - `tests/property/app/api/workflow_builder/test_turn_limits_properties.py`, driving the observer middleware and the usage handling in `run_turn` with fakes.

  - [x] 15.10 Write property test for fan-out and snapshots
    - **Property 24: Every client sees the same turn**
    - **Validates: Requirements 13.3, 17.9, 17.10, 40.4, 40.5, 40.6**
    - `tests/property/app/api/workflow_builder/test_fanout_snapshot_properties.py`, interleaving connect times with an event stream and applying the client `seq` dedupe rule.

  - [x] 15.11 Write unit tests for the bus, turns and telemetry
    - `tests/unit/app/api/workflow_builder/test_bus.py` (eviction on a full queue, close order), `test_turns.py` (finalize per status, unproposed revision candidates, sandbox rebuild input, cancel responses), `test_telemetry.py` (no message text in records).
    - _Requirements: 22.1, 23.18, 30.3, 42.4, 49.2_

- [x] 16. Implement admission, routes, the session stream and lifecycle
  - [x] 16.1 Define the API schemas
    - Create `backend/app/api/workflow_builder/schemas.py` with the request and response models in design §3.2.2, reusing the shared value models from `events.py`. `BuilderModelsResponse.models` items are `ModelCatalogEntry`, and `default_efforts` carries each model's `default_effort` [pending G-27].
    - _Requirements: 12.6, 21.2, 41.14_

  - [x] 16.2 Implement admission and the access dependency
    - Create `backend/app/api/workflow_builder/admission.py` with `require_builder_access` (authentication, the flag giving 404, the custom entitlement giving 403 before any lookup [pending G-07], readiness giving 503 `builder_unavailable`) and a readiness holder that lifecycle sets.
    - Add `admit_message` running checks 6 to 16 of design §3.1.2 in order under a per-user `asyncio.Lock` [pending G-05]: session lookup, duplicate `client_message_id` returning the original ids with `replayed: true`, running turn (409), `check_chat_choice`, `canvas_state` structure and size in compact UTF-8 bytes, the 100-turn limit, the rolling 60 s rate limit with `Retry-After`, two running turns per user, and `_require_host_capacity` last; then insert the user and running assistant messages in one transaction, set the session's model and effort and the title on the first message, map `IntegrityError` to 409, and start `run_turn`. Content length counts code points and whitespace-only is empty [pending G-23]. Refusals store nothing and publish nothing.
    - _Requirements: 2.4, 2.5, 4.7, 21.2, 21.3, 21.7, 21.8, 21.10, 21.11, 21.12, 26.2, 26.3, 26.4, 26.5, 29.1, 29.2, 29.3, 29.4, 29.5, 42.5, 45.3, 47.1, 47.2, 47.6, 47.10, 47.11_

  - [x] 16.3 Write property test for admission
    - **Property 17: Admission stores only accepted messages**
    - **Validates: Requirements 2.5, 21.7, 21.10, 26.2, 29.1, 29.2, 29.3, 47.2, 47.6, 47.10**
    - `tests/property/app/api/workflow_builder/test_admission_properties.py` against `InMemoryBuilderStore`, with the capacity gate and clock stubbed.

  - [x] 16.4 Write property test for message and canvas validation
    - **Property 18: Message and canvas validation**
    - **Validates: Requirements 4.7, 21.11, 21.12, 47.1, 47.11**
    - `tests/property/app/api/workflow_builder/test_admission_validation_properties.py`.

  - [x] 16.5 Implement the REST routes
    - Create `backend/app/api/workflow_builder/routes.py` with thin handlers under `/api/workflow-builder` for the endpoints in design §3.2.1: `GET /models` (through `project_model_entry` and the user's Settings preference), session create, list, get and delete, messages, retry, cancel, undo and link.
    - Create in edit mode checks ownership (404 `workflow_not_found` [pending G-07]) and stores revision 0 from the row's effective manifest. For a base that is not `custom`, fill in the base pipeline's `deliverable`, `planner` and `clarify` when the row lacks them; the design leaves the method open, so confirm it while implementing.
    - Retry accepts only the latest failed turn and reuses its user message through admission checks 8 to 16 [pending G-01]. Undo checks `expected_revision`, stores an `undo` revision from the starting user message's `canvas_state` and publishes `draft_restored` [pending G-16]. Delete stops the turn with `deleted`, removes rows, removes the sandbox with one retry and closes streams with `session_deleted`. Link checks ownership and updates `linked_manifest_hash`.
    - _Requirements: 2.7, 2.9, 2.10, 6.2, 8.4, 8.5, 11.5, 12.6, 13.1, 20.1, 20.13, 20.14, 20.15, 21.1, 23.15, 30.2, 31.2, 31.3, 31.4, 41.14, 42.5_

  - [x] 16.6 Implement the session stream
    - Create `backend/app/api/workflow_builder/stream.py` with `GET /api/workflow-builder/sessions/{id}/events`: owner lookup in request scope (404 otherwise), short-lived sessions inside the generator, `EventSourceResponse` with `SSE_KEEPALIVE_PING_SECONDS`, `X-Accel-Buffering: no` and `Cache-Control: no-cache`, the snapshot first, frames through `_sse_body` with no `id:` line, and the stream kept open between turns.
    - Revocation: wait with `asyncio.wait_for(..., SSE_REVOCATION_CHECK_INTERVAL_SECONDS)`, call `_run_revocation_check` after every `SSE_REVOCATION_CHECK_EVERY_N_EVENTS` events and on every timeout, and send `session_revoked` then close on failure; the revoked user's turn keeps running [pending G-15].
    - _Requirements: 2.7, 21.4, 38.1, 38.3, 40.1, 40.2, 40.3, 40.4, 40.6, 40.7, 40.8, 42.5, 48.3_

  - [x] 16.7 Write property test for the revocation cadence
    - **Property 25: Revocation is checked on cadence**
    - **Validates: Requirements 40.7, 40.8**
    - `tests/property/app/api/workflow_builder/test_stream_revocation_properties.py`, driving the stream generator with a fake queue and clock and a stubbed `_run_revocation_check`.

  - [x] 16.8 Compute the success metrics and the storage report
    - Create `backend/app/agents/workflow_builder/success_metrics.py` with pure functions for the three metrics in Req 44.6. This module is not in the design's module map; it exists for Property 29.
    - Extend `backend/app/api/workflow_builder/store.py` with the rows those functions read and with per-user row counts and sizes; combine them with sandbox folder sizes in `storage_report()`. The design names no reporting surface, so lifecycle logs the report at startup (task 16.10); confirm whether an admin view is wanted.
    - _Requirements: 44.6, 44.7_

  - [x] 16.9 Write property test for the success metrics
    - **Property 29: Success metrics match their definitions**
    - **Validates: Requirements 44.6**
    - `tests/property/app/agents/workflow_builder/test_success_metrics_properties.py`.

  - [x] 16.10 Implement lifecycle and wire the router
    - Create `backend/app/api/workflow_builder/lifecycle.py` with `builder_startup()`: verify the skill package (a failure marks the builder unavailable and logs one ERROR) [pending G-21], run `assert_builder_catalog_valid` (a failure raises and stops the process), run the sweep that marks running assistant rows `interrupted` with `stop_reason='restart'` and stores unproposed revisions from file times, log the storage report, and set readiness. A failed sweep marks the builder unavailable. Add `stop_builder_turns(reason="shutdown")` with `BUILDER_SHUTDOWN_PERSIST_SECONDS`, then `close_all()` on the bus [pending G-17].
    - `backend/app/api/workflow_builder/__init__.py`: export `router` (routes plus stream). `backend/app/main.py`: register it next to `user_workflows_router` and call `builder_startup()` in the lifespan before "Backend ready". `backend/app/api/run_shutdown.py`: call `stop_builder_turns()` as the first step of `shutdown_run_infrastructure()`.
    - `backend/app/api/admin.py`: call `stop_user_turns(user_id)` before deleting the user's builder rows.
    - _Requirements: 22.1, 22.2, 22.3, 22.4, 22.5, 31.7, 41.8, 48.16_

  - [x] 16.11 Write property test for content hygiene
    - **Property 23: User content stays out of the prompt, events and logs**
    - **Validates: Requirements 17.4, 38.15, 38.16, 38.17, 42.2, 42.4, 42.5**
    - `tests/property/app/api/workflow_builder/test_content_hygiene_properties.py`, running scripted turns and failing requests with marker strings, with `caplog` capturing every log record.

  - [x] 16.12 Write unit tests for admission, routes, stream and lifecycle
    - `tests/unit/app/api/workflow_builder/test_admission.py` (check order with mocked dependencies), `test_schemas.py`, `test_routes.py` (undo staleness, retry eligibility, cancel responses, edit-mode seeding), `test_stream.py` (snapshot first, headers), `test_lifecycle.py` (sweep, unavailable paths, shutdown step order), and `tests/unit/app/agents/workflow_builder/test_success_metrics.py`.
    - _Requirements: 8.5, 13.1, 22.2, 29.1, 40.4, 49.2_

- [ ] 17. Checkpoint: backend complete
  - From `backend/`: `uv run pytest tests/unit tests/property`, `uv run pytest tests/unit/agents/test_banned_patterns.py tests/unit/agents/test_sse_cutover_banned_patterns.py tests/security/test_route_contract.py`, `uv run alembic heads` (exactly `0051 (head)`).
  - SC-001: `Get-ChildItem -Recurse agents/execution_engine -Filter *.py | Select-String -Pattern 'if pipeline_type ==', 'spec\.id =='` prints nothing, and `git status --porcelain agents/execution_engine` prints nothing.
  - INV-3: `Remove-Item Env:SNAPSHOT_UPDATE -ErrorAction SilentlyContinue`, then `uv run pytest (Get-ChildItem tests/agents/test_characterization_*.py, tests/contract/agents/test_characterization_*.py).FullName`, then `git status --porcelain tests/agents/characterization/golden/` prints nothing.
  - `uv run pytest --collect-only -q`, `uv run ruff check`, `uv run pyright`, `uv run lint-imports`.
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 18. Build the frontend data layer and pure logic
  - [x] 18.1 Define the wire types and the REST client
    - Create `frontend/src/types/workflowBuilder.ts` with the session, message, revision, model and stream event types matching `schemas.py` and `events.py`, plus `ComposerBuilderBinding` from design §3.10.7.
    - Create `frontend/src/lib/workflowBuilderApi.ts` on `authedFetch`, throwing `ApiError` so a 503 `host_capacity_exhausted` reaches `ServiceBusyProvider` and a 401 reaches session expiry; one function per endpoint, and `client_message_id` from `crypto.randomUUID()`.
    - _Requirements: 13.5, 13.10, 21.1, 21.2, 41.14_

  - [x] 18.2 Implement the session-stream hook
    - Create `frontend/src/hooks/useBuilderSessionStream.ts`: `fetch` with `Accept: text/event-stream` and `Authorization: Bearer`, a `ReadableStream` reader and `TextDecoder`, blocks parsed with `parseSseBlock` from `lib/sseFrame.ts`, no `Last-Event-ID`, reconnect with backoff from 1 s doubling to 30 s, silent token refresh with `refreshOnce` and `getTokenExpiryMs`, and stop on 404, `session_deleted` or `session_revoked`, where `session_revoked` calls `expireSession()` [pending G-14, G-15].
    - _Requirements: 13.2, 13.3, 13.5, 17.12, 17.13, 40.9, 48.10_

  - [x] 18.3 Port the canonical form to TypeScript
    - Create `frontend/src/lib/canonicalManifest.ts` with the same default list, `null` removal and sorted compact serialisation as `canonical.py`, plus `canonicalHash`. Create the shared cases file `frontend/src/lib/canonicalManifest.cases.json` [pending G-34].
    - _Requirements: 10.9, 37.2_

  - [x] 18.4 Fix effort hydration and add `compiledRootIds`
    - `frontend/src/store/api/userWorkflows.ts`: in `manifestStepsToGateSelections`, copy `model.effort` as well as `model.model` (R-12); add `compiledRootIds(manifest)`, a direct port of `export_manifest.compiled_root_ids`.
    - _Requirements: 7.9, 10.9_

  - [x] 18.5 Write property test for effort hydration
    - **Property 32: Effort survives hydration**
    - **Validates: Requirements 7.9**
    - `frontend/src/store/api/userWorkflows.effortHydration.property.test.ts`.

  - [x] 18.6 Write the canonical-form parity tests
    - `frontend/src/lib/canonicalManifest.test.ts` asserts the TypeScript output for every case in `canonicalManifest.cases.json`.
    - `backend/tests/contract/test_canonical_manifest_parity.py` asserts the Python output for the same file, so the two implementations cannot drift.
    - _Requirements: 10.9, 49.8_

  - [x] 18.7 Implement the builder reducer
    - Create `frontend/src/components/workflowBuilder/builderReducer.ts` with the state model in design §3.10.4 (`SessionLoad`, `TurnView`, `CanvasDraft`, `Notice`) and its rules: origin `this_tab`, `other_tab` or `rejoined`; turn events at or below `lastSeq` ignored; text and thinking appended only for `this_tab` [pending G-28]; `draft_applied` applied at once in the sending tab and held in `pendingDraft` elsewhere until `turn_completed` [pending G-03]; `draft_restored` handling [pending G-16]; `turn_completed` moving to `ended`.
    - _Requirements: 5.1, 5.2, 7.2, 7.10, 17.2, 17.9, 17.10, 17.11_

  - [x] 18.8 Write property test for the reducer
    - **Property 34: The panel reducer is consistent**
    - **Validates: Requirements 5.1, 5.2, 7.10, 17.2, 17.9**
    - `frontend/src/components/workflowBuilder/builderReducer.property.test.ts`.

  - [x] 18.9 Implement the panel selectors
    - Create `frontend/src/components/workflowBuilder/builderSelectors.ts`: `codePointLength` (`Array.from(text).length`), `canSend(text, turn)`, `undoTargetMessageId(transcript, revisions)`, `activitySummary(activity, checks, duration)` and `isTurnRunning(state)` [pending G-23].
    - _Requirements: 4.5, 4.6, 8.3, 9.3, 17.7_

  - [x] 18.10 Write property test for the Undo target
    - **Property 35: Undo is offered on the right message only**
    - **Validates: Requirements 8.3**
    - `frontend/src/components/workflowBuilder/builderSelectors.undo.property.test.ts`.

  - [x] 18.11 Write property test for the Send rule
    - **Property 38: Send is allowed exactly when the server would accept**
    - **Validates: Requirements 4.5, 4.6**
    - `frontend/src/components/workflowBuilder/builderSelectors.send.property.test.ts`.

  - [x] 18.12 Implement the picker logic
    - Create `frontend/src/components/workflowBuilder/modelPicker.ts`: thinking options from the selected model's `reasoning_levels` labelled with `effortLabel`, hidden for `reasoning_mode: none`; model change through `modelChangePatch` with the model's `default_effort` when the patch leaves the effort empty; preselection from the stored choice, then the Settings preference, then the default model, with a note when the stored model is no longer offered; `null` effort for a model with no levels [pending G-27].
    - _Requirements: 6.3, 6.4, 6.5, 6.6, 6.8, 6.9_

  - [x] 18.13 Write property test for picker selection
    - **Property 37: Picker selection**
    - **Validates: Requirements 6.3, 6.4, 6.6, 6.8**
    - `frontend/src/components/workflowBuilder/modelPicker.property.test.ts`.

  - [x] 18.14 Implement report folding and the announcement scheduler
    - Create `frontend/src/components/workflowBuilder/reportFold.ts`: a reply whose first line starts with "Context loaded this turn" splits into a summary up to the first `## ` heading and the full report; other replies are not folded [pending G-30].
    - Create `frontend/src/components/workflowBuilder/liveAnnouncer.ts`: announces stage labels, the applied-draft line and the turn-end line, never streamed text, at most one stage label every 3 s with the latest stage winning [pending G-29].
    - _Requirements: 14.2, 14.3, 14.4, 14.5, 15.1_

  - [x] 18.15 Write property test for report folding
    - **Property 40: Report folding loses nothing**
    - **Validates: Requirements 15.1**
    - `frontend/src/components/workflowBuilder/reportFold.property.test.ts`.

  - [x] 18.16 Write property test for the live region
    - **Property 39: The live region announces only what it should**
    - **Validates: Requirements 14.2, 14.5**
    - `frontend/src/components/workflowBuilder/liveAnnouncer.property.test.ts`, with fake timers.

  - [x] 18.17 Write unit and hook tests for the data layer
    - `frontend/src/hooks/useBuilderSessionStream.test.ts` (backoff schedule, stop on 404, `session_deleted` and `session_revoked`, `expireSession` call), `frontend/src/lib/workflowBuilderApi.test.ts` (throws `ApiError`, request bodies), `frontend/src/components/workflowBuilder/builderReducer.test.ts` (named transitions).
    - _Requirements: 13.5, 40.9, 49.12_

- [x] 19. Build the builder components
  - [x] 19.1 Implement the model picker component
    - Create `frontend/src/components/workflowBuilder/BuilderModelPicker.tsx` with labelled Model and Thinking selects driven by `modelPicker.ts`, the model list from `GET /models` only, and an error state with Retry when the list fails to load.
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 48.4_

  - [x] 19.2 Implement the message component
    - Create `frontend/src/components/workflowBuilder/BuilderMessage.tsx`: `react-markdown` with `remark-gfm` and no `rehype-raw` (the `components/chat/ResultCard.tsx` pattern), the report fold, a collapsed "Thinking" block, horizontally scrolling tables, a reading-view dialog, the change summary and launch needs for a turn with an accepted draft, the stop notice worded by `stop_reason` with Continue, the error line with Retry, the Undo control, and the "builder was updated" line when `skill_updated` is true.
    - _Requirements: 4.8, 4.9, 4.10, 5.2, 7.7, 7.13, 13.1, 13.8, 13.9, 15.1, 15.2, 15.3, 16.1, 20.10_

  - [x] 19.3 Write property test for safe Markdown
    - **Property 36: Assistant Markdown never creates HTML elements**
    - **Validates: Requirements 4.8**
    - `frontend/src/components/workflowBuilder/BuilderMessage.property.test.tsx`, rendering generated text with raw HTML, script tags, event-handler attributes and `javascript:` links.

  - [x] 19.4 Implement the transcript, progress, input and live region
    - Create `BuilderProgress.tsx` (stage label and ticking elapsed time, activity lines with status and duration, expandable summary and script command, check lines, limit notices, the collapsed one-line summary), `BuilderTranscript.tsx` (messages in order, "Still working" for a rejoined turn), `BuilderInput.tsx` (textarea, Enter sends, Shift+Enter inserts a newline, IME composition ignored, counter past 11,000, Send and Stop driven by `builderSelectors.ts`) and `BuilderLiveRegion.tsx` (one `aria-live="polite"` element fed by `liveAnnouncer.ts`), all in `frontend/src/components/workflowBuilder/`.
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 5.5, 5.6, 14.2, 14.3, 14.4, 14.5, 16.2, 17.1, 17.2, 17.3, 17.4, 17.5, 17.6, 17.7, 17.8, 23.9, 30.1_

  - [x] 19.5 Implement the panel, header, popup and entry button
    - Create `BuilderPanelHeader.tsx` (title, session menu with the first page and "Show more", delete with confirmation, New conversation, collapse), `BuilderPanel.tsx` (380 px column at 1024 px and wider, overlay with backdrop and focus trap below that, focus returned to the AI button on close), `BuilderPopup.tsx` (prompt box with the panel's input rules, example prompts that fill the box without sending, the picker, five recent sessions, inline error that keeps the text) [pending G-25] and `BuildWithAiButton.tsx`, all in `frontend/src/components/workflowBuilder/`. Colours and spacing use the tokens and classes in `frontend/src/styles/globals.css`.
    - _Requirements: 1.6, 1.11, 3.1, 3.3, 12.1, 12.7, 12.8, 14.1, 14.6_

  - [x] 19.6 Write component tests
    - Colocated Vitest and React Testing Library tests queried by role, label or text: `BuilderPopup.test.tsx`, `BuilderPanel.test.tsx`, `BuilderModelPicker.test.tsx`, `BuilderTranscript.test.tsx`, `BuilderProgress.test.tsx`, `BuilderInput.test.tsx`, `BuilderLiveRegion.test.tsx`, `BuilderPanelHeader.test.tsx`.
    - _Requirements: 4.3, 4.4, 6.4, 12.7, 14.1, 17.7, 49.12_

- [x] 20. Integrate with the Composer and add the entry points
  - [x] 20.1 Add the path-keyed shallow-navigation guard
    - `frontend/src/lib/shallowNavGuard.ts`: add `markShallowNavTo(path)` and `consumeShallowNavTo(path)` beside the existing counter.
    - `frontend/src/app/[...view]/page.tsx`: the `/workflows/{id}/edit` cold-mount effect returns early when `consumeShallowNavTo(currentPath)` is true, so `savedComposition` stays `null` and the composer is not remounted.
    - _Requirements: 3.8, 10.7, 10.11_

  - [x] 20.2 Add the builder binding and the apply-draft path to `ComposerPage`
    - Create `frontend/src/lib/builderDraft.ts` with the pure state computation for a draft (`pipelineAgents` from `manifestStepsToAgents`, replaced `selections` from `manifestStepsToGateSelections`, `capabilities`, `runConfig`) and the unsaved rule (`snapshot !== baseline || draftDirty`).
    - `frontend/src/components/workflow/composer/ComposerPage.tsx`: accept the optional `builder` prop; apply a draft once per revision through a ref, rebuilding agents when the library loads; keep `draftSource` and `draftTrust`; set `draftDirty` on apply and clear it on a successful save; report unsaved work with the new rule without resetting the baseline; register `getManifest` and `isDirty` through `registerCanvasApi`. The three existing one-shot seeding refs stay untouched, and the composer opens no stream.
    - _Requirements: 7.2, 7.3, 7.4, 7.5, 7.6, 7.8, 9.2, 40.10, 43.2, 48.9_

  - [x] 20.3 Write property test for applying drafts
    - **Property 33: Applying drafts replaces state and keeps it unsaved**
    - **Validates: Requirements 7.5, 7.8, 23.16**
    - `frontend/src/lib/builderDraft.property.test.ts`.

  - [x] 20.4 Make the canvas read-only during a turn and gate Run once
    - `ComposerPage.tsx`: wrap the canvas, rails and agent library in an element with `inert={builder?.turnRunning}`, disable Save and Run once while a turn runs, and show "The builder is updating this workflow."
    - Disable Run once when `draftTrust === "db"` and the canvas is dirty, with the note in design §3.10.7 item 5. Render the AI header button when `builder.aiButtonVisible`.
    - Switch to Canvas view when the panel opens, through a `panelOpen` flag added to `ComposerBuilderBinding` (the design's interface omits it); Simple view keeps working.
    - _Requirements: 1.2, 3.4, 3.5, 3.6, 7.12, 9.1, 9.3, 9.4_

  - [x] 20.5 Integrate Save with the builder
    - `ComposerPage.tsx`: build the save manifest with `draftSource ?? initialManifest` as passthrough, make `needsFullManifestOnSave` true when `draftSource` is set, send `compiledRootIds(manifest)` as `agent_ids` when a draft is the source, pre-fill the name modal from the draft's `name` (or `id`) and `description`, and call `builder.onSaved({ id, baseIsCustom })` after success.
    - When the linked row's base is not `custom`, Save becomes "Save as new" (POST) and leaves the original row unchanged; "Save as new" pre-fills "<name> (AI)" and adds " 2", " 3" and so on after a 409 [pending G-34]. Existing 422 and 409 errors keep the current save UI.
    - _Requirements: 10.1, 10.2, 10.3, 10.5, 10.6, 10.8, 10.9, 10.10, 10.11_

  - [x] 20.6 Write property test for the render-and-save round trip
    - **Property 31: Render-and-save round trip**
    - **Validates: Requirements 7.3, 7.4, 10.9, 49.8**
    - `frontend/src/store/api/userWorkflows.builderRoundtrip.property.test.ts`, generating variations of the allowed patterns with unknown step and top-level keys.

  - [x] 20.7 Implement the composer host
    - Create `frontend/src/components/workflowBuilder/BuilderComposerHost.tsx`, which owns the reducer, the stream hook and the REST calls, and renders `ComposerPage` with every existing prop plus `builder`. When `canRunPipeline(tier, "custom")` is false or `GET /models` does not return 200, it renders exactly what `DashboardLayout` renders today.
    - Flows: the AI button reopens the panel when `?ai=` is set and otherwise opens the popup; popup send creates the session, updates the URL per design §3.10.6 (marking the guard before `replaceState`), mounts the panel and sends the popup text once on the first `snapshot`; `canvas_state` comes from `getManifest`; after a save it calls the link endpoint and moves the URL; Undo asks before discarding manual edits; Retry uses the retry endpoint [pending G-01]; Continue sends "continue"; New conversation checks `isDirty`, navigates to `/workflows/new` when needed, creates the session on the first message and keeps the model [pending G-26]; history opens a session and applies its latest draft or the linked row; held drafts in other tabs load at turn end after the unsaved-work prompt [pending G-03]; `session_deleted` shows the deleted notice; 409, 404 and the linked-row note show their states.
    - Read `frontend/node_modules/next/dist/docs` for `useSearchParams` and its Suspense rules before using it, per `frontend/AGENTS.md`.
    - _Requirements: 1.3, 1.5, 1.7, 1.8, 1.9, 1.10, 2.1, 2.2, 2.3, 3.2, 3.7, 3.8, 3.9, 3.10, 6.7, 7.10, 8.4, 8.6, 8.7, 9.2, 10.7, 10.11, 11.1, 11.2, 11.3, 11.4, 12.3, 12.4, 12.5, 12.9, 13.3, 13.4, 13.6, 13.7, 13.10, 17.9, 17.10, 17.11, 17.12, 17.13, 40.10_

  - [x] 20.8 Wire the host and the `/workflows` entry point
    - `frontend/src/components/layout/DashboardLayout.tsx`: render `BuilderComposerHost` in place of the direct `ComposerPage` element for `mainView === "composer"`, keeping the `key`.
    - `frontend/src/components/savedworkflows/SavedWorkflowsPage.tsx`: add the optional `onBuildWithAi` prop and render `BuildWithAiButton` next to "New workflow"; `DashboardLayout` passes a handler that opens the popup on `/workflows`.
    - _Requirements: 1.1, 1.4, 2.1, 2.2_

  - [x] 20.9 Write jsdom integration tests for the composer integration
    - `frontend/src/components/workflowBuilder/BuilderComposerHost.integration.test.tsx`: apply-draft path, other-tab hold and prompt, read-only canvas during a turn, Undo confirmation, "Save as new" on a non-custom row, the Run once note at `db` trust, and the URL move after the first save without a remount.
    - `frontend/src/components/workflow/composer/ComposerPage.builderEffort.test.tsx`: apply a draft that sets a step's effort, check the config rail shows it, change that step's model and check the effort follows `modelChangePatch`.
    - _Requirements: 3.8, 7.5, 7.9, 7.12, 8.6, 9.3, 10.10, 17.11, 49.9, 49.12_

- [ ] 21. Checkpoint: frontend
  - From `frontend/`: `npm run test`, `npm run lint`, `npm run build`.
  - Ensure all tests pass, ask the user if questions arise.

- [x] 22. Add the contract, security, integration, end-to-end and per-pattern suites
  - [x] 22.1 Write the contract tests
    - `backend/tests/contract/test_workflow_builder_openapi_contract.py` snapshots the builder paths from `app.openapi()` into `tests/fixtures/workflow_builder/openapi_builder_paths.json`; no OpenAPI snapshot exists in the repository today, so this creates one scoped to the builder routes.
    - `backend/tests/contract/test_workflow_builder_event_schema_contract.py` snapshots the JSON schema of `BuilderEvent` into `tests/fixtures/workflow_builder/builder_event_schema.json`, and checks that `BuilderModelsResponse.models` items are `ModelCatalogEntry`.
    - _Requirements: 38.1, 41.14, 49.6_

  - [x] 22.2 Write the security tests
    - `backend/tests/security/test_workflow_builder_access.py` (unauthenticated, unentitled and flag-off callers refused on every route with no side effects), `test_workflow_builder_idor.py` (404 on every session-scoped route, the stream included), `test_workflow_builder_script_runner.py` (refused scripts, modes and path escapes return a reason; a child process that prints `os.environ` sees only allow-listed names; writes under `/skills/` refused), `test_workflow_builder_canvas_isolation.py` (`canvas_state` reaches the agent only as the Canvas_File), `test_workflow_builder_stream_revocation.py` (revocation closes the stream with `session_revoked`).
    - _Requirements: 2.4, 2.5, 2.7, 20.7, 34.8, 35.12, 36.4, 37.1, 40.8, 42.2, 49.7_

  - [x] 22.3 Write the sessions API integration test
    - `backend/tests/integration/api/test_workflow_builder_sessions_api.py`: create in both modes (revision 0 seed, non-custom seeding), list, get, delete, link, undo, retry and cancel on testcontainers PostgreSQL.
    - _Requirements: 2.9, 2.10, 8.5, 12.6, 20.13, 20.14, 20.15, 31.2, 49.4_

  - [x] 22.4 Write the turn flow integration test
    - `backend/tests/integration/api/test_workflow_builder_turns_api.py` with `FakeChatModel`: 202 then stream events; 409 on a second turn; a stream drop while the turn completes; a time-out with an unproposed revision under a short cap set through settings; tool rows stored mid-turn; the startup sweep and the shutdown step.
    - _Requirements: 21.3, 21.6, 21.7, 22.1, 22.2, 23.18, 24.5, 49.4_

  - [x] 22.5 Write the stream integration test
    - `backend/tests/integration/api/test_workflow_builder_stream_api.py`: snapshot first, two clients see the same events, the stream stays open between turns, `session_deleted` closes it, headers and keep-alive configuration.
    - _Requirements: 31.4, 40.1, 40.2, 40.3, 40.4, 40.5_

  - [x] 22.6 Write the gate integration test
    - `backend/tests/integration/api/test_workflow_builder_gate_api.py`: the real `_validated_manifest` on valid and invalid manifests at `user` and `db`, with the same verdict as `POST /api/user-workflows` for the same manifest.
    - _Requirements: 23.3, 48.5_

  - [x] 22.7 Write the script runner subprocess integration test
    - `backend/tests/integration/agents/workflow_builder/__init__.py` and `test_script_runner_subprocess.py`, in the repository's existing `tests/integration/agents/` folder as the design states, since none of the five canonical subfolders fits a real-subprocess test: the six real scripts against a sandbox and a skill copy under `tmp_path`, no `__pycache__` written, the scrubbed environment seen by a child, a timeout with a sleeping stub, cancel kills the process, the output cap, and `git status --porcelain` of the Skill_Folder unchanged.
    - _Requirements: 18.3, 32.11, 34.5, 35.5, 36.3, 36.5, 36.8, 49.5_

  - [x] 22.8 Generate the per-pattern fixtures
    - Create `backend/tools/ci/builder_pattern_fixtures.py` with `--write` and `--check`: build one draft manifest per allowed pattern (`patterns.md` §1 to §18 and §21) from the skill's examples and pattern text, run the skill's `export_manifest.py --save-payload` on each, and write the manifest and expected payload to `frontend/src/store/api/__fixtures__/builder-patterns/`.
    - Add `--check` to the CI step in `.github/workflows/ci.yml`.
    - _Requirements: 49.8_

  - [x] 22.9 Write the per-pattern render-and-save tests
    - `frontend/src/store/api/userWorkflows.builderPatterns.test.ts`: one test per pattern fixture; render the unedited draft through the composer mapping, build the Save payload, and compare base `custom`, `agent_ids` and the canonical manifest with the expected payload.
    - _Requirements: 10.9, 49.8_

  - [x] 22.10 Write the Playwright journey
    - `frontend/e2e/tests/ts-z4.workflow-builder.spec.ts` in the `mocked` project, with mocked REST and SSE responses in `frontend/e2e/fixtures/workflowBuilderMocks.ts`: create from `/workflows`, see progress, the draft renders, save, the URL moves to the edit route without a remount; a timed-out turn continued; the busy modal on 503; the overlay panel below 1024 px.
    - _Requirements: 3.3, 3.8, 13.8, 13.10, 49.11_

  - [x] 22.11 Write the opt-in event-delivery performance test
    - `backend/tests/performance/test_workflow_builder_event_delivery.py`: with `FakeChatModel`, each `stage`, `tool_started`, `tool_finished`, `check_result` and `limit_warning` event reaches every connected client within 1 s of publish.
    - _Requirements: 43.3_

  - [x] 22.12 Write the Spike report script
    - Create `backend/tools/builder_spike_report.py`, which reads stored builder rows for given session ids and prints per-turn duration, tokens, tool calls, gate rejections and the Adherence_Record as JSON for the operator. It calls no model; the Spike itself stays operator-run.
    - _Requirements: 46.3_

- [ ] 23. Final checkpoint: all suites
  - From `backend/`: `uv run pytest`, `uv run pytest --collect-only -q`, `uv run ruff check`, `uv run pyright`, `uv run lint-imports`, `uv run alembic heads` (exactly one head), `uv run python -m tools.ci.builder_skill_checks --selftest`, `--step-models`. Integration tests run on the Docker-capable CI runner.
  - INV-3: `Remove-Item Env:SNAPSHOT_UPDATE -ErrorAction SilentlyContinue`, `uv run pytest (Get-ChildItem tests/agents/test_characterization_*.py, tests/contract/agents/test_characterization_*.py).FullName`, then `git status --porcelain tests/agents/characterization/golden/` prints nothing.
  - From `frontend/`: `npm run test`, `npm run lint`, `npm run build`, `npm run e2e`.
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Sub-tasks marked `*` are test-only and optional. Core implementation sub-tasks are never optional.
- Every correctness property in the design has its own sub-task: backend properties 1 to 30 with hypothesis under `backend/tests/property/`, frontend properties 31 to 40 with fast-check colocated under `frontend/src/`.
- Places where the plan departs from a design path or fills a gap the design leaves:
  - Unit test files follow the one-file-per-module mirror (`tests/unit/app/agents/test_deep_agent_runner.py`, `tests/unit/agents/capabilities/test_model_catalog.py`, `tests/unit/app/api/test_capabilities.py`) instead of the design's suffixed names.
  - `TurnPort` (task 9.1) and the shared value models in `events.py` (task 8.3) keep the agent layer from importing `app.api`, which the middleware and `propose_draft` would otherwise need.
  - `check_chat_choice` (task 3.4), `get_builder_store` (task 6.4), `frontend/src/lib/builderDraft.ts` (task 20.2) and the `panelOpen` binding flag (task 20.4) are small additions that make the design testable or complete.
  - Telemetry (task 15.3) uses structured log records, because `backend/app/` has no OpenTelemetry setup, despite the design's "like the rest of the app".
  - How revision 0 fills a non-custom base's `deliverable`, `planner` and `clarify` (task 16.5) is left open by Req 20.15 and the design.
- Q-18 stays open: task 13.8 builds only `BuilderReadPort`, the placeholder tools and a placeholder port. Q-61 no longer applies: the drift check was removed on 2026-11-10. Q-59 and Q-60 are Spike inputs.
- The Spike is operator-run and not a coding task. Req 43.1, 43.4, 46.1, 46.2 and 46.4 to 46.6 are covered by the Spike itself, Req 46.7 and 46.8 apply only after its results, and Req 45.4 is a release decision. Task 22.12 only prepares a read-only report script.
- Checkpoints run single-pass commands only. Integration suites need Docker for testcontainers, so they run on the CI runner; locally they are only collected.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "3.2", "3.3", "4.1", "6.1"] },
    { "id": 1, "tasks": ["1.3", "3.1", "3.4", "4.2", "6.2", "6.4", "8.1", "8.5", "10.1", "12.1", "13.1"] },
    { "id": 2, "tasks": ["1.4", "1.8", "6.3", "6.6", "6.7", "8.3", "12.2", "13.8", "15.3", "16.8"] },
    { "id": 3, "tasks": ["1.5", "1.6", "3.7", "3.8", "6.5", "6.10", "8.2", "8.4", "8.6", "9.1", "9.4", "10.2", "10.3", "12.3", "15.1", "16.1", "16.9"] },
    { "id": 4, "tasks": ["1.7", "1.9", "3.5", "6.8", "9.2", "9.5", "10.4", "10.5", "12.4", "13.2", "13.5", "13.9", "15.2", "18.1", "18.3", "18.4", "18.14", "20.1"] },
    { "id": 5, "tasks": ["3.6", "6.9", "8.7", "9.3", "9.6", "10.6", "12.5", "12.8", "12.10", "13.3", "13.4", "13.6", "13.10", "15.10", "16.2", "18.2", "18.5", "18.6", "18.7", "18.12", "18.15", "18.16", "19.2", "20.2"] },
    { "id": 6, "tasks": ["10.7", "12.6", "12.7", "12.9", "13.7", "13.11", "15.4", "15.6", "16.3", "16.4", "16.6", "18.8", "18.9", "18.13", "18.17", "19.1", "19.3", "20.3", "20.4"] },
    { "id": 7, "tasks": ["15.5", "16.7", "18.10", "18.11", "19.4", "20.5"] },
    { "id": 8, "tasks": ["15.7", "15.8", "15.9", "15.11", "16.5", "19.5", "20.6"] },
    { "id": 9, "tasks": ["16.10", "19.6", "20.7"] },
    { "id": 10, "tasks": ["16.11", "16.12", "20.8", "22.1", "22.2", "22.3", "22.4", "22.5", "22.6", "22.7", "22.8", "22.11", "22.12"] },
    { "id": 11, "tasks": ["20.9", "22.9", "22.10"] }
  ]
}
```
