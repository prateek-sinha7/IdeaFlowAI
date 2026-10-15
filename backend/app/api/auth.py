"""Authentication API endpoints for login and user info.

Cognito is the sole authentication authority (Cognito-only auth migration,
``.kiro/specs/login/prompt.md`` Phase 1). ``login`` calls
``AdminInitiateAuth`` and handles the NEW_PASSWORD_REQUIRED /
SOFTWARE_TOKEN_MFA / EMAIL_OTP / SELECT_MFA_TYPE challenges via the
``/login/challenge`` endpoint. There is no local bcrypt/HS256 path.
``AuthResponse`` shape is UNCHANGED for the happy path -- frontend
``getToken()`` call sites need no edits.

MFA surface
-----------
Two factors, with deliberately different shapes because Cognito's are different:

* **TOTP** needs a secret provisioned, so enrolment is a two-step ceremony:
  ``/mfa/totp/associate`` (returns an ``otpauth://`` URI to render as a QR) then
  ``/mfa/totp/verify`` (proves possession).
* **Email OTP** needs nothing provisioned -- the mailbox is already the pool's
  sign-in identifier and is auto-verified -- so enrolment is a single toggle:
  ``/mfa/email/enable`` / ``/mfa/email/disable``.

``GET /mfa`` reports current state for both. Enabling email OTP requires the pool
to carry ``email_mfa_configuration``, signalled by ``AUTH_EMAIL_MFA_ENABLED``;
that same flag makes ``/forgot-password`` report that self-service reset is
unavailable, because AWS disqualifies email for account recovery whenever it is
an MFA factor (see ``infra/terraform/modules/cognito``).
"""

import json
import logging
from datetime import datetime, timezone

from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import auth_events, cognito
from app.core.auth_events import AuthEvent
from app.core.config import settings
from app.core.email_identity import canonicalize_email
from app.core.crypto import decrypt_cognito_refresh_token, encrypt_cognito_refresh_token
from app.core.dependencies import (
    bearer_scheme,
    get_current_user_for_refresh,
    get_current_user_with_payload,
    get_user_for_logout,
)
from app.core.identity import Principal, effective_is_admin, effective_tier
from app.core.provisioning import (
    STATUS_DISABLED,
    ProvisioningRefused,
    provision_from_login,
    refresh_projection,
)
from app.models.database import get_db
from app.models.revoked_token import RevokedToken
from app.models.schemas import (
    AuthChallengeResponse,
    AuthResponse,
    CanonicalEmail,
    LoginChallengeRequest,
    LoginRequest,
    MfaStatusResponse,
    RefreshResponse,
    UserResponse,
)
from app.models.user import User

router = APIRouter(prefix="/api/auth", tags=["auth"])
logger = logging.getLogger("app.api.auth")


def _principal_from_payload(user: User, payload: dict) -> Principal:
    """Rebuild the Principal from a dependency's projected payload.

    Needed wherever a route has to ask an authorization question that depends
    on the EFFECTIVE role (``cognito:groups``) rather than the advisory DB
    column -- see core/identity.py's precedence rule. ``user`` is accepted
    (and otherwise unused) to keep this helper's signature stable for
    existing callers.
    """
    del user
    return Principal(
        provider="cognito",
        sub=payload.get("sub", ""),
        jti=payload.get("jti"),
        iat=payload.get("iat"),
        groups=payload.get("groups", []),
    )


def _identity_from_minted_token(access_token: str) -> tuple[str, list[str], int | None]:
    """Read ``sub`` + ``cognito:groups`` + ``iat`` off a token Cognito JUST issued.

    Uses the UNVERIFIED claims, deliberately. This token did not come from a
    client: it is the body of the ``AdminInitiateAuth`` /
    ``AdminRespondToAuthChallenge`` response we received over TLS from the AWS
    endpoint moments ago, so its provenance is the same thing a signature check
    would be establishing. Re-verifying it here would only re-derive a fact
    already known.

    ``sub`` is required rather than defaulted, because Phase 2 promoted it from
    "a claim used to seed a display projection" to "the identity a local row is
    created against" (Decision 4a). The previous code swallowed ANY decode
    failure into ``groups = []``, which on the projection-refresh path silently
    rewrote the caller's tier down to ``basic`` -- a latent bug that a
    provisioning path would have upgraded into creating a row under the wrong
    identity. A token we minted that we cannot read is a broken invariant, so it
    raises and the caller returns 503.

    Raises ``ValueError`` when the token cannot be decoded or carries no ``sub``.
    """
    from jose import jwt as _jwt

    try:
        claims = _jwt.get_unverified_claims(access_token)
    except Exception as exc:  # noqa: BLE001 - any malformed-token failure
        raise ValueError(f"could not decode the access token Cognito issued: {exc}")

    sub = claims.get("sub")
    if not sub:
        raise ValueError("the access token Cognito issued carries no sub claim")

    raw_iat = claims.get("iat")
    iat = int(raw_iat) if raw_iat is not None else None

    return sub, list(claims.get("cognito:groups", []) or []), iat


def _cognito_auth_result_to_response(
    email: str, auth_result: dict, db: Session, *, mfa_proved: bool = False
) -> AuthResponse:
    """Resolve-or-provision the local row, persist the refresh token, respond.

    Takes the submitted ``email`` rather than a ``User``, because Phase 2 of the
    Cognito-only auth migration removed the requirement that a local row exist
    BEFORE authentication (Decision 4a). A user created straight in the Cognito
    console now gets their row here, on their first successful sign-in, instead
    of being permanently unable to log in -- see ``core/provisioning.py``.

    ``mfa_proved`` stamps ``mfa_verified_at`` from the token's OWN ``iat``. Set it
    only when the caller just answered a real MFA challenge; see the extended
    note on the write below.

    The returned ``UserResponse`` carries the freshly-synced projection, which on
    this path is equal to the effective values by construction (it was just
    computed from the same token's groups).
    """
    access_token = auth_result["AccessToken"]

    try:
        sub, groups, token_iat = _identity_from_minted_token(access_token)
    except ValueError as exc:
        logger.error("Cognito returned an unreadable access token: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service unavailable",
        )

    try:
        user = provision_from_login(db, email=email, sub=sub, groups=groups)
    except ProvisioningRefused:
        # Fail closed and say nothing specific: the only way to reach this is an
        # email already mapped to a DIFFERENT Cognito identity, which is pool
        # state an unauthenticated caller must not be able to probe.
        auth_events.emit(
            AuthEvent.LOGIN_FAILURE,
            email=email,
            provider="cognito",
            reason="identity_mapping_conflict",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    if auth_result.get("RefreshToken"):
        user.encrypted_cognito_refresh_token = encrypt_cognito_refresh_token(
            auth_result["RefreshToken"]
        )

    if mfa_proved and token_iat is not None:
        # Stamped from the TOKEN's `iat`, not `datetime.now()`.
        #
        # core.identity.enforce_admin_mfa asks `principal.iat >=
        # mfa_verified_at`, so the stamp must not land after the instant the
        # token it is vouching for was minted. Using wall-clock `now()` (as this
        # did before Phase 2) means the stamp is always a few milliseconds LATER
        # than the token, and the comparison only passed because both sides get
        # truncated to whole seconds -- so an admin whose challenge happened to
        # straddle a second boundary was handed a token that instantly failed
        # its own MFA gate, with the only remedy being to log in again and hope
        # for better timing. Phase 2 made that race materially likelier by
        # moving provisioning (a DB insert + commit) in between, so the honest
        # fix is to stop racing: `iat` IS the instant the second factor was
        # proven, and it is what the gate compares against.
        user.mfa_verified_at = datetime.fromtimestamp(token_iat, tz=timezone.utc)

    refresh_projection(user, groups, db)

    return AuthResponse(
        token=access_token,
        user=UserResponse(
            id=user.id,
            email=user.email,
            tier=user.tier,
            is_admin=user.is_admin,
        ),
    )


def _challenge_response(resp: dict) -> AuthChallengeResponse:
    """Project a boto3 challenge response into our wire shape.

    Pulls two things out of ``ChallengeParameters`` that the client genuinely
    needs and cannot derive:

    * ``CODE_DELIVERY_DESTINATION`` -- where Cognito just sent the code, already
      masked by AWS. For EMAIL_OTP a prompt that cannot say which mailbox to
      check is a real support burden when the address on file is not the one the
      user expected.
    * ``MFAS_CAN_CHOOSE`` -- the selectable factors on a SELECT_MFA_TYPE
      challenge, so a client can render an actual choice.

    Both are absent on challenges that do not produce them, hence the ``None``
    defaults rather than empty strings.
    """
    params = resp.get("ChallengeParameters", {}) or {}

    available: list[str] | None = None
    raw_options = params.get("MFAS_CAN_CHOOSE")
    if raw_options:
        # Cognito serialises this as a JSON array inside a string value.
        try:
            parsed = json.loads(raw_options)
            if isinstance(parsed, list):
                available = [str(item) for item in parsed]
        except (ValueError, TypeError):
            logger.warning("Could not parse MFAS_CAN_CHOOSE: %r", raw_options)

    return AuthChallengeResponse(
        challenge=resp["ChallengeName"],
        session=resp["Session"],
        delivery=params.get("CODE_DELIVERY_DESTINATION"),
        available_factors=available,
    )


# --- Audit `reason` values for a login attempt with no local row -------------
#
# These are ``reason`` strings on LOGIN_FAILURE rather than new AuthEvent
# members, deliberately: core/auth_events.py documents the AuthEvent values as
# a PUBLISHED INTERFACE that infra/terraform/modules/monitoring builds metric
# filters against, and warns that adding/renaming one without a matching
# Terraform change leaves an alarm reporting no-data (which looks healthy). A
# new `reason` needs no infrastructure change and is just as greppable in
# CloudWatch Logs Insights ({ $.reason = "orphaned_pool_user" }).

#: No such account in EITHER store — an ordinary typo or a credential-stuffing
#: probe. The pre-existing value; unchanged so existing queries keep working.
_REASON_UNKNOWN_USER = "unknown_user"

# Two sibling reasons (``orphaned_pool_user``, ``unknown_user_provider_unavailable``)
# and the two helpers that produced them (``_classify_pool_presence``,
# ``_probe_unknown_email``) were REMOVED in Phase 2 of the Cognito-only auth
# migration. Both existed to serve a state that can no longer occur:
#
#   * ``orphaned_pool_user`` described an account present in the pool with no
#     local row — permanently unable to log in. Decision 4a provisions that row
#     on first successful sign-in (``core/provisioning.py``), so the condition
#     is now healed automatically instead of being classified and reported.
#   * ``_probe_unknown_email`` burned a deliberately-doomed ``AdminInitiateAuth``
#     against a random password so that an unknown email cost the same as a known
#     one, closing a ~100x timing oracle. ``/login`` no longer short-circuits on a
#     missing local row at all — every attempt now makes the SAME real
#     ``AdminInitiateAuth`` call with the SAME submitted password — so the
#     latency envelope is uniform BY CONSTRUCTION rather than by paying for a
#     decoy round-trip. That is a strictly stronger position than the probe
#     achieved: there is no longer a branch to balance.
#
# If a CloudWatch Logs Insights query or metric filter references either
# removed reason, it will report no-data (which looks healthy) — see the
# published-interface warning in core/auth_events.py.


@router.post("/login", response_model=AuthResponse | AuthChallengeResponse)
def login(request: LoginRequest, db: Session = Depends(get_db)):
    """Authenticate a user and return a bearer token.

    Cognito is the sole authentication authority: ``AdminInitiateAuth``
    (``ADMIN_USER_PASSWORD_AUTH``). On success returns the normal
    ``AuthResponse``. If Cognito responds with a challenge
    (NEW_PASSWORD_REQUIRED / MFA_SETUP / SOFTWARE_TOKEN_MFA) returns an
    ``AuthChallengeResponse`` instead; the client completes it via
    ``POST /api/auth/login/challenge``.

    Returns a generic 401 on failure — does not distinguish between
    wrong email and wrong password (also true of a Cognito
    NotAuthorizedException, which maps to the same 401).

    **A local ``users`` row is NOT a precondition** (Cognito-only auth
    migration, Decision 4a). This endpoint used to load the local row FIRST and
    return 401 when it was absent, which made an account created directly in the
    Cognito console permanently unable to sign in no matter how correct its
    credentials were. Authentication is now attempted against Cognito
    unconditionally, and the local row is created from the resulting token on
    success (``core/provisioning.py`` via
    :func:`_cognito_auth_result_to_response`).

    That change also SUBSUMES the P2 timing fix (COGNITO-AUTH-QA-BUGS.md "Login
    Timing Enumeration") rather than discarding it. The oracle it closed came
    from an unknown email returning in ~ms off a bare indexed DB miss while a
    known one paid a full Cognito round-trip (~hundreds of ms) — a ~100x gap.
    The old remedy was to burn an equivalent decoy ``AdminInitiateAuth`` on the
    miss branch. There is now no miss branch to balance: every attempt, known
    email or not, makes the same real ``AdminInitiateAuth`` call with the
    submitted password and returns the same generic 401 on rejection. Uniform by
    construction beats uniform by compensation — nothing has to be kept in sync
    for it to stay true.

    The local lookup is retained purely so the audit trail can carry
    ``user_id`` for a known account instead of only a hashed email; it is not a
    gate, and its outcome does not change control flow.
    """
    # NOT a gate — see the docstring. Used only to enrich the audit events below
    # with a user_id when one already exists. A miss is the ordinary first-login
    # case for a console-created account, not a failure.
    user = db.query(User).filter(func.lower(User.email) == request.email).first()
    # Email is passed on the no-row branch precisely BECAUSE no user_id exists —
    # without it a credential-stuffing run against never-provisioned addresses
    # would be invisible in the audit trail. (auth_events hashes it; the
    # plaintext never reaches the log line.)
    audit_identity: dict[str, str | None] = (
        {"user_id": user.id} if user else {"email": request.email}
    )

    try:
        resp = cognito.admin_initiate_auth(request.email, request.password)
    except cognito.PROVIDER_ERRORS as exc:
        code = cognito.provider_error_code(exc)
        if code in ("NotAuthorizedException", "UserNotFoundException"):
            auth_events.emit(
                AuthEvent.LOGIN_FAILURE,
                provider="cognito",
                reason="not_authorized" if user else _REASON_UNKNOWN_USER,
                provider_error_code=code,
                **audit_identity,
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
            )
        logger.error("Cognito AdminInitiateAuth failed: %s", code)
        auth_events.emit(
            AuthEvent.LOGIN_FAILURE,
            provider="cognito",
            reason=f"provider_error:{code}",
            **audit_identity,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service unavailable",
        )

    if "ChallengeName" in resp:
        auth_events.emit(
            AuthEvent.LOGIN_CHALLENGE,
            provider="cognito",
            challenge=resp["ChallengeName"],
            **audit_identity,
        )
        return _challenge_response(resp)

    # Provisioning happens inside here, so LOGIN_SUCCESS is emitted AFTER it
    # rather than before: on a first sign-in there is no user_id to log until
    # the row exists, and an event claiming success for an identity that then
    # failed to provision would be worse than a slightly later one.
    response = _cognito_auth_result_to_response(
        request.email, resp["AuthenticationResult"], db
    )
    auth_events.emit(
        AuthEvent.LOGIN_SUCCESS, user_id=response.user.id, provider="cognito"
    )
    return response


#: Maps a challenge name to the ``ChallengeResponses`` key carrying its one-time
#: code. All three are a 6-digit code from the user's point of view; only the key
#: Cognito expects differs, so the request schema uses a single ``mfa_code``
#: field and this table does the translation.
_CODE_RESPONSE_KEY = {
    "SOFTWARE_TOKEN_MFA": "SOFTWARE_TOKEN_MFA_CODE",
    "EMAIL_OTP": "EMAIL_OTP_CODE",
}

#: Valid answers to a SELECT_MFA_TYPE challenge. Note the asymmetry, which is a
#: genuine Cognito quirk and not a typo here: the factor is called ``EMAIL_OTP``
#: everywhere else (challenge name, UserMFASettingList) but the SELECT_MFA_TYPE
#: answer for it is ``EMAIL_MFA``.
_SELECTABLE_FACTORS = ("EMAIL_MFA", "SOFTWARE_TOKEN_MFA")


@router.post("/login/challenge", response_model=AuthResponse | AuthChallengeResponse)
def login_challenge(request: LoginChallengeRequest, db: Session = Depends(get_db)):
    """Complete a Cognito auth challenge started by ``POST /api/auth/login``.

    Handles NEW_PASSWORD_REQUIRED (first login with an admin-set temp password),
    SOFTWARE_TOKEN_MFA and EMAIL_OTP (an enrolled user signing in), and
    SELECT_MFA_TYPE (a user with several active factors and no preference).

    ``response_model`` is the union because a challenge response can itself
    produce another challenge -- NEW_PASSWORD_REQUIRED followed by an MFA prompt
    is the ordinary first-login sequence for a user whose role requires a factor.
    Declaring only ``AuthResponse`` here made FastAPI's response validation
    reject that chained case.

    MFA_SETUP is deliberately NOT handled. Completing it requires a three-call
    session chain (AssociateSoftwareToken -> VerifySoftwareToken ->
    RespondToAuthChallenge, each consuming the previous call's session) that this
    endpoint's single-shot shape cannot express. Cognito only issues MFA_SETUP
    when the pool REQUIRES MFA and the user holds no factor, which cannot happen
    while ``mfa_configuration`` is OPTIONAL. Rather than send a response Cognito
    will reject, this returns an actionable error -- see the guard below.
    """
    # As on /login, a missing local row is NOT a rejection any more (Decision
    # 4a) — and it matters MORE here than there. NEW_PASSWORD_REQUIRED is the
    # first step of the invitation flow every admin-created and every
    # console-created account starts in, so "no local row yet" is the NORMAL
    # state for this endpoint's most common challenge, not an anomaly. Rejecting
    # it made the invitation flow unusable for exactly the users JIT
    # provisioning exists to serve. The row is created from the resulting token
    # by _cognito_auth_result_to_response once the challenge succeeds.
    #
    # Still not an enumeration oracle: reaching Cognito at all additionally
    # requires a valid provider-issued `session`, which only /login can mint.
    user = db.query(User).filter(func.lower(User.email) == request.email).first()
    audit_identity: dict[str, str | None] = (
        {"user_id": user.id} if user else {"email": request.email}
    )
    challenge_responses: dict[str, str] = {}
    if request.challenge == "NEW_PASSWORD_REQUIRED":
        if not request.new_password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="new_password is required for the NEW_PASSWORD_REQUIRED challenge",
            )
        challenge_responses["NEW_PASSWORD"] = request.new_password
    elif request.challenge in _CODE_RESPONSE_KEY:
        if not request.mfa_code:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"mfa_code is required for the {request.challenge} challenge",
            )
        challenge_responses[_CODE_RESPONSE_KEY[request.challenge]] = request.mfa_code
    elif request.challenge == "SELECT_MFA_TYPE":
        if request.selected_factor not in _SELECTABLE_FACTORS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "selected_factor is required for the SELECT_MFA_TYPE challenge "
                    f"and must be one of: {', '.join(_SELECTABLE_FACTORS)}"
                ),
            )
        challenge_responses["ANSWER"] = request.selected_factor
    elif request.challenge == "MFA_SETUP":
        # Reachable only if the pool is switched to mfa_configuration = "ON"
        # while users hold no factor. MFA_SETUP requires a three-call session
        # chain (AssociateSoftwareToken -> VerifySoftwareToken ->
        # RespondToAuthChallenge) that this endpoint cannot express. Direct the
        # user to the enrollment endpoints instead.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "mfa_enrollment_required",
                "enroll_path": "/api/auth/mfa/totp/associate",
            },
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported challenge: {request.challenge}",
        )

    try:
        resp = cognito.admin_respond_to_auth_challenge(
            request.email, request.challenge, request.session, challenge_responses
        )
    except cognito.PROVIDER_ERRORS as exc:
        code = cognito.provider_error_code(exc)
        if code in (
            "NotAuthorizedException",
            "CodeMismatchException",
            "ExpiredCodeException",
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
            )
        if code == "InvalidPasswordException":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="New password does not meet the password policy.",
            )
        logger.error("Cognito AdminRespondToAuthChallenge failed: %s", code)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service unavailable",
        )

    if "ChallengeName" in resp:
        # A second challenge (e.g. NEW_PASSWORD_REQUIRED then EMAIL_OTP) --
        # surface it the same way /login does rather than special-casing.
        auth_events.emit(
            AuthEvent.LOGIN_CHALLENGE,
            provider="cognito",
            challenge=resp["ChallengeName"],
            **audit_identity,
        )
        return _challenge_response(resp)

    # The challenge succeeded, so a token exists and the row can be provisioned
    # (or resolved) from it. On the invitation flow THIS is the request that
    # first creates the row, so there is no `user` object to write to until now
    # -- which is why the mfa_verified_at stamp moved inside, where the row and
    # the token's claims are both in hand.
    #
    # P0 fix (COGNITO-AUTH-QA-BUGS.md "Admin MFA is Off by Default and
    # Bypassable"): the stamp is applied ONLY when the challenge just completed
    # was an actual MFA proof (SOFTWARE_TOKEN_MFA / EMAIL_OTP), never
    # NEW_PASSWORD_REQUIRED or a SELECT_MFA_TYPE selection step. It is the
    # session-bound proof core.identity.enforce_admin_mfa compares a bearer's
    # `iat` against, and it is never stamped by the enrolment endpoints
    # (mfa/totp/verify, mfa/email/enable) -- so enrolling a factor alone, with
    # no reauthentication, does not satisfy the admin gate.
    response = _cognito_auth_result_to_response(
        request.email,
        resp["AuthenticationResult"],
        db,
        mfa_proved=request.challenge in _CODE_RESPONSE_KEY,
    )

    auth_events.emit(
        AuthEvent.LOGIN_SUCCESS, user_id=response.user.id, provider="cognito"
    )
    return response


def _reconcile_status_on_refresh_rejection(user: User, db: Session) -> None:
    """Mark a row disabled ONLY when Cognito confirms the account is gone/off.

    A refresh rejection is deliberately NOT treated as proof of anything. AWS
    returns ``NotAuthorizedException`` for a whole family of causes that have
    nothing to do with the account's standing: the refresh token was revoked by
    an ordinary logout, it aged past the app client's refresh-token validity
    window, an ``AdminUserGlobalSignOut`` was issued for a routine tier change,
    or the stored ciphertext is simply stale. Flipping ``status`` to
    ``disabled`` on that signal would let any of those normal events lock a user
    out of the application permanently -- ``resolve_principal`` rejects a
    non-active row outright, so it would not even be recoverable by logging in
    again.

    So the mutation requires a second, authoritative answer:
    ``AdminGetUser`` -- a read API, outside the scope of
    ``prevent_user_existence_errors`` -- must report the pool user as absent
    (``UserNotFoundException``) or explicitly ``Enabled=false``. Anything else,
    including Cognito being unreachable, leaves the row untouched and the caller
    gets the same 401 either way. The asymmetry is the point: a 401 costs the
    user one sign-in, a wrongly-persisted ``disabled`` costs them their account
    until an operator intervenes.

    Never raises. Reconciliation is a side effect of an already-decided 401.
    """
    try:
        result = cognito.admin_get_user(user.cognito_sub)
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code != "UserNotFoundException":
            logger.warning(
                "Could not confirm pool state for %s after a refresh rejection: %s",
                user.id,
                code,
            )
            return
        confirmed_reason = "missing_at_provider"
    except Exception as exc:  # noqa: BLE001 - no creds / endpoint / DNS failure
        logger.warning(
            "Could not confirm pool state for %s after a refresh rejection: %s",
            user.id,
            exc,
        )
        return
    else:
        if result.get("Enabled", True):
            return
        confirmed_reason = "disabled_at_provider"

    try:
        user.status = STATUS_DISABLED
        db.commit()
    except Exception as exc:  # noqa: BLE001 - the 401 stands regardless
        logger.warning("Could not persist disabled status for %s: %s", user.id, exc)
        db.rollback()
        return

    auth_events.emit(
        AuthEvent.TOKEN_REFRESH_FAILURE,
        user_id=user.id,
        provider="cognito",
        reason=confirmed_reason,
    )


@router.post("/refresh", response_model=RefreshResponse)
def refresh(
    auth: tuple[User, dict] = Depends(get_current_user_for_refresh),
    db: Session = Depends(get_db),
):
    """Silently mint a fresh access token from the caller's stored Cognito
    refresh token (R4 in the migration plan's risk register: long-running
    workflows must not die on access-token expiry).

    P1 fix (COGNITO-AUTH-QA-BUGS.md "Token Refresh: Impossible After Access
    Token Expiry"): accepts a bearer up to ``AUTH_REFRESH_GRACE_SECONDS``
    PAST its own expiry (``get_current_user_for_refresh`` -- see
    ``core.identity.verify_credential(allow_expired=True)``), not only a
    currently-valid one. Previously this required an unexpired access token,
    which meant a REST-only client with no SSE stream attached (the only
    place the frontend's pre-expiry timer runs) had no way to recover once
    the token actually expired -- the 401-triggered refresh retried with the
    SAME expired bearer and failed identically. Every other check (signature,
    issuer, per-jti revocation, password/role-change blanket revocation)
    still applies in full; only the expiry clock is relaxed, and only within
    the bounded grace window.

    Response shape is exactly ``{"token": "..."}`` -- the contract
    ``frontend/src/hooks/useRunStream.ts::attemptSilentRefresh`` already
    parses, so no frontend change is required.
    """
    user, _payload = auth

    if not user.encrypted_cognito_refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No refresh token on file; please log in again.",
        )

    try:
        refresh_token = decrypt_cognito_refresh_token(
            user.encrypted_cognito_refresh_token
        )
    except Exception:  # noqa: BLE001 - InvalidToken or any decrypt failure
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Stored refresh token could not be decrypted; please log in again.",
        )

    # SECRET_HASH on the refresh flow must be computed with the pool's CANONICAL
    # username (a Cognito-generated UUID == the `sub` claim), not the email
    # alias — see core/cognito.py::refresh_auth. `cognito_sub` is exactly that
    # value. Fall back to email only for a row that predates sub mapping, where
    # the pool may genuinely be username=email.
    canonical_username = user.cognito_sub or user.email

    try:
        resp = cognito.refresh_auth(refresh_token, canonical_username)
    except cognito.PROVIDER_ERRORS as exc:
        code = cognito.provider_error_code(exc)
        if code in ("NotAuthorizedException", "UserNotFoundException"):
            _reconcile_status_on_refresh_rejection(user, db)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token is no longer valid; please log in again.",
            )
        logger.error("Cognito REFRESH_TOKEN_AUTH failed: %s", code)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service unavailable",
        )

    auth_result = resp["AuthenticationResult"]
    auth_events.emit(AuthEvent.TOKEN_REFRESH, user_id=user.id, provider="cognito")
    return RefreshResponse(token=auth_result["AccessToken"])


@router.get("/me", response_model=UserResponse)
def get_me(auth: tuple[User, dict] = Depends(get_current_user_with_payload)):
    """Return the current authenticated user's EFFECTIVE info.

    Serves tier/is_admin from the effective principal (cognito:groups on the
    Cognito path, the DB column on the local/break-glass path) -- never the
    raw DB column for a Cognito principal, per the precedence rule in
    core/identity.py.
    """
    user, payload = auth
    principal = _principal_from_payload(user, payload)
    return UserResponse(
        id=user.id,
        email=user.email,
        tier=effective_tier(user, principal),
        is_admin=effective_is_admin(user, principal),
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    auth: tuple[User, dict] = Depends(get_user_for_logout),
    db: Session = Depends(get_db),
):
    """Revoke the bearer credential used to make this request.

    Inserts a row in ``revoked_tokens`` keyed by the token's ``jti``. ALSO
    revokes the stored refresh token at Cognito (``RevokeToken``) so a
    stolen refresh token cannot mint further access tokens; the stored
    encrypted copy is cleared either way.

    Idempotent: hitting this endpoint with an already-revoked token still
    returns 204 — the client wanted to log out, the token is revoked,
    desired state is satisfied. Uses :func:`get_user_for_logout` (rather
    than the standard ``get_current_user``) precisely so an already-revoked
    token doesn't 401 on its own /logout call.
    """
    user, payload = auth
    jti = payload.get("jti")
    exp = payload.get("exp")

    if user.encrypted_cognito_refresh_token:
        try:
            refresh_token = decrypt_cognito_refresh_token(
                user.encrypted_cognito_refresh_token
            )
            cognito.revoke_token(refresh_token)
        except Exception:  # noqa: BLE001 - logout must succeed even if Cognito is unreachable
            logger.warning(
                "Cognito RevokeToken failed for user %s during logout", user.id
            )
        finally:
            user.encrypted_cognito_refresh_token = None
            db.commit()

    # Defence in depth: if the token somehow has no jti, there's nothing we
    # can revoke at the per-token level. The blanket-revoke on password/role
    # change still protects the user; treat this as a successful no-op.
    auth_events.emit(AuthEvent.LOGOUT, user_id=user.id, provider="cognito")

    if not jti or not exp:
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    # ``exp`` comes back as an int (seconds since epoch) from both providers.
    if isinstance(exp, (int, float)):
        expires_at = datetime.fromtimestamp(exp, tz=timezone.utc)
    elif isinstance(exp, datetime):
        expires_at = exp if exp.tzinfo else exp.replace(tzinfo=timezone.utc)
    else:
        # Unknown shape — bail out as a no-op rather than 500.
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    revocation = RevokedToken(
        jti=jti,
        user_id=user.id,
        expires_at=expires_at,
    )
    db.add(revocation)
    try:
        db.commit()
    except IntegrityError:
        # Already revoked — idempotent path. Roll back the failed insert and
        # report success: the caller's intent (this token must be revoked)
        # is satisfied.
        db.rollback()

    return Response(status_code=status.HTTP_204_NO_CONTENT)


class TotpVerifyRequest(BaseModel):
    """Request body for completing TOTP enrolment."""

    code: str
    device_name: str | None = None


@router.post("/mfa/totp/associate", status_code=status.HTTP_200_OK)
def associate_totp(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    auth: tuple[User, dict] = Depends(get_current_user_with_payload),
    db: Session = Depends(get_db),
):
    """Begin TOTP enrolment; returns the shared secret to render as a QR code.

    Phase 6 item 1 (plan §5.5). Cognito provides no enrolment UI without the
    hosted UI, so the application must supply this step -- which is why the pool
    can sit at ``mfa_configuration = OPTIONAL`` while admins are still required
    to hold a factor.

    The secret is returned ONCE and never stored server-side. Enrolment is not
    complete until ``POST /api/auth/mfa/totp/verify`` proves possession.
    """
    user, _payload = auth
    try:
        secret = cognito.associate_software_token(credentials.credentials)
    except cognito.PROVIDER_ERRORS as exc:
        code = cognito.provider_error_code(exc)
        logger.error("Cognito AssociateSoftwareToken failed: %s", code)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service unavailable",
        )
    return {
        "secret": secret,
        "issuer": "Flowin",
        "account": user.email,
        # Standard otpauth URI so the client can render a QR code directly
        # without reimplementing the format.
        "otpauth_uri": f"otpauth://totp/Flowin:{user.email}?secret={secret}&issuer=Flowin",
    }


@router.post("/mfa/totp/verify", status_code=status.HTTP_200_OK)
def verify_totp(
    request: TotpVerifyRequest,
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    auth: tuple[User, dict] = Depends(get_current_user_with_payload),
    db: Session = Depends(get_db),
):
    """Complete TOTP enrolment and mark the factor as the user's preference.

    Verification and preference are separate Cognito steps: verifying proves
    possession, but the factor is not actually used at sign-in until it is set
    preferred. Doing both here means a user who completes this flow is genuinely
    protected, rather than holding a verified-but-unused device.
    """
    user, _payload = auth
    try:
        result = cognito.verify_software_token(
            credentials.credentials, request.code, request.device_name
        )
        if result != "SUCCESS":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Could not verify that code. Try the current code from your app.",
            )
        # Preserves any email factor the user already has (email_enabled=None) --
        # enrolling a second device must not silently remove the first.
        cognito.apply_mfa_preference(
            credentials.credentials, user.email, totp_enabled=True
        )
    except cognito.PROVIDER_ERRORS as exc:
        code = cognito.provider_error_code(exc)
        if code in ("CodeMismatchException", "EnableSoftwareTokenMFAException"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Could not verify that code. Try the current code from your app.",
            )
        logger.error("Cognito VerifySoftwareToken failed: %s", code)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service unavailable",
        )
    auth_events.emit(
        AuthEvent.MFA_ENROLLED,
        user_id=user.id,
        provider="cognito",
        factor=cognito.TOTP_FACTOR,
    )
    return {"message": "Two-factor authentication enabled."}


# ---------------------------------------------------------------------------
# MFA status + email OTP enrolment
# ---------------------------------------------------------------------------
# Email OTP has no enrolment ceremony the way TOTP does: there is no secret to
# provision, so no AssociateSoftwareToken/VerifySoftwareToken pair. Possession of
# the mailbox is already established -- it is the pool's sign-in identifier
# (`username_attributes = ["email"]`), auto-verified, and the address the
# invitation was delivered to. Enabling the factor is therefore a single
# SetUserMFAPreference write, which is why these endpoints are a toggle rather
# than a multi-step flow.


@router.get("/mfa", response_model=MfaStatusResponse)
def get_mfa_status(
    auth: tuple[User, dict] = Depends(get_current_user_with_payload),
):
    """Report the caller's second-factor state and what this deployment offers.

    Returns 200 with ``supported=false`` for a non-Cognito (break-glass) account
    rather than an error: the security page still needs to render, and "this
    account type has no second factor" is a legitimate answer, not a failure.

    On a Cognito lookup failure this reports ``enabled=false`` with the factor
    list empty rather than 503. The consequence of being wrong here is a settings
    page that offers to enable a factor the user already has -- Cognito would
    reject or no-op that -- which is a far better outcome than a security page
    that cannot load at all.
    """
    user, payload = auth
    principal = _principal_from_payload(user, payload)

    try:
        factors = cognito.get_confirmed_mfa_factors(user.email)
    except Exception as exc:  # noqa: BLE001 - see docstring: degrade, don't 503
        logger.warning("Could not read MFA factors for %s: %s", user.id, exc)
        factors = []

    return MfaStatusResponse(
        enabled=bool(factors),
        factors=factors,
        email_available=settings.AUTH_EMAIL_MFA_ENABLED,
        totp_available=True,
        required=settings.ADMIN_MFA_REQUIRED and effective_is_admin(user, principal),
        supported=True,
    )


@router.post("/mfa/email/enable", status_code=status.HTTP_200_OK)
def enable_email_mfa(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    auth: tuple[User, dict] = Depends(get_current_user_with_payload),
):
    """Turn on email OTP as the caller's second factor.

    Guarded on ``AUTH_EMAIL_MFA_ENABLED`` because the factor only works when the
    POOL carries ``email_mfa_configuration`` (which in turn needs SES). Without
    that, Cognito rejects the write with an opaque parameter error; refusing here
    produces an explanation instead.

    Keyed on the caller's own access token, so a user can only ever change their
    OWN factors. Any existing TOTP device is preserved.
    """
    user, _payload = auth

    if not settings.AUTH_EMAIL_MFA_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Email two-factor authentication is not configured for this "
                "environment. Use an authenticator app instead."
            ),
        )

    try:
        factors = cognito.apply_mfa_preference(
            credentials.credentials, user.email, email_enabled=True
        )
    except cognito.PROVIDER_ERRORS as exc:
        code = cognito.provider_error_code(exc)
        logger.error("Cognito SetUserMFAPreference (email on) failed: %s", code)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service unavailable",
        )

    auth_events.emit(
        AuthEvent.MFA_ENROLLED,
        user_id=user.id,
        provider="cognito",
        factor=cognito.EMAIL_FACTOR,
    )
    return {
        "message": "Email two-factor authentication enabled.",
        "factors": factors,
    }


@router.post("/mfa/email/disable", status_code=status.HTTP_200_OK)
def disable_email_mfa(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    auth: tuple[User, dict] = Depends(get_current_user_with_payload),
):
    """Turn off email OTP for the caller.

    Refused when it would leave a user whose role REQUIRES a factor with none at
    all (admin + ``ADMIN_MFA_REQUIRED``, and no TOTP device to fall back on).
    Allowing it would let an admin lock themselves out of every ``/api/admin/*``
    route in one click, and the fix would then need another admin -- so this
    fails closed and explains what to do instead.
    """
    user, payload = auth
    principal = _principal_from_payload(user, payload)

    mfa_required = settings.ADMIN_MFA_REQUIRED and effective_is_admin(user, principal)
    if mfa_required:
        try:
            has_totp = cognito.has_confirmed_totp(user.email)
        except Exception as exc:  # noqa: BLE001 - fail CLOSED here, unlike the gate
            # The admin gate itself fails open on a lookup error because the
            # caller is already authenticated. This is the opposite case: we are
            # about to REMOVE a control, and doing that on incomplete information
            # is how someone locks themselves out. Refuse and let them retry.
            logger.error(
                "Could not confirm TOTP before disabling email MFA for %s: %s",
                user.id,
                exc,
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Could not verify your other factors right now. Please try again.",
            )
        if not has_totp:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Administrator accounts must keep a second factor. Set up an "
                    "authenticator app first, then disable email codes."
                ),
            )

    try:
        factors = cognito.apply_mfa_preference(
            credentials.credentials, user.email, email_enabled=False
        )
    except cognito.PROVIDER_ERRORS as exc:
        code = cognito.provider_error_code(exc)
        logger.error("Cognito SetUserMFAPreference (email off) failed: %s", code)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service unavailable",
        )

    auth_events.emit(
        AuthEvent.MFA_DISABLED,
        user_id=user.id,
        provider="cognito",
        factor=cognito.EMAIL_FACTOR,
    )
    return {
        "message": "Email two-factor authentication disabled.",
        "factors": factors,
    }


class ForgotPasswordRequest(BaseModel):
    email: CanonicalEmail


class ConfirmForgotPasswordRequest(BaseModel):
    email: CanonicalEmail
    code: str
    new_password: str


@router.post("/forgot-password", status_code=status.HTTP_202_ACCEPTED)
def forgot_password(request: ForgotPasswordRequest, db: Session = Depends(get_db)):
    """Start a self-service password reset (Phase 6 item 3, Decision 10).

    Requires the pool's email delivery to be routed through SES (verified
    domain + DKIM) -- Cognito's built-in ``COGNITO_DEFAULT`` sender is rate
    limited to a level that is unusable for real traffic. See
    ``infra/terraform/modules/cognito`` (``ses_source_arn``).

    ALWAYS returns 202, regardless of whether the address exists or is a
    local/break-glass account. Reporting "no such user" here would turn this
    endpoint into an account-enumeration oracle, which is the standard failure
    mode of naive reset flows. The pool client also has
    ``prevent_user_existence_errors = ENABLED`` for the same reason.

    UNAVAILABLE when the pool uses email MFA. AWS forbids email being both a
    second factor and the account-recovery channel, so such a pool is created
    with ``account_recovery_setting = admin_only`` and ``ForgotPassword`` can
    deliver nothing. Returning the usual generic 202 in that configuration would
    be a lie that costs the user a support ticket to discover, so this reports
    the situation directly -- see the 409 branch below.
    """
    email = canonicalize_email(request.email)
    generic = {"message": "If that account exists, a reset code has been sent."}

    if settings.AUTH_EMAIL_MFA_ENABLED:
        # Not an enumeration risk: the answer is a property of the DEPLOYMENT,
        # identical for every address including ones that do not exist, so it
        # reveals nothing about any particular account.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Self-service password reset is unavailable because this "
                "environment uses email verification codes for sign-in. Ask an "
                "administrator to reset your password."
            ),
        )

    try:
        cognito.forgot_password(email)
    except cognito.PROVIDER_ERRORS as exc:
        code = cognito.provider_error_code(exc)
        if code in ("UserNotFoundException", "InvalidParameterException"):
            # Swallow — see the enumeration note above.
            return generic
        if code == "LimitExceededException":
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many reset attempts. Please try again later.",
            )
        logger.error("Cognito ForgotPassword failed: %s", code)
        # Still generic to the caller — do not leak service state on this endpoint.
        return generic

    return generic


@router.post("/forgot-password/confirm", status_code=status.HTTP_200_OK)
def confirm_forgot_password(
    request: ConfirmForgotPasswordRequest, db: Session = Depends(get_db)
):
    """Complete a self-service password reset with the emailed code.

    On success, stamps ``tokens_valid_from`` so every access token issued before
    the reset is rejected on its next request, and clears the stored refresh
    token. A password reset that left the attacker's existing session alive
    would defeat the purpose of the reset.
    """
    email = canonicalize_email(request.email)

    if settings.AUTH_EMAIL_MFA_ENABLED:
        # Mirrors the guard on /forgot-password. No code can have been issued in
        # this configuration, so accepting one here could only ever waste the
        # caller's time -- and leaving the endpoint open would let it be used to
        # probe reset codes that the other half of the flow refuses to send.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Self-service password reset is unavailable in this environment. "
                "Ask an administrator to reset your password."
            ),
        )

    try:
        cognito.confirm_forgot_password(email, request.code, request.new_password)
    except cognito.PROVIDER_ERRORS as exc:
        code = cognito.provider_error_code(exc)
        if code in ("CodeMismatchException", "ExpiredCodeException"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="That reset code is invalid or has expired.",
            )
        if code == "InvalidPasswordException":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="New password does not meet the password policy.",
            )
        if code == "LimitExceededException":
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many attempts. Please try again later.",
            )
        logger.error("Cognito ConfirmForgotPassword failed: %s", code)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service unavailable",
        )

    user = db.query(User).filter(func.lower(User.email) == email).first()
    if user is not None:
        now = datetime.now(timezone.utc)
        user.password_changed_at = now
        user.tokens_valid_from = now
        user.encrypted_cognito_refresh_token = None
        db.commit()
        auth_events.emit(
            AuthEvent.PASSWORD_RESET_COMPLETED, user_id=user.id, provider="cognito"
        )

    return {"message": "Password reset successfully. Please sign in."}


class ChangePasswordRequest(BaseModel):
    """Request body for changing password."""

    current_password: str
    new_password: str


@router.post("/change-password", status_code=status.HTTP_200_OK)
def change_password(
    request: ChangePasswordRequest,
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    auth: tuple[User, dict] = Depends(get_current_user_with_payload),
    db: Session = Depends(get_db),
):
    """Change the authenticated user's password.

    Calls Cognito ``ChangePassword`` with the caller's own access token (no
    password re-entry needed server-side beyond what Cognito itself
    requires); stamps ``tokens_valid_from`` so the generalized revocation
    check (§5.3) rejects any access token issued before this instant, and
    revokes the stored refresh token so the old session cannot silently
    refresh past the change.

    New password requirements defer entirely to the pool's own password
    policy (12+ chars, mixed case/digits/symbols per the Terraform module).
    """
    user, _payload = auth

    # get_current_user_with_payload's dependency chain already verified the
    # credential; the raw bearer string is what Cognito's (non-admin)
    # ChangePassword API needs, obtained via the same HTTPBearer scheme
    # FastAPI already parsed for this request.
    try:
        cognito.change_password(
            credentials.credentials, request.current_password, request.new_password
        )
    except cognito.PROVIDER_ERRORS as exc:
        code = cognito.provider_error_code(exc)
        if code == "NotAuthorizedException":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Current password is incorrect",
            )
        if code == "InvalidPasswordException":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="New password does not meet the password policy",
            )
        logger.error("Cognito ChangePassword failed: %s", code)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service unavailable",
        )

    # Stamp tokens_valid_from so the generalized revocation check (§5.3)
    # rejects every access token issued before this instant, and revoke the
    # stored refresh token so the pre-change session cannot silently refresh
    # past the change.
    user.tokens_valid_from = datetime.now(timezone.utc)
    if user.encrypted_cognito_refresh_token:
        try:
            old_refresh = decrypt_cognito_refresh_token(
                user.encrypted_cognito_refresh_token
            )
            cognito.revoke_token(old_refresh)
        except Exception:  # noqa: BLE001 - best-effort; the token is being replaced regardless
            logger.warning(
                "Failed to revoke pre-change refresh token for user %s", user.id
            )
        user.encrypted_cognito_refresh_token = None
    db.commit()

    auth_events.emit(AuthEvent.PASSWORD_CHANGED, user_id=user.id, provider="cognito")
    return {"message": "Password changed successfully"}
