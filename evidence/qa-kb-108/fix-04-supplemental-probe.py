"""QA-KB-108 fixer probe: the post-fix cases probes 04 and 08 do not reach. Offline, hermetic.

Run from backend/:  PYTHONPATH=. .venv/bin/python ../evidence/qa-kb-108/fix-04-supplemental-probe.py
Every Cognito wrapper on each path is patched (including list_users_in_group, which probe 04
leaves unpatched); DB stubbed; no network, nothing written.
"""
from types import SimpleNamespace
from unittest import mock

from botocore.exceptions import (
    ClientError,
    EndpointConnectionError,
    NoCredentialsError,
    TokenRetrievalError,
)
from fastapi.testclient import TestClient

import app.api.auth as a
import app.core.cognito as cog
from app.core import cognito_admin
from app.core.dependencies import get_current_user_for_refresh, get_current_user_with_payload
from app.main import app
from app.models.database import get_db

ORIGIN = {"Origin": "http://localhost:3000"}
BEARER = {"Origin": "http://localhost:3000", "Authorization": "Bearer probe-token"}


def expired_sso():
    return TokenRetrievalError(provider="sso", error_msg="Token has expired and refresh failed")


def client_error(code):
    return ClientError({"Error": {"Code": code, "Message": "x"}}, "Op")


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
    print(f"{label:58s} status={r.status_code} ACAO={r.headers.get('access-control-allow-origin')!r:26} body={r.text[:70]!r}")


def attempt(label, fn):
    try:
        print(f"{label:58s} returned {fn()!r}")
    except Exception as exc:  # noqa: BLE001
        print(f"{label:58s} raised {type(exc).__name__}(code={getattr(exc, 'code', None)!r})")


print("== F. ISS-1150 safety net on the REAL app (throwaway routes, removed afterwards)")
n_routes = len(app.router.routes)


@app.get("/__probe/boto")
def _boto():
    raise expired_sso()


@app.get("/__probe/runtime")
def _runtime():
    raise RuntimeError("not a botocore error")


show("GET route raising TokenRetrievalError", client.get("/__probe/boto", headers=ORIGIN))
show("GET route raising RuntimeError (scope control)", client.get("/__probe/runtime", headers=ORIGIN))
del app.router.routes[n_routes:]

print("== G. ISS-1144 login: the other BotoCoreError members")
body = {"email": "probe@example.com", "password": "Whatever1!aaaa"}
for label, exc in (
    ("NoCredentialsError", NoCredentialsError()),
    ("EndpointConnectionError", EndpointConnectionError(endpoint_url="https://cognito-idp.eu-west-1.amazonaws.com/")),
):
    with mock.patch.object(a.cognito, "admin_initiate_auth", side_effect=exc):
        show(f"POST /login {label}", client.post("/api/auth/login", json=body, headers=ORIGIN))

print("== H. ISS-1146 trap: /refresh outage must not reconcile the account to disabled")
with mock.patch.object(a, "decrypt_cognito_refresh_token", return_value="rt"), \
        mock.patch.object(a, "_reconcile_status_on_refresh_rejection") as reconcile:
    with mock.patch.object(a.cognito, "refresh_auth", side_effect=expired_sso()):
        show("POST /refresh TokenRetrievalError", client.post("/api/auth/refresh", headers=BEARER))
    print(f"{'  _reconcile_status_on_refresh_rejection called':58s} {reconcile.called}")
    with mock.patch.object(a.cognito, "refresh_auth", side_effect=client_error("NotAuthorizedException")):
        show("POST /refresh control NotAuthorizedException", client.post("/api/auth/refresh", headers=BEARER))
    print(f"{'  _reconcile_status_on_refresh_rejection called':58s} {reconcile.called}")

print("== I. ISS-1147 control: a wrong TOTP code stays 400")
with mock.patch.object(a.cognito, "verify_software_token", side_effect=client_error("CodeMismatchException")):
    show("POST /mfa/totp/verify CodeMismatchException", client.post("/api/auth/mfa/totp/verify", json={"code": "1"}, headers=BEARER))

print("== J. ISS-1148 lifecycle layer, every wrapper on the path patched")
admin_row = SimpleNamespace(email="probe@example.com", is_admin=True)
plain_row = SimpleNamespace(email="probe@example.com", is_admin=False)
with mock.patch.object(cog, "admin_list_groups_for_user", side_effect=expired_sso()), \
        mock.patch.object(cog, "list_users_in_group", side_effect=expired_sso()):
    attempt("is_last_admin, local is_admin=True, both reads fail", lambda: cognito_admin.is_last_admin(admin_row))
    attempt("is_last_admin, local is_admin=False (degrade)", lambda: cognito_admin.is_last_admin(plain_row))
with mock.patch.object(cog, "admin_list_groups_for_user", side_effect=expired_sso()), \
        mock.patch.object(cog, "list_users_in_group", return_value=[{"Username": "a"}, {"Username": "b"}]):
    attempt("is_last_admin, first read fails, local admin, 2 members", lambda: cognito_admin.is_last_admin(admin_row))
with mock.patch.object(cog, "admin_delete_user", side_effect=expired_sso()):
    attempt("try_delete_pool_user (retry code, never raises)", lambda: cognito_admin.try_delete_pool_user("probe@example.com"))
with mock.patch.object(cog, "admin_enable_user", side_effect=expired_sso()):
    attempt("enable_user", lambda: cognito_admin.enable_user(SimpleNamespace(email="probe@example.com", status="disabled", id="u"), FakeDB()))
with mock.patch.object(cog, "admin_user_global_sign_out", return_value=None), \
        mock.patch.object(cog, "admin_set_user_password", side_effect=expired_sso()):
    attempt("reset_password (set-password step)", lambda: cognito_admin.reset_password(FakeDB(), SimpleNamespace(email="probe@example.com", tokens_valid_from=None, id="u")))
with mock.patch.object(cog, "admin_create_user", return_value={"User": {"Attributes": [{"Name": "sub", "Value": "s"}]}}), \
        mock.patch.object(cog, "admin_add_user_to_group", side_effect=expired_sso()), \
        mock.patch.object(cog, "admin_delete_user", return_value=None) as compensate:
    attempt("invite_user, group step fails (compensation path)", lambda: cognito_admin.invite_user("new@example.com", tier="basic", is_admin=False))
    print(f"{'  compensating AdminDeleteUser called':58s} {compensate.called}")
