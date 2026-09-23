"""agents/capabilities/deliverables/_placeholder.py — placeholder-narration check.

QA-PS-027 / ISS-721: every terminal degrade signal the engine has is
presence/absence — an agent raised, a budget cap fired, a commit was blocked,
a declared file did not materialize. None of them looks at what an agent
actually PRODUCED, so an agent that cleanly streams "I don't have access to a
write_file tool" instead of doing the work is a completion, and its narration
is published as the deliverable under a green "Done" badge.

This module is the one place that answers "is this deliverable the agent
talking about the work instead of the work?". It is deliberately a short,
literal marker list and NOT a general output-quality judgement: the signal
flips a user-visible success badge, so a false positive is worse than a miss.

Both conditions must hold before anything is flagged:

  * the text is SHORT — narration is a paragraph; a real deliverable (an HTML
    page, a deck, a backlog, a serialized code bundle) is orders of magnitude
    larger. The bound is what stops a long document that merely QUOTES one of
    the markers from tripping it.
  * it contains a first-person "I could not do this" phrase observed in a
    reproduced run (BUGS.md#qa-ps-027; ISS-721 cycles A–C) or its immediate
    variant.

Import purity (import-linter): stdlib only — no ``app.*``, no kernel import —
so both the kernel's completion gate and a resolver capability can call it
without crossing a boundary.
"""

from __future__ import annotations

# Phrases observed in reproduced runs (ISS-721 cycles A–C, BUGS.md#qa-ps-027
# examples 1–3) plus their immediate first-person variants. Lowercase; matched
# as substrings against the lowercased deliverable.
_NARRATION_MARKERS: tuple[str, ...] = (
    "i don't have access",
    "i do not have access",
    "i'm unable to",
    "i am unable to",
    "i can't ",
    "i cannot ",
    "i'm ready to help",
    "i am ready to help",
    "unable to complete",
    "cannot complete",
    "the pipeline may have failed",
    "not properly generated",
)

# A narration paragraph is hundreds of characters; the shortest REAL
# deliverable this runtime publishes (a one-line note written to result.md) is
# shorter still, which is exactly why length alone is never the signal — it is
# only the bound that keeps the markers off a genuine document.
_MAX_NARRATION_CHARS = 2000


def placeholder_narration_reason(deliverable: object) -> str | None:
    """Return why ``deliverable`` reads as agent narration, or ``None``.

    ``None`` means "no evidence this is narration" — the default for anything
    non-textual (e.g. ``repo_diff``'s dict payload), empty, or longer than
    ``_MAX_NARRATION_CHARS``.
    """
    if not isinstance(deliverable, str):
        return None
    text = deliverable.strip()
    if not text or len(text) > _MAX_NARRATION_CHARS:
        return None
    lowered = text.lower()
    for marker in _NARRATION_MARKERS:
        if marker in lowered:
            return (
                "deliverable is the agent narrating why it could not do the "
                f"work, not the requested output (matched {marker!r} in "
                f"{len(text)} characters)"
            )
    return None
