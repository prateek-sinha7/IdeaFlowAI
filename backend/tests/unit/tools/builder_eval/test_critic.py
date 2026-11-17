"""Unit tests for the offline critic's code facts (``tools/builder_eval/critic.py``)."""

from __future__ import annotations

from tools.builder_eval.critic import DIMENSIONS, compute_facts

_FULL = "\n".join(
    [
        "WHAT YOU RECEIVE",
        "WHAT YOU NEVER DO",
        "IF INPUT IS MISSING",
        "OUTPUT",
        "CHECK BEFORE YOU REPLY",
        "HOW TO DELIVER",
    ]
)


def test_compute_facts_lists_missing_sections_and_ungated_writes() -> None:
    manifest = {
        "steps": [
            {
                "agent": "custom-agent",
                "instance_id": "draft",
                "prompt": "Write the [Customer Name] email.",
            },
            {
                "agent": "custom-agent",
                "instance_id": "check",
                "prompt": "decide",
                "gates": ["conditional"],
                "route": {"outcomes": {"pass": {}}, "loop_max_iterations": 2},
            },
            {
                "agent": "custom-agent",
                "instance_id": "post",
                "prompt": _FULL,
                "depends_on": ["custom-agent:check"],
                "tools": {"mcp": ["slack.post_message"]},
            },
        ]
    }

    facts = compute_facts(
        manifest, reply="**Assumptions**\n- x", assumptions=["Assumption: x"]
    )

    by_step = {p["step"]: p for p in facts["prompts"]}
    assert by_step["draft"]["missing_sections"] == [
        "WHAT YOU RECEIVE",
        "WHAT YOU NEVER DO",
        "IF INPUT IS MISSING",
        "OUTPUT",
        "CHECK BEFORE YOU REPLY",
        "HOW TO DELIVER",
    ]
    assert (
        by_step["check"]["working"] is False
        and by_step["post"]["missing_sections"] == []
    )
    assert len(facts["irreversible_gate_issues"]) == 1
    assert facts["routes"] == [{"step": "check", "loop_max_iterations": 2}]
    assert facts["placeholder_like_text"] == ["draft: [Customer Name]"]
    assert facts["reply_has_assumptions_block"] is True


def test_dimensions_cover_the_rubric() -> None:
    assert len(DIMENSIONS) == 8 and "answers_changed_manifest" in DIMENSIONS


def test_chunks_keeps_small_manifest_whole_and_never_cuts_prompts() -> None:
    from tools.builder_eval.critic import chunks

    big = "x" * 900
    manifest = {"steps": [{"instance_id": f"s{i}", "prompt": big} for i in range(4)]}

    assert len(chunks(manifest, max_chars=100_000)) == 1
    pieces = chunks(manifest, max_chars=2_000)
    assert len(pieces) == 2
    assert [len(s["prompt"]) for p in pieces for s in p["steps"]] == [
        900,
        900,
        900,
        900,
    ]


def test_aggregate_keeps_the_lowest_score_per_dimension() -> None:
    from tools.builder_eval.critic import _aggregate

    one = {d: {"score": 5, "reason": "fine"} for d in DIMENSIONS}
    two = {**one, "prompt_depth": {"score": 3, "reason": "thin"}}

    merged = _aggregate([one, two])

    assert merged["prompt_depth"] == {"score": 3, "reason": "[part 2/2] thin"}
    assert merged["loop_caps"]["score"] == 5
