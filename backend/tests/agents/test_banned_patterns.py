"""Banned-pattern ratchet — INV-13 / R15 (003 SAFE-06, D-14/D-15).

This is a CI *ratchet*, not a behavior test. It machine-enforces the project's
single most load-bearing runtime invariant:

    INV-13 — every agent runs on the LangChain ``deepagents`` library
    (``from deepagents import create_deep_agent``). No hand-rolled deep agent,
    no local ``deepagents`` / ``langchain_deepagents`` module, no re-implemented
    agent loop. (003 plan §3 INV-13, §3 R15.)

It scans our first-party source (``backend/app`` + ``backend/agents``) for the
forbidden shapes of a *re-implemented* deep agent and fails CI if any reappear.
The ONE sanctioned ``create_deep_agent`` import — the ``langchain_deepagents``
adapter in ``app/agents/deep_agent_runner.py`` — is explicitly allow-listed; a
``create_deep_agent`` import anywhere else is a violation.

Grounding (verified on the current tree before authoring — re-verify if it
drifts):
  * The legacy ``app/agents/deep_agent.py`` (with ``class DeepAgent`` /
    ``def deep_agent``) was REMOVED in the 002 migration and does NOT exist
    today. Therefore there is NOTHING to allow-list for those hard-bans — they
    must return ZERO matches on the current tree, and NO allow-list entry is
    added for a (non-existent) legacy file.
  * The only real ``from deepagents import create_deep_agent`` statement lives
    at ``app/agents/deep_agent_runner.py``. Every other textual mention of
    ``create_deep_agent`` in the tree is inside a ``#`` comment / docstring /
    reStructuredText literal — the scanners below ignore comment/docstring text
    by matching only executable import/call/def/class statements.

Non-vacuity (T-04-02 mitigation): because the hard-bans currently match nothing,
a broken scanner (e.g. a regex that never matches) would pass silently and give
false confidence. ``test_gate_catches_injected_hand_rolled_agent`` injects a
known-bad ``class DeepAgent`` fixture into a temp dir and asserts the SAME
scanner reports a violation — proving the gate actually fires on a regression.

INV-1 reservation (``if pipeline_type ==`` / ``spec.id ==``): the L-items that kept
these workflow-name/agent-id branches on the kernel's routed path were DELETED in
07-05. Per D-15 this is now a KERNEL-SCOPED HARD-FAIL (``assert 0`` over
``agents/execution_engine/``) — the SC-001 ratchet. Legit non-routing references
outside the kernel (websocket.py display routing, registry.py ``pipeline_type ==
"custom"``) are intentionally NOT scanned.

Offline / unmarked — runs in CI (no ``requires_api_key``).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

# tests/agents/test_banned_patterns.py -> backend/ (parents[2]); the scanned
# first-party source lives under backend/app and backend/agents.
_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_SCAN_ROOTS = (_BACKEND_ROOT / "app", _BACKEND_ROOT / "agents")

# The KERNEL — the workflow-agnostic runtime. INV-1 (SC-001) is a property of the
# kernel's ROUTED execution path: post-07-05 it has ZERO workflow-name/agent-id
# branches. The INV-1 hard-fail below is scoped HERE (not the whole first-party
# tree) so legit NON-kernel references survive (websocket.py display routing,
# registry.py ``pipeline_type == "custom"``) — those are not routed-path dispatch.
_KERNEL_ROOT = _BACKEND_ROOT / "agents" / "execution_engine"

# The ONE sanctioned ``langchain_deepagents`` adapter — the only file permitted
# to import/call ``create_deep_agent``. Stored relative to the backend root so
# the allow-list is location-stable. (Minimal by design: no legacy
# ``deep_agent.py`` entry — that file does not exist.)
_ALLOWED_CREATE_DEEP_AGENT = frozenset({"app/agents/deep_agent_runner.py"})

# ---------------------------------------------------------------------------
# HARD BANS — any match (outside the allow-list) fails CI immediately.
#
# Each regex targets an executable STATEMENT shape, so comments/docstrings that
# merely *mention* a banned token do not trip the gate. We additionally strip
# obvious comment/docstring lines before matching (see ``_is_code_line``).
# ---------------------------------------------------------------------------
_BAN_HAND_ROLLED_CLASS = re.compile(r"^\s*class\s+DeepAgent\b")
_BAN_HAND_ROLLED_FN = re.compile(r"^\s*(?:async\s+)?def\s+deep_agent\b")
# A bespoke, hand-rolled agent loop (the re-implemented iteration the deepagents
# library exists to replace).
_BAN_BESPOKE_LOOP = re.compile(r"for\s+_\s+in\s+range\(\s*max_iterations")
# Any ``create_deep_agent`` import OR call — sanctioned only in the adapter.
_RE_CREATE_DEEP_AGENT_IMPORT = re.compile(
    r"^\s*from\s+deepagents\s+import\s+[^\n]*\bcreate_deep_agent\b"
)
_RE_CREATE_DEEP_AGENT_CALL = re.compile(r"\bcreate_deep_agent\s*\(")

# Forbidden NEW local modules/packages shadowing the library.
_FORBIDDEN_LOCAL_MODULE_NAMES = ("deepagents", "langchain_deepagents")

# The ONE sanctioned ``langchain_deepagents``-named module — the F5 runtime adapter
# capability (08-05). ``langchain_deepagents`` is the registered ``runtime`` capability
# ID (``@register("runtime", "langchain_deepagents")``), so the capability impl file
# carries that name by design. It is NOT a library shadow: it lives DEEP in the
# capability tree (``agents/capabilities/runtimes/langchain_deepagents.py``, imported
# only as ``agents.capabilities.runtimes.langchain_deepagents`` — never as a top-level
# ``langchain_deepagents``), it imports NEITHER ``deepagents`` NOR ``create_deep_agent``,
# and it re-implements NO agent loop (it delegates construction to the factory build
# seam, which routes to the allow-listed ``deep_agent_runner.py``). The ban's purpose —
# forbidding a local module that could PROVIDE a hand-rolled agent loop masquerading as
# the real import — is preserved: every other ``deepagents``/``langchain_deepagents``-
# named file/dir is still banned, and the create_deep_agent/hand-rolled-loop bans below
# still scan this file (it must stay loop-free). Stored backend-relative for stability.
_ALLOWED_LOCAL_MODULE_PATHS = frozenset(
    {"agents/capabilities/runtimes/langchain_deepagents.py"}
)

# INV-1 reservation — HARD-FAIL since Phase 7 (07-05, D-15). The L1-L13 leaks that
# kept ``if pipeline_type ==`` / ``spec.id ==`` workflow-name/agent-id branches on the
# kernel's routed path were DELETED in 07-05; the kernel now routes purely through the
# capability registry. This pattern must therefore return ZERO matches in the KERNEL
# (``agents/execution_engine/``). It is NOT scanned over the whole first-party tree:
# legit non-routing references survive outside the kernel (websocket.py display routing,
# registry.py ``pipeline_type == "custom"``). Reintroducing a kernel name/id branch
# fails CI (SC-001 ratchet).
_INV1_PATTERN = re.compile(r"if\s+pipeline_type\s*==|spec\.id\s*==")


def _iter_py_files(*roots: Path):
    for root in roots:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            yield path


def _is_code_line(line: str) -> bool:
    """Cheap filter: skip whole-line comments. (Statement-anchored regexes plus
    this filter keep the scanners from tripping on commentary that merely
    mentions a banned token.)"""
    stripped = line.lstrip()
    return bool(stripped) and not stripped.startswith("#")


def _rel(path: Path) -> str:
    """Backend-relative posix path for first-party files; absolute fallback for
    paths outside the backend root (e.g. the injected tmp_path fixture in the
    non-vacuity test)."""
    try:
        return path.relative_to(_BACKEND_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _scan(pattern: re.Pattern[str], *roots: Path) -> list[tuple[str, int, str]]:
    """Return (relpath, lineno, line) for every code line matching ``pattern``."""
    hits: list[tuple[str, int, str]] = []
    for path in _iter_py_files(*roots):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if _is_code_line(line) and pattern.search(line):
                hits.append((_rel(path), lineno, line.strip()))
    return hits


# ===========================================================================
# HARD BANS
# ===========================================================================


def test_no_hand_rolled_deep_agent_class() -> None:
    """No ``class DeepAgent`` anywhere in first-party source (INV-13).

    The legacy class was removed in the 002 migration; this is a ratchet that
    keeps it gone. ZERO matches expected on the current tree (no allow-list)."""
    hits = _scan(_BAN_HAND_ROLLED_CLASS, *_SCAN_ROOTS)
    assert not hits, (
        "INV-13: hand-rolled `class DeepAgent` is banned — every agent must run "
        "on `from deepagents import create_deep_agent`. Offenders:\n"
        + "\n".join(f"  {p}:{n}: {ln}" for p, n, ln in hits)
    )


def test_no_hand_rolled_deep_agent_function() -> None:
    """No ``def deep_agent`` factory function (INV-13). ZERO matches expected."""
    hits = _scan(_BAN_HAND_ROLLED_FN, *_SCAN_ROOTS)
    assert not hits, (
        "INV-13: hand-rolled `def deep_agent` is banned. Offenders:\n"
        + "\n".join(f"  {p}:{n}: {ln}" for p, n, ln in hits)
    )


def test_no_bespoke_agent_loop() -> None:
    """No bespoke ``for _ in range(max_iterations)`` agent loop (INV-13/R15).

    The deepagents library owns the agent loop; re-implementing it is exactly
    the R15 risk. ZERO matches expected on the current tree."""
    hits = _scan(_BAN_BESPOKE_LOOP, *_SCAN_ROOTS)
    assert not hits, (
        "INV-13/R15: a hand-rolled `for _ in range(max_iterations)` agent loop "
        "is banned — the agent loop lives in the deepagents library. Offenders:\n"
        + "\n".join(f"  {p}:{n}: {ln}" for p, n, ln in hits)
    )


def test_no_local_deepagents_module() -> None:
    """No NEW local module/package shadowing the library (INV-13).

    A file/dir named ``deepagents`` or ``langchain_deepagents`` under our source
    tree would let a hand-rolled implementation masquerade as the real import.
    The deepagents runner adapter is ``deep_agent_runner.py``; the F5 runtime
    *capability* (08-05) is named ``langchain_deepagents.py`` (its registered
    ``runtime`` capability id) and is the ONE sanctioned exception
    (``_ALLOWED_LOCAL_MODULE_PATHS``) — it imports neither the library nor
    ``create_deep_agent`` and re-implements no loop (the create_deep_agent /
    hand-rolled-loop bans still scan it). Every other such file/dir is banned."""
    offenders: list[str] = []
    for root in _SCAN_ROOTS:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if "__pycache__" in path.parts:
                continue
            stem = path.stem if path.is_file() and path.suffix == ".py" else path.name
            if path.is_dir() or (path.is_file() and path.suffix == ".py"):
                if stem in _FORBIDDEN_LOCAL_MODULE_NAMES:
                    if _rel(path) in _ALLOWED_LOCAL_MODULE_PATHS:
                        continue  # the sanctioned F5 runtime capability (08-05)
                    offenders.append(_rel(path))
    assert not offenders, (
        "INV-13: a local `deepagents`/`langchain_deepagents` module/package is "
        "banned — only the PyPI `deepagents` library may provide it. Offenders:\n"
        + "\n".join(f"  {o}" for o in offenders)
    )


def test_create_deep_agent_only_in_sanctioned_adapter() -> None:
    """`create_deep_agent` may be imported/called ONLY in the adapter (INV-13).

    Allow-list is the SINGLE file ``app/agents/deep_agent_runner.py`` (verified
    the only real call site). Any other file importing or calling it is a
    violation — this is the elevation-of-privilege guard (T-04-02): the
    allow-list is intentionally minimal so a broad allow-list cannot let a real
    hand-rolled agent through."""
    import_hits = _scan(_RE_CREATE_DEEP_AGENT_IMPORT, *_SCAN_ROOTS)
    call_hits = _scan(_RE_CREATE_DEEP_AGENT_CALL, *_SCAN_ROOTS)
    offenders = [
        (p, n, ln)
        for p, n, ln in (import_hits + call_hits)
        if p not in _ALLOWED_CREATE_DEEP_AGENT
    ]
    assert not offenders, (
        "INV-13: `create_deep_agent` is allow-listed ONLY in "
        f"{sorted(_ALLOWED_CREATE_DEEP_AGENT)}. Unsanctioned use:\n"
        + "\n".join(f"  {p}:{n}: {ln}" for p, n, ln in offenders)
    )
    # Positive assertion: the sanctioned adapter DOES use it (guards against the
    # allow-list pointing at a stale/renamed file — keeps the gate honest).
    adapter_uses = [
        p for p, _, _ in (import_hits + call_hits) if p in _ALLOWED_CREATE_DEEP_AGENT
    ]
    assert adapter_uses, (
        "Expected the sanctioned adapter "
        f"({sorted(_ALLOWED_CREATE_DEEP_AGENT)}) to import/call create_deep_agent "
        "— the allow-list anchor is missing; re-verify the adapter path."
    )


# ===========================================================================
# F5 RUNTIME ADAPTER (08-05) — create_deep_agent stays only in the adapter
# ===========================================================================


def test_runtime_adapter_resolves_after_discover() -> None:
    """``resolve("runtime", "langchain_deepagents")`` returns the adapter (F5 / 08-05).

    The factory selects the runner runtime via this registry-resolved adapter; future
    runtimes slot in by registering the same port with no kernel edit."""
    from agents.capabilities.registry import CapabilityRegistry, discover

    discover()
    adapter = CapabilityRegistry().resolve("runtime", "langchain_deepagents")
    assert adapter.name == "langchain_deepagents"
    assert hasattr(adapter, "create")


def test_runtime_capability_does_not_import_app_or_create_deep_agent() -> None:
    """The kernel-side runtime capability is import-clean of ``app``/``create_deep_agent``.

    F5 keeps the canonical ``create_deep_agent`` call inside the allow-listed
    ``app/agents/deep_agent_runner.py``; the runtime *capability* selects/wraps the
    runner via the factory build seam, never importing ``app.*`` (import-linter) nor
    importing/calling ``create_deep_agent`` (INV-13). This asserts the adapter module's
    source carries neither — so the allow-list stays a single, stable entry."""
    adapter_root = _BACKEND_ROOT / "agents" / "capabilities" / "runtimes"
    # Statement-anchored scans (line-by-line, comment lines stripped) — mirrors the
    # production scanners so prose/docstring mentions of the tokens do not false-trip.
    _RE_IMPORT_APP = re.compile(r"^\s*(?:from\s+app\b|import\s+app\b)")
    import_hits = _scan(_RE_CREATE_DEEP_AGENT_IMPORT, adapter_root)
    call_hits = _scan(_RE_CREATE_DEEP_AGENT_CALL, adapter_root)
    app_hits = _scan(_RE_IMPORT_APP, adapter_root)
    assert not app_hits, (
        "F5: the runtime capability must not import app.* (import-linter); it reaches "
        f"runner construction via the factory build seam. Offenders:\n{app_hits}"
    )
    assert not import_hits, (
        "F5: the runtime capability must not import create_deep_agent — it stays in "
        f"the allow-listed deep_agent_runner.py (INV-13). Offenders:\n{import_hits}"
    )
    assert not call_hits, (
        "F5: the runtime capability must not call create_deep_agent — wrap, never "
        f"replace. Offenders:\n{call_hits}"
    )


# ===========================================================================
# PORTS & ADAPTERS BOUNDARY (TEST-008 / ISS-068)
# ===========================================================================

# The import-linter contract "agents.capabilities must not import the execution
# kernel or the web layer" (pyproject.toml [[tool.importlinter.contracts]]) in
# pytest form. It is duplicated HERE on purpose: `lint-imports` is a separate
# binary that must be invoked from `backend/` (run from the repo root it prints
# "Could not read any configuration" and exits, which reads as a pass), so in
# practice nobody runs it and a violation survives. This exact contract was
# broken for ~3 weeks by a single line — see the non-vacuity guard below.
#
# Scope note: this SUPERSETS the `app`-import half of
# `test_runtime_capability_does_not_import_app_or_create_deep_agent` above,
# which is deliberately kept — that assertion is INV-13/F5-scoped (the runtime
# adapter reaches runner construction through the factory build seam) and
# carries its own diagnostic. This one is the architecture boundary itself.
_RE_CAPABILITY_BOUNDARY_IMPORT = re.compile(
    r"^\s*(?:from|import)\s+(?:agents\.execution_engine|app)\b"
)
_CAPABILITIES_ROOT = _BACKEND_ROOT / "agents" / "capabilities"


def test_capabilities_do_not_import_kernel_or_web_layer() -> None:
    """No module under ``agents/capabilities/`` may import the kernel or ``app`` .

    Ports & Adapters: the kernel depends only on capability ports, and a capability
    reaches kernel/app primitives ONLY through the D-03 handle (``ctx.runner`` /
    ``KernelServices``). A direct import inverts the dependency and drags the web
    layer into the capability tree.

    ISS-068: ``strategies/task_loop.py`` did
    ``from agents.execution_engine.od_context import get_example_html`` for the
    ``template.html`` revision seed, which transitively pulled in
    ``app.services.od_loader`` — breaking the contract on both forbidden roots at
    once. The port it needed (``KernelServices.template_example``) already existed
    and was already used by ``context_providers/opendesign.py``; it was a one-off
    bypass, not a missing seam. ZERO matches expected."""
    hits = _scan(_RE_CAPABILITY_BOUNDARY_IMPORT, _CAPABILITIES_ROOT)
    assert not hits, (
        "Ports & Adapters: agents.capabilities must not import agents.execution_engine "
        "or app — reach kernel/app primitives through the ctx.runner (KernelServices) "
        "handle instead, adding a port there if one is genuinely missing. This mirrors "
        "the import-linter contract in pyproject.toml; do NOT amend that contract to "
        "record a violation. Offenders:\n"
        + "\n".join(f"  {p}:{n}: {ln}" for p, n, ln in hits)
    )


def test_capability_boundary_gate_catches_the_iss068_violation(tmp_path: Path) -> None:
    """NON-VACUITY: replay the real ISS-068 line and assert the scanner flags it.

    The live tree is clean, so a never-matching regex would pass silently. These are
    the exact statements that broke the contract (``task_loop.py:562`` and the
    transitive ``od_context.py:26``), plus a plain kernel import."""
    bad = tmp_path / "rogue_capability.py"
    bad.write_text(
        "def seed(runner, tid):\n"
        "    from agents.execution_engine.od_context import get_example_html\n"
        "    return get_example_html(tid)\n"
        "from app.services import od_loader\n"
        "import agents.execution_engine\n",
        encoding="utf-8",
    )
    hits = _scan(_RE_CAPABILITY_BOUNDARY_IMPORT, tmp_path)
    assert len(hits) == 3, (
        "NON-VACUITY FAILURE: the capability-boundary scanner did not flag the "
        f"injected ISS-068 imports — the gate would not catch a real regression. "
        f"Expected 3 hits, got {len(hits)}: {hits}"
    )


def test_capability_boundary_gate_ignores_lookalikes(tmp_path: Path) -> None:
    """A commented import, a sibling capability import, and modules whose names merely
    START with ``app`` must NOT trip the boundary gate (guards the false-red direction —
    ``agents/capabilities/`` legitimately imports its own subpackages everywhere)."""
    benign = tmp_path / "benign.py"
    benign.write_text(
        "# from agents.execution_engine.od_context import get_example_html\n"
        "from agents.capabilities.registry import CapabilityRegistry\n"
        "from application_config import settings\n"
        "import appdirs\n",
        encoding="utf-8",
    )
    assert not _scan(_RE_CAPABILITY_BOUNDARY_IMPORT, tmp_path), (
        "FALSE POSITIVE: the capability-boundary gate tripped on a comment, a sibling "
        "capability import, or an `app`-prefixed third-party module."
    )


# ===========================================================================
# NON-VACUITY GUARD (T-04-02) — prove the scanner actually fires
# ===========================================================================


def test_gate_catches_injected_hand_rolled_agent(tmp_path: Path) -> None:
    """Inject a known-bad ``class DeepAgent`` and assert the SAME scanner flags it.

    Because the hard-bans match nothing on the clean tree, this is the proof the
    gate is NON-VACUOUS: a broken/never-matching scanner would let a real
    regression through. We write a hand-rolled deep agent into a temp dir and run
    the identical class/loop scanners over it; both MUST report the violation."""
    bad = tmp_path / "rogue_agent.py"
    bad.write_text(
        "class DeepAgent:\n"
        "    def __init__(self):\n"
        "        self.max_iterations = 5\n"
        "    def run(self):\n"
        "        for _ in range(max_iterations):\n"
        "            pass\n",
        encoding="utf-8",
    )

    class_hits = _scan(_BAN_HAND_ROLLED_CLASS, tmp_path)
    loop_hits = _scan(_BAN_BESPOKE_LOOP, tmp_path)

    assert class_hits, (
        "NON-VACUITY FAILURE: the `class DeepAgent` scanner did not flag an "
        "injected hand-rolled agent — the gate would not catch a real regression."
    )
    assert loop_hits, (
        "NON-VACUITY FAILURE: the bespoke-agent-loop scanner did not flag an "
        "injected `for _ in range(max_iterations)` loop."
    )


def test_gate_ignores_comment_mentions(tmp_path: Path) -> None:
    """A banned token inside a comment/docstring must NOT trip the hard-bans.

    Guards against the opposite failure mode (false-red on the many legitimate
    docstring/comment mentions of `create_deep_agent` / `DeepAgent` in the
    adapter + chat_runner). Mirrors why the live tree is green."""
    benign = tmp_path / "benign.py"
    benign.write_text(
        "# class DeepAgent — historical note, not real code\n"
        '"""Docstring mentioning create_deep_agent and class DeepAgent."""\n'
        "x = 1\n",
        encoding="utf-8",
    )
    assert not _scan(_BAN_HAND_ROLLED_CLASS, tmp_path), (
        "FALSE POSITIVE: a commented/docstring `class DeepAgent` mention tripped "
        "the hard-ban; the scanner must match executable statements only."
    )


# ===========================================================================
# INV-1 RESERVATION — HARD-FAIL since Phase 7 (07-05, D-15), KERNEL-SCOPED
# ===========================================================================


def test_inv1_no_kernel_workflow_name_branch() -> None:
    """INV-1 (SC-001) HARD-FAIL: ZERO `if pipeline_type ==` / `spec.id ==` in the kernel.

    The L1-L13 leaks that kept workflow-name/agent-id branches on the kernel's routed
    path were DELETED in 07-05; the kernel now knows NO workflow by name and routes
    purely through the capability registry. This is the SC-001 core-value ratchet:
    reintroducing a kernel name/id branch fails CI. Scoped to the KERNEL
    (``agents/execution_engine/``) so legit non-routing references survive elsewhere
    (websocket.py display routing, registry.py ``pipeline_type == "custom"``)."""
    hits = _scan(_INV1_PATTERN, _KERNEL_ROOT)
    assert not hits, (
        "INV-1 (SC-001): a workflow-name/agent-id branch is back in the kernel "
        "(agents/execution_engine/). The kernel must know NO workflow by name — "
        "route via the capability registry (resolve(kind, name)), never by workflow "
        "identity. Offenders:\n"
        + "\n".join(f"  {p}:{n}: {ln}" for p, n, ln in hits)
    )


def test_inv1_gate_is_non_vacuous(tmp_path: Path) -> None:
    """Non-vacuity: the INV-1 scanner actually fires on an injected name branch.

    Because the kernel is now clean, a broken/never-matching scanner would pass
    silently. Inject a known-bad ``if pipeline_type ==`` / ``spec.id ==`` line into a
    temp file and assert the SAME scanner flags it — proving the hard-fail above would
    catch a real regression."""
    bad = tmp_path / "rogue_kernel.py"
    bad.write_text(
        "def route(pipeline_type, spec):\n"
        "    if pipeline_type == \"prototype\":\n"
        "        return 1\n"
        "    if spec.id == \"prototype-build\":\n"
        "        return 2\n",
        encoding="utf-8",
    )
    hits = _scan(_INV1_PATTERN, tmp_path)
    assert hits, (
        "NON-VACUITY FAILURE: the INV-1 scanner did not flag an injected "
        "`if pipeline_type ==` / `spec.id ==` branch — the kernel hard-fail would "
        "not catch a real regression."
    )


# ===========================================================================
# SC-001 COMPLIANCE — Property 4 (task 7.2)
# Validates: Requirements 8.1, 8.2, 8.3, 8.4
#
# Property 4: SC-001 compliance — the execution kernel must contain ZERO
# occurrences of:
#   (a) ``if pipeline_type ==`` dispatch branches (already covered by the
#       INV-1 tests above; repeated here in a class for explicit labelling)
#   (b) any literal revision pipeline-type name
#       (``prototype_revision`` / ``prototype_large_revision`` /
#       ``prototype_feature_revision``) — these names must NEVER appear in
#       the kernel because the kernel is workflow-agnostic (SC-001).
#
# Scoped to ``agents/execution_engine/`` only (same as the INV-1 ratchet) so
# legitimate references in websocket.py display routing, registry.py custom-
# pipeline checks, and the test files themselves do not false-trip.
# ===========================================================================

# Pattern for the revision pipeline-type literal names.  We intentionally do
# NOT use a word-boundary anchor on the right: ``prototype_revision_foo``
# would still be a violation if it ever appeared, since no such pipeline type
# should exist in the kernel.
_SC001_REVISION_NAMES = re.compile(
    r"prototype_large_revision|prototype_feature_revision|prototype_revision"
)


class TestSC001RevisionPipelineCompliance:
    """Property 4: SC-001 compliance — zero kernel references to revision pipeline names.

    **Validates: Requirements 8.1, 8.2, 8.3, 8.4**

    The execution_engine kernel must be workflow-agnostic.  Specifically:

    * No ``if pipeline_type ==`` dispatch branch may appear (the INV-1 ratchet
      already enforces this; the test is repeated here as a named property so
      CI failure messages map directly to the SC-001 requirement IDs).
    * No literal revision pipeline-type name may appear:
      ``prototype_revision``, ``prototype_large_revision``,
      ``prototype_feature_revision``.  The presence of any such name would
      indicate the kernel has a hard-coded workflow-specific code path — a
      direct violation of SC-001.
    """

    # ------------------------------------------------------------------
    # 4a — ``if pipeline_type ==`` check (SC-001 / Requirements 8.3)
    # ------------------------------------------------------------------

    def test_no_pipeline_type_branch_in_kernel(self) -> None:
        """Zero ``if pipeline_type ==`` / ``spec.id ==`` branches in the kernel.

        Requirements 8.3 — the engine must dispatch through the capability
        registry, never by workflow identity."""
        hits = _scan(_INV1_PATTERN, _KERNEL_ROOT)
        assert not hits, (
            "SC-001 / Req 8.3: a workflow-name dispatch branch (`if pipeline_type ==` "
            "or `spec.id ==`) was found in agents/execution_engine/. The kernel must "
            "remain workflow-agnostic — route via the capability registry. Offenders:\n"
            + "\n".join(f"  {p}:{n}: {ln}" for p, n, ln in hits)
        )

    def test_no_pipeline_type_branch_gate_is_non_vacuous(
        self, tmp_path: Path
    ) -> None:
        """Non-vacuity: scanner fires on an injected ``if pipeline_type ==`` line."""
        bad = tmp_path / "rogue_kernel.py"
        bad.write_text(
            "def route(pipeline_type):\n"
            '    if pipeline_type == "prototype_revision":\n'
            "        return True\n",
            encoding="utf-8",
        )
        hits = _scan(_INV1_PATTERN, tmp_path)
        assert hits, (
            "NON-VACUITY FAILURE: the SC-001 `if pipeline_type ==` scanner did not "
            "flag the injected branch — the gate would not catch a regression."
        )

    # ------------------------------------------------------------------
    # 4b — revision pipeline-type literal names (SC-001 / Requirements 8.1, 8.2, 8.4)
    # ------------------------------------------------------------------

    def test_no_revision_pipeline_names_in_kernel(self) -> None:
        """Zero occurrences of revision pipeline-type names in the kernel.

        Requirements 8.1, 8.2, 8.4 — ``prototype_revision``,
        ``prototype_large_revision``, and ``prototype_feature_revision`` must
        never appear as literals inside ``agents/execution_engine/``.  Their
        presence would mean the kernel has a hard-coded reference to a specific
        workflow variant, violating the SC-001 zero-engine-edit guarantee."""
        hits = _scan(_SC001_REVISION_NAMES, _KERNEL_ROOT)
        assert not hits, (
            "SC-001 / Req 8.1–8.2–8.4: a revision pipeline-type name literal "
            "(`prototype_revision`, `prototype_large_revision`, or "
            "`prototype_feature_revision`) was found in agents/execution_engine/. "
            "The kernel must be workflow-agnostic — remove the reference and route "
            "via the capability registry instead. Offenders:\n"
            + "\n".join(f"  {p}:{n}: {ln}" for p, n, ln in hits)
        )

    def test_no_revision_pipeline_names_gate_is_non_vacuous(
        self, tmp_path: Path
    ) -> None:
        """Non-vacuity: scanner fires on each injected revision pipeline-type name."""
        bad = tmp_path / "rogue_engine.py"
        bad.write_text(
            "PIPELINES = [\n"
            '    "prototype_revision",\n'
            '    "prototype_large_revision",\n'
            '    "prototype_feature_revision",\n'
            "]\n",
            encoding="utf-8",
        )
        hits = _scan(_SC001_REVISION_NAMES, tmp_path)
        # All three names must be caught.
        assert len(hits) == 3, (
            "NON-VACUITY FAILURE: the SC-001 revision-name scanner did not flag all "
            f"three injected pipeline names — expected 3 hits, got {len(hits)}: {hits}"
        )
