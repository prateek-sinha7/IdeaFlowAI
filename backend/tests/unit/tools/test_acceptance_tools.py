"""Unit tests for app/agents/tools/acceptance_tools.py and ledger_check's goal_v2 modes (P27 W1)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.agents.tools import acceptance_tools as at
from app.agents.tools.ledger_tools import run_ledger_check

PAGE = """<!doctype html><html><body>
<nav><button data-test="tab-b" onclick="show('b')">B</button></nav>
<section id="a" data-screen="a">
  <input type="file" data-test="file-in" id="fin">
  <button data-test="go" onclick="convert()">Convert</button>
  <button data-test="off" disabled>Off</button>
  <textarea data-test="out"></textarea>
  <p id="msg" style="display:none">hidden</p>
  <ul><li class="r">1</li><li class="r">2</li></ul>
</section>
<section id="b" data-screen="b"><p>screen b</p></section>
<script>
  let loaded = '';
  document.getElementById('fin').addEventListener('change', async e => {
    loaded = await e.target.files[0].text();
  });
  function convert() {
    document.querySelector('[data-test=out]').value = loaded;
  }
  const show = (id) => {};
</script>
</body></html>"""

GOOD_XML = '<?xml version="1.0"?><ns:Doc xmlns:ns="urn:x"><ns:Item id="7">hello</ns:Item></ns:Doc>'
TWO_DOCS = GOOD_XML + "\n" + GOOD_XML


class FakeSandbox:
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
    r = {
        "id": rid,
        "text": "t",
        "kind": "functional",
        "use_case": "uc",
        "acceptance": "a",
        "testable": testable,
    }
    if not testable:
        r["reason"] = "needs a human eye"
    return r


def _acc(rid, *cases, fixtures=()):
    return {
        "id": rid,
        "title": f"t {rid}",
        "fixtures": list(fixtures),
        "cases": [{"name": n, "steps": steps} for n, steps in cases],
    }


@pytest.fixture
def sb(tmp_path):
    root = tmp_path / "sandbox"
    root.mkdir()
    _w(root, "prototype.html", PAGE)
    _w(root, ".goal/fixtures/good.xml", GOOD_XML)
    _w(root, ".goal/fixtures/two.xml", TWO_DOCS)
    return FakeSandbox(root)


def _ledger(sb, *rows):
    _w(sb.root, ".goal/ledger.json", {"id_pattern": None, "rows": list(rows)})


def _trace(sb):
    return json.loads((sb.root / ".goal/trace.json").read_text())


def _run(sb, ids="all"):
    return json.loads(at.run_acceptance_core(sb, ids))


@pytest.fixture(scope="module")
def _chromium_ok():
    import asyncio

    async def probe():
        from playwright.async_api import async_playwright

        async with async_playwright() as pw:
            b = await pw.chromium.launch(args=["--no-sandbox"])
            await b.close()

    try:
        asyncio.run(probe())
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Chromium cannot launch: {exc}")


C2X = [
    {"verb": "load_file", "target": "file-in", "file": ".goal/fixtures/good.xml"},
    {"verb": "click", "target": "go"},
]


# --- outline & schema (no browser) -------------------------------------------------


def test_outline(sb):
    out = at.page_outline_core(sb, "prototype.html")
    assert "prototype.html:" in out and "lines" in out
    assert "a: lines" in out and "b: lines" in out
    assert "go: line 5" in out and "tab-b: line 2" in out
    assert "convert: line" in out and "show: line" in out
    assert "scripts (1)" in out


def test_outline_cap_and_missing(sb):
    _w(
        sb.root,
        "big.html",
        "<body>" + "".join(f'<i data-test="d{i}"></i>\n' for i in range(2000)),
    )
    out = at.page_outline_core(sb, "big.html")
    assert len(out) < 8300 and "truncated" in out
    assert at.page_outline_core(sb, "nope.html").startswith("error")
    assert at.page_outline_core(sb, "../x.html").startswith("error")


def test_schema_mode(sb):
    _ledger(sb, _row("G1"), _row("G2"), _row("G3"), _row("G4", testable=False))
    _w(
        sb.root,
        ".goal/acceptance/G1.json",
        _acc("G1", ("c", C2X), fixtures=[".goal/fixtures/good.xml"]),
    )
    _w(
        sb.root,
        ".goal/acceptance/G2.json",
        _acc("G2", ("c", [{"verb": "dance", "target": "x"}])),
    )
    res = run_ledger_check(sb, "acceptance_schema")
    reasons = {(g["id"], g["reason"]) for g in res["gaps"]}
    assert not any(i == "G1" for i, _ in reasons)
    assert any(i == "G2" and "unknown verb" in r for i, r in reasons)
    assert ("G3", "missing acceptance file") in reasons
    assert not any(i == "G4" for i, _ in reasons)
    assert res["ok"] is False


def test_schema_field_rules(sb):
    _ledger(sb, _row("G1"))
    bad = _acc(
        "G1",
        (
            "c",
            [
                {"verb": "click"},
                {"verb": "expect_text", "target": "x", "contains": "a", "equals": "a"},
                {"verb": "load_file", "target": "x", "file": "../../etc/passwd"},
                {"verb": "expect_xml", "target": "x", "well_formed": False},
                {"verb": "click", "target": "x", "bogus": 1},
            ],
        ),
    )
    _w(sb.root, ".goal/acceptance/G1.json", bad)
    res = run_ledger_check(sb, "acceptance_schema")
    text = " | ".join(g["reason"] for g in res["gaps"])
    for frag in (
        "missing field 'target'",
        "exactly one of contains, equals",
        "file not found",
        "well_formed must be true",
        "unknown field 'bogus'",
    ):
        assert frag in text


def test_schema_clean(sb):
    _ledger(sb, _row("G1"))
    _w(sb.root, ".goal/acceptance/G1.json", _acc("G1", ("c", C2X)))
    res = run_ledger_check(sb, "acceptance_schema")
    assert res["ok"] is True and res["gaps"] == []


# --- xml helper --------------------------------------------------------------------


def test_check_xml_rules():
    ok = {"well_formed": True}
    assert at.check_xml(GOOD_XML, ok) is None
    assert "declaration" in at.check_xml(TWO_DOCS, ok)
    assert "well-formed" in at.check_xml("<a><b></a>", ok)
    assert at.check_xml(GOOD_XML, {**ok, "root": "Doc"}) is None
    assert "root element" in at.check_xml(GOOD_XML, {**ok, "root": "Other"})
    assert (
        at.check_xml(GOOD_XML, {**ok, "contains": ["hello"], "not_contains": ["zzz"]})
        is None
    )
    assert at.check_xml(GOOD_XML, {**ok, "not_contains": ["hello"]})
    assert (
        at.check_xml(
            GOOD_XML, {**ok, "xpath_text": {"//Item": "hello", "/Doc/Item/@id": "7"}}
        )
        is None
    )
    assert "expected" in at.check_xml(
        GOOD_XML, {**ok, "xpath_text": {"//Item": "nope"}}
    )
    assert "matched nothing" in at.check_xml(
        GOOD_XML, {**ok, "xpath_text": {"//Missing": "x"}}
    )
    assert at.check_xml(GOOD_XML, {**ok, "xpath_text": {"//ns:Item": "hello"}}) is None


# --- browser runner ----------------------------------------------------------------


def _setup_run(sb):
    _ledger(
        sb,
        _row("G1"),
        _row("G2"),
        _row("G3"),
        _row("G4"),
        _row("G5"),
        _row("G6", testable=False),
    )
    ui = [
        {"verb": "expect_visible", "target": "go"},
        {"verb": "expect_disabled", "target": "off"},
        {"verb": "expect_enabled", "target": "go"},
        {"verb": "expect_hidden", "target": "#msg"},
        {"verb": "expect_count", "target": ".r", "equals": 2},
        {"verb": "fill", "target": "out", "value": "typed"},
        {"verb": "expect_text", "target": "out", "equals": "typed"},
        {"verb": "eval", "js": "document.querySelectorAll('.r').length === 2"},
    ]
    xml_ok = C2X + [
        {
            "verb": "expect_xml",
            "target": "out",
            "well_formed": True,
            "root": "Doc",
            "contains": ["hello"],
            "xpath_text": {"//Item": "hello"},
        }
    ]
    xml_two = [
        {"verb": "load_file", "target": "file-in", "file": ".goal/fixtures/two.xml"},
        {"verb": "click", "target": "go"},
        {"verb": "expect_xml", "target": "out", "well_formed": True},
    ]
    _w(sb.root, ".goal/acceptance/G1.json", _acc("G1", ("ui", ui), ("xml", xml_ok)))
    _w(sb.root, ".goal/acceptance/G2.json", _acc("G2", ("two docs", xml_two)))
    _w(
        sb.root,
        ".goal/acceptance/G3.json",
        _acc("G3", ("wrong", [{"verb": "expect_count", "target": ".r", "min": 3}])),
    )
    _w(
        sb.root,
        ".goal/acceptance/G4.json",
        _acc("G4", ("missing", [{"verb": "click", "target": "no-such"}])),
    )


@pytest.mark.allow_io("drives real headless Chromium")
def test_runner_statuses_and_trace(sb, _chromium_ok):
    _setup_run(sb)
    out = _run(sb)
    by = {r["id"]: r for r in _trace(sb)["results"]}
    assert by["G1"]["status"] == "pass", by["G1"]
    assert by["G2"]["status"] == "fail" and "declaration" in by["G2"]["observed"]
    assert by["G2"]["failing_step"] and "expect_xml" in by["G2"]["failing_step"]
    assert by["G3"]["status"] == "fail"
    assert by["G4"]["status"] == "error"
    assert by["G5"]["status"] == "error" and "missing" in by["G5"]["observed"]
    assert (
        by["G6"]["status"] == "not-testable"
        and by["G6"]["evidence"] == "needs a human eye"
    )
    assert out["ok"] is False and out["counts"]["pass"] == 1
    assert {f["id"] for f in out["failures"]} == {"G2", "G3", "G4", "G5"}
    t = _trace(sb)
    assert t["runner"] == "run_acceptance" and t["pass"] == 1 and t["partial"] is False
    assert t["page_sha256"] == at.page_sha256(sb, "prototype.html")
    _run(sb)
    assert _trace(sb)["pass"] == 2


@pytest.mark.allow_io("drives real headless Chromium")
def test_cases_start_from_fresh_page(sb, _chromium_ok):
    _ledger(sb, _row("G1"))
    _w(
        sb.root,
        ".goal/acceptance/G1.json",
        _acc(
            "G1",
            ("sets", [{"verb": "fill", "target": "out", "value": "dirty"}]),
            ("fresh", [{"verb": "expect_text", "target": "out", "equals": ""}]),
        ),
    )
    assert _run(sb)["ok"] is True


@pytest.mark.allow_io("drives real headless Chromium")
def test_partial_run_merges_and_keeps_counter(sb, _chromium_ok):
    _setup_run(sb)
    _run(sb)
    before = {r["id"]: r for r in _trace(sb)["results"]}
    _w(
        sb.root,
        ".goal/acceptance/G3.json",
        _acc("G3", ("fixed", [{"verb": "expect_count", "target": ".r", "min": 2}])),
    )
    out = _run(sb, "G3")
    t = _trace(sb)
    by = {r["id"]: r for r in t["results"]}
    assert t["partial"] is True and t["pass"] == 1 and out["partial"] is True
    assert by["G3"]["status"] == "pass"
    assert {k: v for k, v in by.items() if k != "G3"} == {
        k: v for k, v in before.items() if k != "G3"
    }
    assert len(t["results"]) == len(before)
    _run(sb, "G")  # prefix selects every id again, still partial
    assert _trace(sb)["partial"] is True and _trace(sb)["pass"] == 1
    _run(sb, "all")
    t = _trace(sb)
    assert t["partial"] is False and t["pass"] == 2


def test_runner_never_raises(sb):
    out = json.loads(at.run_acceptance_core(sb, "all", "missing.html"))
    assert out["ok"] is False and "page not found" in out["error"]
    out = json.loads(at.run_acceptance_core(sb, "all"))
    assert out["ok"] is False  # no acceptance ids at all


# --- trace_fresh -------------------------------------------------------------------


@pytest.mark.allow_io("drives real headless Chromium")
def test_trace_fresh_modes(sb, _chromium_ok):
    _ledger(sb, _row("G1"), _row("G2", testable=False))
    _w(
        sb.root,
        ".goal/acceptance/G1.json",
        _acc("G1", ("c", [{"verb": "expect_visible", "target": "go"}])),
    )
    assert run_ledger_check(sb, "trace_fresh")["ok"] is False  # no trace yet

    _run(sb)
    assert run_ledger_check(sb, "trace_fresh")["ok"] is True

    _run(sb, "G1")  # partial
    res = run_ledger_check(sb, "trace_fresh")
    assert any("partial" in g["reason"] for g in res["gaps"])

    _run(sb)
    _w(sb.root, "prototype.html", PAGE + "<!-- edited -->")
    res = run_ledger_check(sb, "trace_fresh")
    assert any("page changed" in g["reason"] for g in res["gaps"])


def test_trace_fresh_rejects_hand_written_trace(sb):
    _ledger(sb, _row("G1"))
    _w(
        sb.root,
        ".goal/trace.json",
        {
            "run_at": "x",
            "page_sha256": at.page_sha256(sb, "prototype.html"),
            "results": [{"id": "G1", "status": "pass"}],
        },
    )
    res = run_ledger_check(sb, "trace_fresh")
    assert res["ok"] is False and any(
        "run_acceptance" in g["reason"] for g in res["gaps"]
    )
    _w(
        sb.root,
        ".goal/trace.json",
        {
            "runner": "run_acceptance",
            "partial": False,
            "pass": 1,
            "page_sha256": at.page_sha256(sb, "prototype.html"),
            "results": [],
        },
    )
    res = run_ledger_check(sb, "trace_fresh")
    assert [g["reason"] for g in res["gaps"]] == ["no result in trace.json"]


# --- goal_v2 dev port: the deliverable is always prototype.html -------------------


def test_trace_fresh_flags_a_trace_of_another_page(sb):
    _ledger(sb, _row("G1"))
    _w(sb.root, "other.html", PAGE)
    _w(
        sb.root,
        ".goal/trace.json",
        {
            "runner": at.RUN_ACCEPTANCE,
            "partial": False,
            "page": "other.html",
            "page_sha256": at.page_sha256(sb, "other.html"),
            "results": [{"id": "G1", "status": "pass"}],
        },
    )
    res = run_ledger_check(sb, "trace_fresh")
    assert res["ok"] is False
    assert any("not the deliverable prototype.html" in g["reason"] for g in res["gaps"])


def test_run_acceptance_tool_has_no_page_argument():
    assert set(at.run_acceptance.args) == {"ids"}


class _FakePage:
    def __init__(self, url: str):
        self.url = url


def test_stay_on_page_allows_fragments_and_fails_on_redirect():
    url = "file:///sb/prototype.html"
    at._stay_on_page(_FakePage(url + "#uc2"), url)
    with pytest.raises(at._Fail, match="navigated away from prototype.html"):
        at._stay_on_page(_FakePage("file:///sb/oms-channel-simulator.html"), url)


@pytest.mark.allow_io("drives real headless Chromium")
def test_redirecting_page_fails_every_case(sb, _chromium_ok):
    _ledger(sb, _row("G1"))
    _w(sb.root, "real.html", PAGE)
    _w(sb.root, "prototype.html", "<script>location.replace('real.html')</script>")
    _w(
        sb.root,
        ".goal/acceptance/G1.json",
        _acc("G1", ("c", [{"verb": "expect_visible", "target": "go"}])),
    )
    out = json.loads(at.run_acceptance_core(sb, "all"))
    assert out["ok"] is False
    assert out["counts"]["pass"] == 0


def test_check_xml_refuses_dtd_and_entities():
    bomb = '<?xml version="1.0"?><!DOCTYPE r [<!ENTITY a "x">]><r>&a;</r>'
    assert "DOCTYPE/ENTITY" in at.check_xml(bomb, {"well_formed": True})
    assert at.check_xml('<?xml version="1.0"?><r/>', {"well_formed": True}) is None
