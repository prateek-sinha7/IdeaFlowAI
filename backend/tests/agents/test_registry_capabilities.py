"""Tests for the capability seam (Phase 4 / 04-01; Phase 8 / 08-01).

Covers:
  - ``CapabilityRegistry.is_registered(kind, name)`` for all known names.
  - Unknown name / unknown kind rejection.
  - The ``od_prototype -> prototype`` id-alias resolver (single source).
  - The registered count drift guard.
  - Phase 8 (08-01 / D-01/D-02): the ``@register`` decorator self-registers
    ``(kind,name)->impl`` at module import; ``discover()`` is idempotent and
    binds the built-in impl set; ``is_user_allowed`` reflects the trust flag;
    the new ``tool``/``skill``/``hook``/``runtime`` KIND strings are accepted;
    the ``_KNOWN`` membership path stays impl-free at compiler import.

No capability implementations are asserted in the Phase-4 section — Phase 4
registers NAMES only; impls + trust flags land in Phase 8 (08-01).
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
from agents.capabilities import registry as registry_mod
from agents.capabilities.registry import CapabilityRegistry, _KNOWN, register

# The authoritative 15 (kind, name) pairs per D-07 / 04-RESEARCH §D-07,
# plus the Phase 6 model_catalog name-only registration (06-01 / D-03),
# plus the 07-10 post_step capability (CR-06: the relocated revision validation).
_EXPECTED_NAMES: list[tuple[str, str]] = [
    ("strategy", "single_shot"),
    ("strategy", "task_loop"),
    ("strategy", "fanout_batch"),          # 11-01 / FANOUT-02
    ("strategy", "wave_scheduler"),        # 12-01 / WAVE-01 (user_allowed=True)
    ("merge", "copy_disjoint"),            # 11-03 / FANOUT-07 (user_allowed=True)
    ("merge", "git_3way"),                 # 11-03 / FANOUT-07 (user_allowed=True)
    ("merge", "json"),                     # 11-03 / FANOUT-07 (user_allowed=True)
    ("merge", "html_fragment"),            # 11-03 / FANOUT-07 (user_allowed=True)
    ("validator", "html_static"),
    ("validator", "html_render"),
    ("validator", "spec_plan_coverage"),   # 08-04 / Tier#4
    ("validator", "task_done_when"),       # 08-04 / Tier#5
    ("validator", "design_quality"),       # 08-04 / Tier#6
    ("validator", "code_compile"),         # 10-04 / EXEC-02 — py_compile via the exec handle
    ("validator", "code_test"),            # 10-04 / EXEC-02 — pytest via the exec handle
    ("validator", "code_lint"),            # 10-04 / EXEC-02 — ruff check via the exec handle
    ("deliverable", "single_file"),
    ("deliverable", "serialized_sandbox"),
    ("deliverable", "streamed_text"),
    ("deliverable", "ppt"),
    ("context_provider", "opendesign"),
    ("context_provider", "previous_run"),
    ("task_parser", "heading_tasks"),
    ("task_parser", "json_tasks"),         # 12-01 / WAVE-02 (structured task list)
    ("gate", "human"),
    ("gate", "validation"),
    ("gate", "approval"),   # 08-02
    ("gate", "security"),   # 08-02
    ("tool", "workspace"),             # 08-03 / F2
    ("tool", "prototype"),             # 08-03 / F2
    ("tool", "prototype_emit_only"),   # 08-03 / F2
    ("tool", "planning"),              # 08-03 / F2
    ("tool", "spawn_subagents"),       # 11-01 / FANOUT-01 (user_allowed=False)
    ("compaction", "html_skeleton"),
    ("post_step", "revision_validation"),
    ("model_catalog", "default"),
    ("runtime", "langchain_deepagents"),   # 08-05 / F5
    ("prompt", "default"),                 # 08-05 / F1
    ("skill", "ui"),                       # 08-05 / F3 / SKILL-01
    ("skill", "disk"),                     # 08-05 / F3 / SKILL-01
    ("skill", "template"),                 # 08-05 / F3 / SKILL-01
    ("skill", "repo"),                     # 08-05 / F3 / SKILL-01
    ("hook", "behavioral"),                # 08-05 / F3
    ("hook", "secret_scan"),               # 08-07 / HOOK-01..04 (executable, blocking)
    ("hook", "otel_tracing"),              # 08-07 / OBS-02 (executable, non-blocking)
    ("runtime_env", "local"),              # 09-01 / RUNTIME-01 — LocalSandboxRuntime (ECS-swap seam)
    ("repo_index", "tree_sitter"),         # 09-03 / REPO-02 — app-side symbol index (tree-sitter)
    ("repo_inventory", "default"),         # 09-03 / REPO-01 — kernel-side stdlib inventory
    ("context_pack", "default"),           # 09-03 / REPO-03 — kernel-side targeted context subset
    ("context_provider", "repo"),          # 09-03 / REPO-03 — surfaces the ContextPack to agents
    ("deliverable", "repo_diff"),          # 09-04 / REPO-04 — brownfield diff-only resolver
    ("mcp_server", "github"),              # 09-05 / MCP-02 — read-scoped (user_allowed=True)
    ("mcp_server", "gitlab"),              # 09-05 / MCP-02 — read-scoped (user_allowed=True)
    ("mcp_server", "jira"),                # 09-05 / MCP-02 — read-scoped (user_allowed=True)
    ("mcp_server", "slack"),              # 09-05 / MCP-02 — post-scoped (user_allowed=True)
    ("mcp_server", "filesystem"),          # 09-05 / MCP-02 — powerful (user_allowed=False)
    ("mcp_server", "postgres"),            # 09-05 / MCP-02 — powerful (user_allowed=False)
    ("integration_provider", "github"),    # 09-06 / INTEG-01 — MCP-backed bridge (user_allowed=True)
    ("integration_provider", "gitlab"),    # 09-06 / INTEG-01 — MCP-backed bridge (user_allowed=True)
    ("integration_provider", "jira"),      # 09-06 / INTEG-01 — MCP-backed bridge (user_allowed=True)
    ("integration_provider", "slack"),     # 09-06 / INTEG-01 — MCP-backed bridge (user_allowed=True)
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


def test_registered_count_is_exactly_fifty() -> None:
    # Drift guard: registering a 60th name (or dropping one) must trip this.
    # 15 authoritative D-07 pairs + model_catalog (06-01) + post_step
    # revision_validation (07-10 / CR-06) = 16, plus the two 08-02 gate names
    # (approval/security) = 18, plus the four 08-03 tool-set names
    # (workspace/prototype/prototype_emit_only/planning, F2) = 22, plus the three
    # 08-04 Tier validators (spec_plan_coverage/task_done_when/design_quality) = 25,
    # plus the one 08-05 runtime adapter (langchain_deepagents, F5) = 26, plus the
    # six 08-05 prompt/skill/hook capabilities (prompt:default F1; skill:ui/disk/
    # template/repo F3/SKILL-01; hook:behavioral F3) = 32, plus the two 08-07
    # executable hooks (hook:secret_scan HOOK-01..04; hook:otel_tracing OBS-02) = 34,
    # plus the one 09-01 runtime backend (runtime_env:local, RUNTIME-01) = 35, plus
    # the four 09-03 repo-context capabilities (repo_index:tree_sitter REPO-02;
    # repo_inventory:default REPO-01; context_pack:default + context_provider:repo
    # REPO-03) = 39, plus the one 09-04 brownfield deliverable (deliverable:repo_diff
    # REPO-04) = 40, plus the six 09-05 mcp_server catalog entries (github/gitlab/jira/
    # slack user_allowed=True + filesystem/postgres user_allowed=False, MCP-02) = 46,
    # plus the four 09-06 integration-provider bridges (github/gitlab/jira/slack
    # user_allowed=True, INTEG-01) = 50, plus the three 10-04 code validators
    # (validator:code_compile/code_test/code_lint, EXEC-02 — they reach exec only via
    # the runner/workspace handle) = 53, plus the two 11-01 fan-out capabilities
    # (strategy:fanout_batch user_allowed=True FANOUT-02; tool:spawn_subagents
    # user_allowed=False FANOUT-01) = 55, plus the four 11-03 merge strategies
    # (merge:copy_disjoint/git_3way/json/html_fragment user_allowed=True FANOUT-07) = 59,
    # plus the two 12-01 wave capabilities (strategy:wave_scheduler user_allowed=True
    # WAVE-01; task_parser:json_tasks WAVE-02) = 61.
    assert len(_KNOWN) == 61
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


# --- Phase 8 (08-01): @register / discover() / user_allowed (D-01/D-02) ----


@pytest.fixture()
def _clean_registry():
    """Snapshot + restore the process-global registry maps around a test.

    The Phase-8 ``@register`` decorator + ``discover()`` mutate process-global
    maps (``_IMPLS``/``_KNOWN``/``_TRUST``) and the idempotency flag. Save/restore
    so a test that registers a throwaway capability (or runs ``discover()``) never
    leaks into another test or the characterization snapshots (mirrors the D-12
    fold added to ``test_strategies.py``).

    Discovery is import-side-effect-driven: the ``@register`` decorators fire only
    on the FIRST import of each impl module in the process. So we ensure
    ``discover()`` has run BEFORE snapshotting — the snapshot then always carries
    the built-in impls, and restoring it can never drop them (a snapshot taken
    pre-discovery would, because a later re-import is a no-op).
    """
    registry_mod.discover()
    known = set(registry_mod._KNOWN)
    impls = dict(registry_mod._IMPLS)
    trust = dict(registry_mod._TRUST)
    discovered = registry_mod._DISCOVERED
    try:
        yield
    finally:
        registry_mod._KNOWN.clear()
        registry_mod._KNOWN.update(known)
        registry_mod._IMPLS.clear()
        registry_mod._IMPLS.update(impls)
        registry_mod._TRUST.clear()
        registry_mod._TRUST.update(trust)
        registry_mod._DISCOVERED = discovered


def test_register_binds_impl_resolvable_after_decorator(_clean_registry) -> None:
    # A module that decorates a class with @register is resolvable with ZERO edits
    # to the registry's resolution code (no central if/elif). Mark discovered so the
    # first resolve() does not re-run discover() and clobber the throwaway impl.
    registry_mod._DISCOVERED = True

    @register("strategy", "demo_single_shot")
    class _FakeSingleShot:
        name = "demo_single_shot"

    assert isinstance(
        CapabilityRegistry().resolve("strategy", "demo_single_shot"), _FakeSingleShot
    )


def test_register_records_user_allowed(_clean_registry) -> None:
    @register("validator", "html_static", user_allowed=True)
    class _AllowedValidator:
        name = "html_static"

    @register("strategy", "single_shot")  # default user_allowed=False
    class _DeniedStrategy:
        name = "single_shot"

    reg = CapabilityRegistry()
    assert reg.is_user_allowed("validator", "html_static") is True
    assert reg.is_user_allowed("strategy", "single_shot") is False


def test_register_adds_membership_to_known(_clean_registry) -> None:
    # A brand-new (kind, name) under one of the new KIND strings registers and
    # becomes a known membership pair — no central kind allow-list / if-elif.
    # Use a NOT-YET-real runtime name (``custom_runner`` is a future slot, F5) so the
    # assertion that it is absent pre-registration holds; ``langchain_deepagents`` is
    # now a permanent _KNOWN member (08-05).
    assert ("runtime", "custom_runner") not in registry_mod._KNOWN

    @register("runtime", "custom_runner")
    class _FakeRuntime:
        name = "custom_runner"

    reg = CapabilityRegistry()
    assert reg.is_registered("runtime", "custom_runner") is True
    assert isinstance(reg.resolve("runtime", "custom_runner"), _FakeRuntime)


@pytest.mark.parametrize("kind", ["tool", "skill", "hook", "runtime"])
def test_new_kinds_are_accepted(_clean_registry, kind: str) -> None:
    @register(kind, f"demo_{kind}")
    class _FakeCap:
        name = f"demo_{kind}"

    assert CapabilityRegistry().is_registered(kind, f"demo_{kind}") is True


def test_discover_is_idempotent(_clean_registry) -> None:
    # Two discover() calls bind the same impl set without error.
    registry_mod._DISCOVERED = False
    registry_mod.discover()
    first = dict(registry_mod._IMPLS)
    registry_mod.discover()  # second call — must be a no-op
    assert registry_mod._IMPLS == first


def test_discover_binds_the_builtin_impls(_clean_registry) -> None:
    # discover() reproduces the impl set install() produced (07 built-ins). The
    # decorators fire at impl-module import (the first discover() in the process);
    # discover() is the single trigger for that import. Assert every built-in pair
    # resolves to an impl whose ``name`` matches.
    registry_mod.discover()
    reg = CapabilityRegistry()
    for kind, name in [
        ("strategy", "single_shot"),
        ("strategy", "task_loop"),
        ("task_parser", "heading_tasks"),
        ("deliverable", "single_file"),
        ("deliverable", "serialized_sandbox"),
        ("deliverable", "streamed_text"),
        ("deliverable", "ppt"),
        ("context_provider", "opendesign"),
        ("context_provider", "previous_run"),
        ("compaction", "html_skeleton"),
        ("post_step", "revision_validation"),
    ]:
        impl = reg.resolve(kind, name)
        assert getattr(impl, "name", None) == name


def test_membership_path_is_impl_free_at_import() -> None:
    # The compiler's INV-4 membership path (is_registered over _KNOWN) must hold
    # with NO impl bound. Importing the registry module alone (this test does not
    # call discover()) must not have bound impls for the known names — the
    # membership check is a pure set lookup.
    reg = CapabilityRegistry()
    # is_registered never consults _IMPLS — pure _KNOWN membership.
    assert reg.is_registered("strategy", "single_shot") is True
    assert reg.is_registered("strategy", "nonexistent") is False


def test_install_is_deleted() -> None:
    # INV-12: install()/_register_builtins() are deleted — discover() is the single
    # successor, not a parallel path.
    assert not hasattr(registry_mod, "install")
    assert not hasattr(registry_mod, "_register_builtins")
