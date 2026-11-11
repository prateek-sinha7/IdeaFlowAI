"""Adherence record: what the Builder_Agent read and ran during one Turn.

The record shows which mandatory Skill files were read in full, whether the
``overview`` and ``example`` lookups ran, and whether the Skill_Validator ran
and what it returned (Req 28.10, Q-45 a). It is derived from the Turn's tool
calls only. The model is never asked to report it. The function is pure: no
I/O, no clock, no shared state. See design section 3.6.6 and D-02.

A mandatory file counts as *read in full* when the union of the line ranges
``[offset, offset + limit)`` of its successful ``read_file`` calls covers every
line of the file. Line counts come from the skill files on disk
(``skill_package.read_skill_facts``), so paged reads count. ``docs/catalog.md`` is
not tracked because a single read cannot return it whole (D-02).
"""

from __future__ import annotations

import posixpath
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Final, Literal

__all__ = [
    "DEFAULT_READ_LIMIT",
    "DEFAULT_READ_OFFSET",
    "DEFAULT_SKILL_ID",
    "MANDATORY_FILES",
    "AdherenceRecord",
    "ToolCall",
    "Verdict",
    "record",
]

Verdict = Literal["valid", "invalid", "unknown"]

DEFAULT_SKILL_ID: Final = "velocity-workflow-creator"

# Paths relative to the skill folder, in the order the skill asks for them.
MANDATORY_FILES: Final[tuple[str, ...]] = (
    "SKILL.md",
    "docs/problem-decomposition.md",
    "docs/quick-reference.md",
    "docs/prompt-writing.md",
)

# deepagents ``read_file`` defaults (``DEFAULT_READ_OFFSET`` and
# ``DEFAULT_READ_LIMIT`` in ``deepagents/middleware/filesystem.py``, pinned at
# 0.6.7). ``offset`` is a 0-based line index. A call that omits either
# argument reads with these values.
DEFAULT_READ_OFFSET: Final = 0
DEFAULT_READ_LIMIT: Final = 100

_SKILLS_PREFIX: Final = "/skills/"
_MANIFEST_SUFFIX: Final = ".workflow.json"
_WRITE_TOOLS: Final = frozenset({"write_file", "edit_file"})
_SCRIPT_TOOL: Final = "run_skill_script"
_LOOKUP_SCRIPT: Final = "catalog_lookup.py"
_VALIDATOR_SCRIPT: Final = "validate_manifest.py"


@dataclass(frozen=True, slots=True)
class ToolCall:
    """One finished tool call of a Turn, as the observer middleware sees it.

    Attributes:
        name: Tool name: ``read_file``, ``write_file``, ``edit_file`` or
            ``run_skill_script``. Other tools are ignored.
        ok: False when the call failed or was refused, for example a
            ``read_file`` on a missing path. Failed ``read_file`` and write
            calls count for nothing.
        path: Target path of ``read_file``, ``write_file`` and ``edit_file``,
            for example ``/skills/velocity-workflow-creator/SKILL.md``.
        offset: ``read_file`` start line (0-based). ``None`` means the
            deepagents default.
        limit: ``read_file`` line count. ``None`` means the deepagents default.
        script: Script file name for ``run_skill_script``, for example
            ``catalog_lookup.py``. A directory prefix is ignored.
        subcommand: First argument of the script, for example ``overview`` or
            ``example``.
        exit_code: Exit code of a script that ran to completion. ``None`` when
            the call was refused, timed out or was stopped before it exited.
        verdict: The ``validate_manifest.py`` verdict parsed by the script
            runner (design 3.4.6). ``None`` when none was parsed.
    """

    name: str
    ok: bool = True
    path: str | None = None
    offset: int | None = None
    limit: int | None = None
    script: str | None = None
    subcommand: str | None = None
    exit_code: int | None = None
    verdict: Verdict | None = None


@dataclass(frozen=True, slots=True)
class AdherenceRecord:
    """What a Turn read and ran, stored as JSON on the assistant message.

    Attributes:
        manifest_turn: The Turn wrote a ``*.workflow.json`` file.
        mandatory_read: For each mandatory Skill file (path relative to the
            skill folder), whether the Turn read it in full.
        overview_ran: ``catalog_lookup.py overview`` exited 0.
        example_ran: ``catalog_lookup.py example ...`` exited 0.
        validator_ran: ``validate_manifest.py`` ran to completion. An INVALID
            verdict still counts as a run.
        last_validator_verdict: Verdict of the last validator run, ``unknown``
            when it printed none, or ``None`` when the validator did not run.
    """

    manifest_turn: bool
    mandatory_read: dict[str, bool]
    overview_ran: bool
    example_ran: bool
    validator_ran: bool
    last_validator_verdict: Verdict | None

    def as_dict(self) -> dict[str, object]:
        """Return the record as a JSON-serialisable dict."""
        return {
            "manifest_turn": self.manifest_turn,
            "mandatory_read": dict(self.mandatory_read),
            "overview_ran": self.overview_ran,
            "example_ran": self.example_ran,
            "validator_ran": self.validator_ran,
            "last_validator_verdict": self.last_validator_verdict,
        }


def _skill_relative(path: str, skill_id: str) -> str | None:
    """Return ``path`` relative to the skill folder, or ``None`` if outside it.

    Backslashes, ``.``, ``..`` and repeated slashes are collapsed first, so
    ``/skills/x/docs/../SKILL.md`` maps to ``SKILL.md``.
    """
    normal = posixpath.normpath(path.replace("\\", "/"))
    prefix = f"{_SKILLS_PREFIX}{skill_id}/"
    if not normal.startswith(prefix):
        return None
    return normal[len(prefix) :]


def _read_range(call: ToolCall) -> tuple[int, int] | None:
    """Return the half-open line range ``[start, end)`` a read covered, or ``None``."""
    offset = DEFAULT_READ_OFFSET if call.offset is None else call.offset
    limit = DEFAULT_READ_LIMIT if call.limit is None else call.limit
    start = max(offset, 0)
    end = offset + limit
    if end <= start:
        return None
    return start, end


def _covers(ranges: Iterable[tuple[int, int]], line_count: int) -> bool:
    """True when the union of ``ranges`` covers lines ``0 .. line_count - 1``.

    An empty file (``line_count`` 0) counts as covered by any successful read.
    """
    reach = 0
    seen = False
    for start, end in sorted(ranges):
        seen = True
        if start > reach:
            break
        reach = max(reach, end)
    if line_count <= 0:
        return seen
    return reach >= line_count


def _is_exit_zero_lookup(call: ToolCall, subcommand: str) -> bool:
    """True for a finished ``catalog_lookup.py <subcommand>`` call with exit code 0."""
    return (
        call.name == _SCRIPT_TOOL
        and call.script is not None
        and posixpath.basename(call.script) == _LOOKUP_SCRIPT
        and call.subcommand == subcommand
        and call.exit_code == 0
    )


def _is_validator_run(call: ToolCall) -> bool:
    """True for a ``validate_manifest.py`` call that ran to completion."""
    return (
        call.name == _SCRIPT_TOOL
        and call.script is not None
        and posixpath.basename(call.script) == _VALIDATOR_SCRIPT
        and call.exit_code is not None
    )


def record(
    tool_calls: Iterable[ToolCall],
    line_counts: Mapping[str, int],
    *,
    skill_id: str = DEFAULT_SKILL_ID,
) -> AdherenceRecord:
    """Derive the adherence record of one Turn from its tool calls.

    Args:
        tool_calls: The Turn's finished tool calls, in the order they ended.
            The order decides which validator run is the last one.
        line_counts: ``{relative_path: line_count}`` for the skill, from
            ``skill_package.read_skill_facts().line_counts``. A mandatory file with no
            entry is never marked as read.
        skill_id: The skill whose files are tracked. ``read_file`` paths are
            matched under ``/skills/<skill_id>/``.

    Returns:
        The record. A mandatory file is marked read when the union of the
        ``[offset, offset + limit)`` ranges of its successful ``read_file``
        calls covers its line count.
    """
    ranges: dict[str, list[tuple[int, int]]] = {name: [] for name in MANDATORY_FILES}
    manifest_turn = False
    overview_ran = False
    example_ran = False
    validator_ran = False
    last_verdict: Verdict | None = None

    for call in tool_calls:
        if call.name == "read_file":
            if not call.ok or call.path is None:
                continue
            relative = _skill_relative(call.path, skill_id)
            line_range = _read_range(call)
            if relative in ranges and line_range is not None:
                ranges[relative].append(line_range)
        elif call.name in _WRITE_TOOLS:
            if call.ok and call.path is not None:
                manifest_turn = manifest_turn or posixpath.normpath(
                    call.path.replace("\\", "/")
                ).endswith(_MANIFEST_SUFFIX)
        elif call.name == _SCRIPT_TOOL:
            overview_ran = overview_ran or _is_exit_zero_lookup(call, "overview")
            example_ran = example_ran or _is_exit_zero_lookup(call, "example")
            if _is_validator_run(call):
                validator_ran = True
                last_verdict = call.verdict if call.verdict is not None else "unknown"

    mandatory_read = {
        name: name in line_counts and _covers(ranges[name], line_counts[name])
        for name in MANDATORY_FILES
    }
    return AdherenceRecord(
        manifest_turn=manifest_turn,
        mandatory_read=mandatory_read,
        overview_ran=overview_ran,
        example_ran=example_ran,
        validator_ran=validator_ran,
        last_validator_verdict=last_verdict,
    )
