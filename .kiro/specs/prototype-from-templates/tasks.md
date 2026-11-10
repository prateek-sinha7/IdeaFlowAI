# Prototype from Templates — Implementation Tasks

## Prerequisites

Before starting, prime the session with `/velocity prime` and read:
- `backend/agents/workflows/prototype_v2/workflow.yaml` — reference for step prompt patterns, tool declarations, and gate syntax
- `backend/agents/workflows/prototype_v2_revision/workflow.yaml` — reference for the `playwright` tool set and the repair-loop prompt pattern
- `frontend/src/components/workflow/LaunchWizard.tsx` — understand the existing wizard mode/step structure
- `frontend/src/components/workflow/prototype/TemplateGallery.tsx` — understand how templates are listed/selected
- `frontend/src/lib/launchDraft.ts` — locate the `LaunchMode` type

---

## Group 1 — Workflow YAML

### T1.1 Create the workflow directory and skeleton YAML
- Create `backend/agents/workflows/prototype_from_template/workflow.yaml`.
- Add the catalog header exactly as specified in `design.md §1`: `id`, `version`, `user_launchable`, `display_name`, `launch_surface: wizard`, `planner: skip`, `clarify`, `deliverable` (`single_file`, `prototype.html`), `context_providers: [opendesign]`, `design_mode: web`, `limits`.
- Add four empty `single_shot` step stubs with the correct `instance_id` values (`req-reader`, `tmpl-analyzer`, `pb-adapt`, `pb-verify`) and their `depends_on` chain.
- Verify `backend/agents/workflows/manifest.py` discovers workflows by directory scan (read it if unsure); confirm no explicit registration step is needed.

**Done when:** `cat backend/agents/workflows/prototype_from_template/workflow.yaml` prints a valid YAML file; the manifest compilation test passes (`pytest tests/agents/test_manifest_coverage.py -q`).

---

### T1.2 Write the `req-reader` step prompt
- Implement the full 3-phase prompt as specified in `design.md §1 — Step 1`.
- Phase 1: read `.uploads/manifest.json`; return `NO_UPLOADS:` error if missing.
- Phase 2: `extract_text` on each non-image entry; collect fields, options (verbatim), screen names, rules, example values.
- Phase 3: `write_file build/requirements.json` in the shape defined in design.md.
- Add `tool_sets: [file_extract]` under `tools`.
- Mirror the "one write_file call, then verify it parses" discipline from `fi-planner` in `prototype_v2`.

**Done when:** Prompt is in the YAML and the manifest coverage test still passes.

---

### T1.3 Write the `tmpl-analyzer` step prompt
- Implement the full 4-phase prompt as specified in `design.md §1 — Step 2`.
- Phase 1: read template SKILL.md + example.html + `selections.json` + `build/requirements.json`.
- Phase 2: extract template screen inventory from `<section class="screen" id="...">` elements.
- Phase 3: map requirement screens to template screens; assign confidence; identify `"new"` and `"remove"` entries.
- Phase 4: `write_file build/screen-map.json` (shape as designed) and `write_file build/adaptation-plan.md`.
- No external tool sets needed — plain `read_files + write_files`.
- The agent reads example.html as a large text file; include the paging reminder ("keep calling with next offset until a short/empty page comes back").

**Done when:** Prompt is in the YAML.

---

### T1.4 Write the `pb-adapt` step prompt
- Implement the full 6-phase prompt as specified in `design.md §1 — Step 3`.
- Phase 1: read example.html (paged), requirements.json, screen-map.json, adaptation-plan.md, design-system.md + tokens.css.
- Phase 2: identify the shell's routing runtime, utility functions, localStorage key. State which functions are safe to call vs forbidden (`route()`, `render()`, `progressTo()`).
- Phase 3: build each adapted screen per the mapping; follow the content-replacement rules for keep/replace/remove/add.
- Phase 4: apply interactivity hard rules — every button `type="button"`, central dispatcher, no form submit, `<dialog>` modals, localStorage state, no external dependencies.
- Phase 5: pre-write self-check — walk all `data-goto` and `data-action` values.
- Phase 6: `write_file prototype.html`.
- Add `skills: [template-content-editor]` to the step.
- Add the NEVER-read-whole-file reminder: use grep + offset reads for large files.

**Done when:** Prompt is in the YAML.

---

### T1.5 Write the `pb-verify` step prompt
- Implement the full audit + repair-loop prompt as specified in `design.md §1 — Step 4`.
- Phase 1: setup + baseline console check.
- Phase 2: all 14 audit checks (A through N) in order — screen reachability, navigation buttons, action buttons, stepper state, sidebar/tab active state, accordions, modals (including Escape and backdrop), dropdowns, form validation, localStorage restore, console sweep, responsive at 3 widths, template CSS fidelity.
- Phase 3: repair loop — 5 rounds max, exit early on zero faults; use the full fault-type repair table from design.md; repair critical faults first.
- Phase 4: screenshot every screen to `.verify/<id>.png`; write `build/validation-report.md` with the full table format.
- Add `tool_sets: [playwright]` and `exec: false`.
- Include the NEVER-read-whole-file rule; use grep + offset for large file reads.
- Note: use `edit_file` (not `write_file`) for all repair patches — surgical changes only.

**Done when:** Prompt is in the YAML; all four steps have correct `depends_on` chains.

---

### T1.6 Validate the compiled workflow
Run the manifest coverage test and the banned-patterns test:
```bash
cd backend
uv run pytest tests/agents/test_manifest_coverage.py tests/agents/test_banned_patterns.py -q
```
Fix any compilation errors (unknown capability names, malformed step fields, etc.).

Also grep the new YAML for accidental SC-001 violations:
```bash
grep -n "if pipeline_type ==" backend/agents/workflows/prototype_from_template/workflow.yaml
grep -n 'spec\.id ==' backend/agents/workflows/prototype_from_template/workflow.yaml
```
Both must return 0 matches.

**Done when:** Both pytest commands pass; both greps return 0 matches.

---

## Group 2 — Frontend: Type and LaunchDraft

### T2.1 Add `"prototype_from_template"` to the `LaunchMode` type
- Locate the `LaunchMode` type definition (likely `frontend/src/lib/launchDraft.ts` or `frontend/src/types/index.ts` — read both to confirm).
- Add `"prototype_from_template"` to the union.
- Run `npm run build` from `frontend/` to confirm the addition compiles cleanly.

**Done when:** `npm run build` exits 0.

---

## Group 3 — Frontend: RequirementsStep Component

### T3.1 Create `RequirementsStep.tsx`
- Location: `frontend/src/components/workflow/prototype/RequirementsStep.tsx`.
- Implement the component as specified in `design.md §2 — RequirementsStep.tsx`.
- Use `useStagedDocuments` (same as `IdeaInputPage`) for upload management.
- Use `UploadChipStatus` to render staged-file chips.
- The drag-and-drop zone and file input accept only `.pdf`.
- `isValid` is `true` when at least one staged upload has `status === "ready"` and filename ends with `.pdf`; call `onValidityChange` on every upload-state change.
- Render an optional `<textarea>` for additional context.
- Show a warning banner ("Attach at least one PDF requirements document to continue") when `!isValid` and the user has interacted with the step (not on first render).

### T3.2 Create `RequirementsStep.test.tsx`
Write unit tests covering:
- Renders the upload zone and optional textarea.
- `onValidityChange(false)` is called on mount (no files yet).
- Simulates staging a `.pdf` file → `onValidityChange(true)` is called.
- Simulates staging a `.docx` file → upload is rejected or `isValid` stays false.
- Warning banner is hidden on initial render; appears after user interacts and no PDF is staged.
- Additional context textarea fires `onAdditionalContextChange` on input.

**Done when:** `npm run test -- --run RequirementsStep` passes all tests.

---

## Group 4 — Frontend: LaunchWizard Integration

### T4.1 Add the `prototype_from_template` step sequence to `LaunchWizard.tsx`
- Read the existing step sequence definitions in `LaunchWizard.tsx` (how `prototype`, `ppt` etc. are wired).
- Add a new sequence entry for `"prototype_from_template"`:
  ```
  STEP_TEMPLATE → STEP_DESIGN_SYSTEM → STEP_REQUIREMENTS
  ```
- `STEP_REQUIREMENTS` is a new constant referencing `RequirementsStep`.
- Import `RequirementsStep` and add it to the wizard's step renderer switch/if chain.
- Wire `onValidityChange` to the wizard's footer `isNextDisabled` / `isLaunchDisabled` state for the Requirements step.
- Pass `additionalContext` value into the run brief when building the launch payload alongside the staged PDFs.

### T4.2 Enforce mandatory template selection in this mode
- In the Template step's footer (the `Next` button logic), when `launchMode === "prototype_from_template"` AND no template is selected, keep `Next` disabled.
- Add a visible hint text below the gallery ("Select a template to continue") that appears only when the user attempts to advance without a selection (existing pattern: check how the design system step does it).

### T4.3 Apply prototype-only filter to `TemplateGallery`
- In `TemplateGallery.tsx`, accept a new optional prop `filterMode?: "prototype" | "all"` (or use `launchMode` if it is already threaded through).
- When `filterMode === "prototype"`, filter the templates array to only entries where `template.od?.mode === "prototype"`.
- The existing `/api/design-templates` response includes the `od` field in the summary object (confirmed by `AGENTS.md`); filter client-side.
- Add a test in `TemplateGallery.reskin.test.tsx` (or a new file) confirming the filter works.

### T4.4 Build the correct launch payload
- When `launchMode === "prototype_from_template"`:
  - `pipeline_type` in the run-create payload must be `"prototype_from_template"`.
  - The selected template and design system IDs must be included (same as the existing `prototype` mode path).
  - The staged PDFs are included as run attachments (same path as existing document uploads).
  - The `additionalContext` text from the Requirements step is appended to the user brief if non-empty.

**Done when:** `npm run build` exits 0; `npm run lint` exits 0.

---

## Group 5 — Validation

### T5.1 Run the full frontend test suite
```bash
cd frontend
npm run test -- --run
```
Fix any regressions introduced by the LaunchWizard or TemplateGallery changes. Focus on:
- `LaunchWizard.test.tsx` and its sibling test files — none should regress.
- `TemplateGallery.reskin.test.tsx` — filter behavior must be covered.

### T5.2 Run the backend test suite
```bash
cd backend
uv run pytest tests/agents/ -q
```
Confirm:
- `test_manifest_coverage.py` — new workflow compiles cleanly.
- `test_banned_patterns.py` (11 tests) — all still pass.
- `test_sse_cutover_banned_patterns.py` — no regressions.
- Characterization golden tests (if `SNAPSHOT_UPDATE` is unset) — output unchanged.

### T5.3 Manual smoke test (developer verification)
With a local stack running:
1. Open the app and start a new workflow.
2. Confirm `"Prototype from Template"` appears in the workflow catalog.
3. Launch the wizard in `prototype_from_template` mode.
4. Confirm the Template step shows only `od.mode === "prototype"` templates.
5. Confirm **Next** stays disabled until a template is selected.
6. Confirm the Design System step pre-selects the recommended DS when the template has one.
7. Confirm the Requirements step shows the PDF upload zone.
8. Confirm **Launch** stays disabled until a PDF is staged.
9. Attach a PDF → confirm **Launch** becomes active.
10. Launch the run. Confirm the four steps execute in order in the run results panel.
11. Confirm `prototype.html` appears in the deliverables section.
12. Open `prototype.html` in a browser. Confirm it loads, screens are reachable, no dead buttons.
13. Check the run results for `build/validation-report.md`.

---

## Completion Checklist

- [ ] `backend/agents/workflows/prototype_from_template/workflow.yaml` created with all 4 steps
- [ ] `test_manifest_coverage.py` passes
- [ ] `test_banned_patterns.py` (11 tests) passes
- [ ] SC-001 grep checks return 0 matches
- [ ] `frontend/src/lib/launchDraft.ts` (or types) updated with new LaunchMode value
- [ ] `RequirementsStep.tsx` created and tested
- [ ] `LaunchWizard.tsx` updated with new step sequence
- [ ] `TemplateGallery.tsx` updated with prototype-only filter + mandatory selection
- [ ] Launch payload includes `pipeline_type: "prototype_from_template"`
- [ ] `npm run build` exits 0
- [ ] `npm run lint` exits 0
- [ ] Frontend test suite passes (`npm run test -- --run`)
- [ ] Backend agent tests pass
- [ ] Manual smoke test confirmed
