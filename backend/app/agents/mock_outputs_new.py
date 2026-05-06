"""Mock outputs for new pipeline types: validate_pitch, app_builder, reverse_engineer."""

# ============================================================
# VALIDATE & PITCH — Mock outputs per agent
# ============================================================

MOCK_VALIDATE_PITCH_OUTPUTS: dict[str, str] = {
    "idea-validator": """## Idea Validation Report

### Feasibility: 8/10
The concept is technically feasible with current LLM and web technologies. Multi-agent orchestration is proven (LangChain, CrewAI). Real-time streaming via WebSocket is standard.

### Uniqueness: 7/10
**Existing competitors:**
- Notion AI (general writing, not structured deliverables)
- Gamma.app (presentations only)
- Linear (project management, not generation)

**Differentiator:** End-to-end pipeline from idea → structured output (stories, decks, prototypes) with visible agent reasoning.

### Market Fit: 9/10
Strong demand signal:
- 78% of PMs spend >5hrs/week on documentation (ProductPlan 2024)
- $4.2B TAM for AI productivity tools (Gartner)
- Enterprise buyers actively seeking "AI copilots" for product teams

### Top 3 Risks
1. **Quality consistency** — LLM outputs vary; need guardrails
2. **Enterprise adoption** — Security/compliance requirements are high
3. **Pricing pressure** — Race to bottom in AI tools market

### Verdict: ✅ GO
Strong market fit, defensible differentiation through multi-agent orchestration. Recommend focusing on enterprise segment with SOC2 compliance from day one.""",

    "market-researcher": """## Market Research Report

### Market Sizing

| Metric | Value | Source |
|--------|-------|--------|
| **TAM** | $12.4B | Global AI productivity software (2025) |
| **SAM** | $3.1B | AI tools for product/engineering teams |
| **SOM** | $45M | Enterprise teams (500+ employees) in US/EU, Year 2 |

### Competitive Landscape

| Competitor | Strength | Weakness | Pricing |
|-----------|----------|----------|---------|
| Notion AI | Brand, ecosystem | Generic output, no pipelines | $10/user/mo |
| Gamma.app | Beautiful decks | Only presentations | $15/user/mo |
| Coda AI | Flexible docs | Complex UX, learning curve | $12/user/mo |
| Miro AI | Visual collaboration | Not structured deliverables | $16/user/mo |
| ChatGPT/Claude | Raw power | No workflow, no preview | $20/user/mo |

### Market Trends (Tailwinds)
1. **Agentic AI adoption** — 67% of enterprises experimenting (McKinsey 2025)
2. **Documentation fatigue** — Teams want "generation" not "writing"
3. **Multi-modal outputs** — Demand for structured artifacts, not just text

### Pricing Benchmark
- Individual: $15-25/month
- Team: $20-40/user/month
- Enterprise: $50-100/user/month (with SSO, compliance, custom agents)""",

    "value-prop-designer": """## Value Proposition

### One-Liner
> "Turn any idea into production-ready deliverables in 60 seconds with AI agents that think like your best team members."

### Value Proposition Canvas

| Jobs to be Done | Pains | Gains |
|----------------|-------|-------|
| Write user stories from ideas | Manual writing takes hours | Sprint-ready backlog in 1 minute |
| Create investor pitch decks | Design + content takes days | Investor-ready deck in 2 minutes |
| Build UI prototypes | Figma iterations take weeks | Clickable prototype instantly |
| Document architecture | Nobody wants to write docs | Living documentation auto-generated |

### Positioning Statement
> For **product and engineering teams** who need to **turn ideas into structured deliverables fast**, **IdeaFlow AI** is an **agentic delivery studio** that **generates production-ready user stories, pitch decks, and prototypes using specialist AI agents**. Unlike **ChatGPT or Notion AI**, we deliver **structured, multi-format outputs through transparent agent pipelines you can customize**.

### Elevator Pitch (30 seconds)
"Every product team wastes 40% of their time on documentation instead of building. IdeaFlow AI fixes this with specialist AI agents that generate user stories, pitch decks, and prototypes from a single idea — in under a minute. Our agents think like your best PM, designer, and architect combined. Teams ship 3x faster."
""",

    "business-model-architect": """## Business Model

### Revenue Model: Usage-Based SaaS + Seat License

**Pricing Tiers:**

| Tier | Price | Includes |
|------|-------|----------|
| **Starter** | $19/mo | 50 pipeline runs, 3 workflows, 1 user |
| **Pro** | $49/user/mo | Unlimited runs, all workflows, custom agents |
| **Enterprise** | $99/user/mo | SSO, audit logs, dedicated support, SLA |

### Unit Economics

| Metric | Value |
|--------|-------|
| **CAC** (blended) | $120 |
| **LTV** (Pro, 18mo avg) | $882 |
| **LTV:CAC Ratio** | 7.4x |
| **Payback Period** | 2.4 months |
| **Gross Margin** | 82% (AI costs ~18% of revenue) |

### Go-to-Market (First 3 Channels)
1. **Product Hunt launch** → 2,000 signups (proven for dev tools)
2. **Content marketing** → SEO for "AI user story generator", "AI pitch deck"
3. **PLG viral loop** → Shared outputs include "Made with IdeaFlow" watermark

### Milestones
- **Seed readiness:** 500 active users, $10K MRR, 3 enterprise pilots
- **Series A readiness:** 5,000 users, $100K MRR, 20% enterprise mix, <5% churn""",

    "pitch-narrative-writer": """## Pitch Narrative Arc (10 Slides)

### Slide 1: Hook / Problem
**Key Message:** Product teams waste 40% of their time writing docs instead of building.
- The average PM writes 15+ user stories per sprint manually
- Pitch decks take 2-3 days to create
- Prototypes require weeks of designer time

### Slide 2: Market Opportunity
**Key Message:** $12.4B market growing 34% YoY — timing is perfect.
- AI productivity tools are the fastest-growing SaaS category
- 67% of enterprises are actively adopting agentic AI
- Documentation automation is the #1 requested feature

### Slide 3: Solution
**Key Message:** IdeaFlow AI turns ideas into deliverables in 60 seconds.
- Describe your idea in plain English
- Specialist AI agents collaborate like a real team
- Get structured outputs: user stories, decks, prototypes

### Slide 4: How It Works
**Key Message:** Transparent agent pipelines you can see and customize.
- Pick a workflow (6 options)
- Watch 10-12 specialist agents work in sequence
- Each agent builds on the previous one's output
- Preview results in real-time

### Slide 5: Traction
**Key Message:** Early signals validate strong product-market fit.
- 500+ beta users in 3 months
- 4.7/5 satisfaction score
- 3x weekly usage per active user
- 2 enterprise pilots signed (Fortune 500)

### Slide 6: Business Model
**Key Message:** High-margin SaaS with strong unit economics.
- $49/user/month (Pro tier)
- 82% gross margin
- 7.4x LTV:CAC ratio
- Usage-based pricing aligns with value delivered

### Slide 7: Competitive Advantage
**Key Message:** Multi-agent orchestration is our moat.
- Not a chatbot — structured, multi-format outputs
- Transparent reasoning (see what each agent thinks)
- Customizable pipelines (add/remove/reorder agents)
- Enterprise-grade (SOC2, SSO, audit logs)

### Slide 8: Team
**Key Message:** Built by people who lived the problem.
- CEO: Ex-PM at Atlassian (built Jira workflows)
- CTO: Ex-ML lead at Anthropic (built agent systems)
- Head of Design: Ex-Figma (built prototyping tools)

### Slide 9: Financial Projections
**Key Message:** Path to $10M ARR in 24 months.
- Year 1: $1.2M ARR (2,000 paid users)
- Year 2: $5.8M ARR (8,000 users + enterprise)
- Year 3: $14M ARR (20,000 users, 30% enterprise)

### Slide 10: The Ask
**Key Message:** Raising $3M Seed to capture the market.
- $3M at $15M pre-money valuation
- 18-month runway
- Use of funds: 60% engineering, 25% GTM, 15% ops
- Target: 5,000 users and $100K MRR by month 18""",

    "pitch-slide-writer": """## Slide Content (Detailed)

### Slide 1: The Problem
**Title:** Documentation is killing your team's velocity
**Subtitle:** Product teams spend 40% of time writing, not building
**Bullets:**
- 15+ user stories written manually per sprint
- 2-3 days to create a single pitch deck
- Weeks of iteration for UI prototypes
- $180K/year wasted per team on documentation overhead
**Speaker Notes:** Open with the pain. Every PM in the room has felt this. The average product team of 8 people wastes the equivalent of 3 full-time salaries on documentation that could be automated.

### Slide 2: The Market
**Title:** $12.4B opportunity growing 34% YoY
**Subtitle:** AI productivity tools are the fastest-growing SaaS category
**Bullets:**
- TAM: $12.4B (AI productivity software)
- SAM: $3.1B (product/engineering teams)
- 67% of enterprises adopting agentic AI in 2025
- Documentation automation: #1 requested feature
**Speaker Notes:** This isn't a niche. Every company with a product team needs this. The market is growing because AI capabilities just crossed the quality threshold for enterprise adoption.

### Slide 3: Our Solution
**Title:** IdeaFlow AI — From idea to deliverable in 60 seconds
**Subtitle:** Specialist AI agents that think like your best team members
**Bullets:**
- Describe any idea in plain English
- 10-12 specialist agents collaborate in sequence
- Structured outputs: user stories, pitch decks, prototypes
- Customize agents and pipelines to your workflow
**Speaker Notes:** This is not ChatGPT with a wrapper. Each agent has a specific role — domain analyst, story writer, QA lead — and they pass context to each other like a real team would.""",

    "pitch-data-viz": """## Chart Data

### Market Size (Funnel Chart)
```json
{"type": "bar", "title": "Market Opportunity ($B)", "labels": ["TAM", "SAM", "SOM (Y2)"], "values": [12.4, 3.1, 0.045]}
```

### Revenue Projection (Line Chart)
```json
{"type": "line", "title": "ARR Projection ($M)", "labels": ["Q1 Y1", "Q2 Y1", "Q3 Y1", "Q4 Y1", "Q1 Y2", "Q2 Y2", "Q3 Y2", "Q4 Y2"], "values": [0.1, 0.3, 0.6, 1.2, 2.1, 3.4, 4.8, 5.8]}
```

### Competitive Comparison (Table)
| Feature | IdeaFlow | Notion AI | Gamma | ChatGPT |
|---------|----------|-----------|-------|---------|
| Multi-agent pipeline | ✅ | ❌ | ❌ | ❌ |
| Structured outputs | ✅ | ❌ | Partial | ❌ |
| Real-time preview | ✅ | ❌ | ✅ | ❌ |
| Custom workflows | ✅ | ❌ | ❌ | ❌ |
| Enterprise (SOC2) | ✅ | ✅ | ❌ | ✅ |

### Unit Economics (Bar Chart)
```json
{"type": "bar", "title": "Unit Economics", "labels": ["CAC", "Monthly Revenue", "LTV (18mo)"], "values": [120, 49, 882]}
```""",

    "pitch-design-advisor": """## Design Recommendations

### Color Palette
- **Primary:** #3B82F6 (Blue — trust, technology)
- **Secondary:** #8B5CF6 (Purple — innovation, premium)
- **Accent:** #10B981 (Green — growth, success)
- **Background:** #0F172A (Dark navy — professional, modern)
- **Text:** #F8FAFC (Near-white — high contrast)

### Typography
- **Headings:** Inter Bold (clean, modern, tech-forward)
- **Body:** Inter Regular (highly readable at all sizes)
- **Data:** JetBrains Mono (for metrics and code)

### Layout Style
Minimal with generous whitespace. Data-forward where metrics exist. Dark background with glowing accent elements for premium feel.

### Key Visual Elements
- Gradient orbs as background accents (subtle, not distracting)
- Agent icons with status indicators (thinking, done)
- Live preview mockups showing the product in action
- Metric cards with large numbers and trend arrows""",

    "pitch-compiler": """{"slides":[{"title":"Documentation is killing your team's velocity","subtitle":"Product teams spend 40% of time writing, not building","content":[{"text":"15+ user stories written manually per sprint","subPoints":[]},{"text":"2-3 days to create a single pitch deck","subPoints":[]},{"text":"Weeks of iteration for UI prototypes","subPoints":[]},{"text":"$180K/year wasted per team on documentation","subPoints":[]}],"type":"text","layout":"centered","colorScheme":{"background":"#0F172A","text":"#F8FAFC","accent":"#3B82F6"},"speakerNotes":"Open with the pain every PM feels."},{"title":"$12.4B opportunity growing 34% YoY","subtitle":"AI productivity tools are the fastest-growing SaaS category","content":[{"text":"TAM: $12.4B global AI productivity","subPoints":[]},{"text":"SAM: $3.1B product/engineering teams","subPoints":[]},{"text":"67% of enterprises adopting agentic AI","subPoints":[]}],"type":"chart","layout":"split","colorScheme":{"background":"#0F172A","text":"#F8FAFC","accent":"#8B5CF6"},"speakerNotes":"The market timing is perfect.","chartData":{"type":"bar","labels":["TAM","SAM","SOM"],"values":[12.4,3.1,0.045],"title":"Market Size ($B)"}},{"title":"IdeaFlow AI — Idea to deliverable in 60 seconds","subtitle":"Specialist AI agents that think like your best team members","content":[{"text":"Describe any idea in plain English","subPoints":[]},{"text":"10-12 specialist agents collaborate","subPoints":[]},{"text":"Structured outputs: stories, decks, prototypes","subPoints":[]},{"text":"Customize pipelines to your workflow","subPoints":[]}],"type":"text","layout":"centered","colorScheme":{"background":"#0F172A","text":"#F8FAFC","accent":"#10B981"},"speakerNotes":"This is not a chatbot. It is a team of specialists."},{"title":"Path to $10M ARR in 24 months","subtitle":"High-margin SaaS with strong unit economics","content":[{"text":"$49/user/month Pro tier","subPoints":[]},{"text":"82% gross margin","subPoints":[]},{"text":"7.4x LTV:CAC ratio","subPoints":[]}],"type":"chart","layout":"split","colorScheme":{"background":"#0F172A","text":"#F8FAFC","accent":"#3B82F6"},"speakerNotes":"The economics work at scale.","chartData":{"type":"line","labels":["Q1","Q2","Q3","Q4","Q5","Q6","Q7","Q8"],"values":[0.1,0.3,0.6,1.2,2.1,3.4,4.8,5.8],"title":"ARR Projection ($M)"}},{"title":"Raising $3M to capture the market","subtitle":"18-month runway to 5,000 users and $100K MRR","content":[{"text":"60% Engineering — build the platform","subPoints":[]},{"text":"25% Go-to-Market — acquire users","subPoints":[]},{"text":"15% Operations — compliance, support","subPoints":[]}],"type":"text","layout":"centered","colorScheme":{"background":"#0F172A","text":"#F8FAFC","accent":"#8B5CF6"},"speakerNotes":"Clear use of funds with measurable milestones."}]}""",

    "pitch-quality-reviewer": """## Pitch Deck Review (VC Perspective)

### Scores
| Dimension | Score | Notes |
|-----------|-------|-------|
| Clarity | 9/10 | Problem and solution are crystal clear |
| Market Story | 8/10 | Good sizing, could use more bottom-up validation |
| Credibility | 7/10 | Early traction is promising, need more data points |
| Design | 9/10 | Professional, modern, consistent |
| Ask | 8/10 | Reasonable valuation, clear milestones |

### Overall Score: 8.2/10

### Top 3 Strengths
1. **Clear problem-solution fit** — Every PM immediately understands the pain
2. **Strong unit economics** — 7.4x LTV:CAC is excellent for seed stage
3. **Defensible moat** — Multi-agent orchestration is hard to replicate

### Top 3 Improvements
1. **Add customer quotes** — Social proof from beta users would strengthen credibility
2. **Show the product** — Include a 30-second demo video or GIF
3. **Bottom-up market sizing** — Show how you calculated SOM from actual customer segments

### Verdict
> "This is a fundable deck. The team understands the market, the product is differentiated, and the economics work. I'd take the meeting."
""",
}


# ============================================================
# APP BUILDER — Mock outputs per agent
# ============================================================

MOCK_APP_BUILDER_OUTPUTS: dict[str, str] = {
    "material-analyzer": """## Requirements Extraction

### App Purpose
A project management tool for small teams that combines task tracking, time logging, and team communication in one place.

### Core Features
1. **Task Board** — Kanban-style with drag-and-drop, labels, due dates
2. **Time Tracking** — Start/stop timer per task, weekly reports
3. **Team Chat** — Real-time messaging per project channel
4. **File Sharing** — Attach files to tasks, preview in-app
5. **Dashboard** — Overview of all projects, deadlines, team workload
6. **Notifications** — Email + in-app for assignments, mentions, deadlines
7. **User Roles** — Admin, Manager, Member with granular permissions
8. **Integrations** — Slack webhook, GitHub PR linking

### User Roles
- **Admin** — Full access, billing, team management
- **Manager** — Create projects, assign tasks, view reports
- **Member** — View/update assigned tasks, log time, chat

### Data Model
- Users, Teams, Projects, Tasks, TimeEntries, Messages, Files, Notifications

### Constraints
- Must work on mobile (responsive)
- Real-time updates (WebSocket)
- Max 50 team members per workspace""",

    "tech-stack-advisor": """## Recommended Tech Stack

### Frontend
- **Framework:** Next.js 14 (App Router)
- **UI Library:** Tailwind CSS + shadcn/ui
- **State:** Zustand (lightweight, no boilerplate)
- **Real-time:** Socket.io client
- **Forms:** React Hook Form + Zod validation

### Backend
- **Language:** TypeScript (Node.js)
- **Framework:** Express.js + tRPC
- **ORM:** Prisma (type-safe, great DX)
- **Real-time:** Socket.io server
- **Auth:** NextAuth.js (OAuth + credentials)

### Database
- **Primary:** PostgreSQL (relational data, ACID)
- **Cache:** Redis (sessions, real-time presence)
- **File Storage:** AWS S3 / Cloudflare R2

### Hosting
- **Frontend:** Vercel (zero-config Next.js)
- **Backend:** Railway or Render (easy Node.js hosting)
- **Database:** Supabase or Neon (managed Postgres)

### Rationale
This stack optimizes for developer velocity (TypeScript end-to-end), type safety (Prisma + tRPC), and deployment simplicity (Vercel + Railway). It scales to 10K users without architecture changes.""",

    "database-designer": """## Database Schema

### Users
```sql
CREATE TABLE users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email VARCHAR(255) UNIQUE NOT NULL,
  name VARCHAR(100) NOT NULL,
  avatar_url TEXT,
  password_hash TEXT NOT NULL,
  role ENUM('admin', 'manager', 'member') DEFAULT 'member',
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);
```

### Projects
```sql
CREATE TABLE projects (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name VARCHAR(200) NOT NULL,
  description TEXT,
  team_id UUID REFERENCES teams(id),
  status ENUM('active', 'archived', 'completed') DEFAULT 'active',
  created_by UUID REFERENCES users(id),
  created_at TIMESTAMP DEFAULT NOW()
);
```

### Tasks
```sql
CREATE TABLE tasks (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  title VARCHAR(300) NOT NULL,
  description TEXT,
  project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
  assignee_id UUID REFERENCES users(id),
  status ENUM('backlog', 'todo', 'in_progress', 'review', 'done') DEFAULT 'backlog',
  priority ENUM('low', 'medium', 'high', 'urgent') DEFAULT 'medium',
  due_date DATE,
  estimated_hours DECIMAL(5,2),
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_tasks_project ON tasks(project_id);
CREATE INDEX idx_tasks_assignee ON tasks(assignee_id);
CREATE INDEX idx_tasks_status ON tasks(status);
```

### Time Entries
```sql
CREATE TABLE time_entries (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  task_id UUID REFERENCES tasks(id) ON DELETE CASCADE,
  user_id UUID REFERENCES users(id),
  started_at TIMESTAMP NOT NULL,
  ended_at TIMESTAMP,
  duration_minutes INTEGER,
  note TEXT
);
```""",

    "api-designer": """## API Design (REST)

### Authentication
| Method | Path | Description | Auth |
|--------|------|-------------|------|
| POST | /api/auth/register | Create account | No |
| POST | /api/auth/login | Get JWT token | No |
| GET | /api/auth/me | Current user | Yes |

### Projects
| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | /api/projects | List user's projects | Yes |
| POST | /api/projects | Create project | Yes (Manager+) |
| GET | /api/projects/:id | Get project details | Yes |
| PATCH | /api/projects/:id | Update project | Yes (Manager+) |
| DELETE | /api/projects/:id | Archive project | Yes (Admin) |

### Tasks
| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | /api/projects/:id/tasks | List tasks (filterable) | Yes |
| POST | /api/projects/:id/tasks | Create task | Yes |
| PATCH | /api/tasks/:id | Update task (status, assignee) | Yes |
| DELETE | /api/tasks/:id | Delete task | Yes (Manager+) |
| POST | /api/tasks/:id/time | Start/stop time tracking | Yes |

### Example Request
```json
POST /api/projects/:id/tasks
{
  "title": "Implement user authentication",
  "description": "Add JWT-based auth with refresh tokens",
  "assignee_id": "uuid-here",
  "priority": "high",
  "due_date": "2025-06-15",
  "estimated_hours": 8
}
```""",

    "component-architect": """## Component Architecture

### Pages
```
/                    → Landing page (marketing)
/login               → Auth (login/register)
/dashboard           → Project overview + stats
/projects/:id        → Kanban board + task list
/projects/:id/chat   → Team chat for project
/settings            → User profile + team settings
/reports             → Time tracking reports
```

### Shared Components
- `<TaskCard />` — Draggable task with status, assignee, priority
- `<KanbanColumn />` — Column with drop zone
- `<TimeTracker />` — Start/stop timer widget
- `<Avatar />` — User avatar with online indicator
- `<ChatMessage />` — Message bubble with timestamp
- `<FileUpload />` — Drag-and-drop file attachment
- `<NotificationBell />` — Badge with dropdown list

### State Management (Zustand)
- `useAuthStore` — User session, token
- `useProjectStore` — Active project, tasks
- `useTimerStore` — Running timer state
- `useChatStore` — Messages, typing indicators""",

    "ui-generator": """## Generated UI Code

### Dashboard Page (`/dashboard/page.tsx`)
```tsx
export default function DashboardPage() {
  const { projects } = useProjectStore();
  
  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="flex items-center justify-between mb-8">
        <h1 className="text-2xl font-bold">Dashboard</h1>
        <Button onClick={() => router.push('/projects/new')}>
          <Plus className="h-4 w-4 mr-2" /> New Project
        </Button>
      </div>
      
      {/* Stats Cards */}
      <div className="grid grid-cols-4 gap-4 mb-8">
        <StatCard title="Active Projects" value={projects.length} />
        <StatCard title="Tasks Due Today" value={3} trend="+2" />
        <StatCard title="Hours This Week" value="32.5" />
        <StatCard title="Team Members" value={8} />
      </div>
      
      {/* Project Grid */}
      <div className="grid grid-cols-3 gap-4">
        {projects.map(project => (
          <ProjectCard key={project.id} project={project} />
        ))}
      </div>
    </div>
  );
}
```

### Kanban Board (`/projects/[id]/page.tsx`)
```tsx
export default function ProjectBoard({ params }) {
  const columns = ['backlog', 'todo', 'in_progress', 'review', 'done'];
  
  return (
    <div className="flex gap-4 p-6 overflow-x-auto h-full">
      {columns.map(status => (
        <KanbanColumn key={status} status={status}>
          {tasks.filter(t => t.status === status).map(task => (
            <TaskCard key={task.id} task={task} draggable />
          ))}
        </KanbanColumn>
      ))}
    </div>
  );
}
```""",

    "backend-generator": """## Generated Backend Code

### Prisma Schema (`prisma/schema.prisma`)
```prisma
model User {
  id        String   @id @default(uuid())
  email     String   @unique
  name      String
  password  String
  role      Role     @default(MEMBER)
  tasks     Task[]   @relation("assignee")
  entries   TimeEntry[]
  createdAt DateTime @default(now())
}

model Task {
  id          String   @id @default(uuid())
  title       String
  description String?
  status      Status   @default(BACKLOG)
  priority    Priority @default(MEDIUM)
  project     Project  @relation(fields: [projectId], references: [id])
  projectId   String
  assignee    User?    @relation("assignee", fields: [assigneeId], references: [id])
  assigneeId  String?
  dueDate     DateTime?
  entries     TimeEntry[]
  createdAt   DateTime @default(now())
  updatedAt   DateTime @updatedAt
}
```

### Task Router (`src/routes/tasks.ts`)
```typescript
router.post('/projects/:projectId/tasks', auth, async (req, res) => {
  const { title, description, assigneeId, priority, dueDate } = req.body;
  
  const task = await prisma.task.create({
    data: {
      title,
      description,
      projectId: req.params.projectId,
      assigneeId,
      priority,
      dueDate: dueDate ? new Date(dueDate) : null,
    },
    include: { assignee: true },
  });
  
  // Notify assignee
  if (assigneeId) {
    await notify(assigneeId, `You were assigned: ${title}`);
  }
  
  res.status(201).json(task);
});
```""",

    "test-writer": """## Test Suite

### API Tests (`tests/tasks.test.ts`)
```typescript
describe('POST /api/projects/:id/tasks', () => {
  it('creates a task with valid data', async () => {
    const res = await request(app)
      .post(`/api/projects/${projectId}/tasks`)
      .set('Authorization', `Bearer ${token}`)
      .send({ title: 'Test task', priority: 'high' });
    
    expect(res.status).toBe(201);
    expect(res.body.title).toBe('Test task');
    expect(res.body.status).toBe('backlog');
  });

  it('returns 401 without auth', async () => {
    const res = await request(app)
      .post(`/api/projects/${projectId}/tasks`)
      .send({ title: 'Test' });
    
    expect(res.status).toBe(401);
  });

  it('returns 400 without title', async () => {
    const res = await request(app)
      .post(`/api/projects/${projectId}/tasks`)
      .set('Authorization', `Bearer ${token}`)
      .send({ priority: 'high' });
    
    expect(res.status).toBe(400);
  });
});
```""",

    "deployment-planner": """## Deployment Configuration

### Dockerfile
```dockerfile
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npx prisma generate
RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app
COPY --from=builder /app/dist ./dist
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/prisma ./prisma
EXPOSE 3000
CMD ["node", "dist/server.js"]
```

### docker-compose.yml
```yaml
services:
  app:
    build: .
    ports: ["3000:3000"]
    environment:
      DATABASE_URL: postgresql://user:pass@db:5432/app
      REDIS_URL: redis://redis:6379
    depends_on: [db, redis]
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_PASSWORD: pass
    volumes: [pgdata:/var/lib/postgresql/data]
  redis:
    image: redis:7-alpine
volumes:
  pgdata:
```

### GitHub Actions (`.github/workflows/deploy.yml`)
```yaml
name: Deploy
on:
  push:
    branches: [main]
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: npm ci && npm test
      - run: docker build -t app .
      - run: docker push $REGISTRY/app:latest
      - run: railway up
```""",

    "app-assembler": """## Project Structure

```
project-manager/
├── prisma/
│   └── schema.prisma
├── src/
│   ├── app/
│   │   ├── (auth)/login/page.tsx
│   │   ├── dashboard/page.tsx
│   │   ├── projects/[id]/page.tsx
│   │   └── layout.tsx
│   ├── components/
│   │   ├── ui/ (shadcn components)
│   │   ├── TaskCard.tsx
│   │   ├── KanbanColumn.tsx
│   │   └── TimeTracker.tsx
│   ├── lib/
│   │   ├── prisma.ts
│   │   ├── auth.ts
│   │   └── api.ts
│   └── stores/
│       ├── auth.ts
│       └── project.ts
├── tests/
├── Dockerfile
├── docker-compose.yml
├── package.json
└── README.md
```

### Setup Instructions
```bash
git clone <repo>
cd project-manager
npm install
cp .env.example .env  # Add DATABASE_URL
npx prisma migrate dev
npm run dev  # http://localhost:3000
```

### Next Steps
1. Add WebSocket for real-time task updates
2. Implement file upload to S3
3. Add email notifications (SendGrid)
4. Build mobile-responsive views
5. Add Slack integration webhook""",
}


# ============================================================
# REVERSE ENGINEER — Mock outputs per agent
# ============================================================

MOCK_REVERSE_ENGINEER_OUTPUTS: dict[str, str] = {
    "repo-scanner": """## Repository Scan Results

### Languages
- **Primary:** TypeScript (68%)
- **Secondary:** Python (22%), SQL (5%), Shell (3%), YAML (2%)

### Frameworks Detected
- **Frontend:** Next.js 14, React 18, Tailwind CSS
- **Backend:** FastAPI (Python), SQLAlchemy ORM
- **Testing:** Pytest, Vitest, Playwright

### Project Structure
```
├── frontend/          (Next.js app — 45 files)
│   ├── src/app/       (App Router pages)
│   ├── src/components/ (React components)
│   └── src/lib/       (Utilities)
├── backend/           (FastAPI app — 32 files)
│   ├── app/api/       (REST + WebSocket endpoints)
│   ├── app/agents/    (LangChain agent definitions)
│   └── app/models/    (SQLAlchemy models)
└── docs/              (Documentation)
```

### Entry Points
- Frontend: `frontend/src/app/layout.tsx`
- Backend: `backend/app/main.py`
- Database: SQLite (dev), PostgreSQL (prod)

### Size Metrics
- ~12,000 lines of code
- 77 source files
- 4 database tables""",

    "dependency-mapper": """## Dependency Analysis

### Frontend (28 dependencies)

| Package | Version | Purpose | Risk |
|---------|---------|---------|------|
| next | 16.2.4 | Framework | Low |
| react | 19.2.4 | UI library | Low |
| motion | 12.38.0 | Animations | Low |
| lucide-react | 1.14.0 | Icons | Low |
| pptxgenjs | 3.12.0 | PPT export | Medium (large bundle) |

### Backend (14 dependencies)

| Package | Version | Purpose | Risk |
|---------|---------|---------|------|
| fastapi | 0.115.6 | Web framework | Low |
| langchain | 0.3.14 | AI orchestration | Medium (fast-moving) |
| langchain-anthropic | 0.3.4 | Claude integration | Medium |
| sqlalchemy | 2.0.36 | ORM | Low |
| python-jose | 3.3.0 | JWT auth | Low |
| bcrypt (passlib) | 1.7.4 | Password hashing | Low |

### Security Concerns
- ⚠️ `python-jose` — consider migrating to `PyJWT` (more maintained)
- ⚠️ No `helmet` equivalent for FastAPI (add security headers)
- ✅ All packages are on latest major versions""",

    "architecture-analyst": """## Architecture Analysis

### Pattern: Modular Monolith (Frontend) + API Backend

```
┌─────────────────────────────────────────┐
│           BROWSER (Client)               │
│  Next.js SSR + React SPA                │
└──────────────┬──────────────────────────┘
               │ HTTP + WebSocket
               ▼
┌─────────────────────────────────────────┐
│         FastAPI Backend                   │
│  ┌─────────┐ ┌──────────┐ ┌─────────┐  │
│  │ REST API│ │WebSocket │ │ Agents  │  │
│  │ (CRUD)  │ │(Streaming)│ │(LangCh.)│  │
│  └────┬────┘ └────┬─────┘ └────┬────┘  │
│       │            │            │        │
│       ▼            ▼            ▼        │
│  ┌─────────────────────────────────────┐│
│  │        SQLAlchemy ORM               ││
│  └──────────────┬──────────────────────┘│
└─────────────────┼───────────────────────┘
                  ▼
         ┌──────────────┐
         │   SQLite/    │
         │  PostgreSQL  │
         └──────────────┘
```

### Layers
1. **Presentation:** Next.js pages + React components
2. **API Gateway:** FastAPI routes (REST + WebSocket)
3. **Business Logic:** Agent pipelines (LangChain orchestration)
4. **Data Access:** SQLAlchemy models + sessions
5. **External Services:** Anthropic Claude API

### Communication
- Frontend → Backend: REST (CRUD) + WebSocket (streaming)
- Backend → AI: Anthropic API (streaming responses)
- Auth: JWT tokens via Bearer header + WebSocket query param""",

    "data-model-extractor": """## Data Model

### Entity Relationship

```
Users (1) ──── (N) ChatSessions
Users (1) ──── (N) WorkflowRuns
ChatSessions (1) ──── (N) Messages
```

### Tables

| Table | Fields | Purpose |
|-------|--------|---------|
| users | id, email, password_hash, created_at, updated_at | User accounts |
| chat_sessions | id, user_id, title, last_activity, final_output | Chat history |
| messages | id, chat_session_id, role, content, created_at | Chat messages |
| workflow_runs | id, user_id, title, type, status, input, output, agent_outputs, duration | Pipeline executions |

### Indexes
- `users.email` — UNIQUE index (login lookup)
- `chat_sessions.user_id` — FK index (list user's chats)
- `workflow_runs.user_id` — FK index (list user's runs)
- `messages.chat_session_id` — FK index (load chat messages)

### Data Patterns
- Soft deletes: Not implemented (hard deletes only)
- Audit trail: `created_at` on all tables, `updated_at` on users
- JSON storage: `final_output` and `agent_outputs` stored as TEXT (JSON strings)""",

    "api-surface-mapper": """## API Surface Map

### REST Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | /api/auth/register | No | Create account |
| POST | /api/auth/login | No | Get JWT token |
| GET | /api/auth/me | Yes | Current user info |
| GET | /api/chats | Yes | List chat sessions |
| POST | /api/chats | Yes | Create chat session |
| GET | /api/chats/:id | Yes | Get chat with messages |
| DELETE | /api/chats/:id | Yes | Delete chat |
| PUT | /api/chats/:id/messages | Yes | Add message |
| GET | /api/workflows | Yes | List workflow runs |
| POST | /api/workflows | Yes | Create workflow run |
| GET | /api/workflows/:id | Yes | Get workflow details |
| PATCH | /api/workflows/:id | Yes | Update workflow status |
| DELETE | /api/workflows/:id | Yes | Delete workflow |
| GET | /api/agents | No | List available agents |
| GET | /health | No | Health check |

### WebSocket
| Path | Auth | Description |
|------|------|-------------|
| /ws/chat?token=JWT | Yes (query param) | Real-time streaming |

### WebSocket Message Types (Client → Server)
- `user_message` — Send chat message
- `run_pipeline` — Start agent pipeline

### WebSocket Message Types (Server → Client)
- `stream` — Content chunk
- `pipeline_start` — Pipeline begins
- `agent_start/thinking/chunk/complete` — Agent progress
- `pipeline_complete` — Pipeline finished
- `error` — Error occurred""",

    "user-journey-tracer": """## User Journeys

### Journey 1: First-Time User Registration
```
1. Visit /register
2. Enter email + password (min 8 chars)
3. Backend: hash password (bcrypt), create user, generate JWT
4. Frontend: store token in localStorage
5. Redirect to /dashboard
6. WebSocket connects with token
```
**Code Path:** `register/page.tsx` → `POST /api/auth/register` → `User model` → `JWT creation`

### Journey 2: Run a Workflow Pipeline
```
1. User on /dashboard (home page)
2. Click feature card (e.g., "User Stories")
3. Navigate to idea input page
4. Type idea + click "Run Workflow"
5. WebSocket sends: {type: "run_pipeline", pipeline_type, message, agent_ids}
6. Backend creates WorkflowRun record
7. Backend executes agents sequentially
8. Each agent: start → thinking → chunks → complete
9. Frontend shows progress in left panel
10. Final output routed to preview panel
11. WorkflowRun marked as "completed"
```
**Code Path:** `DashboardLayout` → `useWorkflow.startPipeline` → WebSocket → `_handle_pipeline_execution` → `PipelineExecutor.execute` → `BaseAgent.astream`

### Journey 3: View Past Workflow Results
```
1. Click workflow in sidebar history
2. Frontend calls GET /api/workflows/:id
3. Load output into preview panel
4. Display based on type (markdown/slides/prototype)
```""",

    "tech-debt-auditor": """## Technical Debt Audit

### Critical Issues

| Issue | Location | Severity | Effort |
|-------|----------|----------|--------|
| SQLite in production | database.py | Critical | 2 days |
| Hardcoded CORS origins | main.py | High | 1 hour |
| No database migrations | models/ | High | 1 day |
| Print statements as logging | websocket.py | Medium | 4 hours |
| No input length validation | API endpoints | Medium | 2 hours |
| No rate limiting | All endpoints | High | 4 hours |

### Code Smells
- **God function:** `_handle_pipeline_execution` (150+ lines) — should be split
- **Duplicated DB session management:** `_get_db()` pattern repeated everywhere
- **Missing error boundaries:** WebSocket errors can crash the connection
- **No retry logic:** API calls to Anthropic have no retry on transient failures

### Testing Gaps
- 0% frontend test coverage
- ~5% backend test coverage (1 test file)
- No integration tests
- No E2E tests

### Security Debt
- JWT secret has a weak default value
- No CSRF protection
- WebSocket auth only checked on connect (not per-message)
- No request size limits""",

    "risk-assessor": """## Risk Assessment

### Security Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| JWT secret compromise | Medium | Critical | Use env-specific secrets, rotate quarterly |
| SQL injection | Low | Critical | SQLAlchemy parameterizes queries (safe) |
| XSS via chat content | Medium | High | Sanitize markdown rendering |
| Brute-force login | High | Medium | Add rate limiting (5/min) |
| API key exposure | Low | Critical | Never log API keys, use secrets manager |

### Scalability Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| SQLite file locking | High | Critical | Migrate to PostgreSQL |
| WebSocket memory per connection | Medium | High | Add connection pooling, Redis pub/sub |
| LLM API rate limits | Medium | Medium | Queue pipeline requests, add backoff |
| Single-server deployment | High | High | Containerize, deploy to ECS/K8s |

### Operational Risks
- No monitoring or alerting
- No backup strategy for database
- No disaster recovery plan
- Single point of failure (one server)""",

    "modernization-planner": """## Modernization Roadmap

### Phase 1: Quick Wins (1-2 weeks)
- [ ] Replace SQLite with PostgreSQL
- [ ] Add Alembic migrations
- [ ] Replace print() with structured logging
- [ ] Add rate limiting to auth endpoints
- [ ] Add input validation (max lengths)
- [ ] Fix CORS to use environment config

### Phase 2: Foundation (1-2 months)
- [ ] Dockerize both services
- [ ] Set up CI/CD (GitHub Actions)
- [ ] Add comprehensive test suite (80%+ coverage)
- [ ] Implement Redis for caching and sessions
- [ ] Add Sentry for error tracking
- [ ] Set up CloudWatch/Prometheus monitoring

### Phase 3: Scale (3-6 months)
- [ ] Move pipeline execution to background workers (Celery)
- [ ] Add WebSocket scaling via Redis pub/sub
- [ ] Implement multi-tenancy (team workspaces)
- [ ] Add OAuth (Google, GitHub login)
- [ ] Build admin dashboard
- [ ] Add usage analytics and billing

### Phase 4: Enterprise (6-12 months)
- [ ] SOC2 compliance
- [ ] SSO (SAML/OIDC)
- [ ] Audit logging
- [ ] Data residency options
- [ ] Custom agent marketplace
- [ ] On-premise deployment option

### Team Requirements
- Phase 1-2: 2 engineers (1 backend, 1 frontend)
- Phase 3: 4 engineers + 1 DevOps
- Phase 4: 6 engineers + 1 security + 1 PM""",

    "documentation-generator": """## Generated Documentation

### README.md

# IdeaFlow AI — Agentic Delivery Studio

An enterprise-grade AI platform that turns ideas into structured deliverables using specialist agent pipelines.

## Features
- 🎯 **6 Workflow Types** — User stories, prototypes, pitch decks, app scaffolding, codebase analysis, custom
- 🤖 **84 Specialist Agents** — Each with a defined role and expertise
- ⚡ **Real-time Streaming** — Watch agents think and produce output live
- 🎨 **Rich Previews** — Rendered slides, component trees, markdown docs
- 🔧 **Customizable Pipelines** — Add, remove, reorder agents

## Architecture
- **Frontend:** Next.js 16 + React 19 + Tailwind CSS + Motion
- **Backend:** FastAPI + SQLAlchemy + LangChain
- **AI:** Anthropic Claude (direct API or AWS Bedrock)
- **Database:** SQLite (dev) / PostgreSQL (prod)
- **Real-time:** WebSocket with JWT auth

## Quick Start
```bash
# Backend
cd backend && pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend && npm install && npm run dev
```

## API Reference
See `/api/docs` (Swagger UI) when backend is running.

## Contributing
1. Fork the repo
2. Create a feature branch
3. Write tests
4. Submit a PR

## License
MIT
""",
}
