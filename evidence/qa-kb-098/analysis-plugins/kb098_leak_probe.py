"""EXPERIMENT ONLY (QA-KB-098 analysis): does bind_sandbox()'s ContextVar write leak out of an
async test into whatever runs next?  Shims the missing global (as kb098_global_shim does) so the
real test body runs, and records the two ContextVars at every test's setup and teardown.
The app import is lazy (inside the fixture) so it cannot run before tests/conftest.py pins env."""
import pytest

OUT = "/private/tmp/claude-502/-Users-bilala-Developer-Projects-VELOCITY-AI-worktrees-feat-user-stories-v2/2d1a1575-310a-48fd-8155-2763a084604d/scratchpad/qa-kb-098/leak.txt"


@pytest.fixture(autouse=True)
def _leak_probe(monkeypatch, request):
    from app.agents.tools import playwright as pw

    monkeypatch.setattr(pw, "_SANDBOX", None, raising=False)
    with open(OUT, "a") as fh:
        fh.write(f"SETUP    {request.node.name}: _SANDBOX_VAR={pw._SANDBOX_VAR.get()!r} _AGENT_KEY_VAR={pw._AGENT_KEY_VAR.get()!r}\n")
    yield
    with open(OUT, "a") as fh:
        fh.write(f"TEARDOWN {request.node.name}: _SANDBOX_VAR={pw._SANDBOX_VAR.get()!r} _AGENT_KEY_VAR={pw._AGENT_KEY_VAR.get()!r}\n")
