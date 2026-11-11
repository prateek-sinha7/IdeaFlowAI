"""Property tests for the script runner's shell-free command parsing.

Covers design Property 2 (tasks 12.3): the tokenizer is a faithful inverse of
quoting, and a parsed command does not depend on the launcher or on how the
skill path is written. Everything runs on ``tmp_path`` folders; no subprocess
is started.
"""

from __future__ import annotations

import dataclasses

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.agents.workflow_builder import script_runner
from app.agents.workflow_builder.script_policy import BUILDER_SKILL_ID
from app.agents.workflow_builder.script_runner import (
    ParsedCommand,
    Refusal,
    Roots,
    parse_command,
)

_SAFE_CHARS = "abcXYZ019-_./:=\\"
_AWKWARD_CHARS = "abc \t\\/'\"`$(){}[]*?~!#%^;|&<>=,\n\r-é"
_WHITESPACE = st.text(alphabet=" \t", min_size=1, max_size=3)
_NAME = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789_", min_size=1, max_size=8
)

_LAUNCHERS = (
    "",
    "python",
    "python3",
    "python3.12",
    "py",
    "py -3",
    "py -3.11",
    "uv run python",
    "uv run python3",
)
_SKILL_PREFIXES = (
    f"/skills/{BUILDER_SKILL_ID}/",
    "<skill>/",
    f"app/agents/workflow_builder/skills/{BUILDER_SKILL_ID}/",
    f"./app/agents/workflow_builder/skills/{BUILDER_SKILL_ID}/",
    f"backend/app/agents/workflow_builder/skills/{BUILDER_SKILL_ID}/",
)


def _single_quote(token: str) -> str:
    """Quote ``token`` in single quotes, splicing any single quote."""
    return "'" + token.replace("'", "'\"'\"'") + "'"


def _quote(token: str, style: str) -> str:
    """Write ``token`` the way a model could: bare, single or double quoted."""
    if style == "bare" and token and all(c in _SAFE_CHARS for c in token):
        return token
    if style == "double" and '"' not in token:
        return '"' + token + '"'
    return _single_quote(token)


@pytest.fixture(scope="module")
def roots(tmp_path_factory: pytest.TempPathFactory) -> Roots:
    """Provide a sandbox folder and a skill folder under a temp directory."""
    base = tmp_path_factory.mktemp("parsing")
    sandbox = base / "sandbox"
    skill = base / "skill"
    (skill / "scripts").mkdir(parents=True)
    sandbox.mkdir()
    return Roots(sandbox=sandbox, skill=skill)


@st.composite
def _allowed_calls(draw: st.DrawFn) -> tuple[str, list[str]]:
    """Draw a script name and the arguments after it that the policy accepts."""
    name = draw(_NAME)
    manifest_style = draw(st.sampled_from(("/", "\\")))
    manifest = f"{manifest_style}workflows{manifest_style}{name}.workflow.json"
    export = f"/exports/{name}.yaml"
    flags = draw(
        st.lists(
            st.sampled_from(("--json", "--strict", "--summary", "--quiet-info")),
            unique=True,
            max_size=4,
        )
    )
    case = draw(st.integers(min_value=0, max_value=7))
    if case == 0:
        return "catalog_lookup.py", ["overview", "--trust", draw(_NAME)]
    if case == 1:
        return "catalog_lookup.py", ["kind", name]
    if case == 2:
        words = draw(st.lists(_NAME, min_size=1, max_size=3))
        return "catalog_lookup.py", ["search", *words]
    if case == 3:
        return "validate_manifest.py", [manifest, *flags]
    if case == 4:
        return "validate_manifest.py", [manifest, "--compiler", draw(_NAME), *flags]
    if case == 5:
        return "selftest.py", []
    if case == 6:
        return "refresh_catalog.py", ["--check"]
    return "export_manifest.py", [manifest, "--yaml", export]


def _plain(launcher: str, script: str, args: list[str]) -> str:
    """Write the baseline command: forward slashes, `/skills/` prefix, one space."""
    script_path = f"/skills/{BUILDER_SKILL_ID}/scripts/{script}"
    return " ".join(part for part in (launcher, script_path, *args) if part)


def _parsed(command: str, roots: Roots) -> ParsedCommand:
    """Parse ``command`` and fail the test if it is refused."""
    result = parse_command(command, roots)
    assert isinstance(result, ParsedCommand), result
    return result


def _same_but_command(first: ParsedCommand, second: ParsedCommand) -> bool:
    """Compare two parsed commands ignoring the original command text."""
    return dataclasses.replace(first, command="") == dataclasses.replace(
        second, command=""
    )


# Feature: ai-workflow-builder, Property 2: Parsing is shell-free and independent of the form used
@settings(max_examples=100, deadline=None)
@given(
    tokens=st.lists(
        st.tuples(
            st.text(alphabet=_AWKWARD_CHARS, max_size=12),
            st.sampled_from(("bare", "single", "double")),
        ),
        max_size=6,
    ),
    separators=st.lists(_WHITESPACE, min_size=8, max_size=8),
)
def test_tokenize_returns_same_tokens_when_quoted_and_joined(
    tokens: list[tuple[str, str]], separators: list[str]
) -> None:
    """Quoting then joining arguments, then tokenising, gives back every token."""
    original = [token for token, _ in tokens]
    pieces = [_quote(token, style) for token, style in tokens]
    command = separators[0] + "".join(
        piece + separators[index + 1] for index, piece in enumerate(pieces)
    )

    result = script_runner._tokenize(command)  # pyright: ignore[reportPrivateUsage]

    assert result == original


# Feature: ai-workflow-builder, Property 2: Parsing is shell-free and independent of the form used
@settings(max_examples=100, deadline=None)
@given(
    call=_allowed_calls(),
    launcher=st.sampled_from(_LAUNCHERS),
    separator=_WHITESPACE,
)
def test_parse_command_gives_same_result_when_launcher_differs(
    call: tuple[str, list[str]], launcher: str, separator: str, roots: Roots
) -> None:
    """Any accepted launcher, or none, yields the same parsed command."""
    script, args = call
    baseline = _parsed(_plain("python", script, args), roots)
    command = _plain(launcher, script, args).replace(" ", separator)

    parsed = _parsed(command, roots)

    assert _same_but_command(parsed, baseline)


# Feature: ai-workflow-builder, Property 2: Parsing is shell-free and independent of the form used
@settings(max_examples=100, deadline=None)
@given(
    call=_allowed_calls(),
    prefix=st.sampled_from(_SKILL_PREFIXES),
    backslashes=st.booleans(),
    launcher=st.sampled_from(_LAUNCHERS),
)
def test_parse_command_gives_same_result_when_skill_path_form_differs(
    call: tuple[str, list[str]],
    prefix: str,
    backslashes: bool,
    launcher: str,
    roots: Roots,
) -> None:
    """Any accepted skill prefix and either slash style maps to the same script."""
    script, args = call
    baseline = _parsed(_plain("python", script, args), roots)
    script_path = f"{prefix}scripts/{script}"
    if backslashes:
        script_path = script_path.replace("/", "\\")
    command = " ".join(part for part in (launcher, f'"{script_path}"', *args) if part)

    parsed = _parsed(command, roots)

    assert _same_but_command(parsed, baseline)


# Feature: ai-workflow-builder, Property 2: Parsing is shell-free and independent of the form used
@settings(max_examples=100, deadline=None)
@given(
    call=_allowed_calls(),
    operator=st.sampled_from(
        ("&&", "||", ";", "|", "&", "<", ">", ">>", "`", "$(", "\n")
    ),
    position=st.integers(min_value=0, max_value=6),
)
def test_parse_command_refuses_when_unquoted_operator_present(
    call: tuple[str, list[str]], operator: str, position: int, roots: Roots
) -> None:
    """An unquoted shell operator anywhere in the command is refused."""
    script, args = call
    words = _plain("python", script, args).split(" ")
    words.insert(min(position, len(words)), operator)

    result = parse_command(" ".join(words), roots)

    assert isinstance(result, Refusal)


# Feature: ai-workflow-builder, Property 2: Parsing is shell-free and independent of the form used
@settings(max_examples=100, deadline=None)
@given(operator=st.sampled_from(("&&", "||", ";", "|", "&", "<", ">", "`", "$(")))
def test_parse_command_accepts_when_operator_is_quoted_message(
    operator: str, roots: Roots
) -> None:
    """The same operator inside quotes is literal text, not a refusal reason."""
    # --message is a plain-value option of export_manifest.py.
    command = (
        f"python /skills/{BUILDER_SKILL_ID}/scripts/export_manifest.py "
        f"/workflows/a.workflow.json --yaml /exports/a.yaml --message 'a {operator} b'"
    )

    parsed = _parsed(command, roots)

    assert parsed.args[-2:] == ("--message", f"a {operator} b")
