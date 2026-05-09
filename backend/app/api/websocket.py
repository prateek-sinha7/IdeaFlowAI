"""WebSocket endpoint for real-time AI chat streaming."""

import json
import logging
from datetime import datetime, timezone

import anthropic
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from jose import JWTError
from sqlalchemy.orm import Session

from app.agents.base import AgentConfigurationError
from app.agents.modes import get_mode_prompt
from app.agents.orchestrator import AgentOrchestrator
from app.core.config import settings
from app.core.security import decode_access_token
from app.models.chat import ChatSession, Message
from app.models.database import SessionLocal
from app.models.user import User
from app.models.workflow import WorkflowRun

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
    print(f"[WS] Connection accepted, checking token...")

    # Extract JWT from query parameters
    token = websocket.query_params.get("token")
    if not token:
        print("[WS] No token provided, closing")
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
    print(f"[WS] Authenticated user={user.id}, entering message loop")

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

            # Handle pipeline execution requests
            if msg_type == "run_pipeline":
                print(f"[WS] Received run_pipeline: type={message_data.get('pipeline_type')}")
                pipeline_type = message_data.get("pipeline_type", "user_stories")
                pipeline_content = message_data.get("message") or message_data.get("content") or ""
                agent_ids = message_data.get("agent_ids")  # Optional custom agent list
                await _handle_pipeline_execution(websocket, pipeline_content, pipeline_type, chat_session_id, token, user, agent_ids=agent_ids)
                continue

            # Handle pipeline cancellation
            if msg_type == "cancel_pipeline":
                logger.info(f"Pipeline cancellation requested by user={user.id}")
                await websocket.send_json({
                    "type": "pipeline_cancelled",
                    "chunk": None,
                    "section": None,
                    "data": {"message": "Pipeline execution cancelled by user"},
                })
                continue

            # Handle questionnaire generation requests
            if msg_type == "generate_questions":
                pipeline_type = message_data.get("pipeline_type", "user_stories")
                prompt = message_data.get("message") or message_data.get("content") or ""
                await _handle_questionnaire(websocket, prompt, pipeline_type)
                continue

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

            # Auto-generate chat title from first message (like ChatGPT)
            if needs_title:
                try:
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

            # Route to Agent Orchestrator and stream responses
            assistant_chunks: list[str] = []
            collected_steps: list[dict] = []
            stream_msg: dict | None = None

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


async def _handle_pipeline_execution(
    websocket: WebSocket,
    content: str,
    pipeline_type: str,
    chat_session_id: str,
    token: str,
    user: User,
    agent_ids: list[str] | None = None,
):
    """Handle a pipeline execution request via WebSocket.

    Runs the full agent pipeline and streams per-agent status updates.
    Creates a WorkflowRun record to track the execution.
    If agent_ids is provided, uses that custom agent list instead of defaults.
    """
    from app.agents.pipeline import PipelineExecutor
    from app.agents.skills import get_skill_content

    logger.info(f"Pipeline execution: type={pipeline_type}, user={user.id}, custom_agents={len(agent_ids) if agent_ids else 'default'}")

    # Determine agent count
    if agent_ids:
        agent_count = len(agent_ids)
    else:
        agent_counts = {"user_stories": 12, "ppt": 4, "prototype": 12}
        agent_count = agent_counts.get(pipeline_type, 12)

    # Create a WorkflowRun record
    workflow_run_id = None
    db = _get_db()
    try:
        workflow_run = WorkflowRun(
            user_id=user.id,
            title=(content or "Untitled")[:60].strip(),
            type=pipeline_type,
            status="running",
            input=content or f"Run {pipeline_type} pipeline",
            agent_count=agent_count,
        )
        db.add(workflow_run)
        db.commit()
        db.refresh(workflow_run)
        workflow_run_id = workflow_run.id
    finally:
        db.close()

    # Persist user message if chat_session_id provided
    if chat_session_id:
        db = _get_db()
        try:
            chat_session = (
                db.query(ChatSession)
                .filter(ChatSession.id == chat_session_id, ChatSession.user_id == user.id)
                .first()
            )
            if chat_session:
                user_msg = Message(
                    chat_session_id=chat_session_id,
                    role="user",
                    content=content or f"Run {pipeline_type} pipeline",
                )
                db.add(user_msg)
                chat_session.last_activity = datetime.now(timezone.utc)
                db.commit()
        finally:
            db.close()

    # Check if API key is configured
    if not settings.ANTHROPIC_API_KEY:
        await websocket.send_json({
            "type": "error",
            "chunk": None,
            "section": None,
            "data": {
                "error": "ANTHROPIC_API_KEY is not configured. Please add your API key to backend/.env to run pipelines.",
                "code": "api_key_missing",
                "recoverable": False,
            },
        })
        return

    final_output = ""
    execution_start = datetime.now(timezone.utc)
    agent_outputs_collector: list[dict] = []  # Collect per-agent thinking/output

    # === LIVE PIPELINE MODE ===
    # Load skills for agents that have them
    from app.agents.registry import get_pipeline_agents, get_all_agents
    agents = get_pipeline_agents(pipeline_type)

    # If custom agent_ids provided, filter and reorder agents accordingly
    if agent_ids:
        all_agents = get_all_agents()
        agent_map = {a.id: a for a in all_agents}
        agents = [agent_map[aid] for aid in agent_ids if aid in agent_map]

    skills: dict[str, str] = {}
    for agent_def in agents:
        skill_content = get_skill_content(agent_def.id)
        if skill_content:
            skills[agent_def.id] = skill_content

    # Execute the pipeline
    executor = PipelineExecutor(pipeline_type, custom_agents=agents if agent_ids else None)

    try:
        current_agent_output_live: dict = {}
        async for update in executor.execute(content, skills=skills):
            await websocket.send_json({
                "type": update["type"],
                "chunk": None,
                "section": pipeline_type,
                "data": update["data"],
            })
            # Collect agent outputs for persistence
            if update["type"] == "agent_start":
                current_agent_output_live = {
                    "agent_id": update["data"].get("agent_id"),
                    "name": update["data"].get("name"),
                    "role": update["data"].get("role"),
                    "icon": update["data"].get("icon"),
                    "thinking": "",
                    "output": "",
                    "duration": None,
                }
            elif update["type"] == "agent_thinking":
                current_agent_output_live["thinking"] = update["data"].get("thinking", "")
            elif update["type"] == "agent_chunk":
                current_agent_output_live["output"] += update["data"].get("chunk", "")
            elif update["type"] == "agent_complete":
                current_agent_output_live["duration"] = update["data"].get("duration")
                agent_outputs_collector.append(current_agent_output_live)
                current_agent_output_live = {}
            elif update["type"] == "pipeline_complete":
                final_output = update["data"].get("final_output", "")
    except Exception as e:
        logger.error(f"Pipeline execution error: {e}")
        await websocket.send_json({
            "type": "error",
            "chunk": None,
            "section": None,
            "data": {
                "error": f"Pipeline execution failed: {str(e)}",
                "code": "pipeline_error",
                "recoverable": True,
            },
        })
        # Mark workflow as failed
        if workflow_run_id:
            db = _get_db()
            try:
                wr = db.query(WorkflowRun).filter(WorkflowRun.id == workflow_run_id).first()
                if wr:
                    wr.status = "failed"
                    wr.error = str(e)
                    wr.completed_at = datetime.now(timezone.utc)
                    duration = (datetime.now(timezone.utc) - execution_start).total_seconds()
                    wr.duration = round(duration, 1)
                    db.commit()
            finally:
                db.close()
        return

    # Mark workflow as completed
    if workflow_run_id:
        db = _get_db()
        try:
            wr = db.query(WorkflowRun).filter(WorkflowRun.id == workflow_run_id).first()
            if wr:
                wr.status = "completed"
                wr.output = final_output if final_output else None
                wr.agent_outputs = json.dumps(agent_outputs_collector) if agent_outputs_collector else None
                wr.completed_at = datetime.now(timezone.utc)
                duration = (datetime.now(timezone.utc) - execution_start).total_seconds()
                wr.duration = round(duration, 1)
                db.commit()
        finally:
            db.close()

    # Persist the final output as assistant message
    if final_output and chat_session_id:
        db = _get_db()
        try:
            if pipeline_type == "ppt":
                summary = "\u2705 **Presentation generated!** Check the Preview panel \u2192 PPT tab."
            elif pipeline_type == "prototype":
                summary = "\u2705 **Prototype generated!** Check the Preview panel \u2192 Prototype tab."
            else:
                summary = final_output[:500]

            assistant_msg = Message(
                chat_session_id=chat_session_id,
                role="assistant",
                content=summary,
            )
            db.add(assistant_msg)

            chat_session = (
                db.query(ChatSession)
                .filter(ChatSession.id == chat_session_id)
                .first()
            )
            if chat_session:
                chat_session.last_activity = datetime.now(timezone.utc)
                db.commit()
        finally:
            db.close()


async def _handle_questionnaire(websocket: WebSocket, prompt: str, pipeline_type: str):
    """Generate clarifying MCQ questions based on the user's prompt and pipeline type.
    
    Uses the questionnaire agent to produce 4 targeted questions.
    Sends the questions back as a 'questionnaire' WebSocket message.
    """
    from app.agents.base import BaseAgent, AgentConfigurationError
    from app.agents.registry import QUESTIONNAIRE_AGENT

    logger.info(f"Generating questionnaire: pipeline_type={pipeline_type}, prompt={prompt[:50]}")

    try:
        agent = BaseAgent(
            system_prompt=QUESTIONNAIRE_AGENT.system_prompt,
            max_tokens=QUESTIONNAIRE_AGENT.max_tokens,
        )

        context_message = f"Pipeline type: {pipeline_type}\nUser's idea: {prompt}"
        response = await agent.run(context_message)

        # Try to parse JSON from response
        import re
        json_match = re.search(r'\{[\s\S]*\}', response)
        if json_match:
            questions_data = json.loads(json_match.group())
            await websocket.send_json({
                "type": "questionnaire",
                "chunk": None,
                "section": None,
                "data": questions_data,
            })
        else:
            # Fallback — couldn't parse questions, skip questionnaire
            await websocket.send_json({
                "type": "questionnaire",
                "chunk": None,
                "section": None,
                "data": {"questions": []},
            })

    except AgentConfigurationError:
        # No API key — skip questionnaire
        await websocket.send_json({
            "type": "questionnaire",
            "chunk": None,
            "section": None,
            "data": {"questions": []},
        })
    except Exception as e:
        logger.error(f"Questionnaire generation error: {e}")
        await websocket.send_json({
            "type": "questionnaire",
            "chunk": None,
            "section": None,
            "data": {"questions": []},
        })
