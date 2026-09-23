"""tests/agents/test_custom_workflow_migration_v3.py — M4 (GIT_VERSIONING_TASKS.md
Phase M) structural proof for the `custom` / `custom_revision` batch.

`test_seam2_gate_v3.py::test_workflow_fully_migrated` only checks that every agent
carries a non-default `prompt_policy` and *some* "## Sandbox Reading Guide" heading —
it cannot catch a migration that leaves an agent structurally unable to do its job.
Neither workflow has a Phase-8 offline driving helper (`test_phase8_live.py`), so
`test_workflow_agents_free_of_world_blocks` skips both — no runtime harness exercises
these agents here or elsewhere.

Both workflows have a real, non-obvious continuity problem this migration had to
solve at the PROMPT level (no `engine.py` edit is in scope for M4):

- `custom`: every one of the 9 agents declares `consumes: []` (no `produces`/`consumes`
  edge exists between any pair — `context_from: [$previous]` is dead metadata per
  `backend/CLAUDE.md`'s own `context_from` section). Before migration every agent
  received the brief directly (broadcast to all agents under the default policy); after
  migration only agent 1 (`market-research-agent`, `is_first_agent`) still gets it. The
  fix is: agent 1's own reply becomes the durable artefact (`.agents/01-market-research-
  agent.md`, auto-persisted by `write_agent_output` for every agent regardless of write
  access) and must reproduce the brief verbatim so agents 2-9 can `read_file` it.
- `custom_revision`: `custom-revision-builder` (step 2) is NOT `is_first_agent`, so after
  migration it no longer receives the pasted `=== ORIGINAL ARTIFACT ===` text its
  original prompt depended on (there is no `produces`/`consumes` edge or `previous_run`
  seed for this pipeline either — `is_revision_workflow` is false for `custom_revision`,
  so that provider is a no-op). The fix is: `custom-revision-planner` (step 1, which
  still receives the pasted text) now ALSO seeds every original file verbatim into the
  sandbox before writing `plan.md`, so the builder can `read_file` what it needs instead
  of being told to trust a paste it will never see.

These are cheap, offline, load-only checks (`load_agent_spec` + a raw YAML read) — no
engine, no model. They fail if either fix's textual mechanics regress (a renamed file
path, a reverted `workflow.yaml` tool grant, a re-introduced stale promise).
"""

from __future__ import annotations

import pathlib

import pytest
import yaml

from agents.loader import load_agent_spec

_BACKEND_ROOT = pathlib.Path(__file__).resolve().parents[2]

_CUSTOM_DOWNSTREAM_AGENTS = (
    "swot-analyst",
    "roadmap-planner",
    "security-auditor",
    "test-case-generator",
    "performance-optimizer",
    "documentation-agent",
    "report-generator",
    "task-list-planner",
)

_WORLD_MARKERS = (
    "=== ORIGINAL USER REQUEST",
    "uploaded_files_context",
    "ACTIVE DESIGN SYSTEM",
    "ACTIVE TEMPLATE",
    "TEMPLATE EXAMPLE",
    "--- Output from",
    "## Planning Context",
    "REVISION MODE",
    "CURRENT PROTOTYPE HTML",
    "TEMPLATE COMPLIANCE",
)


def test_market_research_agent_states_the_durable_brief_artefact() -> None:
    spec = load_agent_spec("market-research-agent")
    assert spec.prompt_policy == "body_only"
    body = spec.prompt_body or ""
    assert "## Sandbox Reading Guide" in body
    # Agent 1 is the only agent every downstream agent can read the brief from —
    # its own reply MUST be instructed to reproduce the brief verbatim.
    assert "## Original Brief" in body
    assert ".agents/01-market-research-agent.md" in body


@pytest.mark.parametrize("agent_id", _CUSTOM_DOWNSTREAM_AGENTS)
def test_custom_downstream_agents_read_the_brief_file_not_a_paste(agent_id: str) -> None:
    spec = load_agent_spec(agent_id)
    assert spec.prompt_policy == "body_only", f"{agent_id}: not migrated"
    body = spec.prompt_body or ""
    assert "## Sandbox Reading Guide" in body
    # The one file every non-first custom-workflow agent needs: agent 1's own
    # output, which carries the brief this agent no longer receives pasted.
    assert ".agents/01-market-research-agent.md" in body
    for marker in _WORLD_MARKERS:
        assert marker not in body, f"{agent_id}: AGENT.md still promises pasted {marker!r}"


def test_custom_workflow_grants_read_files_to_every_downstream_step() -> None:
    manifest = yaml.safe_load(
        (_BACKEND_ROOT / "agents" / "workflows" / "custom" / "workflow.yaml").read_text()
    )
    steps = {s["agent"]: s for s in manifest["steps"]}
    assert set(steps) == {"market-research-agent", *_CUSTOM_DOWNSTREAM_AGENTS}
    for agent_id in _CUSTOM_DOWNSTREAM_AGENTS:
        tools = steps[agent_id].get("tools") or {}
        assert tools.get("read_files") is True, (
            f"{agent_id}: workflow.yaml step must grant read_files so it can open "
            ".agents/01-market-research-agent.md"
        )
        # write_files must stay unset/false — these agents declare deliverable:
        # streamed_text; granting write risks the R-22 defect (agents.md A/B
        # experiment comment in workflow.yaml) where the reply is written to a
        # file instead of returned and the deliverable degrades.
        assert not tools.get("write_files"), f"{agent_id}: must not gain write_files"


def test_custom_revision_planner_seeds_originals_before_writing_the_plan() -> None:
    spec = load_agent_spec("custom-revision-planner")
    assert spec.prompt_policy == "body_only"
    body = spec.prompt_body or ""
    assert "## Sandbox Reading Guide" in body
    assert "Seed the sandbox" in body
    assert "EVERY file named in" in body


def test_custom_revision_builder_no_longer_promises_a_paste_it_wont_get() -> None:
    spec = load_agent_spec("custom-revision-builder")
    assert spec.prompt_policy == "body_only"
    body = spec.prompt_body or ""
    assert "## Sandbox Reading Guide" in body
    # The old (broken-by-migration) promise must be gone, not just supplemented.
    assert "Your context message also carries the original file set" not in body
    for marker in _WORLD_MARKERS:
        assert marker not in body, f"custom-revision-builder: still promises {marker!r}"
    # The replacement channel: plan.md + the already-seeded sandbox tree.
    assert "plan.md" in body
    assert "already seeded" in body or "already correct" in body


def test_custom_revision_workflow_keeps_read_and_write_tools() -> None:
    manifest = yaml.safe_load(
        (_BACKEND_ROOT / "agents" / "workflows" / "custom_revision" / "workflow.yaml").read_text()
    )
    steps = {s["agent"]: s for s in manifest["steps"]}
    for agent_id in ("custom-revision-planner", "custom-revision-builder"):
        tools = steps[agent_id].get("tools") or {}
        assert tools.get("read_files") is True
        assert tools.get("write_files") is True
