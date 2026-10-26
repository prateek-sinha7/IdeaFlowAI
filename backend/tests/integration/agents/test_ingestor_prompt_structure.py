"""Integration tests — unified design-ingestor agent prompt structure.

Disk reads only (no DB, network, LLM, or real I/O). Validates:
  - Unified AGENT.md exists at agents/prompts/design-ingestor/AGENT.md
  - Both prototype_v2 and prototype workflow YAMLs contain ONE design-ingestor step
  - The step's condition covers BOTH html and figma source types
  - The step carries the correct tool grants
  - The AGENT.md prompt names expected input/output files for both html and figma paths
  - The step appears before fi-planner / prototype-specify
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_BACKEND = Path(__file__).resolve().parents[3]
_PROMPTS = _BACKEND / "agents" / "prompts"
_WORKFLOWS = _BACKEND / "agents" / "workflows"

INGESTOR_AGENT_MD = _PROMPTS / "design-ingestor" / "AGENT.md"
PROTO_V2_YAML = _WORKFLOWS / "prototype_v2" / "workflow.yaml"
PROTO_YAML = _WORKFLOWS / "prototype" / "workflow.yaml"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _find_step(data: dict, instance_id: str) -> dict | None:
    return next(
        (s for s in data.get("steps", []) if s.get("instance_id") == instance_id),
        None,
    )


# ---------------------------------------------------------------------------
# Unified agent existence
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_unified_ingestor_agent_md_exists() -> None:
    """Unified AGENT.md must exist at agents/prompts/design-ingestor/AGENT.md."""
    assert (
        INGESTOR_AGENT_MD.exists()
    ), f"design-ingestor AGENT.md not found at {INGESTOR_AGENT_MD}"


@pytest.mark.integration
def test_no_separate_html_ingestor_step_in_yaml() -> None:
    """Separate design-ingestor-html step must be gone — unified step replaces it."""
    for yaml_path in [PROTO_V2_YAML, PROTO_YAML]:
        data = _load_yaml(yaml_path)
        ids = [s.get("instance_id") for s in data.get("steps", [])]
        assert (
            "design-ingestor-html" not in ids
        ), f"design-ingestor-html should be removed from {yaml_path.name} — use design-ingestor"


@pytest.mark.integration
def test_no_separate_figma_ingestor_step_in_yaml() -> None:
    """Separate design-ingestor-figma step must be gone — unified step replaces it."""
    for yaml_path in [PROTO_V2_YAML, PROTO_YAML]:
        data = _load_yaml(yaml_path)
        ids = [s.get("instance_id") for s in data.get("steps", [])]
        assert (
            "design-ingestor-figma" not in ids
        ), f"design-ingestor-figma should be removed from {yaml_path.name} — use design-ingestor"


# ---------------------------------------------------------------------------
# YAML step structure
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_unified_ingestor_step_in_prototype_v2_yaml() -> None:
    """prototype_v2/workflow.yaml must contain exactly one design-ingestor step."""
    data = _load_yaml(PROTO_V2_YAML)
    ids = [s.get("instance_id") for s in data.get("steps", [])]
    assert (
        "design-ingestor" in ids
    ), f"design-ingestor step not found in {PROTO_V2_YAML.name}. Found: {ids}"


@pytest.mark.integration
def test_unified_ingestor_step_in_prototype_yaml() -> None:
    """prototype/workflow.yaml must contain exactly one design-ingestor step."""
    data = _load_yaml(PROTO_YAML)
    ids = [s.get("instance_id") for s in data.get("steps", [])]
    assert (
        "design-ingestor" in ids
    ), f"design-ingestor step not found in {PROTO_YAML.name}. Found: {ids}"


@pytest.mark.integration
def test_ingestor_step_condition_covers_both_source_types() -> None:
    """design-ingestor step condition must cover BOTH html and figma source types."""
    for yaml_path in [PROTO_V2_YAML, PROTO_YAML]:
        data = _load_yaml(yaml_path)
        step = _find_step(data, "design-ingestor")
        assert step is not None, f"design-ingestor not found in {yaml_path.name}"
        condition: str = step.get("condition", "")
        assert "source_type" in condition, "condition must reference source_type"
        assert "html" in condition, "condition must cover html"
        assert "figma" in condition, "condition must cover figma"


@pytest.mark.integration
def test_ingestor_step_has_read_write_tools() -> None:
    """design-ingestor step must have read_files=true, write_files=true, exec=false."""
    for yaml_path in [PROTO_V2_YAML, PROTO_YAML]:
        data = _load_yaml(yaml_path)
        step = _find_step(data, "design-ingestor")
        assert step is not None, f"design-ingestor not found in {yaml_path.name}"
        tools: dict = step.get("tools", {})
        assert (
            tools.get("read_files") is True
        ), f"{yaml_path.name}: read_files must be true"
        assert (
            tools.get("write_files") is True
        ), f"{yaml_path.name}: write_files must be true"
        assert tools.get("exec") is False, f"{yaml_path.name}: exec must be false"


@pytest.mark.integration
def test_ingestor_step_uses_design_ingestor_agent() -> None:
    """design-ingestor step must use agent: design-ingestor (not custom-agent)."""
    for yaml_path in [PROTO_V2_YAML, PROTO_YAML]:
        data = _load_yaml(yaml_path)
        step = _find_step(data, "design-ingestor")
        assert step is not None, f"design-ingestor not found in {yaml_path.name}"
        agent = step.get("agent", "")
        assert (
            agent == "design-ingestor"
        ), f"Expected agent: design-ingestor in {yaml_path.name}, got: {agent!r}"


@pytest.mark.integration
def test_ingestor_step_before_fi_planner_in_v2() -> None:
    """design-ingestor must appear before fi-planner in prototype_v2 YAML."""
    data = _load_yaml(PROTO_V2_YAML)
    ids = [s.get("instance_id") for s in data.get("steps", [])]
    assert "design-ingestor" in ids, "design-ingestor step not found"
    assert "fi-planner" in ids, "fi-planner step not found"
    assert (
        ids.index("design-ingestor") < ids.index("fi-planner")
    ), f"design-ingestor (pos {ids.index('design-ingestor')}) must come before fi-planner (pos {ids.index('fi-planner')})"


@pytest.mark.integration
def test_ingestor_step_before_prototype_specify() -> None:
    """design-ingestor must appear before prototype-specify in prototype YAML."""
    data = _load_yaml(PROTO_YAML)
    ids = [s.get("instance_id") for s in data.get("steps", [])]
    agent_ids = [s.get("agent") for s in data.get("steps", [])]
    assert "design-ingestor" in ids, "design-ingestor step not found"
    assert "prototype-specify" in agent_ids, "prototype-specify step not found"
    ingestor_idx = ids.index("design-ingestor")
    specify_idx = next(i for i, a in enumerate(agent_ids) if a == "prototype-specify")
    assert (
        ingestor_idx < specify_idx
    ), "design-ingestor must come before prototype-specify"


# ---------------------------------------------------------------------------
# AGENT.md prompt content — HTML path
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_html_ingestor_prompt_mentions_raw_upload_input() -> None:
    """Unified AGENT.md must reference raw-upload.html (html ingestion input)."""
    content = INGESTOR_AGENT_MD.read_text(encoding="utf-8")
    assert (
        "raw-upload.html" in content
    ), "design-ingestor AGENT.md must mention 'raw-upload.html' for the html path"


@pytest.mark.integration
def test_html_ingestor_prompt_mentions_example_html_output() -> None:
    """Unified AGENT.md must reference example.html as a template output."""
    content = INGESTOR_AGENT_MD.read_text(encoding="utf-8")
    assert (
        "example.html" in content
    ), "design-ingestor AGENT.md must mention 'example.html'"


# ---------------------------------------------------------------------------
# AGENT.md prompt content — Figma path
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_figma_ingestor_prompt_mentions_uploads_path() -> None:
    """Unified AGENT.md must reference .uploads/manifest.json to distinguish it from .figma/."""
    content = INGESTOR_AGENT_MD.read_text(encoding="utf-8")
    # AGENT.md should mention .uploads/manifest.json to clarify it's NOT where frames live
    assert ".uploads/manifest.json" in content, (
        "design-ingestor AGENT.md must mention '.uploads/manifest.json' "
        "(to distinguish from .figma/manifest.json where Figma frames are stored)"
    )
    # And it MUST reference .figma/manifest.json as the actual frame source
    assert (
        ".figma/manifest.json" in content
    ), "design-ingestor AGENT.md must reference '.figma/manifest.json' as the Figma frame manifest"


@pytest.mark.integration
def test_figma_ingestor_prompt_mentions_context_design_outputs() -> None:
    """Unified AGENT.md must reference all .context/design/ output files for figma path."""
    content = INGESTOR_AGENT_MD.read_text(encoding="utf-8")
    for path in [
        ".context/design/design-system.md",
        ".context/design/template/SKILL.md",
        ".context/design/template/example.html",
    ]:
        assert path in content, f"design-ingestor AGENT.md must mention '{path}'"


@pytest.mark.integration
def test_ingestor_prompt_reads_selections_json_first() -> None:
    """Unified AGENT.md must read selections.json to determine source_type."""
    content = INGESTOR_AGENT_MD.read_text(encoding="utf-8")
    assert (
        "selections.json" in content
    ), "design-ingestor AGENT.md must read selections.json to identify source_type"
    assert (
        "source_type" in content
    ), "design-ingestor AGENT.md must reference source_type"
