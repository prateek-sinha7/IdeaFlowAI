"""agents/capabilities/gates/approval.py — the ``approval`` gate (08-02 / 10-03 / §9).

Requires an explicit human sign-off before the FIRST exec step of a run proceeds
(N3: exec needs both ``security`` AND ``approval``, stricter than security-only).
This gate is the HITL tier — it DELEGATES to the ONE durable HITL mechanism (D-02):
``ctx.runner.run_human_gate`` → engine ``_run_review_gate`` (the checkpointer-backed
pause), exactly as the ``human`` gate does, but with an approval-flavored
policy-snapshot payload (D-04) and a durable first-exec short-circuit (D-03).

Three deltas from ``human.py``:
  1. **D-03 first-exec memory** — before delegating, query the run's
     ``gate_events`` (via ``ctx.runner.read_gate_events``) for a prior
     ``gate="approval"`` / ``outcome="pass"`` row. If present, the run already
     signed off this run's exec → silently PASS without re-pausing (no second
     ``review_gate_ready``). Durable across restarts (the table is persisted +
     owner/workspace-scoped), no new state field, no migration.
  2. **D-04 policy-snapshot payload** — the pause carries the exec policy snapshot
     (step/agent id, exec allow-list, resource caps, scrubbed-env note,
     egress-denied status) rather than an agent-output string. It rides the
     existing ``review_gate_ready.data.output`` field (the generic WS forward — no
     frontend rebuild) via the parameterized ``run_human_gate(step, payload=...)``.
  3. **offline / no handle** — when no ``run_human_gate`` handle is present, PAUSE
     for human (``wait_human``); NEVER auto-approve.

Registered ``user_allowed=False`` (D-01/D-02): approval is an engineer-declared
control, not a user-grantable palette capability.

Import purity (import-linter): registry decorator + outcome contract only; the
``gate_events`` write/read + the HITL delegate are reached through ``ctx.runner`` —
NO kernel/app import.
"""

from __future__ import annotations

from typing import Any

from agents.capabilities.gates.base import (
    GATE_BLOCK,
    GATE_PASS,
    GATE_WAIT_HUMAN,
    GateOutcome,
)
from agents.capabilities.gates.write import write_gate_event
from agents.capabilities.registry import register

# Engine-internal review-gate signal mapping to a block outcome (NOT surfaced as a
# gate event — it drives the outcome only). Kept in sync with engine._run_review_gate.
_REJECTED = "_gate_rejected"
_EDITED = "_gate_edited"


def _exec_policy_snapshot(step: Any, ctx: Any) -> dict:
    """Build the D-04 approval payload: the exec POLICY snapshot (no creds, no argv).

    Sourced from the bound ``ctx.runner.workspace.policy`` when available (the
    constrained profile the §15 host seam attached), else falls back to the step's
    declared tool grant. NEVER includes secrets or a dynamic argv preview — the
    allow-list IS the honest bound the approver evaluates (D-04 / T-10-03-06).
    """
    step_id = getattr(step, "agent_id", None) or "?"
    runner = getattr(ctx, "runner", None)
    workspace = getattr(runner, "workspace", None)
    policy = getattr(workspace, "policy", None)

    if policy is not None:
        allow_list = sorted(getattr(policy, "exec_allow", []) or [])
        caps = {
            "cpu_seconds": getattr(policy, "cpu_seconds", None),
            "mem_mb": getattr(policy, "mem_mb", None),
            "wall_seconds": getattr(policy, "wall_seconds", None),
        }
        # Egress is denied when the policy grants no network (the v1 posture).
        egress_denied = not bool(getattr(policy, "network", False))
    else:
        # No bound workspace at gate time — surface the step's declared grant so the
        # approver still sees what was requested (the seam binds the profile next).
        tools = getattr(step, "tools", None)
        allow_list = []
        caps = {"cpu_seconds": None, "mem_mb": None, "wall_seconds": None}
        egress_denied = not bool(getattr(tools, "network", False))

    return {
        "kind": "approval",
        "step": step_id,
        "agent_id": step_id,
        "exec_allow": allow_list,
        "caps": caps,
        "scrubbed_env": "host credentials scrubbed (PATH/HOME/TMPDIR only)",
        "egress_denied": egress_denied,
    }


@register("gate", "approval", user_allowed=False)
class ApprovalGate:
    """Explicit exec sign-off gate (``name='approval'``) delegating to the HITL machinery.

    Satisfies the ``GateHandler`` port structurally (``name`` + ``async evaluate``).
    """

    name = "approval"

    async def evaluate(self, step: Any, ctx: Any) -> GateOutcome:
        """First-exec pause (D-02/D-04); short-circuit on a prior approval (D-03)."""
        step_id = getattr(step, "agent_id", None) or "?"
        runner = getattr(ctx, "runner", None)

        # ── D-03: durable first-exec memory ────────────────────────────────────────
        # A prior approval-pass row this run → silent PASS (no re-prompt). The lookup
        # is best-effort: an offline handle returning [] simply means "no prior
        # approval", so we fall through to the delegate (correct first-exec behavior).
        read = getattr(runner, "read_gate_events", None)
        if read is not None:
            rows = await read(getattr(runner, "run_id", "")) or []
            if any(
                getattr(r, "gate", None) == "approval"
                and getattr(r, "outcome", None) == GATE_PASS
                for r in rows
            ):
                await write_gate_event(
                    ctx, step_id, "approval", GATE_PASS,
                    {"reason": "prior approval this run"},
                )
                return GateOutcome(outcome=GATE_PASS)

        # ── offline / no handle → pause for human (NEVER auto-approve) ─────────────
        delegate = getattr(runner, "run_human_gate", None)
        if delegate is None:
            detail = {"reason": "explicit human sign-off required before this step"}
            await write_gate_event(ctx, step_id, "approval", GATE_WAIT_HUMAN, detail)
            return GateOutcome(
                outcome=GATE_WAIT_HUMAN,
                events=[
                    {
                        "type": "gate_wait_human",
                        "data": {"step": step_id, "gate": "approval"},
                    }
                ],
                detail=detail,
            )

        # ── D-02/D-04: delegate to the ONE HITL mechanism with the policy snapshot ──
        payload = _exec_policy_snapshot(step, ctx)
        events: list[dict] = []
        rejected = False
        async for event in delegate(step, payload=payload):
            etype = event.get("type")
            if etype == _REJECTED:
                rejected = True
                continue  # internal signal — not re-surfaced as a gate event
            if etype == _EDITED:
                continue  # internal edit signal — not a public gate event
            # review_gate_ready / review_gate_approved flow through UNCHANGED (parity)
            events.append(event)

        outcome = GATE_BLOCK if rejected else GATE_PASS
        await write_gate_event(ctx, step_id, "approval", outcome, None)
        return GateOutcome(outcome=outcome, events=events)
