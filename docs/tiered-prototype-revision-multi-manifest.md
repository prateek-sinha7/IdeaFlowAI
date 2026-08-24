# Tiered Prototype Revision — Multi-Manifest Approach (Pieces 1, 2 & 3)

**Branch:** `feat/tiered-prototype-revision`  
**Date:** 2026-08-19 (updated 2026-08-20 — full code-trace audit)  
**Status:** Proposed (Alternative to Unified Manifest approach)  
**Compare with:** `docs/tiered-prototype-revision.md` (Piece 4 — Unified Manifest)

> **⚠️ NAMING CORRECTION (2026-08-20):** An earlier draft used `prototype_revision_large` /
> `prototype_revision_feature` as pipeline names AND `prototype_large_output` /
> `prototype_feature_output` as target types. These are **mutually inconsistent**.
> The engine derives `revision_pipeline_type = f"{target_artifact_type.removesuffix('_output')}_revision"`
> (`engine.py:7011`). The only self-consistent naming that satisfies this transform is
> **`prototype_large_revision`** / **`prototype_feature_revision`** (target types
> `prototype_large_output` / `prototype_feature_output`). All names in this document use the
> corrected convention. See §10 for the full impact table.

---

## 1. Core Idea

Three **separate, independent manifests** — one per tier — plus a **backend classifier** that runs before the revision run is minted. The classifier determines the tier, then routes to the correct manifest by selecting the right `target_artifact_type`. No manifest shares agents between tiers.

```
Piece 1 — New manifests:   prototype_revision        (small, existing — unchanged)
                           prototype_large_revision   (new)
                           prototype_feature_revision (new)

Piece 2 — New agents:      prototype-revision-planner         (large tier)
                           prototype-large-builder             (large tier task_loop)
                           prototype-revision-feature-specify  (feature tier)
                           prototype-revision-feature-plan     (feature tier)
                           prototype-feature-builder           (feature tier task_loop)

Piece 3 — Backend routing: _classify_revision_tier() in run_commands.py
                           Routes to correct manifest BEFORE minting the row
```

> **Why these names?** The engine at `engine.py:7011` derives the pipeline type as
> `f"{target_artifact_type.removesuffix('_output')}_revision"`. So `prototype_large_output`
> → `prototype_large_revision` ✓ and `prototype_feature_output` → `prototype_feature_revision` ✓.
> Using `prototype_revision_large` as the pipeline name would require a target type of
> `prototype_revision_large_output` which produces `prototype_revision_large_revision` — broken.
> The `{base}_output → {base}_revision` naming convention is a hard constraint of the engine transform.

---

## 2. How Routing Works

Unlike the Piece 4 approach (classifier as a workflow step), here the classification happens **before the WorkflowRun is created**. The backend reads the current prototype, calls a single synchronous LLM classification, and uses the result to select which `target_artifact_type` to mint.

```
Frontend: POST /api/runs/{parent_id}/revisions
  body.target_artifact_type = "prototype_output"
  body.instruction = "=== EXISTING PROTOTYPE HTML ===\n...\n=== REVISION REQUEST ===\nAdd login page"
         │
         ▼
create_revision() endpoint  ← ONE new async step added here
         │
         ├─ _classify_revision_tier(instruction, parent_run_id)
         │     ├─ Reads prototype.html from parent sandbox
         │     ├─ Runs single LLM call: "small | large | feature?"
         │     └─ Returns: "small" | "large" | "feature"
         │
         ├─ Map tier → target_artifact_type:
         │     "small"   → "prototype_output"          → prototype_revision       (existing)
         │     "large"   → "prototype_large_output"    → prototype_large_revision (new)
         │     "feature" → "prototype_feature_output"  → prototype_feature_revision (new)
         │
         ▼
_mint_revision_row(target_artifact_type=<selected>)
         │
         ▼
_drive_revision_to_queue(target_artifact_type=<selected>)
         │
         ▼
Runs the selected manifest
```

---

## 3. Complete Architecture Diagram

```
User clicks "Revise Prototype"
        │
        ▼
POST /api/runs/{id}/revisions
  instruction: "=== EXISTING PROTOTYPE HTML ===\n{html}\n=== REVISION REQUEST ===\n{text}"
        │
        ▼
┌──────────────────────────────────────────────────────────────────────┐
│  create_revision() — MODIFIED                                         │
│                                                                       │
│  1. Resolve parent run (ownership gate)                               │
│  2. _classify_revision_tier(instruction, parent_run_id)  ← NEW       │
│       - Reads prototype.html from parent sandbox                      │
│       - Single LLM call with classifier prompt                        │
│       - Returns: "small" | "large" | "feature"                       │
│  3. Select target:                                                    │
│       small   → "prototype_output"          → prototype_revision       │
│       large   → "prototype_large_output"    → prototype_large_revision │
│       feature → "prototype_feature_output"  → prototype_feature_revision│
│  4. _mint_revision_row(target=<selected>)                             │
│  5. _drive_revision_to_queue(target=<selected>)                       │
└──────────────────────────────────────────────────────────────────────┘
        │
        ├────────────────────────────────────────────────────────────────┐
        │ TIER: small                                                    │
        │ (no change from today)                                         │
        ▼                                                               │
┌────────────────────────────────┐                                      │
│  prototype_revision            │                                      │
│  (existing, UNCHANGED)         │                                      │
│                                │                                      │
│  Step 1: prototype-revision-   │                                      │
│          agent (single_shot)   │                                      │
│  Step 2: prototype-revision-   │                                      │
│          validate              │                                      │
└────────────────────────────────┘                                      │
                                                                        │
        ┌───────────────────────────────────────────────────────────────┘
        │ TIER: large
        ▼
┌────────────────────────────────────────────────────────────┐
│  prototype_large_revision  (NEW manifest)                   │
│                                                             │
│  Step 1: prototype-revision-planner  (single_shot)         │
│    • Reads prototype.html + instruction                      │
│    • Breaks work into 3–8 discrete tasks                   │
│    • Writes tasks.md                                        │
│                                                             │
│  Step 2: prototype-large-builder  (task_loop)              │
│    • Loops over ## Task N: headings in tasks.md            │
│    • Each iteration applies ONE focused change             │
│    • Uses html_static + html_render validators             │
│                                                             │
│  Step 3: prototype-revision-validate (single_shot)         │
│    • Final validation pass                                  │
└────────────────────────────────────────────────────────────┘

        │ TIER: feature
        ▼
┌────────────────────────────────────────────────────────────┐
│  prototype_feature_revision  (NEW manifest)                 │
│                                                             │
│  Step 1: prototype-revision-feature-specify (single_shot)  │
│    • Reads prototype.html, spec.md, design.md              │
│    • Writes a new feature spec into spec.md                │
│    • Gates: [human] — user reviews the spec                │
│                                                             │
│  Step 2: prototype-revision-feature-plan  (single_shot)    │
│    • Reads new spec.md section                             │
│    • Writes tasks.md with full feature task breakdown      │
│    • Gates: [human] — user reviews the task plan          │
│                                                             │
│  Step 3: prototype-feature-builder (task_loop)             │
│    • Same task_loop as large tier                          │
│    • Loops over ## Task N: headings                        │
│    • Full prototype-build parity: html_static + html_render│
│    • html_skeleton compaction                              │
│                                                             │
│  Step 4: prototype-revision-validate (single_shot)         │
│    • Final validation — same as all tiers                  │
└────────────────────────────────────────────────────────────┘
```

---

## 4. Context Flow

### How context reaches each pipeline

The `previous_run` context provider runs identically for all three manifests — it seeds the workspace before any step runs:

```
previous_run provider (runs at start of ALL three manifests)
    ├─ Reads from parent sandbox:
    │    spec.md, design.md, tasks.md → copied to this sandbox
    ├─ Extracts prototype.html from instruction → written to sandbox
    ├─ Captures revision instruction
    ├─ Slims the user message to a file pointer
    └─ Stashes on ExecutionContext:
         ctx.revision_original_html = "<original html snapshot>"
         ctx.revision_instruction = "<user request text>"
```

### Workspace state per tier

#### Small tier (prototype_revision — unchanged)
```
SANDBOX START:              AFTER STEP 1:           AFTER STEP 2:
prototype.html (original)   prototype.html (edited) prototype.html (validated)
spec.md                     spec.md                 spec.md
design.md                   design.md               design.md
tasks.md (from parent)      tasks.md (unchanged)    tasks.md (unchanged)
```

#### Large tier (prototype_large_revision — NEW)
```
SANDBOX START:              AFTER STEP 1:           DURING STEP 2:          AFTER STEP 3:
prototype.html (original)   prototype.html (orig)   prototype.html (edited  prototype.html (validated)
spec.md                     spec.md                  per task N)             spec.md
design.md                   design.md               design.md               design.md
tasks.md (from parent)      tasks.md (OVERWRITTEN   tasks.md (read per      tasks.md (planner's plan)
                             by planner: 3-8 tasks)   iteration)
```

#### Feature tier (prototype_feature_revision — NEW)
```
SANDBOX START:     AFTER STEP 1:    AFTER STEP 2:     DURING STEP 3:    AFTER STEP 4:
prototype.html     prototype.html   prototype.html    prototype.html    prototype.html
spec.md            spec.md          spec.md           (edited per       (validated)
design.md          (APPENDED:       design.md          task N)
tasks.md           new feature      tasks.md
                   spec section)    (OVERWRITTEN:
                                    feature tasks)
```

---

## 5. New Manifest Files

### `prototype_large_revision/workflow.yaml` (NEW)

```yaml
id: prototype_large_revision
user_launchable: false
is_beta: true
display_name: Revise prototype (complex fix)
short_name: Prototype Revision (Large)
description: Plan and apply a multi-step structural revision to a prior prototype.
icon: Layout
version: 1
planner: skip
clarify:
  mode: skip
deliverable:
  strategy: single_file
  name: prototype.html
  revises_existing: true
context_providers:
- previous_run
seed_files: {}
steps:
# Step 1: Break the revision into discrete tasks
- agent: prototype-revision-planner
  tools: {read_files: true, write_files: true}
  strategy: single_shot
  gates: []

# Step 2: Execute each task in isolation (task_loop)
- agent: prototype-large-builder
  tools: {read_files: true, write_files: true}
  strategy: task_loop
  gates: []
  task_source:
    kind: parsed
    parser: heading_tasks
    target: tasks.md
    source_step: prototype-revision-planner
  validators:
  - html_static
  - html_render
  require_render: false
  post_step: revision_validation
  compaction: html_skeleton

# Step 3: Final validation
- agent: prototype-revision-validate
  tools: {read_files: true, write_files: true}
  strategy: single_shot
  gates: []
name: Prototype Revision (Large)
```

### `prototype_feature_revision/workflow.yaml` (NEW)

```yaml
id: prototype_feature_revision
user_launchable: false
is_beta: true
display_name: Revise prototype (feature addition)
short_name: Prototype Revision (Feature)
description: Add a new feature or page to a prior prototype.
icon: Layout
version: 1
planner: skip
clarify:
  mode: skip
deliverable:
  strategy: single_file
  name: prototype.html
  revises_existing: true
context_providers:
- previous_run
- opendesign
seed_files: {}
steps:
# Step 1: Define the new feature spec — human reviews before building
- agent: prototype-revision-feature-specify
  tools: {read_files: true, write_files: true}
  strategy: single_shot
  gates:
  - human

# Step 2: Plan the implementation — human reviews task breakdown
- agent: prototype-revision-feature-plan
  tools: {read_files: true, write_files: true}
  strategy: single_shot
  gates:
  - human

# Step 3: Build the feature (task_loop — matches main prototype build)
- agent: prototype-feature-builder
  tools: {read_files: true, write_files: true}
  strategy: task_loop
  gates: []
  task_source:
    kind: parsed
    parser: heading_tasks
    target: tasks.md
    source_step: prototype-revision-feature-plan
    spec_step: prototype-revision-feature-specify
  validators:
  - html_static
  - html_render
  require_render: true
  post_step: revision_validation
  compaction: html_skeleton

# Step 4: Final validation
- agent: prototype-revision-validate
  tools: {read_files: true, write_files: true}
  strategy: single_shot
  gates: []
name: Prototype Revision (Feature)
```

---

## 6. Backend Code Change — `run_commands.py`

### New function: `_classify_revision_tier()`

Added to `run_commands.py`. Runs a single LLM call before the WorkflowRun is created.

```python
async def _classify_revision_tier(
    instruction: str,
    parent_run_id: str,
    model_id: str | None = None,
) -> str:
    """
    Classify the revision request into a tier before minting the WorkflowRun.

    Runs a single Bedrock LLM call with the current prototype HTML and the
    revision instruction. Returns one of: "small" | "large" | "feature".

    Degrades gracefully to "small" on any error — the existing pipeline always
    runs as a safe fallback.

    Tier definitions:
      small   — targeted fix to 1-3 elements (typo, color, broken link, one field)
      large   — structural change across multiple components (3+ pages, layout rework)
      feature — new page/route/workflow that does not exist in the prototype
    """
    from app.agents.model_factory import build_model

    # Extract existing prototype HTML from the instruction message
    existing_html = _extract_existing_artifact(instruction)
    if not existing_html:
        return "small"  # no prototype content → safe fallback

    revision_text = _extract_revision_instruction(instruction) or instruction

    # Truncate HTML for classifier context (first 8000 chars sufficient for structure)
    html_excerpt = existing_html[:8000]

    classifier_prompt = f"""You are classifying a prototype revision request.

CURRENT PROTOTYPE (excerpt, {len(existing_html)} chars total):
{html_excerpt}
[...truncated if over 8000 chars...]

REVISION REQUEST:
{revision_text}

Classify this revision into EXACTLY ONE tier:

- small: A targeted change to 1-3 elements on 1-2 pages. Examples: fix a broken
  link, change a color, correct a label, add one form field, fix a typo.

- large: A structural change affecting multiple components or pages, or a bug that
  requires coordinated changes across HTML, CSS, and JavaScript. Examples: redesign
  a page layout, fix broken navigation across 5+ pages, add a complex data table
  with filtering and sorting.

- feature: A new page, new workflow, or new capability that does NOT currently exist
  in the prototype. Examples: add an onboarding flow, add a dashboard with charts,
  add authentication pages, add a new section with multiple sub-pages.

Reply with ONLY one word: small, large, or feature. No explanation."""

    try:
        from langchain_core.messages import HumanMessage
        llm = build_model(max_tokens=10)  # one word output — tiny budget
        response = await llm.ainvoke([HumanMessage(content=classifier_prompt)])
        tier = response.content.strip().lower()
        if tier in ("small", "large", "feature"):
            return tier
        # Unexpected output — default to large (safer than small for uncertain cases)
        logger.warning("_classify_revision_tier: unexpected output %r — defaulting to large", tier)
        return "large"
    except Exception as exc:
        logger.warning("_classify_revision_tier: classification failed (%s) — defaulting to small", exc)
        return "small"


# Tier → target_artifact_type mapping
_REVISION_TIER_TARGET_MAP: dict[str, str] = {
    "small":   "prototype_output",          # → prototype_revision (existing)
    "large":   "prototype_large_output",    # → prototype_large_revision (new)
    "feature": "prototype_feature_output",  # → prototype_feature_revision (new)
}
```

### Modified: `create_revision()` endpoint

The ONLY change to the endpoint — insert the classification step before minting:

```python
@router.post("/{run_id}/revisions")
async def create_revision(
    run_id: str,
    body: RevisionCommand,
    current_user: User = Depends(get_current_user),
):
    db = _get_db()
    try:
        parent = (
            db.query(WorkflowRun)
            .filter(WorkflowRun.id == run_id, WorkflowRun.user_id == current_user.id)
            .first()
        )
        if parent is None:
            raise HTTPException(status_code=404, detail="Unknown run")

        # ── NEW: classify and select the correct revision pipeline ──────
        # Only applies when the target is a prototype output — other revision
        # types (user_stories, ppt) use their own existing pipelines unchanged.
        effective_target = body.target_artifact_type
        if body.target_artifact_type == "prototype_output":
            tier = await _classify_revision_tier(
                instruction=body.instruction,
                parent_run_id=run_id,
                model_id=getattr(current_user, "preferred_model", None),
            )
            effective_target = _REVISION_TIER_TARGET_MAP.get(tier, "prototype_output")
            logger.info(
                "Prototype revision classified as %r → target=%r (run=%s)",
                tier, effective_target, run_id,
            )
        # ─────────────────────────────────────────────────────────────────

        child_run_id, _ = _mint_revision_row(
            db,
            user=current_user,
            parent_run_id=run_id,
            target_artifact_type=effective_target,    # ← uses classified target
            instruction=body.instruction,
        )
    finally:
        db.close()

    cancel_event = asyncio.Event()
    _CANCEL_EVENTS[child_run_id] = cancel_event
    event_queue = _get_or_create_queue(child_run_id)
    task = asyncio.create_task(
        _drive_revision_to_queue(
            workflow_run_id=child_run_id,
            parent_run_id=run_id,
            target_artifact_type=effective_target,    # ← uses classified target
            instruction=body.instruction,
            user=current_user,
            cancel_event=cancel_event,
            event_queue=event_queue,
        )
    )
    _PIPELINE_TASKS[child_run_id] = task
    return {"run_id": child_run_id}
```

### Also applies to the Concierge revision path

The `_dispose_concierge_proposal` function (the chat-confirm revision path) also calls `_mint_revision_row`. The same classification needs to be applied there too — same pattern, same function call, same 5-line insertion:

```python
# In _dispose_concierge_proposal, "revision" channel, around line 1385:
# Before the existing _mint_revision_row call:

if target == "prototype_output":
    tier = await _classify_revision_tier(
        instruction=instruction,
        parent_run_id=run_id,
        model_id=getattr(current_user, "preferred_model", None),
    )
    target = _REVISION_TIER_TARGET_MAP.get(tier, "prototype_output")
```

---

## 7. Entitlements Update

The two new pipeline types must be added to `entitlements.py`:

```python
# backend/app/core/entitlements.py

TIER_PIPELINES = {
    "hexaware": {
        ...
        "prototype", "prototype_revision",
        "prototype_large_revision",    # ← NEW
        "prototype_feature_revision",  # ← NEW
        ...
    },
    "pro": {
        ...
        "prototype", "prototype_revision",
        "prototype_large_revision",    # ← NEW
        "prototype_feature_revision",  # ← NEW
        ...
    },
    "enterprise": {
        ...
        "prototype", "prototype_revision",
        "prototype_large_revision",    # ← NEW
        "prototype_feature_revision",  # ← NEW
        ...
    },
}
```

---

## 8. New Agent Files

### `prototype-revision-planner/AGENT.md` (used by large tier)

**Purpose:** Break a complex revision into discrete, independently-executable tasks.  
**Reads:** `prototype.html`, `spec.md` (if present), `design.md` (if present), revision instruction  
**Writes:** `tasks.md` (overwrites the parent's tasks.md with a new plan)

Each task must:
- Be independently executable (no circular dependencies)
- Reference a specific, locatable element in prototype.html
- Include enough context that the builder agent needs no further analysis

Output format matches `heading_tasks` parser:
```markdown
## Task 1: Fix the broken navigation links on the Accounts page
The nav links in <header> point to /accounts but the route map has "account" (no s).
Update the routes map AND the nav href to use "/accounts".

## Task 2: Repair the Filter by Status dropdown on Accounts page
The <select id="status-filter"> has no onchange handler wired. Add a filterByStatus()
function and bind it to the select's onchange event.

## Task 3: Fix the broken "New Quote" button
The button calls navigateTo('/new-quote') but no route or section exists for it.
Add route + a placeholder <section data-page="new-quote"> with a basic form.
```

---

### `prototype-large-builder/AGENT.md` (used by large tier)

Same AGENT.md as described in the unified manifest proposal — reads prototype.html, executes ONE task per iteration, uses `edit_file` for surgical changes.

---

### `prototype-revision-feature-specify/AGENT.md` (used by feature tier)

**Purpose:** Define the new feature — what it is, what pages it needs, what data it uses.  
**Reads:** `prototype.html`, `spec.md`, `design.md`  
**Writes:** `spec.md` — appends a new `## [Feature Name]` section  

Output appended to spec.md:
```markdown
## Login & Authentication Feature

### Purpose
Add a complete authentication flow: login page, registration page, password
reset page, and logout functionality.

### New Pages / Routes
- /login — Email + password login form
- /register — New account registration
- /reset-password — Password reset request form

### Navigation Changes
- Header: add "Login" button (top-right, replaces current "Profile" placeholder)
- Header: show "Logout" + user avatar when authenticated

### Data Model
- currentUser: { email, name, role } | null (stored in window.appState)
- isAuthenticated: boolean (derived from currentUser !== null)

### Interactions
- Login: validates email format, shows error on wrong credentials, redirects to /
- Register: validates all fields, creates user, redirects to /login
- Logout: clears currentUser, redirects to /login
```

---

### `prototype-revision-feature-plan/AGENT.md` (used by feature tier)

**Purpose:** Translate the feature spec into an ordered task list.  
**Reads:** `spec.md` (new feature section), `prototype.html`, `design.md`  
**Writes:** `tasks.md`

Produces a `heading_tasks`-compatible plan with 6–10 tasks covering:
1. Structural HTML (new sections, routes)
2. Data model and state
3. Navigation wiring
4. Interaction handlers per page
5. Styling / design token application
6. End-to-end routing verification

---

### `prototype-feature-builder/AGENT.md` (used by feature tier)

Identical to `prototype-large-builder/AGENT.md` — same contract, same tools, same task_loop behavior. Must be a **separate agent file** declaring `pipeline_type: prototype_feature_revision` (cannot reuse the same agent id since each agent can only declare one `pipeline_type` in its frontmatter).

---

## 9. Complete File Inventory

### Create

```
backend/agents/workflows/
├── prototype_large_revision/
│   └── workflow.yaml                       ← NEW
└── prototype_feature_revision/
    └── workflow.yaml                       ← NEW

backend/agents/prompts/
├── prototype-revision-planner/
│   └── AGENT.md                            ← NEW (large tier, pipeline_type: prototype_large_revision)
├── prototype-large-builder/
│   └── AGENT.md                            ← NEW (large tier, pipeline_type: prototype_large_revision)
├── prototype-revision-feature-specify/
│   └── AGENT.md                            ← NEW (feature tier, pipeline_type: prototype_feature_revision)
├── prototype-revision-feature-plan/
│   └── AGENT.md                            ← NEW (feature tier, pipeline_type: prototype_feature_revision)
└── prototype-feature-builder/
    └── AGENT.md                            ← NEW (feature tier, pipeline_type: prototype_feature_revision)
```

> **Why separate builder agents per tier?** `list_agent_ids(pipeline_type)` scans AGENT.md files
> for exact `pipeline_type` matches. An agent can declare only one `pipeline_type`. A shared
> `prototype-revision-builder` would only appear in one tier's agent list. Separate agent files
> (`prototype-large-builder` and `prototype-feature-builder`) with identical content is the
> clean solution — each declares its own `pipeline_type`.
>
> **Note on `prototype-revision-validate`:** The existing validate agent declares
> `pipeline_type: prototype_revision`. The new manifests reference it as the final step.
> The engine resolves step agents by id via `load_agent_spec(agent_id)` (not by registry
> membership scan), so step execution works. However, `get_pipeline_agents("prototype_large_revision")`
> (used by `_mint_revision_row` existence gate and `_handle_revision` pre-dispatch check) will
> NOT include `prototype-revision-validate` in its returned list, since its AGENT.md declares a
> different `pipeline_type`. This means the existence check returns a non-empty list (the planner
> + builder agents), so it passes. The engine then compiles the manifest and resolves each step
> agent individually. This works correctly — **no change needed** to `prototype-revision-validate`.

### Modify

```
backend/app/api/run_commands.py
  ├─ Add _classify_revision_tier() function  ← ~60 lines
  ├─ Add _REVISION_TIER_TARGET_MAP dict      ← 5 lines
  ├─ Modify create_revision() endpoint       ← +10 lines
  └─ Modify _dispose_concierge_proposal()    ← +8 lines  ⚠️ (base_type fix required, see §6b gap)

backend/app/core/entitlements.py
  └─ Add 2 new pipeline types per tier       ← +8 lines

backend/agents/registry.py
  └─ Add 2 entries to REVISION_BASE_MAP      ← +2 lines  ⚠️ CRITICAL

backend/app/api/runs.py
  └─ Extend _canonical_base() helper         ← +3 lines  ⚠️ NEW GAP (see §6c)

backend/agents/prompts/<each new agent>/AGENT.md
  └─ Must declare correct pipeline_type in frontmatter ← per agent  ⚠️ CRITICAL

backend/agents/workflows/prototype_revision/workflow.yaml
  └─ No change (small tier uses existing)    ← UNCHANGED
```

### No Change Needed

```
backend/agents/execution_engine/engine.py       ← SC-001: zero engine edits
backend/agents/capabilities/context_providers/  ← previous_run works unchanged
backend/app/api/run_stream.py                   ← SSE transport unchanged
frontend/src/components/layout/DashboardLayout  ← revision trigger unchanged (but see §6a–§6b)
backend/agents/prompts/prototype-revision-agent ← small tier reuses existing
backend/agents/prompts/prototype-revision-validate ← all tiers reuse this (see note above)
```

> ⚠️ **One additional frontend change required** — `PreviewPanel.tsx` must be updated to normalize the two new pipeline types to the prototype renderer. See section 6a below.

---

## 6a. Required Frontend Change — `PreviewPanel.tsx`

The `PreviewPanel` normalizes `WorkflowRun.type` to a base render type on **line 575**. It currently handles `prototype_revision` → `"prototype"` but not the two new types. Without this fix, the prototype preview renderer never fires for large/feature revisions — the output won't display.

### File to modify

```
frontend/src/components/preview/PreviewPanel.tsx
```

### Change (2 lines added)

```typescript
// BEFORE (line 575):
const renderType = detectedType === "user_stories_revision" ? "user_stories"
  : detectedType === "ppt_revision" ? "ppt"
  : detectedType === "prototype_revision" ? "prototype"
  : detectedType === "app_builder_revision" ? "app_builder"
  : detectedType;

// AFTER:
const renderType = detectedType === "user_stories_revision" ? "user_stories"
  : detectedType === "ppt_revision" ? "ppt"
  : detectedType === "prototype_revision" ? "prototype"
  : detectedType === "prototype_large_revision" ? "prototype"    // ← ADD
  : detectedType === "prototype_feature_revision" ? "prototype"  // ← ADD
  : detectedType === "app_builder_revision" ? "app_builder"
  : detectedType;
```

### Why this is needed

`renderType` drives which preview component renders and which content slot is used. Without these two entries, `prototype_large_revision` and `prototype_feature_revision` fall through to the `detectedType` catch-all — which is not in `KNOWN_RENDER_TYPES = ["user_stories", "ppt", "prototype", "app_builder"]`. The generic deliverable fallback path kicks in instead, and the prototype HTML is rendered incorrectly (or not at all).

> **Note:** This is the only frontend change in Option B. Option A (Unified Manifest) requires zero frontend changes because the pipeline type always stays `prototype_revision`.

---

## 6b. Required Backend Change — `agents/registry.py`

### Why it matters

`PIPELINE_AGENTS` is built at import time by scanning `agents/prompts/` for AGENT.md files that declare each `pipeline_type`. `get_pipeline_agents("prototype_large_revision")` will return `[]` unless the new agents' AGENT.md files declare `pipeline_type: prototype_large_revision`. An empty list hits the fail-fast guard in both `_mint_revision_row()` (400 error before the run is created) and `engine._handle_revision()` (ValueError mid-dispatch).

### Change 1 — New agents' AGENT.md frontmatter must declare correct `pipeline_type`

Every new AGENT.md must declare the pipeline type it belongs to:

```yaml
# prototype-revision-planner/AGENT.md
---
id: prototype-revision-planner
pipeline_type: prototype_large_revision   ← MUST match the new manifest id
order: 1
...
---

# prototype-large-builder/AGENT.md
---
id: prototype-large-builder
pipeline_type: prototype_large_revision
order: 2
...
---

# prototype-revision-feature-specify/AGENT.md
---
id: prototype-revision-feature-specify
pipeline_type: prototype_feature_revision  ← must match feature manifest id
order: 1
---

# prototype-revision-feature-plan/AGENT.md
---
id: prototype-revision-feature-plan
pipeline_type: prototype_feature_revision
order: 2
---

# prototype-feature-builder/AGENT.md
---
id: prototype-feature-builder
pipeline_type: prototype_feature_revision
order: 3
---
```

### Change 2 — `REVISION_BASE_MAP` must include the new types

```python
# backend/agents/registry.py

REVISION_BASE_MAP: dict[str, str] = {
    "ppt_revision": "ppt",
    "user_stories_revision": "user_stories",
    "prototype_revision": "prototype",
    "prototype_large_revision": "prototype",    # ← ADD
    "prototype_feature_revision": "prototype",  # ← ADD
    "app_builder_revision": "app_builder",
    "custom_revision": "custom",
}
```

This map is used by the engine when resolving the parent artifact for revision runs. Without it, `_handle_revision()` cannot find the correct parent deliverable.

### Change 3 — `SUPPORTED_PIPELINE_TYPES` auto-registers from `workflow.yaml`

`SUPPORTED_PIPELINE_TYPES` (in `agents/loader.py`) is derived from:
1. Directory names under `agents/workflows/` that contain a `workflow.yaml`
2. `pipeline_type` fields declared in AGENT.md files

Since we are creating new `workflow.yaml` directories (`prototype_large_revision/` and `prototype_feature_revision/`), these will be **auto-registered** in `SUPPORTED_PIPELINE_TYPES` — **no change to loader.py is needed** for this. The directories themselves are sufficient.

---

## 6c. Required Backend Change — `runs.py` `_canonical_base` (NEW GAP)

**File:** `backend/app/api/runs.py`

The `_canonical_base()` helper (introduced by FIX-179) normalizes run types for the BFS cross-family isolation guard in `_owned_family_members`. It strips `_revision` then `od_`:

```python
# Current (FIX-179):
def _canonical_base(t: str) -> str:
    return t.removesuffix("_revision").removeprefix("od_")
```

For `prototype_large_revision`, `removesuffix("_revision")` gives `"prototype_large"` — not `"prototype"`. The BFS guard would exclude `prototype_large_revision` and `prototype_feature_revision` child runs from a `prototype` root's family, causing the version picker (`VersionTimeline`) to show only v1 for any prototype run that spawned a large or feature revision. This is exactly the class of bug FIX-179 fixed for `od_prototype`.

**Fix:**
```python
def _canonical_base(t: str) -> str:
    """Strip tiered or generic ``_revision`` suffix then ``od_`` variant prefix."""
    base = t
    for suffix in ("_large_revision", "_feature_revision", "_revision"):
        if base.endswith(suffix):
            base = base[: -len(suffix)]
            break
    return base.removeprefix("od_")
# "prototype_large_revision"   → "prototype" ✓
# "prototype_feature_revision" → "prototype" ✓
# "prototype_revision"         → "prototype" ✓ (unchanged)
# "prototype"                  → "prototype" ✓ (unchanged)
```

---

## 6d. Required Frontend Change — `DashboardLayout.tsx` `laneActiveContent` (NEW GAP)

**File:** `frontend/src/components/layout/DashboardLayout.tsx`, line ~1997

```typescript
// Current:
const laneActiveContent =
  effectiveReviseType === "ppt" || effectiveReviseType === "ppt_revision"
    ? pptContent
  : effectiveReviseType === "prototype" || effectiveReviseType === "prototype_revision"
    ? prototypeContent
  : userStoryContent;
```

For `prototype_large_revision` or `prototype_feature_revision`, `laneActiveContent` falls through to `userStoryContent` (empty). This drives `laneDerivedFilename` (the filename shown in the chat lane Run Summary deliverable card) and the `pipelineType` prop passed to `RunChatLane`. The deliverable card shows a wrong filename and the content is blank.

**Fix:**
```typescript
const laneActiveContent =
  effectiveReviseType === "ppt" || effectiveReviseType === "ppt_revision"
    ? pptContent
  : effectiveReviseType === "prototype"
    || effectiveReviseType === "prototype_revision"
    || effectiveReviseType === "prototype_large_revision"    // ← ADD
    || effectiveReviseType === "prototype_feature_revision"  // ← ADD
    ? prototypeContent
  : userStoryContent;
```

---

| Invariant | Compliance | Notes |
|---|---|---|
| **SC-001** | ✅ | New workflows are manifest + AGENT.md. One backend function added to routing layer (not engine). |
| **INV-1** | ⚠️ | `_classify_revision_tier` checks `body.target_artifact_type == "prototype_output"`. This is NOT a `pipeline_type` branch in the kernel — it lives in the app-layer REST endpoint, which is the sanctioned location for routing decisions. |
| **INV-3** | ✅ | `prototype_revision` golden unchanged. New manifests have no goldens yet. |
| **INV-12** | ✅ | `task_loop` reused. `_drive_revision_to_queue` unchanged (same function, different `target_artifact_type`). |
| **INV-13** | ✅ | All agents use `deepagents` via existing runner. |

---

## 11. Comparison: Pieces 1/2/3 vs Piece 4

| Dimension | Pieces 1/2/3 (Multi-Manifest) | Piece 4 (Unified Manifest) |
|---|---|---|
| **Number of manifests** | 3 (small=existing, large=new, feature=new) | 1 (unified, replaces existing) |
| **Backend code change** | Yes — `_classify_revision_tier()` + routing in 2 endpoints (~80 lines) | No — zero backend changes |
| **Classification timing** | BEFORE run is created (pre-mint) | DURING run (step 1 of pipeline) |
| **User sees classification** | Not visible (happens silently before SSE) | Visible — "Preparing revision…" in Steps panel as classifier runs |
| **Small revision overhead** | 1 extra LLM call (classifier) before run starts | 2 extra LLM calls (classifier step + planner step) |
| **Feature tier gates** | 2 human review gates (spec + plan) | No human gates (planner runs unattended) |
| **Pipeline isolation** | Each tier is a completely independent pipeline | One pipeline handles all tiers via adaptive planner |
| **Debuggability** | `WorkflowRun.type` shows the exact tier used (`prototype_large_revision`, etc.) | `WorkflowRun.type` is always `prototype_revision` |
| **Registry changes** | `REVISION_BASE_MAP` +2 entries; each new AGENT.md must declare correct `pipeline_type` | No registry changes — single manifest, single pipeline type |
| **Entitlement complexity** | 2 new pipeline types need entitlement entries | No entitlement changes |
| **Files changed (frontend)** | 7 files — `PreviewPanel.tsx`, `dashboard/page.tsx`, `DashboardLayout.tsx`, `runs.py` | 0 — pipeline type always `prototype_revision` |
| **Rollback safety** | Small tier is completely untouched | Existing `prototype_revision` manifest is replaced |

---

## 12. Recommended Decision Criteria

**Choose Pieces 1/2/3 (Multi-Manifest) if:**
- You want human review gates on feature revisions (approve spec before build starts)
- You want `WorkflowRun.type` to explicitly record which tier ran (for analytics/debugging)
- You want the small revision pipeline to remain completely unchanged (zero risk)
- You are comfortable with the backend routing function (it's in the app layer, not the kernel)

**Choose Piece 4 (Unified Manifest) if:**
- You want zero backend code changes (pure manifest + AGENT.md)
- You want the classification visible to the user in the Steps panel
- You want a single manifest to maintain going forward
- You are comfortable with the classifier being a paid LLM step that users see

---

*Last updated: 2026-08-20 | Full code-trace audit complete | Branch: feat/tiered-prototype-revision*


---

## 13. Complete Change Checklist (Full Audit — 2026-08-20)

This section is the authoritative list of every file that needs changing for Option B to work end-to-end. Incorporates all gaps discovered during the 2026-08-20 full code trace including the naming correction, the `_canonical_base` gap, the concierge `base_type` derivation bug, and the `laneActiveContent` gap.

### Backend Changes

| # | File | Change | Why needed |
|---|---|---|---|
| B1 | `backend/app/api/run_commands.py` | Add `_classify_revision_tier()` + `_REVISION_TIER_TARGET_MAP` | Core routing logic |
| B2 | `backend/app/api/run_commands.py` | Modify `create_revision()` — call classifier before minting | REST trigger path |
| B3 | `backend/app/api/run_commands.py` | Modify `_dispose_concierge_proposal()` — fix `base_type` derivation for new types + call classifier | Chat/Concierge trigger path; `removesuffix("_revision")` on `"prototype_large_revision"` gives `"prototype_large"`, not `"prototype"` — needs an explicit remap |
| B4 | `backend/app/core/entitlements.py` | Add `prototype_large_revision` + `prototype_feature_revision` to `hexaware`, `pro`, `enterprise` tiers | `can_run_pipeline()` gate in `_mint_revision_row()` will 403 without this |
| B5 | `backend/agents/registry.py` | Add 2 entries to `REVISION_BASE_MAP` | Engine uses this to find parent artifact type; fails silently without it |
| B6 | `backend/agents/prompts/<new-agent>/AGENT.md` | Declare `pipeline_type: prototype_large_revision` or `prototype_feature_revision` in each new agent's frontmatter | `PIPELINE_AGENTS` is auto-discovered from disk; without correct `pipeline_type`, `get_pipeline_agents()` returns `[]` → 400 error from `_mint_revision_row` and ValueError from `_handle_revision` |
| B7 | `backend/agents/workflows/prototype_large_revision/workflow.yaml` | Create new manifest | The pipeline itself |
| B8 | `backend/agents/workflows/prototype_feature_revision/workflow.yaml` | Create new manifest | The pipeline itself |
| B9 | `backend/app/api/runs.py` | Extend `_canonical_base()` to handle tiered revision suffixes | Without this, revision family BFS excludes `prototype_large_revision` / `prototype_feature_revision` children from the prototype root — version picker shows only v1 (same class of bug as FIX-179) |

### Frontend Changes

| # | File | Change | Why needed |
|---|---|---|---|
| F1 | `frontend/src/components/preview/PreviewPanel.tsx` line 575 | Add 2 ternaries to `renderType` normalization | Without this, `prototype_large_revision/feature_revision` fall through to generic deliverable renderer — prototype HTML displays incorrectly |
| F2 | `frontend/src/app/dashboard/page.tsx` line ~1050 | Add 2 new types to `pipeline_complete` content routing | `setPrototypeContent(finalOutput)` never called → preview panel stays empty on live run completion |
| F3 | `frontend/src/app/dashboard/page.tsx` line ~2474 | Add 2 new types to history reopen content routing | `setPrototypeContent(fullRun.output)` never called → preview stays empty on history reopen |
| F4 | `frontend/src/components/layout/DashboardLayout.tsx` line ~1816 | Add 2 new types to `effectiveReviseType → activeReviseHandler` | Without this, the "Revise" button for a `prototype_large_revision` run does nothing (no handler selected) |
| F5 | `frontend/src/components/layout/DashboardLayout.tsx` lines ~1359, ~1506, ~1593, ~1683, ~1723 | Add 2 new types to `isProtoType` notification checks | Without this, prototype-tier notifications are misclassified/missed for large/feature runs |
| F6 | `frontend/src/components/layout/DashboardLayout.tsx` lines ~1467, ~1561 | Add 2 new types to `isHtmlOutput` chain fallback check | Affects chain suggestion detection after revision completion |
| F7 | `frontend/src/components/layout/DashboardLayout.tsx` line ~1997 | Add 2 new types to `laneActiveContent` computation | Without this, `laneActiveContent` falls through to `userStoryContent` for large/feature runs — the chat lane Run Summary deliverable card shows wrong filename and blank content |

### What is Already Generic (No Change Needed)

| # | Location | Why it already works |
|---|---|---|
| G1 | `run_commands.py` `endsWith("_revision")` checks | All 5 occurrences use suffix check — new types end in `_revision` ✓ |
| G2 | `page.tsx` `isRevisionCompletion` | Uses `endsWith("_revision")` — generic ✓ |
| G3 | `page.tsx` `parent_run_id` assignment on mint | Uses `endsWith("_revision")` — generic ✓ |
| G4 | `PIPELINE_AGENTS` discovery | Auto-scans AGENT.md files — no manual registration needed ✓ |
| G5 | `SUPPORTED_PIPELINE_TYPES` | Auto-derives from `workflow.yaml` dirs — no change needed ✓ |
| G6 | `_drive_revision_to_queue()` | Completely generic — runs any manifest ✓ |
| G7 | SSE `pipeline_start` handler in `useWorkflow.ts` | Fully generic, stores `pipeline_type` verbatim ✓ |
| G8 | `allowed_custom_agent_ids` in `registry.py` | Uses `endsWith("_revision")` — already tight for new types ✓ |
| G9 | Revision family BFS (`/api/runs/{id}/family`) — direct `parent_run_id` BFS walk | Keys on `parent_run_id` — generic ✓ (but `_canonical_base` still needs fixing for cross-type isolation guard — B9) |
| G10 | `contentSourceRunId` advance on `pipeline_complete` | Uses `isRevisionCompletion` (generic suffix check) ✓ |

---

### Quick Reference: Code Changes by File

#### `frontend/src/app/dashboard/page.tsx`

```typescript
// 1. pipeline_complete content routing (line ~1050):
} else if (pipelineType === "prototype" || pipelineType === "prototype_revision"
  || pipelineType === "prototype_large_revision"      // ← ADD
  || pipelineType === "prototype_feature_revision") { // ← ADD
  setPrototypeContent(finalOutput);

// 2. History reopen content routing (line ~2474):
} else if (fullRun.type === "prototype" || fullRun.type === "prototype_revision"
  || fullRun.type === "prototype_large_revision"      // ← ADD
  || fullRun.type === "prototype_feature_revision") { // ← ADD
  setPrototypeContent(fullRun.output);
```

#### `frontend/src/components/preview/PreviewPanel.tsx`

```typescript
// renderType normalization (line 575):
const renderType = detectedType === "user_stories_revision" ? "user_stories"
  : detectedType === "ppt_revision" ? "ppt"
  : detectedType === "prototype_revision" ? "prototype"
  : detectedType === "prototype_large_revision" ? "prototype"    // ← ADD
  : detectedType === "prototype_feature_revision" ? "prototype"  // ← ADD
  : detectedType === "app_builder_revision" ? "app_builder"
  : detectedType;
```

#### `frontend/src/components/layout/DashboardLayout.tsx`

```typescript
// activeReviseHandler selection (line ~1816):
(effectiveReviseType === "prototype"
  || effectiveReviseType === "prototype_revision"
  || effectiveReviseType === "prototype_large_revision"      // ← ADD
  || effectiveReviseType === "prototype_feature_revision"    // ← ADD
  || !!prototypeContent) ? handleRevisePrototype :

// isProtoType check (at ~5 locations, each like):
const isProtoType = resolvedTypeStr === "prototype"
  || resolvedTypeStr === "prototype_revision"
  || resolvedTypeStr === "prototype_large_revision"      // ← ADD
  || resolvedTypeStr === "prototype_feature_revision";   // ← ADD

// isHtmlOutput check (at ~2 locations):
workflowType === "prototype" || workflowType === "prototype_revision"
  || workflowType === "prototype_large_revision"         // ← ADD
  || workflowType === "prototype_feature_revision"       // ← ADD

// laneActiveContent (line ~1997):  ← NEW GAP (F7)
: effectiveReviseType === "prototype"
  || effectiveReviseType === "prototype_revision"
  || effectiveReviseType === "prototype_large_revision"    // ← ADD
  || effectiveReviseType === "prototype_feature_revision"  // ← ADD
  ? prototypeContent
```

#### `backend/agents/registry.py`

```python
REVISION_BASE_MAP: dict[str, str] = {
    "ppt_revision": "ppt",
    "user_stories_revision": "user_stories",
    "prototype_revision": "prototype",
    "prototype_large_revision": "prototype",    # ← ADD
    "prototype_feature_revision": "prototype",  # ← ADD
    "app_builder_revision": "app_builder",
    "custom_revision": "custom",
}
```

#### `backend/app/core/entitlements.py`

```python
TIER_PIPELINES = {
    "hexaware":   { ..., "prototype_large_revision", "prototype_feature_revision" },  # ← ADD
    "pro":        { ..., "prototype_large_revision", "prototype_feature_revision" },  # ← ADD
    "enterprise": { ..., "prototype_large_revision", "prototype_feature_revision" },  # ← ADD
}
```

#### `backend/app/api/run_commands.py` — `_dispose_concierge_proposal` (B3 gap)

```python
# In _dispose_concierge_proposal, revision channel, BEFORE the existing base_type derivation:
# Fix: new tiered revision types are already the pipeline type — strip back to prototype base.
if wr_type in ("prototype_large_revision", "prototype_feature_revision"):
    base_type = "prototype"
else:
    base_type = wr_type.removesuffix("_revision") if wr_type.endswith("_revision") else wr_type

target = params.get("target") or f"{base_type}_output"

# Then apply the classifier ONLY for prototype_output targets:
if target == "prototype_output":
    tier = await _classify_revision_tier(
        instruction=instruction,
        parent_run_id=run_id,
        model_id=getattr(current_user, "preferred_model", None),
    )
    target = _REVISION_TIER_TARGET_MAP.get(tier, "prototype_output")
```

#### `backend/app/api/runs.py` — `_canonical_base` (B9 — new gap)

```python
# Current (FIX-179):
def _canonical_base(t: str) -> str:
    """Strip generic ``_revision`` suffix then ``od_`` variant prefix."""
    return t.removesuffix("_revision").removeprefix("od_")

# Fix — also handle tiered revision suffixes:
def _canonical_base(t: str) -> str:
    """Strip tiered or generic ``_revision`` suffix then ``od_`` variant prefix."""
    base = t
    for suffix in ("_large_revision", "_feature_revision", "_revision"):
        if base.endswith(suffix):
            base = base[: -len(suffix)]
            break
    return base.removeprefix("od_")
# Result: "prototype_large_revision" → "prototype" ✓
#         "prototype_feature_revision" → "prototype" ✓
#         "prototype_revision" → "prototype" ✓  (unchanged from today)
```

---

*Last updated: 2026-08-20 | Full code-trace audit complete | Branch: feat/tiered-prototype-revision*
