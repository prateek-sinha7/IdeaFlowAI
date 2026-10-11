"""Admin TOTP enrollment and MFA gate enforcement.

Three areas covered:

1. Admin without MFA enrollment cannot access /api/admin/* endpoints; gate
   returns 403 with admin_mfa_required code and enrollment path.

2. Admin enrolls TOTP via the two-step ceremony (associate → verify), then
   the admin gate passes after a successful login challenge that includes
   SOFTWARE_TOKEN_MFA proof.

3. After MFA proof in the current session (mfa_verified_at stamped), the admin
   gate allows access to /api/admin/* endpoints.

boto3 is mocked throughout: these tests verify the application's orchestration
of the enrollment flow and the gate's session-bound proof check.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.core import cognito
from app.core.config import settings
from app.core.dependencies import get_current_user_with_payload
from app.core.identity import (
    enforce_admin_mfa,
    AdminMfaRequired,
    Principal,
    effective_is_admin,
)
from app.models.user import User


EMAIL = "admin-user@flowinqa.com"
ACCESS_TOKEN = "header.payload.signature"
POOL_ID = "eu-central-1_testpool"


@pytest.fixture
def cognito_settings(monkeypatch):
    monkeypatch.setattr(settings, "COGNITO_CLIENT_ID", "test-client-id")
    monkeypatch.setattr(settings, "COGNITO_CLIENT_SECRET", "test-client-secret")
    monkeypatch.setattr(settings, "COGNITO_USER_POOL_ID", POOL_ID)
    monkeypatch.setattr(settings, "COGNITO_REGION", "eu-central-1")
    monkeypatch.setattr(settings, "ADMIN_MFA_REQUIRED", True)


def _admin_user_no_mfa(**overrides) -> User:
    """Admin with no mfa_verified_at (enrollment not completed this session)."""
    defaults = {
        "id": "admin-uuid",
        "email": EMAIL,
        "cognito_sub": "cognito-sub-admin",
        "tier": "basic",
        "is_admin": True,
        "mfa_verified_at": None,
    }
    defaults.update(overrides)
    return User(**defaults)


def _admin_user_mfa_verified(**overrides) -> User:
    """Admin with mfa_verified_at set (proven MFA this session)."""
    defaults = {
        "id": "admin-uuid",
        "email": EMAIL,
        "cognito_sub": "cognito-sub-admin",
        "tier": "basic",
        "is_admin": True,
        "mfa_verified_at": datetime.now(timezone.utc),
    }
    defaults.update(overrides)
    return User(**defaults)


def _iter_api_routes(routes):
    """Yield the real endpoint routes, descending through included routers.

    This FastAPI version does not flatten ``include_router`` into ``app.routes``;
    it stores a ``fastapi.routing._IncludedRouter`` wrapper that holds the
    original ``APIRouter`` under ``original_router``. A loop over ``app.routes``
    that only looks for ``.methods`` therefore sees NO application endpoints at
    all -- it silently iterates a handful of docs routes and passes. Recursing is
    what makes the assertions below actually inspect the two enrolment routes.
    """
    for route in routes:
        included = getattr(route, "original_router", None)
        if included is not None:
            yield from _iter_api_routes(included.routes)
        else:
            yield route


def _collect_dependency_names(dependant) -> set[str]:
    """Names of every dependency reachable from a route's dependant tree.

    Walks sub-dependants because ``get_current_user_with_payload`` may itself be
    nested under another dependency; a shallow one-level read would miss it and
    make the assertion below pass for the wrong reason.
    """
    names: set[str] = set()
    if dependant is None:
        return names
    for dep in getattr(dependant, "dependencies", None) or ():
        call = getattr(dep, "call", None) or getattr(dep, "dependency", None)
        if call is not None and hasattr(call, "__name__"):
            names.add(call.__name__)
        names.update(_collect_dependency_names(dep))
    return names


class TestAdminMfaEnforcement:
    """Admin MFA gate enforcement and enrollment flow."""

    def test_admin_without_mfa_verified_at_blocked_from_admin_access(
        self, cognito_settings
    ):
        """Admin with no mfa_verified_at is rejected by enforce_admin_mfa."""
        admin = _admin_user_no_mfa()
        principal = Principal(
            provider="cognito",
            sub=admin.cognito_sub,
            jti="jti-token",
            iat=1234567890,  # Well after mfa_verified_at (which is None)
            groups=["flowin-admins"],
        )

        with pytest.raises(AdminMfaRequired):
            enforce_admin_mfa(admin, principal)

    def test_totp_enrollment_associate_and_verify(self, cognito_settings, monkeypatch):
        """Admin enrolls TOTP: associate returns secret, verify confirms enrollment."""
        from app.api.auth import associate_totp, verify_totp, TotpVerifyRequest
        from unittest.mock import patch

        admin = _admin_user_no_mfa()
        db = MagicMock(spec=Session)

        # Mock Cognito responses
        fake_client = MagicMock()
        fake_client.associate_software_token.return_value = {
            "SecretCode": "SECRETCODE123"
        }
        fake_client.verify_software_token.return_value = {"Status": "SUCCESS"}
        fake_client.admin_get_user.return_value = {
            "UserMFASettingList": [],
        }
        fake_client.set_user_mfa_preference.return_value = {}

        with patch.object(cognito, "_client", return_value=fake_client):
            credentials = HTTPAuthorizationCredentials(
                scheme="Bearer", credentials=ACCESS_TOKEN
            )
            payload = {
                "sub": admin.cognito_sub,
                "jti": "jti-token",
                "iat": 1234567890,
                "groups": ["flowin-admins"],
            }
            auth_tuple = (admin, payload)

            # Step 1: Associate (get the secret)
            result = associate_totp(credentials=credentials, auth=auth_tuple, db=db)
            assert "secret" in result
            assert result["secret"] == "SECRETCODE123"
            assert "otpauth_uri" in result
            assert "Flowin:admin-user@flowinqa.com" in result["otpauth_uri"]

            # Step 2: Verify (prove possession, set preference)
            request = TotpVerifyRequest(code="123456", device_name="iPhone")
            result = verify_totp(
                request=request, credentials=credentials, auth=auth_tuple, db=db
            )
            assert result["message"] == "Two-factor authentication enabled."

            # Verify Cognito received the preference call with Enabled=True
            assert fake_client.set_user_mfa_preference.called
            call_kwargs = fake_client.set_user_mfa_preference.call_args.kwargs
            assert call_kwargs["SoftwareTokenMfaSettings"]["Enabled"] is True

    def test_admin_with_mfa_verified_at_passes_gate(self, cognito_settings):
        """After login challenge with SOFTWARE_TOKEN_MFA, gate allows admin access."""
        admin = _admin_user_mfa_verified()
        mfa_timestamp = int(admin.mfa_verified_at.timestamp())

        principal = Principal(
            provider="cognito",
            sub=admin.cognito_sub,
            jti="jti-token",
            iat=mfa_timestamp + 1,  # Token minted AFTER mfa_verified_at
            groups=["flowin-admins"],
        )

        # Should not raise — the token was minted after MFA was proven
        enforce_admin_mfa(admin, principal)  # No exception means success


class TestAdminGateContract:
    """The gate's WIRE contract, not just the predicate underneath it.

    ``TestAdminMfaEnforcement`` above proves ``enforce_admin_mfa`` raises. That
    is necessary but not sufficient: a blocked admin has to be able to ACT on
    the refusal. If ``require_admin`` translated the exception into a bare
    ``403 "Admin access required."`` the frontend could not tell "you are not an
    admin" (nothing to do) apart from "you are an admin who has not enrolled"
    (go here and enrol) -- and the admin would be staring at a dead end with no
    route out. So the machine-readable body is the contract, and it is asserted
    here rather than inferred.
    """

    def test_admin_without_mfa_gets_403_code(self, cognito_settings):
        """No session MFA proof -> 403 carrying the code AND the enrol path."""
        from app.api.admin import require_admin

        admin = _admin_user_no_mfa()
        payload = {
            "sub": admin.cognito_sub,
            "jti": "jti-token",
            "iat": 1234567890,
            "groups": ["flowin-admins"],
        }

        with pytest.raises(HTTPException) as exc:
            require_admin(auth=(admin, payload))

        assert exc.value.status_code == 403
        assert exc.value.detail["code"] == "admin_mfa_required"
        # The path is part of the contract: the client is not expected to
        # hardcode it, so a rename here must break this test rather than
        # silently strand the UI on a 404.
        assert exc.value.detail["enroll_path"] == "/api/auth/mfa/totp/associate"

    def test_enroll_endpoints_do_not_require_admin(self):
        """The two enrolment routes must NOT sit behind the gate they unblock.

        This is the deadlock check. ``require_admin`` refuses an admin who holds
        no factor; if enrolling a factor itself required passing ``require_admin``
        the only way out of that 403 would be through the same 403, and the
        account would be permanently locked out of every ``/api/admin/*`` route.
        Authentication alone must be sufficient here -- which is why this asserts
        the ABSENCE of a dependency, the kind of thing that is otherwise only
        discovered by locking someone out in production.
        """
        from app.main import app

        targets = {
            "/api/auth/mfa/totp/associate",
            "/api/auth/mfa/totp/verify",
        }
        seen: dict[str, set[str]] = {}

        for route in _iter_api_routes(app.routes):
            path = getattr(route, "path", None)
            if path not in targets or not getattr(route, "dependant", None):
                continue
            seen[path] = _collect_dependency_names(route.dependant)

        assert seen.keys() == targets, f"routes not found: {targets - seen.keys()}"

        for path, deps in seen.items():
            assert "require_admin" not in deps, (
                f"{path} depends on require_admin -- an admin with no factor "
                "could never reach it to enrol, which is a permanent lockout."
            )
            # Not merely un-gated: still authenticated. Cognito's
            # AssociateSoftwareToken/VerifySoftwareToken are ACCESS-TOKEN APIs,
            # so a caller with no bearer has nothing to enrol against.
            assert (
                "get_current_user_with_payload" in deps
            ), f"{path} must still require an authenticated caller"

    def test_admin_after_totp_login_passes(self, cognito_settings):
        """A token minted after the MFA stamp clears the gate and returns the user.

        Pairs with the first test: same admin, same groups, the ONLY difference
        is that this session proved the factor. That isolates the gate to the
        session-bound proof rather than to role or configuration.
        """
        from app.api.admin import require_admin

        admin = _admin_user_mfa_verified()
        payload = {
            "sub": admin.cognito_sub,
            "jti": "jti-token",
            # Minted AFTER the factor was proven -- what makes the proof
            # session-bound instead of a permanent account flag.
            "iat": int(admin.mfa_verified_at.timestamp()) + 1,
            "groups": ["flowin-admins"],
        }

        assert require_admin(auth=(admin, payload)) is admin
