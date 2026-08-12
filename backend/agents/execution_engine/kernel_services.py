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

import hashlib
import logging
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, AsyncIterator
from uuid import uuid4 as _uuid4

from app.agents.sandbox import (
    RunSandbox,
    _DELIVERABLE_EXCLUDE,
    _collect_deliverable_relpaths,
    count_sandbox_deliverables as _count_sandbox_deliverables,
    serialize_sandbox_deliverable as _serialize_sandbox_deliverable,
)
from app.agents.static_check import static_check as _static_check

logger = logging.getLogger("agents.execution_engine.kernel_services")


# ---------------------------------------------------------------------------
# DeliverableContext (D-04) — the kernel-pure target a Validator receives.
#
# A registered ``Validator`` (``html_static`` / ``html_render`` / Tier#4/5/6) is
# called as ``await validator.validate(target)`` where ``target`` carries:
#   * ``path``    — the on-disk deliverable path (``runner.sandbox.path_for(name)``);
#   * ``content`` — the deliverable text (lazily read from disk when omitted);
#   * ``runner``  — the KernelServices handle, so the validator reaches the heavy
#                   checks (``runner.static_check`` / ``runner.render_check``) and
#                   the ScopedStore writer (``runner.record_validation_result``)
#                   WITHOUT importing the kernel/app (D-04 — the import-linter
#                   forbids only ``agents.capabilities -> agents.execution_engine``;
#                   reaching the handle dynamically off ``target.runner`` is legal);
#   * ``name``    — the declared deliverable filename;
#   * ``step``    — the step/agent id being validated (the validation_results row key);
#   * ``task_meta`` — per-task metadata (task number / total / attempt) the loop threads.
#
# It lives kernel-side (this module IS the kernel) and is typed so capabilities
# receive a stable shape; the capabilities NEVER import it (they read attributes off
# the ``Any``-typed target).
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# FixPolicy (D-06 / VALID-01/02) — the GENERIC, config-driven fix-loop policy.
#
# The Both-validation + bounded fix-loop is no longer hardcoded to
# ``prototype.html``: it drives off this policy carrying the deliverable name, the
# max attempt bound, and the failure policy (default warn-non-critical /
# block-critical). Running the loop with ``deliverable="app.py"`` operates on
# ``app.py``; the prototype manifest's policy names ``prototype.html`` so the
# prototype path stays byte-identical. The default policy reproduces Phase-7's exact
# behavior (max_attempts=2, the engine's verbatim BUILD/REVISION fix-prompt wording).
# ---------------------------------------------------------------------------


@dataclass
class FixPolicy:
    """The generic fix-loop policy (deliverable name + max_attempts + failure mode).

    ``block_critical`` / ``warn_non_critical`` document the default policy the
    validation gate (08-02) enforces: a CRITICAL issue blocks, residual non-critical
    issues warn. The internal fix-loop continues to ``max_attempts`` then emits a
    residual warning — it never blocks the build (INV-3 parity).
    """

    deliverable: str
    max_attempts: int = 2
    block_critical: bool = True
    warn_non_critical: bool = True


@dataclass
class DeliverableContext:
    """The kernel-pure validation target passed to a registered ``Validator`` (D-04)."""

    name: str
    runner: Any
    path: Any = None
    _content: str | None = None
    step: str = ""
    task_meta: dict = field(default_factory=dict)
    # Per-step render fail-closed knob (quick-260701-bob / REQUIRE-RENDER-KNOB):
    # threaded from the compiled ``Step.require_render`` so html_render sees the
    # per-step policy. None → the validator falls back to the Settings default.
    require_render: bool | None = None

    @property
    def content(self) -> str:
        """The deliverable text — lazily read from ``path`` when not provided."""
        if self._content is not None:
            return self._content
        try:
            if self.path is not None:
                from pathlib import Path

                p = Path(self.path)
                if p.is_file():
                    self._content = p.read_text(encoding="utf-8")
                    return self._content
        except OSError as exc:  # noqa: BLE001 — a read failure degrades to empty content
            logger.debug("DeliverableContext.content read failed (%s)", exc)
        return self._content or ""


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
        allowed_workers: list[str] | None = None,
        aux_usage_sink: Any = None,
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
        # ISS-033-A: the run's aux token-usage sink (``aux_token_usage.append``), bound
        # per-run at construction rather than stashed on the engine singleton (INV-2).
        # The validation fix-loop's sub-agent spend is routed here so it reaches the
        # pipeline_complete totals. None ⇒ the loop counts nothing (direct unit-style
        # invocations), which is exactly today's behavior.
        self._aux_usage_sink = aux_usage_sink
        # The exec-granted Workspace bound by 10-02's host seam (the §15 wiring):
        # validators reach exec via ``target.runner.workspace.exec_command(argv)``.
        # Declared here so the attribute always exists; stays None until an
        # exec-granted plan provisions a workspace in 10-02 (parity: dormant for
        # every existing non-exec run).
        self.workspace = None
        # Phase 11 / FANOUT-03 (CR-01): the compiled workflow-level named-worker
        # allow-list, bound onto the LIVE handle so the kernel ``run_fanout``
        # worker selection (``_select_workers``) reads the REAL declaration —
        # not an attribute that only test fakes fabricate. Threaded from
        # ``compiled.allowed_workers`` at handle construction in ``_execute_impl``.
        self.allowed_workers = list(allowed_workers or [])

    # ── Run-scoped passthroughs (attributes the capabilities read) ────────────
    @property
    def od_context(self) -> dict | None:
        return self._ectx.od_context

    # ── Run terminality (ISS-091) ─────────────────────────────────────────────
    def is_run_terminal(self) -> bool:
        """True once the run has reached a terminal state.

        The fan-out cancel boundary (``fanout._check_cancel``) reads this in
        addition to ``cancel_event``, because a run driven terminal by anything
        OTHER than the Stop button — a review-gate rejection — sets no
        ``cancel_event`` at all. No run is ever ``failed`` while fan-out is in
        flight (both transitions live outside the step loop), so a True here
        always means the run genuinely ended.
        """
        return self._engine._state_machine.get_state(self.run_id) in (
            "cancelled",
            "failed",
        )

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

    # ── Validation-result audit write (08-04 / D-10) ───────────────────────────
    async def record_validation_result(
        self,
        step: str,
        validator: str,
        *,
        severity: str | None = None,
        attempt: int = 0,
        issues: Any = None,
    ) -> str | None:
        """Write one owner/workspace-scoped ``validation_results`` row (08-04).

        Reached by the registered ``Validator`` impls via
        ``target.runner.record_validation_result`` (NO kernel→app import on their
        side). Delegates to the per-run ``ScopedStore`` on the ExecutionContext so
        the row carries the run's ``(owner_id, workspace_id)`` (AUTHZ-01 /
        T-08-04-ID). Best-effort — a persist failure (offline harness / no FK row)
        degrades to ``None`` rather than aborting the validator (INV-3 parity: the
        audit write must never break the live stream).
        """
        store = getattr(self._ectx, "scoped_store", None)
        if store is None:
            return None
        try:
            return await store.record_validation_result(
                self.run_id,
                step,
                validator,
                severity=severity,
                attempt=attempt,
                issues=issues,
            )
        except Exception as exc:  # noqa: BLE001 — audit write must never abort a validator
            logger.warning(
                "record_validation_result(step=%s validator=%s) failed: %s",
                step, validator, exc,
            )
            return None

    # ── Hook-firing audit write (08-07 / HOOK-04 / D-10) ───────────────────────
    async def record_hook_run(
        self, hook: str, event: str, outcome: str, detail: Any = None
    ) -> str | None:
        """Write one owner/workspace-scoped ``hook_runs`` row for a hook firing.

        Reached by the executable ``HookHandler`` impls via
        ``ctx.runner.record_hook_run`` (NO kernel→app import on their side).
        Delegates to the per-run ``ScopedStore`` on the ExecutionContext so the row
        carries the run's ``(owner_id, workspace_id)`` (AUTHZ-01 / T-08-07-ID2).
        ``outcome`` ∈ ``continue | warn | block``. Best-effort — a persist failure
        (offline harness / no FK row) degrades to ``None`` rather than aborting the
        hook firing (INV-3 parity: audit must never break the live stream).
        """
        store = getattr(self._ectx, "scoped_store", None)
        if store is None:
            return None
        try:
            return await store.record_hook_run(
                self.run_id, hook, event, outcome, detail
            )
        except Exception as exc:  # noqa: BLE001 — audit write must never abort a hook
            logger.warning(
                "record_hook_run(hook=%s event=%s outcome=%s) failed: %s",
                hook, event, outcome, exc,
            )
            return None

    # ── Hook real-time WS event emit (KAN-73) ───────────────────────────────────
    def emit_hook_event(self, detail: Any) -> None:
        """Enqueue a ``hook_run`` WS event for the running agent (KAN-73).

        Called synchronously by executable hooks so the live Audit tab updates in
        real-time as each agent executes. The event is pushed into the execution
        context's event queue (if present) for the websocket stream. Best-effort —
        a missing queue or enqueue failure never aborts a hook or the run.
        """
        queue = getattr(self._ectx, "event_queue", None)
        if queue is None:
            return
        try:
            queue.put_nowait({
                "type": "hook_run",
                "data": dict(detail) if detail else {},
            })
        except Exception:  # noqa: BLE001 — emit must never abort a hook
            pass

    # ── Exec-invocation audit write (10 / EXEC-01 / T-10-01-07) ────────────────
    async def record_exec_run(
        self,
        step: str,
        argv: Any,
        outcome: str,
        *,
        exit_code: int | None = None,
        duration_ms: int | None = None,
        policy_snapshot: Any = None,
        output_digest: str | None = None,
    ) -> str | None:
        """Write one owner/workspace-scoped ``exec_runs`` row for an exec outcome.

        Reached by the workspace recorder callback wired in 10-02's host seam, so
        EVERY ``exec_command`` outcome (allowed / denied / killed) is audited at the
        enforcement point — bypass-proof regardless of caller (T-10-01-07).
        Delegates to the per-run ``ScopedStore`` so the row carries the run's
        ``(owner_id, workspace_id)`` (AUTHZ-01 / T-10-01-08). ``outcome`` ∈
        ``allowed | denied | killed``. Best-effort — a persist failure (offline
        harness / no FK row) degrades to ``None`` rather than aborting the exec or
        the run (Pitfall 6 / INV-3 parity: audit must never break the live stream).
        """
        store = getattr(self._ectx, "scoped_store", None)
        if store is None:
            return None
        try:
            return await store.record_exec_run(
                self.run_id,
                step,
                argv,
                outcome,
                exit_code=exit_code,
                duration_ms=duration_ms,
                policy_snapshot=policy_snapshot,
                output_digest=output_digest,
            )
        except Exception as exc:  # noqa: BLE001 — audit must NEVER abort the run
            logger.warning(
                "record_exec_run(step=%s outcome=%s) failed: %s",
                step, outcome, exc,
            )
            return None

    # ── Fan-out child audit writer (Phase 11 / FANOUT-10) ──────────────────────
    async def record_subagent_run(
        self,
        *,
        parent_step: str,
        worker_agent: str,
        depth: int,
        isolation: str,
        status: str,
        tokens: int | None = None,
        cost: Any = None,
        worker_index: int | None = None,
        task_id: str | None = None,
    ) -> str | None:
        """Write one owner/workspace-scoped ``subagent_runs`` row for a fan-out child.

        Reached by the single kernel ``run_fanout`` spawn path, so EVERY child is
        audited at the one spawn point (FANOUT-10). Delegates to the per-run
        ``ScopedStore`` so the row carries the run's ``(owner_id, workspace_id)``
        (AUTHZ-01 / T-11-01-03). Best-effort — a persist failure (offline harness / no
        FK row) degrades to ``None`` rather than aborting the spawn or the run (Pitfall
        6 — audit must never break the live stream). Clones ``record_exec_run`` EXACTLY.
        """
        store = getattr(self._ectx, "scoped_store", None)
        if store is None:
            return None
        try:
            return await store.record_subagent_run(
                self.run_id,
                parent_step=parent_step,
                worker_agent=worker_agent,
                depth=depth,
                isolation=isolation,
                status=status,
                tokens=tokens,
                cost=cost,
                worker_index=worker_index,
                task_id=task_id,
            )
        except Exception as exc:  # noqa: BLE001 — audit must NEVER abort the run
            logger.warning(
                "record_subagent_run(step=%s worker=%s) failed: %s",
                parent_step, worker_agent, exc,
            )
            return None

    async def update_subagent_run(
        self,
        row_id: str,
        *,
        status: str,
        tokens: int | None = None,
        cost: Any = None,
    ) -> None:
        """Flip a ``subagent_runs`` row terminal (best-effort; never aborts the run)."""
        store = getattr(self._ectx, "scoped_store", None)
        if store is None or row_id is None:
            return
        try:
            await store.update_subagent_run(row_id, status=status, tokens=tokens, cost=cost)
        except Exception as exc:  # noqa: BLE001 — audit must NEVER abort the run
            logger.warning("update_subagent_run(row=%s) failed: %s", row_id, exc)

    # ── Per-wave audit writer (Phase 12 / WAVE-02) ─────────────────────────────
    async def record_wave_run(
        self,
        *,
        step: str,
        wave_index: int,
        task_ids: Any,
        status: str,
    ) -> str | None:
        """Write one owner/workspace-scoped ``wave_runs`` row for an executed wave.

        Reached by the ``wave_scheduler`` strategy before each wave's ``run_fanout``,
        so EVERY executed wave is audited (WAVE-02). Delegates to the per-run
        ``ScopedStore`` so the row carries the run's ``(owner_id, workspace_id)``
        (AUTHZ-01 / T-12-01-IDOR). Best-effort — a persist failure (offline harness /
        no FK row) degrades to ``None`` rather than aborting the wave or the run
        (Pitfall 6 — audit must never break the live stream). Clones
        ``record_subagent_run`` EXACTLY.
        """
        store = getattr(self._ectx, "scoped_store", None)
        if store is None:
            return None
        try:
            return await store.record_wave_run(
                self.run_id,
                step=step,
                wave_index=wave_index,
                task_ids=task_ids,
                status=status,
            )
        except Exception as exc:  # noqa: BLE001 — audit must NEVER abort the run
            logger.warning(
                "record_wave_run(step=%s wave=%s) failed: %s",
                step, wave_index, exc,
            )
            return None

    async def update_wave_run(self, row_id: str | None, *, status: str) -> None:
        """Flip a ``wave_runs`` row terminal (best-effort; never aborts the run)."""
        store = getattr(self._ectx, "scoped_store", None)
        if store is None or row_id is None:
            return
        try:
            await store.update_wave_run(row_id, status=status)
        except Exception as exc:  # noqa: BLE001 — audit must NEVER abort the run
            logger.warning("update_wave_run(row=%s) failed: %s", row_id, exc)

    async def read_wave_runs(self) -> list[Any]:
        """Return the run's owner/workspace-scoped ``wave_runs`` rows (wave_index asc).

        The 12-03 MID-WAVE resume read: the ``wave_scheduler`` strategy consults the
        durable wave rows (via this handle — never importing the store) to skip waves
        already driven to a terminal status before a restart (WAVE-03). Best-effort —
        a ``None`` store (offline harness) or a read error degrades to ``[]`` (no
        durable state ⇒ re-run, the read-path precedent). Owner-scoped: a cross-owner
        read returns nothing (T-12-01-IDOR, enforced in ``ScopedStore.read_wave_runs``).
        """
        store = getattr(self._ectx, "scoped_store", None)
        if store is None:
            return []
        try:
            return await store.read_wave_runs(self.run_id)
        except Exception as exc:  # noqa: BLE001 — a resume read must never abort the run
            logger.warning("read_wave_runs failed: %s", exc)
            return []

    async def read_subagent_runs(self) -> list[Any]:
        """Return the run's owner/workspace-scoped ``subagent_runs`` rows (created asc).

        The 12-03 MID-WAVE resume read: within the in-flight wave, the strategy skips
        the workers that already reached a terminal ``subagent_runs`` status before the
        restart (their fragments were persisted pre-merge in Phase 11) and re-fans-out
        only the incomplete ones. Best-effort / owner-scoped, mirroring
        ``read_wave_runs`` (offline / cross-owner ⇒ ``[]``).
        """
        store = getattr(self._ectx, "scoped_store", None)
        if store is None:
            return []
        try:
            return await store.read_subagent_runs(self.run_id)
        except Exception as exc:  # noqa: BLE001 — a resume read must never abort the run
            logger.warning("read_subagent_runs failed: %s", exc)
            return []

    async def workspace_budget_spent(self) -> dict:
        """Return the workspace's already-spent fan-out budget aggregate (OBS-01).

        The per-workspace ceiling read (T-11-04-01): ``run_fanout`` calls this BEFORE a
        reserve when the run's BudgetManager carries a configured ``workspace_ceiling``,
        so the reserve can refuse a spawn once the workspace aggregate is exhausted.
        Delegates to the per-run ``ScopedStore.workspace_budget_spent`` so the aggregate
        is owner+workspace-scoped (a cross-owner workspace's spend is never counted,
        T-11-04-04). Best-effort: no store / a read failure degrades to zeros so the
        offline path is untouched (the read-path precedent). Returns
        ``{"subagents": <int>, "tokens": <int>}``.
        """
        store = getattr(self._ectx, "scoped_store", None)
        if store is None:
            return {"subagents": 0, "tokens": 0}
        try:
            return await store.workspace_budget_spent(
                getattr(self._ectx, "workspace_id", None)
            )
        except Exception as exc:  # noqa: BLE001 — a ceiling read must never abort the run
            logger.warning("workspace_budget_spent read failed: %s", exc)
            return {"subagents": 0, "tokens": 0}

    async def persist_budget_snapshot(self, snapshot: Any) -> None:
        """Persist a ``BudgetSnapshot`` to ``workflow_runs.budget_snapshot_json`` (OBS-01).

        Called at the engine's run-termination boundaries (completion / abort / cancel).
        Clones the ``record_exec_run`` None-degrade pattern EXACTLY: ``store is None →
        return``; wrapped in try/except → ``logger.warning``; the snapshot write must
        NEVER abort the run (audit must never break the live stream, Pitfall 6 / INV-3).
        Serializes the dataclass snapshot into a plain dict for the JSON column.
        """
        store = getattr(self._ectx, "scoped_store", None)
        if store is None:
            return
        payload = {
            "tokens": getattr(snapshot, "tokens", 0),
            "cost": getattr(snapshot, "cost", None),
            "subagents": getattr(snapshot, "subagents", 0),
            "depth": getattr(snapshot, "depth", 0),
            "wall_clock_seconds": getattr(snapshot, "wall_clock_seconds", 0.0),
        }
        try:
            await store.persist_budget_snapshot(self.run_id, payload)
        except Exception as exc:  # noqa: BLE001 — snapshot persist must NEVER abort the run
            logger.warning("persist_budget_snapshot failed: %s", exc)

    # ── Isolated-workspace alloc/reclaim handle (Phase 11 / FANOUT-05) ─────────
    async def allocate_isolated_workspace(
        self, scope: str, step: str, *, worker_index: int
    ) -> Any:
        """Allocate a per-worker isolated ``Workspace`` for ``scope`` (FANOUT-05).

        The capability/engine-facing seam to the ``LocalWorkspace`` git owner: the
        kernel ``run_fanout`` reaches the Task-1 ``allocate_sub_sandbox`` /
        ``allocate_worktree`` THROUGH this handle (never importing the app-side impl).
        ``scope`` is engine-selected upstream (``worktree`` for a repo run, else
        ``sub_sandbox``) — this method only delegates to the matching allocator on the
        run's bound ``workspace``. Returns ``None`` when no base workspace is bound
        (offline harness / non-exec run) so the caller degrades to shared_read.
        """
        base = self.workspace
        if base is None:
            return None
        if scope == "worktree":
            allocator = getattr(base, "allocate_worktree", None)
        elif scope == "sub_sandbox":
            allocator = getattr(base, "allocate_sub_sandbox", None)
        else:
            allocator = None
        if allocator is None:
            return None
        # The Task-1 allocators are synchronous (the git subprocess / mkdir run inline
        # on the single git owner); wrap the call so the async seam is uniform.
        return allocator(step, worker_index)

    def git_3way_merge(self, branch: str, base_commit: str) -> dict:
        """3-way merge a worker ``branch`` into the base via the git owner (11-03 / FANOUT-07).

        The capability-facing seam the ``git_3way`` MergeStrategy reaches git through:
        the strategy NEVER shells git (Pitfall 2 / Phase-9 D-10) — it calls THIS handle,
        which delegates to the base ``LocalWorkspace.merge_worktree`` (the single
        git-subprocess owner). Returns the merge_worktree result dict
        (``{"conflicts": [...], "snippet": ...}``). When no base workspace is bound
        (offline harness) returns a clean empty result so the merge degrades gracefully.
        """
        base = self.workspace
        merge_fn = getattr(base, "merge_worktree", None) if base is not None else None
        if merge_fn is None:
            return {"conflicts": [], "snippet": ""}
        return merge_fn(branch, base_commit)

    async def reclaim_isolated_workspace(self, base_workspace: Any, worker_ws: Any) -> None:
        """Reclaim a per-worker isolated workspace (worktree remove / child rmtree).

        A ``worktree`` workspace is removed via the base workspace's ``remove_worktree``
        (the single git owner — git worktree remove + branch delete); a ``sub_sandbox``
        child is removed via its own ``teardown`` (child-dir rmtree). Detected by the
        ``_worktree_branch`` stamp the Task-1 ``allocate_worktree`` sets. Best-effort —
        a teardown failure must never abort the run (the kernel ``run_fanout`` already
        wraps this, but the discrimination lives here next to the alloc).
        """
        if worker_ws is None:
            return
        if getattr(worker_ws, "_worktree_branch", None) is not None:
            base = base_workspace if base_workspace is not None else self.workspace
            remove = getattr(base, "remove_worktree", None) if base is not None else None
            if remove is not None:
                remove(worker_ws)
        else:
            teardown = getattr(worker_ws, "teardown", None)
            if teardown is not None:
                teardown()

    async def teardown_isolated_workspace(self, base_workspace: Any, worker_ws: Any) -> None:
        """Tear down ONE allocated isolated workspace on the cancel/finally path (11-05).

        The cancel-path teardown entry point the kernel ``run_fanout`` ``finally`` block
        calls for EVERY allocated isolated workspace — on a happy completion, a
        mid-flight cancel, OR a BudgetExceeded abort (Pitfall 5 / RESUME-01: no leaked
        worktrees/branches/sub_sandbox dirs after cancel). Delegates to the SINGLE
        reclaim discriminator (``reclaim_isolated_workspace``): a ``worktree`` ->
        ``LocalWorkspace.remove_worktree`` (git worktree remove + branch delete), a
        ``sub_sandbox`` -> the child's ``teardown`` (rmtree). Best-effort — a teardown
        failure is logged, never aborts the run (the caller also wraps it).
        """
        await self.reclaim_isolated_workspace(base_workspace, worker_ws)

    # ── Typed fragment-artifact persistence (Phase 11 / FANOUT-06) ─────────────
    async def write_fragment_artifact(
        self,
        *,
        producer_step: str,
        worker_agent: str,
        worker_index: int,
        content: str,
        location: str,
        kind: str = "file_bundle",
    ) -> str | None:
        """Persist ONE worker's output as a typed lineage-tracked fragment artifact.

        The artifact-ref source 11-01 deferred (FANOUT-06): each fan-out worker's output
        is persisted as a typed ``ArtifactRef`` (producer step/agent + parent-run linkage)
        BEFORE the merge, so partial results survive an abort/cancel (11-04/11-05 consume
        these refs). Delegates to the engine's SINGLE artifact write path
        (``_dual_write_artifact`` — typed graph + best-effort scoped DB row) so the
        fragment carries the run's ``(owner_id, workspace_id)`` and a ``content_hash``.
        Returns the typed ref id (the structured summary carries it), or ``None`` when no
        engine/graph is reachable (offline harness) so the caller degrades gracefully.

        This is the SINGLE producer of fragment artifacts (INV-12 — one consumer per
        capability); 11-04/11-05 CONSUME these refs, they do not re-introduce them.
        """
        engine = self._engine
        ectx = self._ectx
        if engine is None or ectx is None:
            return None
        graph = getattr(ectx, "artifacts", None)
        try:
            await engine._dual_write_artifact(
                ectx,
                producer_agent=worker_agent,
                producer_step=producer_step,
                content=content,
                kind=kind,
                location=location,
                task_id=str(worker_index),
                visibility="workspace",
            )
        except Exception as exc:  # noqa: BLE001 — fragment persist must never abort the merge
            logger.warning(
                "write_fragment_artifact(step=%s worker=%s idx=%s) failed: %s",
                producer_step, worker_agent, worker_index, exc,
            )
            return None
        # Return the id of the just-written ref (the latest of its kind for this run).
        if graph is None:
            return None
        try:
            refs = [
                r for r in graph.tree(self.run_id)
                if r.producer_step == producer_step and r.task_id == str(worker_index)
            ]
            return refs[-1].id if refs else None
        except Exception:  # noqa: BLE001 — best-effort id readback
            return None

    # ── merge_conflict artifact write (Phase 11 / FANOUT-08) ───────────────────
    async def write_merge_conflict_artifact(
        self, *, producer_step: str, conflicts: list, payload: Any = None
    ) -> str | None:
        """Write an owner-scoped ``merge_conflict`` artifact for a reported conflict.

        The conflict payload is what a human adjudicates (the ``human_gate`` policy) —
        it carries the conflicting relative paths + per-path worker provenance +
        TRUNCATED hunks (NO raw secret, Phase-10 D-04). Uses the already-allowed
        ``merge_conflict`` artifact kind. Delegates to the engine's single artifact
        write path so the row is owner/workspace-scoped (cross-owner read = ∅,
        T-11-03-02). Returns the typed ref id or ``None`` (offline degrade).
        """
        engine = self._engine
        ectx = self._ectx
        if engine is None or ectx is None:
            return None
        import json as _json

        body = _json.dumps(
            payload if payload is not None else {"conflicts": conflicts},
            default=str, sort_keys=True,
        )
        graph = getattr(ectx, "artifacts", None)
        try:
            await engine._dual_write_artifact(
                ectx,
                producer_agent=producer_step,
                producer_step=producer_step,
                content=body,
                kind="merge_conflict",
                location=f"merge_conflict/{producer_step}.json",
                visibility="private",  # owner-scoped: a conflict is not workspace-shared
            )
        except Exception as exc:  # noqa: BLE001 — audit must never abort the conflict flow
            logger.warning(
                "write_merge_conflict_artifact(step=%s) failed: %s", producer_step, exc
            )
            return None
        if graph is None:
            return None
        try:
            refs = [
                r for r in graph.tree(self.run_id) if r.kind == "merge_conflict"
            ]
            return refs[-1].id if refs else None
        except Exception:  # noqa: BLE001
            return None

    # ── Merge-strategy resolver handle (Phase 11 / FANOUT-07) ──────────────────
    def resolve_merge_strategy(self, name: str) -> Any:
        """Resolve a registered ``MergeStrategy`` by name (the engine-facing seam).

        The kernel ``run_fanout`` reaches the merge layer THROUGH this handle so it does
        not depend on the registry import order; returns ``None`` when the strategy is
        unresolved (offline / not discovered) so the merge degrades to a clean no-op.
        """
        try:
            from agents.capabilities.registry import CapabilityRegistry, discover

            discover()
            return CapabilityRegistry().resolve("merge", name)
        except Exception as exc:  # noqa: BLE001 — unresolved ⇒ clean no-op merge
            logger.debug("resolve_merge_strategy(%s) failed: %s", name, exc)
            return None

    # ── Bounded merge-agent invocation (Phase 11 / FANOUT-08 / §13 / CR-03) ───
    async def run_merge_agent(
        self, merge_worker: str, payload: Any, *, attempt: int = 1
    ) -> bool:
        """Run the designated merge-agent worker ONCE over a conflict payload.

        The live handle behind the ``on_conflict: merge_agent`` policy: the kernel
        ``_run_merge_agent`` calls this ≤ ``MERGE_AGENT_MAX_ATTEMPTS`` times then
        falls back to human_gate (the caller owns the bound — Pitfall 8). One call
        = ONE bounded ``run_agent`` invocation of the designated worker, with the
        serialized conflict payload threaded as its CURRENT TASK block so the
        worker sees the conflicting paths/hunks it must resolve in the base
        workspace. Returns ``True`` when the worker run completed without raising
        (the attempt is counted resolved; the merged base is what downstream
        consumes), ``False`` on any failure — including an unknown worker id —
        so the caller counts the attempt and ultimately falls back to the ONE
        durable human_gate. Events are consumed internally (lifecycle-only fan-out
        stream discipline, D-03).
        """
        import json as _json

        try:
            step_view = SimpleNamespace(
                agent_id=merge_worker,
                strategy="single_shot",
                gates=[],
                hooks=[],
                task_source=None,
                post_step=None,
                tools=None,
                fanout=None,
                isolated_workspace=None,
            )
            conflict_block = _json.dumps(payload, default=str, sort_keys=True)
            async for _event in self.run_agent(
                step_view,
                self._ectx,
                task_number=attempt,
                total_tasks=attempt,
                task_block=(
                    "Resolve the following fan-out merge conflict in the "
                    f"workspace (attempt {attempt}):\n{conflict_block}"
                ),
            ):
                pass  # consumed internally — the conflict flow re-emits its own events
            return True
        except Exception as exc:  # noqa: BLE001 — a failed attempt counts, never aborts
            logger.warning(
                "run_merge_agent(worker=%s attempt=%s) failed: %s",
                merge_worker, attempt, exc,
            )
            return False

    # ── Named-worker registry existence check (Phase 11 / FANOUT-03 / CR-01) ──
    def agent_exists(self, agent_id: str) -> bool:
        """True when ``agent_id`` resolves as a runnable fan-out worker (FANOUT-03).

        The registry-existence half of the named-worker pre-spawn guard: the
        kernel ``_select_workers`` calls this THROUGH the handle (never importing
        the agent registry directly — layering). A worker is runnable when it is
        one of the run's ordered AgentSpecs (the ``run_agent`` spec lookup will
        resolve it) or, failing that, when the agent loader knows it by id.
        Fail-closed: an unknown/unloadable id returns ``False`` so ``run_fanout``
        rejects it BEFORE any spawn.
        """
        if any(s.id == agent_id for s in self._ordered_agents):
            return True
        try:
            from agents.loader import load_agent_spec

            load_agent_spec(agent_id)
            return True
        except Exception:  # noqa: BLE001 — unknown/unloadable ⇒ not a runnable worker
            return False

    # ── Fan-out spawn handle (Phase 11 / FANOUT-02) ────────────────────────────
    async def run_fanout(
        self, requests: list, ctx: Any, *, step: Any
    ) -> AsyncIterator[dict]:
        """Re-yield the kernel ``run_fanout`` spawn-path events (FANOUT-02).

        The capability-facing seam: the ``fanout_batch`` strategy + the engine
        tool-result derivation both call THIS handle method, which delegates to the
        kernel-private ``run_fanout`` coroutine (the only spawn path). Lifecycle-only
        events (``subagent_spawned`` / ``subagent_result``) flow back through the
        engine's single emit boundary.
        """
        from agents.execution_engine.fanout import run_fanout as _kernel_run_fanout

        async for event in _kernel_run_fanout(requests, ctx, step=step):
            yield event

    async def run_worker(
        self,
        step: Any,
        ctx: Any,
        *,
        worker_index: int,
        thread_id: str,
        agent_id: str,
        input: str,
        workspace: Any = None,
        total_workers: int | None = None,
    ) -> AsyncIterator[dict]:
        """Run ONE fan-out worker against its allocated isolated workspace (FANOUT-04/05).

        Wraps ``run_agent`` to run a single worker for the resolved ``agent_id`` with
        the per-worker ``thread_id``. Workers carry NO gates + NO per-worker fix-loop
        (D-01 — the kernel orchestrates the fan-out itself; the worker is a plain agent
        run). Re-yields the ``_run_agent`` events; the caller (``run_fanout``) consumes
        them lifecycle-only (it does NOT forward child chunk events — D-03).

        ``workspace`` is the engine-allocated isolated workspace (11-02 / FANOUT-05):
        the worker's writes land in it so two parallel workers cannot cross-contaminate
        before the 11-03 merge. It is bound onto the worker step view (the run-one-agent
        primitive reads it when present); ``None`` keeps the 11-01 shared-workspace
        behavior byte-identical for the non-isolated / offline path.
        """
        # A worker runs the resolved worker agent. When the worker IS the step's own
        # agent (self×N) the step is reused as-is; for a NAMED worker we run that
        # agent via a lightweight step view carrying its agent_id (the spec lookup in
        # run_agent resolves it from the run's ordered agents). The allocated isolated
        # workspace is bound on the (always-fresh) worker step view so the per-worker
        # write isolation rides the step without mutating the shared parent step.
        if getattr(step, "agent_id", None) == agent_id and workspace is None:
            worker_step = step
        else:
            worker_step = SimpleNamespace(
                agent_id=agent_id,
                # WR-05: a worker IS a plain single agent run — the parent's
                # fanout_batch strategy name would be misleading metadata on the
                # worker view (and a nested consumer keying on it would re-fan).
                strategy="single_shot",
                gates=[],
                hooks=[],
                task_source=None,
                post_step=None,
                tools=getattr(step, "tools", None),
                fanout=None,
                isolated_workspace=workspace,
            )

        # FANOUT-04: thread the worker's per-worker input through the existing CURRENT
        # TASK injection path so the worker sees ITS assigned slice (not just the shared
        # context every sibling sees). The worker IS a per-task agent (one per fanned
        # task), so it carries a 1-based task_number derived from its worker_index — the
        # engine's generic context injector then emits the ``=== CURRENT TASK ===`` block
        # carrying ``input`` (INV-1: agnostic — keyed on the build scratch, never a
        # workflow name). A non-fanout single_shot step never routes through run_worker,
        # so its byte/event parity is untouched (INV-3).
        # WR-05: total_tasks is the WAVE WIDTH (threaded from run_fanout, which
        # knows len(selected)) — not worker_index+1, which showed every worker but
        # the last a wrong "task i of N" in its CURRENT TASK header.
        async for event in self.run_agent(
            worker_step,
            ctx,
            task_number=worker_index + 1,
            total_tasks=total_workers or (worker_index + 1),
            task_block=input,
        ):
            yield event

    # ── Hook firing passthrough (08-07 / HOOK-01..04 / D-09) ───────────────────
    async def fire_hooks(
        self, event_name: str, step: Any, *, payload: str = ""
    ) -> str:
        """Fire the executable hooks bound to ``event_name`` (delegates to the engine).

        The SINGLE seam a runner write/tool-call event (``before_write``) or a
        task-loop per-task boundary (``post_task``) reaches the engine's hook
        dispatch through — WITHOUT importing the kernel (the caller is the
        kernel-side runner / strategy reaching it off ``ctx.runner``). Returns the
        aggregate outcome (``block`` iff any bound hook blocked — the caller halts
        the offending write/action ADDITIVELY; else ``continue``). ``payload`` is
        the write content scanned by ``secret_scan`` on a ``before_write`` firing.

        A ``before_write`` carrying a secret returns ``block`` (the write must be
        halted) and the secret_scan hook persists a ``hook_runs`` row outcome=block
        (HOOK-04 / T-08-07-ID). Best-effort: a missing engine/registry degrades to
        ``continue`` so audit never aborts the write.
        """
        from agents.capabilities.hooks.base import HOOK_CONTINUE

        engine = self._engine
        if engine is None:
            return HOOK_CONTINUE
        from agents.capabilities.registry import CapabilityRegistry

        return await engine._fire_hooks(
            event_name, step, self._ectx, CapabilityRegistry(), payload=payload
        )

    # ── FixPolicy factory (D-06) — the strategy builds a policy via the handle ──
    def make_fix_policy(
        self, deliverable: str, *, max_attempts: int = 2
    ) -> "FixPolicy":
        """Return a generic ``FixPolicy`` for the fix-loop (reached via ``ctx.runner``).

        The strategy CANNOT import the kernel (import-linter forbids
        ``agents.capabilities -> agents.execution_engine``), so it builds the policy
        through this handle factory rather than importing ``FixPolicy`` directly. The
        prototype manifest's deliverable is ``prototype.html`` so the produced policy
        keeps the loop byte-identical; a non-prototype workflow names its own file.
        """
        return FixPolicy(deliverable=deliverable, max_attempts=max_attempts)

    # ── Build a DeliverableContext target for a registered Validator (D-04) ─────
    def deliverable_context(
        self,
        *,
        name: str,
        step: str = "",
        content: str | None = None,
        task_meta: dict | None = None,
        require_render: bool | None = None,
    ) -> DeliverableContext:
        """Return a ``DeliverableContext`` target keyed on the sandbox deliverable.

        The validator reaches the heavy checks + the audit writer through the
        ``runner`` handle carried on the returned context; ``path`` resolves to the
        per-run sandbox path for ``name`` so ``runner.static_check(target.path)``
        validates the on-disk deliverable byte-identically to the legacy direct call.

        ``require_render`` (quick-260701-bob / REQUIRE-RENDER-KNOB) is threaded from
        the compiled ``Step.require_render`` so html_render sees the per-step render
        fail-closed policy; None keeps the Settings-default (skip-is-a-pass) behavior.
        """
        try:
            path = self.sandbox.path_for(name)
        except Exception:  # noqa: BLE001 — a missing sandbox degrades to no path
            path = None
        return DeliverableContext(
            name=name,
            runner=self,
            path=path,
            _content=content,
            step=step,
            task_meta=dict(task_meta or {}),
            require_render=require_render,
        )

    # ── Human gate delegate (08-02 / GATE-03 parity; 10-03 approval payload) ────
    async def run_human_gate(
        self, step: Any, *, output: str = "", payload: dict | None = None
    ) -> AsyncIterator[dict]:
        """Route a declared ``gates:[human|approval]`` step through the review gate.

        Delegates to the engine's unchanged ``_run_review_gate`` so the emitted
        ``review_gate_*`` event sequence is byte/event-identical (GATE-03 parity —
        NO new HITL mechanism, NO snapshot re-baseline). The registered ``human``
        gate consumes this generator and re-surfaces its events; the existing
        inline ``_should_gate`` → ``_run_review_gate`` path in ``_run_agent`` is
        untouched (this is the additive registry-driven entry point).

        This is the ONE HITL delegate (D-02 single-mechanism). The ``approval`` gate
        (10-03) passes the D-04 exec-policy SNAPSHOT as ``payload`` — a structured
        dict that rides the SAME generic ``review_gate_ready.data.output`` field (no
        frontend rebuild). When ``payload`` is provided it supersedes ``output`` as
        the review payload; when ``payload`` is ``None`` the behavior is EXACTLY as
        before (the ``human``-gate string ``output`` path is byte-identical —
        parity), because ``_run_review_gate`` is UNCHANGED and simply forwards
        whatever value it receives. There is NO sibling ``run_approval_gate``
        (rejected — a second HITL surface).

        Yields the engine's review-gate event dicts unchanged. The internal
        ``_gate_rejected`` / ``_gate_edited`` signals flow through so the caller can
        map them to the gate outcome.
        """
        # The structured approval payload (D-04) rides the generic output field; a
        # None payload preserves the byte-identical human-gate string path (parity).
        review_payload: Any = payload if payload is not None else output
        spec = self._spec_for(step)
        async for event in self._engine._run_review_gate(
            pipeline_run_id=self.run_id,
            agent_id=spec.id,
            agent_name=spec.name,
            output=review_payload,
            # BUG-2 Cond B (quick-260720-ec4): thread the SAME cooperative
            # cancel_event execute() holds into the delegate so a run parked at a
            # DECLARED human/approval gate honors Stop via the EXISTING cancel-aware
            # race in _run_review_gate — exactly as the inline gate sites do. None
            # (no live cancel_event) preserves the plain `await event.wait()` path
            # byte-identically (INV-3). Keys ONLY on the generic cancel_event.
            cancel_event=self.cancel_event,
        ):
            yield event

    # ── Gate-event read handle (10-03 / D-03 first-exec memory) ─────────────────
    async def read_gate_events(self, run_id: str) -> list:
        """Return the run's ``gate_events`` rows (best-effort, default-deny scoped).

        Reached by the ``approval`` gate via ``ctx.runner.read_gate_events`` for the
        D-03 durable first-exec memory (a prior approval-pass row short-circuits the
        second exec step's pause). Delegates to the per-run ``ScopedStore`` so the
        read is owner/workspace-scoped (cross-owner → ∅, T-08-02-ID). Best-effort —
        mirrors the ``record_hook_run`` degrade: no store (offline harness) → ``[]``;
        a read failure logs + returns ``[]`` rather than aborting the gate (INV-3
        parity: an audit READ must never break the live stream / approval flow).
        """
        store = getattr(self._ectx, "scoped_store", None)
        if store is None:
            return []
        try:
            return await store.read_gate_events(run_id)
        except Exception as exc:  # noqa: BLE001 — read must never abort the run
            logger.warning(
                "read_gate_events(run_id=%s) failed: %s", run_id, exc,
            )
            return []

    # ── Typed-graph read (ART-03) ──────────────────────────────────────────────
    def latest_typed_content(self, producer_step: str) -> str | None:
        return self._engine._latest_typed_content(self._ectx, producer_step)

    # ── Upstream-context-hash handle (RESUME-14; INV-12 one home) ──────────────
    def upstream_context_hash(self, step) -> str:
        """Return the per-step upstream-context-hash the task_key namespaces on.

        Delegates to the engine's single ``_compute_upstream_context_hash`` (the same
        upstream scan ``input_hash`` reuses — no second scheme). The digest is
        PER-STEP (identical for every task in the step), so a strategy computes it
        ONCE per ``run`` and threads it into each task's ``compute_task_key``.
        """
        return self._engine._compute_upstream_context_hash(step, self._ectx)

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
        # Bind the current step (08-08 / CR-01) so the engine's before_write hook
        # firing reads ``step.hooks`` — declaration-driven (only DECLARED hooks fire).
        prev_step = getattr(self._ectx, "current_step", None)
        self._ectx.current_step = step
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
            self._ectx.current_step = prev_step

    # ── The Both-validation + bounded internal fix-loop (L-build region C) ─────
    async def run_validation_fix_loop(
        self,
        step: Any,
        *,
        task_num: int,
        total_tasks: int,
        agent_id: str = "prototype-build",
        filename: str | None = None,
        policy: "FixPolicy | None" = None,
        baseline_static: "set[str] | None" = None,
        baseline_console: "set[str] | None" = None,
        user_instruction: str | None = None,
        label: str = "",
    ) -> None:
        """Run the GENERIC Both-validation + bounded fix-loop (delegates to the engine).

        The loop is config-driven (D-06 / VALID-01/02): the deliverable name + the
        attempt bound come from a ``FixPolicy`` (``policy.deliverable`` /
        ``policy.max_attempts``) — NOT hardcoded to ``prototype.html``. Running it
        with ``policy=FixPolicy(deliverable="app.py")`` validates + fixes ``app.py``.

        It delegates to the engine's SINGLE ``_run_validation_fix_loop`` so the fix
        wording, the thread-id shape, the bounded attempts, and the
        consume-internally-emit-nothing contract are byte-identical (INV-3). The fix
        sub-agent edits the deliverable on disk as a side effect; nothing is re-emitted.

        Back-compat (07-11 / CR-05): callers may pass the DECLARED ``filename``
        directly (the strategy's existing call shape) — it is wrapped into a default
        ``FixPolicy(deliverable=filename, max_attempts=2)`` so prototype validation is
        byte-identical. ``policy`` (when given) takes precedence; exactly one of
        ``policy`` / ``filename`` must be provided.
        """
        from agents.factory import AgentContext

        if policy is None:
            if filename is None:
                raise ValueError(
                    "run_validation_fix_loop requires one of policy / filename"
                )
            policy = FixPolicy(deliverable=filename)
        deliverable_name = policy.deliverable
        max_attempts = policy.max_attempts

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
            filename=deliverable_name,
            max_attempts=max_attempts,
            baseline_static=baseline_static,
            baseline_console=baseline_console,
            user_instruction=user_instruction,
            label=label,
            checkpointer=ectx.checkpointer,
            # Per-step render fail-closed knob (quick-260701-bob / REQUIRE-RENDER-KNOB):
            # None → the loop falls back to settings.PROTOTYPE_REQUIRE_RENDER (parity).
            require_render=getattr(step, "require_render", None),
            # ISS-033-A: the run's aux usage sink, so the fix sub-agent's tokens are
            # COUNTED in the run totals instead of discarded by the internal drain.
            aux_usage_sink=self._aux_usage_sink,
        )

    # ── Post-task typed dual-write (keeps _latest_typed_content current) ───────
    async def persist_task_html(
        self,
        task_num: int,
        agent_id: str = "prototype-build",
        *,
        filename: str,
        task_key: str | None = None,
    ) -> None:
        """Typed-write the post-task deliverable as a new ref version (ART-03).

        RESUME-14: ``task_key`` is the content-addressed identity the strategy threads
        in — it is written into BOTH the declared-file (``html_file``) and the sibling
        (``file_bundle``) ``task_id`` slots so the resume cursor + reconciler key on a
        stable, upstream-namespaced, duplicate-safe identity instead of a raw position.
        When absent (a direct-seam unit caller that does not compute keys) it FALLS BACK
        to the legacy positional ``str(task_num)`` — byte-identical to pre-RESUME-14 —
        so the capture-seam unit contract stays unchanged. A 64-char key can never
        collide with a positional id, so the two coexist (backward-compat fail-safe).

        Mirrors the legacy build loop's per-task dual-write so the NEXT task's
        prompt skeleton reads the most recent content via ``_latest_typed_content``.
        Best-effort; a missing file is a no-op.

        07-11 / CR-05: ``filename`` is the DECLARED deliverable filename threaded in
        from the strategy — REQUIRED (no ``prototype.html`` default). It keys BOTH
        the sandbox read AND the persisted artifact ``location`` so a non-prototype
        task_loop workflow dual-writes ITS OWN file (the prototype manifest declares
        ``prototype.html`` so the prototype dual-write is byte-identical).

        RESUME-07 (Phase 46-02): the capture is now GENERIC — after the declared
        deliverable (branch 1, byte-identical below), branch 2 walks the run sandbox
        and durably captures EVERY OTHER changed file as a ``file_bundle`` row under
        the SAME ``task_id``, so a resume can re-materialise a task's full on-disk
        output (Q7), not just the single declared file. The walk reuses the
        exclusion-proven ``_collect_deliverable_relpaths`` (excludes ``.uploads/`` +
        ``PLANNER.md`` — the Phase-47/ND-10 fence, free) and dedups each sibling by
        ``content_hash`` against the latest durable ref for that ``location``, so an
        unchanged sibling (or a task that touched nothing new) writes nothing. Capture
        is EVENT-FREE and best-effort: a walk/read/write failure must never break the
        task. INV-12: this SUBSUMES the single writer in place — one seam, no second
        capture writer.

        INV-3 dormancy — sibling capture is DURABLE-STORE-ONLY (``store.write_ref``),
        NOT a graph dual-write. Branch 1 (the declared file) still dual-writes graph +
        store as before. Branch 2 deliberately does NOT touch the in-memory typed graph
        (``ectx.artifacts``): ``_latest_typed_content(producer_agent)`` (engine.py:5509)
        returns the MAX-``version`` ref for an agent ACROSS ALL KINDS, so adding a
        sibling ``file_bundle`` under ``producer_agent=agent_id`` to the graph would
        out-version the ``html_file`` and corrupt what the NEXT build task reads —
        diverging the prototype/od_prototype goldens (the build loop writes spec.md /
        design.md / tasks.md reference files into the sandbox, so a golden's sibling set
        is NOT empty). Persisting siblings to the durable mirror only leaves every
        in-memory read (context routing, ``_latest_typed_content``) byte-identical while
        still giving Plan 46-03 re-materialisation a complete record (it reads
        ``store.tree()``, not the in-memory graph). The store write is event-free and
        best-effort — it degrades (logs) on the offline golden harness (no
        ``workflow_runs`` FK row) exactly like every other durable write.

        Reader interaction (documented, not changed): ``_surface_partial_fragments``
        (engine.py:870) reads ``kind in ("file_bundle","fragment")`` off the in-memory
        graph for the budget-abort partial payload — since siblings are store-only they
        never enter that in-memory read, so there is no interaction there; on a RESUMED
        run they arrive via ``_hydrate_artifacts_from_store`` (46-03) and would surface
        as semantically-correct partial results (golden-dormant — goldens never resume
        nor budget-abort).
        """
        # RESUME-14: the content-addressed key stamps the task_id slot; a direct-seam
        # caller that passes no key falls back to the legacy positional id (byte-identical).
        _effective_task_id = task_key if task_key is not None else str(task_num)

        # ── Branch 1: the DECLARED deliverable — byte-identical (INV-3) ──────────
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
            task_id=_effective_task_id,
        )

        # ── Branch 2: generic sibling capture (RESUME-07) — DURABLE-STORE-ONLY ───
        # Best-effort: never let the capture break the task (mirror branch 1's guard
        # discipline). The in-memory typed graph is intentionally NOT touched here (see
        # the INV-3 dormancy note in the docstring) — this is a durable-mirror-only
        # write via the run's owner-scoped ScopedStore.
        store = getattr(self._ectx, "scoped_store", None)
        if store is None:
            return
        try:
            relpaths = _collect_deliverable_relpaths(
                self.sandbox.root, _DELIVERABLE_EXCLUDE
            )
        except Exception:  # noqa: BLE001 — a walk failure must not break the task
            return
        # Latest durable content_hash per location, for content-hash dedup (the
        # fix-loop re-persist under the same task_id writes a NEW version only when the
        # content actually changed — the Phase-45 distinct-id lesson; an unchanged
        # sibling, or a task that touched nothing new, writes nothing → no runaway
        # versions, T-46-02-03).
        latest_hash_by_loc: dict[str, str] = {}
        try:
            for r in await store.tree(self._ectx.run_id):
                loc = getattr(r, "location", None)
                if loc is not None:
                    latest_hash_by_loc[loc] = getattr(r, "content_hash", None)
        except Exception:  # noqa: BLE001 — dedup is best-effort; degrade to no-dedup
            latest_hash_by_loc = {}

        from agents.artifacts.graph import ArtifactRef  # kernel-pure typed record

        for relpath in relpaths:
            if relpath == filename:
                continue  # the declared file is already captured as html_file
            try:
                content = self.sandbox.read(relpath)
            except Exception:  # noqa: BLE001
                continue
            if not content:
                continue
            new_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
            if latest_hash_by_loc.get(relpath) == new_hash:
                continue
            try:
                # DURABLE-ONLY write — force_db_version=True so the per-(run, kind)
                # version is DB-authoritative (this write bypasses the shared
                # in-memory ArtifactGraph counter, mirroring the clarify-path idiom).
                await store.write_ref(
                    ArtifactRef(
                        id=str(_uuid4()),
                        kind="file_bundle",
                        owner_id=self._ectx.owner_id,
                        workspace_id=getattr(self._ectx, "workspace_id", None) or "",
                        run_id=self._ectx.run_id,
                        producer_step=agent_id,
                        producer_agent=agent_id,
                        task_id=_effective_task_id,
                        content=content,
                        content_hash=new_hash,
                        location=relpath,
                        version=1,
                    ),
                    force_db_version=True,
                )
                latest_hash_by_loc[relpath] = new_hash
            except Exception as exc:  # noqa: BLE001 — best-effort, never break the task
                from sqlalchemy.exc import SQLAlchemyError

                if not isinstance(exc, SQLAlchemyError):
                    raise
                logger.warning(
                    "per-task sibling capture persist failed for run %s "
                    "location %s (%s) — durable write degraded (offline harness / "
                    "schema unavailable); task unaffected (RESUME-07 best-effort)",
                    self._ectx.run_id, relpath, exc,
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
