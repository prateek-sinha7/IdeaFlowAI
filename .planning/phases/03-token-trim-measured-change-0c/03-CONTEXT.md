# Phase 3: Token-Trim (measured change) [0C] - Context

**Gathered:** 2026-06-07
**Status:** Ready for planning

<domain>
## Phase Boundary

Wire the dead `_extract_html_skeleton` (engine.py:2616) as build-task-2+ context compaction: in `_build_context_message`, for `is_build_task_2_plus`, replace the full current-HTML block (up to 120k chars) with a ~1–3k char skeleton state-map. Prove a **≥50% reduction** in the task-2+ prompt input (deterministic CI gate) + a real-run token delta (SUMMARY evidence), while holding **semantic parity** (same pages/routes, equal-or-better validation) — the one sanctioned non-byte-identical change (INV-3 exception). Covers `prototype` and `od_prototype` (alias) via the single `prototype-build` path.

**This phase is one engine edit inside `_build_context_message` + its measurement/parity test scaffolding.** No manifests, no capability registry, no `CompactionStrategy` abstraction, no deletion of the inline helper (all Phase 7).

</domain>

<spec_lock>
## Requirements (locked via SPEC.md)

**7 requirements are locked.** See `03-SPEC.md` for full requirements, boundaries, and acceptance criteria.

Downstream agents MUST read `03-SPEC.md` before planning or implementing. Requirements are not duplicated here.

**In scope (from SPEC.md):**
- Replace the full `--- CURRENT HTML … ---` block with `_extract_html_skeleton(current_html)` on the `is_build_task_2_plus` branch of `_build_context_message`; task 1 and non-build agents unchanged.
- Deterministic offline CI test asserting ≥50% task-2+ prompt-input reduction.
- Record a real-run token/cost delta in the phase SUMMARY (live evidence).
- Re-baseline the prototype + od_prototype deliverable byte-goldens (sanctioned change).
- Keep the prototype + od_prototype semantic event snapshots green.
- Dedicated pages/routes + validation-pass parity assertion.
- Ensure/keep `read_file` access to `prototype.html` on the task-2+ path + a read-before-edit instruction.
- Applies to both `prototype` and `od_prototype` (od alias → prototype).

**Out of scope (from SPEC.md):**
- Registering `html_skeleton` as a `CompactionStrategy` capability — Phase 7 / PARITY-04.
- Deleting the inline `_extract_html_skeleton` / flipping ledger row **L13** to `☑` — Phase 7 (`0C→2`); L13 stays `☐`.
- Manifests, compiler, typed artifacts, persistence, model policy — later phases.
- Any change to `prototype_revision`, `ppt`/`od_ppt`, or code-gen deliverable bytes — stay byte-identical.
- Additional compaction tiers (Tier#2+) or compacting any non-build agent's prompt.
- Changing the 120k truncation constant or task-1 behavior.

</spec_lock>

<decisions>
## Implementation Decisions

> The SPEC locked the major calls (≥50% floor; deterministic CI gate + real evidence; re-baseline + pages/routes assertion; read_file access). These are the narrower HOW forks resolved in discussion. Two were discussed; two locked to the plan-grounded recommendation. All four landed on the recommended option.

### Skeleton injection framing (discussed)
- **D-01: Distinct skeleton-map marker + read_file pointer.** For `is_build_task_2_plus`, replace the full `--- CURRENT HTML (modify this — do NOT rebuild from scratch) ---` block (engine.py:2526-2536) with a distinctly-marked skeleton block — e.g. `=== CURRENT PROTOTYPE (skeleton — call read_file('prototype.html') for full content) ===` … `=== END CURRENT PROTOTYPE ===`. The framing MUST make clear this is a compact state-map (not the editable source) and point the agent at `read_file`. Task 1 (HTML shell, no prior HTML) is unchanged.
  - *Rationale:* honest framing stops the agent treating the map as full source; reinforces the read_file behavior right at the injection site. No AGENT.md edit is needed — `prototype-build/AGENT.md` (lines 40, 78) **already** mandates `read_file('prototype.html')` + "NEVER rebuild from scratch", so SPEC Req 7 is already satisfied by the existing prompt; the inline full-HTML block was redundant with it.

### Token-reduction gate test design (discussed)
- **D-02: Message-level ≥50% assertion with an inline-reconstructed full-HTML baseline.** The deterministic CI gate (SPEC Req 2) is a unit test that constructs a task-2 `prototype-build` context (ectx + `accumulated_outputs`) on a representative multi-page fixture and asserts `len(compacted_message) ≤ 0.5 × len(fullhtml_message)`, where `fullhtml_message` is the full-HTML block length the test computes inline (the size the old path would have injected, capped at 120k). Exercises the real `_build_context_message` injection site — faithful to SPEC Req 2's wording.
  - **D-02a:** Fixture = the `prototype.html` golden (the deliverable from the scripted 2-task build) — a realistic multi-page prototype so the ratio reflects real builds.

### Parity assertion approach (locked to recommendation)
- **D-03: Re-baseline deliverable goldens + hold the semantic snapshot + a focused pages/routes + validation assertion.** Re-record `prototype.html` + `od_prototype.html` deliverable byte-goldens via `SNAPSHOT_UPDATE=1` (the sanctioned INV-3 0C change), keep the `_normalize`d semantic event snapshots green (no golden edit), and add a focused assertion deriving the `data-page` ID set + `routes` map keys from the deliverable and comparing them to the pre-0C set, plus equal-or-better validation pass (zero net-new failures). Extend the characterization suite where natural; a small standalone pages/routes test is fine.
  - *Constraint:* ONLY prototype + od_prototype goldens may change — `prototype_revision`/`od_ppt`/`app_builder` deliverable goldens must stay byte-identical (`git diff` touches exactly two goldens).

### Real-run token-delta evidence (locked to recommendation)
- **D-04: Opt-in live-gated test logs the real token delta → SUMMARY.** Mirror the `test_deep_agent_runner_hitl_live.py` opt-in/SSO-gated pattern: a live test runs the multi-task build (with vs without compaction) against a real model and logs accumulated input-token totals; the measured delta + reproduction command are copied into `03-*-SUMMARY.md` as COMPACT-03 evidence. Evidence-only, **NOT** a CI gate (the CI gate is D-02). If a live run isn't available at execution time, fall back to a documented manual-run procedure recorded in SUMMARY.

### Claude's Discretion
- Exact marker wording/casing for the skeleton block (D-01), provided it is visually distinct from the old CURRENT-HTML block AND carries a `read_file('prototype.html')` pointer.
- Whether the ≥50% gate test (D-02) lives in a new `tests/agents/test_phase3_*.py` or extends an existing characterization module.
- **Edge case:** if task-1 HTML is empty or starts with `[Error:`, keep today's guard (engine.py:2528) — emit no skeleton block (and no full HTML), exactly as the current code skips the block. No skeleton on empty/error HTML.
- Leave `_extract_html_skeleton`'s extraction logic as-is (recommended — purpose-built; the parity gate constrains changes), unless the pages/routes assertion surfaces a concrete gap.
- Keep the `=== TEMPLATE COMPLIANCE ===` reminder (engine.py:2542-2547) for task-2+ (recommended: keep — low token cost).
- Plan-task granularity (ROADMAP suggests 03-01 wire+measure, 03-02 re-baseline+parity — keep or resplit as planning sees fit).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Locked requirements (read FIRST)
- `.planning/phases/03-token-trim-measured-change-0c/03-SPEC.md` — the 7 locked requirements (COMPACT-01/02/03 + derived), boundaries, acceptance criteria. **Locked requirements — MUST read before planning.**

### The specification (authoritative)
- `specs/003-workflow-engine-decoupling/plan.md` — Phase 0C anchors:
  - **§25 lines 806-809** — Phase 0C accept criteria (equal-or-better validation pass; measured token reduction; gated on **semantics**, not byte-identity).
  - **§24 lines 785-792** — the snapshot/gating model (deliverable byte where deterministic; semantic event snapshot with volatile fields normalized; 0C is the sanctioned exception gated on semantic + token delta).
  - **§3 line 252** — INV-3 (the one sanctioned compaction/context-change exception).
  - **§4 line 282** — the L13 leak row (plan's numbering: `_extract_html_skeleton` 2565-2628; current actual is engine.py:2616-2679).
  - **lines 590-625** — the target manifest `compaction: html_skeleton` (Tier#1) + the L13 → `CompactionStrategy(html_skeleton)` new-home mapping (Phase 7 re-expression).
- `specs/003-workflow-engine-decoupling/migration-ledger.md` — the **L13** row: grep pattern `_extract_html_skeleton`, owning phase `0C→2`, **stays `☐`** in 0C (0C wires; Phase 7 deletes). The Phase-1 ledger ratchet must stay green (L13 grep NOT enforced yet).

### Project planning
- `.planning/REQUIREMENTS.md` — COMPACT-01/02/03 (lines 32-34) with plan anchors; PARITY-04 (line 71 — the Phase-7 capability re-expression, out of scope here).
- `.planning/ROADMAP.md` §"Phase 3" (lines 83-100) — goal, 3 success criteria, candidate plan breakdown (03-01/03-02).
- `.planning/PROJECT.md` — invariants/constraints (INV-3 sanctioned exception; INV-12 no-dual-impl; the L13 entry in the §4 leak map; "everything from plan.md honored — nothing dropped").
- `.planning/phases/02-executioncontext-ownership-0b/02-CONTEXT.md` — prior-phase decisions that constrain this phase: ectx threading (D-03), `_current_task_block` parked on ectx (D-02), the `_scripted_model._drive` parity harness, commit scopes.

### Code to read (targets / assets)
- `backend/agents/execution_engine/engine.py`:
  - `_extract_html_skeleton` **:2616-2679** — the helper to wire (currently dead; extracts `:root` tokens, `routes` map, filled/empty `data-page` IDs, chrome type, total size).
  - `_build_context_message`: `is_build_task_2_plus` flag **:2428**; existing task-2+ trims (DS/template/example/layouts) **:2434-2493**; the full-HTML block to replace **:2526-2536** (guard `if current_html and not current_html.startswith("[Error:")`); the `=== TEMPLATE COMPLIANCE ===` block **:2542-2547**.
  - `_run_build_task_loop` **:1478+** — reads `prototype.html` back into `accumulated_outputs["prototype-build"]` **:1592-1594** (the HTML the skeleton summarizes).
- `backend/agents/prompts/prototype-build/AGENT.md` — lines **40, 78** already mandate `read_file('prototype.html')` + "NEVER rebuild" (SPEC Req 7 already satisfied → no prompt edit).
- `backend/agents/registry.py` — `_OD_ALIAS_BASE` `{od_prototype: prototype}` **(~:256-263)** — the change covers od_prototype automatically.
- `backend/tests/agents/_scripted_model.py` — `_drive()` offline harness; the scripted `prototype-plan` emits exactly **2 tasks** **(:198-204)** — the multi-task build for measurement/parity.
- `backend/tests/agents/characterization/` — `__init__.py` (`assert_deliverable_snapshot`, `extract_final_output`, `SNAPSHOT_UPDATE`), `_normalize.py` (semantic event snapshot helpers), `golden/` (`prototype.html`, `od_prototype.html`, `*.events.json` to re-baseline / keep).
- `backend/tests/agents/test_characterization_prototype.py` / `test_characterization_od_prototype.py` — the deliverable + event snapshot tests to re-baseline (deliverable) / hold (events).
- `backend/tests/agents/test_deep_agent_runner_hitl_live.py` — the opt-in/SSO-gated live-test pattern for D-04 (real-run token delta).
- `backend/pyproject.toml` **:170-191** — vulture config (`min_confidence=80`; `_extract_html_skeleton` is a method → not flagged → no allow-list change needed).
- `backend/CLAUDE.md` — backend architecture guide (engine = deterministic sequencer; the prototype build loop; commit scopes `engine`/`tests`; `SNAPSHOT_UPDATE=1` regen recipe).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`_extract_html_skeleton(html)`** (engine.py:2616) — the purpose-built compaction helper; wire as-is (it already emits `:root` tokens, routes, filled/empty pages, chrome, size).
- **`_scripted_model._drive("prototype")` + 0A goldens** — offline parity harness; already runs the 2-task build used for measurement and parity.
- **`SNAPSHOT_UPDATE=1` golden regeneration** (`characterization/__init__.py` + `_normalize.py`) — the sanctioned re-baseline mechanism for D-03.
- **`test_deep_agent_runner_hitl_live.py`** — opt-in live-test scaffold to copy for D-04.

### Established Patterns
- `ectx` is already threaded through `_build_context_message` (Phase 2) — the skeleton wiring rides the existing `is_build_task_2_plus` branch; no new state, no signature change.
- Snapshot split: semantic event snapshot = order-canonical multiset (held green); deliverable byte snapshot = exact (re-baselined for prototype/od_prototype only). 0C is the one phase allowed to move deliverable bytes.
- `od_prototype` = alias → `prototype` (registry) — single code path; one edit covers both.
- Dev runtime: `python3.11`, no venv; `cd backend && python3.11 -m pytest tests/agents/ -v`; commit scopes `engine`/`tests`; PR off `feature/003-workflow-engine-decoupling` (never `main`).

### Integration Points
- The ONLY engine edit is inside `_build_context_message`'s `is_build_task_2_plus` branch (swap full-HTML block → skeleton block). No new module, no kernel-leak change (L13 stays `☐`).
- Test surface: new ≥50% gate test + pages/routes parity assertion in `tests/agents/`; re-baselined goldens in `characterization/golden/`; optional live test for the real-run delta.
- Migration ledger L13 row untouched (`☐`); the Phase-1 ledger ratchet stays green.

</code_context>

<specifics>
## Specific Ideas

- Standing project directive (init): *"everything from plan.md must be honored — nothing dropped."* For 0C: this is the sanctioned **INV-3 exception** (semantic parity + measured delta, not byte-identity); **L13 stays `☐`** (deletion is Phase 7's `CompactionStrategy(html_skeleton)` re-expression, PARITY-04).
- The build agent's `read_file('prototype.html')` behavior is **already mandated** by its AGENT.md (lines 40/78) — the skeleton is an orienting state-map layered on top, not a replacement for reading the file.
- User selected the recommended option on all four areas (two discussed, two locked) — treat as locked unless this file is edited.

</specifics>

<deferred>
## Deferred Ideas

- **`html_skeleton` as a registered `CompactionStrategy`** — Phase 7 [2] / PARITY-04. Re-expresses this 0C inline wiring behind the capability (behavior-preserving vs 0C) and deletes the inline `_extract_html_skeleton` (L13 grep → 0).
- **`_current_task_block` → `TaskLoopStrategy`** — Phase 7 (carried from 02-CONTEXT D-02). Not touched here.
- **Compaction for non-build agents / additional tiers (Tier#2+)** — not in this milestone's 0C; new capability work.

None of these are scope creep — all are explicitly later-phase per ROADMAP.md / the §31 ledger.

</deferred>

---

*Phase: 3-Token-Trim (measured change) [0C]*
*Context gathered: 2026-06-07*
