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


# ════════════════════════════════════════════════════════════════════════════
# End-to-end tests — the wired ownership check in ExecutionEngine.execute()
# ════════════════════════════════════════════════════════════════════════════
#
# These drive the REAL execute() on the prototype_revision pipeline (offline,
# scripted models) through the parent-run seed block. The cross-owner case must
# RAISE before any parent file is seeded; the same-owner missing-parent case must
# degrade gracefully (no raise); the anon principal cannot bypass.

_REVISION_MSG = (
    "=== EXISTING PROTOTYPE HTML ===\n"
    "<!doctype html><html><body>original</body></html>\n"
    "=== END EXISTING HTML ===\n"
    "=== REVISION REQUEST ===\nMake the header blue.\n=== END REQUEST ==="
)


async def _drive_revision(
    *,
    user_id: str | None,
    parent_run_id: str,
    parent_owner_override: str | None = None,
    seed_parent_owner: str | None = None,
    run_id: str | None = None,
):
    """Drive execute() on prototype_revision with a parent_run_id, returning the
    captured events. Mirrors the _scripted_model harness wiring but threads
    parent_run_id and lets a test override the by-convention parent owner.

    ``seed_parent_owner`` — if given, pre-create a parent sandbox owned by that
    principal containing spec.md/design.md/tasks.md (so a same-owner run would seed
    them); used to assert NOTHING is seeded on a cross-owner denial.
    """
    import uuid as _uuid

    import agents.execution_engine.engine as engine_mod
    import agents.factory as factory_mod
    from agents.execution_engine.engine import ExecutionEngine
    from agents.registry import get_pipeline_agents
    from app.agents.sandbox import RunSandbox
    from app.core.config import settings as _settings

    from tests.agents._scripted_model import (
        _RUNS_ROOT,
        ScriptedFakeChatModel,
        _scripts_for,
    )

    _settings.RUNS_ROOT = _RUNS_ROOT
    engine_mod.ALWAYS_CLARIFY = False

    specs = get_pipeline_agents("prototype_revision")

    _orig_create_runner = factory_mod.create_runner
    _orig_engine_create_runner = getattr(engine_mod, "create_runner", None)

    def _patched_create_runner(agent_id, ctx, **kw):
        ctx.model = ScriptedFakeChatModel(_scripts_for(agent_id))
        return _orig_create_runner(agent_id, ctx, **kw)

    factory_mod.create_runner = _patched_create_runner
    engine_mod.create_runner = _patched_create_runner

    engine = ExecutionEngine()

    async def _fake_run_planner(user_message, pipeline_run_id, model_id, cancel_event, ptype="custom"):
        return engine._default_planning_context(user_message), "PROCEED"

    engine._run_planner = _fake_run_planner  # type: ignore[assignment]

    async def _noop_store(*a, **k):
        return "artifact-id"

    engine._store.store = _noop_store  # type: ignore[assignment]

    async def _noop_gate(*a, **k):
        return
        yield  # pragma: no cover

    engine._run_review_gate = _noop_gate  # type: ignore[assignment]

    # Override the by-convention parent owner to exercise the cross-owner path.
    if parent_owner_override is not None:
        engine._derive_parent_owner = (  # type: ignore[assignment]
            lambda _uid, _prid, _o=parent_owner_override: _o
        )

    # Optionally seed a real parent sandbox (owned by some principal) so we can prove
    # that a cross-owner denial copies NOTHING into this run's sandbox.
    if seed_parent_owner is not None:
        psb = RunSandbox(seed_parent_owner, parent_run_id)
        psb.ensure()
        psb.write("spec.md", "# parent spec\n")
        psb.write("design.md", "# parent design\n")
        psb.write("tasks.md", "# parent tasks\n")

    run_id = run_id or f"ownertest-{_uuid.uuid4().hex[:8]}"
    events: list[dict] = []
    try:
        async for ev in engine.execute(
            agents=list(specs),
            user_message=_REVISION_MSG,
            pipeline_run_id=run_id,
            pipeline_type="prototype_revision",
            user_id=user_id,
            gate_agent_ids=[],
            parent_run_id=parent_run_id,
        ):
            events.append(ev)
    finally:
        factory_mod.create_runner = _orig_create_runner
        if _orig_engine_create_runner is not None:
            engine_mod.create_runner = _orig_engine_create_runner

    # Surface this run's sandbox so callers can assert what was (not) seeded.
    this_sb = RunSandbox(user_id or "anon", run_id)
    return events, this_sb


@pytest.mark.asyncio
async def test_execute_cross_owner_parent_raises_and_seeds_nothing() -> None:
    """A cross-owner parent_run_id RAISES PermissionError out of execute() BEFORE any
    parent file is seeded (the L16 CHECK denial test). The parent sandbox is real and
    owned by 'bob'; alice's revision sandbox must contain NO copied spec/design/tasks."""
    parent_run_id = "parent-owned-by-bob"
    alice_run_id = "alice-revision-crossowner"
    with pytest.raises(PermissionError):
        await _drive_revision(
            user_id="alice",
            parent_run_id=parent_run_id,
            parent_owner_override="bob",        # cross-owner derivation
            seed_parent_owner="bob",            # parent sandbox really has the files
            run_id=alice_run_id,
        )
    from app.agents.sandbox import RunSandbox
    # Nothing was seeded into alice's run sandbox — the raise fired ABOVE the seed try,
    # so no parent spec/design/tasks was ever copied across the owner boundary.
    alice_sb = RunSandbox("alice", alice_run_id)
    assert alice_sb.read("spec.md") is None
    assert alice_sb.read("design.md") is None
    assert alice_sb.read("tasks.md") is None
    # And bob's parent sandbox is untouched (still owns its files).
    psb = RunSandbox("bob", parent_run_id)
    assert psb.read("spec.md") == "# parent spec\n"


@pytest.mark.asyncio
async def test_execute_same_owner_missing_parent_degrades_gracefully() -> None:
    """A legitimate SAME-OWNER parent that is missing / TTL-swept does NOT raise — the
    graceful-degrade try is preserved (CTX-05 parity); the run completes normally."""
    events, _sb = await _drive_revision(
        user_id="alice",
        parent_run_id="alice-parent-never-created",  # no parent sandbox on disk
        # no override → by-convention owner == alice == ectx.owner_id (same owner)
    )
    # The run produced events and did not raise (graceful degrade on the missing parent).
    assert events, "same-owner revision run should produce events, not raise"
    assert any(ev.get("type") in ("complete", "agent_complete", "pipeline_complete")
               or "complete" in str(ev.get("type", "")) for ev in events), (
        "same-owner revision run should reach completion"
    )


@pytest.mark.asyncio
async def test_execute_anon_principal_cannot_bypass() -> None:
    """user_id=None → owner 'anon'. A cross-owner anon parent (owner 'bob') is DENIED —
    the 'anon' fallback string is a real owner, not a bypass."""
    with pytest.raises(PermissionError):
        await _drive_revision(
            user_id=None,                      # → owner_id == "anon"
            parent_run_id="parent-owned-by-bob",
            parent_owner_override="bob",
        )


@pytest.mark.asyncio
async def test_execute_anon_same_session_parent_allowed() -> None:
    """Two same-session anon runs (owner 'anon' on both sides) are allowed — a missing
    same-anon parent degrades gracefully, no raise."""
    events, _sb = await _drive_revision(
        user_id=None,                          # → owner_id == "anon"
        parent_run_id="anon-parent-never-created",
        # no override → by-convention owner == "anon" == ectx.owner_id (same owner)
    )
    assert events, "same-anon-owner revision run should produce events, not raise"


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
