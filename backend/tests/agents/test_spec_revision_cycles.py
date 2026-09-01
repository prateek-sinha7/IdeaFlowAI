"""tests/agents/test_spec_revision_cycles.py — MULTIPLE spec-revision cycles.

`.planning/BUGFIX-NESTED-REVISION.md` defects A and B. Its sibling
`test_spec_revision_context.py` (quick 260811-mxg) proves what ONE revision cycle puts in
the prompt; this file proves what happens when there is more than one — a second cycle
started from the RE-OPENED gate (B), and a pass that re-enters itself (A).

  * B — ``engine.py``'s third ``_gate_update_specs`` branch (the pending-re-open
    short-circuit) only re-seeded ``spec_revision_pending_output`` and ``break``ed. A
    second "Update the Specs" therefore closed the gate, silently re-opened it on the
    IDENTICAL content (the FE sends the analyzer's own output as the report,
    ``InlineGateActions.tsx:163``) and ran nothing — then the build proceeded from the
    unrevised spec. Tests 1 and 2.
  * B-flat — the second cycle must be a SIBLING of the first, not a nested one. The
    sub-pipeline's ``finally`` precedes its terminal yield and the driving ``async for``
    runs the generator to exhaustion before ``break``ing, so by the time control reaches
    the re-opened gate the first pass is fully unwound. Asserted as pairwise-equal
    ``len(inspect.stack())`` between cycles — the REDO-GATE F2 flat-loop precedent. Test 2.
  * A-affordance — the analyze re-run INSIDE a pass used to be gated and to advertise
    "Update the Specs" there, which is the one route that nests. ISS-053 withheld the
    eligibility flag at that firing; ISS-072 then SUPPRESSED the firing itself, since it
    showed the content the re-opened gate is about to show again. Test 3.
  * A-safety — a nested pass must be SAFE regardless: distinct ``:rev{N}`` at any depth (a
    monotone per-run high-water mark) and an inner pass that RESTORES rather than zeroes
    the outer pass's scratch. Test 4. Since ISS-053 the engine ENFORCES the eligibility
    flag, so the in-pass route is fenced and no client can reach a nested pass through
    ``_run_review_gate``; this test drives the sub-pipeline directly (it stubs the gate
    out) and so still pins that safety as DEFENCE IN DEPTH — what keeps the engine correct
    if a future call site ever passes the flag wrongly. The fence itself is proven in
    ``test_update_specs_enforcement.py``.
  * Safety boundary — one cycle is unchanged. This one PASSES pre-fix; it is the
    dormancy guard. Test 5.

All five run on the scripted-model harness — no Bedrock / Postgres / Chromium.
"""

from __future__ import annotations

import inspect

import pytest

# Importing the harness sets RUNS_ROOT to a temp dir + forces the InMemory checkpointer
# BEFORE app.core.config loads — keep this import first.
from tests.agents._scripted_model import ScriptedFakeChatModel  # noqa: E402

PRIOR = "PRIOR-SPEC-SENTINEL ## Workflow Completion Checklist"

# The gate stub fires 2 times per cycle since ISS-072 suppressed the in-pass analyze gate
# (3 with ``allow_in_pass_gate=True``); a correct two-cycle drive is 3 firings. Anything
# far above that is a wiring mistake looping, so fail fast rather than hang.
_RUNAWAY_LIMIT = 14


def _revision_triple():
    """Three real text-only agents so ``index=2`` gives specify/plan/analyze structurally.

    Read from the registry at test time — the assertions never name an agent (INV-1).

    Sourced from ``prototype``, not ``user_stories``. Both give three text-only agents,
    but only prototype's third IS the analyze gate these tests are about. That did not
    matter while ``_UPDATE_SPECS_ELIGIBLE_KINDS`` was ``{"summary"}``: any UNMAPPED agent
    fell back to ``summary`` and so looked eligible, which is the bug FIX-223 fixed by
    giving prototype-analyze its own ``analysis`` kind and narrowing the eligible set to
    it. With that fix, a stand-in from another pipeline is correctly ineligible and these
    tests were asserting eligibility on an agent that should never have had it.
    """
    from agents.loader import load_agent_spec
    from agents.registry import PIPELINE_AGENTS

    return [load_agent_spec(a) for a in PIPELINE_AGENTS["prototype"][:3]]


def _write_ref(ectx, run_id: str, producer_id: str, content: str) -> None:
    ectx.artifacts.write_ref(
        run_id=run_id,
        owner_id="anon",
        workspace_id="ws",
        kind="summary",
        producer_step=producer_id,
        producer_agent=producer_id,
        task_id=None,
        content=content,
        location=f"artifact_refs/{producer_id}",
    )


async def _drive_cycles(run_id: str, click_at: set[int], *, allow_in_pass_gate: bool = False):
    """Drive ``_run_agent`` over a REAL revision sub-pipeline, clicking "Update the
    Specs" at the gate firings named in ``click_at``. Every other firing approves.

    Returns ``(gate_records, thread_ids, ectx, ordered, events)`` where each gate record
    is a dict of ``firing`` / ``depth`` / ``revision_attempt`` / ``context_set`` /
    ``eligible`` sampled at the START of the gate, before any action is taken.

    Gate-firing map, one cycle = 2 firings since ISS-072:
      ``[0]`` the outer first-pass gate, ``[1]`` the gate re-opened after the sub-pipeline
      returned. The analyze re-run's gate INSIDE the sub-pipeline is SUPPRESSED — it
      showed the content ``[1]`` is about to show again, so it never fires.
    So ``{0}`` is a single cycle and ``{0, 1}`` is the two-sibling-cycle drive (Defect B).

    ``allow_in_pass_gate=True`` stubs ``_should_gate`` down to its ``gate_agent_ids``
    branch, which BYPASSES the ISS-072 suppression and restores the pre-ISS-072 three-
    firing map (``[1]`` in-pass, ``[2]`` re-opened) so ``{0, 1}`` is the nested drive
    (Defect A). It is the same deliberate fence-bypass as this file's ``_run_review_gate``
    stub: no client can reach a nested pass any more, and the A-safety net must be kept
    honest rather than left to rot behind the fence.

    ``_run_spec_revision_sub_pipeline`` is deliberately NOT stubbed — this file exists to
    prove what it does.
    """
    from tests.agents.test_redo_gate_safety import (
        _EngineHarness,
        _drive_agent,
        _make_ectx,
        _text_turn,
    )

    ordered = _revision_triple()
    records: list[dict] = []
    state = {"n": 0, "runaway": False}

    ectx_box: dict = {}

    async def _gate(pipeline_run_id, agent_id, agent_name, output, redoable=False, **kwargs):
        # `**kwargs` is load-bearing: _run_agent swallows a stub TypeError into an
        # `agent_error` event, so a stale signature yields a silently-ZERO gate count
        # rather than an error (the exact trap that keeps biting this area).
        i = state["n"]
        state["n"] += 1
        if i >= _RUNAWAY_LIMIT:
            # Do NOT raise — _run_agent would swallow it. Flag it and approve so the
            # whole chain unwinds; the drive helper asserts on the flag afterwards.
            state["runaway"] = True
            return
        _ectx = ectx_box["ectx"]
        records.append({
            "firing": i,
            # Engine stack depth at the gate — a nested cycle is strictly deeper.
            "depth": len(inspect.stack()),
            "revision_attempt": _ectx.revision_attempt,
            # constraint 9: spec_revision_context was undeclared pre-fix, so a bare
            # attribute read raises AttributeError on a fresh context.
            "context_set": bool(getattr(_ectx, "spec_revision_context", "")),
            "eligible": kwargs.get("update_specs_eligible"),
            # ISS-052 / FIX-220: the per-firing discriminator that tells the in-pass and
            # re-opened gates apart on the wire. Recorded here (not in a second harness —
            # INV-12) and asserted by test_gate_revision_discriminator.py.
            "revision_cycle": kwargs.get("revision_cycle"),
            "revision_in_flight": kwargs.get("revision_in_flight"),
        })
        yield {
            "type": "review_gate_ready",
            "data": {"gate_key": f"{pipeline_run_id}:{agent_id}", "redoable": redoable},
        }
        if i in click_at:
            # The FE sends the ANALYZER'S OWN OUTPUT as the report, not user-typed
            # text (InlineGateActions.tsx:163) — mirror that exactly.
            yield {"type": "_gate_update_specs", "analysis_report": output}

    with _EngineHarness(
        lambda aid, idx: ScriptedFakeChatModel(_text_turn(f"{aid} output {idx}. "))
    ) as h:
        h.engine._run_review_gate = _gate  # type: ignore[assignment]
        if allow_in_pass_gate:
            # The ``gate_agent_ids`` branch of the real ``_should_gate``, minus its
            # ISS-072 ``suppress_review_gate`` veto — see the docstring.
            h.engine._should_gate = (  # type: ignore[assignment]
                lambda spec, ectx, **_kw: spec.id in set(ectx.gate_agent_ids or [])
            )
        ectx = _make_ectx(run_id, gate_agent_ids=[ordered[2].id])
        ectx_box["ectx"] = ectx
        _write_ref(ectx, run_id, ordered[0].id, PRIOR)
        results: list[dict] = []

        # index=2 EXPLICITLY. _drive_agent defaults to index=0 and
        # _run_spec_revision_sub_pipeline silently `return`s when index < 2 (a
        # logger.warning, never a raise), so the default drives ZERO sub-dispatches and
        # the test fails on a baffling count assertion. index=2 is also what makes
        # ordered[0] / ordered[1] the specify/plan predecessors STRUCTURALLY.
        events = await _drive_agent(h.engine, ordered[2], ectx, results, ordered, index=2)
        thread_ids = list(h.thread_ids)

    assert not state["runaway"], (
        f"the gate fired more than {_RUNAWAY_LIMIT} times — the revision wiring is looping"
    )
    return records, thread_ids, ectx, ordered, events


def _assert_sentinel_never_escapes(events: list[dict]) -> None:
    """The shared consumer's terminal ``_update_specs_done`` signal is INTERNAL — it is
    consumed at all three call sites and must never reach the wire."""
    leaked = [e for e in events if e.get("type") == "_update_specs_done"]
    assert not leaked, f"the internal _update_specs_done sentinel reached the wire: {leaked}"


# ===========================================================================
# Defect B — a second "Update the Specs" at the RE-OPENED gate
# ===========================================================================


@pytest.mark.asyncio
async def test_reopened_gate_second_update_specs_runs_a_second_cycle() -> None:
    """B: clicking "Update the Specs" at the re-opened analyze gate starts a REAL second
    revision cycle, on its own ``:rev2`` threads.

    Pre-fix the branch only re-seeded ``spec_revision_pending_output`` and broke, so the
    gate closed, instantly re-opened on the same content, and nothing ran.
    """
    run_id = "cycles-b"
    _records, thread_ids, _ectx, ordered, events = await _drive_cycles(run_id, {0, 1})
    _assert_sentinel_never_escapes(events)

    analyze_id = ordered[2].id
    first_pass = f"{run_id}:{analyze_id}"

    # Count BEFORE slicing, so a pre-fix run fails on a clean assertion not an IndexError.
    assert len(thread_ids) == 7, (
        "expected 1 first-pass dispatch + 3 per revision cycle x 2 cycles = 7; the second "
        f"'Update the Specs' ran no cycle. Got {len(thread_ids)}: {thread_ids}"
    )
    assert thread_ids[0] == first_pass, (
        f"expected the first pass on the unsuffixed thread; got {thread_ids}"
    )

    cycle1, cycle2 = thread_ids[1:4], thread_ids[4:7]
    assert all(t.endswith(":rev1") for t in cycle1), f"cycle 1 must thread :rev1; got {cycle1}"
    assert all(t.endswith(":rev2") for t in cycle2), f"cycle 2 must thread :rev2; got {cycle2}"
    assert len(set(thread_ids)) == 7, (
        f"no checkpoint thread id may be reused across cycles; got {thread_ids}"
    )


@pytest.mark.asyncio
async def test_reopened_gate_cycle_keeps_a_flat_stack() -> None:
    """B-flat: the second cycle is a SIBLING of the first, not a nested one.

    Cycle 2's re-opened gate sits at the same engine stack depth as cycle 1's. A nested
    implementation would make cycle 2 strictly deeper — the REDO-GATE F2 reason unbounded
    human-paced operations must not recurse. (Pre-ISS-072 this compared the in-pass gates
    too; that firing is suppressed now, so the re-opened pair is the whole comparison.)
    """
    records, thread_ids, _ectx, _ordered, events = await _drive_cycles("cycles-flat", {0, 1})
    _assert_sentinel_never_escapes(events)

    assert len(thread_ids) == 7, (
        f"the second cycle never ran, so there is no depth to compare; got {thread_ids}"
    )
    assert len(records) == 3, (
        "expected 3 gate firings (the outer one plus one re-open per cycle); "
        f"got {len(records)}: {[r['firing'] for r in records]}"
    )

    reopened_1, reopened_2 = records[1]["depth"], records[2]["depth"]

    assert reopened_1 == reopened_2, (
        "cycle 2's re-opened gate is NESTED inside cycle 1 (stack grew "
        f"{reopened_1} -> {reopened_2}); revision cycles must be flat siblings"
    )


# ===========================================================================
# Defect A — nesting: the affordance fence and the re-entrancy safety net
# ===========================================================================


@pytest.mark.asyncio
async def test_update_specs_not_offered_while_a_revision_is_in_flight() -> None:
    """A-affordance: over ONE cycle the ``update_specs_eligible`` flag passed to the gate
    is True at the outer first-pass gate and True again at the re-opened gate.

    The single supported entry point is the one gate where the next cycle is flat; no
    capability is withdrawn (the user reaches it with the same number of clicks).

    ISS-072 narrowed this: the analyze re-run's in-pass gate, which this test used to
    watch publish ``False``, is SUPPRESSED and no longer fires at all — a strictly
    stronger fence than withholding the flag at it. The withholding RULE itself
    (``_update_specs_eligible`` condition 2) is kept and is proven directly in
    ``test_update_specs_enforcement.py``, where the rule lives.
    """
    records, _tids, _ectx, _ordered, events = await _drive_cycles("cycles-fence", {0})
    _assert_sentinel_never_escapes(events)

    assert len(records) == 2, (
        f"expected 2 gate firings for one cycle; got {[r['firing'] for r in records]}"
    )
    eligible = [r["eligible"] for r in records]

    assert eligible[0] is True, f"the first-pass analyze gate must offer it; got {eligible}"
    assert eligible[1] is True, (
        f"the re-opened gate must offer it again (the flat sibling route); got {eligible}"
    )


@pytest.mark.issue("ISS-072")
@pytest.mark.asyncio
async def test_in_pass_analyze_gate_is_suppressed_not_just_ineligible() -> None:
    """ISS-072: the in-pass analyze gate `[1]` must not fire at all, not merely be
    ineligible for "Update the Specs".

    ISS-053/FIX-218 already withhold the `update_specs_eligible` flag at firing `[1]`
    (proven by ``test_update_specs_not_offered_while_a_revision_is_in_flight`` above), but
    the gate itself still fires and still costs a plain approval — for content the user is
    about to be shown again at the re-opened gate `[2]` (same producer, same content, per
    ISS-072's live evidence). One cycle should cost 2 approvals (outer `[0]` +
    re-opened `[2]`), not 3.
    """
    records, _tids, _ectx, _ordered, events = await _drive_cycles("cycles-suppress-inpass", {0})
    _assert_sentinel_never_escapes(events)

    assert len(records) == 2, (
        "the in-pass analyze gate fired even though it is redundant with the re-opened "
        f"gate; expected 2 firings (outer + re-opened), got {len(records)}: "
        f"{[r['firing'] for r in records]}"
    )


async def _drive_cycle_all_three_gated(run_id: str):
    """Like ``_drive_cycles``, but ``gate_agent_ids`` covers ALL THREE re-dispatched
    agents (specify, plan, analyze), not just the analyze agent. Records ``agent_id`` on
    each firing so the caller can tell which step gated.

    This is the FIX-420 regression the ISS-072 suppression deliberately risked: the
    suppression marker (``ectx.suppress_review_gate = sub_spec is analyze_spec``) is set
    per-dispatch inside the sub-pipeline loop, True ONLY for the analyze re-dispatch — a
    pass-wide signal (keying on ``revision_attempt`` alone, which ISS-072 explicitly
    rejected) would have suppressed specify's and plan's in-pass gates too.
    """
    from tests.agents.test_redo_gate_safety import _EngineHarness, _drive_agent, _make_ectx, _text_turn

    ordered = _revision_triple()
    records: list[dict] = []
    state = {"n": 0, "runaway": False}
    ectx_box: dict = {}

    async def _gate(pipeline_run_id, agent_id, agent_name, output, redoable=False, **kwargs):
        i = state["n"]
        state["n"] += 1
        if i >= _RUNAWAY_LIMIT:
            state["runaway"] = True
            return
        records.append({"firing": i, "agent_id": agent_id})
        yield {
            "type": "review_gate_ready",
            "data": {"gate_key": f"{pipeline_run_id}:{agent_id}", "redoable": redoable},
        }
        if i == 0:
            # Click "Update the Specs" at the outer gate to enter the sub-pipeline.
            yield {"type": "_gate_update_specs", "analysis_report": output}

    with _EngineHarness(
        lambda aid, idx: ScriptedFakeChatModel(_text_turn(f"{aid} output {idx}. "))
    ) as h:
        h.engine._run_review_gate = _gate  # type: ignore[assignment]
        # ALL THREE re-dispatched agents are gated, not just analyze.
        ectx = _make_ectx(run_id, gate_agent_ids=[a.id for a in ordered])
        ectx_box["ectx"] = ectx
        _write_ref(ectx, run_id, ordered[0].id, PRIOR)
        results: list[dict] = []
        events = await _drive_agent(h.engine, ordered[2], ectx, results, ordered, index=2)

    assert not state["runaway"], (
        f"the gate fired more than {_RUNAWAY_LIMIT} times — the revision wiring is looping"
    )
    return records, ordered, events


@pytest.mark.issue("ISS-072")
@pytest.mark.asyncio
async def test_specify_and_plan_in_pass_gates_still_fire_when_analyze_is_suppressed() -> None:
    """ISS-072 regression guard: suppressing the analyze re-run's in-pass gate must NOT
    suppress the specify/plan in-pass gates too. Those are WANTED (ISS-052's live evidence)
    and the fix's own text calls out that a pass-wide ``revision_attempt`` signal would
    have killed them — the suppression marker must be per-dispatch, identity-scoped to the
    analyze re-dispatch alone.

    With all three re-dispatched agents gated: one cycle must show specify and plan each
    gating exactly once (their in-pass firing), analyze gating exactly twice (outer +
    re-opened), and analyze's IN-PASS re-dispatch must never appear at all.
    """
    records, ordered, events = await _drive_cycle_all_three_gated("cycles-specify-plan-still-fire")
    _assert_sentinel_never_escapes(events)

    specify_id, plan_id, analyze_id = ordered[0].id, ordered[1].id, ordered[2].id
    agent_ids = [r["agent_id"] for r in records]

    assert agent_ids.count(specify_id) == 1, (
        f"the specify in-pass gate must still fire exactly once; got {agent_ids}"
    )
    assert agent_ids.count(plan_id) == 1, (
        f"the plan in-pass gate must still fire exactly once; got {agent_ids}"
    )
    assert agent_ids.count(analyze_id) == 2, (
        "analyze must gate exactly twice (outer first-pass + re-opened), with its "
        f"in-pass re-dispatch suppressed; got {agent_ids}"
    )
    # analyze's in-pass gate would sit strictly between the specify and plan firings —
    # i.e. immediately after them and before the re-opened gate. Assert it is absent by
    # checking the total firing count matches exactly 4 (specify + plan + analyze x2).
    assert len(records) == 4, (
        "expected 4 firings (specify in-pass, plan in-pass, analyze outer, analyze "
        f"re-opened) with analyze's in-pass firing suppressed; got {len(records)}: {agent_ids}"
    )


@pytest.mark.asyncio
async def test_nested_revision_keeps_distinct_threads_and_restores_the_outer_pass() -> None:
    """A-safety: a nested pass is SAFE — proven by driving one directly.

    Two guarantees: the nested pass mints DISTINCT ``:rev{N}`` ids rather than a second
    ``:rev1``, and its exit RESTORES the outer pass's ``revision_attempt`` /
    ``spec_revision_context`` instead of zeroing them while the outer pass is still on
    the stack.

    This drive stubs ``_run_review_gate``, so it bypasses the ISS-053 fence that now
    refuses ``update_specs`` at the in-pass gate, and passes ``allow_in_pass_gate`` so the
    ISS-072 suppression does not stop that gate opening in the first place. Both bypasses
    are deliberate and for the same reason: no client can reach this state any more, and
    this test keeps the nesting safety honest as defence in depth rather than letting it
    rot behind the fences.
    """
    run_id = "cycles-nested"
    records, thread_ids, _ectx, ordered, events = await _drive_cycles(
        run_id, {0, 1}, allow_in_pass_gate=True
    )
    _assert_sentinel_never_escapes(events)

    first_pass = f"{run_id}:{ordered[2].id}"

    assert len(thread_ids) == 7, (
        f"expected 1 first-pass + 3 outer-pass + 3 nested-pass dispatches; got {thread_ids}"
    )
    assert thread_ids[0] == first_pass, f"unexpected first-pass thread; got {thread_ids}"
    assert len(set(thread_ids)) == 7, (
        "two revision passes minted the SAME checkpoint thread id, so one is served the "
        f"other's conversation replay (the P23 class); got {thread_ids}"
    )

    # Firings: [0] outer, [1] in-pass (clicked -> nests), [2] the nested pass's own
    # in-pass gate, [3] the nested pass's re-open — reached with the OUTER pass still on
    # the stack — [4] the outer pass's re-open.
    assert len(records) == 5, (
        f"expected 5 gate firings for the nested drive; got {[r['firing'] for r in records]}"
    )
    after_inner = records[3]

    assert after_inner["revision_attempt"] == 1, (
        "the inner pass zeroed the OUTER pass's revision index while the outer pass was "
        "still running, so its remaining dispatches silently lose their :rev suffix; "
        f"expected 1, got {after_inner['revision_attempt']}"
    )
    assert after_inner["context_set"], (
        "the inner pass wiped the OUTER pass's analysis report mid-flight, so the outer "
        "pass's remaining dispatches compose without the revision block"
    )


# ===========================================================================
# Safety boundary — one cycle is unchanged (PASSES pre-fix; this is the dormancy guard)
# ===========================================================================


@pytest.mark.asyncio
async def test_single_cycle_shape_is_unchanged() -> None:
    """One revision cycle behaves exactly as it does today: 4 dispatches, every sub-run
    on ``:rev1``, and the consume-once scratch fields clear when the drive returns.

    Green BEFORE the engine change and green after — dormancy proven at the test level,
    not only at the golden level.
    """
    run_id = "cycles-single"
    _records, thread_ids, ectx, ordered, events = await _drive_cycles(run_id, {0})
    _assert_sentinel_never_escapes(events)

    first_pass = f"{run_id}:{ordered[2].id}"

    assert len(thread_ids) == 4, (
        f"one cycle is 1 first-pass + 3 sub-dispatches; got {thread_ids}"
    )
    assert thread_ids[0] == first_pass, f"unexpected first-pass thread; got {thread_ids}"
    sub_threads = thread_ids[1:]
    assert all(t.endswith(":rev1") for t in sub_threads), (
        f"a single cycle must still thread :rev1 throughout; got {sub_threads}"
    )
    assert first_pass not in sub_threads, (
        f"a revision dispatch reused the first pass's thread id: {sub_threads}"
    )

    assert ectx.revision_attempt == 0, (
        f"the revision index must clear when the pass returns; got {ectx.revision_attempt}"
    )
    assert not ectx.spec_revision_prior_artifact, (
        "the prior-artifact scratch field must be cleared when the sub-pipeline returns"
    )
    assert not getattr(ectx, "spec_revision_context", ""), (
        "the analysis-report scratch field must be cleared when the sub-pipeline returns"
    )
