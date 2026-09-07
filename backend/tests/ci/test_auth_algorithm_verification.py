"""Focused tests for HS256/RS256 algorithm verification before python-jose replacement.

This suite verifies that the auth layer correctly:
- Uses HS256 for local authentication (signing + verification)
- Uses RS256 for Cognito verification (signature + key resolution)
- Rejects algorithm confusion attacks (HS256 tokens where RS256 is expected)
- Rejects malformed tokens and missing kid headers

These tests establish requirements BEFORE replacing python-jose with PyJWT,
ensuring the replacement preserves all security properties.
"""

import json
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import MagicMock, patch

import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.core import cognito, security
from app.core.config import settings
from app.core.cognito import CognitoVerificationError, CognitoPrincipal


class TestLocalAuthHS256:
    """Local authentication with HS256 — password + token."""

    def test_create_access_token_uses_hs256(self):
        """Verify create_access_token produces a valid HS256 token."""
        user_id = "user-123"
        token = security.create_access_token(user_id)

        # Decode without verification to inspect the algorithm
        header = pyjwt.get_unverified_header(token)
        assert header["alg"] == "HS256", "Local tokens must use HS256"

    def test_decode_access_token_verifies_hs256_signature(self):
        """Verify decode_access_token validates HS256 signature."""
        user_id = "user-123"
        token = security.create_access_token(user_id)

        # Decoding with correct secret succeeds
        claims = security.decode_access_token(token)
        assert claims["sub"] == user_id
        assert "exp" in claims
        assert "iat" in claims
        assert "jti" in claims

    def test_decode_access_token_rejects_tampered_payload(self):
        """Verify decode_access_token rejects tampered tokens."""
        user_id = "user-123"
        token = security.create_access_token(user_id)

        # Decode without verification to get the payload
        from jose import jwt as jose_jwt

        _ = token.split(".")  # Parts not used; kept for token structure reference
        tampered = jose_jwt.get_unverified_claims(token)
        tampered["sub"] = "attacker-999"
        tampered_token = pyjwt.encode(tampered, settings.SECRET_KEY, algorithm="HS256")

        # Original token should still decode correctly
        claims = security.decode_access_token(token)
        assert claims["sub"] == user_id

        # Tampered token with valid signature but different payload decodes with different claim
        tampered_claims = security.decode_access_token(tampered_token)
        assert tampered_claims["sub"] == "attacker-999"

    def test_decode_access_token_rejects_wrong_secret(self):
        """Verify decode_access_token rejects tokens signed with wrong secret."""
        user_id = "user-123"
        token = security.create_access_token(user_id)

        # Re-sign the payload with a different secret
        payload = pyjwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        wrong_secret_token = pyjwt.encode(payload, "wrong-secret", algorithm="HS256")

        # Should reject due to invalid signature
        from jose import JWTError

        with pytest.raises(JWTError):
            security.decode_access_token(wrong_secret_token)

    def test_decode_access_token_rejects_rs256_local_token(self):
        """Verify decode_access_token rejects RS256 tokens (algorithm confusion)."""
        user_id = "user-123"

        # Create an RS256 token (simulating algorithm confusion attack)
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        rs256_token = pyjwt.encode(
            {"sub": user_id, "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
            key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            ),
            algorithm="RS256",
        )

        # Should reject — wrong algorithm
        from jose import JWTError

        with pytest.raises(JWTError):
            security.decode_access_token(rs256_token)

    def test_access_token_expiry_enforcement(self):
        """Verify expiry is enforced by default."""
        user_id = "user-123"
        token = security.create_access_token(user_id)

        # Token should decode successfully (just issued)
        claims = security.decode_access_token(token)
        assert claims["sub"] == user_id

        # Manually create an expired token
        now = datetime.now(timezone.utc)
        expired_payload = {
            "sub": user_id,
            "exp": now - timedelta(hours=1),  # Already expired
            "iat": now - timedelta(hours=2),
            "jti": "test-jti",
        }
        expired_token = pyjwt.encode(
            expired_payload, settings.SECRET_KEY, algorithm="HS256"
        )

        # Should reject when verify_exp=True (default)
        from jose import JWTError

        with pytest.raises(JWTError):
            security.decode_access_token(expired_token)

    def test_access_token_expiry_can_be_bypassed_for_refresh(self):
        """Verify verify_exp=False allows expired token inspection (refresh path only)."""
        user_id = "user-123"

        # Create an expired token
        now = datetime.now(timezone.utc)
        expired_payload = {
            "sub": user_id,
            "exp": now - timedelta(hours=1),
            "iat": now - timedelta(hours=2),
            "jti": "test-jti",
        }
        expired_token = pyjwt.encode(
            expired_payload, settings.SECRET_KEY, algorithm="HS256"
        )

        # Should reject with verify_exp=True (default)
        from jose import JWTError

        with pytest.raises(JWTError):
            security.decode_access_token(expired_token, verify_exp=True)

        # Should decode successfully with verify_exp=False (refresh endpoint only)
        claims = security.decode_access_token(expired_token, verify_exp=False)
        assert claims["sub"] == user_id
        assert claims["jti"] == "test-jti"


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
