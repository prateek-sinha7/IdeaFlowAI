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
from typing import Any, AsyncIterator

from agents.execution_engine.budget import DEFAULT_MAX_CONCURRENCY, MERGE_AGENT_MAX_ATTEMPTS

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
        if ws_spent_fn is not None and getattr(budget, "workspace_ceiling", None) is not None:
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
        except Exception as exc:  # the budget module's BudgetExceeded — surface + re-raise
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
    # Every allocated isolated workspace is recorded so this plan can teardown the
    # happy-path workspaces after collect; 11-05 extends this list's teardown to the
    # cancel/finally path (ALL allocations, including a mid-flight cancel).
    allocated: list[Any] = []

    # Each entry: {"index", "agent_id", "workspace", "branch", "base_commit"} — the
    # merge inputs collected per worker (the isolated workspace handle for sub_sandbox,
    # the worktree branch + spawn-point commit for worktree). Populated in _run_one.
    fragments_meta: list[dict] = []

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

        # (5a) Fragment persistence BEFORE merge (FANOUT-06) — each worker's output
        # persists as a typed lineage-tracked fragment artifact, so partial results
        # survive an abort/cancel (11-04/11-05 consume the ref). Best-effort: a worker
        # that wrote nothing (or no persist handle reachable) leaves artifact_ref=None.
        artifact_ref = None
        write_fragment = getattr(runner, "write_fragment_artifact", None)
        frag_files = _fragment_files(worker_ws)
        if status == "complete" and write_fragment is not None and frag_files:
            # Persist the worker's primary deliverable content (the concatenation is a
            # stable digest of the fragment; the typed ref carries provenance + hash).
            primary_path = sorted(frag_files.keys())[0]
            artifact_ref = await write_fragment(
                producer_step=step_id,
                worker_agent=agent_id,
                worker_index=idx,
                content=frag_files[primary_path],
                location=primary_path,
            )

        # Record the merge inputs for this worker (the merge reads them after collect).
        fragments_meta.append({
            "index": idx,
            "agent_id": agent_id,
            "workspace": worker_ws,
            "status": status,
            "branch": getattr(worker_ws, "_worktree_branch", None),
            "base_commit": _spawn_point(base_workspace),
        })

        result = {"worker": idx, "agent": agent_id, "row_id": row_id, "status": status}
        if artifact_ref is not None:
            result["artifact_ref"] = artifact_ref
        return result

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

    # ── Budget warning at ≥80% consumption (OBS-01) ───────────────────────────
    # After the workers are collected, emit a visible budget_warning when any ceiling
    # is ≥ BUDGET_WARN_THRESHOLD (0.8) consumed — through the single emit boundary +
    # the generic forward (zero websocket.py edits). Best-effort: a manager without the
    # warn handle (a bare stub) is skipped (parity for the offline harness).
    if budget is not None:
        warn_fn = getattr(budget, "warn_threshold_reached", None)
        if callable(warn_fn):
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

    # ── (5b) Merge dispatch (FANOUT-07/08) ────────────────────────────────────
    # The fragments are integrated into the base workspace via the engine-selected
    # MergeStrategy. Replaces the 11-01 trivial pass-through. The merge runs only over
    # the COMPLETED workers' fragments (a failed worker contributes nothing). When no
    # base/merge is reachable (offline harness / shared_read), the merge degrades to a
    # clean no-op so the fan-out still completes.
    async for ev in _merge_fragments(
        runner, base_workspace, step, isolation, fragments_meta
    ):
        yield ev

    # Happy-path teardown — collect/merge is done, so reclaim every allocated
    # isolated workspace (worktree remove + branch delete, or child-dir rmtree). The
    # FULL cancel-path teardown (reclaim on a mid-flight cancel/exception too) lands
    # in 11-05; here we reclaim the post-collect happy-path workspaces. Best-effort
    # per workspace so a teardown failure never aborts the run.
    await _teardown_allocated(runner, base_workspace, allocated)


def _fragment_files(worker_ws: Any) -> dict[str, str]:
    """Return the relative-path → content map of a worker's isolated workspace.

    Reads the worker's written files from its ``_ChildSandbox`` root (the
    sub_sandbox/worktree dir). Returns an empty map when no workspace was allocated
    (shared_read / offline) or the dir is unreadable — the merge then has no fragment
    for that worker. Skips ``.git`` internals + unreadable/binary files.
    """
    if worker_ws is None:
        return {}
    sandbox = getattr(worker_ws, "_sandbox", None)
    root = getattr(sandbox, "root", None)
    if root is None:
        return {}
    files: dict[str, str] = {}
    try:
        for path in sorted(root.rglob("*")):
            if not path.is_file() or ".git" in path.parts or ".worktrees" in path.parts:
                continue
            try:
                files[path.relative_to(root).as_posix()] = path.read_text(encoding="utf-8")
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
    """Adapts a worktree worker to the git_3way fragment shape (runner + branch)."""

    def __init__(self, runner: Any, branch: str, base_commit: str) -> None:
        self.runner = runner
        self.branch = branch
        self.base_commit = base_commit


async def _merge_fragments(
    runner: Any, base_workspace: Any, step: Any, isolation: str, fragments_meta: list
) -> AsyncIterator[dict]:
    """Run the engine-selected merge over the completed fragments + resolve conflicts.

    Emits ``merge_started`` → runs ``MergeStrategy.merge`` → ``merge_completed`` on a
    clean result. On a ``MergeResult`` with conflicts: writes an owner-scoped
    ``merge_conflict`` artifact + emits a ``merge_conflict`` event, THEN resolves per
    the step's ``on_conflict`` (``_resolve_conflict``). The merge runs ONLY over the
    workers that completed (a failed worker contributes no fragment). When no base/merge
    handle is reachable the merge is a clean no-op (offline/shared_read parity).
    """
    completed = [m for m in fragments_meta if m.get("status") == "complete"]
    strategy_name = _select_merge_strategy(isolation)
    step_id = getattr(step, "agent_id", "fanout")

    yield {
        "type": "merge_started",
        "data": {"step": step_id, "strategy": strategy_name,
                 "fragments": len(completed), "isolation": isolation},
    }

    # Resolve the MergeStrategy through the runner handle (no direct registry import in
    # the offline harness path; the engine binds a resolver on the handle). When no
    # resolver is reachable the merge degrades to a clean no-op.
    strategy = _resolve_strategy(runner, strategy_name)
    if strategy is None or not completed:
        yield {"type": "merge_completed",
               "data": {"step": step_id, "strategy": strategy_name, "applied": [], "conflicts": 0}}
        return

    # Build the typed fragments for the selected strategy.
    if strategy_name == "git_3way":
        fragments = [
            _WorktreeFragmentView(runner, m["branch"], m.get("base_commit", ""))
            for m in completed if m.get("branch")
        ]
        base = base_workspace
    else:
        fragments = [
            _FileFragmentView(f"worker-{m['index']}", _fragment_files(m["workspace"]))
            for m in completed
        ]
        base = _BaseWriteView(base_workspace)

    try:
        merge_result = strategy.merge(base, fragments)
    except Exception as exc:  # noqa: BLE001 — a merge crash must not abort the run silently
        logger.warning("merge strategy %s raised: %s", strategy_name, exc)
        yield {"type": "merge_completed",
               "data": {"step": step_id, "strategy": strategy_name, "applied": [], "conflicts": 0}}
        return

    if not getattr(merge_result, "conflicts", None):
        yield {"type": "merge_completed", "data": {
            "step": step_id, "strategy": strategy_name,
            "applied": list(getattr(merge_result, "applied", []) or []),
            "conflicts": 0,
        }}
        return

    # ── Conflict path (FANOUT-08) — first-class, never a silent overwrite. ─────
    conflicts = list(merge_result.conflicts)
    payload = {
        "step": step_id, "strategy": strategy_name, "conflicts": conflicts,
        "applied": list(getattr(merge_result, "applied", []) or []),
    }
    ref_id = None
    write_conflict = getattr(runner, "write_merge_conflict_artifact", None)
    if write_conflict is not None:
        ref_id = await write_conflict(producer_step=step_id, conflicts=conflicts, payload=payload)
    yield {"type": "merge_conflict", "data": {
        "step": step_id, "strategy": strategy_name,
        "conflicts": conflicts, "artifact_ref": ref_id,
    }}

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


async def _resolve_conflict(
    runner: Any, step: Any, merge_result: Any, payload: dict, fragments_meta: list
) -> AsyncIterator[dict]:
    """Resolve a reported merge conflict per the step's ``on_conflict`` policy (§13).

    Four policies (the §13 set):
      * ``human_gate`` (default) — delegate to ``ctx.runner.run_human_gate(...)`` → the
        ONE durable HITL (``_run_review_gate``; NO sibling merge-specific gate). The
        merge_conflict payload rides the generic ``review_gate_ready.data.output``
        (the 10-03 approval-snapshot precedent); the gate pauses/resumes on resolution.
      * ``merge_agent`` — spawn the designated merge worker bounded at
        ``MERGE_AGENT_MAX_ATTEMPTS`` (=2); after 2 unresolved attempts FALL BACK to
        ``human_gate`` (Pitfall 8 — no oscillation). The merge-agent worker is sourced
        from the step's declared merge-agent worker; when none is designated, fall back
        to human_gate immediately.
      * ``partial`` — keep the non-conflicting fragments (already ``applied``), mark the
        conflicted work failed, continue.
      * ``abort`` — fail the run (raise, surfacing the conflict).
    """
    policy = getattr(step, "on_conflict", "human_gate") or "human_gate"

    if policy == "abort":
        raise FanoutError(
            f"fan-out merge aborted on conflict (on_conflict=abort): "
            f"{[c.get('path') for c in merge_result.conflicts]}"
        )

    if policy == "partial":
        # Keep the applied (non-conflicting) fragments; mark conflicted work failed.
        yield {"type": "merge_partial", "data": {
            "step": getattr(step, "agent_id", "fanout"),
            "applied": list(getattr(merge_result, "applied", []) or []),
            "dropped": [c.get("path") for c in merge_result.conflicts],
        }}
        return

    if policy == "merge_agent":
        async for ev in _run_merge_agent(runner, step, payload):
            yield ev
        return

    # Default: human_gate — the ONE durable HITL.
    async for ev in _run_human_gate_resolution(runner, step, payload):
        yield ev


async def _run_merge_agent(runner: Any, step: Any, payload: dict) -> AsyncIterator[dict]:
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
            yield {"type": "merge_agent_attempt", "data": {
                "step": getattr(step, "agent_id", "fanout"),
                "worker": merge_worker, "attempt": attempts,
                "max_attempts": MERGE_AGENT_MAX_ATTEMPTS,
            }}
            try:
                resolved = bool(await run_merge_worker(merge_worker, payload, attempt=attempts))
            except Exception as exc:  # noqa: BLE001 — a failed attempt counts, never aborts
                logger.warning("merge_agent attempt %s failed: %s", attempts, exc)
                resolved = False
        if resolved:
            yield {"type": "merge_completed", "data": {
                "step": getattr(step, "agent_id", "fanout"),
                "strategy": payload.get("strategy"), "resolved_by": "merge_agent",
                "attempts": attempts, "conflicts": 0,
            }}
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
        yield {"type": "merge_human_gate_skipped", "data": {
            "step": getattr(step, "agent_id", "fanout"),
            "reason": "no durable HITL handle reachable (offline)",
        }}
        return
    async for ev in gate_fn(step, payload=payload):
        yield ev


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
