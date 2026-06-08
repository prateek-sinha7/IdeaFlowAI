"""agents/execution_engine/engine.py — Universal Execution Engine (Phase 2).

The single entry point replacing WorkflowOrchestrator.execute(),
run_od_prototype_pipeline, and run_od_ppt_pipeline.

Phase 2 responsibilities:
  1. Validate the Workflow DAG via WorkflowResolver (halt if unsatisfiable)
  2. Prepend and run the Deep_Planner_Agent (15s timeout, default PROCEED)
  3. Evaluate the gate verdict; invoke ClarifyEngine if CLARIFY_REQUIRED
  4. Run domain agents in topological order
  5. Emit all WS events using the existing envelope shape
  6. Validation_Gate blocking (soft block — emit validation_gate_blocked, pause)
  7. Best-effort typed artifact persistence (degrade-and-log; never abort the run)
  8. Missing-template error (halt before any agent executes)

Phase 3 will add: planning_context injection, agent_input events,
DB-backed artifacts, lineage, revision intelligence, restart resumability.
"""

from __future__ import annotations

import asyncio
import itertools
import json
import logging
import re
import time
import uuid
from typing import AsyncGenerator

from pathlib import Path

from agents.artifact_store.store import get_artifact_store
from agents.artifacts.graph import ArtifactGraph
from agents.authz import ScopedStore
from agents.capabilities.registry import CapabilityRegistry
from agents.execution_engine.context import ExecutionContext
from agents.execution_engine.resolver import WorkflowResolver
from agents.execution_engine.state_machine import get_state_machine
from agents.capabilities.model_catalog import ModelCatalog
from agents.factory import AgentContext, create_runner
from agents.model_policy import ModelResolver
from agents.workflows.compiler import WorkflowCompiler
from agents.workflows.manifest import load_manifest
from agents.workflows.plan import CompiledWorkflow
from app.agents.sandbox import (
    RunSandbox,
    count_sandbox_deliverables,
    serialize_sandbox_deliverable,
)

logger = logging.getLogger("agents.execution_engine.engine")

# ---------------------------------------------------------------------------
# Structured JSON logging helper (FR-023 / T076)
# ---------------------------------------------------------------------------


def _log_event(
    event_type: str,
    pipeline_run_id: str,
    agent_id: str | None = None,
    duration_ms: float | None = None,
    error: str | None = None,
    **extra: object,
) -> None:
    """Emit a structured JSON log entry for a lifecycle event (FR-023 / SC-013).

    Every entry includes: timestamp, pipeline_run_id, event_type.
    Optional: agent_id, duration_ms, error.
    """
    import json as _json
    entry: dict = {
        "timestamp": _now(),
        "pipeline_run_id": pipeline_run_id,
        "event_type": event_type,
    }
    if agent_id is not None:
        entry["agent_id"] = agent_id
    if duration_ms is not None:
        entry["duration_ms"] = round(duration_ms, 2)
    if error is not None:
        entry["error"] = error
    entry.update(extra)
    logger.info("LIFECYCLE %s", _json.dumps(entry))


# ---------------------------------------------------------------------------
# Durable run_events sink (PERSIST-03 / D-11)
# ---------------------------------------------------------------------------


class _RunEventSink:
    """Per-run holder that persists stamped events to ``run_events`` (PERSIST-03).

    Created by the public ``execute()`` wrapper and ARMED by ``_execute_impl`` once
    the per-run ``ScopedStore`` + run id are known (after owner/workspace wiring).
    Until armed, ``persist`` is a no-op (events emitted before the entry wiring —
    none today — would simply not be persisted rather than error).

    ``persist`` is BEST-EFFORT for the DB-write CASE ONLY (WR-02 narrowed contract):
    a ``SQLAlchemyError`` (e.g. the offline characterization harness has no
    ``run_events``/``workflow_runs`` schema, or an FK/constraint failure) degrades to
    a ``warning`` so the live event stream and the deterministic deliverable are
    NEVER perturbed (INV-3). Any OTHER exception is treated as a real bug and
    PROPAGATES (re-raised) — it is NOT swallowed. The ``seq``/``event_id`` are stamped
    on the event dict regardless (stripped from the 0A multiset), so parity holds
    whether or not the row lands.
    """

    def __init__(self) -> None:
        self._store: ScopedStore | None = None
        self._run_id: str | None = None

    def arm(self, store: ScopedStore, run_id: str) -> None:
        self._store = store
        self._run_id = run_id

    async def persist(
        self, seq: int, event_id: str, type: str, payload_json: dict
    ) -> None:
        """Append one ``run_events`` row for the stamped event (best-effort)."""
        if self._store is None or self._run_id is None:
            return
        try:
            await self._store.append_event(
                self._run_id, seq, event_id, type, payload_json
            )
        except Exception as exc:  # noqa: BLE001 — never break the live stream
            # WR-02: narrow the degrade to the offline-harness DB condition
            # (no schema → SQLAlchemyError). Surface it at WARNING with the run
            # context so a genuine prod persistence loss is observable instead of
            # a silent debug no-op; any non-DB exception is a real bug → re-raise.
            from sqlalchemy.exc import SQLAlchemyError

            if not isinstance(exc, SQLAlchemyError):
                raise
            logger.warning(
                "run_events persist failed for run %s seq %d (%s) — "
                "DB write degraded (offline harness / schema unavailable); "
                "stream unaffected (PERSIST-03 best-effort)",
                self._run_id, seq, exc,
            )


PLANNER_TIMEOUT_SECONDS = 120.0  # SmartPlanner: single call (generous — large chained prompts run slower). On timeout it defaults to PROCEED, so it never discards agent work.
PLANNER_AGENT_ID = "deep-planner"

# ── Human-in-the-loop: always ask clarifying questions ────────────────────────
# When True, the gate verdict is forced to CLARIFY_REQUIRED for every pipeline
# run regardless of what the planner returns. Set to False to let the planner
# decide autonomously.
ALWAYS_CLARIFY = True


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# PPT carousel deck sanitizer (deterministic safety net)
# ---------------------------------------------------------------------------

_PPT_PIPELINE_TYPES = frozenset({"od_ppt", "od_ppt_revision", "ppt", "ppt_revision"})

# Pipelines whose single deliverable is the ``prototype.html`` built on the run
# sandbox disk (NOT a serialized multi-file bundle, NOT a streamed text answer).
# ``od_prototype`` is the OpenDesign-context alias of ``prototype`` (same agents,
# plus a selected template + design system). It is never a registered pipeline,
# but BOTH entry surfaces — the WebSocket ``run_pipeline`` handler and the NDJSON
# ``/api/prototype/run`` adapter — forward the label ``od_prototype`` to the engine
# UNALIASED (the WS handler resolves the alias only for agent lookup, not for the
# value it passes to execute()), so the engine must accept both spellings.
# ``prototype_revision`` is deliberately excluded: it has its own deliverable
# resolution (original-HTML fallback) in :func:`_resolve_final_output`.
_PROTOTYPE_PIPELINE_TYPES = frozenset({"prototype", "od_prototype"})

# Workspace filename the prototype-revision-agent reads + edits in place. The
# engine seeds it with the current prototype before the agent runs and reads it
# back as the deliverable afterwards (see execute()).
REVISION_FILE_NAME = "prototype.html"


# ---------------------------------------------------------------------------
# Declarative routing seam (MAN-04 / MAN-05)
# ---------------------------------------------------------------------------
#
# The engine sources the FOUR routing concerns — step sequence + agent ids,
# deliverable spec, clarify defaults, and the planner-skip flag — from the
# CompiledWorkflow produced by the manifest + compiler layer (agents/workflows),
# NOT from the legacy hardcoded dicts (get_pipeline_agents / _pipeline_defaults /
# SKIP_PLANNER_FOR_PROTOTYPE). The legacy `pipeline_type` label is reduced to an
# id-alias resolved to a manifest id at run entry (od_prototype -> prototype;
# every real key -> itself), consumed ONLY by that resolver for routing (MAN-05).
# There is NO legacy `pipeline_type` dispatch fallback (INV-12): a dispatchable
# run sources its agent list from the compiled plan.
#
# The behavioral L1-L13 branches that still read `pipeline_type`/`spec.id` are
# UNCHANGED and explicitly allow-listed as Phase-7-scoped — they are behavioral,
# not routing. See RESEARCH §D-09 for the full classification.

# Where the hand-authored workflow.yaml manifests live (one dir per manifest id).
_WORKFLOWS_DIR = Path(__file__).resolve().parents[1] / "workflows"

# Shared, stateless capability registry + compiler for the run-entry seam.
_CAPABILITY_REGISTRY = CapabilityRegistry()
_WORKFLOW_COMPILER = WorkflowCompiler()


def resolve_alias(pipeline_type: str) -> str:
    """Resolve the legacy run label to a manifest id (MAN-05).

    ``od_prototype`` -> ``prototype``; every real key resolves to itself. This is
    the SINGLE point that maps the legacy ``pipeline_type`` label onto a manifest
    id for routing. Sourced from the central capability registry, which lifts
    ``agents.registry._OD_ALIAS_BASE`` (single source of truth) — never
    re-hardcoded here.
    """
    return _CAPABILITY_REGISTRY.resolve_alias(pipeline_type)


def compile_for_run(pipeline_type: str) -> CompiledWorkflow:
    """Load + compile the CompiledWorkflow the engine routes a run from (MAN-04).

    Resolves the ``pipeline_type`` id-alias to a manifest id, loads that
    manifest from ``agents/workflows/<id>/workflow.yaml``, and compiles it to a
    typed, validated ``CompiledWorkflow``. The engine sources the agent
    sequence, deliverable spec, clarify defaults, and planner flag from the
    returned plan — no legacy dispatch fallback (INV-12).

    Raises:
        FileNotFoundError: if no manifest exists for the resolved id (the
            resolver maps to a known id from a closed set, so an unknown label
            surfaces a FileNotFoundError rather than ``open(base / arbitrary)``
            — no path traversal via the run label, T-04-09).
        CompilerError / ManifestValidationError: on a malformed manifest.
    """
    manifest_id = resolve_alias(pipeline_type)
    manifest = load_manifest(manifest_id, _WORKFLOWS_DIR)
    return _WORKFLOW_COMPILER.compile(manifest, _CAPABILITY_REGISTRY)


# ---------------------------------------------------------------------------
# Validation fix-loop — pure, unit-testable issue selection (Phase 4 + 5)
# ---------------------------------------------------------------------------
#
# These module-level helpers are the SINGLE source of truth for how a
# StaticCheckResult + RenderResult are normalized into stable "signatures" and
# into the ordered list of issues the internal fix-loop feeds back to the
# sub-agent. They are deliberately pure (no agent, no I/O, no engine state) so
# both ``_run_validation_fix_loop`` AND its tests — and the Phase-5 revision
# task (T2) — import and reuse the *same* normalization.
#
# Selection policy (locked Phase-5 decision):
#   * Static REGRESSIONS — static issues whose signature is NOT in
#     ``baseline_static``. An empty/None baseline ⇒ ALL static issues (this is
#     today's build behavior — fix everything static_check reports).
#   * Hard render-breakage, ALWAYS included regardless of baseline — uncaught
#     page errors and dead nav links (a click activates no <section data-page>
#     ⇒ blank page / "won't display proper content"). render_check exposes no
#     dedicated blank/empty-render field beyond these; a dead nav IS the
#     blank-render signal.
#   * Console errors — those whose signature is NOT in ``baseline_console``
#     (empty/None baseline ⇒ all, = today).
#   * Render contributes ONLY when ``rres.available`` — a skipped render
#     (Chromium absent) never adds issues, exactly as today.
#
# Line WORDING + ORDER mirror today's build ``error_lines`` assembly EXACTLY
# (static issues, then console errors, then uncaught exceptions, then dead nav
# links) so that with empty baselines the build fix-message is byte-identical.


def _static_issue_sigs(sres) -> set[str]:
    """Signatures of a StaticCheckResult's fatal issues (for baseline diffing).

    A static issue's signature is its message string verbatim — ``static_check``
    already emits precise, stable, position-independent messages (e.g. ``dead
    nav link: href '#/x' has no matching <section data-page="x">``), so the raw
    text is a reliable identity for "the same defect before vs. after an edit".
    """
    return set(getattr(sres, "issues", None) or [])


def _console_sigs(rres) -> set[str]:
    """Signatures of a RenderResult's console errors (for baseline diffing).

    Only meaningful when the render actually ran (``rres.available``); a skipped
    render yields no console signatures. The signature is the console message
    text verbatim — the same identity the baseline is computed from.
    """
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

    Pure function over a :class:`~app.agents.static_check.StaticCheckResult`
    (``sres``) and a :class:`~app.agents.render_check.RenderResult` (``rres``),
    applying the locked Phase-5 selection policy (see the module comment above).

    With ``baseline_static`` and ``baseline_console`` both empty/None the result
    is EXACTLY today's build ``error_lines`` (all static issues, then all
    console errors, then page errors, then dead nav links) — so the build path
    stays byte-identical. With populated baselines (revision) only NEW static
    issues + NEW console errors are selected, while hard render-breakage (page
    errors, dead nav links) is ALWAYS included regardless of baseline.

    The returned strings are exactly the lines fed into the fix prompt; the
    caller builds the failing-decision from ``bool(...)`` of this list.
    """
    base_static = baseline_static or set()
    base_console = baseline_console or set()

    selected: list[str] = []

    # (1) Static regressions — issues not present on the baseline. Empty
    #     baseline ⇒ every static issue (today's build behavior). Preserve the
    #     emission order static_check produced.
    for issue in getattr(sres, "issues", None) or []:
        if issue not in base_static:
            selected.append(issue)

    # Render contributes only when the headless render actually ran.
    if getattr(rres, "available", False):
        # (2) New console errors — filtered by the console baseline (empty ⇒
        #     all, = today). Prefixed exactly as today's error_lines.
        for err in getattr(rres, "console_errors", None) or []:
            if err not in base_console:
                selected.append(f"console error: {err}")

        # (3) Hard render-breakage, ALWAYS included regardless of baseline:
        #     uncaught page exceptions …
        for err in getattr(rres, "page_errors", None) or []:
            selected.append(f"uncaught exception: {err}")

        # … and dead nav links (click activates no <section data-page> ⇒ blank
        #     page). Mirrors today's wording verbatim.
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


def _sanitize_carousel_deck_html(html: str) -> str:
    """Strip slide-hiding CSS that contradicts a horizontal translateX carousel deck.

    The od_ppt composer LLM sometimes hallucinates ``.slide:not(.active){display:none}``
    and ``.slide.active{display:...}`` (and occasionally a bare ``.slide{...display:none...}``)
    on top of a pure-carousel template whose ``.stage`` navigates via
    ``transform: translateX(-i*100vw)`` while every ``.slide`` stays ``display:grid``.
    Those rules remove slides 2..N from layout, so only slide 1 ever renders.

    This is a deterministic backstop — the composer prompt forbids these rules, but LLM
    output is non-deterministic, so we also strip them here. We act ONLY when the deck is
    clearly a horizontal carousel, and we remove ONLY the conflicting rules — never the
    base ``.slide{display:grid}`` (the carousel relies on it) nor ``@media print`` rules
    (those use ``display:block``/``!important``, not ``display:none``).

    Returns the (possibly modified) HTML. No-op on non-carousel / non-HTML input.
    Scope this strictly to ppt/od_ppt output — never call it on prototype HTML.
    """
    if not html or "<style" not in html.lower():
        return html

    # Detect a horizontal carousel: a translateX(...vw) transform driving the stage,
    # plus the .stage/.slide structure it relies on. Whitespace-robust.
    has_translate_vw = re.search(r"translateX\s*\(\s*[^)]*vw", html, re.IGNORECASE) is not None
    has_stage_slide = (".stage" in html) and (".slide" in html)
    if not (has_translate_vw and has_stage_slide):
        return html

    original = html

    # 1) `.slide:not(.active) { ... }` — always a carousel-breaking hide rule. Remove it.
    html = re.sub(
        r"\.slide\s*:not\(\s*\.active\s*\)\s*\{[^}]*\}",
        "",
        html,
        flags=re.IGNORECASE,
    )

    # 2) `.slide.active { ... }` ONLY when it overrides `display` (fights the carousel).
    #    A cosmetic `.slide.active` rule (e.g. box-shadow) without `display` is left alone.
    html = re.sub(
        r"\.slide\.active\s*\{[^}]*\bdisplay\s*:[^}]*\}",
        "",
        html,
        flags=re.IGNORECASE,
    )

    # 3) A bare `.slide { ... display:none ... }` hide rule — never legitimate for a
    #    carousel (base is display:grid, print is display:block). The negative lookbehind
    #    keeps us off `.slide-inner`, `.slide.dark`, `.slide.active`, `.slide:not(...)`, etc.
    html = re.sub(
        r"(?<![\w.\-:])\.slide\s*\{[^}]*?\bdisplay\s*:\s*none\b[^}]*\}",
        "",
        html,
        flags=re.IGNORECASE,
    )

    if html != original:
        # Tidy up runs of blank lines left where rules were removed (cosmetic only).
        html = re.sub(r"[ \t]*\n([ \t]*\n){2,}", "\n\n", html)
        logger.info("Sanitized carousel deck: removed slide-hiding CSS (%d → %d chars)", len(original), len(html))
    return html


def _unwrap_artifact(text: str) -> str:
    """Return the inner content of a single ``<artifact>…</artifact>`` wrapper.

    Some text agents (the PPT composer) emit their deliverable wrapped in an
    ``<artifact>`` tag. Return the unwrapped inner content; return ``text``
    unchanged when there is no wrapper.

    This is applied ONLY to a streamed-text deliverable — NEVER to a serialized
    code-gen bundle or a prototype's raw HTML, both of which can legitimately
    contain the literal substring ``<artifact>`` inside a file (e.g. an
    ``<artifact>`` *example* printed inside design.md). Stripping over those
    would extract the example and discard the real deliverable.
    """
    if text and "<artifact" in text:
        m = re.search(r"<artifact[^>]*>\s*([\s\S]*?)\s*</artifact>", text, re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return text


def _resolve_final_output(
    pipeline_type: str,
    sandbox: RunSandbox,
    results: list[dict],
    *,
    revision_original_html: str | None = None,
) -> str:
    """Resolve the run's deliverable (``WorkflowRun.output``) from the sandbox.

    The deliverable is chosen by *pipeline class* — never by blindly serializing
    every file on the run sandbox. The prototype build loop writes ``spec.md`` /
    ``design.md`` / ``tasks.md`` into the SAME sandbox as build-agent reference
    scaffolding; those are NOT deliverables and must never leak into the output
    (``design.md`` even carries a literal ``<artifact>`` *example*, so an
    indiscriminate serialize-then-strip would surface that example as a tiny
    "deliverable" and discard the real prototype):

      * ``prototype_revision`` — the revision agent edited ``prototype.html`` in
        place; that single file IS the deliverable. Fall back to the streamed
        HTML, or the pre-revision original, only when the file is missing.
      * ``prototype`` / ``od_prototype`` — the build loop wrote ``prototype.html``
        incrementally; that single file IS the deliverable. Fall back to the last
        streamed output (NEVER serialize the sandbox) when the file is missing.
      * code-gen (``app_builder`` / ``mulesoft_to_springboot`` / ``dotnet_to_azure``
        and their revisions) — multiple deliverable files; serialize them to the
        ``filename:``-block bundle the UI's FilesTab/AppBuilderPreview parse.
      * text / PPT — the last agent's streamed output IS the deliverable; an
        ``<artifact>`` wrapper (the PPT composer) is unwrapped.

    Args:
        pipeline_type: The run's pipeline type (resolved, e.g. ``"prototype"``).
        sandbox: The per-run :class:`RunSandbox` the agents wrote to.
        results: Per-agent result dicts (each with an ``"output"`` key); the last
            one's output is the streamed deliverable for the text/PPT class.
        revision_original_html: The pre-revision HTML, used only as the last-ditch
            fallback when a ``prototype_revision`` agent never wrote the file.

    Returns:
        The ``WorkflowRun.output`` string for this run.
    """
    last_streamed = results[-1]["output"] if results else ""

    if pipeline_type == "prototype_revision":
        # The revision agent edited prototype.html in place — that file IS the
        # deliverable (raw HTML, never the ```filename:``` wrapper). Fall back
        # without losing the prototype when the agent never wrote the file.
        revised = sandbox.read(REVISION_FILE_NAME)
        if revised:
            return revised
        streamed = last_streamed.strip()
        looks_like_html = streamed[:60].lower().lstrip().startswith(("<!doctype", "<html"))
        chosen = streamed if looks_like_html else (revision_original_html or streamed)
        logger.warning(
            "prototype_revision: %s not written by agent — fell back to %s",
            REVISION_FILE_NAME,
            "streamed HTML" if looks_like_html else "original HTML",
        )
        return _unwrap_artifact(chosen)

    if pipeline_type in _PROTOTYPE_PIPELINE_TYPES:
        # Forward prototype: the per-task build loop wrote prototype.html on disk.
        # That single file is the deliverable — never serialize the sandbox (which
        # bundles the spec.md/design.md/tasks.md reference scaffolding).
        built = sandbox.read(REVISION_FILE_NAME)
        if built:
            return built
        logger.warning(
            "%s: %s not written by build loop — fell back to streamed output",
            pipeline_type,
            REVISION_FILE_NAME,
        )
        return last_streamed

    if count_sandbox_deliverables(sandbox.root) > 0:
        # Code-gen: multiple deliverable files → the ```filename:```-block bundle.
        # No <artifact> unwrap here — a serialized file may legitimately contain
        # the literal text "<artifact>" (this is the bug the prototype branch above
        # also guards against).
        return serialize_sandbox_deliverable(sandbox.root)

    # Text / PPT: the streamed output IS the deliverable; unwrap an <artifact> tag.
    return _unwrap_artifact(last_streamed)


class ExecutionEngine:
    """Universal Execution Engine — single entry point for all workflows."""

    def __init__(self) -> None:
        self._resolver = WorkflowResolver()
        self._store = get_artifact_store()
        self._state_machine = get_state_machine()

    async def execute(
        self,
        agents: list,
        user_message: str,
        pipeline_run_id: str,
        pipeline_type: str = "custom",
        cancel_event: asyncio.Event | None = None,
        user_id: str | None = None,
        session_id: str | None = None,
        attached_skills: list[dict] | None = None,
        attached_hooks: list[dict] | None = None,
        model_id: str | None = None,
        od_context: dict | None = None,
        gate_agent_ids: list[str] | None = None,
        parent_run_id: str | None = None,
        model_overrides: dict[str, str] | None = None,
    ) -> AsyncGenerator[dict, None]:
        """Public entry — the SINGLE outward emit boundary (PERSIST-03 / D-11).

        This thin wrapper is the ONE chokepoint every engine event passes through
        before reaching the caller (websocket.py's queue drainer). It runs the real
        pipeline body (``_execute_impl``) and, for EACH yielded event, stamps a
        monotonic per-run ``seq`` (1,2,3,… — contiguous deltas==1, SAFE-03) plus a
        unique ``event_id`` (uuid — idempotent replay) onto ``event["data"]``, then
        persists one ``run_events`` row via the per-run scoped store before yielding
        the now-stamped event outward.

        ONE counter, ONE place (RESEARCH #4): there is NO second counter and NOTHING
        is stamped in ``ndjson_adapter`` (not the chokepoint). The persist is
        best-effort — the offline characterization harness has no ``workflow_runs``
        row (the ``run_events`` FK target), so a DB failure DEGRADES (logs a warning)
        and NEVER perturbs the deliverable bytes or the event multiset (INV-3). The
        ``seq``/``event_id`` keys are stripped from the 0A characterization multiset
        (``_VOLATILE_STRIP_KEYS``) so semantic-event parity holds.

        ``_execute_impl`` shares its per-run scoped store + run id with this wrapper
        via the ``_sink`` holder once ``owner_id``/``workspace_id`` are known.
        """
        sink = _RunEventSink()
        counter = itertools.count(1)
        async for event in self._execute_impl(
            agents=agents,
            user_message=user_message,
            pipeline_run_id=pipeline_run_id,
            pipeline_type=pipeline_type,
            cancel_event=cancel_event,
            user_id=user_id,
            session_id=session_id,
            attached_skills=attached_skills,
            attached_hooks=attached_hooks,
            model_id=model_id,
            od_context=od_context,
            gate_agent_ids=gate_agent_ids,
            parent_run_id=parent_run_id,
            model_overrides=model_overrides,
            _sink=sink,
        ):
            # Stamp exactly once, at the boundary, so seq is contiguous across the
            # nondeterministically-interleaved build loop. Events always carry a
            # "data" dict in this engine; guard defensively anyway.
            data = event.get("data")
            if not isinstance(data, dict):
                data = {}
                event["data"] = data
            seq = next(counter)
            event_id = str(uuid.uuid4())
            data["seq"] = seq
            data["event_id"] = event_id
            # Durable sink (best-effort — see docstring). Persist the now-stamped
            # event; a DB/FK failure must not break the live stream.
            await sink.persist(seq, event_id, event.get("type", ""), data)
            yield event

    async def _execute_impl(
        self,
        agents: list,
        user_message: str,
        pipeline_run_id: str,
        pipeline_type: str = "custom",
        cancel_event: asyncio.Event | None = None,
        user_id: str | None = None,
        session_id: str | None = None,
        attached_skills: list[dict] | None = None,
        attached_hooks: list[dict] | None = None,
        model_id: str | None = None,
        od_context: dict | None = None,
        gate_agent_ids: list[str] | None = None,
        parent_run_id: str | None = None,
        model_overrides: dict[str, str] | None = None,
        _sink: "_RunEventSink | None" = None,
    ) -> AsyncGenerator[dict, None]:
        """Execute a workflow end-to-end, yielding WebSocket events.

        Args:
            agents: list[AgentSpec] resolved from PIPELINE_AGENTS[pipeline_type].
            user_message: The user brief.
            pipeline_run_id: UUID for this run.
            pipeline_type: Pipeline type label.
            cancel_event: Optional cancellation signal.
            user_id: Authenticated user ID. Forwarded to the disk skill loader so
                     per-user SKILL.md overrides are honoured, and used as the DB
                     owner principal when present (``owner_id = user_id``). Also
                     keys the on-disk sandbox via ``disk_principal = user_id or
                     "anon"`` (UNCHANGED — byte-identity guard, D-09).
            session_id: D-09 anon-principal source. When ``user_id`` is None the DB
                     owner principal becomes ``f"anon:{session_id}"`` (AUTHZ-03 — a
                     real, per-session-isolated, never-None scoped subject). The WS
                     layer threads its ``chat_session_id`` here (websocket.py); this
                     is lower-risk than reusing ``pipeline_run_id`` because it gives
                     true per-session isolation (two runs in one session share the
                     anon owner; two different sessions do not). When BOTH are None
                     (a defensive/forward path with no session id) it falls back to
                     ``anon:{pipeline_run_id}`` so the owner is still never None.
                     NOTE: ``session_id`` is the DB-PRINCIPAL source ONLY — it NEVER
                     touches the on-disk sandbox key (see ``disk_principal``).
            attached_skills / attached_hooks: UI-attached extras.
            model_id: User-selected model override.
            od_context: For od_prototype/od_ppt — loaded template/design-system
                        content passed through to the factory `injects` composer.
            gate_agent_ids: Per-run selection of which agents pause for the
                        inter-agent Human review gate. The EXPLICIT set of agent
                        IDs to gate for this run.
                        - ``None`` (default / not specified) → fall back to the
                          STATIC set: agents whose AGENT.md declares
                          ``gate: Human_Gate``. This is exactly today's behavior,
                          so existing clients (which never send the field) are
                          unaffected.
                        - a list → gate iff ``spec.id`` is in that list (so a
                          statically-gated agent NOT in the list does NOT gate,
                          and a non-statically-gated agent IN the list DOES).
                        The Phase-6 UI sends this; the inter-agent gate itself
                        stays engine-level (`_run_review_gate`) — this only
                        selects which agents trigger it.
            parent_run_id: For ``prototype_revision`` — the pipeline_run_id of the
                        ORIGINAL run that produced the prototype being revised
                        (the frontend's ``source_workflow_run_id``, already
                        resolved by the WS layer). When set, the engine seeds the
                        parent run's ``spec.md`` / ``design.md`` / ``tasks.md``
                        (read from ``RunSandbox(<same user>, parent_run_id)`` — the
                        build wrote them there; sandboxes survive to the 48h TTL)
                        into this run's sandbox so the revision agent (and its
                        internal fix sub-agent) can consult the original
                        requirements + design system. Graceful degrade: a missing
                        / TTL-swept parent only logs a warning and proceeds on the
                        HTML + instruction. ``None`` (default) → no seeding, exactly
                        today's behavior.
        """
        total_start = time.time()
        # Per-run on-disk sandbox: <RUNS_ROOT>/<user>/<run>/. SHARED across every
        # agent in this pipeline run, so files (prototype.html, code-gen outputs)
        # written by one agent persist for the next. Keyed on pipeline_run_id so
        # create_runner(agent_id, ctx) — which roots its RunSandbox at
        # RunSandbox(ctx.user_id, ctx.run_id) — lands in this SAME directory and
        # the engine reads its deliverables back from disk.
        # ── Byte-identity guard (D-09 / CTX-05): the on-disk principal is DECOUPLED ──
        # from the DB owner principal. disk_principal stays ``user_id or "anon"`` — the
        # SAME value RunSandbox keyed disk with before 05-04 — so anon runs' sandbox paths
        # are byte-identical and the 0A snapshots hold. owner_id (the DB principal, below)
        # may be ``anon:<session_id>`` for anon runs; it must NEVER reach a disk key.
        disk_principal = user_id or "anon"
        sandbox = RunSandbox(disk_principal, pipeline_run_id)
        sandbox.ensure()
        # ── DB owner principal (AUTHZ-03 / D-09): always a real, non-None scoped subject ──
        # ``user_id`` when authenticated; otherwise ``anon:<session_id>`` (true per-session
        # isolation), falling back to ``anon:<pipeline_run_id>`` when no session id was
        # threaded (defensive — owner_id must never be None for the default-deny filter).
        owner_id = user_id or f"anon:{session_id or pipeline_run_id}"
        # ── Per-run state: ONE ExecutionContext, threaded explicitly (CTX-01/CTX-02) ──
        # Construct the per-run value object immediately after the sandbox so NO per-run
        # datum is stashed on the ExecutionEngine singleton (the INV-2 concurrency
        # hazard). owner_id is the DB principal (above); disk_principal is the decoupled
        # byte-identity-guard principal (above). Run state previously written to self._*
        # now lives on `ectx`, threaded down through the call tree (D-03, explicit param —
        # never contextvars). gate_agent_ids selection (None ⇒ static AGENT.md
        # `gate: Human_Gate` set; a list ⇒ exactly those ids) and parent_run_id
        # (prototype_revision parent-seed source) ride on the context too. ctx.artifacts is
        # the per-run typed graph (default_factory=ArtifactGraph — 05-04 dual-write target).
        ectx = ExecutionContext(
            run_id=pipeline_run_id,
            owner_id=owner_id,
            disk_principal=disk_principal,
            od_context=od_context,  # threaded into AgentContext per agent
            gate_agent_ids=gate_agent_ids,
            parent_run_id=parent_run_id,
            cancel_event=cancel_event,
        )
        # Seed the validated per-agent override map (Phase 6 D-07/D-08, MODEL-03).
        # Already allow-list-validated at the WS ingress (websocket.py
        # _validate_model_overrides) — the engine trusts the carried map. Default
        # {} when absent (the only kind today) so the resolver's override tier is a
        # no-op and INV-3 parity holds. Persisted as ``or None`` below ({} → NULL).
        ectx.model_overrides = model_overrides or {}

        # ── Scoped store + default workspace + capabilities (D-04/D-06/CAPRUN-01) ──────
        # The single default-deny scoped store helper (agents.authz.ScopedStore) is the
        # one enforced read/write path for the typed substrate. Constructed with the DB
        # owner principal; the workspace id is set right after create_workspace returns it.
        # create_workspace(run_id) inserts the per-run default ``workspaces`` row and
        # returns its id → ctx.workspace_id (D-04). record_capabilities(run_id,
        # runtime=langchain_deepagents) inserts EXACTLY ONE run_capabilities row at entry
        # (CAPRUN-01/D-12 — INV-13: every agent runs on LangChain deepagents). Both are
        # best-effort: the offline characterization harness has no workflow_runs row (the
        # run_capabilities/run_events FK target), so a DB failure here must DEGRADE (log a
        # warning) and NEVER perturb the deterministic deliverable or the event stream
        # (INV-3). For real runs (the WS layer creates the workflow_runs row first) these
        # persist normally.
        scoped_store = ScopedStore(owner_id=owner_id)
        try:
            ectx.workspace_id = await scoped_store.create_workspace(pipeline_run_id)
            scoped_store._workspace_id = ectx.workspace_id  # stamp later writes
            await scoped_store.record_capabilities(
                pipeline_run_id,
                runtime="langchain_deepagents",
                # D-08: persist the validated overrides at entry. ``or None`` so an
                # empty {} (every run today) persists as SQL NULL — INV-3 row parity
                # with legacy/no-override rows (never a spurious non-null {} write).
                model_overrides=(ectx.model_overrides or None),
            )
        except Exception as _scope_exc:  # noqa: BLE001 — never break a run on DB persist
            # WR-02: degrade ONLY the offline-harness DB condition (no schema →
            # SQLAlchemyError); a non-DB exception is a real bug → re-raise so it
            # is not masked as a silent no-op.
            from sqlalchemy.exc import SQLAlchemyError

            if not isinstance(_scope_exc, SQLAlchemyError):
                raise
            logger.warning(
                "execute(): workspace/capabilities persist failed (%s) — proceeding "
                "(typed-substrate DB writes degrade; deliverable/events unaffected)",
                _scope_exc,
            )
        # Thread the scoped store onto the context so the seq sink and the typed
        # dual-write reuse the SAME owner+workspace-scoped helper.
        ectx.scoped_store = scoped_store
        # Arm the durable run_events sink (PERSIST-03): hand the public execute()
        # wrapper this run's scoped store + run id so it can persist every stamped
        # event. Done HERE (not in the wrapper) because owner_id/workspace_id are only
        # known after the entry wiring above.
        if _sink is not None:
            _sink.arm(scoped_store, pipeline_run_id)

        # ── Durable graph state: acquire the LangGraph checkpointer once per run ──
        # get_checkpointer() is a process-wide CACHED SINGLETON (see
        # app/agents/checkpointer.py): Postgres (AsyncPostgresSaver, owning a pool
        # + .setup() table bootstrap) when DATABASE_URL is postgres, else an
        # InMemorySaver dev fallback (no creds, no error). Because it is shared for
        # the whole process, we acquire it here and thread it into every agent's
        # create_runner — but we DELIBERATELY DO NOT close it per-run:
        # close_checkpointer() tears down the shared pool/instance for the entire
        # process (it sets the module singleton back to None), so closing it after
        # one run would break every later run and is an app-SHUTDOWN concern, not a
        # per-run one (the checkpointer.py docstring: "Wire get_checkpointer on
        # startup and close_checkpointer on shutdown"). Each agent-invocation still
        # gets its OWN unique thread_id below so per-agent graph states never
        # collide on this shared checkpointer; the disk sandbox stays per-run/shared.
        from app.agents.checkpointer import get_checkpointer
        ectx.checkpointer = await get_checkpointer()

        # ── Cumulative prototype task-completion list (run-level, run-shared) ──
        # RESTORES the pre-cutover semantics of PrototypeArtifactStore, which was
        # created ONCE per run and shared across every prototype-build invocation,
        # so report_task_complete calls ACCUMULATED across tasks. After the Phase-3
        # cutover, task_progress is derived from report_task_complete tool events in
        # _run_agent; that list MUST live here (run-level) — not as a local inside
        # _run_agent — because _run_build_task_loop calls _run_agent fresh ONCE PER
        # TASK. A local list resets every task, so completed_count would be stuck at
        # 1 and the frontend's protoCompletedTaskCount would go non-monotonic
        # (0,1,1,1,2,1) instead of cumulative/monotonic (0,1,1,2,2,3) — a visible
        # build-progress UI regression. Lives on the per-run context
        # (ectx.completed_tasks, [] by default_factory), appended in _run_agent,
        # emitted as completed_count=len(ectx.completed_tasks).

        # ── Prototype revision: seed the existing prototype as an editable file ──
        # DELIBERATE EXCEPTION to the revision pattern used elsewhere. Every other
        # revision pipeline (ppt/user_stories/app_builder) follows
        # "existing artifact in the message → agent regenerates the COMPLETE
        # artifact → engine takes the output". Prototype revision instead does a
        # real coding-agent edit loop: the agent edits prototype.html in place via
        # read_file/edit_file/write_file. This is chosen on purpose because a
        # prototype is a single 60-100k char HTML file where surgical edits are
        # far more reliable than re-emitting the whole document (the old approach
        # here — a regex-merged structured diff — silently dropped edits to
        # existing in-page JS such as the SPA route map). We drop the current HTML
        # into the sandbox and slim the prompt to just the instruction + a
        # pointer, so the document isn't also duplicated into the agent's context.
        # Phase-5 revision state consumed by the post-revision fix-loop (below,
        # just before the read-back). The ExecutionContext already carries safe
        # defaults (ectx.revision_original_html="", ectx.revision_instruction=None,
        # ectx.revision_baseline_static/console=set()) so the fix-loop degrades to a
        # no-baseline / no-instruction run (or is skipped) when this is not a
        # prototype_revision, or when no existing HTML was found.
        #   ectx.revision_instruction      — the user's revision request, re-injected
        #                                     into the fix prompt (None ⇒ build-style
        #                                     wording; we set it to the slimmed message
        #                                     as a fallback so it's never None here).
        #   ectx.revision_baseline_static  — static-issue signatures of the seeded
        #                                     ORIGINAL prototype.html (pre-edit), so
        #                                     the fix-loop only treats NEW static
        #                                     issues as regressions.
        #   ectx.revision_baseline_console — console-error signatures of that same
        #                                     pre-edit render (empty when render is
        #                                     unavailable).
        if pipeline_type == "prototype_revision":
            existing_html = self._extract_existing_prototype_html(user_message)
            if existing_html:
                ectx.revision_original_html = existing_html
                sandbox.write(REVISION_FILE_NAME, existing_html)

                # ── Capture the user's revision instruction (for the fix prompt) ──
                # The frontend wraps it as
                #   === REVISION REQUEST ===\n{instruction}\n=== END REQUEST ===
                # Extract it verbatim; fall back to the slimmed user_message if the
                # markers are absent so the fix prompt always has SOMETHING to
                # re-inject (the slimmed message still contains the request).
                _req_match = re.search(
                    r"=== REVISION REQUEST ===\s*([\s\S]*?)\s*=== END REQUEST ===",
                    user_message, re.IGNORECASE,
                )
                user_message = self._slim_revision_message(user_message)
                ectx.revision_instruction = (
                    _req_match.group(1).strip() if _req_match else user_message
                )

                # ── Seed the parent run's spec.md / design.md / tasks.md ──────────
                # The original build wrote these to its OWN run sandbox
                # (RunSandbox(<user>, parent_run_id)) and sandboxes survive to the
                # 48h TTL (no run-end cleanup), so we can read them back and copy
                # them into THIS revision sandbox — giving the revision agent (and
                # its internal fix sub-agent) the original requirements + design
                # system via read_file. Build the parent sandbox the SAME way the
                # engine built its own (line above: RunSandbox(user_id or "anon",
                # pipeline_run_id)) but keyed on parent_run_id. Graceful degrade:
                # ANY failure (no parent_run_id, TTL-swept dir, unreadable file)
                # only logs a warning — a missing parent must never break a revision.
                if parent_run_id:
                    # ── L16 ownership gate (AUTHZ-02 / INV-8) — BEFORE the try ───────
                    # An owner may only seed from a parent run it OWNS. The relocated
                    # ScopedStore.assert_owns (D-07) is now a REAL store lookup: it reads
                    # the parent run's TRUE owner_id from the DB and raises PermissionError
                    # on a cross-owner mismatch (the Phase-2 by-convention parent_owner_id
                    # argument is gone). The PermissionError PROPAGATES OUT of execute()
                    # (re-raised below) — it must NOT be swallowed: a cross-owner parent
                    # is never silently seeded (Highest-Risk Behavior 4 — L16 must not
                    # regress). Any OTHER error (a DB outage / an offline run whose schema
                    # predates the owner_id column) degrades like a missing/TTL-swept
                    # parent — the prior pure-predicate seam never touched the DB, so a
                    # store-lookup failure must NOT newly break a revision (CTX-05 parity).
                    try:
                        await ectx.scoped_store.assert_owns(parent_run_id)
                    except PermissionError:
                        raise  # cross-owner denial — propagate (L16)
                    except Exception as _authz_exc:  # noqa: BLE001 — DB/schema → degrade
                        logger.warning(
                            "prototype_revision: assert_owns store lookup failed for "
                            "parent %s (%s) — degrading to same-owner seed (CTX-05 parity)",
                            parent_run_id, _authz_exc,
                        )
                    try:
                        parent_sb = RunSandbox(ectx.disk_principal, parent_run_id)
                        seeded: list[str] = []
                        for _name in ("spec.md", "design.md", "tasks.md"):
                            try:
                                _content = parent_sb.read(_name)
                            except Exception as _read_exc:  # noqa: BLE001
                                logger.warning(
                                    "prototype_revision: could not read parent %s "
                                    "(%s) — skipping",
                                    _name, _read_exc,
                                )
                                continue
                            if _content:
                                sandbox.write(_name, _content)
                                seeded.append(_name)
                        logger.info(
                            "prototype_revision: seeded parent reference files "
                            "from run %s: %s",
                            parent_run_id, ", ".join(seeded) or "(none found)",
                        )
                    except Exception as _seed_exc:  # noqa: BLE001 — never break a revision
                        logger.warning(
                            "prototype_revision: parent reference seeding from run "
                            "%s failed (%s) — proceeding on HTML + instruction only",
                            parent_run_id, _seed_exc,
                        )

                # ── Baseline on the seeded ORIGINAL prototype.html (PRE-edit) ─────
                # Compute static + render signatures of the prototype BEFORE the
                # revision agent edits it, using the SAME T1 module-level helpers
                # the fix-loop uses — so the signatures line up and the fix-loop
                # treats only NEW static/console issues as regressions (hard
                # render-breakage is always fixed regardless of baseline). Render
                # is best-effort: an unavailable/erroring Chromium yields an empty
                # console baseline (a skipped render contributes no signatures),
                # exactly as _console_sigs handles it.
                from app.agents.static_check import static_check
                _orig_path = sandbox.path_for(REVISION_FILE_NAME)
                _sres0 = static_check(_orig_path)
                ectx.revision_baseline_static = _static_issue_sigs(_sres0)
                try:
                    from app.agents.render_check import render_check
                    _rres0 = await render_check(_orig_path)
                except Exception as _render_exc:  # noqa: BLE001 — render unavailable ⇒ no baseline
                    logger.warning(
                        "prototype_revision: baseline render_check raised (%s) — "
                        "treating as unavailable (no console baseline)",
                        _render_exc,
                    )
                    from app.agents.render_check import RenderResult
                    _rres0 = RenderResult(
                        ok=True, available=False,
                        note=f"render_check error: {_render_exc}",
                    )
                ectx.revision_baseline_console = _console_sigs(_rres0)
                logger.info(
                    "prototype_revision: pre-edit baseline — %d static issue(s), "
                    "%d console error(s)",
                    len(ectx.revision_baseline_static),
                    len(ectx.revision_baseline_console),
                )
            else:
                logger.warning(
                    "prototype_revision: no existing HTML found in request — "
                    "agent will work from the prompt only"
                )

        # Load per-user disk skills for all agents (user → global → built-in).
        # Honours per-user SKILL.md overrides — replicates the behaviour of the
        # former WorkflowOrchestrator._load_skills (WORKFLOWS.md §B6).
        ectx.disk_skills = self._load_disk_skills(agents, user_id)

        # ── Step 1: Validate the DAG ──────────────────────────────────────
        validation = self._resolver.validate(agents)
        yield {
            "type": "workflow_validated",
            "data": {
                "pipeline_run_id": pipeline_run_id,
                "satisfiable": validation.satisfiable,
                "dag_edges": [
                    {"from": e.from_agent_id, "to": e.to_agent_id, "artifact_type": e.artifact_type}
                    for e in validation.edges
                ],
                "unresolved_edges": [
                    {"consuming_agent_id": u.consuming_agent_id, "artifact_type": u.artifact_type}
                    for u in validation.unresolved_edges
                ],
                "timestamp": _now(),
            },
        }
        if not validation.satisfiable:
            yield {
                "type": "error",
                "data": {
                    "error": "Workflow DAG is unsatisfiable: " + "; ".join(validation.errors),
                    "code": "workflow_unsatisfiable",
                    "recoverable": False,
                },
            }
            return

        ordered_agents = validation.dag or list(agents)

        # ── Routing seam: compile the CompiledWorkflow this run executes from ──
        # (MAN-04/MAN-05). Resolve the legacy `pipeline_type` label to a manifest
        # id, load + compile that manifest, and source the FOUR routing concerns
        # from the compiled plan below: (1) the agent sequence/ids, (2) the
        # deliverable spec, (3) the clarify defaults, (4) the planner-skip flag.
        # No legacy `pipeline_type` dispatch fallback (INV-12).
        compiled = compile_for_run(pipeline_type)

        # ── Model resolution seam (Phase 6 / MODEL-01/02/05) ──────────────────────────
        # Construct the per-run ModelResolver ONCE, here — after the workflow is compiled
        # so ``compiled.model`` (CompiledWorkflow.model — the workflow default, tier 4) is
        # available — and carry it on ``ectx.model_resolver``. The three _run_agent model
        # sites consult it for the effective per-agent id by the D-02 precedence
        # (override > step.model > AgentSpec.model > workflow.model > session model_id or
        # Haiku). Seeds: ``ectx.model_overrides`` (validated {agent_id→model_id}; defaults
        # {} this plan, 06-04 wires the WS ingress), ``compiled.model`` (workflow default —
        # None today), the run-wide session ``model_id`` (the existing param — UNCHANGED),
        # and the global Haiku default ``settings.BEDROCK_INFERENCE_PROFILE_ID``.
        # ★ INV-3 PARITY: with model_overrides={} and every manifest/agent tier None (today's
        # state), resolve() returns ``session model_id or Haiku`` == exactly today's
        # ``model_id`` input to build_model — so the characterization snapshots are unchanged.
        from app.core.config import settings as _settings

        ectx.model_resolver = ModelResolver(
            model_overrides=ectx.model_overrides,
            workflow_model=compiled.model,
            session_model_id=model_id,
            haiku_default=_settings.BEDROCK_INFERENCE_PROFILE_ID,
            catalog=ModelCatalog(),
        )

        # (1) Agent sequence/ids — the compiled plan is the SOURCE of the agent
        # MEMBERSHIP for this run. The manifests are authored in the registry's
        # membership order (get_pipeline_agents / PIPELINE_AGENTS — coverage test
        # in 04-03), which is the engine's canonical agent list. The actual
        # EXECUTION order stays the resolver's topo-sorted DAG (validation.dag,
        # unchanged below — byte-identical), which may reorder contract-coupled
        # agents (e.g. the code-gen pipelines). So we assert the compiled plan's
        # step set/order matches the registry MEMBERSHIP source, not validation.dag
        # — any manifest/registry drift fails LOUDLY here rather than silently
        # diverging from the agents the engine drives (RESEARCH Pitfall 3). `ppt`
        # agents declare pipeline_type: od_ppt so get_pipeline_agents("ppt") is
        # empty; fall back to PIPELINE_AGENTS[id] there (mirrors the coverage
        # test). `reverse_engineer` (empty plan) / `chat` (ChatRunner) never reach
        # execute(), so a populated compiled plan is expected for every run here.
        from agents.registry import PIPELINE_AGENTS, get_pipeline_agents

        _compiled_agent_ids = [s.agent_id for s in compiled.steps]
        _registry_specs = get_pipeline_agents(compiled.id)
        _membership_ids = (
            [a.id for a in _registry_specs]
            if _registry_specs
            else list(PIPELINE_AGENTS.get(compiled.id, []))
        )
        if _compiled_agent_ids and _compiled_agent_ids != _membership_ids:
            raise RuntimeError(
                "compiled plan step order does not match the registry agent "
                f"membership for '{pipeline_type}' (manifest id "
                f"'{compiled.id}'): plan={_compiled_agent_ids} "
                f"registry={_membership_ids}"
            )

        # Persist custom workflow definition (T061, FR-013)
        await self._persist_workflow_definition(
            user_id=user_id,
            pipeline_type=pipeline_type,
            agents=ordered_agents,
            validation_result=validation,
        )

        # ── Step 2: Run the Deep_Planner_Agent (gate) ─────────────────────
        self._state_machine.transition(pipeline_run_id, "planning")
        _log_event("workflow_run_created", pipeline_run_id, pipeline_type=pipeline_type)

        # ── Planner-skip routing concern — sourced from the compiled plan ──
        # (MAN-04, concern 4). The planner-skip flag now comes from
        # `compiled.planner` ("run" | "skip"), NOT from the legacy
        # `SKIP_PLANNER_FOR_PROTOTYPE and is_prototype_pipeline(...)` computation.
        # Every dispatchable manifest declares `planner: run` (because the live
        # SKIP_PLANNER_FOR_PROTOTYPE is False today — RESEARCH Pitfall 1), so
        # `skip_planner` is False for every run and behavior is byte-identical:
        # the planner/clarifier runs for every pipeline exactly as before.
        skip_planner = compiled.planner == "skip"

        if skip_planner:
            logger.info("Prototype pipeline (Approach 2+3): skipping planner + clarifier")
            planning_context = self._default_planning_context(user_message)
            planning_context["pipeline_type"] = pipeline_type
            gate_verdict = "PROCEED"
            # Don't emit planner events — no overlay, no flash
        else:
            # Emit planner_start BEFORE running the planner so the frontend
            # can show a "planning…" overlay immediately.
            yield {
                "type": "planner_start",
                "data": {"pipeline_run_id": pipeline_run_id, "pipeline_type": pipeline_type, "timestamp": _now()},
            }

            planner_start_ms = time.time() * 1000
            planning_context, gate_verdict = await self._run_planner(
                user_message, pipeline_run_id, model_id, cancel_event, pipeline_type,
                ectx=ectx,
            )

            # Human-in-the-loop override: force clarification on every run.
            if ALWAYS_CLARIFY and gate_verdict != "CLARIFY_REQUIRED":
                logger.info("ALWAYS_CLARIFY=True — overriding gate verdict PROCEED → CLARIFY_REQUIRED")
                gate_verdict = "CLARIFY_REQUIRED"
                planning_context["execution_gate"] = "CLARIFY_REQUIRED"
                if not planning_context.get("missing_information"):
                    has_topic = planning_context.get("has_topic", True)
                    # ── Clarify-defaults routing concern — sourced from the
                    # compiled plan (MAN-04, concern 3). The per-pipeline default
                    # clarifying-question list now comes from
                    # `compiled.clarify.defaults` (which reproduces the engine's
                    # former `_pipeline_defaults` dict verbatim, with revisions /
                    # edge ids falling to the `custom` list), NOT from a hardcoded
                    # dict keyed by pipeline_type. `od_prototype` resolves to the
                    # `prototype` manifest whose defaults equal the former
                    # `_pipeline_defaults["od_prototype"]`, so behavior is
                    # byte-identical.
                    defaults = list(compiled.clarify.defaults)
                    if not has_topic:
                        defaults = ["topic"] + defaults
                    planning_context["missing_information"] = defaults
                    logger.info(
                        "ALWAYS_CLARIFY: seeding defaults has_topic=%s pipeline=%s: %s",
                        has_topic, pipeline_type, defaults
                    )

            _log_event(
                "planner_complete", pipeline_run_id,
                duration_ms=(time.time() * 1000 - planner_start_ms),
                gate_verdict=gate_verdict,
            )

            # Auto-generate PLANNER.md per run (T082)
            if planning_context and not planning_context.get("planner_timed_out"):
                try:
                    planner_md_lines = ["# PLANNER.md — Deep Planner Analysis\n"]
                    if planning_context.get("inferred_intent"):
                        planner_md_lines.append(f"**Inferred Intent**: {planning_context['inferred_intent']}\n")
                    if planning_context.get("topic"):
                        planner_md_lines.append(f"**Topic**: {planning_context['topic']}\n")
                    if planning_context.get("execution_gate"):
                        planner_md_lines.append(f"**Gate Verdict**: {planning_context['execution_gate']}\n")
                    if planning_context.get("explicit_constraints"):
                        planner_md_lines.append("\n**Explicit Constraints**:\n" +
                            "\n".join(f"- {c}" for c in planning_context["explicit_constraints"]))
                    if planning_context.get("implicit_constraints"):
                        planner_md_lines.append("\n**Implicit Constraints**:\n" +
                            "\n".join(f"- {c}" for c in planning_context["implicit_constraints"]))
                    if planning_context.get("quality_targets"):
                        planner_md_lines.append("\n**Quality Targets**:\n" +
                            "\n".join(f"- {q}" for q in planning_context["quality_targets"]))
                    if planning_context.get("inferred_personas"):
                        planner_md_lines.append("\n**Inferred Personas**:\n" +
                            "\n".join(f"- {p}" for p in planning_context["inferred_personas"]))
                    if planning_context.get("inferred_nfrs"):
                        planner_md_lines.append("\n**Non-Functional Requirements**:\n" +
                            "\n".join(f"- {n}" for n in planning_context["inferred_nfrs"]))
                    if planning_context.get("domain_insights"):
                        planner_md_lines.append("\n**Domain Insights**:\n" +
                            "\n".join(f"- {i}" for i in planning_context["domain_insights"]))
                    sandbox.write("PLANNER.md", "\n".join(planner_md_lines))
                except Exception as _planner_md_exc:
                    logger.debug("PLANNER.md generation failed: %s", _planner_md_exc)
            async for event in self._emit_planner_events(
                pipeline_run_id, pipeline_type, planning_context, gate_verdict
            ):
                yield event

        # ── Step 3: Gate routing ──────────────────────────────────────────
        if gate_verdict == "CLARIFY_REQUIRED":
            self._state_machine.transition(pipeline_run_id, "clarifying")
            from agents.execution_engine.clarify_engine import ClarifyEngine

            clarify = ClarifyEngine()

            # Use a Queue so ClarifyEngine events (questionnaire_ready, etc.)
            # are streamed to the client in real-time while clarify.run()
            # is suspended at event.wait(). The previous _ws_collect pattern
            # buffered events and only yielded them AFTER clarify.run() returned
            # — which meant questionnaire_ready was never sent until after the
            # user had already answered (impossible: they couldn't see questions).
            event_queue: asyncio.Queue[dict | None] = asyncio.Queue()

            async def _ws_send(event: dict) -> None:
                await event_queue.put(event)

            self._state_machine.transition(pipeline_run_id, "waiting_for_user")

            # Run clarify.run() as a background task so we can yield its
            # events concurrently from the queue.
            clarify_task = asyncio.create_task(
                clarify.run(
                    pipeline_run_id,
                    planning_context,
                    _ws_send,
                    owner_id=ectx.owner_id,
                    workspace_id=ectx.workspace_id,
                )
            )

            # Drain the queue until clarify_task completes
            while not clarify_task.done():
                try:
                    event = await asyncio.wait_for(event_queue.get(), timeout=1.0)
                    if event is not None:
                        yield event
                except asyncio.TimeoutError:
                    continue

            # Drain any remaining events after task completion
            while not event_queue.empty():
                event = event_queue.get_nowait()
                if event is not None:
                    yield event

            # Get the updated planning_context from the completed task
            try:
                planning_context = clarify_task.result()
            except Exception as _clarify_exc:
                logger.warning("ClarifyEngine failed: %s — proceeding with original context", _clarify_exc)

        # ── Step 4: Run domain agents ─────────────────────────────────────
        self._state_machine.transition(pipeline_run_id, "generating")

        yield {
            "type": "pipeline_start",
            "data": {
                "pipeline_type": pipeline_type,
                "pipeline_run_id": pipeline_run_id,
                "agent_count": len(ordered_agents),
                "agents": [
                    {"id": s.id, "name": s.name, "role": s.role, "icon": s.icon,
                     "order": getattr(s, "order", 0)}
                    for s in ordered_agents
                ],
            },
        }

        results: list[dict] = []

        try:
            for i, spec in enumerate(ordered_agents):
                if cancel_event and cancel_event.is_set():
                    logger.info("Workflow cancelled before agent %s", spec.id)
                    break

                # ── Task-loop agents: call repeatedly until all tasks done ──
                # The prototype-build agent executes one task per call.
                # We call it N times (once per task) so each call is small
                # and focused — never runs out of tokens filling all pages.
                if getattr(spec, "id", None) == "prototype-build":
                    async for event in self._run_build_task_loop(
                        spec, i, ordered_agents, user_message,
                        sandbox, pipeline_run_id, pipeline_type, planning_context,
                        attached_skills, attached_hooks, model_id, results, cancel_event,
                        ectx,
                    ):
                        yield event
                else:
                    async for event in self._run_agent(
                        spec, i, ordered_agents, user_message,
                        sandbox, pipeline_run_id, pipeline_type, planning_context,
                        attached_skills, attached_hooks, model_id, results, cancel_event,
                        ectx,
                    ):
                        yield event

        except asyncio.CancelledError:
            self._state_machine.transition(pipeline_run_id, "cancelled")
            yield {"type": "pipeline_cancelled", "data": {"pipeline_run_id": pipeline_run_id}}
            raise

        # ── Step 5: Pipeline complete ─────────────────────────────────────
        # Guard: if the run was already cancelled (e.g. user rejected a review
        # gate), don't try to transition to "completed" — that would throw a
        # StateMachineError because "cancelled" is a terminal state.
        current_state = self._state_machine.get_state(pipeline_run_id)
        if current_state not in ("cancelled", "failed"):
            self._state_machine.transition(pipeline_run_id, "completed")

        # Determine the final deliverable below, by pipeline class, via
        # _resolve_final_output (prototype.html for prototype/revision; serialized
        # sandbox for code-gen; streamed+unwrapped output for text/PPT). The
        # revision branch first runs the post-revision validation fix-loop.

        # ── Prototype revision: programmatic post-revision validation + fix ──────
        # After the visible prototype-revision-agent has edited prototype.html, run
        # the generalized (T1) Both-validation + bounded INTERNAL fix-loop on the
        # revision sandbox BEFORE reading the file back as the deliverable. With the
        # pre-edit baseline (computed in the seeding block above) the fix-loop fixes
        # only NEW static/console regressions PLUS hard render-breakage (page
        # errors, dead nav, blank render), re-injecting the user's instruction and
        # leaving pre-existing nits alone. This is NON-YIELDING: the fix sub-agent's
        # stream is consumed internally (it persists prototype.html to disk as a
        # side effect) and NOTHING is re-emitted — the WS/UI event contract is
        # byte-identical (no new events). It NEVER aborts the revision (try/except),
        # and only runs when the agent actually produced a prototype.html.
        if (
            pipeline_type == "prototype_revision"
            and sandbox.path_for("prototype.html").is_file()
        ):
            try:
                # Mirror _run_agent's AgentContext construction for the SAME agent:
                #  - disk-skill merge keyed on the literal agent id (== spec.id),
                #  - agent_outputs={} (prototype-revision-agent declares consumes:[]
                #    so _filter_consumed_outputs returns {} — set directly here),
                #  - run_id=pipeline_run_id + user_id=ectx.disk_principal so create_runner
                #    (inside the fix-loop) roots the fix sub-agent's RunSandbox at
                #    RunSandbox(ctx.user_id or "anon", ctx.run_id) — the SAME revision
                #    dir holding prototype.html — so its edits are NOT lost. Byte-identity
                #    guard (D-09): pass disk_principal (== user_id or "anon"), NOT owner_id
                #    (which may be anon:<session_id>), so the disk path is unchanged.
                _rev_skills: list[dict] = list(attached_skills or [])
                _disk_skills = ectx.disk_skills
                if "prototype-revision-agent" in _disk_skills:
                    _rev_skills.append({"content": _disk_skills["prototype-revision-agent"]})
                rev_ctx = AgentContext(
                    user_request=user_message,
                    agent_outputs={},
                    attached_skills=_rev_skills,
                    attached_hooks=list(attached_hooks or []),
                    # MODEL-01/02/05: resolved id for the revision fix sub-agent (reuses this
                    # agent's spec — RESEARCH). step=None this plan; parity-identical to
                    # ``model_id`` when no override/manifest model is set (INV-3).
                    model=self._resolve_model(ectx, spec, model_id),
                    od_context=ectx.od_context,
                    planning_context=planning_context,
                    user_id=ectx.disk_principal,
                    run_id=pipeline_run_id,
                )
                await self._run_validation_fix_loop(
                    ctx=rev_ctx,
                    sandbox=sandbox,
                    pipeline_run_id=pipeline_run_id,
                    task_num=1,
                    total_tasks=1,
                    cancel_event=cancel_event,
                    agent_id="prototype-revision-agent",
                    baseline_static=ectx.revision_baseline_static,
                    baseline_console=ectx.revision_baseline_console,
                    user_instruction=ectx.revision_instruction,
                    label="revision",
                    checkpointer=ectx.checkpointer,
                )
            except Exception as exc:  # noqa: BLE001 — never let validation abort the revision
                logger.warning(
                    "prototype_revision: post-revision validation errored (%s) — continuing",
                    exc,
                )

        # ── Deliverable routing concern — declared by the compiled plan ─────────
        # (MAN-04, concern 2). The deliverable resolver NAME for this run is
        # declared on `compiled.deliverable.strategy` (e.g. single_file /
        # serialized_sandbox / streamed_text / ppt), sourced from the manifest +
        # validated against the CapabilityRegistry at compile time. In 1A the
        # actual byte-resolution still flows through the behavioral
        # `_resolve_final_output` chooser (allow-listed, Phase-7-scoped): the
        # concrete resolver impls that consume this declared name land with the
        # capability impls in Phase 7. The spec is bound here so the routing
        # concern is genuinely sourced from the compiled plan, not the legacy dict.
        # Logged (not emitted as an event) so the semantic-event multiset stays
        # byte-identical (INV-3) while the sourced concern is observably consumed.
        logger.debug(
            "deliverable routing concern (compiled): pipeline=%s manifest=%s "
            "resolver=%s name=%s",
            pipeline_type,
            compiled.id,
            compiled.deliverable.strategy,
            compiled.deliverable.name,
        )

        # ── Resolve the deliverable (WorkflowRun.output) by pipeline class ──────
        # Single source of truth: _resolve_final_output reads prototype.html for
        # prototype / od_prototype / revision, serializes the sandbox for code-gen,
        # and uses the streamed output (with <artifact> unwrapped) for text/PPT. So
        # the build's reference scaffolding (spec.md/design.md/tasks.md) can never be
        # serialized into the output, and design.md's <artifact> example can never be
        # mis-extracted as the deliverable.
        final_output = _resolve_final_output(
            pipeline_type,
            sandbox,
            results,
            revision_original_html=ectx.revision_original_html,
        )

        # ── PPT carousel deck: strip slide-hiding CSS the composer may hallucinate ──
        # A horizontal-carousel deck navigates by translating .stage; rules like
        # `.slide:not(.active){display:none}` remove slides 2..N so only slide 1 shows.
        # Deterministic backstop scoped strictly to ppt/od_ppt (never prototype HTML).
        if pipeline_type in _PPT_PIPELINE_TYPES and final_output:
            final_output = _sanitize_carousel_deck_html(final_output)

        # (Prototype revisions are now produced by the agent editing
        # prototype.html in the workspace directly — see the output-capture
        # block above. The legacy REVISION_DIFF regex-merge has been removed.)
        # Token totals for the frontend TokenUsageSummary card. The client RESETS
        # its running totals on pipeline_complete, so they must be present here for
        # EVERY pipeline (otherwise the card hides itself). Pricing matches the
        # per-run persistence in websocket.py (Haiku: $0.25/M in, $1.25/M out).
        from app.core.config import settings as _settings
        _tok_in = sum(r.get("input_tokens", 0) or 0 for r in results)
        _tok_out = sum(r.get("output_tokens", 0) or 0 for r in results)
        yield {
            "type": "pipeline_complete",
            "data": {
                "pipeline_type": pipeline_type,
                "pipeline_run_id": pipeline_run_id,
                "total_duration": round(time.time() - total_start, 2),
                "agents_completed": len(results),
                "agents_total": len(ordered_agents),
                "final_output": final_output,
                "total_input_tokens": _tok_in,
                "total_output_tokens": _tok_out,
                "total_tokens": _tok_in + _tok_out,
                "estimated_cost_usd": round((_tok_in * 0.00000025) + (_tok_out * 0.00000125), 6),
                "model_id": model_id or _settings.BEDROCK_INFERENCE_PROFILE_ID,
            },
        }

    # ------------------------------------------------------------------
    # Deep Planner
    # ------------------------------------------------------------------

    async def _run_planner(
        self,
        user_message: str,
        pipeline_run_id: str,
        model_id: str | None,
        cancel_event: asyncio.Event | None,
        pipeline_type: str = "custom",
        ectx: ExecutionContext | None = None,
    ) -> tuple[dict, str]:
        """Run the Deep_Planner_Agent with a timeout. Returns (planning_context, gate)."""
        try:
            planning_context = await asyncio.wait_for(
                self._invoke_planner(user_message, model_id, pipeline_type),
                timeout=PLANNER_TIMEOUT_SECONDS,
            )
            gate = planning_context.get("execution_gate", "PROCEED")
            # Persist the planning_context as a typed ArtifactRef in artifact_refs
            # (PERSIST-02 — migrated off the thin store in 05-06). visibility="workspace"
            # so a later same-owner revision (_handle_revision cross-run read) resolves
            # it through the owner+visibility scope filter. Best-effort: a DB persist
            # failure degrades (log) and never breaks the run — same shape as
            # _dual_write_artifact (the offline characterization harness has no
            # workflow_runs FK row).
            if ectx is not None:
                await self._dual_write_artifact(
                    ectx,
                    producer_agent=PLANNER_AGENT_ID,
                    producer_step="planner",
                    content=json.dumps(planning_context),
                    kind="planning_context",
                    location="artifact_refs/planning_context",
                    visibility="workspace",
                )
            return planning_context, gate
        except asyncio.TimeoutError:
            logger.warning("Deep planner timed out — defaulting to PROCEED")
            return self._default_planning_context(user_message, timed_out=True), "PROCEED"
        except Exception as exc:
            logger.exception("Deep planner failed — defaulting to PROCEED")
            ctx = self._default_planning_context(user_message)
            ctx["planner_error"] = str(exc)
            return ctx, "PROCEED"

    async def _invoke_planner(self, user_message: str, model_id: str | None, pipeline_type: str = "custom") -> dict:
        """Invoke the SmartPlanner — single structured LLM call, 2-5 seconds."""
        from agents.planner.smart_planner import SmartPlanner

        planner = SmartPlanner(model_id=model_id)
        return await planner.plan(user_message, pipeline_type)

    def _default_planning_context(self, user_message: str, timed_out: bool = False) -> dict:
        return {
            "inferred_intent": user_message[:200],
            "has_topic": len(user_message.split()) > 4,
            "topic": None,
            "explicit_constraints": [],
            "implicit_constraints": [],
            "missing_information": [],
            "execution_strategy": "sequential",
            "execution_gate": "PROCEED",
            "inferred_personas": [],
            "inferred_nfrs": [],
            "quality_targets": [],
            "domain_insights": [],
            "planner_timed_out": timed_out,
        }

    async def _emit_planner_events(
        self,
        pipeline_run_id: str,
        pipeline_type: str,
        planning_context: dict,
        gate_verdict: str,
    ) -> AsyncGenerator[dict, None]:
        # planner_start is emitted BEFORE _run_planner is called (in execute())
        # so the frontend sees it immediately. Only emit completion events here.
        if planning_context.get("planner_timed_out"):
            yield {
                "type": "planner_timeout",
                "data": {"pipeline_run_id": pipeline_run_id, "elapsed_seconds": PLANNER_TIMEOUT_SECONDS, "timestamp": _now()},
            }
        yield {
            "type": "planner_complete",
            "data": {
                "pipeline_run_id": pipeline_run_id,
                "planning_context": planning_context,
                "execution_gate": gate_verdict,
                "timestamp": _now(),
            },
        }
        yield {
            "type": "gate_status",
            "data": {"pipeline_run_id": pipeline_run_id, "verdict": gate_verdict, "timestamp": _now()},
        }

    # ------------------------------------------------------------------
    # Domain agent execution
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_model(ectx: ExecutionContext, spec, model_id, step=None):
        """Return the effective model id for ``spec`` (MODEL-01/02/05) — resolver-or-fallback.

        ``execute()`` always seeds ``ectx.model_resolver`` (after the workflow compiles), so on
        the live path this delegates to the D-02 precedence resolver. When the resolver is
        absent — direct unit-style invocations of ``_run_agent`` / ``_run_build_task_loop`` that
        construct an ``ExecutionContext`` WITHOUT going through ``execute()`` — fall back to the
        threaded ``model_id`` (today's behavior). This fallback is parity-safe: with no override
        and no manifest model the resolver itself returns ``model_id or Haiku``, so the resolved
        id is identical either way (INV-3).
        """
        resolver = ectx.model_resolver
        if resolver is None:
            return model_id
        return resolver.resolve(spec, step)

    async def _run_agent(
        self,
        spec,
        index: int,
        ordered_agents: list,
        user_message: str,
        sandbox: RunSandbox,
        pipeline_run_id: str,
        pipeline_type: str,
        planning_context: dict,
        attached_skills: list[dict] | None,
        attached_hooks: list[dict] | None,
        model_id: str | None,
        results: list[dict],
        cancel_event: asyncio.Event | None,
        ectx: ExecutionContext,
    ) -> AsyncGenerator[dict, None]:
        """Run a single domain agent, yielding WS events.

        ``ectx`` is the per-run ExecutionContext (D-03 explicit thread): the engine
        reads od_context / owner / completed-tasks / checkpointer from it instead of
        ``self`` (the kernel holds no per-run state — CTX-02).
        """
        # Guard: if the run is already in a terminal state (e.g. user rejected
        # a review gate), stop immediately without running the agent.
        current_state = self._state_machine.get_state(pipeline_run_id)
        if current_state in ("cancelled", "failed"):
            logger.info(
                "_run_agent: skipping %s — pipeline already in terminal state=%s",
                spec.id, current_state,
            )
            return

        agent_start = time.time()

        yield {
            "type": "agent_start",
            "data": {"agent_id": spec.id, "name": spec.name, "role": spec.role,
                     "icon": spec.icon, "index": index, "total": len(ordered_agents)},
        }
        _log_event("agent_start", pipeline_run_id, agent_id=spec.id)

        # Build context message from upstream outputs (consumes contract)
        context_message = self._build_context_message(
            spec, ordered_agents, user_message,
            planning_context, ectx,
        )

        # Emit agent_input event (Phase 3 / T040) — shows full input prompt
        # and context sources in the Thinking tab (FR-015).
        context_sources = self._build_context_sources(spec, ordered_agents, ectx)
        yield {
            "type": "agent_input",
            "data": {
                "agent_id": spec.id,
                "pipeline_run_id": pipeline_run_id,
                "timestamp": _now(),
                "context_message": context_message,
                "context_sources": context_sources,
                "tool_calls": [],
            },
        }

        try:
            # Merge disk-based skills into attached_skills for this agent.
            # UI-attached skills take priority; disk skill is appended after.
            merged_skills: list[dict] = list(attached_skills or [])
            disk_skills = ectx.disk_skills
            if spec.id in disk_skills:
                merged_skills.append({"content": disk_skills[spec.id]})

            ctx = AgentContext(
                user_request=user_message,
                agent_outputs=self._filter_consumed_outputs(spec, ordered_agents, ectx),
                attached_skills=merged_skills,
                attached_hooks=list(attached_hooks or []),
                # MODEL-01/02/05: the effective model id by the D-02 precedence. With no
                # overrides + no manifest model (today) this returns ``model_id or Haiku`` =
                # the prior value — INV-3 parity. step=None this plan (06-04 wires the
                # compiled Step lookup); resolve() applies tiers 1/3/4/5 unchanged.
                model=self._resolve_model(ectx, spec, model_id),
                od_context=ectx.od_context,
                planning_context=planning_context,
                # Byte-identity guard (D-09): pass disk_principal (== user_id or "anon"),
                # NOT owner_id (the DB principal, which may be anon:<session_id>), so the
                # sub-agent's RunSandbox disk path stays byte-identical to pre-05-04.
                user_id=ectx.disk_principal,
                # run_id roots create_runner's RunSandbox at RunSandbox(user_id,
                # pipeline_run_id) — the SAME per-run disk dir the engine reads
                # deliverables back from (prototype.html / code-gen files).
                run_id=pipeline_run_id,
            )

            # Capture the resolved primary model ID *now*, before create_runner — it is
            # the string id the MODEL-02 fallback chain is armed on (set_chain below).
            # Captured here (not off ctx.model after the build) because the fallback
            # retry reassigns ctx.model to the next chain id on a throttle.
            _resolved_model_id = ctx.model

            # ── Unique per-agent-invocation checkpoint thread_id ──────────────
            # The LangGraph checkpoint thread_id isolates each agent's graph state
            # and MUST be unique per agent-invocation, or sequential agents in the
            # same run would collide on one checkpoint thread. (The disk sandbox is
            # SEPARATE — it stays per-run/shared, keyed on pipeline_run_id, so files
            # like prototype.html persist across the run's agents; see ctx.run_id
            # above.) Base id = "<pipeline_run_id>:<spec.id>". The build loop runs
            # the SAME spec.id ("prototype-build") once per task, so when a task
            # number is present we append it ("<run>:<agent>:<task>") to keep each
            # task on its own thread — _run_build_task_loop sets ectx.build_task_number
            # before each call (and it is "" for every other agent, which then uses the
            # plain two-part id). interrupt_on is intentionally NOT passed (kept None) —
            # gate-selection is Task #44 and the runner stays in non-gate mode so event
            # shapes are unchanged.
            task_num = ectx.build_task_number or None
            thread_id = (
                f"{pipeline_run_id}:{spec.id}:{task_num}"
                if task_num
                else f"{pipeline_run_id}:{spec.id}"
            )
            agent = create_runner(
                spec.id,
                ctx,
                thread_id=thread_id,
                checkpointer=ectx.checkpointer,
            )

            output_chunks: list[str] = []

            # Per-agent timeouts are DISABLED for every pipeline — agents run to
            # completion instead of being cut off mid-generation. Cutting an agent
            # off silently fell back to the PREVIOUS agent's output, which corrupted
            # results (e.g. a stalled backlog-compiler emitting the reviewer's
            # critique as if it were the final backlog). asyncio.timeout(None) is a
            # no-op deadline. The remaining guards are intentional: the Bedrock
            # client's generous botocore read_timeout (set where the client is built)
            # and the cooperative cancel_event (the Stop button), checked per chunk.
            agent_timeout = None

            # Stream with live chunk events AND timeout guard. The runner unifies
            # ALL agents through astream_events: text-only agents stream pure
            # chunk+usage+done; tool agents additionally emit tool_call/tool_result.
            # We map each event to the SAME yielded WS event the legacy use_deep
            # branch produced (chunk→agent_chunk, usage→token accumulation,
            # tool_call→tool_call, tool_result→tool_result).
            timed_out = False
            agent_input_tokens = 0
            agent_output_tokens = 0

            # ── MODEL-02 fallback chain (APPROACH B — engine-level rebuild-and-retry) ──
            # Above the botocore retries (model_factory.py): on a SUSTAINED transient
            # throttle the runner RE-RAISES the classified exception (B1,
            # deep_agent_runner.py), and the engine advances ctx.model_resolver to the
            # next fallback chain id, REBUILDS the runner via create_runner (the
            # sanctioned langchain_deepagents adapter — NO new deepagents-graph
            # construction, INV-13), and re-invokes — BOUNDED by chain length. The
            # rebuild goes through build_model only. Chain exhaustion re-raises the
            # last error (no silent blank, T-06-10). Non-transient errors are NOT
            # re-raised by the runner (they still yield {"type":"error"}); they never
            # enter this loop and propagate exactly as today (parity, T-06-11).
            #
            # ★ INV-3 PARITY: with NO throttle (the normal path) the very first attempt
            # consumes to completion and the loop exits after one pass — byte/semantically
            # identical to the single-model path. The retry only engages on a re-raised
            # throttle, so characterization snapshots are unchanged.
            #
            # ★ Pitfall 4 (mid-stream restart): a throttle BEFORE the first token (the
            # common Bedrock case — throttles are pre-call) restarts cleanly. A throttle
            # AFTER tokens already streamed cannot un-emit them; the retried attempt
            # RE-STREAMS from scratch (we reset output_chunks + token accumulators below),
            # so the final deliverable reflects the successful attempt — the only
            # observable artifact downstream consumes.
            from agents.model_policy import _is_transient_throttle

            _resolver = ectx.model_resolver
            # Arm the active chain for the resolved primary id (06-03 set_chain): the
            # cursor starts at the primary. When the resolver is absent (direct
            # unit-style _run_agent invocations) the loop runs exactly one attempt with
            # the already-built ``agent`` — today's behavior, parity-safe.
            if _resolver is not None and hasattr(_resolver, "set_chain"):
                _resolver.set_chain(_resolved_model_id)
            # Bound: chain length when armed, else a single attempt.
            _max_attempts = len(getattr(_resolver, "_chain", []) or [None]) if _resolver else 1

            # Prototype task progress is derived from the report_task_complete
            # tool events (the store-free runner_tools.report_task_complete no
            # longer populates a PrototypeArtifactStore). We capture each call's
            # args from the tool_call event and emit the SAME task_progress
            # payload shape the engine emitted from proto_store.completed_tasks.
            # The list is RUN-LEVEL (ectx.completed_tasks, created once per run
            # in execute()), NOT a local — because the build loop calls _run_agent
            # fresh once per task, so a local would reset every task and stick
            # completed_count at 1 (the #46 regression). Accumulating on ectx mirrors
            # the old run-shared PrototypeArtifactStore so completed_count grows
            # cumulatively (1,2,3,…) across the build loop's per-task invocations.
            _attempt = 0
            while True:
                _attempt += 1
                # Reset per-attempt accumulators so a retried attempt re-streams from
                # scratch (Pitfall 4) — the deliverable reflects the successful attempt.
                output_chunks = []
                agent_input_tokens = 0
                agent_output_tokens = 0
                # task_progress records appended this attempt (so a retry does not double
                # count the prototype build checklist on re-stream).
                _attempt_task_count = 0
                try:
                    async with asyncio.timeout(agent_timeout):
                        async for event in agent.astream_events(context_message):
                            if cancel_event and cancel_event.is_set():
                                raise asyncio.CancelledError()
                            etype = event["type"]
                            if etype == "chunk":
                                output_chunks.append(event["chunk"])
                                yield {"type": "agent_chunk", "data": {"agent_id": spec.id, "chunk": event["chunk"]}}
                            elif etype == "usage":
                                agent_input_tokens += event.get("input_tokens", 0)
                                agent_output_tokens += event.get("output_tokens", 0)
                            elif etype == "tool_call":
                                # ── Prototype task progress ──────────────────────────────
                                # report_task_complete carries the task in its args; record
                                # it (number/title/summary) so the task_progress event below
                                # (fired on the matching tool_result) reflects every task.
                                if event.get("tool") == "report_task_complete":
                                    args = event.get("args", {}) or {}
                                    ectx.completed_tasks.append({
                                        "number": args.get("task_number"),
                                        "title": args.get("task_title"),
                                        "summary": args.get("summary", ""),
                                    })
                                    _attempt_task_count += 1
                                yield {"type": "tool_call", "data": {"agent_id": spec.id, "tool": event["tool"], "args": event.get("args", {})}}
                            elif etype == "tool_result":
                                yield {"type": "tool_result", "data": {"agent_id": spec.id, "tool": event["tool"], "result": str(event.get("result", ""))[:500]}}
                                # When report_task_complete() returns, emit a task_progress
                                # event so the frontend can update the task checklist in
                                # real-time — same payload shape as before, now sourced from
                                # the tool events instead of the (removed) PrototypeArtifactStore.
                                if event.get("tool") == "report_task_complete":
                                    yield {
                                        "type": "task_progress",
                                        "data": {
                                            "agent_id": spec.id,
                                            "pipeline_run_id": pipeline_run_id,
                                            "completed_tasks": list(ectx.completed_tasks),
                                            "completed_count": len(ectx.completed_tasks),
                                            "timestamp": _now(),
                                        },
                                    }
                    # Stream consumed cleanly (no throttle) — done, exit the retry loop.
                    break
                except asyncio.TimeoutError:
                    timed_out = True
                    break
                except asyncio.CancelledError:
                    raise
                except Exception as _exc:
                    # Only a classified TRANSIENT THROTTLE (re-raised by the runner, B1)
                    # triggers a model switch. Anything else propagates immediately
                    # (the runner already swallows non-throttle errors into an ``error``
                    # event, so reaching here for a non-throttle means a genuine fault —
                    # do NOT mask it behind a fallback).
                    if not _is_transient_throttle(_exc):
                        raise
                    # Roll back any task_progress records appended this (failed) attempt so
                    # a retry's re-stream does not double-count the prototype checklist.
                    if _attempt_task_count:
                        del ectx.completed_tasks[-_attempt_task_count:]
                    # Advance to the next fallback chain id, if any.
                    _next_id = _resolver.advance() if _resolver is not None and hasattr(_resolver, "advance") else None
                    if _next_id is None or _attempt >= _max_attempts:
                        # Chain exhausted — re-raise the last throttle (no silent blank).
                        logger.warning(
                            "Agent %s: fallback chain exhausted after %d attempt(s); "
                            "re-raising last throttle (%s)",
                            spec.id, _attempt, _exc,
                        )
                        raise
                    # Rebuild the runner on the next chain id via create_runner (the
                    # sanctioned langchain_deepagents adapter — no new deepagents-graph
                    # construction, INV-13). ctx.model now carries the next id →
                    # DeepAgentRunner → build_model rebuilds on it. Sandbox unchanged.
                    logger.warning(
                        "Agent %s: transient throttle on model — advancing to fallback "
                        "model %s (attempt %d/%d)",
                        spec.id, _next_id, _attempt + 1, _max_attempts,
                    )
                    ctx.model = _next_id
                    # ── CR-02: fresh checkpoint thread_id per retry attempt ──────
                    # The rebuilt runner MUST restart cleanly from context_message,
                    # not RESUME the throttled attempt's partial graph state. With
                    # the live checkpointer a mid-stream throttle leaves partial
                    # state (messages, tool calls, graph nodes) under the base
                    # thread_id; reusing it would make LangGraph resume on the new
                    # model (mixed-model execution) instead of re-streaming from
                    # scratch (the Pitfall-4 intent). Derive a per-attempt id so each
                    # retry gets a clean checkpoint thread. The PRIMARY attempt keeps
                    # the base thread_id (INV-3 parity: a no-throttle run is
                    # byte-identical). The disk sandbox is UNCHANGED — it stays
                    # per-run/shared, keyed on run_id, so files persist across retries.
                    retry_thread_id = f"{thread_id}:retry{_attempt}"
                    agent = create_runner(
                        spec.id,
                        ctx,
                        thread_id=retry_thread_id,
                        checkpointer=ectx.checkpointer,
                    )
                    yield {
                        "type": "agent_model_fallback",
                        "data": {
                            "agent_id": spec.id,
                            "pipeline_run_id": pipeline_run_id,
                            "fallback_model": _next_id,
                            "attempt": _attempt + 1,
                            # WR-03: the retry RE-STREAMS from scratch on the new
                            # model, so attempt-N chunks already sent to the client
                            # are stale. This signals the frontend (Phase 8) to
                            # discard prior agent_chunk events for this agent.
                            # Additive — existing consumers ignore the new field.
                            "reset_output": True,
                            "timestamp": _now(),
                        },
                    }
                    # loop continues → re-invoke on the rebuilt runner

            if timed_out:
                logger.warning(
                    "Agent %s timed out after %.0fs — using best available output",
                    spec.id, agent_timeout,
                )
                # For tool-based agents: prefer whatever partial output was streamed
                # (may be partial HTML) over the previous agent's output (which may
                # be a spec/plan, not HTML). For text agents: fall back to previous.
                partial = "".join(output_chunks).strip()
                if partial and len(partial) > 500:
                    # Partial output is substantial — use it
                    output_chunks = [partial]
                    logger.info("Agent %s: using partial output (%d chars)", spec.id, len(partial))
                elif results:
                    fallback = results[-1].get("output", "")
                    output_chunks = [fallback] if fallback else output_chunks
                    logger.info("Agent %s: using previous agent output as fallback (%d chars)", spec.id, len(fallback))
                yield {
                    "type": "agent_error",
                    "data": {
                        "agent_id": spec.id,
                        "error": f"Agent timed out after {agent_timeout:.0f}s — using best available output",
                        "recoverable": True,
                    },
                }

            output = "".join(output_chunks)

            # ── Prototype pipeline: read HTML from the run sandbox ───────────
            # A prototype agent writes its HTML to prototype.html on disk via the
            # native deepagents write_file/edit_file tools (the text stream only
            # carries the tool confirmation, not the HTML). Read the file back and
            # prefer it over the streamed text so downstream agents receive the
            # full HTML — same "prefer the deliverable over the confirmation" rule
            # as the old shared-store path.
            if pipeline_type in ("od_prototype", "prototype"):
                html_from_disk = sandbox.read("prototype.html")
                if html_from_disk and len(html_from_disk) > len(output):
                    logger.info(
                        "Agent %s: using sandbox prototype.html (%d chars) instead of text output (%d chars)",
                        spec.id, len(html_from_disk), len(output),
                    )
                    output = html_from_disk

            # ── PPT carousel deck: strip slide-hiding CSS the composer may hallucinate ──
            # Sanitize here (before storage/context) so the stored artifact, the
            # downstream QA validator, and the final output all see a deck whose
            # carousel renders all slides. Scoped strictly to ppt/od_ppt; no-op
            # unless `output` is a horizontal-carousel deck (never prototype HTML).
            if pipeline_type in _PPT_PIPELINE_TYPES and output:
                output = _sanitize_carousel_deck_html(output)

            # Typed write (PERSIST-02 step 2): the typed graph + DB — the SOLE artifact
            # path since the prior-agent output mirror was deleted in 05-07 (INV-3).
            # Skip empty output (an agent that produced nothing has no artifact). The
            # location is the sandbox-relative file for file-backed prototype HTML, else
            # a logical artifact_refs path for string artifacts (D-01).
            if output:
                _kind = self._artifact_kind_for(spec)
                _location = (
                    "prototype.html"
                    if _kind == "html_file"
                    else f"artifact_refs/{spec.id}"
                )
                await self._dual_write_artifact(
                    ectx,
                    producer_agent=spec.id,
                    producer_step=spec.id,
                    content=output,
                    kind=_kind,
                    location=_location,
                )

            # Persist each declared `produces` kind as a typed ArtifactRef in
            # artifact_refs (PERSIST-02 — migrated off the thin store in 05-06). The
            # per-run handoff for spec.id is already dual-written above; this folds each
            # declared `produces` artifact_type into the typed path keyed by that kind.
            # visibility="workspace" so a later same-owner revision (_handle_revision
            # cross-run read) resolves it through the owner+visibility scope filter.
            # Best-effort degrade (matches _dual_write_artifact): the offline
            # characterization harness has no workflow_runs FK row, so a hard-fail here
            # would break 0A parity (INV-3).
            if output:
                for artifact_type in getattr(spec, "produces", []):
                    await self._dual_write_artifact(
                        ectx,
                        producer_agent=spec.id,
                        producer_step=spec.id,
                        content=output,
                        kind=artifact_type,
                        location=f"artifact_refs/{artifact_type}",
                        visibility="workspace",
                    )

            duration = time.time() - agent_start
            agent_total_tokens = agent_input_tokens + agent_output_tokens
            results.append({
                "agent_id": spec.id, "name": spec.name, "role": spec.role,
                "icon": spec.icon, "output": output, "duration": duration,
                "input_tokens": agent_input_tokens, "output_tokens": agent_output_tokens,
                "total_tokens": agent_total_tokens,
            })
            _log_event("agent_complete", pipeline_run_id, agent_id=spec.id,
                       duration_ms=duration * 1000)
            yield {
                "type": "agent_complete",
                "data": {"agent_id": spec.id, "name": spec.name, "duration": round(duration, 2),
                         "output_length": len(output), "index": index, "total": len(ordered_agents),
                         "input_tokens": agent_input_tokens, "output_tokens": agent_output_tokens,
                         "total_tokens": agent_total_tokens},
            }

            # ── Human_Gate: pause for user review if agent declares gate ──
            # The agent's AGENT.md frontmatter declares `gate: Human_Gate`.
            # We pause here, emit review_gate_ready with the agent's output,
            # and wait for the user to approve (possibly with edits).
            # On approve: continue with (possibly edited) output.
            # On reject: cancel the pipeline.
            # Whether THIS agent gates is the effective per-run decision (default
            # = today's static `gate: Human_Gate` set; see _should_gate / the
            # `gate_agent_ids` param on execute()). The gate body below — the
            # _run_review_gate call and its events — is unchanged.
            if self._should_gate(spec, ectx):
                async for gate_event in self._run_review_gate(
                    pipeline_run_id=pipeline_run_id,
                    agent_id=spec.id,
                    agent_name=spec.name,
                    output=output,
                ):
                    if gate_event.get("type") == "_gate_rejected":
                        # User rejected — cancel the pipeline
                        # Guard: only transition if not already in a terminal state
                        current = self._state_machine.get_state(pipeline_run_id)
                        if current not in ("cancelled", "failed"):
                            self._state_machine.transition(pipeline_run_id, "cancelled")
                        yield {"type": "pipeline_cancelled", "data": {
                            "pipeline_run_id": pipeline_run_id,
                            "reason": f"User rejected output from {spec.name}",
                        }}
                        return
                    elif gate_event.get("type") == "_gate_edited":
                        # User edited the output.
                        edited = gate_event.get("edited_content", output)
                        # Typed-write the edited content as a NEW ref version so
                        # _latest_typed_content returns the edit downstream (ART-03).
                        if edited:
                            _ek = self._artifact_kind_for(spec)
                            await self._dual_write_artifact(
                                ectx,
                                producer_agent=spec.id,
                                producer_step=spec.id,
                                content=edited,
                                kind=_ek,
                                location=(
                                    "prototype.html"
                                    if _ek == "html_file"
                                    else f"artifact_refs/{spec.id}"
                                ),
                            )
                        # Also update the last result
                        if results:
                            results[-1] = {**results[-1], "output": edited}
                    else:
                        yield gate_event

        except asyncio.CancelledError:
            raise
        except (FileNotFoundError, PermissionError) as exc:
            # Missing AGENT.md or template — fatal
            _log_event("agent_error", pipeline_run_id, agent_id=spec.id, error=str(exc))
            yield {"type": "agent_error", "data": {"agent_id": spec.id, "error": str(exc), "recoverable": False}}
        except Exception as exc:
            # If the run is already in a terminal state (cancelled/failed), don't
            # treat this as a recoverable error — re-raise so the pipeline stops.
            from agents.execution_engine.state_machine import StateMachineError
            if isinstance(exc, StateMachineError):
                current = self._state_machine.get_state(pipeline_run_id)
                if current in ("cancelled", "failed"):
                    logger.info(
                        "Agent %s: pipeline already in terminal state=%s — stopping",
                        spec.id, current,
                    )
                    return  # Stop the agent loop cleanly
            logger.exception("Agent %s failed", spec.id)
            _log_event("agent_error", pipeline_run_id, agent_id=spec.id, error=str(exc))
            yield {"type": "agent_error", "data": {"agent_id": spec.id, "error": str(exc), "recoverable": True}}
            # Typed-write the error placeholder so a downstream consumer reading from
            # the typed graph sees it (the SOLE artifact path since 05-07; parity).
            _err_output = f"[Error: {exc}]"
            _erk = self._artifact_kind_for(spec)
            await self._dual_write_artifact(
                ectx,
                producer_agent=spec.id,
                producer_step=spec.id,
                content=_err_output,
                kind=_erk,
                location=(
                    "prototype.html" if _erk == "html_file" else f"artifact_refs/{spec.id}"
                ),
            )

    # ------------------------------------------------------------------
    # Build task loop — calls prototype-build once per task
    # ------------------------------------------------------------------

    async def _run_build_task_loop(
        self,
        spec,
        index: int,
        ordered_agents: list,
        user_message: str,
        sandbox,
        pipeline_run_id: str,
        pipeline_type: str,
        planning_context: dict,
        attached_skills: list[dict] | None,
        attached_hooks: list[dict] | None,
        model_id: str | None,
        results: list[dict],
        cancel_event,
        ectx: ExecutionContext,
    ):
        """Per-task isolated sub-agent build loop with Both-validation (Phase 4).

        Replaces the pre-Phase-4 "call prototype-build N times with injected
        context" with: write the shared reference files (spec.md / design.md /
        tasks.md) to the run sandbox ONCE, then run ONE isolated sub-agent per
        task (the SAME create_runner per-task loop as Phase 3 — current task
        injected via `=== CURRENT TASK ===`), and after each task run
        Both-validation (static_check + render_check) with a bounded internal
        fix-loop. The UI event contract is UNCHANGED: task_loop_progress (here)
        + task_progress (from _run_agent's report_task_complete events) keep
        their shapes, and the validation/fix is "richer build underneath" — the
        fix sub-agent's stream is consumed INTERNALLY and never re-emitted, so
        the user still sees exactly ONE build per task.
        """
        # Typed read (ART-03): the planner's task list comes from the typed graph
        # (prototype-plan's ref content) — the SOLE source since 05-07.
        plan_output = self._latest_typed_content(
            ectx, "prototype-plan"
        ) or ""

        # Count the planner's tasks (## Task N: headers, or inside a <tasks>
        # wrapper) via the pure, unit-tested _count_plan_tasks seam. A count of 0
        # means the planner did NOT emit a task plan — the regression where it
        # built HTML/<artifact> instead of planning (now guarded by the
        # prototype-plan plan-only preamble); fall back to a single build pass.
        total_tasks, task_source = self._count_plan_tasks(plan_output)
        if total_tasks == 0:
            logger.warning(
                "Build task loop: no tasks found in plan output (%d chars) — running once",
                len(plan_output),
            )
            total_tasks = 1

        logger.info(
            "Build task loop: %d tasks for pipeline=%s",
            total_tasks, pipeline_run_id,
        )

        # ── (A) Write the shared reference files to the run sandbox ONCE ──────────
        # The sandbox is per-run/SHARED, so every per-task sub-agent (and every
        # internal fix sub-agent) sees the same spec.md / design.md / tasks.md and
        # reads them with read_file for deeper detail than the injected task block.
        # spec.md  = the spec writer's <spec> text; tasks.md = the planner's <tasks>;
        # design.md = ACTIVE TEMPLATE (SKILL.md) + ACTIVE DESIGN SYSTEM (DESIGN.md)
        # from ectx.od_context. Missing keys are handled gracefully (skip a header).
        self._write_build_reference_files(sandbox, ectx)

        for task_num in range(1, total_tasks + 1):
            if cancel_event and cancel_event.is_set():
                logger.info("Build task loop: cancelled at task %d", task_num)
                break

            # Guard: stop if pipeline was cancelled
            current_state = self._state_machine.get_state(pipeline_run_id)
            if current_state in ("cancelled", "failed"):
                logger.info(
                    "Build task loop: stopping at task %d — pipeline in terminal state=%s",
                    task_num, current_state,
                )
                break

            logger.info(
                "Build task loop: executing task %d/%d for pipeline=%s",
                task_num, total_tasks, pipeline_run_id,
            )

            # Inject task number so _build_context_message can pass it to the agent
            # (NON-artifact build-loop scratch on ectx since 05-07 — the prior-agent
            #  output dict it used to ride on was deleted).
            ectx.build_task_number = str(task_num)
            ectx.build_task_total = str(total_tasks)

            # ── (B) Stash THIS task's `## Task N:` block for injection ───────────
            # _build_context_message reads ectx.current_task_block and emits it
            # inside the `=== CURRENT TASK ===` marker the #51 prompt looks for.
            # (D-02 TEMPORARY home — Phase 7 reclaims this into TaskLoopStrategy.)
            ectx.current_task_block = self._extract_task_block(task_source, task_num)

            # Emit loop progress so frontend knows which task is running
            yield {
                "type": "task_loop_progress",
                "data": {
                    "agent_id": spec.id,
                    "pipeline_run_id": pipeline_run_id,
                    "task_number": task_num,
                    "total_tasks": total_tasks,
                    "timestamp": _now(),
                },
            }

            async for event in self._run_agent(
                spec, index, ordered_agents, user_message,
                sandbox, pipeline_run_id, pipeline_type, planning_context,
                attached_skills, attached_hooks, model_id, results, cancel_event,
                ectx,
            ):
                yield event

            # After each task: persist the HTML from the run sandbox.
            # The build agent edited prototype.html on disk this task; read it
            # back so _build_context_message passes the current HTML into the
            # next task's prompt.
            task_html = sandbox.read("prototype.html")
            if task_html:
                # Typed-write the post-task HTML as a new prototype-build ref version
                # (one per task) so _latest_typed_content returns it for the NEXT
                # task's prompt (ART-03; sole source since 05-07). task_id ties the
                # ref to the task.
                await self._dual_write_artifact(
                    ectx,
                    producer_agent=spec.id,
                    producer_step=spec.id,
                    content=task_html,
                    kind="html_file",
                    location="prototype.html",
                    task_id=str(task_num),
                )
                logger.info(
                    "Build task loop: task %d/%d done — HTML=%d chars",
                    task_num, total_tasks, len(task_html),
                )

            # ── (C) Both-validation + bounded internal fix-loop ──────────────────
            # Static check (sync) + headless render (async). On failure, re-invoke
            # the SAME sub-agent internally (≤2 attempts) with the errors injected;
            # the fix stream is consumed but NOT re-emitted (one build per task in
            # the UI). Never blocks the whole build — logs + continues after N.
            if cancel_event and cancel_event.is_set():
                break
            await self._run_validation_fix_loop(
                ctx=AgentContext(
                    user_request=user_message,
                    attached_skills=list(attached_skills or []),
                    attached_hooks=list(attached_hooks or []),
                    # MODEL-01/02/05: resolved id for the build-task validation fix sub-agent
                    # (reuses the build agent's spec). step=None this plan; parity-identical to
                    # ``model_id`` when no override/manifest model is set (INV-3).
                    model=self._resolve_model(ectx, spec, model_id),
                    od_context=ectx.od_context,
                    planning_context=planning_context,
                    # Byte-identity guard (D-09): disk_principal, NOT owner_id — keeps the
                    # fix sub-agent's RunSandbox disk path byte-identical to pre-05-04.
                    user_id=ectx.disk_principal,
                    run_id=pipeline_run_id,
                ),
                sandbox=sandbox,
                pipeline_run_id=pipeline_run_id,
                task_num=task_num,
                total_tasks=total_tasks,
                cancel_event=cancel_event,
                checkpointer=ectx.checkpointer,
            )
            # The fix-loop may have edited prototype.html — refresh the typed graph
            # so the NEXT task's sub-agent sees the corrected document.
            fixed_html = sandbox.read("prototype.html")
            if fixed_html and fixed_html != task_html:
                # Typed-write the fixed HTML only when it actually changed (avoid a
                # redundant identical ref version); keeps _latest_typed_content current.
                await self._dual_write_artifact(
                    ectx,
                    producer_agent=spec.id,
                    producer_step=spec.id,
                    content=fixed_html,
                    kind="html_file",
                    location="prototype.html",
                    task_id=str(task_num),
                )

        logger.info("Build task loop: finished %d tasks for pipeline=%s", total_tasks, pipeline_run_id)

    # ------------------------------------------------------------------
    # Phase 4 helpers — reference files, task-block extraction, validation
    # ------------------------------------------------------------------

    def _write_build_reference_files(
        self, sandbox: RunSandbox,
        ectx: ExecutionContext,
    ) -> None:
        """Write spec.md / design.md / tasks.md into the run sandbox (Region A).

        Called ONCE before the per-task loop. The per-task sub-agents read these
        with ``read_file`` for the full spec / template / design-system / task
        list. The sandbox is per-run/shared so every task (and fix) sub-agent
        sees the same files. Missing inputs degrade gracefully:
          * ``spec.md``  ← the ``prototype-specify`` content, read typed-only
            (ectx.artifacts; ART-03 — the mirror fallback was deleted in 05-07).
            Skipped if absent.
          * ``tasks.md`` ← the ``prototype-plan`` content (same typed-only read).
            Skipped if absent.
          * ``design.md`` ← ``od_context["template_body"]`` (ACTIVE TEMPLATE) +
            ``od_context["ds_body"]`` (ACTIVE DESIGN SYSTEM) under clear headers;
            each header is included only if its body is present (so a run with no
            DS still gets a template-only design.md, and vice versa).
        """
        spec_text = self._latest_typed_content(
            ectx, "prototype-specify"
        ) or ""
        tasks_text = self._latest_typed_content(
            ectx, "prototype-plan"
        ) or ""
        od = ectx.od_context or {}
        template_body = od.get("template_body") or ""
        ds_body = od.get("ds_body") or ""

        try:
            if spec_text:
                sandbox.write("spec.md", spec_text)
            if tasks_text:
                sandbox.write("tasks.md", tasks_text)

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
                sandbox.write("design.md", "\n\n".join(design_sections))

            logger.info(
                "Build task loop: wrote reference files (spec.md=%s, design.md=%s, tasks.md=%s)",
                bool(spec_text), bool(design_sections), bool(tasks_text),
            )
        except Exception as exc:  # noqa: BLE001 — never let a write failure abort the build
            logger.warning("Build task loop: failed writing reference files: %s", exc)

    @staticmethod
    def _count_plan_tasks(plan_output: str) -> tuple[int, str]:
        """Count ``## Task N:`` headers in the planner output → ``(count, task_source)``.

        Looks for top-level ``## Task N:`` headers directly; if none are present,
        falls back to the content inside a ``<tasks>…</tasks>`` wrapper and counts
        there. The returned ``count`` is the RAW number of task headers found —
        ``0`` means the planner did NOT emit a task plan (e.g. it built an HTML
        ``<artifact>`` instead of planning, the regression guarded by the
        prototype-plan plan-only preamble). The caller decides how to treat 0 (the
        build loop runs a single pass). ``task_source`` is the text the headers
        were found in (the whole output, or the unwrapped ``<tasks>`` body) so
        :meth:`_extract_task_block` slices each ``## Task N:`` block from the right
        text.

        Pure (no I/O, no engine state) so the build loop AND its tests share the
        exact same task-detection logic — mirrors :meth:`_extract_task_block`.
        """
        text = plan_output or ""
        task_matches = re.findall(r"^##\s+Task\s+(\d+)", text, re.MULTILINE)
        task_source = text
        if not task_matches:
            tasks_section = re.search(r"<tasks>([\s\S]*?)</tasks>", text, re.IGNORECASE)
            if tasks_section:
                task_source = tasks_section.group(1)
                task_matches = re.findall(r"^##\s+Task\s+(\d+)", task_source, re.MULTILINE)
        return len(task_matches), task_source

    @staticmethod
    def _extract_task_block(task_source: str, task_num: int) -> str:
        """Return the full ``## Task {n}: …`` block (header + body) from the plan.

        The block runs from its ``## Task {n}:`` header up to (but not including)
        the next ``## Task`` / ``## `` header or end-of-text. Returns ``""`` when
        the numbered task can't be located (the caller then falls back to the
        generic "execute this task" instruction in ``_build_context_message``).
        """
        import re as _re

        m = _re.search(
            rf"^##\s+Task\s+{task_num}\b.*$",
            task_source or "",
            _re.MULTILINE,
        )
        if not m:
            return ""
        start = m.start()
        # End at the next top-level "## " heading (the next task or any ## section).
        nxt = _re.search(r"^##\s+", task_source[m.end():], _re.MULTILINE)
        end = m.end() + nxt.start() if nxt else len(task_source)
        return task_source[start:end].strip()

    async def _run_validation_fix_loop(
        self,
        *,
        ctx: "AgentContext",
        sandbox: RunSandbox,
        pipeline_run_id: str,
        task_num: int,
        total_tasks: int,
        cancel_event,
        max_attempts: int = 2,
        agent_id: str = "prototype-build",
        baseline_static: "set[str] | None" = None,
        baseline_console: "set[str] | None" = None,
        user_instruction: str | None = None,
        label: str = "",
        checkpointer: object | None = None,
    ) -> None:
        """Both-validation + bounded INTERNAL fix-loop (Region C — build & revision).

        Reads ``prototype.html`` from the sandbox and runs static_check (sync) +
        render_check (async), then asks :func:`_select_issues_to_fix` which issues
        to feed back. The page is FAILING iff that selection is non-empty. With
        ``baseline_static``/``baseline_console`` empty (the BUILD defaults) the
        selection is every static issue + every render-break/console line, so
        ``failing`` reduces to EXACTLY today's ``(not sres.ok) or render_failed``
        (proof: ``not sres.ok`` ⇔ ``sres.issues`` non-empty ⇔ a static line is
        selected; ``render_failed`` ⇔ render available AND a console/page/dead-nav
        line exists ⇔ a render line is selected; an unavailable render contributes
        nothing in both — so ``bool(selected) == failing_today``). With populated
        baselines (REVISION) only NEW static/console issues are selected, while
        hard render-breakage (page errors, dead nav) is always included.

        While failing and ``attempts < max_attempts``, re-invoke the ``agent_id``
        sub-agent (a fresh ``create_runner`` on a distinct ``…:fix{n}`` thread)
        with the selected issues injected. When ``user_instruction`` is ``None``
        (build) the message keeps TODAY'S exact wording; when set (revision) it is
        revision-framed around the user's instruction. The fix sub-agent's
        ``astream_events`` is consumed INTERNALLY (the runner persists
        prototype.html to disk as a side effect) and NOTHING is re-emitted — the
        UI shows ONE build per task, identical to today. After ``max_attempts``
        still failing → ``logger.warning`` with the residual issues and return
        (the loop always continues; validation never blocks).
        """
        from app.agents.render_check import render_check
        from app.agents.static_check import static_check

        html_path = sandbox.path_for("prototype.html")
        if not html_path.is_file():
            logger.warning(
                "Validation: task %d/%d wrote no prototype.html — skipping validation",
                task_num, total_tasks,
            )
            return

        attempt = 0
        while True:
            if cancel_event and cancel_event.is_set():
                return

            sres = static_check(html_path)
            try:
                rres = await render_check(html_path)
            except Exception as exc:  # noqa: BLE001 — render harness must never crash the build
                logger.warning("Validation: render_check raised (%s) — treating as skipped", exc)
                from app.agents.render_check import RenderResult
                rres = RenderResult(ok=True, available=False, note=f"render_check error: {exc}")

            render_skipped = not rres.available
            render_failed = rres.available and not rres.ok
            # The fix-list (pure selection). With empty baselines this is byte-
            # identical to today's build ``error_lines`` and ``bool(...)`` of it
            # equals today's ``(not sres.ok) or render_failed`` (see docstring).
            error_lines = _select_issues_to_fix(
                sres, rres, baseline_static, baseline_console
            )
            failing = bool(error_lines)

            logger.info(
                "Validation: task %d/%d attempt %d — static=%s render=%s%s",
                task_num, total_tasks, attempt,
                sres.summary(), rres.summary(),
                " (render skipped)" if render_skipped else "",
            )

            if not failing:
                return  # passed (render may be skipped — that's a pass, not a fail)

            if attempt >= max_attempts:
                if user_instruction is None:
                    # BUILD residual — byte-identical to today's assembly.
                    residual: list[str] = list(sres.issues)
                    if render_failed:
                        residual.append(f"render: {rres.summary()}")
                        residual.extend(rres.console_errors)
                        residual.extend(rres.page_errors)
                        residual.extend(
                            f"dead nav link: {n.href} (no section activated)"
                            for n in rres.nav_results if not n.ok
                        )
                else:
                    # REVISION residual — the selected (still-unfixed) issues.
                    residual = list(error_lines)
                logger.warning(
                    "Validation: task %d/%d still failing after %d fix attempt(s) — "
                    "continuing build. Residual issues: %s",
                    task_num, total_tasks, max_attempts, "; ".join(residual) or "(none)",
                )
                return

            attempt += 1
            # Build the fix instruction from the selected issues.
            if user_instruction is None:
                # BUILD — preserve today's exact wording verbatim.
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
                # REVISION — re-inject the user's instruction; keep the requested
                # change intact and fix ONLY the listed (introduced/breaking) issues.
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
                "Validation: task %d/%d FAILING — internal fix attempt %d/%d (%d issue(s))",
                task_num, total_tasks, attempt, max_attempts, len(error_lines),
            )

            # Re-invoke the sub-agent on a distinct fix thread; drive its stream
            # INTERNALLY (apply edits as a side effect) and re-emit NOTHING.
            try:
                if label == "":
                    # BUILD — preserve today's exact thread-id (agent_id defaults
                    # to "prototype-build", so this is byte-identical).
                    fix_thread = f"{pipeline_run_id}:{agent_id}:{task_num}:fix{attempt}"
                else:
                    fix_thread = f"{pipeline_run_id}:{agent_id}:{label}:fix{attempt}"
                fix_agent = create_runner(
                    agent_id,
                    ctx,
                    thread_id=fix_thread,
                    checkpointer=checkpointer,
                )
                async for _ev in fix_agent.astream_events(fix_message):
                    if cancel_event and cancel_event.is_set():
                        return
                    # INTERNAL: consume only — do NOT yield. The runner writes
                    # prototype.html to disk via its tool calls; we just need the
                    # stream to drain so those edits are applied.
                    continue
            except Exception as exc:  # noqa: BLE001 — a fix failure must not abort the build
                logger.warning(
                    "Validation: task %d/%d fix attempt %d errored (%s) — continuing",
                    task_num, total_tasks, attempt, exc,
                )
                return
            # Loop back to re-validate the (possibly) fixed prototype.html.

    # ------------------------------------------------------------------
    # Gate selection — which agents pause for the inter-agent Human gate
    # ------------------------------------------------------------------

    def _should_gate(self, spec, ectx: ExecutionContext) -> bool:
        """Decide whether ``spec`` pauses for the inter-agent Human review gate.

        Effective set = the per-run ``gate_agent_ids`` passed to ``execute()``
        (carried on ``ectx.gate_agent_ids``) when given, else the STATIC set.

        - ``ectx.gate_agent_ids is not None``  → gate iff ``spec.id`` is in it.
        - else (default; field absent / client didn't send it) → gate iff the
          AGENT.md frontmatter declares ``gate: Human_Gate`` — **exactly today's
          static rule**, so behavior is byte-identical unless a client opts in.

        Only selects *which* agents trigger the gate; the gate itself
        (``_run_review_gate`` + its ``review_gate_*`` events) is unchanged.
        """
        gate_ids = ectx.gate_agent_ids
        if gate_ids is not None:
            return spec.id in set(gate_ids)
        return getattr(spec, "gate", None) == "Human_Gate"

    # ------------------------------------------------------------------
    # Review_Gate — Human review/edit/approve gate between agents
    # ------------------------------------------------------------------

    async def _run_review_gate(
        self,
        pipeline_run_id: str,
        agent_id: str,
        agent_name: str,
        output: str,
    ) -> AsyncGenerator[dict, None]:
        """Pause the pipeline for human review of an agent's output.

        Emits `review_gate_ready` with the agent's output.
        Waits for the user to call `approve_review` (via WebSocket).
        On approve: yields `review_gate_approved` and continues.
        On reject: yields `_gate_rejected` (internal signal to cancel).
        On edit+approve: yields `_gate_edited` with the new content.
        """
        gate_key = f"{pipeline_run_id}:{agent_id}"

        # Arm the event BEFORE emitting so a fast response doesn't miss it
        event = await self._store.get_review_event(gate_key)
        event.clear()

        # Guard: if the run is already in a terminal state (e.g. user rejected
        # a previous gate), don't open another gate — just signal rejection.
        current_state = self._state_machine.get_state(pipeline_run_id)
        if current_state in ("cancelled", "failed"):
            logger.info(
                "Review gate skipped: pipeline=%s agent=%s already in terminal state=%s",
                pipeline_run_id, agent_id, current_state,
            )
            yield {"type": "_gate_rejected"}
            return

        self._state_machine.transition(pipeline_run_id, "waiting_for_user")
        logger.info("Review gate opened: pipeline=%s agent=%s", pipeline_run_id, agent_id)

        yield {
            "type": "review_gate_ready",
            "data": {
                "pipeline_run_id": pipeline_run_id,
                "agent_id": agent_id,
                "agent_name": agent_name,
                "gate_key": gate_key,
                "output": output,
                "timestamp": _now(),
            },
        }

        # Wait indefinitely for user response
        await event.wait()

        response = await self._store.get_review_response(gate_key)
        approved = response.get("approved", True) if response else True
        edited_content = response.get("edited_content") if response else None

        # Only transition back to generating if we're still in waiting_for_user.
        # If the user rejected (approved=False), we'll transition to cancelled below.
        if approved:
            self._state_machine.transition(pipeline_run_id, "generating")
        logger.info(
            "Review gate closed: pipeline=%s agent=%s approved=%s edited=%s",
            pipeline_run_id, agent_id, approved, edited_content is not None,
        )

        if not approved:
            yield {"type": "_gate_rejected"}
            return

        yield {
            "type": "review_gate_approved",
            "data": {
                "pipeline_run_id": pipeline_run_id,
                "agent_id": agent_id,
                "edited": edited_content is not None,
                "timestamp": _now(),
            },
        }

        if edited_content is not None:
            yield {"type": "_gate_edited", "edited_content": edited_content}

    # ------------------------------------------------------------------
    # Backend-restart resumability (T069)
    # ------------------------------------------------------------------

    async def restore_non_terminal_runs(self) -> None:
        """Restore non-terminal WorkflowRuns on backend startup (FR-011 / T069).

        Scans workflow_runs for non-terminal states and re-registers asyncio.Events
        in the ArtifactStore for runs in `waiting_for_user` state so they can be
        resumed by user action. Completes within 30 seconds of startup (SC-007).

        Called from the FastAPI @app.on_event('startup') handler (T070).
        """
        import asyncio  # noqa: F401 — used for asyncio.Event type annotation
        from datetime import datetime, timezone

        start = datetime.now(timezone.utc)
        logger.info("ExecutionEngine.restore_non_terminal_runs: scanning for paused runs…")

        try:
            from app.models.database import SessionLocal
            from app.models.workflow import WorkflowRun

            NON_TERMINAL = (
                "running", "planning", "clarifying", "waiting_for_user",
                "generating", "analyzing", "revising",
            )

            db = SessionLocal()
            try:
                stuck_runs = (
                    db.query(WorkflowRun)
                    .filter(WorkflowRun.status.in_(NON_TERMINAL))
                    .all()
                )
                restored = 0
                abandoned = 0
                for wr in stuck_runs:
                    # WorkflowRun.id is the single run identifier (the
                    # pipeline_run_id column was dropped in migration 0013).
                    pipeline_run_id = wr.id
                    if not pipeline_run_id:
                        continue
                    # WR-05: only `waiting_for_user` runs are genuinely resumable —
                    # they are paused on an asyncio.Event the user's next answer
                    # sets. Every OTHER non-terminal state (running/generating/…)
                    # was driven by an in-process coroutine that the restart killed;
                    # re-arming a resume event + transitioning the state machine
                    # into that live-looking status would leave the run permanently
                    # stuck with no driver. Mark those abandoned (failed) instead.
                    if wr.status == "waiting_for_user":
                        await self._store.get_resume_event(pipeline_run_id)
                        try:
                            self._state_machine.transition(
                                pipeline_run_id, wr.status
                            )
                        except Exception:
                            pass
                        restored += 1
                    else:
                        # The owning process is gone — no coroutine will ever drive
                        # this run forward. Fail it loud so it is not a phantom-live
                        # row. DB write is committed once after the loop.
                        prior_status = wr.status
                        wr.status = "failed"
                        wr.error = (
                            "Run abandoned: backend restarted while in "
                            f"'{prior_status}'; no driver after restart (WR-05)."
                        )
                        abandoned += 1

                if abandoned:
                    db.commit()

                elapsed = (datetime.now(timezone.utc) - start).total_seconds()
                logger.info(
                    "restore_non_terminal_runs: restored %d resumable run(s), "
                    "marked %d abandoned run(s) failed, in %.2fs",
                    restored, abandoned, elapsed,
                )
            finally:
                db.close()
        except Exception as exc:
            logger.warning("restore_non_terminal_runs failed: %s", exc)

    # ------------------------------------------------------------------
    # Custom Workflow persistence (T061)
    # ------------------------------------------------------------------

    async def _persist_workflow_definition(
        self,
        user_id: str | None,
        pipeline_type: str,
        agents: list,
        validation_result,
    ) -> str | None:
        """Persist a custom Workflow definition to the `workflows` table.

        Only persists when user_id is set and the pipeline_type is 'custom'
        or when the workflow was explicitly composed (not a standard pipeline).
        Returns the workflow definition ID, or None if not persisted.

        The 1–50 agent limit is enforced here (Deep_Planner_Agent is prepended
        automatically and does NOT count toward the limit).
        """
        if not user_id:
            return None

        # Only persist explicitly custom workflows (not standard pipeline types)
        from agents.registry import PIPELINE_AGENTS
        if pipeline_type in PIPELINE_AGENTS and pipeline_type != "custom":
            return None

        # Enforce 1–50 agent limit (Deep_Planner_Agent excluded)
        non_planner = [a for a in agents if a.id != "deep-planner"]
        if len(non_planner) > 50:
            logger.warning(
                "Custom workflow exceeds 50-agent limit (%d agents) — not persisted",
                len(non_planner),
            )
            return None

        try:
            import json as _json
            import uuid as _uuid
            from datetime import datetime, timezone as _tz
            from app.models.database import SessionLocal
            from app.models.workflow_definition import WorkflowDefinition

            agent_ids = [a.id for a in non_planner]
            artifact_edges = [
                {
                    "from_agent": e.from_agent_id,
                    "to_agent": e.to_agent_id,
                    "artifact_type": e.artifact_type,
                }
                for e in validation_result.edges
            ]

            db = SessionLocal()
            try:
                wf = WorkflowDefinition(
                    id=str(_uuid.uuid4()),
                    user_id=user_id,
                    name=f"{pipeline_type} workflow",
                    agents=_json.dumps(agent_ids),
                    artifact_edges=_json.dumps(artifact_edges),
                    created_at=datetime.now(_tz.utc),
                    updated_at=datetime.now(_tz.utc),
                )
                db.add(wf)
                db.commit()
                db.refresh(wf)
                logger.info(
                    "Custom workflow persisted: id=%s agents=%d",
                    wf.id, len(agent_ids),
                )
                return wf.id
            finally:
                db.close()
        except Exception as exc:
            logger.warning("Failed to persist workflow definition: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Revision intelligence (T053)
    # ------------------------------------------------------------------

    async def _handle_revision(
        self,
        parent_run_id: str,
        target_artifact_type: str,
        instruction: str,
        pipeline_run_id: str,
        websocket_send_fn,
        model_id: str | None = None,
        owner_id: str | None = None,
    ) -> None:
        """Handle a revision request (FR-014).

        Retrieves the original Artifact, version history, and instruction as
        three separate structured inputs (NOT concatenated). Stores the result
        as a new Artifact version with derived_from.

        Cross-run reads of the PARENT run's artifacts go through the owner-scoped
        persisted ``ScopedStore`` against ``artifact_refs`` (the per-run in-memory
        ArtifactGraph CANNOT serve cross-run). ``assert_owns(parent_run_id)`` is
        called ABOVE the reads (T-5-SEED): a caller who does not own the parent run
        gets ``PermissionError`` — never another owner's artifacts. For a valid
        same-owner revision the owner-scoped reads return the SAME artifacts the
        thin store returned → INV-3 byte-identity preserved.

        Raises ValueError for invalid inputs (empty instruction, missing artifact,
        falsy owner_id).
        """
        if not instruction or not instruction.strip():
            raise ValueError("Revision instruction must not be empty.")

        # IN-01 / AUTHZ-03: a real owner principal is REQUIRED. The signature keeps
        # a keyword default for back-compat, but the sink-arm + scope-writeback below
        # are gated on ``if owner_id and _rev_ws_id:`` — a falsy owner would silently
        # skip run_events persistence and run-scope stamping, encoding the precondition
        # in a downstream ``write_ref`` ValueError instead of failing loud at the seam.
        # Mirror ClarifyEngine.run's falsy-owner guard so the contract is explicit.
        if not owner_id:
            raise ValueError(
                "_handle_revision requires a real owner_id (AUTHZ-03)"
            )

        # Owner-scoped persisted store for the cross-run parent reads + revision
        # write. owner_id is the run owner (user.id at the WS call site). No
        # workspace_id is threaded YET — the cross-run reads below are
        # visibility-scoped (the parent's artifacts are written
        # visibility="workspace" by the Task-1 producer writes, so they resolve
        # through the owner+visibility filter for the same owner without a
        # workspace match). The real workspace is resolved from the parent
        # artifact's row (``original.workspace_id``) AFTER the read and threaded
        # back onto the store + sink + revision run row below (CR-01).
        store = ScopedStore(owner_id=owner_id)

        # WR-06: revision runs are invoked OUTSIDE the execute() wrapper, so their
        # events would otherwise carry no seq/event_id and write no run_events row —
        # leaving a revision run with artifacts but an empty event ledger, breaking
        # the idempotent-replay contract (API-05) for that run class. Route every
        # revision emit through the SAME stamping+persist path execute() uses: arm a
        # run-events sink with this run's scoped store and stamp a monotonic seq +
        # unique event_id onto each event's data before sending. Persist is
        # best-effort (offline harness has no workflow_runs FK row → degrade).
        #
        # CR-01: the sink is armed LATER (after ``original.workspace_id`` is known)
        # rather than here, because ``append_event`` stamps the store's
        # ``workspace_id`` into ``run_events.workspace_id`` (NOT NULL, AUTHZ-01).
        # Arming with a workspace-less store would IntegrityError on every persist
        # (then degrade to a silent warning under the WR-02 narrow-catch), so NO
        # revision ledger row would ever land on a real DB. The first emit
        # (``pipeline_start``) is below the read, so deferring the arm is safe.
        _rev_sink = _RunEventSink()
        _rev_counter = itertools.count(1)
        _raw_send_fn = websocket_send_fn

        async def _stamped_send(event: dict) -> None:
            data = event.get("data")
            if not isinstance(data, dict):
                data = {}
                event["data"] = data
            _seq = next(_rev_counter)
            _eid = str(uuid.uuid4())
            data["seq"] = _seq
            data["event_id"] = _eid
            await _rev_sink.persist(_seq, _eid, event.get("type", ""), data)
            await _raw_send_fn(event)

        websocket_send_fn = _stamped_send

        # T-5-SEED: assert the caller owns the parent run BEFORE any cross-run read.
        # A cross-owner caller raises PermissionError (never reads another owner's
        # artifacts); an absent/TTL-swept parent returns None (same-owner degrade).
        await store.assert_owns(parent_run_id)

        # Retrieve the original artifact (latest by version asc) — owner-scoped.
        _refs = await store.list_refs(parent_run_id, kind=target_artifact_type)
        original = _refs[-1] if _refs else None
        if original is None:
            raise ValueError(
                f"No artifact of type {target_artifact_type!r} found for run {parent_run_id!r}. "
                "Revision MUST NOT proceed without original context (FR-014)."
            )

        # CR-01: now that the parent artifact is resolved, its workspace is the
        # authoritative workspace for the whole revision run. Thread it onto the
        # store so ``append_event`` can satisfy ``run_events.workspace_id`` NOT NULL
        # (AUTHZ-01), scope the revision ``workflow_runs`` row with the SAME
        # (owner_id, workspace_id) so the /events endpoint's owner+workspace-scoped
        # ``get_run`` resolves it (else every revision run 404s — CR-01 / AUTHZ-03),
        # and only THEN arm the sink. ``original.workspace_id`` is non-None because
        # the producer write stamped it (artifact_refs.workspace_id NOT NULL).
        _rev_ws_id = getattr(original, "workspace_id", None)
        if owner_id and _rev_ws_id:
            store._workspace_id = _rev_ws_id
            try:
                await store.set_run_scope(pipeline_run_id, owner_id, _rev_ws_id)
            except Exception as _scope_exc:  # noqa: BLE001 — never break the revision on persist
                # WR-02 parity: degrade ONLY the offline-harness DB condition
                # (no schema → SQLAlchemyError); a non-DB exception is a real bug.
                from sqlalchemy.exc import SQLAlchemyError

                if not isinstance(_scope_exc, SQLAlchemyError):
                    raise
                logger.warning(
                    "revision run scope writeback failed for %s (%s) — proceeding "
                    "(typed-substrate DB write degraded; stream unaffected)",
                    pipeline_run_id, _scope_exc,
                )
            _rev_sink.arm(store, pipeline_run_id)

        # Version history = the same owner-scoped list (avoid a second query)
        version_history = _refs

        # Check if parent run predates Phase 3 (no planning_context artifact)
        _pc = await store.list_refs(parent_run_id, kind="planning_context")
        planning_context_artifact = _pc[-1] if _pc else None
        planning_context_unavailable = planning_context_artifact is None

        # Build the three separate structured inputs (NOT concatenated)
        original_content = original.content
        history_summary = f"{len(version_history)} version(s) exist for this artifact."

        # Compose the revision context message with three clearly separated sections
        revision_context = (
            f"=== ORIGINAL ARTIFACT (type: {target_artifact_type}) ===\n"
            f"{original_content}\n"
            f"=== END ORIGINAL ARTIFACT ===\n\n"
            f"=== VERSION HISTORY ===\n"
            f"{history_summary}\n"
            f"=== END VERSION HISTORY ===\n\n"
            f"=== REVISION INSTRUCTION ===\n"
            f"{instruction}\n"
            f"=== END REVISION INSTRUCTION ==="
        )

        # If planning_context is available, prepend it as a guardrail
        if planning_context_artifact:
            revision_context = (
                f"=== PLANNING CONTEXT (original run guardrail) ===\n"
                f"{planning_context_artifact.content}\n"
                f"=== END PLANNING CONTEXT ===\n\n"
            ) + revision_context

        # Run the appropriate revision agent (use the pipeline's revision type)
        # For now, emit the revision as a single-agent pipeline
        await websocket_send_fn({
            "type": "pipeline_start",
            "data": {
                "pipeline_type": f"{target_artifact_type}_revision",
                "pipeline_run_id": pipeline_run_id,
                "agent_count": 1,
                "agents": [{"id": "revision-agent", "name": "Revision Agent",
                             "role": "Intelligent Revision", "icon": "✏️", "order": 1}],
            },
        })

        # Store the revision result as a new artifact version
        # (In a full implementation, this would run a DeepAgent revision loop)
        # For Phase 3, we store the instruction + context as the revision artifact
        # and mark it with derived_from_artifact_id
        try:
            # Build a typed ArtifactRef (graph computes id/content_hash/version)
            # for the revision result, derived_from the parent original. The
            # revision row lands in the revision RUN (pipeline_run_id); persist it
            # owner-scoped via the same ScopedStore. visibility="workspace" keeps it
            # consistent with the producer writes (a future revision-of-revision can
            # read it cross-run for the same owner).
            _rev_graph = ArtifactGraph()
            _rev_ref = _rev_graph.write_ref(
                run_id=pipeline_run_id,
                owner_id=owner_id,
                # Land the revision in the SAME workspace as the parent original so
                # the owner+workspace scope filter holds (workspace_id is NOT NULL).
                workspace_id=original.workspace_id,
                kind=target_artifact_type,
                producer_step="revision",
                producer_agent="revision-agent",
                task_id=None,
                content=revision_context,
                location=f"artifact_refs/{target_artifact_type}",
                derived_from=original.id,
                visibility="workspace",
            )
            new_artifact_id = await store.write_ref(_rev_ref)
            logger.info(
                "Revision stored: parent_run=%s type=%s new_artifact=%s planning_unavailable=%s",
                parent_run_id, target_artifact_type, new_artifact_id, planning_context_unavailable,
            )
        except Exception as exc:  # noqa: BLE001 — preserve the state_restoration_failed emit
            await websocket_send_fn({
                "type": "state_restoration_failed",
                "data": {
                    "pipeline_run_id": pipeline_run_id,
                    "parent_run_id": parent_run_id,
                    "error": str(exc),
                    "timestamp": _now(),
                },
            })
            return

        await websocket_send_fn({
            "type": "pipeline_complete",
            "data": {
                "pipeline_type": f"{target_artifact_type}_revision",
                "pipeline_run_id": pipeline_run_id,
                "total_duration": 0.0,
                "agents_completed": 1,
                "agents_total": 1,
                "final_output": revision_context,
                "planning_context_unavailable": planning_context_unavailable,
            },
        })

    def _build_context_sources(
        self,
        spec,
        ordered_agents: list,
        ectx: ExecutionContext,
    ) -> list[dict]:
        """Build the context_sources list for the agent_input event (FR-015).

        For each upstream agent whose output is consumed, records:
        - type: "summary" (text output) or "artifact" (typed artifact)
        - agent_id, agent_name, summary_length, full_output_length

        Reads consumed content typed-only (ectx.artifacts) via
        _filter_consumed_outputs (ART-03 read-migration; the mirror fallback was
        deleted in 05-07).
        """
        sources: list[dict] = []
        consumed = self._filter_consumed_outputs(spec, ordered_agents, ectx)
        for aid, output in consumed.items():
            prev = next((s for s in ordered_agents if s.id == aid), None)
            sources.append({
                "type": "summary",
                "agent_id": aid,
                "agent_name": prev.name if prev else aid,
                "summary_length": len(output),
                "full_output_length": len(output),
            })
        return sources

    def _load_disk_skills(self, agents: list, user_id: str | None) -> dict[str, str]:
        """Load disk-based skill content for every agent (user → global → built-in).

        Forwards user_id to get_skill_content so per-user SKILL.md overrides
        win over admin global / built-in defaults (WORKFLOWS.md §B6). Returns
        {agent_id: skill_content} for agents that have any skill.
        """
        from app.agents.skills import get_skill_content

        skills: dict[str, str] = {}
        for spec in agents:
            try:
                content = get_skill_content(spec.id, user_id=user_id)
            except Exception:
                content = None
            if content:
                skills[spec.id] = content
        return skills

    # ------------------------------------------------------------------
    # Typed artifact substrate — kind mapping, dual-write, typed reads (05-04)
    # ------------------------------------------------------------------

    # Map a producing agent's role to a typed ARTIFACT_KINDS value (D-01). The
    # KIND is for lineage / persisted artifact_refs rows only — the engine's
    # consumes ROUTING is by producer_agent id (the registry DAG contract is
    # id-based: produces/consumes are agent ids, not kinds), so an unmapped agent
    # still routes correctly with a sensible default kind. spec/plan/task_list/
    # html_file are the prototype pipeline's genuine artifacts.
    _AGENT_KIND_MAP: dict[str, str] = {
        "prototype-specify": "spec",
        "prototype-plan": "task_list",
        "prototype-build": "html_file",
        "prototype-validate": "validation_report",
        "prototype-revision-agent": "html_file",
    }

    def _artifact_kind_for(self, spec) -> str:
        """Resolve the ARTIFACT_KINDS value for ``spec``'s produced artifact (D-01).

        Looks up the agent-id map; falls back to ``summary`` (a valid kind) for
        agents without an explicit mapping. The kind labels the persisted
        artifact_refs row; routing is by producer_agent (see _filter_consumed_outputs),
        so the fallback never affects deliverable content / parity.
        """
        return self._AGENT_KIND_MAP.get(getattr(spec, "id", ""), "summary")

    async def _dual_write_artifact(
        self,
        ectx: ExecutionContext,
        *,
        producer_agent: str,
        producer_step: str,
        content: str,
        kind: str,
        location: str,
        task_id: str | None = None,
        derived_from: str | None = None,
        visibility: str = "private",
    ) -> None:
        """Write a genuine artifact (PERSIST-02 step 2): the in-memory typed
        ``ArtifactGraph`` (ectx.artifacts — the live typed handoff readers consume)
        AND, best-effort, the persisted ``artifact_refs`` DB row via the per-run
        ScopedStore.

        This is the SOLE artifact write path: the prior-agent output mirror that used
        to be dual-written alongside it was DELETED in 05-07 once parity proved the
        typed graph holds the same content (INV-3/INV-12, L15 ☑). The DB persist is
        best-effort like the event sink: the offline characterization harness has no
        workflow_runs FK row, so a DB failure must DEGRADE (log) and never perturb the
        deliverable / event stream.
        """
        ref = ectx.artifacts.write_ref(
            run_id=ectx.run_id,
            owner_id=ectx.owner_id,
            workspace_id=ectx.workspace_id,
            kind=kind,
            producer_step=producer_step,
            producer_agent=producer_agent,
            task_id=task_id,
            content=content,
            location=location,
            derived_from=derived_from,
            visibility=visibility,
        )
        store = ectx.scoped_store
        if store is not None:
            try:
                await store.write_ref(ref)
            except Exception as exc:  # noqa: BLE001 — never break the run on DB persist
                # WR-02: degrade ONLY the offline-harness DB condition (no schema →
                # SQLAlchemyError). Surface at WARNING with run/kind context so a
                # genuine prod artifact-persistence loss is observable; the
                # AUTHZ-03 ValueError and any other non-DB exception propagate.
                from sqlalchemy.exc import SQLAlchemyError

                if not isinstance(exc, SQLAlchemyError):
                    raise
                logger.warning(
                    "artifact_refs persist failed for run %s kind %s (%s) — "
                    "DB write degraded (offline harness / schema unavailable); "
                    "typed graph unaffected (PERSIST-02 best-effort)",
                    ectx.run_id, kind, exc,
                )

    def _latest_typed_content(
        self,
        ectx: ExecutionContext,
        producer_agent: str,
    ) -> str | None:
        """Return the LATEST content produced by ``producer_agent`` — TYPED-ONLY.

        Typed read (ART-03): the typed graph (``ectx.artifacts``) is the SOLE
        source — the latest ref by insertion order (the build loop writes a new
        prototype-build ref version per task; the next task's prompt needs the most
        recent). The prior-agent output mirror that used to be the fallback was
        DELETED in 05-07 (INV-3/INV-12, L15 ☑) once parity proved the typed reads
        return the same content. Returns None if the graph has no such content.
        """
        latest: str | None = None
        for ref in ectx.artifacts.tree(ectx.run_id):
            if ref.producer_agent == producer_agent:
                latest = ref.content
        return latest

    def _filter_consumed_outputs(
        self,
        spec,
        ordered_agents: list,
        ectx: ExecutionContext,
    ) -> dict[str, str]:
        """Return the upstream outputs this agent consumes — READ TYPED-ONLY.

        Typed read (ART-03 / PERSIST-02 step 3): the routing CONTRACT is unchanged
        (an upstream agent is consumed iff its ``produces`` intersects this agent's
        ``consumes`` — both are registry agent-id sets); the CONTENT comes solely
        from ``ectx.artifacts`` (the typed graph). The prior-agent output mirror
        fallback was deleted in 05-07. Returns ``{upstream.id: content}`` exactly as
        before so every caller (_build_context_message / _build_context_sources /
        AgentContext.agent_outputs) is byte-identical.
        """
        consumes = set(getattr(spec, "consumes", []))
        if not consumes:
            return {}
        filtered: dict[str, str] = {}
        for upstream in ordered_agents:
            if upstream.id == spec.id:
                break
            # Skip internal engine markers (not real agent outputs)
            if upstream.id.startswith("_"):
                continue
            produced = set(getattr(upstream, "produces", []))
            if produced & consumes:
                content = self._latest_typed_content(ectx, upstream.id)
                if content is not None:
                    filtered[upstream.id] = content
        return filtered

    def _build_context_message(
        self,
        spec,
        ordered_agents: list,
        user_message: str,
        planning_context: dict,
        ectx: ExecutionContext,
    ) -> str:
        """Build the context message (user request + consumed upstream outputs).

        Phase 3 (FR-016): planning_context is injected cross-cutting to ALL agents.
        For od_ppt / od_prototype agents that declare `injects`, the template body
        and example HTML are also injected into the user message — the AGENT.md
        prompts explicitly expect them there (ACTIVE TEMPLATE, TEMPLATE EXAMPLE).

        Chain context (=== CONTEXT FROM PREVIOUS PIPELINE ===) is only shown to
        the FIRST agent in the pipeline — it interprets the brief. Downstream
        agents already receive the first agent's structured output (spec/HTML)
        via the typed graph, so the raw chain context is noise for them.
        """
        # Determine if this is the first agent in the pipeline
        is_first_agent = (len(ordered_agents) == 0 or spec.id == ordered_agents[0].id)

        # For downstream agents, strip the chain context block from user_message
        # to avoid polluting their input with the full previous pipeline output.
        # Keep only the clean brief (everything before the first === CONTEXT === block).
        if not is_first_agent and "=== CONTEXT FROM PREVIOUS PIPELINE" in user_message:
            clean_brief = user_message.split("\n\n=== CONTEXT FROM PREVIOUS PIPELINE")[0].strip()
            effective_message = clean_brief
        else:
            effective_message = user_message

        parts = [f"=== ORIGINAL USER REQUEST ===\n{effective_message}\n=== END REQUEST ==="]

        # Inject planning_context for ALL pipelines (cross-cutting guardrail, FR-016)
        if planning_context and not planning_context.get("planner_timed_out"):
            intent = planning_context.get("inferred_intent", "")
            constraints = planning_context.get("explicit_constraints", [])
            implicit = planning_context.get("implicit_constraints", [])
            nfrs = planning_context.get("inferred_nfrs", [])
            personas = planning_context.get("inferred_personas", [])
            quality = planning_context.get("quality_targets", [])
            domain_insights = planning_context.get("domain_insights", [])

            ctx_lines = ["## Planning Context (Deep Planner Analysis)"]
            if intent:
                ctx_lines.append(f"\n**Inferred Intent**: {intent}")
            if constraints:
                ctx_lines.append("\n**Explicit Constraints**:\n" + "\n".join(f"- {c}" for c in constraints))
            if implicit:
                ctx_lines.append("\n**Implicit Constraints**:\n" + "\n".join(f"- {c}" for c in implicit))
            if personas:
                ctx_lines.append("\n**Inferred Personas**:\n" + "\n".join(f"- {p}" for p in personas))
            if nfrs:
                ctx_lines.append("\n**Non-Functional Requirements**:\n" + "\n".join(f"- {n}" for n in nfrs))
            if quality:
                ctx_lines.append("\n**Quality Targets**:\n" + "\n".join(f"- {q}" for q in quality))
            if domain_insights:
                ctx_lines.append("\n**Domain Insights**:\n" + "\n".join(f"- {i}" for i in domain_insights))
            ctx_lines.append("\n## End Planning Context")

            parts.append("\n".join(ctx_lines))

        # ── od_ppt / od_prototype: inject template + DS + example into user message ──
        # The AGENT.md prompts for these agents explicitly expect:
        #   - ACTIVE TEMPLATE (SKILL.md) — the template's workflow instructions
        #   - ACTIVE DESIGN SYSTEM (DESIGN.md) — the design tokens
        #   - TEMPLATE EXAMPLE (example.html) — concrete visual reference
        # Without these in the user message, the agent ignores the template and
        # generates a generic prototype that doesn't match the selected style.
        #
        # For prototype-build tasks 2+: skip the full DS body and template body
        # injection — the skeleton already has the DS tokens and the task list
        # has the CSS classes. Only inject for task 1 (HTML shell) and for
        # non-build agents (spec writer, planner, validate).
        od = ectx.od_context or {}
        injects = getattr(spec, "injects", []) or []
        task_num_str = ectx.build_task_number
        is_build_task_2_plus = (spec.id == "prototype-build" and task_num_str not in ("", "1"))

        # Inject design system into user message for ALL prototype agents
        # (it's also in the system prompt via factory.py, but repeating it
        # in the user message ensures text-only agents see it prominently).
        # Skip for build tasks 2+ — skeleton already has DS tokens.
        if "design_system" in injects and od.get("ds_body") and not is_build_task_2_plus:
            ds_id = od.get("ds_id", "custom")
            is_deck_conditional = od.get("is_design_system_required")
            include_ds = True if is_deck_conditional is None else bool(is_deck_conditional)
            if include_ds:
                parts.append(
                    f"=== ACTIVE DESIGN SYSTEM: {ds_id} ===\n"
                    f"Apply these tokens to ALL colors, fonts, and spacing. "
                    f"Map to :root variables: --bg, --fg, --accent, --surface, --border, --muted.\n"
                    f"{od['ds_body']}\n"
                    f"=== END ACTIVE DESIGN SYSTEM ==="
                )

        if "template" in injects and od.get("template_body"):
            template_id = od.get("template_id", "")
            # For build tasks 2+: skip the full template body — the task list
            # already has the CSS classes and layout patterns.
            if not is_build_task_2_plus:
                parts.append(
                    f"=== ACTIVE TEMPLATE (SKILL.md): {template_id} ===\n"
                    f"{od['template_body']}\n"
                    f"=== END ACTIVE TEMPLATE ==="
                )
                # Also inject example.html if available — gives the agent a concrete
                # visual reference for the template's class system and layout patterns.
                # Inject example.html ONLY for the BUILD agent (it needs a concrete
                # reference for the template's class system). Planning agents
                # (prototype-specify / prototype-plan, tools=[]) must NOT see a full
                # working HTML doc — it nudges them to copy/continue it instead of
                # writing the spec / decomposing into tasks.
                _is_builder = bool(set(getattr(spec, "tools", []) or []) & {"prototype_emit_only", "prototype"})
                example_html = self._load_template_example(template_id) if _is_builder else None
                if example_html:
                    parts.append(
                        f"=== TEMPLATE EXAMPLE (example.html): {template_id} ===\n"
                        f"{example_html[:8000]}"
                        f"{'...[truncated]' if len(example_html) > 8000 else ''}\n"
                        f"=== END TEMPLATE EXAMPLE ==="
                    )

            # Pre-inject prototype reference files (template seed + layouts + checklist).
            # For build tasks 2+: inject ONLY the template seed (CSS classes needed
            # to build the page) — skip layouts.md and checklist.md to save tokens.
            # For task 1 and all other agents: inject all reference files.
            if "prototype_emit_only" in (getattr(spec, "tools", []) or []):
                # Build/validate agent — inject template seed always, others only for task 1
                from agents.prototype.context import get_template_injection_parts
                all_parts = get_template_injection_parts(template_id)
                if is_build_task_2_plus:
                    # Only inject the seed (first part) — skip layouts and checklist
                    seed_parts = [p for p in all_parts if "TEMPLATE SEED" in p]
                    for part in seed_parts:
                        parts.append(part)
                else:
                    for part in all_parts:
                        parts.append(part)
            elif "prototype" in (getattr(spec, "tools", []) or []):
                from agents.prototype.context import get_template_injection_parts
                for part in get_template_injection_parts(template_id):
                    parts.append(part)

        consumed = self._filter_consumed_outputs(spec, ordered_agents, ectx)
        for aid, output in consumed.items():
            prev = next((s for s in ordered_agents if s.id == aid), None)
            label = f"{prev.name} ({prev.role})" if prev else aid
            parts.append(f"\n--- Output from {label} ---\n{output}")

        # For the build agent: inject the current task block + current HTML.
        # The #51 prototype-build prompt reads `=== CURRENT TASK ===` to find its
        # authoritative scope. The Phase-4 build loop (_run_build_task_loop) writes
        # spec.md / design.md / tasks.md to the sandbox (the sub-agent reads them
        # with read_file for deeper detail) and stashes THIS task's full `## Task N:`
        # block on `ectx.current_task_block` before each _run_agent call — we emit
        # that block inside the marker so the sub-agent's scope is the exact planner
        # task text, not just "Task N of M". (The Both-validation fix re-run is driven
        # INTERNALLY by the loop with its own constructed message — see
        # _run_validation_fix_loop — so it does NOT pass through here.)
        if spec.id == "prototype-build":
            task_num_str = ectx.build_task_number
            total_str = ectx.build_task_total
            if task_num_str:
                task_block = ectx.current_task_block or ""
                body = task_block.strip() if task_block.strip() else (
                    "Execute ONLY this task from the task list above."
                )
                parts.append(
                    f"\n=== CURRENT TASK ===\n"
                    f"Task {task_num_str} of {total_str}\n"
                    f"{body}\n"
                    f"=== END CURRENT TASK ==="
                )

            # Pass current HTML for modification.
            # For build tasks 2+ (0C / COMPACT-01): inject only the compact
            # ~1-3k char skeleton state-map (self._extract_html_skeleton) instead of
            # the full current HTML (up to 120k) — this kills the O(n²) prompt growth.
            # The skeleton is framed as a state-map (NOT the editable source) and
            # points the sub-agent at read_file('prototype.html') to fetch the full
            # content before editing (its AGENT.md already mandates this). Task 1 (the
            # HTML shell) has no prior HTML and keeps the full-HTML block unchanged.
            # Typed read (ART-03): read the latest prototype-build HTML from the typed
            # graph (the build loop writes a new ref version per task) — sole source
            # since the mirror was deleted in 05-07.
            current_html = self._latest_typed_content(
                ectx, "prototype-build"
            ) or ""
            if current_html and not current_html.startswith("[Error:"):
                if is_build_task_2_plus:
                    skeleton = self._extract_html_skeleton(current_html)
                    parts.append(
                        f"\n=== CURRENT PROTOTYPE (skeleton — call read_file('prototype.html') "
                        f"for full content before editing) ===\n"
                        f"{skeleton}\n"
                        f"=== END CURRENT PROTOTYPE ==="
                    )
                else:
                    html_to_pass = current_html[:120000]
                    truncated = len(current_html) > 120000
                    parts.append(
                        f"\n--- CURRENT HTML (modify this — do NOT rebuild from scratch) ---\n"
                        f"{html_to_pass}"
                        f"{'...[truncated at 120k]' if truncated else ''}\n"
                        f"--- END CURRENT HTML ---"
                    )

            # Template compliance reminder
            od = ectx.od_context or {}
            ds_id = od.get("ds_id", "")
            template_id_val = od.get("template_id", "")
            parts.append(
                f"\n=== TEMPLATE COMPLIANCE ===\n"
                f"Template: {template_id_val} — use ONLY its CSS classes from the TEMPLATE SEED\n"
                f"Design System: {ds_id} — use ONLY :root variables, never raw hex colors\n"
                f"=== END TEMPLATE COMPLIANCE ==="
            )

        return "\n".join(parts)

    @staticmethod
    def _extract_existing_prototype_html(user_message: str) -> str:
        """Pull the current prototype HTML out of a revision request.

        The frontend wraps it as:
            === EXISTING PROTOTYPE HTML ===
            <!doctype html> ...
            === END EXISTING HTML ===
        Returns "" if the markers are absent (defensive — the agent then works
        from the prompt alone).
        """
        import re as _re

        m = _re.search(
            r"=== EXISTING PROTOTYPE HTML ===\s*([\s\S]*?)\s*=== END EXISTING HTML ===",
            user_message, _re.IGNORECASE,
        )
        return m.group(1).strip() if m else ""

    @staticmethod
    def _slim_revision_message(user_message: str) -> str:
        """Replace the inlined EXISTING HTML block with a pointer to the file.

        Once the current prototype lives in the workspace as prototype.html there
        is no reason to also carry 60-100k chars of it in the agent's prompt. We
        swap the HTML block for a one-line pointer and keep the
        === REVISION REQUEST === section (the agent's actual instruction, also
        used to title the run) intact.
        """
        import re as _re

        return _re.sub(
            r"=== EXISTING PROTOTYPE HTML ===[\s\S]*?=== END EXISTING HTML ===",
            f"The current prototype is in the workspace file `{REVISION_FILE_NAME}`. "
            "Call read_file to read it before editing.",
            user_message, count=1, flags=_re.IGNORECASE,
        ).strip()

    def _load_template_example(self, template_id: str) -> str | None:
        """Load the example.html for a template, or None if not available."""
        if not template_id:
            return None
        try:
            from agents.prototype.context import get_example_html
            return get_example_html(template_id)
        except Exception as exc:
            logger.debug("Could not load template example for %s: %s", template_id, exc)
        return None

    def _extract_html_skeleton(self, html: str) -> str:
        """Extract a compact skeleton from the full HTML for build agent context.

        Option 1+5: instead of passing the full HTML (which grows with every task
        and causes O(n²) slowdown), extract only what the build agent needs:
          - :root token values (so DS tokens are preserved across calls)
          - List of <section data-page> IDs with filled/empty status
          - Routes map
          - Chrome structure summary

        Returns a compact ~1-3k char summary instead of the full 50k+ HTML.
        """
        import re as _re
        lines: list[str] = []

        # 1. Extract :root tokens
        root_match = _re.search(r":root\s*\{([^}]+)\}", html, _re.DOTALL)
        if root_match:
            root_content = root_match.group(1).strip()
            # Keep only the 6 key token lines
            token_lines = []
            for line in root_content.split("\n"):
                line = line.strip()
                if any(tok in line for tok in ["--bg:", "--fg:", "--accent:", "--surface:", "--border:", "--muted:", "--font-"]):
                    token_lines.append(f"  {line}")
            if token_lines:
                lines.append(":root tokens (current):\n" + "\n".join(token_lines[:12]))

        # 2. Extract routes map
        routes_match = _re.search(r"const routes\s*=\s*\{([^}]+)\}", html, _re.DOTALL)
        if routes_match:
            routes_content = routes_match.group(1).strip()
            lines.append(f"Routes map:\n  {{{ routes_content.strip() }}}")

        # 3. Scan all <section data-page> elements — filled vs empty
        sections = _re.findall(
            r'<section[^>]+data-page=["\']([^"\']+)["\'][^>]*>([\s\S]*?)(?=<section|</body>)',
            html, _re.IGNORECASE
        )
        filled = []
        empty = []
        for page_id, content in sections:
            # A section is "filled" if it has more than just whitespace/comments
            stripped = _re.sub(r'<!--.*?-->', '', content, flags=_re.DOTALL).strip()
            if len(stripped) > 100:
                filled.append(page_id)
            else:
                empty.append(page_id)

        if filled:
            lines.append(f"Pages already built ({len(filled)}): {', '.join(filled)}")
        if empty:
            lines.append(f"Pages still empty ({len(empty)}): {', '.join(empty)}")

        # 4. Chrome summary (topnav/sidebar presence)
        has_sidebar = bool(_re.search(r'<aside|data-od-id=["\']sidebar', html, _re.IGNORECASE))
        has_topnav = bool(_re.search(r'class=["\'][^"\']*topnav|data-od-id=["\']topnav', html, _re.IGNORECASE))
        chrome_type = "sidebar" if has_sidebar else ("topnav" if has_topnav else "none")
        lines.append(f"Chrome: {chrome_type} (copy chrome from any filled page — do NOT rewrite it)")

        # 5. Total HTML size for reference
        lines.append(f"Total HTML so far: {len(html):,} chars across {len(filled) + len(empty)} sections")

        return "\n".join(lines)


# ------------------------------------------------------------------
# Module-level singleton
# ------------------------------------------------------------------

_ENGINE: ExecutionEngine | None = None


def get_execution_engine() -> ExecutionEngine:
    """Return the module-level ExecutionEngine singleton."""
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = ExecutionEngine()
    return _ENGINE
