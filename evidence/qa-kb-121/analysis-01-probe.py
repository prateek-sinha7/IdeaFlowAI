"""QA-KB-121 analysis probe. Offline, read-only, no network, no engine import.

1. Pulls the REAL sanitizer source out of engine.py with ast (the constants and
   _sanitize_agent_error) and execs only that, so the result is what the app would say.
2. Builds the botocore ClientError a rejected Bedrock bearer token could raise, in the
   two wire shapes botocore's rest-json parser can produce, using the installed botocore.
3. Runs every shape through the sanitizer and through llm_errors.map_exception.
"""
import ast
import importlib.util
import sys
from pathlib import Path

REPO = Path("/Users/bilala/Developer/Projects/VELOCITY-AI-worktrees/feat-user-stories-v2")
ENGINE = REPO / "backend/agents/execution_engine/engine.py"

WANTED_NAMES = {
    "_GENERIC_AGENT_ERROR_MESSAGE",
    "_THROTTLED_AGENT_ERROR",
    "_CREDENTIAL_AGENT_ERROR",
    "_UNAVAILABLE_AGENT_ERROR",
    "_TIMEOUT_AGENT_ERROR",
    "_AGENT_ERROR_CATEGORIES",
}

tree = ast.parse(ENGINE.read_text())
picked = []
for node in tree.body:
    if isinstance(node, ast.Assign) and any(
        isinstance(t, ast.Name) and t.id in WANTED_NAMES for t in node.targets
    ):
        picked.append(node)
    elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id in WANTED_NAMES:
        picked.append(node)
    elif isinstance(node, ast.FunctionDef) and node.name == "_sanitize_agent_error":
        picked.append(node)
        sanitizer_lineno = node.lineno

ns: dict = {}
exec(compile(ast.Module(body=picked, type_ignores=[]), str(ENGINE), "exec"), ns)
sanitize = ns["_sanitize_agent_error"]
CRED = ns["_CREDENTIAL_AGENT_ERROR"]
GENERIC = ns["_GENERIC_AGENT_ERROR_MESSAGE"]
print(f"sanitizer extracted from {ENGINE.relative_to(REPO)} (def at line {sanitizer_lineno})")
print()

# ---- build the exception strings with the installed botocore ---------------------------
from botocore import parsers  # noqa: E402
from botocore.exceptions import ClientError  # noqa: E402
import botocore  # noqa: E402

print("botocore", botocore.__version__)


def client_error(status, headers, body, op="ConverseStream"):
    parser = parsers.RestJSONParser()
    parsed = parser.parse(
        {"status_code": status, "headers": headers, "body": body}, None
    )
    return ClientError(parsed, op)


cases = {
    # Shape A: Bedrock names the error in x-amzn-ErrorType (what the A4 incident text shows)
    "A  403 + x-amzn-ErrorType: AccessDeniedException, message 'API Key invalid'": client_error(
        403, {"x-amzn-errortype": "AccessDeniedException:http://internal.amazon.com/coral/"},
        b'{"Message":"API Key invalid"}'),
    # Shape B: no error-type header and no code in the body -> botocore falls back to the status
    "B  403, no error-type header, message 'API Key invalid'": client_error(
        403, {}, b'{"message":"API Key invalid"}'),
    # Controls (existing behaviour that must not move)
    "C  ExpiredTokenException (existing credential bucket)": client_error(
        403, {"x-amzn-errortype": "ExpiredTokenException"}, b'{"message":"The security token included in the request is expired"}'),
    "D  A4 incident text, AccessDenied 'Authentication failed for the request.'": client_error(
        403, {"x-amzn-errortype": "AccessDeniedException"}, b'{"message":"Authentication failed for the request."}',
        op="InvokeModelWithResponseStream"),
    "E  mid-run bearer expiry wording 'Bearer Token has expired' (wording from memory, INFERRED)": client_error(
        403, {"x-amzn-errortype": "AccessDeniedException"}, b'{"message":"Bearer Token has expired"}'),
    "F  Shape B variant: code 'AccessDenied' (no Exception suffix)": client_error(
        403, {"x-amzn-errortype": "AccessDenied"}, b'{"message":"API Key invalid"}'),
}

# ---- llm_errors.map_exception, loaded by path so app/agents/__init__ is not imported ----
spec = importlib.util.spec_from_file_location("llm_errors_probe", REPO / "backend/app/agents/llm_errors.py")
llm_errors = importlib.util.module_from_spec(spec)
sys.modules["llm_errors_probe"] = llm_errors
spec.loader.exec_module(llm_errors)

for label, exc in cases.items():
    raw = str(exc)[:500]
    msg = sanitize(raw)
    kind = "CREDENTIAL(cloud-session copy)" if msg == CRED else ("GENERIC 'rejected this request'" if msg == GENERIC else "other")
    chat = llm_errors.map_exception(exc)
    print("-" * 100)
    print(label)
    print("  code in ClientError.response :", exc.response.get("Error", {}).get("Code"))
    print("  str(exc) (what the runner yields):", raw)
    print("  engine _sanitize_agent_error  ->", kind)
    print("     user sees:", msg)
    print("  chat llm_errors.map_exception ->", chat.code, "| recoverable =", chat.recoverable)
    print("     user sees:", chat.message)
