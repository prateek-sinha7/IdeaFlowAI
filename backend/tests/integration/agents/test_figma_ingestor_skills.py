"""tests/integration/agents/test_figma_ingestor_skills.py

Disk-read-only tests (no DB, no LLM) verifying that:
- import-design and import-template skills are placed in skills/velocity/
- new-ingestion-skills/ is gone
- design-ingestor global skill is registered in backend/skills/global/
- design-ingestor scripts are present and syntactically valid
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[3]
_REPO = _BACKEND.parent
_VELOCITY = _REPO / "skills" / "velocity"
_GLOBAL = _BACKEND / "skills" / "global"


# ── Phase 1: skills moved to skills/velocity/ ────────────────────────────────


@pytest.mark.integration
def test_import_design_moved_to_velocity() -> None:
    """import-design skill must be at skills/velocity/import-design/SKILL.md."""
    assert (_VELOCITY / "import-design" / "SKILL.md").exists(), (
        "import-design not found at skills/velocity/import-design/ — "
        "run: git mv new-ingestion-skills/import-design skills/velocity/import-design"
    )


@pytest.mark.integration
def test_import_template_moved_to_velocity() -> None:
    """import-template skill must be at skills/velocity/import-template/SKILL.md."""
    assert (_VELOCITY / "import-template" / "SKILL.md").exists(), (
        "import-template not found at skills/velocity/import-template/ — "
        "run: git mv new-ingestion-skills/import-template skills/velocity/import-template"
    )


@pytest.mark.integration
def test_new_ingestion_skills_staging_dir_gone() -> None:
    """new-ingestion-skills/ must not exist in the repo root after Phase 1."""
    staging_dir = _REPO / "new-ingestion-skills"
    assert (
        not staging_dir.exists()
    ), "new-ingestion-skills/ still exists — delete it after git mv"


@pytest.mark.integration
def test_import_design_scripts_present() -> None:
    """import-design must ship its 7 scripts."""
    required = {
        "read_source.py",
        "ds_schema.py",
        "make_ds.py",
        "extract_site.cjs",
        "validate_design_system.py",
        "preview_ds.cjs",
        "shot.cjs",
    }
    scripts_dir = _VELOCITY / "import-design" / "scripts"
    assert scripts_dir.is_dir(), f"scripts/ missing from {scripts_dir.parent}"
    present = {f.name for f in scripts_dir.iterdir() if f.is_file()}
    assert required <= present, f"Missing scripts: {required - present}"


@pytest.mark.integration
def test_import_template_scripts_present() -> None:
    """import-template must ship its 7 scripts."""
    required = {
        "inspect_export.py",
        "snapshot.cjs",
        "trim.cjs",
        "validate_template.py",
        "preview_check.cjs",
        "compare.cjs",
        "css_tools.cjs",
    }
    scripts_dir = _VELOCITY / "import-template" / "scripts"
    assert scripts_dir.is_dir(), f"scripts/ missing from {scripts_dir.parent}"
    present = {f.name for f in scripts_dir.iterdir() if f.is_file()}
    assert required <= present, f"Missing scripts: {required - present}"


# ── Phase 2: design-ingestor global skill registered ──────────────────────────


@pytest.mark.integration
def test_figma_ingestor_skill_dir_exists() -> None:
    """backend/skills/global/design-ingestor/ must exist."""
    assert (
        _GLOBAL / "design-ingestor"
    ).is_dir(), "design-ingestor global skill folder not found at backend/skills/global/design-ingestor/"


@pytest.mark.integration
def test_figma_ingestor_skill_md_exists() -> None:
    """backend/skills/global/design-ingestor/SKILL.md must exist with correct name field."""
    skill_md = _GLOBAL / "design-ingestor" / "SKILL.md"
    assert skill_md.exists(), f"SKILL.md missing at {skill_md}"
    content = skill_md.read_text(encoding="utf-8")
    assert (
        "name: design-ingestor" in content
    ), "SKILL.md frontmatter must contain 'name: design-ingestor'"


@pytest.mark.integration
def test_figma_ingestor_scripts_dir_exists() -> None:
    """backend/skills/global/design-ingestor/scripts/ must contain 4 scripts."""
    scripts_dir = _GLOBAL / "design-ingestor" / "scripts"
    assert scripts_dir.is_dir()
    required = {"figma_extract.py", "figma_to_html.py", "make_ds.py", "ds_schema.py"}
    present = {f.name for f in scripts_dir.iterdir() if f.is_file()}
    assert required <= present, f"Missing scripts: {required - present}"


@pytest.mark.integration
def test_figma_ingestor_schema_bundled() -> None:
    """tokens.schema.ts must be bundled inside the skill for sandbox-offline use."""
    schema_path = (
        _GLOBAL / "design-ingestor" / "scripts" / "schema" / "tokens.schema.ts"
    )
    assert schema_path.exists(), f"tokens.schema.ts not bundled at {schema_path}"
    content = schema_path.read_text(encoding="utf-8")
    assert (
        "TOKEN_SCHEMA" in content or "--bg" in content
    ), "tokens.schema.ts appears empty or is the wrong file"


@pytest.mark.integration
def test_figma_ingestor_scripts_are_valid_python() -> None:
    """All .py scripts in design-ingestor must parse as valid Python."""
    scripts_dir = _GLOBAL / "design-ingestor" / "scripts"
    for py_file in scripts_dir.glob("*.py"):
        try:
            ast.parse(py_file.read_text(encoding="utf-8"))
        except SyntaxError as exc:
            pytest.fail(f"Syntax error in {py_file.name}: {exc}")


@pytest.mark.integration
def test_figma_ingestor_registered_in_catalog(monkeypatch) -> None:
    """skills_catalog.list_global_skills() must include 'design-ingestor'."""
    import app.agents.skills_catalog as skills_catalog

    monkeypatch.setattr(skills_catalog, "_GLOBAL_SKILL_DIR", _GLOBAL)
    skills_catalog.clear_cache()
    try:
        ids = {entry.id for entry in skills_catalog.list_global_skills()}
        assert (
            "design-ingestor" in ids
        ), f"design-ingestor not in catalog. Found: {sorted(ids)}"
    finally:
        skills_catalog.clear_cache()
