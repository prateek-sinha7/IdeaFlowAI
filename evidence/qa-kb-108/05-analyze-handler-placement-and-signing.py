"""QA-KB-108 analyzer probes, part 2. Standalone: imports no application code except llm_errors.

1. Where a global handler must be registered for the 503 to carry CORS headers.
   A throwaway FastAPI app mirrors app/main.py's middleware order (CORSMiddleware added
   first, then two @app.middleware("http") layers added after it, so they sit OUTSIDE it).
2. Which Cognito operations need AWS credentials. Hermetic: no credentials anywhere, the
   endpoint is a closed localhost port, so nothing leaves the machine.
3. What llm_errors.map_exception makes of the SSO-expiry exception (adjacent lead).

Run from backend/:  PYTHONPATH=. .venv/bin/python <this file>
"""
import os

# --- 2 needs a credential-free process: set BEFORE botocore reads its config -----------------
for var in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN", "AWS_PROFILE",
            "AWS_BEARER_TOKEN_BEDROCK", "AWS_CONTAINER_CREDENTIALS_RELATIVE_URI"):
    os.environ.pop(var, None)
os.environ["AWS_CONFIG_FILE"] = "/dev/null"
os.environ["AWS_SHARED_CREDENTIALS_FILE"] = "/dev/null"
os.environ["AWS_EC2_METADATA_DISABLED"] = "true"

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, TokenRetrievalError
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

ORIGIN = {"Origin": "http://localhost:3000"}


def build(handler_key):
    app = FastAPI()
    app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3000"], allow_credentials=True,
                       allow_methods=["*"], allow_headers=["*"])

    @app.middleware("http")
    async def _request_id(request, call_next):
        return await call_next(request)

    @app.middleware("http")
    async def _slow(request, call_next):
        return await call_next(request)

    @app.get("/boom")
    def boom():
        raise TokenRetrievalError(provider="sso", error_msg="Token has expired and refresh failed")

    if handler_key is not None:
        @app.exception_handler(handler_key)
        async def _h(request, exc):
            return JSONResponse({"detail": "Authentication service unavailable"}, status_code=503)
    return app


print("== 1. global handler registration key vs CORS headers on the 503")
for label, key in (("no handler (today's main.py)", None),
                   ("@app.exception_handler(Exception)", Exception),
                   ("@app.exception_handler(500)", 500),
                   ("@app.exception_handler(BotoCoreError)", BotoCoreError)):
    r = TestClient(build(key), raise_server_exceptions=False).get("/boom", headers=ORIGIN)
    print(f"{label:42s} status={r.status_code} ACAO={r.headers.get('access-control-allow-origin')!r:26} body={r.text[:60]!r}")

print("== 2. which Cognito operations need credentials (no creds in this process, endpoint = closed localhost port)")
client = boto3.session.Session().client(
    "cognito-idp", region_name="eu-west-1", endpoint_url="http://127.0.0.1:9",
    config=Config(retries={"max_attempts": 1}, connect_timeout=2, read_timeout=2),
)
calls = {
    "admin_get_user (signed)":              lambda: client.admin_get_user(UserPoolId="eu-west-1_x", Username="u"),
    "admin_initiate_auth (signed)":         lambda: client.admin_initiate_auth(UserPoolId="eu-west-1_x", ClientId="c", AuthFlow="ADMIN_USER_PASSWORD_AUTH", AuthParameters={}),
    "admin_respond_to_auth_challenge (signed)": lambda: client.admin_respond_to_auth_challenge(UserPoolId="eu-west-1_x", ClientId="c", ChallengeName="NEW_PASSWORD_REQUIRED", Session="s" * 30, ChallengeResponses={}),
    "change_password (noAuth)":             lambda: client.change_password(PreviousPassword="a", ProposedPassword="b", AccessToken="t"),
    "forgot_password (noAuth)":             lambda: client.forgot_password(ClientId="c", Username="u"),
    "associate_software_token (noAuth)":    lambda: client.associate_software_token(AccessToken="t"),
    "set_user_mfa_preference (noAuth)":     lambda: client.set_user_mfa_preference(AccessToken="t"),
}
for label, fn in calls.items():
    try:
        fn()
        outcome = "returned"
    except Exception as exc:  # noqa: BLE001
        outcome = f"{type(exc).__name__}"
    print(f"{label:44s} -> {outcome}")

print("== 3. app.agents.llm_errors.map_exception on the SSO-expiry exception")
from app.agents.llm_errors import map_exception
for exc in (TokenRetrievalError(provider="sso", error_msg="Token has expired and refresh failed"),):
    print(f"{type(exc).__name__:44s} -> {map_exception(exc)}")
