"""Builder_Rules: what a Composer draft must not contain (design section 3.5.3).

This module is the one definition of the features a draft may not use.
The Server_Gate rejects them and the Turn_Context lists them, both from
:data:`FORBIDDEN_FEATURES` (Req 23.6, 37.7). The list holds exactly the six
features of Req 23.5. Adding an entry needs the user's approval (Req 23.7).

:func:`check` applies the Builder_Rules and nothing else (Req 23.8):

* forbidden features (Req 23.5),
* step agents outside the agent-id allow-list,
* step models and fallbacks outside the Step_List, naming the allowed ids
  (Req 41.12),
* efforts outside the levels of the step's model (Req 41.11).

Model entitlement by tier and the save check belong to the Server_Gate adapter.

The module is pure: no I/O, no clock, no ``app.api`` import. Issue messages name
the rule, a manifest path and identifiers only. They never repeat prompt text
or other free-form manifest strings (Req 42.3). An id taken from the manifest is
echoed only when it looks like an identifier.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass
from typing import Any, Final

from agents.capabilities.model_catalog import ModelEntry
from agents.workflows.compiler import (
    _MAX_SUBAGENTS_DEPTH,  # noqa: PLC2701 - the one bound the compiler enforces
)
from app.agents.workflow_builder.ports import GateIssue

__all__ = [
    "FORBIDDEN_FEATURES",
    "ForbiddenFeature",
    "check",
    "iter_steps",
]

_CUSTOM_AGENT: Final = "custom-agent"
_SELF_AGENT: Final = "self"

# Ids the manifest supplies (agent, model, effort) are echoed only in this shape.
_SAFE_ID: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
_UNSHOWN_ID: Final = "<not shown>"


# --- Step walkers ---------------------------------------------------------------------


def iter_steps(manifest: Mapping[str, Any]) -> Iterator[tuple[str, Mapping[str, Any]]]:
    """Yield ``(path, step)`` for every step, including nested ``subagents.steps``.

    Nesting is followed exactly as deep as the compiler accepts
    (``_MAX_SUBAGENTS_DEPTH`` levels of ``subagents``). Anything deeper is left
    to the save check. Entries that are not mappings are skipped.
    """
    steps = manifest.get("steps")
    if isinstance(steps, list):
        yield from _walk(steps, "steps", 0)


def _walk(
    steps: list[Any], prefix: str, depth: int
) -> Iterator[tuple[str, Mapping[str, Any]]]:
    for index, step in enumerate(steps):
        if not isinstance(step, Mapping):
            continue
        path = f"{prefix}[{index}]"
        yield path, step
        subagents = step.get("subagents")
        if isinstance(subagents, Mapping) and depth < _MAX_SUBAGENTS_DEPTH:
            children = subagents.get("steps")
            if isinstance(children, list):
                yield from _walk(children, f"{path}.subagents.steps", depth + 1)


def _tools(step: Mapping[str, Any]) -> Mapping[str, Any]:
    tools = step.get("tools")
    return tools if isinstance(tools, Mapping) else {}


# --- Finders: manifest -> paths where a feature occurs --------------------------------

Finder = Callable[[Mapping[str, Any]], list[str]]


def find_step_grant(key: str) -> Finder:
    """Find steps whose ``tools.<key>`` grant is on (a true flag or a non-empty list)."""

    def find(manifest: Mapping[str, Any]) -> list[str]:
        return [
            f"{path}.tools.{key}"
            for path, step in iter_steps(manifest)
            if _tools(step).get(key)
        ]

    return find


def find_mcp_server(server: str) -> Finder:
    """Find ``tools.mcp`` entries of the form ``<server>.<tool>``."""

    def find(manifest: Mapping[str, Any]) -> list[str]:
        found: list[str] = []
        for path, step in iter_steps(manifest):
            entries = _tools(step).get("mcp")
            if not isinstance(entries, list):
                continue
            found.extend(
                f"{path}.tools.mcp[{index}]"
                for index, entry in enumerate(entries)
                if isinstance(entry, str) and entry.partition(".")[0] == server
            )
        return found

    return find


def find_context_provider(provider: str) -> Finder:
    """Find the top-level ``context_providers`` entries equal to ``provider``."""

    def find(manifest: Mapping[str, Any]) -> list[str]:
        entries = manifest.get("context_providers")
        if not isinstance(entries, list):
            return []
        return [
            f"context_providers[{index}]"
            for index, entry in enumerate(entries)
            if entry == provider
        ]

    return find


# --- The single feature list ----------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ForbiddenFeature:
    """A feature a Composer draft must not use.

    Attributes:
        id: Stable identifier. A unit test pins the list to six ids.
        label: What the Turn_Context shows.
        reason: What a rejection says about why.
        find: Returns the manifest paths where the feature occurs.
    """

    id: str
    label: str
    reason: str
    find: Finder


_MCP_REASON: Final = (
    "It needs a secrets grant and the security gate, "
    "which a Composer launch cannot supply."
)

FORBIDDEN_FEATURES: Final[tuple[ForbiddenFeature, ...]] = (
    ForbiddenFeature(
        "exec_grant",
        "the exec tool grant",
        "The Composer cannot run workflows that execute commands.",
        find_step_grant("exec"),
    ),
    ForbiddenFeature(
        "network_grant",
        "the network tool grant",
        "Network egress is off for every Composer workflow.",
        find_step_grant("network"),
    ),
    ForbiddenFeature(
        "secrets_grant",
        "a secrets grant",
        "A Composer launch cannot supply secrets.",
        find_step_grant("secrets"),
    ),
    ForbiddenFeature(
        "mcp_filesystem",
        "the filesystem MCP server",
        _MCP_REASON,
        find_mcp_server("filesystem"),
    ),
    ForbiddenFeature(
        "mcp_postgres",
        "the postgres MCP server",
        _MCP_REASON,
        find_mcp_server("postgres"),
    ),
    ForbiddenFeature(
        "previous_run",
        "the previous_run context provider",
        "A Composer launch has no source run to read.",
        find_context_provider("previous_run"),
    ),
)


# --- The check ------------------------------------------------------------------------


def _shown(value: str) -> str:
    """Return ``value`` when it looks like an identifier, else a placeholder."""
    return value if _SAFE_ID.match(value) else _UNSHOWN_ID


def _listed(ids: Iterable[str]) -> str:
    ordered = sorted(set(ids))
    return ", ".join(ordered) if ordered else "none"


def _check_forbidden(manifest: Mapping[str, Any]) -> list[GateIssue]:
    return [
        GateIssue(
            "forbidden_feature",
            path,
            f"Not allowed ({feature.id}): {feature.label}. {feature.reason}",
        )
        for feature in FORBIDDEN_FEATURES
        for path in feature.find(manifest)
    ]


def _check_agent(
    agent: Any, path: str, allowed_agent_ids: frozenset[str], *, allow_self: bool
) -> GateIssue | None:
    if not isinstance(agent, str):
        return None  # a missing or malformed agent is the save check's finding
    if agent == _CUSTOM_AGENT or agent in allowed_agent_ids:
        return None
    if allow_self and agent == _SELF_AGENT:
        return None
    return GateIssue(
        "agent_allow_list",
        path,
        f"Agent '{_shown(agent)}' is not allowed in a Composer workflow. "
        f"Use '{_CUSTOM_AGENT}' or one of: {_listed(allowed_agent_ids)}.",
    )


def _check_model_policy(
    policy: Any, path: str, step_models: Mapping[str, ModelEntry]
) -> list[GateIssue]:
    if not isinstance(policy, Mapping):
        return []
    issues: list[GateIssue] = []
    allowed = _listed(step_models)

    primary = policy.get("model")
    if isinstance(primary, str) and primary not in step_models:
        issues.append(
            GateIssue(
                "step_model",
                f"{path}.model",
                f"Model '{_shown(primary)}' is not on the step model list. "
                f"Allowed model ids: {allowed}.",
            )
        )

    fallback = policy.get("fallback")
    if isinstance(fallback, list):
        issues.extend(
            GateIssue(
                "step_model",
                f"{path}.fallback[{index}]",
                f"Fallback model '{_shown(model_id)}' is not on the step model list. "
                f"Allowed model ids: {allowed}.",
            )
            for index, model_id in enumerate(fallback)
            if isinstance(model_id, str) and model_id not in step_models
        )

    effort = policy.get("effort")
    entry = step_models.get(primary) if isinstance(primary, str) else None
    if isinstance(effort, str) and entry is not None:
        levels = entry.reasoning.levels
        if effort not in levels:
            allowed_efforts = (
                f"Allowed efforts: {', '.join(levels)}."
                if levels
                else "This model takes no effort setting."
            )
            issues.append(
                GateIssue(
                    "effort",
                    f"{path}.effort",
                    f"Effort '{_shown(effort)}' is not supported by model "
                    f"'{entry.id}'. {allowed_efforts}",
                )
            )
    return issues


def check(
    manifest: Mapping[str, Any],
    *,
    step_models: Iterable[ModelEntry],
    allowed_agent_ids: Iterable[str],
) -> list[GateIssue]:
    """Apply the Builder_Rules to ``manifest`` and return every violation.

    Args:
        manifest: The parsed draft manifest.
        step_models: The user's Step_List entries (tier-filtered). A model id
            not among them is rejected, and the issue names these ids.
        allowed_agent_ids: Agent ids a step may use besides ``custom-agent``
            (``allowed_custom_agent_ids("custom")``).

    Returns:
        The issues in a fixed order: forbidden features (in list order), then
        the workflow-level model, then each step in walk order. Empty when the
        draft follows the rules. Messages hold identifiers only, never prompt
        text.
    """
    models = {entry.id: entry for entry in step_models}
    agents = frozenset(allowed_agent_ids)

    issues = _check_forbidden(manifest)
    issues.extend(_check_model_policy(manifest.get("model"), "model", models))
    for path, step in iter_steps(manifest):
        issue = _check_agent(
            step.get("agent"), f"{path}.agent", agents, allow_self=False
        )
        if issue is not None:
            issues.append(issue)
        subagents = step.get("subagents")
        if isinstance(subagents, Mapping):
            worker = _check_agent(
                subagents.get("agent"),
                f"{path}.subagents.agent",
                agents,
                allow_self=True,
            )
            if worker is not None:
                issues.append(worker)
        issues.extend(_check_model_policy(step.get("model"), f"{path}.model", models))
    return issues
