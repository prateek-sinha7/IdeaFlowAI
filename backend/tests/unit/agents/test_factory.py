"""Unit tests for agents/factory.py::_resolve_step_skills against the catalog root."""

from __future__ import annotations

import pytest

import app.agents.skills_catalog as skills_catalog
from agents.factory import _resolve_step_skills
from tests.factories.skill_catalog_factory import write_catalog_skill


@pytest.fixture(autouse=True)
def _cold_catalog_cache():
    """Empty the process-wide catalog cache around each test so no scan leaks across."""
    skills_catalog.clear_cache()
    yield
    skills_catalog.clear_cache()


def test_resolve_step_skills_returns_payload_when_catalog_served_from_baked_root(
    tmp_path, monkeypatch
):
    # Arrange
    write_catalog_skill(tmp_path, "alpha")
    monkeypatch.setattr(skills_catalog, "_GLOBAL_SKILL_DIR", tmp_path)

    # Act
    resolved = _resolve_step_skills(["alpha"])

    # Assert
    assert resolved == [{"id": "alpha", "name": "alpha", "content": "Body of alpha."}]


def test_resolve_step_skills_raises_assertion_when_id_absent_from_catalog(
    tmp_path, monkeypatch
):
    # Arrange — an unresolvable manifest skill stays a loud failure, never a silent drop.
    monkeypatch.setattr(skills_catalog, "_GLOBAL_SKILL_DIR", tmp_path)

    # Act / Assert
    with pytest.raises(AssertionError, match="unresolvable step skill id: ghost"):
        _resolve_step_skills(["ghost"])
