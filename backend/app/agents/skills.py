"""Skill Manager — Manages skill files (SKILL.md) that enhance agent capabilities."""

import os
from pathlib import Path
from typing import Optional

SKILLS_DIR = Path(__file__).parent.parent.parent / "skills"


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

    "export-formatter": """# Skill: JSON Schema Compliance

## Instructions
The output MUST be a single valid JSON object.
- No markdown code fences
- No explanatory text before or after
- All strings properly escaped
- All required fields present
- Arrays can be empty but must exist

## Validation Rules
- slides array: 1-10 items
- content array per slide: 1-5 items
- colorScheme: must have background, text, accent
- type: must be one of the allowed values
- speakerNotes: required for every slide
""",
}


def get_skill_content(agent_id: str) -> Optional[str]:
    """Get the skill content for an agent.

    Checks custom skills directory first, then falls back to defaults.

    Args:
        agent_id: The agent's ID

    Returns:
        Skill content string, or None if no skill exists
    """
    # Check custom skills directory
    custom_skill_path = SKILLS_DIR / agent_id / "SKILL.md"
    if custom_skill_path.exists():
        return custom_skill_path.read_text(encoding="utf-8")

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
