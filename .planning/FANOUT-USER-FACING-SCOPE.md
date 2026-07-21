# Fan-Out User-Facing — Scope & Implementation Plan (no-hacks)

**Branch:** `feat/ui-2` · **Date:** 2026-07-19 · **Mode:** design/scoping investigation (read-only on code)
**Question:** How do we make fan-out user-facing the architecture-respecting way — NOT by un-fencing the `task` sub-agent tool?
**Method:** Every file:line below was re-verified against the code as it stands now (look, don't recall). Register entries cited are `.planning/IMPLEMENTATION-REGISTER.md`.

**Headline:** The engine already executes declarative fan-out end-to-end with zero kernel edits, and the entire declarative fan-out capability set (`strategy:fanout_batch`, `task_parser:heading_tasks`/`json_tasks`, `merge:copy_disjoint`) is `user_allowed=True` — so **no security/trust flag needs flipping**. The single decisive gap is that the user-composer's runtime overlay, `engine._apply_selections` (`backend/agents/execution_engine/engine.py:6257-6272`), copies only `validators`/`gates`/`model`/`retry`/`injects` onto the run plan and drops `strategy`/`fanout`/`task_source`. Until that overlay carries the fan-out levers, no composer control can ever turn a step into a fan-out step.

---

## 1. Verified current state (prior-analysis claims → verdict, current file:line)

### Claim 1 — palette shows all caps grouped by kind; a "Strategies" group + a locked `spawn_subagents`; DISPLAY-ONLY, selecting a strategy attaches nothing. → **CONFIRMED (with one correction)**
- `CapabilityPaletteSection` (embedded in `frontend/src/components/workflow/AgentsPopup.tsx`, test `CapabilityPaletteSection.test.tsx`) renders every kind from live `GET /api/capabilities`, grouped by kind, `user_allowed=false` rows visible-but-locked (Register Phase 22-05, line 2269; Phase 22 §5 line 2301: "Privileged caps visible-but-locked ... never user-composable").
- Display-only for strategies is CONFIRMED by the fact that the only functional per-step levers are `validators`/`gates`/`model`/`retry` (see Claim 2); there is no strategy lever in the selection shape.
- **Correction:** the locked row is `tool:spawn_subagents` (registry.py:117), which lives in the **Tools** group, not the Strategies group. All four registered strategies (`single_shot`, `task_loop`, `fanout_batch`, `wave_scheduler`) are `user_allowed=True` (registry.py:82-85), so the Strategies group shows NO locked row.

### Claim 2 — composer carries only five levers, `strategy` not one; synth hardcodes `single_shot`; overlay never applies `strategy`/`tools`/`fanout`. → **CONFIRMED in its load-bearing conclusion; CHANGED in the "five levers / `_LEVER_KEYS`" detail**
- **Real lever set = 4, not 5.** The FE selection type is `StepSelection = { validators?, gates?, model?, retry? }` (`frontend/src/components/workflow/AgentsPopup.tsx:1419-1425`). Both composer surfaces expose exactly these: the Canvas config rail patches `model` (CanvasConfigRail.tsx:141), `validators` (:173), `gates` (:193), `retry` (:212/:224); the "custom prompt" is `AgentPromptSection ... surfaceOnly` (CanvasConfigRail.tsx:240) i.e. display-only, not a persisted lever. The AdvancedExpander in AgentsPopup uses the same shared `applyLeverPatch` reducer (AgentsPopup.tsx:1452).
- **`_LEVER_KEYS` claim is outdated.** `backend/agents/workflows/selections.py:43-46` now lists 14 keys (`validators, gates, model, retry, injects, compaction, post_step, fix, fanout, on_conflict, tools, hooks, task_source, depends_on`) — but that constant is **dead code**: a repo-wide grep finds it referenced ONLY at its own definition line. It gates nothing.
- **Synth hardcodes `single_shot`: CONFIRMED.** `selections.py:_synthesize_step` line 86 begins every step as `{"agent": agent_id, "strategy": "single_shot"}` and never overrides `strategy`. Its projection loop (`selections.py:128-131`) CAN copy `fanout`/`task_source`/`on_conflict`/`tools` onto the raw step dict, but the strategy stays `single_shot`.
- **Crucial architectural nuance the prior analysis missed:** the manifest that `synthesize_manifest` produces is an explicit **throwaway** used ONLY to drive `compile(trust="user")` as the CAP-03 trust gate — it is NOT the run plan (`selections.py:150-155`, and it uses a stub `deliverable: single_file` at :177). The plan that actually runs is the file-compiled plan, mutated by `engine._apply_selections`.
- **Overlay never applies `strategy`/`fanout`/`task_source`: CONFIRMED and this is the decisive fence.** `engine._apply_selections` (`engine.py:6194-6274`) re-compiles the selections for trust, then builds a `patch` dict (`engine.py:6257-6272`) that carries only `validators`, `gates`, `model`, `retry`, `injects`. It never reads `user_step.strategy`, `.fanout`, `.task_source`, or `.on_conflict`, and never changes the file step's strategy.

### Claim 3 — `spawn_subagents` is `user_allowed=False`. → **CONFIRMED**
- `registry.py:117`: `("tool", "spawn_subagents"), # 11-01 / FANOUT-01 (user_allowed=False)`. The compiler rejects a user/db manifest granting it (compiler.py:480-499) and its trust ceiling collapses it off (compiler.py:529).

### Claim 4 — no launchable pipeline fans out; `sample_fanout`/`sample_wave` are SC-001 proofs, not launchable; real pipelines are sequential. → **CONFIRMED**
- `user_launchable: true` manifests: `app_builder`, `custom`, `mulesoft_to_springboot`, `ppt`, `prototype`, `user_stories`. All of their steps use `single_shot` / `serialized_sandbox` / `ppt` / `streamed_text` / (prototype) `task_loop` — **none use `fanout_batch` or `wave_scheduler`** (grep over `agents/workflows/*/workflow.yaml`).
- `sample_fanout/workflow.yaml` and `sample_wave/workflow.yaml` carry NO `user_launchable` key → default `False` (`manifest.py:78,223`) → not launchable.
- Register line 4086: "sample_fanout/sample_wave aren't API-launchable and no user-facing pipeline fans out."

### Claim 5 — the `task` sub-agent tool is always stripped by `_ToolFilterMiddleware`; `_LIBRARY_SUBAGENT_TOOL = "task"`. → **CONFIRMED**
- `backend/app/agents/deep_agent_runner.py:85` `_LIBRARY_SUBAGENT_TOOL = "task"`; `:328` `excluded = _BUILTIN_TOOLS if exclude_builtin_tools else frozenset({_LIBRARY_SUBAGENT_TOOL})`; `:352` `middleware=[_ToolFilterMiddleware(excluded=excluded), _BedrockCachePointsMiddleware()]`. Register lines 1136/1161 mark it "deliberately NOT deleted ... do not resurrect."

### Claim 6 — fan-out width is data-driven at runtime (`latest_typed_content(source_step)` → parser → one worker/item); concurrency capped by `Semaphore(min(declared, DEFAULT_MAX_CONCURRENCY))`. → **CONFIRMED**
- `fanout_batch.py:79` `plan_output = runner.latest_typed_content(source_step)`; `:81-85` parser resolve (default `heading_tasks`, `fanout_batch.py:32`); `:93` `requests = [{"agent":"self","input":t.body} for t in tasks]`; `:96-102` WR-06 fallback to `fanout.count` identical workers when no tasks parse.
- `fanout.py:170-179` `_resolve_concurrency = min(declared, DEFAULT_MAX_CONCURRENCY)`; `:533` `sem = asyncio.Semaphore(cap)`. `budget.py:43-46`: `DEFAULT_MAX_SUBAGENTS=8`, `DEFAULT_MAX_CONCURRENCY=4`, `DEFAULT_MAX_DEPTH=2`, `DEFAULT_WALL_CLOCK_SECONDS=900`. The per-run `BudgetManager` is built at run entry from `compiled.limits` (`engine.py:1487`) and `run_fanout` calls `budget.reserve(...)` before any spawn (`fanout.py:304-310`).

### Claim 7 — `fanout_batch`/`wave_scheduler`/`copy_disjoint` are already `user_allowed=True`, so the declarative path passes user-trust WITHOUT flipping a flag; only `spawn_subagents` stays engineer-only. → **CONFIRMED, and strengthened**
- `strategy:fanout_batch` user_allowed=True (`fanout_batch.py:38`); `strategy:wave_scheduler` True (`wave_scheduler.py:136`); `merge:copy_disjoint` True (`copy_disjoint.py:49`); `task_parser:heading_tasks` True (`heading_tasks.py:92`); `task_parser:json_tasks` True (`json_tasks.py:56`).
- **Strengthened:** the DECLARATIVE fan-out path needs NO `spawn_subagents` grant at all. The `tools.spawn_subagents` check exists ONLY inside `_derive_fanout` (the runtime TOOL path, `engine.py:2920-2925`). The declarative dispatch resolves any strategy and runs it (`engine.py:2387-2390`), and `run_fanout` itself performs no permission check (`fanout.py:251-326` — cancel, select, reserve, isolate, spawn; no grant gate). The `tools.spawn_subagents: true` line in `sample_fanout/workflow.yaml:74` is therefore NOT load-bearing for the strategy — it is there to also exercise the tool path.

### Claim 8 — two clean paths (A: a runnable fan-out pipeline; B: user-composable fan-out with `strategy`+`fanout`/`task_source`/`merge` levers). → **CONFIRMED as directions, with one correction on "merge"**
- **Correction:** `merge` is NOT a user choice and there is nowhere for it to live. The engine selects the merge strategy by the isolation scope it already chose — `git_3way` for a git worktree, else `copy_disjoint` (`fanout.py:785-793`, INV-7 "the ENGINE picks the merge strategy ... NOT the manifest"). `FanoutSpec` (`plan.py:196-216`) has no `merge` field (only `merge_agent` for conflict resolution). `fanout_batch`'s `config_schema` advertises a `merge` enum (`fanout_batch.py:43-47`), but nothing reads it on the standard path. So the "how do outputs merge?" follow-up prompt is largely moot — the real second prompt is "which upstream step supplies the list?" (`task_source`).

### Claim 9 — the HACK (un-exclude `task`) loses determinism, cost bounds, isolation, deterministic merge, security. → **CONFIRMED** (see §5).

---

## 2. Full end-to-end gap trace (what must be true for a USER-composed fan-out step to actually execute)

Follow one composed step from the composer to a spawned worker. Each stage is marked GAP (must change) or OK (already works).

1. **Composer selection (FE).** `StepSelection` (`AgentsPopup.tsx:1419-1425`) admits only `{validators, gates, model, retry}`. `CanvasConfigRail.tsx` and the AgentsPopup AdvancedExpander render only those 4 levers. **GAP FE-1:** no control to mark a step "fan out over a list", and no picker for the upstream list-producer (`task_source.source_step`). The reducer `applyLeverPatch` (`AgentsPopup.tsx:1452-1475`) is generic — it iterates `Object.entries(patch)` — so it needs no logic change; only the `StepSelection` type and the UI controls must grow.

2. **Persisted selection (backend model).** Saved to the reused `workflows.manifest_json` column as the compact `{agent_id:{levers}}` JSON (Register 22-04, line 2283). Because it is opaque JSON, extra keys persist fine. **OK** (no schema/migration change).

3. **Save + launch trust gate.** Save: `user_workflows._compile_selections_trust_user` (`app/api/user_workflows.py:150-208`). Launch: `run_commands._revalidate_selections_trust_user` (`app/api/run_commands.py:1534-1539`). Both call `synthesize_manifest` + `compile(trust="user")`. Since `fanout_batch`/`heading_tasks`/`json_tasks` are all `user_allowed=True`, a fan-out selection PASSES this gate. **OK** — but see BE-1: the synth must emit the strategy so the gate actually validates the fan-out shape rather than a `single_shot` step with an inert `fanout`.

4. **Synth (`selections.py::_synthesize_step`).** Hardcodes `strategy: single_shot` (line 86); the projection loop (:128-131) already copies `fanout`/`task_source`/`on_conflict`/`tools` if present, but strategy stays `single_shot`. **GAP BE-1:** emit the selected `strategy` (e.g. `fanout_batch`) instead of the hardcoded default so the trust-compile validates a real fan-out step.

5. **Compiler.** Fully supports it already: `_compile_step` reads `strategy` and trust-checks it (`compiler.py:378-381`), compiles `task_source` with a trust-checked parser (`compiler.py:436-457`), materializes `fanout` via `_compile_fanout` (`compiler.py:539,593`) and `on_conflict` (`compiler.py:545-550`); all keys are in `_ALLOWED_STEP_KEYS` (`compiler.py:68`). **OK — no compiler change.** (This is the "engine already supports it" finding: INV-5 stays intact, no DSL.)

6. **Runtime overlay (`engine._apply_selections`, `engine.py:6194-6274`).** The `patch` dict (`engine.py:6257-6272`) carries ONLY `validators`/`gates`/`model`/`retry`/`injects`. **GAP BE-2 (decisive):** it never overlays `strategy`, `fanout`, `task_source`, or `on_conflict`, so even a perfectly-formed fan-out selection is dropped and the file step keeps its original strategy (for `custom` steps that is `single_shot`). Without this change, nothing a user composes can ever produce a fan-out step.

7. **Step lookup / synthesis for the run.** The main loop iterates the user's chosen agents `ordered_agents` (`engine.py:1656,2245`) and fetches each step from `_steps_by_agent = {s.agent_id: s for s in compiled.steps}` (`engine.py:2123`, built after `_apply_selections` at `:1463`). If a chosen agent is absent from the compiled plan, a bare `single_shot` step is synthesized (`engine.py:2285-2292`). For the `custom` pipeline the compiled plan is `custom/workflow.yaml`'s 8 fixed single_shot steps (`market-research-agent`, `swot-analyst`, `roadmap-planner`, `security-auditor`, `test-case-generator`, `performance-optimizer`, `documentation-agent`, `report-generator`). **GAP BE-3 (custom-specific):** `_apply_selections` only mutates steps that exist in `compiled.steps`, so the fan-out overlay reaches an agent only if that agent is in the base manifest. Any composed agent not in the base manifest gets the synthesized `single_shot` step with no selections applied. This must be handled (either apply selections to synthesized steps too, or constrain fan-out to in-plan steps).

8. **Dispatch + execution.** `engine.py:2387-2390` resolves the step's strategy generically and runs it via `_dispatch_step_with_retry` → `strategy.run`. A `fanout_batch` step here calls `ctx.runner.run_fanout` (`fanout_batch.py:112`) with no extra gate; the per-run budget bounds it (`fanout.py:304-310`); merge is engine-selected (`fanout.py:793`). **OK — no change.**

9. **Data dependency (UX).** `fanout_batch` needs `task_source.source_step` to name an upstream step whose latest typed content parses into tasks (`heading_tasks` reads `## Task N:` headers, `heading_tasks.py:39`). With no `source_step`/no list, it falls back to `fanout.count` identical workers, else spawns nothing (`fanout_batch.py:96-109`). **GAP UX-1:** the composer must let the user designate the producer step (default: the immediately previous step) and, ideally, warn when no upstream step emits a parseable list.

**Answer to "if we ONLY added a strategy picker, would it fan out?" — No.** A strategy picker alone changes nothing at runtime because `engine._apply_selections` (`engine.py:6257-6272`) never carries `strategy` onto the run plan, and `_synthesize_step` (`selections.py:86`) still hardcodes `single_shot`. You must additionally (a) make `_synthesize_step` emit the chosen strategy, (b) make `_apply_selections` overlay `strategy` + `fanout` + `task_source` (+ `on_conflict`), and (c) give the fan-out step an upstream list producer. The compiler and kernel already do the rest.

---

## 3. Path A — a runnable, engineer-authored fan-out pipeline (ships fastest; zero composer work)

**Idea:** register a `user_launchable` pipeline whose one step fans out per item. Because the manifest is file-trusted, everything (including `spawn_subagents` if desired) is allowed, and there is ZERO engine and ZERO composer work.

**Option A1 — promote the existing `sample_fanout` proof to a launchable pipeline (smallest).**
Concrete changes, all data/registration (no kernel edit):
1. `agents/workflows/sample_fanout/workflow.yaml`: add `user_launchable: true` + a friendly `display_name`/`description` (mirrors `custom/workflow.yaml:8-10`).
2. `agents/loader.py`: add `"sample_fanout"` to `SUPPORTED_PIPELINE_TYPES` (the frozenset gate, referenced `run_commands.py:1400,1423`).
3. `agents/registry.py`: add `PIPELINE_AGENTS["sample_fanout"] = ["sample-fanout-plan", "sample-fanout-worker"]` (must equal the manifest step order, else the membership assertion at `engine.py:1708` raises).
4. **Move the worker AGENT.md specs from fixtures to real prompt homes.** They currently live at `tests/agents/fixtures/sc001_fanout/` and are deliberately NOT in `agents/prompts/` because a prompt-home `pipeline_type: sample_fanout` AGENT.md would previously have failed the loader's `SUPPORTED_PIPELINE_TYPES` schema gate (Register line 1148). Once step 2 adds the type, create `agents/prompts/sample-fanout-plan/AGENT.md` and `agents/prompts/sample-fanout-worker/AGENT.md` with real (non-toy) prompt bodies.
- **No composer work.** Launch flows through the existing REST/SSE `launch_run` path (`run_commands.py:1432`), which already resolves `SUPPORTED_PIPELINE_TYPES` and drives `engine.execute`.
- **Effort:** S–M (registration + two real prompt bodies + one live-Bedrock smoke test). The current sample prompts write toy `part_*.txt` files, so for a real product feature you would author meaningful agents (blends into A2).

**Option A2 — author a genuinely useful fan-out pipeline (recommended if the goal is a product feature).**
Example shapes that map cleanly onto the existing machinery: a "plan then fan out per file/section" migration or document generator — one planner agent emits a `## Task N:` list (one heading per file/section), the fan-out step runs one worker per heading in isolated workspaces, and `serialized_sandbox` bundles the merged output. This is `sample_fanout`'s exact structure (`sample_fanout/workflow.yaml:48-74`) with real agents.
- Files: a new `agents/workflows/<id>/workflow.yaml`, new `agents/prompts/<planner>/AGENT.md` + `agents/prompts/<worker>/AGENT.md`, `SUPPORTED_PIPELINE_TYPES` + `PIPELINE_AGENTS` entries. Zero engine/compiler/composer edits.
- **Effort:** M (mostly prompt authoring). **Risk:** low — the runtime is proven (Register Phase 11 SC-001).

**Path A user experience:** the pipeline appears in the catalog like any other; the user launches it with a brief; the planner produces a list; the step fans out (parallel, capped at 4 by `DEFAULT_MAX_CONCURRENCY`); the merged deliverable comes back. Parallelism is free.

**Genuinely NEW code:** essentially none — only manifest/prompt/registration data. **Invariants:** SC-001/INV-1 preserved (no workflow-name branch added to the kernel); INV-3 goldens untouched (a new pipeline touches no existing golden); INV-5 preserved (pure data).

---

## 4. Path B — user-composable fan-out in the composer (the real "make fan-out user-facing")

**Goal:** a user toggles "fan out over a list" on a step in the composer, points it at an upstream producer step, saves/launches, and the step actually fans out. Grounded change set:

### 4.1 Frontend (2 composer surfaces + shared type)
- Extend the shared selection type: `StepSelection` (`AgentsPopup.tsx:1419-1425`) gains an optional fan-out lever. Because `_apply_selections` and the synth are keyed on the compact map, the cleanest shape is a per-step `strategy?: "fanout_batch"` plus a `task_source?: { source_step: string; parser?: "heading_tasks" | "json_tasks" }` (and optionally `fanout?: { max_parallel?: number }`). The generic reducer `applyLeverPatch` (`AgentsPopup.tsx:1452-1475`) already writes arbitrary keys, so it needs no change.
- Add the control to both surfaces (INV-3 reuse — do not fork): a "Fan out over a list" toggle in `CanvasConfigRail.tsx` (alongside the existing Validator/Review-gate/Retry toggles at :159-230) and in the AgentsPopup AdvancedExpander. On enable, show ONE follow-up: a select of the earlier steps to choose `source_step` (default = the immediately previous step). Do NOT offer a merge picker — merge is engine-owned (`fanout.py:793`).
- Guardrail in the UI: only offer the toggle on a step that has at least one upstream step (a fan-out needs a producer). Surface a hint when the chosen producer is not known to emit a list.
- **Effort:** M (two surfaces, one new control + one follow-up select; existing test files `CanvasConfigRail`-adjacent and `AdvancedExpander.test.tsx`/`IdeaInputPage.selections.test.tsx` give the pattern).

### 4.2 Backend — synth (`agents/workflows/selections.py`)
- `_synthesize_step` (`selections.py:78-133`): stop hardcoding `single_shot`. When the selection carries a `strategy`, emit `step["strategy"] = <selected>`; keep `single_shot` as the default when unset. The `fanout`/`task_source`/`on_conflict` projection already exists (:128-131), so once `strategy` is emitted the throwaway trust-compile validates a real fan-out step. (Add `strategy` to the projection; `_LEVER_KEYS` is dead and can be ignored or removed.)
- **Effort:** S. Trust is already satisfied — `fanout_batch`/`heading_tasks`/`json_tasks` are `user_allowed=True`, so `compile(trust="user")` passes with no flag change.

### 4.3 Backend — the decisive overlay (`agents/execution_engine/engine.py`)
- `_apply_selections` (`engine.py:6194-6274`), the `patch` block (`:6257-6272`): additionally overlay the fan-out levers from `user_step` when the user selected them — `strategy` (so the step actually dispatches `fanout_batch`), `fanout` (the `FanoutSpec`), `task_source` (the producer + parser), and `on_conflict`. Keep the guard that this fires ONLY when the user selected it, so the empty-selections path stays byte-identical (INV-3). This is THE change that makes a composed fan-out real.
- **Effort:** S–M. Must re-verify the 5 characterization goldens are byte/event-identical (they declare no selections, so `has_selections` short-circuits at `engine.py:6213` → unchanged plan).

### 4.4 Backend — the custom step-synthesis path (design decision, `engine.py:2285-2292`)
- Because `_apply_selections` only mutates steps present in `compiled.steps`, a fan-out overlay reaches a composed agent only if that agent is in the base manifest (for `custom`, the 8 agents in `custom/workflow.yaml`). Two clean options: (a) also apply the per-agent selection when a step is synthesized at `engine.py:2285-2292` (generic, by agent_id), or (b) scope Path-B fan-out to steps that are already in the base plan and document the constraint. Option (a) is more general and keeps the "compose any agent" promise; either is name-free (SC-001).
- **Effort:** S (a small, generic, agent_id-keyed change).

### 4.5 What Path B does NOT need
- **No security/trust flag flip.** Verified: `fanout_batch` (`fanout_batch.py:38`), `wave_scheduler` (`wave_scheduler.py:136`), `copy_disjoint` (`copy_disjoint.py:49`), `heading_tasks` (`heading_tasks.py:92`), `json_tasks` (`json_tasks.py:56`) are all `user_allowed=True`; the declarative `run_fanout` path requires no `spawn_subagents` grant (`fanout.py:251-326`; the grant gates only `_derive_fanout`, `engine.py:2920`). Do NOT touch `registry.py:117` or the `spawn_subagents` posture.
- **No new capability kind, no migration.** The selection persists in the existing `manifest_json` column; the compiler and kernel already handle the strategy. (Register Phase 22 §7 line 2348 lists "new capability kinds" and "enabling spawn_subagents" as out-of-scope precisely because neither is needed.)
- **No merge picker.** Engine-owned (`fanout.py:793`).
- **Concurrency/cost already bounded** by the per-run `BudgetManager` (default 8 subagents / 4 concurrent / depth 2 / 900s; `budget.py:43-46`, armed at `engine.py:1487`, reserved at `fanout.py:304-310`).

**Path B total effort:** M — roughly 2 FE files + 2 BE files + the custom-step decision + tests. **Biggest risk:** INV-3 golden parity on the overlay change (mitigated by the `has_selections` short-circuit) and a good default/guardrail for `task_source` so a fan-out step without a list producer degrades visibly rather than silently spawning nothing.

**Invariant check (Path B):** SC-001/INV-1 — the overlay stays keyed on `agent_id` + generic lever keys, no workflow-name branch (mirrors the existing `_apply_selections` contract, Register line 2302). INV-3 — empty selections remain a byte-identical no-op. INV-5 — no DSL; the compiler already treats `fanout`/`task_source` as pure data. Kernel-owns-control-flow — the user only DECLARES the fan-out; all spawn/isolation/merge control stays in `run_fanout` (INV-7).

---

## 5. The HACK contrast — un-excluding the `task` tool (recommended AGAINST)

**The shortcut:** delete the `task` exclusion in `deep_agent_runner.py` (`_LIBRARY_SUBAGENT_TOOL = "task"` at :85; the `excluded` set at :328; the `_ToolFilterMiddleware` at :352) so the model can call the library's `task` tool and self-spawn sub-agents from a prompt. It is roughly one line.

**Concrete guarantees it breaks (all verified against the current design):**
- **Determinism / reproducibility (INV-3 goldens).** Fan-out width and worker prompts would be model-decided per run, not derived from a parsed list — the characterization snapshots and any golden byte-parity become impossible.
- **Cost bounds.** `run_fanout` is the ONLY path that calls `budget.reserve(...)` before spawning (`fanout.py:304-310`); a model-driven `task` spawn bypasses `BudgetManager` entirely (subagents/concurrency/depth/wall-clock uncapped).
- **Workspace isolation + deterministic merge.** The engine selects per-worker isolation and the merge strategy by scope (`fanout.py:328-337,785-793`, INV-7); the `task` tool writes into the shared agent state with no isolated workspaces and no `copy_disjoint`/`git_3way` merge, so parallel writers can corrupt each other.
- **Security posture / INV-13.** `spawn_subagents` is `user_allowed=False` by design (`registry.py:117`) and `create_deep_agent` is adapter-only; self-spawn re-opens an uncontrolled, unbounded-depth spawn surface the CI banned-pattern gate exists to prevent (Register lines 1135-1136,1161).
- **Kernel-owns-control-flow (INV-7).** The whole architecture funnels both the declarative strategy and the runtime tool through ONE `run_fanout`; the `task` tool is a second, ungoverned spawn path.

**Recommendation: do NOT un-exclude `task`.** It trades every safety property above for saving the modest, well-scoped work in §3/§4. The architecture was explicitly designed to refuse it (Register: "do not resurrect").

---

## 6. Bottom line

Making fan-out user-facing without hacks is well-supported by the current architecture: the compiler and kernel already execute a declarative `fanout_batch` step end-to-end with zero kernel edits, and every capability the declarative path touches (`fanout_batch`, `heading_tasks`/`json_tasks`, `copy_disjoint`) is `user_allowed=True`, so no security or trust flag needs flipping and no migration or new capability kind is required. The fastest ship is **Path A** (S–M): register a `user_launchable` fan-out pipeline — promote `sample_fanout` or author a real "plan then fan out per item" pipeline — pure manifest/prompt/registration data, no composer work. The fuller feature is **Path B** (M): add a "fan out over a list" lever (+ an upstream-producer picker) to the two composer surfaces, make `selections._synthesize_step` emit the chosen strategy, and — the single decisive change without which nothing else matters — make `engine._apply_selections` (`engine.py:6257-6272`) overlay `strategy`/`fanout`/`task_source`/`on_conflict` onto the run plan (today it overlays only `validators`/`gates`/`model`/`retry`/`injects`), plus decide how the overlay reaches custom agents synthesized as bare `single_shot` steps at `engine.py:2285-2292`. The hack (un-excluding the `task` tool) is one line but forfeits determinism, cost bounds, workspace isolation, deterministic merge, and the security posture — recommend strongly against.
