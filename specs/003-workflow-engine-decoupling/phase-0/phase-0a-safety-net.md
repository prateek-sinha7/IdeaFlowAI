# Phase 0A — Safety net + deletion guard (detailed plan)

> **Goal:** pin today's behavior with characterization snapshots (deliverable + semantic events) for
> 5 pipelines, and arm the two deletion guards — the **migration-ledger CI guard** and the
> **import-linter** contract — so every later phase's deletions are enforced. **No runtime behavior
> change.** This is the regression oracle for 0B/0C and all of 003.
>
> **Accept (003 §25):** snapshots recorded + green; ledger guard + import-linter run green in CI.

Parent: [Phase 0 README](README.md) · Next: [0B](phase-0b-execution-context.md)

---

## A. Workstream A — Characterization tests

### A0. Pre-reqs (already in the repo — reuse, don't rebuild)

- `backend/tests/agents/_scripted_model.py` — `ScriptedFakeChatModel`, `_ScriptedTurn`, `_scripts_for`, `_drive`. The proven offline engine driver.
- `backend/tests/agents/test_phase3_cutover_verify.py` — the event-vocabulary characterization template.
- pytest config: `backend/pyproject.toml [tool.pytest.ini_options]` (`testpaths=["tests"]`, `python_files=["test_*.py"]`, strict asyncio — every async test needs `@pytest.mark.asyncio`). Run: `cd backend && python3.11 -m pytest tests/characterization -v`.

### A1. Decide snapshot tooling, then add the harness layer

Per [README §8 D-1] recommend **`syrupy`** (pin in `requirements-dev.txt`). The characterization layer is a thin wrapper over `_drive`:

```
backend/tests/characterization/
├── conftest.py            # normalize_events(), run_pipeline_chars(), gate/clarify auto-drivers, singleton resets
├── __snapshots__/         # syrupy snapshots (committed)
├── test_char_prototype.py
├── test_char_od_prototype.py
├── test_char_prototype_revision.py
├── test_char_ppt.py        # ppt AND od_ppt
└── test_char_app_builder.py
```

Each test does, in essence:

```python
@pytest.mark.asyncio
async def test_prototype_characterization(snapshot, char_harness):
    result = await char_harness.run("prototype")           # extends _drive
    assert result.events == snapshot                        # normalized semantic event stream
    assert result.deliverable == snapshot                   # raw deliverable bytes
    assert result.final_status == "completed"               # WorkflowRun.status (where applicable)
```

`char_harness.run(pipeline_type)` returns `{events: list[dict] (normalized), deliverable: str, final_status: str}`. It builds on `_drive` but **records the deliverable** (`pipeline_complete.data.final_output` before normalization strips it) and **auto-drives gates/clarify** (A5).

### A2. The normalization contract (verified field list)

One shared `normalize_events(events) -> list[dict]` in `conftest.py`. Events are uniformly `{"type": str, "data": {...}}`. Apply to every event's `data`:

**Drop entirely** (purely volatile): `timestamp`, `duration`, `total_duration`, `input_tokens`, `output_tokens`, `total_tokens`, `total_input_tokens`, `total_output_tokens`, `estimated_cost_usd`, `output_length`, `summary_length`, `full_output_length`.

**Replace with a stable placeholder** (volatile identity, but presence/shape matters): `pipeline_run_id` → `"<run>"`, `gate_key` → `"<run>:<agent>"`, `model_id` → `"<model>"`.

**Normalize, don't drop:** collapse consecutive `agent_chunk` events per `agent_id` into one `{"type":"agent_chunk","data":{"agent_id":..,"chunk":<joined>}}` (chunk boundaries are script-driven).

**Keep (stable — these ARE the behavior):** event `type` + order; `agent_id`/`name`/`role`/`icon`/`index`/`total`; `satisfiable`/`dag_edges`/`unresolved_edges`; `verdict`/`execution_gate`; `task_number`/`total_tasks`/`completed_count`/`completed_tasks[].number`/`.title`; `tool`/`args` keys (values for FS tools are deterministic canned content → keep); `recoverable`/`code`; `agents[]` ordering in `pipeline_start`.

**Assert the net is tight:** after normalization, `assert` no event `data` contains any dropped key (guards against R0-2 — a new volatile field silently entering a snapshot).

Filter **WS-only noise** that never comes from `execute()` (the harness drives the engine generator directly, so these shouldn't appear, but filter defensively): `pipeline_heartbeat`, `pipeline_reconnected`, `title_update`. Also drop the internal control signals `_gate_rejected`/`_gate_edited` (never client-facing; consumed inside `_run_agent`).

> **Snapshot the raw engine generator**, not a caller's reshaped stream. The two production callers reshape differently — `websocket.py` wraps each event as `{type, chunk:null, section, data}` (`websocket.py:~1281`); `ndjson_adapter.py` flattens and renames `final_output→final_html` (`ndjson_adapter.py:73-79`). Capture the canonical engine `{type,data}` stream once; add **thin separate** assertions for each caller's transform if desired (optional, low priority).

### A3. The 24-event vocabulary (reference — for the normalizer and review)

Verified emit sites. V = volatile (drop/placeholder per A2), S = stable (keep).

| event `type` | emit | stable `data` keys (S) | volatile keys (V) |
|---|---|---|---|
| `workflow_validated` | `engine.py:659` | satisfiable, dag_edges[], unresolved_edges[] | pipeline_run_id, timestamp |
| `error` | `engine.py:676` | code, recoverable | error (may embed ids) |
| `planner_start` | `:716` | pipeline_type | pipeline_run_id, timestamp |
| `planner_timeout` | `:1086` | elapsed_seconds | pipeline_run_id, timestamp |
| `planner_complete` | `:1090` | execution_gate (+ planner_timed_out/pipeline_type in ctx) | pipeline_run_id, timestamp, most of planning_context |
| `gate_status` | `:1099` | verdict | pipeline_run_id, timestamp |
| `questionnaire_ready` | `clarify_engine.py:113` | questions[] (deterministic: question_id, answer_type, options, impact_level, ambiguity_category, recommended_answer), round | pipeline_run_id, timestamp |
| `questionnaire_complete` | `clarify_engine.py:134` | responses[], updated_gate | pipeline_run_id, timestamp |
| `clarification_limit_reached` | `clarify_engine.py:152` | unresolved_items[] | pipeline_run_id, timestamp |
| `pipeline_start` | `:845` | pipeline_type, agent_count, agents[]{id,name,role,icon,order} | pipeline_run_id |
| `agent_start` | `:1138` | agent_id, name, role, icon, index, total | — |
| `agent_input` | `:1154` | agent_id, context_sources[] structure | pipeline_run_id, timestamp, context_message, *_length |
| `agent_chunk` | `:1256` | agent_id | chunk (normalize: join per agent) |
| `tool_call` | `:1272` | agent_id, tool, args keys (FS values deterministic) | summary (report_task_complete) |
| `tool_result` | `:1274` | agent_id, tool | result |
| `task_progress` | `:1280` | completed_count, completed_tasks[].number/.title | pipeline_run_id, timestamp, completed_tasks[].summary |
| `task_loop_progress` | `:1539` | task_number, total_tasks | pipeline_run_id, timestamp |
| `agent_complete` | `:1376` | agent_id, name, index, total | duration, output_length, *_tokens |
| `agent_error` | `:1310/1360/1428/1443` | agent_id, recoverable | error |
| `review_gate_ready` | `:1949` | agent_id, agent_name | pipeline_run_id, gate_key, timestamp, output |
| `review_gate_approved` | `:1981` | agent_id, edited | pipeline_run_id, timestamp |
| `pipeline_complete` | `:995` | pipeline_type, agents_completed, agents_total | pipeline_run_id, total_duration, final_output (= deliverable, captured separately), all tokens/cost, model_id |
| `pipeline_cancelled` | `:889/1408` | reason | pipeline_run_id, duration, agents_completed |
| `state_restoration_failed` | `:2230` (`_handle_revision` only) | — | all |

`planning_context` is LLM-derived → treat the whole dict as V except `execution_gate`/`pipeline_type`/`planner_timed_out`. (The harness stubs `_run_planner`→PROCEED, so for non-prototype pipelines clarify runs but the planner context is the deterministic default — confirm against §9 SKIP_PLANNER finding.)

### A4. Per-pipeline fixtures

Common requirements (verified):
- `prototype`, `od_prototype`, `od_ppt` **require** an `od_context` with `template_body` or the factory raises `TemplateMissingError` before any agent runs (`factory.py:330-335`). Supply a minimal one.
- `ppt` specs must be loaded from `PIPELINE_AGENTS["ppt"]` (NOT `get_pipeline_agents("ppt")`, which returns `[]`).
- Code-gen agents must **`write_file`** to disk (the deliverable is read from disk, not the text stream).
- `prototype-build`'s script feeds **every per-task call AND** the fix-loop's internal `create_runner` — keep `turns[-1]` a benign text turn.
- Each run needs a **unique** `pipeline_run_id` (StateMachine singleton rejects reuse).

**A4.1 `prototype`** — agents (registry.py:75-80): `prototype-specify` (gate Human_Gate) → `prototype-plan` (gate Human_Gate) → `prototype-build` (task-loop) → `prototype-validate`. Pass `gate_agent_ids=[]` to suppress both gates for a clean snapshot (or auto-approve, A5).
- `od_context`: `{template_body, template_id:"web-prototype", ds_id:"default", ds_body:":root{--bg:#fff;--fg:#111;--accent:#06f;--surface:#f6f6f6;--border:#ddd;--muted:#888;}", craft_block, is_design_system_required:True}`.
- scripts: `prototype-specify`→text `<spec>…</spec>`; `prototype-plan`→text with **`## Task 1:` / `## Task 2:` headers** (drives a 2-iteration loop); `prototype-build` turn 1→`write_file("prototype.html", CANNED_HTML)` + `report_task_complete(1,…)`, turn 2→text "Done." (reused for task 2 + fixes); `prototype-validate`→text.
- `CANNED_HTML` must **pass `static_check`** (valid nav links, sections) so the fix-loop never fires → byte-stable deliverable, no render dependency. (A second fixture variant with a deliberate `static_check` failure can pin the fix-loop branch — optional.)
- deliverable: `sandbox.read("prototype.html") == CANNED_HTML` verbatim.

**A4.2 `od_prototype`** — same agents (`get_pipeline_agents("prototype")`) + same scripts; pass `pipeline_type="od_prototype"`. Pins the `od_prototype` strings in `_PROTOTYPE_PIPELINE_TYPES` (L1) and the read-back branch (L10).

**A4.3 `prototype_revision`** — agent (registry.py:83-85): `prototype-revision-agent` (tools `workspace`). 
- `user_message` **exact wrappers** (engine parses these):
  ```
  === EXISTING PROTOTYPE HTML ===
  <!doctype html><html><body><section data-page="home">…</section></body></html>
  === END EXISTING HTML ===

  === REVISION REQUEST ===
  Add a dark mode toggle to the header.
  === END REQUEST ===
  ```
- **parent seeding** (to pin L4/L16): pre-create a parent sandbox on disk with the SAME `user_id` + `runs_root`:
  ```python
  parent = RunSandbox(user_id="harness-user", run_id=parent_run_id, runs_root=tmp); parent.ensure()
  parent.write("spec.md", "..."); parent.write("design.md", "..."); parent.write("tasks.md", "## Task 1: …")
  ```
  pass `user_id="harness-user", parent_run_id=parent_run_id`.
- scripts: `prototype-revision-agent` turn 1→`edit_file("prototype.html", old, new)` (engine seeds the file pre-run; `write_file` would refuse to overwrite), turn 2→text (reused by the post-revision fix-loop's internal runner).
- deliverable: `sandbox.read("prototype.html")` (edited in place). Optional second variant: omit the tool call to pin the streamed-HTML/original fallbacks (`engine.py:365-367`).

**A4.4 `ppt` + `od_ppt`** — agents (registry.py:46-57, all `tools:[]` text-only): `od-ppt-brief-analyst` → `od-ppt-composer` → `od-ppt-validator`. No gates. `od_context`: `{template_body:"…carousel…", template_id:"html-ppt", ds_id:"none", ds_body:"", craft_block:"", is_design_system_required:False}`.
- scripts — `od-ppt-composer` and `od-ppt-validator` emit the **canned `<artifact>` carousel deck** below (exercises BOTH `_unwrap_artifact` and `_sanitize_carousel_deck_html`):
  ```html
  <artifact identifier="deck" type="text/html" title="Demo Deck">
  <!doctype html><html><head><style>
  .stage{display:flex;transition:transform .3s}
  .slide{min-width:100vw;display:grid}
  .slide:not(.active){display:none}
  .slide.active{display:block;box-shadow:0 0 4px}
  @media print{.slide{display:block !important}}
  </style></head><body>
  <div class="stage" style="transform:translateX(-100vw)">
  <section class="slide active">Slide 1</section>
  <section class="slide">Slide 2</section>
  </div></body></html>
  </artifact>
  ```
- deliverable: unwrapped (no `<artifact>`) + sanitized (`.slide:not(.active){display:none}` removed; `display` stripped from `.slide.active`; `.slide{…display:grid}` and `@media print` kept). **Pin both** in the snapshot.
- Two tests: one `pipeline_type="od_ppt"` (specs via `get_pipeline_agents("od_ppt")`), one `pipeline_type="ppt"` (specs via `[load_agent_spec(a) for a in PIPELINE_AGENTS["ppt"]]`).

**A4.5 `app_builder` (code-gen)** — 15 agents (registry.py:88-104), no gates. `od_context=None`. Only workspace-tool agents write; for a minimal stable bundle, script `app-code-generator` turn 1→`write_file("src/app.py","print('hello')\n")` + `write_file("README.md","# Generated App\n")`, turn 2→text; all other agents→one benign text turn each.
- deliverable: `serialize_sandbox_deliverable(sandbox.root)` →
  ```
  ```filename: README.md
  # Generated App
  ```

  ```filename: src/app.py
  print('hello')
  ```
  ```
  (sorted by relpath, joined by blank line, `PLANNER.md` excluded). Assert `final_output == serialize_sandbox_deliverable(sandbox.root)` and no `<artifact>` unwrap applied.

### A5. Gate & clarify auto-drivers (in `conftest.py`)

For pipelines that pause, the harness must resume them deterministically (or suppress). Two mechanisms (both via the **global `ArtifactStore` singleton** — reset/isolate it per test):

- **Review gate** (prototype-specify/prototype-plan default to `gate: Human_Gate`): either pass `gate_agent_ids=[]` to disable all gates (simplest, cleanest snapshot — `_should_gate` returns False for everyone), **or** watch the stream for `review_gate_ready`, read `data.gate_key`, and call `await store.set_review_response(gate_key, approved=True, edited_content=None)`. Response shape: `{"approved": bool, "edited_content": str|None}`.
- **Clarify gate** (ppt/code-gen with `ALWAYS_CLARIFY` — though `_drive` sets it False; if a fixture wants to pin the clarify path, set it True): on `questionnaire_ready`, build `responses=[{"question_id": q["question_id"], "answer": <first option>} for q in data.questions]` and call `await store.set_questionnaire_responses(pipeline_run_id, responses)` (this also `event.set()`s the resume event). One full round empties `missing_information` → engine proceeds.

> **Decision baked in:** to keep the *default* snapshots minimal and stable, prototype/od_prototype/revision use `gate_agent_ids=[]` (no gates) and `_drive`'s `ALWAYS_CLARIFY=False` (no clarify). Add **one** dedicated test per gate type (a `prototype` run with gates auto-approved; a `ppt` run with clarify driven) so the gate/clarify event vocabulary is also pinned — these are the events Phase 3+ must preserve.

### A6. Pure-seam unit characterizations (cheap, high-value)

These engine seams are pure/static — characterize directly (no full run). Several already have tests; reference/extend rather than duplicate:

| Seam | Existing test (extend) | Pins |
|---|---|---|
| `_count_plan_tasks` / `_extract_task_block` | `tests/unit/test_plan_task_parsing.py` | task detection (L11) |
| `_select_issues_to_fix` / `_static_issue_sigs` / `_console_sigs` | `tests/agents/test_phase5_fixloop_selection.py` | fix selection policy |
| `_sanitize_carousel_deck_html` / `_unwrap_artifact` | (callable directly) | L3 sanitizer |
| `_resolve_final_output` | `tests/unit/test_final_output_resolution.py` | L2 deliverable resolution |
| `serialize_sandbox_deliverable` / `count_sandbox_deliverables` | `tests/agents/test_sandbox_deliverable.py` | code-gen bundle |

Confirm each is green at HEAD before 0B; they are the fine-grained complement to the end-to-end snapshots.

---

## B. Workstream B — Migration-ledger CI guard

### B1. `specs/003-workflow-engine-decoupling/migration-ledger.json` (the source of truth the test reads)

JSON (no PyYAML dep). Mirrors plan.md §31. Every item starts `status: "pending"` → the guard **skips** it → green today. Initial content (verified patterns still match HEAD, so they MUST be skipped until deleted):

```json
{
  "version": 1,
  "scan_roots": [
    "backend/agents/execution_engine",
    "backend/agents/factory.py",
    "backend/app/agents/deep_agent_runner.py"
  ],
  "items": [
    {"id":"L14","phase":"0B","pattern":"self\\._(od_context|completed_tasks|current_task_block|revision_|gate_agent_ids|user_id|checkpointer|disk_skills)","status":"pending","deleted_in":null},
    {"id":"L16","phase":"0B","pattern":"RunSandbox\\(user_id or \"anon\", parent_run_id\\)","status":"pending","deleted_in":null},
    {"id":"D1","phase":"0B","pattern":"_handle_revision","status":"pending","deleted_in":null},
    {"id":"L13","phase":"2","pattern":"_extract_html_skeleton","status":"pending","deleted_in":null},
    {"id":"L1","phase":"2","pattern":"_PROTOTYPE_PIPELINE_TYPES|_PPT_PIPELINE_TYPES","status":"pending","deleted_in":null},
    {"id":"L2","phase":"2","pattern":"_resolve_final_output","status":"pending","deleted_in":null},
    {"id":"L3","phase":"2","pattern":"_sanitize_carousel_deck_html|_unwrap_artifact","status":"pending","deleted_in":null},
    {"id":"L4","phase":"2","pattern":"_extract_existing_prototype_html|_slim_revision_message","status":"pending","deleted_in":null},
    {"id":"L5","phase":"2","pattern":"SKIP_PLANNER_FOR_PROTOTYPE","status":"pending","deleted_in":null},
    {"id":"L6","phase":"2","pattern":"_pipeline_defaults","status":"pending","deleted_in":null},
    {"id":"L7","phase":"2","pattern":"spec\\.id == \"prototype-build\"","status":"pending","deleted_in":null},
    {"id":"L10","phase":"2","pattern":"pipeline_type in \\(\"od_prototype\", \"prototype\"\\)","status":"pending","deleted_in":null},
    {"id":"L11","phase":"2","pattern":"_run_build_task_loop|_write_build_reference_files|_count_plan_tasks|_extract_task_block|_run_validation_fix_loop|_load_template_example","status":"pending","deleted_in":null},
    {"id":"L12","phase":"2","pattern":"get_template_injection_parts","status":"pending","deleted_in":null},
    {"id":"F1","phase":"3","pattern":"PROMPT_ASSEMBLY_INLINE_MARKER","status":"pending","deleted_in":null},
    {"id":"F2","phase":"3","pattern":"_build_runner_tools","status":"pending","deleted_in":null},
    {"id":"F3","phase":"3","pattern":"Active Behavioral Hooks","status":"pending","deleted_in":null},
    {"id":"F4","phase":"3","pattern":"_inject_constitution","status":"pending","deleted_in":null},
    {"id":"F5","phase":"3","pattern":"create_deep_agent","status":"pending","deleted_in":null}
  ]
}
```

> Notes: (1) L14's pattern is broadened beyond §31's to cover the full self._* set the 0B investigation found (`_user_id`, `_checkpointer`, `_disk_skills`). (2) F5 (`create_deep_agent`) must, when done, allow the **one** legitimate call inside the `langchain_deepagents` adapter — so its "done" assertion is *scoped* (see B2 note) rather than a blanket 0. (3) L6's `_pipeline_defaults` and F1's marker are placeholders — confirm the exact symbol when those phases author the deletion. (4) The 003 §31 markdown table stays the human-readable copy; this JSON is the machine-readable mirror the test asserts (sanctioned by §31 line 913).

### B2. `backend/tests/test_migration_ledger.py`

Pure-Python `re` over files (no `rg`/`grep` — CI's slim image lacks them). Start-green-via-status:

```python
import json, re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LEDGER = REPO_ROOT / "specs/003-workflow-engine-decoupling/migration-ledger.json"

def _iter_py(roots):
    for r in roots:
        p = REPO_ROOT / r
        for f in ([p] if p.is_file() else p.rglob("*.py")):
            if "__pycache__" in f.parts: continue
            yield f

def test_done_items_fully_deleted():
    data = json.loads(LEDGER.read_text())
    for item in data["items"]:
        if item["status"] != "done":           # ☐ pending → SKIP → green today
            continue
        rx = re.compile(item["pattern"])
        hits = [f"{f.relative_to(REPO_ROOT)}:{n}"
                for f in _iter_py(data["scan_roots"])
                for n, line in enumerate(f.read_text(errors="replace").splitlines(), 1)
                if rx.search(line)]
        assert not hits, f"{item['id']} marked done but pattern still matches:\n  " + "\n  ".join(hits)

def test_done_items_record_a_sha():
    for item in json.loads(LEDGER.read_text())["items"]:
        if item["status"] == "done":
            assert item.get("deleted_in"), f"{item['id']} done but no deleted_in SHA"

def test_ledger_schema_valid():
    for item in json.loads(LEDGER.read_text())["items"]:
        assert item["status"] in ("pending","done")
        re.compile(item["pattern"])            # every pattern compiles

def test_ledger_mirrors_plan_section31():       # anti-drift: every L#/F#/D# in §31 exists in JSON
    plan = (REPO_ROOT / "specs/003-workflow-engine-decoupling/plan.md").read_text()
    ids_in_plan = set(re.findall(r"\| (L\d+|F\d+|D\d+)(?:/L?\d+)? \|", plan))
    ids_in_json = {i["id"] for i in json.loads(LEDGER.read_text())["items"]}
    missing = ids_in_plan - ids_in_json
    assert not missing, f"§31 items absent from migration-ledger.json: {sorted(missing)}"
```

- **Today:** every item `pending` → `test_done_items_fully_deleted` asserts nothing → GREEN, even though all legacy patterns still exist.
- **When an item is deleted:** the deleting commit flips `status:"done"` + sets `deleted_in:"<short SHA>"` **in the same commit** → from then the guard enforces 0-matches (the ratchet; reintroducing the symbol fails CI, §31).
- **Scoped-done items (F5):** when `create_deep_agent` deletion lands, change its entry to a `{"allow_in": ["backend/app/agents/deep_agent_runner.py"]}`-style exception (skip matches in the one sanctioned adapter file) rather than blanket 0. Add that field + handling when F5 is authored (Phase 3); not needed for 0A.

### B3. `test_ledger_mirrors_plan_section31` regex

The §31 table's leftmost column has compound ids (`L2/L9`, `L4/L8`). Tune the mirror regex to split those, or list canonical ids in the JSON and relax the check to "every JSON id appears in §31." Keep it advisory-strict (fail on drift) but don't over-engineer the markdown parse.

---

## C. Workstream C — import-linter contract

### C1. Add the dependency

`backend/requirements-dev.txt` (pinned, matches house convention): `import-linter==2.1` (cmd `lint-imports`, config `[tool.importlinter]`, pulls `grimp`). Add `vulture==2.14` only if the §31 dead-code scan is wired now (recommended later — ruff F-rules cover unused imports; vulture covers orphaned functions like L13/D1).

### C2. Permissive baseline contract (green today, ratchet for new leaks)

In `backend/pyproject.toml`. The current kernel legitimately imports legacy modules (`agents.factory`, `app.agents.sandbox`, `app.agents.static_check/render_check`, `agents.prototype.*`, `app.models.*`). So the baseline **only forbids edges that are already absent** — chiefly the R15 "no hand-rolled / direct runtime" rule — and is tightened item-by-item as ledger items land.

```toml
[tool.importlinter]
root_packages = ["agents", "app"]
include_external_packages = false

# R15 / INV-13 — the kernel must never import the deepagents runtime adapter
# directly (it goes through the factory today). TRUE at HEAD → starts GREEN,
# and ratchets: any new direct import fails CI.
[[tool.importlinter.contracts]]
name = "Kernel does not import the deepagents runtime adapter directly"
type = "forbidden"
source_modules = [
  "agents.execution_engine.engine",
  "agents.execution_engine.resolver",
  "agents.execution_engine.state_machine",
  "agents.execution_engine.clarify_engine",
]
forbidden_modules = ["app.agents.deep_agent_runner"]

# Future contracts (kept commented; each un-commented by the phase that deletes
# the corresponding edge — documents the target without breaking CI today):
#   agents.factory            (F1-F5, Phase 3)  → via AgentRuntimeAdapter
#   app.agents.sandbox        (L2/L9, Phase 2/4)→ via deliverable cap / Workspace port
#   app.agents.static_check   (Phase 3)         → via Validator capability
#   app.agents.render_check   (Phase 3)         → via Validator capability
#   app.agents.skills         (F3, Phase 3)     → via skill_provider
#   agents.prototype.pipeline (L5, Phase 2)     → via manifest planner
#   agents.prototype.context  (L12, Phase 2)    → via ContextProvider
#   app.models                (§18)             → via repositories
```

> **Current kernel import graph (baseline reference)** — `engine.py` intra-repo imports: `agents.artifact_store.store` (port-like), `agents.execution_engine.{resolver,state_machine,clarify_engine}` (kernel siblings — always allowed), `agents.factory` **(F-leak)**, `app.agents.sandbox` **(leak)**, `app.agents.checkpointer` (port-ish), `app.agents.static_check`/`render_check` **(leak, Phase 3)**, `agents.prototype.pipeline`/`context` **(L5/L12)**, `app.core.config`, `agents.planner.smart_planner`, `agents.registry`, `app.models.{database,workflow,workflow_definition}` **(persistence leak)**, `app.agents.skills` **(F3)**. `resolver.py` is pure (zero intra-repo). This is the graph the import-linter will progressively constrain.

### C3. Run requirement

`lint-imports` builds the **real** graph by importing modules → the CI job needs `requirements.txt` installed **and** the `backend:test` env vars (the kernel transitively imports `app.core.config.settings`, which needs `SECRET_KEY` etc. at import). Run with cwd `backend/` so `agents`/`app` resolve as top-level packages.

---

## D. Workstream D — CI wiring

CI today (`/.gitlab-ci.yml`, root): `backend:lint` runs `ruff check app/` only (**not `agents/`**); `backend:test` runs `python -m pytest tests/unit -q` only (**not `tests/` or `tests/agents/`**); neither installs `requirements-dev.txt`; image is `python:3.13-slim`. So the new guards need a **dedicated job**.

Add `backend:contracts` (new job in the `test` stage):

```yaml
backend:contracts:
  stage: test
  image: python:3.13-slim
  variables:                # same env as backend:test — engine imports settings at import time
    DATABASE_URL: "sqlite:///./test.db"
    SECRET_KEY: "ci-test-secret-key-not-for-production-use-only"
    AWS_REGION: "eu-central-1"
    BEDROCK_INFERENCE_PROFILE_ID: "eu.anthropic.claude-haiku-4-5-20251001-v1:0"
    BEDROCK_MODEL_ID: "anthropic.claude-haiku-4-5-20251001-v1:0"
    ENV: "test"
  before_script:
    - pip install -r backend/requirements.txt
    - pip install -r backend/requirements-dev.txt      # import-linter (+ syrupy/vulture if added)
  script:
    - cd backend
    - lint-imports                                      # reads [tool.importlinter]
    - python -m pytest tests/test_migration_ledger.py tests/characterization -q
  rules:
    - if: $CI_PIPELINE_SOURCE == "merge_request_event"
    - if: $CI_COMMIT_BRANCH == "main"
```

Optional but recommended: extend `backend:lint` to also `ruff check agents/` (the kernel is currently unlinted in CI). Pick the CI Python per [README §8 D-4] (recommend keeping 3.13).

---

## E. Ordered task checklist (0A)

1. **Confirm decisions** D-1…D-5 ([README §8]); **verify §9 cross-checks** (SKIP_PLANNER_FOR_PROTOTYPE actual value; whether `run_revision`/`_handle_revision` is live).
2. Pin deps: add `import-linter==2.1` (+ `syrupy` if D-1) to `requirements-dev.txt`.
3. Create `specs/003-workflow-engine-decoupling/migration-ledger.json` (B1).
4. Write `backend/tests/test_migration_ledger.py` (B2/B3) → verify GREEN at HEAD (all items pending).
5. Add `[tool.importlinter]` to `backend/pyproject.toml` (C2) → `cd backend && lint-imports` GREEN at HEAD.
6. Create `backend/tests/characterization/conftest.py`: `normalize_events()` (A2), `char_harness` fixture (extends `_drive`, records deliverable), gate/clarify auto-drivers (A5), ArtifactStore/StateMachine singleton resets.
7. Extend `tests/agents/_scripted_model.py` `_drive`/`_scripts_for` for: `od_context` on `ppt`/`od_ppt`; `od-ppt-*` scripts (canned `<artifact>` deck); `prototype_revision` parent-seed + `edit_file` path; verify `app_builder` chain.
8. Write the 5 characterization tests (A4) → record snapshots (`--snapshot-update`) → review the recorded snapshots by eye (this is the human-verified baseline) → commit.
9. Add the gate-driven + clarify-driven dedicated tests (A5).
10. Confirm/extend the pure-seam unit tests (A6) are green.
11. Add the `backend:contracts` CI job (D); extend `backend:lint` to `agents/` (optional).
12. Run full suite locally: `cd backend && python3.11 -m pytest tests/characterization tests/test_migration_ledger.py -v` → all green.
13. Update [README] status; flip nothing in the ledger (0A deletes nothing).

## F. Definition of Done (0A)

- [ ] 5 characterization snapshots (deliverable + normalized events) recorded, human-reviewed, committed; re-running is green and stable across machines (no volatile field leaks — the A2 assertion passes).
- [ ] `ppt` and `od_ppt` each snapshotted; the carousel deck pins both `_unwrap_artifact` + `_sanitize_carousel_deck_html`.
- [ ] One gate-driven and one clarify-driven test pin those event vocabularies.
- [ ] Pure-seam unit characterizations green.
- [ ] `migration-ledger.json` created; `test_migration_ledger.py` green at HEAD (all pending) and mirror-check passes.
- [ ] `[tool.importlinter]` added; `lint-imports` green at HEAD.
- [ ] `backend:contracts` CI job added and passing; runs the ledger guard + import-linter + characterization tests against `agents/`.
- [ ] No runtime behavior change (no production `.py` under `agents/`/`app/` modified except the test-only `_scripted_model.py` extension).
- [ ] §9 cross-checks resolved and recorded (correct §31 if D1 is not dead).

## G. 0A-specific risks

- **Snapshot captures a volatile field** → the A2 post-normalization assertion fails the test loudly (by design).
- **`render_check` differs by host** → fixtures use `static_check`-clean HTML so the (non-yielding) fix-loop never fires; event stream is render-independent.
- **`_drive` extension drifts from production** (e.g. it stubs the planner but prod runs it) → §9 SKIP_PLANNER verification; record the planner/clarify path the fixture actually represents.
- **Ledger pattern false-negative** (a pattern that wouldn't match the symbol once moved) → patterns verified against HEAD now match (so they're skipped-correct); each phase re-verifies its pattern matches 0 *after* deletion before flipping to done.
