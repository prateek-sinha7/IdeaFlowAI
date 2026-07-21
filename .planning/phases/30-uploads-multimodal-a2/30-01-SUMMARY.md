---
phase: 30-uploads-multimodal-a2
plan: 01
subsystem: api
tags: [fastapi, multipart-upload, run-sandbox, document-extraction, idor, pypdf, python-docx, python-pptx]

# Dependency graph
requires:
  - phase: 09-runtime-workspace
    provides: RunSandbox (per-user/per-run traversal-proof disk dir) + serialize_sandbox_deliverable
  - phase: 29-chat-backbone
    provides: two-layer owner check (WorkflowRun.user_id ORM filter -> ScopedStore.get_run default-deny -> 404) in run_commands.post_message
provides:
  - "POST /api/runs/{id}/files — owner-scoped, capped, traversal-proof document upload landing bytes under the reserved .uploads/ sandbox prefix"
  - "extract_upload_text() — the SINGLE PDF/DOCX/PPTX extraction impl (INV-12); /api/files/extract-text now calls it"
  - "reserved .uploads/ prefix + manifest.json contract ({name, mime, has_text}) — the sticky-context SOURCE 30-02's uploaded_files provider consumes"
  - "sandbox._UPLOADS_PREFIX excluded from the deliverable walk (uploads never pollute the deliverable; INV-3 dormant on goldens)"
affects: [30-02, uploaded_files-context-provider, sticky-context]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Two-layer owner check reused verbatim from run_commands.post_message (user_id ORM filter -> ScopedStore default-deny -> 404, IDOR never 403)"
    - "Caps read + validated up-front across all files BEFORE any sandbox write (no partial-write on a later rejection)"
    - "All sandbox writes route through RunSandbox.path_for (traversal-proof) under a reserved prefix"
    - "Single extraction impl factored out; endpoint delegates (INV-12 no dual impl)"
    - "Prefix-aware deliverable exclusion alongside the exact-name exclude (dormant on goldens, INV-3)"

key-files:
  created:
    - backend/app/api/run_files.py
    - backend/tests/unit/test_run_files_upload.py
  modified:
    - backend/app/api/file_extract.py
    - backend/app/agents/sandbox.py
    - backend/app/main.py

key-decisions:
  - "Documents-only endpoint: ext allow-list {pdf,docx,pptx,txt,md,csv,json}; image mimes/exts -> 415 (images are payload-transient, 30-03)"
  - "Per-file cap imported from file_extract._MAX_FILE_BYTES (single source, 10 MB); count cap 20; aggregate cap 40 MB — all -> 413 pre-write"
  - "has_text in manifest means 'has an extracted-text .txt sidecar' — only pdf/docx/pptx with non-empty extraction; a .txt upload lands raw with has_text False"
  - "Raw bytes written via path_for().write_bytes() (handles binary docs); extracted text capped at settings.BRIEF_MAX_CHARS"
  - "UPLD-03 only HALF-delivered here (the extract-to-sidecar SOURCE); the context_provider:uploaded_files capability + sticky-in-every-agent_input proof is 30-02"

patterns-established:
  - "Reserved sandbox prefix (.uploads/) for owner-ingress files invisible to the deliverable"
  - "Manifest.json append-merge (name-keyed) as the stable cross-plan contract a downstream context provider reads"

requirements-completed: [UPLD-01]

# Metrics
duration: ~18min
completed: 2026-07-08
---

# Phase 30 Plan 01: UPLD-01 Document Upload Endpoint Summary

**Owner-scoped, capped, traversal-proof `POST /api/runs/{id}/files` that lands documents under the run sandbox's reserved `.uploads/` prefix with a text-extraction sidecar + manifest — the sticky-context source for 30-02 — with zero new tables and goldens byte-identical.**

## Performance

- **Duration:** ~18 min
- **Completed:** 2026-07-08
- **Tasks:** 2
- **Files modified:** 5 (2 created, 3 modified)

## Accomplishments
- New `POST /api/runs/{id}/files` endpoint: the exact two-layer owner check (WorkflowRun.user_id ORM filter → `ScopedStore.get_run` default-deny → 404, IDOR never 403), document caps enforced before any write, and accepted bytes landing under the reserved `.uploads/` sandbox prefix for agent `read_file`.
- Factored the PDF/DOCX/PPTX extractors into ONE `extract_upload_text()` (INV-12); the existing `/api/files/extract-text` endpoint now delegates to it — no dual extraction impl.
- Extractable docs get a `.uploads/<name>.txt` sidecar + a `manifest.json` entry `{name, mime, has_text}` — the stable contract 30-02's `uploaded_files` provider will read.
- Taught the sandbox deliverable walk to skip the `.uploads/` subtree (prefix-aware exclusion), so uploads never pollute the deliverable and golden runs stay byte-identical (INV-3 dormancy).

## Task Commits

Each task was committed atomically:

1. **Task 1: Reusable extractor + upload endpoint (owner check + caps + sandbox landing)** — `ac7596de` (feat)
2. **Task 2: Upload endpoint test suite (IDOR, caps, sandbox landing, deliverable exclusion, INV-3)** — `5f607b43` (test)

**Plan metadata:** _(this commit)_ (docs: complete plan)

## Files Created/Modified
- `backend/app/api/run_files.py` — the UPLD-01 upload endpoint (owner check, caps, `.uploads/` landing + sidecar + manifest).
- `backend/app/api/file_extract.py` — added `extract_upload_text()` (single impl); `extract_text` endpoint delegates to it.
- `backend/app/agents/sandbox.py` — added `_UPLOADS_PREFIX`; `_collect_deliverable_relpaths` skips the `.uploads/` subtree.
- `backend/app/main.py` — registered `run_files_router` beside `file_extract_router`.
- `backend/tests/unit/test_run_files_upload.py` — 13-test offline suite.

## Decisions Made
- **Documents-only** (POR §2 D-07 amended): ext allow-list `{pdf,docx,pptx,txt,md,csv,json}`; image mimes/exts → 415 (images are payload-transient, handled on the message path in 30-03).
- **Caps** — per-file `file_extract._MAX_FILE_BYTES` (10 MB, imported single source) → 413; count ≤ 20 → 413; aggregate 40 MB → 413. All validated up-front so a single rejection writes nothing.
- **`has_text`** in the manifest means "carries an extracted-text sidecar" — only `pdf/docx/pptx` with non-empty extraction; a `.txt` upload lands raw with `has_text: False`.
- **UPLD-03 is only half-delivered here** — this plan builds the extract-to-`.uploads` sidecar (the sticky-context SOURCE). The `context_provider:uploaded_files` capability and the "present in every subsequent `agent_input`" proof are 30-02. Only UPLD-01 is marked complete.

## Deviations from Plan

None - plan executed exactly as written.

The plan's `_get_db` seam was reused by read-only import from `app.api.websocket` (the same pattern `run_commands.post_message` uses) so the endpoint's Layer-1 owner query is monkeypatch-testable and cannot diverge from the established owner-check path. This is a faithful mirror of the referenced pattern, not a deviation.

## Issues Encountered
None. Binary-safe writes required `path_for().write_bytes()` (rather than the text-only `RunSandbox.write`) so binary PDFs round-trip byte-for-byte — anticipated during implementation, not a problem.

## Verification

- `python3.11 -m pytest tests/unit/test_run_files_upload.py -x -q` → **13 passed** (offline).
- `/opt/homebrew/bin/lint-imports` → **4 kept, 0 broken**.
- `tests/agents/test_sandbox_deliverable.py` → **13 passed** (byte-oracle unchanged, INV-3 dormancy confirmed — the `.uploads/` exclusion is inert when no upload exists).
- No golden fixtures changed; no new tables / migrations.

**DEFERRED-to-live:** none required — the endpoint, caps, owner check, extraction, and deliverable exclusion are all offline-provable and proven. No live server / Bedrock / SSO check is needed for UPLD-01.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- The `.uploads/` prefix, `manifest.json` `{name, mime, has_text}` contract, and `.txt` sidecars are in place — the exact surface 30-02's `context_provider:uploaded_files` will read to make uploaded document text sticky in every subsequent `agent_input`.
- UPLD-03 remains **partially** delivered (source built; provider is 30-02).

## Self-Check: PASSED

- Files exist: `run_files.py`, `test_run_files_upload.py`, `30-01-SUMMARY.md` — all FOUND.
- Commits exist: `ac7596de` (feat), `5f607b43` (test), `701d7392` (docs) — all FOUND.

---
*Phase: 30-uploads-multimodal-a2*
*Completed: 2026-07-08*
