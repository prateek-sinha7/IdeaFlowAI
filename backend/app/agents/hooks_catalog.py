"""hooks_catalog.py — folder-scan loader for the global Hooks catalog.

Each hook lives in ``hooks/global/{hook_id}/HOOK.md`` with YAML frontmatter
for metadata and a markdown body for the hook's behavior description — same
convention as ``agents/prompts/{agent_id}/AGENT.md`` (see agents/loader.py).
Adding a new hook is a folder-drop: no registry, no code change, no restart-time
list to maintain. The catalog is scanned fresh on first request and cached;
call ``clear_cache()`` (e.g. in tests) to force a re-scan.

Hooks are behavioral guidelines attached by users at runtime to customize agent
behavior (formatting, validation, post-processing). Each hook has an event
trigger (PreToolUse, PostToolUse, Stop, SessionStart, SessionEnd) that fires at
specific points in the agent execution pipeline.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import frontmatter  # python-frontmatter

logger = logging.getLogger(__name__)

# backend/ root (this file lives in backend/app/agents/)
_BACKEND_DIR = Path(__file__).resolve().parents[2]
_GLOBAL_HOOKS_DIR = _BACKEND_DIR / "hooks" / "global"


@dataclass
class GlobalHookEntry:
    id: str
    name: str
    display_name: str
    description: str
    content: str
    event: str
    trigger: str
    isBeta: bool = False
    compatible_agents: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)


class GlobalHookError(Exception):
    """Raised when a HOOK.md file has invalid or missing fields."""


_GLOBAL_HOOKS_CACHE: list[GlobalHookEntry] | None = None


def clear_cache() -> None:
    global _GLOBAL_HOOKS_CACHE
    _GLOBAL_HOOKS_CACHE = None


# Map hook events to Lucide icon names (frontend renders these as components)
_EVENT_TO_ICON = {
    "PreToolUse": "AlertCircle",
    "PostToolUse": "CheckCircle",
    "Stop": "Octagon",
    "SessionStart": "Play",
    "SessionEnd": "Square",
}


def _get_icon_for_event(event: str) -> str:
    """Resolve a hook event to its Lucide icon name, defaulting to Webhook."""
    return _EVENT_TO_ICON.get(event, "Webhook")


def _load_one(hook_dir: Path) -> GlobalHookEntry:
    hook_id = hook_dir.name
    hook_file = hook_dir / "HOOK.md"
    if not hook_file.exists():
        raise GlobalHookError(f"HOOK.md not found: {hook_file}")

    post = frontmatter.loads(hook_file.read_text(encoding="utf-8"))
    metadata = post.metadata

    required = ("id", "name", "description", "event", "trigger")
    missing = [f for f in required if f not in metadata]
    if missing:
        raise GlobalHookError(
            f"{hook_id}: HOOK.md missing required field(s): {missing}"
        )

    # Validate that the id field matches the folder name (like agents/loader.py)
    metadata_id = metadata.get("id")
    if metadata_id != hook_id:
        raise GlobalHookError(
            f"{hook_id}: id field in HOOK.md ({metadata_id}) does not match folder name"
        )

    return GlobalHookEntry(
        id=hook_id,
        name=metadata["name"],
        display_name=metadata.get("display_name", metadata["name"]),
        description=metadata["description"],
        content=post.content,
        event=metadata["event"],
        trigger=metadata["trigger"],
        compatible_agents=list(metadata.get("compatible_agents", [])),
        isBeta=metadata.get("isBeta", False),
        tags=list(metadata.get("tags", [])),
    )


def list_global_hooks() -> list[GlobalHookEntry]:
    """Scan hooks/global/ for every {hook_id}/HOOK.md and return parsed entries.

    Results are cached in-process after the first scan; call clear_cache() to
    force a re-scan (e.g. after adding a hook folder in a running dev server,
    or between test cases).
    """
    global _GLOBAL_HOOKS_CACHE
    if _GLOBAL_HOOKS_CACHE is not None:
        return _GLOBAL_HOOKS_CACHE

    if not _GLOBAL_HOOKS_DIR.exists():
        logger.warning("Hooks catalog directory not found: %s", _GLOBAL_HOOKS_DIR)
        _GLOBAL_HOOKS_CACHE = []
        return _GLOBAL_HOOKS_CACHE

    entries = []
    for hook_dir in sorted(_GLOBAL_HOOKS_DIR.iterdir()):
        if not hook_dir.is_dir():
            continue
        try:
            entries.append(_load_one(hook_dir))
        except GlobalHookError:
            logger.exception("Skipping invalid hook catalog entry: %s", hook_dir.name)

    _GLOBAL_HOOKS_CACHE = entries
    return _GLOBAL_HOOKS_CACHE
