# Design Document: Sandbox Git Versioning

## Overview

The core architectural change is a single keying decision: `RunSandbox` moves from
`<RUNS_ROOT>/<user>/<run_id>/` to `<RUNS_ROOT>/<user>/<chain_root_id>/`. Every
revision in a family shares one directory. On top of that shared directory, every
sandbox becomes a real git repository — each step is a commit, each completed run
is a version tag, fan-out workers use git worktrees for isolation, and inspectable
history replaces the current flat working tree.

Five mechanisms already exist in production and are reused rather than rebuilt:

| Need | Existing mechanism | What is new |
|---|---|---|
| Run code around a commit or at run end | `Step.hooks` + `_fire_hooks`, declaration-driven, permission-bound | Three new events: `pre_commit`, `post_commit`, `post_run` |
| Which step is last | `is_leaf`, compiler-computed, runtime-consumed | Nothing — tag moves to the terminal path, not a leaf |
| Read another run's files safely | `read_parent_file` + `ScopedStore.assert_owns`, fail-closed | One sibling method `read_chain_source_file` |
| Change what a prompt contains | Registered `prompt` policy, `user_allowed=True` | One new policy order, one un-hardcoded name in `factory.py` |
| Declare cross-run behaviour | `revises_existing` to `ctx.is_revision_workflow` | One sibling flag for chaining |

What is genuinely missing is narrow: `git init`, a seeded `.gitignore`, `create_tag`
and `list_tags`, a `.chain/` prefix and writer, one declared chain flag, one nullable
column, and the four `run_files.py` call sites that resolve a sandbox independently
of the engine.

---

## Architecture

### Before: One directory per run

The sandbox is keyed by the individual run UUID. A revision mints a new UUID and a new empty directory. The `previous_run` context provider manually copies a narrow allowlist (spec.md, design.md, tasks.md, one deliverable, .uploads/) into the empty directory. Anything the agent wrote outside that list is permanently lost. There is no git history, no commits, no tags, and no diff capability. The `merge_worktree` false-clean merge bug is dormant because no artifact sandbox has ever had `has_git=True`. Chaining carries a text block assembled on the frontend. Every agent receives injected context blocks it did not ask for.

### After: One directory per unit of work

The sandbox is keyed by the chain root (the original run). All revisions in a family share one directory. The shared directory is a real git repository — `git init` with an initial commit at provision time, `.gitignore` covering 8 reserved paths. Every step produces one commit. Every completed run is tagged `vN`. Fan-out workers use git worktrees for isolation and 3-way merge. The `.chain/{run_id}/` payload is written at completion for chained workflows. The `.context/` directory is written before step 1 with everything the run was given.

### Directory layout after this spec

```
RUNS_ROOT/user/
  chain_root_id/
    .git/                      git repository
    .gitignore                 8 reserved prefixes
    prototype.html             rewritten by each revision, tracked in git
    spec.md
    .agents/                   gitignored; flat by design
    .logs/
      run_A_id.jsonl           per-run log
      run_B_id.jsonl
    .verify/
      run_A_id/                per-run validator evidence
      run_B_id/
    .browser/
      run_A_id/                per-run browser artifacts
    .uploads/                  accumulates across the family by design
    .chain/
      run_A_id/                chain payload left by run A
        summary.md
        prototype.html
        logs/
      run_B_id/
    .context/                  what this run was given (gitignored)
      design/
        design-system.md
        craft.md
        template/
      selections.json
```

### Run lifecycle

Launch: `launch_context.py` writes `.context/` before step 1. `engine.run()` builds `RunTrace(RunSandbox(user, chain_root))`. `engine._execute_impl()` opens `RunSandbox(user, chain_root)`, calls `git init` idempotently with an initial commit, and seeds `.gitignore`.

Per step: prompt policy is read from manifest and system prompt is composed as the agent's own `AGENT.md`. The brief reaches agent 1 only; later agents carry their task only. After the model call, `write_agent_output` persists the output to `.agents/{NN}-{agent_id}.md`. At the step boundary: `pre_commit` hook fires (may block), `git add -A && git commit` runs (gated on `has_git`), `post_commit` hook fires (observe only). The commit fires before the routing decision for retry loops.

Terminal path: the `post_run` fire-once finalizer runs. If status is `completed`, `create_tag(f"v{revision_ordinal}")` is called and `git_tag` is written to the DB. `.chain/{run_id}/` is written. `git gc --auto` runs. If cancelled/failed/degraded with a dirty tree, `wip: cancelled at step {id}` is committed.

Revision (run B): `_execute_impl` resolves the same chain root and opens the same directory run A wrote into. `prototype.html`, `spec.md`, `tasks.md` are already present. `previous_run` seeding is short-circuited. Dirty-tree reconciliation runs before the step if the tree is non-empty.

---

## Components and Interfaces

### Frontend — composer (L1)

| Component | Change | Requirement |
|---|---|---|
| `DashboardLayout.tsx` `handleChainPipeline` / `handleChainFromHistory` | Retire or gate `enrichedInput` assembly — agent B must not receive the same context twice | 22 |
| `frontend/src/lib/runInput.ts` `parseRunInput` | No change — single canonical marker parser; keep in sync with producer changes | 22 |
| `LaunchWizard.tsx` | No change — chain ids already thread through | — |

### Frontend — run surface (L2)

| Component | Change | Requirement |
|---|---|---|
| `SandboxTab.tsx` | Renders the shared chain-root directory for all revisions; gains `.chain/` section; gains `selectedRef` state and tag picker | 17, 19, 20, 43 |
| `RunHeader.tsx` VersionMenu | Disabled with explicit notice in Phase 3; restored on real git tags in Phase 6 | 19 |
| `AgentThinkingTab.tsx` / `AgentDetailPanel.tsx` | Repointed at system prompt plus targeted retry payload after Seam 2 removal | 36 |
| `RunDetailPage.tsx` / `RevisionFamilyView.tsx` | Add tagged badge beside existing `v{revision_index}` chip | 32 |
| `FilesTab.tsx` | No change — precedent for read-only version props | — |

### Frontend — data layer (L3)

| Component | Change | Requirement |
|---|---|---|
| `frontend/src/lib/api.ts` | Add optional `ref` on four sandbox functions; add new `getRunSandboxRefs` | 17 |
| `frontend/src/types/index.ts` `FamilyMember` | Add optional `git_tag` field | 32 |
| `frontend/src/hooks/useWorkflow.ts` | No change — `inputPrompt` is a pure passthrough | — |

### API routes (L4)

| Component | Change | Requirement |
|---|---|---|
| `run_files.py` four `RunSandbox(...)` constructions | All four must resolve to the same chain root the engine uses | 1, 43 |
| `run_files.py` read routes | Optional `ref` query param; new `GET /{run_id}/sandbox/refs` | 17 |
| `run_commands.py` `_mint_revision_row` and `_launch_run_core` | Write `source_run_id` for the first time; add server-side revision lock | 3, 22 |
| `runs.py` `_extract_chain_context` | Out of scope — do NOT extend | 34 |
| `runs.py` `FamilyMemberResponse` | Additive `git_tag` field | 32 |
| `runs.py` `_compute_root_ids` | No change — cycle-guarded walk that Requirement 1 mirrors | 1 |
| `runs.py:1625` `GET /s/{token}` | No change — serves `WorkflowRun.output` only; safe while deliverable exclusions hold | 9 |
| `launch_context.py` `resolve_launch_od_context` | Writes `.context/` at sandbox open instead of feeding `od_context_json`; `resume_run` reads those files | 23 |
| `engine.py:2221` `PLANNER.md` write | Must run AFTER clarify rounds merge at `:2339` | 30 |

### Persistence (L5)

| Component | Change | Requirement |
|---|---|---|
| `WorkflowRun.git_tag` | New additive nullable column via one Alembic migration | 32 |
| `WorkflowRun.source_run_id` | Already exists (migration 0014); start writing it | 22, 32 |
| `WorkflowRun.root_run_id` | Optional; one additive nullable column if walk is measured to be slow | 1 |
| `WorkflowRun.od_context_json` | `resume_run` dependency moved to `.context/` files | 23 |
| `agents/artifacts/graph.py` `ARTIFACT_KINDS` | No change — `summary` already recognised | 20 |
| `models/workspace.py` `Workspace` | No change — `has_git` is in-memory, never persisted | 11 |

### Compiler (L6)

| Component | Change | Requirement |
|---|---|---|
| `compiler.py` and `plan.py` | One new declared chain flag mirroring `revises_existing` | 22 |
| `plan.py` `Step.hooks` and `is_leaf` | No change — both already exist and dispatch correctly | 10, 14 |
| `permission_caps.py` | One flip in the same PR as the first declared git hook; engine commit bypasses the cap | 10, 12, 42 |
| `plan.py` and `compiler.py` new `outputs` and `replaces` step fields | Declared output surface for engine-side deletion reconciliation; opt-in per step | 33 |

### Execution kernel (L7)

| Component | Change | Requirement |
|---|---|---|
| `engine.py` `_execute_impl` `RunSandbox` | The key change: resolve to the chain root with visited-set cycle guard | 1 |
| `engine.py` `run()` `RunTrace(RunSandbox(...))` | Second site built BEFORE `_execute_impl` — must also root-resolve or logs land in a dead directory | 1 |
| `factory.py` `create_runner` | Third site; follows only if root resolution reassigns `ctx.run_id` | 1 |
| `engine.py` step-boundary commit | Engine commits gated on `has_git`, fires before routing decision; NOT on `post_step` | 10, 41 |
| `engine.py` `_fire_hooks` new events | `pre_commit`, `post_commit`, `post_run` — dispatch contract unchanged | 12, 13 |
| `engine.py` `post_run` fire-once finalizer | Called from existing `finally` blocks; second call is no-op | 13 |
| `engine.py` cancel handler | `wip: cancelled at step {id}` commit on `post_run`; never `reset --hard` | 26 |
| `engine.py` `_compose_context_message` | Seam 2 — staged per-workflow removal; brief to agent 1 only; retry block targeted | 30, 40 |
| `fanout.py` `_select_isolation_scope` | Keyed solely on `has_git`; global True reroutes every fan-out to worktrees | 11 |
| `main.py` periodic sweep | Must become chain-aware in the same PR as sandbox re-key | 2 |
| `run_log.py` | `.logs/run-logs.jsonl` changes to `.logs/{run_id}.jsonl` | 24 |
| `engine.py` `resume_run` and `restore_non_terminal_runs` | Dirty-tree reconciliation before re-running an interrupted step | 27 |
| `context.py` | Add `chain_source_run_id` field; add `revision_ordinal` for tag naming | 14, 22 |
| `kernel_services.py` `read_parent_file` | Root-resolve the target; raw id is wrong at chain depth two or deeper | 5 |
| `engine.py` completion seam tagging | Tag on terminal path after final status known; not on a leaf `post_step` | 14 |
| `factory.py` prompt policy selection | Read policy name from manifest; default `"default"` | 29 |
| `skill_staging.py` `skills/` | Exclude from deliverable walk and listing | 9 |

### Runtime and workspace (L8)

| Component | Change | Requirement |
|---|---|---|
| `local.py` `merge_worktree` — SHIP-BLOCKER | False-clean merge: refused merge returns `conflicts: []` then `--abort` destroys prior fragment | 7 |
| `merge/git_3way.py` — SHIP-BLOCKER | Loops merge per fragment with no commit between — other half of the same defect | 7, 25 |
| `local.py` `LocalWorkspace` | `git init` plus initial commit plus seed `.gitignore` plus `create_tag` plus `list_tags` plus ref-scoped read | 6, 7, 8, 15, 16, 17 |
| `sandbox.py` `RunSandbox` | Root key; `has_git`; `commit_all` passthrough; `.git/` and `.gitignore` exclusions; `.chain/` and `.context/` prefixes and writers | 1, 2, 6, 9, 20 |
| `sandbox.py` `sweep_expired` | Matches directory basenames — must become chain-aware | 2 |
| `context_providers/previous_run.py` | Short-circuit redundant seed; root-resolve both call sites; guard reserved prefixes | 4, 5, 21 |
| `context_providers/chain_context.py` (new) | Clone of `previous_run`: declared gate plus `assert_owns` plus file-by-file copy plus graceful degradation | 22 |
| `fanout.py` `_merge_fragments` and `_resolve_conflict` | Four `on_conflict` policies now reachable for the first time | 25 |
| `local.py` `remove_worktree` | Gains `delete_branch: bool = True`; cancel path passes `False` to retain worker branches | 28 |
| `hooks/secret_scan.py` plus commit boundary | Wire `pre_commit` — the hook exists, the trigger does not | 12 |
| `local.py` `changed_since` | No change — already computes what a step touched since a base commit; used by `replaces: true` reconciliation | 33 |
| `runtime/base.py` `Workspace` Protocol | No change — stays shut; three import-linter contracts | 15 |
| `run_files.py` plus `local.py` ref-scoped reads | `git ls-tree -r ref`, `git show ref:path`, in-memory zip; HEAD never moves | 17, 18 |
| `run_files.py` plus `SandboxTab.tsx` restore | Restore is a forward commit; refused while a run is active; browsing stays read-only | 18 |
| `sandbox.py` `.verify/` and `.browser/` per-run paths | Flat today; become `{run_id}` subpath via one run-scoped helper | 24 |

### Prompt assembly (L9)

| Component | Change | Requirement |
|---|---|---|
| `factory.py` policy name | One line: hardcoded `"default"` changes to read from manifest | 29 |
| `capabilities/prompt/policy.py` | Register body-only order and governance order | 29 |
| `factory.py` `_compose_injection` | Template/design-system/craft block removed; they live in `.context/design/` | 29, 23 |
| `prompt_overrides.py` | Deferred; API docstring corrected | 37 |
| `backend/agents/prompts/*/AGENT.md` (94 files) | Real rewrite per migrated workflow: name which paths hold what; reading is the agent's own job | 31, 40 |
| `engine.py` `_compose_context_message` `is_first_agent` | Extend: brief reaches agent 1 only; later agents carry task only | 30 |
| `engine.py` `_compose_context_message` retry block | Keep but retarget: injected into the retrying agent only, not broadcast | 30 |
| `sandbox.py` `write_agent_output` and `agent_output_relpath` | No change — `.agents/{NN}-{agent_id}.md` already written; becomes the agent-to-agent channel | 40 |

---

## Data Models

### `WorkflowRun` changes

```python
class WorkflowRun(Base):
    # Existing, now written for the first time:
    source_run_id: Mapped[str | None]  # migration 0014, was never assigned

    # New nullable column (one additive migration):
    git_tag: Mapped[str | None]        # "a real tag object was created"

    # Optional optimisation (one additive migration, only if walk is slow):
    root_run_id: Mapped[str | None]    # cached chain root
```

`git_tag` means only "a real tag object was created." The displayed `vN` version
number stays driven by `revision_index` from the family walk. Threading the ordinal
on `ExecutionContext` ensures the tag name and the UI number can never disagree.

### `ExecutionContext` new fields

```python
@dataclass
class ExecutionContext:
    # New: chain source (must NOT alias into parent_run_id)
    chain_source_run_id: str | None = None

    # New: revision ordinal threaded at launch for tag naming
    # Never computed inside the engine from DB; set app-side at launch
    revision_ordinal: int = 1
```

### `Step` new fields

```python
@dataclass
class Step:
    # Declared output surface for reconciliation (opt-in, default: accumulate)
    outputs: list[str] = field(default_factory=list)
    replaces: bool = False  # if True: remove tracked paths under outputs not written this pass
```

### New reserved-prefix constants in `sandbox.py`

```python
_CHAIN_PREFIX   = ".chain/"    # chain payload written by engine on post_run
_CONTEXT_PREFIX = ".context/"  # what this run was given, written at sandbox open

_GITIGNORE_PATHS = [
    ".uploads/", ".logs/", ".verify/", ".browser/", ".agents/",
    ".chain/", ".context/", "skills/",
]

_DELIVERABLE_EXCLUDE = {
    "PLANNER.md",   # existing
    ".git",         # new
    ".gitignore",   # new (bare filename)
    "skills",       # new
}
```

### `.chain/{run_id}/` payload shape

```
.chain/
  {run_id}/
    summary.md          engine-rendered: steps, status, tag if created
    {deliverable_file}  copy of the final output under its own filename
    logs/
      {run_id}.jsonl    copy of .logs/{run_id}.jsonl
      {agent_id}.md     copy of .agents/{NN}-{agent_id}.md (one per agent)
```

Written per run, never flat. A flat `.chain/` would be overwritten by the next revision.

### `.context/` shape

```
.context/
  selections.json       wizard choices (from resolve_launch_od_context)
  design/
    design-system.md
    craft.md
    template/
      SKILL.md
      example.html
      {seed_files}
      {reference_files}
  summary.md            source run summary (chained runs only)
  {deliverable_file}    source run final output (chained runs only)
  logs/                 source run logs (chained runs only)
```

---

## Key Algorithms

### Chain-root walk

```python
def resolve_chain_root(run_id: str, db: Session) -> str:
    """Walk parent_run_id to find the chain root.
    Mirrors _compute_root_ids (runs.py:211-260), threat T-A-04.
    Follows parent_run_id ONLY — source_run_id is never followed.
    """
    visited: set[str] = set()
    current = run_id
    while current:
        if current in visited:
            break  # cycle detected — use last seen unique node
        visited.add(current)
        row = db.get(WorkflowRun, current)
        if row is None or row.parent_run_id is None:
            return current
        current = row.parent_run_id
    return current
```

Applied at all seven `RunSandbox` construction sites. The `engine.py run()`
`RunTrace` site is built before `_execute_impl` — it must also root-resolve or
the run log lands in a dead per-revision directory.

### Step-boundary commit

```python
# In engine._execute_impl, after each step strategy returns:
if has_git:
    block = _fire_hooks("pre_commit", step, ectx, staged_diff=_git_staged_diff())
    if not block:
        result = workspace.commit_all(f"step: {step.agent_id}")
        if result == "" and _git_is_repo():
            logger.warning("commit no-op on has_git=True run=%s step=%s",
                           ectx.run_id, step.agent_id)
        _fire_hooks("post_commit", step, ectx, commit_sha=result)
    else:
        ectx.last_commit_blocked = True
```

Fires before the routing decision — backward retry jumps also produce a commit.
Does NOT ride `post_step` (singular, already taken on four shipped manifests).

### `post_run` fire-once finalizer

```python
_post_run_fired: set[str] = set()

def _fire_post_run(run_id: str, ectx: ExecutionContext,
                   workspace: LocalWorkspace) -> None:
    if run_id in _post_run_fired:
        return
    _post_run_fired.add(run_id)
    try:
        if ectx.final_status == "completed":
            workspace.create_tag(f"v{ectx.revision_ordinal}")
            _update_git_tag_column(run_id, f"v{ectx.revision_ordinal}")
        _write_chain_payload(ectx, workspace)
        workspace.git_gc_auto()
        if ectx.final_status in ("cancelled", "failed", "degraded"):
            if workspace.is_dirty():
                workspace.commit_all(
                    f"wip: {ectx.final_status} at step {ectx.last_step_id}")
    except Exception as exc:
        logger.warning("post_run finalizer error run=%s: %s", run_id, exc)
```

Called from the existing `finally` blocks of `_execute_impl` and `run()`. A second
call on the same `run_id` is a no-op — guards against the 8+ terminal early-return
sites in `_execute_impl`.

### Fan-out merge sequence (FR-034 fix)

```python
# In _merge_fragments (fanout.py):
for i, fragment in enumerate(fragments):
    result = workspace.merge_worktree(fragment.branch)
    if result.refused:
        raise MergeRefusedError(fragment.branch)
    if result.conflicts:
        _resolve_conflict(step, fragment, result.conflicts, ectx)
        continue
    # Commit between fragments — this is the fix.
    # Clears MERGE_HEAD so the next fragment can merge cleanly.
    workspace.commit_all(f"merge: fanout/{step.agent_id}/{i}")
```

The existing bug: no commit between fragments means fragment 2 is refused because
`MERGE_HEAD` is still set. The conflict probe finds nothing (merge never ran).
`git merge --abort` destroys fragment 1's work. Both workers reported applied over
an unchanged base tree.

---

## Prompt Assembly Architecture

### Before (Seam 1 and Seam 2 active)

System prompt wraps AGENT.md with 7 blocks: tool_availability, injects
(template/design/craft), guardrails, skills, hooks, constitution, prompt_body.
Human message assembles ~15 blocks: brief, planning_context, upstream agent
outputs pasted in, uploaded file text pasted in, revision context, prototype HTML,
current task, and more.

### After (body-only or governance policy, context from files)

System prompt is the agent's own AGENT.md (bare policy), or guardrails + hooks +
constitution + AGENT.md (governance policy for governed agents). Human message for
agent 1 is the brief plus its task. Human message for agents 2+ is the task only.
Agent 2 reads agent 1's output from `.agents/01-{id}.md`. Retry dispatch carries
the retry block and the brief to the retrying agent only.

### Context-message inventory (30 rows, normative — no blank rows)

| Row | Today injected | After | Requirement |
|---|---|---|---|
| 1 | `tool_availability` block | Dropped — deepagents supplies tool schemas itself | 29 |
| 2 | `injects`: design system, craft, template SKILL.md | `.context/design/` | 23 |
| 3 | `guardrails` | Kept in governance order | 29 |
| 4 | `skills` | Unaffected — deepagents' SKILLS_SYSTEM_PROMPT names staged skills | 29 |
| 5 | `hooks` behavioural-hook block | Kept in governance order | 29 |
| 6 | `constitution` | Kept in governance order | 29 |
| 7 | `prompt_body` | The AGENT.md itself | 29 |
| 8 | Brief (stripped for non-first agents) | Agent 1's message only; chain context in `.context/` | 30 |
| 9 | RETRY pass N of M | Control — stays, targeted at retrying agent | 30 |
| 10 | Planning Context — planner's analysis | PLANNER.md written AFTER clarify merge | 30 |
| 11 | ACTIVE DESIGN SYSTEM, ACTIVE TEMPLATE | `.context/design/` | 23 |
| 12 | Output from upstream agents pasted | `.agents/{NN}-{agent_id}.md` | 40 |
| 13 | PRIOR OUTPUT — agent's previous pass on redo | `.agents/{NN}-{agent_id}-p{visit-1}.md` | 30 |
| 14 | REVISE directive — HITL rejection text | Control — stays, targeted | 30 |
| 15 | REVISION MODE — previous spec and task list | Shared tree: spec.md and tasks.md already present | 40 |
| 16 | USER GUIDANCE — mid-run chat steering | One-shot: targeted; sticky: `.uploads/` txt sidecars | 30 |
| 17 | REVISION ANALYSIS — analyzer's plan | Analyzer artifact on disk plus `.agents/01-...md` | 30 |
| 18 | CURRENT PROTOTYPE HTML plus instruction | Agent reads `prototype.html`; instruction is the brief to agent 1 | 31 |
| 19 | CURRENT TASK — Task N of M | Control — stays, targeted per task | 30 |
| 20 | Build skeleton — compacted current HTML | Worker reads `prototype.html` from the tree | 40 |
| 21 | TEMPLATE COMPLIANCE — ids | Ids in `.context/selections.json`; rule in builder's AGENT.md | 23 |
| 22 | Multimodal image blocks | Unchanged — not a text block; out of scope | — |
| 23 | `resolve_launch_od_context` to `od_context_json` | `.context/` written at sandbox open; `resume_run` reads back | 23 |
| 24 | Frontend `enrichedInput` text block | Retired; `.context/` carries copied `.chain/{run_id}/` | 22 |
| 25 | `previous_run` provider — seed plus file-pointer message | Shared tree; seed short-circuited | 4 |
| 26 | `uploaded_files` provider | `.uploads/` | 23 |
| 27 | `skills/` staging | Unchanged | 9 |
| 28 | Validation fix loop message | Control — unchanged; already uses `read_file` and `edit_file` | 30 |
| 29 | Deep planner `design_context` argument | In-process: receives resolver's result; on resume reads from `.context/` | 23 |
| 30 | Engine-side readers of `ectx.od_context` | In-memory while process lives; `resume_run` rebuilds from `.context/` | 23 |

---

## Error Handling

### `merge_worktree` refused merge (ship-blocker fix)

Today: `CalledProcessError` causes probe of `--diff-filter=U` which returns nothing, so `conflicts=[]` is returned, then `git merge --abort` destroys the prior fragment, and the result is reported as a clean merge.

After fix: `CalledProcessError` is classified as "refused to start" (distinct from "ran and found conflicts"). A refused merge raises `MergeRefusedError` and never produces `conflicts=[]`. `git merge --abort` only runs after classifying the error. The caller then decides whether to abort the run or invoke the `on_conflict` policy.

### `pre_commit` blocked

Block returned means the commit is skipped and the diff stays in the working tree. Later commits re-scan the uncommitted diff. If this was the run's last commit, `ectx.last_commit_blocked` is set to True, the run ends `degraded` (not `completed`), and no tag is created.

### Fan-out cancel mid-merge

Stop pressed during fan-out: the base tree is committed as `wip: cancelled at step {id}`. Each worker gets `remove_worktree(delete_branch=False)`. Worker branches `fanout/{step}/{i}` are RETAINED in git history. The next revision starts from a clean commit.

### Crash or SIGKILL during a step

Backend restarts and `restore_non_terminal_runs()` resumes the interrupted run. Before re-running the step, `git status --porcelain` is checked. If the tree is non-empty, `commit_all("wip: recovered dirty tree at step {id}")` runs (subject to `pre_commit`). The step re-runs on a clean tree and the re-run commit contains none of the crash leftovers.

### Chain payload source swept or missing

The `chain_context` provider reads `chain_root/.chain/{source_run_id}/`. If the path exists, files are copied file-by-file to the receiving sandbox `.context/`. If the path is missing, TTL-swept, or raises a permission error, the provider degrades gracefully to an empty chain payload and the run continues.

---

## Invariant Compliance

| Invariant | Mechanism | Status |
|---|---|---|
| INV-1 — Kernel workflow-agnostic | Every gate is a generic `ctx` field or declared manifest flag. `_extract_chain_context` hardcodes 7 branches but lives in the API layer, not the kernel. | Pass |
| SC-001 — Zero engine edits for a new workflow | The commit is one engine call gated on `has_git`; `pre_commit`, `post_commit`, `post_run` are hooks a manifest declares by name in `Step.hooks`. Custom workflow behaviour is manifest-driven. | Pass |
| Workspace port stays shut | `create_tag`, `list_tags`, ref-scoped read land on `LocalWorkspace` via `getattr` duck-typing. Three import-linter contracts stay green. | Pass |
| Migrations are additive only | One nullable `git_tag` column; optional `root_run_id`. `source_run_id` needs no migration. No column removed or renamed. | Pass |
| INV-3 — byte-identical goldens | New reserved prefixes are dormant on golden runs. Three revision characterization goldens need deliberate re-baselining once the sandbox holds accumulated files — expected and blessed. | Pass with known re-baseline |

---

## Testing Strategy

### Ship-blocker tests (must pass before `has_git=True`)

Two fan-out workers writing disjoint files: both files present in the base tree after merge. Today neither appears. (Requirement 7)

A refused merge is reported as a failure — never as `conflicts=[]`. (Requirement 7)

`git init` is idempotent — calling it twice does not error. (Requirement 6)

A fan-out on step 1 (before any boundary commit) merges into the initial commit without "unborn HEAD". (Requirement 6)

### Git foundation tests

`git show --stat HEAD` after a completed run contains none of the 8 gitignored paths. (Requirements 8, 44)

Sandbox listing contains neither `.git/` nor `.gitignore` nor `skills/`. (Requirements 9, 44)

A `pre_commit` block causes the run to end `degraded` and untagged. (Requirement 12)

`post_commit` fires only after a commit landed. (Requirement 12)

A routing step produces a commit before the gate outcome is consumed. (Requirement 10)

All four `on_conflict` policies are exercised — they have never been reachable in production. (Requirement 25)

### Sandbox identity tests

A revision writes into the same directory as its parent; Workspace, Files, and Preview tabs all render that directory. (Requirement 43)

A revision held open past TTL, whose parent is already terminal, is NOT swept. (Requirement 2)

The second `create_revision` against an already-active parent fails fast. (Requirement 3)

### Versioning tests

A completed run carries a tag; a diverted or failed run carries none. (Requirement 14)

Tag name `vN` matches `revision_index` the UI shows. (Requirement 32)

Selecting v1 in the dropdown renders that tag's ref-scoped file tree read-only. (Requirement 17)

Opening v1 while v3 is running does not modify the working tree. (Requirement 18)

### Chaining tests

A chained run renders the "(Chained)" lineage indicator. (Requirement 22)

Chaining from a mid-family revision (not the root) produces a non-empty payload. A root-only test would pass while the majority case is broken. (Requirement 5)

A chained run whose source was swept still completes. (Requirement 22)

### Prompt migration tests

A migrated workflow's agent receives a system prompt byte-identical to its `AGENT.md`. (Requirement 29)

A workflow still on the `default` policy is byte-identical to today. (Requirement 29)

Only the first agent receives the user's brief; agent 2 does not. (Requirement 30)

Agent 2 reaches agent 1's output by reading `.agents/01-{agent_id}.md` and the run still produces its deliverable. (Requirement 40)

A governed agent does NOT silently lose its Constitution when its workflow migrates. (Requirement 29)

A conditional-gate retry loop still tells the agent why it was sent back, and only that agent receives it. (Requirement 30)

### Safety tests

`post_run` fires exactly once per terminal run for success, failure, cancel, and divert. (Requirement 13)

A cancelled run leaves a `wip:` commit and a clean tree; the next revision commits none of the abandoned work. (Requirement 26)

A run killed mid-step and resumed leaves a `wip: recovered dirty tree` commit before the step re-runs. (Requirement 27)

`git status --porcelain tests/agents/characterization/golden/` shows only intentionally re-baselined files after any change. (Requirement 45)

### SC-001 and INV-1 CI checks

`grep -rn "if pipeline_type ==" backend/agents/execution_engine/` must return 0 matches.

`grep -rn 'spec.id ==' backend/agents/execution_engine/` must return 0 matches.

All 11 `test_banned_patterns.py` tests must stay green. (Requirement 34)
