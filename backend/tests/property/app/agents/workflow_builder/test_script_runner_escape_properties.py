"""Property tests for the script runner's containment.

Covers design Property 1 (task 12.6, Req 34.2, 34.3, 34.7, 34.8, 35.1 to 35.12,
27.9, 49.3): whatever string the model sends to ``run_skill_script``, the call is
either refused without starting a subprocess, or starts exactly one subprocess
whose script is one of the six allowed scripts, whose subcommand and options
the policy allows, and whose every path argument lies inside the sandbox
(``/exports/`` for write slots) or, for the script itself, inside the skill's
``scripts/`` folder.

Every call goes through :func:`run_command` with a :class:`FakeProcessFactory`,
so no subprocess starts. The policy tables are restated below and do not read
``POLICY``, so a wrong entry in the module is not copied into the oracle. The
tree under test (sandbox, skill folder, an "outside" folder and links that point
out of the sandbox) is built in a temp folder inside each example.

Symlinks need a privilege that Windows users often lack. On Windows a folder
link falls back to a junction; a link to a file has no fallback, so the
script-link property is skipped when file links are unavailable.
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import pytest
from hypothesis import event, given, settings
from hypothesis import strategies as st

from app.agents.workflow_builder.sandbox import BuilderSandbox
from app.agents.workflow_builder.script_policy import BUILDER_SKILL_ID
from app.agents.workflow_builder.script_runner import (
    ScriptContext,
    ScriptResult,
    run_command,
)
from tests.fakes.builder_gate import FakeGate
from tests.fakes.builder_turn import FakeTurnPort
from tests.fakes.process_factory import FakeProcessFactory

# --- Links --------------------------------------------------------------------


def _link(link: Path, target: Path) -> bool:
    """Make ``link`` point at ``target``; return False when the OS refuses.

    A symlink is tried first. On Windows a folder falls back to a junction,
    which resolves the same way and needs no privilege.
    """
    try:
        os.symlink(target, link, target_is_directory=target.is_dir())
    except (OSError, NotImplementedError):
        if sys.platform == "win32" and target.is_dir():
            import _winapi  # noqa: PLC0415, PLC2701  # Windows-only stdlib module

            try:
                _winapi.CreateJunction(str(target), str(link))
            except OSError:
                return False
            return True
        return False
    return True


def _probe_links() -> tuple[bool, bool]:
    """Return whether folder links and file links can be created here."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as raw:
        base = Path(raw)
        (base / "d").mkdir()
        (base / "f.txt").write_text("x", encoding="utf-8")
        return _link(base / "dl", base / "d"), _link(base / "fl", base / "f.txt")


DIR_LINKS_OK, FILE_LINKS_OK = _probe_links()

# Only a local Windows run may skip the link cases (creating a file symlink needs a
# privilege there). On CI and on every other platform a missing link fails the run,
# so the escape proof cannot disappear silently.
LINK_SKIP_ALLOWED = sys.platform == "win32" and not os.environ.get("CI")


# --- The tree under test ------------------------------------------------------

_SCRIPTS = frozenset(
    {
        "catalog_lookup.py",
        "validate_manifest.py",
        "selftest.py",
        "refresh_catalog.py",
        "schema_sync.py",
        "export_manifest.py",
    }
)
_MANIFEST = "/workflows/a.workflow.json"
_SKILL = BUILDER_SKILL_ID


@dataclass(frozen=True)
class Tree:
    """A sandbox, a skill folder and an outside folder in a temp directory.

    Attributes:
        box: The session sandbox.
        sandbox: Real path of the sandbox folder.
        skill: Real path of the skill folder (``scripts/`` inside it).
        outside: Real path of a folder that no path may reach.
    """

    box: BuilderSandbox
    sandbox: Path
    skill: Path
    outside: Path


def _build_tree(base: Path, *, link_script: str | None = None) -> Tree:
    """Create the tree under ``base`` and the links that point out of it.

    ``workflows/link_out`` and ``exports/link_out`` point outside,
    ``workflows/link_skill`` points into the skill folder and
    ``workflows/link_in`` points at a folder inside the sandbox. When
    ``link_script`` is set, ``scripts/<link_script>`` is a link to a file
    outside the skill folder.
    """
    base = base.resolve()
    outside = base / "outside"
    skill = base / "skill"
    outside.mkdir()
    (outside / "secret.json").write_text("{}", encoding="utf-8")
    (outside / "planted.py").write_text("print('planted')\n", encoding="utf-8")
    (skill / "scripts").mkdir(parents=True)
    (skill / "SKILL.md").write_text("# skill\n", encoding="utf-8")

    box = BuilderSandbox("user-1", "session-1", root=base / "root")
    box.ensure()
    (box.path / "workflows" / "a.workflow.json").write_text("{}", encoding="utf-8")
    _link(box.path / "workflows" / "link_out", outside)
    _link(box.path / "exports" / "link_out", outside)
    _link(box.path / "workflows" / "link_skill", skill)
    _link(box.path / "workflows" / "link_in", box.path / "workflows")
    if link_script is not None:
        _link(skill / "scripts" / link_script, outside / "planted.py")
    return Tree(box=box, sandbox=box.path, skill=skill, outside=outside)


def _run(tree: Tree, command: str) -> tuple[ScriptResult, FakeProcessFactory, FakeGate]:
    """Run ``command`` through the runner with a fake process and a fake gate."""
    factory = FakeProcessFactory()
    gate = FakeGate()
    ctx = ScriptContext(
        sandbox=tree.box,
        skill_root=tree.skill,
        gate=gate,
        turn=FakeTurnPort(),
        semaphore=asyncio.Semaphore(1),
        spawn=factory,
        call_id=uuid4().hex,
        timeout_seconds=5.0,
    )
    return asyncio.run(run_command(command, ctx)), factory, gate


# --- The oracle ---------------------------------------------------------------

_HELP = frozenset({"-h", "--help"})
# Per catalog_lookup.py subcommand: (options with a value, options without one).
_CATALOG: dict[str, tuple[frozenset[str], frozenset[str]]] = {
    "overview": (frozenset({"--trust"}), frozenset()),
    "models": (frozenset(), frozenset({"--eu"})),
    "icons": (frozenset(), frozenset()),
    "kind": (frozenset({"--trust"}), frozenset()),
    "agents": (frozenset(), frozenset({"--all"})),
    "agent": (frozenset(), frozenset()),
    "skills": (frozenset(), frozenset()),
    "workflows": (frozenset(), frozenset()),
    "mcp": (frozenset(), frozenset()),
    "trust": (frozenset(), frozenset()),
    "field": (frozenset(), frozenset({"--full"})),
    "search": (frozenset(), frozenset()),
    "example": (frozenset(), frozenset()),
}
_EXPORT_OPTIONS = frozenset({"--yaml", "--save-payload", "--run-payload"})
# Per other script: (options with a value, options without one).
_SCRIPT_OPTIONS: dict[str, tuple[frozenset[str], frozenset[str]]] = {
    "validate_manifest.py": (
        frozenset({"--trust"}),
        frozenset({"--summary", "--json", "--strict", "--quiet-info"}),
    ),
    "selftest.py": (frozenset(), frozenset()),
    "refresh_catalog.py": (frozenset(), frozenset({"--check"})),
    "schema_sync.py": (frozenset(), frozenset({"--check"})),
    "export_manifest.py": (
        _EXPORT_OPTIONS | {"--message", "--name"},
        frozenset(),
    ),
}
_MANIFEST_SCRIPTS = frozenset({"validate_manifest.py", "export_manifest.py"})
# The interpreter flags the runner always adds before the script path.
_INTERPRETER_ARGV = (sys.executable, "-B", "-s", "-X", "utf8")


def _real(raw: str) -> Path:
    """Resolve ``raw`` with the OS, independently of the runner's own mapping."""
    return Path(os.path.realpath(raw))


def _split_option(token: str) -> str:
    """Return the option name of ``--name=value``; other tokens are unchanged."""
    if token.startswith("--") and "=" in token:
        return token.partition("=")[0]
    return token


def _audit_arguments(script: str, args: Sequence[str], tree: Tree) -> None:
    """Fail unless every argument is allowed for ``script`` and every path is contained.

    Args:
        script: The script file name.
        args: The subprocess arguments after the script path.
        tree: The tree the paths must stay inside.
    """
    exports = _real(str(tree.sandbox / "exports"))
    sandbox = _real(str(tree.sandbox))
    items = list(args)
    index = 0
    if script == "catalog_lookup.py":
        while index < len(items) and items[index] in _HELP:
            index += 1
        value_options: frozenset[str] = frozenset()
        flag_options: frozenset[str] = frozenset()
        if index < len(items):
            assert items[index] in _CATALOG, items[index]
            value_options, flag_options = _CATALOG[items[index]]
            index += 1
    else:
        value_options, flag_options = _SCRIPT_OPTIONS[script]
    positional = 0
    while index < len(items):
        token = items[index]
        index += 1
        if len(token) > 1 and token.startswith("-"):
            name = _split_option(token)
            assert name in _HELP | value_options | flag_options, token
            if name in value_options:
                value = items[index]
                index += 1
                if name in _EXPORT_OPTIONS:
                    target = _real(value)
                    assert target.is_relative_to(exports), value
                    assert target != exports, value
            continue
        if script in _MANIFEST_SCRIPTS and positional == 0:
            assert _real(token).is_relative_to(sandbox), token
        positional += 1


def _assert_contained(
    tree: Tree,
    command: str,
    result: ScriptResult,
    factory: FakeProcessFactory,
    gate: FakeGate,
) -> None:
    """Assert Property 1 for one call: refused with no process, or fully contained."""
    if result.status == "refused":
        assert factory.starts == [], command
        assert gate.dry_run_calls == [], command
        assert result.text.strip(), command
        return
    assert len(factory.starts) == 1, command
    start = factory.starts[0]
    assert start.argv[:5] == _INTERPRETER_ARGV, command
    assert start.cwd == tree.box.path, command
    script = _real(start.argv[5])
    assert script.parent == _real(str(tree.skill / "scripts")), command
    assert script.name in _SCRIPTS, command
    assert "--compiler" not in start.argv, command
    _audit_arguments(script.name, start.argv[6:], tree)
    for call in gate.dry_run_calls:
        assert _real(str(call.manifest_path)).is_relative_to(_real(str(tree.sandbox)))


# --- Generators ---------------------------------------------------------------

_LAUNCHERS = (
    "",
    "python",
    "python3",
    "python3.12",
    "py",
    "py -3",
    "py -3.11",
    "uv run python",
)
_HOSTILE_LAUNCHERS = (
    "python -c",
    "python -m",
    "python -X dev",
    "python -I",
    "python -S",
    "py -2",
    "bash",
    "sh -c",
    "cmd /c",
    "powershell -Command",
    "perl",
    "node",
    "uv run",
    "uv run pip",
    "uv run python -c",
)
_SKILL_PREFIXES = (
    f"/skills/{_SKILL}/",
    f"\\skills\\{_SKILL}\\",
    "<skill>/",
    f"app/agents/workflow_builder/skills/{_SKILL}/",
    f"./app/agents/workflow_builder/skills/{_SKILL}/",
    f"backend/app/agents/workflow_builder/skills/{_SKILL}/",
)
_ODD_PREFIXES = (
    "",
    "/",
    "./",
    "../",
    "/workflows/",
    "workflows/",
    "/exports/",
    "/etc/",
    "C:\\",
    "\\\\server\\share\\",
    "/skills/",
    f"/skills/{_SKILL}/",
    f"/skills/{_SKILL}/../",
    f"/skills/{_SKILL}/scripts/../",
    f"/skills/{_SKILL}/scripts/sub/",
    "scripts/",
)
_OPERATORS = ("&&", "||", ";", "|", "&", "<", ">", ">>", "2>&1", "`", "$(", "\n")

_PATHS = (
    _MANIFEST,
    "/workflows/b.workflow.json",
    "workflows/a.workflow.json",
    "\\workflows\\a.workflow.json",
    "/workflows/link_in/a.workflow.json",
    "/workflows/link_out/secret.json",
    "/workflows/link_skill/SKILL.md",
    "/exports/out.yaml",
    "/exports/link_out/out.yaml",
    "/exports",
    "/exports/",
    "exports/../out.yaml",
    "/workflows/../../x.json",
    "../x.json",
    "/../x.json",
    "..\\..\\x.json",
    "/workflows/.. /x.json",
    "/workflows/.../x.json",
    "/workflows/a./x.json",
    "/workflows/a.json:stream",
    "C:/Windows/win.ini",
    "C:\\Windows\\win.ini",
    "\\\\server\\share\\x.json",
    "/etc/passwd",
    "/proc/self/environ",
    "/workflows/NUL",
    f"/skills/{_SKILL}/SKILL.md",
    "<skill>/SKILL.md",
    f"app/agents/workflow_builder/skills/{_SKILL}/SKILL.md",
    f"/skills/{_SKILL}/scripts/selftest.py",
    "é/ü.json",
    "日本語.workflow.json",
    "a\u202eb.json",
    "a\u00a0b.json",
    "a；b.json",
    "a｜b.json",
    "",
    ".",
    "..",
)
_MISC = (
    "overview",
    "models",
    "kind",
    "agents",
    "agent",
    "skills",
    "workflows",
    "mcp",
    "trust",
    "field",
    "search",
    "example",
    "bogus",
    "user",
    "db",
    "file",
    "builtin",
    "--",
    "-",
    "é",
    "x" * 300,
)
_OPTIONS = (
    "--trust",
    "--trust=user",
    "--trust=-x",
    "--summary",
    "--json",
    "--strict",
    "--quiet-info",
    "--compiler",
    "--compiler=.",
    "--check",
    "--yaml",
    "--save-payload",
    "--run-payload",
    "--message",
    "--name",
    "--eu",
    "--all",
    "--full",
    "-h",
    "--help",
    "--help=1",
    # Refused or unknown.
    "--catalog",
    "--schema",
    "--source",
    "--api",
    "--render",
    "--token",
    "--out-json",
    "--out-md",
    "--no-schema",
    "--evil",
    "-c",
    "-m",
    "-X",
    "-rm",
    "--TRUST",
)
_POOL = _PATHS + _MISC + _OPTIONS + _OPERATORS
_SCRIPT_NAMES = (
    *sorted(_SCRIPTS),
    "SELFTEST.PY",
    "selftest",
    "selftest.py.bak",
    "selftest.py ",
    "__init__.py",
    "evil.py",
    "run.sh",
    "SKILL.md",
    "..",
    "scripts",
    "../selftest.py",
    "sub/selftest.py",
)


def _single_quote(token: str) -> str:
    """Quote ``token`` in single quotes, splicing in any single quote."""
    return "'" + token.replace("'", "'\"'\"'") + "'"


def _render(tokens: Sequence[tuple[str, str]], separators: Sequence[str]) -> str:
    """Write ``(token, style)`` pairs as one command line.

    ``bare`` writes the token as it is, so a token with an operator or spaces
    stays shell syntax or splits. ``single`` and ``double`` quote it.
    """
    pieces: list[str] = []
    for token, style in tokens:
        if style == "single" or (style == "double" and '"' in token):
            pieces.append(_single_quote(token))
        elif style == "double":
            pieces.append('"' + token + '"')
        else:
            pieces.append(token)
    out = ""
    for index, piece in enumerate(pieces):
        out += piece + separators[index % len(separators)]
    return out.strip(" \t")


_STYLE = st.sampled_from(("bare", "bare", "single", "double"))
_SEPARATORS = st.lists(st.sampled_from((" ", "  ", "\t")), min_size=1, max_size=4)


@st.composite
def _script_token(draw: st.DrawFn) -> str:
    """Draw a script path as the model might write it, good or bad."""
    prefix = draw(st.sampled_from(_SKILL_PREFIXES + _ODD_PREFIXES))
    name = draw(st.sampled_from(_SCRIPT_NAMES))
    in_scripts = draw(st.booleans())
    token = f"{prefix}scripts/{name}" if in_scripts else f"{prefix}{name}"
    return token.replace("/", "\\") if draw(st.booleans()) else token


@st.composite
def _good_script_calls(draw: st.DrawFn) -> list[str]:
    """Draw the tokens of a call the policy accepts, without the launcher."""
    prefix = draw(st.sampled_from(_SKILL_PREFIXES))
    case = draw(st.integers(min_value=0, max_value=7))
    name = draw(st.sampled_from(("a", "b", "c")))
    manifest = f"/workflows/{name}.workflow.json"
    export = f"/exports/{name}.yaml"
    script: str
    args: list[str]
    match case:
        case 0:
            script, args = "catalog_lookup.py", ["overview", "--trust", "user"]
        case 1:
            script, args = "catalog_lookup.py", ["search", name, "agent"]
        case 2:
            script, args = "validate_manifest.py", [manifest, "--json"]
        case 3:
            script, args = "validate_manifest.py", [manifest, "--compiler", "."]
        case 4:
            script, args = "selftest.py", []
        case 5:
            script, args = "refresh_catalog.py", ["--check"]
        case 6:
            script, args = "schema_sync.py", ["--check"]
        case _:
            script, args = "export_manifest.py", [manifest, "--yaml", export]
    return [f"{prefix}scripts/{script}", *args]


@st.composite
def _good_calls(draw: st.DrawFn) -> list[str]:
    """Draw the tokens of a call the policy accepts, with an optional launcher."""
    launcher = draw(st.sampled_from(_LAUNCHERS)).split()
    return [*launcher, *draw(_good_script_calls())]


@st.composite
def _commands(draw: st.DrawFn) -> str:
    """Draw a command line: a random mix of tokens, or a good call that was mutated."""
    if draw(st.booleans()):
        launcher = draw(st.sampled_from(_LAUNCHERS + _HOSTILE_LAUNCHERS)).split()
        words = [
            *launcher,
            draw(_script_token()),
            *draw(st.lists(st.sampled_from(_POOL), max_size=6)),
        ]
    else:
        words = draw(_good_calls())
        operation = draw(st.sampled_from(("keep", "insert", "replace", "drop")))
        position = draw(st.integers(min_value=0, max_value=len(words)))
        extra = draw(st.sampled_from(_POOL))
        if operation == "insert":
            words.insert(position, extra)
        elif words and operation == "replace":
            words[position % len(words)] = extra
        elif words and operation == "drop":
            del words[position % len(words)]
    tokens = [(word, draw(_STYLE)) for word in words]
    return _render(tokens, draw(_SEPARATORS))


# --- Properties ---------------------------------------------------------------


# Feature: ai-workflow-builder, Property 1: Script commands cannot escape
@settings(max_examples=100, deadline=None)
@given(command=_commands())
def test_run_command_is_refused_or_contained_when_command_is_arbitrary(
    command: str,
) -> None:
    """A mixed command is refused with no process, or runs one contained script."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as raw:
        tree = _build_tree(Path(raw))

        result, factory, gate = _run(tree, command)

        event(result.status)
        _assert_contained(tree, command, result, factory, gate)


# Feature: ai-workflow-builder, Property 1: Script commands cannot escape
@settings(max_examples=100, deadline=None)
@given(
    base=_good_calls(),
    operator=st.sampled_from(_OPERATORS),
    position=st.integers(min_value=0, max_value=8),
    glued=st.booleans(),
)
def test_run_command_refuses_when_unquoted_operator_is_added(
    base: list[str], operator: str, position: int, glued: bool
) -> None:
    """An unquoted shell operator, apart or glued to a word, is always refused."""
    words = list(base)
    index = min(position, len(words))
    if glued and words:
        index = min(index, len(words) - 1)
        words[index] += operator
    else:
        words.insert(index, operator)
    command = " ".join(words)
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as raw:
        tree = _build_tree(Path(raw))

        result, factory, gate = _run(tree, command)

        assert result.status == "refused", command
        assert factory.starts == [], command
        assert gate.dry_run_calls == [], command


# Feature: ai-workflow-builder, Property 1: Script commands cannot escape
@settings(max_examples=100, deadline=None)
@given(
    launcher=st.sampled_from(_LAUNCHERS[1:5] + ("uv run python", "py -3")),
    option=st.sampled_from(
        ("-c", "-m", "-X", "-I", "-S", "-u", "-W", "-E", "-O", "-i", "-V", "--version")
    ),
    payload=st.sampled_from(("print(1)", "import os", "http.server", "dev", "")),
    call=_good_script_calls(),
    quoted=st.booleans(),
)
def test_run_command_refuses_when_interpreter_option_is_used(
    launcher: str, option: str, payload: str, call: list[str], quoted: bool
) -> None:
    """``python -c`` and every other interpreter option is refused, even before a valid script."""
    script_call = " ".join(call)
    inline = _single_quote(payload) if quoted else payload.replace(" ", "")
    command = f"{launcher} {option} {inline} {script_call}".strip()
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as raw:
        tree = _build_tree(Path(raw))

        result, factory, gate = _run(tree, command)

        assert result.status == "refused", command
        assert factory.starts == [], command
        assert gate.dry_run_calls == [], command


# Each template is a call the policy must refuse: a refused mode, an unknown
# option, a missing required option, a wrong argument count, or an unknown script.
_REFUSED_MODES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("selftest.py", ("--compiler", ".")),
    ("selftest.py", ("--compiler",)),
    ("selftest.py", ("--catalog", "x")),
    ("selftest.py", ("--schema", "x")),
    ("selftest.py", ("--evil",)),
    ("selftest.py", ("extra",)),
    ("catalog_lookup.py", ("overview", "--catalog", "x")),
    ("catalog_lookup.py", ("overview", "--schema=x")),
    ("catalog_lookup.py", ("kind", "agent", "--catalog", "c")),
    ("catalog_lookup.py", ("--catalog", "x", "overview")),
    ("catalog_lookup.py", ("bogus",)),
    ("catalog_lookup.py", ()),
    ("catalog_lookup.py", ("overview", "extra")),
    ("catalog_lookup.py", ("models", "--trust", "user")),
    ("catalog_lookup.py", ("-c", "overview")),
    ("validate_manifest.py", (_MANIFEST, "--catalog", "x")),
    ("validate_manifest.py", (_MANIFEST, "--schema=x")),
    ("validate_manifest.py", (_MANIFEST, "--source", "x")),
    ("validate_manifest.py", (_MANIFEST, "--evil")),
    ("validate_manifest.py", ()),
    ("validate_manifest.py", (_MANIFEST, "extra")),
    ("validate_manifest.py", (_MANIFEST, "--trust")),
    ("refresh_catalog.py", ()),
    ("refresh_catalog.py", ("--source", "x")),
    ("refresh_catalog.py", ("--check", "--source", ".")),
    ("refresh_catalog.py", ("--check", "--api")),
    ("refresh_catalog.py", ("--check", "--render")),
    ("refresh_catalog.py", ("--out-json", "x")),
    ("refresh_catalog.py", ("--check", "--token", "t")),
    ("refresh_catalog.py", ("--no-schema",)),
    ("schema_sync.py", ()),
    ("schema_sync.py", ("--catalog", "x")),
    ("schema_sync.py", ("--check", "--schema", "x")),
    ("schema_sync.py", ("--render",)),
    ("schema_sync.py", ("--source", "x")),
    ("export_manifest.py", (_MANIFEST,)),
    ("export_manifest.py", (_MANIFEST, "--message", "hi")),
    (
        "export_manifest.py",
        (_MANIFEST, "--yaml", "/exports/a.yaml", "--save-payload", "/exports/b.json"),
    ),
    ("export_manifest.py", (_MANIFEST, "--yaml")),
    ("export_manifest.py", (_MANIFEST, "--stdout")),
    ("evil.py", ()),
    ("__init__.py", ()),
    ("run.sh", ()),
    ("validate_manifest.pyc", (_MANIFEST,)),
    ("catalog_lookup", ("overview",)),
    ("SKILL.md", ()),
)


# Feature: ai-workflow-builder, Property 1: Script commands cannot escape
@settings(max_examples=100, deadline=None)
@given(
    mode=st.sampled_from(_REFUSED_MODES),
    launcher=st.sampled_from(_LAUNCHERS),
    prefix=st.sampled_from(_SKILL_PREFIXES),
    styles=st.lists(_STYLE, min_size=8, max_size=8),
    backslashes=st.booleans(),
)
def test_run_command_refuses_when_mode_is_not_allowed(
    mode: tuple[str, tuple[str, ...]],
    launcher: str,
    prefix: str,
    styles: list[str],
    backslashes: bool,
) -> None:
    """A refused mode stays refused whatever the launcher, prefix or quoting."""
    script, args = mode
    script_path = f"{prefix}scripts/{script}"
    if backslashes:
        script_path = script_path.replace("/", "\\")
    # A '<skill>/' prefix holds '<' and '>', so the script path is always quoted.
    words = [*launcher.split(), script_path, *args]
    tokens = [
        (word, "single" if "<" in word else styles[index % len(styles)])
        for index, word in enumerate(words)
    ]
    # Quoted values never turn an unknown option into a known one.
    command = _render(tokens, [" "])
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as raw:
        tree = _build_tree(Path(raw))

        result, factory, gate = _run(tree, command)

        assert result.status == "refused", command
        assert factory.starts == [], command
        assert gate.dry_run_calls == [], command


@st.composite
def _escaping_paths(draw: st.DrawFn, *, writing: bool) -> str:
    """Draw a path that leaves the sandbox, enters the skill folder, or is malformed.

    Args:
        draw: The Hypothesis draw function.
        writing: True for an output path, which must also stay out of
            ``/workflows/`` and out of ``/exports`` itself.
    """
    climb = "../" * draw(st.integers(min_value=2, max_value=5))
    lead = draw(st.sampled_from(("", "/", "./")))
    folder = draw(st.sampled_from(("workflows", "exports", "canvas")))
    name = draw(st.sampled_from(("x.json", "x.yaml", "secret.json", "win.ini")))
    choices: list[str] = [
        f"{lead}{folder}/{climb}{name}",
        f"{lead}{climb}{name}",
        f"/{climb}{name}",
        f"{lead}{folder}/..{'/..' * draw(st.integers(min_value=1, max_value=3))}",
        f"/skills/{_SKILL}/SKILL.md",
        f"/skills/{_SKILL}/scripts/{name}",
        f"<skill>/{name}",
        f"app/agents/workflow_builder/skills/{_SKILL}/{name}",
        f"backend/app/agents/workflow_builder/skills/{_SKILL}/{name}",
        f"/workflows/.. /{name}",
        f"/{folder}/.../{name}",
        f"/{folder}/a./{name}",
        f"/{folder}/{name}:stream",
        f"C:/{name}",
        "",
        "..",
        "/..",
    ]
    if DIR_LINKS_OK:
        choices += [
            "/workflows/link_out/secret.json",
            f"/workflows/link_out/{name}",
            "/workflows/link_skill/SKILL.md",
            f"/workflows/link_skill/scripts/{name}",
        ]
        if writing:
            choices += [f"/exports/link_out/{name}", "/exports/link_out"]
    if writing:
        choices += [
            f"/workflows/{name}",
            f"/canvas/{name}",
            name,
            "/exports",
            "/exports/",
            "exports/.",
            f"exports/../{name}",
            "/",
        ]
    path = draw(st.sampled_from(choices))
    return path.replace("/", "\\") if draw(st.booleans()) else path


# Feature: ai-workflow-builder, Property 1: Script commands cannot escape
@settings(max_examples=100, deadline=None)
@given(
    script=st.sampled_from(("validate_manifest.py", "export_manifest.py")),
    bad=_escaping_paths(writing=False),
    launcher=st.sampled_from(_LAUNCHERS),
    as_input=st.booleans(),
    option=st.sampled_from(("--yaml", "--save-payload", "--run-payload")),
    bad_output=_escaping_paths(writing=True),
)
def test_run_command_refuses_when_a_path_leaves_the_sandbox(
    script: str,
    bad: str,
    launcher: str,
    as_input: bool,
    option: str,
    bad_output: str,
) -> None:
    """An escaping manifest or output path is refused, in a call that is otherwise valid."""
    script_path = f"/skills/{_SKILL}/scripts/{script}"
    words = [*launcher.split(), script_path]
    if script == "export_manifest.py":
        manifest = bad if as_input else _MANIFEST
        output = "/exports/ok.yaml" if as_input else bad_output
        words += [manifest, option, output]
    else:
        # The validator has no output slot, so its only path is the input.
        words += [bad]
    command = _render([(word, "single") for word in words], [" "])
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as raw:
        tree = _build_tree(Path(raw))

        result, factory, gate = _run(tree, command)

        assert result.status == "refused", command
        assert factory.starts == [], command
        assert gate.dry_run_calls == [], command


@st.composite
def _escaping_script_paths(draw: st.DrawFn) -> str:
    """Draw a script path that does not name a real file in ``<skill>/scripts/``."""
    name = draw(st.sampled_from(sorted(_SCRIPTS)))
    choices = [
        f"/skills/{_SKILL}/scripts/../../{name}",
        f"/skills/{_SKILL}/scripts/../{name}",
        f"/skills/{_SKILL}/scripts/../SKILL.md",
        f"/skills/{_SKILL}/{name}",
        f"/skills/{_SKILL}/scripts/sub/{name}",
        f"/skills/{_SKILL}/scripts/{name}/..",
        f"/workflows/{name}",
        f"/exports/{name}",
        f"scripts/{name}",
        name,
        f"../{name}",
        f"/{name}",
        f"/etc/{name}",
        f"C:\\{name}",
        f"<skill>/{name}",
        f"<skill>/scripts/../{name}",
        f"app/agents/workflow_builder/skills/{_SKILL}/{name}",
        f"backend/app/agents/workflow_builder/skills/{_SKILL}/scripts/../../{name}",
    ]
    if DIR_LINKS_OK:
        choices += [
            f"/workflows/link_skill/scripts/{name}",
            f"/workflows/link_out/{name}",
        ]
    path = draw(st.sampled_from(choices))
    return path.replace("/", "\\") if draw(st.booleans()) else path


# Feature: ai-workflow-builder, Property 1: Script commands cannot escape
@settings(max_examples=100, deadline=None)
@given(
    script_path=_escaping_script_paths(),
    launcher=st.sampled_from(_LAUNCHERS),
    args=st.sampled_from(((), ("overview",), ("--check",))),
)
def test_run_command_refuses_when_script_is_outside_the_scripts_folder(
    script_path: str, launcher: str, args: tuple[str, ...]
) -> None:
    """A script path that does not land in ``<skill>/scripts/`` is refused."""
    words = [*launcher.split(), script_path, *args]
    command = _render([(word, "single") for word in words], [" "])
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as raw:
        tree = _build_tree(Path(raw))

        result, factory, gate = _run(tree, command)

        assert result.status == "refused", command
        assert factory.starts == [], command
        assert gate.dry_run_calls == [], command


# Feature: ai-workflow-builder, Property 1: Script commands cannot escape
@pytest.mark.skipif(
    not FILE_LINKS_OK and LINK_SKIP_ALLOWED,
    reason="file symlinks need a privilege on this local Windows machine",
)
@settings(max_examples=100, deadline=None)
@given(
    name=st.sampled_from(sorted(_SCRIPTS)),
    launcher=st.sampled_from(_LAUNCHERS),
    prefix=st.sampled_from(_SKILL_PREFIXES),
)
def test_run_command_refuses_when_script_is_a_link_to_a_file_outside(
    name: str, launcher: str, prefix: str
) -> None:
    """A script that is a symlink to a file outside the skill folder is refused."""
    words = [*launcher.split(), f"{prefix}scripts/{name}"]
    command = _render([(word, "single") for word in words], [" "])
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as raw:
        tree = _build_tree(Path(raw), link_script=name)

        result, factory, gate = _run(tree, command)

        assert result.status == "refused", command
        assert factory.starts == [], command
        assert gate.dry_run_calls == [], command


def test_probe_links_creates_both_link_kinds_when_skipping_is_not_allowed() -> None:
    """Off a local Windows run, folder and file links must work, or this fails."""
    if LINK_SKIP_ALLOWED:
        pytest.skip("local Windows run: links may need a privilege here")
    assert (DIR_LINKS_OK, FILE_LINKS_OK) == (True, True)


@pytest.mark.parametrize(
    "command",
    [
        f"python /skills/{_SKILL}/scripts/catalog_lookup.py overview --trust user",
        f"py -3 /skills/{_SKILL}/scripts/selftest.py",
        'uv run python "<skill>/scripts/refresh_catalog.py" --check',
        f"python3 app/agents/workflow_builder/skills/{_SKILL}/scripts/schema_sync.py --check",
        f"python /skills/{_SKILL}/scripts/validate_manifest.py {_MANIFEST} --json",
        f"python /skills/{_SKILL}/scripts/validate_manifest.py {_MANIFEST} --compiler .",
        f"python /skills/{_SKILL}/scripts/export_manifest.py {_MANIFEST} --yaml /exports/a.yaml",
        f"python \\skills\\{_SKILL}\\scripts\\selftest.py",
        f"python /skills/{_SKILL}/scripts/catalog_lookup.py search 'a && b'",
    ],
)
def test_run_command_starts_one_contained_process_when_command_is_allowed(
    command: str,
) -> None:
    """Allowed calls do start, so the refusal properties above are not vacuous."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as raw:
        tree = _build_tree(Path(raw))

        result, factory, gate = _run(tree, command)

        assert result.status != "refused", result.text
        assert len(factory.starts) == 1
        _assert_contained(tree, command, result, factory, gate)
