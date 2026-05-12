"""Remote MCP server endpoint for /flowin-handoff.

Implements a minimal subset of the Model Context Protocol over the
HTTP-streamable transport (single POST endpoint, JSON-RPC 2.0 envelopes).
Supported methods: ``initialize``, ``notifications/initialized``,
``ping``, ``tools/list``, ``tools/call``.

Tools exposed:

* ``flowin_handoff`` — creates a handoff session (identical to
  ``POST /api/handoff/receive``) and returns the URL the user opens in
  the browser. Synchronous; no streaming needed.

Authentication: ``Authorization: Bearer <flowin_api_key>``. The token
shape is the same value returned by ``POST /api/settings/api-keys``.

We intentionally do NOT support the GET-side SSE channel (server→client
push) — there is nothing to push for this tool since the long-running
work happens inside the browser-driven pipeline.
"""

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api.api_key_auth import hash_api_key
from app.core.config import settings
from app.models.database import get_db
from app.models.handoff import (
    HANDOFF_MODE_AUTO,
    HANDOFF_MODE_CODING,
    HANDOFF_MODE_TEST,
    HANDOFF_STATUS_PENDING,
    HandoffSession,
    UserApiKey,
)
from app.models.user import User

logger = logging.getLogger("app.api.mcp")

router = APIRouter(prefix="/mcp", tags=["mcp"])


_MCP_PROTOCOL_VERSION = "2024-11-05"
_MCP_SERVER_NAME = "flowin-handoff"
_MCP_SERVER_VERSION = "1.0.0"
_ALLOWED_MODES = {HANDOFF_MODE_AUTO, HANDOFF_MODE_CODING, HANDOFF_MODE_TEST}


_TOOL_SCHEMA: dict[str, Any] = {
    "name": "flowin_handoff",
    "description": (
        "Hand off a coding or testing task to Flowin. Flowin will run a multi-"
        "agent pipeline (coding → test analysis → compliance review) against "
        "the named GitHub repository and open a draft pull request. This call "
        "returns a URL the user must open in their browser to view progress, "
        "supply their GitHub credentials if not already configured, and start "
        "the pipeline. The actual code execution does not happen during this "
        "tool call."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "task": {
                "type": "string",
                "description": (
                    "Concise natural-language description of the task. "
                    "Example: 'Add a regression test for the bug described above' "
                    "or 'Refactor the login form to use the new useAuth hook.'"
                ),
                "minLength": 3,
                "maxLength": 4000,
            },
            "transcript_excerpt": {
                "type": "string",
                "description": (
                    "Optional snippet of recent IDE / chat conversation that gives "
                    "the pipeline relevant context. Keep under ~8 KB; longer content "
                    "is silently truncated. Do not include secrets or PII you would "
                    "not put in a PR body."
                ),
            },
            "repo_url": {
                "type": "string",
                "description": (
                    "HTTPS or SSH GitHub URL of the repository to operate on, e.g. "
                    "'https://github.com/acme/widgets' or 'git@github.com:acme/widgets.git'."
                ),
            },
            "mode": {
                "type": "string",
                "enum": ["auto", "coding", "test"],
                "default": "auto",
                "description": (
                    "Pipeline mode. 'coding' runs the coding agent followed by test "
                    "and compliance analysis. 'test' skips the coding step and only "
                    "produces a test + compliance report (no code change). 'auto' "
                    "asks the classifier."
                ),
            },
            "source_branch": {
                "type": "string",
                "description": (
                    "Branch to base the work off. Defaults to the repository's "
                    "default branch."
                ),
            },
        },
        "required": ["task", "repo_url"],
    },
}


def _get_user_from_bearer(
    request: Request,
    db: Session = Depends(get_db),
) -> User:
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = auth.split(None, 1)[1].strip()
    if not token.startswith("flowin_"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    row = (
        db.query(UserApiKey)
        .filter(UserApiKey.token_hash == hash_api_key(token))
        .first()
    )
    if row is None or row.revoked_at is not None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = db.query(User).filter(User.id == row.user_id).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    row.last_used_at = datetime.now(timezone.utc)
    db.add(row)
    db.commit()
    return user


def _jsonrpc_response(req_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _jsonrpc_error(req_id: Any, code: int, message: str, data: Any | None = None) -> dict[str, Any]:
    err: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return {"jsonrpc": "2.0", "id": req_id, "error": err}


def _handle_initialize(req_id: Any, _params: dict[str, Any]) -> dict[str, Any]:
    return _jsonrpc_response(
        req_id,
        {
            "protocolVersion": _MCP_PROTOCOL_VERSION,
            "capabilities": {
                "tools": {"listChanged": False},
            },
            "serverInfo": {"name": _MCP_SERVER_NAME, "version": _MCP_SERVER_VERSION},
        },
    )


def _handle_tools_list(req_id: Any) -> dict[str, Any]:
    return _jsonrpc_response(req_id, {"tools": [_TOOL_SCHEMA]})


def _handle_tools_call(
    req_id: Any, params: dict[str, Any], user: User, db: Session
) -> dict[str, Any]:
    name = params.get("name")
    if name != "flowin_handoff":
        return _jsonrpc_error(req_id, -32601, f"Unknown tool: {name!r}")

    arguments = params.get("arguments") or {}
    task = (arguments.get("task") or "").strip()
    repo_url = (arguments.get("repo_url") or "").strip()
    transcript = arguments.get("transcript_excerpt") or ""
    mode = arguments.get("mode") or HANDOFF_MODE_AUTO
    source_branch = arguments.get("source_branch")

    if not task or len(task) < 3:
        return _jsonrpc_error(req_id, -32602, "`task` must be at least 3 characters")
    if len(task) > 4000:
        return _jsonrpc_error(req_id, -32602, "`task` exceeds 4000 characters")
    if not repo_url:
        return _jsonrpc_error(req_id, -32602, "`repo_url` is required")
    if mode not in _ALLOWED_MODES:
        return _jsonrpc_error(req_id, -32602, f"`mode` must be one of {sorted(_ALLOWED_MODES)}")
    if len(transcript.encode("utf-8")) > settings.HANDOFF_MAX_TRANSCRIPT_BYTES:
        return _jsonrpc_error(
            req_id,
            -32602,
            f"`transcript_excerpt` exceeds {settings.HANDOFF_MAX_TRANSCRIPT_BYTES} bytes",
        )

    token = secrets.token_urlsafe(32)
    sess = HandoffSession(
        token=token,
        issuer_user_id=user.id,
        task_description=task,
        transcript=transcript,
        repo_url=repo_url,
        source_branch=source_branch,
        mode=mode,
        source_client="mcp",
        status=HANDOFF_STATUS_PENDING,
    )
    db.add(sess)
    db.commit()
    db.refresh(sess)

    handoff_url = f"{settings.PUBLIC_BASE_URL.rstrip('/')}/handoff/{token}"
    text = (
        f"Handoff created.\n\n"
        f"Open this URL in your browser to view the plan, supply your GitHub "
        f"PAT if you have not already, and start the pipeline:\n\n  {handoff_url}\n\n"
        f"The pipeline runs against {repo_url} on {source_branch or 'the default branch'}, "
        f"in {mode!r} mode, and opens a draft pull request when it completes."
    )
    return _jsonrpc_response(
        req_id,
        {
            "content": [{"type": "text", "text": text}],
            "structuredContent": {
                "handoff_id": sess.id,
                "token": token,
                "url": handoff_url,
                "expires_at": sess.expires_at.isoformat(),
            },
            "isError": False,
        },
    )


@router.post("/handoff")
async def mcp_handoff_endpoint(
    request: Request,
    user: User = Depends(_get_user_from_bearer),
    db: Session = Depends(get_db),
):
    """Single MCP JSON-RPC endpoint.

    Accepts a JSON-RPC 2.0 request (or batch). Notifications are
    acknowledged with 202; method calls get a JSON 200 response.
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            status_code=400,
            content=_jsonrpc_error(None, -32700, "Parse error"),
        )

    def _dispatch(msg: dict[str, Any]) -> dict[str, Any] | None:
        if not isinstance(msg, dict):
            return _jsonrpc_error(None, -32600, "Invalid Request")
        method = msg.get("method")
        req_id = msg.get("id")
        params = msg.get("params") or {}
        is_notification = req_id is None

        if method == "initialize":
            return _handle_initialize(req_id, params)
        if method == "notifications/initialized":
            return None  # notification, no response
        if method == "ping":
            return _jsonrpc_response(req_id, {})
        if method == "tools/list":
            return _handle_tools_list(req_id)
        if method == "tools/call":
            return _handle_tools_call(req_id, params, user, db)

        if is_notification:
            return None
        return _jsonrpc_error(req_id, -32601, f"Method not found: {method!r}")

    if isinstance(body, list):
        responses = [r for r in (_dispatch(item) for item in body) if r is not None]
        if not responses:
            return JSONResponse(status_code=202, content=None)
        return JSONResponse(content=responses)
    response = _dispatch(body)
    if response is None:
        return JSONResponse(status_code=202, content=None)
    return JSONResponse(content=response)


@router.get("/handoff")
async def mcp_handoff_get(
    request: Request,
    _user: User = Depends(_get_user_from_bearer),
):
    """Server→client GET stream — intentionally unimplemented.

    The MCP spec lets the server push notifications via SSE on GET, but
    our tool is synchronous (the long-running work happens in the
    browser, not over this transport). Returning 405 with a hint helps
    well-behaved MCP clients fall back to POST-only.
    """
    return JSONResponse(
        status_code=405,
        content={"error": "GET streaming not supported by flowin-handoff MCP; use POST."},
    )
