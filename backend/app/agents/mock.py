"""Mock agent that simulates Claude responses for demo/testing without an API key."""

import asyncio
import random
from typing import AsyncGenerator

MOCK_RESPONSES = {
    "default": """Hello! I'm IdeaFlow AI, your creative partner for building products. 🚀

I can help you with:
- **User Stories** — Structured epics, stories, and acceptance criteria
- **Presentations** — Professional slide decks with visual layouts
- **Prototypes** — UI component definitions with navigation and behavior

What would you like to create today? Just describe your idea and I'll get started!""",

    "thinking": """<thinking>
Let me analyze this step by step:

1. First, I need to understand the core request
2. Consider multiple approaches and their trade-offs
3. Evaluate feasibility and complexity
4. Determine the best path forward

The user is asking a question that requires careful reasoning. Let me break it down into components and analyze each one systematically.

After considering all angles, I believe the best approach is to provide a comprehensive yet practical answer.
</thinking>

Based on my analysis, here's what I recommend:

## Key Insights

1. **Start with the core problem** — Define what you're solving before jumping to solutions
2. **Consider your users** — Who are they and what do they need?
3. **Iterate quickly** — Build a minimal version first, then improve

Would you like me to dive deeper into any of these areas?""",

    "deep_research": """# Comprehensive Research Report

## Executive Summary
This report provides an in-depth analysis of the topic based on current industry trends, best practices, and expert insights.

## Key Findings

### 1. Market Overview
The market has seen significant growth over the past year, with a **32% increase** in adoption rates across enterprise segments.

### 2. Technology Trends
| Trend | Adoption Rate | Impact |
|-------|--------------|--------|
| AI Integration | 78% | High |
| Cloud-Native | 85% | Critical |
| Real-time Processing | 62% | Medium |

### 3. Best Practices
- Implement iterative development cycles
- Focus on user feedback loops
- Maintain comprehensive documentation
- Use automated testing pipelines

## Recommendations
1. Start with a pilot program to validate assumptions
2. Invest in team training and tooling
3. Establish clear metrics for success

## Sources
- Industry Report 2025, Gartner
- Technology Trends Survey, McKinsey
- Developer Experience Study, Stack Overflow""",

    "web_search": """## Search Results

### 1. Official Documentation
**Source:** docs.example.com
> The recommended approach involves setting up a structured workflow with clear milestones and deliverables. This ensures alignment across teams.

### 2. Community Best Practices
**Source:** dev.to/best-practices
> Experienced developers suggest starting with a minimal viable product (MVP) and iterating based on user feedback. Key metrics to track include user engagement and task completion rates.

### 3. Expert Analysis
**Source:** techcrunch.com/analysis
> Industry experts predict that this approach will become the standard by 2026, with early adopters seeing 40% improvement in productivity.

### 4. Tutorial & Guide
**Source:** medium.com/tutorials
> Step-by-step guide covering setup, configuration, and deployment. Includes code examples and common pitfalls to avoid.

---
*Note: These results are simulated for demo purposes.*""",

    "quiz": """# 🎓 Interactive Quiz: Software Development

## Overview
Test your knowledge of modern software development practices!

---

### Question 1: What is the primary benefit of agile methodology?
- A) Faster deployment
- B) ✓ Adaptability to changing requirements
- C) Lower costs
- D) Less documentation

**Explanation:** Agile's core strength is its ability to adapt to changing requirements through iterative development cycles.

---

### Question 2: Which testing approach verifies individual components?
- A) Integration testing
- B) End-to-end testing
- ✓ C) Unit testing
- D) Regression testing

**Explanation:** Unit testing focuses on verifying individual components or functions in isolation.

---

### Question 3: What does CI/CD stand for?
- ✓ A) Continuous Integration / Continuous Delivery
- B) Code Integration / Code Deployment
- C) Continuous Improvement / Continuous Development
- D) Code Inspection / Code Debugging

**Explanation:** CI/CD automates the process of integrating code changes and delivering them to production.

---

## Key Takeaways
1. Agile enables flexibility in development
2. Testing at multiple levels ensures quality
3. CI/CD automates the delivery pipeline

**Score: Keep learning! 🌟**""",
}

GREETING_RESPONSES = [
    "Hey there! 👋 I'm IdeaFlow AI. How can I help you today?",
    "Hi! Welcome to IdeaFlow AI. What would you like to create?",
    "Hello! I'm ready to help you build something amazing. What's on your mind?",
    "Hey! 🚀 Tell me about your idea and I'll help bring it to life.",
]


def _get_mock_response(message: str, mode: str = "default") -> str:
    """Get a mock response based on the mode and message content."""
    if mode != "default" and mode in MOCK_RESPONSES:
        return MOCK_RESPONSES[mode]

    lower = message.lower().strip()

    # Simple greeting detection
    if lower in ("hi", "hello", "hey", "hi!", "hello!", "hey!"):
        return random.choice(GREETING_RESPONSES)

    # User stories format (Markdown that the preview parser understands)
    if any(kw in lower for kw in ["user stor", "stories", "requirements", "epics"]):
        return """# User Authentication
Secure login and registration system for the platform.

## User Registration
As a new user, I want to register an account so I can access the platform.
- System validates email format and uniqueness
- Password must be at least 8 characters
- User receives a confirmation email after registration

## User Login
As a registered user, I want to log in so I can access my dashboard.
- System authenticates credentials against stored hash
- JWT token issued with 24-hour expiry
- Failed login shows generic error message

# Dashboard Experience
Core dashboard features for authenticated users.

## View Dashboard
As a user, I want to see a three-panel dashboard so I can manage my work.
- Sidebar shows chat history
- Center panel displays the active conversation
- Preview panel shows generated outputs

## Create New Chat
As a user, I want to start a new conversation so I can generate fresh content.
- New chat button creates a session instantly
- Chat appears at the top of the sidebar list
- Previous chat state is preserved"""

    # PPT format (JSON that the preview parser understands)
    if any(kw in lower for kw in ["ppt", "presentation", "slide", "deck"]):
        return '{"slides":[{"title":"Project Overview","content":[{"text":"AI-powered SaaS platform for enterprise teams"},{"text":"Generates user stories, presentations, and prototypes"},{"text":"Real-time collaboration with streaming responses"},{"text":"Built with Next.js, FastAPI, and Claude AI"}],"type":"text","colorScheme":{"background":"#001f3f","text":"#FFFFFF","accent":"#AAAAAA"}},{"title":"Key Features","content":[{"text":"Multi-agent AI orchestration with specialized roles"},{"text":"WebSocket streaming for real-time interactions"},{"text":"Enterprise-dark themed UI with 4 theme options"},{"text":"Voice input and text-to-speech capabilities"}],"type":"text","colorScheme":{"background":"#001f3f","text":"#FFFFFF","accent":"#AAAAAA"}},{"title":"Architecture","content":[{"text":"Frontend: React/Next.js with TypeScript"},{"text":"Backend: Python/FastAPI with SQLite"},{"text":"AI: LangChain with Anthropic Claude API"},{"text":"Real-time: WebSocket bidirectional streaming"}],"type":"text","colorScheme":{"background":"#000000","text":"#FFFFFF","accent":"#001f3f"}}]}'

    # Prototype format
    if any(kw in lower for kw in ["prototype", "wireframe", "mockup"]):
        return '{"pages":[{"name":"Login","route":"/login","components":[{"type":"Form","props":{"fields":["email","password"]},"children":[{"type":"Input","props":{"type":"email","placeholder":"Email"}},{"type":"Input","props":{"type":"password","placeholder":"Password"}},{"type":"Button","props":{"label":"Sign In"}}]}]},{"name":"Dashboard","route":"/dashboard","components":[{"type":"Sidebar","props":{"width":"280px"},"children":[{"type":"Button","props":{"label":"New Chat"}},{"type":"List","props":{"items":"chats"}}]},{"type":"ChatPanel","props":{"flex":"1"},"children":[{"type":"MessageList","props":{}},{"type":"Input","props":{"placeholder":"Message..."}}]},{"type":"PreviewPanel","props":{"width":"420px"},"children":[{"type":"Tabs","props":{"items":["Stories","PPT","Prototype"]}}]}]}],"navigation":{"routes":{"/login":"Login","/dashboard":"Dashboard","/register":"Register"},"defaultRoute":"/login"},"behavior":{"interactions":{"login-submit":"Validate credentials and redirect to dashboard","new-chat":"Create session and load empty chat","send-message":"Stream AI response via WebSocket"},"animations":{"page-transition":"Fade in 300ms","sidebar-collapse":"Slide width 280px to 56px","message-appear":"Slide up with fade"}}}'

    # Default rich response
    return MOCK_RESPONSES["default"]


async def mock_stream_response(
    message: str, mode: str = "default"
) -> AsyncGenerator[str, None]:
    """Stream a mock response character by character with realistic delays."""
    response = _get_mock_response(message, mode)

    # Stream in small chunks (2-5 chars) with slight delays to simulate real streaming
    i = 0
    while i < len(response):
        chunk_size = random.randint(2, 6)
        chunk = response[i : i + chunk_size]
        yield chunk
        i += chunk_size
        # Vary the delay for realistic feel
        await asyncio.sleep(random.uniform(0.01, 0.04))


async def mock_stream_with_steps(
    message: str, mode: str = "default"
) -> AsyncGenerator[dict, None]:
    """Yield step dicts and content chunks for realistic demo with process indicators."""
    # Steps vary by mode
    steps = [
        {"id": "analyze", "label": "Analyzing your request...", "detail": "Understanding the context and requirements from your message.", "icon": "🔍"},
        {"id": "plan", "label": "Planning response strategy...", "detail": "Determining the best approach based on the selected mode.", "icon": "📋"},
        {"id": "generate", "label": "Generating content...", "detail": "Creating structured output using AI agents.", "icon": "✨"},
        {"id": "format", "label": "Formatting output...", "detail": "Applying markdown formatting and structure.", "icon": "📝"},
    ]

    # For deep_research mode, add extra steps
    if mode == "deep_research":
        steps = [
            {"id": "analyze", "label": "Analyzing research topic...", "detail": "Identifying key areas to investigate.", "icon": "🔍"},
            {"id": "search", "label": "Searching knowledge base...", "detail": "Querying multiple sources for comprehensive data.", "icon": "🌐"},
            {"id": "synthesize", "label": "Synthesizing findings...", "detail": "Cross-referencing data points and identifying patterns.", "icon": "🧬"},
            {"id": "report", "label": "Compiling research report...", "detail": "Structuring findings into a comprehensive report.", "icon": "📊"},
            {"id": "format", "label": "Formatting citations...", "detail": "Adding source attributions and references.", "icon": "📝"},
        ]
    elif mode == "thinking":
        steps = [
            {"id": "analyze", "label": "Analyzing problem...", "detail": "Breaking down the question into components.", "icon": "🔍"},
            {"id": "reason", "label": "Reasoning through approaches...", "detail": "Evaluating multiple strategies and trade-offs.", "icon": "🧠"},
            {"id": "generate", "label": "Generating response...", "detail": "Composing a well-structured answer.", "icon": "✨"},
        ]

    # Yield steps with delays, then content
    for step in steps:
        yield {"type": "step", "step": {**step, "status": "running"}}
        await asyncio.sleep(random.uniform(1.0, 2.0))
        yield {"type": "step", "step": {**step, "status": "done"}}

    # Determine which preview section to stream to based on message content
    lower_msg = message.lower()
    section = "discovery"  # default — no preview
    if any(kw in lower_msg for kw in ["user stor", "stories", "requirements", "epics"]):
        section = "user_stories"
    elif any(kw in lower_msg for kw in ["ppt", "presentation", "slide", "deck"]):
        section = "ppt"
    elif any(kw in lower_msg for kw in ["prototype", "ui", "wireframe", "mockup"]):
        section = "prototype"

    # Then yield content chunks with the section info
    response = _get_mock_response(message, mode)
    i = 0
    while i < len(response):
        chunk_size = random.randint(2, 6)
        chunk = response[i : i + chunk_size]
        yield {"type": "chunk", "chunk": chunk, "section": section}
        i += chunk_size
        await asyncio.sleep(random.uniform(0.01, 0.04))


async def mock_generate_title(message: str) -> str:
    """Generate a mock chat title from the message."""
    await asyncio.sleep(0.1)
    lower = message.lower()
    if "brainstorm" in lower or "idea" in lower:
        return "Product Brainstorming"
    if "architecture" in lower or "technical" in lower:
        return "Technical Architecture"
    if "user stor" in lower:
        return "User Story Creation"
    if "presentation" in lower or "deck" in lower or "slide" in lower:
        return "Presentation Design"
    # Default: use first few words
    words = message.split()[:4]
    return " ".join(words).strip(".,!?")[:40]
