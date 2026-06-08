"""agents/capabilities/strategies/task_loop.py — the ``task_loop`` strategy.

The prototype build backbone, lifted as a capability behind the
``ExecutionStrategy`` port. ``run`` owns the full per-task isolated-sub-agent
build loop the engine's ``_run_build_task_loop`` (engine.py:2072-2257),
``_write_build_reference_files`` (:2263-2316) and ``_run_validation_fix_loop``
(:2370-2549) implement today (INV-12 move-don't-copy):

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
  (5) after each task run Both-validation (``static_check`` + ``render_check``) via
      the handle and the bounded ``N=2`` INTERNAL fix-loop.

The pure fix-signature helpers ``_static_issue_sigs`` / ``_console_sigs`` /
``_select_issues_to_fix`` are lifted VERBATIM from engine.py:274-360 — the
byte-identical fix wording for build AND revision (do not rewrite).

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
  * ``run_fix_agent(fix_message, *, task_num, total_tasks, attempt, label="")``
      -> awaitable — re-invoke the SAME sub-agent on a distinct
      ``…:fix{n}`` thread, DRAIN its stream internally (apply edits as a side
      effect) and re-emit NOTHING.
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

_MAX_FIX_ATTEMPTS = 2


def _now() -> str:
    """ISO-ish timestamp for event payloads (mirrors the engine's ``_now``)."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ===========================================================================
# Pure fix-signature helpers — lifted VERBATIM from engine.py:274-360.
# The byte-identical fix-message wording for build AND revision. Do NOT rewrite.
# ===========================================================================


def _static_issue_sigs(sres) -> set[str]:
    """Signatures of a StaticCheckResult's fatal issues (for baseline diffing)."""
    return set(getattr(sres, "issues", None) or [])


def _console_sigs(rres) -> set[str]:
    """Signatures of a RenderResult's console errors (for baseline diffing)."""
    if not getattr(rres, "available", False):
        return set()
    return set(getattr(rres, "console_errors", None) or [])


def _select_issues_to_fix(
    sres,
    rres,
    baseline_static: "set[str] | None" = None,
    baseline_console: "set[str] | None" = None,
) -> list[str]:
    """Ordered, de-duplicated fix-list for the internal validation fix-loop.

    With empty baselines this is byte-identical to today's build ``error_lines``
    (all static issues, then console errors, then page errors, then dead nav
    links). With populated baselines (revision) only NEW static + NEW console
    issues are selected, while hard render-breakage is ALWAYS included. Lifted
    verbatim from ``engine.py``.
    """
    base_static = baseline_static or set()
    base_console = baseline_console or set()

    selected: list[str] = []

    # (1) Static regressions — issues not present on the baseline.
    for issue in getattr(sres, "issues", None) or []:
        if issue not in base_static:
            selected.append(issue)

    # Render contributes only when the headless render actually ran.
    if getattr(rres, "available", False):
        # (2) New console errors.
        for err in getattr(rres, "console_errors", None) or []:
            if err not in base_console:
                selected.append(f"console error: {err}")

        # (3) Hard render-breakage, ALWAYS included regardless of baseline.
        for err in getattr(rres, "page_errors", None) or []:
            selected.append(f"uncaught exception: {err}")

        for nav in getattr(rres, "nav_results", None) or []:
            if not getattr(nav, "ok", True):
                selected.append(
                    f"dead nav link: clicking '{nav.href}' activated no "
                    f"<section data-page>"
                )

    # De-duplicate while preserving first-seen order.
    seen: set[str] = set()
    deduped: list[str] = []
    for line in selected:
        if line not in seen:
            seen.add(line)
            deduped.append(line)
    return deduped


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

        # ── Source the planner's task plan from the typed graph (ART-03) ──────────
        plan_output = runner.latest_typed_content("prototype-plan") or ""

        # ── (A) Write the shared reference files to the sandbox ONCE ──────────────
        # seed_files behaviour rides here (manifests are {} — Pitfall 2).
        self._write_reference_files(runner)

        # Parse the tasks via the registry-resolved parser (D-02). The compiler
        # validates step.task_source.parser; default to "heading_tasks".
        parser_name = "heading_tasks"
        task_source_decl = getattr(step, "task_source", None)
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
            # The compaction capability is RESOLVED + APPLIED here by manifest name
            # (D-02): the strategy OWNS the per-task skeleton injection into the task
            # block (07-01 contract). The engine's generic injector keys the
            # CURRENT-TASK marker off ectx.current_task_block (= this task_block), so
            # the skeleton rides through to the prompt with NO double-injection (the
            # engine's own build-HTML block is gone on the routed path).
            if task_num >= 2 and compaction_name:
                compactor = self._maybe_resolve_compaction(compaction_name)
                if compactor is not None:
                    try:
                        prior_html = runner.sandbox.read("prototype.html") or ""
                        skeleton = compactor.compact(prior_html)
                        if skeleton:
                            current_task_block = (
                                f"{current_task_block}\n\n"
                                f"=== CURRENT PROTOTYPE SKELETON ===\n{skeleton}"
                            )
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
            async for event in runner.run_agent(
                step,
                ctx,
                task_number=task_num,
                total_tasks=total_tasks,
                task_block=current_task_block,
            ):
                yield event

            # Typed-write the post-task HTML (ART-03) so the NEXT task's prompt
            # skeleton reads the most recent document — mirrors the legacy build
            # loop's per-task dual-write (no event emitted; INV-3 parity).
            if hasattr(runner, "persist_task_html"):
                await runner.persist_task_html(task_num, agent_id=agent_id)

            # ── Both-validation + bounded internal fix-loop ──────────────────────
            # Routed through the handle (the engine's _run_validation_fix_loop) so
            # the fix wording / thread-id / N=2 bound / consume-internally contract
            # is byte-identical to the legacy build loop (INV-3). The handle owns the
            # AgentContext construction the loop needs.
            if cancel_event is not None and cancel_event.is_set():
                break
            if hasattr(runner, "run_validation_fix_loop"):
                await runner.run_validation_fix_loop(
                    step,
                    task_num=task_num,
                    total_tasks=total_tasks,
                    agent_id=agent_id,
                )
            else:  # pragma: no cover — fake handle without the validation method
                await self._run_validation_fix_loop(
                    runner,
                    task_num=task_num,
                    total_tasks=total_tasks,
                    cancel_event=cancel_event,
                    agent_id=agent_id,
                )

        logger.info("task_loop: finished %d tasks for pipeline=%s", total_tasks, run_id)

    # ------------------------------------------------------------------
    # Reference files (seed_files behaviour — lift of _write_build_reference_files)
    # ------------------------------------------------------------------

    def _write_reference_files(self, runner) -> None:
        """Write spec.md / design.md / tasks.md into the run sandbox (Region A).

        Lift of ``_write_build_reference_files`` (engine.py:2263-2316), reaching
        the typed-graph content + od_context + sandbox through the handle.
        """
        spec_text = runner.latest_typed_content("prototype-specify") or ""
        tasks_text = runner.latest_typed_content("prototype-plan") or ""
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

    # ------------------------------------------------------------------
    # Validation + bounded internal fix-loop (lift of _run_validation_fix_loop)
    # ------------------------------------------------------------------

    async def _run_validation_fix_loop(
        self,
        runner,
        *,
        task_num: int,
        total_tasks: int,
        cancel_event,
        agent_id: str = "prototype-build",
        max_attempts: int = _MAX_FIX_ATTEMPTS,
        baseline_static: "set[str] | None" = None,
        baseline_console: "set[str] | None" = None,
        user_instruction: str | None = None,
        label: str = "",
    ) -> None:
        """Both-validation + bounded INTERNAL fix-loop (Region C — build).

        Lift of ``_run_validation_fix_loop`` (engine.py:2370-2549) reaching
        static_check / render_check / the fix sub-agent through the handle. With
        empty baselines (the build default) the failing-decision reduces to
        EXACTLY today's ``(not sres.ok) or render_failed`` (INV-3). Never blocks.
        """
        html_path = runner.sandbox.path_for("prototype.html")
        if not html_path.is_file():
            logger.warning(
                "task_loop validation: task %d/%d wrote no prototype.html — skipping",
                task_num, total_tasks,
            )
            return

        attempt = 0
        while True:
            if cancel_event is not None and cancel_event.is_set():
                return

            sres = runner.static_check(html_path)
            try:
                rres = await runner.render_check(html_path)
            except Exception as exc:  # noqa: BLE001 — render harness must never crash the build
                logger.warning(
                    "task_loop validation: render_check raised (%s) — treating as skipped",
                    exc,
                )
                rres = _SkippedRender(note=f"render_check error: {exc}")

            render_skipped = not getattr(rres, "available", False)
            render_failed = getattr(rres, "available", False) and not getattr(rres, "ok", True)
            error_lines = _select_issues_to_fix(
                sres, rres, baseline_static, baseline_console
            )
            failing = bool(error_lines)

            logger.info(
                "task_loop validation: task %d/%d attempt %d — static=%s render=%s%s",
                task_num, total_tasks, attempt,
                sres.summary(), rres.summary(),
                " (render skipped)" if render_skipped else "",
            )

            if not failing:
                return

            if attempt >= max_attempts:
                if user_instruction is None:
                    residual: list[str] = list(getattr(sres, "issues", None) or [])
                    if render_failed:
                        residual.append(f"render: {rres.summary()}")
                        residual.extend(getattr(rres, "console_errors", None) or [])
                        residual.extend(getattr(rres, "page_errors", None) or [])
                        residual.extend(
                            f"dead nav link: {n.href} (no section activated)"
                            for n in (getattr(rres, "nav_results", None) or [])
                            if not getattr(n, "ok", True)
                        )
                else:
                    residual = list(error_lines)
                logger.warning(
                    "task_loop validation: task %d/%d still failing after %d fix "
                    "attempt(s) — continuing build. Residual issues: %s",
                    task_num, total_tasks, max_attempts, "; ".join(residual) or "(none)",
                )
                return

            attempt += 1
            if user_instruction is None:
                fix_message = (
                    f"=== VALIDATION ERRORS (fix prototype.html) ===\n"
                    f"The prototype you built for task {task_num} of {total_tasks} failed "
                    f"validation. Read the current prototype.html with "
                    f"read_file(file_path=\"prototype.html\") and apply MINIMAL "
                    f"edit_file(file_path=\"prototype.html\", ...) changes to fix ONLY "
                    f"the issues listed below. Do NOT rebuild the document, do NOT add "
                    f"new pages, do NOT touch anything unrelated to these errors. You "
                    f"may read_file(\"spec.md\") / read_file(\"design.md\") for reference.\n\n"
                    + "\n".join(f"- {e}" for e in error_lines)
                    + "\n=== END VALIDATION ERRORS ==="
                )
            else:
                fix_message = (
                    f"=== VALIDATION ERRORS (fix prototype.html) ===\n"
                    f"The user asked you to revise this prototype:\n"
                    f"\"{user_instruction}\"\n\n"
                    f"You revised this prototype to satisfy that request — keep that "
                    f"change intact. Now fix ONLY the issues listed below (they were "
                    f"introduced by your edit, or they stop the page rendering / "
                    f"displaying content); do not touch anything unrelated.\n\n"
                    f"Read the current prototype.html with "
                    f"read_file(file_path=\"prototype.html\") and apply MINIMAL "
                    f"edit_file(file_path=\"prototype.html\", ...) changes. Do NOT "
                    f"rebuild the document and do NOT undo the requested change. You "
                    f"may read_file(\"spec.md\") / read_file(\"design.md\") for the "
                    f"original requirements + design system if present.\n\n"
                    + "\n".join(f"- {e}" for e in error_lines)
                    + "\n=== END VALIDATION ERRORS ==="
                )

            logger.info(
                "task_loop validation: task %d/%d FAILING — internal fix attempt %d/%d (%d issue(s))",
                task_num, total_tasks, attempt, max_attempts, len(error_lines),
            )

            try:
                await runner.run_fix_agent(
                    fix_message,
                    task_num=task_num,
                    total_tasks=total_tasks,
                    attempt=attempt,
                    agent_id=agent_id,
                    label=label,
                )
            except Exception as exc:  # noqa: BLE001 — a fix failure must not abort the build
                logger.warning(
                    "task_loop validation: task %d/%d fix attempt %d errored (%s) — continuing",
                    task_num, total_tasks, attempt, exc,
                )
                return
            # Loop back to re-validate the (possibly) fixed prototype.html.


class _SkippedRender:
    """Minimal RenderResult stand-in for a render_check that raised (handle path).

    Mirrors the engine's ``RenderResult(ok=True, available=False, ...)`` fallback
    so ``_select_issues_to_fix`` treats it as "render unavailable" (a pass).
    """

    def __init__(self, note: str = "") -> None:
        self.ok = True
        self.available = False
        self.note = note
        self.console_errors: list[str] = []
        self.page_errors: list[str] = []
        self.nav_results: list = []

    def summary(self) -> str:
        return self.note or "render unavailable"
