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

    # WR-05 (defense-in-depth): reject DUPLICATE task ids before any work. The ``by_id``
    # map is last-wins, so a duplicate silently drops the earlier task and the in-degree
    # decrement loop (which iterates the ORIGINAL list) decrements twice → negative.
    # json_tasks is the primary gate (untrusted agent JSON); THIS guard protects any other
    # caller that builds tasks without it. Raises pre-spawn (zero wave_runs/subagent_runs).
    if len(by_id) != len(tasks):
        raise WaveBuildError("duplicate task id")

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

        # ── MID-WAVE resume skip-check (12-03 / WAVE-03, D-07; CR-03/CR-04/WR-01) ──
        # On a durable IN-PROCESS RESUME (``ctx.is_resuming``) the strategy consults the
        # durable wave rows via the runner handle (best-effort, None-degrading offline) to
        # avoid re-spawning a WHOLE wave that already completed before the restart:
        #   * a wave whose ``wave_runs`` row is TERMINAL (completed) FOR THIS STEP is
        #     skipped wholesale (its workers' fragments are already durable — Phase 11
        #     persists pre-merge); the read is STEP-FILTERED (``step == step_id``) so a
        #     second wave_scheduler step in the same run never consumes the FIRST step's
        #     completed wave indices (CR-04 cross-step contamination).
        #   * the FIRST INCOMPLETE wave is re-run in its ENTIRETY (every task) through
        #     run_fanout. Waves run PARALLEL, so completion order != dispatch order — the
        #     per-task identity needed for a correct partial skip is NOT on subagent_runs
        #     (migration 0019: parent_step/worker_agent/depth/isolation/status only — no
        #     task_id/worker_index). Re-running a completed file-writer worker is wasteful
        #     but CORRECT (its fragment is overwritten deterministically into an isolated
        #     workspace); skipping an INCOMPLETE one would be DATA LOSS (CR-03). The
        #     per-task skip is the CR-03-followup deferral (CONTEXT.md Deferred Ideas):
        #     an additive migration stamping task identity on subagent_runs enables it.
        # This is the SAME run_fanout path (INV-12 single spawn home). Dormant for a normal
        # run (``is_resuming`` False ⇒ empty set ⇒ byte/event-identical).
        _completed_wave_indices: set[int] = set()
        _wave_rows: list = []
        _resuming = bool(getattr(ctx, "is_resuming", False))
        if _resuming:
            _wave_rows = await runner.read_wave_runs()
            _completed_wave_indices = {
                int(getattr(r, "wave_index", -1))
                for r in _wave_rows
                if getattr(r, "step", None) == step_id
                and getattr(r, "status", None) == "completed"
            }

        # ── Dispatch each wave through the SINGLE kernel run_fanout spawn path ──────
        # Each wave persists ONE owner-scoped wave_runs row (running -> terminal) and
        # emits wave_started/wave_completed/wave_failed events. The recorders are
        # reached via ctx.runner (best-effort, None-degrading offline) so the strategy
        # stays import-pure. All events are plain dicts — the engine's single emit
        # boundary stamps seq/event_id (zero websocket edits, Pattern 4).
        for wave_index, wave in enumerate(waves):
            # MID-WAVE resume: a wave already driven to a terminal status before the
            # restart is skipped wholesale (its fragments are durable). The
            # ``_completed_wave_indices`` set is step-filtered (CR-04) so only THIS
            # step's completed waves are skipped.
            if wave_index in _completed_wave_indices:
                continue

            # CR-03: the first incomplete wave re-runs in its ENTIRETY (no prefix skip).
            task_ids = [t.id for t in wave]
            requests = [{"agent": "self", "input": t.body} for t in wave]

            # WR-01: on resume, before recording the re-entry row, flip any STALE
            # pre-crash non-terminal (``running``) wave_runs row for THIS (step, wave) to a
            # terminal ``superseded`` status (a new free-String value — the status column
            # is free String, no sa.Enum, so this is NOT a schema change). Otherwise the
            # pre-crash row stays ``running`` forever and ``_first_incomplete_step`` reads
            # the wave step as permanently incomplete (the engine never lets the step finish).
            if _resuming:
                for r in _wave_rows:
                    if (
                        getattr(r, "step", None) == step_id
                        and int(getattr(r, "wave_index", -1)) == wave_index
                        and getattr(r, "status", None) == "running"
                    ):
                        _stale_id = getattr(r, "id", None)
                        if _stale_id is not None:
                            await runner.update_wave_run(_stale_id, status="superseded")

            row_id = await runner.record_wave_run(
                step=step_id, wave_index=wave_index, task_ids=task_ids, status="running"
            )
            yield {
                "type": "wave_started",
                "data": {"step": step_id, "wave_index": wave_index, "task_ids": task_ids},
            }
            try:
                async for event in runner.run_fanout(requests, ctx, step=step):
                    # CR-06 (backend half): stamp the current wave_index + step onto the
                    # subagent_spawned/subagent_result events as the strategy re-yields
                    # them, so the FE (12-07) can fold worker leaves into their wave group.
                    # run_fanout itself stays the generic flat-fanout path (INV-12 single
                    # spawn home, no notion of waves) — the wave_index is the wave
                    # strategy's knowledge, stamped at ITS re-yield boundary. The CONTRACT
                    # 12-07 reads (recorded in 12-06-SUMMARY.md): flat on event ``data`` —
                    # ``wave_index`` (number), ``step`` (string), and the existing
                    # ``worker`` (number, unchanged). A copy of the data dict is stamped so
                    # a shared/re-used run_fanout dict is never mutated under the kernel.
                    if event.get("type") in ("subagent_spawned", "subagent_result"):
                        _data = dict(event.get("data") or {})
                        _data["wave_index"] = wave_index
                        _data["step"] = step_id
                        event = {**event, "data": _data}
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
