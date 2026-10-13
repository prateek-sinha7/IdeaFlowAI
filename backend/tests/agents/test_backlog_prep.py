"""The backlog's two code steps (agents/capabilities/backlog_prep.py): the Answer
Integrator folding the user's answers in, and the Story Writers' task list carrying
every model item a slice covers — plus the adapter routing both by instance id."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from agents.capabilities.backlog_assemble import MechanicalAssembleBacklogStrategy
from agents.capabilities.backlog_prep import (
    WRITER_TASKS_PATH,
    build_writer_tasks,
    integrate_answers,
)


class FakeSandbox:
    def __init__(self, files: dict[str, str]) -> None:
        self.files = dict(files)

    def read(self, path: str) -> str | None:
        return self.files.get(path)

    def write(self, path: str, text: str) -> None:
        self.files[path] = text


SYNTHESIS = """# Synthesis

## Rules
- Passwords are checked [p p.1]

## Open gaps
- gap-1: Password policy not specified [p p.1]
- gap-2: Export format unknown [p p.2]
- gap-3: Audit retention unknown [p p.3]
"""

VALIDATE = (
    '{"documents_expected": ["p"], "documents_present": ["p"], "missing_documents": [],\n"gaps": [\n'
    '{"id": "gap-1", "gap": "Password policy not specified", "raised_by": "p p.1", "filled_from": null, "answer": null},\n'
    '{"id": "gap-2", "gap": "Export format unknown", "raised_by": "p p.2", "filled_from": null, "answer": null},\n'
    '{"id": "gap-3", "gap": "Audit retention unknown", "raised_by": "p p.3", "filled_from": null, "answer": null}\n'
    "]}\n"
)

ANSWERS = json.dumps(
    {
        "rounds": 1,
        "answers": [
            {
                "id": "gap-1",
                "question": "q1",
                "answer": "Minimum 8 characters",
                "answered": True,
            },
            {
                "id": "gap-2",
                "question": "q2",
                "answer": "Not applicable — out of scope",
                "answered": True,
            },
            {"id": "gap-3", "question": "q3", "answer": None, "answered": False},
        ],
    }
)


def test_integrate_answers_closes_answered_gaps_and_keeps_the_rest():
    sb = FakeSandbox(
        {
            "synthesis.md": SYNTHESIS,
            "validate.json": VALIDATE,
            "clarify/answers.json": ANSWERS,
        }
    )
    report = integrate_answers(sb)

    assert "2 gap(s) closed" in report and "1 still open" in report
    synthesis = sb.files["synthesis.md"]
    assert (
        "- Password policy not specified — Minimum 8 characters [user gap-1]"
        in synthesis
    )
    assert "- Out of scope: Export format unknown [user gap-2]" in synthesis
    assert "- gap-1:" not in synthesis and "- gap-2:" not in synthesis
    assert "- gap-3: Audit retention unknown [p p.3]" in synthesis
    assert synthesis.index("## Decisions from the user") < synthesis.index(
        "## Open gaps"
    )

    text = sb.files["validate.json"]
    validate = json.loads(text)
    by_id = {g["id"]: g for g in validate["gaps"]}
    assert by_id["gap-1"] == {
        **by_id["gap-1"],
        "filled_from": "user",
        "answer": "Minimum 8 characters",
    }
    assert by_id["gap-3"]["filled_from"] is None
    assert validate["documents_present"] == ["p"]
    assert text == json.dumps(validate, indent=2, ensure_ascii=False) + "\n"  # indented

    # a second run changes nothing
    integrate_answers(sb)
    assert sb.files["synthesis.md"] == synthesis
    assert sb.files["validate.json"] == text


def test_integrate_answers_without_answers_changes_nothing():
    sb = FakeSandbox({"synthesis.md": SYNTHESIS, "validate.json": VALIDATE})
    assert integrate_answers(sb).startswith("No answers")
    assert (
        sb.files["synthesis.md"] == SYNTHESIS and sb.files["validate.json"] == VALIDATE
    )


def _model_files() -> dict[str, str]:
    items = lambda *xs: json.dumps({"items": list(xs)})  # noqa: E731
    return {
        "build/solution/screens.json": items(
            {
                "id": "SCR-login",
                "name": "Login",
                "fields": [{"name": "Username", "control": "text"}],
            }
        ),
        "build/solution/entities.json": items({"id": "ENT-01", "name": "User"}),
        "build/solution/rules.json": items(
            {
                "id": "BR-10",
                "statement": "Username is required",
                "applies_to": ["SCR-login"],
                "message": "Enter a username",
            },
            {
                "id": "BR-11",
                "statement": "Lock after 5 tries",
                "applies_to": ["ENT-01"],
                "message": None,
            },
        ),
        "build/solution/endpoints.json": items(
            {
                "id": "API-01",
                "name": "Sign in",
                "method": "POST",
                "path": "/v1/sessions",
                "screens": ["SCR-login"],
                "entity": None,
            },
            {
                "id": "API-02",
                "name": "List users",
                "method": "GET",
                "path": "/v1/users",
                "screens": [],
                "entity": "ENT-01",
            },
        ),
        "build/backlog-plan.json": json.dumps(
            {"personas": [{"id": "PER-01", "name": "Admin", "goal": "g"}], "epics": []}
        ),
        "build/story-tasks.json": json.dumps(
            {
                "tasks": [
                    {
                        "id": "EPIC-01a",
                        "title": "Auth (slice a)",
                        "targets": ["stories/EPIC-01a.json"],
                        "depends_on": [],
                        "body": "Epic EPIC-01 Auth (functional). Priority P0. Prefix 01a. Cover: SCR-login (Login), BR-10 (Username), NOPE-99 (missing).",
                    }
                ]
            }
        ),
    }


def test_build_writer_tasks_puts_the_items_in_the_task_body():
    sb = FakeSandbox(_model_files())
    assert "1 writer task" in build_writer_tasks(sb)

    task = json.loads(sb.files[WRITER_TASKS_PATH])["tasks"][0]
    assert task["id"] == "EPIC-01a" and task["targets"] == ["stories/EPIC-01a.json"]
    body = task["body"]
    assert body.startswith("Epic EPIC-01 Auth (functional).")
    assert '"id": "SCR-login"' in body and '"name": "Username"' in body  # full item
    assert '"id": "BR-10"' in body
    assert "API-01 POST /v1/sessions — Sign in" in body  # endpoint its screen uses
    assert "BR-11" not in body  # rule on an entity the slice does not cover
    assert '"id": "PER-01"' in body
    assert "API-02 GET /v1/users — List users" in body  # the full endpoint index
    # the source list is untouched
    assert "YOUR ITEMS" not in sb.files["build/story-tasks.json"]


def _run_adapter(instance: str, sb: FakeSandbox) -> list[dict]:
    spec = SimpleNamespace(id=f"custom-agent:{instance}", name=instance)
    ctx = SimpleNamespace(runner=SimpleNamespace(sandbox=sb), deliverable=None)
    strategy = MechanicalAssembleBacklogStrategy(
        spec=spec, index=0, total=1, results=[]
    )

    async def collect():
        return [e async for e in strategy.run(None, ctx)]

    return asyncio.run(collect())


def test_adapter_routes_by_instance_id():
    sb = FakeSandbox(
        {
            "synthesis.md": SYNTHESIS,
            "validate.json": VALIDATE,
            "clarify/answers.json": ANSWERS,
        }
    )
    events = _run_adapter("us-close", sb)
    assert events[-1]["type"] == "agent_complete"
    assert "[user gap-1]" in sb.files["synthesis.md"]
    assert "backlog.md" not in sb.files  # it did not assemble

    sb = FakeSandbox(_model_files())
    _run_adapter("us-writer-tasks", sb)
    assert WRITER_TASKS_PATH in sb.files and "backlog.md" not in sb.files


def test_tidy_json_indents_every_known_file_and_keeps_the_content():
    from agents.capabilities.backlog_prep import tidy_json

    one = lambda d: json.dumps(d)  # noqa: E731
    files = {
        "build/tasks.json": one(
            {"tasks": [{"id": "s01", "targets": ["file-synthesis/doc/status.json"]}]}
        ),
        "file-synthesis/doc/status.json": one({"file": "doc", "complete": True}),
        "file-synthesis/doc/gaps.json": one(
            [{"gap": "g", "raised_by": "doc p.1", "filled_from": None}]
        ),
        "build/solution/endpoints.json": one(
            {"items": [{"id": "API-01", "path": "/v1/a"}]}
        ),
        "build/backlog-plan.json": one({"epics": [{"id": "EPIC-01"}]}),
        "build/story-tasks.json": one({"tasks": [{"id": "EPIC-01a"}]}),
        "stories/EPIC-01a.json": one(
            {"epic": "EPIC-01", "stories": [{"id": "US-01a-01"}]}
        ),
        "stories/review-EPIC-01.json": one({"epic": "EPIC-01", "stories": []}),
        "validate.json": "{not json",
        "notes.json": one({"x": 1}),
    }
    sb = FakeSandbox(files)
    assert tidy_json(sb) == 8
    for path, text in files.items():
        if path in ("validate.json", "notes.json"):
            assert sb.files[path] == text  # broken, or not the workflow's: untouched
            continue
        assert json.loads(sb.files[path]) == json.loads(text)
        assert sb.files[path] == json.dumps(json.loads(text), indent=2) + "\n"
    assert tidy_json(sb) == 0  # idempotent


def test_every_code_step_leaves_indented_json():
    sb = FakeSandbox(_model_files())
    _run_adapter("us-json", sb)
    assert sb.files["build/solution/endpoints.json"].startswith('{\n  "items": [')
    _run_adapter("us-writer-tasks", sb)
    assert sb.files[WRITER_TASKS_PATH].startswith('{\n  "tasks": [')
