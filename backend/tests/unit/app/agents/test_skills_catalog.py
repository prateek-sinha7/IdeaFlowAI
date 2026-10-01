"""Unit tests for app/agents/skills_catalog.py — catalog root resolution."""

from __future__ import annotations

import logging

import pytest

import app.agents.skills_catalog as skills_catalog
from app.core.config import settings
from tests.factories.skill_catalog_factory import write_catalog_skill


@pytest.fixture(autouse=True)
def _cold_catalog_cache():
    """Empty the process-wide catalog cache around each test so no scan leaks across."""
    skills_catalog.clear_cache()
    yield
    skills_catalog.clear_cache()


def test_resolve_global_skill_dir_returns_checkout_default_when_setting_empty(monkeypatch):
    # Arrange
    monkeypatch.setattr(settings, "GLOBAL_SKILLS_ROOT", "")

    # Act
    resolved = skills_catalog._resolve_global_skill_dir()

    # Assert
    assert resolved == skills_catalog._BACKEND_DIR / "skills" / "global"


def test_resolve_global_skill_dir_returns_configured_root_when_directory_exists(
    tmp_path, monkeypatch
):
    # Arrange
    baked = tmp_path / "builtin-skills" / "global"
    baked.mkdir(parents=True)
    monkeypatch.setattr(settings, "GLOBAL_SKILLS_ROOT", str(baked))

    # Act
    resolved = skills_catalog._resolve_global_skill_dir()

    # Assert
    assert resolved == baked


def test_resolve_global_skill_dir_resolves_against_backend_dir_when_root_is_relative(
    tmp_path, monkeypatch
):
    # Arrange
    (tmp_path / "baked" / "global").mkdir(parents=True)
    monkeypatch.setattr(skills_catalog, "_BACKEND_DIR", tmp_path)
    monkeypatch.setattr(settings, "GLOBAL_SKILLS_ROOT", "baked/global")

    # Act
    resolved = skills_catalog._resolve_global_skill_dir()

    # Assert
    assert resolved == tmp_path / "baked" / "global"


def test_resolve_global_skill_dir_falls_back_and_warns_when_configured_root_missing(
    tmp_path, monkeypatch, caplog
):
    # Arrange
    missing = tmp_path / "not-there"
    monkeypatch.setattr(settings, "GLOBAL_SKILLS_ROOT", str(missing))

    # Act
    with caplog.at_level(logging.WARNING, logger=skills_catalog.__name__):
        resolved = skills_catalog._resolve_global_skill_dir()

    # Assert
    assert resolved == skills_catalog._CHECKOUT_GLOBAL_SKILL_DIR
    assert any(str(missing) in r.getMessage() for r in caplog.records)


def test_resolve_global_skill_dir_falls_back_when_configured_root_is_a_file(
    tmp_path, monkeypatch
):
    # Arrange: a path that exists but is not a directory must not be scanned.
    not_a_dir = tmp_path / "global"
    not_a_dir.write_text("", encoding="utf-8")
    monkeypatch.setattr(settings, "GLOBAL_SKILLS_ROOT", str(not_a_dir))

    # Act
    resolved = skills_catalog._resolve_global_skill_dir()

    # Assert
    assert resolved == skills_catalog._CHECKOUT_GLOBAL_SKILL_DIR


def test_list_global_skills_serves_configured_root_when_checkout_default_absent(
    tmp_path, monkeypatch
):
    # Arrange — container shape: no checkout catalog, a baked one at GLOBAL_SKILLS_ROOT.
    baked = tmp_path / "builtin-skills" / "global"
    write_catalog_skill(baked, "alpha", siblings={"reference.md": "sibling"})
    write_catalog_skill(baked, "beta")
    monkeypatch.setattr(skills_catalog, "_CHECKOUT_GLOBAL_SKILL_DIR", tmp_path / "absent")
    monkeypatch.setattr(settings, "GLOBAL_SKILLS_ROOT", str(baked))
    monkeypatch.setattr(
        skills_catalog, "_GLOBAL_SKILL_DIR", skills_catalog._resolve_global_skill_dir()
    )

    # Act
    ids = [entry.id for entry in skills_catalog.list_global_skills()]

    # Assert
    assert ids == ["alpha", "beta"]
    assert (skills_catalog.skill_source_dir("alpha") / "reference.md").is_file()
