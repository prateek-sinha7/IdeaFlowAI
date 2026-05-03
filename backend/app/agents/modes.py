"""Chat mode definitions with system prompt enhancers.

Each mode modifies the system prompt sent to Claude to alter its behavior.
Modes are selected by the user in the frontend and passed via WebSocket.
"""

CHAT_MODES: dict[str, str] = {
    "default": "",
    "thinking": (
        "You are in deep thinking mode. Before answering, show your step-by-step "
        "reasoning process inside <thinking>...</thinking> tags. Break down the problem, "
        "consider multiple angles, evaluate trade-offs, then provide your final answer. "
        "Be thorough and analytical."
    ),
    "deep_research": (
        "You are in deep research mode. Provide an extremely comprehensive, well-structured "
        "research report on the topic. Include: Executive Summary, Key Findings (with details), "
        "Analysis, Comparisons, Pros/Cons, Recommendations, and Sources/References. Use markdown "
        "formatting with headers, bullet points, and tables where appropriate. Be exhaustive "
        "and authoritative."
    ),
    "web_search": (
        "You are in web search simulation mode. Format your response as if you've searched "
        "the web for the most current information. Structure your response with: relevant "
        "findings from multiple perspectives, key facts and data points, source attributions "
        "(cite plausible sources), and a summary. Use markdown formatting. Note: This is "
        "based on your training data, not live web results."
    ),
    "quiz": (
        "You are in quiz/learning mode. Based on the user's topic, create an interactive "
        "learning experience: 1) Start with a brief overview of the topic, 2) Generate 5 "
        "multiple-choice questions with 4 options each (mark correct answers with ✓), "
        "3) Provide detailed explanations for each answer, 4) End with key takeaways and "
        "further learning suggestions. Make it engaging and educational."
    ),
}


def get_mode_prompt(mode: str) -> str:
    """Get the system prompt enhancement for a given mode.

    Args:
        mode: The mode key (e.g., "thinking", "deep_research").

    Returns:
        The mode-specific system prompt string, or empty string for unknown modes.
    """
    return CHAT_MODES.get(mode, "")
