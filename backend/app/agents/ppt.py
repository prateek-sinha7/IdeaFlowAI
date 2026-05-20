"""PPT Agent — Legacy wrapper for backward compatibility.

The PPT pipeline has been redesigned to use a 4-agent pipeline registered in registry.py.

This module is kept for backward compatibility with the orchestrator import.
The actual PPT generation now uses the pipeline executor with agents:
  1. Content Strategist
  2. Slide Architect
  3. PptxGenJS Code Generator (with pptx/ folder skills injected)
  4. Presentation Assembler
"""

from app.agents.base import BaseAgent

# Inlined from registry.py (previously sourced from deleted ppt_pipeline.py)
_COLOR_CONSTRAINT = """
## Color Scheme (STRICT — no other colors allowed):
- Background: white (#FFFFFF) only
- Text: black (#1A1A1A) only
- Accent: navy blue (#1B2A4A) only
- 10-12 slides, 16:9 aspect ratio

You may ONLY use these three colors: #FFFFFF, #1A1A1A, #1B2A4A.
No other hex values. No grays, no blues, no light tints, no gradients.
Icons must be monochrome navy (#1B2A4A) on white, or white (#FFFFFF) on navy.
No colorful icons, no emoji, no multi-color illustrations.

Everything else is up to you — layout, typography, charts, shapes. Be creative within this palette.
"""

CONTENT_STRATEGIST_PROMPT = f"""You are a world-class Presentation Content Strategist.

Analyze the user's topic and create a compelling 10-12 slide presentation plan.

{_COLOR_CONSTRAINT}

For each slide, specify the title, key message, exact content text, and any data/stats to include.
Make it tell a story. Be specific — use real numbers, names, and evidence. No generic filler.
"""


class PPTAgent(BaseAgent):
    """Legacy PPT Agent — kept for orchestrator compatibility.

    The real PPT generation uses the pipeline executor with 4 specialized agents.
    This agent is only used if the orchestrator calls it directly (Phase 4).
    """

    def __init__(self):
        """Initialize with the content strategist prompt as a fallback."""
        super().__init__(system_prompt=CONTENT_STRATEGIST_PROMPT)
