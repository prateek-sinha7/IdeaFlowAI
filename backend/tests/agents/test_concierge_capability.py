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
        """Owner-scoped fake: the bounded read returns rows only when owner matches."""

        def __init__(self, owner_id: str, rows_by_owner: dict[str, list]) -> None:
            self._owner_id = owner_id
            self._rows_by_owner = rows_by_owner

        async def read_events_of_types(self, run_id: str, types, *, limit: int,
                                       after_seq: int = 0) -> list:
            wanted = set(types)
            rows = self._rows_by_owner.get(self._owner_id, [])
            return [r for r in rows if r.type in wanted][-limit:]

    victim_rows = [SimpleNamespace(seq=1, type="chat_message",
                                   payload_json={"text": "secret"})]

    # Cross-owner: attacker store over the victim's data → nothing (default-deny).
    attacker_store = _DefaultDenyStore("attacker", {"victim": victim_rows})
    attacker_tools = ConciergeCapability._read_tools(attacker_store, "run-1")
    read_tool = next(t for t in attacker_tools if t.name == "read_recent_events")
    denied = asyncio.new_event_loop().run_until_complete(read_tool.ainvoke({}))
    assert denied == [], "cross-owner read leaked rows — IDOR scoping broken"

    # Same-owner: the victim's own store sees the rows (the tool DOES delegate).
    owner_store = _DefaultDenyStore("victim", {"victim": victim_rows})
    owner_tools = ConciergeCapability._read_tools(owner_store, "run-1")
    owner_read = next(t for t in owner_tools if t.name == "read_recent_events")
    seen = asyncio.new_event_loop().run_until_complete(owner_read.ainvoke({}))
    assert len(seen) == 1

    # No store / no run → no read tools (dormant).
    assert ConciergeCapability._read_tools(None, "run-1") == []
    assert ConciergeCapability._read_tools(owner_store, None) == []


def test_read_tools_serialize_rows_to_plain_dicts() -> None:
    """M2: read-tool output is plain dicts, never raw ORM ``<...object at 0x...>`` reprs.

    A raw SQLAlchemy row would reach the LIVE model as an opaque ``str()`` repr with no
    usable fields. The tool must project each row to a JSON-safe dict (datetimes → ISO
    strings; JSON columns already parsed) so the model gets a structured field map.
    """
    from datetime import datetime, timezone

    class _FakeRow:  # a plain object → str(obj) is an opaque ``<... object at 0x...>``
        def __init__(self) -> None:
            self.type = "chat_message"
            self.seq = 3
            self.payload_json = {"text": "hi"}
            self.created_at = datetime(2026, 7, 15, tzinfo=timezone.utc)

    class _Store:
        async def read_events_of_types(self, run_id: str, types, *, limit: int,
                                       after_seq: int = 0) -> list:
            return [_FakeRow()]

    tools = ConciergeCapability._read_tools(_Store(), "run-1")
    read_events_tool = next(t for t in tools if t.name == "read_recent_events")
    out = asyncio.new_event_loop().run_until_complete(read_events_tool.ainvoke({}))

    assert isinstance(out, list) and len(out) == 1
    assert isinstance(out[0], dict), "read tool must return plain dicts (M2), not raw rows"
    assert out[0]["type"] == "chat_message"
    assert out[0]["payload_json"] == {"text": "hi"}
    # datetime coerced to a JSON-safe ISO string, not a datetime object.
    assert out[0]["created_at"] == "2026-07-15T00:00:00+00:00"
    # No opaque ORM repr leaked into the tool output the model would receive.
    assert "object at 0x" not in str(out)


def test_compose_system_prompt_injects_compiled_chat_block() -> None:
    """M3: a ctx carrying a compiled with a ``chat`` block injects it into the prompt."""
    compiled = SimpleNamespace(chat={"suggestions": "Ask about the spec or the gate."})
    ctx = SimpleNamespace(conversation_context=None, compiled=compiled)
    prompt = ConciergeCapability._compose_system_prompt(ctx)
    assert "Ask about the spec or the gate." in prompt

    # Degrade-safe: no compiled at all → still a valid prompt, no crash, no block.
    bare = ConciergeCapability._compose_system_prompt(SimpleNamespace())
    assert isinstance(bare, str) and bare


def test_compose_system_prompt_injects_chain_hints_block() -> None:
    """c72: a ctx carrying non-empty ``chain_hints`` appends a GENERIC data block
    naming the labels; an empty/absent ``chain_hints`` is byte-identical (no block)."""
    ctx = SimpleNamespace(
        conversation_context=None,
        compiled=None,
        chain_hints=[
            {"id": "ppt", "label": "Presentation"},
            {"id": "prototype", "label": "Prototype"},
        ],
    )
    prompt = ConciergeCapability._compose_system_prompt(ctx)
    # The labels are reflected as inert data …
    assert "Presentation" in prompt
    assert "Prototype" in prompt
    # … under a generic chain/follow-up phrasing (no workflow-name branch).
    assert "chained into" in prompt or "follow-up" in prompt

    # Byte-identity of the no-hints path: absent vs empty-list == the same prompt,
    # with NO chain block appended.
    no_hints = ConciergeCapability._compose_system_prompt(
        SimpleNamespace(conversation_context=None, compiled=None)
    )
    empty_hints = ConciergeCapability._compose_system_prompt(
        SimpleNamespace(conversation_context=None, compiled=None, chain_hints=[])
    )
    assert no_hints == empty_hints
    assert "chained into" not in no_hints and "follow-up" not in no_hints


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
    # on_chunk=None is byte-behaviorally identical to today: the full concatenated text
    # equals the scripted turn's text (no delta was diverted / dropped).
    assert out == "Here is what I found in the run. "


def test_converse_streams_deltas_to_on_chunk_in_order() -> None:
    """With an ``on_chunk`` sink, converse emits ordered text deltas whose join == return.

    The scripted ``_stream`` yields multiple ``AIMessageChunk``s, so >1 delta is observed;
    order is preserved and the concatenation equals the returned full text. Proves the
    BE-1 streaming seam over the runner's ``astream_events`` (INV-13 — model via the
    adapter only), fully offline.
    """
    scripted = ScriptedFakeChatModel(
        [_ScriptedTurn(texts=["Hel", "lo, ", "world"], usage=(12, 6))]
    )

    class _NoopStore:
        async def read_events(self, run_id: str, after_seq: int) -> list:
            return []

    ctx = SimpleNamespace(
        model=scripted,
        scoped_store=_NoopStore(),
        run_id="run-stream",
        owner_id="owner-A",
        workspace_id="ws-A",
        conversation_context=None,
        compiled=None,
    )

    impl = ConciergeCapability()
    collected: list[str] = []
    out = asyncio.new_event_loop().run_until_complete(
        impl.converse(ctx, "hi", on_chunk=lambda d: collected.append(d))
    )
    # The join of the ordered deltas equals the returned full text (order preserved).
    assert "".join(collected) == out
    # More than one delta is observed (the scripted turn streams multiple chunks).
    assert len(collected) > 1
    # The full text is the concatenation of the scripted pieces.
    assert out == "Hello, world"


def test_converse_awaits_async_on_chunk_sink() -> None:
    """An async ``on_chunk`` (returns an awaitable) is awaited — the async queue sink path.

    Mirrors the BE-2 queue sink: the callback is a coroutine function; converse awaits its
    result (``inspect.isawaitable``) so every delta lands before the next is produced.
    """
    scripted = ScriptedFakeChatModel(
        [_ScriptedTurn(texts=["a", "b", "c"], usage=(3, 2))]
    )

    class _NoopStore:
        async def read_events(self, run_id: str, after_seq: int) -> list:
            return []

    ctx = SimpleNamespace(
        model=scripted,
        scoped_store=_NoopStore(),
        run_id="run-async",
        owner_id="owner-A",
        workspace_id="ws-A",
        conversation_context=None,
        compiled=None,
    )

    impl = ConciergeCapability()
    collected: list[str] = []

    async def _async_sink(delta: str) -> None:
        collected.append(delta)

    out = asyncio.new_event_loop().run_until_complete(
        impl.converse(ctx, "hi", on_chunk=_async_sink)
    )
    assert "".join(collected) == out == "abc"
    assert len(collected) > 1


# ── drain: converse surfaces proposals CTX-SCOPED (per-request), no self buffer ──


def _proposing_model(action: str) -> ScriptedFakeChatModel:
    """A scripted model that proposes ``action`` via a propose_gate_action tool call.

    Turn 1 emits the tool call; turn 2 (no tool calls) terminates the deep-agent loop.
    """
    import json

    return ScriptedFakeChatModel(
        [
            _ScriptedTurn(
                texts=[f"Considering {action}. "],
                tool_calls=[
                    ("propose_gate_action", json.dumps({"action": action}), f"c_{action}")
                ],
                usage=(10, 5),
            ),
            _ScriptedTurn(texts=[f"I suggest {action}."], usage=(8, 4)),
        ]
    )


class _NoopStore:
    async def read_events(self, run_id: str, after_seq: int) -> list:
        return []


def _concierge_ctx(model: ScriptedFakeChatModel, run_id: str, owner: str) -> SimpleNamespace:
    return SimpleNamespace(
        model=model,
        scoped_store=_NoopStore(),
        run_id=run_id,
        owner_id=owner,
        workspace_id=f"ws-{owner}",
        conversation_context=None,
        compiled=None,
    )


def test_converse_surfaces_proposals_on_ctx_and_second_drain_is_empty() -> None:
    """A converse whose model proposes a gate action surfaces it via the ctx-scoped drain.

    The proposal is captured on the PER-REQUEST ctx (not the singleton capability); a
    second drain of the same ctx returns [] (the buffer is cleared, no leak).
    """
    ctx = _concierge_ctx(_proposing_model("approve"), "run-drain", "owner-A")
    impl = ConciergeCapability()

    answer = asyncio.new_event_loop().run_until_complete(impl.converse(ctx, "should I approve?"))
    assert isinstance(answer, str)

    drained = ConciergeCapability.drain_proposals(ctx)
    assert len(drained) == 1
    assert drained[0].channel == "gate_action"
    assert drained[0].params["action"] == "approve"
    # A second drain of the same ctx returns [] — the buffer was cleared.
    assert ConciergeCapability.drain_proposals(ctx) == []


def test_no_self_scoped_proposal_buffer_on_capability() -> None:
    """CONCURRENCY guard: the capability holds NO instance-level proposal buffer.

    Proposals live only on the per-request ctx (or the converse return), so a shared
    singleton reused across concurrent requests cannot leak one request's proposals
    into another. A source assertion complements this at the grep level in the plan.
    """
    ctx = _concierge_ctx(_proposing_model("reject"), "run-x", "owner-X")
    impl = ConciergeCapability()
    asyncio.new_event_loop().run_until_complete(impl.converse(ctx, "reject?"))

    # No proposal state stored on the instance (only ctx carries it).
    assert not hasattr(impl, "_proposals")
    assert not hasattr(impl, "proposals")
    assert not getattr(impl, "__dict__", {}), "capability instance must hold no per-request state"


def test_overlapping_converse_calls_are_ctx_isolated() -> None:
    """CONCURRENCY: two interleaved converse calls on ONE singleton never cross-leak.

    ctx A proposes ``approve``; ctx B proposes ``reject``. Run under ``asyncio.gather``
    (interleaved at await points) against the SAME ConciergeCapability instance; each
    caller drains ONLY its own ctx's proposal, never the other's.
    """
    ctx_a = _concierge_ctx(_proposing_model("approve"), "run-A", "owner-A")
    ctx_b = _concierge_ctx(_proposing_model("reject"), "run-B", "owner-B")

    impl = ConciergeCapability()  # ONE shared/singleton instance reused across requests

    async def _run_both():
        return await asyncio.gather(
            impl.converse(ctx_a, "A: approve?"),
            impl.converse(ctx_b, "B: reject?"),
        )

    asyncio.new_event_loop().run_until_complete(_run_both())

    a = ConciergeCapability.drain_proposals(ctx_a)
    b = ConciergeCapability.drain_proposals(ctx_b)
    assert [p.params["action"] for p in a] == ["approve"], "ctx A leaked/lost proposals"
    assert [p.params["action"] for p in b] == ["reject"], "ctx B leaked/lost proposals"


# ── counting: the Concierge's OWN model spend must be observed (ISS-092) ─────────


def test_converse_accumulates_usage_across_turns() -> None:
    """ISS-092 (D1): converse SUMS the runner's per-turn ``usage`` onto the ctx.

    ``DeepAgentRunner`` emits one ``{"type":"usage", ...}`` event per model turn. A
    tool-calling Concierge takes several turns, so the drain must ACCUMULATE — an
    overwrite would report only the last turn and silently undercount. The totals ride
    the PER-REQUEST ctx (never the singleton capability), the same idiom as
    ``ctx.proposals``.
    """
    import json

    scripted = ScriptedFakeChatModel(
        [
            _ScriptedTurn(
                texts=["Checking. "],
                tool_calls=[("propose_gate_action", json.dumps({"action": "approve"}), "c1")],
                usage=(10, 5),
            ),
            _ScriptedTurn(texts=["Done."], usage=(7, 3)),
        ]
    )
    ctx = _concierge_ctx(scripted, "run-usage", "owner-A")

    impl = ConciergeCapability()
    asyncio.new_event_loop().run_until_complete(impl.converse(ctx, "should I approve?"))

    usage = getattr(ctx, "usage", None)
    assert isinstance(usage, dict), "converse must surface the model spend on the ctx"
    # SUMMED across both turns — not the last turn alone (10+7, 5+3).
    assert usage["input_tokens"] == 17, f"usage must SUM across turns, got {usage}"
    assert usage["output_tokens"] == 8, f"usage must SUM across turns, got {usage}"
    assert usage["cache_read_tokens"] == 0
    assert usage["cache_write_tokens"] == 0
    # The effective model is recorded alongside the counters so the cost site can
    # price the turn instead of falling back to a default profile id.
    assert usage.get("model_id"), "usage must carry the effective model id"


def test_converse_reports_zero_usage_rather_than_estimating() -> None:
    """A model turn that emits NO usage metadata reports zeros — never an estimate.

    The absolute rule for ISS-092: a token that was not OBSERVED is reported as
    unmeasured. Deriving a count from ``len(answer)`` would poison the cache-savings
    figures downstream (ISS-034), so the drain must leave the counters at 0.
    """
    scripted = ScriptedFakeChatModel([_ScriptedTurn(texts=["A long answer body."], usage=None)])
    ctx = _concierge_ctx(scripted, "run-nousage", "owner-A")

    impl = ConciergeCapability()
    answer = asyncio.new_event_loop().run_until_complete(impl.converse(ctx, "hi"))

    assert answer == "A long answer body."
    usage = getattr(ctx, "usage", None)
    assert isinstance(usage, dict)
    assert usage["input_tokens"] == 0 and usage["output_tokens"] == 0


# ════════════════════════════════════════════════════════════════════════════
# ISS-092 — the READ tools must be BOUNDED and fetched on demand
#
# Measured at HEAD against backend/dev.db: one Concierge question re-fed the model
# 9,227,107 chars ≈ 2,306,776 tokens, dominated by 18 ``agent_input`` rows totalling
# 7,290,638 chars (largest single row 479,605). On two runs a single chat read was
# 144% and 151% of everything the entire pipeline recorded. ``list_refs`` projected
# 5,804,067 chars of artifact bodies inline; ``get_ref`` returned bodies up to 389,651.
# ════════════════════════════════════════════════════════════════════════════

# The per-tool ceiling every read tool must respect, in CHARACTERS — the same unit
# ``compaction:chat_history`` bounds against. Deliberately far above every legitimate
# result and far below the megabyte payloads that caused ISS-092.
_TOOL_RESULT_CEILING = 25_000


class _BigRunStore:
    """A fake ScopedStore holding a PRODUCTION-SHAPED worst case (run ``0a27b397``).

    12,000 rows including one 480,000-char ``agent_input`` — the row class that
    actually caused the blowout — plus an oversized artifact body and an agent_outputs
    blob carrying full input prompts. Models the default-deny contract: it answers only
    for its own owner.
    """

    def __init__(self, owner_id: str = "victim", *, cross_run_ref: bool = False) -> None:
        self._owner_id = owner_id
        self.rows = self._build_rows()
        self.ref = SimpleNamespace(
            id="ref-1", run_id="other-run" if cross_run_ref else "run-1",
            kind="deliverable", producer_agent="build", version=3,
            content="X" * 400_000, visibility="private",
        )

    @staticmethod
    def _build_rows() -> list:
        rows = [
            SimpleNamespace(seq=1, type="pipeline_start", payload_json={"total": 6}),
            SimpleNamespace(seq=2, type="agent_start",
                            payload_json={"agent_id": "build", "name": "Build Agent",
                                          "role": "Prototype", "index": 0, "total": 6}),
            # The row class that caused ISS-092 — never reachable through any tool.
            SimpleNamespace(seq=3, type="agent_input", payload_json={"prompt": "P" * 480_000}),
            SimpleNamespace(seq=4, type="planner_complete", payload_json={"plan": "Q" * 380_000}),
            SimpleNamespace(seq=5, type="agent_complete",
                            payload_json={"agent_id": "build", "name": "Build Agent",
                                          "duration": 47.2, "output_length": 20985}),
            SimpleNamespace(seq=6, type="chat_message", payload_json={"text": "what happened?"}),
            SimpleNamespace(seq=7, type="chat_reply", payload_json={"text": "It built."}),
        ]
        rows += [SimpleNamespace(seq=8 + i, type="agent_chunk",
                                 payload_json={"chunk": "c" * 160}) for i in range(11_993)]
        return rows

    def _mine(self, rows: list) -> list:
        return rows if self._owner_id == "victim" else []

    async def read_events(self, run_id: str, after_seq: int = 0) -> list:
        return self._mine([r for r in self.rows if r.seq > after_seq])

    async def read_events_of_types(self, run_id: str, types, *, limit: int,
                                   after_seq: int = 0) -> list:
        wanted = set(types)
        hits = [r for r in self.rows if r.type in wanted and r.seq > after_seq]
        return self._mine(hits[-limit:] if limit else hits)

    async def list_refs(self, run_id: str, kind=None) -> list:
        return self._mine([self.ref])

    async def get_ref(self, ref_id: str):
        return self.ref if self._owner_id == "victim" else None

    async def read_gate_events(self, run_id: str) -> list:
        return self._mine([SimpleNamespace(id="g1", run_id="run-1", gate_key="review",
                                           decision="approve", detail="looks good")])

    async def get_run(self, run_id: str):
        if self._owner_id != "victim":
            return None
        import json as _json

        return SimpleNamespace(id="run-1", status="completed", agent_outputs=_json.dumps([
            # Each entry carries the FULL prompt as well as the output — 7.45M chars in
            # the worst real row. Only ``output`` may ever reach the model, truncated.
            {"agent_id": "build", "name": "Build Agent", "role": "Prototype",
             "input_prompt": "I" * 300_000, "output": "O" * 300_000, "duration": 47.2},
        ]))


def _args_for(tool, *, ref_id: str = "ref-1", agent_name: str = "build") -> dict:
    """Build a minimal valid argument dict for any read tool, old surface or new."""
    args: dict = {}
    for pname in (getattr(tool, "args", {}) or {}):
        if pname == "ref_id":
            args[pname] = ref_id
        elif pname == "agent_name":
            args[pname] = agent_name
        elif pname in ("kind", "types"):
            args[pname] = ""
    return args


def _invoke(tool, **over):
    return asyncio.new_event_loop().run_until_complete(
        tool.ainvoke(_args_for(tool) | over)
    )


def test_no_tool_returns_unbounded_event_history() -> None:
    """THE ISS-092 regression test: EVERY read tool is bounded on a worst-case run.

    Fails at HEAD, where ``read_events`` returns all 12,000 rows including the
    480,000-char ``agent_input`` — megabytes shipped to the model for one question.
    """
    store = _BigRunStore()
    tools = ConciergeCapability._read_tools(store, "run-1")
    assert tools, "the read surface must not be empty"

    oversized = []
    for tool in tools:
        size = len(str(_invoke(tool)))
        if size >= _TOOL_RESULT_CEILING:
            oversized.append(f"{tool.name}={size:,} chars")
    assert not oversized, (
        "unbounded read tool(s) — this is ISS-092: " + ", ".join(oversized)
    )


def test_read_tools_expose_only_the_bounded_allow_list() -> None:
    """INV-12 enforcement: the exact tool-name set, so a re-added unbounded tool fails CI.

    ``read_events`` / ``list_refs`` / ``get_ref`` are DELETED, not kept for
    compatibility — no tool may survive alongside its replacement.
    """
    names = {t.name for t in ConciergeCapability._read_tools(_BigRunStore(), "run-1")}
    assert names == {
        "get_run_progress", "list_agents", "get_agent_output",
        "list_artifacts", "get_artifact", "read_recent_events", "read_gate_history",
    }, f"unexpected Concierge read surface: {sorted(names)}"
    assert {"read_events", "list_refs", "get_ref"} & names == set(), (
        "a superseded unbounded tool is still exposed (INV-12: replace, do not shadow)"
    )


def test_read_recent_events_rejects_bulk_types() -> None:
    """The bulk row classes are not requestable — the allow-list is server-side.

    ``agent_input`` (7.29M chars in the measured run), ``agent_chunk``,
    ``planner_complete``, ``tool_call`` and ``tool_result`` can never be named into
    the result, however the model asks.
    """
    tools = ConciergeCapability._read_tools(_BigRunStore(), "run-1")
    tool = next(t for t in tools if t.name == "read_recent_events")

    out = _invoke(tool, types="agent_input,agent_chunk,planner_complete,tool_result")
    seen = {r.get("type") for r in out if isinstance(r, dict)}
    assert not (seen & {"agent_input", "agent_chunk", "planner_complete", "tool_result"}), (
        f"a bulk event type was reachable: {seen}"
    )
    # An honest empty result, not a silent fallback to everything.
    assert len(str(out)) < _TOOL_RESULT_CEILING

    # The default call still returns useful lifecycle rows (the tool is not inert).
    default = _invoke(tool)
    assert any(r.get("type") == "agent_complete" for r in default if isinstance(r, dict))


def test_read_recent_events_caps_limit_and_row_size() -> None:
    """A model-supplied ``limit`` cannot escape the cap, and each row is capped too."""
    tools = ConciergeCapability._read_tools(_BigRunStore(), "run-1")
    tool = next(t for t in tools if t.name == "read_recent_events")

    out = _invoke(tool, limit=100_000)
    assert len(out) <= 50, f"limit escaped its cap: {len(out)} rows"
    assert len(str(out)) < _TOOL_RESULT_CEILING


def test_get_artifact_truncates_and_flags() -> None:
    """A 400,000-char body comes back truncated, flagged, and honest about its real size."""
    tools = ConciergeCapability._read_tools(_BigRunStore(), "run-1")
    tool = next(t for t in tools if t.name == "get_artifact")

    out = _invoke(tool)
    assert out["truncated"] is True
    assert len(out["content"]) <= 12_000
    assert out["total_chars"] == 400_000, "must report the REAL size, not the truncated one"

    # A model-supplied max_chars cannot escape the hard cap.
    big = _invoke(tool, max_chars=999_999)
    assert len(big["content"]) <= 12_000


def test_get_artifact_denies_cross_run_ref() -> None:
    """A ref belonging to ANOTHER run of the same owner is refused.

    ``ScopedStore.get_ref`` filters owner + visibility but never ``run_id``, so a
    prompt-injected id inside untrusted run content could reach a different run's
    artifact body. The tool asserts the ref belongs to THIS run. Fails at HEAD.
    """
    tools = ConciergeCapability._read_tools(_BigRunStore(cross_run_ref=True), "run-1")
    tool = next(t for t in tools if t.name == "get_artifact")

    out = _invoke(tool)
    assert out == {} or not out.get("content"), (
        "cross-run artifact body leaked — run scoping is missing"
    )


def test_list_artifacts_omits_content() -> None:
    """Metadata only — artifact BODIES never ride the listing (5.8M chars in one run)."""
    tools = ConciergeCapability._read_tools(_BigRunStore(), "run-1")
    tool = next(t for t in tools if t.name == "list_artifacts")

    out = _invoke(tool)
    assert out and isinstance(out[0], dict)
    assert "content" not in out[0], "artifact body leaked into the listing"
    assert out[0]["content_chars"] == 400_000, "size is reported instead of the body"
    assert len(str(out)) < _TOOL_RESULT_CEILING


def test_get_agent_output_never_returns_the_input_prompt() -> None:
    """``workflow_runs.agent_outputs`` embeds full input prompts (7.45M chars worst case).

    Only the named agent's OUTPUT may reach the model, head-truncated and flagged.
    """
    tools = ConciergeCapability._read_tools(_BigRunStore(), "run-1")
    tool = next(t for t in tools if t.name == "get_agent_output")

    out = _invoke(tool)
    assert out["truncated"] is True
    assert len(out["text"]) <= 8_000
    assert "I" * 100 not in str(out), "the agent's INPUT PROMPT leaked to the model"
    assert out["total_chars"] == 300_000

    unknown = _invoke(tool, agent_name="no-such-agent")
    assert unknown.get("error"), "an unknown agent must be reported, not silently empty"


def test_list_agents_omits_output_text() -> None:
    """Per-agent status rows carry sizes and durations — never the output bodies."""
    tools = ConciergeCapability._read_tools(_BigRunStore(), "run-1")
    tool = next(t for t in tools if t.name == "list_agents")

    out = _invoke(tool)
    assert out and isinstance(out[0], dict)
    assert "output" not in out[0] and "text" not in out[0]
    assert out[0]["name"] == "Build Agent"
    assert len(str(out)) < _TOOL_RESULT_CEILING


def test_get_run_progress_returns_counts_not_rows() -> None:
    """The cheapest tool answers the commonest question with derived counts."""
    tools = ConciergeCapability._read_tools(_BigRunStore(), "run-1")
    tool = next(t for t in tools if t.name == "get_run_progress")

    out = _invoke(tool)
    assert out["agents_started"] == 1 and out["agents_completed"] == 1
    assert out["status"] == "completed"
    assert len(str(out)) < 1_000, "progress must be a summary, not a row dump"


def test_no_tool_accepts_a_run_id_argument() -> None:
    """The authorization invariant: ``run_id`` is a CLOSURE, never a tool parameter.

    That is precisely what leaves the model no syntax for naming another run. A tool
    that accepted run_id would move the scoping decision into model-controlled input.
    """
    for tool in ConciergeCapability._read_tools(_BigRunStore(), "run-1"):
        params = set(getattr(tool, "args", {}) or {})
        assert "run_id" not in params, (
            f"{tool.name} accepts a model-supplied run_id — scoping must stay a closure"
        )


def test_every_read_tool_denies_cross_owner() -> None:
    """Default-deny holds for the WHOLE new surface, not just the tool it was proven on."""
    attacker_tools = ConciergeCapability._read_tools(_BigRunStore("attacker"), "run-1")
    for tool in attacker_tools:
        out = _invoke(tool)
        assert not out or out == {} or out.get("error") or out.get("agents_started") == 0, (
            f"{tool.name} leaked data across owners: {str(out)[:200]}"
        )


# ── the model's ACTUAL tool surface + prompt, captured off the runner ────────────

_BOUND_TOOL_NAMES: list[str] = []
_SEEN_SYSTEM_PROMPTS: list[str] = []


def _render_content(content) -> str:  # noqa: ANN001
    """Flatten a message's content to its literal text.

    The Bedrock cache-points middleware rewrites the system message into a list of
    ``{"type": "text", "text": ...}`` blocks, so ``str(content)`` would yield a Python
    repr with escaped newlines — and a byte-verbatim assertion against it would compare
    the wrong bytes.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            b.get("text", "") if isinstance(b, dict) else str(b) for b in content
        )
    return str(content)


class _CapturingModel(ScriptedFakeChatModel):
    """Records the tool names actually bound to the model and the system prompt sent.

    ``bind_tools`` is where the deepagents graph hands the model its real surface, so
    this observes what the LIVE model would be offered — including any library built-in
    the adapter did not exclude. Module-level buffers keep the pydantic model unmodified.
    """

    def bind_tools(self, tools, **kwargs):  # noqa: ANN001, ANN003
        _BOUND_TOOL_NAMES.clear()
        _BOUND_TOOL_NAMES.extend(
            getattr(t, "name", None) or getattr(t, "__name__", str(t)) for t in (tools or [])
        )
        return self

    def _stream(self, messages, stop=None, run_manager=None, **kwargs):  # noqa: ANN001
        for m in messages or []:
            if m.__class__.__name__ == "SystemMessage" or getattr(m, "type", "") == "system":
                _SEEN_SYSTEM_PROMPTS.append(_render_content(m.content))
        return super()._stream(messages, stop=stop, run_manager=run_manager, **kwargs)


_FILESYSTEM_TOOLS = {
    "write_file", "edit_file", "read_file", "ls", "glob", "grep", "write_todos", "task",
}


def test_concierge_model_sees_no_filesystem_tools() -> None:
    """The Concierge's surface is read + propose only — as its own docstring claims.

    ``exclude_builtin_tools`` was never passed, so the adapter excluded only ``task``
    and the model was handed a filesystem WRITE surface (``write_file``, ``edit_file``)
    on an app REST path. Fails at HEAD, where all seven built-ins are present.
    """
    _BOUND_TOOL_NAMES.clear()
    ctx = _concierge_ctx(
        _CapturingModel([_ScriptedTurn(texts=["ok"], usage=(1, 1))]), "run-fs", "owner-A"
    )
    asyncio.new_event_loop().run_until_complete(ConciergeCapability().converse(ctx, "hi"))

    assert _BOUND_TOOL_NAMES, "no tools were bound — the capture seam did not fire"
    leaked = sorted(set(_BOUND_TOOL_NAMES) & _FILESYSTEM_TOOLS)
    assert not leaked, f"the Concierge model was handed filesystem/todo tools: {leaked}"
    # The proposal surface is untouched — this narrows tools, it does not remove them.
    assert "propose_revision" in _BOUND_TOOL_NAMES


def test_excluding_builtins_does_not_flip_the_xml_sanitizer() -> None:
    """Side-effect guard for ``exclude_builtin_tools=True``.

    ``DeepAgentRunner._sanitize_fabricated_xml`` is ``exclude_builtin_tools and not
    self.tools``. The Concierge ALWAYS has custom tools, so the flag must stay False and
    the output path must be unchanged. Asserted, not assumed.
    """
    from app.agents.deep_agent_runner import DeepAgentRunner

    runner = DeepAgentRunner(
        system_prompt="p",
        tools=ConciergeCapability._read_tools(_BigRunStore(), "run-1"),
        model=ScriptedFakeChatModel([_ScriptedTurn(texts=["x"], usage=(1, 1))]),
        exclude_builtin_tools=True,
    )
    assert runner._sanitize_fabricated_xml is False, (
        "excluding built-ins must not turn on the fabricated-XML sanitizer"
    )


# ── multi-turn coherence must survive the deletion of read_events ────────────────


class _ChatHistoryStore(_BigRunStore):
    """The worst-case run PLUS a long chat history, to prove multi-turn survives."""

    def __init__(self, turns: int = 10) -> None:
        super().__init__()
        base = max(r.seq for r in self.rows)
        # Each turn is padded so the whole transcript (~10 KB) EXCEEDS the 6,000-char
        # budget — otherwise compaction is a no-op and the test would not exercise the
        # keep-recent-verbatim / summarize-the-tail path it exists to prove.
        pad = "x" * 480
        for i in range(turns):
            self.rows.append(SimpleNamespace(
                seq=base + 1 + 2 * i, type="chat_message",
                payload_json={"text": f"user question number {i} {pad}"}))
            self.rows.append(SimpleNamespace(
                seq=base + 2 + 2 * i, type="chat_reply",
                payload_json={"text": f"assistant answer number {i} {pad}"}))


def test_conversation_context_reaches_the_concierge_prompt_byte_verbatim() -> None:
    """Deleting ``read_events`` must not kill multi-turn.

    The Concierge has NO checkpointer and never set ``conversation_context``, so today's
    cross-turn coherence comes SOLELY from ``read_events`` returning the chat rows inside
    the flood. The replacement is the already-registered ``context_provider:conversation``
    + ``compaction:chat_history`` (keep_recent=6 byte-verbatim, 6,000-char budget) — reused,
    not rebuilt (INV-12). The LAST 6 turns must appear byte-verbatim in the prompt the
    model actually receives, and the block must stay under budget.
    """
    _SEEN_SYSTEM_PROMPTS.clear()
    store = _ChatHistoryStore(turns=10)
    ctx = SimpleNamespace(
        model=_CapturingModel([_ScriptedTurn(texts=["ok"], usage=(1, 1))]),
        scoped_store=store, run_id="run-1", owner_id="owner-A", workspace_id="ws-A",
        compiled=None, current_spec_injects={"conversation"},
    )
    asyncio.new_event_loop().run_until_complete(
        ConciergeCapability().converse(ctx, "and what about the last one?")
    )

    assert _SEEN_SYSTEM_PROMPTS, "no system prompt reached the model"
    prompt = _SEEN_SYSTEM_PROMPTS[0]
    # The 6 most recent turns, byte-verbatim, in the prompt the model was given.
    for i in (7, 8, 9):
        assert f"user: user question number {i}" in prompt, f"turn {i} lost from the prompt"
        assert f"assistant: assistant answer number {i}" in prompt
    # The older tail is summarized away rather than dropped silently or dumped whole.
    assert "user question number 0" not in prompt
    assert "earlier turns summarized" in prompt

    # The block itself stays under the composed-context budget (the whole prompt also
    # carries the role/rules/tool blocks, so the budget is asserted on the block).
    block = ctx.conversation_context
    assert block in prompt, "the composed transcript did not reach the model's prompt"
    assert len(block) <= 6_000 + len("## Conversation\n\n"), (
        f"conversation block exceeded its budget: {len(block)}"
    )


def test_conversation_provider_stays_dormant_without_the_declared_inject() -> None:
    """The provider's self-gate is NOT relaxed — that gate is what protects the goldens.

    A ctx without ``current_spec_injects`` gets no conversation block, exactly as every
    pipeline agent does today.
    """
    _SEEN_SYSTEM_PROMPTS.clear()
    ctx = SimpleNamespace(
        model=_CapturingModel([_ScriptedTurn(texts=["ok"], usage=(1, 1))]),
        scoped_store=_ChatHistoryStore(turns=10), run_id="run-1",
        owner_id="owner-A", workspace_id="ws-A", compiled=None,
    )
    asyncio.new_event_loop().run_until_complete(ConciergeCapability().converse(ctx, "hi"))
    assert "## Conversation" not in _SEEN_SYSTEM_PROMPTS[0]


# ── the prompt may only name tools that exist ────────────────────────────────────

_TOOL_NAME_UNIVERSE = {
    # superseded — must never be named again
    "read_events", "list_refs", "get_ref", "read_gate_events",
    # current read surface
    "get_run_progress", "list_agents", "get_agent_output", "list_artifacts",
    "get_artifact", "read_recent_events", "read_gate_history",
    # proposal surface
    "propose_steering_note", "propose_revision", "propose_chain", "propose_gate_action",
}


def test_system_prompt_names_only_existing_tools() -> None:
    """Guards the exact bug this refactor invites: prompt says call X, X no longer exists.

    Every tool name the prompt mentions must be in the surface actually built, and every
    new read tool must be mentioned so the model can discover it.
    """
    import re

    prompt = ConciergeCapability._compose_system_prompt(
        SimpleNamespace(conversation_context=None, compiled=None,
                        run_summary="Run title: t", run_status="running")
    )
    built = {t.name for t in ConciergeCapability._read_tools(_BigRunStore(), "run-1")}
    built |= {"propose_steering_note", "propose_revision", "propose_chain",
              "propose_gate_action"}

    mentioned = {tok for tok in re.findall(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b", prompt)}
    stale = (mentioned & _TOOL_NAME_UNIVERSE) - built
    assert not stale, f"the prompt names tools that do not exist: {sorted(stale)}"

    missing = {"get_run_progress", "list_artifacts", "get_artifact"} - mentioned
    assert not missing, f"the prompt never tells the model about: {sorted(missing)}"
