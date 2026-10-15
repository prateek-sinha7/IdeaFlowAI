"""Prompt Override Manager — per-user prompt overrides for agent AGENT.md bodies.

Storage layout (mirrors the skill-file namespace — skills.py):
    backend/skills/users/{user_id}/{agent_id}/PROMPT_OVERRIDE.md

**Override semantics — REPLACEMENT BODIES, not additive fragments.**

A stored override is a COMPLETE REPLACEMENT of the system prompt body for the
specified agent.  It is NOT an additive fragment that is injected ahead of or
appended to the base body.  When an override is present the factory substitutes
the override content for the ``prompt_body`` slot in full; the base AGENT.md
body is not used at all for that agent.

All other assembly blocks (guardrails, hooks, constitution, injects, skills) are
composed around the override exactly as if the agent's own AGENT.md body were
present.  The effective order follows the agent's declared ``prompt_policy``
(Requirement 29 AC4).  Only the ``prompt_body`` slot is replaced.

The AGENT.md file itself is NEVER mutated — overrides are always user-scoped
and reversible by deleting the override file.

The same structural prompt-injection defences used for skills apply here:
``MAX_PROMPT_OVERRIDE_BYTES`` caps the payload at the API layer; sanitisation
is the caller's responsibility if the override is injected into a system prompt
(the factory applies the same sanitize_user_skill_content guard it uses for
skills).

**Production override migration is deferred.**
Moving existing stored overrides from the current replacement-body model to any
future per-section override API is NOT done by this module.  The trigger is the
first production user saving an override under the new API, or GA (Requirement 37).
This module documents the contract; it does not migrate stored overrides.
"""

import logging
from pathlib import Path
from typing import Optional

from app.core.config import settings

logger = logging.getLogger("app.agents.prompt_overrides")

_BACKEND_DIR = Path(__file__).parent.parent.parent
# Same root as app/agents/skills.py USER_SKILLS_DIR (settings.USER_SKILLS_ROOT).
_USER_SKILLS_DIR = (
    Path(settings.USER_SKILLS_ROOT)
    if settings.USER_SKILLS_ROOT
    else _BACKEND_DIR / "skills" / "users"
)

# Prompt overrides can legitimately be longer than skill files (they replace
# the whole system prompt body), so cap at 32 KB — still a firm anti-abuse
# ceiling but large enough for any realistic agent instruction set.
MAX_PROMPT_OVERRIDE_BYTES = 32 * 1024  # 32 KB

_FILENAME = "PROMPT_OVERRIDE.md"


def _override_path(user_id: str, agent_id: str) -> Path:
    """Resolve the on-disk path for a user's prompt override file."""
    return _USER_SKILLS_DIR / user_id / agent_id / _FILENAME


def read_user_prompt_override(agent_id: str, user_id: str) -> Optional[str]:
    """Return the user's saved prompt override, or None if not set.

    Returns raw file content without sanitisation so the editor UI shows
    exactly what the user saved.
    """
    if not user_id:
        return None
    path = _override_path(user_id, agent_id)
    if path.exists():
        return path.read_text(encoding="utf-8")
    return None


def has_user_prompt_override(agent_id: str, user_id: str) -> bool:
    """Return True if the user has saved a prompt override for this agent."""
    if not user_id:
        return False
    return _override_path(user_id, agent_id).exists()


def save_user_prompt_override(agent_id: str, content: str, user_id: str) -> str:
    """Persist a per-user prompt override.

    The saved content is a REPLACEMENT BODY for the agent's ``prompt_body``
    assembly slot.  It is NOT an additive fragment — the base AGENT.md body is
    not used at all when an override is present.  All other assembly blocks
    (guardrails, hooks, constitution, injects, skills) remain unchanged.

    To revert an agent to its base AGENT.md body, delete the override via
    ``delete_user_prompt_override`` — do not save an empty string.

    Args:
        agent_id: The agent's ID (determines which agent's body slot is replaced).
        content: Complete Markdown replacement body.  Must not exceed
            ``MAX_PROMPT_OVERRIDE_BYTES`` bytes when UTF-8 encoded.
        user_id: The authenticated user's ID (required; overrides are
            user-scoped and never affect other users).

    Returns:
        Absolute path where the override was saved.

    Raises:
        ValueError: If user_id is empty or content exceeds MAX_PROMPT_OVERRIDE_BYTES.
    """
    if not user_id:
        raise ValueError("user_id is required to save a prompt override")
    if len(content.encode("utf-8")) > MAX_PROMPT_OVERRIDE_BYTES:
        raise ValueError(
            f"Prompt override exceeds MAX_PROMPT_OVERRIDE_BYTES={MAX_PROMPT_OVERRIDE_BYTES} bytes"
        )
    override_dir = _USER_SKILLS_DIR / user_id / agent_id
    override_dir.mkdir(parents=True, exist_ok=True)
    path = override_dir / _FILENAME
    path.write_text(content, encoding="utf-8")
    return str(path)


def delete_user_prompt_override(agent_id: str, user_id: str) -> bool:
    """Delete a user's prompt override, reverting the agent to its base AGENT.md.

    Returns True if deleted, False if there was nothing to delete.
    """
    if not user_id:
        return False
    path = _override_path(user_id, agent_id)
    if path.exists():
        path.unlink()
        return True
    return False
