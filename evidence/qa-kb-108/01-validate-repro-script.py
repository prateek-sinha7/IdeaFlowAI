import sys
from unittest import mock
from botocore.exceptions import TokenRetrievalError
from fastapi.testclient import TestClient
from app.main import app
import app.api.auth as a
c = TestClient(app, raise_server_exceptions=False)
with mock.patch.object(a.cognito,"admin_initiate_auth",side_effect=TokenRetrievalError(provider="sso",error_msg="Token has expired and refresh failed")):
    r = c.post("/api/auth/login", json={"email":"admin@velocity.ai","password":"x"}, headers={"Origin":"http://localhost:3000"})
print(r.status_code, r.headers.get("access-control-allow-origin"), r.text[:80])
