"""mechanical: assemble_slots — parallel-built parts poured into the shell's part markers (goal)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agents.capabilities.slot_assemble import (
    AssembleSlotsFailed,
    assemble_slots,
    assemble_slots_text,
)

SHELL = (
    "<main><!-- part:P-UC1 -->\n<!-- part:P-UC2 --></main>"
    "<script>shared();\n/* part:P-UC1 */\n/* part:P-UC2 */\nstart();</script>"
)


class _Sandbox:
    def __init__(self, root: Path) -> None:
        self.root = root

    def path_for(self, rel: str) -> Path:
        return self.root / rel

    def read(self, rel: str):
        p = self.root / rel
        return p.read_text() if p.is_file() else None

    def write(self, rel: str, text: str) -> None:
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)


def test_fills_both_slots_and_keeps_order():
    out, report = assemble_slots_text(
        SHELL,
        {
            "P-UC1": {"html": "<section>one</section>", "js": "function uc1(){}"},
            "P-UC2": {"html": "<section>two</section>", "js": "function uc2(){}"},
        },
    )
    assert out.index("<section>one</section>") < out.index("<section>two</section>")
    assert out.index("function uc1") < out.index("start();")
    assert "<!-- part:P-UC1 begin -->" in out and "/* part:P-UC2 end */" in out
    assert report["complete"] is True and report["missing"] == []


def test_missing_part_keeps_its_marker_and_is_reported():
    out, report = assemble_slots_text(
        SHELL, {"P-UC1": {"html": "<section>one</section>", "js": "x()"}}
    )
    assert "<!-- part:P-UC2 -->" in out and "/* part:P-UC2 */" in out
    assert report["missing"] == ["P-UC2.html", "P-UC2.js"]
    assert report["complete"] is False


def test_script_part_with_closing_script_tag_is_refused():
    out, report = assemble_slots_text(
        SHELL,
        {
            "P-UC1": {"html": "<section/>", "js": "x(); </script><script>y();"},
            "P-UC2": {"html": "<b/>", "js": "z()"},
        },
    )
    assert "</script><script>y();" not in out
    assert report["problems"] and "P-UC1.js" in report["missing"]


def test_part_without_a_marker_is_unused():
    _, report = assemble_slots_text(
        "<main><!-- part:A --></main>",
        {"A": {"html": "<i/>", "js": None}, "B": {"html": "<b/>", "js": None}},
    )
    assert report["unused"] == ["B.html"]


def test_assemble_slots_writes_page_and_report(tmp_path):
    sb = _Sandbox(tmp_path)
    sb.write("prototype.html", SHELL)
    sb.write("parts/P-UC1.html", "<section>one</section>")
    sb.write("parts/P-UC1.js", "function uc1(){}")
    sb.write("parts/P-UC2.html", "<section>two</section>")
    sb.write("parts/P-UC2.js", "function uc2(){}")
    summary = assemble_slots(sb)
    assert "Assembled 4 part file(s)" in summary
    assert "<section>two</section>" in sb.read("prototype.html")
    assert json.loads(sb.read("build/assembly.json"))["complete"] is True


def test_no_shell_or_no_markers_fails(tmp_path):
    sb = _Sandbox(tmp_path)
    with pytest.raises(AssembleSlotsFailed):
        assemble_slots(sb)
    sb.write("prototype.html", "<main>no slots</main>")
    with pytest.raises(AssembleSlotsFailed):
        assemble_slots(sb)
