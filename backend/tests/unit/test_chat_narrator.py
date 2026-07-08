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


class TestDeepLinkNonce:
    def _card(self):
        from app.agents.chat_narrator import project_milestone_card

        return project_milestone_card({"type": "pipeline_start", "data": {"pipeline_run_id": "r"}})

    def test_nonce_is_single_use_consume_once(self):
        # T-29-10-2: a replayed deep-link nonce must not resolve twice.
        from app.agents.chat_narrator import consume_deep_link

        nonce = self._card()["deep_link"]["nonce"]
        assert consume_deep_link(nonce) is True  # first use
        assert consume_deep_link(nonce) is False  # reuse rejected

    def test_unknown_nonce_never_resolves(self):
        from app.agents.chat_narrator import consume_deep_link

        assert consume_deep_link("never-issued") is False

    def test_distinct_cards_get_distinct_nonces(self):
        assert self._card()["deep_link"]["nonce"] != self._card()["deep_link"]["nonce"]
