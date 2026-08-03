"""Unit tests for evals.grading.config — the four config kinds.

Offline: no model, no network. Wherever possible these read the REAL shipped
configs, so an edit to a run config, the workflow manifest, the rubric or the
dataset is caught here rather than in a live run.
"""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path

import pytest
import yaml

from evals.grading.config import (
    RunConfig,
    compute_hashes,
    load_dataset,
    load_rubric,
    load_run_config,
    load_workflow,
)

GRADING_DIR = Path(__file__).resolve().parents[2] / "evals" / "grading"
CONFIGS_DIR = GRADING_DIR / "configs"
WORKFLOW_DIR = GRADING_DIR / "model" / "workflows" / "prototype"
REAL_CONFIGS = ("prototype_smoke.yaml", "prototype_small.yaml", "prototype_full.yaml", "prototype_partial.yaml")


def real_rubric() -> dict:
    """The shipped prototype-specify rubric, loaded through load_rubric."""
    return load_rubric(WORKFLOW_DIR, "prototype-specify")


def real_dataset() -> dict:
    """The shipped ten-industries dataset, loaded through load_dataset."""
    return load_dataset(
        "datasets/ten-industries.json",
        workflow_dir=WORKFLOW_DIR,
        agent_id="prototype-specify",
    )


def write_yaml(path: Path, data: dict) -> Path:
    """Dump a mapping to a YAML file and return the path."""
    path.write_text(yaml.safe_dump(data))
    return path


# ── run config ────────────────────────────────────────────────────────────


@pytest.mark.parametrize("name", REAL_CONFIGS)
def test_real_run_configs_load(name):
    config = load_run_config(CONFIGS_DIR / name, {})

    assert isinstance(config, RunConfig)
    assert config.track == "model"
    assert config.workflow == "prototype"
    assert config.overrides == {}
    # Derived, not hardcoded: configs are allowed to name different datasets,
    # but every one they name has to exist.
    dataset = GRADING_DIR / "model/workflows/prototype" / config.dataset
    assert dataset.is_file(), f"{name} points at a dataset that does not exist: {dataset}"


def test_agents_all_and_agents_list_both_parse():
    every = load_run_config(CONFIGS_DIR / "prototype_full.yaml", {})
    subset = load_run_config(CONFIGS_DIR / "prototype_partial.yaml", {})

    assert every.agents == "all"
    assert subset.agents == ["prototype-specify"]


def test_missing_path_produces_a_valid_config_from_defaults_and_cli():
    config = load_run_config(None, {"workflow": "prototype", "rows": ["billing_console"]})

    assert config.track == "model"
    assert config.agents == "all"
    assert config.options["concurrency"] == 3
    assert config.rows == ["billing_console"]
    assert config.overrides["rows"] == {"config": None, "cli": ["billing_console"]}


def test_merge_precedence_defaults_then_file_then_cli():
    config = load_run_config(
        CONFIGS_DIR / "prototype_partial.yaml",
        {"options": {"concurrency": 8}},
    )

    assert config.options["repeats"] == 1          # default, untouched
    assert config.options["no_judge"] is False     # from the file
    assert config.options["concurrency"] == 8      # from the CLI


def test_every_diverging_cli_value_is_recorded_as_an_override():
    # The "config" side of each override is read from the file rather than
    # hardcoded, so this survives a shipped config changing its values.
    baseline = load_run_config(CONFIGS_DIR / "prototype_partial.yaml", {})

    config = load_run_config(
        CONFIGS_DIR / "prototype_partial.yaml",
        {"limit": 999, "judge": {"model": "some-other-judge", "threshold": 60}},
    )

    assert config.overrides == {
        "limit": {"config": baseline.limit, "cli": 999},
        "judge.model": {"config": baseline.judge["model"], "cli": "some-other-judge"},
        "judge.threshold": {"config": baseline.judge["threshold"], "cli": 60},
    }


def test_cli_value_equal_to_the_config_is_not_an_override():
    # Read the config's own values rather than hardcoding them, so this keeps
    # testing "CLI == config records nothing" even when a shipped config changes.
    baseline = load_run_config(CONFIGS_DIR / "prototype_partial.yaml", {})

    config = load_run_config(
        CONFIGS_DIR / "prototype_partial.yaml",
        {
            "options": {"concurrency": baseline.options["concurrency"]},
            "agents": baseline.agents,
        },
    )

    assert config.overrides == {}


def test_unknown_key_is_rejected(tmp_path):
    path = write_yaml(tmp_path / "run.yaml", {"track": "model", "conccurency": 3})

    with pytest.raises(ValueError, match="conccurency"):
        load_run_config(path, {})


def test_invalid_track_is_rejected(tmp_path):
    path = write_yaml(tmp_path / "run.yaml", {"track": "prose"})

    with pytest.raises(ValueError, match="track"):
        load_run_config(path, {})


def test_missing_run_config_file_raises_clearly(tmp_path):
    with pytest.raises(ValueError, match="does not exist"):
        load_run_config(tmp_path / "nope.yaml", {})


# ── workflow + registry assertion ─────────────────────────────────────────


def test_registry_assertion_passes_on_the_real_workflow():
    workflow = load_workflow("prototype")

    assert [stage["agent_id"] for stage in workflow["stages"]][0] == "prototype-specify"
    assert workflow["workflow_dir"] == str(WORKFLOW_DIR)


def mutated_workflow(tmp_path, monkeypatch, mutate) -> None:
    """Copy the real workflow into a temp root, mutate it, and point config at it."""
    import evals.grading.config as config_module

    data = yaml.safe_load((WORKFLOW_DIR / "workflow.yaml").read_text())
    mutate(data)
    target = tmp_path / "prototype"
    target.mkdir()
    write_yaml(target / "workflow.yaml", data)
    monkeypatch.setattr(config_module, "WORKFLOWS_ROOT", tmp_path)


def test_registry_assertion_fails_on_reordered_stages(tmp_path, monkeypatch):
    def reorder(data):
        data["stages"][1], data["stages"][2] = data["stages"][2], data["stages"][1]

    mutated_workflow(tmp_path, monkeypatch, reorder)

    with pytest.raises(ValueError, match="drifted from the registry"):
        load_workflow("prototype")


def test_registry_assertion_fails_on_a_changed_from(tmp_path, monkeypatch):
    def retarget(data):
        data["stages"][1]["input"]["from"] = ["prototype-build"]

    mutated_workflow(tmp_path, monkeypatch, retarget)

    with pytest.raises(ValueError, match="consumes"):
        load_workflow("prototype")


def test_unknown_workflow_raises_clearly():
    with pytest.raises(ValueError, match="no workflow.yaml"):
        load_workflow("does-not-exist")


# ── rubric ────────────────────────────────────────────────────────────────


def test_real_rubric_loads_and_its_validate_hook_is_callable():
    rubric = real_rubric()

    assert rubric["agent_id"] == "prototype-specify"
    assert sum(d["weight"] for d in rubric["dimensions"]) == 100
    assert callable(rubric["validate_hook"])


def test_weights_not_summing_to_100_raise(tmp_path):
    rubric = yaml.safe_load((WORKFLOW_DIR / "prototype_specify_rubric.yaml").read_text())
    rubric["dimensions"][0]["weight"] = 45
    rubric["precheck"].pop("validate")
    write_yaml(tmp_path / "prototype_specify_rubric.yaml", rubric)

    with pytest.raises(ValueError, match="sum to 105"):
        load_rubric(tmp_path, "prototype-specify")


def test_uncompilable_forbidden_pattern_raises(tmp_path):
    rubric = yaml.safe_load((WORKFLOW_DIR / "prototype_specify_rubric.yaml").read_text())
    rubric["precheck"]["forbidden"].append({"pattern": "(unclosed", "reason": "bad"})
    rubric["precheck"].pop("validate")
    write_yaml(tmp_path / "prototype_specify_rubric.yaml", rubric)

    with pytest.raises(ValueError, match="not a valid regex"):
        load_rubric(tmp_path, "prototype-specify")


def test_forbidden_entry_without_a_reason_raises(tmp_path):
    rubric = yaml.safe_load((WORKFLOW_DIR / "prototype_specify_rubric.yaml").read_text())
    rubric["precheck"]["forbidden"].append({"pattern": "(?i)fixme"})
    rubric["precheck"].pop("validate")
    write_yaml(tmp_path / "prototype_specify_rubric.yaml", rubric)

    with pytest.raises(ValueError, match="has no reason"):
        load_rubric(tmp_path, "prototype-specify")


def test_anthropic_provider_warns_rather_than_raising(tmp_path):
    """A pin build_model cannot honour must warn, not raise — it silently falls
    through the implicit chain, so the warning is the only thing that says so.

    Built explicitly rather than read from a shipped rubric: every rubric now
    pins mistral, and a test that asserts what the repo happens to ship stops
    testing the behaviour the moment that choice changes.
    """
    rubric = yaml.safe_load((WORKFLOW_DIR / "prototype_specify_rubric.yaml").read_text())
    rubric["judge"] = {**rubric["judge"], "provider": "anthropic", "model": "claude-sonnet-5"}
    rubric["precheck"].pop("validate")
    write_yaml(tmp_path / "prototype_specify_rubric.yaml", rubric)
    rubric = load_rubric(tmp_path, "prototype-specify")

    assert rubric["judge"]["provider"] == "anthropic"
    assert "anthropic" in rubric["provider_warning"]


def test_every_shipped_rubric_pins_a_provider_build_model_honours():
    """A pin nothing can resolve makes every baseline verdict REFUSED forever."""
    from evals.grading import config as config_module
    from evals.grading.model import judge as judge_module

    workflow = config_module.load_workflow("prototype")
    for stage in workflow["stages"]:
        rubric = load_rubric(Path(workflow["workflow_dir"]), stage["agent_id"])
        provider = rubric["judge"]["provider"]
        assert provider in judge_module.HONOURED_PROVIDERS, (
            f"{stage['agent_id']} pins judge provider {provider!r}, which build_model "
            f"ignores — it would resolve to something else and refuse every baseline"
        )


def test_mistral_provider_produces_no_warning(tmp_path):
    rubric = yaml.safe_load((WORKFLOW_DIR / "prototype_specify_rubric.yaml").read_text())
    rubric["judge"]["provider"] = "mistral"
    rubric["precheck"].pop("validate")
    write_yaml(tmp_path / "prototype_specify_rubric.yaml", rubric)

    assert load_rubric(tmp_path, "prototype-specify")["provider_warning"] is None


def test_missing_rubric_raises_clearly(tmp_path):
    with pytest.raises(ValueError, match="no rubric at"):
        load_rubric(tmp_path, "prototype-plan")


# ── dataset ───────────────────────────────────────────────────────────────


def test_real_dataset_loads():
    dataset = real_dataset()

    assert dataset["dataset_id"] == "ten-industries"
    assert len(dataset["rows"]) == 12
    assert dataset["rows"][-1]["expect"] == "fail"


def test_absolute_and_relative_dataset_paths_agree():
    absolute = load_dataset(
        str(WORKFLOW_DIR / "datasets" / "ten-industries.json"),
        workflow_dir=Path("/nowhere"),
        agent_id="prototype-specify",
    )

    assert absolute == real_dataset()


def test_for_agent_mismatch_raises_naming_both():
    with pytest.raises(ValueError, match="prototype-specify.*prototype-plan"):
        load_dataset(
            "datasets/ten-industries.json",
            workflow_dir=WORKFLOW_DIR,
            agent_id="prototype-plan",
        )


def write_dataset(tmp_path: Path, rows: list[dict]) -> Path:
    """Write a minimal dataset file with the given rows."""
    path = tmp_path / "rows.json"
    path.write_text(json.dumps({"dataset_id": "tiny", "rows": rows}))
    return path


def row(row_id: str) -> dict:
    """A minimal valid dataset row."""
    return {"id": row_id, "industry": "SaaS", "prompt": "Build a console."}


def test_duplicate_row_id_raises(tmp_path):
    write_dataset(tmp_path, [row("a"), row("a")])

    with pytest.raises(ValueError, match="duplicate row id 'a'"):
        load_dataset("rows.json", workflow_dir=tmp_path, agent_id="prototype-specify")


def test_agent_suffixed_row_id_raises(tmp_path):
    write_dataset(tmp_path, [row("billing_console_plan")])

    with pytest.raises(ValueError, match="agent suffix"):
        load_dataset("rows.json", workflow_dir=tmp_path, agent_id="prototype-specify")


def test_row_missing_a_required_field_raises(tmp_path):
    write_dataset(tmp_path, [{"id": "a", "industry": "SaaS"}])

    with pytest.raises(ValueError, match="has no 'prompt'"):
        load_dataset("rows.json", workflow_dir=tmp_path, agent_id="prototype-specify")


def test_missing_dataset_file_raises_clearly(tmp_path):
    with pytest.raises(ValueError, match="not found"):
        load_dataset("datasets/absent.json", workflow_dir=tmp_path, agent_id="x")


# ── hashes ────────────────────────────────────────────────────────────────


def test_rubric_hash_ignores_baseline_but_tracks_dimensions():
    config = load_run_config(CONFIGS_DIR / "prototype_partial.yaml", {})
    rubric = real_rubric()
    dataset = real_dataset()
    original = compute_hashes(config, rubric, dataset)["rubric_hash"]

    ratcheted = copy.deepcopy(rubric)
    ratcheted["baseline"]["min_average_score"] = 85
    assert compute_hashes(config, ratcheted, dataset)["rubric_hash"] == original

    reweighted = copy.deepcopy(rubric)
    reweighted["dimensions"][0]["weight"] = 30
    reweighted["dimensions"][1]["weight"] = 50
    assert compute_hashes(config, reweighted, dataset)["rubric_hash"] != original


def test_dataset_hash_changes_when_a_prompt_changes():
    config = load_run_config(CONFIGS_DIR / "prototype_partial.yaml", {})
    rubric = real_rubric()
    dataset = real_dataset()
    original = compute_hashes(config, rubric, dataset)["dataset_hash"]

    edited = copy.deepcopy(dataset)
    edited["rows"][0]["prompt"] += " Also show churn."

    assert compute_hashes(config, rubric, edited)["dataset_hash"] != original


def test_hashes_are_stable_across_key_reordering():
    config = load_run_config(CONFIGS_DIR / "prototype_partial.yaml", {})
    rubric = real_rubric()
    dataset = real_dataset()
    original = compute_hashes(config, rubric, dataset)

    shuffled_rubric = dict(reversed(list(rubric.items())))
    shuffled_dataset = copy.deepcopy(dataset)
    shuffled_dataset["rows"] = [
        dict(reversed(list(r.items()))) for r in shuffled_dataset["rows"]
    ]

    assert compute_hashes(config, shuffled_rubric, shuffled_dataset) == original


def test_all_three_hashes_are_sha256_prefixed():
    hashes = compute_hashes(
        load_run_config(CONFIGS_DIR / "prototype_partial.yaml", {}),
        real_rubric(),
        real_dataset(),
    )

    assert set(hashes) == {"config_hash", "rubric_hash", "dataset_hash"}
    assert all(value.startswith("sha256:") and len(value) == 71 for value in hashes.values())


def test_config_hash_changes_with_a_setting_but_not_with_provenance():
    base = load_run_config(CONFIGS_DIR / "prototype_partial.yaml", {})
    # Drive a DIFFERENT file to byte-identical settings purely through CLI
    # overrides — the point being that `overrides` is provenance, not a setting,
    # so two runs that arrive at the same place compare equal.
    same_settings_via_cli = load_run_config(
        CONFIGS_DIR / "prototype_full.yaml",
        {
            "run_id": base.run_id,
            "agents": base.agents,
            "rows": base.rows,
            "limit": base.limit,
            "dataset": base.dataset,
            "agent_under_test": dict(base.agent_under_test),
            "judge": dict(base.judge),
            "options": dict(base.options),
        },
    )
    different = load_run_config(CONFIGS_DIR / "prototype_partial.yaml", {"limit": 99})
    rubric, dataset = real_rubric(), real_dataset()

    assert compute_hashes(same_settings_via_cli, rubric, dataset)["config_hash"] == (
        compute_hashes(base, rubric, dataset)["config_hash"]
    )
    assert compute_hashes(different, rubric, dataset)["config_hash"] != (
        compute_hashes(base, rubric, dataset)["config_hash"]
    )


# ── the small debugging fixture ───────────────────────────────────────────


def test_every_shipped_config_is_reachable_by_its_own_name():
    """A shipped config with no `grade.sh` arm is invisible to anyone using it.

    Configs are named `<workflow>_<name>.yaml` and `_config_path` resolves the
    SHORT name (`grade.sh all` -> `prototype_all.yaml`), so the arm to look for
    is the part after the workflow prefix — checked here against whichever of
    the two spellings a config uses, never assuming the prefix is present.
    """
    shipped = {path.name for path in CONFIGS_DIR.glob("*.yaml")}
    arm = (GRADING_DIR / "grade.sh").read_text()

    for filename in sorted(shipped):
        stem = filename.removesuffix(".yaml")
        short = stem.split("_", 1)[1] if "_" in stem else stem
        assert any(
            token in arm
            for name in (stem, short)
            for token in (f"{name}|", f"|{name})", f"|{name}|")
        ), f"{filename} ships but grade.sh has no subcommand arm for it (tried {short!r})"


def test_small_config_is_cheap_and_judged():
    """The debug loop must exercise the judge — otherwise it proves nothing."""
    config = load_run_config(CONFIGS_DIR / "prototype_small.yaml", {})

    assert config.options["no_judge"] is False
    assert config.dataset.endswith("small.json")


def test_small_dataset_is_all_interaction_briefs():
    """Every row is a compact positive that demands working interactions.

    The count is deliberately not pinned — rows get added to this dataset as new
    interaction shapes are worth exercising. What must hold is that `small` stays
    all-positive: the negative test lives in ten-industries, and a `fail` row here
    would silently drag the debugging loop's averages down."""
    dataset = json.loads(
        (
            GRADING_DIR / "model/workflows/prototype/datasets/prototype_small.json"
        ).read_text(encoding="utf-8")
    )

    assert dataset["dataset_id"] == "prototype_small"
    assert dataset["for_agent"] == "prototype-specify"
    assert len(dataset["rows"]) >= 2
    assert not any(row.get("expect") == "fail" for row in dataset["rows"])


def test_small_dataset_says_its_scores_are_not_comparable():
    """The briefs cap their own size, so the numbers mean something different."""
    dataset = json.loads(
        (
            GRADING_DIR / "model/workflows/prototype/datasets/prototype_small.json"
        ).read_text(encoding="utf-8")
    )

    assert "not comparable" in dataset["description"].lower()
    for row in dataset["rows"]:
        # Each brief must demand verifiable behaviour — a dynamic detail route
        # the code track can actually click — so scores have room to
        # differentiate. Assert the ROUTE, not the words "dynamic route": the
        # briefs express it as `#/sku/:id` or `#/job/:id`, and pinning the prose
        # made this fail the moment a brief said the same thing in route syntax.
        assert re.search(r"#/\w+/:\w+", row["prompt"]), (
            f"row {row['id']!r} declares no dynamic detail route"
        )
