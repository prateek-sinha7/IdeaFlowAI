"""Plan 08-08 Task 1 — GET /api/capabilities serves the registry palette (API-02).

This router surfaces the hardened **capability registry palette** to the
composer (D-11): for each registered ``(kind, name)`` it returns kind, name,
``user_allowed`` (the CAP-03 trust flag) and a forward-compat ``config_schema``
slot, plus the model catalog (the ``model_catalog`` kind, expanded from
``ModelCatalog``). These tests pin:

* ``test_requires_auth`` — 401 without a token (``get_current_user`` not
  overridden); 200 with the dependency satisfied. Same posture as every other
  read endpoint (T-08-08-auth).
* ``test_palette_carries_required_fields`` — every entry has
  kind/name/user_allowed/config_schema; the runtime/skill/hook kinds and the
  model catalog are present.
* ``test_palette_reflects_registry`` — a freshly ``@register``'d capability
  appears in the palette with NO endpoint edit (the endpoint enumerates the
  registry, never a hardcoded list).
* ``test_privileged_caps_not_user_allowed`` — privileged kinds (exec/secrets/
  spawn / runtimes) surface ``user_allowed=False`` (T-08-08-ID).
* ``test_new_ws_events_flow_through_generic_forward`` — the new
  ``validator_result``/``validation_warning``/``gate_*`` event TYPES require NO
  ``websocket.py`` edit (the generic forward passes any ``event["type"]``
  through), so the existing-workflow event contract is unchanged (API-03 /
  additive-only).

Drives a FastAPI ``TestClient`` (the ``test_workflows_api.py`` pattern). The
router issues NO DB query, so no ``get_db`` override is needed when auth is
overridden.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI, HTTPException, status
from fastapi.testclient import TestClient

from agents.capabilities import registry as registry_mod
from agents.capabilities.model_catalog import ModelCatalog
from agents.capabilities.registry import register
from app.api.capabilities import router
from app.core.dependencies import get_current_user


class _FakeUser:
    def __init__(self, id: str):
        self.id = id


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def authed_client():
    app = _make_app()
    app.dependency_overrides[get_current_user] = lambda: _FakeUser(id="user-1")
    return TestClient(app)


@pytest.fixture
def unauthed_client():
    """A client whose ``get_current_user`` raises 401 (no token / invalid token)."""
    app = _make_app()

    def _raise_401():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    app.dependency_overrides[get_current_user] = _raise_401
    return TestClient(app)


# ---------------------------------------------------------------------------
# Auth (T-08-08-auth) — an unauthenticated client must not read the palette
# ---------------------------------------------------------------------------


class TestAuth:
    def test_requires_auth(self, unauthed_client):
        resp = unauthed_client.get("/api/capabilities")
        assert resp.status_code == 401, resp.text

    def test_authenticated_returns_200(self, authed_client):
        resp = authed_client.get("/api/capabilities")
        assert resp.status_code == 200, resp.text


# ---------------------------------------------------------------------------
# Palette shape (API-02) — kind/name/user_allowed/config_schema + the kinds
# ---------------------------------------------------------------------------


class TestPaletteShape:
    def test_palette_carries_required_fields(self, authed_client):
        body = authed_client.get("/api/capabilities").json()
        caps = body["capabilities"]
        assert caps, "palette is empty"
        for entry in caps:
            # Existing keys preserved (API-02 / D-10 — additive, none removed).
            assert set(("kind", "name", "user_allowed")).issubset(entry), entry
            assert "config_schema" in entry, entry
            assert isinstance(entry["user_allowed"], bool), entry
            # SURF-02 additive metadata — every entry carries description +
            # security_gated + a config_schema slot.
            assert "description" in entry, entry
            assert isinstance(entry["description"], str), entry
            assert "security_gated" in entry, entry
            assert isinstance(entry["security_gated"], bool), entry
            assert isinstance(entry["config_schema"], dict), entry

    def test_security_gated_is_derived_from_user_allowed(self, authed_client):
        # security_gated is DERIVED (not a second stored source): it is exactly
        # the inverse of user_allowed for every entry (RESEARCH discretion A2).
        body = authed_client.get("/api/capabilities").json()
        for entry in body["capabilities"]:
            assert entry["security_gated"] is (not entry["user_allowed"]), entry

    def test_privileged_entry_is_security_gated(self, authed_client):
        # At least one privileged capability (user_allowed=False, e.g. a runtime)
        # surfaces security_gated=True.
        body = authed_client.get("/api/capabilities").json()
        gated = [e for e in body["capabilities"] if e["security_gated"]]
        assert gated, "no security_gated capability in palette"
        for e in gated:
            assert e["user_allowed"] is False, e

    def test_descriptions_authored_for_surfaced_caps(self, authed_client):
        # The registry-authored descriptions surface non-empty for the
        # capabilities the palette renders (D-08 — registry-sourced).
        body = authed_client.get("/api/capabilities").json()
        described = [e for e in body["capabilities"] if e["description"].strip()]
        assert described, "no capability carries an authored description"

    def test_config_schema_populated_for_config_taking_caps(self, authed_client):
        # config_schema is no longer the literal {} stub for every entry: at
        # least one config-taking capability returns a non-empty schema (D-09).
        body = authed_client.get("/api/capabilities").json()
        with_schema = [e for e in body["capabilities"] if e["config_schema"]]
        assert with_schema, "no capability carries a populated config_schema"
        # The security gate authors its exec/network/secrets/spawn config shape.
        sec = [
            e
            for e in body["capabilities"]
            if e["kind"] == "gate" and e["name"] == "security"
        ]
        assert sec, "security gate missing from palette"
        assert sec[0]["config_schema"], "security gate config_schema is the {} stub"

    def test_runtime_skill_hook_kinds_present(self, authed_client):
        body = authed_client.get("/api/capabilities").json()
        kinds = {e["kind"] for e in body["capabilities"]}
        for required in ("runtime", "skill", "hook", "gate", "validator", "tool"):
            assert required in kinds, f"missing kind '{required}' in palette {kinds}"

    def test_model_catalog_present(self, authed_client):
        body = authed_client.get("/api/capabilities").json()
        # The model catalog is surfaced expanded (per-model entries), sourced
        # from ModelCatalog — not a hardcoded list.
        models = body["model_catalog"]
        catalog_ids = {m.id for m in ModelCatalog().list()}
        api_ids = {m["id"] for m in models}
        assert api_ids == catalog_ids, (catalog_ids ^ api_ids)
        for m in models:
            assert set(("id", "label", "user_allowed")).issubset(m), m


# ---------------------------------------------------------------------------
# Registry-reflective (API-02) — a new @register appears with NO endpoint edit
# ---------------------------------------------------------------------------


class TestRegistryReflective:
    def test_palette_reflects_registry(self, authed_client):
        # Register a brand-new capability at runtime; it must appear in the
        # palette WITHOUT any endpoint code change (the endpoint enumerates
        # _KNOWN, never a hardcoded list).
        kind, name = "validator", "_test_capabilities_api_probe"
        added = (kind, name) not in registry_mod._KNOWN
        try:

            @register(kind, name, user_allowed=True)
            class _Probe:  # noqa: D401 - test capability impl
                name = "_test_capabilities_api_probe"

                async def validate(self, target):  # pragma: no cover - never called
                    return []

            body = authed_client.get("/api/capabilities").json()
            found = [
                e
                for e in body["capabilities"]
                if e["kind"] == kind and e["name"] == name
            ]
            assert found, "freshly registered capability not in palette"
            assert found[0]["user_allowed"] is True
        finally:
            if added:
                registry_mod._KNOWN.discard((kind, name))
                registry_mod._IMPLS.pop((kind, name), None)
                registry_mod._TRUST.pop((kind, name), None)


# ---------------------------------------------------------------------------
# Information disclosure (T-08-08-ID) — privileged kinds not user-allowed
# ---------------------------------------------------------------------------


class TestTrustFlags:
    def test_runtimes_not_user_allowed(self, authed_client):
        body = authed_client.get("/api/capabilities").json()
        runtimes = [e for e in body["capabilities"] if e["kind"] == "runtime"]
        assert runtimes, "no runtime kind in palette"
        for e in runtimes:
            # Privileged kinds default off the user palette (08-01 / D-02).
            assert e["user_allowed"] is False, e


# ---------------------------------------------------------------------------
# Additive WS events (API-03 / T-08-08-parity) — new event TYPES need no
# websocket.py edit; the generic forward passes any event["type"] through.
# ---------------------------------------------------------------------------


class TestAdditiveEvents:
    def test_new_event_types_need_no_websocket_edit(self):
        # The generic forward (websocket.py ~595) emits {"type": event["type"]}
        # for ANY event type — so validator_result/validation_warning/gate_*
        # flow through unchanged. Assert the forward has no per-type allow-list
        # that would have to be edited for the new types (additive-only proof).
        import inspect

        import app.api.websocket as ws

        src = inspect.getsource(ws)
        # The generic dict forward keys off event["type"] (not a closed set of
        # named-event branches the new types would have to be added to).
        assert '"type": event["type"]' in src, (
            "the generic event forward was changed; new event types must flow "
            "through the type-agnostic forward (no rename/remove — additive only)"
        )
