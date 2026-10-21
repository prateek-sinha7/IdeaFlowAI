"""app/services/host_metrics_history.py — on-demand CloudWatch time series for
the admin Machines-tab history charts (ADR-0056).

specs/014 keeps AWS off the request path so a CloudWatch outage can never reach
the admission gate. History charts need a range query, so this module is the one
documented exception, bounded four ways:

* It is only reached from ``GET /api/admin/capacity/history`` (admin-only), for an
  instance id the background poller already knows about.
* It never reads or writes the admission decision in ``capacity_state`` — the gate
  is computed by the background poller alone, so nothing here can change it.
* It reuses ``host_metrics``' boto3 clients (the same tight botocore timeouts) and
  caps pagination, so a slow CloudWatch costs one admin a slow chart, not a wedged
  worker.
* It never raises: a failed query degrades to a per-series ``error`` and an empty
  chart. Only fully successful results are cached
  (``HOST_CAPACITY_HISTORY_CACHE_SECONDS``), so a failure is retried next refresh.

Metric sources — all listed once, in ``HISTORY_METRICS``:

* CloudWatch Agent namespace (``VelocityAI/<Env>``): CPU, memory, disk used %,
  swap. Queried on the ``[InstanceId]`` and ``[InstanceId, path]`` rollups that
  ``infra/scripts/reconcile-host-config.sh``'s ``aggregation_dimensions`` publishes.
* ``AWS/EC2``: NetworkIn/Out and StatusCheckFailed. Network comes from here, not
  the agent, because the agent's ``net`` plugin collects every interface (loopback,
  Docker bridges and veths), so its ``[InstanceId]`` rollup overstates traffic.
  Bytes/s = Sum / period, which assumes detailed (1-minute) monitoring — the
  ``modules/compute`` default.
* ``AWS/EBS``: VolumeRead/WriteBytes summed over the instance's attached volumes.
  ``AWS/EC2`` DiskReadBytes only covers instance-store volumes (always empty on an
  EBS-only Nitro instance), and the agent's ``diskio`` rollup adds whole disks and
  their partitions together.

CloudWatch retention drives the range/period rules: 1-minute data is kept for 15
days, 5-minute for 63 days and 1-hour for 455 days. Ranges up to 15 days may be
read at 1-minute detail; longer ranges are served hourly only.
"""

from __future__ import annotations

import logging
import threading
from collections import OrderedDict
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from app.core.config import settings
from app.services import host_metrics

logger = logging.getLogger("app.services.host_metrics_history")

# ---------------------------------------------------------------------------
# Ranges and periods
# ---------------------------------------------------------------------------

HistoryRange = Literal["1h", "3h", "12h", "1d", "3d", "1w", "15d", "30d", "90d"]

_HOUR = 3_600
_DAY = 86_400

RANGE_SECONDS: dict[str, int] = {
    "1h": _HOUR,
    "3h": 3 * _HOUR,
    "12h": 12 * _HOUR,
    "1d": _DAY,
    "3d": 3 * _DAY,
    "1w": 7 * _DAY,
    "15d": 15 * _DAY,
    "30d": 30 * _DAY,
    "90d": 90 * _DAY,
}

# Every period is a whole number of minutes, so CloudWatch can serve it from the
# 1-minute (≤15 days), 5-minute or 1-hour retention tiers.
PERIOD_CHOICES: tuple[int, ...] = (60, 300, 900, 3_600)

# Default resolution per range: 1-minute detail up to a day, coarser beyond so a
# default view stays around a few hundred to ~1,500 points per series.
DEFAULT_PERIOD: dict[str, int] = {
    "1h": 60,
    "3h": 60,
    "12h": 60,
    "1d": 60,
    "3d": 300,
    "1w": 900,
    "15d": 3_600,
    "30d": 3_600,
    "90d": 3_600,
}

# CloudWatch keeps 1-minute (and 5-minute) detail for at least this long; a range
# longer than this is only offered hourly.
DETAILED_RETENTION_SECONDS = 15 * _DAY
HOURLY_PERIOD = 3_600
MIN_POINTS_PER_SERIES = 3
# 15 days at 1-minute detail — the most a single series is ever allowed to carry.
MAX_POINTS_PER_SERIES = 21_600
# GetMetricData returns at most 100,800 datapoints per page; 20 pages covers every
# range at every period with headroom for many attached EBS volumes.
MAX_PAGES = 20


class HistoryWindowError(ValueError):
    """The requested range/period combination cannot be served."""


@dataclass(frozen=True)
class HistoryWindow:
    """A period-aligned ``[start, end)`` query window.

    ``end`` is floored to a whole period so every returned bucket is complete
    (a half-filled final bucket would draw a false dip on Sum-based series).
    """

    range_key: str
    period_seconds: int
    start: datetime
    end: datetime

    @property
    def point_count(self) -> int:
        """Number of period buckets in the window."""
        return int((self.end - self.start).total_seconds()) // self.period_seconds


def allowed_periods(range_key: str) -> tuple[int, ...]:
    """Return the periods (seconds) a range may be read at, finest first.

    Ranges longer than :data:`DETAILED_RETENTION_SECONDS` are hourly only. A period
    must yield between :data:`MIN_POINTS_PER_SERIES` and
    :data:`MAX_POINTS_PER_SERIES` buckets.

    Raises:
        HistoryWindowError: ``range_key`` is not a supported range.
    """
    seconds = RANGE_SECONDS.get(range_key)
    if seconds is None:
        raise HistoryWindowError(f"Unsupported range {range_key!r}.")
    candidates = (
        (HOURLY_PERIOD,) if seconds > DETAILED_RETENTION_SECONDS else PERIOD_CHOICES
    )
    return tuple(
        period
        for period in candidates
        if MIN_POINTS_PER_SERIES <= seconds // period <= MAX_POINTS_PER_SERIES
    )


def resolve_window(
    range_key: str, period_seconds: int | None, now: datetime
) -> HistoryWindow:
    """Validate a range/period request and build its aligned window.

    Args:
        range_key: One of :data:`RANGE_SECONDS`.
        period_seconds: Requested resolution, or ``None`` for the range default.
        now: Current time (UTC, timezone-aware); injected for deterministic tests.

    Raises:
        HistoryWindowError: Unknown range, or a period not offered for it.
    """
    allowed = allowed_periods(range_key)
    period = DEFAULT_PERIOD[range_key] if period_seconds is None else period_seconds
    if period not in allowed:
        raise HistoryWindowError(
            f"Period {period}s is not available for range {range_key}; "
            f"choose one of {list(allowed)}."
        )
    epoch = int(now.timestamp())
    end = datetime.fromtimestamp(epoch - epoch % period, tz=timezone.utc)
    start = end - timedelta(seconds=RANGE_SECONDS[range_key])
    return HistoryWindow(
        range_key=range_key, period_seconds=period, start=start, end=end
    )


# ---------------------------------------------------------------------------
# Metric catalogue — the single list the router and charts are driven by
# ---------------------------------------------------------------------------

ChartGroup = Literal[
    "cpu", "memory", "disk_used", "disk_io", "network", "swap", "status"
]
MetricUnit = Literal["percent", "bytes_per_second", "count"]
MetricSource = Literal["agent", "ec2", "ebs"]
Transform = Literal["none", "invert_percent", "per_second"]

ROOT_DISK_PATH = "/"
DATA_DISK_PATH = "/var/lib/postgresql"


@dataclass(frozen=True)
class HistoryMetric:
    """One chartable series and where CloudWatch keeps it.

    ``extra_dimensions`` are added to the ``InstanceId`` dimension for agent and
    EC2 metrics. EBS metrics are queried once per attached volume (``VolumeId``)
    and summed. ``transform`` converts the raw statistic into the charted unit.
    """

    key: str
    label: str
    group: ChartGroup
    unit: MetricUnit
    source: MetricSource
    metric_name: str
    stat: str
    extra_dimensions: tuple[tuple[str, str], ...] = ()
    transform: Transform = "none"


HISTORY_METRICS: tuple[HistoryMetric, ...] = (
    # CPU used % = 100 - idle, matching host_metrics.collect_readings (user alone
    # under-reports a host busy on system or I/O-wait time).
    HistoryMetric(
        "cpu_used",
        "Total",
        "cpu",
        "percent",
        "agent",
        "cpu_usage_idle",
        "Average",
        transform="invert_percent",
    ),
    HistoryMetric(
        "cpu_user", "User", "cpu", "percent", "agent", "cpu_usage_user", "Average"
    ),
    HistoryMetric(
        "cpu_system", "System", "cpu", "percent", "agent", "cpu_usage_system", "Average"
    ),
    HistoryMetric(
        "cpu_iowait",
        "I/O wait",
        "cpu",
        "percent",
        "agent",
        "cpu_usage_iowait",
        "Average",
    ),
    HistoryMetric(
        "mem_used", "Used", "memory", "percent", "agent", "mem_used_percent", "Average"
    ),
    HistoryMetric(
        "disk_root_used",
        ROOT_DISK_PATH,
        "disk_used",
        "percent",
        "agent",
        "disk_used_percent",
        "Average",
        (("path", ROOT_DISK_PATH),),
    ),
    HistoryMetric(
        "disk_data_used",
        DATA_DISK_PATH,
        "disk_used",
        "percent",
        "agent",
        "disk_used_percent",
        "Average",
        (("path", DATA_DISK_PATH),),
    ),
    HistoryMetric(
        "disk_read",
        "Read",
        "disk_io",
        "bytes_per_second",
        "ebs",
        "VolumeReadBytes",
        "Sum",
        transform="per_second",
    ),
    HistoryMetric(
        "disk_write",
        "Write",
        "disk_io",
        "bytes_per_second",
        "ebs",
        "VolumeWriteBytes",
        "Sum",
        transform="per_second",
    ),
    HistoryMetric(
        "net_in",
        "In",
        "network",
        "bytes_per_second",
        "ec2",
        "NetworkIn",
        "Sum",
        transform="per_second",
    ),
    HistoryMetric(
        "net_out",
        "Out",
        "network",
        "bytes_per_second",
        "ec2",
        "NetworkOut",
        "Sum",
        transform="per_second",
    ),
    HistoryMetric(
        "swap_used", "Used", "swap", "percent", "agent", "swap_used_percent", "Average"
    ),
    HistoryMetric(
        "status_check_failed",
        "Failed",
        "status",
        "count",
        "ec2",
        "StatusCheckFailed",
        "Maximum",
    ),
)

_ROUND_DIGITS: dict[str, int] = {"percent": 2, "bytes_per_second": 1, "count": 2}

# Generic, client-safe messages. The underlying exception is logged server-side
# only — botocore messages can carry account ids and ARNs.
QUERY_FAILED_MESSAGE = "CloudWatch query failed."
VOLUMES_FAILED_MESSAGE = "Could not list the instance's EBS volumes."

# GetMetricData per-series status codes that mean "this series has no usable data".
_FAILED_STATUS_CODES = frozenset({"InternalError", "Forbidden"})


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SeriesSummary:
    """Latest / min / avg / max over a series' present values (all ``None`` when
    the series has no datapoints)."""

    latest: float | None = None
    min: float | None = None
    avg: float | None = None
    max: float | None = None


@dataclass(frozen=True)
class MetricSeries:
    """One metric's values on the window grid (``None`` = no datapoint)."""

    metric: HistoryMetric
    values: tuple[float | None, ...]
    summary: SeriesSummary
    error: str | None = None


@dataclass(frozen=True)
class InstanceHistory:
    """Every series in :data:`HISTORY_METRICS` for one instance and window."""

    instance_id: str
    window: HistoryWindow
    series: tuple[MetricSeries, ...]
    fetched_at: datetime

    @property
    def has_errors(self) -> bool:
        """True when any series failed to load (such results are never cached)."""
        return any(s.error is not None for s in self.series)


@dataclass
class _RawSeries:
    """One GetMetricData result id, merged across pages."""

    timestamps: list[datetime] = field(default_factory=list)
    values: list[float] = field(default_factory=list)
    status: str = "Complete"


# ---------------------------------------------------------------------------
# AWS access
# ---------------------------------------------------------------------------


def _client(service: str) -> Any:
    """The shared, tight-timeout boto3 client cache in ``host_metrics``.

    Wrapped so tests patch this module's seam without touching the poller's.
    """
    return host_metrics._client(service)


_VOLUME_LOCK = threading.Lock()
_VOLUME_CACHE: dict[str, tuple[datetime, tuple[str, ...]]] = {}


def attached_volume_ids(instance_id: str) -> tuple[str, ...]:
    """Return the EBS volume ids attached to ``instance_id``.

    Cached per instance for ``HOST_CAPACITY_INVENTORY_TTL_SECONDS`` (volumes change
    as rarely as the instance list). Raises on any AWS error — the caller turns that
    into a disk-I/O series error.
    """
    now = datetime.now(timezone.utc)
    with _VOLUME_LOCK:
        cached = _VOLUME_CACHE.get(instance_id)
        if cached is not None:
            fetched_at, volume_ids = cached
            if (
                now - fetched_at
            ).total_seconds() < settings.HOST_CAPACITY_INVENTORY_TTL_SECONDS:
                return volume_ids

    paginator = _client("ec2").get_paginator("describe_volumes")
    found: list[str] = []
    for page in paginator.paginate(
        Filters=[{"Name": "attachment.instance-id", "Values": [instance_id]}]
    ):
        for volume in page.get("Volumes", []):
            volume_id = volume.get("VolumeId")
            if volume_id:
                found.append(volume_id)

    volume_ids = tuple(found)
    with _VOLUME_LOCK:
        _VOLUME_CACHE[instance_id] = (now, volume_ids)
    return volume_ids


def reset_volume_cache() -> None:
    """Test-only: forget cached volume lists. Never called by app code."""
    with _VOLUME_LOCK:
        _VOLUME_CACHE.clear()


def _namespace(source: MetricSource) -> str:
    if source == "agent":
        return settings.HOST_CAPACITY_METRIC_NAMESPACE
    return "AWS/EBS" if source == "ebs" else "AWS/EC2"


def build_queries(
    instance_id: str, window: HistoryWindow, volume_ids: Sequence[str]
) -> tuple[list[dict[str, Any]], dict[str, list[str]]]:
    """Build the GetMetricData queries for every catalogue metric.

    Returns ``(queries, feeds)`` where ``feeds`` maps each metric key to the query
    ids whose values are summed into it (one per volume for EBS metrics, one
    otherwise; none for an EBS metric on an instance with no volumes).
    """
    queries: list[dict[str, Any]] = []
    feeds: dict[str, list[str]] = {}
    for idx, metric in enumerate(HISTORY_METRICS):
        if metric.source == "ebs":
            targets = [
                (f"q{idx}_v{j}", [{"Name": "VolumeId", "Value": volume_id}])
                for j, volume_id in enumerate(volume_ids)
            ]
        else:
            dims = [{"Name": "InstanceId", "Value": instance_id}]
            dims.extend(
                {"Name": name, "Value": value}
                for name, value in metric.extra_dimensions
            )
            targets = [(f"q{idx}", dims)]

        feeds[metric.key] = [query_id for query_id, _ in targets]
        for query_id, dims in targets:
            queries.append(
                {
                    "Id": query_id,
                    "MetricStat": {
                        "Metric": {
                            "Namespace": _namespace(metric.source),
                            "MetricName": metric.metric_name,
                            "Dimensions": dims,
                        },
                        "Period": window.period_seconds,
                        "Stat": metric.stat,
                    },
                    "ReturnData": True,
                }
            )
    return queries, feeds


def _get_metric_data(
    queries: list[dict[str, Any]], window: HistoryWindow
) -> dict[str, _RawSeries]:
    """Run the queries, following ``NextToken`` up to :data:`MAX_PAGES`.

    Raises on any AWS error — the caller owns the degrade-to-error handling.
    """
    cloudwatch = _client("cloudwatch")
    merged: dict[str, _RawSeries] = {}
    next_token: str | None = None
    for _ in range(MAX_PAGES):
        kwargs: dict[str, Any] = {
            "MetricDataQueries": queries,
            "StartTime": window.start,
            "EndTime": window.end,
            "ScanBy": "TimestampAscending",
        }
        if next_token:
            kwargs["NextToken"] = next_token
        response = cloudwatch.get_metric_data(**kwargs)
        for result in response.get("MetricDataResults", []):
            entry = merged.setdefault(result["Id"], _RawSeries())
            entry.timestamps.extend(result.get("Timestamps") or [])
            entry.values.extend(result.get("Values") or [])
            entry.status = result.get("StatusCode", entry.status)
        next_token = response.get("NextToken")
        if not next_token:
            return merged
    logger.warning(
        "host_metrics_history: GetMetricData still paginating after %d pages; "
        "returning the data read so far",
        MAX_PAGES,
    )
    return merged


# ---------------------------------------------------------------------------
# Shaping
# ---------------------------------------------------------------------------


def to_grid(raw: _RawSeries, window: HistoryWindow) -> list[float | None]:
    """Place datapoints into the window's period buckets (``None`` = no data).

    Datapoints outside the window are dropped; mismatched value/timestamp lists
    (never seen from CloudWatch) are truncated to the shorter one.
    """
    count = window.point_count
    grid: list[float | None] = [None] * count
    start_epoch = window.start.timestamp()
    for timestamp, value in zip(raw.timestamps, raw.values, strict=False):
        index = int((timestamp.timestamp() - start_epoch) // window.period_seconds)
        if 0 <= index < count:
            grid[index] = float(value)
    return grid


def sum_grids(
    grids: Sequence[Sequence[float | None]], count: int
) -> list[float | None]:
    """Bucket-wise sum ignoring gaps; a bucket is ``None`` only when every grid is."""
    if not grids:
        return [None] * count
    combined: list[float | None] = []
    for bucket in zip(*grids, strict=True):
        present = [v for v in bucket if v is not None]
        combined.append(sum(present) if present else None)
    return combined


def _transform(value: float, metric: HistoryMetric, period_seconds: int) -> float:
    if metric.transform == "invert_percent":
        return max(0.0, min(100.0, 100.0 - value))
    if metric.transform == "per_second":
        return value / period_seconds
    return value


def summarize(values: Sequence[float | None], digits: int) -> SeriesSummary:
    """Latest / min / avg / max over the present values, rounded to ``digits``."""
    present = [v for v in values if v is not None]
    if not present:
        return SeriesSummary()
    return SeriesSummary(
        latest=present[-1],
        min=min(present),
        avg=round(sum(present) / len(present), digits),
        max=max(present),
    )


def _assemble_series(
    metric: HistoryMetric,
    query_ids: Sequence[str],
    raw: dict[str, _RawSeries],
    window: HistoryWindow,
    error: str | None,
) -> MetricSeries:
    count = window.point_count
    if error is None and any(
        qid in raw and raw[qid].status in _FAILED_STATUS_CODES for qid in query_ids
    ):
        error = QUERY_FAILED_MESSAGE
    if error is not None:
        return MetricSeries(metric, (None,) * count, SeriesSummary(), error)

    grids = [
        to_grid(raw[qid], window) if qid in raw else [None] * count for qid in query_ids
    ]
    digits = _ROUND_DIGITS[metric.unit]
    values = tuple(
        None
        if v is None
        else round(_transform(v, metric, window.period_seconds), digits)
        for v in sum_grids(grids, count)
    )
    return MetricSeries(metric, values, summarize(values, digits))


def fetch_instance_history(instance_id: str, window: HistoryWindow) -> InstanceHistory:
    """Read every catalogue metric for one instance over ``window``. Never raises.

    A failed volume lookup fails only the disk-I/O series; a failed GetMetricData
    call fails every series. Either way the caller gets a complete, typed result.
    """
    volume_error: str | None = None
    try:
        volume_ids = attached_volume_ids(instance_id)
    except Exception as exc:  # noqa: BLE001 — degrade disk I/O only, never raise
        logger.warning(
            "host_metrics_history: DescribeVolumes failed for %s: %s", instance_id, exc
        )
        volume_ids = ()
        volume_error = VOLUMES_FAILED_MESSAGE

    queries, feeds = build_queries(instance_id, window, volume_ids)
    fetch_error: str | None = None
    try:
        raw = _get_metric_data(queries, window)
    except Exception as exc:  # noqa: BLE001 — degrade every series, never raise
        logger.warning(
            "host_metrics_history: GetMetricData failed for %s: %s", instance_id, exc
        )
        raw = {}
        fetch_error = QUERY_FAILED_MESSAGE

    series = tuple(
        _assemble_series(
            metric,
            feeds[metric.key],
            raw,
            window,
            fetch_error or (volume_error if metric.source == "ebs" else None),
        )
        for metric in HISTORY_METRICS
    )
    return InstanceHistory(
        instance_id=instance_id,
        window=window,
        series=series,
        fetched_at=datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# Result cache
# ---------------------------------------------------------------------------

_HISTORY_LOCK = threading.Lock()
_HISTORY_CACHE: OrderedDict[tuple[str, str, int], InstanceHistory] = OrderedDict()


def get_instance_history(
    instance_id: str, window: HistoryWindow
) -> tuple[InstanceHistory, bool]:
    """Return ``(history, cached)`` for one instance/range/period.

    A cached result younger than ``HOST_CAPACITY_HISTORY_CACHE_SECONDS`` is returned
    as-is (its own, slightly older window). Otherwise CloudWatch is queried; the
    result is cached only when every series loaded. The cache holds at most
    ``HOST_CAPACITY_HISTORY_CACHE_MAX_ENTRIES`` results, evicting the least recently
    used. Never raises.
    """
    key = (instance_id, window.range_key, window.period_seconds)
    now = datetime.now(timezone.utc)
    with _HISTORY_LOCK:
        hit = _HISTORY_CACHE.get(key)
        if hit is not None:
            if (
                now - hit.fetched_at
            ).total_seconds() < settings.HOST_CAPACITY_HISTORY_CACHE_SECONDS:
                _HISTORY_CACHE.move_to_end(key)
                return hit, True
            del _HISTORY_CACHE[key]

    history = fetch_instance_history(instance_id, window)
    if not history.has_errors:
        with _HISTORY_LOCK:
            _HISTORY_CACHE[key] = history
            _HISTORY_CACHE.move_to_end(key)
            while len(_HISTORY_CACHE) > max(
                0, settings.HOST_CAPACITY_HISTORY_CACHE_MAX_ENTRIES
            ):
                _HISTORY_CACHE.popitem(last=False)
    return history, False


def reset_history_cache() -> None:
    """Test-only: drop cached history results. Never called by app code."""
    with _HISTORY_LOCK:
        _HISTORY_CACHE.clear()
