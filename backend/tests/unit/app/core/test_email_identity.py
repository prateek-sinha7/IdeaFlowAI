"""Regression coverage for case-insensitive email identity aliases."""

from __future__ import annotations

import pytest

from app.api import auth
from app.api.admin import CreateUserRequest
from app.api.auth import ConfirmForgotPasswordRequest, ForgotPasswordRequest
from app.core import cognito, cognito_admin
from app.core.email_identity import canonicalize_email
from app.core.provisioning import ProvisioningRefused, provision_from_login
from app.models.schemas import LoginChallengeRequest, LoginRequest
from app.models.user import User

MIXED_CASE_EMAIL = "PrateekS7@gmail.com"
CANONICAL_EMAIL = "prateeks7@gmail.com"


class _NoUserQuery:
    """Return no local user for an audit-only router lookup."""

    def filter(self, _criterion: object) -> _NoUserQuery:
        return self

    def first(self) -> None:
        return None


class _NoUserSession:
    """Provide the narrow query seam used by unauthenticated auth routes."""

    def query(self, _model: type[User]) -> _NoUserQuery:
        return _NoUserQuery()


class _QueryResult:
    """Return a predetermined user from a lightweight query chain."""

    def __init__(self, user: User | None, criteria: list[object]) -> None:
        self._user = user
        self._criteria = criteria

    def filter(self, criterion: object) -> _QueryResult:
        self._criteria.append(criterion)
        return self

    def first(self) -> User | None:
        return self._user


class _ProvisioningSession:
    """Feed provision_from_login its sub lookup then case-insensitive alias lookup."""

    def __init__(self, existing_user: User) -> None:
        self.criteria: list[object] = []
        self._results = iter((None, existing_user))

    def query(self, _model: type[User]) -> _QueryResult:
        return _QueryResult(next(self._results), self.criteria)


class TestCanonicalizeEmail:
    # Plan #1 | B1
    def test_canonicalize_email_returns_lowercase_alias_when_value_has_whitespace_and_case_variants(
        self,
    ) -> None:
        # Arrange
        value = "  PrateekS7@gmail.com  "

        # Act
        result = canonicalize_email(value)

        # Assert
        assert result == CANONICAL_EMAIL

    # Plan #2 | B2
    @pytest.mark.parametrize(
        "request_factory",
        [
            lambda: LoginRequest(email=MIXED_CASE_EMAIL, password="not-used"),
            lambda: LoginChallengeRequest(
                email=MIXED_CASE_EMAIL,
                session="session-1",
                challenge="SELECT_MFA_TYPE",
                selected_factor="EMAIL_MFA",
            ),
            lambda: ForgotPasswordRequest(email=MIXED_CASE_EMAIL),
            lambda: ConfirmForgotPasswordRequest(
                email=MIXED_CASE_EMAIL,
                code="123456",
                new_password="StrongPassword1!",
            ),
            lambda: CreateUserRequest(email=MIXED_CASE_EMAIL),
        ],
        ids=["login", "login-challenge", "forgot-password", "confirm-forgot-password", "invite"],
    )
    def test_email_requests_return_the_same_canonical_alias_when_input_has_case_variants(
        self, request_factory
    ) -> None:
        # Arrange / Act
        request = request_factory()

        # Assert
        assert request.email == CANONICAL_EMAIL


class TestAuthEmailIdentity:
    # Plan #3 | B2
    def test_login_forwards_canonical_alias_when_request_has_case_variants(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Arrange
        captured: dict[str, str] = {}

        def initiate_auth(email: str, password: str) -> dict[str, str | dict[str, str]]:
            captured["email"] = email
            captured["password"] = password
            return {"ChallengeName": "EMAIL_OTP", "Session": "session-1"}

        monkeypatch.setattr(cognito, "admin_initiate_auth", initiate_auth)
        monkeypatch.setattr(auth.auth_events, "emit", lambda *_args, **_kwargs: None)
        request = LoginRequest(email=MIXED_CASE_EMAIL, password="current-password")

        # Act
        response = auth.login(request, db=_NoUserSession())

        # Assert
        assert captured == {"email": CANONICAL_EMAIL, "password": "current-password"}
        assert response.challenge == "EMAIL_OTP"

    # Plan #4 | B2
    def test_login_challenge_forwards_canonical_alias_when_request_has_case_variants(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Arrange
        captured: dict[str, object] = {}

        def respond_to_challenge(
            email: str,
            challenge_name: str,
            session: str,
            challenge_responses: dict[str, str],
        ) -> dict[str, str | dict[str, str]]:
            captured["email"] = email
            captured["challenge_name"] = challenge_name
            captured["session"] = session
            captured["challenge_responses"] = challenge_responses
            return {"ChallengeName": "EMAIL_OTP", "Session": "session-2"}

        monkeypatch.setattr(
            cognito, "admin_respond_to_auth_challenge", respond_to_challenge
        )
        monkeypatch.setattr(auth.auth_events, "emit", lambda *_args, **_kwargs: None)
        request = LoginChallengeRequest(
            email=MIXED_CASE_EMAIL,
            session="session-1",
            challenge="SELECT_MFA_TYPE",
            selected_factor="EMAIL_MFA",
        )

        # Act
        response = auth.login_challenge(request, db=_NoUserSession())

        # Assert
        assert captured == {
            "email": CANONICAL_EMAIL,
            "challenge_name": "SELECT_MFA_TYPE",
            "session": "session-1",
            "challenge_responses": {"ANSWER": "EMAIL_MFA"},
        }
        assert response.session == "session-2"

    # Plan #5 | B2
    def test_forgot_password_forwards_canonical_alias_when_request_has_case_variants(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Arrange
        captured: list[str] = []
        monkeypatch.setattr(auth.settings, "AUTH_EMAIL_MFA_ENABLED", False)
        monkeypatch.setattr(cognito, "forgot_password", captured.append)
        request = ForgotPasswordRequest(email=MIXED_CASE_EMAIL)

        # Act
        response = auth.forgot_password(request, db=_NoUserSession())

        # Assert
        assert captured == [CANONICAL_EMAIL]
        assert response == {"message": "If that account exists, a reset code has been sent."}


class TestInvitationEmailIdentity:
    # Plan #6 | B2
    def test_invite_user_uses_canonical_alias_when_input_has_case_variants(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Arrange
        created_with: list[str] = []
        grouped_with: list[tuple[str, str]] = []

        def create_user(
            email: str,
            temporary_password: str | None = None,
            *,
            desired_delivery_mediums: list[str] | None = None,
        ) -> dict[str, dict[str, list[dict[str, str]]]]:
            assert temporary_password is None
            assert desired_delivery_mediums == ["EMAIL"]
            created_with.append(email)
            return {"User": {"Attributes": [{"Name": "sub", "Value": "sub-created"}]}}

        def add_user_to_group(email: str, group: str) -> None:
            grouped_with.append((email, group))

        monkeypatch.setattr(cognito_admin.cognito, "admin_create_user", create_user)
        monkeypatch.setattr(
            cognito_admin.cognito, "admin_add_user_to_group", add_user_to_group
        )
        monkeypatch.setattr(cognito_admin.auth_events, "emit", lambda *_args, **_kwargs: None)

        # Act
        created = cognito_admin.invite_user(
            MIXED_CASE_EMAIL, tier="basic", is_admin=False
        )

        # Assert
        assert created.email == CANONICAL_EMAIL
        assert created_with == [CANONICAL_EMAIL]
        assert grouped_with == [(CANONICAL_EMAIL, "flowin-tier-basic")]


class TestProvisionFromLogin:
    # Plan #7 | B2
    def test_provision_from_login_refuses_identity_takeover_when_email_case_variant_has_different_sub(
        self,
    ) -> None:
        # Arrange
        existing_user = User(
            id="local-user-1",
            email=CANONICAL_EMAIL,
            cognito_sub="sub-existing",
            tier="basic",
        )
        db = _ProvisioningSession(existing_user)

        # Act / Assert
        with pytest.raises(ProvisioningRefused, match="email is already mapped"):
            provision_from_login(
                db,
                email=MIXED_CASE_EMAIL,
                sub="sub-new",
                groups=[],
            )

        assert str(db.criteria[1].left) == "lower(users.email)"
        assert db.criteria[1].right.value == CANONICAL_EMAIL
        assert existing_user.cognito_sub == "sub-existing"
