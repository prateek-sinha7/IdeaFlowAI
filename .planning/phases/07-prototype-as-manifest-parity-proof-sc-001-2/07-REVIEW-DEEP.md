---
status: issues_found
phase: "07"
review_type: deep-multiagent
review_method: 9 finder angles → 1-vote verify (grouped) → sweep
files_reviewed: 14
reviewed_at: 2026-06-09
baseline: acd1636
baseline_note: last phase-6 commit; phase-7 range acd1636..HEAD
supersedes_note: >-
  Companion to 07-REVIEW.md (the 07-06 gap-closure review). That review is PRESERVED;
  this is a deeper independent pass at max effort. Where they conflict, see systemic[0].
findings:
  blocker: 0
  critical: 7
  warning: 8
  info: 0
  total: 15
systemic:
  - "CONFLICT WITH 07-06 ADJUDICATION: 07-REVIEW.md concluded 'net blocking findings: 0' and treated the de-blinded context_message as a MITIGATION ('WR-01 is mitigated — the de-blinded goldens now pin the full assembled context_message'). CR-01/CR-02/CR-04/WR-01/WR-03 below refine that: the acd1636 golden recorded NO context_message (blinded); de-blinding (commit fdd8aef) captured the POST-refactor bytes for the FIRST time, so the goldens pin the DRIFTED prompt as the contract. 'pinned == correct' does not hold. These five fixes REVERSE an adjudicated decision — confirm intent (and capture the true acd1636 bytes via an oracle) before applying."
  - "SC-001 ('a new workflow replicates prototype by manifest + AGENT.md, zero engine edits') is contradicted by CR-05/CR-06/CR-07: prototype names are hardcoded in the 'generic' capabilities. The proven property is the narrower 'kernel name-free dispatch' (test_routing_parity), not the prose criterion."
clusters:
  B_golden_safe: [CR-03, WR-07, WR-08]
  C_parity_needs_oracle: [CR-01, CR-02, CR-04, WR-01, WR-02, WR-03, WR-05]
  D_revision_gating: [WR-04, WR-06]
  E_sc001_architecture: [CR-05, CR-06, CR-07]
---

# Phase 07 — Deep Code Review (15 findings)

Baseline `acd1636`. OLD = `git show acd1636:<path>`. Severity: **CR** = changes live prototype/od_*/ppt behavior vs the pre-phase-7 engine OR falsifies the phase's success criterion; **WR** = byte-divergence with lower functional impact, latent correctness, or a project-invariant violation.

> Execution order: **B** (golden-safe, no adjudication conflict) → **C** (parity, needs the oracle + confirmed intent — reverses the 07-06 adjudication) → **D** (revision gating) → **E** (SC-001 refactors, verified with a non-prototype task_loop workflow).

---

## CR-01 — `TEMPLATE COMPLIANCE` block dropped from every build prompt  · cluster C
**File:** `backend/agents/execution_engine/engine.py:2974` (new build branch) · OLD `engine.py@acd1636:3452-3461`
**Mechanism:** OLD `_build_context_message` unconditionally appended, on every `prototype-build` sub-agent task:
```
=== TEMPLATE COMPLIANCE ===
Template: {template_id} — use ONLY its CSS classes from the TEMPLATE SEED
Design System: {ds_id} — use ONLY :root variables, never raw hex colors
=== END TEMPLATE COMPLIANCE ===
```
Reproduced nowhere in new source; absent from both regenerated goldens.
**Trigger:** every `prototype`/`od_prototype` build task loses the design-discipline directive → LLM-output drift.
**Fix:** re-emit byte-exact on build tasks (in `OpenDesignProvider.load` keyed on the build-task signal, or in `_compose_context_message`'s build branch).

## CR-02 — Design-System block injected without the per-`injects` gate  · cluster C
**File:** `backend/agents/capabilities/context_providers/opendesign.py:70` · OLD `engine.py@acd1636` `_build_context_message`
**Mechanism:** OLD gated each block (`if "design_system" in injects:` / `if "template" in injects:`); provider now emits on `ds_body` truthiness alone and the engine appends the whole block map for any non-empty `injects`.
**Trigger:** `od-ppt-brief-analyst`, `prototype-specify`, `prototype-plan` (`injects:[template]`, no `design_system`) now receive an `ACTIVE DESIGN SYSTEM` block. Confirmed in `golden/od_ppt.events.json` + `od_prototype.events.json`.
**Fix:** restore the per-block `injects` gate inside `OpenDesignProvider.load` (pass the spec `injects`).
**NOTE:** intersects the 07-06 adjudication (which reasoned carefully about what planning agents receive from opendesign — the example.html gate). Verify the fix does NOT re-leak example.html (re-opening 07-06 CR-02).

## CR-03 — `single_file` revision fallback loses the user's prototype  · cluster B (golden-safe)
**File:** `backend/agents/capabilities/deliverables/single_file.py:52-59` · OLD `engine.py@acd1636:489-504`
**Mechanism:** OLD (file missing) preferred `revision_original_html` if the stream wasn't HTML, then `_unwrap_artifact`. NEW returns any non-empty `last_streamed` first (no looks_like_html, no unwrap), un-stripped, and only uses the original when the stream is empty.
**Trigger:** prototype_revision where the agent doesn't write `prototype.html` and streams chatter → user gets chatter instead of their preserved prototype. Reachable; untested (golden fixture always writes the file).
**Fix:** key the revision fallback on `revision_original_html` presence (workflow-name-agnostic): when present, restore the OLD `looks_like_html` + `unwrap_artifact(streamed if html else original or streamed)` + stripped-return; when absent (forward build), keep raw `last_streamed`. Add a degraded-path test.

## CR-04 — Template injection parts double-wrapped  · cluster C
**File:** `opendesign.py:124` + `engine.py:2951` · OLD `agents/prototype/context.py@acd1636:109-123` + raw `parts.append(part)`
**Mechanism:** parts arrive already wrapped (`=== TEMPLATE SEED … ===`); provider stores each as a block value, then `_compose_context_message:2951` re-wraps as `=== TEMPLATE INJECTION PART N: <id> === … ===`.
**Trigger:** every `od_prototype` build prompt gains a nested outer envelope per part (golden-confirmed).
**Fix:** emit pre-wrapped injection-part strings raw (mark these blocks pre-wrapped so the injector skips the `=== {name} ===` wrap).

## CR-05 — `task_loop` + kernel seam hardcode `prototype.html` (SC-001)  · cluster E
**File:** `task_loop.py:185,188,243,316-317` + `kernel_services.py:265,273` + `engine.py:1988`
**Mechanism:** 13× literal `"prototype.html"` + step ids `"prototype-plan"`/`"prototype-specify"`; `ctx.deliverable.name` never read (contrast `single_file.py:43`). `Step` carries no filename field, strategy never receives `compiled.deliverable`, kernel-seam bodies hardcode the filename.
**Trigger:** a `task_loop` workflow producing `app.py` → empty dual-write, skipped validation, fix prompt naming `prototype.html` → SC-001 fails for every task_loop workflow except prototype.
**Fix:** thread `ctx.deliverable.name` to the strategy + `persist_task_html`/`run_validation_fix_loop`/`engine._run_validation_fix_loop` (no prototype default); add a declared `TaskSource.source_step` for the plan/spec source steps. Prove with a non-prototype task_loop fixture.

## CR-06 — Kernel-resident prototype-revision block (SC-001)  · cluster E
**File:** `engine.py:646-746, 1138-1189` (const `REVISION_FILE_NAME` at `:164`)
**Mechanism:** HTML extraction + `prototype.html` seeding + baselines + post-revision fix-loop hardwired to `agent_id="prototype-revision-agent"` live inside kernel `execute()`, not a capability. Comment self-describes it as "a DELIBERATE EXCEPTION."
**Fix:** move seed-existing-artifact → `previous_run` provider (parameterized by `deliverable.name`); move pre-edit baseline + post-edit fix-loop → a declared post-step capability.

## CR-07 — `previous_run` ignores the declared `seed_files` (SC-001 / INV-5)  · cluster E
**File:** `previous_run.py:30,75` · plumbing `manifest.py:62` → `compiler.py:128` → `plan.py:242`
**Mechanism:** `_SEED_FILES = ("spec.md","design.md","tasks.md")` constant; `load()` ignores the plumbed `compiled.seed_files`, and `engine._seed_workflow_context` passes only `ectx` (not `compiled`) to `provider.load()`. The `task_loop._write_reference_files` (`task_loop.py:316-317`) has the identical hardcoded twin.
**Fix:** pass `compiled`/`compiled.seed_files` into `provider.load()`; read the declared list with `_SEED_FILES` as fallback. Mirror for the task_loop writer.

---

## WR-01 — Build skeleton wrapper text/position changed + lost `read_file` instruction  · cluster C
**File:** `task_loop.py:243-249` · OLD `engine.py@acd1636:3433-3450`
**Mechanism:** OLD standalone block AFTER consumed-outputs: `=== CURRENT PROTOTYPE (skeleton — call read_file('prototype.html') for full content before editing) ===` … `=== END CURRENT PROTOTYPE ===`. NEW nests inside `=== CURRENT TASK ===` as `=== CURRENT PROTOTYPE SKELETON ===`, no close marker, no `read_file` directive. (Sweep: OLD also suppressed the skeleton on an `[Error:` sentinel; NEW reads disk.)
**Fix:** restore wrapper text/position/instruction byte-exact.

## WR-02 — `ppt` resolver swaps `unwrap`/`sanitize` order (PLAUSIBLE)  · cluster C
**File:** `ppt.py:41` · OLD `engine.py@acd1636:528` then `:1393`
**Mechanism:** NEW `unwrap_artifact(sanitize_carousel_deck_html(x))`; OLD `sanitize(unwrap(x))`. For an `<artifact>`-wrapped deck the orders may differ.
**Fix:** confirm with an `<artifact>`-wrapped carousel input; if different, restore `sanitize(unwrap(x))`. Also dedup the mid-stream sanitize (`engine.py:1772`) vs the resolver.

## WR-03 — END markers gained an id suffix  · cluster C
**File:** `engine.py:2960` · OLD `engine.py@acd1636:3337,3348,3364`
**Mechanism:** symmetric `=== END {block_name} ===` emits `=== END ACTIVE DESIGN SYSTEM: default ===` where OLD emitted bare `=== END ACTIVE DESIGN SYSTEM ===`.
**Fix:** emit bare END markers (strip the id suffix on the END line).

## WR-04 — `_is_revision_workflow` gate too broad  · cluster D
**File:** `engine.py:646` (used `:1139, :1755`)
**Mechanism:** `"previous_run" in compiled.context_providers` replaces OLD `pipeline_type == "prototype_revision"`. Five workflows declare `previous_run` → four non-prototype revisions now classed as prototype revisions; masked only by the secondary `prototype.html.is_file()` guard. Altitude: kernel branches on workflow identity via a provider-name proxy.
**Fix:** drive the revision behaviors off a declared per-step/per-deliverable flag, not provider presence.

## WR-05 — Typed `prototype-build` ref stale after a fix  · cluster C
**File:** `task_loop.py:278-279` · OLD `engine.py@acd1636:2243-2255`
**Mechanism:** `persist_task_html` runs before the fix-loop and never re-persists; OLD re-wrote the typed artifact when `fixed_html != task_html`. Consumer `prototype-validate` (typed read) sees pre-fix HTML on fix runs. Golden has no fix iteration.
**Fix:** re-persist the typed artifact after the fix-loop when on-disk HTML changed. Add a fix-iteration characterization case.

## WR-06 — `previous_run` seed + `assert_owns` unconditional on `parent_run_id`  · cluster D
**File:** `engine.py:1071` + `previous_run.py:44-55` · OLD `engine.py@acd1636:841/843/873/887`
**Mechanism:** OLD nested the seed + `assert_owns` inside `prototype_revision → existing_html → parent_run_id`; NEW gates only on `parent_run_id`. Latent (unreachable via today's frontend; one client-payload change away).
**Fix:** re-couple to the revision-intent signal, or make it an explicit declared behavior.

## WR-07 — Dual implementation of the validation fix-loop (INV-3/INV-12)  · cluster B
**File:** `task_loop.py:368-523` (+ the `else` at :295-302 and the helpers :92-153)
**Mechanism:** `_run_validation_fix_loop` + `_SkippedRender` + `_select_issues_to_fix`/`_static_issue_sigs`/`_console_sigs` duplicate the live engine versions, reachable only via `else: # pragma: no cover` (real `KernelServices` always defines `run_validation_fix_loop`).
**Fix:** delete the dead `else` branch + duplicated loop/`_SkippedRender`; lift the pure helpers to a shared module if any test needs them. (Verify test_strategies coupling first.)

## WR-08 — `run_fix_agent` documented but unimplemented  · cluster B
**File:** `task_loop.py:489` + contract docstring `:50`
**Mechanism:** the dead else-branch calls `runner.run_fix_agent(...)`; `KernelServices` defines no such method.
**Fix:** delete with WR-07; prune `run_fix_agent` from the contract docstring (or implement it).

---

## Cut for severity (real, lower priority — tracked, not in the 15)
- Efficiency: skeleton extra disk read per task (`task_loop.py:243`); `opendesign.load` disk read for planning agents (`opendesign.py:114`); seed-time `opendesign.load` discards its block map (`engine.py:2842`); uncached `compile_for_run` (`engine.py:222`).
- Test coverage: `_normalize.py` still strips `context_sources`, leaving half of `agent_input` permanently blinded.
- Simplification: deliverable double-assignment (`engine.py:1225`); `is_revision_workflow` redundant-derived state; 4 near-identical resolver shells; single-value `parser_name` branch.
