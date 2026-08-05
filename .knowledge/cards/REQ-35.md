---
id: REQ-35
type: req
status: done
area: [workflow, agents]
summary: >-
  User-Composable Fan-Out in the Composer (Phase 51 [PB])
source: .planning/REQUIREMENTS.md#user-composable-fan-out-in-the-composer-phase-51
---

### User-Composable Fan-Out in the Composer (Phase 51 [PB])

- [ ] **FANOUT-01**: The builder exposes a per-step "fan out over a list" toggle on BOTH composer surfaces (canvas `CanvasConfigRail`, simple-view `AdvancedExpander`); enabling it persists `{strategy:"fanout_batch", task_source:{kind:"parsed", parser:"heading_tasks", source_step:<upstream>}}` (optional `fanout:{mode,max_parallel}`) into `workflows.manifest_json` on SAVE and the `selections` LAUNCH payload; toggling OFF clears the levers; empty selections are omitted so the plan stays byte-identical (INV-3). (scope §4a–c, §6c)
- [ ] **FANOUT-02** *(the crux)*: `engine._apply_selections` carries `strategy`/`fanout`/`task_source` onto the run-plan step (each lever guarded on the user having selected it, so the empty-selections path stays byte-identical), AND the absent-from-base-manifest synthesis site (`engine.py:2285-2292`, the COMMON case for `custom`) consults the trust-compiled user-step map so a composed agent's fan-out reaches the run; `_apply_selections` returns the user-step map and its single live caller (`engine.py:1463`) threads the run's agent ids. Nothing fans out without this. (scope §1)
- [ ] **FANOUT-03**: `selections._synthesize_step` emits the user-selected `strategy` (overriding the safe `single_shot` default at `selections.py:86`) GENERICALLY — no workflow/agent-name literal (INV-1/SC-001); `fanout`/`task_source` ride the existing projection loop; the throwaway trust-check manifest compiles under `trust="user"` at BOTH the SAVE and LAUNCH chokepoints. (scope §3)
- [ ] **FANOUT-04**: Fan-out sourcing follows the INSERT-A-NODE producer model — enabling fan-out wires `task_source.source_step` to a DEDICATED `## Task N:` producer node, reusing an existing node ONLY when it is a known producer (v1 allow-list: `prototype-plan`) and otherwise INSERTING one; a chained agent's output contract is never rewritten; a single generic task-list-planner producer skill (a curated `AGENT.md`/inject fragment, NOT a new engine capability kind — work-item P0) ships and is surfaced by the composer's "Insert a producer" action. (scope §0, §4e)
- [ ] **FANOUT-05**: An additive, INV-5-safe compile-time guard rejects a `fanout_batch` step whose `task_source.source_step` is not an EARLIER compiled step (passes for `sample_fanout`/`sample_wave`); the FE source picker offers only earlier agents, disables the toggle for the first agent (with a hint), and warns on an unknown producer; the runtime degrades safely (`fanout_batch.py:96-109`) when a source emits no `## Task N:` headings. (scope §5a/§5b)
- [ ] **FANOUT-06**: No new engine power — no security/trust flag flip, no new capability kind, no migration (every capability used — `fanout_batch`, `heading_tasks`, `FanoutSpec`, `TaskSource` — is already registered + `user_allowed=True`); invariants hold: INV-1/SC-001 (kernel stays name-free; banned-pattern grep 0), INV-3 (5 characterization goldens byte/event-identical), INV-5 (no DSL — the guard is a pure-data check), INV-7/INV-12 (kernel owns spawn/isolation/merge/concurrency/budget; no second spawn path; merge engine-selected — no merge picker exposed), import-linter 4/0. (scope §5c)
- [ ] **FANOUT-07**: Proof — OFFLINE a selections-driven composed fan-out characterization test (mirrors `tests/agents/test_sc001_fanout.py`) asserts N `subagent_spawned`/`subagent_result` events + a merged deliverable + SC-001 grep 0; unit tests cover the overlay (in-plan + absent-agent + empty-selections byte-identity), the synthesizer, and the compile guard; FE vitest covers the toggle/source-picker/persist. LIVE (orchestrator-owned) a builder-composed `producer → fanned worker` on Bedrock shows ≤4 concurrent parallel workers + per-worker results + a merged deliverable + NO `spawn_subagents` grant. (scope §6)

## v2 Requirements

Deferred to a future milestone; tracked but not in this roadmap.
