"""Focused tests for HS256/RS256 algorithm verification.

This suite verifies that the auth layer correctly:
- Rejects EVERY locally-forged HS256 token, since Cognito is the sole
  authentication authority (Cognito-only auth migration,
  ``.kiro/specs/login/prompt.md`` Phase 1) — there is no local credential
  path left to fall back to, on purpose.
- Uses RS256 for Cognito verification (signature + key resolution)
- Rejects algorithm confusion attacks (HS256 tokens where RS256 is expected)
- Rejects malformed tokens and missing kid headers

TestNoLocalHs256Fallback is a regression guard: it pins the removal of the
local/legacy JWT path so a future change cannot silently reintroduce an
HS256 fallback into ``core.identity.verify_credential`` without this suite
catching it.
"""

import time
from unittest.mock import patch

import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.core import cognito
from app.core.config import settings
from app.core.cognito import CognitoVerificationError, CognitoPrincipal
from app.core.identity import CredentialInvalid, verify_credential


class TestNoLocalHs256Fallback:
    """Cognito is the sole authentication authority — HS256 must never work.

    Regression guard for the Cognito-only auth migration: pins that
    ``core.identity.verify_credential`` has no fallback path for a
    locally-signed HS256 token, however it is constructed. Uses
    ``settings.SECRET_KEY`` only because that value still exists (it derives
    the Fernet key for at-rest encryption) — not because there is any
    remaining code path that verifies a JWT with it.
    """

    def test_hs256_token_signed_with_secret_key_is_rejected(self):
        token = pyjwt.encode(
            {"sub": "user-123", "exp": int(time.time()) + 3600},
            settings.SECRET_KEY,
            algorithm="HS256",
        )
        with pytest.raises(CredentialInvalid):
            verify_credential(token)

    def test_hs256_token_with_admin_claims_is_rejected(self):
        """Even a token forged with plausible admin-looking claims must fail —
        there is no code path that would grant it any authority regardless."""
        token = pyjwt.encode(
            {
                "sub": "attacker-999",
                "exp": int(time.time()) + 3600,
                "cognito:groups": ["flowin-admins"],
                "jti": "forged",
            },
            settings.SECRET_KEY,
            algorithm="HS256",
        )
        with pytest.raises(CredentialInvalid):
            verify_credential(token)

    def test_malformed_token_is_rejected(self):
        with pytest.raises(CredentialInvalid):
            verify_credential("not-a-jwt-at-all")


class TestCognitoRS256Verification:
    """Cognito access token verification with RS256 and JWKS."""

    @pytest.fixture
    def rsa_key(self):
        """Generate an RSA key pair for testing."""
        return rsa.generate_private_key(public_exponent=65537, key_size=2048)

    @pytest.fixture
    def cognito_jwks(self, rsa_key):
        """Create a fake Cognito JWKS response."""
        public_key = rsa_key.public_key()
        public_numbers = public_key.public_numbers()

        def _b64u_uint(n: int) -> str:
            """Base64url encode an unsigned integer."""
            import base64

            return (
                base64.urlsafe_b64encode(n.to_bytes((n.bit_length() + 7) // 8, "big"))
                .decode("ascii")
                .rstrip("=")
            )

        return {
            "keys": [
                {
                    "kty": "RSA",
                    "kid": "test-key-1",
                    "use": "sig",
                    "alg": "RS256",
                    "n": _b64u_uint(public_numbers.n),
                    "e": _b64u_uint(public_numbers.e),
                }
            ]
        }

    @pytest.fixture
    def test_cognito_settings(self, monkeypatch):
        """Mock Cognito settings for testing."""
        monkeypatch.setattr(settings, "COGNITO_USER_POOL_ID", "test-pool-123")
        monkeypatch.setattr(settings, "COGNITO_REGION", "us-east-1")
        monkeypatch.setattr(settings, "COGNITO_CLIENT_ID", "test-client-id")
        return settings

    def test_cognito_token_uses_rs256(self, rsa_key):
        """Verify Cognito tokens use RS256 algorithm."""
        now = int(time.time())
        token = pyjwt.encode(
            {
                "sub": "user-123",
                "jti": "test-jti",
                "iat": now,
                "exp": now + 3600,
                "iss": f"https://cognito-idp.us-east-1.amazonaws.com/{settings.COGNITO_USER_POOL_ID}",
                "token_use": "access",
                "client_id": settings.COGNITO_CLIENT_ID,
                "cognito:groups": [],
            },
            rsa_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            ),
            algorithm="RS256",
            headers={"kid": "test-key-1"},
        )

        header = pyjwt.get_unverified_header(token)
        assert header["alg"] == "RS256"
        assert header["kid"] == "test-key-1"

    def test_cognito_verification_rejects_hs256_algorithm_confusion(
        self, rsa_key, cognito_jwks, test_cognito_settings
    ):
        """Verify algorithm confusion attack is rejected (HS256 token with RS256 verification)."""
        now = int(time.time())

        # Create an HS256 token (attacker tries to trick the server)
        hs256_token = pyjwt.encode(
            {
                "sub": "attacker-999",
                "jti": "malicious",
                "iat": now,
                "exp": now + 3600,
                "iss": cognito._issuer(),
                "token_use": "access",
                "client_id": settings.COGNITO_CLIENT_ID,
                "cognito:groups": [],
            },
            "a-shared-secret",
            algorithm="HS256",
        )

        # Mock the JWKS fetch to return our test key
        with patch.object(
            cognito,
            "_fetch_jwks",
            return_value={k["kid"]: k for k in cognito_jwks["keys"]},
        ):
            # Should reject the HS256 token because RS256 is enforced
            with pytest.raises(CognitoVerificationError):
                cognito.verify_cognito_access_token(hs256_token)

    def test_cognito_verification_accepts_valid_rs256_token(
        self, rsa_key, cognito_jwks, test_cognito_settings
    ):
        """Verify valid RS256 tokens are accepted."""
        now = int(time.time())

        # Use the actual issuer from cognito._issuer()
        issuer = cognito._issuer()

        token = pyjwt.encode(
            {
                "sub": "user-123",
                "jti": "test-jti",
                "iat": now,
                "exp": now + 3600,
                "iss": issuer,
                "token_use": "access",
                "client_id": settings.COGNITO_CLIENT_ID,
                "cognito:groups": ["admins"],
                "username": "testuser",
            },
            rsa_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            ),
            algorithm="RS256",
            headers={"kid": "test-key-1"},
        )

        # Mock the JWKS fetch
        with patch.object(
            cognito,
            "_fetch_jwks",
            return_value={k["kid"]: k for k in cognito_jwks["keys"]},
        ):
            principal = cognito.verify_cognito_access_token(token)
            assert isinstance(principal, CognitoPrincipal)
            assert principal.sub == "user-123"
            assert principal.jti == "test-jti"
            assert principal.groups == ["admins"]

    def test_cognito_verification_rejects_missing_kid_header(
        self, rsa_key, cognito_jwks, test_cognito_settings
    ):
        """Verify tokens without kid header are rejected."""
        now = int(time.time())
        token = pyjwt.encode(
            {
                "sub": "user-123",
                "jti": "test-jti",
                "iat": now,
                "exp": now + 3600,
                "iss": cognito._issuer(),
                "token_use": "access",
                "client_id": settings.COGNITO_CLIENT_ID,
                "cognito:groups": [],
            },
            rsa_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            ),
            algorithm="RS256",
            # Intentionally omit the kid header
        )

        with patch.object(
            cognito,
            "_fetch_jwks",
            return_value={k["kid"]: k for k in cognito_jwks["keys"]},
        ):
            with pytest.raises(
                CognitoVerificationError, match="token header missing kid"
            ):
                cognito.verify_cognito_access_token(token)

    def test_cognito_verification_rejects_unknown_kid(
        self, rsa_key, cognito_jwks, test_cognito_settings
    ):
        """Verify tokens with unknown kid are rejected."""
        now = int(time.time())
        token = pyjwt.encode(
            {
                "sub": "user-123",
                "jti": "test-jti",
                "iat": now,
                "exp": now + 3600,
                "iss": cognito._issuer(),
                "token_use": "access",
                "client_id": settings.COGNITO_CLIENT_ID,
                "cognito:groups": [],
            },
            rsa_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            ),
            algorithm="RS256",
            headers={"kid": "unknown-key-99"},
        )

        with patch.object(
            cognito,
            "_fetch_jwks",
            return_value={k["kid"]: k for k in cognito_jwks["keys"]},
        ):
            with pytest.raises(
                CognitoVerificationError, match="Unknown signing key id"
            ):
                cognito.verify_cognito_access_token(token)

    def test_cognito_verification_rejects_wrong_issuer(
        self, rsa_key, cognito_jwks, test_cognito_settings
    ):
        """Verify tokens with wrong issuer are rejected."""
        now = int(time.time())
        token = pyjwt.encode(
            {
                "sub": "user-123",
                "jti": "test-jti",
                "iat": now,
                "exp": now + 3600,
                "iss": "https://cognito-idp.us-east-1.amazonaws.com/wrong-pool-id",  # Wrong issuer
                "token_use": "access",
                "client_id": settings.COGNITO_CLIENT_ID,
                "cognito:groups": [],
            },
            rsa_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            ),
            algorithm="RS256",
            headers={"kid": "test-key-1"},
        )

        with patch.object(
            cognito,
            "_fetch_jwks",
            return_value={k["kid"]: k for k in cognito_jwks["keys"]},
        ):
            with pytest.raises(
                CognitoVerificationError, match="token verification failed"
            ):
                cognito.verify_cognito_access_token(token)
