# Domain 15 — backend·other

31 cards, 4 batches.

| batch | round | fix site | cards | tier | phases | model |
|---|---|---|---|---|---|---|
| B1 | 1 | backend·other (19 scattered) | ISS-096, ISS-098, ISS-101, ISS-106, ISS-118, ISS-120, ISS-130, ISS-132, ISS-156, ISS-185, ISS-357, ISS-630, ISS-631, ISS-632, ISS-633, ISS-634, ISS-635, ISS-637, ISS-638 | A′ (ISS-132 sibling of ISS-097) + C | full | **sonnet** (scattered backend, test infra, engine-adjacent) |
| B2 | 1 | `backend/tests/agents/test_phase6_frontend_consistency.py` | ISS-079, ISS-636 | A′ (ISS-636 sibling of ISS-617/FIX-415) + C | mixed | haiku |
| B3 | 2 | `backend/agents/workflows/ex_A3_divert/workflow.yaml` | ISS-173, ISS-174 | C | full | haiku |
| B4 | 4 | `backend/agents/execution_engine/engine.py` | ADR-0002, FIX-BUGFIX-NESTED-REVISION, ISS-072, ISS-090, ISS-094, ISS-125, ISS-131, ISS-402 | C | full | **sonnet** (engine.py, 8 cards, load-bearing) |

Notes:
- B1 is the "long tail" — 19 backend cards across test infra, capabilities,
  planner, checkpointer, factory, model catalog, and recently-opened test failures
  (ISS-630 through ISS-638). Many are stale-test or test-fixture drift. The high
  count is why it's sonnet — each is small but there are 19 files to touch.
- B4 `engine.py` — the CRITICAL batch. 8 cards in the busiest, most load-bearing file
  in the runtime. ADR-0002 (vocabulary rename), ISS-072 (redundant in-pass analyze gate),
  ISS-090 (hardcoded redoable=True), ISS-094 (hand-rolled double drift),
  ISS-125 (_stamp_resume_marker unbounded read + non-retrying append),
  ISS-131 (stale line-number citations in comments), ISS-402 (_inject_constitution
  full injection every run), FIX-BUGFIX-NESTED-REVISION (deferred nested-revision
  defect). **Every edit must re-run its test and confirm SC-001 + import-linter.**
- B3 workflow yaml fixes (step-id renames, planner/clarify defaults).

Collision note: engine.py OWNED here (also has cards from domain 14 as secondary
globs — that domain must not edit engine.py). test_phase6_frontend_consistency.py
owned here. Workflow yamls owned here.
Status: NOT STARTED.
