# Tasks: Prototype Quality, Dynamic Questionnaire & Custom Template Upload

## Task 1: Dynamic Questionnaire for Prototype Pipeline

### 1.1 — Backend: extend `_handle_questionnaire` for `od_prototype`

**File:** `backend/app/api/websocket.py`

- Add `PROTOTYPE_QUESTION_SYSTEM_PROMPT` constant — instructs the LLM to generate up to 10 MCQ questions tailored to a prototype brief, using template and design system as context hints
- In `_handle_questionnaire`, add an `elif pipeline_type == "od_prototype":` branch that reads `template_id` and `design_system_id` from the message and uses the prototype-specific system prompt
- The `generate_questions` message handler must extract `template_id` and `design_system_id` from `message_data` and pass them to `_handle_questionnaire`
- Response shape is unchanged: `{ type: "questionnaire", data: { questions: [...] } }`

### 1.2 — Frontend: `PendingPipelineRun` carries `extraParams`

**File:** `frontend/src/components/layout/DashboardLayout.tsx`

- Add `extraParams` field to the `PendingPipelineRun` interface (carries `template_id`, `design_system_id`, `custom_design_system_body`, `discovery` for od_prototype runs)
- `handleQuestionnaireSubmit`: pass `pendingPipelineRun.extraParams` to `onStartPipeline` as the 6th argument
- `handleQuestionnaireSkip`: same — pass `extraParams` through

### 1.3 — Frontend: `dashboard/page.tsx` triggers questionnaire instead of pipeline

**File:** `frontend/src/app/dashboard/page.tsx`

- In the `useEffect` that consumes `pendingOdProtoRef`, instead of calling `startPipeline` directly:
  1. Set `pendingPipelineRun` via the existing mechanism (needs a new prop or direct state setter exposed from DashboardLayout — see note below)
  2. Send `generate_questions` WebSocket message with `pipeline_type: "od_prototype"`, `message: brief`, `template_id`, `design_system_id`
  3. Set `questionnaireLoading = true`
- **Note:** `pendingPipelineRun` and `questionnaireLoading` live in `DashboardLayout`. The cleanest approach is to expose a `handleRunOdPrototype(params)` callback from `DashboardLayout` (similar to `handleRunPipeline`) that `dashboard/page.tsx` calls instead of `startPipeline` directly.

### 1.4 — Frontend: `templates/page.tsx` skips discovery page

**File:** `frontend/src/app/workflow/prototype/templates/page.tsx`

- Change the "Continue" button handler: instead of `router.push("/workflow/prototype/discovery")`, write the draft to sessionStorage and `router.push("/dashboard")`
- Set `sessionStorage.setItem("od_prototype.pending", "true")` before navigating
- Remove the "Step 1 of 3" label — change to "Step 1 of 2" (templates → generate)
- The discovery sessionStorage key (`prototype.discovery`) is no longer written here — it's replaced by questionnaire answers enriched into the brief

---

## Task 2: Custom Template Upload

### 2.1 — Backend: `GET /api/prototype/fetch-url` endpoint

**File:** `backend/app/api/prototype_templates.py`

- Add `GET /api/prototype/fetch-url` route (auth required)
- Query param: `url` (string, required)
- Validation: must be `http://` or `https://`; reject private IP ranges (10.x, 172.16–31.x, 192.168.x, 127.x, localhost)
- Fetch with `httpx.AsyncClient`, timeout=10s, max response size 2MB
- Return `{ "html": "<content>" }` on success
- Return `{ "error": "<reason>" }` with appropriate HTTP status on failure
- Add the route to the router in `backend/app/api/__init__.py` or wherever routes are registered

### 2.2 — Frontend: `CustomTemplateModal.tsx` (new file)

**File:** `frontend/src/components/workflow/prototype/CustomTemplateModal.tsx`

- Two-tab modal: "Upload HTML file" and "From URL"
- **Upload tab:** `<input type="file" accept=".html,.htm">` — reads content via `FileReader.readAsText`; shows filename + char count preview
- **URL tab:** text input for URL; "Fetch" button calls `GET /api/prototype/fetch-url`; shows loading state and error; on success shows char count
- Name input (required): user labels their custom template
- "Use this template" button: disabled until name + content are both present
- On confirm: calls `onConfirm(CustomTemplate)` prop
- `CustomTemplate` interface: `{ id: string; name: string; body: string; source: "file" | "url"; sourceRef: string }`
- Stores confirmed templates in `localStorage` under key `"prototype.customTemplates"`

### 2.3 — Frontend: `TemplateGallery.tsx` — add upload card + prop

**File:** `frontend/src/components/workflow/prototype/TemplateGallery.tsx`

- Add optional prop `onSelectCustomTemplate?: (ct: CustomTemplate | null) => void`
- Add `UploadCustomCard` component at the end of the grid (always visible, not filtered by category/search)
- `UploadCustomCard` shows a dashed-border card with an upload icon and "Upload custom" label
- On click: opens `CustomTemplateModal`
- On modal confirm: calls `onSelectCustomTemplate(ct)` and closes modal
- When a custom template is selected, show it as a selected card (same ring/check badge as built-in templates) with a "×" to clear it
- Load saved custom templates from `localStorage` on mount; show them as selectable cards above the upload card

### 2.4 — Frontend: `templates/page.tsx` — wire custom template

**File:** `frontend/src/app/workflow/prototype/templates/page.tsx`

- Add `customTemplateBody` state (`string | null`)
- Add `handleSelectCustomTemplate(ct: CustomTemplate | null)` callback:
  - Sets `selectedTemplateId` to `ct.id` (or null to clear)
  - Sets `customTemplateBody` to `ct.body` (or null)
- Pass `onSelectCustomTemplate={handleSelectCustomTemplate}` to `TemplateGallery`
- Include `customTemplateBody` in the sessionStorage draft: `{ ..., customTemplateBody }`
- Update the summary line below the Continue button to show "Custom template" when active

### 2.5 — Frontend: `dashboard/page.tsx` — carry `customTemplateBody`

**File:** `frontend/src/app/dashboard/page.tsx`

- `pendingOdProtoRef` already carries `customDsBody`; add `customTemplateBody?: string` to its type
- Read `customTemplateBody` from the draft in sessionStorage
- Pass it in `extraParams` when triggering the questionnaire / pipeline

### 2.6 — Backend: `od_runner.py` — `custom_template_body` param

**File:** `backend/app/agents/od_runner.py`

- `run_od_prototype_pipeline` gains `custom_template_body: str | None = None` parameter
- `_load_od_context` gains `custom_template_body: str | None = None` parameter
- When `custom_template_body` is set:
  - Use it as `example_html` (the visual reference for the SPA Composer)
  - Set `template_body` to the generic "web-prototype" SKILL.md body (load via `od_loader.get_template("web-prototype")`) so the pipeline still has a workflow
  - Log a warning if the body is < 500 chars (likely not a real HTML page)
- In `_user_message_spa_composer`: when `od["custom_template"]` flag is set, replace the `TEMPLATE EXAMPLE` header with `CUSTOM TEMPLATE (user-supplied — use as structural reference)`

### 2.7 — Backend: `websocket.py` — read `custom_template_body`

**File:** `backend/app/api/websocket.py`

- In `_handle_od_prototype_execution` call site: read `message_data.get("custom_template_body") or None`
- Pass it to `_handle_od_prototype_execution` as a new `custom_template_body` param
- `_handle_od_prototype_execution` passes it to `run_od_prototype_pipeline`

---

## Task 3: Enhanced Prototype Quality

### 3.1 — `od_runner.py`: CRITICAL RULES preamble in system prompt

**File:** `backend/app/agents/od_runner.py`

- In `_compose_system_prompt`, prepend a `CRITICAL OUTPUT RULES` section as the very first block (before DESIGN.md)
- Content: 5 numbered rules covering output format, navigation wiring, content quality, token discipline, and self-check requirement
- This ensures the model reads the most important constraints before any other content

### 3.2 — `od_runner.py`: move nav checklist to top of composer user message

**File:** `backend/app/agents/od_runner.py`

- In `_user_message_spa_composer`, move the `NAVIGATION WIRING — NON-NEGOTIABLE REQUIREMENTS` block to the **very top** of the returned string (before `structure_note` and before the spec)
- This makes it the first thing the model reads in the user turn

### 3.3 — `requirements-analyst/AGENT.md`: richer content plan rules

**File:** `backend/agents/prompts/requirements-analyst/AGENT.md`

- Add to the RULES section:
  - `content_plan_per_page` must include ≥3 specific data items per page (real names/numbers, no placeholders)
  - Must include primary CTA label, table column headers, chart type + axis labels where applicable
  - `navigation_graph.pages` must include every page a user would expect; minimum 2 pages for any web app brief
  - Explicitly forbid "Metric A/B/C", "User 1/2/3", "Item 1/2/3" as placeholder patterns

### 3.4 — `html-prototype-builder/AGENT.md`: content richness + chrome consistency

**File:** `backend/agents/prompts/html-prototype-builder/AGENT.md`

- Add to NON-NEGOTIABLES (items 7, 8, 9):
  - Every page must have ≥3 rows/items of realistic seed data; tables ≥5 rows; lists ≥4 items; charts ≥6 data points
  - Every interactive element must have a wired handler in `<script>`; dead buttons are P0
  - Chrome (sidebar/topbar) must be copy-pasted identically across all pages — not rewritten

### 3.5 — `prototype-polisher/AGENT.md`: patch protocol

**File:** `backend/agents/prompts/prototype-polisher/AGENT.md`

- Add a `## PATCH PROTOCOL` section explaining surgical patching (not rewriting)
- Define P0/P1/P2 priority order: navigation broken → token violations → missing data → dead interactions → visual polish
- Instruct the agent to emit the corrected artifact inside `<artifact>` tags

### 3.6 — `prototype-finalizer/AGENT.md`: validation checklist

**File:** `backend/agents/prompts/prototype-finalizer/AGENT.md`

- Add a `## VALIDATION CHECKLIST` section with explicit checkbox items
- P0 navigation checks: routes map populated, data-page elements present, href format correct, `load` listener present
- P0 output contract: artifact tags, single file, no external deps
- P1 content checks: no placeholder text, tables have ≥5 rows, all buttons labelled
