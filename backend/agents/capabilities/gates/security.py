"""agents/capabilities/gates/security.py — the ``security`` gate (08-02 / 10-03 / §9).

The runtime SECOND line of the 3-tier exec stack (compiler ceiling → THIS gate →
workspace ``ExecutionPolicy``). The exec branch is split from network/secrets:

  * ``exec`` (10-03 / N3): a file/builtin-trust step requesting ``exec`` PASSES iff
    (a) the step trust is file/builtin (engineer trust — the compiler already
    hard-fails a user/db exec grant at compile, 10-02, so an exec grant reaching
    this gate is engineer-authored), (b) the ``approval`` gate is declared on the
    step (D-01 defense-in-depth — a missing ``approval`` is NOT a silent pass, it
    BLOCKS so the runtime never authorizes exec without the HITL sign-off the
    compiler also requires), and (c) a constrained profile is attached (the bound
    ``ctx.runner.workspace.policy`` carries a non-empty exec allow-list; when the
    workspace is not yet bound at gate time, profile presence is IMPLIED by the
    exec-conditional provisioning at the §15 host seam — do NOT block solely on an
    unbound workspace).
  * ``network`` / ``secrets`` (still OFF — later phases): BLOCK, byte-identical to
    the pre-10-03 default-deny path (same detail + events).

Registered ``user_allowed=False`` (D-01/D-02): the security gate is engineer-only;
it is never user-grantable (it is the seam keeping exec off the user palette).

Import purity (import-linter): imports only the registry decorator + the gate
outcome contract + the ``write_gate_event`` helper; reaches the ``gate_events``
writer + the bound workspace policy through ``ctx.runner`` — NO kernel/app import.
"""

from __future__ import annotations

from typing import Any

from agents.capabilities.gates.base import GATE_BLOCK, GATE_PASS, GateOutcome
from agents.capabilities.gates.write import write_gate_event
from agents.capabilities.registry import register

# Trust levels that may author an exec grant (engineer trust). The compiler already
# rejects a user/db exec grant at compile (10-02 GRANT-PATH); this is the runtime
# echo of that bound — defense-in-depth, not the primary enforcement.
_ENGINEER_TRUST = frozenset({"file", "builtin"})


@register(
    "gate",
    "security",
    user_allowed=False,
    description="Enforce the security posture before a privileged step (exec/network/secrets/spawn default OFF).",
    config_schema={
        "type": "object",
        "properties": {
            "exec": {
                "type": "boolean",
                "description": "Allow code execution for the gated step.",
                "default": False,
            },
            "network": {
                "type": "boolean",
                "description": "Allow outbound network access for the gated step.",
                "default": False,
            },
            "secrets": {
                "type": "boolean",
                "description": "Allow secret access for the gated step.",
                "default": False,
            },
            "spawn_subagents": {
                "type": "boolean",
                "description": "Allow the step to spawn sub-agents.",
                "default": False,
            },
        },
    },
)
class SecurityGate:
    """Profile-conditional exec gate + default-deny network/secrets (``name='security'``).

    Satisfies the ``GateHandler`` port structurally (``name`` + ``async evaluate``).
    """

    name = "security"

    async def evaluate(self, step: Any, ctx: Any) -> GateOutcome:
        """PASS a constrained file/builtin exec step; BLOCK network/secrets (OFF)."""
        tools = getattr(step, "tools", None)
        wants_exec = bool(getattr(tools, "exec", False))
        wants_network = bool(getattr(tools, "network", False))
        wants_secrets = bool(getattr(tools, "secrets", None))

        step_id = getattr(step, "agent_id", None) or "?"

        # ── network / secrets — BLOCK (byte-identical to the pre-10-03 deny path) ──
        # These stay OFF this phase (later phases). Kept SEPARATE from the exec
        # branch so loosening exec never loosens network/secrets (T-10-03-02).
        net_secret = [
            label
            for label, wanted in (("network", wants_network), ("secrets", wants_secrets))
            if wanted
        ]
        if net_secret:
            detail = {
                "denied": net_secret,
                "reason": "privileged permissions are OFF this phase (default-deny)",
            }
            await write_gate_event(ctx, step_id, "security", GATE_BLOCK, detail)
            return GateOutcome(
                outcome=GATE_BLOCK,
                events=[
                    {
                        "type": "gate_blocked",
                        "data": {
                            "step": step_id,
                            "gate": "security",
                            "denied": net_secret,
                        },
                    }
                ],
                detail=detail,
            )

        # ── exec — profile-conditional PASS (10-03 / N3) ───────────────────────────
        if wants_exec:
            # (a) trust: file/builtin only (compiler already enforces this — 10-02).
            #     No explicit `trust` attribute on the compiled Step ⇒ an exec grant
            #     reaching here is engineer-authored (file/builtin default).
            trust = getattr(step, "trust", "file") or "file"
            if trust not in _ENGINEER_TRUST:
                return await self._block_exec(
                    ctx, step_id, f"exec requires engineer trust (file/builtin); got {trust!r}"
                )

            # (b) D-01 defense-in-depth: the `approval` gate MUST be declared. A
            #     missing approval is NOT a silent pass — the runtime refuses to
            #     authorize exec without the HITL sign-off (T-10-03-01).
            declared_gates = list(getattr(step, "gates", []) or [])
            if "approval" not in declared_gates:
                return await self._block_exec(
                    ctx, step_id,
                    "exec requires the 'approval' gate declared (D-01); none found",
                )

            # (c) constrained profile attached: the bound workspace policy carries a
            #     non-empty exec allow-list. When the workspace is NOT yet bound at
            #     gate time, profile presence is IMPLIED by the exec-conditional
            #     provisioning at the §15 host seam — do NOT block on an unbound
            #     workspace (the seam binds it before the step runs).
            runner = getattr(ctx, "runner", None)
            workspace = getattr(runner, "workspace", None)
            if workspace is not None:
                policy = getattr(workspace, "policy", None)
                exec_allow = list(getattr(policy, "exec_allow", []) or [])
                if not exec_allow:
                    return await self._block_exec(
                        ctx, step_id,
                        "exec requires a constrained profile (non-empty allow-list); "
                        "the bound workspace has none",
                    )

            # All three conditions hold → PASS the exec request.
            detail = {"granted": "exec", "reason": "file/builtin trust + approval declared + constrained profile"}
            await write_gate_event(ctx, step_id, "security", GATE_PASS, detail)
            return GateOutcome(outcome=GATE_PASS, detail=detail)

        # ── no privileged request — PASS (parity: every existing step) ─────────────
        await write_gate_event(ctx, step_id, "security", GATE_PASS, None)
        return GateOutcome(outcome=GATE_PASS)

    async def _block_exec(self, ctx: Any, step_id: str, reason: str) -> GateOutcome:
        """Write a block gate_events row + return the block outcome for an exec refusal."""
        detail = {"denied": ["exec"], "reason": reason}
        await write_gate_event(ctx, step_id, "security", GATE_BLOCK, detail)
        return GateOutcome(
            outcome=GATE_BLOCK,
            events=[
                {
                    "type": "gate_blocked",
                    "data": {"step": step_id, "gate": "security", "denied": ["exec"]},
                }
            ],
            detail=detail,
        )
