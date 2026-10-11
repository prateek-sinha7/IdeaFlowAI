"""Unit tests for app/agents/tools/pptx_tools.py — OpenDesign-relative asset paths."""

from __future__ import annotations

from app.agents.tools import pptx_tools
from app.services import od_loader


def test_audit_scripts_dir_resolves_under_od_root_when_od_root_overridden(
    tmp_path, monkeypatch
):
    # Arrange
    monkeypatch.setattr(od_loader, "_OD_ROOT", tmp_path)

    # Act
    scripts = pptx_tools._audit_scripts_dir()

    # Assert
    assert scripts == tmp_path / "skills" / "pptx-html-fidelity-audit" / "scripts"


def test_fonts_dir_resolves_under_od_root_when_od_root_overridden(
    tmp_path, monkeypatch
):
    # Arrange
    monkeypatch.setattr(od_loader, "_OD_ROOT", tmp_path)

    # Act
    fonts = pptx_tools._fonts_dir()

    # Assert
    assert fonts == tmp_path / "fonts"


def test_available_eot_returns_font_when_file_exists_under_od_root(
    tmp_path, monkeypatch
):
    # Arrange
    (tmp_path / "fonts").mkdir()
    eot = tmp_path / "fonts" / "albert-sans-Regular.eot"
    eot.write_bytes(b"\x00")
    monkeypatch.setattr(od_loader, "_OD_ROOT", tmp_path)

    # Act
    found = pptx_tools._available_eot("Albert Sans")

    # Assert
    assert found == eot


def test_available_eot_returns_none_when_font_absent_under_od_root(
    tmp_path, monkeypatch
):
    # Arrange
    monkeypatch.setattr(od_loader, "_OD_ROOT", tmp_path)

    # Act
    found = pptx_tools._available_eot("Albert Sans")

    # Assert
    assert found is None
