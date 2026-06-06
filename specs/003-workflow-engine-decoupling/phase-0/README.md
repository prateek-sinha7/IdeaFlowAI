# Phase 0 — Safety Net, ExecutionContext & Token-Trim (detailed plan)

> The first three steps of [003 — Workflow Engine Decoupling](../plan.md). Phase 0 is the
> **safety net before surgery**: build the characterization tests + CI guards that pin today's
> behavior (0A), perform the first **behavior-preserving** refactor — lift all per-run state off
> the singleton into a per-run `ExecutionContext` and add the parent-run ownership check (0B), then
> ship the first **measured** improvement — wire the dead HTML-skeleton compaction (0C).
> Nothing here changes a workflow's contract; 0A/0B preserve the deliverable byte-for-byte and the
> event stream at semantic parity, 0C is the one sanctioned context change (gated on a token delta).

| | |
|---|---|
| **Parent spec** | [003 — Workflow Engine Decoupling](../plan.md) (§24 testing, §25 phases, §31 ledger) |
| **Branch** | `feature/003-workflow-engine-decoupling` |
| **Status** | 📋 Planned — awaiting go-ahead. No code landed. |
| **Created** | 2026-06-06 |
| **Detail docs** | [0A Safety net](phase-0a-safety-net.md) · [0B ExecutionContext](phase-0b-execution-context.md) · [0C Token-trim](phase-0c-token-trim.md) |
| **Investigation** | This plan was authored from 5 parallel deep-read investigations of the live code (test harness, entry points/events, pipeline fixtures, per-run state/ownership, CI/import-linter). Every `file:line` below is verified against `HEAD`. |

---

## 1. What Phase 0 is — and why it goes first

The engine (`backend/agents/execution_engine/engine.py`, 2643 lines) is a **module-level singleton** (`get_execution_engine`, `engine.py:2638`) whose `execute()` stashes **per-run mutable state on `self`** (`self._od_context`, `self._completed_tasks`, `self._current_task_block`, `self._revision_*`, …) and dispatches behavior on **literal pipeline/agent names** (`spec.id == "prototype-build"`, `pipeline_type in _PROTOTYPE_PIPELINE_TYPES`, …). The whole 003 refactor will move that logic behind capabilities/ports. **None of that is safe to touch without a regression net.**

Phase 0 builds the net and takes the two lowest-risk first steps:

- **0A — Safety net + deletion guard.** Characterization tests (deliverable + semantic-event snapshots) for 5 pipelines, the **migration-ledger CI guard**, and the **import-linter** contract. *No runtime behavior change.*
- **0B — ExecutionContext + ownership.** Lift every per-run `self._*` into a per-run `ExecutionContext`; add the explicit parent-run ownership check (L14/L16). *No behavior change — 0A snapshots stay byte-identical.*
- **0C — Token-trim (measured).** Wire the dead `_extract_html_skeleton` as the build-task-2+ context compaction. *Intentional context change, gated on semantic snapshot + a measured token delta.*

## 2. The key enabler — the determinism harness already exists ★

The most important investigation finding: **we do not need to invent how to run the engine deterministically offline.** It is built, proven, and runs today with zero Bedrock calls.

- `backend/tests/agents/_scripted_model.py`:
  - **`ScriptedFakeChatModel`** — a hand-rolled `BaseChatModel` whose `_stream` yields `AIMessageChunk`s with `tool_call_chunks` **and** `usage_metadata`, with a no-op `bind_tools`. (Stock LangChain `FakeMessagesListChatModel`/`GenericFakeChatModel` **cannot** drive the deepagents loop — they raise on `bind_tools` and drop tool calls. This custom model is mandatory.)
  - **`_ScriptedTurn(texts, tool_calls=[(name, json_args, call_id)], usage=(in,out))`** — a per-LLM-call script; tool calls actually fire the native FS tools (`write_file`/`edit_file`/`report_task_complete`) against the run sandbox on disk.
  - **`_scripts_for(agent_id)`** — per-agent script registry.
  - **`_drive(pipeline_type)`** — runs the **public `ExecutionEngine.execute()`** end-to-end and returns the ordered event list. It already monkeypatches `RUNS_ROOT`→temp, `ALWAYS_CLARIFY=False`, `_run_planner`→PROCEED, `_store.store`→no-op, `_run_review_gate`→no-op, and `create_runner` (in **both** `factory` and `engine` module namespaces — `engine.py` did `from agents.factory import create_runner`) to inject the scripted model as `ctx.model`.
- `backend/tests/agents/test_phase3_cutover_verify.py` — **the template.** Already asserts the event-type vocabulary + required `data` keys per event from `_drive(pipeline_type)`. Phase 0A generalizes this into recorded snapshots across all 5 pipelines.

The injection seam: `DeepAgentRunner.__init__` (`app/agents/deep_agent_runner.py:219-223`) uses a passed-in `BaseChatModel` **instance** verbatim (only builds from a string/None). `create_runner(agent_id, ctx)` passes `model=ctx.model` (`factory.py:155`). So setting `ctx.model = ScriptedFakeChatModel(...)` flows straight to `create_deep_agent`. deepagents accepts any `BaseChatModel`.

**Consequence for the plan:** Phase 0A is mostly (a) *extend* `_drive`/`_scripts_for` to cover `od_prototype` / `prototype_revision` / `ppt`+`od_ppt` / `app_builder`, (b) add a **normalization + snapshot** layer, and (c) add the **ledger guard + import-linter + CI wiring** (which are genuinely net-new).

## 3. The three sub-phases at a glance

| | Goal | Net-new deliverables | Behavior change? | Acceptance | Ledger items |
|---|---|---|---|---|---|
| **0A** | Pin today's behavior; arm the deletion guards | characterization snapshots (5 pipelines) · `tests/test_migration_ledger.py` + `migration-ledger.json` · `[tool.importlinter]` contract · `backend:contracts` CI job | **None** | snapshots recorded + green; ledger guard + import-linter green in CI | arms the gate for **all** items (starts green) |
| **0B** | Remove per-run state from the singleton; enforce parent ownership | `agents/execution_engine/context.py` (`ExecutionContext`) · `agents/authz.py` (ownership helper) · cross-owner denial test | **None** (semantic + byte parity) | snapshots byte-identical; `self` has no per-run attrs (only `_resolver`/`_store`/`_state_machine`); cross-owner seed rejected | **L14**, **L16**, (**D1** — see §9) |
| **0C** | First measured win: HTML-skeleton compaction | wire `_extract_html_skeleton` into build-task-2+ context · a token-delta measurement test | **Intentional** (context change) | equal-or-better validation pass rate; measured token reduction on a multi-task build; semantic snapshot green | **L13** (0C→2) |

## 4. Sequencing & dependencies

```
0A (safety net)  ──►  0B (ExecutionContext + ownership)  ──►  0C (token-trim)
   │                      │                                      │
   │ snapshots are the    │ 0B is verified by re-running 0A      │ 0C is the FIRST change that may
   │ regression oracle    │ snapshots → must stay byte-identical │ alter output → gated on the 0A
   │ for 0B & 0C          │ (zero behavior change)               │ SEMANTIC snapshot + a token delta
   ▼                      ▼                                      ▼
 must land FIRST       depends on 0A                          depends on 0A + 0B
```

- **0A is a hard prerequisite** for 0B and 0C — it is the oracle. Land and merge it first.
- **0B before 0C**: 0C edits `_build_context_message`, which 0B threads `ctx` through — doing 0B first means 0C edits the already-`ctx`-aware method (less churn, no rework).
- Each sub-phase is independently shippable and keeps every pipeline working (strangler, 003 Q39).

## 5. The 5 characterization pipelines (and what each pins)

Chosen to cover every pipeline-specific branch ("leak") in the engine. (Full fixtures in [0A](phase-0a-safety-net.md).)

| Pipeline | `pipeline_type` to `execute()` | Deliverable source | Engine branches / leaks pinned |
|---|---|---|---|
| `prototype` | `"prototype"` | `sandbox.read("prototype.html")` | task-loop (`_run_build_task_loop`, L11), `_count_plan_tasks`/`_extract_task_block`, cumulative `completed_tasks` monotonic count, reference-file write, `=== CURRENT TASK ===` injection (L12), HTML read-back (L10), `_resolve_final_output` prototype branch (L2), build fix-loop |
| `od_prototype` | `"od_prototype"` | `sandbox.read("prototype.html")` | the `od_prototype` spellings in `_PROTOTYPE_PIPELINE_TYPES` (L1) + read-back (L10), od_context template/DS injection (L12) |
| `prototype_revision` | `"prototype_revision"` | `sandbox.read("prototype.html")` | revision seeding + slim + parent-seed (L4, `engine.py:551-650`), pre-edit baseline (`_select_issues_to_fix` etc.), post-revision fix-loop (L8), revision deliverable branch (L2, `engine.py:358-373`), **the L16 ownership surface** |
| `ppt` **and** `od_ppt` | `"ppt"` / `"od_ppt"` | streamed text → `_unwrap_artifact` + `_sanitize_carousel_deck_html` | `_PPT_PIPELINE_TYPES` (L1/L3), `<artifact>` unwrap, carousel slide-hiding strip (L3) |
| `app_builder` (code-gen) | `"app_builder"` | `serialize_sandbox_deliverable(sandbox.root)` | code-gen branch of `_resolve_final_output` (L2, `engine.py:389-394`), workspace tool writes, multi-agent `consumes` chaining |

> `ppt` and `od_ppt` get **separate** snapshots (same agents, different `pipeline_type` string → different engine branches). See [0A §A4](phase-0a-safety-net.md) and the open decision in §8.

## 6. Shared determinism & normalization contract

Snapshots compare **normalized** event streams + the raw deliverable. With the scripted model the deliverable, chunk text, and planning context become reproducible; the remaining nondeterminism is stripped/placeholdered before compare. (Full verified field list in [0A §A2](phase-0a-safety-net.md).)

**Strip or placeholder, every event:** `timestamp`; `pipeline_run_id`, `gate_key` (→ placeholder); `duration`/`total_duration`; `input_tokens`/`output_tokens`/`total_tokens`/`total_input_tokens`/`total_output_tokens`/`estimated_cost_usd`; `model_id`; `output_length`/`summary_length`/`full_output_length` (char counts).

**Normalize, not strip:** `agent_chunk.chunk` — join per agent and snapshot the concatenation (chunk boundaries are script-driven, not behavior).

**Hazards neutralized by construction:** `serialize_sandbox_deliverable` already `sort()`s by relpath (byte-stable); `static_check` is pure stdlib (deterministic); `render_check` degrades to `available=False` when Chromium is absent and the build fix-loop is **non-yielding** (so render availability never changes the *event stream*, only — if a fix fires — the deliverable bytes; fixtures use HTML that passes `static_check` so no fix fires). **No `seq` field exists yet** (it lands in Phase 1B) — Phase 0A snapshots scope to today's `{type, data}` events only.

## 7. Global Definition of Done (Phase 0)

Per 003 §25/§31, a sub-phase is **done** only when:

1. Its deliverables exist and tests are green (`cd backend && python3.11 -m pytest`).
2. Snapshots are green — **byte-identical** for 0A/0B; **semantic parity + measured token delta** for 0C.
3. CI runs the new guards (ledger + import-linter + characterization job) and they pass.
4. Any ledger items the sub-phase deletes are flipped `☐→☑` with a `deleted_in` SHA **in the same commit**, and the guard enforces 0-matches thereafter (the ratchet).
5. No dual implementation / dead branch left behind (INV-12). (0A/0B add no behavior; 0C's inline trim is superseded — and deleted — in Phase 2, ledger L13.)

## 8. Decisions needed before building

| # | Decision | Recommendation | Affects |
|---|---|---|---|
| D-1 | **Snapshot tooling** — no snapshot lib exists today. Add `syrupy` vs follow the house golden-file style (`tests/fixtures/*.md` + inline asserts, as `test_factory_injects.py` does). | **`syrupy`** (pytest-native, `--snapshot-update`, handles raw strings + normalized dicts; pin in `requirements-dev.txt`). | 0A |
| D-2 | **run_id strategy** — the `StateMachine` singleton rejects a reused completed id. Fix the run_id + reset the machine per test, **or** keep randomizing and normalize `pipeline_run_id` out. | **Randomize + normalize out** (less invasive; matches today's `_drive`). | 0A |
| D-3 | **Ledger source format** — YAML needs PyYAML (not pinned) vs JSON (stdlib). | **JSON** (`migration-ledger.json`, zero new dep). | 0A |
| D-4 | **CI Python** — CI uses `python:3.13-slim`; local convention is `python3.11`. The new job pins one. | **3.13 in CI** (matches existing jobs); keep `python3.11` locally. Pure-`re`/`ast` code is version-agnostic. | 0A |
| D-5 | **`ppt` vs `od_ppt`** — one snapshot or both? | **Both** (different engine branch per string). | 0A |
| D-6 | **D1 `_handle_revision` deletion in 0B** — the 003 ledger marks it dead/Phase-0B, but the investigation found `websocket.py` `run_revision` **calls it**. | **Do NOT delete in 0B** until confirmed dead; see §9. Re-classify after verification. | 0B |

## 9. Corrections / cross-checks the investigation surfaced (vs plan.md)

Two places where the live code contradicts an assumption baked into the parent plan. Both are exactly the latent-behavior risks (R1) the characterization net exists to catch — flagged here so they're resolved, not stumbled into.

- **D1 `_handle_revision` may not be dead.** 003 §31 lists D1 as "dead `_handle_revision` (`engine.py:2138-2251`) → delete, Phase 0B." But the entry-point investigation found the WS `run_revision` handler (`websocket.py:~625`) calls `engine._handle_revision(...)` directly (it is a *separate* path from `execute()`). **Action (0B task):** confirm whether `run_revision` is a live, reachable route. If live → `_handle_revision` is **not** dead; defer its removal to when the revision path is migrated (Phase 2), and correct §31. If the route is itself dead → delete both together. **Until confirmed, 0B does not touch it.**
- **`SKIP_PLANNER_FOR_PROTOTYPE` value conflict.** One investigation read `agents/prototype/pipeline.py` and reported the constant is **`False`** (so prototype *does* run the deep planner in production), while the engine's inline comment (`engine.py:700-708`) reads as if prototype skips it. The characterization fixture must mirror **production**, so the actual value matters. **Action (0A task):** read the constant, confirm the production planner/clarify path for prototype, and configure the fixture (`_drive` stubs the planner today — verify that matches prod, or record the planner events in the snapshot if prod runs it).

## 10. Phase 0 risk register

- **R0-1 Hidden behavior not covered by a fixture** (a branch no snapshot exercises silently changes in 0B/2). *Mitigation:* fixtures in [0A](phase-0a-safety-net.md) are chosen per-leak (§5); add the pure-seam unit characterizations; treat §9 items as proof the net works.
- **R0-2 Snapshot flakiness** (a volatile field slips into a snapshot). *Mitigation:* one shared `normalize_events()` with the §6 field list; assert no stripped key remains.
- **R0-3 0B churn breaks parity** (threading `ctx` subtly changes an order/field). *Mitigation:* 0A snapshots are the gate — 0B is "green snapshots or revert."
- **R0-4 0C regresses build quality** (skeleton omits context the build agent needs). *Mitigation:* 0C is gated on **equal-or-better validation pass rate**, not just tokens; ships behind the same fixture.
- **R0-5 Ledger guard red on day one** (it would be, if it naively grepped). *Mitigation:* start-green-via-`status` design (enforce 0-matches only for `☑` items) — [0A §B](phase-0a-safety-net.md).
- **R0-6 import-linter red on day one** (kernel legitimately imports legacy today). *Mitigation:* permissive baseline contract that only forbids edges already absent (R15 ratchet) — [0A §C](phase-0a-safety-net.md).
- **R0-7 CI doesn't run the new tests** (CI runs `tests/unit` only, lints `app/` only). *Mitigation:* a dedicated `backend:contracts` job that targets `agents/` + the new test paths — [0A §D](phase-0a-safety-net.md).

## 11. File / asset map for Phase 0

`✦` = new file. (Paths relative to repo root.)

```
specs/003-workflow-engine-decoupling/
├── migration-ledger.json                         ✦ 0A — machine-readable §31 mirror (the guard reads this)
└── phase-0/                                       ✦ this folder
    ├── README.md                                  (this file)
    ├── phase-0a-safety-net.md
    ├── phase-0b-execution-context.md
    └── phase-0c-token-trim.md
backend/
├── pyproject.toml                                 ~ 0A — add [tool.importlinter]; (pytest paths if needed)
├── requirements-dev.txt                           ~ 0A — pin import-linter (+ syrupy if D-1, vulture if used)
├── tests/
│   ├── agents/_scripted_model.py                  ~ 0A — extend _drive/_scripts_for for the 5 pipelines
│   ├── characterization/                          ✦ 0A — the snapshot tests + __snapshots__/
│   │   ├── conftest.py                            ✦   shared normalize_events() + harness fixtures
│   │   ├── test_char_prototype.py                 ✦
│   │   ├── test_char_od_prototype.py              ✦
│   │   ├── test_char_prototype_revision.py        ✦
│   │   ├── test_char_ppt.py                        ✦ (ppt + od_ppt)
│   │   └── test_char_app_builder.py               ✦
│   └── test_migration_ledger.py                   ✦ 0A — the deletion guard
├── agents/execution_engine/
│   ├── engine.py                                  ~ 0B (ctx threading, drop self._*) · ~ 0C (skeleton wiring)
│   └── context.py                                 ✦ 0B — ExecutionContext dataclass
└── agents/authz.py                                ✦ 0B — parent-run ownership helper (INV-8 seam)
.gitlab-ci.yml                                     ~ 0A — add backend:contracts stage/job
```

---

*Read next: [Phase 0A — Safety net](phase-0a-safety-net.md). Each detail doc carries its own ordered task checklist, code sketches, and Definition of Done.*
