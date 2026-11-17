"""Turn_Context: the facts the builder agent gets at the start of each turn.

:func:`render` returns the text of the final human message of a turn: a
``<turn_context>`` block of product facts, then the user's text inside a
``<user_message>`` block (design section 3.6.2, Req 37.2 to 37.10, 45.2).

The module is pure. It reads no database, clock or file, and it imports nothing
from ``app.api``. The caller passes everything that varies per turn in
:class:`TurnContextInputs`. The limits and the clarify threshold come from
``app.core.config.settings``, or from the settings object passed to
:func:`render`.

Two key names are named by the system prompt (``prompts/system_prompt.v2.md``,
part 6) and must not change without a new prompt version:
``step_models`` and ``forbidden_features``.

User text appears only inside ``<user_message>``. Every other value is built by
the server from identifiers and settings. The one value that originates from
the agent (the unfinished file path) is collapsed to a single line. The one
exception is the optional ``<intake_brief>`` block (intake flag on only): slot
values the intake took from the user's request and answers, between the
context and the message, marked as data, with closing tags neutralised.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final, Literal

from agents.capabilities.model_catalog import ModelEntry
from app.agents.workflow_builder.builder_rules import (
    FORBIDDEN_FEATURES,
    ForbiddenFeature,
)
from app.agents.workflow_builder.sandbox import CANVAS_FILE
from app.core.config import Settings, settings

__all__ = [
    "CANVAS_FILE_PATH",
    "NO_DRAFT_YET",
    "SKILL_PATH",
    "TurnContextInputs",
    "UnfinishedWork",
    "render",
]

CANVAS_FILE_PATH: Final = f"/{CANVAS_FILE}"
"""Virtual path of the Canvas_File the agent reads."""

SKILL_PATH: Final = "/skills/velocity-workflow-creator"
"""Virtual path of the builder skill (Req 37.10)."""

NO_DRAFT_YET: Final = "no draft yet"

_STOP_PHRASES: Final[dict[str, str]] = {
    "timed_out": "timed out",
    "interrupted": "was interrupted",
    "cancelled": "was cancelled",
    "failed": "failed",
}
_DEFAULT_STOP_PHRASE: Final = "ended early"

_LABEL_OPEN: Final = "<turn_context>"
_LABEL_CLOSE: Final = "</turn_context>"
_MESSAGE_OPEN: Final = "<user_message>"
_MESSAGE_CLOSE: Final = "</user_message>"
_MESSAGE_CLOSE_PREFIX: Final = re.compile(r"</(?=user_message)", re.IGNORECASE)
_INTAKE_OPEN: Final = "<intake_brief>"
_INTAKE_CLOSE: Final = "</intake_brief>"
_INTAKE_CLOSE_PREFIX: Final = re.compile(
    r"</(?=(?:intake_brief|user_message|turn_context)\b)", re.IGNORECASE
)


@dataclass(frozen=True, slots=True)
class UnfinishedWork:
    """The latest unproposed revision, newer than the last applied draft.

    Attributes:
        source_file: Sandbox path of the revision, for example
            ``/workflows/contract-review.workflow.json``.
        revision: The revision number.
        stop_reason: Status of the turn that left it: ``timed_out``,
            ``interrupted``, ``cancelled`` or ``failed``.
    """

    source_file: str
    revision: int
    stop_reason: str


@dataclass(frozen=True, slots=True)
class TurnContextInputs:
    """Everything :func:`render` needs that varies per turn.

    Attributes:
        user_message: The user's text, placed in ``<user_message>`` as written,
            except that a closing ``</user_message`` tag gets a backslash
            after the ``<`` so the text cannot end its own block.
        mode: ``create`` for a session with no canvas to edit, else ``edit``.
        step_count: Number of top-level steps in the Canvas_File.
        canvas_hash: Canonical hash of this message's ``canvas_state``.
        latest_draft_hash: Canonical hash of the latest seed, accepted or undo
            revision, or ``None`` when the session has none.
        unfinished_work: The unproposed revision to continue from, or ``None``
            when the latest revision is a draft (Req 37.3).
        may_use_db: Whether the user's tier may use ``db`` trust.
        premium_allowed: Whether the user's tier may use the ``premium`` cost
            class.
        step_models: The Step_List after entitlement filtering, in order.
        has_accepted_draft: Whether the session has an accepted draft. The
            clarify count stops mattering once it has.
        clarify_count: Turns that ended ``completed`` with a reply before the
            session's first accepted draft (Req 16.3).
        forbidden_features: The list shown to the agent. Defaults to the one
            the Server_Gate uses (Req 37.7).
        intake_brief: The settled intake slots (``intake.render_overlay``), shown
            in an ``<intake_brief>`` block before the user's message. ``None``
            (the default, and always when the intake flag is off) renders nothing.
    """

    user_message: str
    mode: Literal["create", "edit"]
    step_count: int
    canvas_hash: str | None
    latest_draft_hash: str | None
    unfinished_work: UnfinishedWork | None
    may_use_db: bool
    premium_allowed: bool
    step_models: Sequence[ModelEntry]
    has_accepted_draft: bool
    clarify_count: int
    forbidden_features: Sequence[ForbiddenFeature] = FORBIDDEN_FEATURES
    intake_brief: str | None = None


def _neutralise_intake(text: str) -> str:
    """Rewrite closing tags so intake values cannot end their block or open the message."""
    return _INTAKE_CLOSE_PREFIX.sub(r"<\\/", text)


def _neutralise_close_tag(text: str) -> str:
    """Rewrite every ``</user_message`` (any case) so it cannot close the block."""
    return _MESSAGE_CLOSE_PREFIX.sub(r"<\\/", text)


def _one_line(text: str) -> str:
    """Collapse all whitespace so a value cannot add lines to the block."""
    return " ".join(text.split())


def _steps(count: int) -> str:
    return f"{count} step" if count == 1 else f"{count} steps"


def _canvas_changed(inputs: TurnContextInputs) -> str:
    if inputs.latest_draft_hash is None:
        return NO_DRAFT_YET
    changed = inputs.canvas_hash != inputs.latest_draft_hash
    return "yes" if changed else "no"


def _unfinished_line(work: UnfinishedWork) -> str:
    phrase = _STOP_PHRASES.get(work.stop_reason, _DEFAULT_STOP_PHRASE)
    return (
        f"unfinished_work: {_one_line(work.source_file)} (revision {work.revision}, "
        f"from a turn that {phrase}). Continue from it if the user asks to continue."
    )


def _trust_line(*, may_use_db: bool) -> str:
    if may_use_db:
        return (
            "target_trust: user by default. This user may use db. Use db only when "
            "a stated requirement needs a db-only feature: pass "
            'target_trust="db" and the requirement to propose_draft.'
        )
    return (
        "target_trust: user. This user may not use db, so do not request it. "
        "Design without db-only features."
    )


def _product_line(*, premium_allowed: bool) -> str:
    premium = "allowed" if premium_allowed else "not allowed"
    return (
        "product: the workflow is saved from the Composer canvas and run with "
        f"Run once. Premium models: {premium}."
    )


def _step_models_line(models: Sequence[ModelEntry]) -> str:
    listed = ", ".join(f"{m.id} ({m.cost_class})" for m in models) or "none"
    return f"step_models: {listed}"


def _forbidden_lines(features: Sequence[ForbiddenFeature]) -> list[str]:
    lines = ["forbidden_features:"]
    lines.extend(f"- {f.label}: {f.reason}" for f in features)
    return lines


def _clarify_line(inputs: TurnContextInputs, threshold: int) -> str:
    key = "clarifying_turns_without_draft"
    if inputs.has_accepted_draft:
        return f"{key}: not applicable. The session already has an accepted draft."
    count = inputs.clarify_count
    if count >= threshold:
        return (
            f"{key}: {count} of {threshold}. Produce a draft in this turn from the "
            "recommended defaults, ask no further questions, and list each "
            "unanswered question as a risk."
        )
    return (
        f"{key}: {count} of {threshold}. After {threshold}, produce a draft from "
        "the recommended defaults and list the unanswered questions as risks."
    )


def _limits_line(config: Settings) -> str:
    return (
        f"limits: {config.BUILDER_TURN_TIMEOUT_SECONDS} s and "
        f"{config.BUILDER_MAX_TOOL_CALLS_PER_TURN} tool calls for this turn; "
        "propose_draft may be rejected at most "
        f"{config.BUILDER_MAX_GATE_REJECTIONS_PER_TURN} times."
    )


def render(inputs: TurnContextInputs, config: Settings | None = None) -> str:
    """Render the ``<turn_context>`` and ``<user_message>`` blocks.

    Args:
        inputs: The per-turn values.
        config: Settings that supply the limits and the clarify threshold.
            ``None`` reads ``app.core.config.settings``.

    Returns:
        The text of the final human message of the turn. The user's text is
        inside ``<user_message>`` and nowhere else.
    """
    active = config if config is not None else settings
    lines = [
        _LABEL_OPEN,
        f"mode: {inputs.mode}",
        f"canvas_file: {CANVAS_FILE_PATH} ({_steps(inputs.step_count)})",
        f"canvas_changed_since_last_draft: {_canvas_changed(inputs)}",
    ]
    if inputs.unfinished_work is not None:
        lines.append(_unfinished_line(inputs.unfinished_work))
    lines.append(_trust_line(may_use_db=inputs.may_use_db))
    lines.append(_product_line(premium_allowed=inputs.premium_allowed))
    lines.append(_step_models_line(inputs.step_models))
    lines.extend(_forbidden_lines(inputs.forbidden_features))
    lines.append(_clarify_line(inputs, active.BUILDER_CLARIFY_TURNS_BEFORE_DRAFT))
    lines.append(_limits_line(active))
    lines.append(
        f"skill: {SKILL_PATH}. Run its scripts with run_skill_script. Reply in English."
    )
    lines.append(_LABEL_CLOSE)
    if inputs.intake_brief is not None:
        lines.extend(
            [_INTAKE_OPEN, _neutralise_intake(inputs.intake_brief), _INTAKE_CLOSE]
        )
    lines.extend(
        [_MESSAGE_OPEN, _neutralise_close_tag(inputs.user_message), _MESSAGE_CLOSE]
    )
    return "\n".join(lines)
