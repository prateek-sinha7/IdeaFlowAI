"""Resume offset and dispatch loop must index the same step list.

backlog declares ``depends_on`` edges its contract DAG breaks, so the dispatch loop runs
in compiler order. The offset used to be computed over the raw DAG order instead: a run
that failed at us-assemble (DAG index 5) resumed at compiler index 5, us-solution, and
re-ran an hour of agents and gates.
"""

import asyncio

from agents.execution_engine.engine import ExecutionEngine, compile_for_run


def test_resume_offset_points_at_the_failed_step_in_dispatch_order(monkeypatch):
    engine = ExecutionEngine()
    compiled = compile_for_run("backlog")
    failed = "custom-agent:us-assemble"

    async def workspace(*a, **k):
        return "ws"

    async def first_incomplete(ectx, ordered_agents, compiled, *, sandbox=None):
        return [a.id for a in ordered_agents].index(failed)

    monkeypatch.setattr(engine, "_recover_workspace_id", workspace)
    monkeypatch.setattr(engine, "_first_incomplete_step", first_incomplete)
    offset = asyncio.run(
        engine._compute_resume_offset(
            "r1", "u1", None, "backlog", [], compiled=compiled
        )
    )

    specs = engine._specs_from_plan(compiled.steps)
    dispatch = ExecutionEngine._dispatch_order(
        engine._resolver.validate(specs), specs, compiled
    )
    assert dispatch[offset].id == failed
