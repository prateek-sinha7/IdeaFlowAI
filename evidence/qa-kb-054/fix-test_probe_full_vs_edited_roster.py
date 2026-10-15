"""5-fixer probe for QA-KB-054: full vs edited roster, launch and save, on the in-tree code."""
import json

import pytest

import agents.execution_engine.engine as _eng

_REAL_GET = _eng.get_execution_engine

import tests.integration.api.test_rest_run_launch_api as H  # noqa: E402
from tests.integration.api.test_rest_run_launch_api import (  # noqa: E402,F401
    _post_launch, _run_count, _seed_user, env,
)
from tests.integration.api.test_user_workflows_api import (  # noqa: E402,F401
    _valid_body, api, db_session,
)
from agents.execution_engine.engine import compile_for_run  # noqa: E402

_TPL = {"template_id": "web-prototype", "design_system_id": "material"}


def _ids(wf):
    return [s.agent_id for s in compile_for_run(wf).steps]


@pytest.mark.parametrize("wf,extra,delegate", [
    ("backlog", {}, False),
    ("backlog", {}, True),
    ("prototype_v2", {}, True),
    ("prototype_v2", _TPL, True),
])
def test_full_roster_launch(env, monkeypatch, wf, extra, delegate):
    if delegate:
        monkeypatch.setattr(H._RecordingEngine, "_specs_from_plan",
                            lambda self, steps: _REAL_GET()._specs_from_plan(steps), raising=False)
    env["state"]["user"] = _seed_user(env)
    try:
        resp = _post_launch(env, message="build it", pipeline_type=wf, agent_ids=_ids(wf), **extra)
        print("\nFULL", wf, "tpl" if extra else "notpl", "delegate" if delegate else "nodelegate",
              resp.status_code, json.dumps(resp.json())[:300], "runs:", _run_count(env))
    except Exception as exc:  # noqa: BLE001
        print("\nFULL", wf, "EXC", type(exc).__name__, str(exc)[:200])


@pytest.mark.parametrize("wf,extra", [("backlog", {}), ("prototype_v2", _TPL)])
def test_edited_roster_launch(env, monkeypatch, wf, extra):
    monkeypatch.setattr(H._RecordingEngine, "_specs_from_plan",
                        lambda self, steps: _REAL_GET()._specs_from_plan(steps), raising=False)
    env["state"]["user"] = _seed_user(env)
    resp = _post_launch(env, message="build it", pipeline_type=wf, agent_ids=_ids(wf)[:-1], **extra)
    print("\nEDITED", wf, resp.status_code, json.dumps(resp.json())[:400], "runs:", _run_count(env))


@pytest.mark.parametrize("wf", ["prototype_v2", "backlog"])
@pytest.mark.parametrize("which", ["full", "edited"])
def test_save(api, wf, which):
    client, _ = api
    ids = _ids(wf) if which == "full" else _ids(wf)[:-1]
    r = client.post("/api/user-workflows", json=_valid_body(name=f"p-{wf}-{which}", base_pipeline_type=wf,
                                                            agent_ids=ids, model_overrides=None))
    print("\nSAVE", wf, which, r.status_code, r.text[:200])
