"""QA-KB-026 -- `domain prose` must not verdict OK when the architecture build is overdue.

Hermetic: a temporary K with one DOMAIN card; status.py is exec'd as a throwaway module
with source_files()/git() patched. Never reads the live tree's counts.
"""

import contextlib
import importlib.util
import io
import json
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SAME = "aaaaaaaaaaaa"


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    m = importlib.util.module_from_spec(spec)
    sys.modules.setdefault(name, m)
    spec.loader.exec_module(m)
    return m


def _tmpk(tmp, stamps):
    k = tmp / ".knowledge"
    (k / "architecture").mkdir(parents=True)
    (k / "cards").mkdir()
    (k / "architecture/modules.json").write_text(
        json.dumps({"modules": [{"file_count": 3}]})
    )
    (k / "architecture/DOMAIN-x.md").write_text(
        f"---\nid: DOMAIN-x\n{stamps}---\nbody\n"
    )
    (k / "state.yaml").write_text(
        "last_sync_commit: abc123\ncards_count: 0\narchitecture_count: 0\n"
    )
    return k


def _row(
    on_disk=3,
    stamps=f"code_signature: {SAME}\nprose_signature: {SAME}\n",
    behind="0",
    diff="",
):
    mod = _load("kb_status_026", "tools/knowledge/status.py")
    with tempfile.TemporaryDirectory() as t:
        mod.K = _tmpk(Path(t), stamps)
        mod.source_files = lambda: on_disk
        real = mod.git
        mod.git = (
            lambda *a: behind
            if a[:2] == ("rev-list", "--count")
            else (diff if a[:2] == ("diff", "--name-only") else real(*a))
        )
        sys.argv = ["status.py", "--json"]
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            mod.main()
    return {c["area"]: c for c in json.loads(buf.getvalue())["checks"]}


@pytest.mark.allow_io("execs status.py against a temporary .knowledge")
@pytest.mark.issue("ISS-693")
def test_current_tree_is_ok():
    """ISS-693 guard -- fully current stays OK."""
    assert _row()["domain prose"]["verdict"] == "OK"


@pytest.mark.allow_io("execs status.py against a temporary .knowledge")
@pytest.mark.issue("ISS-693")
def test_stale_card_with_stale_covered_stays_stale():
    """ISS-693 guard -- a known-stale card keeps STALE and is not downgraded."""
    r = _row(
        on_disk=4, stamps=f"code_signature: {SAME}\nprose_signature: bbbbbbbbbbbb\n"
    )
    assert r["domain prose"]["verdict"] == "STALE"


@pytest.mark.allow_io("execs status.py against a temporary .knowledge")
@pytest.mark.issue("ISS-693")
def test_covered_stale_degrades_domain_prose():
    """ISS-693 -- `source files covered` STALE => `domain prose` not OK."""
    r = _row(on_disk=4)
    assert r["source files covered"]["verdict"] == "STALE"
    assert r["domain prose"]["verdict"] in ("UNKNOWN", "STALE")


@pytest.mark.allow_io("execs status.py against a temporary .knowledge")
@pytest.mark.issue("ISS-693")
def test_changed_stale_degrades_domain_prose():
    """ISS-693 -- `source files changed` STALE (count equal) => `domain prose` not OK."""
    r = _row(on_disk=3, behind="5", diff="backend/agents/engine.py")
    assert r["source files covered"]["verdict"] == "OK"
    assert r["source files changed"]["verdict"] == "STALE"
    assert r["domain prose"]["verdict"] in ("UNKNOWN", "STALE")


@pytest.mark.allow_io("execs status.py against a temporary .knowledge")
@pytest.mark.issue("ISS-883")
def test_unbuilt_domain_card_not_counted_ok():
    """ISS-883 -- a DOMAIN card with no code_signature must not read as verified OK."""
    r = _row(stamps="")
    assert r["domain prose"]["verdict"] != "OK"


@pytest.mark.allow_io(
    "imports build_architecture and calls live_watch_set on a temporary card"
)
@pytest.mark.issue("ISS-884")
@pytest.mark.xfail(reason="ISS-884 unfixed", strict=True)
def test_live_watch_set_passes_prefer_seam():
    """ISS-884 -- live_watch_set must hand domain_watch_set a `prefer` seam like the build does."""
    ba = _load("kb_build_arch_884", "tools/knowledge/build_architecture.py")
    seen = {}
    real = ba.domain_watch_set

    def spy(card, members, index, prefer=None):
        seen["prefer"] = prefer
        return real(card, members, index, prefer=prefer)

    ba.domain_watch_set = spy
    with tempfile.TemporaryDirectory() as t:
        card = Path(t) / "DOMAIN-x.md"
        card.write_text("---\nid: DOMAIN-x\nmembers:\n  - backend/a/x.py\n---\nbody\n")
        ba.live_watch_set(card, ["backend/a/x.py", "backend/b/registry.py"])
    assert seen.get("prefer") is not None
