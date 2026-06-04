"""Phase 7b — FROZEN characterization of the free-chat WS event contract.

This is the **contract-locking regression net** for the chat-subsystem migration
(specs/002-deepagents-migration/plan.md §5 "Phase 7", tasks "7b task 8" + "7b task 12").

The free-chat path (``user_message`` WS → the chat sequencer's ``astream_execute``)
runs a multi-phase generator (Discovery → Requirements →
UserStories/PPT/Prototype/UIDesign → Preview) and emits a precise WebSocket event
vocabulary the frontend chat bubble consumes:

    phase_start{phase,name}  →  stream{chunk,section}*  →  phase_end{phase}   (per active phase)
    [error{error,code,recoverable,phase}  if a phase raises — pipeline continues]
    complete{<FinalOutputModel: 10 keys>}                                     (trailing, once)

Every event is the ``StreamMessageModel`` shape ``{type, chunk, section, data}``.

The golden was originally captured from the **legacy** ``AgentOrchestrator`` (7b-1).
In 7b-5 the legacy stack was DELETED and this characterization was repointed at the
live ``app.agents.chat_runner.ChatRunner`` (the dedicated free-chat sequencer on the
deepagents runtime): the FROZEN golden literals are **UNCHANGED**, and the assertions
now prove ``ChatRunner`` reproduces the legacy contract byte-for-byte — the
byte-faithful migration proof.

This test:
  1. drives ``ChatRunner.astream_execute`` with **mocked runners** (each chat agent's
     ``.astream`` yields a fixed per-agent text — no network / no Bedrock / no graph),
     so the real ``_parse_output_selection`` / ``_determine_active_phases`` /
     ``_compile_final_output`` / event-emission code runs deterministically;
  2. captures the FULL ordered event stream and asserts it byte-for-byte against the
     **inlined frozen golden** (``GOLDEN_*``).

────────────────────────────────────────────────────────────────────────────────────
HOW THE GOLDEN STAYS FROZEN (survives deleting the legacy orchestrator in 7b-5)
────────────────────────────────────────────────────────────────────────────────────
``GOLDEN_*`` is a **pure Python literal** with ZERO imports from the deleted legacy
stack. The factory builds a ``ChatRunner`` and never touches ``AgentOrchestrator`` /
``BaseAgent``. So:

  * the module imports fine now that ``app/agents/orchestrator.py`` is deleted;
  * the ``tests/unit`` tree carries NO module-level ``BaseAgent``/``AgentOrchestrator``
    reference (so 7b-5's widened ``test_no_baseagent.py`` over the whole tree stays green);
  * the golden remains the single source of truth — the migration is proven byte-faithful
    by re-running these exact assertions against ``ChatRunner``.

────────────────────────────────────────────────────────────────────────────────────
THE MOCK SEAM (determinism)
────────────────────────────────────────────────────────────────────────────────────
``ChatRunner.__init__`` calls ``agents.factory.create_runner("chat-<x>", ctx)`` for each
of the 7 chat agents. We patch ``create_runner`` to return a recording stub whose
``.astream`` yields scripted text (the validated 7b-3 pattern — see
``tests/unit/test_chat_runner.py``), so the real sequencer runs with no network. The
orchestrator-attr → chat-id mapping (``discovery_agent`` → ``chat-discovery`` etc.) is
``_CHAT_ID``. Determinism guarantees:
  * each agent yields its text as exactly TWO chunks (``_split_two``) — proves the
    sequencer accumulates ``"".join(parts)`` AND emits one ``stream`` per chunk;
  * the discovery text is crafted so ``_parse_output_selection`` deterministically picks
    a KNOWN selection per scenario (keyword-driven, ported verbatim into ``ChatRunner``);
  * JSON-bearing phases (4/5/7) yield valid JSON so ``json.loads`` succeeds and the
    parsed object lands verbatim in ``complete.data`` (non-JSON phases wrap as
    ``{"output": text}``) — both branches are asserted.
"""

from __future__ import annotations

import inspect
from typing import Any, AsyncIterator, Callable
from unittest.mock import patch

import pytest

# ─────────────────────────────────────────────────────────────────────────────
# Deterministic per-agent text (the "scripted LLM").
#
# The discovery TEXT is scenario-specific (it drives _parse_output_selection); the
# other six are fixed. JSON-bearing phases (ppt=4, prototype=5, preview/ui_preview=7)
# carry valid JSON so json.loads succeeds in the orchestrator.
# ─────────────────────────────────────────────────────────────────────────────

# Non-discovery agent texts (stable across all scenarios).
REQUIREMENTS_TEXT = "REQUIREMENTS: project overview and functional requirements."
USER_STORIES_TEXT = "# Personas\n\n# Epic: Core [P0]\n## Story: Login"
PPT_TEXT = '{"slides": [{"title": "Intro"}]}'
PROTOTYPE_TEXT = '{"pages": [{"name": "Home", "route": "/"}]}'
UI_DESIGN_TEXT = "Design tokens: primary #001f3f, secondary #FFFFFF."
PREVIEW_TEXT = '{"previews": ["user_stories", "prototype"]}'

# Discovery texts engineered to drive _parse_output_selection deterministically.
#   "all"   → "generate all" / "i'll generate: all"        → ALL four outputs
#   subset  → mention only "user stor" + "prototype"        → [user_stories, prototype]
#   default → no recognised keyword                         → defaults to ALL four
DISCOVERY_ALL_TEXT = (
    "Thanks for the detail. Based on our discussion, I'll generate: All deliverables "
    "(user stories, ppt, prototype, ui design)."
)
DISCOVERY_SUBSET_TEXT = (
    "Got it. Based on our discussion, I'll generate: User Stories and a Prototype."
)


def _agent_texts(discovery_text: str) -> dict[str, str]:
    """Map orchestrator agent-attribute names → their fixed streamed text."""
    return {
        "discovery_agent": discovery_text,
        "requirements_agent": REQUIREMENTS_TEXT,
        "user_story_agent": USER_STORIES_TEXT,
        "ppt_agent": PPT_TEXT,
        "prototype_agent": PROTOTYPE_TEXT,
        "ui_design_agent": UI_DESIGN_TEXT,
        "preview_agent": PREVIEW_TEXT,
    }


def _split_two(text: str) -> list[str]:
    """Split text into exactly two non-trivial chunks (proves chunk accumulation).

    A single-char text still yields two parts ("" + char) but our fixtures are all
    long, so both chunks are non-empty. The orchestrator joins parts for the section
    output and emits one ``stream`` event per chunk.
    """
    mid = max(1, len(text) // 2)
    return [text[:mid], text[mid:]]


# ─────────────────────────────────────────────────────────────────────────────
# Runner factory protocol.
#
# A "runner factory" is a callable that returns an object exposing
# ``astream_execute(user_message, *, mode, mode_prompt) -> AsyncIterator[dict]``.
# The factory builds a ``ChatRunner`` whose 7 chat agents stream the same fixed
# per-agent text, and the SAME frozen golden proves byte-fidelity.
# ``collect_events`` consumes whatever the factory yields.
# ─────────────────────────────────────────────────────────────────────────────

# Maps the legacy orchestrator agent-attribute names (the keys of ``_agent_texts``)
# to the chat AGENT.md ids the ``ChatRunner`` builds via ``create_runner``. This is
# the orchestrator-attr → chat-id mapping the migration preserves (the golden's
# event SHAPE is keyed on the section, which both runtimes derive identically).
_CHAT_ID: dict[str, str] = {
    "discovery_agent": "chat-discovery",
    "requirements_agent": "chat-requirements",
    "user_story_agent": "chat-user-stories",
    "ppt_agent": "chat-ppt",
    "prototype_agent": "chat-prototype",
    "ui_design_agent": "chat-ui-design",
    "preview_agent": "chat-preview",
}


class _StubRunner:
    """Minimal stand-in for a text-only ``DeepAgentRunner`` (no model / no graph).

    ``ChatRunner`` calls ``.astream(message)`` (a single message string); this stub
    yields the scripted text as exactly two chunks via the shared ``_split_two`` (so
    the golden's ``_phase_block`` chunking is reproduced byte-for-byte), or raises
    before yielding to drive the phase-failure scenario.
    """

    def __init__(self, text: str, *, raises: BaseException | None = None) -> None:
        self._text = text
        self._raises = raises

    async def astream(self, message: str) -> AsyncIterator[str]:
        if self._raises is not None:
            raise self._raises
            yield ""  # pragma: no cover — makes this an async generator
        for part in _split_two(self._text):
            yield part


def _chatrunner_factory(
    *,
    discovery_text: str,
    failing_agent: str | None = None,
    failure_exc: BaseException | None = None,
):
    """Build the live ``ChatRunner`` with each chat agent's runner mocked.

    Imports are LAZY (inside the function) so this module carries no module-level
    ``ChatRunner`` reference and stays free of any ``BaseAgent``/``AgentOrchestrator``
    token — keeping 7b-5's widened ``test_no_baseagent.py`` green.

    Patches ``agents.factory.create_runner`` (the seam ``ChatRunner.__init__`` uses to
    build its 7 text-only ``DeepAgentRunner``s) so each ``create_runner("chat-<x>", …)``
    returns a deterministic ``_StubRunner`` instead of constructing a real graph — the
    validated 7b-3 pattern. ``failing_agent`` is the legacy orchestrator attr name
    (e.g. ``"requirements_agent"``); it is translated to its chat id via ``_CHAT_ID``.
    """
    # Lazy, function-local imports — see module docstring (no module-level legacy/chat token).
    from app.agents.chat_runner import ChatRunner

    texts = _agent_texts(discovery_text)
    # chat-id → (text, raises) for each of the 7 agents.
    failing_chat_id = _CHAT_ID.get(failing_agent) if failing_agent else None
    by_chat_id: dict[str, _StubRunner] = {}
    for attr, text in texts.items():
        chat_id = _CHAT_ID[attr]
        raises = failure_exc if (chat_id == failing_chat_id and failure_exc) else None
        by_chat_id[chat_id] = _StubRunner(text, raises=raises)

    def _create_runner(agent_id: str, ctx, **kwargs) -> _StubRunner:
        return by_chat_id[agent_id]

    with patch("agents.factory.create_runner", side_effect=_create_runner):
        return ChatRunner()


async def collect_events(
    runner_factory: Callable[[], Any],
    *,
    message: str,
    mode: str,
    mode_prompt: str,
) -> list[dict]:
    """Drive a runner's ``astream_execute`` and return the full ordered event list.

    Provider-agnostic: ``runner_factory()`` may build the legacy orchestrator (now)
    or a ``ChatRunner`` (7b-6). The returned dicts are the raw WS payloads
    (``{type, chunk, section, data}``) in emission order.
    """
    runner = runner_factory()
    events: list[dict] = []
    async for event in runner.astream_execute(
        message, mode=mode, mode_prompt=mode_prompt
    ):
        events.append(event)
    return events


# ─────────────────────────────────────────────────────────────────────────────
# Normalisation: reduce a raw event to the FROZEN-ASSERTED shape.
#
# We assert the full (type, section, data) of every non-stream event, and for
# ``stream`` events we assert (type, section, chunk-text) — i.e. that ``stream``
# carries the chunk and the rest of the shape is fixed. This is exactly the
# contract the migration must reproduce; chunking is fixed by our scripted model.
# ─────────────────────────────────────────────────────────────────────────────


def _normalise(event: dict) -> dict:
    """Project a raw WS event onto the frozen-comparable shape.

    * ``stream`` → ``{"type","section","chunk"}`` (chunk text is load-bearing; ``data`` is
      always ``None`` for stream, asserted separately by ``test_stream_shape_invariant``).
    * everything else → ``{"type","section","data"}`` (``chunk`` is always ``None``).
    """
    if event["type"] == "stream":
        return {"type": "stream", "section": event["section"], "chunk": event["chunk"]}
    return {"type": event["type"], "section": event["section"], "data": event["data"]}


def _normalise_all(events: list[dict]) -> list[dict]:
    return [_normalise(e) for e in events]


# ═════════════════════════════════════════════════════════════════════════════
# THE FROZEN GOLDEN — single source of truth (pure literals, zero legacy imports).
#
# Each entry is the normalised event. The ``complete.data`` dict is the full
# 10-key FinalOutputModel.model_dump(). Captured from the REAL legacy orchestrator
# (verified by the tests below). Any drift — by the legacy now or the ChatRunner in
# 7b-6 — fails the assertion.
# ═════════════════════════════════════════════════════════════════════════════

# Reusable per-section phase blocks (phase_start → 2×stream → phase_end).
def _phase_block(section: str, phase: int, name: str, text: str) -> list[dict]:
    c1, c2 = _split_two(text)
    return [
        {"type": "phase_start", "section": section, "data": {"phase": phase, "name": name}},
        {"type": "stream", "section": section, "chunk": c1},
        {"type": "stream", "section": section, "chunk": c2},
        {"type": "phase_end", "section": section, "data": {"phase": phase}},
    ]


# ── Scenario (a): discovery selects ALL outputs ──────────────────────────────
GOLDEN_ALL: list[dict] = (
    _phase_block("discovery", 0, "Discovery", DISCOVERY_ALL_TEXT)
    + _phase_block("requirements", 1, "Requirements", REQUIREMENTS_TEXT)
    + _phase_block("user_stories", 3, "user_stories", USER_STORIES_TEXT)
    + _phase_block("ppt", 4, "ppt", PPT_TEXT)
    + _phase_block("prototype", 5, "prototype", PROTOTYPE_TEXT)
    + _phase_block("ui_design", 6, "ui_design", UI_DESIGN_TEXT)
    + _phase_block("ui_preview", 7, "ui_preview", PREVIEW_TEXT)
    + [
        {
            "type": "complete",
            "section": None,
            "data": {
                "auth": None,
                "realtime": None,
                "dashboard": None,
                "discovery": {"output": DISCOVERY_ALL_TEXT},
                "requirements": {"output": REQUIREMENTS_TEXT},
                "user_stories": {"output": USER_STORIES_TEXT},
                # phases 4/5/7 are JSON-parsed → the parsed object lands verbatim
                "ppt": {"slides": [{"title": "Intro"}]},
                "prototype": {"pages": [{"name": "Home", "route": "/"}]},
                "ui_design": {"output": UI_DESIGN_TEXT},
                "ui_preview": {"previews": ["user_stories", "prototype"]},
            },
        }
    ]
)

# ── Scenario (b): discovery selects a SUBSET (user_stories + prototype) ───────
# Proves _parse_output_selection + _determine_active_phases branching: ppt(4) and
# ui_design(6) are SKIPPED; ui_preview(7) always runs; skipped sections become
# {"status":"skipped","value":None} in complete.data.
GOLDEN_SUBSET: list[dict] = (
    _phase_block("discovery", 0, "Discovery", DISCOVERY_SUBSET_TEXT)
    + _phase_block("requirements", 1, "Requirements", REQUIREMENTS_TEXT)
    + _phase_block("user_stories", 3, "user_stories", USER_STORIES_TEXT)
    + _phase_block("prototype", 5, "prototype", PROTOTYPE_TEXT)
    + _phase_block("ui_preview", 7, "ui_preview", PREVIEW_TEXT)
    + [
        {
            "type": "complete",
            "section": None,
            "data": {
                "auth": None,
                "realtime": None,
                "dashboard": None,
                "discovery": {"output": DISCOVERY_SUBSET_TEXT},
                "requirements": {"output": REQUIREMENTS_TEXT},
                "user_stories": {"output": USER_STORIES_TEXT},
                "ppt": {"status": "skipped", "value": None},
                "prototype": {"pages": [{"name": "Home", "route": "/"}]},
                "ui_design": {"status": "skipped", "value": None},
                "ui_preview": {"previews": ["user_stories", "prototype"]},
            },
        }
    ]
)

# ── Scenario (c): non-default mode (``thinking``) ────────────────────────────
# Same event SHAPE as ALL-selection (the mode threads into agent context, not the
# event vocabulary). The mode's *influence* is asserted separately
# (test_mode_prompt_threaded_into_agent_context) — the contract is mode-invariant.
GOLDEN_THINKING_MODE = GOLDEN_ALL

# ── Scenario (d): a phase fails mid-pipeline (requirements raises) ────────────
# Discovery selects the SUBSET; the Requirements agent raises a generic exception.
# Contract: an ``error`` event (shape {error,code,recoverable,phase}) is emitted
# BETWEEN that phase's phase_start and phase_end, NO ``stream`` event fires for the
# failed phase, the pipeline CONTINUES, and complete.data carries
# requirements={"status":"failed","error":<str(exc)>}.
_FAILURE_MESSAGE = "scripted requirements failure"
GOLDEN_FAILURE: list[dict] = (
    _phase_block("discovery", 0, "Discovery", DISCOVERY_SUBSET_TEXT)
    + [
        {"type": "phase_start", "section": "requirements", "data": {"phase": 1, "name": "Requirements"}},
        {
            "type": "error",
            "section": "requirements",
            "data": {
                # generic (non-botocore) exception → internal_error / recoverable
                "error": "Something went wrong. Please try again.",
                "code": "internal_error",
                "recoverable": True,
                "phase": 1,
            },
        },
        {"type": "phase_end", "section": "requirements", "data": {"phase": 1}},
    ]
    + _phase_block("user_stories", 3, "user_stories", USER_STORIES_TEXT)
    + _phase_block("prototype", 5, "prototype", PROTOTYPE_TEXT)
    + _phase_block("ui_preview", 7, "ui_preview", PREVIEW_TEXT)
    + [
        {
            "type": "complete",
            "section": None,
            "data": {
                "auth": None,
                "realtime": None,
                "dashboard": None,
                "discovery": {"output": DISCOVERY_SUBSET_TEXT},
                "requirements": {"status": "failed", "error": _FAILURE_MESSAGE},
                "user_stories": {"output": USER_STORIES_TEXT},
                "ppt": {"status": "skipped", "value": None},
                "prototype": {"pages": [{"name": "Home", "route": "/"}]},
                "ui_design": {"status": "skipped", "value": None},
                "ui_preview": {"previews": ["user_stories", "prototype"]},
            },
        }
    ]
)


# ═════════════════════════════════════════════════════════════════════════════
# FACTORIES — the migration seam.
#
# 7b-5 deleted the legacy orchestrator and flipped this from the ``"legacy"`` factory
# to the ``"chatrunner"`` factory: every parametrized test below now runs against the
# live ``ChatRunner``, asserting the UNCHANGED frozen golden — the byte-faithful proof
# that ``ChatRunner`` reproduces the legacy contract. Keeping the id in the params makes
# a failure say which runtime drifted.
# ═════════════════════════════════════════════════════════════════════════════

CHATRUNNER_FACTORY = _chatrunner_factory

FACTORY_IDS = ["chatrunner"]
_FACTORY_BUILDERS: dict[str, Callable[..., Any]] = {"chatrunner": _chatrunner_factory}


def _build_factory(factory_id: str, **kwargs) -> Callable[[], Any]:
    """Return a zero-arg ``runner_factory`` for ``collect_events`` from a builder id."""
    builder = _FACTORY_BUILDERS[factory_id]
    return lambda: builder(**kwargs)


# ═════════════════════════════════════════════════════════════════════════════
# TESTS — assert each scenario's full ordered event stream against the frozen golden.
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
@pytest.mark.parametrize("factory_id", FACTORY_IDS)
async def test_contract_all_outputs(factory_id: str) -> None:
    """(a) Discovery selects ALL → every phase (0,1,3,4,5,6,7) emits the full block."""
    factory = _build_factory(factory_id, discovery_text=DISCOVERY_ALL_TEXT)
    events = await collect_events(
        factory, message="Build me a full product", mode="default", mode_prompt=""
    )
    assert _normalise_all(events) == GOLDEN_ALL


@pytest.mark.asyncio
@pytest.mark.parametrize("factory_id", FACTORY_IDS)
async def test_contract_subset_outputs(factory_id: str) -> None:
    """(b) Discovery selects user_stories + prototype → ppt/ui_design SKIPPED.

    Locks the ``_parse_output_selection`` keyword parse + ``_determine_active_phases``
    branching + the ``{"status":"skipped"}`` sentinel for omitted sections.
    """
    factory = _build_factory(factory_id, discovery_text=DISCOVERY_SUBSET_TEXT)
    events = await collect_events(
        factory, message="I want stories and a prototype", mode="default", mode_prompt=""
    )
    assert _normalise_all(events) == GOLDEN_SUBSET


@pytest.mark.asyncio
@pytest.mark.parametrize("factory_id", FACTORY_IDS)
async def test_contract_thinking_mode(factory_id: str) -> None:
    """(c) A non-default mode (``thinking``) emits the SAME event contract.

    The mode_prompt influences agent behaviour (asserted in
    ``test_mode_prompt_threaded_into_agent_context``) but does NOT alter the WS
    event vocabulary — the contract is mode-invariant.
    """
    from app.agents.modes import get_mode_prompt

    mode_prompt = get_mode_prompt("thinking")
    assert mode_prompt and mode_prompt.startswith("You are in deep thinking mode")

    factory = _build_factory(factory_id, discovery_text=DISCOVERY_ALL_TEXT)
    events = await collect_events(
        factory, message="Explain and build", mode="thinking", mode_prompt=mode_prompt
    )
    assert _normalise_all(events) == GOLDEN_THINKING_MODE


@pytest.mark.asyncio
@pytest.mark.parametrize("factory_id", FACTORY_IDS)
async def test_contract_phase_failure(factory_id: str) -> None:
    """(d) A phase that raises emits ``error`` + continues; ``complete`` records failure.

    The Requirements agent raises a generic exception → ``map_exception`` →
    internal_error/recoverable; the ``error`` event sits between phase_start and
    phase_end (no ``stream`` for the failed phase); later phases still run; the failed
    section is ``{"status":"failed","error":<str(exc)>}`` in ``complete.data``.
    """
    factory = _build_factory(
        factory_id,
        discovery_text=DISCOVERY_SUBSET_TEXT,
        failing_agent="requirements_agent",
        failure_exc=RuntimeError(_FAILURE_MESSAGE),
    )
    events = await collect_events(
        factory, message="stories and prototype please", mode="default", mode_prompt=""
    )
    assert _normalise_all(events) == GOLDEN_FAILURE


# ═════════════════════════════════════════════════════════════════════════════
# STRUCTURAL INVARIANTS — assert the contract's shape rules directly (not just
# the data). These are migration-critical: drift here silently routes chat
# messages into the FE *pipeline* handler.
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
@pytest.mark.parametrize("factory_id", FACTORY_IDS)
async def test_event_shape_is_stream_message_model(factory_id: str) -> None:
    """Every event has exactly the ``{type, chunk, section, data}`` keys (StreamMessageModel)."""
    factory = _build_factory(factory_id, discovery_text=DISCOVERY_ALL_TEXT)
    events = await collect_events(
        factory, message="x", mode="default", mode_prompt=""
    )
    assert events, "expected a non-empty event stream"
    for ev in events:
        assert set(ev.keys()) == {"type", "chunk", "section", "data"}, ev


@pytest.mark.asyncio
@pytest.mark.parametrize("factory_id", FACTORY_IDS)
async def test_stream_shape_invariant(factory_id: str) -> None:
    """``stream`` events carry chunk text with ``data is None``; non-stream have ``chunk is None``."""
    factory = _build_factory(factory_id, discovery_text=DISCOVERY_ALL_TEXT)
    events = await collect_events(
        factory, message="x", mode="default", mode_prompt=""
    )
    for ev in events:
        if ev["type"] == "stream":
            assert ev["chunk"] is not None and ev["chunk"] != ""
            assert ev["data"] is None
        else:
            assert ev["chunk"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("factory_id", FACTORY_IDS)
async def test_phase_envelope_ordering(factory_id: str) -> None:
    """Each section's events are bracketed: phase_start … phase_end, in active-phase order.

    Asserts: exactly one phase_start/phase_end per section; every ``stream`` and
    ``error`` for a section falls strictly between that section's start and end; and
    ``complete`` is the single trailing event.
    """
    factory = _build_factory(factory_id, discovery_text=DISCOVERY_ALL_TEXT)
    events = await collect_events(
        factory, message="x", mode="default", mode_prompt=""
    )

    # complete is last and unique.
    assert events[-1]["type"] == "complete"
    assert sum(1 for e in events if e["type"] == "complete") == 1

    # Walk the envelope: track the currently-open section.
    open_section: str | None = None
    starts: list[str] = []
    ends: list[str] = []
    for ev in events[:-1]:  # exclude the trailing complete
        t = ev["type"]
        if t == "phase_start":
            assert open_section is None, f"nested phase_start in {open_section}"
            open_section = ev["section"]
            starts.append(open_section)
        elif t == "phase_end":
            assert open_section == ev["section"], "phase_end section mismatch"
            ends.append(ev["section"])
            open_section = None
        else:  # stream / error must be inside an open envelope for their section
            assert open_section is not None, f"{t} outside any phase envelope"
            assert ev["section"] == open_section, f"{t} section {ev['section']} != open {open_section}"
    assert open_section is None, "unclosed phase envelope"
    assert starts == ends, "phase_start/phase_end sections must pair in order"
    # ALL-selection → these sections in this exact order.
    assert starts == [
        "discovery", "requirements", "user_stories", "ppt",
        "prototype", "ui_design", "ui_preview",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("factory_id", FACTORY_IDS)
async def test_complete_has_exactly_ten_keys(factory_id: str) -> None:
    """``complete.data`` is the 10-key FinalOutputModel — the exact key set, no more/less."""
    factory = _build_factory(factory_id, discovery_text=DISCOVERY_SUBSET_TEXT)
    events = await collect_events(
        factory, message="x", mode="default", mode_prompt=""
    )
    complete = events[-1]
    assert complete["type"] == "complete"
    assert set(complete["data"].keys()) == {
        "auth", "realtime", "dashboard", "discovery", "requirements",
        "user_stories", "ppt", "prototype", "ui_design", "ui_preview",
    }


@pytest.mark.asyncio
async def test_mode_prompt_threaded_into_agent_context() -> None:
    """The ``mode_prompt`` + prior-phase context reach each chat agent's ``.astream`` message.

    Proves scenario (c)'s premise: a non-default mode is not cosmetic — the
    ``ChatRunner`` folds ``mode_prompt`` (and the accumulating prior-phase context)
    into the single message string it passes to each agent's ``.astream``. Asserted by
    capturing the message the discovery agent (first) and a later agent receive.

    Imports are LAZY (function-local) so this module carries no module-level
    ``ChatRunner``/legacy token — keeping the widened ``test_no_baseagent.py`` green.
    """
    from app.agents.chat_runner import ChatRunner
    from app.agents.modes import get_mode_prompt

    captured: dict[str, list[str]] = {}

    class _CapturingRunner:
        def __init__(self, agent_id: str, text: str) -> None:
            self._agent_id = agent_id
            self._text = text

        async def astream(self, message: str) -> AsyncIterator[str]:
            captured.setdefault(self._agent_id, []).append(message)
            for part in _split_two(self._text):
                yield part

    texts = _agent_texts(DISCOVERY_ALL_TEXT)
    by_chat_id = {_CHAT_ID[attr]: text for attr, text in texts.items()}

    def _create_runner(agent_id: str, ctx, **kwargs) -> _CapturingRunner:
        return _CapturingRunner(agent_id, by_chat_id[agent_id])

    mode_prompt = get_mode_prompt("thinking")
    with patch("agents.factory.create_runner", side_effect=_create_runner):
        runner = ChatRunner()

    async for _ in runner.astream_execute(
        "go", mode="thinking", mode_prompt=mode_prompt
    ):
        pass

    # Discovery (first) sees the mode_prompt + the user message, but no prior outputs.
    assert captured.get("chat-discovery"), "discovery agent was never invoked"
    disc_msg = captured["chat-discovery"][0]
    assert mode_prompt in disc_msg
    assert "go" in disc_msg

    # A later phase sees the mode_prompt AND the discovery output threaded in.
    req_msg = captured["chat-requirements"][0]
    assert mode_prompt in req_msg
    assert "Here is the context from previous phases:" in req_msg
    assert "discovery:" in req_msg


# ═════════════════════════════════════════════════════════════════════════════
# META — guard the freeze itself: the golden must remain importable/usable even
# after the legacy stack is deleted (7b-5) and re-pointable to ChatRunner (7b-6).
# ═════════════════════════════════════════════════════════════════════════════


def test_goldens_are_plain_literals_no_legacy_import() -> None:
    """The frozen goldens are pure data and the module has no top-level legacy import.

    Guarantees the golden survived deleting ``app/agents/orchestrator.py`` (7b-5): the
    only ``ChatRunner`` references are inside ``_chatrunner_factory`` / the mode-context
    test (both import lazily), and there is NO module-level ``BaseAgent`` /
    ``AgentOrchestrator`` / ``app.agents.orchestrator`` / ``app.agents.base`` token — so
    this module stays valid after 7b-5 and the widened ``test_no_baseagent`` (which now
    scans the whole ``tests``-adjacent tree for module-level BaseAgent) stays green.
    """
    # All goldens are lists of dicts of JSON-ish primitives.
    for golden in (GOLDEN_ALL, GOLDEN_SUBSET, GOLDEN_FAILURE):
        assert isinstance(golden, list) and golden
        assert golden[-1]["type"] == "complete"
        assert isinstance(golden[-1]["data"], dict)
        assert len(golden[-1]["data"]) == 10

    # No module-level import binds the deleted legacy stack (it must be lazy/in-function).
    src = inspect.getsource(inspect.getmodule(test_goldens_are_plain_literals_no_legacy_import))
    module_header = src.split("def _agent_texts", 1)[0]
    assert "import AgentOrchestrator" not in module_header
    assert "from app.agents.orchestrator" not in module_header
    assert "from app.agents.base" not in module_header


def test_collect_events_is_runner_agnostic() -> None:
    """``collect_events`` only depends on the factory protocol, not the legacy class.

    This is the seam 7b-6 repoints: its signature takes any zero-arg
    ``runner_factory`` whose product exposes ``astream_execute(msg, *, mode, mode_prompt)``.
    """
    sig = inspect.signature(collect_events)
    assert list(sig.parameters) == ["runner_factory", "message", "mode", "mode_prompt"]
