"""tests/unit/test_chat_narrator.py — CHAT-04 (29-10): the milestone → chat_reply narrator.

The narrator projects run milestones into ``chat_reply`` result cards — clarify / gate /
pipeline / deliverable, plus a ``spec_revision`` card for the KAN-101 intra-run loop-back
("Revising spec — cycle N"). Each card is a PURE projection of an already-emitted run
event (NO model call), carrying the single-use deep-link ``{target, nonce}`` seam, and is
persisted as a ``chat_reply`` ``run_events`` row through the SAME
``ScopedStore.append_event`` stamping boundary every engine event rides (zero new tables).

Two halves:
  * **Task 1 — projection**: all five card kinds project correctly from their source
    events, each with a consume-once deep-link nonce; a non-milestone event → None.
  * **Task 2 — persistence + golden-neutrality**: a card persists as ONE ``chat_reply``
    ``run_events`` row (family-anchored, owner-scoped, idempotent on the source event);
    the narrator is DORMANT on scripted golden runs, so the 5 characterization goldens
    stay byte/event-identical (that regression proof is the sibling golden suites).

LOCK-B: this suite + ``app/agents/chat_narrator.py`` are the ONLY files touched. No
kernel import; import-linter stays 4 kept / 0 broken.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest


# ════════════════════════════════════════════════════════════════════════════
# Task 1 — the pure projection (no model call, no persistence)
# ════════════════════════════════════════════════════════════════════════════
class TestProjection:
    def _event(self, etype, **data):
        data.setdefault("pipeline_run_id", "run-1")
        return {"type": etype, "data": data}

    def test_clarify_card_from_questionnaire_ready(self):
        from app.agents.chat_narrator import CARD_CLARIFY, project_milestone_card

        card = project_milestone_card(self._event("questionnaire_ready", question_count=3))
        assert card is not None
        assert card["card_kind"] == CARD_CLARIFY
        assert "3" in card["text"]
        assert card["pipeline_run_id"] == "run-1"

    def test_clarify_card_from_questionnaire_complete(self):
        from app.agents.chat_narrator import CARD_CLARIFY, project_milestone_card

        card = project_milestone_card(self._event("questionnaire_complete", question_count=2))
        assert card["card_kind"] == CARD_CLARIFY

    def test_gate_card_from_review_gate_ready(self):
        from app.agents.chat_narrator import CARD_GATE, project_milestone_card

        card = project_milestone_card(
            self._event("review_gate_ready", gate_key="run-1:prototype-specify")
        )
        assert card["card_kind"] == CARD_GATE
        # the deep-link target anchors on the gate the card reports
        assert card["deep_link"]["target"] == "run-1:prototype-specify"

    def test_pipeline_card_from_start(self):
        from app.agents.chat_narrator import CARD_PIPELINE, project_milestone_card

        card = project_milestone_card(self._event("pipeline_start"))
        assert card["card_kind"] == CARD_PIPELINE

    def test_pipeline_card_from_failed_and_cancelled(self):
        from app.agents.chat_narrator import CARD_PIPELINE, project_milestone_card

        assert project_milestone_card(self._event("pipeline_failed"))["card_kind"] == CARD_PIPELINE
        assert (
            project_milestone_card(self._event("pipeline_cancelled"))["card_kind"] == CARD_PIPELINE
        )

    def test_pipeline_complete_without_deliverable_is_pipeline_card(self):
        from app.agents.chat_narrator import CARD_PIPELINE, project_milestone_card

        card = project_milestone_card(self._event("pipeline_complete", final_output="text"))
        assert card["card_kind"] == CARD_PIPELINE

    def test_deliverable_card_from_pipeline_complete_with_artifact(self):
        from app.agents.chat_narrator import CARD_DELIVERABLE, project_milestone_card

        card = project_milestone_card(
            self._event(
                "pipeline_complete",
                deliverable_filename="prototype.html",
                deliverable_mimetype="text/html",
            )
        )
        assert card["card_kind"] == CARD_DELIVERABLE
        assert "prototype.html" in card["deep_link"]["target"]

    def test_spec_revision_card_labels_cycle_distinctly(self):
        # KAN-101 intra-run loop-back — distinct from a family revision run (D-02).
        from app.agents.chat_narrator import CARD_SPEC_REVISION, project_milestone_card

        card = project_milestone_card(self._event("agent_start", spec_revision_attempt=2))
        assert card["card_kind"] == CARD_SPEC_REVISION
        assert "cycle 2" in card["text"].lower()  # "Revising spec — cycle 2"

    def test_spec_revision_accepts_revision_index_alias(self):
        from app.agents.chat_narrator import CARD_SPEC_REVISION, project_milestone_card

        card = project_milestone_card(self._event("agent_start", revision_index=1))
        assert card["card_kind"] == CARD_SPEC_REVISION

    def test_spec_revision_precedes_the_plain_milestone(self):
        # attempt>0 wins even when the carrying event would otherwise be a pipeline card.
        from app.agents.chat_narrator import CARD_SPEC_REVISION, project_milestone_card

        card = project_milestone_card(
            self._event("pipeline_start", spec_revision_attempt=3)
        )
        assert card["card_kind"] == CARD_SPEC_REVISION

    def test_all_five_card_kinds_are_the_documented_set(self):
        from app.agents.chat_narrator import (
            CARD_CLARIFY,
            CARD_DELIVERABLE,
            CARD_GATE,
            CARD_KINDS,
            CARD_PIPELINE,
            CARD_SPEC_REVISION,
        )

        assert CARD_KINDS == {
            CARD_CLARIFY,
            CARD_GATE,
            CARD_PIPELINE,
            CARD_DELIVERABLE,
            CARD_SPEC_REVISION,
        }

    def test_non_milestone_event_projects_nothing(self):
        from app.agents.chat_narrator import project_milestone_card

        assert project_milestone_card(self._event("agent_chunk", chunk="hi")) is None
        assert project_milestone_card(self._event("tool_call")) is None

    def test_card_carries_a_deep_link_target_and_nonce(self):
        from app.agents.chat_narrator import project_milestone_card

        card = project_milestone_card(self._event("pipeline_start"))
        dl = card["deep_link"]
        assert set(dl) == {"target", "nonce"}
        assert dl["target"] and dl["nonce"]

    def test_no_model_call_is_made(self, monkeypatch):
        # The projection is pure — it must not construct or invoke any model.
        import app.agents.chat_narrator as narrator

        assert not hasattr(narrator, "build_model")  # no model dependency imported
        # Two projections of the same event yield fresh, distinct nonces (stateless).
        c1 = narrator.project_milestone_card(self._event("pipeline_start"))
        c2 = narrator.project_milestone_card(self._event("pipeline_start"))
        assert c1["deep_link"]["nonce"] != c2["deep_link"]["nonce"]

    def test_projects_from_run_events_row_shape(self):
        # The narrator also reads a persisted RunEvent-like row (payload_json).
        from app.agents.chat_narrator import CARD_GATE, project_milestone_card

        class _Row:
            type = "review_gate_ready"
            payload_json = {"pipeline_run_id": "run-9", "gate_key": "run-9:agent"}

        card = project_milestone_card(_Row())
        assert card["card_kind"] == CARD_GATE
        assert card["pipeline_run_id"] == "run-9"


class TestDeepLinkNonceProjection:
    def _card(self):
        from app.agents.chat_narrator import project_milestone_card

        return project_milestone_card({"type": "pipeline_start", "data": {"pipeline_run_id": "r"}})

    def test_distinct_cards_get_distinct_nonces(self):
        # The pure projection generates a fresh candidate nonce per card (side-effect-free
        # — the durable row is minted only at persist time; see TestDeepLinkNonceDB).
        assert self._card()["deep_link"]["nonce"] != self._card()["deep_link"]["nonce"]

    def test_projection_does_not_touch_the_db(self):
        # WR-02: the Phase-29 module-global in-memory _ISSUED_NONCES set is DELETED, and
        # the projection is pure — no DB write, no module-level nonce registry survives.
        import app.agents.chat_narrator as narrator

        assert not hasattr(narrator, "_ISSUED_NONCES")
        assert not hasattr(narrator, "_mint_nonce")


# ════════════════════════════════════════════════════════════════════════════
# Task 2 — persist chat_reply as a run_events row (offline, real ScopedStore)
# ════════════════════════════════════════════════════════════════════════════
@pytest.fixture
def store_env(monkeypatch):
    """A ScopedStore bound to an in-memory SQLite log (no live Bedrock / server)."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app.models import database as db_module
    from app.models.database import Base

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr(db_module, "SessionLocal", Session)

    yield {"Session": Session}

    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def _seed_run(store_env, *, owner_id, workspace_id="ws-1", status="running"):
    from app.models.workflow import WorkflowRun

    run_id = str(uuid.uuid4())
    db = store_env["Session"]()
    try:
        db.add(WorkflowRun(
            id=run_id, user_id=owner_id, owner_id=owner_id, workspace_id=workspace_id,
            title="t", type="prototype", status=status, input="i",
            agent_count=1, session_id=owner_id, created_at=datetime.now(timezone.utc),
        ))
        db.commit()
        return run_id
    finally:
        db.close()


def _seed_events(store_env, run_id, rows, *, owner_id, workspace_id="ws-1"):
    from app.models.run_event import RunEvent

    db = store_env["Session"]()
    try:
        for seq, etype, payload in rows:
            db.add(RunEvent(
                id=str(uuid.uuid4()), run_id=run_id, owner_id=owner_id,
                workspace_id=workspace_id, seq=seq, event_id=f"e{seq}",
                type=etype, payload_json=payload,
            ))
        db.commit()
    finally:
        db.close()


def _reply_rows(store_env, run_id):
    from app.models.run_event import RunEvent

    db = store_env["Session"]()
    try:
        return (
            db.query(RunEvent)
            .filter(RunEvent.run_id == run_id, RunEvent.type == "chat_reply")
            .order_by(RunEvent.seq.asc())
            .all()
        )
    finally:
        db.close()


def _run(coro):
    import asyncio

    return asyncio.get_event_loop().run_until_complete(coro)


class TestPersistence:
    def _store(self, owner_id, workspace_id="ws-1"):
        from agents.authz import ScopedStore

        return ScopedStore(owner_id=owner_id, workspace_id=workspace_id)

    def test_card_persists_as_one_chat_reply_row(self, store_env):
        from app.agents.chat_narrator import persist_milestone_card

        owner = "owner-1"
        run_id = _seed_run(store_env, owner_id=owner)
        event = {"type": "review_gate_ready", "event_id": "src-1",
                 "data": {"pipeline_run_id": run_id, "gate_key": f"{run_id}:agent"}}

        created, seq, card = _run(persist_milestone_card(self._store(owner), run_id, event))
        assert created is True
        rows = _reply_rows(store_env, run_id)
        assert len(rows) == 1
        assert rows[0].type == "chat_reply"
        assert rows[0].payload_json["card_kind"] == "gate"
        assert rows[0].owner_id == owner  # family-anchored + owner-scoped
        assert rows[0].workspace_id == "ws-1"

    def test_seq_is_next_after_existing_events(self, store_env):
        from app.agents.chat_narrator import persist_milestone_card

        owner = "owner-2"
        run_id = _seed_run(store_env, owner_id=owner)
        _seed_events(store_env, run_id, [(1, "pipeline_start", {}), (2, "agent_start", {})],
                     owner_id=owner)
        event = {"type": "pipeline_complete", "event_id": "src-c",
                 "data": {"pipeline_run_id": run_id, "deliverable_filename": "p.html"}}

        created, seq, card = _run(persist_milestone_card(self._store(owner), run_id, event))
        assert seq == 3  # max(1,2)+1 — same contiguous seq the engine sink computes

    def test_replayed_milestone_is_idempotent_noop(self, store_env):
        from app.agents.chat_narrator import persist_milestone_card

        owner = "owner-3"
        run_id = _seed_run(store_env, owner_id=owner)
        event = {"type": "pipeline_start", "event_id": "src-dup",
                 "data": {"pipeline_run_id": run_id}}

        r1 = _run(persist_milestone_card(self._store(owner), run_id, event))
        r2 = _run(persist_milestone_card(self._store(owner), run_id, event))  # replay
        assert r1[0] is True and r2[0] is False  # second is a no-op
        assert r1[1] == r2[1]  # same seq
        assert len(_reply_rows(store_env, run_id)) == 1  # exactly ONE row

    def test_non_milestone_persists_nothing(self, store_env):
        from app.agents.chat_narrator import persist_milestone_card

        owner = "owner-4"
        run_id = _seed_run(store_env, owner_id=owner)
        event = {"type": "agent_chunk", "event_id": "src-x",
                 "data": {"pipeline_run_id": run_id, "chunk": "hi"}}

        assert _run(persist_milestone_card(self._store(owner), run_id, event)) is None
        assert _reply_rows(store_env, run_id) == []

    def test_cross_owner_store_cannot_read_or_double_write(self, store_env):
        # The projection reads only the run's OWN events; a cross-owner store's
        # default-deny read sees none, so its seq restarts at 1 (never leaks the
        # owner's rows). T-29-10-1: card never crosses the owner boundary.
        from app.agents.chat_narrator import persist_milestone_card

        owner = "owner-5"
        run_id = _seed_run(store_env, owner_id=owner)
        _seed_events(store_env, run_id, [(1, "pipeline_start", {})], owner_id=owner)
        event = {"type": "pipeline_failed", "event_id": "src-f",
                 "data": {"pipeline_run_id": run_id}}

        # attacker store is scoped to a DIFFERENT owner — read_events default-denies.
        created, seq, _ = _run(
            persist_milestone_card(self._store("attacker"), run_id, event)
        )
        # It can only see its own (empty) scope → seq starts at 1, and the row it writes
        # is stamped with the attacker principal (never mutates the owner's rows).
        attacker_rows = [
            r for r in _reply_rows(store_env, run_id) if r.owner_id == "attacker"
        ]
        assert len(attacker_rows) == 1
        assert seq == 1


# ════════════════════════════════════════════════════════════════════════════
# WR-02 — the DB-backed, owner+workspace-scoped, single-use deep-link nonce
# ════════════════════════════════════════════════════════════════════════════
class TestDeepLinkNonceDB:
    """The hardened nonce: DB-backed (migration 0025), owner+workspace-scoped, single-use,
    bounded. Replaces the Phase-29 process-global in-memory set (unbounded/unscoped/lost on
    restart). A replayed OR cross-owner nonce resolves to nothing (False → 404, IDOR)."""

    def _store(self, owner_id, workspace_id="ws-1"):
        from agents.authz import ScopedStore

        return ScopedStore(owner_id=owner_id, workspace_id=workspace_id)

    def _mint_card_nonce(self, store_env, *, owner_id, workspace_id="ws-1"):
        """Drive a card through persist_milestone_card so its nonce is minted as a durable
        owner+workspace-scoped deep_link_nonces row; return that nonce."""
        from app.agents.chat_narrator import persist_milestone_card

        run_id = _seed_run(store_env, owner_id=owner_id, workspace_id=workspace_id)
        event = {"type": "pipeline_start", "event_id": f"src-{uuid.uuid4().hex[:8]}",
                 "data": {"pipeline_run_id": run_id}}
        created, _seq, card = _run(
            persist_milestone_card(self._store(owner_id, workspace_id), run_id, event)
        )
        assert created is True
        return card["deep_link"]["nonce"]

    def test_first_consume_by_correct_owner_is_true(self, store_env):
        from app.agents.chat_narrator import consume_deep_link

        nonce = self._mint_card_nonce(store_env, owner_id="owner-A")
        assert _run(consume_deep_link(self._store("owner-A"), nonce)) is True

    def test_second_consume_is_false_single_use(self, store_env):
        # T-43-03-REPLAY: a replayed deep-link nonce must not resolve twice.
        from app.agents.chat_narrator import consume_deep_link

        nonce = self._mint_card_nonce(store_env, owner_id="owner-A")
        assert _run(consume_deep_link(self._store("owner-A"), nonce)) is True
        assert _run(consume_deep_link(self._store("owner-A"), nonce)) is False

    def test_cross_owner_consume_is_false_idor(self, store_env):
        # T-43-03-SPOOF/IDOR: owner-B may not consume owner-A's nonce → False → 404.
        from app.agents.chat_narrator import consume_deep_link

        nonce = self._mint_card_nonce(store_env, owner_id="owner-A")
        assert _run(consume_deep_link(self._store("owner-B"), nonce)) is False
        # and it is still consumable by the true owner (cross-owner attempt didn't burn it)
        assert _run(consume_deep_link(self._store("owner-A"), nonce)) is True

    def test_cross_workspace_consume_is_false(self, store_env):
        # owner+WORKSPACE scoped: a different workspace under the same owner → False.
        from app.agents.chat_narrator import consume_deep_link

        nonce = self._mint_card_nonce(store_env, owner_id="owner-A", workspace_id="ws-1")
        assert _run(consume_deep_link(self._store("owner-A", "ws-2"), nonce)) is False
        assert _run(consume_deep_link(self._store("owner-A", "ws-1"), nonce)) is True

    def test_unknown_nonce_never_resolves(self, store_env):
        from app.agents.chat_narrator import consume_deep_link

        assert _run(consume_deep_link(self._store("owner-A"), "never-issued")) is False

    def test_nonce_row_is_bounded_terminal_on_consume(self, store_env):
        # T-43-03-DOS: consumed rows are the terminal state (bounded growth). After a
        # consume the row's consumed_at is set, so it can never resolve again.
        from app.agents.chat_narrator import consume_deep_link
        from app.models.run_event import DeepLinkNonce

        nonce = self._mint_card_nonce(store_env, owner_id="owner-A")
        assert _run(consume_deep_link(self._store("owner-A"), nonce)) is True
        db = store_env["Session"]()
        try:
            row = db.query(DeepLinkNonce).filter(DeepLinkNonce.nonce == nonce).first()
            assert row is not None and row.consumed_at is not None
        finally:
            db.close()

    def test_replayed_card_does_not_leak_a_second_nonce_row(self, store_env):
        # The nonce row is minted only when the card row is created; a replayed milestone
        # (idempotent no-op) must not add a second unconsumed nonce (rows 1:1 with cards).
        from app.agents.chat_narrator import persist_milestone_card
        from app.models.run_event import DeepLinkNonce

        owner = "owner-R"
        run_id = _seed_run(store_env, owner_id=owner)
        event = {"type": "pipeline_start", "event_id": "src-replay",
                 "data": {"pipeline_run_id": run_id}}
        r1 = _run(persist_milestone_card(self._store(owner), run_id, event))
        r2 = _run(persist_milestone_card(self._store(owner), run_id, event))  # replay
        assert r1[0] is True and r2[0] is False
        db = store_env["Session"]()
        try:
            assert db.query(DeepLinkNonce).count() == 1  # exactly ONE nonce row
        finally:
            db.close()
