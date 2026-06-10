---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: executing
last_updated: "2026-06-10T08:51:08.836Z"
last_activity: 2026-06-10 -- Phase 09 plan 02 complete (migration 0017 repositories + RunSandbox refold)
progress:
  total_phases: 12
  completed_phases: 8
  total_plans: 51
  completed_plans: 49
  percent: 67
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-06)

**Core value:** A brand-new custom workflow can replicate `prototype` by manifest + AGENT.md only — with zero engine edits (SC-001).
**Current focus:** Phase 09 — local-workspace-runtime-repo-workflows-no-exec-4a

## Current Position

Phase: 09 (local-workspace-runtime-repo-workflows-no-exec-4a) — EXECUTING
Plan: 5 of 6
Status: Ready to execute
Last activity: 2026-06-10 -- Phase 09 plan 02 complete (migration 0017 repositories + RunSandbox refold)

Progress: [██████░░░░] 60% (7/12 phases complete; Phase 08 = 8/8 plans complete, awaiting verification)

## Performance Metrics

**Velocity:**

- Total plans completed: 76
- Average duration: ~7 min
- Total execution time: ~0.35 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 1 [0A] | 2 | ~9 min | ~4.5 min |
| 02 | 3 | - | - |
| 03 | 2 | - | - |
| 04 | 5 | - | - |
| 05 | 7 | - | - |
| 06 | 5 | - | - |
| 07 | 11 | - | - |
| 08 | 8 | - | - |

**Recent Trend:**

- Last 5 plans: 01-01 (~6 min, 2 tasks, 12 files), 01-03 (~3 min, 2 tasks, 2 files)
- Trend: —

*Updated after each plan completion*
| Phase 07 P11 | ~40 min | 3 tasks | 15 files |
| Phase 01 P02 | ~12 min | 2 tasks | 11 files |
| Phase 01 P04 | ~9 min | 3 tasks | 4 files |
| Phase 02 P02-01 | 75min | 2 tasks | 7 files |
| Phase 02 P02-03 | ~12 min | 2 tasks | 5 files |
| Phase 03 P01 | 25min | 2 tasks | 2 files |
| Phase 03 P02 | ~20min | 3 tasks | 2 files |
| Phase 04 P01 | 4min | 2 tasks | 5 files |
| Phase 04-manifest-compiler-1a P02 | 4min | 2 tasks | 4 files |
| Phase 04-manifest-compiler-1a P03 | 7min | 3 tasks | 20 files |
| Phase 04 P04 | 38min | 3 tasks | 5 files |
| Phase 04-manifest-compiler-1a P05 | 10min | 3 tasks | 9 files |
| Phase 05 P01 | 2min | 2 tasks | 3 files |
| Phase 05 P02 | 7min | 2 tasks | 9 files |
| Phase 05 P03 | 3min | 2 tasks | 3 files |
| Phase 05 P04 | 35min | 3 tasks | 6 files |
| Phase 05 P05 | 7min | 2 tasks | 4 files |
| Phase 05-typed-artifacts-persistence-ownership-1b P06 | ~40min | 3 tasks | 8 files |
| Phase 05 P07 P07 | ~55 min | 3 tasks | 23 files |
| Phase 06-model-policy-1c P01 | 18min | 2 tasks | 4 files |
| Phase 06-model-policy-1c P02 | 5min | 1 tasks | 2 files |
| Phase 06 P03 | 15min | 2 tasks | 4 files |
| Phase 06 P04 | 18min | 2 tasks | 4 files |
| Phase 06 P05 | 35min | 2 tasks | 4 files |
| Phase 07 P01 | 35min | 2 tasks | 10 files |
| Phase 07 P02 | ~30min | 2 tasks | 15 files |
| Phase 07 P03 | 13min | 1 tasks | 4 files |
| Phase 07 P04 | 95min | 2 tasks | 5 files |
| Phase 07 P05 | ~150min | 3 tasks | 21 files |
| Phase 07 P06 | 25min | 3 tasks | 9 files |
| Phase 07 P07 | 6min | 2 tasks | 2 files |
| Phase 07 P08 | ~25min | 2 tasks | 3 files |
| Phase 07 P09 | ~75min | 3 tasks | 13 files |
| Phase 07 P10 | ~55min | 3 tasks | 14 files |
| Phase 08 P01 | ~30min | 4 tasks | 18 files |
| Phase 08 P02 | ~45min | 3 tasks | 19 files |
| Phase 08 P03 | 40min | 3 tasks | 15 files |
| Phase 08 P04 | ~50min | 3 tasks | 11 files |
| Phase 08 P07 | 18min | 3 tasks | 11 files |
| Phase 09 P01 | ~8min | 3 tasks | 9 files |
| Phase 09 P02 | ~12min | 2 tasks | 8 files |
| Phase 09 P03 | ~18min | 3 tasks | 14 files |
| Phase 09 P04 | ~20min | 2 tasks | 8 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table (and the plan's §32 decision log + §31 ledger).
Recent decisions affecting current work:

- Init: Granularity=fine → 12 sequential phases mapped 1:1 to plan §25 sub-phases (0A…6); ECS (plan Phase 7) deferred to v2
- Init: Research skipped — plan.md is the authoritative complete spec (plan-ingestion preference)
- Init: Models=quality (Opus); execution=sequential (strangler safety); git tracking=on
- [Phase ?]: 01-02: event-snapshot is an order-canonical multiset (build-loop interleaving is nondeterministic); strict order covered by assert_seq_contiguous + phase3/01-01 sequence tests. VOLATILE_SENTINEL='<normalized>'; contract dicts imported from phase3 verify (no divergence).
- [Phase ?]: 01-04: import-linter scaffold anchored on kernel→app.api boundary (non-vacuous, green); vulture allow-listed in pyproject; banned-pattern gate single-file allow-list + injected-fixture non-vacuity; tests/agents now run in CI (offline backend:characterization) — closes D-16 false-green.
- [Phase ?]: ExecutionContext revision_* fields kept flat (not nested RevisionState) to keep consumer rewrites mechanical
- [Phase ?]: current_task_block parked on ExecutionContext as a Phase-7-temporary home (D-02); Phase 7 reclaims it into TaskLoopStrategy
- [Phase ?]: Migration-ledger L14/D1 rows left unflipped in 02-01; L14 enforced via acceptance grep, ledger flip deferred to 02-02/02-03
- [Phase ?]: L16 ownership: pure assert_owns (authz.py) raises PermissionError above the seed graceful-degrade try (D-07); by-convention _derive_parent_owner, Phase 5 relocates
- [Phase ?]: 03-01: build-task-2+ context compaction wired (_extract_html_skeleton on the is_build_task_2_plus branch); offline >=50% gate measures 96.9% reduction; L13 stays ☐ (Phase 7 deletes).
- [Phase ?]: 03-02: parity reference derived from committed golden; validation parity = zero net-new failure events + clean pipeline_complete; golden re-baseline confirmed no-op (scripted fixed-HTML); live token-delta is opt-in evidence (D-04)
- [Phase ?]: 04-01: CapabilityRegistry keyed by (kind,name) registers 14 names only (D-07); is_registered pure set-membership; resolve_alias lifts agents.registry._OD_ALIAS_BASE single source (MAN-05); base.py = 6 typing.Protocol ports, plan-domain types typed Any to avoid inbound dep on 04-02 plan.py
- [Phase ?]: 04-04: engine sources agent membership/deliverable/clarify/planner from CompiledWorkflow; pipeline_type reduced to id-alias resolver (MAN-04/MAN-05); behavioral L1-L13 branches byte-identical
- [Phase ?]: 04-04: 1A drift assertion compares compiled plan vs registry MEMBERSHIP (not validation.dag); execution order stays resolver topo-DAG; INV-3 snapshots green
- [Phase ?]: 04-05: /api/workflows reclaimed for manifest-derived definitions (compile_for_run + get_pipeline_agents, no DB); run-history moved to /api/runs with IDOR filter + export sanitization preserved; 10 frontend refs repointed (clean break, no aliases)
- [Phase ?]: 05-01: agents/artifacts/ package path per D-02; kernel-pure typed substrate (graph owns sha256 hashing + per-(run,kind) versioning)
- [Phase ?]: 05-02: Extended existing workflows table (WorkflowDefinition) additively — no second workflows table (RESEARCH #5 collision)
- [Phase ?]: 05-02: Default-workspace backfill inlined in Alembic 0014 (D-03); owner_id/workspace_id NOT NULL on new tables, nullable+backfilled on extended tables
- [Phase ?]: 05-03: relocated assert_owns into the single default-deny ScopedStore helper (agents/authz.py); reads filter owner+visibility (ArtifactRef) / owner+workspace (run/ws/event/caps); assert_owns is a real parent-owner store lookup; old execution_engine/authz.py deleted (INV-12); engine call-site rewiring deferred to 05-04 (vetted intra-phase gap)
- [Phase ?]: 05-04: Typed substrate dual-written alongside the live accumulated_outputs mirror (strangler); engine reads migrated typed-first; mirror deletion deferred to 05-06 (INV-3).
- [Phase ?]: 05-04: Disk principal (user_id or 'anon') decoupled from DB owner (anon:<session_id>) to keep RunSandbox paths byte-identical (CTX-05); single seq/event_id sink at execute() emit boundary, stripped from the 0A characterization multiset.
- [Phase ?]: 05-05: owner-scoped /artifacts (lineage tree) + /events (seq>after replay) route through the single ScopedStore; cross-owner -> 404
- [Phase ?]: 05-06: producer/revision/clarifications writes use visibility=workspace so same-owner cross-run _handle_revision reads pass the owner+visibility scope filter; thin-store artifact consumers fully migrated (05-07 deletion precondition TRUE)
- [Phase ?]: 05-07: deleted accumulated_outputs mirror + thin-store artifact half + WorkflowArtifact (0015); typed ArtifactGraph sole impl; phase 05 DONE; L15+D2 done
- [Phase ?]: 06-01: ModelCatalog is the single source of model ids/metadata (INV-12); AVAILABLE_MODELS/_VALID_MODEL_IDS are projections
- [Phase ?]: 06-01: catalog stores both tier (display) and cost_class (canonical), asserted consistent (D-04); name-only registry membership (D-03)
- [Phase ?]: 06-02: AGENT.md model parsed with a load-time type guard only; catalog-membership validation deferred to the resolver (06-03), keeping the loader catalog-free (D-09)
- [Phase ?]: 06-02: AgentSpec.model is fully additive (str|None, default None); all ~80 existing agents load unchanged
- [Phase ?]: 06-03: ModelResolver constructed after compile_for_run() (CompiledWorkflow.model seeds tier 4), carried on ectx.model_resolver; the 3 _run_agent model sites consult it via _resolve_model — INV-3 snapshots byte/semantic-identical
- [Phase ?]: 06-03: _resolve_model falls back to threaded model_id when ectx.model_resolver is None (direct unit-style _run_agent invocations) — parity-safe (Rule 1 fix); step=None this plan (06-04 wires Step lookup); SmartPlanner left on session id (RESEARCH #2)
- [Phase ?]: 06-03: ModelPolicy.max_tokens stays doc-only (cap stays settings.MAX_OUTPUT_TOKENS); _is_transient_throttle + set_chain/current/advance shipped for the 06-05 fallback loop
- [Phase ?]: 06-04: model_overrides validated at ingress (model_id in ModelCatalog.ids() AND agent_id in run agents) reject with invalid_model_override before execute; {} to SQL NULL on persist (INV-3 parity); no new migration
- [Phase ?]: 06-05: MODEL-02 fallback = APPROACH B (engine rebuild-and-retry), NOT with_fallbacks; B1 runner re-raises classified throttles, engine advances ModelResolver + rebuilds via create_runner (build_model only), bounded by chain length, exhaustion surfaces a visible agent_error
- [Phase 07]: 07-01: D-02 resolve() seam = static dict over a separate _IMPLS map (distinct from _KNOWN), explicit lazy install(); unknown name raises before any lookup (T-07-01-01); D-03 ctx.runner is one object-typed KernelServices handle (concrete class deferred to 07-04); single_shot/task_loop lifted behind ExecutionStrategy with strategy-local task scratch, no kernel/app import, no deep-agent graph (INV-13)
- [Phase ?]: 07-02: 4 deliverable resolvers decompose _resolve_final_output by deliverable.name (no pipeline_type); ppt owns both carousel-sanitize sites (PARITY-07); opendesign/previous_run providers behind ports; 3 prototype OD loaders RELOCATED to execution_engine/od_context.py (move-don't-copy single home, NOT into the capability which would break the import-linter app-ban; provider composes from boundary od_context per A6); previous_run assert_owns-before-seed with propagating PermissionError (L16)
- [Phase ?]: 07-03: html_skeleton compaction = byte-identical lift of engine._extract_html_skeleton behind resolve('compaction','html_skeleton'); structural contract (name+compact()), no CompactionStrategy port added; 0C >=50% reduction gate re-pointed at the capability (PARITY-04 preserved) + byte-parity test pins capability==engine; engine copy left live until 07-05
- [Phase ?]: 07-04: KernelServices(ctx.runner) delegates to engine _run_agent/_run_validation_fix_loop for byte+event parity; per-step dispatch via resolve(strategy).run, deliverable via resolve(deliverable).resolve, generic context injector over context_provider caps; L1-L13 DEAD-not-deleted; 5-pipeline parity GREEN.
- [Phase 07]: 07-05: SC-001 LANDED — L1-L13 deleted from the kernel + agents/prototype/ removed (INV-12 exit gate); the kernel knows NO workflow by name, enforced by a kernel-scoped banned-pattern HARD-FAIL (assert 0 `if pipeline_type ==`/`spec.id ==` in agents/execution_engine/). L10 single-file readback + L3 mid-stream ppt sanitize MIGRATED to key off the declared compiled.deliverable strategy (output_length/PARITY-07/09 held; revision excluded via ectx.is_revision_workflow). L6 ALWAYS_CLARIFY re-homed to compiled.clarify.mode=="auto"; in-place revision setup + post-revision validation gate key off the declared previous_run provider (CompiledWorkflow compiled at run entry). migration-ledger L1-L13 flipped to ☑ kernel-scoped (L4/L8 + L11 refined to the leak construct; L1 keeps live REVISION_FILE_NAME; L11 keeps live survivors _run_validation_fix_loop/_load_template_example); L14/L15/L16 re-confirmed; D1 voided. Stale engine-internal suites retired (behavior covered by capabilities + characterization).
- [Phase ?]: 07-06: opendesign restored to byte-faithful L12 lift; DS preamble (CR-01), builder-gated example (CR-02), task-2+ suppression (CR-03); engine threads ectx.current_spec_tools per D-03, no spec.id/pipeline_type (INV-1); context_message de-blinded (removed from _VOLATILE_STRIP_KEYS + 5 golden regenerated parity-stable) + dedicated parity assertion; PARITY-03/09 closed
- [Phase 07]: 07-07: deleted the dead DUAL validation fix-loop from task_loop.py (INV-3/INV-12; WR-07/WR-08, cluster B). Removed the `else: # pragma: no cover` fallback, the in-strategy `_run_validation_fix_loop`, `_SkippedRender`, the duplicated `_select_issues_to_fix`/`_static_issue_sigs`/`_console_sigs`, and `_MAX_FIX_ATTEMPTS`. TaskLoopStrategy.run now delegates validation+fix UNCONDITIONALLY to runner.run_validation_fix_loop (the single engine home). _FakeRunner re-pointed onto run_validation_fix_loop FIRST (RED→GREEN guard) importing _select_issues_to_fix from engine. run_fix_agent pruned from the strategy docstring; kernel_services already advertised none. Goldens byte-unchanged; characterization green in clean session. Pre-existing test_strategies→characterization session pollution logged to deferred-items.md (out of scope).
- [Phase 07]: 07-08: REVERSES the 07-06 adjudication ("pinned==correct" was false — the de-blind captured POST-refactor drifted bytes). Built an engine-INDEPENDENT acd1636 context_message ORACLE (tests/agents/characterization/oracle/) via PINNED-BYTES (verbatim legacy block strings + per-block provenance, NOT running the legacy method — that would re-couple to engine/od_loader). build_oracle_message covers 4 prototype agent classes honoring every acd1636 gate (per-injects, is_build_task_2_plus suppression, _is_builder example gate, raw injection parts, bare END markers, skeleton wrapper, unconditional TEMPLATE COMPLIANCE). Stability test PASSES; a divergence test (drives _drive('prototype'), extracts build-agent context_message) XFAILS — the documented 07-09 acceptance target. Baseline pinned to acd1636 (07-06 used 1d9234b^; _is_builder gate present at both → baseline-invariant). The 5 goldens left UNTOUCHED (re-pinning to oracle is 07-09 work after the engine is byte-correct).
- [Phase 07]: 07-10 (WR-04/WR-06/CR-06): revision-intent is now a DECLARED per-deliverable flag `DeliverableSpec.revises_existing` (manifest `deliverable.revises_existing` → compiler → compiled model). engine sources `_is_revision_workflow` from it, NOT from `"previous_run" in context_providers` (the proxy that misclassified the 4 non-prototype previous_run workflows). The previous_run provider gates the seed + assert_owns on `ctx.is_revision_workflow` (WR-06: a forward build with a stray parent_run_id no longer seeds). The kernel revision block is EVICTED: seed-existing-artifact → previous_run provider (parameterized by deliverable.name, single-home extract/slim helpers); pre-edit baseline + post-edit fix-loop → a new DECLARED `revision_validation` post-step capability (PostStep port + `post_step` capability kind + `Step.post_step`, invoked by the dispatch loop; agent_id from the compiled step, baseline via `KernelServices.compute_revision_baseline` so the capability never imports the kernel). REVISION_FILE_NAME, the prototype-revision-agent literal (incl. _AGENT_KIND_MAP entry), the DELIBERATE EXCEPTION comment, and the orphaned engine helpers + `import re` are deleted. INV-1=0, WR-04 proxy=0, CR-06 literals=0; lint-imports KEPT; 578 agent tests pass; characterization revision + phase5 + L16 parity held.
- [Phase 08]: 08-01 (CAP-01/02/03 + VALID-03 + D-12): `install()`/`_register_builtins` DELETED (INV-12) → `@register(kind,name,*,user_allowed=False)` self-registration decorator binds `(kind,name)->impl` + `_TRUST` at impl-module import; `discover()` is the single successor (explicit subpackage imports incl. best-effort `app/agents/validators/`, idempotent via `_DISCOVERED`, never at compiler import — Pitfall 1 held). `_KNOWN` kept as the declared impl-free literal allow-list the decorator ADDS to (compiler membership path stays impl-free). 11 Phase-7 built-in impl classes now carry `@register` decorators. Six new ports in base.py (PromptAssemblyPolicy/AgentRuntimeAdapter/HookHandler/ToolProvider/SkillProvider/HookProvider); new `tool`/`skill`/`hook`/`runtime` KIND strings accepted (no central if/elif). CAP-03 trust check: `WorkflowCompiler.compile(trust='file')` default-trusted kwarg threaded inline at the existing per-reference `is_registered` site (no forked path); user/db manifest referencing a non-`user_allowed` cap → CompilerError NAMING `(kind,name)`; file manifests unrestricted (Phase-4/7 parity). VALID-03 single source: ONE `map_severity` (P0→CRITICAL/…/P3→LOW, unknown→ValueError) in `agents/capabilities/validators/severity.py`, pure-stdlib import-clean (no `@register`/discover side-effect) for the 08-02 gate before 08-04. D-12 folded: autouse registry save/restore reset fixture in `test_strategies.py` (snapshots AFTER `discover()` — import-side-effect binding is one-shot per process) → no same-session characterization pollution. 5 characterization snapshots byte/event-identical; lint-imports/banned-pattern/migration-ledger green.
- [Phase 07]: 07-11 (CR-05/CR-07 — the SC-001 PROOF): the deliverable filename is THREADED from `ctx.deliverable.name` (single_file.py pattern) to `persist_task_html`/`run_validation_fix_loop`/`engine._run_validation_fix_loop` as a REQUIRED `filename` (no prototype default; the prototype manifest declares `prototype.html` so it passes through byte-identical). Added DECLARED `TaskSource.source_step`/`spec_step` (prototype declares prototype-plan/-specify; the STRATEGY owns the legacy fallback so the compiler stays thin, INV-5) — no hardcoded prototype-plan/-specify on the routed path. `previous_run` + `task_loop._write_reference_files` honor the declared `compiled.seed_files` (the `from_run` list) threaded onto `ectx.seed_files`, with `_SEED_FILES` fallback (authored manifests are {} → fallback fires → byte-identical, Pitfall 2). SC-001 PROVEN: a brand-new NON-prototype `sc001_task_loop` workflow (manifest + 3 AGENT.md only, using only registered task_loop/single_file/heading_tasks) runs end-to-end producing `app.py` — test asserts the deliverable is app.py, the dual-write location is app.py, the fix-loop operated on app.py, the task list came from the DECLARED source_step, and all proof artifacts live OUTSIDE backend/agents/execution_engine/ (zero engine edits to run the new workflow). 581 agent tests pass; 5-pipeline characterization + banned-pattern + migration-ledger + L16 parity held. Phase 07 gap-closure COMPLETE.
- [Phase ?]: 08-02: GateHandler.evaluate returns a GateOutcome value; the engine _evaluate_gates owns the yield
- [Phase ?]: 08-02: human gate delegates to the unchanged _run_review_gate (GATE-03 parity, no re-baseline); approval/security added to literal _KNOWN
- [Phase ?]: 08-03: effective tool perms = intersect(owner, workflow, step); AGENT.md only lowers (D-07)
- [Phase ?]: 08-03: tool_provider impls emit string tool-keys (capability ↛ app); factory resolves keys → concrete tools
- [Phase ?]: 08-03: F2 _build_runner_tools DELETED (grep→0, ledger ☑) after parity proven vs 5 characterization snapshots
- [Phase 08]: 08-04 (VALID-01/02/04/05 + D-04/05/06/10): Validator registry backbone. `DeliverableContext` (kernel-pure target: path/content/runner-handle/step/task_meta) is what a registered `Validator` receives. `html_static`/`html_render` migrated to registered app-side Validators (`app/agents/validators/`) wrapping `static_check`/`render_check`, reaching the heavy checks ONLY via `target.runner` (the KernelServices handle — NO kernel→app import; import the PORT `agents.capabilities.base.Validator` + `@register`, the legal app→capabilities direction; lint 3 kept/0 broken). Generic FixPolicy fix-loop: `run_validation_fix_loop` driven by a `FixPolicy` (deliverable name + max_attempts) — NOT hardcoded `prototype.html`; it parameterizes the engine's SINGLE `_run_validation_fix_loop` internals, default reproduces Phase-7 byte-for-byte (max_attempts=2). Tier#4/5/6 = `spec_plan_coverage`/`task_done_when` (pure-stdlib KERNEL-side) + `design_quality` (app-side, WARNINGS-FIRST/non-blocking — emits only P2/P3, never blocks); each registered+run+≥1 test manifest, severity via the SINGLE imported `map_severity` (08-01, grep=1, 0 new defs). Each validator run writes an owner/workspace-scoped `validation_results` row (ScopedStore; cross-owner read=∅, T-08-04-ID). task_loop RE-POINT (D-06): drives the registered `html_static`/`html_render` validators ADDITIVELY + EVENT-FREE after the byte-identical fix-loop (only persists validation_results rows) → 5 characterization snapshots byte/event-identical in a clean session, re-point parity PROVEN, NO re-baseline. `revision_validation` STAYS a post_step (gate conversion would NOT be byte/event-identical — the post_step runs the revision-baselined fix sub-agent loop the generic gate doesn't replicate; decided with `test_characterization_prototype_revision.py` evidence). `_KNOWN` + lockstep registry count bumped 22→25 (expected membership growth). The strategy builds FixPolicy/DeliverableContext via handle FACTORIES (`runner.make_fix_policy`/`runner.deliverable_context`) since import-linter forbids `agents.capabilities → agents.execution_engine`. lint-imports/banned-pattern/migration-ledger + 5 snapshots green.
- [Phase 08]: 08-05 (AGENTRT-01/02/03/05 + SKILL-01 / F1/F3/F5): three factory leaks lifted behind declared capabilities + the inline originals DELETED (INV-12, parity-gated). **F5** `AgentRuntimeAdapter` (`runtime:langchain_deepagents`, `user_allowed=False`) WRAPS `DeepAgentRunner` via a factory **build seam** (`RuntimeBuildContext.build`, a bound zero-arg callable) — the runtime capability NEVER imports `app`/`create_deep_agent` (import-linter + INV-13); `create_deep_agent` stays ONLY in the allow-listed `deep_agent_runner.py` (RESEARCH Q2 — allow-list unchanged); `create_runner` selects `resolve("runtime", "langchain_deepagents")` (future `claude_code_cli`/`custom_runner` slot in with no kernel edit). Sanctioned the `langchain_deepagents` capability MODULE NAME in the INV-13 local-module ban (single-entry `_ALLOWED_LOCAL_MODULE_PATHS`; it is the registered runtime id, import-clean of library+create_deep_agent+loop). **F1** `PromptAssemblyPolicy` (`prompt:default`) drives the fixed order `injects→guardrails→skills→hooks→constitution→prompt_body`, `"\n\n"` join — inline `blocks.append` ordering DELETED (grep→0 backend-wide; reworded docstrings off the literal token). **F3** `skill_provider` (`skill:ui/disk/template/repo`, versioned `SkillBlock` — SKILL-01; ui=live source, disk/template/repo inert) + `hook_provider` (`hook:behavioral` non-executable sub-type renders the legacy `## Active Behavioral Hooks` block) — inline `_inject_skills/_inject_hooks` DELETED (grep→0). Providers expose a SYNC core (`extract_ui_skill_blocks`/`render_behavioral_block`) so the sync `_compose_system_prompt` consumes them without an await-in-running-loop bridge. `_inject_constitution` (F4) LEFT INTACT (08-06's deletion; the policy `constitution` slot is its home). `hooks/` package importable + behavioral sub-type intact for 08-07's executable hooks. `_KNOWN`+lockstep count 25→32 (runtime + prompt + 4 skills + behavioral). Composed prompts byte-identical for EVERY agent (5 snapshots unchanged, NO re-baseline); F1/F3/F5 ledger rows ☑. **Out-of-scope deferred:** `test_capability_resolution.py` pre-existing collection error (imports deleted `install()`) → `deferred-items.md`. lint-imports 3 kept/0 broken; banned-pattern/migration-ledger/create_runner/guardrails green.

- [Phase 08]: 08-07 (HOOK-01..04 + OBS-02 / D-09): executable `HookHandler` framework landed — hooks `@register("hook",name)` satisfy the port (name/events/required_permission/async handle) and bind at engine lifecycle/tool-call points (before_write/post_task/before_step/`*`) with outcome continue|warn|block; a blocking hook halts the offending action ADDITIVELY (no new WS event). Permission-gated binding (`hooks.base.bound_hooks`): a hook's required_permission must be granted on the step's effective perms (08-03 intersection) — `secret_scan`→read_files (ON, bound), git/exec hooks NOT bound this phase (those perms OFF; T-08-07-EoP). **secret_scan** (before_write/pre_commit, blocking, read_files) blocks a secret-bearing write + writes hook_runs outcome=block (never logs the raw secret — truncated marker only, T-08-07-ID); clean writes continue. **otel_tracing** (`*`, NON-blocking, required_permission=None always-bound, user_allowed=True) opens a REAL OpenTelemetry span per fired event + writes a hook_runs row; emits NO engine WS event (Pitfall 6 — characterization parity). **OTel decision:** human approved REAL OpenTelemetry at the Task-2 blocking-human package-legitimacy checkpoint — installed `opentelemetry-api`+`opentelemetry-sdk` 1.42.1 ONLY (CNCF, verified on PyPI); a module-level TracerProvider uses `ConsoleSpanExporter` by default and auto-switches to the OTLP exporter ONLY when `OTEL_EXPORTER_OTLP_ENDPOINT` is set (the OTLP exporter package is OPTIONAL/lazy, guarded → degrades to console; NOT a hard dep — least-privilege/supply-chain T-08-07-SC). Every firing persists an owner/workspace-scoped hook_runs row (0016 ScopedStore writer via ctx.runner — no kernel→app import; T-08-07-ID2). The 08-05 behavioral (non-executable) provider survives alongside the executable sub-type. `_KNOWN`+lockstep drift count 32→34 (hook:secret_scan + hook:otel_tracing). banned-pattern unaffected (OTel is an observability lib, not a deep-agent runtime — INV-13 held). Deviation: re-scoped a Task-1 engine-seam test assertion (read_files-off scanner) to assert no secret_scan row rather than a stale total-row count, since otel_tracing now legitimately fires on before_write (Rule 1, test-only). Live-OTLP span export against a real collector deferred to the end-of-milestone live pass. 20 hook tests green; 5 characterization snapshots byte/event-identical (no re-baseline); lint-imports 3 kept/0 broken; migration-ledger green. **Phase 08 = 8/8 plans complete.**

- [Phase 08]: 08-08 (API-02/03/06 + D-11): `GET /api/capabilities` is an auth-gated (`Depends(get_current_user)`, 401 without a token — T-08-08-auth) registry-REFLECTIVE palette — enumerated live from `_KNOWN` post-`discover()`, so a freshly `@register`'d cap appears with ZERO endpoint edit (test_palette_reflects_registry). Each `(kind,name)` carries `user_allowed` (privileged exec/secrets/spawn/runtimes = False, T-08-08-ID) + a forward-compat `config_schema={}` slot (the ports are one-method Protocols with no per-cap schema yet — documented stub, non-blocking). The model_catalog kind is surfaced EXPANDED under a separate `model_catalog` key (per-model records for the picker), not one opaque row. API-03 additive WS events (`validator_result`/`validation_warning`/`gate_*`) flow through the GENERIC `websocket.py` forward with NO websocket.py edit — the 5 characterization snapshots stay byte/event-identical (no re-baseline, T-08-08-parity). Frontend D-11 REUSE (not rebuild): 3 additive sibling panels wired into `WorkflowComposer.tsx` — `CapabilityPalette` (live `/api/capabilities`, grouped by kind + trust badge), `AgentModelPicker` (per-agent model from the catalog → `model_overrides`), `ValidatorIssuePanel` (props-driven like AgentProgressPanel; parent routes the WS events; issues grouped CRITICAL/HIGH/MEDIUM/LOW). Subagent/wave-tree + repo-diff viewers DEFERRED (no backing data until P9/11/12) — confirmed absent. Task 3 (API-06) is a frontend visual render with no headless DOM harness → HUMAN-VERIFIED/APPROVED (human ran the dev servers + confirmed the live render). No new backend/frontend dependency (T-08-08-SC accept). 10 tests pass (capabilities_api 8 + characterization_prototype 2); lint-imports 3 kept/0 broken.

- [Phase 09]: 09-01 (RUNTIME-01): net-new runtime port layer landed. `agents/runtime/base.py` defines four kernel-side stdlib-only `@runtime_checkable` Protocols — `RuntimeEnvironment` (provisioner: `create_workspace(*, owner_id, workspace_id, has_git, exec)` / `teardown`), `Workspace` (facade: read/write/search/clone_repo/create_branch/git_diff/exec_command/teardown + owner_id/workspace_id/runtime back-ref/policy), `ExecutionPolicy` (exec/network/secrets default OFF; `allows`), `IsolationProvider` (`allocate(scope)` — shared_read/per-run downstream, sub_sandbox/worktree Phase 11). `LocalSandboxRuntime` (app-side `app/agents/runtime/local.py`, `@register("runtime_env","local")`, user_allowed=False) returns a `LocalWorkspace` that reuses `RunSandbox.path_for` traversal-safety + `RUNS_ROOT`, and is the SINGLE git-subprocess owner (clone/branch/diff). exec stays OFF: `exec_command` raises `PermissionError` under the default `LocalExecutionPolicy(exec=False)` (T-09-01-02). Registered under the DISTINCT `runtime_env` kind (NOT `runtime:langchain_deepagents` — the agent adapter); `app.agents.runtime` wired into `discover()` `_forward_packages`. The 4th import-linter forbidden contract locks `agents.runtime ↛ [agents.execution_engine, app]` (T-09-01-03) — the ECS-swap seam (D-01: a later `EcsRuntime` plugs in as a backend swap, zero engine edit). `_KNOWN` drift-guard 34→35 (expected membership growth); `git_diff` stages+commits the work-tree edit before diffing `base..work`. lint-imports 4/0; banned-pattern+ledger green (INV-13 untouched); 5 characterization snapshots byte/event-identical (purely additive). Commits e55f89a/6125267/5707298.

- [Phase 09]: 09-02 (RUNTIME-02/03): additive Alembic **0017** (`revision=0017`, `down_revision=0016`) adds the owner/workspace-scoped `repositories` table (free-String `provider`, no `sa.Enum`; `auth_ref` cred pointer) + wires the already-nullable `workspaces.repo_id` to it via a NAMED, `batch_alter_table`-portable FK — reversible (`upgrade head`→`downgrade -1`→`upgrade head`) proven offline against in-memory SQLite (no live Postgres offline); single alembic head `0017`. `kind='repo'` needs NO enum widening (free String since 0014). `Repository` model registered on `Base.metadata` (Pitfall 5). `ScopedStore.create_repository` persists ONE `repositories` row + links the `kind=repo` workspace's `repo_id`; `get_repository`/`assert_repo_owned` are default-deny reads (cross-owner → `None` / `PermissionError`, T-09-02-ID) mirroring `create_workspace`/`assert_owns`. **RunSandbox refolded** IN-PLACE (RUNTIME-02, move-don't-copy): the consumed surface (`__init__`/`ensure`/`root`/`path_for`/`read`/`write`/`cleanup` + `serialize`/`count` helpers) is byte-identical, but `read`/`write`/`cleanup` now DELEGATE to a lazily-built `Workspace(has_git=False, exec=off)` (`LocalWorkspace`, 09-01) — the single disk-IO home; `RunSandbox` keeps only the traversal-proof primitives (`root`/`path_for`) that `LocalWorkspace` itself reuses (wrapping a separate sandbox would be circular). `read` keeps the None-on-missing contract via an `is_file()` guard. NO `if repo:` engine fork (grep `agents/execution_engine/` → 0); one path serves artifact (`has_git=False`) + repo (`has_git=True`, 09-04) workspaces. Migration-ledger `R1` CHECK row (the consumed surface survives byte-identical → a grep gate would false-fire; the parity snapshots + persistence test ARE the gate, L16/F4/F5 precedent) + ledger ratchet `_REQUIRED_ITEMS`/`expected` updated in lockstep. 5-pipeline characterization + `test_sandbox_deliverable` byte/event-identical with `SNAPSHOT_UPDATE` UNSET (no re-baseline); `serialize_sandbox_deliverable` raw-bytes read preserved (0 executable `read_text(`); lint-imports 4/0; banned-pattern + migration-ledger green (INV-13 untouched). Commits 8682402/0e90f3e.
- [Phase ?]: 09-03: repo-context capabilities landed — repo_inventory (kernel stdlib tree/langs/deps/ignore/binary/size-cap, lineage-tracked); repo_index app-side (tree-sitter import-isolated, search=grep default + symbol_query on in-memory per-run build, N6=2000, RepoSpec.index opt-in INV-5); context_pack+selector + repo provider (target+neighbors, cross-owner PermissionError propagates L16). Task-1 pkg checkpoint APPROVED. OFFLINE Open Risk REALIZED: language-pack 1.8.1 lazy-downloads grammars -> FALLBACK to per-language tree-sitter-python/-javascript/-typescript wheels (offline-proven). _KNOWN 35->39; import-linter 4/0; banned-pattern + 5 characterization snapshots byte/event-identical. Commits 4f927a6/e5363e8.
- [Phase 09]: 09-04: repo_diff reads the diff ONLY via ctx.runner.workspace.git_diff (D-10, resolver spawns no child process); diff-only — no commit/PR push (N4), grep-clean of git commit/push + subprocess; base/working branches off ctx (default main/work), never a workflow-name branch (INV-1).
- [Phase 09]: 09-04: sample_brownfield manifest at the REAL manifest home agents/workflows/sample_brownfield/ (not the plan's manifests/ subdir) so compile_for_run loads it with ZERO engine edit; AGENT.md specs + the end-to-end test are test-scoped (sc001 precedent); the §15 RepoSpec injected at run entry, not the manifest (INV-5/D-08). REPO-04/REPO-05 closed; _KNOWN 39→40; exec=off at every step; prototype parity held; commits 98d8f9b/47be9a9.

### Pending Todos

- Phase 09: plans 01-02 complete; next is 09-03 (repo inventory/index/context — tree-sitter behind the repo_index capability).
- Phase 08: all 8 plans complete — run phase 08 verification (still pending).

### Blockers/Concerns

Open decision records to confirm before their phase (from plan §26):

- **N3 (Phase 10/[4B]) ⚠️ highest risk** — local `exec` security threat model; code-exec stays disabled (security gate) until set
- **N2 (Phase 9)** — isolation granularity MVP (ephemeral per-run local)
- **N4 (Phase 9+)** — git hosting scope/order (GitLab vs GitHub; repo is GitLab `hexaware-uki/flowin`)
- **N5/N7 (Phase 9)** — branch/PR policy + repo deliverable shape (diff-only until N4)
- **N6/N10 (Phase 9)** — repo scale → grep-vs-index threshold + RepoIndex approach
- **N8 (Phase 9+)** — long-job orchestration substrate
- **N9 (Phase 5/[1B])** — artifact retention default (run_ttl vs keep)
- **N11 (Phase 6/[1C])** — model default/premium policy + fallback chain

## Deferred Items

- **Plan Phase 7 — ECS/EC2 runtime** behind the unchanged `RuntimeEnvironment` port (separate spec; §27). Tracked as v2 (ECS-01/02).
- CP-SAT scheduling · single-file fragment-merge · PR/commit push · DB-backed user workflows (REQUIREMENTS.md v2 / Out of Scope).

---
*Last updated: 2026-06-10 — 09-01 complete (net-new runtime port layer: RuntimeEnvironment/Workspace/ExecutionPolicy/IsolationProvider kernel-side Protocols + LocalSandboxRuntime app-side @register('runtime_env','local'), the single git-subprocess owner clone/branch/diff; exec_command denied under default policy [RUNTIME-01]; 4th import-linter contract agents.runtime↛[execution_engine,app] — the ECS-swap seam D-01; _KNOWN 34→35; lint 4/0; banned-pattern+ledger green; 5 characterization snapshots byte/event-identical; commits e55f89a/6125267/5707298). Next: 09-02. — previous: 08-07 complete*
<!-- prior footer retained below for history -->
*Last updated: 2026-06-09 — 08-07 complete (executable HookHandler framework continue|warn|block + permission-gated binding; secret_scan blocks before_write secrets → hook_runs outcome=block [HOOK-01..04]; otel_tracing wildcard non-blocking REAL OpenTelemetry spans + hook_runs row [OBS-02] — human approved opentelemetry-api/sdk 1.42.1, console-default/OTLP-via-env, exporter optional/lazy; 20 hook tests green; 5 characterization snapshots byte/event-identical; lint-imports 3/0; banned-pattern unaffected; commits 5354944 + 94b77b3). Phase 08 = 8/8 plans complete; next: phase 08 verification.*
