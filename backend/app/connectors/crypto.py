"""Token encryption for the connector vault.

``TokenCipher`` wraps a ``MultiFernet`` built from ``TOKEN_ENCRYPTION_KEY``: the
first key encrypts, every key decrypts, which is how a key is rotated. It is
separate from the ``SECRET_KEY``-derived keys in ``app/core/crypto.py``.
"""

from __future__ import annotations

from typing import Protocol

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from app.connectors.errors import UndecryptableToken


class TokenCodec(Protocol):
    """What the OAuth service and token provider need from a cipher."""

    def encrypt(self, plaintext: str) -> str:
        """Return the ciphertext of ``plaintext``."""
        ...

    def decrypt(self, ciphertext: str) -> str:
        """Return the plaintext of ``ciphertext``."""
        ...


class TokenCipher:
    """Encrypts and decrypts provider tokens with a rotating list of Fernet keys."""

    def __init__(self, keys: str) -> None:
        """Build a cipher from comma-separated Fernet keys (first encrypts, all decrypt).

        Raises:
            ValueError: ``keys`` holds no key or an entry is not a valid Fernet key.
                The message never contains key material.
        """
        entries = [entry.strip() for entry in keys.split(",")]
        if not entries or not all(entries):
            raise ValueError("TOKEN_ENCRYPTION_KEY holds no usable key")
        try:
            self._fernet = MultiFernet(
                [Fernet(entry.encode("ascii")) for entry in entries]
            )
        except (ValueError, TypeError, UnicodeEncodeError) as exc:
            raise ValueError(
                "TOKEN_ENCRYPTION_KEY holds an invalid Fernet key"
            ) from exc

    def encrypt(self, plaintext: str) -> str:
        """Return the Fernet ciphertext of ``plaintext``, encrypted with the first key."""
        return self._fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")

    def decrypt(self, ciphertext: str) -> str:
        """Return the plaintext of ``ciphertext``.

        Raises:
            UndecryptableToken: no configured key opens it, or it is malformed.
        """
        try:
            return self._fernet.decrypt(ciphertext.encode("ascii")).decode("utf-8")
        except (InvalidToken, ValueError, UnicodeError) as exc:
            raise UndecryptableToken() from exc
