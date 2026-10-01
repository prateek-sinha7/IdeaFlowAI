"""Unit tests for app/agents/skills.py — shipped pptx reference docs."""

from __future__ import annotations

from app.agents import skills


def test_get_skill_content_includes_pptx_design_skill_when_skill_md_is_uppercase(
    tmp_path, monkeypatch
):
    # Arrange — the shipped file is SKILL.md. A lowercase lookup only resolves on
    # case-insensitive filesystems, so it failed on a Linux CI runner and in the image.
    (tmp_path / "SKILL.md").write_text("DESIGN RULES", encoding="utf-8")
    (tmp_path / "pptxgenjs.md").write_text("API REFERENCE", encoding="utf-8")
    monkeypatch.setattr(skills, "PPTX_SKILLS_DIR", tmp_path)
    monkeypatch.setattr(skills, "GLOBAL_SKILLS_DIR", tmp_path / "no-global")

    # Act
    content = skills.get_skill_content("ppt-code-generator")

    # Assert
    assert content is not None
    assert "DESIGN RULES" in content
    assert "API REFERENCE" in content
