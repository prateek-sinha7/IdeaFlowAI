# Phase 10: Safe Local Exec (gated on N3) [4B] - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-10
**Phase:** 10-safe-local-exec-gated-on-n3-4b
**Areas discussed:** Approval-gate wiring (1 of 4 offered; the other 3 went to Claude's discretion)

---

## Area selection

Offered gray areas (multiSelect): Exec profile home + provisioning · Approval-gate wiring · Validator placement + exec access · exec_runs audit seam.

**User's choice:** Approval-gate wiring only — the remaining three locked to Claude's recommendations in CONTEXT.md (Claude's Discretion section).

---

## Approval-gate wiring

### Q1 — How does an exec-granting step acquire the approval requirement?

| Option | Description | Selected |
|--------|-------------|----------|
| Manifest-declared + compiler-enforced | Exec steps MUST declare `gates: [security, approval]`; CompilerError if a step grants tools.exec without both. Explicit, INV-5-pure; SecurityGate double-checks (defense in depth) | ✓ |
| Compiler auto-injection | Compiler silently appends the gates — terser manifests but compiled plan ≠ authored manifest | |
| Kernel runtime check | Engine checks "grants exec & no approval recorded" — author-mistake-proof but plants exec-special-casing into the kernel | |

**User's choice:** Manifest-declared + compiler-enforced (recommended)

### Q2 — Pause/resume mechanics (the approval gate's wait_human currently halts/skips the step)

| Option | Description | Selected |
|--------|-------------|----------|
| Delegate to the review-gate HITL | Approval gate routes via ctx.runner to the _run_review_gate machinery (checkpointer-durable, WS-driven), resolving approve→pass / reject→block inline; ONE HITL mechanism (human-gate precedent) | ✓ |
| Keep halt + run-level resume | New API approve action + re-enter the step — but step-granular resume is Phase 12 and doesn't exist yet | |
| Pre-run approval | Collect at run start when the plan contains exec — approver decides blind; diverges from SPEC wording | |

**User's choice:** Delegate to the review-gate HITL (recommended)

### Q3 — First-exec memory ("subsequent exec steps don't re-prompt")

| Option | Description | Selected |
|--------|-------------|----------|
| Durable gate_events lookup | Query the run's gate_events for an approval-pass row → silently pass; durable across restarts, no new state, audit doubles as memory | ✓ |
| ExecutionContext flag | ectx.exec_approved — cheapest read but forgets on restart | |
| Both: flag + durable backstop | Marginal benefit for extra code | |

**User's choice:** Durable gate_events lookup (recommended)

### Q4 — What does the approver see in the approval payload?

| Option | Description | Selected |
|--------|-------------|----------|
| Exec policy snapshot | Step/agent id + allow-list + caps + scrubbed-env + egress-denied — informed sign-off on exactly what's unlocked; rides existing review_gate_*/gate_* event shapes | ✓ |
| Generic step info only | "Step X requests exec — approve?" — blind sign-off | |
| Full command preview | Exact argv isn't knowable at the gate (constructed dynamically); the allow-list is the honest bound | |

**User's choice:** Exec policy snapshot (recommended)

### Continue check

**User's choice:** Wrap up — write CONTEXT.md.

---

## Claude's Discretion

- **Exec profile home + provisioning** — profile constants in `app/agents/runtime/local.py` (never manifest-tunable); run-entry host seam provisions exec=True iff the compiled plan grants exec; plan.py `ExecutionPolicy.check` forward surface made live or deleted (INV-12).
- **Validator placement + exec access** — kernel-side `agents/capabilities/validators/`, exec via `target.runner` handle only.
- **exec_runs audit seam** — recorder callback injected at `create_workspace`; `LocalWorkspace.exec_command` records every invocation at the enforcement point (bypass-proof); `KernelServices.record_exec_run` backs it.
- Registry lockstep 50→53; exec_runs column details; plan split granularity.

## Deferred Ideas

- network_allow implementation + secrets enablement (later phase)
- OS-level egress enforcement (v2 ECS/containers)
- Ephemeral cred-vendor seam (with N4 push flows)
- Non-Python toolchains on the allow-list
- Dedicated frontend exec-approval panel (rides existing gate event shapes this phase)
