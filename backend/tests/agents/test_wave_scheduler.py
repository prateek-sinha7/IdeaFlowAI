"""tests/agents/test_wave_scheduler.py — the pure build_waves seam + strategy registration.

Covers the deterministic Kahn-levels wave builder (diamond DAG → [[A],[B,C],[D]],
repeat-identical partitions, conflict-key split, targets-as-default-conflict-key,
cycle + unknown-ref WaveBuildError pre-spawn) and the wave_scheduler strategy
registration (WAVE-01).

Offline / pure (no DB / network / API key).
"""

from __future__ import annotations

import pytest

from agents.capabilities.registry import CapabilityRegistry, discover
from agents.capabilities.strategies.wave_scheduler import (
    WaveBuildError,
    WaveSchedulerStrategy,
    build_waves,
)
from agents.workflows.plan import Task


def _t(tid, *, depends_on=None, conflict_keys=None, targets=None):
    return Task(
        id=tid,
        title=tid,
        body=f"body-{tid}",
        depends_on=list(depends_on or []),
        conflict_keys=list(conflict_keys or []),
        targets=list(targets or []),
    )


def _ids(waves):
    return [sorted(t.id for t in w) for w in waves]


def test_diamond_dag_yields_three_waves():
    tasks = [
        _t("A"),
        _t("B", depends_on=["A"]),
        _t("C", depends_on=["A"]),
        _t("D", depends_on=["B", "C"]),
    ]
    waves = build_waves(tasks)
    assert _ids(waves) == [["A"], ["B", "C"], ["D"]]


def test_same_input_yields_byte_identical_partitions():
    tasks = [
        _t("A"),
        _t("B", depends_on=["A"]),
        _t("C", depends_on=["A"]),
        _t("D", depends_on=["B", "C"]),
    ]
    first = _ids(build_waves(tasks))
    second = _ids(build_waves(tasks))
    assert first == second


def test_two_tasks_sharing_conflict_key_split_into_different_waves():
    # A and B are both ready (no deps) but share conflict_key "k" → must NOT co-schedule.
    tasks = [
        _t("A", conflict_keys=["k"]),
        _t("B", conflict_keys=["k"]),
    ]
    waves = build_waves(tasks)
    assert len(waves) == 2
    # Deterministic: the lower id (A) is scheduled first; B spills to wave 2.
    assert _ids(waves) == [["A"], ["B"]]


def test_targets_default_as_conflict_keys_when_conflict_keys_empty():
    # Same target, no explicit conflict_keys → the documented default splits them.
    same_target = [_t("A", targets=["file.txt"]), _t("B", targets=["file.txt"])]
    assert _ids(build_waves(same_target)) == [["A"], ["B"]]

    # Disjoint targets → same wave (no conflict).
    disjoint = [_t("A", targets=["a.txt"]), _t("B", targets=["b.txt"])]
    assert _ids(build_waves(disjoint)) == [["A", "B"]]


def test_dependency_cycle_raises_before_returning_any_wave():
    tasks = [
        _t("A", depends_on=["B"]),
        _t("B", depends_on=["A"]),
    ]
    with pytest.raises(WaveBuildError) as exc:
        build_waves(tasks)
    assert "cycle" in str(exc.value).lower()


def test_unknown_depends_on_ref_raises_named_wave_build_error():
    tasks = [_t("A", depends_on=["ghost"])]
    with pytest.raises(WaveBuildError) as exc:
        build_waves(tasks)
    assert "A" in str(exc.value) and "ghost" in str(exc.value)


def test_conflict_split_preserves_dependents_in_later_wave():
    # A,B share key; C depends on B. B spills to wave 2, so C lands in wave 3.
    tasks = [
        _t("A", conflict_keys=["k"]),
        _t("B", conflict_keys=["k"]),
        _t("C", depends_on=["B"]),
    ]
    waves = build_waves(tasks)
    assert _ids(waves) == [["A"], ["B"], ["C"]]


def test_build_waves_rejects_duplicate_task_id_before_any_wave():
    """WR-05 (defense-in-depth): build_waves raises WaveBuildError on a duplicate id
    BEFORE returning any wave (zero spawn).

    Protects callers that construct tasks without going through json_tasks. FAILS on the
    pre-fix (last-wins ``by_id`` silently drops a task / can drive in-degrees negative).
    """
    tasks = [
        _t("a", targets=["x.txt"]),
        _t("b", depends_on=["a"]),
        _t("a", targets=["y.txt"]),  # duplicate id
    ]
    with pytest.raises(WaveBuildError) as exc:
        build_waves(tasks)
    assert "duplicate" in str(exc.value).lower()


def test_wave_scheduler_is_registered():
    discover()
    reg = CapabilityRegistry()
    assert reg.is_registered("strategy", "wave_scheduler")
    assert WaveSchedulerStrategy().name == "wave_scheduler"


# ===========================================================================
# CR-06 backend half — subagent_* events carry the wave's wave_index + step so
# the FE (12-07) can key worker leaves to their wave.
# ===========================================================================


class _StampFakeRunner:
    """A ctx.runner whose run_fanout yields the flat subagent_* events fanout.py emits
    (``{worker, agent, isolation, depth}`` — NO wave_index), so the test can assert the
    STRATEGY stamps the current wave_index + step onto them as it re-yields per wave."""

    def __init__(self):
        self.recorded = []

    def latest_typed_content(self, _step):
        return ""

    async def read_wave_runs(self):
        return []

    async def read_subagent_runs(self):
        return []

    async def record_wave_run(self, *, step, wave_index, task_ids, status):
        self.recorded.append((step, wave_index))
        return f"row-{wave_index}"

    async def update_wave_run(self, row_id, *, status):
        pass

    async def run_fanout(self, requests, ctx, *, step=None):
        # Mimic fanout.py: one subagent_spawned + one subagent_result per request, flat
        # data dicts with NO wave_index (the strategy must inject it).
        for i, _req in enumerate(requests):
            yield {
                "type": "subagent_spawned",
                "data": {"worker": i, "agent": "w", "isolation": "shared_read", "depth": 0},
            }
        for i, _req in enumerate(requests):
            yield {
                "type": "subagent_result",
                "data": {"worker": i, "agent": "w", "row_id": f"r{i}", "status": "complete"},
            }
        # A non-subagent event must pass through unchanged (no wave_index injected).
        yield {"type": "agent_chunk", "data": {"text": "x"}}


class _StampCtx:
    def __init__(self, runner):
        self.runner = runner
        self.is_resuming = False


class _StampStep:
    def __init__(self, agent_id):
        self.agent_id = agent_id
        self.task_source = type("TS", (), {"source_step": "plan", "parser": "json_tasks"})()


@pytest.mark.asyncio
async def test_subagent_events_carry_wave_index_and_step():
    """Every subagent_spawned/subagent_result emitted during a wave carries a numeric
    ``wave_index`` matching its wave AND a ``step`` == step_id. FAILS on the pre-fix
    re-yield (no wave_index/step on subagent events)."""
    strat = WaveSchedulerStrategy()
    runner = _StampFakeRunner()
    ctx = _StampCtx(runner)
    step = _StampStep("wave-step")

    # wave 0 = [ta, tb] (disjoint); wave 1 = [tc deps ta].
    tasks = [
        _t("ta", targets=["a.txt"]),
        _t("tb", targets=["b.txt"]),
        _t("tc", depends_on=["ta"], targets=["c.txt"]),
    ]

    class _FakeParser:
        def parse(self, _text):
            return tasks

    strat._registry = type("R", (), {"resolve": lambda self, k, n: _FakeParser()})()

    events = [ev async for ev in strat.run(step, ctx)]

    subagent_events = [
        e for e in events if e.get("type") in ("subagent_spawned", "subagent_result")
    ]
    assert subagent_events, "no subagent events were re-yielded"
    for e in subagent_events:
        data = e["data"]
        assert "wave_index" in data, f"subagent event missing wave_index: {e}"
        assert isinstance(data["wave_index"], int), (
            f"wave_index must be a number, got {type(data['wave_index'])}: {e}"
        )
        assert data.get("step") == "wave-step", f"subagent event missing step: {e}"
        # The existing flat worker index is preserved (not renamed / nested).
        assert "worker" in data and isinstance(data["worker"], int)

    # The wave_index actually matches the wave the workers belong to: wave 0 workers carry
    # wave_index 0, wave 1 workers carry wave_index 1.
    wave_indices = sorted({e["data"]["wave_index"] for e in subagent_events})
    assert wave_indices == [0, 1], f"subagent events did not span both waves: {wave_indices}"

    # A non-subagent event is NOT stamped with wave_index (pass-through unchanged).
    chunk = [e for e in events if e.get("type") == "agent_chunk"]
    assert chunk and "wave_index" not in chunk[0]["data"], (
        "a non-subagent event was wrongly stamped with wave_index"
    )
