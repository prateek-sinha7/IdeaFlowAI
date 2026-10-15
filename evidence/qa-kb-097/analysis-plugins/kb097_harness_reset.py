"""EXPERIMENT ONLY: model 'instance B is a new process' at the harness level.
_ResumeHarness.make_engine() resets the process-global StateMachine singleton before it
constructs an engine -- the fix location proposed for the 5 crash->resume tests."""
import pytest


@pytest.fixture(autouse=True)
def _harness_models_a_fresh_process(monkeypatch):
    import agents.execution_engine.state_machine as sm
    import tests.integration.agents.test_restart_resume_db as m

    monkeypatch.setattr(sm, "_MACHINE", sm._MACHINE)  # restored at teardown
    orig = m._ResumeHarness.make_engine

    def make_engine(self):
        sm._MACHINE = None  # a restart empties the in-memory state machine
        return orig(self)

    monkeypatch.setattr(m._ResumeHarness, "make_engine", make_engine)
    yield
