"""agents/capabilities/hooks/audit_logger.py — default audit-logging hook (KAN-73).

A non-blocking ``HookHandler`` that fires on every agent lifecycle event
(``before_step`` / ``after_step``) and writes a structured ``hook_runs`` row per
firing. This is the default hook enabled on every step in every user-launchable
workflow manifest so every agent execution produces an auditable record.

Audit record structure (``detail`` JSON):
  {
    "agent_id":   str,   # the executing agent's id
    "agent_name": str,   # human-readable agent name
    "event":      str,   # "before_step" | "after_step"
    "step_index": int,   # 0-based position in the pipeline
    "timestamp":  str,   # ISO-8601 UTC
    "outcome":    str,   # always "continue" — audit hook never blocks
    "summary":    str,   # one-line narrative for the Audit tab UI
    "severity":   str,   # "info"
    "hook_type":  str,   # "logging"
  }

The hook ALSO yields a ``hook_run`` WS event (via ``ctx.runner.emit_hook_event``)
so the frontend Audit tab updates in real-time as agents execute — matching the
UX contract in KAN-73.

Registered ``user_allowed=True`` — it is safe to expose on the user palette and
enabled by default for every workflow step.

Import purity (import-linter): imports ONLY the registry decorator + the
hook outcome/write helpers + stdlib. No kernel/app import.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from agents.capabilities.hooks.base import HOOK_CONTINUE, HookOutcome
from agents.capabilities.hooks.write import write_hook_run
from agents.capabilities.registry import register


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _agent_info(event: Any) -> tuple[str, str, int]:
    """Extract (agent_id, agent_name, step_index) from the firing event."""
    if isinstance(event, dict):
        return (
            str(event.get("step") or event.get("agent_id") or "unknown"),
            str(event.get("agent_name") or event.get("step") or "Unknown Agent"),
            int(event.get("step_index", 0)),
        )
    return (
        str(getattr(event, "step", None) or getattr(event, "agent_id", "unknown")),
        str(getattr(event, "agent_name", None) or getattr(event, "step", "Unknown Agent")),
        int(getattr(event, "step_index", 0)),
    )


@register(
    "hook",
    "audit_logger",
    user_allowed=True,
    description="Default audit-logging hook: records per-agent lifecycle events for the Audit tab.",
)
class AuditLoggerHook:
    """Non-blocking audit hook that fires on every agent lifecycle event (KAN-73).

    Writes a ``hook_runs`` row AND emits a ``hook_run`` WS event so both persisted
    history and live-run Audit tab entries are populated.
    """

    name = "audit_logger"
    events = ["before_step", "after_step"]
    required_permission = None  # always bound — no privilege required

    async def handle(self, event: Any, ctx: Any) -> HookOutcome:
        event_name = _event_name(event)
        agent_id, agent_name, step_index = _agent_info(event)

        if event_name == "before_step":
            summary = f"{agent_name} started"
        elif event_name == "after_step":
            summary = f"{agent_name} completed"
        else:
            summary = f"{agent_name}: {event_name}"

        detail: dict = {
            "agent_id": agent_id,
            "agent_name": agent_name,
            "event": event_name,
            "step_index": step_index,
            "timestamp": _now_iso(),
            "outcome": HOOK_CONTINUE,
            "summary": summary,
            "severity": "info",
            "hook_type": "logging",
        }

        # Persist to hook_runs table (best-effort via write_hook_run)
        await write_hook_run(ctx, self.name, event_name, HOOK_CONTINUE, detail)

        # Emit real-time WS event so the frontend Audit tab updates live
        _emit_ws(ctx, detail)

        return HookOutcome(outcome=HOOK_CONTINUE, detail=detail)


def _event_name(event: Any) -> str:
    if isinstance(event, dict):
        return str(event.get("event") or event.get("name") or "before_step")
    return str(getattr(event, "event", None) or getattr(event, "name", "before_step"))


def _emit_ws(ctx: Any, detail: dict) -> None:
    """Emit a hook_run WS event via ctx.runner.emit_hook_event (best-effort)."""
    runner = getattr(ctx, "runner", None)
    if runner is None:
        return
    emit = getattr(runner, "emit_hook_event", None)
    if callable(emit):
        try:
            emit(detail)
        except Exception:
            pass
