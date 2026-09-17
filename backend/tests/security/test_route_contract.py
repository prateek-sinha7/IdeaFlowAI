"""T12 — every HTTP endpoint is authenticated, or explicitly declared public.

An endpoint that forgets its auth dependency is not a visible bug. It returns
200, its tests pass, and the only symptom is that anyone on the internet can call
it. That is precisely the class of mistake a contract test should catch, because
nothing else will.

WHAT WAS WRONG WITH THE PREVIOUS VERSION
----------------------------------------
It iterated ``app.routes`` and skipped anything without ``.methods``. On this
FastAPI version ``include_router`` does NOT flatten routes into ``app.routes`` —
it appends a ``fastapi.routing._IncludedRouter`` wrapper holding the original
router under ``original_router``. Those wrappers have no ``.methods``, so every
one was skipped.

Measured at the time of this rewrite: ``app.routes`` held 29 entries, of which 5
had ``.methods`` (the ``/docs``, ``/openapi.json`` and ``/redoc`` handlers FastAPI
mounts itself) and 24 were router wrappers. So the test inspected five
documentation routes and not one application endpoint, and passed — a green check
that guaranteed nothing. That is worse than no test: it occupies the slot where
real coverage would go.

Descending through ``original_router`` is the whole fix.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.main import app

#: Dependencies that establish an authenticated caller. Any one is sufficient.
#
# ``get_current_principal`` belongs here and was missing from the original list.
# It performs the same bearer verification as ``get_current_user`` and simply
# ALSO returns the resolved Principal, because the caller needs the token's
# ``cognito:groups`` for an entitlement decision. Omitting it meant every route
# that needs a tier gate — POST /api/runs, /messages, /resume, /revisions and
# POST /api/user-workflows — looked unauthenticated. Those are among the most
# sensitive endpoints in the app, so the omission would have produced either a
# false alarm or, worse, five bogus public-route allow-list entries.
_AUTH_DEPENDENCIES = {
    "get_current_user",
    "get_current_user_with_payload",
    "get_current_principal",
    "get_current_user_for_refresh",
    "get_user_for_logout",
    "require_admin",
    "get_user_via_api_key",
    "resolve_api_key",
    # api/mcp.py's transport-local authenticator. It carries the API key on the
    # Authorization header rather than X-Flowin-API-Key, so it cannot reuse the
    # get_user_via_api_key DEPENDENCY — it CALLS resolve_api_key inside its body
    # instead. That means `resolve_api_key` never appears in the dependant tree,
    # and without naming this wrapper both /mcp/handoff routes read as public
    # when they in fact 401 without a valid key.
    "_get_user_from_bearer",
}

_ALLOWLIST_PATH = Path(__file__).parent / "public_routes_allowlist.txt"


def _iter_api_routes(routes):
    """Yield real endpoint routes, descending through included-router wrappers.

    Without this, `app.routes` yields wrappers and the caller sees no endpoints.
    """
    for route in routes:
        included = getattr(route, "original_router", None)
        if included is not None:
            yield from _iter_api_routes(included.routes)
        else:
            yield route


def _collect_dependency_names(dependant) -> set[str]:
    """Names of every dependency reachable from a route's dependant tree.

    Recursive because auth is frequently nested — ``require_admin`` itself depends
    on ``get_current_user_with_payload``. A one-level read would miss the inner
    one and misreport which guard is actually in force.
    """
    names: set[str] = set()
    if dependant is None:
        return names
    for dep in getattr(dependant, "dependencies", None) or ():
        call = getattr(dep, "call", None) or getattr(dep, "dependency", None)
        if call is not None and hasattr(call, "__name__"):
            names.add(call.__name__)
        names.update(_collect_dependency_names(dep))
    return names


def _load_allowlist() -> dict[str, str]:
    """Parse ``METHOD /path  # reason`` into key -> reason.

    utf-8-sig because this repo is edited on Windows, where a BOM would otherwise
    become part of the first entry.
    """
    if not _ALLOWLIST_PATH.exists():
        return {}

    entries: dict[str, str] = {}
    for raw in _ALLOWLIST_PATH.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        signature, _, reason = line.partition("#")
        signature = signature.strip()
        reason = reason.strip()
        if not signature:
            continue
        if not reason:
            pytest.fail(
                f"{_ALLOWLIST_PATH.name}: {signature!r} has no reason. "
                "An unauthenticated endpoint must say why it is safe to expose."
            )
        entries[signature] = reason
    return entries


def _endpoint_signatures() -> dict[str, set[str]]:
    """Map ``METHOD /path`` -> dependency names, for every real endpoint."""
    found: dict[str, set[str]] = {}
    for route in _iter_api_routes(app.routes):
        methods = getattr(route, "methods", None)
        path = getattr(route, "path", None)
        if not methods or path is None:
            continue
        deps = _collect_dependency_names(getattr(route, "dependant", None))
        for method in methods:
            found[f"{method} {path}"] = deps
    return found


def test_the_route_tree_is_actually_being_walked():
    """Guard the guard: prove the traversal reaches application endpoints.

    The previous version's failure mode was silence — it found nothing and passed.
    Asserting a floor on what the walk discovers, and naming an endpoint that must
    be in it, makes a repeat of that failure loud instead of invisible.
    """
    signatures = _endpoint_signatures()

    assert len(signatures) > 100, (
        f"only {len(signatures)} endpoints discovered — the traversal is almost "
        "certainly not descending into included routers, which is exactly how "
        "this test previously passed while inspecting nothing"
    )
    assert "GET /api/admin/users" in signatures, (
        "a known admin endpoint is missing from the walk; the traversal is "
        "incomplete and any 'all routes protected' result would be meaningless"
    )


def test_all_routes_are_protected_or_allowlisted():
    """Every endpoint has an auth dependency or an approved public entry."""
    allowed = _load_allowlist()
    unprotected: list[str] = []

    for signature, deps in sorted(_endpoint_signatures().items()):
        if deps & _AUTH_DEPENDENCIES:
            continue
        if signature in allowed:
            continue
        unprotected.append(signature)

    assert not unprotected, (
        "These endpoints have NO authentication dependency and are not "
        "allow-listed:\n"
        + "\n".join(f"  {s}" for s in unprotected)
        + f"\n\nAdd an auth dependency, or add the route to "
        f"{_ALLOWLIST_PATH.name} with the reason it must be public."
    )


def test_allowlist_has_no_stale_entries():
    """A public-route exemption for a route that no longer exists must be removed.

    Stale entries are not merely untidy: a future endpoint that happens to reuse
    the same method and path inherits a pre-approved exemption from auth without
    anyone reviewing it.
    """
    allowed = _load_allowlist()
    live = set(_endpoint_signatures())

    stale = sorted(set(allowed) - live)
    assert not stale, (
        "These allow-list entries match no current route and should be deleted:\n"
        + "\n".join(f"  {s}" for s in stale)
    )


def test_allowlisted_routes_are_genuinely_unauthenticated():
    """An allow-listed route that has since GAINED auth should leave the list.

    Keeping it listed understates the app's real posture and, worse, would keep
    the exemption in place if the dependency were later removed again.
    """
    allowed = _load_allowlist()
    signatures = _endpoint_signatures()

    now_protected = sorted(
        s for s in allowed if signatures.get(s, set()) & _AUTH_DEPENDENCIES
    )
    assert not now_protected, (
        "These routes are allow-listed as public but now require auth — remove "
        "them from the allow-list:\n" + "\n".join(f"  {s}" for s in now_protected)
    )
