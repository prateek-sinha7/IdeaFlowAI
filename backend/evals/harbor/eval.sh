#!/usr/bin/env bash
# One command for the full Harbor loop: compose the real prompt, dispatch it in
# a container, code-grade the artifact, then model-grade it.
#
#   ./eval.sh                          # specify: real agent + Mistral, all graders
#   ./eval.sh --stage plan             # plan, seeded from the newest spec
#   ./eval.sh --stage plan --from 2026-08-01__01-10-06
#   ./eval.sh --scenario mission-control    # the harder brief (7 pages, 2 dynamic routes)
#   ./eval.sh --agent oracle           # canned output, no tokens (plumbing test)
#   ./eval.sh --model mistral/mistral-large-latest
#   ./eval.sh --no-judge               # code grade only — free
#   ./eval.sh -n 3                     # three trials
#
# A run is one point on a STAGE x SCENARIO grid; the task directory it uses is
# named "<scenario>-<stage>" and is assembled by sync_common.sh in step 2.
# `harbor tasks list` shows what is available.
#
# Mirrors evals/minimal/eval.sh: prints each step, exits non-zero on failure,
# and names the artifacts at the end so the next command is obvious.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$(cd "$HERE/../.." && pwd)"
STAGE="specify"
SCENARIO="warehouse-slotting"
FROM_JOB=""

AGENT="velocity_agent:VelocityAgent"
MODEL="mistral/mistral-small-latest"
TRIALS=1
JUDGE=true

while [[ $# -gt 0 ]]; do
  case "$1" in
    --stage)    STAGE="$2"; shift 2 ;;
    --scenario) SCENARIO="$2"; shift 2 ;;
    --from)     FROM_JOB="$2"; shift 2 ;;
    --agent)    AGENT="$2"; shift 2 ;;
    --model)    MODEL="$2"; shift 2 ;;
    -n|--trials) TRIALS="$2"; shift 2 ;;
    --no-judge) JUDGE=false; shift ;;
    -h|--help)  sed -n '2,21p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "unknown flag: $1" >&2; exit 1 ;;
  esac
done

if [[ ! -d "$HERE/scenarios/$SCENARIO" ]]; then
  echo "unknown scenario: $SCENARIO — available:" >&2
  ls "$HERE/scenarios" | sed 's/^/    /' >&2
  exit 1
fi

# The AGENT id stays stage-named — it is the production agent under test
# (agents/prompts/prototype-specify/AGENT.md) and does not vary by scenario.
# Only the TASK directory carries the scenario.
TASK="$SCENARIO-$STAGE"
case "$STAGE" in
  specify)
    AGENT_ID="prototype-specify"
    export VELOCITY_DELIVERABLE="/app/spec.md"
    ;;
  plan)
    AGENT_ID="prototype-plan"
    export VELOCITY_DELIVERABLE="/app/tasks.md"
    export VELOCITY_UPSTREAM_AS="spec.md"
    # `plan` consumes `prototype-specify`, so it cannot run without one.
    # Default to the newest spec on disk rather than silently planning from
    # nothing — a plan with no spec still produces plausible output, which is
    # the worst kind of wrong.
    #
    # The glob is pinned to THIS scenario's specify trials. Seeding a
    # mission-control plan from a warehouse-slotting spec would run and score,
    # just against the wrong product — and before scenarios existed, "newest
    # spec anywhere" was the only option.
    if [[ -n "$FROM_JOB" ]]; then
      UPSTREAM="$(ls "$HERE/jobs/$FROM_JOB/$SCENARIO-specify"*/artifacts/app/spec.md 2>/dev/null | head -1)"
      [[ -z "$UPSTREAM" ]] && echo "job $FROM_JOB has no $SCENARIO-specify trial" >&2
    else
      UPSTREAM="$(ls -t "$HERE"/jobs/*/"$SCENARIO-specify"*/artifacts/app/spec.md 2>/dev/null | head -1)"
    fi
    if [[ -z "$UPSTREAM" ]]; then
      echo "no upstream spec.md for '$SCENARIO' — run './eval.sh --scenario $SCENARIO' first, or pass --from <job>" >&2
      exit 1
    fi
    export VELOCITY_UPSTREAM="$UPSTREAM"
    echo "==> upstream: ${UPSTREAM#"$HERE"/}" >&2
    ;;
  *) echo "unknown stage: $STAGE (specify|plan)" >&2; exit 1 ;;
esac
export VELOCITY_TASK_DIR="$HERE/$TASK"

# MISTRAL_API_KEY does not survive into non-login shells; without it every call
# 401s and it reads like a quota problem rather than a missing env var.
#
# The key is GREPPED out of ~/.zshrc rather than sourced. Sourcing a zsh rc file
# from bash kills the script outright — zsh-only syntax is a bash parse error,
# and `|| true` cannot catch it because bash aborts before the operator is
# reached. This was the first thing that broke here.
if [[ -z "${MISTRAL_API_KEY:-}" && -f "$HOME/.zshrc" ]]; then
  MISTRAL_API_KEY="$(sed -n 's/^[[:space:]]*export[[:space:]]\{1,\}MISTRAL_API_KEY=["'"'"']\{0,1\}\([^"'"'"']*\)["'"'"']\{0,1\}.*/\1/p' "$HOME/.zshrc" | tail -1)"
  export MISTRAL_API_KEY
fi

export PATH="$HERE/bin:$HERE/.venv/bin:$PATH"   # bin/docker shims podman
export PYTHONPATH="$HERE"

if ! podman machine inspect >/dev/null 2>&1; then
  echo "podman machine is not running — run: podman machine start" >&2
  exit 1
fi
DOCKER_HOST="unix://$(podman machine inspect --format '{{.ConnectionInfo.PodmanSocket.Path}}')"
export DOCKER_HOST

# ── 1. Compose the REAL prompt, every run ────────────────────────────────
# Not cached: the composed prompt changes whenever an override is activated or
# AGENT.md is edited, and a stale copy would silently evaluate a prompt that is
# no longer live. The sha is written beside it and becomes the agent's version
# string, so a trial's result is attributable to exact prompt bytes.
echo "==> prompt: composing $AGENT_ID from AGENT.md (+ any active override)" >&2
python3.11 - "$HERE" "$AGENT_ID" "$TASK" <<'PY'
import pathlib, sys
sys.path.insert(0, str(pathlib.Path(sys.argv[1]).parents[1]))
from evals.minimal import run
here, agent_id, task = pathlib.Path(sys.argv[1]), sys.argv[2], sys.argv[3]
body = run.compose_agent_prompt(agent_id)
digest = run._hash_prompt(body)
out = here / task / "agent"
out.mkdir(parents=True, exist_ok=True)
(out / "system_prompt.md").write_text(body, encoding="utf-8")
(out / "system_prompt.sha").write_text(digest, encoding="utf-8")
print(f"    {len(body)} chars  {digest[:26]}", file=sys.stderr)
PY

"$BACKEND/evals/minimal/prompts/activate.sh" status 2>/dev/null | sed 's/^/    /' >&2 || true

# ── 2. Sync shared verifier machinery, then dispatch ─────────────────────
# common/ is the source of truth; Harbor can only copy a task's OWN tests/ and
# environment/ into the container, so the shared files are physically copied in
# before each run. Doing it here means editing common/ needs nothing remembered.
echo "==> sync: common/ x scenarios/ -> each task" >&2
"$HERE/sync_common.sh"

echo "==> run: $TASK (scenario $SCENARIO, stage $STAGE) via $AGENT ($MODEL) x$TRIALS" >&2
cd "$HERE"
harbor run -p "$TASK" --agent "$AGENT" --model "$MODEL" -n "$TRIALS"

JOB="$(ls -t jobs | head -1)"
TRIAL="$(ls "jobs/$JOB" | grep "$TASK" | head -1)"
echo "==> job: jobs/$JOB" >&2

# A trial that raised leaves no reward.json. Fail loudly rather than letting the
# judge run against an artifact that was never produced.
if [[ ! -f "jobs/$JOB/$TRIAL/verifier/reward.json" ]]; then
  echo "FAILED: no reward.json — the trial errored. Detail:" >&2
  tail -5 "jobs/$JOB/$TRIAL/exception.txt" 2>/dev/null >&2
  exit 1
fi

if [[ "$JUDGE" != true ]]; then
  echo "==> code grade only (--no-judge)" >&2
  cat "jobs/$JOB/$TRIAL/verifier/reward.json"
  exit 0
fi

# ── 3. Model grade — the rubric judge (host: judge.py needs python3.11) ──
# specify only for now: model_grade.py reads artifacts/app/spec.md and the
# specify rubric. Saying so beats silently grading the wrong artifact.
if [[ "$STAGE" == "specify" ]]; then
  echo "==> judge: evals/minimal/judge.py over the collected artifact" >&2
  cd "$BACKEND"
  PYTHONPATH="$BACKEND" python3.11 evals/harbor/model_grade.py "$HERE/jobs/$JOB"
else
  echo "==> judge: skipped — model_grade.py is specify-only so far" >&2
fi

# ── 4. Spec grade — facts extracted by model, contradictions found by python ──
# Runs on the harbor venv, not python3.11: it needs litellm and a pydantic
# response_format, which live in .venv. This is the grader that catches
# cross-page value conflicts; the rubric judge above scored a spec 94.4 while
# the same SKU carried two different on-hand figures.
cd "$HERE"
if [[ "$STAGE" == "specify" ]]; then
  echo "==> spec judge: fact extraction + contradiction detection" >&2
  ./.venv/bin/python spec_judge.py "jobs/$JOB/$TRIAL/artifacts/app/spec.md"
else
  echo "==> spec judge: skipped — specify-only so far" >&2
fi

# ── 5. Publish both host-side grades into the viewer ─────────────────────
# `harbor view` only renders verifier_result.rewards from result.json, and the
# host-side graders write sibling files it has never heard of. Without this the
# UI shows the code grade alone and the run looks green.
echo "==> publish: merging grades into result.json for harbor view" >&2
python3.11 publish_grades.py "$HERE/jobs/$JOB" >/dev/null

echo >&2
echo "==> artifacts (all inside the TRIAL folder, not the job root)" >&2
for f in "jobs/$JOB/$TRIAL/artifacts/app"/*; do
  [[ -e "$f" ]] && echo "    artifact    : evals/harbor/$f" >&2
done
for f in model_grade.json spec_judge.json; do
  [[ -f "jobs/$JOB/$TRIAL/$f" ]] && echo "    grade       : evals/harbor/jobs/$JOB/$TRIAL/$f" >&2
done
echo "    next stage  : ./eval.sh --scenario $SCENARIO --stage plan --from $JOB" >&2
echo "    viewer      : (cd evals/harbor && harbor view jobs) -> http://127.0.0.1:8080" >&2
