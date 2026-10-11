"""agents/execution_engine/user_prompt.py — the run sandbox's ``.context/user-prompt.md``.

Persists the user's request into the run sandbox before step 1 and, for workflows
that extract their uploads themselves, strips the wizard's inlined attachment
text from the request.

Moved here from ``app/api/launch_context.py`` (move, not copy — INV-12). The
execution kernel is the only production caller (``_execute_impl`` seeds the file
and rewrites it after stripping attachments), and the import-linter contract
"kernel imports only capability ports (scaffold)" forbids
``agents.execution_engine.engine -> app.api``. Nothing here needs the web layer:
it is stdlib-only text handling plus writes through a duck-typed sandbox
(``write``), so it lives on the kernel side and the dependency points inward.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

USER_PROMPT_PATH = ".context/user-prompt.md"

_ATTACHMENT_BLOCK_RE = re.compile(
    r"\n*=== Attached: (.+?) ===\n[\s\S]*?\n=== End: \1 ===", re.MULTILINE
)


def strip_inline_attachments(user_message: str) -> str:
    """Replace the wizard's inlined ``=== Attached: … ===`` blocks with a pointer.

    For a workflow that extracts its uploads itself (a step granted the
    ``file_extract`` tool set), the pasted document text lets the first agent
    skip its own job and do the whole workflow from the prompt. The files are
    already in ``.uploads/`` (listed in ``.uploads/manifest.json``), so only
    their names are kept.
    """
    names = _ATTACHMENT_BLOCK_RE.findall(user_message or "")
    if not names:
        return user_message
    stripped = _ATTACHMENT_BLOCK_RE.sub("", user_message).rstrip()
    listing = "\n".join(f"- .uploads/{n}" for n in names)
    return (
        f"{stripped}\n\nAttached files (uploaded to .uploads/, listed in "
        f".uploads/manifest.json; their text is not included here):\n{listing}"
    )


def write_user_prompt_to_sandbox(sandbox: object, user_message: str) -> None:
    """Write the user's request to ``.context/user-prompt.md``.

    Only the first agent gets the request inline; this file lets any later agent
    with ``read_files`` read it too. ``.context/`` is reserved (agents cannot
    write it) and agent-readable. A chained run's inherited
    ``=== CONTEXT FROM PREVIOUS PIPELINE`` block is stripped, matching the clean
    brief downstream agents see. A revision overwrites the file with its own
    request. Best-effort, never-raising.
    """
    writer = getattr(sandbox, "write", None)
    if not callable(writer) or not user_message:
        return
    brief = user_message.split("\n\n=== CONTEXT FROM PREVIOUS PIPELINE")[0].strip()
    if not brief:
        return
    try:
        writer(USER_PROMPT_PATH, brief + "\n")
    except Exception:  # noqa: BLE001
        logger.warning(
            "write_user_prompt_to_sandbox: failed to write %s",
            USER_PROMPT_PATH,
            exc_info=True,
        )
