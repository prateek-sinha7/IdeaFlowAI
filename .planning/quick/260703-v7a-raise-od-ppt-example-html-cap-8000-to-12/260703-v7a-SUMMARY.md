---
phase: quick-260703-v7a
plan: 01
subsystem: agents / od_ppt context delivery
tags: [od_ppt, context-provider, example-html, prompt-honesty, INV-12, INV-3]
requires: []
provides:
  - "od-ppt-composer receives the FULL example.html (deck templates up to ~94k injected untruncated)"
  - "Single authoritative example.html cap (EXAMPLE_MAX_CHARS = 120_000) at od_context.get_example_html (INV-12)"
  - "od-ppt-brief-analyst prompt body no longer claims to receive DESIGN.md it never gets"
affects:
  - backend/agents/execution_engine/od_context.py
  - backend/agents/capabilities/context_providers/opendesign.py
  - backend/agents/prompts/od-ppt-brief-analyst/AGENT.md
tech-stack:
  added: []
  patterns: ["single-truncation at one authoritative point (INV-12)"]
key-files:
  created: []
  modified:
    - backend/agents/execution_engine/od_context.py
    - backend/agents/capabilities/context_providers/opendesign.py
    - backend/tests/agents/test_context_providers.py
    - backend/agents/prompts/od-ppt-brief-analyst/AGENT.md
decisions:
  - "Cap raised to a bounded module constant EXAMPLE_MAX_CHARS = 120_000 (not removed) — covers catalog max ~93,663 with headroom, well under Haiku's 200k window (T-v7a-01 mitigate)."
  - "Consolidated the double-truncation to the single od_context point; the provider now injects the runner-capped string directly (INV-12)."
  - "design_system NOT added to od-ppt-brief-analyst injects (would change the od_ppt golden for no benefit) — prompt reworded instead to be honest."
metrics:
  duration: ~8 min
  completed: 2026-07-03
---

# Phase quick-260703-v7a Plan 01: Raise od_ppt example.html cap 8000→120k + prompt honesty Summary

Two register-adherent, backend-only od_ppt context-delivery fixes, both proven INV-3-neutral (no golden regeneration): the composer now receives the full deck template example.html (single 120k cap, redundant second clip removed), and the brief-analyst prompt stops promising a DESIGN.md body it never receives.

## What Was Built

### FIX 1 — example.html cap raised to 120k + double-truncation consolidated (Task 1, TDD)
- `od_context.py`: added module-level `EXAMPLE_MAX_CHARS = 120_000` (import-neutral, no new import); `get_example_html` default changed `8000 → EXAMPLE_MAX_CHARS`. Seed `[:6000]` / reference `[:4000]` caps untouched.
- `opendesign.py`: removed the redundant second `[:8000]` re-truncation (old lines 136-139); the `TEMPLATE EXAMPLE` block now takes the runner-capped string directly (INV-12 single-truncation). Docstring line ~11 updated from `example[:8000]` to reference the od_context cap. The example.html GATE (`is_builder or "template_example" in injects`, ~line 130) is unchanged.
- `test_context_providers.py`: new regression pin `test_opendesign_composer_example_not_truncated` — a composer-shaped ctx with a >8000-char example asserts the injected block is the FULL example (no `...[truncated]`). RED confirmed against the old provider clip, GREEN after removal.

### FIX 2 — od-ppt-brief-analyst prompt honesty (Task 2)
- `od-ppt-brief-analyst/AGENT.md`: body-only reword (frontmatter byte-unchanged, `injects:[template]` intact). Dropped the "ACTIVE DESIGN SYSTEM — full DESIGN.md body" input-list claim; reframed the design-system rule as applied downstream by the Deck Engineer (the composer), referenced symbolically by the planner.

## Verification Results

- Task 1 grep guards: PASS (`EXAMPLE_MAX_CHARS = 120_000` present; `max_chars: int = EXAMPLE_MAX_CHARS`; no `= 8000` in od_context; no `[:8000]` in opendesign; `[:6000]`/`[:4000]` retained).
- New pin `test_opendesign_composer_example_not_truncated`: RED (fails on old `...[truncated]` clip) → GREEN (block == full >8000-char example).
- `test_context_providers.py` + `test_context_message_oracle.py`: 30 passed.
- 5 characterization goldens (prototype, od_prototype, prototype_revision, app_builder, od_ppt) with SNAPSHOT_UPDATE UNSET: 10 passed — byte/event-identical, no regen (hard gate held for both fixes).
- Task 2 guards: PASS (no "full DESIGN.md body"; `injects:\n- template\n` intact).
- lint-imports: 4 kept, 0 broken.
- Scope fence: `git status --porcelain` (code) shows only the 4 target files across the two commits; only the docs dir untracked.

## Deviations from Plan

None — plan executed exactly as written.

## Commits

- `9eea4215` fix(agents): raise od_ppt example.html cap 8000->120k + consolidate double-truncate
- `00b72b00` fix(prompts): trim od-ppt-brief-analyst dangling DESIGN.md claim (symbolic planning)

## Self-Check: PASSED
- FOUND: backend/agents/execution_engine/od_context.py (EXAMPLE_MAX_CHARS = 120_000)
- FOUND: backend/agents/capabilities/context_providers/opendesign.py (no [:8000])
- FOUND: backend/tests/agents/test_context_providers.py (new pin)
- FOUND: backend/agents/prompts/od-ppt-brief-analyst/AGENT.md (reworded, injects intact)
- FOUND commit: 9eea4215
- FOUND commit: 00b72b00
