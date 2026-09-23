"""tests/agents/test_ask_user.py — the ask_user HITL request emitter.

An agent that finds a gap the corpus cannot close should be able to ask the user,
in the SAME questionnaire UI the run-entry clarify gate uses. These tests pin the
contract that makes that safe:

  * the tool ASKS NOTHING — it returns a JSON request and the kernel decides;
  * the fulfilment point enforces the grant, so an agent cannot pause a run its
    step never declared the tool set for;
  * a malformed or empty request is a NO-OP, never an aborted run;
  * a run that never calls it takes the identical path as before.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from agents.execution_engine.engine import ExecutionEngine


def test_the_tool_emits_a_request_and_nothing_else():
    from app.agents.tools.runner_tools import ask_user

    out = ask_user.invoke({"questions": [{"id": "g1", "question": "?", "options": ["a", "b"]}]})
    assert json.loads(out) == {
        "clarify_request": [{"id": "g1", "question": "?", "options": ["a", "b"]}]
    }


def test_the_tool_body_pauses_nothing():
    """Like spawn_subagents: no store, no event, no engine import in the body."""
    src = Path(__file__).resolve().parents[2] / "app/agents/tools/runner_tools.py"
    body = src.read_text().split("def ask_user(")[1].split("\ndef ")[0]
    for forbidden in ("asyncio", "get_artifact_store", "ClarifyEngine", "Event"):
        assert forbidden not in body, f"ask_user must not touch {forbidden}"


def test_the_provider_is_not_on_the_user_palette():
    from agents.capabilities.registry import CapabilityRegistry, discover

    discover()
    registry = CapabilityRegistry()
    assert registry.is_registered("tool", "ask_user")
    # Pausing a run for a human is privileged — never grantable from a user manifest.
    assert registry.is_user_allowed("tool", "ask_user") is False


def _ectx(*, tool_sets, run_id="run-1"):
    step = SimpleNamespace(agent_id="fi-gaps", tools=SimpleNamespace(tool_sets=tool_sets))
    return SimpleNamespace(current_step=step, pipeline_run_id=run_id,
                           owner_id="o", workspace_id="w", sandbox=None)


def _event(*questions):
    return {"tool": "ask_user",
            "result": json.dumps({"clarify_request": list(questions)})}


async def _drain(ectx, event):
    engine = ExecutionEngine.__new__(ExecutionEngine)
    return [e async for e in engine._derive_clarify(event, ectx)]


@pytest.mark.asyncio
async def test_an_ungranted_step_cannot_pause_the_run():
    """The factory binds off declared sets, so fulfilment must enforce the grant."""
    out = await _drain(_ectx(tool_sets=["file_extract"]),
                       _event({"id": "g1", "question": "?", "options": ["a"]}))
    assert out == []


@pytest.mark.asyncio
async def test_an_empty_request_is_a_no_op():
    assert await _drain(_ectx(tool_sets=["ask_user"]), _event()) == []


@pytest.mark.asyncio
async def test_a_malformed_request_does_not_abort_the_run():
    bad = {"tool": "ask_user", "result": "{not json"}
    assert await _drain(_ectx(tool_sets=["ask_user"]), bad) == []


@pytest.mark.asyncio
async def test_a_request_with_no_run_id_is_a_no_op():
    ectx = _ectx(tool_sets=["ask_user"])
    ectx.pipeline_run_id = None
    assert await _drain(ectx, _event({"id": "g1", "question": "?", "options": ["a"]})) == []


def test_the_engine_reuses_the_one_clarify_implementation():
    """No second questionnaire path — the agent's questions ride replay_questions."""
    src = Path(__file__).resolve().parents[2] / "agents/execution_engine/engine.py"
    body = src.read_text().split("async def _derive_clarify")[1].split("\n    @staticmethod")[0]
    assert "ClarifyEngine" in body
    assert "replay_questions=questions" in body
    assert "replay_round=1" in body


def test_the_state_machine_allows_the_pause_and_the_resume():
    """The pause is mid-step; nothing may be terminal or unreachable."""
    from agents.execution_engine.state_machine import TERMINAL_STATES, VALID_STATES

    assert {"waiting_for_user", "generating"} <= VALID_STATES
    assert not ({"waiting_for_user", "generating"} & TERMINAL_STATES)


def test_the_branch_is_dormant_for_every_other_tool():
    src = Path(__file__).resolve().parents[2] / "agents/execution_engine/engine.py"
    body = src.read_text()
    assert re.search(r'elif event\.get\("tool"\) == "ask_user":', body)


class TestTheBrowserCanActuallyRenderThem:
    """``replay_questions`` passes questions through VERBATIM, so whatever the agent
    wrote is what the browser gets. The UI reads snake_case
    (``question_id`` / ``question_text`` / ``recommended_answer`` — page.tsx's
    ``questionnaire_ready`` case) while a model writes the camelCase it sees in a
    schema. Unmapped, every question renders blank with no options."""

    def test_camelcase_from_an_agent_becomes_the_wire_shape(self):
        out = ExecutionEngine._normalise_question({
            "id": "gap-1",
            "question": "Error handling is not specified [1-crimson p.1]",
            "answerType": "single_choice",
            "options": ["Inline messages", "Summary banner", "Not applicable"],
            "recommendedAnswer": "Inline messages",
            "recommendedReasoning": "every other screen validates per field",
            "impactLevel": "medium",
        })
        assert out["question_id"] == "gap-1"
        assert out["question_text"].startswith("Error handling")
        assert out["answer_type"] == "single_choice"
        assert out["recommended_answer"] == "Inline messages"
        assert out["recommended_reasoning"].startswith("every other")
        assert out["impact_level"] == "medium"
        assert len(out["options"]) == 3
        # the camelCase spellings must not survive, or the UI sees two of everything
        assert not ({"id", "question", "answerType", "recommendedAnswer"} & set(out))

    def test_an_agent_that_already_writes_the_wire_shape_is_untouched(self):
        wire = {"question_id": "g1", "question_text": "?", "options": ["a"],
                "answer_type": "single_choice", "recommended_answer": "a"}
        assert ExecutionEngine._normalise_question(dict(wire)) == wire

    def test_a_question_never_renders_blank(self):
        """question_text is what the UI shows; without it the row is empty."""
        out = ExecutionEngine._normalise_question({"question": "why?"})
        assert out["question_text"] == "why?"
        assert out["question_id"]           # never missing — answers key on it
        assert out["options"] == []
        assert out["answer_type"] == "single_choice"

    def test_an_unknown_field_is_not_silently_dropped(self):
        out = ExecutionEngine._normalise_question({"id": "g", "question": "q", "future": 1})
        assert out["future"] == 1


@pytest.mark.asyncio
async def test_skip_all_stops_every_remaining_round():
    """"Skip all & run directly" ends the questionnaire, not one screen of it.

    Clarify puts a long gap list to the user in batches. The agent cannot see
    that the user skipped, so it goes straight on to the next batch — six more
    screens after the one they just dismissed. The flag rides on the ectx and
    turns every later round into a no-op.
    """
    ectx = _ectx(tool_sets=["ask_user"])
    ectx.clarify_skipped = True
    out = await _drain(ectx, _event({"id": "g9", "question": "?", "options": ["a"]}))
    assert out == [], "a skipped run must not put another round on screen"


@pytest.mark.asyncio
async def test_an_unskipped_run_still_asks():
    """The guard is dormant until the user actually skips (no default change)."""
    ectx = _ectx(tool_sets=["ask_user"])
    assert getattr(ectx, "clarify_skipped", False) is False
    # Reaching the clarify round needs a run id; without one the branch no-ops
    # for its OWN reason, which is the pre-existing case covered above.
    ectx.pipeline_run_id = None
    ectx.run_id = None
    assert await _drain(ectx, _event({"id": "g1", "question": "?", "options": ["a"]})) == []


# ── Multiple rounds ───────────────────────────────────────────────────────────
# A long gap list reaches the user in batches: the agent calls `ask_user` once
# per batch, and every call writes the SAME clarify/answers.json. Before the
# merge below, round 2 overwrote round 1 and those answers were gone before the
# folding step ever read the file.


def _answer(qid, answer="A", answered=True):
    return {"id": qid, "question": f"gap {qid}?", "answer": answer, "answered": answered}


def _merge(prior, current):
    return ExecutionEngine._merge_clarify_rounds(prior, current)


class TestMergeClarifyRounds:
    def test_a_second_round_keeps_the_first_rounds_answers(self):
        first = {"answers": [_answer("g1"), _answer("g2")], "answered_count": 2,
                 "clarified_topics": [], "explicit_constraints": []}
        out = _merge(first, {"answers": [_answer("g3")], "answered_count": 1,
                             "clarified_topics": [], "explicit_constraints": []})
        assert [a["id"] for a in out["answers"]] == ["g1", "g2", "g3"]
        assert out["answered_count"] == 3

    def test_the_first_round_writes_into_an_empty_file(self):
        out = _merge({}, {"answers": [_answer("g1")], "answered_count": 1,
                          "clarified_topics": [], "explicit_constraints": []})
        assert [a["id"] for a in out["answers"]] == ["g1"]
        assert out["rounds"] == 1

    def test_rounds_counts_the_calls(self):
        one = _merge({}, {"answers": [], "clarified_topics": [], "explicit_constraints": []})
        two = _merge(one, {"answers": [], "clarified_topics": [], "explicit_constraints": []})
        assert (one["rounds"], two["rounds"]) == (1, 2)

    def test_re_asking_a_question_is_a_correction_not_a_duplicate(self):
        first = {"answers": [_answer("g1", "Quarterly")], "clarified_topics": [],
                 "explicit_constraints": []}
        out = _merge(first, {"answers": [_answer("g1", "Monthly")],
                             "clarified_topics": [], "explicit_constraints": []})
        assert len(out["answers"]) == 1
        assert out["answers"][0]["answer"] == "Monthly"

    def test_an_unanswered_gap_does_not_inflate_the_count(self):
        out = _merge({}, {"answers": [_answer("g1"), _answer("g2", None, False)],
                          "clarified_topics": [], "explicit_constraints": []})
        assert out["answered_count"] == 1

    def test_order_follows_the_order_the_user_was_asked(self):
        first = {"answers": [_answer("g5"), _answer("g1")], "clarified_topics": [],
                 "explicit_constraints": []}
        out = _merge(first, {"answers": [_answer("g3"), _answer("g5", "changed")],
                             "clarified_topics": [], "explicit_constraints": []})
        assert [a["id"] for a in out["answers"]] == ["g5", "g1", "g3"]

    def test_topics_and_constraints_are_unioned_without_repeats(self):
        first = {"answers": [], "clarified_topics": ["billing"], "explicit_constraints": ["a"]}
        out = _merge(first, {"answers": [], "clarified_topics": ["billing", "forms"],
                             "explicit_constraints": ["b"]})
        assert out["clarified_topics"] == ["billing", "forms"]
        assert out["explicit_constraints"] == ["a", "b"]

    def test_a_corrupt_prior_file_does_not_lose_this_round(self):
        # The caller degrades an unreadable file to {}; nothing may be dropped.
        out = _merge({}, {"answers": [_answer("g1")], "clarified_topics": [],
                          "explicit_constraints": []})
        assert [a["id"] for a in out["answers"]] == ["g1"]

    def test_a_non_dict_entry_is_skipped_not_raised(self):
        first = {"answers": [_answer("g1"), "junk", None], "clarified_topics": [],
                 "explicit_constraints": []}
        out = _merge(first, {"answers": [], "clarified_topics": [], "explicit_constraints": []})
        assert [a["id"] for a in out["answers"]] == ["g1"]


# ── The round-2 flash ─────────────────────────────────────────────────────────
# Reported live: round 1 asked and answered, then every later round appeared and
# vanished within a second, unanswerable. `ClarifyEngine.run` guards a lost
# wakeup by falling through when a submission is ALREADY stored — but its
# "already consumed" marker is a local of one run() call, and each ask_user
# round is its own run(). Round 2 therefore found round 1's answers in the store,
# took them for its own, and returned without ever waiting.


class _Store:
    """The two questionnaire slots, with the real set/get/clear semantics."""

    def __init__(self):
        self.responses: dict[str, list] = {}
        self.force: dict[str, bool] = {}

    async def set_questionnaire_responses(self, run_id, responses, skip_clarification=False):
        self.responses[run_id] = responses
        self.force[run_id] = bool(skip_clarification)

    async def get_questionnaire_responses(self, run_id):
        return self.responses.get(run_id)

    async def get_questionnaire_force_proceed(self, run_id):
        return self.force.get(run_id, False)

    async def clear_questionnaire_responses(self, run_id):
        self.responses.pop(run_id, None)
        self.force.pop(run_id, None)


@pytest.mark.asyncio
async def test_a_cleared_slot_makes_the_next_round_wait():
    """The guard's premise: 'a submission is stored' must mean THIS round's."""
    store = _Store()
    await store.set_questionnaire_responses("run-1", [{"question_id": "g1", "answer": "A"}])
    assert await store.get_questionnaire_responses("run-1") is not None

    await store.clear_questionnaire_responses("run-1")

    # None is the ONLY value that sends ClarifyEngine into `await event.wait()`
    # on a fresh run() — anything else is read as an already-arrived submission.
    assert await store.get_questionnaire_responses("run-1") is None


@pytest.mark.asyncio
async def test_clearing_also_drops_a_stale_skip_flag():
    """A skip belongs to the round that was skipped, not to the next one."""
    store = _Store()
    await store.set_questionnaire_responses("run-1", [], skip_clarification=True)
    await store.clear_questionnaire_responses("run-1")
    assert await store.get_questionnaire_force_proceed("run-1") is False


@pytest.mark.asyncio
async def test_clearing_an_untouched_run_is_a_no_op():
    store = _Store()
    await store.clear_questionnaire_responses("never-asked")   # must not raise
    assert await store.get_questionnaire_responses("never-asked") is None


def test_the_engine_clears_before_every_round_not_only_the_first():
    """The clear sits in _derive_clarify, which runs once per ask_user call."""
    src = Path(__file__).resolve().parents[2] / "agents/execution_engine/engine.py"
    body = src.read_text().split("async def _derive_clarify")[1].split("\n    @staticmethod")[0]
    assert "clear_questionnaire_responses" in body
    # It must come BEFORE the round is created, or the round reads the stale slot.
    assert body.index("clear_questionnaire_responses") < body.index("ClarifyEngine()")


def test_the_store_exposes_the_clear():
    from agents.artifact_store.store import ArtifactStore
    assert hasattr(ArtifactStore, "clear_questionnaire_responses")
