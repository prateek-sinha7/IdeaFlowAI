"""QA-KB-056 analysis proof -- offline, no DB, no network, no LLM.

Compares the bytes `build_flat_payload` materializes into `.chain/<name>` for a
`streamed_text` deliverable against what the registered resolver returns for the
SAME `ectx` (the bytes the Preview / `final_output` carry).

Run from backend/:

    .venv/bin/python ../evidence/qa-kb-056/analysis-proof-build_flat_payload.py

It only writes into temp directories. It reuses the fixtures the existing
`backend/tests/agents/test_streamed_text_payload_v3.py` suite uses, so it is the
same harness a regression test would use.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(BACKEND))

from tests.agents.test_finalizer_v2 import _plant_logs, _setup_sandbox  # noqa: E402
from tests.agents.test_streamed_text_payload_v3 import (  # noqa: E402
    _finalize,
    _make_ppt_ectx,
    _make_streamed_ectx,
)

from agents.capabilities.deliverables.ppt import PptResolver  # noqa: E402
from agents.capabilities.deliverables.streamed_text import StreamedTextResolver  # noqa: E402
from agents.execution_engine.engine import build_flat_payload  # noqa: E402


def _payload_vs_resolver(label: str, name: str, last_streamed: str) -> None:
    tmp = Path(tempfile.mkdtemp())
    try:
        sandbox, run_id = _setup_sandbox(tmp)
        _plant_logs(sandbox, run_id)
        ectx = _make_streamed_ectx(
            run_id, sandbox, deliverable_name=name, last_streamed=last_streamed
        )
        resolved = StreamedTextResolver().resolve(ectx)
        payload = build_flat_payload(run_id, ectx)
        f = sandbox.root / ".chain" / name
        written = f.read_text(encoding="utf-8") if f.is_file() else None
        print(f"--- {label}")
        print(f"declared name        : {name}")
        print(f"last_streamed        : {last_streamed!r}")
        print(f"resolver output      : {resolved!r}")
        print(f"payload.materialized : {payload.materialized}  chainable={payload.chainable}")
        print(f"materialized bytes   : {written!r}")
        print(f"payload == resolver  : {written == resolved}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _published(label: str, name: str, last_streamed: str) -> None:
    tmp = Path(tempfile.mkdtemp())
    try:
        sandbox, run_id = _setup_sandbox(tmp)
        _plant_logs(sandbox, run_id)
        ectx = _make_streamed_ectx(
            run_id, sandbox, deliverable_name=name, last_streamed=last_streamed
        )
        record = _finalize(run_id, ectx)
        print(f"--- {label}")
        print(f"last_streamed    : {last_streamed!r}")
        print(
            f"published_status : {record.published_status!r}  "
            f"degraded_reason={getattr(record, 'degraded_reason', None)!r}"
        )
        print(f"tags             : {sandbox.list_tags()}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _ppt_parity(label: str, last_streamed: str) -> None:
    tmp = Path(tempfile.mkdtemp())
    try:
        sandbox, run_id = _setup_sandbox(tmp)
        _plant_logs(sandbox, run_id)
        ectx = _make_ppt_ectx(run_id, sandbox, last_streamed=last_streamed)
        resolved = PptResolver().resolve(ectx)
        payload = build_flat_payload(run_id, ectx)
        written = (sandbox.root / ".chain" / "presentation.pptx").read_text(encoding="utf-8")
        print(f"ppt {label}: materialized={payload.materialized} payload==resolver: {written == resolved}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    print("== PART 1: streamed_text payload bytes vs StreamedTextResolver.resolve(ectx)")
    _payload_vs_resolver(
        "A: ISS-791 / BUGS.md repro (wrapper + preamble)",
        "output.md",
        "Thinking...\n<artifact><!DOCTYPE html><html></html></artifact>",
    )
    _payload_vs_resolver(
        "B: ISS-979 (composer .html pick, markdown stream)",
        "output.html",
        "# Title\n\nbody text\n",
    )
    _payload_vs_resolver(
        "C: ISS-980 (wrapper-only stream)", "output.md", "<artifact>\n</artifact>"
    )
    _payload_vs_resolver(
        "D: control (plain markdown, .md name -- must stay equal)",
        "user_stories.md",
        "# Backlog\n\n- story one\n",
    )

    print()
    print("== PART 2: what finalize_terminal_run publishes (DB stubbed, real git sandbox)")
    _published("empty stream (existing test pins degraded + untagged)", "output.md", "")
    _published("wrapper-only stream (resolver output is '')", "output.md", "<artifact>\n</artifact>")
    _published(
        "wrapper + preamble",
        "output.md",
        "Thinking...\n<artifact><!DOCTYPE html><html></html></artifact>",
    )

    print()
    print("== PART 3: control -- the ppt branch IS in parity with PptResolver")
    deck = "<!DOCTYPE html><html><body><section class='slide'><h1>S1</h1></section></body></html>"
    _ppt_parity("wrapper + preamble", "Thinking...\n<artifact>" + deck + "</artifact>")
    _ppt_parity("code fence", "```html\n" + deck + "\n```")
    _ppt_parity("bare prose + deck", "I will now emit the deck.\n" + deck)
