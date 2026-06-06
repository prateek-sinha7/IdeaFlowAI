"""Template preview asset serving — `/templates/{id}/assets/{path}` + the guard.

REGRESSION GUARD
----------------
A template whose ``example.html`` is a thin iframe wrapper
(``<iframe src="./assets/template.html">``) previewed BLANK in the gallery: the
browser resolved the relative ``./assets/template.html`` against the
``/templates/{id}/preview`` path, but the backend had no route to serve the
template's assets → 404 → empty iframe.

These tests pin the fix: a traversal-safe ``od_loader.get_template_asset_path``
helper and the FastAPI route that serves it (unauthenticated, read-only,
confined to the template's ``assets/`` dir).
"""

from __future__ import annotations

import pytest

from app.services import od_loader

# A real shipped template whose example.html iframe-references ./assets/template.html
# — the exact template the 404 was reported on.
TEMPLATE_ID = "flowai-live-dashboard-template"


pytestmark = pytest.mark.skipif(
    od_loader.get_template(TEMPLATE_ID) is None,
    reason=f"{TEMPLATE_ID} not present on disk",
)


# ---------------------------------------------------------------------------
# od_loader.get_template_asset_path — happy path + traversal safety
# ---------------------------------------------------------------------------


def test_resolves_real_asset_under_assets_dir():
    p = od_loader.get_template_asset_path(TEMPLATE_ID, "template.html")
    assert p is not None
    assert p.is_file()
    assert p.name == "template.html"
    assert p.parent.name == "assets"
    assert p.read_text(encoding="utf-8").strip() != ""


def test_missing_asset_returns_none():
    assert od_loader.get_template_asset_path(TEMPLATE_ID, "does-not-exist.png") is None


def test_unknown_template_returns_none():
    assert od_loader.get_template_asset_path("no-such-template-xyz", "template.html") is None


@pytest.mark.parametrize(
    "evil",
    [
        "../SKILL.md",  # a real sibling OUTSIDE assets/ — must be blocked
        "../example.html",
        "../../design-systems/github/DESIGN.md",
        "../../../../../../etc/passwd",
        "/etc/passwd",
    ],
)
def test_path_traversal_is_blocked(evil):
    assert od_loader.get_template_asset_path(TEMPLATE_ID, evil) is None


@pytest.mark.parametrize("evil_id", ["../app", "..", ".", "a/b", "a\\b", ""])
def test_template_id_traversal_is_blocked(evil_id):
    assert od_loader.get_template_asset_path(evil_id, "template.html") is None


# ---------------------------------------------------------------------------
# The route — unauthenticated, serves the asset, 404 on miss
# ---------------------------------------------------------------------------


@pytest.fixture
def client():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api.prototype_templates import router

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_route_serves_template_html_unauthenticated(client):
    resp = client.get(f"/api/prototype/templates/{TEMPLATE_ID}/assets/template.html")
    assert resp.status_code == 200, resp.text
    assert resp.text.strip() != ""
    assert resp.headers["content-type"].startswith("text/html")


def test_route_404_for_missing_asset(client):
    resp = client.get(f"/api/prototype/templates/{TEMPLATE_ID}/assets/missing.png")
    assert resp.status_code == 404


def test_route_404_for_unknown_template(client):
    resp = client.get("/api/prototype/templates/no-such-template-xyz/assets/template.html")
    assert resp.status_code == 404


def test_preview_iframe_reference_is_now_servable(client):
    """End-to-end: the example.html wrapper references the seed, and it now serves."""
    preview_path = od_loader.get_template_preview_path(TEMPLATE_ID)
    assert preview_path is not None
    example = preview_path.read_text(encoding="utf-8")
    assert "assets/template.html" in example  # the wrapper references the seed
    resp = client.get(f"/api/prototype/templates/{TEMPLATE_ID}/assets/template.html")
    assert resp.status_code == 200  # …and that reference no longer 404s
