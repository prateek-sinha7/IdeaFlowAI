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

    model_config = {"from_attributes": True}


class AuthResponse(BaseModel):
    """Authentication response with token and user info."""

    token: str
    user: UserResponse


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
