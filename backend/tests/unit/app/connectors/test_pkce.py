"""Unit tests for ``app.connectors.pkce``."""

from __future__ import annotations

import re

from app.connectors.pkce import (
    CODE_CHALLENGE_METHOD,
    code_challenge_s256,
    generate_code_verifier,
    generate_state,
    hash_state,
)

# RFC 7636 appendix B test vector.
_RFC_VERIFIER = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
_RFC_CHALLENGE = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"


def test_code_challenge_s256_matches_rfc_vector_when_verifier_is_the_appendix_b_value():
    # Act
    challenge = code_challenge_s256(_RFC_VERIFIER)

    # Assert
    assert challenge == _RFC_CHALLENGE


def test_code_challenge_s256_has_no_padding_when_digest_encoded():
    # Act
    challenge = code_challenge_s256(generate_code_verifier())

    # Assert
    assert "=" not in challenge
    assert len(challenge) == 43


def test_generate_code_verifier_is_86_url_safe_characters_when_called():
    # Act
    verifier = generate_code_verifier()

    # Assert
    assert len(verifier) == 86
    assert re.fullmatch(r"[A-Za-z0-9_-]+", verifier)


def test_generate_code_verifier_differs_when_called_twice():
    # Act / Assert
    assert generate_code_verifier() != generate_code_verifier()


def test_generate_state_is_43_url_safe_characters_when_called():
    # Act
    state = generate_state()

    # Assert
    assert len(state) == 43
    assert re.fullmatch(r"[A-Za-z0-9_-]+", state)


def test_hash_state_is_64_hex_characters_and_not_the_state_when_hashed():
    # Arrange
    state = generate_state()

    # Act
    digest = hash_state(state)

    # Assert
    assert re.fullmatch(r"[0-9a-f]{64}", digest)
    assert state not in digest


def test_hash_state_is_deterministic_when_same_state_hashed_twice():
    # Act / Assert
    assert hash_state("abc") == hash_state("abc")
    assert hash_state("abc") != hash_state("abd")


def test_code_challenge_method_is_s256_only():
    # Assert
    assert CODE_CHALLENGE_METHOD == "S256"
