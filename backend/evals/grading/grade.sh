#!/usr/bin/env bash
# grade.sh — the CLI for agent-output grading.
#
# Standalone: this script owns the grading package and nothing else. It shares no
# entry point with ./evals/hybrid/eval.sh (the hybrid suite — "did the machinery
# run right?", offline by default) or with
# ./evals/model_graded/model-graded.sh (the older, frozen grading branch).
#
# LOCATION-INDEPENDENT by design: it resolves its own directory and walks up to
# find the backend root, so moving this folder does not break it.
#
# Grading answers "is this agent's output good?" — and more to the point, which
# prompt to change and whether the change helped. How to run it: docs/README.md.
# Why it works this way: specs/005-prompt-eval-scoring/.
#
# Usage:
#   ./grade.sh smoke                   # 2 rows, no judge — cheapest real run
#   ./grade.sh small                   # 3 short rows, judged — the debug loop
#   ./grade.sh full                    # every stage, every row, judged  [LIVE]
#   ./grade.sh partial                 # the one you edit: pick agents/rows
#
#   ./grade.sh plan <config>           # any of the above, dispatch nothing (free)
#   ./grade.sh run <config>            # any config by name or path       [LIVE]
#
#   ./grade.sh report <run-id> [-w N]  # per-dimension scores + weaknesses (free)
#   ./grade.sh compare <a> <b>         # deltas between two runs, noise-guarded
#   ./grade.sh history <agent>         # every run grouped by prompt version
#   ./grade.sh code <run-id>           # deterministic HTML checks       (free)
#
#   ./grade.sh runs                    # list run folders               (free)
#   ./grade.sh configs                 # list run configs               (free)
#   ./grade.sh check                   # config integrity, no dispatch  (free)
#   ./grade.sh test                    # the package's own unit tests   (free)
#
#   ./grade.sh model <workflow> ...    # raw passthrough to the runner
#   ./grade.sh <any runner args...>    # anything else goes straight through
#
# EVERYTHING THAT DISPATCHES IS LIVE. There is no --live flag, because
# dispatching real agents is the whole job. Three things protect you: the runner
# prints its blast radius before spending, `plan` stops right there, and the
# judge is preflighted so a misconfigured judge costs nothing.
#
# Exit codes: 0 ok · 2 usage/config · 3 baseline FAIL · 4 judge preflight
#             5 no credentials · 6 run did not complete
set -euo pipefail

GRADING_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Walk up to the backend root (the dir holding pyproject.toml) so the package
# import path works no matter where this folder is moved to.
BACKEND="$GRADING_DIR"
while [[ "$BACKEND" != "/" && ! -f "$BACKEND/pyproject.toml" ]]; do
  BACKEND="$(dirname "$BACKEND")"
done
if [[ ! -f "$BACKEND/pyproject.toml" ]]; then
  echo "grade.sh: cannot find the backend root (no pyproject.toml above $GRADING_DIR)" >&2
  exit 2
fi

# Package path derived from the location on disk, not hardcoded — so a move of
# this folder needs no edit here.
PKG="$(python3 -c "
import os,sys
rel = os.path.relpath('$GRADING_DIR', '$BACKEND')
print(rel.replace(os.sep, '.'))
")"

PY="${PYTHON:-python3.11}"
CONFIGS="$GRADING_DIR/configs"

cd "$BACKEND"

_runner() { exec "$PY" -m "$PKG.grade_runner" "$@"; }

_config_path() {
  # Accept a full path, a filename, or a distinctive fragment ("smoke").
  local want="$1"
  for candidate in "$want" "$CONFIGS/$want" "$CONFIGS/$want.yaml"; do
    [[ -f "$candidate" ]] && { echo "$candidate"; return 0; }
  done

  # Fragment match — only accept it when exactly one config matches, so an
  # ambiguous shortcut never silently picks the wrong (token-spending) run.
  local matches=()
  while IFS= read -r m; do matches+=("$m"); done \
    < <(find "$CONFIGS" -maxdepth 1 -name "*${want}*.yaml" 2>/dev/null | sort)

  if [[ ${#matches[@]} -eq 1 ]]; then
    echo "${matches[0]}"; return 0
  elif [[ ${#matches[@]} -gt 1 ]]; then
    echo "grade.sh: '$want' is ambiguous — matches:" >&2
    printf '  %s\n' "${matches[@]##*/}" >&2
    exit 2
  fi

  echo "grade.sh: no such config '$want'. Available:" >&2
  ls -1 "$CONFIGS"/*.yaml 2>/dev/null | xargs -n1 basename | sed 's/^/  /' >&2
  exit 2
}

_warn_live() {
  echo "" >&2
  echo "  LIVE — this dispatches real agents and spends tokens." >&2
  echo "  Preview it first with:  ./grade.sh plan $*" >&2
}

case "${1:-help}" in
  help|-h|--help)
    # Absolute path: we have already cd'd to the backend root by now.
    sed -n '2,42p' "$GRADING_DIR/grade.sh" | sed 's/^# \{0,1\}//'
    exit 0
    ;;

  run)
    shift
    [[ -z "${1:-}" ]] && { echo "usage: ./grade.sh run <config>" >&2; exit 2; }
    cfg="$(_config_path "$1")"; shift
    _warn_live "$(basename "$cfg")"
    _runner --config "$cfg" "$@"
    ;;

  plan|dry-run)
    shift
    [[ -z "${1:-}" ]] && { echo "usage: ./grade.sh plan <config>" >&2; exit 2; }
    cfg="$(_config_path "$1")"; shift
    _runner --config "$cfg" --dry-run "$@"
    ;;

  smoke|small|full|partial)
    # The four shipped configs, each reachable by its own name.
    name="$1"; shift
    # `$name`, not `$name.yaml`: _config_path tries an exact match first, so
    # this is identical today — but it also lets the fragment matcher find a
    # workflow-prefixed file later. Passing the extension makes the fragment
    # glob `*smoke.yaml*.yaml`, which matches nothing, so `grade.sh smoke` would
    # break under a rename while `grade.sh plan smoke` kept working.
    cfg="$(_config_path "$name")"
    _warn_live "$name"
    _runner --config "$cfg" "$@"
    ;;

  report)
    shift
    [[ -z "${1:-}" ]] && { echo "usage: ./grade.sh report <dataset_run_id> [--worst N]" >&2; exit 2; }
    _runner report "$@"
    ;;

  compare)
    shift
    _runner compare "$@"
    ;;

  history)
    # Every run for one agent, grouped by prompt version — the "did my edit
    # help?" view. Defaults to the prototype workflow.
    shift
    [[ -z "${1:-}" ]] && { echo "usage: ./grade.sh history <agent-id> [--workflow W]" >&2; exit 2; }
    agent="$1"; shift
    _runner compare --by-prompt --agent "$agent" "$@"
    ;;

  code)
    shift
    [[ -z "${1:-}" ]] && { echo "usage: ./grade.sh code <dataset_run_id>" >&2; exit 2; }
    run_id="$1"; shift
    _runner code prototype --from-run "$run_id" "$@"
    ;;

  runs)
    # Every run folder, newest first. Run output lives at the grading root, not
    # inside the workflow config tree, so this is one listing per workflow.
    #
    # The CONFIG column matters: a folder is named for its dataset, so two
    # different configs reading one dataset produce folders that differ only by
    # timestamp. Without this you cannot tell a `smoke` run from a `small` one.
    "$PY" - "$GRADING_DIR" <<'PYRUNS'
import json, pathlib, sys
runs_root = pathlib.Path(sys.argv[1]) / ".runs"
rows = []
# Dot-directories are housekeeping (an .archive someone made), not runs.
def folders(parent):
    return sorted(
        (p for p in parent.glob("*") if p.is_dir() and not p.name.startswith(".")),
        reverse=True,
    )

for workflow in sorted(folders(runs_root)):
    for run in folders(workflow):
        summary = run / "run_summary.json"
        config = status = "—"
        if summary.exists():
            try:
                data = json.loads(summary.read_text())
                config, status = data.get("run_id", "—"), data.get("status", "—")
            except ValueError:
                config = status = "(unreadable)"
        rows.append((run.name, workflow.name, config, status))
if not rows:
    print("  (no runs yet — try ./grade.sh plan smoke)")
else:
    print(f"  {'run':<30}{'workflow':<12}{'config':<12}status")
    for name, workflow, config, status in rows:
        print(f"  {name:<30}{workflow:<12}{config:<12}{status}")
PYRUNS
    exit 0
    ;;

  configs)
    # The WORKFLOW column matters: configs are workflow-agnostic files that each
    # name their own `workflow:`, so the binding is invisible in the filename.
    printf "  %-24s%-12s%s\n" "config" "run_id" "workflow"
    for c in "$CONFIGS"/*.yaml; do
      [[ -f "$c" ]] || continue
      printf "  %-24s%-12s%s\n" "$(basename "$c")" \
        "$(grep -m1 '^run_id:' "$c" | sed 's/run_id: *//')" \
        "$(grep -m1 '^workflow:' "$c" | sed 's/workflow: *//')"
    done
    exit 0
    ;;

  check)
    # Config integrity only. Parses every file, asserts workflow.yaml still
    # mirrors the real agent registry, and dry-runs every shipped config.
    # Zero dispatches, zero tokens.
    "$PY" - "$GRADING_DIR" "$PKG" <<'PYCHECK'
import json, pathlib, re, sys, yaml
root, pkg = pathlib.Path(sys.argv[1]), sys.argv[2]
for p in sorted(root.rglob("*.yaml")):
    if p.suffix == ".yaml" and ".runs" not in p.parts: yaml.safe_load(p.read_text())
for p in sorted(root.rglob("*.json")):
    if ".runs" not in p.parts: json.load(open(p))
print("  every YAML/JSON parses")
from agents.registry import get_pipeline_agents
for wf_path in sorted(root.glob("model/workflows/*/workflow.yaml")):
    wf = yaml.safe_load(wf_path.read_text())
    declared = [s["agent_id"] for s in wf["stages"]]
    actual = [a.id for a in get_pipeline_agents(wf["pipeline_type"])]
    assert declared == actual, f"{wf_path}: {declared} != {actual}"
    print(f"  {wf['workflow_id']}: stage order matches the registry")
for rub in sorted(root.glob("model/workflows/*/*_rubric.yaml")):
    r = yaml.safe_load(rub.read_text())
    total = sum(d["weight"] for d in r["dimensions"])
    assert total == 100, f"{rub.name}: weights sum to {total}, not 100"
    for f in r["precheck"]["forbidden"]:
        re.compile(f["pattern"]); assert f["reason"], f"{rub.name}: forbidden entry missing a reason"
    print(f"  {rub.name}: weights sum 100, all patterns compile")

# A dry_run_sample stands in for a stage's real output during a preview. If it
# would not pass that agent's OWN precheck, it is not real-shaped, and the
# preview quietly stops representing the run it is previewing.
sys.path.insert(0, str(pathlib.Path.cwd()))
from evals.grading import config as _cfg, precheck as _pre
for wf_path in sorted(root.glob("model/workflows/*/workflow.yaml")):
    wf_dir = wf_path.parent
    for stage in yaml.safe_load(wf_path.read_text())["stages"]:
        sample = stage.get("dry_run_sample")
        if not sample:
            continue
        rubric = _cfg.load_rubric(wf_dir, stage["agent_id"])
        ok, why = _pre.run(sample, rubric["precheck"], hook=rubric.get("validate_hook"))
        assert ok, f"{stage['agent_id']} dry_run_sample fails its own precheck: {why}"
        print(f"  {stage['agent_id']}: dry_run_sample passes its own precheck")
PYCHECK
    echo "  --- dry-running every shipped config ---"
    for c in "$CONFIGS"/*.yaml; do
      [[ -f "$c" ]] || continue
      # Strip the leading indent and the row's label, keeping just the numbers.
      line=$("$PY" -m "$PKG.grade_runner" --config "$c" --dry-run 2>/dev/null \
        | grep 'AI call' | sed -E 's/^[[:space:]]*(cost[[:space:]]+)?//' || echo "FAILED")
      printf "  %-34s %s\n" "$(basename "$c")" "$line"
    done
    exit 0
    ;;

  test)
    shift
    exec "$PY" -m pytest tests/unit/test_grading_*.py "$@"
    ;;

  *)
    # Anything else is a raw runner invocation: model / code / report / compare
    # or a bare --config. Passthrough keeps the full CLI reachable.
    case "${1:-}" in
      model|--config) _warn_live "$*" ;;
    esac
    _runner "$@"
    ;;
esac
