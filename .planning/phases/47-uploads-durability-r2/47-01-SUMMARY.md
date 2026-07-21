---
phase: 47-uploads-durability-r2
plan: 01
subsystem: api
tags: [uploads, artifact_refs, scoped_store, context_provider, resume, durability, postgres]

# Dependency graph
requires:
  - phase: 30-uploads
    provides: "POST /api/runs/{id}/files ingest + .uploads/ sandbox contract + uploaded_files provider + extract_upload_text single impl"
  - phase: 05-artifact-substrate
    provides: "ArtifactRef dataclass + ARTIFACT_KINDS vocabulary + ScopedStore.write_ref/list_refs default-deny"
  - phase: 33-concierge
    provides: "conversation provider ctx.scoped_store store-read-from-a-provider precedent"
  - phase: 46-rematerialize
    provides: ".uploads/ re-materialization fence + _FILE_KINDS exclusion (Phase-47 fence, already shipped) + location-keyed max-version idiom"
provides:
  - "Durable upload_text mirror at ingest: each extracted-text sidecar + the manifest snapshot persisted as owner+workspace-scoped artifact_refs rows (RESUME-12)"
  - "uploaded_files provider durable fallback via ctx.scoped_store on a wiped sandbox, byte-equivalent to the disk path (RESUME-13)"
  - "Additive upload_text ARTIFACT_KINDS member (no migration)"
affects: [48-reconciliation, 49-gate-rearm, 50-rest-resume]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "App-layer best-effort durable dual-write (force_db_version=True, SQLAlchemyError-only degrade) mirroring the 46-02 sibling-capture idiom"
    - "Single-composer byte-equivalence: one _compose(entries, read_text) drives both the disk and durable read paths"
    - "Location-keyed max-version selection over a per-(run,kind) global version counter (the 46-03 idiom)"

key-files:
  created: []
  modified:
    - backend/agents/artifacts/graph.py
    - backend/app/api/run_files.py
    - backend/agents/capabilities/context_providers/uploaded_files.py
    - backend/tests/unit/test_run_files_upload.py
    - backend/tests/agents/test_uploaded_files_provider.py

key-decisions:
  - "One kind (upload_text) for BOTH sidecars and manifest, discriminated by location"
  - "Store content as str (capped / json.dumps), NOT bytes, so the provider disk path and durable path are byte-equivalent"
  - "force_db_version=True on write (endpoint has no shared in-memory ArtifactGraph)"
  - "Compute the manifest JSON once and reuse it for both the disk .encode() and the durable row content (byte-identical)"

patterns-established:
  - "Best-effort durable mirror inside the manifest lock, after the disk writes, catching only SQLAlchemyError"
  - "Provider durable fallback as a sibling branch in the kernel-pure module (IN-02: no unify with run_files._read_manifest, no app.* import)"

requirements-completed: [RESUME-12, RESUME-13]

# Metrics
duration: 25min
completed: 2026-07-19
---

# Phase 47 Plan 01: Uploads Durability [R2] Summary

**Uploaded-document extracted text + manifest now persist durably as owner+workspace-scoped `upload_text` artifact_refs at ingest, and the `uploaded_files` provider falls back to that mirror byte-equivalently on a wiped sandbox — so a resumed run keeps full document context with zero engine edits.**

## Performance

- **Duration:** ~25 min
- **Tasks:** 2 (both TDD, RED-before-change observed)
- **Files modified:** 5

## Accomplishments

- **RESUME-12:** `run_files.upload_files` best-effort dual-writes each extracted-text sidecar (`content=capped` str) + the manifest snapshot (`content=json.dumps(...)` str) as immutable owner+workspace-scoped `upload_text` rows inside the manifest lock, from the already-owner-checked Layer-2 `ScopedStore` (`current_user.id` / `wr_workspace`, never client payload), `force_db_version=True`, generic `upload` labels, `task_id=None`. A DB error degrades best-effort (200 + loud `SQLAlchemyError`-only warning).
- **RESUME-13:** `UploadedFilesProvider.load` refactored so the disk path and the new `ctx.scoped_store` durable fallback flow through ONE `_compose(entries, read_text)` — byte-identical by construction. Location-keyed max-version selection picks the latest manifest + sidecars; disk wins when both present; neither → `{}`; a cross-owner run yields `[] → {}` by default-deny.
- Additive `upload_text` kind appended to `ARTIFACT_KINDS` (no migration).

## Task Commits

1. **Task 1: RESUME-12 durable dual-write at ingest** - `684c5d6c` (feat, TDD)
2. **Task 2: RESUME-13 provider durable fallback via single _compose** - `5467569c` (feat, TDD)

_Both tasks are single feat commits: the RED tests and the GREEN implementation were staged together per file since each task's tests + code are one atomic unit; RED was observed before writing the implementation (see below)._

## RED-before-change observations

**Task 1** (`tests/unit/test_run_files_upload.py::TestDurableUploadMirror`, observed failing on HEAD before the graph.py + run_files.py change):
- `test_upload_writes_durable_upload_text_rows` — FAILED (`assert set() == {...}` — no rows written)
- `test_text_less_upload_writes_manifest_row_only` — FAILED (no manifest row)
- `test_durable_mirror_best_effort_degrades_on_db_error` — FAILED (no warning emitted)
- `test_image_upload_writes_no_artifact_ref` / `test_over_cap_upload_writes_no_artifact_ref` — PASSED pre- AND post-implementation. These are **regression guards** (a rejected upload must never reach the durable write); they cannot be RED because no row is ever written on a 415/413. Documented honestly as guards, not RED cases.

**Task 2** (`tests/agents/test_uploaded_files_provider.py`, observed failing on HEAD before the provider refactor):
- `test_provider_falls_back_to_durable_on_wiped_sandbox` — FAILED (`{}` on wiped sandbox)
- `test_durable_body_byte_equivalent_to_disk` — FAILED (`KeyError: 'uploaded_files_context'`)
- `test_wiped_resume_three_agent_sticky_context` — FAILED (upload text absent from every agent_input)
- `test_disk_wins_when_both_present` / `test_neither_disk_nor_durable_returns_empty` / `test_cross_owner_durable_read_denied` — PASSED pre- AND post-implementation (regression guards: disk-only path already returns disk content / `{}`; not RED-able).

## Files Created/Modified

- `backend/agents/artifacts/graph.py` — appended additive `upload_text` to `ARTIFACT_KINDS` (no migration).
- `backend/app/api/run_files.py` — best-effort durable dual-write of `upload_text` rows inside the manifest lock (added stdlib `hashlib`/`uuid` imports; compute manifest JSON once for byte-identical disk + durable content).
- `backend/agents/capabilities/context_providers/uploaded_files.py` — single `_compose` + durable `ctx.scoped_store` fallback (`_read_upload_rows`, `_max_version_by_location`, `_parse_entries` sibling helpers); stays kernel-pure.
- `backend/tests/unit/test_run_files_upload.py` — 5 durable-mirror cases + row-snapshot helpers.
- `backend/tests/agents/test_uploaded_files_provider.py` — `_FakeScopedStore` + 6 fallback/byte-equivalence/disk-wins/neither/denial/3-agent cases.

## Decisions Made

None beyond the plan's stated discretion resolutions (kind name `upload_text`; str-not-bytes content; single kind location-discriminated; `force_db_version=True`; manifest JSON computed once). Followed the plan as specified.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None. The `grep -vc` returning exit code 1 when a count is 0 (INV-1 gate) is expected grep behavior, not a failure — the count is `0` as required.

## Gate Tallies (verified BY DELTA)

- Upload suite: **25 passed** (20 baseline + 5 new).
- Provider suite: **22 passed** (16 baseline + 6 new).
- Quick combined (both files): **47 passed**.
- restart_resume: **16 passed / 1 failed** — `test_waiting_for_user_run_is_rearmed_not_driven` (KAN-88) is the SOLE pre-existing red, UNCHANGED; the `.uploads/` fence assertion stays green.
- Goldens (5 characterization, SNAPSHOT_UPDATE unset): **10/10 passed** (dormant by construction — no golden run calls the upload endpoint).
- Banned-pattern gate: **11 passed**.
- lint-imports: **4 kept, 0 broken** (provider stays kernel-pure — only `ctx.scoped_store` attribute access added).
- INV-1 name-literal grep (both files): **0**.
- `upload_text` in graph.py: **1** (kind appended).
- Drift-guard `test_known_count_is_sixty_nine`: **69** (extending an existing provider adds no capability).
- SC-001: **engine.py untouched** (0 in this phase's diff, 0 textual references to `uploaded_files`).

## Fence confirm-only (untouched)

The `.uploads/` re-materialization fence + `_FILE_KINDS` exclusion in `engine.py` ("Phase-47 fence", already shipped) remain at lines 5996 + 6031 — confirmed present, NOT re-added or modified. No engine edit was made.

## Next Phase Readiness

- RESUME-12/13 satisfied offline; the durable mirror + provider fallback are ready for the milestone-end live-Bedrock upload→crash→resume proof (deferred per convention).
- Ready for Phase 48 (task_key/reconciliation).

## Self-Check: PASSED

- SUMMARY.md present at `.planning/phases/47-uploads-durability-r2/47-01-SUMMARY.md`.
- Task commits `684c5d6c` (RESUME-12) + `5467569c` (RESUME-13) verified in git log.
