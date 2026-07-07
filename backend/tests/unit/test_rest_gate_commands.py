"""tests/unit/test_rest_gate_commands.py — CHAT-07 / D-13 (29-03).

The up-channel REST twin of ``POST /api/runs/{id}/gate``, ported 1:1 from
``test_approve_review_ownership.py`` (the WS ``approve_review`` handler suite)
against the REST endpoint. The endpoint is a thin wrapper over the SAME
``store.set_review_response`` seam the WS handler calls (LOCK-B — ``websocket.py``
is untouched; the ownership + terminal predicates are read-only imports).

Coverage (mirrors the WS suite, adapted to HTTP):
  * P13 / T-29-03-1 owner gate — owner (even with ``owner_id`` NULL) resolves;
    cross-user / unknown-run / malformed gate_key all deny with a non-revealing
    404 "Unknown gate_key" (IDOR → 404, never 403).
  * The FOUR gate actions resolve the pause via the store seam
    (approve / reject / redo+instructions / update_specs).
  * KAN-100 / T-29-03-2 terminal fence — a gate action on a terminal run returns
    ``pipeline_not_running`` (recoverable:false).
  * KAN-94 event-driven gate — an agent with no armed gate → clean not-found,
    never a fabricated pause / a resolved gate no one is waiting on.
  * Source-order wiring pin — the ownership predicate gates
    ``set_review_response`` (and the redo write rides the same boundary).
"""

from __future__ import annotations

import asyncio
import re
import uuid
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


# ────────────────────────────────────────────────────────────────────────────
# Harness — in-memory SQLite bound to ws_module._get_db (mirrors the source
# suite's ``_ws_db_env``, since the shared owner/terminal predicates open their
# own ws session) + a TestClient over the run_commands router.
# ────────────────────────────────────────────────────────────────────────────


class _FakeUser:
    def __init__(self, id: str):
        self.id = id


@pytest.fixture
def env(monkeypatch):
    from app.api import websocket as ws_module
    from app.models.database import Base

    db_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    Base.metadata.create_all(bind=db_engine)
    # The gate/answers/cancel ownership + terminal predicates open their OWN ws
    # session — bind it to the in-memory DB (exactly as the WS suite does).
    monkeypatch.setattr(ws_module, "_get_db", lambda: TestingSession())

    # Fresh artifact-store singleton per test (per-process HITL registry) so an
    # armed gate / recorded response never leaks across tests.
    import agents.artifact_store.store as store_mod
    store_mod._STORE = None
    store = store_mod.get_artifact_store()

    from app.api.run_commands import router
    from app.core.dependencies import get_current_user

    app = FastAPI()
    app.include_router(router)
    state: dict = {"user": None}
    app.dependency_overrides[get_current_user] = lambda: state["user"]
    client = TestClient(app)

    yield {
        "ws": ws_module,
        "store": store,
        "client": client,
        "state": state,
        "Session": TestingSession,
    }

    Base.metadata.drop_all(bind=db_engine)
    db_engine.dispose()
    store_mod._STORE = None


def _seed_user(env, email_tag: str) -> _FakeUser:
    from app.models.user import User

    db = env["ws"]._get_db()
    try:
        u = User(
            id=str(uuid.uuid4()),
            email=f"rest03-{email_tag}-{uuid.uuid4().hex[:8]}@example.com",
            password_hash="x",
        )
        db.add(u)
        db.commit()
        db.refresh(u)
        return _FakeUser(id=u.id)
    finally:
        db.close()


def _seed_run(env, user_id: str, *, status: str = "running") -> str:
    """A run exactly as the main WS creation site writes it: ``user_id`` set,
    ``owner_id`` left NULL (the Phase-5 backfill column ownership must NOT key
    on). ``status`` lets the terminal-fence tests seed a stopped run."""
    from app.models.workflow import WorkflowRun

    run_id = str(uuid.uuid4())
    db = env["ws"]._get_db()
    try:
        db.add(
            WorkflowRun(
                id=run_id,
                user_id=user_id,
                title="t",
                type="prototype",
                status=status,
                input="i",
                agent_count=1,
                session_id=user_id,
            )
        )
        db.commit()
        return run_id
    finally:
        db.close()


def _arm_gate(env, gate_key: str) -> None:
    """Mimic ``_run_review_gate`` arming the review event (KAN-94 ground truth):
    an armed-but-unset event = a genuinely pending pause."""
    env["store"]._resume_events[f"review:{gate_key}"] = asyncio.Event()


def _recorded(env, gate_key: str) -> dict | None:
    responses = env["store"]._questionnaire_responses.get(f"review:{gate_key}")
    return responses[0] if responses else None


def _post_gate(env, run_id: str, gate_key: str, **body):
    payload = {"gate_key": gate_key, **body}
    return env["client"].post(f"/api/runs/{run_id}/gate", json=payload)


# ────────────────────────────────────────────────────────────────────────────
# Owner gate (P13 / T-29-03-1) — ported 1:1 from the source predicate tests
# ────────────────────────────────────────────────────────────────────────────


def test_owner_with_null_owner_id_is_allowed(env):
    """The run's own creator resolves the gate — even though ``owner_id`` is
    NULL (as the main WS creation site leaves it). Ownership is keyed on
    ``user_id`` (keying on ``owner_id`` would lock the owner out)."""
    owner = _seed_user(env, "owner")
    run_id = _seed_run(env, owner.id)
    gate_key = f"{run_id}:prototype-specify"
    _arm_gate(env, gate_key)
    env["state"]["user"] = owner

    resp = _post_gate(env, run_id, gate_key, action="approve")
    assert resp.status_code == 200, resp.text
    assert _recorded(env, gate_key)["approved"] is True


def test_cross_user_is_denied(env):
    """Another authenticated principal who knows the victim's run id is denied —
    approve/reject/edited_content all mutate the victim's run."""
    victim = _seed_user(env, "victim")
    attacker = _seed_user(env, "attacker")
    run_id = _seed_run(env, victim.id)
    gate_key = f"{run_id}:prototype-specify"
    _arm_gate(env, gate_key)
    env["state"]["user"] = attacker

    resp = _post_gate(env, run_id, gate_key, action="approve")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Unknown gate_key"
    # The victim's gate was NOT resolved (no write past the owner boundary).
    assert _recorded(env, gate_key) is None


def test_unknown_run_is_denied(env):
    """A gate_key naming a nonexistent run denies — indistinguishable from an
    unowned run (no run-existence oracle)."""
    caller = _seed_user(env, "caller")
    env["state"]["user"] = caller
    run_id = str(uuid.uuid4())
    gate_key = f"{run_id}:agent"

    resp = _post_gate(env, run_id, gate_key)
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Unknown gate_key"


@pytest.mark.parametrize("bad_key", [":agent-only", "no-colon-unknown-run"])
def test_malformed_gate_keys_are_denied(env, bad_key):
    caller = _seed_user(env, "caller")
    env["state"]["user"] = caller

    resp = _post_gate(env, "some-run", bad_key)
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Unknown gate_key"


def test_empty_gate_key_is_rejected(env):
    """An empty gate_key is a malformed request (the WS handler's
    ``missing_gate_key`` branch)."""
    caller = _seed_user(env, "caller")
    env["state"]["user"] = caller

    resp = _post_gate(env, "some-run", "")
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "missing_gate_key"


# ────────────────────────────────────────────────────────────────────────────
# The FOUR gate actions resolve the pause via the store seam (POR §6)
# ────────────────────────────────────────────────────────────────────────────


def test_approve_with_edited_content(env):
    owner = _seed_user(env, "owner")
    run_id = _seed_run(env, owner.id)
    gate_key = f"{run_id}:prototype-specify"
    _arm_gate(env, gate_key)
    env["state"]["user"] = owner

    resp = _post_gate(env, run_id, gate_key, action="approve", edited_content="EDITED")
    assert resp.status_code == 200, resp.text
    rec = _recorded(env, gate_key)
    assert rec["approved"] is True
    assert rec["edited_content"] == "EDITED"


def test_reject_sets_approved_false(env):
    owner = _seed_user(env, "owner")
    run_id = _seed_run(env, owner.id)
    gate_key = f"{run_id}:prototype-specify"
    _arm_gate(env, gate_key)
    env["state"]["user"] = owner

    resp = _post_gate(env, run_id, gate_key, action="reject")
    assert resp.status_code == 200, resp.text
    assert _recorded(env, gate_key)["approved"] is False


def test_redo_carries_instructions(env):
    """REDO-GATE: the redo action rides the SAME owner-gated seam, carrying
    free-text instructions for an in-place re-run."""
    owner = _seed_user(env, "owner")
    run_id = _seed_run(env, owner.id)
    gate_key = f"{run_id}:prototype-specify"
    _arm_gate(env, gate_key)
    env["state"]["user"] = owner

    resp = _post_gate(env, run_id, gate_key, action="redo", instructions="tighten the nav")
    assert resp.status_code == 200, resp.text
    rec = _recorded(env, gate_key)
    assert rec["approved"] is False
    assert rec["action"] == "redo"
    assert rec["instructions"] == "tighten the nav"


def test_update_specs_carries_analysis_report_in_instructions(env):
    """KAN-101: ``update_specs`` routes to the shipped spec-revision loop; the
    analysis report travels in the generic ``instructions`` field (SC-001)."""
    owner = _seed_user(env, "owner")
    run_id = _seed_run(env, owner.id)
    gate_key = f"{run_id}:prototype-specify"
    _arm_gate(env, gate_key)
    env["state"]["user"] = owner

    resp = _post_gate(
        env, run_id, gate_key, action="update_specs", analysis_report="REPORT-XYZ"
    )
    assert resp.status_code == 200, resp.text
    rec = _recorded(env, gate_key)
    assert rec["approved"] is False
    assert rec["action"] == "update_specs"
    assert rec["instructions"] == "REPORT-XYZ"


# ────────────────────────────────────────────────────────────────────────────
# KAN-100 terminal fence (T-29-03-2) + KAN-94 event-driven not-found
# ────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("terminal_status", ["cancelled", "failed", "degraded"])
def test_gate_on_terminal_run_returns_pipeline_not_running(env, terminal_status):
    """KAN-100: any gate action on a terminal run is fenced with
    ``pipeline_not_running`` (recoverable:false) — a Redo cannot resume a
    stopped pipeline. The fence precedes the store write."""
    owner = _seed_user(env, "owner")
    run_id = _seed_run(env, owner.id, status=terminal_status)
    gate_key = f"{run_id}:prototype-specify"
    _arm_gate(env, gate_key)  # even an armed gate is fenced
    env["state"]["user"] = owner

    resp = _post_gate(env, run_id, gate_key, action="redo", instructions="x")
    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert detail["code"] == "pipeline_not_running"
    assert detail["recoverable"] is False
    # Fenced BEFORE the write — the gate was not resolved.
    assert _recorded(env, gate_key) is None


def test_no_pending_gate_is_clean_not_found(env):
    """KAN-94: gates are event-driven. An owned, non-terminal run whose agent was
    excluded by gate_agent_ids has no armed gate → clean not-found, never a
    fabricated pause / a resolved gate no one is waiting on."""
    owner = _seed_user(env, "owner")
    run_id = _seed_run(env, owner.id)
    gate_key = f"{run_id}:prototype-specify"
    # Deliberately do NOT arm the gate.
    env["state"]["user"] = owner

    resp = _post_gate(env, run_id, gate_key, action="approve")
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "gate_not_pending"
    # Never fabricated a response.
    assert _recorded(env, gate_key) is None


# ────────────────────────────────────────────────────────────────────────────
# Source-order wiring pin — ownership predicate gates set_review_response
# (grep-ratchet style, ported from the WS suite's #5 test onto run_commands.py)
# ────────────────────────────────────────────────────────────────────────────


def test_gate_handler_gates_set_review_response_on_ownership():
    import app.api.run_commands as rc_module

    source = Path(rc_module.__file__).read_text(encoding="utf-8")
    m = re.search(r"async def resolve_gate\((.*?)\n@router\.", source, re.S)
    assert m, "resolve_gate handler not found in run_commands.py"
    branch = m.group(1)

    guard_at = branch.find("_review_gate_owned_by(")
    write_at = branch.find("set_review_response(")
    assert guard_at != -1, "resolve_gate no longer checks _review_gate_owned_by"
    assert write_at != -1, "resolve_gate no longer calls set_review_response"
    assert guard_at < write_at, (
        "ownership must be verified BEFORE set_review_response "
        "(T-29-03-1: cross-user gate resolution)"
    )
    # The redo action rides the SAME owner-gated boundary — the redo write and
    # every other write are AFTER the ownership predicate.
    assert 'action == "redo"' in branch, (
        "resolve_gate no longer handles the redo action discriminator"
    )
    last_write_at = branch.rfind("set_review_response(")
    assert guard_at < last_write_at, (
        "the redo/update_specs set_review_response must also be after ownership "
        "(redo rides the same IDOR boundary)"
    )
    # The read-only import of the WS seam is present (LOCK-B).
    assert "from app.api.websocket import" in source
    assert "_review_gate_owned_by" in source
