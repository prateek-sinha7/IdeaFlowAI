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
    """exec stays OFF: ``exec_command`` raises under the default ExecutionPolicy."""
    ws = _make_workspace(tmp_path)
    ws.clone_repo(str(local_git_fixture))

    # Default policy denies exec (exec=False).
    assert ws.policy.allows("exec") is False
    with pytest.raises(PermissionError):
        ws.exec_command("echo hi")


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


def test_runtime_is_isolation_provider_shaped() -> None:
    """The runtime layer exposes the IsolationProvider port (shared_read/per-run)."""
    # The port is importable and the local runtime satisfies its structural shape
    # where applicable (allocate is downstream — 09-02; the port must exist now).
    assert hasattr(IsolationProvider, "allocate")
