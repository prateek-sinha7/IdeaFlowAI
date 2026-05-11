"""Unit tests for per-user skill resolution in ``WorkflowOrchestrator``.

Regression guard for WORKFLOWS.md §B6 — when skill loading moved from the WS
handler into ``WorkflowOrchestrator._load_skills`` we had to make sure the
orchestrator forwards ``user_id`` to ``get_skill_content`` so that a user's
custom SKILL.md continues to win over the admin global / built-in defaults.

These tests do NOT exercise the on-disk filesystem layer (that's covered in
``test_skills.py``). They verify only the wiring: that ``user_id`` flows from
``WorkflowOrchestrator.__init__`` → ``_load_skills`` → ``get_skill_content``.

Why we test by patching ``get_skill_content`` on the orchestrator's module:
``orchestrator_v2.py`` does ``from app.agents.skills import get_skill_content``
at module-load time. The binding inside the orchestrator's module is the one
``_load_skills`` actually invokes. Patching the symbol on
``app.agents.orchestrator_v2`` is what intercepts the call.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from app.agents.orchestrator_v2 import WorkflowOrchestrator


@pytest.fixture
def skill_spy(monkeypatch):
    """Replace ``get_skill_content`` with a spy that records every call.

    Returns a list of (agent_id, user_id) tuples — one per invocation — so
    each test can assert exactly what ``_load_skills`` forwarded. The mock
    returns ``None`` (no skill) for every call, which short-circuits the
    skill-injection branch in ``execute`` without affecting orchestrator
    construction. (Skills are only loaded when ``execute`` is called, not
    at constructor time, so to exercise ``_load_skills`` we call it directly.)
    """
    calls: list[tuple[str, str | None]] = []

    def _spy(agent_id: str, user_id: str | None = None) -> Any:
        calls.append((agent_id, user_id))
        return None  # Return None so no skill is injected.

    import app.agents.orchestrator_v2 as orchestrator_mod

    monkeypatch.setattr(orchestrator_mod, "get_skill_content", _spy)
    return calls


class TestOrchestratorForwardsUserId:
    """Verify the orchestrator threads ``user_id`` through to ``get_skill_content``.

    The regression we're guarding against: a refactor reverts the
    ``_load_skills`` signature to call ``get_skill_content(agent_id)`` without
    ``user_id``, silently dropping user customisations.
    """

    def test_no_user_id_falls_back_to_global(self, skill_spy):
        """Without ``user_id``, every ``get_skill_content`` call must pass
        ``user_id=None`` so the resolver skips the per-user lookup tier.
        """
        orch = WorkflowOrchestrator("user_stories")
        # Call _load_skills directly — the resolution wiring is what we test,
        # not the surrounding ``execute()`` machinery.
        orch._load_skills()

        assert len(skill_spy) > 0, "Expected at least one get_skill_content call"
        for agent_id, user_id in skill_spy:
            assert user_id is None, (
                f"Expected user_id=None for global fallback, got user_id={user_id!r} "
                f"for agent_id={agent_id!r}"
            )

    def test_explicit_user_id_is_forwarded(self, skill_spy):
        """With ``user_id="abc"``, every ``get_skill_content`` call must pass
        ``user_id="abc"`` so the per-user override tier is consulted.
        """
        orch = WorkflowOrchestrator("user_stories", user_id="abc")
        orch._load_skills()

        assert len(skill_spy) > 0, "Expected at least one get_skill_content call"
        for agent_id, user_id in skill_spy:
            assert user_id == "abc", (
                f"Expected user_id='abc' for agent_id={agent_id!r}, got {user_id!r}"
            )

    def test_user_id_is_set_on_instance(self):
        """``self.user_id`` must round-trip from constructor to attribute.

        ``_load_skills`` reads ``self.user_id`` — if the constructor drops or
        renames the attribute, every skill call will silently use ``None``.
        """
        orch = WorkflowOrchestrator("user_stories", user_id="user-xyz")
        assert orch.user_id == "user-xyz"

        # And the no-arg form leaves it as None.
        orch_anon = WorkflowOrchestrator("user_stories")
        assert orch_anon.user_id is None


class TestBothBaseAndRevisionPipelinesForwardUserId:
    """Both base pipelines and revision pipelines must forward ``user_id``.

    Revision pipelines run against a different registry list
    (``PPT_REVISION_AGENTS`` vs ``PPT_AGENTS``); a refactor that special-cases
    the revision path could silently drop ``user_id``. This test exercises
    both branches in one go.
    """

    def test_base_pipeline_forwards_user_id(self, skill_spy):
        """The base ``user_stories`` pipeline must forward ``user_id``."""
        orch = WorkflowOrchestrator("user_stories", user_id="alice")
        orch._load_skills()

        assert len(skill_spy) > 0
        for agent_id, user_id in skill_spy:
            assert user_id == "alice", (
                f"user_stories pipeline dropped user_id for agent_id={agent_id!r}: "
                f"got {user_id!r}"
            )

    def test_revision_pipeline_forwards_user_id(self, skill_spy):
        """The ``ppt_revision`` pipeline must forward ``user_id``.

        ``ppt_revision`` is a revision pipeline — it routes through the
        REVISION_BASE_MAP at construction time and uses a separate
        ``PPT_REVISION_AGENTS`` list. This test catches any regression where
        the revision-detection branch drops user context.
        """
        orch = WorkflowOrchestrator("ppt_revision", user_id="bob")
        assert orch.is_revision is True, (
            "ppt_revision should be detected as a revision pipeline; "
            "the test setup is wrong if this fails"
        )
        orch._load_skills()

        assert len(skill_spy) > 0
        for agent_id, user_id in skill_spy:
            assert user_id == "bob", (
                f"ppt_revision pipeline dropped user_id for agent_id={agent_id!r}: "
                f"got {user_id!r}"
            )
