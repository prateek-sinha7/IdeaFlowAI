"""Structured authentication events for observability and alarming.

Part of the Cognito Authentication & Authorization Migration
(``.planning/COGNITO-MIGRATION-PLAN.md`` §7 Phase 6 item 6).

WHY A DEDICATED MODULE
----------------------
The pre-migration audit recorded that authentication had effectively no
observability: a legitimate logout and a replay of a stolen-but-revoked token
were indistinguishable in the logs, and the logs largely did not exist. Two
controls this migration depends on are ALARMS, not code paths:

  * **Break-glass use** (Decision 12 / §5.6) — the account's entire
    justification rests on every use being noticed. An unalarmed break-glass
    admin is a permanent unaudited backdoor.
  * **Login-failure spikes** — the only signal for credential stuffing against
    a pool whose ``prevent_user_existence_errors`` deliberately hides
    enumeration from the attacker (and therefore from naive log analysis too).

An alarm can only fire on something machine-greppable. Free-text log lines
scattered across endpoints cannot be turned into a CloudWatch metric filter
reliably, so every auth-significant occurrence is emitted here in ONE stable
shape with a stable discriminator (``auth_event``).

CONTRACT WITH THE INFRASTRUCTURE
--------------------------------
``infra/terraform/modules/monitoring`` builds metric filters keyed on the
``auth_event`` values in :class:`AuthEvent`. Renaming a value silently breaks
the corresponding alarm — the alarm keeps reporting "no data", which looks
healthy. Treat these strings as a published interface.

PII / SECRET HYGIENE
--------------------
Never log a password, token, refresh token, or TOTP secret — not even
truncated. Emails are logged because an auth audit trail without a subject is
useless, but the user's opaque local ``id`` is preferred where available and
the email is included only for events where the account may not exist yet
(a failed login against an unknown address).
"""

from __future__ import annotations

import json
import logging
from enum import StrEnum
from typing import Any

logger = logging.getLogger("app.auth.events")


class AuthEvent(StrEnum):
    """Stable discriminators. See the module docstring before renaming any."""

    LOGIN_SUCCESS = "login_success"
    LOGIN_FAILURE = "login_failure"
    # Deliberately its own event rather than a flag on LOGIN_SUCCESS: this is
    # the one the SNS alarm keys on, and a metric filter matching a nested flag
    # is more fragile than one matching a distinct literal.
    BREAK_GLASS_LOGIN = "break_glass_login"
    LOGIN_CHALLENGE = "login_challenge"
    TOKEN_REFRESH = "token_refresh"
    TOKEN_REFRESH_FAILURE = "token_refresh_failure"
    LOGOUT = "logout"
    PASSWORD_CHANGED = "password_changed"
    PASSWORD_RESET_REQUESTED = "password_reset_requested"
    PASSWORD_RESET_COMPLETED = "password_reset_completed"
    MFA_ENROLLED = "mfa_enrolled"
    # Removing a second factor is a privilege-reducing change to an account's
    # own security posture, so it is audited as its own event rather than folded
    # into MFA_ENROLLED with a flag — an attacker who has taken over a session
    # would use exactly this to establish persistence.
    MFA_DISABLED = "mfa_disabled"
    ADMIN_MFA_BLOCKED = "admin_mfa_blocked"
    # An administrator reset another user's password. The only reset path that
    # exists when the pool uses email MFA (which disqualifies email for
    # self-service recovery), so it carries the audit weight that
    # PASSWORD_RESET_COMPLETED carries in the self-service flow.
    ADMIN_PASSWORD_RESET = "admin_password_reset"
    ROLE_CHANGED = "role_changed"
    TIER_CHANGED = "tier_changed"
    USER_CREATED = "user_created"
    USER_DELETED = "user_deleted"
    # Fires when the single-local-admin invariant is violated (§5.6). Should be
    # impossible in a healthy system, which is exactly why it deserves an alarm.
    BREAK_GLASS_INVARIANT_VIOLATED = "break_glass_invariant_violated"


# Events that must never be sampled or downgraded below WARNING, because an
# alarm depends on them reaching CloudWatch.
_ALARM_EVENTS = {
    AuthEvent.BREAK_GLASS_LOGIN,
    AuthEvent.BREAK_GLASS_INVARIANT_VIOLATED,
    AuthEvent.ADMIN_MFA_BLOCKED,
}


def emit(
    event: AuthEvent,
    *,
    user_id: str | None = None,
    email: str | None = None,
    provider: str | None = None,
    reason: str | None = None,
    **extra: Any,
) -> None:
    """Emit one structured auth event.

    Serialised as a single-line JSON object so a CloudWatch metric filter can
    match on ``{ $.auth_event = "break_glass_login" }`` without depending on
    positional log parsing (the failure mode that made the previous
    space-delimited nginx format unusable for 429 detection).

    ``reason`` is a short machine-ish token (``invalid_password``,
    ``unknown_user``, ``jwks_unavailable``) rather than a sentence, so failure
    modes can be grouped without regex-matching prose.
    """
    payload: dict[str, Any] = {"auth_event": str(event)}
    if user_id:
        payload["user_id"] = user_id
    if email:
        payload["email"] = email
    if provider:
        payload["provider"] = provider
    if reason:
        payload["reason"] = reason
    payload.update(extra)

    message = json.dumps(payload, default=str, separators=(",", ":"))

    if event in _ALARM_EVENTS:
        logger.warning(message)
    elif event in (AuthEvent.LOGIN_FAILURE, AuthEvent.TOKEN_REFRESH_FAILURE):
        logger.warning(message)
    else:
        logger.info(message)


__all__ = ["AuthEvent", "emit"]
