# Phase 51: User-Composable Fan-Out in the Composer (Path B) - Context

**Gathered:** 2026-07-20
**Status:** Ready for planning
**Source:** ADR/Scope Ingest Express Path (`.planning/PATH-B-FANOUT-COMPOSER-SCOPE.md`) — synthesized by the orchestrator because the scope doc is a narrative implementation plan (the ADR auto-parser extracts zero `## Decision` blocks from it); the locked decisions below are lifted verbatim-in-substance from that doc, every file:line re-verified against current `feat/ui-2`.

<domain>
## Phase Boundary

Expose the engine's **already-working** fan-out capability (kernel `run_fanout` + the `fanout_batch`/`wave_scheduler` strategies + `heading_tasks`/`json_tasks` parsers + budget + merge — all shipped in Phase 11) to **users composing custom workflows in the builder**, as a per-step **"fan out over a list"** toggle. The compiler, kernel, budget, and merge already function; the gap is purely that a user-composed fan-out **selection never reaches the run plan**. Closing it is four small, mechanical changes plus one content item — **no new engine power** (no security/trust flag flip, no new capability kind, no migration).

**In scope (v1):**
- The runtime overlay fix so a composed fan-out actually runs (the crux).
- The synthesizer emitting the chosen strategy.
- The two composer FE surfaces gaining a fan-out toggle + a dedicated-producer source picker.
- One generic task-list-planner producer skill (content) for domain-general fan-out.
- An additive compile-time `source_step`-must-be-upstream guard.
- Tests: unit + one offline composed-fan-out characterization + FE vitest; plus the orchestrator-owned live-Bedrock proof.

**Not a workflow-name feature (INV-1/SC-001):** every change keys on generic `agent_id` + generic lever keys (`strategy`/`fanout`/`task_source`); no workflow/agent-name literal enters the kernel.
</domain>

<decisions>
## Implementation Decisions (LOCKED — do not re-litigate)

### D1 — Path B, not the task-tool hack
Fan-out is exposed as a **user-composed composer control**, NOT by un-excluding the `task` sub-agent tool. Un-excluding it forfeits determinism/goldens/cost-bounds/isolation/security and violates INV-7/INV-13 — the architecture refuses it (see `.planning/FANOUT-USER-FACING-SCOPE.md`). The declarative `run_fanout` path is the only spawn path.

### D2 — Producer model = INSERT-A-NODE (the conceptual keystone, scope §0)
Fan-out is a change to the workflow's **SHAPE**, not an attribute of an agent: a **producer** node emits a `## Task N:` list, and a **fanned worker** node runs one copy per task. The engine reads the list and owns spawn/isolation/merge (the LLM never decides control flow).
- The producer is a **NEW, dedicated node you INSERT** — you do **NOT** retrofit a "producer skill" onto an agent already in a chain. A mid-chain agent has an OUTPUT CONTRACT (its output is the named input its downstream consumer reads); rewriting it to emit a task list **breaks the chain**.
- A producer must be a **dedicated list-emitter** (`heading_tasks.parse` scans the WHOLE output for `## Task N:` and slices on `##`, so mixed output tangles). The `<tasks>` side-channel is NOT clean with the current parser and is **out of scope for v1**.
- The "fan-out producer skill" is a **curated prompt fragment** (an `inject`/`AGENT.md` fragment, NOT a new engine capability kind) that SEEDS a producer node.

### D3 — The runtime overlay crux (scope §1) — make-or-break
`engine._apply_selections` (`engine.py:6257-6272`) today overlays only `validators`/`gates`/`model`/`retry`/`injects` and **DROPS `strategy`/`fanout`/`task_source`**. Fix:
- Add per-lever guarded patch lines carrying `strategy`, `fanout`, `task_source` (and optionally `on_conflict`) — each fires ONLY when the user selected it, so the empty-selections path stays byte-identical (INV-3).
- Do **NOT** overlay `tools` — the declarative `fanout_batch` path needs no `spawn_subagents` grant (`run_fanout`/`fanout.py:251-326` performs no permission check); under `trust="user"` the user step's `tools.spawn_subagents` is forced OFF anyway.
- **Cover the absent-agent synthesis site** (`engine.py:2285-2292`) — the COMMON case for `custom` because `allowed_custom_agent_ids("custom")` unions ALL non-revision base-pipeline agents (its docstring is stale — correct it while in the file). Thread the run's agent ids into `_apply_selections`, widen its trust-compile synth set to cover every run agent, and return the trust-compiled user-step map; the synthesis site consults that map before falling back to a bare `single_shot` step. Do NOT add steps to `compiled.steps` (the membership assertion at `engine.py:1701-1714` would raise). The single live caller is `engine.py:1463` (`resume_run` does NOT call it — WR-02 "resume drops selections" is a known, separately-tracked limitation).
- **INV-3 parity:** when `selections` is None/empty, `has_selections` short-circuits (`engine.py:6213`), the user-step map is `{}`, and both sites behave byte-identically to today. One deliberate benign delta: a composed absent agent that carries selections now runs its trust-compiled step (carrying the compiler's default `audit_logger`/`secret_scan` hooks a bare `_Step` lacked) — non-blocking; assert it in the test rather than treat it as a regression.

### D4 — Schema / data path (scope §2) — RESOLVED
`source_step` and `parser` live in the step's **`task_source`** block (`TaskSource`, `plan.py:162-184`: `{kind, parser, target, source_step, spec_step}`), **NOT** in `FanoutSpec` (`plan.py:196-216`: `{mode, max_parallel, agent, count, workers, merge_agent}`). The compiler already compiles both (`compiler.py:436-457` for `task_source` incl. trust-checking `parser`; `compiler.py:539/593` for `fanout`) — **no compiler change needed** for the schema. Minimal viable `StepSelection` = `{ "strategy": "fanout_batch", "task_source": { "kind": "parsed", "parser": "heading_tasks", "source_step": "<prev>" } }`; `fanout` is optional (kernel fans one worker per parsed task at default concurrency).

### D5 — Synthesizer (scope §3)
`selections._synthesize_step` (`selections.py:78-133`) hardcodes `strategy: single_shot` at line 86. The ONLY change: after the `isinstance(sel, dict)` guard (~line 95), emit `step["strategy"] = sel["strategy"]` when the selection carries a non-empty string strategy — GENERIC, no name literal. `fanout`/`task_source` already ride the existing projection loop (`selections.py:128-131`). The throwaway trust-check manifest compiles under `trust="user"` at both chokepoints (SAVE: `user_workflows.py:150-208`; LAUNCH: `run_commands.py:1535-1539`) because `fanout_batch`/`heading_tasks`/`json_tasks` are all `user_allowed=True`.

### D6 — Frontend controls (scope §4)
- `StepSelection` (`AgentsPopup.tsx:1419-1425`) gains `strategy?: "fanout_batch"`, `task_source?`, `fanout?`. `applyLeverPatch` (`:1452-1475`) is generic — no reducer change (toggling ON writes `{strategy, task_source}`; OFF clears them).
- **Canvas rail** (`CanvasConfigRail.tsx`): add a "Fan out over a list" `Toggle` (reuse `:82-112`) + a follow-up "Source list from" `<select>`. Thread `priorAgents={pipelineAgents.slice(0, selIndex)}` from `CanvasView.tsx:270` (owner of `pipelineAgents` at `:43`; the selected-index local is `selIndex` at `:85`, NOT `selectedIndex`). Disable the toggle for the first agent.
- **Simple-view Advanced expander** (`AgentsPopup.tsx` `AdvancedExpander` :1547): same toggle + source picker per agent row via `updateLever`; source options = `agents.slice(0, idx)`.
- **Parser default = `heading_tasks`** (matches `fanout_batch.py:32`); do NOT expose `json_tasks` in v1.
- **Merge = engine-default; NO merge picker** (INV-7 — engine picks merge by isolation scope, `fanout.py:785-793`; leave `merge_agent` unset → `on_conflict: human_gate`).
- **`max_parallel`** omitted from v1 UI (redundant with the kernel cap `min(declared, DEFAULT_MAX_CONCURRENCY=4)`).

### D7 — Producer sourcing = reuse-or-INSERT (scope §4e, governed by D2)
The source control is NOT "pick any earlier agent". It offers: **Reuse** an upstream node ONLY if it is a known `## Task N:` producer (v1 allow-list: **`prototype-plan`**; grows as producer skills ship) — the `<select>` lists only known-producer earlier agents; or **Insert a producer** (default primary action) — inserts a NEW producer node seeded from the generic producer skill (P0) and auto-wires it as `source_step`. Never point `source_step` at a non-producer chained agent.

### D8 — Content: one generic producer skill (P0, scope §0/§4e)
The verified 63-agent composer pool (`allowed_custom_agent_ids("custom")`) DOES contain a real `## Task N:` producer — `prototype-plan` — but it is prototype-domain-specific. **P0 = ship ONE generic task-list-planner producer skill** (an analog of `sample-fanout-plan`/`prototype-plan`, a curated `AGENT.md`/inject). Small content, no machinery. A prototype-domain demo/minimal slice can ship WITHOUT P0 (fan out over `prototype-plan`); GENERAL fan-out needs P0.

### D9 — Guardrails (scope §5)
- **Additive compile-time guard (INV-5-safe, pure data):** when `strategy == "fanout_batch"` and `task_source.source_step` is set, raise `CompilerError` if `source_step` is not the id of an EARLIER compiled step. Passes for `sample_fanout`/`sample_wave`; keep it name-free.
- **FE guardrails:** source picker offers only earlier agents; toggle disabled for the first agent (hint); non-blocking warning on an unknown producer. Runtime degrades safely (`fanout_batch.py:96-109`) when a source emits no headings.

### D10 — Build order (scope §7)
1. **P2 synthesizer** (`selections.py`) — isolated, unit-testable immediately.
2. **P1 overlay + absent-case** (`engine.py`) — the crux; prove with an engine unit test + the offline composed-fan-out characterization (§6b) **BEFORE any FE work** (de-risks the whole feature).
3. **P3 + P4 FE controls** (now the backend honors what they persist).
4. **P5 validation guardrails.**
5. **P6 remaining tests + orchestrator live proof.**
**Minimal-first slice** = P1 + P2 + minimal P3/P4 (single toggle, source defaults to the immediately-preceding step, `heading_tasks` fixed, engine-default merge, no advanced knobs) — fully functional end-to-end.

### Claude's Discretion
- Exact wave grouping / plan splitting (respecting the build order above and file-ownership serialization: `engine.py` P1, `selections.py` P2, FE files P3/P4).
- The generic producer skill's exact prompt wording (must guarantee `## Task N:` headings and "your SOLE output is the task plan").
- Test file names and fixture shapes (mirror `test_sc001_fanout.py` for the characterization).
- The `<threat_model>` block content (small surface — declarative-only, no `spawn_subagents` grant; the security gate still requires the block).
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Plan of record (read first, fully)
- `.planning/PATH-B-FANOUT-COMPOSER-SCOPE.md` — the implementation-ready Path B plan (every file:line, build order, tests, minimal-first). THE source of truth.
- `.planning/FANOUT-USER-FACING-SCOPE.md` — the two-path no-hacks investigation (why Path B, not the task hack).
- `.planning/IMPLEMENTATION-REGISTER.md` — read to EOF before editing (locked decisions; avoid duplicate/contradicting code).

### Backend — the crux
- `backend/agents/execution_engine/engine.py` — `_apply_selections` (`:6194-6274`, patch block `:6257-6272`), the absent-agent synthesis site (`:2245-2292`), the single caller (`:1463`), the membership assertion (`:1701-1714`).
- `backend/agents/workflows/selections.py` — `_synthesize_step` (`:78-133`, hardcoded strategy `:86`, projection loop `:128-131`), `synthesize_manifest` (`:136-181`), `has_selections` (`:218-227`).
- `backend/agents/workflows/plan.py` — `TaskSource` (`:162-184`), `FanoutSpec` (`:196-216`), `Step`.

### Backend — schema / compile / runtime (mostly read-only; the only backend edit here is the D9 guard)
- `backend/agents/workflows/compiler.py` — `_ALLOWED_STEP_KEYS` (`:68-88`), `_ALLOWED_TASK_SOURCE_KEYS` (`:95-97`), `task_source` compile (`:436-457`), `fanout` compile (`:539/593`), trust check (`:480-499`), default hooks (`:406`). The D9 `source_step`-upstream guard lands here. **(PATH CORRECTED 2026-07-20 vs. scope — the engine imports `from agents.workflows.compiler import WorkflowCompiler`; there is NO `execution_engine/compiler.py`.)**
- `backend/agents/capabilities/strategies/fanout_batch.py` — parser default (`:32`), `user_allowed` (`:38`), reads `task_source.source_step`/`parser` (`:75-85`), degrade path (`:96-109`).
- `backend/agents/capabilities/task_parsers/heading_tasks.py` — whole-output `## Task N:` scan (`:39`), block slicing (`:66-68`), `user_allowed` (`:92`).
- `backend/agents/execution_engine/fanout.py` — `run_fanout`, merge selection by isolation (`:785-793`), concurrency cap (`:170-179`).
- `backend/app/api/composition_order.py` + `backend/agents/workflows/resolver.py` — `presort` (producer-first, deterministic from input order; `resolver.py:192`).
- `backend/app/api/run_commands.py` — LAUNCH trust re-validate (`:1535-1539`), unsatisfiable → 422 (`:1481`).
- `backend/agents/workflows/user_workflows.py` — SAVE trust compile (`:150-208`).
- `backend/agents/workflows/sample_fanout/workflow.yaml` — the shipped `sample-fanout-plan` producer (`:49`); a passing reference for the D9 guard.
- `agents/prompts/prototype-plan/AGENT.md` — the existing `## Task N:` producer (the v1 allow-list reuse target).

### Frontend
- `frontend/src/components/workflow/AgentsPopup.tsx` — `StepSelection` (`:1419-1425`), `applyLeverPatch` (`:1452-1475`), `AdvancedExpander` (`:1547`, rows `:1621`, `updateLever` `:1578/:1666`).
- `frontend/src/components/workflow/composer/CanvasConfigRail.tsx` — props (`:36-49`), `Toggle` (`:82-112`), existing lever `patch(...)` (`:141/173/193/212`).
- `frontend/src/components/workflow/composer/CanvasView.tsx` — `pipelineAgents` (`:43`), rail render (`:270`).

### Tests to mirror / extend
- `backend/tests/agents/test_sc001_fanout.py` — mirror for the offline composed-fan-out characterization.
- `backend/tests/unit/test_user_workflows_selections.py` — extend for the synthesizer.
- `backend/tests/agents/test_compiler.py` / `test_compiler_trust.py` — the D9 guard + trust-compile of a fan-out step.
- `frontend/src/components/**` vitest — `AdvancedExpander.test.tsx`, a new `CanvasConfigRail.test.tsx`, `CanvasView.test.tsx`, `IdeaInputPage.selections.test.tsx`.
- The 5 characterization goldens (`backend/tests/agents/test_characterization_*.py`) — MUST stay byte/event-identical (`SNAPSHOT_UPDATE` unset).
</canonical_refs>

<specifics>
## Specific Ideas

- **Exact `StepSelection` persisted shape:** `{ "strategy": "fanout_batch", "task_source": { "kind": "parsed", "parser": "heading_tasks", "source_step": "<upstream_agent_id>" }, "fanout": { "mode": "parallel", "max_parallel": 4 } }` (`fanout` optional).
- **Exact `_apply_selections` patch additions** (scope §1b) — three guarded lines carrying `strategy`/`fanout`/`task_source`; do NOT overlay `tools`.
- **Exact synthesizer insert** (scope §3) — `if isinstance(sel.get("strategy"), str) and sel["strategy"]: step["strategy"] = sel["strategy"]`.
- **Offline characterization** — build a COMPOSED (selections-driven, not file-manifest) fan-out: producer emits a 3-task `## Task N:` list + consumer step whose selection sets `strategy: fanout_batch` + `task_source.source_step = producer`; assert 3 `subagent_spawned`/`subagent_result` + a merged deliverable + `grep -rc <workflow-name> agents/execution_engine/ == 0`. Reuse the `shared_read` harness caveat (Register line 1162: isolated per-worker writes are a live-Bedrock concern).
- **Live proof (orchestrator)** — compose `producer (## Task 1..N:) → worker (fan-out ON, source=producer)`, save, launch on Bedrock; observe N parallel `subagent_spawned` (≤4 concurrent) + per-worker `subagent_result` + merged deliverable + NO `spawn_subagents` grant; contrast a fan-out-OFF control.
</specifics>

<scope_fence>
## Scope Fence — OUT of scope for v1

- `json_tasks` parser exposure in the UI (heading_tasks only; json_tasks stays a future "advanced" option).
- `merge_agent` / `on_conflict` pickers (engine default `human_gate`; merge engine-selected — INV-7).
- `max_parallel` UI field (kernel caps at 4 anyway).
- `<tasks>` side-channel producers (would need a `heading_tasks` parser change; a chained agent doing two jobs).
- Retrofitting a "producer skill" onto an already-chained agent (D2 forbids — breaks its output contract).
- Resume of a composed fan-out run (WR-02: selections are dropped on resume today — a known, separately-tracked limitation; note it, do not fix here).
- The `task` sub-agent tool self-spawn path (D1 — refused).
- Any security/trust flag flip, new capability kind, or DB migration.
</scope_fence>

<deferred>
## Deferred Ideas

- `json_tasks` exposure, merge-agent/on_conflict knobs, `max_parallel` UI — post-v1 "advanced" knobs.
- Robust `<tasks>` side-channel producer (parser change to read only the delimited block).
- Fixing composed-fan-out resume (WR-02).
</deferred>

## Success Criteria (what must be TRUE — mirrors ROADMAP Phase 51)

1. A user-composed step with fan-out ENABLED spawns N workers at runtime — proven by an OFFLINE composed-fan-out characterization test (mirrors `test_sc001_fanout.py`): N `subagent_spawned`/`subagent_result` + merged deliverable; the crux carries `strategy`/`fanout`/`task_source` at BOTH the in-plan and absent-agent sites; keyed generically (INV-1/SC-001; banned-pattern grep 0).
2. The composer persists + threads the fan-out selection through SAVE (`trust="user"`) and LAUNCH on BOTH surfaces, and OMITS it when empty (INV-3 short-circuit).
3. Producer model honored (INSERT-A-NODE): fan-out wires `source_step` to a dedicated producer; reuse only for a known `## Task N:` producer; generic producer skill ships (P0); FE disables the toggle on the first agent + warns on an unknown producer.
4. Additive INV-5-safe compile guard rejects a non-upstream `source_step` (passes `sample_fanout`); NO security/trust flip, NO new capability kind, NO migration.
5. Invariants green: 5 goldens byte/event-identical (INV-3); import-linter 4/0; kernel still owns spawn/isolation/merge (INV-7/INV-12); merge engine-selected (no picker).
6. Live-Bedrock proof (orchestrator-owned): builder-composed `producer → fanned worker` shows ≤4 concurrent parallel workers + per-worker results + merged deliverable + no `spawn_subagents` grant; contrasted with a fan-out-OFF control.

## Risk Summary (scope §8 — flag for the orchestrator live pass)

1. Generic producer content (P0) is the one content prereq for GENERAL fan-out; `prototype-plan` covers the prototype domain for a minimal demo.
2. `task_source.source_step` ordering is not a DAG edge — relies on `presort` determinism + the D9 additive guard; verify with a producer that also participates in a produces/consumes chain.
3. Offline harness (`shared_read`) cannot prove per-worker isolation/merge — the live proof is the real evidence.
4. `_apply_selections` return-signature change touches its single caller (`engine.py:1463`); confirm no new caller since; composed-fan-out resume loses the overlay (WR-02, documented).
5. `allowed_custom_agent_ids("custom")` docstring is stale — correct it while in the file.
6. Benign hook delta on absent composed agents — assert intended behavior in the engine unit test.

---

*Phase: 51-user-composable-fan-out-in-the-composer-path-b*
*Context synthesized 2026-07-20 via Scope Ingest Express Path (orchestrator-authored from `.planning/PATH-B-FANOUT-COMPOSER-SCOPE.md`).*
