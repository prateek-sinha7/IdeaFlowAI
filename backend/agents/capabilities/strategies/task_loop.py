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

from agents.capabilities import task_identity
from agents.capabilities.registry import CapabilityRegistry, register
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

# Legacy reference-file names (07-11 / CR-07). The reference files the build loop
# writes before the per-task loop. Honored positionally as (spec, design, tasks); the
# DECLARED ``seed_files`` overrides them when present (all authored manifests are ``{}``
# → this triple is used, byte-identical, Pitfall 2).
_SEED_FILES = ("spec.md", "design.md", "tasks.md")


def _declared_seed_files(ctx) -> tuple[str, str, str]:
    """Read the DECLARED reference-file names off ctx with the legacy fallback (CR-07).

    The compiled ``seed_files`` dict is threaded onto ``ctx.seed_files`` at run entry.
    Its ``from_run`` list (when present + holding 3 entries) names the (spec, design,
    tasks) reference files; otherwise fall back to ``_SEED_FILES``. INV-5: the manifest
    only DECLARES the list; this control flow lives in the strategy, never the compiler.
    """
    declared = getattr(ctx, "seed_files", None) or {}
    if isinstance(declared, dict):
        from_run = declared.get("from_run")
        if from_run and len(from_run) == 3:
            return (str(from_run[0]), str(from_run[1]), str(from_run[2]))
    return _SEED_FILES


def _now() -> str:
    """ISO-ish timestamp for event payloads (mirrors the engine's ``_now``)."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ===========================================================================
# The strategy
# ===========================================================================


@register(
    "strategy",
    "task_loop",
    user_allowed=True,
    description="Parse the step's deliverable into tasks and run one isolated sub-agent per task, with an optional bounded validation fix-loop.",
    config_schema={
        "type": "object",
        "properties": {
            "task_parser": {
                "type": "string",
                "description": "Capability name of the task_parser that splits the work into tasks.",
                "enum": ["heading_tasks", "json_tasks"],
                "default": "heading_tasks",
            },
            "max_fix_attempts": {
                "type": "integer",
                "description": "Bound on the per-task validation fix-loop (0 disables fixing).",
                "minimum": 0,
                "default": 2,
            },
        },
    },
)
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
        # seed_files behaviour rides here (manifests are {} — Pitfall 2). The
        # reference-file NAMES are read from the declared ``ctx.seed_files`` (CR-07).
        self._write_reference_files(runner, step, ctx)

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

        # ── RESUME-14: content-addressed per-task keys (computed ONCE after parse) ──
        # task_key = sha256(upstream_context_hash · normalized_content · occurrence_ordinal).
        # The upstream hash is PER-STEP (identical for every task) so it is fetched once
        # via the runner handle (the ONE engine home, INV-12); a fake/old handle lacking
        # it degrades to "" (keys still deterministic within the run). These keys stamp
        # the durable ``task_id`` slot (persist_task_html) AND drive the resume skip below,
        # replacing the raw position — reorder/insert/duplicate/upstream-rotate safe.
        _uhash_fn = getattr(runner, "upstream_context_hash", None)
        _upstream_hash = _uhash_fn(step) if callable(_uhash_fn) else ""
        if tasks:
            _ordinals = task_identity.occurrence_ordinals(tasks)
            _task_keys = [
                task_identity.compute_task_key(
                    _upstream_hash, task_identity.normalize_task_content(t), _ordinals[i]
                )
                for i, t in enumerate(tasks)
            ]
        else:
            # No tasks parsed → a single fallback pass; synthesize one key over the
            # empty task content (still a stable 64-char key, never a position).
            _task_keys = [task_identity.compute_task_key(_upstream_hash, "", 0)]

        # Resolve the task-2+ compaction by NAME (D-02). The html_skeleton impl
        # lands in a later plan; resolve-by-name now, skip the call when no impl
        # is bound (the call site routes through resolve regardless).
        compaction_name = getattr(step, "compaction", None)

        # ── RESUME-16 cumulative COMMON-PREFIX skip cursor (kernel-computed; 48-02) ──
        # On a durable resume the kernel stamps ``ctx.resume_completed_ordered`` with the
        # completed keys for THIS step in original build ORDER. Because each task EDITS the
        # same evolving file, a completed key is only safe to skip while it MATCHES the
        # current key at the SAME position: skip the longest common PREFIX ``p`` and re-run
        # everything at/after the first divergence — even a suffix task whose own key
        # matches a completed key (its predecessor changed → its basis changed, Pitfall 3).
        # ``p==0`` (first task edited/deleted, or a task inserted at head) ⇒ skip nothing,
        # run every current task from a clean basis (the kernel's boundary re-materialize
        # restores NOTHING — never a negative-index restore). Read via getattr → None on a
        # normal run ⇒ empty list ⇒ ``p==0`` ⇒ dispatch byte/event-identical (INV-3). The
        # kernel decides the skip — the agent never does (INV-1); waves use set-membership.
        _resume_ordered = getattr(ctx, "resume_completed_ordered", None)
        _completed_ordered: list[str] = []
        if _resume_ordered:
            _completed_ordered = _resume_ordered.get(agent_id, []) or []
        _prefix_skip = task_identity.common_prefix_length(_task_keys, _completed_ordered)

        for task_num in range(1, total_tasks + 1):
            if cancel_event is not None and cancel_event.is_set():
                logger.info("task_loop: cancelled at task %d", task_num)
                break

            # RESUME-16 cumulative: a task inside the unchanged common PREFIX is NOT
            # re-invoked (its deliverable is on disk from the kernel's boundary
            # re-materialization). Skip run_agent dispatch + persist + fix-loop for it.
            # Index-based on the ORDER-diff ``_prefix_skip`` (never set-membership — a
            # suffix task whose predecessor changed MUST re-run, Pitfall 3). Dormant on a
            # normal run (``_prefix_skip == 0`` ⇒ nothing skipped).
            if task_num - 1 < _prefix_skip:
                logger.info(
                    "task_loop: skipping already-completed task %d on resume "
                    "(common-prefix p=%d)", task_num, _prefix_skip
                )
                continue

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
            # ISS-132: each task iteration is an INVOCATION, not a step boundary.
            # Without this flag, _run_agent's inline gate predicate fires once per
            # task — a 5-task step opens 5 sequential gates. The step's own declared
            # gate (gates: [human]) is unaffected; it fires at the step boundary as
            # before. Same reasoning and same fix shape as ISS-097/FIX-242's
            # invocation_gated=False on run_worker and run_merge_agent.
            async for event in runner.run_agent(
                step,
                ctx,
                task_number=task_num,
                total_tasks=total_tasks,
                task_block=current_task_block,
                skeleton=task_skeleton,
                invocation_gated=False,
            ):
                yield event

            # Typed-write the post-task HTML (ART-03) so the NEXT task's prompt
            # skeleton reads the most recent document — mirrors the legacy build
            # loop's per-task dual-write (no event emitted; INV-3 parity).
            if hasattr(runner, "persist_task_html"):
                await runner.persist_task_html(
                    task_num,
                    agent_id=agent_id,
                    filename=filename,
                    task_key=_task_keys[task_num - 1],
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
            #
            # D-06 re-point: the loop is driven by a GENERIC FixPolicy (deliverable
            # name + max_attempts) — not the hardcoded ``prototype.html`` path. The
            # prototype manifest's deliverable is ``prototype.html`` so the value
            # passed through keeps the loop byte/event-identical (the 5 characterization
            # snapshots gate it); a non-prototype task_loop workflow fixes ITS file.
            if cancel_event is not None and cancel_event.is_set():
                break
            fix_policy = self._fix_policy(runner, step, filename)
            if fix_policy is not None:
                await runner.run_validation_fix_loop(
                    step,
                    task_num=task_num,
                    total_tasks=total_tasks,
                    agent_id=agent_id,
                    policy=fix_policy,
                )
            else:
                # Handle lacks the FixPolicy factory (an old unit fake) — fall back
                # to the bare ``filename=`` call (the loop wraps a default policy;
                # byte-identical).
                await runner.run_validation_fix_loop(
                    step,
                    task_num=task_num,
                    total_tasks=total_tasks,
                    agent_id=agent_id,
                    filename=filename,
                )

            # D-06: run the step's DECLARED registered validators against the
            # post-fix deliverable so each task persists ``validation_results`` rows
            # (VALID-04 / D-10) reached via the registry + the KernelServices handle
            # (NO kernel→app import). This is ADDITIVE + EVENT-FREE — the validators
            # only write audit rows; no event is emitted — so the 5 characterization
            # snapshots stay byte/event-identical. Prototype declares
            # ``html_static``/``html_render``; a workflow declaring none is a no-op.
            await self._run_registered_validators(
                runner, step, filename, task_num=task_num, total_tasks=total_tasks
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
                        task_num,
                        agent_id=agent_id,
                        filename=filename,
                        task_key=_task_keys[task_num - 1],
                    )

        logger.info("task_loop: finished %d tasks for pipeline=%s", total_tasks, run_id)

    # ------------------------------------------------------------------
    # D-06 — generic FixPolicy + registered-validator run (additive, event-free)
    # ------------------------------------------------------------------

    def _fix_policy(self, runner, step, filename: str):
        """Build the generic ``FixPolicy`` for this step via the handle (D-06).

        The deliverable name + the attempt bound drive the fix-loop (NOT a hardcoded
        ``prototype.html``). ``max_attempts`` is read from the DECLARED ``step.fix``
        (a ``FixPolicy`` manifest field) when present + positive, else the Phase-7
        default of 2 — so the prototype path stays byte-identical (its manifest
        declares no ``fix``). The policy object is constructed KERNEL-side through
        ``runner.make_fix_policy`` because the strategy must not import the kernel
        (import-linter); when the handle lacks the factory (an old unit fake) fall
        back to a bare ``filename=`` call by returning ``None`` (the loop then wraps
        a default policy — byte-identical).
        """
        fix_decl = getattr(step, "fix", None)
        declared = getattr(fix_decl, "max_attempts", 0) or 0
        max_attempts = declared if declared > 0 else 2
        make = getattr(runner, "make_fix_policy", None)
        if make is None:
            return None
        return make(filename, max_attempts=max_attempts)

    async def _run_registered_validators(
        self, runner, step, filename: str, *, task_num: int, total_tasks: int
    ) -> None:
        """Run the step's DECLARED registered validators (additive, event-free; D-06).

        Resolves each ``step.validators`` name from the registry and calls
        ``.validate(target)`` against a ``DeliverableContext`` built by the handle
        (``runner.deliverable_context``) — so the validators reach the heavy checks +
        write their ``validation_results`` rows through ``target.runner`` (NO
        kernel→app import). EVENT-FREE: the validators only persist audit rows; no
        event is yielded — so the 5 characterization snapshots stay byte/event-
        identical. A workflow declaring no validators (or a handle lacking the
        factory, an old unit fake) is a no-op. Best-effort: a validator raising must
        never abort the build (INV-3 parity — the audit run mirrors the legacy loop's
        non-blocking contract).
        """
        validator_names = list(getattr(step, "validators", None) or [])
        if not validator_names:
            return
        make_target = getattr(runner, "deliverable_context", None)
        if make_target is None:
            return
        agent_id = getattr(step, "agent_id", "") or ""
        # Thread the per-step render fail-closed knob (quick-260701-bob) onto the
        # target so html_render sees the declared policy. A handle whose factory
        # predates the kwarg (an old unit fake) is retried without it (parity).
        target_kwargs = {
            "name": filename,
            "step": agent_id,
            "task_meta": {"attempt": task_num, "total_tasks": total_tasks},
            "require_render": getattr(step, "require_render", None),
        }
        try:
            target = make_target(**target_kwargs)
        except TypeError:
            target_kwargs.pop("require_render", None)
            target = make_target(**target_kwargs)
        for vname in validator_names:
            try:
                validator = self._registry.resolve("validator", vname)
                await validator.validate(target)
            except Exception as exc:  # noqa: BLE001 — an audit validator never aborts the build
                logger.warning(
                    "task_loop: registered validator %r raised (%s) — continuing",
                    vname, exc,
                )

    # ------------------------------------------------------------------
    # Reference files (seed_files behaviour — lift of _write_build_reference_files)
    # ------------------------------------------------------------------

    def _write_reference_files(self, runner, step, ctx) -> None:
        """Write the (spec, design, tasks) reference files into the run sandbox (Region A).

        Lift of ``_write_build_reference_files`` (engine.py:2263-2316), reaching
        the typed-graph content + od_context + sandbox through the handle.

        07-11 / CR-05: the spec/tasks producer step ids are read from the DECLARED
        ``step.task_source.source_step``/``spec_step`` (the strategy owns the legacy
        fallback — INV-5), NOT the hardcoded ``"prototype-specify"``/``"prototype-plan"``
        literals.

        07-11 / CR-07: the reference-file NAMES are read from the DECLARED
        ``ctx.seed_files`` (``_declared_seed_files`` → (spec, design, tasks)) with the
        legacy ``_SEED_FILES`` triple as fallback — NOT the hardcoded
        ``spec.md``/``design.md``/``tasks.md`` literals. All authored manifests are ``{}``
        so the fallback fires → byte-identical (Pitfall 2).
        """
        task_source_decl = getattr(step, "task_source", None)
        spec_step = (
            getattr(task_source_decl, "spec_step", None) or _DEFAULT_SPEC_STEP
        )
        source_step = (
            getattr(task_source_decl, "source_step", None) or _DEFAULT_SOURCE_STEP
        )
        spec_name, design_name, tasks_name = _declared_seed_files(ctx)
        spec_text = runner.latest_typed_content(spec_step) or ""
        tasks_text = runner.latest_typed_content(source_step) or ""
        od = getattr(runner, "od_context", None) or {}
        template_body = od.get("template_body") or ""
        ds_body = od.get("ds_body") or ""

        try:
            if spec_text:
                runner.sandbox.write(spec_name, spec_text)
            if tasks_text:
                runner.sandbox.write(tasks_name, tasks_text)

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
                runner.sandbox.write(design_name, "\n\n".join(design_sections))
            # KAN-103: seed the template's reference HTML as a separate workspace file
            # so the revision agent can read_file("template.html") directly — clean
            # tool call, no bloat in design.md. This is the authoritative CSS class/
            # component reference the agent should use when making visual edits.
            # Best-effort: silently skipped when no example.html exists for the template.
            #
            # ISS-068: read the example through the ``template_example`` PORT on the D-03
            # handle, never by importing od_context directly — a capability importing
            # agents.execution_engine (which itself imports app.services.od_loader) breaks
            # the "agents.capabilities must not import the execution kernel or the web
            # layer" import-linter contract. The port is the same bytes and the same
            # EXAMPLE_MAX_CHARS cap (KernelServices.template_example → engine.
            # _load_template_example → od_context.get_example_html). The ``hasattr`` guard
            # mirrors the context_providers/opendesign.py consumer, because the unit-test
            # fakes set only a bare ``ctx.runner``.
            _tid = od.get("template_id", "") or ""
            if _tid and hasattr(runner, "template_example"):
                try:
                    _example = runner.template_example(_tid)
                    if _example:
                        runner.sandbox.write("template.html", _example)
                        logger.info(
                            "task_loop: seeded template.html for revision reference "
                            "(%d chars, template=%s)",
                            len(_example), _tid,
                        )
                except Exception as _te:  # noqa: BLE001
                    logger.debug("task_loop: could not seed template.html (%s): %s", _tid, _te)

            logger.info(
                "task_loop: wrote reference files (%s=%s, %s=%s, %s=%s)",
                spec_name, bool(spec_text), design_name, bool(design_sections),
                tasks_name, bool(tasks_text),
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

