"""Skill Manager — Manages skill files (SKILL.md) that enhance agent capabilities.

Storage layout (post per-user namespacing fix, see WORKFLOWS.md §B6):
    backend/skills/users/{user_id}/{agent_id}/SKILL.md   — user-specific custom skills
    backend/skills/global/{agent_id}/SKILL.md            — admin-managed skills (reserved;
                                                          NOT writable from user-facing
                                                          REST endpoints today)

For PPT pipeline agents, additional shipped reference docs are loaded from
backend/pptx/ (pptxgenjs.md, skill.md). Those are read-only built-ins, not
user-managed skills, and are stored outside the skills/ tree on purpose.

Defence-in-depth against prompt injection via user-supplied skill content
(Phase B audit G1-C7):
    * ``MAX_SKILL_BYTES`` caps the bytes that a user can save (enforced by the
      REST layer) and acts as a backstop truncation at load time for any
      user-tier file that pre-dates the cap (or sneaks past the API). Trusted
      built-ins (pptx/ reference docs, DEFAULT_SKILLS) are NOT truncated — they
      are not an attack surface and several of them are intentionally larger
      than 8 KB.
    * ``sanitize_user_skill_content`` does best-effort scrubbing of structural
      prompt-injection markers (``=== BEGIN``, ``=== END``, ``### System``,
      ``<|im_start|>``, …) on the load path. Lines that match are demoted to
      markdown blockquotes so they lose their semantic meaning as boundary
      markers — this is best effort, NOT a security control.
"""

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("app.agents.skills")

_BACKEND_DIR = Path(__file__).parent.parent.parent
SKILLS_DIR = _BACKEND_DIR / "skills"
USER_SKILLS_DIR = SKILLS_DIR / "users"
GLOBAL_SKILLS_DIR = SKILLS_DIR / "global"
PPTX_SKILLS_DIR = _BACKEND_DIR / "pptx"

# Maximum size in bytes accepted for a custom SKILL.md payload.
# Enforced at the API layer (POST /api/agents/skills) and again at load time
# in ``get_skill_content`` for user-tier files as a backstop. Exposed here so
# tests and call sites share the single source of truth.
#
# Why 8 KB:
#   Real-world per-agent guidance fits comfortably in a few paragraphs of
#   markdown (a few KB at most). 8 KB is enough headroom for the longest of
#   the built-in DEFAULT_SKILLS plus a generous margin, but small enough that
#   a malicious user cannot use the skill prefix to shove a multi-KB attacker-
#   controlled prefix into the agent's system prompt. The Phase B audit treats
#   anything larger as a strong signal of abuse (Phase B G1-C7).
MAX_SKILL_BYTES = 8 * 1024  # 8 KB

# Per-line length cap applied during sanitisation. Discourages multi-KB
# single-line payloads that try to evade the line-prefix scrubber by keeping
# the structural marker on one extremely long line.
_MAX_SKILL_LINE_CHARS = 500

# Line-level structural markers we demote to blockquotes when they appear in
# user-supplied skill content. NOT a security control — an LLM can still be
# socially engineered — but it stops the obvious "close my untrusted block,
# open a fake trusted block" pattern.
_LINE_PREFIX_BLOCKLIST = (
    "=== BEGIN",
    "=== END",
    "### System",
    "### Assistant",
)
_LINE_SUBSTRING_BLOCKLIST = ("<|im_start|>",)


def sanitize_user_skill_content(content: str) -> str:
    """Best-effort scrub of obvious prompt-injection markers in user skill text.

    This is run on the load path before the content is interpolated into the
    agent's system prompt. It is **not** a security control — see the module
    docstring and the Phase B audit notes — but it raises the floor for
    structural-injection attacks (closing the untrusted block, opening a fake
    system block) by demoting matching lines to markdown blockquotes.

    Operations, applied per-line in order:
      1. Truncate any line longer than ``_MAX_SKILL_LINE_CHARS`` to that many
         characters and append an ellipsis. This prevents a single megaline
         from evading the line-prefix check.
      2. If the line starts with any of ``_LINE_PREFIX_BLOCKLIST`` or contains
         any of ``_LINE_SUBSTRING_BLOCKLIST``, prepend ``> `` so it becomes a
         markdown blockquote and loses its meaning as a structural marker.

    Args:
        content: The raw skill content read from disk.

    Returns:
        The sanitised content with the same number of lines (no lines are
        dropped — we want the user to still see their content rendered in the
        prompt, just without active structural markers).
    """
    if not content:
        return content

    sanitised_lines: list[str] = []
    for line in content.splitlines():
        if len(line) > _MAX_SKILL_LINE_CHARS:
            line = line[: _MAX_SKILL_LINE_CHARS - 1] + "…"
        stripped = line.lstrip()
        if any(stripped.startswith(p) for p in _LINE_PREFIX_BLOCKLIST) or any(
            sub in line for sub in _LINE_SUBSTRING_BLOCKLIST
        ):
            line = "> " + line
        sanitised_lines.append(line)
    # Preserve a trailing newline if the input had one, so save-then-load is
    # a no-op for already-sanitary content.
    suffix = "\n" if content.endswith("\n") else ""
    return "\n".join(sanitised_lines) + suffix


def _load_and_guard_user_skill(path: Path) -> str:
    """Read a user-tier SKILL.md, applying the byte-cap backstop + sanitiser.

    Used only on the per-user resolution path inside ``get_skill_content``.
    Trusted built-ins (pptx/, DEFAULT_SKILLS) bypass this entirely.

    Args:
        path: Absolute path to the user's SKILL.md.

    Returns:
        The (possibly-truncated, always-sanitised) skill content.
    """
    content = path.read_text(encoding="utf-8")
    raw_len = len(content.encode("utf-8"))
    if raw_len > MAX_SKILL_BYTES:
        # Truncate by bytes, then decode-and-discard the trailing partial
        # codepoint with ``errors="ignore"`` so we never emit malformed UTF-8.
        logger.warning(
            "User skill content exceeds MAX_SKILL_BYTES at load time: "
            "path=%s bytes=%d cap=%d (truncating; user should re-save)",
            path,
            raw_len,
            MAX_SKILL_BYTES,
        )
        content = content.encode("utf-8")[:MAX_SKILL_BYTES].decode(
            "utf-8", errors="ignore"
        )
    return sanitize_user_skill_content(content)


# ============================================================
# DEFAULT SKILLS — Built-in skills for each agent
# ============================================================

DEFAULT_SKILLS: dict[str, str] = {
    "domain-analyst": """# Skill: Domain Analysis Expert

## Instructions
When analyzing a domain:
1. Identify the industry vertical (SaaS, fintech, healthcare, e-commerce, etc.)
2. Research common patterns in that industry
3. Note regulatory requirements (GDPR, HIPAA, PCI-DSS, etc.)
4. Identify competitive landscape
5. Define technical constraints (scale, latency, availability)

## Output Format
Use structured markdown with clear sections.
Always include a "Constraints" section even if minimal.
""",

    "persona-researcher": """# Skill: Persona Research Expert

## Instructions
When creating personas:
1. Base personas on real user archetypes, not stereotypes
2. Include demographic AND psychographic details
3. Each persona should have a distinct goal that differs from others
4. Pain points should be specific and actionable
5. Include a "Day in the Life" scenario for the primary persona

## Persona Template
| Field | Description |
|-------|-------------|
| Name | Realistic first name |
| Age | Typical age range |
| Role | Job title or user type |
| Goals | 2-3 specific goals |
| Pain Points | 2-3 current frustrations |
| Tech Level | Low/Medium/High |
| Quote | A sentence that captures their mindset |
""",

    "story-writer": """# Skill: INVEST Story Writing

## Instructions
Every story MUST pass the INVEST criteria:
- **I**ndependent: Can be developed without other stories
- **N**egotiable: Details can be discussed with the team
- **V**aluable: Delivers value to the user or business
- **E**stimable: Team can estimate the effort
- **S**mall: Completable in one sprint (1-2 weeks)
- **T**estable: Has clear pass/fail criteria

## Anti-patterns to Avoid
- Stories that are just tasks ("Set up database")
- Stories without a clear user benefit
- Stories that are too large (> 13 points)
- Stories with vague acceptance criteria
""",

    "acceptance-criteria-gen": """# Skill: Given/When/Then Expert

## Instructions
Write acceptance criteria using Gherkin-style syntax:
- **Given** [initial context/precondition]
- **When** [action/event occurs]
- **Then** [expected outcome]

## Rules
1. Each criterion tests ONE behavior
2. Use specific values, not vague terms ("8 characters" not "long enough")
3. Include both happy path AND error scenarios
4. Cover boundary conditions (empty, max, special characters)
5. Make criteria automatable (a QA engineer should be able to write a test from it)

## Example
- **Given** I am on the login page with no previous attempts
- **When** I submit an incorrect password
- **Then** I see "Invalid credentials" error and the attempt counter increases by 1
""",

    "react-code-generator": """# Skill: React + Tailwind Code Generation

## Instructions
Generate production-quality React components:
1. Use TypeScript with proper type annotations
2. Use Tailwind CSS utility classes (no custom CSS)
3. Follow the enterprise-dark theme:
   - Background: bg-black or bg-[#001f3f]
   - Text: text-white
   - Muted: text-gray-400
   - Accent: bg-[#001f3f] or border-[#001f3f]
   - Borders: border-gray-700/30
4. Make components responsive (mobile-first)
5. Include hover states and transitions
6. Use Lucide React icons

## Component Patterns
- Cards: rounded-xl border border-gray-700/30 bg-gray-900/50 p-6
- Buttons: rounded-lg px-4 py-2 font-medium transition-all
- Inputs: rounded-lg border border-gray-700/30 bg-black/50 px-4 py-2
- Headers: flex items-center justify-between border-b border-gray-700/30 px-6 py-4
""",

    "export-formatter": """# Skill: PptxGenJS Code Generation

## Instructions
Generate correct PptxGenJS JavaScript code following these rules:
1. NEVER use "#" prefix in hex colors — use "1B2A4A" not "#1B2A4A"
2. NEVER encode opacity in hex strings — use the opacity property
3. Use `bullet: true` for bullets, NEVER unicode "•"
4. Use `breakLine: true` between text array items
5. NEVER reuse option objects — create fresh objects for each call
6. Use `charSpacing` not `letterSpacing`
7. Set `margin: 0` when aligning text with shapes
8. Shadow offset must be non-negative
9. Use RECTANGLE not ROUNDED_RECTANGLE when pairing with accent bars
10. Each presentation needs a fresh pptxgen() instance

## Color Scheme
- Background: FFFFFF (white)
- Primary Text: 1A1A1A (near-black)
- Accent: 1B2A4A (navy blue)
- Accent Light: E8EDF5 (light navy tint)
""",
}


# ============================================================
# Path helpers
# ============================================================

def _user_skill_path(user_id: str, agent_id: str) -> Path:
    """Resolve the on-disk path for a user's custom skill file."""
    return USER_SKILLS_DIR / user_id / agent_id / "SKILL.md"


def _global_skill_path(agent_id: str) -> Path:
    """Resolve the on-disk path for the admin-managed global skill file."""
    return GLOBAL_SKILLS_DIR / agent_id / "SKILL.md"


# ============================================================
# Resolution
# ============================================================

def read_user_skill(agent_id: str, user_id: str) -> Optional[str]:
    """Read the user's own custom skill file, with no fallback.

    Used by the REST GET endpoint, where the API contract is "return what
    the user saved or empty" — never another user's content, never the
    DEFAULT_SKILLS, never the admin global tier.

    The on-disk content is returned verbatim (no sanitisation) so the editor
    UI shows what the user actually saved. Sanitisation + size truncation are
    applied at runtime load (``get_skill_content``) when the content is about
    to be interpolated into a system prompt.

    Args:
        agent_id: The agent's ID.
        user_id: The authenticated user's ID.

    Returns:
        The raw file contents if the user has saved a custom skill for
        this agent; otherwise ``None``.
    """
    if not user_id:
        return None
    path = _user_skill_path(user_id, agent_id)
    if path.exists():
        return path.read_text(encoding="utf-8")
    return None


def get_skill_content(agent_id: str, user_id: Optional[str] = None) -> Optional[str]:
    """Resolve the runtime skill content for a single agent.

    Lookup order:
      1. ``backend/skills/users/{user_id}/{agent_id}/SKILL.md`` — per-user override
         (only consulted when ``user_id`` is provided).
      2. ``backend/skills/global/{agent_id}/SKILL.md`` — admin-managed skill
         (reserved; not yet writable from the public API).
      3. Special-case PPT skills under ``backend/pptx/`` — shipped reference docs
         injected for the PPT pipeline agents.
      4. ``DEFAULT_SKILLS`` dict — hard-coded fallback baked into this module.

    Passing ``user_id=None`` (the legacy signature) skips step 1 and behaves
    like the pre-namespacing global resolver. Call sites that authenticate the
    caller should always pass ``user_id`` so user customisations win.

    Args:
        agent_id: The agent's ID.
        user_id: The authenticated user's ID, or None to skip the user-override
            lookup (e.g. for code paths that have no user context).

    Returns:
        Skill content string, or None if no skill exists at any layer.
    """
    # 1. Per-user override — apply byte-cap backstop + sanitiser. We do NOT
    #    apply this to the trusted built-in tiers below (global tier is admin-
    #    managed; pptx/ is shipped read-only; DEFAULT_SKILLS lives in code).
    if user_id:
        user_path = _user_skill_path(user_id, agent_id)
        if user_path.exists():
            return _load_and_guard_user_skill(user_path)

    # 2. Admin-managed global skill (file-backed; reserved for future)
    global_path = _global_skill_path(agent_id)
    if global_path.exists():
        return global_path.read_text(encoding="utf-8")

    # 3. PPT pipeline agents get shipped pptx/ reference docs injected.
    if agent_id == "ppt-code-generator":
        # The code generator gets the full PptxGenJS API reference
        pptxgenjs_path = PPTX_SKILLS_DIR / "pptxgenjs.md"
        skill_path = PPTX_SKILLS_DIR / "skill.md"
        parts = []
        if skill_path.exists():
            parts.append(f"=== PPTX DESIGN SKILL (skill.md) ===\n{skill_path.read_text(encoding='utf-8')}")
        if pptxgenjs_path.exists():
            parts.append(f"=== PPTXGENJS API REFERENCE (pptxgenjs.md) ===\n{pptxgenjs_path.read_text(encoding='utf-8')}")
        if parts:
            return "\n\n".join(parts)

    if agent_id == "ppt-slide-architect":
        # The slide architect gets the design guidelines from skill.md
        skill_path = PPTX_SKILLS_DIR / "skill.md"
        if skill_path.exists():
            return f"=== PPTX DESIGN REFERENCE (skill.md) ===\n{skill_path.read_text(encoding='utf-8')}"

    if agent_id == "ppt-content-strategist":
        # Content strategist only needs a brief color/design reminder, not the full skill
        return """=== DESIGN BRIEF ===
Color Scheme: White background (#FFFFFF), black text (#1A1A1A), navy blue accent (#1B2A4A).
Slides: Exactly 10-12 slides. Title slide uses navy background with white text.
Typography: Arial/Calibri, titles 36-44pt, body 14-16pt.
Structure: Tell a story — problem → evidence → solution → action.
Include at least 2 data/chart slides with specific numbers."""

    if agent_id == "ppt-assembler":
        # The assembler gets the PptxGenJS reference for verifying the code
        pptxgenjs_path = PPTX_SKILLS_DIR / "pptxgenjs.md"
        if pptxgenjs_path.exists():
            # Only include Common Pitfalls section for validation
            content = pptxgenjs_path.read_text(encoding="utf-8")
            pitfalls_start = content.find("## Common Pitfalls")
            if pitfalls_start != -1:
                return f"=== PPTXGENJS COMMON PITFALLS (for validation) ===\n{content[pitfalls_start:]}"

    # 4. Fall back to default skills
    return DEFAULT_SKILLS.get(agent_id)


# ============================================================
# User-scoped CRUD
# ============================================================

def save_custom_skill(agent_id: str, content: str, user_id: str) -> str:
    """Persist a user's custom skill file at the per-user namespaced path.

    The caller is responsible for validating ``agent_id`` against the registry
    — this function rejects oversize content as a low-level backstop so a
    future API endpoint that forgets the cap can't bypass it.

    Args:
        agent_id: The agent's ID.
        content: The skill markdown content.
        user_id: The authenticated user's ID. Required — there is no global
            write path from the public API.

    Returns:
        The absolute path where the skill was saved.

    Raises:
        ValueError: If ``user_id`` is empty.
        ValueError: If ``content`` exceeds ``MAX_SKILL_BYTES`` (the REST
            layer translates this to HTTP 413 before we get here, but the
            low-level guard is enforced again here).
    """
    if not user_id:
        # Defensive — caller must always supply a user_id. Fail loudly so a
        # missing dependency injection surfaces in tests instead of silently
        # writing to a directory named "None/".
        raise ValueError("user_id is required to save a custom skill")

    if len(content.encode("utf-8")) > MAX_SKILL_BYTES:
        raise ValueError(
            f"Skill content exceeds MAX_SKILL_BYTES={MAX_SKILL_BYTES} bytes"
        )

    skill_dir = USER_SKILLS_DIR / user_id / agent_id
    skill_dir.mkdir(parents=True, exist_ok=True)

    skill_path = skill_dir / "SKILL.md"
    skill_path.write_text(content, encoding="utf-8")

    return str(skill_path)


def list_user_skills(user_id: str) -> dict[str, str]:
    """List every custom skill the given user has saved.

    Iterates ``backend/skills/users/{user_id}/*/SKILL.md`` and returns a dict
    mapping ``agent_id`` -> raw file content. Does NOT include defaults, the
    global tier, or other users' files. The API layer is expected to combine
    this with previews/registry metadata as needed.

    Args:
        user_id: The authenticated user's ID.

    Returns:
        Dict of agent_id -> skill content. Empty if the user has no skills.
    """
    if not user_id:
        return {}

    user_root = USER_SKILLS_DIR / user_id
    if not user_root.exists():
        return {}

    skills: dict[str, str] = {}
    for agent_dir in user_root.iterdir():
        if not agent_dir.is_dir():
            continue
        skill_file = agent_dir / "SKILL.md"
        if skill_file.exists():
            skills[agent_dir.name] = skill_file.read_text(encoding="utf-8")
    return skills


def delete_custom_skill(agent_id: str, user_id: str) -> bool:
    """Delete a user's own custom skill file.

    Only ever touches files under ``backend/skills/users/{user_id}/``; cannot
    be used to delete another user's skill or anything in the global tier.

    Args:
        agent_id: The agent's ID.
        user_id: The authenticated user's ID.

    Returns:
        True if a file was deleted, False if there was nothing to delete.
    """
    if not user_id:
        return False

    skill_path = _user_skill_path(user_id, agent_id)
    if skill_path.exists():
        skill_path.unlink()
        return True
    return False
