"""Email OTP (EMAIL_OTP) second factor — the parts a wrong guess would break silently.

Three areas are covered, chosen because each has a failure mode that produces no
error at the time it happens:

1. ``apply_mfa_preference`` must send the COMPLETE desired factor state. AWS does
   not document whether an omitted ``SetUserMFAPreference`` settings block
   preserves or clears the corresponding factor. If omitting cleared it, a user
   turning on email codes would silently lose their authenticator device and only
   find out at their next sign-in. We therefore always send both blocks, and
   these tests pin that.

2. The challenge-response key mapping. ``EMAIL_OTP`` takes ``EMAIL_OTP_CODE``,
   not the ``SOFTWARE_TOKEN_MFA_CODE`` that TOTP uses, and the ``SELECT_MFA_TYPE``
   answer for email is ``EMAIL_MFA`` — an asymmetry in Cognito's own API that is
   very easy to get wrong and which fails as a generic "invalid code" to the user.

3. The account-recovery consequence. Email cannot be both a second factor and the
   password-reset channel, so with ``AUTH_EMAIL_MFA_ENABLED`` the self-service
   reset endpoints must refuse rather than return their usual generic 202 and
   leave the user waiting for mail Cognito will never send.

boto3 is mocked throughout: the contract under test is what we SEND to Cognito,
and CI never calls AWS (same posture as test_cognito_verifier.py).
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.core import cognito
from app.core.config import settings
from app.models.user import User


POOL_ID = "eu-central-1_testpool"
EMAIL = "qa-user@flowinqa.com"
ACCESS_TOKEN = "header.payload.signature"


@pytest.fixture
def cognito_settings(monkeypatch):
    monkeypatch.setattr(settings, "COGNITO_CLIENT_ID", "test-client-id")
    monkeypatch.setattr(settings, "COGNITO_CLIENT_SECRET", "test-client-secret")
    monkeypatch.setattr(settings, "COGNITO_USER_POOL_ID", POOL_ID)
    monkeypatch.setattr(settings, "COGNITO_REGION", "eu-central-1")
    monkeypatch.setattr(settings, "AUTH_PROVIDER", "cognito")


def _client_with_factors(*factors: str) -> MagicMock:
    """A fake cognito-idp client whose AdminGetUser reports `factors` as confirmed."""
    fake = MagicMock()
    fake.admin_get_user.return_value = {"UserMFASettingList": list(factors)}
    return fake


def _cognito_user(**overrides) -> User:
    defaults = {
        "id": "local-uuid",
        "email": EMAIL,
        "cognito_sub": "cognito-sub-uuid",
        "auth_provider": "cognito",
        "tier": "basic",
        "is_admin": False,
    }
    defaults.update(overrides)
    return User(**defaults)


class TestApplyMfaPreferenceSendsCompleteState:
    """Both settings blocks are always sent, so nothing is implicitly cleared."""

    def test_enabling_email_preserves_an_existing_totp_device(self, cognito_settings):
        """THE regression guard for this feature.

        A user with a confirmed authenticator who switches on email codes must end
        up with BOTH. If SetUserMFAPreference were called with only the email
        block, the TOTP factor's fate would depend on undocumented behaviour.
        """
        fake = _client_with_factors(cognito.TOTP_FACTOR)
        with patch.object(cognito, "_client", return_value=fake):
            factors = cognito.apply_mfa_preference(ACCESS_TOKEN, EMAIL, email_enabled=True)

        kwargs = fake.set_user_mfa_preference.call_args.kwargs
        assert kwargs["SoftwareTokenMfaSettings"]["Enabled"] is True, (
            "the existing TOTP device must be explicitly re-asserted, not omitted"
        )
        assert kwargs["EmailMfaSettings"]["Enabled"] is True
        assert set(factors) == {cognito.TOTP_FACTOR, cognito.EMAIL_FACTOR}

    def test_disabling_email_preserves_an_existing_totp_device(self, cognito_settings):
        fake = _client_with_factors(cognito.TOTP_FACTOR, cognito.EMAIL_FACTOR)
        with patch.object(cognito, "_client", return_value=fake):
            factors = cognito.apply_mfa_preference(ACCESS_TOKEN, EMAIL, email_enabled=False)

        kwargs = fake.set_user_mfa_preference.call_args.kwargs
        assert kwargs["SoftwareTokenMfaSettings"]["Enabled"] is True
        assert kwargs["EmailMfaSettings"]["Enabled"] is False
        assert factors == [cognito.TOTP_FACTOR]

    def test_enabling_totp_preserves_an_existing_email_factor(self, cognito_settings):
        """The mirror case — the TOTP enrolment path must not strip email codes."""
        fake = _client_with_factors(cognito.EMAIL_FACTOR)
        with patch.object(cognito, "_client", return_value=fake):
            factors = cognito.apply_mfa_preference(ACCESS_TOKEN, EMAIL, totp_enabled=True)

        kwargs = fake.set_user_mfa_preference.call_args.kwargs
        assert kwargs["EmailMfaSettings"]["Enabled"] is True
        assert kwargs["SoftwareTokenMfaSettings"]["Enabled"] is True
        assert set(factors) == {cognito.TOTP_FACTOR, cognito.EMAIL_FACTOR}

    def test_never_enables_totp_that_was_not_already_confirmed(self, cognito_settings):
        """A None for TOTP can only ever preserve, never introduce.

        Enabling TOTP without a registered software token fails at Cognito with
        ``InvalidParameterException: User does not have delivery config set to turn
        on SOFTWARE_TOKEN_MFA``. Since callers pass None to mean "leave it alone",
        None must resolve to False for a user who has no device.
        """
        fake = _client_with_factors()  # no confirmed factors at all
        with patch.object(cognito, "_client", return_value=fake):
            cognito.apply_mfa_preference(ACCESS_TOKEN, EMAIL, email_enabled=True)

        kwargs = fake.set_user_mfa_preference.call_args.kwargs
        assert kwargs["SoftwareTokenMfaSettings"]["Enabled"] is False


class TestApplyMfaPreferenceNamesOnePreference:
    """Exactly one preferred factor, so sign-in never detours via SELECT_MFA_TYPE."""

    def test_factor_being_enabled_becomes_the_preference(self, cognito_settings):
        fake = _client_with_factors(cognito.TOTP_FACTOR)
        with patch.object(cognito, "_client", return_value=fake):
            cognito.apply_mfa_preference(ACCESS_TOKEN, EMAIL, email_enabled=True)

        kwargs = fake.set_user_mfa_preference.call_args.kwargs
        assert kwargs["EmailMfaSettings"]["PreferredMfa"] is True
        assert kwargs["SoftwareTokenMfaSettings"]["PreferredMfa"] is False

    def test_exactly_one_factor_is_preferred_when_both_are_active(self, cognito_settings):
        """Cognito rejects more than one preferred factor, and zero preferred
        among several active ones produces the SELECT_MFA_TYPE detour."""
        fake = _client_with_factors(cognito.TOTP_FACTOR)
        with patch.object(cognito, "_client", return_value=fake):
            cognito.apply_mfa_preference(ACCESS_TOKEN, EMAIL, email_enabled=True)

        kwargs = fake.set_user_mfa_preference.call_args.kwargs
        preferred = [
            kwargs["EmailMfaSettings"]["PreferredMfa"],
            kwargs["SoftwareTokenMfaSettings"]["PreferredMfa"],
        ]
        assert preferred.count(True) == 1

    def test_no_factor_is_preferred_once_all_are_off(self, cognito_settings):
        fake = _client_with_factors(cognito.EMAIL_FACTOR)
        with patch.object(cognito, "_client", return_value=fake):
            factors = cognito.apply_mfa_preference(ACCESS_TOKEN, EMAIL, email_enabled=False)

        kwargs = fake.set_user_mfa_preference.call_args.kwargs
        assert kwargs["EmailMfaSettings"]["PreferredMfa"] is False
        assert kwargs["SoftwareTokenMfaSettings"]["PreferredMfa"] is False
        assert factors == []


class TestFactorInspection:
    def test_has_any_confirmed_mfa_accepts_either_factor(self, cognito_settings):
        """The admin gate must not care WHICH factor an admin holds.

        An admin with TOTP must not be locked out because the environment later
        standardised on email codes.
        """
        for factor in (cognito.TOTP_FACTOR, cognito.EMAIL_FACTOR):
            with patch.object(cognito, "_client", return_value=_client_with_factors(factor)):
                assert cognito.has_any_confirmed_mfa(EMAIL) is True

    def test_has_any_confirmed_mfa_is_false_with_no_factors(self, cognito_settings):
        with patch.object(cognito, "_client", return_value=_client_with_factors()):
            assert cognito.has_any_confirmed_mfa(EMAIL) is False

    def test_absent_mfa_setting_list_is_treated_as_no_factors(self, cognito_settings):
        """AdminGetUser omits UserMFASettingList entirely for a user who has never
        had a preference set. That must read as "not enrolled", not crash."""
        fake = MagicMock()
        fake.admin_get_user.return_value = {"Username": EMAIL}
        with patch.object(cognito, "_client", return_value=fake):
            assert cognito.get_confirmed_mfa_factors(EMAIL) == []
            assert cognito.has_any_confirmed_mfa(EMAIL) is False


class TestLoginChallengeMapping:
    """The Cognito response keys, which differ per challenge in non-obvious ways."""

    @staticmethod
    def _db_with(user: User | None) -> MagicMock:
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = user
        return db

    def _respond(self, monkeypatch, challenge: str, **body):
        """Drive login_challenge and capture what reached Cognito."""
        from app.api.auth import login_challenge
        from app.models.schemas import LoginChallengeRequest

        captured: dict = {}

        def fake_respond(email, challenge_name, session, challenge_responses):
            captured["email"] = email
            captured["challenge"] = challenge_name
            captured["responses"] = challenge_responses
            return {"AuthenticationResult": {"AccessToken": "tok"}}

        monkeypatch.setattr(cognito, "admin_respond_to_auth_challenge", fake_respond)
        monkeypatch.setattr(
            "app.api.auth._cognito_auth_result_to_response",
            lambda user, auth_result, db: MagicMock(token=auth_result["AccessToken"]),
        )

        request = LoginChallengeRequest(
            email=EMAIL, session="sess", challenge=challenge, **body
        )
        login_challenge(request, db=self._db_with(_cognito_user()))
        return captured

    def test_email_otp_uses_the_email_otp_code_key(self, cognito_settings, monkeypatch):
        captured = self._respond(monkeypatch, "EMAIL_OTP", mfa_code="123456")
        assert captured["responses"]["EMAIL_OTP_CODE"] == "123456"
        assert "SOFTWARE_TOKEN_MFA_CODE" not in captured["responses"], (
            "sending the TOTP key for an email challenge surfaces to the user as "
            "an invalid code"
        )

    def test_totp_still_uses_the_software_token_key(self, cognito_settings, monkeypatch):
        captured = self._respond(monkeypatch, "SOFTWARE_TOKEN_MFA", mfa_code="654321")
        assert captured["responses"]["SOFTWARE_TOKEN_MFA_CODE"] == "654321"
        assert "EMAIL_OTP_CODE" not in captured["responses"]

    def test_select_mfa_type_answers_with_email_mfa_not_email_otp(
        self, cognito_settings, monkeypatch
    ):
        """Cognito's own asymmetry: the factor is EMAIL_OTP, the selection answer
        is EMAIL_MFA."""
        captured = self._respond(
            monkeypatch, "SELECT_MFA_TYPE", selected_factor="EMAIL_MFA"
        )
        assert captured["responses"]["ANSWER"] == "EMAIL_MFA"

    def test_email_otp_without_a_code_is_a_400(self, cognito_settings, monkeypatch):
        with pytest.raises(HTTPException) as exc:
            self._respond(monkeypatch, "EMAIL_OTP")
        assert exc.value.status_code == 400
        assert "mfa_code" in str(exc.value.detail)

    def test_select_mfa_type_rejects_an_unknown_factor(self, cognito_settings, monkeypatch):
        with pytest.raises(HTTPException) as exc:
            self._respond(monkeypatch, "SELECT_MFA_TYPE", selected_factor="CARRIER_PIGEON")
        assert exc.value.status_code == 400

    def test_mfa_setup_reports_501_rather_than_sending_a_doomed_response(
        self, cognito_settings, monkeypatch
    ):
        """MFA_SETUP needs a three-call session chain this endpoint cannot express.
        Answering it with a TOTP code would be rejected by Cognito and surface as a
        confusing credential error, so it is refused explicitly instead."""
        with pytest.raises(HTTPException) as exc:
            self._respond(monkeypatch, "MFA_SETUP", mfa_code="123456")
        assert exc.value.status_code == 501


class TestChallengeProjection:
    """The masked destination and factor options handed to the client."""

    def test_code_delivery_destination_is_surfaced(self):
        from app.api.auth import _challenge_response

        result = _challenge_response(
            {
                "ChallengeName": "EMAIL_OTP",
                "Session": "sess",
                "ChallengeParameters": {"CODE_DELIVERY_DESTINATION": "q***@f***.com"},
            }
        )
        assert result.challenge == "EMAIL_OTP"
        assert result.delivery == "q***@f***.com"

    def test_selectable_factors_are_parsed_from_the_json_string(self):
        """Cognito serialises MFAS_CAN_CHOOSE as a JSON array inside a string."""
        from app.api.auth import _challenge_response

        result = _challenge_response(
            {
                "ChallengeName": "SELECT_MFA_TYPE",
                "Session": "sess",
                "ChallengeParameters": {
                    "MFAS_CAN_CHOOSE": '["EMAIL_MFA","SOFTWARE_TOKEN_MFA"]'
                },
            }
        )
        assert result.available_factors == ["EMAIL_MFA", "SOFTWARE_TOKEN_MFA"]

    def test_malformed_factor_list_degrades_instead_of_raising(self):
        """A parse failure must not turn a completable login into a 500."""
        from app.api.auth import _challenge_response

        result = _challenge_response(
            {
                "ChallengeName": "SELECT_MFA_TYPE",
                "Session": "sess",
                "ChallengeParameters": {"MFAS_CAN_CHOOSE": "not-json"},
            }
        )
        assert result.available_factors is None
        assert result.session == "sess"

    def test_missing_challenge_parameters_is_tolerated(self):
        from app.api.auth import _challenge_response

        result = _challenge_response(
            {"ChallengeName": "NEW_PASSWORD_REQUIRED", "Session": "sess"}
        )
        assert result.delivery is None
        assert result.available_factors is None


class TestSelfServiceResetIsRefusedUnderEmailMfa:
    """Email cannot be both the second factor and the recovery channel.

    With email MFA active the pool is created with ``admin_only`` recovery, so
    ForgotPassword can deliver nothing. Returning the usual generic 202 would be a
    lie the user pays for with a support ticket.
    """

    @staticmethod
    def _db() -> MagicMock:
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = _cognito_user()
        return db

    def test_forgot_password_refuses_with_409(self, cognito_settings, monkeypatch):
        monkeypatch.setattr(settings, "AUTH_EMAIL_MFA_ENABLED", True)
        from app.api.auth import ForgotPasswordRequest, forgot_password

        with pytest.raises(HTTPException) as exc:
            forgot_password(ForgotPasswordRequest(email=EMAIL), db=self._db())
        assert exc.value.status_code == 409
        assert "administrator" in str(exc.value.detail).lower()

    def test_confirm_forgot_password_refuses_with_409(self, cognito_settings, monkeypatch):
        monkeypatch.setattr(settings, "AUTH_EMAIL_MFA_ENABLED", True)
        from app.api.auth import ConfirmForgotPasswordRequest, confirm_forgot_password

        with pytest.raises(HTTPException) as exc:
            confirm_forgot_password(
                ConfirmForgotPasswordRequest(
                    email=EMAIL, code="123456", new_password="Str0ng-Passw0rd!"
                ),
                db=self._db(),
            )
        assert exc.value.status_code == 409

    def test_forgot_password_keeps_its_generic_202_when_email_mfa_is_off(
        self, cognito_settings, monkeypatch
    ):
        """The anti-enumeration behaviour must be untouched in the normal config."""
        monkeypatch.setattr(settings, "AUTH_EMAIL_MFA_ENABLED", False)
        monkeypatch.setattr(cognito, "forgot_password", lambda email: None)
        from app.api.auth import ForgotPasswordRequest, forgot_password

        result = forgot_password(ForgotPasswordRequest(email=EMAIL), db=self._db())
        assert "if that account exists" in result["message"].lower()


class TestEmailMfaEnrolmentGuards:
    def test_enable_is_refused_when_the_pool_has_no_email_mfa(
        self, cognito_settings, monkeypatch
    ):
        """Without ``email_mfa_configuration`` on the pool, Cognito rejects the
        write with an opaque parameter error. Refuse with an explanation instead."""
        monkeypatch.setattr(settings, "AUTH_EMAIL_MFA_ENABLED", False)
        from app.api.auth import enable_email_mfa

        credentials = MagicMock(credentials=ACCESS_TOKEN)
        with pytest.raises(HTTPException) as exc:
            enable_email_mfa(credentials=credentials, auth=(_cognito_user(), {}))
        assert exc.value.status_code == 409

    def test_break_glass_account_is_refused(self, cognito_settings, monkeypatch):
        monkeypatch.setattr(settings, "AUTH_EMAIL_MFA_ENABLED", True)
        from app.api.auth import enable_email_mfa

        local_user = _cognito_user(auth_provider="local", cognito_sub=None)
        credentials = MagicMock(credentials=ACCESS_TOKEN)
        with pytest.raises(HTTPException) as exc:
            enable_email_mfa(credentials=credentials, auth=(local_user, {}))
        assert exc.value.status_code == 501

    def test_admin_cannot_disable_their_only_factor(self, cognito_settings, monkeypatch):
        """Otherwise an admin locks themselves out of every /api/admin/* route in
        one click, and fixing it needs a different admin."""
        monkeypatch.setattr(settings, "AUTH_EMAIL_MFA_ENABLED", True)
        monkeypatch.setattr(settings, "ADMIN_MFA_REQUIRED", True)
        monkeypatch.setattr(cognito, "has_confirmed_totp", lambda email: False)
        from app.api.auth import disable_email_mfa

        admin = _cognito_user(is_admin=True)
        payload = {"sub": "cognito-sub-uuid", "groups": ["flowin-admins"]}
        credentials = MagicMock(credentials=ACCESS_TOKEN)

        with pytest.raises(HTTPException) as exc:
            disable_email_mfa(credentials=credentials, auth=(admin, payload))
        assert exc.value.status_code == 409
        assert "authenticator" in str(exc.value.detail).lower()

    def test_admin_with_a_totp_device_may_disable_email(self, cognito_settings, monkeypatch):
        monkeypatch.setattr(settings, "AUTH_EMAIL_MFA_ENABLED", True)
        monkeypatch.setattr(settings, "ADMIN_MFA_REQUIRED", True)
        monkeypatch.setattr(cognito, "has_confirmed_totp", lambda email: True)
        monkeypatch.setattr(
            cognito, "apply_mfa_preference", lambda *a, **k: [cognito.TOTP_FACTOR]
        )
        from app.api.auth import disable_email_mfa

        admin = _cognito_user(is_admin=True)
        payload = {"sub": "cognito-sub-uuid", "groups": ["flowin-admins"]}
        credentials = MagicMock(credentials=ACCESS_TOKEN)

        result = disable_email_mfa(credentials=credentials, auth=(admin, payload))
        assert result["factors"] == [cognito.TOTP_FACTOR]

    def test_non_admin_may_always_disable(self, cognito_settings, monkeypatch):
        monkeypatch.setattr(settings, "AUTH_EMAIL_MFA_ENABLED", True)
        monkeypatch.setattr(settings, "ADMIN_MFA_REQUIRED", True)
        monkeypatch.setattr(cognito, "apply_mfa_preference", lambda *a, **k: [])
        from app.api.auth import disable_email_mfa

        user = _cognito_user(is_admin=False)
        result = disable_email_mfa(
            credentials=MagicMock(credentials=ACCESS_TOKEN),
            auth=(user, {"sub": "cognito-sub-uuid", "groups": []}),
        )
        assert result["factors"] == []
