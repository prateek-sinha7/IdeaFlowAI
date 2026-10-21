"""tests/agents/test_backlog_target_clarify.py

Pins the contract introduced by the Target System Clarify stage (us-target-clarify)
added as the first step in the Backlog workflow.

What is tested here (unit-layer — no DB, no LLM, no network):

  Manifest contract
  -----------------
  * us-target-clarify is the FIRST step in the compiled plan.
  * It declares ask_user in its tool_sets (the gate for the pause-and-resume path).
  * It produces .clarify/target.json and clarify/answers.json.
  * It consumes nothing (runs before any prototype extraction).
  * It has no gate validators (it is purely a human-pause step).
  * us-ui-extract (the old first step) now depends on us-target-clarify.
  * No other step has an empty depends_on (the target-clarify gates everything).

  Question contract
  -----------------
  * The compiled prompt contains exactly the six required target-N question ids.
  * The six question ids are exactly target-1 … target-6 and no others.
  * Every required option surface is present in the prompt text.

  clarify/answers.json accumulation
  ----------------------------------
  * Answers from the first round (target questions) survive a second round
    (_merge_clarify_rounds is already tested in test_ask_user.py; here we test
    that the target-N ids are treated the same as any other id by the merger).

  us-solution downstream wiring
  --------------------------------
  * us-solution now lists .clarify/target.json and clarify/answers.json in its
    consumes list.
  * us-solution's compiled prompt instructs the agent to read both files.
  * The citation token [user target-N] is present in the prompt text.
"""

from __future__ import annotations

import re

import pytest

from agents.execution_engine.engine import ExecutionEngine, compile_for_run

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_COMPILED = None  # cached once per session — compile_for_run is side-effect-free


def _plan():
    global _COMPILED  # noqa: PLW0603
    if _COMPILED is None:
        _COMPILED = compile_for_run("backlog")
    return _COMPILED


def _step(instance_suffix: str):
    """Return the first compiled step whose agent_id ends with ``:<instance_suffix>``."""
    return next(
        (s for s in _plan().steps if s.agent_id.endswith(f":{instance_suffix}")),
        None,
    )


# ---------------------------------------------------------------------------
# Manifest contract — step ordering and wiring
# ---------------------------------------------------------------------------


class TestManifestContract:
    def test_us_target_clarify_is_the_first_step(self):
        # Arrange / Act
        first_step = _plan().steps[0]
        # Assert
        assert first_step.agent_id.endswith(":us-target-clarify"), (
            f"Expected first step to be us-target-clarify, "
            f"got {first_step.agent_id!r}"
        )

    def test_us_target_clarify_declares_ask_user_tool_set(self):
        # Arrange
        step = _step("us-target-clarify")
        assert step is not None, "us-target-clarify step not found in compiled plan"
        # Act
        tool_sets = step.tools.tool_sets
        # Assert
        assert "ask_user" in tool_sets, (
            f"us-target-clarify must declare ask_user in tool_sets; got {tool_sets!r}"
        )

    def test_us_target_clarify_produces_target_clarify_json(self):
        step = _step("us-target-clarify")
        assert step is not None
        assert ".clarify/target.json" in step.produces

    def test_us_target_clarify_produces_clarify_answers_json(self):
        step = _step("us-target-clarify")
        assert step is not None
        assert "clarify/answers.json" in step.produces

    def test_us_target_clarify_consumes_nothing(self):
        # It must fire before any reading or extraction — no inputs.
        step = _step("us-target-clarify")
        assert step is not None
        assert step.consumes == [], (
            f"us-target-clarify should consume nothing; got {step.consumes!r}"
        )

    def test_us_target_clarify_has_no_gate_validators(self):
        # It is a HITL pause step, not a validation gate.
        step = _step("us-target-clarify")
        assert step is not None
        assert step.gates == [], (
            f"us-target-clarify must have no gates; got {step.gates!r}"
        )

    def test_us_target_clarify_has_no_depends_on(self):
        # Must start immediately when the run launches.
        step = _step("us-target-clarify")
        assert step is not None
        assert step.depends_on == [], (
            f"us-target-clarify must have no depends_on; got {step.depends_on!r}"
        )

    def test_us_ui_extract_depends_on_us_target_clarify(self):
        # The old first step is now gated behind the clarify step.
        step = _step("us-ui-extract")
        assert step is not None, "us-ui-extract step not found in compiled plan"
        dep_ids = step.depends_on
        assert any("us-target-clarify" in d for d in dep_ids), (
            f"us-ui-extract must depend on us-target-clarify; got depends_on={dep_ids!r}"
        )

    def test_only_us_target_clarify_has_empty_depends_on(self):
        # No other step should start unconditionally — every other step must
        # transitively wait for the user to answer the target-system questions.
        independent_steps = [
            s.agent_id
            for s in _plan().steps
            if s.depends_on == [] and not s.agent_id.endswith(":us-target-clarify")
        ]
        assert independent_steps == [], (
            f"Steps other than us-target-clarify must not have empty depends_on; "
            f"found: {independent_steps!r}"
        )


# ---------------------------------------------------------------------------
# Question contract — the six required questions are in the prompt
# ---------------------------------------------------------------------------

_REQUIRED_IDS = [f"target-{n}" for n in range(1, 7)]

_REQUIRED_OPTION_FRAGMENTS = [
    # target-1 architecture options
    "Monolith web application",
    "Microservices",
    "Serverless",
    # target-2 backend options
    "Spring Boot",
    "Node.js",
    ".NET Core",
    "Django",
    # target-3 frontend options
    "React",
    "Angular",
    "Vue.js",
    "Next.js",
    # target-4 database options
    "PostgreSQL",
    "MySQL",
    "MongoDB",
    # target-5 deployment options
    "AWS",
    "Azure",
    "Google Cloud",
    # target-6 project type options
    "greenfield",
    "Migration",
    "Augmentation",
    "Proof-of-concept",
]


class TestQuestionContract:
    @pytest.fixture(scope="class")
    def prompt_text(self):
        step = _step("us-target-clarify")
        assert step is not None
        return step.prompt

    def test_prompt_contains_all_six_question_ids(self, prompt_text):
        for qid in _REQUIRED_IDS:
            assert qid in prompt_text, (
                f"Required question id {qid!r} not found in us-target-clarify prompt"
            )

    def test_prompt_contains_no_other_target_n_ids(self, prompt_text):
        # target-7 or above would indicate a drift from the spec.
        extra = re.findall(r"target-(\d+)", prompt_text)
        ids_found = {f"target-{n}" for n in extra}
        unexpected = ids_found - set(_REQUIRED_IDS)
        assert not unexpected, (
            f"Unexpected target-N ids found in prompt: {unexpected!r}"
        )

    @pytest.mark.parametrize("fragment", _REQUIRED_OPTION_FRAGMENTS)
    def test_prompt_contains_required_option_text(self, prompt_text, fragment):
        assert fragment in prompt_text, (
            f"Required option text {fragment!r} not found in us-target-clarify prompt"
        )

    def test_prompt_instructs_single_ask_user_call(self, prompt_text):
        # The spec requires exactly ONE ask_user call — the prompt must say so.
        assert "ask_user" in prompt_text
        assert "ONCE" in prompt_text

    def test_prompt_instructs_write_target_clarify_json(self, prompt_text):
        assert ".clarify/target.json" in prompt_text

    def test_prompt_instructs_write_in_phases(self, prompt_text):
        # The four-phase structure is enforced by the backlog clarify convention.
        for phase in ("Phase 1", "Phase 2", "Phase 3"):
            assert phase in prompt_text, (
                f"Expected {phase!r} section in us-target-clarify prompt"
            )


# ---------------------------------------------------------------------------
# question normalisation — target-N ids pass through _normalise_question intact
# ---------------------------------------------------------------------------


class TestNormalisationOfTargetQuestions:
    """Target questions use the same camelCase schema as every other clarify step.
    _normalise_question maps them to the wire shape the frontend reads.
    """

    def test_target_question_camelcase_normalises_to_wire_shape(self):
        out = ExecutionEngine._normalise_question(
            {
                "id": "target-1",
                "question": "What is the target system architecture?",
                "answerType": "single_choice",
                "options": [
                    "Monolith web application",
                    "Microservices",
                    "No preference — Architect decides",
                ],
                "recommendedAnswer": "Monolith web application",
                "recommendedReasoning": "Monolith is the pragmatic default.",
                "impactLevel": "high",
            }
        )
        assert out["question_id"] == "target-1"
        assert out["question_text"] == "What is the target system architecture?"
        assert out["answer_type"] == "single_choice"
        assert out["recommended_answer"] == "Monolith web application"
        assert out["recommended_reasoning"] == "Monolith is the pragmatic default."
        assert out["impact_level"] == "high"
        assert len(out["options"]) == 3
        # camelCase keys must not survive (UI would render blank otherwise)
        assert not ({"id", "question", "answerType", "recommendedAnswer"} & set(out))

    def test_all_six_target_question_ids_are_valid_question_ids(self):
        for qid in _REQUIRED_IDS:
            out = ExecutionEngine._normalise_question(
                {
                    "id": qid,
                    "question": f"Question for {qid}",
                    "options": ["A", "B"],
                }
            )
            assert out["question_id"] == qid, (
                f"question_id should be {qid!r}; got {out['question_id']!r}"
            )


# ---------------------------------------------------------------------------
# clarify/answers.json accumulation — target-N answers survive a second round
# ---------------------------------------------------------------------------


def _answer(qid: str, answer: str = "A", answered: bool = True) -> dict:
    return {
        "id": qid,
        "question": f"Question for {qid}?",
        "answer": answer,
        "answered": answered,
    }


def _merge(prior: dict, current: dict) -> dict:
    return ExecutionEngine._merge_clarify_rounds(prior, current)


class TestClarifyAnswersAccumulation:
    """Target-system answers written in round 0 must survive every later round.

    This mirrors the round-merge tests in test_ask_user.py but uses real
    target-N ids to pin the specific accumulation behaviour for this feature.
    """

    def test_target_answers_survive_a_subsequent_solution_clarify_round(self):
        # Arrange: round 0 wrote target answers.
        round_0 = {
            "answers": [_answer("target-1", "Monolith web application")],
            "answered_count": 1,
            "clarified_topics": [],
            "explicit_constraints": [],
        }
        # Act: round 1 (e.g. us-gaps) writes gap-N answers.
        round_1 = {
            "answers": [_answer("gap-1", "Inline messages")],
            "answered_count": 1,
            "clarified_topics": [],
            "explicit_constraints": [],
        }
        merged = _merge(round_0, round_1)
        # Assert
        ids = [a["id"] for a in merged["answers"]]
        assert "target-1" in ids, "target-1 must survive after a second clarify round"
        assert "gap-1" in ids
        assert merged["answered_count"] == 2

    def test_all_six_target_answers_survive_three_further_rounds(self):
        # Arrange: round 0 with all six target answers.
        target_answers = [
            _answer(qid, f"answer-{qid}") for qid in _REQUIRED_IDS
        ]
        state = {
            "answers": target_answers,
            "answered_count": 6,
            "clarified_topics": [],
            "explicit_constraints": [],
        }
        # Act: simulate three downstream clarify rounds (solution, api, architect).
        for round_name in ("gap-1", "api-1", "arch-1"):
            state = _merge(
                state,
                {
                    "answers": [_answer(round_name, "some-answer")],
                    "answered_count": 1,
                    "clarified_topics": [],
                    "explicit_constraints": [],
                },
            )
        # Assert: all six target answers are still present.
        ids = {a["id"] for a in state["answers"]}
        for qid in _REQUIRED_IDS:
            assert qid in ids, (
                f"{qid} must still be in clarify/answers.json after three downstream rounds"
            )

    def test_a_corrected_target_answer_replaces_the_original(self):
        # An architect may change a target choice mid-run (re-ask with same id).
        first = {
            "answers": [_answer("target-2", "Spring Boot / Java")],
            "clarified_topics": [],
            "explicit_constraints": [],
        }
        correction = {
            "answers": [_answer("target-2", "Node.js (Express or NestJS)")],
            "clarified_topics": [],
            "explicit_constraints": [],
        }
        merged = _merge(first, correction)
        target_2 = next(a for a in merged["answers"] if a["id"] == "target-2")
        assert target_2["answer"] == "Node.js (Express or NestJS)"
        assert len([a for a in merged["answers"] if a["id"] == "target-2"]) == 1

    def test_unanswered_target_question_does_not_inflate_count(self):
        state = _merge(
            {},
            {
                "answers": [
                    _answer("target-1", "Monolith web application"),
                    _answer("target-2", None, answered=False),
                ],
                "clarified_topics": [],
                "explicit_constraints": [],
            },
        )
        assert state["answered_count"] == 1


# ---------------------------------------------------------------------------
# us-solution downstream wiring
# ---------------------------------------------------------------------------


class TestSolutionAnalystWiring:
    """us-solution must receive the target context so the solution model
    (platform.json, nfrs.json) is built for the TARGET stack, not the source.
    """

    @pytest.fixture(scope="class")
    def solution_step(self):
        step = _step("us-solution")
        assert step is not None, "us-solution step not found in compiled plan"
        return step

    def test_us_solution_consumes_target_clarify_json(self, solution_step):
        assert ".clarify/target.json" in solution_step.consumes, (
            "us-solution must consume .clarify/target.json so the Solution Analyst "
            "reads the user's target stack choices"
        )

    def test_us_solution_consumes_clarify_answers_json(self, solution_step):
        assert "clarify/answers.json" in solution_step.consumes, (
            "us-solution must consume clarify/answers.json to access target-N answers"
        )

    def test_us_solution_prompt_instructs_reading_target_clarify_json(
        self, solution_step
    ):
        assert ".clarify/target.json" in solution_step.prompt

    def test_us_solution_prompt_instructs_reading_clarify_answers_json(
        self, solution_step
    ):
        assert "clarify/answers.json" in solution_step.prompt

    def test_us_solution_prompt_contains_target_n_citation_pattern(
        self, solution_step
    ):
        # The prompt must teach the agent to cite target answers as [user target-N].
        assert "[user target-N]" in solution_step.prompt, (
            "us-solution prompt must contain the [user target-N] citation token "
            "so the agent attributes target-stack items to the user's answer"
        )
