# Integration Test Report — `sample_conditional_branch_new`

**Test file:** `tools/api/runs/run.sample_conditional_branch_new.http`
**Run method:** `./run-http.sh sample_conditional_branch_new` (httpyac 6.16.7, `-e local --all`)
**Date/time:** 2026-08-21, 15:28:16–15:30:21 local
**Backend:** already running at `http://localhost:8000` (health check 200, not started/stopped by this test)
**Run ID:** `bcb7d6b6-50b8-4fee-ad0e-b10fe6c202a3`
**Log transcript:** `tools/api/runs/logs/sample_conditional_branch_new/20260821-152812.log`

## Verdict: FAIL

The conditional-gate routing itself works correctly (exactly one of the two forward branches
executed, and `pipeline_complete` was reached), but the workflow's actual deliverable content
is wrong: none of the three executed agents followed their literal `workflow.yaml` step prompt
to call `write_file`, so `output.txt` was never produced and AC #3 ("output.txt contains either
'Hello, world!' or '¡Hola, mundo!'") fails. Separately, the `.http` test file itself has two
pre-existing script bugs that produced misleading (but not the root-cause) failures in its own
inline assertions.

## What was tested

Workflow `sample_conditional_branch_new` (spec 014, example A2 — conditional gate picking ONE
of two forward branches). Steps per `backend/agents/workflows/sample_conditional_branch_new/workflow.yaml`:

1. **Greet** (`custom-agent:greet`) — instructed to `write_file(path="input.txt", content="hi")`.
2. **Pick Language** (`custom-agent:pick`) — a `conditional` gate step, instructed to output
   exactly `{"decision": "english"}` or `{"decision": "spanish"}`, no tool calls. Routes:
   `english → say-hello`, `spanish → say-hola`, no `default_next`.
3a. **Say Hello** (`custom-agent:say-hello`) — instructed to `write_file(path="output.txt", content="Hello, world!")`.
3b. **Say Hola** (`custom-agent:say-hola`) — instructed to `write_file(path="output.txt", content="¡Hola, mundo!")`.

Launch payload deliberately omitted `agent_ids` (per the file's own comment) so the roster is
sourced from the compiled plan rather than the registry allow-list.

## Step sequence actually observed (display names, from `pipeline_start`/`agent_start` events)

| Order | Step (display name) | agent_id | Result |
|---|---|---|---|
| 1 | **Greet** | `custom-agent:greet` | Ran. Did **not** call `write_file`. Only tool call was `ls`. Responded with a clarifying question about a filename it invented itself (see below), not the instructed "hi" → `input.txt`. |
| 2 | **Pick Language** | `custom-agent:pick` | Ran correctly. Output exactly `{"decision": "english"}`, no tool calls, as instructed. |
| 3 | **Say Hello** | `custom-agent:say-hello` | Ran (correct branch — the gate routed on `english`, per `route.outcomes`). Did **not** call `write_file`. Responded with an unrelated clarifying question ("The request is underspecified... Are you looking for code structure implementation?"), ignoring its literal instruction to write "Hello, world!" to `output.txt`. |
| — | Say Hola | `custom-agent:say-hola` | **Did not run** — correctly skipped, confirming the gate picked exactly one branch. |

`pipeline_start` event reported `agent_count: 4` (all 4 steps registered in the compiled plan);
`pipeline_complete` reported `agents_completed: 3` (the 4th, `say-hola`, never executed, as expected).

Display names throughout (`agent_start`, `agent_outputs` in `GET /api/runs/{id}`) correctly show
`Greet` / `Pick Language` / `Say Hello`, not a generic `"Custom Agent"` label — the display-name
fix in `run_commands.py` appears to be working.

## Gate/branch routing correctness (AC #1, #2) — PASS

- `pipeline_complete` event reached at `seq 527`, `total_duration: 122.33`s.
- Exactly one of the two branch targets ran: `say-hello` started and completed; `say-hola` never
  started. Confirmed directly against `GET /api/runs/{run_id}/events` (raw event stream), not
  just the `.http` script's own (buggy) assertion — see "Test-file bugs" below.
- Run status via `GET /api/runs/{run_id}`: `"status": "completed"`.

## Deliverable content correctness (AC #3) — FAIL

`GET /api/runs/{run_id}/artifacts?include=content` (HTTP 200) returns 4 artifacts: one `summary`
artifact per executed step, plus one `deliverable` artifact. **No artifact is named `output.txt`.**
The `deliverable` artifact instead bundles each agent's raw (wrong) text output under
auto-generated filenames:

```
filename: greet-conditional-gate-forward-branch-pick-lan.md
  "What would you like me to write in the file `greet-conditional-gate-forward-branch-pick-lan.md`?"

filename: pick-conditional-gate-forward-branch-pick-lan.md
  {"decision": "english"}

filename: say-hello-conditional-gate-forward-branch-pick-lan.md
  "The request is underspecified. What do you want me to create using a conditional gate
  with forward branching? - Are you looking for code structure implementation? - What
  programming language? - What specific behavior should the conditional gate perform?"
```

Those filenames (`greet-conditional-gate-forward-branch-pick-lan.md`,
`say-hello-conditional-gate-forward-branch-pick-lan.md`) are clearly derived by slugifying the
run's title/message ("Conditional gate forward branch — pick language (A2)"), not the literal
`input.txt`/`output.txt` paths named in each step's `workflow.yaml` prompt. Both `Greet` and
`Say Hello`'s `tool_calls` list (from `GET /api/runs/{run_id}` → `agent_outputs`) shows **zero**
`write_file` calls — `Greet`'s only tool call was `ls`; `Say Hello` made no tool calls at all.
The engine's `artifact_fallback` event fired for all 3 executed steps (`seq 243, 354, 525`),
which is the mechanism that wraps an agent's raw text as a `.md` artifact when it never wrote an
expected file — consistent with the agents never calling `write_file`.

Net effect: the deliverable contains no `output.txt`, and even the closest analog (Say Hello's
raw text) is a confused clarifying question, not "Hello, world!". **AC #3 is not met.**

This is a functional regression in step-prompt adherence, not a routing/gate bug — the
`workflow.yaml` prompts (viewed directly) are simple, explicit one-liners (e.g. `Call write_file
with path "output.txt" and content "Hello, world!". Use exactly that path and content — do not
use any other filename.`), yet the model ignored them entirely in favor of inventing its own
filename and asking clarifying questions about an unrelated "conditional gate implementation"
task. Whoever picks this up should look at what else is being injected into the composed system
prompt for `custom-agent:*` instances alongside the step's literal `prompt` field (e.g. a
title/slug-based default filename hint in `agents/factory.py`'s prompt composition or in
`RunSandbox`/deliverable serialization) — the model is visibly reacting to a filename it was
never told to use in the workflow manifest.

## Errors / tool-loop issues

- No provider/auth errors — the corrected model tag (`eu.anthropic.claude-haiku-4-5-20251001-v1:0`)
  ran successfully for all 3 agent invocations, no retries or fallback-provider events observed.
- No infinite tool loops; `Greet` made exactly 1 tool call (`ls`), `Pick Language` and `Say Hello`
  made 0 tool calls each — if anything, under-use of tools (declining to call the instructed
  `write_file`), not looping.
- `agent_thinking` event volume (429 of 528 total events) is high but consistent with normal
  extended-thinking streaming for a Haiku model; not itself an error.

## Test-file (`.http`) bugs found — separate from the backend issue above

These are pre-existing bugs in `run.sample_conditional_branch_new.http` itself (not modified —
read-only investigation only). Reported for the record, not fixed:

1. **SSE block `ReferenceError` (line 106).** The `{{@streaming ...}}` block declares
   `const agents_seen = new Set()` at line 71 inside the `await new Promise((resolve) => {...})`
   executor, then references it as `exports.agents_seen = agents_seen` at line 106, *after* the
   `await` resolves but still nominally in the same enclosing script block. httpyac's script
   sandbox throws `ReferenceError: agents_seen is not defined` at that line on every run. The SSE
   stream itself worked fine (all `agent_start`/`agent_complete`/`pipeline_complete` events were
   received and logged via `apiLine` before the crash) — only the final `exports.agents_seen`
   hand-off fails, so this request is recorded as "errored" (1 of 6) even though the run
   underneath progressed correctly and reached `pipeline_complete`.
2. **Field-name/prefix mismatch in the step-4 branch-count assertion.** The script does
   `events.filter(e => e.type === 'agent_start' && e.data?.agent_id === 'say-hello')` against
   `GET /api/runs/{id}/events`. But that endpoint's actual event shape nests agent data under
   `payload_json`, not `data` (`data` is the field name used only in the *live* SSE envelope,
   confirmed by direct `GET /api/runs/{run_id}/events` inspection) — so `e.data` is always
   `undefined` and the filter always returns 0 regardless of what actually ran. Even if that were
   fixed, the actual `agent_id` values are prefixed (`custom-agent:say-hello`,
   `custom-agent:say-hola`), not the bare `say-hello`/`say-hola` the script compares against — a
   second, independent mismatch. This produced the misleading "✗ Branch count mismatch: expected
   1/0 or 0/1, got 0/0" in the transcript; the real branch count (verified directly against the
   API, see above) is correctly 1/0.

Both of these are `.http`/test-script defects, not backend defects — they make this specific
test file's own pass/fail signal for AC #2 unreliable, independent of the AC #3 backend failure
documented above.

## HTTP status codes observed

| Request | Status |
|---|---|
| `POST /api/auth/login` | 200 |
| `POST /api/runs` (launch) | 200 |
| `GET /api/runs/{id}/events/stream` (SSE) | connected, completed normally (crashed only in the post-stream script, not the HTTP/SSE transport) |
| `GET /api/runs/{id}/events` | 200 |
| `GET /api/runs/{id}/artifacts?include=content` | 200 |
| `GET /api/runs/{id}` (direct verification query, outside the `.http` file) | 200 |

## Run duration

- Wall clock (transcript): `15:28:16` (login) → `15:30:19` (`pipeline_complete`) ≈ 123s.
- API-reported `duration`: `122.5`s (`GET /api/runs/{id}`); `total_duration: 122.33`s (`pipeline_complete` event payload). Consistent.
- Per-step: Greet ~59.9s, Pick Language ~20.5s, Say Hello ~22.6s (from `agent_outputs[].duration`).

## Recent-fix verification (per task context)

| Fix claimed | Verified? | Evidence |
|---|---|---|
| Entitlements allow this pipeline type for enterprise tier | Yes | `POST /api/runs` returned 200 and launched immediately; no entitlement-rejection error. |
| Local model tag corrected | Yes | All 3 agent invocations completed using `eu.anthropic.claude-haiku-4-5-20251001-v1:0` with no provider/auth errors. |
| `workflow.yaml` prompts simplified | Yes (prompts are simple one-liners) — but simplification alone did **not** fix agent adherence; see AC #3 failure above. | Read directly from `backend/agents/workflows/sample_conditional_branch_new/workflow.yaml`. |
| Display-name bug in `run_commands.py` fixed | Yes | `agent_start` events and `agent_outputs` consistently show `Greet`/`Pick Language`/`Say Hello`, not a generic `"Custom Agent"` label. |

## Conclusion

The conditional-gate branching mechanism itself (spec 014's core feature under test) behaves
correctly: the `pick` step's `{"decision": "english"}` output correctly routed the run cursor to
`say-hello` and skipped `say-hola`, and the run reached `pipeline_complete`. However, the test's
actual pass/fail criterion — `output.txt` containing "Hello, world!" or "¡Hola, mundo!" — is not
met, because the `Greet` and `Say Hello` agents never called `write_file` at all and instead
responded with unrelated clarifying questions, ignoring their literal step prompts. **Overall
verdict: FAIL**, on AC #3 (deliverable content), not on the conditional-gate routing logic that
is spec 014's primary subject.
