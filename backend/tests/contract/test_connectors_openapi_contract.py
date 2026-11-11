"""Contract: the OpenAPI slice of ``/api/connectors`` is stable.

Snapshots the connectors part of ``app.openapi()``: every path under
``/api/connectors`` plus the component schemas those paths reference. The committed
file is ``tests/fixtures/connectors/openapi_connectors_paths.json``.

A deliberate API change fails the snapshot test with a diff. Regenerate with
``BUILDER_CONTRACT_SNAPSHOT_UPDATE=1`` (see ``_builder_snapshot.py``; the flag name
is shared by all contract snapshots and is not ``SNAPSHOT_UPDATE``, which belongs to
the INV-3 goldens).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Final

import pytest

from app.main import app
from tests.contract._builder_snapshot import assert_matches_snapshot

_SNAPSHOT_NAME: Final = "openapi_connectors_paths.json"
_SNAPSHOT_DIR: Final = Path(__file__).resolve().parents[1] / "fixtures" / "connectors"
_PREFIX: Final = "/api/connectors"
_REF_PREFIX: Final = "#/components/schemas/"

#: Every operation the connectors API offers. A route added or removed must be a
#: deliberate edit here and in the snapshot.
_EXPECTED_OPERATIONS: Final = frozenset(
    {
        ("get", "/api/connectors"),
        ("get", "/api/connectors/oauth/callback"),
        ("post", "/api/connectors/{key}/authorize"),
        ("delete", "/api/connectors/{key}"),
        ("get", "/api/connectors/{key}/tools"),
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


def connectors_slice(document: dict[str, Any]) -> dict[str, Any]:
    """Return the connectors paths and the component schemas they reach."""
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
def connectors_openapi() -> dict[str, Any]:
    """The connectors slice of the live OpenAPI document, built once per module."""
    return connectors_slice(app.openapi())


def test_connectors_slice_matches_snapshot_when_routes_unchanged(
    connectors_openapi: dict[str, Any],
) -> None:
    assert_matches_snapshot(_SNAPSHOT_NAME, connectors_openapi, directory=_SNAPSHOT_DIR)


def test_connectors_slice_lists_every_operation_when_app_is_built(
    connectors_openapi: dict[str, Any],
) -> None:
    actual = {
        (method, path)
        for path, operations in connectors_openapi["paths"].items()
        for method in operations
        if method in _HTTP_METHODS
    }

    assert actual == _EXPECTED_OPERATIONS


def test_connectors_slice_resolves_every_reference_when_schemas_are_collected(
    connectors_openapi: dict[str, Any],
) -> None:
    refs: set[str] = set()
    _collect_refs(connectors_openapi, refs)

    assert refs
    assert refs <= set(connectors_openapi["components"]["schemas"])


def test_response_schemas_carry_no_secret_fields_when_schemas_are_read(
    connectors_openapi: dict[str, Any],
) -> None:
    fragments = ("token", "secret", "ciphertext", "verifier", "password")
    exact = {"code", "state"}
    leaking = {
        f"{schema}.{prop}"
        for schema, body in connectors_openapi["components"]["schemas"].items()
        for prop in body.get("properties", {})
        if prop in exact or any(fragment in prop for fragment in fragments)
    }

    assert leaking == set()


def test_callback_is_listed_as_public_when_allowlist_is_read() -> None:
    allowlist = (
        Path(__file__).resolve().parents[1] / "security" / "public_routes_allowlist.txt"
    ).read_text(encoding="utf-8")

    assert "GET /api/connectors/oauth/callback  #" in allowlist
