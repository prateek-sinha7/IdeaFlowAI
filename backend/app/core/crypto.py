"""Symmetric encryption for application secrets stored at rest.

The handoff feature stores user-supplied GitHub PATs in the database. We
encrypt them with Fernet (AES-128 CBC + HMAC-SHA256) using a key derived
from ``settings.SECRET_KEY`` via HKDF. Using a derived key — not
``SECRET_KEY`` directly — means a leaked JWT-signing key does not also
decrypt every stored PAT, and vice versa.

The single-process derivation has no salt and a fixed info string. That is
intentional: encrypting "key for tenant N" with a per-tenant salt would
require us to look up the salt on every decrypt, which buys nothing over
"if the master key leaks, everything is gone." A single derived key
matches the threat model (server-side at-rest encryption against DB-only
compromise) and keeps the code small.
"""

import base64

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.core.config import settings


_PAT_HKDF_INFO = b"flowin-pat-v1"
# Distinct info string (Cognito migration, 0032): keeps the refresh-token key
# materially independent of the PAT key even though both derive from the same
# SECRET_KEY, so a compromise of one derived key does not also expose the
# other's plaintext.
_COGNITO_REFRESH_HKDF_INFO = b"flowin-cognito-refresh-v1"


def _derive_fernet_key(secret_key: str, info: bytes) -> bytes:
    """Derive a 32-byte Fernet key (URL-safe base64) from the app secret."""
    raw = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=info,
    ).derive(secret_key.encode("utf-8"))
    return base64.urlsafe_b64encode(raw)


# Lazy-initialised so test suites that monkeypatch settings.SECRET_KEY
# before importing this module still get a fresh key.
_pat_fernet: Fernet | None = None


def _get_pat_fernet() -> Fernet:
    global _pat_fernet
    if _pat_fernet is None:
        _pat_fernet = Fernet(_derive_fernet_key(settings.SECRET_KEY, _PAT_HKDF_INFO))
    return _pat_fernet


def encrypt_pat(plaintext: str) -> str:
    """Encrypt a GitHub PAT for at-rest storage. Returns base64 text."""
    if not plaintext:
        raise ValueError("PAT must be a non-empty string")
    token = _get_pat_fernet().encrypt(plaintext.encode("utf-8"))
    return token.decode("ascii")


def decrypt_pat(ciphertext: str) -> str:
    """Decrypt a previously-encrypted PAT. Raises ``InvalidToken`` if the
    ciphertext was produced under a different key (e.g. after SECRET_KEY
    rotation) — caller should treat that as "credential lost, ask user to
    re-enter."
    """
    if not ciphertext:
        raise ValueError("ciphertext must be non-empty")
    try:
        return _get_pat_fernet().decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except InvalidToken:
        raise


# Lazy-initialised for the same reason as _pat_fernet above.
_cognito_refresh_fernet: Fernet | None = None


def _get_cognito_refresh_fernet() -> Fernet:
    global _cognito_refresh_fernet
    if _cognito_refresh_fernet is None:
        _cognito_refresh_fernet = Fernet(
            _derive_fernet_key(settings.SECRET_KEY, _COGNITO_REFRESH_HKDF_INFO)
        )
    return _cognito_refresh_fernet


def encrypt_cognito_refresh_token(plaintext: str) -> str:
    """Encrypt a Cognito refresh token for at-rest storage. Returns base64 text."""
    if not plaintext:
        raise ValueError("refresh token must be a non-empty string")
    token = _get_cognito_refresh_fernet().encrypt(plaintext.encode("utf-8"))
    return token.decode("ascii")


def decrypt_cognito_refresh_token(ciphertext: str) -> str:
    """Decrypt a previously-encrypted Cognito refresh token. Raises
    ``InvalidToken`` if the ciphertext was produced under a different key
    (e.g. after SECRET_KEY rotation) -- caller should treat that as
    "refresh token lost, the user must log in again"."""
    if not ciphertext:
        raise ValueError("ciphertext must be non-empty")
    try:
        return _get_cognito_refresh_fernet().decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except InvalidToken:
        raise


__all__ = [
    "encrypt_pat",
    "decrypt_pat",
    "encrypt_cognito_refresh_token",
    "decrypt_cognito_refresh_token",
    "InvalidToken",
]
