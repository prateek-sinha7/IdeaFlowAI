"""PROBE copy of the proposed ISS-902 guard. The repo version would fix _TARGET to the integration test file path."""
import os, re
from pathlib import Path

import pytest

_TARGET = Path(os.environ["TARGET"])
_DEF = "async def test_reconcile_degraded_tracks_latest_completion_only("


def _comments_above_the_degraded_test() -> str:
    text = _TARGET.read_text()
    end = text.index(_DEF)
    start = text.rindex("@pytest.mark.parametrize(", 0, end)
    return "\n".join(
        re.sub(r"^\s*#\s?", "", ln) for ln in text[start:end].splitlines() if ln.lstrip().startswith("#")
    )


@pytest.mark.issue("ISS-902")
@pytest.mark.xfail(reason="ISS-902 unfixed", strict=True)
def test_degraded_test_comments_describe_the_boundary_rule_not_latest_wins():
    c = _comments_above_the_degraded_test()
    assert not re.search(r"latest[- ]wins|LATEST\s+pipeline_complete\s+must\s+decide", c, re.I), c
    assert "FIX-484" in c and re.search(r"run_resuming|pipeline_start", c), c
