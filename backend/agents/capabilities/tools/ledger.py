"""agents/capabilities/tools/ledger.py — the ``ledger`` tool_provider capability (P27 E5).

Emits the single tool KEY the requirement-ledger check needs. Like every other
provider here it returns STRINGS, never tool objects, so this package stays
import-clean of ``app.*`` (import-linter: ``agents.capabilities`` ↛ ``app``) —
the concrete implementation lives in ``app/agents/tools/ledger_tools.py`` and the
factory, which IS the composition root, resolves key → tool.

``user_allowed=True``: the check is read-only and confined to the run sandbox.
"""

from __future__ import annotations

from typing import Any

from agents.capabilities.registry import register

TOOL_LEDGER_CHECK = "ledger_check"


@register(
    "tool",
    "ledger",
    user_allowed=True,
    description="Check the run's requirement ledger against the source text, spec, tasks, acceptance tests, trace and report (ledger_check modes: harvest, coverage, trace, report). Read-only.",
)
class LedgerToolProvider:
    """The ledger tool set (``name='ledger'``).

    Returns ``exclude_builtin=False`` — the check reads only, so the native
    filesystem tools stay alongside it.
    """

    name = "ledger"

    def provide(self, spec: Any, ctx: Any) -> tuple[list[str], bool]:
        return ([TOOL_LEDGER_CHECK], False)
