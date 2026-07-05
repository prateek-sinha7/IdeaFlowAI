"""app/agents/validators/html_render.py — the ``html_render`` registered Validator (D-04).

Migrates the prototype build loop's headless ``render_check`` into a registered
``Validator`` capability (VALID-01/04). It lives APP-side because ``render_check``
is a heavy/app dependency (Playwright + Chromium); it imports the kernel PORT
(``agents.capabilities.base.Validator``) + the ``@register`` decorator — the
import-linter-LEGAL direction (app → capabilities). It NEVER imports the kernel:
it reaches ``render_check`` through the KernelServices handle
(``target.runner.render_check(target.path)``), so there is no kernel→app edge.

Severity mapping uses the SINGLE canonical ``map_severity`` IMPORTED from
``agents.capabilities.validators.severity`` (08-01, VALID-03 single source) — this
module does NOT define a second mapping. Console errors, uncaught page exceptions,
and dead nav links are render-breaking → internal P0 (CRITICAL).

Offline degrade: when Chromium/Playwright is unavailable the check returns
``available=False`` → NO issues (a skip, not a failure — byte-identical to the
legacy build loop's render-unavailable degrade).

Each run writes one ``validation_results`` row via the handle's
``record_validation_result`` (owner/workspace-scoped, D-10) — best-effort.
"""

from __future__ import annotations

import logging
from typing import Any

from agents.capabilities.base import Validator  # port import — import-linter LEGAL
from agents.capabilities.registry import register
from agents.capabilities.validators.severity import (  # single source (08-01 / RENDER-SEAM)
    map_severity,
    render_coverage_status,
)
from app.agents.validators.html_static import Issue, _record

logger = logging.getLogger("app.agents.validators.html_render")


@register(
    "validator",
    "html_render",
    user_allowed=True,
    description="Render a single-file HTML prototype in headless Chromium and flag nav/console-error failures.",
)
class HtmlRenderValidator:
    """Wraps ``render_check`` as a registered ``Validator`` (``name='html_render'``).

    Satisfies the ``Validator`` Protocol (``name`` + ``async validate``).
    """

    name = "html_render"

    async def validate(self, target: Any) -> list[Issue]:
        """Run ``render_check`` via the handle, returning mapped ``Issue`` records.

        Reaches the heavy check ONLY through ``target.runner.render_check`` (async).
        An unavailable browser (``available=False``) yields NO issues (a skip). The
        ``map_severity`` import is the single canonical mapping (08-01).
        """
        runner = getattr(target, "runner", None)
        if runner is None:
            return []
        result = await runner.render_check(target.path)

        # Resolve the per-step require_render knob (RENDER-SEAM / REQUIRE-RENDER-KNOB):
        # the compiled Step.require_render is threaded onto the DeliverableContext; when
        # unset (None) fall back to the Settings default (skip-is-a-pass — INV-3).
        require_render = getattr(target, "require_render", None)
        if require_render is None:
            from app.core.config import settings

            require_render = settings.PROTOTYPE_REQUIRE_RENDER

        status = render_coverage_status(result, bool(require_render))

        # ── Render did NOT run — fail closed or record a distinct skip audit ──
        if status != "ok":
            await self._record_skip(target, result)
            if status == "skipped_blocked":
                # require_render=true → emit a P0 so the EXISTING ValidationGate
                # block-critical policy fires (GATE_BLOCK) — no new gate outcome.
                return [
                    Issue(
                        severity="P0",
                        message=f"render unavailable (require_render): "
                                f"{getattr(result, 'note', '')}",
                        validator="html_render",
                    )
                ]
            # skipped_allowed → a pass, but the skip was recorded (never swallowed).
            return []

        issues: list[Issue] = []
        for msg in getattr(result, "console_errors", None) or []:
            issues.append(
                Issue(severity="P0", message=f"console error: {msg}",
                      validator="html_render")
            )
        for msg in getattr(result, "page_errors", None) or []:
            issues.append(
                Issue(severity="P0", message=f"uncaught exception: {msg}",
                      validator="html_render")
            )
        for nav in getattr(result, "nav_results", None) or []:
            if not getattr(nav, "ok", True):
                issues.append(
                    Issue(
                        severity="P0",
                        message=f"dead nav link: {getattr(nav, 'href', '?')} "
                                f"(no section activated)",
                        validator="html_render",
                    )
                )
        # Nav-COVERAGE findings (a multi-section SPA that exercised 0 nav) — P0.
        for msg in getattr(result, "coverage_errors", None) or []:
            issues.append(
                Issue(severity="P0", message=f"nav coverage: {msg}",
                      validator="html_render")
            )

        await _record(target, "html_render", issues)
        return issues

    async def _record_skip(self, target: Any, result: Any) -> None:
        """Write a distinct ``validator_skipped`` audit row for a render skip (VALIDATOR-SKIPPED).

        Guarded like ``_record`` (a no-op when the runner / record hook is absent) so
        the audit write never aborts the validator (INV-3). The ``SKIPPED`` severity
        sentinel marks the row so a render skip is RECORDED — never swallowed into
        "no issues" — even when ``require_render`` is False.
        """
        runner = getattr(target, "runner", None)
        if runner is None:
            return
        record = getattr(runner, "record_validation_result", None)
        if record is None:
            return
        note = getattr(result, "note", "") or ""
        step = getattr(target, "step", "") or ""
        attempt = int((getattr(target, "task_meta", None) or {}).get("attempt", 0))
        logger.info("html_render: render skipped (%s) — recording validator_skipped", note)
        await record(
            step,
            "html_render",
            severity="SKIPPED",
            attempt=attempt,
            issues=[{"severity": "SKIPPED", "message": note}],
        )
