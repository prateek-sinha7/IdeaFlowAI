"""Launch needs derived from a manifest (design section 3.5.4, Req 7.13, 23.17).

``derive(manifest)`` lists what the user must provide before the workflow can
launch:

| Manifest signal                                                         | Need         |
|-------------------------------------------------------------------------|--------------|
| ``context_providers`` has ``uploaded_files``, or a step's                |              |
| ``tools.tool_sets`` has ``file_extract``                                 | ``uploads``  |
| ``context_providers`` has ``opendesign``                                 | ``design``   |
| a step's ``tools.mcp`` entry ``server.tool`` or ``tools.integrations``   | ``connector``|
| top-level ``seed_files.from_run`` is non-empty                           | ``source_run``|
| a step's ``tools.connectors`` entry ``connector__tool`` (``github``,``jira``) | ``connector``|

``previous_run`` is forbidden in a Draft and never produces a need. Steps are
read at every nesting depth (``subagents.steps``). The result has a fixed
order: uploads, design, connectors by server name, source run.

The module is pure: no I/O and no ``app.api`` imports.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import Any, Final

from app.agents.workflow_builder.events import LaunchNeed

__all__ = ["derive"]

# Integration scope -> MCP server (catalog "Integration scopes"). A scope that
# is not listed is taken to name its server.
_SCOPE_SERVERS: Final[Mapping[str, str]] = {
    "github_read": "github",
    "gitlab_read": "gitlab",
    "jira_read": "jira",
    "slack_post": "slack",
}


def derive(manifest: Mapping[str, Any]) -> list[LaunchNeed]:
    """Return the launch needs of ``manifest``.

    Args:
        manifest: A workflow manifest, normally ``{"steps": [...], ...}``.

    Returns:
        One ``uploads`` need, one ``design`` need, one ``connector`` need per
        server (``detail`` is the server name), and one ``source_run`` need,
        each only when its signal is present.
    """
    providers = _string_set(manifest.get("context_providers"))
    steps = list(_iter_steps(manifest.get("steps")))

    needs: list[LaunchNeed] = []

    uses_file_extract = any(
        "file_extract" in _string_set(_tools(step).get("tool_sets")) for step in steps
    )
    if "uploaded_files" in providers or uses_file_extract:
        needs.append(LaunchNeed(kind="uploads"))

    if "opendesign" in providers:
        needs.append(LaunchNeed(kind="design"))

    servers: set[str] = set()
    for step in steps:
        tools = _tools(step)
        servers.update(_mcp_server(entry) for entry in _strings(tools.get("mcp")))
        servers.update(
            _SCOPE_SERVERS.get(scope, scope)
            for scope in _strings(tools.get("integrations"))
        )
        servers.update(
            _connector_key(entry) for entry in _strings(tools.get("connectors"))
        )
    servers.discard("")
    needs.extend(LaunchNeed(kind="connector", detail=name) for name in sorted(servers))

    seed_files = manifest.get("seed_files")
    from_run = seed_files.get("from_run") if isinstance(seed_files, Mapping) else None
    if isinstance(from_run, (list, tuple)) and from_run:
        needs.append(LaunchNeed(kind="source_run"))

    return needs


def _mcp_server(entry: str) -> str:
    """Server name of a ``server.tool`` entry."""
    return entry.partition(".")[0]


def _connector_key(entry: str) -> str:
    """Connector key of a ``<connector>__<tool>`` grant, for example ``jira``."""
    return entry.partition("__")[0]


def _tools(step: Mapping[str, Any]) -> Mapping[str, Any]:
    """The step's ``tools`` mapping, or an empty one."""
    tools = step.get("tools")
    return tools if isinstance(tools, Mapping) else {}


def _strings(value: object) -> list[str]:
    """The string items of a list value; anything else gives an empty list."""
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _string_set(value: object) -> frozenset[str]:
    """The string items of a list value as a set."""
    return frozenset(_strings(value))


def _iter_steps(steps: object) -> Iterator[Mapping[str, Any]]:
    """Yield every step mapping, nested ones included."""
    if not isinstance(steps, list):
        return
    for step in steps:
        if not isinstance(step, Mapping):
            continue
        yield step
        subagents = step.get("subagents")
        if isinstance(subagents, Mapping):
            yield from _iter_steps(subagents.get("steps"))
