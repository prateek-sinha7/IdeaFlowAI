"""Unit/CLI-integration tests for evals.model_graded.cli — the
`graded`/`report` subcommands, including Story 6's `--samples`/`--worst`/
`--by`/`--target`, the agent-under-test `--provider`/`--model` override,
and the per-run-folder `run.json`/`grade.json` storage (revised per user
request: readable files inside each run's own log folder, not one growing
JSONL) — tasks T12, T13, T15, T16.

Monkeypatches the names cli.py imported into its own namespace (driver /
judge / report functions) rather than driving the real deepagents graph or
a real model — proves cli.py's own orchestration logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from evals.model_graded import cli as cli_mod
from evals.model_graded import report as report_mod
from evals.model_graded.driver import GradedScenario


@dataclass
class _FakeResult:
    scenario_id: str
    agent_id: str
    response: str
    errored: bool
    error_reason: str | None
    tokens_in: int
    tokens_out: int
    run_dir: str
    run_id: str = ""
    resolved_model_id: str = "claude-haiku-4-5-20251001"


def _scenario(precheck_module=None) -> GradedScenario:
    return GradedScenario(
        id="s1",
        agent_id="prototype-specify",
        prompt="brief",
        precheck_config={"wrapper": "<spec>", "min_sections": 1, "section_pattern": "^### ", "forbidden": []},
        rubric="grade this",
        precheck_module=precheck_module,
    )


@pytest.fixture()
def fake_scenarios(monkeypatch):
    scenarios = {"s1": _scenario()}
    monkeypatch.setattr(cli_mod, "discover_all_scenarios", lambda: scenarios)
    return scenarios


class _DriverCalls(list):
    """A ``list`` of dispatched scenarios that ALSO tracks the ``run_dir``
    each dispatch was given — plain ``list`` can't carry the extra attribute."""

    def __init__(self):
        super().__init__()
        self.seen_run_dirs: list = []


@pytest.fixture()
def fake_driver(monkeypatch, tmp_path):
    calls = _DriverCalls()

    async def _fake_run(scenario, *, run_dir=None, log_filename=None, **kwargs):
        calls.append(scenario)
        calls.seen_run_dirs.append(run_dir)
        resolved_run_dir = Path(run_dir) if run_dir is not None else tmp_path / f"run-{len(calls)}"
        return _FakeResult(
            scenario_id=scenario.id,
            agent_id=scenario.agent_id,
            response="<spec>\n### Page\n</spec>",
            errored=False,
            error_reason=None,
            tokens_in=1,
            tokens_out=2,
            run_dir=str(resolved_run_dir),
            run_id=f"fake-run-{len(calls)}-{scenario.id}",
        )

    monkeypatch.setattr(cli_mod, "run_graded_scenario_once", _fake_run)
    return calls


@pytest.fixture()
def fake_judge(monkeypatch):
    calls = []

    async def _fake_grade(scenario, result, precheck_reason, **kwargs):
        calls.append((scenario, result, precheck_reason))

        class _Verdict:
            score = 88
            passed = True
            rationale = "solid"
            strengths = ["realistic data"]
            weaknesses = ["dashboard is generic"]
            resolved_model_id = "claude-haiku-4-5-20251001"
            errored = False
            error_reason = None

        return _Verdict()

    monkeypatch.setattr(cli_mod, "grade_run", _fake_grade)
    return calls


@pytest.fixture(autouse=True)
def _fake_system_prompt(monkeypatch, tmp_path):
    monkeypatch.setattr(cli_mod, "_BACKEND", tmp_path.parent)
    agent_dir = tmp_path.parent / "agents" / "prompts" / "prototype-specify"
    agent_dir.mkdir(parents=True, exist_ok=True)
    (agent_dir / "AGENT.md").write_text("sys")

    import agents.loader as loader_module

    monkeypatch.setattr(loader_module, "load_agent_spec", lambda agent_id: object())


def _run_json(run_dir_str: str) -> dict:
    import json
    from pathlib import Path

    return json.loads((Path(run_dir_str) / "run.json").read_text())


def _grade_json(run_dir_str: str) -> dict:
    import json
    from pathlib import Path

    return json.loads((Path(run_dir_str) / "grade.json").read_text())


def test_graded_with_judge_writes_run_and_grade_json(fake_scenarios, fake_driver, fake_judge, tmp_path):
    exit_code = cli_mod.main(["graded", "s1", "--judge"])
    assert exit_code == 0

    run_dir = tmp_path / "run-1"
    run = _run_json(str(run_dir))
    grade = _grade_json(str(run_dir))

    assert run["prompt"] == "brief"
    assert run["response"] == "<spec>\n### Page\n</spec>"
    assert grade["score"] == 88
    assert grade["strengths"] == ["realistic data"]
    assert grade["weaknesses"] == ["dashboard is generic"]


def test_graded_without_judge_writes_run_json_only(fake_scenarios, fake_driver, tmp_path):
    exit_code = cli_mod.main(["graded", "s1"])
    assert exit_code == 0

    run_dir = tmp_path / "run-1"
    assert (run_dir / "run.json").exists()
    assert not (run_dir / "grade.json").exists()


def test_graded_samples_n_produces_n_run_folders(fake_scenarios, fake_driver, fake_judge, tmp_path):
    cli_mod.main(["graded", "s1", "--judge", "--samples", "3"])
    for i in (1, 2, 3):
        run_dir = tmp_path / f"run-{i}"
        assert (run_dir / "run.json").exists()
        assert (run_dir / "grade.json").exists()


def test_graded_judge_without_credentials_never_calls_driver(fake_scenarios, monkeypatch):
    calls = []

    async def _fake_run(scenario, **kwargs):
        calls.append(scenario)
        raise AssertionError("driver should not be called")

    monkeypatch.setattr(cli_mod, "run_graded_scenario_once", _fake_run)
    monkeypatch.setattr(cli_mod, "_has_judge_credentials", lambda: False)

    exit_code = cli_mod.main(["graded", "s1", "--judge"])
    assert exit_code == 1
    assert calls == []


def test_graded_provider_without_credentials_never_calls_driver(fake_scenarios, monkeypatch):
    """--provider overrides the AGENT UNDER TEST's model (distinct from
    --judge-provider, which only ever affects grading) — missing credentials
    for it must fail before dispatch, same as the judge-credential guard."""
    calls = []

    async def _fake_run(scenario, **kwargs):
        calls.append(scenario)
        raise AssertionError("driver should not be called")

    monkeypatch.setattr(cli_mod, "run_graded_scenario_once", _fake_run)
    monkeypatch.setattr(cli_mod, "_has_provider_credentials", lambda provider: False)

    exit_code = cli_mod.main(["graded", "s1", "--provider", "mistral"])
    assert exit_code == 1
    assert calls == []


def test_graded_provider_passes_through_to_driver(fake_scenarios, monkeypatch, tmp_path):
    captured = {}

    async def _fake_run(scenario, **kwargs):
        captured.update(kwargs)
        run_dir = tmp_path / "run-1"
        return _FakeResult(
            scenario_id=scenario.id,
            agent_id=scenario.agent_id,
            response="<spec>\n### Page\n</spec>",
            errored=False,
            error_reason=None,
            tokens_in=1,
            tokens_out=2,
            run_dir=str(run_dir),
        )

    monkeypatch.setattr(cli_mod, "run_graded_scenario_once", _fake_run)
    monkeypatch.setattr(cli_mod, "_has_provider_credentials", lambda provider: True)

    cli_mod.main(["graded", "s1", "--provider", "mistral", "--model", "mistral-large-latest"])
    assert captured["provider"] == "mistral"
    assert captured["model"] == "mistral-large-latest"


@pytest.fixture()
def fake_dataset_scenarios(monkeypatch):
    scenarios = {
        "s1": _scenario(),
        "s2": GradedScenario(
            id="s2",
            agent_id="prototype-specify",
            prompt="brief 2",
            precheck_config={
                "wrapper": "<spec>",
                "min_sections": 1,
                "section_pattern": "^### ",
                "forbidden": [],
            },
            rubric="grade this",
        ),
    }
    monkeypatch.setattr(cli_mod, "discover_all_scenarios", lambda: scenarios)
    monkeypatch.setattr(
        cli_mod,
        "find_dataset_scenarios",
        lambda agent_id, dataset_name="dataset": sorted(
            (s for s in scenarios.values() if s.agent_id == agent_id), key=lambda s: s.id
        ),
    )
    # _next_agent_id walks the REAL agents/registry.py — irrelevant to what
    # these tests are checking (dataset-run I/O), and the autouse
    # _fake_system_prompt fixture's mocked loader isn't shaped for it.
    monkeypatch.setattr(cli_mod, "_next_agent_id", lambda agent_id: None)
    return scenarios


def test_dataset_writes_one_run_folder_with_arrays_and_score(
    fake_dataset_scenarios, fake_driver, fake_judge, tmp_path, monkeypatch
):
    monkeypatch.setattr(report_mod, "DEFAULT_LOGS_ROOT", tmp_path / "logs")

    exit_code = cli_mod.main(["dataset", "prototype-specify", "--judge"])
    assert exit_code == 0

    logs_root = tmp_path / "logs"
    run_folders = list(logs_root.iterdir())
    assert len(run_folders) == 1, "one dataset invocation must produce exactly ONE run folder"
    run_dir = run_folders[0]
    assert "dataset-prototype-specify" in run_dir.name

    import json

    runs = json.loads((run_dir / "run.json").read_text())
    grades = json.loads((run_dir / "grade.json").read_text())
    score = json.loads((run_dir / "score.json").read_text())

    assert isinstance(runs, list) and len(runs) == 2
    assert isinstance(grades, list) and len(grades) == 2
    assert {r["scenario_id"] for r in runs} == {"s1", "s2"}
    assert all(g["score"] == 88 for g in grades)
    assert score["scenario_count"] == 2
    assert score["average_judge_score"] == 88
    assert len(score["results"]) == 2

    # every dataset item's dispatch was actually routed into the SAME
    # shared folder (not a fresh one per item) — this is what would fail if
    # the driver call ever stopped receiving run_dir=<the batch folder>.
    assert {p.name for p in run_dir.iterdir()} >= {"run.json", "grade.json", "score.json"}
    assert fake_driver.seen_run_dirs == [run_dir, run_dir]


def test_dataset_without_judge_writes_only_run_json_array(
    fake_dataset_scenarios, fake_driver, tmp_path, monkeypatch
):
    monkeypatch.setattr(report_mod, "DEFAULT_LOGS_ROOT", tmp_path / "logs")

    exit_code = cli_mod.main(["dataset", "prototype-specify"])
    assert exit_code == 0

    run_dir = next((tmp_path / "logs").iterdir())
    assert (run_dir / "run.json").exists()
    assert not (run_dir / "grade.json").exists()
    assert (run_dir / "score.json").exists()


def test_dataset_name_arg_threads_through_to_find_dataset_scenarios_and_run_folder(
    fake_driver, tmp_path, monkeypatch
):
    monkeypatch.setattr(report_mod, "DEFAULT_LOGS_ROOT", tmp_path / "logs")
    monkeypatch.setattr(cli_mod, "_next_agent_id", lambda agent_id: None)

    captured = {}

    def _fake_find(agent_id, dataset_name="dataset"):
        captured["agent_id"] = agent_id
        captured["dataset_name"] = dataset_name
        return [_scenario()]

    monkeypatch.setattr(cli_mod, "find_dataset_scenarios", _fake_find)

    exit_code = cli_mod.main(["dataset", "prototype-specify", "dataset_small"])
    assert exit_code == 0
    assert captured == {"agent_id": "prototype-specify", "dataset_name": "dataset_small"}

    run_dir = next((tmp_path / "logs").iterdir())
    assert "dataset_small-prototype-specify" in run_dir.name


def test_dataset_unknown_agent_id_fails_before_dispatch(monkeypatch):
    def _fake_find(agent_id, dataset_name="dataset"):
        raise ValueError(f"no scenarios/_template.yaml declares agent_id '{agent_id}'")

    monkeypatch.setattr(cli_mod, "find_dataset_scenarios", _fake_find)

    async def _boom(*a, **k):
        raise AssertionError("driver should not be called")

    monkeypatch.setattr(cli_mod, "run_graded_scenario_once", _boom)

    exit_code = cli_mod.main(["dataset", "no-such-agent"])
    assert exit_code == 1


def test_dataset_report_aggregates_across_the_batch_array(
    fake_dataset_scenarios, fake_driver, fake_judge, tmp_path, monkeypatch, capsys
):
    monkeypatch.setattr(report_mod, "DEFAULT_LOGS_ROOT", tmp_path / "logs")
    cli_mod.main(["dataset", "prototype-specify", "--judge"])

    exit_code = cli_mod.main(["report"])
    out = capsys.readouterr().out
    assert exit_code == 0
    assert "total graded runs: 2" in out


def test_report_worst_prints_lowest_scored(capsys, tmp_path, monkeypatch):
    monkeypatch.setattr(report_mod, "DEFAULT_LOGS_ROOT", tmp_path)
    entries = [
        ("a", 90, "great", []),
        ("b", 20, "bad", ["missing invoice data"]),
    ]
    for run_id, score, rationale, weaknesses in entries:
        run_dir = tmp_path / run_id
        report_mod.write_run(run_dir, _valid_run(run_id))
        report_mod.write_grade(
            run_dir, _valid_grade(run_id, score=score, rationale=rationale, weaknesses=weaknesses)
        )

    exit_code = cli_mod.main(["report", "--worst", "1"])
    out = capsys.readouterr().out
    assert exit_code == 0
    assert "--- b " in out
    assert "--- a " not in out
    assert "bad" in out
    assert "missing invoice data" in out


def test_report_by_system_prompt_hash_with_target(capsys, tmp_path, monkeypatch):
    monkeypatch.setattr(report_mod, "DEFAULT_LOGS_ROOT", tmp_path)
    for run_id, hash_, score in [("a", "sha256:v1", 50), ("b", "sha256:v2", 95)]:
        run_dir = tmp_path / run_id
        report_mod.write_run(run_dir, {**_valid_run(run_id), "system_prompt_hash": hash_})
        report_mod.write_grade(run_dir, _valid_grade(run_id, score=score))

    exit_code = cli_mod.main(["report", "--by", "system_prompt_hash", "--target", "90"])
    out = capsys.readouterr().out
    assert exit_code == 0
    assert "TARGET NOT MET" in out
    assert "TARGET MET" in out


def test_report_never_touches_driver_or_judge(monkeypatch, tmp_path):
    """report command must be a pure read — no model calls, no re-run
    (spec NFR 'Loop stays human-in-the-loop')."""
    def _boom(*a, **k):
        raise AssertionError("report command must not call this")

    monkeypatch.setattr(cli_mod, "run_graded_scenario_once", _boom)
    monkeypatch.setattr(cli_mod, "grade_run", _boom)
    monkeypatch.setattr(report_mod, "DEFAULT_LOGS_ROOT", tmp_path)

    exit_code = cli_mod.main(["report"])
    assert exit_code == 0


def _valid_run(run_id: str) -> dict:
    return {
        "timestamp": "2026-07-28T15:08:02Z",
        "run_id": run_id,
        "scenario_id": "s1",
        "agent_id": "prototype-specify",
        "provider": None,
        "model": None,
        "resolved_model_id": "claude-haiku-4-5-20251001",
        "system_prompt_path": "x",
        "system_prompt_hash": "sha256:abc",
        "prompt": "brief",
        "response": "<spec>...</spec>",
        "precheck_passed": True,
        "precheck_reason": "ok",
        "tokens_in": 10,
        "tokens_out": 20,
    }


def _valid_grade(run_id: str, *, score=80, rationale="good", weaknesses=None) -> dict:
    return {
        "run_id": run_id,
        "judge_provider": None,
        "judge_model": None,
        "judge_resolved_model_id": "claude-haiku-4-5-20251001",
        "judge_threshold": 70,
        "score": score,
        "passed": score >= 70,
        "rationale": rationale,
        "strengths": [],
        "weaknesses": weaknesses or [],
        "errored": False,
        "error_reason": None,
    }
