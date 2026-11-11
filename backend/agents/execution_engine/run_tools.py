"""agents/execution_engine/run_tools.py — the per-run connector tool port.

The engine asks an injected ``RunToolBinder`` for the tools a run's compiled steps were
granted, once, at run entry. This module is the port only: it is stdlib-only and names no
connector, provider or workflow. The app layer supplies the binder implementation, so the
kernel never imports ``app.connectors``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final, Protocol

RUN_TOOL_BIND_TIMEOUT_SECONDS: Final = 30.0
"""Upper bound on one bind call. The engine stops waiting after this many seconds."""


@dataclass(frozen=True)
class RunToolRequest:
    """What the engine asks the binder to bind for one run.

    Attributes:
        run_id: The run's pipeline run id, used for audit rows and log lines.
        user_id: The verified ``users.id`` of the run owner. ``None`` only for anonymous
            runs, which bind no connector tool.
        tool_names: Union of every compiled step's effective connector grant. Names use the
            ``<connector_key>__<tool_name>`` form.
    """

    run_id: str
    user_id: str | None
    tool_names: frozenset[str]


class RunToolBinder(Protocol):
    """Port that binds connector tools for one run.

    Implementations never raise by contract. The engine still wraps the call, so an
    unexpected exception only costs the run its connector tools.
    """

    async def __call__(self, request: RunToolRequest) -> Mapping[str, Any]:
        """Return the bound tools keyed by tool name.

        Args:
            request: The run identity and the union of granted tool names.

        Returns:
            A mapping from each bound tool name to its tool object. Names that cannot be
            bound are absent from the mapping, or present as stubs that return an error.
        """
        ...
