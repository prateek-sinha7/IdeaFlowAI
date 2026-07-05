"""Validation tests for the POST /api/prototype/run request body model.

Pins the `RunRequest.brief` cap to the app-wide `settings.BRIEF_MAX_CHARS`
constant (quick task 260703-d4v). The legacy hardcoded `max_length=8000`
straggler rejected briefs that every other brief-ingest endpoint (planner /
clarify / upload) already accepts up to 450k chars.

Direct Pydantic-model validation — no live pipeline needed.
"""

from __future__ import annotations

import pytest
from annotated_types import MaxLen
from pydantic import ValidationError

from app.api.prototype_templates import RunRequest
from app.core.config import settings


def _brief_max_len(model: type[RunRequest]) -> int:
    """Read the effective MaxLen constraint off the `brief` field metadata.

    Reading the constraint (rather than a literal) means this test fails if
    anyone reverts the cap to a hardcoded number.
    """
    for constraint in model.model_fields["brief"].metadata:
        if isinstance(constraint, MaxLen):
            return constraint.max_length
    raise AssertionError("RunRequest.brief has no MaxLen constraint")


def test_brief_over_8000_is_accepted() -> None:
    """A 9000-char brief (over the old 8000 cap) constructs without error."""
    long_brief = "x" * 9000
    req = RunRequest(template_id="t", design_system_id="d", brief=long_brief)
    assert len(req.brief) == 9000


def test_empty_brief_is_rejected() -> None:
    """min_length=1 is unchanged — an empty brief still fails validation."""
    with pytest.raises(ValidationError):
        RunRequest(template_id="t", design_system_id="d", brief="")


def test_brief_cap_tracks_settings_constant() -> None:
    """The cap is sourced from settings.BRIEF_MAX_CHARS, not a literal."""
    assert _brief_max_len(RunRequest) == settings.BRIEF_MAX_CHARS


def test_brief_at_exact_cap_is_accepted() -> None:
    """A brief at exactly settings.BRIEF_MAX_CHARS length constructs OK."""
    boundary_brief = "x" * settings.BRIEF_MAX_CHARS
    req = RunRequest(
        template_id="t", design_system_id="d", brief=boundary_brief
    )
    assert len(req.brief) == settings.BRIEF_MAX_CHARS


def test_brief_over_cap_is_rejected() -> None:
    """One char past the cap is rejected (cap stays bounded — no DoS surface)."""
    over_cap = "x" * (settings.BRIEF_MAX_CHARS + 1)
    with pytest.raises(ValidationError):
        RunRequest(template_id="t", design_system_id="d", brief=over_cap)
