"""agents/execution_engine/user_prompt.py — the run sandbox's ``.context/user-prompt.md``.

Persists the user's request into the run sandbox before step 1 and, for workflows
that extract their uploads themselves, strips the wizard's inlined attachment
text from the request — but only for the documents ``.uploads/manifest.json``
shows actually reached the sandbox. Any other document's inline text is the
run's only copy of it and is kept.

Moved here from ``app/api/launch_context.py`` (move, not copy — INV-12). The
execution kernel is the only production caller (``_execute_impl`` seeds the file
and rewrites it after stripping attachments), and the import-linter contract
"kernel imports only capability ports (scaffold)" forbids
``agents.execution_engine.engine -> app.api``. Nothing here needs the web layer:
it is stdlib-only text handling plus writes through a duck-typed sandbox
(``write``), so it lives on the kernel side and the dependency points inward.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable

logger = logging.getLogger(__name__)

USER_PROMPT_PATH = ".context/user-prompt.md"
UPLOADS_MANIFEST_PATH = ".uploads/manifest.json"

_ATTACHMENT_BLOCK_RE = re.compile(
    r"\n*=== Attached: (.+?) ===\n[\s\S]*?\n=== End: \1 ===", re.MULTILINE
)


def _same_name(name: str) -> str:
    return name


def parse_inline_attachments(user_message: str | None) -> list[str]:
    """Return the names of the wizard's inlined ``=== Attached: … ===`` blocks.

    The one parser for these blocks: the kernel strip below and the launch-time
    upload guard both count attachments through it.
    """
    return _ATTACHMENT_BLOCK_RE.findall(user_message or "")


def _remove_blocks(
    user_message: str, stored_name_of: Callable[[str], str | None]
) -> tuple[str, list[str], int]:
    """Remove each attachment block for which ``stored_name_of(header_name)``
    returns a stored name; keep the others in place.

    ``stored_name_of`` is called once per block, in message order. Returns
    ``(remaining_text, stored_names_of_removed_blocks, kept_block_count)``.
    """
    removed: list[str] = []
    kept = 0

    def _replace(match: re.Match[str]) -> str:
        nonlocal kept
        stored = stored_name_of(match.group(1))
        if stored is None:
            kept += 1
            return match.group(0)
        removed.append(stored)
        return ""

    return _ATTACHMENT_BLOCK_RE.sub(_replace, user_message), removed, kept


def _with_listing(remaining: str, stored_names: list[str]) -> str:
    listing = "\n".join(f"- .uploads/{name}" for name in stored_names)
    return (
        f"{remaining.rstrip()}\n\nAttached files (uploaded to .uploads/, listed in "
        f".uploads/manifest.json; their text is not included here):\n{listing}"
    )


def strip_inline_attachments(
    user_message: str, *, name_for: Callable[[str], str] = _same_name
) -> str:
    """Replace the wizard's inlined ``=== Attached: … ===`` blocks with a pointer.

    For a workflow that extracts its uploads itself (a step granted the
    ``file_extract`` tool set), the pasted document text lets the first agent
    skip its own job and do the whole workflow from the prompt, so only the
    names are kept. This function does not check that the files exist: call it
    through :func:`prepare_brief_for_uploads`, which strips only the blocks
    whose file ``.uploads/manifest.json`` lists.

    ``name_for`` maps a block's header name to the name the file is stored
    under in ``.uploads/`` (the sandbox sanitizes upload names), so the listing
    points at a path that exists. The default keeps the header name.
    """
    remaining, stored_names, _ = _remove_blocks(user_message, name_for)
    if not stored_names:
        return user_message
    return _with_listing(remaining, stored_names)


def manifest_upload_names(manifest_text: str | None) -> frozenset[str]:
    """The stored names a ``.uploads/manifest.json`` text lists.

    Empty when the text is missing, empty or malformed (not a JSON list, or an
    entry without a string ``"name"``). Never raises.
    """
    if not manifest_text:
        return frozenset()
    try:
        entries = json.loads(manifest_text)
    except (TypeError, ValueError):
        return frozenset()
    if not isinstance(entries, list) or not all(
        isinstance(entry, dict) and isinstance(entry.get("name"), str)
        for entry in entries
    ):
        return frozenset()
    return frozenset(entry["name"] for entry in entries)


def prepare_brief_for_uploads(
    user_message: str,
    manifest_text: str | None,
    *,
    name_for: Callable[[str], str] = _same_name,
) -> tuple[str, bool]:
    """Strip the inlined text of each attachment whose file really reached ``.uploads/``.

    Returns ``(message, stripped)``. With no attachment blocks the message is
    returned unchanged. A block is replaced by the stored-name listing only when
    ``.uploads/manifest.json`` (``manifest_text``) lists its stored name
    (``name_for`` maps a block's header name to it; called once per block, in
    message order). Any other block is the run's only copy of that document, so
    it is kept inline and a WARNING is logged (counts only, never names or
    content).

    A header that repeats an earlier block's header names the same document.
    "Edit brief & run again" seeds the earlier run's blocks and re-attaching
    appends a second block with the same header, but only one file is staged,
    so ``name_for`` de-duplicates the repeat to a ``-2`` name the manifest does
    not list. Such a block also counts as uploaded when the name its header's
    first block mapped to is listed. Each stored name is listed once.
    """
    names = parse_inline_attachments(user_message)
    if not names:
        return user_message, False
    uploaded = manifest_upload_names(manifest_text)
    if not uploaded:
        logger.warning(
            "inline attachments kept: .uploads/manifest.json absent or empty "
            "(attachments=%d)",
            len(names),
        )
        return user_message, False

    # header name -> the stored name its first block mapped to
    first_stored: dict[str, str] = {}

    def _uploaded_name(header_name: str) -> str | None:
        stored = name_for(header_name)
        first = first_stored.setdefault(header_name, stored)
        if stored in uploaded:
            return stored
        return first if first in uploaded else None

    remaining, stored_names, kept = _remove_blocks(user_message, _uploaded_name)
    if kept:
        logger.warning(
            "inline attachments kept: not listed in .uploads/manifest.json "
            "(kept=%d, stripped=%d)",
            kept,
            len(stored_names),
        )
    if not stored_names:
        return user_message, False
    return _with_listing(remaining, list(dict.fromkeys(stored_names))), True


def strip_attachments_if_uploaded(
    sandbox: object,
    user_message: str,
    *,
    name_for: Callable[[str], str] = _same_name,
) -> str:
    """The kernel's entry point: read ``.uploads/manifest.json`` from the run
    sandbox and apply :func:`prepare_brief_for_uploads`.

    Returns the message the run should use. When the blocks are stripped, the
    new message is also written to ``.context/user-prompt.md``. Duck-typed on
    ``sandbox.read`` / ``sandbox.write`` like :func:`write_user_prompt_to_sandbox`;
    an unreadable manifest counts as absent. Never raises.
    """
    if not parse_inline_attachments(user_message):
        return user_message
    reader = getattr(sandbox, "read", None)
    manifest_text: str | None = None
    if callable(reader):
        try:
            manifest_text = reader(UPLOADS_MANIFEST_PATH)
        except Exception:  # noqa: BLE001 — unreadable manifest == absent
            manifest_text = None
    prepared, stripped = prepare_brief_for_uploads(
        user_message, manifest_text, name_for=name_for
    )
    if stripped:
        write_user_prompt_to_sandbox(sandbox, prepared)
    return prepared


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
