"""agents/capabilities/registry.py — self-registering capability registry (MAN-03 / CAP-01..03).

Phase 8 / 08-01 seam: a self-registering ``CapabilityRegistry`` keyed by
``(kind, name)``. A module-level ``@register(kind, name, *, user_allowed=...)``
decorator binds ``(kind,name)->impl`` at module import; a startup ``discover()``
explicitly imports the known capability subpackages so each ``@register`` fires.
The compiler validates every declared capability reference against this registry
(INV-4) — an unknown name is a compile error naming the bad reference.

Evolution (D-01, INV-12): this REPLACES the Phase-7 explicit eager-binding
routine (the deleted ``install``/``_register_builtin`` spelling). ``discover()``
is its single successor — NOT a parallel path. The old eager binder is DELETED.

Scope guards:
  - ``_KNOWN`` is the compiler's pure-membership INV-4 surface (``is_registered``)
    and the declared allow-list ``@register`` validates against. It is a literal
    populated at registry-module import (impl-free) so the compiler path can
    validate manifest references WITHOUT any impl being bound
    (``test_registry_capabilities.py`` asserts no impls at compiler import).
    ``@register`` may ADD a ``(kind,name)`` pair (e.g. the new
    ``tool``/``skill``/``hook``/``runtime`` kinds whose names land in later
    plans) — there is no central if/elif over KIND strings; KINDs are free
    strings keyed in ``_KNOWN``.
  - ``discover()`` imports the impl modules — invoked LAZILY at engine import /
    first ``execute()`` / first ``resolve``, NEVER at compiler import (Pattern 3 /
    D-01). The compiler imports this module for ``is_registered`` only; the impl
    subpackages are dragged in only by ``discover()``.
  - ``resolve(kind, name)`` is a STATIC dict lookup over ``_KNOWN``-validated
    names — it performs no dynamic name resolution of any kind (no attribute
    fetch, no expression evaluation, no dynamic import) (T-04-01 / T-07-01-01).
  - Per-capability ``user_allowed`` trust flags live in ``_TRUST`` (D-02): the
    compiler trust check (CAP-03) keeps ``exec``/``secrets``/``spawn_subagents``
    off the user palette.
  - The ``od_prototype -> prototype`` id-alias is lifted from the single source of
    truth in ``agents.registry`` (``_OD_ALIAS_BASE``); it is NOT re-hardcoded here.

Mirrors the module-level-data + accessor idiom of ``agents/registry.py``.
"""

from __future__ import annotations

import logging
from typing import Callable, TypeVar

# Single source of truth for the od_* id alias (od_prototype -> prototype).
# Lifted, not redefined — do NOT inline the alias map here (MAN-05 / D-04).
from agents.registry import _OD_ALIAS_BASE

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Known capability names — the authoritative (kind, name) membership pairs.
#
# This literal is the compiler's INV-4 pure-membership surface (``is_registered``)
# AND the declared allow-list ``@register`` validates against. It is populated at
# registry-module IMPORT (impl-free) so the compiler can validate manifest
# references with zero impls bound. ``@register`` may ADD a pair (the new
# ``tool``/``skill``/``hook``/``runtime`` kinds land their names in 08-02..08-07).
#
# strategy:        single_shot, task_loop
# merge:           copy_disjoint, git_3way, json, html_fragment  (11-03 / FANOUT-07, user_allowed=True)
# validator:       html_static, html_render, spec_plan_coverage, task_done_when, design_quality  (08-04)
#                  code_compile, code_test, code_lint  (10-04 / EXEC-02 — exec via the handle)
#                  api_prefix  (19-02 / ISS-005 — infra /api/v1 backstop, user_allowed=True)
# deliverable:     single_file, serialized_sandbox, streamed_text, ppt
# context_provider: opendesign, previous_run, repo (09-03), uploaded_files (30-02 / UPLD-03)
# input_provider:  run_images  (260707-edw — image-input Wave 1, user_allowed=True)
# task_parser:     heading_tasks
# gate:            human, validation, approval, security, conditional  (08-02, spec 014 / T17)
# tool:            workspace, prototype, prototype_emit_only, planning  (08-03 / F2)
# compaction:      html_skeleton
# post_step:       revision_validation, api_prefix_audit  (19-02 / ISS-005 — event-free infra audit)
# model_catalog:   default  (the ModelCatalog data capability — name-only, D-03)
# runtime:         langchain_deepagents  (08-05 / F5 — AgentRuntimeAdapter, wraps DeepAgentRunner)
# prompt:          default  (08-05 / F1 — PromptAssemblyPolicy, fixed block order)
# skill:           ui, disk, template, repo  (08-05 / F3 / SKILL-01 — versioned skill providers)
# hook:            behavioral  (08-05 / F3 — non-executable hook sub-type)
#                  secret_scan, otel_tracing  (08-07 / HOOK-01..04 / OBS-02 — executable hooks)
#                  audit_logger  (KAN-73 — default lifecycle audit hook, user_allowed=True)
# ---------------------------------------------------------------------------
_KNOWN: set[tuple[str, str]] = {
    ("strategy", "single_shot"),
    ("strategy", "task_loop"),
    ("strategy", "fanout_batch"),      # 11-01 / FANOUT-02 (user_allowed=True)
    ("strategy", "wave_scheduler"),    # 12-01 / WAVE-01 (user_allowed=True)
    ("strategy", "parallel_group"),    # subagents.mode: parallel (user_allowed=True)
    ("merge", "copy_disjoint"),        # 11-03 / FANOUT-07 (user_allowed=True)
    ("merge", "git_3way"),             # 11-03 / FANOUT-07 (user_allowed=True)
    ("merge", "json"),                 # 11-03 / FANOUT-07 (user_allowed=True)
    ("merge", "html_fragment"),        # 11-03 / FANOUT-07 (user_allowed=True)
    ("validator", "html_static"),
    ("validator", "html_render"),
    ("validator", "spec_plan_coverage"),   # 08-04 / Tier#4
    ("validator", "api_prefix"),           # 19-02 / ISS-005 — infra /api/v1 backstop (user_allowed=True)
    ("validator", "task_done_when"),       # 08-04 / Tier#5
    ("validator", "design_quality"),       # 08-04 / Tier#6 (warnings-first)
    ("validator", "code_compile"),         # 10-04 / EXEC-02 — py_compile via the exec handle
    ("validator", "code_test"),            # 10-04 / EXEC-02 — pytest via the exec handle
    ("validator", "code_lint"),            # 10-04 / EXEC-02 — ruff check via the exec handle
    ("deliverable", "single_file"),
    ("deliverable", "serialized_sandbox"),
    ("deliverable", "streamed_text"),
    ("deliverable", "ppt"),
    ("deliverable", "repo_diff"),          # 09-04 / REPO-04 — brownfield diff-only resolver
    ("context_provider", "opendesign"),
    ("context_provider", "previous_run"),
    ("input_provider", "run_images"),  # 260707-edw — image-input Wave 1 (user_allowed=True)
    ("task_parser", "heading_tasks"),
    ("task_parser", "json_tasks"),     # 12-01 / WAVE-02 (structured task list)
    ("gate", "human"),
    ("gate", "validation"),
    ("gate", "approval"),   # 08-02
    ("gate", "security"),   # 08-02
    ("gate", "conditional"),  # spec 014 / T17
    ("tool", "workspace"),             # 08-03 / F2
    ("tool", "prototype"),             # 08-03 / F2
    ("tool", "prototype_emit_only"),   # 08-03 / F2
    ("tool", "planning"),              # 08-03 / F2
    ("tool", "spawn_subagents"),       # 11-01 / FANOUT-01 (user_allowed=False)
    ("compaction", "html_skeleton"),
    ("post_step", "revision_validation"),
    ("post_step", "api_prefix_audit"),     # 19-02 / ISS-005 — event-free infra audit
    ("model_catalog", "default"),
    ("runtime", "langchain_deepagents"),   # 08-05 / F5
    ("prompt", "default"),                 # 08-05 / F1
    ("skill", "ui"),                       # 08-05 / F3 / SKILL-01
    ("skill", "disk"),                     # 08-05 / F3 / SKILL-01
    ("skill", "template"),                 # 08-05 / F3 / SKILL-01
    ("skill", "repo"),                     # 08-05 / F3 / SKILL-01
    ("hook", "behavioral"),                # 08-05 / F3 (non-executable sub-type)
    ("hook", "secret_scan"),               # 08-07 / HOOK-01..04 (executable, blocking)
    ("hook", "otel_tracing"),              # 08-07 / OBS-02 (executable, non-blocking)
    ("hook", "audit_logger"),              # KAN-73 (executable, non-blocking, default lifecycle audit)
    ("runtime_env", "local"),              # 09-01 / RUNTIME-01 — LocalSandboxRuntime (ECS-swap seam)
    ("repo_index", "tree_sitter"),         # 09-03 / REPO-02 — app-side symbol index (tree-sitter isolated)
    ("repo_inventory", "default"),         # 09-03 / REPO-01 — kernel-side stdlib inventory
    ("context_pack", "default"),           # 09-03 / REPO-03 — kernel-side targeted context subset
    ("context_provider", "repo"),          # 09-03 / REPO-03 — surfaces the ContextPack to agents
    ("context_provider", "uploaded_files"), # 30-02 / UPLD-03 — sticky uploaded-doc context
    ("compaction", "chat_history"),        # 33 / D-08 — bound composed chat history
    ("context_provider", "conversation"),  # 33 / D-08 — compacted chat run_events as context
    ("chat", "concierge"),                 # 33 / D-05 (new KIND — free string, no if/elif)
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
}


# ---------------------------------------------------------------------------
# (kind, name) -> impl instance map + per-capability trust flags (D-01/D-02).
#
# ``_IMPLS`` is SEPARATE from ``_KNOWN`` (the compiler membership set) on purpose:
# ``_KNOWN`` must validate manifest references at compiler import time WITHOUT any
# impl being bound. ``_IMPLS`` is populated by ``@register`` at IMPL-module import,
# which only happens inside ``discover()`` — at engine import / first ``execute()``
# / first ``resolve``, never at compiler import. ``resolve`` looks up THIS map (a
# fixed dict — no dynamic name resolution, T-07-01-01).
#
# ``_TRUST`` records the ``user_allowed`` flag per ``(kind, name)`` (D-02): the
# compiler trust check (CAP-03) keeps privileged capabilities off the user palette.
# ---------------------------------------------------------------------------
_IMPLS: dict[tuple[str, str], object] = {}
_TRUST: dict[tuple[str, str], bool] = {}
# Per-capability display metadata (D-08). Sibling to ``_TRUST``: a SINGLE source
# of truth for the palette's ``description`` + ``config_schema``, recorded by the
# ``@register`` decorator at impl-module import (inside ``discover()``). The API
# layer projects this via ``describe`` — there is deliberately NO static metadata
# map in ``app/api/`` (that would be a second hardcoded source eroding SC-001: a
# newly ``@register``'d capability would appear in the live ``_KNOWN`` enumeration
# but WITHOUT metadata).
_META: dict[tuple[str, str], dict] = {}
_DISCOVERED = False


_T = TypeVar("_T")


def register(
    kind: str,
    name: str,
    *,
    user_allowed: bool = False,
    description: str = "",
    config_schema: dict | None = None,
) -> Callable[[type[_T]], type[_T]]:
    """Self-registration decorator: bind ``(kind,name)->impl`` at module import (D-01).

    Decorate a stateless capability impl CLASS. At import the decorator:
      * adds ``(kind, name)`` to ``_KNOWN`` (the declared membership/allow-list —
        no central if/elif over kinds; the new ``tool``/``skill``/``hook``/
        ``runtime`` kinds register here too);
      * instantiates the class once and binds the instance into ``_IMPLS``;
      * records ``user_allowed`` into ``_TRUST`` (D-02 — privileged capabilities
        default ``user_allowed=False`` and stay off the user palette);
      * records ``description`` + ``config_schema`` into ``_META`` (D-08 — the
        single source of truth the ``/api/capabilities`` palette projects). Both
        are additive-optional (D-09): ``description`` defaults to ``""`` and
        ``config_schema`` to ``{}`` for capabilities that author no metadata, so
        the thin one-method Protocol ports stay unchanged.

    Built-ins decorate their existing Phase-7 impl classes so ``discover()``
    reproduces the exact ``_IMPLS`` set the deleted ``install()`` produced (INV-12).
    The decorator returns the class UNCHANGED (the binding is the side effect).
    """

    def _decorate(cls: type[_T]) -> type[_T]:
        _KNOWN.add((kind, name))
        _IMPLS[(kind, name)] = cls()
        _TRUST[(kind, name)] = user_allowed
        _META[(kind, name)] = {
            "description": description,
            "config_schema": config_schema or {},
        }
        return cls

    return _decorate


def discover() -> None:
    """Import the known capability subpackages so every ``@register`` fires (D-01).

    The single successor to the deleted ``install()`` (INV-12). Explicitly imports
    the in-tree capability subpackages — NO namespace/package auto-walk, NO
    entry-point magic (D-01 rejects auto-discovery: non-deterministic ordering,
    pulls unintended modules, the import-linter cannot reason about it). Also
    imports the app-side ``app/agents/validators/`` package (the only app-side
    capability package) so the heavy-dep validators self-register without the
    kernel importing ``app.*`` directly (the registry IMPORTS the package to
    trigger its ``@register``; the validators import the kernel PORT, the legal
    direction — D-04).

    Idempotent (a flag guards re-invocation). Invoked LAZILY — at engine import /
    first ``execute()`` / first ``resolve`` — NEVER at compiler import, so the
    compiler's membership-only path (``is_registered`` over ``_KNOWN``) stays
    honest with zero impls bound (``test_registry_capabilities.py``).
    """
    global _DISCOVERED
    if _DISCOVERED:
        return
    # Mark discovered FIRST so a re-entrant import (a capability module importing
    # registry at import time) does not recurse into discover().
    _DISCOVERED = True

    import importlib

    # In-tree (kernel-side) capability packages whose modules carry @register.
    # The forward-surface packages (gates/tools/skills/hooks/runtimes/prompt/
    # validators) are created across 08-02..08-07; import them best-effort so a
    # not-yet-created package is a no-op rather than an ImportError.
    _builtin_modules = (
        "agents.capabilities.strategies.single_shot",
        "agents.capabilities.strategies.task_loop",
        "agents.capabilities.strategies.fanout_batch",  # 11-01 / FANOUT-02
        "agents.capabilities.strategies.wave_scheduler",  # 12-01 / WAVE-01
        # subagents.mode: parallel — the sibling-group dispatcher. A thin seam over
        # the SAME run_fanout spawn path as fanout_batch/wave_scheduler (INV-12).
        "agents.capabilities.strategies.parallel_group",
        # 11-03 / FANOUT-07 — the merge layer (port + 4 impls). Import-pure: each
        # reaches git ONLY via the ctx.runner handle, never a capability-side subprocess.
        "agents.capabilities.merge.copy_disjoint",
        "agents.capabilities.merge.git_3way",
        "agents.capabilities.merge.json_merge",
        "agents.capabilities.merge.html_fragment",
        "agents.capabilities.task_parsers.heading_tasks",
        "agents.capabilities.task_parsers.json_tasks",  # 12-01 / WAVE-02
        "agents.capabilities.deliverables.single_file",
        "agents.capabilities.deliverables.serialized_sandbox",
        "agents.capabilities.deliverables.streamed_text",
        "agents.capabilities.deliverables.ppt",
        "agents.capabilities.deliverables.repo_diff",  # 09-04 / REPO-04

        "agents.capabilities.context_providers.opendesign",
        "agents.capabilities.context_providers.previous_run",
        "agents.capabilities.input_providers.run_images",  # 260707-edw — image-input Wave 1
        "agents.capabilities.compaction.html_skeleton",
        "agents.capabilities.post_steps.revision_validation",
        "agents.capabilities.post_steps.api_prefix_audit",  # 19-02 / ISS-005 — event-free infra audit
        # Pure-stdlib kernel-side Tier validators (08-04 / D-05). Imported by module
        # (NOT via the validators package __init__) so importing
        # ``agents.capabilities.validators.severity`` stays @register/discover-clean
        # for the 08-02 gate (08-01 Issues-Encountered: keep severity import-light).
        "agents.capabilities.validators.spec_plan_coverage",
        "agents.capabilities.validators.api_prefix",  # 19-02 / ISS-005 — infra /api/v1 backstop
        "agents.capabilities.validators.task_done_when",
        # 10-04 / EXEC-02 — the three code validators that drive gated exec. They
        # reach exec ONLY via the runner/workspace handle (never spawn directly,
        # never import app.*); kernel-side + pure-stdlib (the argv targets python/
        # pytest/ruff run THROUGH the handle, so no heavy dep is imported here).
        "agents.capabilities.validators.code_compile",
        "agents.capabilities.validators.code_test",
        "agents.capabilities.validators.code_lint",
        # 09-03 / repo-context capabilities (kernel-side, pure-stdlib — reach
        # git/disk only via ctx.runner/ctx.scoped_store handles).
        "agents.capabilities.repo_inventory.inventory",
        "agents.capabilities.context_pack.pack",
        "agents.capabilities.context_providers.repo",
        # 30-02 / UPLD-03 — the uploaded_files context provider (kernel-pure: reads
        # the run's own .uploads sidecar via the ctx.runner handle, never app.*).
        "agents.capabilities.context_providers.uploaded_files",
        # 33 / D-08 — the two kernel-pure bounded-chat-history capabilities (the
        # concierge is NOT here — it is app-side, landing in 33-02). Both reach only
        # the ctx-scoped read surface / the registry, never app.*.
        "agents.capabilities.compaction.chat_history",
        "agents.capabilities.context_providers.conversation",
        # 09-05 / MCP-02 — the allow-listed mcp_server catalog (registration DATA
        # only; the live client is app-side McpClientAdapter).
        "agents.capabilities.mcp_servers.catalog",
        # 09-06 / INTEG-01 — the integration-provider bridge (registration DATA only;
        # each provider bridges a granted integrations scope onto a catalog mcp_server
        # via the SAME prewarm seam — ONE mechanism, no parallel SDK path, D-08).
        "agents.capabilities.integration_providers.providers",
    )
    for mod in _builtin_modules:
        importlib.import_module(mod)

    # Forward-surface capability PACKAGES (created in later plans). A package whose
    # __init__ imports its registered modules fires their @register on import.
    _forward_packages = (
        "agents.capabilities.gates",
        "agents.capabilities.tools",
        "agents.capabilities.skills",
        "agents.capabilities.hooks",
        "agents.capabilities.runtimes",
        "agents.capabilities.prompt",
        "agents.capabilities.validators",
        # App-side capability packages (heavy-dep / app.*-reaching impls, D-04).
        # The registry IMPORTS these to trigger their @register; the impls import
        # the kernel PORT (the legal app->ports direction), never the reverse.
        "app.agents.validators",
        "app.agents.runtime",  # 09-01 / RUNTIME-01 — LocalSandboxRuntime self-registers
        "app.agents.repo_index",  # 09-03 / REPO-02 — tree-sitter symbol index (heavy dep isolated)
        "app.agents.chat",  # 33 / D-05 — chat:concierge self-registers (app-side, DeepAgentRunner)
    )
    for pkg in _forward_packages:
        try:
            importlib.import_module(pkg)
        except ModuleNotFoundError:
            # Package not created yet (lands in a later plan) — best-effort no-op.
            continue
        except ImportError as exc:  # noqa: PERF203 — one broken pkg must not abort all
            # The package EXISTS but failed to import for some other reason (an
            # incompatible optional dependency, a circular import, a syntax error in
            # a sibling module). Degrade to "that package's capabilities are
            # unavailable" rather than aborting ALL registry discovery (IN-03). Logged
            # at warning so the gap is visible, not silent.
            logger.warning(
                "capability discovery: forward package %s failed to import (%s) — "
                "its capabilities are unavailable",
                pkg, exc,
            )
            continue


class CapabilityRegistry:
    """Validates declared capability references and resolves them to impls.

    Paths:
      * ``is_registered(kind, name)`` — the compiler's INV-4 membership check, a
        pure ``_KNOWN`` set lookup. No dynamic name resolution (T-04-01).
      * ``is_user_allowed(kind, name)`` — the CAP-03 trust check: ``True`` iff the
        capability was registered ``user_allowed=True`` (D-02). A capability with
        no recorded trust flag (e.g. the name-only ``model_catalog``) defaults to
        NOT user-allowed.
      * ``resolve(kind, name)`` — the execution seam: a STATIC dict lookup over the
        ``_IMPLS`` map (populated by ``discover()``) returning the bound impl
        instance. Raises on an unknown name BEFORE any lookup, and on a
        known-but-unbound name (a programmer error). Never returns ``None``.
    """

    def is_registered(self, kind: str, name: str) -> bool:
        """Return ``True`` iff ``(kind, name)`` is a known capability."""
        return (kind, name) in _KNOWN

    def is_user_allowed(self, kind: str, name: str) -> bool:
        """Return ``True`` iff the capability is user-grantable (CAP-03 / D-02).

        Ensures impls are discovered so the ``_TRUST`` flag is bound, then reads it.
        A capability with no recorded flag (name-only data capabilities, or an
        unknown reference) defaults to ``False`` — the safe default that keeps
        privileged capabilities off the user palette.
        """
        if not _DISCOVERED:
            discover()
        return _TRUST.get((kind, name), False)

    def describe(self, kind: str, name: str) -> dict:
        """Return the capability's display metadata ``{description, config_schema}`` (D-08).

        Ensures impls are discovered so ``_META`` is bound (mirroring
        ``is_user_allowed``), then reads it. A capability with no recorded
        metadata (name-only data capabilities, or an unknown reference) returns
        the safe default ``{"description": "", "config_schema": {}}`` — never a
        ``KeyError``. This is the SINGLE accessor the ``/api/capabilities``
        palette projects; no static metadata map lives in the API layer.
        """
        if not _DISCOVERED:
            discover()
        return _META.get((kind, name), {"description": "", "config_schema": {}})

    def resolve(self, kind: str, name: str) -> object:
        """Return the impl instance bound to ``(kind, name)`` (D-02).

        Raises ``KeyError`` for an unknown ``(kind, name)`` — checked against
        ``_KNOWN`` FIRST, before any impl lookup, so a name not in the validated
        set never reaches the map (T-07-01-01). Raises ``RuntimeError`` for a known
        name with no bound impl (the impl modules were not discovered, a programmer
        error). This is a pure static dict lookup — no dynamic name resolution.
        """
        if (kind, name) not in _KNOWN:
            raise KeyError(f"unknown capability reference: ({kind!r}, {name!r})")
        # Lazy discover on first resolve so callers need not order discover() themselves.
        if not _DISCOVERED:
            discover()
        try:
            return _IMPLS[(kind, name)]
        except KeyError:  # known name, no impl bound (e.g. an impl not yet landed)
            raise RuntimeError(
                f"capability ({kind!r}, {name!r}) is known but has no bound impl; "
                "call agents.capabilities.registry.discover()"
            ) from None

    def resolve_alias(self, pipeline_type: str) -> str:
        """Resolve an id alias to its base manifest id (MAN-05).

        ``od_prototype`` -> ``prototype``; every real key resolves to itself.
        Sourced from ``agents.registry._OD_ALIAS_BASE`` (single source of truth).
        """
        return _OD_ALIAS_BASE.get(pipeline_type, pipeline_type)
