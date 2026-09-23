# DISPATCH — how Kiro orchestrates a domain run

Kiro plays the `0-orchestrator` role. Unlike the Claude Code version (a separate
Opus agent), here Kiro IS the session and dispatches workers with `spawn_run`.
Kiro keeps its own context thin: it never validates/analyzes/fixes/verifies in the
main session — it dispatches sub-agents and consumes only their ~15-line return
contracts.

## Windows execution — mandatory patterns (learned 2026-08-31)

**Read this before dispatching a single command. Ignoring it costs 20+ minutes of
retries on every domain run.**

This workspace runs PowerShell on Windows with a PTY echo bug and a restrictive
ExecutionPolicy. The symptoms look like hanging commands or garbled output, but
they are deterministic failures with known workarounds.

### The four problems and their fixes

**Problem 1 — PTY echo.** The `execute_pwsh` tool echoes every character as it is
sent to the terminal. Multi-line output looks like a stream of garbage. Complex
commands appear to hang.
- **Fix:** Write commands to `.cmd` files at the project root and run them via
  `cmd /c <file>.cmd`. The `.cmd` file redirects output to a `.txt` file; read
  that with `read_file`. Simple existence checks (`Test-Path`, single `Write-Host`)
  are safe inline — anything that calls an external process is not.

**Problem 2 — PowerShell ExecutionPolicy blocks `.ps1` scripts.** npm, npx, and
any tool that installs as a `.ps1` wrapper silently fail.
- **Fix:** Always invoke npm/npx via `cmd /c "npm run ..."`. Never call `npm` or
  `npx` directly from PowerShell.

**Problem 3 — Relative paths for the backend venv fail.** PowerShell interprets
`backend\.venv\Scripts\uvicorn.exe` as a module import path.
- **Fix:** Always use the absolute path:
  `C:\Users\2000152842\Downloads\IdeaFlowAI\backend\.venv\Scripts\<tool>.exe`

**Problem 4 — `build_context.py` (stage 2 of rebuild) always fails on Windows.**
One MOD-*.md architecture card has a non-UTF-8 byte (0x90 at ~position 7187).
`build_context.py` reads it with the system codec (cp1252) and crashes.
- **Fix:** Accept that `CONTEXT.md` stays stale. Report as pre-existing. Do NOT
  retry the rebuild trying to fix this — it is a data issue in the card, not a
  transient failure.

### Server startup

Start servers with `control_pwsh_process action=start`:

```
# Backend
command: C:\Users\2000152842\Downloads\IdeaFlowAI\backend\.venv\Scripts\uvicorn.exe app.main:app --reload --host 0.0.0.0 --port 8000
cwd:     C:\Users\2000152842\Downloads\IdeaFlowAI\backend

# Frontend
command: cmd /c "npm run dev"
cwd:     C:\Users\2000152842\Downloads\IdeaFlowAI\frontend
```

Wait 8–10 seconds then read output with `get_process_output lines=20`. Confirm:
- Backend: `🟢 Backend ready` in the log
- Frontend: `✓ Ready in <N>ms` in the log

Do NOT use `Invoke-WebRequest` health checks in complex one-liners — the PTY echo
makes the output unreadable. If you must health-check via HTTP, write a `.cmd` file.

### Running tests

Write a `.cmd` file:
```bat
@echo off
cd /d C:\Users\2000152842\Downloads\IdeaFlowAI\backend
C:\Users\2000152842\Downloads\IdeaFlowAI\backend\.venv\Scripts\python.exe -m pytest <file> -v --tb=short --no-header > ..\test_output.txt 2>&1
echo EXIT_CODE=%ERRORLEVEL% >> ..\test_output.txt
```

For e2e tests:
```bat
@echo off
cd /d C:\Users\2000152842\Downloads\IdeaFlowAI\tests\integration\e2e
.venv\Scripts\python.exe -m pytest suites/<area>/<file> -v --tb=short > ..\..\..\e2e_output.txt 2>&1
echo EXIT_CODE=%ERRORLEVEL% >> ..\..\..\e2e_output.txt
```

Run via `cmd /c <file>.cmd`, read result from the output `.txt` file.

### Preflight for in-session execution (one per session)

Before dispatching any sub-agent that needs to run tests, confirm the venv and
servers are healthy with a `.cmd` file that writes its result to a file, then read
that file. Do not trust prior-session state.

## On "run domain X"

1. **Read state first.** Read `.kiro/bug-fix-workflow/STATE.md` and the domain's
   run-doc `domains/NN-<name>.md`. If resuming, the run-doc's per-batch status
   says what is already done — skip it (idempotent; the register/cards are the
   real state).
2. **Preconditions.** Confirm the domain touches no file another *live* session is
   editing. Note whether app servers need to be up (only VERIFY on browser-
   observable cards needs `:3000`/`:8000`; pure unit/tsc verifies do not).
   **On Windows:** start servers using `control_pwsh_process` with absolute paths
   (see the **Windows execution** section above). Confirm via `get_process_output`
   that both logged their ready message before dispatching any worker that needs them.
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

**Important — ALREADY_FIXED fast-path (observed 2026-08-31):**
The VALIDATE step should also check `ALREADY_FIXED`. Cards recorded months before
HEAD may have had their root fixed by a broad subsequent commit with no card link.
When the validator returns `ALREADY_FIXED`, skip all remaining phases: have the
verifier run the tests once to confirm green, update the card to `status: resolved`,
and go straight to CLOSE. Do NOT run the full ANALYZE → TEST → FIX pipeline for a
card whose tests are already green.

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
