# Integration Test Report — `ex_A2_branch`

**Attempt #3** — supersedes both prior FAIL reports. The workflow was redesigned since attempt
#2: **all tool access was removed from every step** (`read_files: false`, `write_files: false`,
`exec: false` on all 4 steps, confirmed by reading
`backend/agents/workflows/ex_A2_branch/workflow.yaml` directly before this run).
Per the dispatch instructions, **old AC #3 ("output.txt contains…") no longer applies** — there is
no file I/O in this workflow anymore. It is replaced by the 5 flow/routing-correctness checks
below.

**Test file:** `tools/api/runs/run.ex_A2_branch.http`
**Run method:** `./run-http.sh ex_A2_branch` (httpyac 6.16.7, `-e local --all`)
**Backend:** already running at `http://localhost:8000` (health check 200 both times, not
started/stopped by this test) — a local `uvicorn app.main:app --reload` dev server (see "Root
cause of the cancellation" below)
**Two runs executed** (the first run's outcome was unusual enough — routing bug + a genuine
backend engine defect — that a second run was executed to confirm it reproduces rather than being
a one-off fluke; it reproduced identically in every structural respect)

| | Run A | Run B (repro) |
|---|---|---|
| Run ID | `c218dc0e-4c99-499e-83f5-d97ce4833301` | `2ae92c04-107e-4f19-8818-6c0d94291f5a` |
| Log transcript | `tools/api/runs/logs/ex_A2_branch/20260821-161238.log` | `tools/api/runs/logs/ex_A2_branch/20260821-161711.log` |
| Wall clock | 16:12:39 → 16:13:20 local | 16:17:12 → 16:18:34 local |
| Final `status` | `cancelled` | `cancelled` |
| API `duration` | 41.4s | 82.5s |

## Verdict: FAIL

Neither run reached `pipeline_complete`; both ended in `status: "cancelled"`. Three distinct,
independent problems were found, none of which is the old "tool-bound steps ignored their
instructions" issue (there are no tools declared, so that specific failure mode cannot recur —
see the tool-exclusion finding below for why that premise itself turned out to be false):

1. **`pick` never produced its instructed decision JSON**, in *either* run — it answered a
   clarifying question instead, both times. (In Run B, `greet` also failed this way.)
2. **A genuine backend engine defect**: when the `conditional` gate correctly detects "no
   matching route outcome and no default_next" (`gate_blocked`), the dispatch loop does **not**
   honor the block — it falls through and starts the *next array step anyway* (`say-hello`),
   contradicting workflow.yaml's own documented design ("No default_next — an unrecognised
   decision value terminates the run at step 2"). Confirmed by reading the dispatch-loop source,
   not just by observing the symptom — see below.
3. **The run terminates via `pipeline_cancelled` mid-flight**, for a reason that is *not* the
   `/api/runs/{id}/cancel` endpoint (not called) — most likely the local dev server's
   `--reload` restarting mid-run. Flagged as environment-suspected, not proven — see below.

## Step sequence actually observed (display names, from `GET /api/runs/{id}` `agent_outputs` +
`GET /api/runs/{id}/events`)

### Run A

| Order | Step | agent_id | Output | Matches expected? |
|---|---|---|---|---|
| 1 | **Greet** | `custom-agent:greet` | `"hi"` (16.72s, 0 tool calls) | **Yes** — exact match to `Respond with exactly: "hi"` |
| 2 | **Pick Language** | `custom-agent:pick` | *"I need clarification on your request. Could you specify: 1. Which language…"* (15.81s, 0 tool calls) | **No** — not `{"decision": "english"}` / `{"decision": "spanish"}`, or anything close |
| — | *(gate)* | — | `gate_blocked`: `"reason": "no matching route outcome and no default_next"` | Gate correctly detected the mismatch |
| 3 | **Say Hello** | `custom-agent:say-hello` | *(none — cut off)* | Started despite the gate block (bug #2); never completed |
| — | Say Hola | `custom-agent:say-hola` | did not run | N/A |

Terminal event: `pipeline_cancelled` at `seq 386`, ~8s after `say-hello` started (before any
`tool_call`/streaming event for it). Run status: `"cancelled"`.

### Run B (repro)

| Order | Step | agent_id | Output | Matches expected? |
|---|---|---|---|---|
| 1 | **Greet** | `custom-agent:greet` | *"I need more context to help you effectively with 'Conditional gate forward branch — pick language (A2)'. Could you clarify: 1. Which programming languages…"* (16.14s, 0 tool calls) | **No** — this time even `greet` failed to say "hi" |
| 2 | **Pick Language** | `custom-agent:pick` | *"I need to understand what options A2 and the pick involve for implementing a conditional gate forward branch. Let me check the context first."* (33.81s, **6 tool calls**: `glob`×2, `ls`, `read_file`×2) | **No** — wrong content, and it used tools it should not have had (see finding below) |
| — | *(gate)* | — | `gate_blocked`: `"reason": "no matching route outcome and no default_next"` (identical reason string, reproduced) | Gate correctly detected the mismatch again |
| 3 | **Say Hello** | `custom-agent:say-hello` | *(none — cut off, but got further this time)*: made real `ls`/`read_file` tool calls (seq 1020, 1021, 1070, 1102), all returning real sandbox contents, before being cut off | Started despite the gate block (bug #2, reproduced); never completed |
| — | Say Hola | `custom-agent:say-hola` | did not run | N/A |

Terminal event: `pipeline_cancelled` at `seq 1234`, ~32s after `say-hello` started (mid
tool-exploration). Run status: `"cancelled"`.

Display names throughout (`agent_start`, `agent_outputs`) correctly show `Greet` / `Pick
Language` / `Say Hello`, not a generic `"Custom Agent"` label, in both runs.

## AC-by-AC results

| # | Criterion | Run A | Run B | Verdict |
|---|---|---|---|---|
| 1 | `greet` responds exactly "hi" | PASS | **FAIL** (clarifying question instead) | **Not reliably met** |
| 2 | `pick` responds with exactly one decision JSON line, no tool calls | FAIL (wrong content; 0 tools, so the "no tools" half held) | FAIL (wrong content; **and** 6 tool calls — the "no tools" half also failed this run) | **FAIL** |
| 3 | Gate routes to exactly one of say-hello/say-hola, never both, never neither | **FAIL** — say-hello started despite no valid decision (should have terminated at step 2 per neither-branch semantics) | **FAIL** — identical | **FAIL**, and it's a confirmed engine bug, not LLM variance (see below) |
| 4 | Chosen branch step responds with its exact expected text | FAIL — say-hello never produced output (cut off) | FAIL — same | **FAIL** |
| 5 | Run reaches `pipeline_complete` / status `"completed"` | FAIL — `"cancelled"` | FAIL — `"cancelled"` | **FAIL** |

## Finding #1 — `pick` does not follow its literal step prompt

`pick`'s composed prompt (per `workflow.yaml`) is:

```
Respond with exactly one of these lines:
{"decision": "english"}
{"decision": "spanish"}
```

In both runs, `pick`'s `thinking_text` shows it reasoning almost entirely about the run's
*title/message* (`"Conditional gate forward branch — pick language (A2)"`, the launch payload's
`message` field, injected into `context_message`) as if that were the actual task to solve, e.g.
Run A: *"This is a very brief and ambiguous request… Let me ask for clarification on what
specific language…"*. It answers a clarifying question about "which programming language" instead
of emitting the instructed JSON. `greet` succeeded in Run A with the identical prompt-composition
architecture (own literal one-line instruction + the same title in `context_message`), so this
is not a structural prompt-composition failure by itself — but it is not reliable: in Run B,
`greet` failed the exact same way `pick` did in Run A. Across 2 runs / 8 step-invocations, this
literal-instruction-adherence failure occurred 3 times (Run A: pick; Run B: greet, pick). This is
a model-behavior/prompt-composition reliability issue with the Haiku model on this workflow
shape, independent of the routing mechanism itself.

## Finding #2 — CONFIRMED backend bug: post-step `conditional` GATE_BLOCK is not honored

This is the most important finding, established by reading source, not just by observing the
symptom.

`agents/capabilities/gates/conditional.py` (`ConditionalGate.evaluate`) correctly detects "no
matching route outcome and no default_next" and returns `outcome=GATE_BLOCK` with a `gate_blocked`
event (lines 99–120) — this fired correctly in both runs (`seq 382` / `seq 916`, identical reason
string).

But in `agents/execution_engine/engine.py`, the **pre-step** gate loop explicitly halts on a
block outcome:

```python
# engine.py ~2759-2786
if _outcome in ("block", "wait_human"):
    _halted = True
...
if _halted:
    cursor += 1
    continue
```

The **post-step** gate loop — the one `conditional` actually runs under, since `conditional` is
in `_POST_STEP_GATES` (engine.py:5895) — only branches on `_outcome == "route"`
(engine.py:2882-3046, `async for _ge, _outcome, _gdetail in self._evaluate_gates(step, ectx,
_registry, phase="post"):` … `if _outcome == "route": …`). **There is no `elif _outcome ==
"block":` arm at all.** When the outcome is `"block"` instead of `"route"`, `_routed` stays
`False`, execution falls through past the `if _routed: continue` skip, into the normal
post-step/cursor-advance path (`cursor = len(ordered_agents) if step.is_leaf else cursor + 1`,
engine.py:3074-3076) — i.e. **the dispatch loop advances to the next array step exactly as if
the gate had passed.**

This is why `say-hello` started in both runs even though `pick` never produced a matching
decision. It directly contradicts `workflow.yaml`'s own header comment: *"No default_next — an
unrecognised decision value terminates the run at step 2."* The correct behavior per that
comment would be for the run to end (cleanly, at `pick`, with neither branch executing) — instead
it silently proceeds into `say-hello`. This reproduced byte-identically (same `gate_blocked`
reason string, same subsequent `agent_start: say-hello`) across both independent runs, so it is
not LLM-driven noise — it is a code-level gap in
`agents/execution_engine/engine.py`'s post-step gate-evaluation loop (~lines 2882-3046):
whoever owns this should add a `block`/`wait_human` handling arm there, symmetric to the existing
pre-step one at ~2759-2786 (e.g. treat conditional-gate block for a post-step as ending the run,
consistent with the workflow author's documented intent, rather than falling through to
`cursor += 1`).

## Finding #3 — tool exclusion is NOT actually enforced, contradicting the task's stated premise

The dispatch instructions stated "ALL tool access was removed from ALL steps… every step is now a
pure text/JSON response, no tools at all." This was verified against `workflow.yaml`'s source
(`read_files: false / write_files: false / exec: false` on every step) and independently
re-verified against the **compiled** plan:

```
$ python3.11 -c "from agents.execution_engine.engine import compile_for_run; ..."
custom-agent:pick      | tools= ToolPermissions(read_files=False, write_files=False, exec=False, ...)
custom-agent:say-hello | tools= ToolPermissions(read_files=False, write_files=False, exec=False, ...)
```

Compile-time is correct. But at runtime, in Run B, `pick` made 6 real tool calls (`glob`×2,
`ls`, `read_file`×2) and `say-hello` made 3 more (`ls`, `read_file`×2) — **all of them
succeeded and returned real sandbox contents**, e.g.:

```
tool_call  {"tool": "ls", "args": {"path": "/"}}
tool_result {"tool": "ls", "result": "['/.logs/', '/greet-conditional-gate-forward-branch-pick-lan.md']"}
```

This is not a denial error — it is a genuine, working filesystem read against the run sandbox,
despite `read_files=False` on the compiled step. The intended enforcement chain
(`agents/workflows/permission_caps.py::apply_cap` → `Step.tools` →
`engine.py: step_tools=ectx.current_step.tools` →
`agents/factory.py: denied_tools = permission_caps.denied_tools(ctx.step_tools)` →
`DeepAgentRunner(denied_tools=…)` → `_ToolFilterMiddleware(excluded=…)` in
`app/agents/deep_agent_runner.py`) reads correctly at every hop by source inspection, and
`agents/execution_engine/kernel_services.py` (`run_agent`, lines 1645-1679) does bind
`ectx.current_step = step` before each step's invocation and restore it after, so I could not
pin down the exact break point without live server logs (`tool_permission: … requested=… :
granted=…`, `agents/workflows/permission_caps.py::log_decision`, logged at INFO) or a debugger —
this needs someone with access to those. `greet` made 0 tool calls in both runs, but that alone
does not prove denial worked for it — it may equally mean tools were available but unused (its
prompt is trivial enough that a model doesn't need to explore). Net: **the task's premise that
this workflow is now tool-less could not be confirmed live — it directly contradicts what was
observed in Run B.** This is a candidate regression worth its own investigation, separate from
findings #1 and #2.

## Root cause of `pipeline_cancelled` — environment-suspected, not proven

Neither run's cancellation was caused by the `POST /api/runs/{id}/cancel` endpoint or a WS
`cancel_pipeline` message — neither was called by this test or by me. `chat_narrator.py`'s
`"Cancelled by you"` text is a generic label applied to *every* `pipeline_cancelled` event
regardless of cause (`app/agents/chat_narrator.py:215`), so it is not itself evidence of a user
action.

Circumstantial evidence points at the local dev server: `ps` confirms it is running
`uvicorn app.main:app --reload` (PID 94963, started ~14:59, i.e. well before either run), and
`.env` sets `RUNS_ROOT=./runs` — i.e. **inside** the `backend/` tree uvicorn's `--reload` watches
by default. Real artifact writes did land under `backend/runs/<user>/<run_id>/*.md` during both
runs (confirmed via `find … -newermt`). If `--reload`'s file matcher is not restricted to `*.py`
in this setup, a mid-run write there would restart the ASGI app and kill the in-flight run's
asyncio task — which maps exactly to the `except asyncio.CancelledError:
self._state_machine.transition(pipeline_run_id, "cancelled")` path at `engine.py:3078-3085`,
producing exactly the observed `pipeline_cancelled` shape. I could not fully confirm this (no
access to the uvicorn process's own console output to see a literal "Reloading…" line at the
exact cancellation timestamp, and modern uvicorn/watchfiles commonly defaults to matching only
`*.py` changes, which would rule this out) — **flagged as inferred/environmental, not an
established root cause.** What I can state with certainty: it reproduced at a different point in
each run (~8s into `say-hello` in Run A, ~32s into `say-hello` in Run B) with no `agent_error` or
`pipeline_failed` event anywhere in either transcript, no explicit cancel call from any observed
actor, and no `budget_aborted` (the 300s `wall_clock_seconds` limit was nowhere close to being
hit in either run — 41.4s and 82.5s respectively).

## Errors / tool-loop / thrash issues

- No `agent_error`, `pipeline_failed`, or `budget_aborted` events in either run.
- No provider/auth errors — `eu.anthropic.claude-haiku-4-5-20251001-v1:0` served every
  invocation successfully in both runs.
- No runaway tool-loop/thrashing: `pick`'s 6 tool calls and `say-hello`'s 3 tool calls in Run B
  were exploratory (`glob`/`ls`/`read_file`), not repeated/looping calls to the same tool with
  the same args. The task's expectation of "should be none now, since there are no tools to
  thrash on" does not hold, per Finding #3 — tools were present and used, just not in a
  pathological loop.
- `agent_thinking` event volume was high in both runs (Run B: 1235 total events for only 2
  completed steps) but consistent with normal extended-thinking streaming, not itself an error.

## Test-file (`.http`) bugs found — pre-existing, unchanged from attempt #2, not fixed (read-only)

1. **SSE block `ReferenceError` at line 106** (`exports.agents_seen = agents_seen;` references a
   `const` declared inside the enclosing `Promise` executor's scope, from outside it). Reproduces
   on every run regardless of outcome — it fired identically in both runs here, immediately after
   each run's `pipeline_cancelled` was received and logged via `apiLine`. Marks the SSE request as
   "errored" (1 of 6) even though the underlying stream/events were received correctly.
2. **Step-4 branch-count assertion field-name/prefix mismatch**: `events.filter(e => e.type ===
   'agent_start' && e.data?.agent_id === 'say-hello')` — the durable `/events` endpoint nests
   event data under `payload_json`, not `data` (confirmed via direct `GET
   /api/runs/{id}/events` inspection), and the real `agent_id` is prefixed
   (`custom-agent:say-hello`), not bare. In both runs here this produced "✗ Branch count mismatch:
   … got 0/0" — which happens to be superficially plausible this time (neither branch
   *completed*), but for the wrong reason: `say-hello` genuinely *started* and ran for up to 32s
   (Run B) before being cut off, which this assertion is structurally incapable of detecting
   either way (it would report 0/0 even if `say-hello` had fully completed, since the field names
   it reads never match anything).

Both are `.http`/test-script defects, not backend defects, independent of Findings #1-#3 above.

## HTTP status codes observed (both runs, identical)

| Request | Status |
|---|---|
| `POST /api/auth/login` | 200 |
| `POST /api/runs` (launch) | 200 |
| `GET /api/runs/{id}/events/stream` (SSE) | connected; all server-side events (through `pipeline_cancelled`) received correctly; the *client script* threw post-receipt (bug #1 above) — not an HTTP/SSE transport failure |
| `GET /api/runs/{id}/events` | 200 (both the `.http` file's own request and my independent re-verification `curl`) |
| `GET /api/runs/{id}/artifacts?include=content` | 200 (ran; correctly found no `output.txt`, as expected under the tool-less redesign) |
| `GET /api/runs/{id}` (independent verification, outside the `.http` file) | 200 |

## Run duration

- Run A: wall clock 16:12:39 → 16:13:20 (41s); API-reported `duration: 41.4`s. Per-step: Greet
  16.72s, Pick Language 15.81s, Say Hello (incomplete, cut off ~8s after start).
- Run B: wall clock 16:17:12 → 16:18:34 (82s); API-reported `duration: 82.5`s. Per-step: Greet
  16.14s, Pick Language 33.81s, Say Hello (incomplete, cut off ~32s after start).

## Conclusion

The tool-less redesign is real at the manifest/compile level (`workflow.yaml` and the compiled
`Step.tools` both confirm every step is `read_files=False, write_files=False, exec=False`), so
the *previous* two reports' root cause ("tool-bound steps ignored their write_file instructions")
cannot recur as such. But the workflow still does not pass, for three new and more fundamental
reasons: (1) the `pick` step is unreliable at producing its literal instructed JSON output at all
(2/2 runs failed here, plus `greet` failed once too), which never gives the conditional-gate
routing a fair chance to demonstrate correct A2 branching behavior; (2) when routing legitimately
fails (gate correctly reports `gate_blocked`), a real backend engine defect in
`agents/execution_engine/engine.py`'s post-step gate-evaluation loop (no `block`-outcome handling,
unlike the pre-step loop) causes the dispatch loop to proceed into `say-hello` anyway instead of
terminating the run as `workflow.yaml`'s own documented design specifies; and (3) the tool
exclusion this whole redesign was supposed to guarantee is not actually enforced at runtime (Run
B), which independently invalidates the task's stated premise. On top of all that, both runs were
independently cut short by a `pipeline_cancelled` whose trigger could not be conclusively
identified (environment-suspected: the local `uvicorn --reload` dev server, given `RUNS_ROOT`
resolves inside its watched tree) — meaning even a run where `pick` *did* answer correctly might
still not have reached `pipeline_complete` in this environment. **Overall verdict: FAIL**, on ACs
2, 3, 4, and 5 in both runs (AC 1 additionally failed in Run B) — for reasons distinct from,
and more actionable than, the previous two attempts' failure mode.
