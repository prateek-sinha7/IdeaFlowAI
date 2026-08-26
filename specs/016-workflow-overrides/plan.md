# Spec 016 — User overrides of built-in workflows

A user edits a built-in workflow (`ppt`) on the canvas, saves it, and from then
on **their** `ppt` is the edited one — on the detail page and at launch —
until they switch it off with a checkbox.

Everything here is **additive**. No existing column changes type or nullability,
no existing endpoint changes its response for a user who has no override, no
existing capability becomes user-grantable, and no run that does not resolve an
override compiles differently by a single byte.

---

## 1. What already exists

Roughly two thirds of this shipped on `feat/conditional-gates`. Naming it
precisely matters, because the plan below extends these seams rather than
adding parallel ones.

| Piece | Where | State |
|---|---|---|
| `workflows` table with `source`, `manifest_json`, `base_pipeline_type`, `version`, `owner_id`, `model_overrides` | `backend/app/models/workflow_definition.py` | ✅ |
| Built-ins open on the full canvas at `/workflows/{type}/canvas` | ADR-0014, `frontend/src/app/[...view]/page.tsx:404` | ✅ copy-only |
| `GET /api/workflows/{id}` returns raw `manifest_steps` so a built-in is reconstructable | `backend/app/api/workflows.py:333` | ✅ |
| A DB manifest compiles (`trust="db"`) and launches via `compiled_override` | `LaunchSource.USER_WORKFLOW_MANIFEST`, `run_commands.py:2616` → `engine.py:1682` | ✅ |
| Per-step overlay onto a file-compiled plan, cache-safe | `_apply_selections`, `engine.py:8428-8530` | ✅ |
| The three launch shapes are named and locked | ADR-0020 | ✅ |

### The four gaps

1. **The binding is deliberately dropped.** `ComposerPage.tsx:653` hardcodes
   `base_pipeline_type: "custom"` — the comment explains why (a shared mutable
   `workflowType` was persisting stale values from unrelated screens). And
   `page.tsx:421` deliberately omits `id` so Save POSTs a new row. Both guards
   are correct and stay; the plan adds an explicit path beside them.
2. **No resolution at display.** `list_workflows` states *"Reads only the
   compiled manifests + registry — no DB query."* Both it and `get_workflow`
   already inject `current_user` and never use it.
3. **No resolution at launch.** `run_commands.py:2563` sets `FILE_PIPELINE`
   whenever `user_workflow_id` is absent; the DB is never consulted.
4. **The wizard's Advanced modal does not read the workflow manifest at all.**
   This is the gap that breaks the target flow, and it is not obvious from the
   backend side. See §1.1.

### 1.1 The `Home → PPT → Advanced` path does NOT go through `GET /api/workflows/ppt`

`ppt` declares `launch_surface: wizard`, so the flow lands in `LaunchWizard`,
whose roster comes from the AGENT.md-derived agent library — never from the
compiled manifest:

```
Home → PPT → click → Advanced → agents
                                   │
                                   ▼
                 LaunchWizard.tsx:172
                 defaultAgentsFor(libraryAgents, "ppt")
                                   │
                                   ▼
                 GET /api/agents/library
                 filtered on AGENT.md pipeline_type == "ppt"
```

`grep -c getWorkflowDetail components/workflow/LaunchWizard.tsx` → **0**. The
wizard makes no workflow-detail call today.

So §4's backend work is necessary but **not sufficient**: an override would
execute correctly while the Advanced modal kept listing the original agents.
§5.3 closes it.

Two facts make that closure smaller than it looks:

- **`IdeaInputPage` already does exactly this.** It builds `manifestAgents`
  from `GET /api/workflows/{id}` and seeds gates from the manifest
  (`IdeaInputPage.tsx:945-975`). Its own comment records why: the library only
  knows agents that declare a `pipeline_type` in an `AGENT.md`, so a composed
  workflow rendered Advanced empty. §5.3 is a port of that proven pattern, not
  a new one.
- **The wizard already sends the right binding.**
  `MODE_CONFIG.ppt.savePipeline = "ppt"` (`LaunchWizard.tsx:98`), so its Save
  already posts `base_pipeline_type: "ppt"` — unlike `ComposerPage`, which
  hardcodes `"custom"`. Adding `overrides_pipeline_type` here is one field.

---

## 2. The two constraints that shape the design

### 2.1 Trust — a full `ppt` manifest cannot compile from the DB

`_TRUSTED_SOURCES` is `{file, builtin}`. A `user`/`db` manifest is untrusted, and
`_check_trust` (`compiler.py:417`) rejects any capability whose registration did
not pass `user_allowed=True`. `registry.is_user_allowed` defaults to `False`.

Two of `ppt`'s workflow-level declarations fail that check:

| Declaration | Registered at | `user_allowed` |
|---|---|---|
| `deliverable: {strategy: ppt}` | `agents/capabilities/deliverables/ppt.py:46` | **absent → False** |
| `context_providers: [opendesign]` | `agents/capabilities/context_providers/opendesign.py:41` | **absent → False** |

Omitting `opendesign` instead is worse, not better: `load_ppt_od_context` never
runs, the template never loads, and the composer builds a deck with no design.
(`buildWorkflowManifest` in `frontend/src/store/api/userWorkflows.ts:387` does
not emit `context_providers` at all, and `run_commands.py:2646` synthesizes
`deliverable`/`planner`/`clarify`/`capabilities` but not that field — so this is
the default outcome, not a corner case.)

**The step-level declarations are fine.** `single_shot`, `human`,
`before-human`, `conditional` and `validation` are all registered
`user_allowed=True`; only `approval` and `security` are engineer-only.

**Therefore: the override row stores ONLY `steps`.** Every workflow-level
field — `deliverable`, `context_providers`, `planner`, `clarify`, `seed_files`,
`limits`, `capabilities` — is taken from the file manifest on every resolve and
is never user-editable. Those fields then never originate from a user, so they
are never trust-checked, and **no capability needs to become `user_allowed`.**

This is also the right product answer: the ask is "override the agents", not
"override the deliverable strategy".

### 2.2 `compile_for_run` is `lru_cache(maxsize=None)`

`engine.py:643`. The returned `CompiledWorkflow` is **shared across every user
and every run**. Mutating it to apply an override would leak one user's
customisation into everyone else's runs, silently, until process restart.

`_apply_selections` already solves this correctly and is the pattern to copy:
build a fresh `new_steps` list, then `dataclasses.replace(compiled, steps=...)`
(`engine.py:8501`, `:8521`). **Never mutate `compiled` or anything reachable
from it.** This is the single highest-risk line in the whole plan.

---

## 3. Data model

One migration, one nullable column, one partial unique index. Nothing else.

```python
# backend/alembic/versions/0039_workflow_override_binding.py
revision = "0039"
down_revision = "0038"

def upgrade() -> None:
    with op.batch_alter_table("workflows") as b:          # SQLite portability (0027 pattern)
        b.add_column(sa.Column("overrides_pipeline_type", sa.String(), nullable=True))
        b.add_column(sa.Column("override_enabled", sa.Boolean(),
                               nullable=False, server_default=sa.false()))
    op.create_index(
        "uq_workflows_user_override",
        "workflows", ["user_id", "overrides_pipeline_type"],
        unique=True,
        sqlite_where=sa.text("overrides_pipeline_type IS NOT NULL"),
        postgresql_where=sa.text("overrides_pipeline_type IS NOT NULL"),
    )
```

### Why a new column instead of reusing `base_pipeline_type`

`base_pipeline_type` already means *"which entitlement key applies / what did I
start from"*. A user may legitimately hold five saved workflows with
`base_pipeline_type = "ppt"` that are ordinary copies, not overrides.
Overloading it makes *"which one wins"* undefined. `overrides_pipeline_type` is
NULL on every existing row and on every ordinary save.

### Why not key on `name`

Three reasons, all load-bearing:

- **It is renamable.** `PATCH /api/user-workflows/{id}` accepts `name`. The
  override would silently detach on rename and `ppt` would revert to the file
  version with no error anywhere.
- **Uniqueness is API-level only.** `user_workflows.py:586` is a check-then-
  insert with a 409; there is no DB constraint, so two concurrent saves both
  pass the check and produce two rows named "PPT" with no tiebreak.
- **"The same name as ppt" is ambiguous** — `"PPT"` is `manifest.name`,
  `"Pitch an idea"` is `display_name`, `"ppt"` is the id. Only the id is stable.

The name stays free text. Display it however you like.

### Why `override_enabled` is a column, not a query parameter

If the checkbox only changes what the page renders, display and execution can
disagree: the detail page shows the system version while a launch routes
through the override. One persisted flag is read by both, so they cannot
diverge.

```
override_enabled = true   →  GET /api/workflows/ppt   returns the override
                             POST /api/runs           routes through it
override_enabled = false  →  both fall back to the file manifest
```

`?original=true` is still added (§5) but strictly as a read-only compare view.
It must never be what decides which plan runs.

---

## 4. Backend — resolution

### 4.1 One shared resolver

New helper, owner-scoped, used by every read site so the rule lives in one
place:

```python
# backend/app/api/_workflow_override.py   (new, ~25 lines)
def resolve_override(db, user, pipeline_type: str) -> WorkflowDefinition | None:
    """The caller's ENABLED override row for a built-in id, or None.

    Returns None for every user who has never saved one — which is the
    entire existing population — so every call site's current behaviour is
    the None branch, unchanged.
    """
    return (
        db.query(WorkflowDefinition)
        .filter(
            WorkflowDefinition.user_id == user.id,
            WorkflowDefinition.source == "user",
            WorkflowDefinition.overrides_pipeline_type == pipeline_type,
            WorkflowDefinition.override_enabled.is_(True),
        )
        .first()
    )
```

Cross-owner rows are unreachable by construction (`user_id` is in the filter),
matching the `_owned` IDOR→404 posture already used in `user_workflows.py:413`.

### 4.2 Merge — steps from the row, everything else from the file

```python
# backend/agents/execution_engine/overrides.py   (new, ~40 lines)
def merge_override_steps(compiled: CompiledWorkflow, manifest_json: dict,
                         registry) -> CompiledWorkflow:
    """Return a NEW CompiledWorkflow with the override's steps.

    `compiled` is lru_cached and SHARED — never mutated. The override's steps
    are compiled trust="db" in isolation; only `.steps` is taken from the
    result, so no workflow-level capability is ever sourced from the DB.
    """
    raw = {"id": compiled.id, "steps": manifest_json["steps"]}
    parsed = build_manifest_from_dict(raw, f"override:{compiled.id}")
    user_compiled = WorkflowCompiler().compile(parsed, registry, trust="db")
    return dataclasses.replace(compiled, steps=list(user_compiled.steps))
```

A `CompilerError` here degrades to the unmodified plan with a `logger.warning`,
mirroring the narrow-catch posture at `engine.py:8412` — a tampered row must
not take a run down, and the file plan is always a safe fallback.

### 4.3 Call sites — three, each a few lines

| Site | Change |
|---|---|
| `app/api/workflows.py:252` `list_workflows` | add `db: Session = Depends(get_db)`; per id, `resolve_override(...)`; when present, project the override's steps and set `is_overridden=True`, `override_id=<row.id>` |
| `app/api/workflows.py:333` `get_workflow` | same, plus honour `?original=true` to force the file projection while still reporting `is_overridden` so the checkbox renders in the right state |
| `app/api/run_commands.py:2561` launch | inside the **existing** `FILE_PIPELINE` branch, resolve the override and stash `manifest_json` for the merge at compile time |

`list_workflows` currently issues zero DB queries. It will now issue one per
built-in id (~15). If that shows up, replace it with a single
`WHERE overrides_pipeline_type IN (...)` and build a dict — but measure first;
this is an authenticated, non-hot listing endpoint.

### 4.4 Where the merge fires

`compile_for_run(pipeline_type)` **must keep its current signature and cache**.
Adding a per-user argument would multiply the cache by the user count and
change a hot, well-tested seam.

Instead the merge happens at the same place `_apply_selections` already runs —
after the compile, inside `execute()`:

```python
compiled = (
    compiled_override
    if compiled_override is not None
    else compile_for_run(pipeline_type)          # unchanged, still cached
)
# NEW, additive — no-op when ectx.override_manifest is None
if getattr(ectx, "override_manifest", None):
    compiled = merge_override_steps(compiled, ectx.override_manifest, _CAPABILITY_REGISTRY)
```

`override_manifest` is one new `dict | None = None` field on `ExecutionContext`
(`agents/execution_engine/context.py`), defaulting to `None` — the same additive
pattern as `step_skills` and `current_step`.

**ADR-0020 is not violated.** No fourth `LaunchSource` is introduced and the
shape is still detected exactly once. An overridden built-in launch stays
`FILE_PIPELINE` — which is precisely what that enum member already means: the
file manifest supplies the plan. Only `.steps` is overlaid, exactly as
`_apply_selections` already overlays levers within the same shape.

---

## 5. Frontend

### 5.1 Save — two buttons

**Assumption, stated because it was not confirmed:** Save keeps its current
copy-only meaning and a *second* button performs the override.

- **Save as new workflow** — today's behaviour, untouched. `POST` with
  `base_pipeline_type: "custom"`, `overrides_pipeline_type` absent.
- **Save as override** — shown only when `builtinCanvasType` is set. `POST`
  with `base_pipeline_type: builtinCanvasType` **and**
  `overrides_pipeline_type: builtinCanvasType`, upserting on the unique index
  so a repeat save updates the same row ("once, or overwritten always").

Two buttons rather than a mode switch because they produce genuinely different
rows, and a silent mode is how someone overwrites the thing they meant to fork.
If you would rather have one button, only this subsection changes.

`ComposerPage.tsx:653`'s hardcoded `"custom"` **stays** for the ordinary path —
its stale-`workflowType` guard is still correct. The override path reads
`builtinCanvasType`, which is already threaded in as a prop
(`page.tsx:3620`) and is derived from the URL, so it cannot go stale.

### 5.2 Detail page

`GET /api/workflows/ppt` gains `is_overridden` and `override_id`. Render a
checkbox bound to `override_enabled`:

- **on** → the page shows the override; runs use it
- **off** → both fall back to the system version
- **"Compare with original"** → refetch with `?original=true`, read-only
- **"Delete my override"** → `DELETE /api/user-workflows/{override_id}`

Both response models are additive: `is_overridden` defaults `False` and
`override_id` defaults `None`, so an old client ignores them and a user with no
override sees byte-identical payloads.

### 5.3 `LaunchWizard` — the target flow

This is the piece that makes `Home → PPT → Advanced` actually show the
override. Per §1.1 the wizard currently sources its roster from the agent
library and never fetches the manifest.

**Overlay, do not replace.** The temptation is to swap `defaultAgentsFor` for a
manifest fetch the way `IdeaInputPage` does. Don't — that changes the default
roster source for every user on a working screen, override or not, and the two
sources are not guaranteed to agree (the library sorts by AGENT.md `order`; the
manifest is the compiled sequence). Instead:

```ts
// LaunchWizard.tsx — pipelineAgents keeps its current initial value.
const [pipelineAgents, setPipelineAgents] = useState<AgentDef[]>(
  () => defaultAgentsFor(libraryAgents, initialMode),   // UNCHANGED
);

// NEW — additive effect, mirrors the IdeaInputPage fetch idiom
// (useEffect + cancelled guard). No new fetch shell.
useEffect(() => {
  if (!token) return;
  let cancelled = false;
  (async () => {
    const detail = await getWorkflowDetail(token, cfg.savePipeline);
    if (cancelled || !detail.is_overridden) return;      // ← the no-op path
    setOverrideAvailable(true);
    if (showOverride) setPipelineAgents(agentsFromManifest(detail));
  })();
  return () => { cancelled = true; };
}, [token, cfg.savePipeline, showOverride]);
```

For a user with **no** override the effect resolves `is_overridden: false` and
returns before touching any state — the screen renders byte-identically to
today, having issued one extra authenticated GET.

`agentsFromManifest` is the projection `IdeaInputPage` already performs on the
same payload; lift it to a shared helper rather than writing a second copy
(INV-12 — one seam, not two).

**Gates must be seeded too.** `IdeaInputPage.tsx:969-975` records that a node
renders as a conditional only when BOTH `agent.route` has outcomes AND
`selections[agent.id].gates` includes `"conditional"` — because in the composer
gates are a user-toggled lever, while a manifest DECLARES them. An override
carrying a conditional gate will draw as an ordinary node unless the same
seeding runs here. Reuse that code path; do not re-derive it.

**The toggle.** A single checkbox in the Advanced modal header, rendered only
when `overrideAvailable`:

- **on** → `pipelineAgents` = the override's steps; the launch resolves the
  override (§4.3), so screen and run agree
- **off** → `pipelineAgents` = `defaultAgentsFor(libraryAgents, mode)`, i.e.
  exactly today's list

The checkbox writes `override_enabled` on the row (§3), so the choice persists
across sessions and the detail page (§5.2) reads the same flag.

**Scope decision (stated, not assumed):** the modal shows **one** roster at a
time and the checkbox swaps it. A side-by-side original-vs-override diff is a
new component and is deliberately deferred — "Compare with original" already
exists as a read-only view via `?original=true` (§5.2) and covers the
inspection need without the diff work.

---

## 6. Blast radius

| Area | Effect |
|---|---|
| `workflows` table | 2 nullable/defaulted columns + 1 partial index. Every existing row: `overrides_pipeline_type IS NULL`, `override_enabled = false` |
| `compile_for_run` | **unchanged** — same signature, same cache key, same cached object, never mutated |
| `_apply_selections` | **unchanged** — the override merge runs before it and returns the same type |
| `USER_WORKFLOW_FLAT` / `USER_WORKFLOW_MANIFEST` | **unchanged** — both still take `user_workflow_id`; the override path never sets it |
| Capability trust | **unchanged** — nothing gains `user_allowed`; workflow-level fields never come from the DB |
| `ppt.v2`, `prototype`, `app_builder`, every other manifest | **unchanged** — the mechanism is keyed on a pipeline id and is inert for any id with no override row |
| Entitlements | **unchanged** — `can_run_pipeline` still keys on `body.pipeline_type`, which stays `"ppt"` for an overridden ppt run |
| `LaunchWizard` roster source | **unchanged** — `defaultAgentsFor(libraryAgents, mode)` stays the initial value; the override is an overlay on top, skipped entirely when `is_overridden` is false |
| `GET /api/agents/library` | **unchanged** — not touched; the wizard still calls it exactly as today |
| `IdeaInputPage` | one extraction only — `agentsFromManifest` lifted to a shared helper, same behaviour |
| Users with no override | Every read returns the `None` branch; every launch stays byte-identical. The only observable difference is one extra authenticated GET on the wizard screen |

---

## 7. Task order

Each step is independently verifiable; nothing after it is needed for the one
before it to be correct.

| # | Task | Verify |
|---|---|---|
| 1 | Migration 0039 + the two model columns | `alembic upgrade head` then `downgrade -1`; single head; existing rows read back with NULL/false |
| 2 | `resolve_override` helper + unit tests | returns None with no row; returns the row when enabled; returns None when disabled; never returns another user's row |
| 3 | `merge_override_steps` + unit tests | **the cache-identity test is mandatory**: call `compile_for_run("ppt")`, merge, assert the cached object's `.steps` is unchanged and `id()` differs from the result |
| 4 | Wire `get_workflow` (+ `?original=true`), then `list_workflows` | with no row, both responses are byte-identical to today |
| 5 | Wire the launch resolve + `ectx.override_manifest` | a no-override ppt run produces the identical event stream |
| 6 | FE: extract `agentsFromManifest` from `IdeaInputPage` to a shared helper | `IdeaInputPage.test` suites unchanged — pure move |
| 7 | FE: second save button, sending the binding (ComposerPage **and** the wizard's save) | row lands with both new columns set |
| 8 | **FE: `LaunchWizard` override overlay + Advanced checkbox (§5.3)** | **the target flow: Home → PPT → Advanced shows the override with the box ticked, the original with it clear** |
| 9 | FE: detail-page checkbox, compare, delete | toggling off restores the system steps in the same session |

Task 8 is the acceptance criterion for the whole spec — everything before it is
necessary but invisible. Demo it as: save an override that renames one ppt step,
then walk `Home → PPT → Advanced` and toggle the box both ways.

### Tests to run, one file at a time

`backend/tests/agents/test_deliverable_resolvers.py`,
`test_gates.py`, `test_composer_skills_delivery.py`, plus whatever covers
`user_workflows` and `run_commands` launch-shape detection. Frontend:
`ComposerPage.test.tsx`, `CanvasView.test.tsx`, `LaunchWizard`'s suite, and the
`IdeaInputPage.*` suites (they must stay green across the task-6 extraction —
if one moves, the extraction was not pure).

Note the known baseline: `ComposerPage.test.tsx` is **7 failed | 7 passed at
HEAD** — `c9ec0149c` removed per-`workflowType` template seeding while the
fixtures still call `renderComposer()` bare. Do not read those 7 as a
regression; confirm the count is still exactly 7 before and after.

---

## 8. Deliberately out of scope

- **Making any capability `user_allowed`.** The merge exists specifically to
  avoid it. If a later requirement genuinely needs a user-authored
  `deliverable`, that is its own ADR.
- **Structural safety of an override.** A user can delete every step and save
  an empty plan. The compiler accepts an empty `steps` list (the
  `reverse_engineer` stub relies on it), so this is a real footgun — worth a
  minimum-one-step check at the save endpoint, filed separately.
- **A side-by-side original-vs-override diff.** The Advanced modal shows one
  roster and the checkbox swaps it (§5.3). A true two-column diff is a new
  component; `?original=true` already gives a read-only view of the system
  version and covers the inspection need. Revisit only if the toggle proves
  insufficient in use.
- **Sharing an override across users, or org-wide defaults.** Rows are
  owner-scoped; a team-level override is a different data model.
- **`ppt_revision` and the other `*_revision` pipelines.** They resolve their
  own `pipeline_type`, so an override of `ppt` does not follow into a revision
  run. Correct for a first cut; needs a decision before it surprises someone.

## 9. Known follow-up: staleness

An override snapshots the steps at save time. Ship a change to `ppt` — adding
the `ppt-pptx-author` step from spec 016's sibling work, say — and every
override holder keeps the old steps, silently, forever.

The cheap guard is to stamp the base manifest's `version` on the row at save
and compare on read, surfacing *"the original has changed since you customised
it"* with a link to the compare view. **Do this in the same pass**, not later:
the column is free to add now alongside the other two, and expensive to
backfill meaningfully once overrides exist in the wild.
