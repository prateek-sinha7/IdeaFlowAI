"""agents/capabilities/strategies/fanout_batch.py — the ``fanout_batch`` strategy.

The DECLARATIVE fan-out entry point (FANOUT-02): a step whose ``strategy:
fanout_batch`` sources a task list (EXACTLY like ``task_loop`` — a declared
``task_source`` → producer step → typed content → registry-resolved parser), turns
each task into a worker request, and funnels them ALL through the SINGLE kernel
``run_fanout`` spawn path via ``ctx.runner.run_fanout(...)``. The strategy holds NO
spawn / worker-selection / concurrency logic of its own — that lives in the kernel
``run_fanout`` (INV-12 single home); the strategy is the thin declarative seam.

The runtime entry point (the ``spawn_subagents`` tool) reaches the SAME ``run_fanout``
through the engine's tool-result derivation (Task 3) — so BOTH entry points funnel
through one spawn path (FANOUT-02).

Import purity (import-linter / INV-13): NOTHING from ``agents.execution_engine`` or
``app.*`` is imported — every kernel primitive (``run_fanout``, the typed-content read)
is reached ONLY through the object-typed ``ctx.runner`` handle (Pitfall 2). The task
parser is resolved by NAME through the capability registry (the ``task_loop`` D-02
precedent).
"""

from __future__ import annotations

import logging
from typing import Any, AsyncIterator

from agents.capabilities.registry import CapabilityRegistry, register

logger = logging.getLogger(__name__)

# Default task parser when the step declares none (the task_loop precedent).
_DEFAULT_PARSER = "heading_tasks"


@register(
    "strategy",
    "fanout_batch",
    user_allowed=True,
    description="Fan a task list out to parallel worker sub-agents in one batch, then merge their results.",
    config_schema={
        "type": "object",
        "properties": {
            "merge": {
                "type": "string",
                "description": "Capability name of the merge strategy that combines the worker outputs.",
                "enum": ["copy_disjoint", "git_3way", "json", "html_fragment"],
            },
            "max_parallel": {
                "type": "integer",
                "description": "Optional cap on concurrent workers (defaults to the kernel concurrency limit).",
                "minimum": 1,
            },
        },
    },
)
class FanoutBatchStrategy:
    """Declarative fan-out: parse a task list → worker requests → run_fanout.

    Satisfies the ``ExecutionStrategy`` port structurally (``name`` + ``run``). All
    kernel/app primitives are reached only via ``ctx.runner`` (the D-03 handle).
    """

    name = "fanout_batch"

    # ISS-131: spawn-only — ``run`` NEVER calls ``ctx.runner.run_agent`` for the
    # step's own agent; every invocation it produces is a ``run_fanout`` child,
    # and those opt out of the inline review gate (ISS-097). The step-boundary
    # dedupe reads this so a declared ``gates:[human]`` on a fan-out step is not
    # skipped in favour of an inline gate that never opens.
    runs_agent_inline = False

    def __init__(self) -> None:
        # Module-singleton registry (capabilities are stateless) — resolves the task
        # parser by NAME (D-02), exactly like task_loop.
        self._registry = CapabilityRegistry()

    async def run(self, step: Any, ctx: Any) -> AsyncIterator[dict]:
        """Source the task list, build worker requests, funnel through run_fanout."""
        runner = ctx.runner

        # ── Source the task list EXACTLY like task_loop (declared task_source) ────
        task_source = getattr(step, "task_source", None)
        source_step = getattr(task_source, "source_step", None) if task_source else None
        plan_output = ""
        if source_step:
            plan_output = runner.latest_typed_content(source_step) or ""

        parser_name = _DEFAULT_PARSER
        if task_source is not None and getattr(task_source, "parser", None):
            parser_name = task_source.parser
        parser = self._registry.resolve("task_parser", parser_name)
        tasks = parser.parse(plan_output)

        # ── Build worker requests (self×N over the parsed tasks) ─────────────────
        # Each task becomes one worker request. The worker agent defaults to "self"
        # (the step's own agent); a heterogeneous fan-out can name workers via the
        # declared FanoutSpec.workers (resolved + validated inside run_fanout). The
        # kernel owns the selection control flow (INV-5) — the strategy only shapes
        # the requests.
        requests = [{"agent": "self", "input": t.body} for t in tasks]

        if not requests:
            # WR-06: a declared self×N width (fanout.count) with NO parsed tasks
            # synthesizes count identical worker requests — the declared field is
            # honored, not decorative. The kernel still owns selection/clamping.
            fanout_spec = getattr(step, "fanout", None)
            count = getattr(fanout_spec, "count", None) if fanout_spec is not None else None
            if count and int(count) > 0:
                requests = [{"agent": "self", "input": ""} for _ in range(int(count))]

        if not requests:
            logger.warning(
                "fanout_batch: no tasks parsed from source_step=%s — no workers spawned",
                source_step,
            )
            return

        # ── Funnel through the SINGLE kernel run_fanout spawn path (FANOUT-02) ────
        async for event in runner.run_fanout(requests, ctx, step=step):
            yield event
