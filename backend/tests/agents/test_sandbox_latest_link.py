"""``<base>/<user>/.latest`` follows the most recently ensured run.

Run ids are fresh uuid4s, so without this link there is no predictable path to
the newest run's output. Staging dirs are deliberately excluded — they are
deleted at ingest, so a link pointing at one would dangle.
"""

from app.agents.sandbox import RunSandbox

USER = "u1"


def _latest(tmp_path):
    return tmp_path / USER / ".latest"


def test_latest_points_at_the_run_just_ensured(tmp_path):
    RunSandbox(USER, "run-a", runs_root=str(tmp_path)).ensure()
    assert _latest(tmp_path).resolve().name == "run-a"


def test_latest_repoints_on_the_next_run(tmp_path):
    RunSandbox(USER, "run-a", runs_root=str(tmp_path)).ensure()
    RunSandbox(USER, "run-b", runs_root=str(tmp_path)).ensure()
    assert _latest(tmp_path).resolve().name == "run-b"


def test_staging_sandbox_never_claims_the_link(tmp_path):
    RunSandbox(USER, "run-a", runs_root=str(tmp_path)).ensure()
    RunSandbox(USER, "staged-" + "0" * 32, runs_root=str(tmp_path)).ensure()
    assert _latest(tmp_path).resolve().name == "run-a"


def test_re_ensuring_the_same_run_is_idempotent(tmp_path):
    sb = RunSandbox(USER, "run-a", runs_root=str(tmp_path))
    sb.ensure()
    sb.ensure()
    assert _latest(tmp_path).is_symlink()
    assert _latest(tmp_path).resolve() == sb.root
