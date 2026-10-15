"""QA-KB-098 fixer probe: NO shim. Records playwright's two ContextVars at each test's setup and
teardown, to show the fixed test (save/restore of the removed global deleted) leaves no binding
behind. App import is lazy (inside the fixture) so it cannot run before tests/conftest.py pins env."""
import os
import pytest

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "leak.txt")


@pytest.fixture(autouse=True)
def _leak_probe(request):
    from app.agents.tools import playwright as pw

    with open(OUT, "a") as fh:
        fh.write(f"SETUP    {request.node.name}: _SANDBOX_VAR={pw._SANDBOX_VAR.get()!r} _AGENT_KEY_VAR={pw._AGENT_KEY_VAR.get()!r} has_global_SANDBOX={hasattr(pw, '_SANDBOX')}\n")
    yield
    with open(OUT, "a") as fh:
        fh.write(f"TEARDOWN {request.node.name}: _SANDBOX_VAR={pw._SANDBOX_VAR.get()!r} _AGENT_KEY_VAR={pw._AGENT_KEY_VAR.get()!r} has_global_SANDBOX={hasattr(pw, '_SANDBOX')}\n")
