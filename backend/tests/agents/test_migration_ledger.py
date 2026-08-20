"""CI ratchet for the 003 migration & deletion ledger (DEL-02 / DEL-03 / SAFE-04).

Parses ``specs/003-workflow-engine-decoupling/migration-ledger.md`` (the operational
mirror of plan §31, D-08) and enforces the **move-don't-copy** discipline (INV-12):

* For every ``☑`` row whose deletion gate is a *grep pattern*, grep the row's SCOPE for
  the pattern and assert **0 matches** — once deleted, a symbol may never reappear (ratchet).
* SCOPE (07-05, INV-1 is a KERNEL property): the engine-leak rows **L1–L13** are scoped to
  the kernel (``agents/execution_engine/``) — their bare-token / lifted-construct patterns
  legitimately reappear OUTSIDE the kernel (the capability impls that are the move-don't-copy
  HOMES, e.g. ``_artifact.py`` / ``heading_tasks.py`` / ``html_skeleton.py``; the
  registry's ``REVISION_BASE_MAP``/``PIPELINE_AGENTS``; ``app/`` consumers; tests). Scoping
  to the kernel asserts the LEAK is gone from the runtime kernel without false-failing on
  those legit non-kernel references (SC-001 is a property of the kernel's routed path). The
  state-lift rows **L14/L15** and any non-engine rows stay scoped to the whole ``backend/``
  (they are tree-wide invariants — the deleted prior-agent output mirror dict / the
  ``self._*`` per-run state must be absent everywhere).
* ``☐`` rows are not yet enforced (they reference code that still legitimately exists).
* CHECK rows (prose / ``test:`` gates like "a denial test passes" — L16/F4/F5) are
  yielded as ``(item, None)`` and skipped here; their assertions live in dedicated tests.

The guard is proven **non-vacuous** by ``test_guard_fails_on_known_present_pattern``: the
SAME parse+classify+grep logic is run against a synthetic ``☑`` grep row whose pattern is
known to exist in ``backend/`` — proving the classifier yields real grep rows and the grep
machinery actually fires even while all real rows are ``☐``.

Offline / unmarked — runs in the CI ``backend:characterization`` job (no DB / no API key).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pytest


@dataclass
class _GrepResult:
    """Portable stand-in for the fields of ``subprocess.run(["grep", ...])`` we use."""

    returncode: int
    stdout: str


# Non-source directories that a repo-local Windows dev venv/tooling cache can leave
# under backend/, but which do not exist in the CI checkout that the original Unix
# `grep -rnE ... backend/` command scanned. Excluded so local runs match CI's on-disk
# reality instead of false-failing on the grep target's own dependency source code.
_ALWAYS_EXCLUDED_DIRS = frozenset({".venv", "venv", "__pycache__", ".pytest_cache", ".hypothesis", "node_modules"})


def _portable_grep(
    pattern: str,
    root: Path,
    *,
    include: str = "*.py",
    exclude_dir: str | None = None,
) -> _GrepResult:
    """Cross-platform (Windows/Linux/macOS) equivalent of ``grep -rnE`` over ``*.py`` files.

    Avoids depending on a Unix ``grep`` binary being on PATH (absent on stock Windows),
    which made every grep-gated ledger row a platform/harness failure rather than a real
    signal. Semantics match the prior invocation: recursive, extended regex, one match line
    is enough to report, ``returncode == 0`` iff at least one match was found.
    """
    regex = re.compile(pattern)
    lines: list[str] = []
    for path in root.rglob(include):
        if any(part in _ALWAYS_EXCLUDED_DIRS for part in path.parts):
            continue
        if exclude_dir is not None:
            if exclude_dir in path.parts:
                continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if regex.search(line):
                lines.append(f"{path}:{lineno}:{line}")
    stdout = "\n".join(lines) + ("\n" if lines else "")
    return _GrepResult(returncode=0 if lines else 1, stdout=stdout)

# tests/agents/test_migration_ledger.py → tests/agents → tests → backend → repo root
_REPO = Path(__file__).resolve().parents[3]
_LEDGER = _REPO / "specs/003-workflow-engine-decoupling/migration-ledger.md"
_BACKEND = _REPO / "backend"
# INV-1 is a KERNEL property (SC-001): the engine-leak rows L1-L13 are scoped here so
# the ratchet asserts the leak is gone from the runtime kernel WITHOUT false-failing on
# the legit non-kernel move-don't-copy homes (capability impls / registry / app / tests).
_KERNEL = _BACKEND / "agents" / "execution_engine"
# Item ids whose deletion gate is scoped to the KERNEL (engine leaks, L1-L13). Every
# other ☑ grep row (the L14/L15 state-lift invariants) is scoped to the whole backend/.
_KERNEL_SCOPED_ITEMS = frozenset(
    {"L1", "L2/L9", "L3", "L4/L8", "L5", "L6", "L7", "L10", "L11", "L12", "L13"}
)


def _scope_for(item: str) -> Path:
    """The grep root for a checked row: the kernel for L1-L13, else whole backend/."""
    return _KERNEL if item in _KERNEL_SCOPED_ITEMS else _BACKEND

# Item ids that MUST be present in the ledger (mirror of plan §31; T-03-02 mitigation).
_REQUIRED_ITEMS = [
    "L14", "L16", "D1", "L13", "L1", "L2/L9", "L3", "L4/L8", "L5", "L6",
    "L7", "L10", "L11", "L12", "L15", "D2", "F1", "F2", "F3", "F4", "F5",
    "R1", "D9", "D10", "D11", "IN-02", "FANOUT-PERSIST", "WAVE-PERSIST",
]


def _gate_pattern(gate: str) -> str:
    """Normalise a gate cell into a usable grep pattern: strip surrounding markdown
    backticks (``\\`...\\```) that the ledger wraps identifiers/regexes in."""
    return gate.strip().strip("`").strip()


def _is_check_gate(gate: str) -> bool:
    """A gate cell is a CHECK row (prose assertion) rather than a grep pattern.

    CHECK rows are authored with an explicit marker — the literal token ``CHECK`` or
    ``test:`` — or are empty. Everything else is a real ``grep -rnE`` pattern (an
    identifier, a regex alternation, an ``==`` dispatch reservation, etc.). Using an
    explicit marker (not metacharacter heuristics) keeps single-token grep rows such as
    ``SKIP_PLANNER_FOR_PROTOTYPE`` correctly classified as grep rows.
    """
    g = gate.strip()
    if not g:
        return True
    return "CHECK" in g or "test:" in g


def _parse_rows(ledger_text: str) -> list[tuple[str, str, str]]:
    """Return (item, gate_cell, status_cell) for every data row of the ledger table."""
    rows: list[tuple[str, str, str]] = []
    for line in ledger_text.splitlines():
        if not line.startswith("|"):
            continue
        if "Status" in line or "---" in line:  # header / separator
            continue
        # Split on UNESCAPED table-pipe delimiters, then un-escape `\|` → `|` so a gate
        # cell holding a grep alternation (e.g. L14's `(od_context|completed_tasks|…)`)
        # survives as ONE cell and reaches grep -E with working alternation, instead of
        # being shredded at every `\|` (which truncated L14 to a `gate_agent_ids)` fragment).
        cells = [
            c.strip().replace("\\|", "|")
            for c in re.split(r"(?<!\\)\|", line.strip().strip("|"))
        ]
        if len(cells) < 6:
            continue
        item = cells[0]
        # Status cell is the last cell that carries a ☐/☑ marker (SHA column may follow).
        status = next((c for c in reversed(cells) if "☐" in c or "☑" in c), "")
        if not status:
            continue
        status_idx = max(i for i, c in enumerate(cells) if c is status or c == status)
        gate = cells[status_idx - 1]  # Deletion-gate column sits just before Status
        rows.append((item, gate, status))
    return rows


def _checked_grep_rows(ledger_text: str | None = None) -> list[tuple[str, str | None]]:
    """(item, grep_pattern | None) for ``☑`` rows only.

    CHECK-row gates → ``None`` (skipped by the parametrized test); real grep gates →
    the verbatim pattern. ``☐`` rows are omitted entirely (not yet enforced).
    """
    text = ledger_text if ledger_text is not None else _LEDGER.read_text(encoding="utf-8")
    out: list[tuple[str, str | None]] = []
    for item, gate, status in _parse_rows(text):
        if "☑" not in status:
            continue
        out.append((item, None if _is_check_gate(gate) else _gate_pattern(gate)))
    return out


@pytest.mark.parametrize("item,pattern", _checked_grep_rows() or [("__none__", None)])
def test_deleted_pattern_absent_from_backend(item: str, pattern: str | None) -> None:
    """Each ``☑`` grep row's banned pattern must return 0 matches in ``backend/``."""
    if pattern is None:
        pytest.skip(
            "no ☑ grep rows yet — green/empty in Phase 1 (D-10), "
            "or a CHECK-row gate handled out-of-band"
        )
    scope = _scope_for(item)
    # `evals/` is excluded deliberately: it is a standalone offline eval
    # harness, not the pipeline runtime this ledger polices. F1's pattern
    # fired on `evals/minimal/run.py`, which assembles its own prompt
    # blocks and has nothing to do with the deepagents move-don't-copy
    # discipline — a false positive that made a real guard look permanently
    # broken.
    #
    # NB: do not quote a banned pattern literally anywhere in this file —
    # the grep scans `backend/` including `tests/`, so a comment naming the
    # token matches itself.
    res = _portable_grep(pattern, scope, exclude_dir="evals")
    scope_label = scope.relative_to(_BACKEND).as_posix() if scope != _BACKEND else "backend/"
    assert res.returncode != 0, (
        f"{item}: banned pattern is back in {scope_label} (move-don't-copy violation):\n"
        f"{res.stdout}"
    )


def test_ledger_parses_and_phase7_flips_all_engine_leaks() -> None:
    """Every §31 item is present; through Phase 7 (07-05) the engine-leak set is ``☑``.

    History: Phase 0B armed L14 (state-lift) + the L16 CHECK row; Phase 1B flipped L15
    (prior-agent output mirror) + D2 (thin-store artifact half). Phase 7 (07-05) deletes
    the L1–L13 engine leaks (the kernel knows no workflow by name — SC-001/INV-1) and flips
    them all to ``☑`` with KERNEL-SCOPED grep gates.

    D1 (``_handle_revision``) was found **live** during 0B — the frontend ``run_revision``
    PPT-revision handler, not dead code — so its deletion is voided/deferred and it stays
    ``☐`` (ledger ‡ note). Phase 3 flips the factory rows in their owning plans:
    08-03 flips F2 (tool-binding switch → ``tool_provider``), 08-05 flips F1/F3/F5
    (prompt policy / skill+hook providers / runtime adapter), and 08-06 flips F4
    (constitution sync-safe pre-warm; R12 ``_mem``-only branch deleted) — so after
    08-06 ALL of F1–F5 are ``☑``.
    """
    text = _LEDGER.read_text(encoding="utf-8")
    rows = _parse_rows(text)
    ids = [item for item, _gate, _status in rows]
    missing = [i for i in _REQUIRED_ITEMS if i not in ids]
    assert not missing, f"ledger drifted from §31 — missing rows: {missing}"
    flipped = sorted(item for item, _g, status in rows if "☑" in status)
    expected = sorted(
        ["L14", "L15", "L16", "D2",  # 0B / 1B
         "L1", "L2/L9", "L3", "L4/L8", "L5", "L6", "L7", "L10", "L11", "L12", "L13",  # 07-05
         "F2",  # 08-03 (Phase 3) — F2 tool-switch lifted to the tool_provider registry
         "F1", "F3", "F5",  # 08-05 (Phase 3) — prompt policy (F1) / skill+hook providers (F3) / runtime adapter (F5)
         "F4",  # 08-06 (Phase 3) — constitution sync-safe pre-warm; R12 _mem-only branch deleted
         "R1",  # 09-02 (Phase 9) — RunSandbox refolded onto a has_git=False Workspace (RUNTIME-02 CHECK)
         "D9",  # 09-06 (Phase 9) — CodingAgent build_model().ainvoke bypass DELETED (bypass-class grep → 0)
         "D10",  # 09-06 (Phase 9) — /api/handoff routers + UserGithubCredential RETAINED-with-justification
         "D11",  # 10-02 (Phase 10) — plan.py ExecutionPolicy forward-surface helper DELETED (INV-12 single surface)
         "IN-02",  # 10-05 (Phase 10) — exec_command shell-exec closed (argv-list, 10-01); permanent no-shell ratchet
         "FANOUT-PERSIST",  # 11-01 (Phase 11) — additive subagent_runs (0019) reversible CHECK row; single 0018→0019 head
         "WAVE-PERSIST"]  # 12-01 (Phase 12) — additive wave_runs (0020) reversible CHECK; single 0019→0020 head
    )
    assert flipped == expected, (
        f"Through Phase 7 + the 08-03 F2 flip + the 08-05 F1/F3/F5 flips + the 08-06 F4 "
        f"flip + the 09-02 R1 RunSandbox-refold flip + the 09-06 D9 CodingAgent-deletion / "
        f"D10 retained-endpoint flips the engine-leak/factory/runtime set + 0B/1B rows must "
        f"be ☑; expected {expected}, found: {flipped} (D1 stays ☐ — voided; F1–F5 all ☑ "
        f"after 08-06; R1 ☑ after 09-02; D9/D10 ☑ after 09-06)"
    )


def test_guard_fails_on_known_present_pattern() -> None:
    """Non-vacuity guard (T-03-01): the ratchet really greps real grep rows.

    Inject a synthetic ``☑`` row whose gate is a token KNOWN to exist in ``backend/``
    (``class ExecutionEngine`` — the kernel sequencer, never deleted). Run the SAME
    parse+classify logic and assert: (1) it is classified as a grep row (pattern is not
    None), and (2) the grep machinery actually FINDS it — i.e. the deletion assertion
    WOULD fail. This proves the guard is not vacuously green. (The prior anchor
    ``_PROTOTYPE_PIPELINE_TYPES`` was a real L1 leak DELETED in 07-05, so it can no longer
    serve as a known-present token.)
    """
    present_token = "class ExecutionEngine"
    synthetic = (
        "| Item | Legacy | New home | Phase | Deletion gate (grep → 0 / check) | Status |\n"
        "|---|---|---|---|---|---|\n"
        f"| FAKE | x | y | 9 | {present_token} | ☑ |\n"
    )
    rows = _checked_grep_rows(synthetic)
    assert rows == [("FAKE", present_token)], (
        f"classifier failed to yield the synthetic grep row: {rows}"
    )
    _item, pattern = rows[0]
    assert pattern is not None, "a real grep gate was misclassified as a CHECK row"

    res = _portable_grep(pattern, _BACKEND)
    # returncode 0 == pattern FOUND == the deletion assertion would fail → guard is live.
    assert res.returncode == 0 and res.stdout, (
        "non-vacuity guard broken: known-present token not found in backend/ "
        "(wrong repo-root depth, or grep machinery dead)"
    )


def test_check_rows_classified_as_check() -> None:
    """CHECK rows (L16/F4/F5) must classify as prose, not grep, regardless of status."""
    text = _LEDGER.read_text(encoding="utf-8")
    by_item = {item: gate for item, gate, _status in _parse_rows(text)}
    for check_item in ("L16", "F4", "F5"):
        assert _is_check_gate(by_item[check_item]), (
            f"{check_item} gate should be a CHECK row but was classified as a grep pattern: "
            f"{by_item[check_item]!r}"
        )
    # And a known grep row must classify as a grep pattern (sanity, both directions).
    assert not _is_check_gate(by_item["L5"]), "L5 (SKIP_PLANNER_FOR_PROTOTYPE) is a grep row"
