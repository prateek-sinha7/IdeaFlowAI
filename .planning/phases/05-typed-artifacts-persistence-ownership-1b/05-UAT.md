---
status: complete
phase: 05-typed-artifacts-persistence-ownership-1b
source: [05-01-SUMMARY.md, 05-02-SUMMARY.md, 05-03-SUMMARY.md, 05-04-SUMMARY.md, 05-05-SUMMARY.md, 05-06-SUMMARY.md, 05-07-SUMMARY.md]
mode: standard (non-mvp — backend infra phase, no user-facing flow; Mode:mvp tag removed from ROADMAP 2026-06-08)
started: 2026-06-08T12:48:10Z
updated: 2026-06-08T12:48:10Z
accepted_by: user
---

## Current Test

[testing complete]

## Tests

<!-- All checks were EXECUTED by Claude on current HEAD (post CR-01/IN-01/IN-02
     review fixes), not copied from the 2026-06-08 VERIFICATION.md. Evidence is the
     real command output captured this session. -->

### 1. Cold Start Smoke Test
expected: On a fresh DB, `alembic upgrade head` applies the entire 0001→0015 chain with no errors; the 4 Phase-5 tables (artifact_refs, workspaces, run_events, run_capabilities) exist; the legacy workflow_artifacts table is dropped; the app imports/boots (runs router + ScopedStore + 4 models import clean).
result: pass
evidence: "Fresh sqlite upgrade head ran 0001→0015 clean (0010 creates workflow_artifacts, 0015 drops it); 4 tables PRESENT; workflow_artifacts absent; alembic head=0015; `from app.api.runs import router`, `from agents.authz import ScopedStore`, `import app.models` all import clean."

### 2. Migration 0014 — additive schema + ownership + backfill
expected: 0014 (down_revision 0013) creates artifact_refs/workspaces/run_events/run_capabilities, each with owner_id + workspace_id NOT NULL + required indexes; extends workflow_runs + workflows additively; backfills every existing run with a workspace row + owner scope; downgrade reverses cleanly.
result: pass
evidence: "test_migration_0014.py 2 passed (up-from-0013 + downgrade + index/scope/backfill asserts); revision=0014/down_revision=0013 confirmed."

### 3. Migration 0015 — reversible drop of workflow_artifacts
expected: 0015 (down_revision 0014) drops workflow_artifacts; downgrade recreates the table + index; re-upgrade re-drops (full reversible roundtrip, Q3).
result: pass
evidence: "Live roundtrip on the cold-start DB: downgrade head→0013 recreated workflow_artifacts + removed the 4 new tables (head→0013); re-upgrade 0013→head re-dropped workflow_artifacts + restored the 4 tables (head→0015). test_migration_ledger.py 0015 roundtrip green."

### 4. Typed ArtifactGraph substrate
expected: ArtifactRef is sha256 content-addressed; per-(run,kind) versioning; typed consumes routing by kind equality (never substring); cycle-safe in-memory lineage/tree walk; kernel-pure (stdlib only, no app.* imports).
result: pass
evidence: "test_artifact_graph.py 7 passed (ART-01..04); lint-imports kernel-purity contract KEPT (graph.py imports stdlib only)."

### 5. Default-deny ownership (ScopedStore) + cross-owner denial + anon isolation + fail-loud guards
expected: every read filters owner_id + workspace/visibility; cross-owner artifact/workspace/parent reads are denied; anon:<session_id> (never None) isolates one anon session from another; falsy-owner rejected loudly — IN-01: `_handle_revision` raises ValueError on falsy owner_id (engine.py:2669); IN-02: `set_run_scope` rejects cross-owner re-scope with PermissionError (authz.py:399).
result: pass
evidence: "test_parent_run_ownership.py 13 passed (artifact + workspace + parent denial, anon:sess-A vs anon:sess-B isolation); test_revision_intelligence.py 10 passed incl. cross-owner PermissionError; IN-01 guard read at engine.py:2669-2672; IN-02 ValueError(376) + PermissionError(399) guards read in authz.py:set_run_scope."

### 6. GET /api/runs/{id}/artifacts — lineage tree + content opt-in + IDOR→404
expected: returns the run's ArtifactRef rows assembled into a nested lineage tree; inline content excluded by default, opt-in via ?include=content; cross-owner and missing runs return 404 (never 403).
result: pass
evidence: "test_runs_api_artifacts.py 5 passed (≥2-node walkable tree, content default-excluded vs ?include=content, empty-run, cross-owner 404, missing 404); route registered (artifacts route: True)."

### 7. GET /api/runs/{id}/events?after=<seq> — durable replay + idempotence + 422 + IDOR→404
expected: returns only run_events with seq>after, ascending, each carrying a unique event_id; idempotent re-replay; non-int `after` → 422; cross-owner and missing → 404. CR-01: a revision run created before its workspace is known is scope-stamped (set_run_scope writeback) so /events resolves on a real DB instead of spuriously 404-ing.
result: pass
evidence: "test_runs_api_events.py 7 passed (after=k → only seq>k ascending w/ event_id, full + idempotent replay, non-int→422, cross-owner 404, missing 404); route registered (events route: True); CR-01 writeback in authz.set_run_scope (authz.py:351) + commit 2d72081."

### 8. run_capabilities records runtime=langchain_deepagents (CAPRUN-01)
expected: exactly one run_capabilities row per run, runtime == "langchain_deepagents", owner_id/workspace_id stamped, forward (Phase 6/8/9) columns present + nullable.
result: pass
evidence: "test_run_capabilities.py 2 passed (one row, runtime=langchain_deepagents, deferred cols present/nullable, owner/workspace stamped)."

### 9. Legacy mirror + thin store deleted — single implementation (INV-3 / INV-12)
expected: accumulated_outputs mirror removed (grep 0 non-test); thin-store artifact methods (store/retrieve_latest/retrieve_version/list_by_type/list_lineage) gone; WorkflowArtifact model deleted (`from app.models.artifact import` → 0); HITL asyncio.Event half KEPT; migration ledger L15 ☑ + D2 ☑.
result: pass
evidence: "grep accumulated_outputs (agents/app non-test)=0; `from app.models.artifact import` (whole backend)=0; thin-store artifact methods in store.py=0; HITL half present=6 matches; app/models/artifact.py absent; test_migration_ledger.py 6 passed (flip-set {D2,L14,L15,L16})."

### 10. INV-3 back-compat — characterization parity (5 pipelines)
expected: prototype / prototype_revision / od_prototype / od_ppt / app_builder produce byte-identical deliverables + semantic-event parity (newly-introduced volatile seq/event_id stripped from the snapshot multiset).
result: pass
evidence: "10 characterization tests passed (all 5 pipelines × byte + event snapshot)."

## Summary

total: 10
passed: 10
issues: 0
pending: 0
skipped: 0
blocked: 0

cross-cutting: "lint-imports 3 kept / 0 broken; focused phase-5 suites 59 passed / 1 skipped; characterization 10 passed."
out-of-scope-notes: "Full sweep carries 8 pre-existing environmental failures unrelated to Phase 5 (test_logout.py ×7 — self-registration disabled→403; test_pipeline_cancel.py ×1 — expired AWS Bedrock token), documented in deferred-items.md. A live uvicorn HTTP round-trip was not run; the endpoint handler→ScopedStore→DB path is covered by the FastAPI TestClient endpoint suites (tests 6/7) against a real DB session."

## Gaps

[none]
