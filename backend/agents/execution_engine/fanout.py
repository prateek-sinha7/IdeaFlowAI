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
  5. Fragment persistence + merge (FANOUT-06/07/08) — BEFORE merge, each worker's
     output persists as a typed lineage-tracked fragment ``ArtifactRef`` via
     ``ctx.runner.write_fragment_artifact`` (partial results survive abort/cancel —
     11-04/11-05 consume these refs). The per-worker structured summary now carries the
     fragment artifact ref (upgrading 11-01's status-only summary). Then the engine
     resolves a ``MergeStrategy`` by name (``git_3way`` for worktree fragments,
     ``copy_disjoint`` for sub_sandbox; engine-decided per INV-7) and runs the merge:
     ``merge_started`` → ``MergeStrategy.merge(base, fragments)`` → on a clean result
     ``merge_completed``; on a ``MergeResult`` with conflicts the engine writes an
     owner-scoped ``merge_conflict`` artifact + emits a ``merge_conflict`` event, then
     resolves per the step's ``on_conflict`` (``human_gate`` default via the ONE durable
     HITL / bounded ``merge_agent`` / ``partial`` / ``abort``).

INV-1: zero workflow-name dispatch branches (no ``pipeline_type``/``spec.id`` equality
checks) — the kernel knows no workflow by name. Import-direction: kernel-side; imports ONLY stdlib + the kernel-local
``budget`` module — never ``app.*``, never the agent registry directly (worker existence
is checked through the runner handle).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from agents.execution_engine.budget import (
    DEFAULT_MAX_CONCURRENCY,
    MERGE_AGENT_MAX_ATTEMPTS,
)

logger = logging.getLogger(__name__)

# The three isolation scopes. ``shared_read`` is the no-isolation per-run fallback
# (used when the engine cannot reach an allocator handle); ``sub_sandbox`` /
# ``worktree`` are the per-worker isolated scopes the engine selects (11-02).
_ISOLATION_SHARED_READ = "shared_read"
_ISOLATION_SUB_SANDBOX = "sub_sandbox"
_ISOLATION_WORKTREE = "worktree"


@dataclass
class FanoutMergeState:
    """Durable record of a fan-out merge outcome persisted to ``wave_runs``.

    Written by ``_merge_fragments`` after a merge attempt (clean or conflicted) via
    ``runner.update_wave_run_merge_state``. The ``wave_runs`` table has carried these
    columns since migration 0045 (sandbox-git-versioning-v2 task 5.1); this dataclass
    gives the caller a typed surface so the column assignment is never ad-hoc.

    ``merge_state`` values (mirrors the ``wave_runs.merge_state`` free-String column):
      ``"clean"``    — all fragments merged without conflict
      ``"conflict"`` — one or more merge conflicts were detected
      ``"partial"``  — some fragments applied, some did not (e.g. after a failed worker)
      ``"aborted"``  — the merge strategy raised an unhandled exception (WR-02)

    ``worker_index`` and ``step_id`` together key back to the ``wave_runs`` row so the
    caller can locate the right row without a secondary lookup.

    ``retained_state`` is populated by the ``partial`` policy (both refused-before-start
    and started-and-conflicted situations) so the kept fragment set is inspectable rather
    than implied.  It is a list of branch/worker descriptors for every fragment whose
    merge commit is still intact after the conflict was adjudicated.  Empty for every
    other policy.  (Requirement 12 AC 5 — Task 7.2.)
    """

    step_id: str
    worker_index: int
    merge_state: str  # "clean" | "conflict" | "partial" | "aborted"
    merge_applied: list[str] = field(
        default_factory=list
    )  # branch names merged cleanly
    merge_conflicts: list[dict] = field(default_factory=list)  # conflict details
    merge_strategy: str = ""  # e.g. "git_3way", "copy_disjoint"
    retained_state: list[str] = field(
        default_factory=list
    )  # fragment ids retained after partial


class FanoutError(Exception):
    """Raised when worker selection rejects a request BEFORE any spawn (FANOUT-03).

    Names the offending worker so the failure is diagnosable. Raised pre-spawn so a
    disallowed/unknown worker leaves zero ``subagent_runs`` rows + no allocation.
    """


class FanoutWorkerFailed(Exception):
    """Raised AFTER collect when one or more spawned workers ended ``status="failed"``
    (task.md R-03 / KRN-004).

    Before this, ``_run_one``'s ``except Exception`` swallowed a worker's exception,
    logged it, flipped its own ``subagent_runs`` row ``failed``, and returned a plain
    dict — nothing downstream of ``run_fanout`` ever inspected the collected results
    for a failed status, so a fan-out step with a failed child proceeded exactly like
    a fully-successful one (through merge, to ``pipeline_complete``) unless a
    *different*, non-worker exception happened to propagate instead. Each failed
    child's own ``subagent_result`` event is still yielded first (unchanged,
    diagnosable per-child signal) — this exception is raised only once, AFTER every
    worker has been collected, so the caller sees exactly one parent-level terminal
    failure that names every failed worker, never a false "succeeded" fan-out.
    """

    def __init__(self, failed: list[dict]):
        self.failed = failed
        names = ", ".join(f"{w.get('agent')}#{w.get('worker')}" for w in failed)
        super().__init__(f"{len(failed)} fan-out worker(s) failed: {names}")


# How many times a fan-out worker is re-run after a transient model failure (a
# timeout, throttling, a provider 5xx) before it counts as failed.
_TRANSIENT_WORKER_RETRIES = 2


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
        selected.append(
            {
                "index": i,
                "agent_id": resolved,
                "input": req.get("input", ""),
                # RESUME-06: carry the plan-global task id from the wave request to the
                # record site so each spawned subagent_runs row is stamped at SPAWN
                # (before the crash window). None on legacy/non-wave fan-out (dormant).
                "task_id": req.get("task_id"),
                # The author's own id (s01) alongside the hashed task_id — display
                # only, and dropped here would mean the UI never sees it.
                "task_author_id": req.get("task_author_id"),
            }
        )
    return selected


def _apply_declared_fanout(requests: list[dict], step: Any) -> list[dict]:
    """Honor the DECLARED ``FanoutSpec`` worker-selection fields (WR-06 / FANOUT-03).

    The manifest declares pure data; the KERNEL honors it here (INV-5 — the
    strategy only shapes requests):

      * ``workers`` — heterogeneous fan-out: request ``i`` carrying the default
        agent (``self``/``None``) maps to ``workers[i]``; each mapped name is then
        validated against ``allowed_workers`` + the registry by ``_select_workers``
        exactly like an explicitly-named request (rejected pre-spawn if disallowed);
      * ``agent`` — the default worker for an agent-less request beyond the
        ``workers`` list (``self`` keeps the step's own agent);
      * ``count`` — the declared fan-out WIDTH: a longer request list is clamped
        to it (the engine honors the declared width; it is not decorative).

    A step with no ``FanoutSpec`` (or none of the fields populated) returns the
    requests unchanged — every existing caller is untouched (parity).
    """
    fanout = getattr(step, "fanout", None)
    if fanout is None:
        return list(requests)
    declared_workers = list(getattr(fanout, "workers", None) or [])
    declared_agent = getattr(fanout, "agent", None)
    count = getattr(fanout, "count", None)
    out: list[dict] = []
    for i, req in enumerate(requests):
        agent = req.get("agent")
        if agent in (None, "self"):
            if i < len(declared_workers):
                req = dict(req)
                req["agent"] = declared_workers[i]
            elif agent is None and declared_agent:
                req = dict(req)
                req["agent"] = declared_agent
        out.append(req)
    if count and int(count) > 0:
        out = out[: int(count)]
    return out


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


def _note_wall_clock(budget: Any) -> None:
    """Check the armed wall-clock deadline at a fan-out boundary (FANOUT-09 / CR-04).

    Called BEFORE each sequential spawn, BEFORE each parallel worker enters
    ``_run_one``, and BEFORE the merge — so a mid-flight breach aborts gracefully
    (``BudgetExceeded`` propagates; pending workers never spawn; the ``finally``
    teardown reclaims allocations; completed fragments are already persisted).
    A budget without the handle (a bare stub / no budget bound) is a no-op.
    """
    if budget is None:
        return
    fn = getattr(budget, "note_wall_clock", None)
    if callable(fn):
        fn()  # raises BudgetExceeded past the armed deadline


def _note_tokens(budget: Any, tokens: int) -> None:
    """Accumulate a worker's reported token usage at the collect boundary (CR-04).

    Raises ``BudgetExceeded`` once a declared ``max_tokens`` cap is breached
    (check-at-boundary, D-05 — you cannot pre-reserve unknown token spend). A
    budget without the handle / zero usage is a no-op.
    """
    if budget is None or not tokens:
        return
    fn = getattr(budget, "note_tokens", None)
    if callable(fn):
        fn(tokens)  # raises BudgetExceeded over a declared max_tokens


def _check_cancel(ctx: Any) -> None:
    """Cooperative cancel check at a fan-out boundary (RESUME-01 / FANOUT-11).

    Reads ``ctx.cancel_event`` (the Stop button — the same cooperative signal the
    engine checks per-agent-step + per-chunk) and raises ``asyncio.CancelledError``
    when it is set. Called BEFORE a fan-out wave (before any allocate/spawn), BETWEEN
    sequential workers, and BEFORE the merge — so a cancelled run stops cooperatively
    at the next boundary, pending workers never spawn, and the kernel's outer
    ``CancelledError`` handler (which emits ``pipeline_cancelled``) drives termination.

    The ``finally``-teardown in ``run_fanout`` reclaims EVERY allocated isolated
    workspace whether this raises or the body completes normally (Pitfall 5 — no leaks
    on the cancel path).
    """
    cancel_event = getattr(ctx, "cancel_event", None)
    if cancel_event is not None and cancel_event.is_set():
        raise asyncio.CancelledError()
    # ── ISS-091 defence-in-depth ──────────────────────────────────────────────
    # A run driven terminal by something OTHER than the Stop button — a review-gate
    # rejection — sets no ``cancel_event``, so the check above cannot see it. Without
    # this, every worker no-ops on _run_agent's terminal guard yet its subagent_runs
    # row is still flipped "complete" and its wave "completed": a durable record of
    # work that never happened, which wave_scheduler's resume skip then trusts,
    # permanently losing the run's output. The dispatch-loop fix means no reported
    # path reaches here; this keeps the SINGLE fan-out cancel boundary (rather than a
    # second one in a strategy — INV-12) correct for any future path that does.
    # None-degrading: a ctx whose runner predates this exposes no such attribute.
    _is_terminal = getattr(getattr(ctx, "runner", None), "is_run_terminal", None)
    if callable(_is_terminal) and _is_terminal():
        raise asyncio.CancelledError()


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
    return (
        _ISOLATION_WORKTREE
        if getattr(base_workspace, "has_git", False)
        else _ISOLATION_SUB_SANDBOX
    )


async def run_fanout(
    requests: list[dict],
    ctx: Any,
    *,
    step: Any,
    event_queue: asyncio.Queue | None = None,
) -> AsyncIterator[dict]:
    """Spawn the fan-out children — the ONLY spawn path (FANOUT-02).

    An async generator yielding lifecycle-only events (``subagent_spawned`` /
    ``subagent_result``) and finally returning. The per-worker status is collected into
    the ``subagent_result`` events (the status-only structured summary this plan
    produces — typed artifact refs are 11-03 / FANOUT-06).

    ``event_queue`` (optional, default None): when a caller supplies a queue, each
    worker's own per-agent events (agent_start/agent_chunk/tool_call/tool_result/
    agent_complete — normally discarded here) are ALSO pushed onto it as a side
    channel, for a caller that wants to forward live per-worker streaming
    (``parallel_group`` and ``wave_scheduler`` both pass one). None (``fanout_batch``,
    the engine tool-result path) is a no-op — byte-identical.
    """

    runner = ctx.runner
    run_id = getattr(runner, "run_id", "")
    step_id = getattr(step, "agent_id", "fanout")
    depth = getattr(ctx, "depth", 0)

    # (0) Cooperative cancel BEFORE the fan-out wave (RESUME-01) — if the run was
    # cancelled before this fan-out starts, raise CancelledError now so NOTHING is
    # selected/reserved/allocated/spawned (the kernel's outer handler emits
    # pipeline_cancelled). A pre-wave cancel leaves zero subagent_runs rows.
    _check_cancel(ctx)

    # (0b) Honor the DECLARED FanoutSpec worker-selection fields (WR-06): the
    # declared ``workers`` map onto default-agent requests (heterogeneous fan-out),
    # ``agent`` defaults an agent-less request, and ``count`` clamps the width —
    # BEFORE selection so a declared named worker passes the same allow-list +
    # registry validation as an explicitly-named one.
    requests = _apply_declared_fanout(requests, step)

    # (1) Worker selection FIRST — a rejected worker raises before any spawn / row.
    selected = _select_workers(requests, ctx, step)

    # (2) Budget reserve BEFORE any spawn — the ENFORCEMENT point (FANOUT-09 / 11-04).
    # ``reserve`` raises BudgetExceeded (naming the breached dimension) when this spawn
    # would exceed total subagents / concurrency / depth / the per-workspace aggregate.
    # Reserve-before-spawn (Pitfall 4): a refused reservation propagates BEFORE any
    # allocate / run_worker / subagent_runs row, so the rejection has zero side effects.
    # The wall-clock deadline is armed here (the first arm wins so a nested fan-out
    # cannot extend the run's wall-clock budget). On BudgetExceeded the abort surfaces a
    # budget_warning + the (zero, here — nothing spawned yet) completed fragments.
    budget = getattr(ctx, "budget", None)
    if budget is not None:
        arm = getattr(budget, "arm", None)
        if callable(arm):
            arm()
        # The per-workspace already-spent aggregate (OBS-01) — read through the runner
        # handle (default 0 when no handle/ceiling reachable, so the offline path is
        # untouched). The aggregate is checked against the configured workspace ceiling.
        workspace_spent = 0
        ws_spent_fn = getattr(runner, "workspace_budget_spent", None)
        if (
            ws_spent_fn is not None
            and getattr(budget, "workspace_ceiling", None) is not None
        ):
            try:
                workspace_spent = int((await ws_spent_fn()).get("subagents", 0))
            except Exception as exc:  # noqa: BLE001 — a ceiling read failure degrades to 0
                logger.debug("workspace_budget_spent read failed: %s", exc)
                workspace_spent = 0
        try:
            budget.reserve(
                subagents=len(selected),
                concurrency=_resolve_concurrency(step),
                depth=depth,
                workspace_spent=workspace_spent,
            )
        except (
            Exception
        ) as exc:  # the budget module's BudgetExceeded — surface + re-raise
            # A failed reserve emits a visible budget_warning BEFORE the abort propagates
            # (OBS-01) so the stream reports the breached ceiling; pending workers never
            # spawn (we are still pre-spawn). No completed fragments exist yet at this
            # single fan-out level, so the partial summary is empty — the engine surfaces
            # any EARLIER level's persisted fragments on the abort path.
            yield {
                "type": "budget_warning",
                "data": {
                    "step": step_id,
                    "dimension": getattr(exc, "dimension", "unknown"),
                    "reason": "reserve_failed",
                    "message": str(exc),
                },
            }
            raise

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
    # Every allocated isolated workspace is recorded so the ``finally`` block can
    # teardown EVERY allocation — on the happy path AND the cancel path AND the
    # BudgetExceeded path (Pitfall 5 / RESUME-01): no leaked workspace dirs / orphan
    # worktrees remain after a mid-flight cancel.
    allocated: list[Any] = []

    # index -> subagent_runs row_id for every worker that recorded a row but has NOT
    # yet flipped terminal. On a mid-flight cancel these rows are marked ``cancelled``
    # (FANOUT-11); ``_run_one`` pops an entry once it flips the row itself.
    open_rows: dict[int, str] = {}

    # Each entry: {"index", "agent_id", "workspace", "branch", "base_commit"} — the
    # merge inputs collected per worker (the isolated workspace handle for sub_sandbox,
    # the worktree branch + spawn-point commit for worktree). Populated in _run_one.
    fragments_meta: list[dict] = []

    async def _run_one(worker: dict) -> dict:
        """Spawn ONE worker: allocate its isolated workspace, run it, flip the row."""
        idx = worker["index"]
        agent_id = worker["agent_id"]
        # A depth segment is added when nested (RESEARCH A4) so child thread ids never
        # collide across fan-out levels. A wave worker's thread is keyed by its task,
        # not its slot: the slot index restarts every wave, and a reused slot thread
        # replayed the previous task's history — one cut reply (run 3976f8ce) failed
        # every later task on that slot. A resume of the same task keeps its thread.
        slot = worker.get("task_id") or idx
        if depth > 0:
            thread_id = f"{run_id}:{step_id}:d{depth}:{slot}"
        else:
            thread_id = f"{run_id}:{step_id}:{slot}"

        # Allocate the engine-selected isolated workspace for this worker (FANOUT-05).
        # The worker reads shared-read parent refs but WRITES isolated. When no
        # allocator is reachable (shared_read fallback) the worker runs against the
        # run's shared workspace exactly as 11-01 did.
        worker_ws = None
        if (
            isolation in (_ISOLATION_SUB_SANDBOX, _ISOLATION_WORKTREE)
            and allocate is not None
        ):
            worker_ws = await allocate(isolation, step_id, worker_index=idx)
            if worker_ws is not None:
                allocated.append(worker_ws)

        row_id = await runner.record_subagent_run(
            parent_step=step_id,
            worker_agent=agent_id,
            depth=depth,
            isolation=isolation,
            status="running",
            # RESUME-06: stamp identity at SPAWN. worker_index=idx restarts at 0 per
            # run_fanout call (wave-local, audit only); task_id is the plan-global id
            # the resume skip cursor keys on (None on non-wave fan-out → dormant).
            worker_index=idx,
            task_id=worker.get("task_id"),
        )
        if row_id is not None:
            open_rows[idx] = row_id
        status = "complete"
        # Pass the isolated workspace ONLY when one was allocated so the 11-01
        # shared-workspace ``run_worker`` call shape stays byte-identical (the kwarg
        # is additive; an offline/shared_read run never threads it).
        worker_kwargs = {"workspace": worker_ws} if worker_ws is not None else {}
        # The worker's reported token usage (read off its agent_complete event) —
        # accumulated into the budget at the collect boundary (FANOUT-09 / CR-04).
        worker_tokens = 0
        worker_error: str | None = None
        # Provider failures (expired credentials, rate limits, etc.) are YIELDED as
        # agent_error events, not raised. Track if we saw an error WITH NO agent_complete:
        # that worker is failed. Timeouts yield BOTH agent_error + agent_complete — those
        # stay complete (the best-available output was delivered).
        saw_complete = False
        agent_error_msg: str | None = None
        # The model the worker actually ran on, read off its own agent_start /
        # agent_complete — the engine resolves it (user override, step, default), so
        # the result event reports what ran rather than a guess made before spawn.
        worker_model: str | None = None
        # One stuck or throttled model call used to fail the whole run with every
        # other worker done (run 2867387c: 67/68 workers). A transient failure gets a
        # fresh call on a new checkpoint thread, so the retry does not resume the
        # stalled one; a deterministic error still fails at once.
        from agents.execution_engine.engine import TRANSIENT_AGENT_ERRORS  # noqa: PLC0415

        attempt = 0
        attempt_thread = thread_id
        while True:
            saw_complete = False
            agent_error_msg = None
            try:
                async for _child_event in runner.run_worker(
                    step,
                    ctx,
                    worker_index=idx,
                    # The worker's plan-global task id (s01…), so a NESTED fan-out this
                    # worker performs can name the parent it came from. None on
                    # non-wave fan-out → the whole chain stays dormant.
                    task_id=worker.get("task_id"),
                    task_author_id=worker.get("task_author_id"),
                    thread_id=attempt_thread,
                    agent_id=agent_id,
                    input=worker["input"],
                    # WR-05: the wave width — the worker's "task i of N" header.
                    total_workers=len(selected),
                    **worker_kwargs,
                ):
                    # Child agent chunk events are NOT forwarded (D-03 — lifecycle-only);
                    # the terminal agent_complete carries the worker's token usage.
                    if _child_event.get("type") in ("agent_start", "agent_complete"):
                        worker_model = (_child_event.get("data") or {}).get(
                            "model_id"
                        ) or worker_model
                    if _child_event.get("type") == "agent_complete":
                        saw_complete = True
                        worker_tokens += int(
                            (_child_event.get("data") or {}).get("total_tokens") or 0
                        )
                    elif _child_event.get("type") == "agent_error":
                        # Capture provider failures (credentials, rate limits, etc.).
                        agent_error_msg = (_child_event.get("data") or {}).get(
                            "error"
                        ) or "agent_error"

                    # Optional side channel (additive, default-off): a caller that
                    # supplied event_queue gets this worker's raw per-agent event too.
                    # parallel_group and wave_scheduler supply one on every fan-out;
                    # fanout_batch and the engine tool-result path pass None.
                    # RESUME-06 companion: stamp worker identity at PUSH time (this loop is
                    # the only place that knows it) on a COPY — never mutate the dict
                    # ``run_worker`` yields, it may be re-read/re-yielded elsewhere.
                    if event_queue is not None:
                        _data = dict(_child_event.get("data") or {})
                        _data["worker_index"] = idx
                        _data["task_id"] = worker.get("task_id")
                        _data["task_author_id"] = worker.get("task_author_id")
                        event_queue.put_nowait({**_child_event, "data": _data})

            except asyncio.CancelledError:
                # This worker's task was cancelled (the run was stopped mid-flight). Flip
                # the row terminal ``cancelled`` (FANOUT-11) and re-raise so asyncio.gather
                # propagates the cancellation; the ``finally`` teardown reclaims this
                # worker's allocated workspace (no leak).
                if row_id is not None:
                    open_rows.pop(idx, None)
                    await runner.update_subagent_run(row_id, status="cancelled")
                raise
            except Exception as exc:  # noqa: BLE001 — a failed worker must not abort siblings
                logger.warning("fan-out worker %s (%s) failed: %s", idx, agent_id, exc)
                status = "failed"
                # Carry WHY on the result event. Without it a failed row can only say
                # "Failed", and the reader is left guessing between a budget refusal,
                # a tool error and a model error — three very different problems.
                worker_error = f"{type(exc).__name__}: {exc}"[:400]

            # Provider failures are YIELDED as agent_error events, not raised. If we saw an
            # error but NO agent_complete, the worker must be recorded failed (not complete).
            # Timeouts yield both agent_error + agent_complete — those correctly stay complete
            # (best-available output was delivered).
            if agent_error_msg is not None and not saw_complete:
                status = "failed"
                worker_error = agent_error_msg[:400]
            if (
                status == "failed"
                and not saw_complete
                and agent_error_msg in TRANSIENT_AGENT_ERRORS
                and attempt < _TRANSIENT_WORKER_RETRIES
            ):
                attempt += 1
                attempt_thread = f"{thread_id}:retry{attempt}"
                logger.warning(
                    "fan-out worker %s (%s): %s — retrying on a fresh call (%d/%d)",
                    idx,
                    agent_id,
                    agent_error_msg,
                    attempt,
                    _TRANSIENT_WORKER_RETRIES,
                )
                status = "complete"
                worker_error = None
                continue
            break

        if row_id is not None:
            open_rows.pop(idx, None)
            await runner.update_subagent_run(
                row_id, status=status, tokens=(worker_tokens or None)
            )

        # Check-at-boundary token accounting (FANOUT-09 / CR-04): accumulate this
        # worker's usage; a declared max_tokens breach raises BudgetExceeded here —
        # AFTER the row flipped terminal (no row left running) and BEFORE further
        # spawns (the abort propagates through the spawn loop / gather).
        _note_tokens(budget, worker_tokens)

        # Commit a completed WORKTREE worker's edits on its per-worker branch
        # (CR-06): without this, merge_worktree's ``git merge`` sees nothing to
        # integrate and the uncommitted edits are destroyed by the worktree
        # teardown — worker output silently lost.
        # Task 4.3 (sandbox-git-versioning-v2, Req 11 AC 9): routed through the
        # ONE security-gated commit primitive so the worker commit is subject to
        # pre_commit hooks and the mandatory secret scan, exactly like every
        # step-boundary commit.  ``audit_operation=None`` because a fan-out
        # worker commit is not an audited operation class (the observer no-ops
        # cleanly on None per the commit_in_sandbox contract, Req 19).
        # A minimal SimpleNamespace step carries the agent_id so _fire_hooks and
        # the audit trail can identify the worker; hooks and tools are None (no
        # per-worker declared hooks to fire, no force-add allowlist needed).
        if status == "complete" and getattr(worker_ws, "_worktree_branch", None):
            try:
                from agents.execution_engine.engine import commit_in_sandbox  # noqa: PLC0415
                import types as _types  # noqa: PLC0415

                _worker_step = _types.SimpleNamespace(
                    agent_id=agent_id,
                    hooks=[],
                    tools=None,
                )
                _result = await commit_in_sandbox(
                    worker_ws,
                    f"fanout: worker {idx} ({agent_id})",
                    ctx,
                    _worker_step,
                    audit_operation=None,
                    registry=None,  # no per-worker declared hooks
                )
                if _result.blocked:
                    logger.warning(
                        "fan-out worker %s worktree commit BLOCKED (reason=%s) — "
                        "worker output will not be merged",
                        idx,
                        _result.block_reason,
                    )
                    # A blocked worker commit means the fragment is incomplete — flip
                    # the status so it is not presented as a mergeable fragment.
                    status = "failed"
            except Exception as exc:  # noqa: BLE001 — commit failure degrades to no fragment
                logger.warning("fan-out worker %s worktree commit failed: %s", idx, exc)

        # (5a) Fragment persistence BEFORE merge (FANOUT-06 / WR-03) — EVERY file the
        # worker wrote persists as a typed lineage-tracked fragment artifact (one ref
        # per file), so a multi-file worker's FULL output survives an abort/cancel
        # (11-04/11-05 consume the refs). Best-effort: a worker that wrote nothing
        # (or no persist handle reachable) leaves artifact_refs empty.
        artifact_refs: list = []
        write_fragment = getattr(runner, "write_fragment_artifact", None)
        frag_files = _fragment_files(
            worker_ws, base_commit=_spawn_point(base_workspace)
        )
        if status == "complete" and write_fragment is not None and frag_files:
            for relpath in sorted(frag_files.keys()):
                ref = await write_fragment(
                    producer_step=step_id,
                    worker_agent=agent_id,
                    worker_index=idx,
                    content=frag_files[relpath],
                    location=relpath,
                )
                if ref is not None:
                    artifact_refs.append(ref)

        # Record the merge inputs for this worker (the merge reads them after collect).
        fragments_meta.append(
            {
                "index": idx,
                "agent_id": agent_id,
                "workspace": worker_ws,
                "status": status,
                "branch": getattr(worker_ws, "_worktree_branch", None),
                "base_commit": _spawn_point(base_workspace),
            }
        )

        result = {
            "worker": idx,
            "agent": agent_id,
            "row_id": row_id,
            "status": status,
            "task_id": worker.get("task_id"),
            "task_author_id": worker.get("task_author_id"),
        }
        if worker_model:
            result["model_id"] = worker_model
        if worker_error:
            result["error"] = worker_error
        if artifact_refs:
            # Back-compat: artifact_ref carries the first (primary) ref; the full
            # multi-file set rides artifact_refs (WR-03 — nothing is dropped).
            result["artifact_ref"] = artifact_refs[0]
            result["artifact_refs"] = list(artifact_refs)
        return result

    # The spawn + merge body runs inside a try/finally so the ``finally`` tears down
    # EVERY allocated isolated workspace whether the body completes normally, is
    # cancelled mid-flight, or aborts on BudgetExceeded (Pitfall 5 / RESUME-01). A
    # CancelledError from a boundary check or an in-flight worker propagates OUT (the
    # kernel's outer handler emits pipeline_cancelled); the teardown still runs first.
    _depth_bumped = False
    _fan_cancelled = False  # tracks cancel/abort path so teardown can retain branches
    try:
        # ── Depth propagation for the workers' execution scope (CR-05) ───────
        # A worker that itself triggers a fan-out (spawn_subagents → _derive_fanout,
        # which reuses THIS shared ctx) must see depth+1 so the nested level
        # reserves at the correct depth (max_depth enforceable), namespaces its
        # child thread ids with the d{depth} segment, and records depth+1 on its
        # subagent_runs rows. The bump scopes the whole wave (every worker at this
        # level runs one level deeper than the spawner) and is restored in the
        # ``finally`` so the parent run continues at its own depth.
        try:
            ctx.depth = depth + 1
            _depth_bumped = True
        except Exception:  # noqa: BLE001 — a read-only ctx degrades to unpropagated depth
            pass
        if _is_sequential(step):
            # Sequential mode — strict order, one worker at a time. Cancel is checked
            # BETWEEN workers (RESUME-01): a cancelled run stops before the NEXT spawn,
            # so pending workers never start (FANOUT-11).
            for worker in selected:
                _check_cancel(ctx)
                # Wall-clock boundary BEFORE each sequential spawn (FANOUT-09 /
                # CR-04): a mid-flight deadline breach aborts before the NEXT
                # worker spawns — pending workers never start.
                _note_wall_clock(budget)
                yield {
                    "type": "subagent_spawned",
                    "data": {
                        "worker": worker["index"],
                        "agent": worker["agent_id"],
                        "isolation": isolation,
                        "depth": depth,
                        "task_id": worker.get("task_id"),
                        "task_author_id": worker.get("task_author_id"),
                    },
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
                    "data": {
                        "worker": worker["index"],
                        "agent": worker["agent_id"],
                        "isolation": isolation,
                        "depth": depth,
                        "task_id": worker.get("task_id"),
                        "task_author_id": worker.get("task_author_id"),
                    },
                }

            async def _bounded(worker: dict) -> dict:
                async with sem:
                    # Wall-clock boundary BEFORE each parallel worker (FANOUT-09 /
                    # CR-04): a queued worker whose turn arrives past the deadline
                    # never runs — BudgetExceeded propagates through the gather.
                    _note_wall_clock(budget)
                    return await _run_one(worker)

            # Cancellation propagation (FANOUT-11): gather the worker tasks so a
            # cancel can reach the in-flight ones. A cancel_event firing mid-flight (or
            # a CancelledError from a worker) cancels EVERY task — the in-flight tasks
            # raise CancelledError (flipping their own row ``cancelled`` in _run_one's
            # handler) and the pending ones never start. The CancelledError then
            # propagates so the run terminates; the ``finally`` reclaims allocations.
            tasks = [asyncio.ensure_future(_bounded(w)) for w in selected]
            try:
                gathered = await _gather_or_cancel(tasks, ctx)
            except asyncio.CancelledError:
                # Mark any still-open rows cancelled (workers cancelled before their
                # own handler ran — e.g. pending tasks that never entered _run_one).
                await _mark_open_cancelled(runner, open_rows)
                raise
            except Exception:
                # WR-04: a NON-worker exception (allocate / record_subagent_run /
                # a budget boundary raising out of one task) re-raises from the
                # gather while the SIBLING tasks keep running detached — the
                # ``finally`` teardown would then rmtree workspaces under
                # in-flight workers and their rows would stay ``running`` forever.
                # Mirror the cancel path: cancel + await every outstanding task
                # (each in-flight worker's own CancelledError handler flips its
                # row), mark the still-open rows cancelled, THEN propagate.
                for t in tasks:
                    t.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                await _mark_open_cancelled(runner, open_rows)
                raise
            # Preserve worker order in the result stream.
            for res in sorted(gathered, key=lambda r: r["worker"]):
                results.append(res)
                yield {"type": "subagent_result", "data": res}

        # ── Budget warning at ≥80% consumption (OBS-01) ───────────────────────
        # After the workers are collected, emit a visible budget_warning when any
        # ceiling is ≥ BUDGET_WARN_THRESHOLD (0.8) consumed — through the single emit
        # boundary + the generic forward (zero websocket.py edits). Best-effort: a
        # manager without the warn handle (a bare stub) is skipped (offline parity).
        if budget is not None:
            warn_fn = getattr(budget, "warn_threshold_reached", None)
            if callable(warn_fn):
                # Refresh the snapshot FIRST (CR-04): wall-clock spend only updates
                # via spent()/note_wall_clock, so without this the wall_clock warn
                # below reads a stale 0.0 and can never fire.
                spent_fn = getattr(budget, "spent", None)
                if callable(spent_fn):
                    try:
                        spent_fn()
                    except Exception:  # noqa: BLE001 — a snapshot refresh is best-effort
                        pass
                for dimension in ("subagents", "depth", "tokens", "wall_clock"):
                    try:
                        breached = warn_fn(dimension)
                    except Exception:  # noqa: BLE001 — a warn read failure is non-fatal
                        breached = False
                    if breached:
                        yield {
                            "type": "budget_warning",
                            "data": {
                                "step": step_id,
                                "dimension": dimension,
                                "reason": "threshold_reached",
                            },
                        }

        # ── KRN-004 (task.md R-03): one child failure → exactly one parent
        # terminal failure ─────────────────────────────────────────────────
        # Every worker's ``subagent_result`` (including a failed one's) has
        # ALREADY been yielded above — this raises only AFTER every child has been
        # collected and its own terminal event emitted, so nothing here suppresses
        # a per-child signal. Raised BEFORE merge: a failed worker's fragment was
        # never written (merge already only integrates ``status == "complete"``
        # fragments), so skipping merge on any failure is consistent with what
        # would have been merged anyway. Fan-out-cancel (FANOUT-11) already
        # propagates via its own asyncio.CancelledError path above and is
        # unaffected — this only fires when EVERY task finished (no cancel/
        # non-worker exception already propagated).
        failed_workers = [r for r in results if r.get("status") == "failed"]
        if failed_workers:
            raise FanoutWorkerFailed(failed_workers)

        # ── Cooperative cancel BEFORE merge (RESUME-01) ───────────────────────
        # Completed workers' fragment artifacts are ALREADY persisted (5a /
        # write_fragment_artifact) so they survive this cancel; the merge is simply
        # skipped and the run terminates (FANOUT-11 — cancel before merge).
        _check_cancel(ctx)
        # Wall-clock boundary BEFORE the merge (FANOUT-09 / CR-04): a run that
        # breached the deadline mid-collect aborts here with its persisted
        # fragments instead of starting the merge.
        _note_wall_clock(budget)

        # ── (5b) Merge dispatch (FANOUT-07/08) ────────────────────────────────
        # The fragments are integrated into the base workspace via the engine-selected
        # MergeStrategy. Replaces the 11-01 trivial pass-through. The merge runs only
        # over the COMPLETED workers' fragments (a failed worker contributes nothing).
        # When no base/merge is reachable (offline / shared_read) the merge is a clean
        # no-op so the fan-out still completes.
        async for ev in _merge_fragments(
            runner, base_workspace, step, isolation, fragments_meta, ctx
        ):
            yield ev
    finally:
        # Restore the spawner's depth (CR-05) — the bump scoped only this wave.
        if _depth_bumped:
            try:
                ctx.depth = depth
            except Exception:  # noqa: BLE001 — best-effort restore
                pass
        # Teardown EVERY allocated isolated workspace — the happy path AND the cancel
        # path AND the BudgetExceeded path all run this (Pitfall 5 / RESUME-01). Each
        # ``worktree`` is removed (git worktree remove + branch delete on the happy
        # path; branch RETAINED on cancel so completed worker work is never lost,
        # Requirement 28 AC2); each ``sub_sandbox`` child dir is rmtree'd. Best-effort
        # per workspace so a teardown failure never masks the original outcome.
        # Zero-residue acceptance: no isolated workspace dirs / orphan
        # ``git worktree list`` entries remain after cancel.
        _cancel_active = _fan_cancelled or (
            getattr(ctx, "cancel_event", None) is not None
            and getattr(ctx.cancel_event, "is_set", lambda: False)()
        )
        await _teardown_allocated(
            runner, base_workspace, allocated, delete_branch=not _cancel_active
        )


async def _gather_or_cancel(tasks: list, ctx: Any) -> list[dict]:
    """Await the worker tasks, but cancel ALL of them when cancel_event fires.

    Races the gathered worker tasks against the cooperative ``cancel_event`` (the Stop
    button): a poller checks the event and, when set, cancels every in-flight worker
    task (the pending ones never enter ``_run_one``). On cancel — or on a
    CancelledError bubbling out of a worker — every task is cancelled and a
    CancelledError is raised so the run terminates (FANOUT-11). On the happy path the
    gathered results are returned in submission order.
    """
    cancel_event = getattr(ctx, "cancel_event", None)
    gather_fut = asyncio.gather(*tasks)
    if cancel_event is None:
        return await gather_fut

    async def _poll_cancel() -> None:
        while not cancel_event.is_set():
            await asyncio.sleep(0.01)

    poller = asyncio.ensure_future(_poll_cancel())
    try:
        done, _pending = await asyncio.wait(
            {gather_fut, poller}, return_when=asyncio.FIRST_COMPLETED
        )
        if cancel_event.is_set() and not gather_fut.done():
            # Cancel every in-flight worker task; await them so each worker's own
            # CancelledError handler (marking its row cancelled) runs.
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            gather_fut.cancel()
            raise asyncio.CancelledError()
        # gather_fut completed (happy path or a worker raised) — return/propagate it.
        return await gather_fut
    finally:
        poller.cancel()
        with _suppress_cancel():
            await poller


class _suppress_cancel:
    """Context manager swallowing a CancelledError from awaiting the cancelled poller."""

    def __enter__(self) -> "_suppress_cancel":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return exc_type is not None and issubclass(exc_type, asyncio.CancelledError)


async def _mark_open_cancelled(runner: Any, open_rows: dict) -> None:
    """Flip every still-open ``subagent_runs`` row terminal ``cancelled`` (FANOUT-11).

    Called on the parallel-mode cancel path for rows a worker recorded but whose own
    handler did not run (e.g. a pending task cancelled before it entered ``_run_one``).
    Best-effort — an audit-write failure must never mask the cancellation.
    """
    update = getattr(runner, "update_subagent_run", None)
    if update is None:
        return
    for idx, row_id in list(open_rows.items()):
        try:
            await update(row_id, status="cancelled")
        except Exception as exc:  # noqa: BLE001 — audit must NEVER mask the cancel
            logger.warning("mark cancelled row=%s failed: %s", row_id, exc)
        open_rows.pop(idx, None)


def _fragment_files(worker_ws: Any, base_commit: str = "") -> dict[str, str]:
    """Return the relative-path → content map of a worker's isolated workspace.

    Reads the worker's written files from its ``_ChildSandbox`` root (the
    sub_sandbox/worktree dir). Returns an empty map when no workspace was allocated
    (shared_read / offline) or the dir is unreadable — the merge then has no fragment
    for that worker. Skips ``.git`` internals + unreadable/binary files.

    WORKTREE scoping (WR-03): a worktree checkout contains the WHOLE repo, so the
    fragment is restricted to the paths the worker actually CHANGED since the
    spawn-point ``base_commit`` (read through the workspace's ``changed_since``
    git handle). A failed/unavailable restriction degrades to NO fragment for a
    worktree (never a whole-repo "fragment" of arbitrary unmodified files).
    """
    if worker_ws is None:
        return {}
    sandbox = getattr(worker_ws, "_sandbox", None)
    root = getattr(sandbox, "root", None)
    if root is None:
        return {}
    restrict: set[str] | None = None
    if getattr(worker_ws, "_worktree_branch", None):
        changed_fn = getattr(worker_ws, "changed_since", None)
        if callable(changed_fn):
            try:
                restrict = set(changed_fn(base_commit))
            except Exception:  # noqa: BLE001 — restriction failure ⇒ no worktree fragment
                restrict = set()
        else:
            restrict = set()  # no git handle ⇒ cannot scope ⇒ no whole-repo fragment
    files: dict[str, str] = {}
    try:
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            # Exclude .git/.worktrees internals NESTED under the scanned root —
            # checked on the RELATIVE parts (WR-03): a worktree workspace root
            # itself lives under the parent's ``.worktrees/``, so an absolute-path
            # check would wrongly exclude EVERY file of a worktree fragment.
            rel_parts = path.relative_to(root).parts
            if ".git" in rel_parts or ".worktrees" in rel_parts:
                continue
            rel = path.relative_to(root).as_posix()
            if restrict is not None and rel not in restrict:
                continue
            try:
                files[rel] = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
    except OSError:
        return {}
    return files


def _spawn_point(base_workspace: Any) -> str:
    """The captured spawn-point commit (the 3-way merge-base) — or '' when no repo."""
    spawn_fn = getattr(base_workspace, "spawn_point_commit", None)
    if spawn_fn is None:
        return ""
    try:
        return spawn_fn() or ""
    except Exception:  # noqa: BLE001 — a missing repo degrades to no merge-base
        return ""


def _select_merge_strategy(isolation: str) -> str:
    """The ENGINE picks the merge strategy by name (INV-7 — NOT the manifest).

    ``git_3way`` integrates worktree fragments (per-worker branches merge back via the
    git handle); ``copy_disjoint`` integrates sub_sandbox fragments (worker files copy
    into the base, overlap → conflict). Deterministic default keyed on the isolation
    scope the engine already selected — never a workflow-name branch (INV-1).
    """
    return "git_3way" if isolation == _ISOLATION_WORKTREE else "copy_disjoint"


class _FileFragmentView:
    """Adapts a sub_sandbox worker workspace to the copy_disjoint fragment shape."""

    def __init__(self, name: str, files: dict[str, str]) -> None:
        self.name = name
        self._files = files

    def files(self) -> dict[str, str]:
        return dict(self._files)


class _BaseWriteView:
    """Adapts the base workspace to the copy_disjoint base shape (files() + write())."""

    def __init__(self, base_workspace: Any) -> None:
        self._base = base_workspace

    def files(self) -> dict[str, str]:
        return {}  # the base-since-spawn delta is not tracked offline; overlap is detected between fragments

    def write(self, path: str, content: str) -> None:
        writer = getattr(self._base, "write_file", None)
        if callable(writer):
            try:
                writer(path, content)
            except Exception as exc:  # noqa: BLE001 — a base write failure is non-fatal to collect
                logger.warning("merge base write_file(%s) failed: %s", path, exc)


class _WorktreeFragmentView:
    """Adapts a worktree worker to the git_3way fragment shape (runner + branch).

    ``commit_fn`` is an optional async callable ``(message: str) -> None`` that
    routes the inter-fragment commit through the ONE security-gated primitive
    (commit_in_sandbox).  None when no ectx/step is available (offline harness) —
    the capability falls back to a plain ``commit_all`` in that case.
    """

    def __init__(
        self,
        runner: Any,
        branch: str,
        base_commit: str,
        commit_fn: "Any | None" = None,
    ) -> None:
        self.runner = runner
        self.branch = branch
        self.base_commit = base_commit
        self.commit_fn = commit_fn


def _persist_merge_state(runner: Any, state: "FanoutMergeState") -> None:
    """Fire-and-forget helper: schedule persisting a ``FanoutMergeState`` to the wave_runs row.

    Delegates to ``runner.update_wave_run_merge_state`` (a coroutine on
    ``KernelServices``).  Uses ``asyncio.ensure_future`` so the caller — an async
    generator — does not need to ``await`` here.  The call is best-effort: if the
    runner has no such method (offline harness / tests that don't supply one) or if the
    task raises, the failure is silently swallowed (audit must NEVER abort the run,
    mirroring ``update_wave_run``'s BLE001 pattern).
    """
    update_fn = getattr(runner, "update_wave_run_merge_state", None)
    if not callable(update_fn):
        return
    try:
        coro = update_fn(state)
        asyncio.ensure_future(coro)
    except Exception:  # noqa: BLE001 — audit failure must not abort the run
        pass


async def _merge_fragments(
    runner: Any,
    base_workspace: Any,
    step: Any,
    isolation: str,
    fragments_meta: list,
    ctx: Any = None,
) -> AsyncIterator[dict]:
    """Run the engine-selected merge over the completed fragments + resolve conflicts.

    Emits ``merge_started`` → runs ``MergeStrategy.merge`` → ``merge_completed`` on a
    clean result. On a ``MergeResult`` with conflicts: writes an owner-scoped
    ``merge_conflict`` artifact + emits a ``merge_conflict`` event, THEN resolves per
    the step's ``on_conflict`` (``_resolve_conflict``). The merge runs ONLY over the
    workers that completed (a failed worker contributes no fragment). When no base/merge
    handle is reachable the merge is a clean no-op (offline/shared_read parity).

    ``ctx`` (optional, default None): the per-run ``ExecutionContext``; threaded in so
    the ``_WorktreeFragmentView.commit_fn`` can call ``commit_in_sandbox`` for the
    inter-fragment commit (Requirement 11 AC 9-10, Task 4.3).  None (offline harness)
    keeps the fallback ``commit_all`` path active — byte/behavior-identical for tests
    that supply no ``ctx``.
    """
    # Sort by declared worker index so the merge sequence is deterministic regardless
    # of which parallel worker finished first (Req 25 AC 1 / FANOUT-07 ordering).
    # fragments_meta is populated by _run_one as workers complete — parallel workers
    # append in arrival order.  Without this sort the strategy receives them in
    # non-deterministic completion order, not declared order.
    completed = sorted(
        [m for m in fragments_meta if m.get("status") == "complete"],
        key=lambda m: m.get("index", 0),
    )
    strategy_name = _select_merge_strategy(isolation)
    step_id = getattr(step, "agent_id", "fanout")

    yield {
        "type": "merge_started",
        "data": {
            "step": step_id,
            "strategy": strategy_name,
            "fragments": len(completed),
            "isolation": isolation,
        },
    }

    # Resolve the MergeStrategy through the runner handle (no direct registry import in
    # the offline harness path; the engine binds a resolver on the handle). When no
    # resolver is reachable the merge degrades to a clean no-op.
    strategy = _resolve_strategy(runner, strategy_name)
    if strategy is None or not completed:
        yield {
            "type": "merge_completed",
            "data": {
                "step": step_id,
                "strategy": strategy_name,
                "applied": [],
                "conflicts": 0,
            },
        }
        _persist_merge_state(
            runner,
            FanoutMergeState(
                step_id=step_id,
                worker_index=0,
                merge_state="clean",
                merge_applied=[],
                merge_conflicts=[],
                merge_strategy=strategy_name,
            ),
        )
        return

    # Build the typed fragments for the selected strategy.
    if strategy_name == "git_3way":
        # Task 4.3 (sandbox-git-versioning-v2, Req 11 AC 9-10): build a ``commit_fn``
        # async callable for each fragment that routes the inter-fragment commit through
        # ``commit_in_sandbox``.  The capability (git_3way.py) cannot import
        # engine.py (import-linter boundary), so we pre-build the callable here
        # (fanout.py IS in agents.execution_engine and CAN import it) and thread it
        # through the fragment view.  None when no ctx is available (offline harness)
        # — the capability falls back to plain ``commit_all`` (existing behavior).
        import types as _types  # noqa: PLC0415

        _merge_step = _types.SimpleNamespace(
            agent_id=getattr(step, "agent_id", "fanout-merge"),
            hooks=[],
            tools=None,
        )

        def _make_commit_fn(ws: Any) -> "Any | None":
            """Return an async commit_fn for the given workspace, or None."""
            if ctx is None:
                return None
            from agents.execution_engine.engine import commit_in_sandbox  # noqa: PLC0415

            async def _commit_fn(message: str) -> None:
                await commit_in_sandbox(
                    ws,
                    message,
                    ctx,
                    _merge_step,
                    audit_operation=None,
                    registry=None,
                )

            return _commit_fn

        fragments = [
            _WorktreeFragmentView(
                runner,
                m["branch"],
                m.get("base_commit", ""),
                commit_fn=_make_commit_fn(base_workspace),
            )
            for m in completed
            if m.get("branch")
        ]
        base = base_workspace
    else:
        fragments = [
            _FileFragmentView(f"worker-{m['index']}", _fragment_files(m["workspace"]))
            for m in completed
        ]
        base = _BaseWriteView(base_workspace)

    # Dynamically import MergeRefusedError so this module keeps its stdlib-only import
    # discipline at module level (import-linter kernel→ports scaffold stays green).
    # The import is deferred into the try/except scope so it only executes when the
    # merge strategy is about to run (not on every fan-out step).
    try:
        from app.agents.runtime.local import MergeRefusedError as _MergeRefusedError  # noqa: PLC0415
    except ImportError:
        _MergeRefusedError = None  # type: ignore[assignment,misc]

    try:
        # Task 4.3 (sandbox-git-versioning-v2, Req 11 AC 9-10): ``merge()`` is now
        # ``async`` for the ``git_3way`` strategy so it can ``await`` the
        # ``commit_fn`` between fragments.  ``copy_disjoint``, ``json``, and
        # ``html_fragment`` do NOT need a between-fragment commit and keep a
        # synchronous ``merge()`` that returns a plain ``MergeResult``.
        # We ``await`` unconditionally here; a coroutine from an async strategy is
        # awaited normally, and a plain ``MergeResult`` returned from a sync strategy
        # is NOT awaitable — but since ``git_3way`` is the only strategy that commits,
        # and it is the only one now async, ``await`` is safe: Python will raise if
        # the object isn't awaitable, which would surface a programmer error immediately.
        # For the non-git_3way strategies we keep the synchronous call via the existing
        # ``merge()`` name (import boundary: they stay sync-only, no async protocol
        # change required at the base Protocol level).
        import inspect as _inspect  # noqa: PLC0415

        _merge_coro = strategy.merge(base, fragments)
        if _inspect.isawaitable(_merge_coro):
            merge_result = await _merge_coro
        else:
            merge_result = _merge_coro
    except BaseException as exc:  # noqa: BLE001
        # Re-raise signals that must propagate (cancel, process exit).
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise

        # ── Refused-before-start (Task 7.2, Requirement 12 AC 1-5) ──────────────
        # A MergeRefusedError means git never started the merge — MERGE_HEAD was NOT
        # written.  This is distinct from a started-and-conflicted merge.  The applied
        # set is empty (nothing was integrated) and ``conflicts: []`` MUST NOT be
        # returned (it would falsely imply a clean merge).  The per-policy outcome is
        # the same four choices but the semantics differ: there is no conflict to
        # resolve, so merge_agent does NOT invoke the resolver and falls through to
        # human_gate.  A scan-blocked commit surfaces here as a refused merge for
        # policy purposes (Requirement 11 AC 12).
        if _MergeRefusedError is not None and isinstance(exc, _MergeRefusedError):
            branch = getattr(exc, "branch", str(exc))
            reason = getattr(exc, "reason", str(exc))
            logger.warning(
                "merge strategy %s refused to start for branch %r: %s",
                strategy_name,
                branch,
                reason,
            )
            # Artifact-before-event: write the conflict artifact first, then emit the
            # event (preserving the ordering rule from the started-and-conflicted path).
            ref_id = None
            write_conflict = getattr(runner, "write_merge_conflict_artifact", None)
            refused_payload: dict = {
                "step": step_id,
                "strategy": strategy_name,
                "refused": True,
                "branch": branch,
                "reason": reason,
                "applied": [],
                "conflicts": [],
            }
            if write_conflict is not None:
                try:
                    ref_id = await write_conflict(
                        producer_step=step_id, conflicts=[], payload=refused_payload
                    )
                except Exception as _art_exc:  # noqa: BLE001
                    logger.warning(
                        "merge_conflict artifact write failed (refused path): %s",
                        _art_exc,
                    )
            _persist_merge_state(
                runner,
                FanoutMergeState(
                    step_id=step_id,
                    worker_index=0,
                    merge_state="conflict",  # a refused merge is a conflict-class outcome
                    merge_applied=[],
                    merge_conflicts=[
                        {"refused": True, "branch": branch, "reason": reason}
                    ],
                    merge_strategy=strategy_name,
                    retained_state=[],
                ),
            )
            yield {
                "type": "merge_failed",
                "data": {
                    "step": step_id,
                    "strategy": strategy_name,
                    "refused": True,
                    "branch": branch,
                    "artifact_ref": ref_id,
                    "applied": [],
                    "conflicts": 0,
                },
            }
            async for ev in _resolve_refused(
                runner, step, refused_payload, fragments_meta
            ):
                yield ev
            return

        # WR-02: a crashed merge is FIRST-CLASS — never reported as a clean
        # merge_completed (consumers/audit would see success while nothing was
        # integrated). The distinct merge_failed event names the error; the run
        # continues (the crash never aborts the fan-out) but downstream sees the
        # truth, mirroring the conflict path's no-silent-overwrite discipline.
        logger.warning("merge strategy %s raised: %s", strategy_name, exc)
        yield {
            "type": "merge_failed",
            "data": {
                "step": step_id,
                "strategy": strategy_name,
                "error": str(exc),
                "applied": [],
                "conflicts": 0,
            },
        }
        _persist_merge_state(
            runner,
            FanoutMergeState(
                step_id=step_id,
                worker_index=0,
                merge_state="aborted",
                merge_applied=[],
                merge_conflicts=[],
                merge_strategy=strategy_name,
            ),
        )
        return

    if not getattr(merge_result, "conflicts", None):
        applied = list(getattr(merge_result, "applied", []) or [])
        yield {
            "type": "merge_completed",
            "data": {
                "step": step_id,
                "strategy": strategy_name,
                "applied": applied,
                "conflicts": 0,
            },
        }
        _persist_merge_state(
            runner,
            FanoutMergeState(
                step_id=step_id,
                worker_index=0,
                merge_state="clean",
                merge_applied=applied,
                merge_conflicts=[],
                merge_strategy=strategy_name,
            ),
        )
        return

    # ── Conflict path (FANOUT-08) — first-class, never a silent overwrite. ─────
    conflicts = list(merge_result.conflicts)
    applied = list(getattr(merge_result, "applied", []) or [])
    payload = {
        "step": step_id,
        "strategy": strategy_name,
        "conflicts": conflicts,
        "applied": applied,
    }
    ref_id = None
    write_conflict = getattr(runner, "write_merge_conflict_artifact", None)
    if write_conflict is not None:
        try:
            ref_id = await write_conflict(
                producer_step=step_id, conflicts=conflicts, payload=payload
            )
        except Exception as _art_exc:  # noqa: BLE001
            logger.warning("merge_conflict artifact write failed: %s", _art_exc)
    _persist_merge_state(
        runner,
        FanoutMergeState(
            step_id=step_id,
            worker_index=0,
            merge_state="conflict",
            merge_applied=applied,
            merge_conflicts=conflicts,
            merge_strategy=strategy_name,
            retained_state=[],
        ),
    )
    yield {
        "type": "merge_conflict",
        "data": {
            "step": step_id,
            "strategy": strategy_name,
            "conflicts": conflicts,
            "artifact_ref": ref_id if ref_id is not None else "",
        },
    }

    async for ev in _resolve_conflict(
        runner, step, merge_result, payload, fragments_meta
    ):
        yield ev


def _resolve_strategy(runner: Any, name: str) -> Any:
    """Resolve a MergeStrategy by name (via the runner handle, else the registry)."""
    resolver = getattr(runner, "resolve_merge_strategy", None)
    if callable(resolver):
        return resolver(name)
    # Fallback: resolve via the capability registry directly (the engine path). The
    # registry is import-clean for the kernel (it imports no app/engine internals).
    try:
        from agents.capabilities.registry import CapabilityRegistry, discover

        discover()
        return CapabilityRegistry().resolve("merge", name)
    except Exception as exc:  # noqa: BLE001 — no resolver reachable ⇒ clean no-op merge
        logger.debug("merge strategy %s unresolved: %s", name, exc)
        return None


async def _resolve_refused(
    runner: Any, step: Any, payload: dict, fragments_meta: list
) -> AsyncIterator[dict]:
    """Apply the per-policy outcome for a **refused-before-start** merge (Task 7.2).

    A refused merge means git never began the operation — MERGE_HEAD was NOT written.
    ``conflicts: []`` is therefore never returned (it would falsely imply a clean merge).
    The per-policy outcomes differ from the started-and-conflicted table because there
    is nothing to resolve — no conflict markers exist, no conflict artifact to feed a
    merge agent.

    Cross-policy invariant (Requirement 12 AC 5): prior successful fragment merge commits
    stay intact under every policy.  A refusal means the current fragment was never
    applied — no ``git merge --abort`` is needed because the merge never started.

    Policies:
      * ``abort``       — raise ``FanoutError``; the run fails.
      * ``partial``     — mark the current fragment dropped; keep every previously
                          applied fragment's commits intact; record ``retained_state``
                          in the durable merge state; continue with subsequent fragments.
      * ``merge_agent`` — no conflict to resolve; fall through to ``human_gate``
                          immediately (Requirement 12 AC 7 — "does not invoke the
                          resolver; there is no conflict to resolve").
      * ``human_gate``  — route through the ONE durable HITL so the decision persists
                          in ``gate_events`` and a resume re-enters at the recorded
                          fragment.
    """
    policy = getattr(step, "on_conflict", "human_gate") or "human_gate"
    step_id = payload.get("step", getattr(step, "agent_id", "fanout"))
    strategy_name = payload.get("strategy", "")

    if policy == "abort":
        raise FanoutError(
            f"fan-out merge refused before start (on_conflict=abort): "
            f"branch={payload.get('branch')!r} reason={payload.get('reason')!r}"
        )

    if policy == "partial":
        # Keep every previously applied fragment's commits intact; mark this fragment
        # dropped.  The retained set is every fragment whose branch is already present
        # in the base workspace's history — we record it explicitly so it is
        # inspectable rather than implied (Requirement 12 AC 5).
        retained = [
            m.get("branch") or f"worker-{m.get('index', '?')}"
            for m in fragments_meta
            if m.get("status") == "complete"
        ]
        _persist_merge_state(
            runner,
            FanoutMergeState(
                step_id=step_id,
                worker_index=0,
                merge_state="partial",
                merge_applied=retained,
                merge_conflicts=[
                    {
                        "refused": True,
                        "branch": payload.get("branch"),
                        "reason": payload.get("reason"),
                    }
                ],
                merge_strategy=strategy_name,
                retained_state=retained,
            ),
        )
        yield {
            "type": "merge_partial",
            "data": {
                "step": step_id,
                "refused": True,
                "applied": retained,
                "dropped": [payload.get("branch")],
            },
        }
        return

    # merge_agent: no conflict to resolve → fall through to human_gate immediately.
    # The merge_agent policy is for *resolving* conflict markers; a refused merge has
    # none, so invoking the resolver would either fabricate a conflict or silently
    # succeed having changed nothing.  Neither is acceptable.
    if policy == "merge_agent":
        logger.info(
            "merge_agent policy on refused merge (branch=%r) — "
            "no conflict to resolve; falling through to human_gate",
            payload.get("branch"),
        )
        # Fall through to human_gate below (no return here).

    # Default / human_gate / merge_agent-fallthrough — the ONE durable HITL.
    async for ev in _run_human_gate_resolution(runner, step, payload):
        yield ev


async def _resolve_conflict(
    runner: Any, step: Any, merge_result: Any, payload: dict, fragments_meta: list
) -> AsyncIterator[dict]:
    """Apply the per-policy outcome for a **started-and-conflicted** merge (Task 7.2).

    Called AFTER ``merge_worktree`` ran, found conflict markers, aborted the in-progress
    merge (``git merge --abort`` — ``local.py`` already does this when MERGE_HEAD is
    present), and returned a non-empty ``conflicts`` list.  The base working tree is
    clean by the time this function is entered.

    Cross-policy invariant (Requirement 12 AC 5): under EVERY policy and for BOTH a
    refusal and a started-and-conflicted merge, prior successful fragment merge commits
    stay intact.  Nothing here may unwind an already-committed fragment — that is the
    v1 defect where ``git merge --abort`` destroyed fragment 1's work after fragment 2
    was refused.  The ``partial`` policy ONLY aborts the conflicting fragment's merge
    (already done by ``merge_worktree``); every earlier applied fragment's commits are
    untouched.

    Policies (Requirement 12 AC 6-8):
      * ``abort``       — raise ``FanoutError``; the run fails.
      * ``partial``     — retained state is every fragment whose merge already committed
                          (``applied`` from the merge result), plus nothing from the
                          conflicting fragment.  Record retained set in
                          ``FanoutMergeState.retained_state`` and keep the conflicting
                          fragment's artifacts in ``artifact_refs`` for recovery.
                          Continue with subsequent fragments.
      * ``merge_agent`` — invoke the manifest-declared resolver, bounded at
                          ``MERGE_AGENT_MAX_ATTEMPTS`` (=2).  Each attempt must
                          materialize a clean, verified result.  Exhaustion falls
                          through to ``human_gate`` — no oscillation past the bound.
      * ``human_gate``  — route through the ONE durable HITL (``_run_review_gate``);
                          decision persists in ``gate_events`` so a resume re-enters
                          at the recorded fragment.
    """
    policy = getattr(step, "on_conflict", "human_gate") or "human_gate"
    step_id = payload.get("step", getattr(step, "agent_id", "fanout"))
    strategy_name = payload.get("strategy", "")

    if policy == "abort":
        raise FanoutError(
            f"fan-out merge aborted on conflict (on_conflict=abort): "
            f"{[c.get('path') for c in merge_result.conflicts]}"
        )

    if policy == "partial":
        # Retained state: every fragment whose merge already committed (the ``applied``
        # set from the merge strategy) plus nothing from the conflicting fragment.
        # ``git merge --abort`` was already called by merge_worktree (local.py) when
        # MERGE_HEAD was present — the conflicting fragment's work is already discarded.
        # Fragment artifacts for the dropped fragment were already written pre-merge
        # (FANOUT-06/WR-03) and remain in artifact_refs for operator recovery.
        applied_set = list(getattr(merge_result, "applied", []) or [])
        conflicts_list = list(getattr(merge_result, "conflicts", []) or [])
        _persist_merge_state(
            runner,
            FanoutMergeState(
                step_id=step_id,
                worker_index=0,
                merge_state="partial",
                merge_applied=applied_set,
                merge_conflicts=conflicts_list,
                merge_strategy=strategy_name,
                retained_state=applied_set,
            ),
        )
        yield {
            "type": "merge_partial",
            "data": {
                "step": step_id,
                "applied": applied_set,
                "dropped": [c.get("path") for c in conflicts_list],
            },
        }
        return

    if policy == "merge_agent":
        async for ev in _run_merge_agent(runner, step, payload):
            yield ev
        return

    # Default: human_gate — the ONE durable HITL (decision persists in gate_events).
    async for ev in _run_human_gate_resolution(runner, step, payload):
        yield ev


async def _run_merge_agent(
    runner: Any, step: Any, payload: dict
) -> AsyncIterator[dict]:
    """Bounded merge-agent retry (≤ MERGE_AGENT_MAX_ATTEMPTS) then human_gate fallback.

    The merge worker is the step's declared merge-agent worker; when none is designated
    (or the worker never resolves the conflict within the bound) we fall back to the ONE
    durable human_gate — NEVER oscillating past the bound (Pitfall 8 / T-11-03-03).
    """
    fanout = getattr(step, "fanout", None)
    merge_worker = getattr(fanout, "merge_agent", None) if fanout is not None else None
    run_merge_worker = getattr(runner, "run_merge_agent", None)

    attempts = 0
    resolved = False
    if merge_worker and callable(run_merge_worker):
        while attempts < MERGE_AGENT_MAX_ATTEMPTS and not resolved:
            attempts += 1
            yield {
                "type": "merge_agent_attempt",
                "data": {
                    "step": getattr(step, "agent_id", "fanout"),
                    "worker": merge_worker,
                    "attempt": attempts,
                    "max_attempts": MERGE_AGENT_MAX_ATTEMPTS,
                },
            }
            try:
                resolved = bool(
                    await run_merge_worker(merge_worker, payload, attempt=attempts)
                )
            except Exception as exc:  # noqa: BLE001 — a failed attempt counts, never aborts
                logger.warning("merge_agent attempt %s failed: %s", attempts, exc)
                resolved = False
        if resolved:
            yield {
                "type": "merge_completed",
                "data": {
                    "step": getattr(step, "agent_id", "fanout"),
                    "strategy": payload.get("strategy"),
                    "resolved_by": "merge_agent",
                    "attempts": attempts,
                    "conflicts": 0,
                },
            }
            return

    # Unresolved (no designated worker, or bound exhausted) → human_gate fallback.
    async for ev in _run_human_gate_resolution(runner, step, payload):
        yield ev


async def _run_human_gate_resolution(
    runner: Any, step: Any, payload: dict
) -> AsyncIterator[dict]:
    """Route a merge conflict through the ONE durable HITL (run_human_gate).

    Delegates to ``ctx.runner.run_human_gate(step, payload=...)`` — the SINGLE durable
    review gate (``_run_review_gate``; NO sibling merge-specific gate, T-11-03-04). The
    merge_conflict payload rides the generic ``review_gate_ready.data.output``. The
    gate's pause/resume round-trips on the user's resolution; its review-gate events are
    re-yielded unchanged. When no gate handle is reachable (offline harness) the
    resolution degrades to a recorded ``merge_human_gate_skipped`` event so the fan-out
    still completes (parity with the no-store degrade pattern).
    """
    gate_fn = getattr(runner, "run_human_gate", None)
    if not callable(gate_fn):
        yield {
            "type": "merge_human_gate_skipped",
            "data": {
                "step": getattr(step, "agent_id", "fanout"),
                "reason": "no durable HITL handle reachable (offline)",
            },
        }
        return
    async for ev in gate_fn(step, payload=payload):
        yield ev


async def _teardown_allocated(
    runner: Any, base_workspace: Any, allocated: list, *, delete_branch: bool = True
) -> None:
    """Reclaim EVERY allocated isolated workspace — happy path AND cancel AND abort.

    Invoked from the ``run_fanout`` ``finally`` so it runs whether the fan-out body
    completed normally, was cancelled mid-flight, or aborted on BudgetExceeded (Pitfall
    5 / RESUME-01 — no leaks on any path). Prefers the ``teardown_isolated_workspace``
    handle (the cancel-path teardown entry point) and falls back to
    ``reclaim_isolated_workspace``; a ``worktree`` workspace is removed via
    ``remove_worktree`` (git worktree remove; branch deleted when ``delete_branch=True``,
    retained when ``False`` — Requirement 28) and a ``sub_sandbox`` child via its own
    ``teardown`` (child-dir rmtree, which never touches the parent). Each teardown is
    best-effort so an orphaned worktree/dir is logged, not fatal (INV-3: cleanup must
    never break the run). The list is cleared after teardown so a re-entry can never
    double-reclaim a workspace.
    """
    teardown = getattr(runner, "teardown_isolated_workspace", None)
    reclaim = getattr(runner, "reclaim_isolated_workspace", None)
    for ws in allocated:
        try:
            if teardown is not None:
                await teardown(base_workspace, ws, delete_branch=delete_branch)
            elif reclaim is not None:
                await reclaim(base_workspace, ws)
        except Exception as exc:  # noqa: BLE001 — a teardown failure must not abort the run
            logger.warning("fan-out workspace teardown failed: %s", exc)
    allocated.clear()
