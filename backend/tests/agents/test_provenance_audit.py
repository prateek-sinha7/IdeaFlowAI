"""tests/agents/test_provenance_audit.py — Provenance audit tests (task 9.4).

Requirement 19 — audit trail for git provenance operations.

Six fixtures (Requirement 19 AC 9):
  1. completed run         → snapshot_commit row via ProvenanceAuditObserver
  2. degraded / blocked    → snapshot_commit row marked degraded
  3. legacy chain read     → chain_payload_installed row
  4. refused chain launch  → chain_refused row (no receiving run id)
  5. restore               → restore row via ScopedStore.write_provenance_audit
  6. crash-recovered run   → recovery_commit row

Additional coverage:
  - Content prohibitions: typed columns only, no raw output/prompts/secrets/PII
  - Owner scoping: cross-owner lookup returns None
  - chain_refused is scoped to actor+source, no receiving run row needed
  - Observer fail-closed: a raising record_fn must not roll back the commit
  - Bidirectional reconstruction via source_ref / source_run_id join

All tests use an in-memory SQLite (StaticPool) — no Postgres, no Bedrock.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# ── DB bootstrap ─────────────────────────────────────────────────────────────

import app.models  # noqa: F401 — register every table on Base.metadata
from app.models.database import Base
from app.models.run_provenance_audit import (
    RunProvenanceAudit,
    lookup_idempotent_restore,
)
from agents.authz import ScopedStore
from agents.capabilities.hooks.base import HOOK_CONTINUE
from agents.capabilities.hooks.provenance_audit import ProvenanceAuditObserver


# ── Helpers ───────────────────────────────────────────────────────────────────


def _run_id() -> str:
    return str(uuid.uuid4())


def _make_db():
    """Return (session, engine) backed by a fresh in-memory SQLite."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = Session()
    return session, engine


def _make_store(session, owner_id: str = "alice", workspace_id: str = "ws-1") -> ScopedStore:
    return ScopedStore(owner_id=owner_id, workspace_id=workspace_id, session=session)


def _make_runner(store: ScopedStore) -> Any:
    """Minimal runner stub whose record_provenance_audit delegates to ScopedStore."""
    runner = MagicMock()

    async def _record(
        run_id: str,
        operation: str,
        *,
        commit_sha: str | None = None,
        tag_name: str | None = None,
        source_ref: str | None = None,
        idempotency_key: str | None = None,
    ) -> str | None:
        return await store.write_provenance_audit(
            run_id,
            operation,
            commit_sha=commit_sha,
            tag_name=tag_name,
            source_ref=source_ref,
            idempotency_key=idempotency_key,
        )

    runner.record_provenance_audit = _record
    return runner


def _make_ctx(runner: Any, run_id: str, owner_id: str = "alice") -> Any:
    ctx = MagicMock()
    ctx.run_id = run_id
    ctx.user_id = owner_id
    ctx.runner = runner
    return ctx


def _make_event(
    *,
    audit_operation: str | None,
    commit_sha: str = "abc123",
    tag_name: str | None = None,
    source_ref: str | None = None,
    idempotency_key: str | None = None,
) -> dict:
    return {
        "audit_operation": audit_operation,
        "commit_sha": commit_sha,
        "audit_detail": {
            k: v
            for k, v in {
                "tag_name": tag_name,
                "source_ref": source_ref,
                "idempotency_key": idempotency_key,
            }.items()
            if v is not None
        },
    }


def _query_audit_rows(session, *, owner_id: str, run_id: str | None = None) -> list[RunProvenanceAudit]:
    q = session.query(RunProvenanceAudit).filter(RunProvenanceAudit.owner_id == owner_id)
    if run_id is not None:
        q = q.filter(RunProvenanceAudit.run_id == run_id)
    return q.all()


# ══════════════════════════════════════════════════════════════════════════════
# Fixture 1 — completed run → snapshot_commit row
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_completed_run_writes_snapshot_commit_row() -> None:
    """A completed-run post_commit event produces one snapshot_commit audit row."""
    session, engine = _make_db()
    try:
        store = _make_store(session)
        runner = _make_runner(store)
        run_id = _run_id()
        ctx = _make_ctx(runner, run_id)
        observer = ProvenanceAuditObserver()

        event = _make_event(
            audit_operation="snapshot_commit",
            commit_sha="deadbeef",
            tag_name="v1",
        )
        outcome = await observer.handle(event, ctx)

        assert outcome.outcome == HOOK_CONTINUE
        rows = _query_audit_rows(session, owner_id="alice", run_id=run_id)
        assert len(rows) == 1
        row = rows[0]
        assert row.operation == "snapshot_commit"
        assert row.commit_sha == "deadbeef"
        assert row.tag_name == "v1"
        assert row.owner_id == "alice"
        assert row.workspace_id == "ws-1"
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


# ══════════════════════════════════════════════════════════════════════════════
# Fixture 2 — degraded / blocked payload
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_degraded_run_writes_snapshot_commit_row() -> None:
    """A blocked/degraded run still writes a snapshot_commit row (record presence on failure)."""
    session, engine = _make_db()
    try:
        store = _make_store(session)
        runner = _make_runner(store)
        run_id = _run_id()
        ctx = _make_ctx(runner, run_id)
        observer = ProvenanceAuditObserver()

        # Degraded run: snapshot_commit but no tag (non-chainable snapshot)
        event = _make_event(
            audit_operation="snapshot_commit",
            commit_sha="cafe1234",
            # No tag_name — blocked payload, no vN tag issued
        )
        outcome = await observer.handle(event, ctx)

        assert outcome.outcome == HOOK_CONTINUE
        rows = _query_audit_rows(session, owner_id="alice", run_id=run_id)
        assert len(rows) == 1
        row = rows[0]
        assert row.operation == "snapshot_commit"
        assert row.commit_sha == "cafe1234"
        assert row.tag_name is None  # no tag for a blocked/degraded payload
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


# ══════════════════════════════════════════════════════════════════════════════
# Fixture 3 — legacy chain read → chain_payload_installed row
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_legacy_chain_read_writes_chain_payload_installed_row() -> None:
    """A chain install (legacy or v2) writes a chain_payload_installed audit row."""
    session, engine = _make_db()
    try:
        store = _make_store(session)
        run_id = _run_id()
        source_run_id = _run_id()

        # chain_payload_installed is a non-commit operation — written directly
        # at the call site (chain_context.py), not via the observer.
        await store.write_provenance_audit(
            run_id,
            "chain_payload_installed",
            source_ref=source_run_id,
            tag_name="legacy",
        )

        rows = _query_audit_rows(session, owner_id="alice", run_id=run_id)
        assert len(rows) == 1
        row = rows[0]
        assert row.operation == "chain_payload_installed"
        assert row.source_ref == source_run_id
        # The receiving run's row carries source_ref pointing at the source run —
        # forward reconstruction: row.source_ref → source's ref/tag
        assert row.run_id == run_id
        assert row.owner_id == "alice"
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


# ══════════════════════════════════════════════════════════════════════════════
# Fixture 4 — refused chain launch → chain_refused row scoped to actor+source
# ══════════════════════════════════════════════════════════════════════════════


def test_chain_refused_row_has_no_receiving_run() -> None:
    """chain_refused row: run_id == source_run_id, no receiving run row required.

    A refusal has no receiving run, so the row is scoped to the actor and the
    source id (Requirement 19 AC 2 / task 9.1 docstring).
    """
    from app.models.run_provenance_audit import RunProvenanceAudit

    session, engine = _make_db()
    try:
        actor_id = "alice"
        workspace_id = "ws-1"
        source_run_id = _run_id()
        reason = "source_not_finalized"

        row = RunProvenanceAudit(
            id=str(uuid.uuid4()),
            owner_id=actor_id,
            workspace_id=workspace_id,
            # No receiving run — run_id IS the source_run_id (the convention
            # used by _write_chain_refused_audit in run_commands.py)
            run_id=source_run_id,
            operation="chain_refused",
            source_ref=source_run_id,
            outcome=reason,
        )
        session.add(row)
        session.commit()

        # The row is scoped to the actor; querying by owner returns it
        rows = _query_audit_rows(session, owner_id=actor_id)
        assert len(rows) == 1
        assert rows[0].operation == "chain_refused"
        assert rows[0].source_ref == source_run_id
        assert rows[0].run_id == source_run_id  # no separate receiving run id
        assert rows[0].outcome == reason

        # Cross-owner query returns nothing — default-deny
        cross_rows = _query_audit_rows(session, owner_id="bob")
        assert cross_rows == []
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


# ══════════════════════════════════════════════════════════════════════════════
# Fixture 5 — restore → restore row + idempotency lookup
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_restore_writes_row_and_lookup_idempotent_restore() -> None:
    """POST /runs/{id}/restore writes a restore row; lookup_idempotent_restore finds it."""
    session, engine = _make_db()
    try:
        store = _make_store(session, owner_id="carol", workspace_id="ws-2")
        run_id = _run_id()
        key = str(uuid.uuid4())

        await store.write_provenance_audit(
            run_id,
            "restore",
            commit_sha="feed1234",
            tag_name="v2",
            idempotency_key=key,
        )

        # Idempotency lookup returns the typed projection
        result = lookup_idempotent_restore(session, owner_id="carol", idempotency_key=key)
        assert result is not None
        assert result["commit_id"] == "feed1234"
        assert result["tag_name"] == "v2"

        # Cross-owner lookup returns None
        cross = lookup_idempotent_restore(session, owner_id="dave", idempotency_key=key)
        assert cross is None
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


# ══════════════════════════════════════════════════════════════════════════════
# Fixture 6 — crash-recovered run → recovery_commit row
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_crash_recovered_run_writes_recovery_commit_row() -> None:
    """A crash-reconciliation commit produces a recovery_commit row."""
    session, engine = _make_db()
    try:
        store = _make_store(session)
        runner = _make_runner(store)
        run_id = _run_id()
        ctx = _make_ctx(runner, run_id)
        observer = ProvenanceAuditObserver()

        event = _make_event(
            audit_operation="recovery_commit",
            commit_sha="baad0001",
        )
        outcome = await observer.handle(event, ctx)

        assert outcome.outcome == HOOK_CONTINUE
        rows = _query_audit_rows(session, owner_id="alice", run_id=run_id)
        assert len(rows) == 1
        assert rows[0].operation == "recovery_commit"
        assert rows[0].commit_sha == "baad0001"
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


# ══════════════════════════════════════════════════════════════════════════════
# Content prohibitions — typed columns only, no free-form sensitive data
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_audit_row_has_only_typed_columns_no_raw_content() -> None:
    """Audit rows expose only typed columns; no raw output, diffs, prompts, or secrets."""
    session, engine = _make_db()
    try:
        store = _make_store(session)
        runner = _make_runner(store)
        run_id = _run_id()
        ctx = _make_ctx(runner, run_id)
        observer = ProvenanceAuditObserver()

        # audit_detail carries extra keys that must be stripped — only the
        # three allowlist keys survive to the row
        event = {
            "audit_operation": "snapshot_commit",
            "commit_sha": "0011aabb",
            "audit_detail": {
                "tag_name": "v3",
                "source_ref": "refs/ideaflow/runs/some-run-id",
                "idempotency_key": "key-xyz",
                # These must NOT appear on the row:
                "raw_output": "SECRET_TOKEN=abc123",
                "diff": "--- old\n+++ new",
                "prompt": "You are an AI assistant…",
            },
        }
        await observer.handle(event, ctx)

        rows = _query_audit_rows(session, owner_id="alice", run_id=run_id)
        assert len(rows) == 1
        row = rows[0]

        # Typed columns populated correctly
        assert row.operation == "snapshot_commit"
        assert row.commit_sha == "0011aabb"
        assert row.tag_name == "v3"
        assert row.source_ref == "refs/ideaflow/runs/some-run-id"
        assert row.idempotency_key == "key-xyz"

        # No extra-data column exists on the row (the model has detail_json but
        # write_provenance_audit does NOT accept a detail_json kwarg — it is
        # intentionally not surfaced in the write path per task 9.1).
        # The row must NOT carry any of the prohibited extra keys.
        row_dict = {c.name: getattr(row, c.name) for c in row.__table__.columns}
        for prohibited in ("raw_output", "diff", "prompt"):
            assert prohibited not in row_dict, f"Prohibited field {prohibited!r} leaked onto row"
        # detail_json column exists but was not set by the observer path
        # (write_provenance_audit never accepts it as a kwarg)
        assert row_dict.get("detail_json") is None
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


# ══════════════════════════════════════════════════════════════════════════════
# Owner scoping — cross-owner read refused
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_cross_owner_cannot_read_audit_rows() -> None:
    """A row written for alice is invisible to a bob-scoped store query."""
    session, engine = _make_db()
    try:
        alice_store = _make_store(session, owner_id="alice")
        runner = _make_runner(alice_store)
        run_id = _run_id()
        ctx = _make_ctx(runner, run_id, owner_id="alice")
        observer = ProvenanceAuditObserver()

        await observer.handle(
            _make_event(audit_operation="snapshot_commit", commit_sha="aaa"),
            ctx,
        )

        # Alice sees her row
        alice_rows = _query_audit_rows(session, owner_id="alice", run_id=run_id)
        assert len(alice_rows) == 1

        # Bob sees nothing — default-deny IDOR gate
        bob_rows = _query_audit_rows(session, owner_id="bob", run_id=run_id)
        assert bob_rows == []

        # lookup_idempotent_restore also enforces owner scoping
        alice_key = str(uuid.uuid4())
        await alice_store.write_provenance_audit(
            run_id, "restore", idempotency_key=alice_key, commit_sha="bbb"
        )
        assert lookup_idempotent_restore(session, "alice", alice_key) is not None
        assert lookup_idempotent_restore(session, "bob", alice_key) is None
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


# ══════════════════════════════════════════════════════════════════════════════
# Observer fail-closed — raising record_fn must NOT roll back the commit
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_observer_failure_does_not_propagate() -> None:
    """A raising record_provenance_audit must never propagate to the commit path.

    The observer wraps the entire body in try/except (Requirement 19 / task 9.1
    observation-only contract).  A DB failure or any exception inside handle()
    returns HOOK_CONTINUE rather than raising.
    """
    run_id = _run_id()

    # Runner whose record_provenance_audit always raises
    failing_runner = MagicMock()
    failing_runner.record_provenance_audit = AsyncMock(
        side_effect=RuntimeError("simulated DB failure")
    )

    ctx = _make_ctx(failing_runner, run_id)
    observer = ProvenanceAuditObserver()

    # Must not raise — the observer catches the exception
    outcome = await observer.handle(
        _make_event(audit_operation="snapshot_commit", commit_sha="dead"),
        ctx,
    )

    # The commit path is unaffected; hook returns CONTINUE
    assert outcome.outcome == HOOK_CONTINUE
    failing_runner.record_provenance_audit.assert_called_once()


# ══════════════════════════════════════════════════════════════════════════════
# audit_operation=None → no row written (not an audited class)
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_none_audit_operation_writes_no_row() -> None:
    """audit_operation=None means 'not an audited class' — no row is written."""
    session, engine = _make_db()
    try:
        store = _make_store(session)
        runner = _make_runner(store)
        run_id = _run_id()
        ctx = _make_ctx(runner, run_id)
        observer = ProvenanceAuditObserver()

        outcome = await observer.handle(
            _make_event(audit_operation=None),
            ctx,
        )

        assert outcome.outcome == HOOK_CONTINUE
        rows = _query_audit_rows(session, owner_id="alice", run_id=run_id)
        assert rows == []
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


# ══════════════════════════════════════════════════════════════════════════════
# Bidirectional reconstruction
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_bidirectional_reconstruction_via_source_ref() -> None:
    """Forward: receiving run row carries source_ref → source run.
    Reverse:  source_ref column query → receiving run ids.

    This closes Requirement 19 AC 6 — the forward direction (which ref fed this
    run?) and the reverse (which runs were fed from this source?).
    """
    session, engine = _make_db()
    try:
        store = _make_store(session, owner_id="alice")
        source_run_id = _run_id()
        receiving_run_1 = _run_id()
        receiving_run_2 = _run_id()

        # Two receiving runs both chain from the same source ref
        for recv_id in (receiving_run_1, receiving_run_2):
            await store.write_provenance_audit(
                recv_id,
                "chain_source_selected",
                source_ref=source_run_id,
                tag_name="v1",
            )

        # Forward: given receiving_run_1, find its source ref
        fwd_rows = (
            session.query(RunProvenanceAudit)
            .filter(
                RunProvenanceAudit.owner_id == "alice",
                RunProvenanceAudit.run_id == receiving_run_1,
                RunProvenanceAudit.operation == "chain_source_selected",
            )
            .all()
        )
        assert len(fwd_rows) == 1
        assert fwd_rows[0].source_ref == source_run_id

        # Reverse: given source_run_id, find all receiving run ids
        rev_rows = (
            session.query(RunProvenanceAudit)
            .filter(
                RunProvenanceAudit.owner_id == "alice",
                RunProvenanceAudit.source_ref == source_run_id,
            )
            .all()
        )
        receiving_run_ids = {r.run_id for r in rev_rows}
        assert receiving_run_ids == {receiving_run_1, receiving_run_2}
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


# ══════════════════════════════════════════════════════════════════════════════
# No-runner offline harness — silent no-op, never raises
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_observer_with_no_runner_is_silent_noop() -> None:
    """When ctx.runner is None (offline harness), the observer returns CONTINUE silently."""
    ctx = MagicMock()
    ctx.run_id = _run_id()
    ctx.runner = None  # no runner

    observer = ProvenanceAuditObserver()
    outcome = await observer.handle(
        _make_event(audit_operation="snapshot_commit"),
        ctx,
    )
    assert outcome.outcome == HOOK_CONTINUE


# ══════════════════════════════════════════════════════════════════════════════
# Record presence for every operation class (Requirement 19 AC 2)
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "operation",
    [
        "snapshot_commit",
        "recovery_commit",
        "fragment_merge",
        "merge_agent_commit",
        "restore",
    ],
)
async def test_each_audited_operation_class_writes_a_row(operation: str) -> None:
    """Every audited commit class produces exactly one row (Requirement 19 AC 2)."""
    session, engine = _make_db()
    try:
        store = _make_store(session)
        runner = _make_runner(store)
        run_id = _run_id()
        ctx = _make_ctx(runner, run_id)
        observer = ProvenanceAuditObserver()

        await observer.handle(
            _make_event(audit_operation=operation, commit_sha="1a2b3c4d"),
            ctx,
        )

        rows = _query_audit_rows(session, owner_id="alice", run_id=run_id)
        assert len(rows) == 1
        assert rows[0].operation == operation
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
