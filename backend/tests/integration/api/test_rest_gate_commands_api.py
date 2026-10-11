"""tests/integration/api/test_rest_gate_commands_api.py — CHAT-07 / D-13 (29-03).

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

Lives in the INTEGRATION suite because the owner gate is the point. "Cross-user is
denied" is only meaningful when there are two REAL rows and the ownership predicate
resolves them through its own session — and the shared owner/terminal predicates open
that session themselves, which is why the harness binds the engine at
``ws_module._get_db`` rather than injecting a session. Against a mocked Session the
404s would be indistinguishable from a handler that simply never looked. The
``approved is True/False`` assertions likewise read back what the store actually
recorded. Offline regardless (in-memory engine), so the unit-suite isolation guard
(``tests/unit/conftest.py``) correctly refuses a real DB connection there.

The two STATIC pins that shared this file — the ``GATE_ACTIONS`` vocabulary check and
the source-order wiring ratchet — parse source text and need no store at all; they stay
in ``tests/unit/api/test_rest_gate_commands.py``.
"""

from __future__ import annotations

import asyncio
import uuid

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
    # W4a (44-03): the shared owner/terminal predicates + _get_db were relocated
    # to app.api.run_engine (INV-12 extract-before-delete). Patch the seam at its
    # new home so the relocated _review_gate_* predicates read the in-memory DB.
    from app.api import run_engine as ws_module
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
            cognito_sub=str(uuid.uuid4()),
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


@pytest.mark.issue("ISS-128")
@pytest.mark.xfail(reason="ISS-128 unfixed", strict=True)
def test_reject_persists_reject_action_not_approve(env):
    """ISS-128: the reject branch calls set_review_response without an
    ``action=`` kwarg, so the store's ``action: str = "approve"`` default
    stamps a false 'approve' on the durable audit row even though the
    engine's terminal decision (keyed on ``approved``) still rejects
    correctly. The persisted record must say what actually happened.
    """
    owner = _seed_user(env, "owner")
    run_id = _seed_run(env, owner.id)
    gate_key = f"{run_id}:prototype-specify"
    _arm_gate(env, gate_key)
    env["state"]["user"] = owner

    resp = _post_gate(env, run_id, gate_key, action="reject")
    assert resp.status_code == 200, resp.text
    rec = _recorded(env, gate_key)
    assert rec["approved"] is False
    assert (
        rec["action"] == "reject"
    ), f"durable audit row says action={rec['action']!r} for a rejection"


def test_redo_carries_instructions(env):
    """REDO-GATE: the redo action rides the SAME owner-gated seam, carrying
    free-text instructions for an in-place re-run."""
    owner = _seed_user(env, "owner")
    run_id = _seed_run(env, owner.id)
    gate_key = f"{run_id}:prototype-specify"
    _arm_gate(env, gate_key)
    env["state"]["user"] = owner

    resp = _post_gate(
        env, run_id, gate_key, action="redo", instructions="tighten the nav"
    )
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


@pytest.mark.parametrize(
    "terminal_status", ["cancelled", "failed", "degraded", "diverted"]
)
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
# ISS-070 / FIX-241 — the action discriminator is a CLOSED domain and the
# dispatch fails CLOSED. An unrecognised action must never resolve a HITL gate.
# ────────────────────────────────────────────────────────────────────────────


def _gate_still_armed(env, gate_key: str) -> bool:
    """True iff the review event is still armed-and-unset — i.e. the pause is
    intact and the user can still decide. ``set_review_response`` sets it."""
    return not env["store"]._resume_events[f"review:{gate_key}"].is_set()


def test_unknown_gate_action_is_refused_not_approved(env):
    """ISS-070: a typo'd action must be REFUSED, not silently resolved.

    Refusal — not a degrade to reject: FIX-232 makes a rejection terminal, so
    turning a malformed request into a rejection would destroy the run. Keeping
    the gate armed is the only degrade that preserves every legitimate option.
    """
    owner = _seed_user(env, "owner")
    run_id = _seed_run(env, owner.id)
    gate_key = f"{run_id}:prototype-specify"
    _arm_gate(env, gate_key)
    env["state"]["user"] = owner

    resp = _post_gate(env, run_id, gate_key, action="rejct")
    assert resp.status_code in (400, 422), resp.text
    assert _recorded(env, gate_key) is None, "an unknown action wrote to the store"
    assert _gate_still_armed(env, gate_key), "an unknown action resolved the pause"


@pytest.mark.parametrize(
    "action",
    [
        "Reject",
        "REJECT",
        " reject",
        "reject\n",
        "rejct",
        "no",
        "deny",
        "Redo",
        "redo ",
        "update-specs",
    ],
)
def test_case_and_whitespace_variants_of_reject_never_approve(env, action):
    """The sharpest case: every near-miss of a DENIAL used to APPROVE.

    ``resolve_gate``'s dispatch is case-sensitive and does not strip whitespace,
    so ``"Reject"``, ``" reject"``, ``"rejct"``, ``"no"``, ``"deny"`` all fell to
    ``else: # approve (default)``. The user believes they stopped the run; the
    run continued spending (od_prototype: 5-21M tokens).
    """
    owner = _seed_user(env, "owner")
    run_id = _seed_run(env, owner.id)
    gate_key = f"{run_id}:prototype-specify"
    _arm_gate(env, gate_key)
    env["state"]["user"] = owner

    resp = _post_gate(env, run_id, gate_key, action=action)
    assert resp.status_code in (
        400,
        422,
    ), f"action={action!r} was accepted: {resp.text}"
    rec = _recorded(env, gate_key)
    assert rec is None, f"action={action!r} wrote {rec}"
    assert _gate_still_armed(env, gate_key), f"action={action!r} resolved the pause"


def test_bare_gate_post_still_defaults_to_approve(env):
    """REGRESSION PIN — ``action`` stays OPTIONAL with its ``approve`` default.

    ``tests/agents/test_attach_replay_matrix.py:551`` posts ``{"gate_key": ...}``
    with no ``action`` key at all, and the published OpenAPI contract carries
    ``"default": "approve"``. Constraining the DOMAIN must not make the field
    required. Green before AND after the ISS-070 fix.
    """
    owner = _seed_user(env, "owner")
    run_id = _seed_run(env, owner.id)
    gate_key = f"{run_id}:prototype-specify"
    _arm_gate(env, gate_key)
    env["state"]["user"] = owner

    resp = env["client"].post(f"/api/runs/{run_id}/gate", json={"gate_key": gate_key})
    assert resp.status_code == 200, resp.text
    assert _recorded(env, gate_key)["approved"] is True
