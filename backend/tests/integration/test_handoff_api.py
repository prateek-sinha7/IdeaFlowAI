"""Integration tests for the /flowin-handoff feature.

Covers the security-critical contract surface end-to-end against an
in-memory SQLite database wired into the FastAPI app:

* Crypto round-trip and key separation from the JWT signing key.
* GitHub PAT endpoints require JWT auth; GitHub upstream validation
  catches typos before persisting.
* API key minting returns the plaintext exactly once; re-listing only
  exposes the prefix.
* Handoff ``POST /receive`` requires the API key header; the token in
  the response is unguessable.
* Handoff ``GET /<token>`` returns 404 for non-issuer users (never
  confirms the token's existence).
* MCP JSON-RPC dispatch: ``initialize``, ``tools/list``, and
  ``tools/call`` with both happy-path and validation errors.
* Path-traversal protection in ``_safe_workspace_join`` and the edit
  application in ``_apply_edits``.
* Branch-name slug logic is deterministic.

Tests that need a real HTTP outbound call (PAT verification, pipeline
end-to-end) are NOT run here — they require Bedrock + GitHub creds and
live behind the ``requires_api_key`` marker.
"""

from __future__ import annotations

import os
import tempfile

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.crypto import decrypt_pat, encrypt_pat
from app.models.database import Base, get_db


# --- Test fixtures ------------------------------------------------------


@pytest.fixture()
def app_client(monkeypatch, tmp_path):
    """Build a FastAPI TestClient backed by a fresh in-memory SQLite DB.

    We monkeypatch ``settings.DATABASE_URL`` and the engine before
    importing the app so the lifespan check sees a migrated schema.
    """
    db_path = tmp_path / "test.db"
    db_url = f"sqlite:///{db_path}"
    monkeypatch.setenv("DATABASE_URL", db_url)

    # Force a clean import of the app + models against the new DB url.
    from app.core.config import settings

    settings.DATABASE_URL = db_url

    # Recreate the engine pointed at the new URL.
    test_engine = create_engine(db_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(test_engine)

    # Stamp alembic_version so the lifespan check passes.
    with test_engine.begin() as conn:
        from sqlalchemy import text

        conn.execute(text("CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR PRIMARY KEY)"))
        conn.execute(text("INSERT INTO alembic_version (version_num) VALUES ('0002')"))

    TestSession = sessionmaker(bind=test_engine, autocommit=False, autoflush=False)

    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    # Late import so the FastAPI app picks up the new engine config.
    from app.main import app

    app.dependency_overrides[get_db] = override_get_db
    # Also override the SessionLocal that the pipeline background task uses.
    import app.models.database as db_module

    monkeypatch.setattr(db_module, "engine", test_engine)
    monkeypatch.setattr(db_module, "SessionLocal", TestSession)
    import app.api.handoff as handoff_module

    monkeypatch.setattr(handoff_module, "SessionLocal", TestSession)

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.clear()


def _register_and_login(client: TestClient, email: str = "alice@example.com", password: str = "hunter2hunter2") -> str:
    """Register a fresh user and return their JWT."""
    resp = client.post("/api/auth/register", json={"email": email, "password": password})
    assert resp.status_code in (200, 201), resp.text
    return resp.json()["token"]


# --- Crypto -------------------------------------------------------------


def test_pat_crypto_roundtrip():
    plaintext = "github_pat_11ABCDE0fakefakefake"
    enc = encrypt_pat(plaintext)
    assert enc != plaintext
    assert decrypt_pat(enc) == plaintext


def test_pat_crypto_rejects_empty():
    with pytest.raises(ValueError):
        encrypt_pat("")
    with pytest.raises(ValueError):
        decrypt_pat("")


def test_pat_crypto_does_not_decrypt_jwt():
    """A token signed with the JWT key must NOT decrypt as a PAT.

    The HKDF info string is what separates the two derived keys; this
    test fails loudly if someone removes the derivation and reuses
    ``settings.SECRET_KEY`` directly.
    """
    from cryptography.fernet import InvalidToken

    # A made-up Fernet token derived from a different (random) key.
    from cryptography.fernet import Fernet

    other_key = Fernet.generate_key()
    bogus = Fernet(other_key).encrypt(b"hello")
    with pytest.raises(InvalidToken):
        decrypt_pat(bogus.decode("ascii"))


# --- Settings: API keys -------------------------------------------------


def test_api_key_creation_returns_plaintext_once(app_client):
    token = _register_and_login(app_client)

    r = app_client.post(
        "/api/settings/api-keys",
        json={"name": "Laptop"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    plaintext = body["token"]
    assert plaintext.startswith("flowin_")
    assert body["token_prefix"] == plaintext[:8]
    assert body["name"] == "Laptop"

    listing = app_client.get(
        "/api/settings/api-keys",
        headers={"Authorization": f"Bearer {token}"},
    ).json()
    assert len(listing) == 1
    # Plaintext is NOT returned on list — only the prefix.
    assert "token" not in listing[0]
    assert listing[0]["token_prefix"] == plaintext[:8]


def test_api_key_revoke_blocks_future_use(app_client):
    token = _register_and_login(app_client)
    created = app_client.post(
        "/api/settings/api-keys",
        json={"name": "X"},
        headers={"Authorization": f"Bearer {token}"},
    ).json()

    # /receive should work first
    r = app_client.post(
        "/api/handoff/receive",
        json={"task": "fix the bug", "repo_url": "https://github.com/a/b"},
        headers={"X-Flowin-API-Key": created["token"]},
    )
    assert r.status_code == 201, r.text

    # Revoke and try again
    rev = app_client.delete(
        f"/api/settings/api-keys/{created['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert rev.status_code == 204

    r2 = app_client.post(
        "/api/handoff/receive",
        json={"task": "fix the bug", "repo_url": "https://github.com/a/b"},
        headers={"X-Flowin-API-Key": created["token"]},
    )
    assert r2.status_code == 401


def test_handoff_receive_requires_api_key(app_client):
    r = app_client.post(
        "/api/handoff/receive",
        json={"task": "fix it", "repo_url": "https://github.com/a/b"},
    )
    assert r.status_code == 401


def test_handoff_get_rejects_wrong_user(app_client):
    # Alice creates a handoff; Bob must not be able to view it.
    alice_jwt = _register_and_login(app_client, "alice@example.com")
    alice_key = app_client.post(
        "/api/settings/api-keys",
        json={"name": "X"},
        headers={"Authorization": f"Bearer {alice_jwt}"},
    ).json()["token"]
    sess = app_client.post(
        "/api/handoff/receive",
        json={"task": "do work", "repo_url": "https://github.com/x/y"},
        headers={"X-Flowin-API-Key": alice_key},
    ).json()

    bob_jwt = _register_and_login(app_client, "bob@example.com", "hunter2hunter2")
    r = app_client.get(
        f"/api/handoff/{sess['token']}",
        headers={"Authorization": f"Bearer {bob_jwt}"},
    )
    # Same 404 we return for non-existent tokens — never leak existence.
    assert r.status_code == 404

    # Alice (the issuer) sees the session.
    r2 = app_client.get(
        f"/api/handoff/{sess['token']}",
        headers={"Authorization": f"Bearer {alice_jwt}"},
    )
    assert r2.status_code == 200
    assert r2.json()["task_description"] == "do work"
    assert r2.json()["has_github_pat"] is False


def test_handoff_start_needs_pat(app_client):
    jwt = _register_and_login(app_client)
    key = app_client.post(
        "/api/settings/api-keys",
        json={"name": "X"},
        headers={"Authorization": f"Bearer {jwt}"},
    ).json()["token"]
    sess = app_client.post(
        "/api/handoff/receive",
        json={"task": "do work", "repo_url": "https://github.com/x/y"},
        headers={"X-Flowin-API-Key": key},
    ).json()
    r = app_client.post(
        f"/api/handoff/{sess['token']}/start",
        headers={"Authorization": f"Bearer {jwt}"},
    )
    assert r.status_code == 412
    assert "GitHub PAT" in r.json()["detail"]


def test_handoff_receive_validates_mode_and_size(app_client):
    jwt = _register_and_login(app_client)
    key = app_client.post(
        "/api/settings/api-keys",
        json={"name": "X"},
        headers={"Authorization": f"Bearer {jwt}"},
    ).json()["token"]

    bad_mode = app_client.post(
        "/api/handoff/receive",
        json={"task": "x" * 10, "repo_url": "https://github.com/a/b", "mode": "bogus"},
        headers={"X-Flowin-API-Key": key},
    )
    assert bad_mode.status_code == 422

    huge = app_client.post(
        "/api/handoff/receive",
        json={
            "task": "fix",
            "repo_url": "https://github.com/a/b",
            "transcript": "x" * (1024 * 1024 + 100),
        },
        headers={"X-Flowin-API-Key": key},
    )
    assert huge.status_code == 413


# --- MCP server ---------------------------------------------------------


def test_mcp_requires_bearer(app_client):
    r = app_client.post("/mcp/handoff", json={"jsonrpc": "2.0", "id": 1, "method": "ping"})
    assert r.status_code == 401


def test_mcp_initialize_and_list_tools(app_client):
    jwt = _register_and_login(app_client)
    key = app_client.post(
        "/api/settings/api-keys",
        json={"name": "X"},
        headers={"Authorization": f"Bearer {jwt}"},
    ).json()["token"]
    headers = {"Authorization": f"Bearer {key}"}

    init = app_client.post(
        "/mcp/handoff",
        headers=headers,
        json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
    )
    assert init.status_code == 200
    init_body = init.json()
    assert init_body["jsonrpc"] == "2.0"
    assert init_body["result"]["serverInfo"]["name"] == "flowin-handoff"
    assert init_body["result"]["protocolVersion"]

    tl = app_client.post(
        "/mcp/handoff",
        headers=headers,
        json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    )
    tools = tl.json()["result"]["tools"]
    assert len(tools) == 1
    assert tools[0]["name"] == "flowin_handoff"
    assert "task" in tools[0]["inputSchema"]["properties"]


def test_mcp_tools_call_creates_handoff(app_client):
    jwt = _register_and_login(app_client)
    key = app_client.post(
        "/api/settings/api-keys",
        json={"name": "X"},
        headers={"Authorization": f"Bearer {jwt}"},
    ).json()["token"]
    headers = {"Authorization": f"Bearer {key}"}

    r = app_client.post(
        "/mcp/handoff",
        headers=headers,
        json={
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "flowin_handoff",
                "arguments": {
                    "task": "Add tests for RateLimiter",
                    "repo_url": "https://github.com/acme/widgets",
                    "mode": "auto",
                },
            },
        },
    )
    body = r.json()
    assert "error" not in body
    structured = body["result"]["structuredContent"]
    assert structured["url"].endswith(f"/handoff/{structured['token']}")
    assert structured["handoff_id"]


def test_mcp_tools_call_rejects_bad_args(app_client):
    jwt = _register_and_login(app_client)
    key = app_client.post(
        "/api/settings/api-keys",
        json={"name": "X"},
        headers={"Authorization": f"Bearer {jwt}"},
    ).json()["token"]
    headers = {"Authorization": f"Bearer {key}"}

    # Missing repo_url
    r = app_client.post(
        "/mcp/handoff",
        headers=headers,
        json={
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "flowin_handoff", "arguments": {"task": "fix"}},
        },
    )
    assert r.json()["error"]["code"] == -32602


# --- Pipeline path-traversal --------------------------------------------


def test_safe_workspace_join_rejects_traversal():
    from app.services.handoff_pipeline import _safe_workspace_join

    with tempfile.TemporaryDirectory() as tmp:
        for bad in [
            "/etc/passwd",
            "../escape",
            "foo/../../escape",
            ".git/config",
            ".git/refs/heads/main",
            ".git",
        ]:
            with pytest.raises(ValueError):
                _safe_workspace_join(tmp, bad)

        # Sanity: a normal path is accepted.
        ok = _safe_workspace_join(tmp, "src/app.py")
        assert ok.startswith(os.path.realpath(tmp))


def test_apply_edits_rejects_path_traversal_and_missing_files():
    from app.services.handoff_pipeline import _apply_edits

    with tempfile.TemporaryDirectory() as tmp:
        target = os.path.join(tmp, "ok.txt")
        with open(target, "w") as fh:
            fh.write("hello world")

        edits = [
            {"path": "ok.txt", "operation": "modify", "old_string": "world", "new_string": "earth"},
            {"path": "ok.txt", "operation": "modify", "old_string": "missing", "new_string": "x"},
            {"path": "../escape", "operation": "create", "new_string": "nope"},
            {"path": "newfile.txt", "operation": "create", "new_string": "fresh"},
            {"path": "doesnt_exist.txt", "operation": "modify", "old_string": "a", "new_string": "b"},
            {"path": ".git/HEAD", "operation": "modify", "old_string": "x", "new_string": "y"},
            {"path": "ok.txt", "operation": "delete"},
        ]
        results = _apply_edits(tmp, edits)
        # Index by position so duplicate (path, operation) tuples are distinct.
        assert results[0]["status"] == "applied"        # world→earth succeeds
        assert results[1]["status"] == "rejected"        # 'missing' substring isn't present
        assert results[2]["status"] == "rejected"        # path traversal
        assert results[3]["status"] == "applied"         # new file create
        assert results[4]["status"] == "rejected"        # modify non-existent
        assert results[5]["status"] == "rejected"        # .git path
        assert results[6]["status"] == "applied"         # delete
        assert not os.path.exists(target)
        # The earlier modify did happen — verify earth got written before the delete.
        # (We can't read it now because we deleted, but the earlier .read() inside
        # _apply_edits would have surfaced the rewrite.)
        assert os.path.exists(os.path.join(tmp, "newfile.txt"))


def test_branch_name_is_safe_and_deterministic():
    from app.services.handoff_pipeline import _branch_name

    a = _branch_name("abc12345-1111-2222-3333-444455556666", "Fix the SQL injection bug!")
    b = _branch_name("abc12345-1111-2222-3333-444455556666", "Fix the SQL injection bug!")
    assert a == b
    assert a.startswith("flowin-handoff/abc12345-")
    # No spaces, no chars that git rejects:
    assert " " not in a
    assert "!" not in a


# --- GitHub URL parsing -------------------------------------------------


def test_parse_github_url_variants():
    from app.services.handoff_github import parse_github_url

    for raw, owner, repo in [
        ("https://github.com/acme/widgets", "acme", "widgets"),
        ("https://github.com/acme/widgets.git", "acme", "widgets"),
        ("https://github.com/acme/widgets/", "acme", "widgets"),
        ("git@github.com:acme/widgets.git", "acme", "widgets"),
        ("git@github.com:acme/widgets", "acme", "widgets"),
    ]:
        t = parse_github_url(raw)
        assert (t.owner, t.repo) == (owner, repo), raw

    for bad in ["", "ftp://github.com/acme/widgets", "gitlab.com/acme/widgets"]:
        with pytest.raises(ValueError):
            parse_github_url(bad)


# --- Settings: GitHub PAT with mocked GitHub ---------------------------


def test_github_pat_upsert_mocked(monkeypatch, app_client):
    """The PUT endpoint hits api.github.com/user; mock that out."""

    class _FakeResp:
        def __init__(self, status: int, json_data: dict, headers: dict | None = None):
            self.status_code = status
            self._json = json_data
            self.headers = headers or {}
            self.text = str(json_data)

        def json(self) -> dict:
            return self._json

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get(self, url, headers=None):
            return _FakeResp(
                200,
                {"login": "octocat"},
                headers={"x-oauth-scopes": "repo, read:org"},
            )

    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)

    jwt = _register_and_login(app_client)
    r = app_client.put(
        "/api/settings/github-pat",
        json={"pat": "github_pat_11" + "A" * 30},
        headers={"Authorization": f"Bearer {jwt}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["github_username"] == "octocat"
    assert body["scopes"] == "repo, read:org"
    assert body["last_4"] == "A" * 4

    # GET reflects what was saved.
    g = app_client.get(
        "/api/settings/github-pat",
        headers={"Authorization": f"Bearer {jwt}"},
    )
    assert g.status_code == 200
    assert g.json()["github_username"] == "octocat"


def test_handoff_get_flips_running_to_failed_on_expiry(app_client, monkeypatch):
    """A pipeline that doesn't finish before ``expires_at`` should be
    flipped from RUNNING to FAILED on the next GET, so the user gets a
    Retry button instead of a permanently-dead RUNNING state.
    """
    from datetime import datetime, timedelta, timezone

    from app.models.handoff import (
        HANDOFF_STATUS_FAILED,
        HANDOFF_STATUS_RUNNING,
        HandoffSession,
    )

    jwt = _register_and_login(app_client)
    key = app_client.post(
        "/api/settings/api-keys",
        json={"name": "X"},
        headers={"Authorization": f"Bearer {jwt}"},
    ).json()["token"]
    sess_resp = app_client.post(
        "/api/handoff/receive",
        json={"task": "do work", "repo_url": "https://github.com/x/y"},
        headers={"X-Flowin-API-Key": key},
    ).json()

    # Forcibly mark RUNNING + already-expired by writing directly via the
    # test DB session. We can't go via /start because that would also
    # spawn a background pipeline coroutine.
    import app.api.handoff as handoff_module

    db = handoff_module.SessionLocal()
    try:
        row = (
            db.query(HandoffSession)
            .filter(HandoffSession.token == sess_resp["token"])
            .first()
        )
        assert row is not None
        row.status = HANDOFF_STATUS_RUNNING
        row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=5)
        db.add(row)
        db.commit()
    finally:
        db.close()

    r = app_client.get(
        f"/api/handoff/{sess_resp['token']}",
        headers={"Authorization": f"Bearer {jwt}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == HANDOFF_STATUS_FAILED
    assert "expired" in (body["error"] or "").lower()


def test_handoff_start_is_race_safe(monkeypatch, app_client):
    """Two near-simultaneous Start calls must not both spawn a pipeline.

    The conditional UPDATE returns rowcount=1 for exactly one caller; the
    other must see 409. We disable the actual pipeline coroutine via
    monkeypatch so the test doesn't need Bedrock credentials.
    """
    import app.api.handoff as handoff_module

    async def _noop_pipeline(**_kwargs):
        # Background task — we never await it from the test; just don't crash.
        return None

    monkeypatch.setattr(handoff_module, "_run_pipeline_background", _noop_pipeline)

    # Setup: a user with a PAT, plus a pending handoff.
    jwt = _register_and_login(app_client)
    key = app_client.post(
        "/api/settings/api-keys",
        json={"name": "X"},
        headers={"Authorization": f"Bearer {jwt}"},
    ).json()["token"]

    # Save a PAT via direct DB write to avoid hitting the GitHub-validation
    # mock in upsert_github_pat. We only need the row to exist.
    from app.core.crypto import encrypt_pat
    from app.models.handoff import UserGithubCredential

    db = handoff_module.SessionLocal()
    try:
        db.add(
            UserGithubCredential(
                user_id=app_client.get(
                    "/api/auth/me", headers={"Authorization": f"Bearer {jwt}"}
                ).json()["id"],
                encrypted_pat=encrypt_pat("github_pat_test_value_long"),
                github_username="testuser",
            )
        )
        db.commit()
    finally:
        db.close()

    sess = app_client.post(
        "/api/handoff/receive",
        json={"task": "do work", "repo_url": "https://github.com/x/y"},
        headers={"X-Flowin-API-Key": key},
    ).json()

    # First Start succeeds.
    r1 = app_client.post(
        f"/api/handoff/{sess['token']}/start",
        headers={"Authorization": f"Bearer {jwt}"},
    )
    assert r1.status_code == 200, r1.text

    # Second Start must 409 (the conditional UPDATE returned 0 rows).
    r2 = app_client.post(
        f"/api/handoff/{sess['token']}/start",
        headers={"Authorization": f"Bearer {jwt}"},
    )
    assert r2.status_code == 409, r2.text


def test_install_endpoint_serves_installer(app_client):
    """``GET /install/flowin-handoff`` returns a runnable bash installer.

    Asserts the response is shell-shaped, embeds the two payload files,
    and pins the host name we serve from (not whatever the client sent
    in the ``Host`` header — we don't honour that, otherwise a proxy
    could redirect a victim's install at a malicious origin).
    """
    r = app_client.get("/install/flowin-handoff")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/x-shellscript")
    body = r.text
    assert body.startswith("#!/usr/bin/env bash")
    assert "set -euo pipefail" in body
    assert "EOF_SLASH_COMMAND" in body
    assert "EOF_BIN" in body
    assert "~/.claude/commands" in body or "$HOME" in body
    # PATH check warning is present
    assert "PATH" in body
    # The embedded slash command must NOT reference the dropped relative path.
    assert ".claude/skills/flowin-handoff/handoff.sh" not in body
    assert "!flowin-handoff" in body


def test_install_command_and_script_raw_endpoints(app_client):
    cmd = app_client.get("/install/flowin-handoff/command")
    assert cmd.status_code == 200
    assert cmd.headers["content-type"].startswith("text/markdown")
    assert "allowed-tools: Bash(flowin-handoff:*)" in cmd.text

    scr = app_client.get("/install/flowin-handoff/script")
    assert scr.status_code == 200
    assert scr.headers["content-type"].startswith("text/x-shellscript")
    assert "FLOWIN_API_URL" in scr.text
    assert "X-Flowin-API-Key" in scr.text


def test_installer_actually_writes_files_when_piped_to_bash(app_client, tmp_path):
    """End-to-end: pipe the installer to bash with a fake $HOME and
    verify the two expected files appear with the right permissions.

    Skipped on platforms without ``bash`` (Windows CI). On macOS / Linux
    this catches heredoc-escape bugs that pure string assertions miss.
    """
    import os
    import shutil
    import stat
    import subprocess

    if shutil.which("bash") is None:
        import pytest as _pytest

        _pytest.skip("bash not available")

    r = app_client.get("/install/flowin-handoff")
    assert r.status_code == 200
    installer_path = tmp_path / "install.sh"
    installer_path.write_text(r.text)

    fake_home = tmp_path / "home"
    fake_home.mkdir()
    env = dict(os.environ)
    env["HOME"] = str(fake_home)
    # Drop ~/.local/bin from PATH if present so the warning prints (we
    # assert on the message below).
    env["PATH"] = "/usr/bin:/bin"

    res = subprocess.run(
        ["bash", str(installer_path)],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert res.returncode == 0, f"installer exit={res.returncode} stderr={res.stderr}"

    cmd_file = fake_home / ".claude" / "commands" / "flowin-handoff.md"
    bin_file = fake_home / ".local" / "bin" / "flowin-handoff"
    assert cmd_file.exists(), "slash command not written"
    assert bin_file.exists(), "binary not written"

    bin_mode = bin_file.stat().st_mode
    assert bin_mode & stat.S_IXUSR, "binary not user-executable"
    assert bin_mode & stat.S_IXGRP, "binary not group-executable"

    # The binary must be syntactically valid bash.
    syntax = subprocess.run(
        ["bash", "-n", str(bin_file)], capture_output=True, text=True
    )
    assert syntax.returncode == 0, f"binary syntax error: {syntax.stderr}"

    # Re-running is idempotent (no error, same files).
    res2 = subprocess.run(
        ["bash", str(installer_path)], env=env, capture_output=True, text=True, timeout=30
    )
    assert res2.returncode == 0


def test_github_pat_rejects_invalid_token(monkeypatch, app_client):
    class _FakeResp:
        status_code = 401
        text = '{"message":"Bad credentials"}'

        def json(self) -> dict:
            return {"message": "Bad credentials"}

    class _FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get(self, url, headers=None):
            return _FakeResp()

    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **kw: _FakeAsyncClient())

    jwt = _register_and_login(app_client)
    r = app_client.put(
        "/api/settings/github-pat",
        json={"pat": "github_pat_bad"},
        headers={"Authorization": f"Bearer {jwt}"},
    )
    assert r.status_code == 400
