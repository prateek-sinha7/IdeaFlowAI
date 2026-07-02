---
phase: quick-260702-gri
plan: 01
subsystem: config / ingest-caps
tags: [config, file_extract, frontend-constants, brief-cap]
requires: []
provides:
  - "settings.BRIEF_MAX_CHARS == 450_000 (single source: planner + clarify + upload extraction)"
  - "file_extract._MAX_TEXT_CHARS derived from settings.BRIEF_MAX_CHARS"
  - "frontend ATTACH_MAX_CHARS == 450000 (single source for the 3 attach slices)"
affects:
  - backend/app/core/config.py
  - backend/app/api/file_extract.py
  - frontend/src/lib/constants.ts
tech-stack:
  added: []
  patterns: ["single-source-of-truth for ingest caps (BE settings + FE constant)"]
key-files:
  created:
    - frontend/src/lib/constants.ts
  modified:
    - backend/app/core/config.py
    - backend/app/api/file_extract.py
    - backend/tests/unit/test_brief_max_chars.py
    - frontend/src/app/workflow/prototype/templates/page.tsx
    - frontend/src/app/workflow/ppt/templates/page.tsx
    - frontend/src/components/workflow/IdeaInputPage.tsx
decisions:
  - "450,000 chars ≈ ~150k tokens dense / ~112k prose; safe under Haiku 200k window"
  - "One intentional value pin remains in tests (settings.BRIEF_MAX_CHARS == 450_000)"
metrics:
  duration: ~10m
  completed: 2026-07-02
---

# Phase quick-260702-gri Plan 01: Raise Brief Cap to 450k Chars Summary

Raised the input-brief character cap from 64k to 450,000 chars (~150k tokens, safe under Haiku's
200k window) and unified the three drifting ingest caps behind one source of truth per side:
backend `settings.BRIEF_MAX_CHARS`, frontend `ATTACH_MAX_CHARS`.

## What Was Built

- **Task 1 — Backend single source.** `config.py` `BRIEF_MAX_CHARS` 64_000 → 450_000 with a
  rewritten rationale comment (chars→tokens ratios, single-source note). `file_extract.py` now
  imports `settings` and sets `_MAX_TEXT_CHARS = settings.BRIEF_MAX_CHARS`; both stale "16,000"
  docstrings (module + endpoint) corrected to reflect `settings.BRIEF_MAX_CHARS` (~450,000).
  `_MAX_FILE_BYTES` (10 MB) and the slice/`truncated` logic left unchanged.
- **Task 2 — Frontend single shared cap.** New `frontend/src/lib/constants.ts` exports
  `ATTACH_MAX_CHARS = 450000`. All three attach sites (prototype templates page, ppt templates
  page, IdeaInputPage) import it and slice with it; their binary-upload truncation notes now
  interpolate `${ATTACH_MAX_CHARS.toLocaleString()}` ("450,000") so the displayed number tracks
  the cap. Revision (40k/60k) and cross-pipeline (4k) slices untouched.
- **Task 3 — Value-agnostic tests.** `test_brief_max_chars.py` derives brief/user_request lengths
  from `settings.BRIEF_MAX_CHARS` (halves for the "reaches uncut" cases, `+10_000` for the ceiling
  case); removed bare `2000`/`64000` literals; kept ONE intentional value pin
  (`settings.BRIEF_MAX_CHARS == 450_000`). Confirmed no existing file_extract cap test exists
  (grep returned none).

## Verification

- Import smoke: `settings.BRIEF_MAX_CHARS == 450000` and `file_extract._MAX_TEXT_CHARS == 450000` — OK.
- `tests/unit/test_brief_max_chars.py` — 4 passed.
- `tests/unit/test_clarify_json_parse.py` — 11 passed.
- INV-3 goldens (prototype, od_prototype, prototype_revision, app_builder) — 8 passed,
  byte/event-identical, NO snapshot update. (od_ppt not run — known environmental.)
- `lint-imports` — 4 contracts kept / 0 broken.
- `npx tsc --noEmit` — the 3 touched files + new `constants.ts` are error-free.

## Deviations from Plan

None - plan executed exactly as written.

## Pre-existing Errors Noted (Not Fixed)

Per scope constraints, these pre-existing, unrelated tsc errors remain and were NOT fixed:
- `frontend/src/components/workflow/IdeaInputPage.tsx(738,9)` TS17001 — duplicate `initialSelections`
  JSX attribute (present in HEAD before this change; outside this task's touched lines).
- `frontend/e2e/fixtures/mockApi.ts(95,21)` and `(96,22)` TS2352 — pre-existing readonly-tuple casts.

## Self-Check: PASSED

- Created file exists: `frontend/src/lib/constants.ts` — FOUND.
- Commit exists: `f351d446` — FOUND.
