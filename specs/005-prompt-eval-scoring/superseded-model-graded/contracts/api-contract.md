# API Contract: Model-Graded Eval Branch (LLM-as-Judge + Report)

**None.** This spec adds no HTTP, WebSocket, or RPC endpoints — confirmed explicitly in
`spec.md` §3.4: "No new HTTP/WebSocket endpoints — this is developer-facing CLI tooling only."

The entire feature is invoked via the local `./tests/evals/eval.sh` shell entry point, executed
directly by a developer on their own machine. It never runs inside the FastAPI app process, is
never reachable over the network, and has no client (frontend or otherwise) that calls it.

## CLI surface (documented here in lieu of an HTTP contract, since this is the feature's only
external interface)

| Command | Effect | Spends tokens? |
|---|---|---|
| `./tests/evals/model_graded/model-graded.sh graded <scenario-id>` | Dispatch scenario to its agent, run deterministic pre-check, print result | Yes — invokes the real agent under test (same cost profile as an existing `--live` run) |
| `./tests/evals/model_graded/model-graded.sh graded <scenario-id> --judge` | Above, plus a judge model call, plus one report entry appended | Yes — agent call + judge call |
| `./tests/evals/model_graded/model-graded.sh graded <scenario-id> --judge --samples N` | Repeats the above N times (default 1), one independent report entry per run | Yes — N × (agent call + judge call) |
| `./tests/evals/model_graded/model-graded.sh graded <scenario-id> --judge --judge-provider P --judge-model M` | Above, judge forced to provider `P`/model `M` | Yes |
| `./tests/evals/model_graded/model-graded.sh graded <scenario-id> --judge --judge-threshold T` | Above, pass/fail cutoff overridden to `T` for this run only | Yes |
| `./tests/evals/model_graded/model-graded.sh report [--last N]` | Read `eval_report.jsonl`, print aggregate summary | No — pure local file read |
| `./tests/evals/model_graded/model-graded.sh report --worst N` | Print the N lowest-`judge_score` entries in full (prompt/response/rationale) | No — pure local file read |
| `./tests/evals/model_graded/model-graded.sh report --by system_prompt_hash [--target T]` | Print per-prompt-version average score/pass rate, chronological; optionally flag whether each version clears `T` | No — pure local file read |

**Exit codes** (following the existing `./tests/evals/eval.sh` scripts' convention — `validate_scenario.py`
uses `SystemExit(1)`/`SystemExit(2)`):
- `0` — scenario ran (PASS or MISS is still exit `0`; a MISS is informational, not a script
  failure — matches `live_benchmark.py`'s existing convention of reporting pass rate without
  raising on a miss).
- `1` — the scenario/agent id is unknown, or a report/precondition error (e.g. `--judge`
  requested with no usable judge credential — spec Story 4 AC3).
- `2` — usage error (missing required argument).

**Stability**: this is dev-tooling, not a public/versioned interface. No backward-compatibility
guarantee beyond this repo's own commit history; the existing `--live`/`benchmark` commands'
contract is unaffected (spec NFR "Backward compatibility") and out of scope for this contract
document.
