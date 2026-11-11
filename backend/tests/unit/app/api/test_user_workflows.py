"""422 ``connector_grants_not_allowed`` on the save paths (design 5.5 layer 4).

Flat selection saves, manifest saves for a predefined trust and override-row saves
all refuse ``tools.connectors`` with the run-envelope detail
``{error, code, recoverable}``. The checks run before any row is stored, so no
database is involved.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.api.run_engine import CONNECTOR_GRANTS_NOT_ALLOWED_MESSAGE
from app.api.user_workflows import (
    _compile_check_manifest,
    _compile_check_override_steps,
    _compile_selections_trust_user,
    _connector_grants_refused,
)

_JIRA = "jira__get_issue"
_AGENT_A = "market-research-agent"
_AGENT_B = "swot-analyst"
_CODE = "connector_grants_not_allowed"


def _step(**tools: object) -> dict:
    step: dict = {"agent": "demo-agent", "strategy": "single_shot"}
    if tools:
        step["tools"] = dict(tools)
    return step


def _assert_envelope(exc: HTTPException) -> None:
    assert exc.status_code == 422
    assert isinstance(exc.detail, dict)
    assert set(exc.detail) == {"error", "code", "recoverable"}
    assert exc.detail["code"] == _CODE
    assert exc.detail["recoverable"] is False
    assert exc.detail["error"]


def test_connector_grants_refused_builds_422_envelope_when_given_a_message() -> None:
    exc = _connector_grants_refused("nope")

    assert exc.status_code == 422
    assert exc.detail == {"error": "nope", "code": _CODE, "recoverable": False}


class TestCompileSelectionsTrustUser:
    def test_compile_selections_trust_user_raises_envelope_when_a_step_names_connectors(
        self,
    ) -> None:
        selections = {_AGENT_A: {"tools": {"connectors": [_JIRA]}}}

        with pytest.raises(HTTPException) as excinfo:
            _compile_selections_trust_user("custom", [_AGENT_A, _AGENT_B], selections)

        _assert_envelope(excinfo.value)
        assert excinfo.value.detail["error"] == CONNECTOR_GRANTS_NOT_ALLOWED_MESSAGE

    def test_compile_selections_trust_user_raises_envelope_when_wizard_key_sits_beside(
        self,
    ) -> None:
        selections = {
            "_wizard": {"brief": "x"},
            _AGENT_B: {"tools": {"connectors": [_JIRA]}},
        }

        with pytest.raises(HTTPException) as excinfo:
            _compile_selections_trust_user("custom", [_AGENT_A, _AGENT_B], selections)

        _assert_envelope(excinfo.value)

    def test_compile_selections_trust_user_accepts_empty_connectors_when_explicitly_off(
        self,
    ) -> None:
        selections = {_AGENT_A: {"tools": {"connectors": []}}}

        _compile_selections_trust_user("custom", [_AGENT_A, _AGENT_B], selections)


class TestCompileCheckManifest:
    @pytest.mark.parametrize("trust", ["file", "builtin"])
    def test_compile_check_manifest_raises_envelope_when_predefined_trust_names_connectors(
        self, trust: str
    ) -> None:
        manifest = {"steps": [_step(connectors=[_JIRA])]}

        with pytest.raises(HTTPException) as excinfo:
            _compile_check_manifest(manifest, "workflow:test", trust)

        _assert_envelope(excinfo.value)


class TestCompileCheckManifestAcceptsConnectorGrants:
    @pytest.mark.parametrize("trust", ["user", "db"])
    def test_compile_check_manifest_returns_none_when_connector_grant_is_user_authored(
        self, trust: str
    ) -> None:
        manifest = {
            "steps": [
                {
                    "agent": _AGENT_A,
                    "strategy": "single_shot",
                    "tools": {"connectors": [_JIRA]},
                }
            ]
        }

        assert _compile_check_manifest(manifest, "workflow:test", trust) is None


class TestCompileCheckOverrideSteps:
    def test_compile_check_override_steps_raises_envelope_when_a_step_names_connectors(
        self,
    ) -> None:
        with pytest.raises(HTTPException) as excinfo:
            _compile_check_override_steps(
                [_step(connectors=[_JIRA])], "custom", "override:test"
            )

        _assert_envelope(excinfo.value)
