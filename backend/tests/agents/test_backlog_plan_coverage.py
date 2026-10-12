"""The Backlog Planner's plan is checked against every coverage item (run 3976f8ce).

Its planner paged endpoints.json only to ~line 3000, so API-34..API-76 were in no
epic, its own check passed, and the run failed at the last step at 83% coverage.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace as NS

import pytest

from agents.capabilities.backlog_prep import COVERAGE_ITEMS_PATH, write_coverage_items
from agents.capabilities.gates.base import GATE_BLOCK, GATE_PASS
from agents.capabilities.gates.validation import ValidationGate
from agents.capabilities.validators.backlog_plan_coverage import BacklogPlanCoverageValidator
from agents.execution_engine.engine import ExecutionEngine, compile_for_run


class Sandbox:
    def __init__(self, files):
        self.files = {k: v if isinstance(v, str) else json.dumps(v) for k, v in files.items()}

    def read(self, path):
        return self.files.get(path)

    def write(self, path, text):
        self.files[path] = text


def _run(*, covers, unassigned=(), task_body="Cover: SCR-01, SCR-02, API-01, API-02."):
    return Sandbox({
        "build/solution/screens.json": {"items": [
            {"id": "SCR-01", "name": "Sign in", "provenance": "evidenced"},
            {"id": "SCR-02", "name": "Users", "provenance": "evidenced"}]},
        "build/solution/endpoints.json": {"items": [
            {"id": f"API-{i:02d}", "method": "GET", "path": f"/x/{i}", "provenance": "evidenced"}
            for i in range(1, 5)]},
        "build/solution/glossary.json": {"items": [{"id": "GLO-01", "term": "Tenant"}]},
        "build/backlog-plan.json": {"epics": [{"id": "EPIC-01", "covers": list(covers)}],
                                    "unassigned": list(unassigned)},
        "build/story-tasks.json": {"tasks": [{"id": "EPIC-01a", "body": task_body}]},
    })


def _validate(sandbox):
    return asyncio.run(BacklogPlanCoverageValidator().validate(NS(runner=NS(sandbox=sandbox))))


def test_items_left_out_of_the_plan_are_named_as_critical():
    issues = _validate(_run(covers=["SCR-01", "SCR-02", "API-01", "API-02"]))
    assert len(issues) == 1 and issues[0].severity == "P0"
    assert "2 coverage item(s) are in no epic's covers" in issues[0].message
    assert "API-03, API-04" in issues[0].message
    assert "build/story-tasks.json" in issues[0].message and "edit_file" in issues[0].message


def test_an_item_in_an_epic_but_in_no_slice_task_is_named():
    issues = _validate(_run(covers=["SCR-01", "SCR-02", "API-01", "API-02", "API-03"],
                            unassigned=[{"id": "API-04", "reason": "out of scope"}]))
    assert len(issues) == 1 and "API-03" in issues[0].message and "no slice task" in issues[0].message


def test_a_complete_plan_passes():
    sandbox = _run(covers=["SCR-01", "SCR-02", "API-01", "API-02", "API-03"], unassigned=["API-04"],
                   task_body="Cover: SCR-01, SCR-02, API-01, API-02, API-03.")
    assert _validate(sandbox) == []


def test_the_gate_blocks_on_gaps_and_passes_a_complete_plan():
    # The block is what the engine's validation-retry loop re-runs the Planner on.
    step = NS(agent_id="custom-agent:us-backlog", validators=["backlog_plan_coverage"])
    gap = asyncio.run(ValidationGate().evaluate(step, NS(runner=NS(sandbox=_run(covers=["SCR-01"])))))
    assert gap.outcome == GATE_BLOCK
    assert "API-02" in gap.events[0]["data"]["issues"][0]["message"]
    full = _run(covers=["SCR-01", "SCR-02", "API-01", "API-02", "API-03", "API-04"],
                task_body="Cover: SCR-01, SCR-02, API-01, API-02, API-03, API-04.")
    assert asyncio.run(ValidationGate().evaluate(step, NS(runner=NS(sandbox=full)))).outcome == GATE_PASS


def test_the_backlog_planner_is_gated_with_two_fix_attempts():
    step = next(s for s in compile_for_run("backlog").steps if s.agent_id.endswith(":us-backlog"))
    assert "validation" in step.gates
    assert step.validators == ["backlog_plan_coverage"]
    assert step.fix.max_attempts == 2


def test_coverage_items_file_lists_every_item_one_per_line():
    sandbox = _run(covers=[])
    note = write_coverage_items(sandbox)
    text = sandbox.files[COVERAGE_ITEMS_PATH]
    items = json.loads(text)["items"]
    assert [i["id"] for i in items] == ["SCR-01", "SCR-02", "API-01", "API-02", "API-03", "API-04"]
    assert items[0] == {"id": "SCR-01", "type": "screens", "title": "Sign in", "provenance": "evidenced"}
    assert items[2]["title"] == "GET /x/1"
    assert "GLO-01" not in text  # the glossary is not a coverage item
    assert len(text.splitlines()) == len(items) + 2  # one item per line
    assert note == f"Wrote {COVERAGE_ITEMS_PATH}: 6 coverage item(s)."


def test_the_planner_prompt_reads_the_coverage_items_file():
    step = next(s for s in compile_for_run("backlog").steps if s.agent_id.endswith(":us-backlog"))
    assert "build/coverage-items.json" in step.consumes
    assert "2. read_file `build/coverage-items.json` to its end" in step.prompt
    assert "2. Every id in `build/coverage-items.json` is in some epic's covers" in step.prompt


class _Events:
    def __init__(self, rows):
        self.rows = rows

    async def read_events(self, run_id, since):
        return self.rows

    async def read_wave_runs(self, run_id):
        return []

    async def tree(self, run_id):
        return [NS(producer_agent="clarify", task_id=None), NS(producer_agent="plan", task_id=None)]


@pytest.mark.asyncio
async def test_a_step_that_failed_validation_is_where_a_resume_starts():
    steps = [NS(agent_id="clarify", strategy="single_shot", mechanical=None),
             NS(agent_id="plan", strategy="single_shot", mechanical=None)]
    ordered = [NS(id=s.agent_id) for s in steps]
    rows = [NS(type="agent_complete", payload_json={"agent_id": "clarify"}),
            NS(type="agent_complete", payload_json={"agent_id": "plan"}),
            NS(type="agent_error", payload_json={"agent_id": "plan", "recoverable": False})]
    ectx = NS(scoped_store=_Events(rows), run_id="r")
    assert await ExecutionEngine()._first_incomplete_step(ectx, ordered, NS(steps=steps)) == 1
    # A recoverable error followed by completion stays complete (unchanged).
    rows[2] = NS(type="agent_error", payload_json={"agent_id": "plan", "recoverable": True})
    assert await ExecutionEngine()._first_incomplete_step(ectx, ordered, NS(steps=steps)) == 2
