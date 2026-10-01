"""Unit tests for app/core/config.py — GLOBAL_SKILLS_ROOT normalisation."""

from __future__ import annotations

from app.core.config import Settings

# The validator is called directly. Constructing Settings (even via
# model_validate) reads the process env and backend/.env in this
# pydantic-settings version, and a unit test must not depend on either.


def test_normalize_global_skills_root_strips_whitespace_when_value_padded():
    # Act
    normalized = Settings._normalize_global_skills_root("  /app/builtin-skills/global\n")

    # Assert
    assert normalized == "/app/builtin-skills/global"


def test_normalize_global_skills_root_returns_empty_when_value_none():
    # Act
    normalized = Settings._normalize_global_skills_root(None)

    # Assert
    assert normalized == ""


def test_global_skills_root_defaults_to_empty_when_field_declared():
    # Act
    default = Settings.model_fields["GLOBAL_SKILLS_ROOT"].default

    # Assert
    assert default == ""
