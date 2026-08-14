"""Golden-neutrality proof for the chat-lane event types (CHAT-06 / POR §7).

Phase 28 [A0] registers three run-chat event types in the documented outbound
vocabulary (``chat_message``, ``chat_reply``, ``stream_attached`` — POR D-01) and
adds their run-specific subkeys to the normalizer's volatile-strip set. Those
additions are only safe if the chat lane NEVER fires on the 5 scripted
characterization pipelines — otherwise the additive vocabulary/normalizer entries
would change a golden's event stream and break INV-3 (5 goldens byte/event-identical).

POR §7 states the landmine plainly: "chat events must never fire on golden paths".
This module is the standing characterization proof of that claim. It reads only the
committed golden event streams (no engine drive, no Bedrock), so it runs in the
offline targeted suite. A passing run against the UNCHANGED ``golden/*`` fixtures IS
the proof — do NOT regenerate any fixture.

Phase 33 extends ``_CHAT_EVENT_TYPES`` with the Concierge's ``concierge_proposal`` —
the SAME neutrality claim must hold (it fires on none of the 5 goldens), which is why
adding it to the documented vocabulary is parity-safe (INV-3).

The two guards are pinned together on purpose:
  * ``test_chat_events_absent_from_golden`` — every chat-lane type appears in NONE of
    the 5 golden event ``type`` sequences (parity neutrality — the reason INV-3 holds).
  * ``test_chat_events_are_documented`` — every chat-lane type IS in the documented
    vocabulary, so a future accidental removal from ``_DOCUMENTED_EVENT_TYPES``
    fails here rather than silently un-registering a legal outbound event.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.agents.test_phase3_cutover_verify import _DOCUMENTED_EVENT_TYPES

# The run-chat lane event types pinned by Phase 28 [A0] (POR D-01), extended in
# Phase 33 with the Concierge's ``concierge_proposal`` (the ONLY new event type 33-03
# introduced — answers reuse ``chat_reply``, and no new ``pipeline_complete`` key was
# added, so ``_VOLATILE_STRIP_KEYS`` needs no addition). Every type here must fire on
# NONE of the 5 golden streams (concierge dormant on golden paths — INV-3).
_CHAT_EVENT_TYPES = frozenset(
    {"chat_message", "chat_reply", "stream_attached", "concierge_proposal"}
)

# The 5 characterization pipelines whose golden event streams must stay chat-free.
_GOLDEN_PIPELINES = (
    "prototype",
    "od_prototype",
    "ppt",
    "prototype_revision",
    "app_builder",
)

_GOLDEN_DIR = Path(__file__).parent / "characterization" / "golden"


def _load_golden_types(pipeline: str) -> list[str]:
    """Return the ordered event-``type`` sequence of a golden event stream."""
    events_path = _GOLDEN_DIR / f"{pipeline}.events.json"
    assert events_path.is_file(), f"missing golden event stream: {events_path}"
    events = json.loads(events_path.read_text(encoding="utf-8"))
    assert isinstance(events, list), (
        f"golden {pipeline}.events.json must be a JSON array of events, "
        f"got {type(events).__name__}"
    )
    return [event.get("type") for event in events]


@pytest.mark.parametrize("pipeline", _GOLDEN_PIPELINES)
def test_chat_events_absent_from_golden(pipeline: str) -> None:
    """No chat-lane event type appears in any golden event stream (POR §7 / INV-3).

    The scripted characterization harness has no interactive chat lane, so a run
    emits none of these types. This is exactly what makes the Phase 28 vocabulary
    and normalizer additions parity-neutral: the 5 goldens stay byte/event-identical.
    """
    golden_types = _load_golden_types(pipeline)
    offenders = _CHAT_EVENT_TYPES.intersection(golden_types)
    assert not offenders, (
        f"chat-lane event(s) {sorted(offenders)} fired on the '{pipeline}' golden "
        f"pipeline — chat events must NEVER fire on golden paths (POR §7). This "
        f"breaks INV-3: the vocabulary/normalizer additions are only parity-neutral "
        f"while no golden emits them."
    )


def test_chat_events_are_documented() -> None:
    """The three chat-lane types are members of the documented outbound vocabulary.

    Pinned alongside the neutrality proof so an accidental removal from
    ``_DOCUMENTED_EVENT_TYPES`` (un-registering a legal event) fails HERE.
    """
    missing = _CHAT_EVENT_TYPES.difference(_DOCUMENTED_EVENT_TYPES)
    assert not missing, (
        f"chat-lane event type(s) {sorted(missing)} are not in "
        f"_DOCUMENTED_EVENT_TYPES — Phase 28 [A0] must register them so the "
        f"forward vocabulary guard (TestNewEngineEventVocabulary) admits them."
    )
