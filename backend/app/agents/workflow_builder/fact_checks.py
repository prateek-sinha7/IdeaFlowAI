"""Draft checks against the settled intake brief (intake flag on).

Two deterministic checks the Server_Gate runs next to ``irreversible_gate``:

* :func:`check_facts`, fact propagation: every concrete identifier the user gave or
  the request stated (a Slack channel, a Jira project or issue key, an email
  recipient, a repository, a URL, a file name) must appear verbatim somewhere in
  the draft's steps or deliverable. Otherwise the step that uses it never sees it
  (the request reaches only the first step).
* :func:`check_placeholders`: no step prompt may tell the writer to insert a
  bracketed placeholder for a fact the intake recorded as missing.

The module is pure: no I/O, no ``app.api`` import. Messages hold only the
identifiers themselves and step ids, never prompt text.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

from app.agents.workflow_builder.ports import GateIssue, GateRule

__all__ = [
    "PLACEHOLDER_RULE",
    "PROPAGATION_RULE",
    "IntakeFacts",
    "check_facts",
    "check_placeholders",
    "concrete_facts",
]

PROPAGATION_RULE: Final[GateRule] = "fact_propagation"
PLACEHOLDER_RULE: Final[GateRule] = "placeholder"

_GIVEN_SOURCES: Final = frozenset({"request", "user"})
_PATTERNS: Final[tuple[tuple[str, re.Pattern[str]], ...]] = (
    ("url", re.compile(r"https?://[^\s)>\]\"']+")),
    ("email", re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")),
    ("slack_channel", re.compile(r"(?<![\w#&])#[a-z0-9][a-z0-9._-]{1,79}")),
    ("jira_issue", re.compile(r"\b[A-Z][A-Z0-9]{1,9}-\d+\b")),
    ("jira_project", re.compile(r"\b(?:project|key)\s+([A-Z][A-Z0-9]{1,9})\b")),
    (
        "file_name",
        re.compile(r"\b[\w-]+\.(?:md|html|json|csv|txt|pdf|docx|xlsx|pptx|yaml|yml)\b"),
    ),
)
_REPO_RE: Final = re.compile(r"\b[A-Za-z0-9_.-]{2,}/[A-Za-z0-9_.-]{2,}\b")
_REPO_CONTEXT_RE: Final = re.compile(r"github|gitlab|repo", re.IGNORECASE)
_NOT_REPO: Final = frozenset({"and/or", "input/output", "read/write", "pdf/docx"})
_TRAILING: Final = ".,;:!?"

# A bracketed placeholder in a prompt, and the words that make it a "never do this".
_BRACKET_RE: Final = re.compile(r"\[([^\]\n]{2,60})\]")
_NEGATION_RE: Final = re.compile(
    r"\b(?:never|do not|don'?t|avoid|must not|should not)\b[^.\n]{0,40}"
    r"\b(?:write|use|insert|leave|add|put|output|placeholders?)\b"
    r"|\bno placeholders?\b|\bplaceholders? (?:are|is) (?:not|never)\b",
    re.IGNORECASE,
)
_WORD_RE: Final = re.compile(r"[a-z0-9]+")
_STOP: Final = frozenset(
    {
        "the",
        "a",
        "an",
        "to",
        "of",
        "for",
        "and",
        "or",
        "in",
        "on",
        "with",
        "our",
        "your",
        "its",
        "it",
    }
)


@dataclass(frozen=True, slots=True)
class IntakeFacts:
    """What the settled intake brief requires of a draft.

    Attributes:
        required: ``(slot, identifier)`` pairs that must appear verbatim in the draft.
        missing: Facts the deliverable needs that nobody supplied; no placeholder
            may stand in for them.
    """

    required: tuple[tuple[str, str], ...] = ()
    missing: tuple[str, ...] = ()


def concrete_facts(slots: Mapping[str, Any]) -> list[tuple[str, str]]:
    """``(slot, identifier)`` for each concrete identifier in a given (request/user) slot."""
    found: list[tuple[str, str]] = []
    seen: set[str] = set()
    for name, slot in slots.items():
        if not isinstance(slot, Mapping) or slot.get("source") not in _GIVEN_SOURCES:
            continue
        value = slot.get("value")
        if not isinstance(value, str):
            continue
        for _kind, pattern in _PATTERNS:
            for match in pattern.finditer(value):
                token = (match.group(1) if match.groups() else match.group(0)).rstrip(
                    _TRAILING
                )
                if token and token not in seen:
                    seen.add(token)
                    found.append((str(name), token))
        if _REPO_CONTEXT_RE.search(value):
            for match in _REPO_RE.finditer(value):
                token = match.group(0).rstrip(_TRAILING)
                if (
                    token.lower() not in _NOT_REPO
                    and "://" not in token
                    and token not in seen
                ):
                    seen.add(token)
                    found.append((str(name), token))
    return found


def _haystack(manifest: Mapping[str, Any]) -> str:
    """Every step (prompt and config) and the deliverable, as one text."""
    return json.dumps(
        {"steps": manifest.get("steps"), "deliverable": manifest.get("deliverable")},
        ensure_ascii=False,
    )


def check_facts(
    manifest: Mapping[str, Any], required: Iterable[tuple[str, str]]
) -> list[GateIssue]:
    """One issue per required identifier that no step or the deliverable carries."""
    text = _haystack(manifest)
    issues = []
    for slot, token in required:
        if token in text:
            continue
        issues.append(
            GateIssue(
                PROPAGATION_RULE,
                "steps",
                f"the {slot} value '{token}' that the user gave appears in no step. Put it "
                "verbatim in the prompt (or config) of every step that uses it: later steps "
                "never see the request, only their prompt and what is pasted or read.",
            )
        )
    return issues


def _words(text: str) -> set[str]:
    return {w.rstrip("s") for w in _WORD_RE.findall(text.lower()) if w not in _STOP}


def _matches(placeholder: str, fact: str) -> bool:
    """A placeholder stands for a fact when they share enough significant words."""
    have, want = _words(placeholder), _words(fact)
    if not have or not want:
        return False
    shared = have & want
    return len(shared) >= min(2, len(want))


def _sentence_before(prompt: str, start: int) -> str:
    """The text from the last sentence end (or line start) to ``start``."""
    cut = max(prompt.rfind(". ", 0, start), prompt.rfind("\n", 0, start))
    return prompt[cut + 1 : start]


def check_placeholders(
    manifest: Mapping[str, Any], missing: Sequence[str]
) -> list[GateIssue]:
    """One issue per step that tells the writer to insert a placeholder for a missing fact.

    A bracket in a "never write a placeholder such as [X]" sentence is not counted.
    """
    if not missing:
        return []
    issues = []
    for index, step in enumerate(manifest.get("steps") or []):
        if not isinstance(step, Mapping) or not isinstance(step.get("prompt"), str):
            continue
        prompt = step["prompt"]
        for match in _BRACKET_RE.finditer(prompt):
            if _NEGATION_RE.search(_sentence_before(prompt, match.start())):
                continue
            fact = next((f for f in missing if _matches(match.group(1), f)), None)
            if fact is None:
                continue
            step_id = str(step.get("instance_id") or index)
            issues.append(
                GateIssue(
                    PLACEHOLDER_RULE,
                    f"steps[{index}].prompt",
                    f"step '{step_id}' tells the writer to insert a placeholder for the missing "
                    f"fact '{fact}'. Remove it: either leave the item out and say so in the "
                    "deliverable, or stop with NEEDS_INPUT: <the fact>.",
                )
            )
            break
    return issues
