"""agents/capabilities/compaction/chat_history.py — the ``chat_history`` compaction (33 / D-08).

Bounds a composed chat transcript so the ``context_provider:conversation`` block
(and, downstream, the Concierge's system-prompt context) stays under a configured
budget: the ``keep_recent`` most-recent turns are kept BYTE-VERBATIM and the older
tail is replaced by a short summary marker (SC-2). It is the offline-provable
"backend-owned transcript compaction" layer of D-08 — the analog of
``compaction:html_skeleton``'s pure ``compact(...)`` transform. (In-graph message
growth is a SEPARATE concern, handled by the deepagents base-stack
``SummarizationMiddleware`` already wired in ``deep_agent_runner.py`` — do NOT
re-add it here.)

The module is PURE: stdlib only — no kernel/engine state, no reach into the app
layer or the execution kernel, no deep-agent library import (Pitfall 4 /
import-linter). It satisfies the ``compaction`` contract STRUCTURALLY — a ``name``
attribute plus ``compact(transcript, *, budget, keep_recent) -> str`` — the same
duck-typed shape ``html_skeleton`` uses; the ``compaction`` kind has NO formal
Protocol port, so there is deliberately no ``base.py`` edit.

Budget is measured in CHARACTERS (``len``) — one measure, asserted against the same
unit by the offline proof (RESEARCH Open-Q2: parameterize ``budget`` / ``keep_recent``
and assert the SHAPE — under budget + recent verbatim — never a magic number).
"""

from __future__ import annotations

from typing import Any, Iterable

from agents.capabilities.registry import register

# A minimal fallback marker used only if the verbatim recent block alone already
# approaches the budget — fidelity of the recent turns always wins over the summary.
_MIN_MARKER = "[… earlier conversation summarized …]"


@register(
    "compaction",
    "chat_history",
    description=(
        "Summarize chat turns beyond budget and keep the most-recent turns "
        "verbatim to bound the composed conversation context."
    ),
)
class ChatHistoryCompaction:
    """Bound a chat transcript under ``budget``, keeping recent turns verbatim.

    Satisfies the compaction contract: a ``name`` attribute plus
    ``compact(self, transcript, *, budget, keep_recent) -> str``. ``transcript`` is
    an iterable of already-rendered turn strings (e.g. ``"user: …"`` /
    ``"assistant: …"``); the return is a single bounded string.
    """

    name = "chat_history"

    def compact(self, transcript: Iterable[Any], *, budget: int, keep_recent: int) -> str:
        """Return the transcript bounded to ``budget`` chars.

        - If the full transcript already fits ``budget``, it is returned verbatim.
        - Otherwise the ``keep_recent`` most-recent turns are kept BYTE-VERBATIM and
          the older tail is replaced by a compact summary marker so the whole block
          fits under ``budget``. Recent-turn fidelity is preserved even under a tight
          budget (the summary shrinks first, never the verbatim tail).
        """
        turns = [str(t) for t in transcript]
        full = "\n".join(turns)
        if len(full) <= budget:
            return full

        keep_recent = max(0, int(keep_recent))
        recent = turns[len(turns) - keep_recent:] if keep_recent else []
        older = turns[: len(turns) - len(recent)]

        recent_block = "\n".join(recent)
        summary = self._summarize_older(older)
        result = f"{summary}\n{recent_block}" if (summary and recent_block) else (summary or recent_block)

        # Safety net: if the verbatim recent block alone still exceeds budget, shrink
        # the summary to the minimal marker (recent turns stay byte-verbatim —
        # fidelity of the most-recent context always wins over the older summary).
        if len(result) > budget and recent_block:
            minimal = f"{_MIN_MARKER}\n{recent_block}"
            result = minimal if len(minimal) < len(result) else recent_block
        return result

    @staticmethod
    def _summarize_older(older: list[str]) -> str:
        """Replace the older turns with ONE short marker line (never their bodies)."""
        if not older:
            return ""
        chars = sum(len(t) for t in older)
        return f"[… {len(older)} earlier turns summarized ({chars} chars) …]"
