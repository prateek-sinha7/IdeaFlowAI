"""Mock agent that simulates Claude responses for demo/testing without an API key."""

import asyncio
import random
from typing import AsyncGenerator

MOCK_USER_STORIES = """# Personas

| Persona | Role | Goals | Pain Points |
|---------|------|-------|-------------|
| Alex | Product Manager | Quickly generate structured backlogs from ideas | Manual story writing is slow and inconsistent |
| Sam | Developer | Clear acceptance criteria and story points | Ambiguous requirements lead to rework |
| Jordan | Designer | Visual prototypes and component specs | Translating ideas to UI takes too many iterations |

# Epic: User Authentication [P0]

**Business Value:** Secure access is foundational - blocks all other features and ensures compliance with data protection regulations.

**Priority:** P0 (Must-have)

## Story: User Registration

**As a** new user (Alex), **I want** to register an account with email and password, **so that** I can access the platform securely.

**Story Points:** 5

**Dependencies:** None

### Acceptance Criteria

- **Given** I am on the registration page, **When** I submit a valid email and password (8+ chars), **Then** my account is created and I receive a confirmation email
- **Given** I submit an email that already exists, **When** the form is submitted, **Then** I see an error "Email already registered" without revealing account details
- **Given** I submit a password shorter than 8 characters, **When** the form validates, **Then** I see a specific error about minimum length

### Definition of Done

- [ ] Code reviewed and approved
- [ ] Unit tests written and passing (>90% coverage)
- [ ] Integration tests for registration flow passing
- [ ] Documentation updated (API docs + user guide)
- [ ] Accessibility audit passed (WCAG 2.1 AA)
- [ ] Performance: registration completes in <2s

---

## Story: User Login

**As a** registered user (Alex), **I want** to log in with my credentials, **so that** I can access my dashboard and saved work.

**Story Points:** 3

**Dependencies:** User Registration

### Acceptance Criteria

- **Given** I have a valid account, **When** I submit correct credentials, **Then** I am redirected to the dashboard with a JWT token issued (24h expiry)
- **Given** I submit incorrect credentials, **When** the form is submitted, **Then** I see a generic "Invalid credentials" error (no info leakage)
- **Given** I have failed login 5 times, **When** I attempt again, **Then** my account is temporarily locked for 15 minutes

### Definition of Done

- [ ] Code reviewed and approved
- [ ] Unit tests written and passing
- [ ] Security review completed (no credential leakage)
- [ ] Rate limiting implemented and tested
- [ ] Accessibility requirements met

---

# Epic: AI Content Generation [P0]

**Business Value:** Core product differentiator - enables users to generate structured deliverables from natural language, driving engagement and retention.

**Priority:** P0 (Must-have)

## Story: Generate User Stories from Idea

**As a** product manager (Alex), **I want** to describe my product idea in natural language, **so that** I get a structured backlog with epics, stories, and acceptance criteria.

**Story Points:** 8

**Dependencies:** User Login

### Acceptance Criteria

- **Given** I am logged in and in a chat session, **When** I describe a product idea, **Then** the system generates structured user stories in Markdown within 30 seconds
- **Given** the AI is generating content, **When** I watch the preview panel, **Then** I see real-time streaming of the output
- **Given** generation is complete, **When** I review the output, **Then** it contains at least 2 epics with 2+ stories each, all with acceptance criteria

### Definition of Done

- [ ] Code reviewed and approved
- [ ] Unit tests for parser and agent
- [ ] Integration test with mock AI responses
- [ ] Streaming works without dropped chunks
- [ ] Output passes Markdown lint

---

## Story: Generate Presentation Slides

**As a** product manager (Alex), **I want** to generate a slide deck from my idea, **so that** I can present to stakeholders without manual PowerPoint work.

**Story Points:** 8

**Dependencies:** User Login

### Acceptance Criteria

- **Given** I request a presentation, **When** generation completes, **Then** I receive 5-10 slides with titles, bullets, and color schemes
- **Given** slides are generated, **When** I view the PPT preview, **Then** each slide renders with correct colors and layout
- **Given** I want to share the deck, **When** I click download, **Then** a .pptx file is generated and downloaded

### Definition of Done

- [ ] Code reviewed and approved
- [ ] Unit tests for slide parser
- [ ] Visual regression tests for slide rendering
- [ ] Download produces valid .pptx file
- [ ] Accessibility: slide content is screen-reader friendly

---

# Epic: Dashboard Experience [P1]

**Business Value:** Improves user retention by providing a polished workspace that organizes past work and enables quick access to AI features.

**Priority:** P1 (Should-have)

## Story: Three-Panel Dashboard Layout

**As a** user (Sam), **I want** a three-panel layout (sidebar, chat, preview), **so that** I can manage conversations and see outputs simultaneously.

**Story Points:** 5

**Dependencies:** User Login

### Acceptance Criteria

- **Given** I am on the dashboard, **When** the page loads, **Then** I see sidebar (280px), chat panel (flex), and preview panel (420px)
- **Given** I am on mobile (<768px), **When** the page loads, **Then** panels stack vertically with tab navigation
- **Given** I click the collapse button, **When** the preview panel collapses, **Then** the chat panel expands to fill available space

### Definition of Done

- [ ] Code reviewed and approved
- [ ] Responsive design tested at all breakpoints
- [ ] Keyboard navigation works between panels
- [ ] Performance: layout renders in <100ms

---

## Non-Functional Requirements

## Story: API Response Time

**As a** system, **I want** all API endpoints to respond within 500ms (p95), **so that** users experience a snappy interface.

**Story Points:** 3

### Acceptance Criteria

- **Given** normal load (100 concurrent users), **When** any API is called, **Then** p95 response time is <500ms
- **Given** AI generation endpoints, **When** streaming begins, **Then** first token appears within 2 seconds

## Story: Accessibility Compliance

**As a** user with disabilities (all personas), **I want** the platform to meet WCAG 2.1 AA standards, **so that** I can use all features with assistive technology.

**Story Points:** 8

### Acceptance Criteria

- **Given** any page in the application, **When** tested with a screen reader, **Then** all interactive elements are properly labeled
- **Given** keyboard-only navigation, **When** I tab through the interface, **Then** focus order is logical and visible"""

MOCK_PPT_RESPONSE = '{"slides":[{"title":"IdeaFlow AI Platform","subtitle":"Transform Ideas into Deliverables","content":[{"text":"AI-powered platform for product teams"},{"text":"From concept to structured output in minutes"}],"type":"title","layout":"title","colorScheme":{"background":"#001f3f","text":"#FFFFFF","accent":"#AAAAAA"},"speakerNotes":"Welcome everyone. Today I am excited to introduce IdeaFlow AI, a platform that transforms raw product ideas into polished, structured deliverables in minutes rather than days."},{"title":"The Problem We Solve","content":[{"text":"Product teams waste 40% of their time writing documentation manually"},{"text":"Requirements are often ambiguous, leading to costly rework cycles"},{"text":"Creating presentations takes hours of formatting instead of thinking"},{"text":"UI prototyping requires expensive tools and specialized skills"}],"type":"text","layout":"content","colorScheme":{"background":"#000000","text":"#FFFFFF","accent":"#AAAAAA"},"speakerNotes":"Research shows product teams spend nearly half their time on documentation rather than building. The gap between idea and deliverable is where productivity dies."},{"title":"Market Opportunity","content":[{"text":"AI SaaS market projected to reach $95B by 2026"},{"text":"67% CAGR in AI-powered productivity tools"}],"type":"chart","layout":"chart","chartData":{"type":"bar","labels":["2022","2023","2024","2025","2026"],"values":[12,28,45,67,95],"title":"AI SaaS Market Growth ($B)"},"colorScheme":{"background":"#001f3f","text":"#FFFFFF","accent":"#4FC3F7"},"speakerNotes":"The AI SaaS market is experiencing explosive growth. We are positioned at the intersection of AI and productivity, targeting a market that will reach 95 billion dollars by 2026."},{"title":"Feature Comparison","content":[{"text":"IdeaFlow AI leads across all key capabilities"}],"type":"table","layout":"content","tableData":{"headers":["Feature","IdeaFlow AI","Competitor A","Competitor B"],"rows":[["User Stories","\\u2713 Full","Partial","\\u2717"],["PPT Generation","\\u2713 Full","\\u2717","Partial"],["Prototyping","\\u2713 Full","\\u2717","\\u2717"],["Real-time Streaming","\\u2713","\\u2717","\\u2713"],["Export to PPTX","\\u2713","\\u2717","\\u2717"]]},"colorScheme":{"background":"#000000","text":"#FFFFFF","accent":"#4FC3F7"},"speakerNotes":"When compared to competitors, IdeaFlow AI is the only platform offering full coverage across user stories, presentations, prototyping, real-time streaming, and export capabilities."},{"title":"Platform Architecture","content":[{"text":"Modern full-stack architecture built for speed and reliability"}],"type":"two-column","layout":"two-column","columns":[["Next.js + TypeScript","Tailwind CSS + Motion","WebSocket streaming"],["FastAPI + Python","LangChain + Claude AI","SQLite database"]],"colorScheme":{"background":"#001f3f","text":"#FFFFFF","accent":"#4FC3F7"},"speakerNotes":"Our architecture separates concerns cleanly. The frontend delivers a responsive, animated experience while the backend orchestrates multiple AI agents through LangChain."},{"title":"Target User Segments","content":[{"text":"Product Managers are our primary audience at 40%"},{"text":"Followed by Developers, Designers, and Executives"}],"type":"chart","layout":"chart","chartData":{"type":"pie","labels":["Product Managers","Developers","Designers","Executives"],"values":[40,25,20,15],"title":"User Distribution"},"colorScheme":{"background":"#000000","text":"#FFFFFF","accent":"#4FC3F7"},"speakerNotes":"Our primary users are product managers who need to quickly generate structured deliverables. Developers and designers benefit from clear specs, while executives use the presentation features."},{"title":"Before vs After IdeaFlow AI","content":[{"text":"Dramatic reduction in time-to-deliverable across all workflows"}],"type":"comparison","layout":"comparison","comparisonData":{"left":{"title":"Before","items":["4+ hours writing user stories","Full day creating presentations","Weeks for UI prototypes","Inconsistent documentation"]},"right":{"title":"After","items":["5 minutes with AI generation","Instant slide deck creation","Real-time prototype preview","Standardized, professional output"]}},"colorScheme":{"background":"#001f3f","text":"#FFFFFF","accent":"#4FC3F7"},"speakerNotes":"The transformation is dramatic. Tasks that took hours or days now complete in minutes. This is not incremental improvement, it is a fundamental shift in how product teams work."},{"title":"Next Steps","content":[{"text":"Launch closed beta with 20 enterprise product teams in Q2 2025"},{"text":"Integrate with Jira, Confluence, and Notion for seamless workflows"},{"text":"Add team collaboration with real-time co-editing capabilities"},{"text":"Expand AI models to support domain-specific generation"}],"type":"text","layout":"content","colorScheme":{"background":"#001f3f","text":"#FFFFFF","accent":"#AAAAAA"},"speakerNotes":"Our roadmap focuses on enterprise adoption, integrations with existing tools, and collaborative features. We are targeting Q2 2025 for our closed beta launch with select enterprise partners."}]}'

MOCK_PROTOTYPE_RESPONSE = '{"pages":[{"name":"Login","route":"/login","components":[{"type":"Header","props":{"variant":"minimal","ariaLabel":"IdeaFlow AI Login","responsive":{"mobile":"centered logo only","desktop":"logo with tagline"}},"children":[{"type":"Logo","props":{"size":"large","ariaLabel":"IdeaFlow AI logo"}},{"type":"Text","props":{"variant":"subtitle","content":"Transform ideas into deliverables"}}],"dataFlow":"Static content, no data needed"},{"type":"Form","props":{"variant":"filled","ariaLabel":"Login form","responsive":{"mobile":"full width, stacked","desktop":"centered card 400px"}},"children":[{"type":"Input","props":{"type":"email","placeholder":"Email address","variant":"outlined","ariaLabel":"Email address input","required":true}},{"type":"Input","props":{"type":"password","placeholder":"Password","variant":"outlined","ariaLabel":"Password input","required":true}},{"type":"Button","props":{"label":"Sign In","variant":"primary","size":"large","ariaLabel":"Sign in to your account","loading":false}},{"type":"Link","props":{"label":"Create an account","route":"/register","variant":"secondary","ariaLabel":"Navigate to registration page"}}],"dataFlow":"Submits email/password to POST /api/auth/login, receives JWT token"}],"states":{"loading":"Skeleton form with pulsing input placeholders","empty":"Default state with empty form fields","error":"Red border on invalid fields with error message below","success":"Redirect to /dashboard with success toast"}},{"name":"Register","route":"/register","components":[{"type":"Header","props":{"variant":"minimal","ariaLabel":"Create Account","responsive":{"mobile":"centered","desktop":"centered with illustration"}},"children":[{"type":"Logo","props":{"size":"medium","ariaLabel":"IdeaFlow AI logo"}},{"type":"Text","props":{"variant":"heading","content":"Create your account"}}],"dataFlow":"Static content"},{"type":"Form","props":{"variant":"filled","ariaLabel":"Registration form","responsive":{"mobile":"full width stacked","desktop":"centered card 450px"}},"children":[{"type":"Input","props":{"type":"email","placeholder":"Email address","variant":"outlined","ariaLabel":"Email address","required":true}},{"type":"Input","props":{"type":"password","placeholder":"Password (8+ characters)","variant":"outlined","ariaLabel":"Password","required":true}},{"type":"Input","props":{"type":"password","placeholder":"Confirm password","variant":"outlined","ariaLabel":"Confirm password","required":true}},{"type":"Button","props":{"label":"Create Account","variant":"primary","size":"large","ariaLabel":"Create your account"}},{"type":"Link","props":{"label":"Already have an account? Sign in","route":"/login","variant":"secondary"}}],"dataFlow":"Submits to POST /api/auth/register, receives JWT token"}],"states":{"loading":"Skeleton form placeholders","empty":"Default empty form","error":"Validation errors shown inline per field","success":"Redirect to /dashboard with welcome message"}},{"name":"Dashboard","route":"/dashboard","components":[{"type":"Sidebar","props":{"width":"280px","collapsible":true,"ariaLabel":"Chat history sidebar","responsive":{"mobile":"hidden, accessible via hamburger menu","tablet":"collapsed to 56px icons only","desktop":"full 280px with labels"}},"children":[{"type":"Button","props":{"label":"New Chat","variant":"primary","icon":"plus","ariaLabel":"Start a new chat session"}},{"type":"List","props":{"items":"chatSessions","variant":"interactive","ariaLabel":"Chat history list"},"children":[{"type":"ListItem","props":{"icon":"message-square","showTimestamp":true,"ariaLabel":"Chat session item"}}]}],"dataFlow":"Fetches GET /api/chats for session list, POST /api/chats for new session"},{"type":"ChatPanel","props":{"flex":"1","ariaLabel":"Main chat conversation area","responsive":{"mobile":"full width","desktop":"flex-1 between sidebar and preview"}},"children":[{"type":"MessageList","props":{"ariaLabel":"Chat messages","variant":"streaming"},"children":[{"type":"MessageBubble","props":{"variant":"user","ariaLabel":"Your message"}},{"type":"MessageBubble","props":{"variant":"assistant","ariaLabel":"AI response"}}]},{"type":"Input","props":{"placeholder":"Describe your idea...","variant":"filled","multiline":true,"ariaLabel":"Chat message input","icon":"send"}}],"dataFlow":"WebSocket connection to /api/ws/{session_id}, streams messages in real-time"},{"type":"PreviewPanel","props":{"width":"420px","collapsible":true,"ariaLabel":"Generated content preview","responsive":{"mobile":"full screen overlay","tablet":"bottom sheet 50% height","desktop":"right panel 420px"}},"children":[{"type":"Tabs","props":{"items":["User Stories","PPT","Prototype"],"variant":"pill","ariaLabel":"Preview content tabs"}},{"type":"TabContent","props":{"ariaLabel":"Preview content area"}}],"dataFlow":"Receives streamed content from WebSocket, parsed by section type"}],"states":{"loading":"Skeleton sidebar + empty chat with loading spinner","empty":"Welcome message with suggested prompts","error":"Error banner with retry button, chat history preserved","success":"Full three-panel layout with active content"}},{"name":"Settings","route":"/settings","components":[{"type":"Header","props":{"variant":"page","title":"Settings","ariaLabel":"Settings page header","responsive":{"mobile":"sticky top","desktop":"inline"}}},{"type":"Card","props":{"variant":"outlined","title":"Profile","ariaLabel":"Profile settings section","responsive":{"mobile":"full width","desktop":"max-width 600px centered"}},"children":[{"type":"Input","props":{"type":"email","label":"Email","variant":"outlined","disabled":true,"ariaLabel":"Your email address"}},{"type":"Button","props":{"label":"Change Password","variant":"secondary","ariaLabel":"Change your password"}}],"dataFlow":"Fetches GET /api/auth/me for current user data"},{"type":"Card","props":{"variant":"outlined","title":"Appearance","ariaLabel":"Theme settings section"},"children":[{"type":"ThemePicker","props":{"options":["Navy Dark","Midnight","Charcoal","Ocean"],"ariaLabel":"Choose application theme"}}],"dataFlow":"Reads/writes theme preference to localStorage"},{"type":"Card","props":{"variant":"outlined","title":"API Configuration","ariaLabel":"API key settings"},"children":[{"type":"Input","props":{"type":"password","label":"Anthropic API Key","placeholder":"sk-ant-...","variant":"outlined","ariaLabel":"Your Anthropic API key"}},{"type":"Button","props":{"label":"Save","variant":"primary","ariaLabel":"Save API configuration"}}],"dataFlow":"Stores API key securely, used for AI generation calls"}],"states":{"loading":"Skeleton cards with pulsing content","empty":"Default state with current values populated","error":"Toast notification for save failures","success":"Success toast on save, fields updated"}},{"name":"Profile","route":"/profile","components":[{"type":"Header","props":{"variant":"page","title":"Profile","ariaLabel":"User profile page"}},{"type":"Avatar","props":{"size":"xlarge","initials":"U","ariaLabel":"User avatar","responsive":{"mobile":"centered 80px","desktop":"left-aligned 120px"}},"dataFlow":"Derived from user email initial"},{"type":"Card","props":{"variant":"filled","title":"Account Information","ariaLabel":"Account details"},"children":[{"type":"Text","props":{"label":"Email","variant":"body"}},{"type":"Text","props":{"label":"Member since","variant":"caption"}},{"type":"Badge","props":{"label":"Free Plan","variant":"outlined","color":"accent"}}],"dataFlow":"Fetches GET /api/auth/me for user profile data"},{"type":"Card","props":{"variant":"filled","title":"Usage Statistics","ariaLabel":"Usage stats"},"children":[{"type":"Text","props":{"content":"Chat sessions: 12","variant":"body"}},{"type":"Text","props":{"content":"Stories generated: 34","variant":"body"}},{"type":"Text","props":{"content":"Presentations created: 8","variant":"body"}}],"dataFlow":"Fetches GET /api/stats for usage metrics"}],"states":{"loading":"Skeleton avatar and cards","empty":"Default profile with no usage stats yet","error":"Error loading profile data with retry","success":"Full profile with stats displayed"}}],"navigation":{"type":"sidebar","items":[{"label":"Dashboard","route":"/dashboard","icon":"layout-dashboard"},{"label":"Settings","route":"/settings","icon":"settings"},{"label":"Profile","route":"/profile","icon":"user"}],"defaultRoute":"/dashboard"},"behavior":{"interactions":{"login-submit":"Validate credentials, show loading state, redirect to dashboard on success","register-submit":"Validate all fields, create account, redirect to dashboard","new-chat":"Create session via API, navigate to empty chat, focus input","send-message":"Stream AI response via WebSocket, update preview panel in real-time","collapse-preview":"Animate panel width to 0, expand chat panel","switch-tab":"Fade transition between preview content types","theme-change":"Apply theme CSS variables immediately, persist to localStorage"},"animations":{"page-transition":"Fade in 300ms ease-out","sidebar-collapse":"Slide width 280px to 56px over 200ms","message-appear":"Slide up 12px with fade over 200ms","preview-stream":"Characters appear with 20ms stagger","tab-switch":"Cross-fade 150ms","button-press":"Scale 0.97 on press, spring back","modal-open":"Fade backdrop + scale content from 0.95"}}}'

MOCK_RESPONSES = {
    "default": """Hello! I'm IdeaFlow AI, your creative partner for building products. \U0001f680

I can help you with:
- **User Stories** \u2014 Structured epics, stories, and acceptance criteria
- **Presentations** \u2014 Professional slide decks with visual layouts
- **Prototypes** \u2014 UI component definitions with navigation and behavior

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

1. **Start with the core problem** \u2014 Define what you're solving before jumping to solutions
2. **Consider your users** \u2014 Who are they and what do they need?
3. **Iterate quickly** \u2014 Build a minimal version first, then improve

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

    "quiz": """# \U0001f393 Interactive Quiz: Software Development

## Overview
Test your knowledge of modern software development practices!

---

### Question 1: What is the primary benefit of agile methodology?
- A) Faster deployment
- B) \u2713 Adaptability to changing requirements
- C) Lower costs
- D) Less documentation

**Explanation:** Agile's core strength is its ability to adapt to changing requirements through iterative development cycles.

---

### Question 2: Which testing approach verifies individual components?
- A) Integration testing
- B) End-to-end testing
- \u2713 C) Unit testing
- D) Regression testing

**Explanation:** Unit testing focuses on verifying individual components or functions in isolation.

---

### Question 3: What does CI/CD stand for?
- \u2713 A) Continuous Integration / Continuous Delivery
- B) Code Integration / Code Deployment
- C) Continuous Improvement / Continuous Development
- D) Code Inspection / Code Debugging

**Explanation:** CI/CD automates the process of integrating code changes and delivering them to production.

---

## Key Takeaways
1. Agile enables flexibility in development
2. Testing at multiple levels ensures quality
3. CI/CD automates the delivery pipeline

**Score: Keep learning! \U0001f31f**""",
}

GREETING_RESPONSES = [
    "Hey there! \U0001f44b I'm IdeaFlow AI. How can I help you today?",
    "Hi! Welcome to IdeaFlow AI. What would you like to create?",
    "Hello! I'm ready to help you build something amazing. What's on your mind?",
    "Hey! \U0001f680 Tell me about your idea and I'll help bring it to life.",
]


def _get_mock_response(message: str, mode: str = "default") -> str:
    """Get a mock response based on the mode and message content."""
    if mode != "default" and mode in MOCK_RESPONSES:
        return MOCK_RESPONSES[mode]

    lower = message.lower().strip()

    # Simple greeting detection
    if lower in ("hi", "hello", "hey", "hi!", "hello!", "hey!"):
        return random.choice(GREETING_RESPONSES)

    # User stories format (rich mock with personas, story points, Given/When/Then)
    if any(kw in lower for kw in ["user stor", "stories", "requirements", "epics"]):
        return MOCK_USER_STORIES

    # PPT format (JSON with speaker notes and layouts)
    if any(kw in lower for kw in ["ppt", "presentation", "slide", "deck"]):
        return MOCK_PPT_RESPONSE

    # Prototype format (rich with screen states, accessibility, data flow)
    if any(kw in lower for kw in ["prototype", "wireframe", "mockup"]):
        return MOCK_PROTOTYPE_RESPONSE

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
        {"id": "analyze", "label": "Analyzing your request...", "detail": "Understanding the context and requirements from your message.", "icon": "\U0001f50d"},
        {"id": "plan", "label": "Planning response strategy...", "detail": "Determining the best approach based on the selected mode.", "icon": "\U0001f4cb"},
        {"id": "generate", "label": "Generating content...", "detail": "Creating structured output using AI agents.", "icon": "\u2728"},
        {"id": "format", "label": "Formatting output...", "detail": "Applying markdown formatting and structure.", "icon": "\U0001f4dd"},
    ]

    # For deep_research mode, add extra steps
    if mode == "deep_research":
        steps = [
            {"id": "analyze", "label": "Analyzing research topic...", "detail": "Identifying key areas to investigate.", "icon": "\U0001f50d"},
            {"id": "search", "label": "Searching knowledge base...", "detail": "Querying multiple sources for comprehensive data.", "icon": "\U0001f310"},
            {"id": "synthesize", "label": "Synthesizing findings...", "detail": "Cross-referencing data points and identifying patterns.", "icon": "\U0001f9ec"},
            {"id": "report", "label": "Compiling research report...", "detail": "Structuring findings into a comprehensive report.", "icon": "\U0001f4ca"},
            {"id": "format", "label": "Formatting citations...", "detail": "Adding source attributions and references.", "icon": "\U0001f4dd"},
        ]
    elif mode == "thinking":
        steps = [
            {"id": "analyze", "label": "Analyzing problem...", "detail": "Breaking down the question into components.", "icon": "\U0001f50d"},
            {"id": "reason", "label": "Reasoning through approaches...", "detail": "Evaluating multiple strategies and trade-offs.", "icon": "\U0001f9e0"},
            {"id": "generate", "label": "Generating response...", "detail": "Composing a well-structured answer.", "icon": "\u2728"},
        ]

    # Yield steps with delays, then content
    for step in steps:
        yield {"type": "step", "step": {**step, "status": "running"}}
        await asyncio.sleep(random.uniform(1.0, 2.0))
        yield {"type": "step", "step": {**step, "status": "done"}}

    # Determine which preview section to stream to based on message content
    lower_msg = message.lower()
    section = "discovery"  # default - no preview
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
