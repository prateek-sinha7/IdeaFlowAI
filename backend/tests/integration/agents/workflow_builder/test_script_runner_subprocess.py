"""Integration tests for the workflow builder's script runner with real subprocesses.

These tests start real child processes through ``run_command`` and the default
``spawn_process``; nothing about the process layer is faked. They need no Docker
and no database: the sandbox and a copy of the skill live under ``tmp_path``, the
gate and the turn are the in-memory fakes.

Covered:

* the six real scripts of the builder skill run against a sandbox and a skill copy
  (Req 35.5 for ``selftest.py``, 18.3 and 32.11 for the skill staying untouched);
* no ``__pycache__`` is written, with a control run that proves the check can fail
  (Req 34.5, 32.11);
* the environment a child sees is the allow-list and nothing else (Req 36.3);
* a sleeping stub is stopped by the timeout (Req 36.5, 36.8);
* cancelling the call kills the child and removes its temp folder;
* output past the cap is cut, keeps the verdict line and fits the cap (Req 36.5);
* ``git status --porcelain`` of the skill folder is the same before and after
  the six scripts run against the real skill (Req 18.3,
  32.11).

The stub scripts replace only the script file in the argv that the runner builds,
through a recording spawner, so the interpreter flags, working directory,
environment and stdin are exactly what a real call gets.

Requirements: 18.3, 32.11, 34.5, 35.5, 36.3, 36.5, 36.8, 49.5.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import sys
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest

from app.agents.workflow_builder.events import CheckResultEvent
from app.agents.workflow_builder.sandbox import BuilderSandbox
from app.agents.workflow_builder.script_policy import BUILDER_SKILL_ID
from app.agents.workflow_builder.script_runner import (
    ProcessLike,
    ScriptContext,
    ScriptResult,
    run_command,
    spawn_process,
)
from app.agents.workflow_builder.skill_package import SKILL_DIR
from app.core.config import settings
from tests.fakes.builder_gate import FakeGate
from tests.fakes.builder_turn import FakeTurnPort

BACKEND_DIR = Path(__file__).resolve().parents[4]
REPO_ROOT = BACKEND_DIR.parent
SKILL_FOLDER = SKILL_DIR

MANIFEST_PATH = "/workflows/a.workflow.json"
MANIFEST: dict[str, Any] = {
    "id": "subprocess-check",
    "planner": "skip",
    "clarify": {"mode": "skip", "defaults": []},
    "deliverable": {"strategy": "single_file", "name": "out.md"},
    "steps": [
        {
            "agent": "custom-agent",
            "instance_id": "a",
            "name": "A",
            "prompt": "Do the a work.",
            "gates": [],
        }
    ],
}

# Three spellings of the skill folder that the runner maps to the skill folder
# (Req 34.6). The git test cycles through them.
SKILL_PREFIXES = (
    f"/skills/{BUILDER_SKILL_ID}",
    f"app\\agents\\workflow_builder\\skills\\{BUILDER_SKILL_ID}",
    f"backend/app/agents/workflow_builder/skills/{BUILDER_SKILL_ID}",
)

# One command per real script, each written the way the skill writes it.
SIX_SCRIPTS: tuple[tuple[str, str], ...] = (
    (
        "catalog_lookup.py",
        "python {skill}/scripts/catalog_lookup.py overview --trust user",
    ),
    (
        "validate_manifest.py",
        "python {skill}/scripts/validate_manifest.py "
        + MANIFEST_PATH
        + " --trust user",
    ),
    ("selftest.py", "python {skill}/scripts/selftest.py"),
    ("refresh_catalog.py", "python {skill}/scripts/refresh_catalog.py --check"),
    ("schema_sync.py", "python {skill}/scripts/schema_sync.py --check"),
    (
        "export_manifest.py",
        "python {skill}/scripts/export_manifest.py "
        + MANIFEST_PATH
        + " --save-payload /exports/payload.json",
    ),
)

# The oracle for Req 36.3. Restated here on purpose: it does not import the
# runner's own constant, so a name added to the runner shows up as a failure.
ALLOWED_ENV_NAMES = frozenset(
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

CANARY = "CANARY-7f3a91"
HOSTILE_ENV = {
    "DATABASE_URL": f"postgresql://user:{CANARY}@db/app",
    "AWS_ACCESS_KEY_ID": f"AKIA{CANARY}",
    "AWS_SECRET_ACCESS_KEY": CANARY,
    "AWS_SESSION_TOKEN": CANARY,
    "COGNITO_CLIENT_SECRET": CANARY,
    "VELOCITY_API_TOKEN": CANARY,
    "JWT_SIGNING_KEY": CANARY,
    "OPENAI_API_KEY": CANARY,
    "ANTHROPIC_API_KEY": CANARY,
    "HTTPS_PROXY": f"http://{CANARY}:3128",
    "PYTHONPATH": f"/{CANARY}",
    "PYTHONSTARTUP": f"/{CANARY}/startup.py",
    "SOME_FUTURE_SECRET": CANARY,
    # Allow-listed names carrying hostile values: the child must get its own.
    "HOME": f"/{CANARY}/home",
    "USERPROFILE": f"/{CANARY}/profile",
    "TMPDIR": f"/{CANARY}/tmp",
}

# --- stub scripts (they replace the script file, nothing else) ------------------

ENV_STUB = """\
import json, os, sys
print(json.dumps({
    "env": dict(os.environ),
    "cwd": os.getcwd(),
    "stdin": sys.stdin.read(),
    "argv": sys.argv[1:],
    "dont_write_bytecode": sys.dont_write_bytecode,
    "no_user_site": sys.flags.no_user_site,
    "utf8_mode": sys.flags.utf8_mode,
}))
"""

# Appends a dot to heartbeat.txt (in the working directory) every 50 ms. It gives
# up after 60 s on its own, so a runner that fails to kill it cannot leave an orphan.
SLEEPING_STUB = """\
import time
end = time.monotonic() + 60
with open("heartbeat.txt", "ab", buffering=0) as beat:
    while time.monotonic() < end:
        beat.write(b".")
        time.sleep(0.05)
"""

FLOOD_STUB = """\
import sys
line = "x" * 99 + "\\n"
for _ in range(2000):
    sys.stdout.write(line)
sys.stdout.write("INVALID: 3 error(s), 1 warning(s)\\n")
sys.exit(1)
"""

# --- helpers --------------------------------------------------------------------


class RecordingSpawner:
    """The real ``spawn_process``, optionally swapping the script for a stub.

    The runner builds ``[python, -B, -s, -X, utf8, <script>, *args]``. A stub takes
    the script's place and everything else (flags, args, cwd, env, pipes) is kept.
    """

    def __init__(self, stub: Path | None = None) -> None:
        self.stub = stub
        self.argvs: list[list[str]] = []
        self.processes: list[ProcessLike] = []

    async def __call__(
        self, argv: Sequence[str], *, cwd: Path, env: Mapping[str, str]
    ) -> ProcessLike:
        args = list(argv)
        if self.stub is not None:
            args[5] = str(self.stub)
        self.argvs.append(args)
        process = await spawn_process(args, cwd=cwd, env=env)
        self.processes.append(process)
        return process


def _write_stub(tmp_path: Path, source: str) -> Path:
    stub = tmp_path / "stub_script.py"
    stub.write_text(source, encoding="utf-8")
    return stub


def _make_ctx(
    sandbox: BuilderSandbox,
    skill_root: Path,
    *,
    spawn: RecordingSpawner | None = None,
    call_id: str = "call-1",
    finished: list[tuple[str, ScriptResult]] | None = None,
    **overrides: Any,
) -> tuple[ScriptContext, FakeTurnPort]:
    turn = FakeTurnPort()
    sink = finished if finished is not None else []
    ctx = ScriptContext(
        sandbox=sandbox,
        skill_root=skill_root,
        gate=FakeGate(),
        turn=turn,
        semaphore=asyncio.Semaphore(2),
        spawn=spawn if spawn is not None else spawn_process,
        call_id=call_id,
        on_finished=lambda cid, result: sink.append((cid, result)),
        **overrides,
    )
    return ctx, turn


def _pycache_dirs(root: Path) -> list[str]:
    return sorted(
        p.relative_to(root).as_posix() for p in root.rglob("__pycache__") if p.is_dir()
    )


def _tree_snapshot(folder: Path) -> list[tuple[str, str, int, int]]:
    """Every file and folder under ``folder`` with size and mtime, for a before/after diff."""
    rows: list[tuple[str, str, int, int]] = []
    for path in sorted(folder.rglob("*")):
        info = path.stat()
        kind = "dir" if path.is_dir() else "file"
        size = 0 if path.is_dir() else info.st_size
        rows.append((path.relative_to(folder).as_posix(), kind, size, info.st_mtime_ns))
    return rows


def _porcelain(paths: Sequence[Path]) -> str:
    try:
        done = subprocess.run(
            [
                "git",
                "-C",
                str(REPO_ROOT),
                "status",
                "--porcelain",
                "--untracked-files=all",
                "--",
                *[str(p) for p in paths],
            ],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except FileNotFoundError:
        pytest.skip("git is not installed")
    if done.returncode != 0:
        pytest.skip(f"git status failed: {done.stderr.strip()[:200]}")
    return done.stdout


async def _wait_for_heartbeat(sandbox: BuilderSandbox, seconds: float = 15.0) -> Path:
    beat = sandbox.path / "heartbeat.txt"
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if beat.exists() and beat.stat().st_size > 0:
            return beat
        await asyncio.sleep(0.05)
    raise AssertionError("the stub never started writing its heartbeat")


async def _assert_heartbeat_stopped(beat: Path) -> None:
    """A dead child cannot append: the file stops growing."""
    first = beat.stat().st_size
    await asyncio.sleep(0.5)
    assert beat.stat().st_size == first


def _platform_injected_names() -> frozenset[str]:
    """Names the platform adds to any child, whatever env the parent passes.

    Some Windows endpoint-security agents inject variables into every new process
    (seen: ``BPPDOMAIN_MANAGER_*``). They are not the runner's doing and not the
    server's secrets, so the allow-list check must not blame the runner for them.
    A bare interpreter started with an empty environment shows which names those
    are; a name the server's own environment could leak is never among them.
    """
    bare = {"SYSTEMROOT": os.environ["SYSTEMROOT"]} if sys.platform == "win32" else {}
    done = subprocess.run(
        [sys.executable, "-c", "import json, os; print(json.dumps(list(os.environ)))"],
        capture_output=True,
        env=bare,
        text=True,
        timeout=60,
        check=True,
    )
    hostile = {name.upper() for name in HOSTILE_ENV}
    return frozenset(name.upper() for name in json.loads(done.stdout)) - hostile


def _env_payload(result: ScriptResult) -> dict[str, Any]:
    header, code, body = result.text.split("\n", 2)
    assert header.startswith("$ ")
    assert code == "exit code: 0"
    return json.loads(body)


# --- fixtures --------------------------------------------------------------------


@pytest.fixture
def sandbox(tmp_path: Path) -> BuilderSandbox:
    box = BuilderSandbox("user-1", "session-1", root=tmp_path / "builder")
    box.ensure()
    manifest = box.path_for(MANIFEST_PATH)
    manifest.write_text(json.dumps(MANIFEST), encoding="utf-8")
    return box


@pytest.fixture
def skill_copy(tmp_path: Path) -> Path:
    """A copy of the builder skill under ``tmp_path``, without any bytecode."""
    assert SKILL_FOLDER.is_dir(), f"the builder skill is missing: {SKILL_FOLDER}"
    target = tmp_path / "skills" / BUILDER_SKILL_ID
    shutil.copytree(SKILL_FOLDER, target, ignore=shutil.ignore_patterns("__pycache__"))
    return target


# --- the six real scripts --------------------------------------------------------


@pytest.mark.parametrize(
    ("script", "template"), SIX_SCRIPTS, ids=[name for name, _ in SIX_SCRIPTS]
)
async def test_run_command_exits_zero_when_a_real_skill_script_runs_in_a_sandbox(
    script: str, template: str, sandbox: BuilderSandbox, skill_copy: Path
) -> None:
    command = template.format(skill=SKILL_PREFIXES[0])
    finished: list[tuple[str, ScriptResult]] = []
    ctx, turn = _make_ctx(
        sandbox, skill_copy, call_id=f"call-{script}", finished=finished
    )

    result = await run_command(command, ctx)

    assert result.script == script
    assert result.status == "ok"
    assert result.exit_code == 0
    assert result.text.startswith(f"$ {command}\nexit code: 0\n")
    assert len(result.text) > len(f"$ {command}\nexit code: 0\n")
    assert [cid for cid, _ in finished] == [f"call-{script}"]
    assert list((sandbox.path / ".tmp").iterdir()) == []
    if script == "validate_manifest.py":
        assert result.verdict == "valid"
        sources = [e.source for e in turn.events if isinstance(e, CheckResultEvent)]
        assert sources == ["skill_validator"]
    if script == "selftest.py":
        assert "checks passed" in result.text
    if script == "export_manifest.py":
        payload = json.loads(
            (sandbox.path / "exports" / "payload.json").read_text("utf-8")
        )
        assert isinstance(payload, dict)


async def test_run_command_writes_no_bytecode_when_all_six_scripts_run(
    sandbox: BuilderSandbox, skill_copy: Path
) -> None:
    for script, template in SIX_SCRIPTS:
        ctx, _ = _make_ctx(sandbox, skill_copy, call_id=f"call-{script}")

        result = await run_command(template.format(skill=SKILL_PREFIXES[0]), ctx)

        assert result.exit_code == 0, result.text

    assert _pycache_dirs(skill_copy) == []
    assert _pycache_dirs(sandbox.path) == []


def test_python_writes_pycache_into_the_copy_when_bytecode_writing_is_left_on(
    skill_copy: Path,
) -> None:
    """Control for the test above: without ``-B`` the same script does leave bytecode."""
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in {"PYTHONDONTWRITEBYTECODE", "PYTHONPYCACHEPREFIX"}
    }
    script = skill_copy / "scripts" / "catalog_lookup.py"

    done = subprocess.run(
        [sys.executable, str(script), "overview"],
        capture_output=True,
        env=env,
        timeout=120,
        check=False,
    )

    assert done.returncode == 0, done.stderr.decode("utf-8", "replace")[-500:]
    assert _pycache_dirs(skill_copy) != []


# --- environment seen by a child -------------------------------------------------


async def test_run_command_gives_the_child_only_allow_listed_variables_when_the_server_holds_secrets(
    sandbox: BuilderSandbox,
    skill_copy: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name, value in HOSTILE_ENV.items():
        monkeypatch.setenv(name, value)
    spawner = RecordingSpawner(_write_stub(tmp_path, ENV_STUB))
    ctx, _ = _make_ctx(sandbox, skill_copy, spawn=spawner, call_id="call-env")
    command = f"python {SKILL_PREFIXES[0]}/scripts/catalog_lookup.py overview"

    result = await run_command(command, ctx)

    assert result.status == "ok", result.text
    seen = _env_payload(result)
    env = {name.upper(): value for name, value in seen["env"].items()}
    call_tmp = str(sandbox.path / ".tmp" / "call-env")
    assert set(env) <= ALLOWED_ENV_NAMES | _platform_injected_names()
    assert not {n for n in HOSTILE_ENV if n not in ALLOWED_ENV_NAMES} & set(env)
    assert all(CANARY not in value for value in env.values())
    assert env["PYTHONDONTWRITEBYTECODE"] == "1"
    assert env["PYTHONIOENCODING"] == "utf-8"
    assert env["TMP"] == env["TEMP"] == env["TMPDIR"] == call_tmp
    assert env["HOME"] == call_tmp
    assert seen["dont_write_bytecode"] is True
    assert seen["no_user_site"] == 1
    assert seen["utf8_mode"] == 1
    assert Path(seen["cwd"]).resolve() == sandbox.path
    assert seen["stdin"] == ""
    assert spawner.argvs[0][:5] == [sys.executable, "-B", "-s", "-X", "utf8"]


# --- timeout, cancel -------------------------------------------------------------


async def test_run_command_stops_a_sleeping_child_when_the_timeout_passes(
    sandbox: BuilderSandbox,
    skill_copy: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The context leaves timeout_seconds unset, so the setting is what stops the child.
    monkeypatch.setattr(settings, "BUILDER_SCRIPT_TIMEOUT_SECONDS", 2)
    spawner = RecordingSpawner(_write_stub(tmp_path, SLEEPING_STUB))
    finished: list[tuple[str, ScriptResult]] = []
    ctx, _ = _make_ctx(
        sandbox,
        skill_copy,
        spawn=spawner,
        call_id="call-sleep",
        finished=finished,
    )
    started = time.monotonic()

    result = await run_command(
        f"python {SKILL_PREFIXES[0]}/scripts/catalog_lookup.py overview", ctx
    )

    assert time.monotonic() - started < 30
    assert result.status == "timed_out"
    assert result.exit_code is None
    assert result.text.startswith(
        f"$ python {SKILL_PREFIXES[0]}/scripts/catalog_lookup.py"
    )
    assert "exit code: none" in result.text
    assert "[timed out after 2 s; the script was stopped]" in result.text
    assert [r.status for _, r in finished] == ["timed_out"]
    assert spawner.processes[0].returncode is not None
    assert not (sandbox.path / ".tmp" / "call-sleep").exists()
    await _assert_heartbeat_stopped(await _wait_for_heartbeat(sandbox))


async def test_run_command_kills_the_child_when_the_call_is_cancelled(
    sandbox: BuilderSandbox, skill_copy: Path, tmp_path: Path
) -> None:
    spawner = RecordingSpawner(_write_stub(tmp_path, SLEEPING_STUB))
    finished: list[tuple[str, ScriptResult]] = []
    ctx, _ = _make_ctx(
        sandbox,
        skill_copy,
        spawn=spawner,
        call_id="call-cancel",
        finished=finished,
        timeout_seconds=120.0,
    )
    task = asyncio.create_task(
        run_command(
            f"python {SKILL_PREFIXES[0]}/scripts/catalog_lookup.py overview", ctx
        )
    )
    beat = await _wait_for_heartbeat(sandbox)

    cancelled_at = time.monotonic()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    # Killed, not waited out: the stub would otherwise run for 60 s.
    assert time.monotonic() - cancelled_at < 10
    assert spawner.processes[0].returncode is not None
    assert not (sandbox.path / ".tmp" / "call-cancel").exists()
    assert [(cid, r.status) for cid, r in finished] == [("call-cancel", "error")]
    await _assert_heartbeat_stopped(beat)


# --- output cap ------------------------------------------------------------------


async def test_run_command_cuts_the_output_and_keeps_the_verdict_when_a_child_prints_too_much(
    sandbox: BuilderSandbox, skill_copy: Path, tmp_path: Path
) -> None:
    spawner = RecordingSpawner(_write_stub(tmp_path, FLOOD_STUB))
    ctx, turn = _make_ctx(sandbox, skill_copy, spawn=spawner, call_id="call-flood")
    command = f"python {SKILL_PREFIXES[0]}/scripts/validate_manifest.py {MANIFEST_PATH}"

    result = await run_command(command, ctx)

    verdict_line = "INVALID: 3 error(s), 1 warning(s)"
    assert len(result.text) <= settings.BUILDER_SCRIPT_OUTPUT_CAP_CHARS
    assert result.text.startswith(f"$ {command}\nexit code: 1\n")
    assert " characters cut ...]" in result.text
    assert result.text.rstrip().endswith(verdict_line)
    assert result.status == "ok"
    assert result.verdict == "invalid"
    assert (result.errors, result.warnings) == (3, 1)
    checks = [e for e in turn.events if isinstance(e, CheckResultEvent)]
    assert [(e.source, e.verdict, e.errors, e.warnings) for e in checks] == [
        ("skill_validator", "invalid", 3, 1)
    ]


# --- the skill folders stay untouched --------------------------------------------


async def test_run_command_leaves_skill_folder_unchanged_when_six_scripts_run(
    sandbox: BuilderSandbox,
) -> None:
    if not (REPO_ROOT / ".git").exists():
        pytest.skip("the git checkout is not available")
    folders = (SKILL_FOLDER,)
    porcelain_before = _porcelain(folders)
    trees_before = [_tree_snapshot(folder) for folder in folders]

    for index, (script, template) in enumerate(SIX_SCRIPTS):
        prefix = SKILL_PREFIXES[index % len(SKILL_PREFIXES)]
        ctx, _ = _make_ctx(sandbox, SKILL_FOLDER, call_id=f"call-{script}")

        result = await run_command(template.format(skill=prefix), ctx)

        assert result.exit_code == 0, result.text

    assert _porcelain(folders) == porcelain_before
    # The tree snapshot lists every folder, so a new __pycache__ (ignored by git,
    # hence invisible to porcelain) or a touched file shows up as a difference.
    assert [_tree_snapshot(folder) for folder in folders] == trees_before
