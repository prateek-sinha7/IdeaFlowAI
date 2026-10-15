"""EXPERIMENT ONLY: after each test, dump the workflow_runs row + durable run_events types
from the harness's in-memory DB, to see what a swallowed resume drive leaves behind."""
import pytest

OUT = "/private/tmp/claude-502/-Users-bilala-Developer-Projects-VELOCITY-AI-worktrees-feat-user-stories-v2/2d1a1575-310a-48fd-8155-2763a084604d/scratchpad/qa-kb-097/dump.txt"
STASH = {}


@pytest.fixture(autouse=True)
def _dump_state(monkeypatch, request):
    import tests.integration.agents.test_restart_resume_db as m

    orig = m._make_session

    def spy():
        s, e = orig()
        STASH["session"] = s
        return s, e

    monkeypatch.setattr(m, "_make_session", spy)
    yield
    s = STASH.get("session")
    if s is None:
        return
    from app.models.run_event import RunEvent
    from app.models.workflow import WorkflowRun

    try:
        s.expire_all()
        with open(OUT, "a") as fh:
            fh.write(f"##### {request.node.name}\n")
            for r in s.query(WorkflowRun).all():
                fh.write(f"workflow_runs: id={r.id} status={r.status!r} error={r.error!r}\n")
            evs = s.query(RunEvent).order_by(RunEvent.seq.asc()).all()
            fh.write("run_events types (seq order): " + ", ".join(f"{e.seq}:{e.type}" for e in evs) + "\n")
    except Exception as exc:  # noqa: BLE001
        with open(OUT, "a") as fh:
            fh.write(f"dump failed: {exc!r}\n")
