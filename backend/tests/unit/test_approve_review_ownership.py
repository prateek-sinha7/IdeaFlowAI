"""tests/unit/test_approve_review_ownership.py — CR-01 (13-REVIEW) / T-13-01-01.

The ``approve_review`` WS message resolves a HITL review gate keyed by
``gate_key = '{run_id}:{agent_id}'`` — approving, rejecting, or injecting
``edited_content`` into the named run. Before the fix the handler called
``set_review_response`` with NO check that the authenticated principal owns
that run, so any authenticated client that learned a victim's run id could
approve the victim's gates (including the ``approval`` gate that is the N3
exec sign-off control), kill the run, or inject content into its deliverable.

The fix gates the handler on ``_review_gate_owned_by(gate_key, user.id)``:

  * ownership is matched on ``WorkflowRun.user_id`` — set at EVERY creation
    site; ``owner_id`` is a nullable Phase-5 backfill the main WS creation
    path leaves unset, so keying on it would lock owners out of their own
    gates (the runs here are seeded with ``owner_id=None`` to pin that);
  * an unknown run and an unowned run are indistinguishable to the caller
    (both deny) — no run-existence oracle.

We drive the predicate directly (the established split — see
``test_run_pipeline_validation.py``: the full WS plumbing is integration-layer)
plus a source-order pin that the handler branch actually gates
``set_review_response`` behind the predicate.
"""

from __future__ import annotations

import uuid

import pytest


@pytest.fixture
def _ws_db_env(monkeypatch):
    """In-memory SQLite bound to ``ws_module._get_db`` (mirrors the
    test_pipeline_failure_semantics.py harness)."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    # W4a (44-03): _review_gate_owned_by + _get_db relocated to app.api.run_engine
    # (INV-12 extract-before-delete). Patch the seam at its new home.
    from app.api import run_engine as ws_module
    from app.models.database import Base

    db_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    Base.metadata.create_all(bind=db_engine)
    monkeypatch.setattr(ws_module, "_get_db", lambda: TestingSession())

    yield ws_module

    Base.metadata.drop_all(bind=db_engine)
    db_engine.dispose()


def _seed_user(ws_module, email_tag: str):
    from app.models.user import User

    db = ws_module._get_db()
    try:
        u = User(
            id=str(uuid.uuid4()),
            email=f"cr01-{email_tag}-{uuid.uuid4().hex[:8]}@example.com",
            password_hash="x",
        )
        db.add(u)
        db.commit()
        db.refresh(u)
        return u
    finally:
        db.close()


def _seed_run(ws_module, user_id: str) -> str:
    """A run exactly as the main WS creation site writes it: ``user_id`` set,
    ``owner_id`` left NULL (the Phase-5 backfill column the handler must NOT
    key ownership on)."""
    from app.models.workflow import WorkflowRun

    run_id = str(uuid.uuid4())
    db = ws_module._get_db()
    try:
        db.add(
            WorkflowRun(
                id=run_id,
                user_id=user_id,
                title="t",
                type="prototype",
                status="running",
                input="i",
                agent_count=1,
                session_id=user_id,
            )
        )
        db.commit()
        return run_id
    finally:
        db.close()


# ────────────────────────────────────────────────────────────────────────────
# Predicate behavior
# ────────────────────────────────────────────────────────────────────────────


def test_owner_with_null_owner_id_is_allowed(_ws_db_env):
    """The run's own creator passes — even though ``owner_id`` is NULL, as the
    main WS creation site leaves it. A check keyed on ``owner_id`` would hang
    the owner's gated run; this pins ``user_id`` as the ownership column."""
    owner = _seed_user(_ws_db_env, "owner")
    run_id = _seed_run(_ws_db_env, owner.id)

    assert _ws_db_env._review_gate_owned_by(f"{run_id}:prototype-specify", owner.id) is True


def test_cross_user_is_denied(_ws_db_env):
    """Another authenticated principal who knows the victim's run id must be
    denied — approve/reject/edited_content all mutate the victim's run."""
    victim = _seed_user(_ws_db_env, "victim")
    attacker = _seed_user(_ws_db_env, "attacker")
    run_id = _seed_run(_ws_db_env, victim.id)

    assert _ws_db_env._review_gate_owned_by(f"{run_id}:prototype-specify", attacker.id) is False


def test_unknown_run_is_denied(_ws_db_env):
    """A gate_key naming a nonexistent run denies — indistinguishable from an
    unowned run (no run-existence oracle)."""
    caller = _seed_user(_ws_db_env, "caller")

    assert _ws_db_env._review_gate_owned_by(f"{uuid.uuid4()}:agent", caller.id) is False


@pytest.mark.parametrize("bad_key", ["", ":agent-only", "no-colon-unknown-run"])
def test_malformed_gate_keys_are_denied(_ws_db_env, bad_key):
    caller = _seed_user(_ws_db_env, "caller")

    assert _ws_db_env._review_gate_owned_by(bad_key, caller.id) is False


# ────────────────────────────────────────────────────────────────────────────
# Wiring pin — RETIRED (44-08).
#
# The source-order pin that the WS ``if msg_type == "approve_review":`` receive-loop
# branch gated ``set_review_response`` behind the ownership predicate is SUPERSEDED:
# the ``/ws/chat`` handler was deleted (44-07). The REST gate-command endpoint is the
# live surface, and its ownership-before-write source-order wiring pin lives in
# ``test_rest_gate_commands.py`` (cross-owner → 404, redo rides the same boundary).
# The transport-neutral predicate behavior above (``_review_gate_owned_by``) stays
# pinned here against ``app.api.run_engine`` (44-03 relocation).
# ────────────────────────────────────────────────────────────────────────────
