# CONTEXT — quick-260812-lfv (ISS-102)

**Status:** every decision below is LOCKED and evidence-backed. Do not re-derive, do not
re-litigate, do not "improve". Plan and execute exactly this.

---

## The problem

`tests/unit/test_chat_messages_endpoint.py::TestRouting` does not monkeypatch
`run_commands._resolve_concierge`, so the endpoint resolves the REAL `ConciergeCapability`,
whose ctx carries `model=None` → `build_model()` → `ChatBedrockConverse` → a **real AWS
Bedrock `ConverseStream` call**. Until today those calls failed on an expired SSO token and
cost nothing. AWS SSO is now live on this machine, so the next suite run bills real money.

## Verified facts (measured at HEAD d31a5a7b — do NOT re-measure to "confirm", trust these)

### F1 — which tests actually reach the wire
Exactly **two** tests make a real Bedrock call:
- `TestRouting::test_clarify_waiting_routes_to_answers_seam`
- `TestRouting::test_gate_paused_routes_to_gate_seam_approve`

Verbatim evidence (`log_cli`):
`ERROR app.agents.deep_agent_runner:deep_agent_runner.py:610 DeepAgentRunner.astream_events failed: An error occurred (ExpiredTokenException) when calling the ConverseStream operation: The security token included in the request is expired`

The ISSUES-REGISTER row for ISS-102 is **wrong on two counts** and must be corrected at
bookkeeping time (not by this plan):
- it names a third test, `test_terminal_routes_to_revision`. That test does **not** reach a
  model — it dies earlier at `app/api/run_commands.py:2497` with
  `AttributeError: '_FakeUser' object has no attribute 'tier'` (the KAN-161/ISS-055
  entitlement gate; the `_FakeUser` double at `:33` is stale).
- it says "four attempts per run". It is **two** calls; "4" was a grep miscount (2 ERROR log
  lines + the same 2 exceptions repeated inside their tracebacks).

### F2 — why they reach the Concierge at all (this is NOT a bug)
`app/api/chat_router.py::route_chat_turn` deliberately routes to `CHANNEL_CONCIERGE`:
- `PHASE_CLARIFY_WAITING` + no structured `responses` → CONCIERGE ("a plain text turn ...
  must NOT be auto-submitted as a freeform clarify answer")
- `PHASE_GATE_PAUSED` + `turn.action not in GATE_ACTIONS` → CONCIERGE ("a plain free-text
  turn with no action ... must NOT default to 'approve'")

Both tests post bare `text=` with no action / no responses, so they encode the **superseded
pre-safety contract**. Patching `_resolve_concierge` stops the spend but will **NOT** make
them green — they will still get `channel == "concierge"` and a `text/event-stream` body
instead of `"answers"` / `"gate"`.

**LOCKED: leave them red.** Do not change their assertions, do not delete them, do not
`xfail` them. Reconciling a safety-critical routing contract is a separate owner decision
and gets its own ISS row at bookkeeping time.

### F3 — every path to a live client (the chokepoint analysis)
Non-test construction sites, all using LAZY `from <module> import <Class>` inside the
function (so patching the SOURCE MODULE's attribute at call time works — this is already the
proven convention in `tests/unit/test_model_factory.py:77/83/89`):
- `app/agents/model_factory.py:84` `ChatAnthropic`, `:148` `ChatBedrockConverse`, `:58`/`:112` `ChatMistralAI`
- `agents/planner/smart_planner.py:173` `ChatAnthropic`, `:189`/`:196` `ChatBedrockConverse`
  — **this bypasses `build_model()` entirely**
- `deepagents.create_deep_agent(model="anthropic:...")` resolves a string via langchain's
  `init_chat_model` → also constructs `ChatAnthropic` (proven empirically)

There is **no** `init_chat_model` in app code, **no** direct `boto3` bedrock-runtime
invoke/converse, and **no** raw `anthropic`/httpx model call.

**Therefore the true single chokepoint is the three provider CLASSES, not `build_model`.**
A guard over `build_model` would be theatre: it would miss all 5 SmartPlanner tests and the
MCP test, and it would be defeated anyway by the by-value
`from app.agents.model_factory import build_model` imports in `deep_agent_runner.py:58`,
`cached_invoke.py:44` and the handoff agents.

### F4 — the guard mechanism, empirically validated
Patch **`__init__` on the real class** (never replace the class object):
- construction raises  → the guard fires
- `isinstance()` still works → `deep_agent_runner._maybe_apply:234` and
  `cached_invoke:79` keep working
- `object.__new__(ChatBedrockConverse)` still works →
  `tests/agents/test_bedrock_cache_and_thinking.py::_bedrock_instance` keeps working
- tests that replace the whole class attribute (`test_model_factory.py`, the `cap` fixture)
  are unaffected — the factory picks up their stub and never reaches the real class
- `monkeypatch` restores it after every test
- cost: one 0.84s import of `langchain_aws` + `langchain_anthropic` per session

`langchain_mistralai` is **NOT installed** on this machine — the guard must tolerate
`ImportError` per class and skip it. (That absence is also the cause of the 6 pre-existing
`test_model_factory.py` reds: `ModuleNotFoundError: No module named 'langchain_mistralai'`.)

### F5 — live-test gating, as it actually exists
Two established mechanisms, both must be honoured:
- env opt-in `RUN_LIVE_BEDROCK=1` (`tests/agents/test_clarify_llm_live.py:65`,
  `test_phase3_token_delta_live.py:78`, `test_phase8_live.py`, `test_deep_agent_runner_hitl_live.py`)
- the declared pytest marker `requires_api_key` (declared in `pyproject.toml` markers;
  applied via `pytest.mark.requires_api_key` in `tests/integration/test_pipeline_workflows.py:53`)

### F6 — the FULL inventory of offline tests that construct a live client
Measured by running the prototype guard over `tests/unit`, `tests/agents`, `tests/properties`
and `tests/integration`. **10 tests**, of which only the 2 in F1 actually invoke:

Construct AND invoke (the money trap — fixed by Task 1):
1. `tests/unit/test_chat_messages_endpoint.py::TestRouting::test_clarify_waiting_routes_to_answers_seam`
2. `tests/unit/test_chat_messages_endpoint.py::TestRouting::test_gate_paused_routes_to_gate_seam_approve`

Construct only, never invoke (zero spend today, currently GREEN, latent hazard):
3. `tests/unit/test_brief_max_chars.py::test_full_brief_reaches_planner_uncut` (SmartPlanner)
4. `tests/unit/test_brief_max_chars.py::test_ceiling_still_enforced_above_cap` (SmartPlanner)
5. `tests/unit/test_cached_invoke.py::test_bedrock_call_places_cache_control_on_stable_prefix`
6. `tests/unit/test_cached_invoke.py::test_cache_control_suppressed_when_flag_off`
7. `tests/agents/test_iss056_clarify_quality_fixes.py::TestH3SmartPlannerDesignNote::test_design_note_present_when_design_context_supplied` (SmartPlanner)
8. `tests/agents/test_iss056_clarify_quality_fixes.py::TestH3SmartPlannerDesignNote::test_design_note_absent_when_design_context_none` (SmartPlanner)
9. `tests/agents/test_iss056_clarify_quality_fixes.py::TestH3SmartPlannerDesignNote::test_design_note_absent_when_both_names_missing` (SmartPlanner)
10. `tests/agents/test_mcp_client.py::test_bound_mcp_tool_augments_a_deepagents_agent` (ChatAnthropic via `init_chat_model`)

---

## LOCKED DECISIONS

**D1 — Task 1 shape.** Add a **class-scoped autouse fixture inside `TestRouting`** that does
exactly the sibling-class call `monkeypatch.setattr(rc_module, "_resolve_concierge", lambda: fake)`
with a `_StreamingConcierge()` instance. Rationale: only 2 of the class's 8 tests reach the
seam today, but any of them could tomorrow; a per-test patch on the other 6 would be dead
code (INV-12 "no shadows"). The setattr call is byte-identical to the pattern at `:439`,
`:487`, `:539`, `:581`, `:615` — only its placement is class-scoped. `_StreamingConcierge`
is defined later in the file (`:398`); that is fine, it resolves at call time.

**D2 — Guard location.** `backend/tests/conftest.py` (the root conftest for
`testpaths = ["tests"]`), as a function-scoped `autouse` fixture. `tests/agents/conftest.py`
has no autouse fixtures and does not conflict.

**D3 — Guard seam.** Patch `__init__` on `langchain_anthropic.ChatAnthropic`,
`langchain_aws.ChatBedrockConverse`, `langchain_mistralai.ChatMistralAI`. Never replace the
class object. Tolerate `ImportError`/missing attribute per class.

**D4 — Failure mode.** Raise a module-level custom exception naming the test's **nodeid**,
the class constructed, and how to fix it. Loud, and on by default.

**D5 — Allowances, exactly three, no others.**
1. `os.getenv("RUN_LIVE_BEDROCK") == "1"`
2. the item carries the `requires_api_key` marker (`request.node.get_closest_marker`)
3. the item's nodeid is in a single explicit `_CONSTRUCTS_BUT_NEVER_INVOKES` dict declared at
   the top of `conftest.py`, mapping nodeid → one-line reason. Seed it with **exactly the 8
   construct-only nodeids from F6** (items 3-10). Do NOT add items 1 and 2.

   Why a nodeid dict rather than markers on the tests: it keeps the whole guard in ONE
   reviewable file, avoids edits scattered across 4 test files, is trivially greppable, and
   **fails closed** — if a test is renamed it drops out of the dict and the guard fires
   loudly rather than silently passing.

**D6 — Do NOT touch the 8 allow-listed tests.** They stay green and unmodified. They are
filed as their own ISS row at bookkeeping time (a latent-hazard class: one added `.ainvoke`
turns any of them into a live spend). Do not "fix" them here — that is the long tail the
task brief explicitly said to FILE, not fold.

**D7 — Out of scope.** No change to `model_factory.py`, `smart_planner.py`, `run_commands.py`,
`chat_router.py`, or any production file. This is a test-infrastructure change only.
No golden file may move. No test may be deleted, loosened, xfail'd or skipped.

---

## Acceptance (all must be observed, not assumed)

Run every pytest command with this exact prefix — **never** export `AWS_PROFILE`, never
`aws sso login`:

```
env -u AWS_PROFILE -u AWS_REGION -u RUN_LIVE_BEDROCK -u AWS_BEARER_TOKEN_BEDROCK ANTHROPIC_API_KEY="" python3.11 -m pytest ...
```

| # | Check | Required result |
|---|---|---|
| A1 | `tests/unit/test_chat_messages_endpoint.py` | still **3 failed / 17 passed**, same 3 ids |
| A2 | same file with `-o log_cli=true -o log_cli_level=ERROR` | **ZERO** `ExpiredTokenException` / `ConverseStream` lines (was 2) |
| A3 | `tests/unit` whole tree | **62 failed / 1167 passed** (unchanged from baseline) |
| A4 | `tests/agents tests/properties tests/integration` | unchanged from the baseline in `base_agents.txt` |
| A5 | characterization goldens (5 files listed below) | **10 passed** |
| A6 | `git status --porcelain tests/agents/characterization/golden` | **empty** (no golden moved) |
| A7 | `/opt/homebrew/bin/lint-imports` run **from `backend/`** | **4 kept, 0 broken** |
| A8 | planted-test demo | a temporary test calling `build_model()` FAILS with the guard's error naming its nodeid; then the plant is removed |

Golden command:
```
python3.11 -m pytest tests/agents/test_characterization_prototype.py \
  tests/agents/test_characterization_prototype_revision.py \
  tests/agents/test_characterization_od_prototype.py \
  tests/agents/test_characterization_od_ppt.py \
  tests/agents/test_characterization_app_builder.py
```

## Baselines measured at d31a5a7b (BEFORE)

- goldens: **10 passed**, 15 golden files, checksums in scratchpad `golden_before.txt`
- `lint-imports` from `backend/`: **4 kept / 0 broken**
- `tests/unit/test_chat_messages_endpoint.py`: **3 failed / 17 passed**
- `tests/unit` (whole): **62 failed / 1167 passed**
- `tests/agents`+`properties`+`integration`: see `base_agents.txt`
- `test_gates` + `test_declared_gate_streaming` + `test_wire_parity` + `test_prompt_contracts`: **11 failed / 54 passed**
- `test_model_factory` + `test_rest_run_launch`: **8 failed / 34 passed**
- `tests/agents/test_mcp_client.py`: **5 passed**

## Hard money rules for whoever executes this

- NEVER `export AWS_PROFILE`, never pass `AWS_PROFILE=` to pytest, never `aws sso login`.
- Always use the env-unset prefix above.
- Do not launch, resume or approve any pipeline run. Do not drive a browser.
- Do not restart or signal the backend on port 8010 (pid 91032).
- `backend/dev.db` is read-only, SELECT only. There is a paused run `41f77342…` — do not touch it.
- Never `git stash` (an executor once swept a needed local change).
