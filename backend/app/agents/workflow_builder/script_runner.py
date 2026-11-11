"""Script runner for the workflow builder: command parsing and path mapping.

``run_skill_script`` takes the command line exactly as the builder skill writes
it, for example ``python /skills/velocity-workflow-creator/scripts/catalog_lookup.py
overview --trust user``. This module turns that string into either a
:class:`ParsedCommand` that is safe to run, or a :class:`Refusal` that carries
the reason and the allowed alternative for the model (Req 35.12).

Parsing is pure: no subprocess, no clock, no network. The only filesystem
access is ``Path.resolve()`` inside :func:`map_path`, which is what makes the
containment test hold for symlinks. Running the subprocess
(:func:`execute`) always starts from a :class:`ParsedCommand`, and
:func:`build_script_tool` wraps both steps into the ``run_skill_script`` tool.

Execution (design sections 3.4.5 to 3.4.7): the script runs as
``sys.executable -B -s -X utf8 <script> <args>`` with the session sandbox as
working directory, stdin closed, stdout and stderr merged and an allow-list
environment (:func:`script_env`). A module-level semaphore bounds concurrent
scripts, a timeout and a cancel kill the process and wait for it, and the
call's temp folder is removed in ``finally``. The tool result keeps a head and
a tail of the output (:func:`read_capped`) and stays within
``BUILDER_SCRIPT_OUTPUT_CAP_CHARS``. The agent layer does not import
``app.api``: the telemetry sink, the result callback and the process spawner
are injected through :class:`ScriptContext`.

The command is never given to a shell. A small tokenizer splits it, keeps
backslashes (so Windows paths survive) and refuses shell syntax (Req 34.2,
34.3). The script and its arguments are then checked against
:data:`~app.agents.workflow_builder.script_policy.POLICY`, which is data; an
option the policy does not list is refused by name, so the check fails closed.

Pending decision this module assumes (design proposal G-18): shell operator
characters inside quotes are literal argument text.

See design sections 3.4.2 and 3.4.3.
"""

from __future__ import annotations

import asyncio
import codecs
import logging
import os
import posixpath
import re
import shutil
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Final, Protocol
from uuid import uuid4

from langchain_core.tools import BaseTool, InjectedToolCallId, tool

from app.agents.workflow_builder.events import (
    CheckResultEvent,
    CheckSource,
    CheckVerdict,
    TargetTrust,
    ToolFinishStatus,
)
from app.agents.workflow_builder.ports import GatePort, GateResult, TurnPort
from app.agents.workflow_builder.sandbox import BuilderSandbox
from app.agents.workflow_builder.script_policy import (
    BUILDER_SKILL_ID,
    EXPORTS_DIR,
    HELP_OPTIONS,
    SLOT_REFUSALS,
    OptionSpec,
    PathSlotKind,
    ScriptRule,
    get_rule,
    unknown_script_message,
)
from app.agents.workflow_builder.stages import DryRunStarted
from app.core.config import settings

__all__ = [
    "SCRIPT_ENV_NAMES",
    "SCRIPT_SEMAPHORE",
    "OutputCapture",
    "ParsedCommand",
    "ProcessLike",
    "ProcessSpawner",
    "Refusal",
    "Roots",
    "ScriptContext",
    "ScriptResult",
    "StreamLike",
    "build_script_tool",
    "execute",
    "map_path",
    "parse_command",
    "read_capped",
    "run_command",
    "script_env",
    "spawn_process",
]

logger = logging.getLogger("app.agents.workflow_builder.script_runner")

_SCRIPTS_DIR_NAME: Final = "scripts"
_EXPORTS_FOLDER_NAME: Final = EXPORTS_DIR.strip("/")
_SKILLS_FOLDER_NAME: Final = "skills"
_SKILL_PLACEHOLDER_PREFIX: Final = "<skill>/"
# Where the skill folder sits in the repository, relative to ``backend/``.
_SKILL_REPO_PATH: Final = "app/agents/workflow_builder/skills"
_OPERATOR_CHARS: Final = ";|&<>"
_MAX_ECHO_CHARS: Final = 200

_PYTHON_LAUNCHER: Final = re.compile(r"python(?:3(?:\.\d+)?)?")
_PY_VERSION_OPTION: Final = re.compile(r"-3(?:\.\d+)?")

_NOT_A_PATH: Final = "This value is not used as a path."
_CHAINING_HINT: Final = (
    "Run one script per call, without chaining, pipes, redirects or substitution."
)
_LAUNCHER_HINT: Final = (
    "Start the command with python, for example "
    "python <skill>/scripts/catalog_lookup.py overview --trust user."
)
_INTERPRETER_OPTION_HINT: Final = (
    "Interpreter options such as -c and -m are not supported. "
    "Run a script from the skill, for example "
    "python <skill>/scripts/catalog_lookup.py overview --trust user."
)


@dataclass(frozen=True)
class Roots:
    """The two folders a command may touch.

    Attributes:
        sandbox: Root of the calling session's sandbox. Relative paths and
            absolute paths such as ``/workflows/a.workflow.json`` resolve
            against it, and it is the subprocess's working directory.
        skill: The skill folder (``workflow_builder/skills/<skill id>``).
    """

    sandbox: Path
    skill: Path


@dataclass(frozen=True)
class Refusal:
    """A command or path that must not run.

    Attributes:
        reason: The reason and the allowed alternative. It is returned to the
            model verbatim as the tool result (Req 35.12).
    """

    reason: str


@dataclass(frozen=True)
class ParsedCommand:
    """A command that passed parsing and the allow-list.

    Attributes:
        command: The command string as the model wrote it.
        skill_id: Id of the builder skill whose policy accepted it.
        rule: The policy row of the script.
        script: Resolved path of the script inside ``<skill>/scripts/``.
        args: Arguments for the subprocess, in order. Path values are replaced
            by their resolved absolute paths. A discarded ``--compiler DIR``
            pair is not included.
        subcommand: The ``catalog_lookup.py`` subcommand, otherwise ``None``.
        is_help: True when the call asked for ``-h`` or ``--help``.
        trust: The last ``--trust`` value, or ``None``.
        manifest_path: Resolved path of the first ``sandbox_read`` argument
            (the manifest of ``validate_manifest.py`` or ``export_manifest.py``),
            or ``None``.
        compiler_dry_run: True when ``--compiler`` was given on a script whose
            policy intercepts it and the call is not a help call. The server
            then runs the dry run; the subprocess runs without the option.
    """

    command: str
    skill_id: str
    rule: ScriptRule
    script: Path
    args: tuple[str, ...]
    subcommand: str | None = None
    is_help: bool = False
    trust: str | None = None
    manifest_path: Path | None = None
    compiler_dry_run: bool = False


def _clip(text: str) -> str:
    """Return ``text`` shortened for echoing in a refusal."""
    if len(text) <= _MAX_ECHO_CHARS:
        return repr(text)
    return repr(text[:_MAX_ECHO_CHARS]) + "..."


# --- Tokenizer ----------------------------------------------------------------


def _operator_at(command: str, index: int) -> str:
    """Return the shell operator that starts at ``index`` (one or two characters)."""
    first = command[index]
    pair = command[index : index + 2]
    if pair in {"&&", "||"}:
        return pair
    return first


def _tokenize(command: str) -> list[str] | Refusal:
    """Split ``command`` into arguments without a shell.

    Unquoted whitespace separates tokens and matching single or double quotes
    are removed. Backslash is an ordinary character. Unquoted ``&&``, ``||``,
    ``;``, ``|``, ``&``, ``<``, ``>``, backtick, ``$(``, a newline or a NUL are
    refused; the same characters inside quotes are literal (G-18).
    """
    if "\x00" in command:
        return Refusal("The command contains a NUL character. " + _CHAINING_HINT)
    tokens: list[str] = []
    buffer: list[str] = []
    in_token = False
    quote: str | None = None
    index = 0
    while index < len(command):
        char = command[index]
        if quote is not None:
            if char == quote:
                quote = None
            else:
                buffer.append(char)
        elif char in {"'", '"'}:
            quote = char
            in_token = True
        elif char in {"\n", "\r"}:
            return Refusal("A newline ends the command. " + _CHAINING_HINT)
        elif char == "`" or command.startswith("$(", index):
            operator = "`" if char == "`" else "$("
            return Refusal(
                f"Shell syntax ({operator}) is not supported. " + _CHAINING_HINT
            )
        elif char in _OPERATOR_CHARS:
            operator = _operator_at(command, index)
            return Refusal(
                f"Shell syntax ({operator}) is not supported. " + _CHAINING_HINT
            )
        elif char.isspace():
            if in_token:
                tokens.append("".join(buffer))
                buffer.clear()
                in_token = False
        else:
            buffer.append(char)
            in_token = True
        index += 1
    if quote is not None:
        return Refusal(f"The command has an unclosed {quote} quote.")
    if in_token:
        tokens.append("".join(buffer))
    return tokens


# --- Path mapping -------------------------------------------------------------


def _skill_prefixes(skill_id: str) -> tuple[str, ...]:
    """Return the spellings that name the deployed skill folder (Req 34.6).

    Besides the virtual ``/skills/<id>/`` and the ``<skill>/`` placeholder, the
    repository paths the skill's own docs show are accepted, from ``backend/``
    and from the repository root, so a command copied from them still runs.
    """
    repo_relative = f"{_SKILL_REPO_PATH}/{skill_id}/"
    return (
        f"/{_SKILLS_FOLDER_NAME}/{skill_id}/",
        _SKILL_PLACEHOLDER_PREFIX,
        repo_relative,
        f"./{repo_relative}",
        f"backend/{repo_relative}",
        f"./backend/{repo_relative}",
    )


def _split_skill_prefix(path: str, skill_id: str) -> str | None:
    """Return the part of ``path`` after a skill prefix, or ``None`` if there is none."""
    for prefix in _skill_prefixes(skill_id):
        if path.startswith(prefix):
            return path[len(prefix) :]
        if path == prefix.rstrip("/"):
            return ""
    return None


def _has_unsafe_segment(relative: str) -> bool:
    """Return True for a segment Windows would read differently from its text.

    Win32 drops trailing dots and spaces, so ``".. "`` or ``"..."`` could act
    as ``".."``. Only the exact names ``.`` and ``..`` are accepted with a dot.
    """
    for segment in relative.split("/"):
        if segment in {"", ".", ".."}:
            continue
        if segment.endswith((" ", ".")):
            return True
    return False


def map_path(
    raw: str,
    slot: PathSlotKind,
    roots: Roots,
    *,
    skill_id: str = BUILDER_SKILL_ID,
) -> Path | Refusal:
    """Map one path argument to a resolved path that the slot allows.

    Backslashes become ``/``. A path that starts with a skill prefix is relative
    to the deployed skill folder; every other path, absolute or relative, is
    relative to the sandbox root. ``.`` and ``..`` are normalised, the result is
    resolved (so symlinks are followed) and must lie inside the root the slot
    allows (Req 34.6, 34.7, 34.8, 35.4).

    Args:
        raw: The path as the model wrote it.
        slot: What the argument may point at.
        roots: The sandbox and the deployed skill folder.
        skill_id: Id of the skill whose prefixes are recognised.

    Returns:
        The resolved path, or a :class:`Refusal` for a path outside the allowed
        root, a drive or stream spelling, an empty path, or an ``ignored`` slot.
    """
    refusal = Refusal(
        f"{_clip(raw)} is outside the allowed folder. {SLOT_REFUSALS.get(slot, _NOT_A_PATH)}"
    )
    if slot is PathSlotKind.IGNORED or not raw or "\x00" in raw:
        return refusal
    normalised = raw.replace("\\", "/")
    skill_relative = _split_skill_prefix(normalised, skill_id)
    from_skill = skill_relative is not None
    relative = skill_relative if skill_relative is not None else normalised.lstrip("/")
    if ":" in relative or _has_unsafe_segment(relative):
        return refusal
    relative = posixpath.normpath(relative)

    sandbox = roots.sandbox.resolve()
    skill = roots.skill.resolve()
    base = skill if from_skill else sandbox
    try:
        resolved = (base / relative).resolve()
    except (OSError, RuntimeError, ValueError):
        return refusal

    match slot:
        case PathSlotKind.SCRIPT:
            allowed = from_skill and resolved.is_relative_to(skill / _SCRIPTS_DIR_NAME)
        case PathSlotKind.SANDBOX_READ:
            allowed = (
                not from_skill
                and resolved.is_relative_to(sandbox)
                and not _is_virtual_skills_path(resolved, sandbox)
            )
        case PathSlotKind.EXPORT_WRITE:
            exports = sandbox / _EXPORTS_FOLDER_NAME
            allowed = (
                not from_skill
                and resolved.is_relative_to(exports)
                and resolved != exports
            )
        case _:
            allowed = False
    return resolved if allowed else refusal


def _is_virtual_skills_path(resolved: Path, sandbox: Path) -> bool:
    """Return True when ``resolved`` is under the sandbox's ``/skills/`` folder."""
    parts = resolved.relative_to(sandbox).parts
    return bool(parts) and parts[0].lower() == _SKILLS_FOLDER_NAME


# --- Argument parsing ---------------------------------------------------------


OptionTable = dict[str, OptionSpec]
"""Alias used in signatures: option name to its spec."""


@dataclass
class _ArgState:
    """What the argument scan collected."""

    out_args: list[str] = field(default_factory=lambda: list[str]())
    positionals: list[str] = field(default_factory=lambda: list[str]())
    counts: dict[str, int] = field(default_factory=lambda: dict[str, int]())
    is_help: bool = False
    trust: str | None = None
    manifest_path: Path | None = None
    compiler_seen: bool = False


def _is_option_token(token: str) -> bool:
    """Return True when ``token`` reads as an option (``-x``, ``--x`` or ``--x=y``)."""
    return len(token) > 1 and token.startswith("-")


def _split_option(token: str) -> tuple[str, str | None]:
    """Split ``--name=value`` into its name and inline value."""
    if token.startswith("--") and "=" in token:
        name, _, value = token.partition("=")
        return name, value
    return token, None


def _unknown_option_refusal(name: str, rule: ScriptRule, options: set[str]) -> Refusal:
    """Return the refusal for an option that is not in the policy, by name."""
    reason = rule.refusal_for(name)
    if reason is not None:
        return Refusal(reason)
    allowed = ", ".join(sorted(options | HELP_OPTIONS))
    return Refusal(
        f"Option {_clip(name)} is not allowed for {rule.script}. Allowed options: {allowed}."
    )


def _take_option(
    token: str,
    following: str | None,
    rule: ScriptRule,
    options: OptionTable,
    roots: Roots,
    skill_id: str,
    state: _ArgState,
) -> int | Refusal:
    """Handle one option token; return how many tokens it used, or a refusal."""
    name, inline = _split_option(token)
    if name in HELP_OPTIONS:
        if inline is not None:
            return Refusal(f"Option {name} takes no value.")
        state.is_help = True
        state.out_args.append(name)
        return 1
    refused = rule.refusal_for(name)
    if refused is not None:
        return Refusal(refused)
    spec = options.get(name)
    if spec is None:
        return _unknown_option_refusal(name, rule, set(options))
    state.counts[name] = state.counts.get(name, 0) + 1
    if not spec.takes_value:
        if inline is not None:
            return Refusal(f"Option {name} takes no value.")
        state.out_args.append(name)
        return 1
    used = 1
    value = inline
    if value is None:
        if following is None or _is_option_token(following):
            return Refusal(
                f"Option {name} needs a value. "
                f"Write {name}=VALUE if the value starts with a dash."
            )
        value = following
        used = 2
    refusal = _store_value(name, value, spec, roots, skill_id, state)
    return refusal if refusal is not None else used


def _store_value(
    name: str,
    value: str,
    spec: OptionSpec,
    roots: Roots,
    skill_id: str,
    state: _ArgState,
) -> Refusal | None:
    """Record an option value, mapping it when the option's slot is a path."""
    if name == "--trust":
        state.trust = value
    if spec.slot is PathSlotKind.IGNORED:
        state.compiler_seen = state.compiler_seen or name == "--compiler"
        return None
    if spec.slot is not None:
        mapped = map_path(value, spec.slot, roots, skill_id=skill_id)
        if isinstance(mapped, Refusal):
            return mapped
        state.out_args.extend((name, str(mapped)))
        return None
    state.out_args.extend((name, value))
    return None


def _take_positional(
    token: str,
    slots: tuple[PathSlotKind | None, ...] | None,
    roots: Roots,
    skill_id: str,
    state: _ArgState,
) -> Refusal | None:
    """Record one positional argument, mapping it when its slot is a path."""
    index = len(state.positionals)
    state.positionals.append(token)
    slot = slots[index] if slots is not None and index < len(slots) else None
    if slot is None:
        state.out_args.append(token)
        return None
    mapped = map_path(token, slot, roots, skill_id=skill_id)
    if isinstance(mapped, Refusal):
        return mapped
    if slot is PathSlotKind.SANDBOX_READ and state.manifest_path is None:
        state.manifest_path = mapped
    state.out_args.append(str(mapped))
    return None


def _scan_arguments(
    tokens: list[str],
    rule: ScriptRule,
    options: OptionTable,
    slots: tuple[PathSlotKind | None, ...] | None,
    roots: Roots,
    skill_id: str,
    state: _ArgState,
) -> Refusal | None:
    """Scan options and positionals into ``state``; return a refusal on the first problem."""
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token == "--":
            return Refusal("The -- separator is not supported.")
        if _is_option_token(token):
            following = tokens[index + 1] if index + 1 < len(tokens) else None
            used = _take_option(token, following, rule, options, roots, skill_id, state)
            if isinstance(used, Refusal):
                return used
            index += used
            continue
        refusal = _take_positional(token, slots, roots, skill_id, state)
        if refusal is not None:
            return refusal
        index += 1
    return None


def _arity_refusal(
    label: str, count: int, bounds: tuple[int, int | None]
) -> Refusal | None:
    """Return a refusal when ``count`` positionals are outside ``bounds``."""
    low, high = bounds
    if count >= low and (high is None or count <= high):
        return None
    if high is None:
        expected = f"at least {low}"
    elif low == high:
        expected = f"exactly {low}"
    else:
        expected = f"{low} to {high}"
    return Refusal(f"{label} takes {expected} argument(s) here, got {count}.")


def _check_required(rule: ScriptRule, state: _ArgState) -> Refusal | None:
    """Apply ``required_any`` and ``exactly_one_of``; both are skipped for help calls."""
    if rule.required_any and not any(state.counts.get(o, 0) for o in rule.required_any):
        return Refusal(rule.required_reason)
    if rule.exactly_one_of:
        total = sum(state.counts.get(o, 0) for o in rule.exactly_one_of)
        if total != 1:
            return Refusal(rule.required_reason)
    return None


def _parse_with_subcommand(
    rest: list[str], rule: ScriptRule, roots: Roots, skill_id: str, state: _ArgState
) -> tuple[str | None, Refusal | None]:
    """Parse the arguments of a script that has subcommands (``catalog_lookup.py``)."""
    subcommands = rule.subcommands or {}
    index = 0
    while index < len(rest) and rest[index] in HELP_OPTIONS:
        state.is_help = True
        state.out_args.append(rest[index])
        index += 1
    if index == len(rest):
        if state.is_help:
            return None, None
        names = ", ".join(sorted(subcommands))
        return None, Refusal(f"{rule.script} needs a subcommand: {names}.")
    name = rest[index]
    if _is_option_token(name):
        refused = rule.refusal_for(_split_option(name)[0])
        return None, Refusal(
            refused or f"Name a subcommand before option {_clip(name)}."
        )
    options = subcommands.get(name)
    if options is None:
        names = ", ".join(sorted(subcommands))
        return None, Refusal(
            f"Unknown subcommand {_clip(name)} for {rule.script}. Allowed: {names}."
        )
    state.out_args.append(name)
    refusal = _scan_arguments(
        rest[index + 1 :], rule, dict(options), None, roots, skill_id, state
    )
    if refusal is not None:
        return name, refusal
    if not state.is_help:
        bounds = rule.subcommand_arity.get(name, (0, None))
        refusal = _arity_refusal(
            f"{rule.script} {name}", len(state.positionals), bounds
        )
    return name, refusal


def _parse_arguments(
    rest: list[str], rule: ScriptRule, roots: Roots, skill_id: str
) -> tuple[_ArgState, str | None] | Refusal:
    """Check the arguments after the script against its rule (design 3.4.4)."""
    state = _ArgState()
    subcommand: str | None = None
    if rule.subcommands is not None:
        subcommand, refusal = _parse_with_subcommand(rest, rule, roots, skill_id, state)
    else:
        refusal = _scan_arguments(
            rest,
            rule,
            dict(rule.options),
            rule.positional_slots,
            roots,
            skill_id,
            state,
        )
        if refusal is None and not state.is_help:
            count = len(rule.positional_slots)
            refusal = _check_required(rule, state) or _arity_refusal(
                rule.script, len(state.positionals), (count, count)
            )
    if refusal is not None:
        return refusal
    return state, subcommand


# --- Command parsing ----------------------------------------------------------


def _script_index(tokens: list[str]) -> int | Refusal:
    """Return the index of the script token after an optional launcher (Req 34.4)."""
    first = tokens[0]
    index = 0
    if _PYTHON_LAUNCHER.fullmatch(first):
        index = 1
    elif first == "py":
        index = 2 if len(tokens) > 1 and _PY_VERSION_OPTION.fullmatch(tokens[1]) else 1
    elif (
        first == "uv"
        and len(tokens) > 2
        and tokens[1] == "run"
        and _PYTHON_LAUNCHER.fullmatch(tokens[2])
    ):
        index = 3
    if index >= len(tokens):
        return Refusal("Name a script after the launcher. " + _LAUNCHER_HINT)
    if _is_option_token(tokens[index]):
        return Refusal(_INTERPRETER_OPTION_HINT)
    if index == 0 and not tokens[0].lower().endswith(".py"):
        return Refusal(_LAUNCHER_HINT)
    return index


def _resolve_script(
    token: str, roots: Roots, skill_id: str
) -> tuple[Path, ScriptRule] | Refusal:
    """Map the script token into ``<skill>/scripts/`` and find its policy row."""
    refusal = Refusal(
        f"{unknown_script_message(skill_id)} {SLOT_REFUSALS[PathSlotKind.SCRIPT]}"
    )
    mapped = map_path(token, PathSlotKind.SCRIPT, roots, skill_id=skill_id)
    if isinstance(mapped, Refusal):
        return refusal
    rule = get_rule(skill_id, mapped.name)
    scripts_dir = roots.skill.resolve() / _SCRIPTS_DIR_NAME
    if rule is None or mapped.parent != scripts_dir:
        return refusal
    return mapped, rule


def parse_command(
    command: str,
    roots: Roots,
    *,
    skill_id: str = BUILDER_SKILL_ID,
) -> ParsedCommand | Refusal:
    """Parse one ``run_skill_script`` command against the allow-list.

    Steps (design 3.4.2): tokenise without a shell and refuse shell syntax;
    drop one optional launcher (``python``, ``python3``, ``python3.N``,
    ``py -3``, ``py -3.N``, ``uv run python``) and refuse interpreter options
    such as ``-c`` and ``-m``; map the script into ``<skill>/scripts/`` and find
    its policy row; check every argument against that row. Path arguments are
    mapped by their slot and replaced by resolved paths in ``args``. A help call
    (``-h`` or ``--help``) is exempt from required options and argument counts.
    No subprocess is started here.

    Args:
        command: The command line as the model wrote it.
        roots: The calling session's sandbox and the deployed skill folder.
        skill_id: Id of the builder skill whose policy applies.

    Returns:
        A :class:`ParsedCommand` that is safe to run, or a :class:`Refusal`
        holding the reason and the allowed alternative.
    """
    tokens = _tokenize(command)
    if isinstance(tokens, Refusal):
        return tokens
    if not tokens:
        return Refusal("The command is empty. " + _LAUNCHER_HINT)
    script_at = _script_index(tokens)
    if isinstance(script_at, Refusal):
        return script_at
    resolved = _resolve_script(tokens[script_at], roots, skill_id)
    if isinstance(resolved, Refusal):
        return resolved
    script, rule = resolved
    parsed = _parse_arguments(tokens[script_at + 1 :], rule, roots, skill_id)
    if isinstance(parsed, Refusal):
        return parsed
    state, subcommand = parsed
    return ParsedCommand(
        command=command,
        skill_id=skill_id,
        rule=rule,
        script=script,
        args=tuple(state.out_args),
        subcommand=subcommand,
        is_help=state.is_help,
        trust=state.trust,
        manifest_path=state.manifest_path,
        compiler_dry_run=(
            rule.intercept == "compiler_dry_run"
            and state.compiler_seen
            and not state.is_help
        ),
    )


# --- Execution: environment, process, output ----------------------------------

_VALIDATOR_SCRIPT: Final = "validate_manifest.py"
_INTERPRETER_FLAGS: Final = ("-B", "-s", "-X", "utf8")
_HEAD_CHARS: Final = 60_000
_TAIL_CHARS: Final = 15_000
_READ_CHUNK_BYTES: Final = 65_536
_MAX_COMMAND_ECHO: Final = 2_000
_MAX_DRY_RUN_ISSUES: Final = 20
_MAX_ISSUE_CHARS: Final = 400
_STOPPED_SUMMARY: Final = "stopped with the turn"
_NO_EXIT_CODE: Final = "none"
_UNSUPPORTED_TRUST: Final = "Only user or db trust applies to Composer workflows."
_DRY_RUN_FAILED: Final = (
    "The platform check could not run. Try again or call propose_draft."
)

_VALIDATOR_LINE: Final = re.compile(
    r"^(VALID|INVALID): (\d+) error\(s\), (\d+) warning\(s\)", re.MULTILINE
)
_JSON_VALID: Final = re.compile(r'^ {2}"valid":\s*(true|false)', re.MULTILINE)
_JSON_COUNTS: Final = re.compile(
    r'^ {2}"counts":\s*\{\s*"errors":\s*(\d+),\s*"warnings":\s*(\d+)', re.MULTILINE
)

SCRIPT_ENV_NAMES: Final[frozenset[str]] = frozenset(
    {
        "PATH",
        "PYTHONDONTWRITEBYTECODE",
        "PYTHONIOENCODING",
        "PYTHONUTF8",
        "PYTHONNOUSERSITE",
        "TMP",
        "TEMP",
        "TMPDIR",
        "HOME",
        "USERPROFILE",
        "LANG",
        "SYSTEMROOT",
        "PATHEXT",
    }
)
"""Every variable name :func:`script_env` can set. Nothing else reaches a script."""

SCRIPT_SEMAPHORE: Final = asyncio.Semaphore(settings.BUILDER_MAX_CONCURRENT_SCRIPTS)
"""Bounds concurrent script processes in this API process (Req 36.6).

One process serves one host, so this is the per-host bound. A call beyond the
limit waits for a slot [pending G-18].
"""


def script_env(tmp: Path) -> dict[str, str]:
    """Build the environment of a script subprocess from an allow-list.

    The mapping starts empty and gains only the names in
    :data:`SCRIPT_ENV_NAMES`, so a secret added to the server's environment later
    never reaches a script (Req 36.3, 36.4).

    Args:
        tmp: The call's temp folder. ``TMP``, ``TEMP``, ``TMPDIR``, ``HOME`` and
            ``USERPROFILE`` point at it.

    Returns:
        The environment for ``create_subprocess_exec``.
    """
    interpreter_dir = str(Path(sys.executable).parent)
    env = {
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
        "PYTHONNOUSERSITE": "1",
        "TMP": str(tmp),
        "TEMP": str(tmp),
        "TMPDIR": str(tmp),
        "HOME": str(tmp),
        "USERPROFILE": str(tmp),
        "LANG": "C.UTF-8",
    }
    if sys.platform == "win32":
        system_root = os.environ.get("SYSTEMROOT", r"C:\Windows")
        env["SYSTEMROOT"] = system_root
        env["PATHEXT"] = os.environ.get("PATHEXT", ".COM;.EXE;.BAT;.CMD")
        env["PATH"] = os.pathsep.join(
            (interpreter_dir, str(Path(system_root) / "System32"), system_root)
        )
    else:
        env["PATH"] = os.pathsep.join((interpreter_dir, os.defpath))
    return env


class StreamLike(Protocol):
    """The part of a subprocess pipe that :func:`read_capped` reads."""

    async def read(self, n: int = -1, /) -> bytes:
        """Return up to ``n`` bytes, or ``b""`` at the end."""
        ...


class ProcessLike(Protocol):
    """The part of a subprocess that :func:`execute` uses."""

    @property
    def stdout(self) -> StreamLike | None:
        """The merged stdout and stderr pipe."""
        ...

    @property
    def returncode(self) -> int | None:
        """The exit code, or ``None`` while the process runs."""
        ...

    def kill(self) -> None:
        """Kill the process."""
        ...

    async def wait(self) -> int:
        """Wait for the process to exit and return its exit code."""
        ...


class ProcessSpawner(Protocol):
    """Starts a script subprocess. Tests inject a fake (tasks 12.5 to 12.10)."""

    async def __call__(
        self, argv: Sequence[str], *, cwd: Path, env: Mapping[str, str]
    ) -> ProcessLike:
        """Start ``argv`` in ``cwd`` with exactly ``env``.

        Raises:
            OSError: The process could not be started.
        """
        ...


async def spawn_process(
    argv: Sequence[str], *, cwd: Path, env: Mapping[str, str]
) -> ProcessLike:
    """Start a subprocess with stdin closed and stderr merged into stdout."""
    return await asyncio.create_subprocess_exec(
        *argv,
        cwd=cwd,
        env=dict(env),
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )


def _cut_note(removed: int) -> str:
    """Return the note that marks ``removed`` characters left out of the output."""
    return f"\n[... {removed} characters cut ...]\n"


class OutputCapture:
    """The first ``head_chars`` and the last ``tail_chars`` of a stream.

    Text fills the head first. Later text goes to a rolling tail, and what
    rolls out of the tail is only counted (:attr:`dropped`). The verdict is read
    from the uncut tail (:attr:`verdict_text`) before :meth:`render` cuts
    anything (design 3.4.6).
    """

    def __init__(
        self, head_chars: int = _HEAD_CHARS, tail_chars: int = _TAIL_CHARS
    ) -> None:
        """Create an empty capture.

        Args:
            head_chars: Characters kept from the start.
            tail_chars: Characters kept from the end.
        """
        self.head_chars = head_chars
        self.tail_chars = tail_chars
        self.head = ""
        self.tail = ""
        self.dropped = 0

    @property
    def total(self) -> int:
        """Number of characters fed so far."""
        return len(self.head) + len(self.tail) + self.dropped

    @property
    def verdict_text(self) -> str:
        """The last ``tail_chars`` characters, contiguous and uncut."""
        if self.dropped:
            return self.tail
        return (self.head + self.tail)[-self.tail_chars :]

    def feed(self, text: str) -> None:
        """Add ``text`` to the capture."""
        room = self.head_chars - len(self.head)
        if room > 0:
            self.head += text[:room]
            text = text[room:]
        if not text:
            return
        self.tail += text
        excess = len(self.tail) - self.tail_chars
        if excess > 0:
            self.dropped += excess
            self.tail = self.tail[excess:]

    def render(self, budget: int) -> str:
        """Return the output within ``budget`` characters, with a cut note if cut.

        With the default sizes and a large budget the result is the 60,000
        character head, the cut note and the 15,000 character tail. A smaller
        budget keeps the same 4 to 1 split (Req 36.7). When the whole output sits
        in the head (nothing rolled out of the tail), the tail is taken from the end
        of that output, so a cut result still ends with the last lines.
        """
        budget = max(budget, 0)
        if not self.dropped and len(self.head) + len(self.tail) <= budget:
            return self.head + self.tail
        available = max(budget - len(_cut_note(self.total)), 0)
        tail_source = self.verdict_text
        head_keep = min(len(self.head), available * 4 // 5)
        tail_keep = min(len(tail_source), available - head_keep)
        head_keep = min(len(self.head), available - tail_keep)
        removed = self.total - head_keep - tail_keep
        tail_text = tail_source[len(tail_source) - tail_keep :] if tail_keep else ""
        if removed <= 0:
            return self.head[:head_keep] + tail_text
        return self.head[:head_keep] + _cut_note(removed) + tail_text


async def read_capped(
    stream: StreamLike,
    *,
    capture: OutputCapture | None = None,
    head_chars: int = _HEAD_CHARS,
    tail_chars: int = _TAIL_CHARS,
) -> OutputCapture:
    """Read ``stream`` to its end, keeping a head and a tail (Req 36.7).

    Memory stays bounded however much the script prints. Invalid UTF-8 becomes
    the replacement character.

    Args:
        stream: The merged stdout and stderr pipe.
        capture: Capture to fill. The caller passes one to keep the partial
            output when a timeout interrupts the read.
        head_chars: Head size, used when ``capture`` is not given.
        tail_chars: Tail size, used when ``capture`` is not given.

    Returns:
        The capture.
    """
    out = capture if capture is not None else OutputCapture(head_chars, tail_chars)
    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
    while chunk := await stream.read(_READ_CHUNK_BYTES):
        out.feed(decoder.decode(chunk))
    out.feed(decoder.decode(b"", final=True))
    return out


def _parse_verdict(
    capture: OutputCapture, *, json_mode: bool
) -> tuple[CheckVerdict, int, int]:
    """Read the validator verdict, error count and warning count (Req 36.11).

    Without ``--json`` it is the last ``VALID:`` or ``INVALID:`` line in the
    uncut tail. With ``--json`` it is the ``valid`` field and the ``counts`` of
    the report, which sit at its start. No match gives ``unknown`` (G-18).
    """
    if json_mode:
        valid = _JSON_VALID.search(capture.head)
        counts = _JSON_COUNTS.search(capture.head)
        if valid is None:
            return "unknown", 0, 0
        verdict: CheckVerdict = "valid" if valid.group(1) == "true" else "invalid"
        if counts is None:
            return verdict, 0, 0
        return verdict, int(counts.group(1)), int(counts.group(2))
    lines = _VALIDATOR_LINE.findall(capture.verdict_text)
    if not lines:
        return "unknown", 0, 0
    word, errors, warnings = lines[-1]
    return ("valid" if word == "VALID" else "invalid"), int(errors), int(warnings)


# --- Execution: context and result --------------------------------------------


@dataclass(frozen=True)
class ScriptResult:
    """What one ``run_skill_script`` call came to.

    Attributes:
        script: Script file name, or ``"refused"`` for a call that did not parse.
        status: The ``tool_finished`` status (design 3.4.6).
        text: The tool result returned to the model.
        exit_code: The exit code the model sees, or ``None`` when there is none.
        duration_ms: Wall time of the call, including the wait for a slot.
        summary: Fixed-template summary for ``tool_finished``, at most 280
            characters and never built from the output.
        verdict: The validator verdict, or ``None`` for other scripts.
        errors: Validator error count.
        warnings: Validator warning count.
    """

    script: str
    status: ToolFinishStatus
    text: str
    exit_code: int | None
    duration_ms: int
    summary: str
    verdict: CheckVerdict | None = None
    errors: int = 0
    warnings: int = 0


ResultCallback = Callable[[str, ScriptResult], None]
"""Called with the tool-call id and the result when a call ends, however it ends."""

MetricSink = Callable[[str, float, int | None, bool], None]
"""``(script, duration_seconds, exit_code, refused)``. The API layer binds
``telemetry.emit_script_call`` with the session and turn ids (Req 44.4)."""


@dataclass(frozen=True)
class ScriptContext:
    """Everything one turn's ``run_skill_script`` needs.

    The model cannot name another session's sandbox, because the sandbox is not
    a tool parameter.

    Attributes:
        sandbox: The session sandbox. Its folder is the subprocess's working
            directory.
        skill_root: The skill folder (``workflow_builder/skills/<skill id>``).
        gate: The Server_Gate, used by the ``--compiler`` dry run.
        turn: The live turn: event publishing, stage signals and the stop flag.
        skill_id: Id of the builder skill whose policy applies.
        semaphore: Bounds concurrent scripts. Defaults to :data:`SCRIPT_SEMAPHORE`.
        spawn: Starts the subprocess. Tests inject a fake.
        call_id: The tool-call id; names the call's temp folder. The tool fills
            it in per call.
        timeout_seconds: Per-call timeout. ``None`` reads
            ``BUILDER_SCRIPT_TIMEOUT_SECONDS``.
        output_cap_chars: Cap on the whole tool result. ``None`` reads
            ``BUILDER_SCRIPT_OUTPUT_CAP_CHARS``.
        stopped_by_turn_cap: True when the turn stopped because of its time or
            tool-call cap; a stopped call is then ``timed_out``, otherwise
            ``error``.
        on_finished: Optional callback for the observer middleware.
        on_metric: Optional telemetry sink.
        clock: Monotonic clock in seconds.
    """

    sandbox: BuilderSandbox
    skill_root: Path
    gate: GatePort
    turn: TurnPort
    skill_id: str = BUILDER_SKILL_ID
    semaphore: asyncio.Semaphore = field(default_factory=lambda: SCRIPT_SEMAPHORE)
    spawn: ProcessSpawner = spawn_process
    call_id: str = ""
    timeout_seconds: float | None = None
    output_cap_chars: int | None = None
    stopped_by_turn_cap: Callable[[], bool] = field(default=lambda: False)
    on_finished: ResultCallback | None = None
    on_metric: MetricSink | None = None
    clock: Callable[[], float] = field(default=time.monotonic)

    @property
    def roots(self) -> Roots:
        """The sandbox and skill folders a command may touch."""
        return Roots(sandbox=self.sandbox.path, skill=self.skill_root)


@dataclass
class _Outcome:
    """What the subprocess step produced."""

    capture: OutputCapture = field(default_factory=OutputCapture)
    exit_code: int | None = None
    timed_out: bool = False
    stopped: bool = False
    start_failed: bool = False


# --- Execution: running the process -------------------------------------------


async def _reap(process: ProcessLike) -> None:
    """Kill ``process`` if it still runs and wait for it to exit."""
    if process.returncode is None:
        try:
            process.kill()
        except ProcessLookupError:
            logger.debug("script process already gone before kill")
    await process.wait()


async def _drain(process: ProcessLike, capture: OutputCapture) -> int:
    """Read the process output to its end, then wait for its exit code."""
    if process.stdout is not None:
        await read_capped(process.stdout, capture=capture)
    return await process.wait()


async def _run_process(
    parsed: ParsedCommand, ctx: ScriptContext, call_id: str
) -> _Outcome:
    """Run the script once; kill and reap it on timeout or cancel; clean up."""
    outcome = _Outcome()
    if ctx.turn.stopping:
        outcome.stopped = True
        return outcome
    timeout = (
        ctx.timeout_seconds
        if ctx.timeout_seconds is not None
        else settings.BUILDER_SCRIPT_TIMEOUT_SECONDS
    )
    tmp: Path | None = None
    process: ProcessLike | None = None
    try:
        tmp = ctx.sandbox.call_temp_dir(call_id)
        argv = [sys.executable, *_INTERPRETER_FLAGS, str(parsed.script), *parsed.args]
        process = await ctx.spawn(argv, cwd=ctx.sandbox.path, env=script_env(tmp))
        try:
            async with asyncio.timeout(timeout):
                outcome.exit_code = await _drain(process, outcome.capture)
        except TimeoutError:
            outcome.timed_out = True
    except (OSError, ValueError):
        # ValueError covers SandboxPathError. Neither text is shown to the model.
        logger.warning(
            "script could not start script=%s", parsed.script.name, exc_info=True
        )
        outcome.start_failed = True
    finally:
        if process is not None and process.returncode is None:
            await _reap(process)
        if tmp is not None:
            shutil.rmtree(tmp, ignore_errors=True)
    return outcome


# --- Execution: result assembly -----------------------------------------------


def _clip_command(command: str) -> str:
    """Return the command as echoed in the result header."""
    if len(command) <= _MAX_COMMAND_ECHO:
        return command
    return command[:_MAX_COMMAND_ECHO] + "..."


def _compose(
    command: str, exit_label: str, body: OutputCapture, trailer: str, cap: int
) -> str:
    """Build ``$ <command>`` / ``exit code: <n>`` / output, within ``cap`` characters."""
    header = f"$ {_clip_command(command)}\nexit code: {exit_label}\n"
    extra = ("\n" + trailer) if trailer else ""
    text = body.render(cap - len(header) - len(extra))
    return (header + text + extra)[:cap]


def _label(parsed: ParsedCommand) -> str:
    """Return ``script`` or ``script subcommand`` for a summary."""
    name = parsed.script.name
    return f"{name} {parsed.subcommand}" if parsed.subcommand else name


def _status_for(parsed: ParsedCommand, exit_code: int) -> ToolFinishStatus:
    """Map an exit code to a status: the validator's 0 and 1 are both ``ok``."""
    if exit_code == 0:
        return "ok"
    if exit_code == 1 and parsed.script.name == _VALIDATOR_SCRIPT:
        return "ok"
    return "error"


def _clip_issue(text: str) -> str:
    """Shorten one dry-run issue line."""
    one_line = " ".join(text.split())
    if len(one_line) <= _MAX_ISSUE_CHARS:
        return one_line
    return one_line[:_MAX_ISSUE_CHARS] + "..."


def _dry_run_section(trust: str, result: GateResult | None, note: str) -> str:
    """Format the dry-run result appended to the validator output (design 3.4.7)."""
    lines = [f"--- platform check (dry run, trust {trust}) ---"]
    if result is None:
        lines.append(note)
    elif result.accepted:
        lines.append("PASS: the platform accepts this manifest.")
    else:
        lines.append(f"FAIL: {len(result.issues)} issue(s)")
        for number, issue in enumerate(result.issues[:_MAX_DRY_RUN_ISSUES], start=1):
            where = f" {issue.path}" if issue.path else ""
            lines.append(
                _clip_issue(f"{number}. [{issue.rule}]{where}: {issue.message}")
            )
        hidden = len(result.issues) - _MAX_DRY_RUN_ISSUES
        if hidden > 0:
            lines.append(f"... and {hidden} more issue(s)")
    return "\n".join(lines)


async def _publish_check(
    ctx: ScriptContext,
    source: CheckSource,
    verdict: CheckVerdict,
    errors: int,
    warnings: int,
) -> None:
    """Publish one ``check_result`` event for the turn."""
    await ctx.turn.publish(
        CheckResultEvent(
            ts=datetime.now(UTC),
            turn_id=ctx.turn.turn_id,
            seq=1,  # placeholder: the port assigns the real seq (TurnPort.publish)
            source=source,
            verdict=verdict,
            errors=errors,
            warnings=warnings,
            attempt=None,
            attempts_left=None,
        )
    )


async def _dry_run(
    parsed: ParsedCommand, ctx: ScriptContext
) -> tuple[str, CheckVerdict, int]:
    """Run the Server_Gate dry run; return its section, verdict and issue count.

    ``file`` and ``builtin`` trust are answered without calling the gate. A gate
    failure gives an ``unknown`` verdict and a generic message.
    """
    trust = parsed.trust or "user"
    if trust not in ("user", "db") or parsed.manifest_path is None:
        return _dry_run_section(trust, None, _UNSUPPORTED_TRUST), "unknown", 0
    await ctx.turn.signal_stage(DryRunStarted())
    requested: TargetTrust = "db" if trust == "db" else "user"
    try:
        result = await ctx.gate.dry_run(parsed.manifest_path, requested_trust=requested)
    except (
        Exception
    ):  # the gate is an injected adapter; its failure must not end the turn
        logger.exception("dry run failed script=%s", parsed.script.name)
        return _dry_run_section(trust, None, _DRY_RUN_FAILED), "unknown", 0
    verdict: CheckVerdict = "valid" if result.accepted else "invalid"
    return _dry_run_section(trust, result, ""), verdict, len(result.issues)


def _refused_result(
    ctx: ScriptContext, refusal: Refusal, started: float
) -> ScriptResult:
    """Build the result of a call the policy refused; the reason is the tool result."""
    return ScriptResult(
        script="refused",
        status="refused",
        text=refusal.reason,
        exit_code=None,
        duration_ms=_elapsed_ms(ctx, started),
        summary="Refused by the script policy.",
    )


def _stopped_result(
    parsed: ParsedCommand, ctx: ScriptContext, started: float
) -> ScriptResult:
    """Build the result of a call stopped by cancel, a turn cap or a shutdown."""
    status: ToolFinishStatus = "timed_out" if ctx.stopped_by_turn_cap() else "error"
    text = (
        f"$ {_clip_command(parsed.command)}\nexit code: {_NO_EXIT_CODE}\n"
        "The script did not finish because the turn stopped."
    )
    return ScriptResult(
        script=parsed.script.name,
        status=status,
        text=text,
        exit_code=None,
        duration_ms=_elapsed_ms(ctx, started),
        summary=_STOPPED_SUMMARY,
    )


def _elapsed_ms(ctx: ScriptContext, started: float) -> int:
    """Milliseconds since ``started`` on the context clock."""
    return max(int((ctx.clock() - started) * 1000), 0)


async def _finish(
    parsed: ParsedCommand, ctx: ScriptContext, outcome: _Outcome, started: float
) -> ScriptResult:
    """Turn the process outcome into a result; publish checks; run the dry run."""
    name = parsed.script.name
    cap = (
        ctx.output_cap_chars
        if ctx.output_cap_chars is not None
        else settings.BUILDER_SCRIPT_OUTPUT_CAP_CHARS
    )
    if outcome.stopped:
        return _stopped_result(parsed, ctx, started)
    if outcome.start_failed:
        text = (
            f"$ {_clip_command(parsed.command)}\nexit code: {_NO_EXIT_CODE}\n"
            "The script could not be started."
        )
        return ScriptResult(
            name, "error", text, None, _elapsed_ms(ctx, started),
            "The script could not be started.",
        )  # fmt: skip
    if outcome.timed_out:
        timeout = (
            ctx.timeout_seconds
            if ctx.timeout_seconds is not None
            else settings.BUILDER_SCRIPT_TIMEOUT_SECONDS
        )
        trailer = f"[timed out after {timeout:g} s; the script was stopped]"
        text = _compose(parsed.command, _NO_EXIT_CODE, outcome.capture, trailer, cap)
        return ScriptResult(
            name, "timed_out", text, None, _elapsed_ms(ctx, started),
            f"{_label(parsed)} timed out after {timeout:g} s.",
        )  # fmt: skip

    exit_code = outcome.exit_code if outcome.exit_code is not None else -1
    verdict: CheckVerdict | None = None
    errors = warnings = 0
    trailer = ""
    if name == _VALIDATOR_SCRIPT and not parsed.is_help:
        verdict, errors, warnings = _parse_verdict(
            outcome.capture, json_mode="--json" in parsed.args
        )
        await _publish_check(ctx, "skill_validator", verdict, errors, warnings)
        if parsed.compiler_dry_run and _status_for(parsed, exit_code) == "ok":
            trailer, dry_verdict, dry_errors = await _dry_run(parsed, ctx)
            await _publish_check(ctx, "platform_dry_run", dry_verdict, dry_errors, 0)
            if exit_code == 0 and dry_verdict != "valid":
                exit_code = 1
    text = _compose(parsed.command, str(exit_code), outcome.capture, trailer, cap)
    status = _status_for(parsed, exit_code)
    summary = f"{_label(parsed)} exited with code {exit_code}."
    return ScriptResult(
        name, status, text, exit_code, _elapsed_ms(ctx, started), summary,
        verdict, errors, warnings,
    )  # fmt: skip


def _notify(ctx: ScriptContext, call_id: str, result: ScriptResult) -> None:
    """Report a finished call to the callback and the telemetry sink."""
    if ctx.on_finished is not None:
        ctx.on_finished(call_id, result)
    if ctx.on_metric is not None:
        ctx.on_metric(
            result.script,
            result.duration_ms / 1000,
            result.exit_code,
            result.status == "refused",
        )


async def execute(parsed: ParsedCommand, ctx: ScriptContext) -> ScriptResult:
    """Run a parsed command and return its result (design 3.4.5).

    The call waits for a semaphore slot, runs ``sys.executable -B -s -X utf8
    <script> <args>`` in the session sandbox, kills and reaps the process on
    timeout or cancel, and removes the call's temp folder in ``finally``. For a
    ``--compiler`` call it also runs the Server_Gate dry run (design 3.4.7). A
    cancel is re-raised after the process is gone.

    Args:
        parsed: A command that passed :func:`parse_command`.
        ctx: The turn's script context. ``ctx.call_id`` names the temp folder.

    Returns:
        The result, with the text to hand back to the model.
    """
    started = ctx.clock()
    call_id = ctx.call_id or uuid4().hex
    try:
        async with ctx.semaphore:
            outcome = await _run_process(parsed, ctx, call_id)
        result = await _finish(parsed, ctx, outcome, started)
    except asyncio.CancelledError:
        _notify(ctx, call_id, _stopped_result(parsed, ctx, started))
        raise
    _notify(ctx, call_id, result)
    return result


async def run_command(command: str, ctx: ScriptContext) -> ScriptResult:
    """Parse ``command`` against the allow-list and run it.

    A refusal is returned as a ``refused`` result whose text is the reason and
    the allowed alternative (Req 35.12). No process starts for a refusal.
    """
    started = ctx.clock()
    parsed = parse_command(command, ctx.roots, skill_id=ctx.skill_id)
    if isinstance(parsed, Refusal):
        result = _refused_result(ctx, parsed, started)
        _notify(ctx, ctx.call_id, result)
        return result
    return await execute(parsed, ctx)


def build_script_tool(ctx: ScriptContext) -> BaseTool:
    """Return the turn's ``run_skill_script`` tool, a closure over ``ctx``.

    The tool takes a command string only. The sandbox, the skill folder, the
    gate and the turn come from ``ctx``, so the model cannot choose them. The
    tool-call id is injected by LangChain and names the call's temp folder.

    Args:
        ctx: The turn's script context.

    Returns:
        The LangChain tool.
    """

    @tool
    async def run_skill_script(
        command: str, tool_call_id: Annotated[str, InjectedToolCallId]
    ) -> str:
        """Run one velocity-workflow-creator script, written exactly as the skill writes it.

        For example: python /skills/velocity-workflow-creator/scripts/catalog_lookup.py overview --trust user
        Returns the exit code and the combined output.
        """
        result = await run_command(command, replace(ctx, call_id=tool_call_id))
        return result.text

    return run_skill_script
