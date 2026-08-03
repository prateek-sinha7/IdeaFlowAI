"""T5/T6 — the `apply-advice` and `revert` commands.

These own all the I/O: read the advice, read AGENT.md, call the pure engine,
write in a fixed order. The properties that matter are about what reaches disk —
above all that a failed edit writes *nothing*, and that the frontmatter comes
back byte-for-byte because it is the engine's contract.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from evals.grading import config, grade_runner
from evals.grading.model.prompt_advisor import _token

AGENT_ID = "demo-agent"
TOKEN = _token(AGENT_ID)
RUN_ID = "260730-173912-demo"

FRONTMATTER = """---
id: demo-agent
name: Demo Agent
order: 3
produces:
- demo
tools: []
---
"""

BODY = """
You are the **Demo Agent**.

## Tools

- `write_file("prototype.html", content)` — overwrite the entire file.

## Steps

1. Read the spec.
2. Build it.
"""

AGENT_MD = FRONTMATTER + BODY


def _edit(action, section="", current_text="", proposed_text="", reason="because"):
    return {
        "action": action,
        "section": section,
        "current_text": current_text,
        "proposed_text": proposed_text,
        "reason": reason,
    }


GOOD_EDITS = [
    _edit(
        "modify",
        section="Tools",
        current_text='`write_file("prototype.html", content)` — overwrite the entire file.',
        proposed_text='`write_file("prototype.html", content)` — create-only.',
        reason="write_file cannot overwrite",
    ),
    _edit("add", section="Steps", proposed_text="3. Verify it.", reason="rows skipped checks"),
]


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    """A fake prompts dir and run folder, wired into the runner."""
    prompts = tmp_path / "prompts"
    agent_dir = prompts / AGENT_ID
    agent_dir.mkdir(parents=True)
    (agent_dir / "AGENT.md").write_text(AGENT_MD, encoding="utf-8")

    workflow_dir = tmp_path / "wf"
    run_dir = workflow_dir / ".runs" / RUN_ID
    (run_dir / "reports").mkdir(parents=True)

    monkeypatch.setattr(grade_runner, "AGENTS_PROMPTS_DIR", prompts)
    monkeypatch.setattr(
        config, "load_workflow", lambda *a, **k: {"workflow_dir": str(workflow_dir)}
    )
    return SimpleNamespace(agent_dir=agent_dir, run_dir=run_dir, prompts=prompts)


def _write_advice(run_dir, edits):
    payload = {"summary": "s", "deviations": [], "edits": edits, "keep": []}
    path = run_dir / "reports" / f"prompt_advice_{TOKEN}.json"
    path.write_text(json.dumps(payload), encoding="utf-8")


def _apply(agent=AGENT_ID, run=RUN_ID):
    return grade_runner.run_apply_advice(
        SimpleNamespace(dataset_run_id=run, agent=agent, workflow="prototype")
    )


def _revert(agent=AGENT_ID):
    return grade_runner.run_revert(SimpleNamespace(agent=agent, workflow="prototype"))


def _read(agent_dir, name="AGENT.md"):
    return (agent_dir / name).read_text(encoding="utf-8")


class TestApplyAdvice:
    def test_archives_the_old_body_and_applies_the_edits(self, workspace, capsys):
        _write_advice(workspace.run_dir, GOOD_EDITS)

        assert _apply() == grade_runner.EXIT_OK

        live = _read(workspace.agent_dir)
        assert "create-only." in live
        assert "overwrite the entire file." not in live
        assert "3. Verify it." in live
        assert _read(workspace.agent_dir, "AGENT.v1.md") == BODY

    def test_archive_holds_the_body_only_never_the_frontmatter(self, workspace):
        """An archive with no frontmatter cannot drift from the contract."""
        _write_advice(workspace.run_dir, GOOD_EDITS)
        _apply()

        assert "id: demo-agent" not in _read(workspace.agent_dir, "AGENT.v1.md")

    def test_frontmatter_is_preserved_byte_for_byte(self, workspace):
        _write_advice(workspace.run_dir, GOOD_EDITS)
        _apply()

        assert _read(workspace.agent_dir).startswith(FRONTMATTER)

    def test_prints_the_diff_and_the_revert_command(self, workspace, capsys):
        _write_advice(workspace.run_dir, GOOD_EDITS)
        _apply()

        out = capsys.readouterr().out
        assert "AGENT.v1.md" in out
        assert "revert" in out
        assert "frontmatter unchanged" in out
        assert "create-only" in out

    def test_a_second_apply_makes_v2_and_leaves_v1_alone(self, workspace):
        _write_advice(workspace.run_dir, GOOD_EDITS)
        _apply()
        first_archive = _read(workspace.agent_dir, "AGENT.v1.md")

        _write_advice(workspace.run_dir, [_edit("add", section="Steps", proposed_text="4. Ship.")])
        assert _apply() == grade_runner.EXIT_OK

        assert _read(workspace.agent_dir, "AGENT.v1.md") == first_archive
        assert "3. Verify it." in _read(workspace.agent_dir, "AGENT.v2.md")
        assert "4. Ship." in _read(workspace.agent_dir)


class TestNothingIsWrittenOnFailure:
    """R-06 / V5 — the property that makes this command safe to run casually."""

    def test_an_unapplicable_edit_writes_nothing_at_all(self, workspace):
        _write_advice(
            workspace.run_dir,
            [
                GOOD_EDITS[0],
                _edit("modify", current_text="text that is not in the prompt", proposed_text="x"),
            ],
        )

        assert _apply() == grade_runner.EXIT_EDIT_FAILED

        assert _read(workspace.agent_dir) == AGENT_MD
        assert not (workspace.agent_dir / "AGENT.v1.md").exists()

    def test_the_failure_names_the_edit_and_the_count(self, workspace, capsys):
        _write_advice(
            workspace.run_dir, [_edit("modify", current_text="absent", proposed_text="x")]
        )
        _apply()

        assert "0 times" in capsys.readouterr().err

    def test_an_unknown_action_fails_rather_than_being_dropped(self, workspace):
        _write_advice(workspace.run_dir, [_edit("reorder", current_text="x")])

        assert _apply() == grade_runner.EXIT_EDIT_FAILED
        assert _read(workspace.agent_dir) == AGENT_MD


class TestFrontmatterEdits:
    def test_a_frontmatter_edit_is_refused_and_the_rest_apply(self, workspace, capsys):
        _write_advice(
            workspace.run_dir,
            [_edit("modify", section="order", current_text="order: 3", proposed_text="order: 9")]
            + GOOD_EDITS,
        )

        assert _apply() == grade_runner.EXIT_OK

        live = _read(workspace.agent_dir)
        assert "order: 3" in live  # untouched
        assert "create-only." in live  # the others applied
        assert "refused" in capsys.readouterr().out.lower()

    def test_every_edit_refused_exits_ten(self, workspace):
        _write_advice(
            workspace.run_dir,
            [_edit("modify", section="order", current_text="order: 3", proposed_text="order: 9")],
        )

        assert _apply() == grade_runner.EXIT_ALL_REFUSED
        assert _read(workspace.agent_dir) == AGENT_MD


class TestMissingInputs:
    def test_markdown_only_run_folder_names_the_advise_command(self, workspace, capsys):
        """V7 — a run graded before the JSON sidecar existed."""
        (workspace.run_dir / "reports" / f"prompt_advice_{TOKEN}.md").write_text("x")

        assert _apply() == grade_runner.EXIT_USAGE
        assert "advise" in capsys.readouterr().err

    def test_unknown_agent_exits_usage(self, workspace, capsys):
        _write_advice(workspace.run_dir, GOOD_EDITS)

        assert _apply(agent="no-such-agent") == grade_runner.EXIT_USAGE
        assert "no-such-agent" in capsys.readouterr().err

    def test_unknown_run_exits_usage(self, workspace, capsys):
        assert _apply(run="260101-000000-nope") == grade_runner.EXIT_USAGE


class TestRevert:
    def test_restores_the_archive_and_removes_it(self, workspace):
        _write_advice(workspace.run_dir, GOOD_EDITS)
        _apply()

        assert _revert() == grade_runner.EXIT_OK

        assert _read(workspace.agent_dir) == AGENT_MD
        assert not (workspace.agent_dir / "AGENT.v1.md").exists()

    def test_repeated_reverts_walk_back_through_history(self, workspace):
        _write_advice(workspace.run_dir, GOOD_EDITS)
        _apply()
        _write_advice(workspace.run_dir, [_edit("add", section="Steps", proposed_text="4. Ship.")])
        _apply()

        _revert()
        assert "4. Ship." not in _read(workspace.agent_dir)
        assert "3. Verify it." in _read(workspace.agent_dir)

        _revert()
        assert _read(workspace.agent_dir) == AGENT_MD
        assert not list(workspace.agent_dir.glob("AGENT.v*.md"))

    def test_the_current_body_is_not_re_archived(self, workspace):
        """Revert is an undo, not another edit."""
        _write_advice(workspace.run_dir, GOOD_EDITS)
        _apply()
        _revert()

        assert not list(workspace.agent_dir.glob("AGENT.v*.md"))

    def test_frontmatter_survives_a_revert(self, workspace):
        _write_advice(workspace.run_dir, GOOD_EDITS)
        _apply()
        _revert()

        assert _read(workspace.agent_dir).startswith(FRONTMATTER)

    def test_no_archive_exits_usage(self, workspace, capsys):
        assert _revert() == grade_runner.EXIT_USAGE
        assert "revert" in capsys.readouterr().err.lower()

    def test_an_empty_archive_is_refused(self, workspace, capsys):
        """T10 — the seven zero-byte AGENT.v2.md files would restore an empty prompt.

        `loader.py` rejects an empty body at load time, so writing one would break
        the agent. A valid archive can never be empty: `apply_edits` guarantees a
        non-empty body before one is written.
        """
        (workspace.agent_dir / "AGENT.v1.md").write_text("", encoding="utf-8")

        assert _revert() == grade_runner.EXIT_USAGE
        assert _read(workspace.agent_dir) == AGENT_MD
        assert "empty" in capsys.readouterr().err.lower()
