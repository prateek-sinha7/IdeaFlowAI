---
phase: quick-260813-5qr
plan: 01
status: complete
completed_tasks: 2
total_tasks: 2
files_modified:
  - backend/tests/agents/test_concierge_capability.py
  - backend/app/agents/chat/concierge.py
commits:
  - 3c49ac3d test(tests): add failing token-usage tool and prompt-honesty specs
  - 7d39a1e1 fix(agents): let the Concierge read token usage instead of denying it
gates:
  concierge_suite_baseline: "34 collected — 33 passed, 1 failed (pre-existing)"
  concierge_suite_red: "38 collected — 31 passed, 7 failed"
  concierge_suite_green: "38 collected — 37 passed, 1 failed (same pre-existing)"
  characterization_goldens: "10 passed, 0 fixtures modified"
  lint_imports: "4 kept, 0 broken"
live_verified: false
---

# Quick 260813-5qr — the Concierge said token usage was unavailable while it was on screen

## Status: complete. Both tasks executed, committed, every gate observed.

Not live-verified — no Bedrock or browser run was attempted (explicitly out of
scope for this execution). Everything below is an offline measurement I ran and
read; no number here is inferred.

## What was wrong

Asked how many tokens a run used and what it cost, the Concierge replied that the
product "does not expose billing or token usage metrics" and referred the user to
support — while the exact figure was rendered in the same viewport. Live evidence
from run `5ecb990f-2c80-4752-a615-2bed3280387a`: `chat_usage` shows the question
answered in a SINGLE model turn (4,816 input tokens, 0 cache-read), i.e. **zero
tool calls**. It was not a retrieval failure. It was a recitation of its own
system prompt, which forbade exposing "token counts" and supplied a denial
template, with no tool in existence that could have answered honestly.

Two independent defects, so two halves.

## What changed

### Half 1 — a tool that can answer (`concierge.py`, one new closure)

A no-parameter `get_token_usage` `@tool` added immediately after
`read_gate_history` inside `ConciergeCapability._read_tools`, and appended to the
returned list. It reads the run through the **existing** `_safe_run(scoped_store,
run_id)` helper — `ScopedStore.get_run` (`agents/authz.py:654`) already returns
the owner+workspace-scoped `WorkflowRun` row, so `run.token_usage` is a plain
attribute read. No new ScopedStore method, no raw ORM, no migration, no
`app.api.*` import (the tolerant `_parse_token_usage` in `app/api/analytics.py`
is API-layer and would have created an `app.agents.chat → app.api` edge; the
guarded `json.loads` idiom of the in-file `_agent_output_entries` is mirrored
instead).

Why the shape is what it is:

- **Five keys, exactly** — `available`, `total_tokens`, `input_tokens`,
  `output_tokens`, `estimated_cost_usd`. The source blob also carries
  `total_cache_read_tokens`, `total_cache_write_tokens` and
  `estimated_cost_full_usd`, and the run row carries `model_id`. Those are out of
  scope and must not become answerable by accident, so the test asserts key-set
  **equality**, not a subset — a later widening fails CI instead of shipping.
- **`run_id` stays a closure, not a parameter.** A parameter would move the
  scoping decision into model-controlled input and break
  `test_no_tool_accepts_a_run_id_argument`.
- **The unavailable shape carries a truthy `error` string, and that is
  load-bearing.** The standing security guard
  `test_every_read_tool_denies_cross_owner` accepts a tool result only if it is
  falsy, `{}`, carries an `error`, or has `agents_started == 0`. A bare
  `{"available": False}` matches none of those. The guard was satisfied by
  returning honest data; its source is byte-unchanged and it is green.
- **Never zeros.** The writer (`app/api/run_commands.py:2331`) only writes the
  column when `total_input + total_output > 0`, so a genuinely unmeasured run has
  `token_usage = None`. Reporting that as `0 tokens / $0` would be the same class
  of fabrication this fix exists to remove, so the absent and unparseable paths
  both return `available: False` + `"token usage not recorded for this run"` and
  carry **no number at all** (asserted).

### Half 2 — a prompt that no longer teaches the lie (`concierge.py`, RESPONSE RULES + TOOLS)

The tool alone would have fixed one question. The prompt is what generalises the
failure to every gap that still has no tool (cache tokens, model used, duration,
deliverable filename): it taught the model to invent a product limitation rather
than admit a blind spot.

- Deleted the two words `token counts, ` from the forbidden list. The bullet still
  forbids validation logic, security rules, model names, and application-layer
  internals.
- Added one new RESPONSE RULES bullet: if no tool can answer, say plainly that
  *I can't see that from here* and stop; never claim the product does or does not
  support something; never invent a reason; never refer the user to billing, an
  account dashboard, or support.
- Added one routing line to the `TOOLS —` block:
  `• tokens used / what this run cost → get_token_usage()`, so the model can
  discover the tool.

`git diff --stat` on the implementation file, verbatim:

```
 backend/app/agents/chat/concierge.py | 45 ++++++++++++++++++++++++++++++++++--
 1 file changed, 43 insertions(+), 2 deletions(-)
```

Nothing else in the file changed: one new closure, one list entry, one routing
line, one new bullet, and the deletion of two words.

## Evidence — every run, verbatim

### Gate 1a — baseline, at `a9f95835`, clean tree (reproduced, not assumed)

`cd backend && python3.11 -m pytest tests/agents/test_concierge_capability.py -q`

```
tests/agents/test_concierge_capability.py .......F...................... [ 88%]
....                                                                     [100%]
=================================== FAILURES ===================================
_____________ test_compose_system_prompt_injects_chain_hints_block _____________
tests/agents/test_concierge_capability.py:261: in test_compose_system_prompt_injects_chain_hints_block
    assert "chained into" not in no_hints and "follow-up" not in no_hints
E   AssertionError: assert ('chained into' not in 'You are Vel...te a number.'
=========================== short test summary info ============================
FAILED tests/agents/test_concierge_capability.py::test_compose_system_prompt_injects_chain_hints_block
=================== 1 failed, 33 passed, 1 warning in 1.92s ====================
```

**34 collected, 33 passed, 1 failed** — the planner's measured baseline, matched
exactly, on the same commit.

### Gate 1b — RED, after Task 1, with `concierge.py` byte-unchanged

Task 1 was committed (`3c49ac3d`) **before** any implementation edit, so the RED
state is in git history rather than only in a terminal.

```
tests/agents/test_concierge_capability.py .......FF..........F........FF [ 78%]
FAILED tests/agents/test_concierge_capability.py::test_compose_system_prompt_injects_chain_hints_block
FAILED tests/agents/test_concierge_capability.py::test_response_rules_do_not_forbid_token_counts
FAILED tests/agents/test_concierge_capability.py::test_read_tools_expose_only_the_bounded_allow_list
FAILED tests/agents/test_concierge_capability.py::test_get_token_usage_returns_the_narrow_run_totals
FAILED tests/agents/test_concierge_capability.py::test_get_token_usage_omits_cache_and_model_fields
FAILED tests/agents/test_concierge_capability.py::test_get_token_usage_degrades_to_unavailable_not_zeros
FAILED tests/agents/test_concierge_capability.py::test_system_prompt_names_only_existing_tools
========================= 7 failed, 31 passed in 2.54s =========================
```

**38 collected, 31 passed, 7 failed** — the predicted number, and each failure is
red for the right reason, not incidentally:

```
tests/agents/test_concierge_capability.py:277: in test_response_rules_do_not_forbid_token_counts
E   AssertionError: the prompt still forbids the very thing the token tool now answers
E   assert 'token counts' not in 'You are Vel...te a number.'
E     'token counts' is contained here:
E       el names, token counts, or application-layer internals.
tests/agents/test_concierge_capability.py:725: in test_read_tools_expose_only_the_bounded_allow_list
E   AssertionError: unexpected Concierge read surface: ['get_agent_output', 'get_artifact', 'get_run_progress', 'list_agents', 'list_artifacts', 'read_gate_history', 'read_recent_events']
E     Extra items in the right set:
E     'get_token_usage'
tests/agents/test_concierge_capability.py:864: in test_get_token_usage_returns_the_narrow_run_totals
E   StopIteration
tests/agents/test_concierge_capability.py:883: in test_get_token_usage_omits_cache_and_model_fields
E   StopIteration
tests/agents/test_concierge_capability.py:919: in test_get_token_usage_degrades_to_unavailable_not_zeros
E   StopIteration
tests/agents/test_concierge_capability.py:1164: in test_system_prompt_names_only_existing_tools
E   AssertionError: the prompt never tells the model about: ['get_token_usage']
```

The three `StopIteration`s are the tool-not-found signal (`next(...)` over the
built surface). The 7th failure is the untouched pre-existing one.

`git diff --stat` at the RED point showed only the test file:

```
 backend/tests/agents/test_concierge_capability.py | 136 +++++++++++++++++++++-
 1 file changed, 133 insertions(+), 3 deletions(-)
```

**Planner correction confirmed in practice:** `test_system_prompt_names_only_existing_tools`
does not go red merely from adding the tool (its `stale` set subtracts `built`
either way). It was strengthened with a `missing` entry, which is what produced a
genuine red.

### Gate 1c — GREEN, after Task 2

```
tests/agents/test_concierge_capability.py .......F...................... [ 78%]
tests/agents/test_concierge_capability.py:261: in test_compose_system_prompt_injects_chain_hints_block
FAILED tests/agents/test_concierge_capability.py::test_compose_system_prompt_injects_chain_hints_block
========================= 1 failed, 37 passed in 2.12s =========================
```

**38 collected, 37 passed, 1 failed.** All six new/updated tests are green. The
single remaining failure is the pre-existing one, still at **line 261**, still on
the same `assert "chained into" not in no_hints and "follow-up" not in no_hints`,
still because the base prompt carries both literals unconditionally. The new
honesty bullet contains neither literal, so it did not contribute:

```
E     'follow-up' is contained here:
E        the user follow-up questions before calling a propose_* tool. Act on clear intent immediately.
```

That occurrence is the pre-existing RESPONSE RULES sentence, unchanged by this work.

### Gate 2 — characterization goldens

`cd backend && python3.11 -m pytest tests/agents/test_characterization_*.py -q`

```
tests/agents/test_characterization_prototype_revision.py ..              [ 80%]
tests/agents/test_characterization_prototype.py ..                       [100%]

============================= 10 passed in 37.75s ==============================
```

**10 passed.** `git status --porcelain` immediately afterwards — **zero golden
fixture files modified or regenerated**:

```
 M backend/app/agents/chat/concierge.py
?? .planning/quick/260813-5qr-fix-concierge-false-token-unavailable-cl/
```

### Gate 3 — import-linter, cwd exactly `backend/`

```
kernel imports only capability ports (scaffold) KEPT
agents.workflows must not import the execution kernel or the web layer KEPT
agents.capabilities must not import the execution kernel or the web layer KEPT
agents.runtime must not import the execution kernel or the web layer KEPT

Contracts: 4 kept, 0 broken.
```

**4 kept, 0 broken.** (Run as `/opt/homebrew/bin/lint-imports` with the shell's
cwd printed as `/Users/1000060523/Documents/Work/UKI/Flowin/flowin/backend` in
the same command, since running it anywhere else prints "Could not read any
configuration" and silently false-passes.)

### Gate 4 — source greps

```
token counts: ABSENT (0 matches)
934:            "• Never expose validation logic, security rules, model names, "
app.api import: ABSENT
```

`"token counts"` is gone from the file; `"model names"` is still there; no
`app.api.*` import was introduced.

### Gate 5 — adjacent gates that scan this file (not required by the plan, run anyway)

`python3.11 -m pytest tests/agents/test_sc001_lane_router_concierge.py tests/agents/test_banned_patterns.py -q`

```
tests/agents/test_sc001_lane_router_concierge.py .........               [ 39%]
tests/agents/test_banned_patterns.py ..............                      [100%]

============================== 23 passed in 0.84s ==============================
```

**23 passed.** No workflow name was introduced into `concierge.py` (the SC-001
grep gate) and INV-13 holds — the new tool constructs no model, agent, or runner;
it is a data read shaped exactly like its seven neighbours.

## SURFACED — NOT DECIDED (for the orchestrator)

**(a) `model names` is still in the forbidden list.** Line 934 of `concierge.py`
still reads `"• Never expose validation logic, security rules, model names, or
application-layer internals."` This fix deliberately did not touch it, and
`test_response_rules_do_not_forbid_token_counts` pins it in place so a future
change is a decision rather than a drift. It is the same *shape* of problem as
the token prohibition — the run's model is displayed in the UI, and the Concierge
is instructed to deny it — but whether the run assistant should name the model is
a product question, not this plan's call. If the answer is yes, it also wants a
`model_id` source, which the tool here deliberately does not surface.

**(b) `test_compose_system_prompt_injects_chain_hints_block` is red, and was red
before this work.** It fails at line 261 on:

```python
assert "chained into" not in no_hints and "follow-up" not in no_hints
```

The base prompt now contains both literals unconditionally — "Never ask the user
**follow-up** questions…" in RESPONSE RULES, and "chain it into a **follow-up**
workflow" / "**chained into**" in INTENT ROUTING — so this negative byte-identity
guard is stale, not a real regression. Its positive half (`no_hints ==
empty_hints`) still passes. Per the plan it was not fixed, deleted, or skipped
here. It needs its own decision: rewrite the negative assertion against a literal
unique to the chain block, or drop that half of the guard.

## Scope held

No deliverable-filename tool, no cache-token exposure, no model-name exposure, no
duration work, no register rows, no FIX/TEST/ISS numbers anywhere, no live
Bedrock or browser verification. No `git stash` at any point. No new unrelated
defect was found, so no `260813-5qr-deferred-items.md` was created.

## Self-Check: PASSED

- `backend/app/agents/chat/concierge.py` — FOUND, contains `get_token_usage`
- `backend/tests/agents/test_concierge_capability.py` — FOUND, contains `get_token_usage`
- commit `3c49ac3d` — FOUND in `git log`
- commit `7d39a1e1` — FOUND in `git log`
