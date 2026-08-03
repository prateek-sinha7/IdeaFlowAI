# Harbor for VELOCITY-AI agent evals — feasibility report

**Date:** 2026-07-31 · **Harbor version tested:** 0.20.0 (Apache-2.0)
**Verdict:** Adopt for *execution*, keep our own *judging*. A hybrid, not a replacement.
**Podman works** — verified end-to-end with a real containerized trial (§4).

Everything below was verified by installing and running Harbor in
`backend/evals/harbor/.venv`, not read off a landing page. Where I could not
verify something it is marked **UNVERIFIED**.

---

## 1. What Harbor actually is

A framework from the Terminal-Bench authors for running agents against tasks in
**isolated containers** and scoring them with a **verifier**. LangChain has
integrated it across LangSmith, Sandboxes, and Deep Agents, and it is what
powers Terminal-Bench 2.0.

The unit of work is a **task** — a directory, not a config entry:

```
prototype-specify/
├── instruction.md          # the prompt handed to the agent
├── task.toml               # timeouts, network policy, resources, verifier env
├── environment/Dockerfile  # the container the agent works inside
├── solution/solve.sh       # reference solution (the "oracle" agent runs it)
└── tests/test.sh           # verifier — writes /logs/verifier/reward.txt
```

A **trial** is one execution of one task. The verifier writes a scalar to
`reward.txt`, or multiple named metrics to `reward.json` (Harbor prefers the
latter). The agent contract is four methods:

```python
class BaseAgent:
    def name(self): ...
    def version(self): ...
    def setup(self): ...
    def run(self, instruction: str, environment: BaseEnvironment,
            context: AgentContext) -> None: ...
```

Anything satisfying that can be evaluated — the CLI ships ~25 built-in agents
(claude-code, codex, aider, cursor-cli, gemini-cli, …) and accepts
`module.path:ClassName` for your own.

Environments are pluggable the same way: `docker` (default), `apple-container`,
`langsmith`, `modal`, `daytona`, `e2b`, `blaxel`, `ec2`, `gke`, `skypilot`, and
others.

---

## 2. Why this is worth taking seriously

Look at what we hand-built in `evals/minimal` — **2,544 lines of Python plus a
760-line JS report** — and how much of it is *plumbing* rather than judgement:

| What we wrote | What Harbor gives free |
|---|---|
| `store.py` — run dirs, phases, JSONL call log | job/trial storage, `harbor job/trial` CLI |
| `run.py` sandbox seeding + dispatch | container per trial, task files staged in |
| serial dispatch loop | `-n` concurrent trials |
| no rate-limit retry on dispatch (a real gap — a 429 kills a row) | concurrency caps, per-agent caps, timeouts |
| `report.py` + `report.js` + `report.css` (~1,500 lines) | LangSmith experiments UI |
| `checks.py` invoking local Chromium | verifier runs in the container, Chromium pinned in the image |
| token/cost accounting | `input`/`cache`/`output` + `cost_usd` per trial |

Three of this week's actual bugs would not have existed under Harbor: the
report.js function-splicing regressions (three times), the undefined CSS
variables, and the missing dispatch entry in `calls.jsonl`. That is not a small
observation — most of the maintenance pain has been in the reporting layer we
own, not in the evaluation logic that is genuinely ours.

The LangSmith plugin (`--plugin langsmith`) syncs each job as a dataset +
experiment, one root run per trial with child runs for environment / agent /
verification, verifier rewards as feedback, and token+cost outputs. Our runtime
is already `deepagents`/LangGraph, so traces attach natively.

---

## 3. Where Harbor does *not* fit

**It has no rubric judge.** Harbor's own docs redirect multi-criterion and
LLM-as-judge scoring to a separate project ("Reward Kit"). Our
`judge.py` — 5 rubrics, per-dimension 0–100, severity-priced findings
(`blocking=45 / major=18 / minor=4`), incomplete-dimension retry — has no
counterpart. A verifier *can* make an LLM call and emit multiple keys in
`reward.json`, so this is portable, but it is a port, not a feature we inherit.

**It has no advisor.** The prompt-edit suggestion loop and its
`OPEN`/`SUPERSEDED` provenance is entirely ours.

**It has no prompt-version concept.** `activate.sh`, the `.vN.md` files, the
override store and `system_prompt_hash` provenance stay exactly as they are.
Harbor would not know a prompt changed.

**One reward per trial, not per stage.** Our five-stage chain is judged
stage-by-stage. Harbor's natural unit is one task → one verdict. Two ways out,
both viable:
- one task per `(row, stage)`, upstream artifacts staged into the container —
  mirrors our existing `--stage X --from RUN_ID` model closely; or
- one task per row with `reward.json` carrying per-stage keys.

**Python 3.12+.** Harbor will not install on 3.11, which is the backend's
interpreter. Verified: `pip index versions harbor` finds nothing on 3.11, works
on 3.12 and 3.13. This is fine — the eval harness does not need to share the
backend's interpreter — but it means a separate venv forever.

---

## 4. Podman — SOLVED, and verified end-to-end

Harbor has no podman backend, but it does not need one. It **shells out to a
`docker` binary** rather than using the Docker SDK — `docker.py:154` gates on
`shutil.which("docker")` and every operation is a `subprocess` call. Podman is
CLI-compatible for all of them, so a three-line shim is sufficient. **No Docker
Desktop, no system install.**

`bin/docker`:

```bash
#!/usr/bin/env bash
if [[ "$1" == "info" && "$*" == *"{{.OSType}}"* ]]; then
  exec podman info --format '{{.Host.OS}}'      # podman has no .OSType field
fi
exec podman "$@"
```

Only one call needed translating: Harbor's `_detect_daemon_os()` runs
`docker info --format {{.OSType}}`, which podman's info schema does not have.
Harbor tolerates the failure (returns `None`), but translating it keeps the
linux/windows check meaningful. `docker compose` and `docker manifest inspect`
— the other two things Harbor uses — work through the shim untouched.

To run:

```bash
export PATH="$PWD/bin:$PWD/.venv/bin:$PATH"
export DOCKER_HOST="unix://$(podman machine inspect \
  --format '{{.ConnectionInfo.PodmanSocket.Path}}')"
harbor run -p prototype-specify --agent oracle -n 1
```

### Verified results

A real task was authored here — `velocity/prototype-specify`, carrying our
actual `warehouse_slotting` brief from `evals/minimal/datasets/small.json`.
`specify` was chosen over `build` deliberately: it is the head of the chain, so
it needs no upstream artifacts staged into the container, whereas `build`
consumes `spec.md` + `tasks.md` + `analysis.md` and would have conflated the
"does Harbor work" question with the "can we stage upstream state" question.

Run on podman, both directions:

| agent | Trials | Exceptions | Reward | Page_Coverage | Words | Has_Route_Pattern | Has_Tables | Missing_Artifact |
|---|---|---|---|---|---|---|---|---|
| `oracle` (reference spec) | 1 | 0 | **1.000** | 1.000 | 423 | 1.000 | 1.000 | 0 |
| `nop` (does nothing) | 1 | 0 | **0.000** | 0.000 | 0 | 0.000 | 0.000 | 1.000 |

22 seconds per trial including image build. **Multi-metric `reward.json`
works** — every key became its own aggregate column, which is what makes
per-dimension scoring viable at all.

### What choosing `specify` exposed — the core finding

`specify` emits **prose**. It has no render gate; in `evals/minimal` its checks
column literally reads `checks n/a`. So the strongest deterministic verifier
that can be written for it is a **coverage floor**: were all six briefed pages
named, is the `#/sku/:id` route pattern preserved, are there tables, is it long
enough to be a spec at all.

That floor is real and worth having — but note what it cannot see. Our
`prototype-specify` scored **94.8 in six of seven runs** on the rubric judge
while the chain downstream of it failed the render gate 6/7 times. A coverage
floor would have scored those same specs 1.0 without hesitation.

**This is the argument for the hybrid, made concrete.** Harbor gives us
execution, isolation, parallelism, and a trustworthy deterministic floor. It
does not and will not tell us whether a spec is *good*. Three of our five
stages (specify, plan, analyze) produce prose and have no deterministic gate
whatsoever — for those, `judge.py` is not a nice-to-have we could drop during a
migration, it is the only signal that exists.

### The one non-obvious verifier rule

The first version of the verifier *crashed* on the missing artifact instead of
scoring zero. Harbor counted the trial as `Trials: 0, Exceptions: 1` —
the failure **vanished from the aggregate rather than dragging it down**. A
verifier must catch its own exceptions and always write `reward.json`:

```python
try:
    result = measure()
except Exception as exc:
    result = {"reward": 0.0, "verifier_error": 1.0, "error": str(exc)[:200]}
(out / "reward.json").write_text(json.dumps(result))
```

This matters directly for us: porting `static_check`/`render_check` into a
verifier means any import error, missing Chromium, or malformed HTML must score
0 rather than raise, or a broken build will silently improve the mean.

**Corporate TLS interception.** `pip install harbor` fails during `litellm`
metadata generation with `CERTIFICATE_VERIFY_FAILED: self-signed certificate in
certificate chain`. The fix is `--prefer-binary` (litellm publishes a universal
wheel; pip had backtracked to an sdist whose build hook makes a network call).
Recorded because it will bite again on any rebuild:

```bash
python3.13 -m venv .venv
./.venv/bin/pip install --prefer-binary harbor      # NOT plain `pip install harbor`
```

**Our pipeline is engine-orchestrated, not a single graph.**
`--agent langgraph` expects a `langgraph.json` exposing one graph. Ours is
`ExecutionEngine` driving five agents with typed `produces`/`consumes` routing,
plus a per-task sub-agent build loop with its own validation fix-loop. So the
integration is a **custom `BaseAgent`** that calls `ExecutionEngine`, not the
built-in langgraph adapter. Four methods, but it must thread model selection,
the run sandbox, and the prompt-override user id through.

---

## 5. Recommendation

**Adopt Harbor for execution and observability. Keep `judge.py`, the advisor,
and the prompt-versioning exactly as they are.**

Concretely, what would be deleted vs kept:

| Keep (ours, the actual value) | Replace with Harbor |
|---|---|
| `judge.py` — rubrics, severity pricing | `run.py` dispatch + sandbox |
| advisor + `advices.json` + provenance | `store.py` |
| `prompts/activate.sh`, `.vN.md`, hashes | `report.py` / `report.js` / `report.css` |
| `rubrics/*.yaml` | `checks.py` → becomes `tests/test.sh` |
| `configs/*.yaml` datasets → Harbor tasks | `cli.py` orchestration |

That deletes roughly **1,900 of 2,544 Python lines** plus the whole JS report,
and buys parallelism, isolation, retries, and a maintained UI.

### But do not start this now

Two reasons, both from this week's evidence:

1. **We have an open, unanswered question that Harbor does not help with.**
   `build` failed the render gate 6/7 runs and `validate` *regressed* working
   output twice, on byte-identical prompts. That is a model-capability question.
   Migrating the harness while the thing under test is unresolved means changing
   two variables at once.

2. **The migration's own risk is the checks.** `static_check` and `render_check`
   are production modules we import directly. Inside a Harbor container they
   become a `test.sh` invoking a pinned image. That is *better* — but it is the
   part most likely to silently change behaviour, and it is currently the only
   ground truth we have.

### Suggested sequencing

1. Finish the `mistral-large-latest` build comparison — decide the capability
   question first.
2. ~~Spike one Harbor task~~ — **DONE**, see §4. `velocity/prototype-specify`
   runs green on podman with a coverage-floor verifier. The next spike is the
   one that actually de-risks the migration: `velocity/prototype-build`, whose
   verifier calls the real `static_check` + `render_check` in the container and
   emits `{render_ok, static_ok, dead_links}` — then check it agrees with
   `evals/minimal`'s verdict on the same HTML. That needs upstream artifacts
   (`spec.md`/`tasks.md`/`analysis.md`) staged into the environment, which is
   the genuinely unproven part.
3. Only if (2) agrees: write the `ExecutionEngine` `BaseAgent` adapter and port
   the judge into a verifier.

Steps 1 and 2 are each roughly a day. Step 3 is the real project.

---

## 6. What is in this folder

```
evals/harbor/
├── REPORT.md                        # this file
├── .venv/                           # python3.13 + harbor 0.20.0 (gitignored, 231MB)
├── bin/docker                       # podman shim — the whole podman story
├── jobs/                            # results from the two verified runs
└── prototype-specify/               # a REAL working task, not a scaffold
    ├── instruction.md
    ├── task.toml
    ├── environment/Dockerfile        # python:3.12-slim
    ├── solution/solve.sh             # oracle's reference spec
    └── tests/{test.sh,test_outputs.py}   # coverage floor -> reward.json
```

Nothing here is wired into the backend. `evals/minimal` is untouched.

To reproduce:

```bash
cd backend/evals/harbor
export PATH="$PWD/bin:$PWD/.venv/bin:$PATH"
export DOCKER_HOST="unix://$(podman machine inspect \
  --format '{{.ConnectionInfo.PodmanSocket.Path}}')"

harbor run -p prototype-specify --agent oracle -n 1  # expect reward 1.0
harbor run -p prototype-specify --agent nop    -n 1  # expect reward 0.0
harbor view jobs                                     # trajectory browser
```

Requires `podman machine start` first.

## Sources

- https://github.com/harbor-framework/harbor
- https://www.harborframework.com/docs/tasks
- https://docs.langchain.com/langsmith/harbor-integrations
- https://www.langchain.com/blog/unified-stack-for-evaluating-agents
