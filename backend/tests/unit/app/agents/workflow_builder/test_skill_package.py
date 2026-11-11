"""Unit tests for ``app.agents.workflow_builder.skill_package``.

Covers the fixed skill path, hashing, file listing, the facts read from disk and
the required-files check. Every tree is built under ``tmp_path``; nothing else on
disk is touched.

Requirements: 20.1 (skill hash), 32.9.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.agents.workflow_builder import skill_package
from app.agents.workflow_builder.adherence import MANDATORY_FILES

# git hash-object of the bytes b"hello\n"
HELLO_BLOB = "ce013625030ba8dba906f756967f9e9ca394464a"


def _make_skill(skill_dir: Path, files: dict[str, bytes]) -> Path:
    """Write ``files`` under ``skill_dir`` and return it."""
    for relative, data in files.items():
        target = skill_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    return skill_dir


class TestPaths:
    def test_skill_dir_is_inside_workflow_builder_package_when_module_is_imported(
        self,
    ) -> None:
        package_dir = Path(skill_package.__file__).resolve().parent

        assert skill_package.SKILLS_ROOT == package_dir / "skills"
        assert skill_package.SKILL_DIR == (
            package_dir / "skills" / "velocity-workflow-creator"
        )
        assert (skill_package.SKILL_DIR / "SKILL.md").is_file()


class TestHashing:
    def test_blob_hash_matches_git_when_content_is_lf_text(self) -> None:
        assert skill_package.blob_hash(b"hello\n") == HELLO_BLOB

    def test_blob_hash_ignores_line_endings_when_content_uses_crlf(self) -> None:
        assert skill_package.blob_hash(b"hello\r\n") == HELLO_BLOB

    @pytest.mark.parametrize(
        ("data", "expected"),
        [(b"", 0), (b"a", 1), (b"a\n", 1), (b"a\r\nb", 2), (b"a\n\n", 2)],
    )
    def test_count_lines_counts_final_partial_line_when_no_trailing_newline(
        self, data: bytes, expected: int
    ) -> None:
        assert skill_package.count_lines(data) == expected

    def test_compute_skill_hash_ignores_order_when_pairs_are_shuffled(self) -> None:
        pairs = [("b.md", "2" * 40), ("a.md", "1" * 40)]

        assert skill_package.compute_skill_hash(pairs) == (
            skill_package.compute_skill_hash(reversed(pairs))
        )

    def test_compute_skill_hash_starts_with_prefix_when_called(self) -> None:
        assert skill_package.compute_skill_hash([]).startswith("sha256:")


class TestListSkillFiles:
    def test_list_skill_files_skips_bytecode_when_pycache_exists(
        self, tmp_path: Path
    ) -> None:
        skill = _make_skill(
            tmp_path / "skill",
            {
                "scripts/__pycache__/x.cpython-313.pyc": b"\0",
                "scripts/y.pyc": b"\0",
                "scripts/run.py": b"print()\n",
                "SKILL.md": b"# s\n",
            },
        )

        assert skill_package.list_skill_files(skill) == ["SKILL.md", "scripts/run.py"]

    def test_list_skill_files_returns_empty_when_folder_is_missing(
        self, tmp_path: Path
    ) -> None:
        assert skill_package.list_skill_files(tmp_path / "absent") == []


class TestReadSkillFacts:
    def test_read_skill_facts_returns_hash_and_line_counts_when_files_exist(
        self, tmp_path: Path
    ) -> None:
        skill = _make_skill(
            tmp_path / "skill", {"SKILL.md": b"hello\n", "refs/a.md": b"a\nb"}
        )

        facts = skill_package.read_skill_facts(skill)

        assert dict(facts.line_counts) == {"SKILL.md": 1, "refs/a.md": 2}
        assert facts.skill_hash == skill_package.compute_skill_hash(
            [
                ("SKILL.md", HELLO_BLOB),
                ("refs/a.md", skill_package.blob_hash(b"a\nb")),
            ]
        )

    def test_read_skill_facts_returns_same_facts_when_checkout_uses_crlf(
        self, tmp_path: Path
    ) -> None:
        lf = _make_skill(tmp_path / "lf", {"SKILL.md": b"one\ntwo\n"})
        crlf = _make_skill(tmp_path / "crlf", {"SKILL.md": b"one\r\ntwo\r\n"})

        lf_facts = skill_package.read_skill_facts(lf)
        crlf_facts = skill_package.read_skill_facts(crlf)

        assert crlf_facts.skill_hash == lf_facts.skill_hash
        assert dict(crlf_facts.line_counts) == dict(lf_facts.line_counts)

    def test_read_skill_facts_changes_hash_when_a_file_changes(
        self, tmp_path: Path
    ) -> None:
        skill = _make_skill(tmp_path / "skill", {"SKILL.md": b"# s\n"})
        before = skill_package.read_skill_facts(skill).skill_hash

        (skill / "SKILL.md").write_bytes(b"# changed\n")

        assert skill_package.read_skill_facts(skill).skill_hash != before

    def test_read_skill_facts_ignores_bytecode_when_pycache_is_written(
        self, tmp_path: Path
    ) -> None:
        skill = _make_skill(tmp_path / "skill", {"SKILL.md": b"# s\n"})
        before = skill_package.read_skill_facts(skill)

        _make_skill(skill, {"scripts/__pycache__/x.pyc": b"\0"})
        after = skill_package.read_skill_facts(skill)

        assert after.skill_hash == before.skill_hash
        assert dict(after.line_counts) == {"SKILL.md": 1}

    def test_read_skill_facts_raises_when_folder_holds_no_files(
        self, tmp_path: Path
    ) -> None:
        with pytest.raises(FileNotFoundError, match="no skill files"):
            skill_package.read_skill_facts(tmp_path / "absent")


class TestMissingFiles:
    def test_required_files_lists_mandatory_docs_and_allowed_scripts_when_called(
        self,
    ) -> None:
        required = skill_package.required_files()

        assert required[: len(MANDATORY_FILES)] == MANDATORY_FILES
        assert "scripts/catalog_lookup.py" in required
        assert "scripts/validate_manifest.py" in required

    def test_missing_files_returns_empty_when_every_required_file_exists(
        self, tmp_path: Path
    ) -> None:
        skill = _make_skill(
            tmp_path / "skill", dict.fromkeys(skill_package.required_files(), b"x\n")
        )

        assert skill_package.missing_files(skill) == []

    def test_missing_files_names_each_absent_file_when_some_are_missing(
        self, tmp_path: Path
    ) -> None:
        present = [
            p
            for p in skill_package.required_files()
            if p not in {"SKILL.md", "scripts/selftest.py"}
        ]
        skill = _make_skill(tmp_path / "skill", dict.fromkeys(present, b"x\n"))

        assert skill_package.missing_files(skill) == ["SKILL.md", "scripts/selftest.py"]

    def test_missing_files_lists_every_required_file_when_folder_is_missing(
        self, tmp_path: Path
    ) -> None:
        assert skill_package.missing_files(tmp_path / "absent") == list(
            skill_package.required_files()
        )
