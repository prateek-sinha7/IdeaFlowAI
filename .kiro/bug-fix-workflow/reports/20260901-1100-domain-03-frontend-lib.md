# Domain 03 — frontend·lib — Run Report

**Date:** 2026-09-01  
**Operator:** Kiro (autonomous session)  
**Domain:** 03 — frontend·lib  
**Batches:** B1 (`frontend/src/lib/routes.ts`), B2 (`frontend/src/lib/api.ts`)  
**Cards in scope:** ISS-386, ISS-413, ISS-486, BUG-013-GROUNDED-CONTEXT  

---

## Cards Closed

| card | fix card | test(s) | what changed |
|---|---|---|---|
| [ISS-386](../../.knowledge/cards/20260828-2228-ISS-386.md) | [FIX-422](../../.knowledge/cards/20260901-1100-FIX-422.md) | `frontend/src/lib/routes.test.ts` | `runStepsAgent` gained `version?` param — builder/parser asymmetry closed |
| [ISS-413](../../.knowledge/cards/20260828-2357-ISS-413.md) | [FIX-406](../../.knowledge/cards/20260829-0431-FIX-406.md) *(already landed)* | `useRunChat.chatTimestamp.test.ts`, `test_runs_api_events.py`, `test_sse_stream.py` | `created_at` already in `RunEventRow` + `getRunEvents` mapper via FIX-406; ALREADY_FIXED fast-path |
| [ISS-486](../../.knowledge/cards/20260828-2335-ISS-486.md) | [FIX-384](../../.knowledge/cards/20260829-0232-FIX-384.md) *(already landed)* | `api.sessionExpiryRedirect.test.ts` | `handleSessionExpiry` already routes through `buildQueryString`/`URLSearchParams` via FIX-384; ALREADY_FIXED fast-path |

**Total closed: 3**

---

## Cards Escalated / Left Open

| card | reason | action needed |
|---|---|---|
| BUG-013-GROUNDED-CONTEXT | Part A (RunConnectionProvider.tsx) is a **cross-domain collision** — the fix site belongs to another domain's primary file. Part B (api.ts `fetchWithTimeout` / AbortController) was ALREADY_FIXED. | Part A needs a domain that owns `frontend/src/providers/RunConnectionProvider.tsx`. The card stays `status: open`. |

---

## Cards Reopened

*None.*

---

## Cards Created This Run

| id | type | what |
|---|---|---|
| FIX-422 | fix | `routes.runStepsAgent` version param — closes ISS-386 |

---

## What Was Rebuilt

- **Stage 1 (index):** ✅ completed — 1098 cards indexed, `INDEX.md` and `state.yaml` updated
- **Stage 2 (context):** ❌ pre-existing failure — `UnicodeDecodeError: 'charmap' cp1252 0x90` in `build_context.py` on a MOD-*.md architecture card. Not retried per DISPATCH.md. `CONTEXT.md` remains stale until the encoding is fixed.
- **Stage 3 (validate_links):** ✅ completed — 9 broken links, all pre-existing venv-path artifacts in `MOD-backend.md`. None are ours.
- **Dedup (OPEN-ISSUES-DEDUP.md):** ✅ regenerated — **218 open, 188 closed**. ISS-386, ISS-413, ISS-486 now in the `✅ Closed` section, not the open backlog.

---

## Test Results

| test file | outcome | notes |
|---|---|---|
| `frontend/src/lib/routes.test.ts` | 60/60 passed | +1 new ISS-386 round-trip case |
| `frontend/src/lib/api.sessionExpiryRedirect.test.ts` | 1/1 passed | ISS-486 / FIX-384 guard |
| `frontend/src/lib/api.test.ts` | 2/2 passed | api client baseline |
| `frontend/src/hooks/useRunChat.chatTimestamp.test.ts` | 3/3 passed | ISS-413 / FIX-406 guard |
| `backend/tests/unit/test_runs_api_events.py` | 7/7 passed | ISS-413 / FIX-406 backend guard |
| `npx tsc --noEmit` | EXIT_CODE=0 | No type errors in changed files |

---

## Integrity

- FIX-422 ID unique: ✅ (one file, one INDEX entry)
- ISS-386 → FIX-422 two-way link: ✅ (`Referenced by` in ISS-386, `Depends on` in FIX-422)
- All closed card chains: ✅ (ISS resolved ↔ FIX card exists ↔ test files real ↔ tests green)
- No `xfail` markers created (no new xfail tests were written — pure code fix + existing test extension)

---

## Ready to Commit

**Suggested commit message (ISS-386):**
```
fix(routes): runStepsAgent gains optional version param — closes ISS-386

routes.runStepsAgent(id, agentId, version?) now produces the version-pinned
/runs/{id}/versions/{v}/steps/{agentId} form, matching every sibling builder.
Adds round-trip test case to routes.test.ts.
```

**Staged files (see gitadd below):**
- `frontend/src/lib/routes.ts`
- `frontend/src/lib/routes.test.ts`
- `.knowledge/cards/20260828-2228-ISS-386.md`
- `.knowledge/cards/20260828-2357-ISS-413.md`
- `.knowledge/cards/20260828-2335-ISS-486.md`
- `.knowledge/cards/20260901-1100-FIX-422.md`
- `.knowledge/INDEX.md`
- `.knowledge/state.yaml`
- `bug-hunter/OPEN-ISSUES-DEDUP.md`
- `.kiro/bug-fix-workflow/STATE.md`
- `.kiro/bug-fix-workflow/reports/20260901-1100-domain-03-frontend-lib.md`

**Note:** `BUG-013-GROUNDED-CONTEXT` card is NOT staged — it stays open with no status change (Part A not fixed in this domain). Backend `test_runs_api_events.py` is not staged here (was already committed with FIX-406; re-runs confirm green, no change).

---

## Pre-existing Issues Found (not fixed)

1. `build_context.py` stage 2 cp1252 encoding failure — pre-existing, documented in DISPATCH.md
2. `MOD-backend.md` 9 broken venv-path links — pre-existing, not from this domain

---

## Needs a Human

- **BUG-013 Part A (RunConnectionProvider.tsx):** Fix requires editing `frontend/src/providers/RunConnectionProvider.tsx`, which is the primary fix site of a different domain. Assign to whichever domain owns that file (likely `frontend·components` or `frontend·hooks` area). The Part B timeout fix is already in `api.ts` — Part A (`AUTO_STREAM_STATUSES` split + `focusedRunId` sticky ref) is what remains.
- **No wontfix candidates** — all cards either closed, escalated with clear reason, or left open for Part A.
- **Restart needed:** No — domain 3 is frontend-only. No backend restart required.
