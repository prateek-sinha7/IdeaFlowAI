"""tests/agents/test_audit_endpoints.py — SC-3 audit-tab read endpoints (Phase 32-03).

The Audit tab (plan 09) is repointed off ``hook_runs`` onto the real
governance / validation / exec audit tables. This suite pins the three additive,
READ-ONLY, owner-scoped endpoints on the ``/api/runs`` router:

    GET /api/runs/{id}/gate-events
    GET /api/runs/{id}/validation-results
    GET /api/runs/{id}/exec-runs

Security surface (T-32-03-01 / P13 / P25): each endpoint applies the two-layer
owner gate that ``get_hook_runs`` uses — Layer 1 gates the run by
``WorkflowRun.user_id == current_user.id`` (→ 404 on a cross-owner or missing id;
IDOR resolves to 404, NEVER 403, NEVER a 200 with another owner's rows), and
Layer 2 re-filters the child rows by ``owner_id`` (defense-in-depth). ``exec-runs``
surfaces ONLY the truncated ``output_digest`` column — never a raw child-output
field (T-32-03-02 / ASVS V7).

Harness: the same in-memory-SQLite ``TestClient`` dependency-override pattern as
``tests/unit/test_runs_api_artifacts.py`` — no Postgres / Bedrock. The FastAPI
TestClient drives the ``async def`` handlers on its own loop, so the test bodies
are plain sync functions.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.runs import router
from app.core.dependencies import get_current_user
from app.models.database import Base, get_db
from app.models.exec_runs import ExecRun
from app.models.gate_events import GateEvent
from app.models.validation_results import ValidationResult
from app.models.workflow import WorkflowRun


class _FakeUser:
    """Stand-in for ``app.models.user.User`` — only ``id`` is read by the API."""

    def __init__(self, id: str):
        self.id = id


@pytest.fixture
def db_session():
    """In-memory SQLite session with all tables (StaticPool so the override and
    the test body share one connection)."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def api(db_session):
    """TestClient for the runs router; mutate ``state["user"]`` to switch the
    authenticated principal (for the cross-owner IDOR assertion)."""
    app = FastAPI()
    app.include_router(router)

    state: dict = {"user": _FakeUser(id="owner-A")}

    def override_user():
        return state["user"]

    def override_db():
        yield db_session

    app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[get_db] = override_db
    return TestClient(app), state


def _seed_run(db, *, run_id, owner_id, workspace_id="ws-1"):
    db.add(
        WorkflowRun(
            id=run_id,
            user_id=owner_id,
            title="My Run",
            type="prototype",
            status="completed",
            input="build me a thing",
            owner_id=owner_id,
            workspace_id=workspace_id,
            created_at=datetime.now(timezone.utc),
        )
    )
    db.commit()


def _t(seconds: int) -> datetime:
    """A deterministic ascending timestamp helper (for order-by assertions)."""
    return datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=seconds)


def _seed_gate_event(db, *, id, run_id, owner_id, workspace_id="ws-1", step="specify",
                     gate="validation", outcome="pass", detail=None, at=0):
    db.add(
        GateEvent(
            id=id, run_id=run_id, owner_id=owner_id, workspace_id=workspace_id,
            step=step, gate=gate, outcome=outcome, detail=detail, created_at=_t(at),
        )
    )
    db.commit()


def _seed_validation_result(db, *, id, run_id, owner_id, workspace_id="ws-1",
                            step="build", validator="static_check", severity="HIGH",
                            attempt=0, issues=None, at=0):
    db.add(
        ValidationResult(
            id=id, run_id=run_id, owner_id=owner_id, workspace_id=workspace_id,
            step=step, validator=validator, severity=severity, attempt=attempt,
            issues=issues if issues is not None else [], created_at=_t(at),
        )
    )
    db.commit()


def _seed_exec_run(db, *, id, run_id, owner_id, workspace_id="ws-1", step="build",
                   argv_json=None, outcome="allowed", exit_code=0, duration_ms=42,
                   policy_snapshot_json=None, output_digest="sha256:deadbeef…(truncated)",
                   at=0):
    db.add(
        ExecRun(
            id=id, run_id=run_id, owner_id=owner_id, workspace_id=workspace_id,
            step=step, argv_json=argv_json if argv_json is not None else ["echo", "hi"],
            outcome=outcome, exit_code=exit_code, duration_ms=duration_ms,
            policy_snapshot_json=policy_snapshot_json if policy_snapshot_json is not None else {"exec": True},
            output_digest=output_digest, created_at=_t(at),
        )
    )
    db.commit()


# Endpoint path suffix ↔ response-envelope key ↔ pinned projection columns.
_GATE_COLS = {"id", "run_id", "step", "gate", "outcome", "detail", "created_at"}
_VALIDATION_COLS = {"id", "run_id", "step", "validator", "severity", "attempt", "issues", "created_at"}
_EXEC_COLS = {
    "id", "run_id", "step", "argv_json", "outcome", "exit_code",
    "duration_ms", "policy_snapshot_json", "output_digest", "created_at",
}


# ---------------------------------------------------------------------------
# 200 + owner rows, ascending order, pinned projection
# ---------------------------------------------------------------------------


class TestOwnerRows:
    def test_gate_events_owner_rows_ordered_and_projected(self, api, db_session):
        client, _ = api
        _seed_run(db_session, run_id="run-A", owner_id="owner-A")
        # Insert out of order; endpoint must return created_at ascending.
        _seed_gate_event(db_session, id="g2", run_id="run-A", owner_id="owner-A",
                         gate="security", outcome="block", detail={"why": "net"}, at=20)
        _seed_gate_event(db_session, id="g1", run_id="run-A", owner_id="owner-A",
                         gate="validation", outcome="pass", detail=None, at=10)

        resp = client.get("/api/runs/run-A/gate-events")
        assert resp.status_code == 200, resp.text
        rows = resp.json()["gate_events"]
        assert [r["id"] for r in rows] == ["g1", "g2"], "not ordered created_at asc"
        assert set(rows[0].keys()) == _GATE_COLS, "projection drift on gate-events"
        assert rows[1]["outcome"] == "block"
        assert rows[1]["detail"] == {"why": "net"}

    def test_validation_results_owner_rows_ordered_and_projected(self, api, db_session):
        client, _ = api
        _seed_run(db_session, run_id="run-A", owner_id="owner-A")
        _seed_validation_result(db_session, id="v2", run_id="run-A", owner_id="owner-A",
                                validator="render_check", severity="LOW", attempt=1,
                                issues=[{"msg": "warn"}], at=20)
        _seed_validation_result(db_session, id="v1", run_id="run-A", owner_id="owner-A",
                                validator="static_check", severity="HIGH", attempt=0,
                                issues=[], at=10)

        resp = client.get("/api/runs/run-A/validation-results")
        assert resp.status_code == 200, resp.text
        rows = resp.json()["validation_results"]
        assert [r["id"] for r in rows] == ["v1", "v2"], "not ordered created_at asc"
        assert set(rows[0].keys()) == _VALIDATION_COLS, "projection drift on validation-results"
        assert rows[1]["validator"] == "render_check"
        assert rows[1]["attempt"] == 1
        assert rows[1]["issues"] == [{"msg": "warn"}]

    def test_exec_runs_owner_rows_ordered_and_projected(self, api, db_session):
        client, _ = api
        _seed_run(db_session, run_id="run-A", owner_id="owner-A")
        _seed_exec_run(db_session, id="e2", run_id="run-A", owner_id="owner-A",
                       outcome="denied", exit_code=None, duration_ms=None, at=20)
        _seed_exec_run(db_session, id="e1", run_id="run-A", owner_id="owner-A",
                       outcome="allowed", exit_code=0, duration_ms=42, at=10)

        resp = client.get("/api/runs/run-A/exec-runs")
        assert resp.status_code == 200, resp.text
        rows = resp.json()["exec_runs"]
        assert [r["id"] for r in rows] == ["e1", "e2"], "not ordered created_at asc"
        assert set(rows[0].keys()) == _EXEC_COLS, "projection drift on exec-runs"
        assert rows[0]["argv_json"] == ["echo", "hi"]
        assert rows[1]["outcome"] == "denied"

    def test_empty_run_returns_empty_lists(self, api, db_session):
        client, _ = api
        _seed_run(db_session, run_id="run-A", owner_id="owner-A")
        assert client.get("/api/runs/run-A/gate-events").json()["gate_events"] == []
        assert client.get("/api/runs/run-A/validation-results").json()["validation_results"] == []
        assert client.get("/api/runs/run-A/exec-runs").json()["exec_runs"] == []


# ---------------------------------------------------------------------------
# T-32-03-02 / ASVS V7 — exec-runs surfaces ONLY the truncated output_digest
# ---------------------------------------------------------------------------


class TestExecDigestOnly:
    def test_exec_runs_exposes_only_truncated_digest_never_raw_output(self, api, db_session):
        client, _ = api
        _seed_run(db_session, run_id="run-A", owner_id="owner-A")
        _seed_exec_run(db_session, id="e1", run_id="run-A", owner_id="owner-A",
                       output_digest="sha256:cafe…(truncated)", at=10)

        row = client.get("/api/runs/run-A/exec-runs").json()["exec_runs"][0]
        assert row["output_digest"] == "sha256:cafe…(truncated)"
        # No raw-output field of any name may appear in the projection.
        for leaked in ("output", "stdout", "stderr", "raw_output", "output_raw", "child_output"):
            assert leaked not in row, f"exec-runs leaked a raw-output field: {leaked}"
        assert set(row.keys()) == _EXEC_COLS


# ---------------------------------------------------------------------------
# T-32-03-01 / P13 / P25 — IDOR resolves to 404 (never 403, never foreign rows)
# ---------------------------------------------------------------------------


class TestCrossOwnerDenied:
    def _seed_two_owners(self, db):
        # Run owned by B, with a child row per audit table.
        _seed_run(db, run_id="run-B", owner_id="owner-B")
        _seed_gate_event(db, id="gB", run_id="run-B", owner_id="owner-B", at=1)
        _seed_validation_result(db, id="vB", run_id="run-B", owner_id="owner-B", at=1)
        _seed_exec_run(db, id="eB", run_id="run-B", owner_id="owner-B", at=1)

    @pytest.mark.parametrize(
        "suffix,key",
        [("gate-events", "gate_events"),
         ("validation-results", "validation_results"),
         ("exec-runs", "exec_runs")],
    )
    def test_cross_owner_is_404_never_403_never_rows(self, api, db_session, suffix, key):
        client, state = api
        self._seed_two_owners(db_session)

        # A authed, requesting B's run → 404 (never 403, never 200 with B's rows).
        state["user"] = _FakeUser(id="owner-A")
        resp = client.get(f"/api/runs/run-B/{suffix}")
        assert resp.status_code == 404, f"IDOR: A read B's {suffix} (got {resp.status_code})"
        assert resp.status_code != 403, "IDOR must resolve to 404, not 403 (existence leak)"

    @pytest.mark.parametrize(
        "suffix", ["gate-events", "validation-results", "exec-runs"],
    )
    def test_missing_run_is_404(self, api, db_session, suffix):
        client, _ = api
        resp = client.get(f"/api/runs/does-not-exist/{suffix}")
        assert resp.status_code == 404, resp.text

    @pytest.mark.parametrize(
        "suffix,key",
        [("gate-events", "gate_events"),
         ("validation-results", "validation_results"),
         ("exec-runs", "exec_runs")],
    )
    def test_owner_sees_only_own_rows_not_foreign(self, api, db_session, suffix, key):
        # Two runs: A's (own) and B's (foreign). A must see ONLY A's row.
        client, state = api
        _seed_run(db_session, run_id="run-A", owner_id="owner-A")
        _seed_gate_event(db_session, id="gA", run_id="run-A", owner_id="owner-A", at=1)
        _seed_validation_result(db_session, id="vA", run_id="run-A", owner_id="owner-A", at=1)
        _seed_exec_run(db_session, id="eA", run_id="run-A", owner_id="owner-A", at=1)
        self._seed_two_owners(db_session)

        state["user"] = _FakeUser(id="owner-A")
        rows = client.get(f"/api/runs/run-A/{suffix}").json()[key]
        assert len(rows) == 1
        assert rows[0]["run_id"] == "run-A"
        assert not any(r["run_id"] == "run-B" for r in rows), "foreign owner rows leaked"


# ---------------------------------------------------------------------------
# T-32-03-05 — every endpoint sits behind Depends(get_current_user)
# ---------------------------------------------------------------------------


class TestAuthRequired:
    @pytest.mark.parametrize(
        "suffix", ["gate-events", "validation-results", "exec-runs"],
    )
    def test_unauthenticated_is_rejected(self, db_session, suffix):
        # Build an app whose get_current_user raises 401 (simulating no valid
        # token): the request must be rejected BEFORE the handler body runs.
        app = FastAPI()
        app.include_router(router)

        def deny_user():
            raise HTTPException(status_code=401, detail="Not authenticated")

        def override_db():
            yield db_session

        app.dependency_overrides[get_current_user] = deny_user
        app.dependency_overrides[get_db] = override_db
        client = TestClient(app)

        _seed_run(db_session, run_id="run-A", owner_id="owner-A")
        resp = client.get(f"/api/runs/run-A/{suffix}")
        assert resp.status_code in (401, 403), resp.text
