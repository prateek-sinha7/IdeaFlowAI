"""app/services/host_metrics.py — the CloudWatch/EC2 adapter for specs/014.

Single source of truth for reading host CPU/memory utilisation from AWS. Auth
comes from the boto3 default credential chain (instance profile in prod,
``AWS_PROFILE``/SSO locally) — exactly the model ``app/core/cognito.py`` and
``app/agents/model_factory.py`` already use; no new credentials anywhere.

Metrics come from the CloudWatch Agent already deployed by
``infra/scripts/reconcile-host-config.sh`` — it publishes ``cpu_usage_idle``
and ``mem_used_percent`` (plus others) to namespace ``VelocityAI/<Env>`` every
60 seconds, dimensioned by ``InstanceId``. CPU-used % is derived as
``100 - cpu_usage_idle`` rather than reading ``cpu_usage_user`` (the metric the
existing CloudWatch alarms use) because ``cpu_usage_user`` excludes system and
I/O-wait time and would silently under-report a host busy on those.

This module NEVER raises to its caller. Every AWS/network failure mode
(missing credentials, throttling, IAM denial, endpoint unreachable, empty
result set) degrades to an ``unknown`` reading rather than propagating an
exception — the caller (``capacity_state``) treats unknown as "fail open"
(specs/014 D-03). This module also never touches the request path: it is only
ever invoked from the background poller in ``main.py``'s lifespan.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Literal

from app.core.config import settings

if TYPE_CHECKING:
    from app.services.capacity_state import CapacitySnapshot

logger = logging.getLogger("app.services.host_metrics")

# ---------------------------------------------------------------------------
# boto3 client cache — double-checked lock, mirroring
# agents/capabilities/hooks/otel_tracing.py's _get_tracer() pattern. boto3 is
# imported lazily (function-local, never at module scope) so importing this
# module never requires AWS credentials to be configured, and so the CI
# offline-sandbox guard (tools/ci/offline_guards.py's BLOCKED_PROVIDER_MODULES)
# never sees a module-level `import boto3`.
# ---------------------------------------------------------------------------

_CLIENT_LOCK = threading.Lock()
_CLIENTS: dict[str, Any] = {}


def _client(service: str) -> Any:
    """Return a cached boto3 client for ``service`` ("ec2" or "cloudwatch").

    Tight timeouts (``HOST_CAPACITY_AWS_{CONNECT,READ}_TIMEOUT`` — deliberately
    NOT the Bedrock ``read_timeout=600`` config): a metrics call must fail
    fast, never wedge the background poller. No explicit credentials are ever
    passed — the default credential chain resolves them.
    """
    cached = _CLIENTS.get(service)
    if cached is not None:
        return cached
    with _CLIENT_LOCK:
        cached = _CLIENTS.get(service)
        if cached is None:
            import boto3
            from botocore.config import Config

            cached = boto3.client(
                service,
                region_name=settings.AWS_REGION,
                config=Config(
                    connect_timeout=settings.HOST_CAPACITY_AWS_CONNECT_TIMEOUT,
                    read_timeout=settings.HOST_CAPACITY_AWS_READ_TIMEOUT,
                    retries={"max_attempts": 3, "mode": "standard"},
                ),
            )
            _CLIENTS[service] = cached
    return cached


def reset_client_cache() -> None:
    """Test-only: drop cached clients so a test's ``patch.object(_client, ...)``
    or a fresh region/timeout setting takes effect. Never called by app code."""
    with _CLIENT_LOCK:
        _CLIENTS.clear()


# ---------------------------------------------------------------------------
# Instance discovery (specs/014 D-06 / D-07)
# ---------------------------------------------------------------------------

_SELF_ID_LOCK = threading.Lock()
_SELF_ID_CACHE: dict[str, str | None] = {"value": None, "resolved": "0"}


def resolve_instance_ids() -> tuple[list[str], bool]:
    """Return ``(instance_ids, from_override)``.

    Precedence (D-07): ``HOST_CAPACITY_INSTANCE_IDS`` first (comma-separated
    allow-list — configuration, not code, since Terraform replaces the
    instance on any AMI/user-data change and a literal id in source would go
    stale silently). Otherwise discover via ``ec2:DescribeInstances`` filtered
    on ``tag:Project=velocityai``, ``tag:Environment=<settings.ENV>``, and
    ``instance-state-name=running``. Never raises — an AWS failure here
    resolves to an empty list, which the caller treats as blind (D-03).
    """
    override = settings.HOST_CAPACITY_INSTANCE_IDS.strip()
    if override:
        ids = [i.strip() for i in override.split(",") if i.strip()]
        if ids:
            return ids, True

    try:
        ec2 = _client("ec2")
        ids: list[str] = []
        paginator = ec2.get_paginator("describe_instances")
        page_iterator = paginator.paginate(
            Filters=[
                {"Name": "tag:Project", "Values": ["velocityai"]},
                {"Name": "tag:Environment", "Values": [settings.ENV]},
                {"Name": "instance-state-name", "Values": ["running"]},
            ]
        )
        for page in page_iterator:
            for reservation in page.get("Reservations", []):
                for instance in reservation.get("Instances", []):
                    instance_id = instance.get("InstanceId")
                    if instance_id:
                        ids.append(instance_id)
        return ids, False
    except Exception as exc:  # noqa: BLE001 — never raise from discovery
        logger.warning("host_metrics: instance discovery failed: %s", exc)
        return [], False


def cross_check_discovery_against_override() -> None:
    """Log a one-time WARNING if tag discovery disagrees with the configured
    override (specs/014 D-07's "cross-check" — makes the operator-supplied
    HOST_CAPACITY_INSTANCE_IDS meaningfully verified rather than an unverified
    value sitting next to the real one). No-op when no override is set.
    Never raises.
    """
    override = settings.HOST_CAPACITY_INSTANCE_IDS.strip()
    if not override:
        return
    configured = {i.strip() for i in override.split(",") if i.strip()}
    if not configured:
        return
    try:
        ec2 = _client("ec2")
        discovered: set[str] = set()
        paginator = ec2.get_paginator("describe_instances")
        for page in paginator.paginate(
            Filters=[
                {"Name": "tag:Project", "Values": ["velocityai"]},
                {"Name": "tag:Environment", "Values": [settings.ENV]},
                {"Name": "instance-state-name", "Values": ["running"]},
            ]
        ):
            for reservation in page.get("Reservations", []):
                for instance in reservation.get("Instances", []):
                    instance_id = instance.get("InstanceId")
                    if instance_id:
                        discovered.add(instance_id)
        if discovered and discovered != configured:
            logger.warning(
                "host_metrics: HOST_CAPACITY_INSTANCE_IDS (%s) disagrees with "
                "tag-based discovery (%s) — verify the override is still correct.",
                sorted(configured),
                sorted(discovered),
            )
    except Exception as exc:  # noqa: BLE001 — cross-check must never raise
        logger.warning("host_metrics: discovery cross-check failed: %s", exc)


def resolve_self_instance_id() -> str | None:
    """Resolve this process's own EC2 instance id via IMDSv2, cached for the
    process lifetime. Returns ``None`` (never raises) when not running on EC2,
    on any IMDS error, or on timeout — the caller treats ``None`` as unknown
    ⇒ fail open (D-03). 1-second timeout so a non-EC2 host (local dev) does
    not stall startup.
    """
    with _SELF_ID_LOCK:
        if _SELF_ID_CACHE["resolved"] == "1":
            return _SELF_ID_CACHE["value"]

        value: str | None = None
        try:
            import urllib.request

            token_req = urllib.request.Request(
                "http://169.254.169.254/latest/api/token",
                method="PUT",
                headers={"X-aws-ec2-metadata-token-ttl-seconds": "21600"},
            )
            # nosec B310 — the URL is a hardcoded literal (the well-known AWS
            # IMDS link-local address), never user input, so the "unexpected
            # scheme" concern the blacklist rule guards against does not apply.
            with urllib.request.urlopen(token_req, timeout=1) as resp:  # nosec B310
                token = resp.read().decode("utf-8").strip()

            id_req = urllib.request.Request(
                "http://169.254.169.254/latest/meta-data/instance-id",
                headers={"X-aws-ec2-metadata-token": token},
            )
            # nosec B310 — same rationale as above: a hardcoded IMDS literal URL.
            with urllib.request.urlopen(id_req, timeout=1) as resp:  # nosec B310
                value = resp.read().decode("utf-8").strip() or None
        except Exception as exc:  # noqa: BLE001 — never raise; not on EC2 is normal
            logger.info(
                "host_metrics: could not resolve self instance id via IMDSv2 "
                "(expected off-EC2, e.g. local dev): %s",
                exc,
            )
            value = None

        _SELF_ID_CACHE["value"] = value
        _SELF_ID_CACHE["resolved"] = "1"
        return value


# ---------------------------------------------------------------------------
# Metric collection
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RawInstanceReading:
    """One instance's raw metric read, before decision logic is applied.

    ``cpu_used_percent`` / ``mem_used_percent`` are ``None`` when CloudWatch
    returned no datapoint for that series (e.g. a freshly launched instance,
    or the CloudWatch Agent degraded — see ``reconcile-host-config.sh``'s
    ``degrade_agent``). ``timestamp`` is the datapoint's own CloudWatch
    timestamp (UTC), used by ``capacity_state`` to bound staleness (D-04) —
    never wall-clock-at-collection-time, which would hide a frozen series.
    """

    instance_id: str
    instance_type: str | None
    cpu_used_percent: float | None
    mem_used_percent: float | None
    cpu_user_percent: float | None
    cpu_system_percent: float | None
    cpu_iowait_percent: float | None
    timestamp: datetime | None


def collect_readings(instance_ids: list[str]) -> list[RawInstanceReading]:
    """Fetch the latest CPU/memory datapoint for each instance via one
    ``GetMetricData`` call. Never raises — any AWS failure yields an
    all-``None`` reading per requested instance id so the caller can render
    the row as unknown rather than dropping it silently.
    """
    if not instance_ids:
        return []

    namespace = settings.HOST_CAPACITY_METRIC_NAMESPACE
    now = datetime.now(timezone.utc)
    # Look back 10 minutes: the agent publishes every 60s and CloudWatch adds
    # its own lag for custom metrics (specs/014 D-04) — 10 minutes is generous
    # headroom to catch the latest real datapoint without over-fetching.
    start = now - timedelta(minutes=10)

    queries: list[dict[str, Any]] = []
    for idx, instance_id in enumerate(instance_ids):
        dims = [{"Name": "InstanceId", "Value": instance_id}]
        for metric_key, series in (
            ("idle", "cpu_usage_idle"),
            ("mem", "mem_used_percent"),
            ("user", "cpu_usage_user"),
            ("sys", "cpu_usage_system"),
            ("iowait", "cpu_usage_iowait"),
        ):
            queries.append(
                {
                    "Id": f"m{idx}_{metric_key}",
                    "MetricStat": {
                        "Metric": {
                            "Namespace": namespace,
                            "MetricName": series,
                            "Dimensions": dims,
                        },
                        "Period": 60,
                        "Stat": "Average",
                    },
                    "ReturnData": True,
                }
            )

    results_by_id: dict[str, dict[str, Any]] = {}

    try:
        cw = _client("cloudwatch")
        next_token: str | None = None
        while True:
            kwargs: dict[str, Any] = {
                "MetricDataQueries": queries,
                "StartTime": start,
                "EndTime": now,
                "ScanBy": "TimestampDescending",
            }
            if next_token:
                kwargs["NextToken"] = next_token
            response = cw.get_metric_data(**kwargs)
            for series_result in response.get("MetricDataResults", []):
                results_by_id[series_result["Id"]] = series_result
            next_token = response.get("NextToken")
            if not next_token:
                break
    except Exception as exc:  # noqa: BLE001 — degrade to unknown, never raise
        logger.warning("host_metrics: GetMetricData failed: %s", exc)
        results_by_id = {}

    readings: list[RawInstanceReading] = []
    for idx, instance_id in enumerate(instance_ids):
        idle = _latest_value(results_by_id.get(f"m{idx}_idle"))
        mem = _latest_value(results_by_id.get(f"m{idx}_mem"))
        user = _latest_value(results_by_id.get(f"m{idx}_user"))
        sys_ = _latest_value(results_by_id.get(f"m{idx}_sys"))
        iowait = _latest_value(results_by_id.get(f"m{idx}_iowait"))

        cpu_used = None if idle is None else max(0.0, min(100.0, 100.0 - idle))
        timestamp = _latest_timestamp(results_by_id.get(f"m{idx}_idle")) or (
            _latest_timestamp(results_by_id.get(f"m{idx}_mem"))
        )

        readings.append(
            RawInstanceReading(
                instance_id=instance_id,
                instance_type=None,
                cpu_used_percent=cpu_used,
                mem_used_percent=mem,
                cpu_user_percent=user,
                cpu_system_percent=sys_,
                cpu_iowait_percent=iowait,
                timestamp=timestamp,
            )
        )
    return readings


def _latest_value(series_result: dict[str, Any] | None) -> float | None:
    """Extract the most recent value from a GetMetricData series result.

    ``Values``/``Timestamps`` are parallel lists; with ``ScanBy=TimestampDescending``
    index 0 is already the latest, but this re-sorts defensively rather than
    trusting an API-ordering assumption to hold forever.
    """
    if not series_result:
        return None
    values = series_result.get("Values") or []
    timestamps = series_result.get("Timestamps") or []
    if not values or not timestamps or len(values) != len(timestamps):
        return None
    paired = sorted(
        zip(timestamps, values, strict=True), key=lambda pair: pair[0], reverse=True
    )
    return float(paired[0][1])


def _latest_timestamp(series_result: dict[str, Any] | None) -> datetime | None:
    """Extract the most recent timestamp from a GetMetricData series result."""
    if not series_result:
        return None
    timestamps = series_result.get("Timestamps") or []
    if not timestamps:
        return None
    return max(timestamps)


# ---------------------------------------------------------------------------
# Inventory cache (D-07 — DescribeInstances is the more expensive call and the
# instance list changes rarely, so it is cached far longer than the metric poll)
# ---------------------------------------------------------------------------

_INVENTORY_LOCK = threading.Lock()
_INVENTORY_CACHE: dict[str, Any] = {"ids": None, "source": "none", "fetched_at": None}


def _cached_instance_ids() -> (
    tuple[list[str], Literal["override", "discovery", "none"]]
):
    """``resolve_instance_ids()`` behind a TTL cache
    (``HOST_CAPACITY_INVENTORY_TTL_SECONDS``). Never raises."""
    with _INVENTORY_LOCK:
        fetched_at = _INVENTORY_CACHE["fetched_at"]
        if fetched_at is not None:
            age = (datetime.now(timezone.utc) - fetched_at).total_seconds()
            if age < settings.HOST_CAPACITY_INVENTORY_TTL_SECONDS:
                return list(_INVENTORY_CACHE["ids"] or []), _INVENTORY_CACHE["source"]

        ids, from_override = resolve_instance_ids()
        _INVENTORY_CACHE["ids"] = ids
        _INVENTORY_CACHE["source"] = (
            "override" if from_override else ("discovery" if ids else "none")
        )
        _INVENTORY_CACHE["fetched_at"] = datetime.now(timezone.utc)
        return ids, _INVENTORY_CACHE["source"]


def reset_inventory_cache() -> None:
    """Test-only: force the next :func:`collect_snapshot` to re-resolve
    instance ids rather than reusing a cached list. Never called by app code."""
    with _INVENTORY_LOCK:
        _INVENTORY_CACHE["ids"] = None
        _INVENTORY_CACHE["source"] = "none"
        _INVENTORY_CACHE["fetched_at"] = None


def collect_snapshot() -> "CapacitySnapshot":
    """The single entry point the background poller calls each tick.

    Resolves the (cached) instance inventory, resolves this process's own
    instance id, fetches fresh CPU/memory readings for every instance, and
    assembles a :class:`app.services.capacity_state.CapacitySnapshot`. Never
    raises — every sub-step already degrades to an empty/None result on
    failure, so the worst case is an all-unknown snapshot, not an exception
    reaching the poller's ``asyncio.to_thread`` call.
    """
    from app.services.capacity_state import (
        CapacitySnapshot,
        instance_capacity_from_raw,
    )

    instance_ids, source = _cached_instance_ids()
    self_instance_id = resolve_self_instance_id()

    if settings.HOST_CAPACITY_INSTANCE_IDS.strip():
        cross_check_discovery_against_override()

    readings = collect_readings(instance_ids)
    instances = tuple(instance_capacity_from_raw(r) for r in readings)

    return CapacitySnapshot(
        instances=instances,
        collected_at=datetime.now(timezone.utc),
        self_instance_id=self_instance_id,
        instance_source=source,
    )
