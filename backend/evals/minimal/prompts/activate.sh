#!/usr/bin/env bash
# Switch which prompt VERSION the eval user (`eval-minimal`) dispatches with,
# using production's own per-user prompt-override store
# (app/agents/prompt_overrides.py, backend/skills/users/eval-minimal/<id>/).
# No eval.py file touches this — run.py/judge.py already build every
# AgentContext with user_id="eval-minimal", and _compose_system_prompt
# already reads that user's override automatically. Activating here is the
# ONLY thing that changes: nothing in evals/minimal/*.py needs editing.
#
# Usage:
#   ./activate.sh prototype-build v2      # one agent
#   ./activate.sh prototype v2            # EVERY agent in the prototype workflow
#   ./activate.sh prototype-build reset   # one agent -> canonical AGENT.md
#   ./activate.sh prototype reset         # whole workflow -> canonical
#   ./activate.sh status                  # prototype's agents (default)
#   ./activate.sh status app_builder      # another workflow's agents
#
# The first argument is a workflow id when the registry knows one by that
# name, otherwise an agent id. `prototype` is a workflow; `prototype-build`
# is an agent — they never collide because an agent id is never also a
# pipeline_type.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../../.."   # -> backend/

target="${1:-}"
version="${2:-}"

if [[ -z "$target" ]]; then
  echo "usage: activate.sh <agent-id|workflow> <version|reset>   (or: activate.sh status [workflow])" >&2
  exit 1
fi

python3.11 - "$target" "$version" <<'PY'
import sys
from pathlib import Path

import frontmatter
from agents import registry
from app.agents import prompt_overrides as po

USER_ID = "eval-minimal"
VERSIONS = Path("evals/minimal/prompts/agents")
target, version = sys.argv[1], sys.argv[2]


def agents_of(workflow: str) -> list[str] | None:
    """Agent ids for a workflow, from the REGISTRY — never a hardcoded list.

    `status` used to carry the five prototype ids inline, so it reported on
    agents that had been renamed and stayed silent about ones that had been
    added. The registry is what the engine itself sequences from, so this
    cannot drift from the real pipeline.
    """
    try:
        found = registry.get_pipeline_agents(workflow)
    except Exception:
        return None
    return [spec.id for spec in found] or None


if target == "status":
    workflow = version or "prototype"
    ids = agents_of(workflow)
    if not ids:
        sys.exit(f"no such workflow: {workflow}")
    print(f"{workflow}:")
    for agent_id in ids:
        active = po.has_user_prompt_override(agent_id, user_id=USER_ID)
        print(f"  {agent_id:<24} {'OVERRIDDEN' if active else 'canonical'}")
    sys.exit(0)

if not version:
    sys.exit("usage: activate.sh <agent-id|workflow> <version|reset>")

ids = agents_of(target) or [target]
scope = f"workflow {target} ({len(ids)} agents)" if len(ids) > 1 else target

if version == "reset":
    for agent_id in ids:
        deleted = po.delete_user_prompt_override(agent_id, user_id=USER_ID)
        print(f"  {agent_id:<24} {'reverted to canonical' if deleted else 'was already canonical'}")
    print(f"reset {scope}")
    sys.exit(0)

# Resolve EVERY version file before writing ANY override. A workflow-wide
# activate that stopped halfway would leave the pipeline running a mix of v1
# and v2 prompts — the single worst state to measure from, because the report
# shows one number and no indication that half the stages moved. Better to
# refuse and name what is missing.
resolved: list[tuple[str, Path]] = []
missing: list[str] = []
for agent_id in ids:
    path = VERSIONS / f"{agent_id}.{version}.md"
    (resolved if path.is_file() else missing).append(
        (agent_id, path) if path.is_file() else str(path)
    )

if missing:
    print(f"refusing to activate {scope} — no {version} for "
          f"{len(missing)} of {len(ids)} agents:", file=sys.stderr)
    for path in missing:
        print(f"  {path}", file=sys.stderr)
    print("\nnothing was changed. create the missing versions "
          "(cp <agent>.v1.md <agent>.%s.md) or activate agents individually."
          % version, file=sys.stderr)
    sys.exit(1)

for agent_id, path in resolved:
    body = frontmatter.load(path).content
    saved = po.save_user_prompt_override(agent_id, body, user_id=USER_ID)
    print(f"  {agent_id:<24} {version} -> {saved}")
print(f"activated {version} for {scope}")
PY
