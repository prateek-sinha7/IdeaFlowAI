# Phase 5: Typed Artifacts + Persistence + Ownership [1B] - Research

**Researched:** 2026-06-07
**Domain:** Brownfield strangler refactor — typed artifact graph, additive Postgres/SQLAlchemy persistence, default-deny ownership, durable event log; Python · FastAPI · SQLAlchemy (sync) · Alembic
**Confidence:** HIGH (all five priority directives confirmed against code; one CONTEXT premise corrected — see D-08 and D-11)

## Summary

The WHAT (14 reqs in `05-SPEC.md`) and HOW (D-01..D-13 in `05-CONTEXT.md`) are fully locked. This research confirms the codebase facts those locks depend on and flags **three places where a locked decision collides with the actual code** so the planner plans against reality:

1. **D-08 "async DB session" is half-wrong.** The thin store methods are `async def`, but the DB layer is **fully synchronous** (`create_engine` + `sessionmaker` → `SessionLocal`, `app/models/database.py`). The store opens a blocking `SessionLocal()` *inside* its `async def` methods. There is no `AsyncSession` anywhere (the only async-DB thing is the LangGraph `AsyncPostgresSaver` checkpointer, which is unrelated). The relocated scoped helper should reuse the **sync `SessionLocal()` inside `async def`** pattern; the two new `runs.py` endpoints can be `async def` but must call sync session code (fine in FastAPI's threadpool, and matches the existing thin-store idiom).

2. **D-11 "reuse the engine's EXISTING per-run `seq`" — there is no existing `seq`.** Confirmed by `tests/agents/characterization/_normalize.py:189` ("The current engine does NOT stamp a `seq` on its event dicts") and by inspecting all 27 `yield {…}` sites in `engine.py` — none carry `seq`. `assert_seq_contiguous` is a **vacuous pass today**. So Phase 5 must *introduce* a single monotonic counter at one chokepoint (it cannot "reuse" one). The good news: a fresh counter is SAFE-03-compatible because the contract is on **deltas == 1**, not absolute values, and `seq`/`event_id` are not in the characterization snapshot (normalize strips/never-includes them).

3. **`workflows` table name collides.** `app/models/workflow_definition.py` **already** declares `__tablename__ = "workflows"` (model `WorkflowDefinition`, migration created it, has `user_id` FK, `agents`/`artifact_edges`/`constitution_ref` JSON columns). The §18 `workflows` (definitions metadata: `owner_id`, `workspace_id`, `source`, `manifest_json`, `version`) is a **different shape** for the same logical concept. This is an **extend/reconcile**, not net-new — see priority answer #5.

**Primary recommendation:** Plan exactly the five D-13 slices. Treat the three collisions above as explicit early tasks: (a) wrap a sync-session scoped helper, (b) add a single `seq`-stamping event sink, (c) reconcile/extend the existing `workflows` table. Update `test_migration_ledger.py`'s hard-coded `flipped == ["L14","L16"]` assertion when L15 flips (it WILL break otherwise — see Validation Architecture).

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions (D-01..D-13 — verbatim summary; full text in 05-CONTEXT.md)

- **D-01:** `artifact_refs` keeps an INLINE `content: Text` column AND records `content_hash` + `location`. `content_hash = sha256(content.encode("utf-8")).hexdigest()` over the inline content. `location` still populated (sandbox-relative path for file-backed, logical store id `artifact_refs/{id}` for string artifacts). Rejected: pointer-only, hybrid.
- **D-02:** Package layout per plan §32 exactly. Typed graph → `agents/artifacts/` (sibling of kernel, NOT inside `execution_engine/`): `graph.py` (ArtifactGraph + ArtifactRef dataclass = plan §6 lines 454-466 + inline `content`). SQLAlchemy row model → `app/models/artifact_ref.py` (`ArtifactRef` table `artifact_refs`), replacing `app/models/artifact.py`'s `WorkflowArtifact`. Mapping dataclass↔row in the store helper. One name everywhere, snake_case.
  - *(NOTE: CONTEXT.md D-02 body says `agents/artifacts/`; SPEC ART-01 target text says `agents/execution_engine/artifacts/`. D-02 is the controlling decision and matches plan §32 — use `agents/artifacts/`. Flagged in Open Questions.)*
- **D-03:** Split chain — `0014_typed_artifacts_persistence` (additive, off `0013`), `0015_drop_thin_artifact_store` (destructive DROP `workflow_artifacts`, lands LAST after read-cutover + parity green). Indexes: `artifact_refs (run_id, kind)` + `(content_hash)`; `run_events (run_id, seq)`. Default-workspace backfill (data step inside `0014` or tiny `0014b`): one default `workspaces` row per existing run + set `workflow_runs.owner_id = user_id`, `workspace_id`. Rejected: single add+drop migration.
- **D-04:** New runs create their default workspace at `execute()` entry (`kind=sandbox`, `runtime=local`, `ttl=run_ttl`); set `ExecutionContext.workspace_id`. Backfill handles only pre-existing rows.
- **D-05:** Flip ledger L15 ☑ (arms `accumulated_outputs` grep ratchet → 0 in non-test) + add a thin-store deletion gate (`WorkflowArtifact`/`workflow_artifacts` + `store`/`retrieve_*`/`list_*` → 0). Migration-ledger CI guard + import-linter stay green.
- **D-06:** Default-deny scoped-query helper lives in `agents/authz.py` (plan §32). Phase 2's pure `assert_owns` (`agents/execution_engine/authz.py`) **relocates up** + grows into store-layer helper. Constructed with caller principal `(owner_id, workspace_id)` + DB session; every read filters `WHERE owner_id = :owner AND (workspace_id = :ws OR visibility IN ('workspace','public'))`. Candidate surface: `write_ref`, `get_ref`, `list_refs`, `lineage/tree`, `append_event`, `read_events`, `get_run`, `create_workspace`, `record_capabilities`. Rejected: free functions, leaving assert_owns in kernel.
- **D-07:** `assert_owns` becomes a real-lookup method (looks up parent run's `owner_id` from store, raises typed `PermissionError` on mismatch). L16 call-site in `engine.py` rewires to relocated helper. `test_parent_run_ownership.py` stays green (now via store lookup); AUTHZ-04 adds artifact + workspace denial tests.
- **D-08:** Store methods are `async`; cross-owner denial surfaces as **404** at the API. Two new `runs.py` endpoints become `async def` (existing sync handlers stay sync). *(Researcher correction below: the underlying DB session is SYNC.)*
- **D-09:** At `execute()` entry: `ctx.owner_id = user_id or f"anon:{session_id}"` (never None); `ctx.workspace_id = <default workspace row id>`. Add `artifacts: ArtifactGraph` and `workspace_id: str` to `ExecutionContext`. **CRITICAL byte-identity guard:** `RunSandbox` on-disk keying stays `user_id or "anon"` — do NOT derive sandbox dir from new `ctx.owner_id`. `ctx.owner_id` is persisted DB principal only.
- **D-10:** `GET /api/runs/{id}/artifacts` returns nested lineage TREE (each node = ArtifactRef fields + `children: []`, assembled by walking `parents`/`derived_from`). Inline `content` excluded by default; `?include=content` flag is planner's call. Cross-owner → 404.
- **D-11:** Durable `run_events` reuses the engine's per-run `seq` — do NOT invent a second counter. Tap a persistence sink at the event-emit boundary. `GET /api/runs/{id}/events?after=<seq>` returns rows `seq > after`, ascending, each with `event_id`. Rejected: fresh DB-side seq. *(Researcher correction below: no `seq` exists yet — must introduce ONE at the sink.)*
- **D-12:** `run_capabilities` row written at `execute()` entry, one row per run, `runtime = langchain_deepagents`; deferred columns (`model_overrides`→P6, `skills`/`hooks`/`integrations`/`mcp_servers`→P8/P9) present + nullable/empty.
- **D-13:** Sequence = add → dual-write → migrate reads → delete, parity-gated. (1) `0014` schema + graph + helper + owner/workspace population; (2) dual-write typed refs alongside mirror + thin store; (3) migrate engine reads + `websocket.py:543` clarifications read; (4) durable sink + capabilities + endpoints; (5) once 0A parity green — delete mirror (L15 ☑) + thin store + apply `0015`.

### Claude's Discretion
- Exact field names/order inside `ArtifactGraph`/`ArtifactRef` (within D-01's set) and dataclass↔row mapping location.
- Whether default-workspace backfill is a data step inside `0014` or a tiny separate `0014b`.
- Plan-task granularity / split across D-13's five concerns.
- The `?include=content` content-fetch shape for API-04.
- Whether `run_capabilities` inserted at run start (D-12) or upserted at completion (exactly one row, `runtime=langchain_deepagents`).
- Exact `async def` route handler signatures / response models / auth dependencies for the two new endpoints (mirror existing `runs.py`).

### Deferred Ideas (OUT OF SCOPE)
- Retention sweep/janitor → Phase 9 (field only here).
- `RuntimeEnvironment`/`Workspace` runtime port + `LocalSandboxRuntime` → Phase 9 (`workspaces` schema-only + default per-run row; `ctx.workspace: Workspace` lands then).
- `repositories` → P9; `subagent_runs` → P11; `wave_runs` → P12; `validation_results`/`gate_events`/`hook_runs` → P8.
- `model_overrides` population → P6; `budget_snapshot_json` population → P11 (columns land additively now, nullable/empty).
- Content dedup / replay-reuse on hash match → P12 (`content_hash` recorded + indexed now, no reuse).
- `GET /api/runs/{id}/diff` (repo diff) + new run-stream event types → Phase 9 / their phases. Existing event contract stays semantic-parity.
- DB-authored user workflows → v2 (`workflows` table is file-backed manifest metadata only this phase).
- Deleting kernel leaks L1–L13 / prototype-as-manifest parity → Phase 7. Only L15 (mirror) + thin store deleted here.
- `engine.py`→`kernel.py` split + import-linter tightening → Phase 7. This phase keeps `engine.py`.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| ART-01 | ArtifactGraph/ArtifactRef typed DAG replaces `accumulated_outputs` + thin store | `agents/artifacts/graph.py` net-new; dataclass mirrors plan §6:454-466 + inline `content`; write/read replaces 42 `accumulated_outputs` refs (engine.py 12 sites) + thin-store calls (engine.py:1182/1505/2377 writes, 2320/2328/2331 reads; clarify_engine.py:396) |
| ART-02 | Lineage fields on every write (producer step/agent/task, content_hash, location, version, parents, visibility, retention) | `WorkflowArtifact` precedent has `producing_agent_id`/`version`/`derived_from_artifact_id`/`content`; `artifact_refs` extends per §6:454-466 |
| ART-03 | Typed produces/consumes routing replaces string matching | `_filter_consumed_outputs` (engine.py:2458) + `_build_context_sources` already read AGENT.md `produces`/`consumes` via `WorkflowResolver`; route by ArtifactRef.kind not substring |
| ART-04 | Retention default `run_ttl`, `keep`/`days:N` overrides | Field on dataclass + column; no sweep (P9). `ArtifactRef.retention="run_ttl"` default per §6:466 |
| PERSIST-01 | Additive `0014+` migrations; every new table carries owner_id+workspace_id; idx as specified | `0013` head confirmed; `revision="NNNN"`/`down_revision` string pattern; env.py uses `Base.metadata` autogenerate-capable (but hand-author recommended — see migration notes) |
| PERSIST-02 | Dual-write → delete mirror AND thin store; rewire websocket clarifications read; keep HITL half | Full thin-store consumer map below; HITL `asyncio.Event` half (get_resume_event/set_questionnaire_responses/get_review_event/set_review_response) stays |
| PERSIST-03 | Durable run_events: monotonic per-run seq + event_id + type + payload_json; idx (run_id, seq) | No seq exists today — introduce at sink (see D-11 answer); 27 yield sites funnel through `execute()` generator |
| AUTHZ-01 | owner_id + workspace_id everywhere; owner_id string principal; user_id FK retained | `workflow_runs` has `user_id` FK + `session_id`; add `owner_id`/`workspace_id`; authed `owner_id == user_id` |
| AUTHZ-02 | Default-deny scoped-query helper; assert_owns relocated, real store lookup | Relocate `agents/execution_engine/authz.py` → `agents/authz.py`; grow into helper (D-06) |
| AUTHZ-03 | Anon principal `anon:<session_id>` never None | session_id source confirmed = `user.id` (see #3); for true-anon needs a stable id — flag (see #3) |
| AUTHZ-04 | Cross-owner parent/artifact/workspace denial tests pass | Extend `test_parent_run_ownership.py` (4 existing tests) + new artifact/workspace denial tests |
| CAPRUN-01 | run_capabilities row, runtime=langchain_deepagents, deferred cols nullable | Source from CapabilityRegistry / CompiledWorkflow (Phase 4); written at execute() entry |
| API-04 | GET /api/runs/{id}/artifacts lineage tree, cross-owner denied | Mirror `runs.py` IDOR pattern (sync filter → 404); async handler |
| API-05 | GET /api/runs/{id}/events?after=<seq> ascending seq>after, event_id, cross-owner denied | Reads `run_events` via scoped helper |
</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| ArtifactGraph typed routing (in-run handoff) | Kernel (`agents/`) | — | Per-run substrate on `ExecutionContext`; pure typed data, kernel-importable (`agents/artifacts/`) |
| Artifact persistence (read/write rows) | Store helper (`agents/authz.py`) | Database | Default-deny scoped queries; DB-touching, NOT in kernel's forbidden `app.api` set |
| Ownership enforcement | Store helper | Kernel call-site | `assert_owns` relocates; engine calls helper, helper hits store |
| Durable event log (seq sink) | Event-emit boundary | Database | Single chokepoint wrapping `execute()` generator stamps seq + persists |
| Migrations / schema | Alembic (`app/models/*` + `alembic/versions/`) | Database | Additive only; models register on `Base.metadata` |
| API endpoints | `app/api/runs.py` (FastAPI) | Store helper | HTTP layer calls INTO store/kernel, never reverse (import-linter scaffold) |
| owner/workspace population | Kernel `execute()` entry | Store helper | `ctx.owner_id`/`workspace_id` set per run; persisted via helper |

## Priority Question Answers (the five CONTEXT "Researcher directive:" callouts)

### #1 (D-02) — Import-linter contract: CONFIRMED, no collision

The **exact** contracts in `backend/pyproject.toml` (`[tool.importlinter]`, `root_packages = ["agents", "app"]`):

1. **"kernel imports only capability ports (scaffold)"** — `forbidden`, `source_modules = ["agents.execution_engine.engine"]`, `forbidden_modules = ["app.api"]`. The kernel (today = `engine.py`) must NOT import `app.api`. (lines 134-146)
2. **"agents.workflows must not import the execution kernel or the web layer"** — `forbidden`, `source = ["agents.workflows"]`, `forbidden = ["agents.execution_engine", "app"]`. (lines 159-163)
3. **"agents.capabilities must not import the execution kernel or the web layer"** — `forbidden`, `source = ["agents.capabilities"]`, `forbidden = ["agents.execution_engine", "app"]`. (lines 165-169)

**Findings for the Phase-5 layout:**
- `agents/artifacts/` (typed dataclasses, referenced by `ExecutionContext`) — **kernel-importable, NO contract violation.** It is not a `source_module` in any contract and is not a forbidden target of any contract. The kernel (`engine.py`) may import it freely. `ExecutionContext` (`context.py`) imports ONLY stdlib today (its docstring mandates this); adding `from agents.artifacts.graph import ArtifactGraph` keeps it inside `agents.*` — still no `app.api` reach. **SAFE.** The dataclass must NOT import any `app.models.*` or `app.api.*` to stay clean (mapping dataclass↔row belongs in the store helper, per D-02).
- **The DB-touching scoped helper in `agents/authz.py`** — `agents.authz` is NOT a `source_module` in any contract, so no contract directly constrains it. BUT the helper will `import app.models.*` (SQLAlchemy rows + `SessionLocal`). The ONLY hard rule is `engine.py` ↛ `app.api`. The helper imports `app.models`, NOT `app.api` — **no violation.** Verified `engine.py` today already reaches `app.agents`/`app.core`/`app.models`/`app.services` but never `app.api` (the scaffold comment confirms this, line 142). So `engine.py → agents.authz → app.models` is fine; just keep the helper free of any `app.api` import so the transitive chain `engine → authz → app.api` never forms.
- **engine.py→kernel.py split is Phase 7** — the contract is still the Phase-1 scaffold. Do NOT add the "INTENDED FINAL FORM" block (documented lines 110-121, commented out). Keep new imports inside the existing scaffold. `[VERIFIED: backend/pyproject.toml grep]`

**Risk:** none. Placing the scoped helper in `agents/authz.py` (DB-touching) does NOT violate any current contract.

### #2 (D-08) — DB session flavor: SYNC (CONTEXT premise corrected)

`app/models/database.py`: `engine = create_engine(...)` (sync), `SessionLocal = sessionmaker(..., bind=engine)` (sync). `get_db()` is a sync generator yielding `SessionLocal()`. **There is no `AsyncSession`/`create_async_engine`/`async_sessionmaker` anywhere in `app` or `agents`** (verified by grep — only hit is the unrelated LangGraph `AsyncPostgresSaver` checkpointer in `app/agents/checkpointer.py`, which is the graph-state store, not the ORM).

**How `get_artifact_store()` acquires its session (the pattern to reuse):** the thin store's methods are declared `async def` but acquire a **sync** session *inside* the coroutine:
```python
# agents/artifact_store/store.py:67-106 (store())
from app.models.database import SessionLocal
db = SessionLocal()
try:
    db.query(...).filter(...)...   # blocking ORM calls
    db.add(...); db.commit()
finally:
    db.close()
```
So `async def` here is **cosmetic** — there is no `await` on any DB call; the coroutine runs blocking sync ORM inside the event loop.

**Implication for the relocated scoped helper (D-06/D-08):** reuse the SAME idiom — `async def` methods that open `SessionLocal()` and run blocking sync ORM, then `close()`. Do NOT introduce `AsyncSession` (that would be a new dependency + Alembic/engine change, out of scope and INV-3-risky). The two new `runs.py` endpoints **can be `async def`** (FastAPI runs sync `Depends(get_db)` in a threadpool; an `async def` handler that calls the `async def` helper which runs sync ORM is consistent with the existing thin-store calls made from `async` engine code). Equally valid: make them sync `def` mirroring the existing `runs.py` handlers (all sync `def` with `db: Session = Depends(get_db)`) — the D-08 discretion note allows either. **Recommendation:** for the helper, accept an injected `Session` (so endpoints pass `Depends(get_db)` and the engine passes `SessionLocal()`), keeping one acquisition path. `[VERIFIED: app/models/database.py + store.py grep]`

### #3 (D-09) — Anon principal source + byte-identity guard

**Where a run is created and the stable session id available at `execute()` entry:**
- Run creation: `app/api/websocket.py:1032-1069`. `pipeline_run_id = str(_uuid.uuid4())` (1032); `WorkflowRun(id=pipeline_run_id, user_id=user.id, ..., session_id=user.id)` (1062). So **`session_id` is literally set to `user.id`** (the model comment "= user_id (JWT sub)" is accurate).
- `execute()` is called with `user_id=user.id` (websocket.py:1115). There is **no separate session token threaded into `execute()`** — the engine signature (engine.py:475-489) has `user_id` but NO `session_id` param.
- **The WS pipeline path is authenticated.** `_authenticate(...)` / `get_current_user`-equivalent runs at connect (websocket.py:80, 100-104); `run_pipeline` requires a real `user`. So in the CURRENT live path **`user_id` is always set** and `owner_id == user_id` always — there is no unauthenticated run reaching `engine.execute()` today.

**Confirmation for `anon:<session_id>` (format LOCKED, source needs a decision):** Since today every run is authed, the `anon:<session_id>` branch is **defensive / forward-looking** (AUTHZ-03). For the format `anon:<session_id>` to be meaningful when `user_id is None`, a stable per-session id must be threaded into `execute()`. **Today that id does not exist as a parameter.** Options for the planner:
  - **(a) Add an explicit `session_id: str | None = None` param to `execute()`** and pass the WS connection/session id (e.g. the `chat_session_id` available at websocket.py:396, or a per-connection uuid). This is the cleanest; `owner_id = user_id or f"anon:{session_id}"`.
  - **(b) Reuse `pipeline_run_id` as the session id when unauthenticated** → `anon:<pipeline_run_id>`. Stable per-run, isolates each anon run, never None. Lowest-change.
  - The existing tests (`test_parent_run_ownership.py:45-53,220-240`) exercise `user_id=None` → today yields `owner_id="anon"`. Moving to `anon:<session_id>` will **change that string** and those tests assert `"anon"` exactly (lines 48,53,221). **Those tests must be updated** when D-09 lands. `[VERIFIED: websocket.py + engine.py + test grep]`

**CRITICAL byte-identity guard (confirmed location):** the sandbox is keyed at `engine.py:539` — `sandbox = RunSandbox(user_id or "anon", pipeline_run_id)` — and again for the parent at `engine.py:669` (`RunSandbox(user_id or "anon", parent_run_id)`), and in fix-loop create_runner calls via `ctx.owner_id` at engine.py:1069/1337/1742. **IMPORTANT NUANCE:** several `create_runner(... user_id=ectx.owner_id ...)` sites (1069, 1337, 1742) currently pass `ectx.owner_id` — which TODAY equals `user_id or "anon"`. If D-09 changes `ectx.owner_id` to `anon:<session_id>`, those `create_runner` calls would re-key the sub-agent's `RunSandbox` to `anon:<session_id>/<run>` — a **disk-path change for anon runs → CTX-05 / 0A snapshot break risk.** The guard (D-09) says keep disk keying at `user_id or "anon"`. **Planner MUST decouple the disk-keying principal from `ctx.owner_id`:** introduce a separate `ctx.disk_principal` (or pass `user_id or "anon"` explicitly to those create_runner sites) so `ctx.owner_id` (DB principal) can become `anon:<session_id>` WITHOUT changing any `RunSandbox(...)` key. For authed runs `owner_id == user_id` so no divergence; only anon runs differ — and anon runs are not characterized by the 0A snapshots (which run authed/scripted), but the engine code path is shared, so the decoupling is mandatory to be safe. `[VERIFIED: engine.py:539,669,1069,1337,1742 grep]`

### #4 (D-11) — Event-emit chokepoint + the `seq` correction

**There is NO existing per-run `seq`.** Confirmed two ways:
- `tests/agents/characterization/_normalize.py:189-195`: *"The current engine does NOT stamp a `seq` on its event dicts (events are ordered purely by stream position), so in practice this is a vacuous pass today."* `assert_seq_contiguous` tolerates both `e["data"]["seq"]` and top-level `e["seq"]` but finds neither today.
- All 27 `yield {...}` sites in `engine.py` (lines 743, 760, 842, 970, 1016, 1144, 1235, 1239, 1248, 1293, 1309, 1411, 1427, 1429, 1435, 1465, 1515, 1531, 1563, 1583, 1598, 1696, 2104, 2110, 2139, 2142, 2153) emit dicts of shape `{"type": ..., "data": {...}}` — **none carry `seq` or `event_id`.**

**Therefore D-11 must INTRODUCE a single monotonic counter — it cannot "reuse" one.** This is consistent with D-11's intent ("do not invent a *second* counter / a fresh DB-side seq independent of the stream"): the correct reading is **stamp ONE counter at the single emit chokepoint and use that same value both on the live stream and in the durable sink.** Do not add a Postgres sequence / `MAX(seq)+1` that diverges.

**The cleanest single chokepoint:** `execute()` is an `async def ... -> AsyncGenerator[dict, None]` (engine.py:489). Every event from every internal `yield` (including `_run_agent`, `_emit_planner_events`, gate handlers) bubbles up through this ONE generator before reaching the caller. The consumer is `websocket.py:1104-1123` (`_run_pipeline_to_queue` → `event_queue.put(...)`). Two viable sink insertion points:
  - **(Recommended) A thin async-generator wrapper around `execute()`'s yields** — at the single point where the engine yields outward, or a `_stamp_and_emit` helper that every `yield` is routed through. Cleanest implementation: wrap the body so each outgoing event dict gets `data["seq"] = next(counter)` + `data["event_id"] = uuid4()` stamped, then `await scoped_helper.append_event(run_id, seq, event_id, type, payload_json)`. Because it's stamped at the boundary, every event gets exactly one contiguous seq.
  - **(Alternative) At the WS drain** (websocket.py:1123) — but this misses events when the engine is driven by `ndjson_adapter` or future callers, and splits the stamping out of the kernel. Prefer the engine-boundary wrapper.
  - **NOTE:** `agents/execution_engine/ndjson_adapter.py` is **NOT** the chokepoint — it is a small `run_od_prototype_pipeline` wrapper that re-yields engine events for the od_prototype ndjson path; it does not assign seq. Do not tap it.

**`event_id` and 0A semantic parity — CONFIRMED SAFE.** `_normalize.py` strips/normalizes volatile fields: `_VOLATILE_STRIP_KEYS` includes `run_id`/`pipeline_run_id`/`timestamp`/`model_id`/etc (lines 101-112). `event_id` and `seq` are **not in `_REQUIRED_DATA_KEYS`** (imported from `test_phase3_cutover_verify.py`) — so they are not asserted-present, and the snapshot is an **order-canonical multiset sorted by canonical JSON** (`_canonical_order`, lines 165-178). Adding `seq`/`event_id` to event `data` would, however, **perturb the canonical-JSON sort and the multiset** unless they are also stripped. **Action for planner:** add `seq` and `event_id` to `_VOLATILE_STRIP_KEYS` in `_normalize.py` (they are generated/volatile) so the multiset snapshot is unaffected, AND rely on `assert_seq_contiguous` (already wired, lines 181-209) to assert seq deltas==1. This keeps semantic-event parity green while the durable log gains real values. SAFE-03 contract is on deltas, not absolute values, so a fresh counter passes. `[VERIFIED: _normalize.py + engine.py yield-site grep]`

### #5 (`workflows` table reconcile) — EXTEND the existing table (collision found)

`app/models/workflow_definition.py` **already** defines `class WorkflowDefinition(Base)` with `__tablename__ = "workflows"` (registered in `app/models/__init__.py:13`). Current columns: `id`, `user_id` (FK→users), `name`, `agents` (JSON), `artifact_edges` (JSON), `constitution_ref`, `created_at`, `updated_at`, index `ix_workflows_user`.

The §18 `workflows` (definitions) table wants: `id`, `owner_id`, `workspace_id`, `source` (`file`/`db`), `manifest_json`, `version`, created/updated.

**Reconciliation = EXTEND, not rename or net-new.** Both are "the persisted workflow-definition table." The lowest-INV-3-risk path:
- Keep `__tablename__ = "workflows"` and the `WorkflowDefinition` model (do NOT create a second `workflows` table — Postgres would reject the duplicate name; SQLAlchemy would raise on duplicate `__tablename__`).
- **Additively add** `owner_id`, `workspace_id`, `source` (default `"file"`), `manifest_json` (nullable — file-backed manifests this phase), `version` (default 1) columns via `0014`. Keep existing `agents`/`artifact_edges`/`constitution_ref`/`user_id` (they're populated by the legacy Phase-3 path; nullable-safe to leave).
- **FK/naming collisions:** none fatal. `workflow_runs` references `users.id` and self (`parent_run_id`); there is NO existing FK from `workflow_runs` → `workflows`. §18 adds `plan_id` (not a `workflows` FK — `plan_id` ties to the compiled plan, Phase 4 forward field). The `WorkflowRun` ORM class (`workflow_runs`) and `WorkflowDefinition` ORM class (`workflows`) are distinct — no class-name collision. The only thing to watch: `every new table carries owner_id + workspace_id` (AUTHZ-01) — `workflows` currently has `user_id` but NOT `owner_id`/`workspace_id`; adding them satisfies the invariant. **Recommendation:** add `owner_id`/`workspace_id` as nullable (file-backed manifests have no owner yet — set `owner_id` to a system/`"file"` sentinel or leave nullable per the schema-only nature; DB-authored user workflows are v2). `[VERIFIED: workflow_definition.py + __init__.py + workflow.py read]`

## Additional confirmations (lower priority, needed for clean plans)

### Alembic revision pattern + autogenerate vs hand-author
- `0013_collapse_pipeline_run_id.py`: module-level `revision = "0013"`, `down_revision = "0012"`, `branch_labels = None`, `depends_on = None`. So `0014` chains: `revision="0014"`, `down_revision="0013"`; `0015`: `down_revision="0014"`. Filename pattern `NNNN_name.py`.
- `0013` uses `op.batch_alter_table("workflow_runs")` (for SQLite batch-recreate) + `op.drop_index`/`op.create_foreign_key` — **the batch pattern is mandatory** because dev runs SQLite (FK PRAGMA enabled, database.py:18-28) while prod is Postgres. New table adds + column adds should use `op.create_table` + `op.add_column` (additive — no batch needed for adds); the `0015` DROP of `workflow_artifacts` should use `op.drop_table` (works on both).
- `env.py`: `target_metadata = Base.metadata`; imports `app.models` (side-effect registration, line 45); `compare_type=True` + `compare_server_default=True`. Autogenerate IS available, BUT **hand-author the migration** — the SPEC/CONTEXT specify exact column lists + indexes + a data backfill (default-workspace rows), which autogenerate cannot produce. Use autogenerate only to cross-check the column diff. New model files (`artifact_ref.py`, `workspace.py`, `run_event.py`, `run_capabilities.py`) **must be imported in `app/models/__init__.py`** or autogenerate/metadata won't see them and `alembic check` will drift (the `__init__.py` comment at line 8 documents this requirement). `[VERIFIED: 0013 + env.py + __init__.py read]`

### `accumulated_outputs` read/write sites (scope the read-migration)
42 total references in `agents`+`app` (non-test). In `engine.py` (the mirror — `ExecutionContext.accumulated_outputs`, context.py:85):
- **Writes:** `engine.py:1500` (`accumulated_outputs[spec.id] = output`), `:1571` (edited-output update), `:1599` (error marker), `:1686-1687` (`_build_task_number`/`_build_task_total` scratch), `:1721`/`:1756` (task_html / fixed_html in build loop). These are the dual-write→delete points.
- **Reads:** `:1308` (`_build_context_sources`), `:1331` (`_filter_consumed_outputs`), `:1358`/`:2554`/`:2639`-`:2640` (build-task-number scratch), `:1637` (`prototype-plan`), `:1664`/`:1783`-`:1784` (`_write_build_reference_files` seeds spec.md/tasks.md), `:2426`/`:2472`-`:2473` (`_filter_consumed_outputs` produces∩consumes routing), `:2661` (`prototype-build` current_html).
- **Routing logic to typed-ify (ART-03):** `_filter_consumed_outputs` (engine.py:2458-2473) already intersects `produced & consumes` from AGENT.md and keys by `upstream.id` — this is the string-matched routing the typed graph replaces.
- **NOTE the scratch keys** `_build_task_number`/`_build_task_total` (engine.py:1358,1686,2554,2639) are NOT artifacts — they're transient build-loop counters stuffed into the same dict. The migration must move these to a non-artifact home (e.g. `ctx.current_task_block` siblings) or the typed graph, not treat them as ArtifactRefs. `[VERIFIED: grep accumulated_outputs]`

### Thin-store consumer map (full surface for PERSIST-02 — broader than SPEC enumerated)
The artifact-persistence half to **delete**, and every caller to rewire:
- **Writes via `self._store.store(...)`:** `engine.py:1182`, `engine.py:1505`, `engine.py:2377` (`_handle_revision` new artifact); `clarify_engine.py:396` (`artifact_type="clarifications"` — the write that `websocket.py:543` reads back).
- **Reads:** `engine.py:2320` (`retrieve_latest(parent_run_id, target_artifact_type)`), `:2328` (`list_by_type`), `:2331` (`retrieve_latest(..., "planning_context")`) — all in `_handle_revision`; `websocket.py:543` (`retrieve_latest(_reconnect_run_id, "clarifications")`).
- **KEEP (HITL `asyncio.Event` half):** `get_resume_event`, `set_questionnaire_responses`, `get_questionnaire_responses`, `get_review_event`, `set_review_response`, `get_review_response` — used by `clarify_engine.py:109,127`, `engine.py:2093,2125,2198`, `websocket.py:664` (`submit_questionnaire`), `websocket.py:682` (`approve_review`). These survive (Phase 8 owns HITL).
- **`_handle_revision` is the heaviest consumer** (engine.py:2300-2394) and overlaps with ledger item D1 (which is **voided/deferred** — `_handle_revision` is the LIVE `run_revision` PPT handler, NOT dead). So PERSIST-02 must migrate `_handle_revision`'s store reads/writes to the typed graph WITHOUT deleting `_handle_revision` itself. `[VERIFIED: grep self._store + clarify_engine grep]`

### IDOR/404 pattern in runs.py (mirror for the two new endpoints)
`runs.py` handlers are **sync `def`** with `current_user: User = Depends(get_current_user)` + `db: Session = Depends(get_db)`. Pattern (get_run:248-269, delete_run, get_chain_context:477-504): `db.query(WorkflowRun).filter(WorkflowRun.id == workflow_id, WorkflowRun.user_id == current_user.id).first()`; if `None` → `raise HTTPException(status_code=404, detail="...")`. **Cross-owner resolves to 404, never 403** (documented "IDOR (ASVS V4): resolves to 404, never another user's data", runs.py:14-17). The two new endpoints mirror this — D-08/D-10 lock 404 for cross-owner. The scoped helper's `owner_id` filter replaces the `user_id == current_user.id` filter (for authed users `owner_id == user_id`). `[VERIFIED: runs.py read]`

### 05-SPEC.md existence — CONFIRMED
`05-SPEC.md` exists on disk (read in full), 14 requirements, ambiguity 0.14, matches the CONTEXT summary exactly. No flag needed. `[VERIFIED: file read]`

## Standard Stack

No new external packages. Phase extends the existing stack (CLAUDE.md mandate: "extend, don't replace").

### Core (existing — verified present)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| SQLAlchemy | (installed; sync `create_engine`/`sessionmaker`) | ORM + schema | Existing persistence layer; all models on `Base` |
| Alembic | (installed; head `0013`) | Additive migrations | Existing migration chain; `op.batch_alter_table` for SQLite/Postgres parity |
| FastAPI | (installed) | `/api/runs` router | Existing API layer; `Depends(get_current_user)` + `Depends(get_db)` |
| Python `hashlib` | stdlib | `sha256(content)` for `content_hash` | No dep needed (D-01) |
| Python `uuid` | stdlib | `event_id`, artifact/workspace ids | Matches existing `str(uuid.uuid4())` PK pattern |

**Installation:** none — no `pip install`. All dependencies already present (verified: `create_engine`, `sessionmaker`, `alembic`, `fastapi` all imported in existing code).

## Package Legitimacy Audit

> Not applicable — this phase installs **zero** external packages. All work uses the existing stack (SQLAlchemy/Alembic/FastAPI/stdlib). slopcheck not run (no packages to verify). No `pip install` task should appear in any plan.

## Architecture Patterns

### System Architecture Diagram

```
WS run_pipeline (authed; user.id) ──► WorkflowRun row (session_id=user.id)
        │                                    │
        ▼                                    ▼
  ExecutionEngine.execute(user_id, [+session_id?])
        │
        ├─► ctx.owner_id = user_id or "anon:<session_id>"   (DB principal — D-09)
        ├─► ctx.disk_principal = user_id or "anon"          (UNCHANGED — byte-identity guard)
        ├─► RunSandbox(disk_principal, run_id)              (disk path stays identical)
        ├─► create default workspaces row → ctx.workspace_id (D-04)
        ├─► record run_capabilities(runtime=langchain_deepagents) (D-12)
        ├─► ctx.artifacts = ArtifactGraph()                 (typed substrate — D-09)
        │
        ├─► per agent: produce/consume typed ArtifactRefs ──► ArtifactGraph (in-mem)
        │        │                                              │
        │        └─ dual-write ─► scoped_helper.write_ref ──► artifact_refs (DB)
        │           (+ legacy accumulated_outputs mirror until step 5)
        │
        └─► every yielded event ─► [SEQ SINK: stamp seq + event_id]
                                         ├─► live stream → WS queue
                                         └─► scoped_helper.append_event → run_events (DB)

GET /api/runs/{id}/artifacts ─► scoped_helper.tree(run_id) ─► lineage tree (404 cross-owner)
GET /api/runs/{id}/events?after=k ─► scoped_helper.read_events(run_id, k) ─► seq>k ascending

scoped_helper (agents/authz.py): every read WHERE owner_id=:o AND (workspace_id=:w OR visibility IN ('workspace','public'))
        │
        └─► SessionLocal() (SYNC ORM inside async def)
```

### Recommended Project Structure (per plan §32 / D-02)
```
backend/
├── agents/
│   ├── artifacts/              # NEW — kernel-importable typed data
│   │   ├── __init__.py
│   │   └── graph.py            # ArtifactGraph + ArtifactRef dataclass (§6:454-466 + inline content)
│   ├── authz.py                # NEW (relocated from execution_engine/authz.py) — scoped store helper
│   └── execution_engine/
│       ├── authz.py            # DELETED (moved up — INV-12 move-don't-copy)
│       ├── context.py          # GROWS: + artifacts: ArtifactGraph, + workspace_id, owner_id semantics
│       └── engine.py           # GROWS: owner/workspace/capabilities wiring; seq sink; read-migration; then mirror DELETED
└── app/
    ├── models/
    │   ├── artifact.py          # DELETED (replaced)
    │   ├── artifact_ref.py      # NEW — ArtifactRef table artifact_refs
    │   ├── workspace.py         # NEW — workspaces table
    │   ├── run_event.py         # NEW — run_events table
    │   ├── run_capabilities.py  # NEW — run_capabilities table
    │   ├── workflow.py          # GROWS: workflow_runs + owner_id, workspace_id, source_run_id, plan_id, budget_snapshot_json
    │   ├── workflow_definition.py # GROWS: workflows + owner_id, workspace_id, source, manifest_json, version
    │   └── __init__.py          # GROWS: import the 4 new models (autogenerate/metadata visibility)
    ├── api/runs.py              # GROWS: + GET /{id}/artifacts, + GET /{id}/events
    └── alembic/versions/
        ├── 0014_typed_artifacts_persistence.py   # NEW additive (+ backfill, or 0014b)
        └── 0015_drop_thin_artifact_store.py        # NEW destructive (DROP workflow_artifacts) — LAST
```

### Pattern: Sync ORM inside `async def` (the existing idiom — reuse it)
```python
# Source: agents/artifact_store/store.py:67-106 (existing pattern to mirror in agents/authz.py)
async def write_ref(self, ...) -> str:
    from app.models.database import SessionLocal
    db = SessionLocal()
    try:
        # blocking sync ORM — NO await on db calls
        db.add(row); db.commit()
        return row.id
    finally:
        db.close()
```

### Pattern: IDOR → 404 (the existing runs.py guard — mirror it)
```python
# Source: app/api/runs.py:258-269
row = db.query(WorkflowRun).filter(
    WorkflowRun.id == workflow_id,
    WorkflowRun.user_id == current_user.id,   # scoped helper replaces with owner_id filter
).first()
if not row:
    raise HTTPException(status_code=404, detail="...")   # cross-owner → 404, never 403
```

### Anti-Patterns to Avoid
- **Deriving the sandbox dir from `ctx.owner_id`** — breaks byte-identity for anon runs (D-09 guard). Keep `RunSandbox(user_id or "anon", run_id)`.
- **Introducing `AsyncSession`/`create_async_engine`** — the DB is sync; adding async ORM is a new dependency + engine + Alembic change, out of scope and INV-3-risky.
- **A second/DB-side `seq` counter** (`MAX(seq)+1`, Postgres sequence) — diverges from the live stream (D-11 rejected). Stamp ONE counter at the emit boundary.
- **Creating a second `workflows` table** — name collision with `WorkflowDefinition`; extend the existing one.
- **Treating build-loop scratch keys** (`_build_task_number`/`_build_task_total`) as artifacts during the read-migration.
- **Deleting `_handle_revision`** while migrating its store calls — it is the LIVE `run_revision` PPT handler (ledger D1 voided).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Content hashing | custom digest | `hashlib.sha256(content.encode("utf-8")).hexdigest()` | D-01 locked; deterministic, stdlib |
| Migration FK/batch on SQLite | raw SQL | `op.batch_alter_table` + `op.create_table`/`op.add_column` | 0013 precedent; SQLite needs batch-recreate, Postgres tolerates it |
| DB session lifecycle | manual conn | `SessionLocal()` + try/finally close (or `Depends(get_db)`) | existing idiom; pool_pre_ping handled |
| Cross-owner denial | per-endpoint checks | the ONE scoped-query helper (default-deny filter) | §19 "not scattered in callers"; single enforced read path |
| Event id | sequential int | `str(uuid.uuid4())` | matches existing PK pattern; idempotent replay |
| Lineage tree walk | DB recursive CTE | in-memory walk over loaded ArtifactRefs (`parents`/`derived_from`) | per-run set is small; D-10 tree from roots |

**Key insight:** Everything this phase needs already exists in the stack. The risk is not missing libraries — it's the three CONTEXT-vs-code mismatches (sync DB, no existing seq, workflows collision) and the byte-identity disk-keying guard.

## Runtime State Inventory

> This is a brownfield refactor touching persistence + a string-keyed in-memory handoff. Runtime-state audit applies.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | `workflow_artifacts` table (rows from live runs via thin store); `workflow_runs` rows lack `owner_id`/`workspace_id` | Migration backfill (D-03): default `workspaces` row per existing run + set `owner_id=user_id`, `workspace_id`. `workflow_artifacts` is DROPPED in `0015` — its content is NOT migrated forward (SPEC: thin store deleted; typed graph is per-run from cutover onward; historical artifacts are not required by acceptance — confirm with planner whether any live prod rows must be preserved). |
| Live service config | None — no external service stores the artifact strings. Engine + DB are in-process. | None — verified by grep (no external artifact store; checkpointer is LangGraph graph-state, untouched). |
| OS-registered state | None — no OS-registered tasks reference artifact/owner strings. | None — verified (dev runtime is `python3.11`, no daemons own these strings). |
| Secrets/env vars | None reference `accumulated_outputs`/artifact keys. `DATABASE_URL` unchanged (additive migration). | None. |
| Build artifacts / installed packages | None — no compiled artifact or egg-info embeds these names. | None — pure Python, no package rename. |

**The canonical question — after every file is updated, what runtime systems still have the old string?** Answer: only the **DB** (the `workflow_artifacts` table + un-backfilled `workflow_runs` rows). Both are handled by the `0014` backfill + `0015` drop. No UI/OS/secret/service caches the artifact handoff — it lived purely in-process (`ExecutionContext.accumulated_outputs`) + one DB table.

## Common Pitfalls

### Pitfall 1: L15 flip breaks the migration-ledger test
**What goes wrong:** `test_migration_ledger.py:143-145` asserts `flipped == ["L14", "L16"]` **exactly**. Flipping L15 → ☑ in the ledger fails this hard-coded assertion.
**Why:** the test was authored for Phase 0B's exact flip set.
**How to avoid:** the planner MUST update `test_ledger_parses_and_phase0b_flips_l14_l16` (rename + expect `["L14","L15","L16"]` or generalize) as part of the L15-flip task. Also add the thin-store deletion gate row (D-05) to the ledger + `_REQUIRED_ITEMS`.
**Warning signs:** CI red on `backend:characterization` after editing the ledger.

### Pitfall 2: L15 grep scope mismatch (test vs SPEC)
**What goes wrong:** the ledger L15 gate greps `accumulated_outputs` over **all of `backend/` including tests** (`test_migration_ledger.py:115` runs `grep -rnE pattern backend/ --include=*.py`), but the SPEC acceptance scopes it to `backend/agents backend/app` (non-test). Tests legitimately reference `accumulated_outputs` (e.g. characterization fixtures).
**Why:** the ratchet greps the whole backend; tests may retain the string.
**How to avoid:** ensure no non-test occurrence remains AND scrub/adjust any test references, OR refine the gate pattern. Verify with `grep -rn accumulated_outputs backend/agents backend/app --include=*.py` → 0 before flipping.
**Warning signs:** 42 current references (12 in engine.py, 1 in context.py) — all must reach 0 in non-test before flip.

### Pitfall 3: anon test strings break under D-09
**What goes wrong:** `test_parent_run_ownership.py:48,53,221` assert `owner_id == "anon"` exactly. D-09 changes this to `anon:<session_id>`.
**How to avoid:** update those assertions when D-09 lands; the helper-relocation task (D-07) and the owner-population task (D-09) both touch this suite.

### Pitfall 4: seq stamping perturbs the semantic snapshot
**What goes wrong:** adding `seq`/`event_id` to event `data` changes the `_canonical_order` multiset → 0A semantic snapshot fails.
**How to avoid:** add `seq` + `event_id` to `_VOLATILE_STRIP_KEYS` in `_normalize.py` (they are generated/volatile); rely on `assert_seq_contiguous` for the seq contract. Regenerate goldens only via `SNAPSHOT_UPDATE=1` if a legitimate change occurs.

### Pitfall 5: new models invisible to Alembic
**What goes wrong:** `artifact_ref.py`/`workspace.py`/`run_event.py`/`run_capabilities.py` not imported in `app/models/__init__.py` → not on `Base.metadata` → `alembic check`/autogenerate drift, relationships fail to resolve.
**How to avoid:** import all four in `__init__.py` (documented requirement, `__init__.py:8`). Hand-author the migration regardless.

## State of the Art

| Old Approach | Current Approach | When | Impact |
|--------------|------------------|------|--------|
| `accumulated_outputs: dict[str,str]` in-memory handoff (L15) | typed `ArtifactGraph`/`ArtifactRef` | this phase | string-matched routing → typed produces/consumes |
| DB `ArtifactStore` thin store + `workflow_artifacts` | `artifact_refs` via scoped helper | this phase | one owner-scoped store; thin store deleted |
| by-convention `assert_owns(parent_owner_id)` pure predicate | real store-lookup scoped helper | this phase | default-deny enforced, not by-convention |
| events streamed, no durable log | `run_events` (seq + event_id) | this phase | replay/resume via `?after=<seq>` |
| `owner_id = user_id or "anon"` | `user_id or anon:<session_id>` (DB); disk stays `user_id or "anon"` | this phase | per-session isolation; disk byte-identical |

**Deprecated/outdated after this phase:** `WorkflowArtifact`, `workflow_artifacts`, `ArtifactStore.store/retrieve_*/list_*`, `ExecutionContext.accumulated_outputs`, `engine._derive_parent_owner`, `agents/execution_engine/authz.py`.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `anon:<session_id>` source should be an explicit new `execute()` param OR `pipeline_run_id` (no stable session id threaded today) | #3 / D-09 | Wrong source → anon runs not per-session isolated (AUTHZ-03); planner must pick a source |
| A2 | Historical `workflow_artifacts` rows do NOT need forward-migration into `artifact_refs` (acceptance only requires new runs typed) | Runtime State Inventory | If prod has live artifact rows users still read, dropping loses them — confirm before `0015` |
| A3 | The two new endpoints may be `async def` OR sync `def` (D-08 discretion); recommend injected `Session` | #2 / D-08 | Low — both work in FastAPI |
| A4 | `seq` + `event_id` should be added to `_VOLATILE_STRIP_KEYS` to preserve the multiset snapshot | #4 / Pitfall 4 | If not stripped, 0A semantic parity fails at cutover |
| A5 | `workflows` extend keeps legacy `agents`/`artifact_edges` columns (nullable, populated by legacy path) | #5 | If legacy Phase-3 workflow-definition path is dead, columns are vestigial (harmless) |
| A6 | D-02 controls over SPEC ART-01 on package location (`agents/artifacts/` not `agents/execution_engine/artifacts/`) | user_constraints note | Wrong location → import-linter still green either way, but §32 fidelity differs |

## Open Questions

1. **Anon session-id source (A1).** CONTEXT locks the *format* `anon:<session_id>` but no stable session id is threaded into `execute()` today (run is always authed; `session_id=user.id`). Recommendation: add an explicit `session_id` param to `execute()` (cleanest) or use `anon:<pipeline_run_id>` (lowest-change). Planner's call.
2. **Historical artifact rows (A2).** Does prod hold `workflow_artifacts` rows that users still fetch (e.g. via the revision `_handle_revision` `retrieve_latest`)? If yes, `_handle_revision`'s parent-artifact reads must resolve against the typed graph for *future* runs but old runs predate `artifact_refs`. Recommendation: confirm whether a one-time data backfill of `workflow_artifacts` → `artifact_refs` is needed (CONTEXT does NOT mandate it — schema-only), or whether revision-of-pre-cutover-runs is acceptably best-effort.
3. **`agents/artifacts/` vs `agents/execution_engine/artifacts/` (A6).** D-02 (controlling) says `agents/artifacts/`; SPEC ART-01 target prose says `agents/execution_engine/artifacts/`. Use D-02 (`agents/artifacts/`, matches plan §32). Flagged for the planner to lock.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | all | ✓ | python3.11 (no venv — dev-runtime memory) | — |
| SQLAlchemy (sync) | persistence | ✓ | imported in app/models/database.py | — |
| Alembic | migrations | ✓ | head 0013 | — |
| FastAPI | endpoints | ✓ | app/api/runs.py | — |
| Postgres (prod) / SQLite (dev) | DB | ✓ | DATABASE_URL-driven; SQLite FK PRAGMA on | — |
| slopcheck | (n/a — no packages) | — | — | not needed |

**Missing dependencies with no fallback:** none.
**Test command:** `cd backend && python3.11 -m pytest tests/agents/ tests/unit/ -v` (per backend/CLAUDE.md).

## Validation Architecture

> nyquist_validation ENABLED. This phase's cutover is gated on parity — validation IS the exit gate.

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (+ pytest-asyncio for `async` engine tests; Hypothesis available) |
| Config file | `backend/pyproject.toml` (`[tool.pytest.ini_options]`, testpaths=`tests`) |
| Quick run command | `cd backend && python3.11 -m pytest tests/agents/test_migration_ledger.py tests/agents/test_parent_run_ownership.py -x` |
| Full suite command | `cd backend && python3.11 -m pytest tests/agents/ tests/unit/ -v` |
| Import-linter | `cd backend && lint-imports` (must stay exit 0) |
| Vulture | `cd backend && vulture app/ agents/` (dead-code after deletions) |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| ART-01/03 | build graph, two refs (one derived), typed lineage read; consumes:[X] gets type-X refs | unit | `pytest tests/agents/test_artifact_graph.py -x` | ❌ Wave 0 |
| ART-02 | every write records producer step/agent/task, sha256, version, parents | unit | same file | ❌ Wave 0 |
| ART-04 | retention defaults run_ttl; keep persists | unit | same file | ❌ Wave 0 |
| PERSIST-01 | `alembic upgrade head` from 0013 + `downgrade` reverse; idx present; owner_id+workspace_id on each table | integration | `pytest tests/unit/test_migration_0014.py -x` | ❌ Wave 0 |
| PERSIST-02 | `grep accumulated_outputs backend/agents backend/app`→0; thin-store methods gone; HITL works | ratchet+unit | `pytest tests/agents/test_migration_ledger.py -x` (UPDATE flip set) | ✅ exists (must edit) |
| PERSIST-03 | run_events contiguous per-run seq; unique event_id | unit/integration | `pytest tests/unit/test_run_events.py -x` | ❌ Wave 0 |
| AUTHZ-02/04 | cross-owner parent / artifact / workspace denial | unit | `pytest tests/agents/test_parent_run_ownership.py -x` (extend) + new artifact/workspace cases | ✅ exists (must extend) |
| AUTHZ-03 | anon run persists `anon:<session_id>`; second anon session can't read first | unit | `pytest tests/agents/test_parent_run_ownership.py -x` (update anon strings) | ✅ exists (must edit) |
| CAPRUN-01 | one run_capabilities row, runtime=langchain_deepagents | unit | `pytest tests/unit/test_run_capabilities.py -x` | ❌ Wave 0 |
| API-04 | walkable lineage tree ≥2 linked; cross-owner 404 | api | `pytest tests/unit/test_runs_api_artifacts.py -x` | ❌ Wave 0 |
| API-05 | `?after=k` → seq>k ascending; event_id; cross-owner 404 | api | `pytest tests/unit/test_runs_api_events.py -x` | ❌ Wave 0 |
| BACK-COMPAT (gate) | prototype/od_prototype/prototype_revision/ppt/code-gen byte-identical + semantic-event parity | characterization | `pytest tests/agents/test_characterization_*.py -x` | ✅ exists (5 files) |

### Sampling Rate
- **Per task commit:** the targeted unit file for that task + `lint-imports`.
- **Per wave merge:** `pytest tests/agents/ tests/unit/ -v` + `lint-imports` + `vulture`.
- **Phase gate (before D-13 step 5 deletion):** full `tests/agents/test_characterization_*.py` byte+semantic green (the parity gate that BLOCKS deleting the mirror/thin store), AND `test_migration_ledger.py` green with L15+thin-store gates armed, AND L16 still green.

### Highest-risk behaviors needing sampling/coverage (for planner Dimension 8)
1. **0A characterization parity** (5 pipelines) — the cutover blocker. Highest risk: the `seq`/`event_id` stamping perturbing the multiset (mitigate: strip them in `_normalize`); any read-migration changing deliverable bytes.
2. **Cross-owner denial** (parent + artifact + workspace, AUTHZ-04) — security-critical; default-deny must hold at the store layer, 404 at API.
3. **Migration up/down + backfill** — `alembic downgrade` must cleanly reverse `0014`; backfill must give EVERY existing run a `workspace_id` (uniform scoping).
4. **L16 stays green** — the relocated helper (now a store lookup) must not regress the existing parent-ownership denial.
5. **`seq` contiguity** (SAFE-03, deltas==1) under the new sink across the interleaving build loop.

### Wave 0 Gaps
- [ ] `tests/agents/test_artifact_graph.py` — ART-01/02/03/04 graph unit tests
- [ ] `tests/unit/test_migration_0014.py` — upgrade/downgrade + schema/index assertions (PERSIST-01)
- [ ] `tests/unit/test_run_events.py` — durable log seq/event_id (PERSIST-03)
- [ ] `tests/unit/test_run_capabilities.py` — CAPRUN-01
- [ ] `tests/unit/test_runs_api_artifacts.py` + `tests/unit/test_runs_api_events.py` — API-04/05 incl. cross-owner 404
- [ ] Extend `tests/agents/test_parent_run_ownership.py` — artifact + workspace denial; update anon strings for `anon:<session_id>`
- [ ] Edit `tests/agents/test_migration_ledger.py` — expected flip set + add thin-store deletion gate row
- [ ] Edit `tests/agents/characterization/_normalize.py` — add `seq`/`event_id` to `_VOLATILE_STRIP_KEYS`
- [ ] Framework: pytest-asyncio already in use (async tests present) — no install.

## Security Domain

> `security_enforcement` not disabled in config — included. SPEC constraint: "Security posture unchanged: no exec/network/secrets; defaults OFF."

### Applicable ASVS Categories
| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | partial | Existing JWT `get_current_user`; owner_id derived from authed user (or anon:session) |
| V3 Session Management | yes | `anon:<session_id>` per-session isolation; session id source = decision (#3) |
| V4 Access Control | **yes (core)** | Default-deny scoped-query helper; IDOR → 404 (runs.py pattern); cross-owner denial tests (AUTHZ-04) |
| V5 Input Validation | yes | `?after=<seq>` int-coerce; `{id}` path is filtered, not interpolated into SQL (ORM) |
| V6 Cryptography | n/a-ish | `sha256` for content-addressing (NOT a security control — dedup/integrity, no secrets) |

### Known Threat Patterns for this stack
| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| IDOR — read another owner's run/artifact/workspace | Information Disclosure / Elevation | Scoped-query helper default-deny filter; 404 not 403 (no existence leak) — runs.py:14-17 precedent |
| Cross-owner parent seeding (L16) | Elevation | `assert_owns` real store lookup; raises PermissionError above seed try (D-07) |
| Anon principal = None bypasses scope | Spoofing | `owner_id` never None; `anon:<session_id>` is a real principal subject to the check |
| SQL injection via `{id}`/`after` | Tampering | SQLAlchemy ORM `.filter()` parameterized; no string SQL |
| Event-log replay tampering | Tampering | `event_id` idempotent; seq monotonic; read-only endpoint, owner-scoped |

## Sources

### Primary (HIGH confidence — code read this session)
- `backend/pyproject.toml` (import-linter contracts, vulture config) — lines 131-218
- `backend/app/models/database.py` — sync engine/sessionmaker (#2)
- `backend/agents/artifact_store/store.py` — thin store, sync-in-async idiom, HITL half
- `backend/agents/execution_engine/authz.py` — pure assert_owns to relocate
- `backend/agents/execution_engine/engine.py` — execute() entry (475-557), L16 seed block (640-694), 27 yield sites, accumulated_outputs sites, _handle_revision store calls, _derive_parent_owner (2694)
- `backend/agents/execution_engine/context.py` — ExecutionContext fields
- `backend/app/models/artifact.py` / `workflow.py` / `workflow_definition.py` (#5 collision) / `__init__.py`
- `backend/app/api/runs.py` — IDOR/404 sync-def pattern
- `backend/app/api/websocket.py` — run creation (1032-1069), session_id=user.id (1062), execute() call (1110), clarifications read (543)
- `backend/alembic/versions/0013_collapse_pipeline_run_id.py` + `backend/alembic/env.py` — revision pattern, batch idiom, metadata autogenerate
- `backend/tests/agents/characterization/_normalize.py` — seq vacuous-today (189), strip/required keys (#4)
- `backend/tests/agents/test_migration_ledger.py` — flip-set assertion (143-145), grep ratchet (115)
- `backend/tests/agents/test_parent_run_ownership.py` — anon strings, denial tests
- `specs/003-workflow-engine-decoupling/plan.md` §6/§11/§17-§19/§21/§22/§31 + `migration-ledger.md` — L15/L16 rows, CHECK-row convention
- `05-SPEC.md` + `05-CONTEXT.md` — locked requirements + decisions

### Secondary / Tertiary
- None — all findings verified against repo code; no WebSearch needed (no external packages, brownfield).

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new packages; existing stack verified by import.
- Architecture/import-linter: HIGH — exact contracts quoted; engine.py→app.api boundary verified.
- DB session flavor (#2): HIGH — corrects CONTEXT premise; grep-confirmed no AsyncSession.
- seq chokepoint (#4): HIGH — corrects CONTEXT premise; _normalize.py + 27 yield sites confirm no existing seq.
- workflows collision (#5): HIGH — existing `__tablename__="workflows"` confirmed.
- Anon source (#3): MEDIUM — format locked, source needs a planner decision (A1/OQ1).
- Pitfalls/Validation: HIGH — derived from actual test-file assertions.

**Research date:** 2026-06-07
**Valid until:** 2026-07-07 (stable brownfield; re-confirm if engine.py line anchors shift after a Phase-4 follow-up commit)
