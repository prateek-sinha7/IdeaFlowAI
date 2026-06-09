---
phase: 07-prototype-as-manifest-parity-proof-sc-001-2
verified: 2026-06-09T10:00:00Z
status: gaps_found
score: 7/9 must-haves verified
overrides_applied: 0
gaps:
  - truth: "opendesign provider produces context_message blocks byte-identical to the legacy L12 injection branches (INV-3 / PARITY-03)"
    status: failed
    reason: "Three distinct behavioral regressions vs the legacy L12 engine block. The characterization parity net is structurally blind to all three because the normalizer strips context_message (_VOLATILE_STRIP_KEYS line 109). The passing characterization tests do NOT evidence byte parity on the injected context."
    artifacts:
      - path: "backend/agents/capabilities/context_providers/opendesign.py"
        issue: "CR-01 (line 58): DS block emits bare ds_body only. Legacy (engine.py @ git fb55699 line ~3333-3337) prepended the instruction preamble 'Apply these tokens to ALL colors, fonts, and spacing. Map to :root variables: --bg,--fg,--accent,--surface,--border,--muted.' The provider drops this entirely."
      - path: "backend/agents/capabilities/context_providers/opendesign.py"
        issue: "CR-02 (lines 67-74): example.html injected unconditionally when template_body present. Legacy gated it on _is_builder = bool(set(spec.tools) & {'prototype_emit_only','prototype'}) — prototype-specify and prototype-plan (tools:[]) must NOT receive the full example.html. The provider has no access to spec.tools and applies no gate."
      - path: "backend/agents/capabilities/context_providers/opendesign.py"
        issue: "CR-03 (lines 50-79): no build-task-2+ suppression. Legacy L12 computed is_build_task_2_plus and skipped the DS body, template body, and example for build tasks 2+. The generic injector (engine.py:2926-2942) calls provider.load() unconditionally for every agent whose injects is set — full DS/template/example re-injected on every build task, defeating the O(n) prompt-growth control the html_skeleton compaction was designed to enforce."
      - path: "backend/tests/agents/test_context_providers.py"
        issue: "line 114 asserts the bare ds_body ('DS TOKENS') locking in the CR-01 regression. No test asserts the preamble. No test asserts the tools-gated example gate (CR-02). No test asserts the task-2+ suppression (CR-03)."
    missing:
      - "Restore DS preamble in opendesign.py line 58: blocks[f'ACTIVE DESIGN SYSTEM: {ds_id}'] = ('Apply these tokens to ALL colors, fonts, and spacing. Map to :root variables: --bg,--fg,--accent,--surface,--border,--muted.\\n' + ds_body)"
      - "Restore builder gate in opendesign.py: require spec.tools access via ctx (e.g. ctx.current_spec or a tools handle method); gate example block on bool(spec_tools & {'prototype_emit_only','prototype'})"
      - "Restore build-task-2+ suppression: either pass ectx.build_task_number into the provider load call, or have _compose_context_message suppress provider blocks for build agents on task 2+ (when ectx.build_task_number not in ('', '1'))"
      - "Add assertions to test_context_providers.py pinning the preamble (CR-01), the tools gate (CR-02), and the task-2+ suppression (CR-03) so the parity net is no longer blind to these three paths"

  - truth: "all 5 pipelines (prototype/od_prototype/prototype_revision/ppt/code-gen) are at deliverable byte parity AND context_message byte parity vs the post-0C baseline (INV-3 full)"
    status: failed
    reason: "Deliverable byte parity and semantic event multiset parity are verified green (characterization tests pass). Context_message parity is NOT verified — the normalizer explicitly strips context_message from the event snapshot (_VOLATILE_STRIP_KEYS). The three CR-01/02/03 regressions in the OD injection path are therefore uncaught unsanctioned deviations from INV-3. The PARITY-09 requirement reads 'deliverable parity + semantic event parity vs the post-0C baseline' and is technically met at the deliverable/event-multiset layer, but INV-3 states 'existing prototype/od_*/PPT/code-gen behavior stays deterministic-byte-identical + semantic-event-parity'. The context_message content IS observable behavior that reaches the model and affects output determinism."
    artifacts:
      - path: "backend/tests/agents/characterization/_normalize.py"
        issue: "line 109: context_message in _VOLATILE_STRIP_KEYS — the normalizer structurally cannot catch context injection regressions. The characterization net passes for the wrong reason on OD pipelines."
    missing:
      - "After fixing CR-01/02/03, add a dedicated context_message parity assertion (separate from the event normalizer) that directly compares the composed context_message for a scripted prototype/od_prototype run against a reference snapshot, or assert the exact block structure/ordering at the test_context_providers level"
---

# Phase 7: Prototype-as-Manifest Parity Proof (SC-001) Verification Report

**Phase Goal:** Re-express prototype/od_/revision entirely as manifests backed by registered
capabilities, then delete the hardcoded kernel leaks L1–L12 — proving the kernel knows no
workflow by name. This is the core-value proof (SC-001).

**Verified:** 2026-06-09T10:00:00Z
**Status:** gaps_found
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Kernel has ZERO workflow-name/pipeline_type/spec.id branches on the routed path (SC-001 structural) | VERIFIED | `grep -rnE 'if pipeline_type\|spec\.id ==' agents/execution_engine/ --include=*.py` returns 0. Banned-pattern gate (test_banned_patterns.py) enforces kernel-scoped HARD-FAIL. L1–L13 deleted; agents/prototype/ package removed. |
| 2 | Engine routes per-step via registry.resolve("strategy") and per-deliverable via registry.resolve("deliverable") with NO spec.id/pipeline_type branch | VERIFIED | engine.py lines 2926-2942 and per-step dispatch confirmed. test_routing_parity.py passes (5 routing assertions). grep for resolve("strategy" and resolve("deliverable" both confirm >= 1 match. |
| 3 | single_shot + task_loop strategies exist behind ExecutionStrategy port; unit tests drive both from a compiled Step | VERIFIED | backend/agents/capabilities/strategies/{single_shot,task_loop}.py exist, are substantive, imported via registry. test_strategies.py passes. |
| 4 | Deliverable resolvers (single_file/serialized_sandbox/streamed_text/ppt) exist and resolve by deliverable.name — no pipeline_type branch | VERIFIED | All four resolvers exist and pass test_deliverable_resolvers.py. grep for pipeline_type in deliverables/*.py = 0. ppt resolver owns both carousel-sanitize behaviors (PARITY-07). |
| 5 | opendesign provider produces context_message blocks byte-identical to legacy L12 injection branches (INV-3 / PARITY-03) | FAILED | CR-01: DS preamble dropped (opendesign.py:58 emits bare ds_body; legacy prepended instruction line). CR-02: example.html leaked to tools:[] planning agents (no builder gate). CR-03: full DS/template/example re-injected on every build task (no is_build_task_2_plus suppression). test_context_providers.py:114 asserts the bare body, locking in CR-01. The characterization parity net is blind to all three: context_message is in _VOLATILE_STRIP_KEYS (normalizer line 109). |
| 6 | All 5 pipelines at deliverable byte parity + semantic event multiset parity vs post-0C baseline | FAILED (partial) | Deliverable byte parity: VERIFIED (all 5 characterization tests pass). Semantic event multiset parity: VERIFIED (context_message stripped from normalizer, events match). Context injection parity (INV-3 full scope): FAILED — the three CR-01/02/03 regressions are unsanctioned deviations from byte-identical context_message content on prototype/od_prototype/prototype_revision pipelines. |
| 7 | L1–L13 deleted from agents/execution_engine/; every per-leak kernel grep returns 0 | VERIFIED | test_migration_ledger.py passes (26 passed, 1 skipped). All 13 per-leak kernel greps confirmed 0. agents/prototype/ package absent from disk. |
| 8 | Migration-ledger rows L1–L13 flipped to checked (kernel-scoped patterns); banned-pattern gate hard-fails on reintroduction | VERIFIED | test_migration_ledger.py green. test_banned_patterns.py green (9 passed). Non-vacuity guard confirmed. |
| 9 | L14/L15/L16 re-confirmed closed; L16 cross-owner PermissionError propagates and is never swallowed | VERIFIED | test_parent_run_ownership.py: 13 passed. grep for L14 (self._current_task_block etc.) and L15 (accumulated_outputs) patterns = 0 across backend/. |

**Score:** 7/9 truths verified

---

## Gaps in Detail

### Gap 1: OpenDesign context-injection parity — three regressions (BLOCKER, PARITY-02/PARITY-03, INV-3)

The `opendesign` provider (`backend/agents/capabilities/context_providers/opendesign.py`) is
NOT a faithful lift of the legacy L12 `_build_context_message` injection branches. Three
independent behavioral regressions exist:

**CR-01 — DS instruction preamble dropped (opendesign.py:58)**

Legacy engine (git fb55699, line ~3333-3337):
```
f"=== ACTIVE DESIGN SYSTEM: {ds_id} ===\n"
f"Apply these tokens to ALL colors, fonts, and spacing. "
f"Map to :root variables: --bg, --fg, --accent, --surface, --border, --muted.\n"
f"{od['ds_body']}\n"
f"=== END ACTIVE DESIGN SYSTEM ==="
```

Current opendesign.py:58:
```python
blocks[f"ACTIVE DESIGN SYSTEM: {ds_id}"] = ds_body
```

The entire "Apply these tokens..." instruction line is gone. `test_context_providers.py:114`
asserts `== "DS TOKENS"` (bare body), locking in this regression.

**CR-02 — example.html leaks into tools:[] planning agents (opendesign.py:67-74)**

Legacy (engine.py @ git fb55699, line ~3357-3359):
```python
_is_builder = bool(set(getattr(spec, "tools", []) or []) & {"prototype_emit_only", "prototype"})
example_html = self._load_template_example(template_id) if _is_builder else None
```

The legacy code explicitly comments: "Planning agents (prototype-specify / prototype-plan,
tools=[]) must NOT see a full working HTML doc." The provider has no access to `spec.tools`
and gates example only on `if template_body:`. The prototype-specify and prototype-plan agents
(tools: [], injects: [template, design_system]) now receive the full example.html. This
regression is masked offline (when web-prototype/example.html is absent from the test env)
and manifests in production where the example file exists.

**CR-03 — build-task-2+ injection skip lost (opendesign.py:50-79 + engine.py:2923-2942)**

Legacy (engine.py @ git fb55699, line ~3321-3344):
```python
is_build_task_2_plus = (spec.id == "prototype-build" and task_num_str not in ("", "1"))
if "design_system" in injects and od.get("ds_body") and not is_build_task_2_plus:
    ...inject DS...
if "template" in injects and od.get("template_body"):
    if not is_build_task_2_plus:
        ...inject template...
```

The generic injector (engine.py:2926-2942) calls `provider.load(ectx)` unconditionally
whenever `injects` is set — no task-number awareness, no suppression for task 2+. Full
DS/template/example are re-injected on every build task on top of the html_skeleton compaction,
defeating the O(n) prompt-growth control that compaction was designed to enforce.

**Why tests pass despite these regressions**

`tests/agents/characterization/_normalize.py` line 109: `"context_message"` is in
`_VOLATILE_STRIP_KEYS`. The deliverable byte-snapshot uses a scripted model that ignores
injected context. Neither the event-multiset gate nor the deliverable snapshot can observe
context_message content changes. The characterization tests pass for the wrong reason on
OD-injected pipelines.

**Remediation (specific, ordered):**

1. `opendesign.py:58` — restore preamble:
   ```python
   blocks[f"ACTIVE DESIGN SYSTEM: {ds_id}"] = (
       "Apply these tokens to ALL colors, fonts, and spacing. "
       "Map to :root variables: --bg, --fg, --accent, --surface, --border, --muted.\n"
       + ds_body
   )
   ```

2. `opendesign.py:67-74` — restore builder gate. Thread the consuming agent's tool set to
   the provider via `ctx` (e.g. add `ctx.current_spec_tools: set[str]` set on `ectx` before
   `_compose_context_message` calls) and gate:
   ```python
   is_builder = bool(getattr(ctx, "current_spec_tools", set()) & {"prototype_emit_only", "prototype"})
   example_html = runner.template_example(template_id) if is_builder else None
   ```

3. `engine.py _compose_context_message` or `opendesign.py` — restore task-2+ suppression.
   Either pass `ectx.build_task_number` into `provider.load()` (extend the port to accept a
   `task_context` dict), or have `_compose_context_message` suppress provider blocks for
   build agents on task 2+ (mirroring `is_build_task_2_plus = task_num_str not in ("", "1")`).

4. `test_context_providers.py` — add assertions that close the blind spots:
   - Assert the preamble is present in the DS block content (not just the key name).
   - Assert `TEMPLATE EXAMPLE` key is absent when invoked with a tools:[] spec.
   - Assert `ACTIVE DESIGN SYSTEM` key is absent when `build_task_number` is "2".

---

## Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/agents/capabilities/strategies/single_shot.py` | SingleShotStrategy (name='single_shot') | VERIFIED | class SingleShotStrategy present; name="single_shot"; satisfies ExecutionStrategy port |
| `backend/agents/capabilities/strategies/task_loop.py` | TaskLoopStrategy (name='task_loop') | VERIFIED | class TaskLoopStrategy present; per-task loop + compaction + validation |
| `backend/agents/capabilities/task_parsers/heading_tasks.py` | HeadingTasksParser (name='heading_tasks') | VERIFIED | class HeadingTasksParser; verbatim lift of _count_plan_tasks/_extract_task_block |
| `backend/agents/capabilities/registry.py` | resolve(kind,name) + install() | VERIFIED | def resolve present; install() binds all known (kind,name) pairs |
| `backend/agents/execution_engine/context.py` | object-typed runner handle field | VERIFIED | runner: object | None = None field present |
| `backend/agents/capabilities/deliverables/single_file.py` | SingleFileResolver (name='single_file') | VERIFIED | class SingleFileResolver; resolves by deliverable.name; no pipeline_type branch |
| `backend/agents/capabilities/deliverables/serialized_sandbox.py` | SerializedSandboxResolver | VERIFIED | class SerializedSandboxResolver; count > 0 guard; filename:-block format preserved |
| `backend/agents/capabilities/deliverables/streamed_text.py` | StreamedTextResolver | VERIFIED | class StreamedTextResolver; _unwrap_artifact(last_streamed) |
| `backend/agents/capabilities/deliverables/ppt.py` | PptResolver (owns both carousel-sanitize behaviors) | VERIFIED | class PptResolver; _sanitize_carousel_deck_html + _unwrap_artifact; owns both final-output and mid-stream behaviors |
| `backend/agents/capabilities/context_providers/opendesign.py` | OpenDesignProvider — byte-identical L12 blocks | FAILED | class OpenDesignProvider exists and is substantive, but emits preamble-dropped DS block (CR-01), no builder gate on example (CR-02), no task-2+ suppression (CR-03) |
| `backend/agents/capabilities/context_providers/previous_run.py` | PreviousRunProvider with assert_owns-before-seed | VERIFIED | class PreviousRunProvider; assert_owns called before seeding; cross-owner PermissionError propagates; test_parent_run_ownership.py green |
| `backend/agents/capabilities/compaction/html_skeleton.py` | HtmlSkeletonCompaction — verbatim lift, >= 50% reduction | VERIFIED | class HtmlSkeletonCompaction; compact() is verbatim lift of _extract_html_skeleton; test_phase3_compaction.py green |
| `backend/agents/execution_engine/kernel_services.py` | KernelServices handle attached as ctx.runner | VERIFIED | KernelServices class present; wraps _run_agent + sandbox + static_check + render_check + serialize/count + run_validation_fix_loop + OD reads; execute() attaches to ctx.runner |
| `backend/agents/execution_engine/engine.py` | capability-routed dispatch; L1-L13 absent | VERIFIED | resolve("strategy") and resolve("deliverable") dispatch confirmed; all L1-L13 kernel greps return 0; _build_context_message deleted; positional spec.id rewritten to index==0 |
| `backend/tests/agents/test_routing_parity.py` | 5-pipeline routing assertions | VERIFIED | 5 tests, all passing; asserts build->task_loop, others->single_shot, deliverable->single_file, no spec.id build branch reached |
| `specs/003-workflow-engine-decoupling/migration-ledger.md` | L1-L13 rows flipped to checked with kernel-scoped patterns | VERIFIED | test_migration_ledger.py passes; L14/L15/L16 re-confirmed |
| `backend/tests/agents/test_banned_patterns.py` | kernel-scoped INV-1 HARD-FAIL gate | VERIFIED | INV-1 check is assert count == 0 scoped to agents/execution_engine/; non-vacuity guard present; test passes |

---

## Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `engine.py` | `registry.resolve("strategy", step.strategy).run(step, ctx)` | per-step dispatch | VERIFIED | grep confirms resolve("strategy" >= 1 match; no spec.id/pipeline_type branch |
| `engine.py` | `registry.resolve("deliverable", compiled.deliverable.strategy).resolve(ctx)` | deliverable resolution | VERIFIED | grep confirms resolve("deliverable" >= 1 match |
| `engine.py` | `ctx.runner = KernelServices(...)` | execute() attaches runner handle | VERIFIED | ectx.runner = KernelServices(...) confirmed in engine.py |
| `opendesign.py` | legacy L12 injection bytes | block-name + content byte-identical | FAILED | CR-01/02/03 confirmed against git fb55699 |
| `previous_run.py` | `ScopedStore.assert_owns` | ownership check BEFORE seeding | VERIFIED | grep for assert_owns in previous_run.py >= 1; test_parent_run_ownership.py green |
| `test_migration_ledger.py` | kernel-scoped L1-L13 grep patterns | ratchet asserts 0 in agents/execution_engine/ | VERIFIED | all 26 checks pass |
| `test_banned_patterns.py` | agents/execution_engine/ | assert count==0 for if pipeline_type / spec.id == | VERIFIED | hard-fail gate green |

---

## Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|--------------|--------|-------------------|--------|
| `opendesign.py` | blocks dict | `ctx.od_context` dict (boundary-built) + `ctx.runner.template_example` / `template_injection_parts` | Structurally yes — data flows from the boundary od_context dict | HOLLOW (behavioral divergence from legacy): data flows but content differs from the legacy byte contract on three independent dimensions (CR-01/02/03) |
| `engine.py _compose_context_message` | context_message parts | provider.load(ectx) blocks + agnostic scaffolding | Structurally yes — providers are invoked | HOLLOW (no task-2+ suppression): full provider invocation on every build task regardless of task number |
| `single_file.py` | deliverable content | `ctx.runner.sandbox.read(deliverable.name)` | Yes — reads prototype.html from sandbox via handle | VERIFIED |
| `ppt.py` | deliverable content | `_sanitize_carousel_deck_html(last_streamed)` | Yes — carousel-sanitize + unwrap applied to streamed text | VERIFIED |
| `previous_run.py` | seeded files | `ctx.runner.read_parent_file()` after `scoped_store.assert_owns` | Yes — ownership-checked parent run files | VERIFIED |

---

## Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| All 5 pipeline characterization tests pass (deliverable byte + event multiset) | `python3.11 -m pytest tests/agents/test_characterization_*.py -q --tb=no` | 10 passed | PASS |
| Migration ledger L1-L13 ratchet green | `python3.11 -m pytest tests/agents/test_migration_ledger.py -q` | 26 passed, 1 skipped | PASS |
| Banned-pattern INV-1 hard-fail gate green | `python3.11 -m pytest tests/agents/test_banned_patterns.py -q` | 9 passed | PASS |
| Routing parity test (build->task_loop, others->single_shot) | `python3.11 -m pytest tests/agents/test_routing_parity.py -q` | 5 passed | PASS |
| Cross-owner PermissionError propagation (L16 ratchet) | `python3.11 -m pytest tests/agents/test_parent_run_ownership.py -q` | 13 passed | PASS |
| Full agents suite (548 passed, 0 new failures vs baseline) | `python3.11 -m pytest tests/agents/ -m "not requires_api_key" -q --tb=no` | 548 passed, 19 skipped | PASS |
| Full unit suite (486 passed, 8 known pre-existing failures only) | `python3.11 -m pytest tests/unit/ -m "not requires_api_key" -q --tb=no` | 486 passed, 8 KNOWN pre-existing failures | PASS |
| context_message bytes for prototype/od_prototype match legacy (CR-01/02/03) | Assert DS preamble present; assert example absent for tools:[] agents; assert DS/template absent on task 2 | Not tested — _VOLATILE_STRIP_KEYS blinds the test net | FAIL |

---

## Probe Execution

Step 7c: SKIPPED — no `scripts/*/tests/probe-*.sh` files declared in PLAN or found by
convention search. Runtime environment is offline-only (no live Bedrock for this phase).

---

## Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| PARITY-01 | 07-01 | single_shot + task_loop execution strategies | SATISFIED | Both strategies exist, pass unit tests, drive from compiled Step |
| PARITY-02 | 07-02 | single_file/serialized_sandbox/streamed_text deliverable resolvers | SATISFIED | All four resolvers exist; no pipeline_type branch; test_deliverable_resolvers green |
| PARITY-03 | 07-02 | opendesign context provider + declared seed_files + heading_tasks task parser | PARTIALLY SATISFIED | heading_tasks parser: satisfied. previous_run provider: satisfied. opendesign provider: NOT satisfied — three parity regressions (CR-01/02/03) vs legacy L12 injection. |
| PARITY-04 | 07-03 | html_skeleton CompactionStrategy, behavior-preserving vs 0C | SATISFIED | HtmlSkeletonCompaction is verbatim lift; test_phase3_compaction green with >=50% reduction assertion |
| PARITY-05 | 07-04 | prototype/od_prototype/prototype_revision run purely from compiled manifests | SATISFIED (structural) | Per-step dispatch and deliverable resolution route purely from manifests; no spec.id/pipeline_type branch. Context injection has the CR-01/02/03 parity gap. |
| PARITY-06 | 07-05 | Delete kernel leaks L1-L13; drop pipeline.py/prototype package | SATISFIED | All per-leak kernel greps return 0; agents/prototype/ absent; test_migration_ledger green |
| PARITY-07 | 07-02 | PPT deliverable: ppt resolver + carousel-sanitize both behaviors | SATISFIED | PptResolver owns both sanitize behaviors; mid-stream + final-output sites removed from kernel |
| PARITY-08 | 07-05 | Kernel zero workflow-name/agent-id branches; banned-pattern hard-fail | SATISFIED | grep agents/execution_engine/ for if pipeline_type/spec.id == = 0; banned-pattern gate hard-fails on reintroduction |
| PARITY-09 | 07-04 | All 5 pipelines at deliverable byte + semantic event parity vs post-0C baseline | PARTIALLY SATISFIED | Deliverable bytes and event multiset: verified green (all 5 characterization tests pass). Context_message byte parity (part of INV-3): NOT verified — the normalizer strips context_message; CR-01/02/03 are uncaught deviations. |

---

## Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `backend/agents/capabilities/context_providers/opendesign.py` | 58 | DS block content missing instruction preamble (bare ds_body instead of preamble + ds_body) | BLOCKER | Behavioral regression vs legacy L12 for all prototype/od_prototype runs; locked in by test assertion |
| `backend/agents/capabilities/context_providers/opendesign.py` | 67-74 | No builder-gate on example.html injection (missing spec.tools check) | BLOCKER | Behavioral regression: example.html leaks to planning agents (tools:[]) in production |
| `backend/agents/execution_engine/engine.py` | 2926-2942 | _compose_context_message invokes providers unconditionally (no task-2+ suppression) | BLOCKER | Full DS/template/example re-injected on every build task; defeats html_skeleton compaction intent |
| `backend/tests/agents/test_context_providers.py` | 114 | Asserts bare ds_body value, locking in CR-01 regression | BLOCKER | Parity net blind spot: this test certifies the wrong behavior |
| `backend/tests/agents/characterization/_normalize.py` | 109 | context_message in _VOLATILE_STRIP_KEYS — test net structurally blind to context injection regressions | WARNING | All three CR-01/02/03 gaps pass characterization; the parity proof does not cover context content |

---

## Human Verification Required

None — this verification is fully automatable via code inspection and test execution. The gaps
identified are code-level behavioral regressions, not UX/visual/external-service items.

---

## Gaps Summary

The phase achieves its structural goal (SC-001 core-value proof) cleanly: the kernel knows no
workflow by name on the routed path, all L1-L13 leaks are deleted, the migration-ledger ratchet
and banned-pattern gate are locked. These are confirmed GOOD and should not be re-litigated.

The blocking gap is in the `opendesign` context provider, which is NOT a faithful lift of the
legacy L12 injection branches. Three independent behavioral regressions (dropped DS preamble,
unguarded example injection, missing task-2+ suppression) mean the `opendesign` provider
produces a context_message that diverges from the legacy byte contract for every
prototype/od_prototype build run. These are unsanctioned deviations from INV-3.

The gap is structurally hidden from the parity test suite because `context_message` is stripped
from the characterization normalizer. The passing characterization tests do NOT evidence
context injection parity — they evidence deliverable byte parity and event-field parity only.

A targeted gap-closure plan should:
1. Fix CR-01/02/03 in opendesign.py (the provider interface needs spec.tools access and
   task-number awareness — both require a small ctx extension or a port-level change).
2. Add assertions to test_context_providers.py that pin the exact content divergences, so
   the parity net is no longer blind to future context injection changes.
3. Optionally remove context_message from _VOLATILE_STRIP_KEYS once the parity is verified,
   or add a separate non-volatile context_message snapshot for OD pipelines.

---

_Verified: 2026-06-09T10:00:00Z_
_Verifier: Claude (gsd-verifier)_
