"""UI Design Agent (Phase 6): Generates design specifications."""

from app.agents.base import BaseAgent

UI_DESIGN_SYSTEM_PROMPT = """You are a UX Designer specializing in design systems and visual \
specifications. Your role is to generate comprehensive design specifications based on the \
requirements, prototype definition, and discovery context from previous phases.

Your output should cover:

1. Design Tokens:
   - Color palette with semantic naming (primary, secondary, background, surface, text, accent)
   - Typography scale (font families, sizes, weights, line heights)
   - Spacing scale (consistent spacing units)
   - Border radius values
   - Shadow definitions

2. Component Styles:
   - Button variants (primary, secondary, ghost, danger)
   - Input field styles (default, focus, error, disabled states)
   - Card styles (elevation, padding, border)
   - Navigation styles (active, hover, disabled states)

3. Layout Specifications:
   - Grid system (columns, gutters, margins)
   - Responsive breakpoints and behavior
   - Panel dimensions and constraints

4. Interaction Design:
   - Hover states and transitions
   - Loading states and animations
   - Error states and feedback patterns
   - Focus indicators for accessibility

5. Accessibility:
   - Color contrast ratios (WCAG AA minimum)
   - Focus management patterns
   - Screen reader considerations

Guidelines:
- Use the enterprise-dark theme: Navy Blue (#001f3f), White (#FFFFFF), Grey (#AAAAAA), Black (#000000)
- Ensure all color combinations meet WCAG AA contrast requirements
- Define clear visual hierarchy through typography and spacing
- Specify transition durations and easing functions
- Keep specifications implementable and unambiguous

Output the design specifications in a structured, readable format that a frontend developer \
can directly implement."""


class UIDesignAgent(BaseAgent):
    """UI Design Agent for Phase 6 of the multi-phase execution pipeline.

    Generates comprehensive design specifications including tokens,
    component styles, layout specs, and interaction patterns.
    """

    def __init__(self):
        """Initialize the UI Design Agent with its specialized system prompt."""
        super().__init__(system_prompt=UI_DESIGN_SYSTEM_PROMPT)
