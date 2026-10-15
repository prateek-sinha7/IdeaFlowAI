"""Scratch probes for QA-KB-061 siblings. Lives in the scratchpad, edits NO repo file.
Reuses the repo's own harness (env fixture + seed helpers) from test_rest_run_launch_api."""
import uuid

import pytest

from tests.integration.api.test_rest_run_launch_api import (  # noqa: F401  (env is a fixture)
    _latest_run,
    _post_launch,
    _run_count,
    _seed_run_owned_by,
    _seed_user,
    env,
)


@pytest.fixture(autouse=True)
def _pin_runs_root(monkeypatch, tmp_path):
    from app.core.config import settings

    monkeypatch.setattr(settings, "RUNS_ROOT", str(tmp_path / "runs"))


def test_B1_chains_from_workflow_foreign_source_is_404_and_mints_nothing(env):
    owner, attacker = _seed_user(env), _seed_user(env)
    foreign = _seed_run_owned_by(env, owner.id)
    env["state"]["user"] = attacker
    before = _run_count(env)
    resp = _post_launch(env, message="steal", pipeline_type="user_stories", source_workflow_run_id=foreign)
    print("B1 user_stories + foreign source ->", resp.status_code, resp.text)
    assert resp.status_code == 404
    assert _run_count(env) == before


def test_B2_chains_from_workflow_unknown_source_is_404(env):
    user = _seed_user(env)
    env["state"]["user"] = user
    resp = _post_launch(env, message="x", pipeline_type="user_stories", source_workflow_run_id=str(uuid.uuid4()))
    print("B2 user_stories + unknown source ->", resp.status_code, resp.text)
    assert resp.status_code == 404


def test_B3_revision_arm_foreign_source_link_dropped_run_still_launches(env):
    owner, attacker = _seed_user(env), _seed_user(env)
    foreign = _seed_run_owned_by(env, owner.id)
    env["state"]["user"] = attacker
    resp = _post_launch(env, message="steal", pipeline_type="user_stories_revision", source_workflow_run_id=foreign)
    print("B3 user_stories_revision + foreign source ->", resp.status_code)
    assert resp.status_code == 200, resp.text
    child = _latest_run(env)
    assert child.user_id == attacker.id
    assert child.parent_run_id is None


def test_B4_revision_arm_unknown_source_link_dropped_run_still_launches(env):
    user = _seed_user(env)
    env["state"]["user"] = user
    resp = _post_launch(env, message="x", pipeline_type="user_stories_revision", source_workflow_run_id=str(uuid.uuid4()))
    print("B4 user_stories_revision + unknown source ->", resp.status_code)
    assert resp.status_code == 200, resp.text
    assert _latest_run(env).parent_run_id is None


def test_S1_response_for_declaration_gated_revision_has_no_chain_v2_accepted(env):
    user = _seed_user(env)
    parent = _seed_run_owned_by(env, user.id)
    env["state"]["user"] = user
    resp = _post_launch(env, message="revise", pipeline_type="user_stories_revision", source_workflow_run_id=parent)
    print("S1 response body ->", resp.json())
    assert resp.status_code == 200
    # The FE (RunConnectionProvider.tsx:613-617) synthesises chain_context_unavailable /
    # incompatible_backend when payload.source_workflow_run_id is set and this flag is absent.
    assert "chain_v2_accepted" not in resp.json()


def test_S1b_row_source_run_id_stays_null_for_rest_launched_revision(env):
    user = _seed_user(env)
    parent = _seed_run_owned_by(env, user.id)
    env["state"]["user"] = user
    resp = _post_launch(env, message="revise", pipeline_type="user_stories_revision", source_workflow_run_id=parent)
    assert resp.status_code == 200
    child = _latest_run(env)
    print("S1b child parent_run_id=%r source_run_id=%r" % (child.parent_run_id, child.source_run_id))
    assert child.source_run_id is None


def test_S3_rest_revision_launch_bypasses_the_family_active_revision_guard(env):
    from app.models.workflow import WorkflowRun

    user = _seed_user(env)
    parent = _seed_run_owned_by(env, user.id)
    env["state"]["user"] = user
    db = env["ws"]._get_db()
    try:
        db.add(WorkflowRun(id=str(uuid.uuid4()), user_id=user.id, owner_id=user.id, title="active sibling",
                           type="user_stories_revision", status="running", input="x", agent_count=1,
                           session_id=user.id, parent_run_id=parent, source_run_id=parent))
        db.commit()
    finally:
        db.close()
    guarded = env["client"].post(f"/api/runs/{parent}/revisions",
                                 json={"target_artifact_type": "user_stories_output", "instruction": "again"})
    print("S3 POST /{id}/revisions with an active sibling ->", guarded.status_code, guarded.text[:160])
    unguarded = _post_launch(env, message="again", pipeline_type="user_stories_revision", source_workflow_run_id=parent)
    print("S3 POST /api/runs revision with an active sibling ->", unguarded.status_code)
    from app.models.workflow import WorkflowRun as _WR
    _db = env["ws"]._get_db()
    try:
        fam = _db.query(_WR.id, _WR.status, _WR.parent_run_id).filter(_WR.parent_run_id == parent).all()
        print("S3 family members under the parent (status, parent):", [(r.status, r.parent_run_id == parent) for r in fam])
    finally:
        _db.close()
    assert guarded.status_code == 409
    assert unguarded.status_code == 200
