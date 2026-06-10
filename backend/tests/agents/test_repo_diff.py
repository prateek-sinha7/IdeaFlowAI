"""Wave-0 acceptance for the brownfield ``repo_diff`` deliverable resolver (Phase 09 / REPO-04).

Drives ``repo_diff`` OFFLINE over a real cloned local git repo (reusing the
``local_git_fixture`` seeder from 09-01):

  * clone the fixture into a per-run ``LocalWorkspace``,
  * branch ``work`` off ``main``,
  * edit ≥1 file on ``work``,
  * resolve ``repo_diff`` and assert it returns a **file tree**, a **per-file
    unified diff CONTAINING the edit**, and a **change summary** (file count +
    lines added / removed),
  * assert it is **diff-only**: no ``git commit`` / ``git push`` lives in the
    resolver source, and resolving the diff pushes NOTHING to any remote (no
    remote is even configured — the brownfield path surfaces a diff, never a PR,
    until N4).

The resolver reads the diff via the ``Workspace`` handle (``ctx.runner.workspace``)
— it never shells git itself (D-10 / the Workspace is the single git owner).
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from agents.capabilities.registry import CapabilityRegistry, discover


# ── offline harness: a runner exposing the cloned LocalWorkspace as .workspace ──
class _FakeRunner:
    def __init__(self, workspace: Any) -> None:
        self.workspace = workspace


class _FakeCtx:
    def __init__(self, runner: _FakeRunner, *, base_branch: str, working_branch: str) -> None:
        self.runner = runner
        self.base_branch = base_branch
        self.working_branch = working_branch


def _resolver():
    discover()
    return CapabilityRegistry().resolve("deliverable", "repo_diff")


def _git_lines(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=str(cwd), check=True, capture_output=True, text=True
    ).stdout


@pytest.fixture()
def cloned_workspace(local_git_fixture: Path, tmp_path: Path):
    """Clone the fixture into a LocalWorkspace, branch ``work``, edit a file.

    Returns ``(workspace, run_root)`` with the ``work`` branch checked out and one
    file (``src/app.py``) edited + committed on ``work`` (the user/agent edit). The
    resolver then reads the ``main..work`` diff without performing any commit itself.
    """
    import app.core.config as config_module

    from app.agents.runtime.local import LocalSandboxRuntime

    # RUNS_ROOT defaults to a non-writable /app/runs; point it at a temp dir.
    config_module.settings.RUNS_ROOT = str(tmp_path / "runs")

    runtime = LocalSandboxRuntime()
    ws = runtime.create_workspace(
        owner_id="anon", workspace_id="repo-diff-ws", has_git=True, exec=False
    )
    ws.clone_repo(str(local_git_fixture))
    ws.create_branch("work")

    # The agent edits a file (write_files) — no exec. Mirror an in-place edit to
    # the greet() helper so the surfaced diff carries the agent's change.
    ws.write_file(
        "src/app.py",
        '"""Sample module."""\n\n\ndef greet(name: str) -> str:\n'
        '    return f"hello dear {name}"\n',
    )
    run_root = Path(ws._root)
    # Commit the agent edit onto the work branch (the agent/workflow's own commit,
    # NOT the resolver's — the resolver must perform no commit/push of its own).
    _git_lines(run_root, "-c", "user.name=t", "-c", "user.email=t@t", "add", "-A")
    _git_lines(run_root, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-m", "agent edit")
    return ws, run_root


def test_repo_diff_returns_tree_diff_and_summary(cloned_workspace) -> None:
    ws, _run_root = cloned_workspace
    ctx = _FakeCtx(_FakeRunner(ws), base_branch="main", working_branch="work")

    result = _resolver().resolve(ctx)

    # File tree: the changed file is listed.
    assert "src/app.py" in result["tree"], result["tree"]
    assert result["tree"] == sorted(result["tree"])

    # Per-file unified diff CONTAINING the agent's edit.
    per_file = result["diffs"]
    assert "src/app.py" in per_file
    app_diff = per_file["src/app.py"]
    assert "diff --git" in app_diff
    assert "+    return f\"hello dear {name}\"" in app_diff, app_diff
    # The full unified diff also carries the edit.
    assert "hello dear" in result["diff"]

    # Change summary: file count + lines added / removed.
    summary = result["summary"]
    assert summary["files_changed"] == 1
    assert summary["lines_added"] >= 1
    assert summary["lines_removed"] >= 1


def test_repo_diff_performs_no_commit_or_push(cloned_workspace, local_git_fixture) -> None:
    """The resolver is diff-only: resolving it creates NO new commit on ``work`` and
    pushes NOTHING — the cloned ``origin`` (the local fixture) gains no ``work`` ref.

    (``git clone`` always wires an ``origin`` remote at the source path; the diff-only
    contract is that the resolver never PUSHES the working branch to it — N4 / N5.)
    """
    ws, run_root = cloned_workspace
    ctx = _FakeCtx(_FakeRunner(ws), base_branch="main", working_branch="work")

    head_before = _git_lines(run_root, "rev-parse", "work").strip()
    count_before = _git_lines(run_root, "rev-list", "--count", "work").strip()
    # The fixture (origin) branches BEFORE the resolver runs.
    origin_branches_before = _git_lines(local_git_fixture, "branch", "--list").strip()

    _resolver().resolve(ctx)

    head_after = _git_lines(run_root, "rev-parse", "work").strip()
    count_after = _git_lines(run_root, "rev-list", "--count", "work").strip()

    # No new commit beyond the agent's edit (the resolver committed nothing).
    assert head_after == head_before, "repo_diff moved the work HEAD (committed?)"
    assert count_after == count_before, "repo_diff added a commit on work"

    # The diff-only deliverable never pushes the work branch upstream (N4): the
    # origin (fixture) has no ``work`` branch after the resolver runs.
    origin_branches_after = _git_lines(local_git_fixture, "branch", "--list").strip()
    assert origin_branches_after == origin_branches_before
    assert "work" not in origin_branches_after, "the work branch was pushed to origin"


def test_repo_diff_resolver_does_not_shell_git() -> None:
    """The resolver source contains no ``git commit``/``git push`` and never shells
    git (it reads via the Workspace handle) — REPO-04 / D-10 acceptance."""
    # tests/agents/<this file> -> backend/ is parents[2]; the module lives under
    # backend/agents/capabilities/deliverables/repo_diff.py.
    backend_root = Path(__file__).resolve().parents[2]
    src = backend_root / "agents" / "capabilities" / "deliverables" / "repo_diff.py"
    assert src.is_file(), f"repo_diff.py not found at {src}"
    text = src.read_text(encoding="utf-8")
    # No git commit / push (diff-only, N4); no subprocess shelling of git.
    assert "git commit" not in text
    assert "git push" not in text
    assert "subprocess" not in text
    assert "os.system" not in text
    assert "Popen" not in text


def test_repo_diff_registered() -> None:
    discover()
    assert CapabilityRegistry().is_registered("deliverable", "repo_diff")
