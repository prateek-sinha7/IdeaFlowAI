# Path B — User-Composable Fan-Out in the Composer: Implementation-Ready Scope

**Branch:** `feat/ui-2` · **Date:** 2026-07-19 · **Mode:** design/scoping (read-only on code; this doc is the only write)
**Companion:** `.planning/FANOUT-USER-FACING-SCOPE.md` (the two-path investigation). This doc expands Path B into a build-ready plan.
**Method:** every file:line was re-verified against the code as it stands now.

**Headline:** Four small, mechanical changes make a user-composed step actually fan out — (1) `engine._apply_selections` must carry `strategy`/`fanout`/`task_source` onto the run-plan step (today it carries only `validators`/`gates`/`model`/`retry`/`injects`), (2) the same fan-out step must be applied at the absent-agent synthesis site (`engine.py:2285-2292`, which is the COMMON case for `custom` because `allowed_custom_agent_ids("custom")` unions all base-pipeline agents), (3) `selections._synthesize_step` must emit the chosen strategy instead of hardcoding `single_shot`, and (4) the two composer surfaces need a "fan out over a list" toggle + an upstream-producer picker. The compiler, kernel `run_fanout`, budget, and merge already work. **No security/trust flag flips, no new capability kind, no migration.** The producer story is settled (see **§0 — the definitive producer model**): fan-out is a graph edit that **inserts a dedicated producer node**, never mutates a chained agent (whose output contract would break its downstream consumer). The content question is RESOLVED — a real `## Task N:` producer (`prototype-plan`) already exists in the verified 63-agent pool, so fan-out isn't dead-on-arrival; the one content prerequisite for GENERAL fan-out is shipping a single generic **task-list-planner producer skill** (work-item P0), a curated prompt fragment, no machinery.

---

## 0. The producer model (DEFINITIVE) — fan-out INSERTS a node; it never mutates a chained agent

*Settled with the user 2026-07-20. This is the conceptual foundation that governs §4 (composer UX) and supersedes the old §8 "riskiest unknown".*

**Fan-out is a change to the workflow's SHAPE, not an attribute of an agent.** It is inherently a two-node pattern: a **producer** node emits a task list, and a **fanned worker** node runs one copy per task. The engine reads the list and owns the spawn/isolation/merge — the LLM never decides control flow (the `task`-tool self-spawn path is refused; see the companion doc). This is why fan-out cannot be "just a flag on one agent": the list must exist as data *before* the parallel spawn, so there are always two nodes.

**The producer is a NEW, dedicated node — you INSERT it; you do NOT retrofit a "producer skill" onto an agent already in a chain.** Load-bearing reason: an agent mid-chain has an OUTPUT CONTRACT — its output is the named input its downstream consumer reads (`latest_typed_content(source_step)` / `depends_on`). Attaching an "emit a `## Task N:` list" skill rewrites that output, so the downstream consumer receives a task list instead of the spec/design it was built to read — **the chain breaks.** A producer skill is therefore safe ONLY as the seed of a NEW node whose output is not already contractually consumed.

**Why a producer must be a DEDICATED list-emitter (from the parser).** `heading_tasks.parse` (verified §2 / `heading_tasks.py:39,66-68`) scans the agent's WHOLE output for `## Task N:` and slices each block from its header to the next `## ` heading. An agent that ALSO emits rich markdown (its own `## ` sections) tangles the slicing — which is why the working producers (`prototype-plan`, `sample-fanout-plan`) mandate *"your SOLE output is the task plan."* A `<tasks>…</tasks>` **side-channel** (agent emits its normal output + a separate task block; downstream reads the former, fan-out the latter) is NOT clean with the current parser: the `<tasks>` wrapper is only a fallback when no top-level `## Task N:` exist (`heading_tasks.py:41-45`), so it does not quarantine the list. Robust side-channeling would need a parser change (read ONLY the delimited block) AND burdens one agent with two competing jobs — **out of scope for v1.**

**The "fan-out producer skill" is the PROMPT that defines a producer node** — a curated, format-guaranteed prompt fragment (implemented as an `inject` / `AGENT.md` fragment, NOT a new engine capability kind) that instructs an agent to emit `## Task N:`. It SEEDS a producer node (optionally flavored by any agent's identity, to reuse domain knowledge); it is never bolted onto a mid-chain node. This is cheaper + safer than letting users hand-write the format (error-prone — they won't reliably type the exact contract the parser needs) or shipping one fixed planner (inflexible).

**Composer UX consequence (governs §4):** toggling **"fan out over a list"** on a step is a **graph edit** — the composer **inserts a dedicated producer node upstream** (seeded from the fan-out producer skill) and auto-wires it as the fanned step's `task_source.source_step`. It offers to reuse an EXISTING upstream node ONLY when that node is already a known list-producer; it NEVER mutates an already-chained agent's output to make it a producer. If a user points the source at a non-producer, that is a mis-wire the FE steers away from ("insert a task-list planner instead").

**Content status (RESOLVED — supersedes §8 item 1).** The composer's user pool is **63 agents** (verified via `allowed_custom_agent_ids("custom")`), and it DOES contain a real `## Task N:` producer — **`prototype-plan`** (verified: its `AGENT.md` mandates *"EVERY task MUST use EXACTLY this header format: `## Task N:`"* and emits `## Task 1: HTML Shell`, …). So fan-out is NOT dead-on-arrival — a user can wire `prototype-plan → fanned worker` today. BUT `prototype-plan` is DOMAIN-SPECIFIC (prototype page-build tasks) and is the ONLY shipped `## Task N:` producer in the pool. **The one content prerequisite for GENERAL fan-out is shipping a single generic task-list-planner producer skill/agent** (a generic analog of `prototype-plan`/`sample-fanout-plan`). Small content, no machinery — and it becomes minimal-slice work-item P0.

---

## 1. The runtime overlay fix (the crux) — pinned exactly

### 1a. `engine._apply_selections` currently drops the fan-out levers
Verified `backend/agents/execution_engine/engine.py:6194-6274`. The overlay re-compiles the selections through `trust="user"` (`:6223-6228`), indexes the result by agent_id (`:6245` `_user_by_agent = {s.agent_id: s for s in user_compiled.steps}`), then builds a `patch` per file step (`:6257-6272`):

```python
# engine.py:6257-6272 (VERIFIED current)
patch: dict = {}
if sel.get("validators"):
    merged_v = list(dict.fromkeys([*step.validators, *user_step.validators]))
    patch["validators"] = merged_v
if user_step.gates:
    merged_g = list(dict.fromkeys([*step.gates, *user_step.gates]))
    patch["gates"] = merged_g
if sel.get("model") and user_step.model is not None:
    patch["model"] = user_step.model
if sel.get("retry") and user_step.retry is not None:
    patch["retry"] = user_step.retry
if sel.get("injects"):
    patch["injects"] = list(dict.fromkeys([*step.injects, *user_step.injects]))
new_steps.append(dataclasses.replace(step, **patch) if patch else step)
```

It never reads `user_step.strategy`, `.fanout`, `.task_source`, or `.on_conflict`. **This is the make-or-break gap.**

### 1b. Exact patch additions
Add, inside the same `patch` block, guarded on the user having explicitly selected the lever (so the empty-selections path stays byte-identical, INV-3):

```python
# NEW — carry the fan-out levers (Path B). Each fires ONLY when the user selected it.
if sel.get("strategy") and user_step.strategy:
    patch["strategy"] = user_step.strategy          # e.g. "fanout_batch"
if sel.get("fanout") and user_step.fanout is not None:
    patch["fanout"] = user_step.fanout              # typed FanoutSpec (mode/max_parallel/count)
if sel.get("task_source") and user_step.task_source is not None:
    patch["task_source"] = user_step.task_source    # typed TaskSource (parser/source_step)
# on_conflict is OPTIONAL for v1 (engine default is "human_gate"); overlay only if selected:
# if sel.get("on_conflict"):
#     patch["on_conflict"] = user_step.on_conflict
```

Notes:
- **Do NOT overlay `tools`.** The declarative `fanout_batch` path needs no `spawn_subagents` grant (verified in the companion doc: `run_fanout`, `fanout.py:251-326`, performs no permission check; the grant gates only `_derive_fanout`, `engine.py:2920`). Under `trust="user"` the user step's `tools.spawn_subagents` is forced OFF anyway (`compiler.py:529`), so overlaying tools would only ever LOWER privilege — leave the base step's tools untouched.
- `user_step.strategy` is the trust-checked strategy string; because `strategy:fanout_batch` is `user_allowed=True` (`fanout_batch.py:38`), the `trust="user"` compile at `:6223` accepts it, so `user_step.strategy == "fanout_batch"` reaches here.

### 1c. The absent-from-base-manifest case (the COMMON case, not an edge)
Verified `engine.py:2245` iterates `ordered_agents` (the user's chosen agents) and `:2285-2292`:

```python
# engine.py:2285-2292 (VERIFIED current)
step = _steps_by_agent.get(spec.id)     # _steps_by_agent = {compiled.steps} (engine.py:2123)
strategy_name = getattr(step, "strategy", "single_shot") if step else "single_shot"
if step is None:
    from agents.workflows.plan import Step as _Step
    step = _Step(agent_id=spec.id, strategy=strategy_name)   # bare single_shot
```

`_steps_by_agent` is built from `compiled.steps` (`engine.py:2123`), i.e. the file-compiled BASE manifest steps. `_apply_selections` (`:6248`) also iterates only `compiled.steps`. **So any chosen agent NOT in the base manifest never receives a selection overlay and is run as a bare `single_shot` step.** For `custom` this is the norm: `allowed_custom_agent_ids("custom")` (`agents/registry.py`, the `if pipeline_type == "custom":` branch) **unions the custom pool with ALL non-revision base-pipeline agents** — contradicting its own docstring, which still claims it was "tightened to just the custom pool" (flag this stale docstring). `custom/workflow.yaml` declares only 8 steps (`market-research-agent`, `swot-analyst`, `roadmap-planner`, `security-auditor`, `test-case-generator`, `performance-optimizer`, `documentation-agent`, `report-generator`), so a composition that pulls in any cross-pipeline agent (or a bundled planner) lands in the absent case.

**Recommended fix — one trust-compile, reused at both sites:**

1. Thread the run's agent ids into `_apply_selections` and have it BOTH cover them in the trust re-compile AND return the trust-compiled user-step map. Change the call site `engine.py:1463`:
   ```python
   compiled, _user_steps_by_agent = self._apply_selections(
       compiled, selections, [s.id for s in agents]
   )
   ```
   `agents` (the passed specs) is in scope at `:1463` (param of `_execute_impl`, `engine.py:1088`), and the returned local is in scope at `:2285` (same method). This is the ONLY live caller of `_apply_selections` (verified: `resume_run` does not call it — WR-02 "resume drops selections" is a documented, separately-tracked limitation).

2. In `_apply_selections` (`engine.py:6194`):
   - Widen the synth agent set so the trust-compile produces a step for EVERY run agent, not just base-manifest agents:
     ```python
     # was: agent_ids = [s.agent_id for s in compiled.steps]   (engine.py:6222)
     base_ids = [s.agent_id for s in compiled.steps]
     agent_ids = list(dict.fromkeys([*base_ids, *(run_agent_ids or [])]))
     ```
   - Overlay onto `compiled.steps` exactly as today (extended with §1b). Do NOT add steps to `compiled.steps` — the membership assertion at `engine.py:1701-1714` compares `[s.agent_id for s in compiled.steps]` to `PIPELINE_AGENTS[compiled.id]` and would raise if the count changed.
   - Return `(dataclasses.replace(compiled, steps=new_steps), _user_by_agent)`. The two early returns must also become tuples: `return compiled, {}` at `:6214` (no selections) and `:6242` (CompilerError degrade).

3. At the synthesis site `engine.py:2285-2292`, consult the user-step map before falling back to bare `single_shot`:
   ```python
   step = _steps_by_agent.get(spec.id)
   if step is None:
       # Path B: a composed agent absent from the base manifest may carry a
       # user-selected fan-out strategy (+ task_source/fanout). Use its
       # trust-compiled user step so the selection reaches the run. Empty for
       # every non-composed run -> byte-identical bare single_shot below (INV-3).
       step = _user_steps_by_agent.get(spec.id)
   strategy_name = getattr(step, "strategy", "single_shot") if step else "single_shot"
   if step is None:
       from agents.workflows.plan import Step as _Step
       step = _Step(agent_id=spec.id, strategy=strategy_name)
   ```

**INV-3 parity:** when `selections` is None/empty, `has_selections` short-circuits (`engine.py:6213`), `_user_steps_by_agent == {}`, and both the overlay and the synthesis site behave byte-identically to today. One deliberate, benign delta: a composed absent agent that DOES carry selections now runs its trust-compiled step, which carries the compiler's default hooks (`audit_logger` + `secret_scan`, `compiler.py:406`) that a bare `_Step(...)` lacks — those hooks are non-blocking and arguably more correct; call it out in the test.

---

## 2. The schema / data path for `task_source` + parser — RESOLVED

**Open question answered:** `source_step` and `parser` do NOT live in `FanoutSpec`. They live in the step's separate `task_source` block (a `TaskSource`).

- `TaskSource` (`agents/workflows/plan.py:162-184`): `kind` (`none|inline|parsed|file`), `parser` (capability name, e.g. `"heading_tasks"`), `target`, `source_step` (the declared upstream producer step id), `spec_step`.
- `FanoutSpec` (`agents/workflows/plan.py:196-216`): `mode` (`parallel|sequential`), `max_parallel`, `agent`, `count`, `workers`, `merge_agent`. **No `source_step`/`parser` here** — confirmed.
- The runtime reads BOTH: `fanout_batch.py:75-85` reads `step.task_source.source_step` (`:76`) and `step.task_source.parser` (`:82-83`, default `heading_tasks` at `:32`) to source + parse the list, and `run_fanout` reads `step.fanout` for width/mode. So a composed fan-out step needs `strategy: fanout_batch` + `task_source:{...}` + (optional) `fanout:{...}`.

**Compiled-step schema (what the manifest step may declare)** — `_ALLOWED_STEP_KEYS` (`compiler.py:68-88`, verified): `agent, strategy, gates, hooks, validators, compaction, task_source, post_step, require_render, tools, model, fix, fanout, on_conflict, retry, injects, depends_on`. **`_ALLOWED_TASK_SOURCE_KEYS`** (`compiler.py:95-97`, verified): `{kind, parser, target, source_step, spec_step}`. The compiler already compiles `task_source` (`compiler.py:436-457`, trust-checking `parser`) and `fanout` (`compiler.py:539` via `_compile_fanout` at `:593`). No compiler change needed.

**Exact `StepSelection` fields the composer must persist** (the compact per-step map stored in `workflows.manifest_json` and consumed by `_apply_selections`):

```jsonc
"<agent_id>": {
  "strategy": "fanout_batch",
  "task_source": { "kind": "parsed", "parser": "heading_tasks", "source_step": "<upstream_agent_id>" },
  "fanout": { "mode": "parallel", "max_parallel": 4 }   // optional; kernel caps at DEFAULT_MAX_CONCURRENCY=4
}
```

Minimal viable selection = `{ "strategy": "fanout_batch", "task_source": { "kind": "parsed", "parser": "heading_tasks", "source_step": "<prev>" } }`. `fanout` may be omitted entirely (the kernel then fans one worker per parsed task with default concurrency).

---

## 3. The synthesizer change (`agents/workflows/selections.py`)

`_synthesize_step` (`selections.py:78-133`, verified) hardcodes `strategy: single_shot` at line 86 and NEVER overrides it; its projection loop (`:128-131`) already copies `fanout`, `task_source`, `on_conflict`, `tools` onto the raw step dict when present. So the ONLY change is to emit the selected strategy. Insert after the `isinstance(sel, dict)` guard (i.e. after `selections.py:95`):

```python
# selections.py — after the "not isinstance(sel, dict)" guard (~line 95)
# A user-selected strategy (e.g. fanout_batch) overrides the safe single_shot
# default. GENERIC — no workflow/agent-name literal (INV-1/SC-001). The compiler's
# trust="user" check is the authority: fanout_batch is user_allowed=True so this
# passes; a smuggled user_allowed=False strategy would be rejected NAMING it.
if isinstance(sel.get("strategy"), str) and sel["strategy"]:
    step["strategy"] = sel["strategy"]
```

`fanout` and `task_source` are already carried by the existing loop at `selections.py:128-131`, so no further edit there. The dead `_LEVER_KEYS` constant (`selections.py:43-46`, referenced only at its definition) can be left or deleted; it gates nothing.

**Trust confirmation (verified):** `strategy:fanout_batch` (`fanout_batch.py:38`), `task_parser:heading_tasks` (`heading_tasks.py:92`), `task_parser:json_tasks` (`json_tasks.py:56`) are all `user_allowed=True`; `FanoutSpec`/`TaskSource` are pure data (no trust). So the throwaway trust-check manifest that `synthesize_manifest` builds (`selections.py:136-181`, deliverable stub `single_file`) compiles cleanly under `trust="user"` for a fan-out selection at BOTH chokepoints (`user_workflows._compile_selections_trust_user:150-208` on SAVE; `run_commands._revalidate_selections_trust_user` → `run_commands.py:1535-1539` on LAUNCH). No flag flip. Keep it name-free (INV-1): the synth already keys only on `agent_id` + generic lever keys.

---

## 4. Frontend composer controls (two surfaces + the shared type)

### 4a. Shared selection type + reducer (no logic change)
`StepSelection` (`frontend/src/components/workflow/AgentsPopup.tsx:1419-1425`, verified `{validators?, gates?, model?, retry?}`) gains the fan-out levers:

```typescript
export type StepSelection = {
  validators?: string[];
  gates?: string[];
  model?: string;
  retry?: number;
  // Path B — fan-out:
  strategy?: "fanout_batch";
  task_source?: { kind: "parsed"; parser: "heading_tasks" | "json_tasks"; source_step: string };
  fanout?: { mode?: "parallel"; max_parallel?: number };
};
```

`applyLeverPatch` (`AgentsPopup.tsx:1452-1475`) is generic — it iterates `Object.entries(patch)` and deletes keys whose value is `undefined`/`""`/`[]` — so toggling fan-out ON writes `{strategy, task_source}` and toggling OFF writes `{strategy: undefined, task_source: undefined, fanout: undefined}` (cleared). No reducer change. `has_selections` (`selections.py:218-227`) treats a `{strategy, task_source}` entry as truthy, so the overlay runs.

### 4b. Canvas config rail (`composer/CanvasConfigRail.tsx`)
Verified this rail already renders Model / Validator / Review-gate / Retry via `patch({...})` (`CanvasConfigRail.tsx:141/173/193/212`) and receives `agent, index, total, selection, onSelection` (`:36-49`). It does NOT currently receive the list of earlier agents. Its parent `CanvasView.tsx` renders it at `:270` and owns the ordered `pipelineAgents` (`:43`). Changes:
- `CanvasView.tsx:270`: pass `priorAgents={pipelineAgents.slice(0, selectedIndex)}` (agents before the selected node).
- `CanvasConfigRail.tsx`: add an "Overrides" row **"Fan out over a list"** (a `Toggle`, reuse the existing `Toggle` component at `:82-112`). On enable, `patch({ strategy: "fanout_batch", task_source: { kind: "parsed", parser: "heading_tasks", source_step: priorAgents.at(-1)?.id } })`; on disable, `patch({ strategy: undefined, task_source: undefined, fanout: undefined })`. When enabled, render a follow-up `<select>` "Source list from" populated from `priorAgents` (default = the immediately-preceding agent), writing `patch({ task_source: { ...sel.task_source, source_step: e.target.value } })`. Disable the toggle when `priorAgents.length === 0` (a fan-out needs a producer) with a hint.

### 4c. Simple-view Advanced expander (`AgentsPopup.tsx` `AdvancedExpander`)
Verified `AdvancedExpander` (`AgentsPopup.tsx:1547`) maps per-agent rows (`:1621 agents.map`) exposing Validator/Gate/Model/Retry via `updateLever(agent.id, {...})` (`:1578`, `:1666`). Add the same "Fan out over a list" toggle + source picker inside each agent's row, using `updateLever` with the identical patch shape. The source picker's option list = the agents that appear BEFORE this agent in the composition (the expander already has the full `agents` array in scope at `:1621`, so `agents.slice(0, idx)`).

### 4d. Parser + merge story (v1 decisions)
- **Parser default = `heading_tasks`** (matches the runtime default `fanout_batch.py:32`). Do NOT expose `json_tasks` in v1 (keep it a future "advanced" option). Rationale: a natural-language producer emitting `## Task N:` headings is the low-friction path; JSON tasks require the producer to emit strict JSON.
- **Merge = engine-default; do NOT expose a merge picker.** Verified merge is engine-selected by isolation scope (`fanout.py:785-793`: `git_3way` for a git worktree, else `copy_disjoint`), INV-7 "the ENGINE picks the merge strategy ... NOT the manifest". `FanoutSpec` has no `merge` field; `fanout_batch`'s `config_schema.merge` (`fanout_batch.py:43-47`) is unread on this path. **Leave `merge_agent` unset in v1** (engine default `on_conflict: human_gate` — the run pauses on a real conflict via the one durable HITL). Exposing a merge-agent picker is a post-v1 knob.
- **Max-parallel** may be exposed as an optional number, but it is redundant with the kernel cap `min(declared, DEFAULT_MAX_CONCURRENCY=4)` (`fanout.py:170-179`, `budget.py:44`). Recommend omitting it from v1 UI.

### 4e. Producer sourcing — reuse-or-INSERT (governed by §0)
Per §0, a fan-out's `task_source.source_step` must be a DEDICATED list-producer node — never a mutation of a chained agent's output. So the source control is NOT a plain "pick any earlier agent" (the §4b/§4c pickers must be constrained to this rule). It offers two actions:
- **Reuse** an existing upstream node ONLY if it is a KNOWN `## Task N:` producer (v1 allow-list: `prototype-plan`; grow it as producer skills ship). The `<select>` in §4b/§4c should list only known-producer earlier agents, not every earlier agent.
- **Insert a producer** (the default primary action): "Add a task-list planner" inserts a NEW producer node — seeded from the bundled generic producer skill (work-item **P0**) — immediately before the fanned step and auto-wires it as `source_step`. This is a graph edit (add a node), not a lever on an existing agent.

The "default = immediately-preceding agent" shortcut (§4b/§4c) is valid ONLY when that agent is a known producer; otherwise the default action is **Insert**. Never let the picker point `source_step` at a non-producer chained agent — it would rewrite nothing but spawn no workers (§5b) and confuses "reuse" with the broken "retrofit a skill onto a chained agent" model §0 rules out.

---

## 5. Validation / guardrails

### 5a. Compile-time (backend)
- **Trust (already enforced):** `trust="user"` at SAVE + LAUNCH rejects any `user_allowed=False` capability NAMING it (`compiler._check_trust`; `run_commands.py:1535`, `user_workflows.py:150-208`). Fan-out caps are all user-allowed, so a legitimate fan-out passes; a smuggled `spawn_subagents`/exec grant is rejected (`compiler.py:480-499`).
- **Satisfiability + producer-first order (already enforced, with a caveat):** `presort_specs` (`app/api/composition_order.py:34`) → `WorkflowResolver().presort` (`resolver.py:192`) reorders producer-first on **produces/consumes** contracts and rejects an unsatisfiable set (`UnsatisfiableComposition` → 422) at LAUNCH (`run_commands.py:1481`) and SAVE. Verified `presort` is **deterministic from input order** (`resolver.py` docstring: "output is deterministic from the input order"), so a user-placed producer-before-fanout ordering is preserved when there is no produces/consumes edge between them.
- **GAP — `task_source.source_step` is not a DAG edge.** The compiler constructs `TaskSource` with whatever `source_step` string is given (`compiler.py:451-457`) and does not check it names a real, earlier step; and `presort`/`validate` key on produces/consumes, not `task_source`. **Recommended additive compile-time guard (INV-5-safe, pure data):** in `_compile_step` (or a post-compile pass over the ordered steps), when a step's `strategy == "fanout_batch"` and `task_source.source_step` is set, raise `CompilerError` if `source_step` is not the id of an EARLIER compiled step. This will not break existing manifests (`sample_fanout` declares `source_step: sample-fanout-plan` which precedes the fan-out step; `sample_wave` similarly). Keep it generic (no workflow-name literal).

### 5b. Frontend UX guardrails
- The source picker only offers EARLIER agents (§4b/§4c), so the user cannot pick a self/forward reference.
- Disable the fan-out toggle for the FIRST agent (no producer) with an inline hint: "Add an earlier step that outputs a task list to fan out over."
- When fan-out is enabled but the chosen producer is not known to emit a list, show a non-blocking warning ("This step will fan out one worker per `## Task N:` heading its source step outputs"). We cannot statically prove the producer emits headings (it is a prompt-time behavior), so this stays a warning, and the runtime already degrades safely: `fanout_batch.py:96-109` falls back to `fanout.count` identical workers, else logs "no workers spawned" and yields nothing.

### 5c. Invariants gating this work
- **INV-1 / SC-001 (generic keying):** the overlay keys on `agent_id` + generic lever keys; the synth keys on `agent_id`; no workflow/agent-name literal is added to the kernel. The banned-pattern grep (`test_banned_patterns.py`) must stay 0.
- **INV-3 (goldens byte/event-identical):** the 5 characterization goldens declare no selections → `has_selections` short-circuit → unchanged plan. Re-run them with `SNAPSHOT_UPDATE` unset; they must stay green.
- **INV-5 (no DSL):** manifests remain pure data; the fan-out control flow already lives in `run_fanout`/`fanout_batch` strategy, not the compiler. The proposed `source_step` guard is a pure data check, not control flow.
- **Kernel-owns-control-flow (INV-7/INV-12):** unchanged — the user only DECLARES the fan-out; spawn/isolation/merge/concurrency/budget stay inside `run_fanout` (`fanout.py`). No second spawn path is introduced.
- **Ports & Adapters / import-linter 4/0:** all edits are in `engine.py` (kernel), `selections.py` (workflows), and FE — none introduces a forbidden import.

---

## 6. Tests

### 6a. Backend unit
- `tests/unit/test_user_workflows_selections.py` (extend): `_synthesize_step` emits `strategy: fanout_batch` when the selection carries it, carries `task_source`/`fanout`, and defaults to `single_shot` when absent; `synthesize_manifest` + `WorkflowCompiler().compile(trust="user")` ACCEPTS a fan-out selection (fanout_batch/heading_tasks user-allowed) and REJECTS a smuggled `spawn_subagents`/exec grant.
- `tests/agents/test_compiler.py` / `test_compiler_trust.py`: a step declaring `strategy: fanout_batch` + `task_source:{parser: heading_tasks, source_step: X}` compiles to a `Step` with populated `.strategy`/`.task_source`/`.fanout` under `trust="user"`; the new `source_step`-must-be-upstream guard raises `CompilerError` on a forward/unknown ref and passes for `sample_fanout`.
- New engine unit for `_apply_selections`: (i) the patch carries `strategy`/`fanout`/`task_source` onto an IN-PLAN step; (ii) the ABSENT-agent case — a composed agent not in the base manifest gets its fan-out step at the synthesis site via `_user_steps_by_agent`; (iii) empty selections → plan byte-identical (INV-3) and `_user_steps_by_agent == {}`.

### 6b. Backend characterization / end-to-end (offline)
- Add an offline test mirroring `tests/agents/test_sc001_fanout.py`: build a COMPOSED (selections-driven, not file-manifest) fan-out — a producer agent that emits a 3-task `## Task N:` list + a consumer step whose selection sets `strategy: fanout_batch` + `task_source.source_step = producer` — drive it through `engine.execute(selections=...)` and assert 3 `subagent_spawned`/`subagent_result` events and a merged deliverable, with `grep -rc <workflow-name> agents/execution_engine/ == 0` (SC-001). Reuse the offline `shared_read` harness caveat from `test_sc001_fanout` (Register line 1162): isolated per-worker writes are a live-Bedrock concern.
- Golden guard: run the 5 characterization snapshots (`SNAPSHOT_UPDATE` unset) — must stay byte/event-identical.

### 6c. Frontend (vitest)
- `AdvancedExpander.test.tsx` / a new `CanvasConfigRail.test.tsx`: the "Fan out over a list" toggle persists `{strategy:"fanout_batch", task_source:{source_step:<prev>}}` into the selection; the source picker defaults to the immediately-preceding agent and only lists earlier agents; the toggle is disabled for the first agent; the no-producer/unknown-producer warning renders.
- `CanvasView.test.tsx`: `priorAgents` is threaded to the rail; changing the selected node updates the available source options.
- `IdeaInputPage.selections.test.tsx`: the composed fan-out selection is threaded into the `createUserWorkflow` save payload AND the launch payload (`selections`), and omitted when empty (INV-3).

### 6d. Live proof (orchestrator runs; do not run here)
Compose in the builder: agent A (a task-list planner that outputs `## Task 1..N:`) → agent B with "Fan out over a list" enabled sourcing from A. Save, launch on live Bedrock, and observe (i) N parallel `subagent_spawned` events (≤ 4 concurrent), (ii) per-worker `subagent_result`, (iii) a merged deliverable, (iv) no `spawn_subagents` grant required. Contrast a control run with fan-out OFF (single_shot, one output).

---

## 7. Effort + sequencing

Sub-pieces (rough sizing):
- **P0 — Generic producer skill (content, §0/§4e):** a curated task-list-planner `AGENT.md`/inject that emits `## Task N:` for any input, registered into the user pool + surfaced by the composer's "Insert a producer" action. **S** (content, no engine change). Required for GENERAL fan-out; `prototype-plan` already covers the prototype domain, so a demo/minimal slice can ship without P0 and still fan out in that domain.
- **P1 — Overlay + absent-case (`engine.py`):** `_apply_selections` patch additions (§1b), signature/return + call-site (§1c step 1-2), synthesis-site consult (§1c step 3). **M** (small diffs, but the return-signature change + the INV-3 golden re-verify make it the highest-care piece). **The make-or-break piece — nothing works without it.**
- **P2 — Synthesizer (`selections.py`):** emit `strategy` (§3). **S.**
- **P3 — Schema/selection type (FE) + no reducer change:** `StepSelection` (§4a). **S.**
- **P4 — FE controls:** toggle + source picker on both surfaces + `priorAgents` threading (§4b/§4c/§4d). **M** (two surfaces, one new control + one follow-up select).
- **P5 — Validation guardrails:** the additive `source_step`-upstream compile guard + FE disable/warn (§5). **S.**
- **P6 — Tests:** unit + one offline characterization + FE (§6). **M.**

Total: **M** (aligns with the companion doc's Path B estimate). Roughly 2 backend files (`engine.py`, `selections.py`) + 3-4 FE files (`AgentsPopup.tsx`, `CanvasConfigRail.tsx`, `CanvasView.tsx`, type) + optional `compiler.py` guard + tests.

**Recommended build order (each independently verifiable):**
1. **P2 synthesizer** (isolated, unit-testable immediately).
2. **P1 overlay + absent-case** (the crux; prove with an engine unit test + the offline composed-fan-out characterization from §6b BEFORE any FE work — this de-risks the whole feature).
3. **P3 + P4 FE controls** (now the backend actually honors what they persist).
4. **P5 validation guardrails.**
5. **P6 remaining tests + live proof.**

**Minimal-first slice (smallest thing that makes a user-composed fan-out actually run):**
P1 + P2 + a minimal P3/P4 = a single "Fan out over a list" toggle whose source defaults to the immediately-preceding step, `heading_tasks` parser fixed, engine-default merge, no advanced knobs (no parser choice, no merge picker, no max-parallel field, no `on_conflict`). This slice is fully functional end-to-end. Defer to a second pass: the `source_step`-upstream compile guard (P5 — the FE earlier-only picker is the interim guardrail), `json_tasks` parser exposure, `merge_agent`/`on_conflict` knobs, and `max_parallel` UI.

**Nothing blocks the minimal-first slice** on the CODE side — every capability it needs is already registered and user-allowed. For GENERAL fan-out, add work-item **P0** (the generic producer skill, §0/§4e); for a prototype-domain demo, `prototype-plan` is already a working producer, so P0 can be deferred. Producer sourcing follows the **§0 insert-a-node** model — the composer inserts/reuses a dedicated producer node, and NEVER retrofits a skill onto a chained agent (which would break that agent's output contract).

---

## 8. Open risks / unknowns (flag for the orchestrator to verify live)

1. **RESOLVED (was "riskiest") — a producer exists; a GENERIC one is the P0 content prereq.** Verified against the live agent library: the composer pool is **63 agents** and DOES include a real `## Task N:` producer, `prototype-plan` (its `AGENT.md` mandates the exact header format) — so fan-out is not dead-on-arrival. But `prototype-plan` is domain-specific (prototype page-build tasks) and is the only shipped `## Task N:` producer, so **GENERAL fan-out needs one bundled generic task-list-planner** (an analog of `sample-fanout-plan`, `sample_fanout/workflow.yaml:49`), delivered as a curated producer skill/`AGENT.md` (see §0). This is **work-item P0** (content, no machinery). Without it a user can still fan out over `prototype-plan` in the prototype domain; a non-producer source degrades to the `fanout_batch.py:104-109` "no workers" path — which §4/§5b steer away from. NOTE (per §0): the producer must be a NEW inserted node, never a skill retrofitted onto a chained agent (that would rewrite its output contract and break its consumer).
2. **`task_source.source_step` ordering is not a DAG edge.** Producer-before-fanout relies on the user's placement order surviving `presort` (deterministic for unconstrained agents) plus the §5a additive compile guard. If some OTHER produces/consumes contract reorders the producer AFTER the fan-out step, the fan-out reads empty content and degrades silently. Verify with a multi-agent composition where the producer also participates in a produces/consumes chain.
3. **Offline harness cannot prove per-worker isolation.** Per Register line 1162, the offline fan-out harness runs in `shared_read`, so genuine per-worker isolated writes + `copy_disjoint`/`git_3way` merge are a LIVE concern. The §6d live proof is the real evidence for isolation + merge correctness.
4. **`_apply_selections` return-signature change** touches its single live caller (`engine.py:1463`). Confirmed `resume_run` does not call it (WR-02 "resume drops selections" is a known, separately-tracked limitation) — but verify no other caller was added since, and note that a backend-restart RESUME of a composed fan-out run currently re-drives the bare file plan (the fan-out overlay is lost on resume, same as all selections today).
5. **`allowed_custom_agent_ids("custom")` docstring is stale** (claims tightened-to-custom-pool; the code unions all base agents). Not a blocker, but correct the docstring while in the file so the absent-case reasoning isn't re-litigated.
6. **Benign hook delta on absent composed agents** (§1c): a composed agent that lands in the synthesis site now runs its trust-compiled step carrying default `audit_logger`/`secret_scan` hooks (a bare `_Step` had none). Non-blocking hooks; assert the intended behavior in the engine unit test rather than treating it as a regression.
