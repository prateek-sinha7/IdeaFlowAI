"""Chat session and message SQLAlchemy models."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import relationship

from app.models.database import Base


class ChatSession(Base):
    """Chat session model."""

    __tablename__ = "chat_sessions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    title = Column(String, nullable=False, default="New Chat")
    last_activity = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    created_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    final_output = Column(Text, nullable=True)  # JSON string of Final_Output

    user = relationship("User", back_populates="chat_sessions")
    messages = relationship(
        "Message", back_populates="chat_session", order_by="Message.created_at"
    )


class Message(Base):
    """Chat message model."""

    __tablename__ = "messages"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    chat_session_id = Column(
        String, ForeignKey("chat_sessions.id"), nullable=False
    )
    role = Column(String, nullable=False)  # "user" | "assistant" | "system"
    content = Column(Text, nullable=False)
    created_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    chat_session = relationship("ChatSession", back_populates="messages")
