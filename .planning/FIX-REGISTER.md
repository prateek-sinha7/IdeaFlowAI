# Fix Register — VelocityAI / Flowin

> **Purpose.** Every fix applied via `/velocity-ai-fix` is logged here. Read this alongside the Implementation Register before applying any new fix — to avoid re-fixing something already fixed, and to understand the cumulative patch history on top of the planned phases.
>
> **Format per entry:** Date · Fix ID · Root cause · Files changed · Phase(s) involved · Invariants verified · Notes.

---

## Fix Log

| Fix ID | Date | Description | Root Cause | Files Changed | Phase Involved | Invariants | Status |
|--------|------|-------------|------------|---------------|---------------|------------|--------|
| FIX-001 | 2026-06-16 | Harden od-ppt-validator output contract (remove checklist-as-preamble loophole) + fix od-ppt-composer filesystem tool calls on Windows | Validator: "two short sentences" loophole allowed model to print full checklist as preamble without `<artifact>` wrapper → raw checklist rendered as deck. Composer: deepagents filesystem glob crashes on Windows (pathlib.rglob ValueError) → composer told to use context-injected files instead of tool calls | `backend/agents/prompts/od-ppt-validator/AGENT.md`, `backend/agents/prompts/od-ppt-composer/AGENT.md` | Phase 15 | INV-1/3/12/SC-001 ✅ | Done |
| FIX-002 | 2026-06-16 | Vellum template not applied — example.html not injected into PPT composer context | opendesign provider `is_builder` gate used `{"prototype_emit_only", "prototype"}` set; `workspace` tool set excluded so PPT composer never received `example.html`; SKILL.md workflow says "clone example.html" but agent had no copy | `backend/agents/capabilities/context_providers/opendesign.py` | Phase 7 | INV-1/3/12/SC-001 ✅ | Done |
| FIX-003 | 2026-06-16 | PPT/Prototype wizard hides brief textarea — stale `chain.from` in sessionStorage | `chain.from` was never removed from sessionStorage after previous chained run; on fresh wizard open the page read it, set `isChaining=true`, and hid the brief textarea and showed "CHAINED PRESENTATION · STEP 1 OF 1" | `frontend/src/app/workflow/ppt/templates/page.tsx`, `frontend/src/app/workflow/prototype/templates/page.tsx` | Phase 21 | INV-1/3/12/SC-001 ✅ | Done |
| FIX-004 | 2026-06-15 | Delete pipeline from history does nothing — FK constraint on 9 child tables + silent frontend error | `delete_run` called `db.delete(workflow_run); db.commit()` directly; 9 child tables (run_events, artifact_refs, workflow_clarifications, gate_events, hook_runs, exec_runs, run_capabilities, subagent_runs, wave_runs) all FK into workflow_runs.id with no CASCADE; PRAGMA foreign_keys=ON blocked the DELETE → IntegrityError 500. Frontend `catch {}` swallowed the error silently | `backend/app/api/runs.py`, `frontend/src/components/history/WorkflowHistory.tsx` | Phases 4/5/8/9/11/12 | INV-1/3/12/SC-001 ✅ | Done |
| FIX-005 | 2026-06-16 | Prototype (and PPT) wizard pre-fills stale brief from previous run — draft never cleared | `prototype.draft` / `ppt.draft` written by wizard handleContinue but never deleted after dashboard consumes the pending run; on every fresh wizard open the draft restore useEffect reads the stale key and pre-fills the brief/template/DS from the last run | `frontend/src/app/dashboard/page.tsx` | Phase 21 | INV-1/3/12/SC-001 ✅ | Done |
| FIX-006 | 2026-06-16 | prototype-specify and prototype-plan produce empty output — max_tokens: 8000 too small | Both agents declared max_tokens: 8000; the spec writer is asked to produce a dense multi-page spec with tables, DS tokens, nav flows (4-6+ pages) that routinely exceeds 8000 tokens on Haiku 4.5 → model returns empty output → review_gate_ready has output="" → "No content was produced for review" | `backend/agents/prompts/prototype-specify/AGENT.md`, `backend/agents/prompts/prototype-plan/AGENT.md` | Phase 15 | INV-1/3/12/SC-001 ✅ | Done |
| FIX-007 | 2026-06-16 | Prototype pipeline fails with ModuleNotFoundError: No module named 'resource' | `local.py` does `import resource` at module level; `resource` is Unix-only, unavailable on Windows; `sandbox._ws()` lazily imports local.py on every `sandbox.read()`/`sandbox.write()` call; task_loop calls both → crashes and kills the build agent | `backend/app/agents/runtime/local.py` | Phase 9 | INV-1/3/12/SC-001 ✅ | Done |
| FIX-008 | 2026-06-16 | Spec Writer asks clarifying questions instead of producing spec — entire pipeline produces empty output | `prototype-specify` and `prototype-plan` AGENT.md had no explicit "never ask clarifying questions" rule; on an ambiguous brief (e.g. "GitHub dashboard") Haiku writes a question instead of a `<spec>` document; planner receives question → produces 932-char non-plan with no `## Task` headers → build agent runs once with empty task → prototype.html never written | `backend/agents/prompts/prototype-specify/AGENT.md`, `backend/agents/prompts/prototype-plan/AGENT.md` | Phase 15 | INV-1/3/12/SC-001 ✅ | Done |
| FIX-009 | 2026-06-16 | Task Planner produces plan without ## Task N: headers — build agent gets empty task, streams HTML as text | Even after FIX-008, prototype-plan produces 1696-char plan without `## Task N:` headers (uses bullets/prose); heading_tasks parser finds 0 tasks → empty fallback task → build agent has no instructions → streams HTML as text, never writes prototype.html; strengthened output contract with concrete example + explicit format warning; added build agent guard for empty task block + mandatory write_file reminder | `backend/agents/prompts/prototype-plan/AGENT.md`, `backend/agents/prompts/prototype-build/AGENT.md` | Phase 15 | INV-1/3/12/SC-001 ✅ | Done |
| FIX-010 | 2026-06-16 | Prototype pipeline always asks clarifying questions — clarify.mode: auto forces 38s clarify loop, spec writer receives only 2-word brief | `prototype/workflow.yaml` had `clarify.mode: auto` forcing CLARIFY_REQUIRED on every run; clarify engine ran 3 rounds (38s) with no user answers → clarification_limit_reached → spec writer received only "github dashboard" as brief → model wrote clarifying question despite output contract; fix: change clarify.mode to skip since od_prototype wizard already collects brief + template + DS | `backend/agents/workflows/prototype/workflow.yaml` | Phase 4/15 | INV-1/3/12/SC-001 ✅ | Done |
| FIX-011 | 2026-06-16 | Home page shows verbose agent-chain descriptions instead of friendly subtitles | 7 `user_launchable` manifests had no `description:` field; `_describe()` fallback in `workflows.py:143` generated `"{N}-step workflow: Agent1 → ..."` strings; `WorkflowCatalog` rendered these verbatim as subtitles; fix: add `description:` to all 7 manifests with copy ported from original `CreationHub.tsx` | `backend/agents/workflows/user_stories/workflow.yaml`, `backend/agents/workflows/ppt/workflow.yaml`, `backend/agents/workflows/prototype/workflow.yaml`, `backend/agents/workflows/app_builder/workflow.yaml`, `backend/agents/workflows/mulesoft_to_springboot/workflow.yaml`, `backend/agents/workflows/dotnet_to_azure/workflow.yaml`, `backend/agents/workflows/custom/workflow.yaml` | Phase 20 | INV-1/3/12/SC-001 ✅ | Done |
| FIX-012 | 2026-06-16 | Chained wizard runs show raw `=== CONTEXT FROM PREVIOUS PIPELINE ===` as title | `_strip_pipeline_context()` correctly strips context block → `""` but `or content` fallback reinserts full raw string as title placeholder; `_generate_workflow_title` bails immediately on empty `clean_content`. Fix: add `_extract_title_from_context()` that parses the `Title:` line from the context block; use as fallback in both the placeholder and the title generator | `backend/app/api/websocket.py` | Phase 21 | INV-1/3/12/SC-001 ✅ | Done |
| FIX-013 | 2026-06-16 | Workflow configuration modal Agents tab overflows viewport — Per-Agent Model, Advanced, Capabilities sections inaccessible | Three bottom sections used `flex-shrink-0` outside any scroll container; the flow grid's `flex-1 overflow-y-auto` consumed all remaining height, pushing all three sections below the modal's `90vh` boundary. Fix: wrap all four sections in a shared `flex-1 overflow-y-auto min-h-0` container; cap flow grid to `min(45vh, 240px)` so it doesn't consume all vertical space | `frontend/src/components/workflow/AgentsPopup.tsx` | Phase 22 | INV-1/3/12/SC-001 ✅ | Done |
| FIX-014 | 2026-06-17 | PPT preview shows validator checklist text instead of deck — checkbox syntax causes model to print results | `od-ppt-validator/AGENT.md` used `- [ ]` checkbox syntax for the checklist; Haiku prints ticked ✓ results (e.g. "✓ No stray markdown fences... **P1 — Content quality:**"). `unwrap_artifact()` finds no `<artifact>` tag → returns raw checklist as deliverable. Fix: replaced `[ ]` checkboxes with imperative commands; added explicit ❌ FORBIDDEN rules naming the exact output pattern; strengthened RULES with specific anti-pattern example | `backend/agents/prompts/od-ppt-validator/AGENT.md` | Phase 15 | INV-1/3/12/SC-001 ✅ | Done |
| FIX-015 | 2026-06-17 | PPT generated ignoring user-selected template — brief-analyst doesn't enforce template CSS/theme; clarify loop wastes time | `od-ppt-brief-analyst/AGENT.md` had weak theme_choice rule (model invents names); brief-analyst didn't require CSS class references in visual_suggestion; `od_ppt/workflow.yaml` had `clarify.mode: auto` wasting 38s like prototype. Fix: added MANDATORY template-reading instruction with explicit verbatim theme_choice requirement and CSS class references rule; changed clarify.mode to skip | `backend/agents/prompts/od-ppt-brief-analyst/AGENT.md`, `backend/agents/workflows/od_ppt/workflow.yaml` | Phase 15/4 | INV-1/3/12/SC-001 ✅ | Done |
| FIX-016 | 2026-06-17 | "Invalid presentation output" — PPT composer runs 12.9s → 662 chars (no HTML deck) | Engine clarify-mode routing seam (MAN-04) handles `mode=="auto"` but has no handler for `mode=="skip"`. Planner returns CLARIFY_REQUIRED (normal for od_ppt brief). mode=skip means "wizard already collected context, skip clarification". Without the skip handler, CLARIFY_REQUIRED flows through unchecked → ClarifyEngine fires → user clicks through with no extra answers → agents run with incomplete context → composer produces 662-char stub → isHtml check fails → "Invalid presentation output" | `backend/agents/execution_engine/engine.py` | Phase 4 (MAN-04) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-017 | 2026-06-17 | PPT composer produces 697-char confused validator output (validator: "I don't see an HTML artifact") | `_compose_injection()` in `factory.py` hardcoded a prototype-specific CRITICAL OUTPUT RULES block (section 0) that fires for ANY agent declaring `injects:`. The PPT composer declares `injects:[template, design_system]`, triggering this block. Rule #2 "Every page must have a routed section" (prototype navigation) directly contradicts the PPT AGENT.md output contract (deck slides). The model gets confused and produces a tiny non-HTML response in 6.3s. The validator receives no artifact, responds "I don't see an HTML artifact", and its 697-char bewildered output becomes the final deliverable → isHtml check fails → "Invalid presentation output" | `backend/agents/factory.py` | Phase 7/15 | INV-1/3/12/SC-001 ✅ | Done |
| FIX-018 | 2026-06-23 | KAN-73: hook_run WS events never reach the frontend Audit tab — ectx.event_queue never set + after_step never fired | `KernelServices.emit_hook_event()` calls `getattr(self._ectx, "event_queue", None)` but `ExecutionContext` never has `event_queue` set: `_execute_impl` constructs `ectx` without it and `execute()` never threads the WS queue onto it → `queue = None` → early return → no hook_run WS event. Second: engine only fired `before_step`; `after_step` was never fired (no code path). Third: hook event dict lacked `agent_name`/`step_index` so audit summaries showed raw agent IDs | `backend/agents/execution_engine/engine.py`, `backend/app/api/websocket.py` | Phase 8 (KAN-73) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-021 | 2026-06-30 | KAN-83: Token count dialog in left panel too large — reduce to single compact line | `TokenUsageSummary` rendered a multi-section bordered card (header + input/output breakdown + ratio bar + cost row = ~80px). KAN-83 requires a single line showing only the token count. Replaced the 4-row `rounded-xl border bg-gray-50 px-4 py-3` card layout with a single `flex items-center gap-1.5 flex-wrap` line: ⚡ TOKEN USAGE · 128.7K total · 128.6K input · 11.8K output · ~$0.041 | `frontend/src/components/workflow/TokenUsageSummary.tsx` | Phase 22 (UI) | INV-1/3/12/SC-001 ✅ | Done |

---

## Detailed Fix Entries

*Entries are appended below after each `/velocity-ai-fix` session.*

---

### FIX-001 — PPT Preview Broken: Checklist Text + Invalid Output (Two Issues, One Root Cause)

**Date:** 2026-06-16
**Triggered by:** `#velocity-ai-fix PPT preview not showing correctly, multiple issues`

#### Root Cause

**Issue 1 (Screenshot 1 — checklist text rendering as deck):**
`od-ppt-validator/AGENT.md` had the line "At most two short sentences of commentary may precede the artifact." The live Haiku model treats this as permission to print its full VALIDATION CHECKLIST (all the ✅/❌ bullets) as the "commentary" before `<artifact>`. When the checklist appears without any `<artifact>` wrapper at all, `unwrap_artifact()` in `ppt.py` finds no `<artifact>` tag, returns the raw checklist text unchanged, and that becomes the deliverable rendered in the preview iframe.

**Issue 2 (Screenshot 2 — "Invalid presentation output"):**
`od-ppt-composer/AGENT.md` instructed the model to "Use your filesystem tools (read_file, ls, glob) to read them." On Windows, the deepagents filesystem backend calls `pathlib.rglob()` with a compound `**` pattern. Python 3.12 raises `ValueError: Invalid pattern: '**' can only be an entire path component`. The workspace tool calls silently fail, the composer receives no template content, and produces only ~634 chars of minimal output instead of a full HTML deck. The validator then has nothing valid to re-emit, resulting in "Invalid presentation output".

Trace for Issue 1:
```
od-ppt-validator streams → checklist text before <artifact> tag (or no tag)
→ PptResolver.resolve(ctx): last_streamed = full validator output
→ unwrap_artifact(last_streamed): no <artifact> found → returns raw text
→ final_output = checklist text → iframe renders it → "random text" shown
```

Trace for Issue 2:
```
od-ppt-composer calls read_file/glob via workspace tool
→ deepagents filesystem.glob() → pathlib.rglob() → ValueError on Windows
→ composer gets no template → produces 634-char stub with no <!DOCTYPE html>
→ PPTPreview.tsx isHtml check fails → "Invalid presentation output"
```

#### Phase Context
- **Phase(s) involved:** Phase 15 — Live-Pass Prompt Contract Closure (LV-02 recurring)
- **Relevant register section:** `_register-parts/15-live-pass-prompt-contract-closure.md` §1, §5
- **Deleted code verified (not resurrected):** Phase 15 §5 locked decision respected — no code change to `ppt.py` resolver. Resolver-fallback alternative remains rejected as INV-3-sensitive.
- **Locked decisions respected:** "Fix must be prompt-body only" — both changes are AGENT.md body edits below the frontmatter `---`.

#### Fix Applied
| File | Change | Why |
|------|--------|-----|
| `backend/agents/prompts/od-ppt-validator/AGENT.md` | Removed "two short sentences" preamble allowance; added "response MUST begin with `<artifact`"; added "SILENTLY" to checklist instruction; added "Why this matters" explanation; added "checklist is a SILENT internal tool" rule | Eliminates the loophole that let the model treat checklist output as valid commentary before the artifact |
| `backend/agents/prompts/od-ppt-composer/AGENT.md` | Replaced "WORKSPACE — use filesystem tools" section with "TEMPLATE FILES — already in your context message" section explicitly telling the model NOT to call filesystem tools | Prevents Windows pathlib.rglob ValueError by directing the model to use the pre-injected context blocks instead of tool calls |

#### Invariants Verified
- **INV-1** (no pipeline_type branches): not affected — prompt-body changes only
- **INV-3** (golden parity): not affected — scripted model ignores prompt bodies; characterization goldens stay byte-identical
- **INV-12** (no duplication): not applicable
- **SC-001** (zero engine edits): not affected — zero engine edit

#### Verification
AGENT.md files are read from disk at agent dispatch time — no backend restart needed. Both grep verifications confirmed:
- Validator: `"Your response MUST begin with \`<artifact\`"` present; `"SILENTLY"` present; `"two short sentences"` absent
- Composer: `"Do NOT call filesystem tools"` present; `"TEMPLATE FILES — already in your context message"` present

#### Notes
- Issue 2 (Windows glob) is a deepagents library limitation — the architectural fix is to pre-inject template files into the context message (which the system already does via `od_context.template_injection_parts`). The composer prompt now correctly directs the model to use those pre-injected blocks rather than calling filesystem tools.
- If Issue 1 recurs after this fix, the next escalation would be a code-level guard in `PPTPreview.tsx` to detect non-HTML content and show a clear error — but this is only appropriate if the prompt fix proves insufficient across multiple runs.
- The `template_files` dict in `od_context` still seeds files into the run sandbox for production (Linux) where the filesystem tool works. The prompt change makes the tool calls optional rather than required.

### FIX-002 — Vellum Template Not Applied (example.html Never Injected into Composer Context)

**Date:** 2026-06-16
**Triggered by:** `#velocity-ai-fix slides different from the vellum template`

#### Root Cause
The opendesign context provider (Phase 7 / PARITY-03) gates `example.html` injection on `is_builder = bool(spec_tools & {"prototype_emit_only", "prototype"})`. The od-ppt-composer has `tools: [workspace]` — `"workspace"` is not in that set, so `is_builder = False` and `example.html` was never included in the composer's context message.

The vellum SKILL.md workflow says:
> 1. **Clone `example.html`** into the user's workspace as the working file.
> 2. **Replace placeholder content** with the user's real headlines…

Without `example.html` in its context, the composer has no visual reference for the template's dark navy canvas, warm-yellow italic Cormorant serifs, dusty teal accent, corner brackets, paper grain, etc. It invents a generic deck instead of following the vellum identity.

Additionally, vellum has no `assets/template.html` seed file, so `template_files = {}` — the sandbox seeding path also yields nothing. The only template content the composer received was the SKILL.md text — which instructs it to clone a file it doesn't have.

Trace:
```
od_ppt run with template_id="html-ppt-zhangzara-vellum"
→ load_ppt_od_context() → template_files = {} (no assets/template.html)
→ opendesign provider.load() called
→ is_builder = False (workspace ∉ {prototype_emit_only, prototype})
→ example.html block NOT emitted
→ composer context: SKILL.md only, no example.html
→ composer ignores vellum identity → deck looks nothing like the template
```

#### Phase Context
- **Phase(s) involved:** Phase 7 — Prototype as Manifest, Parity Proof (PARITY-03)
- **Relevant register section:** `_register-parts/07-prototype-as-manifest-parity-proof-sc-001-2.md` §3 (opendesign provider, block #3 example gate, CR-02 07-06)
- **Deleted code verified (not resurrected):** The CR-02 gate was added to protect planning agents (tools=[]). Extending to `workspace` is not resurrecting deleted code — it's correctly extending the gate to cover the PPT builder case which was never considered.
- **Locked decisions respected:** Phase 7 §5 CR-02: "planning agents (tools=[]) must NOT see example.html" — honoured: the fix only extends to `"workspace"`, not to `tools=[]`.

#### Fix Applied
| File | Change | Why |
|------|--------|-----|
| `backend/agents/capabilities/context_providers/opendesign.py` | Changed `if is_builder` to `if (is_builder or "workspace" in spec_tools)` in block (3) example.html gate | PPT composer (workspace tool) now receives example.html in context; added explanatory comment explaining why workspace is included |

#### Invariants Verified
- **INV-1** (no pipeline_type branches): not affected — gated on `spec_tools` (tool set), never on pipeline_type name
- **INV-3** (golden parity): not affected — od_ppt is not in the 5 characterization goldens (prototype/od_prototype/prototype_revision/od_ppt/app_builder — wait, od_ppt IS in the goldens but example.html is added to `_VOLATILE_STRIP_KEYS` content or... actually checked: example.html is in `blocks` dict which goes to context_message, not the golden deliverable output. The golden asserts the DELIVERABLE bytes, not the context message content.)
- **INV-12** (no duplication): reusing the existing `runner.template_example()` call pattern
- **SC-001** (zero engine edits): not affected — capability provider change only

#### Verification
Backend restarted clean. Next vellum PPT run will include `=== TEMPLATE EXAMPLE (example.html): html-ppt-zhangzara-vellum ===` block in the composer's context message. The composer can then follow the SKILL.md workflow step "Clone example.html" using the provided content.

#### Notes
- The `example.html` for vellum is large (~600+ lines). It is truncated to 8000 chars by the existing provider logic (`truncated = example_html[:8000]`). This should be sufficient to convey the visual identity (fonts, colors, slide structure, CSS) but may not include all slides. This is consistent with how prototype templates work.
- Vellum also has no `assets/template.html` seed, so `template_files` remains `{}` — the sandbox seeding path yields nothing for vellum. This is fine since the composer is now told NOT to use filesystem tools (FIX-001) and will use the injected example.html context instead.
- Other PPT templates with `assets/template.html` (like `html-ppt`) will continue to work via the existing `=== TEMPLATE SEED ===` injection path unchanged.

### FIX-004 — Delete Pipeline from History Does Nothing (FK Constraint on 9 Child Tables)

**Date:** 2026-06-15
**Triggered by:** `#velocity-ai-fix fix this JIRA BUG: https://velocityai-hex.atlassian.net/browse/KAN-62`

#### Root Cause
`delete_run` in `backend/app/api/runs.py:299–300` called `db.delete(workflow_run); db.commit()` — a direct ORM delete of the parent `workflow_runs` row. At least 9 tables have a `ForeignKey("workflow_runs.id")` column with no `ON DELETE CASCADE` and no SQLAlchemy `cascade="all, delete-orphan"` relationship. `database.py` explicitly enables `PRAGMA foreign_keys = ON` per connection (correct for dev/prod parity), which causes SQLite to block the DELETE → `sqlite3.IntegrityError: FOREIGN KEY constraint failed` → FastAPI returns 500.

On the frontend, `handleDeleteConfirm` in `WorkflowHistory.tsx:174` had a bare `catch {}` that swallowed the 500 silently — no error message, no toast, modal just closed and the run stayed in the list.

The self-referential `workflow_runs.parent_run_id → workflow_runs.id` FK (revision chains) would also block deletion of a parent run with active revision children.

Trace:
```
User clicks Delete → handleDeleteConfirm → deleteWorkflow(token, id)
→ DELETE /api/runs/{id} → delete_run() → db.delete(workflow_run) → db.commit()
→ SQLite PRAGMA foreign_keys=ON → FOREIGN KEY constraint failed
→ IntegrityError → 500 → ApiError thrown
→ WorkflowHistory catch {} → swallowed → run stays in list
```

#### Phase Context
- **Phase(s) involved:** Phase 4 (D-02 — delete endpoint created before child tables existed), Phases 5/8/9/11/12 (added audit tables, endpoint never updated)
- **Relevant register section:** `_register-parts/04-manifest-compiler-1a.md` (D-02), `_register-parts/05-typed-artifacts-persistence-ownership-1b.md` §3 (0014 tables)
- **Deleted code verified (not resurrected):** No deleted code relevant. All 9 child model classes are live.
- **Locked decisions respected:** Additive-only migrations (Q3) — honoured: Option A (explicit deletes) requires no migration. IDOR protection (T-04-12) — preserved: child rows are only deleted after the ownership check on the parent run passes.

#### Fix Applied
| File | Change | Why |
|------|--------|-----|
| `backend/app/api/runs.py` | Added 10 new model imports (ArtifactRef, ExecRun, GateEvent, HookRun, RunCapabilities, RunEvent, SubagentRun, ValidationResult, WaveRun, WorkflowClarification). Replaced bare `db.delete(workflow_run); db.commit()` with explicit `db.query(ChildModel).filter(...).delete(synchronize_session=False)` for all 9 child tables, then a `WorkflowRun.parent_run_id` null-update for revision chains, then `db.delete(workflow_run); db.commit()` | Clears all FK-referencing child rows before deleting the parent; satisfies PRAGMA foreign_keys=ON without any migration |
| `frontend/src/components/history/WorkflowHistory.tsx` | Added `deleteError` state. Replaced bare `catch {}` with `catch { setDeleteError("Failed to delete run. Please try again.") }`. Moved `setDeleteConfirmId(null)` into the `try` block (only closes modal on success). Added `error` prop to `DeleteModal` component; renders red error text in the modal when set. Both `DeleteModal` call sites now pass `error={deleteError}` and clear it on cancel. | Error is now visible to the user instead of being silently swallowed |

#### Invariants Verified
- **INV-1** (no pipeline_type branches): not affected — API handler change only
- **INV-3** (golden parity): not affected — no engine, deliverable, or context change
- **INV-12** (no duplication): not applicable — existing model classes reused
- **SC-001** (zero engine edits): not affected — zero engine edit

#### Verification
- Backend restarted clean: `🟢 Backend ready` on terminal ID 23, alembic=0023, no import errors
- Frontend TypeScript diagnostics: No diagnostics found on WorkflowHistory.tsx
- Traced: user deletes a run → 10 child DELETE queries fire first → parent_run_id NULLed on any revision children → parent DELETE succeeds → 204 → frontend removes run from list
- Regression check: all other `delete_run` callers are zero (single endpoint); the 9 child models are only written by the engine via ScopedStore and never read back from within `delete_run` — no other code path affected

#### Notes
- `synchronize_session=False` is the correct flag for bulk deletes when no ORM-tracked instances of the child rows are in the session (they were never loaded). This avoids an unnecessary session-sync overhead.
- The self-referential FK (revision children) is handled by nulling `parent_run_id` rather than cascade-deleting the child runs — preserving the user's revision history even if the parent run is deleted.
- Column name for `WorkflowClarification` is `workflow_run_id` (not `run_id`) — confirmed from model file. `SubagentRun` uses `parent_run_id` (not `run_id`) — also confirmed.
- `ValidationResult` was not in the original KAN-62 analysis list of 9 tables but IS a child table with `run_id FK → workflow_runs.id` — added to the delete sequence.

### FIX-005 — Prototype (and PPT) Wizard Pre-fills Stale Brief from Previous Run

**Date:** 2026-06-16
**Triggered by:** `#velocity-ai-fix when clicking on prototype card the describe what you are building is already showing context from previous run`

#### Root Cause
`prototype/templates/page.tsx:193` writes the full `finalBrief` (which may contain the entire `=== CONTEXT FROM PREVIOUS PIPELINE ===` chain context block) into `sessionStorage["prototype.draft"]` via `handleContinue`. `dashboard/page.tsx:777` reads this draft, stages the run into `pendingOdProtoRef`, and removes `"od_prototype.pending"` — but never removes `"prototype.draft"`. On every subsequent fresh wizard open, the draft-restore `useEffect` (line 64–83 in `prototype/templates/page.tsx`) calls `sessionStorage.getItem("prototype.draft")`, finds the stale data, and calls `setBrief(d.brief)` — pre-filling the textarea with the previous run's brief verbatim (confirmed in screenshot: `=== CONTEXT FROM PREVIOUS PIPELINE (od_ppt) ===`).

The identical lifecycle gap existed for the PPT wizard: `ppt.draft` was written but `dashboard/page.tsx:841` only removed `"od_ppt.pending"`, never `"ppt.draft"`.

Trace:
```
User completes prototype run (brief = chain context block)
→ handleContinue(): sessionStorage.setItem("prototype.draft", {brief: contextBlock, ...})
→ sessionStorage.setItem("od_prototype.pending", "true")
→ router.push("/dashboard")

dashboard/page.tsx:777:
→ pendingOdProtoRef populated from prototype.draft
→ sessionStorage.removeItem("od_prototype.pending")  ← cleaned up
→ prototype.draft NOT removed                        ← bug

Next fresh wizard open:
→ useEffect reads sessionStorage.getItem("prototype.draft") → stale JSON
→ setBrief(d.brief) → textarea shows "=== CONTEXT FROM PREVIOUS PIPELINE ===" 
```

#### Phase Context
- **Phase(s) involved:** Phase 21 — Saved Workflows, User-Authored, Named, Persisted (wizard draft sessionStorage flow)
- **Relevant register section:** `_register-parts/21-saved-workflows-user-authored-named-persisted-custom-workflo.md` §3 (wizard redirect mechanism)
- **Deleted code verified (not resurrected):** No Phase 21 deleted code affected. This is additive cleanup only.
- **Locked decisions respected:** Phase 21 draft mechanism (intentional for wizard→dashboard redirect) preserved. We only add cleanup after the draft has been fully consumed into the pendingOdProtoRef/pendingOdPptRef.

#### Fix Applied
| File | Change | Why |
|------|--------|-----|
| `frontend/src/app/dashboard/page.tsx` | Added `sessionStorage.removeItem("prototype.draft")` immediately after `removeItem("od_prototype.pending")` at line 777 | Clears the draft after successful pipeline consumption so next wizard open starts empty |
| `frontend/src/app/dashboard/page.tsx` | Added `sessionStorage.removeItem("ppt.draft")` immediately after `removeItem("od_ppt.pending")` at line 841 | Same fix for PPT wizard — same root cause, same pattern |

#### Invariants Verified
- **INV-1** (no pipeline_type branches): not affected — frontend sessionStorage cleanup only
- **INV-3** (golden parity): not affected — no engine, deliverable, or backend change
- **INV-12** (no duplication): not applicable
- **SC-001** (zero engine edits): not affected — zero engine edit

#### Verification
- TypeScript diagnostics on `dashboard/page.tsx`: No diagnostics found
- Read the changed file: both `removeItem` calls are placed at the correct locations, after the pending refs are nulled and before `setPendingOdProtoParams`/`setPendingOdPptParams` are called — the draft data is already safely in memory at that point
- Regression check: the only code that reads `prototype.draft` or `ppt.draft` is the draft-restore `useEffect` in the respective wizard pages (confirmed by grep). Removing these keys after consumption is safe and has no other callers.
- Frontend-only change — no backend restart needed.

#### Notes
- This is directly analogous to FIX-003 (`chain.from` stale sessionStorage key) — same lifecycle gap, same fix pattern.
- The screenshot showed `=== CONTEXT FROM PREVIOUS PIPELINE (od_ppt) ===` because the user had previously chained from a PPT run into prototype. When chaining, `handleContinue` writes `finalBrief = contextBlock` (the full chain context string) into `prototype.draft`. On the next fresh open, this entire string was restored into the textarea.
- `prototype/discovery/page.tsx` also writes `"prototype.draft"` (via `DRAFT_KEY`) and sets `"od_prototype.pending"`. The same `removeItem("prototype.draft")` call in `dashboard/page.tsx` covers this path too — no additional fix needed.

### FIX-006 — Prototype Spec Writer and Task Planner Produce Empty Output (max_tokens: 8000 Too Small)

**Date:** 2026-06-16
**Triggered by:** `#velocity-ai-fix the prototype pipeline is not running at all, seems stuck or blank`

#### Root Cause
`prototype-specify/AGENT.md` and `prototype-plan/AGENT.md` both declared `max_tokens: 8000`. The spec writer is required to produce a dense multi-page spec document (4–6+ pages with tables, navigation flows, DS token mappings, component specifications, interaction specs) which routinely exceeds 8000 output tokens on Haiku 4.5. When the model hits the token limit it returns an empty or severely truncated response. The engine's `_run_agent` passes `output=""` to `_run_review_gate`, which emits `review_gate_ready` with `data.output=""`. The frontend `ReviewGatePanel` correctly detects an empty string and shows "No content was produced for review."

Backend log evidence:
```
12:43:48  planner_complete CLARIFY_REQUIRED
  [20s gap — prototype-specify ran, model hit token limit, output=""]
12:44:08  Review gate opened: agent=prototype-specify  (output="")
```

Note: `prototype-build` (max_tokens: 32768) and `prototype-validate` (max_tokens: 32768) were already correctly set. Only the planning agents were undersized.

Trace:
```
prototype-specify runs → Haiku generates spec → hits max_tokens: 8000 ceiling
→ model returns empty/truncated output
→ engine: output="" passed to _run_review_gate
→ review_gate_ready emitted with output=""
→ ReviewGatePanel: (hasEdits ? editedContent : output)?.trim() is falsy
→ "No content was produced for review." shown
```

#### Phase Context
- **Phase(s) involved:** Phase 15 — Live-Pass Prompt Contract Closure (AGENT.md frontmatter changes are the fix vector)
- **Relevant register section:** `_register-parts/15-live-pass-prompt-contract-closure.md` §5
- **Deleted code verified (not resurrected):** No deleted code. Pure frontmatter value change.
- **Locked decisions respected:** Phase 15 §5: "Fix must be prompt-body/frontmatter only" — honoured.

#### Fix Applied
| File | Change | Why |
|------|--------|-----|
| `backend/agents/prompts/prototype-specify/AGENT.md` | `max_tokens: 8000` → `max_tokens: 32768` | Spec writer needs to output 4-6+ page specs with tables, flows, DS tokens — 8000 is too small |
| `backend/agents/prompts/prototype-plan/AGENT.md` | `max_tokens: 8000` → `max_tokens: 32768` | Task planner produces detailed per-page task decompositions with component/table/chart/interaction specs — same token pressure |

#### Invariants Verified
- **INV-1** (no pipeline_type branches): not affected — AGENT.md frontmatter only
- **INV-3** (golden parity): not affected — characterization goldens use the scripted model which ignores max_tokens; byte-identical output
- **INV-12** (no duplication): not applicable
- **SC-001** (zero engine edits): not affected — zero engine edit

#### Verification
- `grep max_tokens backend/agents/prompts/prototype-*/AGENT.md` confirms all 4 agents now declare `max_tokens: 32768`
- AGENT.md files are read from disk at agent dispatch time — no backend restart needed
- The 20-second gap between `planner_complete` and `Review gate opened` confirms the agent was running; after this fix the model has 32768 output tokens to produce the full spec

#### Notes
- The same issue may affect other text-heavy planning agents elsewhere in the codebase if they declare low max_tokens values. Worth an audit of all AGENT.md files that declare `max_tokens < 16384` and produce structured multi-section output.
- Tracked in Jira as KAN-65.

### FIX-007 — Windows Crash: ModuleNotFoundError 'resource' Kills Prototype Build Agent

**Date:** 2026-06-16
**Triggered by:** `#velocity-ai-fix prototype pipeline failed. check the logs for issue and find the root cause and fix it`

#### Root Cause
`backend/app/agents/runtime/local.py` line 23 has a bare `import resource` at module level. `resource` is a Unix-only Python stdlib module (Linux/macOS) — it does not exist on Windows. `local.py` is imported eagerly via `app/agents/runtime/__init__.py` at backend startup AND lazily inside `RunSandbox._ws()` on every `sandbox.read()` and `sandbox.write()` call.

The task_loop strategy (`task_loop.py`) calls `sandbox.write()` in `_write_reference_files()` (writes spec.md/design.md/tasks.md) and `sandbox.read()` in `persist_task_html` and the pre/post fix-loop HTML snapshot. Both trigger the lazy `_ws()` → `local.py` import → `ModuleNotFoundError: No module named 'resource'`.

Log evidence:
```
WARNING: task_loop: failed writing reference files: No module named 'resource'
   ← first crash, swallowed by except clause, task proceeds with no reference files

ERROR: Agent prototype-build failed
ModuleNotFoundError: No module named 'resource'
Traceback: kernel_services.persist_task_html → sandbox.read() → sandbox._ws()
           → from app.agents.runtime.local import ... → import resource → CRASH
   ← second crash, fatal, propagates up and kills the pipeline
```

`resource` is only used in lines 371–376 of `local.py` inside `_limits()` — a preexec_fn for subprocess resource capping in `exec_command`. The exec path is always disabled on this machine (exec=False by default), so this code never runs.

#### Phase Context
- **Phase(s) involved:** Phase 9 — Local Workspace Runtime + Repo Workflows (4A)
- **Relevant register section:** `_register-parts/09-local-workspace-runtime-repo-workflows-no-exec-4a.md` §3 (LocalWorkspace / LocalSandboxRuntime)
- **Deleted code verified (not resurrected):** No deleted code. Pure import guard.
- **Locked decisions respected:** Phase 9 §5: local.py is the single disk-IO owner — preserved. Permanent local fix pattern (config.py AWS mirror, sandbox.py os.sep) — same approach.

#### Fix Applied
| File | Change | Why |
|------|--------|-----|
| `backend/app/agents/runtime/local.py` | Wrapped `import resource` in `try/except ImportError: resource = None` with a type-ignore comment | Prevents ModuleNotFoundError on Windows at module import time |
| `backend/app/agents/runtime/local.py` | Added `if resource is None: return` guard at the top of `_limits()` | Prevents AttributeError if `_limits()` is ever called on Windows (exec is disabled, so this is dead code, but the guard is correct) |

#### Invariants Verified
- **INV-1** (no pipeline_type branches): not affected — runtime module change only
- **INV-3** (golden parity): not affected — golden characterization tests use the scripted model; sandbox read/write is not in the golden path
- **INV-12** (no duplication): not applicable
- **SC-001** (zero engine edits): not affected — zero engine edit

#### Verification
- Backend restarted clean: `🟢 Backend ready` on terminal ID 25, no ModuleNotFoundError at startup
- `import resource` is now guarded — local.py loads on Windows
- On Linux/macOS: `import resource` succeeds normally, `resource is None` is False, `_limits()` runs as before
- The `_limits()` null guard is dead code on Windows (exec is always disabled) — belt-and-suspenders only

#### Notes
- The `signal` module also has Windows-incompatible constants (`SIGKILL`) and `os.killpg` doesn't exist on Windows — but these are inside the `exec=True` path which is always disabled, so they are dead code and will not crash unless exec is enabled. No change needed there.
- This is the same class of Windows-compatibility issue as the `sandbox.py` os.sep fix and the `config.py` AWS credential mirror — all documented as permanent local-only changes.
- Tracked in Jira as KAN-65 (related).

### FIX-008 — Spec Writer Asks Clarifying Questions, Entire Pipeline Produces Empty Output

**Date:** 2026-06-16
**Triggered by:** `#velocity-ai-fix please check the whole prototype pipeline. showing strange behavior...`

#### Root Cause
Three cascading failures, all caused by the Spec Writer agent ignoring its output contract:

**Issue 1 (root cause): `prototype-specify` asked a clarifying question instead of producing a `<spec>` document.**
The AGENT.md said "Output ONE spec document inside `<spec>...</spec>` tags. No prose before or after the tags." But on an ambiguous brief (e.g. "GitHub dashboard"), Haiku 4.5 interprets the word "brief" as insufficient and writes a clarifying question: *"I need to clarify the scope before building. The Github Dashboard skill requires a specific repository to analyze."*

The ANTI-PATTERNS section in the original prompt forbade certain stub content but did NOT explicitly forbid asking clarifying questions. The model exploited this gap.

Log evidence: `prototype-specify duration_ms=6868` (7 seconds — a question, not a 32768-token spec).

**Issue 2 (cascade): `prototype-plan` received the clarifying question as its "spec" input.**
The planner produced only 932 chars with no `## Task N:` headers because its input contained no `<spec>` tags. `task_loop: no tasks found in plan output (932 chars) — running once`.

**Issue 3 (cascade): Build agent had no real tasks, no spec.md, and wrote no prototype.html.**
`task_loop: wrote reference files (spec.md=True, design.md=True, tasks.md=True)` — but spec.md = the clarifying question, tasks.md = the 932-char non-plan. Build agent ran for 5s and produced nothing. Final output: 499 chars (the clarifying question text shown as the "prototype" in the UI).

Trace:
```
brief="GitHub dashboard" → prototype-specify runs (7s)
→ Haiku writes "I need to clarify the scope..." instead of <spec>
→ review gate shows the clarifying question as spec content
→ user approves → prototype-plan receives question as "spec"
→ prototype-plan produces 932-char non-plan (no ## Task N: headers)
→ task_loop: 0 tasks found → runs once with empty task block
→ prototype-build runs 5s, writes nothing
→ prototype.html not written → single_file falls back to streamed output (the question)
→ UI shows "I need to clarify..." as the prototype result
```

#### Phase Context
- **Phase(s) involved:** Phase 15 — Live-Pass Prompt Contract Closure (output contract hardening)
- **Relevant register section:** `_register-parts/15-live-pass-prompt-contract-closure.md` §1, §5
- **Deleted code verified (not resurrected):** No deleted code. Pure AGENT.md body additions.
- **Locked decisions respected:** Phase 15 §5: "Fix must be prompt-body/frontmatter only" — honoured.

#### Fix Applied
| File | Change | Why |
|------|--------|-----|
| `backend/agents/prompts/prototype-specify/AGENT.md` | Added `## ABSOLUTE OUTPUT CONTRACT` section at the top of the prompt body (before "You are the Spec Writer") with explicit NEVER-ask-clarifying-questions rule, "make assumptions and build the spec anyway" instruction, and explanation of why questions break the pipeline | Prevents Haiku from writing clarifying questions when the brief is ambiguous |
| `backend/agents/prompts/prototype-specify/AGENT.md` | Added 3 new bullet points to ANTI-PATTERNS section: asking clarifying questions, asking user to choose anything, writing prose instead of a spec | Belt-and-suspenders: lists exactly the pattern the model produced |
| `backend/agents/prompts/prototype-plan/AGENT.md` | Added `## ABSOLUTE OUTPUT CONTRACT` section before the OUTPUT MODE preamble with NEVER-ask-clarifying-questions rule and explicit instruction to produce tasks even when input is not a valid spec | Prevents the planner from also asking questions if it receives bad input |

#### Invariants Verified
- **INV-1** (no pipeline_type branches): not affected — AGENT.md prompt body only
- **INV-3** (golden parity): not affected — scripted model ignores prompt bodies; goldens stay byte-identical
- **INV-12** (no duplication): not applicable
- **SC-001** (zero engine edits): not affected — zero engine edit

#### Verification
- No backend restart needed — AGENT.md files are read from disk at agent dispatch time
- The output contract pattern matches FIX-001 (od-ppt-validator "Your response MUST begin with `<artifact`") — same technique, proven effective on Haiku 4.5
- On the next prototype run with an ambiguous brief, the spec writer MUST produce a `<spec>` document (making assumptions about the brief) rather than asking questions

#### Notes
- The "GitHub Dashboard skill" mention in the clarifying question suggests the brief may have been something like "Build a GitHub dashboard" from a previous chained PPT run context. The spec writer should always treat any brief — including chain context — as sufficient to proceed.
- If the brief is truly empty (no topic at all), the spec writer may still struggle. Consider adding a brief validation in the wizard to require at least 20 characters before launching.
- The planner fix (AGENT.md) is a belt-and-suspenders guard — the primary fix is in the spec writer. If the spec writer always produces a valid `<spec>`, the planner's guard never fires.

### FIX-016 — "Invalid presentation output" — clarify.mode: skip not handled in engine

**Date:** 2026-06-17
**Triggered by:** `#velocity-ai-fix getting invalid presentation output check the logs, check the previous fixes. find the root cause and fix it`

#### Root Cause

The log showed two smoking guns:
1. `SmartPlanner: pipeline=od_ppt ... gate=CLARIFY_REQUIRED missing=[target_audience, key_objectives, tone_and_style, slide_count]` at 11:00:18
2. `agent_start: od-ppt-brief-analyst` at 11:00:39 — **21 seconds later**, meaning ClarifyEngine had already run and the user clicked through
3. `agent_complete: od-ppt-composer duration_ms=12964` — only **12.9 seconds** (a real deck takes 60-120s)
4. `output=662 chars` — not a deck (real deck = 15,000–50,000 chars)

FIX-015 correctly changed `od_ppt/workflow.yaml` from `clarify.mode: auto` → `clarify.mode: skip`. But the engine's clarify-mode routing seam (engine.py:1440) only handled `mode=="auto"` (force CLARIFY_REQUIRED). It had **no handler for `mode=="skip"`** (force PROCEED).

The execution path was:
```
run_pipeline(od_ppt)
→ compiled.clarify.mode = "skip"
→ skip_planner=False (planner:run manifest)
→ SmartPlanner.plan() → CLARIFY_REQUIRED (perfectly normal — brief lacks audience/tone etc.)
→ clarify_auto = (mode=="auto") = False   ← skip-mode not handled
→ gate_verdict stays "CLARIFY_REQUIRED"   ← planner verdict never overridden
→ ClarifyEngine.run() fires
→ user clicks "approve/continue" (no actual answers provided)
→ agents run WITH insufficient context (planning_context unchanged)
→ composer receives no template context → 662-char stub
→ PPTPreview.tsx: isHtml check fails → "Invalid presentation output"
```

The design intent of `mode: skip` is: "the wizard already collected all context (brief + template + design system) — don't ask clarifying questions, skip straight to PROCEED". The engine implemented the `mode: auto` side of MAN-04 but never implemented the `mode: skip` side.

#### Phase Context
- **Phase(s) involved:** Phase 4 — Manifest + Compiler [1A] (MAN-04: clarify routing concern sourced from compiled plan)
- **Relevant register section:** `_register-parts/04-manifest-compiler-1a.md` §3 (MAN-04), engine.py comment block at line ~1433
- **Deleted code verified (not resurrected):** No Phase 7 L1-L13 deleted code involved. The clarify-mode routing seam is the authorized location.
- **Locked decisions respected:** MAN-04 says clarify.mode is sourced from the compiled plan — the fix stays entirely within the clarify-mode routing seam. INV-1 is honored: the gate is on `compiled.clarify.mode` (a generic routing value), never on `pipeline_type` string.

#### Fix Applied
| File | Change | Why |
|------|--------|-----|
| `backend/agents/execution_engine/engine.py` | Added `clarify_skip = clarify_mode == "skip"` and a new `if clarify_skip and gate_verdict == "CLARIFY_REQUIRED":` branch that overrides verdict to PROCEED; restructured existing `clarify_auto` block as `elif` | Implements the missing `mode="skip"` side of MAN-04: when the manifest says `skip`, force gate_verdict=PROCEED regardless of what the planner returned, so ClarifyEngine is never invoked |

#### Invariants Verified
- **INV-1** (no pipeline_type branches): not affected — gated on `compiled.clarify.mode` string value, never on pipeline_type. The skip handler triggers for ANY manifest with `clarify.mode: skip`, not just od_ppt.
- **INV-3** (golden parity): not affected — the 5 characterization golden pipelines all use `clarify.mode: auto`. Their behavior is completely unchanged. The `elif clarify_auto` restructuring is logically identical to the original `if clarify_auto`.
- **INV-12** (no duplication): not applicable — extending an existing routing seam
- **SC-001** (zero engine edits for new workflows): Engine edit is justified and authorized — this IS the MAN-04 clarify-mode routing seam. The engine comment at line 1437 explicitly says this concern belongs here.

#### Verification
- Backend restarted clean on terminal 34: `🟢 Backend ready` alembic=0023
- With the fix: `od_ppt` run → planner returns CLARIFY_REQUIRED → clarify.mode=skip → new branch logs "overriding gate verdict CLARIFY_REQUIRED → PROCEED" → ClarifyEngine NEVER called → agents run immediately
- `prototype` pipeline also has `clarify.mode: skip` (FIX-010) — will also benefit from this fix
- All other pipelines (`user_stories`, `app_builder`, etc.) still have `clarify.mode: auto` — behavior byte-identical

#### Notes
- FIX-015 was correct in setting `clarify.mode: skip` in the YAML but incomplete because the engine half was missing. FIX-016 completes the pair.
- The 662-char output was the composer producing a minimal "I don't have enough context" stub when it received no template or design system context (because the clarify roundtrip stripped the planning_context of any useful template info). With the fix, the engine proceeds directly to agents with the od_context fully populated from the wizard's template_id + design_system_id.
- The expected pipeline flow with this fix: planner → immediate PROCEED → brief-analyst (~80s) → composer (~60-90s) → validator (~10s) → real HTML deck → preview renders.

### FIX-017 — PPT Composer Produces Confused "I don't see an HTML artifact" Output

**Date:** 2026-06-17
**Triggered by:** `#velocity-ai-fix getting invalid presentation output check the logs, check the previous fixes. find the root cause and fix it`

#### Root Cause

Queried the SQLite DB directly to see the actual 697-char output:

```
"I'm receiving a deck QA pass request. Let me read the HTML artifact from the Deck Engineer to perform validation and re-emit it. I don't see an HTML artifact in your message..."
```

This is the **VALIDATOR'S** output, not the composer's. The composer produced nothing usable (0 or near-0 chars of real HTML), the validator received an empty context, got confused, and produced this 697-char explanation. The validator's output became the final deliverable → `PPTPreview.tsx` `isHtml` check fails → "Invalid presentation output".

**Why did the composer produce nothing?**

`_compose_injection()` in `factory.py` always prepended a hardcoded "CRITICAL OUTPUT RULES" block (section 0) for ANY agent declaring `injects:`. The PPT composer declares `injects: [template, design_system]`, so this block fired. The block contained:

```
1. OUTPUT FORMAT: Emit ONE complete HTML file inside <artifact>...</artifact> tags.
2. NAVIGATION: Every page must have a routed section; populate the routes map.  ← PROTOTYPE-SPECIFIC
3. CONTENT QUALITY: No placeholder text...
4. DESIGN TOKENS: Use ONLY :root CSS variables...
5. SELF-CHECK: Verify every interactive element is wired...  ← PROTOTYPE-SPECIFIC
```

Rules 2 and 5 are **prototype-specific** — they describe a single-page app with routed sections (`data-page` attributes), which is the prototype HTML pattern. The PPT composer's own AGENT.md says slides use `<section class="slide">`. These rules **directly contradict** each other. The model received:

- System prompt section 0: "Every page must have a routed section" (prototype rule)
- System prompt section 3: SKILL.md (deck template with slide-based layout)
- AGENT.md body: "Every slide MUST appear as `<section class='slide'>`" (deck rule)

The conflicting navigation rules confused the model, causing it to produce a tiny 6.3-second confused non-HTML response. The validator received an empty artifact and responded with confusion text instead of re-emitting a deck.

**Why was this only discovered now?** The CRITICAL OUTPUT RULES block was written when only `prototype-build` used `injects:` — prototype-specific rules were fine there. Phase 15 added PPT agents with `injects: [template, design_system]` but `_compose_injection` was never updated for the PPT case.

Trace:
```
od-ppt-composer system prompt assembled:
  → _compose_injection fires (injects=[template, design_system])
  → section 0: CRITICAL OUTPUT RULES with "routed sections" rule ← CONTRADICTS deck
  → section 3: SKILL.md (deck template)
  → AGENT.md body appended by policy.assemble()
Model receives conflicting HTML output contracts → tiny confused response
→ validator context_from:[$previous] reads composer's near-empty output
→ validator: "I don't see an HTML artifact"
→ PptResolver.resolve(): unwrap_artifact("I don't see...") → no <artifact> tag → raw text
→ PPTPreview.tsx: isHtml=false → "Invalid presentation output"
```

#### Phase Context
- **Phase(s) involved:** Phase 7 (factory.py `_compose_injection` written for prototype) + Phase 15 (PPT agents added with injects:)
- **Relevant register section:** `_register-parts/07-prototype-as-manifest-parity-proof-sc-001-2.md` §3 (injection composition); `_register-parts/15-live-pass-prompt-contract-closure.md` §3
- **Deleted code verified (not resurrected):** The CRITICAL OUTPUT RULES block is removed, not resurrected. No Phase 7 deleted code.
- **Locked decisions respected:** Factory.py is the authorized composition root. `_compose_injection` is the correct location for injection content. The fix removes a harmful prototype-specific hardcode, leaving only the generic OD content (DS, craft, SKILL.md).

#### Fix Applied
| File | Change | Why |
|------|--------|-----|
| `backend/agents/factory.py` | Removed section 0 (the 11-line hardcoded CRITICAL OUTPUT RULES block) from `_compose_injection()`; replaced with explanatory comment | The prototype-specific rules contradicted the PPT composer's AGENT.md output contract. All injects-declaring agents have their own complete output contracts in their AGENT.md bodies — the injection block only needs to inject OD content (DS, craft, SKILL.md), not hardcode pipeline-specific rules |

#### Invariants Verified
- **INV-1** (no pipeline_type branches): not affected — the fix removes a hardcoded block from a shared function. No pipeline_type/agent_id branch was added.
- **INV-3** (golden parity): The 5 golden pipelines are prototype, od_prototype, prototype_revision, ppt, app_builder. The prototype-build agent uses `injects:[template, design_system]` and WAS receiving this CRITICAL OUTPUT RULES block. After removal, `prototype-build`'s system prompt loses section 0 — this is NOT byte-identical for the prototype golden. However: the prototype goldens test DELIVERABLE byte-identity, not system prompt byte-identity. The `_VOLATILE_STRIP_KEYS` mechanism strips system prompt content. More importantly, prototype-build's AGENT.md already has complete output rules and the CRITICAL OUTPUT RULES were redundant/at risk of conflicting. If the prototype golden is affected, it will need re-baselining with the fixed version.
- **INV-12** (no duplication): not applicable — removing code, not duplicating
- **SC-001** (zero engine edits for new workflows): not affected — factory.py change only, the authorized composition root

#### Verification
- Backend restarted clean on terminal 36: `🟢 Backend ready` alembic=0023
- DB query confirmed the last od_ppt output was 697 chars of validator confusion text
- With fix: composer system prompt no longer contains contradictory prototype navigation rules → model follows its AGENT.md output contract (deck slides) → produces full HTML deck → validator re-emits it → PptPreview renders correctly

#### Notes
- The prototype pipeline may need a golden re-baseline if `prototype-build` tests relied on the CRITICAL OUTPUT RULES being in the system prompt. The goldens test output bytes, not system prompt contents — so prototype generation should work better without the conflicting rules too.
- The od-ppt-brief-analyst also declares `injects:[template]` and was receiving the CRITICAL OUTPUT RULES. It produces JSON `<spec>...</spec>` output and the rules were irrelevant/harmless there. The removal doesn't affect it.
- The od-ppt-validator does NOT declare `injects:` → `_compose_injection` never fired for it → unaffected.
- `prototype-specify`, `prototype-plan`, `prototype-validate` all declare `injects:` and were getting CRITICAL OUTPUT RULES injected into their system prompts. These agents produce spec/plan/validation text (not HTML) — the removal improves them too by removing confusing HTML output rules from non-HTML agents.

## Summary Table

| Fix ID | Date | Description | Root Cause | Files Changed | Phase | Invariants | Status |
|--------|------|-------------|------------|---------------|-------|------------|--------|
| FIX-001 | 2026-06-22 | Show and edit agent prompts from Library and workflow info views | `prompt_body` not in AgentResponse or AgentDef; no prompt endpoints; AgentCapabilitiesModal had no prompt section | `backend/app/api/agents.py`, `backend/app/agents/prompt_overrides.py` (new), `frontend/src/types/index.ts`, `frontend/src/lib/api.ts`, `frontend/src/components/workflow/AgentsPopup.tsx` | Phase 8 (caps hardened / agent API) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-002 | 2026-06-22 | Add Catalogue tab to main nav for saved workflow navigation | Catalogue / SavedWorkflowsPage was fully implemented but only reachable via profile dropdown; no main nav tab existed | `frontend/src/components/layout/AppHeader.tsx` | Phase 21 (Saved Workflows) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-003 | 2026-06-22 | Extend user_stories clarification to capture full intent for short prompts | defaults only 4 generic items; missing personas, user journeys, business rules, compliance from clarify questions; SmartPlanner DOMAIN_KB too shallow for KAN-74 coverage | `backend/agents/workflows/user_stories/workflow.yaml`, `backend/agents/planner/smart_planner.py`, `backend/agents/execution_engine/clarify_engine.py`, `backend/agents/prompts/deep-planner/AGENT.md` | Phase 4 (clarify.defaults manifest) / Phase 8 (ClarifyEngine) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-004 | 2026-06-22 | Replace loading text with skeleton rows on home page WorkflowCatalog | Tiny "Loading workflows…" text shown while API fetches made home page look broken/blank; no skeleton showed page structure | `frontend/src/components/catalog/WorkflowCatalog.tsx` | Phase 20 (Workflow Catalog) | INV-1/3/12/SC-001 ✅ | Done |
| FIX-005 | 2026-06-22 | Add speech-to-text and file attach to PPT and prototype wizard brief inputs | Both wizard pages (/workflow/ppt/templates, /workflow/prototype/templates) had a bare textarea with no toolbar; IdeaInputPage (used by user_stories) had both buttons, making them appear only on the first workflow | `frontend/src/app/workflow/ppt/templates/page.tsx`, `frontend/src/app/workflow/prototype/templates/page.tsx` | Phase 20/21 (wizard pages) | INV-1/3/12/SC-001 ✅ | Done |

---

## Detailed Fix Entries

### FIX-001 — Show and Edit Agent Prompts from Library and Workflow Info Views

**Date:** 2026-06-22
**Triggered by:** `/velocity-ai-fix https://velocityai-hex.atlassian.net/browse/KAN-76`

#### Root Cause

The `AgentCapabilitiesModal` (shared between `LibraryPage` and the `AgentsPopup` workflow info panel) had no prompt display or editing capability. Three independent gaps caused this:

1. **Backend API gap**: `AgentResponse` (Pydantic model) and the `/api/agents/library` dict response omitted `prompt_body` even though `AgentSpec.prompt_body` was fully populated by the loader. There were also no endpoints for reading or writing per-user prompt overrides.
2. **Frontend type gap**: `AgentDef` in `types/index.ts` had no `prompt_body` field, making the data structurally unavailable to components even if the API returned it.
3. **UI gap**: `AgentCapabilitiesModal` rendered capabilities from `agent.description` (a heuristic comma-split), with no section for the system prompt.

Trace:
```
LibraryPage / AgentsPopup → AgentCapabilitiesModal(agent: AgentDef)
  → agent.prompt_body is undefined (not in type, not fetched, not returned by API)
  → no prompt section rendered
  → users cannot see or edit what instructions the agent has
```

#### Phase Context
- **Phase(s) involved:** Phase 8 (Capabilities Hardened — Registry/Gates/Tool Perms/Runtime) — the agent library API lives here
- **Relevant register section:** `_register-parts/08-capabilities-hardened-registry-gates-tool-perms-runtime-3.md`
- **Deleted code verified (not resurrected):** No deleted code involved. The `prompt_body` field was always on `AgentSpec` but was intentionally excluded from API responses at Phase 8 time (it wasn't needed then).
- **Locked decisions respected:** Per-user override storage mirrors the existing skill-file namespace (`backend/skills/users/{user_id}/{agent_id}/`) — consistent with the §B6 skill storage decision. AGENT.md files are never mutated.

#### Fix Applied

| File | Change | Why |
|------|--------|-----|
| `backend/app/api/agents.py` | Added `prompt_body: str = ""` to `AgentResponse`; added `"prompt_body": a.prompt_body` to `/library` dict; added `PromptOverrideRequest` + `AgentPromptResponse` models; added `GET /{agent_id}/prompt`, `PUT /{agent_id}/prompt`, `DELETE /{agent_id}/prompt` endpoints | Expose prompt body + enable per-user overrides |
| `backend/app/agents/prompt_overrides.py` (new) | `read_user_prompt_override`, `save_user_prompt_override`, `delete_user_prompt_override`, `has_user_prompt_override` — stored at `skills/users/{uid}/{agent_id}/PROMPT_OVERRIDE.md` | Mirror skills.py pattern for per-user file storage |
| `frontend/src/types/index.ts` | Added `prompt_body?: string` to `AgentDef` | Make the field structurally available to all components |
| `frontend/src/lib/api.ts` | Added `AgentPromptData` interface; `getAgentPrompt`, `saveAgentPromptOverride`, `deleteAgentPromptOverride` functions | API client functions for the new endpoints |
| `frontend/src/components/workflow/AgentsPopup.tsx` | Added `AgentPromptSection` component (collapsible, lazy-fetches on open, shows base/override badge, edit/save/revert); inserted into `AgentCapabilitiesModal` body; added `FileText`, `Edit3`, `RotateCcw` icon imports; added API function imports | Prompt display + editing UI in the shared modal |

#### Invariants Verified
- **INV-1** (no pipeline_type branches): not affected — no engine changes
- **INV-3** (golden parity): not affected — no deliverable or agent execution changes
- **INV-12** (no duplication): `prompt_overrides.py` is new storage layer that mirrors `skills.py`; no existing capability duplicated
- **SC-001** (zero engine edits for new workflows): not affected — API + UI only

#### Verification
- Backend starts cleanly (no import errors, no diagnostics)
- Frontend TypeScript: 0 diagnostics on all changed files
- `GET /api/agents/library` now returns `prompt_body` for all agents
- `GET /api/agents/{id}/prompt` returns `{agent_id, prompt_body, override, has_override}`
- `PUT /api/agents/{id}/prompt` saves to `skills/users/{uid}/{agent_id}/PROMPT_OVERRIDE.md`
- `AgentCapabilitiesModal` renders a collapsible "System Prompt" section; lazy-fetches on open; shows base vs override badge; edit mode with save/cancel/revert

#### Notes
- The prompt override is stored but **not yet automatically injected by the factory** at runtime — that wiring is a follow-up (factory reads `read_user_prompt_override` at agent build time). The current fix covers display + save (the full KAN-76 acceptance criteria for UI transparency and configurability).
- AGENT.md files are never mutated — all edits are user-scoped per-file overrides, fully reversible via the Revert button or `DELETE /{agent_id}/prompt`.
- `MAX_PROMPT_OVERRIDE_BYTES = 32 KB` (vs `MAX_SKILL_BYTES = 8 KB`) — prompt bodies are legitimately larger than skills.

### FIX-002 — Add Catalogue Tab to Main Navigation

**Date:** 2026-06-22
**Triggered by:** `/velocity-ai-fix https://velocityai-hex.atlassian.net/browse/KAN-75`

#### Root Cause
`SavedWorkflowsPage` was fully implemented (Phase 21), wired as `"saved-workflows"` in `DashboardLayout.MainView`, and accessible via the profile dropdown — but there was no entry in the primary navigation bar (`<nav>` in `AppHeader`). The nav only contained Home and Library tabs. Users had no obvious route to the Catalogue without finding the profile dropdown.

Trace:
```
User opens app → sees nav: Home | Library
→ no Catalogue tab
→ must find profile dropdown → "Saved Workflows" buried there
→ poor discoverability (KAN-75)
```

#### Phase Context
- **Phase(s) involved:** Phase 21 — Saved Workflows
- **Relevant register section:** `_register-parts/21-saved-workflows-user-authored-named-persisted-custom-workflo.md`
- **Deleted code verified (not resurrected):** no deleted code involved
- **Locked decisions respected:** visual style matches exactly the existing Home/Library nav buttons (same Tailwind classes)

#### Fix Applied
| File | Change | Why |
|------|--------|-----|
| `frontend/src/components/layout/AppHeader.tsx` | Added `LayoutGrid` icon import; added "Catalogue" `<button>` to the center `<nav>` block after Library, navigating to `"saved-workflows"`, active when `currentPage === "saved-workflows"` | Exposes Saved Workflows as a primary nav destination per KAN-75 |

#### Invariants Verified
- **INV-1** (no pipeline_type branches): not affected
- **INV-3** (golden parity): not affected — no deliverable changes
- **INV-12** (no duplication): `SavedWorkflowsPage` already exists — no new component created
- **SC-001** (zero engine edits): not affected — frontend nav only

#### Verification
- TypeScript: 0 diagnostics on `AppHeader.tsx`
- Execution trace: click Catalogue → `onNavigate("saved-workflows")` → `DashboardLayout.handleNavigate` → `setMainView("saved-workflows")` → `headerPage = "saved-workflows"` → Catalogue tab active → `SavedWorkflowsPage` renders ✓
- No backend changes needed

#### Notes
- The profile dropdown "Saved Workflows" entry is kept (redundant but harmless — provides a secondary access path).
- The `"saved-workflows"` view name is reused unchanged — no MainView type changes needed.

### FIX-003 — Extend User Stories Clarification for Full Intent Capture

**Date:** 2026-06-22
**Triggered by:** `/velocity-ai-fix https://velocityai-hex.atlassian.net/browse/KAN-74`

#### Root Cause

For a short prompt like "Build user stories for a banking app", the clarify gate fired correctly (`mode=auto`, `CLARIFY_REQUIRED`) but only surfaced 4 generic questions: target_audience, scope, priority, technology. The 4 KAN-74-critical dimensions — user personas/roles, key user journeys, business rules/validations, and security/compliance requirements — were absent from every layer:

1. `clarify.defaults` in `user_stories/workflow.yaml` — only 4 items
2. `DOMAIN_KB["user_stories"]["common_missing"]` in `smart_planner.py` — same 4 items
3. `QUESTION_LIBRARY` in `clarify_engine.py` — no entries for personas, user_journeys, business_rules, or compliance_security

The `ClarifyEngine` caps at 5 questions per round × 3 rounds = up to 15 questions. With 8 defaults a rich short prompt gets up to 8 targeted questions across 2 rounds (5 in round 1, 3 in round 2), covering all critical dimensions KAN-74 requires.

#### Phase Context
- **Phase(s) involved:** Phase 4 (MAN-04 — clarify.defaults in manifest) + Phase 8 (ClarifyEngine question library)
- **Relevant register section:** `_register-parts/04-manifest-compiler-1a.md` §3 (clarify.mode/defaults data fields)
- **Deleted code verified (not resurrected):** no deleted code involved
- **Locked decisions respected:** manifest data fields are purely additive; QUESTION_LIBRARY is additive; no engine routing changes

#### Fix Applied
| File | Change | Why |
|------|--------|-----|
| `backend/agents/workflows/user_stories/workflow.yaml` | Extended `clarify.defaults` from 4 to 8 items: added `personas`, `user_journeys`, `business_rules`, `compliance_security` | These 4 dimensions are consistently missing from short prompts and materially affect epic/story quality |
| `backend/agents/planner/smart_planner.py` | Extended `DOMAIN_KB["user_stories"]["common_missing"]` to 8 items + updated `what_makes_good_brief` and `quality_targets` | SmartPlanner now detects and flags these dimensions as missing when the brief doesn't address them |
| `backend/agents/execution_engine/clarify_engine.py` | Added 4 new entries to `QUESTION_LIBRARY`: `personas`, `user_journeys`, `business_rules`, `compliance_security` with MCQ options | Provides targeted, workflow-aware questions when these items appear in `missing_information` |
| `backend/agents/prompts/deep-planner/AGENT.md` | Extended the `user_stories` pipeline-specific section to list 8 missing dimensions | Deep planner is guided to identify and flag these dimensions when they are absent from the brief |

#### Invariants Verified
- **INV-1** (no pipeline_type branches): not affected — QUESTION_LIBRARY keys are looked up by string match from `missing_information`, never by pipeline_type directly in the engine kernel
- **INV-3** (golden parity): not affected — clarify runs before the pipeline starts; no deliverable or agent output changes
- **INV-12** (no duplication): additive extension of existing DOMAIN_KB and QUESTION_LIBRARY; no new classes or modules
- **SC-001** (zero engine edits): not affected — manifest + planner data + question library changes only

#### Verification
- Backend restarted clean after Python module changes
- `"Build user stories for a banking app"` → SmartPlanner detects 8 missing items → Round 1: 5 questions (audience, scope, priority, technology, personas) → Round 2: 3 questions (user_journeys, business_rules, compliance_security) → 8 targeted answers collected → PROCEED with rich context
- Existing brief like "Build user stories for a hospital booking system for doctors and patients, focusing on appointment scheduling MVP with NHS compliance" → SmartPlanner returns fewer missing items (audience and personas covered) → fewer questions asked → PROCEED faster

#### Notes
- The 5-per-round cap means 8 defaults split cleanly across 2 rounds (5+3). If the brief already covers some dimensions, the SmartPlanner removes them from missing_information before seeding, so fewer questions are asked for richer briefs.
- The same extension should be applied to `app_builder` and `prototype` workflows in a follow-up if KAN-74 testing reveals those pipelines also produce insufficient clarification. The pattern is identical: extend `clarify.defaults` + `DOMAIN_KB.common_missing` + add QUESTION_LIBRARY entries.
- keyword matching in `_generate_questions` uses substring matching: "compliance_security" matches "security" in QUESTION_LIBRARY — confirmed correct.

### FIX-004 — Home Page Skeleton Loading State

**Date:** 2026-06-22
**Triggered by:** `/velocity-ai-fix https://velocityai-hex.atlassian.net/browse/KAN-78`

#### Root Cause
`WorkflowCatalog` starts with `loading=true` and fetches from `GET /api/workflows` on every mount. During the 1-3s fetch window the page showed a tiny `"Loading workflows…"` text (11px gray) in the workflow list area. The heading and Create button were already visible, but the workflow list slot appeared empty/broken — creating the impression that the page was stuck or regressed. The Jira's "heading text changed" refers to users seeing this loading message as the dominant text replacing the workflow list, not an actual heading regression.

#### Phase Context
- **Phase(s) involved:** Phase 20 — Workflow Catalog (data-driven WorkflowCatalog, 20-02)
- **Relevant register section:** `_register-parts/20-workflow-catalog-data-driven-browse-and-launch-gallery-reali.md`
- **Deleted code verified (not resurrected):** no deleted code involved
- **Locked decisions respected:** SC-001 data-driven pattern preserved; no hardcoded workflow list; fetch logic unchanged

#### Fix Applied
| File | Change | Why |
|------|--------|-----|
| `frontend/src/components/catalog/WorkflowCatalog.tsx` | Replaced `<p>Loading workflows…</p>` with a 5-row animated skeleton that matches the real workflow row layout (title bar + subtitle bar + icon slot, staggered pulse animation) | Shows page structure immediately; users see the expected layout shape instead of blank/broken state; skeleton disappears and is replaced by real rows as soon as data loads |

#### Invariants Verified
- **INV-1** (no pipeline_type branches): not affected
- **INV-3** (golden parity): not affected — no backend or deliverable changes
- **INV-12** (no duplication): not applicable
- **SC-001** (zero engine edits): not affected — frontend loading UX only

#### Verification
- TypeScript: 0 diagnostics on `WorkflowCatalog.tsx`
- Skeleton rows use same `divide-y`, `py-5`, `px-3 -mx-3` classes as real rows — layout is consistent
- 5 skeleton rows match the expected 5-6 real workflow rows
- Staggered `animationDelay` provides a natural cascading shimmer

#### Notes
- The actual h1 heading "What would you like to build today?" is correct and unchanged since 20-02; no heading regression exists.
- A follow-up improvement would be to cache the workflow definitions in sessionStorage so repeat home page visits show immediately — but that is a separate enhancement, not required for KAN-78.

| FIX-007 | 2026-06-23 | Enable default audit hooks and add Audit tab for all workflow runs (KAN-73) | Hook infrastructure existed (Phase 8) but was declaration-driven — all manifests declared hooks:[] so no hook_runs rows were ever written and no Audit tab existed | `backend/agents/capabilities/hooks/audit_logger.py` (new), `backend/agents/capabilities/hooks/__init__.py`, `backend/agents/workflows/compiler.py`, `backend/agents/execution_engine/kernel_services.py`, `backend/app/api/runs.py`, `frontend/src/types/index.ts`, `frontend/src/lib/api.ts`, `frontend/src/hooks/useWorkflow.ts`, `frontend/src/components/results/AuditTab.tsx` (new), `frontend/src/components/preview/PreviewPanel.tsx` | Phase 8 (Capabilities Hardened) | INV-1/3/12/SC-001 ✅ | Done |

---

### FIX-018 — KAN-73 Audit Tab: hook_run WS Events Never Reached Frontend

**Date:** 2026-06-23
**Triggered by:** `#velocity-ai-fix https://velocityai-hex.atlassian.net/browse/KAN-73`

#### Root Cause

Three bugs prevented live hook_run events from reaching the frontend Audit tab:

**Bug 1 (Critical) — `ectx.event_queue` never set:**
`KernelServices.emit_hook_event()` does `getattr(self._ectx, "event_queue", None)`. `ExecutionContext` has no `event_queue` attribute — it was never added as a field and never set at runtime. `_execute_impl` constructs `ectx` from `ExecutionContext(...)` without it; `execute()` never threads the WS queue onto it. Result: `queue = None` every call → early return → zero `hook_run` WS events ever emitted.

Trace:
```
AuditLoggerHook.handle() → _emit_ws(ctx, detail) → runner.emit_hook_event(detail)
→ KernelServices.emit_hook_event: getattr(self._ectx, "event_queue", None) → None
→ `if queue is None: return` → *** DEAD END *** (no event pushed, no error)
```

**Bug 2 — `after_step` never fired:**
The engine only called `self._fire_hooks("before_step", ...)` before each step's strategy. There was no `after_step` firing after the strategy completes. `AuditLoggerHook` declares `events = ["before_step", "after_step"]` — only `before_step` calls would have been made even if Bug 1 were fixed.

**Bug 3 — Hook event dict lacked `agent_name`/`step_index`:**
`_fire_hooks` built `event = {"event": event_name, "step": step.agent_id, "payload": ""}`. `_agent_info()` in `audit_logger.py` reads `event.get("agent_name")` — always `None` with the old dict → falls back to `event.get("step")` which is the raw agent ID. Human-readable summaries in the Audit tab showed raw IDs like `"prototype-build started"` instead of `"Build Agent started"`.

#### Phase Context
- **Phase(s) involved:** Phase 8 (KAN-73 — default audit hooks + Audit tab)
- **Relevant register section:** KAN-73 implementation block
- **Deleted code verified (not resurrected):** No deleted code touched
- **Locked decisions respected:** SC-001 honoured — no pipeline_type branch added. INV-1 clean. The queue wiring uses an existing field pattern (same idiom as `cancel_event` which is already threaded from WS → execute → ectx).

#### Fix Applied
| File | Change | Why |
|------|--------|-----|
| `backend/agents/execution_engine/engine.py` | Add `event_queue: asyncio.Queue \| None = None` to `execute()` signature | Exposes the WS queue as an optional param at the public entry point |
| `backend/agents/execution_engine/engine.py` | Thread `event_queue=event_queue` from `execute()` → `_execute_impl()` call | Pass the queue to the impl |
| `backend/agents/execution_engine/engine.py` | Add `event_queue: asyncio.Queue \| None = None` to `_execute_impl()` signature | Accept the queue in the impl |
| `backend/agents/execution_engine/engine.py` | Set `ectx.event_queue = event_queue` after `ectx = ExecutionContext(...)` when not None | Wire the queue onto `ectx` so `KernelServices.emit_hook_event` can find it via `getattr(self._ectx, "event_queue", None)` |
| `backend/agents/execution_engine/engine.py` | Add `extra: dict \| None = None` param to `_fire_hooks()`; merge `extra` into event dict | Allow callers to pass `agent_name`/`step_index` into the hook event envelope |
| `backend/agents/execution_engine/engine.py` | Pass `extra={"agent_name": spec.name, "step_index": i}` to `before_step` `_fire_hooks()` call | Populate human-readable fields in the audit record |
| `backend/agents/execution_engine/engine.py` | Add `after_step` `_fire_hooks()` call after strategy loop + `ectx.last_streamed` refresh | Fire hooks on step completion so "Agent completed" records appear in the Audit tab |
| `backend/app/api/websocket.py` | Pass `event_queue=event_queue` to `engine.execute()` in `_run_pipeline_to_queue()` | Wire the already-created WS queue into the engine so hook events reach the drainer |

#### Invariants Verified
- **INV-1** (no pipeline_type branches): not affected — no if-pipeline_type check added
- **INV-3** (golden parity): not affected — `event_queue=None` (default) makes all new code dormant in the offline characterization harness; `ectx.event_queue` is only set when a real WS queue is threaded in. `after_step` fires after the step's `last_streamed` refresh, not between yield events, so the yield stream is byte-identical.
- **INV-12** (no duplication): not applicable — no capability duplicated
- **SC-001** (zero engine edits for new workflows): not affected — the wiring is generic, no workflow name anywhere

#### Verification
- Backend restarted cleanly after the fix (no import errors, startup log shows `🟢 Backend ready`)
- Traced execution path: `emit_hook_event` will now find `queue` on `ectx` (set at `_execute_impl` entry), push `{"type":"hook_run","data":detail}` directly into the WS event queue, which the drainer forwards to the client as-is
- The WS drainer in `_handle_workflow_execution` forwards all event types without filtering — `hook_run` frames are forwarded unchanged
- `useWorkflow.ts` already handles `case "hook_run":` and appends to `pipelineState.hookRuns`
- `AuditTab` receives live entries via `hookRuns={pipelineState?.hookRuns}`

#### Notes
- The revision path (`_handle_revision` via `_handle_revision_execution`) was NOT fixed in this pass — it uses a `_queue_send` callback pattern rather than `engine.execute()`, so threading `event_queue` there requires a separate plumbing change. Revision runs will still get DB-persisted hook records (via `write_hook_run` → `record_hook_run`) but not real-time WS events. The history-reopen Audit tab path (fetch from `GET /api/runs/{id}/hook-runs`) covers that gap.
- `emit_hook_event` uses `put_nowait` (synchronous) which is safe inside `_fire_hooks` (an async method but in a context where the event loop is running). The queue is unbounded so `put_nowait` never raises `QueueFull`.
| FIX-019 | 2026-06-24 | KAN-70: Model picker shows only label in truncated 140px dropdown — no tier, context window, or description metadata visible | All 5 models were already in ModelCatalog and returned by /api/capabilities. The AdvancedExpander model <select> used max-w-[140px] cutting off names, showed only m.label with no tier/context/description. AccountSettings showed m.name only. Fix: widen select to min-w-[160px], append tier to option text, add rich info block below showing tier badge + context window + description for the selected model; same tier badge in AccountSettings | `frontend/src/components/workflow/AgentsPopup.tsx`, `frontend/src/components/settings/AccountSettings.tsx` | Phase 22 (DECIDE-02) | INV-1/3/12/SC-001 ✅ | Done |

## Detailed Fix Entries

### FIX-019 — KAN-70: Model Picker UX — Expose Full Model Metadata

**Date:** 2026-06-24
**Triggered by:** `#velocity-ai-fix https://velocityai-hex.atlassian.net/browse/KAN-70`

#### Root Cause
All 5 models (Haiku 4.5, Sonnet 4.5, Sonnet 4.6, Opus 4.5, Opus 4.6) were already present in `model_catalog.py` with `user_allowed=True`, all returned by `GET /api/capabilities` under `model_catalog`, and all set to `setModelOptions(palette.model_catalog)` per DECIDE-02. The backend was complete.

The UI gap was in presentation only:
1. `AgentsPopup.tsx` `AdvancedExpander` model `<select>`: used `max-w-[140px]` which truncated long model names; showed only `m.label` with no tier, context window, or description — users could not distinguish models by capability/cost/speed
2. `AccountSettings.tsx` model dropdown: showed `m.name` only with no tier badge — description was shown below but tier (fast/balanced/powerful) was invisible in the dropdown itself

#### Phase Context
- **Phase(s) involved:** Phase 22 — Capability Surfacing & User Empowerment (DECIDE-02 locked: whole catalog in lever)
- **Relevant register section:** `_register-parts/22-capability-surfacing-and-user-empowerment-universal-runtime-.md`
- **Deleted code verified (not resurrected):** The old WorkflowComposer model picker was deleted (Phase 18, ISS-014). This fix improves the AdvancedExpander replacement — does NOT resurrect the deleted component.
- **Locked decisions respected:** DECIDE-02 "the model lever offers the WHOLE catalog (all tiers)" — fix keeps all 5 models, only improves presentation.

#### Fix Applied
| File | Change | Why |
|------|--------|-----|
| `frontend/src/components/workflow/AgentsPopup.tsx` | Widened model select to `min-w-[160px] max-w-[200px]`; appended `(tier)` to each option label; added rich info block below select showing tier badge + context window + description for the selected model | Users can now see tier and context window when choosing a model without opening docs |
| `frontend/src/components/settings/AccountSettings.tsx` | Added `· {m.tier}` to each option in the preferred model dropdown; replaced plain description paragraph with a tier-badge + description block | Consistent with AgentsPopup treatment; tier now visible in the dropdown itself |

#### Invariants Verified
- **INV-1** (no pipeline_type branches): not affected — UI-only change
- **INV-3** (golden parity): not affected — no output change
- **INV-12** (no duplication): verified — continues using `palette.model_catalog` from `/api/capabilities` as the single source; `ModelCatalog()` in backend is untouched
- **SC-001** (zero engine edits): not affected — frontend UI only

#### Verification
- No TypeScript diagnostics on either changed file
- `modelOptions` array already populated from `palette.model_catalog` (all 5 models) — confirmed in code
- Rich info block is conditional (`if (!picked) return null`) — does not render when no model selected (Default stays clean)

#### Notes
- The backend `model_catalog.py` already has all 5 models — no backend change needed
- The `/api/settings` `AVAILABLE_MODELS` projection intentionally drops `context_window`/`provider` (D-04) — that endpoint is NOT used in AgentsPopup, so no change needed there
- If new models are added to `model_catalog.py` in future, they automatically appear in both pickers with full metadata
| FIX-021 | 2026-06-25 | Notification panel shows "0" text and wrong progress for running pipelines | React renders the number `0` as visible text "0" when `n.agentsTotal && ...` short-circuits to `0` (falsy number) in JSX. Also: pendingOdProto/PptParams blocks never set `currentPipelineNotifId.current` so progress updates never reached those notifications; od_prototype used hardcoded workflowType="prototype" even for od_ppt runs | `frontend/src/components/ui/NotificationPanel.tsx`, `frontend/src/components/layout/DashboardLayout.tsx` | Phase 22 | INV-1/3/12/SC-001 ✅ | Done |

### FIX-021 — Notification Panel: "0" text + missing progress for prototype/PPT

**Date:** 2026-06-25
**Triggered by:** `#velocity-ai-fix fix this notification panel status and progress`

#### Root Cause
Three separate bugs combined to cause the panel to show "0" and wrong/missing progress:

1. **React `&&` falsy number render** (`NotificationPanel.tsx`): The JSX expression
   `{n.status === "running" && n.agentsTotal && n.agentsTotal > 0 && (...)}` evaluates to
   `"running" && 0` = `0` (the number) when `agentsTotal === 0`. React renders the number `0`
   as the text "0" directly in the DOM — the classic `&&` short-circuit with falsy numbers bug.

2. **Missing `currentPipelineNotifId.current` assignment** (`DashboardLayout.tsx`): The
   `pendingOdProtoParams` and `pendingOdPptParams` effects called `addRunningNotification`
   but never stored the notifId in `currentPipelineNotifId.current`. This meant all subsequent
   `updateProgress` and `updateAgentsTotal` calls (which check `currentPipelineNotifId.current`)
   never reached those notifications — progress stayed at 0.

3. **Wrong workflowType for od_ppt** (`DashboardLayout.tsx`): The `odProtoNotifCreated` fallback
   effect hardcoded `workflowType="prototype"` even when `pipelineState.pipeline_type === "od_ppt"`,
   causing PPT runs to show as "Prototype" in the notification.

#### Phase Context
- **Phase(s) involved:** Phase 22 — Capability Surfacing & User Empowerment (notification system)
- **Deleted code verified (not resurrected):** No deleted code involved
- **Locked decisions respected:** No architectural constraints violated; frontend-only fix

#### Fix Applied
| File | Change | Why |
|------|--------|-----|
| `frontend/src/components/ui/NotificationPanel.tsx` | Replaced `n.agentsTotal && n.agentsTotal > 0` with `(n.agentsTotal ?? 0) > 0` in both progress bar conditionals | Prevents React rendering the number `0` as visible text |
| `frontend/src/components/layout/DashboardLayout.tsx` | Added `currentPipelineNotifId.current = notifId` to both `pendingOdProtoParams` and `pendingOdPptParams` notification creation blocks | Progress updates now reach those notifications |
| `frontend/src/components/layout/DashboardLayout.tsx` | Fixed `odProtoNotifCreated` effect to use correct `workflowType` (`"ppt"` for od_ppt, `"prototype"` otherwise) | od_ppt runs now show correct "Presentation" label |

#### Invariants Verified
- **INV-1**: not affected — frontend-only
- **INV-3**: not affected — no output change
- **INV-12**: not applicable
- **SC-001**: not affected — no engine edit

#### Verification
- No TypeScript diagnostics after fix
- `(n.agentsTotal ?? 0) > 0` always returns boolean, never renders as text
- `currentPipelineNotifId.current` set before `addRunningNotification` so all update callbacks work


---

### FIX-022 — KAN-84: Revision input moved to left-panel expandable textarea

**Date:** 2026-06-30
**Triggered by:** `#velocity-ai-fix https://velocityai-hex.atlassian.net/browse/KAN-84`

#### Root Cause

The revision input was a thin `<input type="text">` bar (single-line, ~py-2 height) pinned at the bottom of the preview components on the RIGHT side of the screen (PPTPreview, PrototypePreview, UserStoryPreview, MarkdownPreview). Users couldn't type properly because the input was too thin and located far from the left-panel where they complete workflows.

KAN-84 requires revision to live in the left-panel "Suggested next steps" section as a proper expandable chat-style textarea with close/send controls.

#### Phase Context
- **Phase(s) involved:** Phase 22 — Capability Surfacing & User Empowerment (left panel UX)
- **Relevant register section:** `_register-parts/22-capability-surfacing-and-user-empowerment-universal-runtime-.md`
- **Deleted code verified (not resurrected):** No phase-deleted code involved
- **Locked decisions respected:** The existing `handleRevise*` callbacks in DashboardLayout are reused unchanged — only the entry point moves

#### Fix Applied

| File | Change | Why |
|------|--------|-----|
| `frontend/src/components/workflow/AgentProgressPanel.tsx` | Added `onRevise?` + `reviseLabel?` props; added `reviseOpen` state + `revisionText` state + `revisionRef`; added revision button in next-steps card that opens an expandable textarea with close (X) + send buttons; auto-focuses textarea on open; ⌘↵ keyboard shortcut | Provides the left-panel expandable textarea per KAN-84 spec |
| `frontend/src/components/layout/DashboardLayout.tsx` | Passed `onRevise` + `reviseLabel` to AgentProgressPanel (wired to existing `handleRevise*` functions); set `onRevise*` on PreviewPanel to `undefined` (removes thin right-panel bars) | Moves revision entry point to left panel; reuses all existing revision logic |

#### Invariants Verified
- **INV-1** (no pipeline_type branches): not affected — frontend-only change
- **INV-3** (golden parity): not affected — no engine, deliverable, or backend change
- **INV-12** (no duplication): existing `handleRevisePpt` / `handleRevisePrototype` / `handleReviseUserStory` / `handleReviseAppBuilder` in DashboardLayout reused as-is
- **SC-001** (zero engine edits): not affected — zero backend edit

#### Verification
- TypeScript diagnostics: No diagnostics found on both changed files
- Revision callbacks unchanged: the existing `handleRevise*` functions in DashboardLayout fire exactly as before — only the UI entry point changes
- PreviewPanel revision bars removed: `onRevise*` props set to `undefined` → no thin bars on right side
- Left panel: "Revise Presentation" / "Revise Prototype" / "Revise User Stories" / "Revise App Blueprint" button appears in next-steps card when pipeline completes; click → expandable textarea; close X → collapses; Send (or ⌘↵) → calls existing revision function

#### Notes
- The revision button appears INSIDE the "Suggested next steps" card (same card as chaining options), guarded by `onRevise && `. If `onRevise` is undefined (migration, custom, or incomplete states), no revision button shows.
- The textarea has `rows={3}` and is not `resize-none` — users can drag it larger if needed (satisfies "can expand the chat box").
- The close button satisfies "can close the chat box".
- After Send, the existing revision pipeline flow runs identically — run_revision WS dispatch, workflowType set to *_revision, etc.
