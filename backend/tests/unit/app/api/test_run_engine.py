"""Ingress layer 4 for connected-app grants: ``_reject_connector_selections``.

The predicate runs before any compile or run row, on the raw per-step selections
of a launch or flat save. It never touches I/O.
"""

from __future__ import annotations

import pytest

from app.api.run_engine import (
    CONNECTOR_GRANTS_NOT_ALLOWED_MESSAGE,
    _reject_connector_selections,
)

_JIRA = "jira__get_issue"
_GITHUB = "github__list_issues"


def test_reject_connector_selections_returns_message_when_a_step_names_connectors() -> (
    None
):
    selections = {"agent-a": {"tools": {"connectors": [_JIRA]}}}

    assert (
        _reject_connector_selections(selections) == CONNECTOR_GRANTS_NOT_ALLOWED_MESSAGE
    )


def test_reject_connector_selections_returns_message_when_only_a_later_step_names_them() -> (
    None
):
    selections = {
        "agent-a": {"tools": {"write_files": True}},
        "agent-b": {"tools": {"connectors": [_JIRA, _GITHUB]}},
    }

    assert (
        _reject_connector_selections(selections) == CONNECTOR_GRANTS_NOT_ALLOWED_MESSAGE
    )


def test_reject_connector_selections_returns_none_when_connectors_list_is_empty() -> (
    None
):
    selections = {"agent-a": {"tools": {"connectors": []}}}

    assert _reject_connector_selections(selections) is None


def test_reject_connector_selections_returns_none_when_steps_carry_other_tools_only() -> (
    None
):
    selections = {"agent-a": {"tools": {"write_files": True}, "model": "m"}}

    assert _reject_connector_selections(selections) is None


@pytest.mark.parametrize(
    "selections",
    [
        None,
        {},
        [],
        "connectors",
        {"agent-a": None},
        {"agent-a": "tools"},
        {"agent-a": {"tools": None}},
        {"agent-a": {"tools": ["connectors"]}},
    ],
)
def test_reject_connector_selections_returns_none_when_shape_cannot_carry_grants(
    selections: object,
) -> None:
    assert _reject_connector_selections(selections) is None


def test_connector_grants_not_allowed_message_names_the_save_as_own_remedy() -> None:
    assert "Predefined workflows cannot use connected apps" in (
        CONNECTOR_GRANTS_NOT_ALLOWED_MESSAGE
    )
    assert "save the workflow as your own" in CONNECTOR_GRANTS_NOT_ALLOWED_MESSAGE
