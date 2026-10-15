"""MUTATION EXPERIMENT ONLY: re-introduce the ISS-084 defect (the resumed drive is handed no
cancel_event) by making ExecutionEngine._resolve_resume_cancel_event return None.
A guard that is still green under this mutant cannot detect the defect it claims to guard."""
import pytest


@pytest.fixture(autouse=True)
def _iss084_mutant(monkeypatch):
    from agents.execution_engine import engine as eng

    monkeypatch.setattr(eng.ExecutionEngine, "_resolve_resume_cancel_event", lambda self, run_id: None)
    yield
