"""Cognito access-token verification + thin boto3 admin wrappers.

Part of the Cognito Authentication & Authorization Migration
(``.planning/COGNITO-MIGRATION-PLAN.md``). This module owns exactly two
concerns:

1. ``verify_cognito_access_token`` — offline RS256 verification of a Cognito
   *access* token against the pool's JWKS, with a small in-process cache.
   CI never calls AWS: tests sign with a locally generated RSA key and inject
   a fake JWKS (see ``tests/unit/test_cognito_verifier.py``).
2. Thin ``boto3`` wrappers for the ``cognito-idp`` Admin* API surface the
   backend needs (login, password/challenge handling, group management,
   revocation) plus the ``SECRET_HASH`` computation every Admin* call to a
   confidential client requires.

Nothing here decides *who* the effective identity is — that is
``core/identity.py``'s job (the single shared resolver dual-accepting Cognito
RS256 and legacy HS256). This module is a pure verifier + a thin AWS client
wrapper; it does not touch the ``users`` table.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import time
from dataclasses import dataclass, field
from typing import Any

import httpx
from jose import jwt
from jose.exceptions import JOSEError

from app.core.config import settings

logger = logging.getLogger("app.core.cognito")


class CognitoVerificationError(Exception):
    """Raised for any Cognito access-token verification failure.

    Deliberately a single exception type covering signature failure, expiry,
    wrong issuer, wrong client_id, wrong token_use, unknown kid, and JWKS
    unavailability — the caller (core/identity.py) only needs to know
    "this token did not verify", not the specific reason, mirroring how
    ``JWTError`` is treated for the legacy path.
    """


@dataclass
class CognitoPrincipal:
    """The verified, typed result of a successful Cognito access-token check."""

    sub: str
    jti: str
    iat: int
    exp: int
    client_id: str
    groups: list[str] = field(default_factory=list)
    username: str | None = None


def _region() -> str:
    return settings.COGNITO_REGION or settings.AWS_REGION


def _issuer() -> str:
    return f"https://cognito-idp.{_region()}.amazonaws.com/{settings.COGNITO_USER_POOL_ID}"


def _jwks_url() -> str:
    return f"{_issuer()}/.well-known/jwks.json"


# ---------------------------------------------------------------------------
# JWKS cache
# ---------------------------------------------------------------------------
# In-process TTL cache. Single-EC2 deployment (infra/README.md) means no
# shared cache is needed — this mirrors the existing per-process caching
# idiom used elsewhere in the codebase rather than introducing Redis/etc.
# Fails CLOSED: if the JWKS cannot be fetched and the cache is empty (or
# stale past a hard ceiling), verification raises rather than accepting an
# unverifiable token.

class _JwksCache:
    def __init__(self) -> None:
        self._keys: dict[str, dict[str, Any]] = {}
        self._fetched_at: float = 0.0

    def get(self, kid: str) -> dict[str, Any] | None:
        return self._keys.get(kid)

    def is_stale(self, ttl_seconds: int) -> bool:
        return (time.monotonic() - self._fetched_at) > ttl_seconds

    def replace(self, keys_by_kid: dict[str, dict[str, Any]]) -> None:
        self._keys = keys_by_kid
        self._fetched_at = time.monotonic()

    def is_empty(self) -> bool:
        return not self._keys


_jwks_cache = _JwksCache()


def _fetch_jwks() -> dict[str, dict[str, Any]]:
    """Fetch the pool's JWKS and index by `kid`. Bounded retry (2 attempts)."""
    last_exc: Exception | None = None
    for attempt in range(2):
        try:
            resp = httpx.get(_jwks_url(), timeout=5.0)
            resp.raise_for_status()
            data = resp.json()
            keys = {k["kid"]: k for k in data.get("keys", [])}
            if not keys:
                raise CognitoVerificationError("JWKS response contained no keys")
            return keys
        except Exception as exc:  # noqa: BLE001 - collapsed into one error type
            last_exc = exc
            logger.warning("JWKS fetch attempt %d failed: %s", attempt + 1, exc)
    raise CognitoVerificationError(f"JWKS unavailable: {last_exc}") from last_exc


def _get_signing_key(kid: str) -> dict[str, Any]:
    """Return the JWK for `kid`, refetching once on a cache miss/staleness.

    Refetch triggers: (a) the cache is empty, (b) it is past its TTL, or
    (c) the requested kid is simply not present yet (key rotation) — a
    single refetch attempt covers the rotation case without hammering the
    JWKS endpoint on a sustained attack of bad kids.
    """
    ttl = settings.COGNITO_JWKS_CACHE_TTL_SECONDS
    if _jwks_cache.is_empty() or _jwks_cache.is_stale(ttl) or _jwks_cache.get(kid) is None:
        _jwks_cache.replace(_fetch_jwks())

    key = _jwks_cache.get(kid)
    if key is None:
        raise CognitoVerificationError(f"Unknown signing key id: {kid!r}")
    return key


def verify_cognito_access_token(token: str) -> CognitoPrincipal:
    """Verify a Cognito *access* token offline against the pool's JWKS.

    Enforces: signature (RS256), `kid` resolution, `iss` matches this pool,
    `exp` (via jose's default expiry check), `token_use == "access"`,
    `client_id` matches the configured app client, and the presence of `sub`
    + `jti`. Returns a typed principal carrying `cognito:groups` (defaulting
    to an empty list — a user in no group is a legal, if unusual, principal).

    Raises ``CognitoVerificationError`` on any failure. Never raises a raw
    ``JOSEError``/``httpx`` exception to the caller.
    """
    try:
        unverified_header = jwt.get_unverified_header(token)
    except JOSEError as exc:
        raise CognitoVerificationError(f"malformed token header: {exc}") from exc

    kid = unverified_header.get("kid")
    if not kid:
        raise CognitoVerificationError("token header missing kid")

    signing_key = _get_signing_key(kid)

    try:
        claims = jwt.decode(
            token,
            signing_key,
            algorithms=["RS256"],
            issuer=_issuer(),
            options={
                # Cognito access tokens carry no `aud` claim (only ID tokens
                # do) -- audience is verified via client_id below instead.
                "verify_aud": False,
            },
        )
    except JOSEError as exc:
        raise CognitoVerificationError(f"token verification failed: {exc}") from exc

    if claims.get("token_use") != "access":
        raise CognitoVerificationError(
            f"expected token_use=access, got {claims.get('token_use')!r}"
        )

    client_id = claims.get("client_id")
    if not client_id or client_id != settings.COGNITO_CLIENT_ID:
        raise CognitoVerificationError("token client_id does not match configured app client")

    sub = claims.get("sub")
    jti = claims.get("jti")
    if not sub or not jti:
        raise CognitoVerificationError("token missing sub or jti")

    return CognitoPrincipal(
        sub=sub,
        jti=jti,
        iat=int(claims.get("iat", 0)),
        exp=int(claims.get("exp", 0)),
        client_id=client_id,
        groups=list(claims.get("cognito:groups", []) or []),
        username=claims.get("username"),
    )


# ---------------------------------------------------------------------------
# SECRET_HASH + thin boto3 admin wrappers
# ---------------------------------------------------------------------------

def compute_secret_hash(username: str) -> str:
    """Compute the SECRET_HASH Cognito requires for a confidential app client.

    ``HMAC-SHA256(client_secret, username + client_id)``, base64-encoded.
    Required on every Admin* auth call because the app client has a secret
    (``generate_secret = true`` in the Terraform module).
    """
    message = username + settings.COGNITO_CLIENT_ID
    digest = hmac.new(
        settings.COGNITO_CLIENT_SECRET.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return base64.b64encode(digest).decode("utf-8")


def _client():
    """Lazily construct the boto3 cognito-idp client.

    Imported lazily (function-local) so importing this module never requires
    boto3 credentials to be configured -- verify_cognito_access_token has no
    AWS-credential dependency at all, and only the Admin* wrappers below need
    a real client.
    """
    import boto3

    return boto3.client("cognito-idp", region_name=_region())


def admin_initiate_auth(email: str, password: str) -> dict[str, Any]:
    """``AdminInitiateAuth`` with ``ADMIN_USER_PASSWORD_AUTH``.

    Returns the raw boto3 response dict, which is either
    ``{"AuthenticationResult": {...}}`` on success or
    ``{"ChallengeName": ..., "Session": ..., "ChallengeParameters": {...}}``
    when Cognito needs another step (NEW_PASSWORD_REQUIRED, MFA_SETUP,
    SOFTWARE_TOKEN_MFA). The caller (api/auth.py) branches on which key is
    present.
    """
    return _client().admin_initiate_auth(
        UserPoolId=settings.COGNITO_USER_POOL_ID,
        ClientId=settings.COGNITO_CLIENT_ID,
        AuthFlow="ADMIN_USER_PASSWORD_AUTH",
        AuthParameters={
            "USERNAME": email,
            "PASSWORD": password,
            "SECRET_HASH": compute_secret_hash(email),
        },
    )


def admin_respond_to_auth_challenge(
    email: str,
    challenge_name: str,
    session: str,
    challenge_responses: dict[str, str],
) -> dict[str, Any]:
    """``AdminRespondToAuthChallenge`` for NEW_PASSWORD_REQUIRED / MFA_SETUP /
    SOFTWARE_TOKEN_MFA. `challenge_responses` carries the challenge-specific
    keys (e.g. ``NEW_PASSWORD``, ``SOFTWARE_TOKEN_MFA_CODE``); SECRET_HASH is
    always injected here so callers never have to remember it."""
    return _client().admin_respond_to_auth_challenge(
        UserPoolId=settings.COGNITO_USER_POOL_ID,
        ClientId=settings.COGNITO_CLIENT_ID,
        ChallengeName=challenge_name,
        Session=session,
        ChallengeResponses={
            "USERNAME": email,
            "SECRET_HASH": compute_secret_hash(email),
            **challenge_responses,
        },
    )


def refresh_auth(refresh_token: str, canonical_username: str) -> dict[str, Any]:
    """``AdminInitiateAuth`` with ``REFRESH_TOKEN_AUTH``. Returns
    ``{"AuthenticationResult": {"AccessToken": ..., "IdToken": ..., ...}}``
    (no new refresh token is issued unless refresh-token rotation is
    enabled on the app client).

    ``canonical_username`` MUST be the pool's own ``Username``, which for this
    pool is a Cognito-generated UUID equal to the ``sub`` claim — **not** the
    email address. Pass ``users.cognito_sub``.

    Why this differs from :func:`admin_initiate_auth`, which is happily given an
    email: the pool is configured with ``username_attributes = ["email"]``, so
    email is a sign-in *alias*. On the initial login Cognito verifies
    ``SECRET_HASH`` against whatever you supplied as ``USERNAME``, so the alias
    works. On the refresh flow there is no ``USERNAME`` parameter — Cognito
    verifies the hash against the canonical username the refresh token was
    issued to. Passing the email there fails with a distinctly unhelpful
    ``NotAuthorizedException: Unable to verify secret hash for client``.

    Found by running the real flow against a live pool; a mocked boto3 client
    cannot surface it, which is why the offline test suite stayed green.
    """
    return _client().admin_initiate_auth(
        UserPoolId=settings.COGNITO_USER_POOL_ID,
        ClientId=settings.COGNITO_CLIENT_ID,
        AuthFlow="REFRESH_TOKEN_AUTH",
        AuthParameters={
            "REFRESH_TOKEN": refresh_token,
            "SECRET_HASH": compute_secret_hash(canonical_username),
        },
    )


def revoke_token(refresh_token: str) -> None:
    """``RevokeToken`` — invalidates the refresh token (and any access token
    minted from it, once it expires) at Cognito. Access tokens already
    issued remain offline-valid until their own `exp` per AWS's documented
    caveat (migration plan R3) -- the app's own `revoked_tokens` per-jti
    denylist is what closes that gap for the local/legacy path; there is no
    per-access-token revocation API on the Cognito side."""
    _client().revoke_token(
        Token=refresh_token,
        ClientId=settings.COGNITO_CLIENT_ID,
        ClientSecret=settings.COGNITO_CLIENT_SECRET,
    )


def change_password(access_token: str, previous_password: str, proposed_password: str) -> None:
    """``ChangePassword`` (non-admin) -- requires the *caller's own* Cognito
    access token, unlike every other wrapper in this module which uses the
    Admin* surface. The backend has the token because it just validated the
    request via the shared resolver, so it can make this call on the user's
    behalf without ever needing the user's password again."""
    _client().change_password(
        PreviousPassword=previous_password,
        ProposedPassword=proposed_password,
        AccessToken=access_token,
    )


def admin_create_user(email: str, temporary_password: str | None = None) -> dict[str, Any]:
    """``AdminCreateUser``. `temporary_password` omitted -> Cognito generates
    one and (if email delivery is configured) sends the invite; the caller
    then typically calls ``admin_set_user_password`` with a known temp
    password for deterministic bootstrap/test flows."""
    kwargs: dict[str, Any] = {
        "UserPoolId": settings.COGNITO_USER_POOL_ID,
        "Username": email,
        "UserAttributes": [
            {"Name": "email", "Value": email},
            {"Name": "email_verified", "Value": "true"},
        ],
    }
    if temporary_password:
        kwargs["TemporaryPassword"] = temporary_password
    return _client().admin_create_user(**kwargs)


def admin_set_user_password(email: str, password: str, permanent: bool = True) -> None:
    """``AdminSetUserPassword``. ``permanent=True`` skips the
    NEW_PASSWORD_REQUIRED challenge on next login (used by bootstrap/seed
    flows that want a deterministic, immediately-usable password)."""
    _client().admin_set_user_password(
        UserPoolId=settings.COGNITO_USER_POOL_ID,
        Username=email,
        Password=password,
        Permanent=permanent,
    )


def admin_get_user(email: str) -> dict[str, Any]:
    """``AdminGetUser`` — raises ``UserNotFoundException`` if absent. Used by
    reconciliation/seed tooling that needs to read an existing pool user's
    ``sub`` back rather than assuming a create just happened."""
    return _client().admin_get_user(
        UserPoolId=settings.COGNITO_USER_POOL_ID,
        Username=email,
    )


def admin_get_user_sub(email: str) -> str:
    """Return an existing pool user's ``sub`` claim value."""
    return next(
        attr["Value"]
        for attr in admin_get_user(email)["UserAttributes"]
        if attr["Name"] == "sub"
    )


def admin_delete_user(email: str) -> None:
    """``AdminDeleteUser``. Callers should tolerate ``UserNotFoundException``
    (the pool user may already be absent) -- see api/admin.py."""
    _client().admin_delete_user(
        UserPoolId=settings.COGNITO_USER_POOL_ID,
        Username=email,
    )


def admin_user_global_sign_out(email: str) -> None:
    """``AdminUserGlobalSignOut`` -- revokes every refresh token issued to
    this user. Combined with ``tokens_valid_from`` (0031), this is what makes
    a role/tier change take effect on the user's very next request rather
    than waiting out the access-token TTL."""
    _client().admin_user_global_sign_out(
        UserPoolId=settings.COGNITO_USER_POOL_ID,
        Username=email,
    )


def admin_add_user_to_group(email: str, group_name: str) -> None:
    _client().admin_add_user_to_group(
        UserPoolId=settings.COGNITO_USER_POOL_ID,
        Username=email,
        GroupName=group_name,
    )


def admin_remove_user_from_group(email: str, group_name: str) -> None:
    _client().admin_remove_user_from_group(
        UserPoolId=settings.COGNITO_USER_POOL_ID,
        Username=email,
        GroupName=group_name,
    )


# Cognito's own factor identifiers, as they appear in ``UserMFASettingList``
# and as challenge names. Named constants because they are used in three
# separate places (status reads, the admin gate, challenge mapping) and a typo
# in any of them fails silently as "not enrolled".
TOTP_FACTOR = "SOFTWARE_TOKEN_MFA"
EMAIL_FACTOR = "EMAIL_OTP"


def get_confirmed_mfa_factors(email: str) -> list[str]:
    """The user's CONFIRMED MFA factors, from ``AdminGetUser``.

    ``UserMFASettingList`` contains only confirmed/active factors: a user who
    called ``AssociateSoftwareToken`` but never completed
    ``VerifySoftwareToken`` does NOT appear. That is exactly the semantics the
    admin gate wants -- a half-finished enrolment must not satisfy it.

    Note the AWS quirk: the list stays empty until ``SetUserMFAPreference`` has
    been called at least once, even when a factor is otherwise configured. Both
    enrolment paths in this codebase always set a preference, so an enrolled
    user is never invisible here.
    """
    return list(admin_get_user(email).get("UserMFASettingList", []) or [])


def has_confirmed_totp(email: str) -> bool:
    """True when this user has a CONFIRMED software-token (TOTP) MFA device."""
    return TOTP_FACTOR in get_confirmed_mfa_factors(email)


def has_confirmed_email_mfa(email: str) -> bool:
    """True when this user has email OTP active as a second factor."""
    return EMAIL_FACTOR in get_confirmed_mfa_factors(email)


def has_any_confirmed_mfa(email: str) -> bool:
    """True when the user holds ANY confirmed second factor.

    Backs the admin-MFA gate (migration plan §5.5). Deliberately factor-agnostic:
    the gate's question is "did this admin complete a second factor", not "did
    they choose the one the deployment happens to prefer". An admin with TOTP
    should not be blocked because the environment later standardised on email
    OTP, and vice versa.
    """
    factors = get_confirmed_mfa_factors(email)
    return any(factor in factors for factor in (TOTP_FACTOR, EMAIL_FACTOR))


def associate_software_token(access_token: str) -> str:
    """Begin TOTP enrolment. Returns the shared secret to render as a QR code.

    Non-admin API keyed on the caller's own access token, so a user can only
    ever enrol their OWN device.
    """
    resp = _client().associate_software_token(AccessToken=access_token)
    return resp["SecretCode"]


def verify_software_token(access_token: str, user_code: str, device_name: str | None = None) -> str:
    """Complete TOTP enrolment by proving possession of the secret.

    Returns Cognito's status string (``SUCCESS`` / ``ERROR``). Raises
    ``ClientError`` with ``EnableSoftwareTokenMFAException`` /
    ``CodeMismatchException`` on a wrong code.
    """
    kwargs: dict[str, Any] = {"AccessToken": access_token, "UserCode": user_code}
    if device_name:
        kwargs["FriendlyDeviceName"] = device_name
    return _client().verify_software_token(**kwargs)["Status"]


def apply_mfa_preference(
    access_token: str,
    email: str,
    *,
    totp_enabled: bool | None = None,
    email_enabled: bool | None = None,
) -> list[str]:
    """Set the user's MFA factor state, preserving any factor not named.

    ``None`` means "leave this factor as it is"; it is resolved from the user's
    CURRENT confirmed factors and then sent explicitly, rather than omitted from
    the request. That distinction is deliberate: AWS does not document whether an
    omitted settings block preserves or clears the corresponding factor, and
    guessing wrong would silently strip a user's TOTP device the first time they
    enable email OTP. Reading current state costs one ``AdminGetUser`` on a
    settings-page write -- never on a request path -- which is a cheap price for
    not having to rely on undocumented behaviour.

    Returns the resulting factor list so callers can report and audit the real
    post-write state instead of assuming the write did what was asked.

    Two Cognito protocol rules are enforced here so no caller has to remember
    them:

    * **Only one factor may be preferred.** If several are active and none is
      preferred, Cognito issues a ``SELECT_MFA_TYPE`` challenge at sign-in
      instead of going straight to a code prompt. We always name a preference so
      that extra round trip does not appear. Preference goes to the factor being
      turned on in THIS call; failing that, to email when it is active, else
      TOTP.
    * **TOTP cannot be enabled without a registered software token.** Doing so
      fails with ``InvalidParameterException: User does not have delivery config
      set to turn on SOFTWARE_TOKEN_MFA``. Callers enabling TOTP must have just
      completed ``verify_software_token``; a ``None`` here can only ever preserve
      an already-confirmed token, so it is safe.
    """
    current = get_confirmed_mfa_factors(email)

    resolved_totp = (TOTP_FACTOR in current) if totp_enabled is None else totp_enabled
    resolved_email = (EMAIL_FACTOR in current) if email_enabled is None else email_enabled

    if email_enabled:
        preferred = EMAIL_FACTOR
    elif totp_enabled:
        preferred = TOTP_FACTOR
    elif resolved_email:
        preferred = EMAIL_FACTOR
    elif resolved_totp:
        preferred = TOTP_FACTOR
    else:
        preferred = ""

    _client().set_user_mfa_preference(
        AccessToken=access_token,
        SoftwareTokenMfaSettings={
            "Enabled": resolved_totp,
            "PreferredMfa": preferred == TOTP_FACTOR,
        },
        EmailMfaSettings={
            "Enabled": resolved_email,
            "PreferredMfa": preferred == EMAIL_FACTOR,
        },
    )

    factors = []
    if resolved_totp:
        factors.append(TOTP_FACTOR)
    if resolved_email:
        factors.append(EMAIL_FACTOR)
    return factors


def forgot_password(email: str) -> None:
    """``ForgotPassword`` -- emails a reset code. Requires SES-backed delivery
    for any real volume (Cognito's default sender is heavily rate limited).
    SECRET_HASH is required because the app client is confidential."""
    _client().forgot_password(
        ClientId=settings.COGNITO_CLIENT_ID,
        Username=email,
        SecretHash=compute_secret_hash(email),
    )


def confirm_forgot_password(email: str, code: str, new_password: str) -> None:
    """``ConfirmForgotPassword`` -- completes the reset with the emailed code."""
    _client().confirm_forgot_password(
        ClientId=settings.COGNITO_CLIENT_ID,
        Username=email,
        ConfirmationCode=code,
        Password=new_password,
        SecretHash=compute_secret_hash(email),
    )


def list_pool_users() -> list[dict[str, Any]]:
    """``ListUsers`` across every page. Returns the raw boto3 user dicts.

    Reconciliation/reporting only (``scripts/verify_cognito_cutover.py``) --
    never on a request path. Paginated because a pool with more users than one
    page would otherwise silently under-report, which for a reconciliation
    check is worse than failing.
    """
    client = _client()
    paginator = client.get_paginator("list_users")
    users: list[dict[str, Any]] = []
    for page in paginator.paginate(UserPoolId=settings.COGNITO_USER_POOL_ID):
        users.extend(page.get("Users", []))
    return users


def admin_list_groups_for_user(email: str) -> list[str]:
    """Returns the group NAMES the user currently belongs to. Not called on
    the per-request read path (migration plan §5.2 -- reading
    `cognito:groups` off the verified token is the only per-request path);
    this exists for admin-surface reconciliation/reporting only."""
    resp = _client().admin_list_groups_for_user(
        UserPoolId=settings.COGNITO_USER_POOL_ID,
        Username=email,
    )
    return [g["GroupName"] for g in resp.get("Groups", [])]
