---
phase: 47-uploads-durability-r2
verified: 2026-07-19T02:40:00Z
status: passed
score: 4/4 must-haves verified
verifier: Claude (gsd-verifier)
re_verification: false
overrides_applied: 0
deferred:
  - truth: "Live upload → crash → resume doc-context proof on real Bedrock (RESUME-12/13 end-to-end)"
    addressed_in: "Milestone-end live-Bedrock pass (orchestrator-owned)"
    evidence: "47-VALIDATION.md Manual-Only table — 'offline gates bind phase completion'; project convention: defer live-env verification to milestone end. Offline evidence complete."
---

# Phase 47: Uploads Durability [R2] Verification Report

**Phase Goal:** Uploaded documents survive resume (Q6) — persist the extracted text + manifest durably and teach the `uploaded_files` provider to fall back to the durable mirror when the disk-only `.uploads/` copy is lost on a fresh sandbox.
**Verified:** 2026-07-19
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (the 4 ROADMAP Success Criteria)

| # | Truth (ROADMAP SC) | Status | Evidence |
| --- | --- | --- | --- |
| 1 | Ingest persists each doc's extracted text + manifest durably (additive, owner_id+workspace_id-scoped; caps/415 byte-unchanged) | ✓ VERIFIED | `run_files.py:235-321` dual-write inside `_manifest_lock`, after the disk manifest write, from the Layer-2 `store` (`current_user.id`/`wr_workspace`, never client payload), `force_db_version=True`, generic `"upload"` labels, `task_id=None`, `content` = the exact `capped`/`manifest_json` **str** (byte-matches disk). Caps loop `:174-218` runs BEFORE any write (415/413 raise first). `graph.py:66-72` appends additive `upload_text` kind (no migration). Suite: **25 passed** — `test_upload_writes_durable_upload_text_rows` asserts content byte-equals disk sidecar/manifest + owner_id/workspace_id/task_id/labels; `test_text_less_upload_writes_manifest_row_only`; `test_durable_mirror_best_effort_degrades_on_db_error` (SQLAlchemyError → 200 + loud warning); `test_image_upload_writes_no_artifact_ref` (415→0 rows); `test_over_cap_upload_writes_no_artifact_ref` (413→0 rows). |
| 2 | Provider falls back to the durable mirror when `.uploads/` is missing — resumed run carries FULL doc context in every `agent_input`, byte-equivalent, sticky preserved | ✓ VERIFIED | `uploaded_files.py:77-183` refactored: DISK-first (compose if manifest entries), else DURABLE fallback via `ctx.scoped_store.list_refs(run_id, "upload_text")` + location-keyed max-version selection, both paths through the SINGLE `_compose(entries, *, read_text)` → byte-identical by construction. Suite: **22 passed** — `test_durable_body_byte_equivalent_to_disk` asserts `disk_body == durable_body` (real equality, not vacuous); `test_wiped_resume_three_agent_sticky_context` loops 3 specs through `engine._compose_context_message` asserting the doc text + "## Uploaded Files" appear in EVERY agent_input; `test_provider_falls_back_to_durable_on_wiped_sandbox`; `test_disk_wins_when_both_present`; `test_neither_disk_nor_durable_returns_empty`. |
| 3 | Zero kernel workflow-name branches; provider kernel-pure + self-gating on the declared inject | ✓ VERIFIED | INV-1 grep on both files = **0**. lint-imports = **4 kept, 0 broken** (provider adds only `ctx.scoped_store` attr access, no `app.*`/engine import). `test_sc001_engine_has_zero_reference_to_the_capability` PASS (asserts `"uploaded_files" not in inspect.getsource(engine)`). Self-gate `if "uploaded_files" not in injects: return {}` unchanged. engine.py absent from BOTH feat commits (0 files). |
| 4 | Images stay payload-transient (ND-10) — no image storage anywhere; goldens byte-identical | ✓ VERIFIED | Dual-write only ever mirrors extractable-doc text + manifest; the 415 image path raises in the caps loop BEFORE any write (`test_image_upload_writes_no_artifact_ref` → 0 rows). Goldens **10/10** (5 characterization files, SNAPSHOT_UPDATE unset — dormant by construction, no golden run calls the upload endpoint). Cross-owner durable read denied by construction (`test_cross_owner_durable_read_denied` → `[]` → `{}`). |

**Score:** 4/4 truths verified

### Deferred Items

| # | Item | Addressed In | Evidence |
|---|------|-------------|----------|
| 1 | Live upload→crash→resume doc-context proof on real Bedrock | Milestone-end live pass | 47-VALIDATION.md Manual-Only table — offline gates bind phase completion (project convention: defer live-env verification to milestone end). All offline evidence complete. |

### Required Artifacts

| Artifact | Expected | Status | Details |
| --- | --- | --- | --- |
| `backend/agents/artifacts/graph.py` | `upload_text` appended to `ARTIFACT_KINDS` | ✓ VERIFIED | Additive member at `:66-72` with Phase-47 comment; `grep -c upload_text` = 1; no migration. |
| `backend/app/api/run_files.py` | best-effort durable dual-write of `upload_text` rows inside the manifest lock, after caps | ✓ VERIFIED | `:235-321`; SQLAlchemyError-only degrade; `force_db_version=True`; str content byte-matching disk; wired to `store.write_ref`. |
| `backend/agents/capabilities/context_providers/uploaded_files.py` | single `_compose` + durable `ctx.scoped_store` fallback | ✓ VERIFIED | `:77-183`; disk-first, durable-fallback, max-version selection; kernel-pure imports (json/logging/typing.Any/registry only). |
| `backend/tests/unit/test_run_files_upload.py` | 5 durable-mirror cases | ✓ VERIFIED | Names confirmed `:527-637`; DB-backed, content-exact, non-vacuous. |
| `backend/tests/agents/test_uploaded_files_provider.py` | `_FakeScopedStore` + 6 fallback/byte-eq/disk-wins/neither/denial/3-agent cases | ✓ VERIFIED | Names confirmed `:379-462`; byte-equality + 3-agent sticky asserts are substantive. |

### Key Link Verification

| From | To | Via | Status | Details |
| --- | --- | --- | --- | --- |
| `run_files.upload_files` | `ScopedStore.write_ref` | `force_db_version=True`, owner=`current_user.id`/ws=`wr_workspace` | ✓ WIRED | `run_files.py:289-320`; reuses Layer-2 `store` from `:168`, never client payload. |
| `uploaded_files` provider | `ctx.scoped_store.list_refs` | durable fallback when disk manifest missing | ✓ WIRED | `uploaded_files.py:157` `_read_upload_rows` → `store.list_refs(run_id, kind="upload_text")`. |
| provider disk path | provider durable path | shared `_compose(entries, read_text)` → byte-equivalence | ✓ WIRED | Single composer at `:118`; asserted by `test_durable_body_byte_equivalent_to_disk`. |

### Behavioral Spot-Checks / Gate Execution (run by verifier)

| Gate | Command | Result | Status |
| --- | --- | --- | --- |
| Both extended suites | `pytest tests/unit/test_run_files_upload.py tests/agents/test_uploaded_files_provider.py -q` | 47 passed (25 upload + 22 provider) | ✓ PASS |
| Restart/resume (fence + KAN-88) | `pytest tests/agents/test_restart_resume.py -q` | 16 passed / 1 failed — `test_waiting_for_user_run_is_rearmed_not_driven` (KAN-88, SOLE pre-existing red, unchanged) | ✓ PASS (by delta) |
| Goldens ×5 (SNAPSHOT_UPDATE unset) | 5 characterization files `-q` | 10/10 passed | ✓ PASS |
| Banned-pattern gate (R15/INV-13) | `pytest tests/agents/test_banned_patterns.py -q` | 11 passed | ✓ PASS |
| Import lint | `lint-imports` (cwd=backend) | 4 kept, 0 broken | ✓ PASS |
| Drift-guard + SC-001 | `pytest -k "test_known_count_is_sixty_nine or test_sc001"` | 27 passed (drift-guard=69, SC-001 green) | ✓ PASS |
| INV-1 name-literal grep | both files | 0 | ✓ PASS |
| `upload_text` in graph.py | grep -c | 1 | ✓ PASS |
| engine.py in phase commits | `git show --stat` grep | 0 (absent from both feat commits) | ✓ PASS |

### Scope-Fence Audit

- `git show --stat 684c5d6c 5467569c` files_modified == plan `files_modified` (graph.py, run_files.py, uploaded_files.py + the 2 test files). engine.py **absent** from both feat commits.
- engine.py Phase-47 fence intact in working tree: `_FILE_KINDS = {"html_file","file_bundle","deliverable"}` (`:6023`, EXCLUDES `upload_text`) and `.uploads/` skipped at `:6030-6031` ("Phase-47 fence — never re-materialized"). Confirmed present, NOT re-added/modified.
- `_read_manifest` kept separate across app/kernel boundary (IN-02): the durable read is a sibling branch (`_parse_entries`) in the provider, no import of `run_files._read_manifest`, no unify.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| --- | --- | --- | --- | --- |
| (none) | — | — | — | No TBD/FIXME/XXX/TODO/HACK/PLACEHOLDER in any modified source file. `return {}` paths are legitimate degrade-not-crash branches (data flows populated via disk/store elsewhere), not stubs. |

### Gaps Summary

None. All four ROADMAP Success Criteria are observably true in the codebase: the ingest dual-write persists owner+workspace-scoped `upload_text` rows (str content byte-matching disk) behind the up-front caps, best-effort on DB error; the provider falls back to that mirror byte-equivalently via a single `_compose`, restoring sticky context across a 3-agent wiped resume; the kernel carries zero reference to the capability (SC-001 test + INV-1 grep + lint 4/0); images stay ND-10-transient and goldens are byte-identical (10/10). The sole restart_resume red is the pre-existing KAN-88, unchanged. All gates re-run by the verifier in a fresh process. The live-Bedrock end-to-end proof is deferred to the milestone-end live pass per the established project convention (offline gates bind phase completion).

---

_Verified: 2026-07-19T02:40:00Z_
_Verifier: Claude (gsd-verifier)_
