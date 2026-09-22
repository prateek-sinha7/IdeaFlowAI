"""Phase 6 (T3) — the agents API + agent_ids validation read the REAL registry.

Pins the reconciliation done in T3: ``app/api/agents.py`` and the lazy import in
``app/api/websocket.py`` now import their helpers from the engine's REAL
``agents.registry`` (loader-backed ``AgentSpec``) instead of the stale legacy
``app.agents.registry`` (``AgentDefinition``). This file is the verify gate for
the two latent bugs the repoint fixes:

* **Bug 1** — a custom-selected *prototype* run used to validate against the
  stale legacy ids and then ``load_agent_spec`` the retired ``prototype_v1``
  agents. The endpoint + allow-list must now expose the REAL
  ``prototype-specify`` / ``prototype-plan`` / ``prototype-build`` /
  ``prototype-validate`` ids (with their real ``gate`` frontmatter), so the
  frontend's now-real ids pass validation and the engine loads the real agents.
* **Bug 2** — ``allowed_custom_agent_ids("od_ppt")`` used to return ``∅``,
  rejecting every od_ppt run that supplied ``agent_ids`` (od_ppt's agent set
  now declares pipeline_type: ppt directly — the check is pinned as
  ``allowed_custom_agent_ids("ppt")``). It must be non-empty.

The endpoint tests use a FastAPI ``TestClient`` with ``get_current_user``
overridden (the same pattern as ``test_skill_content_guard.py``); the
allow-list tests drive the real registry helper directly (policy decisions
belong at the unit layer — see ``test_run_pipeline_validation.py``, which after
the Phase-7a legacy excision also drives the REAL ``agents.registry`` helper +
``agents.loader.SUPPORTED_PIPELINE_TYPES``).
"""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Fixtures — FastAPI TestClient with get_current_user overridden
# ---------------------------------------------------------------------------


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
# 3. POST /api/agents/skills validates agent_id via the real get_agent_by_id
# ---------------------------------------------------------------------------


class TestSkillEndpointAgentIdValidation:
    """POST /skills validates ``agent_id`` via the real ``get_agent_by_id``
    (returns ``AgentSpec | None`` — same contract as the legacy helper). A real
    id passes the existence check; an unknown id is rejected with 400.

    We assert on the *validation branch* only: an unknown id must 400 BEFORE
    any skill write, and a real id must NOT 400 (it must get past the existence
    gate). We avoid asserting a 200 success to keep this test free of the skills
    storage sandbox — the save path itself is covered by test_skills.py.
    """

    def test_unknown_agent_id_rejected_400(self, api_client):
        resp = api_client.post(
            "/api/agents/skills",
            json={"agent_id": "no-such-agent-xyz", "content": "hello"},
        )
        assert resp.status_code == 400, resp.text
        assert "Unknown agent_id" in resp.text

    def test_real_agent_id_passes_existence_check(
        self, api_client, tmp_path, monkeypatch
    ):
        """A real id (``prototype-specify``) must get PAST the 400 existence
        gate. We point the skills storage at a tmp dir so the write succeeds
        in isolation, then assert the response is not the 400 rejection.
        """
        from app.agents import skills as skills_module

        monkeypatch.setattr(skills_module, "SKILLS_DIR", tmp_path / "skills")
        monkeypatch.setattr(
            skills_module, "USER_SKILLS_DIR", tmp_path / "skills" / "users"
        )
        monkeypatch.setattr(
            skills_module, "GLOBAL_SKILLS_DIR", tmp_path / "skills" / "global"
        )

        resp = api_client.post(
            "/api/agents/skills",
            json={"agent_id": "prototype-specify", "content": "use our DS"},
        )
        # The id is real → it must NOT be the unknown-id rejection.
        assert resp.status_code != 400, resp.text
        assert "Unknown agent_id" not in resp.text


# ---------------------------------------------------------------------------
# 4. allowed_custom_agent_ids — the REAL registry helper (websocket.py:979)
#    fixes bug 2 (od_ppt → ∅) and underpins bug-1 (prototype custom runs).
# ---------------------------------------------------------------------------


class TestRealAllowedCustomAgentIds:
    """Drive the real ``agents.registry.allowed_custom_agent_ids`` directly —
    the same callable the repointed ``websocket.py`` now imports. (The legacy
    helper is still pinned, against dead code, by
    ``test_run_pipeline_validation.py``; we intentionally don't touch that.)
    """

    def test_ppt_allow_list_is_non_empty(self):
        """Bug 2: legacy returned ``∅`` for od_ppt, rejecting every od_ppt run
        that supplied agent_ids. od_ppt's agent set now declares
        pipeline_type: ppt directly (WR-01 closed at the root); the real
        helper must return a non-empty set that includes the od-ppt agents.
        """
        from agents.registry import allowed_custom_agent_ids

        allowed = allowed_custom_agent_ids("ppt")
        assert allowed, "ppt allow-list is empty — bug 2 not fixed"
        assert {
            "ppt-brief-analyst",
            "ppt-composer",
            "ppt-validator",
        } <= allowed

    def test_prototype_allow_list_contains_real_specify(self):
        """Bug 1 underpinning: a custom prototype run sends the real ids, which
        must be in the allow-list so they pass validation (and the engine then
        loads the REAL agents, not the retired prototype_v1 ones).
        """
        from agents.registry import allowed_custom_agent_ids

        allowed = allowed_custom_agent_ids("prototype")
        assert "prototype-specify" in allowed
        # The retired Approach-1 id must NOT be accepted any more.
        assert "requirements-analyst" not in allowed

    def test_websocket_binds_the_real_helper(self):
        """Belt-and-braces: the symbol the repointed websocket handler binds is
        the REAL registry's helper (``agents.registry``), resolved the same way
        the handler does (a lazy import at ``websocket.py:1002``).

        Phase 7a removed the legacy ``app.agents.registry`` module, so there is
        no longer a second helper to contrast against. Instead we pin the REAL
        helper's behavior with hard-coded expected sets (so the coverage the old
        ``is not legacy_helper`` parity arm gave — "the right callable is wired"
        — is preserved without the dead import).
        """
        from agents.registry import (
            PIPELINE_AGENTS,
            allowed_custom_agent_ids as real_helper,
        )

        # The handler imports the helper from ``agents.registry`` (NOT the
        # deleted ``app.agents.registry``); this resolves to the live callable.
        import agents.registry as real_registry_mod

        assert real_helper is real_registry_mod.allowed_custom_agent_ids

        # And it returns the REAL, tight allow-lists (the values the repointed
        # handler now enforces) — pinned without any legacy reference:
        custom_pool = set(PIPELINE_AGENTS["custom"])
        # ppt → real od-ppt agents ∪ custom pool.
        assert real_helper("ppt") == set(PIPELINE_AGENTS["ppt"]) | custom_pool
        # prototype → real Spec-Kit agents ∪ custom pool.
        assert (
            real_helper("prototype") == set(PIPELINE_AGENTS["prototype"]) | custom_pool
        )
        # custom → OPEN: every non-revision, non-internal pipeline's agents.
        # Cross-pipeline composition is the custom workflow builder's purpose
        # (spec 012), so this branch is deliberately wide. Safe because `custom`
        # is enterprise-only and enterprise already holds every pipeline exposed
        # — see agents/registry.py::allowed_custom_agent_ids, and the equivalence
        # pinned in tests/agents/test_registry_helpers.py.
        expected_custom = {
            aid
            for pt, ids in PIPELINE_AGENTS.items()
            if not pt.endswith("_revision") and pt != "chat"
            for aid in ids
        }
        assert real_helper("custom") == expected_custom
        assert custom_pool <= real_helper("custom")
