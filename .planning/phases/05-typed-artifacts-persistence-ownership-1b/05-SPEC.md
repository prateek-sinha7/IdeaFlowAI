# Phase 5: Typed Artifacts + Persistence + Ownership [1B] — Specification

**Created:** 2026-06-07
**Ambiguity score:** 0.14 (gate: ≤ 0.20)
**Requirements:** 14 locked

## Goal

The untyped per-run `accumulated_outputs: dict[str,str]` handoff **and** the legacy DB `ArtifactStore` (thin store) are replaced by one typed, content-addressed, owner-scoped `ArtifactGraph` / `ArtifactRef`, persisted via additive §18 migrations with default-deny ownership — and both the in-memory mirror (L15) and the thin store are **deleted this phase** at byte-identical deliverable + semantic-event parity.

## Background

Grounded in the codebase as of this phase (branch `feature/003-workflow-engine-decoupling`, after Phase 4):

- **Two artifact mechanisms exist today.** (1) `accumulated_outputs: dict[str,str]` — the in-memory per-run handoff threaded through `agents/execution_engine/engine.py` (`execute` → `_run_agent` → `_build_context_message` → `_run_build_task_loop` / `_write_build_reference_files`), keyed by `spec.id` with string-matched routing. This is leak **L15**. (2) `agents/artifact_store/` — a live DB-backed `ArtifactStore` (singleton `get_artifact_store()`) writing the `workflow_artifacts` table (model `app/models/artifact.py:WorkflowArtifact`, migration `0010_artifact_store`). Plan §17 names this "the thin store."
- **The `ArtifactStore` is dual-purpose.** Its artifact-persistence half (`store` / `retrieve_latest` / `retrieve_version` / `list_by_type` / `list_lineage`) is the §17 thin store. Its **in-memory `asyncio.Event` half** (`get_resume_event` / `set_questionnaire_responses` / `get_review_event` / `set_review_response`, used by `app/api/websocket.py` `submit_questionnaire` / `approve_review`) is HITL run-control plumbing — **not** artifact storage.
- **Persistence baseline.** `workflow_runs` (`app/models/workflow.py`) already has `user_id` (FK→users), `parent_run_id`, `status`, `model_id`, `token_usage`, `session_id`. It lacks `owner_id`, `workspace_id`, `source_run_id`, `plan_id`, `budget_snapshot_json`. There is **no** `artifact_refs`, `workspaces`, `run_events`, `run_capabilities`, or `workflows` (definitions) table. Events are streamed (WS/ndjson) but **not** durably logged with a per-run `seq`. Latest Alembic revision is `0013_collapse_pipeline_run_id`; new migrations are `0014+`.
- **Ownership seam.** Phase 2 landed a pure `assert_owns(owner_id, parent_run_id, parent_owner_id)` in `agents/execution_engine/authz.py` (L16, cross-owner denial test green). Its docstring states Phase 5 (AUTHZ-02) **relocates** it into a store-layer scoped-query helper backed by a real store lookup (mechanical move, D-06/INV-12).
- **API.** `app/api/runs.py` already reserves `/api/runs/{id}/artifacts|events` for this phase ("Phase 5 lands … here").

The gap this phase closes: there is no typed/lineage-tracked artifact graph, no durable event log, no default-deny store-layer scoping, and two competing artifact stores plus an in-memory mirror — all of which §17–§19 collapse into one owner-scoped `ArtifactGraph` + the §18 schema.

## Requirements

1. **ART-01 — ArtifactGraph / ArtifactRef**: A typed, content-addressed, owner-scoped DAG replaces the loose `accumulated_outputs: dict[str,str]` and the thin store.
   - Current: handoff is `accumulated_outputs[spec.id] = output` (in-memory dict) plus a separate DB `ArtifactStore`; no single typed graph.
   - Target: an `ArtifactGraph` of `ArtifactRef`s (new package under `agents/execution_engine/artifacts/`) is the per-run artifact substrate; `ArtifactRef` is typed and content-addressed (sha256), owner-scoped, and persisted.
   - Acceptance: the engine handoff reads/writes `ArtifactRef`s via the graph; a unit test builds a graph, writes two refs (one derived from the other), and reads back the typed lineage.

2. **ART-02 — Lineage fields on every write**: Every artifact write records its provenance.
   - Current: `WorkflowArtifact` records `producing_agent_id`, `version`, `derived_from_artifact_id` only; `accumulated_outputs` records nothing.
   - Target: every `ArtifactRef` records producer **step + agent + task**, `content_hash` (sha256), `location`, `version`, `parents`/`derived_from`, `visibility`, `retention`.
   - Acceptance: an `artifact_refs` row created during a prototype run has non-null producer step/agent, a sha256 `content_hash`, a `version`, and a resolvable `parents`/`derived_from` link for a revision-style artifact.

3. **ART-03 — Typed produces/consumes routing**: Routing replaces string matching; revision lineage is tracked.
   - Current: context routing is string-matched on `spec.id` keys in `accumulated_outputs` (`_filter_consumed_outputs`, `_build_context_sources`).
   - Target: `produces`/`consumes` route artifacts by typed contract (the AGENT.md `produces`/`consumes` already parsed by `WorkflowResolver`); revision lineage flows via `parents`/`derived_from`.
   - Acceptance: an agent declaring `consumes: [X]` receives exactly the `ArtifactRef`(s) of type X from the graph (not a substring match); a revision artifact's `derived_from` points at its parent-run source ref.

4. **ART-04 — Retention default**: Artifacts carry a retention policy.
   - Current: no retention concept; `workflow_artifacts` rows are immutable and never expire.
   - Target: every `ArtifactRef.retention` defaults to `run_ttl` (= the 48h sandbox TTL); `keep` and `days:N` overrides are honored. **The retention sweep/janitor is deferred to Phase 9** (aligns with the Workspace runtime TTL).
   - Acceptance: a written ref defaults `retention = run_ttl`; a ref written with `keep` persists that value; no sweep job is required for this phase to pass (N9 resolved for the default; sweep out of scope).

5. **PERSIST-01 — Additive schema (§18)**: Migrations add the typed/persistence tables, additive only.
   - Current: no `artifact_refs`, `workspaces`, `run_events`, `run_capabilities`, `workflows`; `workflow_runs` lacks the §18 columns.
   - Target: Alembic revisions `0014+` add `artifact_refs`, `workspaces`, `run_events`, `run_capabilities`, and `workflows` (definitions); **extend** `workflow_runs` with `owner_id`, `workspace_id`, `source_run_id`, `plan_id`, `budget_snapshot_json` (`parent_run_id`/`status` already exist). Every new table carries `owner_id` + `workspace_id`. `workspaces` is **schema-only** this phase — a default per-run workspace row (`kind=sandbox`, `runtime=local`) is created so every run/artifact has a real `workspace_id`; the `RuntimeEnvironment`/`Workspace` runtime port is Phase 9.
   - Acceptance: `alembic upgrade head` applies cleanly from `0013`, `alembic downgrade` reverses cleanly; each new table has `owner_id` + `workspace_id`; `artifact_refs` has idx `(run_id, kind)` and `(content_hash)`.

6. **PERSIST-02 — Dual-write then delete the mirror AND the thin store**: One artifact implementation remains.
   - Current: `accumulated_outputs` (L15) + the DB `ArtifactStore` artifact-persistence both live.
   - Target: typed refs are dual-written alongside the mirror, reads migrate to the typed graph, then **both** are deleted this phase — the `accumulated_outputs` mirror (L15 ☑) and the `ArtifactStore` artifact-persistence methods + `workflow_artifacts` table/model. The `websocket.py` `retrieve_latest("clarifications")` read is rewired to the typed store. The in-memory `asyncio.Event` HITL half is **kept**.
   - Acceptance: `grep -rn "accumulated_outputs" backend/agents backend/app --include=*.py` returns 0 in non-test code; `WorkflowArtifact` / `workflow_artifacts` and the `store`/`retrieve_*`/`list_*` methods are gone; `submit_questionnaire`/`approve_review` still function (HITL half intact).

7. **PERSIST-03 — Durable event log**: Events are persisted for replay/resume.
   - Current: events stream over WS/ndjson but are not durably stored with a per-run `seq`.
   - Target: a `run_events` row per emitted event carries monotonic per-run `seq` + `event_id` + `type` + `payload_json`; index `(run_id, seq)`.
   - Acceptance: after a run, `run_events` contains contiguous per-run `seq` values; each row has a unique `event_id`; the table is the source for the §API-05 replay endpoint.

8. **AUTHZ-01 — Ownership model**: A single ownership chain, with `owner_id` + `workspace_id` everywhere.
   - Current: scoping is implicit (on-disk `RunSandbox(user_id, run_id)` namespacing); rows carry `user_id` only.
   - Target: `user → workspace → (repository|project) → run → {artifacts}`; `owner_id` is a **string principal** added to every new/extended table (= `user_id` for authed runs, `anon:<session_id>` otherwise); the existing `user_id` FK is retained for authed joins.
   - Acceptance: `workflow_runs`, `artifact_refs`, `workspaces`, `run_events`, `run_capabilities` each have `owner_id` + `workspace_id`; an authed run's `owner_id == user_id`.

9. **AUTHZ-02 — Default-deny scoped-query helper**: One enforced read path.
   - Current: `assert_owns` is a pure predicate seeded by-convention (`_derive_parent_owner`); reads are not centrally scoped.
   - Target: a store-layer scoped-query helper enforces default-deny on all artifact/run/workspace reads (filter by `owner_id` + `workspace_id`); `assert_owns` is **relocated** into it backed by a real store lookup (mechanical move per D-06).
   - Acceptance: all artifact/run reads route through the helper; a query for a run/artifact the caller does not own returns nothing / raises the typed denial; `agents/execution_engine/authz.py`'s by-convention derivation is replaced by the store lookup.

10. **AUTHZ-03 — Anonymous principal never None**: Unauthenticated runs get a synthetic owner.
    - Current: unauthenticated principal is `user_id or "anon"` by convention in places; not a per-session isolated owner.
    - Target: an unauthenticated run is assigned `owner_id = anon:<session_id>` (never `None`); its artifacts/workspace are isolated per session.
    - Acceptance: an anonymous run persists `owner_id = anon:<session_id>`; a second anon session cannot read the first's artifacts via the scoped helper.

11. **AUTHZ-04 — Authz-denial tests pass**: Cross-owner access is proven rejected.
    - Current: only the L16 parent-run denial test exists (Phase 2).
    - Target: cross-owner **parent-run**, **artifact**, and **workspace** access each have a denial test.
    - Acceptance: tests asserting owner A cannot read owner B's parent run / artifact / workspace all pass (typed denial → 403/404 at the API boundary).

12. **CAPRUN-01 — run_capabilities persistence**: What was active is recorded per run.
    - Current: nothing records the active runtime/skills/hooks/MCP/integrations/model_overrides per run.
    - Target: a `run_capabilities` row per run records the **active runtime** (`langchain_deepagents`) now; columns for `model_overrides`, `skills`, `hooks`, `integrations`, `mcp_servers`, and versions exist and are populated by their owning phases (model_overrides→P6; skills/hooks/MCP/integrations→P8/P9).
    - Acceptance: a completed run has exactly one `run_capabilities` row recording `runtime = langchain_deepagents`; the deferred columns are present and nullable/empty.

13. **API-04 — Typed artifact tree endpoint**: Lineage is queryable.
    - Current: `app/api/runs.py` has no `/artifacts` endpoint.
    - Target: `GET /api/runs/{id}/artifacts` returns the typed `ArtifactRef` **lineage tree** (each node carries producer step/agent/task + `parents`/`derived_from` so lineage is walkable). (`/api/runs/{id}/diff` for repo diffs is Phase 9, not this phase.)
    - Acceptance: the endpoint returns a walkable lineage tree for a run with ≥2 linked artifacts; a cross-owner request is denied (403/404).

14. **API-05 — Durable event replay endpoint**: Reconnect replays from the log.
    - Current: no replay endpoint; reconnection relies on live state.
    - Target: `GET /api/runs/{id}/events?after=<seq>` returns **only** `run_events` rows with `seq > after`, in **ascending `seq`** order, each carrying `event_id` (idempotent replay).
    - Acceptance: with N events persisted, `?after=k` returns exactly the rows with `seq > k` in ascending order; each row has an `event_id`; a cross-owner request is denied (403/404).

## Boundaries

**In scope:**
- `ArtifactGraph` + typed `ArtifactRef` (content-addressed via sha256, owner-scoped, lineage-tracked) as the per-run artifact substrate; typed `produces`/`consumes` routing replacing string matching.
- Additive Alembic migrations (`0014+`): add `artifact_refs`, `workspaces` (schema-only + default per-run row), `run_events`, `run_capabilities`, `workflows` (definitions); extend `workflow_runs` (+`owner_id`, `workspace_id`, `source_run_id`, `plan_id`, `budget_snapshot_json`). Every new table carries `owner_id` + `workspace_id`.
- Default-deny store-layer scoped-query helper; `assert_owns` relocated into it (real store lookup); `anon:<session_id>` synthetic owner; cross-owner denial tests (parent/artifact/workspace).
- Durable `run_events` log (monotonic per-run `seq` + `event_id`, idx `(run_id, seq)`).
- `run_capabilities` persistence of the active runtime per run.
- `GET /api/runs/{id}/artifacts` (typed lineage tree) and `GET /api/runs/{id}/events?after=<seq>` (durable replay), both owner-scoped.
- Dual-write → migrate reads → **delete** the `accumulated_outputs` mirror (L15) **and** the DB `ArtifactStore` artifact-persistence + `workflow_artifacts` table/model; rewire the `websocket.py` clarifications read.
- Retention **field** (default `run_ttl`, `keep`/`days:N` overrides).
- Phase 0A characterization snapshots held byte-identical (deterministic deliverables) + semantic-event parity.

**Out of scope:**
- The in-memory `asyncio.Event` HITL half of `ArtifactStore` (questionnaire/review coordination) — run-control plumbing, not the §17 thin store; stays as-is (gate/HITL work is Phase 8).
- The retention **sweep/janitor** job — field now, sweep with the Workspace runtime (Phase 9), aligned to workspace TTL (N9 sweep).
- Content **dedup / replay-reuse** on hash match — that is RESUME-02 idempotent step retry (Phase 12); `content_hash` is recorded now, no reuse.
- `RuntimeEnvironment` / `Workspace` runtime port + `LocalSandboxRuntime` — Phase 9 (`workspaces` is schema-only here).
- `repositories` table — Phase 9; `subagent_runs` — Phase 11; `wave_runs` — Phase 12; `validation_results` / `gate_events` / `hook_runs` — Phase 8.
- `model_overrides` population (ModelResolver/ModelCatalog) — Phase 6; `budget_snapshot_json` population (BudgetManager) — Phase 11 (columns land additively now).
- `GET /api/runs/{id}/diff` (repo diff) — Phase 9; new run-stream event types (`subagent_*`/`wave_*`/`validator_*`/`merge_*`) — their phases (API-03 is Phase 8). Existing event contract stays at semantic parity.
- DB-authored **user** workflows — v2; the `workflows` table lands as schema for (file-backed) manifest metadata only, not DB-authored user workflows.
- Deleting kernel leaks L1–L12 / prototype-as-manifest parity — Phase 7.

## Constraints

- **Additive migrations only (Q3):** revisions `0014+` chained off `0013`; no destructive column changes except the sanctioned thin-store removal (PERSIST-02). Every new table carries `owner_id` + `workspace_id`.
- **No dual implementations (INV-3/INV-12):** the `accumulated_outputs` mirror **and** the thin DB store are deleted this phase once reads migrate — adding the abstraction without deleting what it supersedes means the phase is **not done**.
- **Backward-compat (Q3/INV-3):** prototype / `od_*` / PPT / code-gen deliverables stay byte-identical + semantic-event parity, proven by the Phase 0A characterization suite; the cutover is gated on parity (fix-forward, never ship with the mirror alive).
- **content_hash = sha256(content)** (assumption — recorded + indexed; no dedup this phase).
- **`owner_id` is always a real principal string** (`user_id` or `anon:<session_id>`), never `None`.
- **Security posture unchanged:** no `exec`/`network`/`secrets` introduced here; defaults stay OFF.
- **Tech stack:** Python · FastAPI · PostgreSQL · SQLAlchemy · Alembic · LangGraph checkpointer — extend, don't replace. `deepagents` runtime mandate (INV-13) unchanged.
- **Hexagonal:** artifact reads/writes go through the store-layer port/helper, not scattered in callers.

## Acceptance Criteria

- [ ] `grep -rn "accumulated_outputs" backend/agents backend/app --include=*.py` returns 0 in non-test code (L15 → ☑ in `migration-ledger.md`).
- [ ] The DB `ArtifactStore` artifact-persistence (`store`/`retrieve_latest`/`retrieve_version`/`list_by_type`/`list_lineage`) + the `WorkflowArtifact` model + `workflow_artifacts` table are deleted; `submit_questionnaire`/`approve_review` (the in-memory HITL half) still work.
- [ ] `alembic upgrade head` applies cleanly from `0013` and `alembic downgrade` reverses it; the migration adds `artifact_refs`, `workspaces`, `run_events`, `run_capabilities`, `workflows` and extends `workflow_runs` (+`owner_id`, `workspace_id`, `source_run_id`, `plan_id`, `budget_snapshot_json`).
- [ ] Every new table has `owner_id` + `workspace_id` columns; `artifact_refs` has idx `(run_id, kind)` + `(content_hash)`; `run_events` has idx `(run_id, seq)`.
- [ ] Each `artifact_refs` row records producer step/agent/task, sha256 `content_hash`, `version`, `parents`/`derived_from`, `visibility`, and `retention` (default `run_ttl`).
- [ ] Every run gets a real `workspace_id` (default per-run `workspaces` row, `kind=sandbox`, `runtime=local`).
- [ ] All artifact/run/workspace reads route through the default-deny scoped-query helper; a cross-owner parent / artifact / workspace read raises the typed denial (403/404) — denial tests pass.
- [ ] An unauthenticated run persists `owner_id = anon:<session_id>` (never `None`) and is isolated from other sessions.
- [ ] `run_events` rows carry monotonic per-run `seq` + unique `event_id`; `GET /api/runs/{id}/events?after=N` returns only `seq > N` rows in ascending `seq` order; cross-owner request denied.
- [ ] `GET /api/runs/{id}/artifacts` returns a walkable typed lineage tree (producer + parents/derived_from); cross-owner request denied.
- [ ] A completed run persists one `run_capabilities` row with `runtime = langchain_deepagents`; deferred columns present and nullable.
- [ ] Phase 0A characterization snapshots (prototype / od_prototype / prototype_revision / ppt / code-gen) stay byte-identical (deterministic deliverables) + semantic-event parity holds.

## Ambiguity Report

| Dimension          | Score | Min  | Status | Notes                                                            |
|--------------------|-------|------|--------|------------------------------------------------------------------|
| Goal Clarity       | 0.90  | 0.75 | ✓      | Precise: replace mirror+thin store → typed graph; land §18; default-deny; delete |
| Boundary Clarity   | 0.82  | 0.70 | ✓      | Thin-store fold scope, table scope (5 + workflows-defs), workspaces schema-only locked |
| Constraint Clarity | 0.85  | 0.65 | ✓      | Retention + owner model locked; content_hash = sha256 / no-dedup assumed (P12 owns reuse) |
| Acceptance Criteria| 0.86  | 0.70 | ✓      | Cutover exit-gate + API acceptance shapes falsifiable             |
| **Ambiguity**      | 0.14  | ≤0.20| ✓      | Gate passed after 2 focused rounds                               |

Status: ✓ = met minimum, ⚠ = below minimum (planner treats as assumption)

**Stated assumption (not below-minimum):** `content_hash = sha256(content)`, recorded + indexed, **no** dedup/replay-reuse this phase — dedup-on-hash-match is RESUME-02's idempotent retry (Phase 12). The planner may treat the hash algorithm as a settled default.

## Interview Log

| Round | Perspective     | Question summary                          | Decision locked                                                                 |
|-------|-----------------|-------------------------------------------|---------------------------------------------------------------------------------|
| 1     | Boundary Keeper | How far does "delete the mirror" go?      | Replace `accumulated_outputs` (L15) **+** fold the DB `ArtifactStore` artifact-persistence into `artifact_refs`; delete both this phase; keep the in-memory HITL `asyncio.Event` half |
| 1     | Boundary Keeper | Which §18 tables land in Phase 5?         | The 5 (`artifact_refs`, extend `workflow_runs`, `workspaces`, `run_events`, `run_capabilities`) **+ `workflows`-definitions**; others deferred to their phases; `workspaces` schema-only (default per-run row) |
| 1     | Boundary Keeper | `owner_id` vs existing `user_id`?         | Add `owner_id` string principal (`user_id` or `anon:<session_id>`); keep `user_id` FK; scoped helper filters `owner_id` + `workspace_id` |
| 2     | Seed Closer     | N9 retention default?                     | Default `run_ttl` (48h) + retention field + `keep`/`days:N`; sweep/janitor deferred to Phase 9 |
| 2     | Failure Analyst | Done-bar if parity is at risk at cutover? | Delete mandatory; parity gates it (`accumulated_outputs`→0 + thin store gone + byte-identical + semantic parity); fix-forward, never ship the mirror alive |
| 2     | Seed Closer     | API-04/05 acceptance shape?               | Lineage tree + ordered owner-scoped replay (`seq > N` ascending, `event_id`); cross-owner denied (403/404) |

---

*Phase: 05-typed-artifacts-persistence-ownership-1b*
*Spec created: 2026-06-07*
*Next step: /gsd-discuss-phase 5 — implementation decisions (artifact package layout, migration shape, scoped-helper API, endpoint serialization)*
