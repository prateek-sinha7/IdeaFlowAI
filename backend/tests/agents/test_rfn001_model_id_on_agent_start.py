"""tests/agents/test_rfn001_model_id_on_agent_start.py — RFN-001 offline proof.

Offline (no network / DB / Bedrock) coverage of the per-agent model-id surfacing
introduced by RFN-001:

  1. Source-pin (agent_start) — engine.py emits ``"model_id"`` on ``agent_start``
     so the model chip can appear while the agent is running, not only after it
     completes.

  2. Source-pin (agent_complete) — engine.py continues to emit ``"model_id"`` on
     ``agent_complete`` (the pre-existing ISS-165 path). Confirmed unchanged.

  3. Normalizer strips on agent_start — ``model_id`` is in ``_VOLATILE_STRIP_KEYS``
     so adding it to ``agent_start`` does NOT break the 5 characterization event
     goldens (INV-3).  Same stripping already applied to ``agent_complete`` —
     proven by the characterization test suite passing unchanged.

  4. End-to-end via ``_drive`` — the scripted pipeline emits at least one
     ``agent_start`` event carrying a non-empty ``model_id`` key, confirming the
     engine path is live.

  5. Persistence source-pin — ``run_commands.py`` already persists ``model_id``
     per-agent in ``agent_outputs`` JSON (ISS-165 path, confirmed still present).

All assertions are OFFLINE (no Bedrock / no DB / no network).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.agents.characterization._normalize import (
    _VOLATILE_STRIP_KEYS,
    _normalize_event,
)

_BACKEND = Path(__file__).resolve().parents[2]
_ENGINE = _BACKEND / "agents" / "execution_engine" / "engine.py"
_RUN_COMMANDS = _BACKEND / "app" / "api" / "run_commands.py"


# ── 1. Source-pin: engine.py emits model_id on agent_start ──────────────────


def test_engine_emits_model_id_on_agent_start() -> None:
    """engine.py must call _resolve_model before the agent_start yield and include
    model_id in the event payload (RFN-001 chip-while-running path)."""
    src = _ENGINE.read_text(encoding="utf-8")

    # The resolved variable name used in the agent_start payload
    assert "_start_model_id" in src, (
        "RFN-001: engine.py must resolve the per-agent model id into "
        "_start_model_id before the agent_start yield"
    )

    # The key must appear in the agent_start data dict
    # Find the agent_start block and confirm model_id is in its data
    assert '"model_id": _start_model_id' in src, (
        "RFN-001: engine.py must include 'model_id': _start_model_id in the "
        "agent_start event payload so the chip appears while the agent is running"
    )


def test_engine_resolves_model_before_agent_start_yield() -> None:
    """_resolve_model must be called before the agent_start yield, not after it,
    so the event carries the correct model id from the moment the agent is dispatched."""
    src = _ENGINE.read_text(encoding="utf-8")

    # Both must appear — resolution call and yield
    resolve_pos = src.find("_start_model_id = self._resolve_model(")
    start_yield_pos = src.find('"type": "agent_start"')

    assert resolve_pos != -1, (
        "RFN-001: _start_model_id assignment via _resolve_model not found in engine.py"
    )
    assert start_yield_pos != -1, (
        "RFN-001: agent_start event yield not found in engine.py"
    )
    assert resolve_pos < start_yield_pos, (
        "RFN-001: _resolve_model must be called BEFORE the agent_start yield "
        f"(resolve at char {resolve_pos}, agent_start at char {start_yield_pos})"
    )


# ── 2. Source-pin: agent_complete still carries model_id (ISS-165 unchanged) ─


def test_engine_still_emits_model_id_on_agent_complete() -> None:
    """The pre-existing ISS-165 model_id on agent_complete must not have been
    accidentally removed during the RFN-001 agent_start addition."""
    src = _ENGINE.read_text(encoding="utf-8")
    # The agent_complete payload contains the resolved model — look for the
    # assignment pattern used there (distinct from the new _start_model_id)
    assert '"model_id": _resolved_model_id' in src, (
        "RFN-001: engine.py agent_complete payload must still carry "
        "'model_id': _resolved_model_id (ISS-165 path must remain intact)"
    )


# ── 3. Normalizer: model_id is stripped so goldens stay byte-identical ───────


def test_model_id_is_in_volatile_strip_keys() -> None:
    """model_id is in _VOLATILE_STRIP_KEYS — so adding it to agent_start does NOT
    break any of the 5 characterization event goldens (INV-3)."""
    assert "model_id" in _VOLATILE_STRIP_KEYS, (
        "RFN-001: 'model_id' must be in _VOLATILE_STRIP_KEYS so adding it to "
        "agent_start is golden-neutral (INV-3)"
    )


def test_normalize_strips_model_id_from_agent_start() -> None:
    """The normalizer drops model_id from an agent_start event the same way it
    already drops it from agent_complete — golden safety confirmed at the event level."""
    raw_event = {
        "type": "agent_start",
        "data": {
            "agent_id": "spec-writer",
            "name": "Spec Writer",
            "role": "Domain analysis",
            "icon": "✍️",
            "index": 0,
            "total": 3,
            "model_id": "eu.anthropic.claude-sonnet-4-5-20250929-v1:0",
        },
    }
    normalized = _normalize_event(raw_event)
    assert "model_id" not in normalized["data"], (
        "RFN-001: _normalize_event must strip model_id from agent_start data "
        "(it is in _VOLATILE_STRIP_KEYS) — golden parity broken if present"
    )
    # The rest of the structural keys must still be present
    assert normalized["data"]["agent_id"] == "spec-writer"
    assert normalized["data"]["name"] == "Spec Writer"
    assert normalized["type"] == "agent_start"


def test_normalize_strips_model_id_from_agent_complete() -> None:
    """Regression guard: model_id is still stripped from agent_complete after the
    RFN-001 changes (the ISS-165 normalizer contract must remain intact)."""
    raw_event = {
        "type": "agent_complete",
        "data": {
            "agent_id": "spec-writer",
            "duration": 12.4,
            "input_tokens": 1000,
            "output_tokens": 500,
            "total_tokens": 1500,
            "model_id": "eu.anthropic.claude-sonnet-4-5-20250929-v1:0",
        },
    }
    normalized = _normalize_event(raw_event)
    assert "model_id" not in normalized["data"], (
        "RFN-001 regression: model_id must still be stripped from agent_complete "
        "by _normalize_event"
    )


# ── 4. End-to-end: scripted pipeline emits agent_start with model_id ─────────


@pytest.mark.asyncio
async def test_prototype_agent_start_events_carry_model_id() -> None:
    """End-to-end via the scripted harness: every agent_start event in the
    prototype pipeline carries a non-empty model_id key (RFN-001 live path)."""
    from tests.agents._scripted_model import _drive

    events = await _drive("prototype")
    assert events, "prototype produced no events"

    start_events = [e for e in events if e.get("type") == "agent_start"]
    assert start_events, "prototype pipeline emitted no agent_start events"

    missing = [
        e["data"].get("agent_id", "<unknown>")
        for e in start_events
        if not e.get("data", {}).get("model_id")
    ]
    assert not missing, (
        f"RFN-001: the following agent_start events have no model_id: {missing}. "
        "engine.py must resolve and include model_id before the agent_start yield."
    )


# ── 5. Persistence source-pin: run_commands.py still persists model_id ───────


def test_run_commands_persists_model_id_per_agent() -> None:
    """_apply_terminal_output_columns in run_commands.py must still carry model_id
    from the agent_complete event into the agent_outputs JSON (ISS-165 path,
    confirmed unbroken by RFN-001 changes)."""
    src = _RUN_COMMANDS.read_text(encoding="utf-8")
    assert 'current_agent["model_id"] = data.get("model_id")' in src, (
        "RFN-001: run_commands.py must still persist model_id per-agent from the "
        "agent_complete event payload into agent_outputs (ISS-165 path must be intact)"
    )
