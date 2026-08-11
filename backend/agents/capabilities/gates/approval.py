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

import logging
from typing import Any, AsyncGenerator

logger = logging.getLogger(__name__)

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
# REDO-GATE F1a: the shared _run_review_gate may now emit _gate_redo. An approval
# gate reviews an exec POLICY snapshot — redo is meaningless here and is NOT wired.
# A stray _gate_redo MUST be CONSUMED (never yielded, never mapped to GATE_PASS) so
# the exec step cannot silently advance on a redo signal.
_REDO = "_gate_redo"
# ISS-053: likewise ``_gate_update_specs``. An approval gate reviews an exec POLICY
# snapshot — there is no spec to revise, so it is not wired for that action either. A
# stray signal MUST be CONSUMED: unhandled it hit the ``yield event`` fall-through
# (leaking an internal ``_gate_*`` onto the SSE wire) and resolved to GATE_PASS — an exec
# step signing off its own approval on an action the approver never took.
_UPDATE_SPECS = "_gate_update_specs"


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


@register(
    "gate",
    "approval",
    user_allowed=False,
    description="Require an explicit privileged approval before the step proceeds.",
)
class ApprovalGate:
    """Explicit exec sign-off gate (``name='approval'``) delegating to the HITL machinery.

    Satisfies the ``GateHandler`` port structurally (``name`` + ``async evaluate``).
    """

    name = "approval"

    async def evaluate_stream(
        self, step: Any, ctx: Any
    ) -> AsyncGenerator[Any, None]:
        """Stream the review-gate events AS PRODUCED, then a terminal ``GateOutcome``.

        F1 fix (Phase 13): same streaming protocol as ``HumanGate.evaluate_stream``
        — each public delegate event is yielded the moment ``run_human_gate``
        produces it, so ``review_gate_ready`` reaches the dispatch loop (and the WS
        consumer) BEFORE the delegate resumes into ``await event.wait()``. The D-03
        first-exec memory, the D-04 policy-snapshot payload, and the offline
        never-auto-approve pause are UNCHANGED — only the event buffering moved.

        Protocol: yields zero or more public gate event dicts, then exactly one
        terminal ``GateOutcome`` (with ``events=[]`` — no double emission).
        """
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
                yield GateOutcome(outcome=GATE_PASS)
                return

        # ── offline / no handle → pause for human (NEVER auto-approve) ─────────────
        delegate = getattr(runner, "run_human_gate", None)
        if delegate is None:
            detail = {"reason": "explicit human sign-off required before this step"}
            await write_gate_event(ctx, step_id, "approval", GATE_WAIT_HUMAN, detail)
            yield {
                "type": "gate_wait_human",
                "data": {"step": step_id, "gate": "approval"},
            }
            yield GateOutcome(outcome=GATE_WAIT_HUMAN, detail=detail)
            return

        # ── D-02/D-04: delegate to the ONE HITL mechanism with the policy snapshot ──
        payload = _exec_policy_snapshot(step, ctx)
        rejected = False
        unwired_action_seen = False
        async for event in delegate(step, payload=payload):
            etype = event.get("type")
            if etype == _REJECTED:
                rejected = True
                continue  # internal signal — not re-surfaced as a gate event
            if etype in (_REDO, _UPDATE_SPECS):
                # REDO-GATE F1a / ISS-053: consume — never yield (no wire leak), never PASS.
                unwired_action_seen = True
                continue
            if etype == _EDITED:
                # WR-04 (13 review fix): an approval gate reviews the D-04 exec
                # POLICY SNAPSHOT — there is no upstream artifact an edit could
                # apply to. The edit is EXPLICITLY discarded (logged, never
                # silent) rather than threaded like the human gate's.
                logger.warning(
                    "approval gate on step %s: edited_content ignored — the "
                    "approval payload is a policy snapshot, not an editable "
                    "artifact (WR-04)",
                    step_id,
                )
                continue  # internal edit signal — not a public gate event
            # review_gate_ready / review_gate_approved flow through UNCHANGED (parity)
            # — yielded IMMEDIATELY so ready reaches the consumer pre-await (F1).
            yield event

        # REDO-GATE F1a: a stray redo maps to a NON-PASS outcome (GATE_WAIT_HUMAN) so
        # the exec step does NOT silently sign off; reject still wins (GATE_BLOCK).
        # The audit row records the honest non-PASS outcome (F9).
        outcome = (
            GATE_BLOCK if rejected
            else (GATE_WAIT_HUMAN if unwired_action_seen else GATE_PASS)
        )
        await write_gate_event(ctx, step_id, "approval", outcome, None)
        yield GateOutcome(outcome=outcome, events=[])

    async def evaluate(self, step: Any, ctx: Any) -> GateOutcome:
        """Thin collector over ``evaluate_stream`` (INV-12 single implementation).

        Preserves the pre-streaming contract exactly: returns one ``GateOutcome``
        whose ``events`` list carries every public event the stream produced
        (incl. the offline ``gate_wait_human`` event) with the terminal's
        ``outcome``/``detail``.
        """
        events: list[dict] = []
        terminal: GateOutcome | None = None
        async for item in self.evaluate_stream(step, ctx):
            if isinstance(item, dict):
                events.append(item)
            else:
                terminal = item
        if terminal is None:  # defensive — the stream always yields one terminal
            terminal = GateOutcome(outcome=GATE_PASS)
        return GateOutcome(
            outcome=terminal.outcome, events=events, detail=terminal.detail
        )
