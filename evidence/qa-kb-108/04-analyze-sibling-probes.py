"""QA-KB-108 analyzer probes: offline, hermetic (DB stubbed, every Cognito function patched).

Run from backend/:  .venv/bin/python <this file>
Each probe patches the Cognito wrapper the endpoint calls so it raises a botocore
exception, POSTs with an Origin header, and prints status + access-control-allow-origin.
No network call is made; no backend restart; nothing is written.
"""
from types import SimpleNamespace
from unittest import mock

from botocore.exceptions import ClientError, EndpointConnectionError, TokenRetrievalError
from fastapi.testclient import TestClient

from app.main import app
import app.api.auth as a
import app.core.cognito as cog
from app.core import cognito_admin
from app.core.dependencies import get_current_user_for_refresh, get_current_user_with_payload
from app.models.database import get_db

ORIGIN = {"Origin": "http://localhost:3000"}
BEARER = {"Origin": "http://localhost:3000", "Authorization": "Bearer probe-token"}


def expired_sso():
    return TokenRetrievalError(provider="sso", error_msg="Token has expired and refresh failed")


def unreachable():
    return EndpointConnectionError(endpoint_url="https://cognito-idp.eu-west-1.amazonaws.com/")


def provider_5xx():
    return ClientError({"Error": {"Code": "InternalErrorException", "Message": "x"}}, "Op")


class FakeDB:
    def query(self, *a, **k): return self
    def filter(self, *a, **k): return self
    def first(self): return None
    def commit(self): pass
    def rollback(self): pass
    def add(self, *a, **k): pass


USER = SimpleNamespace(
    id="u-probe", email="probe@example.com", cognito_sub="sub-probe", is_admin=False,
    tier="basic", encrypted_cognito_refresh_token="ciphertext", tokens_valid_from=None,
)
PAYLOAD = {"sub": "sub-probe", "jti": "j", "iat": 1, "exp": 9999999999, "groups": []}

app.dependency_overrides[get_db] = lambda: FakeDB()
app.dependency_overrides[get_current_user_with_payload] = lambda: (USER, PAYLOAD)
app.dependency_overrides[get_current_user_for_refresh] = lambda: (USER, PAYLOAD)
client = TestClient(app, raise_server_exceptions=False)


def show(label, r):
    print(f"{label:62s} status={r.status_code} ACAO={r.headers.get('access-control-allow-origin')!r:26} body={r.text[:70]!r}")


print("== A. /login/challenge : AdminRespondToAuthChallenge (signed op)")
body = {"email": "probe@example.com", "session": "s", "challenge": "NEW_PASSWORD_REQUIRED", "new_password": "Aa1!aaaaaaaaaaaa"}
with mock.patch.object(a.cognito, "admin_respond_to_auth_challenge", side_effect=expired_sso()):
    show("TokenRetrievalError (expired SSO)", client.post("/api/auth/login/challenge", json=body, headers=ORIGIN))
with mock.patch.object(a.cognito, "admin_respond_to_auth_challenge", side_effect=provider_5xx()):
    show("control: ClientError InternalErrorException", client.post("/api/auth/login/challenge", json=body, headers=ORIGIN))

print("== B. /refresh : AdminInitiateAuth REFRESH_TOKEN_AUTH (signed op)")
with mock.patch.object(a, "decrypt_cognito_refresh_token", return_value="rt"):
    with mock.patch.object(a.cognito, "refresh_auth", side_effect=expired_sso()):
        show("TokenRetrievalError (expired SSO)", client.post("/api/auth/refresh", headers=BEARER))
    with mock.patch.object(a.cognito, "refresh_auth", side_effect=provider_5xx()):
        show("control: ClientError InternalErrorException", client.post("/api/auth/refresh", headers=BEARER))

print("== C. MFA writes : apply_mfa_preference pre-reads AdminGetUser (signed op)")
with mock.patch.object(a.cognito, "verify_software_token", return_value="SUCCESS"):
    with mock.patch.object(cog, "admin_get_user", side_effect=expired_sso()):
        show("POST /mfa/totp/verify   TokenRetrievalError", client.post("/api/auth/mfa/totp/verify", json={"code": "123456"}, headers=BEARER))
    with mock.patch.object(cog, "admin_get_user", side_effect=provider_5xx()):
        show("POST /mfa/totp/verify   control ClientError", client.post("/api/auth/mfa/totp/verify", json={"code": "123456"}, headers=BEARER))
with mock.patch.object(a.settings, "AUTH_EMAIL_MFA_ENABLED", True):
    with mock.patch.object(cog, "admin_get_user", side_effect=expired_sso()):
        show("POST /mfa/email/enable  TokenRetrievalError", client.post("/api/auth/mfa/email/enable", headers=BEARER))
    with mock.patch.object(cog, "admin_get_user", side_effect=provider_5xx()):
        show("POST /mfa/email/enable  control ClientError", client.post("/api/auth/mfa/email/enable", headers=BEARER))
with mock.patch.object(cog, "admin_get_user", side_effect=expired_sso()):
    show("POST /mfa/email/disable TokenRetrievalError", client.post("/api/auth/mfa/email/disable", headers=BEARER))
with mock.patch.object(cog, "admin_get_user", side_effect=provider_5xx()):
    show("POST /mfa/email/disable control ClientError", client.post("/api/auth/mfa/email/disable", headers=BEARER))
with mock.patch.object(cog, "admin_get_user", side_effect=expired_sso()):
    show("GET  /mfa (already `except Exception`) TokenRetrievalError", client.get("/api/auth/mfa", headers=BEARER))

print("== D. network-only endpoints (unsigned ops): EndpointConnectionError")
with mock.patch.object(a.settings, "AUTH_EMAIL_MFA_ENABLED", False):
    with mock.patch.object(a.cognito, "forgot_password", side_effect=unreachable()):
        show("POST /forgot-password         EndpointConnectionError", client.post("/api/auth/forgot-password", json={"email": "probe@example.com"}, headers=ORIGIN))
    with mock.patch.object(a.cognito, "forgot_password", side_effect=provider_5xx()):
        show("POST /forgot-password         control ClientError", client.post("/api/auth/forgot-password", json={"email": "probe@example.com"}, headers=ORIGIN))
    with mock.patch.object(a.cognito, "confirm_forgot_password", side_effect=unreachable()):
        show("POST /forgot-password/confirm EndpointConnectionError", client.post("/api/auth/forgot-password/confirm", json={"email": "probe@example.com", "code": "1", "new_password": "x"}, headers=ORIGIN))
with mock.patch.object(a.cognito, "change_password", side_effect=unreachable()):
    show("POST /change-password         EndpointConnectionError", client.post("/api/auth/change-password", json={"current_password": "a", "new_password": "b"}, headers=BEARER))
with mock.patch.object(a.cognito, "change_password", side_effect=provider_5xx()):
    show("POST /change-password         control ClientError", client.post("/api/auth/change-password", json={"current_password": "a", "new_password": "b"}, headers=BEARER))
with mock.patch.object(a.cognito, "associate_software_token", side_effect=unreachable()):
    show("POST /mfa/totp/associate      EndpointConnectionError", client.post("/api/auth/mfa/totp/associate", headers=BEARER))

print("== E. admin lifecycle layer (core/cognito_admin.py): which exception reaches the route layer?")
def attempt(label, fn):
    try:
        fn()
        print(f"{label:62s} returned normally")
    except Exception as exc:  # noqa: BLE001
        print(f"{label:62s} raised {type(exc).__module__}.{type(exc).__name__}")

adm = SimpleNamespace(email="probe@example.com", is_admin=True, tier="basic", tokens_valid_from=None)
with mock.patch.object(cog, "admin_list_groups_for_user", side_effect=expired_sso()):
    attempt("is_last_admin       (TokenRetrievalError)", lambda: cognito_admin.is_last_admin(adm))
    attempt("change_tier         (TokenRetrievalError)", lambda: cognito_admin.change_tier(adm, "pro", FakeDB()))
with mock.patch.object(cog, "admin_list_groups_for_user", side_effect=provider_5xx()):
    attempt("change_tier         control (ClientError)", lambda: cognito_admin.change_tier(adm, "pro", FakeDB()))
with mock.patch.object(cog, "admin_create_user", side_effect=expired_sso()):
    attempt("invite_user         (TokenRetrievalError)", lambda: cognito_admin.invite_user("new@example.com", tier="basic", is_admin=False))
with mock.patch.object(cog, "admin_create_user", side_effect=provider_5xx()):
    attempt("invite_user         control (ClientError)", lambda: cognito_admin.invite_user("new@example.com", tier="basic", is_admin=False))
with mock.patch.object(cog, "admin_disable_user", side_effect=expired_sso()), mock.patch.object(cog, "admin_user_global_sign_out", return_value=None):
    attempt("disable_user        (TokenRetrievalError)", lambda: cognito_admin.disable_user(SimpleNamespace(id="u", email="probe@example.com", tokens_valid_from=None, status="active", encrypted_cognito_refresh_token=None, is_admin=False), FakeDB()))

import app.api.admin as admin_api
try:
    admin_api._raise_for(expired_sso())
except Exception as exc:  # noqa: BLE001
    print(f"{'api/admin.py::_raise_for(TokenRetrievalError)':62s} re-raised {type(exc).__name__} UNCHANGED (docstring: 'never swallows or reshapes')")
