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

## Runner script

`backend/run-eval.sh` — modes: `all` (default, offline), `hello`, `layers`,
`scenarios`, `defect` (runs S1/S2 with `--runxfail` so the reproduced bug's
real failures print), `prompts` (dumps composed system prompts + dispatch
message to `prompt-dumps/` in this folder — 0 tokens), `live-s1` (REAL
Haiku S1 diagnostic with printed tool calls/output/token usage — the
prompt-iteration measuring stick, never a CI gate), `live` (full
`requires_api_key` tier). Extra args pass through to pytest.

## Prompt-surface coverage (added 2026-07-22, user-requested)

- `test_prompt_surface.py` (9 offline tests): right agents/order/tools per
  registry+manifest; `html-prototype` guardrail injected VERBATIM into both
  agents' composed prompts; each AGENT.md body's load-bearing lines present
  (read-context mandate, wiring mandate, delivery contract, validate
  checklist); prompts distinct per agent; dispatch message = instruction
  verbatim + file pointer, inline HTML slimmed away (199 chars).
- `prompt-dumps/` — human-readable ground truth of what Haiku receives
  (~10 KB system prompt per agent + the slimmed user turn).
- `test_live_s1.py` — opt-in real-Haiku S1 run (gated `requires_api_key` +
  cred-skipif; deselected from every offline mode): seeds the fixture,
  sends the production prompt surface, asserts the Save button got wired
  (inline-onclick-with-defined-fn OR script-side listener) + no static
  regressions; prints diagnostics for prompt iteration on miss.

## Open items / flagged defaults

1. **D-01**: suite placed at `backend/tests/evals/` (inside the existing
   pytest tree) — chosen default, easily moved if a standalone package is
   preferred.
2. **D-05 / S2**: while scripting S2, verify today's `static_check`
   genuinely misses it (T-015 carries the check).
3. **D-07**: exact `ctx.runner` handle for the retry decided at T-019
   after reading the registry contract.

## Phase-gate log

- [x] T-005 (Phase 0 gate): PASSED 2026-07-22 — `pytest tests/evals -m eval`
      → 4 passed (hello-world only); `pytest tests/ -m "not eval"
      --collect-only` → 2801/2805 collected, exactly the 4 eval tests
      deselected. Note: `compile_for_run` lives in
      `agents/execution_engine/engine.py:559` (not `agents/workflows/compiler.py`
      as the design draft assumed) — caught by the hello-world gate, fixed.
- [x] T-013 (Phase 1 gate): PASSED 2026-07-22 — 24 eval tests green
      (`pytest tests/evals -m eval`), 0 tokens. **Instruction propagation is
      INTACT through L1 (API seam), L2 (compile), L3 (provider
      extraction/stash), L4 (post-step threading), and L6 (fix-message
      re-injection).** The gap is isolated to L5 exactly as FINDINGS A2
      predicted: `_select_issues_to_fix` has no instruction-fulfillment
      lane — a clean no-op edit selects `[]` → `failing=False`
      (`test_l5_selection_gap.py::test_clean_noop_edit_selects_nothing__the_root_cause`).
      ⚠️ Pre-existing (NOT ours — verified by stashing our changes):
      `test_phase5_revision_validation.py` 5 failures +
      `test_revision_intelligence.py` 3 failures on this branch; the
      revision-intelligence ones pass in isolation (ordering pollution).
      T-027's "existing suites green" criterion must be judged against this
      baseline, not absolute zero.
- [x] T-018 (Phase 2 gate): PASSED 2026-07-22 — full eval suite: 28 passed
      + 2 xfailed (S1/S2, `strict=True`), deterministic across 8 consecutive
      runs, ~2.5s, 0 tokens. `-m "not eval"` still collects the same 2801
      tests. **The defect is now mechanically reproducible**: S1 (no-op
      edit) and S2 (partial fix) complete "successfully" today and fail
      exactly at the fulfillment assertions (Save handler / sidebar link
      missing in the delivered prototype.html); companion tests prove
      static_check misses both. S1/S2 scripts already carry the
      second-invocation fix turn, so the Phase-3 retry will flip them to
      strict-xpass, forcing marker removal in the fix diff (R-16).

### Harness findings surfaced while building Phase 2 (worth their own follow-ups)

1. **Loop-bound checkpointer singleton** (`app/agents/checkpointer.py:25`):
   the second `_drive()` in one pytest process dies with "Lock is bound to a
   different event loop" → every agent errors "The model rejected this
   request." This is very likely the cause of the PRE-EXISTING second-drive
   failures in `test_characterization_prototype_revision.py` and parts of
   `test_phase5_revision_validation.py` on this branch. Our suite works
   around it test-side (`_fresh_checkpointer` autouse reset in
   `test_scenarios.py`); a production-grade fix (loop-aware cache) is a
   separate small task.
2. **Concurrent multi-edit race in the tool executor**: two `edit_file`
   calls emitted in ONE model turn can lose one edit
   (concurrent read-modify-write, last write wins) — nondeterministically.
   Our scripts now emit one tool call per turn; noted because live Haiku
   also emits multi-edit turns, so this may be a REAL revision-quality
   factor worth investigating separately.
3. Scenario evals pin `render_check` to a deterministic clean result —
   real-Chromium timing was flaky enough to flip S2 across runs (D-03
   determinism rule now enforced in the driver).
- [ ] T-027 (Phase 3 gate / definition of done): _pending_

### Post-Phase-2 additions (2026-07-27, user-requested)

- **AGENT.md verbatim-injection tests** (`test_prompt_surface.py`, +2): the
  ENTIRE current AGENT.md body (post-frontmatter, byte-for-byte) must appear
  in the composed prompt for both revision agents — both via the canonical
  no-user path and via a user_id with no saved override. Discovered while
  adding: `_compose_system_prompt` supports **per-user prompt overrides**
  (KAN-76, `app/agents/prompt_overrides.py`) that REPLACE the AGENT.md body
  when `ctx.user_id` has one saved — so "current AGENT.md is what runs" holds
  only for override-less users. live-s1 uses user "eval-live" (no override).
- **Hermetic checkpointer for scenario evals**: with a Postgres DATABASE_URL
  configured but the server DOWN, the psycopg pool retried localhost:5432 for
  ~90s and S3 failed environmentally. `_fresh_checkpointer` now also patches
  `settings.DATABASE_URL` to sqlite → InMemorySaver, so scenario evals never
  touch a DB (D-03). Suite: 39 passed + 2 xfailed in ~2s, Postgres up or down.
- **Fully hermetic DB for the whole eval session**: a SEPARATE persistence
  subsystem (`run_events`, `artifact_refs`, hooks, `WorkflowMemory` — all via
  the SYNC `app.models.database.engine`/`SessionLocal`, not the LangGraph
  checkpointer) was still dialing the real Postgres URL from the dev env on
  every write and logging a connection-refused warning per call (degrading
  gracefully by design — PERSIST-02/03 best-effort — so it never failed a
  test, just cluttered output). That module builds its engine ONCE at import
  time, so a per-test `settings` patch is too late. Added a session-scoped
  autouse `_hermetic_db` fixture (`tests/evals/conftest.py`) that swaps
  `app.models.database.engine`/`SessionLocal` for an in-memory SQLite
  (`StaticPool`, schema created via `Base.metadata.create_all`) before any
  eval test runs. Verified: `./run-eval.sh` and `./run-eval.sh defect` both
  now run with zero DB warnings, identical pass/fail results, Postgres up or
  down.

## Next step

**Stopped after Phase 2 by user instruction (2026-07-22).** Phases 0–2
complete (T-001…T-018). Next up when resumed: Phase 3, starting at T-019
(registry-contract note, then the `instruction_fulfillment` capability).
Do NOT start Phase 3 without explicit go-ahead.
