"""Unit tests for ``app.connectors.crypto.TokenCipher``."""

from __future__ import annotations

import pytest
from cryptography.fernet import Fernet

from app.connectors.crypto import TokenCipher
from app.connectors.errors import ToolErrorCode, UndecryptableToken

_PLAINTEXT = "gho_example-not-a-real-token"


def _key() -> str:
    return Fernet.generate_key().decode()


def test_decrypt_returns_plaintext_when_round_tripped():
    # Arrange
    cipher = TokenCipher(_key())

    # Act
    restored = cipher.decrypt(cipher.encrypt(_PLAINTEXT))

    # Assert
    assert restored == _PLAINTEXT


def test_encrypt_hides_plaintext_when_ciphertext_produced():
    # Arrange
    cipher = TokenCipher(_key())

    # Act
    ciphertext = cipher.encrypt(_PLAINTEXT)

    # Assert
    assert _PLAINTEXT not in ciphertext


def test_encrypt_differs_between_calls_when_same_plaintext():
    # Arrange
    cipher = TokenCipher(_key())

    # Act / Assert
    assert cipher.encrypt(_PLAINTEXT) != cipher.encrypt(_PLAINTEXT)


def test_decrypt_opens_old_ciphertext_when_old_key_kept_after_rotation():
    # Arrange
    old_key, new_key = _key(), _key()
    old_ciphertext = TokenCipher(old_key).encrypt(_PLAINTEXT)

    # Act
    rotated = TokenCipher(f"{new_key},{old_key}")

    # Assert
    assert rotated.decrypt(old_ciphertext) == _PLAINTEXT


def test_encrypt_uses_first_key_when_several_keys_configured():
    # Arrange
    old_key, new_key = _key(), _key()
    rotated = TokenCipher(f"{new_key},{old_key}")

    # Act
    ciphertext = rotated.encrypt(_PLAINTEXT)

    # Assert: the new key alone opens it; the old key alone does not.
    assert TokenCipher(new_key).decrypt(ciphertext) == _PLAINTEXT
    with pytest.raises(UndecryptableToken):
        TokenCipher(old_key).decrypt(ciphertext)


def test_decrypt_raises_undecryptable_when_key_dropped():
    # Arrange
    ciphertext = TokenCipher(_key()).encrypt(_PLAINTEXT)

    # Act / Assert
    with pytest.raises(UndecryptableToken) as exc_info:
        TokenCipher(_key()).decrypt(ciphertext)
    assert exc_info.value.code is ToolErrorCode.CONNECTION_EXPIRED


@pytest.mark.parametrize("garbage", ["", "not-fernet", "gAAAAA", "ünïcode"])
def test_decrypt_raises_undecryptable_when_ciphertext_malformed(garbage):
    # Arrange
    cipher = TokenCipher(_key())

    # Act / Assert
    with pytest.raises(UndecryptableToken):
        cipher.decrypt(garbage)


def test_decrypt_error_does_not_leak_ciphertext_when_undecryptable():
    # Arrange
    ciphertext = TokenCipher(_key()).encrypt(_PLAINTEXT)

    # Act
    with pytest.raises(UndecryptableToken) as exc_info:
        TokenCipher(_key()).decrypt(ciphertext)

    # Assert
    assert ciphertext not in str(exc_info.value)
    assert _PLAINTEXT not in str(exc_info.value)


_VALID_KEY_LITERAL = (
    "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="  # fixed, so test ids stay stable
)


@pytest.mark.parametrize("keys", ["", "   ", "not-a-key", f"{_VALID_KEY_LITERAL},"])
def test_init_raises_value_error_when_keys_unusable(keys):
    # Act / Assert
    with pytest.raises(ValueError):
        TokenCipher(keys)


def test_init_error_does_not_leak_key_material_when_key_invalid():
    # Arrange
    bad = "secret-looking-but-invalid-key-material"

    # Act
    with pytest.raises(ValueError) as exc_info:
        TokenCipher(bad)

    # Assert
    assert bad not in str(exc_info.value)
