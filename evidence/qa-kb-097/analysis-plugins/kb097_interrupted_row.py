"""EXPERIMENT ONLY: print the workflow_runs row status that test_cancel_stops_resumed_run_db's
_interrupted_run() hands to the resume tier ('resumable, non-terminal run' per its docstring)."""
import pytest

OUT = "/private/tmp/claude-502/-Users-bilala-Developer-Projects-VELOCITY-AI-worktrees-feat-user-stories-v2/2d1a1575-310a-48fd-8155-2763a084604d/scratchpad/qa-kb-097/interrupted_row.txt"


@pytest.fixture(autouse=True)
def _spy(monkeypatch, request):
    import tests.integration.agents.test_cancel_stops_resumed_run_db as m

    orig = m._interrupted_run

    async def wrapped(session, db_engine, call_log):
        run_id, owner = await orig(session, db_engine, call_log)
        from app.models.workflow import WorkflowRun

        session.expire_all()
        row = session.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
        with open(OUT, "a") as fh:
            fh.write(f"{request.node.name}: after instance A the row is status={row.status!r}\n")
        return run_id, owner

    monkeypatch.setattr(m, "_interrupted_run", wrapped)
    yield
