---
phase: quick-260812-lfv
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - backend/tests/unit/test_chat_messages_endpoint.py
  - backend/tests/conftest.py
autonomous: true
requirements: [ISS-102]

must_haves:
  truths:
    - "Running the offline unit suite makes ZERO AWS Bedrock calls."
    - "An offline test that constructs ChatAnthropic / ChatBedrockConverse / ChatMistralAI fails loudly, naming its own nodeid."
    - "The 8 known construct-only tests stay green and unmodified."
    - "No production file, no golden file, and no test assertion changed."
  artifacts:
    - path: "backend/tests/unit/test_chat_messages_endpoint.py"
      provides: "autouse `_no_live_concierge` fixture inside class TestRouting"
      contains: "_resolve_concierge"
    - path: "backend/tests/conftest.py"
      provides: "session-wide live-LLM-client construction guard"
      contains: "_CONSTRUCTS_BUT_NEVER_INVOKES"
  key_links:
    - from: "tests/unit/test_chat_messages_endpoint.py::TestRouting"
      to: "app.api.run_commands._resolve_concierge"
      via: "monkeypatch.setattr in a class-placed autouse fixture"
      pattern: "monkeypatch\\.setattr\\(rc_module, \"_resolve_concierge\""
    - from: "tests/conftest.py"
      to: "langchain_aws.ChatBedrockConverse.__init__"
      via: "monkeypatch.setattr on __init__ (never the class object)"
      pattern: "setattr\\(cls, \"__init__\""
---

<objective>
Disarm ISS-102: stop the two offline unit tests that make REAL AWS Bedrock `ConverseStream`
calls, and add a suite-level guard that fails any offline test which constructs a live LLM
client.

Purpose: AWS SSO went live on this machine today. Until today the two calls died on an
expired SSO token and cost nothing; the next suite run bills real money.

Output: two edited test files. Test-infrastructure change ONLY (D7) — no production file,
no golden file, no assertion, no deletion, no `xfail`, no `skip`.
</objective>

<execution_context>
@/Users/1000060523/Documents/Work/UKI/Flowin/flowin/.claude/gsd-core/workflows/execute-plan.md
</execution_context>

<context>
@/Users/1000060523/Documents/Work/UKI/Flowin/flowin/.planning/quick/260812-lfv-disarm-iss-102-patch-testrouting-to-stop/260812-lfv-CONTEXT.md
@/Users/1000060523/Documents/Work/UKI/Flowin/flowin/backend/tests/unit/test_chat_messages_endpoint.py
@/Users/1000060523/Documents/Work/UKI/Flowin/flowin/backend/tests/conftest.py

CONTEXT.md is LOCKED. D1–D7 are settled and evidence-backed. Implement them literally; do
not re-derive, re-measure the BEFORE baselines, or "improve" any decision.
</context>

<money_safety>
Every pytest invocation in this plan MUST carry this exact prefix. It is already baked into
each `<verify>` block — do not strip it.

`env -u AWS_PROFILE -u AWS_REGION -u RUN_LIVE_BEDROCK -u AWS_BEARER_TOKEN_BEDROCK ANTHROPIC_API_KEY="" python3.11 -m pytest ...`

- NEVER `export AWS_PROFILE`, never pass `AWS_PROFILE=` to pytest, never `aws sso login`.
- Do not launch, resume or approve any pipeline run. Do not drive a browser.
- Do not restart or signal the backend on port 8010 (pid 91032).
- `backend/dev.db` is read-only, SELECT only. Paused run `41f77342…` — do not touch it.
- Never `git stash`.
- All pytest commands run with cwd = `/Users/1000060523/Documents/Work/UKI/Flowin/flowin/backend`
  (pytest rootdir; nodeids resolve as `tests/...` only from there).
- There is no `timeout`/`gtimeout` binary and pytest-timeout is not installed (verified).
  Bound long runs with the Bash tool's own `timeout` parameter (max 600000 ms) or
  `run_in_background`.

Scratch dir for captured output (referred to below as `$SCRATCH`):
`/private/tmp/claude-502/-Users-1000060523-Documents-Work-UKI-Flowin-flowin/596265fd-12e7-4286-ae15-4994405a6584/scratchpad`
</money_safety>

<tasks>

<task type="auto">
  <name>Task 1: Patch TestRouting so the Concierge seam can never reach a live model (D1)</name>
  <files>backend/tests/unit/test_chat_messages_endpoint.py</files>
  <action>
Insert ONE autouse fixture as the first member of `class TestRouting` — i.e. between the
`class TestRouting:` line (currently :239) and `def test_clarify_waiting_routes_to_answers_seam`
(currently :240).

Shape, per D1:
- Decorator: `@pytest.fixture(autouse=True)`.
- Signature: `def _no_live_concierge(self, monkeypatch):`.
- Body, in order: `from app.api import run_commands as rc_module`; then
  `fake = _StreamingConcierge()`; then the line
  `monkeypatch.setattr(rc_module, "_resolve_concierge", lambda: fake)` — byte-identical to the
  sibling pattern already at :439, :487, :539, :581 and :615. Only the placement is new.
- Docstring must record WHY, so a future reader cannot delete it as noise: ISS-102 — a bare-text
  turn at `PHASE_CLARIFY_WAITING` / `PHASE_GATE_PAUSED` is deliberately routed to
  `CHANNEL_CONCIERGE` by `app/api/chat_router.py::route_chat_turn` (a plain text turn must NOT
  be auto-submitted as a clarify answer, and must NOT default to `approve`). The REAL
  `ConciergeCapability` resolved by `run_commands._resolve_concierge` (:918, called at :1442)
  carries `model=None`, so it goes `build_model()` → `ChatBedrockConverse` → a live AWS
  `ConverseStream` call. Class-wide rather than per-test because only 2 of the 8 methods reach
  the seam today but any of them could tomorrow; a per-test patch on the other 6 would be dead
  code (INV-12, "no shadows").

DO NOT write `scope="class"`. VERIFIED on this machine (pytest 8.3.4): a `scope="class"` fixture
that requests `monkeypatch` errors with
`ScopeMismatch: You tried to access the function scoped fixture monkeypatch with a class scoped request object`.
D1's "class-scoped" means PLACEMENT — the fixture lives in the class and covers all 8 methods.
Its pytest scope stays the default `function`, which is exactly what keeps the setattr call
byte-identical to the sibling pattern. Verified in the same probe: a plain
`@pytest.fixture(autouse=True)` inside a class applies to every method and monkeypatch restores
the attribute after the class.

`_StreamingConcierge` is defined LATER in the file (:398). That is fine — the fixture body
resolves it as a module global at call time, not at definition time (D1).

Change NOTHING else in the file. Do not touch a single assertion. Per F2 the two target tests
encode the SUPERSEDED pre-safety routing contract and MUST stay red; reconciling that contract
is a separate owner decision that gets its own ISS row at bookkeeping time.

EXPECTED, DO NOT "FIX": after this change the same two tests still fail, but for a new reason —
they now get `channel == "concierge"` and/or a `text/event-stream` body (so `resp.json()` may
raise) instead of a swallowed Bedrock error. The third red,
`test_terminal_routes_to_revision`, is untouched by this fixture and keeps dying at
`app/api/run_commands.py:2497` with `AttributeError: '_FakeUser' object has no attribute 'tier'`
(KAN-161/ISS-055; the `_FakeUser` double at :33 is stale).
  </action>
  <verify>
```bash
# A1 + A2 in one run (cwd = backend)
env -u AWS_PROFILE -u AWS_REGION -u RUN_LIVE_BEDROCK -u AWS_BEARER_TOKEN_BEDROCK ANTHROPIC_API_KEY="" \
  python3.11 -m pytest tests/unit/test_chat_messages_endpoint.py \
  -o log_cli=true -o log_cli_level=ERROR 2>&1 | tee "$SCRATCH/a1a2_after.txt" | tail -30

# A2 — must print 0
grep -c "ExpiredTokenException\|ConverseStream" "$SCRATCH/a1a2_after.txt" || echo 0

# A1 — the failing id set must be exactly the 3 known reds
grep "^FAILED" "$SCRATCH/a1a2_after.txt"
```
  </verify>
  <done>
A1: `3 failed, 17 passed`, and the three FAILED ids are exactly
`TestRouting::test_clarify_waiting_routes_to_answers_seam`,
`TestRouting::test_gate_paused_routes_to_gate_seam_approve`,
`TestRouting::test_terminal_routes_to_revision`.
A2: the `ExpiredTokenException|ConverseStream` count is **0** (was 2).
No other line of the file changed (`git diff --stat` shows one file, additions only).
  </done>
</task>

<task type="auto">
  <name>Task 2: Add the offline live-client construction guard to tests/conftest.py (D2–D5) and prove it with a planted test (A8)</name>
  <files>backend/tests/conftest.py, backend/tests/unit/test_iss102_guard_plant.py (temporary — created then deleted)</files>
  <action>
**Step A — the A4 comparator is ALREADY CAPTURED. Do not re-run it.**
ORCHESTRATOR CORRECTION: the planner inspected `$SCRATCH/base_agents.txt` while that run was
still in flight, which is why it looked truncated. It has since completed and is the valid
comparator (225 lines, full FAILED list, summary line present):

    57 failed, 1723 passed, 42 skipped, 2 warnings in 414.11s

That capture was taken WITHOUT the guard and BEFORE any edit in this plan, and Task 1 touches
only `tests/unit/test_chat_messages_endpoint.py`, so it is a true pre-guard baseline for these
three trees. Use `$SCRATCH/base_agents.txt` directly as the A4 "before". Do NOT spend another
7 minutes re-capturing it.

For reference, the orchestrator's prototype guard over these same three trees produced
`61 failed, 1719 passed, 42 skipped` — a delta of exactly **+4**, being the four agents-side
allow-list entries (3 × `test_iss056_clarify_quality_fixes.py::TestH3SmartPlannerDesignNote`
+ 1 × `test_mcp_client.py::test_bound_mcp_tool_augments_a_deepagents_agent`). With those four
in `_CONSTRUCTS_BUT_NEVER_INVOKES`, the correct AFTER result is **57 failed / 1723 passed /
42 skipped** — i.e. delta ZERO. Anything else is a regression and must be reported, not
explained away.

**Step B — write the guard into `backend/tests/conftest.py` (D2).**
Keep the existing module docstring and the `import app.models  # noqa: F401` line intact; append
to them. Add `import functools`, `import importlib`, `import os`, `import pytest`.

Four module-level members plus one fixture:

1. `_CONSTRUCTS_BUT_NEVER_INVOKES: dict[str, str]` — the D5 allowance-3 dict, nodeid → one-line
   reason. Seed it with EXACTLY the 8 construct-only nodeids from CONTEXT F6 items 3–10, verbatim,
   and nothing else (do NOT add F6 items 1 and 2):
   - `tests/unit/test_brief_max_chars.py::test_full_brief_reaches_planner_uncut` — "SmartPlanner builds its model, then the test asserts on the composed prompt only; the model is never invoked."
   - `tests/unit/test_brief_max_chars.py::test_ceiling_still_enforced_above_cap` — "Same SmartPlanner prompt-only assertion at the cap boundary; construction only."
   - `tests/unit/test_cached_invoke.py::test_bedrock_call_places_cache_control_on_stable_prefix` — "Builds a real ChatBedrockConverse to exercise cache_control shaping; the request is never sent."
   - `tests/unit/test_cached_invoke.py::test_cache_control_suppressed_when_flag_off` — "Same cache_control shaping with the flag off; construction only."
   - `tests/agents/test_iss056_clarify_quality_fixes.py::TestH3SmartPlannerDesignNote::test_design_note_present_when_design_context_supplied` — "SmartPlanner design-note prompt assertion; construction only."
   - `tests/agents/test_iss056_clarify_quality_fixes.py::TestH3SmartPlannerDesignNote::test_design_note_absent_when_design_context_none` — "Same, design context absent; construction only."
   - `tests/agents/test_iss056_clarify_quality_fixes.py::TestH3SmartPlannerDesignNote::test_design_note_absent_when_both_names_missing` — "Same, both names missing; construction only."
   - `tests/agents/test_mcp_client.py::test_bound_mcp_tool_augments_a_deepagents_agent` — "create_deep_agent resolves the 'anthropic:' model string via init_chat_model; the graph is inspected, never run."
   Precede the dict with a comment recording D6: this is a LATENT-HAZARD class — adding one
   `.ainvoke`/`.astream` to any of these turns it into live spend. They are filed as their own
   ISS row at bookkeeping time. Do NOT modify those 8 test files in this plan.
   Also record D5's rationale for a nodeid dict over per-test markers: the whole guard stays in
   ONE reviewable, greppable file, and it FAILS CLOSED — a renamed test drops out of the dict and
   the guard fires loudly instead of silently passing. Matching is therefore EXACT nodeid
   membership; do not add prefix or parametrize-suffix stripping.

2. `class LiveModelClientConstructed(BaseException)` — the module-level custom exception (D4).
   Derive from `BaseException`, NOT `Exception`, and comment why: `app/agents/deep_agent_runner.py:586`
   is `except Exception as exc:  # noqa: BLE001 — mirror the legacy swallow`, which converts the
   exception into a yielded `{"type": "error"}` event (that is precisely how the ISS-102
   `ExpiredTokenException` surfaced as a log line at :610 rather than a test failure). An
   `Exception`-derived guard error raised on that path would be swallowed and the test would pass
   silently — the opposite of D4's "Loud, and on by default". VERIFIED on this machine
   (pytest 8.3.4): a custom `BaseException` subclass is reported as a normal `FAILED` and the
   session continues (`1 failed, 1 passed`); only `KeyboardInterrupt` and `Exit` abort a run.

3. `_guarded_classes()` — decorated `@functools.lru_cache(maxsize=1)`, returns a tuple of
   `(class_name, cls)` pairs for the three provider classes named in D3:
   `langchain_anthropic.ChatAnthropic`, `langchain_aws.ChatBedrockConverse`,
   `langchain_mistralai.ChatMistralAI`. Resolve each with `importlib.import_module` + `getattr`
   inside its OWN `try/except (ImportError, AttributeError)` and SKIP that class on failure —
   `langchain_mistralai` is not installed on this machine (F4), which is also the cause of the 6
   pre-existing `test_model_factory.py` reds. Resolve inside the function, not at module import,
   so the ~0.84s import cost (F4) is charged once per session on first use and never at
   collection time.
   Comment why these three CLASSES are the chokepoint rather than `build_model` (F3): the app has
   no `init_chat_model` call, no direct boto3 bedrock-runtime invoke and no raw anthropic/httpx
   call, but `agents/planner/smart_planner.py:173/:189/:196` bypasses `build_model()` entirely and
   `deepagents.create_deep_agent(model="anthropic:...")` constructs `ChatAnthropic` via langchain's
   own `init_chat_model` — a `build_model` guard would miss all 6 of those and be defeated anyway
   by the by-value `from app.agents.model_factory import build_model` imports at
   `deep_agent_runner.py:58` and `cached_invoke.py:44`.

4. `_blocked_init(nodeid, class_name)` — returns an `__init__(self, *args, **kwargs)` closure that
   raises `LiveModelClientConstructed`. The message must name all three things D4 requires: the
   test's nodeid, the class it tried to construct, and how to fix it — offering exactly three
   remedies: (a) patch the construction seam in the test (e.g.
   `monkeypatch.setattr(rc_module, "_resolve_concierge", lambda: fake)`, or replace the class
   attribute on the SOURCE module as `tests/unit/test_model_factory.py:77/83/89` already does);
   (b) mark the test `@pytest.mark.requires_api_key` if it genuinely needs a live provider;
   (c) if it provably constructs but never invokes, add its nodeid + a one-line reason to
   `_CONSTRUCTS_BUT_NEVER_INVOKES` in `backend/tests/conftest.py`.

5. `_forbid_live_model_clients(request, monkeypatch)` — decorated `@pytest.fixture(autouse=True)`,
   function-scoped, in the root conftest so it covers all of `testpaths = ["tests"]` (D2;
   `tests/agents/conftest.py` declares no autouse fixture and does not conflict — verified).
   Return early WITHOUT patching on exactly three allowances and no others (D5):
   (a) `os.getenv("RUN_LIVE_BEDROCK") == "1"`;
   (b) `request.node.get_closest_marker("requires_api_key") is not None` — the marker is declared
       in `backend/pyproject.toml` (verified);
   (c) `request.node.nodeid in _CONSTRUCTS_BUT_NEVER_INVOKES`.
   Otherwise, for each `(class_name, cls)` from `_guarded_classes()`, call
   `monkeypatch.setattr(cls, "__init__", _blocked_init(request.node.nodeid, class_name))`.
   Patch `__init__` ONLY — never replace the class object (D3/F4), so `isinstance()` keeps working
   at `deep_agent_runner._maybe_apply:234` and `cached_invoke:79`,
   `object.__new__(ChatBedrockConverse)` keeps working for
   `tests/agents/test_bedrock_cache_and_thinking.py::_bedrock_instance`, tests that swap the whole
   class attribute on the source module are unaffected (the factory picks up their stub and never
   reaches the real class), and monkeypatch restores `__init__` after every test.

**Step C — the A8 planted-test demonstration.**
Create `backend/tests/unit/test_iss102_guard_plant.py` containing exactly one test,
`test_guard_fires_on_build_model`, which imports `build_model` from `app.agents.model_factory`
and calls it with no arguments. VERIFIED on this machine under the env-unset prefix:
`settings.ANTHROPIC_API_KEY` is empty, `settings.AWS_REGION` is `'eu-central-1'` and
`settings.BEDROCK_INFERENCE_PROFILE_ID` is `'eu.anthropic.claude-haiku-4-5-20251001-v1:0'` — so
`build_model()` reaches `ChatBedrockConverse(**bedrock_kwargs)` at
`app/agents/model_factory.py:148`, which is the guarded seam.

CORRECTION to the planning note (verified by the orchestrator, do not re-propagate the error):
those values are **hardcoded code defaults** at `app/core/config.py:130` (`AWS_REGION`), `:123`
(`BEDROCK_INFERENCE_PROFILE_ID`) and `:118` (`BEDROCK_MODEL_ID`). There is **NO `backend/.env`
file** — `find backend -maxdepth 1 -name ".env*"` returns nothing. This matters and is stronger
than the "a .env overrides it" reading: `-u AWS_REGION` cannot help because Bedrock is configured
**by default in code**, so the test suite has no offline-by-default state at all. The ONLY thing
standing between this suite and a bill is whether AWS credentials happen to resolve — which is
exactly why this guard is the deliverable. Run the plant alone, confirm it FAILS with `LiveModelClientConstructed` and that the
message contains the literal nodeid
`tests/unit/test_iss102_guard_plant.py::test_guard_fires_on_build_model`, then DELETE the file and
confirm the tree is clean of it.

**Step D — run the remaining acceptance rows** (A3, A4-after, A5, A6, A7) exactly as written in
`<verify>`.

Touch NO production file (D7). Do not modify any of the 8 allow-listed tests (D6). Do not move a
golden. Do not delete, loosen, xfail or skip any test.
  </action>
  <verify>
```bash
# ── Step A: DO NOT re-capture. The A4 "before" already exists and is complete: ─
#   $SCRATCH/base_agents.txt  →  57 failed, 1723 passed, 42 skipped
sed -n '$p' "$SCRATCH/base_agents.txt"

# ── A3: whole unit tree — must be 62 failed / 1167 passed ────────────────────
env -u AWS_PROFILE -u AWS_REGION -u RUN_LIVE_BEDROCK -u AWS_BEARER_TOKEN_BEDROCK ANTHROPIC_API_KEY="" \
  python3.11 -m pytest tests/unit > "$SCRATCH/a3_after.txt" 2>&1; tail -5 "$SCRATCH/a3_after.txt"

# ── A4: same three trees, after the guard — diff the FAILED/ERROR id sets ────
env -u AWS_PROFILE -u AWS_REGION -u RUN_LIVE_BEDROCK -u AWS_BEARER_TOKEN_BEDROCK ANTHROPIC_API_KEY="" \
  python3.11 -m pytest tests/agents tests/properties tests/integration \
  > "$SCRATCH/a4_after.txt" 2>&1; tail -5 "$SCRATCH/a4_after.txt"
diff <(grep -E "^(FAILED|ERROR)" "$SCRATCH/base_agents.txt" | sort) \
     <(grep -E "^(FAILED|ERROR)" "$SCRATCH/a4_after.txt"    | sort) && echo "A4: id sets identical"

# ── A5: characterization goldens — must be 10 passed ────────────────────────
env -u AWS_PROFILE -u AWS_REGION -u RUN_LIVE_BEDROCK -u AWS_BEARER_TOKEN_BEDROCK ANTHROPIC_API_KEY="" \
  python3.11 -m pytest tests/agents/test_characterization_prototype.py \
    tests/agents/test_characterization_prototype_revision.py \
    tests/agents/test_characterization_od_prototype.py \
    tests/agents/test_characterization_od_ppt.py \
    tests/agents/test_characterization_app_builder.py 2>&1 | tail -5

# ── A6: no golden moved (must print nothing) ────────────────────────────────
git status --porcelain tests/agents/characterization/golden
shasum tests/agents/characterization/golden/* | diff - "$SCRATCH/golden_before.txt" \
  && echo "A6: all 15 golden checksums unchanged"

# ── A7: import contracts — 4 kept, 0 broken (run from backend/) ──────────────
/opt/homebrew/bin/lint-imports 2>&1 | tail -5

# ── A8: planted test fires the guard, then is removed ───────────────────────
env -u AWS_PROFILE -u AWS_REGION -u RUN_LIVE_BEDROCK -u AWS_BEARER_TOKEN_BEDROCK ANTHROPIC_API_KEY="" \
  python3.11 -m pytest tests/unit/test_iss102_guard_plant.py 2>&1 | tail -25
rm backend/tests/unit/test_iss102_guard_plant.py 2>/dev/null || rm tests/unit/test_iss102_guard_plant.py
git status --porcelain tests/unit/test_iss102_guard_plant.py   # must print nothing

# ── final: only the two intended files changed ──────────────────────────────
git status --porcelain
```
  </verify>
  <done>
A3: `62 failed, 1167 passed` for `tests/unit` — identical to the locked baseline.
A4: the FAILED/ERROR id sets of `a4_before.txt` and `a4_after.txt` are identical (`diff` empty).
A5: `10 passed` across the five characterization files.
A6: `git status --porcelain tests/agents/characterization/golden` prints nothing AND all 15
    checksums match `$SCRATCH/golden_before.txt`.
A7: `lint-imports` reports **4 kept, 0 broken**.
A8: the plant FAILED with `LiveModelClientConstructed`, the message contained the literal string
    `tests/unit/test_iss102_guard_plant.py::test_guard_fires_on_build_model` and the class name
    `ChatBedrockConverse`; the file is then gone and `git status --porcelain` for it is empty.
Final: `git status --porcelain` lists exactly `backend/tests/conftest.py` and
    `backend/tests/unit/test_chat_messages_endpoint.py` — nothing else.
  </done>
</task>

</tasks>

<acceptance_table>
Carried verbatim from CONTEXT.md — this table is the definition of done.

| # | Check | Required result |
|---|---|---|
| A1 | `tests/unit/test_chat_messages_endpoint.py` | still **3 failed / 17 passed**, same 3 ids |
| A2 | same file with `-o log_cli=true -o log_cli_level=ERROR` | **ZERO** `ExpiredTokenException` / `ConverseStream` lines (was 2) |
| A3 | `tests/unit` whole tree | **62 failed / 1167 passed** (unchanged from baseline) |
| A4 | `tests/agents tests/properties tests/integration` | **57 failed / 1723 passed / 42 skipped**, and the FAILED/ERROR id set identical to `$SCRATCH/base_agents.txt` |
| A5 | characterization goldens (5 files) | **10 passed** |
| A6 | `git status --porcelain tests/agents/characterization/golden` | **empty** (no golden moved) |
| A7 | `/opt/homebrew/bin/lint-imports` run **from `backend/`** | **4 kept, 0 broken** |
| A8 | planted-test demo | a temporary test calling `build_model()` FAILS with the guard's error naming its nodeid; then the plant is removed |

Planning-time note WITHDRAWN by the orchestrator: the planner read `base_agents.txt` while that
run was still in flight and concluded it was truncated. It completed and is valid
(225 lines, full FAILED list, summary `57 failed, 1723 passed, 42 skipped`). A4 uses it
directly; no re-capture is needed and none should be run.
</acceptance_table>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| offline test process → AWS Bedrock | the only boundary in scope; a constructed provider client can cross it and bill real money |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-lfv-01 | Denial of Service (cost) | `TestRouting` → real `ConciergeCapability` → `ChatBedrockConverse` | mitigate | Task 1: class-placed autouse `monkeypatch.setattr(rc_module, "_resolve_concierge", …)` |
| T-lfv-02 | Denial of Service (cost) | any future offline test constructing a provider class | mitigate | Task 2: root-conftest autouse guard patching `__init__` on the three provider classes (D3) |
| T-lfv-03 | Tampering | guard silently bypassed by a broad `except Exception` (`deep_agent_runner.py:586`) | mitigate | guard exception derives from `BaseException`; verified pytest 8.3.4 still reports it as `FAILED` |
| T-lfv-04 | Repudiation | a renamed allow-listed test silently keeps its exemption | mitigate | exact-nodeid matching only — the dict fails CLOSED (D5) |
| T-lfv-05 | Tampering | the 8 allow-listed construct-only tests each become live spend on one added `.ainvoke` | accept | out of scope by D6; filed as its own ISS row at bookkeeping time |
| T-lfv-SC | Tampering | package installs | n/a | no package is installed by this plan |
</threat_model>

<verification>
Run the tasks strictly in order — Task 1 then Task 2 — so each change's effect is isolated:
A1/A2 are measured with the guard absent, and Task 2 Step A captures its comparator with Task 1
already landed (Task 1 touches only `tests/unit`, so the three A4 trees are untouched by it).

Do NOT re-measure the BEFORE baselines in CONTEXT.md; they are locked and correct.
</verification>

<success_criteria>
All eight acceptance rows A1–A8 observed (not assumed), and `git status --porcelain` lists
exactly two modified files: `backend/tests/conftest.py` and
`backend/tests/unit/test_chat_messages_endpoint.py`.
</success_criteria>

<output>
Commit as `test(tests): disarm ISS-102 — stop offline Bedrock spend + add live-client guard`.
Write the quick-mode summary to
`.planning/quick/260812-lfv-disarm-iss-102-patch-testrouting-to-stop/260812-lfv-SUMMARY.md`.

Carry these three items to bookkeeping (they are corrections/filings, NOT work for this plan):
1. The ISS-102 register row is wrong on two counts — it names `test_terminal_routes_to_revision`
   (which never reaches a model; it dies at `run_commands.py:2497` on `_FakeUser.tier`), and it
   says "four attempts per run" when it is two calls (a grep miscount).
2. A new ISS row for the 8 construct-only tests: a latent-hazard class, one added `.ainvoke`
   from live spend, currently exempted by nodeid in `backend/tests/conftest.py`.
3. A new ISS row for the superseded routing contract: the two `TestRouting` tests assert
   `answers`/`gate` where `chat_router.route_chat_turn` now deliberately returns `concierge`.
   Reconciling a safety-critical routing contract is an owner decision.
</output>
