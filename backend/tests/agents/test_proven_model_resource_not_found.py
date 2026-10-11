"""A ResourceNotFound on a PROVEN model is a provider lie, not our misconfiguration.

Run 353bb0af lost `pb-validate` to
`ResourceNotFoundException: Inference Profile ARN not found` on
eu.anthropic.claude-sonnet-4-6 — minutes after pb-spec and pb-design had used the
SAME id successfully, and with a direct probe returning OK immediately after.

`_is_transient_throttle` is the SINGLE gate for the runner's same-model retry, the
runner's re-raise, and the engine's model-fallback loop, so classifying that code
permanent killed all three defences at once and the step died with no retry.
"""

import botocore.exceptions as be
import pytest

from agents.model_policy import (
    _PROVEN_MODELS,
    _is_transient_throttle,
    mark_model_proven,
)

MODEL = "eu.anthropic.claude-sonnet-4-6"


def _err(code: str, status: int = 400) -> be.ClientError:
    return be.ClientError(
        {
            "Error": {"Code": code, "Message": "x"},
            "ResponseMetadata": {"HTTPStatusCode": status},
        },
        "ConverseStream",
    )


@pytest.fixture(autouse=True)
def _clean():
    before = set(_PROVEN_MODELS)
    _PROVEN_MODELS.clear()
    yield
    _PROVEN_MODELS.clear()
    _PROVEN_MODELS.update(before)


def test_unproven_model_resource_not_found_stays_permanent():
    """A genuinely wrong ARN must still fail fast on its FIRST call."""
    assert (
        _is_transient_throttle(_err("ResourceNotFoundException", 404), MODEL) is False
    )


def test_proven_model_resource_not_found_becomes_retryable():
    mark_model_proven(MODEL)
    assert _is_transient_throttle(_err("ResourceNotFoundException", 404), MODEL) is True


def test_proven_model_does_not_launder_auth_or_validation_failures():
    """Proving a model must never turn a real fault of ours into a retry."""
    mark_model_proven(MODEL)
    for code in (
        "AccessDeniedException",
        "ValidationException",
        "UnrecognizedClientException",
        "ExpiredTokenException",
    ):
        assert _is_transient_throttle(_err(code, 403), MODEL) is False, code


def test_proof_is_per_model_not_global():
    mark_model_proven(MODEL)
    other = "eu.anthropic.claude-haiku-4-5-20251001-v1:0"
    assert (
        _is_transient_throttle(_err("ResourceNotFoundException", 404), other) is False
    )


def test_without_a_model_id_behaviour_is_unchanged():
    """Existing single-arg callers keep the old, conservative verdict."""
    mark_model_proven(MODEL)
    assert _is_transient_throttle(_err("ResourceNotFoundException", 404)) is False
    assert _is_transient_throttle(_err("ThrottlingException", 429)) is True
