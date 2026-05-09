"""Skill Manager — Manages skill files (SKILL.md) that enhance agent capabilities.

For PPT pipeline agents, skills are loaded from the backend/pptx/ folder
which contains comprehensive PptxGenJS API reference and design guidelines.
"""

import os
from pathlib import Path
from typing import Optional

SKILLS_DIR = Path(__file__).parent.parent.parent / "skills"
PPTX_SKILLS_DIR = Path(__file__).parent.parent.parent / "pptx"


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


def get_skill_content(agent_id: str) -> Optional[str]:
    """Get the skill content for an agent.

    Checks custom skills directory first, then falls back to defaults.
    For PPT pipeline agents, loads skills from the pptx/ folder.

    Args:
        agent_id: The agent's ID

    Returns:
        Skill content string, or None if no skill exists
    """
    # Check custom skills directory
    custom_skill_path = SKILLS_DIR / agent_id / "SKILL.md"
    if custom_skill_path.exists():
        return custom_skill_path.read_text(encoding="utf-8")

    # PPT pipeline agents get pptx/ folder skills injected
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

    # Fall back to default skills
    return DEFAULT_SKILLS.get(agent_id)


def save_custom_skill(agent_id: str, content: str) -> str:
    """Save a custom skill file for an agent.

    Args:
        agent_id: The agent's ID
        content: The skill markdown content

    Returns:
        The path where the skill was saved
    """
    skill_dir = SKILLS_DIR / agent_id
    skill_dir.mkdir(parents=True, exist_ok=True)

    skill_path = skill_dir / "SKILL.md"
    skill_path.write_text(content, encoding="utf-8")

    return str(skill_path)


def list_all_skills() -> dict[str, str]:
    """List all available skills (default + custom).

    Returns:
        Dict of agent_id -> skill content
    """
    skills = dict(DEFAULT_SKILLS)

    # Add custom skills
    if SKILLS_DIR.exists():
        for skill_dir in SKILLS_DIR.iterdir():
            if skill_dir.is_dir():
                skill_file = skill_dir / "SKILL.md"
                if skill_file.exists():
                    skills[skill_dir.name] = skill_file.read_text(encoding="utf-8")

    return skills


def delete_custom_skill(agent_id: str) -> bool:
    """Delete a custom skill file.

    Args:
        agent_id: The agent's ID

    Returns:
        True if deleted, False if not found
    """
    skill_path = SKILLS_DIR / agent_id / "SKILL.md"
    if skill_path.exists():
        skill_path.unlink()
        return True
    return False
