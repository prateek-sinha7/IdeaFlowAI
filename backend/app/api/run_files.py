"""app/api/run_files.py — UPLD-01: owner-scoped document upload for a run.

``POST /api/runs/{id}/files`` lets a run's owner attach documents to an in-flight
(or reopened) run. Accepted bytes land under the run's on-disk ``RunSandbox`` at a
RESERVED ``.uploads/`` prefix so agents can ``read_file`` them, and extractable
documents (pdf/docx/pptx) are text-extracted at ingest into a ``.txt`` sidecar +
a ``manifest.json`` entry — the stable contract 30-02's ``uploaded_files``
context provider reads to make the text sticky in every subsequent ``agent_input``.
HTML/HTM files are accepted as raw uploads with no text extraction.

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
    ({pdf,docx,xlsx,pptx,txt,md,csv,json,html,htm}) → 415 on miss; the per-file byte cap
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
    FamilyLockTimeout,
    RunSandbox,
    _UPLOADS_PREFIX,
    _safe_segment,
    family_lock,
    is_deliverable_relpath,
    run_dir_expired,
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


def _resolve_chain_root_or_404(run_id: str, user_id: str) -> str:
    """Resolve the revision root for ``run_id`` or raise HTTP 404.

    Replaces the old ``_resolve_chain_root`` shim (which degraded to ``run_id``
    on failure) with a hard refusal per task 3.3 / Requirement 2 AC 11.

    On ``RevisionRootUnresolved`` (cycle, missing ancestor, cross-owner ancestry,
    DB error) this function:
      * logs ``visited_count``, ``repeated_node``, and ``reason`` server-side
        (Requirement 2 AC 12) without leaking another owner's data to the client;
      * raises ``HTTPException(404)`` — a generic non-enumerating error
        (Requirement 2 AC 11-12).

    The previous ``_resolve_chain_root`` shim that degraded to ``run_id`` is
    kept as a dead alias for reference only and must not be called by new code.
    """
    from app.api.runs import (
        RevisionRootResolved,
        RevisionRootUnresolved,
        resolve_revision_root,
    )

    db = _get_db()
    try:
        result = resolve_revision_root(db, run_id, user_id)
    finally:
        db.close()
    if isinstance(result, RevisionRootResolved):
        return result.root_id
    assert isinstance(result, RevisionRootUnresolved)
    logger.warning(
        "run_files: revision root unresolved for run=%s reason=%s visited=%d repeated=%s"
        " — refusing request",
        run_id,
        result.reason,
        result.visited_count,
        result.repeated_node,
    )
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Workflow run not found",
    )


# Document-only allow-list (T-30-04): the ext set that may land in the sandbox.
# Images are payload-transient (30-03) → rejected here.
_ALLOWED_EXTS: frozenset[str] = frozenset(
    {"pdf", "docx", "xlsx", "pptx", "txt", "md", "csv", "json", "html", "htm"}
)
# The subset that carries an extractable-text sidecar (the sticky-context source).
# `xlsx` is deliberately absent (spec 019, FR-037): no openpyxl is vendored, so a
# spreadsheet gets no flat sidecar rather than an empty one that reads as "this
# document is blank". Its content reaches an agent through the `documents` tool
# set, which is where FR-024 wants document content regardless.
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


async def _validate_uploads(
    files: list[UploadFile],
) -> list[tuple[str, bytes, str, str]]:
    """Read + validate EVERY file up-front so a single cap rejection writes
    NOTHING to disk (T-30-02). Returns ``[(name, data, ext, mime)]``.

    Extracted verbatim from ``upload_files`` so the pre-run staging endpoint
    enforces the IDENTICAL caps — one definition of an acceptable document.
    """
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
    return validated


# ── Pre-run staging (UPLD-05) ───────────────────────────────────────────────
# The launch surfaces attach documents BEFORE a run id exists, so raw files had
# nowhere to go and were discarded client-side after text extraction. Staging
# holds them owner-scoped until launch: POST /uploads/stage validates with the
# EXACT upload caps and parks the bytes in a per-user staging sandbox; the
# launch path calls ``ingest_staged_uploads`` after the run row is minted and
# BEFORE the engine drives the first agent, so `.uploads/` is fully populated
# when any agent calls ``file_info()`` — no race. Stage ids are server-minted
# uuid4 hex (never client input on the filesystem path).

_STAGE_RUN_PREFIX = "staged-"
_STAGE_ID_RE = re.compile(r"^[0-9a-f]{32}$")


@router.post("/uploads/stage")
async def stage_files(
    files: list[UploadFile],
    current_user: User = Depends(get_current_user),
):
    """Validate + park documents for a not-yet-launched run.

    Returns ``{stage_id, files: [name, ...]}``; the client passes
    ``staged_upload_ids: [stage_id, ...]`` in the ``POST /api/runs`` body.
    """
    validated = await _validate_uploads(files)
    stage_id = uuid.uuid4().hex
    sandbox = RunSandbox(
        current_user.id, f"{_STAGE_RUN_PREFIX}{stage_id}", runs_root=settings.RUNS_ROOT
    )
    sandbox.ensure()
    used: set[str] = set()
    names: list[str] = []
    for name, data, ext, mime in validated:
        safe = _dedupe_segment(
            _safe_segment(os.path.basename(name), fallback="upload"), used
        )
        used.add(safe)
        _write_bytes(sandbox, safe, data)
        names.append(safe)
    logger.info(
        "staged upload: user=%s stage=%s files=%d",
        current_user.id,
        stage_id,
        len(names),
    )
    return {"stage_id": stage_id, "files": names}


async def ingest_staged_uploads(
    *,
    user_id: str,
    workspace_id: str | None,
    run_id: str,
    stage_ids: list[str],
) -> None:
    """Move staged documents into a freshly-minted run's ``.uploads/``.

    Called by the launch path (run_commands) after the WorkflowRun row exists and
    before the engine starts, under the launching user's own identity — the stage
    dir lives under that user's RUNS_ROOT segment, so a foreign id simply resolves
    to a missing dir. Best-effort per stage: a missing/empty stage is logged and
    skipped, never fails the launch — and, since the docstring's promise wasn't
    actually implemented (BUG 1 below), a per-stage EXCEPTION is now caught here
    too, not just the missing/empty cases.

    BUG 1 (verified): this loop used to run with NO per-stage try/except. The
    caller (``run_commands.py``) wraps the WHOLE ``ingest_staged_uploads`` call in
    one blanket ``except Exception`` "never strand the launch" — so a single
    stage raising (a corrupt upload, a transient disk error, anything) propagated
    out of THIS loop, past that blanket catch, silently dropping every stage
    still queued after the failing one in ``stage_ids`` order — not just the
    failing file. Reproduced directly: 5 staged files, the 4th's persist forced
    to raise → only the first 3 land; the 4th AND the 5th are gone with zero
    trace (no file, no manifest entry) — exactly the reported symptom. Each
    stage's persist now runs in its own try/except so one bad document can never
    take its siblings down with it.

    BUG 2 (fixed on the client, not here): ``stage_ids`` used to be
    ``stagedUploads.map(s => s.stageId)`` on the client, appended in
    STAGE-RESPONSE-ARRIVAL order (the N stage POSTs fire concurrently) — not the
    order the user attached the files. A prior backend-side fix tried to recover
    order from a ``.seq`` sidecar stamping the order the server BEGAN handling
    each POST; that is also just race order and was provably wrong (5 files
    attached 1..5 landed as 3,2,1,5,4). Only the client knows true attach order,
    so the client now stamps a per-file attach index at attach time (before the
    async stage call) and sorts by it before sending ``staged_upload_ids`` — this
    function simply trusts and preserves the given ``stage_ids`` order.
    """
    import shutil

    from agents.authz import ScopedStore

    store = ScopedStore(owner_id=user_id, workspace_id=workspace_id)
    for stage_id in stage_ids:
        if not _STAGE_ID_RE.match(stage_id or ""):
            logger.warning(
                "ignoring malformed stage id %r for run %s", stage_id, run_id
            )
            continue
        staging = RunSandbox(
            user_id, f"{_STAGE_RUN_PREFIX}{stage_id}", runs_root=settings.RUNS_ROOT
        )
        if not staging.root.is_dir():
            logger.warning("stage %s not found for run %s — skipped", stage_id, run_id)
            continue
        validated: list[tuple[str, bytes, str, str]] = []
        for entry in sorted(staging.root.iterdir()):
            # Skip our own reserved sidecar(s) — never an uploaded document
            # (`_safe_segment` strips leading dots from every real upload name).
            if entry.is_file() and not entry.name.startswith("."):
                validated.append(
                    (
                        entry.name,
                        entry.read_bytes(),
                        _ext_of(entry.name),
                        "application/octet-stream",
                    )
                )
        failed = False
        if validated:
            try:
                await _persist_documents(
                    store,
                    user_id=user_id,
                    workspace_id=workspace_id,
                    run_id=run_id,
                    validated=validated,
                )
            except Exception as exc:  # noqa: BLE001 — one stage must never drop the rest
                # BUG 1 fix: isolate this stage's failure so it cannot drop every
                # stage queued after it — logged loudly, launch still proceeds.
                # The staging dir is still cleaned up below: a failed ingest must
                # not leak the temp stage dir forever either.
                #
                # Log the exception TYPE ONLY — never the exception itself and never
                # a traceback. SQLAlchemy's ``IntegrityError.__str__`` embeds the
                # failed INSERT's bound parameters, and for this call those
                # parameters are the EXTRACTED TEXT OF THE USER'S DOCUMENT. That is
                # precisely the leak this ingest path was fixed for; a
                # ``logger.exception`` here would quietly reintroduce it at a new
                # call site. Stage id + run id are enough to locate the failure.
                failed = True
                logger.warning(
                    "staged upload ingest failed for stage=%s run=%s (%s) — skipped, "
                    "other staged documents still processed",
                    stage_id,
                    run_id,
                    type(exc).__name__,
                )
        shutil.rmtree(staging.root, ignore_errors=True)
        logger.info(
            "staged upload ingested: run=%s stage=%s files=%d failed=%s",
            run_id,
            stage_id,
            0 if failed else len(validated),
            failed,
        )


async def _persist_documents(
    store,
    *,
    user_id: str,
    workspace_id: str | None,
    run_id: str,
    validated: list[tuple[str, bytes, str, str]],
) -> list[dict]:
    """Write validated documents into the run sandbox ``.uploads/`` — raw bytes,
    extracted-text sidecars, manifest merge, and the RESUME-12 durable mirror.
    Extracted verbatim from ``upload_files`` so the launch-time staged-upload
    ingest persists documents byte-identically to a live-run upload.
    """
    # ── All caps passed — NOW persist under the reserved .uploads/ prefix. Every
    #    write resolves through RunSandbox.path_for (traversal-proof, T-30-03). ────
    # Task 5.2 / 3.3: resolve to the revision root so uploads land in the shared
    # family directory (Req 2 AC7). Raises 404 on RevisionRootUnresolved.
    _chain_root_id = _resolve_chain_root_or_404(run_id, user_id)
    sandbox = RunSandbox(user_id, _chain_root_id, runs_root=settings.RUNS_ROOT)
    sandbox.ensure()

    manifest_rel = f"{_UPLOADS_PREFIX}manifest.json"
    # ── Family lock (task 8.4, Requirement 10) ─────────────────────────────────
    # Acquire the cross-process family lock BEFORE the per-sandbox manifest lock.
    # This is the documented lock order: family → manifest.  Never reversed.
    #
    # Admission per the five-state table:
    #   • No active run / agent step executing / gate-paused → lock is free or
    #     released quickly; the default timeout grants a bounded wait.
    #   • Terminal finalization holds the lock → FamilyLockTimeout after the
    #     ceiling expires → 409 (generic retryable; the client may retry once
    #     finalization completes).
    #   • Restore holds the lock → same path → 409 (generic retryable).
    #
    # The 409 reason is intentionally opaque: it does not reveal which process
    # holds the lock or the family ancestry of the run.
    try:
        _family_lock_ctx = family_lock(
            user_id,
            _chain_root_id,
            runs_root=settings.RUNS_ROOT,
        )
        _family_lock_ctx.__enter__()
    except FamilyLockTimeout:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Run is temporarily unavailable for uploads. Please retry shortly.",
        )
    try:
        # Hold the per-run manifest lock across the WHOLE dedupe→write→merge section
        # so a concurrent upload cannot dedupe against a stale snapshot or drop
        # entries in a last-write-wins race (WR-02).  The family lock is already held,
        # so this inner acquisition preserves the family → manifest order.
        with _manifest_lock(sandbox):
            manifest = _read_manifest(sandbox, manifest_rel)
            # Seed with the names already stored for this run so a new upload never
            # silently overwrites a prior one either (WR-01) — every stored file keeps
            # a distinct name.
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
            # (user_id / workspace_id) — NEVER a client payload. Generic
            # labels (``upload_text`` / ``upload``), ``task_id=None`` (SC-001/INV-1).
            # ``force_db_version=True``: the endpoint has no shared in-memory
            # ArtifactGraph, so the DB COUNT(*) WHERE (run_id, kind)+1 is the
            # authoritative monotonic version (the 46-02 idiom). A DB hiccup must not
            # fail an otherwise-valid upload — catch ONLY SQLAlchemyError (loud warning
            # + continue), re-raise everything else (no blanket swallow). The caps ran
            # up-front, so a rejected upload never reaches this block.
            #
            # ``workspace_id`` is NOT always known here, and that is not a DB hiccup —
            # ``artifact_refs.workspace_id`` is NOT NULL, but the per-run ``workspaces``
            # row is minted LAZILY by the engine (``ScopedStore.create_workspace`` in
            # ``agents/execution_engine/engine.py``, at ``execute()`` entry), not at
            # launch. ``ingest_staged_uploads`` (run_commands.py) runs right after the
            # ``WorkflowRun`` row commits and BEFORE the engine task is even spawned, so
            # every staged→launch upload reaches this call with ``workspace_id=None`` —
            # deterministically, not as a rare race. Minting a workspace HERE instead
            # would orphan it: a non-resumed run always mints its OWN fresh workspace
            # unconditionally and re-stamps ``workflow_runs.workspace_id`` over whatever
            # this endpoint wrote, so rows dual-written under an id minted here would
            # become permanently unreachable by every owner+workspace-scoped reader
            # (mismatched workspace_id). Skip the write rather than attempt a doomed
            # insert or mint orphaned data — the sandbox files this function just wrote
            # are the live source of truth for the run's whole lifetime regardless (the
            # ``uploaded_files`` provider reads disk FIRST; the durable mirror is only a
            # wiped-sandbox RESUME fallback — see agents/capabilities/context_providers/
            # uploaded_files.py). A later live ``upload_files`` call on an already-
            # executing run (workspace already minted) still dual-writes below as before.
            if workspace_id is None:
                logger.warning(
                    "upload_text durable mirror skipped for run %s — no workspace_id yet "
                    "(%d file(s)); sandbox copy is authoritative until the run starts",
                    run_id,
                    len(durable_contribs),
                )
            else:
                from agents.artifacts.graph import ArtifactRef

                try:
                    for location, content in durable_contribs:
                        await store.write_ref(
                            ArtifactRef(
                                id=str(uuid.uuid4()),
                                kind="upload_text",
                                owner_id=user_id,
                                workspace_id=workspace_id,
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
                    # Log the exception TYPE + the affected locations only — NEVER `%s`
                    # the exception object itself. A SQLAlchemy IntegrityError's __str__
                    # embeds the full failed INSERT statement, including every bound
                    # param (i.e. the uploaded document's CONTENT), which is exactly
                    # what was leaking into the log before this fix.
                    logger.warning(
                        "upload_text durable mirror failed for run %s (%s) — DB write "
                        "degraded for %d file(s): %r",
                        run_id,
                        type(exc).__name__,
                        len(durable_contribs),
                        [loc for loc, _ in durable_contribs],
                    )
    finally:
        _family_lock_ctx.__exit__(None, None, None)

    return results


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

    validated = await _validate_uploads(files)
    aggregate = sum(len(data) for _, data, _, _ in validated)

    results = await _persist_documents(
        store,
        user_id=current_user.id,
        workspace_id=wr_workspace,
        run_id=run_id,
        validated=validated,
    )
    logger.info(
        "run upload: user=%s run=%s files=%d aggregate_bytes=%d",
        current_user.id,
        run_id,
        len(results),
        aggregate,
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

# Every file the Workspace tab lists is readable here (the listing hides only git
# metadata), so a listed .uploads/, .logs/ or .extract/ file opens rather than 404s.

# Per-file read cap. A sandbox can hold an arbitrarily large agent-written file;
# this endpoint feeds a browser preview, so it refuses rather than streams.
# Raised from 2 MB when the viewer learned to show images and PDFs: a deck's
# `.verify/presentation.pdf` is ~0.5 MB for 12 slides, so a long deck was the
# one artifact the gate writes that the cap would have refused to show.
# Raised from 8 MB to the workspace-zip cap when the backlog workflow's
# Backlog.pdf and Backlog.zip (14-18 MB) were refused both in the viewer and
# on download.
_SANDBOX_MAX_READ_BYTES = 64 * 1024 * 1024  # 64 MB

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


def _validate_ref(ref: str, sandbox: RunSandbox) -> str:
    """Validate a caller-supplied git ref string against the sandbox's known tags.

    This is the security gate required by Requirement 16: a free-form revspec
    from user input must NEVER be passed to a git subprocess.  git's revspec
    syntax is extremely expressive — ``HEAD~3``, ``@{upstream}``, ``:/message``,
    and shell-injection via ``$(cmd)`` are all valid revspecs that a bare
    ``git show ref:path`` would happily evaluate.

    The only refs this API will ever serve are real version tags (``v1``,
    ``v2``, …).  Validating by exact match against ``list_tags()`` confines
    every downstream git subprocess call to a name that git itself previously
    created and that matches the tag-name character set in practice
    (``[a-zA-Z0-9._-]+``).

    Implementation notes:
    - Duck-typed via ``getattr`` so this function works correctly whether the
      underlying workspace is a ``LocalWorkspace``, a test stub, or ``None``.
    - When ``list_tags()`` is unavailable or raises (e.g. not a git repo), the
      effective tag list is ``[]``, so every ref is rejected — fail-closed.
    - Returns ``ref`` unchanged on success so callers can write
      ``safe_ref = _validate_ref(ref, sandbox)`` inline.

    Raises:
        HTTPException(400): when ``ref`` is not an exact match in the tag list.
    """
    list_tags_fn = getattr(sandbox, "list_tags", lambda: [])
    try:
        valid_tags: list[str] = list_tags_fn()
    except Exception:  # noqa: BLE001 — fail-closed: unknown error → empty list
        valid_tags = []

    if ref not in valid_tags:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="invalid ref",
        )
    return ref


@router.get("/{run_id}/sandbox/refs")
async def list_sandbox_refs(
    run_id: str,
    current_user: User = Depends(get_current_user),
):
    """List the git version tags available for this run's sandbox.

    Returns ``{run_id, refs: ["v1", "v2", ...]}``.  Tags are listed via
    ``LocalWorkspace.list_tags()`` reached by ``getattr`` duck-typing (Requirement 15).

    When the sandbox has no git repo, or tags have not yet been created (e.g. a
    run that is still in progress), ``refs`` is ``[]`` — the UI renders the tag
    picker as empty rather than erroring.

    Requirement 17 AC1 / Requirement 19 AC2.
    """
    await _resolve_owned_run(run_id, current_user)

    _chain_root_id = _resolve_chain_root_or_404(run_id, current_user.id)
    sandbox = RunSandbox(current_user.id, _chain_root_id, runs_root=settings.RUNS_ROOT)
    list_tags_fn = getattr(sandbox, "list_tags", lambda: [])
    try:
        refs: list[str] = list_tags_fn()
    except Exception:  # noqa: BLE001 — fail-open: no tags available
        refs = []
    return {"run_id": run_id, "refs": refs}


@router.get("/{run_id}/sandbox")
async def list_sandbox(
    run_id: str,
    ref: str | None = None,
    current_user: User = Depends(get_current_user),
):
    """List the run workspace: ``{run_id, expired, truncated, files:[...]}``.

    ``expired`` is the real signal for a TTL-swept run — the sandbox sweeper
    removes the whole run dir after ``RUN_DIR_TTL_HOURS``, and an empty list
    would otherwise be indistinguishable from a run that wrote nothing. The UI
    renders a "workspace expired" state on it rather than a bare empty tree.

    ``truncated`` says the listing hit a cap; the caps live in ``sandbox.py``.

    When ``ref`` is supplied it must be an exact match for one of the sandbox's
    version tags (validated by ``_validate_ref``).  The listing is then built
    from ``git ls-tree -r <ref>`` rather than the live working tree — HEAD never
    moves (Requirement 17 AC2/3, Requirement 18 AC1).  Omitting ``ref`` is
    byte-identical to today's behaviour (Requirement 17 AC4).
    """
    await _resolve_owned_run(run_id, current_user)

    # Task 5.2 / 3.3: resolve to the revision root so the listing shows the shared
    # family directory (Req 2 AC7). Raises 404 on RevisionRootUnresolved.
    _chain_root_id = _resolve_chain_root_or_404(run_id, current_user.id)
    sandbox = RunSandbox(current_user.id, _chain_root_id, runs_root=settings.RUNS_ROOT)
    expired = run_dir_expired(sandbox.root)

    # Ref-scoped listing (Requirement 17 AC2): when a validated ref is provided
    # use git ls-tree instead of the live working tree.
    # ISS-893: a swept sandbox has no tags, so validating first turned `expired`
    # into a 400. Expiry wins, as it does in the zip and file routes; the live
    # branch below returns the `expired: true` payload.
    if ref is not None and not expired:
        safe_ref = _validate_ref(ref, sandbox)
        list_files_fn = getattr(sandbox, "list_files_at_ref", None)
        if list_files_fn is not None:
            raw_paths = list_files_fn(safe_ref)
        else:
            raw_paths = []
        # ISS-720: `git ls-tree --name-only` drops the object-size column, so this
        # branch used to report `size: 0` for every row. One extra `ls-tree -r -l`
        # for the whole tree carries the real blob sizes; a path missing from the
        # map (a submodule, whose size column is "-") still reads 0.
        sizes_fn = getattr(sandbox, "file_sizes_at_ref", None)
        sizes: dict[str, int] = (
            sizes_fn(safe_ref) if (raw_paths and sizes_fn is not None) else {}
        )
        files_payload = [
            {
                "path": p,
                "size": int(sizes.get(p, 0)),
                "kind": kind,
                "text": kind == "text",
                "deliverable": is_deliverable_relpath(p),
            }
            for p in raw_paths
            for kind in (_sandbox_kind(p.rsplit("/", 1)[-1]),)
        ]
        return {
            "run_id": run_id,
            "expired": expired,
            "truncated": False,
            "ref": safe_ref,
            "files": files_payload,
        }

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
    ref: str | None = None,
    current_user: User = Depends(get_current_user),
):
    """The whole workspace as one zip.

    The alternative the Files tab uses — fire one download per file, 150ms
    apart — is blocked by every browser after a handful, and a ppt_v2 workspace
    is 36 files. Built with the stdlib ``zipfile``, so no dependency.

    Contents are exactly ``list_files()`` — every sandbox file, ``.git/`` included,
    so the archive holds what the workspace view showed and nothing else. Every entry is
    re-resolved through ``path_for``, which raises on any escape — a symlink
    planted in the sandbox cannot pull a host file into the archive.

    When ``ref`` is supplied the zip is built from ``git archive <ref>``
    entirely in memory — HEAD never moves (Requirement 17 AC2/3, Requirement 18
    AC1).  Omitting ``ref`` is byte-identical to today (Requirement 17 AC4).
    """
    import io
    import zipfile

    from fastapi.responses import Response

    await _resolve_owned_run(run_id, current_user)

    # Task 5.2 / 3.3: resolve to the revision root so the zip archive draws from
    # the shared family directory (Req 2 AC7). Raises 404 on RevisionRootUnresolved.
    _chain_root_id = _resolve_chain_root_or_404(run_id, current_user.id)
    sandbox = RunSandbox(current_user.id, _chain_root_id, runs_root=settings.RUNS_ROOT)
    if run_dir_expired(sandbox.root):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Workspace expired"
        )

    stem = f"workspace-{_safe_segment(run_id, fallback='run')[:8]}"

    # Ref-scoped zip (Requirement 17 AC2): serve git archive bytes directly —
    # HEAD never moves.
    if ref is not None:
        from fastapi.responses import Response as _Response  # noqa: F811

        safe_ref = _validate_ref(ref, sandbox)
        archive_fn = getattr(sandbox, "archive_at_ref", None)
        if archive_fn is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="ref-scoped archive not supported",
            )
        # ISS-704: this branch returns before the live path's cap check below, so
        # until blob sizes were readable at a ref (ISS-720) it had no cap at all.
        # Same ceiling, same 413, measured the same way — uncompressed total,
        # checked BEFORE `git archive` builds the whole thing in memory.
        sizes_fn = getattr(sandbox, "file_sizes_at_ref", None)
        if sizes_fn is not None:
            ref_total = sum(sizes_fn(safe_ref).values())
            if ref_total > _SANDBOX_MAX_ZIP_BYTES:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=(
                        f"Workspace too large to archive ({ref_total} bytes; "
                        f"limit {_SANDBOX_MAX_ZIP_BYTES})"
                    ),
                )
        try:
            archive_bytes: bytes = archive_fn(safe_ref)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="could not build ref-scoped archive",
            ) from exc
        return _Response(
            content=archive_bytes,
            media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="{stem}-{safe_ref}.zip"',
                "X-Content-Type-Options": "nosniff",
            },
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
    ref: str | None = None,
    current_user: User = Depends(get_current_user),
):
    """Return ONE workspace file's bytes.

    Whitelisted text extensions come back as ``text/plain; charset=utf-8``
    inline; everything else as ``application/octet-stream`` attachment — see
    ``_SANDBOX_INLINE_EXTS`` for why that distinction is the security boundary.
    ``X-Content-Type-Options: nosniff`` on both, so a browser cannot re-type an
    octet-stream body back into something executable.

    When ``ref`` is supplied the file bytes come from ``git show <ref>:<path>``
    — HEAD never moves (Requirement 17 AC2/3, Requirement 18 AC1).  Omitting
    ``ref`` is byte-identical to today (Requirement 17 AC4).
    """
    from fastapi.responses import Response

    await _resolve_owned_run(run_id, current_user)

    # Task 5.2 / 3.3: resolve to the revision root so single-file reads come from
    # the shared family directory (Req 2 AC7). Raises 404 on RevisionRootUnresolved.
    _chain_root_id = _resolve_chain_root_or_404(run_id, current_user.id)
    sandbox = RunSandbox(current_user.id, _chain_root_id, runs_root=settings.RUNS_ROOT)
    if run_dir_expired(sandbox.root):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Workspace expired"
        )

    rel = path.lstrip("/")

    # Ref-scoped single-file read (Requirement 17 AC2): use git show when a
    # validated ref is supplied — HEAD never moves.
    if ref is not None:
        safe_ref = _validate_ref(ref, sandbox)
        read_at_ref_fn = getattr(sandbox, "read_file_at_ref", None)
        if read_at_ref_fn is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="ref-scoped reads not supported",
            )
        try:
            data_at_ref: bytes = read_at_ref_fn(safe_ref, rel)
        except Exception:  # noqa: BLE001
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="File not found"
            ) from None
        ext = _ext_of(rel.rsplit("/", 1)[-1])
        safe_name = (
            re.sub(r"[^A-Za-z0-9._-]", "_", rel.rsplit("/", 1)[-1])[:80] or "file"
        )
        if ext in _SANDBOX_INLINE_EXTS:
            return Response(
                content=data_at_ref,
                media_type="text/plain; charset=utf-8",
                headers={
                    "Content-Disposition": f'inline; filename="{safe_name}"',
                    "X-Content-Type-Options": "nosniff",
                },
            )
        return Response(
            content=data_at_ref,
            media_type=_SANDBOX_MEDIA_TYPES.get(ext, "application/octet-stream"),
            headers={
                "Content-Disposition": f'attachment; filename="{safe_name}"',
                "X-Content-Type-Options": "nosniff",
            },
        )

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
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="File not found"
        )

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
