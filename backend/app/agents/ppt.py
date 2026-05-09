"""PPT Agent — Legacy wrapper for backward compatibility.

The PPT pipeline has been redesigned to use a 4-agent pipeline defined in
backend/app/agents/ppt_pipeline.py and registered in registry.py.

This module is kept for backward compatibility with the orchestrator import.
The actual PPT generation now uses the pipeline executor with agents:
  1. Content Strategist
  2. Slide Architect
  3. PptxGenJS Code Generator (with pptx/ folder skills injected)
  4. Presentation Assembler
"""

from app.agents.base import BaseAgent
from app.agents.ppt_pipeline import CONTENT_STRATEGIST_PROMPT


class PPTAgent(BaseAgent):
    """Legacy PPT Agent — kept for orchestrator compatibility.

    The real PPT generation uses the pipeline executor with 4 specialized agents.
    This agent is only used if the orchestrator calls it directly (Phase 4).
    """

    def __init__(self):
        """Initialize with the content strategist prompt as a fallback."""
        super().__init__(system_prompt=CONTENT_STRATEGIST_PROMPT)
