# Status

**Phase**: planning complete (v2, eval-first). **No code touched yet.**

## TL;DR of the investigation (unchanged from v1)

- **Revisions "don't fix it"**: both validation layers check *structural
  health* only; nothing ever re-checks the post-edit file against the
  user's instruction. A structurally clean no-op edit passes every gate.
  (FINDINGS A1–A7 — root cause A2.)
- **No thinking visible**: broken in 4 places (config off + runner drops
  thinking blocks + no thinking event type + engine never emits
  `agent_thinking`). Flipping the config alone changes nothing visible.
  (FINDINGS B1–B5.) **PARKED — last phase, by decision 2026-07-22.**

## Plan v2 (eval-first) — decided 2026-07-22

The fix may not land until an eval suite first *reproduces* the defect:

- Phase 0 — scaffold `backend/tests/evals/` + hello-world harness gate.
- Phase 1 — layered unit tests along the issue surface (API → compile →
  context seed → post-step → selection semantics → LLM boundary).
- Phase 2 — S1/S2 defect evals as `xfail(strict=True)` (reproducibility),
  S3 happy-path control.
- Phase 3 — instruction-fulfillment fix; done only when the xfails flip
  and are removed, goldens byte-identical (R-22).
- Phase 4 — parked thinking work.

Token budget: default suite is 100% scripted-model offline (0 tokens);
one opt-in live smoke test behind `requires_api_key`, Haiku, tiny fixture.

## Documents in this folder

- `PROBLEM_STATEMENT.md` — expanded problem statement.
- `FINDINGS.md` — file/line-cited root-cause findings (A = fix gap,
  B = thinking).
- `PLAN.md` — v2 phased plan (eval-first; thinking parked as Phase 4).
- `requirements.md` — R-01…R-24, atomic + testable.
- `design.md` — D-01…D-09 (suite location, folder tree, zero-token
  policy, markers/xfail-strict, scenario matrix, layer seams, fix
  architecture, golden safety, non-goals).
- `tasks.md` — T-001…T-029, phase-gated.

## Open items / flagged defaults

1. **D-01**: suite placed at `backend/tests/evals/` (inside the existing
   pytest tree) — chosen default, easily moved if a standalone package is
   preferred.
2. **D-05 / S2**: while scripting S2, verify today's `static_check`
   genuinely misses it (T-015 carries the check).
3. **D-07**: exact `ctx.runner` handle for the retry decided at T-019
   after reading the registry contract.

## Phase-gate log

- [ ] T-005 (Phase 0 gate): _pending_
- [ ] T-013 (Phase 1 gate): _pending_
- [ ] T-018 (Phase 2 gate): _pending_
- [ ] T-027 (Phase 3 gate / definition of done): _pending_

## Next step

Start T-001 (scaffold) on approval.
