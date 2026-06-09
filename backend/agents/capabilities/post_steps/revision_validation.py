"""agents/capabilities/post_steps/revision_validation.py — the ``revision_validation`` post-step.

The declared post-step capability that owns the in-place-revision validation
(07-10 / CR-06). Relocated OUT of the kernel ``execute()`` (the self-described
"DELIBERATE EXCEPTION"): after the visible revision agent edits the artifact in
place, this capability computes the PRE-edit baseline on the seeded ORIGINAL and
runs the Both-validation + bounded INTERNAL fix-loop, re-injecting the user's
instruction and treating only NEW static/console issues (plus hard
render-breakage) as regressions while leaving pre-existing nits alone.

Byte-identical to the legacy kernel block (INV-3):
  - baseline computed on the seeded ORIGINAL (``ctx.revision_original_html``) via
    the engine's SINGLE-home signature helpers, reached through the handle —
    ``ctx.runner.compute_revision_baseline`` — so the capability never imports the
    kernel (import-linter);
  - the fix-loop is delegated to ``ctx.runner.run_validation_fix_loop`` (the same
    handle method the build path uses), with the agent_id sourced from the
    compiled ``step.agent_id`` (NOT a hardcoded ``"prototype-revision-agent"``
    literal), the captured ``user_instruction``, ``label="revision"``, and the
    computed baselines;
  - NON-YIELDING + NEVER aborts the run (try/except), and only runs when the agent
    actually produced the deliverable file.

Import purity (import-linter / INV-13): imports NOTHING from
``agents.execution_engine`` or ``app.*``; the kernel + validators are reached only
through the object-typed ``ctx.runner`` handle.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_ARTIFACT_NAME = "prototype.html"


class RevisionValidationPostStep:
    """Pre-edit baseline + post-edit Both-validation fix-loop (``name='revision_validation'``).

    Satisfies the ``PostStep`` port structurally (``name`` + ``async run``).
    """

    name = "revision_validation"

    async def run(self, step: Any, ctx: Any) -> None:
        """Compute the pre-edit baseline + run the post-edit fix-loop (CR-06).

        Side effects only (the fix sub-agent edits the artifact on disk); no events
        are emitted. Never raises — a validation error must never abort the run.
        """
        runner = getattr(ctx, "runner", None)
        if runner is None:
            return

        # The artifact name is the declared deliverable.name (parameterized; never a
        # hardcoded const). Only run when the agent actually produced the file.
        deliverable = getattr(ctx, "deliverable", None)
        artifact_name = getattr(deliverable, "name", None) or _DEFAULT_ARTIFACT_NAME

        sandbox = getattr(runner, "sandbox", None)
        if sandbox is None:
            return
        try:
            if not sandbox.path_for(artifact_name).is_file():
                return
        except Exception:  # noqa: BLE001 — defensive: a path probe must never abort
            return

        try:
            # ── Pre-edit baseline on the seeded ORIGINAL ─────────────────────────
            # Computed on ``revision_original_html`` (the pre-edit content the
            # previous_run provider stashed) so only NEW issues count as regressions.
            original_html = getattr(ctx, "revision_original_html", "") or ""
            baseline_static: set[str] = set()
            baseline_console: set[str] = set()
            if original_html:
                baseline_static, baseline_console = (
                    await runner.compute_revision_baseline(original_html)
                )
                # Mirror onto ctx for parity with the legacy ectx.revision_baseline_*
                # (the phase-5 suite reads these off the threaded fix-loop args).
                ctx.revision_baseline_static = baseline_static
                ctx.revision_baseline_console = baseline_console
                logger.info(
                    "revision_validation: pre-edit baseline — %d static issue(s), "
                    "%d console error(s)",
                    len(baseline_static), len(baseline_console),
                )

            # ── Post-edit Both-validation + bounded internal fix-loop ────────────
            # agent_id sourced from the compiled step (NOT a hardcoded literal).
            agent_id = getattr(step, "agent_id", None)
            await runner.run_validation_fix_loop(
                step,
                task_num=1,
                total_tasks=1,
                agent_id=agent_id,
                filename=artifact_name,
                baseline_static=baseline_static,
                baseline_console=baseline_console,
                user_instruction=getattr(ctx, "revision_instruction", None),
                label="revision",
            )
        except Exception as exc:  # noqa: BLE001 — never let validation abort the revision
            logger.warning(
                "revision_validation: post-revision validation errored (%s) — continuing",
                exc,
            )
