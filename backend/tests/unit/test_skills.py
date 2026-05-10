"""Unit tests for the per-user skill namespacing introduced for WORKFLOWS.md §B6.

These tests cover the three layers that changed when skills moved from a
single global directory to per-user directories:

1. The storage helpers in ``app.agents.skills`` (``save_custom_skill``,
   ``list_user_skills``, ``delete_custom_skill``, ``get_skill_content``).
2. The REST endpoints in ``app.api.agents`` exercised through FastAPI's
   ``TestClient`` with ``get_current_user`` overridden so we can simulate
   different authenticated users without the JWT layer.
3. The exact filesystem layout — every storage test inspects the on-disk
   path so a future refactor that silently reverts to the global path will
   fail loudly here.

The tests redirect the module-level skill directory constants to a
``tmp_path`` fixture so every test runs against a fresh sandbox and the
real ``backend/skills/`` directory is never written to.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

import pytest


# ============================================================
# Fixtures — redirect module-level paths to tmp_path
# ============================================================

@pytest.fixture
def skills_sandbox(tmp_path: Path) -> Iterator[Path]:
    """Point the skills module at a fresh tmp_path for the duration of a test.

    Reassigns module-level constants instead of monkeypatching individual
    callers, so tests can verify the on-disk layout the real code produces.
    Restores the originals on teardown so other test files (and the API
    tests below, which import the same module) are not affected.
    """
    from app.agents import skills as skills_module

    original_skills = skills_module.SKILLS_DIR
    original_users = skills_module.USER_SKILLS_DIR
    original_global = skills_module.GLOBAL_SKILLS_DIR

    skills_module.SKILLS_DIR = tmp_path / "skills"
    skills_module.USER_SKILLS_DIR = tmp_path / "skills" / "users"
    skills_module.GLOBAL_SKILLS_DIR = tmp_path / "skills" / "global"
    skills_module.USER_SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    skills_module.GLOBAL_SKILLS_DIR.mkdir(parents=True, exist_ok=True)

    try:
        yield tmp_path
    finally:
        skills_module.SKILLS_DIR = original_skills
        skills_module.USER_SKILLS_DIR = original_users
        skills_module.GLOBAL_SKILLS_DIR = original_global


# ============================================================
# Storage layer — save / list / delete / resolve
# ============================================================

class TestSaveCustomSkill:
    """Tests for save_custom_skill."""

    def test_writes_to_per_user_path(self, skills_sandbox):
        """File lands at users/{user_id}/{agent_id}/SKILL.md, not the legacy path."""
        from app.agents.skills import save_custom_skill, USER_SKILLS_DIR, SKILLS_DIR

        path = save_custom_skill("domain-analyst", "# Custom", user_id="user-A")

        expected = USER_SKILLS_DIR / "user-A" / "domain-analyst" / "SKILL.md"
        assert Path(path) == expected
        assert expected.exists()
        assert expected.read_text(encoding="utf-8") == "# Custom"
        # Negative assertion: the legacy global path must NOT be written to.
        legacy = SKILLS_DIR / "domain-analyst" / "SKILL.md"
        assert not legacy.exists()

    def test_save_then_overwrite(self, skills_sandbox):
        """Saving twice overwrites the same file rather than creating siblings."""
        from app.agents.skills import save_custom_skill

        save_custom_skill("domain-analyst", "v1", user_id="user-A")
        path = save_custom_skill("domain-analyst", "v2", user_id="user-A")

        assert Path(path).read_text(encoding="utf-8") == "v2"

    def test_requires_user_id(self, skills_sandbox):
        """Calling without a user_id is a programming error and must raise."""
        from app.agents.skills import save_custom_skill

        with pytest.raises(ValueError):
            save_custom_skill("domain-analyst", "x", user_id="")


class TestUserIsolation:
    """User A's writes must never leak into User B's reads."""

    def test_b_cannot_read_a(self, skills_sandbox):
        """User A writes skill X — User B reading skill X gets no content."""
        from app.agents.skills import save_custom_skill, get_skill_content, _user_skill_path

        save_custom_skill("story-writer", "secret-A", user_id="user-A")

        # User B has nothing on disk.
        assert not _user_skill_path("user-B", "story-writer").exists()

        # User B's resolution must NOT pick up A's file. It may still
        # surface a default skill (story-writer has one in DEFAULT_SKILLS),
        # but it must not be A's secret content.
        content_for_b = get_skill_content("story-writer", user_id="user-B")
        assert content_for_b is not None  # default skill exists
        assert "secret-A" not in content_for_b

    def test_a_reads_own(self, skills_sandbox):
        """User A writes skill X — User A reading skill X gets that content."""
        from app.agents.skills import save_custom_skill, get_skill_content

        save_custom_skill("story-writer", "secret-A", user_id="user-A")

        content_for_a = get_skill_content("story-writer", user_id="user-A")
        assert content_for_a == "secret-A"

    def test_list_user_skills_isolated(self, skills_sandbox):
        """list_user_skills only returns the calling user's files."""
        from app.agents.skills import save_custom_skill, list_user_skills

        save_custom_skill("story-writer", "A's skill", user_id="user-A")
        save_custom_skill("domain-analyst", "B's skill", user_id="user-B")

        a_skills = list_user_skills("user-A")
        b_skills = list_user_skills("user-B")

        assert a_skills == {"story-writer": "A's skill"}
        assert b_skills == {"domain-analyst": "B's skill"}

    def test_list_user_skills_empty_for_unknown_user(self, skills_sandbox):
        """A user with no directory yet should get an empty dict, not an error."""
        from app.agents.skills import list_user_skills

        assert list_user_skills("nobody") == {}


class TestResolutionOrder:
    """get_skill_content must walk the layers in the documented order."""

    def test_user_overrides_global(self, skills_sandbox):
        """User file beats a global file with the same agent_id."""
        from app.agents.skills import (
            save_custom_skill,
            get_skill_content,
            GLOBAL_SKILLS_DIR,
        )

        # Plant a global file (admin tier) for the same agent.
        gpath = GLOBAL_SKILLS_DIR / "story-writer" / "SKILL.md"
        gpath.parent.mkdir(parents=True, exist_ok=True)
        gpath.write_text("GLOBAL", encoding="utf-8")

        # Plant a user override.
        save_custom_skill("story-writer", "USER", user_id="user-A")

        assert get_skill_content("story-writer", user_id="user-A") == "USER"

    def test_global_overrides_default(self, skills_sandbox):
        """With no user file, a global file beats DEFAULT_SKILLS."""
        from app.agents.skills import get_skill_content, GLOBAL_SKILLS_DIR

        gpath = GLOBAL_SKILLS_DIR / "story-writer" / "SKILL.md"
        gpath.parent.mkdir(parents=True, exist_ok=True)
        gpath.write_text("GLOBAL", encoding="utf-8")

        assert get_skill_content("story-writer", user_id="user-A") == "GLOBAL"

    def test_falls_back_to_default(self, skills_sandbox):
        """With nothing on disk, DEFAULT_SKILLS is returned."""
        from app.agents.skills import get_skill_content, DEFAULT_SKILLS

        result = get_skill_content("story-writer", user_id="user-A")
        assert result == DEFAULT_SKILLS["story-writer"]

    def test_returns_none_for_unknown_agent(self, skills_sandbox):
        """An agent with no file at any layer and no DEFAULT_SKILLS entry returns None."""
        from app.agents.skills import get_skill_content

        assert get_skill_content("agent-that-does-not-exist", user_id="user-A") is None

    def test_legacy_signature_skips_user_layer(self, skills_sandbox):
        """Calling without user_id must not accidentally walk a user directory.

        This pins the migration contract: legacy callers (those not yet
        threading user.id through) must behave like the pre-namespacing
        global resolver — they see global + defaults but never another
        user's customisation.
        """
        from app.agents.skills import save_custom_skill, get_skill_content, DEFAULT_SKILLS

        save_custom_skill("story-writer", "USER-A-CONTENT", user_id="user-A")

        result = get_skill_content("story-writer")  # no user_id
        # Default still wins because user_id is None — A's content must not leak.
        assert result == DEFAULT_SKILLS["story-writer"]
        assert "USER-A-CONTENT" not in (result or "")


class TestDeleteCustomSkill:
    """delete_custom_skill must only ever touch the calling user's path."""

    def test_deletes_own_file(self, skills_sandbox):
        from app.agents.skills import save_custom_skill, delete_custom_skill, _user_skill_path

        save_custom_skill("story-writer", "x", user_id="user-A")
        path = _user_skill_path("user-A", "story-writer")
        assert path.exists()

        assert delete_custom_skill("story-writer", user_id="user-A") is True
        assert not path.exists()

    def test_returns_false_when_missing(self, skills_sandbox):
        from app.agents.skills import delete_custom_skill

        assert delete_custom_skill("story-writer", user_id="user-A") is False

    def test_cannot_delete_other_users_file(self, skills_sandbox):
        """User B asking to delete agent X must not touch User A's file."""
        from app.agents.skills import save_custom_skill, delete_custom_skill, _user_skill_path

        save_custom_skill("story-writer", "A's content", user_id="user-A")
        a_path = _user_skill_path("user-A", "story-writer")
        assert a_path.exists()

        # User B tries to delete the same agent — they have no file, returns False.
        assert delete_custom_skill("story-writer", user_id="user-B") is False
        # And A's file is untouched.
        assert a_path.exists()
        assert a_path.read_text(encoding="utf-8") == "A's content"


# ============================================================
# API layer — endpoint behaviour with the auth dependency overridden
# ============================================================

@pytest.fixture
def api_client(skills_sandbox):
    """FastAPI TestClient with get_current_user pre-overridden.

    Tests can flip the active user by mutating ``state['user']`` before
    each request. We avoid the real JWT path entirely so these tests do
    not depend on a database, password hashing, or token signing.
    """
    from fastapi.testclient import TestClient

    from app.api.agents import router
    from app.core.dependencies import get_current_user

    # Build a minimal app exposing just the agents router.
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(router)

    state: dict = {"user": _FakeUser(id="user-A")}

    def override():
        return state["user"]

    app.dependency_overrides[get_current_user] = override

    client = TestClient(app)
    # Stash the state on the client so tests can swap users without
    # rebuilding the override. ``fake_state`` rather than ``_state`` to
    # avoid colliding with TestClient's own ``_state`` attribute.
    client.fake_state = state  # type: ignore[attr-defined]
    return client


class _FakeUser:
    """Stand-in for app.models.user.User — only ``id`` is read by the endpoints."""

    def __init__(self, id: str):
        self.id = id


class TestSkillEndpointsValidation:
    """Endpoint-level validation: agent_id, payload size, isolation."""

    def test_unknown_agent_rejected_with_400(self, api_client):
        """POST with an agent_id not in the registry returns 400."""
        resp = api_client.post(
            "/api/agents/skills",
            json={"agent_id": "not-a-real-agent", "content": "hello"},
        )
        assert resp.status_code == 400, resp.text
        assert "not-a-real-agent" in resp.text

    def test_oversize_content_rejected_with_413(self, api_client):
        """Content larger than MAX_SKILL_BYTES returns 413."""
        from app.agents.skills import MAX_SKILL_BYTES

        too_big = "x" * (MAX_SKILL_BYTES + 1)
        resp = api_client.post(
            "/api/agents/skills",
            json={"agent_id": "domain-analyst", "content": too_big},
        )
        assert resp.status_code == 413, resp.text

    def test_at_limit_accepted(self, api_client):
        """Content exactly at MAX_SKILL_BYTES is accepted."""
        from app.agents.skills import MAX_SKILL_BYTES

        at_limit = "x" * MAX_SKILL_BYTES
        resp = api_client.post(
            "/api/agents/skills",
            json={"agent_id": "domain-analyst", "content": at_limit},
        )
        assert resp.status_code == 200, resp.text


class TestSkillEndpointsRoundTrip:
    """End-to-end CRUD via the HTTP layer with two different fake users."""

    def test_post_then_get_roundtrip_for_same_user(self, api_client):
        """POST a skill, then GET it back — content matches."""
        api_client.post(
            "/api/agents/skills",
            json={"agent_id": "domain-analyst", "content": "# A"},
        )
        resp = api_client.get("/api/agents/skills/domain-analyst")
        assert resp.status_code == 200
        assert resp.json() == {"agent_id": "domain-analyst", "content": "# A"}

    def test_get_returns_empty_when_no_user_skill(self, api_client):
        """GET on an agent with no user file returns empty content (no fallback)."""
        resp = api_client.get("/api/agents/skills/domain-analyst")
        assert resp.status_code == 200
        # Endpoint must not leak DEFAULT_SKILLS or the global tier.
        assert resp.json() == {"agent_id": "domain-analyst", "content": ""}

    def test_user_b_does_not_see_user_a(self, api_client):
        """User A POSTs — User B GETs — must see empty (no leakage)."""
        # User A writes
        api_client.fake_state["user"] = _FakeUser(id="user-A")
        api_client.post(
            "/api/agents/skills",
            json={"agent_id": "domain-analyst", "content": "A's secret"},
        )
        # User B reads
        api_client.fake_state["user"] = _FakeUser(id="user-B")
        resp = api_client.get("/api/agents/skills/domain-analyst")
        assert resp.status_code == 200
        body = resp.json()
        assert body["content"] == ""
        assert "A's secret" not in body["content"]

    def test_list_endpoint_user_scoped(self, api_client):
        """GET /skills only lists the calling user's skills.

        Uses two registry-valid agent IDs (``domain-analyst``,
        ``epic-architect``) so the registry validation in POST does not
        reject them — DEFAULT_SKILLS contains some stale entries that are
        no longer in the registry, but that's a separate issue.
        """
        api_client.fake_state["user"] = _FakeUser(id="user-A")
        a1 = api_client.post(
            "/api/agents/skills",
            json={"agent_id": "domain-analyst", "content": "A1"},
        )
        assert a1.status_code == 200
        a2 = api_client.post(
            "/api/agents/skills",
            json={"agent_id": "epic-architect", "content": "A2"},
        )
        assert a2.status_code == 200

        api_client.fake_state["user"] = _FakeUser(id="user-B")
        b1 = api_client.post(
            "/api/agents/skills",
            json={"agent_id": "domain-analyst", "content": "B1"},
        )
        assert b1.status_code == 200

        # List for B
        resp = api_client.get("/api/agents/skills")
        assert resp.status_code == 200
        b_body = resp.json()
        assert b_body["total_count"] == 1
        ids = {s["agent_id"] for s in b_body["skills"]}
        assert ids == {"domain-analyst"}
        # And the preview is B's content, not A's.
        assert b_body["skills"][0]["content_preview"] == "B1"

        # List for A
        api_client.fake_state["user"] = _FakeUser(id="user-A")
        resp = api_client.get("/api/agents/skills")
        a_body = resp.json()
        assert a_body["total_count"] == 2
        ids = {s["agent_id"] for s in a_body["skills"]}
        assert ids == {"domain-analyst", "epic-architect"}

    def test_list_includes_200_char_preview(self, api_client):
        """Preview is the first 200 chars of the content."""
        long_content = "A" * 500
        api_client.post(
            "/api/agents/skills",
            json={"agent_id": "domain-analyst", "content": long_content},
        )
        resp = api_client.get("/api/agents/skills")
        previews = [s["content_preview"] for s in resp.json()["skills"]]
        assert previews == ["A" * 200]


class TestDeleteEndpoint:
    """DELETE /skills/{agent_id} idempotency and isolation."""

    def test_delete_existing_returns_deleted(self, api_client):
        api_client.post(
            "/api/agents/skills",
            json={"agent_id": "domain-analyst", "content": "x"},
        )
        resp = api_client.delete("/api/agents/skills/domain-analyst")
        assert resp.status_code == 200
        assert resp.json() == {"status": "deleted", "agent_id": "domain-analyst"}

    def test_delete_missing_is_idempotent(self, api_client):
        """DELETE on a non-existent skill returns 200 + status:not_found."""
        resp = api_client.delete("/api/agents/skills/domain-analyst")
        assert resp.status_code == 200
        assert resp.json() == {"status": "not_found", "agent_id": "domain-analyst"}

        # Calling DELETE again is still safe — idempotent.
        resp2 = api_client.delete("/api/agents/skills/domain-analyst")
        assert resp2.status_code == 200
        assert resp2.json() == {"status": "not_found", "agent_id": "domain-analyst"}

    def test_delete_does_not_touch_other_user(self, api_client):
        """User B's DELETE must not delete User A's file."""
        from app.agents.skills import _user_skill_path

        api_client.fake_state["user"] = _FakeUser(id="user-A")
        api_client.post(
            "/api/agents/skills",
            json={"agent_id": "domain-analyst", "content": "A"},
        )
        a_path = _user_skill_path("user-A", "domain-analyst")
        assert a_path.exists()

        api_client.fake_state["user"] = _FakeUser(id="user-B")
        resp = api_client.delete("/api/agents/skills/domain-analyst")
        assert resp.status_code == 200
        assert resp.json()["status"] == "not_found"
        # A's file is untouched.
        assert a_path.exists()
        assert a_path.read_text(encoding="utf-8") == "A"
