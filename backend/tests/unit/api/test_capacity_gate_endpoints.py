"""Direct branch tests for the host-capacity admission gate (specs/014 D-01/D-02/
D-03) — ``_require_host_capacity`` in ``app/api/run_commands.py``.

Every branch (disabled / admin / blind / engaged / allowing) exercised against
the function itself, with no HTTP machinery and no database: the gate's whole
decision is a pure function of ``settings.HOST_CAPACITY_GATE_ENABLED``, the
caller's admin flag, and the published ``AdmissionState``.

The END-TO-END half of this coverage — that the wiring actually reaches a real
HTTP response on launch/resume/revisions, and that every EXEMPT endpoint
(cancel, answers) still returns 2xx while the gate is engaged — needs a real DB
session behind the router and therefore lives in
``tests/integration/api/test_capacity_gate_endpoints_api.py``.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from app.core.config import settings
from app.services import capacity_state as cs

UTC = timezone.utc


class _FakeUser:
    def __init__(self, id: str, *, tier: str = "enterprise", is_admin: bool = False):
        self.id = id
        self.preferred_model = None
        self.tier = tier
        self.is_admin = is_admin


def _engaged_decision(now: datetime) -> cs.AdmissionState:
    return cs.AdmissionState(
        engaged=True,
        engaged_at=now,
        breach_streak=2,
        blind=False,
        blind_reason=None,
        signals=(cs.Signal(name="cpu", value=91.0, threshold=75.0),),
        evaluated_at=now,
    )


def _allowing_decision(now: datetime) -> cs.AdmissionState:
    return cs.AdmissionState(
        engaged=False,
        engaged_at=None,
        breach_streak=0,
        blind=False,
        blind_reason=None,
        signals=(),
        evaluated_at=now,
    )


@pytest.fixture(autouse=True)
def _clean_capacity_state_and_settings(monkeypatch):
    """Every test starts from the shipped defaults (gate disabled) and a
    clean state holder, restoring both afterwards."""
    cs.reset_state_for_tests()
    original_gate_enabled = settings.HOST_CAPACITY_GATE_ENABLED
    yield
    settings.HOST_CAPACITY_GATE_ENABLED = original_gate_enabled
    cs.reset_state_for_tests()


class TestRequireHostCapacityDirect:
    def test_noop_when_gate_disabled_even_if_engaged(self, monkeypatch):
        from app.api.run_commands import _require_host_capacity

        monkeypatch.setattr(settings, "HOST_CAPACITY_GATE_ENABLED", False)
        cs.publish_decision(_engaged_decision(datetime.now(UTC)))
        _require_host_capacity(_FakeUser("u1"))  # must not raise

    def test_noop_for_admin_even_if_engaged(self, monkeypatch):
        from app.api.run_commands import _require_host_capacity

        monkeypatch.setattr(settings, "HOST_CAPACITY_GATE_ENABLED", True)
        cs.publish_decision(_engaged_decision(datetime.now(UTC)))
        _require_host_capacity(_FakeUser("u1", is_admin=True))  # must not raise

    def test_noop_when_blind_even_if_gate_enabled(self, monkeypatch):
        from app.api.run_commands import _require_host_capacity

        monkeypatch.setattr(settings, "HOST_CAPACITY_GATE_ENABLED", True)
        # INITIAL_ADMISSION_STATE (the reset default) is blind.
        _require_host_capacity(_FakeUser("u1"))  # must not raise

    def test_noop_when_allowing(self, monkeypatch):
        from app.api.run_commands import _require_host_capacity

        monkeypatch.setattr(settings, "HOST_CAPACITY_GATE_ENABLED", True)
        cs.publish_decision(_allowing_decision(datetime.now(UTC)))
        _require_host_capacity(_FakeUser("u1"))  # must not raise

    def test_raises_503_with_full_contract_when_engaged(self, monkeypatch):
        from app.api.run_commands import _require_host_capacity

        monkeypatch.setattr(settings, "HOST_CAPACITY_GATE_ENABLED", True)
        monkeypatch.setattr(settings, "HOST_CAPACITY_RETRY_AFTER_SECONDS", 120)
        cs.publish_decision(_engaged_decision(datetime.now(UTC)))

        with pytest.raises(HTTPException) as excinfo:
            _require_host_capacity(_FakeUser("u1"))

        exc = excinfo.value
        assert exc.status_code == 503
        assert exc.headers is not None
        assert exc.headers["Retry-After"] == "120"
        assert exc.detail["code"] == "host_capacity_exhausted"
        assert exc.detail["recoverable"] is True
        assert exc.detail["retry_after_seconds"] == 120
        assert exc.detail["signals"] == [
            {"name": "cpu", "value": 91.0, "threshold": 75.0}
        ]

    def test_non_admin_flag_missing_entirely_still_gated(self, monkeypatch):
        """A caller object with no ``is_admin`` attribute at all must be
        treated as non-admin (``getattr(..., False)``), not exempted by
        accident."""
        from app.api.run_commands import _require_host_capacity

        class _BareUser:
            id = "bare"

        monkeypatch.setattr(settings, "HOST_CAPACITY_GATE_ENABLED", True)
        cs.publish_decision(_engaged_decision(datetime.now(UTC)))
        with pytest.raises(HTTPException):
            _require_host_capacity(_BareUser())
