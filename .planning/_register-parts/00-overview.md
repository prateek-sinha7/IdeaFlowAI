## Project Overview & How To Use This Register

> **What this document is.** A single navigation + knowledge layer over `.planning/`. Read this BEFORE implementing a bug-fix or feature so you do not (a) write duplicate code that already exists as a registered capability, or (b) contradict a locked plan/phase decision or resurrect deliberately-deleted code. Every claim here points to where the real detail lives.
>
> **Source files this overview summarizes (all read in full):** `.planning/PROJECT.md`, `.planning/REQUIREMENTS.md`, `.planning/ROADMAP.md`, `.planning/STATE.md`, `.planning/config.json`.
> **Authoritative full specification:** `specs/003-workflow-engine-decoupling/plan.md` — nothing in it may be dropped; every requirement traces back to it.
> **Per-phase detail:** the 22 sections that follow (Phase 1…22), each summarizing one `.planning/phases/<NN-…>/` folder and pointing to the exact file + heading for any detail.

### 1. What This Project Is

**Workflow Engine Decoupling & Universal Workflow Runtime** — a brownfield, strangler/incremental refactor (Q39) of Flowin's `agents/execution_engine/engine.py`. It turns the prototype-/PPT-/revision-coupled `ExecutionEngine` into a small, **workflow-agnostic runtime kernel** driven by **declarative workflow manifests** that compile (thin, no-DSL) to a typed `CompiledWorkflow`/`ExecutionPlan`. Every capability once hardwired for `prototype` (per-task sub-agent loop, validation + fix-loop, context injection, deliverable resolution, clarify defaults) becomes a **declared, registered capability** any workflow can opt into. The `Workspace`/`RuntimeEnvironment` abstraction is designed now (local impl only) so ECS/containers plug in later as a backend swap, not an engine rewrite.

Audience: engineers building/operating Flowin's agent workflows, and (via the dynamic composer) users composing custom workflows from an allow-listed capability palette. Builds on spec `002-deepagents-migration` (the `deepagents` runtime this restructures). Branch: `feature/003-workflow-engine-decoupling`. Repo is GitLab `hexaware-uki/flowin`.

### 2. Core Value — SC-001 (the one test that must always hold)

**A brand-new custom workflow can replicate `prototype` by manifest + AGENT.md only — with ZERO engine edits.** If everything else fails, this must hold: the kernel knows no workflow by name; all power lives in registered, declared capabilities.
**Status: PROVEN** (Phase 7 gap-closure `test_sc001_nonprototype_task_loop` — a non-prototype `task_loop` workflow produces `app.py` from manifest+AGENT.md with zero engine edits). Re-proven for fan-out (Phase 11 `sample_fanout`) and waves (Phase 12 `sample_wave`). → detail in the Phase 7 / 11 / 12 sections.

### 3. Milestone & Phase Status (reconciled)

- **Milestone v1.0: COMPLETE on plans — 22/22 phases, 113/113 plans, requirements 117 v1 + new post-milestone families** (`STATE.md` 100%). Phases 1–12 were the planned milestone (**71 plans**, all 117 v1 requirements mapped 1:1, coverage 117/117); Phase 13 added 6 + Phase 14 added 4 + Phase 15 added 3 + Phases 16–17 added 7 + Phases 18–19 added 8 + Phases 20–21 added 5 + Phase 22 added 9 post-milestone plans. Verified offline; the full milestone-end live-Bedrock re-pass ran **2026-06-12** (`.planning/live-verification/REPORT-2026-06-12.md`; an earlier 2026-06-11 pass covered Phase 12); a 2026-06-13 deep root-cause investigation (clusters A–E) drove Phases 16–19; **Phases 20–21 (2026-06-14) realized the formerly-v2 WF-DB-01**; **Phase 22 (2026-06-15) cashed the SC-001 dividend at the UX layer** — surfaced all ~70 capabilities + user-compose/launch, wired the latent `model:`/`retry:`/`injects:` manifest keys, resolved the open decisions **N9 + N11**, and ran the consolidated **LIVE-01** deferral sweep. Status is `verifying`. → `ROADMAP.md` (Progress table), `STATE.md` (footer).
- **Phase 13 (Live Verification Gap Closure): COMPLETE (2026-06-12), 6/6 plans — verified PASSED.** Added AFTER v1.0 was marked complete, to close the product gaps (live findings **F1–F8**) found by a post-milestone **live-Bedrock** verification pass on real Haiku 4.5; **F1–F7 closed in code**, **F8** is an environment-only re-run deferral. → `.planning/live-verification/REPORT.md`, Phase 13 section.
  - *Review/security backlog CLEARED:* the `13-REVIEW.md` **Critical** (`approve_review` ownership/IDOR) **and all 7 Warnings (WR-01…WR-07)** are now **FIXED** (`13-REVIEW-FIX.md` `status: all_fixed`; `13-SECURITY.md` `threats_open: 0`, 17/17 closed). The one **deferred feature** Phase 13 left (the `run_revision` real revision loop) was **CLOSED by Phase 14**; the **end-of-milestone live-Bedrock re-pass ran 2026-06-12** (verified F1/F4/F5/SC4/F8 etc; surfaced new findings **LV-01/LV-02/LV-03** — **LV-02 closed by Phase 15**). The test-infra findings **LV-01/LV-03** (= ISS-002/ISS-003) and the terminal-state/reconnect issues (ISS-007/008/009/016/017) were **closed by Phases 16–17**; the **F4/F5 residuals** (ISS-004/005) + app_builder drift (ISS-006) got **durable structural fixes in Phase 19**; the **cluster-E UI issues** (ISS-021/014/019, + ISS-015 WONTFIX) were **closed by Phase 18**. *⚠ Remaining* (tracked in `.planning/ISSUES-REGISTER.md`): the **deferred live re-confirms** on the `default` Bedrock profile (a consolidated live + Playwright pass) — ISS-005/006 since live-confirmed, **ISS-004 offline-proven only** — plus any open UI-campaign items there. Milestone status is `verifying`. See the Phase 13 section §6/§7 before shipping.
- **Phase 14 (run_revision real revision loop, F2 end-to-end): COMPLETE (2026-06-12), 4/4 plans — verified; SC4 live-confirmed.** Closes the Phase-13 deferred feature: `run_revision` now dispatches the registry's real revision pipelines through `execute()` (a model runs) and persists the revised artifact with `derived_from` lineage; the Phase-3 echo stub (`_stamped_send`, fake `total_duration: 0.0`) is deleted (INV-12). Code review iter-1 (2 CR / 4 WR) → all fixed → iter-2 clean; `14-SECURITY.md` threats_open: 0. SC4 mechanics passed live 2026-06-12; the deck *content* was blocked by LV-02 (parent deliverable), closed by Phase 15. → Phase 14 section.
- **Phase 15 (Live-Pass Prompt Contract Closure): COMPLETE (2026-06-13), 3/3 plans — verified PASSED.** Closes the 2026-06-12 live re-pass's prompt-shaped findings — **LV-02** (the `od_ppt` deliverable returned the validator's QA narration instead of a real deck, breaking the od_ppt preview + revision chain) plus the **F4/F5** prompt residuals — by adding output contracts to **5 AGENT.md bodies + tests only, ZERO engine/capability edits (SC-001)**; the resolver-fallback alternative was rejected as INV-3-sensitive. SC5 live re-check CLOSED 2026-06-13 (a real-Haiku od_ppt run resolved an ~18.6k-char deck + a revised deck, ~$0.09). `15-SECURITY.md` 10/10 closed; review WR-01…04 all fixed. → Phase 15 section.
- **Phase 16 (Terminal-State Integrity & Reconnect Frame-Contract): COMPLETE (2026-06-13), 4/4 plans — verified PASSED.** Closes 6 issues from the 2026-06-13 deep root-cause investigation (clusters A+B): a runner-surfaced model/tool error now ends `pipeline_failed`/`status:degraded` (not an empty `pipeline_complete`) — ISS-016; a real `cancel_pipeline` delivers `pipeline_cancelled` on the live wire via a cooperative `cancel_event` so FE cards clear — ISS-007/002; the Preview shows a degraded/failed affordance — ISS-017; durable-replay frames carry the real `section` + the live-attach ack carries `live:true` — ISS-008/009. Engine + WebSocket + 1 FE affordance; **zero new tables/migrations, INV-3 5 goldens byte-identical, every branch keys on a generic event type (SC-001/INV-1)**. Review 0 CR / 3 WR / 4 IN → in-scope fixed; `16-VERIFICATION.md` passed 5/5. → Phase 16 section.
- **Phase 17 (Test-Infra & Verification-Gap Closure): COMPLETE (2026-06-13), 3/3 plans — verified 4/4; TEST-ONLY.** Closes cluster C of the deep investigation, **zero production code**: ISS-003 (the live token-delta test now compiles `clarify.mode=off` instead of a dead flag — no clarify-gate hang), ISS-010 (OTLP span export verified offline via an `InMemorySpanExporter`, DEFERRED→FIXED-by-test), ISS-011 (Phase-8 HITL live-tail tests SKIP-not-FAIL on SSO-token expiry). `17-VERIFICATION.md` passed 4/4; review 0 CR / 1 WR (fixed) / 2 IN; no `17-SECURITY.md` (test-only); goldens 10/10, lint 4/0. Live re-runs needing fresh AWS creds recorded as deferred. → Phase 17 section.
- **Phase 18 (Custom-Workflow UX Completeness): COMPLETE (2026-06-13), 5/5 plans — verified PASSED.** Closes cluster E of the deep investigation: a custom/unknown-type workflow now renders its declared deliverable via a **generic mimetype-dispatched FE renderer** (HTML→sandboxed iframe / md→markdown / zip→bundle) + Files row with **zero per-workflow FE code** (BE emits additive `deliverable_mimetype`/`deliverable_filename` on `pipeline_complete`, neutralized in `_VOLATILE_STRIP_KEYS`) — **ISS-021**; the orphaned/unrouted `WorkflowComposer.tsx` + `CapabilityPalette.tsx` are **deleted (INV-12)** and the per-agent model picker relocated into the live `AgentsPopup` (MODEL-03 now reachable) — **ISS-014**; WaveTreePanel fold fix (CSS-only) — **ISS-019**; the generic pipeline-type picker is **WONTFIX/by-design** (v2/WF-DB-01) — **ISS-015**. Review CR-01 (live `custom` rendered escaped HTML) fixed; `18-VERIFICATION.md` passed 5/5; visual/Playwright confirm deferred. → Phase 18 section.
- **Phase 19 (Prompt and Deliverable Adherence): COMPLETE (2026-06-13), 3/3 plans — verified PASSED.** Closes cluster D with **durable structural fixes** (not prompt-only) — superseding Phase 15's prompt contracts: a shared canonical `getDatabase` accessor literal across the app_builder producer/consumer prompts + offline grep pin (**ISS-006**); a new pure-stdlib `api_prefix` `Validator` wired as an **event-free `post_step`** (NOT a validation gate — would break the golden) flagging missing `/api/v1` into `validation_results` (**ISS-005**); the `_strip_fabricated_tool_xml` sanitizer extended to the streamed `agent_chunk` path with a chunk-straddle buffer for tool-less agents (**ISS-004**). INV-3 5 goldens byte-identical; lint 4/0; zero new tables. ISS-005/006 since live-confirmed; ISS-004 offline-proven only (live re-confirm deferred). → Phase 19 section.
- **v2 (deferred, intentionally unmapped):** ECS-01/02 (remote runtime), SCHED-01 (CP-SAT), MERGE-01 (single-file fragment merge), GIT-01 (PR/commit push). *(**WF-DB-01** DB-backed user workflows — formerly v2 — has since been **realized by Phases 20–21**.)* → `REQUIREMENTS.md` (## v2 Requirements / ## Out of Scope).

### 4. Architecture & Hard Constraints (apply to EVERY phase — do not violate)

- **Tech stack:** Python · FastAPI · PostgreSQL · LangGraph checkpointer — *extend, don't replace*.
- **INV-13 (runtime mandate):** every agent runs on LangChain `deepagents` — canonical `from deepagents import create_deep_agent` (PyPI `deepagents==0.6.7`); adapter id `langchain_deepagents`. No hand-rolled deep agent, no local `deepagents`/`langchain_deepagents` module, no re-implemented agent loop. **`create_deep_agent` is called ONLY inside the allow-listed `deep_agent_runner.py`.** Enforced by a banned-pattern CI gate (R15).
- **Ports & Adapters (hexagonal):** the kernel depends only on capability **ports**; concrete impls self-register into the `CapabilityRegistry` via `@register(kind,name)`. Adding a capability = add a module + register — **no kernel edit**. Enforced by import-linter (§31): 4 forbidden contracts (`agents.capabilities ↛ agents.execution_engine`, `agents.runtime ↛ [agents.execution_engine, app]`, kernel ↛ `app`, etc.); steady state is **lint-imports 4/0**.
- **Compiler is thin, no DSL (INV-5):** manifests are data; control flow lives inside strategies.
- **Persistence — additive migrations only (Q3):** every new table carries `owner_id` + `workspace_id`. Alembic chain: 0014 (artifacts/workspaces/run_events/run_capabilities) → 0015 (drop legacy `WorkflowArtifact`) → 0016 (validation_results/gate_events/hook_runs) → 0017 (repositories) → 0018 (exec_runs) → 0019 (subagent_runs) → 0020 (wave_runs) → **0021** (Phase 21 — user-authored saved workflows: +3 nullable cols `base_pipeline_type`/`model_overrides`/`description` on the **reused** `workflows` table, NOT a new table; the first migration since the planned milestone) → **0022** (Phase 22 — UXFIX-02: additive `deliverable_mimetype`/`deliverable_filename` on `WorkflowRun` for faithful history-reopen of binary deliverables).
- **Security defaults OFF:** `exec`/`network`/`secrets`/`spawn_subagents` default OFF. Code-exec lives behind the `security`+`approval` gates (N3 resolved Phase 10 — `10-SPEC.md` is the decision record); `network`/`secrets` remain gated-off; untrusted end-user exec stays out of scope.
- **INV-3 / INV-12 — no dual implementations:** a phase that adds an abstraction without deleting the code it supersedes is **not done** (move → rewire call-sites → delete; deletion is an exit gate, ratcheted by banned-pattern greps). The only sanctioned temporary duplication was the `accumulated_outputs` mirror (removed Phase 5).
- **Backward-compat (INV-3):** existing `prototype`/`od_*`/PPT/code-gen behavior stays deterministic-byte-identical + semantic-event-parity, proven by characterization tests (Phase 1). The single sanctioned non-byte-identical change is the Phase 3 token-trim (measured ≥50% reduction, semantic parity held).

**Global invariants (success constraints on every phase):** INV-1 kernel knows no workflow by name (zero `if pipeline_type ==` / `spec.id ==` branches) · INV-2 no per-run state on the singleton (per-run `ExecutionContext`; immutable kernel) · INV-3 semantic event parity, deliverables byte-identical where deterministic · INV-12 move-don't-copy · INV-13 LangChain `deepagents` only.

### 5. The Leak Map (what the refactor had to dissolve)

From plan §4: **16 verified couplings L1–L16** in `engine.py` (literal name frozensets, `_resolve_final_output`, carousel sanitize, revision seeding, skip-planner, clarify defaults, build-loop dispatch, HTML readback, build-loop internals, context injection, dead skeleton, singleton per-run state, untyped `accumulated_outputs`, unchecked parent seeding) and **5 factory leaks F1–F5** (inline prompt order, closed tool switch, inline skills/hooks, constitution no-op R12, hardcoded `create_deep_agent`). **D1** (dead `_handle_revision`) was **VOIDED** — it is LIVE (the `run_revision` PPT-revision handler at `app/api/websocket.py:625`). By milestone end L1–L16 + F1–F5 are resolved/deleted or kept as documented **live survivors** (CHECK ledger rows). The operational mirror with status + deleting commit SHA is `specs/003-…/migration-ledger.md`, asserted by `tests/test_migration_ledger.py`.

### 6. The 22 Phases (strangler order, strictly sequential)

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
| 13 | Live Verification Gap Closure | 6/6 | ✅ 06-12 (verified; review backlog fixed + security-cleared) | Closed post-milestone live-Bedrock findings F1–F8 (declared-gate event streaming, run_revision deliverable contract, pipeline_failed semantics, tool-XML prompt hygiene, app_builder prompt re-templating, sample_fanout deliverable, test-infra repairs) |
| 14 | run_revision Real Revision Loop (F2 end-to-end) | 4/4 | ✅ 06-12 (verified; SC4 live-confirmed) | Real revision dispatch through `execute()` + `derived_from` lineage; deletes the Phase-3 echo stub — closes the Phase-13 deferred feature |
| 15 | Live-Pass Prompt Contract Closure | 3/3 | ✅ 06-13 (verified; SC5 live-confirmed) | Output contracts on 5 AGENT.md bodies (od-ppt-validator deck re-emit = LV-02, sdlc-governance anti-fabrication, infra `/api/v1`) + test pins; zero engine edits |
| 16 | Terminal-State Integrity & Reconnect Frame-Contract | 4/4 | ✅ 06-13 (verified) | `pipeline_failed`/degraded terminals, cooperative cancel delivers `pipeline_cancelled` live, degraded Preview affordance, replay-frame contract; zero new tables (ISS-016/017/007/002/008/009) |
| 17 | Test-Infra & Verification-Gap Closure | 3/3 | ✅ 06-13 (verified 4/4, test-only) | Harness fixes: clarify-off in `_drive_live`, OTLP in-memory span test, HITL SKIP-on-cred-expiry; zero production code (ISS-003/010/011) |
| 18 | Custom-Workflow UX Completeness | 5/5 | ✅ 06-13 (verified 5/5) | Generic mimetype-dispatched deliverable renderer + Files row (zero per-workflow FE code), deleted orphaned composer, model-picker relocated (MODEL-03 reachable), wave-panel fold fix (ISS-021/014/019; ISS-015 WONTFIX) |
| 19 | Prompt & Deliverable Adherence | 3/3 | ✅ 06-13 (verified 4/4) | Durable structural fixes: shared `getDatabase` literal, event-free `api_prefix` post_step validator, streamed-chunk tool-XML sanitizer (ISS-006/005/004) |
| 20 | Workflow Catalog — Data-Driven Browse-and-Launch | 2/2 | ✅ 06-14 (verified 5/5) | Data-driven catalog off `GET /api/workflows` + additive `user_launchable`/display manifest flags; realizes WF-DB-01 browse/launch + reverses ISS-015 WONTFIX; zero new tables |
| 21 | Saved Workflows — User-Authored, Named, Persisted | 3/3 | ✅ 06-14 (verified 5/5) | DB-backed saved workflows (`source="user"`) via migration 0021 on the reused `workflows` table + `/api/user-workflows` CRUD; removes dead `_persist_workflow_definition` (INV-12); completes WF-DB-01/Q5 |
| 22 | Capability Surfacing & User Empowerment — Universal Runtime UX | 9/9 | ✅ 06-15 (verified 17/17) | Live `/api/capabilities` palette (all ~70 caps, trust-gated) + user compose/launch through the run path; wires `model:`/`retry:`/`injects:` manifest keys; resolves N9 (keep-by-default) + N11 (premium open); migration 0022; LIVE-01 deferral sweep (SURF/EMP/WIRE/UXFIX/DECIDE/LIVE) |

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
- **(no new REQ-IDs; completes live finding F2 end-to-end)** → Phase 14 (run_revision real revision loop)
- **(no new REQ-IDs; closes live re-pass findings LV-02 + F4/F5 residuals)** → Phase 15 (live-pass prompt contract closure)
- **(no new REQ-IDs; closes deep-investigation clusters A+B — ISS-016/017/007/002/008/009)** → Phase 16 (terminal-state integrity & reconnect frame-contract)
- **(no new REQ-IDs; closes deep-investigation cluster C — ISS-003/010/011, test-infra only)** → Phase 17 (test-infra & verification-gap closure)
- **(no new REQ-IDs; closes deep-investigation cluster E — ISS-021/014/019/015; delivers MODEL-03's FE half)** → Phase 18 (custom-workflow UX completeness)
- **(no new REQ-IDs; closes deep-investigation cluster D — ISS-006/005/004, durable structural)** → Phase 19 (prompt & deliverable adherence)
- **(no new REQ-IDs; realizes WF-DB-01 browse/launch half + closes ISS-015)** → Phase 20 (workflow catalog — data-driven browse-and-launch)
- **(no new REQ-IDs; completes WF-DB-01 / realizes Q5 — DB-backed user-authored workflows)** → Phase 21 (saved workflows)
- **SURF-01..03, EMP-01..04, WIRE-01..03, UXFIX-01..04, DECIDE-01/02, LIVE-01** (NEW post-milestone families) → Phase 22 (capability surfacing & user empowerment)

Per-phase requirement counts (=117): P1=11 · P2=5 · P3=3 · P4=6 · P5=14 · P6=5 · P7=9 · P8=29 · P9=14 · P10=2 · P11=13 · P12=6. → `REQUIREMENTS.md` (## Traceability).

### 8. Key Locked Decisions (do NOT re-open without a decision record)

- Unify vocabulary on `workflow`; `pipeline_type` kept only as a temporary id-alias (Q1).
- Engineer-registered capabilities + user-composable manifests; per-capability `user_allowed` trust boundary + owner allow-list (Q2 / CAP-03).
- File-backed manifests now; DB-backed user workflows later (Q5) — **now realized**: Phase 21 added DB-backed user-authored saved workflows on the reused `workflows` table (`source="user"`, migration 0021); file-backed built-in manifests remain the source for engineer-authored workflows.
- `ExecutionStrategy` registry: `single_shot` / `task_loop` / `fanout_batch` / `wave_scheduler` (Q8).
- Canonical `Task` schema + parser adapters; `heading_tasks` + `json_tasks` parsers (Q11).
- Engine owns fan-out via the `spawn_subagents` request-emitter tool (Q13 / INV-7); the library `task` tool stays excluded; `spawn_subagents` is `user_allowed=False`.
- Deterministic topo wave-builder first; CP-SAT seam left (Q31/Q32).
- Per-sub-agent subdirs first; git worktrees for brownfield (Q34).
- Internal P0–P3 severities → external CRITICAL/HIGH/MEDIUM/LOW via one `map_severity` (Q24).
- User per-agent model selection at the top of the resolution order (A12); global default stays Haiku.
- **Resolved decision records:** N2 isolation MVP (Phase 9 `LocalSandboxRuntime`) · N3 exec threat-model (Phase 10 — `10-SPEC.md`) · N5/N7 repo deliverable shape (Phase 9 diff-only `repo_diff`) · N6/N10 RepoIndex (Phase 9 grep-default + opt-in tree-sitter).
- **Still-OPEN decision records (confirm before any related future work):** **N4** git hosting (GitHub vs GitLab; repo is GitLab) · **N8** long-job substrate. *(**N9** artifact retention + **N11** model/premium policy — formerly open — were **resolved in Phase 22**: N9 → **keep-by-default** (run_ttl/`days:N` opt-in overrides), N11 → **premium open to all tiers** (global default Haiku + fallback chain; picker tier-filter dropped). ⚠ N9 follow-up: the code/config default still reads `run_ttl` in ~4 sites — see Phase 22 §7.)* → `STATE.md` (Blockers/Concerns), `PROJECT.md` (Key Decisions).

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

The 22 sections that follow summarize each folder and point to the exact file + heading for any detail.
