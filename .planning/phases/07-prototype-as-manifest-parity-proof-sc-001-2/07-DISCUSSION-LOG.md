# Phase 7: Prototype as Manifest — Parity Proof (SC-001) [2] - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-08
**Phase:** 7-prototype-as-manifest-parity-proof-sc-001-2
**Areas discussed:** Discuss mode (meta) — all 5 HOW forks locked to plan-grounded recommendations

---

## Discuss Mode (meta-decision)

The WHAT is locked by `07-SPEC.md` (11 requirements, ambiguity 0.08). Five HOW forks were
identified and presented WITH plan.md-grounded recommendations (§10/§11/§30/§31/§32):
A. Capability module layout · B. Name→impl resolution seam · C. `task_loop`↔kernel coupling ·
D. `opendesign` re-homing · E. Plan sequencing.

| Option | Description | Selected |
|--------|-------------|----------|
| Lock all to recommendations | Mirror Phases 1/2/4/5/6: write CONTEXT.md with all 5 forks locked to the plan-grounded recommendations + implied mechanical decisions + researcher directives | ✓ |
| Discuss specific areas | Drill into one or more forks (most likely C, the deepest) before locking the rest | |

**User's choice:** Lock all to recommendations.
**Notes:** Consistent with the standing directive ("honor plan.md, nothing dropped") and the
established working pattern across Phases 1/2/4/5/6. The five forks and their locked
recommendations are recorded as D-01..D-05 in CONTEXT.md.

---

## HOW forks presented (for audit — all locked to recommendation)

| # | Fork | Locked recommendation (CONTEXT D-0x) | Grounding |
|---|------|--------------------------------------|-----------|
| A | Capability module layout | §32 subpackage tree (`capabilities/{strategies,deliverables,context_providers,task_parsers,compaction}/`); heavy-dep validators stay in `app/agents/` | plan §32 |
| B | Name→impl resolution seam | Extend `CapabilityRegistry` with `(kind,name)→impl` + `resolve()`, explicit startup registration (module singleton); `@register`/`discover()` → Phase 8 | plan §7/§32; 04 D-07, 06 D-03 |
| C | `task_loop`↔kernel coupling | `ExecutionStrategy.run(step,ctx)` owns the loop; kernel run-primitive/sandbox exposed via a narrow runner handle on `ExecutionContext`; reclaim `current_task_block` into the strategy | plan §10/§11 (L11); Phase 2 D-02 |
| D | `opendesign` re-homing | Physically relocate `agents/prototype/context.py`'s 3 live fns into `capabilities/context_providers/opendesign.py` (move-don't-copy); rewire 4 importers; drop `agents/prototype/` | plan §11 (L12) / INV-12 |
| E | Plan sequencing | ROADMAP 07-01…05: build+register caps → route engine through them + prove parity → delete L1–L13 last | ROADMAP / plan §31 |

---

## Claude's Discretion

- Exact runner-handle name/shape on `ExecutionContext` (D-03).
- Where `install()` lives + whether `is_registered`/`resolve` share `_KNOWN` (D-02).
- Whether `od_context.py` is rewired in place or relocated (D-04).
- The exact kernel-scoping mechanism per L1–L13 grep gate (D-05).
- Plan-task granularity within the 5-plan frame; whether the resolution seam lands in 07-01 or a 07-00 scaffold.
- Whether the §32 `engine.py`→`kernel.py` rename happens this phase (cosmetic).
- Whether `previous_run`/`opendesign` share a provider base.

## Deferred Ideas

- Self-registration (`@register`/`discover()`) + trust flags — Phase 8 (CAP-01/02).
- Formal Validator registry + generic fix-loop + severity + Tier#4/5/6 + migrate `html_static`/`html_render` — Phase 8 (08-04).
- Formal GateHandler registry + real `Validation_Gate` — Phase 8 (08-02).
- `fanout_batch`/`wave_scheduler` strategies — Phases 11/12; `repo_diff`/`repo`/`uploaded_files`/`memory` — Phases 9+; `json_tasks`/`bracket_p` parsers — later.
- `engine.py`→`kernel.py` rename — cosmetic; planner's call.
- PromptAssemblyPolicy / AgentRuntimeAdapter / ToolPermissions / F1–F5 — Phase 8.
