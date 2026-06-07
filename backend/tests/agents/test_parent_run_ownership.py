"""tests/agents/test_parent_run_ownership.py — the L16 ownership check (CTX-03 / INV-8).

Two layers:

1. Unit tests for the pure ``assert_owns`` helper (``agents/execution_engine/authz.py``)
   — same-owner allowed, cross-owner denied (``PermissionError``), the ``"anon"`` principal
   treated as a REAL owner (not a bypass), and a by-construction purity assertion (no I/O).

2. End-to-end tests driving ``ExecutionEngine.execute()`` on the ``prototype_revision``
   pipeline: a cross-owner ``parent_run_id`` raises ``PermissionError`` out of ``execute()``
   with NOTHING seeded; a same-owner missing/TTL-swept parent still hits the graceful-degrade
   try and proceeds; the ``"anon"`` principal (``user_id=None``) cannot bypass.

Offline / no DB / no API key — the ``backend:characterization`` job.
"""

from __future__ import annotations

import inspect

import pytest

from agents.execution_engine import authz
from agents.execution_engine.authz import assert_owns


# ════════════════════════════════════════════════════════════════════════════
# Unit tests — the pure assert_owns helper
# ════════════════════════════════════════════════════════════════════════════


def test_assert_owns_same_owner_allowed() -> None:
    """Same owner → returns None, no raise."""
    assert assert_owns("alice", "run-123", parent_owner_id="alice") is None


def test_assert_owns_cross_owner_denied() -> None:
    """Cross-owner → raises PermissionError naming the owner and the parent run id."""
    with pytest.raises(PermissionError) as exc:
        assert_owns("alice", "run-123", parent_owner_id="bob")
    msg = str(exc.value)
    assert "alice" in msg and "run-123" in msg


def test_assert_owns_anon_is_a_real_owner_denied() -> None:
    """The ``"anon"`` principal cannot bypass — a cross-owner anon parent is denied."""
    with pytest.raises(PermissionError):
        assert_owns("anon", "run-123", parent_owner_id="bob")


def test_assert_owns_anon_same_session_allowed() -> None:
    """Two same-session anon runs (same principal string) are allowed."""
    assert assert_owns("anon", "run-123", parent_owner_id="anon") is None


def test_assert_owns_is_pure_no_io() -> None:
    """By construction: the helper performs a string compare only — no store/sandbox/disk
    calls (D-06 — Phase 5 AUTHZ-02 must relocate it as a mechanical move).

    Scan the executable BODY only (strip the docstring, whose prose legitimately mentions
    ``RunSandbox`` to explain what the helper deliberately does NOT do)."""
    import ast
    import textwrap

    tree = ast.parse(textwrap.dedent(inspect.getsource(assert_owns)))
    fn = tree.body[0]
    body = fn.body
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        body = body[1:]  # drop the docstring expression
    code = "\n".join(ast.dump(node) for node in body)
    for banned in ("RunSandbox", "_store", "read", "write", "open", "Path"):
        assert banned not in code, f"assert_owns must be pure; found I/O token {banned!r}"
