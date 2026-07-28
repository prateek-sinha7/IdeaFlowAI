"""Reusable html-prototype validation-result stub factories + a thin
select_issues_to_fix wrapper. _select_issues_to_fix is confirmed shared
engine code (its sibling helper _dead_nav_message in
agents/execution_engine/engine.py is documented as "shared by
_select_issues_to_fix AND the build residual assembly ... so the two can
never diverge") — so this is genuinely cross-pipeline, not just DRY.
"""

from __future__ import annotations


def make_static_result(*, ok: bool = True, issues: list[str] | None = None):
    from app.agents.static_check import StaticCheckResult

    return StaticCheckResult(ok=ok, issues=issues or [])


def make_render_result(
    *,
    ok: bool = True,
    available: bool = True,
    console_errors: list[str] | None = None,
    page_errors: list[str] | None = None,
):
    from app.agents.render_check import RenderResult

    kwargs = {"ok": ok, "available": available}
    if console_errors is not None:
        kwargs["console_errors"] = console_errors
    if page_errors is not None:
        kwargs["page_errors"] = page_errors
    return RenderResult(**kwargs)


def select_issues_to_fix(
    static_result,
    render_result,
    baseline_static: "set[str] | None" = None,
    baseline_console: "set[str] | None" = None,
    *,
    require_render: bool = True,
) -> list[str]:
    from agents.execution_engine.engine import _select_issues_to_fix

    return _select_issues_to_fix(
        static_result, render_result, baseline_static, baseline_console,
        require_render=require_render,
    )
