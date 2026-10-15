"""ISS-947 - the spec-016 override round-trip suite must actually run.

It sits in tests/unit/ where the I/O guard refuses its SQLite engine (all 7 error at
setup), and its fixture overrides only get_current_user although POST/PATCH depend on
get_current_principal. Correct state: the file lives under tests/integration/api/ and
overrides the principal dependency. Static check, no I/O.
"""

from pathlib import Path

import pytest

TESTS = Path(__file__).resolve().parents[1]
OLD = TESTS / "unit" / "test_workflow_override_e2e.py"
NEW = TESTS / "integration" / "api" / "test_workflow_override_e2e_api.py"


@pytest.mark.issue("ISS-947")
def test_override_round_trip_suite_is_relocated_and_overrides_principal():
    """ISS-947 - moved out of tests/unit and overrides get_current_principal."""
    assert (
        not OLD.exists()
    ), "still in tests/unit where the unit I/O guard errors all 7 tests"
    assert NEW.exists(), "relocated suite missing from tests/integration/api"
    src = NEW.read_text()
    assert "get_current_principal" in src, "fixture must override get_current_principal"
    assert (
        "== 201" in src
    ), "save helper must assert 201 so no test passes without a save"
