"""tests/unit/test_admin_create_user_email_validation.py — ISS-295.

`CreateUserRequest.email` (`backend/app/api/admin.py:131`) is a bare Pydantic
``str``, not the codebase's established ``EmailStr`` pattern
(``app/models/schemas.py:15``/``:22``). A value with no ``@`` and no domain —
e.g. ``"not-an-email"`` — is accepted, so `POST /api/admin/users` persists an
unusable, orphaned account with no validation error anywhere in the flow.

This asserts the schema itself rejects a malformed email, independent of any
HTTP wiring around it — the narrowest test that catches the defect at its
documented root cause.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.api.admin import CreateUserRequest


@pytest.mark.issue("ISS-295")
def test_create_user_request_rejects_email_with_no_at_or_domain():
    """A malformed email (no @, no domain) must fail schema validation."""
    with pytest.raises(ValidationError):
        CreateUserRequest(email="not-an-email", password="abc123456", tier="basic")
