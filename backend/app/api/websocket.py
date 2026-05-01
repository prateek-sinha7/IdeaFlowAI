"""WebSocket endpoint for real-time AI chat streaming."""

import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from jose import JWTError
from sqlalchemy.orm import Session

from app.agents.orchestrator import AgentOrchestrator
from app.core.security import decode_access_token
from app.models.chat import ChatSession, Message
from app.models.database import SessionLocal
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter()


def _get_db() -> Session:
    """Create a new database session for WebSocket use."""
    return SessionLocal()


def _authenticate_token(token: str, db: Session) -> User | None:
    """Validate JWT token and return the user, or None if invalid.

    Args:
        token: The JWT token string.
        db: The database session.

    Returns:
        The authenticated User or None.
    """
    try:
        payload = decode_access_token(token)
    except JWTError:
        return None

    user_id: str | None = payload.get("sub")
    if user_id is None:
        return None

    user = db.query(User).filter(User.id == user_id).first()
    return user


@router.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    """WebSocket endpoint for real-time AI chat streaming.

    Authentication is performed via JWT query parameter (?token=<jwt>).
    On successful auth, the connection enters a message loop where:
    - Client sends JSON messages with type, content, and chat_session_id
    - Server routes to AgentOrchestrator and streams responses back
    - Responses include phase_start, stream, phase_end, and complete messages

    Close codes:
    - 4001: JWT expired or invalid during session
    """
    await websocket.accept()

    # Extract JWT from query parameters
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4001, reason="Missing authentication token")
        return

    # Validate JWT and get user
    db = _get_db()
    try:
        user = _authenticate_token(token, db)
        if user is None:
            await websocket.close(code=4001, reason="Invalid or expired token")
            return
    except Exception:
        await websocket.close(code=4001, reason="Authentication error")
        return
    finally:
        db.close()

    logger.info(f"WebSocket connected: user={user.id}")

    # Message loop
    try:
        while True:
            # Receive message from client
            raw_message = await websocket.receive_text()

            try:
                message_data = json.loads(raw_message)
            except json.JSONDecodeError:
                await websocket.send_json({
                    "type": "error",
                    "chunk": None,
                    "section": None,
                    "data": {"error": "Invalid JSON message"},
                })
                continue

            # Validate message structure
            msg_type = message_data.get("type")
            content = message_data.get("content")
            chat_session_id = message_data.get("chat_session_id")

            if msg_type != "user_message" or not content or not chat_session_id:
                await websocket.send_json({
                    "type": "error",
                    "chunk": None,
                    "section": None,
                    "data": {"error": "Invalid message format. Expected {type: 'user_message', content: string, chat_session_id: string}"},
                })
                continue

            # Re-validate JWT before processing (check for expiry during session)
            db = _get_db()
            try:
                user = _authenticate_token(token, db)
                if user is None:
                    await websocket.close(code=4001, reason="Token expired")
                    return

                # Verify chat session belongs to user
                chat_session = (
                    db.query(ChatSession)
                    .filter(
                        ChatSession.id == chat_session_id,
                        ChatSession.user_id == user.id,
                    )
                    .first()
                )

                if chat_session is None:
                    await websocket.send_json({
                        "type": "error",
                        "chunk": None,
                        "section": None,
                        "data": {"error": "Chat session not found"},
                    })
                    continue

                # Persist user message
                user_msg = Message(
                    chat_session_id=chat_session_id,
                    role="user",
                    content=content,
                )
                db.add(user_msg)
                chat_session.last_activity = datetime.now(timezone.utc)
                db.commit()
            finally:
                db.close()

            # Route to Agent Orchestrator and stream responses
            orchestrator = AgentOrchestrator()
            assistant_chunks: list[str] = []

            try:
                async for stream_msg in orchestrator.astream_execute(
                    user_message=content,
                    chat_session_id=chat_session_id,
                ):
                    # Collect stream chunks for persistence
                    if stream_msg.get("type") == "stream" and stream_msg.get("chunk"):
                        assistant_chunks.append(stream_msg["chunk"])

                    # Send stream message to client
                    await websocket.send_json(stream_msg)

            except Exception as e:
                logger.error(f"Agent execution error: {e}")
                await websocket.send_json({
                    "type": "error",
                    "chunk": None,
                    "section": None,
                    "data": {"error": f"Agent execution failed: {str(e)}"},
                })

            # Persist assistant response and final output
            db = _get_db()
            try:
                assistant_content = "".join(assistant_chunks)
                if assistant_content:
                    assistant_msg = Message(
                        chat_session_id=chat_session_id,
                        role="assistant",
                        content=assistant_content,
                    )
                    db.add(assistant_msg)

                # Update chat session last_activity and store final_output if complete
                chat_session = (
                    db.query(ChatSession)
                    .filter(ChatSession.id == chat_session_id)
                    .first()
                )
                if chat_session:
                    chat_session.last_activity = datetime.now(timezone.utc)
                    # Store final output if the last stream message was 'complete'
                    if stream_msg and stream_msg.get("type") == "complete" and stream_msg.get("data"):
                        chat_session.final_output = json.dumps(stream_msg["data"])
                    db.commit()
            finally:
                db.close()

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: user={user.id}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        try:
            await websocket.close(code=1011, reason="Internal server error")
        except Exception:
            pass
