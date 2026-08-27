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

import hashlib
import json
import logging
import os
import re
import sys
import uuid
from contextlib import contextmanager

# fcntl is Unix-only — not available on Windows. Use a no-op shim on Windows.
if sys.platform != "win32":
    import fcntl
else:
    fcntl = None  # type: ignore[assignment]

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status

from app.agents.sandbox import (
    RunSandbox,
    _UPLOADS_PREFIX,
    _safe_segment,
    is_deliverable_relpath,
)
from app.api.file_extract import _MAX_FILE_BYTES, extract_upload_text
from app.core.config import settings
from app.core.dependencies import get_current_user
from app.models.user import User
from app.models.workflow import WorkflowRun

# READ-ONLY reuse of the SAME owner-check DB seam ``run_commands.post_message``
# uses, so the two upload/command paths cannot diverge on ownership (LOCK — no
# symbol is added to websocket.py; the endpoint is monkeypatch-testable via this
# module reference exactly like run_commands).
from app.api.run_engine import _get_db

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
# Bounded read chunk (WR-03): stream each multipart part in 64 KB chunks and abort as
# soon as the running size crosses the per-file cap, so an over-cap part is never
# buffered whole before the 413 fires.
_UPLOAD_CHUNK = 64 * 1024


def _ext_of(filename: str) -> str:
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


async def _read_capped(upload: UploadFile, limit: int) -> "bytes | None":
    """Read ``upload`` in bounded chunks, returning its bytes — or ``None`` once the
    running size exceeds ``limit`` (WR-03).

    The per-file cap was previously enforced only AFTER ``await upload.read()`` had
    materialized the ENTIRE part into one in-memory ``bytes``; a caller could force the
    server to fully buffer an arbitrarily large part (and up to 20 of them per request)
    before the 413 fired. Streaming with early-abort bounds our own buffer at ``limit``
    and rejects an over-cap part without reading the rest.
    """
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await upload.read(_UPLOAD_CHUNK)
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            return None
        chunks.append(chunk)
    return b"".join(chunks)


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

        data = await _read_capped(upload, _MAX_FILE_BYTES)
        if data is None:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=(
                    f"File too large: {name!r} "
                    f"(exceeds the per-file limit of {_MAX_FILE_BYTES // 1024} KB)"
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
    # Hold the per-run manifest lock across the WHOLE dedupe→write→merge section so a
    # concurrent upload cannot dedupe against a stale snapshot or drop entries in a
    # last-write-wins race (WR-02).
    with _manifest_lock(sandbox):
        manifest = _read_manifest(sandbox, manifest_rel)
        # Seed with the names already stored for this run so a new upload never silently
        # overwrites a prior one either (WR-01) — every stored file keeps a distinct name.
        used_names: set[str] = set(manifest)
        results: list[dict] = []
        # (location, content) contributions for the RESUME-12 durable mirror —
        # accumulated as we write disk, flushed durably after the manifest write.
        durable_contribs: list[tuple[str, str]] = []

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
                    # Mirror the EXACT sidecar str (not bytes) durably (RESUME-12).
                    durable_contribs.append((f"{raw_rel}.txt", capped))

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

        # Compute the manifest JSON ONCE so the disk bytes and the durable row
        # content are byte-identical (the provider's byte-equivalence target).
        manifest_json = json.dumps(list(manifest.values()), ensure_ascii=False)
        _write_bytes(sandbox, manifest_rel, manifest_json.encode("utf-8"))
        durable_contribs.append((manifest_rel, manifest_json))

        # ── RESUME-12: durable dual-write of the upload_text mirror ──────────────
        # Best-effort mirror of each extracted-text sidecar + the manifest snapshot
        # as owner+workspace-scoped, immutable ``artifact_refs`` rows, so a resumed
        # run on a WIPED sandbox keeps its uploaded-document context. Rows are
        # written ONLY from the already-owner-checked Layer-2 ``store`` values
        # (current_user.id / wr_workspace) — NEVER a client payload. Generic
        # labels (``upload_text`` / ``upload``), ``task_id=None`` (SC-001/INV-1).
        # ``force_db_version=True``: the endpoint has no shared in-memory
        # ArtifactGraph, so the DB COUNT(*) WHERE (run_id, kind)+1 is the
        # authoritative monotonic version (the 46-02 idiom). A DB hiccup must not
        # fail an otherwise-valid upload — catch ONLY SQLAlchemyError (loud warning
        # + continue), re-raise everything else (no blanket swallow). The caps ran
        # up-front, so a rejected upload never reaches this block.
        from agents.artifacts.graph import ArtifactRef

        try:
            for location, content in durable_contribs:
                await store.write_ref(
                    ArtifactRef(
                        id=str(uuid.uuid4()),
                        kind="upload_text",
                        owner_id=current_user.id,
                        workspace_id=wr_workspace,
                        run_id=run_id,
                        producer_step="upload",
                        producer_agent="upload",
                        task_id=None,
                        content=content,
                        content_hash=hashlib.sha256(
                            content.encode("utf-8")
                        ).hexdigest(),
                        location=location,
                        version=1,  # ignored — force_db_version recomputes
                    ),
                    force_db_version=True,
                )
        except Exception as exc:  # noqa: BLE001 — best-effort mirror, never fail the upload
            from sqlalchemy.exc import SQLAlchemyError

            if not isinstance(exc, SQLAlchemyError):
                raise
            logger.warning(
                "upload_text durable mirror failed for run %s (%s) — DB write degraded",
                run_id, exc,
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


@contextmanager
def _manifest_lock(sandbox: RunSandbox):
    """Serialize the per-run ``.uploads`` manifest read-merge-write across concurrent
    uploads (WR-02).

    The manifest is loaded, merged with the new entries in memory, and written back as a
    non-atomic read-modify-write. Two ``POST /files`` requests for the SAME run (two
    browser tabs, or a client retry racing the original) could otherwise both read the
    same snapshot and last-write-wins — the loser's raw files + sidecars still land on
    disk, but its manifest entries are lost, so ``uploaded_files`` (which drives entirely
    off the manifest) silently never surfaces that document even though the request
    returned 200. A POSIX advisory lock on a dedicated lock file makes the whole
    dedupe→write→merge section mutually exclusive ACROSS processes (e.g. multiple uvicorn
    workers), not merely within one event loop; a waiter blocks until the holder releases.
    """
    lock_path = sandbox.path_for(f"{_UPLOADS_PREFIX}manifest.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        if fcntl is not None:
            fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        if fcntl is not None:
            fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


# ---------------------------------------------------------------------------
# Workspace browsing (spec 017 phase 2)
# ---------------------------------------------------------------------------
#
# `ppt_v2` is the first workflow whose run leaves TWO artifacts on disk —
# presentation.html and presentation.pptx — and only one of them can be the
# deliverable. Rather than bolt a second `.pptx` row onto FilesTab, these two
# endpoints expose the run sandbox itself, so both files (and anything else a
# workflow writes) appear in one workspace view.
#
# Read-only by construction: there is no write path here, and both endpoints run
# the SAME two-layer owner check the upload endpoint above uses.

# Per-file read cap. A sandbox can hold an arbitrarily large agent-written file;
# this endpoint feeds a browser preview, so it refuses rather than streams.
# Raised from 2 MB when the viewer learned to show images and PDFs: a deck's
# `.verify/presentation.pdf` is ~0.5 MB for 12 slides, so a long deck was the
# one artifact the gate writes that the cap would have refused to show.
_SANDBOX_MAX_READ_BYTES = 8 * 1024 * 1024  # 8 MB

# The ONLY extensions served inline, and only ever as text/plain.
#
# Everything else — `.html` INCLUDED, and it is the case that matters — goes out
# as application/octet-stream with `Content-Disposition: attachment`. A sandbox
# file is agent-authored content; serving it inline from the API origin with an
# executable content type is stored XSS with the caller's session in scope. The
# deck preview keeps rendering through the iframe's `srcdoc`, which is sandboxed.
#
# This does NOT stop the UI showing an HTML file's SOURCE: a `fetch()` reads the
# body regardless of Content-Disposition, so SandboxTab renders it as text. The
# header only governs what happens if a browser navigates to the URL directly —
# which is precisely the case being denied.
_SANDBOX_INLINE_EXTS: frozenset[str] = frozenset(
    {"txt", "md", "json", "jsonl", "csv", "log", "yaml", "yml"}
)

# Extensions SandboxTab renders as text in the viewer. Wider than the inline set
# on purpose: these are read through `fetch`, never navigated to, so the XSS
# vector the inline rule closes does not apply. `.html` is here and not there.
_SANDBOX_TEXT_EXTS: frozenset[str] = _SANDBOX_INLINE_EXTS | frozenset(
    {"html", "htm", "css", "js", "ts", "tsx", "jsx", "py", "sh", "sql", "xml", "svg"}
)

# Extensions the workspace viewer renders as a picture or an embedded document
# rather than as text or a download prompt — the validator writes both
# (`.verify/slide-NN.png`, `.verify/presentation.pdf`) and "binary file, use
# Download" is a useless answer for evidence a human is meant to look at.
#
# They travel exactly the way a download does: fetched with the auth header and
# handed to the browser as a `blob:` object URL. Nothing is ever navigated to on
# the API origin, so the response keeps `Content-Disposition: attachment` and
# nosniff and the XSS boundary above is untouched. The ONLY thing that changes
# is the Content-Type — a Blob carries its response's type, and `<img>`/`<iframe>`
# need a real one or the browser re-offers a download.
#
# `svg` is deliberately absent. An SVG is a script-bearing document, not a
# picture; it stays in the text set, where it is shown as source.
_SANDBOX_IMAGE_EXTS: frozenset[str] = frozenset(
    {"png", "jpg", "jpeg", "gif", "webp", "bmp", "avif", "ico"}
)

_SANDBOX_MEDIA_TYPES: dict[str, str] = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "gif": "image/gif",
    "webp": "image/webp",
    "bmp": "image/bmp",
    "avif": "image/avif",
    "ico": "image/x-icon",
    "pdf": "application/pdf",
}


def _sandbox_kind(filename: str) -> str:
    """How the workspace viewer should present this file.

    ``text`` | ``image`` | ``pdf`` | ``binary``. One classification, computed
    once in the listing, so the viewer never re-derives it from the extension.
    """
    ext = _ext_of(filename)
    if ext in _SANDBOX_TEXT_EXTS:
        return "text"
    if ext in _SANDBOX_IMAGE_EXTS:
        return "image"
    if ext == "pdf":
        return "pdf"
    return "binary"


async def _resolve_owned_run(run_id: str, current_user: User) -> None:
    """Two-layer owner check for a run id, or 404.

    Lifted verbatim from ``upload_files`` above so the read endpoints cannot
    drift from the write one on ownership. Cross-owner and unknown both yield
    404 — never 403, which would confirm the id exists (IDOR).
    """
    from agents.authz import ScopedStore

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

    store = ScopedStore(owner_id=current_user.id, workspace_id=wr_workspace)
    if await store.get_run(run_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Workflow run not found"
        )


@router.get("/{run_id}/sandbox")
async def list_sandbox(
    run_id: str,
    current_user: User = Depends(get_current_user),
):
    """List the run workspace: ``{run_id, expired, truncated, files:[...]}``.

    ``expired`` is the real signal for a TTL-swept run — the sandbox sweeper
    removes the whole run dir after ``RUN_DIR_TTL_HOURS``, and an empty list
    would otherwise be indistinguishable from a run that wrote nothing. The UI
    renders a "workspace expired" state on it rather than a bare empty tree.

    ``truncated`` says the listing hit a cap; the caps live in ``sandbox.py``.
    """
    await _resolve_owned_run(run_id, current_user)

    sandbox = RunSandbox(current_user.id, run_id, runs_root=settings.RUNS_ROOT)
    expired = not sandbox.root.is_dir()
    files, truncated = sandbox.list_files()
    return {
        "run_id": run_id,
        "expired": expired,
        "truncated": truncated,
        # `text` stays alongside `kind` — it is the older field and the one the
        # viewer's "read this as a string" path keys off.
        #
        # `deliverable` comes from `is_deliverable_relpath`, the SAME predicate
        # the deliverable walk applies. The workspace groups Deliverables from
        # it, which is why nothing in the frontend knows that `PLANNER.md` is
        # not one — that fact lives in `_DELIVERABLE_EXCLUDE` and only there.
        "files": [
            {
                **f,
                "kind": kind,
                "text": kind == "text",
                "deliverable": is_deliverable_relpath(f["path"]),
            }
            for f in files
            for kind in (_sandbox_kind(f["path"].rsplit("/", 1)[-1]),)
        ],
    }


# Uncompressed ceiling for the whole-workspace zip. A run that wrote a GB of
# intermediate output is a bug report, not a download.
_SANDBOX_MAX_ZIP_BYTES = 64 * 1024 * 1024  # 64 MB


@router.get("/{run_id}/sandbox/zip")
async def download_sandbox_zip(
    run_id: str,
    current_user: User = Depends(get_current_user),
):
    """The whole workspace as one zip.

    The alternative the Files tab uses — fire one download per file, 150ms
    apart — is blocked by every browser after a handful, and a ppt_v2 workspace
    is 36 files. Built with the stdlib ``zipfile``, so no dependency.

    Contents are exactly ``list_files()``: the reserved ``.uploads/`` and
    ``.logs/`` subtrees are excluded there and therefore here, so the archive
    holds what the workspace view showed and nothing else. Every entry is
    re-resolved through ``path_for``, which raises on any escape — a symlink
    planted in the sandbox cannot pull a host file into the archive.
    """
    import io
    import zipfile

    from fastapi.responses import Response

    await _resolve_owned_run(run_id, current_user)

    sandbox = RunSandbox(current_user.id, run_id, runs_root=settings.RUNS_ROOT)
    if not sandbox.root.is_dir():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Workspace expired"
        )

    files, _truncated = sandbox.list_files()
    total = sum(int(f.get("size", 0)) for f in files)
    if total > _SANDBOX_MAX_ZIP_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=(
                f"Workspace too large to archive ({total} bytes; "
                f"limit {_SANDBOX_MAX_ZIP_BYTES})"
            ),
        )

    # One top-level directory inside the archive, so unzipping cannot scatter
    # 36 files across whatever the user's download folder already holds.
    stem = f"workspace-{_safe_segment(run_id, fallback='run')[:8]}"

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for entry in files:
            try:
                target = sandbox.path_for(entry["path"])
            except ValueError:
                continue
            if not target.is_file():
                continue
            archive.write(target, arcname=f"{stem}/{entry['path']}")

    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{stem}.zip"',
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/{run_id}/sandbox/file")
async def read_sandbox_file(
    run_id: str,
    path: str,
    current_user: User = Depends(get_current_user),
):
    """Return ONE workspace file's bytes.

    Whitelisted text extensions come back as ``text/plain; charset=utf-8``
    inline; everything else as ``application/octet-stream`` attachment — see
    ``_SANDBOX_INLINE_EXTS`` for why that distinction is the security boundary.
    ``X-Content-Type-Options: nosniff`` on both, so a browser cannot re-type an
    octet-stream body back into something executable.
    """
    from fastapi.responses import Response

    await _resolve_owned_run(run_id, current_user)

    sandbox = RunSandbox(current_user.id, run_id, runs_root=settings.RUNS_ROOT)
    if not sandbox.root.is_dir():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Workspace expired"
        )

    # The reserved subtrees are not part of the workspace view (they are not
    # listed either) — refusing them here means the listing is the complete
    # description of what this endpoint will serve.
    rel = path.lstrip("/")
    if rel.startswith(_UPLOADS_PREFIX) or rel.startswith(".logs/"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    # path_for resolves inside the run dir and raises on any escape, so `..`
    # and an absolute path both land here rather than reading the host FS.
    try:
        target = sandbox.path_for(rel)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid path"
        ) from None

    # is_file() is false for a symlink to a directory, a dangling link, a FIFO
    # and a socket — and a symlink to a file outside the run dir has already
    # been rejected by path_for, which resolves before it checks containment.
    if not target.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    size = target.stat().st_size
    if size > _SANDBOX_MAX_READ_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=(
                f"File too large to preview ({size} bytes; "
                f"limit {_SANDBOX_MAX_READ_BYTES})"
            ),
        )

    data = target.read_bytes()
    ext = _ext_of(target.name)
    # Same sanitiser as the pptx export: bound the alphabet so a filename can
    # never smuggle CR/LF or a quote into the header (response splitting).
    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", target.name)[:80] or "file"

    if ext in _SANDBOX_INLINE_EXTS:
        return Response(
            content=data,
            media_type="text/plain; charset=utf-8",
            headers={
                "Content-Disposition": f'inline; filename="{safe_name}"',
                "X-Content-Type-Options": "nosniff",
            },
        )
    # An image or a PDF goes out with its REAL type so the viewer's Blob can be
    # rendered — still as an attachment, still nosniff: the frontend fetches it
    # and renders a `blob:` URL, and a browser pointed straight at this URL
    # still saves the file rather than opening it on the API origin.
    return Response(
        content=data,
        media_type=_SANDBOX_MEDIA_TYPES.get(ext, "application/octet-stream"),
        headers={
            "Content-Disposition": f'attachment; filename="{safe_name}"',
            "X-Content-Type-Options": "nosniff",
        },
    )
