"""Implements ../../../screens/24-api-contract.feature.md.

Every test carries the `scenario` marker naming the Gherkin scenario it
implements; `capture/_scenarios.py` checks both directions of that link.

Every other module asserts what a USER SEES. That catches a broken screen and
misses a contract change underneath it — a route renamed, an auth dependency
dropped, a 201 becoming a 200. `capture/API-CONTRACT.json` is the regression
detector, and S-24-01..03 are what make it one.

Requests go out through the browser (`framework/api.py`) so a bearer token never
enters the test process. `api.full` is used rather than `api.request` wherever
a body is parsed: `request` truncates at 400 characters, which turns a populated
run sandbox into a JSON parse error and reads as an empty workspace.
"""

from __future__ import annotations

import json
import subprocess
import uuid
import sys
from pathlib import Path

import pytest
from playwright.sync_api import expect

from framework import accounts, api, settings
from framework.locators import run_history as RH

CAPTURE = Path(__file__).resolve().parents[3] / "capture"
SNAPSHOT = CAPTURE / "API-CONTRACT.json"

ADMIN_ENDPOINTS = [
    ("GET", "/api/admin/users"),
    ("POST", "/api/admin/users"),
    ("DELETE", "/api/admin/users/00000000-0000-0000-0000-000000000000"),
    ("POST", "/api/admin/users/00000000-0000-0000-0000-000000000000/reset-password"),
    ("PATCH", "/api/admin/users/00000000-0000-0000-0000-000000000000/role"),
    ("PATCH", "/api/admin/users/00000000-0000-0000-0000-000000000000/tier"),
]

MFA_ENDPOINTS = [
    ("GET", "/api/auth/mfa"),
    ("POST", "/api/auth/mfa/email/enable"),
    ("POST", "/api/auth/mfa/email/disable"),
    ("POST", "/api/auth/mfa/totp/associate"),
    ("POST", "/api/auth/mfa/totp/verify"),
]


def snapshot() -> dict:
    return json.loads(SNAPSHOT.read_text())


def regenerate() -> dict:
    """The inventory as `_api.py` extracts it from source RIGHT NOW."""
    out = subprocess.run(
        [sys.executable, str(CAPTURE / "_api.py"), "--json"],
        capture_output=True,
        text=True,
        cwd=CAPTURE.parent.parent.parent,
    )
    assert out.returncode == 0, f"_api.py --json failed: {out.stderr[-500:]}"
    return json.loads(SNAPSHOT.read_text())


def endpoints(inventory) -> dict:
    """`{"GET /api/runs": {...}}`, whatever shape the snapshot uses."""
    rows = inventory["endpoints"] if isinstance(inventory, dict) else inventory
    if isinstance(rows, dict):
        return rows
    return {f"{r['method']} {r['path']}": r for r in rows}


def my_run_id(page) -> str:
    """A completed run this account owns."""
    page.goto("/runs")
    expect(page.locator(RH.ROW).first).to_be_visible()
    done = [label for label in RH.rows(page) if RH.status_of(label) == "completed"]
    assert done, "no completed run to read a workspace from"
    page.locator(f'{RH.ROW}[aria-label="{done[0]}"]').first.click()
    page.wait_for_url(lambda url: "/runs/" in url)
    return page.url.split("/runs/")[1].split("/")[0].split("?")[0]


def sandbox_of(page, run_id: str) -> dict:
    return api.json_body(page, "GET", f"/api/runs/{run_id}/sandbox")


# ── the snapshot ─────────────────────────────────────────────────────────────


@pytest.mark.scenario("S-24-01")
def test_the_endpoint_inventory_matches_the_snapshot(page, shot):
    """Scenario: The endpoint inventory matches the snapshot

    THE regression test of this file. Any diff is a contract change; an intended
    one updates the snapshot in the same commit, so it is reviewed rather than
    discovered later.
    """
    with shot("api-snapshot", "When I regenerate the inventory from source"):
        page.goto("/dashboard")

    committed = snapshot()
    fresh = regenerate()
    before, after = endpoints(committed), endpoints(fresh)

    added = sorted(set(after) - set(before))
    removed = sorted(set(before) - set(after))
    changed = [k for k in set(before) & set(after) if before[k] != after[k]]

    assert not (added or removed or changed), (
        "the API contract moved without the snapshot moving with it.\n"
        f"  added:   {added}\n  removed: {removed}\n  changed: {changed}\n"
        "Regenerate with `python3 tests/integration/capture/_api.py --json` in "
        "the same commit as the change."
    )


@pytest.mark.scenario("S-24-02")
def test_no_endpoint_loses_its_authentication_silently(page, shot):
    """Scenario: No endpoint loses its authentication silently

    The single highest-value assertion here. A dropped
    `Depends(get_current_user)` is a one-line diff that no UI test can see.
    """
    with shot("auth-requirements", "When I regenerate the inventory"):
        page.goto("/dashboard")

    before, after = endpoints(snapshot()), endpoints(regenerate())
    demoted = [
        key
        for key, row in after.items()
        if key in before
        and before[key].get("auth") in ("user", "admin")
        and row.get("auth") == "public"
    ]
    assert not demoted, f"these endpoints lost their authentication: {demoted}"


@pytest.mark.scenario("S-24-03")
def test_the_public_list_is_exactly_eighteen_and_each_is_deliberate(page, shot):
    """Scenario: The public list is exactly eighteen, and each is deliberate

    A NEW public endpoint fails this and forces the reason to be written down
    before it ships.
    """
    with shot("public-endpoints", "Then exactly the recorded endpoints are public"):
        page.goto("/dashboard")

    committed = {k for k, r in endpoints(snapshot()).items() if r.get("auth") == "public"}
    current = {k for k, r in endpoints(regenerate()).items() if r.get("auth") == "public"}

    assert current == committed, (
        f"the public surface changed.\n  newly public: {sorted(current - committed)}\n"
        f"  no longer public: {sorted(committed - current)}"
    )
    spec = (CAPTURE.parent / "screens" / "24-api-contract.feature.md").read_text()
    for key in sorted(current):
        path = key.split(" ", 1)[1]
        assert path.split("{")[0].rstrip("/") in spec, (
            f"{key} is public and the spec does not say why"
        )


# ── authentication endpoints ─────────────────────────────────────────────────


@pytest.mark.scenario("S-24-04")
def test_a_request_with_no_credentials_is_answered_401_not_403(page, shot):
    """Scenario: A request with no credentials is answered 401, not 403

    FIX-311, restated here because this is the contract file.
    """
    with shot("no-credentials", "When I call an authenticated endpoint with no header"):
        page.goto("/dashboard")
        result = api.anonymous(page, "GET", "/api/runs")

    assert result["status"] == 401, (
        f"answered {result['status']} — 403 here is the FIX-311 regression"
    )


@pytest.mark.scenario("S-24-05")
def test_registration_is_permanently_closed(page, shot):
    """Scenario: Registration is permanently closed

    Declared as `status_code=HTTP_403_FORBIDDEN` on the route itself, not as a
    runtime check — it cannot succeed by configuration.
    """
    with shot("register-closed", "When I POST /api/auth/register"):
        page.goto("/dashboard")
        # With a well-formed body: FastAPI validates the payload BEFORE the
        # route's declared status is reached, so an empty POST answers 422 and
        # never proves the route is closed.
        result = api.full(
            page,
            "POST",
            "/api/auth/register",
            {"email": "nobody@example.com", "password": "not-a-real-password"},
        )

    assert result["status"] == 403, (
        f"registration answered {result['status']}: {result['body'][:200]}"
    )


@pytest.mark.scenario("S-24-06")
def test_login_returns_either_a_session_or_a_challenge(page, shot):
    """Scenario: Login returns either a session or a challenge

    A union, and that is what makes the five-challenge flow in 01-auth possible.
    A client assuming `AuthResponse` breaks on any MFA-enabled account.
    """
    with shot("login-union", "When I POST valid credentials"):
        page.goto("/login")
        result = api.full(
            page,
            "POST",
            "/api/auth/login",
            {"email": accounts.ADMIN, "password": accounts.PASSWORD},
        )

    assert result["status"] == 200, result["body"][:200]
    body = json.loads(result["body"])
    # Never assert on the token itself — only that the union is one of its two
    # arms.
    assert ("token" in body) ^ ("challenge" in body or "challenge_name" in body), (
        f"the response is neither an AuthResponse nor a challenge: {sorted(body)}"
    )


@pytest.mark.scenario("S-24-07")
@pytest.mark.skip(
    reason="needs a login that returns a challenge; this pool reports MFA as "
    "unsupported, so no challenge can be provoked (see S-09-13)"
)
def test_a_challenge_is_answered_on_its_own_endpoint(page, shot):
    """Scenario: A challenge is answered on its own endpoint"""


@pytest.mark.scenario("S-24-08")
@pytest.mark.defect
def test_logout_works_with_an_already_invalid_token(page, shot):
    """Scenario: Logout works with an already-invalid token

    Asserts TODAY'S behaviour, which contradicts the contract — D-34.

    `API-CONTRACT.json` records `POST /api/auth/logout` as **public** with
    **204**. The running server answers **401 "Invalid token"** both with no
    Authorization header and with a broken one. So a user whose session is
    already unusable — the only user who reaches for logout — cannot clear it
    through the API.

    This is precisely the drift this module exists to catch: the static
    inventory and the running implementation disagree, and no UI test can see
    it.
    """
    with shot("logout-invalid", "When I POST /api/auth/logout with a dead token"):
        page.goto("/login")
        results = {
            label: api.anonymous(page, "POST", "/api/auth/logout", header)
            for label, header in (("none", None), ("broken", "Bearer not-a-usable-token"))
        }

    for label, result in results.items():
        assert result["status"] == 401, (
            f"logout ({label}) answered {result['status']} — if it is 204, D-34 "
            "is fixed and this test should assert the contract instead"
        )


@pytest.mark.scenario("S-24-09")
def test_password_recovery_refuses_when_email_is_a_second_factor(page, shot):
    """Scenario: Password recovery refuses when email is a second factor

    202 is declared, so the response shape does not reveal whether the address
    exists. The refusal is correct — AWS disqualifies email as a recovery
    channel when it is also a second factor.
    """
    with shot("forgot-password", "When I POST /api/auth/forgot-password"):
        page.goto("/login")
        result = api.full(page, "POST", "/api/auth/forgot-password", {"email": accounts.ADMIN})

    assert result["status"] in (200, 202), result["body"][:200]
    # Whatever it answers, it must not confirm or deny the address.
    assert accounts.ADMIN not in result["body"], "the response echoed the address back"


@pytest.mark.scenario("S-24-10")
@pytest.mark.parametrize(("method", "path"), MFA_ENDPOINTS, ids=[p for _, p in MFA_ENDPOINTS])
def test_second_factor_management_requires_a_session(page, shot, method, path):
    """Scenario: Second-factor management requires a session

    Recorded because an earlier `_api.py` reported all five as PUBLIC: it matched
    dependency names exactly and missed `get_current_user_with_payload`. A
    mislabelled auth requirement in a contract spec is worse than no spec, so
    this asserts it against the running server rather than against the tool.
    """
    with shot(f"mfa-auth{path.replace('/', '-')}", f"Then {method} {path} requires a session"):
        page.goto("/dashboard")
        result = api.anonymous(page, method, path)

    assert result["status"] == 401, (
        f"{method} {path} answered {result['status']} without a session"
    )


# ── admin endpoints ──────────────────────────────────────────────────────────


@pytest.mark.scenario("S-24-11")
@pytest.mark.role("basic")
@pytest.mark.parametrize(("method", "path"), ADMIN_ENDPOINTS, ids=[p for _, p in ADMIN_ENDPOINTS])
def test_every_admin_endpoint_requires_an_admin(page, shot, method, path):
    """Scenario: Every admin endpoint requires an admin"""
    with shot(f"admin-gate{path.split('/')[3]}-{method.lower()}", f"Then {method} {path} is refused"):
        page.goto("/dashboard")
        result = api.request(page, method, path)

    assert result["status"] in (401, 403), (
        f"{method} {path} answered {result['status']} for a non-admin: "
        f"{result['body'][:200]}"
    )


@pytest.mark.scenario("S-24-12")
@pytest.mark.destructive
def test_creating_a_user_answers_201_with_the_created_user(page, shot, disposable_user):
    """Scenario: Creating a user answers 201 with the created user

    The account is deleted in the fixture's teardown. `is_admin` is never set —
    a second local admin locks every admin out (D-31).
    """
    with shot("create-201", "When an admin POSTs to /api/admin/users"):
        page.goto("/dashboard")
        address = f"e2e-{uuid.uuid4().hex[:12]}@flowinqa.com"
        result = api.full(
            disposable_user.admin_page,
            "POST",
            "/api/admin/users",
            {
                "email": address,
                "password": accounts.PASSWORD,
                "tier": "basic",
                "is_admin": False,
            },
        )

    assert result["status"] == 201, f"{result['status']}: {result['body'][:200]}"
    body = json.loads(result["body"])
    for field in ("id", "email", "tier", "is_admin", "created_at"):
        assert field in body, f"the AdminUserResponse has no {field!r}: {sorted(body)}"
    assert body["email"] == address and body["tier"] == "basic"
    assert body["is_admin"] is False
    # Never the password, in any form.
    assert accounts.PASSWORD not in result["body"]

    api.full(disposable_user.admin_page, "DELETE", f"/api/admin/users/{body['id']}")


@pytest.mark.scenario("S-24-13")
@pytest.mark.destructive
def test_deleting_a_user_answers_204_with_no_body(page, shot, disposable_user):
    """Scenario: Deleting a user answers 204 with no body"""
    user = disposable_user(tier="basic")

    with shot("delete-204", "When an admin DELETEs /api/admin/users/{id}"):
        page.goto("/dashboard")
        result = api.full(
            disposable_user.admin_page, "DELETE", f"/api/admin/users/{user['id']}"
        )

    assert result["status"] == 204, f"{result['status']}: {result['body'][:200]}"
    assert result["body"] == "", f"a 204 carried a body: {result['body'][:200]!r}"

    gone = api.full(disposable_user.admin_page, "GET", f"/api/admin/users")
    rows = json.loads(gone["body"])
    rows = rows["users"] if isinstance(rows, dict) else rows
    assert all(row["id"] != user["id"] for row in rows), "the user is still listed"


@pytest.mark.scenario("S-24-14")
@pytest.mark.destructive
def test_role_and_tier_changes_return_the_updated_user(page, shot):
    """Scenario: Role and tier changes return the updated user

    TIER only. A role change would promote a second local admin, which locks
    every admin out of the product — see D-31 and S-19-07. The tier is changed
    on qa-pro and changed back.
    """
    page.goto("/dashboard")
    users = api.json_body(page, "GET", "/api/admin/users")
    rows = users["users"] if isinstance(users, dict) else users
    target = next(u for u in rows if u["email"] == accounts.PRO)
    before = target["tier"]
    other = "enterprise" if before != "enterprise" else "pro"

    try:
        with shot("tier-patched", "When an admin PATCHes a user's tier"):
            result = api.full(
                page, "PATCH", f"/api/admin/users/{target['id']}/tier", {"tier": other}
            )

        assert result["status"] == 200, result["body"][:200]
        body = json.loads(result["body"])
        assert body.get("tier") == other, f"the response does not reflect the change: {body}"
        assert body.get("email") == accounts.PRO
    finally:
        api.full(page, "PATCH", f"/api/admin/users/{target['id']}/tier", {"tier": before})


# ── public asset routes ──────────────────────────────────────────────────────


@pytest.mark.scenario("S-24-15")
def test_template_previews_load_without_a_token(page, shot):
    """Scenario: Template previews load without a token

    Deliberate: a sandboxed iframe must load these without propagating the JWT
    into static requests. Asserting it stops someone "securing" these routes and
    silently breaking every template gallery.
    """
    page.goto("/create/ppt")
    expect(page.locator("button:has(iframe)").first).to_be_visible()
    src = page.locator("button:has(iframe) iframe").first.get_attribute("src")
    assert src, "no template preview is rendered"

    with shot("public-preview", "When I GET a template preview with no token"):
        result = api.anonymous(page, "GET", src)

    assert result["status"] == 200, (
        f"a template preview answered {result['status']} without a token — the "
        "gallery's iframes cannot carry one"
    )


@pytest.mark.scenario("S-24-16")
@pytest.mark.parametrize(
    "attack",
    ["../../../etc/passwd", "%2e%2e%2f%2e%2e%2fetc%2fpasswd", "/etc/passwd", "..%2f..%2fetc%2fpasswd"],
)
def test_the_asset_route_refuses_path_traversal(page, shot, attack):
    """Scenario: The asset route refuses path traversal

    A wildcard `{asset_path:path}` on an UNAUTHENTICATED route is the classic
    traversal shape. The source says the loader confines reads to `assets/`;
    that is a comment, and this is the test.
    """
    page.goto("/dashboard")
    templates = api.json_body(page, "GET", "/api/prototype/templates")
    rows = templates["templates"] if isinstance(templates, dict) else templates
    template_id = rows[0]["id"] if rows else "blank"

    with shot(f"traversal-{abs(hash(attack)) % 10000}", "When I ask for a file outside assets/"):
        result = api.anonymous(
            page, "GET", f"/api/prototype/templates/{template_id}/assets/{attack}"
        )

    assert result["status"] in (400, 403, 404), (
        f"traversal answered {result['status']}: {result['body'][:200]}"
    )
    assert "root:" not in result["body"], "the response contains /etc/passwd"


@pytest.mark.scenario("S-24-17")
def test_a_missing_asset_is_a_404_not_a_500(page, shot):
    """Scenario: A missing asset is a 404, not a 500"""
    page.goto("/dashboard")
    templates = api.json_body(page, "GET", "/api/prototype/templates")
    rows = templates["templates"] if isinstance(templates, dict) else templates
    template_id = rows[0]["id"] if rows else "blank"

    with shot("missing-asset", "When I GET a nonexistent asset for a real template"):
        result = api.anonymous(
            page, "GET", f"/api/prototype/templates/{template_id}/assets/no-such-file.png"
        )

    assert result["status"] == 404, f"answered {result['status']}: {result['body'][:200]}"


# ── handoff ingress ──────────────────────────────────────────────────────────


@pytest.mark.scenario("S-24-18")
@pytest.mark.skip(reason="needs a valid X-Flowin-API-Key; minting one is 22_handoff_and_gates' job")
def test_handoff_creation_is_authenticated_by_api_key_not_by_jwt(page, shot):
    """Scenario: Handoff creation is authenticated by API key, not by JWT"""


@pytest.mark.scenario("S-24-19")
def test_handoff_creation_without_a_valid_key_is_refused(page, shot):
    """Scenario: Handoff creation without a valid key is refused

    This endpoint mints a URL that grants access to a run, it is reachable from
    the public internet, and that header is its only guard.
    """
    with shot("handoff-unkeyed", "When I POST /api/handoff/receive with no key"):
        page.goto("/dashboard")
        results = {
            label: api.anonymous(page, "POST", "/api/handoff/receive", header)
            for label, header in (("none", None), ("wrong", "Bearer not-a-key"))
        }

    for label, result in results.items():
        assert result["status"] in (401, 403, 422), (
            f"an unkeyed handoff ({label}) answered {result['status']}: "
            f"{result['body'][:200]}"
        )
        assert "http" not in result["body"].lower() or "url" not in result["body"].lower(), (
            "a handoff URL was returned to an unauthenticated caller"
        )


@pytest.mark.scenario("S-24-20")
@pytest.mark.skip(reason="needs a valid X-Flowin-API-Key to reach the PAT branch at all")
def test_a_github_pat_is_not_required_to_create_a_handoff(page, shot):
    """Scenario: A GitHub PAT is not required to create a handoff"""


# ── ownership ────────────────────────────────────────────────────────────────


@pytest.mark.scenario("S-24-21")
@pytest.mark.role("basic")
def test_a_run_is_readable_only_by_its_owner(page, shot, page_as):
    """Scenario: A run is readable only by its owner

    Authentication is not authorization. All 26 run endpoints are
    user-authenticated, and FIX-309 records a case where the ownership check ran
    AFTER a file read.
    """
    run_id = my_run_id(page_as("admin"))

    with shot("foreign-run", "When I GET another user's run with my own token"):
        page.goto("/dashboard")
        result = api.request(page, "GET", f"/api/runs/{run_id}")

    assert result["status"] in (401, 403, 404), (
        f"a foreign run answered {result['status']}: {result['body'][:200]}"
    )


@pytest.mark.scenario("S-24-22")
@pytest.mark.role("basic")
def test_a_runs_files_cannot_be_fetched_across_an_ownership_boundary(page, shot, page_as):
    """Scenario: A run's files cannot be fetched across an ownership boundary"""
    run_id = my_run_id(page_as("admin"))

    with shot("foreign-run-files", "When I request its files with my own token"):
        page.goto("/dashboard")
        results = {
            path: api.request(page, "GET", f"/api/runs/{run_id}{path}")
            for path in ("/artifacts", "/sandbox/file?path=output.md")
        }

    for path, result in results.items():
        assert result["status"] in (401, 403, 404), (
            f"{path} answered {result['status']}: {result['body'][:200]}"
        )


# ── the run sandbox ──────────────────────────────────────────────────────────


@pytest.mark.scenario("S-24-23")
def test_the_listing_describes_the_whole_workspace(page, shot):
    """Scenario: The listing describes the whole workspace

    `kind` is computed ONCE here so the viewer never re-derives it from the
    extension, and `deliverable` comes from the same predicate the deliverable
    walk uses — which is why the frontend does not have to know that PLANNER.md
    is not one.
    """
    run_id = my_run_id(page)

    with shot("sandbox-listing", 'When I GET "/api/runs/{id}/sandbox"'):
        body = sandbox_of(page, run_id)

    for key in ("run_id", "expired", "truncated", "files"):
        assert key in body, f"the listing has no {key!r}: {sorted(body)}"
    if not body["files"]:
        pytest.skip("this run's workspace holds no files to describe")

    for entry in body["files"]:
        for key in ("path", "size", "kind", "text", "deliverable"):
            assert key in entry, f"a file entry has no {key!r}: {entry}"
        assert entry["kind"] in ("text", "image", "pdf", "binary"), entry["kind"]


@pytest.mark.scenario("S-24-24")
def test_an_expired_workspace_is_stated_not_inferred(page, shot):
    """Scenario: An expired workspace is stated, not inferred

    A swept run and a run that wrote nothing both return an empty list. Only the
    flag separates them, and the UI renders different copy for each — so the
    flag has to be present whether or not this particular run is swept.
    """
    run_id = my_run_id(page)

    with shot("sandbox-expiry", "When I read the workspace listing"):
        body = sandbox_of(page, run_id)

    assert isinstance(body.get("expired"), bool), (
        f"`expired` is {body.get('expired')!r}, so an empty workspace cannot be "
        "told apart from a swept one"
    )
    if body["expired"]:
        assert body["files"] == [], "an expired workspace still listed files"
    else:
        pytest.skip("no TTL-swept run is available; the flag's shape is asserted above")


@pytest.mark.scenario("S-24-25")
def test_the_reserved_subtrees_are_never_listed(page, shot):
    """Scenario: The reserved subtrees are never listed

    The listing is the complete description of what `/sandbox/file` will serve.
    """
    run_id = my_run_id(page)

    with shot("reserved-subtrees", "When I read the workspace listing"):
        body = sandbox_of(page, run_id)

    leaked = [f["path"] for f in body["files"] if f["path"].startswith((".uploads/", ".logs/"))]
    assert not leaked, f"reserved subtrees appear in the listing: {leaked}"


def _pick(files, predicate):
    return next((f["path"] for f in files if predicate(f["path"])), None)


@pytest.mark.scenario("S-24-26")
def test_an_html_workspace_file_is_never_served_inline(page, shot):
    """Scenario: An HTML workspace file is never served inline

    THE assertion on this endpoint. Sandbox files are agent-authored content;
    serving one inline from the API origin with an executable content type is
    stored XSS with the caller's session in scope.
    """
    run_id = my_run_id(page)
    files = sandbox_of(page, run_id)["files"]
    target = _pick(files, lambda p: p.endswith((".html", ".htm")))
    if not target:
        pytest.skip("this workspace holds no HTML file")

    with shot("html-not-inline", "When I GET an HTML workspace file"):
        result = api.full(page, "GET", f"/api/runs/{run_id}/sandbox/file?path={target}")

    # Only `Content-Type` is readable here. The response carries
    # `Content-Disposition: attachment` and `X-Content-Type-Options: nosniff` on
    # the wire — confirmed with curl — but the backend sets no
    # `Access-Control-Expose-Headers`, so neither this test nor the product's own
    # JavaScript can see them (D-35). The content type alone is what stops the
    # browser rendering the file, and it is what this asserts.
    headers = result["headers"]
    assert headers.get("content-type", "").startswith("application/octet-stream"), (
        f"an HTML workspace file came back as {headers.get('content-type')!r} — "
        "anything renderable here is stored XSS with the caller's session in scope"
    )


@pytest.mark.scenario("S-24-27")
@pytest.mark.parametrize("extension", [".md", ".json", ".log"])
def test_text_extensions_come_back_inline_as_plain_text(page, shot, extension):
    """Scenario: Text extensions come back inline as plain text"""
    run_id = my_run_id(page)
    files = sandbox_of(page, run_id)["files"]
    target = _pick(files, lambda p: p.endswith(extension))
    if not target:
        pytest.skip(f"this workspace holds no {extension} file")

    with shot(f"inline{extension.replace('.', '-')}", f"When I GET a {extension} file"):
        result = api.full(page, "GET", f"/api/runs/{run_id}/sandbox/file?path={target}")

    # `Content-Disposition: inline` is on the wire but not CORS-exposed — see
    # S-24-26 and D-35.
    headers = result["headers"]
    assert headers.get("content-type", "").startswith("text/plain"), headers


@pytest.mark.scenario("S-24-28")
@pytest.mark.parametrize(
    "path",
    ["../../../etc/passwd", "/etc/passwd", "..%2f..%2fetc%2fpasswd", ".uploads/manifest.json", ".logs/run.log"],
)
def test_the_path_parameter_refuses_to_leave_the_run_directory(page, shot, path):
    """Scenario: The path parameter refuses to leave the run directory

    `path_for` resolves inside the run dir and raises on any escape, so `..` and
    an absolute path both land as 400. The reserved prefixes are refused
    separately as 404 — they are not part of the workspace view.
    """
    run_id = my_run_id(page)

    with shot(f"escape-{abs(hash(path)) % 10000}", "When I ask for a path outside the run"):
        result = api.full(page, "GET", f"/api/runs/{run_id}/sandbox/file?path={path}")

    assert result["status"] in (400, 403, 404), (
        f"{path!r} answered {result['status']}: {result['body'][:200]}"
    )
    assert "root:" not in result["body"], "the response contains /etc/passwd"


@pytest.mark.scenario("S-24-29")
@pytest.mark.skip(reason="needs a symlink planted in a run workspace; no fixture writes one")
def test_a_symlink_cannot_be_used_to_read_outside_the_run_directory(page, shot):
    """Scenario: A symlink cannot be used to read outside the run directory"""


@pytest.mark.scenario("S-24-30")
@pytest.mark.skip(reason="needs a workspace file larger than 8 MB; no seeded run has one")
def test_a_file_too_large_to_preview_is_refused_not_streamed(page, shot):
    """Scenario: A file too large to preview is refused, not streamed"""


@pytest.mark.scenario("S-24-31")
def test_the_zip_holds_exactly_what_the_listing_showed(page, shot):
    """Scenario: The zip holds exactly what the listing showed"""
    run_id = my_run_id(page)
    listed = {f["path"] for f in sandbox_of(page, run_id)["files"]}
    if not listed:
        pytest.skip("this workspace holds no files to archive")

    with shot("sandbox-zip", 'When I GET "/api/runs/{id}/sandbox/zip"'):
        # Only the headers are asserted here: the body is a binary archive, and
        # pulling it through `evaluate` as text would corrupt it.
        result = api.full(page, "GET", f"/api/runs/{run_id}/sandbox/zip", limit=0)

    # `Content-Disposition: attachment; filename="workspace-<id>.zip"` is on the
    # wire but not CORS-exposed — see S-24-26 and D-35.
    headers = result["headers"]
    assert result["status"] == 200, result["status"]
    assert headers.get("content-type", "").startswith("application/zip"), headers


@pytest.mark.scenario("S-24-32")
@pytest.mark.skip(reason="needs a workspace over 64 MB uncompressed; no seeded run has one")
def test_an_oversized_workspace_is_refused_rather_than_archived(page, shot):
    """Scenario: An oversized workspace is refused rather than archived"""


@pytest.mark.scenario("S-24-33")
@pytest.mark.skip(reason="needs a TTL-swept workspace; every seeded run still has one")
def test_an_expired_workspace_has_nothing_to_serve(page, shot):
    """Scenario: An expired workspace has nothing to serve"""


@pytest.mark.scenario("S-24-34")
@pytest.mark.role("basic")
@pytest.mark.parametrize("endpoint", ["", "/file?path=a.md", "/zip"])
def test_the_sandbox_is_unreachable_across_an_ownership_boundary(page, shot, endpoint, page_as):
    """Scenario: The sandbox is unreachable across an ownership boundary

    404 for BOTH cross-owner and unknown, deliberately: a 403 would confirm the
    id exists, which is the IDOR this is guarding.
    """
    run_id = my_run_id(page_as("admin"))

    with shot(f"foreign-sandbox{endpoint.replace('/', '-').replace('?', '-')}", "When I GET it"):
        page.goto("/dashboard")
        result = api.full(page, "GET", f"/api/runs/{run_id}/sandbox{endpoint}")

    assert result["status"] == 404, (
        f"a foreign sandbox answered {result['status']} — anything but 404 "
        f"confirms the run id exists: {result['body'][:200]}"
    )
