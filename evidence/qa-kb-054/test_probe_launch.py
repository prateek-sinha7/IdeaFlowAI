"""QA-KB-054 / ISS-687 evidence. Drives the REAL POST /api/runs router in-process: in-memory sqlite, recording
stub engine, no Bedrock, no server, no real run. NOT a repo test (lives under evidence/, outside testpaths).
Run from backend/:  .venv/bin/python -m pytest ../evidence/qa-kb-054/test_probe_launch.py -s -q -p no:cacheprovider --rootdir=. -o addopts=\"\"
"""
import json

import pytest

import agents.execution_engine.engine as _eng

_REAL_GET = _eng.get_execution_engine  # captured BEFORE the env fixture monkeypatches it

import tests.integration.api.test_rest_run_launch_api as H  # noqa: E402
from tests.integration.api.test_rest_run_launch_api import (  # noqa: E402,F401
    _post_launch,
    _run_count,
    _seed_user,
    env,
)

# prototype_v2 declares context_providers [opendesign]; without a template the launch dies earlier on template_not_found.
CASES = [
    ("prototype_v2", ["custom-agent:fi-planner", "custom-agent:fi-readers"], {"template_id": "web-prototype", "design_system_id": "material"}),
    ("backlog", ["custom-agent:us-planner"], {}),
]


@pytest.mark.parametrize("pipeline,ids,extra", CASES)
def test_with_own_plan_ids_is_rejected(env, pipeline, ids, extra):
    env["state"]["user"] = _seed_user(env)
    resp = _post_launch(env, message="build it", pipeline_type=pipeline, agent_ids=ids, **extra)
    print("\nPROBE-WITH-IDS", pipeline, resp.status_code, json.dumps(resp.json())[:700], "runs_minted:", _run_count(env))


@pytest.mark.parametrize("pipeline,ids,extra", CASES)
def test_control_without_agent_ids_launches(env, pipeline, ids, extra):
    # The integration stub engine has no _specs_from_plan (the `else` roster branch needs it, run_commands.py:3622),
    # so delegate to the real engine. Registered pipelines never reach that call, which is why no existing test saw it.
    H._RecordingEngine._specs_from_plan = lambda self, steps: _REAL_GET()._specs_from_plan(steps)
    env["state"]["user"] = _seed_user(env)
    resp = _post_launch(env, message="build it", pipeline_type=pipeline, **extra)
    print("\nPROBE-CONTROL-NO-IDS", pipeline, resp.status_code, json.dumps(resp.json())[:300], "runs_minted:", _run_count(env))
