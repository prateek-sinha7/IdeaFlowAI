"""agents/capabilities/strategies/task_loop.py — the ``task_loop`` strategy.

The prototype build backbone, lifted as a capability behind the
``ExecutionStrategy`` port. ``run`` owns the full per-task isolated-sub-agent
build loop the engine's ``_run_build_task_loop`` (engine.py:2072-2257) and
``_write_build_reference_files`` (:2263-2316) implement today (INV-12
move-don't-copy). The Both-validation + bounded ``N=2`` fix-loop is NOT
re-implemented here — it has a SINGLE home in the engine's
``_run_validation_fix_loop``, reached only through ``runner.run_validation_fix_loop``
(INV-3/INV-12 no dual implementations):

  (1) write spec.md / design.md / tasks.md into the run sandbox ONCE before the
      loop — the ``seed_files`` behaviour rides HERE (all manifests are
      ``seed_files: {}``, parity-trap Pitfall 2);
  (2) parse the planner's tasks via the registry-resolved task parser
      (``step.task_source.parser`` -> ``heading_tasks``);
  (3) per task, invoke the run-one-agent primitive through ``ctx.runner`` with the
      ``## Task N:`` block + task counters held as STRATEGY-LOCAL scratch
      (reclaimed off ``ExecutionContext`` per D-03 — NO ``self._...`` engine state,
      L14 ratchet / Pitfall 6), re-yielding its events;
  (4) on task-2+ apply the registry-resolved compaction (``step.compaction`` ->
      ``html_skeleton``; the impl lands in a later plan — the call site routes
      through ``resolve`` now and is skipped when no impl is bound);
  (5) after each task run Both-validation (``static_check`` + ``render_check``) +
      the bounded ``N=2`` INTERNAL fix-loop by delegating UNCONDITIONALLY to
      ``runner.run_validation_fix_loop`` (the engine's single implementation) —
      this strategy holds NO fix-loop / fix-selection code of its own.

INV-3 (WS parity): ``run`` yields the SAME ``{"type", "data"}`` dicts the engine
build loop yields today (``task_loop_progress`` + the per-task ``run_agent``
events). The internal fix sub-agent stream is consumed but NEVER re-emitted — the
UI shows exactly ONE build per task.

Import purity (import-linter / INV-13): NOTHING from ``agents.execution_engine``
or ``app.*`` is imported and no deep-agent graph is constructed here. The agent
loop, sandbox, validators and deliverable helpers are reached ONLY through the
object-typed ``ctx.runner`` handle.

──────────────────────────────────────────────────────────────────────────────
The ``ctx.runner`` contract this strategy calls against
(the D-03 ``KernelServices`` handle attached to ``ExecutionContext.runner`` by
``execute()`` in 07-04 — defined here as the SHAPE the strategy depends on; the
concrete class lives under the kernel and is NEVER imported here):

  * ``run_agent(step, ctx, *, task_number=None, total_tasks=None, task_block=None)``
      -> ``AsyncIterator[dict]`` — run ONE per-task sub-agent, yielding the
      engine's event dicts. The handle owns create_runner, the per-task thread-id
      shape ``f"{run_id}:{spec.id}:{task_num}"`` (vs ``f"{run_id}:{spec.id}"`` for
      the engine path), the MODEL-02 fallback chain and the post-task
      prototype.html readback / typed dual-write.
  * ``run_validation_fix_loop(step, *, task_num, total_tasks, agent_id=…)``
      -> awaitable — the Both-validation + bounded ``N=2`` INTERNAL fix-loop. The
      handle owns the fix sub-agent invocation (on a distinct ``…:fix{n}`` thread),
      DRAINS its stream internally (applies edits as a side effect) and re-emits
      NOTHING. The strategy NEVER calls the fix sub-agent itself.
  * ``sandbox`` — the per-run RunSandbox: ``read(name)`` / ``write(name, text)`` /
      ``path_for(name)`` / ``root``.
  * ``static_check(html_path)`` -> StaticCheckResult (sync).
  * ``render_check(html_path)`` -> awaitable RenderResult.
  * ``latest_typed_content(producer_step)`` -> ``str | None`` — the typed-graph
      read the seed-files write + task count source from (ART-03).
  * ``od_context`` -> ``dict | None`` — the loaded template / design-system blocks
      the design.md seed composes from.
  * ``cancel_event`` -> the cooperative cancel signal (``.is_set()``) or ``None``.
  * ``run_id`` -> the pipeline run id (for logging / progress payloads).
──────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import logging
import time
from typing import Any, AsyncIterator

from agents.capabilities.registry import CapabilityRegistry
from agents.capabilities.task_parsers.heading_tasks import _count_plan_tasks

logger = logging.getLogger(__name__)

# Default deliverable filename when the run declares none (parity fallback — the
# prototype manifest declares ``deliverable.name: prototype.html``, so the prototype
# path passes this value THROUGH and stays byte-identical). Mirrors single_file.py:32.
_DEFAULT_DELIVERABLE_NAME = "prototype.html"

# Legacy producer-step fallbacks (07-11 / CR-05). The prototype manifest now DECLARES
# ``task_source.source_step``/``spec_step``; these are the fallbacks the STRATEGY (not
# the kernel/compiler — INV-5) applies when a manifest omits them, so a manifest that
# forgets the declaration still resolves the prototype producers.
_DEFAULT_SOURCE_STEP = "prototype-plan"      # task-plan producer
_DEFAULT_SPEC_STEP = "prototype-specify"     # spec producer


def _now() -> str:
    """ISO-ish timestamp for event payloads (mirrors the engine's ``_now``)."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ===========================================================================
# The strategy
# ===========================================================================


class TaskLoopStrategy:
    """The prototype per-task sub-agent build loop (``name='task_loop'``).

    Satisfies the ``ExecutionStrategy`` port structurally (``name`` + ``run``).
    All per-task scratch (``current_task_block`` / task counters) is STRATEGY-LOCAL
    (D-03) — never written back onto the engine or ``ctx``.
    """

    name = "task_loop"

    def __init__(self) -> None:
        # Module-level singleton registry (capabilities are stateless) — used to
        # resolve the task parser + the task-2+ compaction by NAME (D-02).
        self._registry = CapabilityRegistry()

    async def run(self, step: Any, ctx: Any) -> AsyncIterator[dict]:
        """Drive the per-task build loop, yielding the engine's event dicts.

        ``ctx`` is typed ``Any``; the kernel/app primitives are reached only via
        ``ctx.runner`` (the D-03 handle).
        """
        runner = ctx.runner
        cancel_event = getattr(runner, "cancel_event", None)
        run_id = getattr(runner, "run_id", "")
        agent_id = getattr(step, "agent_id", "prototype-build")

        # ── De-hardcode the deliverable filename (07-11 / CR-05) ──────────────────
        # Read the deliverable filename from the DECLARED ``ctx.deliverable.name``
        # (the single_file.py:43 pattern) — NOT the hardcoded ``prototype.html``. The
        # prototype manifest declares ``deliverable.name: prototype.html`` so the
        # value passed THROUGH is byte-identical; a non-prototype task_loop workflow
        # names its own file (e.g. ``app.py``). Falls back to the prototype default
        # only when no deliverable is bound (e.g. the unit-test fakes that set only
        # ``ctx.runner``) so those stay parity-stable.
        deliverable = getattr(ctx, "deliverable", None)
        filename = getattr(deliverable, "name", None) or _DEFAULT_DELIVERABLE_NAME

        # ── De-hardcode the upstream producer step ids (07-11 / CR-05) ────────────
        # Read the task-plan + spec producer step ids from the DECLARED
        # ``step.task_source.source_step``/``spec_step`` — NOT the hardcoded
        # ``"prototype-plan"``/``"prototype-specify"`` literals. The strategy owns the
        # legacy fallback (INV-5: the compiler stays thin — it only carries the
        # declaration, it does not default it to a prototype id).
        task_source_decl = getattr(step, "task_source", None)
        source_step = (
            getattr(task_source_decl, "source_step", None) or _DEFAULT_SOURCE_STEP
        )

        # ── Source the planner's task plan from the typed graph (ART-03) ──────────
        plan_output = runner.latest_typed_content(source_step) or ""

        # ── (A) Write the shared reference files to the sandbox ONCE ──────────────
        # seed_files behaviour rides here (manifests are {} — Pitfall 2).
        self._write_reference_files(runner, step)

        # Parse the tasks via the registry-resolved parser (D-02). The compiler
        # validates step.task_source.parser; default to "heading_tasks".
        parser_name = "heading_tasks"
        if task_source_decl is not None and getattr(task_source_decl, "parser", None):
            parser_name = task_source_decl.parser
        parser = self._registry.resolve("task_parser", parser_name)
        tasks = parser.parse(plan_output)

        # A count of 0 means the planner did NOT emit a task plan — run one
        # fallback pass with an empty task block (byte-identical to the engine).
        total_tasks = len(tasks)
        if total_tasks == 0:
            _, _src = _count_plan_tasks(plan_output)
            logger.warning(
                "task_loop: no tasks found in plan output (%d chars) — running once",
                len(plan_output),
            )
            total_tasks = 1
            task_blocks = [""]
        else:
            task_blocks = [t.body for t in tasks]

        logger.info("task_loop: %d tasks for pipeline=%s", total_tasks, run_id)

        # Resolve the task-2+ compaction by NAME (D-02). The html_skeleton impl
        # lands in a later plan; resolve-by-name now, skip the call when no impl
        # is bound (the call site routes through resolve regardless).
        compaction_name = getattr(step, "compaction", None)

        for task_num in range(1, total_tasks + 1):
            if cancel_event is not None and cancel_event.is_set():
                logger.info("task_loop: cancelled at task %d", task_num)
                break

            # STRATEGY-LOCAL scratch (D-03) — the current task block + counters.
            current_task_block = task_blocks[task_num - 1]

            # ── task-2+ compaction (D-02 route) ──────────────────────────────────
            # WR-01 (07-09): the compaction capability is RESOLVED + APPLIED here by
            # manifest name (D-02). The strategy sources the prior HTML from the TYPED
            # GRAPH (runner.latest_typed_content("prototype-build")) — NOT a raw,
            # unconditional disk read — and applies the legacy `[Error:` suppression
            # (legacy read the typed graph then gated `current_html and not
            # current_html.startswith("[Error:")`). The resulting skeleton is threaded
            # onto ectx.current_prototype_skeleton (via the run_agent skeleton param) so
            # the engine emits the legacy STANDALONE `=== CURRENT PROTOTYPE (skeleton —
            # call read_file('prototype.html') ...) ===` block AFTER the CURRENT TASK
            # block (byte-exact position/wrapper) — NOT nested into current_task_block.
            task_skeleton: str | None = None
            if task_num >= 2 and compaction_name:
                compactor = self._maybe_resolve_compaction(compaction_name)
                if compactor is not None:
                    try:
                        prior_html = runner.latest_typed_content(agent_id) or ""
                        if prior_html and not prior_html.startswith("[Error:"):
                            skel = compactor.compact(prior_html)
                            if skel:
                                task_skeleton = skel
                    except Exception as exc:  # noqa: BLE001 — compaction must not abort the build
                        logger.warning("task_loop: compaction failed (%s) — continuing", exc)

            # Emit loop progress so the frontend knows which task is running.
            yield {
                "type": "task_loop_progress",
                "data": {
                    "agent_id": agent_id,
                    "pipeline_run_id": run_id,
                    "task_number": task_num,
                    "total_tasks": total_tasks,
                    "timestamp": _now(),
                },
            }

            # Run the per-task sub-agent through the handle, re-yielding its events.
            # WR-01: pass the task-2+ skeleton via the dedicated param (not nested in
            # the task block) so the engine emits the legacy standalone skeleton block.
            async for event in runner.run_agent(
                step,
                ctx,
                task_number=task_num,
                total_tasks=total_tasks,
                task_block=current_task_block,
                skeleton=task_skeleton,
            ):
                yield event

            # Typed-write the post-task HTML (ART-03) so the NEXT task's prompt
            # skeleton reads the most recent document — mirrors the legacy build
            # loop's per-task dual-write (no event emitted; INV-3 parity).
            if hasattr(runner, "persist_task_html"):
                await runner.persist_task_html(
                    task_num, agent_id=agent_id, filename=filename
                )

            # WR-05 (07-09): snapshot the on-disk deliverable BEFORE the fix-loop so we
            # can detect whether the fix-loop edited it (the legacy build loop re-wrote
            # the typed artifact when `fixed_html != task_html`). Keyed on the DECLARED
            # deliverable filename (07-11 / CR-05), NOT a hardcoded ``prototype.html``.
            pre_fix_html = ""
            try:
                pre_fix_html = runner.sandbox.read(filename) or ""
            except Exception:  # noqa: BLE001 — a read failure must not abort the build
                pre_fix_html = ""

            # ── Both-validation + bounded internal fix-loop ──────────────────────
            # Routed through the handle (the engine's _run_validation_fix_loop) so
            # the fix wording / thread-id / N=2 bound / consume-internally contract
            # is byte-identical to the legacy build loop (INV-3). The handle owns the
            # AgentContext construction the loop needs.
            if cancel_event is not None and cancel_event.is_set():
                break
            await runner.run_validation_fix_loop(
                step,
                task_num=task_num,
                total_tasks=total_tasks,
                agent_id=agent_id,
                filename=filename,
            )

            # WR-05 (07-09): the fix-loop edits prototype.html on disk as a side effect
            # but does NOT touch the typed graph. The consumer (prototype-validate) reads
            # the TYPED graph, so if the fix changed the HTML we must RE-PERSIST the typed
            # build artifact — otherwise prototype-validate sees the PRE-fix HTML (the
            # legacy build loop re-wrote the artifact when `fixed_html != task_html`).
            if hasattr(runner, "persist_task_html"):
                try:
                    post_fix_html = runner.sandbox.read(filename) or ""
                except Exception:  # noqa: BLE001 — read failure must not abort the build
                    post_fix_html = ""
                if post_fix_html and post_fix_html != pre_fix_html:
                    await runner.persist_task_html(
                        task_num, agent_id=agent_id, filename=filename
                    )

        logger.info("task_loop: finished %d tasks for pipeline=%s", total_tasks, run_id)

    # ------------------------------------------------------------------
    # Reference files (seed_files behaviour — lift of _write_build_reference_files)
    # ------------------------------------------------------------------

    def _write_reference_files(self, runner, step) -> None:
        """Write spec.md / design.md / tasks.md into the run sandbox (Region A).

        Lift of ``_write_build_reference_files`` (engine.py:2263-2316), reaching
        the typed-graph content + od_context + sandbox through the handle.

        07-11 / CR-05: the spec/tasks producer step ids are read from the DECLARED
        ``step.task_source.source_step``/``spec_step`` (the strategy owns the legacy
        fallback — INV-5), NOT the hardcoded ``"prototype-specify"``/``"prototype-plan"``
        literals.
        """
        task_source_decl = getattr(step, "task_source", None)
        spec_step = (
            getattr(task_source_decl, "spec_step", None) or _DEFAULT_SPEC_STEP
        )
        source_step = (
            getattr(task_source_decl, "source_step", None) or _DEFAULT_SOURCE_STEP
        )
        spec_text = runner.latest_typed_content(spec_step) or ""
        tasks_text = runner.latest_typed_content(source_step) or ""
        od = getattr(runner, "od_context", None) or {}
        template_body = od.get("template_body") or ""
        ds_body = od.get("ds_body") or ""

        try:
            if spec_text:
                runner.sandbox.write("spec.md", spec_text)
            if tasks_text:
                runner.sandbox.write("tasks.md", tasks_text)

            design_sections: list[str] = []
            if template_body:
                template_id = od.get("template_id", "") or ""
                hdr = f"# ACTIVE TEMPLATE{f' ({template_id})' if template_id else ''}"
                design_sections.append(f"{hdr}\n\n{template_body}")
            if ds_body:
                ds_id = od.get("ds_id", "") or ""
                hdr = f"# ACTIVE DESIGN SYSTEM{f' ({ds_id})' if ds_id else ''}"
                design_sections.append(f"{hdr}\n\n{ds_body}")
            if design_sections:
                runner.sandbox.write("design.md", "\n\n".join(design_sections))

            logger.info(
                "task_loop: wrote reference files (spec.md=%s, design.md=%s, tasks.md=%s)",
                bool(spec_text), bool(design_sections), bool(tasks_text),
            )
        except Exception as exc:  # noqa: BLE001 — never let a write failure abort the build
            logger.warning("task_loop: failed writing reference files: %s", exc)

    # ------------------------------------------------------------------
    # Compaction resolution (D-02 route, impl lands later)
    # ------------------------------------------------------------------

    def _maybe_resolve_compaction(self, name: str):
        """Resolve a compaction impl by name, or ``None`` if not yet bound.

        Routes through ``registry.resolve`` (D-02). The ``html_skeleton`` impl
        lands in a later plan; until then ``resolve`` raises RuntimeError for the
        known-but-unbound name and this returns ``None`` (the call site skips
        compaction — parity-safe).
        """
        try:
            return self._registry.resolve("compaction", name)
        except (KeyError, RuntimeError):
            return None

