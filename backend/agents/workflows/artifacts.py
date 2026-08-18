"""agents/workflows/artifacts.py — artifact filename helpers (R-11, R-12, F-06).

Provides single-source-of-truth helpers for custom-agent artifact names. Both the
prompt preamble (T11) and the roster block (T17) call artifact_name() — neither may
format the filename itself (F-06). This module is the enforcement point.

topic_slug(run_input): kebab slug derived from the run input (lowercased,
  non-alphanumeric runs collapsed to '-', leading/trailing '-' stripped,
  truncated to 40 chars never ending on '-'). Empty/blank/all-punctuation
  input returns the fallback "topic" to ensure no empty filename.

artifact_name(instance_id, topic): the file a custom agent writes, formatted
  as '<instance_id>-<topic>.md'. Keys on instance_id ONLY — never accepts
  agent_id (which carries ':' and would create hostile paths, F-02).

Public API:
    topic_slug(run_input: str) -> str
    artifact_name(instance_id: str, topic: str) -> str
    CUSTOM_AGENT_PREFIX: str
"""

from __future__ import annotations

import re

# The synthetic-id prefix a custom-agent step's agent_id is built from
# (f"{CUSTOM_AGENT_PREFIX}{instance_id}"). Not cosmetic: the colon is what
# loader.py's `load_agent_spec` keys on (":" in agent_id) to resolve a template
# instantiation. userWorkflows.ts's stepAgentId() mirrors this literal exactly
# to build matching depends_on values from the same FE-minted instance_id.
CUSTOM_AGENT_PREFIX = "custom-agent:"

# The bare-slug shape an instance_id must have (mirrors the compiler's R-03 check).
# artifact_name() refuses anything else: it is the last point before a filename is
# built, and a colon or a '/' here becomes a hostile path (F-02).
_INSTANCE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def topic_slug(run_input: str) -> str:
    """Kebab slug from the run input: lowercased, non-alphanumeric runs -> '-',
    leading/trailing '-' stripped, truncated to 40 chars (never ending on '-').

    Empty, blank, or all-punctuation input returns the fallback "topic" to ensure
    no empty filename (F-06 / R-12).

    Args:
        run_input: The user's run input text (run prompt / user message).

    Returns:
        A kebab-case slug safe for use as a filename component.

    Examples:
        >>> topic_slug("Build me a CRM!")
        'build-me-a-crm'
        >>> topic_slug("   ")
        'topic'
        >>> topic_slug("!!!")
        'topic'
        >>> topic_slug("a" * 50)  # truncated to 40, no trailing '-'
        'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'
    """
    if not run_input or not run_input.strip():
        return "topic"

    # Lowercase
    slug = run_input.lower()

    # Replace runs of non-alphanumeric with single '-'
    slug = re.sub(r"[^a-z0-9]+", "-", slug)

    # Strip leading/trailing '-'
    slug = slug.strip("-")

    # If all-punctuation input leaves us with empty string, return fallback
    if not slug:
        return "topic"

    # Truncate to 40 chars, but never end on '-'
    if len(slug) > 40:
        slug = slug[:40]
        # Strip trailing '-' if truncation created one
        slug = slug.rstrip("-")

    return slug


def artifact_name(instance_id: str, topic: str) -> str:
    """The file a custom agent writes: '<instance_id>-<topic>.md'.

    Keys on instance_id ONLY — never on agent_id. Synthetic agent ids contain
    ':' and would produce hostile paths if interpolated (F-02). The instance_id
    is guaranteed to match ^[a-z0-9][a-z0-9-]*$ by the compiler (R-03).

    This is THE single source of the artifact filename. Both the prompt preamble
    (T11) and the roster block (T17) must call this function, never format the
    name themselves (F-06).

    Args:
        instance_id: The step's immutable instance_id (e.g., 'research-a').
        topic: The run's topic slug, computed once per run (via topic_slug()).

    Returns:
        The artifact filename, guaranteed to contain no ':' or other hostile path
        components.

    Examples:
        >>> artifact_name("research-a", "crm-rollout")
        'research-a-crm-rollout.md'

    Raises:
        ValueError: if ``instance_id`` is not a bare slug. The compiler already
            enforces the same shape (R-03), but this function is the LAST point
            before a filename is built, so it refuses rather than trusts. Without
            the check, passing an agent_id here yields
            ``custom-agent:research-a.t.md``, and passing ``../../etc/passwd``
            yields a traversal — exactly F-02.
    """
    if not _INSTANCE_ID_RE.match(instance_id):
        raise ValueError(
            f"artifact_name: instance_id must match {_INSTANCE_ID_RE.pattern!r}, "
            f"got {instance_id!r} — pass the step's instance_id, never an agent_id "
            f"(synthetic agent ids carry ':' and would build a hostile path, F-02)"
        )
    # HYPHEN, not a dot (ADR-0007): local models (observed on qwen3.5:4b) read a
    # dot as a path separator and write `/joke/mountain.md` instead, corrupting
    # the artifact. Every caller is `custom-agent:`-gated, so no existing name
    # changes. Consequence: both halves are hyphen-slugs, so the name is not
    # mechanically splittable — carry instance_id separately rather than
    # parsing it back out of the filename.
    return f"{instance_id}-{topic}.md"
