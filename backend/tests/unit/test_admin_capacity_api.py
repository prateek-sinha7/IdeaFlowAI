"""Tests for GET /api/admin/capacity (specs/014).

Follows the bare-``FastAPI()`` + ``dependency_overrides`` pattern established
by ``tests/unit/test_runs_api.py`` — no real DB, no auth headers, the
authorization dependency (here: ``require_admin``) is overridden directly.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import FastAPI, HTTPException, status
from fastapi.testclient import TestClient

from app.api.admin import require_admin
from app.api.admin_capacity import router
from app.services import capacity_state as cs

UTC = timezone.utc


class _FakeUser:
    def __init__(self, *, is_admin: bool = True, user_id: str = "admin-1"):
        self.id = user_id
        self.is_admin = is_admin


@pytest.fixture
def api():
    """Bare app around the capacity router. ``state["admin"]`` toggles
    whether ``require_admin`` grants or denies (mirrors how existing tests
    flip ``state["user"]`` to prove IDOR/403 behaviour)."""
    app = FastAPI()
    app.include_router(router)

    state: dict = {"admin": True}

    def override_require_admin():
        if not state["admin"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin access required.",
            )
        return _FakeUser(is_admin=True)

    app.dependency_overrides[require_admin] = override_require_admin
    return TestClient(app), state


@pytest.fixture(autouse=True)
def _reset_capacity_state():
    cs.reset_state_for_tests()
    yield
    cs.reset_state_for_tests()


class TestAuthorization:
    def test_non_admin_is_403(self, api):
        client, state = api
        state["admin"] = False
        resp = client.get("/api/admin/capacity")
        assert resp.status_code == 403, resp.text

    def test_admin_is_200(self, api):
        client, _ = api
        resp = client.get("/api/admin/capacity")
        assert resp.status_code == 200, resp.text


class TestBeforeFirstPoll:
    def test_empty_matrix_is_honest_blind_not_an_error(self, api):
        client, _ = api
        resp = client.get("/api/admin/capacity")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["instances"] == []
        assert body["gate"]["state"] == "blind"
        assert body["gate"]["blind_reason"] is not None


class TestPopulatedMatrix:
    def test_reflects_the_published_snapshot(self, api):
        client, _ = api
        now = datetime.now(UTC)
        inst = cs.InstanceCapacity(
            instance_id="i-real",
            instance_type="t3.large",
            cpu_used_percent=42.5,
            mem_used_percent=61.0,
            cpu_user_percent=30.0,
            cpu_system_percent=10.0,
            cpu_iowait_percent=2.5,
            timestamp=now,
        )
        snapshot = cs.CapacitySnapshot(
            instances=(inst,),
            collected_at=now,
            self_instance_id="i-real",
            instance_source="discovery",
        )
        cs.advance(snapshot, now)

        resp = client.get("/api/admin/capacity")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert len(body["instances"]) == 1
        row = body["instances"][0]
        assert row["instance_id"] == "i-real"
        assert row["is_self"] is True
        assert row["cpu_used_percent"] == pytest.approx(42.5)
        assert row["mem_used_percent"] == pytest.approx(61.0)
        assert row["stale"] is False
        assert row["reading_age_seconds"] is not None

    def test_non_self_instance_flagged_correctly(self, api):
        client, _ = api
        now = datetime.now(UTC)
        self_inst = cs.InstanceCapacity(
            instance_id="i-self",
            instance_type=None,
            cpu_used_percent=10.0,
            mem_used_percent=10.0,
            cpu_user_percent=None,
            cpu_system_percent=None,
            cpu_iowait_percent=None,
            timestamp=now,
        )
        other_inst = cs.InstanceCapacity(
            instance_id="i-other",
            instance_type=None,
            cpu_used_percent=20.0,
            mem_used_percent=20.0,
            cpu_user_percent=None,
            cpu_system_percent=None,
            cpu_iowait_percent=None,
            timestamp=now,
        )
        snapshot = cs.CapacitySnapshot(
            instances=(self_inst, other_inst),
            collected_at=now,
            self_instance_id="i-self",
            instance_source="discovery",
        )
        cs.advance(snapshot, now)

        resp = client.get("/api/admin/capacity")
        rows = {r["instance_id"]: r for r in resp.json()["instances"]}
        assert rows["i-self"]["is_self"] is True
        assert rows["i-other"]["is_self"] is False

    def test_stale_reading_flagged_as_stale(self, api, monkeypatch):
        from app.core.config import settings

        monkeypatch.setattr(settings, "HOST_CAPACITY_MAX_STALENESS_SECONDS", 300)
        client, _ = api
        from datetime import timedelta

        old = datetime.now(UTC) - timedelta(seconds=1000)
        inst = cs.InstanceCapacity(
            instance_id="i-frozen",
            instance_type=None,
            cpu_used_percent=90.0,
            mem_used_percent=90.0,
            cpu_user_percent=None,
            cpu_system_percent=None,
            cpu_iowait_percent=None,
            timestamp=old,
        )
        snapshot = cs.CapacitySnapshot(
            instances=(inst,),
            collected_at=old,
            self_instance_id="i-frozen",
            instance_source="discovery",
        )
        cs.advance(snapshot, old)

        resp = client.get("/api/admin/capacity")
        row = resp.json()["instances"][0]
        assert row["stale"] is True


class TestGateBlockPayload:
    def test_engaged_gate_surfaces_signals_with_real_numbers(self, api, monkeypatch):
        """specs/014 §10 Resolutions Q4 — admin matrix (and the 503 body it
        mirrors) must carry actual measured numbers, not just a boolean."""
        from app.core.config import settings

        monkeypatch.setattr(settings, "HOST_CAPACITY_CPU_THRESHOLD_PERCENT", 75.0)
        monkeypatch.setattr(settings, "HOST_CAPACITY_BREACH_DATAPOINTS", 1)
        client, _ = api
        now = datetime.now(UTC)
        inst = cs.InstanceCapacity(
            instance_id="i-hot",
            instance_type=None,
            cpu_used_percent=91.0,
            mem_used_percent=None,
            cpu_user_percent=None,
            cpu_system_percent=None,
            cpu_iowait_percent=None,
            timestamp=now,
        )
        snapshot = cs.CapacitySnapshot(
            instances=(inst,),
            collected_at=now,
            self_instance_id="i-hot",
            instance_source="discovery",
        )
        cs.advance(snapshot, now)

        resp = client.get("/api/admin/capacity")
        gate = resp.json()["gate"]
        assert gate["state"] == "blocking"
        assert gate["signals"] == [{"name": "cpu", "value": 91.0, "threshold": 75.0}]

    def test_gate_enabled_flag_reflects_settings(self, api, monkeypatch):
        from app.core.config import settings

        monkeypatch.setattr(settings, "HOST_CAPACITY_GATE_ENABLED", True)
        client, _ = api
        resp = client.get("/api/admin/capacity")
        assert resp.json()["gate"]["enabled"] is True
