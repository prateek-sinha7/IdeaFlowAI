"""LLM-driven classifier: does this handoff want coding or just testing?

Returns the literal strings ``"coding"`` or ``"test"``. The classifier is
intentionally cheap (Haiku, max_tokens=8) — when the user already passed
``mode`` explicitly we never call here in the first place.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.model_factory import build_model

logger = logging.getLogger("app.agents.handoff.classifier")


def _extract_text(content: Any) -> str:
    """Pull plain text out of a chat-model response ``content`` payload.

    Anthropic returns a ``str``; Bedrock returns a list of content blocks
    (e.g. ``[{"type": "text", "text": "..."}]``). Mirrors
    ``app.agents.deep_agent_runner._extract_text`` so this one-shot call decodes
    model output identically to the agent runtime.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        )
    return ""


_CLASSIFIER_SYSTEM_PROMPT = """You classify software-engineering tasks into one of two modes.

Return EXACTLY one word — either "coding" or "test" — no quotes, no punctuation, no explanation.

Rules:
- "test" — the task is purely about tests (writing missing tests, fixing failing tests, evaluating coverage, adding compliance/audit reports). The task does NOT require any production-code changes.
- "coding" — the task requires changes to production source code. Tests may also be added or modified, but the primary deliverable is a code change.

If ambiguous, prefer "coding". Single word only."""


async def classify_task(task_description: str, transcript_excerpt: str | None = None) -> str:
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
        resp = await llm.ainvoke(
            [
                SystemMessage(content=_CLASSIFIER_SYSTEM_PROMPT),
                HumanMessage(content=user_msg),
            ]
        )
        raw = _extract_text(resp.content).strip().lower()
    except Exception as exc:
        logger.warning("Classifier failed, defaulting to coding: %s", exc)
        return "coding"
    if raw.startswith("test"):
        return "test"
    return "coding"
