"""Prompt Override Manager — per-user prompt overrides for agent AGENT.md bodies.

Storage layout (mirrors the skill-file namespace — skills.py):
    backend/skills/users/{user_id}/{agent_id}/PROMPT_OVERRIDE.md

When a user saves a prompt override, the factory injects it at runtime instead
of (or ahead of) the canonical AGENT.md prompt_body. The AGENT.md file itself
is NEVER mutated — overrides are always user-scoped and reversible.

The same structural prompt-injection defences used for skills apply here:
``MAX_PROMPT_OVERRIDE_BYTES`` caps the payload at the API layer; sanitisation
is the caller's responsibility if the override is injected into a system prompt
(the factory applies the same sanitize_user_skill_content guard it uses for
skills). Note: the factory currently does NOT automatically apply prompt
overrides — this module provides the storage layer only. The factory wiring
is a separate step (KAN-76 follow-up); for now the feature is display + save.
"""

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("app.agents.prompt_overrides")

_BACKEND_DIR = Path(__file__).parent.parent.parent
_USER_SKILLS_DIR = _BACKEND_DIR / "skills" / "users"

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

    Args:
        agent_id: The agent's ID.
        content: Markdown prompt body.
        user_id: The authenticated user's ID (required).

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
