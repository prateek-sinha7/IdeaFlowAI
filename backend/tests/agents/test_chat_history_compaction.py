"""Phase 33 (D-08 / SC-2) — ``compaction:chat_history`` under-budget + fidelity gate.

The DETERMINISTIC, FULLY-OFFLINE half of the bounded-history deliverable. It proves the
``chat_history`` compaction capability (``ChatHistoryCompaction().compact``) bounds a long
chat transcript under a configured budget while keeping the most-recent turns
BYTE-VERBATIM and replacing the older tail with a summary marker — the analog of
``test_phase3_compaction.py``'s ``html_skeleton`` reduction+fidelity gates.

Gates asserted here (RESEARCH §Compaction-Under-Budget — assert the SHAPE, not a magic
number; ``budget``/``keep_recent`` are parameterized per Open-Q2):
  * Under budget — a long transcript compacts to ``<= budget`` chars (the analog of
    ``assert len(skeleton) <= 0.5 * len(source)``).
  * Recent verbatim + older summarized — a specific RECENT turn's exact text survives
    byte-for-byte, while a specific OLD turn's verbatim body is absent (summarized).
"""

from __future__ import annotations

# Import the scripted-model harness FIRST so its import-time env setup
# (RUNS_ROOT→temp + ENV=development) runs and the test stays fully offline.
from tests.agents import _scripted_model  # noqa: F401  (import for side effects)

from agents.capabilities.compaction.chat_history import ChatHistoryCompaction

# ── A long chat transcript fixture ────────────────────────────────────────────
# Many turns with a generous per-turn body so the full block is a realistic
# input-token proxy that far exceeds the configured budget (mirrors the 60×-repeated
# paragraph the html_skeleton fixture uses). Two unique sentinels pin fidelity: one
# in the OLDEST turn (must be summarized away) and one in the NEWEST turn (must survive
# byte-verbatim).
_OLD_SENTINEL = "OLDEST-TURN-UNIQUE-MARKER-alpha-0xDEAD"
_RECENT_SENTINEL = "NEWEST-TURN-UNIQUE-MARKER-omega-0xBEEF"

_BODY = (
    "Lorem ipsum dolor sit amet, consectetur adipiscing elit. Pellentesque "
    "euismod nisl eget ultricies aliquam, nunc nisl aliquet nunc."
)


def _build_transcript(n: int = 40) -> list[str]:
    turns: list[str] = []
    for i in range(n):
        role = "user" if i % 2 == 0 else "assistant"
        marker = ""
        if i == 0:
            marker = f" {_OLD_SENTINEL}"
        elif i == n - 1:
            marker = f" {_RECENT_SENTINEL}"
        turns.append(f"{role}: Turn {i}.{marker} {_BODY}")
    return turns


_TRANSCRIPT = _build_transcript()
# Budget chosen well below the full transcript but comfortably above the verbatim
# recent window (keep_recent turns + the one-line summary marker).
_BUDGET = 1500
_KEEP_RECENT = 4


def test_chat_history_stays_under_budget() -> None:
    """SC-2 under-budget gate: a long transcript compacts to ``<= budget`` chars."""
    full = "\n".join(_TRANSCRIPT)
    assert len(full) > _BUDGET, "fixture must exceed the budget so compaction is exercised"

    compacted = ChatHistoryCompaction().compact(
        _TRANSCRIPT, budget=_BUDGET, keep_recent=_KEEP_RECENT
    )
    assert len(compacted) <= _BUDGET, (
        f"compacted transcript ({len(compacted)} chars) must be ≤ budget "
        f"({_BUDGET} chars) — SC-2 under-budget gate"
    )


def test_recent_turns_are_verbatim_and_old_turns_are_summarized() -> None:
    """SC-2 fidelity gate: newest turn byte-verbatim, oldest turn summarized away."""
    compacted = ChatHistoryCompaction().compact(
        _TRANSCRIPT, budget=_BUDGET, keep_recent=_KEEP_RECENT
    )

    # (a) The most-recent turn survives BYTE-FOR-BYTE (verbatim recent window).
    assert _RECENT_SENTINEL in compacted, "the newest turn must be kept verbatim"
    assert _TRANSCRIPT[-1] in compacted, "the newest turn's exact text must be present"

    # (b) The oldest turn's verbatim body is ABSENT — replaced by a summary marker.
    assert _OLD_SENTINEL not in compacted, "the oldest turn must be summarized (not verbatim)"
    assert "summarized" in compacted, "the older tail must be replaced by a summary marker"


def test_short_transcript_is_returned_verbatim() -> None:
    """A transcript already under budget is returned unchanged (no needless summary)."""
    short = ["user: hi", "assistant: hello there"]
    out = ChatHistoryCompaction().compact(short, budget=10_000, keep_recent=4)
    assert out == "\n".join(short)
    assert "summarized" not in out


def test_name_attribute_matches_registered_name() -> None:
    assert ChatHistoryCompaction().name == "chat_history"
