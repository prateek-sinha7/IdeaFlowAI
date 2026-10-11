"""Agents-API listing endpoints over the REAL registry — the DB-touching half.

Split out of ``tests/unit/api/test_agents_api_real_registry.py``. That module pins the
T3 reconciliation (``app/api/agents.py`` importing its helpers from the engine's real
``agents.registry`` rather than the stale legacy ``app.agents.registry``). Its
allow-list tests drive the registry helper directly and its ``POST /skills`` validation
tests short-circuit at request validation, so both stay in the unit suite.

The two endpoint classes below hit ``GET /api/agents/pipelines/{type}`` and
``GET /api/agents/library``, which resolve ``has_skill`` through a real
``SessionLocal()``. The unit-isolation guard in ``tests/unit/conftest.py`` rejects that
by design — and it surfaced confusingly, because FastAPI wrapped the guard's
``UnitIsolationError`` into a ``RequestValidationError``, so the failure read as a
pydantic ``AgentResponse`` validation error rather than a DB-isolation violation.

``_FakeUser`` + the ``api_client`` fixture are duplicated here rather than imported:
every file under ``tests/integration/api/`` defines its own TestClient (there is no
shared conftest), and the unit half still needs its own copy for the classes that
remain there.
"""

from __future__ import annotations

import pytest


class _FakeUser:
    """Stand-in for ``app.models.user.User`` — only ``id`` is read by the API."""

    def __init__(self, id: str):
        self.id = id


@pytest.fixture
def api_client():
    """FastAPI TestClient wired to the agents router with auth overridden.

    Mirrors ``test_skill_content_guard.py::api_client``. No skills sandbox is
    needed here — these tests only hit the read-only listing endpoints, and
    ``has_skill`` resolving against the real on-disk default/global tiers is
    irrelevant to the assertions (we never assert on its value).
    """
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api.agents import router
    from app.core.dependencies import get_current_user

    app = FastAPI()
    app.include_router(router)

    state: dict = {"user": _FakeUser(id="user-T3")}

    def override():
        return state["user"]

    app.dependency_overrides[get_current_user] = override
    return TestClient(app)


# ---------------------------------------------------------------------------
# 1. GET /api/agents/pipelines/prototype → REAL ids + gate + description
# ---------------------------------------------------------------------------


class TestPrototypePipelineEndpointReturnsRealRegistry:
    """The prototype endpoint must surface the real Spec-Kit agents (specify /
    plan / build / validate), NOT the retired ``prototype_v1`` agents the
    legacy registry used to serve.
    """

    def test_prototype_endpoint_returns_real_ids_in_order(self, api_client):
        resp = api_client.get("/api/agents/pipelines/prototype")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["pipeline_type"] == "prototype"
        ids = [a["id"] for a in body["agents"]]
        assert ids == [
            "prototype-specify",
            "prototype-plan",
            # KAN-86 (ff94f7c1) added the Spec Kit analyze step between plan and
            # build. This list pinned the pre-KAN-86 shape.
            "prototype-analyze",
            "prototype-build",
            "prototype-validate",
        ], f"endpoint did not return the REAL prototype ids: {ids}"
        # The retired Approach-1 ids must NOT appear — that was bug 1.
        legacy_v1 = {
            "requirements-analyst",
            "html-prototype-builder",
            "prototype-polisher",
            "prototype-finalizer",
        }
        assert not (
            set(ids) & legacy_v1
        ), f"retired prototype_v1 ids leaked into the endpoint: {set(ids) & legacy_v1}"

    def test_prototype_endpoint_gate_values(self, api_client):
        """``gate`` is the additive AGENT.md frontmatter projection. The static
        ``gate: Human_Gate`` was removed from prototype-specify/plan (PR #10) —
        human review is now declared per step in the manifest (``gates: [human]``),
        so every prototype agent projects ``None`` here.
        """
        resp = api_client.get("/api/agents/pipelines/prototype")
        assert resp.status_code == 200, resp.text
        gate_by_id = {a["id"]: a["gate"] for a in resp.json()["agents"]}
        assert gate_by_id["prototype-specify"] is None
        assert gate_by_id["prototype-plan"] is None
        assert gate_by_id["prototype-build"] is None
        assert gate_by_id["prototype-validate"] is None

    def test_prototype_endpoint_descriptions_non_empty(self, api_client):
        """T1's loader fallback guarantees a non-empty ``description`` (falls
        back to ``role`` when the frontmatter omits it — which all four
        prototype AGENT.md files do).
        """
        resp = api_client.get("/api/agents/pipelines/prototype")
        assert resp.status_code == 200, resp.text
        for a in resp.json()["agents"]:
            assert a["description"], f"empty description for {a['id']!r}"

    def test_pipeline_response_schema_fields_present(self, api_client):
        """Every field declared on ``AgentResponse`` is populated for a real
        ``AgentSpec`` — guards against a field the routes read that does not
        exist on the loader spec.
        """
        resp = api_client.get("/api/agents/pipelines/prototype")
        assert resp.status_code == 200, resp.text
        expected_keys = {
            "id",
            "name",
            "role",
            "description",
            "pipeline_type",
            "order",
            "icon",
            "estimated_duration",
            "has_skill",
            "gate",
            # The route serialises the spec's prompt body too; this set pinned
            # the pre-`prompt_body` shape.
            "prompt_body",
        }
        for a in resp.json()["agents"]:
            assert set(a.keys()) == expected_keys, (
                f"AgentResponse keys mismatch for {a.get('id')!r}: "
                f"{set(a.keys()) ^ expected_keys}"
            )


# ---------------------------------------------------------------------------
# 2. GET /api/agents/library → 200 + real flat list incl. gate
# ---------------------------------------------------------------------------


class TestAgentLibraryEndpoint:
    """The /library route now spans every pipeline in the REAL
    ``PIPELINE_AGENTS`` (base + revision + custom). It must still return 200,
    expose the additive ``gate`` field, and include the real prototype ids.
    """

    @pytest.mark.issue("ISS-636")
    def test_library_returns_200_with_gate_and_real_prototype_ids(self, api_client):
        resp = api_client.get("/api/agents/library")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total_count"] == len(body["agents"]) > 0
        ids = {a["id"] for a in body["agents"]}
        # Real prototype ids are present...
        assert {"prototype-specify", "prototype-plan"} <= ids
        # ...and the retired v1 ids are gone.
        assert "requirements-analyst" not in ids
        # gate is exposed on every entry (value may be None).
        for a in body["agents"]:
            assert "gate" in a
        # The frontmatter gate is still projected: clarify-agent is the one
        # agent that keeps a static ``gate: Human_Gate``.
        gate_by_id = {a["id"]: a["gate"] for a in body["agents"]}
        assert gate_by_id.get("clarify-agent") == "Human_Gate"
        assert gate_by_id["prototype-specify"] is None
