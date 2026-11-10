# Prototype from Templates — Requirements

## Overview

A new workflow that turns a requirements PDF into a fully interactive, visually faithful prototype. The user selects a template (which becomes the structural skeleton) and a design system, attaches their requirements document, and receives a standalone `prototype.html` whose screens, labels, fields, and business content are sourced from the PDF while the template's layout, navigation, CSS, and component patterns are preserved exactly.

**Zero-tolerance policy for broken interactions:** every visible control in the delivered prototype — every button, tab, dropdown, link, stepper step, sidebar item, accordion, modal trigger, form field — must produce a correct, visible outcome when activated. A control that does nothing is a defect. The workflow uses the built-in `playwright` tool set in a multi-pass repair loop (up to 5 rounds) and SHALL NOT stop until all critical faults are resolved or the maximum rounds are exhausted.

---

## Functional Requirements

### FR-1 — Requirements Document Input

**FR-1.1** The launch wizard SHALL provide a dedicated Requirements step where the user attaches one or more PDF files containing the product requirements.

**FR-1.2** Attaching at least one PDF SHALL be mandatory: the wizard's **Launch** button SHALL remain disabled and visually dimmed until a PDF is staged.

**FR-1.3** The requirements step SHALL accept any PDF up to the existing upload size limit, surfacing the existing upload-too-large error message when the limit is exceeded.

**FR-1.4** A short optional text area SHALL be available for additional context (clarifications, brand name, specific data values); it is NOT a substitute for the PDF.

**FR-1.5** The workflow SHALL use `extract_text` to read the PDF and produce `build/requirements.json` capturing: screens, user flows, field definitions, dropdown options (verbatim, not paraphrased), business rules, and example data values found in the document.

**FR-1.6** If the PDF cannot be parsed or produces an empty extraction, the workflow SHALL terminate early with a clear error rather than continuing to the adaptation step.

---

### FR-2 — Template Selection

**FR-2.1** The wizard SHALL require the user to select exactly one template from the design-templates catalog before launching.

**FR-2.2** When the workflow is `prototype_from_template`, the TemplateGallery SHALL filter to show only templates where `od.mode == "prototype"` in the template's SKILL.md front-matter.

**FR-2.3** Template selection SHALL be mandatory: the wizard SHALL not advance past the Template step without a selection, and the **Next** button SHALL remain disabled until one is chosen.

**FR-2.4** The user SHALL be able to preview the selected template's `example.html` before confirming.

**FR-2.5** The workflow SHALL receive the selected template at `.context/design/template/` (SKILL.md, example.html, and any assets), delivered by the existing `opendesign` context provider. No new API is required.

---

### FR-3 — Design System Selection

**FR-3.1** The wizard SHALL require the user to select a design system before launching when the chosen template's SKILL.md has `design_system.requires: true`.

**FR-3.2** If the template's SKILL.md carries a `design_system.recommended` value, that design system SHALL be pre-selected in the DesignSystemPicker.

**FR-3.3** The workflow SHALL receive the selected design system's tokens, component markup, and guidelines at `.context/design/design-system.md`, `tokens.css`, and `components.html` (when present), delivered by the same `opendesign` context provider.

---

### FR-4 — Template Adaptation (Content Replacement)

**FR-4.1** The workflow SHALL preserve the selected template's complete HTML structure, CSS classes, layout rules, navigation chrome, color tokens, and component patterns. It SHALL NOT rebuild the template from scratch. A user who has seen the selected template's `example.html` SHALL immediately recognize the prototype as the same design.

**FR-4.2** The adaptation agent SHALL replace every placeholder, fictional, or example value (names, prices, codes, labels, dropdown options, table headings) in the template with content derived from `build/requirements.json`. No example/demo content from the original template SHALL survive in the delivered prototype.

**FR-4.3** Where the requirements document specifies screens that correspond to template screens, the mapping SHALL be recorded in `build/screen-map.json` before building begins.

**FR-4.4** Where the requirements document specifies screens that have no equivalent in the template, the adaptation agent SHALL clone the most structurally similar template screen as a starting pattern, relabeling it completely from the requirements. The cloned screen SHALL use the same CSS classes, layout containers, and component markup as the template original — it SHALL look like it belongs to the same design.

**FR-4.5** Template screens that have no corresponding requirement screen SHALL be removed from the output prototype; if removal would break a navigation flow, the agent SHALL create a minimal placeholder screen that preserves routing integrity.

**FR-4.6** All field labels, dropdown option lists, table column headers, button text, and error messages SHALL be taken verbatim from the requirements document, preserving exact casing, punctuation, and codes (e.g. `CUST-REQ; MTR-FAIL; COMPLIANCE` is never normalized).

**FR-4.7** The delivered `prototype.html` SHALL be a single self-contained file with no external runtime dependencies. All CSS, JavaScript, and any inline assets SHALL be embedded.

**FR-4.8** The template's color scheme (primary color, background, text, border, status colors), typography scale (font family, sizes, weights), spacing scale, and border-radius values SHALL be preserved unchanged. The design system tokens provided at `.context/design/tokens.css` SHALL be applied; no ad-hoc color values SHALL be introduced.

**FR-4.9** Every component pattern present in the selected template (steppers, data tables, status badges, cards, sidebars, modals, toast notifications, tabs, accordions) SHALL appear in the prototype wherever the requirements call for that type of component. The template's existing HTML markup for each component SHALL be reused, not re-implemented.

---

### FR-5 — Interactivity Rules (Zero Dead Controls)

**FR-5.1** Every visible button in the prototype SHALL be clickable (`type="button"`) and SHALL produce a clearly visible, defined outcome. A button that does nothing when clicked is a blocking defect. Permitted outcomes: navigation to another screen, opening a modal/dialog, a state change on the current screen (row selection, filter active, toggle on/off), inline form-validation feedback, a toast notification. A button with none of these outcomes is not permitted in the final deliverable.

**FR-5.2** No button SHALL use `type="submit"` or rely on a `<form>` submit event for navigation. All navigation buttons SHALL carry `data-goto="<screen-id>"` and all action buttons SHALL carry `data-action="<action-name>"`, handled by a single central click dispatcher.

**FR-5.3** Every navigation element SHALL change the active screen and update its own visual state:
- Stepper steps: clicking any step navigates to that screen AND marks the clicked step active, marks earlier steps done.
- Sidebar links: clicking a link shows that screen AND applies an active highlight to the clicked link.
- Tabs: clicking a tab shows its panel AND applies the active/selected class to the tab.
- Breadcrumb links: clicking navigates to the named screen.
- Back / Next / Cancel buttons: navigate as labelled.

**FR-5.4** Every dropdown (`<select>` element) SHALL:
- Have `appearance: none; -webkit-appearance: none` and a custom SVG chevron rendered via CSS `background-image`.
- Show all options exactly as specified in the requirements document.
- Reflect its selected value visually after a selection is made.
- Trigger any dependent state change defined by a business rule (e.g. selecting a type updates a sub-form).

**FR-5.5** Every form field SHALL:
- Accept keyboard input.
- Show an inline error message (below or beside the field) when left blank while required, or when input violates a documented rule (format, range, allowed value).
- Clear the error when the user corrects the value.
- Show a disabled state (dimmed, not focusable) when the field is not applicable under current conditions.

**FR-5.6** Every modal / dialog SHALL:
- Open when its trigger button is clicked (`<dialog>.showModal()`).
- Be closable via: (a) the close/× button, (b) clicking the backdrop outside the dialog, (c) pressing Escape.
- Trap focus inside while open.
- Return focus to the triggering element on close.

**FR-5.7** Every accordion / expandable section SHALL:
- Expand to show its content when its header/toggle is clicked.
- Collapse when clicked again, or when another accordion opens (if the template uses single-open behaviour).
- Show the expanded/collapsed state visually (chevron rotation, background change) as the template does.

**FR-5.8** Every table with interactive rows SHALL:
- Highlight a row on hover.
- Show a selected state when a row is clicked (background change or checkbox tick).
- If the template shows a "click row to open detail" pattern, clicking the row SHALL navigate to the detail screen or open the detail panel.

**FR-5.9** Every tab group SHALL show exactly one active panel at a time. Clicking an inactive tab SHALL switch the visible panel and update the tab's active CSS class.

**FR-5.10** The prototype SHALL be responsive at three breakpoints:
- **375 px** (mobile): single-column layout; navigation collapses to a hamburger or is hidden; no horizontal scroll.
- **768 px** (tablet): two-column or stacked layout as the template specifies; all controls reachable.
- **1280 px** (desktop): full template layout; all columns and sidebars visible.
At every breakpoint all controls remain clickable and all text remains readable (no overflow-hidden text, no overlapping elements).

**FR-5.11** All state that must persist across page refreshes SHALL be stored in `localStorage` under a versioned key. After a browser refresh, the user should see the same screen and data they left.

**FR-5.12** All JavaScript SHALL be inline inside `<script>` tags. No `<script src="https://...">` or external CDN references. The file must open and function with no internet connection.

**FR-5.13** The prototype SHALL show no JavaScript console errors on initial load or during normal navigation. `Uncaught`, `TypeError`, `ReferenceError`, and `Cannot read properties of undefined` errors are blocking defects.

---

### FR-6 — Playwright Validation Loop

**FR-6.1** A dedicated verification step SHALL open `prototype.html` in a real browser via `playwright_navigate("prototype.html")` and execute a comprehensive audit before delivery.

**FR-6.2** The verification step SHALL audit every one of the following — this is not a sample check, it is exhaustive:

| Check category | What is verified |
|---|---|
| Initial load | Entry screen is active; no dialogs open; no JS console errors |
| Screen reachability | Every `data-goto` attribute resolves to an existing `section.screen[id]` |
| Navigation buttons | Every `[data-goto]` button click lands on the correct screen |
| Action buttons | Every `[data-action]` button produces a visible outcome; no JS errors |
| Stepper state | After navigating to screen N, stepper step N is active, steps < N are marked done |
| Sidebar/tabs active state | Clicking a nav item applies the active CSS class AND shows the correct screen |
| Tab panels | Clicking each tab shows its panel; only one panel is visible at a time |
| Accordions | Clicking an accordion header toggles its body; collapsed sections are hidden |
| Dropdowns | Each `<select>` renders a custom chevron; selecting an option updates displayed value |
| Table row interactions | Clicking a row applies a selected/highlighted state |
| Modals | Every modal trigger opens the `<dialog>`; × button, backdrop click, and Escape all close it |
| Form validation | Required fields show inline error on submit/blur when empty; error clears on valid input |
| LocalStorage | After `location.reload()`, the previously active screen and its data are restored |
| Console errors | `playwright_console_messages()` returns no `Error` / `Uncaught` lines on any screen |
| Responsive — 375 px | `document.documentElement.scrollWidth <= 375`; no overlapping elements |
| Responsive — 768 px | `document.documentElement.scrollWidth <= 768`; all controls reachable |
| Responsive — 1280 px | Full layout visible; all columns and sidebars present |
| Template CSS fidelity | Primary color variable matches the template's; key CSS class names from SKILL.md are present in the DOM |

**FR-6.3** When any audit check fails, the verification step SHALL immediately attempt to repair it in-place using `edit_file` (never `write_file`, to preserve unchanged sections). The repair-then-verify cycle SHALL run up to **5 rounds**.

**FR-6.4** A round is one full pass of the entire audit checklist. A round ends only when every item has been re-checked after repairs. Partial passes are not rounds.

**FR-6.5** The loop SHALL exit early (before round 5) only when a complete audit pass finds **zero faults**.

**FR-6.6** Critical faults (dead `data-goto` button, broken screen navigation, JS crash on load) SHALL be prioritised in every repair round. The repair agent SHALL fix all critical faults before attempting cosmetic or responsive fixes.

**FR-6.7** After the repair loop, the verification step SHALL write `build/validation-report.md` with: summary table, per-screen pass/fail, list of fixed faults with the exact `edit_file` change applied, and list of open faults with root cause.

**FR-6.8** The verification step SHALL take a screenshot of every screen via `playwright_take_screenshot` and save them to `.verify/<screen-id>.png`.

**FR-6.9** The workflow SHALL deliver `prototype.html` as the primary deliverable regardless of whether all faults were resolved. If open faults remain after 5 rounds, the run results panel SHALL surface the open-fault list and screenshots from `build/validation-report.md` so the user knows what is unresolved.

---

### FR-7 — Output

**FR-7.1** The primary deliverable SHALL be `prototype.html` — a single standalone HTML file, strategy `single_file`.

**FR-7.2** `prototype.html` SHALL open correctly in any modern browser without a build step or local server (file:// protocol).

**FR-7.3** The run result SHALL also surface `build/validation-report.md` summarising the Playwright audit outcome.

---

## Non-Functional Requirements

**NFR-1** Total wall-clock time from launch to delivery SHALL not exceed 3 hours (`wall_clock_seconds: 10800`).

**NFR-2** The workflow SHALL comply with SC-001: no `if pipeline_type ==` or `spec.id ==` checks inside `engine.py`. The new workflow YAML drives everything via the manifest.

**NFR-3** The workflow SHALL be registered purely by creating `backend/agents/workflows/prototype_from_template/workflow.yaml`. No changes to `selections.py`, `engine.py`, or `manifest.py` are required for registration.

**NFR-4** The frontend wizard change SHALL use the existing `LaunchWizard.tsx`, `TemplateGallery.tsx`, and `DesignSystemPicker.tsx` components. New UI is limited to the Requirements input step.

**NFR-5** The new wizard mode SHALL not affect the existing `prototype_v2` launch flow.
