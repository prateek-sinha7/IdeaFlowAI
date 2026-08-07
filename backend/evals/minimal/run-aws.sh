#!/usr/bin/env bash
# run-aws.sh — ONE COMMAND: preflight, dispatch on AWS Bedrock stage by stage,
# judge everything that completed, rebuild the report. The closing run.
#
#   evals/minimal/run-aws.sh                                  # prototype, 1 row, 5 stages
#   evals/minimal/run-aws.sh configs/ppt_smoke_bedrock.yaml   # the deck workflow
#   THINKING_BUDGET_TOKENS=0 evals/minimal/run-aws.sh         # thinking off for this run
#   DRY_RUN=1 evals/minimal/run-aws.sh                        # preflight only, spend nothing
#
# WHY BEDROCK: every prototype run that has ever completed here was dispatched
# on Bedrock claude-haiku-4-5 (265 stage-completions in the run store);
# mistral-small has never once finished a `build`. Bedrock is also a different
# provider from the judge (mistral-large), so the model under test never grades
# its own output.
#
# THE PREFLIGHT IS THE POINT. AWS_BEARER_TOKEN_BEDROCK is a short-lived STS
# session token that has expired mid-run three times in this project's history
# — every stage then fails with AccessDeniedException after minutes of waiting.
# One tiny call up front turns that into a five-second failure with the fix
# named, instead of a dead run you diagnose afterwards.
set -euo pipefail
export PYTHONUNBUFFERED=1

CONFIG="${1:-configs/prototype_smoke_bedrock.yaml}"
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

echo "==> preflight" >&2
python3.11 - "$CONFIG" <<'PY' || exit 1
import sys
from app.core.config import settings
from evals.minimal import workflow

config = sys.argv[1]
missing = [name for name in ("AWS_BEARER_TOKEN_BEDROCK", "AWS_REGION") if not getattr(settings, name, None)]
if not (settings.BEDROCK_INFERENCE_PROFILE_ID or settings.BEDROCK_MODEL_ID):
    missing.append("BEDROCK_INFERENCE_PROFILE_ID")
if missing:
    sys.exit(f"    MISSING in .env: {', '.join(missing)}")

resolved = workflow.resolve_config(f"evals/minimal/{config}" if not config.startswith("/") else config)
if resolved.get("provider") not in ("bedrock", "aws"):
    sys.exit(f"    {config} does not pin `provider: bedrock` — it would dispatch on "
             f"{resolved.get('provider') or 'the default provider'}")

thinking = settings.THINKING_BUDGET_TOKENS
print(f"    workflow   {resolved.get('workflow')}  ({len(resolved['order'])} stages: "
      f"{', '.join(resolved['order'])})")
print(f"    dataset    {workflow.dataset_path(resolved).name}")
print(f"    model      {settings.BEDROCK_INFERENCE_PROFILE_ID or settings.BEDROCK_MODEL_ID}"
      f"  ({settings.AWS_REGION})")
# Stated, never assumed: thinking is live on Bedrock and inert on Mistral, so a
# run that silently changes it is not comparable to the Mistral arm.
print(f"    thinking   {'ON, budget ' + str(thinking) + ' (temperature forced to 1)' if thinking else 'off'}")
print(f"    judge      mistral-large-latest (from the rubrics — a different provider "
      f"from the model under test, deliberately)")
PY

# Auth is verified with a REAL call, because a well-formed expired token looks
# identical to a live one until something uses it. max_tokens is 2048 rather
# than a token or two: with thinking on, build_model floors the budget at 1024
# and it must fit inside max_tokens, so a tiny ceiling fails for a reason that
# has nothing to do with credentials.
if [[ -z "${DRY_RUN:-}" ]]; then
  echo "==> auth probe (one small Bedrock call)" >&2
  python3.11 - <<'PY' || exit 1
import asyncio, sys
import app.agents.model_factory as mf

async def main():
    model = mf.build_model(max_tokens=2048, provider="bedrock")
    reply = await model.ainvoke("Reply with the single word: ready")
    text = getattr(reply, "content", reply)
    print(f"    bedrock OK — {mf.model_identifier(model)}")

try:
    asyncio.run(main())
except Exception as exc:
    detail = str(exc)
    hint = ("\n    The bearer token is expired or invalid — refresh "
            "AWS_BEARER_TOKEN_BEDROCK in .env and re-run."
            if "AccessDenied" in detail or "security token" in detail
            or "UnrecognizedClient" in detail or "ExpiredToken" in detail else "")
    sys.exit(f"    bedrock auth FAILED: {detail}{hint}")
PY
else
  echo "==> DRY_RUN: skipping the auth probe and the run" >&2
  exit 0
fi

echo "==> dispatch: $CONFIG (one invocation per stage)" >&2
set +e
RUN_ID="$(python3.11 -m evals.minimal.cli chain "$CONFIG" | tail -n1)"
DISPATCH_STATUS=$?
set -e

if [[ -z "$RUN_ID" ]]; then
  echo "==> no run id — nothing was dispatched" >&2
  exit 1
fi

# Judge whatever completed, even on a partial chain. The stages that finished
# cost real tokens and are judgeable on their own; throwing that away because a
# later stage failed is the mistake this harness kept making.
echo "==> judge: $RUN_ID" >&2
set +e
python3.11 -m evals.minimal.cli judge "$RUN_ID" --advise
JUDGE_STATUS=$?
set -e

python3.11 -m evals.minimal.cli report >/dev/null
REPORT="$(cd evals/minimal && pwd)/report.html"

echo >&2
echo "=========================================================" >&2
echo " run id   $RUN_ID" >&2
echo " folder   evals/minimal/.runs/$RUN_ID" >&2
echo " report   $REPORT" >&2
if [[ $DISPATCH_STATUS -ne 0 ]]; then
  echo >&2
  echo " PARTIAL — a stage failed to dispatch. Everything before it is judged." >&2
  echo " Resume the failed stage without re-buying the rest:" >&2
  echo "   evals/minimal/eval.sh $CONFIG --stage <name> --into $RUN_ID" >&2
  echo "   evals/minimal/judge.sh $RUN_ID --advise" >&2
fi
echo "=========================================================" >&2
echo "$RUN_ID"

# Non-zero if either half failed, so an unattended run cannot look successful
# while having produced nothing.
[[ $DISPATCH_STATUS -eq 0 && $JUDGE_STATUS -eq 0 ]]
