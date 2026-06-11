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


def test_wave_scheduler_is_registered():
    discover()
    reg = CapabilityRegistry()
    assert reg.is_registered("strategy", "wave_scheduler")
    assert WaveSchedulerStrategy().name == "wave_scheduler"
