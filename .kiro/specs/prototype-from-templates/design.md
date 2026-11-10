# Prototype from Templates — Technical Design

## System Overview

The feature adds one new workflow and one new wizard mode. No new API endpoints, no changes to `engine.py`, `manifest.py`, or `selections.py`.

```
backend/agents/workflows/prototype_from_template/
└── workflow.yaml                        ← NEW

frontend/src/components/workflow/
├── prototype/
│   └── RequirementsStep.tsx             ← NEW
│   └── RequirementsStep.test.tsx        ← NEW
├── LaunchWizard.tsx                     ← MODIFIED (new wizard mode)
└── prototype/TemplateGallery.tsx        ← MODIFIED (mandatory selection + prototype filter)

frontend/src/lib/
└── launchDraft.ts                       ← MODIFIED (add "prototype_from_template" to LaunchMode)

frontend/src/types/index.ts              ← MODIFIED (if LaunchMode is typed here)
```

---

## 1. Workflow YAML — `prototype_from_template`

### File location
`backend/agents/workflows/prototype_from_template/workflow.yaml`

### Catalog header
```yaml
id: prototype_from_template
version: 1
user_launchable: true
is_beta: false
name: Prototype from Template
display_name: "Prototype from Template"
short_name: Proto Template
icon: Layout
description: >
  Attach a requirements PDF, pick a template and design system, and receive a
  fully interactive prototype that matches the template's visual structure with
  your requirement content. Playwright validates every button and screen before delivery.
launch_surface: wizard
planner: skip
clarify:
  mode: skip
  defaults: []
deliverable:
  strategy: single_file
  name: prototype.html
context_providers:
  - opendesign
design_mode: web
limits:
  max_subagents: 50
  max_depth: 2
  wall_clock_seconds: 10800
```

### Step pipeline

```
req-reader ──► tmpl-analyzer ──► pb-adapt ──► pb-verify
```

All steps use `strategy: single_shot`. No wave fan-out (we're adapting ONE existing template, not building N screens in parallel). `pb-verify` has `tool_sets: [playwright]`.

---

### Step 1 — `req-reader` (Requirements Reader)

**Purpose:** Extract screens, flows, field definitions, business rules, and verbatim option codes from the uploaded PDF.

**Tools:**
```yaml
tools:
  read_files: true
  write_files: true
  exec: false
  tool_sets:
    - file_extract
```

**Prompt summary (key rules):**

Phase 1 — Read uploads
- `read_file .uploads/manifest.json`. If missing or empty, stop with `NO_UPLOADS:` error.
- For each non-image entry call `extract_text`.
- Skip any entry whose `type == "image"` or name ends `.png`/`.jpg`/`.jpeg`.

Phase 2 — Read shards
- Read each document's shard manifests to find all pages.
- Collect ALL facts: every field label, control type, dropdown option list (verbatim), table column, button text, screen name, business rule, example data value, and navigation action.
- Option codes are COPIED character for character — `CUST-REQ; MTR-FAIL; COMPLIANCE` stays exactly that.

Phase 3 — Write `build/requirements.json`
- Shape:
```json
{
  "screens": [
    {
      "id": "kebab-case-id",
      "name": "Screen Display Name",
      "reached_by": "action on previous screen",
      "fields": [
        { "label": "...", "control": "text|dropdown|date|checkbox|radio|table", "required": true, "options": ["..."] }
      ],
      "actions": [
        { "label": "Button Label", "outcome": "navigate|modal|state-change|validate" }
      ],
      "business_rules": ["..."],
      "example_values": { "field-label": "example value" }
    }
  ],
  "flows": [
    { "name": "Flow Name", "steps": ["screen-id-1", "screen-id-2"] }
  ],
  "entities": [
    { "name": "Entity Name", "attributes": ["..."] }
  ],
  "branding": {
    "product_name": "...",
    "primary_color_hint": "...",
    "domain": "..."
  }
}
```
- One `write_file` call. Verify it parses with `read_file`.

**Output file:** `build/requirements.json`

---

### Step 2 — `tmpl-analyzer` (Template Analyzer)

**Depends on:** `custom-agent:req-reader`

**Purpose:** Read the template structure and map template screens to requirement screens, producing an adaptation plan.

**Tools:**
```yaml
tools:
  read_files: true
  write_files: true
  exec: false
  tool_sets: []
```

**Context available:** The `opendesign` context provider injects:
- `.context/design/template/SKILL.md` — template capabilities, screen IDs, component rules, hard constraints
- `.context/design/template/example.html` — the complete worked example (the structural reference)
- `.context/design/template/assets/template.html` — the shell frame (when present)
- `.context/design/design-system.md` — design system tokens + guidelines
- `.context/design/tokens.css`, `.context/design/components.html` — (when present)

**Prompt summary (key rules):**

Phase 1 — Read context
- `read_file .context/design/template/SKILL.md` to its end.
- `read_file .context/design/template/example.html`. Note every `section.screen[id]` — these are the template's screen IDs.
- `read_file .context/selections.json` — confirms `template_id` and `ds_id`.
- `read_file build/requirements.json`.

Phase 2 — Extract template screen inventory
- List every `<section class="screen" id="...">` block found in example.html.
- For each template screen: record its id, heading, field count, key components, and navigation targets (`data-goto` references on its buttons).
- Note any hard rules from SKILL.md (e.g. button type rules, stepper constraints, dialog patterns).

Phase 3 — Map requirement screens to template screens
- For each requirement screen, find the best-matching template screen by: same purpose/domain (search → search, list → list, detail → workspace), similar field count, similar action types.
- Confidence: `"high"` (same purpose + similar structure), `"medium"` (similar structure, different purpose), `"new"` (no template equivalent — clone most similar template screen as base).
- Requirement screens with no template match: note which template screen pattern to clone.
- Template screens with no requirement match: mark `"remove": true` (but flag if removal would orphan navigation).

Phase 4 — Write output files
- `write_file build/screen-map.json`:
```json
{
  "template_id": "iberia-order-demo",
  "mapping": [
    {
      "requirement_screen": "order-entry",
      "template_screen": "journey-search",
      "confidence": "high",
      "notes": "Replace flight fields with order fields"
    }
  ],
  "new_screens": [
    {
      "requirement_screen": "review-summary",
      "clone_from": "review-payment",
      "notes": "No direct equivalent; clone review screen pattern"
    }
  ],
  "removed_screens": [
    {
      "template_screen": "baggage-selection",
      "reason": "No requirement screen maps to baggage selection"
    }
  ],
  "hard_rules": ["All buttons type=button", "Stepper must have 7 steps", "..."]
}
```
- `write_file build/adaptation-plan.md` — a human-readable plan describing each screen's changes, which template elements to keep, which to replace, and which fields/buttons to add/remove.

**Output files:** `build/screen-map.json`, `build/adaptation-plan.md`

---

### Step 3 — `pb-adapt` (Prototype Adapter / Builder)

**Depends on:** `custom-agent:tmpl-analyzer`

**Purpose:** Take the template's example.html as the structural base and produce `prototype.html` with all content replaced from the requirements, all interactions wired, and no external dependencies.

**Tools:**
```yaml
tools:
  read_files: true
  write_files: true
  exec: false
  tool_sets: []
skills:
  - template-content-editor
```

**Prompt summary (key rules):**

Phase 1 — Read
- `read_file .context/design/template/example.html` (page-by-page to the end).
- `read_file build/requirements.json`.
- `read_file build/screen-map.json`.
- `read_file build/adaptation-plan.md`.
- `read_file .context/design/design-system.md` + tokens.css (if present).

Phase 2 — Understand the template shell
- Identify: the shell navigation runtime (`data-goto` dispatcher), state management pattern, dialog system, stepper logic, localStorage key, utility functions available globally.
- Never call `route()`, `render()`, `progressTo()` from the template — they reference `<div id="app">` which does not exist in the assembled prototype.
- Utility functions that ARE safe: `persist()`, `defaultState()`, `EUR()`, `E()`, `toast()`, `showModal()`, `lines()` (when present).

Phase 3 — Build adapted screens
For each mapping entry in `build/screen-map.json`:
- **Keep:** the template screen's `<section class="screen" id="...">`, its stepper/sidebar chrome, layout containers, CSS classes.
- **Replace:** every piece of example content (product names, prices, dropdown options, field labels, table columns, button text, heading text) with the equivalent from `build/requirements.json`.
- **Remove:** template fields/sections that have no requirement equivalent.
- **Add:** requirement fields that have no template equivalent, using the closest template component pattern.
- For `"new"` screens: clone the template screen named in `clone_from`, then replace all content.
- For `"removed"` template screens: omit the `<section>` entirely. If `data-goto` attributes elsewhere pointed to it, redirect them to the closest remaining screen.

Phase 4 — Interactivity hard rules (apply to EVERY interactive element)

**Buttons (zero-tolerance)**
- Every `<button>` SHALL have `type="button"`. No `type="submit"`. No exceptions.
- Navigation: `<button type="button" data-goto="<screen-id>">`.
- Actions: `<button type="button" data-action="<action-name>">`.
- One SINGLE central click dispatcher handles all `data-goto` and `data-action` attributes. No inline `onclick` attributes anywhere in the file.
- Every `data-action` value SHALL have a corresponding `case` in the dispatcher switch. A missing case is a dead button.
- Forms: NEVER use `form.addEventListener('submit', ...)` or `<button type="submit">`. Read field values directly in the dispatcher's `data-action` handler.

**Navigation state updates**
- When the dispatcher processes `data-goto`, it SHALL also update visual state:
  - Stepper: set the clicked step to `class="step active" aria-current="step"`, set earlier steps to `class="step done"`, later steps to `class="step"`.
  - Sidebar: remove the active class from all sidebar items, add it to the clicked item.
  - Tabs: remove the active class from all tabs in the group, add it to the clicked tab; hide all panels in the group, show the clicked panel.

**Dropdowns**
- Every `<select>` SHALL have: `appearance: none; -webkit-appearance: none` and a custom SVG chevron as `background-image` in its CSS.
- Selecting an option SHALL fire any business-rule-driven state changes (dependent field visibility, sub-form update) via a `change` event listener wired in the inline script.

**Modals / dialogs**
- Use the native `<dialog>` element and `.showModal()` / `.close()`. Never a custom CSS overlay.
- Close triggers: the × button calls `.close()`; the backdrop click uses `dialog.addEventListener('click', e => { if (e.target === dialog) dialog.close(); })`.
- Every modal SHALL have exactly one `<button type="button">` close button with visible × or "Close" label.

**Accordions**
- Each accordion header is a `<button type="button" data-action="toggle-accordion-<id>">`.
- The dispatcher toggles a CSS class (`open`, `expanded`) on the parent container.
- CSS handles the expand/collapse animation (`max-height` or `display` transition).

**Tables**
- If the template shows row-click behaviour, rows SHALL have `data-action="select-row"` (or equivalent) and the dispatcher SHALL apply a `selected` CSS class.
- Hover state: use CSS `:hover` — no JS needed.

**Form validation**
- Required fields validate on blur and on the submit-equivalent `data-action` handler.
- Each field shows an inline `<span class="field-error">` beneath it. The span is hidden by default (CSS `display: none`) and shown when validation fails.
- Validation clears when the user corrects the value (input event listener removes error class and hides the span).

**Responsive layout**
- Every screen section SHALL include CSS media queries for 375 px and 768 px breakpoints.
- At 375 px: multi-column layouts collapse to single column (`flex-direction: column`); sidebars hide or stack above content; tables scroll horizontally inside a wrapper with `overflow-x: auto`.
- At 768 px: two-column layouts are preserved where the template shows them.
- No `width: Xpx` fixed widths on containers wider than the viewport.

**State persistence**
- `defaultState()` defines the initial shape of all persistent data.
- `persist()` is called after every state change that should survive a refresh.
- On load, `localStorage.getItem(STATE_KEY)` restores the previous state and navigates to the previously active screen.

**No external dependencies**
- No `<script src="https://...">`. No `<link href="https://...">` for fonts or icons.
- SVG icons are inline. Fonts are embedded via `@font-face` with base64 data URIs, OR the template's native font stack is used verbatim.

Phase 5 — Pre-write self-check (mandatory before writing prototype.html)

Run these checks BEFORE calling `write_file`:
1. Count all `data-goto` attribute values. Count all `section.screen[id]` elements. Every `data-goto` value must appear as a screen id. List any orphans and fix them now.
2. Count all `data-action` attribute values. Count all `case` branches in the central dispatcher. Every `data-action` value must have a case. List any missing cases and add them now.
3. Search the file text for `type="submit"`. Count must be zero. Fix any found.
4. Search for `addEventListener('submit'`. Count must be zero. Fix any found.
5. Search for `onclick=`. Count must be zero. Fix any found.
6. Search for `<script src=`. Count must be zero. Fix any found.
7. For each screen that has navigation elements (stepper, sidebar, tabs), confirm the dispatcher updates visual active/done state when navigating.
8. For each `<select>`, confirm a CSS rule sets `appearance: none; -webkit-appearance: none` and a `background-image` chevron.

If any check fails at pre-write, fix it before writing. Report the check results in the one-line reply.

Phase 6 — Write output
- `write_file prototype.html` (one call, the full assembled file).
- Reply with one line: screens adapted, new screens added, screens removed, total controls wired.

**Output file:** `prototype.html`

---

### Step 4 — `pb-verify` (Browser Validator + Repair Loop)

**Depends on:** `custom-agent:pb-adapt`

**Purpose:** Open `prototype.html` in a real browser, run an exhaustive audit of every interactive element across every screen, repair all failures found, and deliver a validation report. The repair loop runs up to **5 rounds**; the loop exits early only when a complete audit pass finds zero faults.

**Tools:**
```yaml
tools:
  read_files: true
  write_files: true
  exec: false
  tool_sets:
    - playwright
```

**Playwright tool set (available tools):**
- `playwright_navigate(path)` — opens a file (no leading slash). Call after every `edit_file` to reload.
- `playwright_snapshot()` — returns the page as a tree of elements with `ref` handles.
- `playwright_click(ref)` — clicks an element by its `ref`.
- `playwright_type(ref, text)` — types text into an element.
- `playwright_evaluate(js)` — runs JavaScript in the page. Key patterns below.
- `playwright_console_messages()` — returns JS console output. Any `Error`/`Uncaught` line is a fault.
- `playwright_take_screenshot(filename)` — writes a PNG file.

**Key `playwright_evaluate` patterns:**
```javascript
// Switch to a screen and read back the active id
window.__prototype.show("screen-id");
document.querySelector("section.screen.active").id

// Walk ALL data-goto buttons in one call; return orphaned ones
JSON.stringify(
  [...document.querySelectorAll("[data-goto]")].map(el => ({
    goto: el.dataset.goto,
    label: el.textContent.trim().slice(0,30),
    exists: !!document.getElementById(el.dataset.goto)
  })).filter(r => !r.exists)
)

// Walk ALL data-action buttons; return ones with no dispatcher case
// (inject a probe: override the dispatcher to log covered cases, then check)
JSON.stringify(
  [...document.querySelectorAll("[data-action]")].map(el => el.dataset.action)
    .filter((v,i,a) => a.indexOf(v) === i)  // unique values
)

// Check stepper active state on current screen
document.querySelector(".step.active")?.dataset.goto

// Check if a dialog is open
!!document.querySelector("dialog[open]")

// Check responsive overflow at width W
(function(w) {
  const prev = document.body.style.width;
  document.body.style.width = w + "px";
  const over = document.documentElement.scrollWidth > w;
  document.body.style.width = prev;
  return over;
})(375)

// Reload and restore state
window.location.reload()
// (then re-navigate after reload)
```

---

**Prompt summary:**

The agent works in two outer phases: **Audit** (Phase 1–2) and **Repair Loop** (Phase 3). The repair loop runs at most 5 rounds.

#### Phase 1 — Setup and Baseline

1. `read_file build/requirements.json` — extract all screen ids, all defined flows, all action types.
2. `read_file build/screen-map.json` — note the final list of screen ids present in the prototype.
3. `playwright_navigate("prototype.html")`.
4. `playwright_console_messages()` — record baseline errors (any `Error`/`Uncaught` are immediate faults).
5. `playwright_snapshot()` — confirm the entry screen is active; no dialogs open; stepper step 1 is active.

#### Phase 2 — Full Audit Checklist

Run ALL checks in order. Record every failure as a fault with: screen id, element description, expected behaviour, actual behaviour, fault severity (`critical` / `major` / `minor`).

- `critical`: dead button, broken screen navigation, JS crash, screen not reachable.
- `major`: wrong active state, modal won't close, form field missing, tab panel won't switch.
- `minor`: visual overflow, missing chevron on dropdown, wrong hover state.

**Check A — Initial load**
- Entry screen has `class="screen active"`.
- No `<dialog>` has `open` attribute.
- No `Error`/`Uncaught` in console.

**Check B — Screen reachability (exhaustive)**
For each screen id in `build/screen-map.json`:
- `playwright_evaluate("window.__prototype.show('<id>')")`.
- Confirm active screen id equals target.
- `playwright_console_messages()` — any new error after the show() call is a `critical` fault.

**Check C — Navigation buttons (exhaustive)**
Use `playwright_evaluate` to bulk-check: get all `[data-goto]` elements, compare their `dataset.goto` values against `document.getElementById(value)`. Every mismatch is `critical`.
Then for a sample of 5+ nav buttons per screen: `playwright_click(ref)`, measure the active screen id. Must equal the `data-goto` value.

**Check D — Action buttons (exhaustive)**
For each screen, `playwright_snapshot()`. For every element with `[data-action]`:
- `playwright_click(ref)`.
- Check for a visible outcome: modal with `open` attribute, DOM class change, new visible element, toast appearing.
- `playwright_console_messages()` — any error is `critical`.
- If no visible change AND no error → fault severity is `major` ("dead action").

**Check E — Stepper visual state**
For each consumer screen: `playwright_evaluate("window.__prototype.show('<id>')")`.
Confirm:
- The stepper button for this screen has `class` containing `active`.
- All stepper buttons for earlier screens have `class` containing `done`.
- All stepper buttons for later screens have neither `active` nor `done`.

**Check F — Sidebar / tab active state**
For backend/dashboard screens with a sidebar:
- Click each sidebar item.
- Confirm the clicked item has the active CSS class.
- Confirm the correct screen is shown.

For screens with tab groups:
- Click each tab.
- Confirm only the clicked tab has the active class.
- Confirm only the corresponding panel is visible (`display !== 'none'`).

**Check G — Accordions**
For each accordion header found in a `playwright_snapshot()`:
- `playwright_click(ref)` — confirm the accordion body becomes visible.
- `playwright_click(ref)` again — confirm the body is hidden.

**Check H — Modals / dialogs**
For each `[data-action]` that opens a modal:
- `playwright_click(ref)` — confirm `dialog[open]` exists.
- Click the × or Close button — confirm `dialog[open]` is gone.
- Reopen — click the backdrop — confirm `dialog[open]` is gone.
- Reopen — press Escape via `playwright_evaluate("document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}))")` — confirm `dialog[open]` is gone.

**Check I — Dropdowns**
`playwright_evaluate("JSON.stringify([...document.querySelectorAll('select')].map(s => ({ id: s.id, hasAppearanceNone: getComputedStyle(s).appearance === 'none' || getComputedStyle(s).webkitAppearance === 'none' })))")` — every select must return `true`.
For each select: `playwright_click(ref)`, `playwright_snapshot()` to confirm options are visible.

**Check J — Form validation**
For each screen with a form and required fields:
- Click the submit-equivalent `[data-action]` button WITHOUT filling in required fields.
- Confirm at least one `.field-error` or equivalent error element is now visible.
- Fill in a valid value, tab out — confirm the error disappears.

**Check K — LocalStorage persistence**
Navigate to a non-entry screen, then:
- `playwright_evaluate("window.location.reload()")`.
- After reload: `playwright_navigate("prototype.html")`.
- Confirm the active screen is the same one that was active before reload (localStorage restored).

**Check L — Console errors (full sweep)**
After checking every screen:
- `playwright_console_messages()`.
- Any line containing `Error`, `Uncaught`, `TypeError`, `ReferenceError`, `Cannot read` is a `critical` fault tagged with the screen it appeared on.

**Check M — Responsive layout (all three breakpoints)**
For each breakpoint (375, 768, 1280):
- `playwright_evaluate` with the overflow-check pattern above.
- Overflow at 375 is `major`. Overflow at 768 is `minor`. Overflow at 1280 is `minor`.

**Check N — Template CSS fidelity**
`playwright_evaluate("JSON.stringify({ primaryColor: getComputedStyle(document.documentElement).getPropertyValue('--primary') || getComputedStyle(document.documentElement).getPropertyValue('--color-primary'), keyClasses: [...document.querySelectorAll('[class]')].map(e=>e.className).join(' ') })")`.
Confirm the primary color value matches the design system token. Confirm at least 3 key CSS class names from the template's SKILL.md are present in the DOM.

---

#### Phase 3 — Repair Loop (up to 5 rounds)

Each round: apply all pending repairs → `playwright_navigate("prototype.html")` → re-run ALL Phase 2 checks → compare results. Exit early if zero faults. Enter round N+1 if faults remain.

**Priority order within a round:**
1. `critical` faults first (dead navigation, JS crash).
2. `major` faults second (broken modals, dead actions, broken tabs).
3. `minor` faults last (overflow, missing chevrons, missing hover styles).

**Repair playbook:**

| Fault type | Diagnosis | Fix |
|---|---|---|
| `data-goto` orphaned | screen id typo or missing `<section>` | Fix the id in the button, OR add a minimal `<section class="screen" id="...">` stub |
| `data-action` dead (no case) | Missing `case` in dispatcher switch | Add `case '<action>': { /* ... */ break; }` |
| `type="submit"` button | Build error | Change to `type="button"` + add `data-action` + dispatcher case |
| `form submit` listener | Build error | Remove listener; move field reads into dispatcher handler |
| Inline `onclick` | Build error | Remove attribute; add corresponding `data-action` case |
| Screen not showing on `show()` | CSS rule hiding section, or wrong id | Fix CSS `display` rule or fix the section id |
| Stepper not updating active/done | Dispatcher missing state update | Add stepper-update logic to navigation handler |
| Sidebar not highlighting | Dispatcher missing class update | Add `document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active')); clickedEl.classList.add('active')` |
| Tab not switching panel | Missing show/hide logic | Add panel show/hide to the tab-click dispatcher case |
| Accordion not toggling | Missing toggle logic | Add class toggle to accordion-header dispatcher case |
| Modal not closing on backdrop | Missing listener | Add `dialog.addEventListener('click', e => { if(e.target===dialog) dialog.close(); })` |
| Modal not closing on Escape | Missing listener | Add `dialog.addEventListener('keydown', e => { if(e.key==='Escape') dialog.close(); })` |
| Dialog using CSS overlay | Wrong pattern | Replace with `<dialog>` + `.showModal()` / `.close()` |
| Form validation not firing | Missing event listener | Add `blur`/submit-action handler with error-class toggle |
| Error not clearing | Missing input listener | Add `el.addEventListener('input', () => { el.classList.remove('error'); errorSpan.style.display='none'; })` |
| `<select>` no chevron | Missing CSS | Add `select { appearance:none; -webkit-appearance:none; background-image: url("data:image/svg+xml,..."); background-repeat:no-repeat; background-position: right 0.75rem center; }` |
| Horizontal overflow at 375 px | Missing media query | Add `@media(max-width:375px){ .container { flex-direction:column; max-width:100%; } }` |
| Table overflow at narrow width | Missing wrapper | Wrap `<table>` in `<div style="overflow-x:auto">` |
| JS console error on load | Undefined reference or missing function | Fix the reference; add a null guard `if(!el) return;` |
| LocalStorage not restoring | Missing restore logic on load | Add `const saved = JSON.parse(localStorage.getItem(STATE_KEY) || 'null'); if(saved?.activeScreen) window.__prototype.show(saved.activeScreen);` |
| No `window.__prototype.show` | Shell runtime not wired | Confirm the shell script block that defines `show()` is present before the closing `</body>` |

---

#### Phase 4 — Screenshots + Report

1. For every screen in `build/screen-map.json`:
   - `playwright_evaluate("window.__prototype.show('<id>')")`.
   - `playwright_take_screenshot(".verify/<id>.png")`.
2. Return to the entry screen. `playwright_take_screenshot(".verify/entry.png")`.
3. `write_file build/validation-report.md` with:

```markdown
# Prototype Validation Report

## Summary
| Metric | Value |
|---|---|
| Screens audited | N |
| Controls checked | N |
| Faults found (total) | N |
| — Critical | N |
| — Major | N |
| — Minor | N |
| Faults fixed | N |
| Faults still open | N |
| Repair rounds used | N / 5 |
| All critical faults resolved | YES / NO |

## Open Faults
| Screen | Element | Severity | Fault description | Attempted fix | Rounds tried |
|---|---|---|---|---|---|

## Fixed Faults  
| Screen | Element | Fault description | Fix applied |
|---|---|---|---|

## Screenshots
One entry per screen: `.verify/<screen-id>.png`
```

4. Reply with one line: screens audited, critical/major/minor faults found, faults fixed, faults open, rounds used.

---

## 2. Frontend — New Wizard Mode

### LaunchMode addition

Add `"prototype_from_template"` to the `LaunchMode` union type wherever it is defined (check `frontend/src/lib/launchDraft.ts` and `frontend/src/types/index.ts`).

### LaunchWizard.tsx — new step sequence

The existing wizard maps `launchMode` to an ordered list of steps. Add a new entry:

```typescript
// Existing entry (for reference):
// "prototype" → [STEP_TEMPLATE, STEP_DESIGN_SYSTEM, STEP_FIGMA, STEP_IDEA]

"prototype_from_template": [
  STEP_TEMPLATE,        // mandatory — TemplateGallery, prototype-mode filter only
  STEP_DESIGN_SYSTEM,   // required when template.design_system.requires === true
  STEP_REQUIREMENTS,    // NEW — RequirementsStep (PDF upload mandatory)
]
```

The final step in this mode is **Requirements** (not Idea). There is no freeform text prompt step; the requirements PDF IS the brief.

When launching in this mode the wizard builds the run payload with:
- `pipeline_type: "prototype_from_template"`
- `template_id`: from selected template
- `ds_id`: from selected design system
- The staged PDFs as run attachments (handled by existing `useStagedDocuments` + upload flow)

### TemplateGallery.tsx — mandatory selection + prototype filter

Two changes when `launchMode === "prototype_from_template"`:

1. **Filter:** Only show templates where the template metadata includes `od: { mode: "prototype" }`. The existing `/api/design-templates` endpoint returns `od.mode` in the summary; filter client-side.

2. **Mandatory:** The gallery already has a "selected" state. The `Next` button in this step's footer SHALL be disabled (`disabled={!selectedTemplate}`) when no template is chosen. Add a visible prompt ("Select a template to continue") when the user tries to advance without choosing.

### RequirementsStep.tsx — new component

**Location:** `frontend/src/components/workflow/prototype/RequirementsStep.tsx`

**Responsibilities:**
- Renders a PDF upload zone using the existing `useStagedDocuments` hook and `UploadChipStatus` component.
- Accept only `.pdf` files (pass `accept=".pdf"` to the file input; the existing `DOCUMENT_AND_IMAGE_ACCEPT` constant may need a pdf-only variant here).
- Shows staged file chips with status (uploading, ready, error) via `UploadChipStatus`.
- Disables the **Launch** button when no PDF is staged. The launch button is owned by the wizard's footer; this step exposes `isValid: boolean` to the wizard (a prop or callback).
- Renders a secondary optional `<textarea>` labelled "Additional context (optional)" for supplementary instructions.
- Shows an inline warning banner ("Attach at least one PDF to continue") when the user hovers or focuses the Launch button with no PDF attached.

**Props interface:**
```typescript
interface RequirementsStepProps {
  onValidityChange: (isValid: boolean) => void;
  additionalContext: string;
  onAdditionalContextChange: (text: string) => void;
}
```

**Key implementation notes:**
- Uses `useStagedDocuments` exactly as `IdeaInputPage` does — no new upload plumbing.
- `isValid = stagedUploads.some(u => u.status === "ready" && u.name.endsWith(".pdf"))`.
- On mount, call `onValidityChange(false)` so the wizard disables Launch immediately.
- When staged uploads change, re-evaluate and call `onValidityChange`.
- File drop zone: same `DragEvent` pattern used elsewhere in the wizard.

---

## 3. Context Provider — No Changes Needed

The `opendesign` context provider already injects:
- `.context/design/template/SKILL.md`
- `.context/design/template/example.html`
- `.context/design/template/assets/template.html`
- `.context/design/design-system.md`
- `.context/design/tokens.css`
- `.context/design/components.html`
- `.context/selections.json`

These are available to all steps in the workflow. No changes to the provider are required.

---

## 4. File Layout After Implementation

```
backend/agents/workflows/prototype_from_template/
└── workflow.yaml

frontend/src/components/workflow/prototype/
├── RequirementsStep.tsx           ← NEW
└── RequirementsStep.test.tsx      ← NEW

frontend/src/components/workflow/
└── LaunchWizard.tsx               ← MODIFIED
    (add "prototype_from_template" step sequence;
     wire RequirementsStep; pass isValid gate to footer)

frontend/src/components/workflow/prototype/
└── TemplateGallery.tsx            ← MODIFIED
    (add prototype-only filter + mandatory selection enforcement)

frontend/src/lib/
└── launchDraft.ts                 ← MODIFIED
    (add "prototype_from_template" to LaunchMode union)
```

---

## 5. Playwright Tool Set — Integration Notes

The `playwright` tool set is already registered and used by `prototype_v2_revision` and `prototype_v2_feature_revision`. The `pb-verify` step uses it identically. No new tool registration is required.

Key `playwright_evaluate` patterns used in the verify step:
```javascript
// Switch to a screen
window.__prototype.show("screen-id")

// Read the active screen
document.querySelector("section.screen.active").id

// Walk all data-goto buttons and return failures
JSON.stringify(
  [...document.querySelectorAll("[data-goto]")].map(el => ({
    goto: el.dataset.goto,
    exists: !!document.getElementById(el.dataset.goto)
  })).filter(r => !r.exists)
)

// Check for horizontal overflow at a given width
(function(w) {
  document.body.style.width = w + "px";
  const overflow = document.documentElement.scrollWidth > w;
  document.body.style.width = "";
  return overflow;
})(375)
```

---

## 6. Workflow Run Flow (End-to-End)

```
User in wizard
  → selects template (TemplateGallery, prototype-only, mandatory)
  → selects design system (DesignSystemPicker, required per template)
  → attaches PDF + optional text (RequirementsStep, PDF mandatory)
  → clicks Launch

opendesign context provider injects template + DS files into .context/design/
Upload pipeline stages PDF into .uploads/

req-reader
  extract_text(.uploads/*.pdf) → build/requirements.json

tmpl-analyzer
  read template/SKILL.md + example.html
  read build/requirements.json
  → build/screen-map.json + build/adaptation-plan.md

pb-adapt
  read example.html + requirements + screen-map + design system
  write prototype.html (template structure, requirement content, all buttons wired)

pb-verify  [playwright tool set]
  playwright_navigate("prototype.html")
  Audit checklist (14 check categories, every element, every screen)
  Repair loop (max 5 rounds, exit early when zero faults):
    → edit_file patches → playwright_navigate → re-audit
  playwright_take_screenshot(".verify/<screen-id>.png") for every screen
  write build/validation-report.md

Deliverable: prototype.html (strategy: single_file)
Artifacts:   build/validation-report.md + .verify/*.png screenshots
```
