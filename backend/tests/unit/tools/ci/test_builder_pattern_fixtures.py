"""Unit tests for ``tools.ci.builder_pattern_fixtures``.

The skill scripts are replaced by a fake runner, so no test starts a process.
Every path is under ``tmp_path``.

Requirements: 10.9, 49.8.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

import pytest

from tools.ci import builder_pattern_fixtures as fixtures
from tools.ci.builder_pattern_fixtures import Pattern
from tools.ci.builder_skill_checks import EXIT_FAILED, EXIT_OK, Layout, ScriptResult

ALLOWED_SECTIONS = [*range(1, 19), 21]


@pytest.fixture
def layout(tmp_path: Path) -> Layout:
    """A layout rooted in ``tmp_path`` with a ``patterns.md`` that matches every pattern."""
    backend = tmp_path / "backend"
    layout = Layout(repo_root=tmp_path, backend_dir=backend)
    docs = layout.skill_dir / "docs"
    docs.mkdir(parents=True)
    (docs / "patterns.md").write_text(
        _patterns_md(fixtures.all_patterns()), encoding="utf-8"
    )
    return layout


def _patterns_md(patterns: Sequence[Pattern]) -> str:
    return "# Workflow patterns\n\n" + "".join(
        f"## {p.number}. {p.title}\n\nBody.\n\n" for p in patterns
    )


class FakeSkill:
    """Stands in for ``validate_manifest.py`` and ``export_manifest.py``."""

    def __init__(self, failing_validation: frozenset[str] = frozenset()) -> None:
        self.failing_validation = failing_validation
        self.calls: list[str] = []

    def __call__(self, argv: Sequence[str], cwd: Path) -> ScriptResult:
        script = Path(argv[1]).name
        manifest_path = Path(argv[2])
        self.calls.append(f"{script}:{manifest_path.name}")
        if script == "validate_manifest.py":
            if manifest_path.name in self.failing_validation:
                return ScriptResult(1, "ERROR [route] broken")
            return ScriptResult(0, "VALID")
        out = Path(argv[argv.index("--save-payload") + 1])
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        payload = {"name": manifest["name"], "manifest": manifest}
        # Like export_manifest.py on Windows: text mode writes CRLF.
        out.write_bytes(fixtures.render_json(payload).replace(b"\n", b"\r\n"))
        return ScriptResult(0, f"wrote {out}")


class TestPatterns:
    def test_all_patterns_covers_sections_1_to_18_and_21_when_called(self) -> None:
        numbers = [p.number for p in fixtures.all_patterns()]

        assert numbers == ALLOWED_SECTIONS

    def test_all_patterns_gives_unique_file_names_and_manifest_ids_when_called(
        self,
    ) -> None:
        patterns = fixtures.all_patterns()

        assert len({p.stem for p in patterns}) == len(patterns)
        assert len({p.manifest["id"] for p in patterns}) == len(patterns)

    def test_all_patterns_gives_custom_agent_steps_with_instance_ids_when_called(
        self,
    ) -> None:
        for pattern in fixtures.all_patterns():
            steps = pattern.manifest["steps"]
            assert steps, pattern.stem
            for step in steps:
                assert step["agent"] == "custom-agent", pattern.stem
                assert step["instance_id"], pattern.stem

    def test_all_patterns_names_files_after_section_number_when_called(self) -> None:
        pattern = fixtures.all_patterns()[0]

        assert pattern.manifest_filename == "01-linear-chain.manifest.json"
        assert pattern.payload_filename == "01-linear-chain.payload.json"


class TestHeadingProblems:
    def test_heading_problems_is_empty_when_every_section_matches(self) -> None:
        patterns = fixtures.all_patterns()

        assert fixtures.heading_problems(patterns, _patterns_md(patterns)) == []

    def test_heading_problems_names_section_when_it_is_missing(self) -> None:
        patterns = fixtures.all_patterns()
        text = _patterns_md([p for p in patterns if p.number != 7])

        assert fixtures.heading_problems(patterns, text) == [
            "patterns.md has no section 7"
        ]

    def test_heading_problems_names_both_titles_when_a_section_is_renamed(self) -> None:
        patterns = fixtures.all_patterns()
        text = _patterns_md(patterns).replace("Dependency waves", "Waves of work")

        problems = fixtures.heading_problems(patterns, text)

        assert len(problems) == 1
        assert "section 6" in problems[0]
        assert "Waves of work" in problems[0]
        assert "Dependency waves" in problems[0]

    def test_heading_problems_ignores_sections_the_fixtures_exclude_when_present(
        self,
    ) -> None:
        patterns = fixtures.all_patterns()
        text = (
            _patterns_md(patterns) + "## 19. Code that is compiled\n\n## 20. Revision\n"
        )

        assert fixtures.heading_problems(patterns, text) == []


class TestRenderJson:
    def test_render_json_uses_lf_indent_and_keeps_unicode_when_called(self) -> None:
        data = fixtures.render_json({"a": "é", "b": [1]})

        assert data == '{\n  "a": "é",\n  "b": [\n    1\n  ]\n}\n'.encode()

    def test_build_index_lists_every_pattern_in_order_when_called(self) -> None:
        patterns = fixtures.all_patterns()

        entries = fixtures.build_index(patterns)["fixtures"]

        assert [e["pattern"] for e in entries] == ALLOWED_SECTIONS
        assert entries[0]["manifest"] == "01-linear-chain.manifest.json"
        assert entries[0]["trust"] == "user"


class TestCompareFiles:
    def test_compare_files_is_empty_when_both_sides_are_equal(self) -> None:
        assert fixtures.compare_files({"a": b"1"}, {"a": b"1"}) == []

    def test_compare_files_reports_missing_extra_and_differing_files(self) -> None:
        problems = fixtures.compare_files(
            {"a": b"1", "b": b"2", "c": b"3"}, {"a": b"1", "b": b"x", "d": b"4"}
        )

        assert problems == ["missing: c", "not a fixture: d", "differs: b"]


class TestBuildExpected:
    def test_build_expected_returns_manifest_payload_and_index_when_scripts_succeed(
        self, layout: Layout, tmp_path: Path
    ) -> None:
        patterns = fixtures.all_patterns()[:2]
        work = tmp_path / "work"
        work.mkdir()

        files, problems = fixtures.build_expected(layout, patterns, work, FakeSkill())

        assert problems == []
        assert set(files) == {
            patterns[0].manifest_filename,
            patterns[0].payload_filename,
            patterns[1].manifest_filename,
            patterns[1].payload_filename,
            fixtures.INDEX_FILENAME,
        }

    def test_build_expected_stores_payload_with_lf_when_script_wrote_crlf(
        self, layout: Layout, tmp_path: Path
    ) -> None:
        patterns = fixtures.all_patterns()[:1]
        work = tmp_path / "work"
        work.mkdir()

        files, _ = fixtures.build_expected(layout, patterns, work, FakeSkill())

        assert b"\r" not in files[patterns[0].payload_filename]
        assert files[patterns[0].manifest_filename] == fixtures.render_json(
            patterns[0].manifest
        )

    def test_build_expected_skips_export_and_reports_when_validation_fails(
        self, layout: Layout, tmp_path: Path
    ) -> None:
        patterns = fixtures.all_patterns()[:2]
        work = tmp_path / "work"
        work.mkdir()
        skill = FakeSkill(frozenset({patterns[0].manifest_filename}))

        files, problems = fixtures.build_expected(layout, patterns, work, skill)

        assert patterns[0].payload_filename not in files
        assert patterns[1].payload_filename in files
        assert problems[0].startswith(
            "pattern 1: validate_manifest.py --trust user exited 1"
        )
        assert "ERROR [route] broken" in problems[1]
        assert f"export_manifest.py:{patterns[0].manifest_filename}" not in skill.calls

    def test_validation_argv_runs_real_compiler_at_pattern_trust_when_called(
        self, layout: Layout, tmp_path: Path
    ) -> None:
        argv = fixtures.validation_argv(layout, tmp_path / "m.json", "db")

        assert argv[argv.index("--trust") + 1] == "db"
        assert argv[argv.index("--compiler") + 1] == "."


class TestRunWrite:
    def test_run_write_writes_every_file_when_scripts_succeed(
        self, layout: Layout
    ) -> None:
        code = fixtures.run_write(layout, FakeSkill())

        names = {p.name for p in fixtures.fixtures_dir(layout).iterdir()}
        assert code == EXIT_OK
        assert len(names) == 2 * len(ALLOWED_SECTIONS) + 1
        assert fixtures.INDEX_FILENAME in names

    def test_run_write_removes_stale_files_when_folder_holds_other_files(
        self, layout: Layout
    ) -> None:
        directory = fixtures.fixtures_dir(layout)
        directory.mkdir(parents=True)
        (directory / "99-old.manifest.json").write_text("{}", encoding="utf-8")

        fixtures.run_write(layout, FakeSkill())

        assert not (directory / "99-old.manifest.json").exists()

    def test_run_write_writes_nothing_when_a_draft_fails_validation(
        self, layout: Layout, capsys: pytest.CaptureFixture[str]
    ) -> None:
        skill = FakeSkill(frozenset({"05-fanout-per-item.manifest.json"}))

        code = fixtures.run_write(layout, skill)

        assert code == EXIT_FAILED
        assert not fixtures.fixtures_dir(layout).exists()
        assert "nothing written" in capsys.readouterr().err

    def test_run_write_writes_nothing_when_a_heading_no_longer_matches(
        self, layout: Layout
    ) -> None:
        path = layout.skill_dir / "docs" / "patterns.md"
        path.write_text(
            path.read_text(encoding="utf-8").replace("Dependency waves", "X"),
            encoding="utf-8",
        )

        code = fixtures.run_write(layout, FakeSkill())

        assert code == EXIT_FAILED
        assert not fixtures.fixtures_dir(layout).exists()


class TestRunCheck:
    def test_run_check_passes_when_files_match_a_rebuild(self, layout: Layout) -> None:
        fixtures.run_write(layout, FakeSkill())

        assert fixtures.run_check(layout, FakeSkill()) == EXIT_OK

    def test_run_check_names_differing_file_when_a_payload_was_edited(
        self, layout: Layout, capsys: pytest.CaptureFixture[str]
    ) -> None:
        fixtures.run_write(layout, FakeSkill())
        edited = fixtures.fixtures_dir(layout) / "10-human-review.payload.json"
        edited.write_text("{}", encoding="utf-8")

        code = fixtures.run_check(layout, FakeSkill())

        err = capsys.readouterr().err
        assert code == EXIT_FAILED
        assert "differs: 10-human-review.payload.json" in err
        assert "--write" in err

    def test_run_check_names_missing_and_extra_files_when_folder_drifted(
        self, layout: Layout, capsys: pytest.CaptureFixture[str]
    ) -> None:
        fixtures.run_write(layout, FakeSkill())
        directory = fixtures.fixtures_dir(layout)
        (directory / "01-linear-chain.manifest.json").unlink()
        (directory / "extra.json").write_text("{}", encoding="utf-8")

        code = fixtures.run_check(layout, FakeSkill())

        err = capsys.readouterr().err
        assert code == EXIT_FAILED
        assert "missing: 01-linear-chain.manifest.json" in err
        assert "not a fixture: extra.json" in err

    def test_run_check_writes_nothing_when_files_differ(self, layout: Layout) -> None:
        fixtures.run_write(layout, FakeSkill())
        edited = fixtures.fixtures_dir(layout) / "10-human-review.payload.json"
        edited.write_text("{}", encoding="utf-8")

        fixtures.run_check(layout, FakeSkill())

        assert edited.read_text(encoding="utf-8") == "{}"

    def test_run_check_fails_without_comparing_when_a_draft_fails_validation(
        self, layout: Layout, capsys: pytest.CaptureFixture[str]
    ) -> None:
        fixtures.run_write(layout, FakeSkill())
        skill = FakeSkill(frozenset({"05-fanout-per-item.manifest.json"}))

        code = fixtures.run_check(layout, skill)

        err = capsys.readouterr().err
        assert code == EXIT_FAILED
        assert "validate_manifest.py" in err
        assert "differs:" not in err


class TestCommandLine:
    def test_modes_registers_write_and_check_when_module_is_imported(self) -> None:
        assert set(fixtures._MODES) == {"write", "check"}

    def test_main_exits_with_usage_error_when_no_mode_is_given(self) -> None:
        with pytest.raises(SystemExit) as raised:
            fixtures.main([])

        assert raised.value.code == 2

    def test_main_exits_with_usage_error_when_both_modes_are_given(self) -> None:
        with pytest.raises(SystemExit) as raised:
            fixtures.main(["--write", "--check"])

        assert raised.value.code == 2
