"""tests/agents/test_model_fallback.py — MODEL-02 APPROACH-B fallback (06-05).

The one genuinely-new mechanism of Phase 6: an engine-level rebuild-and-retry loop
above the botocore retries. On a classified transient throttle the runner re-raises
(B1, ``deep_agent_runner.py``), the engine advances ``ctx.model_resolver`` to the next
chain id, rebuilds via ``create_runner``, and re-invokes — bounded by chain length;
chain exhaustion re-raises the last error; non-transient errors propagate immediately
with NO model switch.

Why APPROACH B (NOT ``Runnable.with_fallbacks``): RESEARCH proved ``with_fallbacks``
does not compose through the deepagents ``astream_events`` graph (``RunnableWithFallbacks``
lacks ``bind_tools``; the runner swallows model exceptions). The engine owns the retry
loop; ``build_model`` stays the unchanged single source. (06-RESEARCH.md § MUST RESOLVE #1.)

Offline contract (D-06): no live Bedrock. We drive ``ExecutionEngine._run_agent`` directly
with an ``ExecutionContext`` whose ``model_resolver`` is seeded + has an armed chain, and we
patch ``create_runner`` so each rebuild gets a ``ScriptedFakeChatModel`` keyed on the
CURRENT chain id (``ctx.model``): the flagged id raises the synthetic throttle, the others
stream a deterministic turn. So a throttle on chain[0] forces the engine to advance and
rebuild with chain[1], where the run completes — observably, on the fallback model.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

# Importing the harness sets RUNS_ROOT to a temp dir + forces the InMemory checkpointer
# (no Postgres / no creds) BEFORE app.core.config loads — keep this import first.
from tests.agents._scripted_model import (  # noqa: E402  (import-for-side-effects order)
    ScriptedFakeChatModel,
    ScriptedNonTransientError,
    ScriptedThrottleError,
    _ScriptedTurn,
)

# Two real catalog ids spanning two cost classes, so the resolver's tier-descent
# derives a concrete fallback chain (standard → [cheap]). Chosen from the live
# catalog (ModelCatalog().list()): sonnet = standard, haiku = cheap.
PRIMARY_STANDARD = "eu.anthropic.claude-sonnet-4-5-20250929-v1:0"  # standard
FALLBACK_CHEAP = "eu.anthropic.claude-haiku-4-5-20251001-v1:0"     # cheap
ONLY_CHEAP = FALLBACK_CHEAP  # cheap → chain_for == [] → single-entry chain


def _text_turn(tag: str) -> list[_ScriptedTurn]:
    """A deterministic text-only turn whose text embeds ``tag`` so a test can assert
    WHICH model produced the completing stream."""
    return [_ScriptedTurn(texts=[f"completed on {tag}. "], usage=(5, 3))]


async def _drive_one_agent(
    *,
    primary: str,
    throttle_ids: set[str],
    non_transient_ids: set[str] | None = None,
):
    """Run a single text-only agent through ``ExecutionEngine._run_agent`` offline with
    an armed fallback chain, returning ``(results, built_for, events, thread_ids)``.

    ``create_runner`` is patched so each (re)build injects a ``ScriptedFakeChatModel``
    keyed on the CURRENT resolved id (``ctx.model``): an id in ``throttle_ids`` raises a
    synthetic transient throttle; an id in ``non_transient_ids`` raises a non-transient
    error; every other id streams a tagged text turn. ``completing_model_ids`` records the
    id each rebuilt runner was constructed for (so the test sees the advance order).
    """
    import agents.factory as factory_mod
    import agents.execution_engine.engine as engine_mod
    from agents.execution_engine.engine import ExecutionEngine
    from agents.execution_engine.context import ExecutionContext
    from agents.model_policy import ModelResolver
    from agents.capabilities.model_catalog import ModelCatalog
    from agents.loader import load_agent_spec
    from app.core.config import settings as _settings

    # Force RUNS_ROOT to the harness temp dir at RUNTIME (settings may have been
    # instantiated earlier with the default /app/runs, read-only here) — mirrors _drive.
    from tests.agents._scripted_model import _RUNS_ROOT

    _settings.RUNS_ROOT = _RUNS_ROOT

    non_transient_ids = non_transient_ids or set()
    built_for: list[str] = []
    # CR-02: record the checkpoint thread_id each (re)build was constructed for, so
    # tests can assert a retry rebuild uses a FRESH thread_id (clean restart, no
    # stale-checkpoint resume) rather than reusing the primary attempt's id.
    thread_ids: list[str | None] = []

    _orig_create_runner = factory_mod.create_runner
    _orig_engine_create_runner = getattr(engine_mod, "create_runner", None)

    def _patched_create_runner(agent_id, ctx, **kw):
        model_id = ctx.model
        built_for.append(model_id)
        thread_ids.append(kw.get("thread_id"))
        if model_id in throttle_ids:
            ctx.model = ScriptedFakeChatModel([], raise_exc=ScriptedThrottleError())
        elif model_id in non_transient_ids:
            ctx.model = ScriptedFakeChatModel([], raise_exc=ScriptedNonTransientError())
        else:
            ctx.model = ScriptedFakeChatModel(_text_turn(model_id))
        return _orig_create_runner(agent_id, ctx, **kw)

    factory_mod.create_runner = _patched_create_runner
    engine_mod.create_runner = _patched_create_runner

    engine = ExecutionEngine()

    # Artifact store writes → no-op (avoid DB coupling, stay deterministic / offline).
    async def _noop_store(*a, **k):
        return "artifact-id"

    engine._store.store = _noop_store  # type: ignore[assignment]

    # No-op the typed dual-write (no workflow_runs FK row in this offline unit context).
    async def _noop_dual_write(*a, **k):
        return None

    engine._dual_write_artifact = _noop_dual_write  # type: ignore[assignment]

    # A real text-only agent spec (tools=[]); the deliverable is its streamed text.
    spec = load_agent_spec("domain-analyst")

    ectx = ExecutionContext(run_id="fallback-test-run", owner_id="anon")
    ectx.disk_principal = "anon"
    resolver = ModelResolver(
        session_model_id=primary,
        haiku_default=_settings.BEDROCK_INFERENCE_PROFILE_ID,
        catalog=ModelCatalog(),
    )
    # Arm the active fallback chain the engine retry loop drives (06-03 set_chain/advance).
    resolver.set_chain(primary)
    ectx.model_resolver = resolver

    results: list[dict] = []
    events: list[dict] = []

    async def _run():
        async for ev in engine._run_agent(
            spec,
            0,
            [spec],
            "Build me a thing.",
            None,  # sandbox: text-only agent never touches it (prototype-only read)
            "fallback-test-run",
            "user_stories",
            engine._default_planning_context("Build me a thing."),
            None,
            None,
            primary,
            results,
            None,
            ectx,
        ):
            events.append(ev)

    try:
        await _run()
    finally:
        factory_mod.create_runner = _orig_create_runner
        if _orig_engine_create_runner is not None:
            engine_mod.create_runner = _orig_engine_create_runner

    return results, built_for, events, thread_ids


# ===========================================================================
# Test 1 — throttle on chain[0] advances to chain[1] and completes there.
# ===========================================================================


@pytest.mark.asyncio
async def test_throttle_advances() -> None:
    """A 2-entry chain [standard, cheap]: the standard primary throttles, the engine
    advances to the cheap fallback and completes the run on it (no live Bedrock)."""
    results, built_for, _events, thread_ids = await _drive_one_agent(
        primary=PRIMARY_STANDARD,
        throttle_ids={PRIMARY_STANDARD},
    )

    # The engine rebuilt twice: first for the throttling primary, then the fallback.
    assert built_for == [PRIMARY_STANDARD, FALLBACK_CHEAP], built_for
    # The run completed — the deliverable reflects the FALLBACK model's stream.
    assert results, "expected a completed agent result"
    assert f"completed on {FALLBACK_CHEAP}" in results[-1]["output"]
    # CR-02: the retry rebuild MUST use a FRESH checkpoint thread_id (clean
    # restart, no stale-checkpoint resume) — distinct from the primary attempt's
    # thread_id. The primary keeps the base id (INV-3 parity); the retry derives
    # a per-attempt id from it.
    assert len(thread_ids) == 2, thread_ids
    primary_tid, retry_tid = thread_ids
    assert retry_tid != primary_tid, (
        f"retry reused the primary thread_id {primary_tid!r} — would resume a "
        f"stale checkpoint instead of restarting cleanly (CR-02)"
    )
    assert retry_tid.startswith(primary_tid), (
        f"retry thread_id {retry_tid!r} should derive from the base "
        f"{primary_tid!r}"
    )


# ===========================================================================
# Test 2 — every chain entry throttles → the last error is re-raised.
# ===========================================================================


def _agent_error_events(events: list[dict]) -> list[dict]:
    return [e for e in events if e.get("type") == "agent_error"]


@pytest.mark.asyncio
async def test_chain_exhaustion_reraises() -> None:
    """A single-entry chain [cheap] (cheap has no tier-descent fallback): it throttles,
    the chain exhausts, and the throttle ESCAPES the retry loop — surfacing as a visible
    ``agent_error`` carrying the throttle message (the run fails with that error, NOT the
    old silent blank where the runner swallowed it and the engine ignored it). The chain
    is walked exactly once (bounded), no model switch beyond the single entry."""
    _results, built_for, events, _thread_ids = await _drive_one_agent(
        primary=ONLY_CHEAP,
        throttle_ids={ONLY_CHEAP},
    )

    # Only the single chain entry was ever built — no phantom advance past the end.
    assert built_for == [ONLY_CHEAP], built_for
    # The throttle surfaced (not a silent blank): a visible agent_error with its message.
    errs = _agent_error_events(events)
    assert errs, "expected the exhausted throttle to surface as an agent_error event"
    assert "throttle" in errs[-1]["data"]["error"].lower()
    # No successful completion result was recorded (the run failed with the error).
    assert not _results, "exhausted chain must not record a completed result"


@pytest.mark.asyncio
async def test_multi_entry_chain_exhaustion_reraises() -> None:
    """A 2-entry chain [standard, cheap] where BOTH throttle → the engine advances
    through the WHOLE chain (bounded by chain length, no infinite loop), then the last
    throttle escapes the retry loop as a visible ``agent_error`` (not a silent blank)."""
    _results, built_for, events, _thread_ids = await _drive_one_agent(
        primary=PRIMARY_STANDARD,
        throttle_ids={PRIMARY_STANDARD, FALLBACK_CHEAP},
    )

    # The engine advanced through every chain entry exactly once (bounded retry).
    assert built_for == [PRIMARY_STANDARD, FALLBACK_CHEAP], built_for
    errs = _agent_error_events(events)
    assert errs, "expected the exhausted throttle to surface as an agent_error event"
    assert "throttle" in errs[-1]["data"]["error"].lower()
    assert not _results, "exhausted chain must not record a completed result"


# ===========================================================================
# Test 3 — a non-transient error propagates immediately, NO model switch.
# ===========================================================================


@pytest.mark.asyncio
async def test_non_transient_propagates() -> None:
    """A non-transient error (ValidationException analogue) is NOT classified as a
    throttle: the runner keeps the existing ``{"type":"error"}`` path (no re-raise), so
    the engine consume loop sees no throttle and NEVER advances the chain — only the
    primary runner is ever built (no model switch). Parity with today's non-throttle
    error handling is preserved (the run ends without a model switch, not with one)."""
    _results, built_for, _events, _thread_ids = await _drive_one_agent(
        primary=PRIMARY_STANDARD,
        throttle_ids=set(),
        non_transient_ids={PRIMARY_STANDARD},
    )

    # The engine never advanced the chain: only the primary runner was ever built.
    assert built_for == [PRIMARY_STANDARD], built_for
