# Deferred Items — 260702-u2o (Workstream B1)

Out-of-scope pre-existing issues discovered during execution. NOT caused by this
plan's changes (proven pre-existing via `git stash` on clean HEAD 99125327). Left
untouched per the scope fence (FE B1 = fetcher + types + state + payloads only).

| Item | File | Error | Note |
|------|------|-------|------|
| Pre-existing tsc TS17001 | `frontend/src/components/workflow/IdeaInputPage.tsx:738` | JSX elements cannot have multiple attributes with the same name | Present on clean HEAD before any B1 edit; unrelated to revision families. |
| Pre-existing tsc TS2352 ×2 | `frontend/e2e/fixtures/mockApi.ts:95,96` | readonly→unknown[] cast mismatch | Long-documented out-of-scope casts (see STATE.md prior sessions). |
