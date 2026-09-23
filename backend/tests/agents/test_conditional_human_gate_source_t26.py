"""T26 (spec 014 / Phase 3 dispatch loop): ``ex_A4_human_gate`` (A4, the
human-gate-as-condition-source fixture) driven end-to-end, proving R-05's claim that a
conditional gate's decision source ``condition_agent`` may name an EARLIER step whose
content a HUMAN supplied — read the same way as any other step's artifact.

Fixture shape (``agents/workflows/ex_A4_human_gate/workflow.yaml``):

    1. ask            produces:[route_decision] — emits a PLACEHOLDER the human overwrites
    2. pick-language  gates:[before-human, conditional], route.condition_agent: ask
         PRE  before-human -> run pauses; the approve-with-edits payload REPLACES
                              ask's artifact (a new ref version, ART-03)
         POST conditional  -> routes on what the human wrote into ask
       outcomes: english -> say-hello | spanish -> say-hola | dutch -> say-hallo
    3a/3b/3c. say-hello / say-hola / say-hallo   (leaves)

Deliberately the SAME 3-way branch as ex_A2_branch, so the only variable between the
two fixtures is WHO decides.

Two scripted passes:

  * ``test_human_edit_at_the_gate_picks_the_branch`` — the human approves WITH an edit
    of ``{"decision": "spanish"}``. ``pick-language``'s own scripted turn is an EMPTY
    string (never valid decision JSON), so a successful route can ONLY have come from
    reading ``ask``'s human-edited content. Asserts ``say-hola`` runs and the other two
    branch targets do not.

  * ``test_bare_approve_leaves_the_placeholder_and_the_gate_blocks`` — the human
    approves WITHOUT editing, so the placeholder survives, ``ask`` holds no decision,
    and (there is no ``default_next``, by design) the run ends at the gate. This is the
    fail-CLOSED half: an unrecognised choice must never fall through to a branch.

Human-gate scripting mechanism: the SAME one the repo's existing declared-gate tests
use (``tests/agents/test_declared_gate_streaming.py``) — drive ``engine.execute()``
by hand, and on each ``review_gate_ready`` call
``engine._store.set_review_response(gate_key, approved=True, edited_content=...)``
(the same call ``websocket.py``'s ``approve_review`` handler makes for
approve-with-edits). ``_drive()`` is NOT used here: it passes ``gate_agent_ids=[]``,
which the WR-02 dedupe in ``_evaluate_gates`` treats as "skip every declared human
gate" — that would bypass the human gate entirely.

No live LLM: fully scripted offline (``ScriptedFakeChatModel``).
"""

from __future__ import annotations

import asyncio
import uuid

import pytest

from tests.agents import _scripted_model as _sm
from tests.agents._scripted_model import _RUNS_ROOT, ScriptedFakeChatModel, _ScriptedTurn

_PIPELINE = "ex_A4_human_gate"
_EVENT_TIMEOUT_S = 30.0


def _scripts_for():
    """``ask`` emits only its placeholder and ``pick-language`` emits an EMPTY string.

    Neither is ever valid decision JSON, so any successful route in these tests can
    only have come from the human's edit landing on ``ask``'s artifact — which is the
    whole claim T26 exists to prove.
    """

    def _fn(agent_id: str) -> list[_ScriptedTurn]:
        if agent_id == "custom-agent:ask":
            return [_ScriptedTurn(texts=["(awaiting language choice)"], usage=(5, 3))]
        if agent_id == "custom-agent:pick-language":
            return [_ScriptedTurn(texts=[""], usage=(1, 1))]
        return [_ScriptedTurn(texts=[f"{agent_id} default output."], usage=(5, 3))]

    return _fn


async def _run_pipeline(edit: str | None, *, stop_when) -> list[dict]:
    """Drive ``engine.execute()`` by hand (real declared human-gate pause/approve —
    the ``test_declared_gate_streaming.py`` recipe), approving every
    ``review_gate_ready`` as it arrives. Returns every event observed once
    ``stop_when(events)`` first returns True (checked after each event, including
    after an approval is sent) or the generator naturally exhausts — the "revise"
    scenario only needs to observe ONE loop-back, not a full drain to a terminal
    event, so the caller supplies the exact stopping condition.
    """
    import agents.execution_engine.engine as engine_mod
    import agents.factory as factory_mod
    from agents.execution_engine.engine import ExecutionEngine
    from agents.registry import get_pipeline_agents
    from app.core.config import settings as _settings

    _settings.RUNS_ROOT = _RUNS_ROOT

    _orig_compile_for_run = engine_mod.compile_for_run

    def _patched_compile_for_run(pipeline_type, _orig=_orig_compile_for_run):
        compiled = _orig(pipeline_type)
        compiled.clarify.mode = "off"
        return compiled

    engine_mod.compile_for_run = _patched_compile_for_run

    specs = list(get_pipeline_agents(_PIPELINE))  # [] for a composed workflow —
    # execute() falls back to the compiled plan's own steps (ADR-0008).

    orig_scripts_for = _sm._scripts_for
    _sm._scripts_for = _scripts_for()

    _orig_create_runner = factory_mod.create_runner
    _orig_engine_create_runner = getattr(engine_mod, "create_runner", None)

    def _patched_create_runner(agent_id, ctx, **kw):
        ctx.model = ScriptedFakeChatModel(_sm._scripts_for(agent_id))
        return _orig_create_runner(agent_id, ctx, **kw)

    factory_mod.create_runner = _patched_create_runner
    engine_mod.create_runner = _patched_create_runner

    engine = ExecutionEngine()

    async def _fake_run_planner(user_message, pipeline_run_id, model_id, cancel_event, ptype="custom", **kwargs):
        return engine._default_planning_context(user_message), "PROCEED"

    engine._run_planner = _fake_run_planner  # type: ignore[assignment]

    async def _noop_store(*a, **k):
        return "artifact-id"

    engine._store.store = _noop_store  # type: ignore[assignment]

    run_id = f"t26-{uuid.uuid4().hex[:8]}"
    events: list[dict] = []

    gen = engine.execute(
        agents=list(specs),
        user_message="Review the draft.",
        pipeline_run_id=run_id,
        pipeline_type=_PIPELINE,
        user_id="harness-user",
        # gate_agent_ids left at the default (None): the declared gates:[human]
        # step must take the REAL pause (see module docstring — NOT _drive()'s
        # gate_agent_ids=[] skip).
    )

    try:
        while True:
            try:
                ev = await asyncio.wait_for(gen.__anext__(), timeout=_EVENT_TIMEOUT_S)
            except StopAsyncIteration:
                break
            events.append(ev)
            if ev.get("type") == "review_gate_ready":
                # `edited_content` is what the human typed at the gate. The gate
                # threads it onto its terminal outcome detail, and the kernel's
                # `_apply_declared_gate_edit` rewrites the PREVIOUS step's artifact
                # (`ask`) with it — which is exactly the channel
                # `route.condition_agent: ask` then reads. `None` = a bare approve.
                await engine._store.set_review_response(
                    ev["data"]["gate_key"], approved=True, edited_content=edit
                )
            if stop_when(events):
                break
    finally:
        await gen.aclose()
        _sm._scripts_for = orig_scripts_for
        factory_mod.create_runner = _orig_create_runner
        if _orig_engine_create_runner is not None:
            engine_mod.create_runner = _orig_engine_create_runner
        engine_mod.compile_for_run = _orig_compile_for_run

    return events


@pytest.mark.asyncio
async def test_human_edit_at_the_gate_picks_the_branch():
    """The human's approve-with-edits payload lands on `ask` and the conditional
    gate routes on it (R-05: condition_agent may name an earlier, human-supplied step)."""

    def _stop_when(events: list[dict]) -> bool:
        starts = [e["data"].get("agent_id") for e in events if e.get("type") == "agent_start"]
        if "custom-agent:say-hola" in starts:
            return True
        return any(
            e.get("type") in ("gate_blocked", "pipeline_complete", "pipeline_cancelled", "budget_aborted")
            for e in events
        )

    events = await _run_pipeline('{"decision": "spanish"}', stop_when=_stop_when)

    assert events, f"{_PIPELINE} produced no events"
    types = [e.get("type") for e in events]
    starts = [e["data"].get("agent_id") for e in events if e.get("type") == "agent_start"]

    # The gate resolved a decision — a failed read is a gate_blocked on this
    # fixture (no default_next), never a silent pass-through.
    assert not any(e.get("type") == "gate_blocked" for e in events), (
        f"pick-language blocked instead of routing — condition_agent:ask did not "
        f"resolve a decision from the human's edit. Events: {types}"
    )
    # pick-language dispatches exactly once: the conditional gate is POST-step, so a
    # route match does not skip the step's own dispatch.
    assert starts.count("custom-agent:pick-language") == 1, (
        f"expected pick-language to dispatch exactly once (POST-step gate). starts={starts}"
    )
    # The SPANISH branch ran, and only it.
    assert "custom-agent:say-hola" in starts, (
        f"'say-hola' never ran despite the human choosing spanish. starts={starts}"
    )
    assert "custom-agent:say-hello" not in starts and "custom-agent:say-hallo" not in starts, (
        f"a non-selected branch target ran — the outcomes are mutually exclusive. "
        f"starts={starts}"
    )


@pytest.mark.asyncio
async def test_bare_approve_leaves_the_placeholder_and_the_gate_blocks():
    """Approving WITHOUT an edit leaves `ask`'s placeholder in place, so the gate has
    no decision to read and the run ends there — fail CLOSED, never a default branch.

    This is the half that makes the sibling test meaningful: without it, a fixture that
    routed to `say-hola` for ANY input would still pass above.
    """

    def _stop_when(events: list[dict]) -> bool:
        return any(
            e.get("type") in ("gate_blocked", "pipeline_complete", "pipeline_failed",
                              "pipeline_cancelled", "budget_aborted")
            for e in events
        )

    events = await _run_pipeline(None, stop_when=_stop_when)

    assert events, f"{_PIPELINE} produced no events"
    starts = [e["data"].get("agent_id") for e in events if e.get("type") == "agent_start"]

    assert any(e.get("type") == "gate_blocked" for e in events), (
        f"expected the gate to block on the surviving placeholder (no matching "
        f"outcome, no default_next). starts={starts}"
    )
    # No branch target may run on an unresolved decision.
    for branch in ("custom-agent:say-hello", "custom-agent:say-hola", "custom-agent:say-hallo"):
        assert branch not in starts, (
            f"{branch} ran without a resolved decision — the gate failed OPEN. "
            f"starts={starts}"
        )
