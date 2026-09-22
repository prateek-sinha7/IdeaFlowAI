"""Tests for app/services/host_metrics.py — the boto3 CloudWatch/EC2 adapter
(specs/014). No ``moto`` is available in this repo (confirmed absent from
both requirements files), so every AWS interaction is mocked at the module's
own ``_client(service)`` seam via ``unittest.mock.patch.object`` — the exact
pattern ``test_cognito_refresh_secret_hash.py`` uses for ``cognito._client``.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.core.config import settings
from app.services import host_metrics as hm

UTC = timezone.utc


@pytest.fixture(autouse=True)
def _clean_caches():
    """Every test starts from a cold client/inventory/self-id cache so
    patched clients from one test never leak into the next."""
    hm.reset_client_cache()
    hm.reset_inventory_cache()
    hm._SELF_ID_CACHE["value"] = None
    hm._SELF_ID_CACHE["resolved"] = "0"
    yield
    hm.reset_client_cache()
    hm.reset_inventory_cache()
    hm._SELF_ID_CACHE["value"] = None
    hm._SELF_ID_CACHE["resolved"] = "0"


@pytest.fixture
def _override_instance_ids(monkeypatch):
    """Bypass discovery entirely by setting the override, so tests that only
    care about metric collection don't also depend on EC2 mocking."""
    monkeypatch.setattr(settings, "HOST_CAPACITY_INSTANCE_IDS", "i-abc123")
    yield
    monkeypatch.setattr(settings, "HOST_CAPACITY_INSTANCE_IDS", "")


# ---------------------------------------------------------------------------
# resolve_instance_ids — override precedence + tag discovery (D-07)
# ---------------------------------------------------------------------------


class TestResolveInstanceIds:
    def test_override_takes_precedence_and_skips_discovery(self, monkeypatch):
        monkeypatch.setattr(
            settings, "HOST_CAPACITY_INSTANCE_IDS", "i-aaa, i-bbb ,i-ccc"
        )
        with patch.object(hm, "_client") as fake_client_factory:
            ids, from_override = hm.resolve_instance_ids()
        assert ids == ["i-aaa", "i-bbb", "i-ccc"]
        assert from_override is True
        fake_client_factory.assert_not_called()

    def test_empty_override_falls_through_to_discovery(self, monkeypatch):
        monkeypatch.setattr(settings, "HOST_CAPACITY_INSTANCE_IDS", "")
        fake_ec2 = MagicMock()
        fake_paginator = MagicMock()
        fake_paginator.paginate.return_value = [
            {
                "Reservations": [
                    {"Instances": [{"InstanceId": "i-discovered-1"}]},
                    {"Instances": [{"InstanceId": "i-discovered-2"}]},
                ]
            }
        ]
        fake_ec2.get_paginator.return_value = fake_paginator

        with patch.object(hm, "_client", return_value=fake_ec2):
            ids, from_override = hm.resolve_instance_ids()

        assert ids == ["i-discovered-1", "i-discovered-2"]
        assert from_override is False
        filters = fake_paginator.paginate.call_args.kwargs["Filters"]
        assert {"Name": "tag:Project", "Values": ["velocityai"]} in filters
        assert {"Name": "instance-state-name", "Values": ["running"]} in filters

    def test_discovery_failure_degrades_to_empty_list_not_raise(self, monkeypatch):
        monkeypatch.setattr(settings, "HOST_CAPACITY_INSTANCE_IDS", "")
        fake_ec2 = MagicMock()
        fake_ec2.get_paginator.side_effect = RuntimeError("network unreachable")
        with patch.object(hm, "_client", return_value=fake_ec2):
            ids, from_override = hm.resolve_instance_ids()
        assert ids == []
        assert from_override is False

    def test_discovery_empty_result_yields_empty_list(self, monkeypatch):
        monkeypatch.setattr(settings, "HOST_CAPACITY_INSTANCE_IDS", "")
        fake_ec2 = MagicMock()
        fake_paginator = MagicMock()
        fake_paginator.paginate.return_value = [{"Reservations": []}]
        fake_ec2.get_paginator.return_value = fake_paginator
        with patch.object(hm, "_client", return_value=fake_ec2):
            ids, _ = hm.resolve_instance_ids()
        assert ids == []


class TestCrossCheckDiscoveryAgainstOverride:
    def test_noop_when_no_override_set(self, monkeypatch, caplog):
        monkeypatch.setattr(settings, "HOST_CAPACITY_INSTANCE_IDS", "")
        with patch.object(hm, "_client") as fake_client_factory:
            hm.cross_check_discovery_against_override()
        fake_client_factory.assert_not_called()

    def test_warns_when_override_disagrees_with_discovery(self, monkeypatch, caplog):
        monkeypatch.setattr(settings, "HOST_CAPACITY_INSTANCE_IDS", "i-configured")
        fake_ec2 = MagicMock()
        fake_paginator = MagicMock()
        fake_paginator.paginate.return_value = [
            {"Reservations": [{"Instances": [{"InstanceId": "i-actually-discovered"}]}]}
        ]
        fake_ec2.get_paginator.return_value = fake_paginator
        with patch.object(hm, "_client", return_value=fake_ec2):
            with caplog.at_level("WARNING", logger="app.services.host_metrics"):
                hm.cross_check_discovery_against_override()
        assert any("disagrees" in rec.message for rec in caplog.records)

    def test_no_warning_when_override_matches_discovery(self, monkeypatch, caplog):
        monkeypatch.setattr(settings, "HOST_CAPACITY_INSTANCE_IDS", "i-match")
        fake_ec2 = MagicMock()
        fake_paginator = MagicMock()
        fake_paginator.paginate.return_value = [
            {"Reservations": [{"Instances": [{"InstanceId": "i-match"}]}]}
        ]
        fake_ec2.get_paginator.return_value = fake_paginator
        with patch.object(hm, "_client", return_value=fake_ec2):
            with caplog.at_level("WARNING", logger="app.services.host_metrics"):
                hm.cross_check_discovery_against_override()
        assert not any("disagrees" in rec.message for rec in caplog.records)

    def test_cross_check_never_raises_on_aws_failure(self, monkeypatch):
        monkeypatch.setattr(settings, "HOST_CAPACITY_INSTANCE_IDS", "i-configured")
        fake_ec2 = MagicMock()
        fake_ec2.get_paginator.side_effect = RuntimeError("boom")
        with patch.object(hm, "_client", return_value=fake_ec2):
            hm.cross_check_discovery_against_override()  # must not raise


# ---------------------------------------------------------------------------
# collect_readings — GetMetricData shaping + failure handling
# ---------------------------------------------------------------------------


class TestCollectReadings:
    def test_empty_instance_list_short_circuits(self):
        assert hm.collect_readings([]) == []

    def test_cpu_derived_as_100_minus_idle(self):
        fake_cw = MagicMock()
        now = datetime.now(UTC)
        fake_cw.get_metric_data.return_value = {
            "MetricDataResults": [
                {"Id": "m0_idle", "Values": [30.0], "Timestamps": [now]},
                {"Id": "m0_mem", "Values": [55.0], "Timestamps": [now]},
            ]
        }
        with patch.object(hm, "_client", return_value=fake_cw):
            readings = hm.collect_readings(["i-abc"])
        assert len(readings) == 1
        assert readings[0].cpu_used_percent == pytest.approx(70.0)
        assert readings[0].mem_used_percent == pytest.approx(55.0)

    def test_uses_namespace_and_instance_id_dimension(self, monkeypatch):
        monkeypatch.setattr(
            settings, "HOST_CAPACITY_METRIC_NAMESPACE", "VelocityAI/Test"
        )
        fake_cw = MagicMock()
        fake_cw.get_metric_data.return_value = {"MetricDataResults": []}
        with patch.object(hm, "_client", return_value=fake_cw):
            hm.collect_readings(["i-abc"])
        queries = fake_cw.get_metric_data.call_args.kwargs["MetricDataQueries"]
        idle_query = next(q for q in queries if q["Id"] == "m0_idle")
        assert idle_query["MetricStat"]["Metric"]["Namespace"] == "VelocityAI/Test"
        assert idle_query["MetricStat"]["Metric"]["Dimensions"] == [
            {"Name": "InstanceId", "Value": "i-abc"}
        ]

    def test_missing_series_yields_none_not_zero(self):
        fake_cw = MagicMock()
        fake_cw.get_metric_data.return_value = {"MetricDataResults": []}
        with patch.object(hm, "_client", return_value=fake_cw):
            readings = hm.collect_readings(["i-abc"])
        assert readings[0].cpu_used_percent is None
        assert readings[0].mem_used_percent is None
        assert readings[0].timestamp is None

    def test_multiple_instances_each_get_their_own_reading(self):
        fake_cw = MagicMock()
        now = datetime.now(UTC)
        fake_cw.get_metric_data.return_value = {
            "MetricDataResults": [
                {"Id": "m0_idle", "Values": [10.0], "Timestamps": [now]},
                {"Id": "m1_idle", "Values": [90.0], "Timestamps": [now]},
            ]
        }
        with patch.object(hm, "_client", return_value=fake_cw):
            readings = hm.collect_readings(["i-a", "i-b"])
        by_id = {r.instance_id: r for r in readings}
        assert by_id["i-a"].cpu_used_percent == pytest.approx(90.0)
        assert by_id["i-b"].cpu_used_percent == pytest.approx(10.0)

    def test_latest_value_picked_when_multiple_datapoints_returned(self):
        fake_cw = MagicMock()
        old = datetime.now(UTC) - timedelta(minutes=5)
        new = datetime.now(UTC)
        fake_cw.get_metric_data.return_value = {
            "MetricDataResults": [
                {
                    "Id": "m0_idle",
                    "Values": [50.0, 20.0],
                    "Timestamps": [old, new],
                },
            ]
        }
        with patch.object(hm, "_client", return_value=fake_cw):
            readings = hm.collect_readings(["i-abc"])
        # idle=20 at the LATEST timestamp -> cpu_used = 80, not 50 (old).
        assert readings[0].cpu_used_percent == pytest.approx(80.0)
        assert readings[0].timestamp == new

    def test_pagination_is_followed(self):
        fake_cw = MagicMock()
        now = datetime.now(UTC)
        fake_cw.get_metric_data.side_effect = [
            {
                "MetricDataResults": [
                    {"Id": "m0_idle", "Values": [40.0], "Timestamps": [now]}
                ],
                "NextToken": "page2",
            },
            {
                "MetricDataResults": [
                    {"Id": "m0_mem", "Values": [60.0], "Timestamps": [now]}
                ]
            },
        ]
        with patch.object(hm, "_client", return_value=fake_cw):
            readings = hm.collect_readings(["i-abc"])
        assert readings[0].cpu_used_percent == pytest.approx(60.0)
        assert readings[0].mem_used_percent == pytest.approx(60.0)
        assert fake_cw.get_metric_data.call_count == 2
        second_call_kwargs = fake_cw.get_metric_data.call_args_list[1].kwargs
        assert second_call_kwargs["NextToken"] == "page2"

    @pytest.mark.parametrize(
        "exc",
        [
            RuntimeError("throttled"),
            ConnectionError("endpoint unreachable"),
        ],
    )
    def test_client_error_degrades_to_all_unknown_readings(self, exc):
        fake_cw = MagicMock()
        fake_cw.get_metric_data.side_effect = exc
        with patch.object(hm, "_client", return_value=fake_cw):
            readings = hm.collect_readings(["i-abc", "i-def"])
        assert len(readings) == 2
        assert all(r.cpu_used_percent is None for r in readings)
        assert all(r.mem_used_percent is None for r in readings)

    def test_botocore_client_error_degrades_gracefully(self):
        from botocore.exceptions import ClientError

        fake_cw = MagicMock()
        fake_cw.get_metric_data.side_effect = ClientError(
            error_response={"Error": {"Code": "AccessDenied", "Message": "denied"}},
            operation_name="GetMetricData",
        )
        with patch.object(hm, "_client", return_value=fake_cw):
            readings = hm.collect_readings(["i-abc"])
        assert readings[0].cpu_used_percent is None

    def test_no_credentials_error_degrades_gracefully(self):
        from botocore.exceptions import NoCredentialsError

        fake_cw = MagicMock()
        fake_cw.get_metric_data.side_effect = NoCredentialsError()
        with patch.object(hm, "_client", return_value=fake_cw):
            readings = hm.collect_readings(["i-abc"])
        assert readings[0].cpu_used_percent is None

    def test_endpoint_connection_error_degrades_gracefully(self):
        from botocore.exceptions import EndpointConnectionError

        fake_cw = MagicMock()
        fake_cw.get_metric_data.side_effect = EndpointConnectionError(
            endpoint_url="https://monitoring.eu-central-1.amazonaws.com"
        )
        with patch.object(hm, "_client", return_value=fake_cw):
            readings = hm.collect_readings(["i-abc"])
        assert readings[0].cpu_used_percent is None


# ---------------------------------------------------------------------------
# resolve_self_instance_id — IMDSv2, cached, never raises
# ---------------------------------------------------------------------------


class TestResolveSelfInstanceId:
    def test_returns_none_and_caches_on_imds_failure(self):
        with patch("urllib.request.urlopen", side_effect=OSError("no route")):
            first = hm.resolve_self_instance_id()
            second = hm.resolve_self_instance_id()
        assert first is None
        assert second is None

    def test_successful_imdsv2_round_trip(self):
        token_resp = MagicMock()
        token_resp.read.return_value = b"tok3n"
        token_resp.__enter__ = lambda self: token_resp
        token_resp.__exit__ = lambda self, *a: None

        id_resp = MagicMock()
        id_resp.read.return_value = b"i-0123456789abcdef0"
        id_resp.__enter__ = lambda self: id_resp
        id_resp.__exit__ = lambda self, *a: None

        with patch("urllib.request.urlopen", side_effect=[token_resp, id_resp]):
            result = hm.resolve_self_instance_id()
        assert result == "i-0123456789abcdef0"

    def test_cached_after_first_call_regardless_of_outcome(self):
        with patch(
            "urllib.request.urlopen", side_effect=OSError("no route")
        ) as fake_urlopen:
            hm.resolve_self_instance_id()
            hm.resolve_self_instance_id()
            hm.resolve_self_instance_id()
        # Only the first call's PUT should have attempted urlopen; every
        # subsequent call reads the cache.
        assert fake_urlopen.call_count == 1


# ---------------------------------------------------------------------------
# _client — caching + timeout config
# ---------------------------------------------------------------------------


class TestClientCache:
    def test_client_is_cached_per_service(self):
        with patch("boto3.client") as fake_boto3_client:
            fake_boto3_client.return_value = MagicMock()
            first = hm._client("ec2")
            second = hm._client("ec2")
        assert first is second
        assert fake_boto3_client.call_count == 1

    def test_different_services_get_different_clients(self):
        with patch("boto3.client") as fake_boto3_client:
            fake_boto3_client.side_effect = lambda service, **kw: MagicMock(
                name=service
            )
            ec2 = hm._client("ec2")
            cw = hm._client("cloudwatch")
        assert ec2 is not cw
        assert fake_boto3_client.call_count == 2

    def test_client_passes_tight_timeouts_not_bedrock_timeouts(self):
        with patch("boto3.client") as fake_boto3_client:
            fake_boto3_client.return_value = MagicMock()
            hm._client("cloudwatch")
        _, kwargs = fake_boto3_client.call_args
        config = kwargs["config"]
        assert config.connect_timeout == settings.HOST_CAPACITY_AWS_CONNECT_TIMEOUT
        assert config.read_timeout == settings.HOST_CAPACITY_AWS_READ_TIMEOUT
        # Not the Bedrock config=Config(read_timeout=600, connect_timeout=30).
        assert config.read_timeout != 600
        assert config.connect_timeout != 30

    def test_no_explicit_credentials_ever_passed(self):
        with patch("boto3.client") as fake_boto3_client:
            fake_boto3_client.return_value = MagicMock()
            hm._client("ec2")
        _, kwargs = fake_boto3_client.call_args
        assert "aws_access_key_id" not in kwargs
        assert "aws_secret_access_key" not in kwargs
        assert "aws_session_token" not in kwargs


# ---------------------------------------------------------------------------
# collect_snapshot — the poller's single entry point
# ---------------------------------------------------------------------------


class TestCollectSnapshot:
    def test_never_raises_when_everything_fails(self, monkeypatch):
        monkeypatch.setattr(settings, "HOST_CAPACITY_INSTANCE_IDS", "")
        with patch.object(hm, "_client", side_effect=RuntimeError("aws is down")):
            with patch("urllib.request.urlopen", side_effect=OSError("no imds")):
                snapshot = hm.collect_snapshot()
        assert snapshot.instances == ()
        assert snapshot.self_instance_id is None
        assert snapshot.instance_source == "none"

    def test_assembles_a_populated_snapshot(self, _override_instance_ids):
        fake_cw = MagicMock()
        now = datetime.now(UTC)
        fake_cw.get_metric_data.return_value = {
            "MetricDataResults": [
                {"Id": "m0_idle", "Values": [25.0], "Timestamps": [now]},
                {"Id": "m0_mem", "Values": [60.0], "Timestamps": [now]},
            ]
        }
        with patch.object(hm, "_client", return_value=fake_cw):
            with patch("urllib.request.urlopen", side_effect=OSError("no imds")):
                snapshot = hm.collect_snapshot()
        assert len(snapshot.instances) == 1
        assert snapshot.instances[0].instance_id == "i-abc123"
        assert snapshot.instances[0].cpu_used_percent == pytest.approx(75.0)
        assert snapshot.instance_source == "override"

    def test_inventory_cache_avoids_repeated_describe_instances(self, monkeypatch):
        monkeypatch.setattr(settings, "HOST_CAPACITY_INSTANCE_IDS", "")
        monkeypatch.setattr(settings, "HOST_CAPACITY_INVENTORY_TTL_SECONDS", 300)
        fake_ec2 = MagicMock()
        fake_paginator = MagicMock()
        fake_paginator.paginate.return_value = [
            {"Reservations": [{"Instances": [{"InstanceId": "i-cached"}]}]}
        ]
        fake_ec2.get_paginator.return_value = fake_paginator
        fake_cw = MagicMock()
        fake_cw.get_metric_data.return_value = {"MetricDataResults": []}

        def _client_router(service: str):
            return fake_ec2 if service == "ec2" else fake_cw

        with patch.object(hm, "_client", side_effect=_client_router):
            with patch("urllib.request.urlopen", side_effect=OSError("no imds")):
                hm.collect_snapshot()
                hm.collect_snapshot()

        # DescribeInstances (via the paginator) should only be called ONCE —
        # the second collect_snapshot() call must hit the inventory cache.
        assert fake_paginator.paginate.call_count == 1
