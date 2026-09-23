"""agents/capabilities/strategies/parallel_group.py — the ``parallel_group`` strategy.

Sibling-group parallelism: a parent step whose manifest declares
``subagents: {mode: parallel, steps: [...]}`` runs its N ALREADY-DISTINCT children
concurrently, then runs its own agent once over their results.

Why this exists
---------------
``mode: parallel`` used to be decorative. The compiler correctly emitted no
dependency edge between siblings, but the engine's dispatch loop takes the
compiler's flat topological order and awaits one step at a time — so ``parallel``
and ``sequential`` produced byte-identical dispatch. Measured on
``sample_subagents_parallel``: sibling B started 13ms after sibling A finished, zero overlap.

What this does NOT do
---------------------
It holds no spawn, worker-selection, concurrency, isolation, merge, budget or
cancellation logic. All of that already exists in the kernel ``run_fanout``
(``execution_engine/fanout.py``: ``asyncio.gather`` over
``asyncio.Semaphore(min(declared, DEFAULT_MAX_CONCURRENCY))``), which is the single
spawn home (INV-12). This strategy only shapes N requests and hands them over —
the same thin-seam shape as ``fanout_batch`` and ``wave_scheduler``.

The difference from ``fanout_batch`` is only where the work list comes from.
``fanout_batch`` parses a task list out of an upstream step's output and clones ONE
worker template N times. Here the N workers are declared in the manifest as distinct
children, each with its own agent id and its own prompt, so the request list is built
from ``FanoutSpec.workers`` (compiler-populated from the child ids) instead of from a
parser. No ``task_source`` is involved and none is required.

Two phases, in order
--------------------
1. Spawn every child through ``ctx.runner.run_fanout`` — these run CONCURRENTLY.
2. Run the parent's own agent once via ``ctx.runner.run_agent`` — the same call
   ``single_shot`` makes. By then the children's artifacts are on disk, so the
   parent's roster block and its ``read_file`` calls see them.

Import purity (import-linter / INV-13): nothing from ``agents.execution_engine`` or
``app.*`` is imported; every kernel primitive is reached through the object-typed
``ctx.runner`` handle.
"""

from __future__ import annotations

import logging
from typing import Any, AsyncIterator

from agents.capabilities.registry import register
from agents.capabilities.strategies._fanout_stream import stream_fanout

logger = logging.getLogger(__name__)


@register(
    "strategy",
    "parallel_group",
    # A user-composed workflow reaches this strategy by declaring
    # `subagents: {mode: parallel}` in the composer, and the compiler sets the
    # strategy name itself — a trust="user" re-compile of any saved workflow using
    # the mode would be rejected otherwise. The privilege it carries is spawning
    # sub-agents, which the kernel already bounds: allowed_workers + the agent
    # registry gate every worker pre-spawn, DEFAULT_MAX_CONCURRENCY caps
    # concurrency, and the fan-out budget caps total spawns.
    user_allowed=True,
    description=(
        "Run a step's declared sibling sub-agents concurrently, then run the step's "
        "own agent over their results."
    ),
    config_schema={
        "type": "object",
        "properties": {
            "max_parallel": {
                "type": "integer",
                "description": (
                    "Cap on concurrent siblings. Clamped by the kernel to "
                    "DEFAULT_MAX_CONCURRENCY regardless of what is declared."
                ),
                "minimum": 1,
            },
        },
    },
)
class ParallelGroupStrategy:
    """Spawn the declared sibling children concurrently, then run the parent.

    Satisfies the ``ExecutionStrategy`` port structurally (``name`` + ``run``).
    """

    name = "parallel_group"

    async def run(self, step: Any, ctx: Any) -> AsyncIterator[dict]:
        runner = ctx.runner

        # The child agent ids the compiler recorded on the parent's FanoutSpec.
        # `workers` is the heterogeneous-fan-out field run_fanout already honors:
        # request i carrying agent "self" maps to workers[i], and each mapped name
        # is validated against allowed_workers + the agent registry BEFORE any
        # spawn (FANOUT-03). So naming the children here cannot smuggle in a worker
        # the workflow did not declare.
        fanout = getattr(step, "fanout", None)
        workers = list(getattr(fanout, "workers", None) or []) if fanout else []

        if not workers:
            # Nothing declared to spawn. Degrade to single_shot rather than
            # failing the step: a parent with an empty group is still a valid
            # step, it just has no children to wait for.
            logger.warning(
                "parallel_group: step %s declares no child workers — running the "
                "parent alone",
                getattr(step, "agent_id", "?"),
            )
        else:
            # One request per declared child. `input` is empty on purpose: each
            # child is a fully-specified step with its own prompt (compiled from
            # the manifest), not a slice of a shared task list. Naming the agent
            # explicitly — rather than "self" — is what makes this a heterogeneous
            # fan-out instead of N clones of the parent.
            requests = [{"agent": w, "input": ""} for w in workers]
            logger.info(
                "parallel_group: spawning %d sibling workers for %s: %s",
                len(requests),
                getattr(step, "agent_id", "?"),
                workers,
            )

            # Live per-child streaming (agent_start/agent_chunk/tool_call/
            # tool_result/agent_complete) rides a side-channel queue merged in by
            # stream_fanout: run_fanout still yields its own lifecycle events
            # (subagent_spawned/subagent_result) normally, and each worker's raw
            # per-agent events are interleaved as they arrive rather than after
            # the whole fan-out finishes.
            async for event in stream_fanout(runner, requests, ctx, step=step):
                yield event

        # Phase 2 — the parent's own single run, identical to single_shot. It runs
        # AFTER the fan-out completes (run_fanout does not return until every worker
        # has finished or been cancelled), so the children's artifacts are already
        # on disk and in the artifact graph when the parent's roster is built.
        async for event in runner.run_agent(step, ctx):
            yield event
