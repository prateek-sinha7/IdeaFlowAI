#!/usr/bin/env python3
"""Decide whether the builder's intake has enough facts to design a workflow.

The intake step fills the Workflow Brief as slots (docs/intake-slots.md,
schema/intake-brief.schema.json). This module is the readiness rule, in one place, for
the builder (it imports this file by path) and for people (the command line below).

The rule:
  ready = every blocking slot has source request, user or upload, or not_applicable on
          a slot that allows it, with a reason
       OR the user explicitly accepted the defaults ("defaults", "you decide", ...)
       OR the question rounds reached the maximum (treated exactly like "defaults").

Important slots may be assumed; each one is echoed as
"Assumption: <slot> = <value> - correct me if wrong". Minor matters are not slots.

Also here, so the rule and its inputs live together: reading answer codes such as
"1a 2c 3b", spotting an explicit "defaults" reply, and filling the open slots from the
recommended options.

Usage:
  python intake_readiness.py BRIEF.json [--defaults] [--rounds-asked N] [--max-rounds N] [--json]

BRIEF.json is an intake brief, or an object with a "slots" key. Exit status: 0 ready,
1 not ready, 2 bad input. Standard library only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

__all__ = [
    "ALL_SLOTS",
    "BLOCKING_SLOTS",
    "FALLBACK_LABEL",
    "FILLED_SOURCES",
    "IMPORTANT_SLOTS",
    "NOT_APPLICABLE_ALLOWED",
    "REPLY_FOOTER",
    "PLATFORM_GATE_NOTE",
    "PLATFORM_GATE_VALUE",
    "SOURCES",
    "UNSPECIFIED_VALUE",
    "UNAVAILABLE_WRITE_REASON",
    "apply_answers",
    "drop_unavailable_write",
    "enforce_platform_rules",
    "has_irreversible_action",
    "is_none_value",
    "missing_destination_followups",
    "question_violations",
    "removes_person",
    "write_is_named",
    "apply_defaults",
    "assumption_line",
    "assumption_lines",
    "evaluate",
    "invalid_not_applicable",
    "is_explicit_defaults",
    "is_filled",
    "main",
    "missing_blocking",
    "order_questions",
    "parse_answer_codes",
    "parse_answers",
    "question_plan_problems",
]

BLOCKING_SLOTS: tuple[str, ...] = (
    "goal",
    "deliverable",
    "done_when",
    "input_source",
    "input_variability",
    "output_structure",
    "external_systems",
    "write_destinations",
    "irreversible_actions",
    "human_approval_points",
)
IMPORTANT_SLOTS: tuple[str, ...] = (
    "volume_scale",
    "quality_bar",
    "constraints",
    "trigger",
    "runtime_trust",
    "depth",
)
ALL_SLOTS: tuple[str, ...] = BLOCKING_SLOTS + IMPORTANT_SLOTS
NOT_APPLICABLE_ALLOWED: frozenset[str] = frozenset(
    {
        "human_approval_points",
        "external_systems",
        "write_destinations",
        "irreversible_actions",
        "input_variability",
    }
)
# The value human_approval_points takes when the user asks to skip approval but the
# workflow posts or writes outside the run: the skill does not allow that workflow.
PLATFORM_GATE_VALUE = "gate-before-post (platform requirement)"
PLATFORM_GATE_NOTE = (
    "The approval step before {action} stays: the platform requires a person to "
    "approve every post or write outside the run, so it cannot post automatically."
)
# Defaults for important slots that no question covered (forced ready only).
_IMPORTANT_DEFAULTS = {"depth": "Full (the skill's default depth)"}
SOURCES: tuple[str, ...] = ("request", "user", "upload", "assumed", "not_applicable", "unknown")
FILLED_SOURCES: frozenset[str] = frozenset({"request", "user", "upload"})
FALLBACK_LABEL = "Not sure - use default"
REPLY_FOOTER = 'Reply e.g. "1a 2c 3b", or "defaults" to accept all recommended options.'
UNSPECIFIED_VALUE = "not specified; choose a sensible default during design and record it"

# "1a", "1 a", "1) a", "1: a", "1-a", "1.b" - a question number then an option letter,
# not followed by another letter (so "2 apples" is not an answer).
_ANSWER_CODE_RE = re.compile(r"(?<!\d)([1-9])\s*[).:\-]?\s*([a-e])(?![a-z])", re.IGNORECASE)
# The whole reply, once normalised, must be one of these phrases. A reply that only
# contains the word ("I don't want the defaults, use OCR") is free text for the model.
_DEFAULTS_PHRASE_RE = re.compile(
    r"(?:use )?(?:your |all )?defaults?"
    r"|(?:use |accept |take )?(?:all |your )?recommended(?: options?| answers?| ones?)?"
    r"|as recommended"
    r"|you decide|you choose|your (?:call|choice)|up to you"
    r"|just (?:do it|build it|go)|go ahead|go for it"
    r"|whatever you (?:think|recommend|suggest)"
    r"|no preference|i don'?t mind"
)
# Words that may surround the phrase without making it free text.
_DEFAULTS_FILLER = frozenset(
    {"please", "pls", "ok", "okay", "thanks", "sure", "yes", "fine", "the", "and",
     "for", "rest", "others", "other", "otherwise", "else"}
)
_DEFAULTS_MAX_WORDS = 4
# A value that says "nothing": "none", "no ...", "n/a", "not needed".
_NONE_VALUE_RE = re.compile(r"^\s*(?:none|no\b|n/?a\b|not needed|not required)", re.IGNORECASE)
# An approval answer or option that removes the person: "no ...", "without review",
# or "automatically" with no approve/confirm/gate/review in the same text.
_NO_GATE_RE = re.compile(
    r"^\s*(?:none|no\b|n/?a\b|skip\b)|\bwithout (?:a |any )?(?:review|approval|confirm\w*|gate|check)",
    re.IGNORECASE,
)
_AUTOMATIC_RE = re.compile(r"\bautomatic(?:ally)?\b", re.IGNORECASE)
_KEEPS_PERSON_RE = re.compile(r"approv|confirm|gate|review|check", re.IGNORECASE)


def _slot(slots: dict[str, Any], name: str) -> dict[str, Any]:
    value = slots.get(name)
    return value if isinstance(value, dict) else {}


def _has_reason(slot: dict[str, Any]) -> bool:
    reason = slot.get("reason")
    return isinstance(reason, str) and bool(reason.strip())


def _has_value(slot: dict[str, Any]) -> bool:
    value = slot.get("value")
    return isinstance(value, str) and bool(value.strip())


def is_filled(name: str, slot: dict[str, Any]) -> bool:
    """True when ``slot`` counts as filled for readiness.

    A value from the request, the user or an upload counts. ``not_applicable`` counts
    only on the five slots that allow it and only with a reason.
    """
    source = slot.get("source")
    if source in FILLED_SOURCES:
        return _has_value(slot)
    if source == "not_applicable":
        return name in NOT_APPLICABLE_ALLOWED and _has_reason(slot)
    return False


def is_none_value(slot: dict[str, Any]) -> bool:
    """True when a slot is ``not_applicable`` or its value says "none" / "no ..."."""
    if slot.get("source") == "not_applicable":
        return True
    return _has_value(slot) and bool(_NONE_VALUE_RE.match(str(slot["value"])))


def has_irreversible_action(slots: dict[str, Any]) -> bool:
    """True when the workflow posts, sends or writes outside the run.

    That is an ``irreversible_actions`` value that is not "none", whatever its
    source: an assumed post still needs a gate and a destination.
    """
    slot = _slot(slots, "irreversible_actions")
    return slot.get("source") != "unknown" and _has_value(slot) and not is_none_value(slot)


def removes_person(text: str) -> bool:
    """True when an approval answer or option takes the person out ("no", "post automatically").

    "Approve the draft earlier, post automatically after edits still gated by a
    confirm step" keeps a person, so it is not a removal.
    """
    if _NO_GATE_RE.search(text or ""):
        return True
    return bool(_AUTOMATIC_RE.search(text or "")) and not _KEEPS_PERSON_RE.search(text or "")


def _cross_slot_unfilled(slots: dict[str, Any]) -> list[str]:
    """Slots that look filled but break a rule tied to an irreversible action.

    With a post or write outside the run, ``write_destinations`` (where it posts or
    writes) and ``human_approval_points`` (where a person approves) cannot be
    ``not_applicable``.
    """
    if not has_irreversible_action(slots):
        return []
    return [
        name
        for name in ("write_destinations", "human_approval_points")
        if _slot(slots, name).get("source") == "not_applicable"
    ]


def invalid_not_applicable(slots: dict[str, Any]) -> list[str]:
    """Slots marked ``not_applicable`` where it is not allowed, has no reason, or
    is ruled out by an irreversible action."""
    bad = []
    tied = set(_cross_slot_unfilled(slots))
    for name in ALL_SLOTS:
        slot = _slot(slots, name)
        if slot.get("source") != "not_applicable":
            continue
        if name not in NOT_APPLICABLE_ALLOWED or not _has_reason(slot) or name in tied:
            bad.append(name)
    return bad


def missing_blocking(slots: dict[str, Any]) -> list[str]:
    """Blocking slots that are not filled, in the fixed slot order."""
    tied = set(_cross_slot_unfilled(slots))
    return [
        name
        for name in BLOCKING_SLOTS
        if name in tied or not is_filled(name, _slot(slots, name))
    ]


UNAVAILABLE_WRITE_REASON = (
    "the system it would write to is not on this platform (see the feasibility note)"
)


def drop_unavailable_write(
    slots: dict[str, Any], available_systems: frozenset[str], *, has_feasibility_note: bool
) -> tuple[dict[str, Any], bool]:
    """Clear a write to a system the platform does not provide (a CRM, email sending).

    When the intake flagged a missing system (a feasibility note) and the
    ``irreversible_actions`` value names none of ``available_systems``, the write
    cannot happen, so it is neither "named" nor a gated action: the slot becomes
    ``not_applicable`` with a reason. Returns the slots and whether they changed.
    """
    merged = {name: dict(_slot(slots, name)) for name in ALL_SLOTS}
    slot = merged["irreversible_actions"]
    if not (has_feasibility_note and has_irreversible_action(merged)):
        return merged, False
    value = str(slot.get("value") or "").lower()
    if any(re.search(rf"\b{re.escape(system)}\b", value) for system in available_systems):
        return merged, False
    merged["irreversible_actions"] = {
        "value": None,
        "source": "not_applicable",
        "criticality": slot.get("criticality", "blocking"),
        "reason": UNAVAILABLE_WRITE_REASON,
    }
    return merged, True


def write_is_named(slots: dict[str, Any]) -> bool:
    """True when the request, or the user's answer, names a write outside the run.

    That is an ``irreversible_actions`` value with source ``request`` or ``user``. An
    assumed write, or a destination that is still only an option, does not count.
    """
    slot = _slot(slots, "irreversible_actions")
    return slot.get("source") in ("request", "user") and has_irreversible_action(slots)


def question_violations(slots: dict[str, Any], questions: list[dict[str, Any]]) -> list[str]:
    """Questions whose approval form is wrong. Empty when every question is right.

    The approval question takes the WHERE/WHAT form ("what should a person approve
    before it posts?", no option removes the person) only when a write outside the
    run is named. Otherwise it asks WHETHER a person reviews, with a "no review"
    option; if the user then picks a write option, the gate-before-post platform
    rule applies (:func:`enforce_platform_rules`).
    """
    named = write_is_named(slots)
    problems = []
    for question in questions:
        if question.get("slot") != "human_approval_points":
            continue
        real = [o for o in question.get("options") or [] if isinstance(o, dict) and not o.get("fallback")]
        removing = [str(o.get("label", "")) for o in real if removes_person(str(o.get("label", "")))]
        if named and removing:
            problems.append(
                "human_approval_points: the workflow posts or writes outside the run, "
                f"so a person must approve before it; the option {removing[0]!r} removes "
                "that person. Ask where or what the person approves instead."
            )
        elif not named and not removing:
            problems.append(
                "human_approval_points: the request names no post or write outside the run, "
                "so ask WHETHER a person reviews, with a 'No, finish without a pause' option. "
                "Ask where or what a person approves only when a write is named."
            )
    return problems


# A write destination named in an option, and the follow-up that asks for it.
_DESTINATION_RE = re.compile(r"\b(slack|jira|e-?mail|github|gitlab)\b", re.IGNORECASE)
_DESTINATION_FOLLOWUP = {
    "slack": "name the Slack channel in your reply",
    "jira": "name the Jira project or issue in your reply",
    "email": "name the email recipients in your reply",
    "e-mail": "name the email recipients in your reply",
    "github": "name the GitHub repository in your reply",
    "gitlab": "name the GitLab project in your reply",
}
_DESTINATION_SLOTS = frozenset({"external_systems", "irreversible_actions", "deliverable", "write_destinations"})
_READ_LABEL_RE = re.compile(r"^\s*(?:read|pulled?|fetched?|from|taken)\b", re.IGNORECASE)


def missing_destination_followups(questions: list[dict[str, Any]]) -> list[tuple[int, int, str]]:
    """``(question, option, follow-up text)`` for each write option naming a system without one.

    An option on a destination-type question that names Slack, Jira, email, GitHub or
    GitLab as somewhere the result goes must ask for the exact destination
    (``followup_text`` + ``followup_slot: write_destinations``), so one round settles it.
    Options that only read from a system are left alone.
    """
    found = []
    for q_index, question in enumerate(questions):
        if question.get("slot") not in _DESTINATION_SLOTS:
            continue
        for o_index, option in enumerate(question.get("options") or []):
            if not isinstance(option, dict) or option.get("fallback") or option.get("followup_slot"):
                continue
            label = str(option.get("label", ""))
            match = _DESTINATION_RE.search(label)
            if match and not _READ_LABEL_RE.match(label):
                found.append((q_index, o_index, _DESTINATION_FOLLOWUP[match.group(1).lower()]))
    return found


def enforce_platform_rules(slots: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Apply the gate rule to the slots. Returns the slots and one note per change.

    With an irreversible action, an approval answer that removes the person
    ("post automatically", "no review") becomes ``gate-before-post (platform
    requirement)``, and the note explains in one line why the gate stays.
    """
    merged = {name: dict(_slot(slots, name)) for name in ALL_SLOTS}
    if not has_irreversible_action(merged):
        return merged, []
    approval = merged["human_approval_points"]
    value = str(approval.get("value") or "")
    already = value == PLATFORM_GATE_VALUE  # the model applied the rule itself
    if not (already or (_has_value(approval) and (is_none_value(approval) or removes_person(value)))):
        return merged, []
    approval.update({
        "value": PLATFORM_GATE_VALUE,
        "reason": "a person approves before every post or write outside the run",
    })
    action = " ".join(str(merged["irreversible_actions"]["value"]).split()).rstrip(".")
    return merged, [PLATFORM_GATE_NOTE.format(action=f"the irreversible action ({action})")]


def assumption_line(name: str, value: str) -> str:
    """The line that shows one assumption to the user."""
    return f"Assumption: {name} = {' '.join(value.split())} - correct me if wrong"


def assumption_lines(slots: dict[str, Any], *, include_blocking: bool = False) -> list[str]:
    """One line per assumed slot with a value: important slots, plus blocking ones if asked."""
    names = (BLOCKING_SLOTS if include_blocking else ()) + IMPORTANT_SLOTS
    lines = []
    for name in names:
        slot = _slot(slots, name)
        if slot.get("source") == "assumed" and _has_value(slot):
            lines.append(assumption_line(name, str(slot["value"])))
    return lines


def is_explicit_defaults(text: str) -> bool:
    """True when the reply IS an acceptance of the defaults, not merely mentions one.

    Answer codes ("1a") are removed first, then punctuation and filler words
    ("please", "the rest"). What remains must be at most four words and exactly one
    of the accepted phrases: "defaults", "use defaults", "you decide", "just do it",
    ... So "1a, rest defaults" accepts, and "I don't want the defaults, use OCR" does
    not (it is free text for the model to merge).
    """
    stripped = _ANSWER_CODE_RE.sub(" ", text or "")
    words = re.sub(r"[^a-z0-9' ]+", " ", stripped.lower().replace("\u2019", "'")).split()
    words = [w for w in words if w not in _DEFAULTS_FILLER]
    if not words or len(words) > _DEFAULTS_MAX_WORDS:
        return False
    return _DEFAULTS_PHRASE_RE.fullmatch(" ".join(words)) is not None


def parse_answers(text: str, questions: list[dict[str, Any]]) -> dict[int, tuple[int, str]]:
    """Map question index to ``(option index, text after the code)`` for "1a 4b #notes".

    The text after a code runs to the next code, with separators (spaces, commas,
    semicolons, full stops, dashes) trimmed; it is empty when the code stands alone.
    Codes that name a question or option that does not exist are ignored. When a
    question is answered twice, the last code wins.
    """
    source = text or ""
    matches = list(_ANSWER_CODE_RE.finditer(source))
    answers: dict[int, tuple[int, str]] = {}
    for position, match in enumerate(matches):
        question = int(match.group(1)) - 1
        option = ord(match.group(2).lower()) - ord("a")
        if not 0 <= question < len(questions):
            continue
        if not 0 <= option < len(questions[question].get("options") or []):
            continue
        end = matches[position + 1].start() if position + 1 < len(matches) else len(source)
        addendum = source[match.end() : end].strip(" \t\r\n,;.-")
        answers[question] = (option, " ".join(addendum.split()))
    return answers


def parse_answer_codes(text: str, questions: list[dict[str, Any]]) -> dict[int, int]:
    """Map question index (0-based) to option index (0-based) for codes like "1a 2c".

    Codes that name a question or option that does not exist are ignored. When a
    question is answered twice, the last code wins.
    """
    return {q: option for q, (option, _) in parse_answers(text, questions).items()}


# Question order: open blocking slots by impact on the workflow's shape, then the
# important slots whose answer most changes the deliverable.
BLOCKING_PRIORITY: tuple[str, ...] = (
    "write_destinations",
    "external_systems",
    "irreversible_actions",
    "input_variability",
    "output_structure",
    "human_approval_points",
    "input_source",
    "deliverable",
    "done_when",
    "goal",
)
IMPORTANT_PRIORITY: tuple[str, ...] = (
    "quality_bar",
    "constraints",
    "volume_scale",
    "depth",
    "trigger",
    "runtime_trust",
)
FILL_IMPORTANT: frozenset[str] = frozenset({"quality_bar", "constraints", "volume_scale", "depth"})
MAX_QUESTIONS = 5


def order_questions(questions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Questions in the fixed priority order (blocking by impact, then important)."""
    rank = {name: i for i, name in enumerate(BLOCKING_PRIORITY + IMPORTANT_PRIORITY)}
    return sorted(questions, key=lambda q: rank.get(str(q.get("slot")), len(rank)))


def _open_important(slots: dict[str, Any]) -> list[str]:
    """Important slots worth a question: assumed or unknown, in priority order.

    ``depth`` counts only when it has a value (a playbook deliverable).
    """
    out = []
    for name in IMPORTANT_PRIORITY:
        slot = _slot(slots, name)
        if name not in FILL_IMPORTANT or slot.get("source") not in ("assumed", "unknown"):
            continue
        if name == "depth" and not _has_value(slot):
            continue
        out.append(name)
    return out


def question_plan_problems(
    slots: dict[str, Any], questions: list[dict[str, Any]], *, first_round: bool
) -> list[str]:
    """What breaks the question rule; empty when the questions are right.

    Open blocking slots come first (up to 5). In the first round, places left are
    filled with open important slots (quality_bar, constraints, volume_scale, depth),
    up to 5 questions in all. A later round needs at least one question.
    """
    missing = missing_blocking(slots)
    asked = [str(q.get("slot")) for q in questions]
    # A slot an option asks for as its follow-up ("name the channel") counts as asked.
    followups = {
        str(o.get("followup_slot"))
        for q in questions
        for o in q.get("options") or []
        if isinstance(o, dict) and o.get("followup_slot")
    }
    problems = []
    blocking_needed = min(MAX_QUESTIONS, len(missing))
    blocking_asked = [s for s in missing if s in asked or s in followups]
    if len(blocking_asked) < blocking_needed and any(s in IMPORTANT_SLOTS for s in asked):
        problems.append(
            "ask every open blocking slot before any important one; open: " + ", ".join(missing)
        )
    if first_round:
        candidates = _open_important(slots)
        separate = len([s for s in missing if s not in followups or s in asked])
        wanted = min(MAX_QUESTIONS, separate + len(candidates))
        if len(asked) < wanted:
            problems.append(
                f"ask {wanted} questions: the open blocking slots ({', '.join(missing) or 'none'}), "
                f"then important slots in this order ({', '.join(candidates) or 'none'})"
            )
    elif missing and not asked:
        problems.append("at least one question is needed while blocking slots are open")
    return problems


def _recommended(question: dict[str, Any]) -> str | None:
    for option in question.get("options") or []:
        if isinstance(option, dict) and option.get("recommended") and not option.get("fallback"):
            return str(option.get("label", "")).strip() or None
    return None


def apply_answers(
    slots: dict[str, Any],
    questions: list[dict[str, Any]],
    answers: dict[int, Any],
) -> tuple[dict[str, Any], set[str]]:
    """Write each coded answer into its slot. Returns the new slots and the slots answered.

    ``answers`` maps a question index to an option index, or to ``(option index,
    text after the code)`` as :func:`parse_answers` returns. A real option sets
    ``source: user``; the "Not sure - use default" option sets the recommended
    option with ``source: assumed``. Text after the code fills the option's
    ``followup_slot`` (``source: user``); without one it is added to the value.
    """
    merged = {name: dict(_slot(slots, name)) for name in ALL_SLOTS}
    answered: set[str] = set()
    for q_index, given in answers.items():
        o_index, addendum = given if isinstance(given, tuple) else (given, "")
        question = questions[q_index]
        name = question.get("slot")
        if name not in merged:
            continue
        option = (question.get("options") or [])[o_index]
        if option.get("fallback"):
            value, source = _recommended(question), "assumed"
        else:
            value, source = str(option.get("label", "")).strip(), "user"
        followup_slot = option.get("followup_slot")
        if addendum and followup_slot in merged and followup_slot != name:
            merged[followup_slot].update({"value": addendum, "source": "user"})
            merged[followup_slot].pop("reason", None)
            answered.add(str(followup_slot))
        elif addendum and value:
            value = f"{value}; {addendum}"
        if value:
            merged[name].update({"value": value, "source": source})
            merged[name].pop("reason", None)
            answered.add(str(name))
    return merged, answered


def apply_defaults(
    slots: dict[str, Any], questions: list[dict[str, Any]], answered: set[str] | None = None
) -> dict[str, Any]:
    """Fill every open slot for a forced ready ("defaults" or the round limit).

    Each question not answered takes its recommended option, ``source: assumed``, unless
    its slot is already filled. A blocking slot that is still empty gets a placeholder
    value saying the builder decides it, ``source: assumed``.
    """
    merged = {name: dict(_slot(slots, name)) for name in ALL_SLOTS}
    done = answered or set()
    for question in questions:
        name = question.get("slot")
        if name not in merged or name in done or is_filled(str(name), merged[name]):
            continue
        value = _recommended(question)
        if value:
            merged[name].update({"value": value, "source": "assumed"})
            merged[name].pop("reason", None)
    tied = set(_cross_slot_unfilled(merged))
    for name in BLOCKING_SLOTS:
        slot = merged[name]
        if is_filled(name, slot) and name not in tied:
            continue
        if not _has_value(slot):
            slot["value"] = UNSPECIFIED_VALUE
        slot["source"] = "assumed"
        slot.pop("reason", None)
    # No slot is left unknown after a forced ready: important ones get their default.
    for name in IMPORTANT_SLOTS:
        slot = merged[name]
        if slot.get("source") != "unknown" and _has_value(slot):
            continue
        slot["value"] = (
            str(slot["value"]) if _has_value(slot) else _IMPORTANT_DEFAULTS.get(name, UNSPECIFIED_VALUE)
        )
        slot["source"] = "assumed"
        slot.pop("reason", None)
    return merged


def evaluate(
    slots: dict[str, Any],
    *,
    explicit_defaults: bool = False,
    rounds_asked: int = 0,
    max_rounds: int = 2,
) -> dict[str, Any]:
    """Apply the readiness rule.

    Args:
        slots: The brief's ``slots`` object.
        explicit_defaults: The user's latest reply accepts the defaults.
        rounds_asked: Question rounds already sent to the user.
        max_rounds: The round limit (``BUILDER_INTAKE_MAX_ROUNDS``).

    Returns:
        ``ready``, ``reason`` (``filled``, ``explicit_defaults``, ``max_rounds`` or
        ``gaps``), ``missing`` (blocking slots not filled), ``invalid_not_applicable``,
        and ``assumptions`` (lines to show: important slots, and blocking ones when the
        ready was forced).
    """
    missing = missing_blocking(slots)
    if not missing:
        reason = "filled"
    elif explicit_defaults:
        reason = "explicit_defaults"
    elif rounds_asked >= max_rounds:
        reason = "max_rounds"
    else:
        reason = "gaps"
    forced = reason in ("explicit_defaults", "max_rounds")
    return {
        "ready": reason != "gaps",
        "reason": reason,
        "missing": missing,
        "invalid_not_applicable": invalid_not_applicable(slots),
        "assumptions": assumption_lines(slots, include_blocking=forced),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("brief", type=Path, help="intake brief JSON, or an object with 'slots'")
    parser.add_argument("--defaults", action="store_true", help="the user accepted the defaults")
    parser.add_argument("--rounds-asked", type=int, default=0, help="question rounds already sent")
    parser.add_argument("--max-rounds", type=int, default=2, help="the round limit")
    parser.add_argument("--json", action="store_true", help="print the result as JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        data = json.loads(args.brief.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"cannot read {args.brief.name}: {exc}", file=sys.stderr)
        return 2
    slots = data.get("slots") if isinstance(data, dict) else None
    if not isinstance(slots, dict):
        print("the file has no 'slots' object", file=sys.stderr)
        return 2
    result = evaluate(
        slots,
        explicit_defaults=args.defaults,
        rounds_asked=args.rounds_asked,
        max_rounds=args.max_rounds,
    )
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"{'READY' if result['ready'] else 'NOT READY'} ({result['reason']})")
        for name in result["missing"]:
            print(f"  missing blocking slot: {name}")
        for name in result["invalid_not_applicable"]:
            print(f"  not_applicable not allowed or without a reason: {name}")
        for line in result["assumptions"]:
            print(f"  {line}")
    return 0 if result["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
