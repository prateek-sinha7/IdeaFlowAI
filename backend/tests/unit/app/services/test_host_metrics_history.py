"""Unit tests for app/services/host_metrics_history.py (ADR-0056).

Every AWS interaction is faked at the module's own ``_client(service)`` seam —
the same approach ``tests/unit/app/test_host_metrics_adapter.py`` uses for the
poller adapter (``moto`` is not a dependency of this repo).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import get_args
from unittest.mock import MagicMock, patch

import pytest

from app.core.config import settings
from app.services import host_metrics_history as hmh

UTC = timezone.utc
START = datetime(2026, 10, 21, 10, 0, tzinfo=UTC)


def _window(points: int = 5, period: int = 60) -> hmh.HistoryWindow:
    """A fixed 1-minute window of ``points`` buckets starting at START."""
    return hmh.HistoryWindow(
        range_key="1h",
        period_seconds=period,
        start=START,
        end=START + timedelta(seconds=points * period),
    )


def _at(minute: int) -> datetime:
    return START + timedelta(minutes=minute)


def _query_id(key: str) -> str:
    """The query id ``build_queries`` assigns a non-EBS metric."""
    index = next(i for i, m in enumerate(hmh.HISTORY_METRICS) if m.key == key)
    return f"q{index}"


def _series(history: hmh.InstanceHistory, key: str) -> hmh.MetricSeries:
    return next(s for s in history.series if s.metric.key == key)


def _ec2_with_volumes(*volume_ids: str) -> MagicMock:
    ec2 = MagicMock()
    paginator = MagicMock()
    paginator.paginate.return_value = [
        {"Volumes": [{"VolumeId": volume_id} for volume_id in volume_ids]}
    ]
    ec2.get_paginator.return_value = paginator
    return ec2


def _clients(cloudwatch: MagicMock, ec2: MagicMock | None = None):
    """``_client`` side effect routing each service to its fake."""
    ec2 = ec2 or _ec2_with_volumes()

    def _route(service: str):
        return cloudwatch if service == "cloudwatch" else ec2

    return _route


@pytest.fixture(autouse=True)
def _clean_caches():
    """Each test starts with empty volume and history caches."""
    hmh.reset_volume_cache()
    hmh.reset_history_cache()
    yield
    hmh.reset_volume_cache()
    hmh.reset_history_cache()


# ---------------------------------------------------------------------------
# allowed_periods / resolve_window
# ---------------------------------------------------------------------------


class TestAllowedPeriods:
    def test_allowed_periods_offers_hourly_only_when_range_exceeds_15_days(self):
        assert hmh.allowed_periods("30d") == (3600,)
        assert hmh.allowed_periods("90d") == (3600,)

    def test_allowed_periods_offers_one_minute_detail_when_range_is_15_days(self):
        assert hmh.allowed_periods("15d") == (60, 300, 900, 3600)

    def test_allowed_periods_drops_periods_under_three_points_when_range_is_1h(self):
        assert hmh.allowed_periods("1h") == (60, 300, 900)

    def test_allowed_periods_raises_window_error_when_range_unknown(self):
        with pytest.raises(hmh.HistoryWindowError):
            hmh.allowed_periods("2y")

    def test_range_catalogue_matches_history_range_literal_when_compared(self):
        assert set(hmh.RANGE_SECONDS) == set(get_args(hmh.HistoryRange))
        assert set(hmh.DEFAULT_PERIOD) == set(hmh.RANGE_SECONDS)

    @pytest.mark.parametrize("range_key", sorted(hmh.RANGE_SECONDS))
    def test_default_period_is_allowed_when_range_is_supported(self, range_key):
        assert hmh.DEFAULT_PERIOD[range_key] in hmh.allowed_periods(range_key)


class TestResolveWindow:
    def test_resolve_window_floors_end_to_period_when_now_is_mid_period(self):
        now = datetime(2026, 10, 21, 10, 7, 42, tzinfo=UTC)
        window = hmh.resolve_window("3h", 300, now)
        assert window.end == datetime(2026, 10, 21, 10, 5, tzinfo=UTC)
        assert window.start == window.end - timedelta(hours=3)
        assert window.point_count == 36

    def test_resolve_window_uses_range_default_when_period_omitted(self):
        now = datetime(2026, 10, 21, 10, 0, tzinfo=UTC)
        window = hmh.resolve_window("1w", None, now)
        assert window.period_seconds == hmh.DEFAULT_PERIOD["1w"]
        assert window.range_key == "1w"

    def test_resolve_window_allows_one_minute_detail_when_range_is_15_days(self):
        now = datetime(2026, 10, 21, 10, 0, tzinfo=UTC)
        window = hmh.resolve_window("15d", 60, now)
        assert window.point_count == hmh.MAX_POINTS_PER_SERIES

    def test_resolve_window_raises_window_error_when_period_not_offered_for_range(self):
        now = datetime(2026, 10, 21, 10, 0, tzinfo=UTC)
        with pytest.raises(hmh.HistoryWindowError, match="not available"):
            hmh.resolve_window("30d", 60, now)

    def test_resolve_window_raises_window_error_when_period_is_arbitrary(self):
        now = datetime(2026, 10, 21, 10, 0, tzinfo=UTC)
        with pytest.raises(hmh.HistoryWindowError):
            hmh.resolve_window("3h", 61, now)


# ---------------------------------------------------------------------------
# build_queries
# ---------------------------------------------------------------------------


class TestBuildQueries:
    def test_build_queries_targets_agent_namespace_with_instance_dimension_when_metric_is_agent(
        self, monkeypatch
    ):
        monkeypatch.setattr(
            settings, "HOST_CAPACITY_METRIC_NAMESPACE", "VelocityAI/Test"
        )
        queries, _ = hmh.build_queries("i-abc", _window(), ())
        cpu = next(q for q in queries if q["Id"] == _query_id("cpu_used"))
        metric = cpu["MetricStat"]["Metric"]
        assert metric["Namespace"] == "VelocityAI/Test"
        assert metric["MetricName"] == "cpu_usage_idle"
        assert metric["Dimensions"] == [{"Name": "InstanceId", "Value": "i-abc"}]
        assert cpu["MetricStat"]["Period"] == 60

    def test_build_queries_adds_path_dimension_when_metric_is_disk_used(self):
        queries, _ = hmh.build_queries("i-abc", _window(), ())
        data = next(q for q in queries if q["Id"] == _query_id("disk_data_used"))
        assert data["MetricStat"]["Metric"]["Dimensions"] == [
            {"Name": "InstanceId", "Value": "i-abc"},
            {"Name": "path", "Value": "/var/lib/postgresql"},
        ]

    def test_build_queries_uses_aws_ec2_sum_when_metric_is_network(self):
        queries, _ = hmh.build_queries("i-abc", _window(), ())
        net_in = next(q for q in queries if q["Id"] == _query_id("net_in"))
        assert net_in["MetricStat"]["Metric"]["Namespace"] == "AWS/EC2"
        assert net_in["MetricStat"]["Stat"] == "Sum"

    def test_build_queries_emits_one_query_per_volume_when_metric_is_ebs(self):
        queries, feeds = hmh.build_queries("i-abc", _window(), ("vol-1", "vol-2"))
        assert len(feeds["disk_read"]) == 2
        read_queries = [q for q in queries if q["Id"] in feeds["disk_read"]]
        assert [q["MetricStat"]["Metric"]["Dimensions"] for q in read_queries] == [
            [{"Name": "VolumeId", "Value": "vol-1"}],
            [{"Name": "VolumeId", "Value": "vol-2"}],
        ]
        assert all(
            q["MetricStat"]["Metric"]["Namespace"] == "AWS/EBS" for q in read_queries
        )

    def test_build_queries_feeds_nothing_to_ebs_metrics_when_instance_has_no_volumes(
        self,
    ):
        queries, feeds = hmh.build_queries("i-abc", _window(), ())
        assert feeds["disk_read"] == []
        assert feeds["disk_write"] == []
        assert len(queries) == len(hmh.HISTORY_METRICS) - 2

    def test_build_queries_uses_unique_ids_when_volumes_present(self):
        queries, _ = hmh.build_queries("i-abc", _window(), ("vol-1", "vol-2"))
        ids = [q["Id"] for q in queries]
        assert len(ids) == len(set(ids))


# ---------------------------------------------------------------------------
# Pure shaping helpers
# ---------------------------------------------------------------------------


class TestShapingHelpers:
    def test_to_grid_places_values_in_period_buckets_when_timestamps_unordered(self):
        raw = hmh._RawSeries(timestamps=[_at(3), _at(0)], values=[30.0, 10.0])
        assert hmh.to_grid(raw, _window()) == [10.0, None, None, 30.0, None]

    def test_to_grid_drops_datapoints_when_outside_window(self):
        raw = hmh._RawSeries(
            timestamps=[_at(-1), _at(5), _at(1)], values=[1.0, 2.0, 3.0]
        )
        assert hmh.to_grid(raw, _window()) == [None, 3.0, None, None, None]

    def test_sum_grids_ignores_gaps_when_some_grids_have_data(self):
        combined = hmh.sum_grids([[1.0, None, None], [2.0, 5.0, None]], 3)
        assert combined == [3.0, 5.0, None]

    def test_sum_grids_returns_all_gaps_when_no_grids(self):
        assert hmh.sum_grids([], 3) == [None, None, None]

    def test_summarize_reports_latest_min_avg_max_when_values_present(self):
        summary = hmh.summarize([None, 10.0, 30.0, None, 20.0], 2)
        assert summary == hmh.SeriesSummary(latest=20.0, min=10.0, avg=20.0, max=30.0)

    def test_summarize_returns_empty_summary_when_no_values_present(self):
        assert hmh.summarize([None, None], 2) == hmh.SeriesSummary()


# ---------------------------------------------------------------------------
# fetch_instance_history
# ---------------------------------------------------------------------------


class TestFetchInstanceHistory:
    def test_fetch_instance_history_inverts_idle_into_cpu_used_when_datapoints_present(
        self,
    ):
        cloudwatch = MagicMock()
        cloudwatch.get_metric_data.return_value = {
            "MetricDataResults": [
                {
                    "Id": _query_id("cpu_used"),
                    "Timestamps": [_at(0), _at(1)],
                    "Values": [70.0, 25.0],
                },
                {
                    "Id": _query_id("mem_used"),
                    "Timestamps": [_at(1)],
                    "Values": [41.234],
                },
            ]
        }
        with patch.object(hmh, "_client", side_effect=_clients(cloudwatch)):
            history = hmh.fetch_instance_history("i-abc", _window())

        cpu = _series(history, "cpu_used")
        assert cpu.values == (30.0, 75.0, None, None, None)
        assert cpu.summary == hmh.SeriesSummary(
            latest=75.0, min=30.0, avg=52.5, max=75.0
        )
        assert _series(history, "mem_used").values[1] == 41.23
        assert not history.has_errors

    def test_fetch_instance_history_reports_bytes_per_second_when_metric_is_network(
        self,
    ):
        cloudwatch = MagicMock()
        cloudwatch.get_metric_data.return_value = {
            "MetricDataResults": [
                {"Id": _query_id("net_in"), "Timestamps": [_at(0)], "Values": [6000.0]},
            ]
        }
        with patch.object(hmh, "_client", side_effect=_clients(cloudwatch)):
            history = hmh.fetch_instance_history("i-abc", _window())
        assert _series(history, "net_in").values[0] == pytest.approx(100.0)

    def test_fetch_instance_history_sums_attached_volumes_when_metric_is_ebs(self):
        _, feeds = hmh.build_queries("i-abc", _window(), ("vol-1", "vol-2"))
        first, second = feeds["disk_read"]
        cloudwatch = MagicMock()
        cloudwatch.get_metric_data.return_value = {
            "MetricDataResults": [
                {
                    "Id": first,
                    "Timestamps": [_at(0), _at(1)],
                    "Values": [600.0, 1200.0],
                },
                {"Id": second, "Timestamps": [_at(0)], "Values": [1800.0]},
            ]
        }
        ec2 = _ec2_with_volumes("vol-1", "vol-2")
        with patch.object(hmh, "_client", side_effect=_clients(cloudwatch, ec2)):
            history = hmh.fetch_instance_history("i-abc", _window())
        assert _series(history, "disk_read").values[:3] == (40.0, 20.0, None)
        filters = ec2.get_paginator.return_value.paginate.call_args.kwargs["Filters"]
        assert filters == [{"Name": "attachment.instance-id", "Values": ["i-abc"]}]

    def test_fetch_instance_history_merges_pages_when_next_token_returned(self):
        query_id = _query_id("mem_used")
        cloudwatch = MagicMock()
        cloudwatch.get_metric_data.side_effect = [
            {
                "MetricDataResults": [
                    {
                        "Id": query_id,
                        "Timestamps": [_at(0)],
                        "Values": [10.0],
                        "StatusCode": "PartialData",
                    }
                ],
                "NextToken": "page-2",
            },
            {
                "MetricDataResults": [
                    {
                        "Id": query_id,
                        "Timestamps": [_at(4)],
                        "Values": [50.0],
                        "StatusCode": "Complete",
                    }
                ]
            },
        ]
        with patch.object(hmh, "_client", side_effect=_clients(cloudwatch)):
            history = hmh.fetch_instance_history("i-abc", _window())

        assert _series(history, "mem_used").values == (10.0, None, None, None, 50.0)
        assert cloudwatch.get_metric_data.call_count == 2
        assert (
            cloudwatch.get_metric_data.call_args_list[1].kwargs["NextToken"] == "page-2"
        )

    def test_fetch_instance_history_stops_paging_when_page_cap_reached(
        self, monkeypatch
    ):
        monkeypatch.setattr(hmh, "MAX_PAGES", 2)
        cloudwatch = MagicMock()
        cloudwatch.get_metric_data.return_value = {
            "MetricDataResults": [],
            "NextToken": "again",
        }
        with patch.object(hmh, "_client", side_effect=_clients(cloudwatch)):
            history = hmh.fetch_instance_history("i-abc", _window())
        assert cloudwatch.get_metric_data.call_count == 2
        assert not history.has_errors

    def test_fetch_instance_history_fails_every_series_without_raising_when_get_metric_data_errors(
        self, caplog
    ):
        cloudwatch = MagicMock()
        cloudwatch.get_metric_data.side_effect = RuntimeError(
            "AccessDenied arn:aws:iam::123456789012:role/x"
        )
        with patch.object(hmh, "_client", side_effect=_clients(cloudwatch)):
            with caplog.at_level("WARNING", logger="app.services.host_metrics_history"):
                history = hmh.fetch_instance_history("i-abc", _window())

        assert len(history.series) == len(hmh.HISTORY_METRICS)
        assert all(s.error == hmh.QUERY_FAILED_MESSAGE for s in history.series)
        assert all(s.values == (None,) * 5 for s in history.series)
        # The AWS detail is logged server-side, never carried to the client.
        assert all("123456789012" not in (s.error or "") for s in history.series)
        assert any("GetMetricData failed" in r.getMessage() for r in caplog.records)

    def test_fetch_instance_history_fails_only_disk_io_when_describe_volumes_errors(
        self,
    ):
        cloudwatch = MagicMock()
        cloudwatch.get_metric_data.return_value = {"MetricDataResults": []}
        ec2 = MagicMock()
        ec2.get_paginator.side_effect = RuntimeError("UnauthorizedOperation")
        with patch.object(hmh, "_client", side_effect=_clients(cloudwatch, ec2)):
            history = hmh.fetch_instance_history("i-abc", _window())

        errored = {s.metric.key for s in history.series if s.error}
        assert errored == {"disk_read", "disk_write"}
        assert _series(history, "disk_read").error == hmh.VOLUMES_FAILED_MESSAGE

    def test_fetch_instance_history_fails_one_series_when_its_status_code_is_forbidden(
        self,
    ):
        cloudwatch = MagicMock()
        cloudwatch.get_metric_data.return_value = {
            "MetricDataResults": [
                {
                    "Id": _query_id("swap_used"),
                    "Timestamps": [],
                    "Values": [],
                    "StatusCode": "Forbidden",
                },
                {
                    "Id": _query_id("mem_used"),
                    "Timestamps": [_at(0)],
                    "Values": [5.0],
                    "StatusCode": "Complete",
                },
            ]
        }
        with patch.object(hmh, "_client", side_effect=_clients(cloudwatch)):
            history = hmh.fetch_instance_history("i-abc", _window())
        assert _series(history, "swap_used").error == hmh.QUERY_FAILED_MESSAGE
        assert _series(history, "mem_used").error is None

    def test_fetch_instance_history_returns_empty_series_when_cloudwatch_has_no_data(
        self,
    ):
        cloudwatch = MagicMock()
        cloudwatch.get_metric_data.return_value = {"MetricDataResults": []}
        with patch.object(hmh, "_client", side_effect=_clients(cloudwatch)):
            history = hmh.fetch_instance_history("i-abc", _window())
        assert not history.has_errors
        assert all(s.summary == hmh.SeriesSummary() for s in history.series)

    def test_fetch_instance_history_queries_aligned_window_when_called(self):
        cloudwatch = MagicMock()
        cloudwatch.get_metric_data.return_value = {"MetricDataResults": []}
        window = _window()
        with patch.object(hmh, "_client", side_effect=_clients(cloudwatch)):
            hmh.fetch_instance_history("i-abc", window)
        kwargs = cloudwatch.get_metric_data.call_args.kwargs
        assert kwargs["StartTime"] == window.start
        assert kwargs["EndTime"] == window.end
        assert kwargs["ScanBy"] == "TimestampAscending"


class TestAttachedVolumeIds:
    def test_attached_volume_ids_reuses_cache_when_called_twice_within_ttl(
        self, monkeypatch
    ):
        monkeypatch.setattr(settings, "HOST_CAPACITY_INVENTORY_TTL_SECONDS", 300)
        ec2 = _ec2_with_volumes("vol-1")
        with patch.object(hmh, "_client", return_value=ec2):
            assert hmh.attached_volume_ids("i-abc") == ("vol-1",)
            assert hmh.attached_volume_ids("i-abc") == ("vol-1",)
        assert ec2.get_paginator.return_value.paginate.call_count == 1


# ---------------------------------------------------------------------------
# get_instance_history — result cache
# ---------------------------------------------------------------------------


class TestGetInstanceHistory:
    def test_get_instance_history_serves_cached_result_when_called_again_within_ttl(
        self, monkeypatch
    ):
        monkeypatch.setattr(settings, "HOST_CAPACITY_HISTORY_CACHE_SECONDS", 60)
        cloudwatch = MagicMock()
        cloudwatch.get_metric_data.return_value = {"MetricDataResults": []}
        with patch.object(hmh, "_client", side_effect=_clients(cloudwatch)):
            first, first_cached = hmh.get_instance_history("i-abc", _window())
            second, second_cached = hmh.get_instance_history("i-abc", _window())

        assert (first_cached, second_cached) == (False, True)
        assert second is first
        assert cloudwatch.get_metric_data.call_count == 1

    def test_get_instance_history_refetches_when_cache_ttl_is_zero(self, monkeypatch):
        monkeypatch.setattr(settings, "HOST_CAPACITY_HISTORY_CACHE_SECONDS", 0)
        cloudwatch = MagicMock()
        cloudwatch.get_metric_data.return_value = {"MetricDataResults": []}
        with patch.object(hmh, "_client", side_effect=_clients(cloudwatch)):
            hmh.get_instance_history("i-abc", _window())
            _, cached = hmh.get_instance_history("i-abc", _window())
        assert cached is False
        assert cloudwatch.get_metric_data.call_count == 2

    def test_get_instance_history_does_not_cache_result_when_any_series_failed(
        self, monkeypatch
    ):
        monkeypatch.setattr(settings, "HOST_CAPACITY_HISTORY_CACHE_SECONDS", 60)
        cloudwatch = MagicMock()
        cloudwatch.get_metric_data.side_effect = [
            RuntimeError("throttled"),
            {"MetricDataResults": []},
        ]
        with patch.object(hmh, "_client", side_effect=_clients(cloudwatch)):
            failed, _ = hmh.get_instance_history("i-abc", _window())
            recovered, cached = hmh.get_instance_history("i-abc", _window())
        assert failed.has_errors
        assert cached is False
        assert not recovered.has_errors

    def test_get_instance_history_keys_cache_by_period_when_same_range_requested(
        self, monkeypatch
    ):
        monkeypatch.setattr(settings, "HOST_CAPACITY_HISTORY_CACHE_SECONDS", 60)
        cloudwatch = MagicMock()
        cloudwatch.get_metric_data.return_value = {"MetricDataResults": []}
        with patch.object(hmh, "_client", side_effect=_clients(cloudwatch)):
            hmh.get_instance_history("i-abc", _window(period=60))
            _, cached = hmh.get_instance_history("i-abc", _window(period=300))
        assert cached is False

    def test_get_instance_history_evicts_least_recently_used_when_cache_is_full(
        self, monkeypatch
    ):
        monkeypatch.setattr(settings, "HOST_CAPACITY_HISTORY_CACHE_SECONDS", 60)
        monkeypatch.setattr(settings, "HOST_CAPACITY_HISTORY_CACHE_MAX_ENTRIES", 1)
        cloudwatch = MagicMock()
        cloudwatch.get_metric_data.return_value = {"MetricDataResults": []}
        with patch.object(hmh, "_client", side_effect=_clients(cloudwatch)):
            hmh.get_instance_history("i-a", _window())
            hmh.get_instance_history("i-b", _window())
            _, cached = hmh.get_instance_history("i-a", _window())
        assert cached is False
        assert cloudwatch.get_metric_data.call_count == 3
