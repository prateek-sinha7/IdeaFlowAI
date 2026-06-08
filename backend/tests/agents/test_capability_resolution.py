"""Wave-0 unit tests for the D-02 resolution seam (07-01 / PARITY-01).

Covers ``CapabilityRegistry.resolve(kind, name)``:
  - returns the bound impl instance whose ``.name == name`` for every known
    (kind, name) that has an impl;
  - raises ``KeyError`` for an unknown name BEFORE any impl lookup (T-07-01-01);
  - raises for a known-but-unbound name;
  - leaves ``is_registered`` (pure ``_KNOWN`` membership) unchanged;
  - performs NO getattr/eval/dynamic-import (asserted by source inspection +
    the unknown-name-raises-first behaviour).
"""

from __future__ import annotations

import inspect
import re

import pytest

from agents.capabilities import registry as registry_mod
from agents.capabilities.registry import CapabilityRegistry, install
from agents.capabilities.strategies.single_shot import SingleShotStrategy
from agents.capabilities.strategies.task_loop import TaskLoopStrategy
from agents.capabilities.task_parsers.heading_tasks import HeadingTasksParser


@pytest.fixture()
def reg() -> CapabilityRegistry:
    install()  # bind impls for these tests
    return CapabilityRegistry()


def test_resolve_heading_tasks_returns_parser_instance(reg: CapabilityRegistry) -> None:
    impl = reg.resolve("task_parser", "heading_tasks")
    assert isinstance(impl, HeadingTasksParser)
    assert impl.name == "heading_tasks"


def test_resolve_single_shot_returns_strategy_instance(reg: CapabilityRegistry) -> None:
    impl = reg.resolve("strategy", "single_shot")
    assert isinstance(impl, SingleShotStrategy)
    assert impl.name == "single_shot"


def test_resolve_task_loop_returns_strategy_instance(reg: CapabilityRegistry) -> None:
    impl = reg.resolve("strategy", "task_loop")
    assert isinstance(impl, TaskLoopStrategy)
    assert impl.name == "task_loop"


@pytest.mark.parametrize(
    "kind,name",
    [
        ("task_parser", "heading_tasks"),
        ("strategy", "single_shot"),
        ("strategy", "task_loop"),
    ],
)
def test_resolved_impl_name_matches_key(
    reg: CapabilityRegistry, kind: str, name: str
) -> None:
    impl = reg.resolve(kind, name)
    assert getattr(impl, "name") == name


def test_resolve_unknown_name_raises(reg: CapabilityRegistry) -> None:
    with pytest.raises(KeyError):
        reg.resolve("strategy", "does_not_exist")


def test_resolve_unknown_kind_raises(reg: CapabilityRegistry) -> None:
    with pytest.raises(KeyError):
        reg.resolve("bogus_kind", "single_shot")


def test_resolve_known_but_unbound_raises_runtime_error() -> None:
    # A name in _KNOWN with no impl bound (e.g. html_static lands in a later plan)
    # is a programmer error → RuntimeError, never silently None.
    install()
    reg = CapabilityRegistry()
    assert reg.is_registered("validator", "html_static") is True
    with pytest.raises(RuntimeError):
        reg.resolve("validator", "html_static")


def test_unknown_name_checked_against_known_before_lookup() -> None:
    # T-07-01-01: an unknown name raises on the _KNOWN membership gate, BEFORE any
    # impl-map lookup — it can never reach the map (no code-exec vector).
    reg = CapabilityRegistry()
    with pytest.raises(KeyError):
        reg.resolve("strategy", "../../etc/passwd")


def test_is_registered_unchanged(reg: CapabilityRegistry) -> None:
    # The compiler's INV-4 membership path is pure _KNOWN set membership.
    assert reg.is_registered("strategy", "single_shot") is True
    assert reg.is_registered("strategy", "nonexistent") is False
    assert reg.is_registered("bogus_kind", "single_shot") is False


def test_resolve_uses_no_dynamic_name_resolution() -> None:
    # T-07-01-01 / V5: resolve must be a STATIC dict lookup — no getattr/eval/
    # importlib/__import__ of the name inside the resolve body. Inspect the CODE
    # (docstring stripped) so the threat-model prose in the docstring doesn't
    # false-trip the gate.
    src = inspect.getsource(CapabilityRegistry.resolve)
    code = re.sub(r'""".*?"""', "", src, count=1, flags=re.DOTALL)
    for banned in ("getattr(", "eval(", "importlib", "__import__"):
        assert banned not in code, f"resolve() must not use {banned}"


def test_resolve_alias_untouched() -> None:
    reg = CapabilityRegistry()
    assert reg.resolve_alias("od_prototype") == "prototype"
    assert reg.resolve_alias("prototype") == "prototype"
