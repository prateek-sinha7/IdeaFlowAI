"""app/api/run_files.py — UPLD-01: owner-scoped document upload for a run.

``POST /api/runs/{id}/files`` lets a run's owner attach documents to an in-flight
(or reopened) run. Accepted bytes land under the run's on-disk ``RunSandbox`` at a
RESERVED ``.uploads/`` prefix so agents can ``read_file`` them, and extractable
documents (pdf/docx/pptx) are text-extracted at ingest into a ``.txt`` sidecar +
a ``manifest.json`` entry — the stable contract 30-02's ``uploaded_files``
context provider reads to make the text sticky in every subsequent ``agent_input``.

Per POR §2 (D-07, amended): only DOCUMENTS go to the sandbox. Images are
payload-transient (handled on the message path, 30-03), so image mimes / exts are
rejected here — this endpoint is documents-only.

Design constraints honoured:
  * **Ownership (T-30-01)** — the SAME two-layer owner check as
    ``run_commands.post_message``: (1) a ``WorkflowRun.id == run_id AND
    user_id == current_user.id`` ORM filter → 404 (never 403), capturing the
    ``workspace_id``; (2) a default-deny ``ScopedStore.get_run(run_id) is None``
    → 404. IDOR resolves to 404, never a 403 existence oracle. ``user_id`` (not
    the nullable ``owner_id``) is the principal (P13/P25 precedent). Owner +
    workspace is thereby stamped on everything persisted.
  * **Caps (T-30-02) — enforced BEFORE any sandbox write**: an ext allow-list
    ({pdf,docx,pptx,txt,md,csv,json}) → 415 on miss; the per-file byte cap
    (``file_extract._MAX_FILE_BYTES``, the single source, imported not
    re-declared) → 413; a document-count cap (≤20) and an aggregate byte cap →
    413. Every file is read + validated first; a single rejection writes nothing.
  * **Traversal (T-30-03)** — every write resolves through ``RunSandbox.path_for``
    under the reserved ``.uploads/`` prefix, so a hostile filename cannot escape
    the per-user/per-run root.
  * **Deliverable isolation (T-30-05)** — the ``.uploads/`` subtree is excluded
    from ``serialize_sandbox_deliverable`` (``sandbox._UPLOADS_PREFIX``), so an
    upload never pollutes the deliverable and golden runs stay byte-identical
    (INV-3 — dormant when no upload happened).

Additive: no new table, no migration (the sandbox + reserved prefix cover it).
"""

from __future__ import annotations

import json
import logging
import os

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status

from app.agents.sandbox import RunSandbox, _UPLOADS_PREFIX, _safe_segment
from app.api.file_extract import _MAX_FILE_BYTES, extract_upload_text
from app.core.config import settings
from app.core.dependencies import get_current_user
from app.models.user import User
from app.models.workflow import WorkflowRun

# READ-ONLY reuse of the SAME owner-check DB seam ``run_commands.post_message``
# uses, so the two upload/command paths cannot diverge on ownership (LOCK — no
# symbol is added to websocket.py; the endpoint is monkeypatch-testable via this
# module reference exactly like run_commands).
from app.api.websocket import _get_db

logger = logging.getLogger("app.api.run_files")

router = APIRouter(prefix="/api/runs", tags=["run-files"])

# Document-only allow-list (T-30-04): the ext set that may land in the sandbox.
# Images are payload-transient (30-03) → rejected here.
_ALLOWED_EXTS: frozenset[str] = frozenset({"pdf", "docx", "pptx", "txt", "md", "csv", "json"})
# The subset that carries an extractable-text sidecar (the sticky-context source).
_EXTRACTABLE_EXTS: frozenset[str] = frozenset({"pdf", "docx", "pptx"})

# Count + aggregate caps (T-30-02), mirroring the image-ingress cap STRUCTURE in
# websocket.py (_IMAGE_MAX_COUNT / _IMAGE_MAX_AGGREGATE_BYTES) but for documents.
# The per-file cap is file_extract._MAX_FILE_BYTES (10 MB, single source).
_MAX_DOC_COUNT = 20
_MAX_AGGREGATE_BYTES = 40 * 1024 * 1024  # ~40 MB raw across all documents in one call


def _ext_of(filename: str) -> str:
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def _dedupe_segment(safe: str, used: set[str]) -> str:
    """Return ``safe`` — or ``safe`` with a ``-N`` suffix inserted before its extension —
    that is not already in ``used`` (WR-01).

    Two DISTINCT original filenames can sanitize to the same ``_safe_segment`` (e.g.
    ``invoice#1.txt`` and ``invoice@1.txt`` both → ``invoice_1.txt``); without this the
    second write silently clobbers the first's bytes + sidecar + manifest entry while the
    response still reports both as stored. The first use keeps the bare name; each
    subsequent collision takes the next free ``-2``, ``-3``… (``invoice_1.txt`` →
    ``invoice_1-2.txt``), so no upload is ever silently overwritten and the caller is told
    the ACTUAL stored name.
    """
    if safe not in used:
        return safe
    stem, dot, ext = safe.rpartition(".")
    base, suffix = (stem, f".{ext}") if dot else (safe, "")
    n = 2
    while f"{base}-{n}{suffix}" in used:
        n += 1
    return f"{base}-{n}{suffix}"


@router.post("/{run_id}/files")
async def upload_files(
    run_id: str,
    files: list[UploadFile],
    current_user: User = Depends(get_current_user),
):
    """Attach owner-scoped documents to a run's sandbox (UPLD-01).

    Two-layer owner check → 404 (IDOR, never 403); caps rejected BEFORE any write;
    accepted docs land under the reserved ``.uploads/`` prefix with an extracted-
    text sidecar + manifest entry for extractable types. Returns the per-file
    ingest summary ``{run_id, files:[{name, bytes, extracted_chars, truncated}]}``.
    """
    from agents.authz import ScopedStore

    # ── Layer 1: owner-scoped ORM filter (cross-owner / missing → 404, never 403).
    #    Mirrors run_commands.post_message EXACTLY — user_id is the principal, not
    #    the nullable owner_id (P13/P25). ────────────────────────────────────────
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

    # ── Layer 2: default-deny re-resolve so the ownership boundary lives in ONE
    #    place — a store-denied run id → 404 (never 403). ─────────────────────────
    store = ScopedStore(owner_id=current_user.id, workspace_id=wr_workspace)
    if await store.get_run(run_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Workflow run not found"
        )

    # ── Read + validate EVERY file up-front so a single cap rejection writes
    #    NOTHING to disk (T-30-02: caps enforced before any sandbox write). ────────
    if len(files) > _MAX_DOC_COUNT:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Too many files ({len(files)}). Maximum: {_MAX_DOC_COUNT}",
        )

    validated: list[tuple[str, bytes, str, str]] = []  # (name, data, ext, mime)
    aggregate = 0
    for upload in files:
        name = upload.filename or "unknown"
        ext = _ext_of(name)
        mime = upload.content_type or "application/octet-stream"

        # Documents-only: reject images (payload-transient, 30-03) + any ext off
        # the allow-list → 415 (T-30-04).
        if ext not in _ALLOWED_EXTS or mime.startswith("image/"):
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=(
                    f"Unsupported file type: {name!r} (.{ext}, {mime}). "
                    f"Allowed document types: {sorted(_ALLOWED_EXTS)}"
                ),
            )

        data = await upload.read()
        if len(data) > _MAX_FILE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=(
                    f"File too large: {name!r} ({len(data) // 1024} KB). "
                    f"Maximum per file: {_MAX_FILE_BYTES // 1024} KB"
                ),
            )
        aggregate += len(data)
        if aggregate > _MAX_AGGREGATE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=(
                    f"Upload exceeds the aggregate limit of "
                    f"{_MAX_AGGREGATE_BYTES // 1024} KB"
                ),
            )
        validated.append((name, data, ext, mime))

    # ── All caps passed — NOW persist under the reserved .uploads/ prefix. Every
    #    write resolves through RunSandbox.path_for (traversal-proof, T-30-03). ────
    sandbox = RunSandbox(current_user.id, run_id, runs_root=settings.RUNS_ROOT)
    sandbox.ensure()

    manifest_rel = f"{_UPLOADS_PREFIX}manifest.json"
    manifest = _read_manifest(sandbox, manifest_rel)
    # Seed with the names already stored for this run so a new upload never silently
    # overwrites a prior one either (WR-01) — every stored file keeps a distinct name.
    used_names: set[str] = set(manifest)
    results: list[dict] = []

    for name, data, ext, mime in validated:
        safe = _dedupe_segment(
            _safe_segment(os.path.basename(name), fallback="upload"), used_names
        )
        used_names.add(safe)
        raw_rel = f"{_UPLOADS_PREFIX}{safe}"
        _write_bytes(sandbox, raw_rel, data)

        extracted_chars = 0
        truncated = False
        has_text = False
        if ext in _EXTRACTABLE_EXTS:
            text = extract_upload_text(name, data)
            if text.strip():
                truncated = len(text) > settings.BRIEF_MAX_CHARS
                capped = text[: settings.BRIEF_MAX_CHARS]
                _write_bytes(sandbox, f"{raw_rel}.txt", capped.encode("utf-8"))
                extracted_chars = len(capped)
                has_text = True

        # manifest append-merge (keyed on the safe on-disk name — the stable
        # contract 30-02's provider reads).
        manifest[safe] = {"name": safe, "mime": mime, "has_text": has_text}
        results.append(
            {
                "name": safe,
                "bytes": len(data),
                "extracted_chars": extracted_chars,
                "truncated": truncated,
            }
        )

    _write_bytes(
        sandbox,
        manifest_rel,
        json.dumps(list(manifest.values()), ensure_ascii=False).encode("utf-8"),
    )

    logger.info(
        "run upload: user=%s run=%s files=%d aggregate_bytes=%d",
        current_user.id, run_id, len(results), aggregate,
    )
    return {"run_id": run_id, "files": results}


def _read_manifest(sandbox: RunSandbox, manifest_rel: str) -> dict[str, dict]:
    """Load the existing ``.uploads/manifest.json`` as a name→entry map (append-merge)."""
    raw = sandbox.read(manifest_rel)
    if not raw:
        return {}
    try:
        entries = json.loads(raw)
    except (ValueError, TypeError):
        return {}
    if not isinstance(entries, list):
        return {}
    out: dict[str, dict] = {}
    for entry in entries:
        if isinstance(entry, dict) and isinstance(entry.get("name"), str):
            out[entry["name"]] = entry
    return out


def _write_bytes(sandbox: RunSandbox, relpath: str, data: bytes) -> None:
    """Write raw bytes under the traversal-proof ``path_for`` (handles binary docs)."""
    path = sandbox.path_for(relpath)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
