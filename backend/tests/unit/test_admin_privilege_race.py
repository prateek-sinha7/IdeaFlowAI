"""ISS-471 — admin.py's update_user_tier/update_user_role share the same
commit-then-refresh response race as ISS-319 (BUG-096).

Both handlers (``app/api/admin.py``) set a privilege field on ``user``,
``db.commit()``, then ``db.refresh(user)`` and build the response via
``_to_response(user, db)``, which reads ``user.tier`` / ``user.is_admin``
straight off the just-refreshed object. Two concurrent admin requests each get
their own ``Session`` on the same ``users`` row; if request B's commit lands
between request A's own ``commit()`` and ``refresh()``, A's response reports
B's value instead of the value A itself sent — here that value is a privilege
field (tier / admin flag), not a mere preference.

Same staging technique as ``test_settings_preferences_race.py``: two SQLAlchemy
sessions on one in-memory SQLite connection (``StaticPool``), with request B's
whole handler call spliced into request A's own ``db.refresh`` via a
monkeypatch, so the exact interleaving is deterministic rather than relying on
thread timing.

Correct behaviour: A's response must report the value A itself set, regardless
of what B committed in between.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.admin import (
    UpdateRoleRequest,
    UpdateTierRequest,
    update_user_role,
    update_user_tier,
)
from app.models.database import Base
from app.models.user import User


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
def seeded_ids(engine):
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    s = Session()
    admin = User(id="admin-1", email="admin@example.com", tier="enterprise", is_admin=True)
    target = User(id="user-target", email="target@example.com", tier="basic", is_admin=False)
    s.add_all([admin, target])
    s.commit()
    ids = (admin.id, target.id)
    s.close()
    return ids


@pytest.mark.issue("ISS-471")
@pytest.mark.xfail(reason="ISS-471 unfixed", strict=True)
def test_losing_tier_updates_response_reports_its_own_value(engine, seeded_ids):
    """A's 200 response must report the tier A itself set, not B's."""
    admin_id, target_id = seeded_ids
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    session_a = Session()
    session_b = Session()

    admin_a = session_a.query(User).filter(User.id == admin_id).one()
    admin_b = session_b.query(User).filter(User.id == admin_id).one()
    # NOTE: the target user is deliberately NOT pre-loaded on either session —
    # each request's `update_user_tier`/`update_user_role` call does its own
    # `db.query(User)...first()` for the target, matching the real per-request
    # `Depends(get_db)` session that has never touched this row before. Pre-
    # loading it here would leave a stale in-memory snapshot on session_b that
    # masks the very race being staged (an unchanged-value reassignment is a
    # session-tracking no-op in SQLAlchemy, not a real DB write).

    real_refresh = session_a.refresh
    response_b_holder: dict = {}

    def refresh_after_b_commits(*args, **kwargs):
        response_b_holder["response"] = update_user_tier(
            target_id,
            UpdateTierRequest(tier="pro"),
            admin=admin_b,
            db=session_b,
        )
        return real_refresh(*args, **kwargs)

    session_a.refresh = refresh_after_b_commits

    response_a = update_user_tier(
        target_id,
        UpdateTierRequest(tier="enterprise"),
        admin=admin_a,
        db=session_a,
    )

    session_a.close()
    session_b.close()

    assert response_b_holder["response"].tier == "pro"  # B's own response is correct

    assert response_a.tier == "enterprise", (
        f"request A set tier='enterprise' but its own response reported "
        f"{response_a.tier!r} (request B's value) — lost update + false-success "
        "response body on a privilege field"
    )


@pytest.mark.issue("ISS-471")
@pytest.mark.xfail(reason="ISS-471 unfixed", strict=True)
def test_losing_role_updates_response_reports_its_own_value(engine, seeded_ids):
    """A's 200 response must report the is_admin flag A itself set, not B's."""
    admin_id, target_id = seeded_ids
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    session_a = Session()
    session_b = Session()

    admin_a = session_a.query(User).filter(User.id == admin_id).one()
    admin_b = session_b.query(User).filter(User.id == admin_id).one()
    # NOTE: see the tier test above for why the target is deliberately not
    # pre-loaded on either session.

    real_refresh = session_a.refresh
    response_b_holder: dict = {}

    def refresh_after_b_commits(*args, **kwargs):
        response_b_holder["response"] = update_user_role(
            target_id,
            UpdateRoleRequest(is_admin=False),
            admin=admin_b,
            db=session_b,
        )
        return real_refresh(*args, **kwargs)

    session_a.refresh = refresh_after_b_commits

    response_a = update_user_role(
        target_id,
        UpdateRoleRequest(is_admin=True),
        admin=admin_a,
        db=session_a,
    )

    session_a.close()
    session_b.close()

    assert response_b_holder["response"].is_admin is False  # B's own response is correct

    assert response_a.is_admin is True, (
        f"request A set is_admin=True but its own response reported "
        f"{response_a.is_admin!r} (request B's value) — lost update + "
        "false-success response body granting/withholding admin privilege"
    )
