"""Tests for the ``chat:concierge`` capability (D-05 / 33-02).

Offline-only (no live Bedrock): importing ``_scripted_model`` FIRST wires the
offline env (``RUNS_ROOT`` temp dir, InMemory checkpointer) and gives us the proven
scripted ``BaseChatModel`` recipe. The Concierge's model call is exercised by
injecting that fake model into the ``DeepAgentRunner`` verbatim-use path (a
``BaseChatModel`` instance is used as-is), so no network / no Bedrock is touched.

Covers:
  * resolve — ``registry.resolve("chat","concierge")`` returns the shared impl keyed
    on the DECLARED capability name (``.name == "concierge"``), never a workflow name;
  * proposal-only — each ``propose_*`` tool, invoked directly, returns a STRUCTURED
    intent (``channel`` + ``params``) and self-executes NOTHING: the three execution
    seams (``set_review_response`` / ``apply_steering`` / ``_mint_revision_row``) are
    spied and asserted NEVER invoked by the tool (T-33-02-02);
  * read-scoping — the READ tools go through an owner+workspace ``ScopedStore`` (the
    default-deny surface): ``_resolve_scoped_store`` constructs a real ``ScopedStore``
    from the run's owner_id + workspace_id, and a cross-owner read yields nothing
    (dormant/empty), proving IDOR → 404 scoping. The impl imports NO raw ORM
    (``app.models``) — the read path is the scoped store alone (T-33-02-01);
  * runner path — ``converse`` runs the scripted model THROUGH ``DeepAgentRunner``
    offline and returns a string (INV-13: the model is reached only via the adapter).

LIVE-DEFERRED (Phase-34, ``human_needed`` — NOT asserted here):
  * live Concierge Q&A against real Bedrock (grounded, non-hallucinated answers);
  * multi-turn prompt-cache-point placement across turns.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

# Import the offline harness FIRST — it sets RUNS_ROOT / ENV before app.core.config
# loads, and exposes the scripted BaseChatModel recipe (used verbatim by the runner).
from tests.agents._scripted_model import ScriptedFakeChatModel, _ScriptedTurn

from agents.authz import ScopedStore
from agents.capabilities import registry as registry_mod
from agents.capabilities.registry import CapabilityRegistry
from app.agents.chat import concierge as concierge_mod
from app.agents.chat.concierge import (
    ConciergeCapability,
    ProposalIntent,
    propose_gate_action,
    propose_revision,
    propose_steering_note,
)


# ── resolve ─────────────────────────────────────────────────────────────────────


def test_concierge_is_registered_and_resolves() -> None:
    registry_mod.discover()
    reg = CapabilityRegistry()
    assert reg.is_registered("chat", "concierge") is True
    impl = reg.resolve("chat", "concierge")
    assert impl.name == "concierge"
    # It runs a model → NOT user-grantable (D-02).
    assert reg.is_user_allowed("chat", "concierge") is False


# ── proposal-only: structured intents + NO side effect (T-33-02-02) ──────────────


def test_propose_tools_return_structured_intents() -> None:
    note = propose_steering_note.invoke({"note": "slow down on the schema"})
    assert isinstance(note, ProposalIntent)
    assert note.channel == "steering_note"
    assert note.params["note"] == "slow down on the schema"

    rev = propose_revision.invoke({"instruction": "tighten the copy", "target": "ref-1"})
    assert isinstance(rev, ProposalIntent)
    assert rev.channel == "revision"
    assert rev.params == {"instruction": "tighten the copy", "target": "ref-1"}

    gate = propose_gate_action.invoke({"action": "update_specs", "rationale": "gap"})
    assert isinstance(gate, ProposalIntent)
    assert gate.channel == "gate_action"
    # update_specs is in the allowed gate-action set (the consequential one).
    assert gate.params["action"] == "update_specs"

    # An out-of-range action degrades to an inert marker — still self-executes nothing.
    bad = propose_gate_action.invoke({"action": "rm -rf"})
    assert bad.channel == "gate_action"
    assert bad.params["action"] == "request_changes"


def test_propose_tools_invoke_no_execution_seam(monkeypatch: pytest.MonkeyPatch) -> None:
    """Proposal-only guard: no propose_* tool touches an execution seam.

    Spy the three consequential seams — the gate writer
    (``ArtifactStore.set_review_response``), the steering applier
    (``chat_router.apply_steering``), and the revision minter
    (``run_commands._mint_revision_row``) — and assert every ``propose_*`` tool
    returns its intent WITHOUT invoking any of them. The app layer (33-03) disposes
    the intent; the Concierge self-executes nothing.
    """
    import app.api.chat_router as chat_router
    import app.api.run_commands as run_commands
    from agents.artifact_store.store import ArtifactStore

    called: list[str] = []

    async def _spy_set_review_response(self, *a, **k):  # noqa: ANN001
        called.append("set_review_response")

    def _spy_apply_steering(*a, **k):
        called.append("apply_steering")

    def _spy_mint_revision_row(*a, **k):
        called.append("_mint_revision_row")

    monkeypatch.setattr(ArtifactStore, "set_review_response", _spy_set_review_response)
    monkeypatch.setattr(chat_router, "apply_steering", _spy_apply_steering)
    monkeypatch.setattr(run_commands, "_mint_revision_row", _spy_mint_revision_row)

    propose_steering_note.invoke({"note": "n"})
    propose_revision.invoke({"instruction": "i"})
    propose_gate_action.invoke({"action": "update_specs"})

    assert called == [], f"a propose_* tool invoked an execution seam: {called}"


# ── read-scoping: owner+workspace ScopedStore, IDOR → 404 (T-33-02-01) ───────────


def test_resolve_scoped_store_constructs_owner_scoped_store() -> None:
    """No ctx-provided store → a real ``ScopedStore`` built from owner + workspace."""
    ctx = SimpleNamespace(owner_id="owner-A", workspace_id="ws-A")
    store = ConciergeCapability._resolve_scoped_store(ctx)
    assert isinstance(store, ScopedStore)
    # The store carries the run's principal (the default-deny scope).
    assert store._owner_id == "owner-A"
    assert store._workspace_id == "ws-A"

    # No principal at all → no read surface (degrade-not-crash, never raw ORM).
    assert ConciergeCapability._resolve_scoped_store(SimpleNamespace()) is None


def test_read_tools_go_through_scoped_store_and_deny_cross_owner() -> None:
    """READ tools delegate to the scoped store; a cross-owner read yields nothing.

    A fake store models the ``ScopedStore`` default-deny contract: it returns rows
    only for its OWN owner. Built for the attacker principal over the victim's run,
    ``read_events`` returns ``[]`` — the IDOR → 404 proof, no raw ORM.
    """

    class _DefaultDenyStore:
        """Owner-scoped fake: read_events returns rows only when owner matches."""

        def __init__(self, owner_id: str, rows_by_owner: dict[str, list]) -> None:
            self._owner_id = owner_id
            self._rows_by_owner = rows_by_owner

        async def read_events(self, run_id: str, after_seq: int) -> list:
            return list(self._rows_by_owner.get(self._owner_id, []))

    victim_rows = [SimpleNamespace(type="chat_message", payload_json={"text": "secret"})]

    # Cross-owner: attacker store over the victim's data → nothing (default-deny).
    attacker_store = _DefaultDenyStore("attacker", {"victim": victim_rows})
    attacker_tools = ConciergeCapability._read_tools(attacker_store, "run-1")
    read_events_tool = next(t for t in attacker_tools if t.name == "read_events")
    denied = asyncio.new_event_loop().run_until_complete(read_events_tool.ainvoke({}))
    assert denied == [], "cross-owner read leaked rows — IDOR scoping broken"

    # Same-owner: the victim's own store sees the rows (the tool DOES delegate).
    owner_store = _DefaultDenyStore("victim", {"victim": victim_rows})
    owner_tools = ConciergeCapability._read_tools(owner_store, "run-1")
    owner_read = next(t for t in owner_tools if t.name == "read_events")
    seen = asyncio.new_event_loop().run_until_complete(owner_read.ainvoke({}))
    assert len(seen) == 1

    # No store / no run → no read tools (dormant).
    assert ConciergeCapability._read_tools(None, "run-1") == []
    assert ConciergeCapability._read_tools(owner_store, None) == []


def test_concierge_impl_imports_no_raw_orm() -> None:
    """The read path is the scoped store alone — no ``app.models`` raw-ORM import."""
    from pathlib import Path

    src = Path(concierge_mod.__file__).read_text(encoding="utf-8")
    assert "app.models" not in src, "concierge must read only via ScopedStore, not raw ORM"


# ── runner path: model reached ONLY via DeepAgentRunner, offline (INV-13) ────────


def test_converse_runs_scripted_model_through_runner_offline() -> None:
    """``converse`` streams a scripted model THROUGH ``DeepAgentRunner`` and returns text.

    The scripted ``BaseChatModel`` instance is used verbatim by the runner (no Bedrock).
    This proves the INV-13 seam works offline; grounded live Q&A is Phase-34 human_needed.
    """
    scripted = ScriptedFakeChatModel(
        [_ScriptedTurn(texts=["Here is what I found in the run. "], usage=(12, 6))]
    )

    class _NoopStore:
        async def read_events(self, run_id: str, after_seq: int) -> list:
            return []

    ctx = SimpleNamespace(
        model=scripted,
        scoped_store=_NoopStore(),
        run_id="run-xyz",
        owner_id="owner-A",
        workspace_id="ws-A",
        conversation_context="## Conversation\n\nuser: what happened?",
        compiled=None,
    )

    impl = ConciergeCapability()
    out = asyncio.new_event_loop().run_until_complete(impl.converse(ctx, "what happened?"))
    assert isinstance(out, str)
    assert out  # the scripted turn produced text
