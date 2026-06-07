"""CI ratchet for the 003 migration & deletion ledger (DEL-02 / DEL-03 / SAFE-04).

Parses ``specs/003-workflow-engine-decoupling/migration-ledger.md`` (the operational
mirror of plan §31, D-08) and enforces the **move-don't-copy** discipline (INV-12):

* For every ``☑`` row whose deletion gate is a *grep pattern*, grep ``backend/`` for the
  pattern and assert **0 matches** — once deleted, a symbol may never reappear (ratchet).
* ``☐`` rows are not yet enforced (they reference code that still legitimately exists).
  In Phase 1 every row is ``☐`` → the parametrized deletion test is green/empty (D-10).
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
import subprocess
from pathlib import Path

import pytest

# tests/agents/test_migration_ledger.py → tests/agents → tests → backend → repo root
_REPO = Path(__file__).resolve().parents[3]
_LEDGER = _REPO / "specs/003-workflow-engine-decoupling/migration-ledger.md"
_BACKEND = _REPO / "backend"

# Item ids that MUST be present in the ledger (mirror of plan §31; T-03-02 mitigation).
_REQUIRED_ITEMS = [
    "L14", "L16", "D1", "L13", "L1", "L2/L9", "L3", "L4/L8", "L5", "L6",
    "L7", "L10", "L11", "L12", "L15", "F1", "F2", "F3", "F4", "F5",
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
    text = ledger_text if ledger_text is not None else _LEDGER.read_text()
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
    res = subprocess.run(
        ["grep", "-rnE", pattern, str(_BACKEND), "--include=*.py"],
        capture_output=True,
        text=True,
    )
    assert res.returncode != 0, (
        f"{item}: banned pattern is back in backend/ (move-don't-copy violation):\n"
        f"{res.stdout}"
    )


def test_ledger_parses_and_phase0b_flips_l14_l16() -> None:
    """Every §31 item is present; Phase 0B flips exactly {L14, L16} to ``☑`` (T-03-02).

    Phase 1 had every row ``☐``. Phase 0B (plan 02-01/02-02) lifts per-run state into
    ``ExecutionContext``, arming the L14 grep ratchet (``☑``). Plan 02-03 wires the explicit
    parent-run ownership check (``assert_owns``) and flips the L16 CHECK row to ``☑`` — L16
    is a CHECK row (its gate is prose referencing the denial test, NOT a grep pattern), so it
    is SKIPPED by the grep ratchet (``_checked_grep_rows`` yields it as ``None``); its
    enforcement lives in ``tests/agents/test_parent_run_ownership.py``. D1 (``_handle_revision``)
    was found **live** during 0B execution — the frontend ``run_revision`` PPT-revision handler,
    not dead code — so its deletion is voided/deferred and it stays ``☐`` (see the ledger ‡
    note). All later-phase rows remain ``☐``.
    """
    text = _LEDGER.read_text()
    rows = _parse_rows(text)
    ids = [item for item, _gate, _status in rows]
    missing = [i for i in _REQUIRED_ITEMS if i not in ids]
    assert not missing, f"ledger drifted from §31 — missing rows: {missing}"
    flipped = sorted(item for item, _g, status in rows if "☑" in status)
    assert flipped == ["L14", "L16"], (
        f"Phase 0B expects exactly {{L14, L16}} flipped to ☑, found: {flipped}"
    )


def test_guard_fails_on_known_present_pattern() -> None:
    """Non-vacuity guard (T-03-01): the ratchet really greps real grep rows.

    Inject a synthetic ``☑`` row whose gate is a token KNOWN to exist in ``backend/``
    (``_PROTOTYPE_PIPELINE_TYPES``, in engine.py). Run the SAME parse+classify logic and
    assert: (1) it is classified as a grep row (pattern is not None), and (2) the grep
    machinery actually FINDS it — i.e. the deletion assertion WOULD fail. This proves the
    guard is not vacuously green while all real rows sit at ``☐``.
    """
    present_token = "_PROTOTYPE_PIPELINE_TYPES"
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

    res = subprocess.run(
        ["grep", "-rnE", pattern, str(_BACKEND), "--include=*.py"],
        capture_output=True,
        text=True,
    )
    # returncode 0 == pattern FOUND == the deletion assertion would fail → guard is live.
    assert res.returncode == 0 and res.stdout, (
        "non-vacuity guard broken: known-present token not found in backend/ "
        "(wrong repo-root depth, or grep machinery dead)"
    )


def test_check_rows_classified_as_check() -> None:
    """CHECK rows (L16/F4/F5) must classify as prose, not grep, regardless of status."""
    text = _LEDGER.read_text()
    by_item = {item: gate for item, gate, _status in _parse_rows(text)}
    for check_item in ("L16", "F4", "F5"):
        assert _is_check_gate(by_item[check_item]), (
            f"{check_item} gate should be a CHECK row but was classified as a grep pattern: "
            f"{by_item[check_item]!r}"
        )
    # And a known grep row must classify as a grep pattern (sanity, both directions).
    assert not _is_check_gate(by_item["L5"]), "L5 (SKIP_PLANNER_FOR_PROTOTYPE) is a grep row"
