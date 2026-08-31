# DISPATCH — how Kiro orchestrates a domain run

Kiro plays the `0-orchestrator` role. Unlike the Claude Code version (a separate
Opus agent), here Kiro IS the session and dispatches workers with `spawn_run`.
Kiro keeps its own context thin: it never validates/analyzes/fixes/verifies in the
main session — it dispatches sub-agents and consumes only their ~15-line return
contracts.

## On "run domain X"

1. **Read state first.** Read `.kiro/bug-fix-workflow/STATE.md` and the domain's
   run-doc `domains/NN-<name>.md`. If resuming, the run-doc's per-batch status
   says what is already done — skip it (idempotent; the register/cards are the
   real state).
2. **Preconditions.** Confirm the domain touches no file another *live* session is
   editing. Note whether app servers need to be up (only VERIFY on browser-
   observable cards needs `:3000`/`:8000`; pure unit/tsc verifies do not).
3. **Walk rounds in order.** For each round in the run-doc:
   - Collect the batches in that round. They write disjoint files → dispatch them
     as **parallel `spawn_run` tasks** (respect the host: on tight memory, cap the
     wave — see Resource note).
   - Each batch task is seeded with: the relevant agent role file(s) from
     `agents/`, the batch's card ids + fix site, the model tag from the run-doc,
     and the standing boundaries.
   - **End the turn after dispatching.** Wait for `[Subagent completion event]`s.
     Do NOT do the work in the main session.
4. **Between rounds:** read each worker's return contract, update the run-doc batch
   status + `STATE.md`. If a backend `*.py`-adjacent non-`.py` file changed
   (yaml/AGENT.md/env), tell the operator to restart before the VERIFY of the next
   round trusts a green test.
5. **After the last round:** dispatch ONE `7-closer` (Haiku) for the domain —
   rebuild stale knowledge artifacts, **regenerate `bug-hunter/OPEN-ISSUES-DEDUP.md`
   via `python3 bug-hunter/tools/dedup.py`** (so closed cards drop off the backlog),
   integrity sweep, write `reports/<UTC>-<domain>.md`. **Closer does NOT commit
   here** (operator owns git).
6. **Report** to the operator in a few lines: cards closed, reopened, escalated,
   what needs a human, what needs a restart/commit. Then STOP — do not roll into
   the next domain unless told.

## Phase routing per card (from the run-doc's tier column)

| tier | route |
|---|---|
| A′ (root fixed) | FIX(replicate FIX-NNN) → VERIFY. Skip validate/analyze. |
| A / B / C (open) | VALIDATE → ANALYZE → TEST → FIX → VERIFY |
| stale-test-only | (validate trivial) → FIX(test) → VERIFY. Fixer edits the TEST, not app — allowed only because the *card* says the test is wrong. |
| no fix site | not scheduled → `TRIAGE.md` |

## spawn_run seeding template

```
task = f"""
You are the {ROLE} in the VELOCITY-AI bug-fix line. Read your role contract:
  .kiro/bug-fix-workflow/agents/{ROLE}.md
and follow it EXACTLY, including the register/card discipline and return contract.

Repo root: /Users/bilala/Developer/Projects/VELOCITY-AI
Work from: {frontend/ or backend/ as the fix site dictates}
Domain: {domain}   Batch: {fix_site}   Cards: {ids}
Tier / route: {tier}   (A′ = replicate the named FIX card, skip validate/analyze)

Verify scoped only:
  frontend: npx tsc --noEmit ; npx vitest run --no-coverage --maxWorkers=3 <file>
  backend:  cd backend && python3.11 -m pytest <file> -x -q   (offline tier, one file)
  e2e:      cd tests/integration/e2e && .venv/bin/python -m pytest suites/<area>/<file>.py::<test> -q
The e2e suite lives in its OWN isolated venv (tests/integration/e2e/.venv, python3.11
with pytest-playwright). It is DELIBERATELY separate from the backend tree — the
default interpreter on PATH does NOT have `playwright` installed, so a bare
`pytest` / `python3 -m pytest` fails with `ModuleNotFoundError: No module named
'playwright'`. ALWAYS invoke it via `tests/integration/e2e/.venv/bin/python`, never
the default python. It drives the real Google Chrome (channel=chrome, no bundled
Chromium) and needs the frontend on :3000 + backend on :8000 to be up. If the venv
is missing, create it once:
  uv venv tests/integration/e2e/.venv
  uv pip install -p tests/integration/e2e/.venv -r tests/integration/e2e/requirements.txt
If a card's e2e test carries `@pytest.mark.xfail(strict=True)` tied to that card,
the FIX/VERIFY that lands the fix must also remove the marker, or a real pass errors
as an unexpected XPASS.
Never run the full suite. Never git commit/add/push. Leave changes in the tree.
Return your role's contract verbatim.
"""
spawn_run(agent="kirocrew", task=task, model=<haiku|sonnet from run-doc>,
          include_lessons=True)   # lessons ON — these workers edit code/tests
```

- **Agent MUST carry file + shell + test tools.** Use **`kirocrew`** (the full
  agent), NOT `kirocrew-lite` / `kirocrew-knowledge` / `kirocrew-research` — the
  lite/specialist variants are read/reason-only (no `read`/`grep`/`shell`/pytest),
  so a worker phase dispatched to them cannot execute its tools, and its inert tool
  calls can surface as text it then HALLUCINATES a verdict from. This exact failure
  was caught in the first smoke test. The model TIER (haiku/sonnet) is set with the
  `model=` arg on the `kirocrew` agent — do not confuse the model tier with the
  agent name.
- The `model=` value comes from the run-doc batch tag (PLAN.md tiered policy).
- `include_lessons=True` always (workers write code — the operator's corrections matter).
- `include_memory=False` — the task fully specifies the work.
- **Preflight (once, before the first dispatch of a session):** confirm the chosen
  agent actually executes tools — spawn a one-line probe ("read the first 5 lines of
  <a known file> and paste them"). If it returns the real lines, tools work. If it
  says tools are unavailable or returns `<function_calls>` as text, STOP — do not
  dispatch worker phases to it; fall back to running the domain in the main session
  (which has real tools) and tell the operator the sub-agent tier can't carry this.

## Resource note

Host memory is often tight. Before a wide fan-out, check `resource_status`. If
"tight"/"critical": cap the round to 1–2 concurrent workers and serialise the
rest, and prefer `tsc --noEmit` over a full `npm run build` in VERIFY. Never launch
a memory-heavy full build during a parallel wave.

## Tripwires — stop and report, do not route around

- A worker returns `BLOCKED` or `ESCALATE` → surface it; never work around a blocker.
- Two consecutive failed VERIFYs on one card → stop that card, escalate (the
  analysis is probably wrong; retrying the same analysis fails the same way).
- A Bedrock auth failure (expired/again token, 401/403 from Bedrock) is global →
  halt the domain, ask the operator to renew, probe once on resume.
- A card whose fix would need a schema change / new dependency / invariant break →
  escalate; not the worker's call.
