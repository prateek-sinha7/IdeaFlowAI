"""tests/unit/test_concierge_escalation.py — CHAT / D-04 (33-03, Wave 3).

The free-form → Concierge escalation branch in the mechanical router, proven PURE and
OFFLINE. ``route_chat_turn`` gains ONE structural branch (D-04): a turn explicitly
marked free-form (the generic ``ChatTurn.concierge`` marker) that carries NO routable
discriminator classifies to ``CHANNEL_CONCIERGE`` — with ZERO model calls (the router
imports no model and makes no I/O; it is a pure function over ``RunState`` + ``ChatTurn``).

The invariant this suite guards (SC-1 / INV-12): the escalation is ADDITIVE — every
ROUTABLE turn (structured clarify answer, gate action, sticky steering, explicit
revision) STILL resolves to its pre-existing Phase-29 channel unchanged, because it never
sets the ``concierge`` marker. Only the genuinely free-form residual escalates. The
predicate keys ONLY on the generic turn marker + generic discriminators — never a workflow
name / ``pipeline_type`` / ``spec.id`` (SC-001/INV-1).
"""

from __future__ import annotations

from app.api.chat_router import (
    CHANNEL_ANSWERS,
    CHANNEL_CONCIERGE,
    CHANNEL_GATE,
    CHANNEL_REVISION,
    CHANNEL_STEERING,
    ChatTurn,
    RunState,
    route_chat_turn,
)


# ════════════════════════════════════════════════════════════════════════════
# Free-form marker → CHANNEL_CONCIERGE (pure classification, zero model)
# ════════════════════════════════════════════════════════════════════════════
class TestFreeFormEscalates:
    def test_free_form_running_turn_escalates(self):
        d = route_chat_turn(
            RunState(status="running"),
            ChatTurn(text="what is this run doing right now?", concierge=True),
        )
        assert d.channel == CHANNEL_CONCIERGE
        assert d.instruction == "what is this run doing right now?"

    def test_free_form_terminal_turn_escalates(self):
        for s in ("completed", "degraded", "failed", "cancelled", "diverted"):
            d = route_chat_turn(
                RunState(status=s),
                ChatTurn(text="did the build succeed?", concierge=True),
            )
            assert d.channel == CHANNEL_CONCIERGE, s

    def test_free_form_during_gate_pause_escalates(self):
        # A free-form question while paused at a gate reaches the Concierge — the
        # gate stays UNresolved (no action → not a routable gate turn).
        d = route_chat_turn(
            RunState(status="waiting_for_user", open_gate="review", gate_key="r:a"),
            ChatTurn(text="why is it asking me to review?", concierge=True),
        )
        assert d.channel == CHANNEL_CONCIERGE

    def test_free_form_during_clarify_escalates(self):
        d = route_chat_turn(
            RunState(status="waiting_for_user", open_gate="questionnaire"),
            ChatTurn(text="what are you asking me?", concierge=True),
        )
        assert d.channel == CHANNEL_CONCIERGE


# ════════════════════════════════════════════════════════════════════════════
# Routable turns STILL resolve to their existing channel (zero model) — the
# concierge marker never disturbs a routable turn (it is not set on them).
# ════════════════════════════════════════════════════════════════════════════
class TestRoutableTurnsUnaffected:
    def test_structured_clarify_answer_stays_answers(self):
        d = route_chat_turn(
            RunState(status="waiting_for_user", open_gate="questionnaire"),
            ChatTurn(responses=[{"question_id": "q1", "answer": "A"}]),
        )
        assert d.channel == CHANNEL_ANSWERS

    def test_gate_action_stays_gate(self):
        for action in ("approve", "reject", "redo", "update_specs"):
            d = route_chat_turn(
                RunState(status="waiting_for_user", open_gate="review", gate_key="r:a"),
                ChatTurn(action=action),
            )
            assert d.channel == CHANNEL_GATE, action

    def test_sticky_steering_stays_steering(self):
        d = route_chat_turn(
            RunState(status="running"), ChatTurn(text="brand.md", sticky=True)
        )
        assert d.channel == CHANNEL_STEERING

    def test_plain_running_turn_stays_steering(self):
        # Phase-29 default preserved (INV-12): a non-concierge running turn still steers.
        d = route_chat_turn(RunState(status="running"), ChatTurn(text="prefer teal"))
        assert d.channel == CHANNEL_STEERING

    def test_plain_terminal_turn_stays_revision(self):
        # Phase-29 default preserved (INV-12): a non-concierge terminal turn still revises.
        d = route_chat_turn(RunState(status="completed"), ChatTurn(text="v2 please"))
        assert d.channel == CHANNEL_REVISION


# ════════════════════════════════════════════════════════════════════════════
# The concierge marker NEVER overrides a routable discriminator (zero-model
# guarantee): a marked turn that ALSO carries a gate action / structured clarify
# answer stays routable — the mechanical channel wins.
# ════════════════════════════════════════════════════════════════════════════
class TestRoutableDiscriminatorWins:
    def test_marked_gate_action_still_routes_to_gate(self):
        d = route_chat_turn(
            RunState(status="waiting_for_user", open_gate="review", gate_key="r:a"),
            ChatTurn(action="approve", concierge=True),
        )
        assert d.channel == CHANNEL_GATE  # a real gate action is NOT a free-form turn

    def test_marked_structured_clarify_still_routes_to_answers(self):
        d = route_chat_turn(
            RunState(status="waiting_for_user", open_gate="questionnaire"),
            ChatTurn(responses=[{"question_id": "q1", "answer": "A"}], concierge=True),
        )
        assert d.channel == CHANNEL_ANSWERS


# ════════════════════════════════════════════════════════════════════════════
# Zero-model / purity: the router has no model handle — the escalation is a pure
# classification (a Dispatch), not an invocation. Same call is deterministic.
# ════════════════════════════════════════════════════════════════════════════
class TestPureClassification:
    def test_escalation_is_deterministic_pure(self):
        rs = RunState(status="running")
        turn = ChatTurn(text="status?", concierge=True)
        d1 = route_chat_turn(rs, turn)
        d2 = route_chat_turn(rs, turn)
        assert d1.channel == d2.channel == CHANNEL_CONCIERGE
        # No side effect on the inputs (pure): the turn is untouched.
        assert turn.text == "status?" and turn.concierge is True

    def test_router_module_imports_no_model(self):
        # The router is model-free: importing it pulls in no model/runner symbol, so a
        # routable turn can never trigger a model call (D-04 zero-model guarantee).
        import app.api.chat_router as mod

        assert not hasattr(mod, "DeepAgentRunner")
        assert not hasattr(mod, "build_model")
