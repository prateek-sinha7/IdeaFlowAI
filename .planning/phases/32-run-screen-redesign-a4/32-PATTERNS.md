# Phase 32: Run-Screen Redesign [A4] - Pattern Map

**Mapped:** 2026-07-08
**Files analyzed:** 18 (13 frontend modify/add, 3 backend add, 1 e2e class, 1 token layer)
**Analogs found:** 17 / 18 (1 net-new: the token `@theme` status/brand ramp has no in-repo analog; DS mock + evidence 11 §B are the source)

> Scope note: this is a **reskin (reuse-don't-rebuild)** phase. Almost every "new" file is a **modify** of an existing component; the strongest analog is usually the file itself or its sibling. Styling in this repo is **inline Tailwind utility classes** (there is **no `cn()`/clsx/twMerge helper** and **no `components/ui` primitive library** — `components/ui/` holds only `CompletionToast`, `ErrorBoundary`, `NotificationPanel`). Tokens are **Tailwind v4 `@theme` in `frontend/src/styles/globals.css`** (`frontend/src/app/globals.css` is a one-line re-export; `tailwind.config.ts` is a stale/reference-only v3 palette, NOT the live theme).

---

## File Classification

| File | Role | Data Flow | Closest Analog | Match |
|------|------|-----------|----------------|-------|
| `frontend/src/styles/globals.css` | config (tokens) | transform (CSS vars) | itself (`:root` + `@theme inline`) | self / net-new values |
| `frontend/tailwind.config.ts` | config | — | itself (reference-only) | self |
| `frontend/src/components/ui/{Button,Card,Tabs,Badge,Pill}.tsx` | component (primitive) | request-response (props→JSX) | inline class idiom in `AgentProgressPanel.tsx` L59-92; `AGENT_ACCENT` const in `AgentThinkingTab.tsx` L31-38 | role-match (no primitive lib exists) |
| `frontend/src/components/chat/RunChatLane.tsx` | component | event-driven (props→composer) | itself (Phase-31) + `AgentProgressPanel.tsx` controls | self (absorb controls) |
| `frontend/src/hooks/useRunChat.ts` | hook | event-driven (WS→transcript) | itself | self (ISS-036 runId) |
| `frontend/src/hooks/useWorkflow.ts` | hook (reducer) | event-driven (WS events→state) | itself, `case "pipeline_cancelled"` L534 | self (ISS-035 + FIX-039) |
| `frontend/src/components/chat/InlineGateActions.tsx` | component | request-response (props→callbacks) | itself (Phase-31) | self |
| `frontend/src/components/chat/InlineClarifyActions.tsx` | component | request-response | `InlineGateActions.tsx` (sibling) | exact |
| `frontend/src/components/preview/ReviewGatePanel.tsx` | component | request-response | `InlineGateActions.tsx` (its inline mirror) | role-match |
| `frontend/src/components/layout/DashboardLayout.tsx` | component (tab host) | request-response | itself | self |
| `frontend/src/app/dashboard/page.tsx` | component (page/WS router) | event-driven | itself | self |
| `frontend/src/components/results/AgentThinkingTab.tsx` | component | transform (agents→L1/L2 tree) | itself | self (drill-down restructure) |
| `frontend/src/components/workflow/WaveTreePanel.tsx` | component | transform (waves→L3 tree) | itself | self (L3 mount) |
| `frontend/src/components/preview/PreviewPanel.tsx` | component | transform (mimetype dispatch) | itself (`FIRST_PARTY_RENDERERS` L601) | self (add switcher) |
| `frontend/src/types/index.ts` | model (types) | — | itself (SC-001 literal leak) | self |
| `backend/app/api/runs.py` (+3 endpoints) | route (read) | CRUD-read (DB→JSON) | **`get_hook_runs` L1021-1065** in same file | **exact** |
| `frontend/src/lib/exporters/auditExporter.ts` (add) | utility | transform (rows→CSV/JSON blob) | `frontend/src/lib/exporters/prototypeExporter.ts` | role-match |
| `frontend/e2e/tests/*.spec.ts` (harden) | test | — | `ts-i.agent-panels.spec.ts` L100-107 | exact (the brittle idiom) |

---

## Shared Patterns

### Token consumption (the D-15 dependency the rest of the shell gates on)
**Source:** `frontend/src/styles/globals.css` L8-46 — the live theme is **Tailwind v4 `@theme inline` + `:root` CSS vars**. `frontend/src/app/globals.css` is just `@import "../styles/globals.css";`. `tailwind.config.ts` is a **v3 reference stub and NOT read at runtime** (its comment says so) — do not put the new palette there expecting it to apply.
**Apply to:** every run-screen component.
**Current `:root` (to be replaced with evidence 11 §B values — black/beige/one-blue `#3C2CDA` + Manrope/Heebo + status ramp):**
```css
@theme inline {
  --font-sans: var(--font-inter), system-ui, -apple-system, sans-serif;
  --font-mono: "JetBrains Mono", "Fira Code", monospace;
}
:root {
  --background: #f5f5f0;  --foreground: #111827;
  --accent: #2563eb;  /* ← becomes one-blue #3C2CDA */
  --success: #059669;  --error: #dc2626;  --warning: #d97706;
}
```
**Gotcha:** the CANONICAL target values (running=blue `#3C2CDA`, "Not run"=grey, radius 10 buttons / 14 cards, status green/amber/red ramp, brand fill `#ECEAFC` / border `#DED9F7`) come from **`evidence 11 §B` (§B2 tokens, §B3 status model)**, NOT any single DS/Run mock — the mocks drift (Handoff's amber `running` is a bug). The status palette is NEW (DS documents zero status colors — §4.1). **Audit governance palette is the SOLE one-chroma exception (LOCK-F).**

### Inline-Tailwind styling idiom (there is no primitive library — you are creating it)
**Source:** `frontend/src/components/workflow/AgentProgressPanel.tsx` L59-92 — components compose raw utility strings with template-literal conditionals:
```tsx
className={`rounded-xl border transition-colors ${expanded ? "..." : "..."}`}
className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 text-[11px] font-bold"
<p className={`text-[12px] font-semibold leading-tight ${isIdle ? "text-gray-500" : "text-gray-900"}`}>
```
Single-accent constants are declared as a plain object per file — model the new Button/Badge variants on `AgentThinkingTab.tsx` L31-38:
```tsx
const AGENT_ACCENT = { bg: "bg-[#E8EDF5]", text: "text-[#1B2A4A]", border: "border-[#1B2A4A]/20", dot: "bg-[#1B2A4A]", glow: "" };
```
**Apply to:** the new `Button/Card/Tabs/Badge/Pill` primitives.
**Gotcha:** the whole codebase currently hardcodes navy `#1B2A4A` / `bg-gray-900` inline (`AGENT_ACCENT` above is the leak). The reskin must route these through the new tokens — **NO new hardcoded palette** (Deliverable 1). Primitives should live in `frontend/src/components/ui/` (existing home of `CompletionToast`/`ErrorBoundary`).

### SC-001 — generic-keying, no workflow-name literals
**Source (the invariant already lived correctly):** `InlineGateActions.tsx` L38-51 — the KAN-101 "Update the Specs" action renders off a **generic caller-supplied `updateSpecsEligible` flag, never a name literal**. `PreviewPanel.tsx` L586-601 (`FIRST_PARTY_RENDERERS` dispatch table) keys on `renderType`/mimetype, not workflow name.
**The leak to FIX:** the `prototype-analyze` / `prototype-specify` string literals appear at:
- `frontend/src/components/results/AgentThinkingTab.tsx` L608 (`.includes(a.id)` on a hardcoded list)
- `frontend/src/components/results/PrototypePipelineView.tsx` L389,391 (`agents.find(a => a.id === "prototype-specify")`)
- `frontend/src/types/index.ts` L615 (comment referencing `prototype-specify` agent_start)
- `frontend/src/components/workflow/AgentLibraryData.ts` L22-24 (data — likely legitimate registry data, confirm)
Replace the render-path literals with a **declared gate/artifact-kind flag** threaded from the event (the InlineGateActions `updateSpecsEligible` pattern is the reference).
**Apply to:** Steps drill-down, gate cards, Preview switcher.

---

## Pattern Assignments

### `backend/app/api/runs.py` — the 3 new read endpoints (route, CRUD-read) — **EXACT ANALOG**

**Analog:** `get_hook_runs` in the SAME file, **L1021-1065**. This endpoint is the precise template: owner-scoped two-layer resolve → 404, ordered rows, dict projection. The three target models (`GateEvent`, `ValidationResult`, `ExecRun`) are **already imported at L35/41/34** and already deleted-cascade-handled in `delete_run` (L446-450), so the tables exist and are engine-populated.

**Copy this shape verbatim** (from L1021-1065), swapping the model + projection:
```python
@router.get("/{workflow_id}/hook-runs")
async def get_hook_runs(
    workflow_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Layer 1: owner-scoped run resolve — cross-owner/missing → 404 (IDOR→404, D-08)
    workflow_run = (
        db.query(WorkflowRun)
        .filter(WorkflowRun.id == workflow_id, WorkflowRun.user_id == current_user.id)
        .first()
    )
    if not workflow_run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow run not found")
    # Layer 2: child rows filtered by run_id AND owner_id (defense in depth)
    rows = (
        db.query(HookRun)
        .filter(HookRun.run_id == workflow_id, HookRun.owner_id == current_user.id)
        .order_by(HookRun.created_at.asc())
        .all()
    )
    return {"workflow_id": workflow_id, "hook_runs": [ {...} for r in rows ]}
```

**Per-endpoint column projections** (from the model files — confirmed):
- `GET /api/runs/{id}/gate-events` → `GateEvent` (`gate_events.py`): `id, run_id, step, gate, outcome, detail(JSON), created_at`. Index `ix_gate_events_run` on `run_id` already exists → order by `created_at.asc()`.
- `GET /api/runs/{id}/validation-results` → `ValidationResult` (`validation_results.py`): `id, run_id, step, validator, severity(CRITICAL|HIGH|MEDIUM|LOW), attempt(int), issues(JSON), created_at`.
- `GET /api/runs/{id}/exec-runs` → `ExecRun` (`exec_runs.py`): `id, run_id, step, argv_json(JSON), outcome(allowed|denied|killed), exit_code(int|null), duration_ms(int|null), policy_snapshot_json(JSON), output_digest, created_at`. **Gotcha:** `output_digest` is a TRUNCATED digest, never raw secrets — surface as-is, do not attempt to expand.

**Auth pattern (VERBATIM, non-negotiable):** every model here carries `owner_id` + `workspace_id` (both `nullable=False`, AUTHZ-01). Use `.filter(Model.run_id == workflow_id, Model.owner_id == current_user.id)` — the `user_id`-keyed P13/P25 two-layer (NOT the nullable `owner_id` on WorkflowRun; on the child audit tables `owner_id` == the authed user id, mirroring `get_hook_runs` L1048). IDOR → 404, never 403 (docstring L14-19).

**Router registration:** already done — `runs.py` is mounted in `backend/app/main.py` L17 (`from app.api.runs import router as runs_router`). Adding methods to the existing `router` needs **no new registration**. **Import-linter:** these handlers stay app-side (`app/api/`), reading ORM models directly like `get_hook_runs` — NO `agents/` kernel import needed (contrast the `/artifacts` + `/events` endpoints L793/858 which DO route through `agents.authz.ScopedStore`; the 3 new ones can follow the simpler `get_hook_runs` direct-ORM path since the models are plain owner-scoped tables). Confirm 4/0 with `/opt/homebrew/bin/lint-imports`.

**Response schema analog:** `WorkflowRunResponse` L88-120 (Pydantic `BaseModel` + `model_config = {"from_attributes": True}`) OR the lighter inline-dict projection `get_hook_runs` uses (L1052-1064). For audit rows the inline-dict is the closest match and avoids a schema per table — prefer it unless the planner wants typed responses (then mirror `FamilyMemberResponse` L911-923).

---

### `frontend/src/hooks/useWorkflow.ts` — ISS-035 cancel-ack + FIX-039 ordering (hook/reducer)

**Analog:** itself. The `pipeline_cancelled` case is at **L534**; the FIX-039 unconditional accumulator reset is in `case "agent_start"` **L271-306** (comment L280-291 documents the ordering that MUST be preserved).
**ISS-035 fix location:** `case "pipeline_cancelled": L534` — today sets no cancelled flag and pushes no chat message, so `runLaneState` falls through to `idle`. Add the cancelled flag + a "Cancelled by you" chat push here (LIVE-STATE-CONTRACT §1). Note L491 already has a "Mirror pipeline_cancelled's teardown" reference in the failed path — keep them symmetric.
**Gotcha (FIX-039):** the accumulator reset in `agent_start` L280 is **unconditional** — do not gate it; a regenerate (2nd `agent_start`) must REPLACE not append (this is the bc016752 / 650b0064 fix). Do not reorder relative to the reset.

### `frontend/src/hooks/useRunChat.ts` — ISS-036 runId threading (hook)

**Analog:** itself, L54-62 (`runId: string | null` prop) + L148-174 (runId derivation from `data.run_id`). Today `useRunChat.runId` is bound to the clarify-only `activePipelineRunId` (null while building). Thread `pipelineState.pipelineRunId` in so the SSE command path would target the live run. **Gotcha (LOCK-B):** wire it correctly but leave SSE **dormant** — legacy WS stays the ACTIVE transport; do NOT activate or delete it.

### `frontend/src/components/chat/RunChatLane.tsx` — left lane absorbing AgentProgressPanel controls (component)

**Analog:** itself (Phase-31) for the composer/props (`RunChatLaneProps` L77-101: `onStop?` L95, `suggestions?: LaneSuggestion[]` L101, `GateContext` L59) + `AgentProgressPanel.tsx` **L248-253** (the Stop button) and **L299-358** (the revise textarea/modal) as the source of the controls to fold in.
```tsx
// AgentProgressPanel.tsx L248 — the Stop control to absorb into the lane composer
<button onClick={handleCancel}><Square className="h-3 w-3" /> Stop</button>
// L305 — revise-as-chat trigger; L347 onRevise(revisionText.trim())
```
**Gotcha:** RunChatLane already declares `onStop`, `onRevise`, and `suggestions` (L94-101) as GENERIC props — the plan-07 wiring threads them live. Suggestions render as chips at L255-264. SC-001: composer mode keys off generic props, never a workflow name (docstring L23-25).

### `frontend/src/components/chat/InlineClarifyActions.tsx` — inline clarify (component)

**Analog:** its exact sibling `InlineGateActions.tsx` L1-51 (same "compact in-lane mirror" doc pattern, same callback-driven presentational contract, same SC-001 generic-flag discipline). The full-panel counterpart being relocated inline is `ReviewGatePanel.tsx`. Both already exist from Phase 31 — this phase moves them from full-panel overlays to **inline Steps cards** + surfaces them in the lane.
**Gotcha:** carries the 4 KAN gate behaviors (KAN-101 update-specs off `updateSpecsEligible`, KAN-100 terminal fence `!isPipelineRunning`→render nothing, KAN-98 `retainAgentEdit`, KAN-95 reject-confirm) — all documented in `InlineGateActions.tsx` L26-48. Reuse KAN-100's cancel-aware gate wait; do NOT re-implement Stop-while-paused.

### `frontend/src/components/results/AgentThinkingTab.tsx` — Steps L1/L2 drill-down (component, transform)

**Analog:** itself. Props `AgentThinkingTabProps` L16-25 (agents[], pipelineState, the C2 "Context received" narrative surfaces — `runInput`, `originalBriefRootRunId`, `revisionParentVersion`, `clarifications`). The L2 "Context received" rail maps to these C2 props. It already imports `PrototypePipelineView`, `StartingPointCard`, `ClarificationsCard`.
**Gotcha:** L31-38 `AGENT_ACCENT` hardcodes navy `#1B2A4A` — reroute to tokens. L608 has the SC-001 literal leak (`["prototype-specify",...].includes(a.id)`) — fix to a declared flag. Preserve **KAN-99** (cap task checklist at N-1 until the build agent truly finishes — the final `task_progress` precedes the fix-loop).

### `frontend/src/components/workflow/WaveTreePanel.tsx` — Steps L3 fanout (component, transform)

**Analog:** itself. `WaveTreePanelProps` L26-32 (fed the assembled `waves: WaveGroup[]` as a prop — the parent's WS handler routes `wave_*`/`subagent_*` events and dedupes by `event_id`). `statusKind()` L34-45 is the free-string→bucket normalizer (running/completed/failed/pending; cancelled→failed terminal per IN-05).
**Gotcha (ISS-019):** WaveTreePanel sits below the fold today — the restructure must MOUNT it into the L3 drill-down. It is the fanout (`subagent_*`) source; `task_progress` is the task-loop source — the L3 is **dual-source** (both feed the drill-down per Phase-28 LIVE-STATE-CONTRACT).

### `frontend/src/components/preview/PreviewPanel.tsx` — Preview + manual switcher (component, transform)

**Analog:** itself, `FIRST_PARTY_RENDERERS` dispatch TABLE at **L586-628** (registered entries keyed on `renderType`, generic mimetype fallback = `GenericDeliverablePreview` L591). The 4 first-party renderers return bespoke output ONLY when their content is present, else fall through to the generic route.
```tsx
// PreviewPanel.tsx L601 / L625 — the dispatch to preserve; add the typed-renderer switcher as a MANUAL OVERRIDE on top
const FIRST_PARTY_RENDERERS: Record<string, () => ReactNode | null> = { ... };
const firstParty = FIRST_PARTY_RENDERERS[renderType]?.();
```
**Gotcha:** keep generic dispatch as PRIMARY (SC-001: dispatch on mimetype, never a workflow-name check — L525-531). The switcher is an additive manual override, not a replacement.

### `frontend/src/components/ui/{Button,Card,Tabs,Badge,Pill}.tsx` — NEW primitives (component)

**Analog:** none in-repo (no primitive lib). Model the API on the inline idiom (shared-patterns section above) + evidence 11 §B4 component idioms: Button `radius10 font 600 12.5px`; Card `#FCFBF7 border #E6E3DB radius14`; underline Tabs `active #15161A + 2px #3C2CDA` (§B4 / §6.9 — already near-consistent in the app); Badge `radius5 Manrope 600 8-8.5px`; Pill `radius999 border #E0DDD3`. Place in `frontend/src/components/ui/`.
**Gotcha:** every value must be a TOKEN, not a literal. Radius ladder + status ramp come from evidence 11 §B2/§B3.

### `frontend/src/lib/exporters/auditExporter.ts` — CSV/JSON export (utility, NEW)

**Analog:** `frontend/src/lib/exporters/prototypeExporter.ts` (`exportPrototype(content, filename?)` — pretty-print + blob download pattern). Model a `exportAuditCSV(rows)` / `exportAuditJSON(rows)` on the same blob-download shape.
**Gotcha (ND-6):** CSV/JSON ONLY — compliance-PDF export is deferred. Feed from the 3 new endpoints' rows.

### E2E hardening — `frontend/e2e/tests/*.spec.ts` (test)

**Analog:** the brittle idiom itself — `frontend/e2e/tests/ts-i.agent-panels.spec.ts` **L100-107**:
```ts
// The progress track is the h-0.5 bar; its fill is the navy (#1B2A4A) child.
const fill = bar.locator("div.bg-\\[\\#1B2A4A\\]");
```
Same brittle color-class / `toHaveClass` / `font-mono` assertions also in: `ts-chat-cards.spec.ts`, `ts-n.review-gate.spec.ts`, `ts-f.skills-hooks.spec.ts`, `ts-m.questionnaire.spec.ts`, `ts-c.input-trigger.spec.ts`.
**Fix pattern:** replace `.bg-[#1B2A4A]` locators and `toHaveClass([...])` color lists with `data-testid` locators (add the testids to the components in the same wave). **Gotcha:** verify BY DELTA against the pre-existing 128-red mocked baseline (DEF-29-06-1) — a passing count change, not absolute green. Run `npm run e2e` / mocked project.

---

## No Analog Found

| File | Role | Reason |
|------|------|--------|
| `frontend/src/styles/globals.css` status/brand ramp | config tokens | The status palette (green/amber/red) + one-blue `#3C2CDA` brand ramp + Manrope/Heebo are NET-NEW values — DS mock documents zero status colors (evidence 11 §4.1). No in-repo analog; source = evidence 11 §B2/§B3 + the DS mock `Hexaware Run - Design System.dc.html`. The FILE structure analog is the existing `:root`/`@theme` block (self). |

## Metadata

**Analog search scope:** `frontend/src/{components,hooks,lib,styles,app,types}`, `frontend/e2e/tests`, `backend/app/api`, `backend/app/models`, `backend/app/main.py`.
**Files scanned:** ~25 read/grepped.
**Key confirmations:** runs.py `get_hook_runs` is a drop-in template for all 3 endpoints; the 3 models (`gate_events`/`validation_results`/`exec_runs`) exist, are owner+workspace scoped (`nullable=False`), engine-populated, already imported + cascade-handled in runs.py; no `cn()` util and no primitive lib exist; live tokens are Tailwind-v4 `@theme` in `styles/globals.css` (tailwind.config.ts is inert); SC-001 literal leak located at 3 render-path sites.
**Pattern extraction date:** 2026-07-08
</content>
</invoke>
