## Project Overview & How To Use This Register

> **What this document is.** A single navigation + knowledge layer over `.planning/`. Read this BEFORE implementing a bug-fix or feature so you do not (a) write duplicate code that already exists as a registered capability, or (b) contradict a locked plan/phase decision or resurrect deliberately-deleted code. Every claim here points to where the real detail lives.
>
> **Source files this overview summarizes (all read in full):** `.planning/PROJECT.md`, `.planning/REQUIREMENTS.md`, `.planning/ROADMAP.md`, `.planning/STATE.md`, `.planning/config.json`.
> **Authoritative full specification:** `specs/003-workflow-engine-decoupling/plan.md` — nothing in it may be dropped; every requirement traces back to it.
> **Per-phase detail:** the 13 sections that follow (Phase 1…13), each summarizing one `.planning/phases/<NN-…>/` folder and pointing to the exact file + heading for any detail.

### 1. What This Project Is

**Workflow Engine Decoupling & Universal Workflow Runtime** — a brownfield, strangler/incremental refactor (Q39) of Flowin's `agents/execution_engine/engine.py`. It turns the prototype-/PPT-/revision-coupled `ExecutionEngine` into a small, **workflow-agnostic runtime kernel** driven by **declarative workflow manifests** that compile (thin, no-DSL) to a typed `CompiledWorkflow`/`ExecutionPlan`. Every capability once hardwired for `prototype` (per-task sub-agent loop, validation + fix-loop, context injection, deliverable resolution, clarify defaults) becomes a **declared, registered capability** any workflow can opt into. The `Workspace`/`RuntimeEnvironment` abstraction is designed now (local impl only) so ECS/containers plug in later as a backend swap, not an engine rewrite.

Audience: engineers building/operating Flowin's agent workflows, and (via the dynamic composer) users composing custom workflows from an allow-listed capability palette. Builds on spec `002-deepagents-migration` (the `deepagents` runtime this restructures). Branch: `feature/003-workflow-engine-decoupling`. Repo is GitLab `hexaware-uki/flowin`.

### 2. Core Value — SC-001 (the one test that must always hold)

**A brand-new custom workflow can replicate `prototype` by manifest + AGENT.md only — with ZERO engine edits.** If everything else fails, this must hold: the kernel knows no workflow by name; all power lives in registered, declared capabilities.
**Status: PROVEN** (Phase 7 gap-closure `test_sc001_nonprototype_task_loop` — a non-prototype `task_loop` workflow produces `app.py` from manifest+AGENT.md with zero engine edits). Re-proven for fan-out (Phase 11 `sample_fanout`) and waves (Phase 12 `sample_wave`). → detail in the Phase 7 / 11 / 12 sections.

### 3. Milestone & Phase Status (reconciled)

- **Milestone v1.0: COMPLETE on plans — 13/13 phases, 77/77 plans, 117/117 requirements** (`STATE.md` 100%). Phases 1–12 were the planned milestone (**71 plans**, all 117 v1 requirements mapped 1:1, coverage 117/117); Phase 13 added 6 post-milestone gap-closure plans. Verified offline + a milestone-end live re-pass on 2026-06-11. → `ROADMAP.md` (Progress table), `STATE.md` (footer).
- **Phase 13 (Live Verification Gap Closure): COMPLETE (2026-06-12), 6/6 plans — verified PASSED.** Added AFTER v1.0 was marked complete, to close the product gaps (live findings **F1–F8**) found by a post-milestone **live-Bedrock** verification pass on real Haiku 4.5; **F1–F7 closed in code**, **F8** is an environment-only re-run deferral. → `.planning/live-verification/REPORT.md`, Phase 13 section.
  - *⚠ Open carry-forward:* `13-REVIEW.md` raised one **Critical** (an `approve_review` ownership/IDOR gap surfaced by F1) that was **not fixed in-phase**; the review post-dates execution (14 findings: 1 CR / 7 WR / 6 IN, none fixed in-phase). Milestone status is `verifying`, gated on resolving that finding + an end-of-milestone live re-pass (live re-verification of F1/F4/F5 on real Haiku deferred per project convention). See the Phase 13 section §6/§7 before shipping.
- **v2 (deferred, intentionally unmapped):** ECS-01/02 (remote runtime), SCHED-01 (CP-SAT), MERGE-01 (single-file fragment merge), GIT-01 (PR/commit push), WF-DB-01 (DB-backed user workflows). → `REQUIREMENTS.md` (## v2 Requirements / ## Out of Scope).

### 4. Architecture & Hard Constraints (apply to EVERY phase — do not violate)

- **Tech stack:** Python · FastAPI · PostgreSQL · LangGraph checkpointer — *extend, don't replace*.
- **INV-13 (runtime mandate):** every agent runs on LangChain `deepagents` — canonical `from deepagents import create_deep_agent` (PyPI `deepagents==0.6.7`); adapter id `langchain_deepagents`. No hand-rolled deep agent, no local `deepagents`/`langchain_deepagents` module, no re-implemented agent loop. **`create_deep_agent` is called ONLY inside the allow-listed `deep_agent_runner.py`.** Enforced by a banned-pattern CI gate (R15).
- **Ports & Adapters (hexagonal):** the kernel depends only on capability **ports**; concrete impls self-register into the `CapabilityRegistry` via `@register(kind,name)`. Adding a capability = add a module + register — **no kernel edit**. Enforced by import-linter (§31): 4 forbidden contracts (`agents.capabilities ↛ agents.execution_engine`, `agents.runtime ↛ [agents.execution_engine, app]`, kernel ↛ `app`, etc.); steady state is **lint-imports 4/0**.
- **Compiler is thin, no DSL (INV-5):** manifests are data; control flow lives inside strategies.
- **Persistence — additive migrations only (Q3):** every new table carries `owner_id` + `workspace_id`. Alembic chain: 0014 (artifacts/workspaces/run_events/run_capabilities) → 0015 (drop legacy `WorkflowArtifact`) → 0016 (validation_results/gate_events/hook_runs) → 0017 (repositories) → 0018 (exec_runs) → 0019 (subagent_runs) → 0020 (wave_runs).
- **Security defaults OFF:** `exec`/`network`/`secrets`/`spawn_subagents` default OFF. Code-exec lives behind the `security`+`approval` gates (N3 resolved Phase 10 — `10-SPEC.md` is the decision record); `network`/`secrets` remain gated-off; untrusted end-user exec stays out of scope.
- **INV-3 / INV-12 — no dual implementations:** a phase that adds an abstraction without deleting the code it supersedes is **not done** (move → rewire call-sites → delete; deletion is an exit gate, ratcheted by banned-pattern greps). The only sanctioned temporary duplication was the `accumulated_outputs` mirror (removed Phase 5).
- **Backward-compat (INV-3):** existing `prototype`/`od_*`/PPT/code-gen behavior stays deterministic-byte-identical + semantic-event-parity, proven by characterization tests (Phase 1). The single sanctioned non-byte-identical change is the Phase 3 token-trim (measured ≥50% reduction, semantic parity held).

**Global invariants (success constraints on every phase):** INV-1 kernel knows no workflow by name (zero `if pipeline_type ==` / `spec.id ==` branches) · INV-2 no per-run state on the singleton (per-run `ExecutionContext`; immutable kernel) · INV-3 semantic event parity, deliverables byte-identical where deterministic · INV-12 move-don't-copy · INV-13 LangChain `deepagents` only.

### 5. The Leak Map (what the refactor had to dissolve)

From plan §4: **16 verified couplings L1–L16** in `engine.py` (literal name frozensets, `_resolve_final_output`, carousel sanitize, revision seeding, skip-planner, clarify defaults, build-loop dispatch, HTML readback, build-loop internals, context injection, dead skeleton, singleton per-run state, untyped `accumulated_outputs`, unchecked parent seeding) and **5 factory leaks F1–F5** (inline prompt order, closed tool switch, inline skills/hooks, constitution no-op R12, hardcoded `create_deep_agent`). **D1** (dead `_handle_revision`) was **VOIDED** — it is LIVE (the `run_revision` PPT-revision handler at `app/api/websocket.py:625`). By milestone end L1–L16 + F1–F5 are resolved/deleted or kept as documented **live survivors** (CHECK ledger rows). The operational mirror with status + deleting commit SHA is `specs/003-…/migration-ledger.md`, asserted by `tests/test_migration_ledger.py`.

### 6. The 13 Phases (strangler order, strictly sequential)

Plan sub-phases (0A/0B/0C, 1A/1B/1C, 4A/4B) map 1:1 to GSD integer phases 1–12; each phase name carries its plan id `[0A]…[6]` tracing to plan §25. Phase 13 is a post-milestone addition (no plan-id).

| Phase | Name [plan-id] | Plans | Status | One-line outcome |
|-------|----------------|-------|--------|------------------|
| 1 | Safety Net + Deletion Guard [0A] | 4/4 | ✅ 06-06 | Characterization snapshots + ledger/import-linter/banned-pattern CI gates; no behavior change |
| 2 | ExecutionContext + Ownership [0B] | 3/3 | ✅ 06-07 | All `self._*` run state → per-run `ExecutionContext`; explicit parent-run ownership check |
| 3 | Token-Trim (measured change) [0C] | 2/2 | ✅ 06-07 | Wire dead `_extract_html_skeleton` as build compaction — the one sanctioned INV-3 exception |
| 4 | Manifest + Compiler [1A] | 5/5 | ✅ 06-07 | File-backed manifests → thin compiler → typed `CompiledWorkflow`; pipelines run from compiled plans |
| 5 | Typed Artifacts + Persistence + Ownership [1B] | 7/7 | ✅ 06-08 | `ArtifactGraph`/`ArtifactRef` + schema (§18); delete the legacy mirror; authz denial tests |
| 6 | Model Policy [1C] | 5/5 | ✅ 06-08 | `ModelResolver` (precedence + fallback + cost_class) + `ModelCatalog` + per-agent overrides |
| 7 | Prototype as Manifest — Parity Proof (SC-001) [2] | 11/11 | ✅ 06-09 | Strategies/resolvers/providers/parsers/compaction; delete L1–L13; **SC-001 PROVEN** |
| 8 | Capabilities Hardened — Registry, Gates, Tool Perms, Runtime [3] | 8/8 | ✅ 06-09 | `CapabilityRegistry` + trust; gate registry; least-privilege; `AgentRuntimeAdapter`; delete F1–F5 |
| 9 | Local Workspace Runtime + Repo Workflows (no exec) [4A] | 6/6 | ✅ 06-10 | `RuntimeEnvironment` + `LocalSandboxRuntime`; repo inventory/index/context-pack + `repo_diff`; MCP client + integrations |
| 10 | Safe Local Exec (gated on N3) [4B] | 5/5 | ✅ 06-10 | Constrained `exec` behind `security` gate + `ExecutionPolicy`; compile/test/lint validators |
| 11 | Engine-Owned Fan-Out + Merge [5] | 5/5 | ✅ 06-11 | `spawn_subagents` + kernel `run_fanout`; isolation + merge-conflict flow; `BudgetManager`; subagent persistence |
| 12 | Wave Scheduler + Durable Resume [6] | 10/10 | ✅ 06-11 | Topo wave scheduler; `wave_runs`; resume mid-wave; prototype stays sequential |
| 13 | Live Verification Gap Closure | 6/6 | ✅ 06-12 (verified; ⚠ 1 Critical open) | Closed post-milestone live-Bedrock findings F1–F8 (declared-gate event streaming, run_revision deliverable contract, pipeline_failed semantics, tool-XML prompt hygiene, app_builder prompt re-templating, sample_fanout deliverable, test-infra repairs) |

> **Deferred (plan Phase 7, OUT OF SCOPE this milestone):** ECS/EC2 runtime behind the unchanged `RuntimeEnvironment` port — a separate spec (§27); tracked as v2 (ECS-01/02).

### 7. Requirement Families (REQ-ID prefixes → owning phase)

- **SAFE-01..07, DEL-01..04** → Phase 1 (safety net, deletion ledger discipline)
- **CTX-01..05** → Phase 2 (ExecutionContext, ownership)
- **COMPACT-01..03** → Phase 3 (token-trim)
- **MAN-01..05, API-01** → Phase 4 (manifests/compiler)
- **ART-01..04, PERSIST-01..03, AUTHZ-01..04, CAPRUN-01, API-04/05** → Phase 5 (typed artifacts, persistence, ownership)
- **MODEL-01..05** → Phase 6 (model policy)
- **PARITY-01..09** → Phase 7 (prototype as manifest; SC-001 proof)
- **CAP-01..03, GATE-01..03, TOOLPERM-01..03, VALID-01..05, AGENTRT-01..06, SKILL-01, HOOK-01..04, OBS-02, API-02/03/06** → Phase 8 (capabilities hardened)
- **RUNTIME-01..03, REPO-01..05, MCP-01..04, INTEG-01..02** → Phase 9 (local runtime + repo + MCP)
- **EXEC-01..02** → Phase 10 (safe local exec)
- **FANOUT-01..11, OBS-01, RESUME-01** → Phase 11 (fan-out + merge)
- **WAVE-01..03, RESUME-02..04** → Phase 12 (wave scheduler + durable resume)
- **(no new REQ-IDs; closes findings F1–F7)** → Phase 13 (live-verification gap closure)

Per-phase requirement counts (=117): P1=11 · P2=5 · P3=3 · P4=6 · P5=14 · P6=5 · P7=9 · P8=29 · P9=14 · P10=2 · P11=13 · P12=6. → `REQUIREMENTS.md` (## Traceability).

### 8. Key Locked Decisions (do NOT re-open without a decision record)

- Unify vocabulary on `workflow`; `pipeline_type` kept only as a temporary id-alias (Q1).
- Engineer-registered capabilities + user-composable manifests; per-capability `user_allowed` trust boundary + owner allow-list (Q2 / CAP-03).
- File-backed manifests now; DB-backed user workflows later (Q5).
- `ExecutionStrategy` registry: `single_shot` / `task_loop` / `fanout_batch` / `wave_scheduler` (Q8).
- Canonical `Task` schema + parser adapters; `heading_tasks` + `json_tasks` parsers (Q11).
- Engine owns fan-out via the `spawn_subagents` request-emitter tool (Q13 / INV-7); the library `task` tool stays excluded; `spawn_subagents` is `user_allowed=False`.
- Deterministic topo wave-builder first; CP-SAT seam left (Q31/Q32).
- Per-sub-agent subdirs first; git worktrees for brownfield (Q34).
- Internal P0–P3 severities → external CRITICAL/HIGH/MEDIUM/LOW via one `map_severity` (Q24).
- User per-agent model selection at the top of the resolution order (A12); global default stays Haiku.
- **Resolved decision records:** N2 isolation MVP (Phase 9 `LocalSandboxRuntime`) · N3 exec threat-model (Phase 10 — `10-SPEC.md`) · N5/N7 repo deliverable shape (Phase 9 diff-only `repo_diff`) · N6/N10 RepoIndex (Phase 9 grep-default + opt-in tree-sitter).
- **Still-OPEN decision records (confirm before any related future work):** **N4** git hosting (GitHub vs GitLab; repo is GitLab) · **N8** long-job substrate · **N9** artifact retention default (run_ttl vs keep) · **N11** model default/premium policy. → `STATE.md` (Blockers/Concerns), `PROJECT.md` (Key Decisions).

### 9. Glossary of Recurring Tags

- **L#** = leak in `engine.py` (§5 leak map). **F#** = factory leak. **D#** = plan decision/dead-code item; **D-0x** = a phase-local design decision. **Q#** = locked decision. **N#** = open decision record. **A#** = answered/locked decision. **R#** = risk. **INV-#** = global invariant. **§#** = section of `plan.md`. **Tier#** = validator tier.
- **CR-xx / WR-xx / IN-xx** = code-review Critical / Warning / Info findings (per-phase `NN-REVIEW*.md`).
- **_KNOWN N→M** = the capability-registry name counter, growing monotonically as capabilities land (final ≈ 61 declared capability names by Phase 12).
- **migration 00NN** = an Alembic revision. **SC-001** = the core-value zero-engine-edit proof.

### 10. Per-Phase File Convention (where detail lives in every phase folder)

Each `.planning/phases/<NN-…>/` folder contains:
- `NN-NN-PLAN.md` + `NN-NN-SUMMARY.md` — one pair per plan (planned vs built).
- `NN-CONTEXT.md` — phase entry context. `NN-DISCUSSION-LOG.md` — Q&A/decisions. `NN-PATTERNS.md` — reusable patterns mapped to analogs.
- `NN-SPEC.md` (some) — scoped contract. `NN-RESEARCH.md` (some) — pre-plan research.
- `NN-REVIEW.md` / `NN-REVIEW-FIX.md` (+ `.iter2/.iter3`) — code-review findings + fixes.
- `NN-SECURITY.md` (some) — threat model + mitigations. `NN-VALIDATION.md` (some) — Nyquist/test coverage.
- `NN-VERIFICATION.md` — goal-backward verification verdict. `NN-UAT.md` (some) — user-acceptance evidence. `deferred-items.md` (some) — out-of-scope carry-forward.

The 13 sections that follow summarize each folder and point to the exact file + heading for any detail.
