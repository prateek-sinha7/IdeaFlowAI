"""EXPERIMENT ONLY (QA-KB-098 analysis): give app.agents.tools.playwright the module global the
stale test expects, so the REST of the test body runs unchanged against the real tools.
This is a probe, not a fix: it answers 'is the AttributeError the only defect in the test?'.
The app import is lazy (inside the fixture) so it cannot run before tests/conftest.py pins env."""
import pytest


@pytest.fixture(autouse=True)
def _shim_stale_global(monkeypatch):
    from app.agents.tools import playwright as pw

    monkeypatch.setattr(pw, "_SANDBOX", None, raising=False)
    yield
