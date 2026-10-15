"""ISS-662 — E2E clarify probes must match the numbered text the narrator emits."""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
E2E = ROOT / "tests/integration/e2e"
ROUND_LESS = "Clarifications answered"
FILES = [
    E2E / "suites/23_controls_inventory/test_controls_inventory.py",
    E2E / "suites/18_chat_lane/test_chat_lane.py",
    ROOT / "tests/integration/screens/18-chat-lane.feature.md",
]


@pytest.mark.issue("ISS-662")
@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_probe_does_not_quote_roundless_clarify_text(path):
    """ISS-662 — narrator emits 'Clarifications round N answered' (chat_narrator.py)."""
    assert (
        ROUND_LESS not in path.read_text()
    ), f"{path.name} still quotes the round-less literal"
