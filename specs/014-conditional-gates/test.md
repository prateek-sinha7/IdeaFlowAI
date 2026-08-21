# 014 — Test plan: how to validate every task, including on a running app

Two kinds of verification run through this spec: **automated** (pytest / scripted-model
harness / validators V1–V6, already wired into `tasks.md` and `workflow.js`) and **on a real
running app** (backend + frontend actually up, a real model in the loop, a real browser). This
file is the second kind — the automated side is already documented in `quickstart.md` and each
validator's `PASS requires all of` block in `tasks.md`; this file doesn't repeat those commands,
it tells you how to reproduce the same behavior live and what to expect when you do.

## 0. Recommended first: a local Ollama harness (qwen3.5:4b) — no cloud, no cost, fastest loop

**Checked on this machine**: Ollama is already installed and running (`ollama --version` →
0.32.14, `curl localhost:11434/api/version` responds) and `qwen3.5:4b` is already pulled
(`ollama list` shows it, 3.4 GB). Nothing to install there. The one real gap: **this codebase
has zero Ollama integration today** (`grep -rn ollama backend` — no hits, no `langchain-ollama`
dependency, no branch in `model_factory.py::build_model()`). This section is the build plan for
closing that gap, test-only — no production code needs to change.

**Why this belongs at the top, not as an afterthought**: it's free, fully offline, and iterates
in seconds instead of minutes. It's also a genuinely harder test of the `route_decision`
contract than Claude — a 4B model is more likely to wrap `{"decision": "ok"}` in a markdown
fence or add commentary despite "output ONLY" instructions, which is exactly the failure mode
R-05b's `json.loads`-or-treat-as-no-match behavior needs to survive. If the mechanism holds up
against qwen3.5:4b, it's solid.

**Why this is a script, not the running app from §0b**: driving `ExecutionEngine.execute()`
directly (like this repo's own offline test harness already does) skips two real obstacles —
`model_catalog.py` is documented as the sole authoritative model-id allow-list, and a
`model_overrides` value sent through the real `POST /api/runs` HTTP path gets validated against
it (per `backend/CLAUDE.md`'s "model-override allow-list" reference); `qwen3.5:4b` isn't in that
catalog, so the HTTP path would reject it outright unless a catalog entry gets added.
`execute()`'s own `model_id`/`model_overrides` params (confirmed at
`agents/execution_engine/engine.py:1059`) have no such gate — the catalog check lives in the API
layer, not the engine — so calling `execute()` directly sidesteps it entirely, with no
production code touched.

### What to build

**1. Add `langchain-ollama` as a dev-only dependency** — `backend/requirements-dev.txt`, not
`requirements.txt` (this is test/harness tooling, never imported by production code). Pin it
using the same resolver-verification convention the existing pins document (`langchain-mistralai`
right above it in `requirements.txt` has an example comment) — I haven't verified the exact
version against this repo's `langchain-core==1.4.0` pin, so run `pip install langchain-ollama`
and confirm the resolved version before pinning it.

**2. A standalone script, not a pytest test** — `backend/scripts/ollama_conditional_gates_harness.py`.
This is a close adaptation of the existing offline end-to-end harness
(`tests/agents/_scripted_model.py::_drive`, already used by `test_compiled_plan_runs.py` to run
composed `custom-agent` workflows like `sample_subagents_parallel` — the exact same shape as
these five fixtures) — same monkeypatch of `factory_mod.create_runner`/`engine_mod.create_runner`
to inject a model onto `ctx.model`, same `RUNS_ROOT` override, same `ExecutionEngine.execute()`
call — except the injected model is a REAL `ChatOllama` instance instead of
`ScriptedFakeChatModel`, so it needs no per-agent script at all:

```python
"""Ad-hoc: run a 014 conditional-gates fixture against local Ollama (qwen3.5:4b).
Not a pytest test. Run directly: python3.11 scripts/ollama_conditional_gates_harness.py <fixture_id>
Needs: `ollama serve` running (already true on this machine), qwen3.5:4b pulled (already true),
`pip install langchain-ollama` (not yet a project dependency — see §0 above).
"""
import asyncio, sys, uuid
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from langchain_ollama import ChatOllama
from app.core.config import settings

OLLAMA_MODEL = "qwen3.5:4b"

async def run_fixture(pipeline_type: str) -> None:
    import agents.execution_engine.engine as engine_mod
    import agents.factory as factory_mod
    from agents.execution_engine.engine import ExecutionEngine

    settings.RUNS_ROOT = "/tmp/flowin-ollama-harness"  # real default (/app/runs) isn't writable locally

    orig_create_runner = factory_mod.create_runner

    def _patched(agent_id, ctx, **kw):
        ctx.model = ChatOllama(model=OLLAMA_MODEL, base_url="http://localhost:11434")
        return orig_create_runner(agent_id, ctx, **kw)

    factory_mod.create_runner = _patched
    engine_mod.create_runner = _patched  # engine imported create_runner by name at module load

    engine = ExecutionEngine()
    run_id = f"ollama-harness-{pipeline_type}-{uuid.uuid4().hex[:8]}"
    try:
        # agents=[] deliberately — per backend/CLAUDE.md's Data Flow doc, execute()
        # falls back to the compiled plan's own steps when the caller supplies no
        # roster (ADR-0008), which is exactly right for a composed custom-agent
        # workflow like these fixtures (get_pipeline_agents() would return [] for
        # them anyway — there's no AGENT.md declaring this pipeline_type).
        async for ev in engine.execute(
            agents=[], user_message="go", pipeline_run_id=run_id,
            pipeline_type=pipeline_type, user_id="ollama-harness-user",
            gate_agent_ids=[],
        ):
            print(ev.get("type"), ev.get("data", {}))
    finally:
        factory_mod.create_runner = orig_create_runner
        engine_mod.create_runner = orig_create_runner

if __name__ == "__main__":
    asyncio.run(run_fixture(sys.argv[1] if len(sys.argv) > 1 else "sample_conditional_previous_step"))
```

**This is a starting skeleton, not a verified-working script** — I built it directly off the
proven `_drive()` pattern and `execute()`'s real signature, but haven't run it. Confirm before
trusting results: (a) `ChatOllama.bind_tools` actually drives the deepagents native `write_file`/
`read_file` tool calls the `custom-agent` steps need — small local models are noticeably less
reliable at structured tool-calling than Claude, and a fixture step that never gets past writing
`hello.txt` is a tool-calling failure, not a conditional-gates bug, don't conflate the two; (b)
whatever `ExecutionEngine()`'s constructor actually needs (`_drive` builds it bare — confirm
nothing else is required for a fixture with no HITL/planner/artifact-store dependency); (c) print
the raw pre-`json.loads` decision text on any route-parse failure, specifically so a malformed
decision (model output) is distinguishable from a genuine routing-logic bug.

### Which fixtures this harness covers

- **A1, A2, A3** — straight through this harness, no extra work; none of them declare `gates:
  [human]`, so there's no pause to script around.
- **A4** — declares `gates: [human]` on `review`, so a real run PAUSES for an actual answer (this
  harness doesn't no-op the gate the way `_drive` does for other pipelines' HITL steps — it can't,
  A4's whole point is that `revise-check` reads that captured answer). Scripting a fake human
  answer into this harness is more involved than the other three; simpler to test A4 against the
  full running app instead (§0b/§0c below), where the real pause/resume flow already works
  through the UI.

Same per-fixture behavioral notes from the cloud section below still apply here (A1's loop path
being unreachable with a model that always reads `hello.txt` correctly is model-independent — it
holds for qwen3.5:4b exactly as it holds for Claude).

## 0b. Bringing up the full app (Bedrock/Anthropic) — needed for Phase 5 and A4

The Ollama harness above only reaches the engine directly — it proves Phases 1–4's runtime
behavior (minus A4) without a UI. Phase 5 (composer/canvas) and A4's human-gate flow need the
real app. Same infra `frontend/e2e/README.md`'s `*.live.spec.ts` suite already uses — nothing new
to provision.

```bash
# 1. Postgres runs natively on the host already (not in docker-compose.yml — see that
#    file's header comment). If you don't have it, this isn't a 014-specific setup step.

# 2. Seed deterministic QA users (idempotent, safe to re-run):
cd backend && python3.11 scripts/seed_test_users.py
# creates qa-basic@flowinqa.com / qa-pro@flowinqa.com / qa-enterprise@flowinqa.com /
# qa-admin@flowinqa.com, all with password flowin-e2e-pass (or $E2E_BASE_PASSWORD)

# 3. Backend on :8000 — pick ONE model provider:
#    (a) real Bedrock, same as CI live tests:
RUNS_ROOT=/tmp/flowin-runs AWS_PROFILE=default AWS_REGION=eu-central-1 \
  python3.11 -m uvicorn app.main:app --port 8000 --timeout-graceful-shutdown 5
#    (b) direct Anthropic instead of Bedrock (backend/CLAUDE.md "Runtime essentials" —
#        build_model() picks ChatAnthropic when ANTHROPIC_API_KEY is set):
ANTHROPIC_API_KEY=sk-... RUNS_ROOT=/tmp/flowin-runs \
  python3.11 -m uvicorn app.main:app --port 8000 --timeout-graceful-shutdown 5
# --timeout-graceful-shutdown is required — a held-open SSE stream (every run in this
# spec keeps one open) makes uvicorn ignore SIGTERM without it. No --reload.

# 4. Frontend on :3000:
cd frontend && npm run dev
```

Login at `http://localhost:3000` with `qa-basic@flowinqa.com` / `flowin-e2e-pass` (any seeded
tier works — none of this spec's checks are tier-gated).

## 0c. A real blocker you WILL hit — read before trying to click a fixture card

All five fixtures ship with `is_beta: true` in their manifest. That field doesn't just add a
badge — I checked `HomeLaunchGrid.tsx:247` and `LibraryPage.tsx:423`, and in both places a beta
row is **permanently non-actionable**: `allowed = !isBeta && canRunPipeline(...)` — `isBeta`
being true forces `allowed` false unconditionally, before the tier check even runs. The card
renders as "Coming Soon" with a disabled button, in every environment, for every tier, with no
override. `quickstart.md`'s own Phase 5 manual steps ("load `sample_conditional_branch_new`
once `user_launchable: true` makes it selectable") don't account for this — `user_launchable`
alone is not enough; `is_beta` blocks the click path independently.

Two ways to actually run a fixture live:

**(a) Bypass the UI, launch via the API directly** (works for Phases 1–4's live checks, where
you don't need the composer/canvas):

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"qa-basic@flowinqa.com","password":"flowin-e2e-pass"}' | jq -r .access_token)

curl -s -X POST http://localhost:8000/api/runs \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"message":"go","pipeline_type":"sample_conditional_previous_step"}'
# -> {"run_id": "..."}  (POST /api/runs body = LaunchCommand, run_commands.py:2041 —
#     "pipeline_type" is the fixture's manifest id)
```

Watch it live:

```bash
curl -N -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/runs/{run_id}/events/stream
```

**(b) Temporarily flip `is_beta: false`** in the fixture's `workflow.yaml` to unlock the actual
catalog card and composer entry — needed for Phase 5's canvas/composer checks, which have no
API-only substitute. Revert it afterward; whether these fixtures ship `is_beta: false`
permanently is a product decision outside this spec's scope, not something to leave flipped by
accident.

---

## Phase 1 — Compiler (T1–T6, guarded by V1)

No running-app angle — this is compile-time only, nothing executes. `V1`'s own PASS criteria
(the compile-and-print-leaves script + the R-03/R-27 negative checks) is the whole story here.
The one live-adjacent sanity check, if you want it: once the backend is up,

```bash
curl -s http://localhost:8000/api/workflows | jq '.[] | select(.id | startswith("sample_conditional"))'
```

confirms all five fixtures parse enough to be listed with a `step_count` — cheap, but not a
substitute for V1.

## Phase 2 — Per-run state (T7–T11, guarded by V2)

Also no running-app angle — `ExecutionContext` fields, unit-tested only. Nothing to click.

## Phase 3 — Dispatch loop (T12–T26, guarded by V3) — where live testing actually matters

This is the first phase with real runtime behavior. Use §0's Ollama harness for A1–A3 (fastest),
or bring up the full app per §0b, then:

**A1 — `sample_conditional_previous_step` (loop). Important caveat**: `greet` unconditionally
writes "hello" to `hello.txt`, and `check`'s prompt is "if it says hello, output ok, else
retry." A real model reading that file will always correctly answer `ok` — **the retry/loop
path is unreachable on a live run of this fixture as authored.** A live run only proves the
straight-through case: `greet` → `check` → `done`, each running exactly once, run completes
normally. The loop count and the `BudgetExceeded` cap (AC-03) can only be proven by the scripted
harness (T23/T24), which controls the model's answer directly — that's not a gap in this test
plan, it's why T23/T24 exist as scripted tests rather than "just run it."

```bash
curl -s -X POST http://localhost:8000/api/runs -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"message":"go","pipeline_type":"sample_conditional_previous_step"}'
# watch via /events/stream; expect greet, check, done each exactly once, status completed
```

**A2 — `sample_conditional_branch_new` (forward branch).** The `pick` step's prompt literally
says "pick either, this is a demo" — a live run reliably proves *mutual exclusivity* (exactly
one of `say-hello`/`say-hola` runs, never both, never neither) but won't reliably show you both
branches without running it several times (model bias toward one answer is a real possibility;
not a defect, just don't read anything into which branch it picks). Run it 3–4 times and confirm
you see both outcomes across the batch, and never both steps in one run.

```bash
for i in 1 2 3 4; do
  curl -s -X POST http://localhost:8000/api/runs -H "Authorization: Bearer $TOKEN" \
    -H 'Content-Type: application/json' \
    -d '{"message":"go","pipeline_type":"sample_conditional_branch_new"}' | jq -r .run_id
done
# then check each run's sandbox output.txt: "Hello, world!" or "¡Hola, mundo!", never both files
```

**A4 — `sample_conditional_human_input` (human-gate-as-condition-source). This is the ONE
fixture where you fully control the branch live**, because `review` pauses for a real human
answer and `revise-check`'s `condition_agent: review` reads what you typed — not the model's own
guess. This is the best live analog for AC-03's loop behavior (you can genuinely force a `retry`
pass by typing something like "please revise this" at the human gate). Needs the browser (or the
`/{run_id}/answers` endpoint) to supply the human response — launch via API, then supply the
gate answer:

```bash
# after launching, the run pauses at "review" (gates: [human]) — find the gate event on the
# SSE stream, then answer it:
curl -s -X POST http://localhost:8000/api/runs/{run_id}/answers \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"answers": {"review": "This looks wrong, please revise it."}}'
# expect: revise-check reads that answer, decides "revise", loop jumps back to greet.
# Run it a second time answering "Looks great, ship it" — expect "continue" -> done.
```

(Confirm the exact `answers` payload shape against whatever the human-gate endpoint already
expects elsewhere in this repo — A4 is new only in that its condition-reader is a conditional
gate, not in how the human gate itself is answered.)

## Phase 4 — Cross-workflow triggering (T27–T33, guarded by V4)

**A3 — `sample_conditional_launch_new` (divert).** Deterministic prompt (`output ONLY
{"decision":"divert"}`), so a live run is a reliable way to see AC-05/AC-08/AC-11 end-to-end —
better than the scripted harness for this one, actually, because you get to see the REAL
`pipeline_diverted` SSE event and the REAL two-linked-cards run-history UI, not a mock of them.

```bash
curl -s -X POST http://localhost:8000/api/runs -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"message":"go","pipeline_type":"sample_conditional_launch_new"}'
# watch /events/stream — expect exactly one "pipeline_diverted" event (not
# "pipeline_complete") before the stream closes, carrying diverted_to_run_id and
# diverted_to_workflow == "sample_conditional_target" (never the literal string "self")
```

Then in the browser (needs is_beta unlocked per §0c, or just open the run-history page directly
by URL/run id if that route isn't itself is_beta-gated): confirm the diverted run's card links
to the new `sample_conditional_target` run and vice versa — both immediately (live, stream still
open at the moment it fires) and after a fresh page reload (historical reconstruction from
`WorkflowRun.status == "diverted"` + `parent_run_id` alone, no live stream).

**Depth-cap (AC-06)** has no convenient live analog with these five fixtures — they're not
chained six deep. Either accept V4's scripted 6-level chain as the sole proof, or if you want to
see it live, temporarily point `sample_conditional_launch_new`'s target at a copy of itself
repeated manually — not worth building a throwaway fixture for unless you specifically want to
eyeball a live `BudgetExceeded` abort.

## Phase 5 — Frontend (T34–T38, guarded by V5/V6) — browser only, no shortcut

This is the one phase where "on the running app" isn't optional extra credit — it's the only way
these tasks get verified at all (canvas UI, composer save/reload round-trip). Needs §0c's
`is_beta: false` flip on whichever fixture(s) you're testing.

1. Composer → load `sample_conditional_branch_new` → confirm `pick` shows a route-target editor
   with `english`/`spanish` outcomes, each wired to a real edge (`say-hello`/`say-hola`).
2. Composer → load `sample_conditional_launch_new` → confirm `decide` shows the new
   external-pipeline reference card pointing at `sample_conditional_target`.
3. Save → reload → confirm the `route` block round-trips byte-identically (diff the manifest
   before/after, or just confirm the editor re-renders the same outcomes after reload).
4. Run A3 live from the composer (not curl this time) → confirm run-history's two-linked-cards
   treatment renders in the actual UI, live and after reload (same assertions as Phase 4's A3
   check above, but through the real components V6 guards, not the API).

---

## Full acceptance sweep — AC → live-app check

| AC | Live-app check |
|---|---|
| AC-01, 02, 09 (compile), 10 | none — compile-time, use V1 |
| AC-01b | none currently — see the gap noted in chat; would need a malformed-JSON scripted case |
| AC-03 | A1 (straight-through only) + A4 (both directions, human-driven) |
| AC-04 | A2, run several times and confirm the untaken branch's step never appears in that run's event log |
| AC-05, AC-11 | A3, via `/events/stream` |
| AC-06 | no convenient live fixture — V4's scripted 6-chain only |
| AC-07 | Phase 5 browser steps 1–3 |
| AC-08 | A3 through the composer, browser step 4 |
| AC-09 (runtime half) | none currently — same gap as noted in chat, this is the untested half of R-26/T20 |

Two gaps repeated here on purpose (already flagged in chat): AC-01b and AC-09's runtime half
have no automated *or* live check anywhere in this plan. Worth a follow-up task, not something
to leave silently uncovered.
