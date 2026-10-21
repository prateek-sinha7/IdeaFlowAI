"""Unit tests for GET /api/admin/capacity/history (ADR-0056).

Bare ``FastAPI()`` around the router with ``require_admin`` overridden — the same
pattern as ``tests/unit/api/test_admin_capacity_api.py``. The CloudWatch read is
replaced at the router's ``get_instance_history`` seam, so these tests cover the
HTTP contract (auth, validation, allow-list, response shape) only; the adapter
has its own tests in ``tests/unit/app/services/test_host_metrics_history.py``.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from fastapi import FastAPI, HTTPException, status
from fastapi.testclient import TestClient

from app.api import admin_capacity_history as route
from app.api.admin import require_admin
from app.services import capacity_state as cs
from app.services import host_metrics_history as hmh

UTC = timezone.utc


class _FakeAdmin:
    id = "admin-1"
    is_admin = True


@pytest.fixture
def api():
    """TestClient over the history router; ``state["admin"]`` flips the guard."""
    app = FastAPI()
    app.include_router(route.router)
    state = {"admin": True}

    def override_require_admin():
        if not state["admin"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required."
            )
        return _FakeAdmin()

    app.dependency_overrides[require_admin] = override_require_admin
    yield TestClient(app), state
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _reset_capacity_state():
    """Each test starts before the first poll (empty snapshot)."""
    cs.reset_state_for_tests()
    yield
    cs.reset_state_for_tests()


def _publish_instances(*instance_ids: str) -> None:
    now = datetime.now(UTC)
    instances = tuple(
        cs.InstanceCapacity(
            instance_id=instance_id,
            instance_type="m6i.xlarge",
            cpu_used_percent=10.0,
            mem_used_percent=20.0,
            cpu_user_percent=None,
            cpu_system_percent=None,
            cpu_iowait_percent=None,
            timestamp=now,
        )
        for instance_id in instance_ids
    )
    snapshot = cs.CapacitySnapshot(
        instances=instances,
        collected_at=now,
        self_instance_id=instance_ids[0] if instance_ids else None,
        instance_source="override",
    )
    cs.advance(snapshot, now)


def _history(instance_id: str, window: hmh.HistoryWindow) -> hmh.InstanceHistory:
    metric = hmh.HISTORY_METRICS[0]
    values = tuple([12.5] + [None] * (window.point_count - 1))
    series = (
        hmh.MetricSeries(metric, values, hmh.summarize(values, 2)),
        hmh.MetricSeries(
            hmh.HISTORY_METRICS[-1],
            (None,) * window.point_count,
            hmh.SeriesSummary(),
            hmh.QUERY_FAILED_MESSAGE,
        ),
    )
    return hmh.InstanceHistory(
        instance_id=instance_id,
        window=window,
        series=series,
        fetched_at=window.end + timedelta(seconds=5),
    )


class TestAuthorization:
    def test_get_capacity_history_returns_403_when_caller_is_not_admin(self, api):
        client, state = api
        state["admin"] = False
        _publish_instances("i-real")
        resp = client.get(
            "/api/admin/capacity/history", params={"instance_id": "i-real"}
        )
        assert resp.status_code == 403, resp.text

    def test_get_capacity_history_returns_403_before_validation_when_caller_is_not_admin(
        self, api
    ):
        client, state = api
        state["admin"] = False
        resp = client.get(
            "/api/admin/capacity/history", params={"instance_id": "i-x", "range": "2y"}
        )
        assert resp.status_code == 403, resp.text


class TestValidation:
    @pytest.mark.parametrize(
        "params",
        [
            {"instance_id": "i-real", "range": "2y"},
            {"instance_id": "i-real", "range": "30d", "period": "60"},
            {"instance_id": "i-real", "range": "3h", "period": "61"},
            {"instance_id": "i-real", "range": "3h", "period": "fast"},
            {"instance_id": ""},
            {"instance_id": "i-" + "a" * 80},
            {},
        ],
    )
    def test_get_capacity_history_returns_422_when_query_is_invalid(self, api, params):
        client, _ = api
        _publish_instances("i-real")
        with patch.object(route, "get_instance_history") as fetch:
            resp = client.get("/api/admin/capacity/history", params=params)
        assert resp.status_code == 422, resp.text
        fetch.assert_not_called()


class TestInstanceAllowList:
    def test_get_capacity_history_returns_404_without_aws_call_when_instance_unknown(
        self, api
    ):
        client, _ = api
        _publish_instances("i-real")
        with patch.object(route, "get_instance_history") as fetch:
            resp = client.get(
                "/api/admin/capacity/history", params={"instance_id": "i-attacker"}
            )
        assert resp.status_code == 404, resp.text
        fetch.assert_not_called()

    def test_get_capacity_history_returns_404_when_poller_has_not_run(self, api):
        client, _ = api
        with patch.object(route, "get_instance_history") as fetch:
            resp = client.get(
                "/api/admin/capacity/history", params={"instance_id": "i-real"}
            )
        assert resp.status_code == 404, resp.text
        fetch.assert_not_called()


class TestHistoryResponse:
    def test_get_capacity_history_returns_series_and_window_when_instance_known(
        self, api
    ):
        client, _ = api
        _publish_instances("i-real", "i-other")
        with patch.object(
            route,
            "get_instance_history",
            side_effect=lambda iid, w: (_history(iid, w), True),
        ) as fetch:
            resp = client.get(
                "/api/admin/capacity/history",
                params={"instance_id": "i-other", "range": "1d", "period": "300"},
            )

        assert resp.status_code == 200, resp.text
        instance_id, window = fetch.call_args.args
        assert instance_id == "i-other"
        assert (window.range_key, window.period_seconds) == ("1d", 300)

        body = resp.json()
        assert body["instance_id"] == "i-other"
        assert body["range"] == "1d"
        assert body["period_seconds"] == 300
        assert body["allowed_periods"] == [60, 300, 900, 3600]
        assert body["cached"] is True
        assert body["cpu_threshold_percent"] == pytest.approx(75.0)
        assert body["mem_threshold_percent"] == pytest.approx(75.0)

        cpu, status_check = body["series"]
        assert cpu["key"] == "cpu_used"
        assert cpu["group"] == "cpu"
        assert cpu["unit"] == "percent"
        assert len(cpu["values"]) == 288
        assert cpu["values"][0] == pytest.approx(12.5)
        assert cpu["values"][1] is None
        assert cpu["summary"] == {"latest": 12.5, "min": 12.5, "avg": 12.5, "max": 12.5}
        assert cpu["error"] is None
        assert status_check["error"] == hmh.QUERY_FAILED_MESSAGE

    def test_get_capacity_history_uses_range_default_period_when_period_omitted(
        self, api
    ):
        client, _ = api
        _publish_instances("i-real")
        with patch.object(
            route,
            "get_instance_history",
            side_effect=lambda iid, w: (_history(iid, w), False),
        ) as fetch:
            resp = client.get(
                "/api/admin/capacity/history", params={"instance_id": "i-real"}
            )
        assert resp.status_code == 200, resp.text
        window = fetch.call_args.args[1]
        assert (window.range_key, window.period_seconds) == ("3h", 60)
        assert resp.json()["cached"] is False

    def test_get_capacity_history_leaves_admission_decision_unchanged_when_called(
        self, api
    ):
        client, _ = api
        _publish_instances("i-real")
        before = cs.current_decision()
        with patch.object(
            route,
            "get_instance_history",
            side_effect=lambda iid, w: (_history(iid, w), False),
        ):
            client.get("/api/admin/capacity/history", params={"instance_id": "i-real"})
        assert cs.current_decision() is before
