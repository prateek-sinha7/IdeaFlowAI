"""agents/capabilities/tools/acceptance.py -- the ``acceptance`` tool_provider capability (P27 goal W1).

Emits the tool KEYS for the acceptance-test runner and the page outline. Strings only, so this
package stays import-clean of ``app.*``; the implementation lives in
``app/agents/tools/acceptance_tools.py`` and the factory resolves key -> tool.

``user_allowed=True``: both tools are confined to the run sandbox (the runner drives a headless
browser against the run's own page with http(s) blocked and writes only ``.goal/trace.json``).
"""

from __future__ import annotations

from typing import Any

from agents.capabilities.registry import register

TOOL_RUN_ACCEPTANCE = "run_acceptance"
TOOL_PAGE_OUTLINE = "page_outline"


@register(
    "tool",
    "acceptance",
    user_allowed=True,
    description="Run the run's acceptance tests in headless Chrome against the built page and write the trace (run_acceptance), and map a large page without reading it (page_outline).",
)
class AcceptanceToolProvider:
    """The acceptance tool set (``name='acceptance'``); keeps the native fs tools."""

    name = "acceptance"

    def provide(self, spec: Any, ctx: Any) -> tuple[list[str], bool]:
        return ([TOOL_RUN_ACCEPTANCE, TOOL_PAGE_OUTLINE], False)
