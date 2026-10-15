"""Scratch probe for QA-KB-061 (analyzer). Edits NO repo file.

Patches live module objects in-process, lazily in pytest_runtest_setup (after the
repo conftest has pinned DATABASE_URL), so it can show what the PROPOSED fixes do:
  PROBE_FIX_A=1  _launch_run_core resolves the revision parent from
                 (request_source_workflow_run_id or source_workflow_run_id)
  PROBE_FIX_C=1  events that follow agent_start get the open agent_id, i.e. what
                 adding agent_id to the stale test fixtures would do
  PROBE_FIX_D=1  _mint_revision_row gets caller_tier="pro" when a caller omits it, i.e. what
                 passing caller_tier in the three stale _mint_revision_row tests would do
"""
import inspect
import os

import pytest

_done = False


def _apply():
    global _done
    if _done:
        return
    import app.api.run_commands as rc

    if os.environ.get("PROBE_FIX_A") == "1":
        src = inspect.getsource(rc._launch_run_core)
        old = "_resolve_owned_parent_run_id(db, source_workflow_run_id, user.id)"
        new = (
            "_resolve_owned_parent_run_id(\n"
            "                    db, request_source_workflow_run_id or source_workflow_run_id, user.id\n"
            "                )"
        )
        assert src.count(old) == 1, "expected exactly one parent-resolution site"
        exec(compile(src.replace(old, new), rc.__file__, "exec"), rc.__dict__)

    if os.environ.get("PROBE_FIX_C") == "1":
        orig = rc._apply_terminal_output_columns

        def wrapped(wr, events, *, model_id, duration_seconds):
            cur, fixed = None, []
            for t, d in events:
                d = dict(d) if isinstance(d, dict) else {}
                if t == "agent_start":
                    cur = d.get("agent_id")
                if t in ("agent_input", "agent_thinking", "tool_call", "tool_result",
                         "agent_chunk", "agent_complete", "agent_error") and not d.get("agent_id"):
                    d["agent_id"] = cur
                fixed.append((t, d))
            return orig(wr, fixed, model_id=model_id, duration_seconds=duration_seconds)

        rc._apply_terminal_output_columns = wrapped
    if os.environ.get("PROBE_FIX_D") == "1":
        _orig_mint = rc._mint_revision_row

        def _mint(*a, **kw):
            kw.setdefault("caller_tier", "pro")
            return _orig_mint(*a, **kw)

        rc._mint_revision_row = _mint
    _done = True


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_setup(item):  # noqa: ARG001
    _apply()
