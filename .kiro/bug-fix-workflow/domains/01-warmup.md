# Domain 1 — warmup (unclassified + docs·planning + backend·engine)

4 cards, 3 batches, all round 1. Smallest domain — proves the loop end to end.

| card | status | batch | round | fix site | tier | phases | model |
|---|---|---|---|---|---|---|---|
| ISS-187 | ANALYZED | B1 | 1 | `backend/agents/execution_engine/engine.py` (ISS-187 only) | C | full | **sonnet** (engine.py) |
| ISS-076 | CLOSED (won't-fix — stale figure is in frozen .planning/ archive; live reference frontend/e2e/README.md updated separately) | B2 | 1 | docs·planning | C | validate→fix→verify (docs) | haiku |
| ISS-095 | CLOSED (already-fixed — all 3 gate-streaming tests pass as of 2026-08-31; fixed by commit da172056) | B2 | 1 | docs·planning | C | validate→fix→verify (docs) | haiku |
| BUG-031 | CLOSED (already-fixed — stages: [manual] restored in commit 0228bf196, 2026-08-29; verified live at .pre-commit-config.yaml:185) | B3 | 1 | unclassified (BUG-031) | C | full | haiku |

Notes:
- ISS-187: spec-014 ex_A* gate fixtures / entitlements mismatch. Fix site is
  actually `backend/app/core/entitlements.py` + `frontend/src/lib/entitlements.ts`
  per the card — confirm at validate; if it edits entitlements not engine.py, it is
  a 2-file fix (still sonnet). Escalate if it needs an engine.py edit under the
  name-free-kernel invariant.
- ISS-076 / ISS-095: stale register/doc figures (`.planning/*`) — but PLAN.md and
  the fixer forbid editing `.planning/` (frozen archive). These are likely
  **stale-doc** cards the analyzer should re-scope or mark for the operator, NOT
  edit in place. Treat as escalate-if-frozen.
- BUG-031: pre-commit knowledge-hook clobber (`.pre-commit-config.yaml` +
  `tools/knowledge/rebuild_knowledge.py`). Real fix. Config change → operator
  should review carefully (touches commit machinery).

Collision: none — three disjoint fix sites.
Status: the `status` column above is authoritative — it is what the line
reads and writes. A whole-file status could only drift from it.
