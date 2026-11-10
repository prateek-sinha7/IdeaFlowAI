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


# gaps ------------------------------------------------------------------------


def _req_doc(sb, pages: dict[int, str], name="brief.pdf", slug="brief"):
    _w(
        sb.root,
        ".goal/inventory.json",
        {"files": [{"name": name, "role": "requirements"}]},
    )
    _w(
        sb.root,
        f".extract/pdf/{slug}/manifest.json",
        {"source": name, "slug": slug, "page_count": len(pages)},
    )
    for n, text in pages.items():
        _w(sb.root, f".extract/pdf/{slug}/pages/{n:02d}/text.md", text)


def _gap_row(rid, text, page, file="brief.pdf"):
    return {**_row(rid), "text": text, "source": {"file": file, "page": page}}


def _kinds(res):
    return sorted(g.get("kind") for g in res["gaps"] if g.get("severity") != "warning")


def test_gaps_clean_and_decides_ok(sb):
    _req_doc(sb, {1: "Cover page.", 2: "G1 The system must show the order id."})
    _ledger(sb, [_gap_row("G1", "The system must show the order id.", 2)])
    _w(
        sb.root,
        ".goal/pages.json",
        {
            "pages": [
                {"file": "brief.pdf", "page": 1, "rows": []},
                {"file": "brief.pdf", "page": 2, "rows": ["G1"]},
            ]
        },
    )
    res = run_ledger_check(sb, "gaps_decide")
    assert res["ok"] is True, res["gaps"]
    assert res["counts"]["next"] == "ok" and res["counts"]["pages_read"] == 2
    written = json.loads((sb.root / ".goal/gaps.json").read_text())
    assert written["history"] == [0] and written["next"] == "ok"


def test_gaps_unread_page_and_unmatched_sentence_retry(sb):
    _req_doc(
        sb,
        {
            1: "G1 The system must show the order id.",
            2: "The user must be able to download the request as a file.",
            3: "Nothing to see.",
        },
    )
    _ledger(sb, [_gap_row("G1", "The system must show the order id.", 1)])
    _w(
        sb.root,
        ".goal/pages.json",
        {
            "pages": [
                {"file": "brief.pdf", "page": 1, "rows": ["G1"]},
                {"file": "brief.pdf", "page": 2, "rows": []},
            ]
        },
    )
    res = run_ledger_check(sb, "gaps_decide")
    assert res["ok"] is False
    assert _kinds(res) == ["page", "sentence"]
    assert res["counts"]["next"] == "retry"
    sentence = next(g for g in res["gaps"] if g.get("kind") == "sentence")
    assert sentence["page"] == 2 and "download" in sentence["text"]


def test_gaps_not_requirements_excuses_a_sentence(sb):
    _req_doc(sb, {1: "This document should be read with the IATA guide."})
    _ledger(sb, [_gap_row("G1", "unrelated", 1)], pattern=None)
    _w(
        sb.root,
        ".goal/pages.json",
        {
            "pages": [
                {
                    "file": "brief.pdf",
                    "page": 1,
                    "rows": [],
                    "not_requirements": [
                        "This document should be read with the IATA guide"
                    ],
                },
            ]
        },
    )
    res = run_ledger_check(sb, "gaps_decide")
    assert res["ok"] is True, res["gaps"]


def test_gaps_no_progress_stops_the_loop(sb):
    _req_doc(sb, {1: "x", 2: "y"})
    _ledger(sb, [_gap_row("G1", "x", 1)], pattern=None)
    _w(sb.root, ".goal/pages.json", {"pages": [{"file": "brief.pdf", "page": 1}]})
    first = run_ledger_check(sb, "gaps_decide")
    assert first["counts"]["next"] == "retry"
    second = run_ledger_check(sb, "gaps_decide")  # nothing changed between passes
    assert second["counts"]["next"] == "ok" and second["counts"]["history"] == [1, 1]
    assert second["ok"] is False  # still reported as open for the review


def test_gaps_missing_ids_and_narrow_pattern(sb):
    _req_doc(sb, {1: "G1 and G2 apply. NFR-7 and NFR-7 again."})
    _ledger(sb, [_gap_row("G1", "G1 and G2 apply.", 1)])
    _w(sb.root, ".goal/pages.json", {"pages": [{"file": "brief.pdf", "page": 1}]})
    res = run_ledger_check(sb, "gaps_decide")
    assert ("G2", "in source but not in ledger") in _reasons(res)
    warn = [g for g in res["gaps"] if g.get("kind") == "id_like"]
    assert [g["id"] for g in warn] == ["NFR-7"] and warn[0]["severity"] == "warning"


def test_gaps_without_pages_or_docs(sb):
    _ledger(sb, [_row("G1")])
    res = run_ledger_check(sb, "gaps_decide")
    reasons = {g["reason"] for g in res["gaps"]}
    assert "pages.json missing" in reasons
    assert "no extracted requirements document found" in reasons


def test_gaps_joins_wrapped_lines_into_one_sentence(sb):
    _req_doc(
        sb,
        {
            1: "Preconditions The order is paid. The fare must permit name changes, as\nshown by the quote.\nFlow\n1. Load the file and review the order."
        },
    )
    _ledger(
        sb,
        [
            _gap_row(
                "U5-1", "The fare must permit name changes, as shown by the quote.", 1
            )
        ],
        pattern=None,
    )
    _w(sb.root, ".goal/pages.json", {"pages": [{"file": "brief.pdf", "page": 1}]})
    res = run_ledger_check(sb, "gaps_decide")
    assert res["ok"] is True, res["gaps"]


def test_gaps_preview_never_writes_or_counts_a_pass(sb):
    _req_doc(sb, {1: "x", 2: "y"})
    _ledger(sb, [_gap_row("G1", "x", 1)], pattern=None)
    _w(sb.root, ".goal/pages.json", {"pages": [{"file": "brief.pdf", "page": 1}]})
    first = run_ledger_check(sb, "gaps_decide")
    assert first["counts"]["next"] == "retry"
    preview = run_ledger_check(sb, "gaps")  # e.g. the ledger agent self-checking
    assert preview["counts"]["preview"] is True and "next" not in preview["counts"]
    assert json.loads((sb.root / ".goal/gaps.json").read_text())["history"] == [1]
    _w(
        sb.root,
        ".goal/pages.json",
        {"pages": [{"file": "brief.pdf", "page": 1}, {"file": "brief.pdf", "page": 2}]},
    )
    second = run_ledger_check(sb, "gaps_decide")
    assert second["counts"]["history"] == [1, 0] and second["counts"]["next"] == "ok"
