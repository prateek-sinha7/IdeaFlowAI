"""Chat session CRUD API endpoints."""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.models.chat import ChatSession, Message
from app.models.database import get_db
from app.models.schemas import ChatSessionResponse, MessageResponse
from app.models.user import User

router = APIRouter(prefix="/api/chats", tags=["chats"])


# --- Request/Response Schemas ---


class CreateChatRequest(BaseModel):
    """Request body for creating a new chat session."""

    title: Optional[str] = None


class AddMessageRequest(BaseModel):
    """Request body for appending a message to a chat session."""

    content: str
    role: str = "user"


class ChatSessionDetailResponse(BaseModel):
    """Detailed chat session response with messages and optional final_output."""

    id: str
    title: str
    last_activity: datetime
    created_at: datetime
    messages: list[MessageResponse]
    final_output: Optional[str] = None

    model_config = {"from_attributes": True}


# --- Endpoints ---


@router.post("", response_model=ChatSessionResponse, status_code=status.HTTP_201_CREATED)
def create_chat(
    request: CreateChatRequest = CreateChatRequest(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new chat session for the authenticated user.

    Auto-generates a title ("New Chat") if not provided.
    """
    title = request.title if request.title else "New Chat"

    chat_session = ChatSession(
        user_id=current_user.id,
        title=title,
    )
    db.add(chat_session)
    db.commit()
    db.refresh(chat_session)

    return chat_session


@router.get("", response_model=list[ChatSessionResponse])
def list_chats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all chat sessions for the authenticated user.

    Ordered by last_activity descending (most recent first).
    """
    sessions = (
        db.query(ChatSession)
        .filter(ChatSession.user_id == current_user.id)
        .order_by(ChatSession.last_activity.desc())
        .all()
    )
    return sessions


@router.get("/{chat_id}", response_model=ChatSessionDetailResponse)
def get_chat(
    chat_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return full chat session with message history and optional final_output.

    Returns 404 if the chat session does not exist or does not belong to the user.
    """
    chat_session = (
        db.query(ChatSession)
        .filter(ChatSession.id == chat_id, ChatSession.user_id == current_user.id)
        .first()
    )
    if not chat_session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat session not found",
        )

    return ChatSessionDetailResponse(
        id=chat_session.id,
        title=chat_session.title,
        last_activity=chat_session.last_activity,
        created_at=chat_session.created_at,
        messages=[
            MessageResponse(
                id=msg.id,
                chat_session_id=msg.chat_session_id,
                role=msg.role,
                content=msg.content,
                created_at=msg.created_at,
            )
            for msg in chat_session.messages
        ],
        final_output=chat_session.final_output,
    )


@router.delete("/{chat_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_chat(
    chat_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a chat session and all its messages.

    Returns 204 No Content on success.
    Returns 404 if the chat session does not exist or does not belong to the user.
    """
    chat_session = (
        db.query(ChatSession)
        .filter(ChatSession.id == chat_id, ChatSession.user_id == current_user.id)
        .first()
    )
    if not chat_session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat session not found",
        )

    # Delete all messages first, then the chat session
    db.query(Message).filter(Message.chat_session_id == chat_id).delete()
    db.delete(chat_session)
    db.commit()

    return None


@router.put("/{chat_id}/messages", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
def add_message(
    chat_id: str,
    request: AddMessageRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Append a message to a chat session and update last_activity.

    Returns 404 if the chat session does not exist or does not belong to the user.
    """
    chat_session = (
        db.query(ChatSession)
        .filter(ChatSession.id == chat_id, ChatSession.user_id == current_user.id)
        .first()
    )
    if not chat_session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat session not found",
        )

    message = Message(
        chat_session_id=chat_id,
        role=request.role,
        content=request.content,
    )
    db.add(message)

    # Update last_activity on the chat session
    chat_session.last_activity = datetime.now(timezone.utc)
    db.commit()
    db.refresh(message)

    return message
