---
name: AI Coach Hub
description: |
  A dark-mode AI coaching platform with a fixed left sidebar and six
  navigable screens: a marketing landing page, a personal dashboard with
  skill-level metrics and roadmap progress, a step-through skills assessment
  with progress tracker and skill graph, an AI coach chat interface with
  message simulation and quick-prompt chips, a phased learning roadmap with
  course resources and time commitments, and an interview practice simulator
  with scenario selection, recording simulation, and score feedback. Use when
  the brief asks for an AI coaching product, learning platform, career
  development tool, mentorship app, onboarding platform, or any
  assessment-and-progress product.
triggers:
  - "ai coaching"
  - "career coaching"
  - "learning platform"
  - "skills development"
  - "coaching app"
  - "mentorship"
  - "career development"
  - "training platform"
  - "skill gap"
  - "interview practice"
  - "learning roadmap"
  - "personal coach"
  - "onboarding"
  - "assessment platform"
od:
  mode: prototype
  platform: desktop
  scenario: saas-product
  preview:
    type: html
    entry: example.html
  design_system:
    requires: true
    sections: [color, typography, layout, components]
  outputs:
    primary: index.html
  example_prompt: "Build an AI coaching platform for data science career transitions — a landing page, a personal dashboard with skill metrics, a skills assessment flow, an AI coach chat, a phased learning roadmap, and an interview practice simulator."
  inputs:
    - "The coaching domain (career transitions, skills training, interview prep, onboarding, etc.)"
    - "The user persona — current role, experience level, and target goal"
    - "The 3–5 core skill areas or learning modules the platform will track"
---

# AI Coach Hub Skill

Produce a single, self-contained HTML prototype of an **AI coaching platform** — a
dark-mode sidebar app with six linked screens: Landing, Dashboard, Skills Assessment, AI
Coach Chat, Learning Roadmap, and Interview Practice. Compose it from the bundled
`example.html` reference — **not** by writing CSS from scratch. The reference encodes the
complete design language (near-black background, terracotta accent `#c96442`, warm silver
text, serif display headings, mono numerics, card components, progress bars, chat bubbles,
skill graphs, stat blocks) and one inline vanilla-JS controller. Your job is to replace
the copy, data, and domain vocabulary — not the mechanism or visual structure.

## Resource map

```
ai-coach-hub/
├── SKILL.md         ← you're reading this
└── example.html     ← rendered, self-contained reference (READ FIRST)
```

## When to use this template

Use this when the brief describes a product that:

- coaches or mentors a user toward a goal (career change, skill mastery, certification)
- assesses current state and generates a personalised improvement plan
- includes a conversational AI interface (chat with a coach / advisor)
- tracks progress through a phased learning or onboarding journey
- simulates practice scenarios (interviews, assessments, exercises)

If the brief is a general analytics dashboard without a coaching loop, use `dashboard`
instead. If it is a process map or workflow review, use `process-canvas` instead.

## Screen inventory (all six must be present and navigable)

| Screen | `data-page` id | `data-od-id` | Purpose |
|---|---|---|---|
| Landing | `landing` | `landing` | Marketing hero + 3 feature cards + 4 social-proof stats + CTA |
| Dashboard | `dashboard` | `dashboard` | User metrics (level, skill %, market value, momentum), quick actions, roadmap summary |
| Skills Assessment | `assessment` | `assessment` | Step-through questionnaire, progress bar, skill-graph panel |
| AI Coach Chat | `coach-chat` | `coach-chat` | Chat history, user/AI bubbles, quick-prompt chips, action panel |
| Learning Roadmap | `learning-roadmap` | `learning-roadmap` | Phased milestones with progress bars, course resources, time commitments |
| Interview Practice | `interview-practice` | `interview-practice` | Scenario selector, recording simulation, scoring + feedback, coach escalation |

## Workflow

### Step 0 — Pre-flight (mandatory before writing anything)

1. **Read `example.html` end-to-end** — through the `<style>` block, all six
   `<section data-page="...">` regions, and the `<script>` controller at the bottom of
   `<body>`. Note:
   - `assessmentState` — `currentQuestion`, `totalQuestions`
   - `const store` — `currentPage`, `userProfile` (name, role, targetRole, location)
   - `const routes` — six keys, one per page id
   - `navigateTo(pageId)` — sets `window.location.hash`; `handleRouteChange()` reads it
     and swaps `.is-active`
   - `data-nav="<pageId>"` on buttons, `data-page-link="<pageId>"` on sidebar links
   - `sendChatMessage()`, `nextQuestion()`, `selectRating()`, `completeAssessment()`,
     `startPractice()`, `stopRecording()`, `nextInterviewQuestion()` — handlers to update
     copy and data but not re-architect
   - `interviewState` — `scenarios` array, `currentScenario`, recording timer
2. **Read the active DESIGN.md** (already injected). Map its color tokens onto:
   - `--accent` (`#c96442` in the reference) → primary brand / interactive / progress fills
   - `--bg` → near-black page background
   - `--surface` → card and sidebar background
   - `--fg` → primary text
   - `--muted` → secondary text, labels, timestamps
   - Keep `--font-display` for serif headings (`h1`, `h2`), `--font-mono` for numerics
     and eyebrows

### Step 1 — Replace the coaching domain and persona

Change the app name (`Career Copilot` → your product name) and the user persona
(`Alex Chen`, `Senior Product Manager`, `San Francisco, CA`) throughout. Set all copy for
the coaching domain:

- **Landing** — product name, eyebrow, headline, lead paragraph, CTA label, three feature
  card titles and descriptions, four social-proof stat blocks
- **Dashboard** — user name, role, location, goal summary; four stat blocks (level,
  skill %, market value, momentum); three quick-action card titles and descriptions;
  three roadmap phases with titles, progress %, course names, and time commitments
- **Assessment** — category badge, question text, answer options; `totalQuestions` count;
  skill-graph labels and percentage values
- **AI Coach Chat** — coach name, pre-seeded conversation (2–3 AI turns + 1 user turn),
  quick-prompt chip labels, action panel item labels and response strings
- **Learning Roadmap** — three or more phases with title, status badge (`In Progress` /
  `Not Started`), progress bar %, course names and sources, time commitments
- **Interview Practice** — question type categories, `interviewState.scenarios` array
  titles, recorded-answer guidance text, score display, feedback summary

### Step 2 — Adapt the JS data

Edit the inline JS data objects — **not** the rendering logic:

- `store.userProfile` — `name`, `role`, `targetRole`, `location`
- `assessmentState.totalQuestions` — question count for the domain
- Skill-graph `.skill-bar-fill` widths and `.skill-label` text in the assessment panel
- `sendChatMessage()` AI response pool strings — make them domain-specific
- `interviewState.scenarios` array — titles and types for the domain
- `handleChatAction()` and `handleAction()` message strings

### Step 3 — Self-check all six screens

For each screen, verify before finishing:

- **Landing** — hero renders, feature cards display, stat blocks show, both CTA buttons
  navigate to `assessment`
- **Dashboard** — all four stat blocks render, three quick-action cards display, roadmap
  summary shows three phases, "View Full Roadmap" navigates to `learning-roadmap`
- **Assessment** — progress bar updates on `nextQuestion()`, skill graph updates on
  `updateSkillGraph()`, "Complete Assessment" calls `completeAssessment()` → `dashboard`
- **AI Coach Chat** — pre-seeded messages render on load, send button calls
  `sendChatMessage()`, quick-prompt chips call `insertPrompt()`, action panel calls
  `handleChatAction()`
- **Learning Roadmap** — three phases render with correct status badges, "Chat with
  Coach" navigates to `coach-chat`
- **Interview Practice** — scenario cards display, "Start Practice" calls `startPractice()`,
  recording timer works, "Schedule Coaching" navigates to `coach-chat`

### Step 4 — Navigation integrity check

Before emitting:

- Every sidebar `data-page-link` resolves to a `<section data-page="...">` that exists
- Every `data-nav` button resolves to a valid page id
- All `onclick="navigateTo('...')"` calls use valid page ids
- The `routes` map in the script contains all six page ids
- Exactly one `<section>` has `class="page is-active"` on load (default: `landing`)

### Step 5 — Emit the artifact

Wrap `index.html` in `<artifact>` tags. One sentence before. Stop after `</artifact>`.

## Hard rules

- **Single self-contained `index.html`** — inline CSS + one inline vanilla-JS controller,
  no external assets, no CDN links, no framework runtime.
- **System font stack for body** — `--font-body: -apple-system, BlinkMacSystemFont,
  'Segoe UI', system-ui, sans-serif`. Serif for display headings (`Georgia, 'Times New
  Roman', serif`). Mono for numerics, eyebrows, meta labels. No external font `<link>`.
- **`data-od-id` on every top-level region** — `sidebar`, `landing`, `dashboard`,
  `assessment`, `coach-chat`, `learning-roadmap`, `interview-practice`.
- **All six screens must be present** — a prototype missing a screen is incomplete.
- **No placeholder filler** — every metric, stat, course name, and message must be
  domain-specific and plausible.
- **Dark mode preserved** — the template's near-black token system is intentional; do not
  flip to a light background.
- **Accent used sparingly** — `--accent` is for primary CTAs, progress fills, and active
  states only; do not use it as a general text colour.

## Output contract

```
<artifact identifier="kebab-case-slug" type="text/html" title="Human Title">
<!doctype html>
<html>...</html>
</artifact>
```

One sentence before the artifact. Nothing after.
