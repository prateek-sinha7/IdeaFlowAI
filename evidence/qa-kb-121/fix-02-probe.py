import re
from agents.execution_engine.engine import (
    _sanitize_agent_error, _CREDENTIAL_AGENT_ERROR, _GENERIC_AGENT_ERROR_MESSAGE,
    _INVALID_KEY_AGENT_ERROR, _CREDENTIAL_AGENT_ERRORS, TRANSIENT_AGENT_ERRORS,
)
gate = re.compile(r"security.*gate|blocked.*security|exec.*denied|exec.*off|secret.*scan|secret.*blocked|credential.*blocked|hook.*block", re.I)
tail = " when calling the ConverseStream operation: API Key invalid"
cases = {
    "bedrock AccessDeniedException": "An error occurred (AccessDeniedException)" + tail,
    "bedrock 403": "An error occurred (403)" + tail,
    "bedrock AccessDenied": "An error occurred (AccessDenied)" + tail,
    "ExpiredTokenException (control)": "ExpiredTokenException: expired",
    "STS security token (control)": "The security token included in the request is invalid",
    "A4 auth failed (control)": "Authentication failed for the request.",
    "Mistral 401 (control)": "Client error '401 Unauthorized' for url 'https://api.mistral.ai/v1/chat/completions'",
    "Anthropic 401 (ISS-1202, left open)": "Error code: 401 - {'type': 'error', 'error': {'type': 'authentication_error', 'message': 'invalid x-api-key'}}",
    "unknown (control)": "something entirely new",
    "ARN leak guard": "An error occurred (AccessDeniedException): API Key invalid for arn:aws:bedrock:eu-west-1:123456789012:inference-profile/x",
}
for name, raw in cases.items():
    out = _sanitize_agent_error(raw)
    tag = ("INVALID_KEY" if out == _INVALID_KEY_AGENT_ERROR else "CREDENTIAL" if out == _CREDENTIAL_AGENT_ERROR
           else "GENERIC" if out == _GENERIC_AGENT_ERROR_MESSAGE else "OTHER")
    print(f"{name:40s} -> {tag}" + ("  ARN-ECHOED!" if "arn:" in out else ""))
print("len(new copy) =", len(_INVALID_KEY_AGENT_ERROR), "(< 400 fan-out cap)")
print("frontend security-gate regex matches new copy:", bool(gate.search(_INVALID_KEY_AGENT_ERROR)))
print("new copy in TRANSIENT_AGENT_ERRORS (fan-out would retry):", _INVALID_KEY_AGENT_ERROR in TRANSIENT_AGENT_ERRORS)
print("run-stop set:", sorted(m[:48] for m in _CREDENTIAL_AGENT_ERRORS))
print("copy:", _INVALID_KEY_AGENT_ERROR)
