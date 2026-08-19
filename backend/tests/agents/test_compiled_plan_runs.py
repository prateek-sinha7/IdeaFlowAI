"""MAN-04 integration — the 12 dispatchable pipelines (+ od_prototype) run from
their CompiledWorkflow, with no legacy pipeline_type dispatch fallback.

Reuses the offline end-to-end engine harness ``_drive`` (tests/agents/
_scripted_model.py) — the SAME harness the Phase-0A characterization snapshots
use — to drive ``ExecutionEngine.execute()`` for each dispatchable pipeline and
assert:

  * The run produces events end-to-end (it executed).
  * The run sourced its agent sequence FROM the CompiledWorkflow: the agent ids
    that actually started (``agent_start`` events) equal the compiled plan's step
    order (``compile_for_run(...).steps``) — proving the compiled-plan path
    executed and no legacy dispatch fallback reordered/replaced the sequence.

The 12 dispatchable ids = the 17 manifest-backed pipelines minus ``chat``
(ChatRunner-driven, never engine-dispatched), ``reverse_engineer``
(empty-plan stub), and the three agentless ``sample_*`` fixtures that cannot
load. Plus the ``od_prototype`` alias, which must run the ``prototype`` plan
(D-04).

FIX-051 / ISS-035: scoped to manifest-backed pipelines (not raw
``PIPELINE_AGENTS`` keys) — ``PIPELINE_AGENTS`` is now derived from a folder
scan and can contain a pipeline_type with real agents but no manifest yet
(e.g. ``spec_kit``), which cannot be dispatched/compiled.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agents.execution_engine.engine import compile_for_run, resolve_alias
from agents.loader import SUPPORTED_PIPELINE_TYPES, load_agent_spec
from agents.registry import get_pipeline_agents
from tests.agents._scripted_model import _drive

_MANIFEST_BASE = Path(__file__).resolve().parents[2] / "agents" / "workflows"


def _every_step_agent_loads(pipeline_type: str) -> bool:
    """True when this manifest's steps all resolve to a real, loadable agent.

    ADR-0005: ``SUPPORTED_PIPELINE_TYPES`` is derived from disk, so a directory
    dropped under ``agents/workflows/`` now joins this set automatically. Three
    of them — ``sample_brownfield``, ``sample_fanout``, ``sample_wave`` — are
    engine test fixtures that reference agent ids with NO ``AGENT.md`` on disk.
    They cannot be dispatched: the roster build raises ``FileNotFoundError``
    before the first agent starts.

    Filtering on that PROPERTY rather than on a name prefix is deliberate
    (SC-001: never a hardcoded name list). If someone adds the missing
    ``AGENT.md`` files those fixtures become dispatchable and join this suite
    on their own; if someone adds a new broken manifest it stays out, and the
    count assertion below tells them the set moved.
    """
    try:
        compiled = compile_for_run(pipeline_type)
    except Exception:  # noqa: BLE001 - unparseable/absent manifest is "not dispatchable"
        return False
    for step in compiled.steps:
        try:
            load_agent_spec(step.agent_id)
        except Exception:  # noqa: BLE001 - a missing AGENT.md is "not dispatchable"
            return False
    return True


_MANIFEST_BACKED_IDS = {
    pt
    for pt in SUPPORTED_PIPELINE_TYPES
    if (_MANIFEST_BASE / pt / "workflow.yaml").exists() and _every_step_agent_loads(pt)
}

# 13 engine-dispatchable ids. There is no longer an alias to append: the
# od_prototype label was collapsed onto prototype (registry._OD_ALIAS_BASE is empty).
_DISPATCHABLE = sorted(_MANIFEST_BACKED_IDS - {"chat", "reverse_engineer"})
_PARAMS = _DISPATCHABLE


def test_dispatchable_count_is_13() -> None:
    """Exactly 13 engine-dispatchable pipelines, minus chat + reverse_engineer.

    Went 12 -> 13 when ``custom_revision`` was authored alongside the composed
    workflow builder; this count was not updated with it.

    ``sample_subagents_parallel`` is included: a real, manifest-backed,
    fully-loadable workflow (its steps are ``custom-agent`` instances and
    ``custom-agent/AGENT.md`` exists) that only became visible here once
    ``SUPPORTED_PIPELINE_TYPES`` stopped being a hand-typed frozenset
    (ADR-0005). It is the spec-012 proof workflow.

    Its three siblings ``sample_brownfield`` / ``sample_fanout`` /
    ``sample_wave`` are NOT here, and not by name: ``_every_step_agent_loads``
    excludes them because they reference agent ids with no ``AGENT.md``. Give
    them their agents and they join automatically.
    """
    assert len(_DISPATCHABLE) == 13
    assert "chat" not in _DISPATCHABLE
    assert "reverse_engineer" not in _DISPATCHABLE
    # The three agentless fixtures must stay out — they cannot be dispatched.
    for broken in ("sample_brownfield", "sample_fanout", "sample_wave"):
        assert broken not in _DISPATCHABLE, (
            f"{broken} references agents with no AGENT.md and cannot run; "
            "if it now has them, that is a real change — update this list"
        )
    # Parametrized coverage = 12 dispatchable + od_prototype alias.
    assert len(_PARAMS) == 13


@pytest.mark.asyncio
@pytest.mark.parametrize("pipeline_type", _PARAMS)
async def test_runs_from_compiled_plan(pipeline_type: str) -> None:
    """Each dispatchable pipeline (+ od_prototype) runs from its CompiledWorkflow.

    Drives execute() via _drive and asserts (a) it produced events and (b) the
    agents that actually started match the compiled plan's step order — i.e. the
    run sourced its agent sequence from the compiled plan, with no legacy
    pipeline_type dispatch fallback.
    """
    events = await _drive(pipeline_type)
    assert events, f"{pipeline_type}: produced no events"

    # The compiled plan is the SOURCE of the agent sequence (no legacy fallback).
    compiled = compile_for_run(pipeline_type)
    assert compiled.steps, f"{pipeline_type}: compiled plan has no steps"
    # A `subagents: {mode: parallel}` child is dispatched by its PARENT through the
    # kernel run_fanout spawn path, not by the engine's serial loop — but it now
    # ALSO emits its own live top-level `agent_start`/`agent_complete` via the
    # fan-out side-channel queue (per-child live streaming, merged into the normal
    # event stream alongside `subagent_spawned`/`subagent_result`). So the full
    # compiled membership (serial + fanout children) is what `started` must match.
    compiled_ids = [s.agent_id for s in compiled.steps]
    assert compiled_ids, f"{pipeline_type}: compiled plan has no steps"

    # The od_prototype alias must compile to the prototype manifest's plan.
    manifest_id = resolve_alias(pipeline_type)
    assert compiled.id == manifest_id

    # Agents that actually started during the run.
    started = [
        e["data"]["agent_id"]
        for e in events
        if e["type"] == "agent_start" and "agent_id" in e.get("data", {})
    ]

    # The set of agents that actually ran must equal the compiled plan's agent
    # MEMBERSHIP — proving the run sourced its agents from the CompiledWorkflow
    # with no legacy dispatch fallback selecting a different set. (Execution ORDER
    # is the resolver's topo-sorted DAG (validation.dag), which legitimately
    # reorders contract-coupled agents in the code-gen pipelines; the exact order
    # is byte-identical to pre-seam and is guarded by the characterization
    # snapshots, not asserted here. The build loop runs prototype-build once per
    # task, so it may start more than once — a set comparison absorbs that.)
    assert set(started) == set(compiled_ids), (
        f"{pipeline_type}: the agents that ran {sorted(set(started))} do not match "
        f"the compiled plan membership {sorted(set(compiled_ids))} — the run did "
        f"not source its agents from the CompiledWorkflow"
    )
    assert len(started) >= len(compiled_ids), (
        f"{pipeline_type}: fewer agents started than the compiled plan declares"
    )


@pytest.mark.asyncio
async def test_prototype_runs_its_own_plan() -> None:
    """``prototype`` drives its own manifest end-to-end under its own name.

    Was ``test_od_prototype_alias_runs_prototype_plan``. The alias used to be the
    only label that reached this plan in practice, because a bare ``prototype``
    launch was rejected upstream by the template-context guard. The alias is gone
    (registry ``_OD_ALIAS_BASE`` is empty) — this asserts the plain name inherited
    the behaviour rather than losing it.
    """
    events = await _drive("prototype")
    assert events

    compiled = compile_for_run("prototype")
    assert compiled.id == "prototype"
    expected = [a.id for a in get_pipeline_agents("prototype")]
    assert [s.agent_id for s in compiled.steps] == expected
