"""QA-KB-108 analyzer probe 3: the /api/admin/* lifecycle routes, offline and hermetic.

Which admin routes translate cognito_admin.ProviderUnavailableError into a 503 today, and what
does each do with a botocore BotoCoreError?  require_admin and get_db are overridden, every
Cognito wrapper is patched; nothing touches the network or a database.

Run from backend/:  PYTHONPATH=. .venv/bin/python <this file>
"""
from types import SimpleNamespace
from unittest import mock

from botocore.exceptions import ClientError, TokenRetrievalError
from fastapi.testclient import TestClient

from app.main import app
import app.api.admin as admin_api
import app.core.cognito as cog
from app.core import cognito_admin
from app.models.database import get_db

ORIGIN = {"Origin": "http://localhost:3000"}


def expired_sso():
    return TokenRetrievalError(provider="sso", error_msg="Token has expired and refresh failed")


def provider_5xx():
    return ClientError({"Error": {"Code": "InternalErrorException", "Message": "x"}}, "Op")


TARGET = SimpleNamespace(
    id="target-1", email="target@example.com", status="active", is_admin=False, tier="basic",
    cognito_sub="sub-target", tokens_valid_from=None, encrypted_cognito_refresh_token=None,
)


class FakeDB:
    def query(self, *a, **k): return self
    def filter(self, *a, **k): return self
    def first(self): return TARGET
    def commit(self): pass
    def rollback(self): pass
    def refresh(self, *a, **k): pass
    def add(self, *a, **k): pass


app.dependency_overrides[admin_api.require_admin] = lambda: SimpleNamespace(id="admin-1", email="admin@example.com", is_admin=True)
app.dependency_overrides[get_db] = lambda: FakeDB()
client = TestClient(app, raise_server_exceptions=False)


def show(label, r):
    print(f"{label:58s} status={r.status_code} ACAO={r.headers.get('access-control-allow-origin')!r:26} body={r.text[:78]!r}")


routes = [
    ("PATCH  /users/{id}/tier   ", "patch", "/api/admin/users/target-1/tier", {"tier": "pro"}, "admin_list_groups_for_user"),
    ("PATCH  /users/{id}/role   ", "patch", "/api/admin/users/target-1/role", {"is_admin": True}, "admin_add_user_to_group"),
    ("POST   /users/{id}/reset-password", "post", "/api/admin/users/target-1/reset-password", {}, "admin_user_global_sign_out"),
    ("POST   /users/{id}/disable", "post", "/api/admin/users/target-1/disable", None, "admin_user_global_sign_out"),
    ("DELETE /users/{id}        ", "delete", "/api/admin/users/target-1", None, "admin_user_global_sign_out"),
]
with mock.patch.object(cognito_admin, "is_last_admin", return_value=False):
    for label, verb, path, body, wrapper in routes:
        for kind, make in (("ClientError control   ", provider_5xx), ("TokenRetrievalError    ", expired_sso)):
            with mock.patch.object(cog, wrapper, side_effect=make()):
                kwargs = {"headers": ORIGIN}
                if body is not None:
                    kwargs["json"] = body
                show(f"{label} {kind}", getattr(client, verb)(path, **kwargs))
