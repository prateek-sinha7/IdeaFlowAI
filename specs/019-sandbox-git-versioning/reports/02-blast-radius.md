# Blast radius — per layer, per item

Spec 019 · companion to [`01-layers.md`](01-layers.md)
Analysed against `feat/git-versioning` @ `15d3d6535`, main checkout.

`layers.md` says *what changes*. This says *what else moves when it does* — callers, tests,
persisted shapes, byte-pinned fixtures, invariant contracts, and the things that break in
production rather than in CI.

Severity is **blast**, not effort: how far a mistake propagates and how loudly it fails.
`silent` in the failure column is the important one — those are the changes that pass QA.

> **Read this first.** Two of the risks below are not risks of *this change* — they are live defects in
> already-shipped code, reproduced against real git, that this change would expose. A fan-out step with
> two worktree workers currently loses every worker's output and reports success; a freshly
> `git init`-ed sandbox hits the same false-clean path on its first merge. They sit dormant only because
> no artifact sandbox has ever had `has_git=True`. See the L8 rows and FR-034 / FR-006.

Rows are **grouped where the risk is shared**, so this is not a 1:1 mirror of `layers.md`'s item
tables. Several R9 items — the policy order, `_compose_injection`, the context providers,
`_seed_workflow_context`, `_compose_input_blocks` — collapse into the two seams they belong to, because
their blast radius is identical and repeating it per symbol would obscure rather than inform.

---

## L1 — Frontend composer

| item | radius | tests | failure mode |
|---|---|---|---|
| `DashboardLayout` chain assembly (R8) | The only producer of `enrichedInput`. `frontend/src/lib/runInput.ts` `parseRunInput` is the single canonical parser of this marker family; the engine's `is_first_agent` split keys on the same marker. Change the producer without the parser and the marker survives into every downstream agent. | no dedicated test found for the assembly path | **silent** — agent B gets the same context twice, in two formats, which diverge after the next edit to only one path |
| Client-side type fallback (R8) | `workflowType === "ppt" \|\| "prototype"` at two sites. Not INV-1 (frontend), but it means a custom workflow's chain fallback is wrong by construction. | — | degraded content, no error |
| `LaunchWizard` chain threading (R7) | none — `source_run_id` already flows | — | — |

---

## L2 — Frontend run surface

| item | radius | tests | failure mode |
|---|---|---|---|
| `SandboxTab` under a re-keyed sandbox (R1) | Every file-serving route the tab uses. If L4 and L7 do not land together, Workspace, Files **and** Preview all render empty for every revision. | `SandboxTab.test.tsx`, `SandboxTab.runs.test.tsx`, `SandboxTab.readOnlyIndicator.test.tsx` — all render with a bare `runId`, none exercise a chain root | **loud** in the UI, invisible in CI |
| `.chain/` section (R6) | Self-contained; mirrors the existing `.agents/` and `.verify/` grouping. Note `.verify/`, `.browser/`, `.agents/` are all **listed** today — only `.uploads/` and `.logs/` are hidden. | none found for prefix grouping — add one | cosmetic |
| The **shipped** "Version ▾" picker (R1) | It works today by handing the selected member's own run id to `SandboxTab`. Root-key the `run_files.py` endpoints and v1 and v3 resolve to the same directory, rendering identical accumulated content. A live, currently-correct feature breaks for every chain created after that change and stays broken until ref-scoped reads land phases later. | `RunHeader.test.tsx`, PreviewPanel version-family tests — none assert *different* content per version | **silent regression of shipped behaviour**, in the phase gap |
| Version props (R5) | Under reading (a) this reuses live, actively-patched plumbing with a long bug history: ISS-065/087/215/230/286/294/296/386, FIX-053/062/087/088/118/328/411/412/422/450. That history is the risk, not the code. | `RunHeader.test.tsx`, PreviewPanel version-family tests | regression in an area already fixed ten times |
| `.git/` in the listing (R2) | Workspace tab renders thousands of loose git objects. | — | **loud**, immediately |
| Tagged badge (R3) | Additive next to an existing chip. | `RunDetailPage.test.tsx` | cosmetic |
| Input-prompt viewer (R9) | `AgentThinkingTab`, `AgentDetailPanel`, `WorkflowHistory`, `PreviewPanel` all consume `inputPrompt`. No code breaks — the panel just goes near-empty. | — | **silent product regression**: a transparency feature quietly stops showing anything |

---

## L3 — Frontend data

| item | radius | tests | failure mode |
|---|---|---|---|
| `ref` param on 4 sandbox functions (R5b) | Every call site must decide what ref to pass. Default `none` = working tree, so omission is safe. | any test mocking `getRunSandbox*` | safe by default |
| `git_tag` on `FamilyMember` (R3) | Optional additive field, no SSE change. | `api.getRunFamily.test.ts` | none |
| `inputPrompt` (R9) | Pass-through only — no other frontend file references `context_message`. | — | see L2 |

---

## L4 — API routes

| item | radius | tests | failure mode |
|---|---|---|---|
| **Four** `RunSandbox(...)` sites in `run_files.py` (R1) | upload, list, zip, read — each independent, each outside the engine path. All four must resolve the same key. | `test_rest_revisions.py`, `test_run_sandbox_api.py` — neither covers a re-keyed sandbox | **silent** per-route: miss one and that route alone serves an empty directory |
| `_extract_chain_context` (R8) | Seven hardcoded `pipeline_type` branches decide extraction for every built-in. Generalising changes chain-context **content** for ppt, user_stories, prototype, app_builder, mulesoft, dotnet — a behaviour change, not additive. The FE parser is marker-based and content-agnostic, so it tolerates it. | `test_runs_api.py` covers chain_context — extend, do not replace | changed content for six shipped workflows |
| `resolve_launch_od_context` (R9) | Feeds `od_context_json`, which `resume_run` depends on. Removing the call cascades into L5. | `test_run_pipeline_validation.py` | **silent** — only shows up on restart |
| `source_run_id` write (R7) | Writing a column that has been dead since migration 0014. Fixes the non-functional "(Chained)" indicator as a side effect. | `test_migration_0014.py` asserts the column exists; add one asserting it is populated | none — strictly additive behaviour |
| Ref-scoped reads (R5b) | Reuse `authz.py`'s existing `assert_repo_owned` rather than inventing authz. Reads of an arbitrary ref are a new authz surface. | `test_sandbox_deliverable.py` pins the no-ref default | authz gap if reinvented |
| `.chain/` single-file read gate (R6) | Today `.agents/*` and `.verify/*` **are** individually readable through the single-file endpoint — only `.uploads/` and `.logs/` are blocked. Decide deliberately which tier `.chain/` joins. | — | information exposure if wrong |
| `FamilyMemberResponse` `git_tag` (R3) | Additive optional field on a shipped response model; the TS `FamilyMember` counterpart is the L3 row. | family/summary response-shape tests | none |
| `GET /s/{token}` public share (R2, R6) | **Unauthenticated** route. It serves only the `WorkflowRun.output` column and never touches the filesystem — so it adds no new exposure *by itself*. But `output` is what the deliverable walk produces, so the FR-008 `.git/` and FR-017 `.chain/` exclusions are the only thing standing between a leaked prefix and a public URL. | — | **silent, and public**, if an exclusion is missed |

---

## L5 — Persistence

| item | radius | tests | failure mode |
|---|---|---|---|
| Chain-root key (R1) | Walk = zero migration, O(depth) DB reads at every sandbox resolution — including the four `run_files.py` sites, so it is on the hot path for the Workspace tab. Column = O(1), one additive nullable field, plus a backfill decision for existing rows. | `test_alembic.py` if the column route is taken | walk: latency; column: NULL for every pre-existing run |
| `git_tag` column (R3) | Nullable additive, existing rows stay NULL. | `test_alembic.py` | none |
| `od_context_json` (R9) | `resume_run` rebuilds `ExecutionContext` from this column after a restart. Orphan it and an in-flight OD run resumes with different context than its earlier steps used — output silently inconsistent within one run. | `test_resumability.py`, `test_run_pipeline_validation.py` | **silent**, and only under restart |
| `source_run_id` (R7) | Already exposed on the response schema, so the frontend contract does not move. | `test_migration_0014.py` | none |
| `ARTIFACT_KINDS` (R6) | `summary` and `deliverable` are already recognised kinds; `kind` is a free string. A `.chain/summary.md` persisted as `kind="summary"` needs zero migration. | — | none |

---

## L6 — Compiler

| item | radius | tests | failure mode |
|---|---|---|---|
| New hook events `pre_commit` / `post_commit` / `post_run` (R2, R3; FR-060, FR-061) | No compiler change. `Step.hooks` and its registry validation already ship; a hook name typo fails at compile time, loudly. The commit itself is an engine call, so nothing is registered for it — `post_step` is singular and already taken on the revision workflows. | `test_manifest.py`, `test_conditional_route_compiler.py` | loud |
| Declared chain flag (R7) | Additive field mirroring `revises_existing`. The risk is the **gate**: `previous_run.py` was deliberately hardened (WR-06) to fire on the declared flag, never on raw id presence, so "a forward build carrying a stray parent_run_id can no longer trigger an unintended cross-run seed". Repeating that mistake for chains reopens the same class. | compiler manifest→CompiledWorkflow tests | **silent cross-run data leak** |
| `git` permission binding (R4) | `permission_caps.py` is the single authority — its docstring says nothing outside it may widen a permission. Flipping `git=False` changes the cap table every workflow inherits, built-in and custom. | permission-cap tests | broad, but loud |
| `context_providers` threading (R9) | Drives both the run-entry seed loop and the per-agent provider loop. Two independent manifest knobs vanish if removed: workflow-level `context_providers` and agent-level `injects`. | `test_loader.py`, `test_manifest_coverage.py`, `test_workflow_resolver.py` | capability loss for custom workflows |

---

## L7 — Kernel

| item | radius | tests | failure mode |
|---|---|---|---|
| Sandbox key (R1) | Small in itself. Its radius is everything downstream that assumed `1 run == 1 directory`. | three byte-pinned characterization tests: `test_characterization_prototype_revision` / `_large_` / `_feature_` — these pin **end-to-end revision output** and will likely need re-baselining once the sandbox holds accumulated prior-revision files instead of a freshly seeded set | re-baseline cost, plus the sweep race below |
| TTL sweep protected set (R1) | `protected_run_ids` is built from run ids; `sweep_expired` matches directory **basenames**. Root-named directory + terminal parent + live child = unprotected live directory. | none — add a sweep-during-active-revision test | **silent, delayed, production-only.** Will not reproduce in a demo. Fires the first time someone leaves a gated revision open overnight |
| Fan-out isolation scope (R2) | `_select_isolation_scope` derives worktree-vs-sub_sandbox **solely** from `has_git`, with an explicit comment that it is never manifest-driven. Global `has_git=True` reroutes **every** fan-out step in **every** workflow from `sub_sandbox` + `copy_disjoint` to `worktree` + `git_3way` — and `allocate_worktree` needs a real `.git` that nothing creates. | `test_isolation.py` pins the current selection | **silent** until a parallel workflow merges wrong |
| `.logs/run-logs.jsonl` under a shared root (R1, R6) | `RunLog` writes a **fixed** filename in append mode. Share the directory and every revision's trace merges into one file — and `agent_chunk`, `agent_thinking`, `tool_call`, `tool_result` carry only `agent_id`, no run id, so the lines cannot be separated afterwards. Q3's "point at the logs" then points at a merged file. | none | **silent**: debugging degrades exactly when a chain gets long |
| `_compose_context_message`, `_seed_workflow_context`, `_compose_input_blocks` (R9) | Every agent dispatch in every workflow. ~15 blocks, each with an in-code INV-1/INV-3/SC-001 justification — which is what makes per-block diffing tractable. Grouped: one seam, one radius. | `test_execution_engine.py`, `test_skill_prompt_baseline.py`, the `test_phase3_*` / `phase5` / `phase6` / `phase8` family | widest radius in the set |
| `has_git` provenance (R2) | Manifest-declared confines the radius to opting-in workflows and makes revert a config change. A global default puts every workflow on worktrees at once, and `allocate_worktree` needs a `.git` only the new init creates. | `test_isolation.py` | see fan-out row below |
| Step-boundary commit on a routing pass (R2, R3) | The commit is engine-driven and fires before the routing decision consumes the gate outcome, so `if _routed: … continue` (which skips only the `post_step` capability) cannot drop it. Had the commit ridden `post_step`, every retry-loop backward jump would have lost its commit silently. | none — add one asserting a commit lands on a routing pass | **silent**: history simply has a hole, if the ordering regresses |
| `resume_run` (R9) | Recomposes context live per step rather than replaying a stored message. It does **not** store a context-message override — the real dependency is `od_context_json`. | `test_phase8_resume.py`, `test_resumability.py` | see L5 |
| Completion-seam chain-payload writer (R6) | Best-effort, never-raising, placed after `final_output` resolves and after run-log writes settle. Same contract as the budget-snapshot persist beside it. | `test_execution_engine.py` | contained by design |
| `chain_source_run_id` ctx field (R7) | Additive field mirroring `parent_run_id`. Must **not** alias into `parent_run_id` — KAN-116 deliberately keeps chained runs out of the revision family, and the family walk BFS has no type filter. | — | **silent**: chained runs appear as revisions of the source workflow |

---

## L8 — Runtime and workspace

| item | radius | tests | failure mode |
|---|---|---|---|
| Missing `git init` (R2) | `commit_all` runs `git add -A` then `git commit`; with no `.git` the `CalledProcessError` is caught and `""` returned. "Nothing to commit" and "not a git repo" are **indistinguishable** today. | new: init idempotency | **silent forever** — the entire feature does nothing and reports success |
| `.gitignore` seeding (R2) | Without it `git add -A` commits `.uploads/` owner-uploaded documents, `.logs/` engine traces, `.verify/` evidence, `.browser/` screenshots and `.agents/` transcripts into permanent history — files explicitly designed not to be part of the deliverable. | one assertion that `git show --stat HEAD` never contains a reserved prefix catches the whole class | **silent privacy leak**, discovered when someone reads a git log or downloads a zip |
| `.git/` exclusion (R2) | Two **separate** lists: the deliverable walk and `list_files`. They are not the same list and the analyses initially conflated them. `serialize_sandbox_deliverable` and `count_sandbox_deliverables` both route through the deliverable helper, so one change covers both — but `list_files` is independent. | `test_sandbox_deliverable.py` is the byte-oracle | deliverable corruption, or a git-object-filled UI |
| `RunSandbox` key + `sweep_expired` (R1) | See L7. | `test_run_sandbox_api.py` | as L7 |
| Concurrent revisions (R1) | **No lock exists.** `create_revision` mints a child with no check for an existing active child on the same parent; `active_revision_run_id` is read-only Concierge status, not a lock. Two revisions on one shared directory interleave writes. The proposed `allocate_worktree` reuse is contingent on R2 landing, because worktrees need a real git base. | new: concurrent-revision test | **silent corruption**, passes single-user QA every time |
| `create_tag` / `list_tags` (R3, R5b) | Added to `LocalWorkspace` and reached by `getattr` duck-typing, exactly as `commit_all` and `allocate_worktree` already are. The `Workspace` Protocol stays untouched, so the three import-linter contracts stay green. Adding them **to the Protocol** would be the actual violation. | new unit tests against a git fixture | port widening if done the obvious way |
| `merge_worktree` false-clean (R2) | **Live defect.** Fragment 1 merges and leaves `MERGE_HEAD`; fragment 2's merge is refused; the conflict probe finds nothing, so `conflicts` stays `[]`; `git merge --abort` then discards fragment 1 too. Both branches are reported applied and the base tree is untouched. Radius = every fan-out step of every workflow that gets `has_git=True`. | `test_isolation.py` covers scope selection, **not** merge outcome | **silent total data loss, reported as success** — the worst failure mode in the document set |
| `git init` with unborn HEAD (R2) | **Live defect, same handler.** `git merge --no-ff` into an empty head fails; the same probe returns nothing; the same false-clean is reported. Reachable on the *first* fan-out of every freshly provisioned sandbox, because a fan-out on step 1 precedes every step-boundary commit — which is why FR-006 seeds an initial commit at `git init`. | none | **silent**, and it is the default state |
| Secret scanning (R2, R6) | `secret_scan` binds to `pre_commit`, which **fires nowhere** in the backend. The only live hook seam is the deliverable write, gated on a step declaring hooks; no manifest declares it. `commit_all` is a raw `git add -A` with no dispatch, and the chain-payload writer calls `sandbox.write()` directly. Git history is immutable, so a secret deleted in a later step stays in `git log -p` forever; a chain payload carries one across a workflow boundary. | none | **silent and permanent** |
| `skills/` staging dir (R2) | `stage_skills` **prunes and rewrites** `<sandbox>/skills/` on every invocation — stale skill directories are pruned and changed ones rewritten; it does not wipe the tree. It is in no exclusion list — not the deliverable walk, not `list_files`, and it would not be in a five-prefix `.gitignore`. Un-ignored, every prune-restage cycle retains another copy of the user's skill bodies in permanent history. It is *also* already a deliverable member today, which is a pre-existing gap this work should close deliberately rather than by accident. | `test_sandbox_deliverable.py` | **silent**, and it compounds per step |
| No delete path out of the sandbox (R1) | `serialize_sandbox_deliverable` walks the whole root every call, with no "only this revision" notion, and there is no `delete_file` on the agent surface. A rename or restructure in revision 3 leaves the old files in every later deliverable forever. | `test_sandbox_deliverable.py` | **silent, and it grows** — the deliverable degrades a little with every revision |
| `_CHAIN_PREFIX` (R6) | Additive constant plus exclusion sites. Golden runs write nothing under a new prefix, so the byte-oracle needs **new cases, not re-pinning**. One doc correction: `sandbox.py` currently states `.agents/` is the *only* listed-but-undelivered prefix — that stops being true. | `test_sandbox_deliverable.py`, modelled on the existing `.logs/` and `.agents/` blocks | contained |
| `read_chain_source_file` (R7) | Reuses `read_parent_file`'s exact primitive — `RunSandbox(disk_principal, other_run_id).read(name)` — with `ScopedStore.assert_owns` fail-closed before any read. No recursive-copy primitive exists on `RunSandbox`; prefer the proven file-by-file `.uploads/` loop over inventing one with its own traversal and size-cap engineering. | `test_parent_run_ownership.py` is the ownership ratchet — add a sibling case | authz regression if `assert_owns` is skipped |

---

## L9 — Prompt assembly

| item | radius | tests | failure mode |
|---|---|---|---|
| Policy name resolution (R9) | One line. Existing workflows keep `default`, so composition stays byte-identical and the characterization snapshots hold. This is the cheapest correct entry point into R9. | `test_skill_prompt_baseline.py` | contained |
| `_compose_context_message` blocks (R9) | See L7 — this is where the real triage lives. | as L7 | as L7 |
| 94 `AGENT.md` files (R4) | Mechanical and additive. | `test_prompt_contracts.py` | low |
| Per-user override shadowing (R4) | The override **replaces** `prompt_body` wholesale. Every user who has ever saved a `PROMPT_OVERRIDE.md` for an agent silently keeps their old text and never receives the new git/tag/chain instructions. The prompt API's own docstring claims the override is "injected ahead of" the base body — that is wrong about the code. | — | **silent per-user divergence**, invisible to everyone including the user |
| `previous_run` reserved-prefix guard (R6) | `.chain/` cannot leak into a child today: the seed is an ownership-gated, per-file **allowlist**, not a directory copy. The risk is a future manifest naming a `.chain/*` path in `seed_files.from_run`. One defensive guard closes it. | `test_context_providers.py`, `test_revision_gating.py` | future-mistake risk, not a current one |
| Redundant seeding after R1 | Once the directory is shared, the seed loop re-copies files that are already correct. Harmless alone; hazardous if a second concurrent revision's seed overwrites the first's edits. | `test_context_providers.py`, `test_spec_revision_context.py` | wasted IO, or stale overwrite under concurrency |
| New `chain_context` provider (R7, R8) | Clone of a proven pattern. The only real risk is the gate — declared flag, never raw id presence. | new, mirroring `test_parent_run_ownership.py` | as L6 |

---

## Cross-cutting — the radius no single layer owns

These fall between requirements. None of the nine per-requirement analyses covered them;
they came out of the completeness pass and are listed here because they are where this
feature set is most likely to fail after it ships.

**1 · Disk growth has no ceiling.** There is no quota constant anywhere in `sandbox.py` or
`core/config.py` — verified. R1 makes a whole revision chain accumulate in one directory
*by design*, and R2 layers git history on top so every superseded blob is retained forever.
Nothing in the codebase bounds this. This is the most concrete unbounded-growth risk in the
set and it appears in no layer table because it belongs to all of them.

**2 · Crash consistency during a commit.** `run_shutdown.py` deliberately leaves pipeline
drivers running (`SHUTDOWN_STOP_RUNS` off in prod) so the row stays `running` for resume.
A SIGKILL between `git add` and `git commit` leaves a dirty tree — on a directory that,
after R1, two revisions may share. R2 + R1 + resume have never been considered together.

**3 · Gate pauses versus the TTL sweeper.** A human gate can hold a run for hours or days.
The sweeper is wall-clock and keyed on run status. Today a non-terminal gated run is protected;
after R1 the *directory* is named for a root whose own status may already be terminal. The
sweep fix must be chain-aware **and** gate-aware, not just chain-aware.

**4 · Budget and terminal status.** `budget.py` and `WorkflowRun.budget_snapshot_json` exist
and were mentioned by none of the nine analyses. Does a revision chain share or reset budget
accounting? Does R3 tag a run that hit budget exhaustion? `TERMINAL_RUN_STATUSES` includes
`diverted` — a mid-run HITL divert. Tag gating should reuse that constant and decide
`diverted → no tag` explicitly rather than inventing a status check.

**5 · Entitlements.** Entitlement checks exist across `auth.py`, `admin.py`, `settings.py`,
`run_commands.py`, `user_workflows.py` and `registry.py`. Nothing establishes whether
git-enabled sandboxes, tagging or chaining are tier-gated. Free-tier users getting git history
and unbounded retained sandboxes for free is a cost leak nobody has priced.

**6 · Export paths beyond the Workspace tab.** `.chain/` and `.git/` exclusions were traced
through `run_files.py`'s routes. Any *other* consumer of the deliverable walk — download
buttons, share links, the `serialized_sandbox` resolver — must move in lockstep, or a
"download deliverable" quietly ships git history or another run's copied chain payload.

**7 · Observability.** `subagent_run`, `wave_run` and `exec_runs` tables exist; none of the
analyses opened them. Adding git commits, chain-payload copies and chain-source links without
corresponding audit rows leaves a blind spot for whoever debugs this in production.

---

## The most likely production failures

Ranked by *likelihood × silence*, with the cheapest guard for each. The first is new in rev 3 and
outranks everything that was previously here, because it needs no unlucky timing at all — it fires on
the first parallel step of the first git-enabled workflow.

**0 · A fan-out step silently discards every worker's output and reports success.** Not a risk of this
change; a live defect this change wakes. Reproduced against real git: two worktree workers, disjoint
files, both reported applied, base tree unchanged. Add `git init`'s unborn HEAD and the same handler
launders that failure too.
→ *Guard:* fix `merge_worktree` before any workflow gets `has_git=True` — commit the base between
fragments, and make a refused merge a first-class failure instead of `conflicts: []`. Acceptance test:
two workers writing disjoint files leave both files present.

**1 · The sweeper deletes a live shared sandbox.** Mechanism verified end to end. Will not
appear in testing — nobody leaves a revision open past the TTL in a demo. It appears the first
time a real user gates a revision overnight.
→ *Guard:* fix the protected-set query to walk the parent chain **in the same change as R1**.
Never a follow-up.

**2 · Reserved prefixes land in git history.** `git add -A` on a sandbox with no seeded
`.gitignore` commits uploaded documents and agent transcripts permanently. Invisible until
someone reads a log or opens a zip. The list is **seven** paths, not five: the five existing prefixes,
plus `.chain/` — which this spec introduces and which the *next* revision's `git add -A` would sweep
up under a shared sandbox — plus `skills/`, which is wiped and rewritten every step.
→ *Guard:* seed `.gitignore` inside the same `git init` call, plus one test asserting
`git show --stat HEAD` never contains any of the seven. One assertion, whole class.

**3 · Two concurrent revisions corrupt a shared directory.** No lock exists; the proposed
worktree fix is unverified against `has_git=False` bases and depends on R2.
→ *Guard, shippable before the real fix:* an advisory lock or `SELECT … FOR UPDATE` on the
parent row at mint time, so a second concurrent revision fails fast with "a revision is
already in progress" instead of silently racing. A few lines, and it buys time to build
worktree isolation properly.
