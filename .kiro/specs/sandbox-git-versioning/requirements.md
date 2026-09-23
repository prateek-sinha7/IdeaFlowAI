# Requirements Document

## Introduction

This feature delivers persistent git-versioned sandboxes, structured chain payloads, and file-based chained workflows for the Velocity run engine. The root cause of every problem addressed here is a single design choice: `RunSandbox` is currently keyed by the run's own UUID, giving each run its own isolated directory. This spec changes the key to the chain root (the original run in a revision family), so every revision in a chain shares one directory. On top of that shared directory, every sandbox becomes a real git repository — enabling per-step commits, version tags, inspectable history, and safe fan-out isolation via git worktrees. A structured `.chain/` payload is written at run completion so that chained workflows receive actual files rather than a prose summary. Both prompt injection seams are removed and replaced by file-based context, so each agent receives only its own `AGENT.md` as the system prompt and reads its context from the sandbox.

All five architecture decisions (Q1–Q5) are locked:
- **Q1**: Real git tags for the version picker (not just the existing run-family picker)
- **Q2**: The engine commits at every step boundary; no agent-callable git tool is built
- **Q3**: Chain payload contains summary + final output + a copy of the logs; folder is `.chain/`
- **Q4**: Both prompt seams removed; context becomes files; brief reaches agent 1 only
- **Q5**: `has_git` is a global default, on — every sandbox is a git repository

## Glossary

- **RunSandbox**: The on-disk directory owned by a run, currently keyed by run UUID
- **chain root**: The original (first) run in a revision family; the directory all revisions share after this spec
- **`has_git`**: Flag indicating a sandbox is a git repository; global default `True` after this spec
- **`post_run` hook**: New lifecycle event that fires exactly once on the terminal path of every run
- **`pre_commit` / `post_commit`**: New hook events that bracket the engine's step-boundary git commit
- **`.chain/{run_id}/`**: Per-run subdirectory inside a shared sandbox holding the chain payload
- **`.context/`**: New reserved prefix — what a run was given (design files, chain payload copy from source run)
- **Seam 1**: `_compose_system_prompt` — the 7-block wrapper around `AGENT.md`; removed under Q4
- **Seam 2**: `_compose_context_message` — the ~15-block human-message assembly; removed under Q4
- **`revision_index`**: The displayed `vN` number, computed from the family walk; stays the display source
- **`git_tag`**: New nullable `WorkflowRun` column meaning only "a real git tag object was created"
- **`source_run_id`**: Existing-but-dead `WorkflowRun` column; written for the first time by this spec
- **INV-1**: Kernel stays workflow-agnostic — no `pipeline_type` or `spec.id` branches in the engine
- **INV-3**: The 5 characterization goldens stay byte/event-identical
- **SC-001**: A new custom workflow replicates `prototype` via manifest + `AGENT.md` with zero engine edits

---

## Requirements

### Requirement 1: Shared sandbox — revisions run on the chain root

**User Story:** As a developer, I want every revision to write into the same directory as the original run, so that agents in a revision find all prior files without any copying and nothing is lost between revisions.

#### Acceptance Criteria

1. WHEN a revision run is dispatched, THE engine SHALL resolve the sandbox path by walking `parent_run_id` to the chain root, using a visited-set cycle guard that mirrors `_compute_root_ids` in `runs.py` (threat T-A-04).
2. THE walk SHALL follow `parent_run_id` ONLY — `source_run_id` SHALL never be followed because a chained run is its own root with its own sandbox.
3. WHEN a revision writes `PLANNER.md` or the deliverable file, THOSE files SHALL be overwritten in place — both are tracked in git and the previous run's copy survives under its version tag.
4. IF a cycle is detected in the `parent_run_id` chain, THE engine SHALL break the walk at the repeated node and use the last seen unique root.
5. ALL seven `RunSandbox` construction sites SHALL resolve to the same chain root key: `engine.py` `_execute_impl`, `engine.py` `run()` `RunTrace` (built BEFORE `_execute_impl` is entered — if missed, the run log lands in a per-revision directory nothing else writes to), `factory.py` `create_runner` (consistent only if root resolution reassigns `ctx.run_id`), and the four routes in `run_files.py` (upload, list, zip, read).
6. `kernel_services.py`'s `RunSandbox(disk_principal, parent_run_id)` reads another run's sandbox by design — after FR-001 a raw `parent_run_id` resolves to a path nothing writes to; it SHALL also root-resolve its target (see Requirement 5).
7. `LocalWorkspaceRuntime.create_workspace` is keyed on a fresh `workspace_id` UUID unrelated to any run id and is deliberately out of scope for this requirement.

---

### Requirement 2: TTL sweeper protects the whole non-terminal chain

**User Story:** As a developer, I want the TTL sweeper to never delete a shared sandbox while any run in the revision family is still active, so that a live revision is not silently deleted because its parent's row is already terminal.

#### Acceptance Criteria

1. THE sweeper's protected set SHALL be built from chain roots, not from individual run ids.
2. WHEN a parent run is terminal but a child revision is still active, THE sweeper SHALL NOT delete the shared directory.
3. THIS fix SHALL ship in the same PR as Requirement 1 — never as a follow-up.

---

### Requirement 3: Server-side concurrency guard on concurrent revisions

**User Story:** As a developer, I want the server to reject a second concurrent revision of the same parent with a clear error, so that two simultaneous revisions cannot interleave writes on one shared directory.

#### Acceptance Criteria

1. WHEN `_mint_revision_row` is called for a parent that already has an active child run, THE server SHALL reject the request with `"a revision is already in progress"`.
2. THIS guard SHALL be a server-side unique constraint or row lock evaluated at insert time.
3. THE existing LLM-prompt instruction in `concierge.py` that says "a revision is already in progress" is advisory only and SHALL NOT be treated as a concurrency guard.

---

### Requirement 4: Short-circuit redundant `previous_run` seeding

**User Story:** As a developer, I want the `previous_run` seed loop short-circuited once the sandbox is shared, so that it does not redundantly re-copy files that are already present or overwrite in-progress edits.

#### Acceptance Criteria

1. WHEN the shared sandbox already contains the files that `previous_run` would copy, THE seed loop SHALL detect their presence and skip re-copying them.
2. `.uploads/` SHALL accumulate across the whole revision family by design — a revision's `uploaded_files` provider sees the root's uploads plus its own.

---

### Requirement 5: Root-resolve every cross-run sandbox read

**User Story:** As a developer, I want every cross-run sandbox read to resolve its target to that target's own chain root first, so that reads at chain depth two or deeper do not silently return an empty path.

#### Acceptance Criteria

1. `previous_run.py` `_seed_existing_artifact` SHALL root-resolve its target id before constructing a `RunSandbox`.
2. THE chain-payload read (Requirement 22) SHALL root-resolve `source_run_id` before constructing the source `RunSandbox` — users chain from their most-refined revision, almost never the chain root itself.
3. `kernel_services.py` `read_parent_file` SHALL root-resolve its target id — a raw `parent_run_id` is wrong at chain depth two or deeper; this breaks the chain-payload read on precisely the path users take most (chaining from a non-root revision).
4. FR-025's graceful degradation SHALL cover only genuinely missing payloads — it SHALL NOT mask depth-two-or-deeper resolution failures.
5. ACCEPTANCE TEST: chaining from a mid-family revision (not the family root) SHALL produce a non-empty chain payload in the chained run. A test that only chains from the root would pass while the majority real-world case is broken.

---

### Requirement 6: git init with an initial commit at sandbox provision

**User Story:** As a developer, I want every sandbox initialised as a real git repository with at least one commit, so that git worktree operations and merges never encounter an unborn HEAD.

#### Acceptance Criteria

1. `git init` SHALL be called at sandbox provision time, idempotently — if `.git/` already exists, the call is a no-op.
2. AN initial commit SHALL be made immediately after `git init` (commit the seeded `.gitignore` or use `git commit --allow-empty`).
3. WITHOUT the initial commit, `git merge --no-ff` into an unborn HEAD fails and that failure is currently laundered into a reported clean merge — this requirement prevents that.
4. THIS is a ship-blocker prerequisite for Requirement 11 (`has_git` global default). Nothing gets `has_git=True` before this is fixed and tested.

---

### Requirement 7: Fix merge_worktree false-clean merge

**User Story:** As a developer, I want `merge_worktree` to correctly report a refused merge as a failure, so that fan-out steps never silently discard all worker output while reporting success.

#### Acceptance Criteria

1. A `CalledProcessError` from a refused merge SHALL be classified as "refused to start" — distinct from "ran and found conflicts".
2. A `CalledProcessError` with no `--diff-filter=U` output SHALL NEVER produce `conflicts: []` — "the merge refused to start" and "the merge ran and found nothing conflicting" are different outcomes.
3. `git merge --abort` SHALL only run after classifying the error, never before.
4. ACCEPTANCE TEST: two fan-out workers writing disjoint files SHALL both appear in the base tree after merge. Today neither appears.
5. THIS is a ship-blocker prerequisite — it must be fixed before any workflow gets `has_git=True`.

---

### Requirement 8: Seed `.gitignore` covering eight reserved paths

**User Story:** As a developer, I want a `.gitignore` seeded at `git init` time covering all reserved prefixes, so that `git add -A` never commits uploaded documents, engine traces, agent transcripts, or chain and context directories into permanent git history.

#### Acceptance Criteria

1. THE `.gitignore` SHALL cover exactly these eight paths: `.uploads/`, `.logs/`, `.verify/`, `.browser/`, `.agents/`, `.chain/`, `.context/`, and `skills/`.
2. `.chain/` MUST be included — without it the next revision's `git add -A` would sweep the previous revision's chain payload into permanent history.
3. `skills/` MUST be included — `stage_skills` prunes and rewrites this directory on every invocation and it accumulates history if unignored.
4. THE `.gitignore` SHALL be seeded inside the same `git init` call — never in a separate step.

---

### Requirement 9: Exclude `.git/`, `.gitignore`, and `skills/` from deliverable walk and file listing

**User Story:** As a developer, I want git internals and implementation artifacts excluded from both the deliverable walk and the Workspace file listing, so that they never appear in the Files tab, the deliverable zip, or `WorkflowRun.output`.

#### Acceptance Criteria

1. `.git/` SHALL be excluded from `serialize_sandbox_deliverable`, `count_sandbox_deliverables`, and `list_files`.
2. `.gitignore` (bare filename) SHALL be excluded from the deliverable walk and `list_files`.
3. `skills/` SHALL be excluded from the deliverable walk and `list_files` — this closes a pre-existing gap where staged skill bodies ship inside user deliverables.
4. The deliverable walk and `list_files` are two separate lists — excluding from one does NOT exclude from the other.

---

### Requirement 10: Engine commits at the step boundary, gated on `has_git`

**User Story:** As a developer, I want the engine to commit after every step completes, so that every unit of work is captured in git history without requiring any agent or manifest to declare it.

#### Acceptance Criteria

1. THE engine SHALL stage and commit after each step strategy returns, gated on `has_git`.
2. THE commit SHALL NOT ride `post_step` — that field is `str | None` (singular) and is already taken on four shipped manifests (`app_builder: api_prefix_audit`, all three prototype revision workflows: `revision_validation`).
3. A routing step SHALL commit before the routing decision consumes the gate outcome — so backward retry jumps also produce a commit.
4. `Step.hooks` (a list) is the correct seam — hooks compose with whatever else a step declares; `post_step` stays free for its existing occupants.
5. WHEN `has_git` is true but a commit returns empty, THE engine SHALL log a warning distinguishing "not a git repo" from "nothing to commit" — today these are indistinguishable.

---

### Requirement 11: `has_git` is on by default for every sandbox

**User Story:** As a developer, I want every sandbox to be a git repository from day one, so that no per-workflow opt-in is needed and versioning is uniformly available.

#### Acceptance Criteria

1. `has_git` SHALL default to `True` for every `RunSandbox`.
2. `_select_isolation_scope` in `fanout.py` derives worktree-vs-`sub_sandbox` solely from `has_git` — turning this on globally reroutes every fan-out step onto git worktrees and `git_3way` merge.
3. `sub_sandbox` isolation and `copy_disjoint` merge SHALL become dormant, not deleted — they remain the path for a sandbox where `git init` failed.
4. Requirement 7 (merge_worktree fix) MUST be fixed and tested before this ships — there is no manifest flag left to stage behind.

---

### Requirement 12: `pre_commit` and `post_commit` hook events bracket the step commit

**User Story:** As a developer, I want declared hooks to be able to observe or block each step commit, so that secret scanning can intercept commits before they become permanent in git history.

#### Acceptance Criteria

1. `pre_commit` SHALL fire over the staged diff before `git commit` — a declared hook MAY block it.
2. `post_commit` SHALL fire after the commit lands — observation only, no block possible.
3. BOTH follow the existing `_fire_hooks` contract: declaration-driven from `step.hooks`, bound only when the step's effective permissions grant the `git` permission.
4. A blocked commit SHALL follow `before_write`'s semantics: the commit is skipped, the step continues, the diff stays in the working tree.
5. A run whose last commit was blocked SHALL end `degraded`, not `completed`, and SHALL NOT be tagged.
6. `secret_scan.py` already declares itself bound to `pre_commit` — that binding SHALL be wired to the engine's commit boundary. Today `pre_commit` fires nowhere.

---

### Requirement 13: `post_run` hook event fires once on the terminal path

**User Story:** As a developer, I want a single `post_run` hook event that fires exactly once when a run ends, so that tag creation, chain payload writing, and git gc all have one principled declared home.

#### Acceptance Criteria

1. `post_run` SHALL fire from one fire-once finalizer — not from each of the eight or more terminal early-return sites in `_execute_impl`.
2. THE finalizer SHALL be called from the existing `finally` blocks of `_execute_impl` and `run()` — a second call is a no-op.
3. `post_run` SHALL fire for all terminal statuses: `completed`, `cancelled`, `failed`, `degraded`, and `diverted`.
4. Tag creation, `git gc`, and `.chain/` writing SHALL all move onto this event — removing them from bespoke inline calls.

---

### Requirement 14: Version tag created on the terminal path

**User Story:** As a developer, I want the version tag created at run completion on the terminal path, so that tags exist only for runs that actually finished and the final status is known before tagging.

#### Acceptance Criteria

1. THE tag SHALL be created on the terminal path via the `post_run` event, after the final status is known.
2. THE tag SHALL NOT be created on a leaf `post_step` — a workflow has many leaves; reaching a leaf does not always end the run; and a `post_step` cannot see the run's final status.
3. Tags SHALL be created ONLY when the terminal status is `completed`.
4. `diverted`, `cancelled`, `failed`, and `degraded` runs SHALL receive no tag. `diverted` is called out explicitly because it is easy to read as success.
5. THE tag name SHALL be `v{revision_ordinal}` — an ordinal threaded onto `ExecutionContext` at launch so the tag and the UI version number can never disagree.

---

### Requirement 15: `create_tag` and `list_tags` added to `LocalWorkspace` via duck-typing

**User Story:** As a developer, I want tag methods on `LocalWorkspace` reachable by `getattr` duck-typing, so that the `Workspace` Protocol port stays shut and import-linter contracts are not broken.

#### Acceptance Criteria

1. `create_tag` and `list_tags` SHALL be added to `LocalWorkspace` and reached by `getattr` duck-typing — the same pattern as `commit_all` and `allocate_worktree`.
2. They SHALL NOT be added to the `Workspace` Protocol — three import-linter contracts hold that port shut for the ECS swap.

---

### Requirement 16: Ref values validated against `list_tags()` before reaching any subprocess

**User Story:** As a developer, I want every ref value validated against the sandbox's own tag list before it touches a git subprocess, so that user-controlled strings cannot inject subprocess arguments.

#### Acceptance Criteria

1. A `ref` query parameter SHALL be validated by exact match against `list_tags()` output before reaching any `git` subprocess call.
2. A free-form revspec from user input SHALL NEVER be passed directly to a git subprocess.

---

### Requirement 17: Ref-scoped workspace browsing on real git tags

**User Story:** As a user, I want the Workspace version dropdown to list real git tags and show me the exact files at each version, so that I can inspect any past version of my work.

#### Acceptance Criteria

1. `run_files.py`'s three read routes SHALL accept an optional `ref` query parameter; a new `GET /{run_id}/sandbox/refs` endpoint SHALL list the sandbox's tags.
2. File listing SHALL use `git ls-tree -r <ref>`, single-file reads SHALL use `git show <ref>:<path>`, and zip downloads SHALL use an in-memory `git archive <ref>`.
3. HEAD SHALL NEVER move — browsing a version reads history without touching the working tree.
4. Omitting `ref` SHALL be byte-identical to today's behaviour — `test_sandbox_deliverable.py` pins this.
5. `SandboxTab.tsx` SHALL gain `selectedRef` state and a tag picker.
6. `frontend/src/lib/api.ts` SHALL add an optional `ref` param on the four sandbox functions and a new `getRunSandboxRefs` function.

---

### Requirement 18: Version browsing read-only and restore as a forward commit

**User Story:** As a user, I want to browse any past version safely while a run is in progress, and to restore a version as a new commit on top so that history is never rewritten.

#### Acceptance Criteria

1. ALL version reads SHALL go through `git show <ref>:<path>` — never `git checkout` into the live working tree.
2. A restore SHALL materialise the old tree as a new commit on top (`git read-tree` + commit or a revert range).
3. v2 and v3 SHALL remain in history and remain browsable after a restore to v1.
4. `reset --hard`, history rewrites, and branch moves SHALL NEVER be used for restore.
5. THE restore action SHALL be refused while any non-terminal run whose resolved chain root is this sandbox is active.
6. A restore is a commit, not a tag — the next completed run tags the restored tree as its own version.

---

### Requirement 19: Existing version picker regression window closed

**User Story:** As a developer, I want the existing shipped "Version ▾" picker to either work correctly or show a clear notice during the transition, so that it never silently shows wrong content.

#### Acceptance Criteria

1. IN Phase 3 (sandbox re-key), THE picker SHALL show the current accumulated tree with an explicit notice ("Older versions available once this run is tagged") rather than pretending to switch versions.
2. IN Phase 6 (tag UI), THE picker SHALL restore real per-version browsing using ref-scoped reads on tags.
3. THE per-member zip download SHALL receive the same Phase 3 notice and Phase 6 restoration.

---

### Requirement 20: `.chain/` payload written on `post_run` for every terminal status

**User Story:** As a developer, I want every completed run to leave a structured chain payload directory, so that a chained workflow can find exactly what its source run produced.

#### Acceptance Criteria

1. `.chain/{run_id}/` SHALL be written per run — one subdirectory per run, not a flat `.chain/`.
2. THE payload SHALL contain: `summary.md` (engine-rendered from `ectx`, not agent prose), the run's final output copied under its own deliverable filename, and `logs/` holding a copy of `.logs/{run_id}.jsonl` and the `.agents/` transcripts.
3. THE payload SHALL be written for every terminal status — a cancelled or failed run can be deliberately chained from.
4. THE writer SHALL be best-effort, never-raising — the same contract as `write_agent_output`.
5. `.chain/` SHALL be listed in the Workspace tab, excluded from the deliverable walk, and readable via the single-file read endpoint.
6. THE engine writes `.chain/` — no agent tool writes to a reserved prefix.

---

### Requirement 21: Reserved-prefix guard in `previous_run.py`

**User Story:** As a developer, I want a defensive guard that rejects any `seed_files.from_run` entry naming a reserved prefix, so that future manifest authors cannot accidentally seed reserved content.

#### Acceptance Criteria

1. `previous_run.py` SHALL reject any `seed_files.from_run` entry that names a reserved prefix: `.chain/`, `.context/`, `.uploads/`, `.logs/`, `.verify/`, `.browser/`, `.agents/`, or `skills/`.

---

### Requirement 22: File-based chaining — `.chain/` copied into receiving sandbox

**User Story:** As a developer, I want a chained workflow to receive the source run's actual files in its sandbox, so that it can read what the source run produced rather than receiving a prose summary.

#### Acceptance Criteria

1. `WorkflowRun.source_run_id` SHALL be written when launching a chained run — this column has existed since migration 0014 and has never been assigned.
2. Writing `source_run_id` SHALL make the frontend "(Chained)" lineage indicator functional for the first time — this is the only writer the column has ever had.
3. THE copy SHALL be gated on a declared manifest flag — never on the mere presence of `source_run_id`.
4. `source_run_id` SHALL be threaded as its own `ExecutionContext` field (`chain_source_run_id`) and SHALL NOT alias into `parent_run_id`.
5. `assert_owns` SHALL be called before any cross-run read, fail-closed, `PermissionError` never swallowed.
6. THE copy SHALL root-resolve `source_run_id` first — users chain from their most-refined revision, not the original.
7. Source path: `<chain_root>/.chain/{source_run_id}/`. Destination: receiving sandbox's `.context/`.
8. A missing, swept, or inaccessible source SHALL degrade gracefully to an empty chain payload — the chained run SHALL NEVER fail because its source is unavailable.
9. THE receiving pipeline SHALL learn about the chain payload through the declared context-provider mechanism (`chain_context` provider), not a new bespoke channel — reusing the existing block-marker convention.
10. THE frontend's `enrichedInput` text-block assembly SHALL be retired or gated so that agent B does not receive the same chain context twice in two formats.
11. ACCEPTANCE TEST: a chained run SHALL render the "(Chained)" lineage indicator.
12. ACCEPTANCE TEST: chaining from a mid-family revision (not the family root) SHALL produce a non-empty chain payload. A root-only test would pass while the majority case is broken.

---

### Requirement 23: `.context/` prefix written at sandbox open before step 1

**User Story:** As a developer, I want a `.context/` directory written before the first step containing everything the run was given, so that Seam 1 no longer needs to paste template and design files into the system prompt.

#### Acceptance Criteria

1. `.context/` SHALL be written by the engine when the sandbox opens, before step 1.
2. OpenDesign material SHALL be written under `.context/design/`: `design-system.md`, `craft.md`, and `template/` holding `SKILL.md`, `example.html`, and the seed and reference files.
3. `selections.json` (wizard choices) SHALL sit at the `.context/` root.
4. For a chained run, the source's `.chain/{run_id}/` SHALL be copied into `.context/` so `.context/` is the single place an agent looks for its inputs.
5. `.context/` SHALL be gitignored, excluded from the deliverable walk, and listed in the Workspace tab.
6. `resume_run` SHALL rebuild `ectx.od_context` from `.context/selections.json` and `.context/design/` instead of `od_context_json` — this happens in the same change as Seam 1 removal.

---

### Requirement 24: Per-run names for logs, validator evidence, and browser artifacts

**User Story:** As a developer, I want the run log and evidence directories scoped per run id, so that a shared sandbox does not merge multiple runs' data into one unattributable file.

#### Acceptance Criteria

1. `RunLog` SHALL write `.logs/{run_id}.jsonl` instead of a fixed `.logs/run-logs.jsonl`.
2. Validator evidence SHALL be written to `.verify/{run_id}/` instead of a flat `.verify/`.
3. Browser artifacts SHALL be written to `.browser/{run_id}/` instead of a flat `.browser/`.
4. ALL writers SHALL take the run-scoped path from one helper on `RunSandbox`.
5. `.agents/` stays flat by design — agent transcripts are gitignored debug artifacts.

---

### Requirement 25: Fan-out merge sequence is ordered and explicit

**User Story:** As a developer, I want the fan-out and wave merge sequence formally ordered, so that each worker's contribution is attributable, `MERGE_HEAD` is always cleared between fragments, and conflicts are correctly detected.

#### Acceptance Criteria

1. THE sequence SHALL be: (a) `spawn_point_commit` captures the base HEAD; (b) each worker commits on its own `fanout/{step}/{i}` branch; (c) fragments merge into the base one at a time with a base commit between each; (d) the engine's step-boundary commit runs last.
2. Merge commits SHALL be real and stay in history — they are not squashed or soft-reset.
3. Waves need no separate mechanism — `wave_scheduler` delegates to the unmodified `run_fanout`, so this sequence covers waves automatically.
4. ALL four `on_conflict` policies (`human_gate`, `merge_agent`, `partial`, `abort`) SHALL be exercised by test before ship — they have never been reachable in production because conflicts were never detected.

---

### Requirement 26: Cancelled and failed runs commit work in progress — never reset

**User Story:** As a user, I want a cancelled or failed run to commit its in-progress work rather than discard it, so that work is never lost and the next revision starts from a known clean state.

#### Acceptance Criteria

1. WHEN a run is cancelled, failed, or degraded mid-step, THE engine SHALL commit the dirty tree on the terminal path with a `wip: cancelled at step {id}` marker.
2. THE engine SHALL NEVER run `git reset --hard` or `git checkout` into the working tree.
3. A WIP commit SHALL NEVER be tagged and SHALL NEVER become a version.
4. THE next revision starts from a clean tree — the abandoned work is in history and attributable.

---

### Requirement 27: Dirty-tree reconciliation on resume and shared-root open

**User Story:** As a developer, I want the engine to commit any dirty tree before re-running an interrupted step, so that crash leftovers are attributed and never silently folded into the re-run's commit.

#### Acceptance Criteria

1. WHEN `restore_non_terminal_runs()` resumes an interrupted run, THE engine SHALL check `git status --porcelain` before re-running the step.
2. IF the tree is non-empty (dirty), THE engine SHALL commit it as `wip: recovered dirty tree at step {id}`.
3. THE re-run step's own commit SHALL contain none of the crash leftovers.

---

### Requirement 28: Cancelled fan-out retains worker branches

**User Story:** As a developer, I want worker branches preserved when a fan-out is cancelled, so that completed worker work is never permanently lost.

#### Acceptance Criteria

1. `remove_worktree` SHALL gain a `delete_branch: bool = True` parameter.
2. THE cancel path SHALL pass `delete_branch=False` — worker branches (`fanout/{step}/{i}`) are retained.
3. Worker branches SHALL NOT appear in the version picker (which lists tags only) but SHALL be visible to `git branch`.

---

### Requirement 29: Two prompt policy orders registered — body-only and governance

**User Story:** As a developer, I want a body-only prompt policy that makes the system prompt exactly the agent's `AGENT.md`, while governed agents keep their Constitution and behavioral hooks.

#### Acceptance Criteria

1. A body-only policy order SHALL be registered: `("prompt_body",)`.
2. A governance policy order SHALL also be registered: `("guardrails", "hooks", "constitution", "prompt_body")`.
3. The body-only order drops SIX blocks — `tool_availability`, `injects`, `guardrails`, `skills`, `hooks`, `constitution` — losing the Constitution as a side effect of a formatting change is NOT acceptable.
4. `factory.py` SHALL read the policy name from the manifest instead of hardcoding `"default"`.
5. THE compiler SHALL warn when a governed agent (one with a Constitution or behavioral hooks) selects the bare body-only order.

---

### Requirement 30: Both prompt seams removed per staged per-workflow migration

**User Story:** As a developer, I want both prompt injection seams removed workflow by workflow as each is migrated, with a 27-row inventory as the authoritative record of where each injected input now lives on disk.

#### Acceptance Criteria

1. EACH of the 30 input rows in the FR-030 inventory table SHALL have a named destination — no blank rows. The table covers rows 1–27 (the seam inputs) plus rows 28–30 (the three model-call paths outside the seams: the validation fix loop, the deep planner's `design_context`, and the engine-side `ectx.od_context` readers that a resumed run must rebuild from `.context/`).
2. ACCEPTANCE TEST: after step 1 of a migrated `prototype` run, every file the inventory table names for that workflow SHALL exist on disk — asserted by test.
2. REMOVAL SHALL be staged per workflow — each built-in moves when its `AGENT.md` files have been rewritten.
3. Seam 2's code SHALL be deleted ONLY once the last workflow is off the `default` policy.
4. `PLANNER.md` SHALL be written AFTER the clarify rounds merge (engine.py `:2339`) — today the write is at `:2221`, before the merge, so agents read a plan without the clarification answers.
5. The user's brief reaches agent 1 only — every later agent's message carries the step's own task and nothing else.
6. The retry block (`=== RETRY — pass N of M ===`) SHALL be injected into the retrying agent only, never broadcast to all agents.

---

### Requirement 31: Every `AGENT.md` in a migrated workflow states where to look and how

**User Story:** As a developer, I want every migrated agent's prompt to explicitly name which sandbox paths hold what, so that removing injection does not leave agents with no way to find their context.

#### Acceptance Criteria

1. EACH migrated `AGENT.md` SHALL state which paths hold what (`.agents/`, `.uploads/`, `.context/`, sandbox root files), that `.agents/` is ordered by step number, and that reading is the agent's own responsibility.
2. A prompt that merely says "read the files" is NOT sufficient.
3. THE first step of every migrated workflow SHALL write a durable artifact — today a first agent that streams prose and writes no file still works because the engine re-injects the brief downstream. After this migration, a workflow whose first step produces nothing readable leaves every later agent with no contract at all. This change makes the first step **load-bearing** in a way it was not before.
4. ACCEPTANCE TEST: in a migrated workflow, the first step SHALL write a durable artifact, and agent 2 SHALL derive its whole contract from that artifact without ever seeing the user's original request.
4. EVERY built-in workflow SHALL be migrated — cheapest first, `prototype` last (SC-001 anchor).

---

### Requirement 32: `WorkflowRun.git_tag` nullable column and `source_run_id` populated

**User Story:** As a developer, I want one additive database migration adding `git_tag` and the existing `source_run_id` column populated, so that the schema supports versioning and chain lineage without breaking existing data.

#### Acceptance Criteria

1. `WorkflowRun.git_tag` SHALL be a nullable string column added by one additive Alembic migration.
2. `WorkflowRun.source_run_id` already exists (migration 0014) — NO new migration is needed; code SHALL begin writing it.
3. Existing rows are unaffected — all new columns are nullable.
4. `root_run_id` is an optional optimisation — one additive nullable column only if the parent-chain walk is measured to be slow.
5. The displayed `vN` version number SHALL stay driven by `revision_index` (the family walk ordinal). `git_tag` means only "a real tag object was created" — it decouples the display counter from the git operation.
6. `frontend/src/types/index.ts` `FamilyMember` SHALL gain an optional `git_tag` field.
7. `RunDetailPage.tsx` and `RevisionFamilyView.tsx` SHALL show a "tagged" badge beside the existing `v{revision_index}` chip when `git_tag` is present.

---

### Requirement 33: Stale-file reconciliation is declarative and opt-in per step

**User Story:** As a developer, I want steps that own a complete output surface to be able to remove files they no longer produce, so that renamed or restructured files do not accumulate forever in the shared sandbox.

#### Acceptance Criteria

1. A step MAY declare `outputs: [...]` (the surface it owns) and `replaces: true` (it owns that surface completely).
2. WHEN a step declares `replaces: true`, THE engine SHALL stage a removal for every tracked path under the declared surface that the step did not write this pass — determined from `changed_since(spawn_point)`.
3. WHEN a step declares nothing, nothing is removed — safe default, accumulate as today.
4. A `delete_file` agent tool SHALL NOT be added.

---

### Requirement 34: SC-001 and INV-1 kernel invariants preserved throughout

**User Story:** As a developer, I want all engine changes to remain workflow-agnostic, so that the kernel never branches on a workflow name or agent id.

#### Acceptance Criteria

1. THE engine kernel SHALL NOT contain any literal check on workflow names or agent ids to gate any behaviour introduced by this spec.
2. EVERY gate SHALL be a generic `ExecutionContext` field or a declared manifest flag.
3. `grep -rn "if pipeline_type ==" backend/agents/execution_engine/` SHALL return 0 matches after implementation.
4. `grep -rn 'spec\.id ==' backend/agents/execution_engine/` SHALL return 0 matches after implementation.
5. `_extract_chain_context`'s seven hardcoded `pipeline_type` branches in `runs.py` SHALL NOT be extended — the chain-payload mechanism is the declarative replacement.

---

### Requirement 35: Git housekeeping instrumented before any quota is imposed

**User Story:** As a developer, I want disk growth instrumented per run so that a retention policy can be set against real data, because three compounding multipliers make unbounded growth a real risk.

#### Acceptance Criteria

1. `git gc --auto` SHALL run on the `post_run` event to bound loose-object count.
2. THE engine SHALL record per terminal run: sandbox on-disk size, `.git` directory size, and chain depth.
3. NO quota or size cap is imposed by this spec — the spec deliberately ships unbounded and accepts the risk.
4. Trigger to revisit: the first sandbox over a threshold revealed by instrumentation, or the first disk-pressure incident.

---

### Requirement 36: Agent input-prompt viewer repointed at system prompt

**User Story:** As a developer, I want the agent input-prompt viewer kept useful after Seam 2 is removed, so that the transparency panel still shows meaningful content.

#### Acceptance Criteria

1. `AgentThinkingTab.tsx` and `AgentDetailPanel.tsx` render `inputPrompt` from the SSE `agent_input` event's `context_message` — after Q4 that message is just the agent's own task.
2. THE panel SHALL be repointed at the system prompt plus the targeted retry payload when one exists.

---

### Requirement 37: Per-user prompt-override migration deferred

**User Story:** As a developer, I want the prompt-override migration deferred until production users exist, with a trigger clearly stated.

#### Acceptance Criteria

1. An override replaces `prompt_body` wholesale — a saved `PROMPT_OVERRIDE.md` would shadow the Phase 7 rewrite.
2. THIS is DEFERRED — no production users have saved overrides yet.
3. TRIGGER to revisit: the first production user saves an override, or GA — whichever comes first.
4. The prompt API docstring SHALL be corrected regardless — it falsely claims the override is "injected ahead of" the base body.

---

### Requirement 38: Budget accounting across a chain deferred

**User Story:** As a developer, I want per-run budget accounting unchanged, with a clear trigger to revisit family-level caps.

#### Acceptance Criteria

1. Every run (root, revision, or chained) SHALL keep its own budget as today.
2. A chained or revised run SHALL NEVER fail because an ancestor spent its budget.
3. TRIGGER to revisit: the first request for a family-level cap.

---

### Requirement 39: Tier gating of git history and chaining deferred

**User Story:** As a developer, I want git history and chaining available to all tiers by default, with a trigger clearly stated for when gating is needed.

#### Acceptance Criteria

1. `has_git` is global — no entitlement is consulted.
2. Chaining is available wherever a workflow declares the chain flag.
3. TRIGGER to revisit: the first tier that should not get git history or chaining.
4. When revisited, the gate SHALL be one more flag in the existing entitlement table, read at launch — never inside the kernel.

---

### Requirement 40: Agent-to-agent context is files, not pasted blocks

**User Story:** As a developer, I want downstream agents to read their upstream context from `.agents/` files rather than from pasted blocks in the message, so that the context channel is durable and inspectable.

#### Acceptance Criteria

1. `write_agent_output` already persists every agent's streamed text to `.agents/{NN}-{agent_id}.md` on the completion path — this file BECOMES the agent-to-agent channel, unchanged.
2. NO new tool SHALL be added — every agent already holds `read_file`, `ls`, `glob`, `grep` through the `read_files` grant.
3. `permission_caps.py` SHALL be untouched for agent-to-agent file reads.
4. ACCEPTANCE TEST: in a migrated workflow, agent 2 SHALL reach agent 1's output by reading `.agents/01-{agent_id}.md`, and the run SHALL still produce its deliverable — the acceptance test for this requirement is that removing the seam injection did not remove the information.

---

### Requirement 41: Single committer of the base tree; commit only at step boundaries

**User Story:** As a developer, I want exactly one entity — the engine — to commit the base tree, and only at step boundaries, so that concurrent commits and in-flight merges never interleave on the shared sandbox.

#### Acceptance Criteria

1. ONLY the engine SHALL commit the base tree — workers commit on their own branches; the base is committed after the step's strategy has fully returned.
2. FOR a fan-out step, "fully returned" means after every fragment has merged — the boundary commit runs after all merge commits are complete.
3. A commit SHALL NEVER be attempted on the base while a merge is in flight (`MERGE_HEAD` set) — `git` refuses to merge with `MERGE_HEAD` set, and `commit_all` currently swallows the resulting error as "nothing to commit."
4. ONE committer does not mean one commit: a fan-out step carries one merge commit per fragment between the spawn point and the boundary commit — those merge commits are real, stay in history, and clear `MERGE_HEAD` for the next fragment.
5. ACCEPTANCE TEST: `git log` in a completed sandbox SHALL show one boundary commit per step, plus one merge commit per fragment for fan-out steps.
6. ACCEPTANCE TEST: `git show --stat HEAD` SHALL contain no reserved-prefix path after a completed run.

---

### Requirement 42: Q2 engine-driven commits — no agent-callable git tool

**User Story:** As a developer, I want it explicitly stated that no agent-callable git tool is built, so that the commit mechanism cannot be accidentally re-implemented at the agent level.

#### Acceptance Criteria

1. NO agent-callable git tool SHALL be added to `permission_caps.py` or the capability registry.
2. THE `git` permission in `permission_caps.py` SHALL remain `False` in both trust caps until a declared hook requires it — then it is set in the same PR as that hook.
3. THE engine's own commit (FR-009) bypasses the permission cap — it is an engine call, not a capability call.

---

### Requirement 43: Workspace, Files, and Preview tabs render the shared directory for all revisions

**User Story:** As a user, I want the Workspace, Files, and Preview tabs to correctly show accumulated files for both the original run and any revision, so that the shared sandbox is visible through every surface.

#### Acceptance Criteria

1. AFTER FR-001 and FR-002 land, the Workspace tab SHALL render the shared chain-root directory for any run in the revision family — not an empty directory keyed by the individual run id.
2. THE Files tab and Preview tab SHALL render the same shared directory for both the original run and its revisions.
3. ACCEPTANCE TEST: a revision's Workspace, Files, and Preview tabs all render the same directory as the original run.

---

### Requirement 44: `git log` shape and reserved-prefix exclusion verified by test

**User Story:** As a developer, I want the git commit history shape and the gitignore coverage verified by test, so that reserved paths never accumulate in permanent git history.

#### Acceptance Criteria

1. `git log` in a completed sandbox SHALL show one boundary commit per step, plus one merge commit per fragment for fan-out steps.
2. `git show --stat HEAD` SHALL contain none of the eight gitignored paths after any completed run.
3. THE sandbox listing SHALL contain neither `.git/` nor `.gitignore` after any completed run.
4. ACCEPTANCE TEST: both of the above SHALL be asserted by automated test.

---

### Requirement 45: Per-workflow characterization golden re-baselining is deliberate and reviewer-blessed

**User Story:** As a developer, I want each workflow's characterization golden re-baselined deliberately when it migrates to the new prompt policy, so that every re-baseline is a known, blessed behaviour change — not an accidental drift.

#### Acceptance Criteria

1. WHEN a workflow migrates to the new prompt policy, its characterization golden SHALL be re-derived deliberately with `SNAPSHOT_UPDATE=1`.
2. A re-baseline SHALL be reviewed by someone who understands it represents a real prompt behaviour change, not a mechanical update.
3. THE 5 non-revision characterization goldens SHALL remain byte/event-identical throughout all phases — `git status --porcelain tests/agents/characterization/golden/` SHALL show only intentionally re-baselined files after any change.
4. THE failure mode being prevented: the mechanism landing with nobody opting in would change zero agents' prompts while every test stays green. Per-workflow migration with explicit re-baselining prevents this.

---

### Requirement 46: Phase ordering and prerequisite constraints

**User Story:** As a developer, I want the implementation order and prerequisite constraints explicitly stated, so that ship-blockers are not skipped and dependent phases are not started before their dependencies are complete.

#### Acceptance Criteria

1. THE prerequisite phase (FR-034 fix + FR-006 initial commit) SHALL land before any sandbox is given `has_git=True` — this is a hard ship-blocker with no per-workflow flag to stage behind.
2. Phase 1 (`.chain/` payload) depends on nothing and may run in parallel with the prerequisite.
3. Phase 2 (git foundation) SHALL NOT begin until the prerequisite is complete and tested.
4. Phase 3 (sandbox reuse) SHALL include the TTL sweep fix (Requirement 2) and the concurrency guard (Requirement 3) in the same PR — never as follow-ups.
5. Phase 4 (tagging) depends on Phases 2 and 3 completing first.
6. Phase 5 (chaining) depends on Phase 1 and Phase 3 completing first.
7. Phase 6 (prompt policy + UI) includes `resume_run` / `od_context_json` migration (Requirement 23 AC 6) in the same change as Seam 1 removal — never separately.
8. Phase 7 (file-based context) deletes Seam 2's code ONLY when the last workflow is off the `default` policy — not before.
9. `prototype` workflow SHALL be migrated last in Phase 7 — it is the SC-001 anchor.
