---
phase: 15-live-pass-prompt-contract-closure
plan: 02
subsystem: tests
tags: [prompt-contracts, pytest-pins, lv-02, od-ppt, sdlc-governance, infra-generator, characterization, inv-3]

# Dependency graph
requires:
  - phase: 15-live-pass-prompt-contract-closure
    provides: "15-01 exact contract wording in the five AGENT.md bodies (the tokens this plan pins)"
  - phase: 08
    provides: "live_harness.drive_engine_pipeline per-agent model factory + CaptureResult contract"
  - phase: 07
    provides: "PptResolver + unwrap_artifact first-match semantics (the REAL resolver the composition test drives through)"
provides:
  - "backend/tests/agents/test_prompt_contracts.py — durable pytest pins for all five 15-01 contract bodies (LV-02/F4/F5), per D-04"
  - "Frontmatter freeze pin for the five edited agents (order/pipeline_type/tools) — T-15-01 mitigation made durable"
  - "LV-02 composition proof: contract-shaped scripted validator through REAL engine + REAL PptResolver resolves final_output to the deck, not QA narration"
  - "Phase gate evidence: 5 characterization pipelines byte-identical (INV-3), lint-imports clean — the offline-evidence pointer 15-03 cites"
affects: [15-03 offline gate + live re-check]

# Tech tracking
tech-stack:
  added: []
  patterns: ["per-test contract-shaped model injected via drive_engine_pipeline(model=factory) — pins live-evidence shapes without touching the golden-pinned _scripted_model.py"]

key-files:
  created:
    - backend/tests/agents/test_prompt_contracts.py
  modified: []

key-decisions:
  - "LV-02 composition deck carries NO <style> block so sanitize_carousel_deck_html is a verified no-op — the test isolates unwrap-first-match resolution, the exact LV-02 mechanism"
  - "Narration constant contains no <artifact token, mirroring the contract's anywhere-else prohibition — proves commentary-first cannot win the first-match unwrap"
  - "Frontmatter freeze asserts list(spec.tools) (od-ppt-validator [workspace] kept intentional — RESEARCH Pitfall 4, never normalize)"

patterns-established:
  - "Prompt-contract pins assert on load_agent_spec(id).prompt_body (parser-surviving), never raw file reads"

requirements-completed: [LV-02, F4-residual, F5-residual]

# Metrics
duration: ~9min
completed: 2026-06-13
---

# Phase 15 Plan 02: Prompt-Contract Pins + LV-02 Composition Proof Summary

**Durable pytest layer (11 nodes) pinning all five 15-01 prompt contracts plus an offline REAL-engine/REAL-resolver drive proving a contract-shaped validator (QA narration first, single artifact-wrapped deck second) resolves final_output to the deck — with the 5 characterization goldens proven byte-identical (INV-3) and zero harness/golden/resolver edits.**

## Performance

- **Duration:** ~9 min
- **Started:** 2026-06-13T00:27:13Z
- **Completed:** 2026-06-13T00:36:00Z
- **Tasks:** 2 (1 implementation + 1 verification-only gate)
- **Files modified:** 1 (created)

## Accomplishments

- **D-04 durable pin layer:** `backend/tests/agents/test_prompt_contracts.py` (246 lines, 11 test nodes) upgrades 13-03's grep-only acceptance to persistent pytest — the contract lines now fail CI if removed by any future prompt rewrite.
  - `test_od_ppt_validator_deck_reemission_contract` — pins `exactly ONE <artifact>`, `complete corrected HTML deck`, `even when you change nothing`; positional pin (contract index < `## VALIDATION CHECKLIST` index); `## OUTPUT CONTRACT` count == 1 (no dual-contract drift).
  - `test_sdlc_governance_anti_fabrication_contract` (3 parametrized) — pins `You have NO tools`, `<function_calls>`, `<invoke>`, `write_todos`, `Begin your response DIRECTLY with` per body; app-only `fenced block` + negative pin `Read the concrete choices` absent (trigger defused); dotnet/mulesoft-only `the first Markdown heading`.
  - `test_infra_generator_api_v1_contract` — `/api/v1` count >= 6 (actual: 8), `API PATH CONTRACT` present and positioned above `OUTPUT FORMAT`, concrete examples `/api/v1/health` + `location /api/v1/` pinned.
  - `test_contract_agents_frontmatter_frozen` (5 parametrized) — (order, pipeline_type, tools) frozen for all five agents, including od-ppt-validator's intentional `tools: [workspace]`.
- **LV-02 composition proof:** `test_od_ppt_deck_resolution_with_contract_shaped_validator` drives the od_ppt pipeline through the REAL engine + REAL `PptResolver` + REAL prompts with only the model scripted: the validator streams multi-sentence QA narration FIRST, then one artifact-wrapped COMPLETE deck (the live LV-02 evidence shape). Asserts `final_output` starts with `<!DOCTYPE html>`, contains `<section class="slide"`, does NOT contain the narration, and `deliverable == final_output`. The contract-shaped validator is a per-test model injected via `drive_engine_pipeline(model=factory)` — zero edits to `_scripted_model.py` (whose validator bytes ARE the od_ppt goldens).
- **INV-3 phase gate (mandatory PROOF per D-04):** full targeted suite green with goldens byte-identical.

## Phase Gate Evidence (15-03 cites this)

Gate command (from `backend/`, `python3.11`, no venv, `SNAPSHOT_UPDATE` env count = 0):

```
python3.11 -m pytest tests/agents/test_characterization_prototype.py \
  tests/agents/test_characterization_od_prototype.py \
  tests/agents/test_characterization_prototype_revision.py \
  tests/agents/test_characterization_od_ppt.py \
  tests/agents/test_characterization_app_builder.py \
  tests/agents/test_loader.py tests/agents/test_prompt_contracts.py \
  tests/agents/test_banned_patterns.py tests/agents/test_migration_ledger.py -q
```

- **Result: 99 passed, 7 skipped in 35.58s** (skips are opt-in live/Bedrock-gated tests in the loader/banned-patterns files, NOT characterization).
- Characterization-only re-run: **10 passed, 0 skipped** — all 5 snapshot pipelines (prototype / od_prototype / prototype_revision / od_ppt / app_builder) green.
- `/opt/homebrew/bin/lint-imports`: **Contracts: 4 kept, 0 broken** (exit 0) — hexagonal boundaries intact.
- Porcelain-empty proof: `git status --porcelain tests/agents/characterization/golden/ tests/agents/_scripted_model.py agents/capabilities/deliverables/` → **0 lines** (goldens byte-identical, ROADMAP SC4); overall `git status --porcelain` clean after the Task-1 commit.
- New-test quick run: `pytest tests/agents/test_prompt_contracts.py -q` → **11 passed in 0.84s**; `-k deck_resolution` → 1 passed.

## Task Commits

1. **Task 1: test_prompt_contracts.py (prompt pins + frontmatter freeze + LV-02 composition)** - `d4dc4861` (test)
2. **Task 2: Full targeted offline phase gate (INV-3)** - verification-only, no file changes (evidence recorded above)

## Files Created/Modified

- `backend/tests/agents/test_prompt_contracts.py` - 11 test nodes: 3 contract-pin tests (1 + 3 + 1 parametrized nodes), 5-node frontmatter freeze, 1 async LV-02 composition test; imports `load_agent_spec` (loader parse path) + `drive_engine_pipeline`/`ScriptedFakeChatModel`/`_ScriptedTurn`/`_scripts_for` (harness, import-only)

## Decisions Made

- The composition test's `_DECK` deliberately omits `<style>` so `sanitize_carousel_deck_html` (which requires `<style` + translateX-vw + .stage/.slide to act) is a verified pass-through — the assertion isolates the unwrap-first-match resolution path, the exact LV-02 mechanism.
- `_NARRATION` contains no `<artifact` token — mirrors the shipped contract's "never use the literal <artifact tag anywhere else" rule and proves commentary-first output cannot win the first-match unwrap.
- Frontmatter freeze uses `list(spec.tools)` comparison and keeps od-ppt-validator's `[workspace]` as-shipped (RESEARCH Pitfall 4: the frontmatter is authoritative; never "normalize").
- od_context seed copied verbatim from `_scripted_model._drive` (template_body/template_id/ds_id/ds_body/craft_block/is_design_system_required) so `_compose_injection` succeeds without touching the harness.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## Known Stubs

None — additive test file only; no production code or data paths touched.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- 15-03 (offline gate + live re-check) can cite this SUMMARY's Phase Gate Evidence section as the offline-evidence pointer (D-05).
- ROADMAP SC4 fully landed offline: contract pins durable, LV-02 resolver+contract composition proven end-to-end, goldens byte-identical.
- Live re-check (~$0.10 od_ppt run + od_ppt_output revision) remains the 15-03 item per the defer-live-verification convention.

## Self-Check: PASSED

- `backend/tests/agents/test_prompt_contracts.py` exists on disk (246 lines, >= 80 min_lines).
- Commit `d4dc4861` present in git log.
- Plan diff confined to the new test file; forbidden-file porcelain empty.

---
*Phase: 15-live-pass-prompt-contract-closure*
*Completed: 2026-06-13*
