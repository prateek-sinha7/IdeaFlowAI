"""app/services/capacity_state.py — the pure decision logic + process-wide
snapshot holder for specs/014 (host capacity matrix + admission gate).

Deliberately zero AWS/boto3 awareness. This module knows nothing about
CloudWatch, EC2, or credentials — it only knows about instance readings
(CPU/memory percentages with a timestamp) and turns them into an admission
decision. That split is what makes ``evaluate_admission`` unit- and
property-testable with zero mocking (no ``moto``, no ``patch.object`` — see
specs/014 §8).

Two halves:

1. **Pure decision logic** — ``evaluate_admission(snapshot, prev, now, ...)``.
   A function of its explicit inputs only; the SAME inputs always produce the
   SAME output. Implements the three anti-flicker mechanisms from specs/014
   D-05 (engage/clear hysteresis band, consecutive-breach confirmation,
   minimum engaged duration) and the fail-open rule from D-03/D-04 (unknown or
   too-stale readings never block).

2. **Process-wide state holder** — ``publish_snapshot`` / ``current_snapshot``
   / ``advance``. A single background poller (``main.py``'s lifespan) is the
   only writer; every request-path reader (the gate, the admin matrix) reads
   an already-computed struct — no AWS call and no lock is ever on the request
   path (specs/014 §4). Module-level reassignment is atomic under the GIL and
   there is exactly one writer, so no lock is needed for the holder either.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

from app.core.config import settings

GateScope = Literal["self", "fleet_worst"]
GateStateLabel = Literal["allowing", "blocking", "blind"]

# The two metric kinds this module reasons about. Kept as a tuple (not an enum)
# because it doubles as the iteration order for building the ``signals`` list.
_SIGNAL_CPU = "cpu"
_SIGNAL_MEM = "memory"


@dataclass(frozen=True)
class InstanceCapacity:
    """One instance's reading, as the decision logic and the admin matrix see it.

    Deliberately shaped independently of ``host_metrics.RawInstanceReading``
    (which is AWS-response-shaped) — this is the domain type. ``timestamp`` is
    the datapoint's own CloudWatch time (UTC), never wall-clock-at-collection,
    so staleness reflects how old the DATA is, not how long ago we asked.
    """

    instance_id: str
    instance_type: str | None
    cpu_used_percent: float | None
    mem_used_percent: float | None
    cpu_user_percent: float | None
    cpu_system_percent: float | None
    cpu_iowait_percent: float | None
    timestamp: datetime | None

    def age_seconds(self, now: datetime) -> float | None:
        """Seconds between the datapoint's own timestamp and ``now``. ``None``
        when there is no timestamp at all (never had a reading)."""
        if self.timestamp is None:
            return None
        return (now - self.timestamp).total_seconds()

    def is_stale(self, now: datetime, max_staleness_seconds: float) -> bool:
        """True when the reading has no timestamp, or is older than the bound.
        A stale reading is treated identically to a missing one (D-04)."""
        age = self.age_seconds(now)
        return age is None or age > max_staleness_seconds


def instance_capacity_from_raw(raw: Any) -> InstanceCapacity:
    """Adapt a ``host_metrics.RawInstanceReading`` (or any duck-typed object
    exposing the same attributes) into the domain type. Duck-typed on
    purpose — this module never imports ``host_metrics``, so it carries no
    transitive boto3 dependency and stays trivially importable in any test.
    """
    return InstanceCapacity(
        instance_id=raw.instance_id,
        instance_type=raw.instance_type,
        cpu_used_percent=raw.cpu_used_percent,
        mem_used_percent=raw.mem_used_percent,
        cpu_user_percent=raw.cpu_user_percent,
        cpu_system_percent=raw.cpu_system_percent,
        cpu_iowait_percent=raw.cpu_iowait_percent,
        timestamp=raw.timestamp,
    )


@dataclass(frozen=True)
class CapacitySnapshot:
    """The full picture at one collection tick: every discovered instance's
    reading, plus which instance (if any) is "self" for this process.

    ``instance_source`` records how the instance list was resolved
    (``"override"`` | ``"discovery"`` | ``"none"``) purely for admin-matrix
    transparency — it plays no role in the decision logic.
    """

    instances: tuple[InstanceCapacity, ...]
    collected_at: datetime
    self_instance_id: str | None
    instance_source: Literal["override", "discovery", "none"]

    def for_instance(self, instance_id: str) -> InstanceCapacity | None:
        for inst in self.instances:
            if inst.instance_id == instance_id:
                return inst
        return None


EMPTY_SNAPSHOT = CapacitySnapshot(
    instances=(),
    collected_at=datetime.fromtimestamp(0, tz=timezone.utc),
    self_instance_id=None,
    instance_source="none",
)


@dataclass(frozen=True)
class Signal:
    """One metric that is currently at-or-above its threshold. Rendered
    verbatim into the 503 rejection body's ``signals`` list (specs/014 D-09,
    §10 Resolutions Q4 — the operator confirmed real numbers are shown)."""

    name: str
    value: float
    threshold: float


@dataclass(frozen=True)
class AdmissionState:
    """The gate's hysteresis state. Both the OUTPUT of one
    ``evaluate_admission`` call and the ``prev`` INPUT to the next — this is
    what makes the anti-flicker behaviour (D-05) work across ticks without any
    mutable shared object.
    """

    engaged: bool
    engaged_at: datetime | None
    breach_streak: int
    blind: bool
    blind_reason: str | None
    signals: tuple[Signal, ...]
    evaluated_at: datetime

    @property
    def state_label(self) -> GateStateLabel:
        if self.blind:
            return "blind"
        return "blocking" if self.engaged else "allowing"


INITIAL_ADMISSION_STATE = AdmissionState(
    engaged=False,
    engaged_at=None,
    breach_streak=0,
    blind=True,
    blind_reason="no capacity data collected yet",
    signals=(),
    evaluated_at=datetime.fromtimestamp(0, tz=timezone.utc),
)


# ---------------------------------------------------------------------------
# Pure decision logic
# ---------------------------------------------------------------------------


def _select_scope_instances(
    snapshot: CapacitySnapshot, gate_scope: GateScope
) -> tuple[InstanceCapacity, ...]:
    """Which instance(s)' readings decide admission for THIS process.

    ``"self"`` (default, specs/014 D-06): only the instance serving this
    request. An unresolved self-id, or a self-id absent from the snapshot
    (discovery didn't include it, or it has no reading yet), yields an EMPTY
    tuple — which ``evaluate_admission`` treats as fully blind, never as a
    reason to block.
    ``"fleet_worst"``: every instance in the snapshot; the worst value per
    signal wins. Reserved for a future multi-instance fleet (§10 Resolutions
    Q2 — confirmed single-instance today).
    """
    if gate_scope == "fleet_worst":
        return snapshot.instances
    if snapshot.self_instance_id is None:
        return ()
    found = snapshot.for_instance(snapshot.self_instance_id)
    return (found,) if found is not None else ()


def _fresh_metric_worst(
    instances: tuple[InstanceCapacity, ...],
    metric: Literal["cpu_used_percent", "mem_used_percent"],
    now: datetime,
    max_staleness_seconds: float,
) -> float | None:
    """The worst (highest) non-stale value of ``metric`` across ``instances``.
    ``None`` when every instance is missing or stale for this metric — the
    signal is simply unavailable, not zero."""
    values = [
        value
        for inst in instances
        if (value := getattr(inst, metric)) is not None
        and not inst.is_stale(now, max_staleness_seconds)
    ]
    return max(values) if values else None


def evaluate_admission(
    snapshot: CapacitySnapshot,
    prev: AdmissionState,
    now: datetime,
    *,
    cpu_threshold: float = 75.0,
    mem_threshold: float = 75.0,
    clear_margin: float = 10.0,
    breach_datapoints_required: int = 2,
    min_block_seconds: float = 60.0,
    max_staleness_seconds: float = 300.0,
    gate_scope: GateScope = "self",
) -> AdmissionState:
    """Decide whether new expensive work should be admitted right now.

    Pure function of its arguments — no I/O, no clock read (``now`` is
    supplied), no settings read. This is what makes it hypothesis-testable and
    exercisable without any AWS mocking.

    Fail-open rule (D-03/D-04): if BOTH cpu and memory are unavailable (no
    reading, or older than ``max_staleness_seconds``) for the scoped
    instance(s), the result is ``blind=True`` and ``engaged=False`` —
    unconditionally allow, regardless of the previous engaged state. A
    monitoring gap must never be indistinguishable from "still busy".

    When at least one signal IS available, hysteresis (D-05) governs
    engagement:
      * From allowing, a signal must reach >= its threshold for
        ``breach_datapoints_required`` CONSECUTIVE evaluations to engage.
      * Once engaged, the gate stays engaged as long as any signal is still
        at-or-above (threshold - clear_margin) — the lower "clear" bar — OR
        until at least ``min_block_seconds`` have elapsed since it first
        engaged, whichever is later. This prevents a single spike from
        producing a multi-flip modal.
    """
    scoped = _select_scope_instances(snapshot, gate_scope)
    cpu_value = _fresh_metric_worst(
        scoped, "cpu_used_percent", now, max_staleness_seconds
    )
    mem_value = _fresh_metric_worst(
        scoped, "mem_used_percent", now, max_staleness_seconds
    )

    if cpu_value is None and mem_value is None:
        reason = (
            "no capacity reading for the selected instance(s)"
            if not scoped
            else "cpu and memory readings are both missing or stale"
        )
        return AdmissionState(
            engaged=False,
            engaged_at=None,
            breach_streak=0,
            blind=True,
            blind_reason=reason,
            signals=(),
            evaluated_at=now,
        )

    hot_signals: list[Signal] = []
    for name, value, threshold in (
        (_SIGNAL_CPU, cpu_value, cpu_threshold),
        (_SIGNAL_MEM, mem_value, mem_threshold),
    ):
        if value is None:
            continue
        # While engaged, the lower "clear" bar keeps the signal hot until the
        # reading genuinely drops below it — that is the hysteresis band.
        effective_threshold = threshold - clear_margin if prev.engaged else threshold
        if value >= effective_threshold:
            hot_signals.append(Signal(name=name, value=value, threshold=threshold))

    is_hot = bool(hot_signals)
    breach_streak = prev.breach_streak + 1 if is_hot else 0

    if not prev.engaged:
        newly_engaged = breach_streak >= breach_datapoints_required
        engaged = newly_engaged
        engaged_at = now if newly_engaged else None
    else:
        held_long_enough = (
            prev.engaged_at is not None
            and (now - prev.engaged_at).total_seconds() >= min_block_seconds
        )
        engaged = is_hot or not held_long_enough
        engaged_at = prev.engaged_at if engaged else None

    return AdmissionState(
        engaged=engaged,
        engaged_at=engaged_at,
        breach_streak=breach_streak,
        blind=False,
        blind_reason=None,
        signals=tuple(hot_signals),
        evaluated_at=now,
    )


def evaluate_admission_from_settings(
    snapshot: CapacitySnapshot, prev: AdmissionState, now: datetime
) -> AdmissionState:
    """Thin settings-reading wrapper over :func:`evaluate_admission`. This is
    the impure edge the poller calls; keep :func:`evaluate_admission` itself
    free of any settings read so it stays trivially unit-testable."""
    return evaluate_admission(
        snapshot,
        prev,
        now,
        cpu_threshold=settings.HOST_CAPACITY_CPU_THRESHOLD_PERCENT,
        mem_threshold=settings.HOST_CAPACITY_MEM_THRESHOLD_PERCENT,
        clear_margin=settings.HOST_CAPACITY_CLEAR_MARGIN_PERCENT,
        breach_datapoints_required=settings.HOST_CAPACITY_BREACH_DATAPOINTS,
        min_block_seconds=settings.HOST_CAPACITY_MIN_BLOCK_SECONDS,
        max_staleness_seconds=settings.HOST_CAPACITY_MAX_STALENESS_SECONDS,
        gate_scope=settings.HOST_CAPACITY_GATE_SCOPE,  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------------
# Process-wide state holder — one writer (the poller), many readers.
# ---------------------------------------------------------------------------

_snapshot_holder: dict[str, CapacitySnapshot] = {"value": EMPTY_SNAPSHOT}
_decision_holder: dict[str, AdmissionState] = {"value": INITIAL_ADMISSION_STATE}


def publish_snapshot(snapshot: CapacitySnapshot) -> None:
    """Publish a freshly collected snapshot. Single dict-key assignment —
    atomic under the GIL, no lock needed for concurrent readers."""
    _snapshot_holder["value"] = snapshot


def current_snapshot() -> CapacitySnapshot:
    """The most recently published snapshot. Never ``None`` — before the
    first successful poll this is :data:`EMPTY_SNAPSHOT`, which the admin
    matrix renders as "no data yet" rather than crashing on."""
    return _snapshot_holder["value"]


def publish_decision(decision: AdmissionState) -> None:
    """Publish a freshly evaluated admission decision."""
    _decision_holder["value"] = decision


def current_decision() -> AdmissionState:
    """The most recently published admission decision. Never ``None`` —
    before the first poll this is :data:`INITIAL_ADMISSION_STATE`, which is
    blind (and therefore allows) rather than blocking on missing data."""
    return _decision_holder["value"]


def advance(snapshot: CapacitySnapshot, now: datetime) -> AdmissionState:
    """One poll tick: evaluate the new snapshot against the currently
    published decision, then publish BOTH the snapshot and the new decision.
    This is the only place ``prev`` (hysteresis continuity) and the settings
    read (:func:`evaluate_admission_from_settings`) come together — called
    exclusively from the background poller (``main.py``'s lifespan), never
    from a request handler.
    """
    prev = current_decision()
    decision = evaluate_admission_from_settings(snapshot, prev, now)
    publish_snapshot(snapshot)
    publish_decision(decision)
    return decision


def should_block_new_work(*, is_admin: bool) -> AdmissionState | None:
    """The gate's caller-facing decision helper (specs/014 D-01/D-02/D-03).

    Returns the current :class:`AdmissionState` when the caller should be
    refused, or ``None`` when the operation may proceed. Centralises the
    three no-op conditions so every call site (``run_commands.py``,
    ``handoff.py``) applies them identically rather than re-deriving them:

      * the gate is disabled (``HOST_CAPACITY_GATE_ENABLED`` — checked by the
        caller via ``settings`` before even calling this, since that flag is
        a pure settings read with no state-holder involvement; see the two
        call sites for the exact order),
      * ``is_admin`` — D-02, an admin is never refused,
      * the decision is currently blind — D-03, fail open on missing data.

    Deliberately takes ``is_admin`` as a plain bool rather than a ``User``
    object, so this module keeps zero dependency on ``app.models.user``.
    """
    if is_admin:
        return None
    decision = current_decision()
    if decision.blind or not decision.engaged:
        return None
    return decision


def reset_state_for_tests() -> None:
    """Test-only: restore both holders to their initial values. Never called
    by app code."""
    publish_snapshot(EMPTY_SNAPSHOT)
    publish_decision(INITIAL_ADMISSION_STATE)
