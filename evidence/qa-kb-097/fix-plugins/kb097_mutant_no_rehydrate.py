"""MUTATION CHECK ONLY (5-fixer, ISS-1104): put the D2 defect back -- the resume tier
rebuilds the planning context from the user_message stub instead of rehydrating the
durable planner + clarification rows. The rewritten PLANNER.md assertions must go red."""
import pytest


@pytest.fixture(autouse=True)
def _d2_mutant(monkeypatch):
    from agents.execution_engine import engine as eng

    monkeypatch.setattr(
        eng.ExecutionEngine,
        "_rehydrate_planning_context",
        lambda self, ectx, user_message: self._default_planning_context(user_message),
    )
    yield
