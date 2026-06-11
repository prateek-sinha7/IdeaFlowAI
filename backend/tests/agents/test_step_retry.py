"""tests/agents/test_step_retry.py — RESUME-02 (12-02) per-step retry/reuse wrapper.

The single engine-side retry/reuse wrapper (``ExecutionEngine._dispatch_step_with_retry``)
is driven OFFLINE against a FAKE ``ctx.runner`` + a fake ExecutionStrategy (the
``test_strategies.py`` pattern — no real agent, no Chromium, no DB). The fake strategy
scripts a transient-throttle / non-transient / success sequence and records every
invocation, so the tests assert:

  (1) a transient failure then success retries EXACTLY the declared count then completes
      with a visible ``step_completed`` (and produced output_ref_id);
  (2) a transient failure that NEVER recovers retries EXACTLY ``max_attempts`` times then
      surfaces a visible error (re-raised — NOT swallowed);
  (3) a NON-transient error does NOT retry (one invocation, error surfaced);
  (4) a re-entry with the SAME (run_id, step_id, input_hash) reuses the artifact — the
      strategy invocation count proves ZERO second agent call;
  (5) a step with NO declared retry runs the UNCHANGED legacy path (the wrapper is dormant).

``_retry_sleep`` is monkeypatched to a no-op so the bounded-backoff loop stays fast.
"""

from __future__ import annotations

import pytest

import agents.execution_engine.engine as engine_mod
from agents.artifacts.graph import ArtifactGraph
from agents.execution_engine.engine import ExecutionEngine
from agents.workflows.plan import RetryPolicy, Step

# Reuse the synthetic error shapes the 06-05 fallback tests already defined: the
# throttle classifies True via _is_transient_throttle, the non-transient classifies
# False. Importing the harness module also pins RUNS_ROOT to a temp dir (side-effect).
from tests.agents._scripted_model import (  # noqa: E402
    ScriptedNonTransientError,
    ScriptedThrottleError,
)


# ===========================================================================
# Fakes — a minimal ExecutionStrategy + ExecutionContext stand-in
# ===========================================================================


class _FakeRunner:
    """Stand-in for ctx.runner (KernelServices) — only the input-hash reads it."""

    def __init__(self, ordered_agents=None, user_message="brief") -> None:
        self._ordered_agents = ordered_agents or []
        self.user_message = user_message


class _FakeCtx:
    """Minimal ExecutionContext stand-in carrying the fields the wrapper reads."""

    def __init__(self, *, run_id="run-1", scoped_store=None, runner=None) -> None:
        self.run_id = run_id
        self.owner_id = "owner-1"
        self.workspace_id = "ws-1"
        self.artifacts = ArtifactGraph()
        self.scoped_store = scoped_store
        self.runner = runner or _FakeRunner()
        self.current_task_block = ""


class _FakeStrategy:
    """A scripted strategy: each call either raises a scripted exc or 'produces'.

    ``script`` is a list of exceptions (or ``None`` for success). On a success
    call it writes a ref to ``ctx.artifacts`` (simulating an agent deliverable)
    and yields one ``agent_chunk`` event. ``calls`` counts every ``run`` entry.
    """

    name = "fake"

    def __init__(self, script, *, step_agent="agent-a", produce=True) -> None:
        self._script = list(script)
        self._idx = 0
        self.calls = 0
        self._step_agent = step_agent
        self._produce = produce

    async def run(self, step, ctx):
        self.calls += 1
        exc = self._script[self._idx] if self._idx < len(self._script) else None
        self._idx += 1
        if exc is not None:
            raise exc
        if self._produce:
            ctx.artifacts.write_ref(
                run_id=ctx.run_id,
                owner_id=ctx.owner_id,
                workspace_id=ctx.workspace_id,
                kind="summary",
                producer_step=self._step_agent,
                producer_agent=self._step_agent,
                task_id=None,
                content="deliverable body",
                location="memory://out",
            )
        yield {"type": "agent_chunk", "data": {"text": "ok"}}


class _RunEventRow:
    """A RunEvent-like row (type + payload_json) the reuse-lookup scans."""

    def __init__(self, type, payload_json) -> None:
        self.type = type
        self.payload_json = payload_json


class _FakeStore:
    """A scoped_store stand-in whose read_events returns pre-seeded rows."""

    def __init__(self, rows=None) -> None:
        self._rows = list(rows or [])

    async def read_events(self, run_id, after_seq):
        return list(self._rows)


def _step(*, max_attempts, agent_id="agent-a", backoff=0.0, on=None):
    retry = (
        RetryPolicy(max_attempts=max_attempts, backoff_seconds=backoff, on=on or ["transient"])
        if max_attempts is not None
        else None
    )
    return Step(agent_id=agent_id, strategy="fake", retry=retry)


async def _collect(engine, step, ctx, strategy):
    return [ev async for ev in engine._dispatch_step_with_retry(step, ctx, strategy)]


@pytest.fixture(autouse=True)
def _noop_sleep(monkeypatch):
    """Monkeypatch the module-level backoff seam to a no-op (keep tests fast)."""
    async def _noop(_seconds):
        return None

    monkeypatch.setattr(engine_mod, "_retry_sleep", _noop)


# ===========================================================================
# (1) transient-then-success retries the declared count then completes
# ===========================================================================


@pytest.mark.asyncio
async def test_transient_then_success_retries_then_completes():
    engine = ExecutionEngine()
    # Throttle on attempt 1, succeed on attempt 2 (max_attempts=3 allows it).
    strategy = _FakeStrategy([ScriptedThrottleError(), None])
    ctx = _FakeCtx()
    step = _step(max_attempts=3)

    events = await _collect(engine, step, ctx, strategy)

    # Exactly 2 strategy invocations (1 failed transient + 1 success).
    assert strategy.calls == 2
    types = [e["type"] for e in events]
    assert "step_retry" in types
    assert types.count("step_retry") == 1  # one retry before success
    # Visible completion carrying the produced output_ref_id.
    completed = [e for e in events if e["type"] == "step_completed"]
    assert len(completed) == 1
    assert completed[0]["data"]["output_ref_id"] is not None
    assert completed[0]["data"]["input_hash"]


# ===========================================================================
# (2) transient that never recovers retries max_attempts then surfaces error
# ===========================================================================


@pytest.mark.asyncio
async def test_transient_never_recovers_exhausts_then_raises():
    engine = ExecutionEngine()
    # Every attempt throttles → never recovers.
    strategy = _FakeStrategy([ScriptedThrottleError()] * 5)
    ctx = _FakeCtx()
    step = _step(max_attempts=3)

    collected = []
    with pytest.raises(ScriptedThrottleError):
        async for ev in engine._dispatch_step_with_retry(step, ctx, strategy):
            collected.append(ev)

    # Bounded strictly at max_attempts (T-12-02-DOS): 3 invocations total.
    assert strategy.calls == 3
    # Exactly max_attempts - 1 retry events (the last failure re-raises, no retry).
    assert [e["type"] for e in collected].count("step_retry") == 2


# ===========================================================================
# (3) a non-transient error does NOT retry
# ===========================================================================


@pytest.mark.asyncio
async def test_non_transient_does_not_retry():
    engine = ExecutionEngine()
    strategy = _FakeStrategy([ScriptedNonTransientError()])
    ctx = _FakeCtx()
    step = _step(max_attempts=3)

    collected = []
    with pytest.raises(ScriptedNonTransientError):
        async for ev in engine._dispatch_step_with_retry(step, ctx, strategy):
            collected.append(ev)

    # One invocation only — a non-transient error propagates immediately.
    assert strategy.calls == 1
    assert [e["type"] for e in collected].count("step_retry") == 0


# ===========================================================================
# (4) a matching (run_id, step_id, input_hash) reuses with ZERO agent calls
# ===========================================================================


@pytest.mark.asyncio
async def test_reuse_skips_agent_invocation():
    engine = ExecutionEngine()
    strategy = _FakeStrategy([None])  # would produce if ever called
    ctx = _FakeCtx()
    step = _step(max_attempts=3)

    # Seed a prior produced artifact, then compute the input_hash the wrapper
    # will compute (the artifact is part of the hashed upstream set). Seed a
    # step_completed event under the SAME (step_id, input_hash) whose
    # output_ref_id points at the artifact that still exists in the graph.
    existing = ctx.artifacts.write_ref(
        run_id=ctx.run_id, owner_id=ctx.owner_id, workspace_id=ctx.workspace_id,
        kind="summary", producer_step="agent-a", producer_agent="agent-a",
        task_id=None, content="prior body", location="memory://prior",
    )
    input_hash = engine._compute_step_input_hash(step, ctx)
    ctx.scoped_store = _FakeStore([
        _RunEventRow("step_completed", {
            "step": "agent-a", "input_hash": input_hash, "output_ref_id": existing.id,
        })
    ])

    events = await _collect(engine, step, ctx, strategy)

    # ZERO agent invocations — the artifact was reused.
    assert strategy.calls == 0
    reused = [e for e in events if e["type"] == "step_reused"]
    assert len(reused) == 1
    assert reused[0]["data"]["output_ref_id"] == existing.id
    assert reused[0]["data"]["input_hash"] == input_hash


@pytest.mark.asyncio
async def test_no_reuse_when_store_empty_reexecutes():
    """A None/empty store (offline) → NO reuse → the agent runs (reuse minus one)."""
    engine = ExecutionEngine()
    strategy = _FakeStrategy([None])
    ctx = _FakeCtx(scoped_store=None)  # offline-safe → re-execute
    step = _step(max_attempts=3)

    events = await _collect(engine, step, ctx, strategy)

    # No prior completion → exactly ONE invocation (the reuse path's count + 1).
    assert strategy.calls == 1
    assert [e["type"] for e in events].count("step_reused") == 0
    assert [e["type"] for e in events].count("step_completed") == 1


# ===========================================================================
# (5) no declared retry → the wrapper is DORMANT (legacy path, no extra events)
# ===========================================================================


@pytest.mark.asyncio
async def test_no_retry_declared_runs_legacy_path():
    engine = ExecutionEngine()
    strategy = _FakeStrategy([None])
    ctx = _FakeCtx()
    step = _step(max_attempts=None)  # retry=None → dormant

    events = await _collect(engine, step, ctx, strategy)

    # Exactly the strategy's own events — NO step_retry/step_reused/step_completed.
    assert strategy.calls == 1
    types = {e["type"] for e in events}
    assert types == {"agent_chunk"}


@pytest.mark.asyncio
async def test_zero_max_attempts_runs_legacy_path():
    """max_attempts == 0 is also dormant (byte-identical to today)."""
    engine = ExecutionEngine()
    strategy = _FakeStrategy([None])
    ctx = _FakeCtx()
    step = _step(max_attempts=0)

    events = await _collect(engine, step, ctx, strategy)

    assert strategy.calls == 1
    assert {e["type"] for e in events} == {"agent_chunk"}
