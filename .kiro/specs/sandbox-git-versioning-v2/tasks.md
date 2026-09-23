# Implementation Plan: Sandbox Git Versioning V2

## Overview

Implementation follows the rollout order in the design's "Rollout" section, which
is derived from Requirement 17 AC 1-2. Task 3 is atomic and cannot be split: the
revision-root re-key must land together with sweeper protection **and** the family
lock, because the window between re-keying the sandbox and serializing access to it
is exactly the shared-mutable-state defect v2 exists to close.

Where v2 conflicts with v1, v2 wins (Requirement 1 AC 1). A v1 checkbox is not
verification evidence — every task below needs a passing behavioural test or direct
runtime observation (Requirement 1 AC 3). The design's component map is normative
(Requirement 1 AC 5): a required change outside it updates the map first.

Implementation language: **Python** (backend) + **TypeScript** (frontend)

---

## Tasks

- [x] 1. Baseline and pre-flight
  - [x] 1.1 Capture the current-behaviour baseline before any change
    - Run the full backend suite and record the passing set; this is the regression floor
    - Run `pytest tests/agents/test_characterization_*.py` with `SNAPSHOT_UPDATE` **unset** and confirm green (INV-3)
    - Run `git status --porcelain tests/agents/characterization/golden/` and confirm empty
    - Run `ruff check`, `pyright`, and `lint-imports` and record the clean state
    - _Requirements: 16, 17_
  - [x] 1.2 Verify the Alembic chain has exactly one head
    - `cd backend && alembic heads` must print exactly ONE head
    - Confirm the head is **0041** (`0041_add_git_tag_to_workflow_run.py`), not 0037
    - Two heads make `alembic upgrade head` fail under `set -eu` in `docker-entrypoint.sh` and crash-loop the container
    - _Requirements: 15_
  - [x] 1.3 Correct the stale Alembic head in `.kiro/steering/project-index.md`
    - The file states head 0037; the actual head is 0041. It is auto-loaded into every session, so the drift misleads every future change
    - _Requirements: 1_
  - [x] 1.4 Record the five Overview defects as failing or characterizing tests before fixing them
    - D1 `_find_chain_root` walks `source_run_id`; D2 root-id log path collides across revisions; D3 `_fire_post_run` runs before Step 5; D4 `.chain/` is gitignored and in no commit; D5 `pre_commit` fires with `payload=""` so the scan cannot block
    - Each needs a test that fails now and passes after its owning task, so the fix is proven by behaviour rather than by reading the diff
    - _Requirements: 1, 17_
  - [x] 1.5 Pin the scope boundary — what this spec does NOT build
    - **Out of scope, do not implement:** diff/blame/merge UI, branch management, arbitrary revspec input, agent-callable Git tooling, cross-owner version access, automated retention jobs, a history command beyond restore, and production override migration
    - **Explicit no-change surfaces** (the map names them so nobody "improves" them): `WorkflowRun.git_tag` (`workflow.py:150`, migration 0041) stays the visible completed-version mapping; `WorkflowRun.source_run_id` (:76, migration 0014) keeps its shape, written at creation only, never mutated, never aliased into `parent_run_id`; `lib/runInput.ts` `parseRunInput` `chainRe` (:61); `local.py` `read_file_at_ref`/`list_files_at_ref`/`archive_at_ref` (:721/742/764); `local.py` `create_tag`/`list_tags` (:686/703); `merge_worktree`'s `MERGE_HEAD` classification (:896); `plan.py` `Step.outputs`/`Step.replaces`; `kernel_services.py` `write_merge_conflict_artifact` (:924-964); `skill_staging.py`; deepagents' `SKILLS_SYSTEM_PROMPT`; `gate_events`, `artifact_refs`; `/ws/handoff`
    - **Retained v1 obligations** stay mandatory — a v1 Retain row is not superseded by v2's silence on it
    - `_extract_chain_context`'s seven hardcoded `pipeline_type` branches are frozen: not extended, not called by new code
    - No new method on the `Workspace` Protocol in `agents/runtime/base.py`; no `has_git` column; no tag cache; no column for the internal run ref
    - _Requirements: 16, 1, 15_

- [x] 2. Reserved-path registry (single source of truth)
  - [x] 2.1 Add `RESERVED_PATHS` to `backend/app/agents/sandbox.py`
    - One canonical set: today's nine prefixes plus `.chain-legacy/`
    - Define `AGENT_READABLE_RESERVED = {".context/"}` — `.chain/` is **not** in it
    - Define `GIT_METADATA_PATHS = {".git/", ".gitignore"}` — excluded from listing, deliverable, deliverable counting, zip, and share, but **not** a "reserved subtree" in the registry sense. Requirement 18 AC 3 restates this from v1 Requirement 9; without the constant each enforcement point keeps inventing its own `.git*` literal
    - Define `payload_allowlist(output_basename)` returning the three exact normalized paths (`.chain/logs.jsonl`, `.chain/summary.md`, `.chain/{output_basename}`) — it lives in the registry block because it is the *only* exception to the registry, and task 4.4 (wave 8) needs it before the payload builder in 5.2 exists
    - Adding a reserved path must be a single edit
    - _Requirements: 18, 4_
  - [x] 2.2 Derive every enforcement point from the registry
    - `sandbox.py`: `is_deliverable_relpath` (:745), `serialize_sandbox_deliverable` (:821), `count_sandbox_deliverables` (:889), `list_files` (:344-358)
    - `local.py` `_GITIGNORE_PATHS` (:620-630) — the only list containing `conversation_history/`, which is the proof of drift; add `.chain-legacy/`; seeding stays inside `git_init_sandbox` before the initial commit
    - `run_files.py::read_sandbox_file` single-file read guard (:864-867) — two literals today (`.uploads/` and a raw `".logs/"`); derive both from the registry and add `.chain-legacy/`
    - `run_files.py::download_sandbox_zip` (:720) — the **non-ref** branch derives its entry set from the registry instead of `list_files`' independent literals. The **ref** branch stays `git archive` (tracked content only, already governed by the seeded `.gitignore`) and needs no second exclusion list
    - `GIT_METADATA_PATHS` is wired into the deliverable walk, deliverable counting, `list_files`, the zip route, and the public share so `.git/` and `.gitignore` are unreachable through all five — 12.3 only *tests* that, it does not implement it
    - `skills/` stays excluded from all of the above (Requirement 18 AC 3)
    - Keep the deliberate read-visibility of `.chain/` and `.context/` in `list_files`; exclude `.chain-legacy/`
    - No enforcement point may carry its own literal list
    - _Requirements: 18_
  - [x] 2.3 Guard the agent file tools in `backend/agents/capabilities/tools/providers.py` (:67-70)
    - Today returns `([], exclude_builtin=False)`, so native deepagents fs tools write unguarded
    - No writes to any registry path; reads permitted only for `AGENT_READABLE_RESERVED`
    - _Requirements: 18, 8_
  - [x] 2.4 Guard `kernel_services.py` `write_to_sandbox` (:1735)
    - No path validation or reserved-prefix check today
    - Refuse every registry path unconditionally, including `.chain/summary.md` — the engine-only payload force-stage exception does **not** apply to an agent-reachable write path
    - _Requirements: 18_
  - [x] 2.5 Normalize and derive the cross-run selector guard
    - `context_providers/previous_run.py` `_RESERVED_PREFIXES` (:56-67) → derive from the registry and add path normalization; the guard is prefix-string only today, so `./.chain/x` and `..` forms slip through
    - `compiler.py` provider validation (:281-285): reject a declared reserved selector at compile time, with the error **naming the offending entry**
    - A rejected entry must **not** fall back to a default seed set
    - _Requirements: 18, 16_
  - [x] 2.6 Add the registry-derived assertion to the public share path
    - `runs.py` `POST/DELETE /{id}/share` (:1644/:1693) and `/s/{token}`: a share exposes only the deliverable projection — no `RESERVED_PATHS` entry and no `GIT_METADATA_PATHS` entry is ever reachable, and a share of a run whose family has a `.chain/` payload does not leak it
    - _Requirements: 18_
  - [x] 2.7 Write `tests/agents/test_reserved_path_registry.py`
    - Enumerate each enforcement point's effective exclusion set and assert it equals `RESERVED_PATHS` (plus `GIT_METADATA_PATHS` for the five surfaces that exclude it) — this is the test that makes the v1 "two separate lists" failure mode unable to recur
    - Cover all twelve enforcement points, including the two `run_files.py` guards: `read_sandbox_file` and the non-ref branch of `download_sandbox_zip`
    - Every entry in both slash and bare form, plus nested paths beneath it
    - A manifest declaring only reserved entries; a rejected entry does not fall back to a default seed set
    - End-to-end: no reserved content is written into the receiving sandbox
    - An agent file tool cannot write any registry path, cannot read any except `.context/`, and specifically cannot read `.chain/`
    - _Requirements: 18_

- [x] 3. Identity, logging, sweeper protection, and the family lock (ONE ATOMIC CHANGE)
  - [x] 3.1 Add the canonical `resolve_revision_root` resolver app-side
    - Walks `parent_run_id` **only**; owner-scoped by non-null `WorkflowRun.user_id`; visited-set cycle guard; fails closed on cross-owner ancestry
    - One typed `RevisionRootUnresolved` / `revision_root_unresolved` outcome for a cycle, a missing ancestor, cross-owner ancestry, a null principal, and a DB error
    - Never selects the last unique node, never falls back to the requested run id, never returns a partial root — this supersedes v1 Requirement 1 AC 4
    - Adopt `runs.py` `_compute_root_ids` (:211) as the reference implementation, plus the non-null `user_id` condition
    - Offline characterization harnesses may default an explicitly absent `sandbox_root_id` to the logical run id without a DB query
    - _Requirements: 2_
  - [x] 3.2 Delete the duplicate walks
    - `engine.py` `_find_chain_root` (:518-580) — its docstring's "never walk `parent_run_id`" is exactly inverted from V2-Q1
    - `run_files.py` `_resolve_chain_root` (:80)
    - Fold `run_commands.py` `_revision_chain_root_id` (:3551) into the canonical resolver
    - _Requirements: 2_
  - [x] 3.3 Route every consumer through the resolver — the single owner of route root-resolution
    - Requirement 2 AC 7's consumers: engine launch, `resume_run` (~:10644), `factory.create_runner` (:293), `RunTrace` setup (:1575-1576), the **four file routes** in `run_files.py` (:605, :633, :720, :823), sweeper protection, `read_parent_file` (:1627), restore, family locking
    - Plus the two this design adds: `upload_files` (`run_files.py`:189 — the **fifth** route handler, which Requirement 2 AC 7 does not list because Requirement 10 AC 9 adds it) and `open_source_sandbox`. Five route handlers total; the "four file routes" phrasing is the requirement's, and upload is the addition — the two counts are not in conflict
    - Also fix `engine.py` `context_sources` probe (~:8816-8821) — `_RS(_disk_p, _run_id)` does not root-resolve
    - Every consumer refuses identically on `RevisionRootUnresolved` with a generic non-enumerating client error; the server logs visited-set size, repeated node, and failure class
    - This is the **only** task that changes route root-resolution; 8.5 verifies the refusal surface rather than repeating the wiring
    - _Requirements: 2, 10_
  - [x] 3.4 Split the sandbox into two ids in `backend/app/agents/sandbox.py`
    - `RunSandbox.__init__(user_id, sandbox_root_id, *, current_run_id=None, runs_root=None, has_git=True)` — root id picks the **directory** (`self.root`), `current_run_id` builds the **paths**
    - `current_run_id` defaults to `sandbox_root_id` so a root-only golden run produces an identical `.logs/` path (INV-3)
    - Fixes D2: `run_log_path`, `verify_dir`, and `browser_dir` derive from `current_run_id`, so `.logs/{run_id}.jsonl`, `.verify/{run_id}/`, and `.browser/{run_id}/` no longer collide across a revision family
    - _Requirements: 3_
  - [x] 3.5 Fix the `RunTrace` principal and path in `engine.py` (:1575-1576)
    - Root-resolve for the directory; build the log path from `current_run_id`
    - It uses the literal `user_id or "anon"` while the real sandbox at `:1808` uses `disk_principal` — if those differ the trace lands under a different user segment
    - _Requirements: 3, 2_
  - [x] 3.6 Fix the `has_git` lie in `engine.py` `_execute_impl` (:1808-1811)
    - A `git_init_sandbox` failure must flip `has_git=False`; today it only logs (:1819-1827), leaving `has_git=True` with no reachable `.git/`
    - _Requirements: 3_
  - [x] 3.7 Collapse the two disagreeing ordinal walks in `engine.py` (:1831-1856 and :452-470)
    - One counts only `completed` ancestors, the other every hop, so the tag name can differ from the ordinal written into `summary.md`
    - _Requirements: 5, 4_
  - [x] 3.8 Re-key sweeper protection to the canonical resolver
    - `main.py` `_sandbox_sweep_loop` (~:195-250) builds its protected set from `_find_chain_root`; re-key it
    - A gate-paused **or active** descendant protects the family; resolver failure ⇒ **protected**, never deletable
    - `sandbox.py` `sweep_expired` (:600) keying by `run_dir.name` is fine — it is the caller's set that must change
    - _Requirements: 2_
  - [x] 3.9 Add the cross-process family lock to `backend/app/agents/sandbox.py`
    - Keyed `(user_id, revision_root_id)`. Lock acquisition and the active-run check are ONE atomic fail-closed operation
    - `timeout` defaults to a settings-backed `FAMILY_LOCK_TIMEOUT_S` so no call site can acquire without a ceiling; expiry raises `FamilyLockTimeout` and never proceeds unlocked
    - Documented lock order: **family lock first, then the per-sandbox manifest lock.** Never the reverse
    - The only cross-process lock in the codebase today is a POSIX `flock` that silently no-ops on Windows — the family lock needs a mechanism that holds on both platforms and cannot reuse it
    - _Requirements: 10_
  - [x] 3.10 Serialize revision admission under the lock
    - `run_commands.py` `_mint_revision_row` (:3650) / `_launch_run_core` (:2415): `_has_active_chain_revision` (:3594) is three plain fail-**open** DB reads with the whole function as the race window
    - _Requirements: 10_
  - [x] 3.11 Write `tests/agents/test_sandbox_identity_v2.py` and the lock-order tests
    - Root plus two revisions in one physical sandbox produce three distinct `.logs/{run_id}.jsonl` files
    - A depth-two revision shares its family root while a chain from that revision gets a **different** root
    - Self-parent cycle, two-node cycle, missing ancestor, cross-owner ancestry, and a null principal each refuse identically at **every** caller
    - TTL sweep: an active descendant protects the family; a gate-paused descendant past TTL protects it; a fully terminal expired family is swept; a resolver failure protects
    - Admission atomicity under concurrent revision launches; lock order asserted family→manifest
    - _Requirements: 2, 3, 10_

- [x] 4. The one security-gated commit primitive
  - [x] 4.1 Add `commit_in_sandbox(...)` to `backend/agents/execution_engine/engine.py`
    - Stage exact paths → `pre_commit` → **mandatory** secret scan of real staged content → commit → `post_commit`
    - `audit_operation` is a REQUIRED explicit argument (possibly `None`), never inferred from the staged path set — restore and a recovery commit both stage `ALL_TRACKED` and would be indistinguishable. `None` means "not an audited class" and the observer no-ops rather than inventing an enum value
    - `audit_detail` carries operation-specific identifiers the observer cannot derive, mapped onto the audit row's typed columns via an allowlist (`tag_name`, `source_ref`, `idempotency_key`); keys outside it are dropped
    - The scan is **not** delegated to whether a manifest declared `secret_scan` — a declared hook may add policy but cannot remove the mandatory scan
    - Isolate the `post_commit` dispatch in `try/except`: an observer failure must not roll back the commit or alter control flow
    - Message content is engine-rendered and carries no user content
    - _Requirements: 11, 5, 19_
  - [x] 4.2 Fix D5 — replace `payload=""` with the real staged diff
    - `engine.py` step-boundary commit (:3568-3596): `scan_for_secret("")` short-circuits on its first line today, so the mandatory scan **cannot block** and only writes a `hook_runs` row with `outcome=continue`
    - `staged.hook_payload` is real staged content; for a binary-only staging set the textual diff is empty, so fall back to a content digest plus per-entry metadata
    - The `has_git=False` branch at `:3596` fires **no hooks at all** — unify it
    - _Requirements: 11_
  - [x] 4.3 Route every remaining commit path through the primitive
    - `fanout.py` worker commit (:497-503) and `merge/git_3way.py` (:76-82) — both call `commit_all` directly, bypassing hooks and the scan; a secret must be blocked at *that* commit, not at a later clean boundary
    - `engine.py` resume dirty commit (:3213-3229) and terminal wip (:404-431) — unify the two divergent message formats and the two ways of deriving the step id
    - `engine.py` spawn-point commit path: `spawn_point_commit` only *reads* `git rev-parse HEAD` today; if any spawn boundary is ever made to create a commit it goes through the primitive. If it stays read-only, record that as an explicit not-applicable closure rather than an omission
    - Assert no caller invokes `git commit` outside the primitive
    - _Requirements: 11_
  - [x] 4.4 Add typed commit outcomes to `local.py` `commit_all` (:669)
    - `git add -A` with no exclusion logic and a `CalledProcessError`→`""` swallow today
    - Add explicit-path staging plus the three-path force-add allowlist (exact normalized paths, **never** a `.chain` prefix)
    - `NoChangeToCommit` is a normal outcome surfaced as `no_change=True`; anything else raises a typed `GitCommandError`. A failed Git invocation must never be indistinguishable from a clean tree
    - _Requirements: 10, 4, 18_
  - [x] 4.5 Add binary handling to `scan_staged` / `backend/agents/capabilities/hooks/secret_scan.py` (:73-107)
    - Per-entry policy: content-scan raw bytes; bounded safe extraction for PPTX/DOCX/XLSX/ZIP; block by type/size; or a **security-approved recorded** exemption carrying its approval id
    - Extraction treats archive contents as untrusted, rejects any member whose normalized path escapes the extraction root (no zip-slip), and blocks on failure, exceeded bounds, or a malformed container
    - Unknown binary type ⇒ **block**. "Binary files differ" is never an accepted result
    - _Requirements: 11_
  - [x] 4.6 Write `tests/agents/test_commit_primitive.py` and `tests/agents/test_binary_scan.py`
    - One primitive per commit path; a blocked commit leaves the diff in the tree and is reported as blocked, not as success
    - A planted secret is unreachable from any commit, tree, tag, ref, base branch, retained worker branch, reflog entry created by finalization, or event payload
    - Binary policy matrix; a PPTX fixture with an embedded marker is caught; zip-slip refused; bounds enforced; unknown type blocked
    - _Requirements: 11_

- [x] 5. Flat payload, ordered finalizer, and the durable finalization record
  - [x] 5.1 Add the additive migrations on top of head 0041
    - `run_finalizations`: owner/workspace-scoped, **every column nullable**, `run_id` UNIQUE — the row can be created before agent 1 by the chain installer and completed at step 9 by an upsert on that key
    - `run_provenance_audits`: owner/workspace-scoped, with a nullable `idempotency_key` under a partial unique index on `(owner_id, operation, idempotency_key) WHERE idempotency_key IS NOT NULL`, plus an index on `(owner_id, source_ref)` for reverse reconstruction
    - `WorkflowRun.payload_chainable` + `WorkflowRun.non_chainable_reason`: two additive nullable columns; NULL on every legacy row means "unknown", which the eligibility gate resolves from the finalization record
    - Durable fan-out merge state: prefer an additive column set on `wave_runs` (Requirement 15 AC 10 asks for reuse first); a `fanout_merge_states` table only if that scope does not fit
    - No column removed or renamed. No `has_git` column, no tag cache, **no column for the internal run ref**
    - Every new table carries `owner_id` + `workspace_id`; re-verify one Alembic head after adding
    - _Requirements: 15, 5, 12, 19_
  - [x] 5.2 Fix D4 — build the flat payload and force-stage it
    - Rewrite `engine.py` `_write_chain_payload` (:189-311) as `build_flat_payload` returning a typed `Payload` (`allowlist`, `built`, `materialized`, `chainable`, `non_chainable_reason`), with `payload_allowlist(output_basename)` producing the three exact paths
    - `built` and `materialized` are separate facts: the metadata-only snapshot is built *and* has no output. Collapsing them would loop the finalizer's `if not payload.materialized` guard or make `materialized` mean two things. `built` is read by `FinalizationAttempt.record_payload`, which refuses a payload no builder wrote
    - Build into a `.chain.staging-{run_id}/` temp sibling, then atomically swap into `.chain/`
    - Exactly three regular files, no directories: `logs.jsonl`, `summary.md`, `{workflow_output_filename}`. Identical path set across every tag in a family
    - Drop the `.agents/` transcript copy (v1 step 5)
    - Fix the id mismatch: it reads `sandbox.run_log_path` (root id) and writes `logs/{run_id}.jsonl` (logical id)
    - Stale-basename reconciliation: `git rm --cached` a renamed deliverable's previous tracked basename so no stale file survives in `.chain/`
    - `.chain/` stays gitignored as a prefix; the three exact paths are force-staged by the primitive's allowlist exception
    - _Requirements: 4, 18_
  - [x] 5.3 Add `build_metadata_only_snapshot` for both triggers
    - `summary.md` alone, `payload_chainable: false`, a generic reason, no `logs.jsonl`, no output bytes, no excerpt of blocked material
    - Requirement 4 AC 16 is unconditional, so it must also **untrack** the other two allowlist paths — otherwise the snapshot's tree inherits the previous run's `logs.jsonl` and output bytes from the parent commit
    - Reset the index before the metadata-only commit, or the blocked bytes staged for the first attempt are swept into the snapshot built to exclude them
    - Both triggers reach it: `payload_blocked` and `output_unmaterializable`
    - _Requirements: 4, 5_
  - [x] 5.4 Render `summary.md` with fields all knowable before the commit that contains them
    - `schema_version: 2`, run/workflow/revision-root ids, `candidate_status`, `completed_steps`, `output_filename`, `intended_tag` (completed only), `internal_run_ref`, `payload_chainable`, `non_chainable_reason`, `written_at`
    - `intended_tag` is proof of *intent* only. A committed `summary.md` is **never** amended to reflect a tag created afterwards
    - The same immutability binds the **flushed terminal log**: once `.chain/logs.jsonl` is committed it is never rewritten to match a later published status either. A finalization failure after the snapshot exists changes only the published status and the finalization record (Requirement 5 AC 20) — both halves of that rule, not just the summary
    - _Requirements: 4, 5_
  - [x] 5.5 Add the internal ref namespace to `backend/app/agents/runtime/local.py`
    - New `create_run_ref` / `resolve_ref_commit` / `has_internal_run_ref` for `refs/ideaflow/runs/{run_id}` via create-only compare-and-set
    - No `git update-ref` and no `refs/ideaflow/*` exists anywhere today
    - Constructed only from a validated owned run UUID; never accepted as a caller-supplied revspec
    - Land via `getattr` duck-typing on `LocalWorkspace` as `create_tag`/`list_tags` already do — **no new method on the `Workspace` Protocol**
    - _Requirements: 5, 7_
  - [x] 5.6 Add the byte and index helpers named by the normative map
    - `read_bytes_at_ref`, `read_bytes`, `list_prefix`, `staged_entries`, `stage_exact`, `head_commit`, `reset_index`, `git_rm_cached`, `tracked_chain_paths`, `atomic_replace_dir`, `atomic_context_install`
    - New `ReadOnlySandbox` — a read-only handle on **another** run's revision-root sandbox with no write surface at all
    - _Requirements: 4, 6, 10_
  - [x] 5.7 Flush all four buffered trace classes at finalizer step 3
    - Write the candidate terminal entry into the trace, **then** flush streamed output, thinking, tool payloads, and the terminal entry — so `logs.jsonl` is complete before step 4 copies it
    - `RunTrace.flush` (`run_log.py:204`) already drains output and thinking; tool entries are written inline by `observe`; the terminal entry is the new one
    - The externally visible SSE terminal event at step 11 is the *published* event and is deliberately **not** part of the copied trace — it cannot be, because it does not exist until the snapshot it would describe is already committed
    - `run_trace` is `ectx.run_trace`, the per-run tracer bound at `execute()`
    - _Requirements: 3, 4_
  - [x] 5.8 Fix D3 — replace the early finalizer with `finalize_terminal_run`, the ordered 12-step sequence
    - Delete the optimistic stamp at `engine.py` (:4156-4165); the candidate outcome is resolved in Step 5 and passed in as a typed `CandidateOutcome`, replacing the dynamic `final_status` / `git_tag` ctx attrs
    - Replace `_fire_post_run` (:325-511) and `_post_run_fired` (:322). The process-local set may remain a fast path but must not be the sole idempotency mechanism — Git refs and durable state are inspected first
    - Structure the finalizer with **exactly one exit**: a `FinalizationAttempt` accumulator (`record_payload`, `record_commit`, `record_ref`, `record_tag`, `note_blocked_reconcile`, `degrade`) that never returns early, a `try/except BaseException` (re-raising `KeyboardInterrupt`/`SystemExit`), and a single tail. Early returns are what produced the defect class of a terminal path that skips `post_run` or the terminal event
    - The accumulator is per-pass and **not persisted** — `FinalizationRecord` is. `create_run_ref` returns a typed `RefResult` (`state` = created | idempotent | conflict, `name`, `sha`, `existing` on conflict)
    - Step 1b runs `detect_persistent_git_state` before anything else and reconciles with `crash-recovered` if needed
    - Step 2 (non-success reconcile): if the dirty-WIP commit is **blocked**, reset the index and degrade via `note_blocked_reconcile` — the reconciliation the non-success outcome required did not happen, so the published status must say so, and a blocked WIP must not poison the step-5 snapshot
    - Step 5: on a blocked snapshot, reset the index, rebuild as metadata-only, and retry once; a second block is `SnapshotUnrecoverable` (defensive only — engine-rendered content cannot block)
    - Step 6: a crash-replay whose snapshot is already committed returns `no_change`; converge on the **existing** commit rather than a null sha
    - Step 8 — **no orphan tag.** On tag success followed by DB mapping failure, retry the mapping; if it still fails, remove **only** the tag this attempt just created and report `degraded`. Never silently leave a tag with no `WorkflowRun.git_tag` mapping. This is the one exception to the no-tag-mutation rule of Requirement 5 AC 22, and it is narrow by construction: it removes a tag that was never successfully published and it never repoints a tag at a different commit. `persist_finalization_record` records the outcome as `tag_state: rolled_back`
    - `FinalizationAttempt.degrade` keeps the **first** reason — the earliest failure is the actionable one
    - Step 12 (`cleanup_worktrees_and_gc`) re-acquires the family lock **and** is wrapped in its own guard: it sits outside the main handler because the terminal event has already fired, so an unguarded `FamilyLockTimeout` there would skip `return record`. Cleanup is housekeeping; the sweeper reclaims what it misses
    - _Requirements: 5, 10, 11_
  - [x] 5.9 Route all ten terminal emission sites through the one finalizer
    - Bare return (:3261), pre-agent cancel (~:3274), gate-reject cancel (:3363), gate block (~:3411), `CancelledError`, `BudgetExceeded`, `FanoutWorkerFailed` (:4102-4119), unhandled exception / `GeneratorExit`, Step-5 total collapse (~:4185), Step-5 normal (~:4489)
    - Each emits its terminal event only after the required sequence is durable
    - `_fire_hooks` (:6945-7010) dispatch contract is unchanged; `post_run` becomes a real registered event fired exactly once per terminal run for all five statuses
    - _Requirements: 5, 11_
  - [x] 5.10 Add `persist_finalization_record` as the record's ONLY writer
    - Called on every path including every failure path — that is what makes `published_status` and `payload_chainable` durable rather than best-effort
    - Enforce the derived invariant: **when published status diverges from candidate status, set `payload_chainable = false`.** This is what makes reading `candidate_status` out of an installed `summary.md` equal to reading the published status, reconciling Requirement 4 AC 7, Requirement 5 AC 21, and Requirement 21 AC 14 without rewriting any snapshot
    - `chain_context_installed` is PRESERVED, never overwritten — its writer is `mark_chain_context_installed` at install time
    - Mirror `payload_chainable` + `non_chainable_reason` onto `WorkflowRun` in the same transaction as the published status
    - Add `persist_finalization_record_safe` for the failure path: on a second write failure return an in-memory record so the tail can still emit a terminal event, and log the unpersisted state for operator recovery (**departure N1**)
    - `FinalizationRecord` is the **complete** projection only; `read_finalization_record` returns `None` for both the absent and the partial row state
    - _Requirements: 5, 15_
  - [x] 5.11 Write `tests/agents/test_finalizer_v2.py`
    - Failure injected at each of the five Requirement 5 AC 3 points — before commit, after commit before ref, after ref before tag, after tag before mapping, after mapping — converges on retry to one consistent description of published status, record, ref, and tag
    - At **each** crash-and-retry point, a fixture whose staged content carries a secret never appears in `git rev-list --objects --all`
    - A blocked payload and an unmaterializable output each produce a metadata-only snapshot, an internal ref, `payload_chainable=false`, `degraded`, and no tag
    - `post_run` fires exactly once for completed, cancelled, failed, degraded (including degraded-by-ref-conflict), and diverted; every terminal emission path reaches one finalizer and one dispatch
    - The tag, the internal ref, and the commit whose `summary.md` names that same `intended_tag` and run id all resolve to one commit
    - `v1`/`v2`/`v3` expose the identical three `.chain/` paths with different bytes and no `.chain` directory entries; a ref-scoped `git archive` of a completed tag contains exactly the three flat files
    - A renamed deliverable leaves no stale tracked basename; a commit message contains the run id and status and no user content
    - The three named Requirement 5 AC 25 cases, all behaving per the create-only CAS contract: **repeated finalization** over an already-committed snapshot converges (`idempotent`, no duplicate commit or tag); a **manually corrupted ref** pointing at a different commit yields `conflict`, `run_finalization_failed`, `degraded`, both commit ids in the record, and the existing ref preserved rather than self-healed; a **ref that survives while the tag is absent** is readable and does not fabricate or re-derive a tag
    - Tag success followed by DB mapping failure leaves **no orphan tag**: the mapping is retried, and on second failure only the just-created tag is removed, `tag_state: rolled_back`, published `degraded` — asserted against `list_tags()` as well as the DB
    - Requirement 5 AC 20 in both halves: after a finalization failure that lands *after* the snapshot commit, neither the committed `summary.md` **nor** the committed `.chain/logs.jsonl` differs byte-for-byte from what the snapshot contained, and the snapshot commit is not amended, re-committed, force-updated, or deleted
    - **Departure N1** is exercised: a record that cannot persist still yields a terminal event, `degraded`, and a logged unpersisted state — and nothing wider
    - _Requirements: 4, 5, 11_

- [x] 6. Exact-ref chaining behind a declared activation gate
  - [x] 6.1 Make the chain capability a compiled declaration
    - `plan.py` `DeliverableSpec.chains_from` (:343) has been compiled since v1 with **zero consumers** — it becomes the gate the provider reads
    - New `plan.py` `DeliverableSpec.chain_policy`: `refuse` (default) | `degrade`; an unknown value fails compilation
    - `plan.py` `DeliverableSpec.name` (:336) becomes a validated safe basename: no separator, not `.`/`..`, no case-insensitive collision with `logs.jsonl`/`summary.md`
    - `compiler.py` `_compile_deliverable` (~:1436-1473) adds **validation only** (INV-5 keeps the compiler thin): a chainable workflow without a resolvable output name, or an unknown chain policy, fails compilation. No defaulting
    - The kernel stays name-free: the gate is read from the compiled plan, never from a workflow id comparison
    - _Requirements: 6, 4_
  - [x] 6.2 Add `open_source_sandbox` to `KernelServices`
    - Returns a `ReadOnlySandbox` on the **source's** revision-root sandbox — a different directory from `ctx.sandbox`, which holds none of the source's Git objects, refs, or tags
    - Lives on `KernelServices` (which may import `app.*`) because it needs a DB session; `chain_context` keeps importing only stdlib + registry and reaches every sandbox and persistence fact through `ctx.services`
    - Add `resolved_or_refuse`: a ref that does not resolve is a **refusal**, not a pass. Without it the Requirement 6 AC 3 tag-versus-ref check would compare `None` to `None`, find them equal, and pass having verified nothing
    - Replace `kernel_services.py` `list_chain_source_files` (:1656) / `read_chain_source_file` (:1717) — both read the live tree as text today and both resolve through `_find_chain_root` on the wrong edge
    - _Requirements: 6, 2_
  - [x] 6.3 Add the pre-mint admission gate in `run_commands.py`
    - `admit_chain_launch` returns a typed `ChainAdmission` (`active`, `source_id`, `record`, `selection`); `selection is None` while `active` means admitted under `degrade` with no payload
    - Order: declaration gate first (so a stray `source_run_id` triggers ZERO cross-run reads) → owned-row fetch → `assert_owns` → **404** for missing or cross-owner → terminality → record gates
    - Terminality must precede the record check: a running source has no finalization record by definition, so checking the record first would report every running source as `source_not_finalized` and make `source_running` unreachable
    - The record gates must precede any sandbox open: Requirement 6 AC 19 says a non-chainable source is not read from disk or from any ref at all, and the refusal is decidable from the record alone
    - Then `open_or_refuse` once, and `select_source_payload` — **provenance is settled pre-mint**. Every non-degradable verdict (tag/ref disagreement, unresolvable ref, bad payload shape, `summary.md` identity mismatch) must be reachable before the row is minted, or it would leave a persisted edge behind a refused payload
    - `is_legacy_source` is the **single** feature predicate for both Requirement 7 AC 9 disjuncts, answered from Git. Do **not** add a DB-side twin: the internal ref is deliberately not mirrored into a column, and a twin reached only when `record is None` would re-test its own branch condition, return `True` unconditionally, and admit every record-less v2 run as legacy
    - _Requirements: 6, 7, 2_
  - [x] 6.4 Split refusal from degradation in the launch handler
    - `source_running`, `source_not_finalized`, `source_non_chainable`, `source_provenance_conflict` → refuse. No run row, no edge. Never consults `chain_policy`
    - `source_payload_missing` → consults `chain_policy`: `refuse` (default) refuses; `degrade` mints **with** the edge and `selection=None`
    - Corrupt payloads refuse rather than degrade (**departure N2**): Requirement 6 AC 10 lists corrupt as degradable, but AC 3 and AC 7 say a provenance disagreement SHALL be refused and SHALL NOT fall back. `chain_policy: degrade` therefore covers absence, not disproof
    - Every refusal writes one `chain_refused` audit row carrying the reason class, so a refusal is audited exactly like a success
    - _Requirements: 6, 20, 19_
  - [x] 6.5 Persist the edge and the audit row in the mint transaction
    - `_mint_revision_row` writes the authorized `source_run_id` atomically with run creation — consuming it transiently is insufficient
    - Write the receiving run's `chain_source_selected` row in the **same transaction**, scoped to the **receiving** run id, not the source. This is what makes Requirement 19 AC 6's forward direction answerable; a row filed under the source cannot answer "which ref fed this run?"
    - A `chain_refused` row has no receiving run and is scoped to `actor_id` plus the source id — that asymmetry is the audit trail's own statement of Requirement 6 AC 16
    - Add `ExecutionContext.chain_selection` and `chain_source_run_id` (:156, declared since v1 and never assigned outside tests). The selection is derived, not authoritative: ignored unless the compiled plan declares chaining, and every read it drives still goes through an owner-scoped `ReadOnlySandbox`
    - _Requirements: 6, 19, 15_
  - [x] 6.6 Rewrite `context_providers/chain_context.py` `install_chain_context` as a byte copier
    - Re-check the declaration (its activation gate) then copy the admitted selection into `.context/` atomically before agent 1, as **bytes** — which is what makes a PPTX payload survive at all
    - Discriminate on `SourceSelection.is_legacy`: `V2Selection` (`ref`, `basename`) copies from the ref; `LegacySelection` (`ref` nullable for untagged legacy, `base`, `files`, `reason_class`) copies from the live nested tree via `install_legacy_chain_context`. `mark_chain_context_installed` and the `chain_payload_installed` audit write are the **shared tail**, so both classes get them on exactly one path
    - `mark_chain_context_installed` is the one writer of the Requirement 21 AC 8 flag; it upserts the receiving run's `run_finalizations` row at install time, before agent 1
    - `emit_chain_context_unavailable` and `resolve_install_toctou` handle the one remaining in-run failure — the validated bytes vanishing before the install (**departure N3**). Under `degrade` this is plain AC 10; under `refuse` the run fails with the edge intact and `chain_context_installed = false` as the durable discriminator
    - Provenance decisions move **out** of this file entirely
    - _Requirements: 6, 21_
  - [x] 6.7 Add legacy relocation and the legacy read path
    - New `relocate_legacy_payloads(sandbox)`: atomic `.chain/{run_id}/` → `.chain-legacy/{run_id}/`, bytes preserved, source removed only after the destination is durable, an existing destination **never** overwritten silently. Runs before the first v2 flat payload, at sandbox open. After migration `.chain/` contains no directory
    - `.chain-legacy/` is excluded from Git, Workspace listing, deliverables, zips, agent tools, and the ordinary single-file API — all derived from the one registry
    - `select_legacy_payload` (pre-mint) + `install_legacy_chain_context` (byte copy). Fallback order is `.chain-legacy/{id}/` then `.chain/{id}/` and nothing else — never live flat `.chain/`, another run's directory, the latest tag, an ordinal-derived tag, or `HEAD`
    - Validate the nested `summary.md` run id; select only the three files; ignore `{base}logs/*.md` agent transcripts
    - An untagged legacy terminal run is eligible — the `git_tag` check is conditional, not a precondition. When a tag exists, pass it through `_validate_ref` against the source sandbox's visible tag list **before** any Git subprocess sees it
    - No terminality decision here: admission's `source_is_terminal` gate already satisfies Requirement 7 AC 11, and two gates that must agree is the defect class this design removes
    - Never synthesize or backfill `refs/ideaflow/runs/{source_run_id}` for a legacy source
    - _Requirements: 7_
  - [x] 6.8 Add the `.context/` determinism, inheritance, and resume rules
    - `.context/` is one directory per **physical sandbox**, so a revision family shares it — deliberate, since it is what makes a revision see the same design inputs as the run it revises, but it means the overwrite rules must be explicit
    - `launch_context.py` (:41, :97): `resolve_launch_od_context` stays the sole producer; `write_od_context_to_sandbox` writes `.context/design/` and `selections.json` fully before step 1
    - Add the **inheritance guard**: `if context_already_present(sandbox) and not explicit_selection: return`. `explicit_selection` is true only when the revision request carried a resolved template/design-system choice — without it a revision must not silently re-resolve and overwrite the family's design inputs
    - The chain install writes only the three flat names at the `.context/` root and never touches `design/` or `selections.json`
    - `engine.py` `resume_run` (~:10644) rebuilds `ectx.od_context` via `rebuild_od_context_from_sandbox` (`launch_context.py:114`), which already wins over the `od_context_json` DB column. V2 adds the chain half: an installed payload is **preserved byte-for-byte** — resume does not re-read the source ref, re-copy, or overwrite. Re-installing would be observable, since a source tag could have been swept between the original run and the resume
    - Determinism comes from exactly three mechanisms, all of which must hold: the design writer is deterministic given one `od_context`; the inheritance guard prevents a second write producing different bytes; the chain payload is preserved rather than re-fetched
    - `.context/` stays gitignored, listed in the Workspace surface, excluded from deliverables, and readable to authorized agents via `AGENT_READABLE_RESERVED` — which contains `.context/` and nothing else
    - _Requirements: 8, 18_
  - [x] 6.9 Write the `.context/` determinism tests (real Git + real DB)
    - A resumed and an uninterrupted execution with the same inputs observe **byte-identical** `.context/` files
    - A revision inherits the root's `design/` and `selections.json` unchanged; the same revision *with* an explicit design selection rewrites them
    - A chain install does not touch `design/` or `selections.json`; a resume after install re-reads neither the source ref nor the payload
    - A source tag swept between the original run and the resume does not change what the resumed run sees
    - _Requirements: 8_
  - [x] 6.10 Write `tests/agents/test_chain_exact_ref.py`
    - A stray `source_run_id` on a workflow **without** the declaration performs zero cross-run reads — no ref resolution, no `git show`, no source sandbox `stat` — and installs no `.context/` files; the same source read by a declared workflow yields the authorized exact-ref payload
    - Chaining from `v1` after `v3` exists yields `v1`'s bytes; from a mid-family revision; from an untagged failed run; with a binary output — each receives only the selected source bytes
    - Four ineligible-source fixtures each yield their own reason code and no empty-but-successful launch: running, terminal-but-unfinalized, secret-blocked, unmaterializable-output
    - A tag/ref disagreement and a `summary.md` run-id or output-filename mismatch each refuse as `source_provenance_conflict` and never degrade
    - **Every non-degradable refusal asserts no `WorkflowRun` row was created and no `source_run_id` edge persisted** — the behavioural proof that provenance really runs pre-mint
    - A source with no finalization record and *with* an internal run ref is refused `source_not_finalized` rather than read as legacy — the assertion that keeps the legacy predicate from failing open
    - **Departure N3** exercised directly: payload validated at admission then deleted before install — `degrade` yields `chain_context_unavailable` with the edge intact; `refuse` fails the run with the edge intact and `chainContextInstalled: false`. No other fixture may reach that state
    - Three legacy fixtures — tagged with a live nested payload, the same after a sweep, and untagged terminal — and in all three **no internal ref is ever created for a legacy source**
    - A legacy stored tag absent from the owned sandbox's visible tag list is refused before any Git subprocess runs
    - Immediate chaining after each of the five terminal statuses, launched as early as the terminal event is observable, either delivers the exact payload or produces an explicit refusal — never silently empty
    - _Requirements: 6, 7, 8_

- [x] 7. Hooks, fan-out conflict policies, and crash recovery
  - [x] 7.1 Persist durable fan-out merge state as `FanoutMergeState`
    - `fanout.py` `fragments_meta` (:399, :526-533) is an in-memory `list[dict]`; persist fragment order, current fragment, and per-fragment outcome before each attempt so a crash classifies as "resume the recorded fragment"
    - `fanout.py` teardown (:702-725): branch retention on cancel is correct — keep it, and additionally clear durable merge state and worktree registrations
    - _Requirements: 12_
  - [x] 7.2 Define an outcome for every merge situation
    - Keep the `MERGE_HEAD` classification in `local.py` `merge_worktree` (:896) — it is what makes "refused" distinguishable from "conflicted", and `conflicts: []` must never be returned for a refusal
    - `fanout.py` `_resolve_conflict` (:1023-1065), **refused-before-start**: emit `merge_failed` and apply the per-policy outcome. `abort` fails the run; `partial` retains the applied set and marks the fragment failed; `merge_agent` does **not** invoke the resolver (there is no conflict to resolve) and falls through to `human_gate`; `human_gate` pauses for a decision. Never continue as though the fragment applied
    - **Started-and-conflicted** is a separate outcome table and needs its own definition, or the four policies stay undefined for the case they exist for (Requirement 12 AC 6-8):
      - `abort` — raise `FanoutError`; the run fails
      - `partial` — retained state is **every fragment whose merge already committed, plus nothing from the conflicting fragment**. Abort the conflicting merge (`git merge --abort`), mark that fragment `dropped` in the durable state, keep its per-file fragment artifacts in `artifact_refs` for recovery, record the retained set in `FanoutMergeState.retained_state` so it is inspectable rather than implied, and continue with subsequent fragments
      - `merge_agent` — the manifest-declared resolver, bounded at `MERGE_AGENT_MAX_ATTEMPTS` (`budget.py:58`, = 2). Each attempt must materialize a **clean, verified** result (no conflict markers, the step's declared validators pass) and that result is **committed through the commit primitive before success is reported**. Exhaustion falls through to `human_gate` with no oscillation past the bound
      - `human_gate` — routes through the one durable HITL (`runner.run_human_gate` → `_run_review_gate`) and persists the decision in `gate_events`, not in memory, so a resume re-enters the same merge state machine at the recorded fragment
    - **Cross-policy invariant (Requirement 12 AC 5):** under *every* policy, and for both a refusal and a started-and-conflicted merge, prior successful fragment merge commits stay intact. Nothing in the conflict path may unwind an already-committed fragment — that is the v1 defect where `git merge --abort` destroyed fragment 1's work after fragment 2 was refused
    - A scan-blocked worker or fragment commit is treated as a refusal for policy purposes — this is the Requirement 11 AC 12 linkage
    - `fanout.py` `_merge_fragments` (:910-1000): keep artifact-before-event ordering (`write_merge_conflict_artifact` then `merge_conflict`); the event carries the artifact ref on success and a generic reason on persistence failure
    - Reuse `gate_events` for the merge human-gate decision and `artifact_refs` for the conflict artifact — no new table
    - `plan.py` `Step.on_conflict` values stay exactly the four, default `human_gate`; a fifth already raises `CompilerError`
    - _Requirements: 12, 11, 15_
  - [x] 7.3 Add persistent-Git-state detection and reconciliation to `local.py`
    - New `detect_persistent_git_state` / `reconcile_persistent_git_state` covering `MERGE_HEAD`, stale `index.lock` (handled nowhere today), orphan worktree registrations, unmerged worker branches, corrupt repo → quarantine, and **a Git command failure as its own explicit state**
    - One outcome per state: recorded merge → resume at the recorded fragment; unrecorded merge → abort, retain all worker branches, `crash-recovered` commit; stale lock with no live owner → remove and record (a live owner is an explicit failure, never a forced removal); orphan worktree → prune, retain the branch; unmerged branches → retain and surface for operator inspection; corrupt repo → quarantine the family, refuse all writes, require operator action, **never delete or reinitialize**
    - Preserve staged, unstaged, and untracked content — which is why the non-success reconcile at finalizer step 2 stages tracked **and** untracked
    - Five reconciliation message classes: `cancelled`, `failed`, `degraded`, `crash-recovered`, `restore-precondition`
    - Wire detection into `engine.py` `restore_non_terminal_runs` (:7944-8235), which is purely DB-driven today and touches no Git state
    - _Requirements: 10_
  - [x] 7.4 Wire persistent-Git-state detection into **sandbox open** — the fourth entry point
    - Requirement 10 AC 14 names four entry points. Resume is 7.3, finalization entry is 5.8 step 1b, restore is 8.1 — **sandbox open had no owner**, so a family whose previous process died mid-merge would take its first write of the next run onto a repo holding `MERGE_HEAD` or a stale `index.lock`
    - Ordered exactly as the design's "Sandbox open" lifecycle requires: `git init` + `.gitignore` seeding → legacy `.chain/{run_id}/` relocation (6.7) → **detection and reconciliation under the family lock** → `.context/` design write or inherit (6.8) → chain payload install (6.6)
    - Detection precedes *any* seed, context, agent, restore, or new-revision write on ordinary shared-root revision open, not only on resume (Requirement 10 AC 3)
    - Reuses `detect_persistent_git_state` / `reconcile_persistent_git_state` from 7.3 and the family lock from 3.9 — no second detector, no second lock mechanism
    - Reconciliation goes through the commit primitive with the correct message class; a quarantined family refuses the open rather than being silently reinitialized
    - _Requirements: 10_
  - [x] 7.5 Write `tests/agents/test_crash_recovery_v2.py` and the fan-out outcome tests
    - Every persistent Git state, every restart point, every message class — including the **sandbox-open** entry point of 7.4, not just resume, restore, and finalization
    - A **Git command failure is proven to raise** rather than read as a clean tree (Requirement 10 AC 6-7) — the failure mode that would otherwise let finalization proceed to ref, tag, and published status on top of a reconciliation commit that never happened
    - **Staged, unstaged, and untracked content all survive** reconciliation — asserted per class, which is why the non-success reconcile at finalizer step 2 stages tracked *and* untracked
    - The **"after a recovery commit and before state persistence"** restart point proves idempotent resume with **no duplicate recovery commit** (Requirement 10 AC 8)
    - All four `on_conflict` policies reachable and exercised for **both** a refusal and a started-and-conflicted merge, on the **first** fragment and on a **later** fragment; a refused merge never reports `conflicts: []`; prior successful fragment commits stay intact under every policy and both situations
    - `partial`'s retained set asserted **explicitly** against `FanoutMergeState.retained_state`, and the dropped fragment's artifacts still present in `artifact_refs`
    - **Resolver exhaustion falls through to `human_gate` without oscillation** past `MERGE_AGENT_MAX_ATTEMPTS`; a `merge_agent` **success is proven to have committed a clean verified result before reporting success**
    - **Human-gate resume re-enters at the recorded fragment from `gate_events`**, not from in-memory state
    - The **artifact-persistence-failure branch**: with `write_merge_conflict_artifact` forced to fail, the `merge_conflict` event carries a generic reason and **no** ref, and the run still follows its policy
    - Cancel clears durable merge state and worktree registrations while retaining branches
    - Existing fan-out isolation tests pass, **or** carry a reviewed and recorded expectation change directly attributable to this spec (Requirement 17 AC 6) — an unexplained diff there is a regression, not a baseline update
    - _Requirements: 10, 12, 11, 17_

- [x] 8. Restore and uploads (consuming the family lock from task 3)
  - [x] 8.1 Add `POST /runs/{id}/restore` → `restore_version(run_id, tag, idempotency_key, user, db)`
    - There is **no restore endpoint anywhere** in the backend today — a regex for `@router.(post|get|put)` × `restore|revert|rollback|checkout` over `backend/**/*.py` returns zero
    - Two-layer owner gate → 404 for missing/cross-owner; root-resolve; take the family lock
    - **Idempotency check first, before the active-family guard**: a retried restore whose first attempt succeeded must return that same answer even if a new run has since started, or the replay would be refused `family_run_active` and the caller could not tell "your restore happened" from "your restore was rejected"
    - `validate_ref` against `list_tags()` (exact match) → `detect_persistent_git_state` → reconcile with `restore-precondition` if needed → `materialize_tree_at_ref` → commit through the primitive with `audit_operation="restore"`
    - Forward-only: no `reset --hard`, no tag rewrite, no branch moved backwards, no tag checked out into the live tree. Every existing commit and tag survives. The restore commit consumes no `vN` ordinal
    - A blocked restore is a refusal — it did not restore. A `no_change` restore is an honest no-op, reported as such rather than as a null commit id
    - Construct a minimal `AuditContext` (owner, workspace, run, revision root, `actor_id = user.id`) since there is no `ExecutionContext`
    - _Requirements: 9, 10, 11_
  - [x] 8.2 Store the restore replay key on `run_provenance_audits`
    - `lookup_idempotent(db, owner_id, key)` reads the typed columns (`commit_id`, `tag_name`, `outcome`) — no `detail` blob
    - The success path supplies the key through `audit_detail`, which the `post_commit` observer maps onto the column; the no-op path writes it inline because no commit means no observer dispatch
    - A **blocked** restore deliberately does not record the key: nothing was restored, the block may clear once the offending content is removed, and burning the key would make a legitimate retry return a stale refusal
    - The partial unique index is what makes two concurrent replays collapse instead of double-committing
    - _Requirements: 9, 15_
  - [x] 8.3 Add `materialize_tree_at_ref` to `local.py`
    - Forward materialization of the tracked tree only. Never `checkout`, never move a branch backwards
    - Keep `read_file_at_ref` / `list_files_at_ref` / `archive_at_ref` (:721/742/764) unchanged — read-only, HEAD never moves. Add no `checkout`, `reset`, or `read-tree` to any browse path
    - _Requirements: 9_
  - [x] 8.4 Serialize uploads behind the family lock
    - `run_files.py` `upload_files` (:189): acquire the **family lock before the manifest lock**
    - Admission per the five-state table: no active run → accept; agent step executing → accept, serialized; paused at a human or clarify gate → accept, serialized; terminal finalization holds the lock → reject with a generic retryable reason **or** queue with a bounded wait; a restore holds the lock → reject with a generic retryable reason
    - Never written concurrently with trace flush, payload assembly, or staging. Atomically visible: bytes durable → manifest entry → response
    - Uploads stay under `.uploads/`, which remains reserved and untracked
    - _Requirements: 10_
  - [x] 8.5 Verify the refusal surface on all five `run_files.py` route handlers
    - The wiring itself belongs to **3.3** and is not repeated here. This task confirms it holds for every handler once upload joins the set: the four file routes (:605, :633, :720, :823) plus `upload_files` (:189)
    - Each refuses on `revision_root_unresolved` with a generic non-enumerating error that leaks no other owner's run id, ancestry shape, or path
    - _Requirements: 2, 10_
  - [x] 8.6 Extend `tests/agents/test_family_lock.py`
    - Admission atomicity, upload races, restore races, lock order
    - Restore replay-key collapse under concurrency; a blocked restore does not burn the key
    - A step-12 family-lock timeout still returns the finalization record
    - A restore that is a genuine no-op is reported as one and is replayable
    - **Requirement 9 AC 12:** the next completed run after a restore overwrites the flat `.chain/` and is tagged normally, while the **restore commit itself consumed no `vN` ordinal** — assert the ordinal sequence has no gap and no reuse across `restore → next completed run`, and that every pre-restore commit and tag still exists
    - All five upload-admission states from the 8.4 table are asserted, and no upload lands inside a terminal snapshot commit nor is a snapshot built from a half-written upload
    - _Requirements: 9, 10_

- [x] 9. Provenance audit and failure-event contracts
  - [x] 9.1 Add the `ProvenanceAuditObserver` as a registered `post_commit` observer
    - Every commit-class row — `snapshot_commit`, `recovery_commit`, `fragment_merge`, `merge_agent_commit`, `restore` — is written by the observer, not by an inline call at each commit site. That is what makes "success is recorded" hold for a commit path someone adds later
    - Declares `events = ["post_commit"]`, registered in **both** registry surfaces (INV-12's two-surface rule), writes through the owner-scoped store
    - Observation-only: it cannot block, and a raising observer cannot abort the commit or the finalizer
    - Non-commit operations write at their own call sites: `run_ref_created`, `run_ref_idempotent`, `run_ref_conflict`, `tag_created`, `tag_mapped`, `status_published`, `chain_source_selected`, `chain_payload_installed`, `chain_refused`, `legacy_migrated`, `commit_blocked`, `legacy_context_block_stripped`
    - `run_id` is the run the row **explains** — the receiving run for chain operations. Typed columns only, no free-form `detail` blob
    - Declare the 13-month retention policy with operator-run deletion; automation is out of scope
    - _Requirements: 19, 15_
  - [x] 9.2 Add the two event types and their durable projections
    - `useWorkflow.ts` `handlePipelineMessage` (`switch` at :403, `default: return false` at :1347): add `chain_context_unavailable` and `run_finalization_failed` — both fall through the silent default today
    - Neither event carries file contents, diffs, secrets, internal paths, another owner's run id, or a raw exception string
    - Both persist through the existing `_RunEventSink.persist` path (every engine event already persists unconditionally at `engine.py:1633`), so reconnect replay is free and no transport changes
    - Both are additionally projected into durable run state: `run_finalization_failed` from the finalization record, `chain_context_unavailable` from the chain provenance audit row
    - Five bounded reason codes: `source_running`, `source_not_finalized`, `source_non_chainable`, `source_payload_missing`, `source_provenance_conflict`
    - _Requirements: 20, 19_
  - [x] 9.3 Extend the API projections
    - `runs.py` `WorkflowRunResponse` (:89) / `FamilyMemberResponse` (:1120): additive chain-source + finalization projection, ownership-scoped. A source the caller does not own projects as **absent**, never partially disclosed
    - `chain_context_installed` projects from the `run_finalizations` column directly, not through `FinalizationRecord` — a run that never finalizes still needs to report whether it received a chain payload
    - `run_commands.py` `LaunchCommand` ingress + `_launch_run_core`: the backend half of the duplicate-context guard. A launch carrying an authorized `source_workflow_run_id` **and** a legacy `=== CONTEXT FROM PREVIOUS PIPELINE … ===` block has the block stripped and the strip recorded. This must be server-side — an older frontend cannot be trusted to stop sending it
    - _Requirements: 15, 20, 21, 13_
  - [x] 9.4 Write `tests/agents/test_provenance_audit.py`
    - The six Requirement 19 AC 9 fixtures, each asserted to leave the expected owner-scoped records: a **completed run**; a **degraded run with a blocked payload**; a **legacy chain read**; a **refused chain launch**; a **restore**; and a **crash-recovered run**
    - Record presence for success as well as failure — an operation that only emitted a transient event or a log line is **not** audited (Requirement 19 AC 2)
    - Owner scoping, and a cross-owner audit read refused; content prohibitions (no file contents, diffs, prompts, model output, secrets, PII) — asserted against the row's typed columns, not merely "no payload bytes"
    - Bidirectional reconstruction: forward from a run's own `chain_source_selected.source_ref`; reverse from `WorkflowRun.source_run_id` joined to those rows
    - A `chain_refused` row raised pre-mint is scoped to the actor and the source, with no receiving run
    - Fail-closed writes; an observer failure does not roll back its commit
    - _Requirements: 19_
  - [x] 9.5 Write the event-contract and reconnect tests (backend/replay half)
    - Reconnect coverage is **required, not optional** (Requirement 17 AC 15) — for **both** `chain_context_unavailable` and `run_finalization_failed`
    - **Live delivery** on the open stream
    - **Delivery via SSE reconnect** after a disconnect that spans the event, replayed from `Last-Event-ID` through the existing down-channel and **in its original order relative to other run events** — the single append/replay path is what makes that hold, so assert the ordering, not just the presence
    - **Presence in the run-detail projection after a full reload**: `run_finalization_failed` from the finalization record, `chain_context_unavailable` from the chain provenance audit row
    - Neither payload carries file contents, diffs, secrets, internal paths, another owner's run id, or a raw exception string
    - Every one of the five reason codes (`source_running`, `source_not_finalized`, `source_non_chainable`, `source_payload_missing`, `source_provenance_conflict`) is distinct and round-trips through persistence and replay unchanged
    - _Requirements: 20, 17, 19_

- [x] 10. Prompt assembly and per-workflow migration
  - [x] 10.1 Register the body-only and governance prompt orders in `capabilities/prompt/policy.py`
    - Governed agents keep guardrails, hooks, Constitution, and `AGENT.md`
    - `factory.py` prompt policy selection reads the policy name from the manifest; omitted/empty ⇒ `default`; unknown non-empty ⇒ compile error
    - _Requirements: 13_
  - [x] 10.2 Remove the factory's own skills rendering only
    - `factory.py` `_compose_injection` (the `skills` block): removing it removes the factory's rendering. Deepagents' `SKILLS_SYSTEM_PROMPT` is supplied by the runtime adapter and is **not** touched; `skill_staging.py` keeps staging `skills/` unchanged
    - _Requirements: 13_
  - [x] 10.3 Retarget `engine.py` `_compose_context_message` (~:11261)
    - Seam 2 removal per workflow; brief to agent 1 only, except the Requirement 14 retry classes; the retry block targets the retrying agent
    - **No `REQUEST.md` is ever created** — the engine does not write the raw user request to disk and does not propagate it downstream outside those retry classes
    - _Requirements: 13, 14_
  - [x] 10.4 Implement the retry and redo recipient matrix
    - Requirement 14's five classes, resume rules, and **unconditional draining** of the consume-once `context.py` retry/redo scratch fields per dispatch iteration — never replayed twice on resume
    - The Requirement 14 AC 6 dispatch-consumption record reuses the existing checkpoint thread plus `gate_events`; no new table
    - `run_commands.py` validation-fix dispatch + `capabilities/post_step/revision_validation`: the fix-loop control payload carries validation errors and the exact deliverable path, and nothing else
    - _Requirements: 14_
  - [x] 10.5 Migrate each workflow's first durable artifact, cheapest first, `prototype` last
    - Every migrated first step declares and produces one durable contract artifact (`PLANNER.md`, a spec file, or a declared typed artifact — whichever the workflow already produces); later agents read declared files plus their own task
    - Verify per workflow **before** Seam 2 is deleted for it. `prototype` is the SC-001 anchor and goes last
    - Re-derive each workflow's characterization baseline deliberately — this is a blessed behaviour change, not a mechanical update
    - _Requirements: 13_
  - [x] 10.6 Update the prompt viewer
    - `AgentThinkingTab.tsx` / `AgentDetailPanel.tsx`: display the effective system prompt plus the targeted control payload — never a misleading empty-context message
    - _Requirements: 13_
  - [x] 10.7 Document override semantics in `prompt_overrides.py` and its API docstring
    - Overrides remain **replacement bodies**, not additive fragments; the API documentation must state that explicitly rather than leaving it to be inferred
    - Production override migration stays **deferred to the v1 trigger** — this task documents the contract, it does not migrate stored overrides
    - _Requirements: 13_
  - [x] 10.8 Write `tests/agents/test_prompt_ledger_v2.py` and `tests/agents/test_retry_recipients_v2.py`
    - All 30 ledger rows across five modes (normal, retry, redo, resume, chained-run), verified through the **full composer**, not by popping a dictionary; rows 22 and 27 carry explicit not-applicable assertions
    - Requirement 14's five classes for both first and non-first agents
    - **Staged skills remain discoverable after the factory `skills` block is removed** — removing it removes the factory's own rendering only; deepagents' `SKILLS_SYSTEM_PROMPT` is untouched and `skill_staging.py` still stages `skills/` (Requirement 13 AC 3)
    - **No `REQUEST.md` is created**, and the raw user request reaches **no** downstream agent outside the Requirement 14 retry classes (Requirement 13 AC 4)
    - **The prompt viewer shows the effective system prompt plus the targeted control payload and never an empty-context message** — with file-based context the human message is legitimately short, and rendering that as "no context" would hide the migration's actual behaviour (Requirement 13 AC 9)
    - A migrated workflow's first step produces its durable contract artifact
    - A governed agent does not silently lose its Constitution when its workflow migrates
    - A conditional-gate retry loop still tells the agent why it was sent back, and only that agent receives it
    - A consumed one-shot control payload is not replayed on resume
    - _Requirements: 13, 14_

- [x] 11. Compatibility and UI
  - [x] 11.1 Send lineage on the direct chain paths
    - `DashboardLayout.tsx` `handleChainPipeline` (:1760) / `handleChainFromHistory` (:1883): add the missing `source_workflow_run_id` to the two non-wizard `onStartPipeline` calls (:1870, :1958) — the direct chain path sends **no lineage at all** today
    - _Requirements: 21, 6_
  - [x] 11.2 Version the chain storage namespace in `lib/workflowChaining.ts` (:33-38)
    - Add a `chain.v2.*` namespace; give `chain.context_block` a constant, then drop the legacy key on first load under the version key
    - Cleanup covers `sessionStorage`, `localStorage`, and in-memory launch state; is idempotent; and must not discard `chain.brief` or unrelated draft input
    - `LaunchWizard.tsx` (:830-834): stop reading `chain.context_block`; keep the consume-once removal of `chain.source_run_id`
    - `lib/runInput.ts` `parseRunInput` `chainRe` (:61): **no change** — the marker parser stays for historical runs
    - _Requirements: 21, 13_
  - [x] 11.3 Extend the frontend data layer
    - `lib/api.ts`: add `postRestoreRun(token, runId, {tag, idempotency_key})`; extend `RawWorkflowRun` (:676) + `normalizeWorkflowRun` (:703) with the chain-source projection plus `payload_chainable`, `non_chainable_reason`, `chain_context_installed`, `chain_unavailable_reason`, and the finalization reason code/message
    - `types/index.ts` `WorkflowRun` (:375) / `FamilyMember` (:429): add `chainSource` (id, **shortId**, workflowId, publishedStatus, visibleTag | null), `chainContextInstalled`, `payloadChainable`, `nonChainableReason`, `chainUnavailableReason`, `finalizationReason`. **No internal ref field ever**
    - _Requirements: 9, 15, 20, 21_
  - [x] 11.4 Render the chain lineage indicator on the two named surfaces
    - `RunDetailPage.tsx` (:457) and `RevisionFamilyView.tsx` (:796), driven by the `chainSource` projection rather than client inference
    - Label composition names the source workflow plus the **selected version**: the visible tag when one exists, otherwise the source run's short id plus its published status. Never an internal ref name
    - Add "no version tag" for a terminal-untagged run, and the source's status for a chained run
    - Presentation precedence: a run is file-based **iff** `chainContextInstalled`, not `chainSource != null` — `source_run_id` predates v2 (migration 0014), so keying on the edge would flip both a pre-v2 marker run and a deliberately degraded run to file-based
    - A revision is never labelled chained; a chained run never appears inside its source's revision family list (the family view is built from the `parent_run_id` projection, which structurally excludes chains)
    - `HomeLaunchGrid.tsx` (:382): the `(Chained)` recents affordance stays
    - _Requirements: 21_
  - [x] 11.5 Add the `RunEngineNotice` component and degraded-status treatment
    - Engine-fact presentation, not a chat message from an agent: non-color-only indicator, programmatically associated message, keyboard-reachable detail, unknown-reason-code fallback to a generic message
    - `role="alert"` exists exactly once in the tree today (`AgentsPopup.tsx:2670`) — this establishes the convention; the `role="log" aria-live="polite"` transcript (`ChatPanel.tsx:283`) announces it
    - A `degraded` run is visually **and** semantically distinguishable from `completed`: distinct label text, distinct non-color indicator, announced to assistive tech. Not a colour variant of the success state
    - Reason→action mapping: retry (`source_not_finalized`) · choose another source (`source_non_chainable`, `source_payload_missing`, `source_provenance_conflict`) · retry-later (`source_running`) · contact support with the reason code (`run_finalization_failed`). Never offer an action the server refuses
    - _Requirements: 20_
  - [x] 11.6 Fix the live version-menu defect and add restore
    - `RunHeader.tsx` `VersionMenu` (:30-127) passes a **tag name** to `onSelectVersion`, but `PreviewPanel.handleSelectVersion` (:669) treats it as a **run id** → `findIndex` returns -1 and `getWorkflow("v2")` fails into a `console.warn`. Wire it to `SandboxTab`'s `selectedRef`
    - `SandboxTab.tsx` (:948-951, :1184-1215): keep the working ref picker; add the restore action, disabled while any family member is non-terminal, showing the server's generic reason. `.chain-legacy/` must not appear in the listing
    - _Requirements: 9, 18_
  - [x] 11.7 Add the chain-source picker and pre-launch warning
    - Offer `completed` normally; offer non-success only when `payload_chainable`; show non-chainable as unavailable with its reason
    - The warning is accessible and acknowledged, not color-alone, and states **both** the source's published status **and** that its output may be incomplete
    - _Requirements: 21_
  - [x] 11.8 Handle mixed deploy explicitly
    - New FE + older BE: degrade to no chain context and surface the Requirement 20 AC 4 reason rather than launching without provenance
    - Older FE + new BE: the legacy text block is rejected or ignored, never combined with the file payload
    - Any other combination is **named as unsupported** in the launch error, never left undefined
    - _Requirements: 21, 13_
  - [x] 11.9 Write the frontend tests (and the two API/server-side tests they pair with)
    - `frontend/src/**/*.test.tsx`: lineage indicator on both named surfaces driven by the API projection rather than client inference, versioned storage cleanup, source picker, the two new event types rendering, restore action gating, unknown reason-code fallback
    - **An API test proves the persisted edge and the projection** (Requirement 21 AC 4) — including that a source the caller does **not** own projects as **absent**, never partially disclosed. Together with the frontend test this closes the v1 Requirement 22 AC 11 acceptance test, which had never had a writer
    - **A server-side test for the duplicate-context guard** (Requirement 21 AC 10): an older client sends **both** `source_workflow_run_id` **and** a legacy `=== CONTEXT FROM PREVIOUS PIPELINE … ===` block, and the backend is proven to strip the block and record the strip as `legacy_context_block_stripped`. No launch produces duplicate chain context
    - A new launch sends **no** text context block; a stale stored block is cleaned up **exactly once** across `sessionStorage`, `localStorage`, and in-memory launch state, and unrelated draft input survives
    - **A historical marker-bearing run still renders** as it does today
    - **Presentation precedence asserted on `chainContextInstalled`, not on `chainSource != null`**: a pre-v2 marker-bearing run that happens to carry `source_run_id` still renders as legacy text, and a `chain_policy: degrade` run that kept its edge without a payload does too. Keying on the edge would flip both to file-based and break Requirement 21 AC 7-8
    - **Source-list composition for all five terminal statuses plus a non-chainable source**; a non-chainable source shows as unavailable with its reason rather than being offered and then refused
    - The non-success warning is accessible and acknowledged, not color-alone, and names **both** the published status **and** that output may be incomplete
    - **No internal ref string appears in any rendered output**; a terminal-untagged run reads "no version tag", never an error and never a ref name
    - **The receiving run's surface displays a non-success source's published status**, sourced from the installed `.context/summary.md` fact via the projection
    - A `degraded` run is visually **and** semantically distinguishable from a `completed` one
    - Both event types render with the Requirement 20 AC 5 accessible pattern — non-color-only indicator, programmatically associated message, keyboard-reachable detail — with the correct next action per reason code and never an action the server refuses
    - **Reconnect rendering half** (Requirement 20 AC 9, pairing with 9.5): each event type renders after arriving via reconnect, and remains visible from the run-detail projection after a full page reload
    - `frontend/e2e/tests/*.spec.ts` (`mocked` project): version browse, restore, chain launch
    - Run single-pass (`npm run test`), never watch mode
    - _Requirements: 20, 21, 9, 13, 17_

- [x] 12. Final validation
  - [x] 12.1 Verify the kernel stayed name-free
    - `grep -rn "if pipeline_type ==" backend/agents/execution_engine/` → 0 matches
    - `grep -rn 'spec\.id ==' backend/agents/execution_engine/` → 0 matches
    - All 11 `tests/agents/test_banned_patterns.py` tests pass; the SSE banned-pattern ratchet stays green
    - `_extract_chain_context`'s seven hardcoded `pipeline_type` branches are **not** extended
    - _Requirements: 16, 17_
  - [x] 12.2 Verify INV-3
    - `pytest tests/agents/test_characterization_*.py` with `SNAPSHOT_UPDATE` unset
    - `git status --porcelain tests/agents/characterization/golden/` shows only the intentionally re-baselined prompt-migration files
    - New `pipeline_complete` fields are in `_VOLATILE_STRIP_KEYS`; new chat event types are in `_DOCUMENTED_EVENT_TYPES`
    - _Requirements: 16, 17_
  - [x] 12.3 Run the design's Security (behavioural) checklist
    - After a completed run **and** after a restore: `git log --name-only` and `git show --stat` contain no registry path except the three allowlisted files
    - `list_files`, the deliverable walk, deliverable counting, the zip, `WorkflowRun.output`, and the public-share output contain none of them, nor `.git/`, nor `.gitignore`
    - An agent file tool cannot write any registry path and cannot read any except `.context/` — specifically not `.chain/`
    - Security closures are verified by behaviour, never by reading code
    - _Requirements: 17, 18_
  - [x] 12.4 Verify the three named departures are bounded
    - **N1** (Req 5 AC 12): a terminal event fires without a durable record only on double write failure, publishing `degraded` with the DB-failure reason class and a logged unpersisted state
    - **N2** (Req 6 AC 10): corrupt payloads refuse; only missing and swept degrade
    - **N3** (Req 6 AC 16): exactly one TOCTOU case keeps the edge on a failed run, discriminated by `chain_context_installed = false`
    - Each has a test asserting the bound, so a future change cannot widen it silently
    - _Requirements: 5, 6_
  - [x] 12.5 Run the toolchain on every modified file
    - Backend: `ruff check`, `pyright`, `lint-imports` (three import-linter contracts stay green — `chain_context` still imports only stdlib + registry; the closed `Workspace` Protocol in `agents/runtime/base.py` gained no method)
    - Frontend: `npm run build`, `npm run lint`, `npm run test`
    - Re-verify one Alembic head
    - _Requirements: 16, 17_
  - [x] 12.6 Verify rollback safety
    - Exercise a rollback build against a sandbox that **already holds v2 artifacts**, not a clean one
    - Rollback stops producing v2 payloads without deleting tags, internal refs, tracked flat files, audit records, or legacy payloads
    - A rollback reader ignores unknown tracked `.chain` files rather than corrupting a run
    - A rollback reader also **ignores a v2 finalization record and a metadata-only snapshot without corrupting the run** (Requirement 17 AC 18) — a `summary.md`-only snapshot must not read as a truncated three-file payload
    - Feature detection is by the presence of the internal run ref and the `schema_version` in `summary.md` — **no global date or deploy flag** anywhere
    - _Requirements: 17_
  - [x] 12.7 Gap-closure review — the release gate
    - Confirm, **before release**, that every row of the requirements' GAPS.md Closure Matrix (`SGV2-GAP-001` … `SGV2-GAP-021`) has a passing test **or** an explicitly recorded not-applicable justification
    - An **unreviewed row blocks release** (Requirement 17 AC 19). "The code looks right" is not a closure; neither is a checked task — Requirement 1 AC 3 applies to v2's own checkboxes exactly as it applies to v1's
    - Record the reviewed outcome per gap id alongside the criteria the matrix names, so a later reader can tell a closure from an omission
    - _Requirements: 17_

---

## Notes

- **Task 1.5 is a standing constraint, not a one-off step.** It pins what this spec does *not* build and which surfaces must stay unchanged. Re-read it before adding anything not already on this list — the design's component map is normative (Requirement 1 AC 5), so a required change outside it updates the map first.
- **Task 3 is atomic.** Requirement 17 AC 2 requires the revision-root correction to land together with sweeper protection *and* family-lock protection. The lock therefore ships in task 3, not with restore in task 8 — the window between re-keying the sandbox and serializing access to it is exactly the unserialized shared state v2 exists to close. Tasks 8.1 and 8.4 only *consume* it.
- Task 2 (the registry) precedes everything that enforces a path rule; the registry is the single source those enforcement points derive from.
- Task 4 (the commit primitive) precedes task 5 (the finalizer), because the finalizer's snapshot commit goes through it and the mandatory scan must be real before any payload is committed.
- Task 6 depends on task 5: chaining reads the finalization record and the internal ref that task 5 creates.
- The payload/finalizer change and the revision-root correction ship as separate revertible commits or PRs where repository workflow permits (Requirement 17 AC 5).
- Alembic head before this spec is **0041**, not 0037 as `.kiro/steering/project-index.md` claims — task 1.3 corrects the steering file. Verify with `cd backend && alembic heads` before task 5.1; it must print exactly ONE head.
- Every new table and column carries `owner_id` + `workspace_id` where applicable, and all migrations are additive — no column removed or renamed.
- A v1 checkbox is not verification evidence (Requirement 1 AC 3). Source inspection does not count as acceptance for restore, lifecycle dispatch, locks, or prompt recipients (Requirement 17 AC 8).
- Production apply stays pipeline-controlled and approved. No operator applies a migration, creates a ref, moves a tag, or edits a sandbox by hand on a shared environment. The one operator-driven action — internal-ref conflict recovery — is inspection-and-decision, and any resulting write goes through the pipeline (Requirement 17 AC 12).

---

## File path resolution

Several filenames referenced in short form above (and in the design's component map)
are ambiguous in this repo — `providers.py` exists in four places, `factory.py` and
`compiler.py` also exist inside `backend/.venv/`. Verified full paths, so no task
edits the wrong file:

| Short form used | Actual path |
|---|---|
| `sandbox.py` | `backend/app/agents/sandbox.py` |
| `local.py` | `backend/app/agents/runtime/local.py` |
| `base.py` (closed Workspace Protocol) | `backend/agents/runtime/base.py` |
| `engine.py` | `backend/agents/execution_engine/engine.py` |
| `context.py` (`ExecutionContext`) | `backend/agents/execution_engine/context.py` |
| `fanout.py` | `backend/agents/execution_engine/fanout.py` |
| `kernel_services.py` | `backend/agents/execution_engine/kernel_services.py` |
| `run_log.py` (`RunTrace`) | `backend/agents/execution_engine/run_log.py` |
| `factory.py` | `backend/agents/factory.py` — **not** `backend/.venv/.../langchain/agents/factory.py` |
| `plan.py` | `backend/agents/workflows/plan.py` |
| `compiler.py` | `backend/agents/workflows/compiler.py` — **not** SQLAlchemy's `ext/compiler.py` |
| `authz.py` | `backend/agents/authz.py` |
| `secret_scan.py` | `backend/agents/capabilities/hooks/secret_scan.py` |
| agent-tool `providers.py` | `backend/agents/capabilities/tools/providers.py` |
| `chain_context.py` / `previous_run.py` | `backend/agents/capabilities/context_providers/` |
| `git_3way.py` | `backend/agents/capabilities/merge/git_3way.py` |
| `launch_context.py` | `backend/app/api/launch_context.py` — API layer, not `app/agents/` |
| `run_files.py` / `run_commands.py` / `runs.py` | `backend/app/api/` |
| `main.py` (`_sandbox_sweep_loop`) | `backend/app/main.py` |
| `skill_staging.py` | `backend/app/agents/skill_staging.py` |
| `prompt_overrides.py` | `backend/app/agents/prompt_overrides.py` |
| Alembic revisions | `backend/alembic/versions/` |
| `tests/agents/...` | `backend/tests/agents/...` — test paths are **backend-relative**, matching the existing convention; run `pytest` from `backend/` |

Line numbers throughout are from the state at spec authoring. Treat them as
navigation hints, not contracts — confirm the symbol before editing.

---

## Task Dependency Graph

Waves follow the design's Rollout order (Requirement 17 AC 1-2). Tasks inside one
wave have no dependency on each other and can be worked in parallel; a wave cannot
start until every earlier wave is done. The non-obvious edges:

- **Waves 4-7 are a build order inside task 3, not four shippable increments.**
  Requirement 17 AC 2 makes task 3 atomic — the re-key, sweeper protection, and the
  family lock land together.
- **7.3 is hoisted ahead of 5.8.** The finalizer's Step 1b calls
  `detect_persistent_git_state`, so the detector must exist before the finalizer
  lands. 7.1 waits for 5.1 because the durable fan-out merge state is one of that
  task's additive migrations.
- **7.4 (sandbox-open detection) sits after 6.7, not with 7.3.** It reuses 7.3's
  detector but has to be ordered *inside* the sandbox-open sequence — after the
  legacy `.chain/{run_id}/` relocation and before the `.context/` write — so it
  cannot land until 6.7 exists.
- **7.5 is the last of task 7, in wave 23.** It asserts the `restore-precondition`
  message class, so it waits for 8.1, and it covers 7.4's entry point.
- **9.1 precedes 8.1 and 8.2.** Restore's audit row and its replay key are written
  by the `post_commit` observer, so the observer exists before restore does.
- **9.5 follows 9.2 and 9.3.** Reconnect replay needs both event types emitted and
  both durable projections in place; its frontend counterpart is in 11.9.
- **2.1 carries `payload_allowlist`.** Task 4.4's force-add allowlist (wave 8)
  needs the function before the payload builder in 5.2 (wave 12) exists, which is
  why it lives in the registry block rather than with the builder.
- **8.3 lands early (wave 13).** `materialize_tree_at_ref` is a `local.py`
  read/materialize helper with no dependency on the finalizer or the record.
- **Task 10 has no hard dependency on tasks 2-9** and may be pulled forward. Its
  only ordering constraints are that 10.5's deliberate re-baselining happens after
  1.1 captured the baseline and before 12.2 checks the goldens.
- **Task 12 is a single wave** — all seven checks are independent and read-only.
  12.7 is the release gate: it reviews the other six plus every gap row, and
  reviews nothing it also implements.

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "1.3", "1.5"] },
    { "id": 1, "tasks": ["1.4", "2.1"] },
    { "id": 2, "tasks": ["2.2", "2.3", "2.4", "2.5", "2.6"] },
    { "id": 3, "tasks": ["2.7"] },
    { "id": 4, "tasks": ["3.1"] },
    { "id": 5, "tasks": ["3.2", "3.4", "3.9"] },
    { "id": 6, "tasks": ["3.3", "3.5", "3.6", "3.7", "3.8", "3.10"] },
    { "id": 7, "tasks": ["3.11"] },
    { "id": 8, "tasks": ["4.4", "4.5"] },
    { "id": 9, "tasks": ["4.1"] },
    { "id": 10, "tasks": ["4.2", "4.3"] },
    { "id": 11, "tasks": ["4.6"] },
    { "id": 12, "tasks": ["5.1", "5.5", "5.6"] },
    { "id": 13, "tasks": ["5.2", "5.4", "5.7", "7.1", "7.3", "8.3"] },
    { "id": 14, "tasks": ["5.3", "5.10", "7.2"] },
    { "id": 15, "tasks": ["5.8"] },
    { "id": 16, "tasks": ["5.9"] },
    { "id": 17, "tasks": ["5.11"] },
    { "id": 18, "tasks": ["6.1", "9.1"] },
    { "id": 19, "tasks": ["6.2", "6.7", "8.2"] },
    { "id": 20, "tasks": ["6.3", "7.4", "8.4", "8.5"] },
    { "id": 21, "tasks": ["6.4", "6.8", "8.1"] },
    { "id": 22, "tasks": ["6.5", "6.6"] },
    { "id": 23, "tasks": ["6.9", "6.10", "7.5", "8.6"] },
    { "id": 24, "tasks": ["9.2"] },
    { "id": 25, "tasks": ["9.3"] },
    { "id": 26, "tasks": ["9.4", "9.5", "10.1", "10.2", "10.7"] },
    { "id": 27, "tasks": ["10.3"] },
    { "id": 28, "tasks": ["10.4", "10.6"] },
    { "id": 29, "tasks": ["10.5"] },
    { "id": 30, "tasks": ["10.8", "11.1", "11.2", "11.3"] },
    { "id": 31, "tasks": ["11.4", "11.5", "11.6", "11.7", "11.8"] },
    { "id": 32, "tasks": ["11.9"] },
    { "id": 33, "tasks": ["12.1", "12.2", "12.3", "12.4", "12.5", "12.6", "12.7"] }
  ]
}
```
