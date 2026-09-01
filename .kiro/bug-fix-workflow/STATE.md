# STATE — bug-fix workflow progress

Durable record of what has run. Re-read this on resume rather than trusting chat
memory. Updated by the closer after every domain run.

| # | domain | cards | status | closed | reopened | escalated | report |
|---|--------|-------|--------|--------|----------|-----------|--------|
| 1 | warmup | 4 | DONE | 2 | 0 | 2 | [20260831-domain-01-warmup.md](reports/20260831-domain-01-warmup.md) |
| 2 | frontend·settings | 4 | DONE | 3+1already | 0 | 0 | [20260831-domain-02-frontend-settings.md](reports/20260831-domain-02-frontend-settings.md) |
| 3 | frontend·lib | 4 | DONE | 3 (ISS-386 fixed; ISS-413,ISS-486 already-fixed) | 0 | 1 (BUG-013 Part A cross-domain) | [20260901-domain-03-frontend-lib.md](reports/20260901-1100-domain-03-frontend-lib.md) |
| 4 | tests·integration | 5 | DONE | ISS-625,ISS-626,ISS-627 closed; ISS-628 partial | 0 | ISS-623(escalated),ISS-628-workspace(escalated) | [20260901-1200-domain-04-tests-integration.md](reports/20260901-1200-domain-04-tests-integration.md) |
| 5 | frontend·preview | 7 | NOT STARTED | – | – | – | – |
| 6 | frontend·components | 10 | NOT STARTED | – | – | – | – |
| 7 | frontend·library | 11 | NOT STARTED | – | – | – | – |
| 8 | frontend·routes | 13 | NOT STARTED | – | – | – | – |
| 9 | frontend·history | 13 | NOT STARTED | – | – | – | – |
| 10 | frontend·composer | 14 | NOT STARTED | – | – | – | – |
| 11 | frontend·hooks | 16 | NOT STARTED | – | – | – | – |
| 12 | frontend·workflow | 22 | NOT STARTED | – | – | – | – |
| 13 | frontend·layout | 23 | NOT STARTED | – | – | – | – |
| 14 | backend·api | 29 | PAUSED (15/29 moved: 1 CLOSED, 3 FIXED, 7 TESTED, 4 ESCALATED; 14 still ANALYZED) | 1 | 0 | 4 | 20260831T180611Z-all.md |
| 15 | backend·other | 31 | DONE (all 31 cards resolved: CLOSED 18, ESCALATED 13) | 18 | 0 | 13 | 20260831-173432-all.md |
| T | triage (no fix site) | 21 | NOT STARTED | – | – | – | – |

Status values: NOT STARTED · IN PROGRESS (round N) · PAUSED · DONE · BLOCKED · PARTIAL.

## Global notes
- Model policy: PLAN.md tiered table. Haiku default; Sonnet for analyze(non-trivial),
  verify, backend·api/other, engine.py/run_commands.py, any 3+-file fix.
- Git: operator owns all commits. Closer never commits — it lists "Ready to commit".
- Restart: fixes to yaml/AGENT.md/env/deps need a manual backend restart before verify.
- **Pre-existing Windows encoding issue:** `build_context.py` fails with `UnicodeDecodeError: 'charmap' cp1252 0x90` on one MOD-*.md card. `CONTEXT.md` is stale until fixed. Index and dedup run fine.
- **Servers:** backend `.venv` is at `backend/.venv/Scripts/`; use absolute paths. Frontend: `cmd /c "npm run dev"` from `frontend/`. Both confirmed up on 2026-08-31.
- Run 2026-08-31T15:48:02Z (batch B4 of backend·other) reached COMPLETE for its own
  scope: ISS-131, ISS-402, ISS-090, ISS-125 and FIX-BUGFIX-NESTED-REVISION all
  closed; ISS-072 was ESCALATED pending a re-run of its manual repro. See
  `bug-hunter/reports/20260831T154802Z-all.md`.
- Run 2026-08-31T17:34:32Z: **Domain 15 (backend·other) DONE** — 18 CLOSED,
  13 ESCALATED. 3 new cards spun off (ISS-640/641/642). Needs human ruling on
  ISS-132/630/632/634/638 + ADR-0002/ISS-094. See `bug-hunter/reports/20260831-173432-all.md`.
- Run 2026-08-31T18:06:11Z: Domain 14 (backend·api) **PAUSED** at 15/29 cards.
  ISS-182 CLOSED (FIX-438), ISS-470/471 FIXED (FIX-439/441), ISS-419/134 ESCALATED.
  Still pending: fix for ISS-100/104/127/128/154; verify for ISS-470/471;
  ISS-161/398/418/422/435/436/437 (B2 rest); ISS-180/181/263/381 (B3); BUG-015-016/ISS-105/137 (B4).
  See `bug-hunter/reports/20260831T180611Z-all.md`.
