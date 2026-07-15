# Roadmap: Workflow Engine Decoupling & Universal Workflow Runtime

## Overview

A strangler/incremental migration (Q39) that turns the prototype-coupled `ExecutionEngine` into a workflow-agnostic kernel driven by declarative manifests. Each phase is independently shippable and **keeps prototype working throughout** — abstractions are introduced behind existing behavior, prototype is migrated to declarations, then hardcoded leaks are deleted. The journey: lock behavior with characterization tests → lift per-run state into `ExecutionContext` → trim tokens → introduce manifests/compiler → typed artifacts + persistence + ownership → model policy → **prove parity (SC-001) by re-expressing prototype as a manifest and deleting L1–L12** → harden the capability registry, gates, tool-permissions, runtime adapter (delete F1–F5) → local Workspace runtime + repo workflows → safe gated exec → engine-owned fan-out + merge → wave scheduler + durable resume. ECS/EC2 (plan Phase 7) is deferred to a separate spec.

The plan sub-phases (0A/0B/0C, 1A/1B/1C, 4A/4B) are mapped to sequential GSD phases 1–12; each phase name carries its plan id `[0A]…[6]` so it traces directly to `specs/003-workflow-engine-decoupling/plan.md §25`.

**Global invariants (success constraints on every phase):** INV-1 (kernel knows no workflow by name) · INV-2 (no per-run state on the singleton) · INV-3 (semantic event parity; deliverables byte-identical where deterministic) · INV-12 (move-don't-copy; deletion is an exit gate) · INV-13 (LangChain `deepagents` only — never hand-rolled).

## Phases

**Phase Numbering:** Integer phases map 1:1 to the plan's §25 sub-phases. Strangler order is strictly sequential — each phase depends on the prior.

- [x] **Phase 1: Safety Net + Deletion Guard [0A]** - Characterization snapshots + ledger/import-linter/banned-pattern CI gates; no behavior change (completed 2026-06-06)
- [x] **Phase 2: ExecutionContext + Ownership [0B]** - Lift all `self._*` run state into a per-run `ExecutionContext`; explicit parent-run ownership check; no behavior change (completed 2026-06-07)
- [x] **Phase 3: Token-Trim (measured change) [0C]** - Wire the dead `_extract_html_skeleton` as build compaction; gated on semantic snapshot + measured token delta (completed 2026-06-07)
- [x] **Phase 4: Manifest + Compiler [1A]** - File-backed manifests → thin compiler → typed `CompiledWorkflow`; pipelines run from compiled plans (completed 2026-06-07)
- [x] **Phase 5: Typed Artifacts + Persistence + Ownership [1B]** - `ArtifactGraph`/`ArtifactRef` + schema (§18); dual-write then delete the legacy mirror; authz denial tests (completed 2026-06-08)
- [x] **Phase 6: Model Policy [1C]** - `ModelResolver` (resolution order + fallback + cost_class) + `ModelCatalog` + per-agent overrides (completed 2026-06-08 — verified offline + threat-secured; 1 live-Bedrock check deferred to end-of-milestone, see 06-UAT.md)
- [x] **Phase 7: Prototype as Manifest — Parity Proof (SC-001) [2]** - Strategies/resolvers/providers/parsers/compaction; delete kernel leaks L1–L12; zero name/id branches (plans 11/11 executed — 6 original + 5 gap-closure 07-07…07-11 ALL DONE 2026-06-09; the 14 deep-review findings closed, SC-001 PROVEN by a non-prototype task_loop workflow; **awaiting re-verification** — see 07-REVIEW-DEEP.md / 07-11-SUMMARY.md) (completed 2026-06-09)
- [x] **Phase 8: Capabilities Hardened — Registry, Gates, Tool Perms, Runtime [3]** - CapabilityRegistry + trust; gate registry; least-privilege; AgentRuntimeAdapter + PromptAssemblyPolicy; delete F1–F5 (completed 2026-06-09)
- [x] **Phase 9: Local Workspace Runtime + Repo Workflows (no exec) [4A]** - `RuntimeEnvironment` port + `LocalSandboxRuntime`; repo inventory/index/context-pack + `repo_diff`; MCP client + integrations (completed 2026-06-10)
- [x] **Phase 10: Safe Local Exec (gated on N3) [4B]** - Constrained `exec` behind the `security` gate + `ExecutionPolicy`; compile/test/lint validators (completed 2026-06-10)
- [x] **Phase 11: Engine-Owned Fan-Out + Merge [5]** - `spawn_subagents` + kernel `run_fanout`; isolation + merge-conflict flow; `BudgetManager`; subagent persistence (completed 2026-06-11)
- [x] **Phase 12: Wave Scheduler + Durable Resume [6]** - Topo wave scheduler; `wave_runs`; resume mid-wave; prototype stays sequential (completed 2026-06-11)
- [x] **Phase 13: Live Verification Gap Closure** - Close the post-milestone live-Bedrock findings F1–F7 (.planning/live-verification/REPORT.md): declared-gate event delivery, run_revision FR-014 dead end, silent inject-halt completion, tool-XML prompt hygiene + handoff hardening, app_builder prompt re-templating, sample_fanout deliverable, test-infra repairs (completed 2026-06-11)

> **Deferred (plan Phase 7, OUT OF SCOPE this milestone):** ECS/EC2 runtime behind the unchanged `RuntimeEnvironment` port — a separate spec (§27). Tracked as v2 in REQUIREMENTS.md (ECS-01/02).

## Phase Details

### Phase 1: Safety Net + Deletion Guard [0A]

**Goal**: Lock current behavior with characterization snapshots and stand up the CI gates that enforce the migration discipline — before any refactor touches the engine.
**Depends on**: Nothing (first phase)
**Requirements**: SAFE-01, SAFE-02, SAFE-03, SAFE-04, SAFE-05, SAFE-06, SAFE-07, DEL-01, DEL-02, DEL-03, DEL-04
**Success Criteria** (what must be TRUE):

  1. Deliverable byte-snapshots + semantic event snapshots recorded and green for prototype, od_prototype, prototype_revision, ppt/od_ppt, and one code-gen pipeline (driven by the scripted model)
  2. The migration-ledger CI guard, import-linter contract, and hand-rolled-deep-agent banned-pattern gate all run in CI (start green/empty, tighten as items delete)
  3. Per-run event `seq` asserted contiguous; no runtime behavior change

**Plans**: 4 plans (3 waves)

Plans:

- [x] 01-01-PLAN.md — Extend `_scripts_for` (PPT) + deliverable byte-snapshot characterization tests for 5 pipelines (SAFE-01) [wave 1] ✅ 2026-06-06
- [x] 01-02-PLAN.md — `_normalize()` + semantic event-stream snapshots + contiguous `seq` assertion (SAFE-02, SAFE-03) [wave 2]
- [x] 01-03-PLAN.md — `migration-ledger.md` mirror of §31 + `test_migration_ledger.py` ratchet (DEL-01..04, SAFE-04) [wave 1] ✅ 2026-06-06
- [x] 01-04-PLAN.md — import-linter + vulture (SAFE-05) + banned-pattern gate (SAFE-06) + CI wiring (SAFE-07) [wave 3]

### Phase 2: ExecutionContext + Ownership [0B]

**Goal**: Extract every per-run `self._*` attribute into a per-run `ExecutionContext`, make the kernel singleton stateless/immutable, and add the explicit parent-run ownership check — with no behavior change.
**Depends on**: Phase 1
**Requirements**: CTX-01, CTX-02, CTX-03, CTX-04, CTX-05
**Success Criteria** (what must be TRUE):

  1. All `self._*` run state (`_od_context`/`_completed_tasks`/`_current_task_block`/`_revision_*`/`_gate_agent_ids`/`_user_id`/`_checkpointer`) lives on `ExecutionContext`; kernel has no per-run attributes (NFR-001); ledger L14 grep gate returns 0
  2. Cross-owner `parent_run` seeding is rejected by an explicit ownership check (L16 denial test passes)
  3. ~~Dead `_handle_revision` deleted (D1)~~ **[VOIDED 2026-06-07 — `_handle_revision` is live (the `run_revision` PPT-revision handler); D1 deferred, see CTX-04]**; deliverable snapshots byte-identical and event snapshots at semantic parity

**Plans**: 3 plans (3 waves — strangler chain, each wave leaves the 0A suite green)
Plans:
**Wave 1**

- [x] 02-01-PLAN.md — Introduce `ExecutionContext` (context.py, D-01 field set) + relocate all `self._*` per-run state onto it + thread `ectx` through the 6 read-sites; kernel stateless; L14 grep → 0 (CTX-01, CTX-02, CTX-05) [wave 1]

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 02-02-PLAN.md — **[RE-SCOPED 2026-06-07]** ~~Delete dead `_handle_revision` (D1)~~ (voided — live `run_revision` handler) + flip migration-ledger row **L14** to ☑ (arm the grep ratchet; fixed the ledger parser to handle alternation patterns); D1 deferred (CTX-05; CTX-04 deferred) [wave 2]

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 02-03-PLAN.md — `assert_owns` ownership helper (authz.py) + explicit cross-owner check above the seed try/except + denial/degrade/anon tests + record L16 (CTX-03, CTX-05) [wave 3]

**Cross-cutting constraints:**

- Phase 0A characterization snapshots stay byte-identical and at semantic-event parity

### Phase 3: Token-Trim (measured change) [0C]

**Goal**: Wire the dead `_extract_html_skeleton` as build-task-2+ context compaction (Tier#1) — the one sanctioned non-byte-identity change, gated on the semantic snapshot plus a measured token reduction.
**Depends on**: Phase 2
**Requirements**: COMPACT-01, COMPACT-02, COMPACT-03
**Success Criteria** (what must be TRUE):

  1. `_extract_html_skeleton` is wired into build-task-2+ prompts (L13 now live)
  2. Semantic snapshot holds (same pages/routes, equal-or-better validation pass rate) — gated on semantics, not byte-identity
  3. A measured token/cost reduction is demonstrated on a multi-task build

**Plans**: 2 plans (2 waves)
Plans:
**Wave 1**

- [x] 03-01-PLAN.md — Wire `_extract_html_skeleton` into `_build_context_message` task-2+ + deterministic offline ≥50% reduction CI gate + read_file-access assert (COMPACT-01, COMPACT-03) [wave 1]

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 03-02-PLAN.md — Re-baseline prototype/od_prototype deliverable goldens (hold semantic snapshots) + pages/routes + equal-or-better-validation parity assertion + opt-in live token-delta evidence → SUMMARY (COMPACT-02, COMPACT-03) [wave 2]

### Phase 4: Manifest + Compiler [1A]

**Goal**: Introduce hand-authored file-backed workflow manifests and a thin compiler (no DSL) that produces a typed `CompiledWorkflow`; run every existing pipeline from a compiled plan while artifacts still flow via the legacy mirror.
**Depends on**: Phase 3
**Requirements**: MAN-01, MAN-02, MAN-03, MAN-04, MAN-05, API-01
**Success Criteria** (what must be TRUE):

  1. `WorkflowManifest` (schema + loader/validator) and `WorkflowCompiler` compile a YAML manifest to a validated typed `CompiledWorkflow`/`ExecutionPlan` with no control flow in manifests (INV-5)
  2. Every current pipeline runs from a compiled plan; snapshots green; `accumulated_outputs` mirror still used (no schema change yet)
  3. Compiler rejects unknown/not-allowed capability references (INV-4); `GET /api/workflows[/{id}]` returns manifest-derived metadata

**Plans**: 5 plans
Plans:
**Wave 1**

- [x] 04-01-PLAN.md — Capability ports (`base.py`) + name registry (`registry.py`, 14 names) + id-alias resolver [MAN-03]
- [x] 04-02-PLAN.md — `plan.py` (CompiledWorkflow/Step/Task §6 contract) + `manifest.py` loader/validator [MAN-01]

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 04-03-PLAN.md — `compiler.py` (thin, no-DSL, name-resolve) + the 15 `workflow.yaml` manifests + coverage/parity tests [MAN-02, MAN-03, MAN-04]

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 04-04-PLAN.md — Engine routing seam + id-alias (run from CompiledWorkflow) + characterization parity gate [MAN-04, MAN-05]
- [x] 04-05-PLAN.md — `/api/workflows` definitions rewrite + `/api/runs` relocation + 10 frontend repoints [API-01]

### Phase 5: Typed Artifacts + Persistence + Ownership [1B]

**Goal**: Replace the untyped `accumulated_outputs` handoff with a typed, content-addressed, owner-scoped `ArtifactGraph`; land the persistence schema (§18) and default-deny ownership enforcement; dual-write then delete the legacy mirror.
**Depends on**: Phase 4
**Requirements**: ART-01, ART-02, ART-03, ART-04, PERSIST-01, PERSIST-02, PERSIST-03, AUTHZ-01, AUTHZ-02, AUTHZ-03, AUTHZ-04, CAPRUN-01, API-04, API-05
**Success Criteria** (what must be TRUE):

  1. Artifacts are typed + lineage-tracked (producer step/agent/task, content hash, version, parents, visibility, retention) and persisted; the `accumulated_outputs` mirror is deleted (L15 gate; only typed reads remain)
  2. Additive migrations add `artifact_refs`, extend `workflow_runs`, add `workspaces`/`run_events`/`run_capabilities`; every table carries `owner_id` + `workspace_id`
  3. Default-deny store-layer scoping enforced; cross-owner authz denial tests pass; `anon:<session_id>` owner used for unauthenticated runs; snapshots green
  4. `GET /api/runs/{id}/artifacts` returns the typed lineage tree; `GET /api/runs/{id}/events?after=<seq>` replays the durable log

**Plans**: 7 plans (6 waves)
Plans:
**Wave 1**

- [x] 05-01-PLAN.md — `agents/artifacts/` typed `ArtifactGraph`/`ArtifactRef` + typed produces/consumes routing (ART-01..04) [wave 1]
- [x] 05-02-PLAN.md — §18 additive `0014` migration + 4 models + extend `workflow_runs`/`workflows` + default-workspace backfill (PERSIST-01, AUTHZ-01) [wave 1]

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 05-03-PLAN.md — relocate `assert_owns` → `agents/authz.py` default-deny scoped store helper + parent/artifact/workspace denial tests + anon:<session_id> (AUTHZ-01..04) [wave 2]

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 05-04-PLAN.md — engine wiring: owner/workspace/capabilities/artifacts at `execute()` entry (byte-identity guard) + per-run seq/event_id sink + dual-write + read-migration (ART-01/03, PERSIST-02/03, CAPRUN-01) [wave 3]

**Wave 4** *(blocked on Wave 3 completion)*

- [x] 05-05-PLAN.md — `/api/runs/{id}/artifacts` lineage tree + `/api/runs/{id}/events?after=<seq>` replay + CAPRUN-01 (API-04/05) [wave 4]

**Wave 5** *(blocked on Wave 4 completion)*

- [x] 05-06-PLAN.md — migrate the 6 thin-store artifact-method consumers (planner/produces-loop/`_handle_revision` reads+write/clarifications write/reconnect read) onto `ScopedStore`/`artifact_refs`, `assert_owns`-gated; additive, parity-safe, no deletion (ART-01/03, PERSIST-02) [wave 5]

**Wave 6** *(blocked on Wave 5 completion)*

- [x] 05-07-PLAN.md — [BLOCKING parity gate] then delete `accumulated_outputs` mirror + thin-store artifact half + `WorkflowArtifact` + `0015` DROP + flip ledger L15 + thin-store gate (PERSIST-02) [wave 6]

### Phase 6: Model Policy [1C]

**Goal**: Implement model resolution with the full precedence order, fallback chains, cost classes, a `ModelCatalog`, and persisted per-agent overrides — global default stays Haiku.
**Depends on**: Phase 5
**Requirements**: MODEL-01, MODEL-02, MODEL-03, MODEL-04, MODEL-05
**Success Criteria** (what must be TRUE):

  1. `ModelResolver` applies user-override > step > agent > workflow > global(Haiku); per-step/workflow model honored; global default unchanged
  2. `ModelPolicy` (model id, max_tokens doc-only, cost_class, ordered fallback) drives `model_factory.build_model`; fallback fires on throttle/error
  3. `ModelCatalog` capability lists selectable models (label/provider/cost_class/window/user_allowed); per-agent `model_overrides` applied at the top of the order and persisted per run

**Plans**: 5 plans
Plans:
**Wave 1**

- [x] 06-01-PLAN.md — `ModelCatalog` single-source capability + registry name + `AVAILABLE_MODELS` projection (MODEL-04, INV-12)
- [x] 06-02-PLAN.md — AGENT.md optional `model` field → `AgentSpec.model` (loader, backs resolver tier 3)

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 06-03-PLAN.md — `ModelResolver` + precedence + tier-descent chains + `_is_transient_throttle`, on `ExecutionContext`; rewire `_run_agent` model sites (MODEL-01/02/05, INV-3 parity)

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 06-04-PLAN.md — per-agent `model_overrides` ingress + allow-list validation + persist to `run_capabilities` (MODEL-03; HIGH threat)

**Wave 4** *(blocked on Wave 3 completion)*

- [x] 06-05-PLAN.md — APPROACH B engine-level fallback (rebuild-and-retry on throttle) + scripted-throttle tests (MODEL-02)

### Phase 7: Prototype as Manifest — Parity Proof (SC-001) [2]

**Goal**: Re-express prototype/od_/revision entirely as manifests backed by registered capabilities, then delete the hardcoded kernel leaks L1–L12 — proving the kernel knows no workflow by name. **This is the core-value proof.**
**Depends on**: Phase 6
**Requirements**: PARITY-01, PARITY-02, PARITY-03, PARITY-04, PARITY-05, PARITY-06, PARITY-07, PARITY-08, PARITY-09
**Success Criteria** (what must be TRUE):

  1. `single_shot` + `task_loop` strategies, `single_file`/`serialized_sandbox`/`streamed_text` + `ppt` resolvers, `opendesign` provider, declared `seed_files`, `heading_tasks` parser, and `html_skeleton` `CompactionStrategy` all implemented and registered
  2. prototype, od_prototype (alias), and prototype_revision (from_run + previous_run + post-edit validation gate) run purely from manifests
  3. Kernel leaks L1–L12 deleted; grep gate for `if pipeline_type`/`spec.id ==` and the L1/L2/L5/L6/L7/L10/L11/L12 patterns return 0 (INV-1)
  4. prototype/od_/revision/ppt/code-gen at deliverable parity + semantic event parity vs the post-0C baseline

**Plans**: 11 plans (6 original + 5 gap-closure 07-07…07-11 — ALL 11 EXECUTED; **REOPENED then closed 2026-06-09** — deep review found context_message parity drift + SC-001 hardcoding; all 14 findings closed, SC-001 PROVEN; awaiting re-verification)
Plans:
**Wave 1**

- [x] 07-01-PLAN.md — `single_shot` + `task_loop` strategies + `heading_tasks` parser + the D-02 resolve seam + D-03 runner handle (PARITY-01)

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 07-02-PLAN.md — `single_file`/`serialized_sandbox`/`streamed_text`/`ppt` resolvers + `opendesign`/`previous_run` providers + seed_files (PARITY-02/03/07)

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 07-03-PLAN.md — `html_skeleton` CompactionStrategy re-expressing 0C behind the capability (PARITY-04)

**Wave 4** *(blocked on Wave 3 completion)*

- [x] 07-04-PLAN.md — wire the engine to route prototype/od_prototype/prototype_revision through the capabilities + prove 5-pipeline parity while L1–L13 are present-but-dead (PARITY-05/09)

**Wave 5** *(blocked on Wave 4 completion)*

- [x] 07-05-PLAN.md — delete kernel leaks L1–L13 + drop pipeline.py + flip ledger rows kernel-scoped + banned-pattern hard-fail + re-verify L14/L15/L16 (PARITY-06/08)

**Wave 6** *(gap-closure — 07-01…05 executed; closes the 2 FAILED verification truths)*

- [x] 07-06-PLAN.md — restore the opendesign provider's L12 byte contract (CR-01 DS preamble, CR-02 builder-gated example, CR-03 build-task-2+ suppression) + fix the locked-in test assertion + add a dedicated context_message parity assertion / de-blind the characterization normalizer (PARITY-03/09 gap-closure)

**Wave 7** *(gap-closure — REOPENED 2026-06-09; 07-REVIEW-DEEP.md found 14 confirmed findings the 07-06 de-blind masked; order B→C→D→E, sequential)*

- [x] 07-07-PLAN.md — cluster B (golden-safe): delete the dead dual validation fix-loop in task_loop.py (the `else` branch, `_SkippedRender`, duplicated helpers) + prune `run_fix_agent` from the KernelServices contract; re-point test_strategies (WR-07/WR-08, INV-3/INV-12) (PARITY-09)
- [x] 07-08-PLAN.md — cluster C oracle: capture the TRUE pre-Phase-7 (acd1636) context_message bytes as an engine-independent oracle + a test proving the current routed message diverged (reverses the 07-06 adjudication; the 07-09 acceptance target) (PARITY-03/09)
- [x] 07-09-PLAN.md — cluster C restorations (asserted vs the oracle): TEMPLATE COMPLIANCE (CR-01), per-injects gate (CR-02), raw injection parts (CR-04), bare END markers (WR-03), build-skeleton wrapper (WR-01), ppt order (WR-02), typed re-persist after fix (WR-05); regenerate the 5 goldens to oracle bytes (PARITY-03/07/09)
- [x] 07-10-PLAN.md — cluster D + E-CR-06: declared revision-intent flag (WR-04/WR-06) + move the kernel-resident prototype-revision block (seed → baseline → post-edit fix-loop) into the previous_run provider + a declared post-step capability; remove the DELIBERATE EXCEPTION (PARITY-05/09)
- [x] 07-11-PLAN.md — cluster E CR-05/CR-07 (SC-001 core value): thread ctx.deliverable.name (de-hardcode prototype.html) + declared TaskSource.source_step + honored seed_files; PROVE a brand-new non-prototype task_loop workflow runs from manifest+AGENT.md only, ZERO engine edits (PARITY-05/09) — DONE: app.py produced end-to-end with validation/fix on app.py, zero engine edits; 581 agent tests + 5-pipeline characterization parity green

### Phase 8: Capabilities Hardened — Registry, Gates, Tool Perms, Runtime [3]

**Goal**: Formalize the capability registry + trust flags, make gates first-class (incl. a real `validation` gate), enforce least-privilege tool permissions, and lift the factory's hardcoded runtime/tools/prompt-order into adapters/registries/policy — deleting F1–F5 and fixing the constitution no-op (R12).
**Depends on**: Phase 7
**Requirements**: CAP-01, CAP-02, CAP-03, GATE-01, GATE-02, GATE-03, TOOLPERM-01, TOOLPERM-02, TOOLPERM-03, VALID-01, VALID-02, VALID-03, VALID-04, VALID-05, AGENTRT-01, AGENTRT-02, AGENTRT-03, AGENTRT-04, AGENTRT-05, AGENTRT-06, SKILL-01, HOOK-01, HOOK-02, HOOK-03, HOOK-04, OBS-02, API-02, API-03, API-06
**Success Criteria** (what must be TRUE):

  1. `CapabilityRegistry` (self-registering, trust flags) drives all capability lookups; `GateHandler` registry implements human/validation/approval/security and makes `Validation_Gate` real
  2. `ToolPermissions` enforced at `factory._build_runner_tools` + `ExecutionPolicy` (least-privilege; exec/network/secrets/spawn default OFF); validators + generic fix-loop + P0–P3→severity mapping migrated; Tier#4/5/6 validators land
  3. `AgentRuntimeAdapter` (`langchain_deepagents`), `PromptAssemblyPolicy`, `tool_provider`/`skill_provider`/`hook_provider` replace the inline factory code; F1–F5 deleted; constitution-injected-in-prod test passes (R12)
  4. Executable lifecycle hooks (secret_scan/otel_tracing/pre-post_commit/post_task) fire and persist to `hook_runs`; `/api/capabilities` returns the dynamic palette; new validator/gate events surface at semantic parity for existing workflows

**Plans**: 8 plans (7 waves — strangler dependency order; each F# deletion gated on parity before its row flips ☑)
Plans:
**Wave 1**

- [x] 08-01-PLAN.md — `@register`/`discover()` self-registration + `user_allowed` trust + new tool/skill/hook/runtime kinds + `base.py` ports + the single canonical `map_severity` (VALID-03); delete `install()`; fold the test-isolation reset fixture (CAP-01/02/03, VALID-03) [wave 1] ✅ 2026-06-09

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 08-02-PLAN.md — `GateHandler` registry (human/validation/approval/security) + real `Validation_Gate` (imports the 08-01 `map_severity`) + the additive `0016` migration (validation_results/gate_events/hook_runs) (GATE-01/02/03) [wave 2]
- [x] 08-03-PLAN.md — `ToolPermissions` intersection + enforcement (factory tool_provider + ExecutionPolicy); delete F2 switch (TOOLPERM-01/02/03, AGENTRT-04) [wave 2]

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 08-04-PLAN.md — `Validator` registry + generic `FixPolicy` fix-loop + migrate html_static/html_render (severity via the imported 08-01 `map_severity`) + Tier#4/5/6 + re-point task_loop validation (VALID-01/02/04/05) [wave 3]
- [x] 08-05-PLAN.md — `AgentRuntimeAdapter` + `PromptAssemblyPolicy` + skill_provider/hook_provider; delete F1/F3/F5 (AGENTRT-01/02/03/05, SKILL-01) [wave 3]

**Wave 4** *(blocked on Wave 3 completion)*

- [x] 08-06-PLAN.md — constitution sync-safe pre-warm fix; delete F4/R12 branch — all F1–F5 ☑ (AGENTRT-06) [wave 4]
- [x] 08-08-PLAN.md — `GET /api/capabilities` palette + additive run-stream events (semantic parity) + capability palette/model picker/validator panel (API-02/03/06) [wave 4]

**Wave 5** *(blocked on Wave 4 completion)*

- [x] 08-07-PLAN.md — executable `HookHandler` framework + secret_scan + otel_tracing (real OpenTelemetry, human-approved) + hook_runs (HOOK-01..04, OBS-02) [wave 5]

### Phase 9: Local Workspace Runtime + Repo Workflows (no exec) [4A]

**Goal**: Introduce the `RuntimeEnvironment`/`Workspace` ports with a `LocalSandboxRuntime`, and deliver the first brownfield repo workflow end-to-end locally without execution (clone → branch → inventory → read/edit/search → diff) — plus the MCP client and integration providers.
**Depends on**: Phase 8
**Requirements**: RUNTIME-01, RUNTIME-02, RUNTIME-03, REPO-01, REPO-02, REPO-03, REPO-04, REPO-05, MCP-01, MCP-02, MCP-03, MCP-04, INTEG-01, INTEG-02
**Success Criteria** (what must be TRUE):

  1. `RuntimeEnvironment` port + `LocalSandboxRuntime`; one `Workspace` abstraction (prototype = `has_git=False, exec=off`) with no engine fork repo-vs-artifact; `repositories`/`workspaces` rows persisted
  2. `RepoInventory` (tree/lang/deps/ignore-rules/binary-skip/summaries), optional `RepoIndex`, and per-task `ContextPack` produced; `repo_diff` resolver yields a file tree + per-file diff
  3. A sample repo workflow runs end-to-end locally with **no exec** and surfaces a diff; prototype unaffected
  4. `McpClientAdapter` + allow-listed famous-server catalog (scoped per-owner creds, security-gated for powerful servers); compiler validates `tools.mcp`; integration providers reachable from the unified runner path

**Plans**: 6 plans (sequential — `use_worktrees=false`; waves encode the true DAG)
Plans:
**Wave 1**

- [x] 09-01-PLAN.md — `RuntimeEnvironment`/`Workspace`/`ExecutionPolicy`/`IsolationProvider` ports (kernel `agents/runtime/base.py`) + `LocalSandboxRuntime` (app-side `app/agents/runtime/local.py`) + the 4th import-linter contract (RUNTIME-01) [wave 1] — DONE 2026-06-10 (3 tasks; runtime_env registered; lint 4/0; 5 characterization snapshots byte/event-identical)

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 09-02-PLAN.md — additive migration 0017 (`repositories`, down_revision 0016) + `repositories`/`kind=repo` `workspaces` rows + `RunSandbox` → `Workspace(has_git=False, exec=off)` refold (parity-gated) (RUNTIME-02/03) [wave 2] — DONE 2026-06-10 (2 tasks; 0017 reversible offline; ScopedStore.create_repository one-repo+one-kind=repo-workspace + cross-owner PermissionError; no `if repo:` fork; 5 characterization snapshots byte/event-identical, SNAPSHOT_UPDATE UNSET; lint 4/0; ledger R1 green)

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 09-03-PLAN.md — `RepoInventory` + `RepoIndex` (grep default, tree-sitter behind the capability) + `ContextPack`/`context_selector` + `repo` `ContextProvider` (REPO-01/02/03) [wave 3]

**Wave 4** *(blocked on Wave 3 completion)*

- [x] 09-04-PLAN.md — `repo_diff` `DeliverableResolver` (reads `Workspace.git_diff`; diff-only) + the sample brownfield workflow (clone→branch→inventory→read/edit→diff, no exec) (REPO-04/05) [wave 4]

**Wave 5** *(blocked on Wave 4 completion)*

- [x] 09-05-PLAN.md — `McpClientAdapter` over `MultiServerMCPClient` (async-prewarm) + allow-listed `mcp_server` catalog + compiler `tools.mcp` compile-validation + security-gate+secrets gating + the stdio stub server (MCP-01/02/03/04) [wave 5]

**Wave 6** *(blocked on Wave 5 completion)*

- [x] 09-06-PLAN.md — `integration_provider` capabilities (github/gitlab/jira/slack from `create_runner`) + `integrations` scopes + delete the `CodingAgent` handoff bypass (retain `/api/handoff`) (INTEG-01/02) [wave 6]

### Phase 10: Safe Local Exec (gated on N3) [4B]

**Goal**: After the N3 threat model is decided, enable a constrained `exec` profile behind the `security` gate with command allow/deny, default-deny egress, resource caps, and ephemeral creds — plus compile/test/lint validators.
**Depends on**: Phase 9 (and the N3 threat-model decision)
**Requirements**: EXEC-01, EXEC-02
**Success Criteria** (what must be TRUE):

  1. `exec` runs only under the `security` gate + `ExecutionPolicy` (command allow/deny, resource caps, ephemeral creds); network egress denied by default
  2. compile/test/lint validators land and a sample compile/test validator passes

**Plans**: 5 plans
Plans:
**Wave 1**

- [x] 10-01-PLAN.md — exec foundation: hardened argv exec_command + LocalExecutionPolicy caps + exec_runs audit (0018) [EXEC-01] (completed 2026-06-10)

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 10-02-PLAN.md — compile-time GRANT-PATH: trust-conditional ceiling + D-01 gates-required + plan.py forward-surface deletion (INV-12) [EXEC-01]

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 10-03-PLAN.md — GATES: profile-conditional security pass + approval HITL (D-02/03/04) + §15 runtime workspace wiring [EXEC-01]

**Wave 4** *(blocked on Wave 3 completion)*

- [x] 10-04-PLAN.md — VALIDATORS: code_compile/test/lint + fixture repo + VALIDATOR-DENY + exec-granting sample manifest (EXEC-02) [EXEC-02]

**Wave 5** *(blocked on Wave 4 completion)*

- [x] 10-05-PLAN.md — DEBT+PARITY: IN-01/02/03 closure + N3-resolved flips + phase parity gate [EXEC-01, EXEC-02] (completed 2026-06-10)

### Phase 11: Engine-Owned Fan-Out + Merge [5]

**Goal**: Implement engine-owned fan-out (declarative + `spawn_subagents` tool) with isolation, merge-conflict handling, budgets, depth/concurrency caps, subagent persistence, and cancellation propagation — the engine alone decides isolation/caps/merge (INV-7).
**Depends on**: Phase 9
**Requirements**: FANOUT-01, FANOUT-02, FANOUT-03, FANOUT-04, FANOUT-05, FANOUT-06, FANOUT-07, FANOUT-08, FANOUT-09, FANOUT-10, FANOUT-11, OBS-01, RESUME-01
**Success Criteria** (what must be TRUE):

  1. A granted step fans out N workers (self-copies or named workers) under `max_concurrency`, parallel or sequential; both declarative and tool entry points funnel through kernel `run_fanout`
  2. `IsolationProvider` (shared_read/sub_sandbox/worktree, writes isolated) + `MergeStrategy` merge fragments deterministically; conflicts follow `on_conflict` (human_gate/merge_agent/partial/abort) with a `merge_conflict` artifact + event
  3. `BudgetManager` reserves-before-spawn and enforces subagents/concurrency/tokens/cost/wall-clock/depth (per-run + per-workspace); `BudgetExceeded` aborts gracefully with partial results; cancellation propagates to children
  4. Each child → a `subagent_runs` row; `subagent_*`/`merge_*` events emitted

**Plans**: 5 plans (5 waves — sequential `use_worktrees=false`; each plan leaves the characterization suite green, D-09)
Plans:
**Wave 1**

- [x] 11-01-PLAN.md — Fan-out foundation: kernel `run_fanout` (fanout.py, the single spawn path) + `spawn_subagents` request-emitter tool (capability + concrete, gated) + `fanout_batch` strategy + worker selection (self×N / `allowed_workers`) + parallel/sequential modes + `0019 subagent_runs` migration/ORM/ScopedStore + budget stub seam + engine tool-result derivation (FANOUT-01/02/03/04/10) [wave 1] ✅ cdec230/903b704/26ee45c

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 11-02-PLAN.md — Isolation: `sub_sandbox` + `worktree` on `LocalWorkspace` (single git-subprocess owner) + engine-decided scope selection (has_git→worktree else sub_sandbox, INV-7) + per-worker workspace binding in `run_fanout` (FANOUT-05) [wave 2]

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 11-03-PLAN.md — Merge: `MergeStrategy` port + 4 registered impls (copy_disjoint/git_3way/json/html_fragment) + merge dispatch + `merge_conflict` artifact/event + 4 `on_conflict` policies (human_gate/merge_agent≤2/partial/abort) + per-worker fragment artifacts (FANOUT-06/07/08) [wave 3]

**Wave 4** *(blocked on Wave 1; landed after merge so the snapshot captures real worker activity)*

- [x] 11-04-PLAN.md — Budget enforcement: `BudgetManager.reserve()` (reserve-before-spawn; subagents/concurrency/depth + token/wall-clock at-boundary) + trust-conditional `Limits` + per-workspace ceiling (settings seam) + `BudgetSnapshot`→`budget_snapshot_json` + `budget_warning` (FANOUT-09, OBS-01) [wave 4]

**Wave 5** *(blocked on Wave 3 + Wave 4 completion)*

- [x] 11-05-PLAN.md — Cancellation + SC-001: cancel checks at fan-out boundaries + finally-teardown of every isolated workspace (no leaks) + terminal `cancelled` rows + `pipeline_cancelled` + the test-scoped sample fan-out workflow (manifest + AGENT.md only, zero engine edits) + phase exit gate (FANOUT-11, RESUME-01) [wave 5]

### Phase 12: Wave Scheduler + Durable Resume [6]

**Goal**: Add a deterministic topological wave scheduler that runs disjoint tasks in parallel waves via fan-out, with durable mid-wave resume; prototype stays sequential and a CP-SAT seam is left.
**Depends on**: Phase 11
**Requirements**: WAVE-01, WAVE-02, WAVE-03, RESUME-02, RESUME-03, RESUME-04
**Success Criteria** (what must be TRUE):

  1. `wave_scheduler` strategy topo-sorts by `depends_on` + `conflict_keys` into waves and runs each wave via fan-out; a multi-file workflow runs disjoint tasks in parallel waves; prototype stays sequential; CP-SAT seam left
  2. `wave_runs` persisted; a server restart resumes mid-wave via `subagent_runs`/`wave_runs`; idempotent step retry reuses artifacts on content-hash match
  3. Reconnect replays from the durable `run_events` log (`after=<seq>`, idempotent by `event_id`); `restore_non_terminal_runs` resumes at step granularity (waiting_for_user gates resume on user action)

**Plans**: 10 plans (4 waves + 3 gap-closure waves)
Plans:
**Wave 1**

- [x] 12-01-PLAN.md — `wave_scheduler` strategy + pure `build_waves` (topo by depends_on + conflict_keys, CP-SAT seam) + `json_tasks` parser + additive `0020 wave_runs` (migration/ORM/ScopedStore/KernelServices) + sample multi-file wave workflow (SC-001) + ledger/lockstep ratchets [wave 1]

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 12-02-PLAN.md — `Step.retry` consumption: one engine retry wrapper (transient-only) + `(run_id, step_id, input content_hash)` artifact reuse + `step_retry`/`step_reused` events [wave 2]

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 12-03-PLAN.md — durable WS `reconnect_pipeline` `after_seq` replay (idempotent by `event_id`) + `resume_run` step-granular in-process auto-resume incl. mid-wave + three-way `restore_non_terminal_runs` (WR-05 fallback kept) [wave 3] ✅ 2026-06-11

**Wave 4** *(blocked on Wave 3 completion)*

- [x] 12-04-PLAN.md — FE wave/subagent tree panel (additive sibling) + FE reconnect `after_seq` + `event_id` dedup adoption (clears the 08-08 deferral) [wave 4]

**Gap Closure** *(after 12-VERIFICATION found 4 blockers + CR-05 + triaged warnings)*

- [x] 12-05-PLAN.md — durable-resume/replay blockers: seed `resume_run` seq counter past the durable tail (CR-01) + recover `workspace_id` in the WS reconnect replay ScopedStore (CR-02) [wave 1, gap_closure] (completed 2026-06-11)
- [x] 12-06-PLAN.md — mid-wave resume correctness: step-filter completed-wave set (CR-04) + re-run the whole in-flight wave instead of an unsafe parallel-order prefix skip (CR-03) + flip stale `running` wave row (WR-01) + stamp `wave_index`/`step` on subagent events (CR-06 backend half) + reject duplicate task ids pre-spawn (WR-05) [wave 1, gap_closure]
- [x] 12-07-PLAN.md — FE wave tree: hoist `event_id` dedup to cover all event types (CR-05) + reset per-run replay/dedup/wave state (WR-03) + render worker leaves keyed by worker index, waves keyed by `step:waveIndex` (CR-06 FE half / IN-06) + cancelled→terminal (IN-05) + live render/reconnect human-verify [wave 2, gap_closure, depends 12-06]

**Gap Closure 2** *(after 12-UAT live pass found Gap 1 dead wave panel, Gap 2 auto-resume reconnect, Gap 3 sample deliverable)*

- [x] 12-08-PLAN.md — FE: mount `WaveTreePanel` on the dashboard execution surface (thread `waveGroups` from page.tsx → DashboardLayout; Gap 1, no longer dead UI) + add the missing `pipeline_reconnected` handler in useWorkflow (resolve on live:false+terminal; Gap 2 FE half — stops the post-resume "running forever" hang) [wave 1, gap_closure]
- [x] 12-09-PLAN.md — BE: injected engine→WS live-task bridge so an auto-resumed run registers in `_PIPELINE_TASKS`/`_PIPELINE_QUEUES` (reconnect live-attaches; Gap 2a) + stamp `workflow_runs.workspace_id` consistently with the run_events sink via `set_run_scope` (non-null `pipeline_reconnected.status`; Gap 2c) + `_stamp_resume_marker` recovers the real workspace_id (no NOT NULL IntegrityError); import-linter-safe (no engine→app.api import) [wave 1, gap_closure]
- [x] 12-10-PLAN.md — manifest: switch `sample_wave` deliverable from `single_file name=merged.txt` (no step produces it) to `serialized_sandbox` (bundles the merged `part_*.txt` base the workers actually write) — no more "merged.txt not written — falling back to streamed output" warning; zero engine edits (SC-001) [wave 1, gap_closure]

## Progress

**Execution Order:**
Phases execute sequentially: 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10 → 11 → 12

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Safety Net + Deletion Guard [0A] | 4/4 | Complete   | 2026-06-06 |
| 2. ExecutionContext + Ownership [0B] | 3/3 | Complete    | 2026-06-07 |
| 3. Token-Trim [0C] | 2/2 | Complete    | 2026-06-07 |
| 4. Manifest + Compiler [1A] | 5/5 | Complete    | 2026-06-07 |
| 5. Typed Artifacts + Persistence [1B] | 7/7 | Complete    | 2026-06-08 |
| 6. Model Policy [1C] | 5/5 | Complete    | 2026-06-08 |
| 7. Prototype as Manifest (Parity Proof) [2] | 11/11 | Complete    | 2026-06-09 |
| 8. Capabilities Hardened [3] | 8/8 | Complete    | 2026-06-09 |
| 9. Local Runtime + Repo (no exec) [4A] | 6/6 | Complete    | 2026-06-10 |
| 10. Safe Local Exec [4B] | 5/5 | Complete    | 2026-06-10 |
| 11. Fan-Out + Merge [5] | 5/5 | Complete    | 2026-06-11 |
| 12. Wave Scheduler + Resume [6] | 10/10 | Complete    | 2026-06-11 |
| 13. Live Verification Gap Closure | 6/6 | Complete    | 2026-06-12 |

### Phase 13: Live Verification Gap Closure

**Goal**: Close the product gaps found by the 2026-06-11 post-milestone live-Bedrock verification pass (every workflow + all options on real Haiku 4.5, semantic review by Opus agents) — the findings register lives at `.planning/live-verification/REPORT.md`; the diagnosed gaps (root causes + file:line artifacts) are staged in `13-UAT.md` for `--gaps` planning.
**Depends on**: Phase 12
**Requirements**: None new — closes findings F1–F7 (post-milestone UAT; no REQUIREMENTS.md ids)
**Success Criteria** (what must be TRUE):

  1. A manifest-declared `gates: [human]` step surfaces `review_gate_ready` on the live WS stream BEFORE awaiting the response, so a UI client can approve and the run proceeds (F1)
  2. `run_revision` with the FE's exact payload (`target_artifact_type: ppt_output` / `od_ppt_output`) against a completed parent run passes FR-014 and produces a revision run (F2)
  3. A run whose agents hard-fail (e.g. missing od_context injects) terminates as a visible failure or fails fast at ingress — never `pipeline_complete` with an empty/improvised deliverable (F3)
  4. Text-only agents emit no fabricated tool-call XML into prose on live Haiku, and the handoff coder reliably returns parseable JSON (prompt hygiene + bounded parse-retry) (F4)
  5. All 15 app_builder agents produce role-conformant output: the three migration-templated prompts (code-compliance / test-compliance / sdlc-governance) re-templated for app_builder scope; devops agent emits files, not narration (F5)
  6. sample_fanout resolves its declared deliverable from produced files with no single_file fallback warning; `test_phase3_token_delta_live` runs against the current engine; the phase-8 live sweep budget reflects real Haiku 4.5 spend (F6/F7)

**Plans:** 6/6 plans complete
Plans:
**Wave 1**

- [x] 13-01-PLAN.md — Stream declared human-gate events to the WS consumer before the await (F1)
- [x] 13-02-PLAN.md — Text-only prompt hygiene (no-tools preamble) + handoff coder JSON hardening + output sanitation (F4)
- [x] 13-03-PLAN.md — Re-template app_builder compliance/governance prompts; devops output contract; cross-agent /api/v1 + export-surface contracts (F5)
- [x] 13-04-PLAN.md — sample_fanout serialized_sandbox deliverable swap; token-delta test seam repair; phase-8 budget recalibration (F6/F7)

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 13-05-PLAN.md — run_revision FR-014: persist deliverable-kind ref at completion + fallback lookup chain + FE-exact regression (F2)

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 13-06-PLAN.md — pipeline_failed terminal semantics + degraded completion + missing_template_context ingress guard + FE handling (F3)

### Phase 14: run_revision real revision loop (F2 end-to-end)

**Goal:** `run_revision` produces a real revised artifact, not the Phase-3 echo stub. `_handle_revision` (engine.py:3656) currently resolves the parent via the FR-014 chain, composes the three-section revision context, then writes that context back as the "revision" and emits `pipeline_complete` with `total_duration: 0.0` — no model ever runs. Close it by dispatching the registry's real revision pipelines (`ppt_revision` / `od_ppt_revision` / …, via the WR-06 generic alias) through the normal `execute()` path with the composed context as input, and persisting the run's actual deliverable as the `derived_from` artifact.
**Requirements**: None new — completes live-pass finding F2 beyond its 13-05/WR-06 scoped fixes (validation + FE routing). Known design wrinkle to settle in planning: `od_*_revision` agents may declare `injects: [template, design_system]`, which interacts with the 13-06 `missing_template_context` ingress guard when revising from a completed parent (re-resolve the parent's template vs. exempt revision dispatch).
**Depends on:** Phase 13
**Plans:** 4/4 plans complete

**Success Criteria** (what must be TRUE):

  1. `run_revision` against a completed parent run drives the real revision pipeline agents (model runs observed) and the final deliverable is a revised artifact reflecting the instruction — not the instruction/context blob
  2. The revision artifact persists with `derived_from` lineage to the parent original, owner/workspace-scoped, and revision-of-revision still resolves (FR-014 chain link 1)
  3. Stub-pinning tests (`test_revision_intelligence`, `test_run_revision_fe_contract`) updated to the real-dispatch contract; characterization goldens stay byte/event-identical for non-revision runs (INV-3); no workflow-name literal added to the kernel (SC-001)
  4. Live-confirmed on real Bedrock as part of the milestone-end live pass (FE-exact `run_revision` frame → revised deck in the preview)

Plans:
**Wave 1**

- [x] 14-01-PLAN.md — Manifest planner flips (ppt_revision/od_ppt_revision → skip) + both planner parity traps + design-wrinkle pin + scripted revision-agent harness entries
- [x] 14-02-PLAN.md — WS run_revision queue dispatch (`_handle_revision_execution`) + terminal-status fidelity + agent_count derivation + handler regression suite

**Wave 2** *(blocked on 14-01)*

- [x] 14-03-PLAN.md — Engine real dispatch: `_handle_revision` → `execute()` via the WR-06 alias, delete stub/`_stamped_send`/fake event pair (INV-12), guarded `derived_from` lineage write + FE-exact contract suite rewrite (incl. revision-of-revision)

**Wave 3** *(blocked on 14-03)*

- [x] 14-04-PLAN.md — `test_revision_intelligence` real-dispatch rewrite (guards kept verbatim) + phase-gate battery + SC-001/INV-3 grep sweep + SC4 live deferral recording

### Phase 15: Live-Pass Prompt Contract Closure

**Goal:** Close the three prompt-shaped findings of the 2026-06-12 milestone-end live re-pass (`.planning/live-verification/REPORT-2026-06-12.md`) so the od_ppt deliverable/revision chain carries a real deck and the last live-model adherence gaps get prompt contracts. AGENT.md bodies + tests only — ZERO engine/capability edits (SC-001); the LV-02 resolver alternative (fallback in `deliverable: ppt`) is explicitly rejected as INV-3-sensitive.
**Requirements**: none new — closes live findings LV-02 (major) + two F4/F5 residuals
**Depends on:** Phase 14

**Success Criteria**:

1. LV-02 closed: `od-ppt-validator` AGENT.md carries an output contract (always re-emit the complete corrected deck wrapped in `<artifact>`); on a live od_ppt run the resolved `final_output` is the deck (contains `<section class="slide">`, not QA narration), and an FE-exact `od_ppt_output` revision returns a revised deck (Phase-14 SC4 content unblocked).
2. sdlc-governance residual closed: the sdlc-governance agent family (`app-`/`dotnet-`/`mulesoft-sdlc-governance`) AGENT.md bodies carry anti-fabrication output contracts (begin directly with deliverable content; never emit tool-call syntax); live streams show zero `<function_calls>`/`<invoke>` preambles.
3. infra-generator residual closed: `app-infra-generator` AGENT.md makes the `/api/v1` prefix contract forceful and positionally prominent; a live app_builder infra output targets `/api/v1` routes consistently with api-design/devops.
4. Offline pins land (13-03 precedent): AGENT.md contract-grep tests for all five prompts + a scripted-model pin that the ppt deliverable resolution yields the validator's re-emitted artifact deck; characterization goldens byte-identical (prompt bodies are not characterization inputs for the 5 snapshot pipelines — verify).
5. Live re-check recorded: one od_ppt run + one revision (≈$0.10) demonstrating criteria 1; criteria 2–3 evidence may ride the same session or the next scheduled live pass if quota-constrained (record disposition either way).

**Plans:** 3/3 plans complete

Plans:

- [x] 15-01-PLAN.md — Prompt output contracts on the five AGENT.md bodies: od-ppt-validator exactly-ONE-artifact complete-deck re-emission (LV-02), 3x sdlc-governance anti-fabrication (F4), app-infra-generator top-of-body /api/v1 contract (F5) — bodies only, frontmatter untouched
- [x] 15-02-PLAN.md — Durable pins: new tests/agents/test_prompt_contracts.py (prompt_body pins + frontmatter freeze + LV-02 harness composition test via drive_engine_pipeline per-agent model) + full targeted offline gate proving 5 characterization goldens byte-identical (INV-3)
- [x] 15-03-PLAN.md — Live re-check: one od_ppt run + one FE-exact od_ppt_output revision on real Haiku (~$0.10) with deck evidence, or explicit quota/SSO deferral; disposition record PHASE-15-RECHECK.md (criteria 2-3 as next-live-pass items)

### Phase 16: Terminal-State Integrity and Reconnect Frame-Contract

**Goal:** Make abnormal run outcomes faithful end-to-end. A run whose agents failed on a runner-surfaced model/tool error must end `pipeline_failed` (not an empty `pipeline_complete` with DONE badges); a cancelled run must deliver `pipeline_cancelled` to the live wire so in-flight agent cards clear; the Preview must show a degraded/failed affordance instead of a neutral empty-state for a terminal run with no content; and durable-replay/reconnect frames must match live frames (revision `section`, ack `live`). Engine + WebSocket + one FE affordance only — zero new tables/migrations, INV-3 byte/event parity preserved, SC-001 honored (every new branch keys on a generic event type, never a workflow/model name).
**Requirements**: ISS-016, ISS-017, ISS-007, ISS-002, ISS-008, ISS-009 (.planning/ISSUES-REGISTER.md — "Deep Root-Cause Investigation", clusters A+B)
**Depends on:** Phase 15
**Plans:** 4/4 plans complete

**Success Criteria:**

1. A runner-surfaced model/tool error (e.g. `ValidationException`) on every agent ends the run `pipeline_failed` with `agent_error`s — never an empty `pipeline_complete`; a partial failure ends `status:degraded`. (ISS-016)
2. A real `cancel_pipeline` delivers `pipeline_cancelled` on the live wire so the FE clears all in-flight agent cards, with the DB row `cancelled`; `test_pipeline_cancel.py` passes deterministically. (ISS-007/002)
3. The Preview pane shows a degraded/failed affordance (not the neutral "Output will appear here") for a terminal run with no content, on both live and history-reopen, keyed on the server signal. (ISS-017)
4. Durable-replay revision frames carry the real `section` (matching live-attach) and the live-attach `pipeline_reconnected` ack carries `live:true`. (ISS-008/009)
5. INV-3 parity holds: the 5 characterization goldens (prototype/od_prototype/prototype_revision/od_ppt/app_builder) stay byte-identical; lint-imports stays 4 kept / 0 broken; zero new tables/migrations.

Plans:
**Wave 1** *(A1 engine error-arm + A2 FE affordance run in parallel — disjoint files)*

- [x] 16-01-PLAN.md — A1 · ISS-016: engine `error` consume-arm → routes a runner-surfaced error into the agent_error→pipeline_failed/degraded machinery (no empty agent_complete) + ScriptedNonTransientError fault-injection test + flip test_non_transient_propagates [wave 1]
- [x] 16-04-PLAN.md — A2 · ISS-017: FE terminal-empty degraded/failed affordance keyed on the server signal (live pipeline_failed/degraded + history-reopen status) + additive PipelineRunState `failed` flag + PreviewPanel component test [wave 1]

**Wave 2** *(A3 cancel — edits engine.py after 16-01)*

- [x] 16-02-PLAN.md — A3 · ISS-007/002: cooperative `cancel_event` for cancel_pipeline (set, not destructive task.cancel) + engine pre-agent cancel gap → pipeline_cancelled + asyncio.timeout() at the 3 drainers + keep destructive cancel on disconnect-only + deterministic cancel tests [wave 2, depends 16-01]

**Wave 3** *(B reconnect-contract — edits websocket.py after 16-02)*

- [x] 16-03-PLAN.md — B · ISS-008/009: durable-replay `_replay_section` via the WR-06 inverse + live-attach ack `live:true` + revision-replay section assertion (mirror the WR-03 live-attach contract) [wave 3, depends 16-02]

### Phase 17: Test-Infra and Verification-Gap Closure

**Goal:** Close the 3 test-infra / verification-gap issues of cluster C from the 2026-06-13 deep investigation — all **test-harness-only**, zero production code, no INV-3 exposure. (1) ISS-003: the live token-delta test hangs forever at the clarify gate because its `_drive_live` sets a dead flag instead of compiling clarify off. (2) ISS-010: OTLP span export is unverifiable here (no collector) — close it with a deterministic in-memory-exporter test rather than a live collector. (3) ISS-011: the Phase-8 HITL live-tail tests fail on mid-sweep SSO-token expiry, not a product defect — make the harness skip (not fail) on expiry and re-confirm offline. Outcome: the three are deterministically closeable offline; the live re-runs that need fresh credentials are recorded as deferred, not blocking.
**Requirements**: ISS-003, ISS-010, ISS-011 (.planning/ISSUES-REGISTER.md — "Deep Root-Cause Investigation", cluster C)
**Depends on:** Phase 16
**Plans:** 3/3 plans complete

**Success Criteria:**

1. `test_phase3_token_delta_live._drive_live` compiles `clarify.mode="off"` (mirroring the shared harness) instead of the dead `ALWAYS_CLARIFY` flag; a fault-injected drive returns instead of hanging at the clarify `event.wait()`; the offline collection still skips cleanly. (ISS-003)
2. A deterministic offline test asserts the OTLP hook emits a span with the right attributes via an injected `InMemorySpanExporter` (the hook's module-private `_TRACER` is reset; `_build_span_processor` monkeypatched), plus a graceful-degrade case when the OTLP exporter pkg/endpoint is absent. ISS-010 closed by test, not by a live collector. (ISS-010)
3. The Phase-8 HITL live-tail tests SKIP (not fail) on mid-sweep SSO/credential expiry via a per-test `live_skip_reason()` re-check, and the collection self-check no longer asserts strict collection-vs-runtime equality; `TestOfflineHITL` stays green offline. (ISS-011)
4. Zero production-code changes (test/harness files only); the 5 characterization goldens + lint-imports 4/0 unaffected; live re-runs requiring fresh AWS creds recorded as deferred follow-ups.

Plans:
**Wave 1**

- [x] 17-01-PLAN.md — ISS-003: replace the dead `ALWAYS_CLARIFY` flag in `_drive_live` with the `compile_for_run` clarify-off wrap + a bounded offline fault-injection regression test (SC1) ✅ 2026-06-13 (1 passed / 1 skipped offline; goldens 10/10; lint-imports 4/0; test-only diff)
- [x] 17-02-PLAN.md — ISS-010: in-memory `InMemorySpanExporter` span-capture test (via the hook's own `_build_span_processor` + `_TRACER` reset) + OTLP graceful-degrade test; close DEFERRED→FIXED-by-test (SC2) ✅ 2026-06-13 (10 otel tests green [8+2]; 1 span hook.before_step + flowin.hook/event/agent_id + scope flowin.agents.hooks.otel_tracing; OTLP-pkg-absent→console degrade; goldens 10/10; lint-imports 4/0; test-only diff; ISS-010 FIXED-by-test)
- [x] 17-03-PLAN.md — ISS-011: per-test `live_skip_reason()` re-check (SKIP not FAIL on mid-sweep expiry) + relaxed self-check + offline expired-creds skip simulation; transient classification untouched (SC3)

### Phase 18: Custom-Workflow UX Completeness

**Goal:** Close cluster E of the 2026-06-13 deep investigation — the "custom workflows are backend-complete but UI-incomplete / has orphaned dual UI" gap. (1) ISS-021: a custom workflow's non-markdown deliverable (HTML/zip) has no faithful FE path — add a type-driven generic deliverable contract (BE emits a `mimetype`/filename hint on `pipeline_complete`; FE renders any declared deliverable via a generic mimetype-dispatched renderer + Files row) so a brand-new SC-001 workflow renders with ZERO per-workflow FE code. (2) ISS-014: delete the orphaned, unrouted capability-palette composer (`WorkflowComposer.tsx` + `CapabilityPalette.tsx` — INV-3/12 dual-impl), and relocate the per-agent model picker into the live agent-composer wiring `model_overrides` into the run path (delivers MODEL-03 reachably); keep the `/api/capabilities` contract (API-02). (3) ISS-019: the WaveTreePanel sits below the 1440×950 fold — fix the left-column flex budget so both panels are visible without scrolling. (4) ISS-015: record the WONTFIX disposition for the generic pipeline-type picker (by-design; the wizards + agent-composer are the intended launch surfaces; a manifest-driven picker is v2/WF-DB-01). FE-weighted; one INV-3-sensitive BE addition (the additive `pipeline_complete` field, neutralized via `_VOLATILE_STRIP_KEYS`). Offline-verifiable; visual confirmation deferred to the Playwright pass.
**Requirements**: ISS-021, ISS-014, ISS-019, ISS-015 (.planning/ISSUES-REGISTER.md — "Deep Root-Cause Investigation", cluster E)
**Depends on:** Phase 17
**Plans:** 5/5 plans complete

**Success Criteria:**

1. A custom/unknown-type workflow whose declared deliverable is HTML renders in a sandboxed iframe (and markdown→markdown, zip/bundle→file view) via a GENERIC mimetype-dispatched renderer — no per-workflow FE branch (SC-001); the resolved deliverable is also listed + downloadable in the Files tab. BE emits `deliverable_mimetype`/`deliverable_filename` on `pipeline_complete`, added to `_VOLATILE_STRIP_KEYS` so the 5 characterization goldens stay byte-identical. (ISS-021)
2. `WorkflowComposer.tsx` + `CapabilityPalette.tsx` are deleted (proven unrouted; no broken imports; FE build + tests green); the per-agent model picker is relocated into the live agent-composer and `model_overrides` reaches the `run_pipeline` payload (or, if relocation is too invasive, deleted with MODEL-03's FE-half recorded as v2 — decision recorded); `/api/capabilities` + `test_capabilities_api.py` retained. (ISS-014)
3. At 1440×950 during an active wave run, the "WAVE / SUBAGENT TREE" heading is fully visible WITHOUT scrolling (heading bottom ≤ viewport height) while the agent panel still scrolls internally — a CSS-only flex-budget fix, no clipped content. (ISS-019)
4. ISS-015 dispositioned WONTFIX in the register with a crisp by-design rationale (wizards + agent-composer are the launch surfaces; generic manifest-driven picker = v2/WF-DB-01). (ISS-015)
5. INV-3 parity holds (5 goldens byte-identical, lint-imports 4/0, zero new tables/migrations); SC-001 honored (generic mimetype dispatch + no workflow-name FE branch); FE `tsc --noEmit` + vitest green.

Plans:

- [x] 18-01-PLAN.md — ISS-021 backend: DeliverableSpec.mimetype + emit deliverable_mimetype/deliverable_filename on pipeline_complete + _VOLATILE_STRIP_KEYS parity guard (wave 1) — Complete 2026-06-13
- [x] 18-02-PLAN.md — ISS-019: flex-budget the left execution column so the wave panel is above the 1440x950 fold (CSS-only, wave 1) — Complete 2026-06-13 (af61f1d3, 81ed1719; live-Playwright fold proof deferred)
- [x] 18-03-PLAN.md — ISS-021 frontend: generic mimetype-dispatched deliverable renderer (HTML->sandboxed iframe / md->markdown / zip->bundle) + generic Files row, live + reopen (wave 2)
- [x] 18-04-PLAN.md — ISS-014: delete the orphaned WorkflowComposer/CapabilityPalette + relocate the per-agent model picker into the live AgentsPopup wiring model_overrides (wave 3)
- [x] 18-05-PLAN.md — ISS-015 WONTFIX disposition + ISS-014 doc reconciliation (issues/requirements/impl registers, wave 1)

### Phase 19: Prompt and Deliverable Adherence

**Goal:** Close cluster D of the 2026-06-13 deep investigation with DURABLE structural fixes (not prompt-only "ask the model nicely") for the three prompt/deliverable-adherence residuals — so they can't silently regress on a non-deterministic model. (1) ISS-006: thread a single shared canonical DB-accessor literal (`getDatabase`) through the app_builder producer + consumer prompts so the generated Jest global-setup imports what the impl exports (no TS2305) + an offline grep pin. (2) ISS-005: add a pure-stdlib `api_prefix` deliverable-validator wired as an EVENT-FREE `post_step` on the app_builder infra-generator step (NOT a `gates:[validation]` gate — that emits events → breaks the golden) that deterministically catches missing `/api/v1` prefixes. (3) ISS-004: apply the existing `_strip_fabricated_tool_xml` sanitizer to the STREAMED `agent_chunk` path (with chunk-straddle buffering) for tool-less agents, so fabricated tool-XML never reaches the live UI stream (today it's stripped only from the accumulated output). INV-3-critical throughout: the validator is event-free, the sanitizer is same-object on clean text + goldens normalize chunks, prompt edits don't perturb scripted goldens — all 5 characterization goldens stay byte-identical. The deferred LIVE re-confirms (ISS-004 chunks clean, ISS-005 `/api/v1` present, ISS-006 no getDb error) run on the now-active `default` Bedrock profile in the consolidated live + Playwright pass after this phase.
**Requirements**: ISS-006, ISS-005, ISS-004 (.planning/ISSUES-REGISTER.md — "Deep Root-Cause Investigation", cluster D)
**Depends on:** Phase 18
**Plans:** 3/3 plans complete

**Success Criteria:**

1. The app_builder producer (`app-code-generator`) + consumer (`app-test-implementation`) AGENT.md bodies share a single canonical `getDatabase` accessor literal (incl. the Jest global-setup file), pinned by an offline acceptance-grep test; reverting either side fails the pin. INV-3-safe (scripted model ignores prompts). (ISS-006)
2. A pure-stdlib `api_prefix` `Validator` capability exists (modeled on `spec_plan_coverage.py`), self-registers, and is wired as an event-free `post_step` on the app_builder infra-generator step — it flags infra endpoints lacking `/api/v1` and writes a `validation_results` row, WITHOUT adding any event to the run (the app_builder golden stays byte-identical). Import-pure (lint-imports 4/0). (ISS-005)
3. The engine sanitizes the streamed `agent_chunk` path (reusing `_strip_fabricated_tool_xml`, with a chunk-straddle buffer) for tool-less agents, so fabricated `<function_calls>`/`<invoke>` XML is removed from the live UI stream, not just the accumulated output — proven by a fault-injection test (a scripted model streams split tool-XML → no `<function_calls>` in emitted chunks; a tool-using agent's identical stream untouched). SC-001: keys on the tool-less/generic condition, never a workflow name. (ISS-004)
4. INV-3 parity holds: the 5 characterization goldens stay byte/event-identical (the validator post_step is event-free; the chunk sanitizer is same-object on clean text); lint-imports 4/0; zero new tables/migrations. The live re-confirms (004/005/006) are recorded as the next live-pass items, not phase blockers.

Plans:

- [x] 19-01-PLAN.md — ISS-006: shared canonical `getDatabase` accessor literal across producer + consumer prompts + offline grep pin
- [x] 19-02-PLAN.md — ISS-005: pure-stdlib `api_prefix` validator wired as an event-free `post_step` on the app_builder infra-generator step
- [x] 19-03-PLAN.md — ISS-004: engine streamed-`agent_chunk` sanitizer (reuse `_strip_fabricated_tool_xml`) with chunk-straddle buffer for tool-less agents

### Phase 20: Workflow Catalog — Data-Driven Browse-and-Launch (realizes WF-DB-01 / closes ISS-015)

**Goal:** Replace the hardcoded home tiles with a data-driven catalog that reads the live `GET /api/workflows` list, shows only user-ready workflows (a new additive `user_launchable` manifest flag) the user's tier entitles, and launches each through the EXISTING run flow — proving the SC-001 dividend: zero engine/kernel edits, no new tables or migrations. Reuse-first: every new surface is bound to an existing analog and net-new UI is minimized.
**Requirements**: REUSE MANDATE (first-class) — reuse existing UI elements and flows wherever possible: CreationHub rows+launch fork+tier gating, DashboardLayout view-state machine, AppHeader nav, AgentModelPicker data-fetch shell, entitlements helpers, the existing run_pipeline + template-wizard launch paths. Additive backend only: `user_launchable`/`display_name`/`description`/`icon`/`launch_surface` on the manifest schema + surfaced via the existing `GET /api/workflows`. Invariants: INV-3 (5 goldens byte-identical) · SC-001 (launchability keyed on the declared flag, never a hardcoded name list) · Ports & Adapters (import-linter 4 kept/0 broken) · INV-5 (no DSL; control-flow keys stay rejected) · additive-only (no new tables/migrations). Full file:line-grounded spec: `20-SPEC.md` in this phase directory.

**Success Criteria**:

1. Catalog renders ONLY `user_launchable` ∧ tier-entitled workflows from a live `GET /api/workflows` fetch — no hardcoded name list; test fixtures (`sample_*`), revisions (`*_revision`), and `od_*` internal types never appear.
2. Idea-box workflows launch through the existing single `run_pipeline` send site; `prototype`/`ppt` route into the existing template wizard (no bare run); gated workflows show the existing lock/upgrade affordance.
3. Net-new UI is minimal and reuse-bound — the catalog is a data-driven CreationHub mounted as one new DashboardLayout view; each new file names the existing analog it copied.
4. Backend change is additive-only — `user_launchable`+display fields on the manifest schema, surfaced through the existing endpoint; no new tables, no migration.
5. INV-3 parity holds (5 characterization goldens byte-identical) · `lint-imports` 4/0 · a mocked Playwright e2e spec asserts filtering + launch + gating · manifest-schema unit test covers the new optional fields while strict-key still rejects `when/if/for/expr`.

**Depends on:** Phase 19
**Plans:** 2/2 plans complete
Plans:

- [x] 20-01-PLAN.md — BACKEND: additive `user_launchable`/`display_name`/`description`/`icon`/`launch_surface` manifest fields + `_optional_bool`/`_optional_str` + `_ALLOWED_TOP_KEYS` widening + surface via `GET /api/workflows` + set flags on the 7 launchable YAMLs + manifest/workflows_api tests + INV-3 goldens-parity + lint-imports 4/0 [wave 1]
- [x] 20-02-PLAN.md — FRONTEND: `getWorkflowDefinitions`+`WorkflowSummary` (api.ts) + `WorkflowCatalog.tsx` (data-driven CreationHub) + `"catalog"` DashboardLayout view + AppHeader nav button + mocked Playwright `ts-z.catalog.spec.ts` + vitest [wave 1]

### Phase 21: Saved Workflows — User-Authored, Named, Persisted Custom Workflows

**Goal:** Let a user compose a custom workflow (agents + per-agent models), **name and save** it from BOTH the catalog AND the main-page custom-workflow composer, see it in the catalog as their own **renameable/deletable** "Your workflows" entry, and launch it through the EXISTING run path. Persistence **completes the half-built `workflows` table** (reuse, not a new table) with the milestone's first additive table-migration; everything else is reuse.
**Requirements**: REUSE-FIRST — persistence REUSES the dormant `WorkflowDefinition`/`workflows` table (`source="user"`) and REMOVES the dead `engine.py` `_persist_workflow_definition` writer it supersedes (INV-12); FE reuses `DeleteModal` (NameWorkflowModal), `WorkflowHistory` kebab (row menu), `admin*` api.ts fetchers (CRUD), the catalog rows + `IdeaInputPage`/`AgentsPopup` Save buttons; run reuses `run_pipeline` (saved `{base_pipeline_type, agent_ids, model_overrides}` re-validated at launch). Additive backend: migration `0021` (+`base_pipeline_type`, +`model_overrides` nullable cols) + a new owner-scoped `/api/user-workflows` CRUD router. Invariants: INV-3 (5 goldens byte-identical — the only engine edit removes a custom-only dead write, dormant on the non-custom goldens) · INV-12 (delete the superseded writer) · SC-001 (saved workflow = pure data, no new pipeline name) · Ports & Adapters (import-linter 4/0; `app→agents` legal) · additive-migration-only (2 nullable cols; `owner_id`+`workspace_id` already present, stamped on create) · security (owner-scoped CRUD IDOR→404; `agent_ids`/`model_overrides` re-validated at save AND launch). Full file:line spec: `21-SPEC.md`.

**Success Criteria**:

1. A user composing a custom workflow can **Save** it (name + optional description) from the main-page composer AND from the catalog; it persists as a `source="user"` `workflows` row scoped to `owner_id`/`workspace_id`/`user_id`.
2. The catalog shows a **"Your workflows"** section listing the user's saved workflows (friendly name), with a per-row menu to **Rename / Duplicate / Delete**; built-in (manifest) rows stay read-only.
3. Launching a saved workflow replays `{base_pipeline_type, agent_ids, model_overrides}` through the EXISTING `run_pipeline` path; `agent_ids` + `model_overrides` are re-validated at launch (a since-disallowed agent/model is rejected, not smuggled).
4. Persistence REUSES the `workflows` table (additive migration `0021` adds only 2 nullable columns; no new table) AND the dead `engine.py` writer it supersedes is **removed** (INV-12 — no dual write); CRUD is owner-scoped (cross-owner read/rename/delete → 404).
5. INV-3 holds — the 5 characterization goldens stay byte-identical (the engine-writer removal is dormant on the non-custom goldens; proven by running the suite) · `lint-imports` 4/0 · backend CRUD + authz tests + a mocked Playwright spec (save → appears in catalog → rename → launch) pass.

**Depends on:** Phase 20
**Plans:** 3/3 plans complete
Plans:
**Wave 1**

- [x] 21-01-PLAN.md — BACKEND spine: reuse the `workflows` table (`source="user"`) +2 nullable cols, additive migration `0021`, owner-scoped `/api/user-workflows` CRUD router (save==launch validation, IDOR→404), REMOVE the dead `_persist_workflow_definition` writer (INV-12), BE tests + 5-goldens parity + alembic up/down + lint-imports [wave 1]

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 21-02-PLAN.md — FRONTEND save + persistence + catalog: api.ts CRUD + `UserWorkflowSummary`, `NameWorkflowModal` (⟵DeleteModal), "Your workflows" section + per-row kebab (rename/duplicate/delete) + "+ Create workflow" in `WorkflowCatalog`, "Save workflow" button in `IdeaInputPage`, catalog vitest [wave 2, depends 21-01]

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 21-03-PLAN.md — FRONTEND launch wiring + e2e: load-bearing `IdeaInputPage` `initialAgentIds`/`initialModelOverrides` preload + guarded re-derive, `onLaunchSaved` prop threaded through `DashboardLayout`, mocked Playwright spec (compose→Save→appears→rename→launch) [wave 3, depends 21-01, 21-02]

### Phase 22: Capability Surfacing and User Empowerment - Universal Runtime UX Completeness

**Goal:** Cash the SC-001 dividend at the UX layer. The kernel + registry already expose ~70 capabilities, but the product surface uses ~a dozen — every advanced capability (fan-out, waves, the Tier#4/5/6 validators, MCP servers, integration providers, executable hooks, exec, repo, merge, isolation, retry, per-step/per-workflow model selection) is sample/fixture-proven or registered-but-unused, and the user has no way to see or opt into them. This phase makes **every registered capability surface visually** in the UI (sourced from the live `GET /api/capabilities` registry, grouped by kind, trust/tier-gated) and gives the user the **power to compose and launch** workflows that opt into the user-allowed ones — through the EXISTING run path, with no kernel workflow-name branches. It also closes the latent wiring gaps the v1.0 audit found: the `model:`/`retry:`/`injects:` manifest keys the compiler silently drops, the friendly-label/reopen-mimetype/home-landing UX gaps, the two open design decisions (N9 artifact retention, N11 premium-model policy), and a consolidated live-Bedrock re-confirm pass. Full evidence: `.planning/v1.0-MILESTONE-AUDIT.md` + the capability-adoption audit + the deferral-ledger sweep (2026-06-14).

**Depends on:** Phase 21 (reuses the catalog + saved-workflows composer + `/api/capabilities` + `/api/user-workflows` CRUD; extends, never forks)

**Requirements** (new families for this phase — to be added to REQUIREMENTS.md at plan time):

- **Capability surfacing (visual):**
  - **SURF-01** — One capability palette/inspector reads the live `GET /api/capabilities` registry and renders EVERY capability kind grouped by kind (strategies · deliverables · validators incl. Tier#4/5/6 `spec_plan_coverage`/`task_done_when`/`design_quality` · gates · context_providers · compaction · task_parsers · merge · isolation · hooks · skills · tools · mcp_servers · integration_providers · runtimes · model_catalog · limits), each showing name, description, `user_allowed`/trust flag, security-gated flag, and config schema — no hardcoded capability list in the FE (SC-001).
  - **SURF-02** — `/api/capabilities` extended additively so every registered capability supplies the display metadata the palette needs; the empty `config_schema: {}` stub (P8) is filled per capability (auth + permission scopes preserved, API-02 contract intact).
  - **SURF-03** — For each launchable workflow the composer shows which capabilities it currently declares (from `GET /api/workflows/{id}` / the compiled plan) so the user can SEE what a workflow uses before composing.
- **User empowerment (compose + use):**
  - **EMP-01** — The live agent-composer lets a user opt a workflow's step(s) into user-allowed capabilities (validators, human/validation gates, context providers, deliverable type, compaction, fan-out, retry, model selection, limits); the selection reaches the run path (saved-workflow payload → compiler/engine) and demonstrably takes effect.
  - **EMP-02** — Trust/tier gating enforced in UI AND server: `user_allowed=False` capabilities (exec, `spawn_subagents`, `security`/`approval` gates, powerful MCP servers) render visible-but-locked (engineer-only / upgrade affordance), never user-composable; the compiler's `_check_trust` (CAP-03) rejects a smuggled grant, re-validated at SAVE and at LAUNCH.
  - **EMP-03** — Saved user workflows (Phase 21) persist the richer per-step capability selections (additive column/JSON on the reused `workflows` table), owner-scoped (IDOR→404), re-validated at launch.
  - **EMP-04** — When a user selects a capability that requires a gate (security/validation/approval), the composer auto-attaches the required gate; the compiler's exec⇒`gates:[security,approval]` coupling (D-01) and the §13 policies stay enforced.
- **Latent manifest-key wiring (verified accepted-but-dropped — `compiler.py:231`/`:505`):**
  - **WIRE-01** — The compiler materializes top-level `model:` and per-step `model:` into `CompiledWorkflow.model`/`Step.model` so manifest-declared model selection is honored by `ModelResolver`'s step/workflow tiers (today silently dropped); INV-3 goldens byte-identical.
  - **WIRE-02** — The compiler materializes per-step `retry:` into `Step.retry` so a manifest can enable the transient-retry wrapper (RESUME-02 reachable from a manifest, not only programmatically).
  - **WIRE-03** — The compiler materializes per-step `injects:` (or removes the key and fails loud) — no allow-listed step key may silently no-op; a test asserts every `_ALLOWED_STEP_KEYS` entry is either consumed or rejected.
- **UX / data-faithfulness fixes (v1.0 audit warnings):**
  - **UXFIX-01** — The catalog shows the friendly `display_name`/`WORKFLOW_LABELS` (not the title-cased raw id): author `display_name:` on the launchable manifests or leave the BE fallback null (P20 WR-01).
  - **UXFIX-02** — `deliverable_mimetype`/`deliverable_filename` persist on the run row (additive column, carries owner_id+workspace_id) and drive history-reopen so a custom BINARY deliverable re-renders faithfully (P18 reopen gap).
  - **UXFIX-03** — The data-driven catalog is the home landing (resolve the home-vs-`CreationHub` dual surface) so "no hardcoded name list" holds on the default view (P20 SC-1 / integration warning).
  - **UXFIX-04** — The generic mimetype-dispatched deliverable renderer is the PRIMARY dispatch path (first-party branches collapse into it or are proven equivalent) so the SC-001 dividend isn't fallback-only (P18 integration warning).
- **Open decisions + live confirmation:**
  - **DECIDE-01** — Resolve N9 (artifact retention default — `run_ttl`=48h vs `keep`/`days:N`); update ART-04 + reconcile the stale "confirm" labels (REPO-02 N6/N10, REPO-04 N5/N7, FANOUT-05 N2).
  - **DECIDE-02** — Resolve N11 (premium-model policy + default fallback chain); update MODEL-05 and reflect the tier policy in the model picker (which models a tier may select).
  - **LIVE-01** — One consolidated live-Bedrock re-confirmation pass on the `default` profile records evidence for the standing deferrals (COMPACT-03 token delta · P6 CR-02 checkpointer fallback · P8 OTLP collector · P13 F1/F4/F5 · P14 SC4 · P16 SC1/SC2 · P19 ISS-004) — or an explicit re-deferral disposition if ISS-018 (the `hexaware-srini` entitlement) still blocks.

**Invariants (bind every plan):** SC-001 (the user composer routes through the capability registry + `trust=user/db`, never a workflow-name branch; activates the built-but-dormant untrusted-manifest path) · INV-3 (5 characterization goldens byte-identical) · INV-13 (`create_deep_agent` only inside the `langchain_deepagents` adapter) · Ports & Adapters (import-linter 4 kept / 0 broken) · INV-5 (no DSL; strict-key rejection preserved) · additive migrations only (every new table/column carries `owner_id` + `workspace_id`).

**Success Criteria** (what must be TRUE):

  1. Every registered capability kind is visible in the UI palette, sourced from a live `GET /api/capabilities` fetch, grouped by kind, each showing name / description / trust (`user_allowed`) / security-gated flag / config schema — and the FE carries no hardcoded capability name list (SC-001).
  2. A user can compose a workflow from the UI that opts into ≥1 previously-unsurfaced user-allowed capability (e.g. a validator + a human gate + a non-default model + retry), SAVE it, and LAUNCH it through the existing run path — and the selection demonstrably reaches execution (the validator fires / the chosen model is used / retry activates).
  3. Privileged capabilities (exec, `spawn_subagents`, `security`/`approval` gates, powerful MCP/integration servers) render visible-but-locked for an unentitled user and are server-rejected if smuggled into a save/launch payload (CAP-03), re-validated at SAVE and LAUNCH.
  4. Manifest `model:` and `retry:` keys are materialized by the compiler and take effect (a manifest-declared model/retry changes behavior); `injects:` works or fails loud — a test proves no `_ALLOWED_STEP_KEYS` entry is accepted-but-dropped.
  5. The data-driven catalog is the home landing showing friendly names; a custom binary deliverable re-renders faithfully on history-reopen; the generic mimetype renderer is the primary deliverable dispatch path.
  6. N9 and N11 are decided and recorded in REQUIREMENTS.md (ART-04 / MODEL-05 updated, the 3 stale "confirm" labels reconciled); the model picker reflects the N11 tier policy.
  7. One consolidated live-Bedrock pass on the `default` profile records evidence for the standing live deferrals, or an explicit re-deferral disposition is recorded if ISS-018 still blocks.
  8. Invariants hold: 5 characterization goldens byte-identical (INV-3) · kernel name-free (SC-001 grep 0) · `create_deep_agent` only in the adapter (INV-13) · import-linter 4/0 · additive migrations only.

**Plans:** 9/9 plans complete
Plans:
**Wave 1**

- [x] 22-01-PLAN.md — WIRE-01/02/03: compiler materializes model:/retry:/injects: + the parametrized _ALLOWED_STEP_KEYS consumed-or-raises guard (wave 1)
- [x] 22-02-PLAN.md — SURF-02: registry _META + describe(); /api/capabilities supplies description + security_gated + populated config_schema additively (wave 1)
- [x] 22-03-PLAN.md — UXFIX-02: additive migration 0022 + WorkflowRun deliverable_mimetype/_filename + reopen-from-persisted (wave 1)
- [x] 22-07-PLAN.md — UXFIX-01/03/04: data-driven catalog as home + authored display_name + generic-primary deliverable dispatch (wave 1)
- [x] 22-08-PLAN.md — DECIDE-01/02: ART-04 keep-by-default + MODEL-05 premium-open + reconcile 3 confirm labels + register 17 families (wave 1)
- [x] 22-09-PLAN.md — LIVE-01: per-item offline evidence record for the 8 standing deferrals (deferred live pass, default profile / Haiku 4.5) (wave 1)

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 22-04-PLAN.md — EMP-02/03/01: activate trust=user compile at save+launch + persist selections in manifest_json + selection-reaches-execution proof (wave 2)
- [x] 22-05-PLAN.md — SURF-01/03 + EMP-02: embedded grouped capability palette in AgentsPopup with visible-but-locked rows (wave 2)

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 22-06-PLAN.md — EMP-01/04 + DECIDE-02: per-agent Advanced expander (validator/gate/model/retry) + auto-attach + drop the model-picker tier filter (wave 3)

### Phase 42: Run Screen State Fidelity — kill legacy full-screen takeovers so clarify, gate, planning, failed and live states match the VelocityAI mocks [B8]

**Goal:** Every run state (planning · live · clarify · review-gate · complete · failed · revision) matches the three VelocityAI run mocks, by REMOVING the legacy full-screen right-panel takeovers so the already-built inline surfaces become reachable, plus the fidelity polish the mocks require, plus the settled agent-detail artifact cards — FRONTEND-ONLY (INV-3/LOCK-B), generically keyed (SC-001), closed on per-state screenshot-diff + human sign-off.
**Requirements:** RUNUI-06, RUNUI-07, RUNUI-08, RUNUI-09
**Depends on:** Phase 41
**Plans:** 11/11 plans complete — frontend-only (INV-3/LOCK-B); per-state gallery sign-off closed the phase. **RUNUI-09 NOT yet met** — see the closeout note (33 mocked-e2e specs assert the pre-Phase-42 UI; dedicated reconciliation pass deferred, `42-.../deferred-items.md` D-42-1).

Plans:

- [x] 42-01-PLAN.md — Fidelity harness: capture planning/clarify-awaiting/gate-awaiting states both sides (Wave 1)
- [x] 42-02-PLAN.md — Kill the 3 takeover branches + auto-tab per state + re-home Cancel + delete QuestionnairePanel (Wave 2)
- [x] 42-03-PLAN.md — Lane composer = plain hint during clarify/gate + failed run drops Preview/defaults Audit/retires DegradedRunAffordance (Wave 3)
- [x] 42-04-PLAN.md — Delete dead code: AgentProgressPanel / WaveTreePanel / TodoCard + tests + stale comments (Wave 3)
- [x] 42-05-PLAN.md — Extract shared artifactPreview module (discriminator + Spec/Tasks/Analysis parsers) + delete ReviewGatePanel.tsx (Wave 3)
- [x] 42-06-PLAN.md — Steps phase pill + label + violet running-row + clarify submit copy + drop extra clarify affordances (Wave 3)
- [x] 42-07-PLAN.md — Live Files-building hero + live Audit badge/monitoring banner (Wave 3)
- [x] 42-08-PLAN.md — Gate = 2 buttons + plan-preview reusing artifactPreview (Wave 4)
- [x] 42-09-PLAN.md — Settled agent-detail artifact cards (pages/tasks/checks + handoff) + F1/F2 deferrals (Wave 4)
- [x] 42-10-PLAN.md — Inline reskin navy→brand (InlineClarify / InlineGate / ResultCard) (Wave 5)
- [x] 42-11-PLAN.md — Full gallery regen + per-state human sign-off + ISS-035/036/037 + F1/F2 + register/ROADMAP reconcile (Wave 6)

> **Closeout (42-11):** full run-screen fidelity gallery regenerated across every state (planning · live · clarify · gate · complete · failed), each paired against its mock; the clarify/gate TARGET frames corrected to the Live mock's canonical Steps-active state; ND register carries the Phase-42 divergences (**ND-W/ND-X/ND-Y**, ND-U SUPERSEDED, W0-42 RESOLVED). Registers reconciled: **ISS-035/036** flipped `OPEN`→`RESOLVED` (code landed 32-05, VERIFIED `32-VERIFICATION.md` Truth #8); **ISS-037** TodoCard clause closed (42-04); **F1** (coverage/counts aggregate) + **F2** (event-free `sections` extractor) recorded as deferred backend/additive follow-ups; the Phase-42 IMPLEMENTATION-REGISTER entry (deletions ledger + ND register + F1/F2) added. `tsc --noEmit` clean; `vitest` failure set = the 8 pre-existing baseline (zero net-new).
>
> **RUNUI-09 deferred (mocked-e2e reconciliation).** 33 `ts-*` mocked-e2e specs are red at HEAD because they assert the **pre-Phase-42** run-screen UI — the deleted full-screen `ReviewGatePanel` (ts-n ×9) / `QuestionnairePanel` "Quick Setup" (ts-m ×7) takeovers, the changed terminal/cancel/streaming/clarify-gate chrome (ts-i/j/q/r/x/chat), plus some pre-existing stale assertions that predate Phase 42 (e.g. ts-a TS-A-06's retired "NEW" pill, self-documented). Waves 42-02..42-10 changed the run-screen `src` but never reconciled these specs (only `zzz-baseline.spec.ts` was touched in-phase). This is a dedicated e2e-reconciliation pass (re-anchor selectors / `test.fixme` the deleted-panel specs to the inline surfaces — **never delete a spec**), tracked in `42-.../deferred-items.md`. RUNUI-09 stays **Pending** until that pass lands.

### Phase 28: Chat Contracts & Guards [A0]

**Goal:** Every contract the later phases build against is pinned before code: event vocabulary + golden guards, Steps artifact-derivation rules, the live-state contract, the e2e chat driver, and the ND-1..ND-9 decision records.
**Depends on:** — (first v2.0 phase; v1.0 close-out is the milestone entry gate)
**Success Criteria:**

1. `chat_message`/`chat_reply` registered in `_DOCUMENTED_EVENT_TYPES` + volatile keys in `_VOLATILE_STRIP_KEYS`, with a characterization proof that the 5 goldens stay byte-identical (chat events never fire on golden paths).
2. Artifact-block derivation contracts written for Steps L2 (pages/tasks/checks/construction ← their exact data sources) and every run-screen figure pinned to its producing field (incl. `context_sources` verification).
3. The D-12 live-state contract table exists as UI-SPEC input; the mockWs chat driver contract exists.
4. ND-1..ND-9 each have a recorded decision.

**Plans:** 3/3 plans complete

- [x] 28-01-PLAN.md — Golden-neutrality guards + characterization proof (chat event vocabulary + volatile keys; CHAT-06)
- [x] 28-02-PLAN.md — Steps-L2 artifact-derivation contract + figure-to-field pinning + D-12 live-state contract (UI-SPEC input)
- [x] 28-03-PLAN.md — mockWs e2e chat-driver contract + resolved-decisions record (LOCK-A..G, ND-1..ND-13)

### Phase 29: Transport Cutover + Chat Backbone [A1]

**Goal:** The transport becomes SSE-down + REST-up in full (D-13, WS run-path deleted at exit), and a user message reaches a run over the new transport, persists durably, routes by run state, and shapes the next agent dispatch — with browser-native reconnect/reopen fidelity.
**Depends on:** Phase 28
**Success Criteria:**

1. Wire-parity characterization green (the SSE stream replays the recorded WS frame sequences identically for the 5 golden pipelines); all inbound-handler test suites ported 1:1 to the REST endpoints; SSE+REST built ADDITIVELY alongside `/ws/chat` behind a transport flag (LOCK-B — NO deletion this unattended run; the WS-delete + ratchets + ledger row are a deferred supervised follow-up). Wire-parity characterization still built + green (CHAT-07).
2. `POST /api/runs/{id}/messages` (idempotent by client `message_id`) persists as `run_events` rows; a full conversation survives page reload → native `Last-Event-ID` auto-reconnect → reopen; a gate answered via REST while the stream is down resumes correctly on reattach.
3. The mechanical router delivers turns per state: clarify answer, gate action (approve/reject/redo+instructions/**update_specs** — routes to the shipped KAN-101 loop; terminal-fenced per KAN-100; event-driven per KAN-94), steering note, revision.
4. A steering note lands in the next agent's composed context via `ectx.steering_notes` + `=== USER GUIDANCE ===` (offline fault-injection proof); consume-once semantics hold.
5. Narrator `chat_reply` cards emit for clarify/gate/pipeline/deliverable milestones.
6. INV-3 goldens byte-identical; lint-imports 4/0; kernel name-free (SC-001 grep 0).

**Plans:** 10/10 plans complete

Plans:

- [x] 29-01-PLAN.md — Wire-parity characterization harness (binding gate: SSE projection ≡ recorded WS frames, 5 goldens) [wave 1]
- [x] 29-02-PLAN.md — Per-run SSE stream `GET /events/stream` + Last-Event-ID resume + stream_attached handshake + gate re-arm (D-14g/h) [wave 2]
- [x] 29-03-PLAN.md — REST commands: gate (4 actions + KAN-100 fence) / answers / cancel, suites ported 1:1 [wave 3]
- [x] 29-04-PLAN.md — REST commands: run launch (+ image caps) / revisions / user_message POST+stream shim [wave 4]
- [x] 29-05-PLAN.md — Attach/replay matrix (fresh·mid·live·terminal·cross-owner·restart·gate-answer-while-down = SC-2) [wave 5]
- [x] 29-06-PLAN.md — e2e mock-SSE driver + additive chat frames (123 mocked specs stay green) [wave 1]
- [x] 29-07-PLAN.md — FE transport adapter + app-level connection provider + server-derived reattach (D-14 a–f), flag-gated [wave 2]
- [x] 29-08-PLAN.md — Steering seam `ectx.steering_notes` + `=== USER GUIDANCE ===` + ND-11 decision record (first design task) [wave 1]
- [x] 29-09-PLAN.md — `POST /runs/{id}/messages` (idempotent) + mechanical intent router (CHAT-01/02/05) [wave 5]
- [x] 29-10-PLAN.md — Narrator `chat_reply` cards (clarify/gate/pipeline/deliverable/spec_revision + deep-link nonce) [wave 6]

### Phase 30: Uploads & Multimodal [A2]

**Goal:** Images and files enter runs — as vision input, as workspace files agents read, and as sticky launch context.
**Depends on:** Phase 29
**Success Criteria:**

1. `POST /api/runs/{id}/files` (owner-scoped, IDOR→404) stores bytes under the run's `RunSandbox`.
2. *(Run-entry image path ALREADY LANDED 2026-07-07 — IMAGE-INPUT-PLAN waves `edw`/`frv`/`gvq`, offline shape test green.)* Remaining: **per-turn** images ride the Phase 29 `chat_message` path into the next dispatch's content blocks.
3. Uploaded documents are agent-readable (`read_file`) AND their extracted text is sticky context present in every subsequent `agent_input`.
4. Launch-time attachments (incl. images) ride `run_pipeline`.

**Plans:** 5 plans (planned 2026-07-08) — *(scope-trimmed: image-INGESTION spine already landed via IMAGE-INPUT-PLAN waves edw/frv/gvq; image-persistence DEFERRED per ND-10/LOCK-E)*

- [x] 30-01-PLAN.md — UPLD-01: `POST /api/runs/{id}/files` (owner-scoped, capped) → RunSandbox + extract-to-`.uploads` sidecar [wave 1] ✅ 2026-07-08
- [x] 30-02-PLAN.md — UPLD-03: `context_provider:uploaded_files` sticky context (zero engine edits, SC-001) [wave 2] ✅ 2026-07-08
- [x] 30-03-PLAN.md — UPLD-02 residue: per-turn image carrier on the Phase-29 message path + ND-10 no-persistence lock [wave 1] ✅ 2026-07-08
- [x] 30-04-PLAN.md — UPLD-04: client-side image resize + ND-10 "image not retained" reopen placeholder [wave 1] ✅ 2026-07-08
- [x] 30-05-PLAN.md — IMPLEMENTATION-REGISTER entry for the landed image-input cluster (edw/frv/gvq) + ND-10 payload-transient disposition [wave 1] ✅ 2026-07-08

### Phase 31: Chat Lane MVP [A3]

**Goal:** The chat lane ships inside the current skin — streaming bubbles, result cards deep-linking into tabs, quick actions, attachments — before any reskin.
**Depends on:** Phases 29–30
**Success Criteria:**

1. The revived kit renders the family-stitched transcript (D-02) with streaming markdown + `aria-live`.
2. Result cards deep-link into the run tabs (nonce'd seam); gate/clarify quick-actions work in-lane and mirror Steps.
3. Attachment UI: file picker + paste + drag-drop + image preview + client resize; token-usage widget shows P26 fields.
4. Open-design borrow-list mechanisms 1–7 integrated with Apache-2.0 attribution/NOTICE.

**Plans:** 7/7 plans complete

Plans:
**Wave 1**

- [x] 31-01-PLAN.md — Borrow-list pure primitives (#1 partial-json, #2 extractStreamingJsonString, #4 buildBlocks) + Apache-2.0 NOTICE (CHATUI-01) [wave 1]
- [x] 31-02-PLAN.md — Borrow-list rendering (#3 tool-renderer registry, #5 measured virtualizer, #7 ThinkingBlock/todo/file-ops) (CHATUI-01) [wave 1]
- [x] 31-03-PLAN.md — Chat transcript hook (useRunChat, D-02 family-anchored) + ChatMessage type + #6 nonce'd deep-link seam (CHATUI-01) [wave 1]
- [x] 31-05-PLAN.md — In-lane gate/clarify quick-actions (4 gate actions incl update_specs KAN-101, terminal fence KAN-100, retained edit KAN-98) (CHATUI-02) [wave 1]

**Wave 2**

- [x] 31-06-PLAN.md — Attachment UI (paste + drag-drop + resizeImage, ND-10 placeholder) + P26 token widget (CHATUI-03) [wave 2, depends 31-03]

**Wave 3**

- [x] 31-04-PLAN.md — Revived chat lane composition root: streaming markdown + aria-live/role=log + narrator result cards + absorbed controls (CHATUI-01) [wave 3, depends 31-01/02/03/05/06]

**Wave 4**

- [x] 31-07-PLAN.md — Integrate: mount RunChatLane in execution left column + transport-agnostic wiring (LOCK-B) + PreviewPanel deep-link target + delta-verified mocked chat e2e + first data-testids (CHATUI-01/02/03) [wave 4, depends 31-04]

### Phase 32: Run-Screen Redesign [A4]

**Goal:** The run screen converges to the Hexaware Run design: chat lane left; Preview/Steps/Files/Audit right; Steps is a 3-level drill-down.
**Depends on:** Phase 31
**Success Criteria:**

1. Token layer (black/beige/one-blue `#3C2CDA`, Manrope/Heebo) + primitives land first; run screens consume them (no new hardcoded palette).
2. Steps renders the 3-level drill-down (overview spine → agent detail + Context-received rail → task detail, dual-source) from real events; gate/clarify render inline in Steps.
3. Audit tab reads the 3 new endpoints (`gate_events`/`validation_results`/`exec_runs`) with counters/filters + CSV/JSON export; governance keeps the status palette; one-chroma elsewhere.
4. Failed/degraded/cancelled states faithful (P16 affordances + chat card); e2e green with brittle color assertions fixed + `data-testid`s added.

**Plans:** 10/10 plans complete
Plans:
**Wave 1**

- [x] 32-01-PLAN.md — Token layer: globals.css @theme rewrite + Manrope/Heebo fonts + token-guard test (Wave 1)
- [x] 32-02-PLAN.md — Primitives: Button/Card/Tabs/Badge/Pill in components/ui + tests (Wave 1)

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 32-03-PLAN.md — 3 additive owner-scoped Audit read endpoints (IDOR->404) + tests (Wave 2)
- [x] 32-04-PLAN.md — SC-001 golden-neutral review_gate_ready flag (update_specs_eligible) + 5 goldens byte-identical (Wave 2)
- [x] 32-05-PLAN.md — Chat-lane state: ISS-035 cancel marker + ISS-036 runId + SC-001 L2 fix + flag parse (Wave 2)

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 32-06-PLAN.md — RunChatLane reskin + absorb AgentProgressPanel + cancelled/failed/degraded terminal renders (Wave 3)
- [x] 32-07-PLAN.md — Right tab shell reskin + Thinking->Steps + Preview manual switcher (Wave 3)
- [x] 32-08-PLAN.md — Steps 3-level drill-down + dual-source L3 + KAN-99 cap + inline gate/clarify + SC-001 de-literalize (Wave 3)
- [x] 32-09-PLAN.md — Audit tab repoint to 3 endpoints + counters/filters + CSV/JSON export (Wave 3)

**Wave 4** *(blocked on Wave 3 completion)*

- [x] 32-10-PLAN.md — E2E hardening: re-anchor brittle color assertions to token/data-testid, verify BY DELTA (Wave 4)

### Phase 33: Concierge + Compaction [A5]

**Goal:** Free-form conversation works on every run via ONE orchestrator capability, and long transcripts stay inside budget.
**Depends on:** Phase 29 (Phase 32 not required)
**Success Criteria:**

1. `chat:concierge` (proposal-only tools, confirm chips, Haiku default, via `deep_agent_runner` — INV-13) answers run questions from real run data and its proposals execute only through existing channels.
2. `compaction:chat_history` + `context_provider:conversation` bound the composed history (proof: long-transcript context stays under budget with recent turns verbatim).
3. Post-run chat turns produce revision runs stitched into the family transcript.
4. A brand-new custom workflow gets lane + router + Concierge with zero new code (SC-001 proof).

**Plans:** 5/5 plans executed — VERIFIED (PASS-WITH-CONCERNS); offline-complete, live wiring + H1/M2/M3 → Phase 34 (--no-transition)
Plans:
**Wave 1**

- [ ] 33-01-PLAN.md — Wave 1: compaction:chat_history + context_provider:conversation + registry lockstep (66→68) [D-08, SC-2]

**Wave 2** *(blocked on Wave 1 completion)*

- [ ] 33-02-PLAN.md — Wave 2: chat:concierge capability (DeepAgentRunner/Haiku, read + proposal-only tools) + registry lockstep (68→69) [D-05, INV-13, SC-1]

**Wave 3** *(blocked on Wave 2 completion)*

- [ ] 33-03-PLAN.md — Wave 3: router free-form→Concierge escalation + proposal→channel disposal + revision-family stitching [D-04, D-05, D-02, SC-1, SC-3]

**Wave 4** *(blocked on Wave 3 completion)*

- [ ] 33-04-PLAN.md — Wave 4: FE — confirm-chip UX + compact affordance + composed-context/token display (extend RunChatLane/ChatTokenWidget) [D-05, D-08, SC-1]
- [ ] 33-05-PLAN.md — Wave 4: SC-001 throwaway-manifest proof + manifest chat: data key (INV-5) + INV-3 golden neutrality (5 goldens byte-identical) [SC-001, INV-3]

### Phase 34: Live Pass & Closure [A6]

> **⚠ SUPERSEDED by Phase 43** (Concierge Live Wiring and Live-Pass Closure) — never executed; its full worklist is carried and updated for Phases 35–42 in `43-CONTEXT.md`. Kept here for provenance.

**Goal:** Everything proven live on Bedrock; registers updated; deferrals swept.
**Depends on:** Phases 31, 33 (32 recommended)
**Success Criteria:**

1. Live multi-turn chat with images on a real run; steering mid-run observed in the next dispatch; Concierge Q&A live.
2. `cache_read > 0` confirmed incl. multi-turn cache-point placement (P26 deferral closed or explicitly re-dispositioned; ISS-033 noted).
3. Playwright live chat suite green; ISSUES/FIX registers + IMPLEMENTATION-REGISTER updated.

### Phase 35: Shell Chrome + Reskin Pages [B1]

**Goal:** The app shell converges: dark top bar, nav pill (Home · Library · My Workflows), profile menu, notifications — plus all reskin-only pages.
**Depends on:** Phase 32 (token layer)
**Success Criteria:**

1. Shell chrome matches the Workspace v2 idiom on tokens (no per-page palette forks); nav = Home · Library · My Workflows (D-11).
2. Account Settings, Template/DS pickers, Review-gates popover, Library restyled with real controls where the mock had static text.

**Plans:** 7/7 plans complete
**Wave 1**

- [x] 35-01-PLAN.md — Shell chrome: dark top bar + nav pill (My Workflows) + a11y profile menu + notifications panel + baseline capture (Wave 1)

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 35-02-PLAN.md — Account Settings reskin (preserve wiring; no unbacked fields) (Wave 2)
- [x] 35-03-PLAN.md — Template picker + detail/custom/card modals reskin (Wave 2)
- [x] 35-04-PLAN.md — Design-System picker (LOCK-F ~14) + DS modals + Review-gates reskin (Wave 2)
- [x] 35-05-PLAN.md — Library (Agents/Skills/Hooks) reskin with real controls (Wave 2)
- [x] 35-06-PLAN.md — Login reskin + dark brand panel + Register tokenize (ND-12) (Wave 2)
- [x] 35-07-PLAN.md — Admin reskin (keep Runs/Role/Joined + pw-create; defer Status/Last-active) (Wave 2)

### Phase 36: Home + History + My Workflows [B2]

**Goal:** The three restructured list surfaces + the new Run detail page.
**Depends on:** Phase 35
**Requirements:** SHELL-02, SHELL-03
**Success Criteria:**

1. Fused Home: prompt launcher + deliverable grid + recents (merges `input`/`home` views).
2. History: Today/Earlier/Older grouping, token/duration sort, real delete, revision families intact.
3. "My Workflows" rename + working kebab actions; `WorkflowCatalog`→`HomeLaunchGrid` rename (D-11) — "Catalogue" reserved for the future marketplace.
4. Run detail/reopen page live off a run-summary endpoint aggregating existing data (agents, KPIs, failure banner, version timeline).

**Plans:** 5/5 plans executed
**Wave 1**

- [x] 36-01-PLAN.md — `WorkflowCatalog`→`HomeLaunchGrid` rename (D-11) + Fused Home (launcher + grid + recents) + HomeLaunchGrid reskin (Wave 1)
- [x] 36-02-PLAN.md — Backend `GET /api/runs/{id}/summary` owner-scoped read endpoint aggregating existing data + tests (Wave 1)

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 36-03-PLAN.md — "My Workflows" label reskin (drop "Catalogue") + kebab CRUD verify test (Wave 2)
- [x] 36-04-PLAN.md — Run detail page (`RunDetailPage`) + `getRunSummary` client, reusing shared surfaces (Wave 2)

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 36-05-PLAN.md — History Today/Earlier/Older grouping + tokens/duration sort + delete + KAN-96/KAN-92 preserve + RunDetailPage promotion + reskin (Wave 3)

### Phase 37: Configure Unification [B3]

**Goal:** One generic per-run setup surface for every deliverable type; the agent drawer and workflow dialog give capabilities a real home.
**Depends on:** Phase 36; ND-1/ND-7/ND-8 decided
**Plans:** 5/6 plans executed
**Success Criteria:**

1. Configure screen: Describe + Templates + Design System + Review Gates + Workflow Settings for ANY deliverable type (declared run inputs, not prototype-only wizardry).
2. Agent drawer (Overview/Skills/Hooks/Config) live against real data; Workflow dialog surfaces declared capabilities/context/compaction with `user_allowed` gating.
3. Draft-run persistence per ND-1 disposition.

Plans:
**Wave 1**

- [x] 37-01-PLAN.md — D-15/C: generic template/DS declared-signal run-launch seam (backend, additive, byte-identical goldens) [Wave 1]

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 37-02-PLAN.md — Configure screen (generic per-run setup accordions) + client-side draft (ND-1) [Wave 2]
- [x] 37-03-PLAN.md — Composer reskin (live /api/capabilities palette + AdvancedExpander + Save to user-workflows) [Wave 2]
- [x] 37-04-PLAN.md — Wizard NEW-BUILD unified Template->DS->Discovery stepper + Web/Deck toggle + template-page reskin [Wave 2]

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 37-05-PLAN.md — DS band-card restructure (real ~14) + wire orphaned DiscoveryForm as stepper step 3 [Wave 3]
- [ ] 37-06-PLAN.md — Agent drawer 4-tab (Config surface-only, ND-7) + Workflow dialog (user_allowed gating) [Wave 3]

### Phase 38: Analytics, Estimates & Notifications [B4]

**Goal:** The data-backed shell tail: real analytics, estimates, notifications.
**Depends on:** Phase 35 (independent of 36/37)
**Success Criteria:**

1. Date-scoped analytics aggregations power the dashboard (filters actually recompute).
2. Home deliverable cards show real time/agent estimates; notifications feed live (gate/running/done/failed).

**Plans:** 5/5 plans complete
Plans:
**Wave 1**

- [x] 38-01-PLAN.md — Owner-scoped `/api/analytics/summary` aggregation endpoint (Wave 1)
- [x] 38-02-PLAN.md — Extracted token-styled SVG DonutChart + BarChart, a11y-labelled (Wave 1)
- [x] 38-03-PLAN.md — Notifications feed: gate kind + wire failed/cancelled/gate transitions (Wave 1)

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 38-04-PLAN.md — AnalyticsPage rewire to endpoint + full Phase-32 reskin + chart swap (Wave 2)

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 38-05-PLAN.md — Home deliverable-card real estimates (~N agents · ~Xm) (Wave 3)

### Phase 39: Run Screen Mock Fidelity [B5]

**Goal:** Bring the run/execution screen to full visual fidelity with the VelocityAI-New-UI mocks (`Hexaware Run` / `Run - Live` / `Run - Failed`) — the left conversation lane, the run header, all four tabs (Preview / Steps / Files / Audit) with every sub-navigation level, across the settled / live-streaming / failed states — as-is. Re-aligns the run screen Phase 32 built.
**Depends on:** Phase 32 (Run-Screen Redesign — the code this re-aligns), Phase 36 (D-11 nav), Phase 33 (Concierge)
**Requirements:** RUNUI-06, RUNUI-07, RUNUI-08, RUNUI-09
**Success Criteria:**

1. Each run-screen surface (left lane, run header, Preview/Steps/Files/Audit, and the three run states) matches its mock to the intended-divergence register — proven by a side-by-side screenshot-diff against the mock, not a prose claim.
2. Net-new as-is affordances land: Share, the Version ▾ menu, the "Renders as" deliverable-type switch, and the fuller Audit categories (secret-scan / performance / behavioral).
3. Data stays real & live (SC-001): no cloning the mocks' hardcoded values; the deliverable renderers are reused, not rebuilt; intended divergences (brand "VelocityAI", "My Workflows", nav underline) are preserved.
4. The mocked e2e suite is green again against feat/ui-2 (home-grid / launch-flow / run-family fixes) and the fidelity screenshot harness runs under `frontend/e2e`.

**Plans:** 7/7 plans executed

Plans:

- [x] 39-07-PLAN.md — Repair stale mocked-e2e harness + formalize the fidelity screenshot oracle (Wave 1)
- [x] 39-01-PLAN.md — Left conversation lane: structured transcript + lane header + live/failed states (Wave 2)
- [x] 39-02-PLAN.md — Steps tab: overview spine → 2-col agent detail (sticky Context received) → task drill (Wave 2)
- [x] 39-03-PLAN.md — Files tab: dark Final-output hero + agent-outputs timeline + Run-input cards (Wave 2)
- [x] 39-04-PLAN.md — Audit tab: 6-stat grid + coverage banner + fuller categories over real fetches (Wave 2)
- [x] 39-05-PLAN.md — Run header (Version/Share/Download/status) + tab order + shell wiring (Wave 3)
- [x] 39-06-PLAN.md — Preview browser chrome + "Renders as" switch wrapping the reused renderers (Wave 4)

### Phase 40: Shell Mock Fidelity (restyle surfaces) [B6]

**Goal:** Bring the SHELL surfaces to full visual fidelity with the VelocityAI-New-UI `Hexaware Workspace v2` mock — Home, Library (Agents/Skills/Hooks +agent-detail), Analytics, Account Settings (4 tabs), Workflow History (3 states), and Catalogue / My Workflows — as-is, using the SAME anti-drift method Phase 39 used for the run screen. RESTYLE-FIRST: only the close-to-mock / merely-blocked surfaces, plus the harness fixes that unblock them. The Configure single-screen rebuild + the Composer full-page rebuild are DEFERRED to Phase 41.
**Depends on:** Phase 39 (the fidelity oracle + shell oracle scaffolding this reuses), Phase 35/36/38 (the shell surfaces this re-aligns), Phase 36 (D-11 nav)
**Requirements:** SHELL-01, SHELL-02, SHELL-03, SHELL-04
**Success Criteria:**

1. Each in-scope shell surface + every sub-view/sub-tab/state matches its `Hexaware Workspace v2` mock to the intended-divergence register — proven by the side-by-side shell gallery + a HUMAN sign-off (a blocking checkpoint), not a prose claim.
2. Net-new as-is affordances land on live data: the Home 3×2 deliverable card grid + "Jump back in" recents, the Library card grids, the Settings richer profile form, the History filter chips / Sort tabs / date groups, the Catalogue card grid.
3. Data stays real & live (SC-001/ND-D): no cloned mock values, no fabricated fields; intended divergences preserved (ND-A brand · ND-B "My Workflows" · ND-C nav underline · ND-W "Run History" · ND-X no Voice · ND-Y no fabricated profile fields · ND-Z Library drawer → Phase 41).
4. The blocked Catalogue is stubbed (`/api/user-workflows`) + the empty surfaces seeded, the shell fidelity oracle is formalized (per-surface gallery), and each touched surface's mocked-e2e spec is re-anchored green.

**Plans:** 7 plans (2 waves: 40-01 harness → 40-02..40-07 surfaces, parallel/disjoint files)

Plans:

- [x] 40-01-PLAN.md — Stub `/api/user-workflows` + seed History/Analytics/recents + formalize the shell fidelity oracle + own SHELL-01..04 (Wave 1) — Complete 2026-07-12 (c6c28c4f)
- [x] 40-02-PLAN.md — Home: prompt-under-h1 (Attach + Build, no Voice) + 3×2 live card grid + "Jump back in" recents (Wave 2) — Complete 2026-07-12 (caa8e185; human-approved, closed to ND-A/D/X)
- [x] 40-03-PLAN.md — Library: h1 + count + search header + Agents/Skills/Hooks card grids (agent-detail drawer → Phase 41, ND-Z) (Wave 2) — Complete 2026-07-12 (be885c58; +count-line capabilities hint; human-approved, closed to ND-A/B/C/D/Z)
- [x] 40-04-PLAN.md — Analytics: styling + number-format parity pass over the live endpoint (Wave 2) — Complete 2026-07-12 (fc536cab + chart-primitive fidelity fix: tall bars + one dark peak, enlarged donut; human-approved, closed to ND-A/C/D + new ND-AA)
- [x] 40-05-PLAN.md — Account Settings: Usage & Limits relabel + real-data richer profile form (ND-Y) + four mock-parity tabs (Wave 2) — Complete 2026-07-12 (ba3a0fe9 + label-fix dbdc5e61; human-approved, closed to ND-A/C/D/Y/AB/AC)
- [x] 40-06-PLAN.md — Workflow History: keep "Run History" (ND-W) + filter chips + Sort tabs + date groups + 3 states (Wave 2) — Complete 2026-07-12 (552e0673 + row-level fidelity fix: per-row token/elapsed + purple version chip + always-visible kebab, Newest/Longest/Tokens sort, EARLIER THIS WEEK bucket, near-black active chip; human-approved, closed to ND-W/D)
- [x] 40-07-PLAN.md — Catalogue / My Workflows: unblock + restyle the Catalogue grid, keep "My Workflows" (ND-B), 3 states (Wave 2) — Complete 2026-07-12 (f02fc671; human-approved, closed to ND-A/B/C/D/AD)

### Phase 41: Configure Unification + Composer Rebuild [B7]

**Goal:** Deliver the two structural REBUILDS Phase 40 deferred, to full mock/proposal fidelity using the same anti-drift method: (1) CONFIGURE — unify the split flow (IdeaInputPage + LaunchWizard + ConfigureScreen across two routes) into the mock's ONE "Configure your run" screen (Step-1 brief + four inline accordions Templates·Design System·Review Gates·Workflow Settings + overlays), reviving the dormant ConfigureScreen and DELETING the superseded impls (INV-3); (2) COMPOSER — a full-page custom-workflow surface with a Simple ⇄ Canvas view toggle bound to the AgentsPopup shared data model — the Simple view mock-fidelity to `Hexaware Composer.dc.html`, the Canvas view a hand-rolled node-graph designer matching the USER-APPROVED proposal `composer-canvas-proposal.html`. Plus the additive Composer Run-once wiring through the existing onStartPipeline seam (no engine change), and the Library agent-detail drawer (Phase-40 ND-Z deferral). Presentation-only except the one additive Run-wiring task.
**Depends on:** Phase 40 (the shell fidelity oracle + shots this reuses), Phase 39 (the fidelity method), Phase 37 (SHELL-04 Configure surface this closes)
**Requirements:** CFGUI-01, CFGUI-02, CMPUI-01, CMPUI-02, CMPUI-03, CMPUI-04, CMPUI-05, HARN-01 (closes SHELL-04)
**Success Criteria:**

1. The unified "Configure your run" screen (Step-1 brief + four accordions + overlays) matches its mock — screenshot-diff + a HUMAN sign-off — and no dual Configure implementation survives (IdeaInputPage brief-launch + LaunchWizard + WizardStepper deleted, INV-3); Start-run launches through the existing onStartPipeline seam.
2. The Composer is a full-page surface (entry from Home + edit-from-My-Workflows) with a Simple ⇄ Canvas toggle bound to the AgentsPopup shared data model; the modal shell is replaced (INV-3). The Simple view matches `Hexaware Composer.dc.html` (HUMAN sign-off); the hand-rolled Canvas view matches the approved proposal `composer-canvas-proposal.html` (design-match HUMAN sign-off, ND-AJ; no graph library).
3. Composer Run-once launches through the existing onStartPipeline seam (functional test) + Save-to-catalogue reuses createUserWorkflow — additive FE only, no engine/backend/manifest change, no fabricated cost (ND-AG). The Library agent-detail drawer (ND-Z) lands.
4. Data stays real & live (SC-001/ND-D): live registries, "None selected" until picked (ND-AF), no fabricated cost; intended divergences preserved (ND-A/B/C/D carried + ND-AE..AJ new). The Configure template/DS/ppt APIs are stubbed + seeded and the Phase-41 fidelity oracle is formalized (per-surface regenerable + a canvas target).

**Closeout (2026-07-14 — verifier PASSED 8/8, `41-VERIFICATION.md`):** SC-2/3/4 DELIVERED + human-signed-off (Simple mock-match · Canvas proposal-match · Run-once functional · Library drawer ND-Z resolved; ND register ND-AE..AM). **SC-1 REVERTED by user decision** (quick-260713-rcf, `131c4e30`): the unified Configure single-screen was abandoned because a bare `prototype` launch fails the backend `missing_template_context` guard — template/design-system selection stays in the intact `LaunchWizard`; INV-3 is honored via DELETION of ConfigureScreen (not unification). SC-2's "the modal shell is replaced" clause is SUPERSEDED — the AgentsPopup modal is RETAINED + REUSED (additive; not a dual implementation — the user-approved framing). Whole phase additive-FE-only (backend untouched, verified).

**Plans:** 7 plans (6 waves: 41-01 harness → 41-02 Configure build → 41-03 Configure unify+delete → 41-04 Composer shell+Simple → {41-05 Canvas ‖ 41-07 Library drawer} → 41-06 Run wiring)

Plans:

- [x] 41-01-PLAN.md — Harness: template/DS/ppt API stubs + the Phase-41 fidelity oracle (ND-AE..AM) + B7 requirement docs (Wave 1)
- [x] 41-02-PLAN.md — Configure build — BUILT (d7a947e1) then REVERTED (quick-260713-rcf, 131c4e30): the unified Configure screen was abandoned; prototype/ppt kept on the wizard (a bare `prototype` launch fails the backend `missing_template_context` guard); INV-3 honored via DELETION of ConfigureScreen (+ accordions + /workflow/configure + lib/draft.ts).
- [x] 41-03-PLAN.md — Configure unify+delete wiring — BUILT (88f4db97) then REVERTED with 41-02; LaunchWizard + IdeaInputPage RETAINED (the delete was never executed).
- [x] 41-04-PLAN.md — Composer shell + Simple view (mock-fidelity, human-signed-off); the AgentsPopup modal is RETAINED + reused — additive (corrected from "delete the modal") (Wave 4; ND-AK)
- [x] 41-05-PLAN.md — Composer Canvas view: hand-rolled SVG node-graph + inline config rail + 2×2 docked summary matching the approved proposal (design-match signed-off); extracted `applyLeverPatch`/`useAgentCapabilities` (Wave 5; ND-AL)
- [x] 41-07-PLAN.md — Library agent-detail drawer: `AgentCapabilitiesModal` → right drawer via an `asDrawer` variant + Overview-body tightening (ND-Z RESOLVED, human-signed-off) (Wave 5; ND-AM)
- [x] 41-06-PLAN.md — Composer Run wiring: Run-once → `onStartPipeline('custom')` + Save-to-catalogue → `createUserWorkflow`; functional mocked-e2e (Wave 6; CMPUI-04)

### v2.0 Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 28. Chat Contracts & Guards [A0] | 3/3 | Complete    | 2026-07-07 |
| 29. Chat Backbone [A1] | 10/10 | Complete   | 2026-07-08 |
| 30. Uploads & Multimodal [A2] | 0/? | Not started | — |
| 31. Chat Lane MVP [A3] | 7/7 | Complete    | 2026-07-08 |
| 32. Run-Screen Redesign [A4] | 10/10 | Complete   | 2026-07-08 |
| 33. Concierge + Compaction [A5] | 5/5 | Verified⚠ (P34 live) | — |
| 34. Live Pass & Closure [A6] | 0/? | Superseded → Phase 43 | 2026-07-15 |
| 43. Concierge Live Wiring & Live-Pass Closure [A6-redux] | 2/9 | In Progress|  |
| 35. Shell Chrome + Reskin Pages [B1] | 7/7 | Complete   | 2026-07-09 |
| 36. Home + History + My Workflows [B2] | 4/5 | In Progress|  |
| 37. Configure Unification [B3] | 5/6 | In Progress|  |
| 38. Analytics, Estimates & Notifications [B4] | 5/5 | Complete   | 2026-07-10 |
| 39. Run Screen Mock Fidelity [B5] | 7/7 | Complete | 2026-07-12 |
| 40. Shell Mock Fidelity (restyle) [B6] | 7/7 | Complete | 2026-07-12 |
| 41. Configure Unification + Composer Rebuild [B7] | 7/7 | Complete (SC-1 Configure reverted) | 2026-07-14 |

### Phase 43: Concierge Live Wiring and Live-Pass Closure [A6-redux]

**Goal:** The milestone-end live pass — **carries/supersedes Phase 34** (never executed), updated for Phases 35–42. **Part A** (offline wiring): decide the transport fork (A.0 — SSE-activation vs WS-routed Concierge), then wire the dormant Concierge to a live caller (A.1 — attach the `RunChatLane` Concierge props + **re-route the settled-run free-text path so a status question is answered, not launched as a `*_revision`** + fix H1/M2/M3/M1 + the dead proposal-drain), mount the SSE provider (A.2), the steering live-drain (A.3 — also delivers per-turn images, DEF-30-03-1), and the narrator live call-site (A.4). **Part B** (needs Bedrock SSO): the 7 live checks (multi-turn chat+images · mid-run steering · Concierge Q&A · `cache_read>0` incl. multi-turn cache placement · LaunchWizard live launch · analytics/notification live · live Playwright chat suite) + the `default`-profile live re-confirms. **Part C** (closure): register/deferred-items sweeps, the WS→SSE deletion + INV-12 exit gate (LOCK-B), `/gsd-complete-milestone` v2.0. Full worklist + verified current file:line integration points + the stale-ref map in `43-CONTEXT.md`.
**Requirements:** carries Phase-34 SC (live chat/images/steering/Concierge/cache/launch/analytics/Playwright) + the exhaustive live-deferred register (CONTEXT §5).
**Depends on:** Phase 33 (the `chat:concierge` subsystem this wires), Phase 29 (chat backbone / SSE / steering / narrator seams), Phase 42 (the run-screen restructure that moved the FE integration points), Phase 30/37/38 (offline halves whose live-confirm folds in). **Supersedes Phase 34 [A6].**
**Status:** SUPERVISED — Part A offline-doable; Part B needs live AWS Bedrock + the supervised SSE cutover; Part C is the exit gate. NOT autonomous.
**Plans:** 2/9 plans executed

Plans:

**Wave 1 — Part A offline wiring (autonomous)**

- [x] 43-01-PLAN.md — Backend Concierge defects: M2 (serialize read-tool ORM rows) + M3 (thread compiled onto _ConciergeCtx) + drain (drain_proposals) + H1 (durable-row confirm disposal, IDOR→404) + M1 (non-approve gate default) [A.1]
- [x] 43-02-PLAN.md — FE Concierge composer re-routing: extend the useRunChat send contract + generic ask-vs-change classifier + attach the RunChatLane Concierge props at the mount [A.1]
- [x] 43-03-PLAN.md — Narrator live call-site (engine event sink) + deep-link nonce hardening (WR-02: additive 0025 table, owner-scoped, single-use) [A.4]
- [x] 43-04-PLAN.md — Shared cached-invoke helper (ISS-033/034): route SmartPlanner/ClarifyEngine/handoff Test+Compliance through cache-eligible, token-counted calls [A.x]

**Wave 2 — Part A offline wiring (autonomous)**

- [x] 43-05-PLAN.md — Steering live-drain + per-turn images: live-ectx registry (_live_ectx_for_run resolves the running ectx) + engine === USER GUIDANCE === drain (closes DEF-29-09-1 / DEF-30-03-1) [A.3] (depends 43-01, 43-03 — shared run_commands.py / engine.py)

**Wave 3 — Part C SSE cutover (supervised)**

- [ ] 43-06-PLAN.md — Mount RunConnectionProvider behind the SSE flag (A.2) + flip NEXT_PUBLIC_SSE_TRANSPORT ON + verify B.3 live Concierge Q&A (grounded, confirm-gated) [A.0, A.2, B.3]

**Wave 4 — Part B live checks: chat/steering/cache (supervised)**

- [ ] 43-07-PLAN.md — Live: B.1 (multi-turn chat + per-turn/document images) · B.2 (mid-run steering in next agent's live prompt) · B.4 (cache_read>0 + multi-turn placement + ISS-033 counted) [B.1, B.2, B.4]

**Wave 5 — Part B live checks: launch/analytics/e2e (supervised)**

- [ ] 43-08-PLAN.md — Live: B.5 (LaunchWizard live launch prototype+ppt) · B.6 (analytics round-trip + notification push) · B.7 (live Playwright chat suite) + default-profile re-confirms [B.5, B.6, B.7] (depends 43-07 — shared 43-LIVE-EVIDENCE.md)

**Wave 6 — Part C closure (supervised)**

- [~] 43-09-PLAN.md — WS→SSE deletion (INV-12 exit gate) + register reconciliation + /gsd-complete-milestone v2.0 [C.1, C.2, C.3, C.4] — **SUPERSEDED BY PHASE 44** (re-scoped to a hard cutoff; the C.3 deletion + run_revision retirement move to Phase 44; the milestone close becomes a separate later step). Not executed as 43-09.

### Phase 44: SSE-only hard cutoff run_revision retirement and Part-B automation

**Goal:** The **hard** WS→SSE cutoff (supersedes 43-09's flag-branch scope). Remove the `NEXT_PUBLIC_SSE_TRANSPORT`/`SSE_TRANSPORT_ENABLED` flags entirely, make SSE the sole transport, and delete `/ws/chat` — keeping `/ws/handoff` (D10 survivor). This is a FE-rewiring + BE-relocation project (the backend REST/SSE twin was built additively in Phase 29; the gap is the FE still emitting WS frames + the pipeline down-channel being WS-only). **W1** re-source the pipeline reducer from SSE + launch→attach bootstrap (the enabler); **W2** rewire gate/cancel/questionnaire to REST (gates → `POST /{id}/gate` to preserve `edited_content`); **W3** retire `run_revision` via Strategy A (`handleRevisePpt` → REST `/revisions`, full parity) + the confirm-first refinement chip + 2 pre-existing bug fixes; **W4** relocate the shared transport-neutral infra out of `websocket.py` + delete `/ws/chat` + `useWebSocket` + the flag; **W5** re-point the mocked e2e harness to SSE + a CI banned-pattern gate; **W6** a scripted Part-B live-smoke suite (B.6b + ISS-033 live tail). Grounded worklist + verified file:line seams in `44-CONTEXT.md`.
**Requirements**: carries 43-09's C.3 (WS deletion / INV-12 exit gate) — re-scoped to a hard cutoff — + the run_revision retirement (D1/CTX-04) + the Part-B live re-confirm tail. LOCK-B precondition ("human validates the live cutover") is SATISFIED per `43-LIVE-EVIDENCE.md`.
**Depends on:** Phase 43 (the supervised SSE cutover this deletes behind), Phase 29 (the additive REST/SSE twin). **Supersedes Phase 43-09.**
**Status:** SUPERVISED — offline FE-rewire + BE-relocation + tests, then a live SSE smoke + a live-Bedrock Part-B lane. **Does NOT close the v2.0 milestone** (separate later step).
**Plans:** 11/12 plans executed

Plans:

- [x] 44-01-PLAN.md — W1: re-source the pipeline down-channel from SSE + launch->attach bootstrap [wave 1]
- [x] 44-02-PLAN.md — W3a: confirm-first refinement chip (RunChatLane) [wave 1]
- [x] 44-03-PLAN.md — W4a: relocate shared transport-neutral infra to app/api/run_engine.py (endpoint stays) [wave 1]
- [x] 44-04-PLAN.md — W2: rewire gate(->/gate, WR-03)/cancel/questionnaire to REST [wave 2]
- [x] 44-05-PLAN.md — W3b: run_revision retirement Strategy A (handleRevisePpt -> REST /revisions) + 2 bug fixes [wave 3]
- [x] 44-06-PLAN.md — W4-FE: remove the flag + delete useWebSocket + extract useHandoffSocket survivor [wave 4]
- [x] 44-07-PLAN.md — W4b+W3c: delete /ws/chat endpoint + run_revision WS handler + BE flag (INV-12 exit gate) [wave 5]
- [x] 44-08-PLAN.md — W5b: backend WS-test migration to REST + delete obsolete WS tests [wave 6]
- [x] 44-09-PLAN.md — W5a: e2e harness -> SSE + re-point the mocked suite [wave 5]
- [x] 44-10-PLAN.md — W5c: CI banned-pattern gate (the hard-cutoff ratchet) [wave 6]
- [x] 44-11-PLAN.md — W6: offline Part-B (ISS-033 aux-token fold + mocked-SSE B.6b) [wave 6] — Complete 2026-07-16 (0dadd5da, b4a20c55)
- [ ] 44-12-PLAN.md — W6 live lanes + supervised live SSE smoke (autonomous:false, Bedrock SSO) [wave 7]
