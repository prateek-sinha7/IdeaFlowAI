"""User-scoped settings: GitHub PAT and long-lived API keys.

All endpoints require an interactive Flowin login (the standard JWT
dependency). The PAT and API keys are credentials for OTHER services
(GitHub / the IDE), so we never accept them on this router via the same
auth they unlock — that would create a credential-laundering vector.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.api_key_auth import mint_api_key
from app.core.crypto import decrypt_pat, encrypt_pat
from app.core.dependencies import get_current_user
from app.models.database import get_db
from app.models.handoff import UserApiKey, UserGithubCredential
from app.models.user import User

logger = logging.getLogger("app.api.settings")


router = APIRouter(prefix="/api/settings", tags=["settings"])


# --- Schemas ------------------------------------------------------------


class GithubPATRequest(BaseModel):
    pat: str = Field(..., min_length=10, max_length=512)


class GithubPATResponse(BaseModel):
    github_username: str | None = None
    scopes: str | None = None
    last_4: str
    created_at: datetime
    updated_at: datetime


class ApiKeyCreateRequest(BaseModel):
    name: str = Field(default="Default", min_length=1, max_length=64)


class ApiKeyCreateResponse(BaseModel):
    id: str
    name: str
    token: str  # plaintext — ONLY returned on creation
    token_prefix: str
    created_at: datetime


class ApiKeySummary(BaseModel):
    id: str
    name: str
    token_prefix: str
    last_used_at: datetime | None
    created_at: datetime
    revoked_at: datetime | None


# --- GitHub PAT ---------------------------------------------------------


@router.put("/github-pat", response_model=GithubPATResponse)
async def upsert_github_pat(
    payload: GithubPATRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> GithubPATResponse:
    """Save (or replace) the caller's GitHub PAT.

    We validate the PAT before persisting by calling ``GET /user`` on the
    GitHub API; this catches obvious typos and also lets us record the
    GitHub username + visible scopes so the UI can show what was saved.
    """
    pat = payload.pat.strip()
    if not pat:
        raise HTTPException(status_code=422, detail="PAT must not be empty")

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            "https://api.github.com/user",
            headers={
                "Authorization": f"Bearer {pat}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "Flowin-Handoff/1.0",
            },
        )
    if resp.status_code != 200:
        raise HTTPException(
            status_code=400,
            detail=f"GitHub rejected the PAT ({resp.status_code}). Check that it has at least `repo` scope.",
        )
    gh_user = resp.json().get("login")
    scopes_header = resp.headers.get("x-oauth-scopes") or resp.headers.get("X-OAuth-Scopes") or ""

    encrypted = encrypt_pat(pat)
    row = (
        db.query(UserGithubCredential)
        .filter(UserGithubCredential.user_id == user.id)
        .first()
    )
    now = datetime.now(timezone.utc)
    if row is None:
        row = UserGithubCredential(
            user_id=user.id,
            encrypted_pat=encrypted,
            github_username=gh_user,
            scopes=scopes_header,
        )
        db.add(row)
    else:
        row.encrypted_pat = encrypted
        row.github_username = gh_user
        row.scopes = scopes_header
        row.updated_at = now
    db.commit()
    db.refresh(row)
    return GithubPATResponse(
        github_username=row.github_username,
        scopes=row.scopes,
        last_4=pat[-4:],
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get("/github-pat", response_model=GithubPATResponse | None)
def get_github_pat_status(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = (
        db.query(UserGithubCredential)
        .filter(UserGithubCredential.user_id == user.id)
        .first()
    )
    if row is None:
        return None
    try:
        pat = decrypt_pat(row.encrypted_pat)
        last_4 = pat[-4:]
    except Exception:
        last_4 = "????"
    return GithubPATResponse(
        github_username=row.github_username,
        scopes=row.scopes,
        last_4=last_4,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.delete("/github-pat", status_code=status.HTTP_204_NO_CONTENT)
def delete_github_pat(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = (
        db.query(UserGithubCredential)
        .filter(UserGithubCredential.user_id == user.id)
        .first()
    )
    if row is not None:
        db.delete(row)
        db.commit()
    return None


# --- API keys -----------------------------------------------------------


@router.post(
    "/api-keys",
    response_model=ApiKeyCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_api_key(
    payload: ApiKeyCreateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiKeyCreateResponse:
    plaintext, prefix, digest = mint_api_key()
    row = UserApiKey(
        user_id=user.id,
        name=payload.name,
        token_prefix=prefix,
        token_hash=digest,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return ApiKeyCreateResponse(
        id=row.id,
        name=row.name,
        token=plaintext,
        token_prefix=row.token_prefix,
        created_at=row.created_at,
    )


@router.get("/api-keys", response_model=list[ApiKeySummary])
def list_api_keys(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(UserApiKey)
        .filter(UserApiKey.user_id == user.id)
        .order_by(UserApiKey.created_at.desc())
        .all()
    )
    return [
        ApiKeySummary(
            id=r.id,
            name=r.name,
            token_prefix=r.token_prefix,
            last_used_at=r.last_used_at,
            created_at=r.created_at,
            revoked_at=r.revoked_at,
        )
        for r in rows
    ]


@router.delete("/api-keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_api_key(
    key_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = (
        db.query(UserApiKey)
        .filter(UserApiKey.id == key_id, UserApiKey.user_id == user.id)
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="API key not found")
    if row.revoked_at is None:
        row.revoked_at = datetime.now(timezone.utc)
        db.add(row)
        db.commit()
    return None
