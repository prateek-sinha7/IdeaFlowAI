"""tests/unit/api/test_concierge_proposal_channels.py — CHAT / D-05 (33-03, Wave 3),
disposal half.

``run_commands._dispose_concierge_proposal`` routes each ``propose_*`` intent through the
SAME Phase-29 seam the mechanical router uses (D-05, INV-12), with the seams SPIED:
``propose_steering_note`` → ``apply_steering``; ``propose_gate_action`` →
``store.set_review_response`` (request_changes reconciled to the seam's ``redo``);
``propose_revision`` → ``_mint_revision_row`` + ``_drive_revision_to_queue``. A
CONSEQUENTIAL proposal is HELD behind a confirm chip (emits ``concierge_proposal``, calls
NO seam until confirmed — T-33-03-01); a proposed gate resolution on a terminal run is
refused (KAN-100 fence), as is one on an unarmed gate (KAN-94).

Disposal is a pure function of its arguments — every collaborator arrives as a parameter
(``store``, ``art_store``, ``ectx``) or is patched on the module — so these need no
database and no HTTP. The ENDPOINT half, where ``POST /api/runs/{id}/messages`` drives
this branch for real and the H1 server-enforced confirm-hold is proven against durable
rows, lives in ``tests/integration/api/test_concierge_proposal_channels_api.py``.

The intents are built from the REAL 33-02 ``propose_*`` tools (their frozen channel/param
contract), so a drift in that contract fails here.
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from app.agents.chat.concierge import (
    ProposalIntent,
    propose_gate_action,
    propose_revision,
    propose_steering_note,
)
from app.api import run_commands as rc


# ════════════════════════════════════════════════════════════════════════════
# Unit — _dispose_concierge_proposal routes to the matching Phase-29 seam.
# ════════════════════════════════════════════════════════════════════════════
class _SpyArtStore:
    """A spy for the artifact store's gate seam + the KAN-94 armed-gate registry."""

    def __init__(self):
        self.review_calls: list[tuple] = []
        self._resume_events: dict = {}

    async def set_review_response(self, gate_key, **kwargs):
        self.review_calls.append((gate_key, kwargs))

    def arm(self, gate_key):
        self._resume_events[f"review:{gate_key}"] = asyncio.Event()

    def review_event_pending(self, gate_key: str) -> bool:
        # Mirror the real ArtifactStore.review_event_pending (IN-02): an armed but
        # not-yet-set review:{gate_key} event is a genuine pending pause (KAN-94).
        # ``_gate_is_pending`` reads this PUBLIC accessor (the private _resume_events
        # peek was closed); the fake must expose it too.
        event = self._resume_events.get(f"review:{gate_key}")
        return event is not None and not event.is_set()


class _SpyStore:
    """A spy for the ScopedStore append path (the concierge_proposal hold record)."""

    def __init__(self):
        self.appended: list[dict] = []

    async def append_event_next_seq(self, run_id, *, event_id, type, payload_json):
        self.appended.append(
            {"event_id": event_id, "type": type, "payload": payload_json}
        )
        return True, len(self.appended)


class _Ectx:
    def __init__(self):
        self.steering_notes: list = []


class _User:
    id = "u-1"


def _dispose(intent, **overrides):
    kwargs = dict(
        confirmed=False,
        store=_SpyStore(),
        art_store=_SpyArtStore(),
        run_id="run-1",
        message_id="m-1",
        current_user=_User(),
        # The caller's EFFECTIVE tier, forwarded to the revision entitlement gate
        # (Decision 3). Overridable per-test via `overrides` for the cases that
        # want to assert a proposal is DENIED on tier.
        caller_tier="enterprise",
        wr_status="running",
        wr_type="prototype",
        gate_key=None,
        ectx=None,
    )
    kwargs.update(overrides)
    return rc._dispose_concierge_proposal(intent, **kwargs), kwargs


class TestSteeringDisposal:
    @pytest.mark.asyncio
    async def test_steering_note_applies_immediately_via_apply_steering(self):
        ectx = _Ectx()
        store = _SpyStore()
        intent = propose_steering_note.func(note="prefer teal")
        coro, kw = _dispose(intent, ectx=ectx, store=store)
        res = await coro
        # 29-08 seam: appended to ectx.steering_notes; NOT held (non-consequential).
        assert ectx.steering_notes == [{"text": "prefer teal", "sticky": False}]
        assert res["disposed"] == "steering"
        assert (
            store.appended == []
        )  # no concierge_proposal for a non-consequential note

    @pytest.mark.asyncio
    async def test_steering_note_best_effort_without_ectx(self):
        # DEF-29-09-1: no live ectx handle today → best-effort no-op, must not raise.
        res = await _dispose(propose_steering_note.func(note="x"), ectx=None)[0]
        assert res["disposed"] == "steering"


class TestGateDisposal:
    @pytest.mark.asyncio
    async def test_confirmed_approve_calls_set_review_response(self):
        art = _SpyArtStore()
        gk = "run-1:agent"
        art.arm(gk)
        intent = propose_gate_action.func(action="approve")
        res = await _dispose(
            intent,
            confirmed=True,
            art_store=art,
            gate_key=gk,
            wr_status="waiting_for_user",
        )[0]
        assert res["disposed"] == "gate"
        assert len(art.review_calls) == 1
        gate_key, kwargs = art.review_calls[0]
        assert gate_key == gk and kwargs == {"approved": True}

    @pytest.mark.asyncio
    async def test_request_changes_reconciles_to_redo(self):
        # The concierge proposes `request_changes`; the seam names that `redo`.
        art = _SpyArtStore()
        gk = "run-1:agent"
        art.arm(gk)
        intent = propose_gate_action.func(action="request_changes", rationale="tighten")
        res = await _dispose(
            intent,
            confirmed=True,
            art_store=art,
            gate_key=gk,
            wr_status="waiting_for_user",
        )[0]
        assert res["action"] == "redo"
        gate_key, kwargs = art.review_calls[0]
        assert kwargs["action"] == "redo"
        assert kwargs["instructions"] == "tighten"

    @pytest.mark.asyncio
    async def test_update_specs_routes_to_kan101(self):
        art = _SpyArtStore()
        gk = "run-1:analyze"
        art.arm(gk)
        intent = propose_gate_action.func(action="update_specs", rationale="RPT")
        await _dispose(
            intent,
            confirmed=True,
            art_store=art,
            gate_key=gk,
            wr_status="waiting_for_user",
        )[0]
        _, kwargs = art.review_calls[0]
        assert kwargs["action"] == "update_specs"
        assert kwargs["instructions"] == "RPT"

    @pytest.mark.asyncio
    async def test_missing_gate_action_defaults_to_request_changes_not_approve(self):
        # M1: a gate intent with NO `action` key (e.g. a durable row missing it) must
        # degrade to request_changes (→ redo), NEVER silently approve.
        art = _SpyArtStore()
        gk = "run-1:agent"
        art.arm(gk)
        intent = ProposalIntent(channel="gate_action", params={})  # no "action" key
        res = await _dispose(
            intent,
            confirmed=True,
            art_store=art,
            gate_key=gk,
            wr_status="waiting_for_user",
        )[0]
        assert res["action"] == "redo"  # request_changes → redo (non-consequential)
        _, kwargs = art.review_calls[0]
        assert kwargs.get("action") == "redo"
        assert kwargs.get("approved") is False  # NEVER a silent approve

    @pytest.mark.asyncio
    async def test_terminal_run_gate_proposal_is_fenced(self):
        # KAN-100: a proposed gate resolution never resolves a stopped run.
        art = _SpyArtStore()
        with pytest.raises(HTTPException) as exc:
            await _dispose(
                propose_gate_action.func(action="approve"),
                confirmed=True,
                art_store=art,
                gate_key="run-1:a",
                wr_status="cancelled",
            )[0]
        assert exc.value.status_code == 409
        assert exc.value.detail["code"] == "pipeline_not_running"
        assert art.review_calls == []  # NO write past the fence

    @pytest.mark.asyncio
    async def test_unarmed_gate_proposal_is_fenced(self):
        # KAN-94: a gate no one is waiting on is not resolvable.
        art = _SpyArtStore()  # gate NOT armed
        with pytest.raises(HTTPException) as exc:
            await _dispose(
                propose_gate_action.func(action="approve"),
                confirmed=True,
                art_store=art,
                gate_key="run-1:a",
                wr_status="waiting_for_user",
            )[0]
        assert exc.value.status_code == 409
        assert art.review_calls == []


class TestRevisionDisposal:
    @pytest.mark.asyncio
    async def test_confirmed_revision_mints_and_drives(self, monkeypatch):
        minted: dict = {}
        driven: dict = {}

        def _fake_mint(
            db,
            *,
            user,
            caller_tier,
            parent_run_id,
            target_artifact_type,
            instruction,
            pipeline_run_id=None,
            extra_agent_count=0,
        ):
            minted.update(
                parent=parent_run_id,
                target=target_artifact_type,
                instruction=instruction,
                caller_tier=caller_tier,
                pipeline_run_id=pipeline_run_id,
            )
            return pipeline_run_id, f"{target_artifact_type}_revision"

        async def _fake_drive(**kwargs):
            driven.update(kwargs)

        monkeypatch.setattr(rc, "_get_db", lambda: _FakeDb())
        monkeypatch.setattr(rc, "_mint_revision_row", _fake_mint)
        monkeypatch.setattr(rc, "_drive_revision_to_queue", _fake_drive)
        # A ``prototype_output`` target routes through the tiered classifier, which is a
        # one-word Bedrock call. Stub it: the tier→pipeline mapping is that function's
        # own contract, while THIS test is about mint+drive routing. "small" is the tier
        # that maps back to prototype_output, so the target asserted below is the one the
        # intent actually requested.
        async def _fake_classify(instruction, parent_run_id, model_id=None):
            return "small"

        monkeypatch.setattr(rc, "_classify_revision_tier", _fake_classify)

        intent = propose_revision.func(
            instruction="bigger CTA", target="prototype_output"
        )
        res = await _dispose(
            intent,
            confirmed=True,
            wr_type="prototype",
            run_id="parent-1",
        )[0]
        assert res["disposed"] == "revision"
        # The child run id is ALLOCATED BY THE CALLER (it has to be: the cancel event and
        # the event queue are registered under it before the row is minted), so the id is
        # pushed INTO the mint as ``pipeline_run_id`` rather than handed back by it. What
        # matters is that one id is used consistently — a mismatch between the id the
        # caller reports, the id the row is minted under, and the id the driver streams
        # to would strand the run's events on a queue nobody reads.
        child_id = res["revision_run_id"]
        assert child_id
        assert minted == {
            "parent": "parent-1",
            "target": "prototype_output",
            "instruction": "bigger CTA",
            # The caller's EFFECTIVE tier reaches the mint's entitlement gate
            # (Decision 3) rather than being re-derived from the DB row.
            "caller_tier": "enterprise",
            "pipeline_run_id": child_id,
        }
        await asyncio.sleep(0)  # let the driver task start
        assert driven.get("parent_run_id") == "parent-1"
        assert driven.get("workflow_run_id") == child_id

    @pytest.mark.asyncio
    async def test_revision_target_defaults_from_run_type(self, monkeypatch):
        captured: dict = {}

        def _fake_mint(
            db,
            *,
            user,
            caller_tier,
            parent_run_id,
            target_artifact_type,
            instruction,
            pipeline_run_id=None,
            extra_agent_count=0,
        ):
            captured["target"] = target_artifact_type
            return pipeline_run_id, "x_revision"

        async def _fake_drive(**kwargs):
            return None

        monkeypatch.setattr(rc, "_get_db", lambda: _FakeDb())
        monkeypatch.setattr(rc, "_mint_revision_row", _fake_mint)
        monkeypatch.setattr(rc, "_drive_revision_to_queue", _fake_drive)

        intent = propose_revision.func(instruction="x")  # target=""
        await _dispose(intent, confirmed=True, wr_type="ppt", run_id="p")[0]
        assert captured["target"] == "ppt_output"


class _FakeDb:
    def close(self):
        pass


class TestConfirmChipHold:
    @pytest.mark.asyncio
    async def test_gate_proposal_held_when_unconfirmed(self):
        store = _SpyStore()
        art = _SpyArtStore()
        res = await _dispose(
            propose_gate_action.func(action="approve"),
            confirmed=False,
            store=store,
            art_store=art,
            gate_key="run-1:a",
        )[0]
        assert res["held"] is True
        # A concierge_proposal row is emitted; the seam is NOT called.
        assert len(store.appended) == 1
        row = store.appended[0]
        assert row["type"] == "concierge_proposal"
        assert row["payload"]["channel"] == "gate_action"
        assert row["payload"]["status"] == "pending"
        assert art.review_calls == []

    @pytest.mark.asyncio
    async def test_revision_proposal_held_when_unconfirmed(self, monkeypatch):
        minted = {"n": 0}

        def _fake_mint(*a, **k):
            minted["n"] += 1
            return "c", "t"

        monkeypatch.setattr(rc, "_mint_revision_row", _fake_mint)
        store = _SpyStore()
        res = await _dispose(
            propose_revision.func(instruction="v2"),
            confirmed=False,
            store=store,
        )[0]
        assert res["held"] is True
        assert store.appended[0]["type"] == "concierge_proposal"
        assert minted["n"] == 0  # NOT executed until confirmed

