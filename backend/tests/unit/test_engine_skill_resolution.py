"""Unit tests for per-user skill resolution in the Universal ExecutionEngine.

Migrated from test_orchestrator_skill_resolution.py after the orchestrator_v2
deletion (T021). Regression guard for WORKFLOWS.md §B6 — the engine's
_load_disk_skills must forward user_id to get_skill_content so a user's custom
SKILL.md wins over the admin global / built-in defaults.

We verify the wiring only: user_id flows from execute() → _load_disk_skills →
get_skill_content. The on-disk filesystem layer is covered in test_skills.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from agents.execution_engine.engine import ExecutionEngine


@dataclass
class _Spec:
    id: str
    produces: list[str] = field(default_factory=list)
    consumes: list[str] = field(default_factory=list)


@pytest.fixture
def skill_spy(monkeypatch):
    """Replace get_skill_content (as imported inside engine._load_disk_skills)
    with a spy recording (agent_id, user_id) per call. Returns None each time
    so no skill is actually injected."""
    calls: list[tuple[str, str | None]] = []

    def _spy(agent_id: str, user_id: str | None = None) -> Any:
        calls.append((agent_id, user_id))
        return None

    import app.agents.skills as skills_mod
    monkeypatch.setattr(skills_mod, "get_skill_content", _spy)
    return calls


def test_no_user_id_forwards_none(skill_spy):
    engine = ExecutionEngine()
    agents = [_Spec("domain-analyst"), _Spec("epic-architect")]
    result = engine._load_disk_skills(agents, user_id=None)
    assert result == {}
    assert len(skill_spy) == 2
    for _agent_id, user_id in skill_spy:
        assert user_id is None


def test_explicit_user_id_is_forwarded(skill_spy):
    engine = ExecutionEngine()
    agents = [_Spec("domain-analyst"), _Spec("epic-architect")]
    engine._load_disk_skills(agents, user_id="abc")
    assert len(skill_spy) == 2
    for _agent_id, user_id in skill_spy:
        assert user_id == "abc"


def test_skill_content_collected_when_present(monkeypatch):
    """When get_skill_content returns content, it is collected under agent_id."""
    def _fake(agent_id: str, user_id: str | None = None):
        return "SKILL BODY" if agent_id == "domain-analyst" else None

    import app.agents.skills as skills_mod
    monkeypatch.setattr(skills_mod, "get_skill_content", _fake)

    engine = ExecutionEngine()
    agents = [_Spec("domain-analyst"), _Spec("epic-architect")]
    result = engine._load_disk_skills(agents, user_id="u1")
    assert result == {"domain-analyst": "SKILL BODY"}


def test_get_skill_content_failure_is_swallowed(monkeypatch):
    """A failure loading one agent's skill must not break the run."""
    def _boom(agent_id: str, user_id: str | None = None):
        raise RuntimeError("disk error")

    import app.agents.skills as skills_mod
    monkeypatch.setattr(skills_mod, "get_skill_content", _boom)

    engine = ExecutionEngine()
    agents = [_Spec("domain-analyst")]
    result = engine._load_disk_skills(agents, user_id="u1")
    assert result == {}
