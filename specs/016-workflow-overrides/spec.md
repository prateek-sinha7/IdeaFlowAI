# Feature Specification: User overrides of built-in workflows

**Spec ID**: 016-workflow-overrides
**Created**: 2026-08-25
**Status**: Implemented — written retroactively against what shipped; §7 records what validation actually covered
**Root**: `backend/app/api/`, `backend/agents/execution_engine/`, `frontend/src/components/workflow/`
**Grounding**: ADR-0020 (three `LaunchSource` shapes), `agents/workflows/compiler.py` trust model, `specs/012-per-agent-skills-custom-agents` (the composer's saved-workflow row this reuses).

---

## Clarifications

### Session 2026-08-25

- Q: Should an override store the whole manifest, or only the steps? → A: **Steps only.** A full
  manifest cannot compile for `ppt`: `WorkflowCompiler._check_trust` rejects any capability not
  registered `user_allowed=True`, and both `deliverable/ppt` and `context_provider/opendesign`
  lack that flag (`registry.is_user_allowed` defaults to False). Overlaying only `steps` sidesteps
  the trust wall without making any capability user-grantable.
- Q: Does this need a fourth `LaunchSource`? → A: No, and it must not have one — ADR-0020 locks the
  set at three. An override stays inside `FILE_PIPELINE`: the file manifest still supplies the plan,
  only `steps` is overlaid, exactly as `_apply_selections` already overlays per-step levers.
- Q: Where does the user turn an override on and off? → A: A "Use my version" checkbox in the
  Advanced agents panel, bound to a persisted `override_enabled` flag — not a view-only toggle, or
  the screen could show one plan while the launch executed another.
- Q: Can an override contain a user-authored blank agent? → A: **No.** The blank `custom-agent`
  template mints a dynamic `custom-agent:<instance_id>` id that has no `AGENT.md` on disk and is
  absent from the static roster `allowed_custom_agent_ids` builds, so the launch rejects it with
  `invalid_agent_ids`. Confirmed live: such an override saved, rendered, and 400'd on every launch.
  An override may only reuse agents that exist as files. The template stays on the composer canvas.

---

## 1. Problem

A built-in workflow is fixed. `ppt` always runs its three agents, `user_stories` always runs its
six, in the order the file manifest declares. A user who wants their own research step in front of
the deck pipeline, or a different model on one step, has exactly one option today: "Save workflow",
which forks an **unrelated** saved workflow under a new name. The built-in is untouched, so the
next time they click **Pitch an idea** from the home grid they get the stock pipeline again, and
their edited version is somewhere in a list of saved workflows under a name they have to remember.

That is the wrong shape for the actual intent, which is not "make me a new workflow" but "this is
how *I* run this one". The fork also drifts: the built-in gets improved in a later release, the
fork does not.

## 2. What it does

**A user can bind their own step list to a built-in workflow, and from then on opening that
workflow shows and runs their version — with a checkbox to flip back to the original.**

The binding is per user and per built-in: one override row per `(user, pipeline)`, enforced by a
partial unique index. Saving again updates that row rather than creating a second one.

Crucially, **only the steps are the user's**. Every workflow-level field — the deliverable, the
context providers, the planner flag, the clarify config, seed files, limits — always comes from the
file manifest, on every run, override or not. A user cannot change what a `ppt` run delivers; they
can change which agents produce it.

## 3. User Scenarios & Testing *(mandatory)*

### Primary user story

A user opens **Pitch an idea**, expands **Advanced**, adds a research agent before the first deck
agent, and clicks **Save as my version**. Every subsequent time they open that workflow — new
session, new tab, fresh page load — Advanced shows four agents with theirs first, and a run
executes those four. Unticking **Use my version** restores the stock three, immediately and for
runs as well as for the display.

### Acceptance scenarios

1. **Save and reopen.** Given a user with no override, when they edit the lineup in Advanced and
   save as their version, then reloading the workflow page shows their lineup and `is_overridden`
   is true.
2. **Toggle both ways.** Given an enabled override, when the user unticks the box, then the panel
   shows the file's steps; when they re-tick it, the panel shows theirs again — and the persisted
   flag matches on both transitions.
3. **The run follows the toggle.** Given an enabled override, when the user launches, then the run
   executes the override's steps, and the roster reported alongside the run matches those steps.
4. **Workflow-level fields are immune.** Given an override on `ppt`, when the run completes, then
   the deliverable is still resolved by the file manifest's `ppt` strategy to `presentation.pptx`.
5. **Re-saving updates one row.** Given an existing override, when the user saves again, then the
   same row id is returned and no second row exists for that `(user, pipeline)`.
6. **No override changes nothing.** Given a user who never saved one, when they open or run any
   built-in, then behaviour is byte-identical to before this feature — the one difference being a
   single extra authenticated GET on the workflow screen.

### Edge cases

- **Another user's override is invisible.** Resolution filters on `user_id`; a second user opening
  the same built-in sees the file version.
- **A malformed stored row is ignored, not fatal.** A NULL/non-dict `manifest_json`, a missing or
  empty `steps`, or a non-mapping step entry makes the merge return the base plan unchanged and log
  a warning. The run proceeds on the file plan rather than failing.
- **A not-user-allowed capability is refused.** A stored row declaring `approval` or `security`
  fails the `trust="db"` compile; the run falls back to the file plan.
- **Appending a step to a last-streamed workflow would replace its deliverable** — see FR-011.

## 4. Requirements *(mandatory)*

### Functional Requirements

- **FR-001** — A user MUST be able to bind a step list to a built-in workflow, stored as a row
  carrying `overrides_pipeline_type`, `override_enabled`, and `base_version`.
- **FR-002** — At most ONE override row may exist per `(user_id, overrides_pipeline_type)`,
  enforced by a partial unique index (NULL `overrides_pipeline_type` rows are unconstrained, so
  ordinary saved workflows are unaffected).
- **FR-003** — Saving an override for a pipeline that already has one MUST update that row
  (upsert), not create a second or fail on a duplicate-name check.
- **FR-004** — `GET /api/workflows/{id}` MUST serve the caller's enabled override's steps and
  report `is_overridden`, `has_override`, `override_id`; `?original=true` MUST force the file
  projection while still reporting `has_override` so the toggle renders correctly.
- **FR-005** — A launch MUST resolve the caller's enabled override and execute its steps, setting
  BOTH the compiled plan and the reported roster — never one without the other.
- **FR-006** — Every workflow-level field (deliverable, context_providers, planner, clarify,
  seed_files, limits) MUST come from the file manifest on every run, regardless of override.
- **FR-007** — The override merge MUST NOT mutate the cached `CompiledWorkflow`.
  `compile_for_run` is `@lru_cache`'d and its return value is shared process-wide across every
  user and run; the merge MUST use `dataclasses.replace`.
- **FR-008** — An override MUST stay inside `LaunchSource.FILE_PIPELINE`. No fourth shape
  (ADR-0020).
- **FR-009** — Resolution MUST be owner-scoped on every path (read, launch, toggle).
- **FR-010** — An override MUST only reference agents that exist as files. The blank `custom-agent`
  template MUST NOT be offered when authoring one.
- **FR-011** — Where a workflow's declared deliverable is last-streamed (`ppt`, `streamed_text`),
  the UI MUST NOT offer an append-after-final-step slot: the last step's output *is* the
  deliverable, so appending silently replaces it. Sandbox-readback deliverables (`single_file`,
  `serialized_sandbox`) are unaffected and keep the slot.
- **FR-012** — The override affordance MUST be available on every user-launchable built-in, not
  only those routed through one particular launch component.
- **FR-013** — A canvas insert affordance MUST insert at the slot the user clicked, including the
  head slot before step 1.

### Key Entities

- **Override row** — a `workflows` row with `source="user"`, distinguished from an ordinary saved
  workflow solely by a non-NULL `overrides_pipeline_type`. Reuses the existing table; no new table.
- **`base_version`** — the base manifest's `version` at save time. **Stored but not yet read** —
  see §6.

## 5. Out of scope

- Making any capability `user_allowed=True`. The steps-only design exists precisely to avoid this.
- Org-wide or team-level overrides. Per user only.
- A side-by-side diff of override vs original. The toggle is the comparison.
- `*_revision` pipelines inheriting their base's override.
- Editing workflow-level fields. Deliverable, planner and clarify stay file-owned by design.

## 6. Known gaps — not resolved by this spec

- **G-1 — `base_version` is inert.** The column is written and never read. If a built-in's
  `workflow.yaml` changes, every saved override keeps running its old steps with no staleness
  signal to the user.
- **G-2 — Two validators disagree.** `merge_override_steps` compiles a row through the workflow
  compiler; the launch separately runs `presort_specs`' produces/consumes DAG check. A row can
  pass the first and fail the second, so **an override can be saved and displayed while being
  unlaunchable**, surfacing only at launch (observed: a 2-step `prototype` override → 422
  `prototype-build consumes prototype-plan`). The DAG check should run at save time.
- **G-3 — Pre-existing bad rows.** Overrides saved before FR-010 may still contain a
  `custom-agent:` step and will 400 on launch. There is no validation sweep or migration.
- **G-4 — `ComposerPage` cannot author an override.** It hardcodes `base_pipeline_type: "custom"`,
  deliberately (its comment: `workflowType` is a shared mutable other screens set, and trusting it
  risked persisting a stale type). Seven tests assert the opposite. Unresolved design conflict.

## 7. Success Criteria *(mandatory)*

- **SC-001** — A user with no override observes no behavioural change anywhere.
- **SC-002** — Ticking the box changes both what Advanced displays AND what a run executes.
- **SC-003** — An overridden `ppt` run still produces a deck via the file manifest's deliverable.
- **SC-004** — Saving twice yields one row, same id.
- **SC-005** — A cache-identity test proves the merge leaves the `lru_cache`'d plan untouched.

### Validation actually performed (2026-08-25, local, `qwen3.5:4b`)

| workflow | steps run | deliverable | outcome |
|---|---|---|---|
| `ppt` | 4 — `report-generator` first | `presentation.pptx` | deck rendered, 5 slides |
| `user_stories` | 7 — added agent first, `backlog-compiler` last | `user_stories.md` | real backlog, no leakage from the added agent |
| `prototype` | 2 — added agent → `prototype-specify` | `prototype.html` | completed |

**Not covered:** `app_builder`, `mulesoft_to_springboot`, `dotnet_to_azure` were saved and served
correctly but their runs were cancelled as out of scope. `prototype`'s run was deliberately
shortened, so no `prototype.html` was written and the deliverable fell back to last-streamed —
meaning **the `single_file` deliverable surviving an override is not yet proven**.

## Assumptions

- The user editing an override is its owner; there is no sharing or delegation model.
- A built-in's file manifest is the authority on what the workflow *delivers*; the user's authority
  extends only to which agents run and how each is configured.
