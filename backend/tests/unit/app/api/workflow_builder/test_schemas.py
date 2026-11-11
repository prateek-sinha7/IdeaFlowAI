"""Unit tests for the builder API schemas (task 16.1, design 3.2.2).

Pure pydantic validation: no database, network or model.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from app.agents.workflow_builder import events
from app.api.workflow_builder import schemas
from app.api.workflow_builder.schemas import (
    CreateSessionRequest,
    LinkRequest,
    SendMessageRequest,
    TurnAccepted,
    UndoRequest,
)
from app.core.config import settings

MODEL = "eu.anthropic.claude-sonnet-5-5"


def _message(**overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "content": "Make a workflow",
        "model_id": MODEL,
        "effort": None,
        "canvas_state": {"steps": []},
        "client_message_id": "client-msg-0001",
    }
    values.update(overrides)
    return values


# --- CreateSessionRequest ---------------------------------------------------------------


def test_create_session_request_accepts_create_mode_without_workflow_id() -> None:
    request = CreateSessionRequest(mode="create", model_id=MODEL)

    assert request.workflow_id is None
    assert request.effort is None


@pytest.mark.parametrize("workflow_id", [None, ""])
def test_create_session_request_rejects_edit_mode_when_workflow_id_missing(
    workflow_id: str | None,
) -> None:
    with pytest.raises(ValidationError):
        CreateSessionRequest(mode="edit", workflow_id=workflow_id, model_id=MODEL)


def test_create_session_request_accepts_edit_mode_with_workflow_id() -> None:
    request = CreateSessionRequest(mode="edit", workflow_id="wf-1", model_id=MODEL)

    assert request.workflow_id == "wf-1"


def test_create_session_request_rejects_unknown_mode() -> None:
    with pytest.raises(ValidationError):
        CreateSessionRequest(mode="clone", model_id=MODEL)  # type: ignore[arg-type]


def test_create_session_request_rejects_unknown_keys() -> None:
    with pytest.raises(ValidationError):
        CreateSessionRequest.model_validate(
            {"mode": "create", "model_id": MODEL, "user_id": "someone-else"}
        )


# --- SendMessageRequest -----------------------------------------------------------------


def test_send_message_request_accepts_valid_body() -> None:
    request = SendMessageRequest.model_validate(_message())

    assert request.content == "Make a workflow"
    assert request.effort is None


@pytest.mark.parametrize("content", ["", "   ", "\n\t \u00a0"])
def test_send_message_request_rejects_content_when_empty_or_whitespace_only(
    content: str,
) -> None:
    with pytest.raises(ValidationError):
        SendMessageRequest.model_validate(_message(content=content))


def test_send_message_request_accepts_content_at_the_cap_and_rejects_one_over() -> None:
    cap = settings.BUILDER_MAX_MESSAGE_CHARS

    SendMessageRequest.model_validate(_message(content="a" * cap))
    with pytest.raises(ValidationError):
        SendMessageRequest.model_validate(_message(content="a" * (cap + 1)))


def test_send_message_request_counts_code_points_not_utf16_units() -> None:
    # An astral character is one code point (and two UTF-16 units).
    cap = settings.BUILDER_MAX_MESSAGE_CHARS

    SendMessageRequest.model_validate(_message(content="\U0001f600" * cap))
    with pytest.raises(ValidationError):
        SendMessageRequest.model_validate(_message(content="\U0001f600" * (cap + 1)))


def test_send_message_request_validator_message_never_echoes_the_content() -> None:
    # pydantic's own str() carries the input; the app's RequestValidationError handler
    # drops it. The validator's message must not add the content back (Req 42.5).
    marker = "SECRET-MARKER-" + "x" * settings.BUILDER_MAX_MESSAGE_CHARS

    with pytest.raises(ValidationError) as exc:
        SendMessageRequest.model_validate(_message(content=marker))

    assert "SECRET-MARKER" not in repr(exc.value.errors(include_input=False))


@pytest.mark.parametrize(
    "client_message_id", ["short", "x" * 65, "has space 1234", "bad/char/1234", ""]
)
def test_send_message_request_rejects_malformed_client_message_id(
    client_message_id: str,
) -> None:
    with pytest.raises(ValidationError):
        SendMessageRequest.model_validate(_message(client_message_id=client_message_id))


@pytest.mark.parametrize("client_message_id", ["abcd1234", "a_b-C_9" + "z" * 57])
def test_send_message_request_accepts_client_message_id_at_both_length_bounds(
    client_message_id: str,
) -> None:
    SendMessageRequest.model_validate(_message(client_message_id=client_message_id))


def test_send_message_request_requires_effort_and_canvas_state_keys() -> None:
    body = _message()
    del body["effort"]
    with pytest.raises(ValidationError):
        SendMessageRequest.model_validate(body)

    body = _message()
    del body["canvas_state"]
    with pytest.raises(ValidationError):
        SendMessageRequest.model_validate(body)


def test_send_message_request_rejects_unknown_keys() -> None:
    with pytest.raises(ValidationError):
        SendMessageRequest.model_validate(_message(session_id="s-1"))


# --- UndoRequest and LinkRequest --------------------------------------------------------


def test_undo_request_accepts_zero_and_rejects_negative_revision() -> None:
    assert UndoRequest(expected_revision=0).expected_revision == 0
    with pytest.raises(ValidationError):
        UndoRequest(expected_revision=-1)


def test_link_request_rejects_empty_workflow_id() -> None:
    assert LinkRequest(workflow_id="wf-1").workflow_id == "wf-1"
    with pytest.raises(ValidationError):
        LinkRequest(workflow_id="")


@pytest.mark.parametrize(
    ("model", "body"),
    [
        (CreateSessionRequest, {"mode": "create", "model_id": "{long}"}),
        (
            CreateSessionRequest,
            {"mode": "create", "model_id": MODEL, "effort": "{long}"},
        ),
        (
            CreateSessionRequest,
            {"mode": "edit", "model_id": MODEL, "workflow_id": "{long}"},
        ),
        (LinkRequest, {"workflow_id": "{long}"}),
    ],
    ids=["create-model", "create-effort", "create-workflow", "link-workflow"],
)
def test_request_rejects_id_when_longer_than_cap(
    model: type[CreateSessionRequest] | type[LinkRequest], body: dict[str, Any]
) -> None:
    at_cap = "a" * schemas.MAX_ID_CHARS
    over_cap = at_cap + "a"
    model.model_validate({k: at_cap if v == "{long}" else v for k, v in body.items()})
    with pytest.raises(ValidationError):
        model.model_validate(
            {k: over_cap if v == "{long}" else v for k, v in body.items()}
        )


@pytest.mark.parametrize("field", ["model_id", "effort"])
def test_send_message_request_rejects_field_when_longer_than_cap(field: str) -> None:
    SendMessageRequest.model_validate(_message(**{field: "a" * schemas.MAX_ID_CHARS}))
    with pytest.raises(ValidationError):
        SendMessageRequest.model_validate(
            _message(**{field: "a" * (schemas.MAX_ID_CHARS + 1)})
        )


# --- Responses --------------------------------------------------------------------------


def test_turn_accepted_defaults_replayed_to_false() -> None:
    accepted = TurnAccepted(turn_id="t-1", message_id="m-1")

    assert accepted.replayed is False
    assert accepted.model_dump() == {
        "turn_id": "t-1",
        "message_id": "m-1",
        "replayed": False,
    }


def test_response_models_reject_unknown_keys() -> None:
    with pytest.raises(ValidationError):
        TurnAccepted.model_validate({"turn_id": "t", "message_id": "m", "extra": 1})


def test_shared_value_models_are_the_event_models_not_copies() -> None:
    assert schemas.ToolActivityOut is events.ToolActivity
    assert schemas.CheckResultOut is events.CheckResult
    assert schemas.ActivityLine is events.ToolActivity
    assert schemas.ChangeSummary is events.ChangeSummary
    assert schemas.LaunchNeed is events.LaunchNeed
    assert schemas.RunningTurnSnapshot is events.RunningTurnSnapshot


def test_builder_models_response_carries_default_effort_per_model() -> None:
    response = schemas.BuilderModelsResponse(
        models=[], default_model_id=MODEL, default_efforts={MODEL: "medium", "m2": None}
    )

    assert response.default_efforts == {MODEL: "medium", "m2": None}
