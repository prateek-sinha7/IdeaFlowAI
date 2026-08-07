"""Security utilities for password hashing and JWT token management."""

import uuid
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

import bcrypt
from jose import jwt

from app.core.config import settings

if TYPE_CHECKING:  # pragma: no cover - type-only import
    from sqlalchemy.orm import Session

# JWT configuration
ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    """Hash a plain-text password using bcrypt.

    Args:
        password: The plain-text password to hash.

    Returns:
        The bcrypt hash string.
    """
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plain-text password against a bcrypt hash.

    Args:
        plain: The plain-text password to verify.
        hashed: The bcrypt hash to verify against.

    Returns:
        True if the password matches the hash, False otherwise.
    """
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def create_access_token(user_id: str) -> str:
    """Create a JWT access token with 24-hour expiry.

    Each token is given a fresh ``jti`` (JWT ID) so it can be individually
    revoked via the ``revoked_tokens`` table.

    Args:
        user_id: The user ID to encode in the token's 'sub' claim.

    Returns:
        The encoded JWT token string.
    """
    now = datetime.now(timezone.utc)
    expire = now + timedelta(hours=settings.ACCESS_TOKEN_EXPIRE_HOURS)
    payload = {
        "sub": user_id,
        "exp": expire,
        "iat": now,
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str, *, verify_exp: bool = True) -> dict:
    """Decode and validate a JWT access token.

    Args:
        token: The JWT token string to decode.
        verify_exp: When False, an expired token still decodes successfully
            (signature/issuer-equivalent checks still apply). Used ONLY by
            the refresh path (``core.identity.verify_credential(...,
            allow_expired=True)``), which needs to identify who an expired
            token belonged to in order to mint a replacement.

    Returns:
        The decoded payload dictionary with 'sub', 'exp', 'iat', and 'jti'
        claims.

    Raises:
        JWTError: If the token is expired (when verify_exp=True), malformed,
            or has an invalid signature.
    """
    return jwt.decode(
        token,
        settings.SECRET_KEY,
        algorithms=[ALGORITHM],
        options={"verify_exp": verify_exp},
    )


def is_token_revoked(jti: str, db: "Session") -> bool:
    """Return True if the given JWT ``jti`` has been explicitly revoked.

    A single source of truth for "is this individual token revoked" — used by
    both the HTTP dependency (`get_current_user`) and the WebSocket handler so
    that revocations are honoured everywhere.

    Args:
        jti: The JWT ID claim to check.
        db: An active SQLAlchemy session.

    Returns:
        True if a row exists in ``revoked_tokens`` for ``jti``, else False.
    """
    # Local import to avoid a circular dependency: revoked_token -> models ->
    # security at module load time.
    from app.models.revoked_token import RevokedToken

    if not jti:
        return False
    return (
        db.query(RevokedToken.id)
        .filter(RevokedToken.jti == jti)
        .first()
        is not None
    )
