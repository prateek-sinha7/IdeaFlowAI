"""agents/capabilities/strategies/single_shot.py — the ``single_shot`` strategy.

The trivial one-agent strategy: run a step's agent ONCE and re-yield its event
dicts unchanged. This is the non-build path every non-prototype step uses today
(``specify`` / ``plan`` / ``validate`` / ``ppt``) — the ``else`` branch of the
engine's per-step dispatch (``engine.py:1262-1269``). Lifted as a capability
behind the ``ExecutionStrategy`` port (``capabilities.base``).

INV-3 (WS-vocabulary parity): ``run`` is an async generator that yields the SAME
``{"type", "data"}`` dicts the run-one-agent primitive produces — the
``execute()`` seq-stamping chokepoint is untouched.

Import purity (import-linter / INV-13): this module imports NOTHING from
``agents.execution_engine`` or ``app.*`` and never constructs a deep-agent graph
itself. The agent loop is reached ONLY through the object-typed ``ctx.runner``
handle.

The ``ctx.runner`` contract this strategy calls against (the D-03 ``KernelServices``
handle attached to ``ExecutionContext.runner`` by ``execute()`` in 07-04):
  * ``run_agent(step, ctx) -> AsyncIterator[dict]`` — run the step's agent once
    (create_runner + astream + MODEL-02 fallback + deliverable readback all live
    inside the handle), yielding the engine's event dicts. The per-agent vs
    per-task thread-id shape (``f"{run_id}:{spec.id}"`` here) is the handle's
    concern, not the strategy's.
"""

from __future__ import annotations

from typing import Any, AsyncIterator

from agents.capabilities.registry import register


@register(
    "strategy",
    "single_shot",
    # EMP-02 (22-04): the default per-step strategy must be user-grantable — a
    # user-composed custom workflow runs one agent per step via single_shot, so a
    # trust="user" compile of ANY saved workflow's steps would otherwise reject the
    # safe default. Running one agent once carries no privilege (no exec/spawn/
    # network), so it is user-allowed like task_loop/fanout_batch/wave_scheduler.
    user_allowed=True,
    description="Run the step's agent exactly once and emit its output (the default strategy).",
)
class SingleShotStrategy:
    """Run one agent for the step and re-yield its events (``name='single_shot'``).

    Satisfies the ``ExecutionStrategy`` port structurally (``name`` + ``run``).
    """

    name = "single_shot"

    async def run(self, step: Any, ctx: Any) -> AsyncIterator[dict]:
        """Drive one step: call the run-one-agent primitive ONCE, re-yield events.

        Exactly one ``ctx.runner.run_agent`` call; every event it produces is
        re-yielded unchanged (INV-3). ``ctx`` is typed ``Any`` and the handle is
        reached dynamically so no kernel/app type is imported.

        Step-level condition (design-ingestor / Phase 1): if the compiled step
        declares a ``condition`` expression, evaluate it against
        ``ctx.od_context["source_type"]``. A False result short-circuits the
        strategy (yields nothing → the engine silently skips this step). The
        condition variable namespace is intentionally minimal: only
        ``source_type`` is exposed. Absent or empty condition ⇒ always run
        (dormant for every pre-Phase-1 step — INV-3 byte/event-identical).
        """
        # ── Condition evaluation ──────────────────────────────────────────────
        cond: str = getattr(step, "condition", "") or ""
        if cond:
            od: dict = getattr(ctx, "od_context", None) or {}
            source_type: str = od.get("source_type") or "catalog"
            try:
                # Restricted eval: only ``source_type`` in namespace; no builtins.
                # The condition is authored in trusted YAML files (trust="file"),
                # so eval is acceptable. Fail-open on any error so a mis-typed
                # condition never silently blocks a run.
                _result = bool(
                    eval(cond, {"__builtins__": {}}, {"source_type": source_type})  # noqa: S307
                )
            except Exception:  # noqa: BLE001
                _result = True  # fail-open: run the step if condition can't evaluate
            if not _result:
                return  # condition False → skip step, yield nothing

        async for event in ctx.runner.run_agent(step, ctx):
            yield event
