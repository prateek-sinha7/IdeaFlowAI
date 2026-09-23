"""QA-PS-028 — a compiling/aggregation agent can silently drop upstream content
without the run's terminal status ever reflecting it.

Cards:

  * ISS-730 (root, reproduced) — ``backlog-compiler`` (step 6/6 of ``user_stories``)
    reads all prior ``.agents/NN-*.md`` outputs and compiles the final
    ``user_stories.md`` deliverable. Live evidence (run ``e2903536`` in
    BUGS.md#qa-ps-028, plus two independently-observed DB cycles on ISS-730's own
    card) shows an entire epic vanishing from the compiled output with zero trace
    in the compiler's own "Total Epics" summary or in ``pipeline_complete``. The
    engine's shared terminal-completion gate (``_execute_impl``,
    ``engine.py:7376-7457`` — the SAME block ISS-721 root-causes for the sibling
    QA-PS-027) only flips ``status`` to ``"degraded"`` on an unrecovered agent
    failure, a budget-cap degrade, or a blocked commit — never on a compiling
    step's output silently omitting content it read. ``test_compiler_content_drop_leaves_run_completed``
    drives the REAL ``user_stories`` pipeline end-to-end offline (scripted model,
    zero Bedrock cost) with ``epic-architect`` producing an "SDK Integration
    Layer" epic and ``backlog-compiler`` omitting it while still reporting
    "Total Epics: 3" — mirroring the live evidence shape exactly — and asserts
    the terminal event flags the drop. It does not today.

  * ISS-772 (inferred sibling, not reproduced live) — the three
    ``*-sdlc-governance`` final-synthesis agents (``app_builder``,
    ``dotnet_to_azure``, ``mulesoft_to_springboot``) share backlog-compiler's
    exact prompt shape: a final step told to ``read_file`` N upstream
    ``.agents/*.md`` files with only a soft "cover everything" instruction and
    no structural requirement to enumerate what it read against what it wrote.
    ``test_sdlc_governance_agents_lack_completeness_checklist`` pins that gap
    directly against the three ``AGENT.md`` bodies.

  * ISS-773 (inferred sibling, not reproduced live) — ``user_stories_revision``'s
    single step, ``user-story-revision-agent``, is contracted to "PRESERVE every
    other epic, story... exactly as-is" and to "Update the Backlog Summary
    section... with correct totals" against whatever ``user_stories.md`` was
    seeded — with no instruction to check whether the seeded backlog was itself
    already short a QA-PS-028-dropped epic before recomputing those totals.
    ``test_revision_agent_recomputes_totals_with_no_completeness_check`` pins
    that gap directly against its ``AGENT.md`` body.
"""

from __future__ import annotations

import re
from unittest.mock import patch

import pytest

from tests.agents import _scripted_model as _sm
from tests.agents._scripted_model import _ScriptedTurn, _drive

import agents.execution_engine.engine as engine_mod
from agents.execution_engine.finalization import FinalizationRecord
from agents.loader import load_agent_spec


def _clean_finalizer():
    """Stub ``finalize_terminal_run`` to always report a clean finalization —
    isolating the completion GATE's own content-drop blindness (the thing
    ISS-730 targets, `engine.py:7376-7457`) from the harness's unrelated
    finalizer noise (the offline run id is not a real UUID, so the REAL
    finalizer's git-ref step fails and falls back to a sentinel
    ``published_status="degraded"`` record regardless of content — that
    fallback would make this test pass for the wrong reason). Same recipe
    ``test_pipeline_complete_status_v3.py`` uses to control the finalizer
    input independently of the engine's own completion-gate decision.
    """

    async def _finalize(run_id, ectx, *, candidate_status="completed"):
        return FinalizationRecord(
            run_id=run_id,
            owner_id="harness-user",
            workspace_id="",
            published_status="completed",
            candidate_status=candidate_status,
        )

    return _finalize

_PIPELINE = "user_stories"

# The dropped epic's content, mirroring the live evidence shape in BUGS.md#qa-ps-028
# (epic-architect produced an "SDK Integration Layer" epic that backlog-compiler's
# final output never mentioned).
_DROPPED_EPIC_HEADING = "SDK Integration Layer"


def _content_drop_scripts_for(agent_id: str) -> list[_ScriptedTurn]:
    """``epic-architect`` produces 3 epics including the one that gets dropped;
    ``backlog-compiler`` compiles only 2 of them into the final deliverable but
    reports a "Total Epics" count that matches only what it kept — the exact
    shape ISS-730's live evidence describes (run e2903536: "Total Epics: 4,
    Total Stories: 18" matched only what shipped, gave no indication one
    epic was missing). Every other step gets the harness's generic default
    text (irrelevant to this defect)."""
    if agent_id == "epic-architect":
        return [
            _ScriptedTurn(
                texts=[
                    "# Epic: Core Authentication [P0]\n"
                    "## Story: Login flow\n\n"
                    "# Epic: Token Management [P0]\n"
                    "## Story: Refresh tokens\n\n"
                    f"# Epic: {_DROPPED_EPIC_HEADING} [P1]\n"
                    "## Story: Node.js SDK\n"
                    "## Story: Mobile SDK\n"
                ],
                usage=(50, 40),
            )
        ]
    if agent_id == "backlog-compiler":
        return [
            _ScriptedTurn(
                texts=[
                    "I'll compile all the agent outputs.\n\n"
                    "# Epic: Core Authentication [P0]\n"
                    "## Story: Login flow\n\n"
                    "# Epic: Token Management [P0]\n"
                    "## Story: Refresh tokens\n\n"
                    "## Backlog Summary\n"
                    "**Total Epics:** 2\n"
                    "**Total Stories:** 2\n"
                ],
                usage=(30, 25),
            )
        ]
    return [_ScriptedTurn(texts=[f"{agent_id} default output."], usage=(5, 3))]


@pytest.mark.issue("ISS-730")
@pytest.mark.asyncio
async def test_compiler_content_drop_leaves_run_completed():
    """The compiled deliverable is missing an epic epic-architect produced, and
    the compiler's own summary count matches only what it kept — the terminal
    ``pipeline_complete`` event must flag the run as incomplete, not report a
    clean completion."""
    orig_scripts_for = _sm._scripts_for
    _sm._scripts_for = _content_drop_scripts_for
    try:
        with patch.object(engine_mod, "finalize_terminal_run", _clean_finalizer()):
            events = await _drive(_PIPELINE)
    finally:
        _sm._scripts_for = orig_scripts_for

    completes = [e for e in events if e.get("type") == "pipeline_complete"]
    assert len(completes) == 1, f"expected exactly 1 pipeline_complete, got {completes}"
    data = completes[0]["data"]

    final_output = data.get("final_output") or ""
    # Sanity check the fixture actually reproduces the drop: the epic
    # epic-architect produced must be absent from the final compiled output.
    assert _DROPPED_EPIC_HEADING not in final_output, (
        "fixture did not reproduce the drop — the dropped epic heading is "
        f"present in final_output: {final_output!r}"
    )

    # The load-bearing assertion (ISS-730's expected behaviour): a compiled
    # deliverable that silently omits content read from an upstream agent must
    # not be reported as a clean "completed" run.
    assert data.get("status") == "degraded", (
        "backlog-compiler dropped an upstream epic with no trace in its own "
        "summary count, yet pipeline_complete carries no 'status' key (defaults "
        f"to completed): {data}"
    )


@pytest.mark.issue("ISS-772")
def test_sdlc_governance_agents_lack_completeness_checklist():
    """Each ``*-sdlc-governance`` final-synthesis agent must require itself to
    enumerate the upstream items it read and cross-check that list against what
    it wrote — a structural completeness contract, not just a prose "cover
    everything" instruction. None of the three carries one today."""
    agent_ids = ["app-sdlc-governance", "dotnet-sdlc-governance", "mulesoft-sdlc-governance"]
    # A structural self-check names BOTH the enumeration step and a check that
    # ties count/coverage back to what was actually read (e.g. "list every ADR
    # source read... the count MUST match").
    checklist_pattern = re.compile(
        r"(?i)(list|enumerate).{0,80}(read|source).{0,120}(must|before writing|match)"
    )
    missing = []
    for agent_id in agent_ids:
        body = load_agent_spec(agent_id).prompt_body
        if not checklist_pattern.search(body):
            missing.append(agent_id)

    assert not missing, (
        "these governance agents have no structural completeness checklist "
        f"requiring them to account for every upstream item read: {missing}"
    )


@pytest.mark.issue("ISS-773")
def test_revision_agent_recomputes_totals_with_no_completeness_check():
    """``user-story-revision-agent`` recomputes the Backlog Summary totals
    against whatever ``user_stories.md`` was seeded, with no instruction to
    verify the seeded backlog was complete before trusting it — so a
    QA-PS-028-truncated parent propagates with no new signal at the revision
    layer either."""
    body = load_agent_spec("user-story-revision-agent").prompt_body

    assert "Update the Backlog Summary section" in body, (
        "fixture assumption broken — the agent no longer recomputes totals; "
        "re-check ISS-773 against the current prompt"
    )

    # A completeness check would tell the agent to verify the seeded document
    # against something external to it (a parent run status, an expected epic
    # count) before recomputing totals purely from what it was handed.
    verify_pattern = re.compile(r"(?i)verify.{0,80}(complete|parent|degraded|expected count)")
    assert verify_pattern.search(body), (
        "the revision agent recomputes Backlog Summary totals with no "
        "instruction to verify the seeded backlog was complete first — a "
        "QA-PS-028 drop in the parent run compounds forward unflagged"
    )
