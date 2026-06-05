# Phase 8 — Live-Verification Playbook (operator runbook)

> **Goal:** prove the migrated `deepagents` runtime works end-to-end against the **real**
> model — AWS Bedrock **Haiku 4.5** — across every pipeline, with a committed, repeatable
> harness. Run **offline first (zero cost)**, then flip live with one env var.
>
> **Scope of this doc:** the exact commands + env to verify each pipeline live, the
> docker-Postgres resume recipe, cost guidance, and troubleshooting. This is verify-only —
> Phase 8 adds **no production code** (harness + tests + this doc only).

| | |
|---|---|
| **Plan** | [`specs/002-deepagents-migration/plan.md` → `### Phase 8`](./plan.md) |
| **Repo root** | `/Users/1000060523/Documents/Work/UKI/Flowin/flowin` |
| **Backend (run everything from here)** | `backend/` |
| **Model** | AWS Bedrock Haiku 4.5 — inference profile `eu.anthropic.claude-haiku-4-5-20251001-v1:0`, region `eu-central-1` |
| **AWS profile** | the **DEFAULT** profile (NOT `personal-sso`) |
| **Opt-in gate** | `RUN_LIVE_BEDROCK=1` + an STS preflight (live path is off by default) |
| **Pricing** | $0.25 / 1M input tokens · $1.25 / 1M output tokens |

---

## ⚠️ Status of referenced test files (read before you start)

All Phase 8 harness, validator, and test files are **present and green** (offline self-tests pass; ruff clean):

| File | Status | Purpose |
|---|---|---|
| `backend/tests/agents/live_harness.py` | ✅ present | T1 harness — the `drive_*` entry points + the opt-in gate (the thing you invoke) |
| `backend/tests/agents/test_live_harness.py` | ✅ present | T1 offline self-test (scripted model; zero Bedrock) |
| `backend/tests/agents/live_contract.py` | ✅ present | T2 content-agnostic per-world validator + cost summary (`summarize_cost`) |
| `backend/tests/agents/test_live_contract.py` | ✅ present | T2 offline self-test for the validator |
| `backend/tests/agents/test_phase8_live.py` | ✅ present | T3 per-pipeline LIVE suite (`RUN_LIVE_BEDROCK`-gated) + HITL on/off + offline proof |
| `backend/tests/agents/test_phase8_resume.py` | ✅ present | T4 cross-process resume-after-kill (docker Postgres) |
| `backend/tests/agents/_resume_child.py` | ✅ present | T4 subprocess runner for the cross-process kill/resume |
| `backend/tests/agents/_scripted_model.py` | ✅ present | the reusable scripted `BaseChatModel` + `_scripts_for` |
| `backend/tests/agents/test_deep_agent_runner_hitl_live.py` | ✅ present | the existing opt-in/SSO-gated runner HITL smoke (the creds pattern this doc reuses) |

Every command below is runnable as written. The `summarize_cost(...)` printer and the `cost_usd()`
math are both available off `tests.agents.live_contract` / `tests.agents.live_harness`.

---

## 1. Prerequisites

Run all commands from the backend dir:

```bash
cd /Users/1000060523/Documents/Work/UKI/Flowin/flowin/backend
```

### 1.1 Python runtime
Homebrew **`python3.11`**, **no venv** (`python` / `python3` are the wrong interpreters):

```bash
python3.11 --version          # expect 3.11.x
which ruff                     # ruff is on PATH (lint, not required to run tests)
```

If the agent loader errors with `ModuleNotFoundError: frontmatter`, install the one missing dep:
```bash
python3.11 -m pip install --user python-frontmatter
```

### 1.2 AWS DEFAULT profile must resolve
The live path uses the **default** credential chain (the harness deliberately does **not** set
`AWS_PROFILE` — per the Phase-8 decision to use the default profile, **not** `personal-sso`).
Confirm with the same cheap STS probe the harness preflight runs (no Bedrock charge):

```bash
aws sts get-caller-identity
```

Expected (known-good): account `473293451041`, an ARN for `ImranY@hexaware.com` (SSO-backed).

If it fails (`ExpiredToken` / `SSOTokenLoadError` / no creds), **refresh the SSO session** — this
is the exact hint the harness emits in `_RUN_LIVE_HINT` (`live_harness.py`):

```bash
aws sso login            # refresh the default-profile SSO session
```

> The harness skips the live path *cleanly* (`pytest.skip`, not error) if creds don't resolve:
> `live_harness._aws_creds_resolve()` probes `sts.get_caller_identity()` and catches
> `BotoCoreError`/`ClientError`. So a stale session never blows up mid-model-call — it just skips.

### 1.3 `ANTHROPIC_API_KEY` must be EMPTY
`build_model()` (`app/agents/model_factory.py`) selects the provider by this single setting:
- `ANTHROPIC_API_KEY` set → `ChatAnthropic` (local dev) — **wrong for Bedrock verification**
- `ANTHROPIC_API_KEY` empty → `ChatBedrockConverse` for `BEDROCK_INFERENCE_PROFILE_ID` in `AWS_REGION` — **this is what we want**

Confirm it is unset/empty in your shell **and** in `backend/.env`:
```bash
echo "shell ANTHROPIC_API_KEY=[${ANTHROPIC_API_KEY}]"      # expect empty
grep -n "ANTHROPIC_API_KEY" .env 2>/dev/null || echo "not in .env (good)"
```
If `.env` sets it, comment it out for the live run (otherwise `live_skip_reason()` returns `None`
because a key is "a usable provider" — but the run would hit **Anthropic, not Bedrock**, defeating
the verification). See Troubleshooting §8.

### 1.4 Docker (only for the resume test)
Native Postgres is **not** installed; the cross-process resume test uses a **docker Postgres
container**. Confirm the daemon is up:
```bash
docker info >/dev/null 2>&1 && echo "docker OK" || echo "docker NOT running — start Docker Desktop"
```
Docker is **not** needed for the offline suites or the per-pipeline live runs (those use the
in-memory checkpointer).

---

## 2. Env block — the one-liner for a live run

The defaults already point at Bedrock Haiku 4.5 in `eu-central-1` (`config.py`:
`BEDROCK_INFERENCE_PROFILE_ID`, `AWS_REGION`), so a live run needs **only** the opt-in flag —
**rely on the default AWS profile; do NOT export `AWS_PROFILE=personal-sso`.**

```bash
# Minimal: opt in, rely on default profile + the built-in Bedrock defaults.
export RUN_LIVE_BEDROCK=1
```

Optional explicit pins (these are the values already defaulted in `config.py` — set them only
to be defensive or to override a stray `.env`):
```bash
export AWS_REGION=eu-central-1
export BEDROCK_INFERENCE_PROFILE_ID=eu.anthropic.claude-haiku-4-5-20251001-v1:0
unset ANTHROPIC_API_KEY        # force the Bedrock branch in build_model()
# Do NOT set AWS_PROFILE — the default credential chain must win.
```

The opt-in gate (`live_harness.live_skip_reason()`) requires **both**: `RUN_LIVE_BEDROCK=1`
**and** a usable provider (resolvable default-profile AWS creds, since `ANTHROPIC_API_KEY` is empty).

---

## 3. Offline first (zero cost) — must be green before spending a cent

These drive the **same** harness machinery with a `ScriptedFakeChatModel` (no Bedrock, no AWS),
so they cost nothing and need no credentials. They are the foundation gate: if the capture
format / drivers are wrong here, every live result inherits the bug.

```bash
cd /Users/1000060523/Documents/Work/UKI/Flowin/flowin/backend

# T1 harness self-test (all 3 worlds: engine / chat / handoff, scripted) — PRESENT.
python3.11 -m pytest tests/agents/test_live_harness.py -v

# T2 validator self-test — PLANNED (run once test_live_contract.py lands).
python3.11 -m pytest tests/agents/test_live_contract.py -v

# T4 resume test — PLANNED. Uses docker Postgres but a SCRIPTED model (no Bedrock),
# so it is part of the OFFLINE gate (it spends $0 on the model; it does need docker).
python3.11 -m pytest tests/agents/test_phase8_resume.py -v
```

Convenience — the whole offline Phase-8 gate in one shot (skips the planned files that don't exist yet):
```bash
python3.11 -m pytest tests/agents/test_live_harness.py tests/agents/test_live_contract.py \
  tests/agents/test_phase8_resume.py -v
```

> `RUN_LIVE_BEDROCK` must be **unset** for these — the offline self-tests assert
> `live_enabled() is False` without it (see `TestOptInAndCost` in `test_live_harness.py`).

Expected: all present tests **pass**; nothing in `tests/agents/test_live_harness.py` makes a
network call. `test_live_harness.py::TestOptInAndCost::test_cost_usd_haiku_pricing` confirms the
pricing math ($0.25/M in + $1.25/M out).

---

## 4. Live per-pipeline runs

Each pipeline has **two** ways to drive it live:
- **(A) pytest entry** — the T3 suite `test_phase8_live.py` (⏳ planned), `RUN_LIVE_BEDROCK`-gated,
  wiring the harness + the T2 validator. Self-skips if not opted in / creds missing.
- **(B) inline harness snippet** — an ad-hoc `python3.11` one-liner against the **present**
  `live_harness.py` API. Useful right now (before T3 lands) and for one-off probes.

**What "good" looks like for every live run** (assertions are content-agnostic — live text is
nondeterministic):
- the run **completes** (`CaptureResult.completed is True`, no `error`);
- **non-zero tokens** (`result.tokens.total > 0` for engine/chat — a real model was called);
- a **valid deliverable** for the world (details per pipeline below).

All snippets share this preamble (sets `ENV=development` so the checkpointer is InMemory — no
Postgres needed for a single run — and forces a writable `RUNS_ROOT`; the harness also forces
`RUNS_ROOT` itself, but being explicit is harmless):

```bash
cd /Users/1000060523/Documents/Work/UKI/Flowin/flowin/backend
export RUN_LIVE_BEDROCK=1
export ENV=development
export RUNS_ROOT=/tmp/flowin-live-runs        # /app/runs is not writable locally
mkdir -p "$RUNS_ROOT"
```

> The harness drive functions take `model=None` → **no patch** → `create_runner` →
> `build_model()` builds real Bedrock. That is the LIVE path. (Passing a `ScriptedFakeChatModel`
> instance instead is the offline path.)

---

### 4.1 Prototype — build (`prototype`)

The heaviest pipeline: `specify → plan → build (per-task sub-agents + Both-validation) → validate`.
Each build task writes/edits `prototype.html` on the run sandbox; the engine runs
`static_check` + `render_check` after each task with a bounded internal fix-loop.

**(A) pytest** (⏳ planned):
```bash
RUN_LIVE_BEDROCK=1 python3.11 -m pytest tests/agents/test_phase8_live.py -k prototype_build -v -s
```

**(B) inline:**
```bash
python3.11 -c '
import asyncio
from tests.agents.live_harness import drive_engine_pipeline
from tests.agents.live_harness import live_skip_reason, cost_usd

async def main():
    skip = live_skip_reason()
    assert skip is None, skip                       # refuse to "fake-pass" offline
    r = await drive_engine_pipeline(
        "prototype",
        brief="Build a single-page personal task-list app with an Add form and a list view.",
        model=None,                                  # None => real Bedrock Haiku
    )
    print("completed:", r.completed, "| error:", r.error)
    print("tokens:", r.tokens.as_dict(), "| cost $%.4f" % r.cost_usd())
    html = r.deliverable or ""
    print("deliverable bytes:", len(html), "| looks like html:", html.lstrip().lower().startswith("<!doctype") or "<section" in html)
asyncio.run(main())
'
```
**Produces:** a `prototype.html` deliverable (multi-section SPA) that passed the engine's
static + render validation. **Expect non-zero tokens.** Roughly the **most expensive** single
pipeline (multiple per-task sub-agent turns + fix-loops) — see the cost table in §7
(~$0.05–0.20 depending on page count).

> The harness auto-supplies a minimal `od_context` (template + design-system body) for
> `prototype`/`od_prototype` so the prompt injection succeeds — you do not need to pass one.

---

### 4.2 Prototype — revision (`prototype_revision`)

One agent (`prototype-revision-agent`) editing `prototype.html` in place, then the smart-hybrid
fix-loop. It can seed the **parent** run's `spec.md`/`design.md`/`tasks.md` via `parent_run_id`
(graceful degrade if absent).

**(A) pytest** (⏳ planned):
```bash
RUN_LIVE_BEDROCK=1 python3.11 -m pytest tests/agents/test_phase8_live.py -k prototype_revision -v -s
```

**(B) inline** — run a build first, then revise it against the SAME run id so the parent
sandbox (spec/design) exists:
```bash
python3.11 -c '
import asyncio
from tests.agents.live_harness import drive_engine_pipeline, live_skip_reason

async def main():
    assert live_skip_reason() is None
    base = await drive_engine_pipeline("prototype",
        brief="Build a simple notes app with a list and an add form.", model=None)
    print("base build completed:", base.completed, "run_id:", base.run_id)
    rev = await drive_engine_pipeline(
        "prototype_revision",
        brief="Add a dark-mode toggle button to the header and persist the choice.",
        parent_run_id=base.run_id,                  # seed parent spec/design
        model=None,
    )
    print("revision completed:", rev.completed, "| error:", rev.error)
    print("tokens:", rev.tokens.as_dict(), "| cost $%.4f" % rev.cost_usd())
    print("revised html bytes:", len(rev.deliverable or ""))
asyncio.run(main())
'
```
**Produces:** a revised `prototype.html` (the requested change applied, regressions auto-fixed).
**Expect non-zero tokens.** Cheaper than a full build (one agent + bounded fix-loop) — ~$0.01–0.05.

---

### 4.3 App Builder (`app_builder`)

A 15-agent code-gen pipeline. Deliverable = `filename:`-block string (code files serialized off
the sandbox by `serialize_sandbox_deliverable`).

**(A) pytest** (⏳ planned):
```bash
RUN_LIVE_BEDROCK=1 python3.11 -m pytest tests/agents/test_phase8_live.py -k app_builder -v -s
```

**(B) inline:**
```bash
python3.11 -c '
import asyncio
from tests.agents.live_harness import drive_engine_pipeline, live_skip_reason

async def main():
    assert live_skip_reason() is None
    r = await drive_engine_pipeline(
        "app_builder",
        brief="Build a small REST API + minimal UI for a personal task list (add/list/complete).",
        model=None,
    )
    print("completed:", r.completed, "| error:", r.error)
    print("tokens:", r.tokens.as_dict(), "| cost $%.4f" % r.cost_usd())
    out = r.deliverable or ""
    print("has filename: blocks:", "filename:" in out, "| bytes:", len(out))
asyncio.run(main())
'
```
**Produces:** a multi-file `filename:`-block deliverable. **Expect non-zero tokens.** 15 agents →
**potentially the costliest sweep item** — ~$0.10–0.40+. (The related code-gen pipelines
`mulesoft_to_springboot` and `dotnet_to_azure` drive identically — substitute the pipeline name.
They expect **repo-input**; with only a synthetic brief they will produce a thinner deliverable —
flag-and-spot-check rather than gate on completeness.)

---

### 4.4 User Stories (`user_stories`)

6 text-only agents → a backlog document. The cheapest, most deterministic engine pipeline — a
good **first live smoke**.

**(A) pytest** (⏳ planned):
```bash
RUN_LIVE_BEDROCK=1 python3.11 -m pytest tests/agents/test_phase8_live.py -k user_stories -v -s
```

**(B) inline:**
```bash
python3.11 -c '
import asyncio
from tests.agents.live_harness import drive_engine_pipeline, live_skip_reason

async def main():
    assert live_skip_reason() is None
    r = await drive_engine_pipeline(
        "user_stories",
        brief="A mobile app for tracking daily water intake with reminders and a weekly chart.",
        model=None,
    )
    print("completed:", r.completed, "| error:", r.error)
    print("tokens:", r.tokens.as_dict(), "| cost $%.4f" % r.cost_usd())
    print("deliverable bytes:", len(r.deliverable or ""))
asyncio.run(main())
'
```
**Produces:** a non-empty backlog deliverable. **Expect non-zero tokens.** Cheap — ~$0.01–0.03.

---

### 4.5 PPT (`ppt` / `od_ppt`)

3 agents (`od-ppt-brief-analyst → od-ppt-composer → od-ppt-validator`) → a deck deliverable.
Both `ppt` and `od_ppt` resolve to the same agents; `od_ppt` declares `injects`, so pass an
`od_context` for it.

**(A) pytest** (⏳ planned):
```bash
RUN_LIVE_BEDROCK=1 python3.11 -m pytest tests/agents/test_phase8_live.py -k ppt -v -s
```

**(B) inline** (`ppt` — no injects needed):
```bash
python3.11 -c '
import asyncio
from tests.agents.live_harness import drive_engine_pipeline, live_skip_reason

async def main():
    assert live_skip_reason() is None
    r = await drive_engine_pipeline(
        "ppt",
        brief="A 6-slide investor pitch deck for a B2B SaaS that automates expense reports.",
        model=None,
    )
    print("completed:", r.completed, "| error:", r.error)
    print("tokens:", r.tokens.as_dict(), "| cost $%.4f" % r.cost_usd())
    print("deliverable bytes:", len(r.deliverable or ""))
asyncio.run(main())
'
```
For `od_ppt`, swap the pipeline to `"od_ppt"` and pass an `od_context` dict (template/design-system
body) — mirror the prototype `od_context` shape the harness auto-builds.
**Produces:** a deck deliverable. **Expect non-zero tokens.** ~$0.02–0.06.

> **Known caveat (from the plan, §9):** PPT *revision* via the `run_revision` path
> (`engine._handle_revision`) is a **non-agentic stub** — it stores the instruction text as the
> artifact and runs **no** agent. A live `ppt_revision` through that path yields a placeholder,
> not a revised deck. Verify PPT **build** here; treat PPT revision as a known gap, not a failure.

---

### 4.6 Free-chat (`chat`)

Its **own** sequencer (`ChatRunner.astream_execute()`), not the engine — different entry point and
vocabulary (`phase_start` / `stream` / `phase_end` / `complete`). The terminal payload is the
10-key `FinalOutputModel` dict (in `final_output`, not `deliverable`).

**(A) pytest** (⏳ planned):
```bash
RUN_LIVE_BEDROCK=1 python3.11 -m pytest tests/agents/test_phase8_live.py -k chat -v -s
```

**(B) inline** — uses `drive_chat` (not `drive_engine_pipeline`):
```bash
python3.11 -c '
import asyncio
from tests.agents.live_harness import drive_chat, live_skip_reason

async def main():
    assert live_skip_reason() is None
    r = await drive_chat(
        "I want to build an app that helps freelancers track billable hours.",
        mode="default",
        model=None,                                  # real Bedrock
    )
    print("completed:", r.completed, "| error:", r.error)
    print("tokens:", r.tokens.as_dict(), "| cost $%.4f" % r.cost_usd())
    fo = r.final_output or {}
    print("final_output keys (expect 10):", sorted(fo.keys()) if isinstance(fo, dict) else type(fo))
asyncio.run(main())
'
```
**Produces:** the 10-key `FinalOutputModel` dict on the trailing `complete` event. **Expect
non-zero tokens** (captured via the `astream_with_usage` tap the harness installs). ~$0.02–0.08.

---

### 4.7 Handoff (`/flowin-handoff`)

The IDE→PR pipeline (`run_handoff_pipeline()`). The harness **mocks `handoff_github`** (clone /
branch / commit / push / PR are faked, NO real GitHub) and uses a temp local git workspace, but
runs the **real** `build_model()`-backed agents when `model=None`. Terminal payload is the
`pipeline_output` dict (`final_output`); `deliverable` is `None`; tokens are `TokenTotals()` (the
handoff agents are one-shot `ainvoke` calls whose usage is not surfaced as events) — so for
handoff, assert **deliverable validity (the `pipeline_output` shape)**, not tokens.

**(A) pytest** (⏳ planned):
```bash
RUN_LIVE_BEDROCK=1 python3.11 -m pytest tests/agents/test_phase8_live.py -k handoff -v -s
```

**(B) inline** — uses `drive_handoff`:
```bash
python3.11 -c '
import asyncio
from tests.agents.live_harness import drive_handoff, live_skip_reason

async def main():
    assert live_skip_reason() is None
    r = await drive_handoff(
        mode="coding",
        task_description="Add a subtract function next to add().",
        model=None,                                  # real agents; GitHub still mocked
    )
    print("completed:", r.completed, "| error:", r.error, "| raised:", r.raised)
    fo = r.final_output or {}
    print("resolved_mode:", fo.get("resolved_mode"), "| branch:", fo.get("branch_name"), "| pr_url:", fo.get("pr_url"))
asyncio.run(main())
'
```
**Produces:** a `pipeline_complete` event whose `pipeline_output` carries `resolved_mode`,
`branch_name`, `pr_url`, `pr_number`, `test_report`, `compliance_report`. **Tokens are zero by
design** (assert the structured output instead). Cost is small (a few one-shot calls) — ~$0.01–0.03
but not token-reported here. Use `mode="test"` to verify the no-PR path.

---

## 5. HITL on/off

Two **distinct** gate mechanisms (the harness handles both):

### 5.1 Engine inter-agent gate (the user-facing "Review gates")
The engine pauses **between agents** by awaiting the ArtifactStore review event and emits
`review_gate_ready` (`gate_key = f"{run_id}:{agent_id}"`). The default-gated agents (those whose
`AGENT.md` declares `gate: Human_Gate`) are **`prototype-specify`**, **`prototype-plan`**, and
**`clarify-agent`**.

`drive_engine_pipeline(...)` controls this via two params:
- `gate_agent_ids=(...)` — which agents to gate (empty `()` ⇒ no inter-agent gates; a list ⇒ gate
  exactly those ids).
- `auto_resume_gates=True` (default) — auto-approve each gate so a gated run completes;
  `CaptureResult.gated` records that a gate fired.

**Gate-OFF (no pauses):**
```bash
python3.11 -c '
import asyncio
from tests.agents.live_harness import drive_engine_pipeline, live_skip_reason
async def main():
    assert live_skip_reason() is None
    r = await drive_engine_pipeline("user_stories", model=None, gate_agent_ids=())
    print("gated:", r.gated, "| completed:", r.completed)     # expect gated=False
asyncio.run(main())
'
```

**Gate-ON, auto-resume (pause → auto-approve → complete):**
```bash
python3.11 -c '
import asyncio
from tests.agents.live_harness import drive_engine_pipeline, live_skip_reason
async def main():
    assert live_skip_reason() is None
    r = await drive_engine_pipeline(
        "prototype", model=None,
        gate_agent_ids=("prototype-specify", "prototype-plan"),
        auto_resume_gates=True,                       # default; shown for clarity
    )
    print("gated:", r.gated, "| completed:", r.completed)     # expect gated=True, completed=True
asyncio.run(main())
'
```

**Gate-ON, manual resume (explicit pause→resume seam — T3 uses this):** drive with
`auto_resume_gates=False` **as a concurrent task**, wait for `review_gate_ready`, then call
`manual_resume_engine_gate(gate_key, approved=True)`. ⚠️ With `auto_resume_gates=False` and a
single consumer the run BLOCKS at the first gate, so the drive must be consumed **concurrently**
with the resume (the harness docstring spells this out). Prefer the pytest case in
`test_phase8_live.py` for the manual-resume scenario.

### 5.2 Runner tool-level gate (dormant in the engine path)
A standalone `DeepAgentRunner` armed with `interrupt_on={tool: True}` emits a `gate` event and
resumes via `Command(resume={"decisions":[{"type":"approve"}]})`. The harness helpers are
`capture_runner_stream(runner, msg)` → `(events, gate_event)` and `resume_paused_run(runner)`.
The existing, **present** live proof of this seam is:
```bash
RUN_LIVE_BEDROCK=1 python3.11 -m pytest tests/agents/test_deep_agent_runner_hitl_live.py -v -s
```
(Note: that older file's docstring still shows `--profile personal-sso`; for Phase 8 use the
**default** profile and **omit** `AWS_PROFILE`. The `_aws_creds_resolve` preflight inside it works
the same against the default chain.)

---

## 6. Cross-process resume-after-kill (docker Postgres)

In-process resume is already proven; this proves **true crash recovery** — kill the process
mid-run, start a fresh one, resume from the checkpoint. It requires a **Postgres**
`DATABASE_URL` (the checkpointer falls back to `InMemorySaver` for sqlite/anything-else, which
does NOT survive a restart — `app/agents/checkpointer.py`).

### 6.1 Automated (preferred) — `test_phase8_resume.py` (⏳ planned, T4)
This test stands up docker Postgres, points `DATABASE_URL` at it, runs a pipeline to a gate in a
**child process**, kills it, then resumes from the checkpoint in a fresh process — asserting
completion + state continuity. It uses a **scripted model** (no Bedrock), so it is part of the
**offline** gate (it costs $0 on the model; it does need docker running).
```bash
docker info >/dev/null 2>&1 && echo "docker OK"
python3.11 -m pytest tests/agents/test_phase8_resume.py -v
```
> The test manages its own container lifecycle. If it cannot reach docker it should skip with a
> reason (mirroring the live-gate skip pattern). Until it lands, use the manual recipe below.

### 6.2 Manual hands-on verification
Stand up a throwaway Postgres in docker, point the app at it, then do the two-process kill/resume
by hand. The checkpoint thread id is deterministic: same `pipeline_run_id` → same per-agent
`thread_id = f"{run_id}:{agent_id}"`, so a fresh process resumes the SAME run.

```bash
# 1) Start a throwaway Postgres (host port 5433 to avoid clashing with anything on 5432).
docker run -d --name flowin-pg-resume \
  -e POSTGRES_PASSWORD=flowin -e POSTGRES_USER=flowin -e POSTGRES_DB=flowin \
  -p 5433:5432 postgres:16

# wait for it to accept connections
until docker exec flowin-pg-resume pg_isready -U flowin >/dev/null 2>&1; do sleep 1; done
echo "postgres ready"

# 2) Point the app at it. AsyncPostgresSaver.setup() creates the checkpoint tables on first use.
export DATABASE_URL="postgresql://flowin:flowin@localhost:5433/flowin"
export ENV=development
export RUNS_ROOT=/tmp/flowin-live-runs && mkdir -p "$RUNS_ROOT"
# For a LIVE-model resume also: export RUN_LIVE_BEDROCK=1   (omit to resume a scripted run)
```

Process A — run to a gate and **kill** before it completes (a gated prototype run pauses at
`prototype-specify`). With Postgres wired (`DATABASE_URL` postgres), the checkpoint persists past
the kill:
```bash
# Pick a FIXED run id so process B can resume the same threads.
export RESUME_RUN_ID="resume-demo-001"

# Drive in the background, let it reach the first gate, then kill the process group.
python3.11 -c '
import asyncio, os
from tests.agents.live_harness import drive_engine_pipeline
async def main():
    await drive_engine_pipeline(
        "prototype",
        run_id=os.environ["RESUME_RUN_ID"],
        gate_agent_ids=("prototype-specify",),
        auto_resume_gates=False,            # leave the gate OPEN so the run is mid-flight
        model=None,                          # or a scripted model for a $0 demo
    )
asyncio.run(main())
' &
APID=$!
sleep 25            # give it time to checkpoint at the gate (tune as needed)
kill -9 $APID ; echo "killed process A (pid $APID)"
```

Process B — fresh process, SAME run id + SAME Postgres → resume from the checkpoint. The
durable state (and the run's sandbox on disk) survive; the engine's `get_checkpointer()` returns
the `AsyncPostgresSaver` and the per-agent threads continue. Drive B with `auto_resume_gates=True`
so it approves the pending gate and runs to completion:
```bash
python3.11 -c '
import asyncio, os
from tests.agents.live_harness import drive_engine_pipeline
async def main():
    r = await drive_engine_pipeline(
        "prototype",
        run_id=os.environ["RESUME_RUN_ID"],   # SAME id → SAME thread_ids → resume
        gate_agent_ids=("prototype-specify",),
        auto_resume_gates=True,
        model=None,
    )
    print("resumed completed:", r.completed, "| error:", r.error)
asyncio.run(main())
'
```

> NOTE: this manual recipe is a **best-effort** illustration of the cross-process mechanics; the
> authoritative, deterministic proof is the committed `test_phase8_resume.py` (T4), which controls
> the kill point precisely via a subprocess runner. Use the manual recipe to build intuition, the
> test to gate.

Teardown:
```bash
docker rm -f flowin-pg-resume
unset DATABASE_URL RESUME_RUN_ID
```

---

## 7. Cost watch

### 7.1 Reading the per-run token/cost summary
Every drive returns a `CaptureResult` with token totals and a cost accessor (Haiku pricing baked in):
```python
r = await drive_engine_pipeline("user_stories", model=None)
print(r.tokens.as_dict())     # {"input": ..., "output": ..., "total": ...}
print(r.cost_usd())           # USD at $0.25/M in + $1.25/M out
print(r.per_agent_tokens)     # {agent_id: TokenTotals(...)} — attribute spend per agent
```
Module-level math (accepts a `TokenTotals` or a plain dict):
```python
from tests.agents.live_harness import cost_usd
cost_usd({"input": 1_000_000, "output": 1_000_000})   # -> 1.50
```
The **T2 `live_contract.summarize_cost(...)`** printer (a token/cost summary with a soft ceiling)
is **planned** — until it lands, the `cost_usd()` helpers above give you the same numbers. When
T3 runs are invoked with `-s`, the per-run summary prints to stdout.

### 7.2 Rough per-pipeline cost (Haiku 4.5, single live run)
Order-of-magnitude only — live token counts vary with brief + model nondeterminism. Treat as
ceilings-to-watch, not guarantees.

| Pipeline | Entry | Rough cost / run | Notes |
|---|---|---|---|
| `user_stories` | `drive_engine_pipeline` | ~$0.01–0.03 | 6 text agents; cheapest engine smoke |
| `chat` | `drive_chat` | ~$0.02–0.08 | multi-phase; 10-key final dict |
| `ppt` / `od_ppt` | `drive_engine_pipeline` | ~$0.02–0.06 | 3 agents |
| `prototype_revision` | `drive_engine_pipeline` | ~$0.01–0.05 | 1 agent + bounded fix-loop |
| `prototype` (build) | `drive_engine_pipeline` | ~$0.05–0.20 | per-task sub-agents + validate/fix loops |
| `app_builder` | `drive_engine_pipeline` | ~$0.10–0.40+ | 15 agents — costliest |
| `mulesoft_to_springboot` / `dotnet_to_azure` | `drive_engine_pipeline` | ~$0.10–0.40+ | 13 agents each; repo-input (thin on synthetic brief) |
| `/flowin-handoff` | `drive_handoff` | ~$0.01–0.03 (not token-reported) | a few one-shot calls; GitHub mocked |

### 7.3 Suggested ceiling for the full sweep
A single pass over the **headline** pipelines (prototype build + revision, app_builder,
user_stories, ppt, chat, handoff) is comfortably **under ~$1.00**. Add the two large code-gen
migration pipelines and re-runs for nondeterminism and budget **~$2–3 total**. **Suggested hard
ceiling: $5** for an exploratory sweep — if you blow past it, something is looping (check the
`recursion_limit=400` backstop and the validate-fix loops). The cheap `user_stories` smoke first
is the cost-safe way to confirm creds + Bedrock access before launching the expensive runs.

---

## 8. Troubleshooting

**Live tests all SKIP (`RUN_LIVE_BEDROCK!=1 …`).** You did not opt in. `export RUN_LIVE_BEDROCK=1`.
The skip message (from `live_skip_reason()` / `_RUN_LIVE_HINT`) prints the exact command.

**Expired SSO / creds don't resolve** (`AWS credentials did not resolve: …ExpiredToken…` /
`SSOTokenLoadError`). The default-profile SSO session lapsed. Refresh:
```bash
aws sso login
aws sts get-caller-identity      # confirm acct 473293451041 / ImranY@hexaware.com
```
The harness skips cleanly (doesn't error) when creds are missing — re-run after refreshing.

**`ANTHROPIC_API_KEY` accidentally set → run hits Anthropic, NOT Bedrock.** This is the silent
trap: `live_skip_reason()` treats a configured key as "a usable provider" and returns `None`
(not skipped), but `build_model()` then builds `ChatAnthropic`, so you'd be billing Anthropic and
**not** verifying Bedrock. Confirm it's empty in **both** the shell and `backend/.env`:
```bash
echo "[$ANTHROPIC_API_KEY]"      # must be []
grep -n ANTHROPIC_API_KEY .env || echo "not in .env (good)"
unset ANTHROPIC_API_KEY
```
Comment the line out of `.env` for the duration of the Bedrock verification.

**`ModelConfigurationError: No LLM configured`.** Both providers are unset — `ANTHROPIC_API_KEY`
empty AND `BEDROCK_INFERENCE_PROFILE_ID`/`AWS_REGION` empty. The defaults in `config.py` cover
the Bedrock case; if a `.env` blanked them, restore (or export) `BEDROCK_INFERENCE_PROFILE_ID=eu.anthropic.claude-haiku-4-5-20251001-v1:0`
and `AWS_REGION=eu-central-1`.

**Bedrock `AccessDeniedException` / model not found.** The IAM identity lacks Bedrock invoke on
the Haiku profile, or the model isn't enabled in the region. Verify availability:
```bash
aws bedrock list-foundation-models --region eu-central-1 \
  | grep -i "claude-haiku-4-5" || echo "Haiku 4.5 not listed — request access in the Bedrock console"
```
(Phase-8 fact: Haiku 4.5 IS accessible in `eu-central-1` for the default profile right now.)

**Docker not running** (resume test). `docker info` fails / `Cannot connect to the Docker daemon`.
Start Docker Desktop; the resume test/recipe needs it (native Postgres is absent). The offline
self-tests and the per-pipeline live runs do **not** need docker.

**Resume "completes immediately" / no resume happens.** Almost always `DATABASE_URL` is **not**
Postgres, so the checkpointer is `InMemorySaver` and state didn't survive the kill (the
checkpointer logs a warning to this effect). Confirm `DATABASE_URL` starts with `postgresql://`
and points at your docker container, and that you reused the **same** `run_id` in both processes.

**`render_check` / Chromium missing.** `render_check` runs headless Chromium for real locally and
**degrades to a skip** if the browser is unavailable — a prototype run still completes (validation
just skips the render leg). To enable real render validation install the Playwright browser:
```bash
python3.11 -m playwright install chromium
```

**`RUNS_ROOT` not writable** (`PermissionError` under `/app/runs`). The default `RUNS_ROOT` is
the container path `/app/runs`, which does not exist locally. Export a writable dir before any
run: `export RUNS_ROOT=/tmp/flowin-live-runs && mkdir -p "$RUNS_ROOT"`. (The harness also forces a
temp `RUNS_ROOT` internally, but being explicit avoids surprises if you call production code paths
directly.)

**`ModuleNotFoundError: frontmatter`.** The agent loader's one missing dep:
`python3.11 -m pip install --user python-frontmatter`.

**Wrong interpreter** (`ModuleNotFoundError` for langchain/fastapi, or `python: command not found`).
Use `python3.11` explicitly — `python`/`python3` are the wrong runtimes (no venv).

---

## 9. Full-sweep checklist (copy-paste)

Run top-to-bottom: offline (free) → one cheap smoke → all pipelines → resume. Check each box.

```bash
cd /Users/1000060523/Documents/Work/UKI/Flowin/flowin/backend
```

**Prereqs**
- [ ] `python3.11 --version` → 3.11.x
- [ ] `aws sts get-caller-identity` → acct `473293451041` (else `aws sso login`)
- [ ] `echo "[$ANTHROPIC_API_KEY]"` → `[]` (empty); not set in `.env`
- [ ] `docker info` → OK (only needed for the resume step)

**Offline (zero cost) — must be green first**
- [ ] `python3.11 -m pytest tests/agents/test_live_harness.py -v`  *(present)*
- [ ] `python3.11 -m pytest tests/agents/test_live_contract.py -v`  *(planned — skip if absent)*
- [ ] `python3.11 -m pytest tests/agents/test_phase8_resume.py -v`  *(planned; needs docker; scripted model = $0)*

**Flip live**
- [ ] `export RUN_LIVE_BEDROCK=1 ENV=development RUNS_ROOT=/tmp/flowin-live-runs && mkdir -p "$RUNS_ROOT"`
- [ ] (defensive) `unset ANTHROPIC_API_KEY; unset AWS_PROFILE`

**One cheap live smoke (confirms creds + Bedrock before the expensive runs)**
- [ ] `user_stories` — inline snippet §4.4 (or `pytest test_phase8_live.py -k user_stories -v -s`) → completed, tokens > 0, cost printed

**All pipelines (each: completed, non-zero tokens [except handoff], valid deliverable)**
- [ ] `user_stories`  (§4.4)
- [ ] `prototype` build  (§4.1)
- [ ] `prototype_revision`  (§4.2 — revise the build's run_id)
- [ ] `app_builder`  (§4.3)
- [ ] `ppt` / `od_ppt`  (§4.5)  *(PPT revision is a known stub — skip)*
- [ ] `chat`  (§4.6 — `drive_chat`)
- [ ] `/flowin-handoff`  (§4.7 — `drive_handoff`, GitHub mocked; assert `pipeline_output` shape, not tokens)
- [ ] *(optional)* `mulesoft_to_springboot`, `dotnet_to_azure` (§4.3 — spot-check; repo-input pipelines)

**HITL**
- [ ] gates-off: `gate_agent_ids=()` → `gated=False` (§5.1)
- [ ] gates-on auto-resume: `gate_agent_ids=("prototype-specify","prototype-plan")` → `gated=True`, `completed=True` (§5.1)
- [ ] runner tool-level gate: `pytest test_deep_agent_runner_hitl_live.py -v -s` (present) (§5.2)

**Cross-process resume-after-kill**
- [ ] automated: `pytest tests/agents/test_phase8_resume.py -v` (planned) OR
- [ ] manual: docker Postgres + two-process kill/resume (§6.2) → "resumed completed: True"

**Cost**
- [ ] full headline sweep total under the ~$1 expectation; nothing exceeded the **$5** ceiling
- [ ] teardown: `docker rm -f flowin-pg-resume` (if used); `unset RUN_LIVE_BEDROCK DATABASE_URL`
```
