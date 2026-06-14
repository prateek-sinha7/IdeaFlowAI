"""agents/capabilities/post_steps/api_prefix_audit.py — the ``api_prefix_audit`` post-step (19-02 / ISS-005).

The declared, EVENT-FREE post-step that runs the ``api_prefix`` validator as a pure
side effect after the infra-generator step (the INV-3-CRITICAL wiring decision).

WHY a post_step and NOT a ``gates: [validation]`` gate: the ``validation`` gate emits
a ``validation_warning`` event when residual (non-critical) issues exist — but the
85-event app_builder characterization golden contains NO such event, so a gate would
break INV-3 byte/event-identity. A post_step is side-effects-only (the engine invokes
it at the declared-post_step seam in ``_run_step``, engine.py:1889-1891, and yields
NOTHING from it), so the run's event stream is
untouched and the golden stays byte-identical. The ``validation_results`` audit row
the validator writes is NOT golden-tracked, so it does not perturb parity either.

Mirrors ``revision_validation.py`` exactly: ``@register("post_step", ...)``,
``async def run(self, step, ctx)``, side-effects only, NEVER raises (a validator
error must never abort the run), reaches the runner via ``getattr(ctx, "runner", None)``
and the deliverable via ``getattr(ctx, "deliverable", None)``.

Import purity (import-linter / INV-13): imports NOTHING from
``agents.execution_engine`` or ``app.*``; the validator is reached through the
registry, and the kernel handle through the object-typed ``ctx``/``step`` handles —
exactly as ``revision_validation`` does.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from agents.capabilities.registry import register

logger = logging.getLogger(__name__)


@dataclass
class _AuditTarget:
    """A DeliverableContext-shaped target the ``api_prefix`` validator reads.

    The validator reads only ``.runner`` (→ ``.sandbox`` + ``record_validation_result``),
    ``.step`` and ``.task_meta`` — so this tiny local stub is sufficient and keeps the
    shim import-pure (no kernel ``DeliverableContext`` import → no kernel→app cycle).
    """

    name: str
    runner: Any
    step: str = ""
    task_meta: dict = field(default_factory=dict)


@register(
    "post_step",
    "api_prefix_audit",
    description="After a step, run an event-free infra audit for endpoints not under the /api/v1 prefix.",
)
class ApiPrefixAuditPostStep:
    """Runs the ``api_prefix`` validator side-effects-only (``name='api_prefix_audit'``).

    Satisfies the ``PostStep`` port structurally (``name`` + ``async run``).
    """

    name = "api_prefix_audit"

    async def run(self, step: Any, ctx: Any) -> None:
        """Run the ``api_prefix`` validator as a pure side effect (NO events, NEVER raises)."""
        runner = getattr(ctx, "runner", None)
        if runner is None:
            return

        try:
            from agents.capabilities.registry import CapabilityRegistry

            validator = CapabilityRegistry().resolve("validator", "api_prefix")

            deliverable = getattr(ctx, "deliverable", None)
            target = _AuditTarget(
                name=getattr(deliverable, "name", "") or "",
                runner=runner,
                step=getattr(step, "agent_id", "") or "",
                task_meta={"attempt": 0},
            )
            issues = await validator.validate(target)
            if issues:
                logger.info(
                    "api_prefix_audit: %d infra endpoint(s) missing %s on step %s",
                    len(issues), "/api/v1", target.step,
                )
        except Exception as exc:  # noqa: BLE001 — an audit error must never abort the run
            logger.warning(
                "api_prefix_audit: validation errored (%s) — continuing", exc,
            )
