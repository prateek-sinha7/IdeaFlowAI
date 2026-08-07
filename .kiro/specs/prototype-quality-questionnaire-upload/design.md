# Design: Prototype Quality, Dynamic Questionnaire & Custom Template Upload

## Overview

Three interconnected improvements to the prototype pipeline:

1. **Dynamic Questionnaire** — replace the static Discovery page with LLM-generated MCQ questions (same pattern as `user_stories`/`ppt`), shown inline in the dashboard before the pipeline fires
2. **Custom Template Upload** — let users supply their own HTML file or a website URL as a starting template in the TemplateGallery
3. **Enhanced Prototype Quality** — stronger agent prompts, richer content instructions, and a mandatory self-check pass to make navigation and interactivity consistent

---

## Feature 1: Dynamic Questionnaire for Prototype

### Current flow (to be replaced)

```
/workflow/prototype/templates  →  /workflow/prototype/discovery  →  /dashboard (auto-fires)
```

The `/discovery` page shows hardcoded radio buttons (Surface, Audience, Tone, Scale, Constraints). These are static — they don't adapt to the brief, template, or design system chosen.

### New flow

```
/workflow/prototype/templates  →  /dashboard (fires questionnaire first, then pipeline)
```

The Discovery page is **removed from the navigation path**. Instead, after the user clicks "Continue" on the templates page, the app navigates directly to `/dashboard` and triggers the same questionnaire flow that `user_stories` and `ppt` already use.

### Data flow

```
templates/page.tsx
  └─ sessionStorage.setItem("od_prototype.pending", "true")
  └─ sessionStorage.setItem("prototype.draft", { templateId, designSystemId, brief, customDsBody? })
  └─ router.push("/dashboard")

dashboard/page.tsx  (existing pendingOdProtoRef logic)
  └─ reads draft from sessionStorage
  └─ instead of calling startPipeline directly:
       calls websocketSend({ type: "generate_questions", pipeline_type: "od_prototype", message: brief,
                              template_id, design_system_id })
  └─ sets questionnaireLoading = true, pendingPipelineRun = { type: "od_prototype", ... }

DashboardLayout.tsx  (existing QuestionnairePanel logic)
  └─ shows QuestionnairePanel when questionnaireLoading || questionnaireQuestions.length > 0
  └─ on submit: enriches brief with answers, calls startPipeline("od_prototype", enrichedBrief, ..., extraParams)
  └─ on skip: calls startPipeline("od_prototype", brief, ..., extraParams)
```

### Backend: `generate_questions` for `od_prototype`

`websocket.py::_handle_questionnaire` currently only handles `user_stories` and `ppt`. It needs to handle `od_prototype` with a prototype-specific system prompt.

The question generator receives: `brief + template_id + design_system_id` and produces up to 10 MCQ questions tailored to the prototype context (e.g. "How many pages should the prototype have?", "Should it include a login/auth flow?", "What data density do you prefer?").

```python
# websocket.py — _handle_questionnaire
if pipeline_type == "od_prototype":
    template_hint = f"Template: {template_id}" if template_id else ""
    ds_hint = f"Design system: {design_system_id}" if design_system_id else ""
    system_prompt = PROTOTYPE_QUESTION_SYSTEM_PROMPT.format(
        template_hint=template_hint, ds_hint=ds_hint
    )
```

The `generate_questions` WebSocket message gains two optional fields:
```json
{ "type": "generate_questions", "pipeline_type": "od_prototype",
  "message": "<brief>", "template_id": "...", "design_system_id": "..." }
```

### `od_prototype` extra params threading

The `pendingPipelineRun` object in `DashboardLayout` needs to carry `template_id`, `design_system_id`, `customDsBody`, and `discovery` so they survive the questionnaire round-trip:

```ts
// DashboardLayout.tsx
interface PendingPipelineRun {
  type: WorkflowType;
  message: string;
  agentIds?: string[];
  // New — od_prototype only
  extraParams?: {
    template_id?: string;
    design_system_id?: string;
    custom_design_system_body?: string;
    discovery?: unknown;
  };
}
```

`handleQuestionnaireSubmit` and `handleQuestionnaireSkip` already call `onStartPipeline(type, message, agentIds, skills, hooks)`. The `startPipeline` function in `useWorkflow.ts` already accepts a 6th `extraParams` argument for `od_prototype`. The pending run's `extraParams` just needs to be passed through.

### Discovery page

The `/workflow/prototype/discovery/page.tsx` file is **kept** (not deleted) but is no longer linked from the templates page. It becomes a dead route — can be removed in a follow-up cleanup. The `DiscoveryForm` component is also kept as-is.

---

## Feature 2: Custom Template Upload

### UI — TemplateGallery

A new "Upload custom" card is added at the end of the template grid (always visible, not filtered by category). It opens a `CustomTemplateModal`.

```
TemplateGallery
  └─ CompactTemplateCard (existing, for each template)
  └─ UploadCustomCard (new — always last in grid)
       └─ opens CustomTemplateModal
```

### CustomTemplateModal

Two tabs:
- **Upload HTML** — `<input type="file" accept=".html,.htm">` — reads file as text via `FileReader`
- **From URL** — text input for a website URL — fetches via a new backend proxy endpoint to avoid CORS

```tsx
// CustomTemplateModal.tsx
interface CustomTemplate {
  id: string;          // "custom-<timestamp>"
  name: string;        // user-provided label
  body: string;        // raw HTML content
  source: "file" | "url";
  sourceRef: string;   // filename or URL
}
```

Custom templates are stored in `localStorage` (same pattern as custom design systems).

### Backend proxy endpoint (URL fetch)

```
GET /api/prototype/fetch-url?url=<encoded-url>
```

- Validates URL (must be http/https, no private IPs)
- Fetches with a 10s timeout, max 2MB response
- Returns `{ html: string }` or `{ error: string }`
- Auth required (JWT)

This avoids CORS issues when the user pastes a URL.

### Data flow

```
TemplateGallery
  └─ onSelectCustomTemplate(ct: CustomTemplate) callback (new prop)

templates/page.tsx
  └─ customTemplateBody state (string | null)
  └─ when customTemplateBody set: selectedTemplateId = "custom-<id>", show in summary

sessionStorage draft
  └─ { templateId, designSystemId, brief, customDsBody?, customTemplateBody? }

dashboard/page.tsx
  └─ pendingOdProtoRef carries customTemplateBody

od_runner.py
  └─ run_od_prototype_pipeline gains custom_template_body param
  └─ _load_od_context: when custom_template_body set, uses it as example_html
     and injects a "CUSTOM TEMPLATE" header block into the user message

websocket.py
  └─ reads custom_template_body from message, passes to od_runner
```

### Agent prompt impact

When a custom template is used, the `_user_message_spa_composer` function replaces the `TEMPLATE EXAMPLE` block with:

```
═══════════════════════════════════════════════════════════
CUSTOM TEMPLATE (user-supplied — use as structural reference)
Extract: layout regions, component patterns, navigation chrome.
Apply the ACTIVE DESIGN SYSTEM tokens — do NOT copy the custom
template's colors or fonts verbatim.
═══════════════════════════════════════════════════════════

{custom_template_body}
```

The `template_body` (SKILL.md) is replaced with a generic "web-prototype" SKILL.md when no matching template is found, so the pipeline still has a workflow to follow.

---

## Feature 3: Enhanced Prototype Quality

### Root cause of inconsistency

The LLM sometimes ignores the navigation wiring checklist because it appears deep in a long user message. The fix is to move the most critical constraints **earlier** and make them impossible to miss.

### Changes to `od_runner.py`

#### `_compose_system_prompt` — add a CRITICAL RULES preamble

```python
sections.insert(0,
    "═══════════════════════════════════════════════════════════\n"
    "CRITICAL OUTPUT RULES — READ BEFORE ANYTHING ELSE\n"
    "═══════════════════════════════════════════════════════════\n\n"
    "1. OUTPUT: Emit ONE complete HTML file inside <artifact>...</artifact> tags.\n"
    "2. NAVIGATION: Every page in the spec MUST have a <section data-page='id'>.\n"
    "   The routes map MUST be populated. Every nav link MUST use href='#/path'.\n"
    "3. CONTENT: No placeholder text. Every label, number, name is domain-specific.\n"
    "4. TOKENS: Use ONLY :root variables from the ACTIVE DESIGN SYSTEM below.\n"
    "5. SELF-CHECK: Before emitting, mentally click every nav link. If any page\n"
    "   would not show, fix it first.\n"
)
```

#### `_user_message_spa_composer` — move navigation checklist to top

The `NAVIGATION WIRING — NON-NEGOTIABLE REQUIREMENTS` block currently appears after the example HTML. Move it to the **very top** of the user message, before the spec.

#### `requirements-analyst/AGENT.md` — richer content plan

Add to the RULES section:

```markdown
- `content_plan_per_page` MUST include for each page:
  - At least 3 specific data items (real names, numbers, labels — no placeholders)
  - The primary CTA and its label
  - Any table/list column headers
  - Any chart type and its axis labels
- `navigation_graph.pages` MUST include every page the user would expect for
  the described app. A SaaS dashboard needs at minimum: dashboard, detail/item,
  settings. A kanban needs: board, card-detail. Never produce fewer than 2 pages
  for a web app brief.
```

#### `html-prototype-builder/AGENT.md` — content richness rules

Add to NON-NEGOTIABLES:

```markdown
7. Every page MUST have at least 3 rows/items of realistic seed data.
   Tables show ≥5 rows. Lists show ≥4 items. Charts show ≥6 data points.
8. Every interactive element (button, form, modal trigger) MUST have a
   wired handler in the <script> block. Dead buttons are a P0 failure.
9. The chrome (sidebar/topbar) MUST be pixel-identical across all pages.
   Copy-paste the chrome HTML block — do not rewrite it per page.
```

#### `prototype-polisher/AGENT.md` — explicit patch instructions

Add a PATCH PROTOCOL section:

```markdown
## PATCH PROTOCOL

You receive the SPA Composer's HTML. Your job is surgical patching, not rewriting.

For each violation found:
1. Identify the exact element or block causing the violation
2. Emit the corrected version inside <artifact> tags
3. Do NOT change anything that is not a violation

Priority order (fix P0 before P1 before P2):
- P0: Navigation broken (missing data-page, empty routes map, wrong href format)
- P0: Design token violations (hardcoded colors/fonts not from DESIGN.md)
- P1: Missing seed data (placeholder text, empty tables, Lorem ipsum)
- P1: Dead interactive elements (buttons with no handler)
- P2: Visual polish (spacing, alignment, density)
```

#### `prototype-finalizer/AGENT.md` — structural validation checklist

Add an explicit VALIDATION CHECKLIST:

```markdown
## VALIDATION CHECKLIST

Run each check. If any P0 fails, fix it before emitting.

**P0 — Navigation integrity:**
- [ ] Every `routes` entry has a matching `<section data-page="...">` element
- [ ] No nav link uses `href="#page"` without the slash (must be `href="#/page"`)
- [ ] First page has `class="is-active"` on its `<section data-page>`
- [ ] `window.addEventListener('load', route)` is present

**P0 — Output contract:**
- [ ] Output is wrapped in `<artifact>...</artifact>` tags
- [ ] Output is a single complete HTML file (no external dependencies)

**P1 — Content quality:**
- [ ] No "Lorem ipsum", "Metric A", "User 1", or other placeholder text
- [ ] Every table has ≥5 rows of realistic data
- [ ] Every button/link has a visible label (no icon-only without aria-label)
```

---

## Component & File Change Map

### Frontend

| File | Change |
|------|--------|
| `frontend/src/app/workflow/prototype/templates/page.tsx` | Remove "Continue to discovery" → navigate directly to dashboard; add `customTemplateBody` state; pass `onSelectCustomTemplate` to TemplateGallery |
| `frontend/src/components/workflow/prototype/TemplateGallery.tsx` | Add `onSelectCustomTemplate` prop; add `UploadCustomCard` at end of grid |
| `frontend/src/components/workflow/prototype/CustomTemplateModal.tsx` | New file — file upload + URL fetch tabs |
| `frontend/src/app/dashboard/page.tsx` | `pendingOdProtoRef` triggers questionnaire instead of `startPipeline` directly; carries `customTemplateBody` |
| `frontend/src/components/layout/DashboardLayout.tsx` | `PendingPipelineRun.extraParams` carries od_prototype params; `handleQuestionnaireSubmit`/`handleQuestionnaireSkip` pass extraParams to `startPipeline` |

### Backend

| File | Change |
|------|--------|
| `backend/app/api/websocket.py` | `_handle_questionnaire` handles `od_prototype`; `generate_questions` message reads `template_id`/`design_system_id`; `_handle_od_prototype_execution` reads `custom_template_body` |
| `backend/app/agents/od_runner.py` | `run_od_prototype_pipeline` gains `custom_template_body` param; `_load_od_context` uses it as `example_html`; `_compose_system_prompt` gets CRITICAL RULES preamble; nav checklist moved to top of composer user message |
| `backend/app/api/prototype_templates.py` | New `GET /api/prototype/fetch-url` endpoint |
| `backend/agents/prompts/requirements-analyst/AGENT.md` | Richer content plan rules |
| `backend/agents/prompts/html-prototype-builder/AGENT.md` | Content richness + chrome consistency rules |
| `backend/agents/prompts/prototype-polisher/AGENT.md` | Patch protocol section |
| `backend/agents/prompts/prototype-finalizer/AGENT.md` | Validation checklist |

---

## API Contracts

### WebSocket: `generate_questions` (extended)

**Request:**
```json
{
  "type": "generate_questions",
  "pipeline_type": "od_prototype",
  "message": "<user brief>",
  "template_id": "web-prototype",
  "design_system_id": "linear"
}
```

**Response** (existing `questionnaire` event shape, unchanged):
```json
{
  "type": "questionnaire",
  "data": {
    "questions": [
      { "id": "q1", "question": "How many pages should the prototype have?",
        "options": ["1–2 (focused)", "3–5 (standard)", "6+ (full app)"] },
      ...
    ]
  }
}
```

### REST: `GET /api/prototype/fetch-url`

**Request:** `?url=https%3A%2F%2Fexample.com` (JWT required)

**Response 200:**
```json
{ "html": "<!doctype html>..." }
```

**Response 4xx/5xx:**
```json
{ "error": "URL fetch failed: timeout" }
```

---

## Key Design Decisions

1. **Discovery page not deleted** — kept as a dead route to avoid breaking any bookmarks or history entries. The questionnaire replaces its function entirely.

2. **Custom template stored in localStorage** — same pattern as custom design systems. No backend storage needed. The HTML body is passed through sessionStorage → WebSocket message → od_runner, same as `custom_design_system_body`.

3. **URL fetch via backend proxy** — browser CORS blocks direct fetches to arbitrary URLs. The backend proxy is the only reliable approach. It's auth-gated and size-limited to prevent abuse.

4. **Questionnaire for od_prototype uses brief + template + DS context** — the question generator gets all three so it can ask relevant questions (e.g. for a "kanban" template it asks about columns; for a "dashboard" template it asks about KPI types).

5. **Quality improvements are prompt-only** — no new agents, no pipeline restructuring. The 4-agent pipeline is already the right shape; the issue is prompt discipline. Moving the nav checklist to the top of the user message and adding a CRITICAL RULES preamble to the system prompt are the highest-leverage changes.
