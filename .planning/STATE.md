---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: executing
last_updated: "2026-06-09T11:48:00.000Z"
last_activity: "2026-06-09 -- 07-07 executed: deleted the dead dual validation fix-loop from task_loop.py (INV-3/INV-12; WR-07/WR-08, cluster B closed). Goldens unchanged."
progress:
  total_phases: 12
  completed_phases: 6
  total_plans: 38
  completed_plans: 34
  percent: 50
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-06)

**Core value:** A brand-new custom workflow can replicate `prototype` by manifest + AGENT.md only — with zero engine edits (SC-001).
**Current focus:** Phase 07 — gap-closure PLANNED (07-07..07-11): closes the 14 deep-review findings — context_message parity drift (oracle-gated) + SC-001 hardcoding (see 07-REVIEW-DEEP.md); Phase 08 deferred until 07 truly closes

## Current Position

Phase: 7
Plan: 07-08..07-11 (gap-closure — 07-07 DONE, 4 plans remaining, waves 2–5)
Status: Executing (gap-closure) — 07-07 complete; next: /gsd-execute-phase 7 (07-08)
Last activity: 2026-06-09 -- 07-07 executed: deleted the dead dual validation fix-loop from task_loop.py (INV-3/INV-12; WR-07/WR-08, cluster B closed). Goldens unchanged.

Progress: [█████░░░░░] 50% (6/12 phases complete)

## Performance Metrics

**Velocity:**

- Total plans completed: 37
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
| 07 | 6 | - | - |

**Recent Trend:**

- Last 5 plans: 01-01 (~6 min, 2 tasks, 12 files), 01-03 (~3 min, 2 tasks, 2 files)
- Trend: —

*Updated after each plan completion*
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

### Pending Todos

None yet.

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
*Last updated: 2026-06-09 — 07-07 complete (cluster B / WR-07+WR-08 closed); gap-closure continues with 07-08..07-11*
