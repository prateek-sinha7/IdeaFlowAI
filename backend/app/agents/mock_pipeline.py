"""Mock Pipeline Executor — Simulates agent pipeline execution without API keys."""

import asyncio
import random
import time
from typing import AsyncGenerator

from app.agents.registry import get_pipeline_agents


# ============================================================
# MOCK AGENT OUTPUTS — Realistic responses per agent
# ============================================================

MOCK_USER_STORY_OUTPUTS: dict[str, str] = {
    "domain-analyst": """## Domain Analysis

**Domain:** Enterprise SaaS / AI-Powered Productivity
**Core Problem:** Product teams spend 40%+ of time on manual documentation instead of building.
**Target Market:** Product managers, developers, and designers at mid-to-large companies (50-5000 employees).

**Key Constraints:**
- Must support real-time collaboration
- Data privacy compliance (SOC2, GDPR)
- Sub-2s response time for AI generation
- Must integrate with existing tools (Jira, Confluence)

**Scope Boundaries:**
- In scope: User stories, presentations, prototypes
- Out of scope: Code generation, deployment, project management""",

    "persona-researcher": """## User Personas

| Persona | Role | Goals | Pain Points | Tech Savviness |
|---------|------|-------|-------------|----------------|
| Alex | Product Manager | Quickly generate structured backlogs | Manual story writing is slow and inconsistent | High |
| Sam | Senior Developer | Clear acceptance criteria and dependencies | Ambiguous requirements lead to rework | High |
| Jordan | UX Designer | Visual prototypes from descriptions | Translating ideas to UI takes too many iterations | Medium |
| Morgan | VP of Product | Executive presentations from data | Creating decks takes a full day | Medium |
| Casey | Scrum Master | Well-estimated, INVEST-compliant stories | Teams argue about story points | High |""",

    "epic-architect": """## Epics

### Epic 1: User Authentication & Access Control [P0]
**Business Value:** Security foundation — blocks all features, ensures compliance.
**Success Metrics:** 99.9% auth uptime, <500ms login, zero credential leaks.

### Epic 2: AI Content Generation Engine [P0]
**Business Value:** Core differentiator — drives user engagement and retention.
**Success Metrics:** <30s generation time, 85% user satisfaction, 3x weekly usage.

### Epic 3: Real-Time Collaboration [P1]
**Business Value:** Enterprise stickiness — teams that collaborate together stay together.
**Success Metrics:** 60% of users share outputs, <100ms sync latency.

### Epic 4: Dashboard & Workspace [P1]
**Business Value:** Retention driver — organized workspace keeps users coming back.
**Success Metrics:** 70% DAU/MAU ratio, <3s page load, 90% feature discoverability.""",

    "story-writer": """## Story: User Registration

**As a** new user (Alex), **I want** to register with email and password, **so that** I can access the platform securely.

**Story Points:** 5 | **Dependencies:** None

## Story: User Login

**As a** registered user (Alex), **I want** to log in with my credentials, **so that** I can access my dashboard and saved work.

**Story Points:** 3 | **Dependencies:** User Registration

## Story: Generate User Stories from Idea

**As a** product manager (Alex), **I want** to describe my idea in natural language, **so that** I get a structured backlog with epics, stories, and acceptance criteria.

**Story Points:** 8 | **Dependencies:** User Login

## Story: Generate Presentation Slides

**As a** VP of Product (Morgan), **I want** to generate a slide deck from my idea, **so that** I can present to stakeholders without manual PowerPoint work.

**Story Points:** 8 | **Dependencies:** User Login

## Story: Real-Time Preview Streaming

**As a** designer (Jordan), **I want** to see content generating in real-time, **so that** I can provide feedback early without waiting for completion.

**Story Points:** 5 | **Dependencies:** AI Content Generation""",

    "acceptance-criteria-gen": """### Acceptance Criteria — User Registration

- **Given** I am on the registration page, **When** I submit a valid email and password (8+ chars), **Then** my account is created and I receive a confirmation email
- **Given** I submit an email that already exists, **When** the form is submitted, **Then** I see "Email already registered" without revealing account details
- **Given** I submit a password shorter than 8 characters, **When** the form validates, **Then** I see a specific error about minimum length

### Acceptance Criteria — Generate User Stories

- **Given** I am logged in, **When** I describe a product idea, **Then** the system generates structured stories within 30 seconds
- **Given** the AI is generating, **When** I watch the preview, **Then** I see real-time streaming output
- **Given** generation is complete, **When** I review output, **Then** it contains 2+ epics with 2+ stories each""",

    "story-point-estimator": """## Story Point Estimates (Fibonacci)

| Story | Points | Rationale |
|-------|--------|-----------|
| User Registration | 5 | Moderate: form validation, email service, error handling |
| User Login | 3 | Simple: JWT generation, credential check, rate limiting |
| Generate User Stories | 8 | Complex: AI orchestration, streaming, parsing |
| Generate Presentations | 8 | Complex: multi-agent pipeline, JSON schema, charts |
| Real-Time Preview | 5 | Moderate: WebSocket streaming, section routing |
| Dashboard Layout | 5 | Moderate: responsive 3-panel, collapse/expand |
| Export to PPTX | 5 | Moderate: PptxGenJS integration, chart rendering |

**Total Velocity Estimate:** 39 points
**Sprint Capacity (30pts/sprint):** ~1.3 sprints for MVP""",

    "dependency-mapper": """## Dependency Map

```
User Registration ──► User Login ──► AI Generation ──► Preview Streaming
                                  ──► PPT Generation ──► Export to PPTX
                                  ──► Prototype Gen
```

**Critical Path:** Registration → Login → AI Generation → Preview
**Parallel Tracks:** PPT and Prototype can run in parallel after Login
**Blockers:** No external blockers identified""",

    "nfr-specialist": """## Non-Functional Requirements

### NFR-1: Performance
- API p95 response time < 500ms
- AI first-token latency < 2 seconds
- WebSocket message delivery < 100ms

### NFR-2: Security
- JWT tokens with 24h expiry
- bcrypt password hashing (12 rounds)
- Rate limiting: 5 failed logins → 15min lockout

### NFR-3: Accessibility
- WCAG 2.1 AA compliance
- Keyboard navigation for all features
- Screen reader compatible

### NFR-4: Reliability
- 99.9% uptime SLA
- Graceful degradation on AI service failure
- Auto-reconnect WebSocket with exponential backoff""",

    "dod-generator": """## Definition of Done (Global)

- [ ] Code reviewed and approved by 1+ peer
- [ ] Unit tests written and passing (>80% coverage)
- [ ] Integration tests for critical paths
- [ ] Documentation updated (API docs + user guide)
- [ ] Accessibility audit passed
- [ ] Performance benchmarks met
- [ ] No critical/high security vulnerabilities
- [ ] Deployed to staging and smoke-tested""",

    "journey-mapper": """## User Journey — Alex (Product Manager)

| Stage | Touchpoint | Action | Emotion | Opportunity |
|-------|-----------|--------|---------|-------------|
| Awareness | Landing page | Reads value prop | Curious | Clear demo video |
| Consideration | Pricing page | Compares plans | Cautious | Free trial CTA |
| Onboarding | Registration | Creates account | Hopeful | Guided tutorial |
| First Use | Dashboard | Types first idea | Excited | Smart suggestions |
| Generation | Preview panel | Watches AI stream | Delighted | Progress indicators |
| Export | Download button | Gets .md/.pptx | Satisfied | Share options |
| Advocacy | Team invite | Shares with team | Proud | Referral rewards |""",

    "risk-assessor": """## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| AI API rate limits hit during peak | Medium | High | Implement queue + retry with backoff |
| User data breach | Low | Critical | SOC2 compliance, encryption at rest |
| AI generates low-quality output | Medium | Medium | Quality scoring + regenerate option |
| WebSocket connection instability | Medium | Medium | Auto-reconnect + message buffering |
| Competitor launches similar feature | High | Medium | Speed to market, unique UX |""",

    "quality-reviewer": """## Quality Review Summary

**INVEST Compliance:** 9/10 — All stories are independent, valuable, and testable.
**Coverage:** 8/10 — Good coverage of core flows; could add more error scenarios.
**Consistency:** 9/10 — Personas used consistently, priorities are logical.

**Completeness Score: 8.5/10**

**Total Stories:** 12 | **Total Points:** 62 | **Sprints Needed:** ~2.1

### Top 3 Recommendations:
1. Add stories for password reset and session management
2. Include more edge cases for AI generation failures
3. Add a story for onboarding/tutorial flow""",
}

MOCK_PPT_OUTPUTS: dict[str, str] = {
    "audience-analyst": """**Audience:** Executive stakeholders and potential investors
**Knowledge Level:** Business-savvy, limited technical depth
**Tone:** Professional, confident, data-driven
**Key Messages:** 1) Massive market opportunity 2) Proven technology 3) Clear path to revenue
**Call to Action:** Schedule a product demo / Invest in Series A""",

    "narrative-architect": """**Narrative Arc:**
1. Hook: "Product teams waste 40% of their time on documentation"
2. Problem: Manual processes, inconsistent quality, slow iteration
3. Solution: AI-powered generation in minutes, not days
4. Evidence: Market data, feature comparison, architecture
5. Vision: The future of product development
6. CTA: Join the beta / Schedule demo""",

    "outline-planner": """**Slide Outline:**
1. Title Slide — Hook with tagline
2. The Problem — Pain points with statistics
3. Market Opportunity — Growth chart ($95B by 2026)
4. Our Solution — Feature overview
5. Feature Comparison — Table vs competitors
6. Architecture — Two-column tech stack
7. Target Users — Pie chart of segments
8. Before vs After — Comparison layout
9. Traction & Metrics — Key numbers
10. Next Steps — Call to action""",

    "content-writer": """**Slide content written for all 10 slides with concise bullets, action verbs, and max 12 words per point. Each slide has 3-5 key bullets with optional sub-points for depth.**""",

    "data-visualizer": """**Charts specified:**
- Slide 3: Bar chart — AI SaaS market growth 2022-2026
- Slide 7: Pie chart — User segment distribution
- Slide 5: Table — Feature comparison matrix
- Slide 8: Comparison — Before vs After layout""",

    "layout-designer": """**Layouts assigned:**
- Title slides: centered, navy #001f3f background
- Content slides: alternating navy/black backgrounds
- Charts: full-width with accent color #4FC3F7
- Tables: clean grid with header highlight
- All text: white #FFFFFF with grey #AAAAAA for secondary""",

    "speaker-notes-writer": """**Speaker notes written for all 10 slides with:**
- Opening hook for each slide
- 2-3 talking points to elaborate
- Key statistics to mention verbally
- Smooth transitions between slides""",

    "visual-asset-advisor": """**Visual suggestions:**
- Slide 1: Rocket icon, gradient background
- Slide 2: AlertTriangle icon, pain point illustrations
- Slide 3: TrendingUp icon with animated chart
- Slide 5: CheckCircle/XCircle for comparison
- Slide 6: Server + Monitor icons for architecture""",

    "slide-polisher": """**Quality Score: 9/10**
- Text density: All slides within limits
- Color consistency: Navy/black alternation maintained
- Flow: Logical problem→solution→evidence→CTA arc
- Impact: Strong opening hook, clear closing CTA
- Improvement: Add one more data point to slide 9""",

    "export-formatter": """{"slides":[{"title":"IdeaFlow AI Platform","subtitle":"Transform Ideas into Deliverables","content":[{"text":"AI-powered platform for product teams"},{"text":"From concept to structured output in minutes"}],"type":"title","layout":"title","colorScheme":{"background":"#001f3f","text":"#FFFFFF","accent":"#AAAAAA"},"speakerNotes":"Welcome everyone. Today I am excited to introduce IdeaFlow AI, a platform that transforms raw product ideas into polished deliverables in minutes."},{"title":"The Problem We Solve","content":[{"text":"Product teams waste 40% of time on documentation"},{"text":"Requirements are ambiguous, causing costly rework"},{"text":"Creating presentations takes hours of formatting"},{"text":"UI prototyping requires expensive tools and skills"}],"type":"text","layout":"content","colorScheme":{"background":"#000000","text":"#FFFFFF","accent":"#AAAAAA"},"speakerNotes":"Research shows product teams spend nearly half their time on documentation rather than building. The gap between idea and deliverable is where productivity dies."},{"title":"Market Opportunity","content":[{"text":"AI SaaS market projected to reach $95B by 2026"},{"text":"67% CAGR in AI-powered productivity tools"}],"type":"chart","layout":"chart","chartData":{"type":"bar","labels":["2022","2023","2024","2025","2026"],"values":[12,28,45,67,95],"title":"AI SaaS Market Growth ($B)"},"colorScheme":{"background":"#001f3f","text":"#FFFFFF","accent":"#4FC3F7"},"speakerNotes":"The AI SaaS market is experiencing explosive growth. We are positioned at the intersection of AI and productivity."},{"title":"Feature Comparison","content":[{"text":"IdeaFlow AI leads across all key capabilities"}],"type":"table","layout":"content","tableData":{"headers":["Feature","IdeaFlow AI","Competitor A","Competitor B"],"rows":[["User Stories","\\u2713 Full","Partial","\\u2717"],["PPT Generation","\\u2713 Full","\\u2717","Partial"],["Prototyping","\\u2713 Full","\\u2717","\\u2717"],["Real-time Streaming","\\u2713","\\u2717","\\u2713"],["Export to PPTX","\\u2713","\\u2717","\\u2717"]]},"colorScheme":{"background":"#000000","text":"#FFFFFF","accent":"#4FC3F7"},"speakerNotes":"When compared to competitors, IdeaFlow AI is the only platform offering full coverage across all deliverable types."},{"title":"Platform Architecture","content":[{"text":"Modern full-stack built for speed and reliability"}],"type":"two-column","layout":"two-column","columns":[["Next.js + TypeScript","Tailwind CSS + Motion","WebSocket streaming"],["FastAPI + Python","LangChain + Claude AI","SQLite / PostgreSQL"]],"colorScheme":{"background":"#001f3f","text":"#FFFFFF","accent":"#4FC3F7"},"speakerNotes":"Our architecture separates concerns cleanly. The frontend delivers a responsive experience while the backend orchestrates multiple AI agents."},{"title":"Target User Segments","content":[{"text":"Product Managers are our primary audience at 40%"}],"type":"chart","layout":"chart","chartData":{"type":"pie","labels":["Product Managers","Developers","Designers","Executives"],"values":[40,25,20,15],"title":"User Distribution"},"colorScheme":{"background":"#000000","text":"#FFFFFF","accent":"#4FC3F7"},"speakerNotes":"Our primary users are product managers who need to quickly generate structured deliverables."},{"title":"Before vs After","content":[{"text":"Dramatic reduction in time-to-deliverable"}],"type":"comparison","layout":"comparison","comparisonData":{"left":{"title":"Before","items":["4+ hours writing user stories","Full day creating presentations","Weeks for UI prototypes","Inconsistent documentation"]},"right":{"title":"After","items":["5 minutes with AI generation","Instant slide deck creation","Real-time prototype preview","Standardized professional output"]}},"colorScheme":{"background":"#001f3f","text":"#FFFFFF","accent":"#4FC3F7"},"speakerNotes":"The transformation is dramatic. Tasks that took hours now complete in minutes."},{"title":"Next Steps","content":[{"text":"Launch closed beta with 20 enterprise teams Q2 2025"},{"text":"Integrate with Jira, Confluence, and Notion"},{"text":"Add team collaboration with real-time co-editing"},{"text":"Expand AI models for domain-specific generation"}],"type":"text","layout":"content","colorScheme":{"background":"#001f3f","text":"#FFFFFF","accent":"#AAAAAA"},"speakerNotes":"Our roadmap focuses on enterprise adoption and integrations. We are targeting Q2 2025 for our closed beta."}]}""",
}

MOCK_PROTOTYPE_OUTPUTS: dict[str, str] = {
    "requirements-analyst": """## Functional Requirements

**Core Features:**
1. User authentication (login/register)
2. Chat-based AI interaction
3. Real-time content streaming
4. Preview panel with tabs (Stories/PPT/Prototype)
5. Chat history management
6. Content export (MD/PPTX/JSON)
7. Theme customization
8. Agent workflow visualization

**Pages Needed:** Login, Register, Dashboard, Settings, Profile
**Key Flows:** Auth → Dashboard → Chat → Generate → Preview → Export""",

    "information-architect": """## Sitemap

```
/ (redirect to /login or /dashboard)
├── /login
├── /register
├── /dashboard (main workspace)
│   ├── Sidebar (chat history)
│   ├── Chat Panel (conversation)
│   └── Preview Panel (generated content)
├── /settings
│   ├── Profile section
│   ├── Appearance section
│   └── API Configuration
├── /profile
└── /workflow (agent pipeline view)
```""",

    "navigation-designer": """## Navigation Design

**Type:** Sidebar (collapsible)
**Items:**
- Dashboard (layout-dashboard icon) → /dashboard
- Settings (settings icon) → /settings
- Profile (user icon) → /profile
- Workflows (rocket icon) → /workflow

**Default Route:** /dashboard
**Mobile:** Bottom tab bar with 4 items""",

    "wireframe-generator": """## Page Wireframes

### Login Page
- Header: Logo + tagline
- Form: Email input, Password input, Sign In button
- Link: "Create an account" → /register

### Dashboard Page
- Sidebar (280px): New Chat button, Chat list
- Chat Panel (flex-1): Message list, Input area
- Preview Panel (420px): Tabs, Content area

### Settings Page
- Profile card: Email (readonly), Change password button
- Appearance card: Theme picker (4 options)
- API card: API key input, Save button""",

    "component-designer": """## Component Specifications

**Button:** variants (primary/secondary/ghost), sizes (sm/md/lg), states (default/hover/loading/disabled)
**Input:** variants (outlined/filled), types (text/email/password), states (default/focus/error)
**Card:** variants (outlined/filled), with optional header and footer
**Sidebar:** collapsible (280px → 56px), with icon-only mini mode
**Tabs:** variants (pill/underline), with animated indicator""",

    "layout-engineer": """## Responsive Layouts

**Dashboard:** CSS Grid — sidebar | chat | preview
- Desktop: 280px | 1fr | 420px
- Tablet: 56px | 1fr | 0 (preview as overlay)
- Mobile: 0 | 1fr | 0 (sidebar as drawer)

**Auth Pages:** Flexbox centered card (max-width 400px)
**Settings:** Single column, max-width 600px, centered""",

    "interaction-designer": """## Interactions & Animations

- Page transitions: Fade in 300ms ease-out
- Sidebar collapse: Width 280px → 56px over 200ms
- Message appear: Slide up 12px + fade over 200ms
- Preview stream: Characters appear with 20ms stagger
- Button press: Scale 0.97 on press, spring back
- Modal open: Fade backdrop + scale from 0.95
- Tab switch: Cross-fade 150ms""",

    "state-manager": """## Screen States

**Dashboard:**
- Loading: Skeleton sidebar + empty chat with spinner
- Empty: Welcome message with suggested prompts
- Active: Full 3-panel layout with content
- Error: Error banner with retry, chat preserved

**Auth Pages:**
- Loading: Skeleton form placeholders
- Empty: Default empty form
- Error: Red borders + inline error messages
- Success: Redirect with success toast""",

    "accessibility-auditor": """## Accessibility Audit

- All inputs have associated labels (aria-label or htmlFor)
- Tab order follows visual layout (sidebar → chat → preview)
- Focus trapped in modals, restored on close
- Color contrast: 7:1 for body text (white on navy/black)
- Skip navigation link for keyboard users
- Live regions for streaming content (aria-live="polite")
- All icons have aria-label or aria-hidden=""",

    "react-code-generator": """## Generated React Components

All 5 pages generated as TypeScript + Tailwind components:
- LoginPage.tsx (form with validation)
- RegisterPage.tsx (form with confirm password)
- DashboardPage.tsx (3-panel layout)
- SettingsPage.tsx (cards with theme picker)
- ProfilePage.tsx (avatar + stats)

Each uses the enterprise-dark theme with responsive breakpoints.""",

    "page-renderer": """## HTML Preview Files

Standalone HTML files generated for iframe rendering:
- login.html (centered card, gradient background)
- register.html (centered card, gradient background)
- dashboard.html (full 3-panel layout)
- settings.html (single column cards)
- profile.html (avatar + info cards)

All include Tailwind CDN and Lucide icons.""",

    "prototype-assembler": """{"pages":[{"name":"Login","route":"/login","components":[{"type":"Header","props":{"variant":"minimal","ariaLabel":"IdeaFlow AI Login"},"children":[{"type":"Logo","props":{"size":"large"}},{"type":"Text","props":{"variant":"subtitle","content":"Transform ideas into deliverables"}}]},{"type":"Form","props":{"variant":"filled","ariaLabel":"Login form"},"children":[{"type":"Input","props":{"type":"email","placeholder":"Email address","required":true}},{"type":"Input","props":{"type":"password","placeholder":"Password","required":true}},{"type":"Button","props":{"label":"Sign In","variant":"primary","size":"large"}},{"type":"Link","props":{"label":"Create an account","route":"/register"}}]}],"states":{"loading":"Skeleton form","empty":"Default empty fields","error":"Red borders with messages","success":"Redirect to dashboard"}},{"name":"Register","route":"/register","components":[{"type":"Header","props":{"variant":"minimal"},"children":[{"type":"Logo","props":{"size":"medium"}},{"type":"Text","props":{"variant":"heading","content":"Create your account"}}]},{"type":"Form","props":{"variant":"filled"},"children":[{"type":"Input","props":{"type":"email","placeholder":"Email address","required":true}},{"type":"Input","props":{"type":"password","placeholder":"Password (8+ characters)","required":true}},{"type":"Input","props":{"type":"password","placeholder":"Confirm password","required":true}},{"type":"Button","props":{"label":"Create Account","variant":"primary","size":"large"}},{"type":"Link","props":{"label":"Already have an account? Sign in","route":"/login"}}]}],"states":{"loading":"Skeleton form","empty":"Default empty","error":"Inline validation errors","success":"Redirect to dashboard"}},{"name":"Dashboard","route":"/dashboard","components":[{"type":"Sidebar","props":{"width":"280px","collapsible":true},"children":[{"type":"Button","props":{"label":"New Chat","variant":"primary","icon":"plus"}},{"type":"List","props":{"items":"chatSessions","variant":"interactive"}}]},{"type":"ChatPanel","props":{"flex":"1"},"children":[{"type":"MessageList","props":{"variant":"streaming"}},{"type":"Input","props":{"placeholder":"Describe your idea...","variant":"filled","multiline":true}}]},{"type":"PreviewPanel","props":{"width":"420px","collapsible":true},"children":[{"type":"Tabs","props":{"items":["User Stories","PPT","Prototype"]}},{"type":"TabContent","props":{}}]}],"states":{"loading":"Skeleton panels","empty":"Welcome with prompts","error":"Error banner with retry","success":"Full layout with content"}},{"name":"Settings","route":"/settings","components":[{"type":"Header","props":{"variant":"page","title":"Settings"}},{"type":"Card","props":{"variant":"outlined","title":"Profile"},"children":[{"type":"Input","props":{"type":"email","label":"Email","disabled":true}},{"type":"Button","props":{"label":"Change Password","variant":"secondary"}}]},{"type":"Card","props":{"variant":"outlined","title":"Appearance"},"children":[{"type":"ThemePicker","props":{"options":["Midnight","Ocean","Forest","Light"]}}]},{"type":"Card","props":{"variant":"outlined","title":"API Configuration"},"children":[{"type":"Input","props":{"type":"password","label":"API Key","placeholder":"sk-ant-..."}},{"type":"Button","props":{"label":"Save","variant":"primary"}}]}],"states":{"loading":"Skeleton cards","empty":"Current values populated","error":"Toast on save failure","success":"Success toast"}},{"name":"Profile","route":"/profile","components":[{"type":"Header","props":{"variant":"page","title":"Profile"}},{"type":"Avatar","props":{"size":"xlarge","initials":"U"}},{"type":"Card","props":{"variant":"filled","title":"Account Information"},"children":[{"type":"Text","props":{"label":"Email","content":"user@example.com"}},{"type":"Text","props":{"label":"Member since","content":"January 2025"}},{"type":"Badge","props":{"label":"Free Plan","variant":"outlined"}}]},{"type":"Card","props":{"variant":"filled","title":"Usage Statistics"},"children":[{"type":"Text","props":{"content":"Chat sessions: 12"}},{"type":"Text","props":{"content":"Stories generated: 34"}},{"type":"Text","props":{"content":"Presentations created: 8"}}]}],"states":{"loading":"Skeleton avatar and cards","empty":"Default profile","error":"Error with retry","success":"Full profile displayed"}}],"navigation":{"type":"sidebar","items":[{"label":"Dashboard","route":"/dashboard","icon":"layout-dashboard"},{"label":"Settings","route":"/settings","icon":"settings"},{"label":"Profile","route":"/profile","icon":"user"}],"defaultRoute":"/dashboard"},"behavior":{"interactions":{"login-submit":"Validate and redirect to dashboard","new-chat":"Create session, focus input","send-message":"Stream AI response via WebSocket","collapse-preview":"Animate width to 0, expand chat","theme-change":"Apply CSS variables, persist to localStorage"},"animations":{"page-transition":"Fade in 300ms ease-out","sidebar-collapse":"Slide width 280px to 56px over 200ms","message-appear":"Slide up 12px with fade over 200ms","preview-stream":"Characters appear with 20ms stagger","button-press":"Scale 0.97 on press, spring back"}}}""",
}


MOCK_CUSTOM_OUTPUTS: dict[str, str] = {
    "market-research-agent": """## Market Research Report

**TAM:** $95B (Global AI SaaS market by 2026)
**SAM:** $12B (AI-powered productivity tools for product teams)
**SOM:** $480M (English-speaking mid-market companies)

| Competitor | Market Share | Pricing | Strengths | Weaknesses |
|-----------|-------------|---------|-----------|------------|
| Notion AI | 15% | $10/user/mo | Brand recognition, ecosystem | Generic AI, no specialized output |
| Coda AI | 8% | $12/user/mo | Flexible docs | Limited AI capabilities |
| ClickUp AI | 12% | $7/user/mo | PM integration | AI feels bolted on |
| Jasper | 10% | $49/mo | Marketing copy | No product management features |
| Linear | 6% | $8/user/mo | Developer-loved | No AI generation |

**Key Trends:** 1) AI-native tools replacing legacy suites 2) Vertical AI beating horizontal 3) Real-time collaboration as table stakes 4) API-first architectures 5) Usage-based pricing models

**Market Gaps:** Specialized AI for structured deliverables (stories, decks, prototypes) remains underserved.""",

    "swot-analyst": """## SWOT Analysis

### Strengths
- Multi-modal output (stories + PPT + prototype) in one platform
- Real-time streaming provides engaging UX
- Agent pipeline architecture enables quality through specialization
- Modern tech stack (Next.js + FastAPI) enables rapid iteration

### Weaknesses
- Single LLM dependency (Anthropic) creates vendor risk
- No offline capability
- Limited customization of output formats
- Early stage — no enterprise compliance certifications yet

### Opportunities
- Enterprise teams spending $50K+/year on manual documentation
- Integration with Jira/Confluence/Notion for seamless workflows
- Vertical expansion into specific industries (fintech, healthcare)
- Team collaboration features for real-time co-editing

### Threats
- Large incumbents (Microsoft Copilot, Google Duet) adding similar features
- Open-source alternatives gaining traction
- AI regulation could limit automated content generation
- Economic downturn reducing SaaS budgets

### Recommendations
1. **Leverage:** Double down on multi-modal output as key differentiator
2. **Address:** Add SOC2 compliance and multi-LLM support
3. **Capture:** Launch Jira integration within 90 days
4. **Counter:** Build moat through proprietary agent skills and templates""",

    "okr-generator": """## OKRs — Q3 2025

### Objective 1: Achieve Product-Market Fit
- KR1: Reach 500 weekly active users (from 50) by end of Q3
- KR2: Achieve 40% week-1 retention rate (from 15%)
- KR3: Net Promoter Score > 50 (from untracked)
- **Owner:** Product Team | **Timeline:** Q3 2025

### Objective 2: Deliver Enterprise-Ready Platform
- KR1: Complete SOC2 Type II certification by Sept 30
- KR2: Achieve 99.9% uptime SLA (from 99.5%)
- KR3: Reduce p95 API latency to <500ms (from 1.2s)
- **Owner:** Engineering Team | **Timeline:** Q3 2025

### Objective 3: Build Sustainable Revenue Engine
- KR1: Reach $50K MRR (from $5K)
- KR2: Achieve <3 month payback period on CAC
- KR3: Expand to 3 paid enterprise accounts
- **Owner:** Growth Team | **Timeline:** Q3 2025""",

    "roadmap-planner": """## Product Roadmap

### Phase 1: Foundation (Month 1-2)
| Feature | Priority | Effort | Dependency |
|---------|----------|--------|------------|
| User auth + JWT | P0 | M | None |
| Chat + WebSocket streaming | P0 | L | Auth |
| User Stories generation | P0 | L | Chat |
| PPT generation | P0 | L | Chat |
| Prototype generation | P1 | XL | Chat |
| Basic preview panel | P0 | M | Generation |

### Phase 2: Growth (Month 3-4)
| Feature | Priority | Effort | Dependency |
|---------|----------|--------|------------|
| Agent workflow UI | P1 | L | Phase 1 |
| Skill management | P1 | M | Agents |
| Export (PPTX, MD, JSON) | P1 | M | Generation |
| Team collaboration | P1 | XL | Auth |
| Jira integration | P2 | L | Stories |

### Phase 3: Scale (Month 5-6)
- Performance optimization and caching
- Enterprise SSO (SAML/OIDC)
- Usage analytics dashboard
- Custom agent builder (no-code)""",

    "prioritization-agent": """## Feature Prioritization (RICE Scoring)

| Feature | Reach | Impact | Confidence | Effort | RICE Score | MoSCoW |
|---------|-------|--------|-----------|--------|-----------|--------|
| AI User Stories | 500 | 3 | 80% | 2 | 600 | Must |
| PPT Generation | 400 | 2 | 80% | 2 | 320 | Must |
| Real-time Preview | 500 | 2 | 90% | 1.5 | 600 | Must |
| Agent Workflow | 200 | 2 | 70% | 3 | 93 | Should |
| Jira Integration | 300 | 2 | 60% | 2 | 180 | Should |
| Team Collab | 150 | 3 | 50% | 4 | 56 | Could |
| Custom Templates | 100 | 1 | 80% | 1 | 80 | Could |
| Mobile App | 50 | 1 | 40% | 5 | 4 | Won't |

**Recommendation:** Focus on AI generation + preview (highest RICE), then agent workflow for differentiation.""",

    "api-designer": """## API Specification

### Authentication
```
POST /api/auth/register  — Create account (email, password)
POST /api/auth/login     — Get JWT token (email, password)
POST /api/auth/refresh   — Refresh expired token
DELETE /api/auth/logout   — Invalidate token
```

### Chat Sessions
```
GET    /api/chats              — List user's chat sessions
POST   /api/chats              — Create new session
GET    /api/chats/{id}         — Get session with messages
DELETE /api/chats/{id}         — Delete session
```

### Generation
```
WebSocket /ws/chat?token={jwt} — Real-time streaming
  → Send: {type: "user_message", content, chat_session_id}
  ← Recv: {type: "stream", chunk, section}
  ← Recv: {type: "complete", data}
```

### Agents & Pipeline
```
GET  /api/agents/library       — List all available agents
GET  /api/agents/pipeline/{type} — Get pipeline config
POST /api/agents/skills        — Save agent skill
```

**Auth:** Bearer JWT (24h expiry) | **Rate Limit:** 100 req/min | **Pagination:** cursor-based""",

    "database-schema-agent": """## Database Schema

### users
| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PK, DEFAULT gen_random_uuid() |
| email | VARCHAR(255) | UNIQUE, NOT NULL |
| hashed_password | VARCHAR(255) | NOT NULL |
| created_at | TIMESTAMPTZ | DEFAULT NOW() |
| updated_at | TIMESTAMPTZ | DEFAULT NOW() |

### chat_sessions
| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PK |
| user_id | UUID | FK → users.id ON DELETE CASCADE |
| title | VARCHAR(100) | DEFAULT 'New Chat' |
| last_activity | TIMESTAMPTZ | DEFAULT NOW() |
| final_output | TEXT | NULLABLE |

### messages
| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PK |
| chat_session_id | UUID | FK → chat_sessions.id ON DELETE CASCADE |
| role | VARCHAR(20) | NOT NULL (user/assistant/system) |
| content | TEXT | NOT NULL |
| created_at | TIMESTAMPTZ | DEFAULT NOW() |

**Indexes:** users(email), chat_sessions(user_id, last_activity DESC), messages(chat_session_id, created_at)""",

    "security-auditor": """## Security Audit Report

### OWASP Assessment
| Vulnerability | Risk | Status | Mitigation |
|--------------|------|--------|------------|
| SQL Injection | High | ✅ Mitigated | SQLAlchemy ORM parameterized queries |
| XSS | Medium | ✅ Mitigated | React auto-escaping + CSP headers |
| Broken Auth | High | ✅ Mitigated | JWT with expiry + bcrypt hashing |
| CSRF | Low | ✅ Mitigated | SameSite cookies + token-based auth |
| Rate Limiting | Medium | ⚠️ Partial | Implement per-user rate limiting |

### Recommendations
1. **Critical:** Add rate limiting on auth endpoints (5 attempts/15min)
2. **High:** Implement refresh token rotation
3. **Medium:** Add Content-Security-Policy headers
4. **Low:** Enable HSTS with 1-year max-age""",

    "performance-optimizer": """## Performance Optimization Plan

### Quick Wins (This Sprint)
1. Enable gzip compression on API responses (-70% payload)
2. Add Redis caching for chat session list (TTL: 30s)
3. Implement WebSocket message batching (50ms window)
4. Lazy-load preview panel components
5. Add database connection pooling (pool_size=20)

### Frontend Targets
- LCP: < 2.0s (currently ~3.5s)
- FID: < 100ms (currently ~150ms)
- Bundle size: < 200KB gzipped (currently ~350KB)

### Backend Targets
- API p95: < 300ms (currently ~800ms)
- WebSocket first-token: < 1s (currently ~2.5s)
- DB query p95: < 50ms""",

    "test-case-generator": """## Test Cases

### Unit Tests — Authentication
- should hash password with bcrypt on registration
- should reject passwords shorter than 8 characters
- should return JWT token on successful login
- should return 401 for invalid credentials
- should lock account after 5 failed attempts

### Integration Tests — Chat
- should create chat session and return ID
- should persist messages in correct order
- should stream response chunks via WebSocket
- should generate title after first message

### E2E Tests — User Flow
1. Register → Login → Create Chat → Send Message → See Response → Download
2. Login → Open Workflow → Select Pipeline → Run → View Results
3. Login → Change Theme → Verify Persistence → Logout → Login → Theme Preserved""",

    "email-copywriter": """## Email Sequence

### Email 1: Welcome
**Subject:** Welcome to IdeaFlow AI — let's build something 🚀
**Preview:** Your first AI-generated deliverable is 30 seconds away

Hi {{first_name}},

You're in! IdeaFlow AI is ready to transform your ideas into structured deliverables.

Here's what you can create right now:
• User Stories — Complete backlogs with acceptance criteria
• Presentations — Slide decks with charts and speaker notes
• Prototypes — UI definitions with navigation and states

**[Create Your First Deliverable →]**

### Email 2: Getting Started (Day 2)
**Subject:** 3 prompts that produce amazing results
**Preview:** Copy-paste these to see IdeaFlow AI at its best""",

    "release-notes-writer": """## v1.2.0 — May 2025

### 🚀 New Features
- **Agent Workflow Pipeline** — Visual agent execution with real-time progress
- **Drag & Drop Reordering** — Customize agent sequence before running
- **20 Custom Agents** — Market research, API design, security audit, and more

### ✨ Improvements
- Preview panel now auto-opens when content is generated
- Pipeline type switching with instant agent list update
- Better error handling for WebSocket disconnections

### 🐛 Bug Fixes
- Fixed nested button hydration error in AgentNode
- Fixed preview not showing after pipeline completion
- Fixed pipeline messages not routing to workflow state""",

    "documentation-agent": """## README.md

# IdeaFlow AI 🚀

> Transform product ideas into structured deliverables using AI agent pipelines.

## Quick Start
```bash
# Backend
cd backend && pip install -r requirements.txt
python -m uvicorn app.main:app --reload

# Frontend
cd frontend && npm install
npm run dev
```

## Features
- 🤖 54 specialized AI agents across 4 categories
- 📝 User story generation with personas and acceptance criteria
- 📊 Presentation generation with charts and speaker notes
- 🎨 Prototype generation with component hierarchy
- ⚡ Real-time WebSocket streaming
- 🔄 Drag-and-drop agent pipeline customization""",

    "localization-agent": """## Translation Keys (en-US)

```json
{
  "auth": {
    "login": { "title": "Sign In", "submit": "Sign In", "register_link": "Create an account" },
    "register": { "title": "Create Account", "submit": "Create Account" }
  },
  "dashboard": {
    "sidebar": { "new_chat": "New Chat", "search": "Search chats...", "logout": "Log out" },
    "chat": { "placeholder": "Describe your idea...", "send": "Send" },
    "preview": { "tab_stories": "User Stories", "tab_ppt": "PPT", "tab_prototype": "Prototype" }
  },
  "workflow": {
    "title": "Agent Workflow",
    "run": "Run Workflow",
    "cancel": "Cancel",
    "view_results": "View Results",
    "add_agent": "Add Agent"
  }
}
```""",

    "color-palette-generator": """## Color System

### Primary (Navy)
- 50: #E8EDF5 | 100: #C5D1E8 | 200: #9FB3D9
- 500: #001F3F (primary) | 700: #001529 | 900: #000B14

### Accent (Cyan)
- 400: #4FC3F7 (accent) | 500: #29B6F6 | 600: #039BE5

### Semantic
- Success: #4CAF50 | Warning: #FFA726 | Error: #EF5350 | Info: #42A5F5

### Neutrals
- 50: #FAFAFA | 100: #F5F5F5 | 300: #E0E0E0
- 500: #9E9E9E | 700: #616161 | 900: #212121

### Dark Mode
```css
:root { --bg: #000000; --surface: #0a0a0a; --border: rgba(255,255,255,0.1); --text: #FFFFFF; --text-muted: #AAAAAA; }
```

All combinations pass WCAG AA (4.5:1 contrast ratio).""",

    "microcopy-writer": """## UI Microcopy

### Buttons
- Primary: "Create", "Generate", "Run Workflow"
- Secondary: "Cancel", "Back", "Skip for now"
- Destructive: "Delete chat", "Remove agent"

### Empty States
- Chat: "What would you like to create today?" + [Suggested prompts]
- Preview: "Generated content will appear here"
- Workflow: "Select a pipeline and click Run Workflow"

### Error Messages
- Network: "Connection lost. Retrying..." + [Reconnect]
- Auth: "Session expired. Please sign in again."
- Generation: "Something went wrong. Try again?" + [Retry]

### Loading States
- "Analyzing your request...", "Generating content...", "Almost there..."

### Success
- "✅ Generated!", "Saved successfully", "Copied to clipboard" """,

    "competitive-ui-analyst": """## Competitive UI Analysis

| Product | Navigation | AI Interaction | Output Display | Unique Pattern |
|---------|-----------|---------------|----------------|----------------|
| ChatGPT | Sidebar + chat | Conversational | Inline markdown | Artifacts panel |
| Claude | Sidebar + chat | Conversational | Artifacts side panel | Projects context |
| Notion AI | Inline + slash | Block-based | In-document | AI blocks |
| Gamma | Wizard flow | Form-based | Full preview | Template gallery |

### Differentiation Opportunities
1. Agent pipeline visualization (no competitor shows this)
2. Multi-output in single session (stories + PPT + prototype)
3. Drag-and-drop agent customization
4. Real-time streaming with progress indicators""",

    "kpi-dashboard-designer": """## KPI Dashboard Design

### North Star: Weekly Active Generators (WAG)
Users who generate at least 1 deliverable per week.

### Supporting Metrics
| Metric | Target | Chart Type | Alert |
|--------|--------|-----------|-------|
| DAU/MAU Ratio | >30% | Line (30d) | <20% |
| Generations/User/Week | >3 | Bar (weekly) | <1 |
| Preview Open Rate | >70% | Gauge | <50% |
| Export Download Rate | >40% | Funnel | <25% |
| p95 Generation Time | <30s | Line (hourly) | >45s |
| Error Rate | <1% | Line (daily) | >3% |

### Layout: 2x3 grid of metric cards with sparklines, expandable to full charts""",

    "data-flow-mapper": """## Data Flow Map

```
[User Input] → [WebSocket] → [Agent Orchestrator] → [Claude API]
                                    ↓
                            [Stream Chunks]
                                    ↓
                    [Frontend State] → [Preview Panel]
                                    ↓
                    [Database] → [Chat History]
```

### Data Sources
- User input (WebSocket messages)
- Claude API responses (streaming)
- SQLite database (persistence)
- LocalStorage (theme, token)

### Pipelines
1. **Chat Flow:** Input → WS → Backend → Claude → Stream → DB + Frontend
2. **Pipeline Flow:** Run → WS → Mock/Claude per agent → Status updates → Final output → Preview
3. **Auth Flow:** Credentials → JWT → LocalStorage → WS query param""",

    "report-generator": """## Executive Report — IdeaFlow AI Platform

### Executive Summary
IdeaFlow AI has successfully implemented a full agent pipeline system with 54 specialized agents across 4 categories. The platform now supports end-to-end generation of user stories, presentations, and prototypes with real-time streaming and visual workflow management.

### Key Metrics
| Metric | Value | Trend |
|--------|-------|-------|
| Total Agents | 54 | ↑ from 34 |
| Pipeline Types | 4 | ↑ from 3 |
| Mock Mode Coverage | 100% | → stable |
| TypeScript Errors | 0 | → stable |

### Recommendations
1. **High Priority:** Enable Claude API for production testing
2. **Medium:** Add agent output caching to reduce API costs
3. **Low:** Implement agent performance benchmarking""",
}


def _get_mock_outputs(pipeline_type: str) -> dict[str, str]:
    """Get mock outputs for a given pipeline type."""
    if pipeline_type == "user_stories":
        return MOCK_USER_STORY_OUTPUTS
    elif pipeline_type == "ppt":
        return MOCK_PPT_OUTPUTS
    elif pipeline_type == "validate_pitch":
        from app.agents.mock_outputs_new import MOCK_VALIDATE_PITCH_OUTPUTS
        return MOCK_VALIDATE_PITCH_OUTPUTS
    elif pipeline_type == "prototype":
        return MOCK_PROTOTYPE_OUTPUTS
    elif pipeline_type == "app_builder":
        from app.agents.mock_outputs_new import MOCK_APP_BUILDER_OUTPUTS
        return MOCK_APP_BUILDER_OUTPUTS
    elif pipeline_type == "reverse_engineer":
        from app.agents.mock_outputs_new import MOCK_REVERSE_ENGINEER_OUTPUTS
        return MOCK_REVERSE_ENGINEER_OUTPUTS
    elif pipeline_type == "custom":
        return MOCK_CUSTOM_OUTPUTS
    return {}


async def mock_pipeline_execute(
    user_message: str, pipeline_type: str, skills: dict[str, str] | None = None, agent_ids: list[str] | None = None
) -> AsyncGenerator[dict, None]:
    """Simulate pipeline execution with realistic delays and per-agent outputs.

    Yields the same message format as PipelineExecutor.execute() so the
    WebSocket handler can use it as a drop-in replacement.
    If agent_ids is provided, uses that custom agent list instead of defaults.
    """
    if agent_ids:
        # Use custom agent list — look up each agent by ID
        from app.agents.registry import get_agent_by_id
        agents = [a for aid in agent_ids if (a := get_agent_by_id(aid)) is not None]
    else:
        agents = get_pipeline_agents(pipeline_type)

    mock_outputs = _get_mock_outputs(pipeline_type)
    total_start = time.time()

    # Pipeline start
    yield {
        "type": "pipeline_start",
        "data": {
            "pipeline_type": pipeline_type,
            "agent_count": len(agents),
            "agents": [
                {"id": a.id, "name": a.name, "role": a.role, "icon": a.icon, "order": a.order}
                for a in agents
            ],
        },
    }

    results = []

    for i, agent_def in enumerate(agents):
        agent_start = time.time()

        # Agent start
        yield {
            "type": "agent_start",
            "data": {
                "agent_id": agent_def.id,
                "name": agent_def.name,
                "role": agent_def.role,
                "icon": agent_def.icon,
                "index": i,
                "total": len(agents),
            },
        }

        # Thinking phase
        yield {
            "type": "agent_thinking",
            "data": {
                "agent_id": agent_def.id,
                "thinking": f"Analyzing context from {i} previous agents...",
            },
        }
        await asyncio.sleep(random.uniform(0.5, 1.2))

        # Get mock output for this agent
        output = mock_outputs.get(agent_def.id, "")
        if not output:
            # Check custom outputs as fallback (user may have added custom agents to any pipeline)
            output = MOCK_CUSTOM_OUTPUTS.get(agent_def.id, f"[{agent_def.name}] Processing complete for: {user_message[:50]}...")

        # Stream output in chunks
        chunk_size = random.randint(15, 40)
        pos = 0
        while pos < len(output):
            chunk = output[pos:pos + chunk_size]
            yield {
                "type": "agent_chunk",
                "data": {
                    "agent_id": agent_def.id,
                    "chunk": chunk,
                },
            }
            pos += chunk_size
            await asyncio.sleep(random.uniform(0.02, 0.08))

        # Agent complete
        duration = time.time() - agent_start
        results.append({"agent_id": agent_def.id, "output": output, "duration": duration})

        yield {
            "type": "agent_complete",
            "data": {
                "agent_id": agent_def.id,
                "name": agent_def.name,
                "duration": round(duration, 2),
                "output_length": len(output),
                "index": i,
                "total": len(agents),
            },
        }

        # Small pause between agents
        await asyncio.sleep(random.uniform(0.3, 0.7))

    # Pipeline complete
    total_duration = time.time() - total_start

    # For the final output, use the appropriate rich content for preview
    if pipeline_type == "user_stories":
        # Combine the key story outputs into full markdown for the preview
        from app.agents.mock import MOCK_USER_STORIES
        final_output = MOCK_USER_STORIES
    elif pipeline_type == "ppt":
        # Use the export-formatter's JSON output for PPT preview
        final_output = mock_outputs.get("export-formatter", results[-1]["output"] if results else "")
    elif pipeline_type == "validate_pitch":
        # Use the pitch-compiler's JSON output for PPT preview
        final_output = mock_outputs.get("pitch-compiler", results[-1]["output"] if results else "")
    elif pipeline_type == "prototype":
        # Use the prototype-assembler's JSON output for prototype preview
        final_output = mock_outputs.get("prototype-assembler", results[-1]["output"] if results else "")
    elif pipeline_type == "app_builder":
        # Use the app-assembler's markdown output
        final_output = mock_outputs.get("app-assembler", results[-1]["output"] if results else "")
    elif pipeline_type == "reverse_engineer":
        # Use the documentation-generator's markdown output
        final_output = mock_outputs.get("documentation-generator", results[-1]["output"] if results else "")
    else:
        final_output = results[-1]["output"] if results else ""

    yield {
        "type": "pipeline_complete",
        "data": {
            "pipeline_type": pipeline_type,
            "total_duration": round(total_duration, 2),
            "agents_completed": len(results),
            "agents_total": len(agents),
            "final_output": final_output,
        },
    }
