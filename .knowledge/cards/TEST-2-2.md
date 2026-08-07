---
id: TEST-2-2
type: test
status: done
area: [sse, workflow, agents, auth, artifacts]
summary: >-
  2.2 Typed artifacts, persistence & ownership (register part 05)
source: .planning/TEST-REGISTER.md#2-2-typed-artifacts-persistence-ownership-regist
covers: [BE-ART-01, BE-ART-02, BE-PERS-01, BE-AUTHZ-01, BE-AUTHZ-02, BE-PERS-02, BE-API-04, BE-SEC]
---

### 2.2 Typed artifacts, persistence & ownership  (register part 05)

| ID | Guarantee | Verify | Status |
|---|---|---|---|
| BE-ART-01 | Typed sha256-content-addressed `ArtifactGraph`/`ArtifactRef`; typed `consumes` routing; lineage walk | `pytest tests/agents/test_artifact_graph.py` (7) | 🟢 |
| BE-ART-02 | **`accumulated_outputs` mirror DELETED (INV-12);** `ctx.artifacts` sole prior-output source | `pytest tests/agents/test_migration_ledger.py`; `grep -rn accumulated_outputs backend --include=*.py \| grep -v test` → 0 | 🟢 CI-gated |
| BE-PERS-01 | Migration `0014` additive + reversible; cold `0001→0020` chain; **single head `0020`** | `pytest tests/unit/test_migration_0014.py`; `alembic upgrade head` | 🟢 |
| BE-AUTHZ-01 | **Every new table carries `owner_id` + `workspace_id` NOT NULL** (11 tables: artifact_refs, workspaces, run_events, run_capabilities, validation_results, gate_events, hook_runs, repositories, exec_runs, subagent_runs, wave_runs) | `grep -nE 'create_table\|owner_id\|workspace_id' alembic/versions/00{14,16,17,18,19,20}_*.py` — both NOT NULL on every table | 🟢 (confirmed all 11) |
| BE-AUTHZ-02 | Default-deny `ScopedStore` is the single read/write path; cross-owner read denied; `assert_owns` raises `PermissionError` (never swallowed) | `pytest tests/agents/test_parent_run_ownership.py` (13) | 🟢 |
| BE-PERS-02 | Durable `run_events` with **contiguous `seq`** (deltas==1) + unique `event_id`; both stripped from parity multiset | `pytest tests/unit/test_run_events.py` (6); `assert_seq_contiguous` | 🟢 char-locked |
| BE-API-04/05 | `GET /api/runs/{id}/artifacts` (owner-scoped lineage tree, content opt-in); `GET /api/runs/{id}/events?after=<seq>` (seq>after asc, non-int → 422) | `pytest tests/unit/test_runs_api_artifacts.py test_runs_api_events.py` (5+7) | 🟢 |
| BE-SEC | 19/19 threats closed (ASVS L1); revision-run `run_events` NOT NULL on real DB (round-2 CR-01) | `pytest tests/.../test_revision_run_events_persist_and_resolve_on_real_db` | 🟢 |
