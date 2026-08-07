# Tasks: PPT Pipeline Redesign

## Task 1 — Backend: `od_loader.py` — add PPT template filter

**File:** `backend/app/services/od_loader.py`

Add `list_ppt_templates()` function that filters `_all_templates()` to only return templates where `od.mode` is `"deck"` or `"slides"`. Returns slim view (no `body` field). Also add `get_ppt_template(template_id)` that returns the full payload including body.

---

## Task 2 — Backend: `loader.py` + `registry.py` — add `od_ppt` type

**File:** `backend/agents/loader.py`
- Add `"od_ppt"` to `SUPPORTED_PIPELINE_TYPES` frozenset

**File:** `backend/agents/registry.py`
- Add `"od_ppt": ["od-ppt-brief-analyst", "od-ppt-composer", "od-ppt-validator"]` to `PIPELINE_AGENTS`

---

## Task 3 — Backend: Agent prompt files

**Create** `backend/agents/prompts/od-ppt-brief-analyst/AGENT.md`

Frontmatter: `id: od-ppt-brief-analyst`, `pipeline_type: od_ppt`, `order: 1`, `max_tokens: 8000`, `tools: []`

Prompt body:
- Role: PPT Brief Analyst — turn user brief into a structured slide plan
- Receives: USER BRIEF, DISCOVERY ANSWERS, ACTIVE TEMPLATE SKILL.md, ACTIVE DESIGN SYSTEM (if applicable)
- Output: ONE JSON object in `<spec>...</spec>` tags with fields: title, audience, tone, slide_count (8–15), theme_choice (from template's available themes), slides array (each with index, type, title, content, visual_suggestion), design_notes
- Rules: real content only (no placeholders), theme_choice must reference an actual theme from the SKILL.md, slide count matches brief complexity

**Create** `backend/agents/prompts/od-ppt-composer/AGENT.md`

Frontmatter: `id: od-ppt-composer`, `pipeline_type: od_ppt`, `order: 2`, `max_tokens: 32768`, `tools: []`

Prompt body:
- Role: Deck Engineer — build the complete HTML deck from the spec
- Primary instruction: the ACTIVE TEMPLATE SKILL.md Workflow section — follow each numbered step
- Apply SKILL.md workflow per slide from the spec
- Use the template's own visual system (colors, fonts, layouts from SKILL.md)
- If ACTIVE DESIGN SYSTEM is provided, use its tokens (for simple-deck/ib-pitch-book)
- NEVER rewrite the navigation script — copy it verbatim from the template seed
- Every slide from the spec must appear as `<section class="slide">`
- First slide gets `class="slide active"`, all others start hidden
- Emit ONE artifact: `<artifact identifier="..." type="text/html" title="..."><!DOCTYPE html>...</artifact>`

**Create** `backend/agents/prompts/od-ppt-validator/AGENT.md`

Frontmatter: `id: od-ppt-validator`, `pipeline_type: od_ppt`, `order: 3`, `max_tokens: 32768`, `tools: []`

Prompt body:
- Role: Deck QA Agent — structural validation, surgical patching only
- P0 checks: `<section class="slide">` elements present, navigation script intact (keydown/click listeners), first slide has `active` class, single file, `<artifact>` tags present
- P1 checks: no lorem ipsum, slide counter correct
- If no violations: output unchanged
- Output: `<artifact>` tags with validated HTML

---

## Task 4 — Backend: `od_ppt_runner.py` — new pipeline runner

**Create** `backend/app/agents/od_ppt_runner.py`

Mirrors `od_runner.py` structure. Key differences:
- `_load_ppt_context(template_id, design_system_id, custom_ds_body, custom_template_body)`:
  - Loads template via `od_loader.get_ppt_template(template_id)` (not `get_template`)
  - Loads design system ONLY when `template.get("design_system", {}).get("requires") == True` OR `custom_ds_body` is provided
  - Sets `is_design_system_required` flag in returned context dict
- `_compose_ppt_system_prompt(base_prompt, od, include_design_system)`:
  - CRITICAL RULES preamble (deck-specific: slides, navigation, content, single-file)
  - DESIGN.md block only when `include_design_system=True`
  - SKILL.md body
  - Base agent role prompt
- `_user_message_brief_analyst(brief, discovery, od)` — brief + discovery
- `_user_message_deck_composer(spec_json, brief, discovery, od)` — spec + example.html + template seed
- `_user_message_delivery_validator(prior_html)` — HTML to validate
- `run_od_ppt_pipeline(template_id, design_system_id, brief, discovery, custom_ds_body, custom_template_body)`:
  - Loads 3 agents from registry: `od-ppt-brief-analyst`, `od-ppt-composer`, `od-ppt-validator`
  - Uses `DeepAgent.astream_with_usage` for all 3 (text-only, no tools)
  - Yields same event shapes as `od_runner.py`: `pipeline_start`, `agent_start`, `agent_chunk`, `agent_complete`, `artifact`, `pipeline_complete`, `pipeline_error`
  - Extracts spec from Agent 1 output via `<spec>...</spec>` regex
  - Extracts HTML from Agent 2/3 output via `<artifact>...</artifact>` regex

---

## Task 5 — Backend: `ppt_templates.py` — REST endpoints

**Create** `backend/app/api/ppt_templates.py`

```python
router = APIRouter(prefix="/api/ppt", tags=["ppt"])

GET /api/ppt/templates          → list_ppt_templates() slim view
GET /api/ppt/templates/{id}     → get_ppt_template(id) full view
GET /api/ppt/templates/{id}/preview  → serve example.html as FileResponse
```

Register router in `backend/app/main.py` (or wherever prototype_templates router is registered).

---

## Task 6 — Backend: `websocket.py` — add `od_ppt` handler

**File:** `backend/app/api/websocket.py`

1. In `run_pipeline` handler, add `od_ppt` branch (mirrors `od_prototype` block):
   - Tier gate: `can_run_pipeline(user.tier, "ppt")`
   - Create task: `_handle_od_ppt_execution(websocket, brief, template_id, design_system_id, discovery, user, custom_ds_body, custom_template_body)`

2. In `_handle_questionnaire`, add `od_ppt` branch:
   - System prompt generates 5 deck-specific MCQ questions (audience, slide count, tone, goal, data vs visual)
   - Reads `template_id` and `design_system_id` from message_data

3. Add `_handle_od_ppt_execution` function:
   - Validates template (skip if `custom_template_body` provided)
   - Validates design system only if template requires it
   - Creates WorkflowRun with `type="od_ppt"`
   - Streams events from `run_od_ppt_pipeline`
   - Translates events to WebSocket envelope `{type, chunk, section: "od_ppt", data}`
   - Persists to DB on completion

---

## Task 7 — Backend: Delete old PPT agent prompts

**Delete** these files:
- `backend/agents/prompts/ppt-content-strategist/AGENT.md` (and folder)
- `backend/agents/prompts/ppt-slide-architect/AGENT.md` (and folder)
- `backend/agents/prompts/ppt-code-generator/AGENT.md` (and folder)
- `backend/agents/prompts/ppt-assembler/AGENT.md` (and folder)

Update `registry.py` `PIPELINE_AGENTS["ppt"]` to `["od-ppt-brief-analyst", "od-ppt-composer", "od-ppt-validator"]`.

---

## Task 8 — Frontend: `ppt-api.ts` — API client

**Create** `frontend/src/lib/ppt-api.ts`

```ts
export interface PPTTemplate {
  id: string; name: string; description: string;
  mode: string | null; platform: string | null; scenario: string | null;
  triggers: string[]; example_prompt: string | null; has_preview: boolean;
  design_system: { requires?: boolean };
}
export interface PPTTemplateDetail extends PPTTemplate {
  inputs: ...; outputs: ...; body: string;
}
export async function listPPTTemplates(token: string): Promise<PPTTemplate[]>
export async function getPPTTemplate(token: string, id: string): Promise<PPTTemplateDetail>
export function getPPTTemplatePreviewUrl(id: string): string
  // → `${ENV.API_URL}/api/ppt/templates/${id}/preview`
```

---

## Task 9 — Frontend: `PPTTemplateGallery.tsx` — new component

**Create** `frontend/src/components/workflow/ppt/PPTTemplateGallery.tsx`

Copy structure from `TemplateGallery.tsx`. Differences:
- Categories: `["All", "Pitch Deck", "Business", "Tech", "Editorial", "Creative", "Minimal", "Custom"]`
- `getPPTBucket(template)` function maps template name/scenario to category
- Same `CompactTemplateCard` with iframe preview
- Same `CustomTemplateModal` integration
- Same "Upload custom" button in top bar
- No `TemplateDetailModal` needed (or reuse existing one)

---

## Task 10 — Frontend: `/workflow/ppt/templates/page.tsx` — wizard page

**Create** `frontend/src/app/workflow/ppt/templates/page.tsx`

Mirrors `/workflow/prototype/templates/page.tsx`. Differences:
- Storage key: `"ppt.draft"` (not `"prototype.draft"`)
- Pending key: `"od_ppt.pending"` (not `"od_prototype.pending"`)
- Uses `listPPTTemplates` / `PPTTemplateGallery`
- Design system section: **conditionally rendered** — only show when `selectedTemplate?.design_system?.requires === true`
- If DS not required: `canContinue = Boolean(selectedTemplateId && brief.trim())`
- If DS required: `canContinue = Boolean(selectedTemplateId && selectedDsId && brief.trim())`
- Step label: "New presentation · Step 1 of 2"
- Continue button: writes draft + sets `od_ppt.pending` + navigates to `/dashboard`

---

## Task 11 — Frontend: `dashboard/page.tsx` — add `od_ppt` pending flow

**File:** `frontend/src/app/dashboard/page.tsx`

1. Add `pendingOdPptRef` (mirrors `pendingOdProtoRef`):
   ```ts
   const pendingOdPptRef = useRef<{
     templateId: string; designSystemId: string | null; brief: string;
     discovery: unknown; customDsBody?: string; customTemplateBody?: string;
   } | null>(null);
   ```

2. Add `pendingOdPptParams` state (mirrors `pendingOdProtoParams`)

3. Add `useEffect` that reads `od_ppt.pending` from sessionStorage on auth (mirrors the `od_prototype.pending` effect)

4. Add `useEffect` that fires on `connectionStatus === "connected"` — consumes `pendingOdPptRef`, sends `generate_questions` for `od_ppt`, sets `pendingOdPptParams`

5. Route `pipeline_complete` for `od_ppt` → `setPptContent(finalOutput)` (already handled by the `ppt` branch — add `od_ppt` to the condition)

6. Pass `pendingOdPptParams` and `onClearPendingOdPpt` to `DashboardLayout`

---

## Task 12 — Frontend: `DashboardLayout.tsx` — add `od_ppt` support

**File:** `frontend/src/components/layout/DashboardLayout.tsx`

1. Add `pendingOdPptParams` and `onClearPendingOdPpt` props (mirrors `pendingOdProtoParams`)

2. Add `useEffect` for `pendingOdPptParams` (mirrors the `pendingOdProtoParams` effect):
   - `setMainView("execution")`
   - `setWorkflowType("ppt")`
   - `setPendingPipelineRun({ type: "od_ppt", message: brief, extraParams: { template_id, design_system_id, ... } })`
   - `setQuestionnaireLoading(true)`
   - Call `onClearPendingOdPpt()`

3. `workflowType` normalisation: add `od_ppt` → `ppt` (mirrors `od_prototype` → `prototype`)

4. `odPptNotifCreated` ref (mirrors `odProtoNotifCreated`) — creates notification when `od_ppt` pipeline starts

---

## Task 13 — Frontend: `CreationHub.tsx` — update PPT card

**File:** `frontend/src/components/home/CreationHub.tsx`

Change the "Presentation" card's click handler from `handleSelectFeature("ppt")` to `router.push("/workflow/ppt/templates")`.

---

## Task 14 — Frontend: `PPTPreview.tsx` — update for HTML deck output

**File:** `frontend/src/components/preview/PPTPreview.tsx`

1. Accept `pipelineType?: string` prop (passed from PreviewPanel)
2. When `pipelineType === "od_ppt"`:
   - Hide "Download PPTX" button (no PptxGenJS code)
   - Show "Download HTML" button that creates a blob URL and triggers download
3. When `pipelineType === "ppt"` (old pipeline, kept for history): existing behaviour

---

## Task 15 — Frontend: `types/index.ts` — add `od_ppt`

**File:** `frontend/src/types/index.ts`

Add `"od_ppt"` to the `WorkflowType` union type.

---

## Task 16 — Frontend: `PreviewPanel.tsx` — pass pipelineType to PPTPreview

**File:** `frontend/src/components/preview/PreviewPanel.tsx`

Pass `pipelineType` prop to `PPTPreview` so it knows whether to show PPTX or HTML download.
