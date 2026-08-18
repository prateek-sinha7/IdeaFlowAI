"""tests/agents/test_redo_prompt_contract.py — what a redo re-dispatch RECEIVES.

`ISS-086`. ``test_redo_gate_safety.py`` pins four *absence* properties of a redo (no
leaked signal, no leaked lineage, no leaked REVISE block, a flat stack) — it drives a
full redo of agent A and then inspects **agent B's** prompt. Nothing anywhere asserted
what the re-run itself is given, so the engine shipped a "Request changes" action whose
re-dispatch carried the user's instruction and *not* the document that instruction is
about: the model, having no subject, wrote only the delta and the prior work was lost
(measured live: a task list went 12,542 → 3,495 chars, 7 headings → 1, 0 of 7 kept).

The characterization goldens cannot guard this — ``_scripted_model.py`` drives them with
``gate_agent_ids=[]``, so no gate ever opens and a redo is unreachable there. This file is
the safety net.

Five presence properties, all on the scripted-model harness (no Bedrock / Postgres /
Chromium), reusing ``test_redo_gate_safety``'s harness rather than forking it (INV-12):

  * the redo dispatch carries the agent's OWN prior output — parametrized over agent ids
    read from the registry, across two workflows (the SC-001 generality proof);
  * the subject is rendered BEFORE the instructions (FIX-217's ordering rule);
  * after two redos the injected subject is the version actually being rejected (v2);
  * the same holds at BOTH non-live consumer sites — the RESUME-17 gate re-entry and the
    gate re-opened after a revision pass;
  * a per-task build dispatch is skipped while a whole-artifact redo of the same agent is
    injected (the discriminating pair — see the test's own docstring).

TRAP (documented in test_redo_gate_safety.py:230-235 and hit again while writing this
file): the fake gate's parameter names must match ``_run_review_gate``'s keyword-only
call exactly. ``_run_agent`` swallows a stub ``TypeError`` into an ``agent_error`` event,
so a misnamed parameter does not error — the test silently observes ZERO gate firings.
"""

from __future__ import annotations

import pytest

# Importing the harness sets RUNS_ROOT to a temp dir + forces the InMemory checkpointer
# BEFORE app.core.config loads — keep this import first.
from tests.agents._scripted_model import ScriptedFakeChatModel, _ScriptedTurn  # noqa: E402

from tests.agents.test_redo_gate_safety import (  # noqa: E402
    _EngineHarness,
    _drive_agent,
    _make_ectx,
)

# Sentinels no scripted-model output can produce by accident.
PRIOR = "PRIOR-OUTPUT-SENTINEL ## Task 2: Dashboard Overview"
PRIOR_2 = "SECOND-DRAFT-SENTINEL ## Task 2: Dashboard Overview"
INSTRUCTION = "add 2 more pages to it"
PRIOR_BLOCK = "=== PRIOR ARTIFACT UNDER REVISION ==="
REVISE_BLOCK = "=== ADDITIONAL INSTRUCTIONS (REVISE) ==="


def _redo_agent_ids() -> list[str]:
    """Three real text-only agents from TWO pipelines, read from the registry.

    The assertions never name an agent (INV-1): the defect is agent-general, so the
    guard has to be too (SC-001).
    """
    from agents.registry import PIPELINE_AGENTS

    return [*PIPELINE_AGENTS["user_stories"][:2], PIPELINE_AGENTS["prototype"][1]]


def _turn(text: str):
    return [_ScriptedTurn(texts=[text], usage=(5, 3))]


def _redo_then_approve_gate(calls: dict, *, redos: int = 1, instructions: str = INSTRUCTION):
    """Gate stub: the first ``redos`` firings request a redo, the next one approves."""

    async def _gate(pipeline_run_id, agent_id, agent_name, output, redoable=False, **kwargs):
        calls["n"] += 1
        yield {
            "type": "review_gate_ready",
            "data": {"gate_key": f"{pipeline_run_id}:{agent_id}", "redoable": redoable},
        }
        if calls["n"] <= redos:
            yield {"type": "_gate_redo", "instructions": instructions}
        else:
            yield {"type": "review_gate_approved", "data": {}}

    return _gate


def _prompts(events: list[dict], agent_id: str | None = None) -> list[str]:
    return [
        e["data"]["context_message"]
        for e in events
        if e["type"] == "agent_input"
        and (agent_id is None or e["data"]["agent_id"] == agent_id)
    ]


async def _drive_redo(
    agent_id: str,
    *,
    redos: int = 1,
    instructions: str = INSTRUCTION,
    drafts: list[str] | None = None,
    build_task_number: str = "",
):
    """Run one gated agent, redo ``redos`` times, then approve. Return (prompts, ectx)."""
    from agents.loader import load_agent_spec

    spec = load_agent_spec(agent_id)
    calls = {"n": 0}
    texts = drafts or [PRIOR, "delta only. "]

    def _model_for(_aid, idx):
        return ScriptedFakeChatModel(_turn(texts[idx] if idx < len(texts) else "delta only. "))

    with _EngineHarness(_model_for) as h:
        h.engine._run_review_gate = _redo_then_approve_gate(  # type: ignore[assignment]
            calls, redos=redos, instructions=instructions
        )
        ectx = _make_ectx(f"iss086-{agent_id}-{redos}-{bool(build_task_number)}",
                          gate_agent_ids=[spec.id])
        ectx.build_task_number = build_task_number
        events = await _drive_agent(h.engine, spec, ectx, [], [spec])

    prompts = _prompts(events)
    assert len(prompts) == redos + 1, (
        f"expected {redos + 1} dispatches (first + {redos} redo(s)), got {len(prompts)} "
        f"— check the gate stub's parameter names (see this file's TRAP note)"
    )
    return prompts, ectx


# ===========================================================================
# 1 — the defect itself, proven agent-general
# ===========================================================================


@pytest.mark.asyncio
@pytest.mark.parametrize("agent_id", _redo_agent_ids())
async def test_redo_dispatch_carries_the_agents_own_prior_output(agent_id) -> None:
    """ISS-086: "Request changes" must show the agent the document it is changing.

    Self-consumption cannot do this (``_filter_consumed_outputs`` breaks on
    ``upstream.id == spec.id``), the ``:redo{N}`` thread deliberately kills checkpoint
    replay, and a gated authoring agent declares ``tools: []`` — so the injected block is
    the ONLY channel.
    """
    prompts, ectx = await _drive_redo(agent_id)

    # The prior version IS durable in the typed graph at redo time...
    versions = [r for r in ectx.artifacts.tree(ectx.run_id) if r.producer_agent == agent_id]
    assert versions, "no artifact versions were written at all"

    redo_prompt = prompts[1]
    assert INSTRUCTION in redo_prompt, "the instruction must still reach the re-run"
    assert PRIOR in redo_prompt, (
        f"the redo dispatch for {agent_id} does NOT contain the agent's own prior output "
        f"(delta first->redo = {len(redo_prompt) - len(prompts[0])} chars, i.e. the "
        f"instruction block alone)"
    )
    assert PRIOR_BLOCK in redo_prompt, "the prior output must ride its own labelled block"


# ===========================================================================
# 2 — ordering: subject first, instructions second
# ===========================================================================


@pytest.mark.asyncio
async def test_redo_dispatch_renders_subject_before_instructions() -> None:
    """FIX-217's stated rule. The REVISE block is appended by the same composer, and
    before this fix it landed ABOVE where the prior-artifact block renders — so reusing
    the seam without moving the block would read "instructions first, subject second"."""
    prompts, _ = await _drive_redo(_redo_agent_ids()[0])
    p = prompts[1]

    assert PRIOR_BLOCK in p and REVISE_BLOCK in p
    assert p.index(PRIOR_BLOCK) < p.index(REVISE_BLOCK), (
        "the redo prompt states the instructions before the document they are about"
    )


# ===========================================================================
# 3 — the injected subject is the version being REJECTED (max-version, kind-scoped)
# ===========================================================================


@pytest.mark.asyncio
async def test_redo_injects_the_version_actually_being_rejected() -> None:
    """After two redos the third dispatch must carry v2 (the draft on screen), not v1."""
    prompts, _ = await _drive_redo(
        _redo_agent_ids()[0], redos=2, drafts=[PRIOR, PRIOR_2, "delta only. "]
    )

    assert PRIOR in prompts[1] and PRIOR_2 not in prompts[1], (
        "the FIRST redo must carry v1 — the draft it is rejecting"
    )
    assert PRIOR_2 in prompts[2], (
        "the SECOND redo must carry v2 (the max version), not the superseded v1"
    )
    assert PRIOR not in prompts[2], (
        "the second redo served the SUPERSEDED v1 — the selection is not max-version"
    )


# ===========================================================================
# 4 — the two non-live consumer sites
# ===========================================================================


@pytest.mark.asyncio
async def test_redo_at_the_gate_reentry_site_carries_it_too() -> None:
    """The RESUME-17 restart-parked gate re-entry re-opens with ZERO model call, so its
    redo consumer is a separate branch. FIX-217's own analogue nearly shipped wired at
    one site only; this is the parametrization that would have caught it."""
    from agents.loader import load_agent_spec
    from tests.agents.test_restart_resume import _FakeGateRunner, _seed_gate_reentry_ectx

    spec = load_agent_spec(_redo_agent_ids()[0])
    calls = {"n": 0}

    with _EngineHarness(lambda aid, idx: ScriptedFakeChatModel(_turn("delta only. "))) as h:
        h.engine._run_review_gate = _redo_then_approve_gate(calls)  # type: ignore[assignment]
        ectx = _seed_gate_reentry_ectx(
            "iss086-reentry", spec, content=PRIOR, runner=_FakeGateRunner()
        )
        results = [{"agent_id": spec.id, "output": PRIOR}]
        events = await _drive_agent(h.engine, spec, ectx, results, [spec])

    prompts = _prompts(events)
    assert len(prompts) == 1, (
        f"the re-entry skips the model call, so only the REDO re-run dispatches: {len(prompts)}"
    )
    assert PRIOR in prompts[0] and PRIOR_BLOCK in prompts[0], (
        "the re-entry redo consumer did not inject the persisted prior output"
    )


@pytest.mark.asyncio
async def test_redo_at_the_reopened_post_revision_gate_carries_it_too() -> None:
    """The gate re-opened after a revision pass short-circuits the model call the same
    way. Before ISS-086 this branch was a THIN COPY of the live consumer — it set only the
    directive, so besides missing the subject it also dropped ``derived_from`` lineage,
    left a duplicate ``results`` entry and wrote no audit row."""
    from agents.loader import load_agent_spec
    from tests.agents.test_restart_resume import _FakeGateRunner

    spec = load_agent_spec(_redo_agent_ids()[0])
    calls = {"n": 0}

    with _EngineHarness(lambda aid, idx: ScriptedFakeChatModel(_turn("delta only. "))) as h:
        h.engine._run_review_gate = _redo_then_approve_gate(calls)  # type: ignore[assignment]
        ectx = _make_ectx("iss086-reopen", gate_agent_ids=[spec.id])
        runner = _FakeGateRunner()
        ectx.runner = runner
        ectx.artifacts.write_ref(
            run_id=ectx.run_id, owner_id="anon", workspace_id="ws", kind="summary",
            producer_step=spec.id, producer_agent=spec.id, task_id=None,
            content=PRIOR, location=f"artifact_refs/{spec.id}",
        )
        # The sub-pipeline's terminal hand-off: re-open this agent's gate on the new
        # analysis text without re-running its model.
        ectx.spec_revision_pending_output = "NEW ANALYSIS AFTER THE PASS"
        results = [{"agent_id": spec.id, "output": PRIOR}]
        events = await _drive_agent(h.engine, spec, ectx, results, [spec])

    prompts = _prompts(events)
    assert len(prompts) == 1, f"expected exactly the redo re-run dispatch, got {len(prompts)}"
    assert PRIOR in prompts[0] and PRIOR_BLOCK in prompts[0], (
        "the re-opened-gate redo consumer did not inject the prior output"
    )
    # The thin-copy defects the shared consumer closes.
    assert [r for r in results if r.get("agent_id") == spec.id][:1], "results lost the agent"
    assert len([r for r in results if r.get("agent_id") == spec.id]) == 1, (
        "the re-opened-gate redo left a DUPLICATE results entry (no results.pop())"
    )
    assert any(row[2] == "redo" for row in runner.recorded), (
        "the re-opened-gate redo wrote no audit row, so a post-restart :redo{N} can collide"
    )
    _refs = [r for r in ectx.artifacts.tree(ectx.run_id)
             if r.producer_agent == spec.id and r.kind == "summary"]
    assert len(_refs) == 2 and _refs[-1].derived_from == _refs[0].id, (
        "the re-opened-gate redo's re-run lost its derived_from lineage"
    )


# ===========================================================================
# 5 — the task-loop skip, as a DISCRIMINATING pair
# ===========================================================================


@pytest.mark.asyncio
async def test_task_loop_redo_is_skipped_but_a_whole_artifact_redo_is_not() -> None:
    """A per-task build dispatch already carries a COMPACTED skeleton of the same
    document, so injecting the full artifact on top would double-inject the deliverable.

    Asserted as a PAIR on the SAME agent so it is a genuine red before the fix: today
    neither case injects, so "the task-loop case does not inject" would be green from
    birth and prove nothing. The pair fails on its second half until the fix lands.
    """
    agent_id = _redo_agent_ids()[0]

    task_prompts, _ = await _drive_redo(agent_id, build_task_number="2")
    whole_prompts, _ = await _drive_redo(agent_id)

    assert PRIOR_BLOCK in whole_prompts[1], (
        "a whole-artifact redo MUST carry the prior output (the ISS-086 fix)"
    )
    assert PRIOR_BLOCK not in task_prompts[1], (
        "a per-task redo must NOT be handed the full artifact — the task dispatch already "
        "carries a compacted view of it"
    )
    assert INSTRUCTION in task_prompts[1], (
        "the per-task redo must still receive the user's instruction"
    )


# ===========================================================================
# Dormancy guards — GREEN before AND after the fix (INV-3), not red-first tests
# ===========================================================================


@pytest.mark.asyncio
async def test_first_dispatch_carries_neither_block() -> None:
    """INV-3: the fix is keyed on a redo-only loop local, so the FIRST dispatch of the
    same agent is untouched. (Byte-identity against the pre-fix build is proven out of
    band by dumping and diffing this prompt; this is the in-suite guard.)"""
    prompts, _ = await _drive_redo(_redo_agent_ids()[0])
    assert PRIOR_BLOCK not in prompts[0] and REVISE_BLOCK not in prompts[0]


@pytest.mark.asyncio
async def test_blank_redo_stays_a_regenerate() -> None:
    """The FE labels a blank instruction "leave blank to just regenerate". Blank ⇒
    regenerate-from-scratch is coherent and is what the ``:redo{N}`` fresh thread exists
    for, so the subject is withheld; only a non-blank instruction asks for an amendment."""
    prompts, _ = await _drive_redo(_redo_agent_ids()[0], instructions="")
    assert PRIOR_BLOCK not in prompts[1], (
        "a blank redo injected the prior output — that turns 'regenerate' into 'revise'"
    )
    assert REVISE_BLOCK not in prompts[1]


@pytest.mark.asyncio
async def test_redo_subject_does_not_leak_to_the_next_agent() -> None:
    """Consume-once, via save/restore rather than clear (the FIX-218 defect-A shape): the
    next agent's prompt must carry neither the block nor the text."""
    from agents.loader import load_agent_spec

    ids = _redo_agent_ids()
    spec_a, spec_b = load_agent_spec(ids[0]), load_agent_spec(ids[1])
    ordered = [spec_a, spec_b]
    calls = {"n": 0}

    def _model_for(agent_id, idx):
        if agent_id == spec_a.id:
            return ScriptedFakeChatModel(_turn(PRIOR if idx == 0 else "delta only. "))
        return ScriptedFakeChatModel(_turn("epic output. "))

    with _EngineHarness(_model_for) as h:
        h.engine._run_review_gate = _redo_then_approve_gate(calls)  # type: ignore[assignment]
        ectx = _make_ectx("iss086-noleak", gate_agent_ids=[spec_a.id])
        results: list[dict] = []
        await _drive_agent(h.engine, spec_a, ectx, results, ordered, index=0)
        assert not ectx.spec_revision_prior_artifact, (
            "the prior-artifact scratch field outlived the redo (not consume-once)"
        )
        b_events = await _drive_agent(h.engine, spec_b, ectx, results, ordered, index=1)

    b_prompt = _prompts(b_events)[0]
    assert PRIOR_BLOCK not in b_prompt and PRIOR not in b_prompt, (
        "the redo subject leaked onto the NEXT agent"
    )
