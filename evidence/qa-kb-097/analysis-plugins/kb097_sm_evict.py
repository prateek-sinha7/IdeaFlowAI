"""EXPERIMENT ONLY (scratchpad, not in the repo): emulate a fresh process / endpoint step 6b.

Wraps ExecutionEngine.resume_run so the process-global StateMachine forgets the run first,
exactly what resume_run_endpoint does at run_commands.py "(6b)" before spawning the drive.
"""
import pytest


@pytest.fixture(autouse=True)
def _evict_state_machine_on_resume(monkeypatch):
    from agents.execution_engine import engine as eng
    from agents.execution_engine.state_machine import get_state_machine

    orig = eng.ExecutionEngine.resume_run

    async def patched(self, run_id):
        get_state_machine().forget_run(run_id)
        return await orig(self, run_id)

    monkeypatch.setattr(eng.ExecutionEngine, "resume_run", patched)
    yield
