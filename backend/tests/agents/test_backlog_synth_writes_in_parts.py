"""The Synthesizer writes synthesis.md in parts (run 7ef4faf8).

In one write_file call the whole document ran past the output limit three times and
arrived empty each time.
"""

from agents.execution_engine.engine import compile_for_run


def _synth_prompt() -> str:
    return next(
        s.prompt
        for s in compile_for_run("backlog").steps
        if s.agent_id.endswith(":us-synth")
    )


def test_the_synthesizer_writes_the_first_sections_then_edits_in_the_rest():
    prompt = _synth_prompt()
    assert (
        "1. write_file `synthesis.md` with `## Product`, `## Actors` and `## Screens`."
        in prompt
    )
    assert (
        "2. Add the remaining sections in order, a few at a time: edit_file" in prompt
    )
    assert "well under 8,000 words" in prompt
    assert (
        "1. write_file `synthesis.md`.\n" not in prompt
    )  # the single-call step is gone


def test_the_rest_of_the_synthesizer_prompt_is_unchanged():
    prompt = _synth_prompt()
    for kept in (
        "Phase 4 - Write the doc",
        "Sections, in this order: `## Product`",
        "Phase 5 - Write validate",
        "1. write_file `validate.json` in exactly this layout:",
    ):
        assert kept in prompt
