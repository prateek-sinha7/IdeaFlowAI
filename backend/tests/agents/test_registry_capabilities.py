"""Tests for the capability seam (Phase 4 / 04-01).

Covers:
  - ``CapabilityRegistry.is_registered(kind, name)`` for all 15 known names.
  - Unknown name / unknown kind rejection.
  - The ``od_prototype -> prototype`` id-alias resolver (single source).
  - The registered count is exactly 15 (drift guard).

No capability implementations are asserted here — Phase 4 registers NAMES only
(impls land in Phase 7, trust flags in Phase 8 per D-07).
"""

from __future__ import annotations

import typing

import pytest

from agents.capabilities.base import (
    ContextProvider,
    DeliverableResolver,
    ExecutionStrategy,
    GateHandler,
    TaskParser,
    Validator,
)
from agents.capabilities.registry import CapabilityRegistry, _KNOWN

# The authoritative 15 (kind, name) pairs per D-07 / 04-RESEARCH §D-07,
# plus the Phase 6 model_catalog name-only registration (06-01 / D-03).
_EXPECTED_NAMES: list[tuple[str, str]] = [
    ("strategy", "single_shot"),
    ("strategy", "task_loop"),
    ("validator", "html_static"),
    ("validator", "html_render"),
    ("deliverable", "single_file"),
    ("deliverable", "serialized_sandbox"),
    ("deliverable", "streamed_text"),
    ("deliverable", "ppt"),
    ("context_provider", "opendesign"),
    ("context_provider", "previous_run"),
    ("task_parser", "heading_tasks"),
    ("gate", "human"),
    ("gate", "validation"),
    ("compaction", "html_skeleton"),
    ("model_catalog", "default"),
]


@pytest.fixture()
def registry() -> CapabilityRegistry:
    return CapabilityRegistry()


@pytest.mark.parametrize("kind,name", _EXPECTED_NAMES)
def test_all_known_names_are_registered(
    registry: CapabilityRegistry, kind: str, name: str
) -> None:
    assert registry.is_registered(kind, name) is True


def test_unknown_name_is_rejected(registry: CapabilityRegistry) -> None:
    assert registry.is_registered("strategy", "nonexistent") is False


def test_unknown_kind_is_rejected(registry: CapabilityRegistry) -> None:
    # A real name under the wrong kind must not validate.
    assert registry.is_registered("bogus_kind", "single_shot") is False


def test_registered_count_is_exactly_fifteen() -> None:
    # Drift guard: registering a 16th name (or dropping one) must trip this.
    assert len(_KNOWN) == 15
    assert set(_KNOWN) == set(_EXPECTED_NAMES)


def test_resolve_alias_maps_od_prototype(registry: CapabilityRegistry) -> None:
    assert registry.resolve_alias("od_prototype") == "prototype"


def test_resolve_alias_is_identity_for_real_keys(
    registry: CapabilityRegistry,
) -> None:
    assert registry.resolve_alias("prototype") == "prototype"
    assert registry.resolve_alias("ppt") == "ppt"
    assert registry.resolve_alias("od_ppt") == "od_ppt"
    assert registry.resolve_alias("custom") == "custom"


# --- capability ports (base.py) -------------------------------------------

_PORTS = [
    ExecutionStrategy,
    Validator,
    DeliverableResolver,
    ContextProvider,
    GateHandler,
    TaskParser,
]


@pytest.mark.parametrize("port", _PORTS)
def test_port_is_a_protocol(port: type) -> None:
    # Every capability port is a typing.Protocol (hexagonal boundary, §6/§32).
    assert issubclass(port, typing.Protocol)  # type: ignore[arg-type]
    assert getattr(port, "_is_protocol", False) is True


def test_all_six_ports_importable() -> None:
    # Guard against drift in the exported port surface.
    names = {p.__name__ for p in _PORTS}
    assert names == {
        "ExecutionStrategy",
        "Validator",
        "DeliverableResolver",
        "ContextProvider",
        "GateHandler",
        "TaskParser",
    }
