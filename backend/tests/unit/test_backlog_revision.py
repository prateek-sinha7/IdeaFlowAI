"""Spec 022 revisions 7-9: the backlog_revision manifest (analyst, plan, write, review, assemble)."""

from __future__ import annotations

import contextlib
import json
import re
from types import SimpleNamespace

import pytest

from agents.capabilities.backlog_assemble import (
    BUILD_ORDER_PATH,
    COVERAGE_PATH,
    DEFAULT_DELIVERABLE,
    GAPS_PATH,
    NEW_DOCUMENT_FILES,
    assemble_backlog,
)
from agents.capabilities.backlog_export import PDF_NAME, ZIP_NAME
from agents.execution_engine.engine import compile_for_run
from agents.registry import REVISION_BASE_MAP, get_pipeline_agents
from agents.workflows.plan import DeliverableSpec
from app.agents.sandbox import agent_output_relpath
from app.api import run_commands as rc
from app.core.entitlements import can_run_pipeline
from tests.agents.test_backlog_assemble import (
    FakeSandbox,
    _requirement,
    _story,
    _two_level_sandbox,
    _write_json,
)

STEP_IDS = [
    "custom-agent:blr-analyst",
    "custom-agent:blr-plan",
    "custom-agent:blr-write",
    "custom-agent:blr-review",
    "custom-agent:blr-assemble",
]
# Every file the assembler and the export write: code rebuilds them after the writers, so a
# revision never edits one (user decision 16:02).
CODE_BUILT = (
    DEFAULT_DELIVERABLE,
    "backlog.csv",
    "backlog.json",
    BUILD_ORDER_PATH,
    *NEW_DOCUMENT_FILES,
    GAPS_PATH,
    PDF_NAME,
    ZIP_NAME,
    COVERAGE_PATH,
)


@pytest.fixture(scope="module")
def compiled():
    return compile_for_run("backlog_revision")


def _step(compiled, agent_id: str):
    return next(s for s in compiled.steps if s.agent_id == agent_id)


def _prompt(compiled, agent_id: str) -> str:
    return _step(compiled, agent_id).prompt


# ── 1. manifest shape ────────────────────────────────────────────────────────────────


def test_manifest_steps_and_mechanical_steps(compiled):
    assert [s.agent_id for s in compiled.steps] == STEP_IDS
    assert [s.mechanical for s in compiled.steps] == [
        None,
        None,
        None,
        None,
        "assemble_backlog",
    ]


def test_gates_by_step(compiled):
    assert {s.agent_id: list(s.gates) for s in compiled.steps} == {
        "custom-agent:blr-analyst": ["human"],
        "custom-agent:blr-plan": [],
        "custom-agent:blr-write": [],
        "custom-agent:blr-review": [],
        "custom-agent:blr-assemble": [],
    }


def test_only_the_analyst_is_a_human_gate_agent(compiled):
    # _handle_revision passes these as gate_agent_ids under E2.
    assert [s.agent_id for s in compiled.steps if "human" in s.gates] == [
        "custom-agent:blr-analyst"
    ]


def test_no_step_declares_a_validator(compiled):
    assert [list(s.validators) for s in compiled.steps] == [[]] * len(STEP_IDS)


def test_write_step_reads_exactly_the_revision_task_list(compiled):
    write = _step(compiled, "custom-agent:blr-write")
    assert write.strategy == "wave_scheduler"
    ts = write.task_source
    assert (ts.kind, ts.path, ts.parser, ts.source_step, ts.target) == (
        "custom_path",
        "revisions/{revision_n}/tasks.json",
        "json_tasks",
        "custom-agent:blr-plan",
        None,
    )


def test_the_plan_produces_the_task_list_the_writers_consume(compiled):
    plan, write = (
        _step(compiled, "custom-agent:blr-plan"),
        _step(compiled, "custom-agent:blr-write"),
    )
    path = write.task_source.path
    assert path == "revisions/{revision_n}/tasks.json"
    assert list(plan.produces) == [path]
    assert list(write.consumes) == [path]
    # The run-entry DAG check (engine: _specs_from_plan + WorkflowResolver.validate)
    # resolves the edge plan -> writers on that name.
    from agents.execution_engine.engine import ExecutionEngine
    from agents.execution_engine.resolver import WorkflowResolver

    result = WorkflowResolver().validate(
        ExecutionEngine._specs_from_plan(None, compiled.steps)
    )
    assert result.satisfiable, result.errors
    assert ("custom-agent:blr-plan", "custom-agent:blr-write", path) in {
        (e.from_agent_id, e.to_agent_id, e.artifact_type) for e in result.edges
    }


def test_the_last_step_is_the_existing_assembly(compiled):
    last = compiled.steps[-1]
    assert (last.mechanical, last.is_leaf) == ("assemble_backlog", True)
    # Not a backlog code job (backlog_prep.BACKLOG_CODE_JOBS), so it assembles and exports.
    from agents.capabilities.backlog_prep import BACKLOG_CODE_JOBS

    assert last.agent_id.rsplit(":", 1)[-1] not in BACKLOG_CODE_JOBS


def test_deliverable_revises_the_workspace(compiled):
    d = compiled.deliverable
    assert (
        d.strategy,
        d.name,
        d.text_name,
        d.revises_existing,
        d.revision_context,
    ) == ("single_file", "Backlog.pdf", "backlog.md", True, "workspace")


# ── 2. transcript contract ───────────────────────────────────────────────────────────


def test_prompts_read_earlier_step_transcripts_at_their_real_paths(compiled):
    relpaths = [
        agent_output_relpath(index=i, agent_id=s.agent_id)
        for i, s in enumerate(compiled.steps)
    ]
    assert relpaths[0] == ".agents/01-custom-agent_blr-analyst.md"
    assert relpaths[0] in _prompt(compiled, "custom-agent:blr-plan")
    assert relpaths[0] in _prompt(compiled, "custom-agent:blr-review")
    for i, step in enumerate(compiled.steps):
        for path in re.findall(r"\.agents/\d\d-[\w.-]+\.md", step.prompt or ""):
            assert (
                path in relpaths[:i]
            ), f"{step.agent_id} reads {path}, not an earlier step's transcript"


# ── 3. prompt contracts ──────────────────────────────────────────────────────────────


def test_analyst_prompt_states_its_reply_contract(compiled):
    prompt = _prompt(compiled, "custom-agent:blr-analyst")
    for needle in (
        "A message that calls a tool holds the tool call and nothing else",
        "Your last message calls no tool. It is the spec, exactly as you wrote it to its file, starting with its `Spec:` line",
        "`Spec: revisions/<n>/revision-spec.md`",
        "## Request",
        "## Findings",
        "## Changes",
        "## Out of scope",
        "## Open questions",
        "### C<N>: ",
    ):
        assert needle in prompt, needle


def test_analyst_prompt_numbers_the_revision_and_handles_a_redo(compiled):
    prompt = _prompt(compiled, "custom-agent:blr-analyst")
    for needle in (
        "glob `revisions/*/revision-spec.md`",
        "n is the highest of those numbers plus 1",
        "=== ADDITIONAL INSTRUCTIONS (REVISE) ===",
        "revision-spec-<k>.md",
        "You change no existing file.",
    ):
        assert needle in prompt, needle


@pytest.mark.parametrize(
    "agent_id",
    [
        "custom-agent:blr-analyst",
        "custom-agent:blr-plan",
        "custom-agent:blr-write",
        "custom-agent:blr-review",
    ],
)
def test_no_prompt_globs_the_revisions_folder(compiled, agent_id):
    # glob lists files only: glob('revisions/*') returned [] in revision 0924fe8a, and the
    # Analyst numbered the revision 1 while revisions/1-3 existed. The folder pattern may
    # appear only in the warning against it.
    rest = _prompt(compiled, agent_id).replace(
        "never glob a folder pattern such as `revisions/*`", ""
    )
    assert "`revisions/*`" not in rest and "glob revisions/*" not in rest.replace(
        "glob revisions/*/revision-spec.md", ""
    )


@pytest.mark.parametrize(
    "agent_id",
    ["custom-agent:blr-analyst", "custom-agent:blr-plan", "custom-agent:blr-review"],
)
def test_prompt_names_every_file_code_builds(compiled, agent_id):
    prompt = _prompt(compiled, agent_id)
    for path in CODE_BUILT:
        assert f"`{path}`" in prompt, path


def test_analyst_prompt_never_edits_a_built_document_and_may_create_a_file(compiled):
    # User decision 16:02: the assembler rebuilds every code-built document, so a change
    # goes through its source and a layout change is out of scope; a new file is fine.
    prompt = _prompt(compiled, "custom-agent:blr-analyst")
    for needle in (
        "and a new file when the request needs one. Never a document code builds.",
        "so an edit to one of them is lost",
        "A change to what one of them says goes in its source.",
        "how a document code builds is laid out (its sections, how it draws a diagram)",
        "A request only code can satisfy (a code-built document's layout, the PDF's look) goes under `## Out of scope`.",
        "`## Out of scope` — what only code can change (a code-built document's layout, the PDF's look)",
        "`(new file)` for a file the change creates",
    ):
        assert needle in prompt, needle
    for gone in (
        "are edited directly too: a diagram, a section, the wording",
        "Any file in this folder, edited in place",
        "anything that needs a new file",
        "what would need a new file",
    ):
        assert gone not in prompt, gone


def test_plan_prompt_states_the_task_list_contract(compiled):
    prompt = _prompt(compiled, "custom-agent:blr-plan")
    for needle in (
        "One task per file",
        "`Targets: <path>`",
        "`revisions/<n>/tasks.json`",
        "NEVER write `build/story-tasks.json`",
        "No task targets a document code builds",
        "so an edit to one is lost",
        '"targets": the one file the task changes, or creates.',
    ):
        assert needle in prompt, needle
    assert "the documents code builds included" not in prompt


def test_writer_prompt_creates_only_a_file_its_task_says_is_new(compiled):
    prompt = _prompt(compiled, "custom-agent:blr-write")
    assert "you create a file only when your task says it is new" in prompt
    assert "you never create a file" not in prompt


def test_review_prompt_limits_changes_and_names_the_statuses(compiled):
    prompt = _prompt(compiled, "custom-agent:blr-review")
    for needle in (
        "Only the files the spec's changes name.",
        "`revisions/<n>/revision-review.md`",
        "`done`",
        "`fixed now`",
        "`not possible`",
        "Never a document code builds",
        "A new file only when a spec change creates it",
    ):
        assert needle in prompt, needle
    assert "They may be documents code builds" not in prompt


# ── 4. a backlog parent mints backlog_revision ───────────────────────────────────────


class _Query:
    def first(self):
        return None

    def filter(self, *_a, **_k):
        return self


class _Db:
    def __init__(self):
        self.added = []

    def query(self, *_a, **_k):
        return _Query()

    def add(self, row):
        self.added.append(row)

    def commit(self):
        pass


def test_backlog_parent_mints_backlog_revision_with_five_agents(monkeypatch):
    monkeypatch.setattr(rc, "_revision_chain_root_id", lambda *_a: "root")
    monkeypatch.setattr(rc, "_has_active_chain_revision", lambda *_a: False)
    monkeypatch.setattr(rc, "family_lock", lambda *_a, **_k: contextlib.nullcontext())
    assert get_pipeline_agents("backlog_revision") == []
    db = _Db()
    run_id, rev_type = rc._mint_revision_row(
        db,
        user=SimpleNamespace(id="u1"),
        caller_tier="pro",
        parent_run_id="p1",
        target_artifact_type="backlog_output",
        instruction="close the gaps",
    )
    assert rev_type == "backlog_revision"
    [row] = db.added
    assert row.type == "backlog_revision" and row.agent_count == 5 and row.id == run_id


@pytest.mark.parametrize(
    "tier,allowed",
    [("hexaware", True), ("pro", True), ("enterprise", True), ("basic", False)],
)
def test_backlog_revision_entitlement_by_tier(tier, allowed):
    assert can_run_pipeline(tier, "backlog_revision")[0] is allowed


def test_backlog_revision_base_is_backlog():
    assert REVISION_BASE_MAP["backlog_revision"] == "backlog"


# ── 5. revision re-assembly picks up edited and review-file stories ──────────────────


def test_second_assembly_shows_changed_title_and_new_review_story():
    sandbox = _two_level_sandbox()
    _write_json(sandbox, "build/review.json", {"rounds": 1, "fixed": [], "open": []})
    ctx = SimpleNamespace(
        runner=SimpleNamespace(sandbox=sandbox),
        deliverable=DeliverableSpec(
            strategy="single_file",
            name="Backlog.pdf",
            text_name="backlog.md",
            revises_existing=True,
        ),
    )
    assemble_backlog(ctx)
    assert "Create a quote" in sandbox.files["backlog.md"]
    assert "Create a quote" in sandbox.files["backlog.csv"]

    data = json.loads(sandbox.files["stories/EPIC-01.json"])
    data["stories"][0]["title"] = "Draft a quote"
    _write_json(sandbox, "stories/EPIC-01.json", data)
    new = _story(
        id="US-R-01",
        title="Export a quote",
        requirements=[_requirement(id="REQ-R-001")],
        gherkin=[
            "Feature: Export a quote",
            "  @US-R-01 @REQ-R-001 @P0",
            "  Scenario: Agent exports",
            "    Given a quote exists",
            "    When the agent exports it",
            "    Then a file is produced",
        ],
    )
    _write_json(
        sandbox, "stories/review-EPIC-01.json", {"epic": "EPIC-01", "stories": [new]}
    )

    assemble_backlog(ctx)
    for path in ("backlog.md", "backlog.csv"):
        text = sandbox.files[path]
        assert (
            "Draft a quote" in text and "US-R-01" in text and "Export a quote" in text
        )
        assert "Create a quote" not in text
    assert "Backlog.pdf" not in sandbox.files
    assert json.loads(sandbox.files["build/coverage.json"])["mode"] == "final"


@pytest.mark.parametrize(
    "agent_id", ["custom-agent:blr-plan", "custom-agent:blr-review"]
)
def test_later_steps_find_the_spec_line_wherever_it_is(compiled, agent_id):
    # The step transcript holds every word the Analyst streamed (engine: all text chunks
    # joined), so notes can sit above the spec; n comes from the `Spec:` line itself.
    prompt = _prompt(compiled, agent_id)
    assert (
        "Its `Spec: revisions/<n>/…` line gives n; any text above that line is not the spec."
        in prompt
    )
    assert "Its first line" not in prompt


def test_analyst_changes_every_copy_of_a_field_attribute_or_endpoint(compiled):
    # Revision 8d4d2d70: the spec made five SCR-site-setup fields required in
    # build/solution/screens.json only, while story US-01a-01 kept its own ui copies
    # of them as not required, so the PDF contradicted itself.
    prompt = _prompt(compiled, "custom-agent:blr-analyst")
    for needle in (
        "grep `stories/` for its name and its id too",
        "each story's `ui` (screen and field), `data` (entity and attributes) and `api` (endpoint ids) entries",
        "A change to a screen field, an entity attribute or an endpoint changes every copy of it",
        "A copy left as it was makes the backlog contradict itself.",
    ):
        assert needle in prompt, needle


def test_only_the_analyst_replies_with_its_last_message(compiled):
    assert {s.agent_id: s.reply for s in compiled.steps} == {
        "custom-agent:blr-analyst": "last_message",
        "custom-agent:blr-plan": "all",
        "custom-agent:blr-write": "all",
        "custom-agent:blr-review": "all",
        "custom-agent:blr-assemble": "all",
    }


def test_the_planner_gives_every_approved_change_a_task(compiled):
    # Revision 8d4d2d70: the Planner read "never write ... under build/ yourself" as a ban
    # on targets and left C3 (build/solution/screens.json) without a task.
    prompt = _prompt(compiled, "custom-agent:blr-plan")
    for needle in (
        "Every `### C<N>` block in the spec's `## Changes` gets a task",
        "Never drop one, never move it to another file, never second-guess it.",
        "`build/solution/*.json` — are files a change edits like any other: valid targets.",
        "that rule is about your own writes, not about the targets of the tasks you list",
        "No task targets `build/tasks.json`.",
        "each C<N> is in exactly one task's body",
    ):
        assert needle in prompt, needle
    assert "any change you left out" not in prompt
