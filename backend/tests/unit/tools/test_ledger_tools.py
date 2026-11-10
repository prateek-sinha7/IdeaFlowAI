"""Unit tests for app/agents/tools/ledger_tools.py (P27 E5), on tmp-dir fixtures."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.agents.tools import ledger_tools
from app.agents.tools.ledger_tools import run_ledger_check


class FakeSandbox:
    """Same path_for contract as RunSandbox: resolve inside root or raise ValueError."""

    def __init__(self, root: Path):
        self.root = root.resolve()

    def path_for(self, relpath: str) -> Path:
        c = (self.root / str(relpath).lstrip("/")).resolve()
        if not c.is_relative_to(self.root):
            raise ValueError(f"path escapes run sandbox: {relpath!r}")
        return c


def _w(root: Path, rel: str, content) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        content if isinstance(content, str) else json.dumps(content), encoding="utf-8"
    )


def _row(rid, testable=True):
    return {
        "id": rid,
        "text": "t",
        "source": {"file": "a.pdf", "page": 1},
        "kind": "functional",
        "use_case": "uc",
        "acceptance": "a",
        "testable": testable,
        "status": "open",
    }


@pytest.fixture
def sb(tmp_path):
    root = tmp_path / "sandbox"
    root.mkdir()
    return FakeSandbox(root)


def _ledger(sb, rows, pattern=r"^G\d+$"):
    _w(sb.root, ".goal/ledger.json", {"id_pattern": pattern, "rows": rows})


def _reasons(res):
    return {(g["id"], g["reason"]) for g in res["gaps"]}


# harvest ---------------------------------------------------------------------


def test_harvest_clean(sb):
    _ledger(sb, [_row("G1"), _row("G2")])
    _w(sb.root, ".extract/pdf/brief/document.md", "Needs G1 and G2.")
    res = run_ledger_check(sb, "harvest")
    assert res["ok"] is True and res["gaps"] == []


def test_harvest_planted_gaps(sb):
    _ledger(sb, [_row("G1"), _row("G3")])
    _w(
        sb.root,
        ".extract/pdf/brief/pages/02/text.md",
        "G1, G10 and G2 appear; G11x does not.",
    )
    _w(sb.root, ".uploads/notes.txt", "also G2")
    _w(sb.root, ".uploads/manifest.json", '{"x": "G99"}')
    (sb.root / ".uploads/blob.bin").write_bytes(b"\x00\x01 G98")
    res = run_ledger_check(sb, "harvest")
    assert res["ok"] is False
    r = _reasons(res)
    assert ("G2", "in source but not in ledger") in r
    assert ("G10", "in source but not in ledger") in r
    assert ("G3", "not found in source") in r
    assert not any(g["id"] in ("G99", "G98", "G11") for g in res["gaps"])
    g2 = next(g for g in res["gaps"] if g["id"] == "G2")
    assert ".extract/pdf/brief/pages/02/text.md" in g2["where"]


def test_harvest_warning_alone_is_ok(sb):
    _ledger(sb, [_row("G1"), _row("G2")])
    _w(sb.root, ".uploads/a.md", "only G1")
    res = run_ledger_check(sb, "harvest")
    assert res["ok"] is True
    assert res["gaps"][0]["reason"] == "not found in source"
    assert res["gaps"][0]["severity"] == "warning"


def test_harvest_null_pattern(sb):
    _ledger(sb, [_row("R-001")], pattern=None)
    res = run_ledger_check(sb, "harvest")
    assert res["ok"] is True and "re-read" in res["note"]


def test_harvest_no_sources_and_bad_pattern(sb):
    _ledger(sb, [_row("G1")])
    assert run_ledger_check(sb, "harvest")["ok"] is False
    _ledger(sb, [_row("G1")], pattern="^(G$")
    assert "invalid id_pattern" in run_ledger_check(sb, "harvest")["gaps"][0]["reason"]


def test_harvest_ignores_symlink_escape(sb, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "document.md").write_text("G777")
    (sb.root / ".extract").mkdir()
    (sb.root / ".extract/link").symlink_to(outside)
    _ledger(sb, [_row("G1")])
    _w(sb.root, ".uploads/a.txt", "G1")
    res = run_ledger_check(sb, "harvest")
    assert res["ok"] is True
    assert not any(g["id"] == "G777" for g in res["gaps"])


# coverage --------------------------------------------------------------------


def _coverage_fixture(sb):
    _ledger(sb, [_row("G1"), _row("G2", testable=False)])
    _w(sb.root, "spec.md", "Covers G1 and G2.")
    _w(
        sb.root,
        "tasks.json",
        {"tasks": [{"id": "T1", "title": "x", "ids": ["G1", "G2"]}]},
    )
    _w(sb.root, ".goal/acceptance/G1.json", {"steps": []})


def test_coverage_clean(sb):
    _coverage_fixture(sb)
    res = run_ledger_check(sb, "coverage")
    assert res["ok"] is True, res


def test_coverage_planted_gaps(sb):
    _ledger(sb, [_row("G1"), _row("G2"), _row("G3"), _row("G3")])
    _w(sb.root, "spec.md", "mentions G1 and G10 only")
    _w(sb.root, "tasks.json", {"tasks": [{"id": "T1", "ids": ["G1", "G9"]}]})
    res = run_ledger_check(sb, "coverage")
    r = _reasons(res)
    assert res["ok"] is False
    assert ("G2", "not mentioned in spec.md") in r
    assert ("G2", "not in any task") in r
    assert ("G1", "missing acceptance file") in r
    assert ("G9", "task id not in ledger") in r
    assert ("G3", "duplicate ledger id") in r


def test_coverage_missing_files(sb):
    _ledger(sb, [_row("G1", testable=False)])
    res = run_ledger_check(sb, "coverage")
    wheres = {g["where"] for g in res["gaps"]}
    assert res["ok"] is False and {"spec.md", "tasks.json"} <= wheres


def test_coverage_traversal_id_never_read(sb, tmp_path):
    (tmp_path / "evil.json").write_text("{}")
    _ledger(sb, [_row("../../evil")])
    _w(sb.root, "spec.md", "../../evil")
    _w(sb.root, "tasks.json", {"tasks": [{"id": "T", "ids": ["../../evil"]}]})
    res = run_ledger_check(sb, "coverage")
    assert res["ok"] is False
    assert any("acceptance" in g["where"] for g in res["gaps"])


# trace -----------------------------------------------------------------------


def test_trace_clean(sb):
    _ledger(sb, [_row("G1"), _row("G2", testable=False)])
    _w(
        sb.root,
        ".goal/trace.json",
        {
            "results": [
                {"id": "G1", "status": "pass", "evidence": "e"},
                {"id": "G2", "status": "not-testable", "evidence": "e"},
            ]
        },
    )
    assert run_ledger_check(sb, "trace")["ok"] is True


def test_trace_planted_gaps(sb):
    _ledger(sb, [_row("G1"), _row("G2"), _row("G3"), _row("G4"), _row("G5")])
    _w(
        sb.root,
        ".goal/trace.json",
        {
            "results": [
                {"id": "G1", "status": "fail"},
                {"id": "G2", "status": "pass"},
                {"id": "G2", "status": "pass"},
                {"id": "G3", "status": "maybe"},
                {"id": "G4", "status": "not-testable"},
                {"id": "G8", "status": "pass"},
            ]
        },
    )
    res = run_ledger_check(sb, "trace")
    r = _reasons(res)
    assert res["ok"] is False
    assert ("G1", "failing") in r
    assert ("G5", "no result in trace.json") in r
    assert ("G4", "marked not-testable but ledger row is testable") in r
    assert ("G8", "trace id not in ledger") in r
    assert any(i == "G2" and "2 results" in why for i, why in r)
    assert any(i == "G3" and "invalid status" in why for i, why in r)


def test_trace_missing_file(sb):
    _ledger(sb, [_row("G1")])
    res = run_ledger_check(sb, "trace")
    assert res["ok"] is False and res["gaps"][0]["where"] == ".goal/trace.json"


# report ----------------------------------------------------------------------


def test_report_clean_and_gap(sb):
    _ledger(sb, [_row("G1"), _row("G2"), _row("G3")])
    _w(
        sb.root,
        ".goal/trace.json",
        {"results": [{"id": "G1", "status": "pass"}, {"id": "G2", "status": "fail"}]},
    )
    _w(sb.root, ".goal/report.md", "G2 failed: login broken. G30 is unrelated.")
    res = run_ledger_check(sb, "report")
    # G3 has no trace result so counts as non-pass; G30 must not satisfy G3.
    assert res["ok"] is False
    assert _reasons(res) == {("G3", "non-pass id not named in report")}
    _w(sb.root, ".goal/report.md", "G2 failed. G3 was never run.")
    assert run_ledger_check(sb, "report")["ok"] is True


def test_report_missing_report(sb):
    _ledger(sb, [_row("G1")])
    _w(sb.root, ".goal/trace.json", {"results": [{"id": "G1", "status": "pass"}]})
    res = run_ledger_check(sb, "report")
    assert res["ok"] is False and res["gaps"][0]["where"] == ".goal/report.md"


# generic ---------------------------------------------------------------------


def test_unknown_mode_lists_valid_modes(sb):
    res = run_ledger_check(sb, "bogus")
    assert res["ok"] is False
    for m in ("harvest", "coverage", "trace", "report"):
        assert m in res["gaps"][0]["reason"]


def test_missing_or_invalid_ledger(sb):
    res = run_ledger_check(sb, "coverage")
    assert res["ok"] is False and res["gaps"][0]["where"] == ".goal/ledger.json"
    _w(sb.root, ".goal/ledger.json", "{not json")
    assert "invalid JSON" in run_ledger_check(sb, "trace")["gaps"][0]["reason"]


def test_gap_cap(sb):
    _ledger(sb, [_row(f"G{i}") for i in range(250)])
    _w(sb.root, ".goal/trace.json", {"results": []})
    res = run_ledger_check(sb, "trace")
    assert len(res["gaps"]) == 200 and res["truncated"] == 50


def test_tool_wrapper_json_and_unbound(sb):
    ledger_tools.bind_sandbox(None)
    assert (
        json.loads(ledger_tools.ledger_check.invoke({"mode": "trace"}))["ok"] is False
    )
    _ledger(sb, [_row("G1")])
    _w(sb.root, ".goal/trace.json", {"results": [{"id": "G1", "status": "pass"}]})
    ledger_tools.bind_sandbox(sb)
    try:
        out = json.loads(ledger_tools.ledger_check.invoke({"mode": "TRACE"}))
    finally:
        ledger_tools.bind_sandbox(None)
    assert out["ok"] is True and out["mode"] == "trace"
