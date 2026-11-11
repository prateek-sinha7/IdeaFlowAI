"""Contract: the builder snapshot helper never rewrites a snapshot silently.

Covers ``tests/contract/_builder_snapshot.py``: the update flag is opt-in, is not
``SNAPSHOT_UPDATE``, is refused in CI, and a rewrite is reported as a skip.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tests.contract._builder_snapshot import (
    UPDATE_ENV_VAR,
    assert_matches_snapshot,
    render_snapshot,
    update_requested,
)

_NAME = "sample.json"
_COMMITTED: dict[str, Any] = {"b": 1, "a": [1, 2]}


@pytest.fixture
def snapshot_dir(tmp_path: Path) -> Path:
    (tmp_path / _NAME).write_text(render_snapshot(_COMMITTED), encoding="utf-8")
    return tmp_path


def test_update_requested_is_false_when_environment_is_empty() -> None:
    assert update_requested({}) is False


@pytest.mark.parametrize("value", ["", "0", "true", "yes", "2"])
def test_update_requested_is_false_when_value_is_not_exactly_one(value: str) -> None:
    assert update_requested({UPDATE_ENV_VAR: value}) is False


def test_update_requested_is_false_when_only_the_golden_flag_is_set() -> None:
    assert update_requested({"SNAPSHOT_UPDATE": "1"}) is False


def test_update_requested_is_true_when_flag_is_exactly_one() -> None:
    assert update_requested({UPDATE_ENV_VAR: "1"}) is True


def test_assert_matches_snapshot_passes_when_data_is_equal_in_any_key_order(
    snapshot_dir: Path,
) -> None:
    assert_matches_snapshot(
        _NAME, {"a": [1, 2], "b": 1}, environ={}, directory=snapshot_dir
    )


def test_assert_matches_snapshot_fails_without_writing_when_data_differs(
    snapshot_dir: Path,
) -> None:
    before = (snapshot_dir / _NAME).read_bytes()

    with pytest.raises(pytest.fail.Exception, match=UPDATE_ENV_VAR):
        assert_matches_snapshot(
            _NAME, {"a": [1], "b": 1}, environ={}, directory=snapshot_dir
        )

    assert (snapshot_dir / _NAME).read_bytes() == before


def test_assert_matches_snapshot_fails_without_writing_when_golden_flag_is_set(
    snapshot_dir: Path,
) -> None:
    before = (snapshot_dir / _NAME).read_bytes()

    with pytest.raises(pytest.fail.Exception):
        assert_matches_snapshot(
            _NAME,
            {"changed": True},
            environ={"SNAPSHOT_UPDATE": "1"},
            directory=snapshot_dir,
        )

    assert (snapshot_dir / _NAME).read_bytes() == before


def test_assert_matches_snapshot_fails_when_snapshot_file_is_missing(
    tmp_path: Path,
) -> None:
    with pytest.raises(pytest.fail.Exception, match="missing"):
        assert_matches_snapshot(_NAME, {"a": 1}, environ={}, directory=tmp_path)

    assert not (tmp_path / _NAME).exists()


def test_assert_matches_snapshot_rewrites_and_skips_when_update_flag_is_set(
    snapshot_dir: Path,
) -> None:
    new_data = {"a": [1, 2, 3]}

    with pytest.raises(pytest.skip.Exception, match="REWRITTEN"):
        assert_matches_snapshot(
            _NAME, new_data, environ={UPDATE_ENV_VAR: "1"}, directory=snapshot_dir
        )

    assert json.loads((snapshot_dir / _NAME).read_text(encoding="utf-8")) == new_data


def test_assert_matches_snapshot_creates_the_file_when_update_flag_is_set_and_file_missing(
    tmp_path: Path,
) -> None:
    target = tmp_path / "nested"

    with pytest.raises(pytest.skip.Exception):
        assert_matches_snapshot(
            _NAME, {"a": 1}, environ={UPDATE_ENV_VAR: "1"}, directory=target
        )

    assert (target / _NAME).read_text(encoding="utf-8") == render_snapshot({"a": 1})


def test_assert_matches_snapshot_passes_without_rewrite_when_flag_set_and_data_equal(
    snapshot_dir: Path,
) -> None:
    assert_matches_snapshot(
        _NAME, _COMMITTED, environ={UPDATE_ENV_VAR: "1"}, directory=snapshot_dir
    )


def test_assert_matches_snapshot_refuses_to_rewrite_when_ci_is_set(
    snapshot_dir: Path,
) -> None:
    before = (snapshot_dir / _NAME).read_bytes()

    with pytest.raises(pytest.fail.Exception, match="CI"):
        assert_matches_snapshot(
            _NAME,
            {"changed": True},
            environ={UPDATE_ENV_VAR: "1", "CI": "true"},
            directory=snapshot_dir,
        )

    assert (snapshot_dir / _NAME).read_bytes() == before
