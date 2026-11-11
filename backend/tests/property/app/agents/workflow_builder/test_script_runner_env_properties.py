"""Property tests for the script runner's subprocess environment.

Covers design Property 4 (task 12.8, Req 36.3, 36.4): whatever the API process's
environment holds, the environment handed to the spawner is exactly the
allow-list. Every call goes through :func:`run_command` with a
:class:`FakeProcessFactory`, so no subprocess starts. The allow-list and the
expected values are restated here and do not read ``SCRIPT_ENV_NAMES``.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from unittest import mock
from uuid import uuid4

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.agents.workflow_builder.sandbox import BuilderSandbox
from app.agents.workflow_builder.script_policy import BUILDER_SKILL_ID
from app.agents.workflow_builder.script_runner import ScriptContext, run_command
from tests.fakes.builder_gate import FakeGate
from tests.fakes.process_factory import FakeProcessFactory

_IS_WINDOWS = sys.platform == "win32"

# The allow-list, restated from Req 36.3 and the 12.4 decision. Names that only
# Windows sets are kept apart so the oracle can tell the two platforms apart.
_COMMON_NAMES = frozenset(
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
    }
)
_WINDOWS_ONLY_NAMES = frozenset({"SYSTEMROOT", "PATHEXT"})
_ALLOWED_NAMES = _COMMON_NAMES | (_WINDOWS_ONLY_NAMES if _IS_WINDOWS else frozenset())

# Fixed values when the server's own environment is left out of the picture.
_FIXED_VALUES = {
    "PYTHONDONTWRITEBYTECODE": "1",
    "PYTHONIOENCODING": "utf-8",
    "PYTHONUTF8": "1",
    "PYTHONNOUSERSITE": "1",
    "LANG": "C.UTF-8",
}
_TEMP_NAMES = ("TMP", "TEMP", "TMPDIR", "HOME", "USERPROFILE")
_WINDOWS_SYSTEMROOT = r"C:\Windows"
_WINDOWS_PATHEXT = ".COM;.EXE;.BAT;.CMD"

_COMMAND = f"python /skills/{BUILDER_SKILL_ID}/scripts/catalog_lookup.py overview"
_CANARY = "CANARY-"

_HOSTILE_NAMES = (
    # Secrets and credentials.
    "DATABASE_URL",
    "POSTGRES_PASSWORD",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "JWT_SECRET",
    "SIGNING_KEY",
    "GITHUB_TOKEN",
    "COGNITO_CLIENT_SECRET",
    # Interpreter switches that change what a script runs.
    "PYTHONPATH",
    "PYTHONHOME",
    "PYTHONSTARTUP",
    "PYTHONINSPECT",
    "PYTHONWARNINGS",
    "PYTHONHASHSEED",
    "PYTHONSAFEPATH",
    "PYTHONUSERBASE",
    "PYTHONBREAKPOINT",
    "PYTHONDEVMODE",
    # Loader and network knobs.
    "LD_PRELOAD",
    "LD_LIBRARY_PATH",
    "DYLD_INSERT_LIBRARIES",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "PIP_INDEX_URL",
    "UV_INDEX_URL",
    "VIRTUAL_ENV",
    # Allow-listed names set to hostile values: the runner must ignore them.
    "PATH",
    "HOME",
    "USERPROFILE",
    "TMP",
    "TEMP",
    "TMPDIR",
    "LANG",
    "PYTHONUTF8",
    "PYTHONIOENCODING",
    "PYTHONDONTWRITEBYTECODE",
    "PYTHONNOUSERSITE",
)

# Names are upper case with digits and underscores, because Windows folds the
# case of environment names and rejects '=' and NUL in them.
_RANDOM_NAMES = st.builds(
    "".join,
    st.tuples(
        st.sampled_from(("", "PYTHON", "AWS_", "SECRET_", "TOKEN_", "X_")),
        st.text(
            alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_", min_size=1, max_size=12
        ),
    ),
).filter(lambda name: name not in _WINDOWS_ONLY_NAMES)
_NAMES = st.one_of(st.sampled_from(_HOSTILE_NAMES), _RANDOM_NAMES).filter(
    lambda name: name not in _WINDOWS_ONLY_NAMES
)

_TEXT = st.text(
    alphabet=st.characters(blacklist_categories=("Cs",), blacklist_characters="\x00"),
    max_size=60,
)
_LONG = st.integers(min_value=1_000, max_value=20_000).map(lambda n: "x" * n)
# Every value carries the canary, so a leak shows up wherever the value lands.
_VALUES = st.builds(
    lambda body: _CANARY + body,
    st.one_of(_TEXT, _LONG, st.just("../../etc/passwd"), st.just("a;b|c&d$(e)")),
)
_HOSTILE_ENVS = st.dictionaries(_NAMES, _VALUES, max_size=15)


class _StubTurn:
    """The one part of ``TurnPort`` that ``catalog_lookup.py`` calls read."""

    stopping = False


@pytest.fixture(scope="module")
def sandbox(tmp_path_factory: pytest.TempPathFactory) -> BuilderSandbox:
    """Provide a created sandbox under a temp directory."""
    box = BuilderSandbox("env-user", "env-session", root=tmp_path_factory.mktemp("env"))
    box.ensure()
    return box


@pytest.fixture(scope="module")
def skill_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Provide a skill folder with a ``scripts`` folder."""
    root = tmp_path_factory.mktemp("env-skill")
    (root / "scripts").mkdir()
    return root


def _server_env(extra: dict[str, str]) -> dict[str, str]:
    """Return the variables to add to ``os.environ`` for one example."""
    env = dict(extra)
    if _IS_WINDOWS:
        env["SYSTEMROOT"] = _WINDOWS_SYSTEMROOT
        env["PATHEXT"] = _WINDOWS_PATHEXT
    return env


def _spawned_env(
    sandbox: BuilderSandbox, skill_root: Path, server_env: dict[str, str]
) -> tuple[dict[str, str], Path]:
    """Run one command with ``server_env`` added to the server and return the env.

    Returns:
        The environment the spawner received and the call's expected temp folder.
    """
    call_id = uuid4().hex
    factory = FakeProcessFactory()
    ctx = ScriptContext(
        sandbox=sandbox,
        skill_root=skill_root,
        gate=FakeGate(),
        turn=_StubTurn(),  # type: ignore[arg-type]
        semaphore=asyncio.Semaphore(1),
        spawn=factory,
        call_id=call_id,
        timeout_seconds=5.0,
    )
    with mock.patch.dict(os.environ, server_env):
        result = asyncio.run(run_command(_COMMAND, ctx))
    assert result.status == "ok"
    assert len(factory.starts) == 1
    return dict(factory.starts[0].env), sandbox.path / ".tmp" / call_id


def _expected_path() -> str:
    """Return the ``PATH`` the runner must set, built without ``script_env``."""
    interpreter_dir = os.path.dirname(sys.executable)
    if _IS_WINDOWS:
        parts = [
            interpreter_dir,
            os.path.join(_WINDOWS_SYSTEMROOT, "System32"),
            _WINDOWS_SYSTEMROOT,
        ]
        return os.pathsep.join(parts)
    return os.pathsep.join([interpreter_dir, os.defpath])


def _expected_env(tmp: Path) -> dict[str, str]:
    """Return the exact environment an allow-list produces for ``tmp``."""
    expected = dict(_FIXED_VALUES)
    expected.update({name: str(tmp) for name in _TEMP_NAMES})
    expected["PATH"] = _expected_path()
    if _IS_WINDOWS:
        expected["SYSTEMROOT"] = _WINDOWS_SYSTEMROOT
        expected["PATHEXT"] = _WINDOWS_PATHEXT
    return expected


# Feature: ai-workflow-builder, Property 4: The script environment is an allow-list
@settings(max_examples=100, deadline=None)
@given(hostile=_HOSTILE_ENVS)
def test_run_command_passes_exactly_the_allow_list_when_server_env_is_hostile(
    sandbox: BuilderSandbox, skill_root: Path, hostile: dict[str, str]
) -> None:
    env, tmp = _spawned_env(sandbox, skill_root, _server_env(hostile))

    assert env == _expected_env(tmp)


# Feature: ai-workflow-builder, Property 4: The script environment is an allow-list
@settings(max_examples=100, deadline=None)
@given(hostile=_HOSTILE_ENVS)
def test_run_command_passes_no_name_outside_the_allow_list_when_server_env_is_hostile(
    sandbox: BuilderSandbox, skill_root: Path, hostile: dict[str, str]
) -> None:
    env, _ = _spawned_env(sandbox, skill_root, _server_env(hostile))

    assert set(env) <= _ALLOWED_NAMES
    assert not [name for name in env if name.startswith(("AWS_", "LD_", "DYLD_"))]
    assert not [
        name for name in env if name.startswith("PYTHON") and name not in _ALLOWED_NAMES
    ]


# Feature: ai-workflow-builder, Property 4: The script environment is an allow-list
@settings(max_examples=100, deadline=None)
@given(hostile=_HOSTILE_ENVS)
def test_run_command_passes_no_server_value_when_server_env_is_hostile(
    sandbox: BuilderSandbox, skill_root: Path, hostile: dict[str, str]
) -> None:
    env, _ = _spawned_env(sandbox, skill_root, _server_env(hostile))

    assert not [name for name, value in env.items() if _CANARY in value]


# Feature: ai-workflow-builder, Property 4: The script environment is an allow-list
@settings(max_examples=100, deadline=None)
@given(
    hostile=_HOSTILE_ENVS,
    system_root=_VALUES,
    path_ext=_VALUES,
)
def test_run_command_passes_only_platform_names_when_windows_variables_are_hostile(
    sandbox: BuilderSandbox,
    skill_root: Path,
    hostile: dict[str, str],
    system_root: str,
    path_ext: str,
) -> None:
    server_env = {**hostile, "SYSTEMROOT": system_root, "PATHEXT": path_ext}
    env, tmp = _spawned_env(sandbox, skill_root, server_env)

    assert set(env) == _ALLOWED_NAMES
    for name in _TEMP_NAMES:
        assert env[name] == str(tmp)
    if not _IS_WINDOWS:
        assert not set(env) & _WINDOWS_ONLY_NAMES
        assert not [name for name, value in env.items() if _CANARY in value]
