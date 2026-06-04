"""Focused unit tests for the Phase-7b ``ChatRunner`` sequencer.

Two things are proven here (the frozen byte-for-byte event contract lives in
``tests/unit/test_chat_contract.py`` — repointed at this runner in 7b-5):

  1. **Ported-helper behavior** — ``ChatRunner._parse_output_selection`` /
     ``_determine_active_phases`` / ``_compile_final_output`` produce the FROZEN
     expected output over a battery of sample inputs. These values were originally
     captured byte-for-byte from the legacy ``AgentOrchestrator`` (the "ported
     verbatim" oracle); 7b-5 DELETED the legacy stack, so the expectations are now
     inlined as frozen literals (the helpers are self-contained ports — the contract
     golden in ``test_chat_contract.py`` independently proves the runtime reproduces
     the legacy event stream).

  2. **Event-sequence smoke** — ``astream_execute`` with mocked runners yields
     the legacy ``phase_start`` → ``stream``* → ``phase_end`` envelope per active
     phase and a single trailing ``complete`` carrying the 10-key
     ``FinalOutputModel``; mode + prior-phase context reach each agent's
     ``.astream``; a per-phase failure emits ``error`` + continues.

This module carries NO ``AgentOrchestrator`` / ``BaseAgent`` token (keeps the widened
``test_no_baseagent`` green and lets the module import after 7b-5's deletion).
"""

from __future__ import annotations

from typing import AsyncIterator, Callable
from unittest.mock import patch

import pytest

from app.agents.chat_runner import ChatRunner


# ─────────────────────────────────────────────────────────────────────────────
# Mocked runner machinery — stub the 7 DeepAgentRunners so no model / no graph
# is built. ``create_runner`` (imported inside ChatRunner.__init__) is patched to
# return a recording stub whose ``.astream`` yields scripted text.
# ─────────────────────────────────────────────────────────────────────────────


class _StubRunner:
    """Minimal stand-in for a text-only ``DeepAgentRunner``.

    Records every message passed to ``.astream`` (so we can assert mode + prior
    context threading) and yields its scripted text in two chunks (proving the
    sequencer accumulates ``"".join(parts)`` AND emits one ``stream`` per chunk).
    """

    def __init__(self, agent_id: str, text: str, *, raises: BaseException | None = None) -> None:
        self.agent_id = agent_id
        self._text = text
        self._raises = raises
        self.seen_messages: list[str] = []

    async def astream(self, message: str) -> AsyncIterator[str]:
        self.seen_messages.append(message)
        if self._raises is not None:
            raise self._raises
            yield ""  # pragma: no cover — makes this an async generator
        mid = max(1, len(self._text) // 2)
        for part in (self._text[:mid], self._text[mid:]):
            yield part


# Per-agent scripted text. Discovery text drives _parse_output_selection;
# ppt/prototype/preview carry valid JSON so json.loads succeeds.
_DISCOVERY_ALL = "Based on our discussion, I'll generate: All deliverables."
_DISCOVERY_SUBSET = "I'll generate: User Stories and a Prototype."
_AGENT_TEXT = {
    "chat-discovery": _DISCOVERY_ALL,
    "chat-requirements": "REQUIREMENTS body.",
    "chat-user-stories": "# Epic: Core",
    "chat-ppt": '{"slides": [{"title": "Intro"}]}',
    "chat-prototype": '{"pages": [{"name": "Home"}]}',
    "chat-ui-design": "Design tokens here.",
    "chat-preview": '{"previews": ["user_stories"]}',
}


def _make_create_runner(
    *,
    discovery_text: str,
    failing_agent: str | None = None,
    failure_exc: BaseException | None = None,
    registry: dict[str, _StubRunner] | None = None,
) -> Callable[..., _StubRunner]:
    """Build a ``create_runner`` replacement returning recording stubs.

    ``registry`` (if given) is populated ``agent_id -> _StubRunner`` so the test
    can introspect what each agent received.
    """

    def _factory(agent_id: str, ctx, **kwargs) -> _StubRunner:
        text = discovery_text if agent_id == "chat-discovery" else _AGENT_TEXT[agent_id]
        raises = failure_exc if (agent_id == failing_agent and failure_exc) else None
        stub = _StubRunner(agent_id, text, raises=raises)
        if registry is not None:
            registry[agent_id] = stub
        return stub

    return _factory


def _build_chat_runner(**kwargs) -> tuple[ChatRunner, dict[str, _StubRunner]]:
    """Construct a ``ChatRunner`` with ``create_runner`` patched to stubs."""
    registry: dict[str, _StubRunner] = {}
    factory = _make_create_runner(registry=registry, **kwargs)
    with patch("agents.factory.create_runner", side_effect=factory):
        runner = ChatRunner()
    return runner, registry


async def _collect(runner: ChatRunner, *, message: str, mode: str = "default",
                   mode_prompt: str = "") -> list[dict]:
    events: list[dict] = []
    async for ev in runner.astream_execute(message, mode=mode, mode_prompt=mode_prompt):
        events.append(ev)
    return events


# ═════════════════════════════════════════════════════════════════════════════
# 1. PORTED-HELPER BEHAVIOR — frozen expectations.
#
# These values were captured byte-for-byte from the legacy ``AgentOrchestrator``
# (the "ported verbatim" oracle) before 7b-5 deleted it. They are now inlined as
# frozen literals: the helpers are self-contained ports, and the contract golden in
# ``test_chat_contract.py`` independently proves the runtime reproduces the legacy
# event stream. A future refactor of these helpers must keep these literals satisfied.
# ═════════════════════════════════════════════════════════════════════════════

_ALL_FOUR = ["user_stories", "ppt", "prototype", "ui_design"]

# (discovery sample, expected Output_Selection) — spans every parse branch.
_PARSE_CASES: list[tuple[str, list[str]]] = [
    ("Based on our discussion, I'll generate: All deliverables.", _ALL_FOUR),  # all fast-path
    ("i'll generate: all of them", _ALL_FOUR),                                  # all variant
    ("let's generate all the things", _ALL_FOUR),                              # "generate all"
    ("I'll generate: User Stories and a Prototype.", ["user_stories", "prototype"]),  # subset
    ("We'll make a PowerPoint presentation with slides.", ["ppt"]),           # ppt synonyms
    ("A ui design / design spec would help.", ["ui_design"]),                 # ui_design
    ("ppt and prototype and user stories and ui design", _ALL_FOUR),         # all via keywords
    ("no recognised keyword here at all whatsoever", _ALL_FOUR),             # 'all' substr, no trigger → default
    ("", _ALL_FOUR),                                                          # empty → default all
    ("PROTOTYPE in caps", ["prototype"]),                                    # case-insensitive
]


def test_parse_output_selection_frozen() -> None:
    """``_parse_output_selection`` produces the frozen Output_Selection over all branches."""
    new = ChatRunner.__new__(ChatRunner)  # no __init__ — pure-function methods only
    for sample, expected in _PARSE_CASES:
        assert new._parse_output_selection(sample) == expected, sample


def test_determine_active_phases_frozen() -> None:
    """``_determine_active_phases`` produces the frozen phase lists (phase 7 always appended)."""
    new = ChatRunner.__new__(ChatRunner)
    # (selection, expected active phases) — every subset + unknown/dup/reversed.
    cases: list[tuple[list[str], list[int]]] = [
        ([], [7]),
        (["user_stories"], [3, 7]),
        (["ppt"], [4, 7]),
        (["prototype"], [5, 7]),
        (["ui_design"], [6, 7]),
        (["user_stories", "ppt"], [3, 4, 7]),
        (["user_stories", "prototype"], [3, 5, 7]),
        (["user_stories", "ui_design"], [3, 6, 7]),
        (["ppt", "prototype"], [4, 5, 7]),
        (["ppt", "ui_design"], [4, 6, 7]),
        (["prototype", "ui_design"], [5, 6, 7]),
        (["user_stories", "ppt", "prototype"], [3, 4, 5, 7]),
        (["user_stories", "ppt", "ui_design"], [3, 4, 6, 7]),
        (["user_stories", "prototype", "ui_design"], [3, 5, 6, 7]),
        (["ppt", "prototype", "ui_design"], [4, 5, 6, 7]),
        (_ALL_FOUR, [3, 4, 5, 6, 7]),
        (["unknown_key"], [7]),                       # unmapped key dropped
        (["ppt", "ppt"], [4, 4, 7]),                  # legacy did NOT dedupe
        (["ui_design", "user_stories"], [3, 6, 7]),   # sorted regardless of input order
        (["prototype", "bogus", "ppt"], [4, 5, 7]),   # bogus dropped, sorted
    ]
    for sel, expected in cases:
        assert new._determine_active_phases(sel) == expected, sel


def test_compile_final_output_frozen() -> None:
    """``_compile_final_output`` produces the frozen 10-key output (produced/skipped/failed/JSON)."""
    new = ChatRunner.__new__(ChatRunner)

    cases: list[tuple[dict, list[str], dict]] = [
        # ALL produced (JSON phases already parsed in context).
        (
            {
                "discovery": {"output": "d"}, "requirements": {"output": "r"},
                "user_stories": {"output": "us"}, "ppt": {"slides": []},
                "prototype": {"pages": []}, "ui_design": {"output": "ui"},
                "ui_preview": {"previews": []},
                "output_selection": _ALL_FOUR,
            },
            _ALL_FOUR,
            {
                "auth": None, "realtime": None, "dashboard": None,
                "discovery": {"output": "d"}, "requirements": {"output": "r"},
                "user_stories": {"output": "us"}, "ppt": {"slides": []},
                "prototype": {"pages": []}, "ui_design": {"output": "ui"},
                "ui_preview": {"previews": []},
            },
        ),
        # SUBSET — ppt + ui_design skipped → {"status":"skipped"}.
        (
            {
                "discovery": {"output": "d"}, "requirements": {"output": "r"},
                "user_stories": {"output": "us"}, "prototype": {"pages": []},
                "ui_preview": {"previews": []},
                "output_selection": ["user_stories", "prototype"],
            },
            ["user_stories", "prototype"],
            {
                "auth": None, "realtime": None, "dashboard": None,
                "discovery": {"output": "d"}, "requirements": {"output": "r"},
                "user_stories": {"output": "us"},
                "ppt": {"status": "skipped", "value": None},
                "prototype": {"pages": []},
                "ui_design": {"status": "skipped", "value": None},
                "ui_preview": {"previews": []},
            },
        ),
        # FAILED requirements + a failed ppt (only ppt selected).
        (
            {
                "discovery": {"output": "d"},
                "requirements": {"status": "failed", "error": "boom"},
                "ppt": {"status": "failed", "error": "kaboom"},
                "ui_preview": {"previews": []},
                "output_selection": ["ppt"],
            },
            ["ppt"],
            {
                "auth": None, "realtime": None, "dashboard": None,
                "discovery": {"output": "d"},
                "requirements": {"status": "failed", "error": "boom"},
                "user_stories": {"status": "skipped", "value": None},
                "ppt": {"status": "failed", "error": "kaboom"},
                "prototype": {"status": "skipped", "value": None},
                "ui_design": {"status": "skipped", "value": None},
                "ui_preview": {"previews": []},
            },
        ),
        # EMPTY context — always-run sections → None; selectable → skipped.
        (
            {}, [],
            {
                "auth": None, "realtime": None, "dashboard": None,
                "discovery": None, "requirements": None,
                "user_stories": {"status": "skipped", "value": None},
                "ppt": {"status": "skipped", "value": None},
                "prototype": {"status": "skipped", "value": None},
                "ui_design": {"status": "skipped", "value": None},
                "ui_preview": None,
            },
        ),
        # Only discovery present (selection = all → nothing 'skipped'; missing → None).
        (
            {"discovery": {"output": "d"}}, _ALL_FOUR,
            {
                "auth": None, "realtime": None, "dashboard": None,
                "discovery": {"output": "d"}, "requirements": None,
                "user_stories": None, "ppt": None, "prototype": None,
                "ui_design": None, "ui_preview": None,
            },
        ),
    ]
    for ctx, sel, expected in cases:
        got = new._compile_final_output(dict(ctx), sel).model_dump()
        assert got == expected, (ctx, sel)
        # Always the 10-key set.
        assert set(got.keys()) == {
            "auth", "realtime", "dashboard", "discovery", "requirements",
            "user_stories", "ppt", "prototype", "ui_design", "ui_preview",
        }


# ═════════════════════════════════════════════════════════════════════════════
# 2. EVENT-SEQUENCE SMOKE — astream_execute with mocked runners.
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_astream_execute_all_outputs_sequence() -> None:
    """ALL-selection: phase_start→2×stream→phase_end for every phase + trailing complete."""
    runner, _registry = _build_chat_runner(discovery_text=_DISCOVERY_ALL)
    events = await _collect(runner, message="build it all")

    # Shape invariant: every event is the StreamMessageModel quadruple.
    for ev in events:
        assert set(ev.keys()) == {"type", "chunk", "section", "data"}, ev

    # The phase envelope order (ALL-selection → all 7 sections).
    starts = [e["section"] for e in events if e["type"] == "phase_start"]
    ends = [e["section"] for e in events if e["type"] == "phase_end"]
    assert starts == ends == [
        "discovery", "requirements", "user_stories", "ppt",
        "prototype", "ui_design", "ui_preview",
    ]

    # phase_start payloads: phases 0/1 use display names; 3-7 use the section key.
    by_start = {e["section"]: e["data"] for e in events if e["type"] == "phase_start"}
    assert by_start["discovery"] == {"phase": 0, "name": "Discovery"}
    assert by_start["requirements"] == {"phase": 1, "name": "Requirements"}
    assert by_start["user_stories"] == {"phase": 3, "name": "user_stories"}
    assert by_start["ui_preview"] == {"phase": 7, "name": "ui_preview"}

    # Exactly two stream events per section (the stub yields two chunks).
    for section in ("discovery", "requirements", "ppt", "ui_preview"):
        streams = [e for e in events if e["type"] == "stream" and e["section"] == section]
        assert len(streams) == 2, section
        for s in streams:
            assert s["chunk"] and s["data"] is None

    # Trailing complete: single, last, 10-key FinalOutputModel; JSON phases parsed.
    assert sum(1 for e in events if e["type"] == "complete") == 1
    complete = events[-1]
    assert complete["type"] == "complete" and complete["section"] is None
    data = complete["data"]
    assert set(data.keys()) == {
        "auth", "realtime", "dashboard", "discovery", "requirements",
        "user_stories", "ppt", "prototype", "ui_design", "ui_preview",
    }
    assert data["ppt"] == {"slides": [{"title": "Intro"}]}          # JSON-parsed (phase 4)
    assert data["prototype"] == {"pages": [{"name": "Home"}]}       # JSON-parsed (phase 5)
    assert data["ui_preview"] == {"previews": ["user_stories"]}     # JSON-parsed (phase 7)
    assert data["requirements"] == {"output": "REQUIREMENTS body."}  # non-JSON → wrapped
    assert data["auth"] is None and data["realtime"] is None and data["dashboard"] is None


@pytest.mark.asyncio
async def test_astream_execute_subset_skips_phases() -> None:
    """SUBSET selection: ppt(4)/ui_design(6) skipped; skipped sections are sentinels."""
    runner, _ = _build_chat_runner(discovery_text=_DISCOVERY_SUBSET)
    events = await _collect(runner, message="stories and a prototype")

    starts = [e["section"] for e in events if e["type"] == "phase_start"]
    assert starts == ["discovery", "requirements", "user_stories", "prototype", "ui_preview"]
    assert "ppt" not in starts and "ui_design" not in starts

    data = events[-1]["data"]
    assert data["ppt"] == {"status": "skipped", "value": None}
    assert data["ui_design"] == {"status": "skipped", "value": None}
    assert data["prototype"] == {"pages": [{"name": "Home"}]}


@pytest.mark.asyncio
async def test_mode_and_context_thread_into_each_agent() -> None:
    """``mode_prompt`` and prior-phase outputs reach every agent's ``.astream`` message."""
    runner, registry = _build_chat_runner(discovery_text=_DISCOVERY_ALL)
    mode_prompt = "You are in deep thinking mode."
    await _collect(runner, message="go", mode="thinking", mode_prompt=mode_prompt)

    # Discovery (first) sees the mode_prompt + the user message, but no prior outputs.
    disc_msg = registry["chat-discovery"].seen_messages[0]
    assert mode_prompt in disc_msg
    assert "go" in disc_msg
    assert "discovery:" not in disc_msg  # no prior-phase context yet

    # Requirements (second) sees the mode_prompt AND the discovery output threaded in.
    req_msg = registry["chat-requirements"].seen_messages[0]
    assert mode_prompt in req_msg
    assert "Here is the context from previous phases:" in req_msg
    assert "discovery:" in req_msg and _DISCOVERY_ALL in req_msg

    # A later phase sees requirements too (full prior-phase context accumulates).
    ppt_msg = registry["chat-ppt"].seen_messages[0]
    assert "requirements:" in ppt_msg and "REQUIREMENTS body." in ppt_msg


@pytest.mark.asyncio
async def test_phase_failure_emits_error_and_continues() -> None:
    """A raising phase emits ``error`` (between start/end), no ``stream``, pipeline continues."""
    runner, _ = _build_chat_runner(
        discovery_text=_DISCOVERY_SUBSET,
        failing_agent="chat-requirements",
        failure_exc=RuntimeError("scripted requirements failure"),
    )
    events = await _collect(runner, message="stories + prototype")

    # An error event for the requirements section, with the legacy payload shape.
    errors = [e for e in events if e["type"] == "error"]
    assert len(errors) == 1
    err = errors[0]
    assert err["section"] == "requirements"
    assert set(err["data"].keys()) == {"error", "code", "recoverable", "phase"}
    assert err["data"]["phase"] == 1
    assert err["data"]["code"] == "internal_error" and err["data"]["recoverable"] is True

    # No stream event fired for the failed requirements phase.
    assert not [e for e in events if e["type"] == "stream" and e["section"] == "requirements"]

    # The error sits strictly between requirements' phase_start and phase_end.
    types_for_req = [
        e["type"] for e in events
        if e["section"] == "requirements" or (e["type"] in ("phase_start", "phase_end") and e["section"] == "requirements")
    ]
    assert types_for_req == ["phase_start", "error", "phase_end"]

    # Pipeline CONTINUED: later phases ran; complete records the failure.
    starts = [e["section"] for e in events if e["type"] == "phase_start"]
    assert starts == ["discovery", "requirements", "user_stories", "prototype", "ui_preview"]
    assert events[-1]["data"]["requirements"] == {
        "status": "failed", "error": "scripted requirements failure",
    }


@pytest.mark.asyncio
async def test_json_parse_fallback_wraps_non_json() -> None:
    """A JSON phase (5) whose output isn't valid JSON falls back to ``{"output": text}``."""
    # Override the prototype agent's text to be non-JSON.
    registry: dict[str, _StubRunner] = {}

    def _factory(agent_id: str, ctx, **kwargs) -> _StubRunner:
        text = _DISCOVERY_SUBSET if agent_id == "chat-discovery" else _AGENT_TEXT[agent_id]
        if agent_id == "chat-prototype":
            text = "this is not json"
        stub = _StubRunner(agent_id, text)
        registry[agent_id] = stub
        return stub

    with patch("agents.factory.create_runner", side_effect=_factory):
        runner = ChatRunner()
    events = await _collect(runner, message="x")

    # Phase 5 (prototype) is a JSON phase; invalid JSON → wrapped, not raised.
    assert events[-1]["data"]["prototype"] == {"output": "this is not json"}
    assert events[-1]["type"] == "complete"
