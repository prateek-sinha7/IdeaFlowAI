"""agents/capabilities/hooks/otel_tracing.py — the ``otel_tracing`` observability hook (08-07 / OBS-02 / §23).

The §23 observability capability: a NON-blocking ``HookHandler`` bound to the ``*``
wildcard event, so it fires at EVERY lifecycle/tool-call firing point. Each firing
opens a real OpenTelemetry span (one span per fired event) AND writes one
owner/workspace-scoped ``hook_runs`` row (HOOK-04). It NEVER blocks (outcome is
always ``continue``) and emits NO existing WS event, so the characterization
multiset is unchanged (RESEARCH Pitfall 6) — a clean characterization run carries
the same events whether or not otel_tracing is bound.

Real OpenTelemetry (human-verified at the 08-07 package-legitimacy checkpoint —
``opentelemetry-api`` + ``opentelemetry-sdk`` 1.42.1, CNCF OpenTelemetry):

  * A MODULE-LEVEL ``TracerProvider`` is configured ONCE, lazily, on the first
    firing (``_get_tracer``) so importing this module is side-effect-light and a
    test/CI process that never fires a hook pays nothing.
  * Exporter policy (orchestrator-confirmed): a ``ConsoleSpanExporter`` (wrapped
    in a ``SimpleSpanProcessor``) BY DEFAULT; if ``OTEL_EXPORTER_OTLP_ENDPOINT`` is
    set, the OTLP span exporter is imported LAZILY and used instead. The OTLP
    exporter package (``opentelemetry-exporter-otlp``) is an OPTIONAL dependency —
    a missing package degrades GRACEFULLY back to the console exporter rather than
    aborting (least-privilege / supply-chain: only api+sdk are hard deps).

Permissioned as pure observability (HOOK-02): ``required_permission=None`` — the
hook needs no privilege (it reads nothing off disk, runs no command, touches no
git), so it is always bound. Registered ``user_allowed=True`` (D-02): an
observability span emitter grants no privilege and is safe on the user palette.

Import purity (import-linter): imports ONLY the registry decorator + the hook
outcome/write helpers + ``opentelemetry`` + stdlib ``os``/``threading`` — NO
kernel/app import. It reaches the ``hook_runs`` writer through ``ctx.runner`` (the
KernelServices handle), the same idiom secret_scan uses.
"""

from __future__ import annotations

import os
import threading
from typing import Any

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor

from agents.capabilities.hooks.base import HOOK_CONTINUE, HookOutcome
from agents.capabilities.hooks.write import write_hook_run
from agents.capabilities.registry import register

# The instrumentation scope name for every span this hook opens (the OTel
# "tracer" identity — one tracer, one provider, shared process-wide).
_TRACER_NAME = "flowin.agents.hooks.otel_tracing"

# Module-level provider + tracer, configured ONCE on the first firing under a lock
# so concurrent first-firings do not double-configure. Kept module-global (not
# per-instance) because a process must own a SINGLE TracerProvider — the hook impl
# is registered once and reused, so this is the natural home.
_PROVIDER_LOCK = threading.Lock()
_TRACER: trace.Tracer | None = None


def _build_span_processor() -> Any:
    """Return the SpanProcessor for the configured exporter (console default / OTLP via env).

    Console by default (a ``SimpleSpanProcessor`` over a ``ConsoleSpanExporter``).
    If ``OTEL_EXPORTER_OTLP_ENDPOINT`` is set, the OTLP span exporter is imported
    LAZILY and used (wrapped in a ``BatchSpanProcessor`` — the OTLP-recommended
    batching). A missing ``opentelemetry-exporter-otlp`` package degrades GRACEFULLY
    to the console exporter (the OTLP exporter is an OPTIONAL dependency).
    """
    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    if endpoint:
        try:
            # Lazy, guarded import — the OTLP exporter is NOT a hard dependency.
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                OTLPSpanExporter,
            )
            from opentelemetry.sdk.trace.export import BatchSpanProcessor

            return BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint))
        except Exception:
            # Missing/incompatible OTLP exporter package → degrade to console
            # rather than abort (a non-blocking observability hook must never
            # break the run because an optional exporter is absent).
            pass
    return SimpleSpanProcessor(ConsoleSpanExporter())


def _get_tracer() -> trace.Tracer:
    """Return the process-wide tracer, configuring the provider once (lazily, thread-safe)."""
    global _TRACER
    if _TRACER is not None:
        return _TRACER
    with _PROVIDER_LOCK:
        if _TRACER is None:
            provider = TracerProvider()
            provider.add_span_processor(_build_span_processor())
            _TRACER = provider.get_tracer(_TRACER_NAME)
    return _TRACER


@register("hook", "otel_tracing", user_allowed=True)
class OtelTracingHook:
    """The ``otel_tracing`` non-blocking observability hook (``name='otel_tracing'``).

    Satisfies the ``HookHandler`` port structurally (``name`` + ``events`` +
    ``required_permission`` + ``async handle``). Bound to ``*`` (every firing
    point); ``required_permission=None`` (pure observability, always bound). Opens a
    real OpenTelemetry span per fired event and writes a ``hook_runs`` row (HOOK-04);
    ALWAYS returns ``continue`` and emits NO engine WS event (Pitfall 6).
    """

    name = "otel_tracing"
    events = ["*"]
    required_permission = None

    async def handle(self, event: Any, ctx: Any) -> HookOutcome:
        """Open a span for the fired event + write a hook_runs row; always continue (OBS-02)."""
        event_name = _event_name(event)

        # One span per fired lifecycle/tool-call event. The span is opened + closed
        # synchronously around the audit write — it carries the event name + the
        # firing agent/step id (best-effort) as attributes. Span export is the
        # configured exporter's job (console by default); this emits NO WS event.
        tracer = _get_tracer()
        with tracer.start_as_current_span(f"hook.{event_name}") as span:
            span.set_attribute("flowin.hook", self.name)
            span.set_attribute("flowin.event", event_name)
            agent_id = _event_agent_id(event)
            if agent_id:
                span.set_attribute("flowin.agent_id", agent_id)

            detail = {"event": event_name, "span": True}
            if agent_id:
                detail["agent_id"] = agent_id
            await write_hook_run(ctx, self.name, event_name, HOOK_CONTINUE, detail)

        # NON-blocking: every firing is a clean continue (OBS-02 — observability,
        # never a halt).
        return HookOutcome(outcome=HOOK_CONTINUE)


def _event_name(event: Any) -> str:
    """Best-effort lifecycle-event name off the fired event (dict or attr or str)."""
    if isinstance(event, str):
        return event
    if isinstance(event, dict):
        return str(event.get("event") or event.get("name") or "event")
    return str(getattr(event, "event", None) or getattr(event, "name", "event"))


def _event_agent_id(event: Any) -> str | None:
    """Best-effort firing agent/step id off the fired event (span attribute provenance)."""
    if isinstance(event, dict):
        value = event.get("agent_id") or event.get("step")
    else:
        value = getattr(event, "agent_id", None) or getattr(event, "step", None)
    return str(value) if value else None
