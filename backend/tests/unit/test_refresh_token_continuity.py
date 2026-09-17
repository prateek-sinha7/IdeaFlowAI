"""Pins the Cognito refresh-token key derivation against silent breakage.

Refresh tokens are Fernet-encrypted at rest (migration 0032) under a key
derived from ``settings.SECRET_KEY`` via HKDF-SHA256 with the info string
``flowin-cognito-refresh-v1``. Nothing else in the suite would notice if that
derivation changed: encrypt-then-decrypt round-trip tests pass under ANY
self-consistent key, so a changed info string, a changed HKDF length, an added
salt, or a switch to using ``SECRET_KEY`` directly would all stay green while
rendering every refresh token already in the production database undecryptable.
Users would be silently logged out and forced to re-authenticate.

This test decrypts a ciphertext that was generated ONCE, out-of-band, and
hard-coded below. Any change to the derivation makes it fail.

Regenerating ``LEGACY_CIPHERTEXT`` (only legitimate as part of a deliberate,
documented key-rotation change -- it invalidates stored tokens):

    cd backend
    uv run python -c "from app.core.crypto import _derive_fernet_key; \
from cryptography.fernet import Fernet; \
k = _derive_fernet_key('dev-secret-key-change-in-production', \
b'flowin-cognito-refresh-v1'); \
print(Fernet(k).encrypt(b'test-refresh-token').decode())"

Note the module exports ``decrypt_cognito_refresh_token``; the task brief calls
it ``decrypt_refresh_token``. Same function, real name used here.
"""

from __future__ import annotations

import pytest

from app.core import crypto


#: The SECRET_KEY the ciphertext below was derived from. Pinned explicitly
#: rather than read from settings so the test is independent of any local
#: ``backend/.env``.
LEGACY_SECRET_KEY = "dev-secret-key-change-in-production"

#: Plaintext encrypted under LEGACY_SECRET_KEY + the v1 refresh info string.
LEGACY_PLAINTEXT = "test-refresh-token"

#: Fernet ciphertext generated once (see module docstring). Fernet embeds a
#: creation timestamp, but ``decrypt`` without a ``ttl`` ignores age, so this
#: constant does not expire.
LEGACY_CIPHERTEXT = (
    "gAAAAABqpxWsSQfTZaZ6uGwySawzbVUHZPwA2es9Sry_W_Pyxn8Ysmb_bINTeb0j"
    "-ED2CqdvLee0qj8-9WYskvKT38KXaYBpbaDgFvWP-9DcJm8dT_-jqR8="
)


@pytest.fixture()
def pinned_secret_key(monkeypatch):
    """Point the module at LEGACY_SECRET_KEY and clear its cached Fernet.

    ``_cognito_refresh_fernet`` is a module-level cache, so it must be reset
    both before (to pick up the pinned key) and after (so a key derived from
    the pinned value does not leak into other tests).
    """
    monkeypatch.setattr(crypto.settings, "SECRET_KEY", LEGACY_SECRET_KEY)
    monkeypatch.setattr(crypto, "_cognito_refresh_fernet", None)
    yield
    crypto._cognito_refresh_fernet = None


def test_decrypt_cognito_refresh_token_returns_the_plaintext_when_the_ciphertext_is_legacy(
    pinned_secret_key,
):
    """The derivation contract itself: HKDF-SHA256, no salt, 32 bytes, info
    ``flowin-cognito-refresh-v1``, over ``SECRET_KEY`` as UTF-8."""
    assert crypto.decrypt_cognito_refresh_token(LEGACY_CIPHERTEXT) == LEGACY_PLAINTEXT


def test_derive_fernet_key_is_stable_when_given_the_pinned_secret(pinned_secret_key):
    """Pins the derived key itself, so a failure localises to the HKDF
    parameters rather than to Fernet or the stored ciphertext."""
    derived = crypto._derive_fernet_key(
        LEGACY_SECRET_KEY, crypto._COGNITO_REFRESH_HKDF_INFO
    )

    assert derived == b"igWHAUtLCM64P03z-v0UvB58Q8hxUD1XLQbBsnfGSqk="


def test_decrypt_cognito_refresh_token_raises_when_the_pat_key_was_used(
    pinned_secret_key,
):
    """The two info strings must stay materially independent: a PAT ciphertext
    must not decrypt on the refresh-token key, or the domain separation that
    justifies the separate derivation is not real."""
    from cryptography.fernet import Fernet

    pat_key = Fernet(
        crypto._derive_fernet_key(LEGACY_SECRET_KEY, crypto._PAT_HKDF_INFO)
    )
    pat_ciphertext = pat_key.encrypt(LEGACY_PLAINTEXT.encode("utf-8")).decode("ascii")

    with pytest.raises(crypto.InvalidToken):
        crypto.decrypt_cognito_refresh_token(pat_ciphertext)
