"""spec 017 — ppt_v2 compiles, and ppt is provably untouched by it.

The pinned-parity test is the load-bearing one: the whole feature is built as a
SEPARATE workflow precisely so the existing deck pipeline cannot regress, and a
claim like that is worth exactly as much as the test behind it.
"""

from __future__ import annotations

import pytest

from agents.execution_engine.engine import compile_for_run
from agents.registry import allowed_custom_agent_ids

_V2_STEPS = ["ppt-brief-analyst", "ppt-composer", "ppt-deck-qa-v2", "ppt-code-generator"]


def test_ppt_v2_compiles_with_the_declared_four_steps():
    compiled = compile_for_run("ppt_v2")
    assert [s.agent_id for s in compiled.steps] == _V2_STEPS


def test_ppt_v2_deliverable_is_sandbox_readback_not_last_streamed():
    """The single decision the whole design rests on.

    `strategy: ppt` resolves to ctx.last_streamed — the LAST step's output — so a
    4th step emitting JavaScript would REPLACE the deck with its own source.
    `single_file` reads a named file back off the sandbox instead, which is immune
    to step order and degrades to the composer's deck if step 4 dies outright.
    """
    compiled = compile_for_run("ppt_v2")
    assert compiled.deliverable.strategy == "single_file"
    assert compiled.deliverable.name == "presentation.html"


def test_ppt_is_byte_identical_to_its_own_manifest():
    """ppt must not have moved. Pinned literally, not compared to ppt_v2."""
    compiled = compile_for_run("ppt")
    assert [s.agent_id for s in compiled.steps] == [
        "ppt-brief-analyst", "ppt-composer", "ppt-validator",
    ]
    assert compiled.deliverable.strategy == "ppt"
    assert compiled.deliverable.name == "presentation.pptx"


def test_only_the_render_tool_may_write_the_pptx():
    """One writer per file (FR-003).

    write_file does not overwrite in deepagents' FilesystemBackend, so two steps
    writing the same name is a silent no-op for the second. Step 4 therefore gets
    read-only filesystem access — the pptx is written by the render_pptx tool,
    which is not a filesystem grant.
    """
    step4 = compile_for_run("ppt_v2").steps[3]
    assert step4.agent_id == "ppt-code-generator"
    assert step4.tools.read_files is True
    assert step4.tools.write_files is False


def test_every_ppt_v2_step_is_launchable_from_the_wizard():
    """FR-010. PIPELINE_AGENTS is derived from each AGENT.md's pipeline_type, so
    the two REUSED ppt agents are absent from ppt_v2's own entry — and a wizard
    launch sends agent_ids for all four steps. Without the own-manifest union in
    allowed_custom_agent_ids, two of the four are rejected invalid_agent_ids.
    """
    allowed = allowed_custom_agent_ids("ppt_v2")
    assert set(_V2_STEPS) <= allowed


@pytest.mark.parametrize("pipeline,expected", [("chat", set()), ("zzz_not_a_pipeline", set())])
def test_the_allow_list_still_fails_closed(pipeline, expected):
    """The own-manifest union must not have widened the security fallback."""
    assert allowed_custom_agent_ids(pipeline) == expected
