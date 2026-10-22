"""app/api/run_figma_frames.py — FIGMA-01: owner-scoped Figma frame upload for a run.

``POST /api/runs/{id}/figma-frames`` accepts PNG/JPEG screen exports from Figma
and lands them under the run's ``RunSandbox`` at the dedicated ``.figma/``
prefix (NOT ``.uploads/``). This keeps ``.uploads/`` for text-extractable
documents only and avoids cluttering the workspace with PNG assets alongside
spec PDFs and DOCX files.

The Design Ingestor agent reads frames from ``.figma/`` and the fi-planner
ignores ``.figma/`` entirely (it only reads ``.uploads/manifest.json``).
"""

Design constraints honoured (mirrors run_files.py):
  * **Ownership (FIGMA-01)** — the SAME two-layer owner check as
    ``run_files.upload_files``: (1) a ``WorkflowRun.id == run_id AND
    user_id == current_user.id`` ORM filter → 404 (never 403), capturing the
    ``workspace_id``; (2) a default-deny ``ScopedStore.get_run(run_id) is None``
    → 404.  IDOR resolves to 404, never a 403 existence oracle.
  * **Caps (FIGMA-02) — enforced BEFORE any sandbox write**: an ext allow-list
    ({png,jpg,jpeg}) AND mime allow-list ({image/png,image/jpeg}) → 415 on miss,
    with a friendly Figma-specific export instruction; a per-file byte cap of 4 MB
    (images are lighter than the 10 MB document cap) → 413; a frame-count cap of 20
    → 413.  Every file is read + validated first; a single rejection writes nothing.
  * **Traversal** — every write resolves through ``RunSandbox.path_for`` under
    the reserved ``.uploads/`` prefix (same as run_files.py).
  * **Manifest shape** — each entry carries ``name``, ``mime``, ``type='image'``,
    ``description``, ``has_text=False``.  The fi-planner branches on
    ``type='image'`` OR an image file extension to skip extract_text and build a
    synthetic shard.
  * **SC-001 intact** — no ``if pipeline_type ==`` added to engine.py.
  * **Additive** — no new table, no migration.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, status

from app.agents.sandbox import (
    FamilyLockTimeout,
    RunSandbox,
    _safe_segment,
    family_lock,
)
from app.api.run_engine import _get_db
from app.api.run_files import (
    _dedupe_segment,
    _manifest_lock,
    _read_capped,
    _read_manifest,
    _resolve_chain_root_or_404,
    _write_bytes,
)
from app.core.config import settings
from app.core.dependencies import get_current_user
from app.models.user import User
from app.models.workflow import WorkflowRun

logger = logging.getLogger("app.api.run_figma_frames")

router = APIRouter(prefix="/api/runs", tags=["runs"])

# ── Constants ────────────────────────────────────────────────────────────────
# Separate from the 10 MB document cap in file_extract — images are lighter.
_MAX_FRAME_BYTES = 4 * 1024 * 1024  # 4 MB per frame
_MAX_FRAME_COUNT = 20
_ALLOWED_FRAME_EXTS: frozenset[str] = frozenset({"png", "jpg", "jpeg"})
_ALLOWED_FRAME_MIMES: frozenset[str] = frozenset({"image/png", "image/jpeg"})

# Dedicated prefix for Figma frame assets — separate from .uploads/ (documents).
# Keeps the workspace clean: .uploads/ = text docs, .figma/ = design PNGs.
# The Design Ingestor reads from .figma/; fi-planner never touches it.
_FIGMA_PREFIX = ".figma/"

# Friendly 415 message: guides users to the correct Figma export path.
_UNSUPPORTED_TYPE_MSG = (
    "Unsupported file type: {name!r}. Please export your screens as PNG from Figma: "
    "select a frame → right-click → Export → PNG @ 1×. "
    "Accepted: .png / .jpg / .jpeg"
)


def _ext_of(filename: str) -> str:
    """Return the lowercased extension of ``filename``, or empty string."""
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


@router.post("/{run_id}/figma-frames")
async def upload_figma_frames(
    run_id: str,
    files: list[UploadFile],
    current_user: User = Depends(get_current_user),
    # Optional per-file descriptions as a repeated form field.
    # Each element is a JSON string: {"index": N, "description": "..."}.
    # FastAPI does not auto-parse mixed file+form in one list, so we accept
    # a single joined string (comma-separated JSON objects) or repeated fields.
    metadata_json: Optional[str] = Form(None),
) -> dict:
    """Accept PNG/JPEG Figma screen exports and land them under ``.uploads/``.

    Two-layer IDOR check → 404 (never 403). Caps enforced BEFORE any write.
    Manifest entries carry ``type='image'``, ``description``, ``has_text=False``
    so the fi-planner's Phase 1 Step 3 image branch fires automatically.

    Returns ``{run_id, files: [{name, bytes}]}``.
    """
    from agents.authz import ScopedStore

    # ── Count cap (before reading any bytes) ─────────────────────────────────
    if len(files) > _MAX_FRAME_COUNT:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Too many files ({len(files)}). Maximum: {_MAX_FRAME_COUNT}",
        )

    # ── Parse optional per-file descriptions ─────────────────────────────────
    # metadata_json is a JSON array: [{"index": 0, "description": "..."}, ...]
    descriptions: list[str] = [""] * len(files)
    if metadata_json:
        try:
            items = json.loads(metadata_json)
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, dict):
                        idx = item.get("index")
                        desc = item.get("description", "")
                        if isinstance(idx, int) and 0 <= idx < len(files):
                            descriptions[idx] = str(desc)
        except (ValueError, TypeError):
            pass  # Malformed metadata is ignored; descriptions stay empty

    # ── Per-file validation — ALL files validated before any write ────────────
    validated: list[tuple[str, bytes, str, str, str]] = []  # (name,data,ext,mime,desc)
    for i, upload in enumerate(files):
        name = upload.filename or f"frame-{i + 1}.png"
        ext = _ext_of(name)
        mime = upload.content_type or "application/octet-stream"

        if ext not in _ALLOWED_FRAME_EXTS or mime not in _ALLOWED_FRAME_MIMES:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=_UNSUPPORTED_TYPE_MSG.format(name=name),
            )

        data = await _read_capped(upload, _MAX_FRAME_BYTES)
        if data is None:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=(
                    f"File too large: {name!r} "
                    f"(max {_MAX_FRAME_BYTES // (1024 * 1024)} MB per frame)"
                ),
            )
        validated.append((name, data, ext, mime, descriptions[i]))

    # ── Layer 1: owner-scoped ORM filter (cross-owner / missing → 404, never 403)
    #    Mirrors upload_files() in run_files.py verbatim. ──────────────────────
    db = _get_db()
    try:
        wr = (
            db.query(WorkflowRun)
            .filter(WorkflowRun.id == run_id, WorkflowRun.user_id == current_user.id)
            .first()
        )
        if wr is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Workflow run not found"
            )
        wr_workspace = wr.workspace_id
    finally:
        db.close()

    # ── Layer 2: default-deny re-resolve (store-denied → 404, never 403) ─────
    store = ScopedStore(owner_id=current_user.id, workspace_id=wr_workspace)
    if await store.get_run(run_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Workflow run not found"
        )

    # ── Resolve to revision root and create sandbox ───────────────────────────
    chain_root_id = _resolve_chain_root_or_404(run_id, current_user.id)
    sandbox = RunSandbox(current_user.id, chain_root_id, runs_root=settings.RUNS_ROOT)
    sandbox.ensure()

    manifest_rel = f"{_FIGMA_PREFIX}manifest.json"

    # ── Acquire family lock (family → manifest ordering per run_files.py) ─────
    try:
        _family_lock_ctx = family_lock(
            current_user.id,
            chain_root_id,
            runs_root=settings.RUNS_ROOT,
        )
        _family_lock_ctx.__enter__()
    except FamilyLockTimeout:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Run is temporarily unavailable. Please retry.",
        )

    try:
        with _manifest_lock(sandbox):
            manifest = _read_manifest(sandbox, manifest_rel)
            # Offset from existing image entries so frame numbering is additive.
            frame_offset = sum(
                1 for e in manifest.values() if e.get("type") == "image"
            )
            used_names: set[str] = set(manifest)
            results: list[dict] = []

            for i, (name, data, ext, mime, description) in enumerate(validated):
                base_name = f"frame-{frame_offset + i + 1}.{ext}"
                safe = _dedupe_segment(
                    _safe_segment(base_name, fallback="frame"), used_names
                )
                used_names.add(safe)
                _write_bytes(sandbox, f"{_FIGMA_PREFIX}{safe}", data)
                manifest[safe] = {
                    "name": safe,
                    "mime": mime,
                    "type": "image",
                    "description": description,
                    "has_text": False,
                }
                results.append({"name": safe, "bytes": len(data)})
                    "name": safe,
                    "mime": mime,
                    "type": "image",
                    "description": description,
                    "has_text": False,
                }
                results.append({"name": safe, "bytes": len(data)})

            # Write manifest as a JSON array (same shape run_files.py writes).
            _write_bytes(
                sandbox,
                manifest_rel,
                json.dumps(list(manifest.values()), ensure_ascii=False).encode(
                    "utf-8"
                ),
            )
    finally:
        _family_lock_ctx.__exit__(None, None, None)

    logger.info(
        "figma frames upload: user=%s run=%s frames=%d",
        current_user.id,
        run_id,
        len(results),
    )
    return {"run_id": run_id, "files": results}
