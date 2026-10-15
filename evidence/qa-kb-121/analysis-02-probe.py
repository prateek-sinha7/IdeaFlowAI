"""QA-KB-121 analysis probe 2. Offline. Other providers' key-rejection strings -> the real sanitizer."""
import ast
from pathlib import Path

REPO = Path("/Users/bilala/Developer/Projects/VELOCITY-AI-worktrees/feat-user-stories-v2")
ENGINE = REPO / "backend/agents/execution_engine/engine.py"
WANTED = {"_GENERIC_AGENT_ERROR_MESSAGE", "_THROTTLED_AGENT_ERROR", "_CREDENTIAL_AGENT_ERROR",
          "_UNAVAILABLE_AGENT_ERROR", "_TIMEOUT_AGENT_ERROR", "_AGENT_ERROR_CATEGORIES"}
picked = []
for node in ast.parse(ENGINE.read_text()).body:
    if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in WANTED for t in node.targets):
        picked.append(node)
    elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id in WANTED:
        picked.append(node)
    elif isinstance(node, ast.FunctionDef) and node.name == "_sanitize_agent_error":
        picked.append(node)
ns: dict = {}
exec(compile(ast.Module(body=picked, type_ignores=[]), str(ENGINE), "exec"), ns)
sanitize, CRED, GENERIC = ns["_sanitize_agent_error"], ns["_CREDENTIAL_AGENT_ERROR"], ns["_GENERIC_AGENT_ERROR_MESSAGE"]

import httpx  # noqa: E402
import anthropic  # noqa: E402

print("anthropic", anthropic.__version__, "| httpx", httpx.__version__)


def label(msg):
    return "CREDENTIAL(cloud-session copy)" if msg == CRED else ("GENERIC 'rejected this request'" if msg == GENERIC else "other: " + msg)


# --- Anthropic: what the SDK itself builds for a 401 on a revoked key -------------------
req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
resp = httpx.Response(401, request=req, json={"type": "error", "error": {"type": "authentication_error", "message": "invalid x-api-key"}})
body = resp.json()
client = anthropic.Anthropic(api_key="sk-probe-not-a-real-key")
exc = client._make_status_error_from_response(resp)  # the SDK's own constructor path for a non-2xx response
print("-" * 100)
print("Anthropic revoked/invalid ANTHROPIC_API_KEY (401)")
print("  type:", type(exc).__name__, "| status_code:", exc.status_code)
print("  str(exc):", str(exc)[:300])
print("  engine _sanitize_agent_error ->", label(sanitize(str(exc)[:500])))

# --- Mistral: langchain_mistralai surfaces httpx.HTTPStatusError ------------------------
mreq = httpx.Request("POST", "https://api.mistral.ai/v1/chat/completions")
mresp = httpx.Response(401, request=mreq, json={"message": "Unauthorized", "request_id": "x"})
try:
    mresp.raise_for_status()
except httpx.HTTPStatusError as e:
    print("-" * 100)
    print("Mistral invalid MISTRAL_API_KEY (401)")
    print("  type:", type(e).__name__)
    print("  str(exc):", str(e)[:200].replace("\n", " | "))
    print("  engine _sanitize_agent_error ->", label(sanitize(str(e)[:500])))
