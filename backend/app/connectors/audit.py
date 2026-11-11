"""Audit sink for connector tool calls and tool binding.

Every tool call and every per-run binding writes one ``connector_audit_log`` row and
one JSON log line. Rows and lines hold the connector, tool name, outcome, error code,
duration and run id: never arguments, results, tokens or provider text.

The insert runs in a worker thread with a 2 s bound. A failed or slow insert logs a
WARNING and returns: auditing must not fail a tool call. Lifecycle events
(``connected``, ``refreshed``, ``disconnected`` and so on) are written by the OAuth
service and the token provider through ``ConnectionStore.record_audit``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import Mapping
from typing import Any

from app.connectors.store import AuditEntry, ConnectionStore
from app.models.connector import AUDIT_TOOL_CALL, AUDIT_TOOLS_BOUND

logger = logging.getLogger("app.connectors.audit")

INSERT_TIMEOUT_SECONDS = 2.0

_AGENT_REF_RE = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")
_MAX_CODE_LENGTH = 64
_MAX_TOOL_LENGTH = 128


def agent_ref_from_config(config: Mapping[str, Any] | None) -> str | None:
    """Return the agent id in ``config["configurable"]["thread_id"]``, or ``None``.

    Thread ids look like ``<run_id>:<agent_id>[:suffix]``; the agent id is the second
    segment. Anything that does not look like an identifier is dropped.
    """
    if not isinstance(config, Mapping):
        return None
    configurable = config.get("configurable")
    if not isinstance(configurable, Mapping):
        return None
    thread_id = configurable.get("thread_id")
    if not isinstance(thread_id, str):
        return None
    parts = thread_id.split(":")
    if len(parts) < 2:
        return None
    return parts[1] if _AGENT_REF_RE.match(parts[1]) else None


class ConnectorAudit:
    """Writes tool-call and binding audit rows. Never raises."""

    def __init__(
        self,
        store: ConnectionStore,
        *,
        insert_timeout_seconds: float = INSERT_TIMEOUT_SECONDS,
    ) -> None:
        self._store = store
        self._timeout = insert_timeout_seconds

    async def record_tool_call(
        self,
        *,
        user_id: str,
        connector_key: str,
        tool_name: str,
        outcome: str,
        error_code: str | None = None,
        duration_ms: int | None = None,
        run_id: str | None = None,
        agent_ref: str | None = None,
    ) -> None:
        """Record one tool call (row plus log line)."""
        entry = AuditEntry(
            user_id=user_id,
            connector_key=connector_key,
            action=AUDIT_TOOL_CALL,
            outcome=outcome,
            error_code=_clip(error_code, _MAX_CODE_LENGTH),
            tool_name=_clip(tool_name, _MAX_TOOL_LENGTH),
            run_id=run_id,
            agent_ref=agent_ref,
            duration_ms=duration_ms,
        )
        self._log("connector.tool_call", entry)
        await self._insert(entry)

    async def record_tools_bound(
        self,
        *,
        user_id: str,
        connector_key: str,
        outcome: str,
        error_code: str | None = None,
        run_id: str | None = None,
    ) -> None:
        """Record that a run's tools for one connector were bound (or bound as stubs)."""
        entry = AuditEntry(
            user_id=user_id,
            connector_key=connector_key,
            action=AUDIT_TOOLS_BOUND,
            outcome=outcome,
            error_code=_clip(error_code, _MAX_CODE_LENGTH),
            run_id=run_id,
        )
        self._log("connector.tools_bound", entry)
        await self._insert(entry)

    async def _insert(self, entry: AuditEntry) -> None:
        try:
            await asyncio.wait_for(
                asyncio.to_thread(self._store.record_audit, entry), self._timeout
            )
        except Exception as exc:  # auditing must never fail the caller
            logger.warning(
                "connector audit insert failed connector=%s action=%s error=%s",
                entry.connector_key,
                entry.action,
                type(exc).__name__,
            )

    @staticmethod
    def _log(event: str, entry: AuditEntry) -> None:
        payload: dict[str, Any] = {
            "event": event,
            "connector": entry.connector_key,
            "outcome": entry.outcome,
        }
        if entry.tool_name:
            payload["tool"] = entry.tool_name
        if entry.error_code:
            payload["error_code"] = entry.error_code
        if entry.duration_ms is not None:
            payload["duration_ms"] = entry.duration_ms
        if entry.run_id:
            payload["run_id"] = entry.run_id
        logger.info(json.dumps(payload, sort_keys=True))


def _clip(value: str | None, limit: int) -> str | None:
    return value[:limit] if value else value
