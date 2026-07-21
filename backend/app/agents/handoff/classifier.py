"""LLM-driven classifier: does this handoff want coding or just testing?

Returns the literal strings ``"coding"`` or ``"test"``. The classifier is
intentionally cheap (Haiku, max_tokens=8) — when the user already passed
``mode`` explicitly we never call here in the first place.
"""

from __future__ import annotations

import logging

from app.agents.cached_invoke import cached_invoke
from app.agents.model_factory import build_model

logger = logging.getLogger("app.agents.handoff.classifier")


_CLASSIFIER_SYSTEM_PROMPT = """You classify software-engineering tasks into one of two modes.

Return EXACTLY one word — either "coding" or "test" — no quotes, no punctuation, no explanation.

Rules:
- "test" — the task is purely about tests (writing missing tests, fixing failing tests, evaluating coverage, adding compliance/audit reports). The task does NOT require any production-code changes.
- "coding" — the task requires changes to production source code. Tests may also be added or modified, but the primary deliverable is a code change.

If ambiguous, prefer "coding". Single word only."""


async def classify_task(
    task_description: str,
    transcript_excerpt: str | None = None,
    *,
    usage_sink=None,
) -> str:
    """Classify a handoff task. Returns ``"coding"`` or ``"test"``."""
    # Build the model OUTSIDE the try so a provider-misconfiguration
    # (``ModelConfigurationError``) propagates exactly as the legacy agent
    # constructor did — the try/except below mirrors the legacy one-shot guard,
    # which only ever wrapped the invocation itself.
    llm = build_model(max_tokens=8)
    user_msg = task_description.strip()
    if transcript_excerpt:
        excerpt = transcript_excerpt[-2000:]
        user_msg = f"Task: {user_msg}\n\nRecent IDE conversation context:\n{excerpt}"
    try:
        # ISS-033: route the direct ainvoke through the ONE shared cached-invoke helper.
        # The stable classifier system prompt is the cache-eligible prefix; the tokens
        # are counted via the sink. Pass the pre-built model so build_model stays
        # OUTSIDE the try (ModelConfigurationError propagation preserved).
        raw, _usage = await cached_invoke(
            user_msg,
            system=_CLASSIFIER_SYSTEM_PROMPT,
            model=llm,
            usage_sink=usage_sink,
        )
        raw = raw.strip().lower()
    except Exception as exc:
        logger.warning("Classifier failed, defaulting to coding: %s", exc)
        return "coding"
    if raw.startswith("test"):
        return "test"
    return "coding"
