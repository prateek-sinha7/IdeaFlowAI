"""An expired AWS SSO login is a credential failure (pauses as credentials and auto-resumes), not a refusal."""

from agents.execution_engine import engine


RAW = "Error when retrieving token from sso: Token has expired and refresh failed"


def test_sso_refresh_failure_maps_to_the_credential_message():
    assert engine._sanitize_agent_error(RAW) == engine._CREDENTIAL_AGENT_ERROR
    assert engine._sanitize_agent_error(RAW) in engine._CREDENTIAL_AGENT_ERRORS


def test_sso_refresh_failure_code_is_credential():
    assert engine._classify_agent_error(RAW) == "CREDENTIAL_ERROR"
