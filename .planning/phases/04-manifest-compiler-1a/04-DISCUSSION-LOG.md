# Phase 4: Manifest + Compiler [1A] - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-07
**Phase:** 04-manifest-compiler-1a
**Areas discussed:** A. /api/workflows collision, D. Coverage & aliases

---

## Gray-area selection

| Area | Description | Selected to discuss |
|------|-------------|---------------------|
| A. /api/workflows collision | Existing GET /api/workflows + /{id} = run-history; API-01 wants those paths for manifest metadata | ✓ |
| B. Type-contract scope | Full §6 Step/CompiledWorkflow/Task now vs. minimal-grow-per-phase | (locked to rec) |
| C. Registry seam depth | Minimal name-registry vs. @register/discover() machinery now | (locked to rec) |
| D. Coverage & aliases | Which pipeline_types get a real workflow.yaml vs. alias; reverse_engineer + chat | ✓ |

---

## A. /api/workflows collision

### Question 1 — resolving the path collision

| Option | Description | Selected |
|--------|-------------|----------|
| Catalog sub-path (Recommended) | /api/workflows/catalog + /catalog/{id} in existing router; additive, back-compat-safe, keeps §32 file home; adjusts SPEC's literal path | |
| Reclaim /api/workflows | Move run-history to /api/runs; /api/workflows + /{id} become manifest endpoints per SPEC literal text; changes an existing frontend endpoint | ✓ |
| New distinct router | Separate file/path for definitions; cleanest isolation but deviates from SPEC path + §32 file home | |

**User's choice:** Reclaim /api/workflows (user override of the recommendation).
**Notes:** Justified by plan §22 — run-scoped resources already live under /api/runs/{id}/* (API-04/05), so moving run-history there is plan-aligned, not scope creep. Consistent with the standing "honor the plan literally / nothing dropped" directive.

### Question 2 — migration scope

| Option | Description | Selected |
|--------|-------------|----------|
| Full move + frontend repoint (Recommended) | New app/api/runs.py holds all run-history routes; repoint 10 frontend refs; rewrite workflows.py as definitions router; no aliases; researcher confirms no external API-key consumer | ✓ |
| Full move + deprecated aliases | Same, but keep non-colliding old routes as deprecated aliases for a transition window | |
| Backend-only, defer frontend | Ship backend cutover now; defer frontend repoint (run-history UI temporarily broken) | |

**User's choice:** Full move + frontend repoint, clean break.
**Notes:** Consumer surface is small/localized (10 refs: lib/api.ts + FilesTab/PreviewPanel/PPTPreview). Routes moved: GET /api/runs (was GET /api/workflows, keeps ?type=&limit=), GET /{id}, GET /{id}/chain-context, DELETE /{id}, POST /export-pptx.

---

## D. Coverage & aliases

### Question 1 — edge-case pipeline treatment

| Option | Description | Selected |
|--------|-------------|----------|
| Exclude both, exempt in test (Recommended) | reverse_engineer (0 agents) + chat (ChatRunner, not engine) get no manifest; coverage test exempts them with documented reasons | |
| Placeholder manifests for both | Author workflow.yaml for chat + reverse_engineer too; zero coverage-test exemptions; ships 2 manifests the engine never runs | ✓ |
| Exclude reverse_engineer; include chat | chat manifest authored (anticipates Phase-7b); only reverse_engineer exempted | |

**User's choice:** Placeholder manifests for both (user override of the recommendation).
**Notes:** Full 15-manifest coverage, zero exemptions; pre-stages the Phase-7b ChatRunner migration. Confirmed scheme: revisions get their own manifest (distinct agents); od_prototype = sole id-alias → prototype.

### Question 2 — placeholder mechanics

| Option | Description | Selected |
|--------|-------------|----------|
| Empty steps OK + chat compiles, engine skips (Recommended) | MAN-01 schema permits steps:[]; reverse_engineer = stub; chat loads+compiles but engine doesn't dispatch it; no new schema fields | ✓ |
| Explicit status/enabled marker | Add status: active\|stub\|external_runtime field; engine dispatches active only; more self-documenting, adds schema surface | |
| Require non-empty steps | Schema enforces non-empty; reverse_engineer needs a sentinel agent — not viable (no such agent, MAN-03 reference check fails) | |

**User's choice:** Empty steps OK + chat compiles, engine skips.
**Notes:** Coverage test = all 15 load+compile (zero exemptions); the 13 engine-dispatchable pipelines run from their compiled plan (no legacy fallback). reverse_engineer compiles to an empty plan; chat stays on ChatRunner.

---

## Claude's Discretion

- Route handler signatures / response models / auth deps for the new /api/runs + /api/workflows definitions routers (mirror existing workflows.py).
- Whether nested forward-field types (D-06) are stub-defined now or deferred (no Phase-4 behavior may key off an inert field).
- Plan-task granularity / split.
- Stub metadata wording for the reverse_engineer + chat manifests.
- New run-history router filename (runs.py recommended) + export-pptx path placement.

## Deferred Ideas

- @register/discover() self-registration + trust flags (user_allowed, owner allow-list) — Phase 8 [3] / CAP-02, CAP-03.
- Concrete capability impls + deleting L1–L13 — Phase 7 [2] / PARITY-*.
- Typed ArtifactGraph/ArtifactRef + persistence + deleting accumulated_outputs mirror — Phase 5 [1B] / ART-*, PERSIST-*, L15.
- ModelResolver / model policy (inert `model` fields) — Phase 6 [1C] / MODEL-*.
- GET /api/capabilities + new run-stream events + dynamic composer — Phase 8+ / API-02/03/06.
- Deprecated 308-redirect aliases for old run paths — only if an external API-key consumer is found (D-02 researcher directive).
