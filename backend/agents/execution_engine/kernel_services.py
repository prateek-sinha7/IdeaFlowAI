"""agents/execution_engine/kernel_services.py — the D-03 ``KernelServices`` handle.

The concrete object ``execute()`` attaches as ``ctx.runner`` (07-04). It is the
SINGLE seam a capability (strategy / deliverable resolver / context provider)
reaches the kernel + ``app.*`` runtime primitives through — the run-one-agent
loop (``_run_agent`` wrapping ``create_deep_agent`` via the
``langchain_deepagents`` adapter, INV-13), the per-run ``RunSandbox``, the
``static_check`` / ``render_check`` validators, the typed-graph reads, the OD
template/example reads, the parent-run reads, and the sandbox-deliverable
helpers. Capabilities never import this module (the import-linter contract
forbids ``agents.capabilities -> agents.execution_engine``); they call its
attributes/methods dynamically off ``ctx.runner``.

This module IS the kernel, so it MAY import ``app.*`` + engine internals freely.
It delegates the heavy behavior to the engine's EXISTING ``_run_agent`` /
``_run_validation_fix_loop`` so the routed path is byte-identical + semantic-event
parity to the legacy per-task build loop / per-step dispatch (INV-3). The
strangler constraint (07-04): nothing here re-implements a leak — it wraps the
engine's existing primitives so the L1-L13 call SITES could be swapped to the
capabilities; the leak DEFINITIONS were then deleted in 07-05.

The handle is constructed once per run inside ``_execute_impl`` and carries the
per-run invocation context (the engine instance, the ordered AgentSpecs, the
sandbox, the run id, the planning context, the per-run ``ExecutionContext`` and
the static call args) so its ``run_agent`` can rebuild the exact positional call
the engine's ``_run_agent`` expects from the minimal ``(step, ctx)`` contract the
strategies call it with.
"""

from __future__ import annotations

import logging
from typing import Any, AsyncIterator

from app.agents.sandbox import (
    RunSandbox,
    count_sandbox_deliverables as _count_sandbox_deliverables,
    serialize_sandbox_deliverable as _serialize_sandbox_deliverable,
)
from app.agents.static_check import static_check as _static_check

logger = logging.getLogger("agents.execution_engine.kernel_services")


class KernelServices:
    """The concrete D-03 runner handle attached as ``ctx.runner`` by ``execute()``.

    Exposes exactly the surface the strategies / resolvers / context providers
    call against (the 07-01/07-02 contract):

      * ``run_agent(step, ctx, *, task_number, total_tasks, task_block)`` —
        async generator: run ONE (per-task) sub-agent, re-yielding the engine's
        event dicts. Delegates to the engine's ``_run_agent`` (which owns
        create_runner, the thread-id shape ``f"{run_id}:{spec.id}:{task_num}"``
        vs ``f"{run_id}:{spec.id}"``, the MODEL-02 fallback chain, the L10
        prototype.html readback, the L3 mid-stream PPT sanitize, and the typed
        dual-write) — so the routed path is byte/event identical (INV-3).
      * ``run_validation_fix_loop(...)`` — the Both-validation + bounded internal
        fix-loop, delegated to the engine's ``_run_validation_fix_loop`` (the fix
        sub-agent stream is consumed internally; nothing re-emitted). Byte-identical
        build / revision wording.
      * ``sandbox`` — the per-run RunSandbox (read/write/path_for/root).
      * ``static_check`` / ``render_check`` — the validators.
      * ``latest_typed_content(producer_step)`` — the typed-graph read.
      * ``od_context`` / ``cancel_event`` / ``run_id`` — run-scoped values.
      * ``template_example`` / ``template_injection_parts`` — the OD reads the
        opendesign provider composes from.
      * ``read_parent_file(parent_run_id, name)`` — the previous_run provider seed read.
      * ``count_sandbox_deliverables`` / ``serialize_sandbox_deliverable`` — the
        serialized_sandbox resolver helpers.
    """

    def __init__(
        self,
        *,
        engine: Any,
        ectx: Any,
        sandbox: RunSandbox,
        ordered_agents: list,
        user_message: str,
        pipeline_run_id: str,
        pipeline_type: str,
        planning_context: dict,
        attached_skills: list[dict] | None,
        attached_hooks: list[dict] | None,
        model_id: str | None,
        results: list[dict],
        cancel_event: Any,
    ) -> None:
        self._engine = engine
        self._ectx = ectx
        self.sandbox = sandbox
        self._ordered_agents = ordered_agents
        self._user_message = user_message
        self.run_id = pipeline_run_id
        self._pipeline_type = pipeline_type
        self._planning_context = planning_context
        self._attached_skills = attached_skills
        self._attached_hooks = attached_hooks
        self._model_id = model_id
        self._results = results
        self.cancel_event = cancel_event

    # ── Run-scoped passthroughs (attributes the capabilities read) ────────────
    @property
    def od_context(self) -> dict | None:
        return self._ectx.od_context

    # ── The run's user message (read/write) ────────────────────────────────────
    # The previous_run provider (07-10 / CR-06) reads this to extract the existing
    # artifact for an in-place revision and writes back the SLIMMED message (the
    # inlined artifact replaced by a pointer to the seeded file). ``run_agent``
    # reads ``self._user_message`` so a write here reaches the agent — and it is
    # mutated at run entry (during _seed_workflow_context), BEFORE the strategy loop
    # consumes it, so the agent receives the slimmed message exactly as the legacy
    # inline kernel block produced it (byte-identical).
    @property
    def user_message(self) -> str:
        return self._user_message

    @user_message.setter
    def user_message(self, value: str) -> None:
        self._user_message = value

    # ── Validators ────────────────────────────────────────────────────────────
    def static_check(self, html_path):
        return _static_check(html_path)

    async def render_check(self, html_path):
        from app.agents.render_check import render_check

        return await render_check(html_path)

    # ── Pre-edit revision baseline (revision_validation post-step, CR-06) ───────
    async def compute_revision_baseline(self, original_html: str):
        """Return ``(baseline_static, baseline_console)`` for the pre-edit ORIGINAL.

        Writes the seeded ORIGINAL to a temp file and runs static_check + (best-
        effort) render_check on it, normalizing via the engine's SINGLE-home
        ``_static_issue_sigs`` / ``_console_sigs`` helpers — so the post-step
        capability never imports the kernel (import-linter) yet reuses the exact
        signature logic the fix-loop uses. Byte-identical to the legacy inline
        baseline (same helpers, same render-unavailable degrade).
        """
        import tempfile
        from pathlib import Path

        from agents.execution_engine.engine import _console_sigs, _static_issue_sigs

        with tempfile.TemporaryDirectory() as _td:
            _orig_path = Path(_td) / "original.html"
            _orig_path.write_text(original_html, encoding="utf-8")
            _sres0 = _static_check(_orig_path)
            baseline_static = _static_issue_sigs(_sres0)
            try:
                from app.agents.render_check import render_check

                _rres0 = await render_check(_orig_path)
            except Exception as _render_exc:  # noqa: BLE001 — render unavailable ⇒ no baseline
                logger.warning(
                    "revision baseline render_check raised (%s) — treating as "
                    "unavailable (no console baseline)",
                    _render_exc,
                )
                from app.agents.render_check import RenderResult

                _rres0 = RenderResult(
                    ok=True, available=False,
                    note=f"render_check error: {_render_exc}",
                )
            baseline_console = _console_sigs(_rres0)
        return baseline_static, baseline_console

    # ── Gate-event audit write (08-02 / D-10) ──────────────────────────────────
    async def record_gate_event(
        self, step: str, gate: str, outcome: str, detail: Any = None
    ) -> str | None:
        """Write one owner/workspace-scoped ``gate_events`` row for a gate firing.

        Reached by the ``GateHandler`` impls via ``ctx.runner.record_gate_event``
        (NO kernel→app import on their side). Delegates to the per-run
        ``ScopedStore`` on the ExecutionContext so the row carries the run's
        ``(owner_id, workspace_id)`` (AUTHZ-01 / T-08-02-ID). Best-effort — a
        persist failure (offline harness / no FK row) degrades to ``None`` rather
        than aborting the gate evaluation (INV-3 parity: audit must never break the
        live stream).
        """
        store = getattr(self._ectx, "scoped_store", None)
        if store is None:
            return None
        try:
            return await store.record_gate_event(
                self.run_id, step, gate, outcome, detail
            )
        except Exception as exc:  # noqa: BLE001 — audit write must never abort a gate
            logger.warning(
                "record_gate_event(step=%s gate=%s outcome=%s) failed: %s",
                step, gate, outcome, exc,
            )
            return None

    # ── Typed-graph read (ART-03) ──────────────────────────────────────────────
    def latest_typed_content(self, producer_step: str) -> str | None:
        return self._engine._latest_typed_content(self._ectx, producer_step)

    # ── OD reads the opendesign provider composes from (Assumption A6) ─────────
    def template_example(self, template_id: str) -> str | None:
        return self._engine._load_template_example(template_id)

    def template_injection_parts(self, template_id: str) -> list[str]:
        if not template_id:
            return []
        try:
            from agents.execution_engine.od_context import get_template_injection_parts

            return list(get_template_injection_parts(template_id) or [])
        except Exception as exc:  # noqa: BLE001 — OD reads degrade, never abort
            logger.debug("template_injection_parts(%s) failed: %s", template_id, exc)
            return []

    # ── Parent-run seed read (previous_run provider) ───────────────────────────
    def read_parent_file(self, parent_run_id: str, name: str) -> str:
        parent_sb = RunSandbox(self._ectx.disk_principal, parent_run_id)
        return parent_sb.read(name)

    # ── Sandbox-deliverable helpers (serialized_sandbox resolver) ──────────────
    def count_sandbox_deliverables(self, root) -> int:
        return _count_sandbox_deliverables(root)

    def serialize_sandbox_deliverable(self, root) -> str:
        return _serialize_sandbox_deliverable(root)

    # ── The run-one-agent primitive (the L7 dispatch the strategy replaces) ────
    async def run_agent(
        self,
        step: Any,
        ctx: Any,
        *,
        task_number: int | None = None,
        total_tasks: int | None = None,
        task_block: str | None = None,
        skeleton: str | None = None,
    ) -> AsyncIterator[dict]:
        """Run ONE agent and re-yield its events (delegates to engine._run_agent).

        Rebuilds the engine's positional ``_run_agent`` call from the minimal
        ``(step, ctx)`` contract: looks up the AgentSpec for ``step.agent_id`` in
        the run's ordered agents, sets the build-loop scratch on the per-run
        ``ExecutionContext`` (so the engine's generic context injector emits the
        ``=== CURRENT TASK ===`` block — task_loop path), then re-yields every
        event ``_run_agent`` produces unchanged (INV-3). The scratch is reset
        afterwards so a single_shot step is byte-identical to today.

        WR-01 (07-09): ``skeleton`` carries the task-2+ CURRENT PROTOTYPE skeleton
        (the strategy sources it from the typed graph). It is threaded onto
        ``ectx.current_prototype_skeleton`` so the engine emits the legacy STANDALONE
        skeleton block (after the CURRENT TASK block); reset afterwards like the
        other build scratch. Task 1 passes ``None`` → no skeleton block.
        """
        spec = self._spec_for(step)
        index = self._index_for(spec)

        # Build-loop scratch (task_loop path): set the per-task counters + block so
        # the engine's generic context injector emits the CURRENT TASK marker exactly
        # as the legacy per-task build loop did. For single_shot (no task_number)
        # these stay "" — byte-identical to a non-build agent.
        prev_num = self._ectx.build_task_number
        prev_total = self._ectx.build_task_total
        prev_block = self._ectx.current_task_block
        prev_skeleton = getattr(self._ectx, "current_prototype_skeleton", "")
        if task_number is not None:
            self._ectx.build_task_number = str(task_number)
            self._ectx.build_task_total = str(total_tasks or task_number)
            self._ectx.current_task_block = task_block or ""
            self._ectx.current_prototype_skeleton = skeleton or ""
        try:
            async for event in self._engine._run_agent(
                spec,
                index,
                self._ordered_agents,
                self._user_message,
                self.sandbox,
                self.run_id,
                self._pipeline_type,
                self._planning_context,
                self._attached_skills,
                self._attached_hooks,
                self._model_id,
                self._results,
                self.cancel_event,
                self._ectx,
            ):
                yield event
        finally:
            # Reset the build scratch (only meaningful for the task_loop path).
            self._ectx.build_task_number = prev_num
            self._ectx.build_task_total = prev_total
            self._ectx.current_task_block = prev_block
            self._ectx.current_prototype_skeleton = prev_skeleton

    # ── The Both-validation + bounded internal fix-loop (L-build region C) ─────
    async def run_validation_fix_loop(
        self,
        step: Any,
        *,
        task_num: int,
        total_tasks: int,
        agent_id: str = "prototype-build",
        filename: str,
        baseline_static: "set[str] | None" = None,
        baseline_console: "set[str] | None" = None,
        user_instruction: str | None = None,
        label: str = "",
    ) -> None:
        """Run the Both-validation + bounded fix-loop (delegates to the engine).

        Builds the SAME per-agent ``AgentContext`` the legacy build loop built and
        calls the engine's ``_run_validation_fix_loop`` so the fix wording, the
        thread-id shape, the N=2 bound, and the consume-internally-emit-nothing
        contract are byte-identical (INV-3). The fix sub-agent edits the deliverable
        on disk as a side effect; nothing is re-emitted.

        07-11 / CR-05: ``filename`` is the DECLARED deliverable filename, threaded in
        from the strategy (``ctx.deliverable.name``) — REQUIRED (no ``prototype.html``
        default). The prototype manifest declares ``prototype.html`` so the value
        passed through keeps prototype validation byte-identical; a non-prototype
        task_loop workflow validates + fixes ITS OWN file.
        """
        from agents.factory import AgentContext

        spec = self._spec_for(step)
        ectx = self._ectx
        ctx = AgentContext(
            user_request=self._user_message,
            attached_skills=list(self._attached_skills or []),
            attached_hooks=list(self._attached_hooks or []),
            model=self._engine._resolve_model(ectx, spec, self._model_id),
            od_context=ectx.od_context,
            planning_context=self._planning_context,
            user_id=ectx.disk_principal,
            run_id=self.run_id,
        )
        await self._engine._run_validation_fix_loop(
            ctx=ctx,
            sandbox=self.sandbox,
            pipeline_run_id=self.run_id,
            task_num=task_num,
            total_tasks=total_tasks,
            cancel_event=self.cancel_event,
            agent_id=agent_id,
            filename=filename,
            baseline_static=baseline_static,
            baseline_console=baseline_console,
            user_instruction=user_instruction,
            label=label,
            checkpointer=ectx.checkpointer,
        )

    # ── Post-task typed dual-write (keeps _latest_typed_content current) ───────
    async def persist_task_html(
        self, task_num: int, agent_id: str = "prototype-build", *, filename: str
    ) -> None:
        """Typed-write the post-task deliverable as a new ref version (ART-03).

        Mirrors the legacy build loop's per-task dual-write so the NEXT task's
        prompt skeleton reads the most recent content via ``_latest_typed_content``.
        Best-effort; a missing file is a no-op.

        07-11 / CR-05: ``filename`` is the DECLARED deliverable filename threaded in
        from the strategy — REQUIRED (no ``prototype.html`` default). It keys BOTH
        the sandbox read AND the persisted artifact ``location`` so a non-prototype
        task_loop workflow dual-writes ITS OWN file (the prototype manifest declares
        ``prototype.html`` so the prototype dual-write is byte-identical).
        """
        task_html = self.sandbox.read(filename)
        if not task_html:
            return
        await self._engine._dual_write_artifact(
            self._ectx,
            producer_agent=agent_id,
            producer_step=agent_id,
            content=task_html,
            kind="html_file",
            location=filename,
            task_id=str(task_num),
        )

    # ── Internal: resolve the AgentSpec + its index for a compiled Step ───────
    def _spec_for(self, step: Any):
        agent_id = getattr(step, "agent_id", None)
        for s in self._ordered_agents:
            if s.id == agent_id:
                return s
        raise RuntimeError(
            f"KernelServices.run_agent: no AgentSpec for step agent_id={agent_id!r} "
            f"in ordered agents {[s.id for s in self._ordered_agents]}"
        )

    def _index_for(self, spec) -> int:
        for i, s in enumerate(self._ordered_agents):
            if s.id == spec.id:
                return i
        return 0
