"""Scratch probe 3 for QA-KB-054 (analyzer) - NOT a repo test. SAVE-side sibling: POST
/api/user-workflows with a flat agent_ids roster (no manifest) for a custom-agent file workflow."""
import json

import pytest

from tests.integration.api.test_user_workflows_api import _valid_body, api, db_session  # noqa: F401

CASES = [
    ("prototype_v2", ["custom-agent:fi-planner", "custom-agent:fi-readers"]),
    ("backlog", ["custom-agent:us-planner"]),
]


@pytest.mark.parametrize("pipeline,ids", CASES)
def test_probe_save(api, pipeline, ids):
    client, _ = api
    r = client.post(
        "/api/user-workflows",
        json=_valid_body(name=f"probe-{pipeline}", base_pipeline_type=pipeline, agent_ids=ids, model_overrides=None),
    )
    print("\nPROBE-SAVE-FLAT", pipeline, r.status_code, json.dumps(r.json())[:400])
