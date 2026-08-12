---
phase: quick-260812-9tq
plan: 01
status: complete
subsystem: execution-engine, agents, cost-accounting
date: 2026-08-12
branch: bugfix/spec-revision-context-loss
base-commit: d24c576a
commits: [80356fda]
ids:
  fix: FIX-230
  test: TEST-014
  issues-closed: [ISS-033]
  issues-filed: [ISS-092, ISS-093]
  issues-annotated: [ISS-034]
---

# Quick 260812-9tq — SUMMARY

**On the real prototype pipeline, a run's reported input tokens and the sum of its *visible*
per-agent tokens were identical — a difference of exactly zero — while four fix sub-agents ran
unbilled. That zero is the whole defect. It is now +240 / +100.**

## The two call-sites, as fixed

| # | site | was | now |
|---|---|---|---|
| 1 | `engine.py::_run_validation_fix_loop` | the internal drain was a bare `continue`, discarding **every** `usage` event | routes `usage` into the run's existing `aux_token_usage` via a `KernelServices` constructor sink |
| 2 | `app/agents/handoff/test_agent.py` | raw `llm.ainvoke` — **neither cached nor counted** | routed through the shared `cached_invoke`, exactly as `ComplianceAgent`; the superseded local `_extract_text` **deleted** |

Both are keyed on structure only — `event["type"] == "usage"` and the `KernelServices` handle —
never on a workflow, agent or model name (SC-001, INV-1).

## The measured delta

**Offline, exact.** Driving the real `prototype` pipeline: RED was `assert (220 - 220) == 240`.
After: **460 in / 213 out** against **220 / 113** visible → **+240 input, +100 output**
previously invisible; `estimated_cost_usd` `$0.000864 → $0.001678`.

**On live data, read-only against `dev.db`.** The shared `estimate_cost_usd` reproduces the
persisted figure for `fa66227a` to six decimals (`$2.550421`) before anything is added. The
fix-loop spend now counted — the investigation's wall-clock reconstruction, ~929,000 input
tokens — is worth **+$0.176 (+6.9%)** at that run's own 97.06% cache-read ratio, or +$1.061
(+41.6%) as an uncached upper bound. **6.9% of the run's input was invisible.**

## What the repaired INV-12 guard now pins

`test_websocket_cost_site_uses_shared_function` read `app/api/websocket.py` — a file Phase 44's
SSE cutover **deleted** — so it raised `FileNotFoundError` instead of checking, and the "both
cost sites share ONE pricing implementation" contract has been **unenforced for the persistence
site since the cutover**. It is now `test_both_cost_sites_use_the_shared_pricing_function`,
parametrized over `engine.py` (live `pipeline_complete`) and `app/api/run_commands.py` (durable
`workflow_runs.token_usage`), pinning three things:

1. the file **exists** — an explicit assertion naming the contract, so the next file move fails
   loudly instead of silently disabling the guard (the exact failure mode that happened);
2. each site **imports** `estimate_cost_usd` — the old `"estimate_cost_usd" in src` substring
   check was satisfiable by a comment;
3. neither site carries a per-token rate literal.

**Mutation-tested, not assumed:** all three arms were made to fail on purpose (missing file;
a site that only mentions the function; a site that imports it but hand-rolls a rate).

## Baselines, against `d24c576a`

| check | before | after |
|---|---|---|
| 5 characterization goldens | 10 passed / 0 failed | **10 passed / 0 failed** — no golden regenerated |
| `lint-imports` | 4 kept / 0 broken | **4 kept / 0 broken** |
| 8 protected suites | 112 passed / 0 failed | **112 passed / 0 failed** (`test_restart_resume.py` 60/0) |
| `test_model_pricing.py` | 26 passed / **1 failed** (the dead guard) | **27 passed / 0 failed** |
| fix-loop + cost + KernelServices sweep | — | **157 passed / 0 failed** |

**The fix loop DID have to be re-run, not reasoned about.** The prototype goldens fire it four
times (read out of the engine's own INFO log), so their run totals genuinely move 220 → 460.
They stay golden-neutral only because `total_input_tokens`/`total_output_tokens`/`total_tokens`
are sentinel-normalized (`_VOLATILE_REQUIRED_KEYS`) and `estimated_cost_usd` + the cache keys are
stripped (`_VOLATILE_STRIP_KEYS`). Any future change to run-token accounting must re-run them.

## Three findings that changed the shape of the work

**1. The ISS-033 row was stale by a month.** Phase 43-04 shipped `cached_invoke.py` (`0aa2072c`)
and routed four sites (`8518f29b`) on 2026-07-15; the aux fold is *live-proven* in `dev.db`. The
row still read `OPEN (deferred)`, and the card store repeated it. Corrected in place, and the
ISS-033/034 cards **force-refreshed** so the drift does not survive this task.

**2. The 43-04 miss has a procedural cause.** Its own wording, "handoff Test(classifier)",
mistook `classifier.py` (the coding-vs-test router) for `test_agent.py` (the real Test agent).
A grep for the raw `.ainvoke(` call-site would have caught it; a grep for "Test agent" did not.
**Route by call-site, not by name.** The true direct-call set is **9 sites, not the 3 filed**.

**3. `agents_completed == 6` while `agents_total == 5` is CORRECT — and was nearly mis-pinned.**
The first draft of the guard asserted equality and failed at HEAD. `agents_completed` counts
`_run_agent` *invocations*: the prototype's 5 steps plus the build agent's second task. The test
now pins the literal 6, which is what makes a regression (6 → 10, one per fix attempt) loud.

## The shortcut rejected, recorded so it is not re-proposed

*"Estimate the fix-loop by multiplying the task agent's tokens by a fudge factor"* — and its
sibling, *"estimate the Concierge from `len(chat_reply)`."* Both put a fabricated number where a
real one is one event-branch away, and both would make ISS-034's "saved $Y" a fiction built on a
fiction. **If a token was not observed, it must be reported as unmeasured, never invented.**

## Filed, not fixed

- **ISS-092** (major) — part B. The Concierge discards `usage` **and** its input is unbounded:
  `authz.py:315` has no LIMIT and no type filter, so one chat question can be handed up to
  **2.3M tokens** of run events. Plus the handoff pipeline's total absence of a cost surface.
  Not bundled because `converse` runs from a REST handler outside `execute()`, often after the
  run is terminal — it needs a product decision (does chat spend belong in the run's headline
  cost?), not plumbing.
- **ISS-093** (minor) — 3 stale clarify-round tests in `tests/unit/test_execution_engine.py`
  expecting `clarification_limit_reached`. **Verified pre-existing with a SHA:** the identical 3
  fail at `d24c576a` in a detached worktree containing none of this change.

## ISS-034 is blocked, and its spec is wrong as written

Left OPEN, with the dependency recorded on its row. Beyond the token-base dependency: computed
across every run in `dev.db`, **on 7 of 9 runs the cache "saving" is NEGATIVE** (−5.0% to −8.9%)
— single-turn text-only agents write a cache entry nothing ever reads back, and `cache_write_5m`
is 1.25× the input rate. A naive "saved $Y (Z%)" would render a **wrong-signed number**; the FE
contract must be a **signed** delta. Falls out for free: prompt caching is a measured net cost
*increase* on single-turn workflows, so the cache flag arguably belongs per-step, not global.

## Not live-proven, deliberately

No run was launched, resumed or gate-approved: one build is 5–21M tokens of the owner's money.
Every proof above is offline or a read-only query against `backend/dev.db`.
