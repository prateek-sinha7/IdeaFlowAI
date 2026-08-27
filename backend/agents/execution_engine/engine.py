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
import hashlib
import itertools
import json
import logging
import time
import uuid
from typing import AsyncGenerator, Awaitable, Callable

from pathlib import Path

from agents.artifact_store.store import get_artifact_store
from agents.artifacts.graph import ArtifactGraph
from agents.authz import ScopedStore

# A.4 (Phase 43): the app-layer narrator milestone-card persist, INJECTED into ``execute()``
# (never imported — the kernel must not import ``app.*``). Structurally
# ``chat_narrator.persist_milestone_card(store, run_id, event) -> (created, seq, card, reply_eid) | None``;
# typed here as a generic awaitable callback so no app symbol crosses the import boundary.
MilestoneSink = Callable[[ScopedStore, str, dict], Awaitable[object]]

# A.3 (Phase 43): the app-layer live-ectx registrar, INJECTED into ``execute()`` (never
# imported — the kernel must not import ``app.*``, import-linter 4/0). At run start the
# engine REGISTERS the run's in-process ``ExecutionContext`` keyed by run_id so the app-layer
# ``_live_ectx_for_run`` can resolve it for mid-run steering (=== USER GUIDANCE ===) + per-turn
# images; on teardown it UNREGISTERS (no leak). Typed as generic callables so no app symbol
# crosses the import boundary. Both ``None`` (the goldens + every current WS caller) keeps the
# seam DORMANT — byte/event-identical (the drain fires only when a note/image was queued for a
# resolvable running run). Keyed on run_id ONLY (SC-001/INV-1 — no workflow/agent literal).
LiveEctxRegister = Callable[[str, "ExecutionContext"], None]
LiveEctxUnregister = Callable[[str], None]

# BUG-R03: the app-layer resume output-column persister, INJECTED into the engine (never
# imported — the kernel must not import ``app.*``, import-linter 4/0). The resume tier is
# structurally silent on every output-bearing WorkflowRun column (output/agent_outputs/
# token_usage/duration/deliverable_*) — only the engine state machine writes ``status``. This
# callback reads the run's owner-scoped durable ``run_events`` tail and persists those columns
# via the SAME mapping the launch driver uses (INV-12). Fired from ``_drive_resumed_stream``'s
# finally on the RESTART auto-resume path (branch b). Typed as a generic run_id→awaitable so no
# app symbol crosses the boundary; ``None`` (the goldens + every non-app driver) keeps it
# DORMANT — byte/event-identical resume (INV-3). Keyed on run_id ONLY (SC-001 — no workflow
# name, no column literal in the kernel).
ResumeOutputPersist = Callable[[str], Awaitable[None]]

# ISS-084: the app-layer per-run cooperative cancel Event lookup, INJECTED into the engine
# (never imported — the kernel must not import ``app.*``, import-linter 4/0). The launch
# path receives its Event as an ``execute()`` argument, but a RESUMED run has no such
# caller: ``restore_non_terminal_runs`` spawns its drivers from the kernel itself, so
# ``_drive_resumed_stream`` passed ``_execute_impl`` no ``cancel_event`` at all and every
# cooperative guard (``if cancel_event and cancel_event.is_set()``) bound None and
# short-circuited — no resumed run could be stopped by anyone. This callback resolves the
# SAME Event object the REST cancel endpoint sets (one registry, one object; an Event the
# engine does not hold is an orphan, which is what made ``cancel`` answer ``true`` while
# the run kept billing). Typed as a generic run_id→Event so no app symbol crosses the
# boundary; ``None`` (the goldens + every non-app driver) keeps it DORMANT → the funnel
# passes ``cancel_event=None``, byte/event-identical (INV-3). Keyed on run_id ONLY (SC-001).
ResumeCancelEvent = Callable[[str], "asyncio.Event | None"]
from agents.capabilities.context_providers.opendesign import (
    RAW_BLOCK_PREFIX as _RAW_BLOCK_PREFIX,
)
from agents.capabilities import task_identity
from agents.capabilities.gate_pendency import derive_open_gate
from agents.capabilities.registry import CapabilityRegistry
from agents.capabilities.validators.severity import render_coverage_status
from agents.execution_engine.budget import BudgetExceeded, BudgetManager, BudgetSnapshot
from agents.execution_engine.fanout import FanoutWorkerFailed
# _ClarifyEngineImpl is bound at IMPORT time on purpose, and does NOT supersede the
# function-level ``from ... import ClarifyEngine`` inside the clarify drain loop. There
# is still exactly one ClarifyEngine and one _merge_answers — only the RESOLUTION TIMING
# differs, deliberately. The live clarify invocation must stay LATE-bound because two
# tests monkeypatch the module attribute (test_restart_resume.py's _FakeClarify /
# _ParkingClarify); the rehydrator must stay EARLY-bound because those same fakes have no
# _merge_answers and a late binding would silently pick them up, leaving a resumed run
# with none of its clarification answers. Do not "tidy" either binding away.
from agents.execution_engine.clarify_engine import ClarifyEngine as _ClarifyEngineImpl
from agents.execution_engine.context import ExecutionContext
from agents.execution_engine.resolver import WorkflowResolver
from agents.execution_engine.run_log import RunLog, RunTrace
from agents.execution_engine.state_machine import get_state_machine
from agents.capabilities.model_catalog import ModelCatalog
from agents.capabilities.model_pricing import estimate_cost_usd
from agents.factory import AgentContext, create_runner
from agents.model_policy import ModelResolver
from agents.workflows.artifacts import CUSTOM_AGENT_PREFIX, artifact_name, topic_slug
from agents.workflows.compiler import WorkflowCompiler
from agents.workflows.manifest import load_manifest
from agents.workflows.plan import CompiledWorkflow
from app.agents.sandbox import RunSandbox, write_agent_output

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
# WR-02 (16 review) — client-facing sanitization of runner error text
# ---------------------------------------------------------------------------

# Stable, leak-free message placed on the client-facing ``agent_error`` event.
# The chat path routes provider exceptions through
# ``app.agents.llm_errors.map_exception`` to a secret-free triple; the engine
# only holds the runner's stringified ``str(exc)`` (the runner stays as-is, A1),
# so we cannot inspect the botocore error code to pick a granular message —
# ``map_exception`` itself falls back to ``internal_error`` ("Something went
# wrong…") for any non-exception input. We therefore emit a fixed generic
# message and keep the raw provider text server-side only (logged). This makes a
# leak structurally impossible: a non-throttle Bedrock fault's ``str(exc)`` can
# carry ARNs / region / model-id / config, none of which reach the browser.
_GENERIC_AGENT_ERROR_MESSAGE = "The model rejected this request."


def _sanitize_agent_error(raw: str) -> str:
    """Return a bounded, secret-free client-facing message for a runner error.

    ``raw`` is the runner's ``str(exc)`` (already bounded to 500 chars upstream).
    It can carry provider ARNs / region / model-id / internal config for a
    non-throttle Bedrock fault, so it is NEVER returned verbatim — the caller
    keeps it in the server log only. We return a fixed generic message
    (WR-02 / T-16-01-ID: bounded, no stack frames, no secrets). Keyed on nothing
    in ``raw`` — no provider/model/workflow text match (SC-001).
    """
    return _GENERIC_AGENT_ERROR_MESSAGE


# ---------------------------------------------------------------------------
# ISS-004 (19-03): streamed agent_chunk sanitizer + chunk-straddle buffer
# ---------------------------------------------------------------------------
# The 13-02 sanitizer (`_strip_fabricated_tool_xml`, reused here via the runner's
# duck-typed `sanitize_output`) cleans the AUTHORITATIVE chunk-joined output at the
# post-loop locus (~:2645). But the engine YIELDS each raw `chunk` as an
# `agent_chunk` event BEFORE accumulation/sanitization, so fabricated
# `<function_calls>`/`<invoke ...>` reaches the LIVE UI stream (plus the
# durable-replay collector + the reconnect tail). This buffer routes each YIELDED
# chunk through the SAME runner sanitizer — but a naive per-chunk pass misses a
# `<function_calls>…</function_calls>` span SPLIT across two chunk deltas: chunk 1
# ends with an unterminated `<function_calls>` opener, chunk 2 carries the close.
# Sanitizing chunk 1 alone would strip from the opener to EOF (the runner's
# `_UNTERMINATED_TOOL_XML_RE`) and silently swallow the legitimate tail of chunk 2.
# So we HOLD the tail from an unterminated opener, append the next chunk, and only
# sanitize+yield once the span closes (or at stream end). SC-001: gated ONLY on the
# generic tool-less runner capability (`sanitize_output` is an identity no-op for
# tool-using agents), never a workflow/agent-name literal.

# Opener / matching-close tokens (mirror the runner's `_FABRICATED_TOOL_XML_RE`
# openers — we do NOT hand-roll a divergent STRIPPING regex; the actual stripping is
# delegated to the runner's `sanitize_output`. These tokens are used ONLY to detect
# WHERE an unterminated span begins so the buffer can hold its tail). `<invoke` has no
# trailing `>` so a split mid-attribute (`<invoke name="read_`) is still an opener.
_TOOL_XML_OPENERS: tuple[str, ...] = ("<function_calls>", "<invoke")
# Each opener's matching CLOSE tag — a span is COMPLETE once its close has arrived.
_TOOL_XML_CLOSE_FOR: dict[str, str] = {
    "<function_calls>": "</function_calls>",
    "<invoke": "</invoke>",
}


class _ChunkStreamSanitizer:
    """Per-agent-stream buffer that strips fabricated tool-XML from yielded chunks.

    Wraps the runner's duck-typed ``sanitize_output`` (the SAME 13-02
    ``_strip_fabricated_tool_xml`` transform applied to the authoritative output).
    For a tool-USING agent ``sanitize_output`` is an identity no-op, so this buffer
    passes every chunk through verbatim (the gate is the runner capability itself,
    NOT a workflow name — SC-001). For a tool-less agent it removes complete
    ``<function_calls>…</function_calls>`` / ``<invoke …>…</invoke>`` spans AND holds
    an UNTERMINATED trailing opener until the next chunk supplies the close (or until
    stream end), so a span split across two chunk deltas is still stripped.

    The held buffer only ever spans from an unterminated opener to the (eventual)
    close or stream end — bounded by one agent's output (T-19-03-03: no unbounded
    growth, reuses the runner's linear single-pass regex). At stream end any residual
    held tail is flushed through the sanitizer (an unterminated opener at EOF is
    stripped, mirroring the runner's WR-01 ``_UNTERMINATED_TOOL_XML_RE``), so the
    buffer never silently swallows legitimate trailing content.
    """

    __slots__ = ("_sanitize", "_buffer", "_active")

    # A fabricated-tool-XML PROBE: a tool-less runner's sanitize_output strips this to
    # empty; a tool-using runner's identity no-op returns it unchanged. Used ONCE at
    # construction to decide whether buffering is needed at all (so a tool-using stream
    # is byte-AND-chunk-identical, not merely join-identical). Generic — the probe is a
    # behavioral test of the runner capability, NOT a workflow/agent-name check (SC-001).
    _PROBE = "<function_calls><invoke name=\"_probe_\"></invoke></function_calls>"

    def __init__(self, sanitize: Callable[[str], str] | None) -> None:
        # ``sanitize`` is the runner's duck-typed ``sanitize_output`` (identity for
        # tool-using agents / clean text — same-object return). ``None`` when the
        # runner exposes no such capability → pass-through identity.
        self._sanitize: Callable[[str], str] = sanitize if callable(sanitize) else (lambda t: t)
        self._buffer: str = ""
        # Is the sanitizer ACTUALLY active (tool-less)? Probe once: if it strips the
        # fabricated-XML probe, buffering is needed; if it returns the probe unchanged
        # (tool-using identity / no capability), the buffer stays fully inert so every
        # chunk passes through verbatim — same chunks, same boundaries (the plan's
        # "tool-using stream untouched" contract). SC-001: behavioral probe, no name.
        self._active: bool = self._sanitize(self._PROBE) != self._PROBE

    @staticmethod
    def _hold_from_index(text: str) -> int:
        """Index from which ``text`` must be HELD (an open/partial span), or ``-1``.

        Scans for the earliest position that begins an UNTERMINATED tool-XML span:

        * a complete opener token (``<function_calls>`` / ``<invoke``) whose matching
          CLOSE (``</function_calls>`` / ``</invoke>``) has NOT yet arrived — the span
          straddles into a future chunk, so hold from the opener; OR
        * a trailing PARTIAL opener token (e.g. ``…<inv`` / ``…<function_cal``) — the
          opener itself is split across the delta boundary, so hold the partial tail
          until the next chunk completes (or refutes) it.

        Complete, already-closed spans are NOT held (the sanitizer strips them in
        place). Returns ``-1`` when nothing needs holding.
        """
        hold = -1
        # (1) Earliest complete opener token whose matching close has not yet arrived.
        for opener in _TOOL_XML_OPENERS:
            start = 0
            while True:
                pos = text.find(opener, start)
                if pos == -1:
                    break
                close = _TOOL_XML_CLOSE_FOR[opener]
                if text.find(close, pos + len(opener)) == -1:
                    # No matching close yet → this opener begins an open span.
                    if hold == -1 or pos < hold:
                        hold = pos
                    break  # earliest unclosed instance of THIS opener found
                start = pos + len(opener)
        # (2) A trailing PARTIAL opener token (the opener itself is split): the text
        # ends with a non-empty proper prefix of some opener token. Hold from there so
        # the next chunk can complete it. Only matters when it would hold EARLIER than
        # (1) — a partial prefix is by construction at the very end of the text.
        #
        # WR-01: require the held prefix to be at least 2 chars (``<f``/``<i`` and
        # longer), so a LONE ``<`` — common in legit tool-less prose (HTML/JSX tags,
        # comparison operators like ``a < b``) — is NEVER buffered. This keeps chunk
        # granularity byte-identical for ordinary tool-less streams. A lone ``<``
        # followed in the next delta by ``function_calls>``/``invoke`` is still caught:
        # the joined text re-scans for the complete/partial opener on the next ``feed``.
        for opener in _TOOL_XML_OPENERS:
            # Longest proper prefix of `opener` (length >= 2) that is a suffix of `text`.
            for plen in range(len(opener) - 1, 1, -1):  # stop at 2, never hold a lone "<"
                if text.endswith(opener[:plen]):
                    pos = len(text) - plen
                    if hold == -1 or pos < hold:
                        hold = pos
                    break
        return hold

    def feed(self, chunk: str) -> str:
        """Accept one streamed chunk; return the safe-to-yield (sanitized) prefix.

        Concatenates any held buffer + the new chunk. If the joined text contains a
        tool-XML span whose close has NOT yet arrived (or a trailing partial opener
        token), HOLD from that point onward in the buffer and yield only the
        sanitized prefix before it (possibly empty). Otherwise sanitize the whole
        joined text (stripping any complete span) and yield it, clearing the buffer.
        Clean text with no opener passes through unbuffered + unchanged (the runner's
        same-object identity → byte-identical, no latency).
        """
        if not self._active:
            # Tool-using agent (or no sanitize capability): pass through verbatim —
            # same chunk, same boundary, no buffering (the plan's "untouched" contract).
            return chunk
        joined = self._buffer + chunk
        if "<function_calls>" not in joined and "<invoke" not in joined:
            # Fast path: no (complete) opener token anywhere. A trailing PARTIAL opener
            # (e.g. the text ends with `<inv`) still has to be held — fall through.
            hold_idx = self._hold_from_index(joined)
            if hold_idx == -1:
                self._buffer = ""
                return joined

        hold_idx = self._hold_from_index(joined)
        if hold_idx == -1:
            # Every span present is COMPLETE (closed) → sanitize-strip + yield all.
            self._buffer = ""
            return self._sanitize(joined)

        # An open/partial span begins at hold_idx → hold its RAW tail for the next
        # chunk's close; yield only the sanitized prefix before it (the prefix cannot
        # contain an unclosed span by construction, but may hold an earlier COMPLETE
        # span the sanitizer strips).
        self._buffer = joined[hold_idx:]
        prefix = joined[:hold_idx]
        return self._sanitize(prefix) if prefix else ""

    def flush(self) -> str:
        """At stream end, sanitize + return any residual held tail (then clear).

        An unterminated opener still held at EOF is stripped here (mirrors the
        runner's WR-01 ``_UNTERMINATED_TOOL_XML_RE``), so the buffer never swallows
        legitimate trailing content silently. Returns ``""`` when nothing is held.
        """
        if not self._buffer:
            return ""
        out = self._sanitize(self._buffer)
        self._buffer = ""
        return out


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

    def __init__(self, milestone_sink: "MilestoneSink | None" = None) -> None:
        self._store: ScopedStore | None = None
        self._run_id: str | None = None
        # A.4 (Phase 43): the narrator milestone-card persist, INJECTED by the app layer
        # (``chat_narrator.persist_milestone_card``) — NEVER imported here (import-linter:
        # the kernel must not import ``app.*``). ``None`` (every current caller, incl. the
        # 5 characterization goldens) ⇒ the seam is DORMANT: no card is projected/persisted,
        # so the golden event/deliverable bytes are untouched (INV-3). The narrator is wired
        # LIVE only at the supervised SSE transport cutover (Part C / B.3, per CONTEXT §A.0).
        self._milestone_sink = milestone_sink

    def arm(self, store: ScopedStore, run_id: str) -> None:
        self._store = store
        self._run_id = run_id

    async def emit_milestone_card(self, event: dict) -> "tuple[bool, int, dict, str] | None":
        """Project + persist a ``chat_reply`` milestone card for one stamped engine event (A.4).

        Returns the injected sink's ``(created, seq, card, reply_eid)`` result — or ``None``
        when there is no injected ``milestone_sink``, the event is not a projectable milestone,
        or the DB write degraded. The engine loop (:meth:`execute`) uses the returned ``seq``
        to advance its OWN allocator PAST the card so the next engine event can never reuse the
        card's seq (which would collide on the 0024 per-run-seq constraint → the engine's
        best-effort persist would drop that event → a durable-log gap on reconnect,
        DEF-43-03-1), and to yield the card into the live stream (emit LIVE). ``reply_eid`` is
        used by the engine to stamp the live SSE ``chat_reply`` frame with the SAME event_id
        that the DB row carries — ensuring the FE ``seenRef`` dedup recognises a
        DB-fetched frame as a duplicate of the already-delivered live frame (FIX-175).

        DORMANT unless an app-layer ``milestone_sink`` was injected AND the sink is armed.
        The injected callback (``chat_narrator.persist_milestone_card(store, run_id, event)``)
        SELF-FILTERS — it returns ``None`` for a non-milestone event — so calling it per
        event is safe. Best-effort with the SAME degrade contract as :meth:`persist`: a
        DB-only failure (offline harness / schema-less) degrades to a warning so the live
        stream and deterministic deliverable are NEVER perturbed; any non-DB exception is a
        real bug and PROPAGATES. The card rides the run's OWN scoped store, so it can never
        leak or write a cross-owner row.
        """
        if self._milestone_sink is None or self._store is None or self._run_id is None:
            return None
        try:
            return await self._milestone_sink(self._store, self._run_id, event)
        except Exception as exc:  # noqa: BLE001 — a card must never break the live stream
            from sqlalchemy.exc import SQLAlchemyError

            if not isinstance(exc, SQLAlchemyError):
                raise
            logger.warning(
                "milestone-card persist failed for run %s (%s) — DB write degraded "
                "(offline harness / schema unavailable); stream unaffected (A.4 best-effort)",
                self._run_id, exc,
            )
            return None

    async def persist(
        self, seq: int, event_id: str, type: str, payload_json: dict
    ) -> int | None:
        """Append one ``run_events`` row for the stamped event (best-effort).

        Returns the seq the row ACTUALLY landed on, or ``None`` when the sink is unarmed
        or the write degraded. ``seq`` is a REQUEST, not a guarantee: the chat lane writes
        into the same per-run seq space on every turn, so a live run's engine event can
        find its seq already taken (FIX-240 / ISS-121). ``append_event_at_or_after``
        re-appends past the racing writer instead of losing the row; the caller must
        re-stamp the returned seq onto the event it is about to yield, because the SSE
        ``id:`` cursor is ``row.seq`` on replay and ``data["seq"]`` live.
        """
        if self._store is None or self._run_id is None:
            return None
        try:
            return await self._store.append_event_at_or_after(
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
            return None


PLANNER_TIMEOUT_SECONDS = 120.0  # SmartPlanner: single call (generous — large chained prompts run slower). On timeout it defaults to PROCEED, so it never discards agent work.
PLANNER_AGENT_ID = "deep-planner"

# The statuses a boot re-adopts. ``restore_non_terminal_runs`` filters on this set, so a
# run is auto-resumed by the next process IFF its status is in here — which makes the
# tuple the system's single definition of "still owed work", read by the startup scan AND
# by every caller that must decide whether a run would be picked up again (ISS-089's
# durable cancel).
#
# Module scope, not an inline literal: this value was copied into three places and cited by
# five different ``file:line`` values in one week, and every citation was wrong within days.
# One definition, imported — never re-stated (INV-12).
NON_TERMINAL_RUN_STATUSES: tuple[str, ...] = (
    "running", "planning", "clarifying", "waiting_for_user",
    "generating", "analyzing", "revising",
)

# API-001 (task.md R-05): the CANONICAL terminal-status set. Before this, "terminal"
# had at LEAST two separately-typed literal definitions:
#   * ``_review_gate_run_is_terminal`` (app/api/run_engine.py) hardcoded
#     ``("cancelled", "failed", "degraded")``;
#   * the ``/resume`` endpoint (app/api/run_commands.py) hardcoded
#     ``{"failed", "cancelled", "degraded"}`` as its RESUMABLE set (the same three
#     values, inverted meaning, independently spelled).
# Neither is caught by ``test_the_non_terminal_status_set_has_exactly_one_definition``
# (test_rest_answers_cancel.py), which only AST-scans for a literal copy of
# ``NON_TERMINAL_RUN_STATUSES``'s own 7-value set — a SEPARATE terminal-literal
# duplication was invisible to it. ``completed`` is included (a successfully
# finished run is just as terminal as a failed/cancelled/degraded one for the
# purposes of "may a mutating command still act on this run?" — API-001's actual
# question) even though today's call sites only ever compared against the
# cancelled/failed/degraded subset; every mutating REST command below now checks
# membership in THIS tuple, imported — never re-stated (INV-12, mirrors
# NON_TERMINAL_RUN_STATUSES's own precedent immediately above).
TERMINAL_RUN_STATUSES: tuple[str, ...] = ("completed", "cancelled", "failed", "degraded", "diverted")


def is_terminal_run_status(status_value: str | None) -> bool:
    """True iff ``status_value`` is one of :data:`TERMINAL_RUN_STATUSES`.

    The single predicate every mutating REST command (gate/answers/cancel/
    messages/revisions) should call before writing — API-001's shared
    "reject if terminal" fence. ``None``/unknown statuses are NOT terminal
    (fail toward "still running" rather than toward "silently allow a stale
    caller to believe a live run is dead" — mirrors
    ``_review_gate_run_is_terminal``'s existing "absent row → not terminal"
    default).
    """
    return status_value in TERMINAL_RUN_STATUSES

# ── Human-in-the-loop: always ask clarifying questions ────────────────────────
# (Migrated L6, 07-05) The former module-level always-clarify flag is GONE; the
# "force CLARIFY_REQUIRED on every run" behavior is now declared per-workflow by the
# manifest ``clarify.mode`` ("auto" ⇒ always clarify), read off the CompiledWorkflow
# at run entry (``compiled.clarify.mode == "auto"``). Every dispatchable manifest
# declares ``clarify.mode: auto`` today, so behavior is byte-identical (INV-1/INV-3).


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


async def _retry_sleep(seconds: float) -> None:
    """Patchable backoff seam for the per-step retry wrapper (RESUME-02 / 12-02).

    A module-level async function so scripted tests monkeypatch it to a no-op
    (keeping the retry tests fast) without touching the wrapper's control flow.
    Honors ``RetryPolicy.backoff_seconds`` between transient-classified attempts;
    the bounded attempt loop (≤ ``max_attempts``) is the T-12-02-DOS guard.
    """
    if seconds and seconds > 0:
        await asyncio.sleep(seconds)


# ---------------------------------------------------------------------------
# Declarative routing seam (MAN-04 / MAN-05)
# ---------------------------------------------------------------------------
#
# The engine sources the FOUR routing concerns — step sequence + agent ids,
# deliverable spec, clarify defaults, and the planner-skip flag — from the
# CompiledWorkflow produced by the manifest + compiler layer (agents/workflows),
# NOT from the legacy hardcoded dicts (get_pipeline_agents / per-pipeline default
# question lists / the legacy planner-skip flag). The legacy `pipeline_type` label is reduced to an
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


def _normalize_run_images(images: "list | None") -> list[dict]:
    """Canonicalize run-supplied images onto the transient carrier shape (image-input).

    Maps each incoming image dict to ``{"mime_type": <str>, "data": <base64 str>}``
    (Locked Decision #1 — base64 passed through verbatim, no decode). Reads
    ``mime_type`` (accepting a ``mimeType`` alias defensively) and ``data``; DROPS any
    entry missing either. Returns ``[]`` for ``None``/empty. Pure, dormant by default
    (every existing caller passes nothing ⇒ ``[]``).
    """
    out: list[dict] = []
    for img in images or []:
        if not isinstance(img, dict):
            continue
        mime = img.get("mime_type") or img.get("mimeType")
        data = img.get("data")
        if not mime or not data:
            continue
        out.append({"mime_type": mime, "data": data})
    return out


def _drain_turn_images(ectx) -> None:
    """Drain per-turn images (30-03) off ``ectx.pending_turn_images`` onto the ONE-SHOT
    ``ectx.turn_images_once`` carrier.

    The UPLD-02 residue seam: images attached to an in-flight chat turn were enqueued
    onto the generic ``pending_turn_images`` queue by ``chat_router.apply_turn_images``.
    Called BEFORE ``_compose_input_blocks`` at each dispatch. Consume-once (HI-01): the
    pending images move onto the ONE-SHOT ``turn_images_once`` carrier — DISTINCT from the
    sticky run-entry ``run_images`` — which ``_compose_input_blocks`` renders into exactly
    THIS dispatch's blocks and then clears, so a per-turn image reaches exactly ONE
    dispatch and never re-delivers on a later one. (Draining onto the sticky ``run_images``
    was the pre-fix bug: it re-attached the image to every subsequent ``injects:[images]``
    dispatch for the rest of the run.) APPEND (not replace) so an image enqueued across a
    non-``injects:[images]`` dispatch — which does not consume ``turn_images_once`` — is
    still delivered to the next images-opted agent. DORMANT by default — an empty queue
    drains nothing (INV-3 byte-parity). Payload-transient (ND-10): never persisted. Keyed
    on the generic queue only (SC-001/INV-1).
    """
    pending = getattr(ectx, "pending_turn_images", None)
    if not pending:
        return
    ectx.turn_images_once = (getattr(ectx, "turn_images_once", None) or []) + list(pending)
    ectx.pending_turn_images = []


def _dispatch_payload(context_message: str, input_blocks: list) -> "str | list":
    """Wrap the text context message with any multimodal input blocks (image-input).

    Split-transport (Locked Decision #3): returns the bare ``context_message`` str
    when ``input_blocks`` is falsy (the dormant default — zero re-baseline, the
    ``agent_input`` event + goldens stay byte-identical), else a content-list
    ``[{"type":"text","text":context_message}, *input_blocks]`` handed to the model
    dispatch. ``HumanMessage(content=...)`` accepts either shape natively.
    """
    if not input_blocks:
        return context_message
    return [{"type": "text", "text": context_message}, *input_blocks]


def resolve_alias(pipeline_type: str) -> str:
    """Resolve the legacy run label to a manifest id (MAN-05).

    ``od_prototype`` -> ``prototype``; every real key resolves to itself. This is
    the SINGLE point that maps the legacy ``pipeline_type`` label onto a manifest
    id for routing. Sourced from the central capability registry, which lifts
    ``agents.registry._OD_ALIAS_BASE`` (single source of truth) — never
    re-hardcoded here.
    """
    return _CAPABILITY_REGISTRY.resolve_alias(pipeline_type)


import functools as _functools

@_functools.lru_cache(maxsize=None)
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


def _known_skill_ids() -> set[str]:
    """The global skills catalog's ids (ADR-0010).

    Used by ``_apply_selections`` to drop a USER-supplied per-step skill id that
    no longer resolves, so a workflow saved when a skill existed keeps running
    after that skill leaves the catalog instead of tripping the assert in
    ``factory._resolve_step_skills``. Imported lazily, and inside a try, because
    the catalog lives in the ``app`` layer: the kernel must not hard-depend on it
    (INV-1), and a catalog that cannot be read must degrade to "drop nothing new"
    rather than silently stripping every skill off the run.
    """
    try:
        from app.agents.skills_catalog import list_global_skills

        return {entry.id for entry in list_global_skills()}
    except Exception:  # pragma: no cover - defensive
        logger.warning(
            "engine: skills catalog unreadable — skipping the unknown-skill-id filter"
        )
        return set()


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


def _dead_nav_line(nav) -> str:
    """Honest one-line fix-message for a dead nav route, by its ACTUAL failure class.

    A dead nav (``nav.ok is False``) has one of two distinct causes; the message must
    name the real one so the fix-loop gets the right defect signal:

      * ``nav.activated is None`` — the route activated NOTHING (no ``<section
        data-page>`` became active → a blank page). This is the null-honesty case: the
        render read found no real page section (never coerced to a nav-link name).
      * otherwise — the route activated a real-but-WRONG section (``activated`` != the
        ``expected`` resolved id): a mis-routed nav, not a blank page.

    Pure + side-effect-free — shared by ``_select_issues_to_fix`` AND the build residual
    assembly in ``_run_validation_fix_loop`` so the two can never diverge.
    """
    if getattr(nav, "activated", None) is None:
        return (
            f"dead nav link: '{nav.href}' activated NOTHING (no <section data-page> "
            f"became active — blank page)"
        )
    return (
        f"dead nav link: '{nav.href}' activated '{nav.activated}' but expected "
        f"'{getattr(nav, 'expected', None)}'"
    )


def _select_issues_to_fix(
    sres,
    rres,
    baseline_static: "set[str] | None" = None,
    baseline_console: "set[str] | None" = None,
    require_render: bool = True,
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

    # Render contributes only when the headless render actually ran — routed through
    # the SINGLE render-coverage policy helper (RENDER-SEAM). ``status == "ok"`` iff
    # ``rres.available`` (the require_render value only distinguishes the skip flavors,
    # which contribute no lines either way), so this is byte-identical to the prior
    # ``if getattr(rres,'available',False)`` for an available render.
    if render_coverage_status(rres, require_render) == "ok":
        # (2) New console errors — filtered by the console baseline (empty ⇒
        #     all, = today). Prefixed exactly as today's error_lines.
        for err in getattr(rres, "console_errors", None) or []:
            if err not in base_console:
                selected.append(f"console error: {err}")

        # (3) Hard render-breakage, ALWAYS included regardless of baseline:
        #     uncaught page exceptions …
        for err in getattr(rres, "page_errors", None) or []:
            selected.append(f"uncaught exception: {err}")

        # … and dead nav links — worded by their ACTUAL failure class (blank vs
        #     wrong-section) via the shared ``_dead_nav_line`` helper.
        for nav in getattr(rres, "nav_results", None) or []:
            if not getattr(nav, "ok", True):
                selected.append(_dead_nav_line(nav))

        # (4) Nav-COVERAGE findings (a multi-section SPA that exercised 0 nav) —
        #     always-included hard breakage (RENDER-NAV-COV). Goldens have no
        #     coverage_errors so this is byte-identical for the existing manifests.
        for msg in getattr(rres, "coverage_errors", None) or []:
            selected.append(f"nav coverage: {msg}")

    # De-duplicate while preserving first-seen order.
    seen: set[str] = set()
    deduped: list[str] = []
    for line in selected:
        if line not in seen:
            seen.add(line)
            deduped.append(line)
    return deduped


def _make_exec_recorder(runner):
    """Build the sync→async exec-audit recorder the host seam wires (CR-01).

    The workspace recorder contract is synchronous and step-FREE:
    ``recorder(argv, *, outcome, exit_code=None, duration_ms=None,
    policy_snapshot=None, output_digest=None)`` (see ``local._noop_recorder``).
    But the audit sink ``KernelServices.record_exec_run(step, argv, outcome, ...)``
    is an async coroutine. This adapter bridges the two:

      1. **Step id is RUN-scoped here.** The recorder is wired ONCE at run entry,
         before the per-step dispatch loop, so no reliable per-step id is
         reachable from this seam. We pass a clearly-named ``""`` placeholder for
         ``step`` — the row is still owner/workspace/run-scoped and outcome-true;
         per-step attribution is a future enhancement (D-03 makes exec a
         run-scoped grant, so a run-scoped audit row is consistent with the model).
      2. **Best-effort, never raises into ``exec_command``.** The recorder is
         documented best-effort (Pitfall 6 / INV-3): a failure here must NEVER
         turn ``denied`` into ``TypeError`` or break the ``allowed``/``killed``
         contract. We schedule the async write on the running loop via
         ``loop.create_task`` when one exists, else swallow with a debug log.
    """

    def _recorder(
        argv,
        *,
        outcome: str,
        exit_code: int | None = None,
        duration_ms: int | None = None,
        policy_snapshot=None,
        output_digest: str | None = None,
    ) -> None:
        # RUN-scoped step id: the recorder is wired at run entry, before any
        # per-step tracking exists in scope, so attribute the row to the run with
        # an explicit "" placeholder rather than a misleading fabricated step id.
        step_id = ""
        try:
            coro = runner.record_exec_run(
                step_id,
                list(argv),
                outcome,
                exit_code=exit_code,
                duration_ms=duration_ms,
                policy_snapshot=policy_snapshot,
                output_digest=output_digest,
            )
        except Exception as exc:  # noqa: BLE001 — audit must NEVER break exec
            logger.debug("exec recorder build failed (%s) — audit skipped", exc)
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # No running loop at this call site — best-effort: close the coroutine
            # to avoid a "never awaited" warning and skip the write. exec_command
            # in the live path always runs inside the engine's event loop, so this
            # branch is the defensive offline fallback only.
            try:
                coro.close()
            except Exception:  # noqa: BLE001
                pass
            logger.debug("exec recorder: no running loop — audit skipped")
            return
        try:
            loop.create_task(coro)
        except Exception as exc:  # noqa: BLE001 — best-effort schedule
            try:
                coro.close()
            except Exception:  # noqa: BLE001
                pass
            logger.debug("exec recorder schedule failed (%s) — audit skipped", exc)

    return _recorder


class ExecutionEngine:
    """Universal Execution Engine — single entry point for all workflows."""

    def __init__(self) -> None:
        self._resolver = WorkflowResolver()
        self._store = get_artifact_store()
        self._state_machine = get_state_machine()
        # ── 12-09 Gap 2a: OPTIONAL injected engine→WS live-task bridge ──────────
        # The kernel MUST NOT import app.api (import-linter forbidden direction),
        # so live delivery for an AUTO-RESUMED run is wired as injected callables
        # set from the app layer (app/main.py startup, the single wiring site).
        # All three default None — the bridge is DORMANT for every other
        # construction path (offline tests, characterization harness), keeping
        # resume_run byte/event-identical when unset. Workflow-agnostic: keyed by
        # run_id only (SC-001 — the kernel knows no workflow by name).
        #   _resume_register_queue(run_id) -> asyncio.Queue
        #       returns/creates the WS live queue for the run and records it in
        #       the WS pipeline-queue registry, so a reconnect mid-resume finds a
        #       live queue and takes the live-attach branch.
        #   _resume_register_task(run_id, task) -> None
        #       records the resume driver task in the WS pipeline-task registry
        #       (called at the create_task site in restore_non_terminal_runs).
        #   _resume_cleanup(run_id) -> None
        #       drops the queue+task entries when the resumed drive finishes, so
        #       a completed resume never leaves a stale live registration.
        self._resume_register_queue: Callable[[str], asyncio.Queue] | None = None
        self._resume_register_task: Callable[[str, asyncio.Task], None] | None = None
        self._resume_cleanup: Callable[[str], None] | None = None
        # ── RESUME-10: the live-layer callbacks a RESUMED run must thread, injected
        # app-side (app/main.py restore-scan site) from the SAME callables the REST/SSE
        # launch path threads into execute() (run_commands.py). resume_run bypasses the
        # execute() wrapper (it calls _execute_impl directly), so the wrapper's callback
        # threading never reached a resumed run — these slots carry the trio into
        # resume_run's own drive loop instead. Typed as the generic engine-side aliases
        # so NO app symbol crosses the import boundary (import-linter 4/0). All None (the
        # goldens + every non-app driver) keeps the resume live-wire DORMANT — a resumed
        # offline run is byte/event-identical (INV-3).
        #   _resume_milestone_sink(store, run_id, event) -> (created, seq, card) | None
        #       the narrator projector — projects a chat_reply milestone card per
        #       projectable lifecycle event (self-filtering).
        #   _resume_live_ectx_register(run_id, ectx) -> None
        #       registers the resumed run's rebuilt ectx so _live_ectx_for_run resolves
        #       it for mid-run steering / per-turn images / Concierge.
        #   _resume_live_ectx_unregister(run_id) -> None
        #       drops the ectx registration in resume_run's finally (no _LIVE_ECTX leak).
        self._resume_milestone_sink: "MilestoneSink | None" = None
        self._resume_live_ectx_register: "LiveEctxRegister | None" = None
        self._resume_live_ectx_unregister: "LiveEctxUnregister | None" = None
        # ── BUG-R03: the app-layer resume output-column persister, injected app-side
        # (app/main.py restore-scan site) from the SAME callable the REST/SSE launch
        # driver's terminal block folds through. Fired from _drive_resumed_stream's
        # finally so the RESTART auto-resume path (branch b) persists the output-bearing
        # columns (output/agent_outputs/token_usage/duration/deliverable_*) the resume
        # tier is otherwise structurally silent on. None (goldens + non-app drivers) →
        # DORMANT, byte/event-identical resume (INV-3). Keyed on run_id (SC-001).
        #   _resume_output_persist_sink(run_id) -> awaitable
        self._resume_output_persist_sink: "ResumeOutputPersist | None" = None
        # ── ISS-084: the per-run cooperative cancel Event lookup, injected app-side
        # (app/main.py, the SAME wiring site as the hooks above) so a RESUMED run can be
        # stopped at all. Resolved ONCE in _drive_resumed_stream — the single funnel every
        # resume driver reaches the kernel through — and handed to _execute_impl, which
        # threads it into KernelServices and thence into every cooperative boundary.
        #   _resume_cancel_event(run_id) -> asyncio.Event | None
        self._resume_cancel_event: "ResumeCancelEvent | None" = None

    async def _persist_budget_snapshot_if_active(
        self, ectx: ExecutionContext, *, force: bool = False
    ) -> None:
        """Persist the per-run BudgetSnapshot — STRICTLY CONDITIONAL on fan-out activity.

        OBS-01: writes ``workflow_runs.budget_snapshot_json`` at the run-termination
        boundaries (completion / abort / cancel). The write is GATED so existing
        workflows (no fanout, no budget activity) stay byte/event-identical — a run that
        never fanned out (``snapshot.subagents == 0`` and no token/wall-clock spend)
        writes NOTHING (the exec-workspace conditional-provisioning precedent, Pitfall 3).
        ``force=True`` (the BudgetExceeded abort) persists regardless (a breach means
        fan-out ran). Reaches the persist through the runner handle (None-degrading);
        never aborts the run.
        """
        budget = getattr(ectx, "budget", None)
        runner = getattr(ectx, "runner", None)
        if budget is None or runner is None:
            return
        persist = getattr(runner, "persist_budget_snapshot", None)
        if persist is None:
            return
        snapshot = budget.spent()
        active = (
            getattr(snapshot, "subagents", 0)
            or getattr(snapshot, "tokens", 0)
            or getattr(snapshot, "wall_clock_seconds", 0.0)
        )
        if not active and not force:
            return
        await persist(snapshot)

    @staticmethod
    def _collect_partial_fragments(ectx: ExecutionContext) -> list[dict]:
        """Surface the completed workers' 11-03 fragment artifacts (OBS-01 abort path).

        On a BudgetExceeded abort the completed workers' fragment artifacts — the typed
        lineage-tracked refs persisted by 11-03's ``write_fragment_artifact`` BEFORE
        merge — are surfaced so partial results survive the abort (pending workers never
        spawned). Reads the per-run typed ``ArtifactGraph`` for fragment-kind refs; each
        entry carries the producer step/agent + the artifact-ref id. Best-effort: an
        unreadable graph degrades to an empty list (never aborts the abort path).
        """
        graph = getattr(ectx, "artifacts", None)
        run_id = getattr(ectx, "run_id", "")
        if graph is None or not run_id:
            return []
        fragments: list[dict] = []
        try:
            for ref in graph.tree(run_id):
                if getattr(ref, "kind", None) in ("file_bundle", "fragment"):
                    fragments.append(
                        {
                            "artifact_ref": getattr(ref, "id", None),
                            "producer_step": getattr(ref, "producer_step", None),
                            "producer_agent": getattr(ref, "producer_agent", None),
                            "location": getattr(ref, "location", None),
                        }
                    )
        except Exception as exc:  # noqa: BLE001 — partial-results read must never abort
            logger.warning("partial-fragment surfacing failed: %s", exc)
            return []
        return fragments

    def _specs_from_plan(self, steps: list) -> list:
        """Load each step's AgentSpec, overlaying the composer's display_name (FIX-266)
        and the step's declared ``produces``/``consumes`` (R-29).

        The single source for rebuilding ``agents`` from a compiled plan's steps —
        used by execute() and both resume seams, which must agree or a resumed
        composed run reports every step under its template's name ("Custom Agent").

        R-29 — why produces/consumes must be overlaid here: a composed step's runtime
        spec is ``replace(base_spec, id="custom-agent:<instance_id>")`` (loader.py), so
        it inherits the produces/consumes of ``agents/prompts/custom-agent/AGENT.md``,
        which declares NEITHER. ``_filter_consumed_outputs`` reads those fields off the
        objects in ``ordered_agents`` — these specs, not the compiled Steps — so without
        this overlay a manifest's declaration is silently inert and every composed step
        gets ``context_sources: []``. That is observable as a judging step being shown
        only the brief and asked to assess an output it was never given.
        """
        import dataclasses

        from agents.loader import load_agent_spec

        specs = []
        for s in steps:
            overlay: dict = {}
            if getattr(s, "display_name", ""):
                overlay["name"] = s.display_name
            if getattr(s, "produces", None):
                overlay["produces"] = list(s.produces)
            if getattr(s, "consumes", None):
                overlay["consumes"] = list(s.consumes)
            base = load_agent_spec(s.agent_id)
            specs.append(dataclasses.replace(base, **overlay) if overlay else base)
        return specs

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
        images: list | None = None,
        gate_agent_ids: list[str] | None = None,
        parent_run_id: str | None = None,
        model_overrides: dict[str, str] | None = None,
        selections: dict | None = None,
        event_queue: "asyncio.Queue | None" = None,
        milestone_sink: "MilestoneSink | None" = None,
        live_ectx_register: "LiveEctxRegister | None" = None,
        live_ectx_unregister: "LiveEctxUnregister | None" = None,
        compiled_override: "CompiledWorkflow | None" = None,
        trigger_depth: int = 0,
        workspace_id_override: str | None = None,
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

        ``milestone_sink`` (A.4, Phase 43): an OPTIONAL app-layer callback that persists a
        ``chat_reply`` milestone card per projectable lifecycle event. ``None`` (every current
        caller, incl. the 5 characterization goldens) keeps the seam DORMANT — byte/event-
        identical. It is injected LIVE only at the supervised SSE transport cutover
        (CONTEXT §A.0 / Part C / B.3), never here and never by the golden harness.

        ``live_ectx_register`` / ``live_ectx_unregister`` (A.3, Phase 43): an OPTIONAL app-layer
        register/unregister callback PAIR. When ``live_ectx_register`` is provided, the engine
        registers this run's in-process ``ExecutionContext`` (keyed by ``pipeline_run_id``) right
        after it is constructed, so the app-layer ``_live_ectx_for_run`` resolves the RUNNING ectx
        for mid-run steering + per-turn images; ``live_ectx_unregister`` runs in the ``finally``
        below (ALWAYS — on normal completion, exception, or an early ``GeneratorExit`` if the
        consumer stops draining) so the registry never leaks. Both ``None`` (the goldens + every
        current WS caller) keeps the seam DORMANT — byte/event-identical. Keyed on
        ``pipeline_run_id`` ONLY (SC-001/INV-1), so two concurrent runs never cross-deliver.

        ``trigger_depth`` (spec 014 R-18/R-19): the cross-workflow trigger-chain depth
        this run STARTS at, stamped onto the ``ExecutionContext`` built below. ``0``
        (the default — every HTTP/WS/golden caller) means "root of its own chain" and
        is byte/event-identical to before. ``run_trigger_workflow`` passes
        ``parent_ectx.trigger_depth + 1`` down through ``_launch_run_core`` →
        ``_drive_launch_to_queue`` → here, which is what makes the fixed-ceiling-of-5
        guard in that delegate fire on a REAL chain instead of a hand-built context.

        ``workspace_id_override`` (spec 014 R-15): execute IN AN EXISTING workspace
        instead of minting a fresh one. ``None`` (every HTTP/WS/golden caller) keeps
        the mint-a-new-workspace default — byte/event-identical. Set only for a run
        minted by ``run_trigger_workflow``, which must share its triggering run's
        workspace so both runs land in one budget aggregate and the ``workspace_id``
        already stamped on the new ``WorkflowRun`` row is not overwritten.
        """
        sink = _RunEventSink(milestone_sink=milestone_sink)
        # R-23 amendment — the on-disk run trace. The engine ALREADY emits every
        # fact worth tracing (each tool call and its arguments, each result, the
        # model's reasoning and output, gates, clarify rounds, failures) as a typed
        # event, and every one of them passes through the stamping boundary a few
        # lines below. Tracing there means the engine keeps no per-event logging
        # calls of its own and cannot grow a gap: a new event type is traced the
        # day it is added. `.logs/run-logs.jsonl` previously held step boundaries
        # only, so reading a broken run meant reading the console or the database.
        _trace = RunTrace(RunSandbox(user_id or "anon", pipeline_run_id).root)
        # Manual monotonic allocator (NOT itertools.count): a milestone card projected below
        # is drawn from this SAME per-run seq space, so the loop must be able to advance the
        # counter PAST the card's persisted seq — otherwise the engine's next event would reuse
        # the card's seq, collide on the 0024 (run_id, seq) constraint, and (persist being
        # best-effort) silently DROP that engine event → a durable-log gap on reconnect
        # (DEF-43-03-1). DORMANT-neutral: with no milestone_sink the card branch never fires,
        # so next_seq increments 1,2,3,… exactly like the old itertools.count (goldens identical).
        next_seq = 1
        try:
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
                images=images,
                gate_agent_ids=gate_agent_ids,
                parent_run_id=parent_run_id,
                model_overrides=model_overrides,
                selections=selections,
                _sink=sink,
                event_queue=event_queue,
                live_ectx_register=live_ectx_register,
                compiled_override=compiled_override,
                trigger_depth=trigger_depth,
                workspace_id_override=workspace_id_override,
            ):
                # Stamp exactly once, at the boundary, so seq is contiguous across the
                # nondeterministically-interleaved build loop. Events always carry a
                # "data" dict in this engine; guard defensively anyway.
                data = event.get("data")
                if not isinstance(data, dict):
                    data = {}
                    event["data"] = data
                seq = next_seq
                next_seq += 1
                event_id = str(uuid.uuid4())
                data["seq"] = seq
                data["event_id"] = event_id
                # Durable sink (best-effort — see docstring). Persist the now-stamped
                # event; a DB/FK failure must not break the live stream.
                #
                # FIX-240 (ISS-121): the row may land PAST the requested seq — the chat
                # lane allocates from this same per-run space on every turn, so a live
                # run's engine event can find its seq already taken. Re-stamp the seq the
                # row actually got and advance the allocator past it: the SSE id: cursor
                # is row.seq on replay but data["seq"] live, so a divergence corrupts
                # Last-Event-ID resumption. Identical to the milestone-card re-sync below.
                # ``None`` (unarmed sink / degraded write — the goldens) ⇒ no re-stamp, so
                # the offline seq stays contiguous 1,2,3,… (SAFE-03 / INV-3).
                actual_seq = await sink.persist(seq, event_id, event.get("type", ""), data)
                if actual_seq is not None and actual_seq != seq:
                    data["seq"] = actual_seq
                    if actual_seq >= next_seq:
                        next_seq = actual_seq + 1
                _trace.observe(event)
                yield event
                # A.4 (Phase 43, DEF-43-03-1): project + persist a chat_reply milestone card for
                # this event via the INJECTED narrator callback (self-filtering; DORMANT when
                # milestone_sink is None — the 5 goldens + every non-cutover caller). The card is
                # persisted at the store's next contiguous seq (max+1), so we ADVANCE next_seq
                # PAST it — the engine's next event can then never reuse the card's seq (a collision
                # would drop that engine event → durable-log gap). The card is ALSO yielded so it
                # reaches the live event_queue → SSE (emit LIVE), stamped with the SAME event_id
                # (chat_reply:{source}) the persisted row carries so a reconnect replay dedups it.
                card_result = await sink.emit_milestone_card(event)
                if card_result is not None:
                    _created, _card_seq, _card, _reply_eid = card_result
                    if _card_seq >= next_seq:
                        next_seq = _card_seq + 1
                    if _created:
                        yield {
                            "type": "chat_reply",
                            "data": {
                                **_card,
                                "seq": _card_seq,
                                # FIX-175: use the SAME event_id the DB row carries so the
                                # FE seenRef can match live-delivered frames against
                                # appendFrames-fetched frames.  The old f"chat_reply:{event_id}"
                                # (raw source UUID) diverged from the DB's idempotency key for
                                # "Run started" ("chat_reply:pipeline_start:run:{run_id}"),
                                # causing FIX-172's appendFrames to treat it as unseen and add
                                # a second "Run started" card.
                                "event_id": _reply_eid,
                            },
                        }
        finally:
            # Flush any deltas buffered when the stream ended (or was abandoned
            # mid-run), so a cancelled/failed run's last output is still on disk.
            _trace.flush()
            # A.3: ALWAYS deregister the run's live ectx (normal completion, exception, or an
            # early GeneratorExit if the consumer stops draining) so the process-local registry
            # never leaks a terminated run's context. DORMANT when live_ectx_unregister is None
            # (the goldens + WS callers) — a no-op that cannot perturb the event stream (INV-3).
            if live_ectx_unregister is not None:
                try:
                    live_ectx_unregister(pipeline_run_id)
                except Exception:  # noqa: BLE001 — teardown must never mask the real outcome
                    logger.warning(
                        "live_ectx_unregister failed for run %s",
                        pipeline_run_id,
                        exc_info=True,
                    )

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
        images: list | None = None,
        gate_agent_ids: list[str] | None = None,
        parent_run_id: str | None = None,
        model_overrides: dict[str, str] | None = None,
        selections: dict | None = None,
        _sink: "_RunEventSink | None" = None,
        _resume_from: int = 0,
        _is_resume: bool = False,
        _clarify_replay: dict | None = None,
        event_queue: "asyncio.Queue | None" = None,
        live_ectx_register: "LiveEctxRegister | None" = None,
        compiled_override: "CompiledWorkflow | None" = None,
        trigger_depth: int = 0,
        workspace_id_override: str | None = None,
    ) -> AsyncGenerator[dict, None]:
        """Execute a workflow end-to-end, yielding WebSocket events.

        ``_resume_from`` (RESUME-04 / WAVE-03, D-06): when > 0 this is a durable
        IN-PROCESS RESUME of a run interrupted by a backend restart. The SAME entry
        wiring runs (the ExecutionContext is rebuilt via this one construction path —
        no copy-paste fork, Pitfall 2), but the planner/clarifier phases are SKIPPED
        (a resumed run already cleared its gate) and the SINGLE per-step dispatch loop
        skips the already-completed steps (``i < _resume_from``) so it re-enters at the
        FIRST incomplete step. Completed steps' artifacts are reused via the 12-02
        content-hash key; a completed wave's workers are skipped via the durable
        ``wave_runs``/``subagent_runs`` rows (mid-wave resume). ``_resume_from == 0``
        (every normal run) is byte/event-identical — the resume path is dormant.

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
            parent_run_id: For revision pipelines — the pipeline_run_id of the
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
        # ── Seed declared od-template resources into the run sandbox (data-driven,
        # INV-1: keyed off od_context content, never a workflow name). The template's
        # SKILL.md instructions name workspace paths ("read assets/template.html",
        # "references/layouts.md"); seeding them makes those instructions executable
        # for file-granted agents instead of inducing fabricated tool syntax on
        # tool-less prompts. Best-effort: a seed failure degrades to the inline
        # template block already carried in the inject.
        for _seed_rel, _seed_content in ((od_context or {}).get("template_files") or {}).items():
            try:
                sandbox.write(_seed_rel, _seed_content)
            except Exception:  # noqa: BLE001 — never abort a run on seed failure
                logger.warning(
                    "od template seed failed for %s (run %s)",
                    _seed_rel, pipeline_run_id, exc_info=True,
                )
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
        # (parent-seed source for revision runs) ride on the context too. ctx.artifacts is
        # the per-run typed graph (default_factory=ArtifactGraph — 05-04 dual-write target).
        ectx = ExecutionContext(
            run_id=pipeline_run_id,
            owner_id=owner_id,
            disk_principal=disk_principal,
            od_context=od_context,  # threaded into AgentContext per agent
            run_images=_normalize_run_images(images),  # image-input Wave 1 carrier (dormant by default)
            gate_agent_ids=gate_agent_ids,
            parent_run_id=parent_run_id,
            cancel_event=cancel_event,
            # spec 014 R-18/R-19: the constructor-time chain depth (context.py's own
            # docstring: "the '+1' propagation logic itself lives at the caller"). 0 for
            # every normal launch ⇒ DORMANT / byte-identical; parent+1 when this run was
            # minted by run_trigger_workflow, which is what lets that delegate's
            # exact-equality-to-5 guard fail closed on the 6th hop of a real chain.
            trigger_depth=trigger_depth,
        )
        # ── A.3 (Phase 43): register the RUNNING run's live in-process ExecutionContext ──
        # Keyed by run_id into the app-layer process-local registry via the INJECTED callback
        # (no engine→app import — import-linter 4/0). Once registered, the app-layer
        # ``_live_ectx_for_run(run_id)`` resolves THIS ectx, so a mid-run chat steering note
        # (=== USER GUIDANCE ===) or a per-turn image posted to POST /messages drains onto the
        # NEXT agent dispatch (via ectx.steering_notes / ectx.pending_turn_images, consumed in
        # _compose_context_message / _drain_turn_images below). The matching UNREGISTER runs in
        # the execute() wrapper's finally (ALWAYS — no leak). DORMANT when the callback is None
        # (the goldens + every current caller): a no-op ⇒ byte/event-identical (INV-3). Keyed on
        # run_id ONLY (SC-001/INV-1) so two concurrent runs never cross-deliver steering/images.
        if live_ectx_register is not None:
            try:
                live_ectx_register(pipeline_run_id, ectx)
            except Exception:  # noqa: BLE001 — a registry failure must never break the run
                logger.warning(
                    "live_ectx_register failed for run %s", pipeline_run_id, exc_info=True
                )
        # ISS-033: run-usage accumulator for the model calls that run OUTSIDE the
        # per-agent stream and so never reach ``results``. Three sources feed it:
        # the SmartPlanner and the clarify question-generation one-shots (43-04, via
        # the shared cached_invoke), and the validation fix-loop's sub-agent (ISS-033-A
        # / FIX-230, via the KernelServices ``aux_usage_sink``). All of their tokens
        # historically dropped on the floor. Folded into the run totals at
        # pipeline_complete (below).
        #
        # On the offline characterization goldens the two one-shots contribute nothing
        # (the planner is neutralised, clarify.mode="off") but the FIX-LOOP DOES fire
        # on both prototype goldens, so this list is non-empty there and the run token
        # totals grow. That is golden-neutral only because the totals are normalized
        # (_VOLATILE_REQUIRED_KEYS) and the cost/cache keys stripped
        # (_VOLATILE_STRIP_KEYS) — verified by re-running the goldens, not assumed.
        aux_token_usage: list[dict] = []
        # KAN-73: wire the live WS queue onto ectx so KernelServices.emit_hook_event
        # can push hook_run events into the real-time stream. The queue is the same
        # asyncio.Queue the WS drainer reads from (created in _get_or_create_queue
        # before engine.execute() is called). Setting it here (before KernelServices
        # is constructed and before any hook fires) is the single wiring point —
        # no new engine param, no import of app.api from the kernel. Best-effort:
        # a None queue (offline/test harness) leaves emit_hook_event a no-op.
        if event_queue is not None:
            ectx.event_queue = event_queue  # type: ignore[attr-defined]
        # RESUME-04: mark the context as a durable in-process resume when re-entered at
        # an offset. The wave_scheduler strategy reads ``is_resuming`` to enable its
        # mid-wave worker filter (a completed wave/worker is not re-invoked). False for
        # every normal run (the mid-wave filter is dormant — byte/event-identical).
        ectx.is_resuming = _resume_from > 0
        # T16 (R-12, R-14, R-20, F-06): the run's topic slug, computed ONCE here from
        # the user's run input and reused by every step — never recomputed per step,
        # or two steps (the preamble's filename vs. the artifact-guarantee check)
        # could disagree. Threaded onto AgentContext.topic (T11's factory.py already
        # consumes it) and read back off ``ectx.topic`` by the artifact-guarantee
        # check and the roster builder in ``_run_agent`` (T16/T17).
        ectx.topic = topic_slug(user_message)  # type: ignore[attr-defined]
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
            # ── RESUME-04 workspace binding (Pitfall 2 — no binding drift) ───────────
            # ``create_workspace`` mints a NEW workspace_id every call, but the run's
            # durable rows (wave_runs / subagent_runs / artifact_refs / run_events) were
            # written under the ORIGINAL workspace_id. The owner+workspace-scoped resume
            # reads MUST use that same id or they resolve to ∅ (the mid-wave skip would
            # silently re-run completed workers). On resume, RECOVER the original
            # workspace_id from a durable row (owner-scoped) and reuse it; only mint a
            # fresh one for a normal run or when no prior workspace exists.
            #
            # CR-01: recover the workspace whenever this is a RESUME (``_is_resuming``),
            # NOT only when the offset is > 0. A run interrupted with a durable run_events
            # tail but no COMPLETED step (offset 0) must still bind to its ORIGINAL
            # workspace, else its resumed events are stamped with a fresh workspace_id and
            # the owner+workspace-scoped ``after_seq`` reconnect read resolves to ∅ —
            # the reconnecting client never sees the resumed tail (RESUME-03). A run with
            # no durable row (offline harness) recovers ``None`` → mints fresh →
            # byte/event-identical to the prior behavior.
            _recovered_ws = (
                await self._recover_workspace_id(owner_id, pipeline_run_id)
                if (_is_resume or _resume_from > 0)
                else None
            )
            if _recovered_ws is not None:
                ectx.workspace_id = _recovered_ws
            elif workspace_id_override:
                # ── spec 014 R-15: an INHERITED workspace (cross-workflow trigger) ──
                # A run minted by ``run_trigger_workflow`` must execute IN THE SAME
                # workspace as the run that triggered it — that shared id is what puts
                # both runs' spend in one ``BudgetManager.workspace_ceiling`` aggregate
                # and what AC-05 asserts on the two ``WorkflowRun`` rows. Minting a
                # fresh workspace here would silently overwrite the id
                # ``_launch_run_core`` already stamped on the row (via ``set_run_scope``
                # a few lines below), so the inheritance has to be honoured HERE, not
                # only at mint time. Same shape as the resume recovery above: an
                # explicitly-supplied id is reused instead of created. ``None`` (every
                # HTTP/WS/golden caller) ⇒ mint fresh, byte/event-identical (INV-3).
                ectx.workspace_id = workspace_id_override
            else:
                ectx.workspace_id = await scoped_store.create_workspace(pipeline_run_id)
            scoped_store._workspace_id = ectx.workspace_id  # stamp later writes
            # ── 12-09 Gap 2c: stamp workflow_runs.workspace_id CONSISTENTLY with
            # the run_events sink via the EXISTING set_run_scope seam (INV-3/
            # INV-12 — the revision path already rides it; no parallel stamper).
            # The WS run path creates the workflow_runs row BEFORE the workspace
            # exists (workspace_id NULL), while every run_events row carries the
            # real workspace_id — so the owner+workspace-scoped get_run on
            # reconnect never matched and pipeline_reconnected.status was null.
            # Guarded: both principals must be truthy (set_run_scope fail-louds
            # on falsy by design). WR-03: error contract mirrors the revision
            # caller of this SAME seam (set_run_scope below) — degrade ONLY the
            # DB condition (offline harness with no schema → SQLAlchemyError);
            # a non-DB exception — notably the IN-02 cross-owner
            # PermissionError, i.e. the WS layer created the row under a
            # DIFFERENT principal than the engine derived (principal drift) —
            # is a real bug and FAILS LOUD. Swallowing it would hide the drift
            # AND leave workspace_id NULL, silently reinstating the
            # null-status reconnect bug this stamp exists to fix.
            if owner_id and ectx.workspace_id:
                try:
                    await scoped_store.set_run_scope(
                        pipeline_run_id, owner_id, ectx.workspace_id
                    )
                except Exception as _stamp_exc:  # noqa: BLE001 — DB-only degrade
                    from sqlalchemy.exc import SQLAlchemyError

                    if not isinstance(_stamp_exc, SQLAlchemyError):
                        raise
                    logger.warning(
                        "execute(): workflow_runs scope stamping failed for %s "
                        "(%s) — proceeding",
                        pipeline_run_id, _stamp_exc,
                    )
            # ── Per-run integration scopes + active MCP servers (09-06 / CAPRUN-01) ──
            # Record the run's active integration scopes + the MCP servers they activate
            # (alongside the runtime) so ``run_capabilities`` is the audit row for WHAT
            # external surface this run could reach (INTEG-02). ``integration_scopes`` is
            # host-injected (the §15 seam); default NONE ⇒ both persist as SQL NULL (INV-3
            # row parity — never a spurious non-null write for a run with no integration).
            _rec_scopes = list(getattr(ectx, "integration_scopes", None) or [])
            _rec_servers: list[str] = []
            if _rec_scopes:
                from agents.capabilities.integration_providers.providers import (
                    SCOPE_TO_SERVER,
                )

                _rec_servers = sorted(
                    {SCOPE_TO_SERVER[s] for s in _rec_scopes if s in SCOPE_TO_SERVER}
                )
            await scoped_store.record_capabilities(
                pipeline_run_id,
                runtime="langchain_deepagents",
                # D-08: persist the validated overrides at entry. ``or None`` so an
                # empty {} (every run today) persists as SQL NULL — INV-3 row parity
                # with legacy/no-override rows (never a spurious non-null {} write).
                model_overrides=(ectx.model_overrides or None),
                # 09-06: the active integration scopes + the MCP servers they activate
                # (``or None`` ⇒ SQL NULL for a no-integration run — INV-3 parity).
                integrations=(_rec_scopes or None),
                mcp_servers=(_rec_servers or None),
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
        # ── RESUME-04 durable artifact hydration ─────────────────────────────────────
        # On a fresh-process resume (``_is_resume``) the in-memory typed graph is
        # empty, but the steps that completed before the restart persisted their typed
        # outputs to the durable ``artifact_refs``. The dispatch loop SKIPS those steps,
        # so their outputs must be re-seeded into the graph for the downstream steps that
        # CONSUME them (e.g. the wave_scheduler step reads the plan step's task list via
        # ``latest_typed_content`` — an empty graph would parse zero tasks). Adopt the
        # durable refs verbatim (id/hash/version preserved). Best-effort: a read failure
        # (offline) leaves the graph empty → the skipped step's downstream re-runs from
        # scratch (still correct). Dormant for a normal run.
        # BUG-R05: keyed on ``_is_resume`` (NOT ``_resume_from > 0``) — an offset-0 gate
        # re-entry (a step-0 open review gate) is still a resume and MUST hydrate, else the
        # 49-02 gate-reentry consumer reconstructs the gate output from an empty graph → "".
        if _is_resume:
            await self._hydrate_artifacts_from_store(ectx)
        # ── RESUME-08 durable → disk re-materialization (DEFERRED to the boundary hook) ──
        # Re-materialization is now performed AFTER the compiled workflow + ordered_agents +
        # the per-run runner handle + the ordered resume cursor are all available (the
        # RESUME-16 cumulative boundary needs the parsed CURRENT task list + the strategy's
        # upstream hash), which is post-compile — not here (this point precedes
        # ``compile_for_run``). See the ``_is_resume`` boundary re-materialization hook right
        # after the skip-cursor computation below. Nothing between here and that hook reads
        # the re-materialized deliverable (only a PLANNER.md write), so deferring it keeps
        # the disk reconstructed BEFORE the dispatch loop re-enters (Edge-Case 6 preserved).
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
        # _run_agent — because the task_loop strategy calls _run_agent fresh ONCE PER
        # TASK. A local list resets every task, so completed_count would be stuck at
        # 1 and the frontend's protoCompletedTaskCount would go non-monotonic
        # (0,1,1,1,2,1) instead of cumulative/monotonic (0,1,1,2,2,3) — a visible
        # build-progress UI regression. Lives on the per-run context
        # (ectx.completed_tasks, [] by default_factory), appended in _run_agent,
        # emitted as completed_count=len(ectx.completed_tasks).

        # ── Routing seam: compile the CompiledWorkflow this run executes from ──
        # (MAN-04/MAN-05). Resolve the legacy `pipeline_type` label to a manifest id,
        # load + compile that manifest, and source EVERY routing concern from the
        # compiled plan below (agent sequence/ids, deliverable spec, clarify mode +
        # defaults, planner flag, declared context_providers). Compiled HERE — before
        # the revision setup — so the in-place-edit revision behavior keys off the
        # DECLARED ``previous_run`` provider, NOT a ``pipeline_type`` name branch
        # (INV-1). No legacy `pipeline_type` dispatch fallback (INV-12).
        # compiled_override (spec: launch_run's USER_WORKFLOW_MANIFEST case): a
        # DB-composed manifest already compiled with trust="db" at launch time.
        # When set, skip the file-based compile entirely — there is no file.
        compiled = (
            compiled_override
            if compiled_override is not None
            else compile_for_run(pipeline_type)
        )
        # ── Roster seam (ADR-0003, refined by ADR-0008) ───────────────────────────
        # The plan FILLS IN the roster; it never overrules a caller that has one.
        # ``not agents`` is the load-bearing discriminator: rebuilding whenever the
        # plan was non-empty discarded the composer's agent picks. Reached only by
        # custom workflows, whose template steps have no AGENT.md for the caller
        # to resolve.
        # ...and a caller whose roster is a STRICT SUBSET of the plan does not have
        # one either, in the sense that matters. PIPELINE_AGENTS is derived from each
        # AGENT.md's `pipeline_type`, so a workflow REUSING an agent from another
        # pipeline gets a partial roster: ppt_v2 reuses ppt's brief-analyst and
        # composer, and `get_pipeline_agents("ppt_v2")` returns only the two authored
        # for it. The DAG resolver then validates against that partial set and
        # rejects the run outright — "ppt-deck-qa-v2 consumes 'ppt-composer' but no
        # upstream agent produces it" — when ppt-composer is in fact step 2. The
        # declaration is right; the roster was missing what the plan already knew.
        #
        # A composed run cannot take this branch: its plan is DERIVED from the picks,
        # so its roster is equal to or larger than the plan, never a strict subset
        # (the Path-B fan-out case is roster 2 / plan 1). So the composer's picks are
        # still never discarded, which is what `not agents` was protecting.
        _plan_ids = {s.agent_id for s in compiled.steps}
        _roster_is_partial = bool(agents) and {a.id for a in agents} < _plan_ids
        if compiled.steps and (not agents or _roster_is_partial):
            agents = self._specs_from_plan(compiled.steps)
        # ── EMP-01 (22-04): apply user-composed per-step selections onto the plan ──
        # A saved/custom workflow may carry a compact per-step selections map
        # (validators / gates / non-default model / retry) the user composed. It is
        # applied GENERICALLY by agent_id onto the file-compiled steps — never a
        # workflow/agent-name branch (SC-001) — AFTER re-compiling the selections
        # through the SAME trust="user" path the WS layer already gated on, so the
        # overlay can only carry user-allowed levers. ``selections`` is None/empty for
        # every existing run (and all 5 goldens) → a pure no-op (byte/event-identical,
        # INV-3): the overlay function returns ``compiled`` unchanged.
        # Thread the run's ordered agent ids so a composed agent absent from the base
        # manifest still gets a trust-compiled step (Path B); ``_user_steps_by_agent``
        # is {} for every None/empty-selections run → the absent-agent synthesis site
        # (below) stays byte-identical (INV-3).
        compiled, _user_steps_by_agent = self._apply_selections(
            compiled, selections, [s.id for s in agents]
        )
        # Bind the declared deliverable spec onto the context at run entry (INV-1) so
        # the per-agent mid-stream transforms in _run_agent (the single-file disk
        # readback + the ppt carousel sanitize) key off compiled.deliverable.strategy.
        ectx.deliverable = compiled.deliverable
        # Bind the DECLARED seed_files dict onto the context (07-11 / CR-07) so the
        # previous_run provider + the task_loop reference-file writer read the declared
        # list (honoring the ``seed_files.from_run`` surface) with the legacy
        # ``_SEED_FILES`` triple as fallback. All authored manifests are ``{}`` so the
        # fallback fires → byte-identical (Pitfall 2). The compiler stays thin (INV-5):
        # it only carries the declaration; the read/control-flow lives in the
        # provider/strategy, NOT in compiler.py.
        ectx.seed_files = dict(getattr(compiled, "seed_files", None) or {})
        # ── Per-run fan-out BudgetManager (Phase 11 / FANOUT-09 / OBS-01) ────────
        # Construct the ENFORCING per-run budget from the compiled workflow's Limits
        # (trust-conditional, materialized by the compiler) over the module-constant
        # defaults, plus the OPTIONAL per-workspace ceiling from the WORKSPACE_BUDGET
        # settings seam (None = unset = uncapped; the workspace aggregate gate stays
        # dormant). A PER-RUN object (INV-2 — never on the engine singleton); the single
        # kernel run_fanout spawn path calls ``ectx.budget.reserve(...)`` BEFORE any
        # spawn (Pitfall 4). A non-fanout run never reaches reserve, so this is inert for
        # existing workflows (byte/event-identical — the budget is dormant until a
        # fan-out step runs).
        from app.core.config import settings as _budget_settings
        ectx.budget = BudgetManager.from_limits(
            getattr(compiled, "limits", None),
            workspace_ceiling=getattr(
                _budget_settings, "WORKSPACE_BUDGET_MAX_SUBAGENTS", None
            ),
        )
        # The "revise a prior run in place" setup (extract the existing artifact,
        # slim the message, compute the pre-edit baseline) is gated on the DECLARED
        # per-deliverable revision-intent flag ``compiled.deliverable.revises_existing``
        # (07-10 / WR-04) — the manifest feature that marks a revise-prior-run
        # workflow — NOT on the presence of the ``previous_run`` provider (a
        # provider-name proxy is a workflow-identity branch in disguise: four other
        # workflows declare ``previous_run`` yet are NOT in-place revisions) and NOT
        # on the workflow's name (INV-1). Stash it on the context too: the per-agent
        # single_file mid-stream readback (in _run_agent) fires for a FORWARD
        # single_file build (the agent writes the file fresh) but NOT for a revision
        # (whose mid-stream deliverable is the edited streamed output — the legacy
        # L10 gate excluded in-place revision runs, parity).
        _is_revision_workflow = bool(
            getattr(compiled.deliverable, "revises_existing", False)
        )
        ectx.is_revision_workflow = _is_revision_workflow

        # ── Existing-artifact seed: OWNED by the previous_run provider (CR-06) ───
        # The "seed the prior artifact as an in-place-editable file" behavior
        # (extract the EXISTING artifact from the message → write it under
        # deliverable.name → capture the revision instruction → slim the message to
        # a file pointer → stash revision_original_html/revision_instruction) was
        # relocated OUT of this kernel block into the ``previous_run`` provider
        # (07-10), invoked at run entry by ``_seed_workflow_context`` below — right
        # after the KernelServices handle is attached (the provider reaches the
        # message + sandbox through the handle). The provider also slims the
        # handle's user_message, so the strategy loop hands the agent the same
        # slimmed prompt the legacy inline block produced (byte-identical). The
        # pre-edit baseline (computed on the seeded original) runs just after that
        # seed, below.

        # Load per-user disk skills for all agents (user → global → built-in).
        # Honours per-user SKILL.md overrides — replicates the behaviour of the
        # former WorkflowOrchestrator._load_skills (WORKFLOWS.md §B6).
        ectx.disk_skills = self._load_disk_skills(agents, user_id)

        # ── Constitution pre-warm at run entry (AGENTRT-06 / F4 / R12) ──────────────────
        # The factory's _inject_constitution is SYNC but is called from THIS async engine
        # under a RUNNING event loop. Awaiting get_constitution there is unsafe (the old
        # running-loop branch silently read only the in-process _mem dict, dropping a
        # DB-stored Constitution in prod — the R12 no-op). Per RESEARCH A3 / D-08 (the
        # lower-risk option) we await it HERE, ONCE, before the sync create_runner calls,
        # and stash the value on the context; each per-agent AgentContext carries it
        # (prewarmed_constitution) so the factory reads it sync-safely. The pre-warm key is
        # ``disk_principal`` — the SAME value threaded as AgentContext.user_id in
        # _run_agent (the factory's effective Constitution key). Best-effort: the offline
        # characterization harness has no DB and sets no Constitution, so this degrades to
        # None (graceful no-op) and the 5 snapshots stay byte-identical (RESEARCH A4).
        try:
            from agents.workflow_memory.memory import get_workflow_memory

            _const_key = ectx.disk_principal or owner_id
            if _const_key:
                ectx.prewarmed_constitution = await get_workflow_memory().get_constitution(
                    _const_key
                )
        except Exception as _const_exc:  # noqa: BLE001 — never break a run on the pre-warm
            logger.warning(
                "execute(): Constitution pre-warm failed (%s) — proceeding without a "
                "pre-warmed Constitution (graceful no-op)",
                _const_exc,
            )

        # ── MCP/integration tool pre-warm at run entry (09-05 / MCP-01) ──────────────
        # The SAME async→sync resolution as the Constitution pre-warm above: the factory
        # tool-resolution (_resolve_runner_tools) is SYNC and runs under THIS running
        # event loop, but McpClientAdapter.get_tools() is ASYNC. We connect + await the
        # tools ONCE here, before any sync create_runner, and stash them on the per-run
        # context (ectx.prewarmed_mcp_tools); each per-agent AgentContext carries the list
        # so the factory UNIONS them WITHOUT awaiting (no double-loop, Pitfall 3). The
        # tools AUGMENT the deepagents runtime, never replace it (INV-13). Best-effort:
        # the offline characterization harness activates no MCP scope → the list stays
        # empty (graceful no-op) and the 5 snapshots stay byte-identical. The per-run MCP
        # scope/credential wiring (which servers a run activates) is supplied by the
        # run-entry host (the §15 binding seam, like the RepoSpec injection in 09-04);
        # absent any active scope this pre-warm is a no-op.
        if not hasattr(ectx, "prewarmed_mcp_tools"):
            ectx.prewarmed_mcp_tools = []

        # ── Integration-provider bridge → the SAME MCP prewarm (09-06 / INTEG-01) ─────
        # The github/gitlab/jira/slack integration providers are THIN bridges onto the
        # 09-05 mcp_server catalog (ONE mechanism, no parallel SDK path — D-08): a granted
        # ``integrations`` scope (``gitlab_read`` etc.) is translated into the EXACT two
        # inputs the MCP prewarm below consumes (server-config map + exposed-tool allow-list)
        # by ``resolve_integration_scopes``. We MERGE them with any host-supplied MCP configs
        # so an integration's tools surface through the identical ``McpClientAdapter`` path.
        # Scopes default NONE (INTEG-02): no granted scope ⇒ empty maps ⇒ zero integration
        # tools bound (graceful no-op; the offline characterization activates none → snapshots
        # byte-identical). ``integration_scopes`` is host-injected per-run (the §15 seam, like
        # ``mcp_server_configs``); the live transport/credential per server rides on
        # ``integration_host_configs`` (also host-injected). Recorded per-run below (CAPRUN-01).
        _integration_scopes = list(getattr(ectx, "integration_scopes", None) or [])
        if _integration_scopes:
            try:
                from agents.capabilities.integration_providers.providers import (
                    resolve_integration_scopes,
                )

                _integ_configs, _integ_exposed = resolve_integration_scopes(
                    _integration_scopes,
                    getattr(ectx, "integration_host_configs", None),
                )
                # NOTE: the per-run active-server list persisted to
                # run_capabilities is computed ONCE at the scoped-store entry
                # (_rec_servers via SCOPE_TO_SERVER) — do not duplicate it here.
                if _integ_configs:
                    _merged_configs = dict(getattr(ectx, "mcp_server_configs", None) or {})
                    _merged_configs.update(_integ_configs)
                    ectx.mcp_server_configs = _merged_configs
                    _merged_exposed = dict(getattr(ectx, "mcp_exposed_tools", None) or {})
                    _merged_exposed.update(_integ_exposed)
                    ectx.mcp_exposed_tools = _merged_exposed
            except Exception as _integ_exc:  # noqa: BLE001 — never break a run on the bridge
                logger.warning(
                    "execute(): integration-scope bridge failed (%s) — proceeding "
                    "without integration tools (graceful no-op)",
                    _integ_exc,
                )

        try:
            _mcp_configs = getattr(ectx, "mcp_server_configs", None)
            if _mcp_configs:
                from app.agents.mcp.client import McpClientAdapter

                _mcp_allowed = getattr(ectx, "mcp_exposed_tools", None)
                _adapter = McpClientAdapter(_mcp_configs)
                ectx.prewarmed_mcp_tools = await _adapter.get_tools(allowed=_mcp_allowed)
        except Exception as _mcp_exc:  # noqa: BLE001 — never break a run on the pre-warm
            logger.warning(
                "execute(): MCP tool pre-warm failed (%s) — proceeding without "
                "pre-warmed MCP tools (graceful no-op)",
                _mcp_exc,
            )

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

        # ── Ordering seam (ADR-0004) ──────────────────────────────────────────────
        # Declared order (`depends_on`) wins over the resolver's inferred DAG, but
        # ONLY where the two actually disagree. Custom workflows are the case this
        # exists for: their steps all load the same contract-free template, so the
        # resolver has nothing to sort by and its DAG cannot satisfy the declared
        # edges. Ordering only — satisfiability already ran and halted above.
        #
        # The former `any(depends_on)` test was a WHOLE-PLAN switch: one declared or
        # compiler-derived `depends_on` anywhere (every `subagents:` group emits
        # them) discarded the resolver's contract-derived ordering for every other
        # step too, silently reverting app_builder / dotnet_to_azure /
        # mulesoft_to_springboot to manifest order. Now the resolver's DAG is kept
        # whenever it ALREADY satisfies every declared edge, so adding a
        # `depends_on:` that the contracts imply anyway is a no-op.
        _dag_order = validation.dag or list(agents)
        _declared_edges = [
            (s.agent_id, dep)
            for s in compiled.steps
            for dep in (getattr(s, "depends_on", None) or [])
        ]
        if not _declared_edges:
            ordered_agents = _dag_order
        else:
            _pos = {
                getattr(a, "id", None): i for i, a in enumerate(_dag_order)
            }
            # A declared edge is violated when the resolver placed the DEPENDENCY
            # after the step that depends on it. Edges naming an agent the resolver
            # never placed (a custom-agent template with no contracts) are skipped
            # here and covered by the fallback below.
            _violated = any(
                dep in _pos and child in _pos and _pos[dep] > _pos[child]
                for child, dep in _declared_edges
            )
            # An edge whose endpoints the resolver never ordered at all means the
            # DAG is not a usable ordering for this plan — take the compiler's.
            _unplaced = any(
                dep not in _pos or child not in _pos
                for child, dep in _declared_edges
            )
            if _violated or _unplaced:
                ordered_agents = list(agents)  # already topo-sorted by the compiler
            else:
                ordered_agents = _dag_order

        # (The CompiledWorkflow was compiled at run entry above — before the revision
        # setup — so the in-place-edit revision behavior keys off the declared
        # ``previous_run`` provider rather than a ``pipeline_type`` name branch, INV-1.)

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

        # (1) Agent sequence/ids — the manifest-vs-registry membership assertion is
        # DELETED (ADR-0003; roster rule in ADR-0008): a custom workflow can never
        # satisfy it, since its template steps have no AGENT.md and the registry side
        # is always [].
        #
        # REPLACEMENT (ADR-0003 "Confirmation"): a NON-BLOCKING drift warning. The
        # assertion raised; this only logs, so a custom workflow — whose registry side
        # is legitimately [] — is never affected, while a genuine manifest/registry
        # divergence on a file-backed pipeline is still visible in the logs before the
        # run gets far enough to fail inside load_agent_spec.
        #
        # Still outstanding (deliberately NOT fixed here — see ADR-0003): three
        # consumers keep reporting registry membership rather than what actually ran —
        # api/agents.py, run_commands.py `agent_count`, run_engine.py model allow-list.
        try:
            from agents.registry import PIPELINE_AGENTS, get_pipeline_agents

            _compiled_agent_ids = [s.agent_id for s in compiled.steps]
            # Skip composed workflows entirely: a `custom-agent:<instance>` step has no
            # AGENT.md, so the registry can never know it and a "drift" warning would
            # fire on every composed run (SC-001 — no name branch, a property check).
            _is_composed = any(
                isinstance(a, str) and a.startswith(CUSTOM_AGENT_PREFIX)
                for a in _compiled_agent_ids
            )
            if _compiled_agent_ids and not _is_composed:
                _registry_specs = get_pipeline_agents(compiled.id)
                _membership_ids = (
                    [a.id for a in _registry_specs]
                    if _registry_specs
                    else list(PIPELINE_AGENTS.get(compiled.id, []))
                )
                # An empty registry side is "no membership declared", not drift.
                if _membership_ids and _compiled_agent_ids != _membership_ids:
                    logger.warning(
                        "manifest/registry drift for %r (manifest id %r): the run will "
                        "execute the PLAN order %s, while api/agents.py, agent_count and "
                        "the model allow-list report the REGISTRY order %s. Reconcile "
                        "agents/workflows/%s/workflow.yaml with registry.PIPELINE_AGENTS.",
                        pipeline_type,
                        compiled.id,
                        _compiled_agent_ids,
                        _membership_ids,
                        compiled.id,
                    )
        except Exception as _drift_exc:  # noqa: BLE001 — a warning must never break a run
            logger.debug("drift check skipped (%s)", _drift_exc)

        # ── Step 2: Run the Deep_Planner_Agent (gate) ─────────────────────
        # RESUME-04 / BUG-R05: a resumed run (``_is_resume``) does NOT re-run the planner
        # or the clarifier — it already cleared its planning gate before the restart.
        # The state-machine transition to "planning" is suppressed on resume so the run
        # goes straight to "generating" below (a resumed run is mid-build).
        # Keyed on ``_is_resume`` (NOT ``_resume_from > 0``): an offset-0 resume whose
        # resume point IS a step-0 open gate is still a resume — reading offset 0 as a
        # fresh start would re-run the planner/auto-clarifier and re-park the run at a new
        # questionnaire BEFORE reaching the 49-02 gate-reentry block below (BUG-R05).
        _resuming = _is_resume
        if not _resuming:
            self._state_machine.transition(pipeline_run_id, "planning")
        _log_event("workflow_run_created", pipeline_run_id, pipeline_type=pipeline_type)

        # ── Planner-skip routing concern — sourced from the compiled plan ──
        # (MAN-04, concern 4). The planner-skip flag now comes from
        # `compiled.planner` ("run" | "skip"), NOT from the legacy module-level
        # planner-skip flag the prototype path used to read. Every dispatchable
        # manifest declares `planner: run` today, so `skip_planner` is False for every
        # run and behavior is byte-identical: the planner/clarifier runs for every
        # pipeline exactly as before. A resumed run forces the planner-skip path (no
        # planner overlay, no clarify gate — the run is mid-build).
        # RESUME-17 clarify twin (A5): a restart-parked clarify run re-arms by REPLAYING
        # the durable open round (no planner/LLM re-gen — the planner events are already
        # durable from before the restart). So the replay ALSO takes the planner-skip
        # path, but forces the clarify gate below so Step 3 re-emits the durable questions
        # and re-enters the wait. ``_clarify_replay`` is None for every fresh/resumed run
        # ⇒ dormant (INV-3).
        _replaying_clarify = _clarify_replay is not None
        skip_planner = compiled.planner == "skip" or _resuming or _replaying_clarify

        if skip_planner:
            logger.info("Prototype pipeline (Approach 2+3): skipping planner + clarifier")
            # D2: a RESUME rehydrates its planning context from the durable rows instead
            # of rebuilding the stub. The planner is still NOT re-invoked (TRAP 4 /
            # BUG-R05 / quick 260719-hd5, guarded by
            # test_offset0_gate_resume_does_not_replan_or_reclarify) — RESUME-04 hydration
            # (:1406) already put the rows in the graph, so this is a pure read.
            # Gated on ``_resuming`` ALONE. Clarify replay is deliberately excluded: on a
            # replay the durable rows exist but the questions are about to be RE-ASKED, so
            # injecting the previously-merged answers into that prompt is a behaviour
            # change no source artifact analysed. The two flags cannot co-occur (the replay
            # drive passes _is_resume=False; the resume drive passes _clarify_replay=None),
            # so this is a clean narrowing that keeps BOTH the planner=="skip" path and the
            # clarify-replay path byte-identical (INV-3).
            planning_context = (
                self._rehydrate_planning_context(ectx, user_message)
                if _resuming
                else self._default_planning_context(user_message)
            )
            planning_context["pipeline_type"] = pipeline_type
            planning_context["planner_ran"] = False
            if _replaying_clarify:
                # Force the clarify gate so Step 3 replays the durable open round. This
                # is the ONLY thing the replay changes about the skip-planner path.
                gate_verdict = "CLARIFY_REQUIRED"
                planning_context["execution_gate"] = "CLARIFY_REQUIRED"
            else:
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
                ectx=ectx, usage_sink=aux_token_usage.append,
            )

            # ── Clarify-mode routing concern — sourced from the compiled plan ─────
            # (MAN-04, concern 3; migrated L6, INV-1). The "force clarification on
            # every run" behavior is now declared by the manifest `clarify.mode`
            # ("auto" ⇒ always clarify, "skip" ⇒ always proceed), NOT a hardcoded
            # module-level always-clarify flag.
            clarify_mode = compiled.clarify.mode  # "auto" | "skip" | None
            clarify_auto = clarify_mode == "auto"
            clarify_skip = clarify_mode == "skip"

            if clarify_skip and gate_verdict == "CLARIFY_REQUIRED":
                # FIX-016: mode=skip means the wizard already collected all context.
                # Override the planner's CLARIFY_REQUIRED verdict to PROCEED so the
                # ClarifyEngine is never invoked. Gated on compiled.clarify.mode
                # (generic routing value) — never on pipeline_type (INV-1).
                logger.info(
                    "clarify.mode=skip — overriding gate verdict CLARIFY_REQUIRED → PROCEED"
                )
                gate_verdict = "PROCEED"
                planning_context["execution_gate"] = "PROCEED"

            elif clarify_auto and gate_verdict != "CLARIFY_REQUIRED":
                logger.info("clarify.mode=auto — overriding gate verdict PROCEED → CLARIFY_REQUIRED")
                gate_verdict = "CLARIFY_REQUIRED"
                planning_context["execution_gate"] = "CLARIFY_REQUIRED"
                if not planning_context.get("missing_information"):
                    has_topic = planning_context.get("has_topic", True)
                    # The per-pipeline default clarifying-question list comes from
                    # `compiled.clarify.defaults` (which reproduces the engine's former
                    # `_pipeline_defaults` dict verbatim, with revisions / edge ids
                    # falling to the `custom` list), NOT from a hardcoded dict keyed by
                    # pipeline_type. `od_prototype` resolves to the `prototype` manifest
                    # whose defaults equal the former `_pipeline_defaults["od_prototype"]`,
                    # so behavior is byte-identical.
                    defaults = list(compiled.clarify.defaults)
                    if not has_topic:
                        defaults = ["topic"] + defaults
                    planning_context["missing_information"] = defaults
                    logger.info(
                        "clarify.mode=auto: seeding defaults has_topic=%s pipeline=%s: %s",
                        has_topic, pipeline_type, defaults
                    )

            # KAN-87: no-template prototype — ensure UI style question is asked.
            # When the user chose blank-canvas (no_template=True in od_context),
            # inject "ui_style" as the FIRST missing item so ClarifyEngine always
            # asks what kind of visual UI they want before the spec writer runs.
            # Also set no_template_mode flag on planning_context so ClarifyEngine
            # knows to generate extra UI-focused questions via the LLM path.
            # Keyed on od_context.no_template (generic data flag, NOT pipeline_type
            # name — INV-1 compliant). Only fires when clarification will run.
            _is_no_template = bool((ectx.od_context or {}).get("no_template"))
            if _is_no_template and gate_verdict == "CLARIFY_REQUIRED":
                _missing = planning_context.get("missing_information") or []
                if "ui_style" not in _missing:
                    planning_context["missing_information"] = ["ui_style"] + [
                        m for m in _missing if m != "ui_style"
                    ]
                # Signal ClarifyEngine to ask extra UI design questions
                planning_context["no_template_mode"] = True
                logger.info(
                    "no-template prototype: prepended 'ui_style', set no_template_mode=True"
                )

            # ISS-056/H3(a): the wizard already resolved a design system before the
            # engine was called (od_context.ds_id, set at the REST launch boundary).
            # Asking "what visual style?" is redundant. Prune style/ui_style from
            # missing_information when a ds_id is present and no_template is NOT set
            # (blank-canvas is the one case where style IS still genuinely unknown —
            # KAN-87 above has already forced ui_style back in for that path).
            # Keyed on od_context content (generic, INV-1-compliant), not pipeline_type.
            _od = ectx.od_context or {}
            if _od.get("ds_id") and not _od.get("no_template") and gate_verdict == "CLARIFY_REQUIRED":
                _missing = planning_context.get("missing_information") or []
                _filtered = [m for m in _missing if m not in ("style", "ui_style")]
                if len(_filtered) != len(_missing):
                    planning_context["missing_information"] = _filtered
                    logger.info(
                        "ISS-056/H3: pruned style/ui_style from missing_information "
                        "(ds_id=%s already chosen)", _od.get("ds_id")
                    )

            # ISS-056/H3(b): thread the design system's friendly name into
            # planning_context so ClarifyEngine can acknowledge it in its LLM prompt.
            # Uses the template_name/ds_name fields added to od_context by od_context.py.
            # Keyed on od_context.ds_id (generic, INV-1-compliant), not pipeline_type.
            if _od.get("ds_id") and gate_verdict == "CLARIFY_REQUIRED":
                if _od.get("ds_name"):
                    planning_context["design_system_name"] = _od.get("ds_name")
                if _od.get("template_name"):
                    planning_context["template_name"] = _od.get("template_name")
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
            # ISS-033: count the clarify question-generation model-call tokens in the
            # run accounting (via the shared cached_invoke inside the engine).
            clarify._usage_sink = aux_token_usage.append

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
                    max_rounds=compiled.clarify.rounds,
                    # RESUME-17 clarify twin (A5): replay the durable open round's
                    # questions VERBATIM (no LLM re-gen). None for every fresh/live run
                    # ⇒ ClarifyEngine.run generates normally (INV-3 dormant).
                    replay_questions=(
                        _clarify_replay.get("questions") if _clarify_replay else None
                    ),
                    replay_round=(
                        _clarify_replay.get("round") if _clarify_replay else None
                    ),
                )
            )

            # Drain the queue until clarify_task completes
            while not clarify_task.done():
                try:
                    event = await asyncio.wait_for(event_queue.get(), timeout=1.0)
                    if event is not None:
                        yield event
                except asyncio.TimeoutError:
                    # BUG-2 Cond A (quick-260720-ec4): the Stop button sets the
                    # cooperative cancel_event; observe it on the drain loop's 1s
                    # heartbeat so a clarify-parked run honors Stop. Cancel the
                    # clarify task, transition to cancelled, and yield the existing
                    # pipeline_cancelled terminal (no new event type). DORMANT when
                    # cancel_event is None (scripted/golden runs) — byte-identical to
                    # today's plain `continue` (INV-3). Keys ONLY on the generic
                    # cancel_event (no workflow/agent-name branch — SC-001/INV-1).
                    if cancel_event is not None and cancel_event.is_set():
                        clarify_task.cancel()
                        try:
                            await clarify_task
                        except (asyncio.CancelledError, Exception):
                            pass
                        self._state_machine.transition(pipeline_run_id, "cancelled")
                        yield {
                            "type": "pipeline_cancelled",
                            "data": {"pipeline_run_id": pipeline_run_id},
                        }
                        return
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
                # KAN-120 BUG-2: surface the resume offset so the FE can mark
                # already-completed agents as "done" immediately on resume, rather
                # than waiting for the durable SSE replay to restore their statuses.
                # 0 on every normal (non-resumed) run → byte/event-identical (INV-3).
                "resume_offset": _resume_from,
            },
        }

        results: list[dict] = []

        # ── KernelServices runner handle (D-03) — the SINGLE seam capabilities ──
        # reach the kernel/app primitives through (INV-13/hexagonal). Constructed
        # here, after the sandbox + compiled plan + per-run ExecutionContext, and
        # attached to ctx.runner so the routed strategies / deliverable resolvers /
        # context providers call _run_agent / sandbox / static_check / render_check /
        # serialize/count WITHOUT importing the kernel. The handle wraps the engine's
        # EXISTING _run_agent (which wraps create_deep_agent via langchain_deepagents —
        # INV-13, no hand-rolled agent loop) so the routed path is byte/event identical.
        # Carry the workflow's declared context-provider names on the context so the
        # generic injector composes the OD blocks from them in declared order (INV-1).
        ectx.compiled_context_providers = list(compiled.context_providers or [])
        # image-input Wave 1: carry the workflow's declared input_provider capability
        # names on the per-run context (same dynamic-attr thread) so the per-agent
        # _compose_input_blocks resolves them in declared order. Dormant — [] this wave.
        ectx.compiled_input_providers = list(compiled.input_providers or [])
        # capabilities (spec 012 / R-25, T33/T35): carry the workflow-level
        # ``CompiledWorkflow.capabilities`` dict (e.g. ``{"internet": bool}``) on the
        # per-run context (same dynamic-attr thread as the two providers above) so
        # ``_run_agent`` can pass it into every step's ``AgentContext.capabilities``.
        # {} when the manifest declares none → AgentContext.capabilities stays {} →
        # no internet tools bound (byte-identical for every existing manifest).
        ectx.compiled_capabilities = dict(compiled.capabilities or {})

        from agents.execution_engine.kernel_services import KernelServices

        ectx.runner = KernelServices(
            engine=self,
            ectx=ectx,
            sandbox=sandbox,
            ordered_agents=ordered_agents,
            user_message=user_message,
            pipeline_run_id=pipeline_run_id,
            pipeline_type=pipeline_type,
            planning_context=planning_context,
            attached_skills=attached_skills,
            attached_hooks=attached_hooks,
            model_id=model_id,
            results=results,
            cancel_event=cancel_event,
            # Phase 11 / FANOUT-03 (CR-01): bind the compiled workflow-level
            # named-worker allow-list onto the LIVE handle so run_fanout's
            # pre-spawn worker selection reads the real declaration.
            allowed_workers=list(getattr(compiled, "allowed_workers", None) or []),
            # The compiled steps, so run_worker can resolve a NAMED worker's own
            # declared step (prompt, skills, instance_id) rather than synthesizing
            # a bare one. Only heterogeneous fan-out reads this.
            compiled_steps=list(getattr(compiled, "steps", None) or []),
            # ISS-033-A: bind the run's aux usage accumulator onto the handle so the
            # validation fix-loop's sub-agent tokens fold into the run totals below
            # (the same sink the SmartPlanner + clarify one-shots already feed).
            aux_usage_sink=aux_token_usage.append,
        )

        # ── KAN-73: persist attached behavioral hooks as audit records ───────────
        # Each hook from the UI (Quality Gate, Config Protection, etc.) is a
        # behavioral prompt instruction injected into agent system prompts. We write
        # ONE hook_runs row per attached hook at run entry so they appear in the
        # Audit tab as "Active Behavioral Guidelines" — giving the user traceability
        # of which hooks were active for this run. Best-effort: a write failure
        # must never abort the run.
        for _ah in (attached_hooks or []):
            _ah_name = _ah.get("name") or _ah.get("id") or "Unknown Hook"
            _ah_event = _ah.get("event") or _ah.get("trigger") or "run_start"
            _ah_desc = _ah.get("description") or f"{_ah_name}: {_ah_event}"
            _ah_detail = {
                "hook_name": _ah_name,
                "event_type": _ah_event,
                "description": _ah_desc,
                "source": _ah.get("source") or "workflow_config",
                "timestamp": _now(),
                "outcome": "continue",
                "summary": f"Behavioral guideline active: {_ah_name}",
                "severity": "info",
                "hook_type": "behavioral",
            }
            try:
                await ectx.runner.record_hook_run(
                    "behavioral", "run_start", "continue", _ah_detail
                )
            except Exception:  # noqa: BLE001 — audit must never abort the run
                pass
            # Also emit live WS event so the Audit tab shows immediately
            try:
                _emit_fn = getattr(ectx.runner, "emit_hook_event", None)
                if callable(_emit_fn):
                    _emit_fn(_ah_detail)
            except Exception:  # noqa: BLE001
                pass

        # ── §15 host seam: bind the exec-enabled runtime workspace (10-03 / EXEC-01) ──
        # The runtime_env capability (09-01) is REGISTERED but, until here, never
        # BOUND onto the live run path — ``KernelServices.workspace`` defaulted to
        # None (10-01). This is the ONE place an exec-enabled Workspace is
        # provisioned (Pitfall 1 — first-class, not a footnote): when (and ONLY when)
        # the compiled plan grants exec, resolve the local ``runtime_env`` impl, call
        # ``create_workspace(exec=True, recorder=record_exec_run)`` and bind it onto
        # ``KernelServices.workspace`` so the security gate's profile check + the
        # exec validators (10-04) reach it via ``target.runner.workspace``. The
        # recorder is the 10-01 best-effort audit handle — EVERY exec_command outcome
        # is audited bypass-proof at the enforcement point (T-10-01-07).
        #
        # GATED on the exec grant (Pitfall 3 / T-10-03-05): a run whose plan grants
        # NO exec never provisions a workspace, so ``KernelServices.workspace`` stays
        # None and every existing non-exec run is byte/event-identical (the 5
        # characterization snapshots prove the dormancy). A non-exec run silently
        # gaining an exec-enabled workspace would be a parity break / latent
        # escalation — so the provisioning is strictly conditional.
        #
        # WR-03 — exec authorization is RUN-scoped (NOT per-step): one
        # security+approval-gated grant provisions the workspace for the WHOLE run.
        # The exec-enabled workspace is bound once onto the shared
        # ``KernelServices.workspace`` whenever ANY step grants exec, so every
        # step's exec validators reach the same run-global grant; per-step
        # re-authorization is intentionally NOT enforced here. This is D-03's
        # SPEC-locked first-exec memory: the first exec step prompts for approval,
        # subsequent exec steps in the same run do NOT re-prompt. The compiler's
        # engineer-trust ceiling (a user/db manifest can never provision the exec
        # workspace) + the run-level approval model bound the blast radius, so this
        # run-scoped grant is by-design, not a default-deny break.
        _plan_grants_exec = any(
            bool(getattr(getattr(s, "tools", None), "exec", False))
            for s in (compiled.steps or [])
        )
        if _plan_grants_exec:
            try:
                from agents.capabilities.registry import CapabilityRegistry as _RtReg

                _runtime_impl = _RtReg().resolve("runtime_env", "local")
                ectx.runner.workspace = _runtime_impl.create_workspace(
                    owner_id=owner_id,
                    workspace_id=ectx.workspace_id,
                    exec=True,
                    recorder=_make_exec_recorder(ectx.runner),
                )
            except Exception as _ws_exc:  # noqa: BLE001 — degrade only the offline harness
                # Mirror the _scope_exc discipline: a missing on-disk runs root in the
                # offline characterization harness (OSError) degrades; a real
                # provisioning bug (KeyError unknown cap, registry RuntimeError) is
                # NOT silently no-op'd for an exec run — re-raise so it surfaces.
                if not isinstance(_ws_exc, OSError):
                    raise
                logger.warning(
                    "execute(): exec workspace provisioning failed (%s) — proceeding "
                    "without a bound workspace (exec validators will degrade)",
                    _ws_exc,
                )

        # ── Workflow-level context-provider seeding (INV-1) ─────────────────────
        # Invoke each declared workflow ``context_provider`` once at run entry. The
        # ``previous_run`` provider performs the parent-run spec/design/tasks SEED
        # (its L16 assert_owns gate runs here; a cross-owner PermissionError
        # propagates) — replacing the inline L4 seed block on the routed path. The
        # ``opendesign`` provider returns its block map (discarded here; the generic
        # injector re-composes it per-agent), so calling it at entry is a harmless,
        # side-effect-free read. A PermissionError propagates (L16); other errors
        # degrade (a missing parent must never break a revision).
        await self._seed_workflow_context(ectx, compiled)

        # The pre-edit revision baseline + post-edit Both-validation fix-loop are no
        # longer kernel-resident (07-10 / CR-06): they live in the declared
        # ``revision_validation`` post-step capability, invoked by the per-step
        # dispatch loop below after the revision step's strategy completes. The
        # kernel hosts NO prototype-revision behavior by name.

        # ── Per-step capability dispatch (INV-1) — NO workflow-name/agent-id branch ──
        # The compiled plan's Step.strategy names the execution-strategy capability for
        # each agent (task_loop for the prototype build step; single_shot for every
        # other step). The engine routes per-step via
        # registry.resolve("strategy", step.strategy).run(step, ctx) — the former L7
        # build-vs-else dispatch (the deleted prototype-build name branch) is gone from
        # the kernel entirely (07-05). install() is lazy-bound by resolve(); the
        # compiled steps align 1:1 with ordered_agents (asserted at compile-time above),
        # so we zip them by index for the per-step strategy name.
        from agents.capabilities.registry import CapabilityRegistry as _CapReg

        _registry = _CapReg()
        _steps_by_agent = {s.agent_id: s for s in compiled.steps}
        # T17 (R-15, D-05): the full agent_id -> compiled Step lookup, threaded onto
        # ectx so ``_run_agent``'s roster builder can resolve a parent's
        # ``depends_on`` child agent_ids to their ``display_name``/``instance_id`` —
        # the SAME dict this loop already built, just readable from the per-agent
        # call (which only carries ``ectx.current_step``, the ONE step, not the
        # whole compiled plan).
        ectx.steps_by_agent = _steps_by_agent  # type: ignore[attr-defined]

        # ── RESUME-09 per-task/per-worker SKIP CURSOR (kernel-computed, D-06) ────
        # On a durable resume, compute the completed-identity set per step from the
        # run's OWN owner-scoped durable rows and stamp it on ``ectx`` BEFORE the
        # dispatch loop re-enters. The task_loop / wave_scheduler strategies read it
        # (``getattr(ctx, "resume_completed_task_ids", None)``) and SKIP the completed
        # task_nums / workers — the AGENT never decides the skip set (SC-001/INV-1);
        # remaining work still flows through the SAME run_agent/run_fanout paths
        # (INV-13). Best-effort: any read failure leaves a step out of the set (re-run,
        # never skip-on-uncertainty). Gated on ``_is_resume`` (NOT ``_resume_from > 0``:
        # the in-flight wave at offset==0 has its own completed workers to skip) so the
        # cursor stays None on every normal run ⇒ byte/event-identical dispatch (INV-3).
        if _is_resume:
            try:
                (
                    ectx.resume_completed_task_ids,
                    ectx.resume_completed_ordered,
                ) = await self._compute_resume_completed_task_ids(
                    ectx, ordered_agents, compiled
                )
            except Exception as _cur_exc:  # noqa: BLE001 — fail-safe: leave the cursor None
                logger.warning(
                    "resume: skip-cursor compute failed (%s) — re-running remaining "
                    "work in full (no per-task/worker skip)", _cur_exc
                )
                ectx.resume_completed_task_ids = None
                ectx.resume_completed_ordered = None
            # ── RESUME-08 + RESUME-16 boundary re-materialization ───────────────────
            # Restore the durable file-backed refs onto the fresh sandbox BEFORE the
            # dispatch loop re-enters (the hydrate at the top restored the in-memory graph
            # ONLY; disk stays empty). Done HERE (not at the earlier hydrate hook) because
            # the RESUME-16 cumulative boundary needs the compiled steps + ordered_agents +
            # the runner handle (upstream hash) + the ordered cursor — all set above. The
            # boundary makes re-materialization AS-OF the common-prefix boundary task for a
            # cumulative resume-after-edit (p>0 → boundary version; p==0 → restore nothing);
            # a non-cumulative / non-edited resume yields an EMPTY boundary → the default
            # global-max path (byte-identical to the pre-move behavior). Best-effort:
            # a boundary-compute failure degrades to global-max (fail-safe, never a wrong
            # restore). Dormant on a normal run (``_is_resume`` False → this whole block is
            # skipped) → byte/event-identical (INV-3).
            try:
                _boundaries = self._compute_cumulative_boundaries(
                    ectx, ordered_agents, compiled, ectx.resume_completed_ordered
                )
            except Exception as _bnd_exc:  # noqa: BLE001 — fail-safe: default global-max
                logger.warning(
                    "resume: cumulative boundary compute failed (%s) — re-materializing "
                    "the global-max deliverable (no boundary restore)", _bnd_exc
                )
                _boundaries = {}
            # RESUME-16 independent: the per wave-step current-key allow-set that gates
            # confidently-orphaned (completed-but-absent) fragments out of re-materialization
            # (hence out of merge + assembly, zero merge edits). Dormant for a step with no
            # completed workers; a compute failure degrades to an empty allow-set → the
            # orphan gate stays dormant → all fragments restored (fail-safe KEEP).
            try:
                _wave_allow = self._compute_wave_orphan_allowsets(
                    ectx, ordered_agents, compiled, ectx.resume_completed_task_ids
                )
            except Exception as _wav_exc:  # noqa: BLE001 — fail-safe: keep all fragments
                logger.warning(
                    "resume: wave orphan allow-set compute failed (%s) — re-materializing "
                    "all fragments (no orphan exclusion)", _wav_exc
                )
                _wave_allow = {}
            await self._rematerialize_artifacts_to_disk(
                ectx, sandbox,
                boundary_by_agent=_boundaries,
                wave_allow_by_step=_wave_allow,
            )
            # ── RESUME-11 steering re-drain ─────────────────────────────────────────
            # Re-derive the steering notes the pre-crash run had NOT yet consumed from
            # the durable chat_message rows (seq > max agent_input.seq) and re-queue them
            # onto ectx.steering_notes so the FIRST re-dispatch renders them (no-loss); a
            # drained note (seq < last_input_seq) is skipped (no-duplicate). Best-effort +
            # owner-scoped (self-contained degrade). Gated on _is_resume ⇒ dormant on a
            # normal run (steering_notes stays empty → INV-3 byte-parity).
            await self._redrain_steering_notes(ectx)

            # ── RESUME-17 review-gate re-entry sentinel (49-02) ──────────────────────
            # When the durable events show an OPEN review gate whose target agent is the
            # step the resume offset landed on, arm a CONSUME-ONCE sentinel so ``_run_agent``
            # re-enters AT the gate phase (skip the model call; reconstruct ``output`` +
            # ``ectx.last_streamed`` from the persisted max-version ref — WR-02) and falls
            # into the SHIPPED five-action gate consumer. The output is NOT stashed here —
            # it is seeded at the loop entry from the freshly-hydrated graph (hydrated above
            # at ``_resume_from > 0``). Generic keying: parse the agent id out of
            # ``gate_key = f"{run}:{agent_id}:{visit_count}"`` (INV-1). R-08: strip BOTH the
            # run_id prefix (first colon) and the visit_count suffix (last colon) rather than
            # a plain ``split(":", 1)[1]`` — a custom-agent id (``custom-agent:<instance_id>``)
            # itself contains a colon, so only the outer two must be peeled. No-op when no
            # review gate is open (``derive_open_gate`` → ``(None, None)``) ⇒ the sentinel
            # stays unset and every non-gate resume is byte/event-identical (INV-3).
            # Best-effort — a read failure degrades to a normal (model-running) resume of the
            # step (fail-safe).
            if 0 <= _resume_from < len(ordered_agents):
                try:
                    _rr_rows = await scoped_store.read_events(pipeline_run_id, 0)
                    _rr_kind, _rr_gate_key = derive_open_gate(_rr_rows)
                    if _rr_kind == "review" and _rr_gate_key:
                        _rr_target = _rr_gate_key.split(":", 1)[1].rsplit(":", 1)[0]
                        _rr_spec = ordered_agents[_resume_from]
                        if getattr(_rr_spec, "id", None) == _rr_target:
                            ectx.gate_reentry = {
                                "agent_id": _rr_target,
                                "artifact_kind": self._artifact_kind_for(_rr_spec),
                                "gate_key": _rr_gate_key,
                            }
                except Exception:  # noqa: BLE001 — fail-safe: no sentinel → normal resume
                    logger.debug(
                        "resume: gate-reentry sentinel derivation failed (ignored)",
                        exc_info=True,
                    )

        # ── F3 (13-06): failed-agent tracking — pure OBSERVATION ────────────────
        # Record the agent_id of every ``agent_error`` event flowing through the
        # dispatch loop below. No event is modified, reordered or suppressed; the
        # set is consulted ONLY at the Step-5 terminal block to decide between
        # ``pipeline_failed`` (total collapse: nothing completed) and the additive
        # ``status="degraded"``/``agents_failed`` fields on ``pipeline_complete``
        # (partial failure). Keyed on counters only — no workflow name, no
        # agent-id literal, no spec.id comparison (SC-001/INV-1).
        _failed_agent_ids: set[str] = set()

        cursor = 0
        try:
            while cursor < len(ordered_agents):
                spec = ordered_agents[cursor]
                # ── RESUME-04 mid-run offset (D-06/D-07) ─────────────────────────
                # A resumed run re-enters THIS SAME loop (no forked dispatch path —
                # INV-12) at the first incomplete step: every step BEFORE the resume
                # offset already completed before the restart, so it is skipped here.
                # Its typed artifacts are already in the durable graph (reused by
                # downstream steps via the 12-02 content-hash key); re-invoking it
                # would re-spend the model. ``_resume_from == 0`` (normal run) never
                # skips, so this is byte/event-identical for every non-resumed run.
                if cursor < _resume_from:
                    cursor += 1
                    continue
                # ── Sibling-group parallelism (subagents.mode: parallel) ─────────
                # A parallel group's children are dispatched by their parent via
                # run_fanout; running them here too would run them twice. Removed from
                # SERIAL dispatch only — they stay in compiled.steps. `dispatched_by` is
                # compiler-derived and empty for every manifest not using the mode.
                _step_for_dispatch = _steps_by_agent.get(spec.id)
                if getattr(_step_for_dispatch, "dispatched_by", ""):
                    cursor += 1
                    continue
                # ── Cooperative state-machine check at the STEP BOUNDARY ─────────
                # A terminal event inside _run_agent only ends ITS generator; this loop
                # would keep dispatching steps and then report "completed" at Step 5.
                # Checked before cancel_event so a state-machine-only cancellation
                # (no event set) is caught too.
                if self._state_machine.get_state(pipeline_run_id) in ("cancelled", "failed", "diverted"):
                    return
                if cancel_event and cancel_event.is_set():
                    # ── ISS-007 (16-02): pre-agent cooperative cancel ─────────
                    # The Stop button sets the cooperative cancel_event; the
                    # per-chunk check inside a running agent routes through the
                    # outer ``except asyncio.CancelledError`` clean-terminal
                    # (:1670-1678). But a cancel observed at the STEP BOUNDARY
                    # (between agents, or before the first agent) hits THIS
                    # break — which previously fell through to the Step-5
                    # ``pipeline_complete`` terminal (:1741), so the live wire
                    # got the wrong terminal and the FE card never cleared.
                    # Emit ``pipeline_cancelled`` here (mirroring the outer
                    # cooperative terminal at :1670-1678 and the WR-03
                    # declared-gate reject precedent at :1561-1577) and RETURN
                    # before deliverable resolution — keyed on the generic
                    # cancel signal only (no workflow/model name, SC-001).
                    logger.info("Workflow cancelled before agent %s", spec.id)
                    _cur = self._state_machine.get_state(pipeline_run_id)
                    if _cur not in ("cancelled", "failed", "diverted"):
                        self._state_machine.transition(pipeline_run_id, "cancelled")
                    await self._persist_budget_snapshot_if_active(ectx)
                    yield {
                        "type": "pipeline_cancelled",
                        "data": {"pipeline_run_id": pipeline_run_id},
                    }
                    return

                # Resolve the per-step strategy capability by manifest name (D-02).
                # Fall back to single_shot when a step is absent from the compiled
                # plan (defensive — a populated plan is asserted above for every run).
                step = _steps_by_agent.get(spec.id)
                if step is None:
                    # Path B (51-04): a composed agent ABSENT from the base manifest
                    # (the common ``custom`` case) receives its trust-compiled fan-out
                    # step from the user-step map BEFORE the bare single_shot fallback.
                    # ``_user_steps_by_agent`` is {} for every None/empty-selections run,
                    # so this stays byte-identical (INV-3) to the old bare-single_shot
                    # synthesis for every non-composed run.
                    step = _user_steps_by_agent.get(spec.id)
                strategy_name = getattr(step, "strategy", "single_shot") if step else "single_shot"
                if step is None:
                    # Synthesize a minimal step carrying the agent id so the handle
                    # can resolve the AgentSpec (single_shot needs only agent_id).
                    from agents.workflows.plan import Step as _Step

                    step = _Step(agent_id=spec.id, strategy=strategy_name)
                # ── [D-03] Pre-step gates (security/approval/human) ──────────────
                # A step's declared ``gates: [...]`` evaluate in order at the step
                # BOUNDARY. The pre-step gates (security/approval/human) run BEFORE
                # the strategy; a ``block``/``wait_human`` outcome halts the step
                # ADDITIVELY (it emits the NEW ``gate_*`` event, never a renamed
                # existing one). The existing inline ``_should_gate`` →
                # ``_run_review_gate`` human path in ``_run_agent`` is UNCHANGED
                # (parity); a declared ``gates:[human]`` step is the additive
                # registry-driven entry point that delegates to the SAME review gate.
                _halted = False
                _blocked = False
                async for _ge, _outcome, _gdetail in self._evaluate_gates(
                    step, ectx, _registry, phase="pre",
                    # WR-02 (13 review fix): when the legacy inline review gate
                    # will fire for THIS agent (_should_gate — AGENT.md
                    # ``gate: Human_Gate`` or an explicit gate_agent_ids opt-in),
                    # the declared ``human`` gate is the SAME mechanism reviewing
                    # the SAME agent (same gate_key) — evaluating both
                    # double-prompts the user (pre-step with an empty payload,
                    # then post-step with the real output). Dedupe: the inline
                    # gate wins (the legacy, output-bearing UX); the declared
                    # ``human`` gate is skipped for this step only.
                    inline_gated=self._should_gate(spec, ectx),
                ):
                    # WR-04: skip the terminal (None, outcome) sentinel when
                    # forwarding (keeps the emitted stream identical) but still
                    # honor its outcome so a no-event block halts the step.
                    if _ge is not None:
                        yield _ge
                    if _outcome == "cancel":
                        # ── WR-03 (13 review fix): declared-gate rejection ────
                        # The user clicked Reject at a declared human/approval
                        # pause — run-cancellation parity with the inline
                        # _run_review_gate path (which the _gate_rejected
                        # handler in _run_agent cancels). Without this the run
                        # kept executing downstream agents and terminated as a
                        # completion while the state machine sat stranded in
                        # waiting_for_user.
                        _cur = self._state_machine.get_state(pipeline_run_id)
                        if _cur not in ("cancelled", "failed", "diverted"):
                            self._state_machine.transition(
                                pipeline_run_id, "cancelled"
                            )
                        await self._persist_budget_snapshot_if_active(ectx)
                        yield {
                            "type": "pipeline_cancelled",
                            "data": {
                                "pipeline_run_id": pipeline_run_id,
                                "reason": (
                                    f"User rejected at the review gate "
                                    f"before {spec.name}"
                                ),
                            },
                        }
                        return
                    if _outcome == "block":
                        _blocked = True
                        _halted = True
                    elif _outcome == "wait_human":
                        _halted = True
                    # NOTE: no ``elif _outcome == "route":`` arm here — the
                    # ``conditional`` gate (the only "route" emitter) is a
                    # POST-step gate (see ``_POST_STEP_GATES``); its route-jump
                    # handling lives in the post-step gate loop below.
                    # ── WR-04 (13 review fix): apply a declared-gate edit ─────
                    # The human gate threads an approve-with-edits payload on
                    # the terminal sentinel's detail. A declared pre-step gate
                    # reviews the PREVIOUS step's output (ectx.last_streamed),
                    # so the edit re-writes THAT step's artifact + results
                    # entry — exactly what the inline path does post-step
                    # (engine._run_agent's _gate_edited handler). No upstream
                    # output yet (first step) → nothing to apply (logged).
                    _edited = (
                        _gdetail.get("edited_content")
                        if isinstance(_gdetail, dict)
                        else None
                    )
                    if _edited:
                        await self._apply_declared_gate_edit(
                            _edited, results, ordered_agents, ectx
                        )
                if _blocked:
                    # ── §8b: a pre-step ``block`` terminates the RUN, not just
                    # the step. Previously every halt fell through to
                    # ``cursor += 1; continue``, so a security/approval gate
                    # refusing a step emitted ``gate_blocked`` and then let the
                    # run carry on through every downstream step and finish as
                    # ``pipeline_complete`` — a refused run reported success with
                    # a silently missing step. "Block" is a refusal, so it takes
                    # the same single-terminal shape the fan-out child-failure
                    # abort uses (KRN-004): one ``pipeline_failed``, no further
                    # steps, no ``pipeline_complete``.
                    #
                    # ``wait_human`` deliberately keeps the old skip-and-continue
                    # path below — it is a pause the human resolves (a rejection
                    # there arrives as the ``cancel`` outcome handled above), not
                    # a refusal.
                    _cur = self._state_machine.get_state(pipeline_run_id)
                    if _cur not in ("cancelled", "failed", "diverted"):
                        self._state_machine.transition(pipeline_run_id, "failed")
                    await self._persist_budget_snapshot_if_active(ectx, force=True)
                    yield {
                        "type": "pipeline_failed",
                        "data": {
                            "pipeline_type": pipeline_type,
                            "pipeline_run_id": pipeline_run_id,
                            "total_duration": round(time.time() - total_start, 2),
                            "agents_completed": cursor,
                            "agents_total": len(ordered_agents),
                            "agents_failed": [spec.id],
                            "error": f"A gate blocked {spec.name} before it ran.",
                            "timestamp": _now(),
                        },
                    }
                    return
                if _halted:
                    # The step is halted at its boundary — skip the strategy + the
                    # post-step gates/post_step for this agent (additive halt).
                    cursor += 1
                    continue

                # ── [08-07 / 08-08 / D-09] before_step hook firing (additive) ────
                # Declaration-driven (CR-01/WR-03): only the hooks this step DECLARES
                # on ``step.hooks`` fire — and only those bound to ``before_step`` (or
                # the ``*`` wildcard) under the step's effective perms. A legacy step
                # declares no hooks → NOTHING fires here (no hook_runs row, no console
                # span on the characterization parity paths). A declared non-blocking
                # hook (otel_tracing) records a span/hook_runs row + emits NO WS event;
                # a declared blocking hook would halt the step additively.
                _hook_outcome = await self._fire_hooks(
                    "before_step", step, ectx, _registry,
                    extra={"agent_name": spec.name, "step_index": cursor},
                )
                if _hook_outcome == "block":
                    # Additive halt — no new WS event, the step simply does not run.
                    cursor += 1
                    continue

                strategy = _registry.resolve("strategy", strategy_name)
                # RESUME-02 (D-10): the SINGLE per-step retry/reuse wrapper. Dormant
                # (byte/event-identical) unless the step declares retry.max_attempts > 0.
                _terminated = False
                async for event in self._dispatch_step_with_retry(step, ectx, strategy):
                    # F3 (13-06): observe agent_error events for the terminal
                    # semantics decision (no mutation — the event flows unchanged).
                    if event.get("type") == "agent_error":
                        _failed_id = event.get("data", {}).get("agent_id")
                        if _failed_id:
                            _failed_agent_ids.add(_failed_id)
                    # ── ISS-091: a TERMINAL event arriving through the stream ends
                    # the RUN, not just the step. The inline review gate's reject
                    # handler (_run_agent :4458) cancels the run and returns — but a
                    # generator ``return`` only ends THAT step, so without this the
                    # loop advanced to step cursor+1 and the run terminated on
                    # ``pipeline_complete``. The post-rejection steps bill nothing
                    # (every _run_agent short-circuits on the :3329 terminal guard),
                    # but fan-out still wrote ``subagent_runs='complete'`` /
                    # ``wave_runs='completed'`` rows for work that never happened —
                    # and wave_scheduler's resume skip trusts exactly those rows, so
                    # a rejected run, once resumed, skipped every wave and could
                    # never produce its deliverable again.
                    # The sibling of the declared-gate handler at :2454-2479 (WR-03).
                    # Keyed on the generic event type — no workflow name, no agent-id
                    # literal, no strategy branch (SC-001/INV-1).
                    elif event.get("type") == "pipeline_cancelled":
                        _terminated = True
                    yield event
                if _terminated:
                    # Flag-then-return rather than breaking mid-generator: the
                    # producer returns on its next statement, so the inner loop ends
                    # on its own and every ``finally`` (notably run_agent's
                    # build-scratch reset) still runs on its normal path. The event
                    # is already emitted by the producer — do NOT emit a second one.
                    await self._persist_budget_snapshot_if_active(ectx)
                    return

                # ── WR-02 (13 review fix): keep the review payload fresh ─────────
                # Declared pre-step HITL gates source their review payload from
                # ``ectx.last_streamed`` (gates/human.py), which used to be set
                # ONLY at the terminal deliverable block — every declared gate
                # opened with an EMPTY payload. Refresh it per completed step so
                # the gate before step N reviews step N-1's output. The terminal
                # block re-assigns it from the same ``results[-1]["output"]``
                # value, so deliverable resolution is byte-identical (no event is
                # emitted here — characterization parity holds).
                if results:
                    ectx.last_streamed = results[-1].get("output", "") or ""

                # -- Post-step: extract solution plan if declared (revision-pipeline-refactor) --
                # Declaration-driven hook (INV-1/SC-001): branches on the Step's boolean flag,
                # never on agent id or pipeline name. Default False → DORMANT on all existing
                # steps → INV-3 byte/event-identical on the 5 characterization goldens.
                # Use the local ``step`` variable (the just-completed compiled Step) rather than
                # ``ectx.current_step`` — the KernelServices.run_agent finally block restores
                # ``ectx.current_step`` to ``prev_step`` (None for the first step) before this
                # post-step check runs, so ``ectx.current_step`` is always None here.
                if getattr(step, "produces_solution_plan", False):
                    try:
                        from app.agents.revision_analyzer import parse_analyzer_output  # noqa: PLC0415
                        _raw = ectx.last_streamed or ""
                        ectx.analyzer_solution = parse_analyzer_output(_raw)
                        logger.debug("produces_solution_plan hook: solution_len=%d (run=%s)", len(ectx.analyzer_solution), ectx.run_id)
                    except Exception as _psp_exc:  # noqa: BLE001
                        logger.warning(
                            "produces_solution_plan hook failed (%s) — ectx.analyzer_solution stays ''",
                            _psp_exc,
                        )
                        ectx.analyzer_solution = ""

                # ── [KAN-73] after_step hook firing ───────────────────────────────
                # Fires AFTER the strategy loop and after ectx.last_streamed is
                # refreshed, so hooks see the completed step's output. Non-blocking
                # by design (no ``continue`` on block — after_step is audit-only
                # in all current hook implementations; a blocking after_step would
                # need a separate mechanism). INV-3 parity: a legacy step with no
                # declared hooks → nothing fires here (same as before_step).
                await self._fire_hooks(
                    "after_step", step, ectx, _registry,
                    extra={"agent_name": spec.name, "step_index": cursor},
                )

                # ── [D-03] Post-step gates (validation, conditional) ─────────────
                # Post-step gates evaluate AFTER the strategy completes. ``validation``
                # runs the step's declared validators + the block-critical / warn-
                # non-critical policy, emitting the additive ``validation_warning`` +
                # ``gate_*`` events; its ``block`` is surfaced as the additive
                # ``gate_blocked`` event only (the deliverable already produced; this
                # is the declarative post-build validation entry point, NOT the
                # inline task_loop build-loop validation which stays put per D-06).
                #
                # ``conditional`` (spec 014 / T14) is ALSO post-step here (moved
                # from the pre-step loop above) because by default it reads THIS
                # step's own ``route_decision`` artifact (route.condition_agent
                # defaults to the step's own id), which does not exist until the
                # strategy above has run. Unlike ``validation``'s block, its
                # ``route`` outcome IS consumed below — it redirects the cursor.
                _routed = False
                _cond_blocked = False
                async for _ge, _outcome, _gdetail in self._evaluate_gates(
                    step, ectx, _registry, phase="post",
                    # ISS-172a — WR-02 dedupe, which the pre-step loop has passed
                    # since the 13-review fix and this loop never did. It did not
                    # matter while ``human`` was a PRE-step gate; ADR-0013 moved it
                    # here, and an inline-gated step then opened the SAME review on
                    # the SAME gate_key twice — once from ``_should_gate`` ->
                    # ``_run_review_gate`` inside ``_run_agent``, once from the
                    # declared gate evaluated here. Symptom in the suite: a
                    # duplicate ``review_gate_ready`` and ``['block','block']``
                    # where one outcome was expected.
                    inline_gated=self._should_gate(spec, ectx),
                ):
                    # WR-04: skip the terminal (None, outcome) sentinel when
                    # forwarding (keeps the emitted stream identical) but still
                    # honor a ``route`` outcome below.
                    if _ge is not None:
                        yield _ge
                    # ── ISS-170: a conditional gate with nowhere to route ─────
                    # ``ConditionalGate`` returns GATE_BLOCK when the decision
                    # matches no ``route.outcomes`` entry AND the manifest
                    # declares no ``route.default_next`` — the documented
                    # hard-stop (spec 014 R-13). Only the ``route`` outcome was
                    # consumed here, so the block was forwarded to the client and
                    # then IGNORED: ``_routed`` stayed False, the step is not a
                    # leaf (it declares a route), and control fell through to the
                    # plain ``cursor = cursor + 1`` below — landing on whichever
                    # branch happens to be declared first in the manifest, purely
                    # as an array-order artifact. The run then reported
                    # ``pipeline_complete``, so a mis-routed run looked green.
                    #
                    # Read off the EVENT rather than ``_gdetail``: the gate's
                    # detail carries ``decision``/``reason`` but no gate name,
                    # while the ``gate_blocked`` event carries
                    # ``data.gate == "conditional"`` (conditional.py's GateOutcome
                    # events list). Narrow on purpose — ``validation``'s post-step
                    # block is intentionally soft (event-only, no halt) and a
                    # blanket ``elif _outcome == "block"`` would regress it.
                    if (
                        _outcome == "block"
                        and isinstance(_ge, dict)
                        and (_ge.get("data") or {}).get("gate") == "conditional"
                    ):
                        _cond_blocked = True
                    if _outcome == "cancel":
                        # ISS-172b — WR-03 parity for the POST-step loop. The
                        # pre-step loop has cancelled the run on a declared-gate
                        # rejection since the 13-review fix; this loop had no arm,
                        # so once ADR-0013 moved ``human`` post-step a Reject
                        # yielded its gate event and then fell through — downstream
                        # steps kept executing and the run terminated as a
                        # completion with the state machine stranded in
                        # ``waiting_for_user``. Mirrors the pre-step arm exactly;
                        # only the reason string differs, because a post-step gate
                        # reviews the step's OWN output rather than the previous
                        # step's.
                        _cur = self._state_machine.get_state(pipeline_run_id)
                        if _cur not in ("cancelled", "failed", "diverted"):
                            self._state_machine.transition(
                                pipeline_run_id, "cancelled"
                            )
                        await self._persist_budget_snapshot_if_active(ectx)
                        yield {
                            "type": "pipeline_cancelled",
                            "data": {
                                "pipeline_run_id": pipeline_run_id,
                                "reason": (
                                    f"User rejected at the review gate "
                                    f"after {spec.name}"
                                ),
                            },
                        }
                        return
                    if _outcome == "route":
                        # ── [spec 014 / T14] ConditionalGate route outcome ────
                        # ``_gdetail`` is the ``GateOutcome.detail`` the
                        # ConditionalGate (agents/capabilities/gates/conditional.py)
                        # sets on a matched route: ``{"trigger": ..., "target": ...}``.
                        _route_trigger = (
                            _gdetail.get("trigger") if isinstance(_gdetail, dict) else None
                        )
                        _route_target = (
                            _gdetail.get("target") if isinstance(_gdetail, dict) else None
                        )
                        # R-28 feedback travels with EITHER trigger type: the step arm
                        # stashes it in pending_route_feedback for the re-dispatched
                        # target (a loop-back rebuilds its context from scratch, so
                        # without this the retry is byte-identical to the first pass);
                        # the workflow arm below hands it to the child run as its
                        # user message, which is otherwise empty.
                        _route_feedback = (
                            _gdetail.get("feedback") if isinstance(_gdetail, dict) else None
                        )
                        if _route_trigger == "step":
                            # Resolve the target step's index in ordered_agents and
                            # jump the cursor directly to it — forward or backward,
                            # same code path (T13's while-loop conversion). R-10
                            # (compiler._validate_route_targets) already guarantees
                            # a "step" target names a real step id at compile time.
                            #
                            # R-05/R-10 dual-identity: a composed custom-agent step's
                            # ordered_agents entry carries the FULL
                            # "custom-agent:<instance_id>" id, but ``target`` is
                            # author-facing and commonly the bare ``instance_id`` (the
                            # same dual-identity the compiler's
                            # ``_validate_route_targets`` ``by_name`` map already
                            # accepts at compile time — see that method's docstring).
                            # Try an exact match first (byte-identical for every
                            # non-composed / already-full-id target); fall back to a
                            # ``":<target>"`` suffix match only when no exact match
                            # exists.
                            _route_index = next(
                                (i for i, s in enumerate(ordered_agents) if s.id == _route_target),
                                None,
                            )
                            if _route_index is None:
                                _route_index = next(
                                    (
                                        i for i, s in enumerate(ordered_agents)
                                        if s.id.endswith(f":{_route_target}")
                                    ),
                                    None,
                                )
                            if _route_index is not None:
                                if _route_index <= cursor:
                                    # ── [spec 014 / T18] R-07 loop-cap enforcement ──
                                    # A backward (or self) "step" jump is a LOOP
                                    # (forward branches never touch
                                    # step_visit_counts — R-06/data-model.md).
                                    # Check the jump TARGET's already-recorded
                                    # visit count against ``loop_max_iterations``
                                    # BEFORE letting the jump proceed. The cap
                                    # lives on THIS step's own ``route`` (the
                                    # step currently being dispatched, already
                                    # bound as ``step``) — RouteSpec is only
                                    # ever attached to the step declaring
                                    # ``gates: [conditional]`` (R-03), never to
                                    # its jump target (confirmed against the
                                    # A1 fixture: ``check`` declares
                                    # ``route.loop_max_iterations: 3``; its
                                    # target ``greet`` has no ``route`` at
                                    # all). Fail closed: raise the existing
                                    # BudgetExceeded (caught by the
                                    # ``except BudgetExceeded`` graceful-abort
                                    # handler below) rather than silently
                                    # capping the count. Only increment AFTER
                                    # the check passes.
                                    _step_route = getattr(step, "route", None)
                                    _loop_max = (
                                        _step_route.loop_max_iterations
                                        if _step_route is not None
                                        else 5
                                    )
                                    # ── [R-08 fix] key on the COMPOSED id ──────
                                    # This counter was WRITTEN under the authored
                                    # target ("greet") but every other reader looks it
                                    # up by ``spec.id`` ("custom-agent:greet") — see
                                    # the gate_key folds at ~4270/~4392, the completion
                                    # record at ~5431 and the failed-invocation triple
                                    # at ~4012. All three therefore read 0 forever on a
                                    # composed step, silently disarming R-08: a
                                    # loop-re-entered human gate reused pass 1's
                                    # gate_key, and a pass-2 completion masked a pass-1
                                    # failure. Only the cap worked, because it read with
                                    # the same bare key it wrote. Resolve once, here, to
                                    # the form everyone else uses. The BudgetExceeded
                                    # message still names the author-facing target.
                                    _visit_key = ordered_agents[_route_index].id
                                    _visits = ectx.step_visit_counts.get(_visit_key, 0)
                                    if _visits >= _loop_max:
                                        raise BudgetExceeded(
                                            "loop_iterations",
                                            f"step {_route_target!r} would be "
                                            f"revisited {_visits + 1} time(s), "
                                            f"exceeding loop_max_iterations="
                                            f"{_loop_max} (R-07)",
                                        )
                                    ectx.step_visit_counts[_visit_key] = _visits + 1
                                    # ── [R-28] Retry feedback for the loop target ──
                                    # A loop-back re-dispatches its target with context
                                    # rebuilt from scratch: same brief, no upstream
                                    # outputs (_filter_consumed_outputs stops at the
                                    # current step, so a loop target can NEVER consume
                                    # its own downstream judge's verdict). Same input →
                                    # same output → same decision, so before this the
                                    # loop could only ever run to loop_max_iterations
                                    # and fail closed. Observed live: the A1 fixture's
                                    # `greet` emitted a byte-identical 12-char answer on
                                    # passes 2, 3 and 4.
                                    #
                                    # Stash the reason here (BACKWARD jumps only — a
                                    # forward branch target is being reached for the
                                    # first time and has nothing to be told). The block
                                    # is composed and consumed in
                                    # _compose_context_message, then cleared, so it is
                                    # delivered exactly once per jump.
                                    _fb_store = getattr(
                                        ectx, "pending_route_feedback", None
                                    )
                                    if _fb_store is None:
                                        _fb_store = {}
                                        ectx.pending_route_feedback = _fb_store
                                    _fb_store[ordered_agents[_route_index].id] = {
                                        "from_step": step.id,
                                        "decision": (
                                            _gdetail.get("decision")
                                            if isinstance(_gdetail, dict) else None
                                        ),
                                        "from_output": getattr(ectx, "last_streamed", None),
                                        "pass_number": _visits + 2,
                                        "max_passes": _loop_max + 1,
                                        "authored": (
                                            _gdetail.get("feedback")
                                            if isinstance(_gdetail, dict) else None
                                        ),
                                    }
                                cursor = _route_index
                                _routed = True
                                # ── [spec 014 follow-up] explicit skip signal ──────
                                # ConditionalGate.evaluate (conditional.py) already
                                # scanned route.outcomes and computed which raw
                                # targets are being skipped (_gdetail["skipped_targets"])
                                # — this loop only does what only the dispatch loop
                                # CAN do: resolve each raw target string to a real
                                # ordered_agents id (dual-identity, same as
                                # _route_target above) and yield an explicit event, so
                                # the frontend can render "Skipped" with a definite
                                # reason instead of inferring it from an agent never
                                # receiving agent_start (ambiguous — that absence
                                # can't distinguish "skipped by routing" from "run
                                # ended mid-way for some other reason").
                                _skipped_ids: list[str] = []
                                for _skip_target in (
                                    _gdetail.get("skipped_targets", []) if isinstance(_gdetail, dict) else []
                                ):
                                    _sib_index = next(
                                        (i for i, s in enumerate(ordered_agents) if s.id == _skip_target),
                                        None,
                                    )
                                    if _sib_index is None:
                                        _sib_index = next(
                                            (
                                                i for i, s in enumerate(ordered_agents)
                                                if s.id.endswith(f":{_skip_target}")
                                            ),
                                            None,
                                        )
                                    if _sib_index is None:
                                        continue
                                    _sib_id = ordered_agents[_sib_index].id
                                    # Report a sibling ONLY if it never ran. A forward
                                    # branch target (say-hola in ex_A2_branch) is
                                    # genuinely skipped. A BACKWARD/loop target already
                                    # executed on every earlier pass, so calling it
                                    # "skipped" contradicts its own agent_complete
                                    # events — the UI honours the last lifecycle signal
                                    # and rendered a step that ran twice as Skipped,
                                    # under-reporting the run as 3/4 agents.
                                    if any(r.get("agent_id") == _sib_id for r in results):
                                        continue
                                    _skipped_ids.append(_sib_id)
                                    yield {
                                        "type": "agent_skipped",
                                        "data": {
                                            "agent_id": _sib_id,
                                            "step": step.id,
                                            "gate": "conditional",
                                            "reason": (
                                                f"conditional gate routed to "
                                                f"{_route_target!r} instead"
                                            ),
                                        },
                                    }
                                logger.info(
                                    "condition: step %s -> next=%s, skipped=%s",
                                    step.id, ordered_agents[_route_index].id, _skipped_ids or "-",
                                )
                        elif _route_trigger == "workflow":
                            # ── [spec 014 / T29] Cross-workflow trigger (R-12/R-13/R-14) ──
                            # Mint + spawn a NEW, independent WorkflowRun via the T28
                            # kernel delegate (``ectx.runner`` is the KernelServices
                            # handle, D-03) — this run does NOT wait on it (R-13,
                            # Option 2: the mint/spawn call is the only await; it
                            # returns as soon as the new run exists, not when it
                            # finishes).
                            logger.info(
                                "condition: step %s launching workflow %r (this run stops here — R-13)",
                                step.id, _route_target,
                            )
                            _diverted_to_run_id, _diverted_to_workflow = (
                                await ectx.runner.run_trigger_workflow(
                                    step, ectx, workflow_ref=_route_target,
                                    content=_route_feedback or "",
                                )
                            )
                            # R-14: the SAME state_machine.transition mechanism
                            # cancelled/failed use elsewhere in this file (persists
                            # to WorkflowRun.status via StateMachine._persist).
                            self._state_machine.transition(pipeline_run_id, "diverted")
                            # ── [spec 014 / R-20 audit finding, T41] diverted_at_step_id ──
                            # Same best-effort DB-write shape StateMachine._persist (T71)
                            # already uses for WorkflowRun.status: a fresh SessionLocal, a
                            # single row lookup, one attribute set, one commit — applied
                            # here as an additional small write on the SAME row this
                            # transition() call just updated, not a new DB-access pattern.
                            # Non-fatal: a DB hiccup here must not break the
                            # already-persisted "diverted" transition or the yield below.
                            try:
                                from app.models.database import SessionLocal
                                from app.models.workflow import WorkflowRun

                                _divert_db = SessionLocal()
                                try:
                                    _divert_wr = (
                                        _divert_db.query(WorkflowRun)
                                        .filter(WorkflowRun.id == pipeline_run_id)
                                        .first()
                                    )
                                    if _divert_wr is not None:
                                        _divert_wr.diverted_at_step_id = step.instance_id
                                        _divert_db.commit()
                                finally:
                                    _divert_db.close()
                            except Exception as _divert_exc:  # noqa: BLE001 — non-fatal
                                logger.debug(
                                    "diverted_at_step_id persist failed (non-fatal): %s",
                                    _divert_exc,
                                )
                            # ── [spec 014 / R-28] pipeline_diverted — additive event,
                            # emitted through the SAME generic event-forward path
                            # ``pipeline_cancelled`` already uses (a bare ``yield``
                            # here; INV-3, decision-log #18). ``diverted_to_workflow``
                            # is the ``target_pipeline_type`` ``run_trigger_workflow``
                            # already resolved before minting — never the manifest's
                            # literal ``"self"`` sentinel, even when ``_route_target``
                            # (the raw manifest ``target``) was ``"self"``.
                            yield {
                                "type": "pipeline_diverted",
                                "data": {
                                    "pipeline_run_id": pipeline_run_id,
                                    "diverted_to_run_id": _diverted_to_run_id,
                                    "diverted_to_workflow": _diverted_to_workflow,
                                },
                            }
                            # R-13: THIS run's dispatch loop ends here — no
                            # default_next, no cursor advance, no post_step
                            # capability, no pipeline_complete.
                            return
                if _cond_blocked:
                    # ── ISS-170: terminate the RUN, mirroring the pre-step loop's
                    # ``_blocked`` arm (§8b). A block is a refusal, so it takes the
                    # single-terminal shape the fan-out child-failure abort uses
                    # (KRN-004): one ``pipeline_failed``, no further steps, no
                    # ``pipeline_complete``. ``agents_completed`` is ``cursor + 1``
                    # rather than the pre-step arm's ``cursor`` — this step's own
                    # strategy has already run and produced output; it is the
                    # ROUTING that had nowhere to go.
                    _cur = self._state_machine.get_state(pipeline_run_id)
                    if _cur not in ("cancelled", "failed", "diverted"):
                        self._state_machine.transition(pipeline_run_id, "failed")
                    await self._persist_budget_snapshot_if_active(ectx, force=True)
                    yield {
                        "type": "pipeline_failed",
                        "data": {
                            "pipeline_type": pipeline_type,
                            "pipeline_run_id": pipeline_run_id,
                            "total_duration": round(time.time() - total_start, 2),
                            "agents_completed": cursor + 1,
                            "agents_total": len(ordered_agents),
                            "error": (
                                f"{spec.name}'s conditional gate had nowhere to "
                                f"route: no matching outcome and no default_next."
                            ),
                        },
                    }
                    return

                if _routed:
                    # The conditional gate redirected the cursor to the route
                    # target — skip the post_step capability and the default
                    # ``cursor += 1`` (the jump above already set the exact next
                    # cursor; forward and backward targets are the same code path,
                    # T13).
                    continue

                # ── Declared post-step capability (INV-1 / CR-06) ────────────────
                # After the step's strategy finishes, run any declared ``post_step``
                # capability (resolved by NAME from the compiled step — NO workflow-
                # name/agent-id branch). This is where the in-place-revision pre-edit
                # baseline + post-edit Both-validation fix-loop now lives (relocated
                # out of the formerly kernel-resident revision block). It is
                # non-yielding (side effects only) and never aborts the run (the
                # capability swallows its own errors).
                post_step_name = getattr(step, "post_step", None)
                if post_step_name:
                    await _registry.resolve("post_step", post_step_name).run(step, ectx)

                # ── [spec 014 / T13-T14 fix] Stop at a LEAF step, don't fall through ──
                # ``step.is_leaf`` (R-26, compiler._compute_is_leaf) is True iff nothing
                # in the compiled graph legitimately continues from this step — but a
                # leaf step is not always array-LAST: a forward branch's target (e.g.
                # ``say-hello`` in ex_A2_branch) is a leaf sitting
                # BEFORE the other branch's target in array order. A bare ``cursor += 1``
                # here walked straight into that other branch's exclusive target — the
                # T25 mutual-exclusivity failure. Advancing all the way past
                # ``ordered_agents`` on a leaf ends the walk instead, exactly like the
                # natural end-of-array case already did (is_leaf's own docstring: for a
                # step with no route, is_leaf is True only at array-end OR when the next
                # array slot is stolen by another branch — this makes both cases end the
                # loop). Every non-leaf step still gets the plain ``cursor + 1`` it
                # always had (parity for every pre-014 / non-branching workflow).
                #
                # ...but `is_leaf` is computed by the COMPILER over `compiled.steps`,
                # while this loop walks `ordered_agents` (the ROSTER). Those are 1:1 for
                # every file-manifest run, and were assumed to be so here. They are NOT
                # for a COMPOSED run (Path B): an agent that exists only in the user's
                # selections has no step in the base plan, so a 1-step plan + 2-agent
                # roster made the single compiled step `is_leaf` (i+1 >= len(steps)) and
                # this line jumped the cursor clean past the composed agent — it never
                # ran, and the run "completed" with agents_completed < agents_total.
                # `is_leaf` only ever claims that nothing in the COMPILED GRAPH follows;
                # when the next roster entry has no compiled step at all, the graph has
                # no opinion about it and plain array-adjacency (the pre-014 behaviour)
                # is what must win.
                _next_spec = (
                    ordered_agents[cursor + 1] if cursor + 1 < len(ordered_agents) else None
                )
                _leaf_ends_the_walk = getattr(step, "is_leaf", False) and (
                    _next_spec is None or _next_spec.id in _steps_by_agent
                )
                cursor = len(ordered_agents) if _leaf_ends_the_walk else cursor + 1

        except asyncio.CancelledError:
            self._state_machine.transition(pipeline_run_id, "cancelled")
            # OBS-01: persist the budget snapshot on CANCEL (the completed workers'
            # fragments persisted by 11-03 survive; pending workers never spawned).
            # Strictly conditional on fan-out activity so a cancelled non-fanout run
            # stays byte/event-identical (no snapshot written when nothing fanned out).
            await self._persist_budget_snapshot_if_active(ectx)
            yield {"type": "pipeline_cancelled", "data": {"pipeline_run_id": pipeline_run_id}}
            # ── ISS-023 (IN-04): single canonical pipeline_cancelled on the ───────
            # cooperative per-chunk cancel path. The Stop button sets ``cancel_event``;
            # the per-chunk check (:2613) raises CancelledError, which lands HERE. If we
            # re-raise, the cancellation propagates out of ``execute()`` into the
            # websocket bg task's ``except CancelledError`` (_run_pipeline_to_queue),
            # which enqueues a SECOND pipeline_cancelled — a discarded duplicate (the
            # drainer breaks on the first terminal; _cleanup_pipeline drops the rest).
            # On the COOPERATIVE path we have already yielded the one true terminal, so
            # RETURN (the async-for ends normally, mirroring the pre-agent/between-agent
            # cooperative terminals at :1737-1741 / :1797-1807 which yield+return). Only
            # a GENUINE destructive ``task.cancel()`` (the WebSocketDisconnect path /
            # the no-event defensive fallback — cancel_event NOT set) re-raises, so the
            # disconnect cleanup that depends on the propagating CancelledError is
            # preserved. Keyed on the generic cooperative signal only (no workflow /
            # model / agent name — SC-001).
            if cancel_event is not None and cancel_event.is_set():
                return
            raise
        except BudgetExceeded as _budget_exc:
            # OBS-01 graceful abort: a fan-out reserve/boundary breach aborts the run.
            # Persist the snapshot (always active here — a BudgetExceeded means fan-out
            # ran), surface the completed workers' 11-03 fragment artifacts in a partial
            # structured summary, and emit a visible budget abort event reporting the
            # breached dimension. Pending workers never spawned (reserve-before-spawn).
            self._state_machine.transition(pipeline_run_id, "failed")
            await self._persist_budget_snapshot_if_active(ectx, force=True)
            yield {
                "type": "budget_aborted",
                "data": {
                    "pipeline_run_id": pipeline_run_id,
                    "dimension": getattr(_budget_exc, "dimension", "unknown"),
                    "message": str(_budget_exc),
                    "partial_results": self._collect_partial_fragments(ectx),
                },
            }
            return
        except FanoutWorkerFailed as _fanout_exc:
            # KRN-004 (task.md R-03): a fan-out step where one or more spawned
            # children ended ``status="failed"`` used to proceed to
            # pipeline_complete as if the step had succeeded — nothing aggregated
            # child failures into a run-level outcome. Mirror the BudgetExceeded
            # graceful-abort precedent exactly: ONE pipeline_failed terminal, no
            # further steps, no pipeline_complete. Each failed child's own
            # subagent_result event was already yielded by run_fanout before this
            # raised, so the per-child diagnosis is preserved; this is the single
            # additional parent-level terminal signal that was previously missing.
            self._state_machine.transition(pipeline_run_id, "failed")
            await self._persist_budget_snapshot_if_active(ectx, force=True)
            yield {
                "type": "pipeline_failed",
                "data": {
                    "pipeline_type": pipeline_type,
                    "pipeline_run_id": pipeline_run_id,
                    "total_duration": round(time.time() - total_start, 2),
                    "agents_completed": 0,
                    "agents_total": len(ordered_agents),
                    "agents_failed": sorted(
                        {str(w.get("agent")) for w in _fanout_exc.failed}
                    ),
                    "error": str(_fanout_exc),
                    "timestamp": _now(),
                },
            }
            return

        # ── Step 5: Pipeline complete ─────────────────────────────────────
        # Guard: if the run was already cancelled (e.g. user rejected a review
        # gate), don't try to transition to "completed" — that would throw a
        # StateMachineError because "cancelled" is a terminal state.
        current_state = self._state_machine.get_state(pipeline_run_id)

        # ── F3 (13-06): total collapse → pipeline_failed terminal ───────────────
        # When EVERY agent that ran errored and NOTHING completed (``not results
        # and _failed_agent_ids``), the run is a failure — not a completion with
        # final_output=''. Mirror the BudgetExceeded failed-terminal precedent:
        # transition to "failed", persist the budget snapshot if fan-out was
        # active, emit ONE ``pipeline_failed`` event, and RETURN before
        # deliverable resolution (no empty-deliverable resolution, no
        # deliverable ref write — composes with the 13-05 guard — and no
        # pipeline_complete). Counters only — no workflow-name branch (SC-001).
        if (
            current_state not in ("cancelled", "failed", "diverted")
            and not results
            and _failed_agent_ids
        ):
            self._state_machine.transition(pipeline_run_id, "failed")
            await self._persist_budget_snapshot_if_active(ectx)
            yield {
                "type": "pipeline_failed",
                "data": {
                    "pipeline_type": pipeline_type,
                    "pipeline_run_id": pipeline_run_id,
                    "total_duration": round(time.time() - total_start, 2),
                    "agents_completed": 0,
                    "agents_total": len(ordered_agents),
                    "agents_failed": sorted(_failed_agent_ids),
                    # IN-04 (13 review fix): neutral message — the branch fires
                    # on "no agent completed AND at least one errored", but
                    # agents skipped by a pre-step gate block are neither
                    # completed nor failed, so "all agents failed" could
                    # overstate the failure set (agents_failed is the precise
                    # list; agents_total counts every manifest step).
                    "error": "no agent completed",
                    "timestamp": _now(),
                },
            }
            return

        if current_state not in ("cancelled", "failed", "diverted"):
            self._state_machine.transition(pipeline_run_id, "completed")

        # Determine the final deliverable below via the DECLARED deliverable resolver
        # capability (single_file → prototype.html for prototype/revision;
        # serialized_sandbox → code-gen bundle; streamed_text/ppt → streamed+unwrapped
        # output). The post-edit revision validation fix-loop already ran inside the
        # declared ``revision_validation`` post-step capability (invoked by the
        # per-step dispatch loop above) — the kernel hosts NO in-place-revision
        # block, no agent-id literal, and no by-name revision exception (07-10 / CR-06).

        # ── Deliverable routing concern — declared by the compiled plan ─────────
        # (MAN-04, concern 2). The deliverable resolver NAME for this run is
        # declared on `compiled.deliverable.strategy` (e.g. single_file /
        # serialized_sandbox / streamed_text / ppt), sourced from the manifest +
        # validated against the CapabilityRegistry at compile time. The byte-resolution
        # flows entirely through the declared resolver capability (07-04 wired it; the
        # legacy chooser was deleted from the kernel in 07-05). The spec is bound here
        # so the routing concern is genuinely sourced from the compiled plan, not a
        # legacy name dict.
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

        # ── Resolve the deliverable via the declared resolver capability (INV-1) ──
        # The deliverable resolver NAME is declared on compiled.deliverable.strategy
        # (single_file / serialized_sandbox / streamed_text / ppt), validated against
        # the registry at compile time. The engine routes resolution through
        # registry.resolve("deliverable", compiled.deliverable.strategy).resolve(ctx),
        # reading deliverable.name — NO legacy by-class deliverable chooser / workflow-
        # name branch on the routed path (deleted from the kernel in 07-05). The resolver
        # reads the run state off ctx: ctx.deliverable (the compiled spec), ctx.last_streamed
        # (the final agent's streamed output), ctx.revision_original_html (the seeded
        # original), and the sandbox via ctx.runner. The ppt resolver owns the carousel
        # sanitize (PARITY-07) so the inline mid-stream sanitize call site is
        # gone too. serialized_sandbox returns None when the sandbox holds 0 deliverable
        # files (the legacy count>0 guard); the engine then falls back to streamed_text
        # — byte-identical to the legacy code-gen→text fall-through.
        ectx.deliverable = compiled.deliverable
        ectx.last_streamed = results[-1]["output"] if results else ""

        _deliverable_strategy = compiled.deliverable.strategy or "streamed_text"
        # WR-01 (18 review fix): the EFFECTIVE strategy is the one that actually
        # produced the emitted bytes. It starts as the DECLARED strategy and is
        # reassigned to "streamed_text" when the fallback below fires, so the
        # emitted deliverable_mimetype (computed at :~1917) always matches the
        # bytes the FE receives — never the declared "serialized_sandbox" →
        # "application/zip" while final_output is markdown text.
        _effective_strategy = _deliverable_strategy
        _resolver = _CAPABILITY_REGISTRY.resolve("deliverable", _deliverable_strategy)
        final_output = _resolver.resolve(ectx)
        if final_output is None:
            # The declared resolver did not claim the deliverable (serialized_sandbox
            # with 0 files) — fall back to the streamed-text resolver (legacy parity).
            _effective_strategy = "streamed_text"
            final_output = _CAPABILITY_REGISTRY.resolve(
                "deliverable", "streamed_text"
            ).resolve(ectx)

        # ── F2 (13-05): persist the resolved deliverable as a generic ref ───────
        # Write the run's final_output as a kind="deliverable" artifact_ref so a
        # later run_revision can resolve the parent deliverable regardless of which
        # workflow produced it (the FE targets a ``*_output`` type that no producer
        # write ever persists — the FR-014 fallback chain in _handle_revision reads
        # this ref). Guarded on a non-empty deliverable AND at least one completed
        # agent: a run with no completed agents or an empty deliverable writes
        # NOTHING (keeps the all-agents-failed path write-free, and artifact writes
        # emit no WS events so the characterization snapshots stay byte/event
        # identical). visibility="workspace" matches the producer-write policy
        # (05-06) so the same-owner cross-run _handle_revision read passes the
        # owner+visibility scope filter. SC-001: "deliverable" is a generic kind —
        # no workflow name, no agent-id literal.
        if final_output and results:
            # IN-05 (13 review fix): attribute the deliverable ref to the agent
            # that ACTUALLY produced its content — the latest typed ref with
            # byte-identical content (e.g. prototype-build via the single_file
            # resolver) — not blindly the final manifest agent (which may be a
            # validator that produced nothing). Falls back to the last agent
            # when no typed ref matches (resolver-transformed output, e.g. the
            # ppt carousel sanitize). Lineage metadata only: content/kind/hash
            # and the event stream are unchanged (artifact writes emit no WS
            # events — INV-3 snapshots unaffected). No agent-id literal (SC-001).
            _deliverable_producer = (
                ordered_agents[-1].id if ordered_agents else "deliverable"
            )
            for _ref in reversed(ectx.artifacts.tree(ectx.run_id)):
                if _ref.content == final_output:
                    _deliverable_producer = _ref.producer_agent
                    break
            # ArtifactRef.content is typed str (write_ref hashes it via
            # hashlib.sha256(content.encode("utf-8"))) — a structured deliverable
            # (e.g. repo_diff's dict payload) must be serialized before it reaches
            # the typed graph. final_output itself stays a dict for the WS
            # pipeline_complete event / FE consumption (untouched above).
            _deliverable_content = (
                final_output
                if isinstance(final_output, str)
                else json.dumps(final_output, sort_keys=True)
            )
            await self._dual_write_artifact(
                ectx,
                producer_agent=_deliverable_producer,
                producer_step="deliverable",
                content=_deliverable_content,
                kind="deliverable",
                location="artifact_refs/deliverable",
                visibility="workspace",
            )

        # (Prototype revisions are now produced by the agent editing
        # prototype.html in the workspace directly — see the output-capture
        # block above. The legacy REVISION_DIFF regex-merge has been removed.)
        # Token totals for the frontend TokenUsageSummary card. The client RESETS
        # its running totals on pipeline_complete, so they must be present here for
        # EVERY pipeline (otherwise the card hides itself). Pricing matches the
        # per-run persistence in websocket.py (Haiku: $0.25/M in, $1.25/M out).
        # OBS-01: persist the budget snapshot on COMPLETION (strictly conditional on
        # fan-out activity — a run that never fanned out writes NO snapshot, so the 5
        # characterization snapshots stay byte/event-identical, Pitfall 3).
        await self._persist_budget_snapshot_if_active(ectx)

        from app.core.config import settings as _settings
        _tok_in = sum(r.get("input_tokens", 0) or 0 for r in results)
        _tok_out = sum(r.get("output_tokens", 0) or 0 for r in results)
        # ISS-032: run-total prompt-cache split (0 under the scripted model → the
        # cost math is unchanged and the goldens stay byte/event-identical).
        _cache_read = sum(r.get("cache_read_tokens", 0) or 0 for r in results)
        _cache_write = sum(r.get("cache_write_tokens", 0) or 0 for r in results)
        # ISS-033: fold in every model call that ran OUTSIDE the per-agent stream —
        # the SmartPlanner + clarify one-shots (43-04) and the validation fix-loop's
        # sub-agent (ISS-033-A / FIX-230) — so their tokens are COUNTED in the run
        # totals instead of being silently dropped. ONE fold, ONE accumulator: a new
        # aux source registers by feeding this sink, never by adding a second sum.
        _tok_in += sum(u.get("input_tokens", 0) or 0 for u in aux_token_usage)
        _tok_out += sum(u.get("output_tokens", 0) or 0 for u in aux_token_usage)
        _cache_read += sum(u.get("cache_read_tokens", 0) or 0 for u in aux_token_usage)
        _cache_write += sum(u.get("cache_write_tokens", 0) or 0 for u in aux_token_usage)
        # ── ISS-021 (18-01): the DECLARED deliverable shape hint ────────────────
        # Surface a type-driven deliverable contract on EVERY pipeline_complete so
        # the FE renderer (18-03) dispatches on a mimetype, never a workflow name
        # (SC-001). Sourced ONLY from the already-resolved ``ectx.deliverable``
        # (set at :953/:1838) — no new plumbing, no cross-boundary import: prefer
        # the author-DECLARED ``mimetype``, else the per-resolver default computed
        # from the DECLARED strategy/name (never content-sniffed from the bytes).
        from agents.capabilities.deliverables._mimetype import (
            default_mimetype as _default_mimetype,
        )
        _deliverable_name = getattr(ectx.deliverable, "name", None)
        # WR-01 (18 review fix): derive the default from the EFFECTIVE strategy
        # (the resolver that actually produced the bytes), not the DECLARED one, so
        # a serialized_sandbox→streamed_text fallback advertises text/markdown (the
        # real bytes) rather than application/zip. The author-declared `mimetype`
        # still wins when present; only the computed default tracks the fallback.
        _deliverable_mimetype = getattr(ectx.deliverable, "mimetype", None) or (
            _default_mimetype(_effective_strategy, _deliverable_name)
        )
        _pipeline_complete_data = {
            "pipeline_type": pipeline_type,
            "pipeline_run_id": pipeline_run_id,
            "total_duration": round(time.time() - total_start, 2),
            "agents_completed": len(results),
            "agents_total": len(ordered_agents),
            "final_output": final_output,
            "deliverable_mimetype": _deliverable_mimetype,
            "deliverable_filename": _deliverable_name,
            "total_input_tokens": _tok_in,
            "total_output_tokens": _tok_out,
            "total_tokens": _tok_in + _tok_out,
            # ISS-032: run-total cache split — additive telemetry, stripped by
            # _VOLATILE_STRIP_KEYS so the goldens stay byte/event-identical.
            "total_cache_read_tokens": _cache_read,
            "total_cache_write_tokens": _cache_write,
            # ISS-032: price the UNCACHED input split (input − cache) plus the
            # cache_read/cache_write tiers via the ONE shared estimate_cost_usd —
            # no double-count (input_tokens is the TOTAL incl. cache; subtract once).
            # Under the scripted model cache=0 → uncached=total and the cost is
            # unchanged, so the goldens stay byte/event-identical.
            "estimated_cost_usd": estimate_cost_usd(
                model_id or _settings.BEDROCK_INFERENCE_PROFILE_ID,
                input_tokens=max(0, _tok_in - _cache_read - _cache_write),
                output_tokens=_tok_out,
                cache_read_tokens=_cache_read,
                cache_write_tokens=_cache_write,
                cache_ttl=_settings.BEDROCK_PROMPT_CACHE_TTL,
            ),
            # ISS-034: the as-if-UNCACHED counterfactual on the SAME token base —
            # every input token at 1x, no cache tiers. ``full - estimated`` is the
            # SIGNED effect of prompt caching on this run, and it is NEGATIVE
            # whenever the run wrote cache entries it never re-read (cache_write_5m
            # is 1.25x input). Same shared estimate_cost_usd (INV-12) — no second
            # rate table. Additive + stripped by _VOLATILE_STRIP_KEYS, so the
            # goldens stay byte/event-identical (INV-3).
            "estimated_cost_full_usd": estimate_cost_usd(
                model_id or _settings.BEDROCK_INFERENCE_PROFILE_ID,
                input_tokens=_tok_in,
                output_tokens=_tok_out,
            ),
            "model_id": model_id or _settings.BEDROCK_INFERENCE_PROFILE_ID,
        }
        # ── F3 (13-06): degraded completion — STRICTLY CONDITIONAL fields ───────
        # A partially-failed run (some agents completed, at least one agent_error
        # observed) carries the ADDITIVE ``status="degraded"`` + ``agents_failed``
        # keys. A clean run's payload is byte-identical — neither key is present
        # (mirrors the OBS-01 conditional-snapshot pattern; the 5 characterization
        # snapshots gate this parity).
        # WR-05 (13 review fix): key the failure set on agents that did NOT
        # subsequently complete. A RECOVERABLE agent_error (the agent-timeout
        # degrade path emits one, then continues with partial/fallback output and
        # appends to results) is a completion, not a failure — pre-fix such an
        # agent appeared in BOTH agents_completed and agents_failed, and a
        # timeout-only run flipped to "degraded" (a behavior change for runs
        # that previously presented as clean completions). The total-collapse
        # branch above is unaffected (results is empty there, so the
        # subtraction removes nothing).
        #
        # ── ISS-028: key the unrecovered decision on (agent_id, task_number) ─────
        # The plain ``_failed_agent_ids - {completed agent_ids}`` collapsed on the
        # agent_id, so in the task_loop — where ONE agent_id (e.g. prototype-build)
        # runs across all tasks — a task K completion masked a task K+1 hard error:
        # the agent_id was in BOTH sets, subtracted to ∅, and a HALF-BUILT
        # deliverable reported a clean pipeline_complete. Subtract the COMPLETED
        # ``(agent_id, task_number)`` pairs from the per-invocation failure pairs
        # (``ectx.failed_invocations``, populated at every _run_agent agent_error)
        # instead. The single-shot timeout-recovery case is preserved: the error +
        # the completion share one invocation → the SAME ("" task_number) pair →
        # subtracted (WR-05 intact). DORMANT on the goldens (all tasks succeed →
        # failed_invocations is empty → no degraded key → INV-3 byte-identical). The
        # ``agents_failed`` payload stays a sorted agent_id list (the FE / DB
        # contract is unchanged; only the DECISION gained task granularity). A
        # defensive floor keeps any _failed_agent_ids agent that completed NOTHING
        # at all, so a future agent_error path that skips the recorder can't silently
        # regress to a clean completion.
        # R-08: ``visit_count`` folded into the triple too — otherwise a step re-
        # entered via a route loop-back's pass-2 COMPLETION (same agent_id/task_number,
        # different visit_count) would mask a pass-1 hard failure. ``.get("visit_count",
        # 0)`` defaults results entries that predate this field (e.g. the RESUME-17
        # gate-reentry short-circuit) to 0, matching ``step_visit_counts``'s own default.
        _completed_pairs = {
            (r.get("agent_id"), r.get("task_number", "") or "", r.get("visit_count", 0))
            for r in results
        }
        _completed_agent_ids = {r.get("agent_id") for r in results}
        _unrecovered_agents = {
            agent_id
            for (agent_id, task_number, visit_count) in getattr(ectx, "failed_invocations", set())
            if (agent_id, task_number, visit_count) not in _completed_pairs
        }
        # Floor (no regression): an errored agent with zero completions anywhere.
        _unrecovered_agents |= (_failed_agent_ids - _completed_agent_ids)
        if results and _unrecovered_agents:
            _pipeline_complete_data["status"] = "degraded"
            _pipeline_complete_data["agents_failed"] = sorted(_unrecovered_agents)
        # Guard (mirrors the ``pipeline_failed`` guard above): a run parked/stopped
        # at a re-entered gate (cancelled/failed BEFORE this terminal block, e.g. by
        # the step-boundary state-machine check above) must never report
        # ``pipeline_complete`` — that is what flips the persisted run status back
        # to "completed" past a rejection (``_reconcile_terminal_status``). Its own
        # terminal event (``pipeline_cancelled`` / ``pipeline_failed``) was already
        # emitted at the point of cancellation/failure.
        if current_state not in ("cancelled", "failed", "diverted"):
            yield {
                "type": "pipeline_complete",
                "data": _pipeline_complete_data,
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
        usage_sink=None,
    ) -> tuple[dict, str]:
        """Run the Deep_Planner_Agent with a timeout. Returns (planning_context, gate)."""
        try:
            # ISS-056/H3(b): if a design system was already chosen in the wizard,
            # thread its friendly name into the planner prompt so it doesn't flag
            # visual style as missing. Keyed on od_context.ds_id (generic, INV-1).
            _od = (ectx.od_context or {}) if ectx is not None else {}
            design_context = (
                {
                    "template_name": _od.get("template_name"),
                    "ds_name": _od.get("ds_name"),
                }
                if _od.get("ds_id") else None
            )
            planning_context = await asyncio.wait_for(
                self._invoke_planner(
                    user_message, model_id, pipeline_type,
                    usage_sink=usage_sink, design_context=design_context,
                ),
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

    async def _invoke_planner(
        self, user_message: str, model_id: str | None, pipeline_type: str = "custom",
        usage_sink=None, design_context: dict | None = None,
    ) -> dict:
        """Invoke the SmartPlanner — single structured LLM call, 2-5 seconds."""
        from agents.planner.smart_planner import SmartPlanner

        # ISS-033: thread the run-usage sink so the planner's model-call tokens are
        # counted in the run accounting (via the shared cached_invoke inside plan()).
        planner = SmartPlanner(model_id=model_id, usage_sink=usage_sink)
        return await planner.plan(user_message, pipeline_type, design_context=design_context)

    def _default_planning_context(self, user_message: str, timed_out: bool = False) -> dict:
        # DO NOT add keys: this dict is serialized verbatim into the planner event and the
        # characterization normalizer does not recurse into it, so a new key breaks INV-3.
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

    def _rehydrate_planning_context(self, ectx: ExecutionContext, user_message: str) -> dict:
        """Reconstruct a resumed run's planning context from the DURABLE rows.

        BUGFIX-SPEC-REVISION-CONTEXT D2. A resume takes the planner-skip path and used to
        rebuild the context from ``_default_planning_context`` — ``inferred_intent`` cut to
        ``user_message[:200]`` and every list empty. Measured on the reported run: the
        injected block collapsed 4,591 → 291 chars and 16 of the 18 dispatches ran on the
        stub. The real content was never lost: RESUME-04 hydration (:1406) already adopts
        EVERY durable kind into ``ectx.artifacts`` before this point, so both the
        ``planning_context`` row and the ``clarifications`` rounds are in the graph and
        this is a pure read — no new store call, no new write, no new storage.

        The planner is NOT re-invoked. Re-running it regresses BUG-R05 (quick 260719-hd5),
        which ``test_offset0_gate_resume_does_not_replan_or_reclarify`` guards.

        Never raises into the run: a missing row, unparseable JSON, a malformed
        clarifications shape, or a planner row whose ``explicit_constraints`` is not a
        list of strings each degrade to the best context available.

        KNOWN LOSSINESS. ``_persist_qa`` (clarify_engine.py:867-884) writes the raw
        ``responses`` map BEFORE ``_merge_answers`` (:931-938) auto-fills a
        ``recommended_answer`` for unanswered questions, and persists neither
        ``recommended_answer`` nor ``ambiguity_category``. So: questions the user ANSWERED
        reconstruct exactly; questions the user SKIPPED cannot have their auto-filled
        constraints recovered, and ``clarified_topics`` comes back empty. The alternative —
        persisting the merged context as a new ``planning_context`` version on the clarify
        path — would close the gap at the cost of a write on that path, and is deliberately
        not taken here.
        """
        base_ref = None
        for ref in ectx.artifacts.tree(ectx.run_id):
            if ref.kind == "planning_context" and (
                base_ref is None or ref.version >= base_ref.version
            ):
                base_ref = ref
        if base_ref is None:
            # No durable planner row (planner == "skip", an offline test, or a run
            # predating the persist) ⇒ exactly today's behaviour (INV-3 by construction).
            return self._default_planning_context(user_message)

        try:
            base = json.loads(base_ref.content)
            if not isinstance(base, dict):
                raise ValueError(f"planning_context is {type(base).__name__}, not a dict")
        except (ValueError, TypeError) as exc:
            logger.warning(
                "resume rehydrate: planning_context for run %s is unreadable (%s) — "
                "falling back to the default stub",
                ectx.run_id, exc,
            )
            return self._default_planning_context(user_message)

        # The planner row is raw, UNVALIDATED LLM JSON (smart_planner.py persists whatever
        # the model returned), so ``explicit_constraints`` can be a non-list or hold
        # non-string members. The idempotency ``set()`` below and the summary log's
        # ``len()`` would then raise TypeError straight OUT of this helper — breaking the
        # "never raises into the run" contract above on a resumed run, a path that did not
        # exist before D2 became the first reader of this row. Normalise ONCE, here, so
        # every later use is total. A well-formed row is unchanged (INV-3 dormant).
        _constraints = base.get("explicit_constraints")
        if not isinstance(_constraints, list):
            if _constraints:
                logger.warning(
                    "resume rehydrate: planning_context for run %s has explicit_constraints "
                    "as %s, not a list — dropping it and merging onto an empty list",
                    ectx.run_id, type(_constraints).__name__,
                )
            base["explicit_constraints"] = []
        else:
            _strs = [c for c in _constraints if isinstance(c, str)]
            if len(_strs) != len(_constraints):
                logger.warning(
                    "resume rehydrate: planning_context for run %s carried %d non-string "
                    "explicit_constraint(s) — dropped",
                    ectx.run_id, len(_constraints) - len(_strs),
                )
            base["explicit_constraints"] = _strs

        clar_refs = sorted(
            (r for r in ectx.artifacts.tree(ectx.run_id) if r.kind == "clarifications"),
            key=lambda r: r.version,
        )
        merger = _ClarifyEngineImpl()
        rounds_merged = 0
        for ref in clar_refs:
            try:
                pairs = json.loads(ref.content)
            except (ValueError, TypeError):
                logger.warning(
                    "resume rehydrate: clarifications v%s for run %s is unreadable — skipped",
                    ref.version, ectx.run_id, exc_info=True,
                )
                continue
            if not isinstance(pairs, list):
                logger.warning(
                    "resume rehydrate: clarifications v%s for run %s is a %s, not a list "
                    "of Q&A pairs — skipped",
                    ref.version, ectx.run_id, type(pairs).__name__,
                )
                continue
            # Idempotent: a pair whose rendered constraint is already present is dropped,
            # so re-merging a base that already carries answers cannot double-count.
            existing = set(base.get("explicit_constraints") or [])
            questions, responses = [], []
            for p in pairs:
                # A row whose shape is wrong is skipped rather than crashing the resume:
                # _merge_answers indexes q["question_text"] directly.
                if not isinstance(p, dict) or not p.get("question_id") or not p.get("question_text"):
                    continue
                answer = p.get("answer")
                if answer and f"{p['question_text']} → {answer}" in existing:
                    continue
                questions.append({
                    "question_id": p["question_id"],
                    "question_text": p["question_text"],
                })
                if answer:
                    responses.append({"question_id": p["question_id"], "answer": answer})
            if not questions:
                continue
            try:
                # Reuse the ONE merge implementation (INV-12) — the engine must not
                # re-derive the "{question} → {answer}" constraint format. The catch is
                # narrow ON PURPOSE: it exists for a malformed durable row whose JSON
                # parses but whose shape is wrong. A broad catch here would silently hand
                # back a context with no clarification answers — the exact silent
                # degradation this fix removes.
                base = merger._merge_answers(base, questions, responses)
                rounds_merged += 1
            except (AttributeError, TypeError, KeyError):
                logger.warning(
                    "resume rehydrate: clarifications v%s for run %s has an unexpected "
                    "shape — keeping the unmerged context for this round",
                    ref.version, ectx.run_id, exc_info=True,
                )

        # A resumed run is mid-build: a stale CLARIFY_REQUIRED on the persisted row must
        # not leak to a consumer. The caller's gate_verdict local is unaffected.
        base["execution_gate"] = "PROCEED"

        logger.info(
            "resume rehydrate: run %s reconstructed planning context from durable rows — "
            "%d clarification round(s) merged, %d explicit constraint(s), %d chars of "
            "planner JSON (stub would have been %d chars of intent)",
            ectx.run_id, rounds_merged, len(base.get("explicit_constraints") or []),
            len(base_ref.content), len(user_message[:200]),
        )
        return base

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
        absent — direct unit-style invocations of ``_run_agent`` (or the task_loop strategy) that
        construct an ``ExecutionContext`` WITHOUT going through ``execute()`` — fall back to the
        threaded ``model_id`` (today's behavior). This fallback is parity-safe: with no override
        and no manifest model the resolver itself returns ``model_id or Haiku``, so the resolved
        id is identical either way (INV-3).
        """
        resolver = ectx.model_resolver
        if resolver is None:
            return model_id
        return resolver.resolve(spec, step)

    async def _derive_fanout(self, event: dict, ectx: ExecutionContext) -> AsyncGenerator[dict, None]:
        """Derive a fan-out from a ``spawn_subagents`` tool_result + fulfil it (FANOUT-02).

        Parses the structured request the spawn_subagents request emitter returned
        (``{"fanout_request": [...], "mode": ...}``), shapes one worker request per
        task, and funnels them through the SINGLE kernel ``run_fanout`` spawn path —
        the SAME path the declarative ``fanout_batch`` strategy reaches (so both entry
        points funnel through one spawn path, FANOUT-02). Re-yields run_fanout's
        lifecycle events. A malformed/empty request is a no-op (the agent already saw
        the tool's JSON result; a bad payload must not abort the run — INV-3 parity).
        """
        runner = getattr(ectx, "runner", None)
        step = getattr(ectx, "current_step", None)
        if runner is None or step is None:
            return
        # WR-01 / T-11-01-01: the FULFILMENT point enforces the grant. The factory
        # binds the tool purely off AGENT.md spec.tools (grant-driven binding is a
        # later enforcement point), so an agent whose AGENT.md declares the tool
        # set could emit a request the step never granted. The compiled effective
        # ``step.tools.spawn_subagents`` is the engine-side ceiling — an ungranted
        # request is logged and IGNORED (no spawn).
        if not bool(getattr(getattr(step, "tools", None), "spawn_subagents", False)):
            logger.warning(
                "spawn_subagents tool result on step %r without an effective "
                "tools.spawn_subagents grant — request ignored (T-11-01-01)",
                getattr(step, "agent_id", None),
            )
            return
        raw = event.get("result", "")
        try:
            payload = json.loads(raw) if isinstance(raw, str) else (raw or {})
        except (ValueError, TypeError):
            logger.warning("spawn_subagents: unparseable fanout request — skipping")
            return
        if not isinstance(payload, dict):
            return
        tasks = payload.get("fanout_request") or []
        if not tasks:
            return
        # Shape one request per task — the kernel run_fanout owns worker selection +
        # concurrency (INV-5).
        requests = [{"agent": "self", "input": t} for t in tasks]
        # WR-07: honor the tool's requested mode. The request's ``mode`` is threaded
        # onto a COPY of the step view (never mutating the shared compiled step) so
        # run_fanout reads it off ``step.fanout.mode`` — a model asking for
        # sequential execution actually gets it (concurrency stays clamped by the
        # engine cap regardless). An invalid/absent mode keeps the declared step.
        fo_step = step
        mode = payload.get("mode")
        if mode in ("parallel", "sequential"):
            import copy as _copy
            from types import SimpleNamespace as _SN

            try:
                fo_step = _copy.copy(step)
                existing = getattr(step, "fanout", None)
                if existing is not None:
                    new_fanout = _copy.copy(existing)
                else:
                    new_fanout = _SN(mode=None, max_parallel=None, agent=None,
                                     count=None, workers=[], merge_agent=None)
                new_fanout.mode = mode
                fo_step.fanout = new_fanout
            except Exception:  # noqa: BLE001 — a non-copyable step degrades to declared mode
                fo_step = step
        async for fo_ev in runner.run_fanout(requests, ectx, step=fo_step):
            yield fo_ev

    @staticmethod
    def _isolated_run_sandbox(ectx):
        """The per-worker isolated sandbox override for THIS invocation (CR-02 / FANOUT-05).

        A fan-out worker step view (built by ``KernelServices.run_worker``) carries
        the engine-allocated ``isolated_workspace``; its RunSandbox-shaped
        ``_sandbox`` (the ``_ChildSandbox`` rooted at the sub_sandbox/worktree dir)
        overrides the shared per-run sandbox so the worker's deepagents disk writes
        land ISOLATED — two parallel workers writing the same relpath cannot
        cross-contaminate before the merge (T-11-02-02). Returns ``None`` for every
        non-worker invocation, keeping the shared per-run sandbox byte-identical
        (INV-3 parity — the override is dormant outside fan-out workers).
        """
        step = getattr(ectx, "current_step", None)
        iso_ws = getattr(step, "isolated_workspace", None) if step is not None else None
        if iso_ws is None:
            return None
        return getattr(iso_ws, "_sandbox", None)

    @staticmethod
    def _record_failed_invocation(ectx, agent_id: str) -> None:
        """ISS-028: record an UNRECOVERED ``(agent_id, task_number, visit_count)`` failure
        triple.

        Called at every ``_run_agent`` ``agent_error`` emission so the terminal
        degraded decision (``_execute_impl``) can key on the per-invocation triple
        rather than collapsing on ``agent_id`` alone. ``task_number`` is read from the
        per-task build scratch (``ectx.build_task_number`` — set by
        ``KernelServices.run_agent`` for a task_loop invocation, "" for a single_shot
        agent). A later successful task of the SAME agent_id appends a result under a
        DIFFERENT pair, so it no longer masks this failure (the ISS-028 root cause).
        A timeout that emits a recoverable ``agent_error`` then completes in the SAME
        invocation records + completes the SAME pair, so it still subtracts cleanly
        (WR-05 preserved). ``visit_count`` (R-08) additionally distinguishes a step
        re-entered via a route loop-back: without it, a pass-1 hard failure is masked
        by a pass-2 completion of the SAME (agent_id, task_number) pair. Best-effort:
        never abort the run on a bookkeeping miss.
        """
        try:
            ectx.failed_invocations.add((
                agent_id,
                getattr(ectx, "build_task_number", "") or "",
                ectx.step_visit_counts.get(agent_id, 0),
            ))
        except Exception:  # noqa: BLE001 — failure bookkeeping must never break the run
            pass

    def _build_roster(self, ectx: ExecutionContext, topic: str, sandbox: RunSandbox) -> str:
        """Build the parent's roster block from artifacts that ACTUALLY exist (R-15, D-05).

        Reads the about-to-run step's ``depends_on`` (``ectx.current_step``) — the
        compiler wires every direct child's ``agent_id`` there for a ``subagents``
        group (T12/T13) — and, for each ``custom-agent:<instance_id>`` dependency,
        resolves its ``display_name`` off the full step lookup (``ectx.steps_by_agent``,
        stamped once per run) and its filename via the SAME ``artifact_name`` helper
        the preamble uses (F-06). A dependency's line is included ONLY when its file
        exists in the sandbox — a failed child never reaches T16's artifact guarantee
        (that check runs after a SUCCESSFUL step completes), so its artifact is
        naturally absent and its line is simply absent (R-21) — no separate
        success/failure bookkeeping, no manifest lookup.

        Never raises — a lookup/read failure degrades to "no roster" (fail-open,
        mirroring RunLog's contract), never breaks the run.
        """
        try:
            step = getattr(ectx, "current_step", None)
            deps = list(getattr(step, "depends_on", None) or [])
            if not deps:
                return ""
            steps_by_agent = getattr(ectx, "steps_by_agent", None) or {}
            lines: list[str] = []
            for dep_id in deps:
                if not isinstance(dep_id, str) or not dep_id.startswith(CUSTOM_AGENT_PREFIX):
                    continue
                instance_id = dep_id.split(":", 1)[1]
                dep_step = steps_by_agent.get(dep_id)
                display = (getattr(dep_step, "display_name", "") or "") or instance_id
                filename = artifact_name(instance_id, topic)
                if sandbox.read(filename) is not None:
                    lines.append(f"- {display} → {filename}")
            if not lines:
                return ""
            return (
                # Not "sub-agents": depends_on is now derived for sequential steps too, whose
                # dependencies are peers, not children.
                "Earlier steps produced:\n"
                + "\n".join(lines)
                + "\nRead the files you need before you start."
            )
        except Exception as exc:  # noqa: BLE001 — roster build must never break the run
            logger.warning("_build_roster: failed to build roster (%s) — omitting it", exc)
            return ""

    @staticmethod
    def _concurrent_skill_scope(ectx: ExecutionContext) -> list[str]:
        """Skill ids of every step dispatched CONCURRENTLY with the current one (ADR-0006).

        A ``subagents: {mode: parallel}`` group compiles its children with a shared
        ``dispatched_by`` (the parent's agent id) and the parent hands them all to
        ``run_fanout``, which runs them under one ``asyncio.gather`` against the SAME
        ``RunSandbox`` whenever the run grants no exec workspace (the ``shared_read``
        isolation path). Staging prunes every skill dir not attached to the calling
        step, so without this the siblings delete each other's skills mid-run —
        silently, since the prune is ``ignore_errors=True``.

        Returns the UNION of the cohort's declared skill ids, which ``stage_skills``
        uses as its KEEP set. ``[]`` for a serially-dispatched step (no
        ``dispatched_by``) ⇒ the KEEP set stays that step's own attached ids ⇒
        byte-identical to the pre-fix behaviour for every existing workflow.

        Deliberately keyed on ``dispatched_by`` rather than on the calling step's
        identity: every member of a cohort shares that value, so this returns the
        same union no matter which sibling asks. Never raises — an unreadable plan
        degrades to ``[]`` (the old, narrower KEEP set), never breaks the run.
        """
        try:
            step = getattr(ectx, "current_step", None)
            cohort = getattr(step, "dispatched_by", "") or ""
            if not cohort:
                return []
            steps_by_agent = getattr(ectx, "steps_by_agent", None) or {}
            scope: set[str] = set()
            for sibling in steps_by_agent.values():
                if (getattr(sibling, "dispatched_by", "") or "") == cohort:
                    scope.update(getattr(sibling, "skills", None) or [])
            return sorted(scope)
        except Exception as exc:  # noqa: BLE001 — scope build must never break the run
            logger.warning(
                "_concurrent_skill_scope: failed (%s) — falling back to per-step prune",
                exc,
            )
            return []

    @staticmethod
    def _deliverable_filename_override(
        ectx: ExecutionContext, index: int, ordered_agents: list
    ) -> str | None:
        """The declared ``single_file`` deliverable name, for every LEAF step.

        One definition, two consumers: the ``AgentContext`` the factory composes the
        prompt from, and the artifact guarantee below. They MUST agree — when they
        disagreed, the prompt told the model to write ``page.html`` while the
        guarantee looked for (and wrote) ``page-<topic>.md``, producing a duplicate
        file on every successful run and, had the model skipped ``write_file``,
        silently writing the deliverable to a name the single_file readback never
        looks at.
        """
        step = getattr(ectx, "current_step", None)
        if not getattr(step, "is_leaf", False):
            return None
        deliverable = getattr(ectx, "deliverable", None)
        if getattr(deliverable, "strategy", None) != "single_file":
            return None
        return getattr(deliverable, "name", None) or None

    def _check_artifact_fallback(
        self,
        ectx: ExecutionContext,
        spec_id: str,
        output: str,
        sandbox: RunSandbox,
        user_message: str,
        deliverable_filename: str | None = None,
    ) -> str | None:
        """The artifact guarantee for a custom-agent step (R-20, D-06, F-06).

        The preamble TELLS a custom-agent step the exact filename to write to
        (factory.py, T11) — but an instruction is not a guarantee, and the engine is
        model-agnostic by decision (Q15): it cannot assume any model obeys it. This
        verifies the file actually landed in the run sandbox and, if not, writes the
        step's streamed ``output`` there itself — making R-20 true regardless of
        model, and structurally killing the spec 011 D-02 defect (an agent that
        streams instead of writing yielding a silently empty deliverable).

        A no-op (returns ``None``) for every non-custom-agent step (R-16 parity) and
        for a custom-agent step whose file already exists. Returns the filename ONLY
        when it just wrote the fallback, so the caller can log/emit
        ``artifact_fallback`` exactly once. Never raises — a guarantee that can crash
        the run is not a guarantee either.
        """
        if not spec_id.startswith(CUSTOM_AGENT_PREFIX):
            return None
        try:
            instance_id = spec_id.split(":", 1)[1]
            topic = getattr(ectx, "topic", "") or topic_slug(user_message)
            # Must match what the factory told the model to write (factory.py:559),
            # or the guarantee checks the wrong file.
            filename = deliverable_filename or artifact_name(instance_id, topic)
            if sandbox.read(filename) is not None:
                return None
            sandbox.write(filename, output or "")
            return filename
        except Exception as exc:  # noqa: BLE001 — the guarantee must never break the run
            logger.warning(
                "artifact_fallback: could not guarantee an artifact for %s: %s",
                spec_id, exc,
            )
            return None

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
        *,
        invocation_gated: bool = True,
    ) -> AsyncGenerator[dict, None]:
        """Run a single domain agent, yielding WS events.

        ``ectx`` is the per-run ExecutionContext (D-03 explicit thread): the engine
        reads od_context / owner / completed-tasks / checkpointer from it instead of
        ``self`` (the kernel holds no per-run state — CTX-02).

        ``invocation_gated`` (ISS-097) is the invocation-scope half of the inline
        review-gate decision — see ``_should_gate``. It reaches all three inline gate
        sites below (restart re-entry, revision re-open, live post-stream) so a
        non-step invocation can never open one. Default ``True`` ⇒ dormant.
        """
        # Guard: if the run is already in a terminal state (e.g. user rejected
        # a review gate), stop immediately without running the agent.
        current_state = self._state_machine.get_state(pipeline_run_id)
        if current_state in ("cancelled", "failed", "diverted"):
            logger.info(
                "_run_agent: skipping %s — pipeline already in terminal state=%s",
                spec.id, current_state,
            )
            return

        # ── REDO-GATE redo loop (F2): unbounded human-paced redos are a FLAT
        # while-loop, NOT recursion — N redos = N iterations, O(1) stack, O(1) per
        # event. The loop body is the EXISTING single run + inline gate; only the
        # loop framing + the _gate_redo branch are new. The redo directive, the
        # derived_from lineage and the prior artifact are LOOP LOCALS (consume-once,
        # F3): captured per iteration and reset BEFORE the model call, so an
        # empty-output / errored / non-redo exit can never leak lineage, a REVISE
        # block or a prior-artifact block onto the next agent.
        redo_directive = ""          # extra instructions for the NEXT re-run
        redo_derived_from = None     # rejected ref id the re-run supersedes
        redo_prior_artifact = ""     # ISS-086: the rejected CONTENT the re-run amends
        redo_attempt = 0             # 0 = first run; N>0 = Nth redo → fresh checkpoint thread
        spec_revision_attempt = 0   # KAN-101: 0 = first run; N>0 = Nth spec revision cycle
        while True:
            agent_start = time.time()

            # ── RESUME-17 gate re-entry (49-02): a restart-parked review gate ─────────
            # re-opens AT its gate phase with ZERO model call — cloning the
            # ``pending_revision_output`` short-circuit below. The sentinel (armed in the
            # ``_is_resume`` block) fires ONCE for the gated step: reconstruct ``output``
            # from the persisted max-version ref (F5) + re-seed ``ectx.last_streamed``
            # (WR-02) so the gate reviews the REAL output, seed the redo / spec-revision
            # attempt counters FAIL-SAFE HIGH from durable evidence (T-49-02-01 — the P23
            # ``:redo{N}`` replay class: over-estimating is a fresh unused thread id,
            # under-estimating collides), then fall into the IDENTICAL five-action consumer.
            # Consume-once + guarded on ``spec.id`` ⇒ dormant on every normal/scripted run
            # (the sentinel is unset → this whole block is skipped, INV-3).
            _gate_reentry = getattr(ectx, "gate_reentry", None)
            if _gate_reentry is not None and _gate_reentry.get("agent_id") == spec.id:
                ectx.gate_reentry = None  # consume-once
                output = self._latest_typed_content(ectx, spec.id) or ""
                ectx.last_streamed = output  # WR-02: the gate reviews the real output
                if results and results[-1].get("agent_id") == spec.id:
                    results[-1] = {**results[-1], "output": output}
                else:
                    results.append({"agent_id": spec.id, "output": output})
                # Seed the redo / spec-revision loop locals from durable evidence so a
                # post-restart redo / update_specs never reuses a pre-restart thread id.
                redo_attempt, spec_revision_attempt = (
                    await self._seed_gate_reentry_attempts(ectx, spec)
                )
                if self._should_gate(spec, ectx, invocation_gated=invocation_gated):
                    # Re-open the gate directly — skip the model call entirely. The five-
                    # branch consumer below is the SAME logic as the post-stream inline
                    # gate (:3842-3999) so ALL FIVE actions behave IDENTICALLY to a live
                    # gate: reject cancels, edit dual-writes with derived_from lineage,
                    # redo threads a fresh :redo{N}, update_specs FIRES the Phase-27
                    # sub-pipeline (SC-3). Deviation from the plan's "clone the
                    # pending_revision_output path" note: that path's update_specs branch
                    # only re-seeds + breaks (it does NOT run the sub-pipeline — it IS the
                    # re-open-after-sub-pipeline stage), so cloning it would NEVER fire the
                    # sub-pipeline from a re-entered gate. The success criterion "update_specs
                    # sub-pipeline fires" requires the post-stream consumer.
                    _ek = self._artifact_kind_for(spec)
                    # ISS-052: name WHICH firing this is. The analyze gate opened inside a
                    # revision pass and the one re-opened after it returns share a gate_key
                    # AND their output bytes, so without this the user (and any consumer
                    # keyed on those two) cannot tell them apart.
                    _rev_cycle, _rev_in_flight = self._stamp_revision_marks(ectx)
                    # R-08: fold the loop-revisit count into gate_key so a step re-entered
                    # via a route loop-back doesn't collide with its own prior firing.
                    _visit_count = ectx.step_visit_counts.get(spec.id, 0)
                    async for gate_event in self._run_review_gate(
                        pipeline_run_id=pipeline_run_id,
                        agent_id=spec.id,
                        agent_name=spec.name,
                        output=output,
                        redoable=True,
                        update_specs_eligible=self._update_specs_eligible(_ek, ectx),
                        artifact_kind=_ek,
                        revision_cycle=_rev_cycle,
                        revision_in_flight=_rev_in_flight,
                        cancel_event=cancel_event,
                        visit_count=_visit_count,
                    ):
                        if gate_event.get("type") == "_gate_rejected":
                            current = self._state_machine.get_state(pipeline_run_id)
                            if current not in ("cancelled", "failed", "diverted"):
                                self._state_machine.transition(pipeline_run_id, "cancelled")
                            yield {"type": "pipeline_cancelled", "data": {
                                "pipeline_run_id": pipeline_run_id,
                                "reason": f"User rejected output from {spec.name}",
                            }}
                            return
                        elif gate_event.get("type") == "_gate_edited":
                            edited = gate_event.get("edited_content", output)
                            if edited:
                                _ek = self._artifact_kind_for(spec)
                                _ek_html_loc = getattr(getattr(ectx, "deliverable", None), "name", None) or "prototype.html"
                                # RESUME-15: stamp lineage to the version this edit
                                # supersedes (resolved BEFORE the write == prior max).
                                _prior_ref = self._latest_typed_ref_id(ectx, spec.id, _ek)
                                await self._dual_write_artifact(
                                    ectx,
                                    producer_agent=spec.id,
                                    producer_step=spec.id,
                                    content=edited,
                                    kind=_ek,
                                    location=(
                                        _ek_html_loc
                                        if _ek == "html_file"
                                        else f"artifact_refs/{spec.id}"
                                    ),
                                    derived_from=_prior_ref,
                                )
                            if results:
                                results[-1] = {**results[-1], "output": edited}
                        elif gate_event.get("type") == "_gate_redo":
                            # RESUME-17 gate re-entry: identical to the live consumer, via
                            # the ONE shared helper (INV-12).
                            (redo_directive, redo_derived_from,
                             redo_prior_artifact) = await self._consume_redo(
                                gate_event=gate_event, spec=spec,
                                results=results, ectx=ectx,
                            )
                            redo_attempt += 1
                            break
                        elif gate_event.get("type") == "_gate_update_specs":
                            # RESUME-17 gate re-entry: identical to the live consumer, via
                            # the ONE shared helper (INV-12). spec_revision_attempt was
                            # seeded FAIL-SAFE HIGH from the durable gate_events above.
                            spec_revision_attempt += 1
                            _us_cancelled = False
                            async for _us_event in self._consume_update_specs(
                                gate_event=gate_event, spec=spec, index=index,
                                ordered_agents=ordered_agents, user_message=user_message,
                                sandbox=sandbox, pipeline_run_id=pipeline_run_id,
                                pipeline_type=pipeline_type, planning_context=planning_context,
                                attached_skills=attached_skills, attached_hooks=attached_hooks,
                                model_id=model_id, results=results, cancel_event=cancel_event,
                                ectx=ectx, revision_index=spec_revision_attempt,
                            ):
                                if _us_event.get("type") == "_update_specs_done":
                                    _us_cancelled = bool(_us_event.get("cancelled"))
                                else:
                                    yield _us_event
                            if _us_cancelled:
                                return
                            break
                        else:
                            yield gate_event
                    else:
                        return
                    continue
                # Durably-open gate, but the current selection says this step should
                # not gate: continue with the recorded output and drop any pending gate
                # response. Migration 0031 fixed the known cause (per-run gate_agent_ids
                # lost on resume, discarding redo instructions silently); the warning
                # keeps any remaining path visible instead of looking like an approval.
                logger.warning(
                    "gate_reentry: %s has a durably-open gate but does not gate under "
                    "the current selection — continuing with its recorded output; any "
                    "pending gate response for this step is discarded",
                    spec.id,
                )
                return

            # KAN-101: if a spec revision sub-pipeline just completed, skip re-running
            # THIS agent (the analyzer) and jump straight to re-opening the gate with
            # the new analysis output from the sub-pipeline. The pending output is
            # stored on ectx scratch (cleared here so it's consume-once). This avoids
            # a full model re-run for the gate-owner agent when the real new output
            # came from the sub-pipeline. Keyed on generic ectx field (SC-001/INV-1).
            pending_revision_output = getattr(ectx, "spec_revision_pending_output", None)
            if pending_revision_output is not None:
                ectx.spec_revision_pending_output = None  # consume-once
                # Update `output` with the sub-pipeline's new analysis text so the
                # gate re-opens with the correct content. Also update results.
                output = pending_revision_output  # noqa: F821 — set below on first run
                if results and results[-1].get("agent_id") == spec.id:
                    results[-1] = {**results[-1], "output": output}
                # Re-open the gate directly — skip the model call entirely.
                if self._should_gate(spec, ectx, invocation_gated=invocation_gated):
                    # SC-001: derive the update-specs eligibility STRUCTURALLY from the
                    # artifact-kind (name-free), mirroring redoable's inline True.
                    _ek = self._artifact_kind_for(spec)
                    # ISS-052: name WHICH firing this is. The analyze gate opened inside a
                    # revision pass and the one re-opened after it returns share a gate_key
                    # AND their output bytes, so without this the user (and any consumer
                    # keyed on those two) cannot tell them apart.
                    _rev_cycle, _rev_in_flight = self._stamp_revision_marks(ectx)
                    # R-08: fold the loop-revisit count into gate_key so a step re-entered
                    # via a route loop-back doesn't collide with its own prior firing.
                    _visit_count = ectx.step_visit_counts.get(spec.id, 0)
                    async for gate_event in self._run_review_gate(
                        pipeline_run_id=pipeline_run_id,
                        agent_id=spec.id,
                        agent_name=spec.name,
                        output=output,
                        redoable=True,
                        update_specs_eligible=self._update_specs_eligible(_ek, ectx),
                        artifact_kind=_ek,
                        revision_cycle=_rev_cycle,
                        revision_in_flight=_rev_in_flight,
                        cancel_event=cancel_event,
                        visit_count=_visit_count,
                    ):
                        if gate_event.get("type") == "_gate_rejected":
                            current = self._state_machine.get_state(pipeline_run_id)
                            if current not in ("cancelled", "failed", "diverted"):
                                self._state_machine.transition(pipeline_run_id, "cancelled")
                            yield {"type": "pipeline_cancelled", "data": {
                                "pipeline_run_id": pipeline_run_id,
                                "reason": f"User rejected output from {spec.name}",
                            }}
                            return
                        elif gate_event.get("type") == "_gate_edited":
                            edited = gate_event.get("edited_content", output)
                            if edited:
                                _ek = self._artifact_kind_for(spec)
                                # RESUME-15: stamp lineage to the version this edit
                                # supersedes (resolved BEFORE the write == prior max).
                                # None on a first-ever write ⇒ byte-identical (INV-3).
                                _prior_ref = self._latest_typed_ref_id(ectx, spec.id, _ek)
                                await self._dual_write_artifact(
                                    ectx,
                                    producer_agent=spec.id,
                                    producer_step=spec.id,
                                    content=edited,
                                    kind=_ek,
                                    location=f"artifact_refs/{spec.id}",
                                    derived_from=_prior_ref,
                                )
                            if results and results[-1].get("agent_id") == spec.id:
                                results[-1] = {**results[-1], "output": edited}
                        elif gate_event.get("type") == "_gate_redo":
                            # ── ISS-086 ──────────────────────────────────────────────
                            # This branch was a THIN COPY: it set the directive and
                            # nothing else, so a redo at the gate re-opened after a
                            # revision pass lost its ``derived_from`` lineage, left a
                            # DUPLICATE ``results`` entry (the re-run appends, and only
                            # this branch never popped) and wrote no audit row — which
                            # also under-seeded ``_seed_gate_reentry_attempts``, risking a
                            # colliding ``:redo{N}`` after a restart. Driving the ONE
                            # shared consumer closes all three for free (INV-12).
                            (redo_directive, redo_derived_from,
                             redo_prior_artifact) = await self._consume_redo(
                                gate_event=gate_event, spec=spec,
                                results=results, ectx=ectx,
                            )
                            redo_attempt += 1
                            break
                        elif gate_event.get("type") == "_gate_update_specs":
                            # ── DEFECT B FIX (quick-260811-si4) ──────────────────────
                            # This branch previously ONLY re-seeded
                            # ``spec_revision_pending_output`` and broke. No sub-pipeline
                            # call, no audit row, no log. So a SECOND "Update the Specs"
                            # — at the gate the engine re-opens after a revision cycle —
                            # closed the gate, instantly re-opened it on the IDENTICAL
                            # content (the FE sends the analyzer's own output as the
                            # report, InlineGateActions.tsx:163), ran nothing, and the
                            # build then proceeded from the unrevised spec. A silent
                            # no-op, invisible on screen, one wasted build.
                            #
                            # Driving the shared consumer here is a SIBLING call, NOT
                            # recursion: _run_spec_revision_sub_pipeline's ``finally``
                            # precedes its terminal ``_revision_analyze_output`` yield,
                            # and the driving ``async for`` runs the generator to
                            # exhaustion before breaking — so by the time control reaches
                            # this re-opened gate the previous pass is fully unwound and
                            # this call sits at the SAME stack depth as the live
                            # consumer's. A flat cycle, the REDO-GATE F2 precedent
                            # (asserted by test_reopened_gate_cycle_keeps_a_flat_stack).
                            # The enclosing ``spec_revision_attempt`` local increments
                            # across siblings, so cycle 2 naturally threads ``:rev2``.
                            spec_revision_attempt += 1
                            _us_cancelled = False
                            async for _us_event in self._consume_update_specs(
                                gate_event=gate_event, spec=spec, index=index,
                                ordered_agents=ordered_agents, user_message=user_message,
                                sandbox=sandbox, pipeline_run_id=pipeline_run_id,
                                pipeline_type=pipeline_type, planning_context=planning_context,
                                attached_skills=attached_skills, attached_hooks=attached_hooks,
                                model_id=model_id, results=results, cancel_event=cancel_event,
                                ectx=ectx, revision_index=spec_revision_attempt,
                            ):
                                if _us_event.get("type") == "_update_specs_done":
                                    _us_cancelled = bool(_us_event.get("cancelled"))
                                else:
                                    yield _us_event
                            if _us_cancelled:
                                return
                            break
                        else:
                            yield gate_event
                    else:
                        return
                    continue
                return

            yield {
                "type": "agent_start",
                # ``visit_count`` (R-08) is emitted ONLY when non-zero: a first dispatch
                # omits the key entirely, so every non-looping workflow yields a
                # byte-identical event and the 5 characterization goldens — which pin
                # agent_start's exact key set — stay valid with no regeneration. It
                # appears only on a RE-dispatch, which is the only time it carries
                # information. Without it two passes of the same step are
                # indistinguishable on the wire and a loop is invisible in the UI.
                "data": {"agent_id": spec.id, "name": spec.name, "role": spec.role,
                         "icon": spec.icon, "index": index, "total": len(ordered_agents),
                         **({"visit_count": _vc}
                            if (_vc := ectx.step_visit_counts.get(spec.id, 0)) else {})},
            }
            _log_event("agent_start", pipeline_run_id, agent_id=spec.id)
            RunLog(getattr(sandbox, "root", None)).write("step_start", agent_id=spec.id)

            # Build context message via the GENERIC injector (INV-1) — OD/template blocks
            # come from the declared context_provider capabilities, the agnostic parts
            # (brief + planning + consumed outputs + CURRENT TASK) are composed inline.
            # The former L12 per-pipeline injection branches were deleted from the kernel
            # in 07-05; the generic injector is the sole context-composition path.
            # ── REDO-GATE consume-once (F3) ──────────────────────────────────────────
            # Publish the redo directive to ectx ONLY around this compose call, then
            # clear it UNCONDITIONALLY right after — so an empty-output / errored /
            # non-redo path can never carry a REVISE block onto the next agent. The
            # derived_from lineage never touches ectx (it stays a loop local), and all
            # three locals are reset to empty here so a NON-redo exit cannot leak any.
            #
            # ── ISS-086: the re-run's SUBJECT rides the same seam ────────────────────
            # "Request changes" asks the agent to AMEND, and an amendment needs the
            # document. It is published on FIX-217's existing consume-once field and
            # rendered by that field's existing block — one field, one renderer, two
            # publishers (INV-12), not a parallel seam. SAVE/RESTORE rather than clear
            # (the quick-260811-si4 defect-A shape): a redo can fire at a gate opened
            # INSIDE a revision pass, and zeroing the field there would strip the outer
            # pass's own subject mid-flight. At the outer level the saved value is "" so
            # this is byte-equivalent to a clear, and the whole block is dormant on every
            # non-redo dispatch (INV-3).
            #
            # The ``finally`` covers the one path that is NOT inside _run_agent's own
            # try/except: ``_compose_context_message`` itself raising (it reads template /
            # design-system files, so a missing one propagates). Without it a compose-time
            # failure would strand BOTH published fields on the shared per-run ectx.
            # On the success path this is byte-identical to the previous straight-line
            # clear — the same two assignments, in the same order (INV-3).
            _saved_prior_artifact = ectx.spec_revision_prior_artifact
            ectx.redo_directive = redo_directive
            if redo_prior_artifact:
                ectx.spec_revision_prior_artifact = redo_prior_artifact
            try:
                context_message = await self._compose_context_message(
                    spec, index, ordered_agents, user_message,
                    planning_context, ectx,
                )
            finally:
                ectx.redo_directive = ""
                ectx.spec_revision_prior_artifact = _saved_prior_artifact
            _iter_derived = redo_derived_from   # lineage for THIS iteration's write
            redo_directive = ""
            redo_derived_from = None
            redo_prior_artifact = ""

            # UPLD-02 residue (30-03): drain any per-turn images queued by the chat
            # ``POST /api/runs/{id}/messages`` path (via chat_router.apply_turn_images →
            # ectx.pending_turn_images) onto the ONE-SHOT ``turn_images_once`` carrier
            # BEFORE composing THIS dispatch's blocks. Consume-once (HI-01):
            # _compose_input_blocks renders turn_images_once into exactly THIS dispatch
            # and clears it, so a per-turn image reaches ONE dispatch and never
            # re-delivers — DISTINCT from the sticky run-entry ``run_images`` (which the
            # run_images provider re-renders every dispatch). DORMANT by default — an
            # empty queue drains nothing ⇒ the dispatch payload + the 5 goldens stay
            # byte-identical (INV-3). Payload-transient (ND-10): the images are never
            # persisted (the durable chat_message row keeps retained:false refs, no
            # bytes). Keyed on the generic queue only (SC-001).
            _drain_turn_images(ectx)

            # image-input Wave 1: the per-agent LOCAL image content-blocks (NOT an ectx
            # field — a shared field would leak the F1 blocks to a later non-opted agent).
            # Locally gated on spec.injects ∪ step.injects inside _compose_input_blocks;
            # [] for every agent this wave (no injects:[images] declared) ⇒ dormant.
            input_blocks = await self._compose_input_blocks(spec, ectx)

            # Emit agent_input event (Phase 3 / T040) — shows full input prompt
            # and context sources in the Thinking tab (FR-015).
            context_sources = self._build_context_sources(
                spec, ordered_agents, ectx,
                agent_index=index,
                user_message=user_message,
            )
            # context_message stays a TEXT str ALWAYS in the agent_input event (split-
            # transport, Locked Decision #3): only the model dispatch wraps the blocks.
            _agent_input_data = {
                "agent_id": spec.id,
                "pipeline_run_id": pipeline_run_id,
                "timestamp": _now(),
                "context_message": context_message,
                "context_sources": context_sources,
                "tool_calls": [],
            }
            # image_count: optional observability key, emitted ONLY when images ride this
            # dispatch (>0). A text-only run emits NO image_count key ⇒ dormant goldens
            # byte-identical. Stripped from the characterization multiset belt-and-suspenders.
            if input_blocks:
                _agent_input_data["image_count"] = len(input_blocks)
            yield {
                "type": "agent_input",
                "data": _agent_input_data,
            }

            try:
                # spec 011 / D6: run-attached skills are STAGED to <sandbox>/skills/ by
                # create_runner and advertised by deepagents — their bodies never enter a
                # prompt. The per-user DISK skill keeps its eager injection and therefore
                # rides its OWN context field instead of being merged in here.
                merged_skills: list[dict] = list(attached_skills or [])
                disk_skill: str | None = ectx.disk_skills.get(spec.id)

                # Every attached skill reaches every agent (spec 011 R-01) — there is no
                # per-agent scoping left to apply, so the displayed set IS the attached set.
                displayed_skills = merged_skills

                ctx = AgentContext(
                    user_request=user_message,
                    agent_outputs=self._filter_consumed_outputs(spec, ordered_agents, ectx),
                    attached_skills=merged_skills,
                    disk_skill=disk_skill,
                    attached_hooks=list(attached_hooks or []),
                    # MODEL-01/02/05: the effective model id by the D-02 precedence. With no
                    # overrides + no manifest model this returns ``model_id or Haiku`` = the
                    # prior value — INV-3 parity. ``ectx.current_step`` is the SAME compiled
                    # Step already read a few lines below for injects/skills/prompt/tools —
                    # wiring it here lets tier 2 (``step.model``, the ``selections`` overlay
                    # from ``_apply_selections``) actually win instead of always resolving
                    # None (ISS-164).
                    model=self._resolve_model(ectx, spec, model_id, step=ectx.current_step),
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
                    # prewarmed_constitution (AGENTRT-06 / F4 / R12): the owner's Constitution,
                    # awaited ONCE at run entry, so the SYNC factory injects a DB-stored
                    # Constitution under this running event loop WITHOUT awaiting (the R12
                    # no-op fix). None when none is set → graceful no-op (parity).
                    prewarmed_constitution=ectx.prewarmed_constitution,
                    # prewarmed_mcp_tools (09-05 / MCP-01): the MCP/integration tools bound
                    # ONCE at run entry (above) so the SYNC factory unions them into the runner
                    # tool set under this running loop WITHOUT awaiting. Empty when no MCP
                    # scope is active → graceful no-op (parity; snapshots byte-identical).
                    prewarmed_mcp_tools=list(getattr(ectx, "prewarmed_mcp_tools", None) or []),
                    # step_injects (WIRE-03 / D-16): the compiled Step.injects for THIS step,
                    # read GENERICALLY off ectx.current_step (the compiled Step bound by the
                    # strategy handle before this call — the SAME seam current_step.hooks uses,
                    # NOT a spec.id/pipeline_type branch, SC-001). The factory merges it with
                    # spec.injects (AGENT.md). [] for every step declaring no per-step injects:
                    # (all 5 goldens) → the merge is a no-op → byte-identical (INV-3).
                    step_injects=list(
                        getattr(getattr(ectx, "current_step", None), "injects", None) or []
                    ),
                    # step_skills (spec 012 / R-01, D-03): the compiled Step.skills for
                    # THIS step, read off ectx.current_step (the SAME seam step_injects
                    # uses). [] for every step declaring no per-step skills: the factory
                    # falls back to ctx.attached_skills unchanged, so behaviour stays
                    # byte-identical (R-16) for the goldens, which declare no skills.
                    step_skills=list(
                        getattr(getattr(ectx, "current_step", None), "skills", None) or []
                    ),
                    # skills_prune_scope (ADR-0006 Consequences): the union of the
                    # concurrently-dispatched cohort's skill ids, so a sibling running
                    # under the same asyncio.gather against the shared sandbox does not
                    # get its staged skill pruned away. [] for every serial step ⇒ the
                    # factory passes an empty scope ⇒ stage_skills keeps its per-step
                    # KEEP set ⇒ byte-identical for the goldens (R-16).
                    skills_prune_scope=self._concurrent_skill_scope(ectx),
                    # step_prompt (spec 012 / R-14, T11/T16): a custom-agent step's own
                    # ``prompt`` text, read off ectx.current_step (the SAME seam
                    # step_injects/step_skills use). "" for every non-custom-agent step
                    # (they declare no ``prompt`` — R-06), so this is a no-op for every
                    # existing agent (R-16 parity).
                    step_prompt=str(
                        getattr(getattr(ectx, "current_step", None), "prompt", None) or ""
                    ),
                    # topic (spec 012 / R-12, R-14, T11/T16): the run's topic slug,
                    # computed ONCE at run entry (ectx.topic, above) and reused for
                    # every step — never recomputed here (F-06).
                    topic=getattr(ectx, "topic", "") or topic_slug(user_message),
                    # capabilities (spec 012 / R-25, T33/T35): the compiled workflow's
                    # capabilities dict, threaded off ectx.compiled_capabilities (set
                    # once at run entry, above — the SAME seam step_injects/step_skills
                    # use). {} for every manifest declaring none, so this is a no-op
                    # for every existing agent (R-16 parity).
                    capabilities=dict(getattr(ectx, "compiled_capabilities", None) or {}),
                    # step_tools / workflow_name: CARRIED, never decided. The
                    # engine makes no permission decision — the compiled Step's
                    # effective ToolPermissions were resolved by
                    # agents/workflows/permission_caps.py at compile time, and the
                    # engine only hands them to the factory (the SAME pass-through
                    # seam step_injects/step_skills use). None when no step is
                    # bound ⇒ the factory narrows nothing (parity).
                    step_tools=getattr(
                        getattr(ectx, "current_step", None), "tools", None
                    ),
                    workflow_name=pipeline_type,
                    # Only the FINAL step may be named by a single_file deliverable —
                    # its declared name and the per-instance artifact convention are
                    # mutually exclusive, and the readback looks for the declared name.
                    # None elsewhere, so the factory falls back to artifact_name().
                    deliverable_filename_override=self._deliverable_filename_override(
                        ectx, index, ordered_agents,
                    ),
                )
                # Roster block built from the artifacts the dependencies ACTUALLY wrote,
                # never the manifest — a failed step's artifact is absent, so its line is
                # simply absent (R-21). Consumed by factory.py `_compose_system_prompt`.
                ctx.roster = self._build_roster(ectx, ctx.topic, sandbox)

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
                # task on its own thread — the task_loop strategy sets ectx.build_task_number
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
                # REDO-GATE: every redo re-run MUST use a FRESH checkpoint thread, else
                # the checkpointer replays the prior turn and the model "remembers" its
                # rejected output → it acknowledges completion ("it's already done")
                # instead of regenerating (same class as the 06-05 CR-02 throttle-fallback
                # `:retry{n}` fix). The suffix is added ONLY for redo_attempt > 0, so the
                # first (non-redo) run — and every characterization golden — keeps its
                # exact thread_id (INV-3 dormant).
                if redo_attempt:
                    thread_id = f"{thread_id}:redo{redo_attempt}"
                # Same class, same reason for a REVISION re-run: reusing the first pass's
                # thread lets the checkpointer replay that turn, so the model "remembers"
                # the pre-revision document and acknowledges it instead of rewriting it.
                # This also closes a latent case — redo-then-update_specs previously
                # revised the REJECTED draft (redo ran on :redo1, the revision re-ran on
                # the base thread). Dormant when revision_attempt is 0, so every normal
                # run and every characterization golden keeps its exact thread_id (INV-3).
                _rev = getattr(ectx, "revision_attempt", 0) or 0
                if _rev:
                    thread_id = f"{thread_id}:rev{_rev}"
                agent = create_runner(
                    spec.id,
                    ctx,
                    thread_id=thread_id,
                    checkpointer=ectx.checkpointer,
                    # Phase 11 / FANOUT-05 (CR-02): a fan-out worker invocation carries
                    # an engine-allocated ISOLATED workspace on its step view — its
                    # sandbox overrides the shared per-run dir so worker writes land
                    # isolated. None for every non-worker invocation (parity).
                    run_sandbox=self._isolated_run_sandbox(ectx),
                )

                # spec 011 / D6: emitted AFTER create_runner returns (moved from before the
                # call) — before construction this event only reported an INTENTION to
                # attach skills; here it reports what create_runner's stage_skills actually
                # DELIVERED (ctx.skills_delivery), so a silently-dropped/unparseable
                # SKILL.md is surfaced instead of assumed.
                _delivery = getattr(ctx, "skills_delivery", None)
                # Advertise what create_runner actually STAGED, not just what the run
                # attached. ``displayed_skills`` is the run-attached (UI) set and is
                # EMPTY for a manifest-declared per-step skill, which travels the
                # separate ``step_skills`` seam into the factory. The result was a skill
                # that staged to disk and was billed in ``estimated_tokens`` while
                # ``attached_skills`` shipped ``[]`` — so AgentDetailPanel's card, gated
                # on a non-empty array, silently never rendered. ``skills_resolved``
                # is the list the factory handed to ``stage_skills`` and falls back to
                # ``displayed_skills`` when no step skills are declared, so a run with
                # only UI-attached skills emits exactly the payload it did before.
                _advertised = list(getattr(ctx, "skills_resolved", None) or displayed_skills)
                yield {
                    "type": "agent_skills",
                    "data": {
                        "agent_id": spec.id,
                        "attached_skills": [
                            {
                                "name": s.get("name", ""),
                                "source": s.get("source", ""),
                                "content": s.get("content", ""),
                            }
                            for s in _advertised
                        ],
                        "attached_hooks": [
                            {
                                "name": h.get("name", ""),
                                "event": h.get("event", ""),
                                "trigger": h.get("trigger", ""),
                                "description": h.get("description", ""),
                            }
                            for h in (attached_hooks or [])
                        ],
                        "skills_load_errors": list(getattr(_delivery, "errors", []) or []),
                        "estimated_tokens": getattr(_delivery, "est_tokens", 0),
                    },
                }
                # Advisory-only cost ceiling warning — never raises, never skips the agent.
                if getattr(_delivery, "est_tokens", 0) > 8000:
                    logger.warning(
                        "agent=%s advertises %d skill(s) at ~%d tok/agent (ceiling 8000)",
                        spec.id, len(getattr(_delivery, "staged", []) or []), _delivery.est_tokens,
                    )

                output_chunks: list[str] = []

                # ── ISS-004 (19-03): streamed agent_chunk sanitizer (chunk-straddle) ──
                # The buffer is (re)constructed per retry-attempt below (so a fallback
                # re-stream gets a fresh one), keyed on the runner's duck-typed
                # `sanitize_output` — the SAME transform the post-loop authoritative block
                # (~:2645) uses. It is an identity no-op for tool-using agents (and for
                # clean text), so the buffer is inert there and only strips fabricated
                # tool-XML from the YIELDED chunks of a tool-less agent. SC-001: keyed on
                # the generic runner capability, NOT a workflow/agent-name literal. The
                # authoritative `output_chunks` path is unchanged (it still accumulates the
                # RAW chunk) so the post-loop sanitize_output keeps the goldens byte-identical.

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
                # ── ISS-016 (A1): runner ``error``-event capture ────────────────────
                # The runner (deep_agent_runner.py:507-527) swallows every non-throttle
                # exception into ``yield {"type":"error","error":str(exc)}`` and returns.
                # The consume loop below now branches on that event (the ``error`` arm),
                # recording the failure here. The scripted model never raises, so this
                # flag stays False on the characterization goldens (INV-3 dormant arm).
                agent_errored = False
                agent_error_message = ""
                # WR-02 (16 review): the raw runner ``str(exc)`` is kept server-side
                # only (log) — never placed on the client-facing event. See the
                # ``error`` arm + the agent_errored post-loop block below.
                agent_error_raw = ""
                agent_input_tokens = 0
                agent_output_tokens = 0
                # ISS-032: per-agent prompt-cache split (0 under the scripted model).
                agent_cache_read_tokens = 0
                agent_cache_write_tokens = 0

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
                    # ISS-004: a fresh chunk-straddle buffer per attempt so a re-stream
                    # never inherits a held tail from the throttled prior attempt (the FE
                    # discards prior agent_chunk events on agent_model_fallback/reset_output).
                    _chunk_sanitizer = _ChunkStreamSanitizer(getattr(agent, "sanitize_output", None))
                    agent_input_tokens = 0
                    agent_output_tokens = 0
                    # ISS-032: reset the cache split too so a re-streamed attempt
                    # does not inherit the throttled prior attempt's counts.
                    agent_cache_read_tokens = 0
                    agent_cache_write_tokens = 0
                    # task_progress records appended this attempt (so a retry does not double
                    # count the prototype build checklist on re-stream).
                    _attempt_task_count = 0
                    try:
                        async with asyncio.timeout(agent_timeout):
                            # image-input Wave 1: wrap the text with any per-agent image
                            # blocks for the model dispatch ONLY (split-transport). Bare str
                            # when input_blocks empty (dormant) ⇒ byte-identical. Re-sent on
                            # each model-fallback retry inside this while-True (intended).
                            _dispatch = _dispatch_payload(context_message, input_blocks)
                            async for event in agent.astream_events(_dispatch):
                                if cancel_event and cancel_event.is_set():
                                    raise asyncio.CancelledError()
                                etype = event["type"]
                                if etype == "chunk":
                                    # Authoritative path UNCHANGED: accumulate the RAW chunk
                                    # so the post-loop sanitize_output (~:2645) still produces
                                    # the byte-identical golden final_output (INV-3).
                                    output_chunks.append(event["chunk"])
                                    # ISS-004: the YIELDED chunk is routed through the
                                    # chunk-straddle sanitizer (no-op identity for tool-using
                                    # agents / clean text). `feed` returns the safe-to-yield
                                    # prefix, holding an unterminated tool-XML opener until its
                                    # close arrives. Suppress empty deltas (nothing to stream).
                                    _safe_chunk = _chunk_sanitizer.feed(event["chunk"])
                                    if _safe_chunk:
                                        yield {"type": "agent_chunk", "data": {"agent_id": spec.id, "chunk": _safe_chunk}}
                                elif etype == "thinking":
                                    # Live model reasoning (extended-thinking providers) —
                                    # mirrors the "chunk" -> agent_chunk mapping directly
                                    # above. The FE already has a full agent_thinking
                                    # handler + Thinking tab (useWorkflow.ts, AgentThinkingTab)
                                    # waiting on this; only the emission was missing.
                                    yield {"type": "agent_thinking", "data": {"agent_id": spec.id, "thinking": event["thinking"]}}
                                elif etype == "usage":
                                    agent_input_tokens += event.get("input_tokens", 0)
                                    agent_output_tokens += event.get("output_tokens", 0)
                                    # ISS-032: accumulate the per-turn cache split.
                                    agent_cache_read_tokens += event.get("cache_read_tokens", 0) or 0
                                    agent_cache_write_tokens += event.get("cache_write_tokens", 0) or 0
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
                                    # ── Audit: log tool call to hook_runs + live WS (KAN-73) ──
                                    # Best-effort — must never abort the run or the stream.
                                    _tc_tool = event.get("tool", "unknown")
                                    _tc_args = event.get("args", {}) or {}
                                    _tc_detail = {
                                        "agent_id": spec.id,
                                        "agent_name": spec.name,
                                        "event": "tool_call",
                                        "tool": _tc_tool,
                                        "args_summary": ", ".join(
                                            f"{k}={str(v)[:40]}" for k, v in list(_tc_args.items())[:3]
                                        ) if _tc_args else "",
                                        "timestamp": _now(),
                                        "outcome": "continue",
                                        "summary": f"{spec.name} used tool: {_tc_tool}",
                                        "severity": "info",
                                        "hook_type": "tool_call",
                                    }
                                    _runner = getattr(ectx, "runner", None)
                                    if _runner is not None:
                                        try:
                                            await _runner.record_hook_run(
                                                "audit_logger", "tool_call", "continue", _tc_detail
                                            )
                                        except Exception:
                                            pass
                                        try:
                                            _emit_fn = getattr(_runner, "emit_hook_event", None)
                                            if callable(_emit_fn):
                                                _emit_fn(_tc_detail)
                                        except Exception:
                                            pass
                                elif etype == "tool_result":
                                    yield {"type": "tool_result", "data": {"agent_id": spec.id, "tool": event["tool"], "result": str(event.get("result", ""))[:500]}}
                                    # ── Audit: log tool result to hook_runs + live WS (KAN-73) ──
                                    _tr_tool = event.get("tool", "unknown")
                                    _tr_result = str(event.get("result", ""))
                                    _tr_detail = {
                                        "agent_id": spec.id,
                                        "agent_name": spec.name,
                                        "event": "tool_result",
                                        "tool": _tr_tool,
                                        "result_preview": _tr_result[:120] + ("…" if len(_tr_result) > 120 else ""),
                                        "timestamp": _now(),
                                        "outcome": "continue",
                                        "summary": f"{spec.name} tool result: {_tr_tool}",
                                        "severity": "info",
                                        "hook_type": "tool_call",
                                    }
                                    if _runner is not None:
                                        try:
                                            await _runner.record_hook_run(
                                                "audit_logger", "tool_result", "continue", _tr_detail
                                            )
                                        except Exception:
                                            pass
                                        try:
                                            if callable(_emit_fn):
                                                _emit_fn(_tr_detail)
                                        except Exception:
                                            pass
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
                                    # ── Runtime fan-out derivation (Phase 11 / FANOUT-02) ──────
                                    # When the spawn_subagents request emitter returns, derive the
                                    # structured request from its result + fulfil it via the SINGLE
                                    # kernel run_fanout spawn path (the runtime entry point B; the
                                    # declarative entry point A flows through the fanout_batch
                                    # strategy). STRICTLY conditional on the tool name so every
                                    # non-fanout run takes the IDENTICAL path as today (zero new
                                    # events, zero reordering — fanout stays DORMANT, Pitfall 3).
                                    elif event.get("tool") == "spawn_subagents":
                                        async for _fo_ev in self._derive_fanout(event, ectx):
                                            yield _fo_ev
                                elif etype == "error":
                                    # ── ISS-016 (A1): consume the runner's swallowed-error event ──
                                    # The runner (deep_agent_runner.py:507-527) yields
                                    # ``{"type":"error","error":str(exc)}`` for every non-throttle
                                    # fault (e.g. a model-side validation reject) and returns.
                                    # WITHOUT this arm the event was dropped, the stream "ended
                                    # clean" with output="", and an empty agent_complete fired → a
                                    # hard-failed run terminated as a clean pipeline_complete.
                                    # Branch keys on the GENERIC event type only — no provider /
                                    # model / workflow text match (SC-001).
                                    # Record the fault and break out of the stream so the post-loop
                                    # ``agent_errored`` branch emits a recoverable agent_error and
                                    # SKIPS the result-append + agent_complete for this agent.
                                    # WR-02 (16 review): the runner forwards the raw ``str(exc)`` which,
                                    # for a non-throttle Bedrock fault, can carry ARNs / region /
                                    # model-id / internal config. The chat path routes provider errors
                                    # through ``app.agents.llm_errors.map_exception`` to a stable,
                                    # secret-free user message; mirror that here. The engine only holds
                                    # the stringified message (the runner stays as-is, A1), so we keep
                                    # the raw text SERVER-SIDE (the warning log below) and place only a
                                    # bounded, generic, leak-free message on the client-facing event
                                    # (T-16-01-ID: bounded, no stack frames, no secrets). Keyed on the
                                    # generic event type only — no provider/model/workflow match (SC-001).
                                    agent_errored = True
                                    agent_error_raw = str(event.get("error", "") or "")[:500]
                                    agent_error_message = _sanitize_agent_error(agent_error_raw)
                                    break
                        # ISS-004 (19-03): flush any residual held tail through the
                        # chunk-straddle sanitizer at stream end. An unterminated tool-XML
                        # opener still held at EOF is stripped (mirrors the runner's WR-01
                        # _UNTERMINATED_TOOL_XML_RE); a clean held tail flushes verbatim so
                        # legitimate trailing content is never silently swallowed.
                        _flushed_chunk = _chunk_sanitizer.flush()
                        if _flushed_chunk:
                            yield {"type": "agent_chunk", "data": {"agent_id": spec.id, "chunk": _flushed_chunk}}
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
                    # ISS-028: record the (agent_id, task_number) failure pair. The
                    # timeout path RECOVERS — it falls through to results.append below
                    # under the SAME task_number, so this pair is subtracted out by the
                    # terminal degraded decision (WR-05 timeout-recovery preserved). The
                    # pair-keying only changes behavior when a DIFFERENT task of the same
                    # agent_id failed (the ISS-028 task_loop edge).
                    self._record_failed_invocation(ectx, spec.id)
                    yield {
                        "type": "agent_error",
                        "data": {
                            "agent_id": spec.id,
                            "error": f"Agent timed out after {agent_timeout:.0f}s — using best available output",
                            "recoverable": True,
                        },
                    }

                # ── ISS-016 (A1): runner ``error``-event → recoverable agent_error ──────
                # A runner-surfaced fault marks the agent failed. Emit the SAME recoverable
                # agent_error shape the timeout path uses above (so the dispatch loop's
                # _failed_agent_ids collector at :1620-1627 records spec.id), then RETURN —
                # explicitly SKIPPING the ``output = "".join(output_chunks)`` build below,
                # the result-append, and the agent_complete yield. This is the deliberate
                # divergence from the timeout path (which keeps the completion): per CONTEXT
                # A1 the error path must NOT append a completed result, so this agent stays
                # in _failed_agent_ids and is NOT in results → the engine terminal machinery
                # maps it to pipeline_failed (all-fail) / status:degraded (partial). The
                # client-facing message is the SANITIZED, bounded text (no traceback /
                # provider ARN / region / model-id — WR-02, T-16-01-ID); the raw str(exc)
                # is logged server-side only. No F3 re-key, no runner edit, no text match
                # (SC-001).
                if agent_errored:
                    # WR-02 (16 review): log the RAW provider message server-side for
                    # operator triage (the warning log is not client-visible), but emit
                    # only the sanitized, leak-free message on the agent_error event.
                    logger.warning(
                        "Agent %s: runner surfaced an error event — marking failed (no "
                        "completion). raw=%s | client=%s",
                        spec.id, agent_error_raw, agent_error_message,
                    )
                    _log_event("agent_error", pipeline_run_id, agent_id=spec.id,
                               error=agent_error_message)
                    RunLog(getattr(sandbox, "root", None)).write(
                        "agent_error", agent_id=spec.id, error=agent_error_message,
                    )
                    # ISS-028: record the (agent_id, task_number) failure pair. This arm
                    # RETURNS without a results.append, so the pair stays UNRECOVERED — a
                    # task_loop where an earlier task of this same agent_id completed no
                    # longer masks this hard failure (the agent_id-only subtraction at the
                    # terminal zeroed it → a half-built deliverable lied as clean
                    # pipeline_complete). All-fail still maps to pipeline_failed via the
                    # untouched _failed_agent_ids branch.
                    self._record_failed_invocation(ectx, spec.id)
                    yield {
                        "type": "agent_error",
                        "data": {
                            "agent_id": spec.id,
                            "error": agent_error_message or "Agent run failed",
                            "recoverable": True,
                        },
                    }
                    return

                output = "".join(output_chunks)

                # ── WR-01 (13 review fix): sanitize fabricated tool-call XML HERE ────────
                # The runner's done-event sanitizer (F4 / 13-02) is inert on this path —
                # the engine assembles the authoritative output from ``chunk`` events and
                # never consumes ``done``. Apply the SAME transform to the chunk-joined
                # output, duck-typed on the runner's capability surface (no app-module
                # import, no workflow/agent-name branch — SC-001). The runner method is a
                # no-op for tool-using agents and a same-object identity for clean text,
                # so the characterization snapshots stay byte-identical.
                _sanitize_fn = getattr(agent, "sanitize_output", None)
                if callable(_sanitize_fn):
                    output = _sanitize_fn(output)

                # ── Single-file deliverable: read the named file from the run sandbox ─────
                # (INV-1, migrated L10) An agent whose run produces a single on-disk file
                # (deliverable.strategy == "single_file", e.g. the prototype build loop)
                # writes its HTML to that file via the native deepagents write_file/edit_file
                # tools — the text stream only carries the tool confirmation, not the HTML.
                # Read the named file back and prefer it over the streamed text so downstream
                # agents (and the agent_complete.output_length snapshot key — PARITY-09) see
                # the full deliverable. Keyed off the DECLARED deliverable spec on ctx, NOT a
                # workflow-name branch (the former prototype-name readback gate, deleted in
                # 07-05). The fall-through resolution is owned by the single_file deliverable
                # resolver; this is the mid-stream "prefer the deliverable over the
                # confirmation" readback that the per-agent output (and output_length) needs.
                _deliv = getattr(ectx, "deliverable", None)
                _deliv_strategy = getattr(_deliv, "strategy", None)
                if _deliv_strategy == "single_file" and not getattr(ectx, "is_revision_workflow", False):
                    _deliv_name = getattr(_deliv, "name", None) or "prototype.html"
                    file_from_disk = sandbox.read(_deliv_name)
                    if file_from_disk and len(file_from_disk) > len(output):
                        logger.info(
                            "Agent %s: using sandbox %s (%d chars) instead of text output (%d chars)",
                            spec.id, _deliv_name, len(file_from_disk), len(output),
                        )
                        output = file_from_disk

                # ── PPT carousel deck: strip slide-hiding CSS the composer may hallucinate ──
                # (INV-1, migrated L3) Sanitize here (before storage/context) so the stored
                # artifact, the downstream QA validator, the agent_complete.output_length
                # snapshot key (PARITY-07/09), and the final output all see a deck whose
                # carousel renders all slides. Keyed off the DECLARED deliverable strategy
                # (== "ppt"), NOT a workflow-name branch (the former ppt-name-set sanitize
                # gate, deleted in 07-05). The transform is import-pure and a no-op on
                # non-carousel / non-HTML input; its definition lives in the ppt deliverable
                # resolver's shared _artifact module (move-don't-copy, INV-12).
                if _deliv_strategy == "ppt" and output:
                    from agents.capabilities.deliverables._artifact import (
                        sanitize_carousel_deck_html as _sanitize_deck,
                    )
                    from agents.capabilities.deliverables._artifact import (
                        strip_code_fence as _strip_fence,
                    )

                    # Fence-strip BEFORE the sanitize, mirroring the ppt resolver's
                    # own order. Doing it here (not only at deliverable time) is what
                    # keeps the DOWNSTREAM agent honest: ppt-validator consumes
                    # ppt-composer's stored artifact, so a composer that wrapped its
                    # deck in ```html would otherwise hand the validator a fenced
                    # blob to "validate" and re-emit.
                    output = _sanitize_deck(_strip_fence(output))

                # ── [08-08 / CR-01] before_write hook firing (additive, declaration-driven) ──
                # The DELIVERABLE-WRITE seam: the agent's produced deliverable content
                # (``output``, read back off the sandbox above for single_file) is about to
                # be persisted (the typed dual-write below + the downstream readback). Fire
                # the step's DECLARED ``before_write`` hooks over it FIRST (secret_scan
                # scans this payload; a manifest declaring ``hooks: [secret_scan]`` blocks a
                # secret-bearing write). Declaration-driven (only DECLARED hooks fire) so a
                # legacy step (declares no hooks) fires NOTHING here — no hook_runs row, the
                # write proceeds byte-identically (the characterization snapshots stay green:
                # they declare no hooks AND carry no secret). A ``block`` HALTS the persist
                # ADDITIVELY (the artifact is not written; no new WS event type) — the
                # fine-grained complement to the coarse pre-step ``security`` gate.
                _cur_step = getattr(ectx, "current_step", None)
                if output and _cur_step is not None and getattr(_cur_step, "hooks", None):
                    _bw_outcome = await self._fire_hooks(
                        "before_write", _cur_step, ectx, _CAPABILITY_REGISTRY, payload=output
                    )
                    if _bw_outcome == "block":
                        logger.warning(
                            "before_write hook blocked the deliverable write for agent %s "
                            "(declared hooks=%s) — skipping persist (additive halt)",
                            spec.id, list(getattr(_cur_step, "hooks", []) or []),
                        )
                        output = ""

                # Typed write (PERSIST-02 step 2): the typed graph + DB — the SOLE artifact
                # path since the prior-agent output mirror was deleted in 05-07 (INV-3).
                # Skip empty output (an agent that produced nothing has no artifact). The
                # location is the sandbox-relative file for file-backed prototype HTML, else
                # a logical artifact_refs path for string artifacts (D-01).
                if output:
                    _kind = self._artifact_kind_for(spec)
                    # CR-05 / 07-11 de-hardcode (WR-01): source the html_file location from
                    # the DECLARED deliverable name (the same accessor threaded through the
                    # strategy + persist path, mirroring single_file.py / engine.py:1629),
                    # NOT the literal "prototype.html". Parity-safe: for prototype/od_prototype
                    # the declared name IS "prototype.html", so the persisted location stays
                    # byte-identical; a future non-prototype html_file workflow now persists
                    # under its own declared name instead of a wrong prototype location.
                    _html_loc = getattr(getattr(ectx, "deliverable", None), "name", None) or "prototype.html"
                    _location = (
                        _html_loc
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
                        # REDO-GATE B5: on a re-run this records lineage to the rejected
                        # ref (the new version N+1 supersedes it, decision #4). None on
                        # every normal run ⇒ byte-identical (INV-3). Loop local (F3).
                        derived_from=_iter_derived,
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

                # ── T16: the artifact guarantee (R-20, D-06, F-06) ──────────────────────
                # The preamble TELLS a custom-agent step the filename it must write to
                # (factory.py, T11) — but an instruction is not a guarantee, and the
                # engine is model-agnostic by decision (Q15). Verify the file actually
                # landed in the run sandbox; if not, write the step's streamed text there
                # ourselves and emit ``artifact_fallback``. This is what makes R-20 true
                # regardless of model, and structurally kills the spec 011 D-02 defect
                # (an agent that streams instead of writing yielding a silently empty
                # deliverable).
                _fallback_filename = self._check_artifact_fallback(
                    ectx, spec.id, output, sandbox, user_message,
                    deliverable_filename=self._deliverable_filename_override(
                        ectx, index, ordered_agents,
                    ),
                )
                if _fallback_filename:
                    _log_event(
                        "artifact_fallback", pipeline_run_id,
                        agent_id=spec.id, filename=_fallback_filename,
                    )
                    RunLog(getattr(sandbox, "root", None)).write(
                        "artifact_fallback", agent_id=spec.id, filename=_fallback_filename,
                    )
                    yield {
                        "type": "artifact_fallback",
                        "data": {"agent_id": spec.id, "filename": _fallback_filename},
                    }

                duration = time.time() - agent_start
                agent_total_tokens = agent_input_tokens + agent_output_tokens
                results.append({
                    "agent_id": spec.id, "name": spec.name, "role": spec.role,
                    "icon": spec.icon, "output": output, "duration": duration,
                    "input_tokens": agent_input_tokens, "output_tokens": agent_output_tokens,
                    "total_tokens": agent_total_tokens,
                    # ISS-032: per-agent prompt-cache split (summed into the run totals
                    # below; 0 under the scripted characterization model).
                    "cache_read_tokens": agent_cache_read_tokens,
                    "cache_write_tokens": agent_cache_write_tokens,
                    # ISS-028: the task identity of THIS completed invocation ("" for a
                    # single_shot agent) so the terminal degraded decision can subtract
                    # COMPLETED (agent_id, task_number, visit_count) triples from
                    # ectx.failed_invocations. An internal-only field — results never
                    # reaches the wire / a snapshot (the WS layer builds its agent_outputs
                    # from EVENTS, and every reader of ``results`` uses
                    # .get()/["output"]/["agent_id"]/len), so INV-3 byte-parity is
                    # unaffected.
                    "task_number": getattr(ectx, "build_task_number", "") or "",
                    # R-08: this invocation's loop-revisit count, so a pass-2 completion
                    # of the same (agent_id, task_number) doesn't mask a pass-1 failure.
                    "visit_count": ectx.step_visit_counts.get(spec.id, 0),
                })
                _log_event("agent_complete", pipeline_run_id, agent_id=spec.id,
                           duration_ms=duration * 1000)
                RunLog(getattr(sandbox, "root", None)).write(
                    "step_end", agent_id=spec.id, model=_resolved_model_id,
                    tokens_in=agent_input_tokens, tokens_out=agent_output_tokens,
                )
                # Persist what this step STREAMED into the sandbox, so the run
                # workspace holds every output an agent produced and not only the
                # files one explicitly authored through ``write_file``. Lands under
                # the reserved ``.agents/`` prefix, which ``list_files`` shows and
                # the deliverable walk skips — see sandbox._AGENT_OUTPUTS_PREFIX for
                # why that asymmetry is required. Best-effort and never raises, so a
                # write failure cannot fail an agent that already succeeded; the
                # streamed UI transport below is untouched either way.
                write_agent_output(
                    sandbox,
                    index=index,
                    agent_id=spec.id,
                    name=spec.name,
                    output=output,
                    task_number=getattr(ectx, "build_task_number", "") or "",
                    visit_count=ectx.step_visit_counts.get(spec.id, 0),
                )
                yield {
                    "type": "agent_complete",
                    # ``visit_count`` mirrors agent_start's (R-08) — same non-zero-only
                    # rule, so a first dispatch stays byte-identical and the goldens
                    # hold. Emitted on BOTH ends so a client can pair start/complete per
                    # pass instead of collapsing repeats onto one row.
                    "data": {"agent_id": spec.id, "name": spec.name, "duration": round(duration, 2),
                             "output_length": len(output), "index": index, "total": len(ordered_agents),
                             **({"visit_count": _vc_done}
                                if (_vc_done := ectx.step_visit_counts.get(spec.id, 0)) else {}),
                             "input_tokens": agent_input_tokens, "output_tokens": agent_output_tokens,
                             "total_tokens": agent_total_tokens,
                             # CWF-002 (fix a): the per-agent RESOLVED primary model id (captured
                             # at :3055, the id the MODEL-02 fallback chain is armed on) — makes the
                             # effective model queryable in the live stream. Reuses the existing
                             # _VOLATILE_STRIP_KEYS "model_id" entry, so the 5 characterization
                             # goldens stay byte/event-identical (INV-3) with no _normalize edit.
                             "model_id": _resolved_model_id,
                             # ISS-032: per-agent cache split (stripped by _VOLATILE_STRIP_KEYS,
                             # golden-neutral; the WS collector sums these into the run totals).
                             "cache_read_tokens": agent_cache_read_tokens,
                             "cache_write_tokens": agent_cache_write_tokens},
                }

                # ── Human_Gate: pause for user review if agent declares gate ──
                # The agent's AGENT.md frontmatter declares `gate: Human_Gate`.
                # We pause here, emit review_gate_ready with the agent's output,
                # and wait for the user to approve (possibly with edits).
                # On approve: continue with (possibly edited) output.
                # On reject: cancel the pipeline.
                # Whether THIS agent gates is the effective per-run decision (default
                # = today's static `gate: Human_Gate` set; see _should_gate / the
                # `gate_agent_ids` param on execute()). REDO-GATE: the inline call site
                # passes redoable=True (a structural path, name-free — SC-001) so the
                # FE offers Redo on every LIVE human gate; the _gate_redo branch below
                # re-runs THIS agent via the enclosing while-loop (flat stack, F2).
                if self._should_gate(spec, ectx, invocation_gated=invocation_gated):
                    # SC-001: derive the update-specs eligibility STRUCTURALLY from the
                    # artifact-kind (name-free), mirroring redoable's inline True.
                    _ek = self._artifact_kind_for(spec)
                    # ISS-052: name WHICH firing this is. The analyze gate opened inside a
                    # revision pass and the one re-opened after it returns share a gate_key
                    # AND their output bytes, so without this the user (and any consumer
                    # keyed on those two) cannot tell them apart.
                    _rev_cycle, _rev_in_flight = self._stamp_revision_marks(ectx)
                    # R-08: fold the loop-revisit count into gate_key so a step re-entered
                    # via a route loop-back doesn't collide with its own prior firing.
                    _visit_count = ectx.step_visit_counts.get(spec.id, 0)
                    async for gate_event in self._run_review_gate(
                        pipeline_run_id=pipeline_run_id,
                        agent_id=spec.id,
                        agent_name=spec.name,
                        output=output,
                        redoable=True,
                        update_specs_eligible=self._update_specs_eligible(_ek, ectx),
                        artifact_kind=_ek,
                        revision_cycle=_rev_cycle,
                        revision_in_flight=_rev_in_flight,
                        cancel_event=cancel_event,
                        visit_count=_visit_count,
                    ):
                        if gate_event.get("type") == "_gate_rejected":
                            # User rejected — cancel the pipeline
                            # Guard: only transition if not already in a terminal state
                            current = self._state_machine.get_state(pipeline_run_id)
                            if current not in ("cancelled", "failed", "diverted"):
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
                                # WR-01 de-hardcode: declared deliverable name for html_file.
                                _ek_html_loc = getattr(getattr(ectx, "deliverable", None), "name", None) or "prototype.html"
                                # RESUME-15: stamp lineage to the version this edit
                                # supersedes (resolved BEFORE the write == prior max).
                                # None on a first-ever write ⇒ byte-identical (INV-3).
                                _prior_ref = self._latest_typed_ref_id(ectx, spec.id, _ek)
                                await self._dual_write_artifact(
                                    ectx,
                                    producer_agent=spec.id,
                                    producer_step=spec.id,
                                    content=edited,
                                    kind=_ek,
                                    location=(
                                        _ek_html_loc
                                        if _ek == "html_file"
                                        else f"artifact_refs/{spec.id}"
                                    ),
                                    derived_from=_prior_ref,
                                )
                            # Also update the last result
                            if results:
                                results[-1] = {**results[-1], "output": edited}
                        elif gate_event.get("type") == "_gate_redo":
                            # REDO-GATE: re-run THIS agent in place (decision #1/2).
                            # Set the LOOP LOCALS the next iteration consumes (F3) —
                            # the rejected output stays as a prior ArtifactRef version
                            # (decision #4); the re-run's write records derived_from
                            # lineage to it, and (ISS-086) the re-run's PROMPT carries
                            # that same version as its subject. Keyed on the GENERIC
                            # event type (SC-001); the body is the ONE shared consumer.
                            (redo_directive, redo_derived_from,
                             redo_prior_artifact) = await self._consume_redo(
                                gate_event=gate_event, spec=spec,
                                results=results, ectx=ectx,
                            )
                            redo_attempt += 1  # next re-run gets a FRESH checkpoint thread (:redo{N})
                            break  # leave the gate consumer; the while-loop re-runs
                        elif gate_event.get("type") == "_gate_update_specs":
                            # KAN-101: "Update the Specs" — run the spec revision
                            # sub-pipeline (specify → plan → analyze) with the analysis
                            # report as additional context, then re-open this gate with
                            # the new analysis output. FLAT loop (like _gate_redo) — no
                            # recursion (F2 precedent). Keyed on GENERIC event type, no
                            # agent/workflow literal (INV-1 / SC-001).
                            #
                            # si4: the body is the ONE shared _consume_update_specs helper
                            # (INV-12) — the re-entry and re-open branches drive the
                            # identical code rather than holding their own copies. The
                            # helper stores the new output on ectx scratch; breaking here
                            # lets the while-loop's pending short-circuit re-open the gate
                            # WITHOUT re-running this agent's model.
                            spec_revision_attempt += 1
                            _us_cancelled = False
                            async for _us_event in self._consume_update_specs(
                                gate_event=gate_event, spec=spec, index=index,
                                ordered_agents=ordered_agents, user_message=user_message,
                                sandbox=sandbox, pipeline_run_id=pipeline_run_id,
                                pipeline_type=pipeline_type, planning_context=planning_context,
                                attached_skills=attached_skills, attached_hooks=attached_hooks,
                                model_id=model_id, results=results, cancel_event=cancel_event,
                                ectx=ectx, revision_index=spec_revision_attempt,
                            ):
                                if _us_event.get("type") == "_update_specs_done":
                                    _us_cancelled = bool(_us_event.get("cancelled"))
                                else:
                                    yield _us_event
                            if _us_cancelled:
                                return
                            break  # leave gate consumer; while-loop re-enters
                        else:
                            yield gate_event
                    else:
                        # The gate generator exhausted WITHOUT a redo break →
                        # approve / edit / (reject already returned) → this agent is
                        # done; leave _run_agent.
                        return
                    # Only reached via the _gate_redo `break` above → re-run the SAME
                    # agent in the enclosing while-loop (FLAT STACK — no recursion, F2).
                    continue

                # Not gated → a single run; done after one loop iteration.
                return

            except asyncio.CancelledError:
                raise
            except (FileNotFoundError, PermissionError) as exc:
                # Missing AGENT.md or template — fatal
                _log_event("agent_error", pipeline_run_id, agent_id=spec.id, error=str(exc))
                RunLog(getattr(sandbox, "root", None)).write("agent_error", agent_id=spec.id, error=str(exc))
                # ISS-028: unrecovered (agent_id, task_number) failure — no results.append.
                self._record_failed_invocation(ectx, spec.id)
                yield {"type": "agent_error", "data": {"agent_id": spec.id, "error": str(exc), "recoverable": False}}
                return  # REDO-GATE: terminate the redo while-loop (no re-run on a fatal error)
            except Exception as exc:
                # If the run is already in a terminal state (cancelled/failed), don't
                # treat this as a recoverable error — re-raise so the pipeline stops.
                from agents.execution_engine.state_machine import StateMachineError
                if isinstance(exc, StateMachineError):
                    current = self._state_machine.get_state(pipeline_run_id)
                    if current in ("cancelled", "failed", "diverted"):
                        logger.info(
                            "Agent %s: pipeline already in terminal state=%s — stopping",
                            spec.id, current,
                        )
                        return  # Stop the agent loop cleanly
                logger.exception("Agent %s failed", spec.id)
                _log_event("agent_error", pipeline_run_id, agent_id=spec.id, error=str(exc))
                RunLog(getattr(sandbox, "root", None)).write("agent_error", agent_id=spec.id, error=str(exc))
                # ISS-028: unrecovered (agent_id, task_number) failure — this handler
                # writes an [Error:…] placeholder but never appends to results.
                self._record_failed_invocation(ectx, spec.id)
                yield {"type": "agent_error", "data": {"agent_id": spec.id, "error": str(exc), "recoverable": True}}
                # Typed-write the error placeholder so a downstream consumer reading from
                # the typed graph sees it (the SOLE artifact path since 05-07; parity).
                _err_output = f"[Error: {exc}]"
                _erk = self._artifact_kind_for(spec)
                # WR-01 de-hardcode: declared deliverable name for html_file.
                _erk_html_loc = getattr(getattr(ectx, "deliverable", None), "name", None) or "prototype.html"
                await self._dual_write_artifact(
                    ectx,
                    producer_agent=spec.id,
                    producer_step=spec.id,
                    content=_err_output,
                    kind=_erk,
                    location=(
                        _erk_html_loc if _erk == "html_file" else f"artifact_refs/{spec.id}"
                    ),
                )
                return  # REDO-GATE: terminate the redo while-loop after an errored run

    # ------------------------------------------------------------------
    # DELETED (07-05, L11): the legacy per-task build-loop driver, its reference-file
    # writer, and the two pure task-plan parsers (count + per-block slice). The per-task
    # build loop is now the ``task_loop`` ExecutionStrategy (heading_tasks task parser +
    # the html_static/html_render validators), routed via
    # resolve("strategy","task_loop").run() and delegating per-agent runs to
    # KernelServices.run_agent / .run_validation_fix_loop. The kept survivors (the
    # validation fix-loop below, the template-example loader, _run_agent) are LIVE
    # behavioral primitives reached via the handle — NOT leaks (the L11 ratchet scopes
    # the four deleted symbols only; see specs/.../migration-ledger.md).
    # ------------------------------------------------------------------

    async def _run_validation_fix_loop(
        self,
        *,
        ctx: "AgentContext",
        sandbox: RunSandbox,
        pipeline_run_id: str,
        task_num: int,
        total_tasks: int,
        cancel_event,
        filename: str,
        max_attempts: int = 2,
        agent_id: str = "prototype-build",
        baseline_static: "set[str] | None" = None,
        baseline_console: "set[str] | None" = None,
        user_instruction: str | None = None,
        label: str = "",
        checkpointer: object | None = None,
        require_render: bool | None = None,
        aux_usage_sink: "Callable[[dict], None] | None" = None,
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

        # Resolve the require_render knob (RENDER-SEAM / REQUIRE-RENDER-KNOB): None
        # falls back to the Settings default (skip-is-a-pass — INV-3 parity).
        if require_render is None:
            from app.core.config import settings as _rr_settings

            require_render = _rr_settings.PROTOTYPE_REQUIRE_RENDER

        # 07-11 / CR-05: the deliverable filename is threaded in from the strategy
        # (``ctx.deliverable.name``) — no hardcoded ``prototype.html``. The prototype
        # manifest declares ``prototype.html`` so the value passed through keeps
        # validation byte-identical; a non-prototype task_loop workflow validates +
        # fixes ITS OWN file. The fix-prompt wording names this ACTUAL file too.
        html_path = sandbox.path_for(filename)
        if not html_path.is_file():
            logger.warning(
                "Validation: task %d/%d wrote no %s — skipping validation",
                task_num, total_tasks, filename,
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

            # Route render availability through the SINGLE policy helper (RENDER-SEAM).
            # ``status == "ok"`` iff the render ran; a skip (blocked/allowed) never
            # opens a :fix thread here — the GATE is the authoritative fail-closed, and
            # the validator_skipped audit row is owned by html_render, not re-written
            # here (CORRECTION 3). ``render_skipped``/``render_failed`` keep the legacy
            # logging + residual semantics.
            _render_status = render_coverage_status(rres, bool(require_render))
            render_skipped = _render_status != "ok"
            render_failed = _render_status == "ok" and not rres.ok
            if render_skipped:
                logger.info(
                    "Validation: task %d/%d render skipped (%s) — status=%s "
                    "(require_render=%s); not opening a fix thread for it",
                    task_num, total_tasks, rres.summary(), _render_status,
                    bool(require_render),
                )
            # The fix-list (pure selection). With empty baselines this is byte-
            # identical to today's build ``error_lines`` and ``bool(...)`` of it
            # equals today's ``(not sres.ok) or render_failed`` (see docstring).
            error_lines = _select_issues_to_fix(
                sres, rres, baseline_static, baseline_console,
                require_render=bool(require_render),
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
                            _dead_nav_line(n)
                            for n in rres.nav_results if not n.ok
                        )
                        residual.extend(getattr(rres, "coverage_errors", None) or [])
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
                # BUILD — preserve today's exact wording verbatim (the deliverable
                # filename is interpolated; ``prototype.html`` passes through
                # byte-identically for the prototype manifest, 07-11 / CR-05).
                fix_message = (
                    f"=== VALIDATION ERRORS (fix {filename}) ===\n"
                    f"The prototype you built for task {task_num} of {total_tasks} failed "
                    f"validation. Read the current {filename} with "
                    f"read_file(file_path=\"{filename}\") and apply MINIMAL "
                    f"edit_file(file_path=\"{filename}\", ...) changes to fix ONLY "
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
                    f"=== VALIDATION ERRORS (fix {filename}) ===\n"
                    f"The user asked you to revise this prototype:\n"
                    f"\"{user_instruction}\"\n\n"
                    f"You revised this prototype to satisfy that request — keep that "
                    f"change intact. Now fix ONLY the issues listed below (they were "
                    f"introduced by your edit, or they stop the page rendering / "
                    f"displaying content); do not touch anything unrelated.\n\n"
                    f"Read the current {filename} with "
                    f"read_file(file_path=\"{filename}\") and apply MINIMAL "
                    f"edit_file(file_path=\"{filename}\", ...) changes. Do NOT "
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
                    # ISS-033-A: the fix sub-agent is REAL run spend (300k-600k input
                    # tokens per call) that this drain used to discard wholesale. Route
                    # its ``usage`` into the run's aux accounting — the SAME sink and
                    # the SAME four keys the planner/clarify one-shots feed, so the
                    # tokens land in the pipeline_complete totals with no second fold.
                    # It must NOT reach ``results``: agents_completed = len(results),
                    # so a fix attempt counted there would become a phantom agent.
                    # ORDERING: capture BEFORE the cancel check — a token the model has
                    # already reported was already paid for, and a cancel must not
                    # erase it from the bill.
                    if aux_usage_sink is not None and _ev.get("type") == "usage":
                        aux_usage_sink(
                            {
                                "input_tokens": _ev.get("input_tokens", 0) or 0,
                                "output_tokens": _ev.get("output_tokens", 0) or 0,
                                "cache_read_tokens": _ev.get("cache_read_tokens", 0) or 0,
                                "cache_write_tokens": _ev.get("cache_write_tokens", 0) or 0,
                            }
                        )
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

    def _should_gate(
        self, spec, ectx: ExecutionContext, *, invocation_gated: bool = True
    ) -> bool:
        """Decide whether ``spec`` pauses for the inter-agent Human review gate.

        Effective set = the per-run ``gate_agent_ids`` passed to ``execute()``
        (carried on ``ectx.gate_agent_ids``) when given, else the STATIC set.

        - ``ectx.gate_agent_ids is not None``  → gate iff ``spec.id`` is in it.
        - else (default; field absent / client didn't send it) → gate iff the
          AGENT.md frontmatter declares ``gate: Human_Gate`` — **exactly today's
          static rule**, so behavior is byte-identical unless a client opts in.

        ``invocation_gated`` (ISS-097) narrows that agent-level selection to the
        invocations it was written to describe. ``gate_agent_ids`` is a per-STEP
        choice ("checked agents pause the pipeline after they finish"), but this
        predicate reads ``spec.id``, which is per-INVOCATION. Those were the same
        thing until a strategy started producing N invocations of one agent id for
        one step, at which point a single tick armed N gates on the ONE gate_key.
        A call site that creates an invocation which is NOT a step — a fan-out
        worker, a bounded merge-agent attempt — passes ``False``. It defaults
        ``True``, so every step-shaped invocation is byte-identical (INV-3).

        Only selects *which* agents trigger the gate; the gate itself
        (``_run_review_gate`` + its ``review_gate_*`` events) is unchanged.
        """
        gate_ids = ectx.gate_agent_ids
        selected = (
            spec.id in set(gate_ids)
            if gate_ids is not None
            else getattr(spec, "gate", None) == "Human_Gate"
        )
        return invocation_gated and selected

    # ------------------------------------------------------------------
    # Executable hook firing (08-07 / HOOK-01..04) — the D-09 lifecycle seam
    # ------------------------------------------------------------------

    def _resolve_executable_hooks(self, step, registry) -> list:
        """Return the step's DECLARED executable ``HookHandler`` impls (08-08 / CR-01/WR-03).

        Declaration-driven (CR-01/WR-03): a step fires ONLY the hooks it DECLARES on
        ``step.hooks`` (the manifest ``hooks: [...]`` list, name-validated at compile
        time) — NOT every registered executable hook. A legacy step (prototype/od_/
        ppt/code-gen) declares no hooks → this returns ``[]`` → it fires NOTHING (no
        hook_runs row, no console span on the legacy parity paths). The ``behavioral``
        provider is the non-executable prompt-only sub-type and is never a firing hook.

        Resolves each declared name off the registry, skipping any unresolvable name
        defensively (a compile-validated manifest never carries one). The permission
        filter (``hooks.base.is_bound`` against the step's effective perms) is applied
        downstream in ``_fire_hooks`` — a declared git/exec hook stays unbound while
        its permission is OFF.
        """
        names = list(getattr(step, "hooks", None) or [])
        hooks: list = []
        for name in names:
            try:
                hooks.append(registry.resolve("hook", name))
            except (KeyError, RuntimeError):
                continue
        return hooks

    async def _fire_hooks(
        self,
        event_name: str,
        step,
        ectx: ExecutionContext,
        registry,
        *,
        payload: str = "",
        extra: dict | None = None,
    ) -> str:
        """Fire the step's DECLARED executable hooks bound for ``event_name`` (HOOK-01..04 / D-09).

        Declaration-driven (08-08 / CR-01/WR-03): the candidate set is the step's
        DECLARED hooks (``step.hooks``), NOT every registered executable hook. A
        legacy step declares no hooks → nothing fires (no hook_runs row, no console
        span on the legacy parity paths). Among the declared hooks, binding then =
        the hook declares ``event_name`` (or the ``*`` wildcard) AND the step's
        EFFECTIVE permissions (``step.tools`` — the 08-03 intersection) grant the
        hook's ``required_permission`` (``hooks.base.bound_hooks``). A declared git/
        exec hook stays NOT bound while those perms are OFF (HOOK-02 / T-08-07-EoP).
        Each bound hook's ``handle`` writes its own ``hook_runs`` row (HOOK-04) via
        ``ctx.runner.record_hook_run``.

        Returns the AGGREGATE outcome: ``block`` iff ANY hook blocked (the caller
        halts the offending action ADDITIVELY — it emits NO existing WS event, it
        just stops the write/step, so a clean characterization run that carries no
        secret is byte/event-identical — RESEARCH Pitfall 6); else ``continue``. A
        hook that RAISES is swallowed (a hook failure must never abort the run —
        INV-3 parity), treated as ``continue``.
        """
        from agents.capabilities.hooks.base import (
            HOOK_BLOCK,
            HOOK_CONTINUE,
            bound_hooks,
        )

        perms = getattr(step, "tools", None)
        hooks = bound_hooks(
            self._resolve_executable_hooks(step, registry), event_name, perms
        )
        if not hooks:
            return HOOK_CONTINUE

        # The fired-event envelope every hook reads (dict shape — defensive parsers
        # in the hook impls accept attr OR dict). ``payload`` carries the write
        # content for a ``before_write`` firing (scanned by secret_scan); it is ""
        # for a lifecycle firing (otel just records the span/row).
        event = {
            "event": event_name,
            "step": getattr(step, "agent_id", None),
            "payload": payload,
        }
        # KAN-73: merge caller-supplied extra fields (agent_name, step_index, etc.)
        # so the audit_logger hook can populate human-readable summaries without
        # the hook needing to look up AgentSpec from ctx.
        if extra:
            event.update(extra)

        aggregate = HOOK_CONTINUE
        for hook in hooks:
            try:
                result = await hook.handle(event, ectx)
            except Exception as exc:  # noqa: BLE001 — a hook must never abort the run
                logger.warning(
                    "hook %r on event %s raised (%s) — treating as continue",
                    getattr(hook, "name", "?"), event_name, exc,
                )
                continue
            outcome = getattr(result, "outcome", HOOK_CONTINUE)
            if outcome == HOOK_BLOCK:
                aggregate = HOOK_BLOCK
        return aggregate

    # ------------------------------------------------------------------
    # Review_Gate — Human review/edit/approve gate between agents
    # ------------------------------------------------------------------

    # Pre-step vs post-step gate placement (D-03). security/approval/human gate
    # BEFORE the strategy runs (they decide whether the step proceeds); validation
    # gates AFTER (it inspects the produced deliverable). An unknown/unclassified
    # gate name defaults to pre-step (fail-safe: evaluate it before the work).
    # ``conditional`` is likewise POST-step (spec 014): by default it reads its OWN
    # step's route_decision artifact (route.condition_agent defaults to the step's
    # own id — conditional.py's decision_source), which does not exist until the
    # step's own agent has run. Evaluating it pre-step always finds no content, so
    # every match fails closed to gate_blocked and the routing cursor jump (T14)
    # never fires.
    # ``human`` is POST-step: it reviews the step's OWN output and supports redo —
    # the behaviour every shipping pipeline already gets from the inline
    # ``_should_gate``/``AGENT.md gate: Human_Gate`` path, and what an author
    # reasonably expects from `gates: [human]`. The PRE-step variant (review the
    # PREVIOUS step's output, the edit becomes this step's input) is now spelled
    # ``before-human`` so the two are distinguishable in a manifest. Previously both
    # were spelled ``human`` and which one ran depended on whether the step's AGENT
    # had an ``AGENT.md`` gate flag — invisible from the manifest, and the reason
    # prototype's three `gates: [human]` declarations were silently dead lines.
    _POST_STEP_GATES = frozenset({"validation", "conditional", "human"})

    # WR-03 (13 review fix): gates whose ``block`` outcome is an EXPLICIT human
    # rejection (the user clicked Reject at the HITL pause) — run-cancellation
    # parity with the inline _run_review_gate path, not a mere step skip.
    # Gate-capability names, not workflow/agent names (SC-001).
    _HITL_GATES = frozenset({"human", "before-human", "approval"})

    # WR-07 (13 review fix): gates that FAIL CLOSED. A raised exception in a
    # validation-class gate degrades to pass (a gate failure must never abort a
    # run); for the security/HITL controls the same swallow would let a step
    # execute WITHOUT the required sign-off — inverting the control's purpose.
    # An exception in these maps to ``block`` (the step is skipped, the run
    # continues). Gate-capability names, not workflow/agent names (SC-001).
    # ``before-human`` belongs here for the same reason ``human`` does: an exception
    # in a HITL control must BLOCK, never degrade to pass — swallowing it would let a
    # step execute without the sign-off the control exists to require.
    _FAIL_CLOSED_GATES = frozenset({"security", "approval", "human", "before-human"})

    async def _evaluate_gates(
        self,
        step,
        ectx: ExecutionContext,
        registry,
        *,
        phase: str,
        inline_gated: bool = False,
    ) -> AsyncGenerator[tuple[dict, str, dict | None], None]:
        """Evaluate a step's declared ``gates: [...]`` for one phase (D-03).

        Yields ``(event, outcome, detail)`` for every additive event a gate emits
        so the caller can both forward the event AND act on the outcome (a
        pre-step ``block``/``wait_human`` halts the step). After a gate's events,
        yields a terminal ``(None, outcome, detail)`` sentinel so the halt
        decision is observable EVEN when the gate emits zero events (WR-04); the
        caller skips the ``None`` event when forwarding, so the emitted stream is
        unchanged. ``detail`` is the terminal ``GateOutcome.detail`` (e.g. the
        human gate's ``edited_content`` the kernel applies upstream — WR-04
        review fix); event yields carry ``None``. Gates evaluate in DECLARED
        order;
        only the gates belonging to ``phase`` (``pre``|``post``) run here. Each gate
        returns a ``GateOutcome`` (outcome + additive events); the kernel owns the
        yield so the gate impls stay simple async functions.

        Additive-only (INV-3): every event a gate yields is a NEW ``gate_*`` /
        ``validation_warning`` type flowing through the generic forward — no
        existing event is renamed/removed. A VALIDATION-class gate that raises is
        swallowed (a gate failure must never abort the run) and the step proceeds
        as if it passed; ``security``/``approval``/``human`` FAIL CLOSED — an
        exception maps to ``block`` (WR-07). Once a gate blocks (or waits for a
        human) the remaining declared gates are NOT evaluated (WR-07
        short-circuit); an HITL rejection short-circuits via ``cancel`` (WR-03).
        """
        declared = list(getattr(step, "gates", None) or [])
        if not declared:
            return
        for name in declared:
            is_post = name in self._POST_STEP_GATES
            if phase == "post" and not is_post:
                continue
            if phase == "pre" and is_post:
                continue
            # ── WR-02 (13 review fix): inline-gate dedupe ─────────────────────
            # ``human`` delegates to the SAME _run_review_gate the inline
            # ``_should_gate`` path drives, keyed on the SAME gate_key. When the
            # inline gate fires for this step, evaluating the declared ``human``
            # gate too would double-prompt (pre-step empty payload + post-step
            # real output). Skip it; the inline (output-bearing) gate is the
            # single review for this agent. Gate-CAPABILITY name, not a
            # workflow/agent name (SC-001) — same idiom as _POST_STEP_GATES.
            #
            # Also skip when the per-run gate_agent_ids selection EXPLICITLY
            # excludes this agent. gate_agent_ids=None means "use static AGENT.md
            # defaults"; gate_agent_ids=[] means "no gates this run" (user
            # unchecked all). Without this check the declared ``gates:[human]``
            # manifests on prototype steps fire a pre-step blank review_gate_ready
            # even when the user deselected all gates in the wizard, because
            # _should_gate returns False → inline_gated=False → the dedupe only
            # fires on the inline path, not on the user-deselect path.
            # Applies to BOTH declared HITL names. The `phase == "pre"` guard this
            # replaced was correct only while `human` was pre-step; now that `human`
            # is POST-step the guard would never match it, and prototype's three
            # `gates: [human]` declarations — live for the first time — would fire
            # ALONGSIDE the inline gate on the same agent and double-prompt.
            # `_evaluate_gates` has already filtered by phase before this point, so
            # whichever name arrives here is in its own phase and needs the same
            # treatment: the inline (output-bearing) gate wins, and a per-run
            # deselection suppresses the declared gate entirely.
            #
            # It also protects `before-human`: gate_key is
            # f"{run}:{agent_id}:{visit_count}" with no gate name in it, so a
            # pre-step declared pause plus an inline post-step pause on the SAME
            # step would collide on durable gate state.
            if name in ("human", "before-human") and (
                inline_gated
                or (
                    ectx.gate_agent_ids is not None
                    and getattr(step, "agent_id", None) not in ectx.gate_agent_ids
                )
            ):
                logger.info(
                    "declared 'human' gate on step %s skipped — %s",
                    getattr(step, "agent_id", "?"),
                    "inline review gate already covers this agent (WR-02 dedupe)"
                    if inline_gated
                    else "agent not in per-run gate_agent_ids selection",
                )
                continue
            try:
                gate = registry.resolve("gate", name)
                # ── [F1 / Phase 13] Streaming gate evaluation ─────────────────
                # A gate exposing ``evaluate_stream`` (human/approval) streams its
                # delegate events AS PRODUCED — so ``review_gate_ready`` reaches
                # the dispatch loop (and the WS consumer) BEFORE the gate awaits
                # the approval response, matching the working inline
                # ``_run_review_gate`` ordering. Streamed event dicts ride a
                # non-halting ``"pass"`` placeholder outcome (the caller only
                # halts on ``block``/``wait_human``); the definitive outcome
                # follows as the terminal WR-04 ``(None, outcome)`` sentinel.
                # Duck-typed on the gate's capability surface — no workflow/agent
                # names (SC-001/INV-1). Gates WITHOUT evaluate_stream (validation,
                # security) keep the await-then-yield path byte-identically.
                stream_fn = getattr(gate, "evaluate_stream", None)
                if callable(stream_fn):
                    outcome = "pass"
                    detail = None
                    async for item in stream_fn(step, ectx):
                        if isinstance(item, dict):
                            yield item, "pass", None
                        else:
                            # Terminal GateOutcome → captured; the WR-04
                            # sentinel is yielded below (shared with the
                            # awaited path so WR-03 cancel mapping applies).
                            outcome = getattr(item, "outcome", "pass")
                            detail = getattr(item, "detail", None)
                            break
                else:
                    result = await gate.evaluate(step, ectx)
                    outcome = getattr(result, "outcome", "pass")
                    detail = getattr(result, "detail", None)
                    for event in getattr(result, "events", None) or []:
                        yield event, outcome, None
            except Exception as exc:  # noqa: BLE001 — a gate must never abort the run
                # ── WR-07 (13 review fix): scope the fail-open swallow ────────
                # security/approval/human FAIL CLOSED: a raised gate (e.g. a
                # StateMachineError mid-HITL-stream) maps to ``block`` — the
                # step is skipped rather than executing WITHOUT its required
                # sign-off. Validation-class gates keep the fail-open degrade.
                if name in self._FAIL_CLOSED_GATES:
                    logger.warning(
                        "gate %r on step %s raised (%s) — FAIL-CLOSED: "
                        "treating as gate_blocked (WR-07)",
                        name, getattr(step, "agent_id", "?"), exc,
                    )
                    yield None, "block", {"gate": name, "reason": f"gate error: {exc}"}
                    return
                logger.warning(
                    "gate %r on step %s raised (%s) — treating as pass",
                    name, getattr(step, "agent_id", "?"), exc,
                )
                continue
            # ── WR-03 (13 review fix): HITL rejection cancels the RUN ─────────
            # A ``block`` from a human/approval gate is the user clicking Reject
            # at the review pause. The inline path cancels the pipeline on
            # rejection; the declared path used to merely skip the step and let
            # the run continue to a "successful" completion with the state
            # machine stranded in waiting_for_user. Surface a distinct
            # ``cancel`` sentinel the dispatch loop acts on; no further gates
            # evaluate (the run is over).
            if outcome == "block" and name in self._HITL_GATES:
                yield None, "cancel", detail
                return
            # WR-04: surface the outcome INDEPENDENTLY of event emission. A
            # blocking gate that emits zero events (``GateOutcome`` with
            # ``outcome="block"``/``"wait_human"`` but an empty ``events`` list)
            # must still halt the step — the prior code only yielded inside the
            # event loop, coupling "did the gate halt" to "did the gate emit a UI
            # event", so a no-event block would silently pass at a security
            # boundary. Yield a terminal ``(None, outcome)`` so the caller can act
            # on the halt regardless of events; the caller skips the ``None`` event
            # when forwarding/persisting, so the emitted event STREAM is unchanged
            # for every existing path (characterization snapshots stay byte/event
            # identical — a gate that already emits its event yields the same
            # events, only an extra non-forwarded ``None`` sentinel follows).
            yield None, outcome, detail
            # ── WR-07 (13 review fix): short-circuit on a blocking outcome ────
            # The step is halted regardless of the remaining declared gates —
            # evaluating them anyway could open a full HITL pause (declared
            # ``gates: [security, human]`` with security blocking used to ask
            # the user to approve a step that cannot run). Clean-run parity:
            # every gate passing never reaches this return.
            if outcome in ("block", "wait_human"):
                return

    async def _apply_declared_gate_edit(
        self,
        edited: str,
        results: list[dict],
        ordered_agents: list,
        ectx: ExecutionContext,
    ) -> None:
        """Apply an approve-with-edits payload from a DECLARED gate (WR-04).

        A declared pre-step human gate reviews the PREVIOUS step's output, so
        the user's edit re-writes that step's typed artifact as a NEW ref
        version (``_latest_typed_content`` then serves the edit to downstream
        consumers — ART-03) and updates the ``results`` entry, mirroring the
        inline ``_gate_edited`` handler in ``_run_agent`` byte-for-byte. With no
        completed upstream step there is nothing to apply — logged, not silent.
        """
        if not results:
            logger.warning(
                "declared-gate edit received before any step completed — "
                "no upstream artifact to apply it to; edit dropped (WR-04)"
            )
            return
        prev_id = results[-1].get("agent_id")
        prev_spec = next((s for s in ordered_agents if s.id == prev_id), None)
        if prev_spec is None:
            logger.warning(
                "declared-gate edit: no spec found for upstream agent %r — "
                "edit dropped (WR-04)", prev_id,
            )
            return
        _ek = self._artifact_kind_for(prev_spec)
        _ek_html_loc = (
            getattr(getattr(ectx, "deliverable", None), "name", None)
            or "prototype.html"
        )
        # RESUME-15: stamp lineage to the version this edit supersedes (resolved
        # BEFORE the write == prior max). None on a first-ever write ⇒ byte-identical.
        _prior_ref = self._latest_typed_ref_id(ectx, prev_spec.id, _ek)
        await self._dual_write_artifact(
            ectx,
            producer_agent=prev_spec.id,
            producer_step=prev_spec.id,
            content=edited,
            kind=_ek,
            location=(
                _ek_html_loc if _ek == "html_file" else f"artifact_refs/{prev_spec.id}"
            ),
            derived_from=_prior_ref,
        )
        results[-1] = {**results[-1], "output": edited}
        # Keep the running review payload consistent with the applied edit
        # (the WR-02 per-step refresh would otherwise lag one gate behind).
        ectx.last_streamed = edited

    # ------------------------------------------------------------------
    # KAN-101: Spec revision sub-pipeline helper
    # ------------------------------------------------------------------

    async def _run_spec_revision_sub_pipeline(
        self,
        spec,
        index: int,
        ordered_agents: list,
        user_message: str,
        sandbox,
        pipeline_run_id: str,
        pipeline_type: str,
        planning_context: dict,
        attached_skills,
        attached_hooks,
        model_id,
        results: list[dict],
        cancel_event,
        ectx,
        analysis_report: str,
        revision_index: int,
    ):
        """Re-run the specify → plan → analyze agents with the analysis report
        injected as revision context, yielding all their WS events upstream.

        Yields a synthetic ``_revision_analyze_output`` event at the end carrying
        the new analyzer output, followed by a normal return.

        ``analysis_report`` is the text produced by the previous analyze run.
        It is placed on ``ectx.spec_revision_context`` (a generic scratch field)
        so ``_compose_context_message`` can inject it. Cleared on exit (consume-
        once, matching the ``ecto.redo_directive`` pattern — F3 precedent).

        The specify re-dispatch ALSO receives its own prior output on
        ``ectx.spec_revision_prior_artifact`` — the report instructs it to preserve
        unchanged sections, and with ``consumes: []`` + ``tools: []`` that field is its
        only channel to the document (D1). The plan/analyze re-dispatches do NOT get it.

        The whole sub-pipeline runs on ``:rev{N}`` checkpoint threads (via
        ``ectx.revision_attempt``), so a revision never depends on the checkpointer
        replaying the pre-revision turn (D3).

        The three agents to re-run are identified by looking BACKWARDS from the
        current (analyzer) position in ``ordered_agents`` to find the three agents
        immediately before it: prototype-specify → prototype-plan → this agent.
        This is STRUCTURAL (position-based), not name-based (INV-1 / SC-001).

        RE-ENTRANCY (quick-260811-si4, BUGFIX-NESTED-REVISION defect A)
        --------------------------------------------------------------
        This method can RE-ENTER ITSELF. The analyze re-run below is a full ``_run_agent``,
        so it opens its own human gate, and the gate ACTION is client-controlled.

        Since ISS-053 that route is FENCED: ``_run_review_gate`` refuses an
        ``update_specs`` whose firing published ``update_specs_eligible=False`` (which the
        in-pass analyze gate always does) and keeps waiting, so a replayed or crafted POST
        no longer nests. The safety below is therefore no longer the ONLY protection — but
        it is kept, and kept tested, as defence in depth: it is what makes this method
        correct at any depth if a future call site ever passes the flag wrongly.

        * **Distinct ``:rev{N}`` at any depth.** ``revision_index`` arrives from the
          caller's per-``_run_agent`` local, which restarts at 0 for every invocation, so
          two nesting levels both computed 1. The effective index is instead derived from
          ``ectx.revision_high_water`` — a MONOTONE per-run mark that is never restored —
          so no two passes, sibling or nested, can mint the same checkpoint thread id.
          MEASURED pre-fix: both levels published index 1 and the run minted three
          duplicate ``:rev1`` ids, so the nested pass was served the outer pass's
          LangGraph conversation replay (the P23 class).
        * **An inner pass cannot strip the outer pass's state.** The ``finally`` below
          RESTORES the three scratch fields to what they held at entry instead of clearing
          them to zero/empty. MEASURED pre-fix: at the gate reached after the nested pass
          returned — with the OUTER pass still on the stack — ``revision_attempt`` was 0
          and ``spec_revision_context`` was empty, so the outer pass's remaining dispatches
          silently lost both their ``:rev`` suffix and their analysis report.

        At the OUTER nesting level the saved values are ``""`` / ``""`` / ``0``, so the
        restore is byte-equivalent to the previous unconditional clear and a first cycle
        still resolves to index 1 → ``:rev1``. Dormant on every non-revision run (INV-3).
        """
        # Identify the three agents to re-run: the two agents before this one
        # in ordered_agents (specify, plan) plus this agent (analyze).
        # index is THIS agent's (analyze) position; specify=index-2, plan=index-1.
        if index < 2:
            # Defensive: fewer than 2 predecessors — skip the sub-pipeline and
            # return no new output (the caller handles missing output gracefully).
            logger.warning(
                "Spec revision sub-pipeline: agent %s at index %d < 2 — cannot "
                "find predecessor specify/plan agents; skipping sub-pipeline",
                spec.id, index,
            )
            return

        specify_spec = ordered_agents[index - 2]
        plan_spec = ordered_agents[index - 1]
        analyze_spec = spec

        # ── RE-ENTRANCY (si4) ────────────────────────────────────────────────────────
        # Derive the EFFECTIVE index from the per-run high-water mark rather than trusting
        # the caller's per-_run_agent local, which restarts at 0 on every invocation and so
        # makes two nesting levels both publish 1. The mark is monotone and NEVER restored
        # — that is the whole guarantee that no two passes mint the same :rev{N}.
        # First cycle: high-water 0, revision_index 1 → 1 > 0 → 1 ⇒ :rev1 unchanged (INV-3).
        _prev_high = getattr(ectx, "revision_high_water", 0)
        effective_index = revision_index if revision_index > _prev_high else _prev_high + 1
        ectx.revision_high_water = effective_index

        # Capture the state THIS pass is about to overwrite, so the finally can restore it
        # instead of zeroing an outer pass that is still on the stack.
        _saved_attempt = ectx.revision_attempt
        _saved_context = getattr(ectx, "spec_revision_context", "")
        _saved_prior = ectx.spec_revision_prior_artifact

        # Read the document under revision ONCE, before the loop — the max-version typed
        # read (F5 discipline), so a rehydrated graph's arbitrary insertion order cannot
        # serve a stale version. Read before the loop because the specify re-run itself
        # mints a new version partway through (D1).
        prior_artifact = self._latest_typed_content(ectx, specify_spec.id) or ""

        # Inject the analysis report as revision context onto ectx (consume-once).
        ectx.spec_revision_context = analysis_report
        # Publish the thread index — this is what makes the previously-dead
        # ``revision_index`` parameter live (D3). The EFFECTIVE index, not the caller's
        # raw one, so a nested pass cannot re-publish the outer pass's number (si4).
        ectx.revision_attempt = effective_index

        new_analyze_output = ""

        try:
            for sub_spec, sub_index in (
                (specify_spec, index - 2),
                (plan_spec, index - 1),
                (analyze_spec, index),
            ):
                # Abort if the run was cancelled by the user during the sub-pipeline.
                if cancel_event and cancel_event.is_set():
                    yield {"type": "_gate_rejected"}
                    return
                current_state = self._state_machine.get_state(pipeline_run_id)
                if current_state in ("cancelled", "failed", "diverted"):
                    yield {"type": "_gate_rejected"}
                    return

                # Drop the previous result entry for this agent so the re-run appends
                # a fresh one (same pattern as _gate_redo's results.pop()).
                results[:] = [r for r in results if r.get("agent_id") != sub_spec.id]

                # Publish the prior artifact for the SPECIFY dispatch only. Identity
                # against the spec object, not an id string (INV-1) — this is the
                # no-leak guarantee: plan and analyze compose without the block.
                ectx.spec_revision_prior_artifact = (
                    prior_artifact if sub_spec is specify_spec else ""
                )

                # Re-run the agent — reuses the FULL _run_agent path (INV-12).
                async for event in self._run_agent(
                    spec=sub_spec,
                    index=sub_index,
                    ordered_agents=ordered_agents,
                    user_message=user_message,
                    sandbox=sandbox,
                    pipeline_run_id=pipeline_run_id,
                    pipeline_type=pipeline_type,
                    planning_context=planning_context,
                    attached_skills=attached_skills,
                    attached_hooks=attached_hooks,
                    model_id=model_id,
                    results=results,
                    cancel_event=cancel_event,
                    ectx=ectx,
                ):
                    # Propagate all events except internal gate signals upstream.
                    evt_type = event.get("type", "")
                    if evt_type in ("_gate_rejected", "_gate_edited", "_gate_redo",
                                    "_gate_update_specs", "_revision_analyze_output"):
                        # If a nested gate signals rejection, propagate it and abort.
                        if evt_type == "_gate_rejected":
                            yield event
                            return
                        # Other internal signals (nested redo / update_specs) from
                        # sub-pipeline agents are silently consumed — the review gate
                        # on specify/plan is not expected during a revision cycle
                        # (gate_agent_ids controls this at the run level).
                    else:
                        yield event

                # Capture the new analyze output from results after the analyze run.
                if sub_spec is analyze_spec:
                    for r in reversed(results):
                        if r.get("agent_id") == analyze_spec.id:
                            new_analyze_output = r.get("output", "")
                            break

        finally:
            # RESTORE, don't clear (si4). Consume-once still holds: this finally covers
            # the cancel / error / early-return paths, so neither injection nor the
            # :rev{N} thread suffix can outlive the pass. But an INNER pass must hand the
            # outer pass back the index and report it was running with, not zero them
            # while the outer pass is still on the stack. At the OUTER level the saved
            # values are ""/""/0, so this is byte-equivalent to the previous
            # unconditional clear (INV-3 dormancy).
            # ``revision_high_water`` is deliberately NOT restored — that is the point.
            ectx.spec_revision_context = _saved_context
            ectx.spec_revision_prior_artifact = _saved_prior
            ectx.revision_attempt = _saved_attempt

        # Emit internal signal carrying the new analysis text so the gate consumer
        # can re-open the gate with the correct output.
        yield {"type": "_revision_analyze_output", "output": new_analyze_output}

    async def _consume_update_specs(
        self,
        *,
        gate_event,
        spec,
        index: int,
        ordered_agents: list,
        user_message: str,
        sandbox,
        pipeline_run_id: str,
        pipeline_type: str,
        planning_context: dict,
        attached_skills,
        attached_hooks,
        model_id,
        results: list[dict],
        cancel_event,
        ectx,
        revision_index: int,
    ) -> AsyncGenerator[dict, None]:
        """The ONE ``_gate_update_specs`` consumer, shared by all three gate branches.

        There are three places a gate can hand back ``_gate_update_specs`` — the RESUME-17
        restart-parked re-entry gate, the pending-re-open short-circuit, and the live
        post-stream gate. They previously held two near-identical 50-line copies of this
        logic (differing only in a ``logger.info``) and one broken stub. This is the single
        implementation (INV-12): after si4 exactly ONE
        ``_run_spec_revision_sub_pipeline`` call site exists in this file.

        Writes the content-free audit row, drives the sub-pipeline, forwards its events
        upstream, and finishes with ONE terminal ``_update_specs_done`` sentinel telling the
        caller whether the pass was cancelled. That sentinel is INTERNAL — every call site
        consumes it and it must never reach the wire.
        """
        analysis_report = gate_event.get("analysis_report") or ""

        # A2 (RESUME-17): best-effort, content-free update_specs audit row — SYMMETRIC with
        # the _gate_redo audit, so a post-restart spec_revision_attempt is derivable from
        # the durable gate_events (else the sub-pipeline thread ids could collide, the P23
        # replay class). Dormant on goldens (they never update_specs). Never aborts the run.
        _us_runner = getattr(ectx, "runner", None)
        if _us_runner is not None and hasattr(_us_runner, "record_gate_event"):
            try:
                await _us_runner.record_gate_event(
                    spec.id, "human", "update_specs",
                    {"has_report": bool(analysis_report)},
                )
            except Exception:  # noqa: BLE001 — audit never aborts a run
                logger.debug(
                    "update_specs audit row failed for agent %s (ignored)",
                    spec.id, exc_info=True,
                )
        logger.info(
            "Spec revision sub-pipeline: pipeline=%s attempt=%d",
            pipeline_run_id, revision_index,
        )

        # Run specify → plan → analyze with the analysis report injected as revision
        # context, collecting the new analyze output for the re-opened gate.
        new_analysis_output = ""
        async for sub_event in self._run_spec_revision_sub_pipeline(
            spec=spec,
            index=index,
            ordered_agents=ordered_agents,
            user_message=user_message,
            sandbox=sandbox,
            pipeline_run_id=pipeline_run_id,
            pipeline_type=pipeline_type,
            planning_context=planning_context,
            attached_skills=attached_skills,
            attached_hooks=attached_hooks,
            model_id=model_id,
            results=results,
            cancel_event=cancel_event,
            ectx=ectx,
            analysis_report=analysis_report,
            revision_index=revision_index,
        ):
            if sub_event.get("type") == "_revision_analyze_output":
                # Internal signal carrying the new analysis text
                new_analysis_output = sub_event.get("output", "")
            elif sub_event.get("type") == "_gate_rejected":
                # Stop button fired during the sub-pipeline
                current = self._state_machine.get_state(pipeline_run_id)
                if current not in ("cancelled", "failed", "diverted"):
                    self._state_machine.transition(pipeline_run_id, "cancelled")
                yield {"type": "pipeline_cancelled", "data": {
                    "pipeline_run_id": pipeline_run_id,
                    "reason": "Cancelled during spec revision sub-pipeline",
                }}
                yield {"type": "_update_specs_done", "cancelled": True}
                return
            else:
                yield sub_event

        # Re-open the gate with the new output so the user can Accept or request another
        # revision cycle. The while-loop must NOT re-run this agent, so the new output goes
        # on ectx scratch and the caller breaks: the loop top's pending short-circuit sees
        # the sentinel, skips the model call and jumps straight to the gate.
        ectx.spec_revision_pending_output = new_analysis_output
        yield {"type": "_update_specs_done", "cancelled": False}

    async def _consume_redo(
        self,
        *,
        gate_event: dict,
        spec,
        results: list[dict],
        ectx,
    ) -> tuple[str, str | None, str]:
        """The ONE ``_gate_redo`` consumer, shared by all three gate branches.

        Three places hand back ``_gate_redo`` — the RESUME-17 restart-parked re-entry
        gate, the gate re-opened after a revision pass, and the live post-stream gate.
        They held two near-identical copies and one THIN copy that set only the directive,
        so a redo at the re-opened gate silently lost its ``derived_from`` lineage, left a
        duplicate ``results`` entry and wrote no audit row. This is the single
        implementation (INV-12), mirroring ``_consume_update_specs``.

        Returns the three loop locals the while-loop consumes on its next iteration:
        ``(directive, derived_from, prior_artifact)``. ``redo_attempt`` stays at the call
        site — it is the caller's fresh-thread counter, exactly as
        ``spec_revision_attempt`` is at the ``_consume_update_specs`` call sites.

        **ISS-086.** ``prior_artifact`` is the re-run's SUBJECT: the very output the user
        is asking to amend. It is read off the SAME kind-scoped max-version ref the
        lineage stamp uses — no extra read, and kind-scoped by construction, which matters
        because one producer can write two kinds (``prototype-build`` writes both
        ``html_file`` and ``file_bundle``, so a producer-only lookup would serve the wrong
        document). It is WITHHELD in two cases:

          * **a blank redo** — the FE labels that "leave blank to just regenerate", and
            regenerate-from-scratch is precisely the P23 semantics the ``:redo{N}`` fresh
            thread exists to enforce. Only a non-blank instruction asks for an amendment;
          * **a per-task build dispatch** (``build_task_number`` set) — that dispatch
            already carries a COMPACTED view of the same document, so injecting the full
            artifact on top would double-inject the deliverable.

        Keyed on the generic gate vocabulary + generic scratch only — no agent id, no
        workflow name (SC-001 / INV-1).
        """
        directive = gate_event.get("instructions") or ""
        kind = self._artifact_kind_for(spec)
        cands = [
            r for r in ectx.artifacts.list_by_kind(kind)
            if r.producer_agent == spec.id
        ]
        latest = max(cands, key=lambda r: r.version) if cands else None
        derived_from = latest.id if latest is not None else None

        prior_artifact = ""
        if latest is not None and directive and not (ectx.build_task_number or ""):
            prior_artifact = latest.content or ""

        # Drop the rejected output's results entry (matching agent_id) so the re-run
        # appends a fresh one.
        if results and results[-1].get("agent_id") == spec.id:
            results.pop()

        # T7 (B8): best-effort, content-free redo audit row — written HERE and not in
        # ``_run_review_gate``, which has no ectx. It is what makes a post-restart
        # ``redo_attempt`` derivable from durable evidence (_seed_gate_reentry_attempts),
        # so a re-entered gate cannot mint a colliding ``:redo{N}``. Dormant on the
        # goldens (they never redo). Never aborts the run.
        _runner = getattr(ectx, "runner", None)
        if _runner is not None and hasattr(_runner, "record_gate_event"):
            try:
                await _runner.record_gate_event(
                    spec.id, "human", "redo",
                    {"has_instructions": bool(directive)},
                )
            except Exception:  # noqa: BLE001 — audit never aborts a run
                logger.debug(
                    "redo audit row failed for agent %s (ignored)",
                    spec.id, exc_info=True,
                )
        return directive, derived_from, prior_artifact

    async def _run_review_gate(
        self,
        pipeline_run_id: str,
        agent_id: str,
        agent_name: str,
        output: str,
        redoable: bool = False,
        update_specs_eligible: bool = False,
        artifact_kind: str = "",
        revision_cycle: int = 0,
        revision_in_flight: bool = False,
        cancel_event: asyncio.Event | None = None,
        visit_count: int = 0,
    ) -> AsyncGenerator[dict, None]:
        """Pause the pipeline for human review of an agent's output.

        Emits `review_gate_ready` with the agent's output.
        Waits for the user to call `approve_review` (via WebSocket).
        On approve: yields `review_gate_approved` and continues.
        On reject: yields `_gate_rejected` (internal signal to cancel).
        On edit+approve: yields `_gate_edited` with the new content.
        On redo: yields `_gate_redo` (internal signal to re-run the gated agent).

        ``redoable`` (REDO-GATE F1b) is a GENERIC discriminator stamped on
        ``review_gate_ready.data`` — True ONLY from the inline call site (a
        structural path, NOT a workflow/agent-id literal — SC-001). The FE renders
        the Redo button IFF ``redoable``; a declared/user-composed ``gate:human``
        step (which calls this primitive via ``run_human_gate`` with the default
        ``redoable=False``) therefore shows NO Redo button. It is added to
        ``_VOLATILE_STRIP_KEYS`` so the goldens stay byte-identical (INV-3).

        ``update_specs_eligible`` / ``artifact_kind`` (SC-001 / KAN-101) mirror the
        ``redoable`` pattern EXACTLY: a generic, name-free discriminator stamped True
        ONLY from the inline analyze/spec call site — derived STRUCTURALLY from
        ``_artifact_kind_for(spec)`` (spec-authoring kinds → eligible), NEVER a
        workflow/agent-id string literal. The FE drives the "Update the Specs"
        affordance IFF ``update_specs_eligible`` instead of matching a leaked
        agent-id string. A declared/user gate defaults to
        ``update_specs_eligible=False`` (as ``redoable`` defaults False). Both keys
        are added to ``_VOLATILE_STRIP_KEYS`` so the goldens stay byte-identical.

        ``revision_cycle`` / ``revision_in_flight`` (ISS-052) are the same pattern once
        more: the per-FIRING discriminator. ``gate_key`` is ``f"{run_id}:{agent_id}"`` — it
        names a gate SLOT, so the analyze gate re-run inside a revision pass and the gate
        re-opened after that pass returns are indistinguishable on the wire (same key, same
        output bytes, milliseconds apart). Publishing ``(cycle, in_flight)`` makes every
        firing identifiable: ``(0, False)`` before any revision, ``(N, True)`` inside pass
        N, ``(N, False)`` at pass N's re-opened gate. Both come from generic run scratch
        (see ``_stamp_revision_marks``) — no workflow or agent name — and both default to the
        no-revision value on the declared/user gate path, exactly as ``redoable`` does.

        ``visit_count`` (R-08) folds a step's loop-revisit count into ``gate_key`` itself:
        without it, a step re-entered via a ``route.loop_back_to`` jump collides with its
        own prior firing on the SAME gate_key (the review-event/response store is keyed on
        this string). Callers pass ``ectx.step_visit_counts.get(agent_id, 0)`` — 0 for a
        step's first/only firing, matching every workflow that never declares ``route:``.
        """
        gate_key = f"{pipeline_run_id}:{agent_id}:{visit_count}"

        # Arm the event BEFORE emitting so a fast response doesn't miss it
        event = await self._store.get_review_event(gate_key)
        event.clear()

        # Guard: if the run is already in a terminal state (e.g. user rejected
        # a previous gate), don't open another gate — just signal rejection.
        current_state = self._state_machine.get_state(pipeline_run_id)
        if current_state in ("cancelled", "failed", "diverted"):
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
                # REDO-GATE F1b: generic FE fence — True only from the inline call
                # site (stripped by _VOLATILE_STRIP_KEYS so the goldens stay byte-id).
                "redoable": redoable,
                # SC-001 / KAN-101: generic name-free update-specs discriminator —
                # True only from the inline analyze/spec call site (derived from
                # _artifact_kind_for, never an agent-id literal). Both keys are
                # stripped by _VOLATILE_STRIP_KEYS so the goldens stay byte-id.
                "update_specs_eligible": update_specs_eligible,
                "artifact_kind": artifact_kind,
                # ISS-052: the per-FIRING discriminator. gate_key names a gate SLOT, so
                # without these two the in-pass and re-opened analyze gates are identical
                # on the wire while carrying opposite affordances. Also stripped by
                # _VOLATILE_STRIP_KEYS (INV-3).
                "revision_cycle": revision_cycle,
                "revision_in_flight": revision_in_flight,
                "timestamp": _now(),
            },
        }

        # Loop, because ONE gate firing may consume more than one response: an
        # ineligible ``update_specs`` (ISS-053, below) is refused and the gate goes back
        # to waiting. Every other action still resolves the gate on the first response.
        while True:
            # Wait for user response, but stop immediately if the pipeline is
            # cancelled (Stop button). KAN-100: without this check, cancel_event.set()
            # is observed at the next pre-agent step (engine.py:1842) but the gate
            # stays blocked here indefinitely, allowing a subsequent Redo to unblock
            # the cancelled pipeline and resume agent execution.
            if cancel_event is not None:
                # Race: gate event set by approve_review vs cancel event set by Stop.
                gate_task = asyncio.ensure_future(event.wait())
                cancel_task = asyncio.ensure_future(cancel_event.wait())
                done, pending = await asyncio.wait(
                    {gate_task, cancel_task},
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for p in pending:
                    p.cancel()
                if cancel_task in done and gate_task not in done:
                    # Cancel fired before the user responded — bail out.
                    logger.info(
                        "Review gate cancelled: pipeline=%s agent=%s — cancel_event set",
                        pipeline_run_id, agent_id,
                    )
                    yield {"type": "_gate_rejected"}
                    return
            else:
                # No cancel_event available — plain wait (safe for declared-gate path
                # which does not receive cancel_event from the dispatch loop).
                await event.wait()

            response = await self._store.get_review_response(gate_key)
            approved = response.get("approved", True) if response else True
            edited_content = response.get("edited_content") if response else None
            action = response.get("action", "approve") if response else "approve"
            instructions = response.get("instructions") if response else None

            # REDO-GATE: a "redo" action re-runs the gated agent in place (a fresh model
            # call), then re-pauses at the SAME gate. Keyed on the GENERIC ``action``
            # discriminator (no workflow/agent literal — SC-001). Emit the internal
            # ``_gate_redo`` signal (mirroring ``_gate_rejected``: consumed by the
            # inline consumer, never forwarded to the wire) and return; the consumer's
            # while-loop re-runs the agent. The declared-path consumers (human/approval
            # gate) CONSUME this signal safely (T-human) — never PASS, never leak.
            if action == "redo":
                self._state_machine.transition(pipeline_run_id, "generating")
                logger.info(
                    "Review gate redo: pipeline=%s agent=%s has_instructions=%s",
                    pipeline_run_id, agent_id, bool(instructions),
                )
                yield {"type": "_gate_redo", "instructions": instructions or ""}
                return

            # KAN-101: "update_specs" action — trigger spec revision sub-pipeline that
            # re-runs the preceding specify + plan + analyze agents with the analysis
            # report as additional context, then re-opens this same gate with the new
            # analysis output. Keyed on the GENERIC action discriminator (SC-001 / INV-1).
            if action == "update_specs":
                # ISS-053: the eligibility verdict this firing PUBLISHED on
                # ``review_gate_ready`` is BINDING, not advisory. ``gate_key`` names a
                # gate SLOT, not a firing (see above), so replaying a legitimate earlier
                # click on the same agent lands on whichever firing is armed now — no
                # crafting required. Unenforced, that ran the sub-pipeline at gates the
                # rule excludes: positionally-chosen targets mean the same action means
                # "re-run specify/plan/analyze" at one gate and "re-run
                # plan/analyze/build" at the next, and below index 2 it revises NOTHING
                # while still blanking the agent's output.
                #
                # The degrade is KEEP WAITING. Approving would be fail-open on a HITL
                # gate — what the Phase-23 F1a redo defence exists to prevent, and
                # against WR-07's fail-closed rule; rejecting would cancel the user's
                # run, a semantic change nobody asked for. So the gate re-arms and every
                # legitimate action stays available. This is the LAST line of defence:
                # the ingresses reject it earlier with a 409
                # (``run_engine._review_gate_advertises_update_specs``), but that check
                # reads the durable log and abstains when the row is missing — it is
                # allowed to abstain only because this one never does.
                if not update_specs_eligible:
                    logger.warning(
                        "Review gate update_specs REFUSED: pipeline=%s agent=%s "
                        "kind=%s — this firing published update_specs_eligible=False; "
                        "gate stays open (ISS-053)",
                        pipeline_run_id, agent_id, artifact_kind,
                    )
                    event.clear()
                    continue
                self._state_machine.transition(pipeline_run_id, "generating")
                analysis_report = instructions or ""
                logger.info(
                    "Review gate update_specs: pipeline=%s agent=%s has_report=%s",
                    pipeline_run_id, agent_id, bool(analysis_report),
                )
                yield {"type": "_gate_update_specs", "analysis_report": analysis_report}
                return

            break

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

            db = SessionLocal()
            try:
                stuck_runs = (
                    db.query(WorkflowRun)
                    .filter(WorkflowRun.status.in_(NON_TERMINAL_RUN_STATUSES))
                    .all()
                )
                restored = 0
                resumed = 0
                abandoned = 0
                for wr in stuck_runs:
                    # WorkflowRun.id is the single run identifier (the
                    # pipeline_run_id column was dropped in migration 0013).
                    pipeline_run_id = wr.id
                    if not pipeline_run_id:
                        continue
                    # ── Three-way startup classification (RESUME-04 / D-08) ──────
                    # (a) waiting_for_user → re-arm its resume event (UNCHANGED — the
                    #     user's next answer sets the asyncio.Event the run is paused on).
                    # (b) a RESUMABLE in-flight run — a compiled-manifest run WITH
                    #     persisted step state (durable run_events / artifact_refs /
                    #     wave_runs) — is auto-resumed IN-PROCESS: stamp an additive
                    #     resume marker BEFORE creating the driver task (the double-drive
                    #     guard, Pitfall 3 / T-12-03-DOUBLEDRIVE — a crash mid-resume is
                    #     itself resumable and the run is never driven twice), then
                    #     asyncio.create_task(self.resume_run(run_id)).
                    # (c) anything ELSE → the WR-05 abandoned→failed path VERBATIM (a
                    #     stateless legacy run with no durable step state has nothing to
                    #     resume FROM; re-arming it would leave it stuck with no driver).
                    if wr.status == "waiting_for_user":
                        # ── branch (a): waiting_for_user (RESUME-17 re-arm, PINNED A1) ─
                        # KAN-88 was the RESTORATION-in-reverse: it FAILED every paused
                        # run because a restart destroyed the in-memory waiter. The fix
                        # is not "don't fail" — it is "recreate the waiter". So a
                        # COMPILABLE waiting_for_user run is NEVER auto-failed: it is
                        # either RE-ARMED (a durable open gate + resumable-in-flight →
                        # recreate the store waiter and spawn the re-arm driver BEFORE
                        # leaving waiting_for_user) or left PARKED untouched (no durable
                        # open gate → harmless: D-14g surfaces nothing without a durable
                        # review_gate_ready). ONLY an UNCOMPILABLE / stateless-legacy run
                        # (compile_for_run RAISES) keeps the byte-unchanged WR-05-clarify
                        # fail. The STATUS decision gates on compilability alone (the
                        # KAN-88 anchor seeds a compilable row with NO durable events);
                        # the re-arm DRIVER additionally requires a derivable open gate
                        # AND _is_resumable_in_flight.
                        _compilable = True
                        try:
                            compile_for_run(wr.type)
                        except Exception:  # noqa: BLE001 — uncompilable/legacy
                            _compilable = False

                        if not _compilable:
                            # Uncompilable / stateless legacy → WR-05-clarify fail VERBATIM.
                            prior_status = wr.status
                            wr.status = "failed"
                            wr.error = (
                                "Run abandoned: backend restarted while waiting for "
                                "user clarification (WR-05-clarify). The clarify gate "
                                "cannot be resumed after a backend restart — please "
                                "start a new run."
                            )
                            abandoned += 1
                        else:
                            # Compilable → derive the durable open gate (owner-scoped,
                            # mirroring _is_resumable_in_flight's owner derivation).
                            try:
                                _owner_id = (
                                    wr.owner_id or wr.user_id
                                    or f"anon:{wr.session_id or wr.id}"
                                )
                                _gate_store = ScopedStore(
                                    owner_id=_owner_id, workspace_id=wr.workspace_id
                                )
                                _rows = await _gate_store.read_events(wr.id, after_seq=0)
                            except Exception:  # noqa: BLE001 — no durable substrate
                                _rows = []
                            open_kind, open_gate_key = derive_open_gate(_rows)

                            if open_kind in ("review", "questionnaire") and (
                                await self._is_resumable_in_flight(wr)
                            ):
                                # ── ARM-THEN-CLASSIFY (fail-safe) ──────────────────────
                                # Recreate the store waiter FIRST, then spawn the re-arm
                                # driver, so a live waiter + driver exist BEFORE the row is
                                # left waiting_for_user (never a phantom-live hung row). ANY
                                # exception in this block fail-safes to the WR-05 fail path.
                                try:
                                    import asyncio as _asyncio

                                    if open_kind == "review" and open_gate_key:
                                        _evt = await self._store.get_review_event(
                                            open_gate_key
                                        )
                                    else:
                                        _evt = await self._store.get_resume_event(
                                            pipeline_run_id
                                        )
                                    _evt.clear()  # armed == created + not set (KAN-94)

                                    # 46-05: register the run's live queue at the SAME
                                    # synchronous site as the driver task, BEFORE
                                    # create_task (idempotent). Best-effort + dormant.
                                    if self._resume_register_queue is not None:
                                        try:
                                            self._resume_register_queue(pipeline_run_id)
                                        except Exception as _q_exc:  # noqa: BLE001
                                            logger.warning(
                                                "re-arm queue registration failed for "
                                                "%s: %s",
                                                pipeline_run_id, _q_exc,
                                            )
                                    # Spawn the DISTINCT re-arm driver (NOT resume_run —
                                    # the KAN-88 spy; the driver ≠ resume_run is what keeps
                                    # the anchor assertion holding once the review path is
                                    # live). Status stays waiting_for_user.
                                    _rearm_task = _asyncio.create_task(
                                        self._rearm_gate_run(pipeline_run_id)
                                    )
                                    if self._resume_register_task is not None:
                                        try:
                                            self._resume_register_task(
                                                pipeline_run_id, _rearm_task
                                            )
                                        except Exception as _reg_exc:  # noqa: BLE001
                                            logger.warning(
                                                "re-arm task registration failed for "
                                                "%s: %s",
                                                pipeline_run_id, _reg_exc,
                                            )
                                    restored += 1
                                except Exception as _arm_exc:  # noqa: BLE001 — fail-safe
                                    logger.warning(
                                        "branch (a) re-arm failed for %s: %s — falling "
                                        "back to WR-05 fail",
                                        pipeline_run_id, _arm_exc,
                                    )
                                    wr.status = "failed"
                                    wr.error = (
                                        "Run abandoned: backend restarted while waiting "
                                        "for user clarification (WR-05-clarify). The "
                                        "clarify gate cannot be resumed after a backend "
                                        "restart — please start a new run."
                                    )
                                    abandoned += 1
                            # else: compilable but no derivable open gate OR not
                            # resumable-in-flight (the KAN-88 no-events row) → leave
                            # wr.status waiting_for_user, spawn nothing (harmless park).
                    elif await self._is_resumable_in_flight(wr):
                        # ── branch (b): resumable in-flight → auto-resume in-process ─
                        # Stamp the additive ``run_resuming`` marker FIRST (the
                        # double-drive guard). An additive EVENT (not a new status
                        # value) keeps the NON_TERMINAL list + the state machine
                        # untouched (Open Q2). Then spawn the in-process driver.
                        await self._stamp_resume_marker(wr)
                        import asyncio as _asyncio

                        # D9 (KAN-139): admission-control wrapper — limit concurrent
                        # in-flight resume drivers so N non-terminal runs at restart
                        # do NOT fire N simultaneous Bedrock calls (saturating the
                        # checkpointer pool and the Bedrock concurrency limit). Uses a
                        # per-restore Semaphore (lazily created) + a time-based stagger
                        # between batches. The port is bound (lifespan yield) BEFORE
                        # this method returns, so tasks are created here but their
                        # Bedrock calls are staged after the healthcheck passes.
                        # Gate-parked runs NEVER hold the semaphore (resume_run only
                        # acquires it around the actual model call, not the whole
                        # lifespan), so this cannot deadlock.
                        if not hasattr(self, "_restore_sem") or self._restore_sem is None:
                            from app.core.config import settings as _cfg
                            self._restore_sem = _asyncio.Semaphore(
                                _cfg.RESTORE_ADMISSION_CONCURRENCY
                            )
                            self._restore_batch_count = 0

                        _restore_sem = self._restore_sem
                        _batch_idx = self._restore_batch_count
                        _stagger_s: float
                        try:
                            from app.core.config import settings as _cfg2
                            _stagger_s = _cfg2.RESTORE_ADMISSION_STAGGER_SECONDS
                            _concurrency = _cfg2.RESTORE_ADMISSION_CONCURRENCY
                        except Exception:
                            _stagger_s = 15.0
                            _concurrency = 4
                        self._restore_batch_count += 1
                        _batch_num = self._restore_batch_count

                        async def _admitted_resume(
                            _run_id: str = pipeline_run_id,
                            _sem: "_asyncio.Semaphore" = _restore_sem,
                            _batch: int = _batch_num,
                            _stagger: float = _stagger_s,
                            _conc: int = _concurrency,
                        ) -> None:
                            # Stagger: wait (batch_number // concurrency) * stagger_s
                            # before acquiring the semaphore so consecutive batches
                            # start RESTORE_ADMISSION_STAGGER_SECONDS apart.
                            _wait = (_batch // _conc) * _stagger
                            if _wait > 0:
                                await _asyncio.sleep(_wait)
                            async with _sem:
                                await self.resume_run(_run_id)

                        # ── WR-02: register the run's LIVE queue at the SAME
                        # synchronous site as the driver task, BEFORE
                        # create_task. resume_run registers the queue again
                        # only after several awaited DB round-trips (run row,
                        # agent resolution, resume offset, durable-tail seq);
                        # a client reconnecting in that window saw a task with
                        # NO queue → _has_live_task False → pipeline_reconnected
                        # {live:false, status non-terminal} with no FE retry —
                        # the UAT Gap 2 "running forever" hang confined to a
                        # race window (most likely right after a restart, when
                        # every open client reconnects during this scan). The
                        # bridge's _get_or_create_queue is idempotent, so the
                        # later registration inside resume_run returns this
                        # same queue. Best-effort + dormant when unset.
                        if self._resume_register_queue is not None:
                            try:
                                self._resume_register_queue(pipeline_run_id)
                            except Exception as _q_exc:  # noqa: BLE001
                                logger.warning(
                                    "resume queue registration failed for "
                                    "%s: %s",
                                    pipeline_run_id, _q_exc,
                                )
                        _resume_task = _asyncio.create_task(
                            _admitted_resume()
                        )
                        # ── 12-09 Gap 2a: register the resume DRIVER task in the
                        # WS pipeline registry via the injected bridge so a
                        # reconnect during the resumed run sees a live task and
                        # takes the live-attach branch. Best-effort + dormant
                        # when unset (offline/no-WS — byte-identical).
                        if self._resume_register_task is not None:
                            try:
                                self._resume_register_task(
                                    pipeline_run_id, _resume_task
                                )
                            except Exception as _reg_exc:  # noqa: BLE001
                                logger.warning(
                                    "resume task registration failed for %s: %s",
                                    pipeline_run_id, _reg_exc,
                                )
                        resumed += 1
                    else:
                        # ── branch (c): WR-05 abandoned→failed VERBATIM ──────────
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
                    "auto-resumed %d in-flight run(s), marked %d abandoned run(s) "
                    "failed, in %.2fs",
                    restored, resumed, abandoned, elapsed,
                )
            finally:
                db.close()
        except Exception as exc:
            logger.warning("restore_non_terminal_runs failed: %s", exc)

    async def _rearm_gate_run(self, run_id: str) -> None:
        """Re-arm DRIVER for a restart-parked gate run (RESUME-17, branch (a)).

        Spawned by ``restore_non_terminal_runs`` branch (a) AFTER the store waiter is
        re-armed, for a run left ``waiting_for_user`` with a durable open gate. It is a
        DISTINCT coroutine from ``resume_run`` on purpose: branch (a) must NEVER spawn
        ``resume_run`` directly (the KAN-88 anchor spies it), so keeping the driver a
        separate method is what holds that assertion once the review path is live.

        This plan (49-01) lands the SKELETON: for a review-open run it delegates the
        actual gate re-entry to ``resume_run`` (the offset-override that re-enters AT the
        gate lands in 49-02); a clarify-open run is a no-op stub here (the clarify replay
        driver lands in 49-03). WR-01: EVERY exit path drops the live-registry entries the
        restore ``create_task`` site registered (idempotent, mirroring ``resume_run``'s
        ``finally``) so a parked run never leaks a queue/task registration.
        """
        try:
            from app.models.database import SessionLocal
            from app.models.workflow import WorkflowRun

            db = SessionLocal()
            try:
                wr = db.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
                if wr is None:
                    logger.warning(
                        "_rearm_gate_run(%s): no workflow_runs row — skipping", run_id
                    )
                    return
                owner_id = (
                    wr.owner_id or wr.user_id or f"anon:{wr.session_id or run_id}"
                )
                workspace_id = wr.workspace_id
            finally:
                db.close()

            try:
                store = ScopedStore(owner_id=owner_id, workspace_id=workspace_id)
                rows = await store.read_events(run_id, after_seq=0)
            except Exception:  # noqa: BLE001 — no durable substrate → nothing to drive
                rows = []
            open_kind, _open_gate_key = derive_open_gate(rows)

            if open_kind == "review":
                # Review re-entry (49-02): resume_run re-enters the SINGLE per-step dispatch
                # loop; the open-gate offset override + gate_reentry sentinel re-open the gate
                # AT the gated step (model-skip). INV-12 — no forked path.
                await self.resume_run(run_id)
            elif open_kind == "questionnaire":
                # Clarify re-entry (49-03, PINNED A5): the REPLAY driver re-drives from
                # planning with the durable open round replayed (no LLM re-gen), re-enters
                # the store wait, and — on answers via the unchanged POST /answers seam —
                # proceeds into the normal dispatch. DISTINCT from resume_run (the KAN-88
                # twin asserts resume_run is never driven for a clarify re-arm).
                await self._replay_clarify_run(run_id)
        finally:
            # WR-01: drop the queue/task entries registered at the restore create_task
            # site (idempotent). Dormant when the hooks are None (offline / goldens).
            self._fire_resume_cleanup(run_id)
            if self._resume_live_ectx_unregister is not None:
                try:
                    self._resume_live_ectx_unregister(run_id)
                except Exception:  # noqa: BLE001 — teardown never masks the outcome
                    logger.warning(
                        "_rearm_gate_run(%s): live_ectx_unregister failed", run_id,
                        exc_info=True,
                    )

    async def _is_resumable_in_flight(self, wr) -> bool:
        """Classify a non-terminal run as RESUMABLE in-flight (branch b) or not (D-08).

        A run is resumable in-flight iff it is a compiled-manifest run WITH persisted
        step state — i.e. the durable substrate carries evidence the run made progress
        before the restart: at least one ``run_events`` row OR one ``artifact_refs`` row
        OR one ``wave_runs`` row, read OWNER-SCOPED (the run's owner). A run with NO
        durable step state has nothing to resume FROM (a stateless legacy run, or a run
        that died before its first persisted event) → it falls to the WR-05 path
        (branch c). Best-effort: the offline harness (no DB) → ``False`` (every test run
        keeps the legacy WR-05 path, so the 5 characterization snapshots are unchanged —
        the resume branch is dormant for existing test runs, Q-12-03).
        """
        # The run's pipeline_type must compile to a manifest (a non-compilable / unknown
        # workflow cannot be re-driven through _execute_impl).
        try:
            compile_for_run(wr.type)
        except Exception:  # noqa: BLE001 — unknown/uncompilable pipeline → not resumable
            return False
        owner_id = wr.owner_id or wr.user_id or f"anon:{wr.session_id or wr.id}"
        try:
            store = ScopedStore(owner_id=owner_id, workspace_id=wr.workspace_id)
            # Any persisted step state ⇒ resumable. read_events(after_seq=0) returns the
            # whole durable tail; a single row is enough evidence.
            if await store.read_events(wr.id, after_seq=0):
                return True
            if await store.tree(wr.id):
                return True
            if await store.read_wave_runs(wr.id):
                return True
        except Exception:  # noqa: BLE001 — no durable substrate (offline) → not resumable
            return False
        return False

    async def _stamp_resume_marker(self, wr) -> None:
        """Persist an additive ``run_resuming`` event BEFORE the driver task (Pitfall 3).

        The double-drive guard (T-12-03-DOUBLEDRIVE): the marker is written to the
        durable ``run_events`` log so a crash DURING resume is itself resumable and the
        run is never driven twice. An additive EVENT (not a new status value) leaves the
        NON_TERMINAL list + the state machine untouched (Open Q2). The marker rides the
        SAME owner-scoped append path as every other event; best-effort (a persist
        failure logs and proceeds — the resume still drives, just without the audit
        marker). The ``seq`` is the next durable seq for the run (read + 1).

        12-09: the marker's workspace is the run's RECOVERED real workspace_id
        (``_recover_workspace_id`` — the run_events-sourced value the sink wrote
        under), NOT ``wr.workspace_id``: the WS-path workflow_runs row carried a
        NULL workspace, so the marker's ``append_event`` hit the run_events
        NOT NULL constraint (IntegrityError) and the marker was LOST on every
        in-process auto-resume. A resumable run (branch b) always HAS durable
        rows, so recovery is the normal path; a None recovery (no durable row)
        falls through to the existing best-effort except — never an inserted
        NULL, the same logged-warning degrade as today.

        DB-001 (task.md R-02): the seq allocation used to be a single unretried
        read-``max(seq)+1``-then-``append_event`` — exactly the race
        :meth:`agents.authz.ScopedStore.append_event_next_seq` exists to close (a
        concurrent resume attempt, or the run's own event sink, can compute the
        same ``seq`` first and this insert loses silently under the old bare
        ``except Exception: log and swallow``). This now allocates through that
        same optimistic-retry-on-``IntegrityError`` method the chat lane already
        uses, so a raced seq is re-derived and retried (bounded, 8 attempts)
        instead of being dropped. A retry-exhaustion failure is a real,
        unresolved conflict (not a transient "no durable substrate" case) and is
        re-raised — the marker is best-effort only for genuinely missing
        durable state, never for a swallowed write collision.
        """
        # Capture the row's scalars UP FRONT so the best-effort except never
        # touches the ORM object (a lazy-attribute load on a session a failed
        # flush already poisoned would raise INSIDE the handler).
        run_id = wr.id
        prior_status = wr.status
        owner_id = wr.owner_id or wr.user_id or f"anon:{wr.session_id or run_id}"
        try:
            workspace_id = await self._recover_workspace_id(owner_id, run_id)
            store = ScopedStore(owner_id=owner_id, workspace_id=workspace_id)
            await store.append_event_next_seq(
                run_id,
                event_id=str(uuid.uuid4()),
                type="run_resuming",
                payload_json={
                    "pipeline_run_id": run_id,
                    "prior_status": prior_status,
                    "reason": "backend_restart_in_process_resume",
                },
            )
        except RuntimeError as exc:
            # append_event_next_seq exhausted its retry budget — a REAL, surfaced
            # seq conflict (task.md R-02 oracle: "no swallowed write, deterministic
            # retry or surfaced terminal error"). Still degrades the marker itself
            # (it is audit-only) but does not hide the conflict as a generic
            # "no durable substrate" case.
            logger.error(
                "_stamp_resume_marker(%s) exhausted seq-allocation retries: %s",
                run_id, exc,
            )
        except Exception as exc:  # noqa: BLE001 — the marker is best-effort audit
            logger.warning("_stamp_resume_marker(%s) failed: %s", run_id, exc)

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
        cancel_event: asyncio.Event | None = None,
        milestone_sink=None,
        live_ectx_register=None,
        live_ectx_unregister=None,
    ) -> None:
        """Handle a revision request (FR-014) — real revision-pipeline dispatch.

        Retrieves the original Artifact, version history, and instruction as
        three separate structured inputs (NOT concatenated), composes them into
        the revision context, then dispatches the registry's revision pipeline
        (``get_pipeline_agents(<derived WR-06 alias>)``) through the normal
        ``execute()`` chokepoint — real agents on the deepagents runtime
        (INV-13), every event stamped (seq/event_id) and persisted to
        ``run_events`` by execute() itself (PERSIST-03/SAFE-03). The final
        REVISED deliverable is then persisted under the exact target kind with
        ``derived_from`` so a revision-of-revision resolves it via FR-014
        chain link 1.

        Cross-run reads of the PARENT run's artifacts go through the owner-scoped
        persisted ``ScopedStore`` against ``artifact_refs`` (the per-run in-memory
        ArtifactGraph CANNOT serve cross-run). ``assert_owns(parent_run_id)`` is
        called ABOVE the reads (T-5-SEED): a caller who does not own the parent run
        gets ``PermissionError`` — never another owner's artifacts. For a valid
        same-owner revision the owner-scoped reads return the SAME artifacts the
        thin store returned → INV-3 byte-identity preserved.

        Raises ValueError for invalid inputs (empty instruction, missing artifact,
        falsy owner_id, unmapped target type).
        """
        if not instruction or not instruction.strip():
            raise ValueError("Revision instruction must not be empty.")

        # IN-01 / AUTHZ-03: a real owner principal is REQUIRED. The signature keeps
        # a keyword default for back-compat, but owner_id threads to execute() as
        # user_id (the run principal every scoped write/stamp derives from) and to
        # the cross-run ScopedStore reads below — a falsy owner would encode the
        # precondition in a downstream ``write_ref`` ValueError instead of failing
        # loud at the seam. Mirror ClarifyEngine.run's falsy-owner guard so the
        # contract is explicit.
        if not owner_id:
            raise ValueError(
                "_handle_revision requires a real owner_id (AUTHZ-03)"
            )

        # Owner-scoped persisted store for the cross-run parent reads + revision
        # write. owner_id is the run owner (user.id at the WS call site). No
        # workspace_id is threaded — the cross-run reads below are
        # visibility-scoped (the parent's artifacts are written
        # visibility="workspace" by the producer writes, so they resolve
        # through the owner+visibility filter for the same owner without a
        # workspace match), and the post-dispatch lineage write stamps the
        # parent artifact's workspace (``original.workspace_id``) on the ref
        # itself. The dispatched execute() run mints the revision run's OWN
        # workspace, calls set_run_scope, and arms the run-events sink at its
        # chokepoint (INV-12 — no duplicate stamping/persist path here).
        store = ScopedStore(owner_id=owner_id)

        # T-5-SEED: assert the caller owns the parent run BEFORE any cross-run read.
        # A cross-owner caller raises PermissionError (never reads another owner's
        # artifacts); an absent/TTL-swept parent returns None (same-owner degrade).
        await store.assert_owns(parent_run_id)

        # Retrieve the original artifact (latest by version asc) — owner-scoped.
        #
        # F2 (13-05) — FR-014 fallback lookup chain. The FE sends
        # ``target_artifact_type`` values (DashboardLayout.tsx:388-403) that no
        # producer write ever persists: run-path kinds are the _AGENT_KIND_MAP
        # values + summary/planning_context/clarifications + the 13-05 completion
        # "deliverable" ref. Resolve the parent original deterministically:
        #   link 1 — exact target kind (revision-of-revision + any future
        #            exact-kind producer; preserves the existing exact-kind tests)
        #   link 2 — the kind="deliverable" completion ref (every NEW run —
        #            written by the execute() terminal block)
        #   link 3 — legacy kind="summary" (pre-fix completed runs: the final
        #            agent's output lands as summary via the _AGENT_KIND_MAP
        #            fallback)
        # All links empty → the FR-014 ValueError, byte-unchanged. Latest-by-
        # version semantics stay ``_refs[-1]``. SC-001: the chain introduces only
        # the generic kinds "deliverable"/"summary" — no workflow-name literal;
        # target_artifact_type is data passing through.
        _refs = await store.list_refs(parent_run_id, kind=target_artifact_type)
        _resolved_kind = target_artifact_type
        if not _refs:
            _refs = await store.list_refs(parent_run_id, kind="deliverable")
            _resolved_kind = "deliverable"
        if not _refs:
            # IN-06 (13 review fix): a failed agent typed-writes
            # "[Error: {exc}]" under its mapped kind — summary for unmapped
            # agents. On a legacy (pre-13-05) degraded parent whose FINAL
            # agent errored, the latest summary ref is that placeholder, so
            # the unfiltered link-3 read would "resolve" garbage as the
            # revision original instead of raising FR-014. Skip error
            # placeholders; if every summary ref is one, the link stays
            # empty and the FR-014 ValueError fires (byte-unchanged).
            _refs = [
                r
                for r in await store.list_refs(parent_run_id, kind="summary")
                if not r.content.startswith("[Error:")
            ]
            _resolved_kind = "summary"
        original = _refs[-1] if _refs else None
        if original is None:
            raise ValueError(
                f"No artifact of type {target_artifact_type!r} found for run {parent_run_id!r}. "
                "Revision MUST NOT proceed without original context (FR-014)."
            )
        # Live diagnosability (no new WS event — stream parity): name the chain
        # link that resolved the parent original.
        logger.info(
            "FR-014 lookup resolved: target_kind=%r resolved_kind=%r ref=%s parent_run=%s",
            target_artifact_type, _resolved_kind, original.id, parent_run_id,
        )

        # Version history = the owner-scoped refs list of WHICHEVER chain link
        # matched above (avoid a second query) — not unconditionally the
        # exact-kind list (F2).
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

        # ── WR-06 (13 review fix): FE-routable revision pipeline_type ───────────
        # The FE sends ``*_output`` artifact KINDS as the revision target
        # (ppt_output / od_ppt_output) but routes pipeline_complete previews on
        # the WORKFLOW revision aliases (ppt_revision / od_ppt_revision /
        # *_revision suffixed types). Emitting
        # ``{target}_revision`` verbatim produced ``ppt_output_revision`` —
        # matched by NO FE branch, so the revision's final_output was never
        # routed to the preview panel. Normalize with a GENERIC suffix
        # transform (no workflow-name literal — SC-001); non-``*_output``
        # targets are unchanged.
        revision_pipeline_type = (
            f"{target_artifact_type.removesuffix('_output')}_revision"
        )

        # ── Real dispatch (Phase 14 / F2): the registry revision pipeline runs
        # through the normal execute() chokepoint. The derived alias resolves the
        # ordered AgentSpec list from the SAME registry source _execute_impl
        # asserts compiled-plan membership against (RESEARCH Pitfall 6) — pass it
        # EXACTLY, never filtered (a plan↔registry mismatch raises RuntimeError
        # mid-dispatch). SC-001: the alias is data-derived above; no
        # workflow-name literal enters the kernel.
        # revision-pipeline-refactor: pass agents=[] so execute() builds the agent
        # roster from the compiled manifest steps via _specs_from_plan(compiled.steps).
        # This is required because prototype-revision-analyzer declares
        # pipeline_type: prototype_revision_analyzer (its own private type) and is
        # therefore NOT in PIPELINE_AGENTS["prototype_revision"] — passing the
        # registry list silently skips step 0 of the manifest.
        # Validate the pipeline is registered (compile_for_run succeeds) as the
        # fail-fast check instead of relying on an empty get_pipeline_agents() result.
        try:
            compile_for_run(revision_pipeline_type)
        except Exception:
            raise ValueError(
                f"No revision pipeline is registered for target_artifact_type "
                f"{target_artifact_type!r} (derived pipeline "
                f"{revision_pipeline_type!r})."
            )
        agents: list = []

        # ── CR-02 (14 review fix): planner-flow pipelines are NOT revision-
        # dispatchable. The derived alias resolves ANY registered ``*_revision``
        # pipeline, but only a ``planner: skip`` manifest can run headless from
        # the revision panel — a ``planner: run`` manifest parks the dispatch at
        # the clarify gate's no-timeout ``await event.wait()`` waiting for a
        # questionnaire round-trip the panel never sends, leaking a permanently
        # stuck background task + a row frozen "revising". Fail fast at the
        # seam instead; the WS layer maps ValueError → revision_validation_error.
        # SC-001: the predicate is the compiled manifest's DATA
        # (``compiled.planner``), never a workflow-name literal — flipping a
        # manifest to ``planner: skip`` makes it dispatchable with no engine
        # edit.
        if compile_for_run(revision_pipeline_type).planner != "skip":
            raise ValueError(
                f"target_artifact_type {target_artifact_type!r} is not "
                f"revision-dispatchable: pipeline {revision_pipeline_type!r} "
                f"requires the planner/clarify flow the revision panel cannot "
                f"drive (manifest declares planner: run)."
            )

        # Forward-and-capture dispatch: every event yielded by execute() arrives
        # ALREADY stamped (seq/event_id) and persisted to run_events at the
        # chokepoint (PERSIST-03/SAFE-03) — forward each one VERBATIM through the
        # RAW caller-supplied sender; never mutate, never re-persist. execute()
        # also mints the revision run's own workspace, calls set_run_scope and
        # records run_capabilities — the former in-method duplicates of all three
        # are deleted (INV-12).
        #
        # od_context=None (settled Phase-14 design wrinkle): no revision agent
        # declares template/design_system injects (pinned executable by
        # test_run_revision_revision_agents_declare_no_template_injects); the
        # 13-06 missing_template_context guard lives only at the run_pipeline WS
        # ingress, which this path never traverses; and the parent deck embedded
        # in revision_context already physically realizes the template.
        # gate_agent_ids=[]: no inter-agent HITL gate on a panel revision — None
        # would fall back to the static gate set.
        final_output: str | None = None
        terminal_failed = False
        async for event in self.execute(
            agents=agents,
            user_message=revision_context,
            pipeline_run_id=pipeline_run_id,
            pipeline_type=revision_pipeline_type,
            # ISS-007 (16-02): thread the cooperative cancel event so the Stop
            # button cancels a running revision through the engine's per-chunk /
            # pre-agent observation → pipeline_cancelled on the forwarded stream.
            cancel_event=cancel_event,
            user_id=owner_id,
            model_id=model_id,
            od_context=None,
            gate_agent_ids=[],
            parent_run_id=parent_run_id,
            # FIX-171: thread the narrator milestone_sink so chat_reply cards
            # (pipeline_start "Revision started", pipeline_complete "Delivered")
            # are persisted for revision runs — same wiring as _run_workflow_to_queue.
            # None when the WS caller does not supply it (backward-compat).
            milestone_sink=milestone_sink,
            # live_ectx_register / live_ectx_unregister: optional app-layer callbacks
            # threaded from _drive_revision_to_queue so the ectx is registered
            # (and analyzer_solution set) before the first agent step runs.
            # None → dormant (INV-3 safe, backward-compat).
            live_ectx_register=live_ectx_register,
            live_ectx_unregister=live_ectx_unregister,
        ):
            if event.get("type") == "pipeline_complete":
                final_output = event.get("data", {}).get("final_output")
            elif event.get("type") == "pipeline_failed":
                terminal_failed = True
            await websocket_send_fn(event)

        # ── Post-dispatch exact-kind lineage write (FR-014 chain link 1) ────────
        # Persist the REVISED deliverable under the exact target kind with
        # derived_from so a revision-of-revision resolves THIS run's output via
        # chain link 1. execute()'s terminal block already wrote the generic
        # kind="deliverable" ref (chain link 2) — both refs coexisting is
        # intentional. Guarded: a failed dispatch or empty deliverable writes
        # NOTHING under the exact kind (a failed revision must never become a
        # future revision parent — composes with the WS layer's terminal-status
        # fidelity).
        if final_output and not terminal_failed:
            try:
                # Build a typed ArtifactRef (graph computes id/content_hash/version)
                # for the revision result, derived_from the parent original. The
                # revision row lands in the revision RUN (pipeline_run_id); persist
                # it owner-scoped via the same ScopedStore. visibility="workspace"
                # keeps it consistent with the producer writes (a future
                # revision-of-revision can read it cross-run for the same owner).
                _rev_graph = ArtifactGraph()
                _rev_ref = _rev_graph.write_ref(
                    run_id=pipeline_run_id,
                    owner_id=owner_id,
                    # Land the revision in the SAME workspace as the parent original
                    # so the owner+workspace scope filter holds (workspace_id is
                    # NOT NULL).
                    workspace_id=original.workspace_id,
                    kind=target_artifact_type,
                    producer_step="revision",
                    # Derived from the resolved spec list (IN-05 spirit, SC-001 —
                    # no agent-id literal): revision pipelines are 1-2 single_shot
                    # steps and the LAST agent's streamed output is the declared
                    # deliverable.
                    producer_agent=agents[-1].id,
                    task_id=None,
                    content=final_output,
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
                # RESEARCH Open Q2 (resolved): keep the event vocabulary on a
                # lineage-persist failure but do NOT fail the run — the dispatch
                # already completed, and the terminal-block kind="deliverable" ref
                # keeps FR-014 chain link 2 functional for revision-of-revision.
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

    def _build_context_sources(
        self,
        spec,
        ordered_agents: list,
        ectx: ExecutionContext,
        agent_index: int = -1,
        user_message: str = "",
    ) -> list[dict]:
        """Build the context_sources list for the agent_input event (FR-015).

        For each upstream agent whose output is consumed, records:
        - type: "summary" (text output) or "artifact" (typed artifact)
        - agent_id, agent_name, summary_length, full_output_length

        KAN-102: additionally records run-originating sources for the FIRST agent
        (agent_index == 0) so "Context Received" is never empty:
        - type: "run_input" — the user brief (always present for first agent)
        - type: "context_block" — template and/or design system (when od_context is set)

        Positional check: agent_index == 0 is the GENERIC "first agent" predicate
        (same INV-1-compliant pattern used in _compose_context_message). No
        pipeline_type or spec.id branch.

        context_sources is in _VOLATILE_STRIP_KEYS in _normalize.py so the
        characterization goldens are byte-identical regardless of new entries (INV-3).

        Reads consumed content typed-only (ectx.artifacts) via
        _filter_consumed_outputs (ART-03 read-migration; the mirror fallback was
        deleted in 05-07).
        """
        sources: list[dict] = []

        # ── KAN-102: run-originating sources for the first agent ─────────────────
        # agent_index == 0 is the generic "first dispatched agent" predicate (INV-1).
        # Dormant for downstream agents (they have prior-agent sources instead).
        # context_sources is already in _VOLATILE_STRIP_KEYS so the goldens stay
        # byte-identical (INV-3) regardless of what we add here.
        is_first_agent = (agent_index == 0)
        if is_first_agent:
            # User brief — always present for the first agent
            if user_message:
                sources.append({
                    "type": "run_input",
                    "label": "prompt.md",
                    "size_chars": len(user_message),
                })

            # OD template and design system — present when od_context is loaded
            # (od_prototype / od_ppt runs). Read from ectx.od_context (same pattern
            # as the TEMPLATE COMPLIANCE block in _compose_context_message, INV-1).
            od = getattr(ectx, "od_context", None) or {}
            template_id = od.get("template_id") or ""
            ds_id = od.get("ds_id") or ""
            template_body = od.get("template_body") or ""
            ds_body = od.get("ds_body") or ""
            if template_id:  # show chip even if template_body empty (slug is enough)
                sources.append({
                    "type": "context_block",
                    "label": f"Template: {template_id}",
                    "size_chars": len(template_body) if template_body else 0,
                })
            if ds_id and ds_body:
                sources.append({
                    "type": "context_block",
                    "label": f"Design system: {ds_id}",
                    "size_chars": len(ds_body),
                })

            # KAN-103: for revision runs ectx.od_context is None, but design.md was
            # seeded into the sandbox by the previous_run provider (from the parent
            # build's sandbox). Parse the "# ACTIVE DESIGN SYSTEM (slug)" and
            # "# ACTIVE TEMPLATE (slug)" headers that _write_reference_files wrote to
            # emit template/DS chips even when od_context is absent.
            # INV-1: keyed on sandbox file content (generic), not pipeline_type/agent name.
            # INV-3: context_sources is in _VOLATILE_STRIP_KEYS → goldens unaffected.
            if not (template_id and ds_id):
                try:
                    import re as _re
                    _sandbox = getattr(ectx, "_sandbox", None)
                    if _sandbox is None:
                        from app.agents.sandbox import RunSandbox as _RS
                        _run_id = getattr(ectx, "run_id", None)
                        _disk_p = getattr(ectx, "disk_principal", None)
                        if _run_id and _disk_p:
                            _sandbox = _RS(_disk_p, _run_id)
                    if _sandbox is not None:
                        _design_md = _sandbox.read("design.md") or ""
                        if _design_md:
                            _tmpl_m = _re.search(
                                r"^#\s+ACTIVE TEMPLATE\s*(?:\(([^)]+)\))?",
                                _design_md, _re.MULTILINE
                            )
                            _tmpl_slug = (_tmpl_m.group(1) or "").strip() if _tmpl_m else ""
                            _ds_m = _re.search(
                                r"^#\s+ACTIVE DESIGN SYSTEM\s*(?:\(([^)]+)\))?",
                                _design_md, _re.MULTILINE
                            )
                            _ds_slug = (_ds_m.group(1) or "").strip() if _ds_m else ""
                            if _tmpl_slug and not template_id:
                                sources.append({
                                    "type": "context_block",
                                    "label": f"Template: {_tmpl_slug}",
                                    "size_chars": len(_design_md),
                                })
                            if _ds_slug and not ds_id:
                                sources.append({
                                    "type": "context_block",
                                    "label": f"Design system: {_ds_slug}",
                                    "size_chars": len(_design_md),
                                })
                        if not template_id and _sandbox.path_for("template.html").is_file():
                            _tmpl_html = _sandbox.read("template.html") or ""
                            if _tmpl_html and not any(
                                s.get("label", "").startswith("Template:") for s in sources
                            ):
                                sources.append({
                                    "type": "context_block",
                                    "label": "Template: (reference)",
                                    "size_chars": len(_tmpl_html),
                                })
                except Exception:  # noqa: BLE001 — observability, never abort agent dispatch
                    pass

            # ── Prototype HTML source chip for no-tools first agents (Concierge path) ─
            # When ectx.revision_original_html is set and the first agent has no tools,
            # Position 6 in _compose_context_message injects the HTML inline. Surface it
            # as a source chip so "Context Received" reflects what was actually fed.
            # INV-1/SC-001: keyed on generic ectx fields and spec.tools, never on
            # agent id or pipeline name. context_sources is in _VOLATILE_STRIP_KEYS
            # so INV-3 golden parity holds.
            _rev_html = getattr(ectx, "revision_original_html", "") or ""
            _s_tools = list(getattr(spec, "tools", []) or [])
            if _rev_html and not _s_tools:
                sources.append({
                    "type": "context_block",
                    "label": "prototype.html",
                    "size_chars": len(_rev_html),
                })

        # ── Prior-agent outputs (inter-agent handoff sources) ─────────────────────
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

        # ── Revision analysis (additive, INV-1 / SC-001 compliant) ───────────────
        # When ectx.analyzer_solution is non-empty (set by the produces_solution_plan
        # post-step hook after the analyzer step), downstream agents receive a
        # === REVISION ANALYSIS === block in their context. Surface it as a source
        # chip so "Context Received" is never empty on a revision run.
        # Keyed on ectx.analyzer_solution truthiness only — no agent_id / pipeline
        # name branch (SC-001). context_sources is in _VOLATILE_STRIP_KEYS so INV-3
        # golden parity holds.
        _analyzer_solution = getattr(ectx, "analyzer_solution", "") or ""
        if _analyzer_solution and not is_first_agent:
            sources.append({
                "type": "context_block",
                "label": "Revision Analysis",
                "size_chars": len(_analyzer_solution),
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
    # CR-06 (07-10): the in-place-revision agent is NO LONGER named here. This map
    # is a lineage-only KIND label for the persisted artifact_refs row; routing is
    # by producer_agent id, so an unmapped agent (the revision agent) falls back to
    # the valid ``summary`` kind below — which "never affects deliverable content /
    # parity" (see _artifact_kind_for). The kernel names no workflow agent by literal
    # for any behavior (INV-1).
    _AGENT_KIND_MAP: dict[str, str] = {
        "prototype-specify": "spec",
        "prototype-plan": "task_list",
        # FIX-223: add prototype-analyze explicitly with a dedicated "analysis" kind.
        # Previously it was absent → fell back to "summary" → _UPDATE_SPECS_ELIGIBLE_KINDS
        # matched "summary" → any unmapped gated agent also showed "Update the Specs".
        # The dedicated kind breaks the accidental fallback dependency (SC-001/INV-1 safe —
        # no agent-id literal in the eligibility check, only the kind string).
        "prototype-analyze": "analysis",
        "prototype-build": "html_file",
        "prototype-validate": "validation_report",
        # Revision pipeline agents — same semantic kinds as prototype counterparts
        # so artifact routing and FR-014 chain links work correctly (IN-01 advisory
        # silenced: these agent ids were falling back to "summary" then using agent
        # id as kind, which is outside ARTIFACT_KINDS).
        "prototype-revision-agent": "html_file",
        "prototype-revision-validate": "validation_report",
        # Tiered revision agents (large / feature pipeline variants).
        "prototype-revision-planner": "task_list",
        "prototype-large-builder": "html_file",
        "prototype-large-validate": "validation_report",
        "prototype-revision-feature-specify": "spec",
        "prototype-revision-feature-plan": "task_list",
        "prototype-feature-builder": "html_file",
        "prototype-feature-validate": "validation_report",
    }

    # SC-001 / KAN-101 / MD-01: the ARTIFACT KIND whose LIVE human gate offers the
    # generic "Update the Specs" affordance — the ANALYZE gate only. Keyed on the
    # structural artifact-kind from _artifact_kind_for — NEVER a workflow/agent-id
    # literal (name-free path). FIX-223: changed from {"summary"} to {"analysis"} —
    # prototype-analyze is now explicitly mapped to "analysis" in _AGENT_KIND_MAP,
    # so it alone produces this kind. Unmapped agents fall back to "summary" which is
    # NOT in the eligible set, so no other gated agent shows "Update the Specs".
    # The spec/plan authoring gates (spec / task_list) and the build/validation gates
    # (html_file / validation_report) are deliberately excluded, so a custom workflow
    # gating on any of them gets NO update-specs affordance.
    # A declared/user gate that never passes the flag defaults update_specs_eligible
    # to False regardless (mirroring redoable) — see _run_review_gate.
    _UPDATE_SPECS_ELIGIBLE_KINDS: frozenset[str] = frozenset({"analysis"})

    def _artifact_kind_for(self, spec) -> str:
        """Resolve the ARTIFACT_KINDS value for ``spec``'s produced artifact (D-01).

        Looks up the agent-id map; falls back to ``summary`` (a valid kind) for
        agents without an explicit mapping. The kind labels the persisted
        artifact_refs row; routing is by producer_agent (see _filter_consumed_outputs),
        so the fallback never affects deliverable content / parity.
        """
        return self._AGENT_KIND_MAP.get(getattr(spec, "id", ""), "summary")

    def _update_specs_eligible(self, artifact_kind: str, ectx) -> bool:
        """Does THIS gate firing advertise the "Update the Specs" affordance?

        Both conditions are STRUCTURAL — an artifact kind and a generic scratch field.
        No workflow name and no agent id appears here or at any call site (INV-1 / SC-001).

        1. ``artifact_kind`` is one of the eligible kinds (the analyze gate only — see
           ``_UPDATE_SPECS_ELIGIBLE_KINDS``).
        2. **No revision pass is currently in flight.** The sub-pipeline's PUBLISHED index
           (``ectx.revision_attempt``) doubles as the in-flight signal — it is non-zero for
           exactly the pass's duration — so this invents no parallel state (INV-12).

        Condition 2 exists to keep revision cycles FLAT. The analyze re-run INSIDE a pass is
        itself a full ``_run_agent`` and so opens its own gate; advertising "start another
        revision" there is the one route that NESTS. Withholding it moves the single
        supported entry point to the gate re-opened AFTER the pass returns, where the next
        cycle is a SIBLING call at the same stack depth — the REDO-GATE F2 flat-loop
        precedent (see the redo loop's comment at the top of ``_run_agent``). The user
        reaches it with the same number of clicks, so no capability is withdrawn.

        This verdict is BINDING, not merely an affordance (ISS-053). It is published on
        ``review_gate_ready`` and then ENFORCED in two places, neither of which restates
        the rule computed here — so there is exactly one rule and changing it changes both
        layers (INV-3 / INV-12):

          * ``_run_review_gate`` refuses an ineligible ``update_specs`` and keeps the gate
            waiting (the unbypassable layer — it holds this verdict in memory);
          * the three REST ingresses answer 409 ``update_specs_not_offered`` by reading the
            published value back (``run_engine._review_gate_advertises_update_specs``).

        Enforcement is what stops a replayed or crafted POST from nesting. The high-water
        index + save/restore in ``_run_spec_revision_sub_pipeline`` (T-si4-01) remain as
        defence in depth, so a nested pass would still be SAFE if it were ever reached.
        """
        return (
            artifact_kind in self._UPDATE_SPECS_ELIGIBLE_KINDS
            and not getattr(ectx, "revision_attempt", 0)
        )

    def _stamp_revision_marks(self, ectx) -> tuple[int, bool]:
        """Which spec-revision cycle is THIS gate firing part of, and is it inside it?

        Returns ``(revision_cycle, revision_in_flight)``, published on every inline
        ``review_gate_ready`` (ISS-052). Both values are read from generic per-run scratch
        that already exists — this invents no counter and no state (INV-12):

          * ``revision_high_water`` — the MONOTONE mark of the highest revision index ever
            published in this run. Never cleared, never restored, so it still names the
            cycle at the gate re-opened AFTER the pass has unwound.
          * ``revision_attempt`` — non-zero for EXACTLY the duration of a pass (set at
            entry, restored in the ``finally``), so it answers "is this gate inside the
            revision, or after it".

        The PAIR is what identifies a firing; neither half does it alone. Over one cycle
        the three analyze-gate firings are ``(0, False)`` outer, ``(1, True)`` in-pass,
        ``(1, False)`` re-opened — the in-pass and re-opened gates share a cycle and are
        told apart by the in-flight flag alone. That matters downstream: they also share a
        ``gate_key`` and their output bytes, so a consumer keyed on those two (the FE's
        one-action latch) cannot see the second gate arrive without this.

        Structural throughout — no workflow name, no agent id (INV-1 / SC-001). Default
        ``(0, False)`` on a context that has never revised ⇒ dormant on every normal run.
        """
        return (
            getattr(ectx, "revision_high_water", 0),
            bool(getattr(ectx, "revision_attempt", 0)),
        )

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
        source — the latest ref by ``max(version)`` (the build loop writes a new
        prototype-build ref version per task; the next task's prompt needs the most
        recent). The prior-agent output mirror that used to be the fallback was
        DELETED in 05-07 (INV-3/INV-12, L15 ☑) once parity proved the typed reads
        return the same content. Returns None if the graph has no such content.

        REDO-GATE B10 (F5): the winner is the MAX-``version`` matching ref (tie-broken
        by later insertion via ``>=``), NOT raw ``tree()`` insertion order — so a
        REJECTED prior version can never win after persist + rehydrate (where
        ``store.tree()`` re-adopts refs in an arbitrary order). Byte-identical on the
        goldens: within one process write order == version order, and no golden
        producer emits a higher-version kind before a lower-version different kind, so
        "max version, later-insertion tie-break" == "last inserted" (parity-guarded).

        R-05 fallback (spec 014 / conditional gates): a composed custom-agent step's
        typed artifacts are always written under its FULL ``"custom-agent:<instance_id>"``
        producer id (engine.py's per-step dual-write), but a ``route.condition_agent``
        is author-facing and commonly names the step's bare ``instance_id`` (the same
        dual-identity acceptance the compiler's R-27/R-10 route-target validation
        already allows — see ``compiler.py::_validate_route_targets``'s ``by_name``
        map). When no ref matches ``producer_agent`` exactly, retry against a
        ``":<producer_agent>"`` suffix. Purely additive — every existing caller passes
        a full id that matches on the first pass, so this is byte-identical for them.
        """
        best = None
        for ref in ectx.artifacts.tree(ectx.run_id):
            if ref.producer_agent == producer_agent and (
                best is None or ref.version >= best.version
            ):
                best = ref
        if best is not None:
            return best.content
        _suffix = f":{producer_agent}"
        for ref in ectx.artifacts.tree(ectx.run_id):
            if ref.producer_agent.endswith(_suffix) and (
                best is None or ref.version >= best.version
            ):
                best = ref
        return best.content if best is not None else None

    def _latest_typed_ref_id(
        self,
        ectx: ExecutionContext,
        producer_agent: str,
        kind: str,
    ) -> str | None:
        """Return the id of the MAX-``version`` typed ref for (producer_agent, kind).

        RESUME-15 lineage resolver: a gate Edit mints a NEW artifact version, and
        its ``derived_from`` must point at the version it supersedes. Resolved
        BEFORE the edit write, so the current max IS the prior version. Mirrors the
        redo path's max-version id lookup (``max(_cands, key=version).id``, B5) and
        the ``_latest_typed_content`` max-version F5 discipline (tie-broken by later
        insertion via ``>=``). Returns None when no prior ref of this kind exists
        (the first version has no ancestor) — so a first-ever write stamps None,
        byte-identical to today (INV-3).
        """
        best = None
        for ref in ectx.artifacts.tree(ectx.run_id):
            if (
                ref.producer_agent == producer_agent
                and ref.kind == kind
                and (best is None or ref.version >= best.version)
            ):
                best = ref
        return best.id if best is not None else None

    async def _seed_gate_reentry_attempts(self, ectx: ExecutionContext, spec) -> tuple[int, int]:
        """RESUME-17 (A2): seed ``(redo_attempt, spec_revision_attempt)`` FAIL-SAFE HIGH.

        On a post-restart gate re-entry the loop locals reset to 0, but a redo /
        update_specs threads a checkpoint id off ``redo_attempt`` / ``spec_revision_attempt``
        (``:redo{N}`` / ``:rev{N}``). Reusing a pre-restart id is the P23
        checkpointer-replay bug (the model "remembers" its rejected output). Derive the
        prior counts from TWO durable signals and take the MAX so the next id is STRICTLY
        greater than any pre-restart id — over-estimating is a fresh unused thread id;
        under-estimating collides, so the fail-safe direction is HIGH:

          * ``gate_events`` audit rows for this step (``gate=="human"`` +
            ``outcome=="redo"`` / ``"update_specs"``) — the inline consumers write these
            best-effort (redo since P23; update_specs since A2 this plan);
          * the durable typed-artifact version count for this agent+kind (each redo /
            revision re-run mints a new version).

        Best-effort: any read failure degrades to the durable version count (NEVER a bare
        0 when versions exist — that would risk a collision). Offline / no runner ⇒ the
        version-count signal alone. Keyed on ``spec.id`` + the generic gate vocabulary
        only (SC-001 / INV-1).
        """
        _kind = self._artifact_kind_for(spec)
        # (1) durable audit counts (best-effort, owner-scoped via the runner).
        redo_events = 0
        update_specs_events = 0
        runner = getattr(ectx, "runner", None)
        if runner is not None and hasattr(runner, "read_gate_events"):
            try:
                rows = await runner.read_gate_events(ectx.run_id)
                for r in rows:
                    if (
                        getattr(r, "step", None) == spec.id
                        and getattr(r, "gate", None) == "human"
                    ):
                        _outcome = getattr(r, "outcome", None)
                        if _outcome == "redo":
                            redo_events += 1
                        elif _outcome == "update_specs":
                            update_specs_events += 1
            except Exception:  # noqa: BLE001 — an audit read must never abort a resume
                logger.debug(
                    "gate-reentry: read_gate_events failed for %s (ignored)",
                    spec.id, exc_info=True,
                )
        # (2) durable typed-artifact version count for this agent+kind.
        version_count = 0
        try:
            version_count = len(
                [
                    r for r in ectx.artifacts.list_by_kind(_kind)
                    if r.producer_agent == spec.id
                ]
            )
        except Exception:  # noqa: BLE001 — no graph → version signal 0
            version_count = 0
        # Fail-safe HIGH: the MAX of both durable signals (per the PINNED A2 formulas).
        redo_attempt = max(redo_events, version_count - 1)
        spec_revision_attempt = max(update_specs_events, version_count)
        if redo_attempt < 0:
            redo_attempt = 0
        return redo_attempt, spec_revision_attempt

    # ──────────────────────────────────────────────────────────────────────
    # RESUME-02 (12-02): the SINGLE per-step retry/reuse wrapper (D-10).
    #
    # Wraps the per-step ``strategy.run(step, ectx)`` dispatch at the ONE home
    # (the engine dispatch loop — NOT inside strategies, NOT per-worker inside
    # run_fanout). It is GATED STRICTLY: only when the compiled step declares
    # ``retry.max_attempts > 0``. When the gate is FALSE the legacy path
    # (``async for event in strategy.run(...): yield event``) runs UNCHANGED —
    # byte/event-identical to today (Pitfall 4; existing manifests declare no
    # retry, so the 5 characterization snapshots stay dormant).
    # ──────────────────────────────────────────────────────────────────────

    @staticmethod
    def _apply_selections(compiled, selections: dict | None, run_agent_ids: list[str] | None = None):
        """Overlay user-composed per-step selections onto the compiled plan (EMP-01).

        ``selections`` is the compact ``{agent_id: {validators, gates, model, retry,
        strategy, fanout, task_source, ...}}`` map a saved/custom workflow carries. It
        is re-compiled through the SAME thin ``trust="user"`` path (the synth seam in
        ``agents.workflows.selections`` + ``WorkflowCompiler.compile(trust="user")``)
        — so the overlay can ONLY carry user-allowed levers — then the selected
        levers are merged onto the matching file-compiled ``Step`` BY AGENT_ID
        (generic, name-free — SC-001). A step the user did not touch is unchanged.

        ``run_agent_ids`` (the run's ordered agent ids) widens the trust-compile synth
        set so a composed agent ABSENT from the base manifest (the common ``custom``
        case) still gets a trust-compiled step. Returns a 2-tuple
        ``(plan, user_step_map)`` where ``user_step_map`` is ``{agent_id: trust-compiled
        Step}`` — the absent-agent synthesis site (Path B) consults it before falling
        back to a bare ``single_shot`` step. It NEVER adds/removes steps from the plan
        (the overlay replaces steps in place — the membership assertion stays valid).

        ``None`` / empty selections → ``(compiled, {})`` — the plan is returned UNCHANGED
        and the map is empty (every existing run + all 5 goldens take this path → both
        consumption sites are byte/event-identical, INV-3). Any compile failure (a
        tampered map that slipped past the WS gate) degrades to ``(compiled, {})`` rather
        than crashing the run — the WS layer is the authoritative rejection site (this is
        the defense-in-depth backstop).
        """
        from agents.workflows.selections import has_selections

        if not has_selections(selections):
            return compiled, {}

        import dataclasses

        from agents.capabilities.registry import CapabilityRegistry
        from agents.workflows.compiler import CompilerError, WorkflowCompiler
        from agents.workflows.selections import synthesize_manifest

        # Trust-compile a step for EVERY run agent, not just the base-manifest agents,
        # so a composed agent absent from the base plan still yields a user-step the
        # synthesis site can consult (Path B). Order-preserving, de-duplicated.
        # Run agents come FIRST so the synth manifest reflects the user's composed
        # producer->worker order (which presort preserves for unconstrained agents),
        # NOT the base-manifest `order`. Without this the D9 upstream-source guard
        # falsely rejects a valid fan-out whose producer has a HIGHER base order than
        # its worker (e.g. task-list-planner order:9 feeding market-research-agent
        # order:1) — the producer would land AFTER the worker in base order and read
        # as a forward reference. Base ids follow for coverage of run-absent agents.
        base_ids = [s.agent_id for s in compiled.steps]
        agent_ids = list(dict.fromkeys([*(run_agent_ids or []), *base_ids]))
        try:
            user_compiled = WorkflowCompiler().compile(
                synthesize_manifest(compiled.id, agent_ids, selections),
                CapabilityRegistry(),
                trust="user",
            )
        except CompilerError:
            # WR-03: narrow the catch to the ONLY expected rejection (a tampered map
            # that slipped past the WS gate). This is the documented defense-in-depth
            # backstop — the WS layer is the authoritative rejection site, so a
            # CompilerError here degrades safely to the unmodified plan. An UNEXPECTED
            # exception type (e.g. an AttributeError/TypeError from a future refactor)
            # is a programmer error and MUST propagate, not be silently swallowed —
            # otherwise the overlay fails open invisibly.
            logger.warning(
                "engine: user selections failed trust=user re-compile at run entry "
                "— proceeding with the unmodified plan (the WS layer is the "
                "authoritative rejection site)"
            )
            return compiled, {}

        # Index the user-compiled levers by agent_id and merge onto the file steps.
        _user_by_agent = {s.agent_id: s for s in user_compiled.steps}
        _sel_map = selections or {}
        new_steps = []
        for step in compiled.steps:
            sel = _sel_map.get(step.agent_id)
            user_step = _user_by_agent.get(step.agent_id)
            if not sel or user_step is None:
                new_steps.append(step)
                continue
            # Merge ONLY the levers the user actually selected (present in ``sel``) —
            # de-duplicating gates/validators so a step that already declared one
            # keeps a single entry. The model/retry overlay wins when selected.
            patch: dict = {}
            if sel.get("validators"):
                merged_v = list(dict.fromkeys([*step.validators, *user_step.validators]))
                patch["validators"] = merged_v
            if user_step.gates:
                merged_g = list(dict.fromkeys([*step.gates, *user_step.gates]))
                patch["gates"] = merged_g
            if sel.get("model") and user_step.model is not None:
                patch["model"] = user_step.model
            if sel.get("retry") and user_step.retry is not None:
                patch["retry"] = user_step.retry
            if sel.get("injects"):
                patch["injects"] = list(
                    dict.fromkeys([*step.injects, *user_step.injects])
                )
            # ADR-0010 — per-agent skills selected in the composer. UNION with the
            # step's manifest-declared skills, exactly like ``injects`` above: the
            # composer's picker can only ADD to what the workflow author declared,
            # never silently drop a skill the manifest requires. This is the ONLY
            # route a composed run's skills take now that run-level
            # ``attached_skills`` is retired — it lands on ``Step.skills``, which
            # the dispatch loop reads as ``ectx.current_step.skills`` into
            # ``ctx.step_skills``, which ``factory._resolve_step_skills`` turns into
            # the staged skill payloads.
            if sel.get("skills"):
                # Unknown ids are DROPPED here rather than carried through.
                # ``factory._resolve_step_skills`` asserts on an unresolvable id,
                # and that assert is correct for a file-backed manifest (a typo
                # there is an author bug worth failing loudly on) — but these ids
                # are USER-supplied and may be stale: a workflow saved when skill
                # "x" existed must not crash the run after "x" leaves the catalog.
                # Note the assert's docstring claims the compiler validates these
                # at compile time; it does not (`compiler.py` carries `skills`
                # verbatim), so this filter is the only guard on the user path.
                _known = _known_skill_ids()
                _merged = list(dict.fromkeys([*step.skills, *user_step.skills]))
                if not _known:
                    # Catalog unreadable — filtering on an empty set would strip
                    # EVERY skill, which is worse than the stale-id crash it is
                    # meant to prevent. Carry the ids through untouched.
                    patch["skills"] = _merged
                else:
                    _dropped = [s for s in _merged if s not in _known]
                    if _dropped:
                        logger.warning(
                            "engine: dropping unknown per-step skill ids %s for agent "
                            "%s (not in the global skills catalog)",
                            _dropped, step.agent_id,
                        )
                    patch["skills"] = [s for s in _merged if s in _known]
            # Fan-out levers (D3, the crux) — each fires ONLY when the user selected
            # it, so the empty-selections path stays byte-identical (INV-3). No
            # ``tools`` overlay: the declarative fanout_batch path acquires no
            # spawn_subagents grant (run_fanout does no permission check; trust=user
            # forces tools.spawn_subagents OFF anyway).
            if sel.get("strategy") and user_step.strategy:
                patch["strategy"] = user_step.strategy
            if sel.get("fanout") and user_step.fanout is not None:
                patch["fanout"] = user_step.fanout
            if sel.get("task_source") and user_step.task_source is not None:
                patch["task_source"] = user_step.task_source
            new_steps.append(dataclasses.replace(step, **patch) if patch else step)

        # Option B (KAN-112): if the user explicitly selected an output type in the
        # custom composer, the FE stores it under the reserved ``__deliverable__`` key
        # in the selections map (same namespace convention as ``__workflow__`` for
        # limits — no new column, no migration).  Apply it by replacing the compiled
        # plan's deliverable spec so the engine routes the run to the correct
        # deliverable resolver (e.g. single_file → prototype.html instead of
        # streamed_text).  Generic, name-free (SC-001): the caller decides the shape,
        # the engine just carries it.  None/absent → the compiled deliverable is
        # unchanged (byte/event-identical for all existing runs, INV-3).
        # Also set clarify.mode=skip when a deliverable override is present — the
        # custom composer brief already describes intent; forcing a clarification
        # questionnaire would block the FE (the QuestionnairePanel never renders
        # before pipeline_start on the custom flow — same reason custom_prototype
        # had clarify.mode:skip in its manifest).
        _deliverable_override = (selections or {}).get("__deliverable__")
        if _deliverable_override and isinstance(_deliverable_override, dict):
            from agents.workflows.plan import DeliverableSpec
            try:
                patched_deliverable = DeliverableSpec(**_deliverable_override)
                # Force clarify.mode=skip: the custom composer brief already captures
                # intent; questionnaire would block (FIX-016 / MAN-04 parity).
                patched_clarify = dataclasses.replace(compiled.clarify, mode="skip")
                return dataclasses.replace(
                    compiled,
                    steps=new_steps,
                    deliverable=patched_deliverable,
                    clarify=patched_clarify,
                ), _user_by_agent
            except TypeError:
                # Unknown DeliverableSpec field — degrade gracefully; the unmodified
                # deliverable is safer than crashing the run (the WS layer already
                # validated the shape at ingress).
                logger.warning(
                    "engine: __deliverable__ override has unknown fields %s — "
                    "proceeding with the compiled deliverable unchanged",
                    list(_deliverable_override),
                )

        return dataclasses.replace(compiled, steps=new_steps), _user_by_agent

    async def _dispatch_step_with_retry(self, step, ectx: ExecutionContext, strategy):
        """Drive one step's strategy with retry-on-transient + content-hash reuse.

        Gate-FALSE (no retry / max_attempts == 0): re-yield ``strategy.run`` events
        unchanged (legacy parity). Gate-TRUE:
          (a) compute the step input_hash; if a matching prior completion exists,
              yield ``step_reused`` and SKIP execution (zero agent invocation);
          (b) otherwise run the strategy in an attempt loop bounded by
              ``max_attempts``; on success yield ``step_completed`` carrying the
              ``input_hash`` + produced ``output_ref_id`` (so a later retry/restart
              reuse-lookup can find it); on a TRANSIENT-classified error with
              attempts remaining yield ``step_retry`` + ``await _retry_sleep`` and
              loop; on a non-transient error OR exhaustion RE-RAISE (the existing
              visible agent_error path — never swallowed).
        """
        # Strict gate: activate ONLY when ``step.retry and step.retry.max_attempts > 0``.
        retry = getattr(step, "retry", None)
        if not (retry and getattr(retry, "max_attempts", 0) > 0):
            # Dormant: byte/event-identical legacy dispatch.
            async for event in strategy.run(step, ectx):
                yield event
            return

        from agents.model_policy import _is_transient_throttle

        step_id = getattr(step, "agent_id", None)
        input_hash = self._compute_step_input_hash(step, ectx)

        # (a) Reuse path — a prior matching completion → skip the agent entirely.
        reused_ref = await self._find_reused_completion(ectx, step_id, input_hash)
        if reused_ref is not None:
            yield {
                "type": "step_reused",
                "data": {
                    "step": step_id,
                    "input_hash": input_hash,
                    "output_ref_id": reused_ref,
                },
            }
            return

        # (b) Bounded attempt loop (T-12-02-DOS: strictly ≤ max_attempts).
        max_attempts = int(retry.max_attempts)
        on = set(getattr(retry, "on", ["transient"]) or ["transient"])
        attempt = 0
        while True:
            attempt += 1
            # Snapshot existing refs for THIS step so we can identify the new one.
            before_ids = {
                r.id for r in ectx.artifacts.tree(ectx.run_id)
                if r.producer_agent == step_id
            }
            # KRN-006 (task.md R-04): a strategy can signal a terminal outcome
            # COOPERATIVELY (an ``agent_error``/``pipeline_cancelled`` EVENT) rather
            # than by raising, and then still let its generator end "normally" —
            # before this fix, this loop blindly forwarded every yielded event and,
            # once the generator returned without raising, emitted ``step_completed``
            # regardless of what terminal-shaped events had already gone out. A
            # ``pipeline_cancelled`` here means the WHOLE RUN already stopped (the
            # engine's own cancel handling), so this step obviously never
            # completed; an UNRECOVERABLE ``agent_error`` (``recoverable: False`` —
            # the fatal-error arm's own contract, see ``_run_agent``'s
            # ``return``-after-yield sites) means the invocation that would have
            # produced this step's output never did. Track both; a strategy that
            # legitimately recovers (a ``recoverable: True`` timeout/degrade that
            # still appends a result) is UNAFFECTED — ``step_completed`` still
            # fires for it, matching today's behavior.
            _step_terminal_seen = False
            try:
                async for event in strategy.run(step, ectx):
                    if event.get("type") == "pipeline_cancelled":
                        _step_terminal_seen = True
                    elif event.get("type") == "agent_error" and (
                        event.get("data", {}).get("recoverable") is False
                    ):
                        _step_terminal_seen = True
                    yield event
            except Exception as exc:  # noqa: BLE001 — classify then retry or re-raise
                transient = "transient" in on and _is_transient_throttle(exc)
                if transient and attempt < max_attempts:
                    yield {
                        "type": "step_retry",
                        "data": {
                            "step": step_id,
                            "attempt": attempt,
                            "max": max_attempts,
                        },
                    }
                    await _retry_sleep(getattr(retry, "backoff_seconds", 0.0))
                    continue
                # Non-transient OR attempts exhausted → surface the visible error.
                raise
            if _step_terminal_seen:
                # The strategy already signaled a terminal outcome through the
                # event stream (not an exception) — do NOT emit step_completed for
                # a step that never actually completed. Nothing else to do: the
                # terminal event itself was already forwarded above, and the
                # OUTER step-dispatch loop (engine.py, the ``_terminated``/
                # ``_failed_agent_ids`` bookkeeping) reads that same forwarded
                # event to decide the run-level outcome — this only removes the
                # FALSE ``step_completed`` that used to follow it.
                return
            # Success: identify the artifact this step produced (newest ref).
            output_ref_id = None
            for ref in ectx.artifacts.tree(ectx.run_id):
                if ref.producer_agent == step_id and ref.id not in before_ids:
                    output_ref_id = ref.id
            yield {
                "type": "step_completed",
                "data": {
                    "step": step_id,
                    "input_hash": input_hash,
                    "output_ref_id": output_ref_id,
                },
            }
            return

    # ──────────────────────────────────────────────────────────────────────
    # RESUME-02 (12-02): per-step retry/reuse — input-hash + reuse-lookup.
    #
    # These two helpers are the shared key for BOTH the retry re-entries (this
    # plan) and the 12-03 durable-restart re-runs: a step's input content-hash.
    # ``_compute_step_input_hash`` is CROSS-RESTART STABLE (sha256 over the
    # SORTED upstream artifact content_hashes + the resolved input string — NO
    # timestamp, NO uuid, NO unsorted collection, per RESEARCH D-11/Pitfall 1).
    # ``_find_reused_completion`` reads the durable, OWNER-SCOPED run_events for a
    # prior completion under the SAME (step_id, input_hash) and returns its
    # output_ref_id only when the produced artifact still exists (else None;
    # None offline → re-execute).
    # ──────────────────────────────────────────────────────────────────────

    def _upstream_content_hashes(self, step, ectx: ExecutionContext) -> list[str]:
        """Return the (unsorted) content_hashes of the upstream artifacts this step consumes.

        THE single home of the produces∩consumes upstream scan (INV-12). Both
        ``_compute_step_input_hash`` (which folds it into the step input_hash) AND
        ``_compute_upstream_context_hash`` (which digests it for the RESUME-14
        ``task_key`` namespace) call this — so the upstream-consume scan exists
        EXACTLY ONCE in the file; there is never a second upstream-hashing scheme.

        Reuses the registry produces∩consumes contract via the runner's
        ordered_agents when present; falls back to every produced ref (a step that
        consumes nothing yields the empty upstream set — still deterministic).
        """
        spec = None
        ordered_agents: list = []
        runner = getattr(ectx, "runner", None)
        if runner is not None:
            ordered_agents = list(getattr(runner, "_ordered_agents", []) or [])
            for s in ordered_agents:
                if getattr(s, "id", None) == getattr(step, "agent_id", None):
                    spec = s
                    break

        upstream_hashes: list[str] = []
        if spec is not None and ordered_agents:
            consumes = set(getattr(spec, "consumes", []))
            for upstream in ordered_agents:
                if upstream.id == spec.id:
                    break
                if upstream.id.startswith("_"):
                    continue
                if set(getattr(upstream, "produces", [])) & consumes:
                    for ref in ectx.artifacts.tree(ectx.run_id):
                        if ref.producer_agent == upstream.id:
                            upstream_hashes.append(ref.content_hash)
        else:
            # No consume contract reachable → hash over ALL produced upstream
            # content (still deterministic + cross-restart stable).
            for ref in ectx.artifacts.tree(ectx.run_id):
                upstream_hashes.append(ref.content_hash)
        return upstream_hashes

    def _compute_upstream_context_hash(self, step, ectx: ExecutionContext) -> str:
        """Return a cross-restart-stable sha256 of the SORTED upstream content_hashes.

        RESUME-14: this is the NAMESPACE half of a ``task_key``. A spec/plan edit
        rotates the consumed upstream content → this digest rotates → every dependent
        ``task_key`` rotates → the reconciler auto-re-runs the affected tasks (Q2
        automatic reconciliation). Reuses the ONE upstream scan
        (``_upstream_content_hashes``) that ``_compute_step_input_hash`` also folds in
        (INV-12 — no second upstream-hashing scheme). Sorting makes the digest
        insensitive to production order; NEVER a timestamp/uuid → cross-restart stable.
        """
        upstream_hashes = self._upstream_content_hashes(step, ectx)
        canonical = json.dumps(
            {"upstream": sorted(upstream_hashes)},
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _compute_step_input_hash(self, step, ectx: ExecutionContext) -> str:
        """Return a cross-restart-stable sha256 of the step's resolved input.

        The hash is taken over a canonical JSON payload of two parts:
          * ``upstream``: the SORTED list of the content_hashes of the upstream
            artifacts this step consumes (content-addressed → identical upstream
            content ⇒ identical hashes), read from the typed graph
            (``ectx.artifacts``) via the shared ``_upstream_content_hashes`` scan.
            Sorting makes the key insensitive to production order (Pitfall 1 —
            cross-restart stability).
          * ``input``: the step's resolved task/prompt input string (the run's
            user brief; a task-loop step also carries its per-task block on
            ``ectx.current_task_block`` when present).

        NEVER includes a timestamp, a fresh uuid, or an unsorted collection: the
        12-03 restart re-runs depend on hash EQUALITY for the same input. The
        payload is byte-identical to pre-factoring HEAD (the upstream half now
        comes from ``_upstream_content_hashes`` — same list, same order, same hash).
        """
        upstream_hashes = self._upstream_content_hashes(step, ectx)

        runner = getattr(ectx, "runner", None)
        resolved_input = getattr(runner, "user_message", "") if runner is not None else ""
        task_block = getattr(ectx, "current_task_block", None)
        if task_block:
            resolved_input = f"{resolved_input}\n{task_block}"

        canonical = json.dumps(
            {"upstream": sorted(upstream_hashes), "input": resolved_input},
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    async def _find_reused_completion(
        self, ectx: ExecutionContext, step_id: str, input_hash: str
    ) -> str | None:
        """Return an existing ``output_ref_id`` for a prior matching completion, else None.

        Queries the durable, OWNER-SCOPED ``run_events`` (T-12-02-REPLAY: a
        cross-owner run resolves to ∅ via ``ScopedStore.read_events``) for a prior
        ``step_completed``/``step_reused`` event whose payload carries the SAME
        ``(step_id, input_hash)``, and confirms the referenced output artifact still
        exists in the typed graph before reusing it. Best-effort: a ``None`` store
        (offline harness) or any read error → return ``None`` (no reuse, re-execute).
        """
        store = getattr(ectx, "scoped_store", None)
        if store is None:
            return None
        try:
            rows = await store.read_events(ectx.run_id, 0)
        except Exception:  # noqa: BLE001 — offline / schema-less harness → no reuse
            return None
        for row in rows:
            if getattr(row, "type", None) not in ("step_completed", "step_reused"):
                continue
            payload = getattr(row, "payload_json", None) or {}
            if not isinstance(payload, dict):
                continue
            if payload.get("step") != step_id or payload.get("input_hash") != input_hash:
                continue
            output_ref_id = payload.get("output_ref_id")
            if not output_ref_id:
                continue
            # Confirm the produced artifact still exists before reusing it.
            if ectx.artifacts.get(output_ref_id) is not None:
                return output_ref_id
        return None

    async def _recover_workspace_id(self, owner_id: str, run_id: str) -> str | None:
        """Recover the run's ORIGINAL ``workspace_id`` from a durable row (RESUME-04).

        ``create_workspace`` is not idempotent (it mints a fresh uuid per call), but a
        resumed run's durable rows were written under the ORIGINAL workspace_id. To keep
        the owner+workspace-scoped resume reads aligned with those rows (Pitfall 2 — no
        binding drift), recover the original id from the first available durable row for
        this run, scoped by ``owner_id`` ONLY (the run_id + owner pins it; the
        workspace_id is exactly what we are recovering). Tries the run's
        ``run_events`` / ``artifact_refs`` / ``wave_runs`` in turn. Returns ``None`` when
        no durable row exists (a run that never persisted state → mint a fresh
        workspace, the normal path). Best-effort: any error → ``None``.
        """
        try:
            from app.models.database import SessionLocal
        except Exception:  # noqa: BLE001 — no DB (offline harness) → mint fresh
            return None
        db = SessionLocal()
        try:
            from app.models.artifact_ref import ArtifactRef as _ARow
            from app.models.run_event import RunEvent as _ERow
            from app.models.wave_run import WaveRun as _WRow

            for model in (_ERow, _ARow, _WRow):
                row = (
                    db.query(model)
                    .filter(model.run_id == run_id, model.owner_id == owner_id)
                    .first()
                )
                if row is not None and getattr(row, "workspace_id", None):
                    return row.workspace_id
            return None
        except Exception:  # noqa: BLE001 — recovery is best-effort
            return None
        finally:
            db.close()

    async def _hydrate_artifacts_from_store(self, ectx: ExecutionContext) -> None:
        """Re-seed the run's durable typed artifacts into ``ectx.artifacts`` (resume).

        Reads the OWNER-SCOPED durable ``artifact_refs`` and ``adopt``s each into the
        in-memory graph PRESERVING its id/hash/version (12-03 / RESUME-04). On a
        fresh-process resume this re-populates the outputs of the steps that completed
        before the restart so the downstream (re-entered) steps can consume them.
        Best-effort: no store / a read error leaves the graph empty (the resumed step's
        downstream just re-runs from scratch — still correct, D-09).
        """
        from agents.artifacts.graph import ArtifactRef as _GraphRef

        store = getattr(ectx, "scoped_store", None)
        if store is None:
            return
        try:
            rows = await store.tree(ectx.run_id)
        except Exception:  # noqa: BLE001 — offline / schema-less → empty graph
            return
        for row in rows or []:
            try:
                ectx.artifacts.adopt(
                    _GraphRef(
                        id=row.id,
                        kind=row.kind,
                        owner_id=row.owner_id,
                        workspace_id=row.workspace_id,
                        run_id=row.run_id,
                        producer_step=row.producer_step,
                        producer_agent=row.producer_agent,
                        task_id=row.task_id,
                        content=row.content,
                        content_hash=row.content_hash,
                        location=row.location,
                        version=row.version,
                        parents=list(row.parents or []),
                        derived_from=row.derived_from,
                        visibility=row.visibility,
                        retention=row.retention,
                    )
                )
            except Exception:  # noqa: BLE001 — a malformed row must not break the resume
                continue

    async def _rematerialize_artifacts_to_disk(
        self,
        ectx: ExecutionContext,
        sandbox,
        *,
        boundary_by_agent: dict | None = None,
        wave_allow_by_step: dict | None = None,
    ) -> None:
        """Restore the durable FILE-backed artifacts onto the fresh ``RunSandbox`` (RESUME-08).

        The DISK half of resume — the mirror of :meth:`_hydrate_artifacts_from_store`
        (which restores the in-memory graph ONLY). On a fresh-process resume the
        sandbox on disk is empty, so a resumed strategy re-reading it (e.g. the next
        task's skeleton read, or the per-wave merge picking up its workers' fragments)
        sees nothing. This walks the latest durable file-backed refs and writes their
        content back onto the sandbox BEFORE strategies re-enter — reconstructing the
        worktree/sandbox state from ``artifact_refs``, NEVER from git (worktree commits
        are ephemeral, POR §3.2).

        Reads the SAME owner-scoped ``store.tree(run_id)`` hydrate uses (default-deny,
        keyed on the run's own principal — a foreign row can never appear in the result
        set, so it can never reach disk; NO scope widening). Per-location
        ``max(version)`` wins (the fix-loop re-persist writes a new version under the
        same location). Filtered to the FILE-backed kinds — ``html_file``/``file_bundle``/
        ``deliverable`` — that map to a real on-disk relpath (the typed metadata kinds
        ``spec``/``plan``/``clarifications``/… are graph-only handoffs already restored
        by hydrate and have no disk file); ``.uploads/`` is dropped (Phase-47 fence,
        never re-materialized; images never captured — ND-10). ``sandbox.write`` resolves
        through the traversal-proof ``path_for``. Best-effort: no store / a read error /
        a per-row write error degrades to a partial-or-empty disk (the resumed step just
        re-runs from scratch — still correct). Dormant on a normal run (gated on
        ``_is_resume`` at the call site).

        Mid-wave merge re-entry: fragments persist via ``write_fragment_artifact``
        (``kind="file_bundle"``) BEFORE the per-wave merge. The ``wave_runs.status`` is
        the merged-vs-unmerged discriminator — ``completed`` ⇒ the merge ran (the wave is
        skipped wholesale); ``running``/absent ⇒ the in-flight wave whose merge never ran.
        Re-materializing that wave's fragments here lets the EXISTING whole-wave re-run
        (``run_fanout``→``_merge_fragments``) merge over the recovered fragments — no
        second merge implementation (INV-12). The stored ``content`` is restored exactly,
        so ``content_hash``es are unchanged and step-reuse input keys stay stable
        (Pitfall 1). Reads the ORIGINAL workspace_id path (never a fresh workspace —
        Pitfall 2), since the read rides ``ectx.scoped_store``.

        RESUME-16 cumulative BOUNDARY selector (``boundary_by_agent``, THREE explicit
        states per producing agent — Pitfall 4):
          (i)   NOT supplied (None / agent absent) → per-location global ``max(version)``
                (byte-identical to today; dormant on non-cumulative / non-edited resume).
          (ii)  ``{restore_nothing: False, boundary_task_id: <key>}`` (p>0) → restore the
                ``max(version)`` row of THAT agent whose ``task_id == boundary_task_id``
                (the file AFTER the boundary task's fixes), NOT the global max (which may
                embed deleted-suffix-task work). Restore-by-max PER task_id absorbs the
                fix-loop re-persist multiplicity (Pitfall 9).
          (iii) ``{restore_nothing: True, ...}`` (p==0, first task diverged) → materialize
                NO version for that agent's locations — the build starts from a clean/empty
                basis. The negative-index (``current_keys[-1]``) wrong-restore is impossible
                here because the p==0 caller supplies ``restore_nothing`` (never a key).
        (i) and (iii) are DISTINCT states (None is never overloaded to mean "restore
        nothing"). Immutable rows are only READ — no row is deleted/mutated (T-48-04).

        RESUME-16 independent (``wave_allow_by_step``, the orphan-fragment gate — T-48-04/
        T-48-05): maps a WAVE step's agent id (== a fragment's ``producer_step``) to the
        set of CURRENT (max-version) task keys. When a ``file_bundle`` fragment's
        ``producer_step`` is in this map, the fragment→key join (its ``task_id`` == the
        owning worker's ``str(worker_index)`` → the worker's ``subagent_runs.task_id`` ==
        the key) is PINNED to THREE cases (Pitfall: the join is the MEDIUM wrinkle, the
        exclusion POINT here is HIGH):
          (1) RESOLVABLE (an UNAMBIGUOUS worker_index→key map) and key ∈ allow-set →
              RESTORE (a completed, still-current fragment);
          (2) RESOLVABLE (unambiguous) and key ∉ allow-set (a completed key ABSENT from
              the current list = CONFIDENTLY orphaned) → EXCLUDE — NOT restored to disk,
              so it reaches NEITHER ``_merge_fragments`` NOR the terminal
              ``serialized_sandbox`` assembly (both read only disk); the merge impls are
              UNTOUCHED, the row is never deleted;
          (3) UNRESOLVABLE — no ``subagent_run`` maps the worker_index, OR the map is
              AMBIGUOUS (a wave-local worker_index shared across waves resolves to >1
              key) → RESTORE (fail-safe keep — a wasteful-but-correct include, never a
              wrong exclusion of live work, T-48-05).
        Default ``None`` ⇒ this gate is dormant (no wave orphan exclusion on a
        non-edited / non-wave resume) → byte-identical to (i)-(iii). The join reads the
        SAME owner-scoped ``subagent_runs`` rows the cursor uses (default-deny; no
        cross-owner fragment can enter the allow-set or reach disk — T-48-02).
        """
        store = getattr(ectx, "scoped_store", None)
        if store is None:
            return
        try:
            rows = await store.tree(ectx.run_id)
        except Exception:  # noqa: BLE001 — offline / schema-less → nothing to restore
            return
        _boundaries = boundary_by_agent or {}
        _wave_allow = wave_allow_by_step or {}
        # RESUME-16 independent: build the per-wave-step worker_index → keys join ONCE
        # from the owner-scoped subagent_runs (only when a wave allow-set is supplied, so
        # the default path never reads them → dormant / byte-identical). A worker_index is
        # wave-LOCAL, so it can (rarely) resolve to >1 key across waves in the same step →
        # recorded as a SET; an ambiguous (len>1) resolution is treated as unresolvable
        # (fail-safe RESTORE, case 3).
        _wi_to_keys: dict = {}  # producer_step -> { str(worker_index) -> set(keys) }
        if _wave_allow:
            try:
                _sub_rows = await store.read_subagent_runs(ectx.run_id)
            except Exception:  # noqa: BLE001 — no child rows → every join unresolvable → keep
                _sub_rows = []
            for _sr in _sub_rows or []:
                _pstep = getattr(_sr, "parent_step", None)
                _widx = getattr(_sr, "worker_index", None)
                _key = getattr(_sr, "task_id", None)
                if _pstep is None or _widx is None or _key is None:
                    continue
                _wi_to_keys.setdefault(_pstep, {}).setdefault(str(_widx), set()).add(
                    str(_key)
                )
        # Group by location, keep the max-version row per location (fix-loop re-persist
        # + fan-out fragment versions: the latest content is the disk truth) — subject to
        # the per-agent cumulative boundary above.
        _FILE_KINDS = {"html_file", "file_bundle", "deliverable"}
        latest: dict = {}
        for row in rows or []:
            kind = getattr(row, "kind", None)
            location = getattr(row, "location", None)
            if kind not in _FILE_KINDS or not location:
                continue
            if str(location).startswith(".uploads/"):
                continue  # Phase-47 fence — never re-materialized
            # RESUME-16 cumulative boundary filter (default path leaves this untouched).
            _binfo = _boundaries.get(getattr(row, "producer_agent", None))
            if _binfo is not None:
                if _binfo.get("restore_nothing"):
                    continue  # (iii) p==0 → this agent's deliverable is NOT restored
                _btid = _binfo.get("boundary_task_id")
                if _btid is not None and str(getattr(row, "task_id", None)) != str(_btid):
                    continue  # (ii) only the boundary task's versions are eligible
            # RESUME-16 independent orphan-fragment gate (default path leaves this
            # untouched — _wave_allow empty ⇒ dormant). Keyed on the fragment's
            # producer_step (== the wave step agent id).
            _allow = _wave_allow.get(getattr(row, "producer_step", None))
            if _allow is not None:
                _keys = _wi_to_keys.get(
                    getattr(row, "producer_step", None), {}
                ).get(str(getattr(row, "task_id", None)))
                # EXCLUDE only on an UNAMBIGUOUS resolvable join whose key is NOT in the
                # current-key allow-set (case 2, confidently orphaned). No mapping (None)
                # or an ambiguous (>1) map falls through to RESTORE (case 3, fail-safe).
                if _keys and len(_keys) == 1:
                    if next(iter(_keys)) not in _allow:
                        continue  # (2) confidently orphaned → not restored to disk
            prev = latest.get(location)
            if prev is None or getattr(row, "version", 0) >= getattr(prev, "version", 0):
                latest[location] = row
        for location, row in latest.items():
            try:
                sandbox.write(location, row.content)
            except Exception:  # noqa: BLE001 — a bad row must never break the resume
                continue

    def _compute_cumulative_boundaries(
        self,
        ectx: ExecutionContext,
        ordered_agents: list,
        compiled,
        completed_ordered: "dict[str, list[str]] | None",
    ) -> dict:
        """RESUME-16 cumulative: the per task_loop step re-materialization BOUNDARY.

        The reconciler that turns the ordered completed cursor + the CURRENT (max-version)
        parsed task list into the three-state boundary ``_rematerialize_artifacts_to_disk``
        consumes. For each task_loop step with completed work it computes the common-prefix
        ``p`` (the SAME rule the strategy skip uses — ``task_identity.common_prefix_length``,
        one home) between ``current_keys`` and the completed keys, and emits a boundary ONLY
        when there is a real divergence (``p < len(completed)`` — a completed task exists
        AFTER the boundary). Otherwise global-max already equals the boundary version (the
        last completed task), so the step is left out and the default global-max path stays
        byte-identical (three-state (i)).

          * ``p > 0`` → ``{restore_nothing: False, boundary_task_id: current_keys[p-1]}``
            (== ``completed_ordered[p-1]``): restore that task's version, not the global
            max that embeds deleted-suffix work (Pitfall 4).
          * ``p == 0`` (first task edited/deleted, or inserted at head) →
            ``{restore_nothing: True, boundary_task_id: None}``: restore nothing, every
            task re-runs from a clean basis. NEVER indexes ``current_keys[-1]``.

        Uses the SAME upstream hash as the strategy (``_compute_upstream_context_hash`` via
        ``ectx.runner`` — set before this runs) so ``current_keys`` match what was persisted.
        Fail-safe: any parse/hash failure leaves the step out → default global-max (re-run,
        never a wrong restore). Keys ONLY on generic parsed content (SC-001/INV-1).
        """
        boundaries: dict = {}
        if not completed_ordered:
            return boundaries
        _steps_by_agent = {s.agent_id: s for s in (getattr(compiled, "steps", None) or [])}
        for spec in ordered_agents:
            agent_id = getattr(spec, "id", None)
            done_ordered = completed_ordered.get(agent_id) if agent_id else None
            if not agent_id or not done_ordered:
                continue
            step = _steps_by_agent.get(agent_id)
            if step is None or getattr(step, "strategy", None) != "task_loop":
                continue
            try:
                task_source = getattr(step, "task_source", None)
                source_step = getattr(task_source, "source_step", None)
                parser_name = getattr(task_source, "parser", None) or "heading_tasks"
                if not source_step:
                    continue
                plan_content = self._latest_typed_content(ectx, source_step)
                if plan_content is None:
                    continue
                parser = _CAPABILITY_REGISTRY.resolve("task_parser", parser_name)
                tasks = parser.parse(plan_content)
                if not tasks:
                    continue
                upstream_hash = self._compute_upstream_context_hash(step, ectx)
                ordinals = task_identity.occurrence_ordinals(tasks)
                current_keys = [
                    task_identity.compute_task_key(
                        upstream_hash,
                        task_identity.normalize_task_content(t),
                        ordinals[i],
                    )
                    for i, t in enumerate(tasks)
                ]
                p = task_identity.common_prefix_length(current_keys, done_ordered)
                # Only a real divergence (a completed task AFTER the boundary) needs a
                # non-default restore; otherwise global-max IS the boundary version.
                if p >= len(done_ordered):
                    continue
                if p == 0:
                    boundaries[agent_id] = {
                        "restore_nothing": True,
                        "boundary_task_id": None,
                    }
                else:
                    boundaries[agent_id] = {
                        "restore_nothing": False,
                        "boundary_task_id": current_keys[p - 1],
                    }
            except Exception:  # noqa: BLE001 — fail-safe: default global-max (never wrong-restore)
                boundaries.pop(agent_id, None)
                continue
        return boundaries

    def _compute_wave_orphan_allowsets(
        self,
        ectx: ExecutionContext,
        ordered_agents: list,
        compiled,
        completed_sets: "dict[str, set[str]] | None",
    ) -> dict:
        """RESUME-16 independent: the per wave_scheduler step CURRENT-KEY allow-set.

        The reconciler that turns the CURRENT (max-version) parsed wave task list into the
        current-key allow-set the ``_rematerialize_artifacts_to_disk`` orphan gate
        consumes (keyed on the wave step agent id == a fragment's ``producer_step``). For
        each wave_scheduler step that HAS completed workers (from the skip cursor) it
        parses the current list and computes the SAME content-addressed keys the strategy
        stamps (``compute_task_key`` over the step's own ``upstream_context_hash`` — one
        home) so a completed-but-absent (deleted/edited-out) worker's fragment is
        confidently excluded while every still-current fragment restores.

        Emitted ONLY for a wave step with completed work — dormant otherwise (a step with
        no completed workers has no orphan to exclude). Fail-safe: any parse/hash failure
        leaves the step OUT → the gate is dormant for it → its fragments are all restored
        (fail-safe KEEP, never a wrong exclude — T-48-05). Keys ONLY on generic parsed
        content (SC-001/INV-1).
        """
        allowsets: dict = {}
        if not completed_sets:
            return allowsets
        _steps_by_agent = {s.agent_id: s for s in (getattr(compiled, "steps", None) or [])}
        for spec in ordered_agents:
            agent_id = getattr(spec, "id", None)
            if not agent_id or not completed_sets.get(agent_id):
                continue
            step = _steps_by_agent.get(agent_id)
            if step is None or getattr(step, "strategy", None) != "wave_scheduler":
                continue
            try:
                task_source = getattr(step, "task_source", None)
                source_step = getattr(task_source, "source_step", None)
                # Waves default to the STRUCTURED json_tasks parser (heading_tasks lacks
                # depends_on/conflict_keys) — mirror the strategy's _DEFAULT_PARSER.
                parser_name = getattr(task_source, "parser", None) or "json_tasks"
                if not source_step:
                    continue
                plan_content = self._latest_typed_content(ectx, source_step)
                if plan_content is None:
                    continue
                parser = _CAPABILITY_REGISTRY.resolve("task_parser", parser_name)
                tasks = parser.parse(plan_content)
                if not tasks:
                    continue
                upstream_hash = self._compute_upstream_context_hash(step, ectx)
                ordinals = task_identity.occurrence_ordinals(tasks)
                allowsets[agent_id] = {
                    task_identity.compute_task_key(
                        upstream_hash,
                        task_identity.normalize_task_content(t),
                        ordinals[i],
                    )
                    for i, t in enumerate(tasks)
                }
            except Exception:  # noqa: BLE001 — fail-safe: leave the step out → restore all (keep)
                allowsets.pop(agent_id, None)
                continue
        return allowsets

    async def _first_incomplete_step(
        self, ectx: ExecutionContext, ordered_agents: list, compiled
    ) -> int:
        """Return the index of the FIRST step that is NOT yet complete (D-07).

        A step is COMPLETE when its durable evidence shows it finished before the
        restart — derived (NO new step-status table) from the persisted substrate:

          * its TYPED artifacts exist in the durable graph (``artifact_refs`` whose
            ``producer_agent`` is this step's agent id — the step produced its output);
            and/or its terminal ``step_completed``/``step_reused`` event is in the durable
            ``run_events`` log;
          * a WAVE step (``strategy == "wave_scheduler"``) is complete only when EVERY
            wave it dispatched reached a terminal ``wave_runs`` row AND no worker is left
            mid-flight — but the precise mid-wave worker filter lives in the strategy
            (it re-enters run_fanout with only the incomplete workers). At THIS level a
            wave step with ANY non-terminal/absent wave row is treated as incomplete so
            the loop re-enters it and the strategy does the mid-wave skip.

        The returned index is the resume offset for the SINGLE dispatch loop: every step
        before it is skipped (already done), the loop re-enters at it. When every step is
        already complete the offset is ``len(ordered_agents)`` (nothing left to drive).

        R-11 (v1 scope cut): resumes at the first incomplete step by ORIGINAL array position,
        which assumes each step id appears at most once per run — for a mid-loop/branch
        crash-restart (a step id visited more than once) this may resume at the wrong
        occurrence. Documented v1 limitation, not solved here.
        """
        store = getattr(ectx, "scoped_store", None)

        # Durable run_events (for terminal step events) + the produced-artifact set.
        completed_step_events: set[str] = set()
        # KAN-120-ISSUE1: also track agent_complete events so we can distinguish an
        # agent that COMPLETED (wrote artifact + emitted agent_complete) from one that
        # was stopped BETWEEN artifact-write and agent_complete.  Without this, a
        # single_shot agent that persisted its typed artifact but never fired
        # agent_complete is wrongly classified as complete, and the resume skips it
        # → no data shown for that agent.  agent_complete is persisted in run_events by
        # _RunEventSink.emit() like every other event, so it IS in the durable store
        # for completed agents and ABSENT for agents killed before they emitted it.
        agent_complete_events: set[str] = set()
        terminal_wave_indices_by_step: dict[str, set[int]] = {}
        running_wave_steps: set[str] = set()
        # RESUME-17: the run's durable run_events, captured ONCE so the open-gate
        # override below reuses them (no second round-trip) — [] on the offline harness.
        durable_rows: list = []
        if store is not None:
            try:
                rows = await store.read_events(ectx.run_id, 0)
                durable_rows = rows
                for row in rows:
                    payload = getattr(row, "payload_json", None) or {}
                    if not isinstance(payload, dict):
                        continue
                    row_type = getattr(row, "type", None)
                    if row_type in ("step_completed", "step_reused"):
                        sid = payload.get("step")
                        if sid:
                            completed_step_events.add(sid)
                    # KAN-120-ISSUE1: collect agent_complete events by agent_id so the
                    # single_shot completeness check below can require both artifact
                    # presence AND a terminal agent event (fails closed — never skips an
                    # agent that was stopped mid-execution between artifact-write and the
                    # completion event, which would show "no data" for that step).
                    elif row_type == "agent_complete":
                        aid = payload.get("agent_id")
                        if aid:
                            agent_complete_events.add(aid)
            except Exception:  # noqa: BLE001 — offline / schema-less harness → no evidence
                pass
            try:
                for wr in await store.read_wave_runs(ectx.run_id):
                    sid = getattr(wr, "step", None)
                    widx = getattr(wr, "wave_index", None)
                    status = getattr(wr, "status", None)
                    if sid is None or widx is None:
                        continue
                    if status == "completed":
                        terminal_wave_indices_by_step.setdefault(sid, set()).add(int(widx))
                    else:
                        running_wave_steps.add(sid)
            except Exception:  # noqa: BLE001 — no durable wave evidence → treat as incomplete
                pass

        _steps_by_agent = {s.agent_id: s for s in (compiled.steps or [])}
        # The set of agent ids that produced a durable typed artifact (read from the
        # DURABLE artifact_refs, owner-scoped — on a fresh-process resume the in-memory
        # graph is empty until a step re-runs, so completeness is read from the store).
        produced_agents: set[str] = set()
        # Materialize the durable ref rows ONCE — produced_agents is derived from
        # them here, and the task_loop branch below reuses them for the per-task
        # distinct-task_id count + the source_step plan content (no second round-trip).
        tree_rows: list = []
        if store is not None:
            try:
                tree_rows = list(await store.tree(ectx.run_id))
                for ref in tree_rows:
                    pa = getattr(ref, "producer_agent", None)
                    if pa:
                        produced_agents.add(pa)
            except Exception:  # noqa: BLE001 — no durable refs → treat steps as incomplete
                pass

        # ── RESUME-17 open-gate override (49-02): re-enter AT the gate phase ─────────
        # A gated step whose agent ALREADY produced its typed artifact classifies
        # "complete" at the non-wave produced-disjunct below and would be SKIPPED PAST —
        # but an OPEN review gate at step k IS the resume point (the gated agent produced
        # its output and is PARKED awaiting the human, not finished). Derive the open gate
        # from the SAME durable run_events already read above (no extra round-trip); when a
        # review gate is open, return the gated step so ``_run_agent`` re-enters it in GATE
        # MODE (model-skip, output reconstructed from the persisted max-version ref).
        # Generic keying ONLY: parse the agent id out of
        # ``gate_key = f"{run}:{agent_id}:{visit_count}"`` (:4802) and match
        # ``ordered_agents[j].id`` — zero workflow/agent-name literals (INV-1). R-08: strip
        # BOTH the run_id prefix (first colon) and the visit_count suffix (last colon) rather
        # than a plain ``split(":", 1)[1]`` — a custom-agent id (``custom-agent:<instance_id>``)
        # itself contains a colon, so only the outer two must be peeled. No-op when
        # ``derive_open_gate`` returns ``(None, None)`` ⇒ every non-gate resume offset is
        # byte/event-identical (proven by the branch-(b) resume tests that seed no
        # ``review_gate_ready``).
        _open_kind, _open_gate_key = derive_open_gate(durable_rows)
        if _open_kind == "review" and _open_gate_key:
            _gate_target = _open_gate_key.split(":", 1)[1].rsplit(":", 1)[0]
            for _j in range(len(ordered_agents)):
                if getattr(ordered_agents[_j], "id", None) == _gate_target:
                    return _j

        # NOTE: this is a completeness SCAN, NOT the dispatch loop — it iterates by
        # index (not ``enumerate(ordered_agents)``) so the single-dispatch-loop grep
        # gate (which proves no FORKED dispatch path was introduced, INV-12) stays at 1.
        for i in range(len(ordered_agents)):
            spec = ordered_agents[i]
            agent_id = getattr(spec, "id", None)
            step = _steps_by_agent.get(agent_id)
            strategy = getattr(step, "strategy", None) if step else None

            if strategy == "wave_scheduler":
                # A wave step is complete only when it has at least one terminal wave
                # row AND no wave is left running/absent. Any running/absent wave ⇒
                # re-enter (the strategy applies the mid-wave worker filter).
                if agent_id in running_wave_steps:
                    return i
                if agent_id not in terminal_wave_indices_by_step:
                    # No wave evidence at all → never reached this step → resume here.
                    return i
                # Has terminal waves and none running → consider it complete; continue.
                continue

            if strategy == "task_loop":
                # Task-granular step (RESUME-05): persist_task_html dual-writes an
                # html_file ref with producer_agent=<build agent> from task 1, so the
                # produced_agents membership below CANNOT tell a PARTIAL build (task
                # N<M persisted) from a COMPLETE one — it would classify a crashed-
                # mid-build step complete and the resume offset would SKIP the build
                # (silent deliverable truncation). Completeness is instead task-granular:
                # complete ⟺ a terminal step event exists (retry/step_reused) OR the
                # count of DISTINCT persisted task_ids for this agent >= the task total
                # re-parsed from the DECLARED source_step plan (the same derivation
                # task_loop.run uses). Any uncertainty ⇒ INCOMPLETE (re-enter, never
                # skip): the fail-safe direction is re-run (correct-but-wasteful),
                # because the inverse (skip-on-uncertainty) is the data-loss bug.
                if agent_id in completed_step_events:
                    continue
                try:
                    task_source = getattr(step, "task_source", None)
                    source_step = getattr(task_source, "source_step", None)
                    parser_name = (
                        getattr(task_source, "parser", None) or "heading_tasks"
                    )
                    # No durable store, or the workflow did not DECLARE a source_step
                    # (INV-1: never hard-code a workflow/agent-id fallback here) ⇒ the
                    # total is underivable ⇒ re-enter (fail-safe).
                    if store is None or not source_step:
                        return i
                    plan_content = None
                    for r in tree_rows:
                        if getattr(r, "producer_agent", None) == source_step:
                            plan_content = getattr(r, "content", None)
                    if plan_content is None:
                        return i
                    parser = _CAPABILITY_REGISTRY.resolve("task_parser", parser_name)
                    # max(...,1) mirrors task_loop.run's 0-task → run-once fallback, so
                    # a genuinely-complete 0-task build still classifies complete.
                    expected_total = max(len(parser.parse(plan_content)), 1)
                    # DISTINCT task_ids only — the fix-loop re-persists the same task_id,
                    # so counting rows/versions would over-count (Pitfall 7).
                    distinct_done = len(
                        {
                            getattr(r, "task_id", None)
                            for r in tree_rows
                            if getattr(r, "producer_agent", None) == agent_id
                            and getattr(r, "task_id", None) is not None
                        }
                    )
                except Exception:  # noqa: BLE001 — underivable total ⇒ re-run (never skip)
                    return i
                if distinct_done >= expected_total:
                    continue
                return i

            # Non-wave step: complete iff it produced its typed artifact OR a terminal
            # step event is recorded. Neither ⇒ this is the first incomplete step.
            # KAN-120-ISSUE1: require BOTH produced_agents AND agent_complete_events for
            # the produced-artifact branch — an agent stopped between its artifact-write
            # and its agent_complete emission has the artifact but no completion event;
            # the fail-safe direction is to re-run it (correct-but-wasteful: the
            # content-hash key reuses the prior artifact, so no model credit is wasted)
            # rather than to skip it and show "no data" for that step.
            # completed_step_events (step_completed/step_reused) remain a standalone
            # sufficient signal — retry/reuse events are only emitted after the agent
            # genuinely finished, so they need no agent_complete corroboration.
            complete_by_artifact = (
                agent_id in produced_agents and agent_id in agent_complete_events
            )
            if complete_by_artifact or agent_id in completed_step_events:
                continue
            return i

        # Every step already complete → nothing left to drive.
        return len(ordered_agents)

    async def _compute_resume_completed_task_ids(
        self, ectx: ExecutionContext, ordered_agents: list, compiled
    ) -> "tuple[dict[str, set[str]], dict[str, list[str]]]":
        """RESUME-09: the KERNEL-computed per-step SKIP CURSOR (D-06 discretion).

        Reads the run's OWN owner-scoped durable rows (via ``ectx.scoped_store`` — the
        SAME default-deny helper ``_first_incomplete_step`` uses; a cross-owner row can
        never enter) and returns the completed-identity set PER STEP, keyed on the step's
        agent id, for the strategies to SKIP (the AGENT never decides — SC-001/INV-1):

          * ``task_loop`` step: the DISTINCT ``task_id`` set from ``store.tree`` where
            ``producer_agent == step agent`` — a ``set`` de-dups the fix-loop re-persist
            of the SAME ``task_id`` (Edge-Case 1), exactly the derivation
            ``_first_incomplete_step`` already uses for the completeness count.
          * ``wave_scheduler`` step: the ``task_id`` set from ``read_subagent_runs`` where
            ``parent_step == step agent`` AND ``status == "complete"`` — keyed on the
            plan-global ``task_id`` (unique across waves), NOT the wave-local, ambiguous
            ``worker_index`` (Edge-Case 5). A ``running``/``failed`` worker is NOT
            completed ⇒ re-run (fail-safe direction).

        RESUME-16 cumulative: a ``task_loop`` step ALSO returns its completed keys in
        original production ORDER (``completed_ordered[agent_id]: list[str]``, ordered by
        ``min(version)`` per distinct ``task_id`` — versions are monotonic per kind and a
        task persists after it runs, so version order == build order). The distinct-set
        return is preserved UNCHANGED (waves + completeness read it byte-neutrally); the
        ordered list is the extra emission the task_loop common-prefix reconcile needs.

        Fail-safe = RE-RUN: a read failure or an underivable step leaves that step OUT of
        the dict (best-effort, per-step try/except) so nothing is skipped for it — the
        inverse (skip-on-uncertainty) is the data-loss bug (T-46-04-03). Keys ONLY on
        generic identity (``strategy``/``producer_agent``/``task_id``/``status``) — zero
        workflow-name/agent-id literal (INV-1). LOCAL-derived; the caller stamps it on
        ``ectx`` (INV-2 — no engine per-run state).
        """
        completed: dict[str, set[str]] = {}
        completed_ordered: dict[str, list[str]] = {}
        store = getattr(ectx, "scoped_store", None)
        if store is None:
            return completed, completed_ordered

        _steps_by_agent = {s.agent_id: s for s in (compiled.steps or [])}

        # Materialize each durable source ONCE (owner-scoped; best-effort degrade).
        tree_rows: list = []
        try:
            tree_rows = list(await store.tree(ectx.run_id))
        except Exception:  # noqa: BLE001 — no durable refs → task_loop steps left out (re-run)
            tree_rows = []
        subagent_rows: list = []
        try:
            subagent_rows = list(await store.read_subagent_runs(ectx.run_id))
        except Exception:  # noqa: BLE001 — no durable child rows → wave steps left out (re-run)
            subagent_rows = []

        for spec in ordered_agents:
            agent_id = getattr(spec, "id", None)
            if not agent_id:
                continue
            step = _steps_by_agent.get(agent_id)
            strategy = getattr(step, "strategy", None) if step else None
            try:
                if strategy == "task_loop":
                    _rows = [
                        r
                        for r in tree_rows
                        if getattr(r, "producer_agent", None) == agent_id
                        and getattr(r, "task_id", None) is not None
                    ]
                    done = {str(getattr(r, "task_id", None)) for r in _rows}
                    if done:
                        completed[agent_id] = done
                        # RESUME-16 cumulative: emit the distinct completed keys in build
                        # ORDER (by min(version) per task_id). Pitfall 9: the fix-loop
                        # re-persists a task_id at higher versions, so MIN pins the
                        # first-run version == its position in the build sequence.
                        _min_ver: dict[str, int] = {}
                        for r in _rows:
                            _tid = str(getattr(r, "task_id", None))
                            _v = getattr(r, "version", 0) or 0
                            if _tid not in _min_ver or _v < _min_ver[_tid]:
                                _min_ver[_tid] = _v
                        completed_ordered[agent_id] = sorted(
                            _min_ver, key=lambda t: _min_ver[t]
                        )
                elif strategy == "wave_scheduler":
                    done = {
                        str(getattr(r, "task_id", None))
                        for r in subagent_rows
                        if getattr(r, "parent_step", None) == agent_id
                        and getattr(r, "status", None) == "complete"
                        and getattr(r, "task_id", None) is not None
                    }
                    if done:
                        completed[agent_id] = done
            except Exception:  # noqa: BLE001 — any ambiguity ⇒ leave the step out (re-run)
                completed.pop(agent_id, None)
                completed_ordered.pop(agent_id, None)
        return completed, completed_ordered

    async def _redrain_steering_notes(self, ectx: ExecutionContext) -> None:
        """RESUME-11: re-queue durably-logged-but-undrained steering onto the resumed ectx.

        A mid-run chat steering note reaches a RUNNING run's ectx.steering_notes only via
        the process-local ``_LIVE_ECTX`` registry (``apply_steering``); a backend restart
        drops that in-memory queue. But every chat turn was ALSO persisted as a durable
        ``chat_message`` ``run_events`` row (``_persist_chat_message``, carrying ``text``).
        On resume this re-derives the notes the pre-crash run had NOT yet consumed and
        re-queues them so the FIRST re-dispatch renders them (=== USER GUIDANCE ===).

        Drained-vs-undrained heuristic (the seq compare, ND-9): a dispatched agent turn
        persists a seq'd ``agent_input`` event, so ``last_input_seq = max(seq of
        agent_input rows)`` marks the last point guidance was consumed. A ``chat_message``
        row is UNDRAINED iff its ``seq > last_input_seq`` (no dispatch ran after it
        arrived) AND it carries non-empty ``text`` → re-queued as ``{"text": ...,
        "sticky": False}`` (the ``apply_steering`` append shape). This is NO-LOSS
        (undrained notes survive the restart) AND NO-DUPLICATE (a drained note has
        ``seq < last_input_seq`` → skipped; the engine's own consume-once drain then drops
        each re-queued note after one render).

        CLASSIFICATION BOUND (honest — the durable row lacks the routed channel + sticky):
        ``_persist_chat_message`` records ``text`` but NOT the channel or ``sticky`` (the
        route is derived POST-persist), so a ``chat_message`` row cannot be DEFINITIVELY
        distinguished as steering vs a clarify-answer / gate-action from the row alone.
        This is acceptable for THIS scope because auto-resume (restore_non_terminal_runs
        branch b) only fires for IN-FLIGHT running runs — a ``waiting_for_user`` run takes
        branch (a) (Phase 49), and during a running phase plain-text turns route to
        steering anyway (chat_router.py: PHASE_RUNNING + plain text → CHANNEL_STEERING),
        with no gate-action mid-dispatch. So "text present + seq > last_input_seq" ≈ an
        undrained steering note here. A DRAINED *sticky* note (uploaded-context, which
        re-renders every dispatch by design) has ``seq < last_input_seq`` so this won't
        re-queue it → sticky-on-resume loss is Phase-47 territory (uploads durability),
        NOT fixed here; re-queued notes are one-shot (``sticky=False``), correct for the
        undrained one-shot notes this targets.

        Best-effort + owner-scoped: reads the run's OWN ``ectx.scoped_store`` (default-deny
        — a cross-owner row can never appear); no store / a read failure ⇒ return (leave
        ``steering_notes`` untouched). Dormant on a normal run (called only in the resume
        tier when ``_is_resume``) ⇒ byte/event-identical (INV-3).
        """
        store = getattr(ectx, "scoped_store", None)
        if store is None:
            return
        try:
            rows = await store.read_events(ectx.run_id, 0)
        except Exception:  # noqa: BLE001 — offline / schema-less → nothing to re-derive
            return
        last_input_seq = max(
            (
                int(getattr(r, "seq", 0) or 0)
                for r in (rows or [])
                if getattr(r, "type", None) == "agent_input"
            ),
            default=0,
        )
        for r in rows or []:
            if getattr(r, "type", None) != "chat_message":
                continue
            if int(getattr(r, "seq", 0) or 0) <= last_input_seq:
                continue  # drained pre-crash (no-duplicate) — the seq-compare skip
            payload = getattr(r, "payload_json", None) or {}
            text = payload.get("text") if isinstance(payload, dict) else None
            if not text:
                continue
            ectx.steering_notes.append({"text": text, "sticky": False})

    def _fire_resume_cleanup(self, run_id: str) -> None:
        """Invoke the injected bridge cleanup hook (best-effort, idempotent).

        WR-01: ``restore_non_terminal_runs`` registers the driver task (and the
        live queue) in the process-global WS registries synchronously at the
        ``create_task`` site — so EVERY exit path of ``resume_run`` (including
        the early returns before queue registration and a failed
        ``_resume_register_queue``) must drop those entries, or a done task
        leaks in ``_PIPELINE_TASKS`` forever (a slow registry leak in a
        long-lived process). The app-layer ``_cleanup_pipeline`` pops are
        idempotent (``dict.pop(..., None)``), so calling this on every path —
        including paths where nothing was registered — is safe.
        """
        if self._resume_cleanup is None:
            return
        try:
            self._resume_cleanup(run_id)
        except Exception as _cl_exc:  # noqa: BLE001 — cleanup is best-effort
            logger.warning(
                "resume_run(%s): bridge cleanup failed: %s", run_id, _cl_exc
            )

    def _resolve_resume_cancel_event(self, run_id: str) -> "asyncio.Event | None":
        """Resolve this run's cooperative cancel Event via the injected hook (ISS-084).

        Mirrors ``_fire_resume_cleanup``'s best-effort shape. ``None`` — the hook unset
        (goldens / offline / any non-app driver) or a lookup failure — degrades to the
        historical ``cancel_event=None``, i.e. a DORMANT signal, never a crashed resume.
        """
        if self._resume_cancel_event is None:
            return None
        try:
            return self._resume_cancel_event(run_id)
        except Exception as _ce_exc:  # noqa: BLE001 — a lookup failure must not abort
            logger.warning(
                "resume(%s): cancel-event lookup failed: %s", run_id, _ce_exc
            )
            return None

    async def resume_run(self, run_id: str) -> None:
        """Durably RESUME an interrupted in-flight run IN-PROCESS (RESUME-04 / D-06).

        Called by ``restore_non_terminal_runs`` (branch b) for a resumable run that a
        backend restart left mid-build. Rebuilds the run's ExecutionContext via the SAME
        construction path (``_execute_impl`` — NO copy-paste fork, Pitfall 2: the resumed
        run carries the SAME owner/workspace/pipeline as the original, so new artifacts
        get the original owner_id — T-12-03-RESUMESCOPE) and re-enters the SINGLE per-step
        dispatch loop at the FIRST incomplete step (computed by ``_first_incomplete_step``
        from the durable artifact_refs/run_events/wave_runs rows). Completed steps are
        skipped (their artifacts reused via the 12-02 content-hash key); a completed
        wave's workers are skipped by the wave_scheduler mid-wave filter (WAVE-03).

        The run's identity (pipeline type, user brief, owner, session) is read from the
        durable ``workflow_runs`` row. The resumed events flow through the SAME seq/
        event_id durable sink as a fresh run (so a reconnecting client replays them via
        the 12-03 ``after_seq`` branch). Best-effort: a missing/cross-owner row or a
        compile failure logs and returns (the run stays in its prior state — a later
        manual retry is still possible). Cross-process locks are OUT of scope (N8 v1,
        T-12-03-CROSSNODE).
        """
        from app.models.database import SessionLocal
        from app.models.workflow import WorkflowRun

        db = SessionLocal()
        try:
            wr = db.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
            if wr is None:
                logger.warning("resume_run(%s): no workflow_runs row — skipping", run_id)
                # WR-01: drop the task entry registered at the create_task site.
                self._fire_resume_cleanup(run_id)
                return
            pipeline_type = wr.type
            user_message = wr.input or ""
            user_id = wr.user_id
            session_id = wr.session_id
            parent_run_id = wr.parent_run_id
            # WR-02: the launch-time per-step selections overlay, persisted on the
            # row at run creation (websocket.py, migration 0023). Legacy/non-
            # composed runs are None → the resume takes the has_selections None
            # branch in _apply_selections (engine.py:4538) → byte/event-identical
            # resume (INV-3). Read inside this SAME db session so it closes with
            # the rest (no second session opened).
            #
            # SECURITY (trust=user re-validation): this map was already re-validated
            # trust="user" at LAUNCH (websocket.py:1544 via
            # _revalidate_selections_trust_user) before it was persisted, and
            # _apply_selections re-compiles via WorkflowCompiler().compile(
            # trust="user") AGAIN at overlay time (engine.py:4549) — so the resume
            # overlay can only ever carry user-allowed levers (resume applies LESS
            # privilege, never more). No extra WS-layer pre-check is needed here:
            # the engine-side trust=user re-compile IS the authoritative
            # re-validation on this path (the WS pre-check exists only because the
            # launch path accepts a client-supplied map, whereas resume reads the
            # already-persisted, already-launch-validated map).
            selections = wr.selections_json
            # KAN-120: restore the launch-time od_context (template + design-system
            # data) for OpenDesign pipelines (od_ppt, od_prototype). Persisted at
            # run CREATION by run_commands._drive_launch_to_queue (migration 0027).
            # NULL for non-OD runs → od_context=None passed to _drive_resumed_stream
            # → _execute_impl → ectx.od_context = None (same as before — INV-3).
            od_context = getattr(wr, "od_context_json", None)
            # Restore the launch-time per-run gate selection (migration 0031).
            # NULL → None → _should_gate falls back to the static AGENT.md set,
            # which is the correct default for every run that never overrode it.
            # For a run that DID override it, this is the difference between the
            # gate re-opening on resume and the pending redo being swallowed.
            gate_agent_ids = getattr(wr, "gate_agent_ids_json", None)
        finally:
            db.close()

        # Reconstruct the ordered agent list the same way the WS layer does for a fresh
        # run (registry membership for the run's pipeline type). A custom-workflow run
        # without a static membership degrades to an empty list → nothing to resume.
        from agents.registry import get_pipeline_agents

        try:
            agents = get_pipeline_agents(resolve_alias(pipeline_type))
        except Exception as exc:  # noqa: BLE001 — unknown pipeline → cannot resume
            logger.warning("resume_run(%s): cannot resolve agents (%s)", run_id, exc)
            # WR-01: drop the task entry registered at the create_task site.
            self._fire_resume_cleanup(run_id)
            return
        if not agents:
            # ── Roster seam (twin of the execute() roster seam at ~line 1473): the
            # compiled plan is the single source of the run's agent roster. For a
            # composed workflow (steps are instances of an agent template, e.g.
            # `custom-agent:facts`, with no AGENT.md on disk) the registry has no
            # static membership and returns `[]` above — that alone doesn't mean
            # there's nothing to resume, so fall back to the compiled plan before
            # giving up.
            try:
                compiled = compile_for_run(pipeline_type)
            except Exception as exc:  # noqa: BLE001 — cannot compile → cannot resume
                logger.warning("resume_run(%s): cannot compile plan (%s)", run_id, exc)
                self._fire_resume_cleanup(run_id)
                return
            if compiled.steps:
                agents = self._specs_from_plan(compiled.steps)
        if not agents:
            logger.warning("resume_run(%s): empty agent list — nothing to resume", run_id)
            # WR-01: drop the task entry registered at the create_task site.
            self._fire_resume_cleanup(run_id)
            return

        # ── Compute the resume offset from the durable substrate ─────────────────────
        # Build a TEMP ExecutionContext carrying just the run id + scoped store so the
        # offset computation can read the durable artifact_refs/run_events/wave_runs. The
        # full context is rebuilt by _execute_impl below (the single construction path).
        offset = await self._compute_resume_offset(
            run_id, user_id, session_id, pipeline_type, agents
        )

        logger.info(
            "resume_run(%s): resuming pipeline=%s at step offset %d/%d",
            run_id, pipeline_type, offset, len(agents),
        )
        if offset >= len(agents):
            # Every step already complete — finalize without re-driving any agent.
            logger.info("resume_run(%s): all steps complete — nothing to re-drive", run_id)

        # ── Seed the resume seq counter PAST the durable tail (CR-01 / RESUME-03) ─────
        # The pre-restart run already persisted run_events at seq 1..N (plus the
        # run_resuming marker at max(seq)+1). Re-using itertools.count(1) would make
        # every resumed event collide with seq 1..N (run_events has no unique
        # constraint), so a reconnecting client that sends after_seq=N (its last
        # pre-crash seq) would never receive ANY resumed event (they all carry seq <= N).
        # Read the durable tail under the SAME owner+workspace scope the engine sink
        # wrote the rows under (recover the ORIGINAL workspace_id, NOT a fresh
        # create_workspace id — binding drift, Pitfall 2 / IN-04) and seed the counter at
        # max(seq)+1 so resumed events continue the monotonic per-run seq. Best-effort:
        # any read failure (offline harness with no DB / no durable tail) degrades to
        # start=1 — a resume on an offline run has no durable tail to collide with, so
        # seq 1 is correct there (byte/event-identical to the prior behavior).
        start = 1
        try:
            owner_id = user_id or f"anon:{session_id or run_id}"
            workspace_id = await self._recover_workspace_id(owner_id, run_id)
            tail_store = ScopedStore(owner_id=owner_id, workspace_id=workspace_id)
            existing = await tail_store.read_events(run_id, after_seq=0)
            start = max((r.seq for r in existing), default=0) + 1
        except Exception as exc:  # noqa: BLE001 — no durable tail → start=1 (offline)
            logger.debug(
                "resume_run(%s): durable-tail read failed (%s) → seeding seq at 1",
                run_id, exc,
            )
            start = 1

        # ── 12-09 Gap 2a: register the run's LIVE queue via the injected bridge
        # BEFORE the drive loop, so a reconnect mid-resume finds a live queue and
        # the live-attach drainer receives the resumed tail in real time
        # (mirroring the run_pipeline queue contract). Dormant when the hook is
        # unset (offline/no-WS → byte/event-identical to the queue-less drive).
        live_queue: asyncio.Queue | None = None
        if self._resume_register_queue is not None:
            try:
                live_queue = self._resume_register_queue(run_id)
            except Exception as _q_exc:  # noqa: BLE001 — bridge is best-effort
                logger.warning(
                    "resume_run(%s): live-queue registration failed: %s",
                    run_id, _q_exc,
                )
                live_queue = None

        # ── WR-02 (RESOLVED — quick-260615-dzk) ──────────────────────────────────────
        # ``resume_run`` now reads the launch-time ``selections`` overlay persisted on
        # the ``workflow_runs`` row (``selections_json``, migration 0023) and re-threads
        # it through ``_execute_impl`` → ``_apply_selections`` (trust="user" re-compile)
        # below — so a backend-restart-resumed run re-applies the SAME user-composed
        # levers (selected validators / gates / per-step model / retry) it ran pre-crash.
        # None/empty selections (every legacy/non-composed run) take the ``has_selections``
        # None branch in ``_apply_selections`` → the plan is unchanged → byte/event-
        # identical resume (INV-3). The overlay is privilege-bounded by construction (the
        # trust="user" re-compile rejects any over-privileged lever).
        #
        # ── Re-drive through the SAME seq/event sink as a fresh run (so resumed events
        # persist + replay via the after_seq branch). _execute_impl rebuilds the
        # ExecutionContext via its one construction path and skips i < offset. ─────────
        # ── RESUME-10: a resumed run is a first-class LIVE run ────────────────────────
        # resume_run bypasses the execute() wrapper (it drives _execute_impl directly),
        # so the wrapper's live-layer threading + DEF-43-03-1 milestone-card loop never
        # reached a resumed run. Replicate them HERE from the app-injected hooks:
        #   * arm the sink with the injected milestone_sink so narrator cards project;
        #   * a MANUAL next_seq allocator (NOT itertools.count) so the loop can advance
        #     PAST a card's persisted seq — otherwise the engine's next base event would
        #     reuse the card's seq, collide on the 0024 (run_id, seq) constraint, and
        #     (persist being best-effort) be silently DROPPED → a durable-log gap on
        #     reconnect (DEF-43-03-1 / Edge-Case 7);
        #   * thread live_ectx_register into _execute_impl (the :1184 consumer registers
        #     the rebuilt ectx when the callback is present) so _live_ectx_for_run
        #     resolves the resumed run for steering / per-turn images / Concierge;
        #   * unregister in the finally below (guaranteed — no _LIVE_ECTX leak, WR-01).
        # All three hooks None (offline / non-app drivers, the goldens) ⇒ the resume
        # live-wire is DORMANT: no card branch fires, next_seq increments 1,2,3,… exactly
        # like the old itertools.count, and no register/unregister runs (byte/event-
        # identical resume, INV-3). Card seq is drawn from the store's own allocator (via
        # emit_milestone_card), never append_event_next_seq for the engine's base events.
        # Re-drive through the SHARED resume stream (INV-12 — the SAME sink/seq/live-queue/
        # milestone-card loop the clarify re-arm driver uses). ``_resume_from=offset`` +
        # ``_is_resume=True`` is the review/mid-build re-entry; ``_clarify_replay`` stays
        # None here (byte/event-identical to the pre-extraction resume_run).
        await self._drive_resumed_stream(
            run_id,
            agents=agents,
            user_message=user_message,
            pipeline_type=pipeline_type,
            user_id=user_id,
            session_id=session_id,
            parent_run_id=parent_run_id,
            selections=selections,
            od_context=od_context,
            gate_agent_ids=gate_agent_ids,
            start_seq=start,
            live_queue=live_queue,
            _resume_from=offset,
            _is_resume=True,
        )

    async def _drive_resumed_stream(
        self,
        run_id: str,
        *,
        agents: list,
        user_message: str,
        pipeline_type: str,
        user_id: str | None,
        session_id: str | None,
        parent_run_id: str | None,
        selections: dict | None,
        od_context: dict | None = None,
        gate_agent_ids: list[str] | None = None,
        start_seq: int,
        live_queue: "asyncio.Queue | None",
        _resume_from: int = 0,
        _is_resume: bool = False,
        _clarify_replay: dict | None = None,
    ) -> None:
        """Drive ``_execute_impl`` through the resume seq/persist/live-queue/milestone-card
        sink — the SHARED re-entry stream of BOTH restart drivers (INV-12).

        ``resume_run`` (branch b / review re-entry) drives with ``_resume_from=offset,
        _is_resume=True``; ``_replay_clarify_run`` (RESUME-17 clarify twin) drives from
        planning with ``_clarify_replay`` set (replay the durable open round, no LLM
        re-gen). Resumed events persist + replay via the ``after_seq`` branch (a
        reconnecting client sees the tail); ``next_seq`` is a MANUAL allocator that
        advances PAST any narrator milestone card so the engine's next base event never
        reuses a card's seq (DEF-43-03-1). WR-01: the ``finally`` ALWAYS drops the
        queue/task/live-ectx registry entries (no leak on any exit path). All app hooks
        None (offline / goldens) ⇒ this whole stream is DORMANT and byte/event-identical
        to a queue-less drive (INV-3); ``_clarify_replay=None`` ⇒ byte-identical to the
        pre-extraction ``resume_run`` drive.
        """
        sink = _RunEventSink(milestone_sink=self._resume_milestone_sink)
        next_seq = start_seq
        # ── ISS-084: the cooperative STOP signal, resolved HERE because this is the ONE
        # funnel every resume driver (resume_run branch (b), _rearm_gate_run branch (a),
        # _replay_clarify_run, the user POST /resume wrapper) reaches _execute_impl
        # through — so a future resume driver inherits the fix instead of re-opening the
        # hole. Without it _execute_impl bound its None default and all twelve cooperative
        # guards short-circuited: Stop, POST /cancel, SIGTERM and a restart were ALL no-ops
        # for any run that had crossed a restart, and one measured run billed 7.5M tokens
        # after the API answered `cancelled: true`. The hook returns the SAME Event object
        # the REST endpoint sets; None (goldens / offline) ⇒ DORMANT, byte/event-identical.
        cancel_event = self._resolve_resume_cancel_event(run_id)
        try:
            async for event in self._execute_impl(
                agents=agents,
                user_message=user_message,
                pipeline_run_id=run_id,
                pipeline_type=pipeline_type,
                cancel_event=cancel_event,
                user_id=user_id,
                session_id=session_id,
                parent_run_id=parent_run_id,
                # WR-02: re-thread the persisted launch selections through the
                # SHARED _apply_selections overlay seam (engine.py:1140) — no fork,
                # the launch path uses the exact same kwarg (INV-12). None/empty →
                # _apply_selections returns the plan unchanged → INV-3 parity.
                selections=selections,
                # KAN-120: restore the launch-time od_context so OpenDesign agents
                # (od-ppt-*, prototype-*) receive their template + DS context on
                # resume. None for non-OD runs → ectx.od_context=None (INV-3).
                od_context=od_context,
                # Restore the launch-time gate selection so a gate that exists
                # only via the per-run override still exists after a restart.
                # None (every run that never overrode it) → the static AGENT.md
                # set, unchanged (INV-3).
                gate_agent_ids=gate_agent_ids,
                _sink=sink,
                _resume_from=_resume_from,
                _is_resume=_is_resume,
                _clarify_replay=_clarify_replay,
                live_ectx_register=self._resume_live_ectx_register,
            ):
                data = event.get("data")
                if not isinstance(data, dict):
                    data = {}
                    event["data"] = data
                seq = next_seq
                next_seq += 1
                event_id = str(uuid.uuid4())
                data["seq"] = seq
                data["event_id"] = event_id
                # FIX-240 (ISS-121): re-stamp the seq the row ACTUALLY landed on and
                # advance the allocator past it — a resumed run is exactly as exposed to
                # the chat lane's concurrent seq allocation as a launched one, and the
                # live push below carries data["seq"] onto the wire. Same contract as the
                # execute() wrapper (engine.py:1065).
                actual_seq = await sink.persist(seq, event_id, event.get("type", ""), data)
                if actual_seq is not None and actual_seq != seq:
                    data["seq"] = actual_seq
                    if actual_seq >= next_seq:
                        next_seq = actual_seq + 1
                # 12-09 Gap 2a: ALSO push the resumed event onto the WS live
                # queue (when the bridge is wired) so a connected/reconnecting
                # client receives the resumed tail incl. pipeline_complete in
                # real time — not only via a manual durable-tail replay.
                if live_queue is not None:
                    try:
                        live_queue.put_nowait(
                            {"type": event.get("type", ""), "data": data}
                        )
                    except Exception:  # noqa: BLE001 — live push is best-effort
                        pass
                # RESUME-10 (DEF-43-03-1): project + persist a chat_reply milestone card
                # for this event via the INJECTED narrator sink (self-filtering; DORMANT
                # when _resume_milestone_sink is None). The card is persisted at the store's
                # next contiguous seq (max+1), so ADVANCE next_seq PAST it — the engine's
                # next base event can then never reuse the card's seq (a collision would
                # drop that event → durable-log gap). The card is ALSO pushed onto the WS
                # live queue (the driver is a coroutine, NOT a generator — it delivers live
                # via live_queue, not yield), stamped with the SAME event_id the persisted
                # DB row carries so a reconnect replay dedups it (FIX-175).
                card_result = await sink.emit_milestone_card(event)
                if card_result is not None:
                    _created, _card_seq, _card, _reply_eid = card_result
                    if _card_seq >= next_seq:
                        next_seq = _card_seq + 1
                    if _created and live_queue is not None:
                        try:
                            live_queue.put_nowait(
                                {
                                    "type": "chat_reply",
                                    "data": {
                                        **_card,
                                        "seq": _card_seq,
                                        "event_id": _reply_eid,
                                    },
                                }
                            )
                        except Exception:  # noqa: BLE001 — live push is best-effort
                            pass
        except Exception as exc:  # noqa: BLE001 — a resume failure must not crash startup
            logger.warning("resumed-stream drive(%s) failed mid-drive: %s", run_id, exc)
        finally:
            # End-of-stream: the None sentinel terminates the live drainer
            # (matching the run_pipeline contract), then the injected cleanup
            # drops the queue+task registry entries so a finished resume never
            # leaves a stale live registration (no unbounded queue).
            if live_queue is not None:
                try:
                    live_queue.put_nowait(None)
                except Exception:  # noqa: BLE001
                    pass
            # WR-01: cleanup is gated on the HOOK, not the queue — a failed
            # ``_resume_register_queue`` (live_queue None) must still drop the
            # task entry registered at the restore create_task site, or the
            # done task leaks in the process-global registry.
            self._fire_resume_cleanup(run_id)
            # RESUME-10 (WR-01): ALWAYS deregister the resumed run's live ectx
            # (normal completion, mid-drive exception, or the offset==len early
            # path) so the process-local _LIVE_ECTX registry never leaks a
            # terminated run's context — mirroring the execute() wrapper's finally.
            # DORMANT when the hook is None (offline / non-app drivers, the goldens)
            # — a no-op that cannot perturb the resume (INV-3).
            if self._resume_live_ectx_unregister is not None:
                try:
                    self._resume_live_ectx_unregister(run_id)
                except Exception:  # noqa: BLE001 — teardown must never mask the outcome
                    logger.warning(
                        "resumed-stream drive(%s): live_ectx_unregister failed", run_id,
                        exc_info=True,
                    )
            # BUG-R03: persist the terminal OUTPUT-bearing columns (output/agent_outputs/
            # token_usage/duration/deliverable_*) from the durable run_events tail via the
            # INJECTED app-layer sink — the resume tier is otherwise structurally silent on
            # every output column (only the engine state machine wrote status), so a
            # restart auto-resumed completion (branch b) read empty from /chain-context,
            # /summary, analytics + export. Keyed on run_id ONLY (SC-001 — the kernel maps
            # no column, names no workflow); the app callback reads the owner-scoped tail +
            # applies the SAME mapping the launch driver uses (INV-12). DORMANT when the hook
            # is None (offline / goldens / non-app drivers) → byte/event-identical resume
            # (INV-3). Best-effort: a persist error must never mask the drive outcome.
            if self._resume_output_persist_sink is not None:
                try:
                    await self._resume_output_persist_sink(run_id)
                except Exception:  # noqa: BLE001 — persistence must never crash the resume
                    logger.warning(
                        "resumed-stream drive(%s): output-column persist failed", run_id,
                        exc_info=True,
                    )

    async def _replay_clarify_run(self, run_id: str) -> None:
        """Clarify re-arm REPLAY driver (RESUME-17 clarify twin, PINNED A5).

        Spawned by ``_rearm_gate_run`` for a restart-parked run whose durable open gate is
        a clarify ``questionnaire_ready`` (no ``questionnaire_complete``). Unlike the review
        re-entry, clarify is PRE-DISPATCH: a resumed run skips planner+clarify (engine.py:
        1708), so a clarify-parked run cannot route through the review offset override. This
        driver instead REPLAYS the durable open round: it re-drives ``_execute_impl`` from
        planning with ``_clarify_replay`` set, so Step 3 re-emits the SAME questions from the
        durable payload (NO ``_generate_questions`` LLM re-gen), re-enters the store wait, and
        — on answers (via the UNCHANGED ``POST /answers`` → ``set_questionnaire_responses``
        seam) — merges via the EXISTING ``ClarifyEngine._merge_answers``/``_persist_qa``
        helpers (INV-12) and proceeds into the normal dispatch exactly as a never-restarted
        run. It is DISTINCT from ``resume_run`` on purpose (the KAN-88 twin spies resume_run
        and asserts it is never driven). Reuses the SHARED ``_drive_resumed_stream`` loop.
        """
        from app.models.database import SessionLocal
        from app.models.workflow import WorkflowRun

        db = SessionLocal()
        try:
            wr = db.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
            if wr is None:
                logger.warning(
                    "_replay_clarify_run(%s): no workflow_runs row — skipping", run_id
                )
                self._fire_resume_cleanup(run_id)
                return
            pipeline_type = wr.type
            user_message = wr.input or ""
            user_id = wr.user_id
            session_id = wr.session_id
            parent_run_id = wr.parent_run_id
            selections = wr.selections_json
            # Same restore as resume_run (migration 0031) — this driver re-enters
            # the same dispatch loop, so it needs the same gate selection.
            gate_agent_ids = getattr(wr, "gate_agent_ids_json", None)
            owner_id = wr.owner_id or wr.user_id or f"anon:{wr.session_id or run_id}"
            workspace_id = wr.workspace_id
        finally:
            db.close()

        # Resolve the ordered agent list the same way a fresh run does (registry
        # membership). A custom-workflow run without a static membership degrades to an
        # empty list → nothing to drive.
        from agents.registry import get_pipeline_agents

        try:
            agents = get_pipeline_agents(resolve_alias(pipeline_type))
        except Exception as exc:  # noqa: BLE001 — unknown pipeline → cannot replay
            logger.warning(
                "_replay_clarify_run(%s): cannot resolve agents (%s)", run_id, exc
            )
            self._fire_resume_cleanup(run_id)
            return
        if not agents:
            logger.warning(
                "_replay_clarify_run(%s): empty agent list — nothing to replay", run_id
            )
            self._fire_resume_cleanup(run_id)
            return

        # Extract the durable open round's questions + round from the last unresolved
        # ``questionnaire_ready`` payload (owner+workspace scoped, mirroring
        # _is_resumable_in_flight). Confirm the gate is STILL a clarify gate (defensive —
        # a review gate would route through resume_run, not here).
        try:
            store = ScopedStore(owner_id=owner_id, workspace_id=workspace_id)
            rows = await store.read_events(run_id, after_seq=0)
        except Exception:  # noqa: BLE001 — no durable substrate → nothing to replay
            rows = []
        open_kind, _open_gate_key = derive_open_gate(rows)
        if open_kind != "questionnaire":
            logger.warning(
                "_replay_clarify_run(%s): no open questionnaire gate — skipping", run_id
            )
            self._fire_resume_cleanup(run_id)
            return

        questions: list = []
        round_num = 1
        for r in rows:
            if getattr(r, "type", None) == "questionnaire_ready":
                _p = getattr(r, "payload_json", None) or {}
                if isinstance(_p, dict):
                    questions = _p.get("questions") or questions
                    round_num = _p.get("round") or round_num
        if not questions:
            # The gate derived open but carries no replayable questions (malformed durable
            # payload). Leave the run parked untouched rather than drive an empty replay.
            logger.warning(
                "_replay_clarify_run(%s): open gate has no durable questions — leaving "
                "parked", run_id,
            )
            self._fire_resume_cleanup(run_id)
            return

        # Seed the resumed seq PAST the durable tail (CR-01) so the re-emitted
        # questionnaire_ready + the post-answer dispatch events carry seq > the pre-restart
        # tail (a reconnecting client replays them via the after_seq branch).
        start = 1
        try:
            _tail_ws = await self._recover_workspace_id(owner_id, run_id)
            tail_store = ScopedStore(owner_id=owner_id, workspace_id=_tail_ws)
            existing = await tail_store.read_events(run_id, after_seq=0)
            start = max((r.seq for r in existing), default=0) + 1
        except Exception as exc:  # noqa: BLE001 — no durable tail → start=1 (offline)
            logger.debug(
                "_replay_clarify_run(%s): durable-tail read failed (%s) → seq 1",
                run_id, exc,
            )
            start = 1

        # Register the run's LIVE queue BEFORE the drive (mirroring resume_run) so a
        # reconnect mid-replay finds a live queue. Dormant when the hook is unset.
        live_queue: asyncio.Queue | None = None
        if self._resume_register_queue is not None:
            try:
                live_queue = self._resume_register_queue(run_id)
            except Exception as _q_exc:  # noqa: BLE001 — bridge is best-effort
                logger.warning(
                    "_replay_clarify_run(%s): live-queue registration failed: %s",
                    run_id, _q_exc,
                )
                live_queue = None

        # Re-drive from planning with the durable open round REPLAYED (no LLM re-gen). The
        # SHARED stream persists/live-pushes every event and, on answers, proceeds into the
        # normal dispatch. WR-01 cleanup is handled inside _drive_resumed_stream's finally.
        await self._drive_resumed_stream(
            run_id,
            agents=agents,
            user_message=user_message,
            pipeline_type=pipeline_type,
            user_id=user_id,
            session_id=session_id,
            parent_run_id=parent_run_id,
            selections=selections,
            gate_agent_ids=gate_agent_ids,
            start_seq=start,
            live_queue=live_queue,
            _resume_from=0,
            _is_resume=False,
            _clarify_replay={"questions": questions, "round": round_num},
        )

    async def _compute_resume_offset(
        self, run_id, user_id, session_id, pipeline_type, agents
    ) -> int:
        """Build a minimal scoped context + compiled plan and return the resume offset.

        Reads the durable substrate (artifact_refs/run_events/wave_runs) via a temp
        ExecutionContext to find the first incomplete step. Kept SEPARATE from the full
        _execute_impl build so the offset is known BEFORE the dispatch loop re-enters
        (the loop needs the offset as a parameter). Best-effort: any failure → offset 0
        (re-drive from the start; completed steps are then reused via the content-hash
        key, so re-driving from 0 is still correct, just less efficient — D-09).
        """
        try:
            owner_id = user_id or f"anon:{session_id or run_id}"
            scoped_store = ScopedStore(owner_id=owner_id)
            # Use the ORIGINAL workspace_id (the durable rows were written under it) so
            # the offset's owner+workspace-scoped reads see the pre-restart state — NOT
            # a fresh create_workspace id (binding drift, Pitfall 2).
            workspace_id = await self._recover_workspace_id(owner_id, run_id)
            if workspace_id is None:
                try:
                    workspace_id = await scoped_store.create_workspace(run_id)
                except Exception:  # noqa: BLE001 — offline harness has no workflow_runs FK
                    workspace_id = None
            scoped_store._workspace_id = workspace_id
            tmp = ExecutionContext(
                run_id=run_id,
                owner_id=owner_id,
                disk_principal=user_id or "anon",
            )
            tmp.workspace_id = workspace_id
            tmp.scoped_store = scoped_store
            # _first_incomplete_step reads the durable artifact_refs/run_events/wave_runs
            # directly off the scoped store (the in-memory graph is empty on a fresh
            # process — completeness comes from the durable substrate).
            compiled = compile_for_run(pipeline_type)
            # ── Roster seam (twin of the execute() roster seam at ~line 1473): the
            # compiled plan is the single source of the run's agent roster. For a
            # composed workflow (steps are instances of an agent template, e.g.
            # `custom-agent:facts`, with no AGENT.md on disk) the registry-sourced
            # `agents` passed in here is `[]`, so `self._resolver.validate(agents)`
            # below would validate an empty roster and resume would die with "empty
            # agent list — nothing to resume". Rebuild `agents` from the compiled
            # plan exactly as execute() does, guarded the same way.
            if compiled.steps:
                agents = self._specs_from_plan(compiled.steps)
            from agents.execution_engine.resolver import WorkflowResolver  # noqa: F401

            validation = self._resolver.validate(agents)
            ordered_agents = validation.dag or list(agents)
            return await self._first_incomplete_step(tmp, ordered_agents, compiled)
        except Exception as exc:  # noqa: BLE001 — cannot derive offset → re-drive from 0
            logger.warning(
                "resume_run(%s): offset computation failed (%s) → resuming from 0",
                run_id, exc,
            )
            return 0

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
        before so every caller (the generic context injector / _build_context_sources /
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

    async def _seed_workflow_context(
        self, ectx: ExecutionContext, compiled: CompiledWorkflow
    ) -> None:
        """Invoke each declared workflow context provider once at run entry (INV-1).

        The provider seam replaces the inline L4 parent-run seed on the routed path:
        ``previous_run.load(ctx)`` runs the L16 ownership gate (assert_owns) BEFORE
        seeding the parent spec/design/tasks into this run's sandbox, propagating a
        cross-owner ``PermissionError`` (never swallowed). ``opendesign.load(ctx)``
        is a side-effect-free read (its blocks are re-composed per-agent by the
        generic injector), so invoking it here is harmless. Any non-ownership error
        degrades (a missing/TTL-swept parent must never break a revision).
        """
        for name in (compiled.context_providers or []):
            try:
                provider = _CAPABILITY_REGISTRY.resolve("context_provider", name)
            except (KeyError, RuntimeError):
                continue
            try:
                await provider.load(ectx)
            except PermissionError:
                raise  # L16 cross-owner denial — propagate, never swallow
            except Exception as exc:  # noqa: BLE001 — never break a run on a provider read
                logger.warning(
                    "_seed_workflow_context: provider %s.load failed (%s) — continuing",
                    name, exc,
                )

    async def _compose_context_message(
        self,
        spec,
        index: int,
        ordered_agents: list,
        user_message: str,
        planning_context: dict,
        ectx: ExecutionContext,
    ) -> str:
        """Generic context injector (INV-1) — the sole per-agent context-composition path.

        Composes the per-agent context message from the workflow-AGNOSTIC mechanics
        (user brief + planning context + consumed upstream outputs + the build-loop
        ``=== CURRENT TASK ===`` block) PLUS the OD/template/example blocks sourced
        from the declared ``context_provider`` capabilities — ``registry.resolve(
        "context_provider", name).load(ctx)`` for each name in the run's
        ``compiled.context_providers``, composed in declared order. The former L12 per-
        pipeline od/template/example injection branches were deleted from the kernel in
        07-05; this injector replaced them. The ``opendesign`` provider yields the ``{block-name -> content}`` map
        (ACTIVE DESIGN SYSTEM / ACTIVE TEMPLATE / TEMPLATE EXAMPLE / injection parts);
        the ``previous_run`` provider returns ``{}`` (its effect is the parent-run
        seed performed once at run entry, not injected text).

        Only an agent that DECLARES the relevant inject (``injects`` on its AGENT.md)
        receives the OD blocks — the provider is consulted only when the agent opts
        in, mirroring the L12 ``injects`` gate. The build-task-2+ skip (compaction)
        rides the strategy / the engine's per-task scratch, not here.
        """
        # ── Agnostic base: user brief + planning context + consumed outputs ───────
        # POSITIONAL first-agent check (Pitfall 1, INV-1): index == 0 is the
        # workflow-agnostic "first agent in the run" predicate — NOT a spec.id name
        # branch. Rewritten from the former positional first-agent-id comparison so the
        # kernel agent-id-equality grep cleanly returns 0 (the banned-pattern hard-fail
        # gate, Task 3, does not false-match). Behavior identical: the first dispatched
        # agent (index 0) interprets the raw cross-pipeline brief; downstream agents
        # (index > 0) get the stripped clean brief.
        is_first_agent = (len(ordered_agents) == 0 or index == 0)
        if not is_first_agent and "=== CONTEXT FROM PREVIOUS PIPELINE" in user_message:
            clean_brief = user_message.split("\n\n=== CONTEXT FROM PREVIOUS PIPELINE")[0].strip()
            effective_message = clean_brief
        else:
            effective_message = user_message

        parts = [f"=== ORIGINAL USER REQUEST ===\n{effective_message}\n=== END REQUEST ==="]

        # ── [R-28] Retry feedback block ──────────────────────────────────────────
        # Present only when a conditional gate jumped BACKWARD to this step (the
        # dispatch loop stashed it in ``ectx.pending_route_feedback`` keyed by target
        # id). Popped, so it is delivered exactly once per jump and a later pass never
        # replays a stale reason. Sits directly under the brief because it is the most
        # actionable thing this dispatch knows.
        #
        # Two halves: the AUTOMATIC part (which step sent it back, that step's decision
        # and output, and which pass this is) is composed from data the kernel already
        # holds, so every loop gets it with nothing authored; the AUTHORED part is the
        # outcome's optional ``feedback:`` string. A workflow with no backward jump
        # never populates the store, so the composed context is byte-identical to
        # pre-R-28 for every existing manifest and golden fixture.
        _fb_store = getattr(ectx, "pending_route_feedback", None) or {}
        _fb = _fb_store.pop(getattr(spec, "id", None), None) if _fb_store else None
        if _fb:
            _fb_lines = [
                f"=== RETRY — pass {_fb['pass_number']} of {_fb['max_passes']} ==="
            ]
            _fb_lines.append(
                f"Step {_fb['from_step']!r} sent you back here"
                + (f" with decision {_fb['decision']!r}." if _fb.get("decision") else ".")
            )
            if _fb.get("from_output"):
                _fb_lines.append(f"That step's output was:\n{_fb['from_output']}")
            if _fb.get("authored"):
                _fb_lines.append(f"\nWhat to change:\n{_fb['authored']}")
            _fb_lines.append(
                "\nYour previous answer was rejected. Address the above and produce a "
                "DIFFERENT answer — repeating it will fail again."
            )
            _fb_lines.append("=== END RETRY ===")
            parts.append("\n".join(_fb_lines))

        # A composed step carries its own authored prompt; when no planner actually ran the
        # "Planning Context" block is a verbatim echo of the brief above, so suppress it.
        # Registry agents declare no step prompt -> unchanged (R-16 parity, cf. :3814).
        _own_prompt = getattr(getattr(ectx, "current_step", None), "prompt", "") or ""

        if (planning_context
                and not planning_context.get("planner_timed_out")
                and (planning_context.get("planner_ran", True) or not _own_prompt)):
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

        # ── OD blocks via the declared context_provider capabilities (INV-1) ─────
        # Consulted only when this agent declares an inject (the L12 injects gate).
        injects = getattr(spec, "injects", []) or []
        if injects:
            # Thread the consuming agent's OPAQUE tool set onto the ExecutionContext
            # before the provider loop (D-03 per-run-state-on-ctx, the same dynamic-attr
            # mechanism used for ectx.compiled_context_providers above). The opendesign
            # provider gates its builder-only example + the task-2+ suppression on this
            # tool set + the already-populated ectx.build_task_number — NOT on spec.id /
            # pipeline_type (INV-1: the kernel passes the opaque tools, the provider does
            # the gating). This is exactly how the legacy L12 branch identified the build
            # agent (`set(spec.tools) & {"prototype_emit_only", "prototype"}`).
            ectx.current_spec_tools = set(getattr(spec, "tools", []) or [])
            # CR-02 (07-09): thread the consuming agent's DECLARED injects onto the ctx
            # so the opendesign provider can restore the legacy per-block per-injects
            # gate (DS requires "design_system" in injects; template/example/parts
            # require "template" in injects) — the SAME D-03 per-run-state-on-ctx
            # mechanism as current_spec_tools, NOT a spec.id/pipeline_type branch (INV-1).
            ectx.current_spec_injects = set(injects)
            provider_names = list(getattr(ectx, "compiled_context_providers", []) or [])
            for name in provider_names:
                try:
                    provider = _CAPABILITY_REGISTRY.resolve("context_provider", name)
                except (KeyError, RuntimeError):
                    continue
                try:
                    blocks = await provider.load(ectx)
                except PermissionError:
                    raise
                except Exception as exc:  # noqa: BLE001 — a provider read must not abort the agent
                    logger.warning("context provider %s.load failed (%s) — skipping", name, exc)
                    continue
                for block_name, content in (blocks or {}).items():
                    if not content:
                        continue
                    # CR-04 (07-09): a RAW-prefixed block is PRE-WRAPPED (it carries its
                    # own `=== ... ===` envelope) — append it verbatim, never re-wrap. The
                    # legacy engine did `parts.append(part)` for the injection parts.
                    if block_name.startswith(_RAW_BLOCK_PREFIX):
                        parts.append(content)
                        continue
                    # WR-03 (07-09): the END marker is BARE — the legacy END markers
                    # carried NEITHER the `: {id}` suffix NOR the `(SKILL.md)` /
                    # `(example.html)` parenthetical the OPEN marker has. Legacy bytes:
                    #   `=== ACTIVE DESIGN SYSTEM: default ===`     -> `=== END ACTIVE DESIGN SYSTEM ===`
                    #   `=== ACTIVE TEMPLATE (SKILL.md): web... ===` -> `=== END ACTIVE TEMPLATE ===`
                    #   `=== TEMPLATE EXAMPLE (example.html): ... ===` -> `=== END TEMPLATE EXAMPLE ===`
                    # So strip the `: {id}` suffix AND any `(...)` parenthetical to get
                    # the bare base name.
                    base = block_name.split(":", 1)[0]
                    paren = base.find("(")
                    if paren != -1:
                        base = base[:paren]
                    end_name = base.strip()
                    parts.append(f"=== {block_name} ===\n{content}\n=== END {end_name} ===")

        # ── Consumed upstream outputs (agnostic routing contract) ────────────────
        consumed = self._filter_consumed_outputs(spec, ordered_agents, ectx)
        for aid, output in consumed.items():
            prev = next((s for s in ordered_agents if s.id == aid), None)
            label = f"{prev.name} ({prev.role})" if prev else aid
            parts.append(f"\n--- Output from {label} ---\n{output}")

        # ── D1: the artifact UNDER revision — rendered BEFORE the instruction blocks ──
        # SUBJECT FIRST, INSTRUCTIONS SECOND. Both blocks that follow — the REVISE
        # directive and the analysis report — tell the agent to preserve what it was not
        # asked to change, and that is unsatisfiable unless the document is in the prompt.
        # This block is the agent's ONLY channel to its own prior output: it declares
        # ``consumes: []`` + ``tools: []``, self-consumption is structurally impossible
        # (_filter_consumed_outputs breaks on upstream.id == spec.id), and the re-run
        # threads a FRESH checkpoint id so nothing is replayed.
        #
        # ORDERING IS LOAD-BEARING, not cosmetic (ISS-086): the REVISE block used to be
        # appended ABOVE this one, so reusing the field for a redo without moving it would
        # have read "instructions first, subject second" — the inverse of the rule FIX-217
        # learned. The move is INV-3-safe: on the revision path ``redo_directive`` is empty,
        # so the REVISE block renders nothing and PRIOR → REPORT keeps its relative order.
        #
        # Two publishers (FIX-217's revision pass, ISS-086's redo loop), one field, one
        # block (INV-12). Keyed on the generic scratch field — no workflow/agent literal
        # (SC-001) — and dormant on every non-revision, non-redo dispatch ⇒ the goldens
        # stay byte-identical (INV-3). Costs one extra copy of the artifact per pass.
        prior_artifact = getattr(ectx, "spec_revision_prior_artifact", "") or ""
        if prior_artifact:
            parts.append(
                "\n=== PRIOR ARTIFACT UNDER REVISION ===\n"
                "This is YOUR OWN previous output for this run. Revise THIS document in "
                "place: reproduce verbatim every section you were not asked to change, and "
                "change only what the instructions below identify. Do NOT regenerate from "
                "scratch and do NOT drop sections you were not asked to change.\n\n"
                f"{prior_artifact}\n"
                "=== END PRIOR ARTIFACT UNDER REVISION ==="
            )

        # ── REDO-GATE B6: the optional "redo with additional instructions" block ──
        # Appended IFF ectx.redo_directive is set for THIS re-run (set adjacently in
        # _run_agent's redo loop, cleared unconditionally right after — consume-once,
        # F3). Generic (keyed on the scratch field, no workflow/agent literal —
        # SC-001). Dormant on every non-redo run (redo_directive == "" → no block) ⇒
        # byte-identical (INV-3). Signature UNCHANGED (rides the additive ectx field).
        redo_note = getattr(ectx, "redo_directive", "") or ""
        if redo_note:
            parts.append(
                "\n=== ADDITIONAL INSTRUCTIONS (REVISE) ===\n"
                f"{redo_note}\n"
                "=== END ADDITIONAL INSTRUCTIONS ==="
            )

        # ── KAN-101: Spec revision context — injected during a revision sub-pipeline ──
        # Appended IFF ectx.spec_revision_context is set (set by
        # _run_spec_revision_sub_pipeline before calling _run_agent for the revision
        # cycle, cleared unconditionally on exit — consume-once, F3 pattern).
        # Generic (keyed on the scratch field, no workflow/agent literal — SC-001).
        # Dormant on every normal run (spec_revision_context == "" → no block) ⇒
        # byte-identical for the 5 characterization goldens (INV-3).
        revision_context = getattr(ectx, "spec_revision_context", "") or ""
        if revision_context:
            parts.append(
                "\n=== SPEC KIT ANALYSIS REPORT (REVISION CONTEXT) ===\n"
                "You are running in REVISION MODE. The previous spec and task list "
                "were analyzed and issues were identified. The analysis report is "
                "provided below. Focus your output on fixing the identified issues "
                "rather than regenerating from scratch. Preserve unchanged sections.\n\n"
                f"{revision_context}\n"
                "=== END SPEC KIT ANALYSIS REPORT ==="
            )

        # ── D-06 / CHAT-03 / ND-11: the mid-run steering block (=== USER GUIDANCE ===) ─
        # Generalized Redo (the THIRD consume-once seam beside redo_directive +
        # KAN-101's spec_revision_context — COEXIST, per ND-11-SEAM-DECISION.md).
        # Pending steering notes on ectx.steering_notes render here as a single
        # === USER GUIDANCE === block at the NEXT agent dispatch (mid-generation
        # injection is impossible — an agent invocation runs to completion; D-03),
        # joining the injected-context marker family the chat launch surface strips
        # (POR §6). READ+CLEAR is consume-once DURING composition (the key-link
        # contract — the router enqueues externally/async to any single dispatch, so
        # the clear lives here, not in the _run_agent caller like redo_directive):
        # one-shot directives (sticky False) are dropped after this render; STICKY
        # (uploaded-context) notes (sticky True) persist and re-render next dispatch
        # (D-06). Keyed on the generic queue only — no workflow/agent literal
        # (SC-001/INV-1). Dormant on every golden run (steering_notes empty → no
        # block emitted AND no mutation) ⇒ INV-3 byte/event-parity holds.
        steering_notes = getattr(ectx, "steering_notes", None) or []
        if steering_notes:
            guidance = "\n\n".join(
                n["text"]
                for n in steering_notes
                if isinstance(n, dict) and n.get("text")
            )
            if guidance:
                parts.append(
                    "\n=== USER GUIDANCE ===\n"
                    f"{guidance}\n"
                    "=== END USER GUIDANCE ==="
                )
            # consume-once: drop the one-shot notes, KEEP the sticky ones so
            # uploaded context persists across every subsequent dispatch (D-06).
            ectx.steering_notes = [
                n for n in steering_notes if isinstance(n, dict) and n.get("sticky")
            ]

        # ── Position 5 — Revision Analysis (additive seam, INV-1 / SC-001 compliant) ──
        # Appended IFF ectx.analyzer_solution is non-empty. Generic truthiness check on
        # a dataclass field — no pipeline_type branch, no agent_id literal (SC-001).
        # Default "" → DORMANT on every non-analyzer run → INV-3 byte-parity holds.
        _analyzer_solution = getattr(ectx, "analyzer_solution", "") or ""
        if _analyzer_solution:
            parts.append(
                f"\n=== REVISION ANALYSIS ===\n{_analyzer_solution}\n"
                "=== END REVISION ANALYSIS ==="
            )

        # ── Position 6 — Prototype HTML injection for no-tools first agents ─────
        # On the Concierge revision path the previous_run provider slims the
        # user_message to a file pointer ("Call read_file to read it before editing")
        # because file-capable agents use their tools. A no-tools agent (tools=[])
        # cannot call read_file, so it never sees the HTML content.
        # This seam injects the seeded prototype directly when ALL three conditions hold:
        #   a) ectx.revision_original_html is non-empty (previous_run seeded it)
        #   b) spec.tools is empty (the agent has no file-reading tools)
        #   c) ectx.analyzer_solution is empty (this IS the analyzer step — not a
        #      downstream agent that should use the analysis instead)
        # Declaration-driven (INV-1/SC-001): keyed on generic ectx fields and
        # spec.tools, never on agent id or pipeline name. Default "" → DORMANT on
        # every tool-using agent and every non-revision run → INV-3 byte-parity holds.
        _revision_html = getattr(ectx, "revision_original_html", "") or ""
        _spec_tools = list(getattr(spec, "tools", []) or [])
        _revision_instruction = getattr(ectx, "revision_instruction", None) or ""
        if _revision_html and not _spec_tools and not _analyzer_solution:
            parts.append(
                f"\n=== CURRENT PROTOTYPE HTML ===\n{_revision_html}\n"
                "=== END CURRENT PROTOTYPE HTML ==="
            )
            if _revision_instruction:
                parts.append(
                    f"\n=== REVISION INSTRUCTION ===\n{_revision_instruction}\n"
                    "=== END REVISION INSTRUCTION ==="
                )

        # ── Build agent: the CURRENT TASK block + current HTML (agnostic scratch) ─
        if ectx.build_task_number:
            task_num_str = ectx.build_task_number
            total_str = ectx.build_task_total
            task_block = ectx.current_task_block or ""
            body = task_block.strip() if task_block.strip() else (
                "Execute ONLY this task from the task list above."
            )
            # The CURRENT TASK block carries the task text. The task_loop strategy
            # threads the compacted prototype skeleton onto ectx.current_prototype_skeleton
            # (NOT nested inside current_task_block — WR-01 restored the legacy STANDALONE
            # skeleton block in its legacy position, below the CURRENT TASK block).
            parts.append(
                f"\n=== CURRENT TASK ===\n"
                f"Task {task_num_str} of {total_str}\n"
                f"{body}\n"
                f"=== END CURRENT TASK ==="
            )

            # WR-01 (07-09): the STANDALONE build-skeleton block, restored byte-exact to
            # its legacy text/position/instruction. Emitted AFTER the CURRENT TASK block
            # (the legacy position), gated on the build signal (build_task_number set +
            # the builder tool set) — NOT a workflow name (INV-1). The skeleton is sourced
            # by the task_loop strategy from the typed graph (with the `[Error:`
            # suppression) and threaded onto ectx.current_prototype_skeleton; task 1 has
            # no prior HTML → no skeleton block.
            spec_tools = set(getattr(spec, "tools", []) or [])
            is_builder = bool(spec_tools & {"prototype_emit_only", "prototype"})
            skeleton = getattr(ectx, "current_prototype_skeleton", "") or ""
            if is_builder and skeleton and not skeleton.startswith("[Error:"):
                parts.append(
                    f"\n=== CURRENT PROTOTYPE (skeleton — call read_file('prototype.html') "
                    f"for full content before editing) ===\n"
                    f"{skeleton}\n"
                    f"=== END CURRENT PROTOTYPE ==="
                )

            # CR-01 (07-09): the UNCONDITIONAL TEMPLATE COMPLIANCE block, re-emitted on
            # EVERY build task in its legacy position (last block of the build region),
            # gated on the build signal (build_task_number set + builder tool set) — NOT a
            # workflow name (INV-1). template_id / ds_id read from od_context.
            if is_builder:
                od = ectx.od_context or {}
                ds_id_val = od.get("ds_id", "") or ""
                template_id_val = od.get("template_id", "") or ""
                parts.append(
                    f"\n=== TEMPLATE COMPLIANCE ===\n"
                    f"Template: {template_id_val} — use ONLY its CSS classes from the TEMPLATE SEED\n"
                    f"Design System: {ds_id_val} — use ONLY :root variables, never raw hex colors\n"
                    f"=== END TEMPLATE COMPLIANCE ==="
                )

        return "\n".join(parts)

    async def _compose_input_blocks(self, spec, ectx) -> list:
        """Compose the per-agent multimodal input content-blocks (image-input Wave 1).

        CORRECTNESS-CRITICAL — the gate is derived LOCALLY per-agent from
        ``set(spec.injects) ∪ set(ectx.current_step.injects)`` (the SAME union the
        AgentContext factory seam uses at the step_injects wiring). It NEVER reads
        the stale ``ectx.current_spec_injects`` (set once in _compose_context_message
        inside ``if injects:`` and never reset — reading it would leak ``{images}`` to
        a later NON-opted agent that ran after an opted-in one, the F1 leak vector).

        When ``"images"`` is not in the local gate, returns ``[]`` immediately. Otherwise
        resolves each declared ``input_provider`` capability (off the per-run
        ``ectx.compiled_input_providers`` thread) and extends a blocks list with each
        provider's ``load(ectx)`` output. Mirrors the context_provider provider loop:
        an unresolvable capability is skipped; a ``load`` failure logs-and-skips but a
        ``PermissionError`` propagates. DORMANT by default — no manifest declares an
        ``input_provider`` and no AGENT.md declares ``injects:[images]`` this wave, so
        ``compiled_input_providers`` is ``[]`` and this returns ``[]`` (INV-3).
        """
        agent_injects = set(getattr(spec, "injects", []) or []) | set(
            getattr(getattr(ectx, "current_step", None), "injects", None) or []
        )
        if "images" not in agent_injects:
            return []
        blocks: list = []
        for name in list(getattr(ectx, "compiled_input_providers", []) or []):
            try:
                provider = _CAPABILITY_REGISTRY.resolve("input_provider", name)
            except (KeyError, RuntimeError):
                continue
            try:
                loaded = await provider.load(ectx)
            except PermissionError:
                raise
            except Exception as exc:  # noqa: BLE001 — a provider read must not abort the agent
                logger.warning("input provider %s.load failed (%s) — skipping", name, exc)
                continue
            blocks.extend(loaded or [])
        # Consume-once per-turn images (30-03, HI-01): the images drained onto the
        # ONE-SHOT ``turn_images_once`` carrier render into exactly THIS dispatch's
        # blocks, then clear — so a per-turn image reaches ONE dispatch and never
        # re-delivers on a later one (DISTINCT from the sticky run-entry ``run_images``
        # the provider loop above re-renders every dispatch). Read+clear are co-located
        # HERE (the ``steering_notes`` read-then-clear idiom) so the clear can never be
        # forgotten. The block shape mirrors ``RunImagesProvider.load`` — duplicated by
        # the capability import boundary (the kernel must not import the pure provider
        # module; cf. review IN-02), kept in lockstep by the 30-03 regression test.
        # DORMANT by default — an empty carrier adds nothing (INV-3 byte-parity).
        turn_once = getattr(ectx, "turn_images_once", None) or []
        if turn_once:
            blocks.extend(
                {
                    "type": "image",
                    "source_type": "base64",
                    "mime_type": img["mime_type"],
                    "data": img["data"],
                }
                for img in turn_once
            )
            ectx.turn_images_once = []
        return blocks

    # DELETED (07-05, L12): the legacy per-pipeline context-message builder with its
    # od/template/example injection branches. The routed path composes the per-agent
    # context via the GENERIC _compose_context_message injector (above), which sources
    # OD/template blocks from the declared ``context_provider`` capabilities (resolve(
    # "context_provider", name).load(ctx)) in declared order — NO workflow-name/agent-id
    # branch (INV-1). The build-task CURRENT-TASK marker + compaction now ride the
    # task_loop strategy's ectx scratch, read by _compose_context_message.

    # DELETED (07-10, CR-06): the kernel-resident revision HTML-extraction +
    # message-slimming helpers (``_extract_existing_prototype_html`` /
    # ``_slim_revision_message``). The single home for the existing-artifact
    # extraction + slimming is now the ``previous_run`` context provider
    # (agents/capabilities/context_providers/previous_run.py), which owns the
    # in-place-revision seed (parameterized by deliverable.name). No dual
    # implementation — the kernel no longer extracts/slims a revision request.

    def _load_template_example(self, template_id: str) -> str | None:
        """Load the example.html for a template, or None if not available."""
        if not template_id:
            return None
        try:
            from agents.execution_engine.od_context import get_example_html
            return get_example_html(template_id)
        except Exception as exc:
            logger.debug("Could not load template example for %s: %s", template_id, exc)
        return None

    # DELETED (07-05, L13): the legacy HTML-skeleton extraction helper. The
    # build-task-2+ HTML skeleton
    # compaction is now the ``html_skeleton`` compaction capability (resolve(
    # "compaction","html_skeleton").compact()), owned + injected by the task_loop
    # strategy into ectx.current_task_block — NOT composed by the engine. The 0C
    # >=50% reduction gate is re-pointed at the capability (PARITY-04 preserved).


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
