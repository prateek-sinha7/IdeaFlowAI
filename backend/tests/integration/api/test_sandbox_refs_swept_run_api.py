"""ISS-996 / QA-KB-064 — GET /sandbox/refs must not re-create a TTL-swept sandbox.

A swept run has no sandbox directory, so GET /sandbox answers ``expired: true``. The refs
feed used to build the workspace to list tags, which mkdir'd the directory and re-pointed
``.latest``, so every later GET /sandbox answered ``expired: false`` with no files.
The same body was observed red before FIX-727 (evidence/qa-kb-064/fix-01, fix-08).
One file only; offline.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.integration.api.test_run_files_ref_family_scope_api import (  # noqa: F401
    _seed_run,
    _seed_user,
    env,
)


@pytest.mark.issue("ISS-996")
def test_refs_on_a_swept_run_keeps_the_workspace_expired(env):  # noqa: F811
    """ISS-996 — the refs feed neither re-creates a swept sandbox nor loses ``expired``."""
    user = _seed_user(env)
    env["state"]["user"] = user
    run_id = _seed_run(env, user_id=user.id)  # no sandbox directory: a TTL-swept run
    sandbox_dir = Path(env["runs_root"]) / user.id / run_id
    latest = Path(env["runs_root"]) / user.id / ".latest"
    assert env["client"].get(f"/api/runs/{run_id}/sandbox").json()["expired"] is True

    r = env["client"].get(f"/api/runs/{run_id}/sandbox/refs")

    assert r.status_code == 200, r.text
    assert r.json()["refs"] == []
    assert (
        not sandbox_dir.exists()
    ), "GET /sandbox/refs re-created the swept sandbox directory"
    assert not latest.is_symlink(), ".latest was re-pointed at the swept run"
    assert env["client"].get(f"/api/runs/{run_id}/sandbox").json()["expired"] is True
