"""Scratch probe for QA-KB-061: which *_revision pipeline types does POST /api/runs accept, and is the owned
source linked as parent_run_id? Edits NO repo file; reuses the repo's launch-test harness."""
import pytest

from tests.integration.api.test_rest_run_launch_api import (  # noqa: F401  (env is a fixture)
    _latest_run,
    _post_launch,
    _seed_run_owned_by,
    _seed_user,
    env,
)

REVISION_TYPES = [
    "app_builder_revision", "backlog_revision", "custom_revision", "ppt_revision",
    "prototype_feature_revision", "prototype_large_revision", "prototype_revision",
    "prototype_v2_feature_revision", "prototype_v2_revision", "user_stories_revision",
]


@pytest.fixture(autouse=True)
def _pin_runs_root(monkeypatch, tmp_path):
    from app.core.config import settings

    monkeypatch.setattr(settings, "RUNS_ROOT", str(tmp_path / "runs"))


@pytest.fixture(autouse=True)
def _stub_engine_can_build_specs(monkeypatch):
    """The repo's _RecordingEngine stub has no _specs_from_plan, which launch_run calls for workflows whose registry
    roster is shorter than the plan (backlog_revision, prototype_v2_*). The method reads no engine state."""
    import agents.execution_engine.engine as engine_mod
    from tests.integration.api.test_rest_run_launch_api import _RecordingEngine

    monkeypatch.setattr(_RecordingEngine, "_specs_from_plan", engine_mod.ExecutionEngine._specs_from_plan, raising=False)


@pytest.mark.parametrize("ptype", REVISION_TYPES)
def test_rest_revision_type_parent_link(env, ptype):
    user = _seed_user(env)
    parent = _seed_run_owned_by(env, user.id)
    env["state"]["user"] = user
    resp = _post_launch(env, message="revise it", pipeline_type=ptype, source_workflow_run_id=parent)
    if resp.status_code != 200:
        print(f"T {ptype:32s} -> {resp.status_code} {resp.text[:215]}")
        return
    child = _latest_run(env)
    print(f"T {ptype:32s} -> 200 parent_linked={child.parent_run_id == parent} source_run_id={child.source_run_id!r}")
