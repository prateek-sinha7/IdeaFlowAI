"""Unit tests for ``app/agents/workflow_builder/irreversible_gate.py``."""

from __future__ import annotations

from typing import Any

import pytest

from app.agents.workflow_builder.irreversible_gate import (
    RULE,
    check,
    irreversible_tools,
)


def _step(instance_id: str, **fields: Any) -> dict[str, Any]:
    return {"agent": "custom-agent", "instance_id": instance_id, **fields}


_POST = {
    "mcp": ["slack.post_message", "slack.list_channels"],
    "integrations": ["slack_post"],
}


@pytest.mark.parametrize(
    ("tools", "expected"),
    [
        ({"mcp": ["slack.post_message"]}, ["slack.post_message"]),
        ({"mcp": ["github.list_issues", "jira.get_issue"]}, []),
        (
            {"connectors": ["jira__create_issue", "jira__search_issues"]},
            ["jira__create_issue"],
        ),
        ({"integrations": ["github_read", "slack_post"]}, ["slack_post"]),
        ({"exec": True}, ["exec"]),
        ({"read_files": True, "write_files": True}, []),
    ],
)
def test_irreversible_tools_lists_only_writes_outside_the_run(
    tools: dict[str, Any], expected: list[str]
) -> None:
    assert irreversible_tools({"tools": tools}) == expected


def test_check_accepts_post_when_previous_step_has_human_gate() -> None:
    manifest = {
        "steps": [
            _step("draft", gates=["human"], redoable=True),
            _step("post", depends_on=["custom-agent:draft"], tools=_POST),
        ]
    }

    assert check(manifest) == []


def test_check_accepts_post_when_step_itself_has_before_human_gate() -> None:
    manifest = {
        "steps": [_step("draft"), _step("post", gates=["before-human"], tools=_POST)]
    }

    assert check(manifest) == []


def test_check_uses_previous_root_step_when_post_has_no_depends_on() -> None:
    manifest = {"steps": [_step("draft", gates=["human"]), _step("post", tools=_POST)]}

    assert check(manifest) == []


def test_check_rejects_post_when_gate_is_two_steps_earlier() -> None:
    manifest = {
        "steps": [
            _step("draft", gates=["human"]),
            _step("critic", depends_on=["custom-agent:draft"], gates=["conditional"]),
            _step("post", depends_on=["custom-agent:critic"], tools=_POST),
        ]
    }

    issues = check(manifest)

    assert [(i.rule, i.path) for i in issues] == [(RULE, "steps[2]")]
    assert (
        "step 'post' posts or writes outside the run (slack.post_message, slack_post)"
        in issues[0].message
    )
    assert '"gates": ["before-human"]' in issues[0].message


def test_check_rejects_nested_write_when_no_gate_precedes_it() -> None:
    manifest = {
        "steps": [
            _step(
                "parent",
                subagents={
                    "mode": "sequential",
                    "steps": [
                        _step("child-a"),
                        _step("child-b", tools={"connectors": ["jira__add_comment"]}),
                    ],
                },
            ),
        ]
    }

    issues = check(manifest)

    assert [i.path for i in issues] == ["steps[0].subagents.steps[1]"]


def test_check_hides_step_id_when_it_does_not_look_like_an_identifier() -> None:
    manifest = {"steps": [_step("post it now!", tools=_POST)]}

    assert "step '<not shown>'" in check(manifest)[0].message


def test_check_returns_nothing_when_manifest_has_no_steps_list() -> None:
    assert check({"steps": "x"}) == []
