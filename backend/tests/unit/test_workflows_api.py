"""Plan 04-05 Task 2 — /api/workflows serves manifest-derived definitions (API-01).

After the run-history CRUD moved to ``/api/runs`` (Task 1 / D-02), this router
was reclaimed for the composer: it lists every authored workflow from the
compiled manifests and returns the full compiled step config for a known id,
404 on an unknown id. These tests pin:

* ``test_list_returns_all_authored_workflows`` — one entry per
  ``PIPELINE_AGENTS`` id, with id/name/description/step-summary metadata.
* ``test_get_prototype_matches_manifest`` — the ``prototype`` payload matches
  its compiled manifest (agents in order, gates, deliverable).
* ``test_get_unknown_id_is_404`` — an unknown id is rejected without ever
  touching the filesystem (T-04-13 path-traversal mitigation).

Drives a FastAPI ``TestClient`` with ``get_current_user`` overridden (the same
pattern as ``test_agents_api_real_registry.py``). The router issues NO DB query,
so no ``get_db`` override is needed.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agents.execution_engine.engine import compile_for_run
from agents.registry import PIPELINE_AGENTS, get_pipeline_agents
from app.api.workflows import router
from app.core.dependencies import get_current_user


class _FakeUser:
    def __init__(self, id: str):
        self.id = id


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: _FakeUser(id="user-1")
    return TestClient(app)


# ---------------------------------------------------------------------------
# GET /api/workflows — list every authored workflow with metadata
# ---------------------------------------------------------------------------


class TestList:
    def test_list_returns_all_authored_workflows(self, client):
        resp = client.get("/api/workflows")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        ids = {w["id"] for w in body}
        assert ids == set(PIPELINE_AGENTS.keys()), (
            f"list did not cover every authored workflow: {ids ^ set(PIPELINE_AGENTS)}"
        )
        assert len(body) == len(PIPELINE_AGENTS)

    def test_list_entries_carry_metadata(self, client):
        resp = client.get("/api/workflows")
        assert resp.status_code == 200, resp.text
        by_id = {w["id"]: w for w in resp.json()}
        proto = by_id["prototype"]
        assert proto["name"] == "Prototype"
        assert proto["description"], "empty description"
        assert proto["step_count"] == len(get_pipeline_agents("prototype"))
        assert [s["agent_id"] for s in proto["steps"]] == [
            s.id for s in get_pipeline_agents("prototype")
        ]

    @pytest.mark.parametrize("workflow_id", sorted(PIPELINE_AGENTS.keys()))
    def test_list_step_count_matches_compiled_plan(self, client, workflow_id):
        # WR-01 regression guard: the list step_count must derive from the
        # COMPILED plan, not get_pipeline_agents — so 'ppt' (whose agents declare
        # pipeline_type: od_ppt, making get_pipeline_agents('ppt') empty) reports
        # its real 3 steps rather than step_count=0 / empty steps.
        resp = client.get("/api/workflows")
        assert resp.status_code == 200, resp.text
        by_id = {w["id"]: w for w in resp.json()}
        compiled = compile_for_run(workflow_id)
        entry = by_id[workflow_id]
        assert entry["step_count"] == len(compiled.steps), (
            f"{workflow_id}: list step_count {entry['step_count']} != "
            f"compiled plan {len(compiled.steps)}"
        )
        assert len(entry["steps"]) == len(compiled.steps)

    def test_list_ppt_reports_nonempty_steps(self, client):
        # The specific bug WR-01 fixed: 'ppt' previously reported step_count=0
        # and empty steps. It has 3 well-defined steps.
        resp = client.get("/api/workflows")
        assert resp.status_code == 200, resp.text
        by_id = {w["id"]: w for w in resp.json()}
        ppt = by_id["ppt"]
        assert ppt["step_count"] == len(compile_for_run("ppt").steps) > 0
        assert len(ppt["steps"]) > 0
        # Names resolve via the membership fallback, not bare agent ids.
        assert all(s["name"] for s in ppt["steps"])

    def test_list_does_not_query_workflow_run(self, client):
        # The router imports no DB session; a clean list call must succeed with
        # no get_db override present (proves no WorkflowRun dependency).
        resp = client.get("/api/workflows")
        assert resp.status_code == 200, resp.text


# ---------------------------------------------------------------------------
# GET /api/workflows/{id} — full compiled config + 404
# ---------------------------------------------------------------------------


class TestGetAnd404:
    def test_get_prototype_matches_manifest(self, client):
        resp = client.get("/api/workflows/prototype")
        assert resp.status_code == 200, resp.text
        body = resp.json()

        compiled = compile_for_run("prototype")
        specs = get_pipeline_agents("prototype")

        # Agents in compiled order match the registry-ordered specs.
        assert [s["agent_id"] for s in body["steps"]] == [
            st.agent_id for st in compiled.steps
        ]
        assert [s["agent_id"] for s in body["steps"]] == [sp.id for sp in specs]

        # Per-step gates match the compiled manifest gates verbatim.
        compiled_gates = {st.agent_id: list(st.gates) for st in compiled.steps}
        body_gates = {s["agent_id"]: s["gates"] for s in body["steps"]}
        assert body_gates == compiled_gates

        # Deliverable matches the manifest.
        assert body["deliverable"]["strategy"] == compiled.deliverable.strategy
        assert body["deliverable"]["name"] == compiled.deliverable.name

        # Declared capabilities / clarify surfaced.
        assert body["planner"] == compiled.planner
        assert body["clarify_defaults"] == list(compiled.clarify.defaults)

    def test_get_each_known_id_compiles(self, client):
        # Every authored id returns 200 with a step list of the right length.
        for wid in PIPELINE_AGENTS:
            resp = client.get(f"/api/workflows/{wid}")
            assert resp.status_code == 200, f"{wid}: {resp.text}"
            compiled = compile_for_run(wid)
            assert len(resp.json()["steps"]) == len(compiled.steps)

    def test_get_unknown_id_is_404(self, client):
        resp = client.get("/api/workflows/not_a_real_workflow")
        assert resp.status_code == 404, resp.text

    def test_get_path_traversal_id_is_404(self, client):
        # A traversal-looking id must be rejected by the known-id allow-list,
        # never reaching the filesystem (T-04-13).
        resp = client.get("/api/workflows/..%2f..%2fetc%2fpasswd")
        assert resp.status_code == 404, resp.text
