"""``pdf_to_prototype`` compiles to the topology it is run on.

Repinned when the wave-based build (formerly ``pdf_to_prototype_v2``) replaced
the original 12-step/17-agent shape and took over the plain id. The old shape is
archived at ``agents/.workflow-archive/pdf_to_prototype_v1`` and is no longer
compiled by anything.

16 declared steps compile to 21 runtime agents: the five readers are dispatched
as subagents of the synthesizer rather than as steps of their own. The 16th
declared step is ``publish`` (A10 STABILIZATION.md item), a mechanical no-model
step that copies the highest ``draft.v*.html`` to ``prototype.html``.
"""

import pytest

from agents.execution_engine.engine import compile_for_run

WORKFLOW = "pdf_to_prototype"

READERS = [f"custom-agent:reader-{n}" for n in range(1, 6)]
SUPERVISOR = "custom-agent:synthesizer"
WAVE_STEPS = [
    "custom-agent:screen-builder",
    "custom-agent:review-workers",
    "custom-agent:review-revision",
]


@pytest.fixture(scope="module")
def compiled():
    return compile_for_run(WORKFLOW)


def _by_id(compiled):
    return {s.id: s for s in compiled.steps}


def test_compiles_to_twenty_one_runtime_agents(compiled):
    """16 declared steps + 5 reader subagents."""
    assert len(compiled.steps) == 21


def test_readers_are_subagents_of_the_synthesizer(compiled):
    """They are dispatched BY the synthesizer, so the serial loop must skip them.

    Without ``dispatched_by`` the engine's own dispatch loop would run each
    reader a second time.
    """
    steps = _by_id(compiled)
    for rid in READERS:
        assert steps[rid].dispatched_by == SUPERVISOR, rid


def test_synthesizer_fans_the_readers_out_in_parallel(compiled):
    assert _by_id(compiled)[SUPERVISOR].strategy == "parallel_group"


def test_the_three_per_screen_steps_are_waves(compiled):
    """Screen build, review and revision each fan out over N screens.

    A wave step has no consolidated reply, so none of these can be a
    ``task_source`` producer or carry a conditional route — hence the separate
    ``review-revision-route`` step that follows the revision wave.
    """
    steps = _by_id(compiled)
    for sid in WAVE_STEPS:
        assert steps[sid].strategy == "wave_scheduler", sid
    assert "custom-agent:review-revision-route" in steps


def test_structure_check_is_the_last_thing_to_touch_the_document(compiled):
    """Nothing may re-run the assembler after structure-check.

    structure-check repairs the assembled document in place; a later assembler
    pass would silently overwrite those fixes with stale fragments.
    """
    ids = [s.id for s in compiled.steps]
    assert ids.index("custom-agent:assembler") < ids.index("custom-agent:structure-check")
    assert "custom-agent:assembler" not in ids[ids.index("custom-agent:structure-check") :]
