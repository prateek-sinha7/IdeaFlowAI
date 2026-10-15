"""QA-KB-109 analysis probe: which admin endpoints refuse an admin acting on their OWN id?

Offline. In-memory SQLite, boto3 mocked, no network, nothing minted. The handlers are
called directly with the admin as both actor and target, the way
backend/tests/integration/api/test_admin_privilege_atomicity_api.py calls them.
Application source is not edited and nothing is patched except the Cognito client.

Why it matters: the /admin users table renders one row of controls per user, with no self
check (frontend/src/app/admin/page.tsx:512-623). Whether an own-row control is a harmless
dead end or a real action depends on the endpoint behind it.

Run from backend/ (one file, offline):
  PYTHONDONTWRITEBYTECODE=1 DATABASE_URL=sqlite:///:memory: \
    .venv/bin/python -m pytest <this file> -p no:cacheprovider -q -s -W ignore
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401 - registers every model on Base.metadata
from app.api import admin as admin_mod
from app.core import cognito
from app.models.database import Base
from app.models.user import User


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine, autocommit=False, autoflush=False)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def _user(db, *, id, email, sub, is_admin, tier="enterprise") -> User:
    u = User(id=id, email=email, cognito_sub=sub, tier=tier, is_admin=is_admin)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


class _Req:
    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


def _world(db):
    """Two admins and one plain user, so 'last admin' is never the reason for a refusal."""
    me = _user(db, id="me-admin", email="admin@velocity.ai", sub="sub-me", is_admin=True)
    other = _user(db, id="other-admin", email="bob@velocity.ai", sub="sub-bob", is_admin=True)
    plain = _user(db, id="plain-user", email="alice@velocity.ai", sub="sub-alice", is_admin=False, tier="pro")
    return me, other, plain


def _call(name, me, db, fake_client):
    """Invoke the handler a row control reaches, with the admin targeting their own id."""
    with patch.object(cognito, "_client", return_value=fake_client):
        if name == "tier":
            return admin_mod.update_user_tier(user_id=me.id, request=_Req(tier="basic"), admin=me, db=db)
        if name == "role":
            return admin_mod.update_user_role(user_id=me.id, request=_Req(is_admin=False), admin=me, db=db)
        if name == "disable":
            return admin_mod.disable_user(user_id=me.id, admin=me, db=db)
        if name == "delete":
            return admin_mod.delete_user(user_id=me.id, admin=me, db=db)
        if name == "reset-password":
            return admin_mod.reset_user_password(user_id=me.id, request=_Req(), admin=me, db=db)
    raise AssertionError(name)


ENDPOINTS = ["tier", "role", "disable", "delete", "reset-password"]
GUARDED = {
    "tier": "You cannot change your own tier",
    "role": "You cannot remove your own admin access",
    "disable": "You cannot disable your own account",
    "delete": "You cannot delete your own account",
}


@pytest.mark.parametrize("name", ENDPOINTS)
def test_self_target_outcome(name, db):
    """[S] Print and assert, per endpoint, what the server does when actor == target."""
    me, _other, _plain = _world(db)
    fake_client = MagicMock()
    try:
        out = _call(name, me, db, fake_client)
    except HTTPException as exc:
        print(f"[S] {name:15s} -> HTTP {exc.status_code} {exc.detail!r}; cognito calls: {len(fake_client.method_calls)}")
        assert name in GUARDED, f"{name} refused unexpectedly: {exc.detail!r}"
        assert exc.status_code == 400
        assert GUARDED[name] in exc.detail
        assert fake_client.method_calls == [], "a refused self-action must not touch Cognito"
        return
    print(f"[S] {name:15s} -> ACCEPTED, returned {out!r}; cognito calls: {[c[0] for c in fake_client.method_calls]}")
    assert name == "reset-password", f"{name} was accepted for the admin's own id; the guard is gone"
    assert out == {"status": "temporary_password_set"}


def test_self_reset_side_effects(db):
    """[R] What the accepted self-reset does to the admin's own account."""
    me, _other, _plain = _world(db)
    assert me.tokens_valid_from is None
    fake_client = MagicMock()
    out = _call("reset-password", me, db, fake_client)

    db.expire_all()
    refreshed = db.query(User).filter(User.id == me.id).one()
    set_pw = fake_client.admin_set_user_password.call_args.kwargs
    signout = fake_client.admin_user_global_sign_out.call_args.kwargs
    print(f"[R] response                 : {out!r}")
    print(f"[R] AdminSetUserPassword     : Username={set_pw['Username']!r} Permanent={set_pw['Permanent']!r} (password length {len(set_pw['Password'])}, not in the response)")
    print(f"[R] AdminUserGlobalSignOut   : Username={signout['Username']!r}")
    print(f"[R] tokens_valid_from stamped: {refreshed.tokens_valid_from is not None} (every access token issued before now, the admin's own included, is rejected)")
    assert set_pw["Username"] == me.email and set_pw["Permanent"] is False
    assert signout["Username"] == me.email
    assert refreshed.tokens_valid_from is not None
    assert set_pw["Password"] not in repr(out)
    assert fake_client.admin_set_user_password.call_count == 1


def test_control_reset_for_another_user_is_the_intended_use(db):
    """[C] The endpoint's documented purpose ('another user') still works."""
    me, _other, plain = _world(db)
    fake_client = MagicMock()
    with patch.object(cognito, "_client", return_value=fake_client):
        out = admin_mod.reset_user_password(user_id=plain.id, request=_Req(), admin=me, db=db)
    assert out == {"status": "temporary_password_set"}
    assert fake_client.admin_set_user_password.call_args.kwargs["Username"] == plain.email
    print("[C] reset of ANOTHER user -> accepted, as documented")


@pytest.mark.xfail(strict=True, reason="RED today: reset_user_password has no `user_id == admin.id` guard (admin.py:501-546)")
def test_expected_contract_self_reset_is_refused(db):
    """[X] The contract the siblings already meet (FIX-310): refuse an actor targeting their own account."""
    me, _other, _plain = _world(db)
    fake_client = MagicMock()
    with pytest.raises(HTTPException) as exc:
        _call("reset-password", me, db, fake_client)
    assert exc.value.status_code == 400
    assert fake_client.admin_set_user_password.call_count == 0
