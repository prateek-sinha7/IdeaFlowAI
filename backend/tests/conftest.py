"""Shared pytest fixtures for backend tests.

The former ``fk_session`` / ``make_fk_sqlite_engine`` FK-enforcing fixtures were
removed in 05-07 alongside their sole consumer (``test_artifact_store_fk.py``):
that regression covered the now-deleted thin-store ``workflow_artifacts`` FK path.
Tests that need an FK-enforcing in-memory SQLite session build it locally (see the
ScopedStore bootstrap in ``tests/unit/test_revision_intelligence.py`` / the typed
``artifact_refs`` suites).
"""

from __future__ import annotations

import app.models  # noqa: F401 — importing the package registers every model on Base.metadata
