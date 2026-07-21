# Phase 51: User-Composable Fan-Out in the Composer (Path B) - Pattern Map

**Mapped:** 2026-07-20
**Files analyzed:** 8 change sites (5 MODIFY + 2 NEW + 1 test-analog)
**Analogs found:** 8 / 8 (every site has an exact in-repo analog)
**Branch:** feat/ui-2 (read-only; no source edited)

> All excerpts below are the ACTUAL current code at the cited lines, read live this session.
> Line/path DRIFT vs. the scope doc is called out inline and summarized in the final section.

---

## File Classification

| File | Change | Role | Data Flow | Closest Analog | Match |
|------|--------|------|-----------|----------------|-------|
| `backend/agents/execution_engine/engine.py` | MODIFY | kernel / runtime overlay | transform (plan→plan) | itself (existing lever patch block) | exact (self) |
| `backend/agents/workflows/selections.py` | MODIFY | synthesizer | transform (selection→step dict) | itself (existing projection loop) | exact (self) |
| `backend/agents/workflows/compiler.py` | MODIFY (D9 guard) | compiler / validator | batch validate | `_compile_step` task_source block `:436-457` | role+flow |
| `frontend/src/components/workflow/composer/CanvasConfigRail.tsx` | MODIFY | component (config rail) | event→state (request-response) | existing `Toggle` `:82-112` + `patch()` `:77-80` | exact (self) |
| `frontend/src/components/workflow/composer/CanvasView.tsx` | MODIFY | component (canvas owner) | prop threading | existing `CanvasConfigRail` render `:270` | exact (self) |
| `frontend/src/components/workflow/AgentsPopup.tsx` | MODIFY | component + shared type/reducer | event→state | `AdvancedExpander` rows `:1621` + `updateLever` `:1578` | exact (self) |
| Generic producer skill `AGENT.md` (NEW) | CREATE | content / prompt fragment | — | `sample-fanout-plan` fixture + `prototype-plan/AGENT.md` | exact |
| Offline composed-fan-out characterization (NEW) | CREATE | test | event-driven assertion | `backend/tests/agents/test_sc001_fanout.py` | exact |

---

## Pattern Assignments

### 1. `backend/agents/execution_engine/engine.py` (kernel, transform)

**Analog: itself** — the existing lever-patch block is the template the three new fan-out lines copy.

**1a. The patch block to EXTEND** (`engine.py:6257-6272`, VERIFIED verbatim):

```python
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
    patch["injects"] = list(
        dict.fromkeys([*step.injects, *user_step.injects])
    )
new_steps.append(dataclasses.replace(step, **patch) if patch else step)
```

**Pattern to follow (D3/§1b):** append three MORE guarded lines in the SAME shape — each fires only when `sel.get(...)` is truthy so the empty path stays byte-identical (INV-3):
```python
if sel.get("strategy") and user_step.strategy:
    patch["strategy"] = user_step.strategy
if sel.get("fanout") and user_step.fanout is not None:
    patch["fanout"] = user_step.fanout
if sel.get("task_source") and user_step.task_source is not None:
    patch["task_source"] = user_step.task_source
```
Do NOT add a `tools` overlay (run_fanout needs no `spawn_subagents` grant — confirmed below).

**1b. The signature + no-selections early return** (`engine.py:6194`, `:6213-6214`, `:6222`, VERIFIED):
```python
def _apply_selections(compiled, selections: dict | None):
    ...
    if not has_selections(selections):
        return compiled            # ← becomes: return compiled, {}
    ...
    agent_ids = [s.agent_id for s in compiled.steps]   # :6222  ← widen with run_agent_ids
    ...
    _user_by_agent = {s.agent_id: s for s in user_compiled.steps}   # :6245
    ...
    return dataclasses.replace(compiled, steps=new_steps)   # :6274 ← return (…, _user_by_agent)
```
The CompilerError degrade path also early-returns `compiled` (`:6242`) → must become `return compiled, {}`.

**Pattern (§1c):** add a `run_agent_ids: list[str] | None = None` param; widen `agent_ids` to `list(dict.fromkeys([*base_ids, *(run_agent_ids or [])]))`; return `(compiled_or_replaced, _user_by_agent)` at ALL THREE exits. Do NOT append to `compiled.steps` (membership assertion below would raise).

**1c. The single caller to update** (`engine.py:1463`, VERIFIED — one return today):
```python
compiled = self._apply_selections(compiled, selections)
```
`agents` (the run specs) is in scope here (param of `_execute_impl`). Change to:
```python
compiled, _user_steps_by_agent = self._apply_selections(
    compiled, selections, [s.id for s in agents]
)
```
Confirmed this is the ONLY live caller (resume_run does not call it — WR-02).

**1d. The absent-agent synthesis site** (`engine.py:2285-2292`, VERIFIED verbatim):
```python
step = _steps_by_agent.get(spec.id)
strategy_name = getattr(step, "strategy", "single_shot") if step else "single_shot"
if step is None:
    # Synthesize a minimal step carrying the agent id so the handle
    # can resolve the AgentSpec (single_shot needs only agent_id).
    from agents.workflows.plan import Step as _Step

    step = _Step(agent_id=spec.id, strategy=strategy_name)
```
**Pattern (§1c step 3):** consult `_user_steps_by_agent.get(spec.id)` BEFORE falling back to bare single_shot:
```python
step = _steps_by_agent.get(spec.id)
if step is None:
    step = _user_steps_by_agent.get(spec.id)   # Path B: composed absent agent's fan-out step
strategy_name = getattr(step, "strategy", "single_shot") if step else "single_shot"
if step is None:
    from agents.workflows.plan import Step as _Step
    step = _Step(agent_id=spec.id, strategy=strategy_name)
```

**1e. The membership assertion — DO NOT BREAK** (`engine.py:1701-1714`, VERIFIED):
```python
_compiled_agent_ids = [s.agent_id for s in compiled.steps]
...
if _compiled_agent_ids and _compiled_agent_ids != _membership_ids:
    raise RuntimeError("compiled plan step order does not match the registry ...")
```
Guardrail: the overlay must REPLACE steps in place, never add/remove them, or this raises.

**Also:** correct the stale `allowed_custom_agent_ids("custom")` docstring while in the codebase (Risk #5) — it claims "tightened to custom pool" but the code unions all non-revision base agents.

---

### 2. `backend/agents/workflows/selections.py` (synthesizer, transform)

**Analog: itself** — `_synthesize_step` (`:78-133`, VERIFIED). Hardcoded default at `:86`:
```python
step: dict = {"agent": agent_id, "strategy": "single_shot"}
if not sel:
    return step
if not isinstance(sel, dict):
    step["__invalid_selection__"] = sel
    return step      # ← :95 — insert the strategy override right AFTER this guard
```
Existing generic projection loop (`:128-131`, VERIFIED — already carries `fanout`/`task_source`):
```python
for key in ("injects", "compaction", "post_step", "fix", "fanout",
            "on_conflict", "tools", "hooks", "task_source", "depends_on"):
    if sel.get(key) is not None:
        step[key] = sel[key]
```
**Pattern to follow (D5/§3):** the ONLY new line, inserted after `:95`, keyed generically (no name literal):
```python
if isinstance(sel.get("strategy"), str) and sel["strategy"]:
    step["strategy"] = sel["strategy"]
```
`fanout`/`task_source` already ride the `:128-131` loop — no further edit. The `single_shot` default at `:86` stays for the absent/empty path.

---

### 3. `backend/agents/workflows/compiler.py` (compiler/validator, batch)

> **DRIFT:** the task prompt and CONTEXT canonical-refs cite `backend/agents/execution_engine/compiler.py`. ACTUAL path is **`backend/agents/workflows/compiler.py`** (the engine imports `from agents.workflows.compiler import WorkflowCompiler`). All cited line numbers are correct against the real file.

**`_ALLOWED_STEP_KEYS`** (`:68-90`, VERIFIED — includes `strategy`, `task_source`, `fanout`, `on_conflict`) and **`_ALLOWED_TASK_SOURCE_KEYS`** (`:95-97`, VERIFIED):
```python
_ALLOWED_TASK_SOURCE_KEYS: frozenset[str] = frozenset(
    {"kind", "parser", "target", "source_step", "spec_step"}
)
```
**Analog — the existing `task_source` compile block** (`:436-457`, VERIFIED) where `source_step` is read WITHOUT an upstream check:
```python
task_source = None
raw_ts = raw.get("task_source")
if raw_ts is not None:
    extra_ts = set(raw_ts) - _ALLOWED_TASK_SOURCE_KEYS
    if extra_ts:
        raise CompilerError(...)
    parser = raw_ts.get("parser")
    if parser is not None and not registry.is_registered("task_parser", parser):
        raise CompilerError(f"unknown task_parser '{parser}' in {where}")
    if parser is not None:
        self._check_trust(registry, "task_parser", parser, trusted, where)
    task_source = TaskSource(
        kind=raw_ts.get("kind", "none"),
        parser=parser,
        target=raw_ts.get("target"),
        source_step=raw_ts.get("source_step"),   # ← accepted with NO upstream check
        spec_step=raw_ts.get("spec_step"),
    )
```
**Pattern to follow (D9/§5a):** add a PURE-DATA additive guard (no DSL, INV-5-safe): when `strategy == "fanout_batch"` and `task_source.source_step` is set, raise `CompilerError` unless `source_step` names an EARLIER already-compiled step. Because per-step compilation runs in order, the cleanest home is a POST-COMPILE pass over the ordered `steps` (so "earlier" = index-lower) — mirror the `CompilerError(f"... in {where}")` message style above. Must pass for `sample_fanout` (`source_step: sample-fanout-plan` precedes the fan-out step) and `sample_wave`; keep it name-free.

---

### 4. `frontend/src/components/workflow/composer/CanvasConfigRail.tsx` (component, event→state)

> **DRIFT:** scope path `frontend/src/components/composer/…` → ACTUAL `frontend/src/components/workflow/composer/…`. Line numbers correct.

**Analog: the reusable `Toggle`** (`:82-112`, VERIFIED — an accessible `role="switch"` button) and the shared **`patch()`** writer (`:77-80`, VERIFIED):
```python
const patch = (p: Partial<StepSelection>) => {
  const next = applyLeverPatch(sel, p);
  onSelection(agent.id, Object.keys(next).length > 0 ? next : undefined);
};
```
Existing lever rows use `patch(...)` — e.g. Validator toggle (`:168-175`), Review-gate (`:187-195`), Model select (`:141`), Retry stepper (`:212`/`:224`). All VERIFIED. Props (`:36-49`, VERIFIED):
```python
export function CanvasConfigRail({ agent, index, total, selection, onSelection }: {
  agent: AgentDef | null;
  index: number; total: number;
  selection?: StepSelection;
  onSelection: (agentId: string, sel: StepSelection | undefined) => void;
})
```
**Pattern to follow (D6/§4b):**
- Add a `priorAgents: AgentDef[]` prop (threaded from CanvasView — see #5).
- Add an "Overrides" row "Fan out over a list" using the existing `Toggle`; on enable `patch({ strategy: "fanout_batch", task_source: { kind: "parsed", parser: "heading_tasks", source_step: priorAgents.at(-1)?.id } })`; on disable `patch({ strategy: undefined, task_source: undefined, fanout: undefined })`.
- When enabled, render a "Source list from" `<select>` (mirror the Model `<select>` at `:135-152`) populated from `priorAgents`, writing `patch({ task_source: { ...sel.task_source, source_step: e.target.value } })`.
- Disable the toggle when `priorAgents.length === 0` (reuse the `Toggle` `disabled` prop) with an inline hint.

---

### 5. `frontend/src/components/workflow/composer/CanvasView.tsx` (component, prop threading)

**Analog: the existing rail render** (`:270-276`, VERIFIED):
```python
<CanvasConfigRail
  agent={selAgent}
  index={selIndex}
  total={pipelineAgents.length}
  selection={selAgent ? selections[selAgent.id] : undefined}
  onSelection={onSelection}
/>
```
`pipelineAgents` is the ordered prop (`:49`/`:63`, VERIFIED) and the selected index is the local `selIndex` (`:84-87`, VERIFIED — NOT `selectedIndex`; scope names it loosely):
```python
const foundIndex = pipelineAgents.findIndex((a) => a.id === selectedId);
const selIndex = foundIndex >= 0 ? foundIndex : pipelineAgents.length > 0 ? 0 : -1;
const selAgent = selIndex >= 0 ? pipelineAgents[selIndex] : null;
```
**Pattern to follow (D6/§4b):** add one prop to the render — `priorAgents={pipelineAgents.slice(0, selIndex)}` (agents before the selected node).

---

### 6. `frontend/src/components/workflow/AgentsPopup.tsx` (component + shared type/reducer, event→state)

**6a. `StepSelection` type + `SelectionsMap`** (`:1419-1425`, VERIFIED):
```python
export type StepSelection = {
  validators?: string[];
  gates?: string[];
  model?: string;
  retry?: number;
};
export type SelectionsMap = Record<string, StepSelection>;
```
**Pattern (D6/§4a):** widen with `strategy?: "fanout_batch"`, `task_source?: { kind: "parsed"; parser: "heading_tasks" | "json_tasks"; source_step: string }`, `fanout?: { mode?: "parallel"; max_parallel?: number }`.

**6b. `applyLeverPatch`** (`:1452-1474`, VERIFIED) — the SINGLE generic writer; no change needed (it deletes keys whose value is `undefined`/`""`/`[]`):
```python
export function applyLeverPatch(current, patch): StepSelection {
  const cur = { ...(current ?? {}) };
  for (const [k, v] of Object.entries(patch)) {
    const key = k as keyof StepSelection;
    if (v === undefined || v === "" || (Array.isArray(v) && v.length === 0)) delete cur[key];
    else cur[key] = v;
  }
  if (cur.validators && cur.validators.length > 0) { /* auto-attach validation gate */ }
  return cur;
}
```
So toggling ON writes `{strategy, task_source}`; OFF writes `{strategy: undefined, task_source: undefined, fanout: undefined}` (cleared). No reducer change (D6).

**6c. `AdvancedExpander` + `updateLever`** (`:1547-1594`, VERIFIED). `updateLever` delegates to `applyLeverPatch` (`:1586`); the per-agent rows are `agents.map((agent) => …)` (`:1621`) and the existing Validator lever calls `updateLever(agent.id, { validators: … })` (`:1666`). Full `agents` array is in scope so `agents.slice(0, idx)` gives the earlier agents.
**Pattern (D6/§4c):** add the identical "Fan out over a list" toggle + source `<select>` inside each agent row, driven by `updateLever(agent.id, { strategy, task_source })`; source options = `agents.slice(0, idx)`; disable for `idx === 0`.

---

### 7. Generic producer skill — NEW `AGENT.md` / inject (content, P0)

**Analog A — the SC-001 fixture producer** `backend/tests/agents/fixtures/sc001_fanout/sample-fanout-plan/AGENT.md` (VERIFIED): frontmatter `tools: []`, `produces: [sample-fanout-plan]`, body = *"Emit a task plan with exactly … `## Task N:` headings — one per fan-out worker … the heading_tasks parser turns each heading into one fan-out worker request."*

**Analog B — the shipped domain producer** `backend/agents/prompts/prototype-plan/AGENT.md` (VERIFIED, the v1 reuse allow-list target). Its contract, to COPY generically:
- `## Task 1: HTML Shell` … `## Task 2: …` literal headers (`:30,32`).
- *"EVERY task MUST use EXACTLY this header format: `## Task N:`"* (`:38`).
- *"Your SOLE output is the task plan as plain text … Produce the plan and nothing else."* (`:48`).

**Pattern to follow (D8/§0):** ship ONE curated, domain-GENERAL task-list-planner `AGENT.md` (a new agent folder under `backend/agents/prompts/`, added to the composer pool) whose body guarantees `## Task N:` headings and mandates "your SOLE output is the task plan." NO engine change; it is a prompt fragment that SEEDS an inserted producer node (never retrofitted onto a chained agent — D2). NOTE: `prototype-plan` wraps its tasks in a `<tasks>…</tasks>` block AND uses `## Task N:` inside — for a GENERIC producer prefer top-level `## Task N:` headings as the sole output (the fixture pattern), since `heading_tasks` scans the whole output.

---

### 8. Offline composed-fan-out characterization — NEW test (event-driven)

**Analog: `backend/tests/agents/test_sc001_fanout.py`** (VERIFIED, 450 lines) — mirror its structure EXACTLY:
- Monkeypatch seam: patch `engine_mod.compile_for_run` / `resolve_alias` / `registry_mod.get_pipeline_agents` / `factory_mod.create_runner` (+ `engine_mod.create_runner`) and restore in `finally` (`:214-320`).
- Scripted model: a `ScriptedFakeChatModel` subclass whose worker turn emits a `write_file` tool-call for the part named in its injected `=== CURRENT TASK ===` block (`:89-154`); planner turn emits the 3-task `## Task N:` plan (`:79-86`, `:192-193`).
- Neutralize planner/store/gate: `engine._run_planner`, `engine._store.store`, `engine._run_review_gate` replaced with no-ops (`:276-290`).
- Drive via `engine.execute(agents=…, pipeline_type=…, gate_agent_ids=[])` and collect events (`:296-304`).
- Probe: patch `KernelServices.record_subagent_run` to record every worker (`:251-262`).
- Assertions: N `subagent_spawned` + N `subagent_result` with `status == "complete"` (`:339-348`); distinct files in the sandbox base + no `merge_conflict` (`:350-363`); deliverable bundle contains the produced files (`:376-380`).
- SC-001 grep: `grep -rl <workflow-name> backend/agents/execution_engine/` returns "" (`:408-430`).

**Pattern DIVERGENCE for THIS phase (§6b):** unlike `test_sc001_fanout` (file-manifest driven), build a **COMPOSED / selections-driven** fan-out — pass `selections={ "<worker>": { "strategy": "fanout_batch", "task_source": { "kind": "parsed", "parser": "heading_tasks", "source_step": "<producer>" } } }` into `engine.execute(...)` and assert the crux carried the levers at BOTH the in-plan and absent-agent sites. Reuse the `shared_read` harness caveat (isolated per-worker writes are a live-Bedrock concern; Register line 1162). Assert the benign hook delta (default `audit_logger`/`secret_scan` on the trust-compiled absent step) as intended behavior, not a regression (Risk #6).

---

## Shared Patterns

### Generic keying (INV-1 / SC-001)
**Source:** `engine._apply_selections` (`:6248-6249` keys by `step.agent_id`) + `selections._synthesize_step` (keys by `agent_id`).
**Apply to:** every backend edit — the overlay, the synthesizer strategy line, and the D9 guard must key on `agent_id` + generic lever keys ONLY. The banned-pattern grep (`test_banned_patterns.py`) and the characterization's `grep -rl` must stay 0.

### INV-3 short-circuit (byte/event-identical goldens)
**Source:** `has_selections` gate at `engine.py:6213` (`return compiled` when empty).
**Apply to:** the overlay signature change — the empty/None path must return `(compiled, {})` and both consumption sites must behave identically to today. Re-run the 5 characterization goldens with `SNAPSHOT_UPDATE` unset.

### Shared lever reducer (no forked FE logic)
**Source:** `applyLeverPatch` (`AgentsPopup.tsx:1452-1474`) — the SINGLE writer, consumed by BOTH `CanvasConfigRail.patch()` and `AdvancedExpander.updateLever`.
**Apply to:** both FE surfaces write fan-out via this reducer; no new reducer.

---

## Confirmations (read-verified this session)

- **`fanout_batch` strategy `user_allowed=True`** — `fanout_batch.py:38`. VERIFIED.
- **`heading_tasks` parser `user_allowed=True`** — `heading_tasks.py:92`. VERIFIED. **`json_tasks` `user_allowed=True`** — `json_tasks.py:56`. VERIFIED (kept out of v1 UI per scope fence).
- **Default parser = `heading_tasks`** — `fanout_batch.py:32` `_DEFAULT_PARSER = "heading_tasks"`. VERIFIED.
- **`run_fanout` performs NO `spawn_subagents` permission check on the declarative path** — scanned `fanout.py:251-330`; the only raises are cancel (`_check_cancel`), budget `reserve` (BudgetExceeded), and worker-selection rejection — NO permission/`spawn_subagents`/`has_permission` check. VERIFIED. → **no security/trust flag flip needed** (D3 confirmed).

---

## No Analog Found

None. Every change site has an exact in-repo analog (mostly self-referential extensions of existing patterns).

---

## Metadata

**Line/path drift corrected vs. scope (written 2026-07-19/20):**
1. **Compiler path** — scope/CONTEXT canonical-refs + task cite `backend/agents/execution_engine/compiler.py`; ACTUAL is **`backend/agents/workflows/compiler.py`**. All cited line numbers (`:68`, `:95`, `:436-457`) are correct against the real file.
2. **FE composer directory** — scope cites `frontend/src/components/composer/`; ACTUAL is **`frontend/src/components/workflow/composer/`** (both `CanvasView.tsx` and `CanvasConfigRail.tsx`). `AgentsPopup.tsx` is at `frontend/src/components/workflow/AgentsPopup.tsx` (as cited). All cited line numbers correct.
3. **CanvasView selected-index local** — scope says `selectedIndex`; the actual local is **`selIndex`** (`:84-87`); `slice(0, selIndex)` is the correct call.

**All other cited line ranges matched exactly:** engine.py `:1463`, `:1701-1714`, `:2285-2292`, `:6194`, `:6213-6214`, `:6222`, `:6245`, `:6257-6272`, `:6274`; selections.py `:78-133`/`:86`/`:95`/`:128-131`; compiler.py `:68`/`:95-97`/`:436-457`; CanvasConfigRail `:36-49`/`:77-80`/`:82-112`/`:141`/`:270`; AgentsPopup `:1419-1425`/`:1452-1474`/`:1547`/`:1578`/`:1621`/`:1666`.

**Files scanned:** engine.py, selections.py, compiler.py, fanout_batch.py, heading_tasks.py, json_tasks.py, fanout.py, CanvasConfigRail.tsx, CanvasView.tsx, AgentsPopup.tsx, sample_fanout/workflow.yaml, test_sc001_fanout.py, sample-fanout-plan/AGENT.md, prototype-plan/AGENT.md.
**Pattern extraction date:** 2026-07-20.
