---
phase: 15-live-pass-prompt-contract-closure
fixed_at: 2026-06-13T01:25:00Z
review_path: .planning/phases/15-live-pass-prompt-contract-closure/15-REVIEW.md
iteration: 1
findings_in_scope: 4
fixed: 4
skipped: 0
status: all_fixed
---

# Phase 15: Code Review Fix Report

**Fixed at:** 2026-06-13T01:25:00Z
**Source review:** .planning/phases/15-live-pass-prompt-contract-closure/15-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 4 (WR-01..WR-04; IN-01/IN-02 out of scope per fix_scope, left documented)
- Fixed: 4
- Skipped: 0

## Fixed Issues

### WR-01: od-ppt-validator contradictory instructions on non-minimally-patchable defects

**Files modified:** `backend/agents/prompts/od-ppt-validator/AGENT.md`
**Commit:** aa33d5ea
**Applied fix:** Added an explicit precedence rule to `## RULES`: P0 structural/functional repairs and bounded P1 placeholder substitutions (smallest content consistent with the slide's own title and the deck) are the ONLY sanctioned exceptions to the SURGEON rule; everything else stays exactly as-is. The OUTPUT CONTRACT explicitly outranks the checklist — a fix requiring a rewrite/redesign is skipped and the deck re-emitted as-is, in full. All existing contract pins (exactly-ONE-artifact, contract-above-checklist, single `## OUTPUT CONTRACT` heading) remain intact.

### WR-02: app-sdlc-governance "state the assumption" had no permitted location under the begin-directly / no-prose contract

**Files modified:** `backend/agents/prompts/app-sdlc-governance/AGENT.md`
**Commit:** e0cc2e84
**Applied fix:** Rewrote the assumption instruction to "record the assumption INSIDE the relevant file block (e.g., as an 'Assumptions' note in the ADR's Context section — never as prose outside a block)". The begin-directly first-token shape stays pinned. Checked dotnet-/mulesoft-sdlc-governance for the same conflict: neither contains any assumption wording (grep count 0) — no alignment edit needed.

### WR-03: Frontmatter freeze pinned only 3 of the behavior-bearing fields

**Files modified:** `backend/tests/agents/test_prompt_contracts.py`
**Commit:** 0557423f
**Applied fix:** Replaced the 4-tuple parametrize with a `_FROZEN_FRONTMATTER` dict pinning order, pipeline_type, tools, guardrails, context_from, max_tokens, injects, and gate for all five agents. Frozen expectations captured from the live `load_agent_spec` values (e.g., dotnet `guardrails=["dotnet"]`, mulesoft `guardrails=["mulesoft", "java-spring"]`, all five `injects=[]`, `gate=None`). Module docstring and test docstring updated to state the actual coverage honestly.

### WR-04: Anti-fabrication pin weaker than its cited pitfalls (exactly-once; Pitfall-5 negative assertion)

**Files modified:** `backend/tests/agents/test_prompt_contracts.py`
**Commit:** 7b507ce7
**Applied fix:** (a) `body.count(token) == 1` for `<function_calls>`, `<invoke>`, `write_todos` across all three governance bodies (Pitfall 7 — repetition re-primes fabrication; verified all three bodies currently carry each token exactly once). (b) `assert "filename:" not in body` for the dotnet/mulesoft branch only (Pitfall 5). app-sdlc-governance verified first: its body legitimately contains 7 `filename:` occurrences (app_builder file blocks), so the negative pin correctly excludes it.

## Verification (required post-fix gates)

- `python3.11 -m pytest tests/agents/test_prompt_contracts.py tests/agents/test_loader.py -q` — **55 passed**
- `python3.11 -m pytest tests/agents/test_characterization_od_ppt.py -q` — **2 passed** (goldens byte-identical)
- `/opt/homebrew/bin/lint-imports` — **4 kept / 0 broken**
- Constraint checks: AGENT.md frontmatter untouched on all five agents (WR-03 pins only); zero edits to `agents/capabilities/`, `_scripted_model.py`, `live_harness.py`, golden fixtures.

## Out of Scope (left documented in 15-REVIEW.md)

- IN-01: od_context seed duplication vs `_scripted_model._drive`
- IN-02: tautological narration assertion / narration-magnitude comment accuracy

---

_Fixed: 2026-06-13T01:25:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
