"""tests/unit/test_mechanical_router.py — CHAT-01/CHAT-02/CHAT-05 / D-04 (29-09).

The mechanical intent router's decision table, proven PURE and OFFLINE: each generic
run state routes one chat turn to the correct command channel with **zero model calls**
(the router imports no model / makes no I/O — it is a pure function over a ``RunState``
+ ``ChatTurn``). Covers:

  * clarify_waiting → answers ; gate_paused → gate(4 actions) ; running → steering ;
    terminal → revision.
  * update_specs → KAN-101 (routed via the gate channel, analysis_report carried).
  * terminal fence (KAN-100): a gate action after terminal → pipeline_not_running, no write.
  * event-driven gates (KAN-94): open-gate derivation from the durable run_events + the
    generic ``RunState.phase`` — never a workflow name (SC-001/INV-1).
"""

from __future__ import annotations

from app.api.chat_router import (
    CHANNEL_ANSWERS,
    CHANNEL_GATE,
    CHANNEL_REVISION,
    CHANNEL_STEERING,
    ChatTurn,
    RunState,
    apply_steering,
    apply_turn_images,
    derive_open_gate,
    route_chat_turn,
)


# ════════════════════════════════════════════════════════════════════════════
# phase derivation (generic, name-free)
# ════════════════════════════════════════════════════════════════════════════
class TestPhaseDerivation:
    def test_open_questionnaire_is_clarify_waiting(self):
        rs = RunState(status="waiting_for_user", open_gate="questionnaire")
        assert rs.phase == "clarify_waiting"

    def test_open_review_is_gate_paused(self):
        rs = RunState(status="waiting_for_user", open_gate="review", gate_key="r:a")
        assert rs.phase == "gate_paused"

    def test_running_status_no_gate_is_running(self):
        assert RunState(status="running").phase == "running"

    def test_terminal_statuses_are_terminal(self):
        for s in ("completed", "degraded", "failed", "cancelled", "diverted"):
            assert RunState(status=s).phase == "terminal", s

    def test_open_gate_wins_over_status(self):
        # A paused run's raw status is the generic waiting_for_user; the open gate is the
        # driving signal that separates clarify from gate (never the pipeline name).
        assert RunState(status="running", open_gate="review", gate_key="r:a").phase == "gate_paused"


# ════════════════════════════════════════════════════════════════════════════
# clarify_waiting → answers
# ════════════════════════════════════════════════════════════════════════════
class TestClarifyRouting:
    def test_freetext_maps_to_concierge_not_freeform_answer(self):
        # SAFETY: plain text during clarify (no structured responses from the form)
        # routes to Concierge instead of auto-submitting as a freeform answer.
        # This prevents users typing a question from accidentally answering the form.
        d = route_chat_turn(RunState(status="waiting_for_user", open_gate="questionnaire"),
                            ChatTurn(text="use dark mode"))
        assert d.channel == "concierge"
        assert d.instruction == "use dark mode"

    def test_structured_responses_ride_verbatim(self):
        turn = ChatTurn(responses=[{"question_id": "q1", "answer": "A"}], skip_clarification=True)
        d = route_chat_turn(RunState(status="waiting_for_user", open_gate="questionnaire"), turn)
        assert d.channel == CHANNEL_ANSWERS
        assert d.responses == [{"question_id": "q1", "answer": "A"}]
        assert d.skip_clarification is True


# ════════════════════════════════════════════════════════════════════════════
# gate_paused → gate (four actions), update_specs → KAN-101
# ════════════════════════════════════════════════════════════════════════════
class TestGateRouting:
    def _rs(self):
        return RunState(status="waiting_for_user", open_gate="review", gate_key="run-1:agent")

    def test_default_action_routes_to_concierge_not_auto_approve(self):
        d = route_chat_turn(self._rs(), ChatTurn())
        # KAN-100: a plain text turn with no explicit gate action routes to Concierge,
        # not auto-approved. This prevents silent approval if the user types a question.
        assert d.channel == "concierge"
        assert d.instruction == ""

    def test_reject_and_redo_and_approve(self):
        for action in ("approve", "reject", "redo"):
            d = route_chat_turn(self._rs(), ChatTurn(action=action, text="do it differently"))
            assert d.channel == CHANNEL_GATE
            assert d.action == action

    def test_redo_carries_instructions(self):
        d = route_chat_turn(self._rs(), ChatTurn(action="redo", text="tighten the header"))
        assert d.action == "redo"
        assert d.instructions == "tighten the header"

    def test_update_specs_routes_to_kan101_with_report(self):
        d = route_chat_turn(self._rs(),
                            ChatTurn(action="update_specs", analysis_report="REPORT-BODY"))
        assert d.channel == CHANNEL_GATE
        assert d.action == "update_specs"
        assert d.instructions == "REPORT-BODY"

    def test_unknown_action_routes_to_concierge(self):
        # KAN-100: an unknown/invalid action is not a gate action, so it routes
        # to Concierge instead of being silently treated as approve.
        d = route_chat_turn(self._rs(), ChatTurn(action="bogus"))
        assert d.channel == "concierge"
        assert d.action is None


# ════════════════════════════════════════════════════════════════════════════
# running → steering (29-08 seam)
# ════════════════════════════════════════════════════════════════════════════
class TestSteeringRouting:
    def test_running_routes_to_steering_note(self):
        d = route_chat_turn(RunState(status="running"), ChatTurn(text="prefer teal"))
        assert d.channel == CHANNEL_STEERING
        assert d.note == {"text": "prefer teal", "sticky": False}

    def test_sticky_note_marked_sticky(self):
        d = route_chat_turn(RunState(status="running"), ChatTurn(text="brand.md", sticky=True))
        assert d.note["sticky"] is True

    def test_apply_steering_appends_to_ectx_seam(self):
        class _Ectx:
            def __init__(self):
                self.steering_notes = []

        ectx = _Ectx()
        d = route_chat_turn(RunState(status="running"), ChatTurn(text="go teal"))
        apply_steering(ectx, d.note)
        assert ectx.steering_notes == [{"text": "go teal", "sticky": False}]

    def test_apply_steering_noop_without_seam(self):
        class _Bare:
            pass

        apply_steering(_Bare(), {"text": "x"})  # must not raise


# ════════════════════════════════════════════════════════════════════════════
# per-turn image seam (30-03) — the image analogue of apply_steering
# ════════════════════════════════════════════════════════════════════════════
class TestTurnImageSeam:
    def test_apply_turn_images_appends_to_pending_queue(self):
        class _Ectx:
            def __init__(self):
                self.pending_turn_images = []

        ectx = _Ectx()
        apply_turn_images(ectx, [{"mime_type": "image/png", "data": "AAAA"}])
        assert ectx.pending_turn_images == [{"mime_type": "image/png", "data": "AAAA"}]

    def test_apply_turn_images_normalizes_and_drops_malformed(self):
        class _Ectx:
            def __init__(self):
                self.pending_turn_images = []

        ectx = _Ectx()
        apply_turn_images(ectx, [
            {"mimeType": "image/jpeg", "data": "BBBB"},  # alias key normalized
            {"mime_type": "image/png"},                   # missing data → dropped
            {"data": "CCCC"},                             # missing mime → dropped
            "not-a-dict",                                 # non-dict → dropped
        ])
        assert ectx.pending_turn_images == [{"mime_type": "image/jpeg", "data": "BBBB"}]

    def test_apply_turn_images_noop_without_seam(self):
        class _Bare:
            pass

        apply_turn_images(_Bare(), [{"mime_type": "image/png", "data": "AAAA"}])  # no raise
        apply_turn_images(None, [{"mime_type": "image/png", "data": "AAAA"}])     # no raise


# ════════════════════════════════════════════════════════════════════════════
# terminal → revision + KAN-100 fence
# ════════════════════════════════════════════════════════════════════════════
class TestTerminalRouting:
    def test_terminal_freetext_is_revision(self):
        d = route_chat_turn(RunState(status="completed"),
                            ChatTurn(text="make the CTA bigger", target_artifact_type="prototype_output"))
        assert d.channel == CHANNEL_REVISION
        assert d.instruction == "make the CTA bigger"
        assert d.target_artifact_type == "prototype_output"

    def test_gate_action_after_terminal_is_fenced(self):
        d = route_chat_turn(RunState(status="cancelled"), ChatTurn(action="approve"))
        assert d.channel == CHANNEL_GATE
        assert d.fenced is True
        assert d.code == "pipeline_not_running"

    def test_all_terminal_statuses_route(self):
        for s in ("completed", "degraded", "failed", "cancelled", "diverted"):
            d = route_chat_turn(RunState(status=s), ChatTurn(text="v2 please"))
            assert d.channel == CHANNEL_REVISION, s


# ════════════════════════════════════════════════════════════════════════════
# derive_open_gate — generic, event-driven (KAN-94)
# ════════════════════════════════════════════════════════════════════════════
class TestDeriveOpenGate:
    def test_dangling_review_gate_is_open(self):
        events = [
            {"seq": 1, "type": "agent_start", "payload_json": {}},
            {"seq": 2, "type": "review_gate_ready", "payload_json": {"gate_key": "run-1:specify"}},
        ]
        kind, key = derive_open_gate(events)
        assert kind == "review"
        assert key == "run-1:specify"

    def test_resolved_review_gate_is_closed(self):
        events = [
            {"seq": 1, "type": "review_gate_ready", "payload_json": {"gate_key": "run-1:a"}},
            {"seq": 2, "type": "review_gate_approved", "payload_json": {}},
        ]
        assert derive_open_gate(events) == (None, None)

    def test_dangling_questionnaire_is_open(self):
        events = [{"seq": 1, "type": "questionnaire_ready", "payload_json": {}}]
        assert derive_open_gate(events) == ("questionnaire", None)

    def test_questionnaire_closed_by_pipeline_start(self):
        events = [
            {"seq": 1, "type": "questionnaire_ready", "payload_json": {}},
            {"seq": 2, "type": "pipeline_start", "payload_json": {}},
        ]
        assert derive_open_gate(events) == (None, None)

    def test_review_precedence_over_questionnaire(self):
        events = [
            {"seq": 1, "type": "questionnaire_ready", "payload_json": {}},
            {"seq": 2, "type": "questionnaire_complete", "payload_json": {}},
            {"seq": 3, "type": "review_gate_ready", "payload_json": {"gate_key": "run-1:plan"}},
        ]
        assert derive_open_gate(events) == ("review", "run-1:plan")

    def test_no_events_no_open_gate(self):
        assert derive_open_gate([]) == (None, None)
