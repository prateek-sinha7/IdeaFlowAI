"""Builder model lists over the shared model catalog (design section 3.9).

The builder keeps no model list of its own. This module filters
:class:`agents.capabilities.model_catalog.ModelCatalog` by the ``builder_*``
flags on each :class:`ModelEntry` and by the cost classes the user's tier may
select (``TIER_MODEL_COST_CLASSES``), so labels, reasoning levels, cost class
and context window always come from the entry (Req 41.6) and the view holds no
effort data (Req 41.10).

Everything here is pure: no I/O, no clock, no shared state. The agent layer
stays free of ``app.api`` imports; the API layer projects entries for the wire.

Public surface:

* :class:`BuilderModelView`, the tier-filtered Chat_List and Step_List.
* :func:`builder_models`, builds the view for a tier.
* :func:`assert_builder_catalog_valid`, the startup check (Req 41.8, 41.9, 45.1).
* :func:`check_chat_choice`, admission checks 9 and 10 of design section 3.1.2.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Final

from agents.capabilities.model_catalog import ModelCatalog, ModelEntry
from app.core.entitlements import TIER_MODEL_COST_CLASSES

__all__ = [
    "EFFORT_NOT_ALLOWED",
    "MODEL_NOT_ALLOWED",
    "MODEL_NOT_ENTITLED",
    "BuilderModelView",
    "ChatChoiceRefusal",
    "assert_builder_catalog_valid",
    "builder_models",
    "check_chat_choice",
]

MODEL_NOT_ALLOWED: Final = "model_not_allowed"
MODEL_NOT_ENTITLED: Final = "model_not_entitled"
EFFORT_NOT_ALLOWED: Final = "effort_not_allowed"

# Provider marker that must never carry a builder flag (Req 45.1).
_OPENAI_MARKER: Final = ".openai."


@dataclass(frozen=True)
class BuilderModelView:
    """The models one tier may use in the builder.

    ``chat`` is the Chat_List and ``step`` the Step_List, both in catalog
    declaration order and both filtered by the tier's cost classes.
    ``default_chat_id`` is empty only when ``chat`` is empty.
    """

    chat: tuple[ModelEntry, ...]
    step: tuple[ModelEntry, ...]
    default_chat_id: str


@dataclass(frozen=True)
class ChatChoiceRefusal:
    """A refused model/effort choice: machine code, HTTP status and a short message."""

    code: str
    status_code: int
    message: str


def _allowed_cost_classes(tier: str) -> set[str]:
    return TIER_MODEL_COST_CLASSES.get(tier, TIER_MODEL_COST_CLASSES["basic"])


def _default_chat_id(
    chat: tuple[ModelEntry, ...], preferred_model_id: str | None
) -> str:
    """Pick the default chat model from the already filtered ``chat`` list.

    Order: the user's Settings preference when offered, else the entry flagged
    ``builder_default_chat`` (Sonnet 5.5) when offered, else the first offered
    entry (Req 6.8). An empty list gives an empty string.
    """
    offered = {entry.id for entry in chat}
    if preferred_model_id is not None and preferred_model_id in offered:
        return preferred_model_id
    for entry in chat:
        if entry.builder_default_chat:
            return entry.id
    return chat[0].id if chat else ""


def builder_models(
    tier: str, preferred_model_id: str | None = None
) -> BuilderModelView:
    """Build the tier-filtered builder model view.

    An unknown ``tier`` is treated as ``basic`` (fail closed), matching
    ``can_use_model``. ``preferred_model_id`` is the user's Settings model
    preference; it becomes the default only when it is on the filtered
    Chat_List.
    """
    allowed = _allowed_cost_classes(tier)
    entries = ModelCatalog().list()
    chat = tuple(e for e in entries if e.builder_chat and e.cost_class in allowed)
    step = tuple(e for e in entries if e.builder_step and e.cost_class in allowed)
    return BuilderModelView(
        chat=chat,
        step=step,
        default_chat_id=_default_chat_id(chat, preferred_model_id),
    )


def assert_builder_catalog_valid(entries: Iterable[ModelEntry]) -> None:
    """Raise ``RuntimeError`` when the builder flags on ``entries`` are inconsistent.

    Fails when there is not exactly one ``builder_default_chat`` entry, when
    that entry lacks ``builder_chat``, or when any id containing ``.openai.``
    carries a builder flag (Req 41.8, 41.9, 45.1).
    """
    items = list(entries)
    defaults = [e for e in items if e.builder_default_chat]
    if len(defaults) != 1:
        raise RuntimeError(
            "builder model catalog needs exactly one builder_default_chat entry, "
            f"found {len(defaults)}"
        )
    if not defaults[0].builder_chat:
        raise RuntimeError(
            f"builder default chat model {defaults[0].id!r} must also set builder_chat"
        )
    flagged_openai = [
        e.id
        for e in items
        if _OPENAI_MARKER in e.id
        and (e.builder_chat or e.builder_step or e.builder_default_chat)
    ]
    if flagged_openai:
        raise RuntimeError(
            f"GPT models must not carry builder flags: {', '.join(flagged_openai)}"
        )


def check_chat_choice(
    entries: Iterable[ModelEntry],
    view: BuilderModelView,
    model_id: str,
    effort: str | None,
) -> ChatChoiceRefusal | None:
    """Admission checks 9 and 10: return the refusal, or ``None`` when allowed.

    ``entries`` is the full catalog, so an unknown model (422) can be told
    apart from a known one the tier may not use (403, pending G-06). ``view``
    is the caller's tier-filtered view.

    * Unknown id, GPT id, or a model not flagged ``builder_chat``:
      ``model_not_allowed`` (422).
    * Flagged model absent from ``view.chat``: ``model_not_entitled`` (403).
    * ``effort`` outside the model's ``reasoning.levels``, ``None`` for a model
      that has levels, or a non-``None`` effort for a model with none:
      ``effort_not_allowed`` (422) (Req 26.3).
    """
    entry = next((e for e in entries if e.id == model_id), None)
    if entry is None or _OPENAI_MARKER in entry.id or not entry.builder_chat:
        return ChatChoiceRefusal(
            MODEL_NOT_ALLOWED, 422, "That model is not available in the builder."
        )
    if all(e.id != model_id for e in view.chat):
        return ChatChoiceRefusal(
            MODEL_NOT_ENTITLED, 403, "That model is not available on your plan."
        )
    levels = entry.reasoning.levels
    if not levels:
        if effort is not None:
            return ChatChoiceRefusal(
                EFFORT_NOT_ALLOWED, 422, "That model does not take an effort level."
            )
    elif effort is None or effort not in levels:
        return ChatChoiceRefusal(
            EFFORT_NOT_ALLOWED,
            422,
            f"Effort must be one of: {', '.join(levels)}.",
        )
    return None
