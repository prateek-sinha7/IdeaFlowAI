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
  3. Isolation (FANOUT-05) — the ENGINE (INV-7, NOT the manifest) selects the scope
     from the base workspace: ``worktree`` when ``has_git=True``, else ``sub_sandbox``.
     Each worker binds to its own engine-allocated isolated workspace (writes isolated,
     reads shared-read of parent refs); when no allocator handle is reachable the scope
     degrades to ``shared_read`` (the 11-01 per-run behavior). Happy-path workspaces are
     reclaimed after collect; the full cancel-path teardown is 11-05.
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

# The three isolation scopes. ``shared_read`` is the no-isolation per-run fallback
# (used when the engine cannot reach an allocator handle); ``sub_sandbox`` /
# ``worktree`` are the per-worker isolated scopes the engine selects (11-02).
_ISOLATION_SHARED_READ = "shared_read"
_ISOLATION_SUB_SANDBOX = "sub_sandbox"
_ISOLATION_WORKTREE = "worktree"


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


def _select_isolation_scope(base_workspace: Any) -> str:
    """The ENGINE decides the per-worker isolation scope (INV-7 — NOT the manifest).

    ``worktree`` when the base workspace is a git repo (``has_git=True``) — worker
    commits/edits are isolated on per-worker branches off the working branch; else
    ``sub_sandbox`` — worker writes are isolated in a child dir under the run root.

    The scope is derived SOLELY from the base workspace's ``has_git`` — it is NEVER
    read from ``step.fanout`` (the manifest declares no isolation field). This keeps
    isolation engine-controlled: a user-authored manifest cannot downgrade isolation
    (T-11-02-03 / INV-7).
    """
    return _ISOLATION_WORKTREE if getattr(base_workspace, "has_git", False) else _ISOLATION_SUB_SANDBOX


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

    # (3) Isolation — the ENGINE selects the scope from the base workspace (INV-7,
    # never the manifest): has_git -> worktree, else sub_sandbox. When no allocator
    # handle is reachable (offline harness / no workspace bound) the scope degrades to
    # shared_read (the 11-01 per-run behavior) so the fan-out still runs.
    base_workspace = getattr(runner, "workspace", None)
    allocate = getattr(runner, "allocate_isolated_workspace", None)
    if base_workspace is not None and allocate is not None:
        isolation = _select_isolation_scope(base_workspace)
    else:
        isolation = _ISOLATION_SHARED_READ

    # Per-worker terminal-status collector (the status-only merge, step 5).
    results: list[dict] = []
    # Every allocated isolated workspace is recorded so this plan can teardown the
    # happy-path workspaces after collect; 11-05 extends this list's teardown to the
    # cancel/finally path (ALL allocations, including a mid-flight cancel).
    allocated: list[Any] = []

    async def _run_one(worker: dict) -> dict:
        """Spawn ONE worker: allocate its isolated workspace, run it, flip the row."""
        idx = worker["index"]
        agent_id = worker["agent_id"]
        # A depth segment is added when nested (RESEARCH A4) so child thread ids never
        # collide across fan-out levels.
        if depth > 0:
            thread_id = f"{run_id}:{step_id}:d{depth}:{idx}"
        else:
            thread_id = f"{run_id}:{step_id}:{idx}"

        # Allocate the engine-selected isolated workspace for this worker (FANOUT-05).
        # The worker reads shared-read parent refs but WRITES isolated. When no
        # allocator is reachable (shared_read fallback) the worker runs against the
        # run's shared workspace exactly as 11-01 did.
        worker_ws = None
        if isolation in (_ISOLATION_SUB_SANDBOX, _ISOLATION_WORKTREE) and allocate is not None:
            worker_ws = await allocate(isolation, step_id, worker_index=idx)
            if worker_ws is not None:
                allocated.append(worker_ws)

        row_id = await runner.record_subagent_run(
            parent_step=step_id,
            worker_agent=agent_id,
            depth=depth,
            isolation=isolation,
            status="running",
        )
        status = "complete"
        # Pass the isolated workspace ONLY when one was allocated so the 11-01
        # shared-workspace ``run_worker`` call shape stays byte-identical (the kwarg
        # is additive; an offline/shared_read run never threads it).
        worker_kwargs = {"workspace": worker_ws} if worker_ws is not None else {}
        try:
            async for _child_event in runner.run_worker(
                step, ctx,
                worker_index=idx,
                thread_id=thread_id,
                agent_id=agent_id,
                input=worker["input"],
                **worker_kwargs,
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

    # Happy-path teardown — collect/merge is done, so reclaim every allocated
    # isolated workspace (worktree remove + branch delete, or child-dir rmtree). The
    # FULL cancel-path teardown (reclaim on a mid-flight cancel/exception too) lands
    # in 11-05; here we reclaim the post-collect happy-path workspaces. Best-effort
    # per workspace so a teardown failure never aborts the run.
    await _teardown_allocated(runner, base_workspace, allocated)


async def _teardown_allocated(runner: Any, base_workspace: Any, allocated: list) -> None:
    """Reclaim every allocated isolated workspace (happy path; 11-05 extends to cancel).

    A ``worktree`` workspace is removed via the base workspace's ``remove_worktree``
    (the single git owner — git worktree remove + branch delete); a ``sub_sandbox``
    child is removed via its own ``teardown`` (child-dir rmtree, which never touches
    the parent). Each teardown is best-effort so an orphaned worktree/dir is logged,
    not fatal (INV-3: cleanup must never break the run).
    """
    reclaim = getattr(runner, "reclaim_isolated_workspace", None)
    for ws in allocated:
        try:
            if reclaim is not None:
                await reclaim(base_workspace, ws)
        except Exception as exc:  # noqa: BLE001 — a teardown failure must not abort the run
            logger.warning("fan-out workspace teardown failed: %s", exc)
