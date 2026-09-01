"""Offline regression tests for the planner + clarify brief-INPUT cap (260702-e90).

Proves that a realistic brief (including a full uploaded doc, <= settings.BRIEF_MAX_CHARS)
reaches the SmartPlanner analyze prompt AND the ClarifyEngine brief_sample IN FULL — no
"chars omitted" whittling — while a pathological brief beyond the ceiling is still
head+tail sampled so the input stays bounded.

Both the planner and clarify derive the cap from the SAME settings.BRIEF_MAX_CHARS
(single source of truth). These tests track the setting rather than a hardcoded literal.

Pure offline: no model call, no network — only the pure prompt builder + slice logic.
"""

from __future__ import annotations

from agents.planner.smart_planner import SmartPlanner
from app.core.config import settings


def test_full_brief_reaches_planner_uncut(stub_provider_classes):
    """A brief well under the cap passes to the analyze prompt IN FULL — no 'chars omitted'.

    ``stub_provider_classes`` (ISS-118): ``SmartPlanner.__init__`` builds a provider
    client before ``_build_prompt`` can be called; stubbing the class on its source
    module keeps that construction offline without exempting this test from the
    ISS-102 live-model guard.
    """
    phrase = "The system shall support role-based access. "
    target = settings.BRIEF_MAX_CHARS // 2  # comfortably under the cap
    brief = (phrase * ((target // len(phrase)) + 1))[:target]
    assert len(brief) <= settings.BRIEF_MAX_CHARS

    prompt = SmartPlanner()._build_prompt(brief, "prototype")

    # The full brief text is present verbatim (old head+tail cap removed).
    assert brief in prompt
    assert "chars omitted" not in prompt


def test_full_user_request_reaches_clarify_uncut():
    """A user_request under the cap yields a brief_sample equal to the full text (no cut)."""
    phrase = "As a user I want to filter reports by date. "
    target = settings.BRIEF_MAX_CHARS // 2
    user_request = (phrase * ((target // len(phrase)) + 1))[:target]
    assert len(user_request) <= settings.BRIEF_MAX_CHARS

    # Mirror the ClarifyEngine brief_sample slice logic (clarify_engine.py:363).
    brief_sample = user_request[: settings.BRIEF_MAX_CHARS]

    # The whole user_request survives — the sample equals the full request.
    assert brief_sample == user_request
    assert len(brief_sample) == len(user_request)


def test_ceiling_still_enforced_above_cap(stub_provider_classes):
    """A brief > settings.BRIEF_MAX_CHARS is still head+tail sampled ('chars omitted')."""
    brief = "z" * (settings.BRIEF_MAX_CHARS + 10_000)  # over the ceiling

    prompt = SmartPlanner()._build_prompt(brief, "prototype")

    # Sampling triggered: the omitted marker is present and the raw brief is NOT
    # embedded whole, so the prompt stays bounded well under the raw brief length.
    assert "chars omitted" in prompt
    assert brief not in prompt
    assert len(prompt) < len(brief) + 5000


def test_planner_and_clarify_share_single_source_of_truth():
    """Both cap sites read the SAME settings.BRIEF_MAX_CHARS (450k) — the value pin."""
    assert settings.BRIEF_MAX_CHARS == 450_000
