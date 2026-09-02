# STATE — bug-fix workflow progress

Durable record of what has run. Re-read this on resume rather than trusting chat
memory. Updated by the closer after every domain run.

| # | domain | cards | status | closed | reopened | escalated | report |
|---|--------|-------|--------|--------|----------|-----------|--------|
| 1 | warmup | 4 | DONE | 2 | 0 | 2 | [20260831-domain-01-warmup.md](reports/20260831-domain-01-warmup.md) |
| 2 | frontend·settings | 4 | DONE | 3+1already | 0 | 0 | [20260831-domain-02-frontend-settings.md](reports/20260831-domain-02-frontend-settings.md) |
| 3 | frontend·lib | 4 | DONE | 3 (ISS-386 fixed; ISS-413,ISS-486 already-fixed) | 0 | 1 (BUG-013 Part A cross-domain) | [20260901-domain-03-frontend-lib.md](reports/20260901-1100-domain-03-frontend-lib.md) |
| 4 | tests·integration | 5 | DONE | ISS-625,ISS-626,ISS-627 closed; ISS-628 partial | 0 | ISS-623(escalated),ISS-628-workspace(escalated) | [20260901-1200-domain-04-tests-integration.md](reports/20260901-1200-domain-04-tests-integration.md) |
| 5 | frontend·preview | 7 | DONE | ISS-433,ISS-596,ISS-251,ISS-388,ISS-389,ISS-599,ISS-609 (7 closed: FIX-446–450; ISS-388/389 already fixed by FIX-358) | 0 | 0 | [20260901-1545-domain-05-frontend-preview.md](reports/20260901-1545-domain-05-frontend-preview.md) |
| 6 | frontend·components | 10 | DONE | ISS-409,ISS-481,ISS-600,ISS-117,ISS-387 closed (FIX-451–455); ISS-073,ISS-114,ISS-216 already-fixed | 0 | ISS-112 (no FE data source), ISS-434 (needs PipelineRunState.deliverableMimetype + useWorkflow.ts) | [20260901-1630-domain-06-frontend-components.md](reports/20260901-1630-domain-06-frontend-components.md) |
| 7 | frontend·library | 11 | DONE | ISS-330,ISS-336,ISS-605 closed (FIX-456–458); ISS-318,ISS-335,ISS-441,ISS-591 already-fixed | 0 | BUG-073(escalated-prior), ISS-392(escalated-prior), ISS-378(domain-12) | [20260901-1900-domain-07-frontend-library.md](reports/20260901-1900-domain-07-frontend-library.md) |
| 8 | frontend·routes | 13 | DONE | ISS-342,ISS-602,ISS-492,ISS-350,ISS-624,ISS-376,ISS-405,ISS-415 closed (FIX-459–465); ISS-352,ISS-407,ISS-442 already-fixed | 0 | ISS-195 (inferred-wrong-root/already-fixed), ISS-579 (cross-domain: WorkflowView.tsx) | [20260901-2100-domain-08-frontend-routes.md](reports/20260901-2100-domain-08-frontend-routes.md) |
| 9 | frontend·history | 13 | DONE | ISS-198,ISS-207,ISS-208,ISS-209,ISS-213,ISS-414 closed (FIX-466–467); ISS-219 partial | 0 | ISS-325 (test premise broke), ISS-629 (spec contradiction) | [20260902-1100-domain-09-frontend-history.md](reports/20260902-1100-domain-09-frontend-history.md) |
| 10 | frontend·composer | 14 | DONE | ISS-333,ISS-353,ISS-431,ISS-382,ISS-489,ISS-178 closed (FIX-468–473); ISS-340,ISS-192 already-fixed | 0 | ISS-183 (design decision), ISS-223 (ADR-0027 ruling), ISS-334/410/604 (page.tsx domain 8), ISS-393 (AgentsPopup domain 7) | [20260902-1200-domain-10-frontend-composer.md](reports/20260902-1200-domain-10-frontend-composer.md) |
| 11 | frontend·hooks | 16 | DONE | ISS-108,ISS-110,ISS-141 closed (FIX-474–475); ISS-417,ISS-438,ISS-439,ISS-440 already-fixed | 0 | ISS-109,ISS-115,ISS-116,ISS-142,BUG-014-B,BUG-018,BUG-021,ISS-111,FIX-BUGFIX-SPEC-REVISION (9 escalated) | [20260902-1300-domain-11-frontend-hooks.md](reports/20260902-1300-domain-11-frontend-hooks.md) |
| 12 | frontend·workflow | 22 | NOT STARTED | – | – | – | – |
| 13 | frontend·layout | 23 | NOT STARTED | – | – | – | – |
| 14 | backend·api | 29 | PAUSED (15/29 moved: 1 CLOSED, 3 FIXED, 7 TESTED, 4 ESCALATED; 14 still ANALYZED) | 1 | 0 | 4 | 20260831T180611Z-all.md |
| 15 | backend·other | 31 | DONE (all 31 cards resolved: CLOSED 18, ESCALATED 13) | 18 | 0 | 13 | 20260831-173432-all.md |
| T | triage (no fix site) | 21 | NOT STARTED | – | – | – | – |

Status values: NOT STARTED · IN PROGRESS (round N) · PAUSED · DONE · BLOCKED · PARTIAL.

- Run 2026-09-02T13:00:00Z: **Domain 11 (frontend·hooks) DONE** — 3 FIXED (ISS-108/110 → FIX-475; ISS-141 → FIX-474), 4 ALREADY_FIXED (ISS-417/438/439/440 confirmed by FIX-373/FIX-379), 9 ESCALATED (ISS-109/115/116/142 design decisions; BUG-014-B/ISS-142 cross-domain SSE; BUG-018/BUG-021 cross-domain api.ts/page.tsx; ISS-111 design decision; FIX-BUGFIX-SPEC-REVISION backend engine). tsc clean (0 errors), vitest 86/86 green. Dedup regenerated: 136 → 131 units. See `reports/20260902-1300-domain-11-frontend-hooks.md`.

- Run 2026-09-02T12:00:00Z: **Domain 10 (frontend·composer) DONE** — 6 FIXED (ISS-333/353/431/382/489/178 → FIX-468–473), 2 ALREADY_FIXED (ISS-340/192 confirmed pre-fixed), 6 ESCALATED (ISS-183 design decision; ISS-223 ADR-0027 backend ruling; ISS-334/410 page.tsx domain 8; ISS-393 AgentsPopup domain 7; ISS-604 CanvasView/page.tsx domain 8/12). tsc clean (0 errors), vitest 83/83 green. Dedup regenerated: 139 → 136 units. See `reports/20260902-1200-domain-10-frontend-composer.md`.

- Run 2026-09-02T11:00:00Z: **Domain 9 (frontend·history) DONE** — 6 FIXED (ISS-198/207/208/209/213 → FIX-466; ISS-414 → FIX-467), 1 PARTIAL (ISS-219 chip units remain), 2 ESCALATED (ISS-325 test premise broke; ISS-629 spec contradiction), 4 NO CHANGE (secondary globs: ISS-077/113/145/412). tsc clean (0 errors), vitest 13/13 green. Dedup regenerated: 144 → 139 units. See `reports/20260902-1100-domain-09-frontend-history.md`.

- Run 2026-09-01T21:00:00Z: **Domain 8 (frontend·routes) DONE** — 8 FIXED (ISS-342/602/492/350/624/376/405/415 → FIX-459–465), 3 ALREADY_FIXED (ISS-352/407/442), 2 ESCALATED (ISS-195 inferred-wrong-root; ISS-579 cross-domain WorkflowView.tsx). tsc clean (0 errors), vitest 77/77 green. Dedup regenerated: 163 → 144 units. See `reports/20260901-2100-domain-08-frontend-routes.md`.

 — 3 FIXED (ISS-330/336/605 → FIX-456/457/458), 4 ALREADY_FIXED (ISS-318/335/441/591), 3 ESCALATED (BUG-073/ISS-392 prior escalation unchanged; ISS-378 → domain 12). tsc clean (0 errors), vitest 10/10 green. Dedup regenerated: 171 → 150 units. See `reports/20260901-1900-domain-07-frontend-library.md`.

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
- Run 2026-09-01T15:45:00Z: **Domain 5 (frontend·preview) DONE** — 7 CLOSED (FIX-446–450).
  ISS-388/389 already fixed by FIX-358 (confirmed by degraded test suite 11/11). ISS-251 inline
  deliverable logic collapsed to resolveRunDeliverable. ISS-599 clipboard hook. ISS-609 AuditTab
  workflowRunId → activeRunId. ISS-433 flex-wrap. ISS-596 test disambiguation. e2e test for ISS-609
  needs live servers. ISS-596 it.fails marker needs verifier removal.
  See `reports/20260901-1545-domain-05-frontend-preview.md`.
- Run 2026-09-01T16:30:00Z: **Domain 6 (frontend·components) DONE** — 5 CLOSED (FIX-451–455),
  3 ALREADY_FIXED (ISS-073/114/216), 2 ESCALATED (ISS-112 no FE data source; ISS-434 needs
  PipelineRunState.deliverableMimetype + useWorkflow.ts). tsc clean; 11 unit tests passing.
  Backlog regenerated: 178 open cards → 156 work units.
  See `reports/20260901-1630-domain-06-frontend-components.md`.
