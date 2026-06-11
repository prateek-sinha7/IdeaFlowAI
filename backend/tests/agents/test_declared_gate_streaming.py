"""Declared-gate STREAMING regression (Phase 13 / F1 / GAP 1).

A manifest-declared ``gates: [human]`` step must surface ``review_gate_ready`` to
the ``engine.execute()`` consumer (the WS layer) BEFORE the gate awaits the
approval response. Pre-fix, ``HumanGate.evaluate`` consumed the whole
``run_human_gate`` delegate generator into a list, so the ready event reached the
consumer only AFTER the gate had already been unblocked — a real UI run hung at
the first declared gate with no signal.

This test drives the DECLARED-gate path end-to-end over the public
``engine.execute()`` async generator, event by event, with NO auto-approve
workaround (the anti-pattern in ``live_harness.py``'s auto-approve wrapper that
papered over this gap). It approves a gate ONLY after its ``review_gate_ready``
arrives — exactly what ``websocket.py``'s ``approve_review`` handler does via
``store.set_review_response(gate_key, approved=True)``.

Against the PRE-fix buffering behavior the generator blocks inside gate
evaluation without ever yielding ready, so the bounded per-event timeout fails
the test instead of hanging CI.

Offline-safe: scripted model only — no Bedrock, no Postgres, no Chromium. The
shared harness conventions (RUNS_ROOT temp dir, InMemory checkpointer) come from
``tests/agents/_scripted_model`` at import.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest

from tests.agents._scripted_model import (
    _RUNS_ROOT,
    ScriptedFakeChatModel,
    _scripts_for,
)

# Per-event bound: pre-fix code never yields review_gate_ready (the gate buffers
# until approval, which never comes) → this timeout fails the test deterministically.
_EVENT_TIMEOUT_S = 30.0


@pytest.mark.asyncio
async def test_declared_human_gate_streams_ready_before_approval_and_resumes() -> None:
    """F1: ready received WHILE PAUSED → approve → resume → pipeline_complete.

    Scaffolds a prototype run exactly as ``_scripted_model._drive('prototype')``
    does, with TWO deliberate differences:

      (a) ``engine._run_review_gate`` is NOT monkeypatched — the declared
          ``gates:[human]`` steps (prototype-specify / prototype-plan) must reach
          the REAL pause (``await event.wait()``);
      (b) ``gate_agent_ids=[]`` is passed to ``execute()`` so the legacy inline
          ``_should_gate`` path stays silent and ONLY the manifest-declared gate
          path is exercised.
    """
    import agents.execution_engine.engine as engine_mod
    import agents.factory as factory_mod
    from agents.execution_engine.engine import ExecutionEngine
    from agents.registry import get_pipeline_agents
    from app.core.config import settings as _settings

    # RunSandbox reads settings.RUNS_ROOT at __init__ — force the temp dir at
    # runtime (the env var alone is too late if settings loaded earlier).
    _settings.RUNS_ROOT = _RUNS_ROOT

    # ── Disable the auto-clarify override (needs live WS round-trips). ────────
    _orig_compile_for_run = engine_mod.compile_for_run

    def _patched_compile_for_run(pipeline_type, _orig=_orig_compile_for_run):
        compiled = _orig(pipeline_type)
        compiled.clarify.mode = "off"
        return compiled

    engine_mod.compile_for_run = _patched_compile_for_run

    specs = get_pipeline_agents("prototype")

    # ── Per-agent scripted model factory (no network). ────────────────────────
    _orig_create_runner = factory_mod.create_runner
    _orig_engine_create_runner = getattr(engine_mod, "create_runner", None)

    def _patched_create_runner(agent_id, ctx, **kw):
        ctx.model = ScriptedFakeChatModel(_scripts_for(agent_id))
        return _orig_create_runner(agent_id, ctx, **kw)

    factory_mod.create_runner = _patched_create_runner
    engine_mod.create_runner = _patched_create_runner

    engine = ExecutionEngine()

    # ── Neutralise the planner (real LLM call) → default PROCEED context. ─────
    async def _fake_run_planner(
        user_message, pipeline_run_id, model_id, cancel_event, ptype="custom", **kwargs
    ):
        return engine._default_planning_context(user_message), "PROCEED"

    engine._run_planner = _fake_run_planner  # type: ignore[assignment]

    # ── Artifact store WRITES → no-op (no DB coupling). The review pause/resume
    #    API (get_review_event / set_review_response) stays REAL — it is the
    #    surface under test. NOTE: _run_review_gate is NOT noop'd here (the
    #    deliberate difference from _drive). ───────────────────────────────────
    _orig_store_write = getattr(engine._store, "store", None)

    async def _noop_store(*a, **k):
        return "artifact-id"

    engine._store.store = _noop_store  # type: ignore[assignment]

    run_id = f"declared-gate-{uuid.uuid4().hex[:8]}"

    # Prototype agents declare injects=[template, design_system, ...] — supply a
    # minimal od_context so prompt composition succeeds (mirrors _drive).
    od_context = {
        "template_body": (
            "## Workflow\nUse .card and .grid classes. "
            "Build pages into <section data-page>."
        ),
        "template_id": "web-prototype",
        "ds_id": "default",
        "ds_body": (
            ":root{--bg:#fff;--fg:#111;--accent:#06f;--surface:#f6f6f6;"
            "--border:#ddd;--muted:#888;}"
        ),
        "craft_block": "Keep markup semantic; wire every nav link.",
        "is_design_system_required": True,
    }

    events: list[dict] = []
    approved_gate_keys: list[str] = []

    def _approved_keys_observed() -> set[str]:
        """gate_keys for every review_gate_approved event received so far."""
        return {
            f"{run_id}:{(e.get('data') or {}).get('agent_id')}"
            for e in events
            if e.get("type") == "review_gate_approved"
        }

    gen = engine.execute(
        agents=list(specs),
        user_message="Build me a thing for managing tasks.",
        pipeline_run_id=run_id,
        pipeline_type="prototype",
        user_id="harness-user",
        od_context=od_context,
        gate_agent_ids=[],  # silence the legacy inline path — declared gates ONLY
    )

    try:
        while True:
            try:
                # Bounded per-event wait: pre-fix, the generator blocks inside the
                # buffering gate evaluation and NEVER yields ready → TimeoutError
                # fails the test instead of hanging CI.
                ev = await asyncio.wait_for(gen.__anext__(), timeout=_EVENT_TIMEOUT_S)
            except StopAsyncIteration:
                break
            events.append(ev)

            if ev.get("type") == "review_gate_ready":
                gate_key = ev["data"]["gate_key"]
                # ── THE F1 REGRESSION ASSERTION ──────────────────────────────
                # ready must arrive WHILE THE RUN IS PAUSED — i.e. before any
                # approval for this gate_key was observed. Pre-fix, the buffered
                # events arrived only after the gate resolved, so approved would
                # already be visible (or, live, ready never arrived at all).
                assert gate_key not in _approved_keys_observed(), (
                    f"review_gate_ready for {gate_key} arrived AFTER its "
                    "review_gate_approved — gate events were buffered, not "
                    "streamed (F1 regression)"
                )
                assert gate_key not in approved_gate_keys, (
                    f"duplicate review_gate_ready for already-approved {gate_key}"
                )
                # Approve ONLY in response to ready — the exact call the
                # websocket.py approve_review handler makes. No blind pre-approval.
                await engine._store.set_review_response(gate_key, approved=True)
                approved_gate_keys.append(gate_key)
    finally:
        await gen.aclose()
        # Restore harness patches (repeated runs in one pytest process).
        factory_mod.create_runner = _orig_create_runner
        if _orig_engine_create_runner is not None:
            engine_mod.create_runner = _orig_engine_create_runner
        engine_mod.compile_for_run = _orig_compile_for_run
        if _orig_store_write is not None:
            engine._store.store = _orig_store_write  # type: ignore[assignment]
        else:
            # The patch CREATED the instance attribute — remove it again.
            try:
                del engine._store.store
            except AttributeError:
                pass

    types = [e.get("type") for e in events]

    # ── Post-conditions ───────────────────────────────────────────────────────
    # The prototype manifest declares gates:[human] on prototype-specify AND
    # prototype-plan — both must have paused and been approved through this flow.
    assert len(approved_gate_keys) >= 1, "no review_gate_ready was ever received"
    assert len(approved_gate_keys) == 2, (
        f"expected the 2 declared gated steps (specify, plan) to pause; "
        f"approved={approved_gate_keys}"
    )

    # Each ready precedes its approved in the RECEIVED event order.
    for gate_key in approved_gate_keys:
        agent_id = gate_key.split(":", 1)[1]
        ready_idx = next(
            i for i, e in enumerate(events)
            if e.get("type") == "review_gate_ready"
            and (e.get("data") or {}).get("agent_id") == agent_id
        )
        approved_idx = next(
            i for i, e in enumerate(events)
            if e.get("type") == "review_gate_approved"
            and (e.get("data") or {}).get("agent_id") == agent_id
        )
        assert ready_idx < approved_idx, (
            f"review_gate_ready (idx {ready_idx}) did not precede "
            f"review_gate_approved (idx {approved_idx}) for {gate_key}"
        )

    # The run RESUMED after approval and finished.
    assert "pipeline_complete" in types, (
        f"run never reached pipeline_complete after gate approval; got {types[-5:]}"
    )
