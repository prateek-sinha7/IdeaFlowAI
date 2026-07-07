# Steps-L2 Artifact-Derivation Contract

**Phase 28 (A0) UI-SPEC input for RUNUI-03 (Steps 3-level drill-down).**
**Authority:** POR D-12 + evidence `01-run-ui-teardown.md` §2B / §2C / §7 + `07-synthesized-contracts.md` §2. The VelocityAI mock (`Hexaware Run.dc.html`) is a **visual reference only** — all data comes from the backend fields pinned below, never from the mock's hardcoded class fields (`ART`, `STEPS`). Phases 31/32 wire the run screens directly against this table.

> Transcribed from the locked POR + evidence pack — no decision is re-derived or re-opened (mode: yolo / skip_discuss, per the AUTONOMOUS-RUN DECISION LOCK in `.planning/CHAT-AND-UI-CONVERGENCE-PLAN.md` §3).

---

## 1. The four Steps-L2 artifact kinds

Steps L2 (agent detail) shows exactly ONE artifact block per agent, discriminated by kind (evidence 01 §2B.2). The mock's `ART[code].kind` is one of `pages | tasks | checks | construction`. Each kind's real backend data source is pinned here.

| Kind | Backend data source (event / artifact / module) | Producing field(s) | Notes |
|---|---|---|---|
| **`pages`** | The prototype **route table** parsed from `backend/app/agents/route_table.py` (`parse_routes_table` → ordered `(pattern, page)` tuples via `resolve_route`) | The `page` value of each `(pattern, page)` tuple = the page-name list the mock renders as `pages[]` (mock: `ART.SW.pages`). `pattern` is the nav path; `page` is the resolved page id shown as the thumbnail name. | Source is the agent's produced HTML/spec route declaration, parsed by the shared `route_table` resolver (the single source of route semantics for both prototype validators). An href-valued object map returns `None` (not a resolvable table) → no `pages[]` derivable; fall back to the artifact's declared page list. Green-status-neutral. |
| **`tasks`** | The **`task_list`** typed artifact (artifact-graph kind `task_list`, produced by `prototype-plan`; see `_AGENT_KIND_MAP` in `engine.py`: `"prototype-plan": "task_list"`) | The numbered build-task list + `{total} planned` count (mock: `ART.TP.tasks[]`). Each task carries `title` (+ `status` once building). | The typed artifact is read from the artifact graph (`ectx.artifacts`), not synthesized. Count = length of the task list. |
| **`checks`** | The **`validation_results`** governance verdict + rows (artifact-graph / persisted `validation_results` table; produced by the analyzer / validation agents; `_AGENT_KIND_MAP`: `"prototype-validate": "validation_report"`) | Green verdict pill (`artVerdict`, e.g. "Coverage 100%" / "0 blockers") + green-check rows (mock: `ART.SK` / `ART.VA.rows[]`). | **Status-palette exception:** this block stays GREEN (the one governance-semantic-color block) — see evidence 01 §6 status palette exception. Owner+workspace scoped (`validation_results` carries `owner_id`+`workspace_id`, AUTHZ-01). |
| **`construction`** | **DUAL SOURCE** — `task_progress` (the task-loop checklist) AND `subagent_*` / `wave_*` (the fan-out waves + workers). Per evidence 07 §2 "Steps L3 dual source". | See §2 (dual-source detail) + §3 (KAN-99 cap) below. | Both event families feed the Construction block and its L3 drill-down. |

---

## 2. `construction` — dual-source derivation

The Construction block ("Construction · waves & subagents", mock `Run:440–476`) is fed from TWO distinct backend event families. Phase 32 must merge them, not pick one.

**Source A — the task-loop checklist (`task_progress`).** Emitted by `engine.py:3108` when the build sub-agent's `report_task_complete` tool returns. Payload fields (verified in code):

| Field | Meaning |
|---|---|
| `agent_id` | the build agent id |
| `pipeline_run_id` | run id |
| `completed_tasks` | list of completed task identifiers (`list(ectx.completed_tasks)`) |
| `completed_count` | cumulative count of completed tasks |
| `timestamp` | emit time |

**Source B — the fan-out waves + workers (`wave_*` / `subagent_*`).** Emitted by the wave-scheduler strategy and the fan-out runner:

| Event type | Emit site | Payload fields (verified) |
|---|---|---|
| `wave_started` | `wave_scheduler.py:268` | `step`, `wave_index`, `task_ids` |
| `wave_completed` | `wave_scheduler.py:298` | `step`, `wave_index`, `task_ids` |
| `wave_failed` | `wave_scheduler.py:292` | `step`, `wave_index`, `task_ids` |
| `subagent_spawned` | `fanout.py:508` / `:523` | `worker` (index), `agent` (agent id), `isolation`, `depth` — **plus** `wave_index` + `step` stamped by the wave scheduler at its re-yield boundary (`wave_scheduler.py:283–287`) |
| `subagent_result` | `fanout.py:514` / `:567` | the worker result dict `res` (includes `worker`, `wave_index`, `step` after stamping) |

The mock's `ART.BA.waves[]` (3 waves; wave1/2 `parallel`, wave3 `sequential`; 7 tasks) maps to: **wave** = one `wave_started`→`wave_completed`/`wave_failed` bracket keyed by `wave_index`; **wave kind** (parallel/sequential) = the strategy's concurrency mode; **per-task rows within a wave** = the `subagent_spawned`/`subagent_result` pair for each `worker` under that `wave_index`.

---

## 3. The KAN-99 N-1 checklist cap (construction contract)

**Record this explicitly (KAN-99):** the FINAL `task_progress` event fires BEFORE the build agent's internal fix-loop runs. Consequently the construction checklist **caps at N-1** completed tasks until the build agent truly finishes (the last task is only marked done after the non-yielding validation fix-loop completes — the fix-loop is a non-yielding coroutine that emits no extra `task_progress`). Phase 32 must NOT treat `completed_count == total - 1` as a stall or an error: it is the expected steady state during the final agent's fix-loop. The checklist reaches N only on the build agent's real completion (surfaced by `agent_complete`, not by a further `task_progress`). This is the KAN-99 contract.

---

## 4. L3 per-task detail shape

Steps L3 (task detail, evidence 01 §2C, `Run:585–609`) is a single card flattened from the selected construction task. Per-task shape (mock `ART.BA.waves[].tasks[]`, evidence 01 §7 "Task (subagent)"):

| L3 field | Meaning | Real source |
|---|---|---|
| `n` | task number | `worker` index / `task_progress` order |
| `title` | task title | `task_list` artifact task title / `report_task_complete` `task_title` arg |
| `status` | `done \| running \| pending` | derived from `subagent_spawned` (running) → `subagent_result` (done); unspawned = pending |
| `dur` | task duration | `subagent_result` `res` timing |
| `thinking` | reasoning text | the worker sub-agent's `agent_thinking` / reasoning stream |
| `tools[]` | tool calls (`{name, arg, result}`) | the worker's `tool_call` / `tool_result` events |

---

## 5. Rule for Phase 32

Every Construction/Steps figure must resolve to one of the fields above. If a mock number has no pinned field, treat it as mock fiction (evidence 01 §9 warns against synthesized agent statuses / tokens / versions) — do NOT wire it. The companion `FIGURE-TO-FIELD-PINNING.md` pins the numeric figures (durations, tokens, sizes, cost, version) to their producing fields.
