#!/usr/bin/env bash
# Pool every stored run's advisor output into ONE file, next to the versioned
# prompts it argues about: evals/minimal/prompts/advices.json
#
# Free — reads what's already on disk, makes no model call. Safe to re-run
# after every eval; it always rebuilds from scratch rather than appending, so
# archived or deleted runs drop out instead of lingering.
#
# Usage:
#   ./advice.sh                      # -> prompts/advices.json
#   ./advice.sh /tmp/advices.json    # somewhere else
#   ./advice.sh --summary            # rebuild, then print the per-stage table
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../../.."   # -> backend/

summary=false
out=""
for arg in "$@"; do
  case "$arg" in
    --summary) summary=true ;;
    *) out="$arg" ;;
  esac
done

if [[ -n "$out" ]]; then
  python3.11 -m evals.minimal.cli advice --out "$out"
  target="$out"
else
  target=$(python3.11 -m evals.minimal.cli advice)
fi

# Always report the prompt-version split, not only under --summary. Advice is
# a criticism of a SPECIFIC prompt body: once a stage shows more than one
# hash, its bucket mixes suggestions about text that still exists with
# suggestions about text that was replaced, and nothing downstream can tell
# them apart. That is a correctness warning about the file just written, so
# it prints whether or not you asked for the table.
python3.11 - "$target" "$summary" <<'PY'
import json, sys
data = json.load(open(sys.argv[1]))
verbose = sys.argv[2] == "true"
mixed = []
for workflow, wf in data["workflows"].items():
    if verbose:
        print(f"\n{workflow}: {wf['unique']} unique / {wf['total']} total"
              f"  ({len(data['runs'])} runs)")
    for stage, st in wf["stages"].items():
        hashes = st.get("system_prompt_hashes") or []
        if verbose:
            cats = ", ".join(f"{c}={v['unique']}" for c, v in st["categories"].items())
            print(f"  {stage:<9} {str(st.get('agent_id')):<20} "
                  f"unique={st['unique']:<4} {cats}")
        if len(hashes) > 1:
            mixed.append((workflow, stage, st.get("agent_id"), len(hashes)))
for workflow, stage, agent, n in mixed:
    print(f"\nWARNING  {workflow}/{stage} ({agent}) mixes advice from {n} prompt "
          f"versions.\n         Suggestions collected against a replaced prompt body "
          f"describe text\n         that no longer exists. Split by "
          f"`system_prompt_hashes` before applying.")
PY
