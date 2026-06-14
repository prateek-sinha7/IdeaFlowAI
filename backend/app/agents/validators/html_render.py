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

from typing import Any

from agents.capabilities.base import Validator  # port import — import-linter LEGAL
from agents.capabilities.registry import register
from agents.capabilities.validators.severity import map_severity  # single source (08-01)
from app.agents.validators.html_static import Issue, _record


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

        issues: list[Issue] = []
        if getattr(result, "available", True):
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

        await _record(target, "html_render", issues)
        return issues
