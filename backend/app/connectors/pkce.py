"""PKCE (RFC 7636, S256 only) and OAuth state helpers.

Only ``S256`` is implemented: the plain method offers no protection against an
intercepted authorization request. State values are random 256-bit tokens and
only their SHA-256 hash is ever stored.
"""

from __future__ import annotations

import base64
import hashlib
import secrets

CODE_CHALLENGE_METHOD = "S256"


def generate_code_verifier() -> str:
    """Return a new PKCE code verifier (86 URL-safe characters, within RFC 7636's 43..128)."""
    return secrets.token_urlsafe(64)


def code_challenge_s256(verifier: str) -> str:
    """Return ``base64url(sha256(verifier))`` without padding (RFC 7636 section 4.2)."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def generate_state() -> str:
    """Return a new OAuth ``state`` value (256 bits of randomness, URL-safe)."""
    return secrets.token_urlsafe(32)


def hash_state(state: str) -> str:
    """Return the lower-case SHA-256 hex digest under which a state is stored."""
    return hashlib.sha256(state.encode("utf-8")).hexdigest()
