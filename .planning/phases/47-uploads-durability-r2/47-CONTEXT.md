# Phase 47: Uploads Durability [R2] - Context

**Gathered:** 2026-07-19
**Status:** Ready for planning
**Source:** POR Ingest Express Path (`.planning/RESUME-CAPABILITY-DESIGN-DRAFT.md` §3.6 / Gap G / §6-R2 / §8 Q6 — DECIDED: persist durably)

<domain>
## Phase Boundary

Uploaded DOCUMENTS survive resume. Today `POST /api/runs/{id}/files` (`run_files.py`) writes raw bytes + extraction sidecars + `manifest.json` under the sandbox `.uploads/` prefix — disk only; the `uploaded_files` context provider re-reads them from disk on EVERY dispatch and silently degrades to `{}` when missing. A fresh sandbox (crash/TTL/environment loss) loses all uploaded-document context and Postgres cannot restore it. This phase adds the durable mirror (RESUME-12) and the provider fallback (RESUME-13).

OUT of scope (hard fences): images (ND-10 locked payload-transient — 415 rejection at the upload endpoint stays; zero image storage), raw-bytes durability (only EXTRACTED TEXT + manifest go durable — the raw PDF/DOCX bytes stay sandbox-only, honestly documented), task_key/reconciliation (48), gate re-arm (49), REST resume endpoint (50), any cap change.

</domain>

<decisions>
## Implementation Decisions

### RESUME-12 — durable mirror at ingest (LOCKED)
- At upload time, `run_files.py` dual-writes each document's EXTRACTED TEXT and the updated `manifest.json` durably, owner+workspace-scoped, via the existing `ScopedStore` write path (app→agents import is legal). Disk stays the live-truth copy (sticky provider semantics unchanged on healthy runs).
- **Storage = `artifact_refs` rows with a NEW ADDITIVE `ARTIFACT_KINDS` member** (e.g. `upload_text` — final name planner's choice, but it MUST be a dedicated kind): reuses ScopedStore/ownership/TTL-survival/immutability machinery, zero new table (Q3-friendliest). Do NOT reuse `file_bundle` — `_surface_partial_fragments` (engine.py ~:870) reads `("file_bundle","fragment")` rows and MUST NOT pick uploads up; do NOT reuse `context_pack`. The additive-kind precedent is P13's `"deliverable"`.
- Row shape: generic labels only (`producer_step`/`producer_agent` = a generic constant like `"upload"` — no workflow/agent-name literal), `task_id=None`, `location` = the sandbox-relative sidecar path (`.uploads/<name>.txt` / `.uploads/manifest.json`), content = the extracted text / manifest JSON. Re-upload of the same filename = a new VERSION (max-version wins on read).
- Caps byte-unchanged: per-file 10MB, count ≤20, aggregate 40MB, ext allow-list, image mimes/exts → 415 — all validated BEFORE any write, disk or durable (reject writes nothing anywhere).
- Failure posture: the durable write is best-effort at ingest (a DB hiccup must not fail an otherwise-valid upload — mirror the `_dual_write_artifact` best-effort discipline) BUT a durable-write failure is logged loudly.

### RESUME-13 — provider fallback (LOCKED)
- `uploaded_files` context provider (`context_providers/uploaded_files.py`, kernel-pure): when the sandbox `.uploads/` manifest is MISSING, fall back to reading the durable mirror via `ectx.scoped_store` (the P33 `conversation` provider precedent for store reads from a provider — kernel-pure, default-deny, owner-scoped). When BOTH exist, disk wins (live truth). When neither, degrade to `{}` exactly as today.
- The fallback must produce a byte-equivalent `uploaded_files_context` block to the disk path for the same content (same header/format), so a resumed run's `agent_input` carries the SAME document context — sticky semantics fully restored.
- Self-gating on the declared `uploaded_files` inject token stays; zero engine edits (the provider rides the existing provider loop — SC-001).
- 46-02's capture exclusion and 46-03's re-materialization exclusion of `.uploads/` BOTH STAY (no disk re-materialization needed — the provider reads durably; simpler, no write-back).

### Guardrails (LOCKED — POR §7 + standing)
- INV-1/SC-001 (no name literals; grep-gated) · INV-2 · INV-3 (goldens 10/10, `SNAPSHOT_UPDATE` unset — golden runs upload nothing, all new machinery dormant; ZERO new WS events) · INV-12 (extend the existing endpoint/provider in place — no parallel upload path, no second extraction impl; `extract_upload_text` stays the single extraction) · INV-5 · INV-13 · lint-imports 4/0 (provider stays kernel-pure — registry decorator + stdlib + the ctx handles only) · ownership default-deny (cross-owner durable reads impossible by ScopedStore construction; add the denial test).
- Additive vocabulary only: the new kind is appended to `ARTIFACT_KINDS`; no migration (artifact_refs table unchanged).
- Verify BY DELTA: KAN-88 sole restart_resume red; 2 stale-head migration fails + 1 attach_replay fail untouched; `test_run_files_upload.py` + `test_uploaded_files_provider.py` extended, never weakened.

### Execution constraints (LOCKED — standing)
- feat/ui-2 only · NO commit trailers · NEVER push · NEVER `git stash` · python3.11 no venv · ABSOLUTE cd to backend/ (stray backend/backend dir exists) · targeted pytest only · NO live Bedrock in executors · sequential.

### Claude's Discretion
- The exact new kind name (`upload_text` vs `upload_doc` etc.) and whether the manifest gets its own kind or the same kind with the manifest location.
- Whether the provider's durable fallback reads per-sidecar rows or reconstructs from the manifest row + text rows (pick the simpler that meets byte-equivalence).
- Plan decomposition (likely ONE plan, 2 tasks: ingest dual-write → provider fallback; or two plans if the test surface is cleaner split).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

- `.planning/RESUME-CAPABILITY-DESIGN-DRAFT.md` — POR §3.6, §4 Gap G, §5.3 boundaries, §6-R2, §7. READ FULLY.
- `.planning/ROADMAP.md` — "### Phase 47" block (4 success criteria) + v3.0 header.
- `.planning/REQUIREMENTS.md` — RESUME-12, RESUME-13.
- `.planning/IMPLEMENTATION-REGISTER.md` — Phase 30 section (the upload endpoint/`.uploads/` contract/`extract_upload_text` single-impl/uploaded_files provider/two-layer owner check; IN-02 note: run_files and the provider deliberately have separate manifest readers across the app/kernel boundary), Phase 33 (the `conversation` provider's ScopedStore-read precedent), Phase 5 (ARTIFACT_KINDS vocabulary + D-01 inline content), P13 (the additive-kind precedent).
- Code: `backend/app/api/run_files.py` (ingest + caps + owner check), `backend/app/api/file_extract.py` (`extract_upload_text` — single impl, do not duplicate), `backend/app/agents/sandbox.py` (`_UPLOADS_PREFIX`), `backend/agents/capabilities/context_providers/uploaded_files.py` (the provider), `backend/agents/capabilities/context_providers/conversation.py` (the store-read precedent), `backend/agents/artifacts/graph.py` (ARTIFACT_KINDS), `backend/agents/authz.py` (ScopedStore write_ref/list_refs/tree), `backend/agents/execution_engine/engine.py` (~:870 `_surface_partial_fragments` — must stay blind to the new kind; the provider loop).
- Tests: `backend/tests/unit/test_run_files_upload.py`, `backend/tests/agents/test_uploaded_files_provider.py`, `test_restart_resume.py` (for a resumed-context integration case), the 5 characterization files, lint.

</canonical_refs>

<specifics>
## Specific Ideas

- The Phase-30 sticky-context proof drove a 3-agent fixture workflow end-to-end — reuse that harness idiom for the fallback proof (same context block from durable as from disk).
- `run_files.py` already resolves owner/workspace via its two-layer check — the ScopedStore for the dual-write should be constructed from THOSE resolved values (never client payload).
- Provider byte-equivalence: the block format lives in the provider (`## Uploaded Files` header composition) — derive both paths through ONE composing function so equivalence is by construction, not by parallel formatting.

</specifics>

<deferred>
## Deferred Ideas

- Raw-bytes durability (re-download of originals after environment loss) — out of scope; extracted text + manifest only (documented).
- Disk re-materialization of `.uploads/` — not needed (provider reads durably); revisit only if a future feature needs the raw files back on disk.
- Live-Bedrock proof — milestone-end pass.

</deferred>

---

*Phase: 47-uploads-durability-r2*
*Context gathered: 2026-07-19 via POR Ingest Express Path (Q6 DECIDED: persist durably)*
