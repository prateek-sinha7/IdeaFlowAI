"""tests/unit/test_figma_ingestor_yaml.py

Disk-read-only tests verifying that both workflow YAML files have the
correct design-ingestor step configuration after Phase 5:
- exec: false (D-01 requires gates for exec: true)
- skills: [design-ingestor]
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

_BACKEND = Path(__file__).resolve().parents[2]
_PROTO_V2_YAML = _BACKEND / "agents" / "workflows" / "prototype_v2" / "workflow.yaml"
_PROTO_YAML = _BACKEND / "agents" / "workflows" / "prototype" / "workflow.yaml"


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _find_step(data: dict, instance_id: str) -> dict | None:
    return next(
        (s for s in data.get("steps", []) if s.get("instance_id") == instance_id),
        None,
    )


@pytest.mark.unit
def test_design_ingestor_has_exec_true_in_v2() -> None:
    """design-ingestor step in prototype_v2 must have exec: false (D-01 requires
    gates: [security, approval] for exec: true, which is too restrictive for an
    automated workflow step; scripts are documented in SKILL.md for developer use).
    """
    data = _load_yaml(_PROTO_V2_YAML)
    step = _find_step(data, "design-ingestor")
    assert step is not None, "design-ingestor step not found in prototype_v2"
    tools = step.get("tools", {})
    assert (
        tools.get("exec") is False
    ), f"design-ingestor in prototype_v2 must have exec: false (got {tools.get('exec')})"


@pytest.mark.unit
def test_design_ingestor_has_exec_true_in_prototype() -> None:
    """design-ingestor step in prototype must have exec: false (same D-01 constraint)."""
    data = _load_yaml(_PROTO_YAML)
    step = _find_step(data, "design-ingestor")
    assert step is not None, "design-ingestor step not found in prototype"
    tools = step.get("tools", {})
    assert (
        tools.get("exec") is False
    ), f"design-ingestor in prototype must have exec: false (got {tools.get('exec')})"


@pytest.mark.unit
def test_design_ingestor_has_figma_ingestor_skill_in_v2() -> None:
    """design-ingestor step in prototype_v2 must declare skills: [design-ingestor]."""
    data = _load_yaml(_PROTO_V2_YAML)
    step = _find_step(data, "design-ingestor")
    assert step is not None
    skills = step.get("skills", [])
    assert (
        "design-ingestor" in skills
    ), f"design-ingestor in prototype_v2 must have design-ingestor in skills. Got: {skills}"


@pytest.mark.unit
def test_design_ingestor_has_figma_ingestor_skill_in_prototype() -> None:
    """design-ingestor step in prototype must declare skills: [design-ingestor]."""
    data = _load_yaml(_PROTO_YAML)
    step = _find_step(data, "design-ingestor")
    assert step is not None
    skills = step.get("skills", [])
    assert (
        "design-ingestor" in skills
    ), f"design-ingestor in prototype must have design-ingestor in skills. Got: {skills}"


@pytest.mark.unit
def test_design_ingestor_still_has_file_extract_tool_set_in_v2() -> None:
    """file_extract tool set must still be present (for PDF ingestion)."""
    data = _load_yaml(_PROTO_V2_YAML)
    step = _find_step(data, "design-ingestor")
    assert step is not None
    tool_sets = step.get("tools", {}).get("tool_sets", [])
    assert (
        "file_extract" in tool_sets
    ), "file_extract tool set must remain on design-ingestor step for PDF support"


@pytest.mark.unit
def test_design_ingestor_still_has_read_write_tools() -> None:
    """read_files and write_files must still be true in both workflows."""
    for yaml_path in [_PROTO_V2_YAML, _PROTO_YAML]:
        data = _load_yaml(yaml_path)
        step = _find_step(data, "design-ingestor")
        assert step is not None
        tools = step.get("tools", {})
        assert (
            tools.get("read_files") is True
        ), f"read_files must be true in {yaml_path.name}"
        assert (
            tools.get("write_files") is True
        ), f"write_files must be true in {yaml_path.name}"
