"""Unit tests for ``app/main.py`` — the unauthenticated public share route.

``view_shared_run`` must answer an unknown / expired token, or a run with no
deliverable, with a 404 (no enumeration). It used to raise ``HTTPException``
without importing it, so that path died with ``NameError`` — a 500 instead of
the 404 the route promises.
"""

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.workflow import WorkflowRun


@pytest.fixture
def share_lookup(monkeypatch):
    """Point the share route at a spec'd fake session and a stubbed token lookup.

    Returns a setter: call it with the run the lookup should return (or None).
    """
    import app.api.runs as runs_module
    import app.models.database as database_module

    def _fake_get_db():
        yield MagicMock(spec=Session)

    monkeypatch.setattr(database_module, "get_db", _fake_get_db)

    def _returning(run):
        monkeypatch.setattr(
            runs_module, "get_shared_run_by_token", lambda token, db: run
        )

    return _returning


async def test_view_shared_run_raises_not_found_when_token_unknown(share_lookup):
    from app.main import view_shared_run

    share_lookup(None)

    with pytest.raises(HTTPException) as exc_info:
        await view_shared_run("unknown-token")

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Share not found or expired."


async def test_view_shared_run_raises_not_found_when_run_has_no_output(share_lookup):
    from app.main import view_shared_run

    run = MagicMock(spec=WorkflowRun)
    run.output = ""
    share_lookup(run)

    with pytest.raises(HTTPException) as exc_info:
        await view_shared_run("token-for-empty-run")

    assert exc_info.value.status_code == 404
