"""Unit tests for evals.model_graded.scenario_discovery (task T3)."""

from __future__ import annotations

import pytest

from evals.model_graded.scenario_discovery import (
    discover_all_scenarios,
    load_scenario_yaml,
)

VALID_YAML = """
id: {id}
agent_id: prototype-specify
prompt: "Build a thing."
precheck:
  wrapper: "<spec>"
  section_pattern: '^### '
  forbidden: ["TBD"]
rubric: |
  Grade this.
"""


def _write(tmp_path, agent_dir_name, scenario_id, content):
    agent_dir = tmp_path / agent_dir_name / "scenarios"
    agent_dir.mkdir(parents=True, exist_ok=True)
    path = agent_dir / f"{scenario_id}.yaml"
    path.write_text(content)
    return path


def test_loads_a_valid_scenario(tmp_path):
    path = _write(tmp_path, "prototype_specify", "s1", VALID_YAML.format(id="s1"))
    scenario = load_scenario_yaml(path)
    assert scenario.id == "s1"
    assert scenario.agent_id == "prototype-specify"
    assert scenario.min_pages == 4
    assert scenario.precheck_config["min_sections"] == 4
    assert scenario.precheck_module is None
    assert "Grade this." in scenario.rubric


def test_id_filename_mismatch_raises(tmp_path):
    path = _write(tmp_path, "prototype_specify", "s1", VALID_YAML.format(id="different"))
    with pytest.raises(ValueError, match="must match the filename"):
        load_scenario_yaml(path)


def test_unknown_agent_id_raises(tmp_path):
    bad = VALID_YAML.format(id="s1").replace("prototype-specify", "no-such-agent")
    path = _write(tmp_path, "prototype_specify", "s1", bad)
    with pytest.raises(ValueError, match="unknown agent_id"):
        load_scenario_yaml(path)


def test_missing_precheck_block_raises(tmp_path):
    bad = "id: s1\nagent_id: prototype-specify\nprompt: hi\nrubric: grade this\n"
    path = _write(tmp_path, "prototype_specify", "s1", bad)
    with pytest.raises(ValueError, match="'precheck' block is required"):
        load_scenario_yaml(path)


def test_missing_rubric_raises(tmp_path):
    bad = (
        "id: s1\nagent_id: prototype-specify\nprompt: hi\n"
        "precheck:\n  wrapper: '<spec>'\n  section_pattern: '^### '\n  forbidden: []\n"
    )
    path = _write(tmp_path, "prototype_specify", "s1", bad)
    with pytest.raises(ValueError, match="'rubric' block is required"):
        load_scenario_yaml(path)


def test_unresolvable_precheck_module_raises(tmp_path):
    bad = VALID_YAML.format(id="s1") + "precheck_module: nonexistent.module:fn\n"
    path = _write(tmp_path, "prototype_specify", "s1", bad)
    with pytest.raises(ValueError, match="could not be resolved"):
        load_scenario_yaml(path)


def test_invalid_min_pages_raises(tmp_path):
    bad = VALID_YAML.format(id="s1") + "min_pages: 0\n"
    path = _write(tmp_path, "prototype_specify", "s1", bad)
    with pytest.raises(ValueError, match="'min_pages' must be a positive integer"):
        load_scenario_yaml(path)


def test_discover_all_scenarios_finds_the_real_prototype_specify_scenario():
    """Integration-flavored: exercises the real agents/ tree in this repo,
    proving the shipped prototype-specify scenario (task T5) loads cleanly."""
    scenarios = discover_all_scenarios()
    assert "billing_console" in scenarios
    scenario = scenarios["billing_console"]
    assert scenario.agent_id == "prototype-specify"
    assert scenario.precheck_module is not None


def test_discover_all_scenarios_expands_dataset_json_against_shared_template():
    """The real prototype-specify dataset.json (10+ industries) all share
    ONE _template.yaml's precheck/rubric — no new Python or YAML per prompt."""
    scenarios = discover_all_scenarios()
    dataset_ids = {
        "billing_console", "healthcare_scheduling", "logistics_fleet",
        "ecommerce_orders", "education_lms", "real_estate_crm",
        "fintech_fraud_review", "hr_ats", "manufacturing_production",
        "legal_case_management", "hospitality_reservations",
    }
    assert dataset_ids <= scenarios.keys()
    rubrics = {scenarios[sid].rubric for sid in dataset_ids}
    assert len(rubrics) == 1, "all dataset entries must share the template's rubric"
    prompts = {scenarios[sid].prompt for sid in dataset_ids}
    assert len(prompts) == len(dataset_ids), "each dataset entry must have a distinct prompt"


def test_load_dataset_scenarios_rejects_duplicate_entry_ids(tmp_path):
    import json

    scenarios_dir = tmp_path / "agent_x" / "scenarios"
    scenarios_dir.mkdir(parents=True)
    (scenarios_dir / "_template.yaml").write_text(
        "agent_id: prototype-specify\n"
        "precheck:\n  wrapper: '<spec>'\n  section_pattern: '^### '\n  forbidden: []\n"
        "rubric: grade this\n"
    )
    (scenarios_dir / "dataset.json").write_text(
        json.dumps([{"id": "dup", "prompt": "a"}, {"id": "dup", "prompt": "b"}])
    )
    from evals.model_graded.scenario_discovery import load_dataset_scenarios

    with pytest.raises(ValueError, match="duplicate dataset entry id"):
        load_dataset_scenarios(scenarios_dir / "_template.yaml", scenarios_dir / "dataset.json")


def test_discover_all_scenarios_raises_on_duplicate_id(tmp_path):
    _write(tmp_path, "agent_a", "dup", VALID_YAML.format(id="dup"))
    dup_yaml = VALID_YAML.format(id="dup")
    _write(tmp_path, "agent_b", "dup", dup_yaml)
    with pytest.raises(ValueError, match="duplicate model-graded scenario id"):
        discover_all_scenarios(agents_root=tmp_path)


def _write_template_and_dataset(tmp_path, agent_dir_name, agent_id, dataset_filename, entries):
    import json

    scenarios_dir = tmp_path / agent_dir_name / "scenarios"
    scenarios_dir.mkdir(parents=True, exist_ok=True)
    (scenarios_dir / "_template.yaml").write_text(
        f"agent_id: {agent_id}\n"
        "precheck:\n  wrapper: '<spec>'\n  section_pattern: '^### '\n  forbidden: []\n"
        "rubric: grade this\n"
    )
    (scenarios_dir / dataset_filename).write_text(json.dumps(entries))


def test_find_dataset_scenarios_defaults_to_dataset_json(tmp_path):
    from evals.model_graded.scenario_discovery import find_dataset_scenarios

    _write_template_and_dataset(
        tmp_path, "agent_x", "prototype-specify", "dataset.json", [{"id": "a", "prompt": "hi"}]
    )
    scenarios = find_dataset_scenarios("prototype-specify", agents_root=tmp_path)
    assert [s.id for s in scenarios] == ["a"]


def test_find_dataset_scenarios_loads_a_named_dataset_file(tmp_path):
    from evals.model_graded.scenario_discovery import find_dataset_scenarios

    _write_template_and_dataset(
        tmp_path, "agent_x", "prototype-specify", "dataset_small.json", [{"id": "b", "prompt": "hi"}]
    )
    scenarios = find_dataset_scenarios("prototype-specify", "dataset_small", agents_root=tmp_path)
    assert [s.id for s in scenarios] == ["b"]


def test_find_dataset_scenarios_raises_when_named_file_missing(tmp_path):
    from evals.model_graded.scenario_discovery import find_dataset_scenarios

    _write_template_and_dataset(
        tmp_path, "agent_x", "prototype-specify", "dataset.json", [{"id": "a", "prompt": "hi"}]
    )
    with pytest.raises(FileNotFoundError, match="dataset_small.json"):
        find_dataset_scenarios("prototype-specify", "dataset_small", agents_root=tmp_path)


def test_find_dataset_scenarios_raises_when_agent_id_unknown(tmp_path):
    from evals.model_graded.scenario_discovery import find_dataset_scenarios

    _write_template_and_dataset(
        tmp_path, "agent_x", "prototype-specify", "dataset.json", [{"id": "a", "prompt": "hi"}]
    )
    with pytest.raises(ValueError, match="no scenarios/_template.yaml declares"):
        find_dataset_scenarios("no-such-agent", agents_root=tmp_path)
