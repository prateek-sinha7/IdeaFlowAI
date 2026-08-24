"""Pydantic request/response schemas for the API."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field


# --- Auth Schemas ---


class RegisterRequest(BaseModel):
    """Registration request body."""

    email: EmailStr
    password: str = Field(..., min_length=8)


class LoginRequest(BaseModel):
    """Login request body."""

    email: EmailStr
    password: str


class UserResponse(BaseModel):
    """User data returned in API responses."""

    id: str
    email: str
    tier: str = "basic"
    is_admin: bool = False

    model_config = {"from_attributes": True}


class AuthResponse(BaseModel):
    """Authentication response with token and user info."""

    token: str
    user: UserResponse


class AuthChallengeResponse(BaseModel):
    """Returned instead of AuthResponse when Cognito requires another auth
    step (NEW_PASSWORD_REQUIRED, EMAIL_OTP, SOFTWARE_TOKEN_MFA, MFA_SETUP,
    SELECT_MFA_TYPE) before a token can be issued. ``session`` must be echoed
    back verbatim on the matching /login/challenge call."""

    challenge: str
    session: str
    # Cognito's masked destination for a code it just sent (e.g. "j***@e***.com"),
    # read from the challenge's CODE_DELIVERY_DESTINATION parameter. Present only
    # for delivered-code challenges like EMAIL_OTP. Surfaced so the UI can say
    # WHERE to look -- a bare "enter your code" prompt is a common support burden
    # when the address on file isn't the one the user expected. Already masked by
    # Cognito, so it leaks nothing the caller did not just authenticate against.
    delivery: str | None = None
    # For SELECT_MFA_TYPE: the factors this user may choose between. Lets a
    # client render a real choice instead of guessing.
    available_factors: list[str] | None = None


class LoginChallengeRequest(BaseModel):
    """Request body for responding to a Cognito auth challenge."""

    email: EmailStr
    session: str
    challenge: str
    # NEW_PASSWORD_REQUIRED
    new_password: str | None = None
    # SOFTWARE_TOKEN_MFA / MFA_SETUP / EMAIL_OTP -- one field for every
    # one-time code, since the user experience is identical and only the
    # Cognito response key differs.
    mfa_code: str | None = None
    # SELECT_MFA_TYPE only: "EMAIL_MFA" or "SOFTWARE_TOKEN_MFA".
    selected_factor: str | None = None


class MfaStatusResponse(BaseModel):
    """The caller's current second-factor state.

    Drives the account-security UI: which factors are active, which the
    deployment offers, and whether the user is obliged to hold one.
    """

    enabled: bool
    factors: list[str] = []
    # Whether email OTP is configured on the pool at all. False means the UI
    # must not offer it -- the enable call would fail at Cognito.
    email_available: bool = False
    totp_available: bool = True
    # True when this user's role requires a factor (admin + ADMIN_MFA_REQUIRED),
    # so the UI can explain why disabling is refused.
    required: bool = False
    # False when the account is not Cognito-backed (break-glass), where none of
    # this applies.
    supported: bool = True


class RefreshResponse(BaseModel):
    """Response body for POST /api/auth/refresh.

    Deliberately just ``{"token": "..."}`` -- the exact shape
    ``frontend/src/hooks/useRunStream.ts``'s ``attemptSilentRefresh`` already
    parses (D-14f), so no frontend change is required to light this up.
    """

    token: str


# --- Chat Schemas ---


class MessageResponse(BaseModel):
    """Message data returned in API responses."""

    id: str
    chat_session_id: str
    role: str
    content: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ChatSessionResponse(BaseModel):
    """Chat session data returned in API responses."""

    id: str
    title: str
    last_activity: datetime
    created_at: datetime

    model_config = {"from_attributes": True}


# --- WebSocket / Streaming Schemas ---


class StreamMessageModel(BaseModel):
    """WebSocket stream message structure."""

    type: Literal["stream", "complete", "error", "phase_start", "phase_end"]
    chunk: str | None = None
    section: str | None = None
    data: dict | None = None


class FinalOutputModel(BaseModel):
    """Final compiled output from the agent pipeline."""

    auth: dict | None = None
    realtime: dict | None = None
    dashboard: dict | None = None
    discovery: dict | None = None
    requirements: dict | None = None
    user_stories: dict | None = None
    ppt: dict | None = None
    prototype: dict | None = None
    ui_design: dict | None = None
    ui_preview: dict | None = None
