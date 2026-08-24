"""Offline claim + JWKS verification matrix for ``core/cognito.py``.

This is the Phase 2 exit gate of ``.planning/COGNITO-MIGRATION-PLAN.md`` §7 and
the file ``core/cognito.py``'s own module docstring points at. Every case here
is a way a token can be forged, replayed, or misdirected, so the matrix is a
security control rather than coverage decoration.

**No AWS calls.** Tokens are signed with an RSA key generated in-process and the
pool's JWKS is injected through a counting fake, exactly as the plan requires
("CI stays offline: tests sign with a locally generated RSA key and inject a
fake JWKS"). The fetch counter is load-bearing in its own right: the verifier
runs on every authenticated request, so an accidental network call per request
would be both a latency tax and a hard dependency on Cognito's control plane.

Cases covered (plan §7 Phase 2 exit gate):
tampered signature · expired · wrong issuer · wrong ``client_id`` ·
``token_use=id`` rejection · unknown ``kid`` · JWKS unavailable ·
missing ``jti`` · missing ``sub`` · algorithm confusion · key substitution ·
JWKS cache reuse, TTL staleness, and single-refetch key rotation.
"""
from __future__ import annotations

import base64
import time
from typing import Any

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jose import jwt

from app.core import cognito
from app.core.cognito import CognitoVerificationError
from app.core.config import settings

POOL_ID = "eu-central-1_testpool"
REGION = "eu-central-1"
CLIENT_ID = "test-client-id"
ISSUER = f"https://cognito-idp.{REGION}.amazonaws.com/{POOL_ID}"

KID = "test-key-1"
ROTATED_KID = "test-key-2"

SUB = "03f4d8e2-3031-700f-4df4-5733a9c5b300"
JTI = "b3d1f0c2-0000-4a1a-9c1e-1a2b3c4d5e6f"


# ---------------------------------------------------------------------------
# Key + token helpers
# ---------------------------------------------------------------------------


def _b64u_uint(value: int) -> str:
    raw = value.to_bytes((value.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


class _KeyPair:
    """An RSA keypair plus its JWKS entry, keyed by a chosen ``kid``."""

    def __init__(self, kid: str) -> None:
        self.kid = kid
        self._key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.pem = self._key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode("ascii")
        numbers = self._key.public_key().public_numbers()
        self.jwk: dict[str, Any] = {
            "kty": "RSA",
            "kid": kid,
            "use": "sig",
            "alg": "RS256",
            "n": _b64u_uint(numbers.n),
            "e": _b64u_uint(numbers.e),
        }


# 2048-bit RSA generation is not free; the pool's signing keys are fixed for the
# life of a test session, so generate each one once.
@pytest.fixture(scope="module")
def signing_key() -> _KeyPair:
    return _KeyPair(KID)


@pytest.fixture(scope="module")
def rotated_key() -> _KeyPair:
    return _KeyPair(ROTATED_KID)


@pytest.fixture(scope="module")
def foreign_key() -> _KeyPair:
    """A different key published under the SAME kid — key-substitution attack."""
    return _KeyPair(KID)


class _Omit:
    """Sentinel: drop a claim entirely rather than setting it to None."""


_OMIT = _Omit()


def make_token(key: _KeyPair, **overrides: Any) -> str:
    """Mint a token shaped like a real Cognito ACCESS token.

    Pass ``claim=_OMIT`` to drop a claim, which is how the "missing required
    claim" cases are built — setting it to ``None`` would test something else.
    """
    now = int(time.time())
    claims: dict[str, Any] = {
        "sub": SUB,
        "iss": ISSUER,
        "client_id": CLIENT_ID,
        "token_use": "access",
        "jti": JTI,
        "iat": now,
        "exp": now + 3600,
        "username": SUB,
        "cognito:groups": ["flowin-admins", "flowin-tier-pro"],
    }
    claims.update(overrides)
    for claim_name in [k for k, v in claims.items() if v is _OMIT]:
        del claims[claim_name]

    return jwt.encode(claims, key.pem, algorithm="RS256", headers={"kid": key.kid})


@pytest.fixture(autouse=True)
def cognito_settings(monkeypatch):
    monkeypatch.setattr(settings, "COGNITO_USER_POOL_ID", POOL_ID)
    monkeypatch.setattr(settings, "COGNITO_CLIENT_ID", CLIENT_ID)
    monkeypatch.setattr(settings, "COGNITO_CLIENT_SECRET", "test-client-secret")
    monkeypatch.setattr(settings, "COGNITO_REGION", REGION)
    monkeypatch.setattr(settings, "COGNITO_JWKS_CACHE_TTL_SECONDS", 3600)


@pytest.fixture(autouse=True)
def clean_jwks_cache():
    """The JWKS cache is module-level state; never leak it between tests."""
    cognito._jwks_cache.replace({})
    cognito._jwks_cache._fetched_at = 0.0
    yield
    cognito._jwks_cache.replace({})
    cognito._jwks_cache._fetched_at = 0.0


class _JwksSpy:
    """Stands in for the network fetch and counts how often it is called."""

    def __init__(self, *keys: _KeyPair) -> None:
        self.keys = {k.kid: k.jwk for k in keys}
        self.calls = 0

    def __call__(self) -> dict[str, dict[str, Any]]:
        self.calls += 1
        return dict(self.keys)


@pytest.fixture
def jwks(monkeypatch, signing_key):
    spy = _JwksSpy(signing_key)
    monkeypatch.setattr(cognito, "_fetch_jwks", spy)
    return spy


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestValidToken:
    def test_returns_typed_principal_with_groups(self, jwks, signing_key):
        principal = cognito.verify_cognito_access_token(make_token(signing_key))

        assert principal.sub == SUB
        assert principal.jti == JTI
        assert principal.client_id == CLIENT_ID
        assert principal.username == SUB
        # The groups claim is what every authorization decision reads (§5.2),
        # so it must survive verification verbatim.
        assert principal.groups == ["flowin-admins", "flowin-tier-pro"]
        assert principal.exp > principal.iat

    def test_absent_groups_claim_yields_an_empty_list(self, jwks, signing_key):
        """A user in no group is legal — and must not be a crash or a None."""
        token = make_token(signing_key, **{"cognito:groups": _OMIT})
        assert cognito.verify_cognito_access_token(token).groups == []

    def test_no_aws_call_is_needed_beyond_the_jwks_fetch(self, jwks, signing_key):
        cognito.verify_cognito_access_token(make_token(signing_key))
        assert jwks.calls == 1


# ---------------------------------------------------------------------------
# Forgery and misdirection
# ---------------------------------------------------------------------------


class TestSignatureIntegrity:
    def test_tampered_signature_is_rejected(self, jwks, signing_key):
        token = make_token(signing_key)
        header, payload, signature = token.split(".")
        # Flip the last character of the signature — the payload still parses,
        # which is exactly why the signature check has to be the gate.
        forged = f"{header}.{payload}.{signature[:-1]}{'A' if signature[-1] != 'A' else 'B'}"

        with pytest.raises(CognitoVerificationError):
            cognito.verify_cognito_access_token(forged)

    def test_tampered_payload_is_rejected(self, jwks, signing_key):
        """Escalating a claim invalidates the signature over it."""
        token = make_token(signing_key)
        header, _payload, signature = token.split(".")
        escalated = jwt.encode(
            {"sub": SUB, "cognito:groups": ["flowin-admins"]},
            signing_key.pem,
            algorithm="RS256",
        ).split(".")[1]

        with pytest.raises(CognitoVerificationError):
            cognito.verify_cognito_access_token(f"{header}.{escalated}.{signature}")

    def test_key_substitution_under_the_same_kid_is_rejected(
        self, monkeypatch, signing_key, foreign_key
    ):
        """An attacker's key published under the pool's kid must not verify.

        The kid is attacker-controlled metadata; only the pool's published JWKS
        decides which key is trusted.
        """
        monkeypatch.setattr(cognito, "_fetch_jwks", _JwksSpy(signing_key))
        token = make_token(foreign_key)  # same kid, different private key

        with pytest.raises(CognitoVerificationError):
            cognito.verify_cognito_access_token(token)

    def test_symmetric_algorithm_is_rejected(self, jwks):
        """Algorithm confusion: an HS256 token must never be accepted.

        The verifier pins ``algorithms=["RS256"]``. Without that pin, a token
        signed with a guessable secret could be presented as if the pool had
        signed it.
        """
        now = int(time.time())
        hs_token = jwt.encode(
            {
                "sub": SUB,
                "iss": ISSUER,
                "client_id": CLIENT_ID,
                "token_use": "access",
                "jti": JTI,
                "iat": now,
                "exp": now + 3600,
            },
            "a-shared-secret",
            algorithm="HS256",
            headers={"kid": KID},
        )

        with pytest.raises(CognitoVerificationError):
            cognito.verify_cognito_access_token(hs_token)


class TestClaimEnforcement:
    def test_expired_token_is_rejected(self, jwks, signing_key):
        now = int(time.time())
        token = make_token(signing_key, iat=now - 7200, exp=now - 3600)

        with pytest.raises(CognitoVerificationError):
            cognito.verify_cognito_access_token(token)

    def test_wrong_issuer_is_rejected(self, jwks, signing_key):
        """A valid token from a DIFFERENT pool must not authenticate here.

        Closes audit finding C1 (no `iss` enforcement on the legacy path): the
        signature alone proves only that *some* pool minted it.
        """
        other_pool = f"https://cognito-idp.{REGION}.amazonaws.com/{REGION}_otherpool"
        token = make_token(signing_key, iss=other_pool)

        with pytest.raises(CognitoVerificationError):
            cognito.verify_cognito_access_token(token)

    def test_wrong_client_id_is_rejected(self, jwks, signing_key):
        """Access tokens carry no `aud`, so client_id IS the audience check."""
        token = make_token(signing_key, client_id="some-other-app-client")

        with pytest.raises(CognitoVerificationError):
            cognito.verify_cognito_access_token(token)

    def test_missing_client_id_is_rejected(self, jwks, signing_key):
        token = make_token(signing_key, client_id=_OMIT)

        with pytest.raises(CognitoVerificationError):
            cognito.verify_cognito_access_token(token)

    def test_id_token_is_rejected_on_the_access_token_path(self, jwks, signing_key):
        """`token_use` must be `access`.

        An ID token is signed by the same pool and would otherwise verify, but
        it is minted for a different purpose and carries different claims —
        accepting one here is the impersonation risk AWS warns about.
        """
        token = make_token(signing_key, token_use="id")

        with pytest.raises(CognitoVerificationError):
            cognito.verify_cognito_access_token(token)

    def test_missing_jti_is_rejected(self, jwks, signing_key):
        """No jti means the token cannot be entered in the revocation denylist.

        Since Cognito cannot revoke an already-issued access token (plan R3),
        the per-jti denylist is the only per-token revocation that exists.
        """
        token = make_token(signing_key, jti=_OMIT)

        with pytest.raises(CognitoVerificationError):
            cognito.verify_cognito_access_token(token)

    def test_missing_sub_is_rejected(self, jwks, signing_key):
        """`sub` is the only mapping to a local `users` row."""
        token = make_token(signing_key, sub=_OMIT)

        with pytest.raises(CognitoVerificationError):
            cognito.verify_cognito_access_token(token)


class TestMalformedInput:
    @pytest.mark.parametrize(
        "token",
        ["", "not-a-jwt", "a.b", "a.b.c", "....", "Bearer eyJhbGciOiJSUzI1NiJ9.e30.x"],
    )
    def test_garbage_never_raises_a_raw_jose_error(self, jwks, token):
        """The verifier's contract is CognitoVerificationError, nothing else.

        A leaking JOSEError/httpx error would escape the 401 mapping in
        core/dependencies.py and surface as a 500.
        """
        with pytest.raises(CognitoVerificationError):
            cognito.verify_cognito_access_token(token)

    def test_header_without_kid_is_rejected(self, jwks, signing_key):
        token = jwt.encode({"sub": SUB}, signing_key.pem, algorithm="RS256")

        with pytest.raises(CognitoVerificationError):
            cognito.verify_cognito_access_token(token)


# ---------------------------------------------------------------------------
# JWKS cache behaviour
# ---------------------------------------------------------------------------


class TestJwksCache:
    def test_second_verification_reuses_the_cache(self, jwks, signing_key):
        """One fetch per TTL, not one per request."""
        token = make_token(signing_key)
        cognito.verify_cognito_access_token(token)
        cognito.verify_cognito_access_token(token)
        cognito.verify_cognito_access_token(token)

        assert jwks.calls == 1

    def test_stale_cache_is_refetched(self, jwks, signing_key):
        """Past the TTL, the keys are re-read rather than trusted forever.

        Staleness is forced by ageing the cache's own timestamp instead of
        setting the TTL to 0 and racing the clock: `is_stale` uses a strict
        `>` against `time.monotonic()`, whose resolution on some platforms is
        coarse enough (~15ms on Windows) that two back-to-back calls can land
        in the same tick and read as "not stale" — a flake that would only ever
        show up in a full-suite run.
        """
        token = make_token(signing_key)
        cognito.verify_cognito_access_token(token)
        assert jwks.calls == 1

        cognito._jwks_cache._fetched_at -= settings.COGNITO_JWKS_CACHE_TTL_SECONDS + 1
        cognito.verify_cognito_access_token(token)

        assert jwks.calls == 2

    def test_unknown_kid_triggers_exactly_one_refetch_then_succeeds(
        self, monkeypatch, signing_key, rotated_key
    ):
        """Key rotation must self-heal without a restart.

        The cache is warm with the old key; a token signed by the pool's NEW
        key arrives; one refetch picks it up.
        """
        spy = _JwksSpy(signing_key)
        monkeypatch.setattr(cognito, "_fetch_jwks", spy)
        cognito.verify_cognito_access_token(make_token(signing_key))
        assert spy.calls == 1

        spy.keys[rotated_key.kid] = rotated_key.jwk  # pool rotates
        principal = cognito.verify_cognito_access_token(make_token(rotated_key))

        assert principal.sub == SUB
        assert spy.calls == 2

    def test_unknown_kid_that_stays_unknown_is_rejected_after_one_refetch(
        self, monkeypatch, signing_key, rotated_key
    ):
        """A bad-kid flood must not hammer the JWKS endpoint per request."""
        spy = _JwksSpy(signing_key)
        monkeypatch.setattr(cognito, "_fetch_jwks", spy)

        with pytest.raises(CognitoVerificationError):
            cognito.verify_cognito_access_token(make_token(rotated_key))

        assert spy.calls == 1

    def test_jwks_unavailable_fails_closed(self, monkeypatch, signing_key):
        """No JWKS, no authentication — never accept an unverifiable token.

        This is the R6 failure mode: a JWKS outage must degrade to "nobody can
        log in", not "everybody is trusted".
        """

        def exploding_fetch() -> dict[str, dict[str, Any]]:
            raise CognitoVerificationError("JWKS unavailable: boom")

        monkeypatch.setattr(cognito, "_fetch_jwks", exploding_fetch)

        with pytest.raises(CognitoVerificationError):
            cognito.verify_cognito_access_token(make_token(signing_key))
