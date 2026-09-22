"""Authentication PII in logs — COGNITO-AUTH-QA-BUGS.md "Authentication PII in Logs".

``core.auth_events.emit(email=...)`` must never write the plaintext address into the log
line — only a stable, non-reversible hash. Stability matters as much as redaction: an
operator has to be able to correlate repeated failures for one account without the log
ever carrying the address itself.

A direct test of ``auth_events.emit`` — no HTTP, no database, no provider. The TIMING
half of this pair (an unknown email must not return faster than a known one on
``POST /api/auth/login``) needs a real seeded row and a real endpoint round-trip to mean
anything, so it lives in ``tests/integration/api/test_login_timing_api.py``.
"""

from __future__ import annotations

from app.core import auth_events
from app.core.auth_events import AuthEvent


class TestAuthEventPiiRedaction:
    def test_emit_never_writes_plaintext_email(self, caplog):
        """core.auth_events.emit(email=...) must hash the address before it
        reaches the log line — never the raw value."""
        plaintext_email = "attacker-target@example.com"
        with caplog.at_level("WARNING", logger="app.auth.events"):
            auth_events.emit(
                AuthEvent.LOGIN_FAILURE, email=plaintext_email, reason="unknown_user"
            )
        assert len(caplog.records) == 1
        message = caplog.records[0].message
        assert plaintext_email not in message
        assert "email_hash" in message

    def test_hash_is_stable_for_the_same_email(self, caplog):
        """The SAME email must hash to the SAME value across calls, so
        repeated-attempt aggregation/alerting still works post-redaction."""
        import json

        email = "repeat-offender@example.com"
        with caplog.at_level("WARNING", logger="app.auth.events"):
            auth_events.emit(
                AuthEvent.LOGIN_FAILURE, email=email, reason="unknown_user"
            )
            auth_events.emit(
                AuthEvent.LOGIN_FAILURE, email=email, reason="unknown_user"
            )
        hashes = [json.loads(r.message)["email_hash"] for r in caplog.records]
        assert hashes[0] == hashes[1]

    def test_hash_differs_for_different_emails(self, caplog):
        import json

        with caplog.at_level("WARNING", logger="app.auth.events"):
            auth_events.emit(
                AuthEvent.LOGIN_FAILURE, email="a@example.com", reason="unknown_user"
            )
            auth_events.emit(
                AuthEvent.LOGIN_FAILURE, email="b@example.com", reason="unknown_user"
            )
        hashes = [json.loads(r.message)["email_hash"] for r in caplog.records]
        assert hashes[0] != hashes[1]
