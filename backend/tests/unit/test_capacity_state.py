"""Tests for app/services/capacity_state.py — the pure admission decision logic
and the process-wide snapshot/decision holders (specs/014).

evaluate_admission is a pure function of its explicit arguments, so these are
plain unit tests plus a hypothesis property suite — no AWS mocking, no
``moto``, no patched clock (this repo has neither freezegun nor
pytest-freezegun; ``now`` is always passed in explicitly, per the convention
documented at test_cognito_verifier.py:370-380).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from hypothesis import HealthCheck, given, settings as hyp_settings
from hypothesis import strategies as st

from app.services import capacity_state as cs

UTC = timezone.utc


def _instance(
    instance_id: str = "i-1",
    *,
    cpu: float | None = None,
    mem: float | None = None,
    timestamp: datetime | None = None,
) -> cs.InstanceCapacity:
    return cs.InstanceCapacity(
        instance_id=instance_id,
        instance_type="t3.large",
        cpu_used_percent=cpu,
        mem_used_percent=mem,
        cpu_user_percent=None,
        cpu_system_percent=None,
        cpu_iowait_percent=None,
        timestamp=timestamp,
    )


def _snapshot(
    *instances: cs.InstanceCapacity,
    self_id: str | None = "i-1",
    now: datetime,
) -> cs.CapacitySnapshot:
    return cs.CapacitySnapshot(
        instances=tuple(instances),
        collected_at=now,
        self_instance_id=self_id,
        instance_source="discovery",
    )


# ---------------------------------------------------------------------------
# InstanceCapacity — age / staleness helpers
# ---------------------------------------------------------------------------


class TestInstanceCapacityStaleness:
    def test_age_seconds_none_when_no_timestamp(self):
        inst = _instance(timestamp=None)
        now = datetime.now(UTC)
        assert inst.age_seconds(now) is None

    def test_age_seconds_computed_from_timestamp(self):
        now = datetime.now(UTC)
        inst = _instance(timestamp=now - timedelta(seconds=42))
        assert inst.age_seconds(now) == pytest.approx(42.0, abs=0.01)

    def test_is_stale_true_when_no_timestamp(self):
        inst = _instance(timestamp=None)
        now = datetime.now(UTC)
        assert inst.is_stale(now, max_staleness_seconds=300) is True

    def test_is_stale_true_past_bound(self):
        now = datetime.now(UTC)
        inst = _instance(timestamp=now - timedelta(seconds=301))
        assert inst.is_stale(now, max_staleness_seconds=300) is True

    def test_is_stale_false_within_bound(self):
        now = datetime.now(UTC)
        inst = _instance(timestamp=now - timedelta(seconds=299))
        assert inst.is_stale(now, max_staleness_seconds=300) is False


# ---------------------------------------------------------------------------
# evaluate_admission — blind / fail-open (D-03, D-04)
# ---------------------------------------------------------------------------


class TestFailOpen:
    def test_blind_when_no_instances_in_scope(self):
        now = datetime.now(UTC)
        snap = _snapshot(self_id=None, now=now)  # no self id resolved at all
        decision = cs.evaluate_admission(snap, cs.INITIAL_ADMISSION_STATE, now)
        assert decision.blind is True
        assert decision.engaged is False

    def test_blind_when_self_id_not_in_snapshot(self):
        now = datetime.now(UTC)
        other = _instance("i-other", cpu=99.0, mem=99.0, timestamp=now)
        snap = _snapshot(other, self_id="i-1", now=now)
        decision = cs.evaluate_admission(snap, cs.INITIAL_ADMISSION_STATE, now)
        assert decision.blind is True
        assert decision.engaged is False

    def test_blind_when_both_signals_missing(self):
        now = datetime.now(UTC)
        inst = _instance(cpu=None, mem=None, timestamp=now)
        snap = _snapshot(inst, now=now)
        decision = cs.evaluate_admission(snap, cs.INITIAL_ADMISSION_STATE, now)
        assert decision.blind is True

    def test_blind_when_both_signals_stale(self):
        now = datetime.now(UTC)
        old = now - timedelta(seconds=1000)
        inst = _instance(cpu=95.0, mem=95.0, timestamp=old)
        snap = _snapshot(inst, now=now)
        decision = cs.evaluate_admission(
            snap, cs.INITIAL_ADMISSION_STATE, now, max_staleness_seconds=300
        )
        assert decision.blind is True
        assert decision.engaged is False

    def test_not_blind_when_only_one_signal_available(self):
        """CPU alone (memory missing) is enough to make a real decision —
        the gate must not go blind just because one of two signals is absent."""
        now = datetime.now(UTC)
        inst = _instance(cpu=90.0, mem=None, timestamp=now)
        snap = _snapshot(inst, now=now)
        decision = cs.evaluate_admission(
            snap, cs.INITIAL_ADMISSION_STATE, now, cpu_threshold=75.0
        )
        assert decision.blind is False

    def test_stale_reading_never_engages_even_if_high(self):
        """A frozen 95%-reading from an hour ago must not gate the product
        forever — staleness makes it as good as absent (D-04)."""
        now = datetime.now(UTC)
        old = now - timedelta(hours=1)
        inst = _instance(cpu=95.0, mem=None, timestamp=old)
        snap = _snapshot(inst, now=now)
        decision = cs.evaluate_admission(
            snap,
            cs.INITIAL_ADMISSION_STATE,
            now,
            cpu_threshold=75.0,
            max_staleness_seconds=300,
        )
        assert decision.blind is True
        assert decision.engaged is False


# ---------------------------------------------------------------------------
# evaluate_admission — hysteresis (D-05)
# ---------------------------------------------------------------------------


class TestHysteresis:
    def test_below_threshold_never_engages(self):
        now = datetime.now(UTC)
        inst = _instance(cpu=50.0, mem=40.0, timestamp=now)
        snap = _snapshot(inst, now=now)
        decision = cs.evaluate_admission(
            snap, cs.INITIAL_ADMISSION_STATE, now, cpu_threshold=75, mem_threshold=75
        )
        assert decision.engaged is False
        assert decision.blind is False

    def test_single_breach_does_not_engage(self):
        """One breaching datapoint is not enough — confirmation requires
        breach_datapoints_required consecutive ticks."""
        now = datetime.now(UTC)
        inst = _instance(cpu=90.0, mem=None, timestamp=now)
        snap = _snapshot(inst, now=now)
        decision = cs.evaluate_admission(
            snap,
            cs.INITIAL_ADMISSION_STATE,
            now,
            cpu_threshold=75,
            breach_datapoints_required=2,
        )
        assert decision.engaged is False
        assert decision.breach_streak == 1

    def test_two_consecutive_breaches_engage(self):
        now = datetime.now(UTC)
        inst = _instance(cpu=90.0, mem=None, timestamp=now)
        snap = _snapshot(inst, now=now)
        d1 = cs.evaluate_admission(
            snap,
            cs.INITIAL_ADMISSION_STATE,
            now,
            cpu_threshold=75,
            breach_datapoints_required=2,
        )
        d2 = cs.evaluate_admission(
            snap,
            d1,
            now + timedelta(seconds=30),
            cpu_threshold=75,
            breach_datapoints_required=2,
        )
        assert d1.engaged is False
        assert d2.engaged is True
        assert d2.signals == (cs.Signal(name="cpu", value=90.0, threshold=75.0),)

    def test_breach_streak_resets_on_a_cool_tick_before_confirmation(self):
        now = datetime.now(UTC)
        hot = _instance(cpu=90.0, mem=None, timestamp=now)
        cool = _instance(cpu=50.0, mem=None, timestamp=now)
        d1 = cs.evaluate_admission(
            _snapshot(hot, now=now),
            cs.INITIAL_ADMISSION_STATE,
            now,
            cpu_threshold=75,
            breach_datapoints_required=2,
        )
        d2 = cs.evaluate_admission(
            _snapshot(cool, now=now),
            d1,
            now + timedelta(seconds=30),
            cpu_threshold=75,
            breach_datapoints_required=2,
        )
        assert d1.breach_streak == 1
        assert d2.breach_streak == 0
        assert d2.engaged is False

    def test_dropping_below_threshold_but_above_clear_margin_stays_engaged(self):
        """Classic hysteresis: engaged at 90, drops to 70 (still >= 65 clear
        bar with a 10-point margin off a 75 threshold) — must stay engaged."""
        now = datetime.now(UTC)
        hot = _instance(cpu=90.0, mem=None, timestamp=now)
        d1 = cs.evaluate_admission(
            _snapshot(hot, now=now),
            cs.INITIAL_ADMISSION_STATE,
            now,
            cpu_threshold=75,
            breach_datapoints_required=1,
        )
        assert d1.engaged is True

        mid = _instance(cpu=70.0, mem=None, timestamp=now + timedelta(seconds=30))
        d2 = cs.evaluate_admission(
            _snapshot(mid, now=now),
            d1,
            now + timedelta(seconds=30),
            cpu_threshold=75,
            clear_margin=10,
            min_block_seconds=999,
        )
        assert d2.engaged is True

    def test_dropping_below_clear_margin_and_past_min_block_clears(self):
        now = datetime.now(UTC)
        hot = _instance(cpu=90.0, mem=None, timestamp=now)
        d1 = cs.evaluate_admission(
            _snapshot(hot, now=now),
            cs.INITIAL_ADMISSION_STATE,
            now,
            cpu_threshold=75,
            breach_datapoints_required=1,
        )
        assert d1.engaged is True

        cool = _instance(cpu=50.0, mem=None, timestamp=now + timedelta(seconds=90))
        d2 = cs.evaluate_admission(
            _snapshot(cool, now=now),
            d1,
            now + timedelta(seconds=90),
            cpu_threshold=75,
            clear_margin=10,
            min_block_seconds=60,
        )
        assert d2.engaged is False

    def test_min_block_seconds_holds_engaged_even_when_cool(self):
        """Even a fully-cool reading cannot clear the gate before
        min_block_seconds has elapsed since it engaged — this is what stops a
        single spike from producing a three-second modal flash."""
        now = datetime.now(UTC)
        hot = _instance(cpu=90.0, mem=None, timestamp=now)
        d1 = cs.evaluate_admission(
            _snapshot(hot, now=now),
            cs.INITIAL_ADMISSION_STATE,
            now,
            cpu_threshold=75,
            breach_datapoints_required=1,
        )
        cool = _instance(cpu=10.0, mem=None, timestamp=now + timedelta(seconds=5))
        d2 = cs.evaluate_admission(
            _snapshot(cool, now=now),
            d1,
            now + timedelta(seconds=5),
            cpu_threshold=75,
            clear_margin=10,
            min_block_seconds=60,
        )
        assert d2.engaged is True

    def test_memory_alone_can_engage(self):
        now = datetime.now(UTC)
        inst = _instance(cpu=None, mem=90.0, timestamp=now)
        snap = _snapshot(inst, now=now)
        d1 = cs.evaluate_admission(
            snap,
            cs.INITIAL_ADMISSION_STATE,
            now,
            mem_threshold=75,
            breach_datapoints_required=1,
        )
        assert d1.engaged is True
        assert d1.signals[0].name == "memory"

    def test_admin_matrix_signal_carries_real_numbers(self):
        """specs/014 §10 Resolutions Q4 — the operator confirmed the rejected
        caller sees actual numbers, not just 'busy'. Assert the Signal really
        carries the measured value and the configured threshold."""
        now = datetime.now(UTC)
        inst = _instance(cpu=None, mem=81.4, timestamp=now)
        snap = _snapshot(inst, now=now)
        d1 = cs.evaluate_admission(
            snap,
            cs.INITIAL_ADMISSION_STATE,
            now,
            mem_threshold=75.0,
            breach_datapoints_required=1,
        )
        assert d1.signals == (cs.Signal(name="memory", value=81.4, threshold=75.0),)


# ---------------------------------------------------------------------------
# evaluate_admission — fleet_worst scope (D-06)
# ---------------------------------------------------------------------------


class TestFleetWorstScope:
    def test_fleet_worst_considers_every_instance(self):
        now = datetime.now(UTC)
        cool = _instance("i-1", cpu=10.0, mem=None, timestamp=now)
        hot = _instance("i-2", cpu=95.0, mem=None, timestamp=now)
        snap = _snapshot(cool, hot, self_id="i-1", now=now)
        decision = cs.evaluate_admission(
            snap,
            cs.INITIAL_ADMISSION_STATE,
            now,
            cpu_threshold=75,
            breach_datapoints_required=1,
            gate_scope="fleet_worst",
        )
        assert decision.engaged is True
        assert decision.signals[0].value == 95.0

    def test_self_scope_ignores_other_instances(self):
        now = datetime.now(UTC)
        cool = _instance("i-1", cpu=10.0, mem=None, timestamp=now)
        hot = _instance("i-2", cpu=95.0, mem=None, timestamp=now)
        snap = _snapshot(cool, hot, self_id="i-1", now=now)
        decision = cs.evaluate_admission(
            snap,
            cs.INITIAL_ADMISSION_STATE,
            now,
            cpu_threshold=75,
            breach_datapoints_required=1,
            gate_scope="self",
        )
        assert decision.engaged is False


# ---------------------------------------------------------------------------
# state_label
# ---------------------------------------------------------------------------


class TestStateLabel:
    def test_blind_label(self):
        assert cs.INITIAL_ADMISSION_STATE.state_label == "blind"

    def test_allowing_label(self):
        now = datetime.now(UTC)
        state = cs.AdmissionState(
            engaged=False,
            engaged_at=None,
            breach_streak=0,
            blind=False,
            blind_reason=None,
            signals=(),
            evaluated_at=now,
        )
        assert state.state_label == "allowing"

    def test_blocking_label(self):
        now = datetime.now(UTC)
        state = cs.AdmissionState(
            engaged=True,
            engaged_at=now,
            breach_streak=2,
            blind=False,
            blind_reason=None,
            signals=(),
            evaluated_at=now,
        )
        assert state.state_label == "blocking"


# ---------------------------------------------------------------------------
# instance_capacity_from_raw — duck-typed adapter off host_metrics' shape
# ---------------------------------------------------------------------------


class TestFromRaw:
    def test_adapts_a_duck_typed_raw_reading(self):
        class _FakeRaw:
            instance_id = "i-1"
            instance_type = "t3.large"
            cpu_used_percent = 42.0
            mem_used_percent = 33.0
            cpu_user_percent = 20.0
            cpu_system_percent = 15.0
            cpu_iowait_percent = 7.0
            timestamp = datetime.now(UTC)

        inst = cs.instance_capacity_from_raw(_FakeRaw())
        assert inst.instance_id == "i-1"
        assert inst.cpu_used_percent == 42.0
        assert inst.mem_used_percent == 33.0


# ---------------------------------------------------------------------------
# Process-wide holder — publish/current/advance
# ---------------------------------------------------------------------------


class TestStateHolder:
    def setup_method(self):
        cs.reset_state_for_tests()

    def teardown_method(self):
        cs.reset_state_for_tests()

    def test_initial_state_is_empty_and_blind(self):
        assert cs.current_snapshot() is cs.EMPTY_SNAPSHOT
        assert cs.current_decision().blind is True

    def test_publish_snapshot_is_read_back(self):
        now = datetime.now(UTC)
        snap = _snapshot(_instance(cpu=10.0, mem=10.0, timestamp=now), now=now)
        cs.publish_snapshot(snap)
        assert cs.current_snapshot() is snap

    def test_advance_publishes_both_snapshot_and_decision(self):
        now = datetime.now(UTC)
        snap = _snapshot(_instance(cpu=90.0, mem=None, timestamp=now), now=now)
        decision = cs.advance(snap, now)
        assert cs.current_snapshot() is snap
        assert cs.current_decision() is decision

    def test_advance_carries_hysteresis_across_calls(self):
        now = datetime.now(UTC)
        hot = _instance(cpu=90.0, mem=None, timestamp=now)
        d1 = cs.advance(_snapshot(hot, now=now), now)
        d2 = cs.advance(_snapshot(hot, now=now), now + timedelta(seconds=30))
        # With default settings (HOST_CAPACITY_BREACH_DATAPOINTS=2), two
        # consecutive advance() calls at 90% CPU must engage on the second.
        assert d1.engaged is False
        assert d2.engaged is True


# ---------------------------------------------------------------------------
# Property-based tests (hypothesis) — specs/014 §8
# ---------------------------------------------------------------------------


@st.composite
def _reading_or_none(draw: st.DrawFn) -> tuple[float | None, float | None]:
    """A (value, age_seconds) pair, or (None, None) for "no reading"."""
    has_value = draw(st.booleans())
    if not has_value:
        return None, None
    value = draw(st.floats(min_value=0.0, max_value=100.0, allow_nan=False))
    age = draw(st.floats(min_value=0.0, max_value=10_000.0, allow_nan=False))
    return value, age


class TestPropertyBased:
    @hyp_settings(
        max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @given(cpu=_reading_or_none(), mem=_reading_or_none())
    def test_never_blocks_when_every_reading_is_stale_or_absent(
        self,
        cpu: tuple[float | None, float | None],
        mem: tuple[float | None, float | None],
    ):
        """No combination of readings that are ALL either absent or beyond the
        staleness bound may ever result in an engaged gate — the gate must be
        blind (and therefore non-blocking) whenever it has no fresh data."""
        now = datetime.now(UTC)
        max_staleness = 300.0
        cpu_value, cpu_age = cpu
        mem_value, mem_age = mem

        # Force staleness: any present value gets an age STRICTLY beyond the bound.
        cpu_ts = (
            None
            if cpu_value is None
            else now - timedelta(seconds=max_staleness + 1 + cpu_age)
        )
        mem_ts = (
            None
            if mem_value is None
            else now - timedelta(seconds=max_staleness + 1 + mem_age)
        )
        # capacity_state has one combined (cpu, mem) reading per instance, so a
        # single InstanceCapacity carries both — use the "stalest wins" timestamp
        # for whichever field is present (each field's own None/timestamp still
        # governs its own is_stale check independently at evaluation time).
        inst = cs.InstanceCapacity(
            instance_id="i-1",
            instance_type=None,
            cpu_used_percent=cpu_value,
            mem_used_percent=mem_value,
            cpu_user_percent=None,
            cpu_system_percent=None,
            cpu_iowait_percent=None,
            timestamp=cpu_ts or mem_ts,
        )
        snap = _snapshot(inst, now=now)
        decision = cs.evaluate_admission(
            snap, cs.INITIAL_ADMISSION_STATE, now, max_staleness_seconds=max_staleness
        )
        assert decision.engaged is False

    @hyp_settings(
        max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @given(
        cpu_value=st.floats(min_value=0.0, max_value=100.0, allow_nan=False),
        mem_value=st.floats(min_value=0.0, max_value=100.0, allow_nan=False),
        threshold=st.floats(min_value=1.0, max_value=99.0, allow_nan=False),
    )
    def test_engaging_implies_at_least_one_signal_at_or_above_threshold(
        self, cpu_value: float, mem_value: float, threshold: float
    ):
        """If the function ever reports engaged=True (after enough confirming
        ticks), at least one reported signal's value must be >= its threshold
        (accounting for the hysteresis clear-margin only when already
        engaged — here we start from allowing, so the raw threshold applies)."""
        now = datetime.now(UTC)
        inst = _instance(cpu=cpu_value, mem=mem_value, timestamp=now)
        snap = _snapshot(inst, now=now)
        decision = cs.evaluate_admission(
            snap,
            cs.INITIAL_ADMISSION_STATE,
            now,
            cpu_threshold=threshold,
            mem_threshold=threshold,
            breach_datapoints_required=1,
        )
        if decision.engaged:
            assert any(s.value >= s.threshold for s in decision.signals)

    @hyp_settings(
        max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @given(
        cpu_value=st.one_of(
            st.none(), st.floats(min_value=0, max_value=100, allow_nan=False)
        ),
        mem_value=st.one_of(
            st.none(), st.floats(min_value=0, max_value=100, allow_nan=False)
        ),
    )
    def test_never_raises(self, cpu_value: float | None, mem_value: float | None):
        """The function must never raise regardless of input shape — it is
        the caller's ONLY defense against a monitoring outage (D-03)."""
        now = datetime.now(UTC)
        inst = _instance(cpu=cpu_value, mem=mem_value, timestamp=now)
        snap = _snapshot(inst, now=now)
        cs.evaluate_admission(snap, cs.INITIAL_ADMISSION_STATE, now)
