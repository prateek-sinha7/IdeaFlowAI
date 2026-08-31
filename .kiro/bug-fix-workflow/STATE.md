# STATE — bug-fix workflow progress

Durable record of what has run. Re-read this on resume rather than trusting chat
memory. Updated by the closer after every domain run.

| # | domain | cards | status | closed | reopened | escalated | report |
|---|--------|-------|--------|--------|----------|-----------|--------|
| 1 | warmup | 4 | IN PROGRESS (BUG-031 done, in-session) | 1 | 0 | 0 | smoke test 2026-08-31 |
| 2 | frontend·settings | 4 | NOT STARTED | – | – | – | – |
| 3 | frontend·lib | 4 | NOT STARTED | – | – | – | – |
| 4 | tests·integration | 5 | NOT STARTED | – | – | – | – |
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
- Run 2026-08-31T15:48:02Z (batch B4 of backend·other) reached COMPLETE for its own
  scope: ISS-131, ISS-402, ISS-090, ISS-125 and FIX-BUGFIX-NESTED-REVISION all
  closed; ISS-072 was ESCALATED pending a re-run of its manual repro. See
  `bug-hunter/reports/20260831T154802Z-all.md`.
- Run 2026-08-31T17:34:32Z picked up the remaining 23 ANALYZED cards (B1-B3 plus a
  new B5 batch: ISS-630..638/079/636) and ran them all the way through
  validate→analyze→test→fix→verify. **Domain 15 (backend·other) is now DONE**:
  all 31 cards are resolved to a terminal state — 18 CLOSED, 13 ESCALATED, 0 left
  ANALYZED or otherwise pending. ISS-072 (prior batch) is also now closed. Register
  and cards checked and agree throughout (every CLOSED card is `status: resolved`,
  every ESCALATED card is `status: open`, every FIX↔ISS link is reciprocal) — no
  disagreements found this run. 3 new cards were spun off mid-fix and are NOT yet
  in the register: ISS-640 (ISS-120's deferred middleware half), ISS-641
  (unreachable shutdown-budget dead code found fixing ISS-106), ISS-642 (2 stale
  ISS-633 test witnesses left xfailed rather than bent to pass) — these need to be
  added to the register on a future pass before they can be worked.
  Needs a human ruling before further automated work: **ISS-132**, **ISS-630**,
  **ISS-632**, **ISS-634**, **ISS-638** (product/design decisions, detailed in the
  report), plus carried-over **ADR-0002**, **ISS-094**. Propose closing as
  already-fixed (not reproducible today, re-check evidence on each card): ISS-096,
  ISS-130, ISS-156, ISS-079, ISS-173, ISS-174. See
  `bug-hunter/reports/20260831-173432-all.md` for the full per-bug breakdown.
  Resume: domain 15 has no further work queued; move to another domain (e.g. #14
  backend·api) or wait for a human ruling on the escalated items above.
- Run 2026-08-31T18:06:11Z worked domain 14 (backend·api), batch size 3, phases
  validate→analyze→test→fix→verify, and **PAUSED on request** partway through (15 of
  29 cards moved). B1 (ISS-134/182/419/470/471): ISS-182 CLOSED (FIX-438), ISS-470
  FIXED (FIX-439), ISS-471 FIXED (FIX-441), ISS-419 ESCALATED (locked-constraint
  conflict, needs a design ruling), ISS-134 ESCALATED/blocked (env — no
  reproducible defect until the future multi-instance migration exists). B2
  (10 of 17 cards): BUG-004 FIXED (already shipped, FIX-440 backfilled), BUG-017/
  ISS-100/104/127/128/154 TESTED (red tests written, not yet fixed — ISS-100/104/
  127/128/154 fixes still pending), BUG-017/144 TESTED-as-already-fixed (existing
  coverage found green, no new test needed), ISS-119/133 ESCALATED as
  already-resolved/duplicate (proposed WONTFIX candidates, mirrored to
  `bug-hunter/wontfix-candidates.md`). Register and cards checked and agree
  throughout — no disagreements found. One data-quality note: BUG-004's register
  row still names `run_commands.py` as its fix site; the real fix site is
  `run_stream.py` + `database.py` (flagged in the register's own Notes, not
  restructured). **Still ANALYZED, queued for next run:** ISS-161, ISS-398,
  ISS-418, ISS-422, ISS-435, ISS-436, ISS-437 (rest of B2); ISS-180, ISS-181,
  ISS-263, ISS-381 (B3); BUG-015-016, ISS-105, ISS-137 (B4). Also still pending:
  fix phase for ISS-100/104/127/128/154 (tested but not fixed) and verify phase
  for ISS-470/471 (fixed but not verified). Needs a human ruling before further
  automated work: **ISS-134** (migration-tracking reclassification?), **ISS-419**
  (ADR-0013/FIX-377 conflict — 3 options on the card), **ISS-119**, **ISS-133**
  (propose closing as already-resolved/duplicate). See
  `bug-hunter/reports/20260831T180611Z-all.md` for the full per-bug breakdown.
  **Resume: delete `bug-hunter/PAUSE` and re-run the same command** — the
  scheduler picks up domain 14's remaining ANALYZED cards from where this run
  left off.
