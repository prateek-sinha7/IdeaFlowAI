"""GET /api/workflows/{id} exposes the manifest's workflow-level authoring keys (gap 2).

The compiled ``steps`` and the raw ``manifest_steps`` leave out everything a built-in
declares beside its steps: ``limits``, ``input_providers``, ``seed_files``,
``capabilities`` and the other pass-through keys. A canvas that saved a built-in as a
user-owned copy therefore lost them (ISS-876). The detail payload now carries them in
``manifest``, without the identity keys that would make the copy pose as the built-in.

Drives the real router with ``get_current_user`` overridden. The caller's override
lookup (the endpoint's only DB read) is replaced, so no database is involved; the
override-in-force cases are covered by ``tests/integration/api``.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agents.execution_engine.engine import _WORKFLOWS_DIR
from agents.workflows.manifest import load_manifest
from app.api import workflows as workflows_module
from app.core.dependencies import get_current_user
from app.models.database import get_db

# Identity and catalog-presentation keys. None may reach a copy.
_IDENTITY_KEYS = {
    "id",
    "name",
    "display_name",
    "short_name",
    "description",
    "icon",
    "version",
    "user_launchable",
    "is_beta",
    "launch_surface",
    "chained_from",
    "steps",
    "deliverable",
    "planner",
    "clarify",
}


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(workflows_module, "find_override", lambda *a, **k: None)
    app = FastAPI()
    app.include_router(workflows_module.router)
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id="user-1")
    app.dependency_overrides[get_db] = lambda: None
    return TestClient(app)


def _detail(client: TestClient, workflow_id: str, **params) -> dict:
    resp = client.get(f"/api/workflows/{workflow_id}", params=params)
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest.mark.parametrize("workflow_id", ["prototype_v2", "backlog"])
def test_get_workflow_exposes_limits_when_manifest_declares_them(
    client: TestClient, workflow_id: str
) -> None:
    body = _detail(client, workflow_id)

    assert body["manifest"]["limits"] == {
        "max_subagents": 200,
        "max_depth": 2,
        "wall_clock_seconds": 10800,
    }


def test_get_workflow_exposes_input_providers_when_manifest_declares_them(
    client: TestClient,
) -> None:
    body = _detail(client, "prototype")

    assert body["manifest"]["input_providers"] == ["run_images"]


def test_get_workflow_exposes_capabilities_when_manifest_declares_them(
    client: TestClient,
) -> None:
    body = _detail(client, "ex_playwright_smoke_test")

    assert body["manifest"]["capabilities"] == {"internet": False}


def test_get_workflow_omits_undeclared_keys_when_manifest_does_not_declare_them(
    client: TestClient,
) -> None:
    # prototype declares input_providers but no limits and an empty seed_files.
    body = _detail(client, "prototype")

    assert "limits" not in body["manifest"]
    assert "seed_files" not in body["manifest"]
    assert None not in body["manifest"].values()


@pytest.mark.parametrize("workflow_id", ["prototype", "prototype_v2", "backlog"])
def test_get_workflow_excludes_identity_keys_when_manifest_is_projected(
    client: TestClient, workflow_id: str
) -> None:
    body = _detail(client, workflow_id)

    assert not (_IDENTITY_KEYS & set(body["manifest"]))
    # Built-in identity stays in the top-level fields, separate from the copyable keys.
    assert body["id"] == workflow_id


def test_get_workflow_matches_file_manifest_when_a_key_is_declared(
    client: TestClient,
) -> None:
    manifest = load_manifest("prototype_v2", _WORKFLOWS_DIR)

    body = _detail(client, "prototype_v2")

    assert body["manifest"]["limits"] == manifest.limits
    assert body["manifest"].get("seed_files") == (manifest.seed_files or None)


def test_get_workflow_keeps_file_limits_when_an_override_is_in_force(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # An override only replaces steps; its own top-level keys must never leak into the
    # payload, or a copy of the user's copy would inherit them as if built-in.
    file_steps = load_manifest("prototype_v2", _WORKFLOWS_DIR).steps
    row = SimpleNamespace(
        id="override-1",
        override_enabled=True,
        manifest_json={"steps": file_steps, "limits": {"max_subagents": 1}},
    )
    monkeypatch.setattr(workflows_module, "find_override", lambda *a, **k: row)
    monkeypatch.setattr(
        workflows_module, "_overridden_plan", lambda compiled, _row: compiled
    )

    body = _detail(client, "prototype_v2")

    assert body["is_overridden"] is True
    assert body["manifest"]["limits"]["max_subagents"] == 200


def test_get_workflow_manifest_payload_has_no_secret_like_keys(
    client: TestClient,
) -> None:
    # Everything exposed is repo-authored config; guard against a future key that is not.
    body = _detail(client, "prototype_v2")

    flat = repr(body["manifest"]).lower()
    for needle in ("secret", "password", "token_value", "api_key", "credential"):
        assert needle not in flat
