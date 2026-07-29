"""evals/hybrid/common/test_live_scenario_model_resolution.py

Unit coverage for ``live_scenario._resolve_ctx_model`` — the small helper that
decides what value ``run_live_scenario_once`` passes as ``AgentContext.model``.

Confirms the eval harness's free-provider call path passes
``provider="mistral"`` to ``build_model()``, while every existing call site
(``provider=None``, the default) is completely unaffected — no network calls,
``build_model`` is mocked.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from evals.hybrid.common.live_scenario import _resolve_ctx_model


def test_provider_none_passes_model_through_unchanged() -> None:
    """Every existing caller (live_benchmark.py, test_live.py) omits `provider`
    — confirm the default path is a pure pass-through, not a build_model call."""
    assert _resolve_ctx_model(None, None) is None
    assert _resolve_ctx_model(None, "some-model-id") == "some-model-id"


def test_provider_mistral_calls_build_model_with_explicit_opt_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_build_model = MagicMock(name="build_model")
    monkeypatch.setattr(
        "app.agents.model_factory.build_model", mock_build_model
    )

    result = _resolve_ctx_model("mistral", "mistral-small-latest")

    mock_build_model.assert_called_once_with("mistral-small-latest", provider="mistral")
    assert result is mock_build_model.return_value


def test_provider_mistral_with_no_model_override_still_forces_mistral(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_build_model = MagicMock(name="build_model")
    monkeypatch.setattr(
        "app.agents.model_factory.build_model", mock_build_model
    )

    _resolve_ctx_model("mistral", None)

    mock_build_model.assert_called_once_with(None, provider="mistral")
