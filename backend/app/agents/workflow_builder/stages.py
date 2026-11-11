"""Turn stages for the workflow builder, derived from the agent's actions.

The Turn_Runner never asks the model to report a stage (Req 39.1). It feeds
each observable action into :func:`derive_stage` as a *signal* and publishes a
``stage`` event only when the function returns a stage. The function is pure:
no I/O, no clock, no shared state. See design section 3.3.3.

Signal to stage table (Req 39.2 to 39.10):

=========================================================  ==============
Signal                                                     Stage
=========================================================  ==============
turn accepted                                              ``starting``
thinking while no tool call is running                     ``thinking``
``read_file`` on a path under ``/skills/``                 ``reading``
``catalog_lookup.py`` or a read tool                       ``looking_up``
``write_file`` / ``edit_file`` on ``*.workflow.json``      ``writing``
``validate_manifest.py``, ``selftest.py``,
``refresh_catalog.py --check``, ``schema_sync.py --check``  ``checking``
``propose_draft`` starts, or the dry run of ``--compiler``  ``platform_check``
the gate accepts a ``propose_draft`` draft                 ``applying``
text while no tool call is running                         ``responding``
=========================================================  ==============

Other tools (``ls``, ``glob``, ``grep``, ``write_todos``, ``export_manifest.py``
and help calls) do not change the stage.
"""

from __future__ import annotations

import posixpath
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

__all__ = [
    "READ_TOOL_NAMES",
    "STAGE_LABELS",
    "DryRunStarted",
    "GateAccepted",
    "Signal",
    "Stage",
    "TextDelta",
    "ThinkingDelta",
    "ToolStarted",
    "TurnAccepted",
    "derive_stage",
    "label_for",
]


class Stage(StrEnum):
    """What the Builder_Agent is doing, as shown to the user."""

    STARTING = "starting"
    THINKING = "thinking"
    READING = "reading"
    LOOKING_UP = "looking_up"
    WRITING = "writing"
    CHECKING = "checking"
    PLATFORM_CHECK = "platform_check"
    APPLYING = "applying"
    RESPONDING = "responding"


STAGE_LABELS: Final[dict[Stage, str]] = {
    Stage.STARTING: "Starting",
    Stage.THINKING: "Thinking",
    Stage.READING: "Reading the workflow guide",
    Stage.LOOKING_UP: "Looking up agents, models and examples",
    Stage.WRITING: "Writing the workflow",
    Stage.CHECKING: "Checking the workflow",
    Stage.PLATFORM_CHECK: "Checking with the platform",
    Stage.APPLYING: "Updating the canvas",
    Stage.RESPONDING: "Writing the reply",
}


def label_for(stage: Stage) -> str:
    """Return the plain-language label shown for ``stage``."""
    return STAGE_LABELS[stage]


# Placeholder read-tool names, pending the Q-18 tool list (design section 3.7).
READ_TOOL_NAMES: Final[frozenset[str]] = frozenset(
    {
        "list_my_agents",
        "list_my_skills",
        "list_my_workflow_names",
        "list_my_connectors",
        "list_handoff_targets",
        "get_builder_models",
    }
)

_SKILLS_PREFIX: Final = "/skills/"
_MANIFEST_SUFFIX: Final = ".workflow.json"
_WRITE_TOOLS: Final = frozenset({"write_file", "edit_file"})
_LOOKUP_SCRIPT: Final = "catalog_lookup.py"
_CHECK_SCRIPTS: Final = frozenset({"validate_manifest.py", "selftest.py"})
_CHECK_FLAG_SCRIPTS: Final = frozenset({"refresh_catalog.py", "schema_sync.py"})


@dataclass(frozen=True, slots=True)
class TurnAccepted:
    """A Turn was accepted; sent before the first model output (Req 39.2)."""


@dataclass(frozen=True, slots=True)
class ThinkingDelta:
    """Reasoning text arrived. ``tool_running`` is true while a tool call runs."""

    tool_running: bool = False


@dataclass(frozen=True, slots=True)
class TextDelta:
    """Assistant text arrived. ``tool_running`` is true while a tool call runs."""

    tool_running: bool = False


@dataclass(frozen=True, slots=True)
class ToolStarted:
    """A tool call started.

    Attributes:
        name: Tool name, for example ``read_file`` or ``run_skill_script``.
        path: Target path for ``read_file``, ``write_file`` and ``edit_file``.
        script: Script file name for ``run_skill_script``.
        subcommand: Subcommand of the script, if any (``catalog_lookup.py``).
        check: True when the script call carries ``--check``.
    """

    name: str
    path: str | None = None
    script: str | None = None
    subcommand: str | None = None
    check: bool = False


@dataclass(frozen=True, slots=True)
class DryRunStarted:
    """The dry run of an intercepted ``--compiler`` call started (Req 39.8)."""


@dataclass(frozen=True, slots=True)
class GateAccepted:
    """The Server_Gate accepted a draft submitted through ``propose_draft``."""


Signal = (
    TurnAccepted
    | ThinkingDelta
    | TextDelta
    | ToolStarted
    | DryRunStarted
    | GateAccepted
)


def _normalise(path: str) -> str:
    """Collapse ``.``, ``..`` and repeated slashes so prefix checks are reliable."""
    return posixpath.normpath(path.replace("\\", "/"))


def _stage_for_tool(tool: ToolStarted) -> Stage | None:
    """Map a tool start to its stage, or ``None`` for tools that do not change it."""
    name = tool.name
    path = tool.path
    if name == "read_file":
        if path is not None and (_normalise(path) + "/").startswith(_SKILLS_PREFIX):
            return Stage.READING
        return None
    if name in _WRITE_TOOLS:
        if path is not None and _normalise(path).endswith(_MANIFEST_SUFFIX):
            return Stage.WRITING
        return None
    if name == "propose_draft":
        return Stage.PLATFORM_CHECK
    if name in READ_TOOL_NAMES:
        return Stage.LOOKING_UP
    if name == "run_skill_script":
        script = tool.script
        if script is None:
            return None
        script = posixpath.basename(script)
        if script == _LOOKUP_SCRIPT:
            return Stage.LOOKING_UP
        if script in _CHECK_SCRIPTS:
            return Stage.CHECKING
        if script in _CHECK_FLAG_SCRIPTS and tool.check:
            return Stage.CHECKING
    return None


def _target_stage(signal: Signal) -> Stage | None:
    """Return the stage a signal maps to, ignoring the current stage."""
    match signal:
        case TurnAccepted():
            return Stage.STARTING
        case ThinkingDelta(tool_running=False):
            return Stage.THINKING
        case TextDelta(tool_running=False):
            return Stage.RESPONDING
        case ToolStarted():
            return _stage_for_tool(signal)
        case DryRunStarted():
            return Stage.PLATFORM_CHECK
        case GateAccepted():
            return Stage.APPLYING
        case _:
            return None


def derive_stage(signal: Signal, current: Stage | None) -> Stage | None:
    """Derive the stage change caused by ``signal``.

    Args:
        signal: The observed action.
        current: The stage the turn is in now, or ``None`` before the first one.

    Returns:
        The new stage, or ``None`` when the signal leaves the stage as it is.
        That covers tools outside the table, thinking or text during a tool
        call, and a signal whose stage equals ``current``, so a caller
        publishes a stage event exactly when the result is not ``None``.
    """
    target = _target_stage(signal)
    if target is None or target == current:
        return None
    return target
