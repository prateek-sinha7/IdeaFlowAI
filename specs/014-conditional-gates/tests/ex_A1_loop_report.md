# Integration Test Report — `ex_A1_loop`

**Test file:** `tools/api/runs/run.ex_A1_loop.http`
**Run method:** `./run-http.sh ex_A1_loop` (httpyac 6.16.7, `-e local --all`)
**Date/time:** 2026-08-21, 15:38:04–15:42:26 local
**Backend:** already running at `http://localhost:8000` (health check 200, not started/stopped by this test)
**Run ID:** `4ea0a017-5253-4bbd-893f-8a7736d5f447`
**Log transcript:** `tools/api/runs/logs/ex_A1_loop/20260821-153804.log`

## Verdict: FAIL

The specific gate mechanism this file exists to test — **looping back to an earlier step**
(R-06/R-07/R-08, `loop_max_iterations: 3`) — was **never exercised at all**. `greet` ran exactly
once; no retry/loop occurred. This is a direct consequence of the same root cause seen in
`ex_A2_branch`: the `greet` step ignored its literal `write_file` instruction
and produced unrelated markdown documentation instead, so `hello.txt` never existed, `check`
could never read it, and `check`'s output was free-form prose rather than the required strict
`{"decision": "ok"|"retry"}` JSON. The `conditional` gate correctly failed closed on the
unparseable decision (`gate_blocked`, reason `"no matching route outcome and no default_next"`),
but — separately concerning — **that block did not actually stop the run**: the engine fell
through to the next step (`done`) anyway and the pipeline reported `status: "completed"`,
masking the failure as a pass to anyone only checking `pipeline_complete`.

## What was tested

Workflow `ex_A1_loop` (spec 014, example A1 — conditional gate looping
back to an earlier step). Steps per
`backend/agents/workflows/ex_A1_loop/workflow.yaml` **as it existed at
test-run time** (see "workflow.yaml changed after this test ran" below — the file has since been
edited further and no longer reads exactly as quoted here):

1. **Greet** (`custom-agent:greet`) — instructed: `You are the "Greet" step. Call write_file
   with path "hello.txt" and content "hello". Use exactly that path and content — do not use any
   other filename.`
2. **Check** (`custom-agent:check`, `gates: [conditional]`, `produces: ["route_decision"]`) —
   instructed to `read_file("hello.txt")` then respond with exactly one line: `{"decision":
   "ok"}` if content is `"hello"`, else `{"decision": "retry"}`. Route: `ok → done`,
   `retry → greet` (loop back), `loop_max_iterations: 3`, **no `default_next`**.
3. **Done** (`custom-agent:done`) — instructed to `read_file("hello.txt")` to confirm it exists;
   explicitly told not to write anything.

Launch payload deliberately omitted `agent_ids` (per the file's own comment), sourcing the
roster from the compiled plan.

## Step sequence actually observed (display names, from `agent_start`/`agent_complete` events)

| Order | Step (display name) | agent_id | Result |
|---|---|---|---|
| 1 | **Greet** | `custom-agent:greet` | Ran once (15:38:05→15:38:52, ~47s). Did **not** call `write_file` on `hello.txt`. Its one `write_file` tool call wrote to `greet-conditional-gate-loop-back-to-earlier-st.md` with ~40 lines of invented markdown documentation about "conditional gate loop-back" patterns (ASCII diagram, YAML pseudo-example, a table) — content unrelated to the literal one-line instruction. |
| 2 | **Check** | `custom-agent:check` | Ran once (15:38:52→15:41:07, ~135s). Called `read_file` **23 times**, alternating `path: "hello.txt"`, `path: "/hello.txt"`, and once `file_path: "/hello.txt"` (guessing at parameter-name/path variants), every call returning `Error: File '/hello.txt' not found` (because `greet` never created it). Its `thinking_text` shows the model explicitly reasoning about a tool-schema mismatch that doesn't exist (it never was a schema problem — the file was simply never written). Final output was prose: `"The file \`/hello.txt\` was not found. Please verify the correct path to this file, as it may need to be searched from the current working directory instead of with a leading slash prefix."` — **not** the required `{"decision": "ok"\|"retry"}` line. |
| 3 | **Done** | `custom-agent:done` | Ran once (15:41:07→15:42:25, ~78s). Did not call `read_file("hello.txt")` as instructed. Instead called `glob(path="/", pattern="**/*gate*")`, found the two stray `.md` files `greet`/`check` had written, tried reading one from a `/large_tool_results/...` path (an artifact-offload path, not a real read target), then **called `write_file`** on that same `/large_tool_results/check-conditional-gate-loop-back-to-earlier-st.md` path with an unrelated Python code sample about a "done marker" while-loop pattern — despite being told explicitly "Do not call write_file — this step never writes anything." |

`pipeline_complete` reached at event `seq 3803`; `GET /api/runs/{id}` reports `"status":
"completed"`, `"agent_count": 3`, `"duration": 260.4`.

## Loop-back gate behavior (the AC under test) — FAIL / not exercised

This is the primary finding, verified directly against `GET /api/runs/{run_id}/events` (raw
event history, not the `.http` file's own SSE log):

- `greet` (`agent_start` type) appears **exactly once** in the full event history (`seq 4`).
  There was no second pass through `greet` — the loop-back never fired, not once, let alone up
  to the `loop_max_iterations: 3` ceiling.
- `check`'s typed `route_decision` output (the JSON it should have produced) was never valid
  JSON with a `"decision"` key — it was the plain-English "file not found" sentence quoted
  above. Per `backend/agents/capabilities/gates/conditional.py`'s own documented contract
  (`json.loads`es the content; malformed JSON is treated as "no match", never a crash), this
  correctly resolved to "no match against `route.outcomes`".
- Because this workflow's `route` block declares no `default_next`, the gate emitted the
  `gate_blocked` event at `seq 2837`: `{"step": "custom-agent:check", "gate": "conditional",
  "reason": "no matching route outcome and no default_next"}` — this is the code's documented
  "nowhere to go" fail-closed path (`conditional.py` lines 99–120), and it fired correctly given
  the malformed decision.
- **However**, immediately after `gate_blocked` (`seq 2837`), the very next event (`seq 2838`) is
  `agent_start custom-agent:done` — the dispatch loop proceeded to the next step in manifest
  order anyway, and the run went on to reach `pipeline_complete` normally. `gate_blocked` did
  **not** cancel, fail, or pause the run — reading `backend/agents/execution_engine/engine.py`'s
  `_evaluate_gates`, a `block` outcome from a non-HITL gate (`conditional` is not in
  `_HITL_GATES`) only short-circuits *that step's own remaining declared gates*; it does not map
  to the `cancel` sentinel HITL gates use, so the caller's normal step-advance logic simply
  continues. Net effect: a workflow whose only conditional-gate step blocks with "nowhere to go"
  still shows up as a **successfully completed run** to anything checking `status`/
  `pipeline_complete` alone — worth flagging separately from the write_file-adherence root cause,
  since it means a genuinely blocked conditional-routing run is currently indistinguishable from
  a clean pass at the run-status level.
- **Loop-budget behavior (`loop_max_iterations: 3`) was not exercised at all** — the retry path
  that would decrement/check the budget never triggered, so this run provides zero evidence
  about whether the loop-budget enforcement itself works.

## Deliverable / write_file adherence — independently verified, FAIL

`GET /api/runs/{run_id}/artifacts?include=content` (HTTP 200) returns 4 artifacts: one `summary`
per executed step, plus one `deliverable`. **No artifact named `hello.txt` exists.** The
`deliverable` bundles the three agents' raw text/markdown under invented filenames
(`check-conditional-gate-loop-back-to-earlier-st.md`, etc.), matching the pattern from the
`ex_A2_branch` report: `write_file` calls used titles derived from the run's
message/slug, not the literal paths named in each step's `workflow.yaml` prompt. This was
cross-checked directly via the API (`/api/runs/{id}` `agent_outputs[].tool_calls` and
`/api/runs/{id}/artifacts?include=content`), independent of the `.http` file's own inline
assertion — see below for whether that assertion itself is trustworthy.

## workflow.yaml changed on disk after this test ran

`backend/agents/workflows/ex_A1_loop/workflow.yaml` was modified during/
after this test run (confirmed via `git diff` against the working tree after the run completed).
The version **actually exercised by this run** had these three step prompts (quoted verbatim
above in "What was tested"): `Greet` = `"You are the \"Greet\" step. Call write_file with path
\"hello.txt\"..."`, `Check` = `"You are the \"Check\" step. First call read_file with path
\"hello.txt\"..."`, `Done` = `"You are the \"Done\" step. Call read_file with path
\"hello.txt\"..."`. The file on disk now (post-run) has been hardened further, e.g. `Greet`'s
prompt now reads `"Call write_file with path \"hello.txt\" and content \"hello\". Do not ask
clarifying questions. Do not explain your reasoning. Do not use any other filename or content.
Call write_file now with exactly this path and content, then stop."` — a stricter, more
directive rewrite, apparently in response to the same write_file-adherence failure this report
and the `ex_A2_branch` report both document. **This report's findings apply
only to the prompt text quoted above, which is what actually ran; the current on-disk prompts
were not tested by this run** and would need a fresh run to verify whether the stricter wording
fixes the adherence problem.

## Test-file (`.http`) assertion trustworthiness

Per the task's request to verify this file's own assertions before relying on them:

1. **Loop-count assertion (step 4, informational) — confirmed BUGGY, same class of bug as
   `ex_A2_branch`.** The script does `events.filter(e => e.type ===
   'agent_start' && e.data?.agent_id === 'greet')` against `GET /api/runs/{id}/events`. That
   endpoint's actual event shape nests payload under `payload_json`, not `data` (confirmed by
   direct inspection of the raw JSON: every event is `{seq, event_id, type, payload_json:
   {...}}`, no `data` key at all) — so `e.data` is always `undefined` and the filter always
   returns `0`, regardless of how many times `greet` actually ran. Even if the field name were
   fixed, the comparison `=== 'greet'` would still miss, since the real `agent_id` values are
   prefixed (`custom-agent:greet`), not bare `greet` — a second, independent mismatch. The
   transcript's `"Loop count: greet agent ran 0 time(s)"` is consequently meaningless; the real,
   verified count (directly against the API) is exactly `1`, not `0` — and not because of the
   script bug (greet genuinely ran only once; the script bug just also happens to under-report
   it as zero for the wrong reason). **Do not trust this assertion.**
2. **`pipeline_complete` presence assertion (step 4) — trustworthy.** Confirmed independently:
   `pipeline_complete` event exists at `seq 3803`, and `GET /api/runs/{id}` reports `status:
   "completed"`.
3. **`hello.txt` artifact assertion (step 5) — trustworthy and correctly caught the failure.**
   The script's `✗ hello.txt artifact not found` matches direct verification against
   `GET /api/runs/{run_id}/artifacts?include=content` — no artifact named `hello.txt` exists in
   any of the 4 returned artifacts. This assertion is accurate.

Net: 1 of 3 inline assertions (the loop-count log line) is broken by the same `data` vs.
`payload_json` field-name bug documented in the `ex_A2_branch` report; the
other two (`pipeline_complete`, `hello.txt` presence) are accurate and were independently
confirmed.

## Errors / tool-loop issues

- No provider/auth errors — all 3 agent invocations completed on
  `eu.anthropic.claude-haiku-4-5-20251001-v1:0` with no retries or fallback-provider events.
- `check` made 23 `read_file` calls in a single invocation, all against variants of a path that
  never existed (`hello.txt` / `/hello.txt` / `file_path: "/hello.txt"`) — not an infinite loop
  (it eventually stopped and answered in prose), but a clear thrash: the model kept re-guessing
  parameter names/leading-slash variants rather than accepting the first `Error: File
  '/hello.txt' not found` result, consuming the bulk of its 134.7s duration and ~52K input
  tokens on this one step alone (`token_usage` in `GET /api/runs/{id}`: `total_input_tokens:
  63550` across all 3 steps combined).
- `done` similarly wandered off-script: a `glob` for `**/*gate*` and a `read_file`/`write_file`
  round-trip against an artifact-offload path (`/large_tool_results/...`) that has nothing to do
  with its literal one-line instruction to just `read_file("hello.txt")`.

## HTTP status codes observed

| Request | Status |
|---|---|
| `POST /api/auth/login` | 200 |
| `POST /api/runs` (launch) | 200 |
| `GET /api/runs/{id}/events/stream` (SSE) | connected, ran to a terminal event (`pipeline_complete`), no dropped connection |
| `GET /api/runs/{id}/events` | 200 |
| `GET /api/runs/{id}/artifacts?include=content` | 200 |
| `GET /api/runs/{id}` (direct verification query, outside the `.http` file) | 200 |

`6 requests processed (6 succeeded)` per httpyac's own summary — no request-level failures; all
findings above are about run *behavior*, not transport/auth errors.

## Run duration

- Wall clock (transcript): `15:38:05` (login) → `15:42:25` (`pipeline_complete`) ≈ 260s (~4m20s).
- API-reported `duration`: `260.4`s (`GET /api/runs/{id}`) — consistent.
- Per-step (`agent_outputs[].duration`): Greet 46.83s, Check 134.7s, Done 78.71s.

## Conclusion

**FAIL.** The loop-back-to-previous-step gate mechanism that is this fixture's entire reason for
existing was never actually exercised — `greet` ran once, no retry/loop occurred, and
`loop_max_iterations: 3` was never tested. Root cause is identical to the `ex_A2_branch`
finding: the `greet` and `done` agents did not follow their literal `write_file`/`read_file`
step instructions, instead producing unrelated invented content, which cascaded into `check`
never being able to read `hello.txt` and therefore never producing a parseable
`{"decision": ...}` for the gate to route on. The `conditional` gate itself behaved correctly
given that malformed input (`gate_blocked`, "no matching route outcome and no default_next"),
but that block did not halt or fail the run — the pipeline fell through to the next step and
reported `completed` regardless, which independently hides this class of failure from anyone
checking only `pipeline_complete`/`status`. Separately, one of the `.http` file's own three
inline assertions (the loop-count log line) is broken by the same `data`-vs-`payload_json`
field-name bug already documented for `ex_A2_branch`; the other two assertions
(`pipeline_complete`, `hello.txt` presence) are accurate. `workflow.yaml`'s step prompts were
edited (apparently strengthened) after this run completed — this report's findings apply to the
pre-edit prompts quoted above; the current on-disk prompts have not yet been verified by a run.
