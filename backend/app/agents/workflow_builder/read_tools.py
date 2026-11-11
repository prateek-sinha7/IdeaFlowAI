"""Read-only lookup tools for the workflow builder agent (design section 3.7).

The final tool list is pending Q-18. Until it arrives this module fixes only the
:class:`BuilderReadPort` interface and six placeholder tools whose names match
``stages.READ_TOOL_NAMES``. Every tool is a closure over the caller's ``user_id``
and ``tier``, so the model has no way to name another user (Req 27.7, 27.8). The
tools return JSON text with fixed fields and bounded lists, never raw ORM rows.
Each call is a ``lookup`` and moves the turn to the ``looking_up`` stage
(Req 39.5, see :func:`stages.stage_for_tool`).

No user-data adapter exists yet. :class:`PlaceholderReadPort` serves
``builder_models`` from :mod:`model_catalog_view` and raises
:class:`ReadNotAvailableError` for every other call; the tools turn that into
a ``{"available": false}`` answer instead of failing the turn.

The agent layer stays free of ``app.api`` imports. The port is the seam where
the API layer will inject a database-backed adapter once Q-18 is decided.

Public surface:

* :class:`AgentFact`, :class:`SkillFact`, :class:`ConnectorFact`,
  :class:`WorkflowFact`, the fixed-field records a port returns.
* :class:`BuilderReadPort`, the read interface.
* :class:`ReadNotAvailableError`, raised by a port that has no data source.
* :class:`PlaceholderReadPort`, the default port until Q-18.
* :func:`build_read_tools`, the per-turn tool closures.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Final, Protocol

from langchain_core.tools import BaseTool, tool

from app.agents.workflow_builder.model_catalog_view import (
    BuilderModelView,
    builder_models,
)
from app.agents.workflow_builder.stages import READ_TOOL_NAMES

__all__ = [
    "MAX_AGENTS",
    "MAX_CONNECTORS",
    "MAX_HANDOFF_TARGETS",
    "MAX_SKILLS",
    "MAX_SKILLS_PER_AGENT",
    "MAX_SUMMARY_CHARS",
    "MAX_WORKFLOW_NAMES",
    "NOT_AVAILABLE_MESSAGE",
    "AgentFact",
    "BuilderReadPort",
    "ConnectorFact",
    "PlaceholderReadPort",
    "ReadNotAvailableError",
    "SkillFact",
    "WorkflowFact",
    "build_read_tools",
]

# Bounds from the design table in section 3.7. Names-only lists get a generous
# cap so one call can never return an unbounded payload.
MAX_AGENTS: Final = 50
MAX_SUMMARY_CHARS: Final = 280
MAX_SKILLS: Final = 100
MAX_WORKFLOW_NAMES: Final = 200
MAX_CONNECTORS: Final = 100
MAX_HANDOFF_TARGETS: Final = 100
MAX_SKILLS_PER_AGENT: Final = 20

NOT_AVAILABLE_MESSAGE: Final = "not available yet"


@dataclass(frozen=True, slots=True)
class AgentFact:
    """One of the user's saved agents: name, prompt summary and skill ids."""

    name: str
    prompt_summary: str
    skills: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SkillFact:
    """One skill the user may reference: its id and where it comes from."""

    id: str
    source: str  # "user" or "global"


@dataclass(frozen=True, slots=True)
class ConnectorFact:
    """One configured connector. Server name only, never a secret."""

    server_name: str


@dataclass(frozen=True, slots=True)
class WorkflowFact:
    """One workflow the tier may hand off to: id and display name."""

    id: str
    display_name: str


class ReadNotAvailableError(Exception):
    """Raised by a port that has no data source for the requested read."""


class BuilderReadPort(Protocol):
    """Read-only lookups the builder may use. Implemented in the API layer (Q-18)."""

    def my_agents(self, user_id: str) -> list[AgentFact]: ...

    def my_skills(self, user_id: str) -> list[SkillFact]: ...

    def my_workflow_names(self, user_id: str) -> list[str]: ...

    def my_connectors(self, user_id: str) -> list[ConnectorFact]: ...

    def handoff_targets(self, tier: str) -> list[WorkflowFact]: ...

    def builder_models(self, tier: str) -> BuilderModelView: ...


class PlaceholderReadPort:
    """Port used until Q-18 supplies the tool list.

    ``builder_models`` is served from the shared model catalog. Every other
    read raises :class:`ReadNotAvailableError`.
    """

    def my_agents(self, user_id: str) -> list[AgentFact]:
        raise ReadNotAvailableError(NOT_AVAILABLE_MESSAGE)

    def my_skills(self, user_id: str) -> list[SkillFact]:
        raise ReadNotAvailableError(NOT_AVAILABLE_MESSAGE)

    def my_workflow_names(self, user_id: str) -> list[str]:
        raise ReadNotAvailableError(NOT_AVAILABLE_MESSAGE)

    def my_connectors(self, user_id: str) -> list[ConnectorFact]:
        raise ReadNotAvailableError(NOT_AVAILABLE_MESSAGE)

    def handoff_targets(self, tier: str) -> list[WorkflowFact]:
        raise ReadNotAvailableError(NOT_AVAILABLE_MESSAGE)

    def builder_models(self, tier: str) -> BuilderModelView:
        return builder_models(tier)


def _dump(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _unavailable() -> str:
    return _dump({"available": False, "message": NOT_AVAILABLE_MESSAGE})


def _bounded(items: Sequence[Any], limit: int) -> tuple[list[Any], bool]:
    """Return the first ``limit`` items and whether any were cut."""
    return list(items[:limit]), len(items) > limit


def _truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "\u2026"


def _listing(key: str, rows: list[Any], truncated: bool) -> str:
    return _dump(
        {"available": True, key: rows, "count": len(rows), "truncated": truncated}
    )


def _model_rows(entries: Sequence[Any]) -> list[dict[str, Any]]:
    return [
        {
            "id": e.id,
            "label": e.label,
            "cost_class": e.cost_class,
            "levels": list(e.reasoning.levels),
        }
        for e in entries
    ]


def _guarded(read: Callable[[], str]) -> str:
    try:
        return read()
    except ReadNotAvailableError:
        return _unavailable()


def build_read_tools(
    port: BuilderReadPort, *, user_id: str, tier: str
) -> list[BaseTool]:
    """Build the read tools for one turn, bound to ``user_id`` and ``tier``.

    The tool arguments never carry a user id or tier, so the model cannot ask
    about another user. The returned tool names equal ``READ_TOOL_NAMES``.
    """

    @tool
    def list_my_agents() -> str:
        """List the user's saved agents: name, short prompt summary and skill ids."""

        def read() -> str:
            facts, truncated = _bounded(port.my_agents(user_id), MAX_AGENTS)
            rows = [
                {
                    "name": f.name,
                    "prompt_summary": _truncate(f.prompt_summary, MAX_SUMMARY_CHARS),
                    "skills": list(f.skills[:MAX_SKILLS_PER_AGENT]),
                }
                for f in facts
            ]
            return _listing("agents", rows, truncated)

        return _guarded(read)

    @tool
    def list_my_skills() -> str:
        """List skill ids the user may reference: their own and the global catalog."""

        def read() -> str:
            facts, truncated = _bounded(port.my_skills(user_id), MAX_SKILLS)
            rows = [{"id": f.id, "source": f.source} for f in facts]
            return _listing("skills", rows, truncated)

        return _guarded(read)

    @tool
    def list_my_workflow_names() -> str:
        """List the names of the user's own workflows, to avoid a name clash."""

        def read() -> str:
            unique = list(dict.fromkeys(port.my_workflow_names(user_id)))
            names, truncated = _bounded(unique, MAX_WORKFLOW_NAMES)
            return _listing("names", names, truncated)

        return _guarded(read)

    @tool
    def list_my_connectors() -> str:
        """List the names of the user's configured connectors. Never secrets."""

        def read() -> str:
            facts, truncated = _bounded(port.my_connectors(user_id), MAX_CONNECTORS)
            rows = [{"server_name": f.server_name} for f in facts]
            return _listing("connectors", rows, truncated)

        return _guarded(read)

    @tool
    def list_handoff_targets() -> str:
        """List the workflows the user's plan may hand off to: id and display name."""

        def read() -> str:
            facts, truncated = _bounded(port.handoff_targets(tier), MAX_HANDOFF_TARGETS)
            rows = [{"id": f.id, "display_name": f.display_name} for f in facts]
            return _listing("targets", rows, truncated)

        return _guarded(read)

    @tool
    def get_builder_models() -> str:
        """List the models the user's plan allows: chat and step lists with levels."""

        def read() -> str:
            view = port.builder_models(tier)
            return _dump(
                {
                    "available": True,
                    "chat": _model_rows(view.chat),
                    "step": _model_rows(view.step),
                    "default_chat_id": view.default_chat_id,
                }
            )

        return _guarded(read)

    tools: list[BaseTool] = [
        list_my_agents,
        list_my_skills,
        list_my_workflow_names,
        list_my_connectors,
        list_handoff_targets,
        get_builder_models,
    ]
    if {t.name for t in tools} != READ_TOOL_NAMES:
        raise RuntimeError("read tool names drifted from stages.READ_TOOL_NAMES")
    if isinstance(port, PlaceholderReadPort):
        # Until Q-18 supplies a data source, the five user-data tools only answer
        # "not available". Binding them costs schema tokens and tool calls for no
        # answer, so only get_builder_models, which the placeholder port serves, is offered.
        return [t for t in tools if t.name == "get_builder_models"]
    return tools
