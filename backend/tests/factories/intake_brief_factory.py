"""Builders for builder-intake briefs (the JSON the intake model returns).

``IntakeBriefFactory.vague_pdf()`` is round one of "convert pdf to md": six blocking
gaps and five questions. ``filled_email()`` is the fully specified launch email: every
blocking slot filled, no questions. ``answer(...)`` is a later-round reply. Each
returns a plain dict; ``as_text`` serialises it the way the model would.
"""

from __future__ import annotations

import copy
import json
from typing import Any

BLOCKING = (
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
IMPORTANT = (
    "volume_scale",
    "quality_bar",
    "constraints",
    "trigger",
    "runtime_trust",
    "depth",
)


def _slot(
    value: str | None, source: str, criticality: str, reason: str | None = None
) -> dict[str, Any]:
    slot: dict[str, Any] = {
        "value": value,
        "source": source,
        "criticality": criticality,
    }
    if reason is not None:
        slot["reason"] = reason
    return slot


def question(
    slot: str, text: str, labels: tuple[str, ...], recommended: int = 0
) -> dict[str, Any]:
    """A question with the given real options and the fallback option last."""
    options: list[dict[str, Any]] = [
        {"label": label, "recommended": True}
        if index == recommended
        else {"label": label}
        for index, label in enumerate(labels)
    ]
    options.append({"label": "Not sure - use default", "fallback": True})
    return {
        "slot": slot,
        "text": text,
        "litmus": f"the {slot} answer changes the steps of the workflow",
        "options": options,
    }


PDF_QUESTIONS: tuple[dict[str, Any], ...] = (
    question(
        "input_source",
        "Where do the PDFs come from?",
        ("Uploaded at launch", "Pasted text"),
    ),
    question(
        "input_variability",
        "Are some PDFs scans?",
        ("Digital only", "Some scans", "Mostly scans"),
    ),
    question(
        "output_structure",
        "What must the Markdown keep?",
        ("Headings and tables", "Text only"),
    ),
    question(
        "deliverable",
        "One file per PDF or one combined file?",
        ("One combined file", "One per PDF"),
    ),
    question(
        "human_approval_points",
        "Should a person review the result?",
        ("No review", "Review first"),
    ),
)


SLACK_QUESTIONS: tuple[dict[str, Any], ...] = (
    question(
        "input_source",
        "Where do the release notes come from?",
        ("Pasted into the brief", "Uploaded file"),
    ),
    question(
        "output_structure",
        "How should the post be laid out?",
        ("Short summary and bullets", "Full notes"),
    ),
    question(
        "write_destinations",
        "Which Slack channel should it post to?",
        ("#releases", "Chosen at each launch"),
    ),
    question(
        "human_approval_points",
        "What should a person approve before it posts?",
        (
            "The final message before it posts",
            "The draft earlier; edits still pass a confirm step",
        ),
    ),
    question(
        "constraints",
        "What tone should the post have?",
        ("Short and neutral", "Friendly with emoji"),
    ),
)


class IntakeBriefFactory:
    """Builds intake briefs as plain dicts."""

    @classmethod
    def filled_slack(
        cls, approval: str = "The final message before it posts"
    ) -> dict[str, Any]:
        """A Slack-post brief with every blocking slot filled: ready, no questions."""
        slots = cls.vague_slack()["slots"]
        slots.update(
            {
                "input_source": _slot("Pasted into the brief", "user", "blocking"),
                "output_structure": _slot(
                    "Short summary and bullets", "user", "blocking"
                ),
                "external_systems": _slot("Write: Slack", "user", "blocking"),
                "write_destinations": _slot("#releases", "user", "blocking"),
                "human_approval_points": _slot(approval, "user", "blocking"),
                "volume_scale": _slot("one release per run", "assumed", "important"),
            }
        )
        return {
            "message_kind": "answer",
            "slots": slots,
            "questions": [],
            "ready": True,
        }

    @classmethod
    def vague_slack(cls) -> dict[str, Any]:
        """Round one of 'workflow to post release notes to slack': an irreversible post."""
        slots = cls.slots(
            goal=_slot("Post release notes to Slack", "request", "blocking"),
            deliverable=_slot("A Slack post and a short report", "request", "blocking"),
            done_when=_slot(
                "The notes are posted to the channel", "request", "blocking"
            ),
            input_variability=_slot(
                None, "not_applicable", "blocking", "one text input"
            ),
            external_systems=_slot("Write: Slack", "request", "blocking"),
            irreversible_actions=_slot(
                "Posts the release notes to Slack", "request", "blocking"
            ),
        )
        return {
            "message_kind": "new_request",
            "slots": slots,
            "questions": [copy.deepcopy(q) for q in SLACK_QUESTIONS],
            "ready": False,
        }

    @staticmethod
    def slots(**overrides: dict[str, Any]) -> dict[str, Any]:
        """All 16 slots unknown, with ``overrides`` applied by slot name."""
        slots: dict[str, Any] = {
            name: _slot(None, "unknown", "blocking") for name in BLOCKING
        }
        slots.update({name: _slot(None, "unknown", "important") for name in IMPORTANT})
        slots.update(copy.deepcopy(overrides))
        return slots

    @classmethod
    def vague_pdf(cls) -> dict[str, Any]:
        """Round one of 'create workflow for converting pdf to md content'."""
        slots = cls.slots(
            goal=_slot("Turn PDFs into Markdown", "request", "blocking"),
            done_when=_slot("Every PDF converted", "assumed", "blocking"),
            external_systems=_slot(
                None, "not_applicable", "blocking", "returned in the run"
            ),
            write_destinations=_slot(None, "not_applicable", "blocking", "no writes"),
            irreversible_actions=_slot(None, "not_applicable", "blocking", "read-only"),
            volume_scale=_slot("up to 8 PDFs per run", "assumed", "important"),
        )
        return {
            "message_kind": "new_request",
            "slots": slots,
            "minor_decisions": [{"name": "model", "value": "standard model"}],
            "questions": [copy.deepcopy(q) for q in PDF_QUESTIONS],
            "ready": False,
        }

    @classmethod
    def filled_email(cls) -> dict[str, Any]:
        """The fully specified launch email: ready, no questions."""
        na = "not_applicable"
        slots = cls.slots(
            goal=_slot(
                "Announce the billing module to customers", "request", "blocking"
            ),
            deliverable=_slot("The email text as the reply", "request", "blocking"),
            done_when=_slot(
                "150-200 words, friendly, date and link", "request", "blocking"
            ),
            input_source=_slot("The brief only", "request", "blocking"),
            input_variability=_slot(None, na, "blocking", "one text brief"),
            output_structure=_slot("Subject and body", "request", "blocking"),
            external_systems=_slot(None, na, "blocking", "returned, not sent"),
            write_destinations=_slot(None, na, "blocking", "nothing is written"),
            irreversible_actions=_slot(None, na, "blocking", "nothing is sent"),
            human_approval_points=_slot(None, na, "blocking", "nothing irreversible"),
            constraints=_slot("friendly, 150-200 words", "request", "important"),
            quality_bar=_slot("checks in the prompts", "assumed", "important"),
        )
        return {
            "message_kind": "new_request",
            "slots": slots,
            "questions": [],
            "ready": True,
        }

    @classmethod
    def answer(
        cls,
        previous: dict[str, Any],
        *,
        ready: bool = False,
        **overrides: dict[str, Any],
    ) -> dict[str, Any]:
        """A later-round reply: the previous slots with ``overrides``, no questions."""
        slots = copy.deepcopy(previous["slots"])
        slots.update(copy.deepcopy(overrides))
        return {
            "message_kind": "answer",
            "slots": slots,
            "questions": [],
            "ready": ready,
        }

    @staticmethod
    def as_text(brief: dict[str, Any]) -> str:
        """The brief as the model's reply text."""
        return json.dumps(brief)
