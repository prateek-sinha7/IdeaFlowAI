"""Wave-0 acceptance for the local workspace runtime (Phase 09 / RUNTIME-01).

Drives the net-new runtime port layer fully OFFLINE (no DB / Bedrock / API key /
network): a ``local_git_fixture`` (conftest) seeds a tiny REAL git repo on disk,
and ``LocalSandboxRuntime`` — resolved via the capability registry handle
``("runtime_env", "local")`` — clones it into a per-run dir, branches, round-trips
read/write/search, and produces a non-empty ``git_diff`` after an edit.

The exec-denied test pins the no-exec invariant for the phase: ``exec_command``
must raise under the default ``ExecutionPolicy`` (exec OFF until N3 / Phase 4B).

This file is RED until the ports (``agents.runtime.base``) and the impl
(``app.agents.runtime.local`` registered as ``("runtime_env", "local")``) land.
It carries no live-LLM marker so CI runs it offline.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agents.capabilities.registry import CapabilityRegistry, discover
from agents.runtime.base import (
    ExecutionPolicy,
    IsolationProvider,
    RuntimeEnvironment,
    Workspace,
)


def _runtime() -> RuntimeEnvironment:
    """Resolve the registered local runtime via the capability handle."""
    discover()
    runtime = CapabilityRegistry().resolve("runtime_env", "local")
    assert isinstance(runtime, RuntimeEnvironment)
    return runtime  # type: ignore[return-value]


def _make_workspace(tmp_path: Path) -> Workspace:
    """Construct a LocalSandboxRuntime-backed Workspace rooted under a temp dir."""
    import app.core.config as config_module

    # RUNS_ROOT defaults to a non-writable /app/runs; point it at a temp dir.
    config_module.settings.RUNS_ROOT = str(tmp_path / "runs")

    runtime = _runtime()
    ws = runtime.create_workspace(
        owner_id="anon", workspace_id="ws-test", has_git=True, exec=False
    )
    assert isinstance(ws, Workspace)
    return ws


def test_runtime_registered() -> None:
    """The local runtime self-registers under the distinct ``runtime_env`` kind."""
    discover()
    reg = CapabilityRegistry()
    assert reg.is_registered("runtime_env", "local")


def test_clone_branch_read_write_search_diff(
    local_git_fixture: Path, tmp_path: Path
) -> None:
    """Full RUNTIME-01 round-trip: clone -> branch -> read/write/search -> git_diff."""
    ws = _make_workspace(tmp_path)

    ws.clone_repo(str(local_git_fixture))
    ws.create_branch("work")

    # read_file round-trips a committed file.
    original = ws.read_file("src/app.py")
    assert "def greet" in original

    # search finds a known token across the cloned tree.
    hits = ws.search("def greet")
    assert any("src/app.py" in h for h in hits)

    # write_file edits a file, read_file reflects it.
    edited = original.replace('return f"hello {name}"', 'return f"hi {name}"')
    ws.write_file("src/app.py", edited)
    assert "hi {name}" in ws.read_file("src/app.py")

    # git_diff(base, work) returns a non-empty unified diff after the edit.
    diff = ws.git_diff("main", "work")
    assert diff.strip(), "expected a non-empty diff after editing a tracked file"
    assert "src/app.py" in diff
    assert "hi {name}" in diff


def test_exec_command_denied_under_default_policy(
    local_git_fixture: Path, tmp_path: Path
) -> None:
    """exec stays OFF: ``exec_command`` raises under the default ExecutionPolicy.

    T-09-01-02 preserved (deny default unchanged); the recorder records
    outcome="denied".
    """
    ws = _make_workspace(tmp_path)
    ws.clone_repo(str(local_git_fixture))

    recorded: list[dict] = []
    ws._recorder = lambda argv, **kw: recorded.append({"argv": argv, **kw})

    # Default policy denies exec (exec=False).
    assert ws.policy.allows("exec") is False
    with pytest.raises(PermissionError):
        ws.exec_command(["python3", "-c", "print(1)"])  # argv, not str
    assert recorded and recorded[-1]["outcome"] == "denied"


# ---------------------------------------------------------------------------
# Phase 10 — hardened argv exec_command (EXEC-PROFILE / EXEC-POLICY / caps / audit)
# ---------------------------------------------------------------------------


def _exec_workspace(tmp_path: Path, **policy_overrides):
    """An exec=True LocalWorkspace with a recorder, for the hardened-exec tests."""
    from app.agents.runtime.local import (
        DEFAULT_EXEC_PROFILE,
        LocalExecutionPolicy,
        LocalSandboxRuntime,
        LocalWorkspace,
    )
    from app.agents.sandbox import RunSandbox

    import app.core.config as config_module

    config_module.settings.RUNS_ROOT = str(tmp_path / "runs")

    fields = dict(
        exec=True,
        network=False,
        secrets=[],
        exec_allow=DEFAULT_EXEC_PROFILE.exec_allow,
        exec_deny=DEFAULT_EXEC_PROFILE.exec_deny,
        cpu_seconds=DEFAULT_EXEC_PROFILE.cpu_seconds,
        mem_mb=DEFAULT_EXEC_PROFILE.mem_mb,
        wall_seconds=DEFAULT_EXEC_PROFILE.wall_seconds,
    )
    fields.update(policy_overrides)
    policy = LocalExecutionPolicy(**fields)

    runtime = LocalSandboxRuntime()
    sandbox = RunSandbox("anon", "ws-exec", runs_root=config_module.settings.RUNS_ROOT)
    recorded: list[dict] = []
    ws = LocalWorkspace(
        owner_id="anon",
        workspace_id="ws-exec",
        runtime=runtime,
        policy=policy,
        sandbox=sandbox,
    )
    ws._recorder = lambda argv, **kw: recorded.append({"argv": argv, **kw})
    return ws, recorded


def test_exec_allow_list_runs_and_records_allowed(tmp_path: Path) -> None:
    """An allow-listed interpreter runs; recorder records outcome=allowed exit_code=0."""
    ws, recorded = _exec_workspace(tmp_path)
    out = ws.exec_command(["python3", "-c", "print('ok')"])
    assert "ok" in out
    assert recorded[-1]["outcome"] == "allowed"
    assert recorded[-1]["exit_code"] == 0


def test_exec_pre_spawn_deny_for_unlisted_command(tmp_path: Path) -> None:
    """A non-allow-listed argv[0] raises PermissionError naming it, BEFORE any spawn."""
    ws, recorded = _exec_workspace(tmp_path)

    import subprocess as _subprocess

    # If exec_command spawns anything for a denied command the test fails loudly.
    orig_run = _subprocess.run
    spawned = {"hit": False}

    def _tripwire(*a, **k):
        spawned["hit"] = True
        return orig_run(*a, **k)

    _subprocess.run = _tripwire
    try:
        with pytest.raises(PermissionError) as exc:
            ws.exec_command(["bash", "-c", "echo hi"])
    finally:
        _subprocess.run = orig_run

    assert "bash" in str(exc.value)
    assert spawned["hit"] is False, "denied command must NOT spawn a process"
    assert recorded[-1]["outcome"] == "denied"


def test_exec_empty_argv_denied_and_audited(tmp_path: Path) -> None:
    """WR-02: an empty argv is a clean, audited PermissionError (not IndexError)."""
    ws, recorded = _exec_workspace(tmp_path)
    with pytest.raises(PermissionError) as exc:
        ws.exec_command([])
    assert "empty argv" in str(exc.value)
    assert recorded[-1]["outcome"] == "denied"
    assert recorded[-1]["argv"] == []


def test_exec_deny_beats_allow(tmp_path: Path) -> None:
    """A command in BOTH exec_allow and exec_deny is rejected (deny-precedence)."""
    ws, recorded = _exec_workspace(
        tmp_path, exec_allow=("python3",), exec_deny=("python3",)
    )
    with pytest.raises(PermissionError):
        ws.exec_command(["python3", "-c", "print(1)"])
    assert recorded[-1]["outcome"] == "denied"


def test_exec_scrubbed_env_excludes_host_creds(
    tmp_path: Path, monkeypatch
) -> None:
    """The child env carries no AWS_*/ANTHROPIC_*/DATABASE_URL/*_TOKEN/*_PROXY keys."""
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "super-secret")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-secret")
    monkeypatch.setenv("DATABASE_URL", "postgres://secret")
    monkeypatch.setenv("SOME_TOKEN", "tok")
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy")

    ws, _ = _exec_workspace(tmp_path)
    out = ws.exec_command(
        ["python3", "-c", "import os,json;print(json.dumps(dict(os.environ)))"]
    )
    import json as _json

    child_env = _json.loads(out)
    for forbidden in (
        "AWS_SECRET_ACCESS_KEY",
        "ANTHROPIC_API_KEY",
        "DATABASE_URL",
        "SOME_TOKEN",
        "HTTPS_PROXY",
    ):
        assert forbidden not in child_env, f"{forbidden} leaked into the child env"

    # The env DICT the workspace constructs carries only PATH/HOME/TMPDIR (the
    # scrub). The child may still SEE a few benign darwin/toolchain-injected keys
    # (CPATH/LC_CTYPE/LIBRARY_PATH/MANPATH/SDKROOT/__CF_USER_TEXT_ENCODING) that the
    # OS launcher adds AFTER our env is applied — none are host credentials. So we
    # assert the security property directly: no host-cred CLASS key survives, rather
    # than an exact 3-key allow-list (platform-fragile on darwin, like Pitfall 4).
    cred_markers = ("AWS", "ANTHROPIC", "DATABASE", "TOKEN", "PROXY", "SECRET", "API_KEY")
    leaked = [
        k for k in child_env if any(marker in k.upper() for marker in cred_markers)
    ]
    assert not leaked, f"host-credential-class keys leaked into the child env: {leaked}"


def test_exec_wall_clock_kill_records_killed(tmp_path: Path) -> None:
    """A runaway command is killed at the wall-clock timeout; recorder records killed."""
    import subprocess

    ws, recorded = _exec_workspace(tmp_path, wall_seconds=1)
    with pytest.raises(subprocess.TimeoutExpired):
        ws.exec_command(["python3", "-c", "import time;time.sleep(30)"])
    assert recorded[-1]["outcome"] == "killed"


def test_exec_wall_clock_kills_forking_descendants(tmp_path: Path) -> None:
    """WR-01: a child that forks a grandchild has its WHOLE group killed on timeout.

    The child writes its grandchild's pid to a file then both sleep. On the
    wall-clock timeout the workspace must ``os.killpg`` the new session group so
    NO descendant survives — ``subprocess.run``'s direct-child ``proc.kill()``
    would leave the grandchild orphaned and running.
    """
    import os as _os
    import subprocess
    import time as _time

    ws, recorded = _exec_workspace(tmp_path, wall_seconds=1)
    pidfile = tmp_path / "grandchild.pid"
    script = (
        "import os,sys,time\n"
        "pid=os.fork()\n"
        "if pid==0:\n"  # grandchild
        f"    open({str(pidfile)!r},'w').write(str(os.getpid()))\n"
        "    time.sleep(30)\n"
        "    sys.exit(0)\n"
        "time.sleep(30)\n"
    )
    with pytest.raises(subprocess.TimeoutExpired):
        ws.exec_command(["python3", "-c", script])
    assert recorded[-1]["outcome"] == "killed"

    # The grandchild must be dead (group kill). Give the SIGKILL a beat to land.
    _time.sleep(0.5)
    assert pidfile.exists(), "grandchild never recorded its pid"
    gc_pid = int(pidfile.read_text())

    def _alive(pid: int) -> bool:
        try:
            _os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    assert not _alive(gc_pid), (
        f"grandchild {gc_pid} survived the wall-clock kill — process group not killed"
    )


def test_exec_output_truncated_at_64kb(tmp_path: Path) -> None:
    """Output exceeding 64KB/stream is truncated to 64KB."""
    ws, _ = _exec_workspace(tmp_path)
    # Emit ~200KB to stdout; expect a 64KB-truncated return.
    out = ws.exec_command(
        ["python3", "-c", "import sys;sys.stdout.write('x'*200000)"]
    )
    assert len(out) == 65536, f"expected 64KB truncation, got {len(out)}"


def test_exec_rlimit_mechanism_applied(tmp_path: Path) -> None:
    """The preexec_fn calls resource.setrlimit for RLIMIT_CPU and RLIMIT_AS.

    Asserts the MECHANISM is applied (Pitfall 4: RLIMIT_AS is best-effort on darwin,
    so an OOM-kill assertion would be flaky). We have the child report its OWN soft
    limits — if the preexec_fn set them, the child sees the capped values.
    """
    import resource

    ws, _ = _exec_workspace(tmp_path, cpu_seconds=42, mem_mb=256)
    out = ws.exec_command(
        [
            "python3",
            "-c",
            "import resource,json;"
            "print(json.dumps([resource.getrlimit(resource.RLIMIT_CPU)[0],"
            "resource.getrlimit(resource.RLIMIT_AS)[0]]))",
        ]
    )
    import json as _json

    cpu_soft, as_soft = _json.loads(out)
    assert cpu_soft == 42, "RLIMIT_CPU soft limit not applied in the child"
    # RLIMIT_AS is best-effort on darwin; assert it is either the cap or RLIM_INFINITY
    # (the darwin no-op) — never an unrelated value.
    assert as_soft in (256 * 1024 * 1024, resource.RLIM_INFINITY)


def test_default_exec_profile_caps_are_locked() -> None:
    """DEFAULT_EXEC_PROFILE carries the N3-locked caps (cpu=60 mem=512 wall=120)."""
    from app.agents.runtime.local import DEFAULT_EXEC_PROFILE

    assert DEFAULT_EXEC_PROFILE.exec_allow == ("python", "python3", "pytest", "ruff")
    assert DEFAULT_EXEC_PROFILE.cpu_seconds == 60
    assert DEFAULT_EXEC_PROFILE.mem_mb == 512
    assert DEFAULT_EXEC_PROFILE.wall_seconds == 120


def test_grown_policy_keeps_allows_exec_byte_identical() -> None:
    """LocalExecutionPolicy grows allow/deny + caps; allows('exec') still returns self.exec."""
    from app.agents.runtime.local import LocalExecutionPolicy

    deny = LocalExecutionPolicy()
    assert deny.allows("exec") is False
    grant = LocalExecutionPolicy(exec=True, exec_allow=("python3",))
    assert grant.allows("exec") is True
    # The new cap fields exist with the locked defaults.
    assert deny.cpu_seconds == 60 and deny.mem_mb == 512 and deny.wall_seconds == 120
    assert deny.exec_allow == () and deny.exec_deny == ()


def test_default_execution_policy_denies_privileged_actions() -> None:
    """The default ExecutionPolicy (concrete impl) denies exec / network / secrets."""
    from app.agents.runtime.local import LocalExecutionPolicy

    policy = LocalExecutionPolicy()
    # The concrete default satisfies the ExecutionPolicy port structurally.
    assert isinstance(policy, ExecutionPolicy)
    assert policy.allows("exec") is False
    assert policy.allows("network") is False
    assert policy.allows("secrets") is False


def test_path_traversal_rejected(local_git_fixture: Path, tmp_path: Path) -> None:
    """Untrusted relpaths cannot escape the run root (T-09-01-01)."""
    ws = _make_workspace(tmp_path)
    ws.clone_repo(str(local_git_fixture))

    with pytest.raises(ValueError):
        ws.read_file("../../../../etc/passwd")
    with pytest.raises(ValueError):
        ws.write_file("../escape.txt", "nope")


def test_teardown_removes_run_dir_without_recursion(
    local_git_fixture: Path, tmp_path: Path
) -> None:
    """``runtime.teardown(ws)`` deletes the run dir and does not raise (CR-01).

    Pins the cycle-free teardown seam: ``LocalWorkspace.teardown`` delegates to
    ``RunSandbox.cleanup`` (the single rmtree owner) — never the reverse — so
    BOTH entry points delete the directory exactly once with no RecursionError.
    """
    ws = _make_workspace(tmp_path)
    ws.clone_repo(str(local_git_fixture))
    run_root = Path(ws._root)
    assert run_root.is_dir()

    runtime = _runtime()
    runtime.teardown(ws)  # must not raise (pre-fix: RecursionError)
    assert not run_root.exists(), "teardown must remove the run dir"

    # Idempotent: a second teardown (and a direct sandbox cleanup) is a no-op.
    runtime.teardown(ws)
    ws._sandbox.cleanup()


def test_runsandbox_cleanup_direct_entry_removes_run_dir(tmp_path: Path) -> None:
    """The sandbox facade entry point also deletes exactly once, no recursion."""
    from app.agents.sandbox import RunSandbox

    sb = RunSandbox("u", "r", runs_root=str(tmp_path / "runs"))
    root = sb.ensure()
    assert root.is_dir()
    sb.cleanup()  # pre-fix: RecursionError via the Workspace round-trip
    assert not root.exists()
    sb.cleanup()  # idempotent


# ---------------------------------------------------------------------------
# CR-01 regression — the REAL engine recorder adapter through exec_command
# ---------------------------------------------------------------------------


class _FakeRunner:
    """A stand-in for ``KernelServices`` exposing the async ``record_exec_run``.

    Records each call's positional/keyword arguments so the test asserts the
    workspace recorder bridged to the async sink with the correct outcome — the
    contract that the OLD direct-binding wiring (``recorder=record_exec_run``)
    could never satisfy (it raised ``TypeError`` and never awaited).
    """

    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def record_exec_run(
        self,
        step,
        argv,
        outcome,
        *,
        exit_code=None,
        duration_ms=None,
        policy_snapshot=None,
        output_digest=None,
    ):
        self.calls.append(
            {
                "step": step,
                "argv": argv,
                "outcome": outcome,
                "exit_code": exit_code,
                "duration_ms": duration_ms,
            }
        )
        return "exec-row-id"


@pytest.mark.asyncio
async def test_real_engine_recorder_adapter_audits_every_outcome(tmp_path: Path) -> None:
    """The engine's sync→async recorder adapter audits allowed/denied/killed (CR-01).

    Wires the REAL ``_make_exec_recorder`` adapter (the host-seam shape) as the
    workspace recorder — NOT a hand-rolled sync lambda — and drives ``exec_command``
    inside a running event loop. Asserts ``record_exec_run`` was invoked with the
    right outcome for each path, and that the exec contract is preserved (denied →
    PermissionError, killed → TimeoutExpired, allowed → stdout). This test FAILS
    against the OLD wiring (``recorder=runner.record_exec_run`` raised TypeError on
    the single positional argv binding to ``step`` and never awaited the coroutine).
    """
    import asyncio
    import subprocess

    from agents.execution_engine.engine import _make_exec_recorder

    runner = _FakeRunner()
    adapter = _make_exec_recorder(runner)

    ws, _ = _exec_workspace(tmp_path, wall_seconds=1)
    ws._recorder = adapter

    # allowed
    out = ws.exec_command(["python3", "-c", "print('ok')"])
    assert "ok" in out  # exec contract: allowed returns stdout

    # denied (unlisted argv[0]) — must raise PermissionError, NOT TypeError.
    with pytest.raises(PermissionError):
        ws.exec_command(["bash", "-c", "echo hi"])

    # killed (wall-clock timeout) — must raise TimeoutExpired.
    with pytest.raises(subprocess.TimeoutExpired):
        ws.exec_command(["python3", "-c", "import time;time.sleep(30)"])

    # The adapter scheduled the async writes on the running loop — let them run.
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    outcomes = [c["outcome"] for c in runner.calls]
    assert "allowed" in outcomes, "allowed exec must be audited via record_exec_run"
    assert "denied" in outcomes, "denied exec must be audited via record_exec_run"
    assert "killed" in outcomes, "killed exec must be audited via record_exec_run"
    # The bridged call passes argv as a list and a (run-scoped) step placeholder.
    allowed_call = next(c for c in runner.calls if c["outcome"] == "allowed")
    assert allowed_call["argv"] == ["python3", "-c", "print('ok')"]
    assert allowed_call["exit_code"] == 0


def test_runtime_is_isolation_provider_shaped() -> None:
    """The runtime layer exposes the IsolationProvider port (shared_read/per-run)."""
    # The port is importable and the local runtime satisfies its structural shape
    # where applicable (allocate is downstream — 09-02; the port must exist now).
    assert hasattr(IsolationProvider, "allocate")
