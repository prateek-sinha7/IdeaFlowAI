"""_seed_from_prior_run — the temporary launch-time copy of a prior run's files.

TODO: Remove with the hack (run_commands._seed_from_prior_run / sandbox .latest).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.agents.sandbox import RunSandbox
from app.api.run_commands import _seed_from_prior_run
from app.core.config import settings

USER = "user-a"
PRIOR = "11111111-1111-1111-1111-111111111111"
NEW = "22222222-2222-2222-2222-222222222222"


@pytest.fixture
def runs_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "runs"
    monkeypatch.setattr(settings, "RUNS_ROOT", str(root))
    return root


def _manifest(**seed) -> dict:
    return {"steps": [], "seed_files": seed}


def test_copies_declared_files_from_prior_run(runs_root: Path) -> None:
    RunSandbox(USER, PRIOR).write("synthesis.md", "# facts\n- one [user]\n")
    seeded = _seed_from_prior_run(
        user_id=USER,
        run_id=NEW,
        manifest_json=_manifest(from_run=["synthesis.md"], run_id=PRIOR),
    )
    assert seeded == ["synthesis.md"]
    assert RunSandbox(USER, NEW).read("synthesis.md") == "# facts\n- one [user]\n"


def test_no_seed_declared_is_a_noop(runs_root: Path) -> None:
    assert (
        _seed_from_prior_run(user_id=USER, run_id=NEW, manifest_json={"steps": []})
        == []
    )
    assert _seed_from_prior_run(user_id=USER, run_id=NEW, manifest_json=None) == []
    # from_run without a run_id (the declared revision surface) is not ours to act on.
    assert (
        _seed_from_prior_run(
            user_id=USER,
            run_id=NEW,
            manifest_json=_manifest(from_run=["synthesis.md"]),
        )
        == []
    )
    assert not (runs_root / USER / NEW).exists()


def test_missing_file_is_skipped_not_raised(runs_root: Path) -> None:
    RunSandbox(USER, PRIOR).write("synthesis.md", "x")
    seeded = _seed_from_prior_run(
        user_id=USER,
        run_id=NEW,
        manifest_json=_manifest(
            from_run=["synthesis.md", "validate.json"], run_id=PRIOR
        ),
    )
    assert seeded == ["synthesis.md"]
    assert RunSandbox(USER, NEW).read("validate.json") is None


def test_another_users_run_is_not_readable(runs_root: Path) -> None:
    RunSandbox("user-b", PRIOR).write("synthesis.md", "theirs")
    seeded = _seed_from_prior_run(
        user_id=USER,
        run_id=NEW,
        manifest_json=_manifest(from_run=["synthesis.md"], run_id=PRIOR),
    )
    assert seeded == []
    assert RunSandbox(USER, NEW).read("synthesis.md") is None


def test_path_escape_in_seed_name_is_swallowed(runs_root: Path) -> None:
    RunSandbox(USER, PRIOR).write("synthesis.md", "x")
    seeded = _seed_from_prior_run(
        user_id=USER,
        run_id=NEW,
        manifest_json=_manifest(
            from_run=["../../etc/passwd", "synthesis.md"], run_id=PRIOR
        ),
    )
    assert seeded == ["synthesis.md"]
