"""agents/capabilities/strategies/wave_scheduler.py — the ``wave_scheduler`` strategy.

The DECLARATIVE wave-scheduling entry point (WAVE-01): a step whose ``strategy:
wave_scheduler`` sources a STRUCTURED task list (a declared ``task_source`` → producer
step → typed content → registry-resolved parser, defaulting to ``json_tasks``),
topologically partitions it into deterministic WAVES via the pure :func:`build_waves`
seam, and runs EACH wave through the SINGLE kernel ``run_fanout`` spawn path via
``ctx.runner.run_fanout(...)``. The strategy holds NO spawn / worker-selection /
concurrency / isolation / merge logic of its own — that ALL lives in the unmodified
kernel ``run_fanout`` (INV-12 single home), so every wave inherits isolation, merge,
budget reserve, and cancellation. The strategy is the thin declarative seam plus the
pure ``build_waves`` topo-sort.

``build_waves`` is a pure stdlib Kahn-levels function (RESEARCH Pattern 2): topological
levels over ``depends_on`` with a stable tie-break by task id, then within each level a
conflict-key split so two tasks sharing a ``conflict_key`` NEVER co-schedule in the same
wave (the second deterministically spills to a later wave). It raises ``WaveBuildError``
BEFORE returning any wave on a dependency cycle or an unknown ``depends_on`` ref — so a
bad plan produces ZERO ``wave_runs`` / ``subagent_runs`` rows (T-12-01-INPUT).

**conflict_keys defaults to targets** (the DOCUMENTED default, Pitfall 6 / discretion
A2): when a task declares no explicit ``conflict_keys``, its ``targets`` set is used as
the conflict-key set. Disjoint targets ⇒ same wave; the same target ⇒ split. This keeps
two tasks that write the same file out of the same wave without the manifest author
having to restate the file as a conflict key.

Import purity (import-linter / INV-13): NOTHING from ``agents.execution_engine`` or
``app.*`` is imported — every kernel primitive (``run_fanout``, the typed-content read,
the wave-run recorders) is reached ONLY through the object-typed ``ctx.runner`` handle.
The task parser is resolved by NAME through the capability registry (the ``task_loop``
D-02 precedent). The pure ``build_waves`` + ``WaveBuildError`` live in THIS module.
"""

from __future__ import annotations

import logging
from typing import Any, AsyncIterator

from agents.capabilities.registry import CapabilityRegistry, register
from agents.workflows.plan import Task

logger = logging.getLogger(__name__)

# Default task parser when the step declares none — the wave default is the STRUCTURED
# json_tasks parser (NOT heading_tasks; waves need the depends_on/conflict_keys surface).
_DEFAULT_PARSER = "json_tasks"


class WaveBuildError(Exception):
    """A wave plan is unschedulable — a dependency cycle or an unknown ``depends_on`` ref.

    Raised by :func:`build_waves` BEFORE returning any wave, so the scheduler never
    spawns on a bad plan (zero ``wave_runs`` / ``subagent_runs`` rows, T-12-01-INPUT).
    """


def build_waves(tasks: list[Task]) -> list[list[Task]]:
    """Topologically partition ``tasks`` into deterministic waves (pure, stdlib only).

    Kahn-levels over ``depends_on`` with a stable tie-break by task id, then a
    within-level conflict-key split:

    1. Validate EVERY ``depends_on`` ref against ``{t.id for t in tasks}`` — an unknown
       ref raises ``WaveBuildError`` naming the offender (pre-spawn).
    2. Compute in-degrees; each round take the ready set
       ``sorted([tid for tid in remaining if indeg[tid] == 0])`` (stable tie-break).
       A non-empty ``remaining`` with an empty ready set is a dependency cycle →
       ``WaveBuildError`` (pre-spawn).
    3. Within a level, split on conflict keys: ``keys = set(t.conflict_keys) or
       set(t.targets)`` (the documented default). A task whose keys overlap the keys
       already used THIS wave is deferred — it stays in ``remaining`` so it is picked
       deterministically the next round, landing in a later wave.

    Determinism: the same input twice yields byte-identical partitions (the ready set
    is sorted by id and the deferral order is stable). LOCKED (D-03).
    """
    by_id = {t.id: t for t in tasks}

    # 1. Validate refs BEFORE any work (raise pre-spawn → zero rows).
    for t in tasks:
        for dep in t.depends_on:
            if dep not in by_id:
                raise WaveBuildError(
                    f"task '{t.id}' depends_on unknown task '{dep}'"
                )

    # 2. Kahn levels (deterministic: sort the ready set by task id each round).
    indeg = {t.id: len(set(t.depends_on)) for t in tasks}
    remaining = set(by_id)
    waves: list[list[Task]] = []

    while remaining:
        ready_ids = sorted(tid for tid in remaining if indeg[tid] == 0)
        if not ready_ids:
            # remaining but none ready ⇒ a cycle among the survivors.
            raise WaveBuildError("dependency cycle detected")

        # 3. Within-level conflict-key split: tasks sharing a conflict key cannot
        #    co-schedule → keep the first (by id order), spill the rest to a later wave.
        scheduled: list[Task] = []
        used_keys: set[str] = set()
        for tid in ready_ids:
            t = by_id[tid]
            keys = set(t.conflict_keys) or set(t.targets)  # documented default (Pitfall 6)
            if keys & used_keys:
                # Defer: leave it in `remaining` (indeg still 0) → picked next round.
                continue
            used_keys |= keys
            scheduled.append(t)

        waves.append(scheduled)

        # Decrement in-degrees only for the tasks actually SCHEDULED this wave; the
        # deferred (conflicting) tasks stay in `remaining` with their indeg unchanged.
        for t in scheduled:
            remaining.discard(t.id)
            for u in tasks:
                if t.id in u.depends_on:
                    indeg[u.id] -= 1

    return waves


@register("strategy", "wave_scheduler", user_allowed=True)
class WaveSchedulerStrategy:
    """Declarative wave scheduler: parse a structured task list → waves → run_fanout.

    Satisfies the ``ExecutionStrategy`` port structurally (``name`` + ``run``). All
    kernel/app primitives are reached only via ``ctx.runner`` (the D-03 handle). Each
    ``build_waves`` level is dispatched through ONE ``run_fanout`` call.
    """

    name = "wave_scheduler"

    def __init__(self) -> None:
        # Module-singleton registry (capabilities are stateless) — resolves the task
        # parser by NAME (D-02), exactly like fanout_batch / task_loop.
        self._registry = CapabilityRegistry()

    async def run(self, step: Any, ctx: Any) -> AsyncIterator[dict]:
        """Source the structured task list, build waves, dispatch each wave via run_fanout."""
        runner = ctx.runner
        step_id = getattr(step, "agent_id", None)

        # ── Source the task list EXACTLY like fanout_batch (declared task_source) ──
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

        if not tasks:
            logger.warning(
                "wave_scheduler: no tasks parsed from source_step=%s — no waves run",
                source_step,
            )
            return

        # ── Partition into deterministic waves (raises pre-spawn on cycle/unknown ref) ─
        waves = build_waves(tasks)

        # ── MID-WAVE resume skip-check (12-03 / WAVE-03, D-07) ─────────────────────
        # On a durable IN-PROCESS RESUME (``ctx.is_resuming``) the strategy consults the
        # durable rows via the runner handle (best-effort, None-degrading offline) to
        # avoid re-spawning work that already completed before the restart:
        #   * a wave whose ``wave_runs`` row is TERMINAL (completed) is skipped wholesale
        #     (its workers' fragments are already durable — Phase 11 persists pre-merge);
        #   * within the in-flight wave (the lowest non-terminal wave_index) only the
        #     workers WITHOUT a terminal ``subagent_runs`` row are re-fanned-out.
        # This is the SAME run_fanout path with a filtered task set (INV-12 single spawn
        # home) — completed workers are NOT re-invoked. Dormant for a normal run
        # (``is_resuming`` False ⇒ both sets empty ⇒ byte/event-identical).
        _completed_wave_indices: set[int] = set()
        _completed_worker_count = 0
        if getattr(ctx, "is_resuming", False):
            _wave_rows = await runner.read_wave_runs()
            _completed_wave_indices = {
                int(getattr(r, "wave_index", -1))
                for r in _wave_rows
                if getattr(r, "status", None) == "completed"
            }
            _sub_rows = await runner.read_subagent_runs()
            # Terminal worker rows for THIS step (parent_step == step_id). The count of
            # terminal workers tells the in-flight wave how many of its leading tasks
            # already completed (run_fanout dispatches the requests in task order).
            _completed_worker_count = sum(
                1
                for r in _sub_rows
                if getattr(r, "parent_step", None) == step_id
                and getattr(r, "status", None) in ("complete", "completed")
            )

        # ── Dispatch each wave through the SINGLE kernel run_fanout spawn path ──────
        # Each wave persists ONE owner-scoped wave_runs row (running -> terminal) and
        # emits wave_started/wave_completed/wave_failed events. The recorders are
        # reached via ctx.runner (best-effort, None-degrading offline) so the strategy
        # stays import-pure. All events are plain dicts — the engine's single emit
        # boundary stamps seq/event_id (zero websocket edits, Pattern 4).
        # Running tally of workers completed in already-terminal waves, so the
        # remaining ``_completed_worker_count`` applies to the first IN-FLIGHT wave only.
        _workers_seen_in_completed_waves = 0
        for wave_index, wave in enumerate(waves):
            # MID-WAVE resume: a wave already driven to a terminal status before the
            # restart is skipped wholesale (its fragments are durable). Tally its task
            # count so the per-worker filter below targets the FIRST incomplete wave.
            if wave_index in _completed_wave_indices:
                _workers_seen_in_completed_waves += len(wave)
                continue

            # Within the first incomplete wave, skip the LEADING workers that already
            # reached a terminal subagent_runs status (run_fanout dispatches in task
            # order, so the first N completed workers are the first N tasks). The
            # completed fragments are reused (Phase 11 made them durable pre-merge);
            # only the remaining tasks are re-fanned-out through the SAME run_fanout.
            _wave_to_run = wave
            if getattr(ctx, "is_resuming", False) and _completed_worker_count > 0:
                _remaining_completed = _completed_worker_count - _workers_seen_in_completed_waves
                if _remaining_completed > 0:
                    _wave_to_run = wave[_remaining_completed:]
                    # Tasks consumed by this filter are accounted for; a later wave
                    # never re-applies the same completed-worker budget.
                    _workers_seen_in_completed_waves += min(_remaining_completed, len(wave))
                    if not _wave_to_run:
                        # Every worker in this wave already completed — skip it.
                        continue

            task_ids = [t.id for t in _wave_to_run]
            requests = [{"agent": "self", "input": t.body} for t in _wave_to_run]

            row_id = await runner.record_wave_run(
                step=step_id, wave_index=wave_index, task_ids=task_ids, status="running"
            )
            yield {
                "type": "wave_started",
                "data": {"step": step_id, "wave_index": wave_index, "task_ids": task_ids},
            }
            try:
                async for event in runner.run_fanout(requests, ctx, step=step):
                    yield event
            except Exception:
                await runner.update_wave_run(row_id, status="failed")
                yield {
                    "type": "wave_failed",
                    "data": {"step": step_id, "wave_index": wave_index, "task_ids": task_ids},
                }
                raise
            await runner.update_wave_run(row_id, status="completed")
            yield {
                "type": "wave_completed",
                "data": {"step": step_id, "wave_index": wave_index, "task_ids": task_ids},
            }
