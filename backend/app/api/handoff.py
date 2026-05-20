"""HTTP routes for the /flowin-handoff feature.

* ``POST /api/handoff/receive`` — IDE-side endpoint that accepts a
  task + transcript + repo URL and returns a one-time URL the user
  opens in the browser. Authenticated by ``X-Flowin-API-Key``.

* ``GET /api/handoff/{token}`` — browser-side endpoint that returns
  the session details for the issuer (the user who created it).
  Authenticated by the standard JWT dependency.

* ``POST /api/handoff/{token}/start`` — kick the pipeline. The
  WebSocket at :mod:`app.api.websocket_handoff` is the live event
  channel. This endpoint is fire-and-forget — it returns 202 the moment
  the pipeline task is scheduled.
"""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.api_key_auth import get_user_via_api_key
from app.core.config import settings
from app.core.crypto import decrypt_pat
from app.core.dependencies import get_current_user
from app.models.database import SessionLocal, get_db
from app.models.handoff import (
    HANDOFF_MODE_AUTO,
    HANDOFF_MODE_CODING,
    HANDOFF_MODE_TEST,
    HANDOFF_STATUS_COMPLETED,
    HANDOFF_STATUS_FAILED,
    HANDOFF_STATUS_PENDING,
    HANDOFF_STATUS_RUNNING,
    HandoffSession,
    UserGithubCredential,
)
from app.models.user import User
from app.services.handoff_pipeline import run_handoff_pipeline

logger = logging.getLogger("app.api.handoff")

router = APIRouter(prefix="/api/handoff", tags=["handoff"])


_ALLOWED_MODES = {HANDOFF_MODE_AUTO, HANDOFF_MODE_CODING, HANDOFF_MODE_TEST}


# --- Schemas ------------------------------------------------------------


class HandoffReceiveRequest(BaseModel):
    task: str = Field(..., min_length=3, max_length=4000)
    transcript: str = Field(default="")
    repo_url: str = Field(..., min_length=4, max_length=512)
    mode: str = Field(default=HANDOFF_MODE_AUTO)
    source_branch: str | None = Field(default=None, max_length=255)
    source_client: str | None = Field(default=None, max_length=64)


class HandoffReceiveResponse(BaseModel):
    handoff_id: str
    token: str
    url: str
    expires_at: datetime
    status: str


class HandoffSessionView(BaseModel):
    id: str
    token: str
    task_description: str
    repo_url: str
    mode: str
    resolved_mode: str | None
    status: str
    source_client: str | None
    source_branch: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    expires_at: datetime
    pr_url: str | None
    pr_number: int | None
    branch_name: str | None
    pipeline_output: dict[str, Any] | None
    error: str | None
    issuer_email: str | None
    has_github_pat: bool


class HandoffStartResponse(BaseModel):
    status: str
    started_at: datetime


# --- Helpers ------------------------------------------------------------


def _mint_token() -> str:
    """Return a 43-char URL-safe random token (256 bits)."""
    return secrets.token_urlsafe(32)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime | None) -> datetime | None:
    """Promote SQLite-naive datetimes to tz-aware UTC.

    The DB layer hands back naive datetimes on SQLite even though we
    write tz-aware values in (the column type is plain ``DateTime``).
    Compare apples to apples by treating any naive value as UTC.
    """
    if dt is None or dt.tzinfo is not None:
        return dt
    return dt.replace(tzinfo=timezone.utc)


def _serialise(session: HandoffSession, issuer_email: str | None, has_pat: bool) -> HandoffSessionView:
    output: dict[str, Any] | None = None
    if session.pipeline_output:
        try:
            output = json.loads(session.pipeline_output)
        except (TypeError, json.JSONDecodeError):
            output = None
    return HandoffSessionView(
        id=session.id,
        token=session.token,
        task_description=session.task_description,
        repo_url=session.repo_url,
        mode=session.mode,
        resolved_mode=session.resolved_mode,
        status=session.status,
        source_client=session.source_client,
        source_branch=session.source_branch,
        created_at=session.created_at,
        started_at=session.started_at,
        completed_at=session.completed_at,
        expires_at=session.expires_at,
        pr_url=session.pr_url,
        pr_number=session.pr_number,
        branch_name=session.branch_name,
        pipeline_output=output,
        error=session.error,
        issuer_email=issuer_email,
        has_github_pat=has_pat,
    )


def _user_has_pat(db: Session, user_id: str) -> bool:
    return (
        db.query(UserGithubCredential)
        .filter(UserGithubCredential.user_id == user_id)
        .first()
        is not None
    )


# --- POST /api/handoff/receive (IDE-side) -------------------------------


@router.post(
    "/receive",
    response_model=HandoffReceiveResponse,
    status_code=status.HTTP_201_CREATED,
)
def receive_handoff(
    payload: HandoffReceiveRequest,
    user: User = Depends(get_user_via_api_key),
    db: Session = Depends(get_db),
) -> HandoffReceiveResponse:
    """Create a handoff session and return the URL the user opens.

    Authenticated by the long-lived ``X-Flowin-API-Key`` header. We do
    NOT require the GitHub PAT to be configured at this point — the
    /start endpoint enforces that, so the user can be prompted to set
    it up after they click the URL.
    """
    if payload.mode not in _ALLOWED_MODES:
        raise HTTPException(status_code=422, detail=f"mode must be one of {sorted(_ALLOWED_MODES)}")

    if len(payload.transcript.encode("utf-8")) > settings.HANDOFF_MAX_TRANSCRIPT_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"transcript exceeds {settings.HANDOFF_MAX_TRANSCRIPT_BYTES} bytes",
        )

    token = _mint_token()
    sess = HandoffSession(
        token=token,
        issuer_user_id=user.id,
        task_description=payload.task.strip(),
        transcript=payload.transcript,
        repo_url=payload.repo_url.strip(),
        source_branch=payload.source_branch,
        mode=payload.mode,
        source_client=payload.source_client or "unknown",
        status=HANDOFF_STATUS_PENDING,
    )
    db.add(sess)
    db.commit()
    db.refresh(sess)

    base = settings.PUBLIC_BASE_URL.rstrip("/")
    return HandoffReceiveResponse(
        handoff_id=sess.id,
        token=token,
        url=f"{base}/handoff/{token}",
        expires_at=sess.expires_at,
        status=sess.status,
    )


# --- GET /api/handoff/{token} (browser-side, issuer-only) ---------------


@router.get("/{token}", response_model=HandoffSessionView)
def get_handoff(
    token: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> HandoffSessionView:
    sess = db.query(HandoffSession).filter(HandoffSession.token == token).first()
    if sess is None:
        raise HTTPException(status_code=404, detail="Handoff not found")
    if sess.issuer_user_id != user.id:
        # Same 404 — never confirm a token's existence to the wrong user.
        raise HTTPException(status_code=404, detail="Handoff not found")
    now = _now()
    expires_at = _aware(sess.expires_at) or now
    if expires_at < now:
        if sess.status == HANDOFF_STATUS_PENDING:
            sess.status = "expired"
            db.add(sess)
            db.commit()
            db.refresh(sess)
        elif sess.status == HANDOFF_STATUS_RUNNING:
            # A pipeline that didn't complete before expiry — most likely
            # because the asyncio task was GC'd by a backend restart. Flip
            # the row to FAILED so the frontend's "Retry pipeline" button
            # becomes active again, instead of leaving the user staring at
            # a dead RUNNING state with no recovery path.
            sess.status = HANDOFF_STATUS_FAILED
            sess.error = "Pipeline did not complete before the handoff expired."
            sess.completed_at = now
            db.add(sess)
            db.commit()
            db.refresh(sess)
    return _serialise(sess, user.email, _user_has_pat(db, user.id))


# --- POST /api/handoff/{token}/start (browser-side) ---------------------


@router.post("/{token}/start", response_model=HandoffStartResponse)
async def start_handoff(
    token: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> HandoffStartResponse:
    """Kick the pipeline. Returns immediately; events flow over the WS."""
    sess = db.query(HandoffSession).filter(HandoffSession.token == token).first()
    if sess is None or sess.issuer_user_id != user.id:
        raise HTTPException(status_code=404, detail="Handoff not found")
    if sess.status not in (HANDOFF_STATUS_PENDING, HANDOFF_STATUS_FAILED):
        raise HTTPException(status_code=409, detail=f"Handoff already in state {sess.status!r}")
    if (_aware(sess.expires_at) or _now()) < _now():
        raise HTTPException(status_code=410, detail="Handoff has expired; create a new one from your IDE")

    pat_row = (
        db.query(UserGithubCredential)
        .filter(UserGithubCredential.user_id == user.id)
        .first()
    )
    if pat_row is None:
        raise HTTPException(
            status_code=412,
            detail="GitHub PAT not configured. Add one under Settings before starting a handoff.",
        )
    try:
        pat = decrypt_pat(pat_row.encrypted_pat)
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Stored PAT could not be decrypted (encryption key may have rotated). Please re-add it under Settings.",
        )

    # Atomic state transition guards against a double-click / two-tab race
    # where both requests pass the read-then-write check above and both
    # spawn a background pipeline (which would open two PRs and race on
    # pipeline_output). The conditional UPDATE returns 1 only for the
    # request that actually transitions the row; everyone else gets 409.
    started_at = _now()
    rows = (
        db.query(HandoffSession)
        .filter(
            HandoffSession.id == sess.id,
            HandoffSession.status.in_([HANDOFF_STATUS_PENDING, HANDOFF_STATUS_FAILED]),
        )
        .update(
            {
                HandoffSession.status: HANDOFF_STATUS_RUNNING,
                HandoffSession.started_at: started_at,
                HandoffSession.error: None,
            },
            synchronize_session=False,
        )
    )
    db.commit()
    if rows != 1:
        raise HTTPException(
            status_code=409,
            detail="Handoff is already running or has changed state. Refresh to see the latest status.",
        )
    db.refresh(sess)

    asyncio.create_task(
        _run_pipeline_background(
            handoff_id=sess.id,
            handoff_token=sess.token,
            task=sess.task_description,
            transcript=sess.transcript,
            repo_url=sess.repo_url,
            requested_mode=sess.mode,
            source_branch=sess.source_branch,
            pat=pat,
            issuer_email=user.email,
            handoff_public_url=f"{settings.PUBLIC_BASE_URL.rstrip('/')}/handoff/{sess.token}",
        )
    )
    return HandoffStartResponse(status=sess.status, started_at=sess.started_at)


async def _run_pipeline_background(
    *,
    handoff_id: str,
    handoff_token: str,
    task: str,
    transcript: str,
    repo_url: str,
    requested_mode: str,
    source_branch: str | None,
    pat: str,
    issuer_email: str,
    handoff_public_url: str,
) -> None:
    """Drive the pipeline generator and persist results.

    Lives outside the request scope so the HTTP response can return 202
    immediately. Uses a fresh DB session because the request session is
    long gone by the time the pipeline finishes.
    """
    from app.api.websocket_handoff import dispatch_event  # local import — avoid cycle

    pipeline_output: dict[str, Any] | None = None
    error_msg: str | None = None
    try:
        async for event in run_handoff_pipeline(
            handoff_id=handoff_id,
            handoff_token=handoff_token,
            task_description=task,
            transcript_excerpt=transcript[-8000:] if transcript else None,
            repo_url=repo_url,
            requested_mode=requested_mode,
            source_branch=source_branch,
            pat=pat,
            issuer_email=issuer_email,
            handoff_public_url=handoff_public_url,
        ):
            await dispatch_event(handoff_token, event)
            if event.get("type") == "pipeline_complete":
                pipeline_output = event.get("data") or {}
    except Exception as exc:
        error_msg = str(exc)
        logger.exception("Handoff pipeline failed for %s", handoff_id)
    finally:
        db = SessionLocal()
        try:
            sess = db.query(HandoffSession).filter(HandoffSession.id == handoff_id).first()
            if sess is not None:
                now = _now()
                if error_msg is not None:
                    sess.status = HANDOFF_STATUS_FAILED
                    sess.error = error_msg[:4000]
                else:
                    sess.status = HANDOFF_STATUS_COMPLETED
                if pipeline_output is not None:
                    sess.pipeline_output = json.dumps(pipeline_output)
                    sess.resolved_mode = pipeline_output.get("resolved_mode")
                    sess.branch_name = pipeline_output.get("branch_name")
                    sess.pr_url = pipeline_output.get("pr_url")
                    sess.pr_number = pipeline_output.get("pr_number")
                sess.completed_at = now
                db.add(sess)
                db.commit()
        finally:
            db.close()
