"""agents/execution_engine/fanout.py — the SINGLE kernel fan-out spawn path (Phase 11).

``run_fanout`` is the ONE place fan-out children are spawned (FANOUT-02): BOTH entry
points funnel through it — the declarative ``fanout_batch`` strategy (which calls
``ctx.runner.run_fanout(...)``) and the runtime ``spawn_subagents`` tool (whose
structured request the engine derives + fulfils via the same ``run_fanout``). The
kernel — not the tool, not the manifest — owns what spawns.

Sequence (each numbered step maps to a FANOUT requirement):

  1. Worker selection (FANOUT-03) — for each request, ``agent="self"`` (or ``None``)
     resolves to the step's own ``agent_id``; a NAMED worker MUST appear in the run's
     compiled ``allowed_workers`` AND resolve in the agent registry (both reached via
     the ``ctx.runner`` handle, never a direct registry import — layering). A
     disallowed / unknown worker raises ``FanoutError`` BEFORE any spawn, leaving zero
     ``subagent_runs`` rows and no workspace allocation.
  2. Budget reserve (FANOUT-09) — ``ctx.budget.reserve(...)`` is called FIRST, before
     any spawn (the call site exists now; the raising enforcement is the 11-04 stub —
     Pitfall 4 enforcement-point discipline).
  3. Isolation — this plan uses the existing per-run / ``shared_read`` allocation
     (``sub_sandbox`` / ``worktree`` land in 11-02).
  4. Spawn (FANOUT-04) — parallel mode runs under
     ``asyncio.Semaphore(min(declared, DEFAULT_MAX_CONCURRENCY))`` so the engine caps
     concurrency REGARDLESS of the manifest; sequential mode runs ordered awaits. Each
     child writes ONE ``subagent_runs`` row (status ``running``) + emits a
     ``subagent_spawned`` event; on completion the row is flipped terminal + a
     ``subagent_result`` event is emitted. Child agent chunk events are NOT forwarded
     (D-03 — lifecycle-only).
  5. Merge — the trivial single-fragment / collect pass-through this plan (the real
     ``MergeStrategy`` registry is 11-03). The structured summary carries per-worker
     STATUS only — NOT typed artifact refs (those are the 11-03 FANOUT-06 deliverable).

INV-1: zero workflow-name dispatch branches (no ``pipeline_type``/``spec.id`` equality
checks) — the kernel knows no workflow by name. Import-direction: kernel-side; imports ONLY stdlib + the kernel-local
``budget`` module — never ``app.*``, never the agent registry directly (worker existence
is checked through the runner handle).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, AsyncIterator

from agents.execution_engine.budget import DEFAULT_MAX_CONCURRENCY

logger = logging.getLogger(__name__)

# This plan's isolation scope — the existing per-run/shared_read allocation. The
# sub_sandbox/worktree scopes land in 11-02 (selected off the step there).
_ISOLATION_SHARED_READ = "shared_read"


class FanoutError(Exception):
    """Raised when worker selection rejects a request BEFORE any spawn (FANOUT-03).

    Names the offending worker so the failure is diagnosable. Raised pre-spawn so a
    disallowed/unknown worker leaves zero ``subagent_runs`` rows + no allocation.
    """


def _select_workers(requests: list[dict], ctx: Any, step: Any) -> list[dict]:
    """Resolve each request to a concrete worker agent id (FANOUT-03).

    ``agent`` ``"self"``/``None`` → the step's own ``agent_id`` (self×N). A NAMED
    worker MUST be in the run's ``allowed_workers`` AND resolve in the agent registry
    — both checked through the ``ctx.runner`` handle (no direct registry import). A
    disallowed/unknown worker raises ``FanoutError`` BEFORE any spawn returns, so the
    caller never spawns / allocates / writes a row for a rejected fan-out.
    """
    runner = ctx.runner
    step_agent = getattr(step, "agent_id", None)
    allowed = set(getattr(runner, "allowed_workers", None) or [])
    agent_exists = getattr(runner, "agent_exists", None)

    selected: list[dict] = []
    for i, req in enumerate(requests):
        agent = req.get("agent")
        if agent in (None, "self"):
            resolved = step_agent
        else:
            # A named worker must be BOTH allow-listed AND registry-resolvable.
            if agent not in allowed:
                raise FanoutError(
                    f"fan-out worker {agent!r} is not in the workflow's "
                    f"allowed_workers {sorted(allowed)} — rejected before spawn (FANOUT-03)"
                )
            if agent_exists is not None and not agent_exists(agent):
                raise FanoutError(
                    f"fan-out worker {agent!r} is allow-listed but unknown to the "
                    f"agent registry — rejected before spawn (FANOUT-03)"
                )
            resolved = agent
        if not resolved:
            raise FanoutError(
                f"fan-out request {i} resolved to an empty worker agent id "
                f"(step agent_id={step_agent!r})"
            )
        selected.append({"index": i, "agent_id": resolved, "input": req.get("input", "")})
    return selected


def _resolve_concurrency(step: Any) -> int:
    """The effective parallel cap = ``min(declared_max_parallel, DEFAULT_MAX_CONCURRENCY)``.

    The engine ENFORCES the cap regardless of the manifest (T-11-01-02 DoS mitigation):
    a manifest asking for 100 parallel workers still runs at most ``DEFAULT_MAX_CONCURRENCY``.
    """
    fanout = getattr(step, "fanout", None)
    declared = getattr(fanout, "max_parallel", None) if fanout is not None else None
    if declared is None or declared <= 0:
        return DEFAULT_MAX_CONCURRENCY
    return min(declared, DEFAULT_MAX_CONCURRENCY)


def _is_sequential(step: Any) -> bool:
    fanout = getattr(step, "fanout", None)
    return bool(fanout is not None and getattr(fanout, "mode", None) == "sequential")


async def run_fanout(requests: list[dict], ctx: Any, *, step: Any) -> AsyncIterator[dict]:
    """Spawn the fan-out children — the ONLY spawn path (FANOUT-02).

    An async generator yielding lifecycle-only events (``subagent_spawned`` /
    ``subagent_result``) and finally returning. The per-worker status is collected into
    the ``subagent_result`` events (the status-only structured summary this plan
    produces — typed artifact refs are 11-03 / FANOUT-06).
    """
    runner = ctx.runner
    run_id = getattr(runner, "run_id", "")
    step_id = getattr(step, "agent_id", "fanout")
    depth = getattr(ctx, "depth", 0)

    # (1) Worker selection FIRST — a rejected worker raises before any spawn / row.
    selected = _select_workers(requests, ctx, step)

    # (2) Budget reserve BEFORE any spawn (the call site is the 11-04 enforcement seam).
    budget = getattr(ctx, "budget", None)
    if budget is not None:
        budget.reserve(
            subagents=len(selected),
            concurrency=_resolve_concurrency(step),
            depth=depth,
        )

    # (3) Isolation = the existing per-run / shared_read allocation this plan.
    isolation = _ISOLATION_SHARED_READ

    # Per-worker terminal-status collector (the status-only merge, step 5).
    results: list[dict] = []

    async def _run_one(worker: dict) -> dict:
        """Spawn ONE worker: write the row, run it, flip the row terminal."""
        idx = worker["index"]
        agent_id = worker["agent_id"]
        # A depth segment is added when nested (RESEARCH A4) so child thread ids never
        # collide across fan-out levels.
        if depth > 0:
            thread_id = f"{run_id}:{step_id}:d{depth}:{idx}"
        else:
            thread_id = f"{run_id}:{step_id}:{idx}"

        row_id = await runner.record_subagent_run(
            parent_step=step_id,
            worker_agent=agent_id,
            depth=depth,
            isolation=isolation,
            status="running",
        )
        status = "complete"
        try:
            async for _child_event in runner.run_worker(
                step, ctx,
                worker_index=idx,
                thread_id=thread_id,
                agent_id=agent_id,
                input=worker["input"],
            ):
                # Child agent chunk events are NOT forwarded (D-03 — lifecycle-only).
                pass
        except Exception as exc:  # noqa: BLE001 — a failed worker must not abort siblings
            logger.warning("fan-out worker %s (%s) failed: %s", idx, agent_id, exc)
            status = "failed"
        if row_id is not None:
            await runner.update_subagent_run(row_id, status=status)
        return {"worker": idx, "agent": agent_id, "row_id": row_id, "status": status}

    if _is_sequential(step):
        # Sequential mode — strict order, one worker at a time.
        for worker in selected:
            yield {
                "type": "subagent_spawned",
                "data": {"worker": worker["index"], "agent": worker["agent_id"],
                         "isolation": isolation, "depth": depth},
            }
            res = await _run_one(worker)
            results.append(res)
            yield {"type": "subagent_result", "data": res}
    else:
        # Parallel mode — bounded by the engine-enforced semaphore (T-11-01-02).
        cap = _resolve_concurrency(step)
        sem = asyncio.Semaphore(cap)

        # Emit the spawned events up-front (deterministic order) before gathering.
        for worker in selected:
            yield {
                "type": "subagent_spawned",
                "data": {"worker": worker["index"], "agent": worker["agent_id"],
                         "isolation": isolation, "depth": depth},
            }

        async def _bounded(worker: dict) -> dict:
            async with sem:
                return await _run_one(worker)

        gathered = await asyncio.gather(*(_bounded(w) for w in selected))
        # Preserve worker order in the result stream.
        for res in sorted(gathered, key=lambda r: r["worker"]):
            results.append(res)
            yield {"type": "subagent_result", "data": res}
