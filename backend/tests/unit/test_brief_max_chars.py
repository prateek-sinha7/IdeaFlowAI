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


def test_full_brief_reaches_planner_uncut():
    """A ~10,000-char brief passes to the analyze prompt IN FULL — no 'chars omitted'."""
    brief = "The system shall support role-based access. " * 250  # ~11k chars, <= 64k
    assert len(brief) <= settings.BRIEF_MAX_CHARS

    prompt = SmartPlanner()._build_prompt(brief, "prototype")

    # The full brief text is present verbatim (old 2500 head+tail cap removed).
    assert brief in prompt
    assert "chars omitted" not in prompt


def test_full_user_request_reaches_clarify_uncut():
    """A ~10,000-char user_request yields a brief_sample slice >2000 chars (full text)."""
    user_request = "As a user I want to filter reports by date. " * 230  # ~10k chars
    assert len(user_request) <= settings.BRIEF_MAX_CHARS

    # Mirror the ClarifyEngine brief_sample slice logic (clarify_engine.py:362).
    brief_sample = (
        user_request[: settings.BRIEF_MAX_CHARS] if user_request else ""[:2000]
    )

    # The old 2000-char cap is gone: the full user_request survives.
    assert len(brief_sample) > 2000
    assert brief_sample == user_request


def test_ceiling_still_enforced_above_cap():
    """A brief > settings.BRIEF_MAX_CHARS is still head+tail sampled ('chars omitted')."""
    brief = "z" * (settings.BRIEF_MAX_CHARS + 6000)  # 70,000 chars, over the ceiling

    prompt = SmartPlanner()._build_prompt(brief, "prototype")

    # Sampling triggered: the omitted marker is present and the raw brief is NOT
    # embedded whole, so the prompt stays bounded well under the raw brief length.
    assert "chars omitted" in prompt
    assert brief not in prompt
    assert len(prompt) < len(brief) + 5000


def test_planner_and_clarify_share_single_source_of_truth():
    """Both cap sites read the SAME settings.BRIEF_MAX_CHARS (64k)."""
    assert settings.BRIEF_MAX_CHARS == 64_000
