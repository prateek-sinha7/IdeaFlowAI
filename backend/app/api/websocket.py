"""WebSocket endpoint for real-time AI chat streaming."""

import json
import logging
from datetime import datetime, timezone

import anthropic
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from jose import JWTError
from sqlalchemy.orm import Session

from app.agents.base import AgentConfigurationError
from app.agents.mock import mock_stream_response, mock_stream_with_steps, mock_generate_title
from app.agents.modes import get_mode_prompt
from app.agents.orchestrator import AgentOrchestrator
from app.core.config import settings
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
            mode = message_data.get("mode", "default")

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

                # Check if this chat needs a title (first message or default title)
                needs_title = chat_session.title in ("New Chat", "") or chat_session.title == content[:50]
                db.commit()
            finally:
                db.close()

            # Check if we're in mock mode (no API key configured)
            use_mock = not settings.ANTHROPIC_API_KEY

            # Auto-generate chat title from first message (like ChatGPT)
            if needs_title:
                try:
                    if use_mock:
                        generated_title = await mock_generate_title(content)
                    else:
                        from app.agents.base import BaseAgent
                        title_agent = BaseAgent(
                            system_prompt=(
                                "Generate a very short title (3-5 words max) for a chat conversation "
                                "based on the user's first message. Return ONLY the title text, nothing else. "
                                "No quotes, no punctuation at the end, no explanation. Just the title."
                            )
                        )
                        generated_title = await title_agent.run(content)
                    # Clean up the title
                    generated_title = generated_title.strip().strip('"').strip("'").strip(".")[:60]
                    if generated_title:
                        db2 = _get_db()
                        try:
                            cs = db2.query(ChatSession).filter(ChatSession.id == chat_session_id).first()
                            if cs:
                                cs.title = generated_title
                                db2.commit()
                        finally:
                            db2.close()
                        # Notify frontend of the title update
                        await websocket.send_json({
                            "type": "title_update",
                            "chunk": None,
                            "section": None,
                            "data": {"chat_session_id": chat_session_id, "title": generated_title},
                        })
                except Exception as e:
                    logger.warning(f"Failed to generate chat title: {e}")

            # Route to Agent Orchestrator (or mock) and stream responses
            assistant_chunks: list[str] = []
            collected_steps: list[dict] = []
            stream_msg: dict | None = None

            if use_mock:
                # === MOCK MODE — simulate streaming without API key ===
                logger.info(f"Mock mode: streaming response for '{content[:50]}' (mode={mode})")
                try:
                    async for item in mock_stream_with_steps(content, mode):
                        if item["type"] == "step":
                            # Collect steps for persistence
                            step_data = item["step"]
                            # Only keep the final status of each step
                            existing = next((i for i, s in enumerate(collected_steps) if s["id"] == step_data["id"]), None)
                            if existing is not None:
                                collected_steps[existing] = step_data
                            else:
                                collected_steps.append(step_data)
                            await websocket.send_json({
                                "type": "step",
                                "chunk": None,
                                "section": None,
                                "data": step_data,
                            })
                        elif item["type"] == "chunk":
                            assistant_chunks.append(item["chunk"])
                            stream_msg = {
                                "type": "stream",
                                "chunk": item["chunk"],
                                "section": item.get("section", "discovery"),
                                "data": None,
                            }
                            await websocket.send_json(stream_msg)

                    # Send complete message
                    stream_msg = {
                        "type": "complete",
                        "chunk": None,
                        "section": None,
                        "data": {},
                    }
                    await websocket.send_json(stream_msg)
                except Exception as e:
                    logger.error(f"Mock streaming error: {e}")
                    await websocket.send_json({
                        "type": "error",
                        "chunk": None,
                        "section": None,
                        "data": {
                            "error": "Something went wrong in demo mode.",
                            "code": "mock_error",
                            "recoverable": True,
                        },
                    })
            else:
                # === LIVE MODE — use real Claude API ===
                # Get mode-specific system prompt enhancement
                mode_prompt = get_mode_prompt(mode)

                try:
                    orchestrator = AgentOrchestrator()
                    async for stream_msg in orchestrator.astream_execute(
                        user_message=content,
                        chat_session_id=chat_session_id,
                        mode=mode,
                        mode_prompt=mode_prompt,
                    ):
                        if stream_msg.get("type") == "stream" and stream_msg.get("chunk"):
                            assistant_chunks.append(stream_msg["chunk"])
                        await websocket.send_json(stream_msg)

                except AgentConfigurationError:
                    logger.error("Agent configuration error: missing API key")
                    await websocket.send_json({
                        "type": "error", "chunk": None, "section": None,
                        "data": {"error": "AI service is not configured. Please contact the administrator.", "code": "api_key_missing", "recoverable": False},
                    })
                except anthropic.APITimeoutError:
                    logger.error("Anthropic API timeout")
                    await websocket.send_json({
                        "type": "error", "chunk": None, "section": None,
                        "data": {"error": "The AI service took too long to respond. Please try again.", "code": "timeout", "recoverable": True},
                    })
                except anthropic.RateLimitError:
                    logger.error("Anthropic rate limit exceeded")
                    await websocket.send_json({
                        "type": "error", "chunk": None, "section": None,
                        "data": {"error": "Too many requests. Please wait a moment and try again.", "code": "rate_limit", "recoverable": True},
                    })
                except anthropic.APIConnectionError:
                    logger.error("Anthropic API connection error")
                    await websocket.send_json({
                        "type": "error", "chunk": None, "section": None,
                        "data": {"error": "Unable to reach the AI service. Please check your connection and try again.", "code": "connection_error", "recoverable": True},
                    })
                except anthropic.AuthenticationError:
                    logger.error("Anthropic API authentication error")
                    await websocket.send_json({
                        "type": "error", "chunk": None, "section": None,
                        "data": {"error": "AI service authentication failed. Please contact the administrator.", "code": "auth_error", "recoverable": False},
                    })
                except Exception as e:
                    logger.error(f"Agent execution error: {e}")
                    await websocket.send_json({
                        "type": "error", "chunk": None, "section": None,
                        "data": {"error": "Something went wrong. Please try again.", "code": "internal_error", "recoverable": True},
                    })

            # Persist assistant response and final output
            db = _get_db()
            try:
                assistant_content = "".join(assistant_chunks)

                # For PPT/Prototype, the raw content is JSON — persist a summary instead
                if use_mock:
                    lower_msg = content.lower()
                    if any(kw in lower_msg for kw in ["ppt", "presentation", "slide", "deck"]):
                        assistant_content = "✅ **Presentation generated!** Check the Preview panel → PPT tab to see your slides."
                    elif any(kw in lower_msg for kw in ["prototype", "wireframe", "mockup"]):
                        assistant_content = "✅ **Prototype generated!** Check the Preview panel → Prototype tab to see the UI definition."

                if assistant_content:
                    # Embed steps as a hidden marker at the start of content
                    persisted_content = assistant_content
                    if collected_steps:
                        steps_json = json.dumps(collected_steps)
                        persisted_content = f"<!--steps:{steps_json}-->{assistant_content}"
                    assistant_msg = Message(
                        chat_session_id=chat_session_id,
                        role="assistant",
                        content=persisted_content,
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
