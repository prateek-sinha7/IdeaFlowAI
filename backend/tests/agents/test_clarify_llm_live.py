"""tests/agents/test_clarify_llm_live.py — opt-in LIVE Haiku clarify parse smoke.

Proves the KAN-82 / FIX-024 fix END-TO-END against real AWS Bedrock Haiku: that
``ClarifyEngine._generate_questions_via_llm`` — with the stricter prompt + the
tolerant ``_parse_llm_json_array`` parser — accepts a real Haiku 4.5 response and
returns content-aware questions, WITHOUT falling to the static library.

The offline ``tests/unit/test_clarify_json_parse.py`` is the blocking proof of the
parser; this smoke is the live confirmation the user asked for on Part B. It is
opt-in / self-skipping so the default offline suite and credential-less CI stay
green.

Opt-in — this test runs ONLY when BOTH hold:
  * env ``RUN_LIVE_BEDROCK=1`` is set (explicit opt-in), AND
  * AWS credentials actually resolve (SSO not expired) — probed via STS.
Otherwise it ``pytest.skip(...)``\\s with the exact command to run it live.

Run it live (creds via SSO — see the local-run-bedrock memory: profile hex-ai-fe,
ANTHROPIC_API_KEY empty, model claude-haiku-4-5):
    aws sso login --profile hex-ai-fe
    RUN_LIVE_BEDROCK=1 AWS_PROFILE=hex-ai-fe \\
        python3.11 -m pytest tests/agents/test_clarify_llm_live.py -v -s

If SSO/Bedrock is unavailable the offline tolerant-parser tests stand as evidence
and the live confirm defers to the milestone-end live pass
(defer-live-verification convention).
"""

from __future__ import annotations

import logging
import os

import pytest

from agents.execution_engine.clarify_engine import ClarifyEngine

_RUN_LIVE_HINT = (
    "LIVE Bedrock clarify smoke is opt-in. To run it:\n"
    "    aws sso login --profile hex-ai-fe\n"
    "    RUN_LIVE_BEDROCK=1 AWS_PROFILE=hex-ai-fe "
    "python3.11 -m pytest tests/agents/test_clarify_llm_live.py -v -s"
)


def _aws_creds_resolve() -> tuple[bool, str]:
    """Return ``(ok, detail)`` — whether usable AWS credentials resolve right now."""
    try:
        import boto3
        from botocore.exceptions import BotoCoreError, ClientError

        from app.core.config import settings

        region = settings.AWS_REGION or os.getenv("AWS_REGION") or None
        ident = boto3.client("sts", region_name=region).get_caller_identity()
        return True, f"sts caller={ident.get('Arn', '<unknown>')}"
    except (BotoCoreError, ClientError) as exc:  # SSO expired / no creds / no token
        return False, f"AWS credentials did not resolve: {type(exc).__name__}: {exc}"
    except Exception as exc:  # pragma: no cover — defensive (e.g. boto3 missing)
        return False, f"AWS credential probe failed: {type(exc).__name__}: {exc}"


def _skip_reason() -> str | None:
    """Return a skip reason if the live smoke must not run, else ``None``."""
    if os.getenv("RUN_LIVE_BEDROCK") != "1":
        return f"RUN_LIVE_BEDROCK!=1 — live Bedrock clarify smoke is opt-in.\n{_RUN_LIVE_HINT}"

    from app.core.config import settings

    if settings.ANTHROPIC_API_KEY:
        return None

    ok, detail = _aws_creds_resolve()
    if not ok:
        return f"{detail}\n{_RUN_LIVE_HINT}"
    return None


pytestmark = pytest.mark.skipif(_skip_reason() is not None, reason=_skip_reason() or "")


@pytest.mark.asyncio
async def test_live_haiku_clarify_returns_content_aware_questions(caplog):
    """A representative brief -> real Haiku -> tolerant parser -> content-aware
    questions (NOT the static-library fallback)."""
    planning_context = {
        "user_request": (
            "Build an internal expense-approval dashboard for finance managers. "
            "Managers should see pending expense claims, drill into each claim's "
            "line items and receipts, and approve or reject with a comment. "
            "We also need a summary view of monthly spend by department."
        ),
        "inferred_intent": "internal finance approval dashboard prototype",
        "missing_information": ["ui_style", "key_screens", "personas"],
        "pipeline_type": "prototype",
        "topic": "expense-approval dashboard",
    }

    engine = ClarifyEngine()
    with caplog.at_level(logging.WARNING):
        questions = await engine._generate_questions_via_llm(
            planning_context,
            round_num=1,
            pipeline_type="prototype",
            is_no_template=False,
        )

    assert questions, "live Haiku returned no parseable questions (parser fell to None)"
    assert isinstance(questions, list)
    for q in questions:
        assert q.get("question_text"), f"question missing question_text: {q}"

    # The tolerant parser accepted Haiku's output — the static fallback must NOT
    # have fired for the LLM path.
    fell_back = any(
        "falling back to static library" in rec.getMessage()
        for rec in caplog.records
    )
    assert not fell_back, "LLM path fell back to the static library (parse failed)"
