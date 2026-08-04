#!/usr/bin/env bash
# eval.sh — DISPATCH ONLY, one stage at a time, all into one run folder.
# Judging is a separate script on purpose: ./judge.sh <RUN_ID>
#
#   ./eval.sh <config> [--stage NAME] [--into RUN_ID] [--repeats N]
#                      [--provider P] [--model M]
#
#   ./eval.sh configs/prototype_smoke.yaml            # whole chain, stage by stage
#   ./eval.sh configs/ppt_smoke.yaml                  # a different workflow
#   ./eval.sh configs/prototype_smoke.yaml --stage build --into 260804-154746-prototype_smoke
#
# It prints the RUN ID (last line of stdout) — that is what judge.sh takes.
#
# WHY STAGE BY STAGE: the stages are wildly uneven. specify/plan/analyze are
# 4k-27k input tokens; a prototype `build` is 168k-288k and `validate` up to
# 2.5M, all in bursts that trip a free-tier rate limit. Dispatching each stage
# as its own invocation means a stage that fails costs only that stage — the
# ones before it are stored and are reused by `--into` rather than re-bought.
#
# WHY JUDGING IS NOT HERE: it spends separately and fails for different
# reasons. When the two were welded together, a 429 in `build` also threw away
# the right to judge the three stages that had already succeeded.
#
# LOCATION-INDEPENDENT: `python3.11 -m evals.minimal.cli` resolves `evals` as a
# package, which only works with cwd = backend/. Running it from this folder
# fails with `ModuleNotFoundError: No module named 'evals'` — the one error
# that looks like a broken install and is really a wrong directory. So this
# script finds backend/ from its own path and cds there itself.
#
# UNBUFFERED: without PYTHONUNBUFFERED, output sits in a block buffer and never
# reaches the terminal until the process exits, which is what made a
# multi-minute run look hung.
set -euo pipefail
export PYTHONUNBUFFERED=1

cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
exec python3.11 -m evals.minimal.cli chain "$@"
