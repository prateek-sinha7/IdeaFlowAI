"""ISS-319 — concurrent PUT /api/settings/preferences loses a write and lies
in the response body (BUG-20260828-094120-settings-ai-model-r2).

``update_preferences`` (``app/api/settings.py``) sets ``user.preferred_model``,
``db.commit()``s, then ``db.refresh(user)`` and builds the response from that
refreshed object. Two concurrent requests each get their own ``Session`` on the
same ``users`` row; if request B's commit lands between request A's own
``commit()`` and ``refresh()``, A's response reports B's value instead of the
value A itself sent — a silent lost update PLUS a false-success response body.

This test drives the real ``update_preferences`` handler function directly
(not via TestClient/threads) with two separate SQLAlchemy sessions bound to
the same in-memory SQLite connection (``StaticPool`` — the
``test_user_workflows.py`` harness), so the exact interleaving the card
describes can be staged deterministically instead of relying on thread timing:

    A: set preferred_model=opus, commit()
    B: set preferred_model=sonnet, commit(), refresh(), build response  -> "sonnet" (correct)
    A: refresh(), build response                                        -> should be "opus", is "sonnet"

Correct behaviour: A's response must report "opus" — the value A itself sent —
regardless of what B committed in between.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.settings import UserPreferencesUpdateRequest, update_preferences
from app.models.database import Base
from app.models.user import User

_MODEL_A = "eu.anthropic.claude-opus-4-6-v1"
_MODEL_B = "eu.anthropic.claude-sonnet-4-5-20250929-v1:0"


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
    s.commit()
    uid = user.id
    s.close()
    return uid


@pytest.mark.issue("ISS-319")
def test_losing_requests_response_reports_its_own_value(engine, seeded_user_id):
    """A's 200 response must report A's own requested model, not B's.

    Calls the real ``update_preferences`` handler for BOTH requests. Request
    B's entire call (commit + refresh + response) is spliced in to run inside
    request A's own ``db.refresh(user)`` call — by monkeypatching session A's
    ``refresh`` to fire B first — so the interleaving is exactly the window
    the card names (B's commit lands between A's commit and A's refresh),
    staged deterministically instead of relying on thread scheduling.
    """
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    session_a = Session()
    session_b = Session()

    user_a = session_a.query(User).filter(User.id == seeded_user_id).one()
    user_b = session_b.query(User).filter(User.id == seeded_user_id).one()

    real_refresh = session_a.refresh
    response_b_holder: dict = {}

    def refresh_after_b_commits(*args, **kwargs):
        response_b_holder["response"] = update_preferences(
            UserPreferencesUpdateRequest(preferred_model=_MODEL_B),
            user=user_b,
            db=session_b,
        )
        return real_refresh(*args, **kwargs)

    session_a.refresh = refresh_after_b_commits

    # Request A: the real handler, end to end. Its own db.refresh(user) call
    # is the point where B's full request runs (see monkeypatch above).
    response_a = update_preferences(
        UserPreferencesUpdateRequest(preferred_model=_MODEL_A),
        user=user_a,
        db=session_a,
    )

    session_a.close()
    session_b.close()

    assert response_b_holder["response"].preferred_model == _MODEL_B  # B's own response is correct

    assert response_a.preferred_model == _MODEL_A, (
        f"request A asked for {_MODEL_A!r} but its own response reported "
        f"{response_a.preferred_model!r} (request B's value) — lost update + "
        "false-success response body"
    )
