---
phase: quick-260703-d4v
plan: 01
subsystem: backend-api
tags: [brief-cap, prototype-run, pydantic-validation, inv-3]
requires:
  - settings.BRIEF_MAX_CHARS (app/core/config.py — already 450k, commit f351d446)
provides:
  - POST /api/prototype/run accepts briefs up to settings.BRIEF_MAX_CHARS (450k)
affects:
  - backend/app/api/prototype_templates.py (RunRequest.brief cap)
tech-stack:
  added: []
  patterns:
    - "Source per-endpoint brief caps from settings.BRIEF_MAX_CHARS (no magic numbers)"
key-files:
  created:
    - backend/tests/unit/test_prototype_run_request.py
  modified:
    - backend/app/api/prototype_templates.py
decisions:
  - "Cap sourced from settings.BRIEF_MAX_CHARS constant, not a literal (self-maintaining, matches planner/clarify/upload precedent)"
  - "Change is additive/permissive — INV-3 preserved for briefs <= 8000 chars"
metrics:
  duration: ~12 min
  completed: 2026-07-03
---

# Quick 260703-d4v: Raise prototype run endpoint brief cap Summary

Raised the `POST /api/prototype/run` request-body brief cap from a hardcoded
`8000` (a Phase-4 OpenDesign straggler) to the app-wide `settings.BRIEF_MAX_CHARS`
(450,000 chars ~= 150k tokens), so briefs >8000 chars no longer get a spurious 422
here while working on every other brief-ingest path (planner / clarify / upload).

## What Was Done

### Task 1 — Source the RunRequest brief cap from settings.BRIEF_MAX_CHARS (commit fe2da746)
- Added `from app.core.config import settings` to `backend/app/api/prototype_templates.py`,
  placed alphabetically in the `app.*` import group (immediately before
  `from app.core.dependencies import get_current_user`), reusing the exact form from
  `file_extract.py:25`.
- Changed `RunRequest.brief` cap from `max_length=8000` to
  `max_length=settings.BRIEF_MAX_CHARS`. `min_length=1` unchanged. Effective cap is
  now 450,000 (verified: `brief` metadata = `[MinLen(1), MaxLen(450000)]`).
- `od_context.py:170` (`max_chars=8000`) and `config.py` left untouched, as instructed.
- No frontend `maxLength` exists on the prototype brief input (previously confirmed by grep) —
  no FE change needed; the backend Pydantic cap is the hard 422 gate.

### Task 2 — Validation test + offline gates (commit 834eb0f4)
- Created `backend/tests/unit/test_prototype_run_request.py` (5 direct Pydantic-model tests):
  - brief of length 9000 (over the old 8000 cap) constructs OK and round-trips length 9000
  - empty brief still raises `ValidationError` (min_length=1)
  - the effective `MaxLen` constraint (read off `model_fields["brief"].metadata`) equals
    `settings.BRIEF_MAX_CHARS` — fails if anyone reverts to a literal
  - a brief at exactly `settings.BRIEF_MAX_CHARS` length constructs OK (boundary)
  - one char past the cap is rejected (cap stays bounded — no DoS surface)

## Verification / Gate Results

| Gate | Result |
|------|--------|
| Task 1 verify (grep + module import) | PASS — `settings` imported, `max_length=settings.BRIEF_MAX_CHARS` present, no `max_length=8000` remains, module imports cleanly; brief metadata = `[MinLen(1), MaxLen(450000)]` |
| New `test_prototype_run_request.py` | PASS — 5/5 |
| Characterization goldens (INV-3, NO SNAPSHOT_UPDATE) | 4/5 byte/event-identical: prototype, od_prototype, prototype_revision, app_builder PASS. od_ppt FAIL — proven PRE-EXISTING (see Deferred) |
| `lint-imports` (§31 hexagonal) | PASS — 4 kept, 0 broken |
| Final code scope (`git status --porcelain`) | Only `backend/app/api/prototype_templates.py` + `backend/tests/unit/test_prototype_run_request.py` (both committed); no other code touched |

## Deviations from Plan

None to the source/test changes. Plan executed exactly as written.

## Deferred Issues

**`test_characterization_od_ppt.py::test_od_ppt_event_snapshot` fails at base HEAD (out of scope).**
- The od_ppt golden diverges at index 3 (`agent_input` / `context_message` for
  `od-ppt-brief-analyst`).
- Proven PRE-EXISTING: reverted `prototype_templates.py` to its parent version
  (`max_length=8000`) and the same golden failed IDENTICALLY. This task only touches the
  `RunRequest.brief` API model; the od_ppt golden drives the engine via `ndjson_adapter`
  and never constructs `RunRequest`, so this change cannot affect that stream.
- INV-3 for this change is intact: the 4 relevant goldens pass byte/event-identical with
  no snapshot update. Logged to
  `.planning/quick/260703-d4v-.../deferred-items.md`. Do NOT regenerate the od_ppt golden here.

## Commits

- `fe2da746` — fix(api): source prototype run brief cap from settings.BRIEF_MAX_CHARS (260703-d4v)
- `834eb0f4` — test(api): pin RunRequest.brief cap to settings.BRIEF_MAX_CHARS (260703-d4v)

## Self-Check: PASSED
- FOUND: backend/app/api/prototype_templates.py
- FOUND: backend/tests/unit/test_prototype_run_request.py
- FOUND commit: fe2da746
- FOUND commit: 834eb0f4
