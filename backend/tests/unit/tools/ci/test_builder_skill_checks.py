"""Unit tests for ``tools.ci.builder_skill_checks``.

Covers ``--step-models`` with a fake ``ModelCatalog`` and a tmp snapshot, and the
mode registry. No test runs git or a skill script, and every path is under
``tmp_path``.

Requirements: 33.8, 41.4.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools.ci import builder_skill_checks
from tools.ci.builder_skill_checks import Layout


@pytest.fixture
def layout(tmp_path: Path) -> Layout:
    """A layout rooted in ``tmp_path`` (repo root) with ``backend/`` beneath it."""
    backend = tmp_path / "backend"
    backend.mkdir()
    return Layout(repo_root=tmp_path, backend_dir=backend)


class TestLayout:
    def test_skill_dir_is_workflow_builder_skills_folder_when_layout_is_built(
        self, layout: Layout, tmp_path: Path
    ) -> None:
        relative = "app/agents/workflow_builder/skills/velocity-workflow-creator"

        assert layout.skill_dir == tmp_path / "backend" / relative
        assert layout.skill_pathspec == f"backend/{relative}"


class TestSnapshotModelIds:
    def test_snapshot_model_ids_returns_ids_when_models_list_is_valid(self) -> None:
        catalog = {"models": [{"id": "a"}, {"id": "b", "label": "B"}], "agents": {}}

        assert builder_skill_checks.snapshot_model_ids(catalog) == {"a", "b"}

    @pytest.mark.parametrize(
        "catalog",
        [[], {}, {"models": "a"}, {"models": [{"label": "no id"}]}, {"models": ["a"]}],
    )
    def test_snapshot_model_ids_raises_when_models_list_is_malformed(
        self, catalog: object
    ) -> None:
        with pytest.raises(ValueError):
            builder_skill_checks.snapshot_model_ids(catalog)


class TestStepModelProblems:
    def test_step_model_problems_returns_empty_when_all_ids_are_in_snapshot(
        self,
    ) -> None:
        assert (
            builder_skill_checks.step_model_problems(["a", "b"], {"a", "b", "c"}) == []
        )

    def test_step_model_problems_names_each_missing_id_when_snapshot_lacks_them(
        self,
    ) -> None:
        problems = builder_skill_checks.step_model_problems(["b", "a", "c"], {"c"})

        assert problems == [
            "builder_step model missing from the catalog snapshot: a",
            "builder_step model missing from the catalog snapshot: b",
        ]


def _fake_model_catalog(*entries: tuple[str, bool]) -> type:
    """A ``ModelCatalog`` stand-in listing ``(id, builder_step)`` entries."""
    items = [SimpleNamespace(id=i, builder_step=step) for i, step in entries]

    class _FakeCatalog:
        def list(self) -> list[SimpleNamespace]:
            return list(items)

    return _FakeCatalog


def _write_snapshot(layout: Layout, ids: Sequence[str]) -> None:
    path = layout.skill_dir / "references" / "catalog.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"models": [{"id": i} for i in ids]}), encoding="utf-8")


class TestRunStepModels:
    def test_run_step_models_returns_ok_when_step_models_are_in_snapshot(
        self,
        layout: Layout,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _write_snapshot(layout, ["step-a", "chat-only", "extra"])
        monkeypatch.setattr(
            builder_skill_checks,
            "ModelCatalog",
            _fake_model_catalog(("step-a", True), ("chat-only", False)),
        )

        code = builder_skill_checks.run_step_models(layout)

        assert code == builder_skill_checks.EXIT_OK
        assert "1 builder_step models" in capsys.readouterr().out

    def test_run_step_models_fails_and_names_id_when_snapshot_lacks_step_model(
        self,
        layout: Layout,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _write_snapshot(layout, ["step-a"])
        monkeypatch.setattr(
            builder_skill_checks,
            "ModelCatalog",
            _fake_model_catalog(("step-a", True), ("step-b", True), ("other", False)),
        )

        code = builder_skill_checks.run_step_models(layout)

        err = capsys.readouterr().err
        assert code == builder_skill_checks.EXIT_FAILED
        assert "step-b" in err
        assert "other" not in err
        assert "refresh_catalog.py --source ." in err

    def test_run_step_models_fails_when_no_entry_is_a_step_model(
        self, layout: Layout, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write_snapshot(layout, ["a"])
        monkeypatch.setattr(
            builder_skill_checks, "ModelCatalog", _fake_model_catalog(("a", False))
        )

        assert (
            builder_skill_checks.run_step_models(layout)
            == builder_skill_checks.EXIT_FAILED
        )

    def test_run_step_models_fails_when_snapshot_file_is_missing(
        self,
        layout: Layout,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setattr(
            builder_skill_checks, "ModelCatalog", _fake_model_catalog(("a", True))
        )

        code = builder_skill_checks.run_step_models(layout)

        assert code == builder_skill_checks.EXIT_FAILED
        assert "cannot read" in capsys.readouterr().err


class TestModeRegistry:
    def test_modes_lists_only_selftest_and_step_models_when_module_is_imported(
        self,
    ) -> None:
        assert builder_skill_checks._MODES == {
            "selftest": builder_skill_checks.run_selftest,
            "step-models": builder_skill_checks.run_step_models,
        }
