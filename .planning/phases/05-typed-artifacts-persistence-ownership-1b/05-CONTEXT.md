# Phase 5: Typed Artifacts + Persistence + Ownership [1B] - Context

**Gathered:** 2026-06-07
**Status:** Ready for planning
**Mode:** Recommended options locked (gray-area question dismissed — user chose "Lock all to recommendations", mirroring Phases 2 & 4). Every decision below is the plan.md-grounded recommendation. Review/edit this file before planning if any needs changing.

<domain>
## Phase Boundary

Replace the two competing artifact mechanisms — the untyped per-run `accumulated_outputs: dict[str,str]` handoff (leak **L15**) **and** the legacy DB `ArtifactStore` "thin store" (`agents/artifact_store/store.py` artifact-persistence half + `WorkflowArtifact` / `workflow_artifacts`) — with **one** typed, content-addressed (sha256), owner-scoped `ArtifactGraph` / `ArtifactRef`. Land the additive §18 persistence schema (Alembic `0014+`): add `artifact_refs`, `workspaces` (schema-only + a default per-run row), `run_events`, `run_capabilities`, `workflows` (definitions metadata); **extend** `workflow_runs` (+`owner_id`, `workspace_id`, `source_run_id`, `plan_id`, `budget_snapshot_json`). Add the default-deny store-layer scoped-query helper (relocating Phase 2's pure `assert_owns` into it, backed by a real store lookup); assign every run a real `owner_id` (`user_id` or `anon:<session_id>`, never `None`) + `workspace_id`. Persist a durable `run_events` log (monotonic per-run `seq` + `event_id`) and one `run_capabilities` row (`runtime=langchain_deepagents`). Expose `GET /api/runs/{id}/artifacts` (typed lineage tree) + `GET /api/runs/{id}/events?after=<seq>` (durable replay), both owner-scoped.

**This phase deletes BOTH the mirror and the thin store** (dual-write → migrate reads → delete), gated on Phase-0A byte-identical deliverables + semantic-event parity. Adding the typed graph without deleting what it supersedes means the phase is **not done** (INV-3/INV-12).

**Explicitly NOT this phase:** the retention sweep/janitor (P9), the `RuntimeEnvironment`/`Workspace` runtime port + `LocalSandboxRuntime` (P9 — `workspaces` is schema-only here), dedup/replay-reuse on hash match (P12), and deleting kernel leaks L1–L13 (P7).

</domain>

<spec_lock>
## Requirements (locked via SPEC.md)

**14 requirements are locked.** See `05-SPEC.md` for full requirements (ART-01..04, PERSIST-01..03, AUTHZ-01..04, CAPRUN-01, API-04, API-05), boundaries, and acceptance criteria.

Downstream agents MUST read `05-SPEC.md` before planning or implementing. Requirements are not duplicated here.

**In scope (from SPEC.md):**
- `ArtifactGraph` + typed `ArtifactRef` (content-addressed via sha256, owner-scoped, lineage-tracked) as the per-run artifact substrate; typed `produces`/`consumes` routing replacing string matching.
- Additive Alembic migrations (`0014+`): add `artifact_refs`, `workspaces` (schema-only + default per-run row), `run_events`, `run_capabilities`, `workflows` (definitions); extend `workflow_runs` (+`owner_id`, `workspace_id`, `source_run_id`, `plan_id`, `budget_snapshot_json`). Every new table carries `owner_id` + `workspace_id`.
- Default-deny store-layer scoped-query helper; `assert_owns` relocated into it (real store lookup); `anon:<session_id>` synthetic owner; cross-owner denial tests (parent/artifact/workspace).
- Durable `run_events` log (monotonic per-run `seq` + `event_id`, idx `(run_id, seq)`).
- `run_capabilities` persistence of the active runtime per run.
- `GET /api/runs/{id}/artifacts` (typed lineage tree) and `GET /api/runs/{id}/events?after=<seq>` (durable replay), both owner-scoped.
- Dual-write → migrate reads → **delete** the `accumulated_outputs` mirror (L15) **and** the DB `ArtifactStore` artifact-persistence + `workflow_artifacts` table/model; rewire the `websocket.py` clarifications read.
- Retention **field** (default `run_ttl`, `keep`/`days:N` overrides).
- Phase 0A characterization snapshots held byte-identical (deterministic deliverables) + semantic-event parity.

**Out of scope (from SPEC.md):**
- The in-memory `asyncio.Event` HITL half of `ArtifactStore` (questionnaire/review coordination) — stays as-is (gate/HITL work is Phase 8).
- The retention **sweep/janitor** job — field now, sweep with the Workspace runtime (Phase 9), aligned to workspace TTL (N9 sweep).
- Content **dedup / replay-reuse** on hash match — RESUME-02 idempotent step retry (Phase 12); `content_hash` is recorded now, no reuse.
- `RuntimeEnvironment` / `Workspace` runtime port + `LocalSandboxRuntime` — Phase 9 (`workspaces` is schema-only here).
- `repositories` table — Phase 9; `subagent_runs` — Phase 11; `wave_runs` — Phase 12; `validation_results` / `gate_events` / `hook_runs` — Phase 8.
- `model_overrides` population — Phase 6; `budget_snapshot_json` population — Phase 11 (columns land additively now).
- `GET /api/runs/{id}/diff` (repo diff) — Phase 9; new run-stream event types — their phases. Existing event contract stays at semantic parity.
- DB-authored **user** workflows — v2; the `workflows` table lands as schema for (file-backed) manifest metadata only.
- Deleting kernel leaks L1–L12 / prototype-as-manifest parity — Phase 7.

</spec_lock>

<decisions>
## Implementation Decisions

> The SPEC locked the 14 requirements (WHAT) at ambiguity 0.14. These are the four HOW forks the SPEC flagged for discussion (package layout, migration shape, scoped-helper API, endpoint serialization), each **locked to the plan.md-grounded recommendation**, plus the mechanical decisions they imply. Per the standing project directive ("everything from plan.md must be honored — nothing dropped") the recommendations favor the plan-faithful, lowest-INV-3-risk option.

### Area A — Artifact storage model & package layout (SPEC: "artifact package layout")

- **D-01: `artifact_refs` keeps an INLINE `content: Text` column AND records `content_hash` + `location`.** The thin store being deleted (`workflow_artifacts.content`) is inline Text today; the faithful, lowest-risk swap keeps content **self-contained in the row** so deliverables/lineage/replay survive the 48h sandbox TTL (the retention sweep is Phase 9 — content must not vanish before then) and the scoped-query helper stays **pure-DB** (no sandbox/runtime coupling — the `Workspace` runtime is Phase 9). `content_hash = sha256(content.encode("utf-8")).hexdigest()` is computed over the inline content (deterministic, no disk re-read). The plan-literal `location` field (§6: `sandbox path | store id | git ref`) is **still populated** — the sandbox-relative path for file-backed artifacts (e.g. the HTML deliverable), or a logical store id (e.g. `artifact_refs/{id}`) for string artifacts (spec/plan/tasks) that have no disk file — so Phase 9 can later prefer `location` with no schema change.
  - *Rejected:* location-pointer-only (content dies with the 48h TTL → API-04 / lineage / replay break; couples the store helper to the sandbox/runtime that doesn't exist until Phase 9; risks byte-drift on disk re-read). Hybrid inline/pointer — premature (dedup is Phase 12).

- **D-02: Package layout follows plan §32 exactly.** Typed graph → **`agents/artifacts/`** (sibling of the kernel, NOT inside `execution_engine/`): a `graph.py` holding `ArtifactGraph` (per-run; typed `produces`/`consumes` routing; lineage walk) + the `ArtifactRef` dataclass (mirrors plan §6 lines 454–466 **plus** the inline `content` field from D-01). The SQLAlchemy row model → **`app/models/artifact_ref.py`** (`ArtifactRef` table `artifact_refs`), **replacing** `app/models/artifact.py`'s `WorkflowArtifact`. Mapping dataclass↔row lives in the store helper (Area C). One name everywhere (§32): the dataclass, the table, and the `kind` strings stay consistent snake_case.
  - **Researcher directive:** confirm the exact import-linter contract in `backend/pyproject.toml` — `agents/artifacts/` (typed, referenced by `ExecutionContext` in the kernel) must be kernel-importable; the DB-touching store/authz helper (Area C) must NOT pull `app.api` into the kernel. The `engine.py`→`kernel.py` split is Phase 7, so the contract is still the Phase-1 scaffold (kernel ↛ `app.api`); keep new imports inside that.

### Area B — Migration shape & thin-store drop ordering (SPEC: "migration shape")

- **D-03: Split chain — `0014` additive, `0015` destructive (drop), drop lands LAST after the read-cutover.** PERSIST-02 is dual-write → migrate reads → delete; the destructive `workflow_artifacts` DROP is the **one sanctioned** non-additive change (Q3 / SPEC constraint) and must land **after** reads cut over and parity is green.
  - **`0014_typed_artifacts_persistence`** (additive, chained off `0013`): create `artifact_refs`, `workspaces`, `run_events`, `run_capabilities`, `workflows`; extend `workflow_runs` (+`owner_id`, `workspace_id`, `source_run_id`, `plan_id`, `budget_snapshot_json`). New columns/tables nullable/defaulted so `alembic upgrade head` applies cleanly over existing rows; `alembic downgrade` reverses cleanly. Indexes: `artifact_refs (run_id, kind)` + `(content_hash)`; `run_events (run_id, seq)`.
  - **Default-workspace backfill** (data migration inside `0014`, or a tiny `0014b`): create one default `workspaces` row per existing run (`kind=sandbox`, `runtime=local`, `ttl=run_ttl`) and set `workflow_runs.owner_id = user_id`, `workspace_id = <that row>` for existing rows — so **every** run (incl. historical) has a real `workspace_id` and the scoped helper applies uniformly.
  - **`0015_drop_thin_artifact_store`** (destructive, sanctioned): drop `workflow_artifacts`. Authored as a separate revision and **sequenced last in the phase** — applied only once `accumulated_outputs`→0, reads are on the typed graph, and the 0A parity suite is green (fix-forward; never ship with the mirror/thin store alive).
  - *Rejected:* a single `0014` doing add+drop — couples the irreversible DROP to the additive step, muddies `downgrade`, and removes the dual-write window the strangler needs.

- **D-04: New runs create their default workspace at `execute()` entry.** On run start the engine inserts a `workspaces` row (`kind=sandbox`, `runtime=local`, `ttl=run_ttl`) and sets `ExecutionContext.workspace_id`. The Alembic backfill (D-03) handles only pre-existing rows.

- **D-05: Flip ledger L15 ☑ + add a thin-store deletion gate.** Flipping L15 to ☑ arms the `accumulated_outputs` grep ratchet (gate: `grep -rn accumulated_outputs backend/ --include=*.py` → 0 in non-test). Add a parallel deletion gate (new ledger row or acceptance check) for the thin store: `WorkflowArtifact` / `workflow_artifacts` and the `store`/`retrieve_*`/`list_*` artifact-persistence methods → 0. **The migration-ledger CI guard + import-linter must stay green.**

### Area C — Scoped-query helper API & `assert_owns` relocation (SPEC: "scoped-helper API")

- **D-06: The default-deny scoped-query helper lives in `agents/authz.py` (plan §32 "ownership-scoped query/seed helpers").** Phase 2's pure `assert_owns` (`agents/execution_engine/authz.py`) **relocates up** to `agents/authz.py` and **grows** from a pure predicate into the store-layer helper — this is the D-06 mechanical MOVE that Phase 2 sited it for (INV-12 move-don't-copy). Shape: a cohesive scoped store/repository object constructed with the caller principal `(owner_id, workspace_id)` + a DB session, where **every read filters** `WHERE owner_id = :owner AND (workspace_id = :ws OR visibility IN ('workspace','public'))` (default-deny). One enforced read path (§19: "not scattered in callers"). Candidate surface: `write_ref`, `get_ref`, `list_refs(run_id, kind=None)`, `lineage(run_id)` / `tree(run_id)`, `append_event`, `read_events(run_id, after_seq)`, `get_run`, `create_workspace`, `record_capabilities`.
  - *Rejected:* standalone free functions (harder to guarantee "all reads go through it" + a uniform principal); leaving `assert_owns` in the kernel (contradicts §32 + Phase 2's stated relocation).

- **D-07: `assert_owns` becomes a real-lookup method.** It no longer takes a by-convention `parent_owner_id` arg; it **looks up** the parent run's `owner_id` from the store and raises the typed `PermissionError` on mismatch (AUTHZ-02). The L16 call-site in `engine.py` rewires to the relocated helper. The Phase-2 cross-owner denial test (`tests/agents/test_parent_run_ownership.py`) must stay green now exercising the store lookup, and AUTHZ-04 adds cross-owner **artifact** + **workspace** denial tests.

- **D-08: Store methods are `async`; cross-owner denial surfaces as 404 at the API.** Matches the existing async thin store + the async engine + the async DB session. The two NEW `runs.py` endpoints (Area D) become `async def` (existing sync `def` run-history handlers stay sync — mixing is fine in FastAPI). A cross-owner request returns **404** (don't-leak existence) per the SPEC "returns nothing / typed denial → 403/404".
  - **Researcher directive:** confirm the DB session flavor the thin store uses (sync vs async SQLAlchemy session, how `get_artifact_store()` acquires it) so the relocated helper reuses the same acquisition path.

- **D-09: Owner/workspace population path + byte-identity guard (resolves Phase-2 deferrals).** At `execute()` entry: `ctx.owner_id = user_id or f"anon:{session_id}"` (upgrades Phase 2's `user_id or "anon"` to AUTHZ-03's `anon:<session_id>`, never `None`); `ctx.workspace_id = <default workspace row id>` (D-04). Add `artifacts: ArtifactGraph` and `workspace_id: str` to `ExecutionContext` (the §6 fields Phase 2 deferred to here; `workspace: Workspace` stays Phase 9). **CRITICAL byte-identity guard:** `RunSandbox` on-disk keying must stay `user_id or "anon"` (unchanged from Phase 2 D-04/D-05) — do NOT derive the sandbox dir from the new `ctx.owner_id`, or anon runs' disk paths change and risk a CTX-05 / 0A snapshot break. `ctx.owner_id` is the **persisted DB principal only**, decoupled from the disk path (for authed runs `owner_id == user_id`, so only anon runs differ).
  - **Researcher directive:** confirm the `session_id` source for anonymous runs (`workflow_runs.session_id` is "= user_id (JWT sub)"; the anon principal needs a stable per-session id — likely the WS/session id). Lock the **format** `anon:<session_id>`; confirm the **source**.

### Area D — API serialization & durable-event wiring (SPEC: "endpoint serialization")

- **D-10: `GET /api/runs/{id}/artifacts` returns a nested lineage TREE.** Each node = the `ArtifactRef` fields (id, kind, producer step/agent/task, content_hash, version, visibility, retention, location) + `children: []`, assembled from roots by walking `parents`/`derived_from` (SPEC "walkable lineage tree"). Inline `content` is **excluded by default** (keep the tree light); expose content via a separate fetch or an explicit `?include=content` flag — planner's call. Cross-owner → 404 (D-08).

- **D-11: Durable `run_events` reuses the engine's EXISTING per-run `seq` — do not invent a second counter.** SAFE-03 already asserts the in-memory event `seq` is contiguous per run; the durable log must persist **that same seq** so replay matches the live stream. Tap a **persistence sink at the engine's event-emit boundary** (where seq is already assigned — the `ndjson_adapter` / event-stream chokepoint), writing each emitted event to `run_events` with its existing `seq` + a generated `event_id`. `GET /api/runs/{id}/events?after=<seq>` returns rows with `seq > after`, ascending, each carrying `event_id` (idempotent replay).
  - **Researcher directive:** locate the exact emit chokepoint (engine → `ndjson_adapter` → WS) and confirm `seq` is assigned once upstream of the sink; confirm `event_id` is in the 0A-normalized-out set (generated IDs) so adding it doesn't break semantic-event parity.
  - *Rejected:* assigning a fresh DB-side `seq` (Postgres sequence / `MAX(seq)+1`) independent of the engine's seq — risks divergence from the live stream and the SAFE-03 contiguity contract.

- **D-12: `run_capabilities` row written at `execute()` entry.** One row per run with `runtime = langchain_deepagents` (sourced from the active runtime / `CompiledWorkflow`); the deferred columns (`model_overrides`→P6, `skills`/`hooks`/`integrations`/`mcp_servers`→P8/P9) present and nullable/empty.

### Dual-write cutover sequencing (the strangler increment — locked to plan-grounded order)

- **D-13: Sequence within the phase = add → dual-write → migrate reads → delete, parity-gated.** Suggested plan order (planner's final call): (1) `0014` schema + `ArtifactGraph`/`ArtifactRef` + the relocated scoped helper + owner/workspace population; (2) dual-write typed refs alongside the `accumulated_outputs` mirror + the thin store (mirror still source of truth); (3) migrate engine reads + `websocket.py:543` clarifications read to the typed graph; (4) durable `run_events` sink + `run_capabilities` + the two endpoints; (5) **once 0A parity is green** — delete the mirror (flip L15 ☑) + the thin store + apply `0015` drop. The parity gate (0A deliverable byte-snapshots + semantic-event snapshots) sits before step 5 and blocks the deletion.

### Claude's Discretion
- Exact field names/order inside `ArtifactGraph` / `ArtifactRef` (within D-01's set) and the dataclass↔row mapping location.
- Whether the default-workspace backfill is a data step inside `0014` or a tiny separate `0014b` revision.
- Plan-task granularity / split across D-13's five concerns (schema; graph+helper; dual-write; read-migrate; events+endpoints; delete) — planner's call.
- The `?include=content` content-fetch shape for API-04 (D-10).
- Whether `run_capabilities` is inserted at run start (D-12) or upserted at completion, provided exactly one row per completed run records `runtime=langchain_deepagents`.
- Exact `async def` route handler signatures / response models / auth dependencies for the two new endpoints (mirror existing `runs.py` patterns).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Locked requirements (read FIRST)
- `.planning/phases/05-typed-artifacts-persistence-ownership-1b/05-SPEC.md` — the 14 locked requirements (ART-01..04, PERSIST-01..03, AUTHZ-01..04, CAPRUN-01, API-04/05), boundaries, acceptance criteria. **Locked requirements — MUST read before planning.**

### The specification (authoritative — `specs/003-workflow-engine-decoupling/plan.md`)
- **§6 lines 454–466** — the `ArtifactRef` dataclass (the exact typed field set D-01/D-02 mirror, + the inline `content` addition).
- **§6 lines 468–495** — `RuntimeEnvironment`/`Workspace`/`IsolationProvider`/`BudgetManager` Protocols (designed-now context; **runtime impl is Phase 9** — `workspaces` schema-only here).
- **§11 lines 609–628** — Leak → new-home mapping: **L15** `accumulated_outputs` → `ArtifactGraph`/`ArtifactRef` (1A→**1B delete mirror**); **L16** unchecked parent seeding → ownership check at the store layer.
- **§17 lines 688–695** — Artifact graph & lineage: content-addressed, owner-scoped DAG; replaces the mirror AND the thin store; retention default `run_ttl`.
- **§18 lines 697–717** — Persistence schema: the table-by-table column lists (`artifact_refs`, `workflow_runs` extend, `workspaces`, `run_events`, `run_capabilities`, `workflows`); every table carries `owner_id` + `workspace_id`; additive only.
- **§19 lines 719–730** — Authorization: ownership model, default-deny, store-layer single scoped-query helper, `anon:<session_id>` never-`None` owner.
- **§21 lines 740–753** — Cancellation/retry/resume: the monotonic per-run `seq` + `event_id` durable log; reconnect = replay via `after=<last_seq>` (the API-05 contract; dedup-reuse is Phase 12).
- **§22 lines 755–771** — API/frontend contract: `GET /api/runs/{id}/artifacts` (lineage tree) + `GET /api/runs/{id}/events?after=<seq>` (durable replay); `/diff` is Phase 9.
- **§31 lines 989–1025** — Migration & deletion ledger: the strangler wrap→rewire→delete discipline; the **one sanctioned temporary duplication** (the `accumulated_outputs` mirror, deleted in 1B); deletion = exit gate.
- **§32 lines 1027–1098** — Target directory structure (D-02/D-06 layout: `agents/artifacts/`, `agents/authz.py`, `app/models/{artifact_ref,workspace,run_event,run_capabilities}.py`, `app/api/runs.py`) + the Ports & Adapters patterns + import-linter direction.
- `specs/003-workflow-engine-decoupling/migration-ledger.md` — operational mirror of §31 (CI-asserted): the **L15** row (gate `accumulated_outputs` → 0, owning phase 1B, still ☐) and the **L16** row (☑ CHECK; the relocated helper must keep it green).

### Project planning
- `.planning/REQUIREMENTS.md` — ART-01..04 (lines 46–49), PERSIST-01..03 (50–52), AUTHZ-01..04 (53–56), CAPRUN-01 (157), API-04/05 (164–165) with plan anchors; the phase→requirement traceability (Phase 5 = 14 reqs).
- `.planning/ROADMAP.md` § Phase 5 — goal + the surrounding phase ordering (P6 model policy, P7 parity/leak-deletion, P9 runtime, P11 fan-out, P12 wave/resume) that bounds what is deferred.
- `.planning/PROJECT.md` — invariants/constraints (INV-3 back-compat byte-identical + semantic parity, INV-8 ownership/default-deny, INV-10 typed artifacts, INV-12 no dual impl, INV-13 deepagents); Key Decisions (N9 retention pending→resolved by SPEC); "nothing from plan.md dropped".
- `.planning/phases/02-executioncontext-ownership-0b/02-CONTEXT.md` — Phase 2 decisions this phase consumes: D-04/D-05 (`user_id or "anon"` disk keying — the byte-identity guard D-09 preserves), D-06 (`assert_owns` sited to relocate here), the deferred `workspace_id` / `anon:<session_id>` / heavy `ExecutionContext` fields.
- `.planning/phases/04-manifest-compiler-1a/04-CONTEXT.md` — Phase 4 decisions this phase builds on: the `/api/runs.py` router (D-01/D-02) that now gains `/artifacts|events`; the `CapabilityRegistry` (`runtime=langchain_deepagents` for `run_capabilities`); `plan.py` forward fields (`plan_id`).

### Code to read (targets / assets)
- `backend/agents/execution_engine/authz.py` — the pure `assert_owns(owner_id, parent_run_id, parent_owner_id)` to **relocate** to `agents/authz.py` + grow into the scoped helper (D-06/D-07).
- `backend/agents/execution_engine/engine.py` (~146 KB) — `execute()` entry (owner/workspace/artifacts/run_capabilities wiring D-09/D-12); the L16 parent-seed block (`~:583-610`, rewire to the relocated helper); the read-sites that consume `accumulated_outputs` (migrate to the typed graph); the event-emit path feeding the `run_events` sink (D-11).
- `backend/agents/execution_engine/context.py` — `ExecutionContext` (add `artifacts: ArtifactGraph` + `workspace_id`; upgrade `owner_id` per D-09).
- `backend/agents/execution_engine/ndjson_adapter.py` — the event-stream adapter near the seq-assignment chokepoint (D-11 sink location — confirm).
- `backend/agents/artifact_store/store.py` (~15 KB) — the thin store: DELETE the artifact-persistence half (`store`/`retrieve_latest`/`retrieve_version`/`list_by_type`/`list_lineage`, `get_artifact_store` DB usage); **KEEP** the in-memory HITL `asyncio.Event` half (`get_resume_event`/`set_questionnaire_responses`/`get_review_event`/`set_review_response` used by `websocket.py` `submit_questionnaire`/`approve_review`).
- `backend/app/models/artifact.py` — `WorkflowArtifact` (table `workflow_artifacts`) to DELETE; replaced by `app/models/artifact_ref.py` (`artifact_refs`).
- `backend/app/models/workflow.py` — `WorkflowRun` (`workflow_runs`) to EXTEND (+`owner_id`, `workspace_id`, `source_run_id`, `plan_id`, `budget_snapshot_json`); has `user_id` FK, `parent_run_id`, `status`, `session_id`, `model_id` today.
- `backend/app/models/workflow_definition.py` — **reconcile** with the new §18 `workflows` (definitions) table (rename/extend/new — researcher directive).
- `backend/alembic/versions/0013_collapse_pipeline_run_id.py` + `backend/alembic/env.py` — the migration chain head (`0014+` chain off `0013`); pattern `NNNN_name.py`.
- `backend/app/api/runs.py` — `APIRouter(prefix="/api/runs")`; header already reserves `/artifacts|events` for Phase 5; **sync `def`** handlers today (new endpoints are `async def`, D-08/D-10).
- `backend/app/api/websocket.py` (`:543` `retrieve_latest(..., "clarifications")`; `:663` `submit_questionnaire`; `:681` `approve_review`) — rewire the clarifications read to the typed store; keep the HITL handlers working.
- `backend/tests/agents/_scripted_model.py` + `tests/agents/characterization/` + `test_characterization_*.py` — the 0A deliverable byte + semantic-event snapshots that gate the cutover (D-13).
- `backend/tests/agents/test_parent_run_ownership.py` — the Phase-2 L16 denial test (must stay green via the relocated helper; AUTHZ-04 extends with artifact/workspace denial tests).
- `backend/tests/agents/test_migration_ledger.py` + `backend/pyproject.toml` (import-linter + vulture config) — CI gates: flip L15 ☑ (arms `accumulated_outputs` ratchet), keep import-linter green.
- `backend/CLAUDE.md` — backend architecture (engine = deterministic sequencer; commit scopes `engine`/`registry`/`tests`; dev runtime `python3.11`, no venv).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`agents/artifact_store/store.py`** — the existing async DB store: its persistence methods are the behavior the typed `artifact_refs` writes/reads replace (move-don't-copy); its HITL `asyncio.Event` half is the part that survives. The async session-acquisition pattern (`get_artifact_store()`) is the model the relocated scoped helper reuses (D-08).
- **`agents/execution_engine/authz.py`** — the pure `assert_owns` predicate, written intentionally lean/pure (Phase 2 D-06) so the relocation into `agents/authz.py` + real-lookup growth is mechanical (D-06/D-07).
- **`app/models/artifact.py` `WorkflowArtifact`** — the column shape (`producing_agent_id`, `version`, `derived_from_artifact_id`, inline `content` Text) is the precedent the richer `artifact_refs` schema extends (adds `owner_id`/`workspace_id`/`content_hash`/`location`/`parents`/`visibility`/`retention`).
- **`app/api/runs.py` router** — existing FastAPI patterns (`APIRouter(prefix=…)`, `response_model=`, `Depends` auth, `HTTPException(404)`, IDOR filtering on run-history) to reuse for the two new owner-scoped endpoints.
- **`_scripted_model.py` 0A snapshots** — the offline regression gate; re-run after each strangler step (D-13) to keep deliverables byte-identical + events at semantic parity.

### Established Patterns
- **Additive migrations only (Q3)** — `0014+` chains off `0013`; the only sanctioned destructive change is the thin-store DROP (`0015`, D-03). Every new table carries `owner_id` + `workspace_id`.
- **Deterministic sequencer + per-run `ExecutionContext` (INV-2)** — the typed graph + owner/workspace ride on the per-run ctx; the kernel stays stateless. The typed `ArtifactRef` handoff replaces the `dict[str,str]` (the §32 "typed seams" pattern).
- **Ports & Adapters / import-linter (§31/§32)** — `agents/artifacts/` is kernel-importable typed data; DB-touching helpers stay out of `app.api`'s reach from the kernel. The `engine.py`→`kernel.py` split is Phase 7 — keep the Phase-1 import-linter scaffold green.
- **Move-don't-copy + deletion-as-exit-gate (INV-12/§31)** — adding the typed graph without deleting the mirror + thin store = not done. Flip L15 ☑ + add the thin-store gate (D-05).
- **Dev runtime** — `python3.11`, no venv; `cd backend && python3.11 -m pytest tests/agents/ tests/unit/ -v`; commit scopes per `backend/CLAUDE.md`; PR off `feature/003-workflow-engine-decoupling`, never `main`.

### Integration Points
- **Net-new:** `agents/artifacts/` (graph.py + ArtifactRef dataclass); `app/models/artifact_ref.py`, `app/models/workspace.py`, `app/models/run_event.py`, `app/models/run_capabilities.py`; Alembic `0014` + `0015`; the two `app/api/runs.py` endpoints.
- **Grows:** `agents/authz.py` (relocated `assert_owns` → scoped store helper); `agents/execution_engine/context.py` (`artifacts` + `workspace_id` fields); `app/models/workflow.py` (`workflow_runs` extension); the `workflows`-definitions table (reconcile with `workflow_definition.py`).
- **Rewired then deleted:** `engine.py` `accumulated_outputs` read/write-sites → typed graph (then L15 ☑); `agents/artifact_store/store.py` artifact half + `app/models/artifact.py` + `workflow_artifacts` → deleted; `websocket.py:543` clarifications read → typed store.
- **Event sink:** the engine/`ndjson_adapter` emit path gains a durable `run_events` sink reusing the existing per-run `seq` (D-11).
- **CI gates that constrain the work:** migration-ledger ratchet (flip L15, don't regress L16), import-linter (kernel→ports), characterization snapshots (parity gate before deletion).

</code_context>

<specifics>
## Specific Ideas

- **Standing project directive (init):** "everything from plan.md must be honored — nothing dropped." Every lock above takes the plan-faithful option (inline content for TTL-survival + pure-DB helper; §32-literal package layout; split additive/destructive migrations; reuse the engine's existing `seq`) over a lighter shortcut.
- **Mode:** the user dismissed the per-area discussion and chose "Lock all to recommendations" (mirrors Phase 1 `--auto` + Phase 2's dismissal). Treat all D-01..D-13 as locked unless this file is edited.
- **The cutover is parity-gated, fix-forward:** the deletion of the mirror + thin store (D-13 step 5) is blocked on the 0A suite being green — never ship with the mirror alive (INV-3 / SPEC constraint).
- **N9 retention** is resolved by the SPEC (default `run_ttl` + `keep`/`days:N`; sweep deferred to Phase 9) — recorded as a field only this phase; do not build the sweep.

</specifics>

<deferred>
## Deferred Ideas

- **Retention sweep/janitor** — Phase 9, aligned to the workspace runtime TTL (N9 sweep). Field only here.
- **`RuntimeEnvironment` / `Workspace` runtime port + `LocalSandboxRuntime`** — Phase 9. `workspaces` is schema-only + a default per-run row here; `ctx.workspace: Workspace` (vs the `workspace_id` string) lands then.
- **`repositories` table** — Phase 9; **`subagent_runs`** — Phase 11; **`wave_runs`** — Phase 12; **`validation_results` / `gate_events` / `hook_runs`** — Phase 8. (Listed in §18 but each lands in its owning phase.)
- **`model_overrides` population** (ModelResolver/ModelCatalog) — Phase 6; **`budget_snapshot_json` population** (BudgetManager) — Phase 11. The columns land additively now (nullable/empty).
- **Content dedup / replay-reuse on hash match** — Phase 12 (RESUME-02). `content_hash` is recorded + indexed now; no reuse.
- **`GET /api/runs/{id}/diff`** (repo diff) + new run-stream event types — Phase 9 / their phases. Existing event contract stays at semantic parity.
- **DB-authored user workflows** — v2. The `workflows` table is file-backed manifest metadata only this phase.
- **Deleting kernel leaks L1–L13 / prototype-as-manifest parity** — Phase 7. Only L15 (mirror) + the thin store are deleted here.
- **`engine.py` → `kernel.py` split + import-linter tightening** — Phase 7. This phase keeps `engine.py`.
- **Historical `workflow_artifacts` → `artifact_refs` content backfill** — **out of scope (recorded decision, not a silent drop).** The §18 schema + typed graph cover the *new* per-run mechanism; the SPEC/CONTEXT mandate schema + the default-**workspace** backfill (D-03) only, NOT a content backfill of historical artifact rows. `0015` drops `workflow_artifacts` without migrating its content; revision/lineage of **pre-cutover** runs is acceptably best-effort (those runs predate `artifact_refs`). New runs are fully typed from cutover forward. Surfaced by plan-checker (A2) — recorded here so the drop is a deliberate, visible decision. *Override:* if historical artifacts must survive, add a one-time data-migration task to 05-06 before the `0015` DROP.

None of these are scope creep — all are explicitly later-phase per ROADMAP.md / the §31 ledger.

</deferred>

---

*Phase: 5-typed-artifacts-persistence-ownership-1b*
*Context gathered: 2026-06-07*
