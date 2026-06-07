# Phase 5: Typed Artifacts + Persistence + Ownership [1B] - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-07
**Phase:** 05-typed-artifacts-persistence-ownership-1b
**Areas discussed:** Artifact storage model, Migration shape + drop order, Scoped-query helper, API + event wiring (all presented; user dismissed per-area discussion → all locked to plan-grounded recommendations)

---

## Meta-gate: discuss vs lock-all

| Option | Description | Selected |
|--------|-------------|----------|
| Lock all to recommendations | Lock all four HOW forks to the plan.md-grounded recommendation, write CONTEXT.md, proceed to planning (mirrors Phases 2 & 4) | ✓ |
| Let me pick areas | Re-show the four areas to select which to deep-dive | |

**User's choice:** Lock all to recommendations (after dismissing the initial 4-area multiSelect).
**Notes:** Consistent with the standing plan-ingestion preference ("when a full plan/spec exists, copy it faithfully; skip interactive discovery/approval") and the SPEC's 0.14 ambiguity (WHAT fully locked). The four areas were still presented with concrete forks + code/prior-decision annotations before the lock.

---

## Artifact storage model (SPEC: "artifact package layout")

| Option | Description | Selected |
|--------|-------------|----------|
| Inline content column | `artifact_refs` keeps an inline `content` Text column + records `content_hash` + `location`; self-contained, survives the 48h sandbox TTL, helper stays pure-DB | ✓ (recommendation) |
| Location-pointer only | Store `location` + `content_hash` only; content re-read from the RunSandbox/disk | |
| Hybrid | Small inline, large by-pointer | |

**User's choice:** Locked to recommendation (inline content) — CONTEXT.md D-01/D-02.
**Notes:** Faithful swap of the inline-Text thin store being deleted; avoids TTL/runtime coupling (Workspace runtime is Phase 9); package layout per plan §32 (`agents/artifacts/`, `app/models/artifact_ref.py`).

---

## Migration shape + drop order (SPEC: "migration shape")

| Option | Description | Selected |
|--------|-------------|----------|
| Split chain | `0014` additive (tables + `workflow_runs` extend + default-workspace backfill); `0015` drops `workflow_artifacts` last, after read-cutover + parity | ✓ (recommendation) |
| Single 0014 | All add + drop in one migration; cutover gated in code | |
| You decide | Planner's call | |

**User's choice:** Locked to recommendation (split chain) — CONTEXT.md D-03/D-04/D-05.
**Notes:** Honors PERSIST-02's dual-write→migrate→delete ordering; isolates the one sanctioned destructive change; default-workspace backfill so historical runs get a real `workspace_id`. Flip ledger L15 ☑ + add a thin-store deletion gate.

---

## Scoped-query helper (SPEC: "scoped-helper API")

| Option | Description | Selected |
|--------|-------------|----------|
| `agents/authz.py` scoped store object | Relocate Phase 2's pure `assert_owns` up + grow into a real-lookup default-deny store helper (per §32); async; cross-owner → 404 | ✓ (recommendation) |
| Standalone scoped functions | Free functions per read | |
| You decide | Planner's call | |

**User's choice:** Locked to recommendation — CONTEXT.md D-06/D-07/D-08/D-09.
**Notes:** The D-06 mechanical move Phase 2 sited the helper for; `owner_id = user_id or anon:<session_id>` (DB principal) while RunSandbox disk keying stays `user_id or "anon"` (byte-identity guard).

---

## API + event wiring (SPEC: "endpoint serialization")

| Option | Description | Selected |
|--------|-------------|----------|
| Nested tree + reuse engine seq | `/artifacts` nested lineage tree; `/events` reuses the engine's existing per-run `seq` via a durable sink at the emit path | ✓ (recommendation) |
| Flat nodes+edges / fresh DB seq | Client assembles the tree; DB-side `MAX(seq)+1` independent counter | |

**User's choice:** Locked to recommendation — CONTEXT.md D-10/D-11/D-12.
**Notes:** Reusing the engine's seq preserves the SAFE-03 contiguity contract + live-stream/replay parity; `run_capabilities` row with `runtime=langchain_deepagents`.

---

## Claude's Discretion

- `ArtifactGraph`/`ArtifactRef` field names/order + dataclass↔row mapping location.
- Default-workspace backfill as a data step in `0014` vs a tiny `0014b`.
- Plan-task granularity across the D-13 cutover sequence.
- `?include=content` content-fetch shape for API-04.
- `run_capabilities` insert-at-start vs upsert-at-completion.
- `async def` route signatures / response models / auth deps for the two new endpoints.

## Deferred Ideas

- Retention sweep/janitor (P9); `RuntimeEnvironment`/`Workspace` runtime + `LocalSandboxRuntime` (P9); `repositories` (P9); `subagent_runs` (P11); `wave_runs` (P12); `validation_results`/`gate_events`/`hook_runs` (P8).
- `model_overrides` population (P6); `budget_snapshot_json` population (P11) — columns land additively now.
- Content dedup/replay-reuse on hash (P12); `GET /api/runs/{id}/diff` + new event types (P9/their phases).
- DB-authored user workflows (v2); deleting L1–L13 + `engine.py`→`kernel.py` split (P7).
