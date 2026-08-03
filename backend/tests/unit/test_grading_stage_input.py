"""Unit tests for evals.grading.stage_input — the five input shapes.

Offline and fast: no model calls and no run folder, only loaded envelopes as
dicts. Uses the real `workflow.yaml` stages and the real dataset where possible,
so a config edit that breaks the fan-in join fails here rather than in a run.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from evals.grading.model.stage_input import StageInput, build_stage_inputs

WORKFLOW_DIR = (
    Path(__file__).resolve().parents[2]
    / "evals"
    / "grading"
    / "model"
    / "workflows"
    / "prototype"
)

# The committed 11-row run the "real artifacts" tests read. It is not currently
# on disk, so those tests skip rather than fail — regenerating it re-arms them.
EXAMPLE_RUN = WORKFLOW_DIR / "example-run"

ADAPTER_SOURCE = """
def build_prompt(row, upstreams):
    return f"[{row['id']}] {len(upstreams)} upstream(s): " + upstreams['prototype-plan']


def derive_design(row, upstreams):
    return f"design for {row['id']}"
"""


def load_workflow() -> dict:
    """Read the real prototype workflow manifest."""
    return yaml.safe_load((WORKFLOW_DIR / "workflow.yaml").read_text())


def stage_for(agent_id: str) -> dict:
    """Pick one stage out of the real workflow by agent id."""
    stages = load_workflow()["stages"]
    return next(stage for stage in stages if stage["agent_id"] == agent_id)


def real_dataset() -> dict:
    """Read the real ten-industries dataset envelope."""
    path = WORKFLOW_DIR / "datasets" / "ten-industries.json"
    return json.loads(path.read_text())


def real_specify_output() -> dict:
    """Read the real prototype-specify output envelope from example-run/."""
    path = WORKFLOW_DIR / "example-run" / "artifacts" / "prototype_specify_output.json"
    return json.loads(path.read_text())


def dataset(*rows: dict) -> dict:
    """Build a minimal dataset envelope from row dicts."""
    return {"dataset_id": "test", "rows": list(rows)}


def row(row_id: str, **fields) -> dict:
    """Build a dataset row with sensible defaults."""
    return {
        "id": row_id,
        "industry": fields.pop("industry", "Testing"),
        "tags": fields.pop("tags", ["tag-a"]),
        "prompt": fields.pop("prompt", f"brief for {row_id}"),
        **fields,
    }


def output(agent_id: str, *rows: dict) -> dict:
    """Build an upstream output envelope from row dicts."""
    return {"dataset_id": "test", "source_agent": agent_id, "rows": list(rows)}


def upstream_row(row_id: str, text: str, **fields) -> dict:
    """Build an upstream output row (its `prompt` is that agent's response)."""
    return {
        "id": row_id,
        "industry": "Testing",
        "tags": ["tag-a"],
        "prompt": text,
        "upstream_precheck_passed": fields.pop("upstream_precheck_passed", True),
        "upstream_score": fields.pop("upstream_score", 90),
        **fields,
    }


@pytest.fixture
def adapter_dir(tmp_path: Path) -> Path:
    """A config dir holding a workflow.yaml sibling hook file."""
    (tmp_path / "workflow.yaml").write_text("stages: []\n")
    (tmp_path / "adapter.py").write_text(ADAPTER_SOURCE)
    return tmp_path


# ── shape 1: dataset source ──────────────────────────────────────────────


def test_dataset_source_yields_one_input_per_row_verbatim():
    """The root stage forwards every dataset row's prompt unchanged."""
    data = real_dataset()

    inputs = build_stage_inputs(
        stage_for("prototype-specify"), dataset=data, upstream_outputs={}
    )

    assert len(inputs) == len(data["rows"])
    assert [item.row_id for item in inputs] == [r["id"] for r in data["rows"]]
    assert [item.prompt for item in inputs] == [r["prompt"] for r in data["rows"]]
    assert all(isinstance(item, StageInput) for item in inputs)
    assert all(item.skip_reason is None for item in inputs)


def test_dataset_source_carries_row_metadata():
    """industry, tags and expect come from the dataset row."""
    data = real_dataset()

    inputs = build_stage_inputs(
        stage_for("prototype-specify"), dataset=data, upstream_outputs={}
    )

    by_id = {item.row_id: item for item in inputs}
    assert by_id["billing_console"].industry == "SaaS Billing"
    assert "admin-console" in by_id["billing_console"].tags
    assert by_id["billing_console"].expect == "pass"
    assert by_id["underspecified_brief"].expect == "fail"


# ── shape 2: single upstream ─────────────────────────────────────────────


@pytest.mark.skipif(not EXAMPLE_RUN.exists(), reason="the committed example-run fixture is not on disk")
def test_single_upstream_prompt_is_the_response_verbatim():
    """A linear hop forwards the upstream response with no wrapping."""
    data = real_dataset()
    specify = real_specify_output()
    expected = specify["rows"][0]["prompt"]

    inputs = build_stage_inputs(
        stage_for("prototype-plan"),
        dataset=data,
        upstream_outputs={"prototype-specify": specify},
    )

    by_id = {item.row_id: item for item in inputs}
    assert by_id["billing_console"].prompt == expected
    assert by_id["billing_console"].skip_reason is None


def test_upstream_chain_populated_for_a_two_stage_chain():
    """Every row records which upstream produced it, with precheck and score."""
    inputs = build_stage_inputs(
        stage_for("prototype-plan"),
        dataset=dataset(row("r1")),
        upstream_outputs={
            "prototype-specify": output(
                "prototype-specify",
                upstream_row("r1", "spec text", upstream_score=87),
            )
        },
    )

    assert inputs[0].upstream_chain == [
        {"agent": "prototype-specify", "precheck_passed": True, "score": 87}
    ]


# ── shape 3: fan-in inner join ───────────────────────────────────────────


FAN_IN_STAGE = {
    "agent_id": "prototype-analyze",
    "input": {
        "source": "upstream",
        "from": ["prototype-plan", "prototype-specify"],
        "template": "{prototype-specify}\n\n{prototype-plan}\n",
    },
}


def test_fan_in_joins_rows_by_id_in_template_order():
    """`from:` order is irrelevant — the template decides what comes first."""
    inputs = build_stage_inputs(
        FAN_IN_STAGE,
        dataset=dataset(row("r1"), row("r2")),
        upstream_outputs={
            "prototype-specify": output(
                "prototype-specify",
                upstream_row("r2", "SPEC-TWO"),
                upstream_row("r1", "SPEC-ONE"),
            ),
            "prototype-plan": output(
                "prototype-plan",
                upstream_row("r1", "TASKS-ONE"),
                upstream_row("r2", "TASKS-TWO"),
            ),
        },
    )

    by_id = {item.row_id: item for item in inputs}
    prompt = by_id["r1"].prompt
    assert "SPEC-ONE" in prompt and "TASKS-ONE" in prompt
    assert prompt.index("SPEC-ONE") < prompt.index("TASKS-ONE")
    assert "SPEC-TWO" not in prompt and "TASKS-TWO" not in prompt
    assert by_id["r2"].prompt.strip() == "SPEC-TWO\n\nTASKS-TWO"


def test_real_workflow_fan_in_stage_composes():
    """The shipped analyze stage joins the two real upstreams for one row."""
    inputs = build_stage_inputs(
        stage_for("prototype-analyze"),
        dataset=dataset(row("r1")),
        upstream_outputs={
            "prototype-specify": output(
                "prototype-specify", upstream_row("r1", "SPEC")
            ),
            "prototype-plan": output("prototype-plan", upstream_row("r1", "TASKS")),
        },
    )

    assert inputs[0].prompt.strip() == "SPEC\n\nTASKS"


def test_row_missing_from_one_upstream_is_returned_with_a_skip_reason():
    """A half-joined row is never dropped — row counts must match across stages."""
    data = dataset(row("r1"), row("r2"), row("r3"))

    inputs = build_stage_inputs(
        FAN_IN_STAGE,
        dataset=data,
        upstream_outputs={
            "prototype-specify": output(
                "prototype-specify",
                upstream_row("r1", "SPEC-ONE"),
                upstream_row("r2", "SPEC-TWO"),
                upstream_row("r3", "SPEC-THREE"),
            ),
            "prototype-plan": output(
                "prototype-plan",
                upstream_row("r1", "TASKS-ONE"),
                upstream_row("r3", "TASKS-THREE"),
            ),
        },
    )

    assert len(inputs) == len(data["rows"])
    by_id = {item.row_id: item for item in inputs}
    assert by_id["r2"].skip_reason == "row missing from upstream 'prototype-plan'"
    assert by_id["r2"].prompt == ""
    assert by_id["r1"].skip_reason is None
    assert by_id["r3"].skip_reason is None


def test_several_upstreams_without_a_template_raises():
    """Never concatenate in `from:` order — a fan-in must state its ordering."""
    stage = {
        "agent_id": "x",
        "input": {"source": "upstream", "from": ["a", "b"]},
    }

    with pytest.raises(ValueError, match="no 'template'"):
        build_stage_inputs(stage, dataset=dataset(row("r1")), upstream_outputs={})


def test_unknown_placeholder_raises_at_load_time():
    """A template naming an agent that is not in `from:` is a config error."""
    stage = {
        "agent_id": "x",
        "input": {"source": "upstream", "from": ["a", "b"], "template": "{a}{c}{b}"},
    }

    with pytest.raises(ValueError, match="unknown placeholder"):
        build_stage_inputs(stage, dataset=dataset(row("r1")), upstream_outputs={})


def test_from_entry_without_a_placeholder_raises_at_load_time():
    """An upstream declared but never substituted would be silently discarded."""
    stage = {
        "agent_id": "x",
        "input": {"source": "upstream", "from": ["a", "b"], "template": "{a}"},
    }

    with pytest.raises(ValueError, match="no placeholder"):
        build_stage_inputs(stage, dataset=dataset(row("r1")), upstream_outputs={})


# ── shape 4: adapter ─────────────────────────────────────────────────────


def test_adapter_runs_after_composition_and_owns_the_prompt(adapter_dir: Path):
    """The adapter receives (row, upstreams) and its return value is the prompt."""
    stage = {
        "agent_id": "prototype-build",
        "input": {
            "source": "upstream",
            "from": ["prototype-plan"],
            "adapter": "./adapter.py:build_prompt",
        },
    }

    inputs = build_stage_inputs(
        stage,
        dataset=dataset(row("r1")),
        upstream_outputs={
            "prototype-plan": output("prototype-plan", upstream_row("r1", "TASKS"))
        },
        config_dir=adapter_dir,
    )

    assert inputs[0].prompt == "[r1] 1 upstream(s): TASKS"


def test_adapter_declared_without_a_config_dir_raises():
    """A hook that cannot be resolved must fail at load time, not at dispatch."""
    stage = {
        "agent_id": "x",
        "input": {"source": "upstream", "from": ["a"], "adapter": "./adapter.py:build_prompt"},
    }

    with pytest.raises(ValueError, match="no config_dir"):
        build_stage_inputs(stage, dataset=dataset(row("r1")), upstream_outputs={})


# ── shape 5: seed files ──────────────────────────────────────────────────


def test_seed_files_resolved_from_an_upstream_outside_the_from_list():
    """The real build stage seeds spec.md from prototype-specify."""
    inputs = build_stage_inputs(
        {
            "agent_id": "prototype-build",
            "input": {
                "source": "upstream",
                "from": ["prototype-plan"],
                "seed_files": {"spec.md": "prototype-specify"},
            },
            "deliverable_file": "prototype.html",
        },
        dataset=dataset(row("r1")),
        upstream_outputs={
            "prototype-plan": output("prototype-plan", upstream_row("r1", "TASKS")),
            "prototype-specify": output(
                "prototype-specify", upstream_row("r1", "SPEC")
            ),
        },
    )

    assert inputs[0].seed_files == {"spec.md": "SPEC"}
    assert inputs[0].deliverable_file == "prototype.html"
    assert [entry["agent"] for entry in inputs[0].upstream_chain] == [
        "prototype-plan",
        "prototype-specify",
    ]


def test_seed_files_resolved_through_a_derivation_hook(adapter_dir: Path):
    """A `./file.py:func` seed value derives the content per row."""
    inputs = build_stage_inputs(
        {
            "agent_id": "prototype-build",
            "input": {
                "source": "upstream",
                "from": ["prototype-plan"],
                "seed_files": {"design.md": "./adapter.py:derive_design"},
            },
        },
        dataset=dataset(row("r1")),
        upstream_outputs={
            "prototype-plan": output("prototype-plan", upstream_row("r1", "TASKS"))
        },
        config_dir=adapter_dir,
    )

    assert inputs[0].seed_files == {"design.md": "design for r1"}


# ── skip policy ──────────────────────────────────────────────────────────


@pytest.mark.skipif(not EXAMPLE_RUN.exists(), reason="the committed example-run fixture is not on disk")
def test_expect_fail_row_runs_at_the_root_and_is_skipped_downstream():
    """A row meant to be rejected must never propagate into a later stage."""
    data = real_dataset()
    specify = real_specify_output()

    root = build_stage_inputs(
        stage_for("prototype-specify"), dataset=data, upstream_outputs={}
    )
    downstream = build_stage_inputs(
        stage_for("prototype-plan"),
        dataset=data,
        upstream_outputs={"prototype-specify": specify},
    )

    root_negative = next(i for i in root if i.row_id == "underspecified_brief")
    assert root_negative.skip_reason is None
    assert root_negative.prompt

    downstream_negative = next(
        i for i in downstream if i.row_id == "underspecified_brief"
    )
    assert downstream_negative.skip_reason == (
        "expect: fail row is not propagated to a downstream stage"
    )
    assert len(downstream) == len(data["rows"])


@pytest.mark.parametrize("policy", ["skip", "run_anyway"])
def test_errored_upstream_row_is_always_skipped(policy: str):
    """There is no text to forward, so `run_anyway` cannot rescue an error."""
    stage = {
        "agent_id": "x",
        "on_upstream_failure": policy,
        "input": {"source": "upstream", "from": ["up"]},
    }

    inputs = build_stage_inputs(
        stage,
        dataset=dataset(row("r1")),
        upstream_outputs={
            "up": output("up", upstream_row("r1", "", errored=True, upstream_score=None))
        },
    )

    assert inputs[0].skip_reason == "upstream 'up' errored"
    assert inputs[0].prompt == ""


def test_precheck_failed_upstream_is_skipped_by_default():
    """`on_upstream_failure` defaults to skip."""
    stage = {"agent_id": "x", "input": {"source": "upstream", "from": ["up"]}}

    inputs = build_stage_inputs(
        stage,
        dataset=dataset(row("r1")),
        upstream_outputs={
            "up": output(
                "up",
                upstream_row("r1", "TEXT", upstream_precheck_passed=False, upstream_score=41),
            )
        },
    )

    assert inputs[0].skip_reason == "upstream 'up' failed precheck"
    assert inputs[0].upstream_chain == [
        {"agent": "up", "precheck_passed": False, "score": 41}
    ]


def test_precheck_failed_upstream_runs_with_run_anyway():
    """`run_anyway` keeps the row, prompt intact, chain still showing the failure."""
    stage = {
        "agent_id": "x",
        "on_upstream_failure": "run_anyway",
        "input": {"source": "upstream", "from": ["up"]},
    }

    inputs = build_stage_inputs(
        stage,
        dataset=dataset(row("r1")),
        upstream_outputs={
            "up": output(
                "up", upstream_row("r1", "TEXT", upstream_precheck_passed=False)
            )
        },
    )

    assert inputs[0].skip_reason is None
    assert inputs[0].prompt == "TEXT"
    assert inputs[0].upstream_chain[0]["precheck_passed"] is False


def test_unknown_failure_policy_raises():
    """A typo in `on_upstream_failure` must not silently mean skip."""
    stage = {
        "agent_id": "x",
        "on_upstream_failure": "continue",
        "input": {"source": "upstream", "from": ["up"]},
    }

    with pytest.raises(ValueError, match="on_upstream_failure"):
        build_stage_inputs(stage, dataset=dataset(row("r1")), upstream_outputs={})


def test_missing_upstream_output_is_reported_not_ignored():
    """A stage whose upstream never ran must not fall back to the dataset prompt."""
    stage = {"agent_id": "x", "input": {"source": "upstream", "from": ["up"]}}

    inputs = build_stage_inputs(
        stage, dataset=dataset(row("r1")), upstream_outputs={}
    )

    assert inputs[0].skip_reason == "upstream 'up' did not run for this dataset"
    assert inputs[0].prompt == ""


def test_blank_upstream_text_is_treated_as_no_text_to_forward():
    """An empty response is an error upstream; downstream it is nothing to send."""
    stage = {"agent_id": "x", "input": {"source": "upstream", "from": ["up"]}}

    inputs = build_stage_inputs(
        stage,
        dataset=dataset(row("r1")),
        upstream_outputs={"up": output("up", upstream_row("r1", "   "))},
    )

    assert inputs[0].skip_reason == "upstream 'up' produced no text"


def test_propagate_expected_fail_lets_the_negative_row_flow_downstream():
    """Opt-in observation mode: the bad brief runs every stage, even though its
    own upstream output failed precheck (that failure is the eval working)."""
    data = dataset(
        row("good_row"),
        row("underspecified_brief", expect="fail", prompt="Build me an app."),
    )
    upstream = output(
        "prototype-specify",
        upstream_row("good_row", "<spec>a real spec</spec>"),
        upstream_row(
            "underspecified_brief",
            "I need more detail before I can specify this.",
            upstream_precheck_passed=False,
        ),
    )

    held = build_stage_inputs(
        stage_for("prototype-plan"), dataset=data,
        upstream_outputs={"prototype-specify": upstream},
    )
    flowing = build_stage_inputs(
        stage_for("prototype-plan"), dataset=data,
        upstream_outputs={"prototype-specify": upstream},
        propagate_expected_fail=True,
    )

    assert next(i for i in held if i.row_id == "underspecified_brief").skip_reason
    negative = next(i for i in flowing if i.row_id == "underspecified_brief")
    assert negative.skip_reason is None
    assert negative.prompt == "I need more detail before I can specify this."
    assert negative.expect == "fail"
    # The positive row's policy is untouched by the flag.
    assert next(i for i in flowing if i.row_id == "good_row").skip_reason is None
