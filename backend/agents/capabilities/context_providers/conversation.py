"""agents/capabilities/context_providers/conversation.py — the ``conversation`` provider (33 / D-08).

Surfaces the run's chat history — the ``chat_message`` / ``chat_reply`` ``run_events``
rows appended by the Phase-29 chat backbone — as STICKY agent/steering context, bounded
by ``compaction:chat_history`` so the composed block stays under budget (SC-2). Present in
every subsequent ``agent_input`` for an agent that declares ``injects:[conversation]``.
Satisfies the ``ContextProvider`` port (``name`` + ``async load(ctx) -> dict[str, str]``),
a near-verbatim clone of ``uploaded_files.py``.

Self-gate (INV-1): the block is surfaced ONLY when ``"conversation"`` is in
``ctx.current_spec_injects`` — the per-agent DECLARED inject token, NEVER a workflow
name / spec.id / pipeline_type. Un-gated → ``{}``, so the provider stays DORMANT on
golden runs (no golden agent declares the inject, INV-3 byte/event parity holds).

Owner-scoped reads (T-33-01-01): chat ``run_events`` are read STRICTLY through the
owner+workspace-scoped read surface reached via the ``ctx`` handle
(``ScopedStore.read_events_of_types`` — a cross-owner run returns nothing → 404). There
is NO raw ORM path here; the highest-risk information-disclosure boundary is closed by
the scoped store's default-deny filter. The read is BOUNDED (ISS-101): the type filter
and the LIMIT are pushed into SQL rather than materialising a whole run's log to slice
it in Python.

Degrade-not-crash (mirrors ``uploaded_files.py``): a missing store/run handle, an empty
transcript, or any read error degrades to ``{}`` — a broken chat log must never break the
agent.

Import purity (import-linter, 4 kept / 0 broken): this module imports ONLY the registry
decorator + stdlib — never the app layer nor the execution kernel. The bounding
transform is resolved through the registry (the legal kernel->capability direction).
"""

from __future__ import annotations

import logging
from typing import Any

from agents.capabilities.registry import register

logger = logging.getLogger(__name__)

# The chat-lane ``run_events`` types the Phase-29 backbone appends: the user turn
# (``chat_message``) + the narrator projection back to the lane (``chat_reply``).
_USER_TYPE = "chat_message"
_REPLY_TYPE = "chat_reply"
_CHAT_TYPES = frozenset({_USER_TYPE, _REPLY_TYPE})

# Defaults for the composed-context budget (chars) + the verbatim-recent window
# (turns). Overridable per-run via ctx attributes so a workflow can tune them without
# an engine edit; the compaction transform asserts the SHAPE, not these numbers.
_DEFAULT_BUDGET = 6000
_DEFAULT_KEEP_RECENT = 6

# ISS-101 — hard cap on the bounded read (rows). Well above anything ``_DEFAULT_BUDGET``
# could keep verbatim (200 turns is already 30 chars/turn at budget), so the cap can never
# truncate a transcript the compaction would have kept, while keeping the read O(cap)
# instead of O(whole run log) — 12,123 rows / ~9.2 MB on the worst run in the corpus.
_MAX_CHAT_ROWS = 200


@register(
    "context_provider",
    "conversation",
    description="Surface the run's compacted chat history as sticky agent/steering context.",
)
class ConversationProvider:
    """Surface the run's bounded chat history to agents (``name='conversation'``).

    Returns a ``dict[str, str]`` with a single ``conversation_context`` block: the
    run's chat turns rendered as a transcript and bounded by ``compaction:chat_history``.
    Returns ``{}`` when un-gated, when there is no chat history, or on any read error.
    """

    name = "conversation"

    async def load(self, ctx: Any) -> dict[str, str]:
        # ── Self-gate (INV-1) — only an agent that DECLARES the inject sees it ─────
        injects = set(getattr(ctx, "current_spec_injects", None) or set())
        if "conversation" not in injects:
            return {}

        # ── Owner-scoped read surface (T-33-01-01) — the ONLY chat-events path ────
        # ctx.scoped_store is THIS owner+workspace's ScopedStore (default-deny scope).
        scoped_store = getattr(ctx, "scoped_store", None)
        run_id = getattr(ctx, "run_id", None)
        if scoped_store is None or not run_id:
            return {}

        rows = await self._read_chat_events(scoped_store, run_id)
        if not rows:
            return {}

        transcript = self._render_transcript(rows)
        if not transcript:
            return {}

        body = self._compact(ctx, transcript)
        if not body:
            return {}

        return {"conversation_context": "## Conversation\n\n" + body}

    # ── owner-scoped read (degrade-not-crash — a broken log never breaks the agent) ──
    @staticmethod
    async def _read_chat_events(scoped_store: Any, run_id: str) -> list:
        """Read this run's own chat ``run_events`` via the scoped store; ``[]`` on any miss.

        Uses the BOUNDED, type-filtered read (ISS-101): ``read_events`` is the unbounded
        replay primitive behind SSE resume and engine resume, and draining it to keep six
        chat turns materialised the whole run's log server-side.
        """
        try:
            rows = await scoped_store.read_events_of_types(
                run_id, _CHAT_TYPES, limit=_MAX_CHAT_ROWS
            )
        except Exception as exc:  # noqa: BLE001 — a read error must not break the agent
            logger.warning(
                "conversation: read_events_of_types failed (%s) — no context", exc
            )
            return []
        return list(rows or [])

    @staticmethod
    def _render_transcript(rows: list) -> list[str]:
        """Render chat ``run_events`` rows into ``role: text`` turn strings (in order)."""
        turns: list[str] = []
        for row in rows:
            etype = getattr(row, "type", None)
            if etype not in _CHAT_TYPES:
                continue
            payload = getattr(row, "payload_json", None)
            if not isinstance(payload, dict):
                continue
            text = payload.get("text")
            if not isinstance(text, str) or not text.strip():
                continue
            role = "user" if etype == _USER_TYPE else "assistant"
            turns.append(f"{role}: {text.strip()}")
        return turns

    @staticmethod
    def _compact(ctx: Any, transcript: list[str]) -> str:
        """Bound the transcript through ``compaction:chat_history`` (kernel->cap, legal)."""
        budget = getattr(ctx, "conversation_budget", None) or _DEFAULT_BUDGET
        keep_recent = getattr(ctx, "conversation_keep_recent", None) or _DEFAULT_KEEP_RECENT
        try:
            from agents.capabilities.registry import CapabilityRegistry, discover

            discover()
            compactor = CapabilityRegistry().resolve("compaction", "chat_history")
            return compactor.compact(transcript, budget=budget, keep_recent=keep_recent)
        except Exception as exc:  # noqa: BLE001 — no bounding transform → no context
            logger.warning("conversation: chat_history compaction failed (%s)", exc)
            return ""
