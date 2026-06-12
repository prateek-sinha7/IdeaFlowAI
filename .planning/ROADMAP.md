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
**Plans:** 0 plans

**Success Criteria** (what must be TRUE):

  1. `run_revision` against a completed parent run drives the real revision pipeline agents (model runs observed) and the final deliverable is a revised artifact reflecting the instruction — not the instruction/context blob
  2. The revision artifact persists with `derived_from` lineage to the parent original, owner/workspace-scoped, and revision-of-revision still resolves (FR-014 chain link 1)
  3. Stub-pinning tests (`test_revision_intelligence`, `test_run_revision_fe_contract`) updated to the real-dispatch contract; characterization goldens stay byte/event-identical for non-revision runs (INV-3); no workflow-name literal added to the kernel (SC-001)
  4. Live-confirmed on real Bedrock as part of the milestone-end live pass (FE-exact `run_revision` frame → revised deck in the preview)

Plans:

- [ ] TBD (run /gsd-plan-phase 14 to break down)

---
*Roadmap created: 2026-06-06*
*Source: specs/003-workflow-engine-decoupling/plan.md §25 (12 active phases; plan Phase 7 / ECS deferred to v2)*
