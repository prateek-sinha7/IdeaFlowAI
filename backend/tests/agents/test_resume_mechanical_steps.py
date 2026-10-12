"""Resume after a failed wave lands on the wave, not on step 0 (run 2867387c).

A mechanical step writes plain files, never a typed artifact, so the old completeness
scan read every one as incomplete and a resume restarted the backlog run from its
first step (a mechanical UI extract) — Clarify included.
"""

from __future__ import annotations

from types import SimpleNamespace as NS

import pytest

from agents.execution_engine.engine import ExecutionEngine

WAVE = 15


def _steps():
    """20 steps shaped like the backlog workflow: mechanical steps between LLM ones."""
    steps = []
    for i in range(20):
        if i == WAVE:
            steps.append(NS(agent_id=f"custom-agent:s{i}", strategy="wave_scheduler", mechanical=None))
        elif i in (0, 4, 9, 14, 16, 19):
            steps.append(NS(agent_id=f"custom-agent:s{i}", strategy=None, mechanical="assemble_backlog"))
        else:
            steps.append(NS(agent_id=f"custom-agent:s{i}", strategy="single_shot", mechanical=None))
    return steps


class _Store:
    def __init__(self, done_before: int, *, artifacts=True):
        steps = _steps()
        self.events = [
            NS(type="agent_complete", payload_json={"agent_id": s.agent_id})
            for s in steps[:done_before]
        ]
        self.refs = [
            NS(producer_agent=s.agent_id, task_id=None)
            for s in steps[:done_before]
            if artifacts and not s.mechanical and s.strategy != "wave_scheduler"
        ]
        wave = steps[WAVE].agent_id
        self.waves = [NS(step=wave, wave_index=w, status="completed") for w in range(3)]
        self.waves.append(NS(step=wave, wave_index=3, status="failed"))
        self.workers = [
            NS(parent_step=wave, worker_index=i, task_id=f"t{i}", status="complete")
            for i in range(3)
        ] + [NS(parent_step=wave, worker_index=3, task_id="t3", status="failed")]

    async def read_events(self, run_id, since):
        return self.events

    async def read_wave_runs(self, run_id):
        return self.waves

    async def tree(self, run_id):
        return self.refs

    async def read_subagent_runs(self, run_id):
        return self.workers


def _run(store):
    steps = _steps()
    ectx = NS(scoped_store=store, run_id="run-1")
    ordered = [NS(id=s.agent_id) for s in steps]
    return ExecutionEngine(), ectx, ordered, NS(steps=steps)


@pytest.mark.asyncio
async def test_a_failed_wave_after_mechanical_steps_resumes_at_the_wave():
    engine, ectx, ordered, compiled = _run(_Store(done_before=WAVE))
    assert await engine._first_incomplete_step(ectx, ordered, compiled) == WAVE


@pytest.mark.asyncio
async def test_the_wave_reruns_only_its_incomplete_workers():
    engine, ectx, ordered, compiled = _run(_Store(done_before=WAVE))
    done, _ = await engine._compute_resume_completed_task_ids(ectx, ordered, compiled)
    assert done[f"custom-agent:s{WAVE}"] == {"t0", "t1", "t2"}  # t3 (failed) re-runs


@pytest.mark.asyncio
async def test_a_mechanical_step_that_never_completed_is_still_the_resume_point():
    engine, ectx, ordered, compiled = _run(_Store(done_before=9))
    assert await engine._first_incomplete_step(ectx, ordered, compiled) == 9


@pytest.mark.asyncio
async def test_an_llm_step_without_its_artifact_is_still_incomplete():
    # Unchanged rule for model steps: agent_complete alone is not enough.
    engine, ectx, ordered, compiled = _run(_Store(done_before=WAVE, artifacts=False))
    assert await engine._first_incomplete_step(ectx, ordered, compiled) == 1
