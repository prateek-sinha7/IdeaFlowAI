# Phase 47: Uploads Durability [R2] - Pattern Map

**Mapped:** 2026-07-19
**Files analyzed:** 3 modified (`run_files.py`, `uploaded_files.py`, `graph.py`) + 2 test files extended
**Analogs found:** 5 / 5 (all in-repo, all excerpt-verified against current `feat/ui-2`)
**Shape:** ONE plan, TWO tasks (Task 1 = RESUME-12 ingest dual-write; Task 2 = RESUME-13 provider fallback), per RESEARCH §Summary.

All excerpts below are copied from CURRENT files with re-verified line numbers. Drift vs the CONTEXT/RESEARCH citations is flagged in the Anchor Verification table at the end. **Net: research is accurate; two line-number citations drifted (46-02 idiom + 46-03 idiom) and one anchor is ALREADY SHIPPED — see the table.**

---

## File Classification

| Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---------------|------|-----------|----------------|---------------|
| `backend/app/api/run_files.py` (extend `upload_files`) | API endpoint (app layer) | file-I/O + CRUD-write | `kernel_services.py` 46-02 sibling-capture (`force_db_version=True` durable-only write) | role-adjacent, idiom-exact |
| `backend/agents/capabilities/context_providers/uploaded_files.py` (extend `load`) | capability / context_provider (kernel-pure) | request-response read + fallback | `conversation.py` (`ctx.scoped_store` store-read from a provider) | exact (same port, same store-read) |
| `backend/agents/artifacts/graph.py` (append 1 member to `ARTIFACT_KINDS`) | vocabulary / config | n/a | P13's `deliverable` addition to the same frozenset | exact |
| `backend/tests/unit/test_run_files_upload.py` (extend) | test (DB-backed) | — | its own `env` fixture (in-mem SQLite + `SessionLocal` patch) | exact (self) |
| `backend/tests/agents/test_uploaded_files_provider.py` (extend) | test (unit + scripted-engine) | — | its own `_FakeSandbox` / `_staged_ectx` 3-agent harness | exact (self) |

---

## Pattern Assignments

### 1. `run_files.py` — ingest dual-write (RESUME-12, Task 1)

**Analogs:** the endpoint's own manifest-lock region (self), `ScopedStore.write_ref` (`authz.py`), the 46-02 best-effort `force_db_version=True` idiom (`kernel_services.py`), and the `_dual_write_artifact` best-effort discipline (`engine.py`).

**Copy this — the Layer-2 `ScopedStore` construction to REUSE (`run_files.py:160,166`, verified):**
```python
        wr_workspace = wr.workspace_id
    finally:
        db.close()

    # ── Layer 2: default-deny re-resolve so the ownership boundary lives in ONE place ──
    store = ScopedStore(owner_id=current_user.id, workspace_id=wr_workspace)
    if await store.get_run(run_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow run not found")
```
→ **DEVIATE:** do NOT construct a second `ScopedStore` and NEVER from a client payload — reuse this `store`. `current_user.id` = principal; `wr_workspace` = resolved workspace (CONTEXT specific idea confirmed).

**Copy this — the manifest-lock region where the dual-write lands (`run_files.py:227-270`, verified):**
```python
    with _manifest_lock(sandbox):
        manifest = _read_manifest(sandbox, manifest_rel)
        used_names: set[str] = set(manifest)
        results: list[dict] = []
        for name, data, ext, mime in validated:
            safe = _dedupe_segment(_safe_segment(os.path.basename(name), fallback="upload"), used_names)
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
            manifest[safe] = {"name": safe, "mime": mime, "has_text": has_text}
            results.append({...})
        _write_bytes(
            sandbox, manifest_rel,
            json.dumps(list(manifest.values()), ensure_ascii=False).encode("utf-8"),
        )
```
→ **DEVIATE — where the new dual-write goes:** INSIDE the lock, AFTER the `_write_bytes(sandbox, manifest_rel, ...)` at `:266-270`, still before releasing the lock. For each result with `has_text=True` write one `upload_text` row (`content=capped` — the **str**, NOT `.encode(...)`; `location=f"{_UPLOADS_PREFIX}{safe}.txt"`), plus exactly one manifest row (`content=json.dumps(list(manifest.values()), ensure_ascii=False)` — the exact str, NOT bytes; `location=f"{_UPLOADS_PREFIX}manifest.json"`). Caps at `:174-216` already ran → a rejected upload writes nothing durable.

**Copy this — `ScopedStore.write_ref` signature + version semantics (`authz.py:134,163-207`, verified):**
```python
    async def write_ref(self, ref: Any, *, force_db_version: bool = False) -> str:
        resolved_owner = getattr(ref, "owner_id", None) or self._owner_id
        if not resolved_owner:
            raise ValueError("artifact_refs.owner_id must be a real principal (AUTHZ-03); ...")
        ...
        existing_count = session.query(func.count(...)).filter(
            ArtifactRefRow.run_id == ref.run_id, ArtifactRefRow.kind == ref.kind).scalar() or 0
        if force_db_version:
            version = existing_count + 1     # DB COUNT(*)+1 is authoritative
        else:
            version = getattr(ref, "version", None) or (existing_count + 1)
        row = ArtifactRefRow(..., content=ref.content, content_hash=ref.content_hash,
                             location=ref.location, version=version, ...)
        session.add(row); session.commit(); return row.id
```
→ **DEVIATE:** pass `force_db_version=True`. The endpoint has NO shared in-memory `ArtifactGraph` (that lives on `ectx` in the engine), so the DB `COUNT(*) WHERE (run_id, kind) + 1` is the only authoritative monotonic version. `owner_id=current_user.id` is always a real principal → no AUTHZ-03 risk here. Note version is per-`(run_id, kind)` GLOBAL (not per-location) → drives the location-keyed max-version read in Task 2.

**Copy this — the best-effort discipline (mirror `_dual_write_artifact`, `engine.py:5556-5573`, verified):**
```python
        store = ectx.scoped_store
        if store is not None:
            try:
                await store.write_ref(ref)
            except Exception as exc:  # noqa: BLE001 — never break the run on DB persist
                from sqlalchemy.exc import SQLAlchemyError
                if not isinstance(exc, SQLAlchemyError):
                    raise
                logger.warning("artifact_refs persist failed for run %s kind %s (%s) — DB write degraded ...", ...)
```
And the 46-02 sibling (`kernel_services.py:1429-1456`, verified — the app-adjacent `force_db_version=True` + `ArtifactRef(...)` construction to copy shape from):
```python
                await store.write_ref(
                    ArtifactRef(
                        id=str(_uuid4()), kind="file_bundle",
                        owner_id=self._ectx.owner_id,
                        workspace_id=getattr(self._ectx, "workspace_id", None) or "",
                        run_id=self._ectx.run_id,
                        producer_step=agent_id, producer_agent=agent_id,
                        task_id=str(task_num), content=content, content_hash=new_hash,
                        location=relpath, version=1,
                    ),
                    force_db_version=True,
                )
            except Exception as exc:  # noqa: BLE001 — best-effort, never break the task
                from sqlalchemy.exc import SQLAlchemyError
                if not isinstance(exc, SQLAlchemyError):
                    raise
                logger.warning(...)
```
→ **DEVIATE for the row (generic labels — SC-001/INV-1):** `kind="upload_text"`, `producer_step="upload"`, `producer_agent="upload"` (generic constant — NO workflow/agent literal), `task_id=None`, `content_hash=hashlib.sha256(content.encode("utf-8")).hexdigest()`. Wrap the durable writes in the try/except above; catch ONLY `SQLAlchemyError` (loud `logger.warning`), re-raise everything else. Import `from agents.artifacts.graph import ArtifactRef` (app→agents legal — the endpoint already imports `ScopedStore` from `agents.authz` at `:144`).

---

### 2. `uploaded_files.py` — provider fallback (RESUME-13, Task 2)

**Analog:** `conversation.py` (P33 — the sole kernel-pure precedent for reading the durable store FROM a provider).

**Copy this — the exact `ctx.scoped_store` access + degrade guard (`conversation.py:73-103`, verified):**
```python
        scoped_store = getattr(ctx, "scoped_store", None)
        run_id = getattr(ctx, "run_id", None)
        if scoped_store is None or not run_id:
            return {}
        rows = await self._read_chat_events(scoped_store, run_id)  # degrade → [] on any Exception
        ...
    @staticmethod
    async def _read_chat_events(scoped_store: Any, run_id: str) -> list:
        try:
            rows = await scoped_store.read_events(run_id, 0)
        except Exception as exc:  # noqa: BLE001 — a read error must not break the agent
            logger.warning("conversation: read_events failed (%s) — no context", exc)
            return []
        return list(rows or [])
```
→ **DEVIATE:** substitute `await scoped_store.list_refs(run_id, kind="upload_text")` for `read_events`. `ectx.scoped_store` is already threaded onto the same `ctx` the provider receives (RESEARCH: set at run entry; the provider loop passes the SAME `ectx` that carries `runner.sandbox`) — zero engine edit.

**Copy this — the current disk read path + block format = the BYTE-EQUIVALENCE TARGET (`uploaded_files.py:83-110`, verified):**
```python
        runner = getattr(ctx, "runner", None)
        sandbox = getattr(runner, "sandbox", None)
        if sandbox is None:
            return {}
        entries = self._read_manifest(sandbox)   # reads .uploads/manifest.json → list
        if not entries:
            return {}
        sections: list[str] = []
        for entry in entries:
            if not isinstance(entry, dict): continue
            name = entry.get("name")
            if not isinstance(name, str) or not name: continue
            if not entry.get("has_text"): continue
            text = self._read_sidecar(sandbox, name)   # reads .uploads/<name>.txt, .strip()
            if not text: continue
            sections.append(f"### {name}\n{text}")
        if not sections:
            return {}
        body = "## Uploaded Files\n\n" + "\n\n".join(sections)
        return {"uploaded_files_context": body}
```
→ **DEVIATE — the single-composer refactor (RESEARCH §Provider Fallback Design; CONTEXT specific idea "one composing function"):** extract this loop into `_compose(self, entries, *, read_text)` so DISK and DURABLE both flow through it → byte-equivalence by construction. Disk path: `read_text = lambda n: self._read_sidecar(sandbox, n)`. Durable path: after `list_refs`, apply the **location-keyed max-version** selection (see analog #4), take the `.uploads/manifest.json` row's `content` as the entries source, and `read_text = lambda n: getattr(latest.get(f"{_UPLOADS_PREFIX}{n}.txt"), "content", "")`. **Disk wins:** try disk manifest first; only fall through to the store when the sandbox manifest is missing. **Neither → `{}`** unchanged.

→ **KEEP (IN-02 / Pitfall 3):** do NOT unify with `run_files._read_manifest`; do NOT import `app.*`. Add the durable branch as a SIBLING inside this module. Import purity (`:40-54`) stays: only `agents.capabilities.registry.register` + stdlib; `_UPLOADS_PREFIX`/`_MANIFEST_REL` stay local constants → lint-imports 4/0 holds.

---

### 3. `graph.py` — additive kind (Task 1 prerequisite)

**Analog:** the `deliverable` member of the same frozenset (P13 / IN-01).

**Copy this — the frozenset to append to (`graph.py:52-70`, verified):**
```python
ARTIFACT_KINDS: frozenset[str] = frozenset(
    {
        "spec", "plan", "task_list", "html_file", "file_bundle",
        "repo_inventory", "repo_diff", "context_pack", "validation_report",
        "merge_conflict", "summary", "patch", "deliverable",
        "clarifications", "planning_context",
    }
)
```
→ **DEVIATE:** append `"upload_text"` (RESEARCH recommended name — ONE kind for both sidecars AND manifest, discriminated by `location`). **No migration** — the `artifact_refs.kind` column is a free String; the vocabulary is advisory-only (`write_ref` at `:148-155` WARNS, never raises). Appending merely silences the advisory for our writes. `test_artifact_graph.py:202-239` asserts warn/silent behavior but does NOT pin the frozenset length → safe.

---

### 4. Location-keyed max-version selection (shipped 46-03 idiom — reuse in Task 2 read)

**Analog:** `_rematerialize_artifacts_to_disk` (`engine.py:6021-6034`, verified).

**Copy this exact idiom:**
```python
        latest: dict = {}
        for row in rows or []:                     # list_refs → ORDER BY version ASC
            location = getattr(row, "location", None)
            if ...: continue
            prev = latest.get(location)
            if prev is None or getattr(row, "version", 0) >= getattr(prev, "version", 0):
                latest[location] = row
```
→ **DEVIATE:** key on `row.location` alone (all rows are already `kind="upload_text"` from the filtered `list_refs`). Because `list_refs` orders by `version ASC` and the per-`(run_id,kind)` counter only grows, the LAST row per location is its max version — correct for the version-stacking manifest snapshots AND the (in practice single-versioned, dedupe-renamed) sidecars. `latest[".uploads/manifest.json"]` = the final full snapshot; `latest[".uploads/<name>.txt"]` = each sidecar.

---

### 5. Test idioms

**`test_run_files_upload.py` — DB-backed `env` fixture (`:44-90`, verified):** in-memory SQLite via `create_engine("sqlite:///:memory:", ..., poolclass=StaticPool)`, `Base.metadata.create_all` (includes `artifact_refs`), monkeypatches `_get_db` on BOTH `run_files` and `run_engine` modules AND `database.SessionLocal` (so `ScopedStore(session=None)` binds the test session), temp `RUNS_ROOT`.
→ **EXTEND (Wave 0):** after `POST /files` a `.pdf` (monkeypatch `extract_upload_text` → text, existing pattern), open a session, assert `artifact_refs` rows: `kind="upload_text"`, `location==".uploads/<safe>.txt"` / `".uploads/manifest.json"`, `content==` the sidecar `capped` / manifest json str, `producer_step=="upload"`, `producer_agent=="upload"`, `task_id is None`. Add: best-effort degrade (patch `store.write_ref` → `SQLAlchemyError` → 200 + warning); no-row-on-415; text-less upload writes manifest row only.

**`test_uploaded_files_provider.py` — `_FakeSandbox` + `_ctx` unit harness (`:41-75`, verified)** and the **3-agent sticky-context scripted-engine harness `_staged_ectx` / `_compose` (`:229-263`, verified).**
→ **EXTEND (Wave 0):** add a `_FakeScopedStore` with `async def list_refs(run_id, kind=None)` returning `SimpleNamespace(location=..., content=..., version=..., kind="upload_text")` rows (manifest + sidecars); return `[]` for a foreign `run_id` (models default-deny → the cross-owner denial test). Unit: compose disk body from a staged `_FakeSandbox`, then a wiped ctx (`runner.sandbox=_FakeSandbox()` EMPTY + `scoped_store=_FakeScopedStore(<same content>)` + `run_id`); assert `disk_body == durable_body` (byte-equivalence). Assert disk-wins (both present → disk content). Assert empty `list_refs` → `{}`.
→ **EXTEND the 3-agent proof:** clone `_staged_ectx` into a `_wiped_resume_ectx` where `ectx.runner = SimpleNamespace(sandbox=_FakeSandbox())` (empty) + `ectx.scoped_store = _FakeScopedStore(<durable rows>)` + `ectx.run_id`; loop the same `ordered` 3-agent list through `engine._compose_context_message` and assert `_UPLOAD_TEXT in msg` + `"## Uploaded Files" in msg` for EVERY agent — the wiped-sandbox resume proof.

**`test_restart_resume.py` — wiped-sandbox integration shape (`:1123-1211`, verified):** `_build_rematerialize_ctx` returns `(ectx, sandbox, store, run_id)` with a REAL `ScopedStore(session=session)` + a fresh empty `RunSandbox`; drives `_rematerialize_artifacts_to_disk` and asserts `sandbox.read(".uploads/doc.txt") is None` (the fence holds).
→ **REFERENCE only:** confirms the `.uploads/` re-materialization fence STAYS (no disk write-back — the provider reads durably). Do NOT add re-materialization of uploads.

---

## Shared Patterns

### Best-effort durable write (catch-only-`SQLAlchemyError`)
**Source:** `_dual_write_artifact` (`engine.py:5559-5573`) + 46-02 sibling (`kernel_services.py:1451-1456`).
**Apply to:** every durable `write_ref` in `run_files.py`. Catch ONLY `SQLAlchemyError` → loud `logger.warning`; re-raise all else. Never blanket-swallow (Pitfall 1).

### Kernel-pure store read from a provider
**Source:** `conversation.py:75-103`.
**Apply to:** the `uploaded_files.py` fallback. `getattr(ctx, "scoped_store", None)` + `getattr(ctx, "run_id", None)` guard → degrade-to-`{}`; the `list_refs` in a try/except → `[]`. No `app.*` import.

### Ownership default-deny (proof by construction)
**Source:** `ScopedStore.list_refs` (`authz.py:229-247`) — `_scope_with_visibility` + `ORDER BY version ASC`; a cross-owner run yields `[]`.
**Apply to:** the denial test — a `_FakeScopedStore` returning `[]` models it exactly; fallback degrades to `{}`.

### str-not-bytes content (byte-equivalence)
**Source:** `authz.write_ref` maps `content=ref.content` to a Text column; the provider disk path reads back a str.
**Apply to:** store `content=capped` and `content=json.dumps(...)` as STR, `content_hash=sha256(content.encode("utf-8")).hexdigest()` over that same str (Pitfall 2).

---

## No Analog Found

None. Every pattern has a shipped in-repo precedent (this is a brownfield extend-in-place phase; INV-12 forbids parallel paths).

---

## Anchor Verification

| RESEARCH/CONTEXT citation | Verified current location | Status |
|---------------------------|---------------------------|--------|
| `run_files.py:166-170` Layer-2 `ScopedStore` | `:166-170` | ✅ EXACT |
| `run_files.py:227-270` manifest lock + disk writes | `:227-270` | ✅ EXACT |
| `run_files.py:256` manifest append-merge | `:256` | ✅ EXACT |
| `authz.py:134-210` `write_ref` / `force_db_version` | `:134-210` | ✅ EXACT |
| `authz.py:229-250` `list_refs` order-by-version | `:229-250` (asc, ends `:250`) | ✅ EXACT |
| `graph.py:52-70` `ARTIFACT_KINDS` | `:52-70` (15 members, `deliverable` at `:66`) | ✅ EXACT |
| `conversation.py:75-103` `ctx.scoped_store` read | `:75-103` | ✅ EXACT |
| `uploaded_files.py:73-138` load + block format | `:73-138` | ✅ EXACT |
| `_dual_write_artifact` best-effort | cited `engine.py:5555-5573` → actual **`:5556-5573`** (try at `:5557`) | ⚠️ MINOR DRIFT (−1) |
| 46-02 `force_db_version` sibling-capture | cited `kernel_services.py:1387-1454` / `:1430-1448` → actual write block **`:1429-1456`** | ⚠️ MINOR DRIFT |
| 46-03 `_rematerialize` location-keyed max-version | cited `engine.py:6021-6034` → actual **`:6021-6034`** | ✅ EXACT |
| `.uploads/` re-materialization fence | `engine.py:6030-6031` — **already reads "Phase-47 fence"** | ✅ SHIPPED AHEAD (fence + `_FILE_KINDS` exclusion already in place; do NOT re-add) |
| `sandbox.py` `.uploads/` deliverable exclusion | `:41` `_UPLOADS_PREFIX`, `:244` `startswith` skip | ✅ EXACT |
| `test_run_files_upload.py` `env` fixture | `:44-90` | ✅ EXACT |
| `test_uploaded_files_provider.py` 3-agent harness | `:229-263`, drift-guard `test_known_count_is_sixty_nine` at `:199-201` | ✅ EXACT (count=69) |
| `test_restart_resume.py` wiped-sandbox shape | `:1123-1211` | ✅ EXACT |

**Two flags for the planner:**
1. The `.uploads/` re-materialization fence AND `_FILE_KINDS` exclusion in `_rematerialize_artifacts_to_disk` (`engine.py:6023,6030-6031`) are **already shipped** (comment literally says "Phase-47 fence"). CONTEXT/RESEARCH say "46-03 exclusion STAYS" — correct; the plan must NOT re-add or modify it, only confirm it holds (the restart_resume test at `:1211` already asserts it).
2. Best-effort/46-02 line numbers drifted ±1–2; the idioms themselves are unchanged. Excerpts above use the re-verified lines.

## Metadata

**Analog search scope:** `backend/app/api/`, `backend/agents/capabilities/context_providers/`, `backend/agents/artifacts/`, `backend/agents/authz.py`, `backend/agents/execution_engine/{engine,kernel_services}.py`, `backend/app/agents/sandbox.py`, `backend/tests/{unit,agents}/`.
**Files scanned:** 9 source + 3 test files, all excerpt-read (no re-reads).
**Pattern extraction date:** 2026-07-19
