# Phase 47: Uploads Durability [R2] — Research

**Researched:** 2026-07-19
**Domain:** Durable mirror of uploaded-document extracted text + manifest (`artifact_refs`) + provider fallback on a wiped sandbox
**Confidence:** HIGH (every claim grounded in current `feat/ui-2` code at file:line; baseline suites run)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **RESUME-12 (durable mirror at ingest):** `run_files.py` dual-writes each document's EXTRACTED TEXT + the updated `manifest.json` durably, owner+workspace-scoped, via the existing `ScopedStore` write path (app→agents import is legal). Disk stays live-truth (sticky provider semantics unchanged on healthy runs).
- **Storage = `artifact_refs` rows with a NEW ADDITIVE `ARTIFACT_KINDS` member** (`upload_text` — planner's final name, but a DEDICATED kind). Reuses ScopedStore/ownership/TTL/immutability; zero new table (Q3-friendliest). Do NOT reuse `file_bundle` (`_surface_partial_fragments` reads `("file_bundle","fragment")`) or `context_pack`. Precedent = P13's `deliverable`.
- **Row shape:** generic labels only (`producer_step`/`producer_agent` = a generic constant like `"upload"` — no workflow/agent-name literal), `task_id=None`, `location` = sandbox-relative sidecar path (`.uploads/<name>.txt` / `.uploads/manifest.json`), content = extracted text / manifest JSON. Re-upload of same filename = a new VERSION (max-version wins on read).
- **Caps byte-unchanged:** per-file 10MB, count ≤20, aggregate 40MB, ext allow-list, image mimes/exts → 415 — all validated BEFORE any write (disk OR durable).
- **Failure posture:** durable write is best-effort at ingest (a DB hiccup must not fail a valid upload — mirror `_dual_write_artifact`) BUT a durable-write failure is logged loudly.
- **RESUME-13 (provider fallback):** `uploaded_files` provider (kernel-pure): when the sandbox `.uploads/` manifest is MISSING, fall back to the durable mirror via `ectx.scoped_store` (the P33 `conversation` store-read precedent — kernel-pure, default-deny, owner-scoped). Both exist → disk wins. Neither → `{}` as today. Fallback produces a BYTE-EQUIVALENT `uploaded_files_context` block. Self-gate on the declared `uploaded_files` inject stays; ZERO engine edits.
- **46-02 capture exclusion + 46-03 re-materialization exclusion of `.uploads/` BOTH STAY** (no disk re-materialization — provider reads durably).

### Guardrails (LOCKED)
- INV-1/SC-001 (no name literals; grep-gated) · INV-2 · INV-3 (goldens 10/10, upload nothing → all new machinery dormant; ZERO new WS events) · INV-12 (extend endpoint/provider in place — no parallel path, no second extraction; `extract_upload_text` stays single) · INV-5 · INV-13 · lint-imports 4/0 (provider stays kernel-pure) · ownership default-deny (add the cross-owner denial test).
- Additive vocabulary only: append the new kind to `ARTIFACT_KINDS`; no migration.
- Verify BY DELTA: KAN-88 sole restart_resume red; extend (never weaken) `test_run_files_upload.py` + `test_uploaded_files_provider.py`.

### Claude's Discretion
- Exact new kind name (`upload_text` vs `upload_doc`), and whether the manifest gets its own kind or the same kind keyed by manifest location.
- Whether the fallback reads per-sidecar rows or reconstructs from the manifest row + text rows (pick simpler that meets byte-equivalence).
- Plan decomposition (likely ONE plan, 2 tasks: ingest dual-write → provider fallback; or two plans).

### Deferred Ideas (OUT OF SCOPE)
- Raw-bytes durability (re-download of originals) — extracted text + manifest only.
- Disk re-materialization of `.uploads/` — not needed (provider reads durably).
- Live-Bedrock proof — milestone-end pass.
- OUT (hard fences): images (ND-10 — 415 stays, zero image storage), task_key/reconciliation (48), gate re-arm (49), REST resume endpoint (50), any cap change.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| RESUME-12 | Durable mirror of upload extracted text + manifest at ingest, as `artifact_refs` rows with a new additive kind | `run_files.py:220-270` ingest surface + `ScopedStore.write_ref` (`authz.py:134-210`) + `ArtifactRef` (`graph.py:73-101`); dual-write design + row/version scheme below |
| RESUME-13 | `uploaded_files` provider falls back to the durable mirror when the sandbox copy is missing, byte-equivalent context block | `uploaded_files.py:73-138` current read path + `conversation.py:75-103` `ctx.scoped_store` precedent; single-composing-function design below |
</phase_requirements>

## Summary

Recommended shape: **ONE plan, TWO tasks.** Task 1 (RESUME-12) extends `run_files.py`'s upload endpoint to dual-write, inside the existing manifest lock and after the disk writes, each new `.uploads/<name>.txt` sidecar and the rewritten `.uploads/manifest.json` as immutable `artifact_refs` rows under a new additive kind `upload_text` (one kind, location-discriminated), best-effort via the already-constructed Layer-2 `ScopedStore(owner_id=current_user.id, workspace_id=wr_workspace)`. Task 2 (RESUME-13) extends the kernel-pure `uploaded_files` provider so that when `ctx.runner.sandbox` has no `.uploads/manifest.json`, it falls back to `ctx.scoped_store.list_refs(run_id, kind="upload_text")`, selects the max-version row per `location`, and composes the block through the SAME single function the disk path uses — byte-equivalence by construction.

The new kind is **invisible to every kind-keyed reader** (audited below): `_surface_partial_fragments` reads only `("file_bundle","fragment")`; `_rematerialize_artifacts_to_disk` reads `{"html_file","file_bundle","deliverable"}` AND already fences `.uploads/`; FR-014's `_handle_revision` reads only `deliverable`/`summary`/target-kind/`planning_context`; deliverable resolvers read disk. Adding `upload_text` to `ARTIFACT_KINDS` is purely additive (only silences the advisory warning in `write_ref`) with no migration. INV-3 holds by construction: golden runs never call the upload endpoint, so no `upload_text` row is ever written. Baseline is green (20 + 16 + 16 passing; KAN-88 the sole pre-existing restart_resume red; lint 4/0). No new packages; no new capability (drift-guard stays 69). Confidence HIGH.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Ingest dual-write of extracted text + manifest | API/Backend (`app/api/run_files.py`) | Database (`artifact_refs` via `ScopedStore`) | Upload endpoint already owns disk writes + owner/workspace resolution; the durable mirror rides the same request |
| Durable read fallback | Capability/kernel-pure (`agents/capabilities/context_providers/uploaded_files.py`) | Database (`ScopedStore.list_refs`) | Provider is the sole reader of upload context; fallback rides `ctx.scoped_store` (kernel→capability legal direction) |
| Byte-equivalent block composition | Capability (provider) | — | Format lives in the provider; one shared composing function keeps disk == durable by construction |
| Ownership enforcement | `ScopedStore` default-deny (`agents/authz.py`) | — | Cross-owner durable read impossible by construction (`_scope_with_visibility`) |

## Verified Current-State Anchors

**Ingest endpoint — `app/api/run_files.py`:**
- Two-layer owner check: Layer 1 ORM filter `WorkflowRun.id == run_id AND user_id == current_user.id` → 404, capturing `wr_workspace = wr.workspace_id` (`:149-162`). Layer 2 default-deny `store = ScopedStore(owner_id=current_user.id, workspace_id=wr_workspace); if await store.get_run(run_id) is None → 404` (`:166-170`). **`user_id` is the principal (P13/P25); `wr_workspace` is the resolved workspace.** This `store` is exactly the handle the dual-write must reuse — never a client payload (CONTEXT specific idea confirmed).
- Caps enforced BEFORE any write: count ≤ `_MAX_DOC_COUNT`=20 (`:174-178`), ext allow-list `_ALLOWED_EXTS` + `mime.startswith("image/")` → 415 (`:189-196`), per-file `_read_capped(upload, _MAX_FILE_BYTES=10MB)` → 413 (`:198-206`), aggregate `_MAX_AGGREGATE_BYTES`=40MB → 413 (`:208-215`). `validated` list built first; "a single rejection writes nothing."
- Disk writes under the manifest lock (`:227` `with _manifest_lock(sandbox):`): per file, `_safe_segment`+`_dedupe_segment` → `safe` name (`:235-238`); raw bytes to `.uploads/<safe>` (`:240`); if `ext in _EXTRACTABLE_EXTS`: `text = extract_upload_text(name, data)`; if `text.strip()`: `truncated = len(text) > settings.BRIEF_MAX_CHARS`; `capped = text[:BRIEF_MAX_CHARS]`; `_write_bytes(sandbox, f"{raw_rel}.txt", capped.encode("utf-8"))`; `has_text = True` (`:245-253`). **The sidecar content = `capped` (str, ≤ BRIEF_MAX_CHARS ≈ 450k chars); the `has_text` flag drives what the provider surfaces.**
- Manifest update: append-merge keyed on the safe on-disk name (`manifest[safe] = {"name": safe, "mime": mime, "has_text": has_text}`, `:256`), then the WHOLE manifest is rewritten every call: `_write_bytes(sandbox, manifest_rel, json.dumps(list(manifest.values()), ensure_ascii=False).encode("utf-8"))` (`:266-270`). **Manifest is a full rewrite per upload call (not incremental append) — so each durable manifest row is a full snapshot; max-version = final manifest.**
- `extract_upload_text` (`app/api/file_extract.py:87-105`) is the SINGLE extraction impl (INV-12): dispatches pdf/docx/pptx → text, `""` otherwise, never raises.

**Provider — `agents/capabilities/context_providers/uploaded_files.py`:**
- Self-gate: `if "uploaded_files" not in set(ctx.current_spec_injects) → {}` (`:74-78`).
- Disk read: `sandbox = getattr(getattr(ctx, "runner", None), "sandbox", None); if sandbox is None → {}` (`:83-86`); `entries = _read_manifest(sandbox)` (reads `.uploads/manifest.json` as a list, `:114-128`); per entry: skip non-dict / no `name` / `not has_text`; `text = _read_sidecar(sandbox, name)` (reads `.uploads/<name>.txt`, `.strip()`, `:130-138`); `sections.append(f"### {name}\n{text}")` (`:104`).
- **Block format (the byte-equivalence target):** `body = "## Uploaded Files\n\n" + "\n\n".join(sections)` → `{"uploaded_files_context": body}` (`:109-110`). Degrade-to-`{}` on missing/empty/corrupt at every step.
- Import purity: imports ONLY `agents.capabilities.registry.register` + stdlib; `_UPLOADS_PREFIX=".uploads/"` replicated (not imported) (`:40-55`).

**Store-read precedent — `agents/capabilities/context_providers/conversation.py` (P33):**
- `scoped_store = getattr(ctx, "scoped_store", None); run_id = getattr(ctx, "run_id", None); if scoped_store is None or not run_id → {}` (`:75-78`), then `await scoped_store.read_events(run_id, 0)` inside a degrade-to-`[]` try (`:96-103`). **This is the exact reach-the-store-from-a-provider pattern the fallback clones — `ectx.scoped_store` is reachable and is the SAME owner+workspace default-deny helper.**

**ScopedStore (`agents/authz.py`):**
- `write_ref(ref, force_db_version=False)` (`:134-210`): maps an `ArtifactRef` dataclass → `artifact_refs` ORM row; stamps `owner_id = ref.owner_id or self._owner_id` (rejects falsy — AUTHZ-03), `workspace_id = ref.workspace_id or self._workspace_id`; `version = existing_count+1` when `force_db_version` else `ref.version or existing_count+1`; `existing_count = COUNT(*) WHERE run_id=ref.run_id AND kind=ref.kind`.
- `list_refs(run_id, kind=None)` (`:229-250`): owner+visibility-scoped (`_scope_with_visibility`), `ORDER BY version ASC`. **A cross-owner run yields `[]` (default-deny) → the denial test's proof-by-construction.**

**ExecutionContext / engine provider loop (`agents/execution_engine/engine.py`):**
- `ectx.scoped_store = scoped_store` set at run entry (`:1358`); `ectx.run_id`, `ectx.owner_id`, `ectx.workspace_id` all populated (`context.py:51`, `:66-82`). `ectx.compiled_context_providers` threaded at run entry.
- Provider loop (`:6832-6845`): sets `ectx.current_spec_injects`, then `for name in compiled_context_providers: provider = resolve("context_provider", name); blocks = await provider.load(ectx)` — the SAME `ectx` carries BOTH `runner.sandbox` (disk) AND `scoped_store` (durable). **Zero engine edit needed — the provider already receives everything.**

## Ingest Dual-Write Design

**Where:** inside `_manifest_lock(sandbox)` in `upload_files`, AFTER the disk manifest write (`run_files.py:270`), before releasing the lock. Reuse `store` (the Layer-2 `ScopedStore(owner_id=current_user.id, workspace_id=wr_workspace)` already constructed at `:166`). Import `from agents.artifacts.graph import ArtifactRef` (app→agents legal — the endpoint already imports `ScopedStore` from `agents.authz`).

**What to write (this call's contribution):**
1. For each of THIS call's `results` where `has_text` is True: one `upload_text` row — `location=f"{_UPLOADS_PREFIX}{safe}.txt"`, `content=capped` (the exact str written to the `.txt` sidecar — store `capped`, NOT `capped.encode(...)`; the `content` column is Text/str and the provider disk path reads back a str).
2. Exactly one `upload_text` row for the manifest — `location=f"{_UPLOADS_PREFIX}manifest.json"`, `content=json.dumps(list(manifest.values()), ensure_ascii=False)` (the exact str that was `.encode()`d to disk).

**Row shape (generic — SC-001/INV-1):**
```python
ArtifactRef(
    id=str(uuid.uuid4()), kind="upload_text",
    owner_id=current_user.id, workspace_id=wr_workspace, run_id=run_id,
    producer_step="upload", producer_agent="upload",   # generic constant — no workflow/agent literal
    task_id=None,
    content=<capped text | manifest json str>,
    content_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
    location=<".uploads/<safe>.txt" | ".uploads/manifest.json">,
    version=1,                                          # ignored — force_db_version recomputes
)
# then: await store.write_ref(ref, force_db_version=True)
```

**Best-effort discipline (mirror `_dual_write_artifact`, engine.py:5555-5573):** wrap the durable writes in try/except; on `SQLAlchemyError` log a LOUD warning (`logger.warning("upload_text durable mirror failed for run %s (%s)", run_id, exc)`) and continue — the upload's 200 response is unaffected. Re-raise any non-`SQLAlchemyError` (there is no AUTHZ-03 risk here: `owner_id=current_user.id` is always a real principal). **Caps already enforced up-front, so no write (disk or durable) can precede a rejection.**

**Why `force_db_version=True`:** the endpoint has no shared in-memory `ArtifactGraph` (that lives on `ectx` in the engine, absent here). The clarify path (`authz.py:180-185`) and the 46-02 sibling-capture path (`kernel_services.py:1430-1448`) both use `force_db_version=True` for exactly this reason — the DB `COUNT(*) WHERE (run_id, kind) + 1` is the authoritative monotonic version. This is the established app-layer idiom.

## Kind & Reader Audit

**Current `ARTIFACT_KINDS` (`agents/artifacts/graph.py:52-70`):** `spec, plan, task_list, html_file, file_bundle, repo_inventory, repo_diff, context_pack, validation_report, merge_conflict, summary, patch, deliverable, clarifications, planning_context`.

**Additive-kind precedent (P13 / IN-01):** `deliverable` was appended as a generic FR-014 fallback kind (`graph.py:38-51` docstring). The vocabulary is **advisory-enforced only** — `write_ref` logs a WARNING for an out-of-vocabulary kind but never raises (`graph.py:148-155`); `*_output` kinds are a documented carve-out. Appending `upload_text` to the frozenset silences that advisory for our writes; there is **no migration** (the `artifact_refs.kind` column is a free String).

**IN-01 unenforced-vocabulary caveat to respect:** the frozenset is advisory, so a typo'd kind is silently unroutable. Append `upload_text` (or the chosen name) to `ARTIFACT_KINDS` so the vocabulary matches every production writer (the IN-01 intent). `test_artifact_graph.py:202-239` asserts unknown-kind-warns / vocabulary-kind-silent but does NOT pin the frozenset length — appending a member breaks nothing.

**Every kind-keyed reader (grep-audited) and why `upload_text` is invisible:**

| Reader | Location | Kinds it matches | Sees `upload_text`? |
|--------|----------|------------------|---------------------|
| `_surface_partial_fragments` (`_collect_partial_fragments`) | `engine.py:890` | `("file_bundle","fragment")` off the in-memory graph | **No** — different kind, AND app-layer writes never touch `ectx.artifacts` |
| `_rematerialize_artifacts_to_disk` (46-03) | `engine.py:6023-6031` | `{"html_file","file_bundle","deliverable"}` AND explicitly `continue` on `location.startswith(".uploads/")` | **No** — kind excluded AND `.uploads/` fenced (46-03 exclusion STAYS per CONTEXT) |
| FR-014 revision chain (`_handle_revision`) | `engine.py:5203-5243` | `list_refs(kind=target_artifact_type)` → `deliverable` → `summary` → `planning_context` | **No** — `upload_text` is never a revision target kind, never `deliverable`/`summary` |
| Deliverable resolvers | `agents/capabilities/deliverables/*` | read the DISK sandbox (`serialized_sandbox`/`single_file`); `repo_diff` only WRITES `kind="repo_diff"` | **No** — resolvers don't read `artifact_refs` by upload kind |
| `_latest_typed_content` | `engine.py:5597-5603` | matches by `producer_agent`, off `ectx.artifacts` | **No** — app-layer write never enters the in-memory graph; `producer_agent="upload"` matches no pipeline agent |
| `write_fragment_artifact` / merge | `kernel_services.py:721-814` | `file_bundle` / `merge_conflict` | **No** |
| `GET /{id}/artifacts` kind filter | `runs.py:797-859` | generic equality `r.kind == kind`; no kind param → full tree | **Visible but harmless** (see note) |

**Note on `/artifacts`:** with `?kind=upload_text` the rows return; with NO kind param the full owner-scoped lineage tree includes them as root nodes (inline `content` excluded unless `?include=content`). This is a generic, owner-scoped, content-excluded surfacing — NOT a mis-route (nothing treats them as a deliverable/spec). It is INV-3-safe (goldens write no `upload_text` row → tree unchanged). Document it as a known, acceptable read surface; no special handling needed.

**Recommended kind name:** `upload_text` (matches CONTEXT's example; a single kind for BOTH sidecars and manifest, discriminated by `location`). Rationale: one `list_refs(run_id, kind="upload_text")` call reads everything; the manifest is distinguishable by `location == ".uploads/manifest.json"`. This is the "same kind with the manifest location" discretion option — simplest, meets byte-equivalence.

## Provider Fallback Design (single composing function)

Refactor `UploadedFilesProvider.load` so BOTH paths flow through ONE composer — byte-equivalence by construction, never parallel formatting (CONTEXT specific idea).

```
async def load(ctx):
    if "uploaded_files" not in set(getattr(ctx, "current_spec_injects", None) or ()): return {}

    # 1. DISK first (live truth — sticky semantics unchanged on healthy runs)
    sandbox = getattr(getattr(ctx, "runner", None), "sandbox", None)
    manifest_raw = _read_manifest_raw(sandbox)          # sandbox.read(_MANIFEST_REL) or None
    if manifest_raw:
        return self._compose(_entries(manifest_raw),
                             read_text=lambda name: _read_disk_sidecar(sandbox, name))

    # 2. FALLBACK to durable mirror (wiped/fresh sandbox — RESUME-13)
    store = getattr(ctx, "scoped_store", None)
    run_id = getattr(ctx, "run_id", None)
    if store is None or not run_id: return {}
    rows = await _read_upload_rows(store, run_id)        # list_refs(run_id, "upload_text"); degrade → []
    latest = _max_version_by_location(rows)             # {location: row} — max(version) per location
    manifest_row = latest.get(_MANIFEST_REL)            # ".uploads/manifest.json"
    if manifest_row is None: return {}
    return self._compose(_entries(manifest_row.content),
                         read_text=lambda name: _durable_text(latest, name))
```

**The shared composer** (identical loop for both sources — the ONLY place the block format lives):
```
def _compose(self, entries, *, read_text):
    sections = []
    for entry in entries:
        if not isinstance(entry, dict): continue
        name = entry.get("name")
        if not isinstance(name, str) or not name: continue
        if not entry.get("has_text"): continue
        text = (read_text(name) or "").strip()          # strip applied identically to both sources
        if not text: continue
        sections.append(f"### {name}\n{text}")
    if not sections: return {}
    return {"uploaded_files_context": "## Uploaded Files\n\n" + "\n\n".join(sections)}
```

**Byte-equivalence proof:** the durable manifest content is the EXACT str `json.dumps(list(manifest.values()), ensure_ascii=False)` written to disk (so `_entries` yields the identical ordered list with identical `has_text`); the durable sidecar content is the EXACT `capped` str written to the `.txt` sidecar; `_compose` applies the identical `.strip()` and identical `f"### {name}\n{text}"` / `## Uploaded Files\n\n` framing regardless of source. Therefore disk-path body == durable-path body for the same content.

- `_durable_text(latest, name)` = `getattr(latest.get(f"{_UPLOADS_PREFIX}{name}.txt"), "content", "")`.
- **Disk wins when both exist** (manifest present on disk short-circuits before the store read).
- **Degrade-to-`{}` unchanged** when neither disk nor durable resolves.
- **Import purity preserved:** the fallback adds only `ctx.scoped_store` attribute access (the conversation-provider precedent) — no `app.*` import, no engine import. `_UPLOADS_PREFIX`/`_MANIFEST_REL` stay local constants. lint-imports 4/0 holds.

## Row/Version Selection Scheme

**The version question (CONTEXT Q4):** `write_ref`/`ArtifactGraph.write_ref` compute `version = 1 + count of same (run_id, kind)` — this is PER-`(run_id, kind)`, NOT per-location. With one shared kind `upload_text`, every sidecar row AND every manifest row increments the SAME counter. So `version` is a monotonic global-within-kind sequence, not a per-file counter.

**Therefore location-keyed max-version selection is REQUIRED** (the 46-03 idiom, `engine.py:6021-6034`):
```
latest = {}
for row in rows:                       # list_refs → ORDER BY version ASC
    loc = row.location
    if latest.get(loc) is None or row.version >= latest[loc].version:
        latest[loc] = row
```
Because `list_refs` already orders by `version ASC` and the global counter only grows, the LAST row seen per location is its highest version — correct for both re-uploads and manifest snapshots.

**Why this resolves N documents + re-uploads correctly:**
- **N documents, one call:** N distinct sidecar locations (`.uploads/a.txt`, `.uploads/b.txt`, …) + 1 manifest location. Each location appears once → `latest` holds all N + the manifest. The manifest lists all N with `has_text` → composer emits N sections in manifest order.
- **Re-upload of the SAME filename:** `_dedupe_segment` (seeded from the existing manifest names, `run_files.py:230-238`) assigns a NEW safe name (`report.pdf` → `report-2.pdf`), so it is a DISTINCT location + a DISTINCT manifest entry — NOT a same-location version bump. So in practice each sidecar location is written once; version-stacking within a single sidecar location does not occur.
- **Manifest re-writes:** every upload call rewrites the full manifest → a NEW `upload_text` row at `.uploads/manifest.json` with a higher version. `_max_version_by_location` picks the latest = the final full snapshot listing all files across all calls. This is the only location that genuinely version-stacks, and max-version selection handles it exactly.

**Recommendation:** ONE kind `upload_text`; location-keyed max-version selection on read; `force_db_version=True` on write. This makes the manifest snapshot self-consistent (the latest manifest lists exactly the files whose latest sidecar rows exist) and needs no per-location version bookkeeping.

## Resumed-Run Proof Design

The existing `tests/agents/test_uploaded_files_provider.py` already carries BOTH the unit-level provider harness (`_FakeSandbox` + `_ctx` with `ctx.runner.sandbox`) AND an end-to-end sticky proof driving `engine._compose_context_message` directly with a real `ExecutionContext` (`:205-321`). Reuse/extend it — no new harness needed.

**Unit fallback + byte-equivalence proof (Task 2):**
- Add a `_FakeScopedStore` with `async def list_refs(run_id, kind=None)` returning a list of `SimpleNamespace(location=..., content=..., version=..., kind="upload_text")` rows (a manifest row + sidecar rows), owner-scoped by construction (return `[]` for a foreign `run_id` → the denial test).
- Compose the DISK body from a staged `_FakeSandbox` (existing `_stage_uploads`), then a ctx with `runner.sandbox = _FakeSandbox()` (EMPTY — wiped) + `scoped_store = _FakeScopedStore(<same content as durable rows>)` + `run_id`. Assert the two bodies are **byte-identical** (`disk_body == durable_body`) — proves RESUME-13 byte-equivalence.
- Assert disk-wins: ctx with BOTH a populated sandbox AND a divergent store → body matches the disk content.
- Assert cross-owner denial: `_FakeScopedStore` returning `[]` for the run → fallback degrades to `{}` (models the default-deny `list_refs` empty result).

**End-to-end wiped-sandbox sticky proof:** clone `_staged_ectx` into a `_wiped_resume_ectx` where `ectx.runner = SimpleNamespace(sandbox=_FakeSandbox())` (empty) and `ectx.scoped_store = _FakeScopedStore(<durable rows>)`, `ectx.run_id` set. Loop the 3-agent `ordered` list through `engine._compose_context_message` and assert `_UPLOAD_TEXT in msg` + `"## Uploaded Files" in msg` for EVERY agent — proving a resumed run with a WIPED sandbox still carries the doc context in `agent_input` via the durable fallback (the closest analog to the Phase-30 3-agent fixture proof, `:250-263`).

**Ingest-side DB-backed proof (Task 1):** `test_run_files_upload.py`'s `env` fixture stands up a real in-memory SQLite with the full `Base.metadata` (includes `artifact_refs`) and monkeypatches `SessionLocal` (`:52-65`). So a test can `POST /files` a `.pdf` (with `extract_upload_text` monkeypatched to return text, per the existing `:251` pattern), then open a session and assert `artifact_refs` rows exist with `kind="upload_text"`, `location==".uploads/<safe>.txt"` / `".uploads/manifest.json"`, `content` == the sidecar/manifest bytes, `producer_step=="upload"`, `task_id is None`. Add a best-effort-degrade test (patch `store.write_ref` to raise `SQLAlchemyError` → upload still 200, warning logged). Add an INV-3-by-construction assertion: a text-less upload (`has_text=False`) writes only the manifest row, no sidecar row.

## At-Risk Tests & Baseline (real output)

All run offline, `python3.11` no venv, absolute `cd backend/`:

| Suite | Command | Baseline (real) |
|-------|---------|-----------------|
| Upload ingest | `python3.11 -m pytest tests/unit/test_run_files_upload.py -q` | **20 passed** |
| Provider | `python3.11 -m pytest tests/agents/test_uploaded_files_provider.py -q` | **16 passed** |
| Restart resume | `python3.11 -m pytest tests/agents/test_restart_resume.py -q` | **16 passed, 1 failed** — `test_waiting_for_user_run_is_rearmed_not_driven` (KAN-88, `'failed' != 'waiting_for_user'`; the sole pre-existing red, Phase-49 territory) |
| Goldens (characterization ×5) | `python3.11 -m pytest tests/agents/test_characterization_{prototype,od_prototype,od_ppt,app_builder,prototype_revision}.py -q` | **all passed** (bundled run: 26 passed alongside restart_resume's 16, minus the 1 KAN-88 fail) |
| Import lint | `/opt/homebrew/bin/lint-imports` | **Contracts: 4 kept, 0 broken** |
| Vocabulary guard | `python3.11 -m pytest tests/agents/test_artifact_graph.py -q` | (not length-pinned; appending `upload_text` is safe) |
| Provider drift-guard | `test_known_count_is_sixty_nine` | **69** — extending the existing provider adds NO capability; count STAYS 69 |

**Delta expectation:** Task 1 EXTENDS `test_run_files_upload.py` (new durable-mirror assertions), Task 2 EXTENDS `test_uploaded_files_provider.py` (fallback + byte-equivalence + denial). Never weaken. KAN-88 stays the sole restart_resume red (untouched). Goldens stay byte-identical (no upload endpoint call → no `upload_text` row).

## Pitfalls

1. **Best-effort scope creep.** The durable write must catch ONLY the DB condition (`SQLAlchemyError` → loud warning + continue) and RE-RAISE anything else — mirror `_dual_write_artifact` (`engine.py:5559-5573`) exactly. Do NOT blanket-swallow; a bug would silently drop mirrors. Owner is always real here, so no AUTHZ-03 concern.
2. **Content type mismatch → byte drift.** Store `content=capped` (str) and `content=json.dumps(...)` (str) — NOT `.encode()`d bytes. The `artifact_refs.content` column is Text; the provider disk path reads back a str. Storing bytes would round-trip differently and break byte-equivalence. `content_hash` must be `sha256(content.encode("utf-8"))` over the same str.
3. **IN-02 dual-manifest-reader boundary — keep the two readers separate.** `run_files._read_manifest` (app, reads disk to append-merge) and `uploaded_files._read_manifest` (kernel-pure, reads disk to surface) are DELIBERATELY separate across the app/kernel boundary (register IN-02 note). Do NOT unify them or import one into the other — the provider must not import `app.*`. Add the durable read as a SIBLING branch in the provider, not a shared helper across layers.
4. **No engine edits (SC-001).** The provider rides the existing loop (`engine.py:6832-6845`); `ectx.scoped_store` is already set (`:1358`). `test_sc001_engine_has_zero_reference_to_the_capability` (`:283-296`) greps engine source for `"uploaded_files"` — keep it clean.
5. **Caps before ANY write.** The dual-write lives AFTER the up-front cap loop and after the disk writes, inside the lock — so a rejected upload writes nothing anywhere. Do not hoist any durable write above the validation loop.
6. **INV-3 dormancy — prove by construction.** Golden runs never call `POST /files`, so no `upload_text` row exists → the provider fallback never fires on goldens, `_rematerialize` skips `.uploads/`, and the tree is unchanged. Appending `upload_text` to `ARTIFACT_KINDS` only silences an advisory warning. Zero new WS events (ingest is a REST endpoint, not an engine emit).
7. **Image 415 unchanged (ND-10).** The image reject (`mime.startswith("image/")` / ext off allow-list → 415, `:189-196`) is untouched; zero image storage (durable or disk). The dual-write only ever mirrors extractable-doc text + manifest.
8. **`.uploads/` re-materialization fence STAYS.** 46-03's `_rematerialize_artifacts_to_disk` already `continue`s on `.uploads/` (`engine.py:6030`) AND `upload_text ∉ _FILE_KINDS` — so uploads are never written back to disk on resume; the provider reads durably instead. Do not remove either guard.

## Package Legitimacy Audit

**N/A — no external packages introduced.** Phase 47 reuses in-repo modules only: `agents.authz.ScopedStore`, `agents.artifacts.graph.ArtifactRef` (both already imported across the app/kernel boundary), `app.api.file_extract.extract_upload_text`, stdlib `json`/`hashlib`/`uuid`. Extraction libs (`pypdf`/`python-docx`/`python-pptx`) are already pinned dependencies used by the existing `extract_upload_text`; this phase adds no new call to them.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.3.4 + pytest-asyncio 0.24.0 (Mode.STRICT) |
| Config file | `backend/pyproject.toml` |
| Quick run command | `cd backend && python3.11 -m pytest tests/unit/test_run_files_upload.py tests/agents/test_uploaded_files_provider.py -q` |
| Full suite command | quick + `tests/agents/test_restart_resume.py` + 5 characterization + `/opt/homebrew/bin/lint-imports` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| RESUME-12 | Upload dual-writes `upload_text` rows (sidecars + manifest) with generic labels, `task_id=None`, correct location/content | unit (DB-backed) | `python3.11 -m pytest tests/unit/test_run_files_upload.py -q` | ✅ extend |
| RESUME-12 | Durable write is best-effort (DB error → 200 + loud warning) | unit | same file | ❌ Wave 0 (add) |
| RESUME-12 | Caps still reject BEFORE any durable write; image 415 unchanged | unit | same file | ✅ (caps tests exist; add "no row on 415") |
| RESUME-13 | Provider falls back to durable mirror on wiped sandbox; byte-equivalent block | unit | `python3.11 -m pytest tests/agents/test_uploaded_files_provider.py -q` | ✅ extend |
| RESUME-13 | Disk wins when both present; degrade-to-`{}` when neither; cross-owner denial → `{}` | unit | same file | ❌ Wave 0 (add) |
| RESUME-13 | Resumed 3-agent run (wiped sandbox) carries doc text in EVERY agent_input | integration (scripted) | same file (`_compose_context_message` path) | ✅ extend (clone `_staged_ectx`) |
| SC-001 | Engine source has zero `"uploaded_files"` reference | unit | same file (`test_sc001_...`) | ✅ exists |
| INV-3 | Dormant case byte-identical to baseline | unit | same file (`test_inv3_...`) | ✅ exists |
| Guardrail | lint-imports 4/0 (provider stays kernel-pure) | lint | `/opt/homebrew/bin/lint-imports` | ✅ exists |

### Sampling Rate
- **Per task commit:** the quick run command (2 files) + `/opt/homebrew/bin/lint-imports`.
- **Per plan/phase gate:** quick + `tests/agents/test_restart_resume.py` (expect 16 passed / 1 KAN-88 fail) + 5 characterization goldens (all pass) + lint.

### Wave 0 Gaps
- [ ] `tests/unit/test_run_files_upload.py` — add: durable `upload_text` rows present + content-exact; best-effort degrade (patched `SQLAlchemyError`); no-row-on-415; text-less upload writes manifest row only.
- [ ] `tests/agents/test_uploaded_files_provider.py` — add: `_FakeScopedStore`; wiped-sandbox fallback; disk-body == durable-body byte-equivalence; disk-wins; neither → `{}`; cross-owner (empty `list_refs`) → `{}`; wiped-sandbox 3-agent sticky proof.
- [ ] `agents/artifacts/graph.py` — append `upload_text` (or chosen name) to `ARTIFACT_KINDS` (additive, no migration).
- No framework install needed (pytest/pytest-asyncio present).

## Sources

### Primary (HIGH — current code, file:line)
- `backend/app/api/run_files.py` (ingest, caps, two-layer owner check, manifest lock)
- `backend/app/api/file_extract.py` (`extract_upload_text` single impl)
- `backend/agents/capabilities/context_providers/uploaded_files.py` (provider read path + block format)
- `backend/agents/capabilities/context_providers/conversation.py` (P33 `ctx.scoped_store` precedent)
- `backend/agents/authz.py` (`ScopedStore.write_ref`/`list_refs`, default-deny scope)
- `backend/agents/artifacts/graph.py` (`ARTIFACT_KINDS`, `ArtifactRef`, IN-01 advisory)
- `backend/agents/execution_engine/engine.py` (provider loop `:6832`, `_surface_partial_fragments` `:890`, `_rematerialize_artifacts_to_disk` `:5975-6039`, FR-014 `:5203-5243`, `_dual_write_artifact` `:5517-5573`)
- `backend/agents/execution_engine/kernel_services.py` (46-02 best-effort `force_db_version` sibling-capture idiom `:1387-1454`)
- `backend/app/agents/sandbox.py` (`_UPLOADS_PREFIX`, `_collect_deliverable_relpaths` `.uploads/` exclusion `:41,:242-244`)
- `backend/app/api/runs.py` (`/artifacts` kind filter `:797-859`)
- `.planning/RESUME-CAPABILITY-DESIGN-DRAFT.md` §3.6 / Gap G / §5.3 / §6-R2 / §7 / §8 Q6
- Test baselines run this session (tallies above)

### Secondary (MEDIUM)
- `backend/tests/agents/test_uploaded_files_provider.py` + `tests/unit/test_run_files_upload.py` (harness shapes to extend)
- `backend/tests/agents/test_artifact_graph.py:202-239` (vocabulary not length-pinned)

## Metadata

**Confidence breakdown:**
- Ingest dual-write design: HIGH — grounded in the endpoint + `ScopedStore.write_ref` + the 46-02 `force_db_version` precedent.
- Provider fallback / byte-equivalence: HIGH — the conversation provider proves `ctx.scoped_store` reachability; the shared-composer approach makes equivalence structural.
- Kind/reader invisibility: HIGH — every kind-keyed reader grep-audited; `.uploads/` fences already in place.
- Row/version scheme: HIGH — matches the shipped 46-03 location-keyed max-version idiom.
- Test strategy: HIGH — DB-backed `env` fixture + existing 3-agent scripted harness cover both requirements offline.

**Research date:** 2026-07-19
**Valid until:** 2026-08-18 (stable brownfield; re-verify if `run_files.py`/`uploaded_files.py`/`authz.py` change)

## RESEARCH COMPLETE

- **Shape:** ONE plan, TWO tasks — Task 1 (RESUME-12) app-layer best-effort dual-write of `upload_text` rows (sidecars + manifest, generic labels, `task_id=None`, `location`-keyed) via the endpoint's existing Layer-2 `ScopedStore`; Task 2 (RESUME-13) kernel-pure provider fallback to `ctx.scoped_store` through a single shared composer.
- **Kind:** new additive `upload_text` (one kind, location-discriminated for manifest vs sidecars); invisible to `_surface_partial_fragments`, `_rematerialize`, FR-014, deliverable resolvers, `_latest_typed_content`; only surfaces (harmlessly, owner-scoped, content-excluded) via `GET /artifacts`. No migration.
- **Version:** per-`(run_id, kind)` global counter → location-keyed max-version selection required (the 46-03 idiom); `force_db_version=True` on write; re-uploads dedupe to new filenames so only the manifest genuinely version-stacks.
- **Byte-equivalence:** durable content = the exact str written to disk (manifest json / capped text); one `_compose(entries, read_text)` used by both paths → disk == durable by construction; disk wins when both present.
- **Baseline (real):** upload 20✅, provider 16✅, restart_resume 16✅/1 KAN-88 red, 5 goldens ✅, lint 4/0, drift-guard stays 69. Extend both suites, never weaken; INV-3 dormant by construction (goldens never upload).
- **Risks:** best-effort must catch only `SQLAlchemyError` (log loud, else re-raise); store str not bytes; keep the IN-02 app/kernel manifest-reader split; caps before any write; `.uploads/` re-materialization fence stays; image 415 untouched; zero engine edits.
