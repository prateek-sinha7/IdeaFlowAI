"""SQLAlchemy and Pydantic models."""

from app.models.database import Base, SessionLocal, engine, get_db
from app.models.user import User
from app.models.chat import ChatSession, Message
from app.models.workflow import WorkflowRun
from app.models.revoked_token import RevokedToken, cleanup_expired_revocations
# Phase 3 models — must be imported before WorkflowRun mapper is finalized
# so that the relationship() references resolve correctly. (The thin-store
# WorkflowArtifact model was deleted in 05-07; artifacts live in artifact_refs.)
from app.models.workflow_clarification import WorkflowClarification  # noqa: F401
from app.models.workflow_memory import WorkflowMemory  # noqa: F401
from app.models.workflow_definition import WorkflowDefinition  # noqa: F401
# Phase 5 typed-artifacts / persistence / ownership models — must be imported
# here so Base.metadata sees them for Alembic autogenerate/check (Pitfall 5).
from app.models.artifact_ref import ArtifactRef  # noqa: F401
from app.models.workspace import Workspace  # noqa: F401
from app.models.run_event import RunEvent  # noqa: F401
from app.models.run_capabilities import RunCapabilities  # noqa: F401
# Phase 8 capability-hardening models (0016) — imported here so Base.metadata
# sees them for Alembic autogenerate/check (Pitfall 5).
from app.models.validation_results import ValidationResult  # noqa: F401
from app.models.gate_events import GateEvent  # noqa: F401
from app.models.hook_runs import HookRun  # noqa: F401
# Phase 9 repo-workflow model (0017) — imported here so Base.metadata sees it for
# Alembic autogenerate/check (Pitfall 5).
from app.models.repository import Repository  # noqa: F401
from app.models.mcp_credential import McpCredential  # noqa: F401
# Phase 10 exec-audit model (0018) — imported here so Base.metadata sees it for
# Alembic autogenerate/check (Pitfall 5).
from app.models.exec_runs import ExecRun  # noqa: F401
# Phase 11 fan-out child audit model (0019) — imported here so Base.metadata sees
# it for Alembic autogenerate/check (Pitfall 5).
from app.models.subagent_run import SubagentRun  # noqa: F401
from app.models.handoff import (
    HandoffSession,
    UserApiKey,
    UserGithubCredential,
    HANDOFF_MODE_AUTO,
    HANDOFF_MODE_CODING,
    HANDOFF_MODE_TEST,
    HANDOFF_STATUS_COMPLETED,
    HANDOFF_STATUS_EXPIRED,
    HANDOFF_STATUS_FAILED,
    HANDOFF_STATUS_PENDING,
    HANDOFF_STATUS_RUNNING,
)
from app.models.schemas import (
    AuthResponse,
    ChatSessionResponse,
    FinalOutputModel,
    LoginRequest,
    MessageResponse,
    RegisterRequest,
    StreamMessageModel,
    UserResponse,
)

__all__ = [
    "Base",
    "SessionLocal",
    "engine",
    "get_db",
    "User",
    "ChatSession",
    "Message",
    "WorkflowRun",
    "ArtifactRef",
    "Workspace",
    "RunEvent",
    "RunCapabilities",
    "Repository",
    "McpCredential",
    "ExecRun",
    "SubagentRun",
    "RevokedToken",
    "cleanup_expired_revocations",
    "HandoffSession",
    "UserApiKey",
    "UserGithubCredential",
    "HANDOFF_MODE_AUTO",
    "HANDOFF_MODE_CODING",
    "HANDOFF_MODE_TEST",
    "HANDOFF_STATUS_COMPLETED",
    "HANDOFF_STATUS_EXPIRED",
    "HANDOFF_STATUS_FAILED",
    "HANDOFF_STATUS_PENDING",
    "HANDOFF_STATUS_RUNNING",
    "AuthResponse",
    "ChatSessionResponse",
    "FinalOutputModel",
    "LoginRequest",
    "MessageResponse",
    "RegisterRequest",
    "StreamMessageModel",
    "UserResponse",
]
