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

import asyncio
import logging
import time
from typing import Any, AsyncIterator

from agents.capabilities import task_identity
from agents.capabilities.registry import CapabilityRegistry, register
from agents.capabilities.strategies._fanout_wave_stream import stream_wave_fanout
from agents.workflows.plan import Task

# WAVE-REPAIR: an EMPTY (or whitespace-only) target is treated as MISSING — evidence
# the worker never actually wrote real content, same as an absent file. NOT a byte
# minimum: a real fixture legitimately writes a 1-character file ("a"), and an
# arbitrary size floor false-positived on it (caught in review — see the call site).

logger = logging.getLogger(__name__)

# Default task parser when the step declares none — the wave default is the STRUCTURED
# json_tasks parser (NOT heading_tasks; waves need the depends_on/conflict_keys surface).
_DEFAULT_PARSER = "json_tasks"

# A revision writes its own files under revisions/<run_id>/. Every revision of a run's
# family shares the root run's folder, so the folder is named by this revision's own
# pipeline_run_id, which the engine writes to .context/run-id.txt at the start of each
# run. A custom_path task source may name that folder as {run_id}. RUN_ID_PATH mirrors
# agents.execution_engine.user_prompt.RUN_ID_PATH; this module may not import it.
RUN_ID_PATH = ".context/run-id.txt"
REVISION_TOKEN = "{run_id}"


def resolve_revision_path(path: str, sandbox: Any) -> str:
    """``path`` with ``{run_id}`` replaced by this revision's run id."""
    text = sandbox.read(RUN_ID_PATH) if sandbox is not None else None
    run_id = (text or "").strip()
    if not run_id:
        raise ValueError(
            f"wave_scheduler: task_source path {path!r} names the current revision, "
            f"but {RUN_ID_PATH} is missing or empty"
        )
    return path.replace(REVISION_TOKEN, run_id)


def read_custom_path(path: str, sandbox: Any) -> str:
    """The text of the one file a ``custom_path`` task source names.

    No fallback — not to build/tasks.json, not to the producer step's reply — so a
    missing or empty file stops the step before any task runs.
    """
    if REVISION_TOKEN in path:
        path = resolve_revision_path(path, sandbox)
    text = sandbox.read(path) if sandbox is not None else None
    if not (text or "").strip():
        raise ValueError(
            f"wave_scheduler: task_source path {path!r} is missing or empty"
        )
    return text


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
                raise WaveBuildError(f"task '{t.id}' depends_on unknown task '{dep}'")

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
            keys = set(t.conflict_keys) or set(
                t.targets
            )  # documented default (Pitfall 6)
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


# WAVE-REPAIR canary: a name unlikely to collide with any real deliverable, written
# then read back through the SAME ``runner.sandbox`` handle the repair check reads
# targets through, to positively prove writes actually round-trip before trusting a
# "missing" verdict from it (see the call site for why this exists).
_REPAIR_CANARY_PATH = ".wave_repair_canary"


def _check_sandbox_round_trips(sandbox: Any) -> bool:
    """True iff ``sandbox`` demonstrably persists a write and reads it back.

    Best-effort and side-effect-cleaned: any exception (read-only handle, missing
    write/read methods, ...) is treated as "can't prove it" → False, never raised.
    """
    try:
        marker = "wave-repair-canary"
        sandbox.write(_REPAIR_CANARY_PATH, marker)
        ok = sandbox.read(_REPAIR_CANARY_PATH) == marker
    except Exception:  # noqa: BLE001 — unprovable round-trip degrades to "don't trust it"
        return False
    finally:
        try:
            sandbox.path_for(_REPAIR_CANARY_PATH).unlink(missing_ok=True)
        except Exception:  # noqa: BLE001 — best-effort cleanup only
            pass
    return ok


@register(
    "strategy",
    "wave_scheduler",
    user_allowed=True,
    description="Schedule a structured task list into dependency-ordered waves, fanning each wave out concurrently.",
    config_schema={
        "type": "object",
        "properties": {
            "task_parser": {
                "type": "string",
                "description": "Capability name of the task_parser that yields the structured task list with dependencies.",
                "enum": ["json_tasks", "heading_tasks"],
                "default": "json_tasks",
            },
            "merge": {
                "type": "string",
                "description": "Capability name of the merge strategy applied per wave.",
                "enum": ["copy_disjoint", "git_3way", "json", "html_fragment"],
            },
        },
    },
)
class WaveSchedulerStrategy:
    """Declarative wave scheduler: parse a structured task list → waves → run_fanout.

    Satisfies the ``ExecutionStrategy`` port structurally (``name`` + ``run``). All
    kernel/app primitives are reached only via ``ctx.runner`` (the D-03 handle). Each
    ``build_waves`` level is dispatched through ONE ``run_fanout`` call.
    """

    name = "wave_scheduler"

    # ISS-131: spawn-only, exactly like fanout_batch — every wave is dispatched
    # through ``run_fanout`` and the step's own agent is never run inline, so the
    # inline review gate never fires for it.
    runs_agent_inline = False

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
        target = getattr(task_source, "target", None) if task_source else None
        sandbox = getattr(runner, "sandbox", None)
        if getattr(task_source, "kind", None) == "custom_path":
            tasks = parser.parse(read_custom_path(task_source.path, sandbox))
        else:
            tasks = task_identity.parse_step_tasks(
                parser, plan_output, sandbox=sandbox, target=target
            )

        if not tasks:
            logger.warning(
                "wave_scheduler: no tasks parsed from source_step=%s — no waves run",
                source_step,
            )
            yield {
                "type": "wave_skipped",
                "data": {
                    "agent_id": step_id,
                    "step": step_id,
                    "reason": f"no tasks parsed from source_step={source_step}",
                    "source_step": source_step,
                },
            }
            return

        # ── Partition into deterministic waves (raises pre-spawn on cycle/unknown ref) ─
        # Pitfall 7: build_waves / depends_on / the duplicate-id guard keep reading the
        # AUTHOR ``t.id`` — the content-addressed key only WRAPS it downstream.
        waves = build_waves(tasks)

        # ── RESUME-14: content-addressed key per author id (computed ONCE after parse) ──
        # key = sha256(upstream_context_hash · normalized_content · occurrence_ordinal).
        # The key WRAPS (namespaces) the author id — it stamps the request/subagent_runs
        # ``task_id`` slot and drives the per-worker resume skip, so a reorder/edit/dup/
        # upstream-rotate is handled while ``build_waves``/DAG/dup-guard stay on ``t.id``.
        _uhash_fn = getattr(runner, "upstream_context_hash", None)
        _upstream_hash = _uhash_fn(step) if callable(_uhash_fn) else ""
        _ordinals = task_identity.occurrence_ordinals(tasks)
        _key_by_id = {
            t.id: task_identity.compute_task_key(
                _upstream_hash, task_identity.normalize_task_content(t), _ordinals[i]
            )
            for i, t in enumerate(tasks)
        }

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
        # ── RESUME-09 per-WORKER SKIP CURSOR (kernel-computed; 46-04) ─────────────
        # The CR-03-followup the comment above waits on: now that RESUME-06 stamps
        # ``task_id`` on ``subagent_runs`` at spawn, the KERNEL computes the completed-
        # WORKER set for this step (``task_id`` of every ``status=="complete"`` child)
        # and stamps it on ``ctx.resume_completed_task_ids``. The first-incomplete wave
        # re-runs only its INCOMPLETE workers (``t.id`` not in the set) — identity-based,
        # NOT the deleted-for-cause prefix-by-count skip (12-06 CR-03). The completed
        # workers' fragments are already on disk (46-03 re-materialization). Read via
        # getattr → empty on a normal run ⇒ whole-wave dispatch unchanged (INV-3). The
        # kernel decides the set — the agent never does (SC-001/INV-1).
        _completed_worker_task_ids: set[str] = set()
        if _resuming:
            _wave_rows = await runner.read_wave_runs()
            _completed_wave_indices = {
                int(getattr(r, "wave_index", -1))
                for r in _wave_rows
                if getattr(r, "step", None) == step_id
                and getattr(r, "status", None) == "completed"
            }
            _cursor = getattr(ctx, "resume_completed_task_ids", None)
            if _cursor:
                _completed_worker_task_ids = _cursor.get(step_id, set()) or set()

        # ── Parent-step lifecycle (WS-EV) ──────────────────────────────────────────
        # A wave step never passes through the kernel ``_run_agent`` — it dispatches
        # workers via run_fanout instead — so the agent_start/agent_complete pair that
        # every single_shot step emits was simply absent here. The UI node had no
        # running state, no duration and no terminal tick, and ``_first_incomplete_step``
        # had no terminal agent event to read on resume. Emitted as plain dicts, stamped
        # by the engine's single emit boundary like every other event this strategy
        # yields. Same shape as engine.py's pair, minus the fields only the dispatch
        # loop knows (index/total/visit_count) — all optional on the wire.
        _t0 = time.monotonic()
        yield {
            "type": "agent_start",
            "data": {
                "agent_id": step_id,
                "name": getattr(step, "name", None) or step_id,
            },
        }

        # WAVE-REPAIR canary result — computed lazily, once, on first use (see the
        # per-wave repair block below): None = not checked yet, True/False = proven
        # capable / not. Cached across waves so the round-trip write only happens once
        # per run, not once per wave.
        _sandbox_repair_capable: bool | None = None

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

            # RESUME-09 (CR-03-followup): re-run only the INCOMPLETE workers of the
            # in-flight wave — a worker whose ``t.id`` is in the kernel-computed
            # completed set already finished pre-crash (its fragment is on disk from
            # 46-03 re-materialization) and is NOT re-invoked. Identity-based (by
            # ``task_id``), NOT the deleted prefix-by-count skip. Dormant on a normal
            # run (empty set ⇒ the whole wave runs, byte/event-identical).
            # RESUME-14: the completed set carries content-addressed KEYS (from
            # subagent_runs.task_id, now the key) — compare the wrapped key, not the
            # raw author id.
            wave_tasks = [
                t for t in wave if _key_by_id[t.id] not in _completed_worker_task_ids
            ]
            # AUTHOR ids feed the wave_runs row + the wave_started/completed/failed event
            # payloads — UNCHANGED (byte/event-neutral goldens; the key is durable-only).
            task_ids = [t.id for t in wave_tasks]
            # RESUME-06/RESUME-14: carry each task's content-addressed KEY on its request
            # so the spawned subagent_runs row is stamped with the skip-cursor key at SPAWN
            # (fanout.py:388 threads request task_id → subagent_runs.task_id).
            requests = [
                {
                    "agent": "self",
                    "input": t.body,
                    "task_id": _key_by_id[t.id],
                    # The author id (s01…). task_id is a content HASH — correct for
                    # the resume cursor, unreadable in a UI. Display only.
                    "task_author_id": t.id,
                }
                for t in wave_tasks
            ]

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
            # The PLAN totals ride along with every wave_started. The whole wave
            # list is built before this loop, so the run knows from its first
            # wave that there are four of them and thirty-four tasks in all — but
            # only the current wave's ids were ever sent, so a reader watching a
            # 34-task build saw "0 / 1 done" and no way to tell whether that was
            # the whole job or the first hundredth of it. Optional on the wire,
            # like every other field this strategy yields.
            yield {
                "type": "wave_started",
                "data": {
                    "step": step_id,
                    "wave_index": wave_index,
                    "task_ids": task_ids,
                    "wave_total": len(waves),
                    "task_total": sum(len(w) for w in waves),
                },
            }

            async def _dispatch_wave(disp_requests, disp_task_ids, disp_wave_index):
                # The wave index is a parameter, not a closure over the loop
                # variable: this generator only ever runs inside the iteration that
                # defines it today, but binding it explicitly keeps that true even if
                # the generator is ever stored or consumed later (ruff B023).
                #
                # CR-06 (backend half) + per-worker identity: ``stream_wave_fanout``
                # stamps every WORKER-queue event with wave_index/step/task_id/
                # worker_index/wave_total (the whole point — a wave clones one agent
                # N times, so raw worker events all carry the parent's agent_id).
                # subagent_spawned/subagent_result come off the run_fanout generator
                # itself (not the worker queue), so they're stamped here, same as
                # before (a copy of the data dict — a shared run_fanout dict is never
                # mutated under the kernel).
                async for event in stream_wave_fanout(
                    runner,
                    disp_requests,
                    ctx,
                    step=step,
                    wave_index=disp_wave_index,
                    task_ids=disp_task_ids,
                ):
                    if event.get("type") in ("subagent_spawned", "subagent_result"):
                        _data = dict(event.get("data") or {})
                        _data["wave_index"] = disp_wave_index
                        _data["step"] = step_id
                        event = {**event, "data": _data}
                    yield event

            try:
                async for event in _dispatch_wave(requests, task_ids, wave_index):
                    yield event
            except asyncio.CancelledError:
                # ISS-098: ``CancelledError`` has inherited from ``BaseException`` (not
                # ``Exception``) since Python 3.8, so a Stop-during-a-wave never reached the
                # arm below and this wave's row was left reading ``running`` forever (only
                # self-corrected by the WR-01 stale-row sweep on the next resume). Flip it to
                # a terminal ``cancelled`` (a free-String status like WR-01's ``superseded``,
                # NOT a schema change) and re-raise so cancellation propagates unchanged.
                # A NARROW arm, not ``except BaseException`` — that would also catch the
                # ``GeneratorExit`` thrown at the ``yield`` above when the consumer closes
                # this generator, where awaiting/yielding is a RuntimeError.
                await runner.update_wave_run(row_id, status="cancelled")
                raise
            except Exception:
                await runner.update_wave_run(row_id, status="failed")
                yield {
                    "type": "wave_failed",
                    "data": {
                        "step": step_id,
                        "wave_index": wave_index,
                        "task_ids": task_ids,
                    },
                }
                raise
            await runner.update_wave_run(row_id, status="completed")
            yield {
                "type": "wave_completed",
                "data": {
                    "step": step_id,
                    "wave_index": wave_index,
                    "task_ids": task_ids,
                },
            }

            # ── WAVE-REPAIR: assert every task's declared targets actually landed ──
            # Evidence: a 5-task fidelity wave silently produced only 4 files; a
            # 50-task wave silently dropped two screens. A "completed" wave never
            # asserted its workers actually wrote what they were supposed to. This
            # is non-fatal (repair, never fail the step) and bounded to ONE repair
            # pass per wave (never loop forever).
            #
            # Two false-positive guards, found the hard way (a coordinator caught
            # both from a single test run):
            #
            # 1. A ``runner.sandbox`` that can't positively be proven to round-trip
            #    a write is NOT trusted to report "missing" — an offline/fake/mock
            #    runner (every fixture in test_restart_resume.py /
            #    test_sample_wave_workflow.py) never actually persists a worker's
            #    output through this handle, so treating "read returned None" as
            #    "genuinely missing" fired the repair pass on EVERY wave,
            #    unconditionally doubling run_fanout dispatch cost. A cheap canary
            #    write+read (once per run, not per wave) is the only way to tell
            #    "target absent" from "this handle doesn't actually read what gets
            #    written" apart — no sandbox, or a sandbox that fails the canary,
            #    skips the whole check (same posture as no handle at all).
            # 2. Never during a resume (``_resuming``): the mid-wave resume
            #    contract already accounts for exactly the fan-out calls the
            #    resumed wave needs — an extra repair-triggered ``run_fanout`` call
            #    is a call the resume script/contract does not expect (observed:
            #    a scripted crash on "call #2", and a run driven past its own
            #    terminal ``completed`` status). Repair is a live-run-only concern;
            #    a resumed wave's targets were already asserted before the crash.
            sandbox = getattr(runner, "sandbox", None) if not _resuming else None
            if sandbox is not None and _sandbox_repair_capable is None:
                _sandbox_repair_capable = _check_sandbox_round_trips(sandbox)
            if sandbox is not None and not _sandbox_repair_capable:
                sandbox = None
            if sandbox is not None:
                # ``sandbox`` is bound as a default so the check reads THIS wave's
                # handle even if the function outlives the iteration (ruff B023).
                def _target_missing(path: str, sandbox=sandbox) -> bool:
                    try:
                        content = sandbox.read(path)
                    except Exception:  # noqa: BLE001 — a read failure counts as missing
                        return True
                    return content is None or not content.strip()

                missing_tasks = [
                    t
                    for t in wave_tasks
                    if t.targets and any(_target_missing(p) for p in t.targets)
                ]
                if missing_tasks:
                    missing_ids = [t.id for t in missing_tasks]
                    logger.warning(
                        "wave_scheduler: wave %s step=%s missing targets for tasks %s "
                        "— dispatching one repair pass",
                        wave_index,
                        step_id,
                        missing_ids,
                    )
                    yield {
                        "type": "wave_repair",
                        "data": {
                            "agent_id": step_id,
                            "step": step_id,
                            "wave_index": wave_index,
                            "missing_task_ids": missing_ids,
                            "count": len(missing_ids),
                        },
                    }
                    repair_requests = [
                        {
                            "agent": "self",
                            "input": t.body,
                            "task_id": _key_by_id[t.id],
                            # The author id (s01…). task_id is a content HASH — correct for
                            # the resume cursor, unreadable in a UI. Display only.
                            "task_author_id": t.id,
                        }
                        for t in missing_tasks
                    ]
                    try:
                        async for event in _dispatch_wave(
                            repair_requests, missing_ids, wave_index
                        ):
                            yield event
                    except Exception as exc:  # noqa: BLE001 — repair stays non-fatal
                        logger.warning(
                            "wave_scheduler: repair pass for wave %s step=%s failed: %s",
                            wave_index,
                            step_id,
                            exc,
                        )

                    still_missing = [
                        t
                        for t in missing_tasks
                        if any(_target_missing(p) for p in t.targets)
                    ]
                    if still_missing:
                        still_missing_ids = [t.id for t in still_missing]
                        logger.warning(
                            "wave_scheduler: wave %s step=%s targets still missing "
                            "after repair: %s",
                            wave_index,
                            step_id,
                            still_missing_ids,
                        )
                        yield {
                            "type": "wave_repair",
                            "data": {
                                "agent_id": step_id,
                                "step": step_id,
                                "wave_index": wave_index,
                                "missing_task_ids": still_missing_ids,
                                "count": len(still_missing_ids),
                            },
                        }

        # Every wave reached a terminal status — the step is done. A wave that FAILED
        # re-raises above, so this is only reached on the all-completed path (the
        # engine's own error handling owns the failure event, exactly as for any
        # other strategy that raises).
        yield {
            "type": "agent_complete",
            "data": {
                "agent_id": step_id,
                "name": getattr(step, "name", None) or step_id,
                "duration": round(time.monotonic() - _t0, 2),
                "output_length": 0,
                "waves": len(waves),
                "tasks": len(tasks),
            },
        }
