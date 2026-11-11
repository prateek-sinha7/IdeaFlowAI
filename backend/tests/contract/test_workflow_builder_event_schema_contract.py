"""Contract: the Session_Stream event schema of the AI Workflow Builder is stable.

Snapshots the JSON schema of the ``BuilderEvent`` union (validation mode, as
``TypeAdapter(BuilderEvent).json_schema()`` returns it) into
``tests/fixtures/workflow_builder/builder_event_schema.json``, and checks that
``BuilderModelsResponse.models`` items are ``ModelCatalogEntry``.

A deliberate event change fails the snapshot test with a diff. Regenerate with
``BUILDER_CONTRACT_SNAPSHOT_UPDATE=1`` (see ``_builder_snapshot.py``); this is
not ``SNAPSHOT_UPDATE``, which belongs to the INV-3 goldens.

Requirements 38.1, 41.14 and 49.6.
"""

from __future__ import annotations

import typing
from typing import Any, Final

import pytest
from pydantic import TypeAdapter

from app.agents.workflow_builder.events import BuilderEvent, event_types
from app.api.capabilities import ModelCatalogEntry
from app.api.workflow_builder.schemas import BuilderModelsResponse
from tests.contract._builder_snapshot import assert_matches_snapshot

_SNAPSHOT_NAME: Final = "builder_event_schema.json"
_DEF_PREFIX: Final = "#/$defs/"

#: Events scoped to one Turn carry ``turn_id`` and ``seq`` (Req 38.2).
_TURN_SCOPED_TYPES: Final = frozenset(
    {
        "turn_started",
        "stage",
        "thinking",
        "tool_started",
        "tool_finished",
        "check_result",
        "draft_applied",
        "text",
        "limit_warning",
        "turn_completed",
    }
)


@pytest.fixture(scope="module")
def event_schema() -> dict[str, Any]:
    """The JSON schema of the ``BuilderEvent`` union."""
    return TypeAdapter(BuilderEvent).json_schema()


def _variants(schema: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Map each wire type name to the schema definition of its event class."""
    mapping: dict[str, str] = schema["discriminator"]["mapping"]
    return {
        type_name: schema["$defs"][ref[len(_DEF_PREFIX) :]]
        for type_name, ref in mapping.items()
    }


def test_event_schema_matches_snapshot_when_events_unchanged(
    event_schema: dict[str, Any],
) -> None:
    assert_matches_snapshot(_SNAPSHOT_NAME, event_schema)


def test_event_schema_discriminates_on_type_when_union_is_built(
    event_schema: dict[str, Any],
) -> None:
    assert event_schema["discriminator"]["propertyName"] == "type"
    assert set(event_schema["discriminator"]["mapping"]) == event_types()
    assert len(event_schema["oneOf"]) == len(event_types())


def test_event_schema_gives_each_variant_its_type_constant_when_defs_are_read(
    event_schema: dict[str, Any],
) -> None:
    for type_name, definition in _variants(event_schema).items():
        assert definition["properties"]["type"]["const"] == type_name


def test_event_schema_requires_a_timestamp_when_any_event_is_described(
    event_schema: dict[str, Any],
) -> None:
    for type_name, definition in _variants(event_schema).items():
        assert "ts" in definition["required"], type_name


def test_event_schema_requires_turn_id_and_seq_when_event_is_turn_scoped(
    event_schema: dict[str, Any],
) -> None:
    variants = _variants(event_schema)

    for type_name in _TURN_SCOPED_TYPES:
        required = set(variants[type_name]["required"])
        assert {"turn_id", "seq"} <= required, type_name


def test_builder_models_response_lists_model_catalog_entries_when_field_is_read() -> (
    None
):
    annotation = BuilderModelsResponse.model_fields["models"].annotation

    assert typing.get_origin(annotation) is list
    assert typing.get_args(annotation) == (ModelCatalogEntry,)


def test_builder_models_response_schema_refers_to_model_catalog_entry_when_built() -> (
    None
):
    schema = BuilderModelsResponse.model_json_schema()
    models = schema["properties"]["models"]

    assert models["items"] == {"$ref": f"{_DEF_PREFIX}ModelCatalogEntry"}
    assert schema["$defs"]["ModelCatalogEntry"] == ModelCatalogEntry.model_json_schema()
