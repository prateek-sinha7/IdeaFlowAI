"""Unit tests for ``app.agents.workflow_builder.backend_fs``.

Covers the read-only skills route (every mutation refused, listings limited to
the configured skill folders, reads unchanged) and the composite backend built by
``build_builder_backend`` (sandbox as default, skills under ``/skills/``, nothing
copied into the sandbox). All files live under ``tmp_path``.

Requirements: 20.6, 20.7, 20.8, 27.1, 27.2.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.agents.workflow_builder.backend_fs import (
    SKILL_READ_ONLY_MESSAGE,
    SKILLS_ROUTE,
    ReadOnlySkillsBackend,
    build_builder_backend,
)

SKILL_ID = "velocity-workflow-creator"
HIDDEN_DIR = "internal-notes"
# Any file beside the skill folders; listings must not show it.
STRAY_FILE = "notes.json"


@pytest.fixture
def skills_root(tmp_path: Path) -> Path:
    """A skills root with one visible skill, one hidden folder and a stray file beside them."""
    root = tmp_path / "skills"
    (root / SKILL_ID / "docs").mkdir(parents=True)
    (root / SKILL_ID / "SKILL.md").write_text("# Skill\nneedle in the skill\n", "utf-8")
    (root / SKILL_ID / "docs" / "guide.md").write_text("guide needle\n", "utf-8")
    (root / HIDDEN_DIR).mkdir()
    (root / HIDDEN_DIR / "secret.md").write_text("hidden needle\n", "utf-8")
    (root / STRAY_FILE).write_text('{"needle": true}', "utf-8")
    return root


@pytest.fixture
def sandbox_root(tmp_path: Path) -> Path:
    """An empty session sandbox folder."""
    root = tmp_path / "sandbox"
    root.mkdir()
    return root


@pytest.fixture
def backend(skills_root: Path) -> ReadOnlySkillsBackend:
    """The read-only backend that shows only the velocity skill folder."""
    return ReadOnlySkillsBackend(skills_root, visible=frozenset({SKILL_ID}))


def _paths(entries: list[dict[str, object]] | None) -> set[str]:
    return {str(entry["path"]).strip("/") for entry in entries or []}


def test_init_raises_when_virtual_mode_is_false(skills_root: Path) -> None:
    with pytest.raises(ValueError, match="virtual_mode"):
        ReadOnlySkillsBackend(skills_root, False, visible=frozenset({SKILL_ID}))  # noqa: FBT003


def test_visible_returns_configured_folders_when_created(
    backend: ReadOnlySkillsBackend,
) -> None:
    assert backend.visible == frozenset({SKILL_ID})


def test_ls_lists_only_visible_folders_when_root_listed(
    backend: ReadOnlySkillsBackend,
) -> None:
    result = backend.ls("/")

    assert _paths(result.entries) == {SKILL_ID}  # type: ignore[arg-type]


def test_ls_lists_skill_content_when_visible_folder_listed(
    backend: ReadOnlySkillsBackend,
) -> None:
    result = backend.ls(f"/{SKILL_ID}")

    assert _paths(result.entries) == {  # type: ignore[arg-type]
        f"{SKILL_ID}/SKILL.md",
        f"{SKILL_ID}/docs",
    }


def test_glob_hides_stray_file_and_hidden_folder_when_pattern_matches_all(
    backend: ReadOnlySkillsBackend,
) -> None:
    result = backend.glob("**/*", "/")

    paths = _paths(result.matches)  # type: ignore[arg-type]
    assert f"{SKILL_ID}/SKILL.md" in paths
    assert f"{SKILL_ID}/docs/guide.md" in paths
    assert all(path.startswith(f"{SKILL_ID}/") for path in paths)


def test_grep_returns_only_visible_matches_when_hidden_files_match_too(
    backend: ReadOnlySkillsBackend,
) -> None:
    result = backend.grep("needle", "/")

    paths = {str(match["path"]).strip("/") for match in result.matches or []}
    assert paths == {f"{SKILL_ID}/SKILL.md", f"{SKILL_ID}/docs/guide.md"}


def test_read_returns_content_when_file_is_stray_file_beside_skill(
    backend: ReadOnlySkillsBackend,
) -> None:
    """Reads are not filtered (decision 13.1): only listings are."""
    result = backend.read(f"/{STRAY_FILE}")

    assert result.error is None


def test_write_returns_read_only_error_when_called(
    backend: ReadOnlySkillsBackend, skills_root: Path
) -> None:
    result = backend.write(f"/{SKILL_ID}/new.md", "x")

    assert result.error == SKILL_READ_ONLY_MESSAGE
    assert not (skills_root / SKILL_ID / "new.md").exists()


async def test_awrite_returns_read_only_error_when_called(
    backend: ReadOnlySkillsBackend, skills_root: Path
) -> None:
    result = await backend.awrite(f"/{SKILL_ID}/new.md", "x")

    assert result.error == SKILL_READ_ONLY_MESSAGE
    assert not (skills_root / SKILL_ID / "new.md").exists()


def test_edit_returns_read_only_error_when_called(
    backend: ReadOnlySkillsBackend, skills_root: Path
) -> None:
    result = backend.edit(f"/{SKILL_ID}/SKILL.md", "Skill", "Changed")

    assert result.error == SKILL_READ_ONLY_MESSAGE
    assert "Changed" not in (skills_root / SKILL_ID / "SKILL.md").read_text("utf-8")


async def test_aedit_returns_read_only_error_when_called(
    backend: ReadOnlySkillsBackend, skills_root: Path
) -> None:
    result = await backend.aedit(f"/{SKILL_ID}/SKILL.md", "Skill", "Changed", True)  # noqa: FBT003

    assert result.error == SKILL_READ_ONLY_MESSAGE
    assert "Changed" not in (skills_root / SKILL_ID / "SKILL.md").read_text("utf-8")


def test_upload_files_refuses_every_file_when_called(
    backend: ReadOnlySkillsBackend, skills_root: Path
) -> None:
    responses = backend.upload_files([("/a.md", b"1"), (f"/{SKILL_ID}/b.md", b"2")])

    assert [r.error for r in responses] == [SKILL_READ_ONLY_MESSAGE] * 2
    assert [r.path for r in responses] == ["/a.md", f"/{SKILL_ID}/b.md"]
    assert not (skills_root / "a.md").exists()


async def test_aupload_files_refuses_every_file_when_called(
    backend: ReadOnlySkillsBackend,
) -> None:
    responses = await backend.aupload_files([("/a.md", b"1")])

    assert [r.error for r in responses] == [SKILL_READ_ONLY_MESSAGE]


# --- build_builder_backend ----------------------------------------------------------


def test_build_builder_backend_reads_skill_file_when_path_is_under_skills(
    sandbox_root: Path, skills_root: Path
) -> None:
    composite = build_builder_backend(sandbox_root, skills_root, [SKILL_ID])

    result = composite.read(f"{SKILLS_ROUTE}{SKILL_ID}/SKILL.md")

    assert result.error is None
    assert "needle in the skill" in str(result.file_data["content"])  # type: ignore[index]


def test_build_builder_backend_refuses_write_when_path_is_under_skills(
    sandbox_root: Path, skills_root: Path
) -> None:
    composite = build_builder_backend(sandbox_root, skills_root, [SKILL_ID])

    result = composite.write(f"{SKILLS_ROUTE}{SKILL_ID}/new.md", "x")

    assert result.error == SKILL_READ_ONLY_MESSAGE
    assert not (skills_root / SKILL_ID / "new.md").exists()
    assert not (sandbox_root / "skills").exists()


def test_build_builder_backend_writes_to_sandbox_when_path_is_under_workflows(
    sandbox_root: Path, skills_root: Path
) -> None:
    composite = build_builder_backend(sandbox_root, skills_root, [SKILL_ID])

    result = composite.write("/workflows/a.workflow.json", '{"steps": []}')

    assert result.error is None
    assert (sandbox_root / "workflows" / "a.workflow.json").is_file()


def test_build_builder_backend_refuses_json_write_when_content_is_not_json(
    sandbox_root: Path, skills_root: Path
) -> None:
    composite = build_builder_backend(sandbox_root, skills_root, [SKILL_ID])

    result = composite.write("/workflows/bad.workflow.json", "{not json")

    assert result.error is not None
    assert not (sandbox_root / "workflows" / "bad.workflow.json").exists()


def test_build_builder_backend_copies_no_skill_file_when_built_and_used(
    sandbox_root: Path, skills_root: Path
) -> None:
    composite = build_builder_backend(sandbox_root, skills_root, [SKILL_ID])

    composite.read(f"{SKILLS_ROUTE}{SKILL_ID}/SKILL.md")
    composite.ls(SKILLS_ROUTE)

    assert list(sandbox_root.iterdir()) == []


def test_build_builder_backend_lists_only_visible_skills_when_skills_route_listed(
    sandbox_root: Path, skills_root: Path
) -> None:
    composite = build_builder_backend(sandbox_root, skills_root, [SKILL_ID])

    result = composite.ls(SKILLS_ROUTE)

    names = {str(e["path"]).rstrip("/") for e in result.entries or []}
    assert names == {f"{SKILLS_ROUTE}{SKILL_ID}"}
