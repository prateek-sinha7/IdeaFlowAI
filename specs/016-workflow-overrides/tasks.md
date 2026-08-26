# Tasks: User overrides of built-in workflows

Plan: [plan.md](plan.md). Nine tasks, two checkpoints. Every task is additive —
a user with no override must see byte-identical behaviour after all nine.

```mermaid
flowchart LR
    T1((T1)) --> T2((T2)) --> T3((T3)) --> V1{{V1}}
    V1 --> T4((T4)) --> T5((T5))
    T5 --> T6((T6)) --> T7((T7)) --> T8((T8)) --> T9((T9)) --> V2{{V2}}
    V2 --> T10((T10)) --> T11((T11)) --> T12((T12)) --> T13((T13)) --> V3{{V3}}

    classDef todo fill:#ffffff,stroke:#868e96,color:#1b1b1b;
    classDef inprogress fill:#4dabf7,stroke:#1971c2,color:#ffffff;
    classDef done fill:#40c057,stroke:#2f9e44,color:#ffffff;
    classDef error fill:#fa5252,stroke:#e03131,color:#ffffff;

    %% STATUS — move a task id between these lines on completion. Never change
    %% a node's shape, never edit the classDefs.
    class T1,T2,T3,V1,T4,T5,T6,T7,T8,T9,V2,T10,T11,T12,T13,V3 done;
```

**13 tasks · 3 checkpoints · COMPLETE**

T1–T9 delivered the feature. T10–T13 were added on 2026-08-25 after end-to-end UI validation
across `ppt`, `user_stories` and `prototype` surfaced four defects the original nine never
covered — three of them capable of losing a user's deliverable or making a saved override
unlaunchable. They are tasks, not patches: each has its own verification below.

Backend, each file run individually:
`test_workflow_override.py` 23 · `test_workflow_override_e2e.py` 7 · `test_workflows_api.py` 42 ·
`test_user_workflows.py` 39 · `test_user_workflows_selections.py` 32 · `test_rest_run_launch.py` 32 ·
`test_run_commands_fix218.py` 24 — all green.

Frontend: `tsc --noEmit` clean · `LaunchWizard` 19 · `CanvasView` 24 · `InlineGateActions` 23 ·
`AgentsPopup.reskin` 14 · `ComposerPage` **7 failed | 7 passed = the exact HEAD baseline** (V2 criterion).

Migration 0039 applied to the dev DB (`flowin_local_merged`); 27 existing rows intact.

**T9 folded into T8.** The flow the user named — `Home → PPT → Advanced` — is the wizard's
Advanced modal, and that is where the checkbox lives. There is no separate "ppt detail page"
in that path, so building one would have been scope invented rather than delivered.

---

## Backend

### T1 — Migration 0039 + model columns
`backend/alembic/versions/0039_workflow_override_binding.py`, `backend/app/models/workflow_definition.py`

Three columns on `workflows`, all nullable or defaulted, plus a partial unique
index on `(user_id, overrides_pipeline_type)`:

- `overrides_pipeline_type` — String, nullable — the built-in id this overrides
- `override_enabled` — Boolean, not null, server_default false
- `base_version` — Integer, nullable — the base manifest's `version` at save (plan §9)

`batch_alter_table` for SQLite portability (0027/0038 pattern).

**Verify:** `alembic upgrade head` then `downgrade -1`; `alembic heads` shows
one head; an existing row reads back NULL / false / NULL.

### T2 — `resolve_override` helper
`backend/app/api/_workflow_override.py` (new, ~25 lines)

Owner-scoped lookup returning the caller's **enabled** override row for a
pipeline id, else `None`.

**Verify:** unit tests — None when no row; row when enabled; **None when
disabled**; never another user's row.

### T3 — `merge_override_steps`
`backend/agents/execution_engine/overrides.py` (new, ~40 lines)

Compile the row's `steps` alone with `trust="db"`, take only `.steps`, return
`dataclasses.replace(compiled, steps=...)`. `CompilerError` → log warning,
return `compiled` unchanged.

**Verify:** **the cache-identity test is mandatory** — call
`compile_for_run("ppt")`, merge, assert the cached object's `.steps` is
unchanged and `id()` differs from the result. Plus: a row declaring `security`
or `approval` is rejected (not user-allowed); the returned plan still carries
the file's `deliverable` and `context_providers`.

### V1 — Backend checkpoint
No FE work starts until T1–T3 are green **and** a no-override `ppt` run
produces an identical event stream to `main`.

### T4 — Wire the read endpoints
`backend/app/api/workflows.py` — `list_workflows` (:252), `get_workflow` (:333)

Add `db: Session = Depends(get_db)`. Resolve per id; when present project the
override's steps and set `is_overridden` / `override_id`. `get_workflow`
honours `?original=true` (forces the file projection, still reports
`is_overridden` so the checkbox renders correctly).

**Verify:** with no row, both responses are byte-identical to today.

### T5 — Wire the launch resolve
`backend/app/api/run_commands.py` (:2561 branch), `backend/agents/execution_engine/context.py`, `engine.py` (~:1682)

Inside the **existing** `FILE_PIPELINE` branch — no new `LaunchSource`
(ADR-0020). One new `ExecutionContext` field `override_manifest: dict | None =
None`; merge fires right after `compile_for_run`.

**Verify:** a no-override ppt run is byte-identical; an overridden run executes
the override's steps and still resolves the `ppt` deliverable.

---

## Frontend

### T6 — Extract `agentsFromManifest`
`frontend/src/components/workflow/IdeaInputPage.tsx` → shared helper

Pure move of the existing manifest→`AgentDef[]` projection (plus its gates
seeding) so the wizard reuses it instead of a second copy (INV-12).

**Verify:** the `IdeaInputPage.*` suites stay green. If one moves, the
extraction was not pure.

### T7 — Save as override
`frontend/src/components/workflow/composer/ComposerPage.tsx` (:653), `LaunchWizard.tsx`

Second button, shown only when a built-in is open. Sends
`overrides_pipeline_type` alongside `base_pipeline_type`; upserts on the unique
index. `ComposerPage`'s hardcoded `"custom"` **stays** for the ordinary path —
its stale-`workflowType` guard is still correct.

The wizard already sends `base_pipeline_type: "ppt"`
(`MODE_CONFIG.ppt.savePipeline`), so it needs one extra field.

**Verify:** saving twice updates one row, not two.

### T8 — LaunchWizard overlay + Advanced checkbox ⭐
`frontend/src/components/workflow/LaunchWizard.tsx` (:172), `AgentsPopup.tsx`

Plan §5.3. `defaultAgentsFor(libraryAgents, mode)` **stays** the initial value;
an additive effect fetches the detail and returns early when `is_overridden` is
false. Checkbox writes `override_enabled`, swaps the roster, seeds gates.

**Verify — this is the acceptance criterion for the whole spec:** save an
override that renames one ppt step, then walk `Home → PPT → Advanced` and
toggle the box both ways. Ticked shows the override, clear shows the original.

### T9 — Detail page checkbox
`frontend/src/components/...` detail view

Same checkbox bound to the same flag, plus "Compare with original"
(`?original=true`, read-only) and "Delete my override".

**Verify:** toggling off restores the system steps in the same session.

### V2 — Final
- A user with no override sees no change anywhere (the one difference: a single
  extra authenticated GET on the wizard screen)
- Ticking the box changes both what Advanced shows **and** what a run executes
- `ComposerPage.test.tsx` is still **exactly 7 failed | 7 passed** — the known
  HEAD baseline from `c9ec0149c`, not a regression

---

## Notes

Tests run **one file at a time**, never the suite.

Out of scope, per plan §8: making any capability `user_allowed`, side-by-side
diff, org-wide overrides, `*_revision` inheritance.


---

## Round 2 — defects found by end-to-end UI validation (2026-08-25)

### T10 — Remove the file-less custom agent from override authoring (FR-010)
`frontend/src/components/workflow/AgentLibrary.tsx`, `AgentsPopup.tsx`, `LaunchWizard.tsx`

The blank `custom-agent` template mints `custom-agent:<instance_id>`, which has no `AGENT.md` and
is absent from the roster `allowed_custom_agent_ids` builds — so the launch rejects it with
`invalid_agent_ids`. Such an override saved fine, rendered fine, and 400'd on every launch.

New `allowCustomAgentTemplate` prop, default `true` (the composer canvas keeps it — a user-defined
step is the point there), `false` from the LaunchWizard. Gates the list AND the category count.

**Verify:** the wizard's Custom category shows the file-backed pool but not the blank template;
the composer canvas still offers it. 6 source-lock tests.

### T11 — Guard the append-at-end slot (FR-011)
`frontend/src/components/workflow/composer/CanvasView.tsx`

`ppt` and `streamed_text` resolve to `ctx.last_streamed`, so appending after the final step
silently replaces the deck/backlog with the new agent's output — no error, wrong artifact
delivered. The trailing "+" is now disabled for those, with a reason naming the file.

Keyed on the **declared** strategy, never the `?? "streamed_text"` default — the first attempt used
the default and wrongly disabled the composer's own append slot (`CanvasView.test.tsx` caught it).

**Verify:** on `ppt` the trailing slot is disabled and head/mid-chain slots stay enabled; a custom
composition is unaffected. `CanvasView` 24/24; 4 source-lock tests.

### T12 — Override support on `IdeaInputPage` (FR-012)
`frontend/src/components/workflow/IdeaInputPage.tsx`

`LaunchWizard.MODE_CONFIG` is typed `"prototype" | "ppt"`. Every other built-in —
`user_stories`, `app_builder`, `mulesoft_to_springboot`, `dotnet_to_azure` — renders
`IdeaInputPage`, which had **no override affordance at all**. T7/T8 shipped the feature for two of
six workflows.

Override state; capture off the EXISTING detail fetch (no second request); roster precedence
resolved inside the roster effect so the manifest arriving cannot clobber it; toggle; save;
"Save as my version" button; "Use my version" checkbox props. Hidden for `custom`.

**Verify:** "Save as my version" appears on user_stories/app_builder/mulesoft/dotnet; saving binds
an override that the page then applies on reload.

### T13 — Honour the clicked insert slot (FR-013)
`frontend/src/components/workflow/IdeaInputPage.tsx`

`handleAddAgent` hardcoded `insertIdx = prev.length - 1` for every non-custom pipeline and never
accepted `insertBeforeId` — clicking the leftmost "+" on a 6-agent pipeline put the agent at
position 6 of 7. Now honours the slot and re-numbers `order` across the list (the splice left
duplicate `order` values behind the insert point).

**Verify:** the head slot puts the agent at position 1 on user_stories, prototype and app_builder.

### V3 — End-to-end, from the UI, per deliverable family

| workflow | family | steps run | result |
|---|---|---|---|
| `ppt` | `ppt` (last-streamed) | 4, added agent first | deck rendered, 5 slides |
| `user_stories` | `streamed_text` (last-streamed) | 7, added first, compiler last | real backlog, no leakage |
| `prototype` | `single_file` (sandbox) | 2 | completed |

**Not covered — carried into [spec.md](spec.md) §6:** `app_builder`, `mulesoft_to_springboot` and
`dotnet_to_azure` were saved and served correctly but their runs were cancelled as out of scope.
`prototype` ran shortened, so no `prototype.html` was written and the deliverable fell back to
last-streamed — **`single_file` surviving an override is still unproven**.
