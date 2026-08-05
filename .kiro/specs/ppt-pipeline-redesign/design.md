# Design: PPT Pipeline Redesign — OpenDesign Template + DeepAgent Flow

## Overview

Replace the existing 4-agent PptxGenJS pipeline with a new OpenDesign-style HTML deck pipeline. The new flow mirrors the prototype wizard exactly: Brief → Template → (optional Design System) → Dashboard → Questionnaire → 3-agent DeepAgent pipeline → HTML deck output.

The existing `ppt` pipeline type is **replaced** — same pipeline type string, new runner, new agents, new output format.

---

## Why Replace PptxGenJS

The current pipeline hardcodes white/black/navy colors in every agent prompt and produces PptxGenJS JavaScript code that gets wrapped in an HTML viewer. This is fragile (JS code generation is error-prone), visually limited (3 colors only), and doesn't leverage OpenDesign's 50+ professionally designed deck templates.

The new pipeline produces **self-contained HTML decks** directly — the same format OpenDesign's deck skills produce. These are richer, more visually diverse, and don't require a separate PPTX export step.

---

## New Flow

```
CreationHub "Presentation" card
  → /workflow/ppt/templates  (Step 1: Brief + Template + optional DS)
  → /dashboard               (Step 2: Questionnaire → od_ppt pipeline)
  → Pipeline execution view  (3 DeepAgents streaming)
  → PPTPreview               (HTML deck in iframe)
```

---

## Template Selection

### Which OpenDesign templates to use

Filter `od.mode == "deck"` OR `od.mode == "slides"` from the design-templates directory. Key templates available:

| ID | Name | Style |
|----|------|-------|
| `html-ppt` | HTML PPT Studio | Master skill, 36 themes |
| `html-ppt-pitch-deck` | Pitch Deck | Investor-ready |
| `html-ppt-tech-sharing` | Tech Sharing | GitHub-dark, terminal |
| `html-ppt-weekly-report` | Weekly Report | Corporate KPI |
| `html-ppt-course-module` | Course Module | Training/education |
| `html-ppt-product-launch` | Product Launch | Marketing |
| `html-ppt-retro-quarterly-review` | Quarterly Review | Retro style |
| `simple-deck` | Simple Deck | Minimal, uses DESIGN.md |
| `guizang-ppt` | Magazine Web PPT | Editorial, WebGL |
| `kami-deck` | Kami Deck | Print-grade, serif |
| `replit-deck` | Replit Deck | 8 themes |
| `ib-pitch-book` | IB Pitch Book | Finance/banking |
| `open-design-landing-deck` | Landing Deck | Warm editorial |
| `html-ppt-zhangzara-*` | ZhangZara series | 30+ visual styles |

### Design system usage

Most deck templates are **self-contained** — they carry their own visual system and do NOT use the shared design systems. Two exceptions:
- `simple-deck` — `design_system.requires: true`
- `ib-pitch-book` — `design_system.requires: true`

**UI logic**: Show the design system picker only when the selected template has `design_system.requires: true`. For all other templates, skip the DS step entirely.

### Custom templates

Same `CustomTemplateModal` as prototype — user can upload HTML or paste URL.

---

## Backend Architecture

### New runner: `backend/app/agents/od_ppt_runner.py`

Mirrors `od_runner.py` exactly. Uses `DeepAgent` with `astream_with_usage` (text-only, `tools=[]`).

**3-agent pipeline:**

```
Agent 1: PPT Brief Analyst     (od-ppt-brief-analyst)
Agent 2: PPT Deck Composer     (od-ppt-composer)
Agent 3: PPT Delivery Validator (od-ppt-validator)
```

**Pipeline function:**
```python
async def run_od_ppt_pipeline(
    template_id: str,
    design_system_id: str | None,
    brief: str,
    discovery: dict | None,
    custom_ds_body: str | None = None,
    custom_template_body: str | None = None,
) -> AsyncGenerator[dict, None]:
```

**Context loading** (`_load_ppt_context`):
- Loads template SKILL.md body (same as prototype)
- Loads design system DESIGN.md only if `template.get("design_system", {}).get("requires") == True` OR `custom_ds_body` provided
- Loads `example.html` for visual reference
- Loads `references/*.md` files
- Sets `is_design_system_required` flag

**System prompt composition** (`_compose_ppt_system_prompt`):
- Same structure as `_compose_system_prompt` in od_runner
- CRITICAL RULES preamble (deck-specific version)
- DESIGN.md block (only when design system is required/provided)
- SKILL.md body
- Agent role prompt

**User message builders:**
- `_user_message_brief_analyst(brief, discovery, od)` → brief + discovery answers
- `_user_message_deck_composer(spec_json, brief, discovery, od)` → spec + example.html + template seed
- `_user_message_delivery_validator(prior_html)` → HTML to validate

### CRITICAL RULES preamble (deck-specific)

```
1. OUTPUT: Emit ONE complete HTML file inside <artifact>...</artifact> tags.
2. SLIDES: Every slide must be a <section class="slide"> element.
   The first slide gets class="slide active". All others start hidden.
3. NAVIGATION: Arrow keys (←/→), click buttons, and touch swipe must all work.
   Never rewrite the proven nav script — it solves iframe-specific bugs.
4. CONTENT: No placeholder text. No lorem ipsum. Every slide has real content.
5. SELF-CONTAINED: No external image URLs. No CDN dependencies except PptxGenJS
   if the template requires it. Single file, works offline.
```

### Agent 1: PPT Brief Analyst

**Role**: Turn the user's brief into a structured slide plan.

**Output schema** (wrapped in `<spec>...</spec>`):
```json
{
  "title": "Presentation title",
  "audience": "Who this is for",
  "tone": "professional|casual|technical|inspirational",
  "slide_count": 10,
  "theme_choice": "which theme/palette from the template to use",
  "slides": [
    {
      "index": 1,
      "type": "title|content|data|quote|image|closing",
      "title": "Slide title",
      "content": "Key points, data, narrative",
      "visual_suggestion": "chart type, layout hint, icon suggestion"
    }
  ],
  "design_notes": "Any specific design guidance from the brief"
}
```

**Rules**:
- Slide count: 8–15 based on brief complexity
- Every slide has specific, real content — no "TBD" or placeholders
- Theme choice must reference an actual theme from the template's SKILL.md

### Agent 2: PPT Deck Composer

**Role**: Build the complete HTML deck from the spec.

**Primary instruction**: The template's SKILL.md Workflow section — follow each numbered step.

**Key constraints**:
- Apply the SKILL.md workflow per slide from the spec
- Use the template's own visual system (colors, fonts, layouts)
- If design system is provided, use its tokens for `simple-deck`/`ib-pitch-book`
- Navigation script must be copied verbatim from the template seed — never rewritten
- Every slide from the spec must appear in the output
- Emit as `<artifact>...</artifact>`

### Agent 3: PPT Delivery Validator

**Role**: Final QA — structural validation only, no redesign.

**Checks**:
- P0: `<section class="slide">` elements present and match spec slide count
- P0: Navigation script intact (hashchange/keydown listeners present)
- P0: First slide has `class="slide active"`
- P0: Single file (no broken external references)
- P0: `<artifact>` tags present
- P1: No lorem ipsum / placeholder text
- P1: Slide counter shows correct total

**Output**: Fixed HTML in `<artifact>` tags.

### `od_loader.py` additions

```python
def list_ppt_templates() -> list[dict]:
    """Return gallery list: only deck/slides mode templates."""
    out = []
    for t in _all_templates():
        mode = t.get("mode", "")
        if mode not in ("deck", "slides"):
            continue
        out.append({k: v for k, v in t.items() if k != "body"})
    return out
```

### `websocket.py` changes

1. Add `od_ppt` to the `run_pipeline` handler (mirrors `od_prototype` block)
2. Add `od_ppt` branch in `_handle_questionnaire` with deck-specific questions:
   - "How many slides should the presentation have?" (5–8 / 10–12 / 15+)
   - "Who is the primary audience?" (Executives / Technical team / Customers / General)
   - "What tone should the deck have?" (Professional / Inspirational / Data-driven / Creative)
   - "What's the primary goal?" (Pitch/fundraise / Inform/educate / Sell/persuade / Report)
   - "Should it be data-heavy or visual-heavy?" (Data charts & tables / Visual & imagery / Balanced)
3. Add `_handle_od_ppt_execution` function (mirrors `_handle_od_prototype_execution`)

### `prototype_templates.py` additions

```python
@router.get("/api/ppt/templates", response_model=list[TemplateListItem])
async def list_ppt_templates_endpoint(current_user: User = Depends(get_current_user)):
    return od_loader.list_ppt_templates()

@router.get("/api/ppt/templates/{template_id}/preview")
async def get_ppt_template_preview(template_id: str, ...):
    # Same as prototype preview endpoint
```

Or add to existing `prototype_templates.py` with `/api/ppt/` prefix.

### `registry.py` + `loader.py` changes

Add `od_ppt` to `SUPPORTED_PIPELINE_TYPES` in `loader.py`.

Add to `registry.py` `PIPELINE_AGENTS`:
```python
"od_ppt": [
    "od-ppt-brief-analyst",
    "od-ppt-composer",
    "od-ppt-validator",
],
```

(These won't be used by the orchestrator — `od_ppt` uses its own runner like `od_prototype` — but the registry entry is needed for tier gating and validation.)

---

## Frontend Architecture

### New pages

**`/workflow/ppt/templates/page.tsx`** — mirrors `/workflow/prototype/templates/page.tsx`

Sections:
1. Brief textarea (rows=5)
2. PPT Template Gallery (filtered to deck templates)
3. Design System Picker — **conditionally shown** only when selected template has `design_system.requires: true`

On "Continue":
- Write `ppt.draft` to sessionStorage: `{ templateId, designSystemId?, brief, customDsBody?, customTemplateBody? }`
- Set `od_ppt.pending = "true"` in sessionStorage
- Navigate to `/dashboard`

Step label: "Step 1 of 2" (no discovery page — questionnaire replaces it)

### New components

**`frontend/src/components/workflow/ppt/PPTTemplateGallery.tsx`**

Same structure as `TemplateGallery.tsx`. Categories:
- All, Pitch Deck, Business, Tech, Editorial, Creative, Minimal, Custom

Category mapping from template scenario/name:
```ts
function getPPTBucket(template): string {
  const name = template.name.toLowerCase();
  const scenario = (template.scenario ?? "").toLowerCase();
  if (name.includes("pitch") || name.includes("investor")) return "Pitch Deck";
  if (name.includes("tech") || name.includes("code") || name.includes("terminal")) return "Tech";
  if (name.includes("editorial") || name.includes("magazine") || name.includes("kami")) return "Editorial";
  if (name.includes("weekly") || name.includes("report") || name.includes("quarterly")) return "Business";
  if (name.includes("course") || name.includes("training")) return "Business";
  if (name.includes("minimal") || name.includes("simple") || name.includes("clean")) return "Minimal";
  if (["design", "creative", "artistic"].includes(scenario)) return "Creative";
  return "All";
}
```

### `dashboard/page.tsx` changes

Add `pendingOdPptRef` (mirrors `pendingOdProtoRef`):
```ts
const pendingOdPptRef = useRef<{
  templateId: string;
  designSystemId: string | null;
  brief: string;
  discovery: unknown;
  customDsBody?: string;
  customTemplateBody?: string;
} | null>(null);
```

On `od_ppt.pending` in sessionStorage → read `ppt.draft` → store in ref.

On WebSocket connected → consume ref → send `generate_questions` with `pipeline_type: "od_ppt"` → set `pendingOdPptParams`.

Route `pipeline_complete` for `od_ppt` → `setPptContent(finalOutput)` (same as `ppt`).

### `DashboardLayout.tsx` changes

Add `pendingOdPptParams` prop (mirrors `pendingOdProtoParams`).

`workflowType` normalisation: `od_ppt` → `ppt` (same as `od_prototype` → `prototype`).

The `odProtoNotifCreated` effect pattern is replicated for `od_ppt`.

### `CreationHub.tsx` change

PPT card: change `onClick` from `handleSelectFeature("ppt")` to `router.push("/workflow/ppt/templates")`.

### `types/index.ts` change

Add `"od_ppt"` to `WorkflowType` union.

### `PPTPreview.tsx` changes

The existing component renders HTML in an iframe — it works as-is for the new HTML deck output.

Changes needed:
- Hide "Download PPTX" button when `pipeline_type === "od_ppt"` (no PptxGenJS code available)
- Add "Download HTML" button for `od_ppt` output (downloads the HTML file)
- The revision bar stays — revision pipeline will be updated separately

### `ppt-api.ts` (new file)

```ts
// frontend/src/lib/ppt-api.ts
export interface PPTTemplate { /* same shape as PrototypeTemplate */ }
export async function listPPTTemplates(token: string): Promise<PPTTemplate[]>
export async function getPPTTemplate(token: string, id: string): Promise<PPTTemplate>
export function getPPTTemplatePreviewUrl(id: string): string
```

---

## Agent Prompt Files

### `od-ppt-brief-analyst/AGENT.md`

```yaml
id: od-ppt-brief-analyst
name: Presentation Strategist Agent
role: Slide Plan & Content Architecture
pipeline_type: od_ppt
order: 1
max_tokens: 8000
tools: []
guardrails: []
context_from: []
icon: "📋"
estimated_duration: 8.0
```

Prompt body: Instructs the agent to produce a `<spec>` JSON with slide plan, theme choice, content per slide. Enforces real content (no placeholders), appropriate slide count, and theme selection from the template's available options.

### `od-ppt-composer/AGENT.md`

```yaml
id: od-ppt-composer
name: Deck Engineer Agent
role: HTML Deck Construction
pipeline_type: od_ppt
order: 2
max_tokens: 32768
tools: []
guardrails: []
context_from: ["$previous"]
icon: "🖥️"
estimated_duration: 30.0
```

Prompt body: Instructs the agent to follow the SKILL.md Workflow as primary instruction, apply it per slide from the spec, use the template's visual system, never rewrite the nav script, emit `<artifact>`.

### `od-ppt-validator/AGENT.md`

```yaml
id: od-ppt-validator
name: Deck QA Agent
role: Structural Validation & Delivery
pipeline_type: od_ppt
order: 3
max_tokens: 32768
tools: []
guardrails: []
context_from: ["$previous"]
icon: "📦"
estimated_duration: 10.0
```

Prompt body: Validation checklist (P0/P1 checks), surgical patching only, emit `<artifact>`.

---

## Existing PPT Pipeline — What Changes

The old `ppt` pipeline agents (`ppt-content-strategist`, `ppt-slide-architect`, `ppt-code-generator`, `ppt-assembler`) are **deleted**. Their AGENT.md files are removed.

The `ppt_revision` pipeline agents are **kept for now** — revision of the new HTML deck format will be handled by a future `od_ppt_revision` pipeline. The existing revision agents still work on PptxGenJS code, so they'll be deprecated once the new revision flow is built.

The `ppt` pipeline type in `registry.py` is updated to point to the new agents:
```python
"ppt": ["od-ppt-brief-analyst", "od-ppt-composer", "od-ppt-validator"],
```

But since `od_ppt` uses its own runner (not the orchestrator), the `ppt` type in registry is only used for tier gating. The actual execution goes through `od_ppt_runner.py`.

---

## Data Flow Summary

```
sessionStorage: ppt.draft = { templateId, designSystemId?, brief, customDsBody?, customTemplateBody? }
sessionStorage: od_ppt.pending = "true"

dashboard/page.tsx:
  pendingOdPptRef → { templateId, designSystemId, brief, discovery, customDsBody?, customTemplateBody? }
  → send generate_questions(pipeline_type: "od_ppt", message: brief, template_id, design_system_id)
  → setPendingOdPptParams(...)

DashboardLayout.tsx:
  pendingOdPptParams effect → setPendingPipelineRun({ type: "od_ppt", extraParams: { template_id, design_system_id, ... } })
  → setQuestionnaireLoading(true)

QuestionnairePanel → user answers → handleQuestionnaireSubmit
  → onStartPipeline("od_ppt", enrichedBrief, undefined, skills, hooks, extraParams)
  → startPipeline() → websocketSend({ type: "run_pipeline", pipeline_type: "od_ppt", ... })

Backend websocket.py:
  → _handle_od_ppt_execution(brief, template_id, design_system_id, discovery, ...)
  → run_od_ppt_pipeline(...)
  → 3 DeepAgents stream events
  → pipeline_complete { final_html }

dashboard/page.tsx:
  pipeline_complete → setPptContent(finalOutput)
  → PPTPreview renders HTML deck in iframe
```

---

## File Change Map

| File | Action |
|------|--------|
| `backend/app/agents/od_ppt_runner.py` | **Create** |
| `backend/app/api/ppt_templates.py` | **Create** |
| `backend/app/api/websocket.py` | **Modify** — add od_ppt handler + questionnaire |
| `backend/app/services/od_loader.py` | **Modify** — add list_ppt_templates() |
| `backend/agents/loader.py` | **Modify** — add od_ppt to SUPPORTED_PIPELINE_TYPES |
| `backend/agents/registry.py` | **Modify** — update ppt agents list |
| `backend/agents/prompts/od-ppt-brief-analyst/AGENT.md` | **Create** |
| `backend/agents/prompts/od-ppt-composer/AGENT.md` | **Create** |
| `backend/agents/prompts/od-ppt-validator/AGENT.md` | **Create** |
| `backend/agents/prompts/ppt-content-strategist/AGENT.md` | **Delete** |
| `backend/agents/prompts/ppt-slide-architect/AGENT.md` | **Delete** |
| `backend/agents/prompts/ppt-code-generator/AGENT.md` | **Delete** |
| `backend/agents/prompts/ppt-assembler/AGENT.md` | **Delete** |
| `frontend/src/app/workflow/ppt/templates/page.tsx` | **Create** |
| `frontend/src/components/workflow/ppt/PPTTemplateGallery.tsx` | **Create** |
| `frontend/src/lib/ppt-api.ts` | **Create** |
| `frontend/src/app/dashboard/page.tsx` | **Modify** — add od_ppt pending flow |
| `frontend/src/components/layout/DashboardLayout.tsx` | **Modify** — add od_ppt params |
| `frontend/src/components/home/CreationHub.tsx` | **Modify** — PPT card → wizard |
| `frontend/src/components/preview/PPTPreview.tsx` | **Modify** — HTML download, hide PPTX btn |
| `frontend/src/types/index.ts` | **Modify** — add od_ppt |
