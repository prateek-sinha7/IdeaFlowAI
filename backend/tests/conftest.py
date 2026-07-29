"""Shared pytest fixtures for backend tests.

The former ``fk_session`` / ``make_fk_sqlite_engine`` FK-enforcing fixtures were
removed in 05-07 alongside their sole consumer (``test_artifact_store_fk.py``):
that regression covered the now-deleted thin-store ``workflow_artifacts`` FK path.
Tests that need an FK-enforcing in-memory SQLite session build it locally (see the
ScopedStore bootstrap in ``tests/unit/test_revision_intelligence.py`` / the typed
``artifact_refs`` suites).
"""

from __future__ import annotations

import pytest

import app.models  # noqa: F401 — importing the package registers every model on Base.metadata


@pytest.fixture(autouse=True)
def _no_live_model_from_a_unit_test(request, monkeypatch):
    """Fail loudly if a grading unit test tries to build a REAL judge model.

    A test that forgets to fake `judge.grade` does not fail — it reaches the
    provider, hangs on the network and spends real tokens. That happened while
    writing these tests. Blowing up on the attempt turns a silent bill into an
    immediate, obvious error naming the missing fixture.
    """
    if "grading" not in request.node.nodeid:
        return
    import app.agents.model_factory

    def refuse(*_args, **_kwargs):
        raise AssertionError(
            "a unit test tried to build a REAL model — add the `judgements` fixture, "
            "or patch build_model yourself if that is what you are testing"
        )

    # Applied first, so a test that deliberately patches build_model still wins.
    monkeypatch.setattr(app.agents.model_factory, "build_model", refuse)
