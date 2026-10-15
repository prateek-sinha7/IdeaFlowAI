"""ISS-684 / QA-KB-065 — a mechanical kind with no engine dispatch branch must FAIL the run,
naming the step and the kind, instead of silently running a billed single_shot model step.

Offline: scripted-model harness over the ex_publish_step fixture, with the publish step's
``mechanical`` relabelled to a kind the engine chain lacks.
"""

from __future__ import annotations

import copy
import pathlib
import re

import pytest

from tests.agents.test_mechanical_publish_step import _publish_fixture_scripts_for

STEP = "custom-agent:publish"
BAD_KIND = "zz_new_kind"


@pytest.mark.issue("ISS-684")
@pytest.mark.asyncio
async def test_unhandled_mechanical_kind_fails_the_run():
    """ISS-684 — unknown mechanical kind -> agent_error + one pipeline_failed, no model run."""
    from agents.execution_engine import engine as engine_mod
    from tests.agents import _scripted_model as _sm
    from tests.agents._scripted_model import _drive

    orig_compile = engine_mod.compile_for_run

    def _relabel(pipeline_type, _orig=orig_compile):
        compiled = copy.deepcopy(_orig(pipeline_type))
        for s in compiled.steps:
            if getattr(s, "mechanical", None) == "publish":
                s.mechanical = BAD_KIND
        return compiled

    orig_scripts = _sm._scripts_for
    engine_mod.compile_for_run = _relabel
    _sm._scripts_for = _publish_fixture_scripts_for
    try:
        events = await _drive("ex_publish_step")
    finally:
        engine_mod.compile_for_run = orig_compile
        _sm._scripts_for = orig_scripts

    def of(t):
        return [e for e in events if e.get("type") == t]

    step_events = lambda t: [e for e in of(t) if e["data"].get("agent_id") == STEP]  # noqa: E731
    assert not step_events("agent_input"), "unhandled kind ran a model on the step"
    assert not step_events("agent_complete"), "unhandled kind completed as a model step"
    errors = step_events("agent_error")
    assert errors and errors[0]["data"].get("recoverable") is False
    failed = of("pipeline_failed")
    assert len(failed) == 1 and not of("pipeline_complete")
    assert failed[0]["data"].get("agents_failed") == [STEP]
    assert BAD_KIND in str(failed[0]["data"].get("error"))


@pytest.mark.issue("ISS-684")
def test_engine_dispatch_matches_registered_kinds():
    """ISS-684 — engine kinds == compiler/registry kinds (green today; guards the typo case)."""
    from agents.capabilities import registry as registry_mod
    from agents.workflows import compiler as compiler_mod

    registry_mod.discover()
    registered = {n for k, n in registry_mod._KNOWN if k == "mechanical"}
    src = (
        pathlib.Path(__file__).parents[2] / "agents/execution_engine/engine.py"
    ).read_text()
    handled = set(
        re.findall(r'getattr\(step, "mechanical", None\) == "([a-z_]+)"', src)
    )
    assert handled == registered == set(compiler_mod._ALLOWED_MECHANICAL_KINDS)
