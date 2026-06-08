---
phase: 5
slug: typed-artifacts-persistence-ownership-1b
status: verified
threats_open: 0
asvs_level: 1
created: 2026-06-08
---

# Phase 5 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.
> **Audit type:** threat-mitigation verification of plan-time dispositions (`register_authored_at_plan_time: true`) — not a blind vuln scan.
> **Verdict:** SECURED — 19/19 threats resolved (17 mitigate CLOSED, 2 accept CLOSED). `block_on: high`.
> Every mitigation was verified present in the implementation by grep/read at the named location; implementation files were not modified.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| caller principal → store reads | Every artifact/run/workspace/event read crosses the ownership boundary; `ScopedStore` is the single default-deny enforcement point (§19). | `owner_id`, `workspace_id`, run/artifact rows |
| WS run start → `execute()` | `user_id`/`session_id` cross into the engine; an unauthenticated run must still receive a real non-None DB principal. | user/session identity → `owner_id` |
| revision run → parent run artifacts | `_handle_revision` reads a DIFFERENT run's artifacts; the caller must own that parent run or be denied (cross-owner read = IDOR). | parent `run_id`, parent artifact bodies |
| engine emit → durable `run_events` log | Every event is persisted; a malformed/duplicated `seq` would break replay ordering / idempotency. | `seq`, `event_id`, event payloads |
| HTTP client → `GET /api/runs/{id}/artifacts\|events` | Untrusted `{id}` + `after` cross into the read path; another owner's run must not be readable and inputs must not reach raw SQL. | path `{id}`, `after` query, inline `content` |
| migration runner → DB | `0014` backfill writes production schema (unscoped row = default-deny bypass); `0015` drops a table (irreversible downgrade = no rollback). | `owner_id`/`workspace_id` backfill, `workflow_artifacts` DROP |
| disk principal vs DB principal | Decoupling `owner_id` from the sandbox disk key prevents an anon DB-principal change from altering disk paths (CTX-05 / 0A byte-identity). | `disk_principal` vs `owner_id` |
| agents kernel → `app.api` | The kernel/typed-artifacts packages must not import the web layer (import-direction elevation). | Python import edges |

---

## Threat Register

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-5-IDOR | Information Disclosure / Elevation | ScopedStore reads + `GET /artifacts`/`/events` + WS reconnect | mitigate | Default-deny `owner + (workspace OR visibility)` filter on every read; cross-owner/missing → 404 never 403 | closed |
| T-5-SEED | Elevation | relocated `assert_owns(parent_run_id)` + `_handle_revision` cross-run reads | mitigate | Real store lookup of parent's true `owner_id`; `PermissionError` on mismatch; called ABOVE cross-run reads | closed |
| T-5-ANON | Spoofing | `execute()` owner derivation / anon principal | mitigate | `owner_id = user_id or "anon:<session_id>"` — never None; anon sessions isolated by the same filter | closed |
| T-5-SQLI | Tampering | ScopedStore `.filter()` + `runs.py` `{id}`/`after` | mitigate | Parameterized ORM only (no raw SQL/interpolation); `after: int` coerced (non-int → 422) | closed |
| T-5-NULLOWNER | Elevation | `artifact_refs` / `run_events` / `run_capabilities` | mitigate | `owner_id` + `workspace_id` `nullable=False` on all new tables; `write_ref` rejects falsy owner | closed |
| T-5-BACKFILL | Tampering / Info Disclosure | `0014` default-workspace backfill | mitigate | Scopes every existing run (`owner_id`+`workspace_id`); idempotency guard prevents double-backfill | closed |
| T-5-CONTENT | Information Disclosure | inline `content` on `GET /artifacts` | mitigate | `content` excluded by default; returned only under `?include=content` for the same owner | closed |
| T-5-WEBIMPORT | Elevation (import-direction) | `agents/authz.py` imports | mitigate | Imports `app.models` only, never `app.api`; `lint-imports` contract holds | closed |
| T-5-PURITY | Elevation (import-direction) | `agents/artifacts/` package | mitigate | Stdlib-only (no `app.*`); `lint-imports` contract holds | closed |
| T-5-CTX05 | Tampering (byte-drift) | RunSandbox / `create_runner` disk keying | mitigate | `disk_principal = user_id or "anon"` decoupled from `owner_id`; no disk-keying site uses `owner_id` | closed |
| T-5-REPLAY | Tampering | `run_events` seq/event_id sink + `/events` replay | mitigate | One monotonic `itertools.count(1)` at single emit boundary; uuid `event_id`; `seq > after` ascending | closed |
| T-5-MIGRATE-DOWN | Denial of Service | `0014` `downgrade()` | mitigate | Reverses cleanly to `0013`; no irreversible op in `0014` | closed |
| T-5-DROP-DOWN | Denial of Service | `0015` `downgrade()` | mitigate | Recreates `workflow_artifacts` with original shape + index; reversible | closed |
| T-5-CUTOVER | DoS / data loss | mirror + thin-store deletion | mitigate | Deletion gated on zero live consumers + 0A parity; `0015` sequenced last | closed |
| T-5-HITL | Denial of Service | thin-store HITL half | mitigate | Only artifact-persistence methods removed; `asyncio.Event` HITL half + `get_artifact_store` preserved | closed |
| T-5-PARITY | Tampering (regression) | producer-write + revision-read migration | mitigate | Persistence target changed (thin store → `artifact_refs`), not deliverable bytes/event stream; 0A parity | closed |
| T-5-RATCHET | Tampering (regression) | ledger L15 ratchet | mitigate | L15 grep ratchet armed; reintroducing mirror/thin-store-model fails CI | closed |
| T-5-HASH | Tampering | `content_hash` in `write_ref` | accept | content-addressing (dedup/lineage), not a security control; sha256, no secret material | closed |
| T-5-SC | Tampering | npm/pip/cargo installs | accept | Zero packages installed this phase; no manifest change in any Phase-5 commit | closed |

*Status: open · closed*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

### Verification Evidence (file:line)

| Threat ID | Evidence |
|-----------|----------|
| T-5-IDOR | Default-deny filters `agents/authz.py:111-117` (`_scope_with_visibility`: `owner_id == :owner AND (workspace_id == :ws OR visibility IN ('workspace','public'))`) + `:124-127` (`_scope_owner_ws`), applied on every read (`get_ref:223`, `list_refs:245`, `lineage:261`, `read_events:325`, `get_run:345`). API IDOR→404 (never 403) `app/api/runs.py:634-638`+`649-653` (artifacts), `:679-683`+`692-696` (events) — owner-filter query AND `ScopedStore.get_run`→None→404. WS reconnect owner-scoped `app/api/websocket.py:550-555`. |
| T-5-SEED | `assert_owns` real lookup raising `PermissionError` on mismatch `agents/authz.py:512-532`; called ABOVE cross-run reads `engine.py:2722` (precedes `list_refs` `:2725`); build-loop seam `engine.py:871`; IN-01 owner_id truthy guard at `_handle_revision` entry `engine.py:2669-2672`. |
| T-5-ANON | `owner_id = user_id or f"anon:{session_id or pipeline_run_id}"` `engine.py:700` (never None); real-principal invariant documented `authz.py:76-78`. |
| T-5-SQLI | Parameterized `.filter()` only — zero raw-SQL/f-string interpolation in `agents/authz.py` (no `execute(`/`text(`/`f"SELECT`/`%s`/`.format`); `after: int = 0` int-coerced `app/api/runs.py:663`. |
| T-5-NULLOWNER | `nullable=False` on `artifact_ref.py:34-35`, `run_event.py:30-31`, `run_capabilities.py:28-29`; migration mirrors `0014:46-47,105-106,123-124`; `write_ref` rejects falsy owner `authz.py:162-167`. |
| T-5-BACKFILL | `0014_typed_artifacts_persistence.py:185-209` scopes every existing run; WR-07 idempotency guard (`workspace_id IS NULL`) `:185-188`. |
| T-5-CONTENT | `_build_lineage_tree(refs, include_content=(include == "content"))` `app/api/runs.py:656`; content added only when set `:547-548`. |
| T-5-WEBIMPORT | `agents/authz.py` imports `app.models.*` + `SessionLocal` only; zero `app.api` (grep clean); `lint-imports` → 3 kept, 0 broken. |
| T-5-PURITY | `agents/artifacts/{graph,__init__}.py` stdlib-only (`hashlib`/`uuid`/`dataclasses`/`__future__`); zero `app.*`; `lint-imports` green. |
| T-5-CTX05 | `disk_principal = user_id or "anon"` `engine.py:693`, decoupled from `owner_id` `:700`; disk-keying sites use `disk_principal` `:694,881,1289,1566,2038`; decoupling documented `context.py:69-75`. |
| T-5-REPLAY | One `itertools.count(1)` at single emit boundary `engine.py:575`; `seq`/uuid `event_id` `:599-602` → `append_event` `:605`,`authz.py:284-309`; revision path mirrors `engine.py:2701-2717`; read `seq > after` ascending `authz.py:321-326`, API `:698-711`. |
| T-5-MIGRATE-DOWN | `0014…downgrade()` `:212-237` reverses to 0013; no irreversible op. |
| T-5-DROP-DOWN | `0015_drop_thin_artifact_store.py:31-58` recreates table + `ix_workflow_artifacts_run_type`; `down_revision="0014"`. |
| T-5-CUTOVER | `0015` sequenced last (`down_revision="0014"` `:22`); thin-store persistence methods + `WorkflowArtifact` gone (only deletion-note comments remain); 0A parity gate (05-07). |
| T-5-HITL | `agents/artifact_store/store.py:29-119`: `asyncio.Event` HITL half + `get_artifact_store()` preserved; only persistence methods removed. |
| T-5-PARITY | Producer writes route `ectx.artifacts.write_ref`→`ScopedStore.write_ref` `engine.py:2964,2977-2980`; `seq`/`event_id` stripped from 0A multiset (`_VOLATILE_STRIP_KEYS` `engine.py:568-569`); UAT 10/10 (`05-UAT.md`). |
| T-5-RATCHET | L15 in `tests/agents/test_migration_ledger.py:37`; flipped-set assertion `:150-151` ({D2,L14,L15,L16}). |
| T-5-HASH | `graph.py:121` `hashlib.sha256(content.encode("utf-8")).hexdigest()` — deterministic, no secret material; rationale `graph.py:22-24`, `artifact_ref.py:41`. |
| T-5-SC | All 7 SUMMARYs `tech-stack added: []`; RESEARCH "no `pip install`" (`05-RESEARCH.md:208`); no Phase-05 commit touches `requirements.txt`/`pyproject.toml`. |

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-5-HASH | T-5-HASH | `content_hash` is sha256 content-addressing for dedup/lineage, NOT a security control — deterministic, no secret material, no auth/integrity decision keys off it. | gsd-security-auditor | 2026-06-08 |
| AR-5-SC | T-5-SC | Zero packages installed this phase; no Phase-5 commit modifies `requirements.txt`/`pyproject.toml` (manifest changes owned by Phase 0/1/4). | gsd-security-auditor | 2026-06-08 |

*Accepted risks do not resurface in future audit runs.*

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-06-08 | 19 | 19 | 0 | gsd-security-auditor (opus, ASVS L1, block_on=high) |

**Review-cycle context:** 3 review/fix iterations. Security findings IN-01 (`_handle_revision` owner_id fail-loud, commit `38077bf`) and IN-02 (`set_run_scope` same-owner re-scope guard, commit `8be60ae`) were applied and are present in the audited code (`engine.py:2669-2672`, `authz.py:399-404`). IN-03 (revision `pipeline_complete` constant duration/agent counts) was a non-security intentional Phase-3 stub, correctly deferred.

**Unregistered flags:** None. Both SUMMARY `## Threat Flags` sections (`05-02`, `05-05`) report "None"; no unmapped attack surface appeared during implementation.

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-06-08
