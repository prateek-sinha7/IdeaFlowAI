# Phase 8: Capabilities Hardened — Registry, Gates, Tool Perms, Runtime [3] - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-09
**Phase:** 8-capabilities-hardened-registry-gates-tool-perms-runtime-3
**Areas discussed:** Gray-area selection (4 HOW forks presented) — dismissed → "lock all to plan-faithful recommendations"

---

## Gray-area selection (single multiSelect turn)

SPEC.md had already locked the 29-ID WHAT (ambiguity 0.15) + three boundaries (frontend = backend + data-bearing panels; validator/gate depth = real plan-faithful; parity = strict INV-3), so discussion was HOW-only. Four implementation forks were presented for optional deep-dive:

| Option | Description (recommendation embedded) | Selected |
|--------|----------------------------------------|----------|
| Validator↔heavy-dep architecture | static_check/render_check have Chromium/stdlib deps; kernel can't import app.*. Rec: Validator impls in `app/agents/validators/` (import port + heavy checks) self-register; task_loop reaches via registry + KernelServices handle. | |
| Validation ownership: gate vs strategy | Rec: generic FixPolicy fix-loop replaces `run_validation_fix_loop` internals (behavior-identical, config-driven), stays where task_loop invokes it; `validation` gate is the declared step-boundary mechanism for `gates:[validation]`; existing build-loop validation at INV-3 parity, declarative gates additive. | |
| Self-registration & discovery | Rec (§32): `@register(kind,name)` + `discover()` explicit-subpackage-import, deletes Phase-7 `install()` (move-don't-copy); no pkgutil walk. | |
| F1–F5 deletion sequencing + plan spine | Rec (strangler, mirrors Phase-7 D-05): 08-01 registry+trust → gates/tool-perms/validators register in → factory deletions (F1/F3/F4 together, F2, F5) → hooks → API/frontend; each F# wrapped→rewired→deleted in-plan. | |

**User's choice:** Dismissed the question (no selection) → interpreted as **"lock all to plan-faithful recommendations"**, consistent with the documented project pattern (Phases 1/2/4/5/6/7 all chose lock-all) and the standing init directive *"everything from plan.md must be honored — nothing dropped."* All four recommendations above + the supporting decisions they imply were locked as D-01…D-12 in CONTEXT.md.

**Notes:** No re-ask performed — the dismissal-as-lock-all behavior is established and documented (07-CONTEXT.md: *"gray-area question dismissed — user chose 'lock all to recommendations', mirroring Phases 1/2/4/5/6"*). Every locked decision is grounded in `specs/003-workflow-engine-decoupling/plan.md` (§6–§9, §16, §18, §22, §30, §32) and the Phase-7 evolution framing.

---

## Claude's Discretion

Captured in CONTEXT.md `### Claude's Discretion`. Mechanical sub-choices left open: `@register` signature + `_KNOWN` population; `discover()` invocation point + `app`-side validator registration; whether the `validation` gate subsumes the Phase-7 `revision_validation` post_step; `PromptAssemblyPolicy` shape; single vs per-table `0016` migration; Tier#4/5/6 validator placement (app vs capabilities); frontend panel composition (extend vs new); plan-task granularity within the 8-plan frame.

## Deferred Ideas

Captured in CONTEXT.md `<deferred>`. Highlights: MCP client + catalog (P9/N13 — only the `mcp` slot lands); integration providers (P9 — only `integrations` slot); RuntimeEnvironment/Workspace + repo workflows (P9); constrained exec (P10/N3 — security gate registered + default-denies); fan-out (P11 — `spawn_subagents` slot only); subagent/wave/diff frontend viewers (P9/11/12); prompt-content changes (Q37 — separate PR; only R12 bug fix lands); `claude_code_cli`/`custom_runner` adapters. **Folded:** the Phase-7 test-isolation pollution (test_strategies global-registry mutation → autouse reset fixture) into the 08-01 registry work. **Triage-only (not locked):** WR-02/03/05 from 07-REVIEW.md.
