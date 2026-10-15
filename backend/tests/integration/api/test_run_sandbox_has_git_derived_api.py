"""ISS-678 / QA-KB-064 — API-built RunSandbox must not claim a repo that is not there.

Over a sandbox directory with NO ``.git``, the refs feed and the restore tag gate
each spawn a doomed ``git tag --list``. After the fix they spawn none.
One file only; offline.
"""

from __future__ import annotations

import pytest

from tests.integration.api.test_run_files_ref_family_scope_api import (  # noqa: F401
    _seed_run,
    _seed_user,
    env,
)


@pytest.fixture
def git_calls(monkeypatch):
    from app.agents.runtime.local import LocalWorkspace

    calls: list[tuple] = []
    orig = LocalWorkspace._git

    def spy(self, *args, **kwargs):
        calls.append(args)
        return orig(self, *args, **kwargs)

    monkeypatch.setattr(LocalWorkspace, "_git", spy)
    return calls


@pytest.mark.issue("ISS-678")
def test_refs_endpoint_spawns_no_git_without_dot_git(env, git_calls):  # noqa: F811
    """ISS-678 — GET /sandbox/refs over a repo-less sandbox runs zero git calls."""
    from app.agents.sandbox import RunSandbox

    user = _seed_user(env)
    env["state"]["user"] = user
    run_id = _seed_run(env, user_id=user.id)
    sb = RunSandbox(user.id, run_id, runs_root=env["runs_root"])
    sb.ensure()
    assert not (sb.root / ".git").exists()
    git_calls.clear()

    r = env["client"].get(f"/api/runs/{run_id}/sandbox/refs")
    assert r.status_code == 200, r.text
    assert r.json()["refs"] == []
    assert git_calls == [], f"doomed git subprocess(es) spawned: {git_calls!r}"


@pytest.mark.issue("ISS-678")
def test_restore_tag_gate_spawns_no_git_without_dot_git(env, git_calls):  # noqa: F811
    """ISS-678 — the restore tag gate over a repo-less sandbox runs zero git calls."""
    from fastapi import HTTPException

    from app.agents.sandbox import RunSandbox
    from app.api.runs import _validate_tag_for_restore

    # Build the sandbox the way the restore endpoint does (runs.py:2511).
    from app.core.config import settings

    sb = RunSandbox(
        "user-1", "run-1", current_run_id="run-1", runs_root=settings.RUNS_ROOT
    )
    sb.ensure()
    assert not (sb.root / ".git").exists()
    git_calls.clear()

    with pytest.raises(HTTPException) as ei:
        _validate_tag_for_restore("v1", sb)
    assert ei.value.status_code == 400
    assert git_calls == [], f"doomed git subprocess(es) spawned: {git_calls!r}"
