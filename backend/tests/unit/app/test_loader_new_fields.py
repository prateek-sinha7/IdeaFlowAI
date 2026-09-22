"""Unit tests for loader.py Phase 1 extensions (T003/T009).

Tests:
  - Existing AGENT.md without new fields loads with correct defaults
  - New fields (produces, consumes, gate, injects) parse correctly
  - Invalid gate value raises AgentSpecError
  - context_from-only AGENT.md loads without error (backward compat)
  - spec_kit pipeline_type is accepted
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from agents.loader import AgentSpec, AgentSpecError, _build_spec


def _make_metadata(**kwargs) -> dict:
    """Build a minimal valid metadata dict with optional overrides."""
    base = {
        "id": "test-agent",
        "name": "Test Agent",
        "role": "Testing",
        "pipeline_type": "custom",
        "order": 1,
        "max_tokens": 1024,
    }
    base.update(kwargs)
    return base


def _make_prompt() -> str:
    return "You are a test agent."


# ---------------------------------------------------------------------------
# Backward compatibility — existing fields load unchanged
# ---------------------------------------------------------------------------


def test_existing_agent_loads_without_new_fields() -> None:
    """An AGENT.md without produces/consumes/gate/injects loads with defaults."""
    metadata = _make_metadata()
    spec = _build_spec(metadata, _make_prompt(), Path("test/AGENT.md"))

    assert spec.produces == []
    assert spec.consumes == []
    assert spec.gate is None
    assert spec.injects == []


def test_existing_fields_still_work() -> None:
    """Existing optional fields (tools, guardrails, context_from) still parse."""
    metadata = _make_metadata(
        tools=["workspace"],
        guardrails=["react"],
        context_from=["$previous"],
    )
    spec = _build_spec(metadata, _make_prompt(), Path("test/AGENT.md"))

    assert spec.tools == ["workspace"]
    assert spec.guardrails == ["react"]
    assert spec.context_from == ["$previous"]


# ---------------------------------------------------------------------------
# New fields parse correctly
# ---------------------------------------------------------------------------


def test_produces_parses_correctly() -> None:
    metadata = _make_metadata(produces=["spec", "research"])
    spec = _build_spec(metadata, _make_prompt(), Path("test/AGENT.md"))
    assert spec.produces == ["spec", "research"]


def test_consumes_parses_correctly() -> None:
    metadata = _make_metadata(consumes=["spec", "brief"])
    spec = _build_spec(metadata, _make_prompt(), Path("test/AGENT.md"))
    assert spec.consumes == ["spec", "brief"]


def test_injects_parses_correctly() -> None:
    metadata = _make_metadata(injects=["template", "design_system"])
    spec = _build_spec(metadata, _make_prompt(), Path("test/AGENT.md"))
    assert spec.injects == ["template", "design_system"]


def test_gate_human_gate_parses() -> None:
    metadata = _make_metadata(gate="Human_Gate")
    spec = _build_spec(metadata, _make_prompt(), Path("test/AGENT.md"))
    assert spec.gate == "Human_Gate"


def test_gate_validation_gate_parses() -> None:
    metadata = _make_metadata(gate="Validation_Gate")
    spec = _build_spec(metadata, _make_prompt(), Path("test/AGENT.md"))
    assert spec.gate == "Validation_Gate"


def test_gate_null_parses() -> None:
    metadata = _make_metadata(gate=None)
    spec = _build_spec(metadata, _make_prompt(), Path("test/AGENT.md"))
    assert spec.gate is None


def test_gate_absent_defaults_to_none() -> None:
    metadata = _make_metadata()
    spec = _build_spec(metadata, _make_prompt(), Path("test/AGENT.md"))
    assert spec.gate is None


# ---------------------------------------------------------------------------
# Validation errors
# ---------------------------------------------------------------------------


def test_invalid_gate_value_raises_agent_spec_error() -> None:
    metadata = _make_metadata(gate="InvalidGate")
    with pytest.raises(AgentSpecError, match="gate"):
        _build_spec(metadata, _make_prompt(), Path("test/AGENT.md"))


def test_gate_wrong_type_raises_agent_spec_error() -> None:
    metadata = _make_metadata(gate=42)
    with pytest.raises(AgentSpecError, match="gate"):
        _build_spec(metadata, _make_prompt(), Path("test/AGENT.md"))


# ---------------------------------------------------------------------------
# spec_kit pipeline_type accepted
# ---------------------------------------------------------------------------


def test_spec_kit_pipeline_type_accepted() -> None:
    metadata = _make_metadata(pipeline_type="spec_kit")
    spec = _build_spec(metadata, _make_prompt(), Path("test/AGENT.md"))
    assert spec.pipeline_type == "spec_kit"


# ---------------------------------------------------------------------------
# context_from-only backward compat (I3 fix)
# ---------------------------------------------------------------------------


def test_context_from_only_loads_without_error() -> None:
    """An AGENT.md with only context_from (no produces/consumes) loads cleanly."""
    metadata = _make_metadata(context_from=["domain-analyst", "epic-architect"])
    spec = _build_spec(metadata, _make_prompt(), Path("test/AGENT.md"))

    # context_from is preserved
    assert spec.context_from == ["domain-analyst", "epic-architect"]
    # produces/consumes default to empty (not derived from context_from)
    assert spec.produces == []
    assert spec.consumes == []


def test_empty_produces_and_consumes_are_valid() -> None:
    metadata = _make_metadata(produces=[], consumes=[])
    spec = _build_spec(metadata, _make_prompt(), Path("test/AGENT.md"))
    assert spec.produces == []
    assert spec.consumes == []
