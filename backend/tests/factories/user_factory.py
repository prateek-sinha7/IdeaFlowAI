"""Shared helper for creating Cognito-backed users in tests.

``POST /api/auth/register`` is a permanent 403 by design (see
``app/api/auth.py``) — account creation is administrator-only, the endpoint
only still exists so legacy clients get a clear error instead of a 404.
Cognito is the sole authentication authority (Cognito-only auth migration,
``.kiro/specs/login/prompt.md`` Phase 1): there is no local password to
hash, so a test user needs BOTH a local ``User`` row (with a ``cognito_sub``)
AND a way for ``POST /api/auth/login`` to succeed without a real AWS call.

``FakeCognitoAuth`` provides that: it generates an RSA keypair once, patches
``app.core.cognito._fetch_jwks`` to serve its public key, and patches
``app.core.cognito.admin_initiate_auth`` to mint a real RS256 access token
signed with the matching private key -- so the token that comes back from
``POST /api/auth/login`` passes ``verify_cognito_access_token`` exactly the
way a real Cognito token would (same claim shape, same signature algorithm),
without any network call. This is the same pattern
``tests/unit/test_cognito_verifier.py`` uses for the verifier's own suite.

``create_user`` inserts the local row (a ``cognito_sub`` that matches what
``FakeCognitoAuth.login_response`` will mint for that email) and returns it.
"""

from __future__ import annotations

import base64
import time
import uuid
from dataclasses import dataclass, field

from botocore.exceptions import ClientError
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jose import jwt as jose_jwt
from sqlalchemy.orm import Session

from app.core import cognito
from app.core.config import settings
from app.models.user import User
from tests.fakes.cognito_pool import FakeCognitoPool


def create_user(
    session: Session,
    email: str,
    password: str,
    *,
    tier: str = "basic",
    is_admin: bool = False,
    cognito_sub: str | None = None,
) -> User:
    """Insert and commit a Cognito-linked user row.

    ``password`` is accepted (and otherwise unused) so every existing call
    site — written when this helper hashed a local password — keeps working
    unmodified; the actual credential now lives entirely in Cognito, mocked
    per-test via :class:`FakeCognitoAuth`.
    """
    del password
    user = User(
        id=str(uuid.uuid4()),
        email=email,
        cognito_sub=cognito_sub or str(uuid.uuid4()),
        tier=tier,
        is_admin=is_admin,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def _b64u_uint(value: int) -> str:
    raw = value.to_bytes((value.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


@dataclass
class FakeCognitoAuth:
    """Monkeypatches ``app.core.cognito`` so login/verify work with no AWS call.

    Usage::

        fake = FakeCognitoAuth(monkeypatch)
        fake.configure_settings()
        user = create_user(session, email, "pw", cognito_sub=fake.sub_for(email))
        # POST /api/auth/login now succeeds and returns a token that
        # verify_cognito_access_token accepts.
    """

    monkeypatch: object
    kid: str = "test-key-1"
    pool_id: str = "eu-central-1_testpool"
    region: str = "eu-central-1"
    client_id: str = "test-client-id"
    client_secret: str = "test-client-secret"
    #: Optional in-memory pool (``tests/fakes/cognito_pool.py``). When set,
    #: ``configure_settings`` installs it over every ``cognito`` Admin* wrapper
    #: and minted tokens carry the pool's CURRENT group membership -- which is
    #: what lets a test exercise group-driven entitlement decisions and
    #: just-in-time provisioning against one consistent identity store instead
    #: of two hand-synced doubles.
    pool: FakeCognitoPool | None = None
    _subs_by_email: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self._key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self._pem = self._key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode("ascii")
        numbers = self._key.public_key().public_numbers()
        self._jwk = {
            "kty": "RSA",
            "kid": self.kid,
            "use": "sig",
            "alg": "RS256",
            "n": _b64u_uint(numbers.n),
            "e": _b64u_uint(numbers.e),
        }

    def configure_settings(self) -> None:
        self.monkeypatch.setattr(settings, "COGNITO_USER_POOL_ID", self.pool_id)
        self.monkeypatch.setattr(settings, "COGNITO_CLIENT_ID", self.client_id)
        self.monkeypatch.setattr(settings, "COGNITO_CLIENT_SECRET", self.client_secret)
        self.monkeypatch.setattr(settings, "COGNITO_REGION", self.region)
        self.monkeypatch.setattr(cognito, "_fetch_jwks", lambda: {self.kid: self._jwk})
        self.monkeypatch.setattr(
            cognito, "admin_initiate_auth", self._admin_initiate_auth
        )
        # The JWKS cache is module-level state keyed by kid. Every
        # FakeCognitoAuth generates a fresh RSA key but reuses the SAME
        # literal kid ("test-key-1"), so a stale cache entry from a
        # PRIOR test would otherwise verify against the wrong public key.
        # Mirrors tests/unit/test_cognito_verifier.py's clean_jwks_cache.
        cognito._jwks_cache.replace({})
        cognito._jwks_cache._fetched_at = 0.0

        if self.pool is not None:
            self.pool.install(self.monkeypatch)

    def sub_for(self, email: str) -> str:
        """Deterministic per-email sub, minted on first use."""
        return self._subs_by_email.setdefault(email, str(uuid.uuid4()))

    def seed_pool_user(
        self,
        email: str,
        *,
        groups: set[str] | None = None,
        enabled: bool = True,
        user_status: str = "CONFIRMED",
    ):
        """Register ``email`` in the attached pool under this fake's ``sub_for``.

        The shared ``sub`` is the reason this lives here rather than on the pool:
        the token minted for an email and the pool row looked up by ``sub`` must
        agree, or a JIT-provisioning test would pass for the wrong reason.
        """
        if self.pool is None:
            raise RuntimeError("FakeCognitoAuth has no pool attached")
        return self.pool.add(
            sub=self.sub_for(email),
            email=email,
            groups=groups,
            enabled=enabled,
            user_status=user_status,
        )

    def mint_token(
        self,
        email: str,
        *,
        groups: list[str] | None = None,
        expires_in: int = 3600,
        issued_at: int | None = None,
    ) -> str:
        """Public token minter for tests that need a bearer without a login.

        ``expires_in``/``issued_at`` exist so a test can produce an ALREADY-EXPIRED
        but otherwise perfectly-signed token -- the only way to prove that a code
        path actually runs the verifier's expiry check rather than merely looking
        plausible (see ``run_stream.py``'s periodic re-check).
        """
        return self._mint_token(
            email, groups=groups, expires_in=expires_in, issued_at=issued_at
        )

    def _issuer(self) -> str:
        return f"https://cognito-idp.{self.region}.amazonaws.com/{self.pool_id}"

    def _mint_token(
        self,
        email: str,
        *,
        groups: list[str] | None = None,
        expires_in: int = 3600,
        issued_at: int | None = None,
    ) -> str:
        iat = int(time.time()) if issued_at is None else issued_at
        claims = {
            "sub": self.sub_for(email),
            "iss": self._issuer(),
            "client_id": self.client_id,
            "token_use": "access",
            "jti": str(uuid.uuid4()),
            "iat": iat,
            "exp": iat + expires_in,
            "cognito:groups": groups or [],
            "username": self.sub_for(email),
        }
        return jose_jwt.encode(
            claims, self._pem, algorithm="RS256", headers={"kid": self.kid}
        )

    def _admin_initiate_auth(self, email: str, password: str) -> dict:
        """Fake ``AdminInitiateAuth``.

        Always succeeds when no pool is attached (credential CHECKING is out of
        scope for most callers; only the resulting token's shape matters). With a
        pool attached it additionally behaves like the real thing on the two
        outcomes that change control flow in ``api/auth.py``:

        * an unknown email raises ``NotAuthorizedException`` -- NOT
          ``UserNotFoundException`` -- because this pool's app client runs with
          ``prevent_user_existence_errors = ENABLED``, which AWS documents as
          collapsing "no such user" into the same error a wrong password gives.
          Getting this wrong in a fake would make an anti-enumeration test pass
          against behaviour the real pool never exhibits;
        * a disabled user likewise cannot authenticate at all, which is what
          lets ``provision_from_login`` treat a successful auth as proof of
          ``Enabled``.

        Minted tokens carry the pool's CURRENT groups, so a test that changes
        group membership and logs in again sees the change reflected in the
        token's ``cognito:groups`` exactly as it would in production.
        """
        del password
        groups: list[str] | None = None
        if self.pool is not None:
            pool_user = self.pool.get(email)
            if pool_user is None or not pool_user.enabled:
                raise ClientError(
                    {"Error": {"Code": "NotAuthorizedException", "Message": "denied"}},
                    "AdminInitiateAuth",
                )
            groups = sorted(pool_user.groups)
        return {
            "AuthenticationResult": {
                "AccessToken": self._mint_token(email, groups=groups),
                "RefreshToken": "fake-refresh-token",
            }
        }
