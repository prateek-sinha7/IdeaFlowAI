"""ISS-470 — upsert_github_pat shares update_preferences' commit-then-refresh
response race (sibling of ISS-319).

``upsert_github_pat`` (``app/api/settings.py``) validates the PAT against the
GitHub API, sets ``row.github_username``/``row.scopes``, ``db.commit()``s,
then ``db.refresh(row)`` and builds the response from that refreshed row.
Two concurrent PUTs for the same user share one ``UserGithubCredential`` row
(unique on ``user_id``); if request B's commit lands between request A's own
``commit()`` and ``refresh()``, A's response reports B's github_username /
scopes instead of the value A itself just saved.

Mirrors ``test_settings_preferences_race.py`` (ISS-319): drives the real
``upsert_github_pat`` handler for both requests against two SQLAlchemy
sessions bound to the same in-memory SQLite connection (StaticPool), with
B's full request spliced into session A's ``db.refresh`` call so the exact
interleaving the card describes is staged deterministically. Because the
handler is async (it awaits the GitHub validation call), B's call is driven
to completion on a separate thread's event loop while A's own event loop is
paused inside the (synchronous) ``refresh`` monkeypatch.

Correct behaviour: A's response must report the github_username/scopes for
the PAT A itself submitted, regardless of what B committed in between.
"""

from __future__ import annotations

import asyncio
import threading

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.settings import GithubPATRequest, upsert_github_pat
from app.models.database import Base
from app.models.handoff import UserGithubCredential
from app.models.user import User

_PAT_A = "ghp_AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
_PAT_B = "ghp_BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB"


class _FakeGithubResponse:
    def __init__(self, login: str, scopes: str):
        self.status_code = 200
        self._login = login
        self.headers = {"x-oauth-scopes": scopes}

    def json(self):
        return {"login": self._login}


class _FakeAsyncClient:
    """Stands in for httpx.AsyncClient so no real GitHub call is made."""

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, headers=None, **kwargs):
        pat = headers["Authorization"].removeprefix("Bearer ")
        if pat == _PAT_A:
            return _FakeGithubResponse("user-a-login", "repo,read:org")
        return _FakeGithubResponse("user-b-login", "repo")


@pytest.fixture(autouse=True)
def _fake_github(monkeypatch):
    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)


@pytest.fixture
def engine():
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=eng)
    yield eng
    Base.metadata.drop_all(bind=eng)


@pytest.fixture
def seeded_user_id(engine):
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    s = Session()
    user = User(id="user-race", email="race@example.com", tier="enterprise")
    s.add(user)
    s.add(
        UserGithubCredential(
            user_id=user.id,
            encrypted_pat="seed-ciphertext",
            github_username="old-login",
            scopes="repo",
        )
    )
    s.commit()
    uid = user.id
    s.close()
    return uid


@pytest.mark.issue("ISS-470")
@pytest.mark.xfail(reason="ISS-470 unfixed", strict=True)
def test_losing_requests_response_reports_its_own_value(engine, seeded_user_id):
    """A's 200 response must report A's own submitted PAT's github data, not B's.

    Calls the real ``upsert_github_pat`` handler for BOTH requests. Request
    B's entire call (GitHub validation + commit + refresh + response) is
    spliced in to run inside request A's own ``db.refresh(row)`` call — by
    monkeypatching session A's ``refresh`` to drive B's coroutine to
    completion on a separate thread first — so the interleaving is exactly
    the window the card names (B's commit lands between A's commit and A's
    refresh).
    """
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    session_a = Session()
    session_b = Session()

    user_a = session_a.query(User).filter(User.id == seeded_user_id).one()
    user_b = session_b.query(User).filter(User.id == seeded_user_id).one()

    real_refresh = session_a.refresh
    response_b_holder: dict = {}

    def refresh_after_b_commits(*args, **kwargs):
        def run_b():
            response_b_holder["response"] = asyncio.run(
                upsert_github_pat(
                    GithubPATRequest(pat=_PAT_B), user=user_b, db=session_b
                )
            )

        t = threading.Thread(target=run_b)
        t.start()
        t.join()
        return real_refresh(*args, **kwargs)

    session_a.refresh = refresh_after_b_commits

    # Request A: the real handler, end to end. Its own db.refresh(row) call
    # is the point where B's full request runs (see monkeypatch above).
    response_a = asyncio.run(
        upsert_github_pat(GithubPATRequest(pat=_PAT_A), user=user_a, db=session_a)
    )

    session_a.close()
    session_b.close()

    assert response_b_holder["response"].github_username == "user-b-login"  # B's own response is correct

    assert response_a.github_username == "user-a-login", (
        f"request A submitted a PAT that validates as 'user-a-login' but its "
        f"own response reported {response_a.github_username!r} (request B's "
        "value) — lost update + false-success response body"
    )
