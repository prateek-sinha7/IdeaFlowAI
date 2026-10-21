"""Phase 2 integration tests — design-ingestor-html agent prompt structure.

Disk reads only (no DB, network, LLM, or real I/O). Validates:
  - AGENT.md exists at the expected path
  - Both prototype_v2 and prototype workflow YAMLs contain the step
  - The step carries the correct source_type condition and tool grants
  - The AGENT.md prompt content names the expected input / output files

Phase 3 will add the figma-ingestor counterpart tests to this file, and
test_both_ingestor_steps_have_read_write_tools will be extended to cover both.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

# ---------------------------------------------------------------------------
# Paths (resolved from this file's location — never rely on cwd)
# ---------------------------------------------------------------------------

_BACKEND = Path(__file__).resolve().parents[3]
_PROMPTS = _BACKEND / "agents" / "prompts"
_WORKFLOWS = _BACKEND / "agents" / "workflows"

HTML_AGENT_MD = _PROMPTS / "design-ingestor-html" / "AGENT.md"
PROTO_V2_YAML = _WORKFLOWS / "prototype_v2" / "workflow.yaml"
PROTO_YAML = _WORKFLOWS / "prototype" / "workflow.yaml"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _find_step(workflow_data: dict, instance_id: str) -> dict | None:
    """Return the first step with the given instance_id, or None."""
    return next(
        (s for s in workflow_data.get("steps", []) if s.get("instance_id") == instance_id),
        None,
    )


# ---------------------------------------------------------------------------
# Phase 2 tests — HTML Ingestor
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_html_ingestor_agent_md_exists() -> None:
    """AGENT.md must exist at agents/prompts/design-ingestor-html/AGENT.md."""
    assert HTML_AGENT_MD.exists(), (
        f"design-ingestor-html AGENT.md not found at {HTML_AGENT_MD}. "
        "Phase 2 must create this file."
    )


@pytest.mark.integration
def test_html_ingestor_step_in_prototype_v2_yaml() -> None:
    """prototype_v2/workflow.yaml must contain a design-ingestor-html step."""
    data = _load_yaml(PROTO_V2_YAML)
    instance_ids = [s.get("instance_id") for s in data.get("steps", [])]
    assert "design-ingestor-html" in instance_ids, (
        f"design-ingestor-html step not found in {PROTO_V2_YAML.name}. "
        f"Found instance_ids: {instance_ids}"
    )


@pytest.mark.integration
def test_html_ingestor_step_in_prototype_yaml() -> None:
    """prototype/workflow.yaml must contain a design-ingestor-html step."""
    data = _load_yaml(PROTO_YAML)
    instance_ids = [s.get("instance_id") for s in data.get("steps", [])]
    assert "design-ingestor-html" in instance_ids, (
        f"design-ingestor-html step not found in {PROTO_YAML.name}. "
        f"Found instance_ids: {instance_ids}"
    )


@pytest.mark.integration
def test_html_ingestor_step_has_source_type_condition() -> None:
    """The design-ingestor-html step must have a condition referencing source_type == 'html'."""
    for yaml_path in [PROTO_V2_YAML, PROTO_YAML]:
        data = _load_yaml(yaml_path)
        step = _find_step(data, "design-ingestor-html")
        assert step is not None, f"design-ingestor-html step not found in {yaml_path.name}"

        condition: str = step.get("condition", "")
        assert condition, (
            f"design-ingestor-html step in {yaml_path.name} has no condition field"
        )
        assert "source_type" in condition, (
            f"condition {condition!r} in {yaml_path.name} must reference source_type"
        )
        assert "html" in condition, (
            f"condition {condition!r} in {yaml_path.name} must reference 'html'"
        )


@pytest.mark.integration
def test_html_ingestor_prompt_mentions_raw_upload_input() -> None:
    """design-ingestor-html AGENT.md must reference raw-upload.html as its input."""
    content = HTML_AGENT_MD.read_text(encoding="utf-8")
    assert "raw-upload.html" in content, (
        "design-ingestor-html AGENT.md must mention 'raw-upload.html' "
        "(the file written by od_context_sandbox.py for html source_type runs)"
    )


@pytest.mark.integration
def test_html_ingestor_prompt_mentions_example_html_output() -> None:
    """design-ingestor-html AGENT.md must reference example.html as an output."""
    content = HTML_AGENT_MD.read_text(encoding="utf-8")
    assert "example.html" in content, (
        "design-ingestor-html AGENT.md must mention 'example.html' "
        "(the template file written for downstream agents)"
    )


@pytest.mark.integration
def test_both_ingestor_steps_have_read_write_tools() -> None:
    """design-ingestor-html step must have read_files=true, write_files=true, exec=false.

    Phase 2 — html only. Phase 3 extends this to also cover design-ingestor-figma.
    """
    for yaml_path in [PROTO_V2_YAML, PROTO_YAML]:
        data = _load_yaml(yaml_path)
        step = _find_step(data, "design-ingestor-html")
        assert step is not None, f"design-ingestor-html step not found in {yaml_path.name}"

        tools: dict = step.get("tools", {})
        assert tools.get("read_files") is True, (
            f"design-ingestor-html in {yaml_path.name}: tools.read_files must be true"
        )
        assert tools.get("write_files") is True, (
            f"design-ingestor-html in {yaml_path.name}: tools.write_files must be true"
        )
        assert tools.get("exec") is False, (
            f"design-ingestor-html in {yaml_path.name}: tools.exec must be false"
        )
