"""Contract: the OpenAPI slice of the AI Workflow Builder routes is stable.

The repository has no whole-application OpenAPI snapshot, so this file snapshots
only the builder part of ``app.openapi()``: every path under
``/api/workflow-builder`` plus the component schemas those paths reference,
directly or through other schemas. The committed file is
``tests/fixtures/workflow_builder/openapi_builder_paths.json``.

A deliberate API change fails the snapshot test with a diff. Regenerate with
``BUILDER_CONTRACT_SNAPSHOT_UPDATE=1`` (see ``_builder_snapshot.py``); this is
not ``SNAPSHOT_UPDATE``, which belongs to the INV-3 goldens.

Requirements 41.14 and 49.6.
"""

from __future__ import annotations

from typing import Any, Final

import pytest

from app.main import app
from tests.contract._builder_snapshot import assert_matches_snapshot

_SNAPSHOT_NAME: Final = "openapi_builder_paths.json"
_PREFIX: Final = "/api/workflow-builder"
_REF_PREFIX: Final = "#/components/schemas/"

#: Every operation the builder offers (design 3.2.1 and 3.3). A route added or
#: removed must be a deliberate edit here and in the snapshot.
_EXPECTED_OPERATIONS: Final = frozenset(
    {
        ("get", "/api/workflow-builder/models"),
        ("get", "/api/workflow-builder/sessions"),
        ("post", "/api/workflow-builder/sessions"),
        ("get", "/api/workflow-builder/sessions/{session_id}"),
        ("delete", "/api/workflow-builder/sessions/{session_id}"),
        ("post", "/api/workflow-builder/sessions/{session_id}/link"),
        ("post", "/api/workflow-builder/sessions/{session_id}/messages"),
        ("post", "/api/workflow-builder/sessions/{session_id}/turns/{turn_id}/retry"),
        ("post", "/api/workflow-builder/sessions/{session_id}/turns/{turn_id}/cancel"),
        ("post", "/api/workflow-builder/sessions/{session_id}/undo"),
        ("get", "/api/workflow-builder/sessions/{session_id}/events"),
    }
)

_HTTP_METHODS: Final = frozenset(
    {"get", "put", "post", "delete", "patch", "options", "head"}
)


def _collect_refs(node: Any, found: set[str]) -> None:
    """Add the component schema name of every ``$ref`` under ``node`` to ``found``."""
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith(_REF_PREFIX):
            found.add(ref[len(_REF_PREFIX) :])
        for value in node.values():
            _collect_refs(value, found)
    elif isinstance(node, list):
        for item in node:
            _collect_refs(item, found)


def builder_slice(document: dict[str, Any]) -> dict[str, Any]:
    """Return the builder paths and the component schemas they reach."""
    paths = {
        path: operations
        for path, operations in document["paths"].items()
        if path == _PREFIX or path.startswith(_PREFIX + "/")
    }
    all_schemas: dict[str, Any] = document.get("components", {}).get("schemas", {})
    needed: set[str] = set()
    _collect_refs(paths, needed)
    pending = sorted(needed)
    while pending:
        name = pending.pop()
        extra: set[str] = set()
        _collect_refs(all_schemas.get(name, {}), extra)
        for found in sorted(extra - needed):
            needed.add(found)
            pending.append(found)
    return {
        "paths": paths,
        "components": {
            "schemas": {
                name: all_schemas[name]
                for name in sorted(needed)
                if name in all_schemas
            }
        },
    }


@pytest.fixture(scope="module")
def builder_openapi() -> dict[str, Any]:
    """The builder slice of the live OpenAPI document, built once per module."""
    return builder_slice(app.openapi())


def test_builder_slice_matches_snapshot_when_routes_unchanged(
    builder_openapi: dict[str, Any],
) -> None:
    assert_matches_snapshot(_SNAPSHOT_NAME, builder_openapi)


def test_builder_slice_lists_every_builder_operation_when_app_is_built(
    builder_openapi: dict[str, Any],
) -> None:
    actual = {
        (method, path)
        for path, operations in builder_openapi["paths"].items()
        for method in operations
        if method in _HTTP_METHODS
    }

    assert actual == _EXPECTED_OPERATIONS


def test_builder_slice_resolves_every_reference_when_schemas_are_collected(
    builder_openapi: dict[str, Any],
) -> None:
    refs: set[str] = set()
    _collect_refs(builder_openapi, refs)

    assert refs
    assert refs <= set(builder_openapi["components"]["schemas"])


def test_models_route_returns_builder_models_response_when_called_with_get(
    builder_openapi: dict[str, Any],
) -> None:
    operation = builder_openapi["paths"][f"{_PREFIX}/models"]["get"]
    ok_schema = operation["responses"]["200"]["content"]["application/json"]["schema"]

    assert ok_schema == {"$ref": f"{_REF_PREFIX}BuilderModelsResponse"}


def test_builder_models_response_lists_model_catalog_entries_when_schema_is_read(
    builder_openapi: dict[str, Any],
) -> None:
    schemas = builder_openapi["components"]["schemas"]
    models = schemas["BuilderModelsResponse"]["properties"]["models"]

    assert models["type"] == "array"
    assert models["items"] == {"$ref": f"{_REF_PREFIX}ModelCatalogEntry"}
    assert "ModelCatalogEntry" in schemas
