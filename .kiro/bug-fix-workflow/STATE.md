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
| 14 | backend·api | 29 | NOT STARTED | – | – | – | – |
| 15 | backend·other | 31 | NOT STARTED | – | – | – | – |
| T | triage (no fix site) | 21 | NOT STARTED | – | – | – | – |

Status values: NOT STARTED · IN PROGRESS (round N) · DONE · BLOCKED · PARTIAL.

## Global notes
- Model policy: PLAN.md tiered table. Haiku default; Sonnet for analyze(non-trivial),
  verify, backend·api/other, engine.py/run_commands.py, any 3+-file fix.
- Git: operator owns all commits. Closer never commits — it lists "Ready to commit".
- Restart: fixes to yaml/AGENT.md/env/deps need a manual backend restart before verify.
