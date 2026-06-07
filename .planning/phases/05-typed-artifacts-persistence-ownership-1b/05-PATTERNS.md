# Phase 5: Typed Artifacts + Persistence + Ownership [1B] - Pattern Map

**Mapped:** 2026-06-07
**Files analyzed:** 19 (6 net-new, 6 grow, 4 rewired→deleted, 3 test edits)
**Analogs found:** 19 / 19 (every file has a real in-repo analog — brownfield refactor)

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `agents/artifacts/graph.py` (NEW) | model (typed data) | transform / in-mem routing | `agents/execution_engine/context.py` (stdlib-only dataclass) + `app/models/artifact.py` (field shape) | role-match (dataclass) |
| `app/models/artifact_ref.py` (NEW) | model (ORM) | CRUD | `app/models/artifact.py` `WorkflowArtifact` (replaces it) | exact |
| `app/models/workspace.py` (NEW) | model (ORM) | CRUD | `app/models/workflow_definition.py` (small owned table) | role-match |
| `app/models/run_event.py` (NEW) | model (ORM) | event-driven / append | `app/models/artifact.py` (run-scoped immutable rows + `(run_id, X)` index) | role-match |
| `app/models/run_capabilities.py` (NEW) | model (ORM) | CRUD (one row/run) | `app/models/workflow.py` (run-scoped) | role-match |
| `alembic/versions/0014_typed_artifacts_persistence.py` (NEW) | migration | batch / schema | `alembic/versions/0013_collapse_pipeline_run_id.py` | exact |
| `alembic/versions/0015_drop_thin_artifact_store.py` (NEW) | migration | destructive DROP | `0013` downgrade (`drop_*`) | role-match |
| `app/api/runs.py` `GET /{id}/artifacts` (GROWS) | route | request-response | `runs.py::get_run` (IDOR→404) | exact |
| `app/api/runs.py` `GET /{id}/events?after=` (GROWS) | route | request-response / replay | `runs.py::get_run` (IDOR→404) | exact |
| `agents/authz.py` (GROWS — relocated) | service (store helper) | CRUD + access-control | `agents/execution_engine/authz.py` (predicate) + `agents/artifact_store/store.py` (sync-in-async session) | exact (2 seams) |
| `agents/execution_engine/context.py` (GROWS) | model (dataclass) | — | itself (additive fields) | exact |
| `app/models/workflow.py` (GROWS) | model (ORM) | CRUD | itself (`workflow_runs` extend) | exact |
| `app/models/workflow_definition.py` (GROWS) | model (ORM) | CRUD | itself (`workflows` EXTEND — collision) | exact |
| `agents/execution_engine/engine.py` (REWIRE→DELETE mirror) | controller (sequencer) | event-driven | itself + the new helper/graph | n/a (rewire) |
| `agents/artifact_store/store.py` (DELETE persistence half) | service | CRUD | itself (split seam) | n/a (delete) |
| `app/api/websocket.py:543` (REWIRE clarifications read) | route | request-response | the typed store helper | n/a (rewire) |
| `tests/agents/test_migration_ledger.py` (EDIT) | test | — | itself | exact |
| `tests/agents/test_parent_run_ownership.py` (EXTEND) | test | — | itself | exact |
| `tests/agents/characterization/_normalize.py` (EDIT) | test | — | itself (`_VOLATILE_STRIP_KEYS`) | exact |

---

## Pattern Assignments

### `app/models/artifact_ref.py` (ORM, CRUD) — REPLACES `app/models/artifact.py`

**Analog:** `app/models/artifact.py` `WorkflowArtifact` — the EXACT precedent. New table `artifact_refs` extends this shape (+`owner_id`/`workspace_id`/`content_hash`/`location`/`parents`/`visibility`/`retention`). Keep INLINE `content: Text` (D-01). PK + `created_at` lambda + run-scoped `Index` are all reusable verbatim.

**Full analog to copy from** (`app/models/artifact.py:1-37`):
```python
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import relationship
from app.models.database import Base

class WorkflowArtifact(Base):
    __tablename__ = "workflow_artifacts"
    __table_args__ = (Index("ix_workflow_artifacts_run_type", "workflow_run_id", "type"),)
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    workflow_run_id = Column(String, ForeignKey("workflow_runs.id"), nullable=False)
    type = Column(String, nullable=False)
    name = Column(String, nullable=False)
    content = Column(Text, nullable=False)                   # ← KEEP inline (D-01)
    version = Column(Integer, nullable=False)
    schema_version = Column(String, nullable=False, default="1.0", server_default="1.0")
    producing_agent_id = Column(String, nullable=False)
    derived_from_artifact_id = Column(String, ForeignKey("workflow_artifacts.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    workflow_run = relationship("WorkflowRun", back_populates="artifacts")
    derived_from = relationship("WorkflowArtifact", remote_side=[id])
```

**Delta for `ArtifactRef`** (per D-01/D-02, §6:454-466, AUTHZ-01): rename `type`→`kind`; add `owner_id`/`workspace_id` (NOT NULL), `content_hash` (`sha256(content.encode("utf-8")).hexdigest()`), `location`, `parents`/`derived_from`, `visibility` (default `"workspace"`), `retention` (default `"run_ttl"`); indexes `(run_id, kind)` + `(content_hash)`. **MUST be imported in `app/models/__init__.py`** (else invisible to Alembic — Pitfall 5). The relationship on `WorkflowRun.artifacts` (`workflow.py:52`) must be repointed/dropped when `WorkflowArtifact` is deleted.

---

### `agents/artifacts/graph.py` (typed data) — `ArtifactGraph` + `ArtifactRef` dataclass

**Analog:** `agents/execution_engine/context.py` — the stdlib-only `@dataclass` pattern + the import-direction discipline this module MUST also follow.

**Imports pattern to copy** (`context.py:27-30` — stdlib only, NO `app.models.*`, NO `app.api.*`):
```python
from __future__ import annotations
from dataclasses import dataclass, field
```
Import-linter: `agents/artifacts/` is kernel-importable (RESEARCH #1, no contract violation). The dataclass↔ORM mapping lives in the store helper (D-02), NOT here — keep this file pure typed data so `ExecutionContext` can import it without dragging in `app.models`.

**Field-set source:** plan §6:454-466 + the inline `content` addition (D-01) + the `WorkflowArtifact` column shape above (producer agent/version/derived_from). Lineage walk (`tree`/`parents`) is in-memory (Don't Hand-Roll: no recursive CTE — per-run set is small).

---

### `agents/authz.py` (store helper, CRUD + access-control) — RELOCATED + GROWN

**Analog A — the predicate to RELOCATE** (`agents/execution_engine/authz.py:35-50`, INV-12 move-don't-copy, D-06/D-07):
```python
def assert_owns(owner_id: str, parent_run_id: str, parent_owner_id: str) -> None:
    if parent_owner_id != owner_id:
        raise PermissionError(
            f"owner {owner_id!r} may not seed from parent run {parent_run_id!r} "
            f"(owned by {parent_owner_id!r})"
        )
```
D-07 change: drop the `parent_owner_id` by-convention arg — **look it up from the store** (`get_run(parent_run_id).owner_id`) and raise on mismatch. The old `agents/execution_engine/authz.py` is then DELETED (move, not copy).

**Analog B — the sync-ORM-inside-`async def` session idiom to reuse** (`agents/artifact_store/store.py:66-106`; RESEARCH #2 corrected CONTEXT — the DB is **sync**, no `AsyncSession`):
```python
async def store(self, ...) -> str:
    from app.models.database import SessionLocal
    db = SessionLocal()
    try:
        existing_count = (db.query(func.count(WorkflowArtifact.id))
            .filter(WorkflowArtifact.workflow_run_id == run_id,
                    WorkflowArtifact.type == artifact_type).scalar()) or 0
        version = existing_count + 1
        artifact = WorkflowArtifact(...)
        db.add(artifact); db.commit()
        return artifact_id
    finally:
        db.close()
```
**Apply to every helper method** (`write_ref`, `get_ref`, `list_refs`, `lineage/tree`, `append_event`, `read_events`, `get_run`, `create_workspace`, `record_capabilities`). Default-deny filter on every read (D-06):
```python
.filter(Model.owner_id == self._owner_id,
        ((Model.workspace_id == self._workspace_id) | (Model.visibility.in_(("workspace","public")))))
```
The helper imports `app.models.*` only — NEVER `app.api.*` (keeps `engine → authz → app.api` chain from forming; RESEARCH #1). RESEARCH recommends an **injected `Session`** so endpoints pass `Depends(get_db)` and the engine passes `SessionLocal()` (one acquisition path).

---

### `app/api/runs.py` — `GET /{id}/artifacts` + `GET /{id}/events?after=<seq>` (GROWS)

**Analog — the IDOR→404 guard to mirror** (`runs.py::get_run`, lines 248-269; RESEARCH confirmed cross-owner → 404 never 403, doc'd at `runs.py:14-17`):
```python
@router.get("/{workflow_id}", response_model=WorkflowRunResponse)
def get_run(workflow_id: str,
            current_user: User = Depends(get_current_user),
            db: Session = Depends(get_db)):
    workflow_run = (db.query(WorkflowRun)
        .filter(WorkflowRun.id == workflow_id, WorkflowRun.user_id == current_user.id)
        .first())
    if not workflow_run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow run not found")
    return workflow_run
```
**Deltas:** D-08 — new endpoints are `async def` (existing handlers stay sync `def` — mixing is fine in FastAPI). The scoped helper's `owner_id` filter replaces `WorkflowRun.user_id == current_user.id` (for authed users `owner_id == user_id`). `/artifacts` returns the nested lineage tree (D-10; `content` excluded by default, `?include=content` is planner's call). `/events` returns rows `seq > after` ascending each with `event_id` (D-11/API-05); int-coerce `after` (ASVS V5). Router already reserves these routes (`runs.py:7`). Existing imports at `runs.py:27-34` (`APIRouter, Depends, HTTPException, status`, `Session`, `get_current_user`, `get_db`) are the import precedent.

---

### `alembic/versions/0014_typed_artifacts_persistence.py` + `0015_drop_thin_artifact_store.py` (NEW)

**Analog — the revision header + batch idiom** (`0013_collapse_pipeline_run_id.py:17-51`):
```python
from alembic import op
import sqlalchemy as sa
revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.drop_index("ix_workflow_runs_pipeline_run_id", table_name="workflow_runs")
    with op.batch_alter_table("workflow_runs") as batch_op:
        batch_op.drop_column("pipeline_run_id")
        batch_op.create_foreign_key("fk_...", "workflow_runs", ["parent_run_id"], ["id"])

def downgrade() -> None:
    with op.batch_alter_table("workflow_runs") as batch_op:
        batch_op.drop_constraint("fk_...", type_="foreignkey")
        batch_op.add_column(sa.Column("pipeline_run_id", sa.String(), nullable=True))
```
**Deltas (D-03):** `0014`: `revision="0014"`, `down_revision="0013"`. Use `op.create_table` (new tables — additive, no batch) + `op.add_column` (within `batch_alter_table("workflow_runs")` and `"workflows"` for the column extends — batch is **mandatory** for SQLite/Postgres parity). Indexes: `artifact_refs (run_id, kind)` + `(content_hash)`; `run_events (run_id, seq)`. New columns nullable/defaulted so `upgrade head` applies over existing rows; `downgrade` reverses. **Default-workspace backfill** (data step in `0014` or tiny `0014b` — planner's discretion): one `workspaces` row per existing run + set `workflow_runs.owner_id = user_id`, `workspace_id`. `0015`: `revision="0015"`, `down_revision="0014"`, `op.drop_table("workflow_artifacts")` (works both DBs) — **sequenced LAST after read-cutover + parity green**. Hand-author both; autogenerate only to cross-check (RESEARCH Alembic notes).

---

### `app/models/workflow_definition.py` (GROWS — EXTEND, collision) — RESEARCH #5

**Analog = the file itself** (`workflow_definition.py:12-40`) — it ALREADY owns `__tablename__ = "workflows"`. Do NOT create a second `workflows` table (SQLAlchemy raises on duplicate `__tablename__`; Postgres rejects the name). **Additively add** `owner_id`, `workspace_id` (satisfy AUTHZ-01), `source` (default `"file"`), `manifest_json` (nullable — file-backed this phase), `version` (default 1). Keep legacy `agents`/`artifact_edges`/`constitution_ref`/`user_id` (nullable-safe). PK/`created_at`/`updated_at` lambda pattern stays.

### `app/models/workflow.py` (GROWS — `workflow_runs` extend)

**Analog = the file itself** (`workflow.py:12-53`). Add `owner_id`, `workspace_id`, `source_run_id`, `plan_id`, `budget_snapshot_json` (nullable/defaulted — `budget`/`plan` populated in P11/P4). Existing `user_id` FK + `session_id` (`= user_id`, line 43) + `parent_run_id` (line 42) are the columns the owner/anon logic and L16 lookup ride on. The `artifacts` relationship (line 52, → `WorkflowArtifact`) must be repointed to `ArtifactRef` or dropped when the old model is deleted.

### `agents/execution_engine/context.py` (GROWS) — D-09

**Analog = the file itself.** Add `artifacts: ArtifactGraph` (`field(default_factory=ArtifactGraph)`) + `workspace_id: str`. Upgrade `owner_id` semantics (line 44: currently `user_id or "anon"`) — DB principal becomes `user_id or f"anon:{session_id}"`. **CRITICAL (RESEARCH #3):** the dataclass docstring (lines 22-25) currently mandates stdlib-only imports; adding `from agents.artifacts.graph import ArtifactGraph` keeps it inside `agents.*` (SAFE — no `app.api` reach). Introduce a SEPARATE disk-keying principal (e.g. `disk_principal = user_id or "anon"`) so `RunSandbox(...)` keys stay byte-identical — do NOT derive the sandbox dir from the new `owner_id`.

---

## REWIRED → DELETED files (show the seam)

### `agents/artifact_store/store.py` — DELETE persistence half, KEEP HITL half

**Seam (RESEARCH thin-store consumer map):**
- **DELETE:** `store` (66-127), `retrieve_latest` (129-164), `retrieve_version` (165-188), `list_by_type` (190-220), `list_lineage` (222-248), `_store_in_memory` (264-295), `_to_dict` (359-373), and the `_use_db`/`_mem_*` fields. Callers to rewire to the typed graph: `engine.py:1182/1505/2377` (writes), `engine.py:2320/2328/2331` (reads in `_handle_revision` — migrate reads, do NOT delete `_handle_revision`, it is LIVE), `clarify_engine.py:396` (clarifications write), `websocket.py:543` (clarifications read).
- **KEEP (Phase 8 owns HITL):** `__init__` event registries (255-262), `get_resume_event` (300-307), `set_questionnaire_responses` (309-321), `get_questionnaire_responses` (323-328), `get_review_event` (334-339), `set_review_response` (341-347), `get_review_response` (349-353), `get_artifact_store` singleton (380-391). Consumers that must keep working: `clarify_engine.py:109,127`, `engine.py:2093,2125,2198`, `websocket.py:664` (`submit_questionnaire`), `websocket.py:682` (`approve_review`).

### `agents/execution_engine/engine.py` — mirror rewire + seq sink

`accumulated_outputs` 12 sites (writes 1500/1571/1599/1686-1687/1721/1756; reads 1308/1331/1358/1637/1664/1783-1784/2426/2472-2473/2554/2639-2640/2661) → typed graph; **NOTE** `_build_task_number`/`_build_task_total` scratch keys (1358/1686/2554/2639) are NOT artifacts — move to a non-artifact home. L16 seed block (~640-694) rewires to the relocated helper. **Seq sink (D-11, RESEARCH #4 — NO existing seq):** introduce ONE monotonic counter at the single `execute()` async-generator emit boundary (`execute()` at engine.py:489; all 27 `yield` sites bubble through it) — stamp `data["seq"] = next(counter)` + `data["event_id"] = uuid4()`, then `append_event(...)` to `run_events`. Do NOT tap `ndjson_adapter.py` (not the chokepoint) and do NOT use a DB-side `MAX(seq)+1`.

---

## Shared Patterns

### Default-deny ownership (the ONE scoped read path)
**Source:** `agents/execution_engine/authz.py` (predicate) → grown in `agents/authz.py`.
**Apply to:** every artifact/event/run/workspace read (engine + both endpoints + `websocket.py:543`).
Filter: `WHERE owner_id = :owner AND (workspace_id = :ws OR visibility IN ('workspace','public'))`. Cross-owner → 404 at API (never 403 — `runs.py:14-17`).

### Sync ORM inside `async def`
**Source:** `agents/artifact_store/store.py:66-106`.
**Apply to:** all `agents/authz.py` helper methods. `SessionLocal()` in try/`db.close()` finally; NO `AsyncSession`.

### ORM model conventions
**Source:** `app/models/artifact.py` + `workflow.py`.
**Apply to:** all new models. `id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))`; `created_at` with `datetime.now(timezone.utc)` lambda; run-scoped `Index`; **register in `app/models/__init__.py`** (Pitfall 5).

### Migration revision chaining + SQLite batch
**Source:** `alembic/versions/0013_collapse_pipeline_run_id.py`.
**Apply to:** `0014`/`0015`. Module-level `revision`/`down_revision`/`branch_labels`/`depends_on`; `op.batch_alter_table` for column changes; `op.create_table`/`op.add_column` additive (no batch); hand-author.

### Content hashing / event ids
**Source:** stdlib (Don't Hand-Roll). `hashlib.sha256(content.encode("utf-8")).hexdigest()` (D-01); `str(uuid.uuid4())` for `event_id` (matches PK pattern).

---

## Test files to edit (exact assertions)

### `tests/agents/test_migration_ledger.py` — the L15-flip break (Pitfall 1)
**Hard-coded assertion that WILL break** (`test_migration_ledger.py:143-145`):
```python
flipped = sorted(item for item, _g, status in rows if "☑" in status)
assert flipped == ["L14", "L16"], (
    f"Phase 0B expects exactly {{L14, L16}} flipped to ☑, found: {flipped}")
```
**Edit:** rename `test_ledger_parses_and_phase0b_flips_l14_l16` and expect `["L14","L15","L16"]` (or generalize). Add the thin-store deletion gate row to the ledger + `_REQUIRED_ITEMS`. The grep ratchet runs `grep -rnE pattern backend/ --include=*.py` over ALL of `backend/` incl. tests (line 115) — scrub non-test `accumulated_outputs` to 0 first (`grep -rn accumulated_outputs backend/agents backend/app` → 0; Pitfall 2). L16 stays a CHECK row (skipped by `_checked_grep_rows`).

### `tests/agents/test_parent_run_ownership.py` — anon strings + denial extend (Pitfall 3)
**Assertions that break under D-09** (lines 47-53 — `"anon"` becomes `anon:<session_id>`):
```python
def test_assert_owns_anon_is_a_real_owner_denied() -> None:
    with pytest.raises(PermissionError):
        assert_owns("anon", "run-123", parent_owner_id="bob")
def test_assert_owns_anon_same_session_allowed() -> None:
    assert assert_owns("anon", "run-123", parent_owner_id="anon") is None
```
**Edit:** update anon strings for `anon:<session_id>`; the `assert_owns` signature changes (D-07 store lookup) so these unit cases adapt to the new method shape; the E2E denial tests (lines 56+) stay green via the store lookup. AUTHZ-04 adds new cross-owner **artifact** + **workspace** denial cases (same pattern: second principal can't read first's rows → `PermissionError`/404).

### `tests/agents/characterization/_normalize.py` — strip `seq`/`event_id` (Pitfall 4)
**Set to extend** (`_normalize.py:101-112`):
```python
_VOLATILE_STRIP_KEYS = frozenset({
    "timestamp", "pipeline_run_id", "run_id", "total_duration",
    "estimated_cost_usd", "model_id", "context_message", "context_sources",
})
```
**Edit:** add `"seq"` and `"event_id"` (generated/volatile) so the canonical-JSON multiset snapshot is unperturbed; rely on `assert_seq_contiguous` (already wired) for the deltas==1 seq contract. SAFE-03 is on deltas not absolute values, so a fresh counter passes.

---

## No Analog Found

None. Every file maps to a real in-repo analog (brownfield refactor).

| File | Note |
|------|------|
| (none) | All 19 files have a concrete analog above. |

## Metadata

**Analog search scope:** `backend/agents/`, `backend/app/models/`, `backend/app/api/`, `backend/alembic/versions/`, `backend/tests/agents/`.
**Files scanned (read in full or targeted):** `app/models/artifact.py`, `app/models/workflow.py`, `app/models/workflow_definition.py`, `agents/execution_engine/authz.py`, `agents/execution_engine/context.py`, `agents/artifact_store/store.py`, `app/api/runs.py`, `alembic/versions/0013_collapse_pipeline_run_id.py`, `tests/agents/test_migration_ledger.py`, `tests/agents/test_parent_run_ownership.py`, `tests/agents/characterization/_normalize.py`.
**Pattern extraction date:** 2026-06-07
**RESEARCH.md corrections honored:** sync DB (#2), no existing `seq` (#4), `workflows` table collision/EXTEND (#5), byte-identity disk-keying guard (#3).

## PATTERN MAPPING COMPLETE
