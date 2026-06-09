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
    Our adapter id is ``langchain_deepagents`` but it is NOT a module name — the
    adapter file is ``deep_agent_runner.py``. ZERO such files expected."""
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
