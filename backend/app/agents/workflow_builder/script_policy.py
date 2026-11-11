"""Allow-list policy for the workflow builder's script runner, encoded as data.

This module is pure data and small lookup helpers: no I/O, no clock, no
subprocess, no filesystem. It states which scripts of a builder skill may run,
which options each accepts, which options are refused and why, and which
argument slots hold paths (and so need containment checks). Parsing a command
line against these rules is ``script_runner.parse_command``; running the
subprocess is ``script_runner.execute``. See design section 3.4.4.

The policy fails closed: an option that is neither listed in a rule's
``options`` (or a subcommand's options) nor in the ``-h`` / ``--help`` pair is
unknown and is refused by name by the parser. ``refused`` only adds a specific
reason and alternative for options the model is likely to try.

Rules are keyed by skill id (Q-47), so another builder skill adds its own table
to :data:`POLICY` without touching the parser.

Pending decisions this module assumes (design proposals):

* G-02: ``export_manifest.py`` writes only under ``/exports/`` in the sandbox.
* G-18: ``selftest.py`` takes no options; ``export_manifest.py`` takes exactly
  one output option; ``refresh_catalog.py --check`` refuses its path options.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Final, Literal

__all__ = [
    "BUILDER_SKILL_ID",
    "EXPORTS_DIR",
    "HELP_OPTIONS",
    "POLICY",
    "SLOT_REFUSALS",
    "OptionSpec",
    "PathSlotKind",
    "ScriptRule",
    "allowed_script_names",
    "get_rule",
    "unknown_script_message",
]

BUILDER_SKILL_ID: Final = "velocity-workflow-creator"
"""Id of the only builder skill today; the key of its table in :data:`POLICY`."""

EXPORTS_DIR: Final = "/exports/"
"""Sandbox folder the only writing script (``export_manifest.py``) may write to."""

HELP_OPTIONS: Final[frozenset[str]] = frozenset({"-h", "--help"})
"""Accepted by every allowed script, alone or after a subcommand (Req 35.10)."""


class PathSlotKind(StrEnum):
    """What a path-valued argument may point at (design section 3.4.3)."""

    SCRIPT = "script"
    """Argument 0: must map into ``<skill root>/scripts/``."""

    SANDBOX_READ = "sandbox_read"
    """A file inside the sandbox, excluding the deployed ``/skills/`` folder."""

    EXPORT_WRITE = "export_write"
    """An output file under the sandbox's ``/exports/`` folder."""

    IGNORED = "ignored"
    """The value is discarded and never used as a path (``--compiler DIR``)."""


@dataclass(frozen=True)
class OptionSpec:
    """One option a script accepts.

    Attributes:
        takes_value: True when the option consumes the next token as its value.
        slot: The path slot the value fills, or ``None`` for a plain value or
            for a flag that takes no value.
    """

    takes_value: bool
    slot: PathSlotKind | None = None


@dataclass(frozen=True)
class ScriptRule:
    """The allow-list entry for one script.

    Attributes:
        script: File name inside the skill's ``scripts/`` folder.
        subcommands: Allowed subcommands and the options each accepts, or
            ``None`` for a script without subcommands (only ``catalog_lookup``).
        options: Options accepted when the script has no subcommands. Empty
            for scripts that take no options.
        positional_slots: One entry per positional argument of a script
            without subcommands, in order. ``None`` marks a plain value.
        subcommand_arity: For scripts with subcommands, the allowed positional
            count per subcommand as ``(minimum, maximum)``; ``maximum`` is
            ``None`` when unbounded.
        required_any: Options of which at least one must be present unless the
            call is a help call (for example ``{"--check"}``).
        exactly_one_of: Options of which exactly one must be present.
        required_reason: Reason and alternative returned when ``required_any``
            or ``exactly_one_of`` is not satisfied.
        refused: Option -> reason and allowed alternative, returned verbatim as
            the tool result when the option is used (Req 35.12).
        intercept: Marks a script whose call is partly handled by the server
            instead of the subprocess (the ``--compiler`` dry run).
    """

    script: str
    subcommands: Mapping[str, Mapping[str, OptionSpec]] | None
    options: Mapping[str, OptionSpec]
    positional_slots: tuple[PathSlotKind | None, ...]
    subcommand_arity: Mapping[str, tuple[int, int | None]] = MappingProxyType({})
    required_any: frozenset[str] = frozenset()
    exactly_one_of: frozenset[str] = frozenset()
    required_reason: str = ""
    refused: Mapping[str, str] = MappingProxyType({})
    intercept: Literal["compiler_dry_run"] | None = None

    def refusal_for(self, option: str) -> str | None:
        """Return the reason and alternative for a refused option, if any."""
        return self.refused.get(option)


# --- Refusal texts (Req 35.2, 35.6, 35.8, 35.12) ----------------------------

_OWN_FILES_REASON: Final = (
    "The script always reads the skill's own catalog and schema. "
    "Run it without --catalog or --schema."
)
_SELFTEST_COMPILER_REASON: Final = (
    "CI runs the compiler self-test. Run selftest.py with no options, "
    "or use validate_manifest.py <manifest> --compiler for a platform check of your manifest."
)
_REFRESH_REASON: Final = (
    "The catalog is refreshed in CI. Use catalog_lookup.py to read it. "
    "The only allowed call is refresh_catalog.py --check."
)
_SCHEMA_SYNC_REASON: Final = (
    "The schema never changes at run time. Use --check. "
    "The only allowed call is schema_sync.py --check."
)
_EXPORT_REQUIRED_REASON: Final = (
    "export_manifest.py needs exactly one output option: --yaml OUT, --save-payload OUT or "
    f"--run-payload OUT, with OUT under {EXPORTS_DIR} in the sandbox."
)

SLOT_REFUSALS: Final[Mapping[PathSlotKind, str]] = MappingProxyType(
    {
        PathSlotKind.SANDBOX_READ: (
            "The manifest must be a file in your sandbox, for example "
            "/workflows/my.workflow.json. The skill's own files cannot be used as input."
        ),
        PathSlotKind.EXPORT_WRITE: (
            f"Write exports under {EXPORTS_DIR}. The canvas saves and runs the workflow."
        ),
        PathSlotKind.SCRIPT: (
            "Run a script from the skill's scripts folder, for example "
            f"/skills/{BUILDER_SKILL_ID}/scripts/catalog_lookup.py."
        ),
    }
)
"""Reason and alternative returned when a path argument fails containment (Req 35.4)."""


# --- Rule tables -------------------------------------------------------------

_FLAG: Final = OptionSpec(takes_value=False)
_VALUE: Final = OptionSpec(takes_value=True)
_TRUST: Final = {"--trust": _VALUE}
_OWN_FILES_REFUSED: Final[Mapping[str, str]] = MappingProxyType(
    {"--catalog": _OWN_FILES_REASON, "--schema": _OWN_FILES_REASON}
)


def _options(options: Mapping[str, OptionSpec]) -> Mapping[str, OptionSpec]:
    """Return a read-only copy of an option table."""
    return MappingProxyType(dict(options))


_CATALOG_LOOKUP: Final = ScriptRule(
    script="catalog_lookup.py",
    subcommands=MappingProxyType(
        {
            "overview": _options(_TRUST),
            "models": _options({"--eu": _FLAG}),
            "icons": _options({}),
            "kind": _options(_TRUST),
            "agents": _options({"--all": _FLAG}),
            "agent": _options({}),
            "skills": _options({}),
            "workflows": _options({}),
            "mcp": _options({}),
            "trust": _options({}),
            "field": _options({"--full": _FLAG}),
            "search": _options({}),
            "example": _options({}),
        }
    ),
    options=_options({}),
    positional_slots=(),
    subcommand_arity=MappingProxyType(
        {
            "overview": (0, 0),
            "models": (0, 0),
            "icons": (0, 0),
            "kind": (1, 1),
            "agents": (0, 0),
            "agent": (1, 1),
            "skills": (0, None),
            "workflows": (0, 0),
            "mcp": (0, 0),
            "trust": (1, 1),
            "field": (0, 1),
            "search": (1, None),
            "example": (0, 2),
        }
    ),
    refused=_OWN_FILES_REFUSED,
)

_VALIDATE_MANIFEST: Final = ScriptRule(
    script="validate_manifest.py",
    subcommands=None,
    options=_options(
        {
            "--trust": _VALUE,
            "--summary": _FLAG,
            "--json": _FLAG,
            "--strict": _FLAG,
            "--quiet-info": _FLAG,
            "--compiler": OptionSpec(takes_value=True, slot=PathSlotKind.IGNORED),
        }
    ),
    positional_slots=(PathSlotKind.SANDBOX_READ,),
    refused=_OWN_FILES_REFUSED,
    intercept="compiler_dry_run",
)

_SELFTEST: Final = ScriptRule(
    script="selftest.py",
    subcommands=None,
    options=_options({}),
    positional_slots=(),
    refused=MappingProxyType(
        {"--compiler": _SELFTEST_COMPILER_REASON, "--catalog": _OWN_FILES_REASON}
    ),
)

_REFRESH_CATALOG: Final = ScriptRule(
    script="refresh_catalog.py",
    subcommands=None,
    options=_options({"--check": _FLAG}),
    positional_slots=(),
    required_any=frozenset({"--check"}),
    required_reason=_REFRESH_REASON,
    refused=MappingProxyType(
        dict.fromkeys(
            (
                "--source",
                "--api",
                "--render",
                "--token",
                "--out-json",
                "--out-md",
                "--schema",
                "--no-schema",
            ),
            _REFRESH_REASON,
        )
    ),
)

_SCHEMA_SYNC: Final = ScriptRule(
    script="schema_sync.py",
    subcommands=None,
    options=_options({"--check": _FLAG}),
    positional_slots=(),
    required_any=frozenset({"--check"}),
    required_reason=_SCHEMA_SYNC_REASON,
    refused=MappingProxyType(
        {"--catalog": _SCHEMA_SYNC_REASON, "--schema": _SCHEMA_SYNC_REASON}
    ),
)

_EXPORT_MANIFEST: Final = ScriptRule(
    script="export_manifest.py",
    subcommands=None,
    options=_options(
        {
            "--yaml": OptionSpec(takes_value=True, slot=PathSlotKind.EXPORT_WRITE),
            "--save-payload": OptionSpec(
                takes_value=True, slot=PathSlotKind.EXPORT_WRITE
            ),
            "--run-payload": OptionSpec(
                takes_value=True, slot=PathSlotKind.EXPORT_WRITE
            ),
            "--message": _VALUE,
            "--name": _VALUE,
        }
    ),
    positional_slots=(PathSlotKind.SANDBOX_READ,),
    exactly_one_of=frozenset({"--yaml", "--save-payload", "--run-payload"}),
    required_reason=_EXPORT_REQUIRED_REASON,
)

POLICY: Final[Mapping[str, Mapping[str, ScriptRule]]] = MappingProxyType(
    {
        BUILDER_SKILL_ID: MappingProxyType(
            {
                rule.script: rule
                for rule in (
                    _CATALOG_LOOKUP,
                    _VALIDATE_MANIFEST,
                    _SELFTEST,
                    _REFRESH_CATALOG,
                    _SCHEMA_SYNC,
                    _EXPORT_MANIFEST,
                )
            }
        )
    }
)
"""Allow-list rules keyed by skill id, then by script file name (design 3.4.4)."""


def get_rule(skill_id: str, script_name: str) -> ScriptRule | None:
    """Return the rule for a script of a skill, or ``None`` when not allowed.

    Args:
        skill_id: Id of the builder skill, a key of :data:`POLICY`.
        script_name: File name of the script, for example ``selftest.py``.
    """
    return POLICY.get(skill_id, MappingProxyType({})).get(script_name)


def allowed_script_names(skill_id: str) -> tuple[str, ...]:
    """Return the allowed script file names of a skill, sorted."""
    return tuple(sorted(POLICY.get(skill_id, MappingProxyType({}))))


def unknown_script_message(skill_id: str) -> str:
    """Return the refusal text for a call that names a script not in the policy."""
    names = ", ".join(allowed_script_names(skill_id))
    return f"Only these scripts can run: {names}."
