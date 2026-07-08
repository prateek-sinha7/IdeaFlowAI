# Phase 32: Run-Screen Redesign [A4] — Research

**Researched:** 2026-07-08
**Domain:** Frontend reskin (Next.js/React/Tailwind v4) + 3 additive read-only FastAPI endpoints
**Confidence:** HIGH (nearly every claim is file:line-verified in this session; the few training-based claims are tagged)

> **Method note.** This is a *reuse-mapping* research pass, not a design pass. The visual design is LOCKED (D-15); token values are LOCKED in `evidence 11 §B`. Every "reuse vs add" call below is grounded in a grep/read of the live tree at HEAD (`new-workflow-engine`). Claims are tagged **[VERIFIED: file:line]**, **[CITED: doc]**, or **[ASSUMED]**.

---

<user_constraints>
## User Constraints (from 32-CONTEXT.md)

### Locked Decisions (do NOT re-open — POR §3 / D-15 / D-12 / LOCK-F)
- **Token layer FIRST**, then everything consumes it (no per-page palette fork). Tokens = DS mock EXTENDED with the status palette it omits + a resolved radius ladder (D-15 i). Shared-surface values come from **`evidence 11 §B`**, NOT any single mock (running=blue `#3C2CDA` is correct; Handoff's amber is a bug; "Not run"=grey).
- **Reskin-look, keep-behavior (D-15):** adopt the visual language; KEEP the product's richer live-data behavior and REUSE existing components (`AgentThinkingTab`, `WaveTreePanel`, `PreviewPanel`/`FIRST_PARTY_RENDERERS`, the Phase-31 `RunChatLane`) over rebuilding from the mock's stale/hardcoded versions — a face-value rebuild REGRESSES.
- **Live-state contract (D-12):** real event → lane render + composer mode + Steps behavior, per state; transcript ACCUMULATES; the mock's phase scrubber is excluded. Cancelled/degraded/planner-running/fix-loop are real states the mock omits — render them per `LIVE-STATE-CONTRACT.md`.
- **Inline gate-card behaviors:** KAN-101 (Update-the-Specs + "Accept & continue to build" relabel — **generalized off a declared gate/artifact-kind flag, NOT the `prototype-analyze`/`prototype-specify` literals**), KAN-95 (reject-confirm + navigate-home), KAN-100 (`isPipelineRunning` guard + terminal auto-dismiss + `approve_review`→`pipeline_not_running`), KAN-98 (`retainAgentEdit`). Reuse KAN-100's cancel-aware gate wait — do NOT re-implement Stop-while-paused.
- **Output name "Deliverable"** (LOCK-F). **Audit governance palette** (green/amber/red) is the SOLE one-chroma exception.

### Claude's Discretion
- Wave/task splitting; primitive component API shapes; exact Steps drill-down interaction; CSV/JSON export field selection; where to place `data-testid`s; whether the Audit reader uses a new `ScopedStore.read_validation_results` vs a direct app-layer ORM query (both additive, both valid).

### Deferred Ideas (OUT OF SCOPE)
- SSE activation (LOCK-B — legacy WS stays ACTIVE; ISS-036 wires runId correctly but leaves SSE dormant). Compliance-PDF export (ND-6 — CSV/JSON only). Concierge LLM (Phase 33). Shell chrome / nav / other pages (Phase 35+; the ~370 `#1B2A4A` shell sites are NOT this phase). Handoff screen (post-v2.0). ISS-037 MED/LOW cluster — fold in opportunistically only where the rework already touches that code, else leave tracked.
</user_constraints>

<phase_requirements>
## Phase Requirements (ROADMAP Phase 32 SC 1–4)

| ID | Description | Research Support |
|----|-------------|------------------|
| SC-1 | Token layer (black/beige/one-blue `#3C2CDA`, Manrope/Heebo) + primitives land first; run screens consume them (no new hardcoded palette). | §1.1 (token layer map) + §Landmines |
| SC-2 | Steps renders the 3-level drill-down (overview spine → agent detail + Context-received rail → task detail, dual-source) from real events; gate/clarify render inline in Steps. | §1.4 (Steps) + §4 (KAN) + STEPS-ARTIFACT-DERIVATION-CONTRACT |
| SC-3 | Audit tab reads the 3 endpoints (`gate_events`/`validation_results`/`exec_runs`) with counters/filters + CSV/JSON export; governance keeps the status palette; one-chroma elsewhere. | §3 (endpoints) |
| SC-4 | Failed/degraded/cancelled states faithful (P16 affordances + chat card); e2e green with brittle color assertions fixed + `data-testid`s added. | §5 (ISS-035) + §6 (e2e) + LIVE-STATE-CONTRACT §1 |
</phase_requirements>

## Summary

The run screen is **already substantially wired for this reskin** — this is the single most important planning fact. The Phase-31 `RunChatLane` is already mounted as the left column of `DashboardLayout` **[VERIFIED: DashboardLayout.tsx:1592]**, with `AgentProgressPanel` deliberately **retained alongside it** for Phase 32 to finish absorbing/removing **[VERIFIED: DashboardLayout.tsx:1623, comment :1585]**. The right-panel tab host already has four tabs — **Preview / Files / Thinking / Audit** **[VERIFIED: PreviewPanel.tsx:310-313]** — so "Steps" is a **rename+restructure of the existing "Thinking" tab** (`AgentThinkingTab` + `WaveTreePanel`), not a new tab. An `AuditTab.tsx` already exists but reads the wrong data source (`hook_runs` via `getRunHookRuns`) **[VERIFIED: AuditTab.tsx:16, :20]** — Phase 32 repoints it at the three new endpoints. All four KAN gate behaviors are **already implemented generically and SC-001-clean** in `InlineGateActions.tsx` (Phase 31) **[VERIFIED: InlineGateActions.tsx:50,101,138 + header doc]**. The three backend tables (`gate_events`/`validation_results`/`exec_runs`) already exist with owner+workspace scoping **[VERIFIED: backend/app/models/*.py]** — the endpoints are pure additive reads with **no migration**.

The real work concentrates in four risk areas: (1) the **token layer** — a Tailwind v4 `@theme` rewrite of `src/styles/globals.css` swapping Inter/Fraunces→Manrope/Heebo and `#2563eb`→`#3C2CDA` plus the full `evidence 11 §B` families; (2) the **SC-001 literal leak**, which is NOT purely front-end — the `review_gate_ready` payload currently carries **no analyze/update-specs discriminator** (only generic `redoable`) **[VERIFIED: engine.py:4503-4516]**, so generalizing off `agentId === "prototype-analyze"` **[VERIFIED: ReviewGatePanel.tsx:253]** requires an **additive golden-neutral backend flag** using the proven `redoable`/`_VOLATILE_STRIP_KEYS` pattern; (3) **ISS-035** — the `pipeline_cancelled` handler sets no cancelled marker and pushes no transcript line **[VERIFIED: useWorkflow.ts:534-566]**, so `runLaneState` falls to `idle`, and the fix must thread through FIX-039-sensitive code; (4) the **3-level Steps drill-down** restructure, which is dual-source and carries the KAN-99 N-1 cap.

**Primary recommendation:** Sequence as CONTEXT specifies — **Wave 0 = token layer + primitives (own wave, blocks everything)**, then Wave 1 = left-lane completion (fold ISS-035 + ISS-036), Wave 2 = Steps 3-level restructure + KAN carry-over + SC-001 backend flag, Wave 3 = Audit endpoints + tab, Wave 4 = failed/degraded/cancelled affordances + e2e hardening. Verify BY DELTA (mocked Playwright vs the 128-red baseline); never run full backend pytest.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Token layer / primitives | Frontend (CSS `@theme` + React) | — | `src/styles/globals.css` Tailwind v4 tokens; primitives are pure client components |
| Chat lane + composer modes | Frontend (React hooks) | — | `RunChatLane` + `useRunChat` + `useWorkflow` reducer; transport-agnostic |
| Steps drill-down | Frontend (React) | Backend (event payloads — read-only) | Renders live WS events already emitted; no new backend events |
| SC-001 gate-kind flag | **Backend (engine payload)** | Frontend (consume flag) | `review_gate_ready` must gain a generic discriminator; FE currently leaks literals |
| Audit reads | **Backend (FastAPI `app.api`)** | Frontend (fetch + render) | Owner-scoped reads over existing tables; app-layer per import-linter |
| Cancel-ack (ISS-035) | Frontend (reducer) | — | `pipeline_cancelled` already arrives; FE must surface it |
| runId threading (ISS-036) | Frontend (hook wiring) | — | Pure FE prop change; SSE stays dormant |
| CSV/JSON export | Frontend (client-side) | — | ND-6: client-side only, no backend export endpoint |

---

## 1. Reuse Map (per surface)

### 1.1 Token layer (SC-1) — **the blocking dependency for Phases 34/35/36/37**

| Item | Reuse / Add | Detail |
|------|-------------|--------|
| Source of truth file | **REWRITE** | The live token file is **`frontend/src/styles/globals.css`** (Tailwind **v4**, `@theme inline` + `:root` CSS vars) **[VERIFIED: styles/globals.css:1-46]**. `frontend/src/app/globals.css` is a 1-line `@import` shim **[VERIFIED]**. |
| `tailwind.config.ts` | **IGNORE as source of truth** | It is a vestigial "reference" (navy `#001f3f`) — v4 does theme via CSS `@theme`, per the file's own header **[VERIFIED: tailwind.config.ts:6-9]**. Do not treat it as the palette. |
| Current tokens (to replace) | REPLACE | `--accent: #2563eb`, `--background: #f5f5f0`, `--font-sans: Inter`, `--font-serif: Fraunces`, `--font-mono: JetBrains Mono` **[VERIFIED: styles/globals.css:9-33]**. |
| Fonts | ADD | `layout.tsx:2` loads `Inter, Fraunces` via `next/font/google` **[VERIFIED]** → swap to **Manrope + Heebo** (+ `'SF Mono', ui-monospace, Menlo, monospace` code token). |
| Token families to add | ADD (verbatim from `evidence 11 §B2`) | Brand `#3C2CDA`/`#3324C4`/`#ECEAFC`/`#DED9F7`/`#8E88E8`; warm ink ramp `#15161A…#A0A199`; surfaces `#F0EEE7`/`#F6F4EE`/`#FCFBF7`/`#FFFFFF`/`#111114`/`#0C0D12`; lines `#E6E3DB`/`#E2DFD6`/`#E0DDD3`; **status** green `#1F7A4D` / red `#A33A32` / amber `#9A6B1E` / running-blue `#3C2CDA` / neutral-grey `#9A9B92` (each with fill+border tints). **Radius ladder LOCKED: button=10, card=14** (5 tags, 8 nodes, 11 rows, 12 menus, 18 hero, 999 pills). |
| Primitives | ADD (new) | Button / Card / Tabs / Badge / Pill — new token-consuming components. No existing shared primitive set found; run components inline Tailwind classes today. |

**Blast radius (do NOT boil the ocean):** `#1B2A4A` (old navy) appears **370 times across 54 files** **[VERIFIED: grep count]** — but most are shell/admin/login/settings/workflow-wizard pages that belong to **Phase 35+**. Phase 32 converts only the **run-screen subtree** (DashboardLayout + chat + results + preview + workflow panels that mount on the run). Leaving other pages on the old navy is expected and correct.

### 1.2 Chat-lane mount (SC-2/SC-4)

| Item | Reuse / Add | Detail |
|------|-------------|--------|
| `RunChatLane` | **REUSE (already mounted)** | Left column, absorbing controls — already in place **[VERIFIED: DashboardLayout.tsx:1592, RunChatLane.tsx]**. `RunLaneState` is already the generic SC-001-clean union `idle\|building\|clarify\|gate\|complete\|terminal` **[VERIFIED: RunChatLane.tsx:50-56]**. `GateContext` already has generic `updateSpecsEligible`/`approveLabel` **[VERIFIED: RunChatLane.tsx:66-67]**. |
| `AgentProgressPanel` | **ABSORB then REMOVE** | Currently RETAINED as a capped secondary panel below the lane **[VERIFIED: DashboardLayout.tsx:1623]**; its Stop/revise/suggestions are already absorbed into RunChatLane props (`onStop`/`onRevise`/`onRelaunch`/`suggestions`) **[VERIFIED: RunChatLane.tsx:94-102]**. Phase 32 completes the absorption and deletes the duplicate mount (INV-3: no dual impl). Pre-existing test `AgentProgressPanel.test.tsx` (ISS-022) is a known-baseline red — don't be misled by it. |
| Suggestions-as-chips | REUSE | `LaneSuggestion`/`onSuggestion` props exist **[VERIFIED: RunChatLane.tsx:71-75,100-102]**. |

### 1.3 Tab shell (SC-2/SC-3)

The right-panel host lives in **`PreviewPanel.tsx`**, tab ids `preview\|files\|thinking\|audit` **[VERIFIED: PreviewPanel.tsx:236, :310-313, :318]**. Tab bodies dispatch at `:717-796`.
- **"Thinking" → "Steps":** relabel + restructure (see §1.4). Body currently renders `<AgentThinkingTab>` **[VERIFIED: PreviewPanel.tsx:789]**.
- **"Audit":** body renders `<AuditTab>` **[VERIFIED: PreviewPanel.tsx:12 import, tab render ~:794]** — repoint data source (see §3).
- **Preview switcher:** `FIRST_PARTY_RENDERERS` is a `Record<string,()=>ReactNode>` keyed on `renderType` with generic dispatch **[VERIFIED: PreviewPanel.tsx:601, :625]** — KEEP; add a manual typed-renderer override on top (do not replace the generic dispatch). Files-tab fallback + `deliverable_mimetype` generic path already exist (ISS-021 groundwork).
- `PreviewPanel.degraded.test.tsx` already exists — reuse as the degraded-affordance harness anchor.

### 1.4 Steps 3-level drill-down (SC-2)

Restructure **`AgentThinkingTab.tsx` (702 lines)** + **`WaveTreePanel.tsx` (140 lines)** into L1→L2→L3, per `STEPS-ARTIFACT-DERIVATION-CONTRACT.md`:
- **L1 overview spine:** status line + per-agent progress + clarifications block + trace rows with inline gate strips.
- **L2 agent detail:** reasoning, artifact blocks ×4 kinds, tool calls, full input prompt, output, summary, handoff, sticky **"Context received" rail** (from `agent_input.context_sources`).
- **L3 task detail — DUAL SOURCE:** `task_progress` (task-loop; emitted `engine.py:3108`) **AND** `subagent_*`/`wave_*` (fanout; `wave_scheduler.py:268/298`, `fanout.py:508`) **[VERIFIED: contract §2 + engine grep]**.
- **The 4 artifact kinds:** `pages`←`route_table.py`; `tasks`←`task_list` artifact; `checks`←`validation_results`; `construction`←dual-source above **[CITED: STEPS-ARTIFACT-DERIVATION-CONTRACT §1]**.
- **KAN-99 N-1 cap:** the final `task_progress` fires BEFORE the fix-loop; cap the checklist at N-1 until `agent_complete` — do NOT treat `completed_count == total-1` as a stall **[CITED: contract §3 + LIVE-STATE-CONTRACT §2d]**.
- **ISS-019 fold:** `WaveTreePanel` sits below the fold today (`DashboardLayout.tsx:1158-1190` flex-budget) — the drill-down restructure naturally mounts it into L3, resolving the below-fold problem. `WaveTreePanel` mounts unconditionally at `DashboardLayout.tsx:1639` today **[VERIFIED]**.
- **Gate/clarify relocate inline:** move from full-panel overlays (`ReviewGatePanel`) to inline Steps cards. `InlineGateActions`/`InlineClarifyActions` (Phase 31) are the ready-made generic inline components to reuse **[VERIFIED: RunChatLane.tsx:40-43 imports]**.

### 1.5 Preview switcher — see §1.3. Keep `FIRST_PARTY_RENDERERS` generic dispatch; add manual override only.

### 1.6 Audit endpoints + UI — see §3.

### 1.7 Failed/degraded/cancelled affordances (SC-4)

- Existing `DegradedRunAffordance` (ISS-017/024, in `PreviewPanel` + `WorkflowHistory.tsx`) and `parseFailedAgents.ts` are the reuse base for P16 affordances. Server `status ∈ {failed,cancelled,degraded}` gates them (`page.tsx:1315`, `DashboardLayout.tsx` status thread) **[VERIFIED: grep]**.
- **"What went wrong" chat card:** new RunChatLane render for the `terminal`/failed state (LIVE-STATE-CONTRACT §1 failed row: `agents_failed[]` + sanitized error). The `terminal` RunLaneState already exists as the target **[VERIFIED: RunChatLane.tsx:56]**.
- **Cancelled:** the missing ack — see §5 (ISS-035).

---

## 2. SC-001 Literal-Leak Remediation

**The FE receives NO analyze/update-specs discriminator from the backend today.** `review_gate_ready.data` carries only `pipeline_run_id / agent_id / agent_name / gate_key / output / redoable / timestamp` **[VERIFIED: engine.py:4503-4516]**. So every "is this an analyze gate?" decision on the FE is currently made by matching the **agent-id string literal** — that IS the leak.

### Production (load-bearing) literal sites

| # | File:line | Literal | Drives | Fix |
|---|-----------|---------|--------|-----|
| L1 | `ReviewGatePanel.tsx:251-253` | `=== "prototype-specify"/"prototype-plan"/"prototype-analyze"` | `isSpec/isTasks/isAnalysis` → icon, label, description, **and the Update-Specs affordance** | Drive off a declared kind flag; or relocate inline (reuse `InlineGateActions`) and drop the literal-labeled panel |
| L2 | `useWorkflow.ts:293` | `agentId === "prototype-specify"` | `isSpecifyRerun` → `specRevisionCount` bump (revision-cycle badge) | Drive off a generic "spec-revision re-run" signal (a re-fired `agent_start` on an already-`done` agent is itself the generic signal — the `wasAlreadyDone` check at `:292` is already generic; the literal is redundant guard, replace with a declared-flag check) |
| L3 | `AgentThinkingTab.tsx:608` | `["prototype-specify","prototype-plan","prototype-analyze","prototype-build","prototype-validate"].includes(a.id)` | prototype-specific view gating in the Thinking/Steps tab | Generalize to a declared workflow/artifact-kind check (the Steps restructure touches this file anyway) |
| L4 | `PrototypePipelineView.tsx:389-391` | finds agents by the 3 literals | prototype pipeline view | Legacy prototype-only view; confirm whether Steps supersedes it, else generalize |

### Out-of-Phase-32 literal sites (do NOT touch here)
- `AgentsPopup.tsx:99,135`, `AgentLibraryData.ts:22-24`, `ReviewGatesSection.test.tsx` — these are the **composer/config** surface = **Phase 37** (evidence 08 / ND-12). Leave them.
- `types/index.ts:615` is a **comment**, not code.

### The proper generalization (backend-additive, golden-neutral)

`_artifact_kind_for(spec)` already exists on the engine (`_AGENT_KIND_MAP`, fallback `"summary"`) **[VERIFIED: engine.py:5226-5234]**. The sanctioned fix mirrors the **`redoable` precedent exactly**: stamp a generic discriminator (e.g. `update_specs_eligible: bool` and/or `artifact_kind: str`) onto `review_gate_ready.data`, and add the new key(s) to **`_VOLATILE_STRIP_KEYS`** so the 5 characterization goldens stay byte-identical. The normalizer already strips `redoable` and explicitly documents this as the pattern to mirror **[VERIFIED: tests/agents/characterization/_normalize.py:142-157]**. The FE then drives `updateSpecsEligible`/`approveLabel` off the payload flag — the wiring props already exist **[VERIFIED: InlineGateActions.tsx:50, RunChatLane.tsx:66]**.

**[ASSUMED]** that adding `update_specs_eligible` to `_VOLATILE_STRIP_KEYS` is sufficient for byte-identity — this must be proven empirically (run the 5 goldens post-change). The precedent is strong but the phase must verify, not presume.

---

## 3. The 3 Audit Endpoints (SC-3)

### Endpoint pattern (owner-scoped read, IDOR→404)

- **Router:** `backend/app/api/runs.py`, `APIRouter(prefix="/api/runs")` **[VERIFIED: runs.py:46]**, mounted `main.py:175`. New endpoints land here (or a sibling `app.api.audit` router sharing the prefix — multiple routers per prefix is already the pattern, `main.py:178,197`).
- **The two-layer owner check (P13/P25 precedent):** `db.query(WorkflowRun).filter(WorkflowRun.id == workflow_id, WorkflowRun.user_id == current_user.id).first()` → `HTTPException(404)` on miss **[VERIFIED: runs.py:397-405; get_run]**. Uses `user_id` (the principal), **NOT** the nullable `owner_id`.
- **Best template to copy:** `run_files.py` documents the exact two-layer check (ORM filter → 404, capturing `workspace_id`; then a default-deny `ScopedStore.get_run(run_id) is None` → 404) **[VERIFIED: run_files.py header + :1-40]**. `get_hook_runs` (`runs.py:1021`) is the closest existing **read** analog + its FE client `getRunHookRuns` (`api.ts:928`, `GET /api/runs/{id}/hook-runs`) **[VERIFIED]** — clone both.
- **import-linter (4/0):** the endpoints live app-side (`app.api`), which is the CALLER; the forbidden direction is `agents.* → app` only **[VERIFIED: pyproject.toml:134-185, 4 contracts]**. So `app.api.runs` importing `agents.authz.ScopedStore` (or querying models directly) is legal and keeps the contract green.

### Tables (already exist — NO migration; additive-only)

| Endpoint | Table | Columns available (owner_id+workspace_id+run_id on all) |
|----------|-------|----------------------------------------------------------|
| `GET /api/runs/{id}/gate-events` | `gate_events` | `step, gate(human\|validation\|approval\|security), outcome(pass\|block\|wait_human), detail(JSON), created_at` **[VERIFIED: models/gate_events.py:31-41]** |
| `GET /api/runs/{id}/validation-results` | `validation_results` | `step, validator, severity(CRITICAL\|HIGH\|MEDIUM\|LOW), attempt, issues(JSON list), created_at` **[VERIFIED: models/validation_results.py:31-42]** |
| `GET /api/runs/{id}/exec-runs` | `exec_runs` | `step, argv_json, outcome(allowed\|denied\|killed), exit_code, duration_ms, policy_snapshot_json, output_digest(truncated), created_at` **[VERIFIED: models/exec_runs.py:32-45]** |

- Tables landed in alembic `0016_capability_hardening_tables` / `0018_exec_runs` **[VERIFIED: alembic dir grep]**. All three carry `owner_id`+`workspace_id` `nullable=False` (AUTHZ-01) + `run_id` FK. **Additive-only confirmed** — no new table, no migration.
- **Reader seam GAP:** `ScopedStore` has `read_gate_events` **[VERIFIED: authz.py:831]** and `read_exec_runs` **[VERIFIED: authz.py:972]**, but **no `read_validation_results`** **[VERIFIED: grep of `async def read`]**. Phase 32 either (a) adds the missing scoped reader (mirroring the two existing ones — owner+ws-scoped `_scope_owner_ws`, `authz.py:119`), or (b) queries `validation_results` directly in the app layer scoped by `run_id`+`owner_id`+`workspace_id` (the `runs.py` ORM idiom). Both additive; discretion.

### UI + export
- Repoint `AuditTab.tsx` (currently `getRunHookRuns` → hook_runs **[VERIFIED: AuditTab.tsx:16-20]**) to fetch the three endpoints; add client-side stat counters / coverage chips / severity filters.
- **CSV/JSON export = client-side only (ND-6)** — no backend export route. Compliance-PDF is deferred.
- **Governance palette is the SOLE one-chroma exception** — green/amber/red status colors are permitted only in the Audit governance verdicts (evidence 11 §B "status-palette exception").

---

## 4. The 4 Inline-Gate KAN Behaviors + KAN-99

**Nearly all already built generically in `InlineGateActions.tsx` (Phase 31), SC-001-clean** **[VERIFIED: InlineGateActions.tsx header doc + code]**:

| KAN | Behavior | Where today | Carry-over to Phase 32 |
|-----|----------|-------------|------------------------|
| **KAN-101** | Update-Specs action + "Accept & continue to build" relabel, **generalized off `updateSpecsEligible` flag** (NOT a literal) | `InlineGateActions.tsx:50,101` (`canUpdateSpecs = !!onUpdateSpecs && !!updateSpecsEligible`); `approveLabel` at `:189` | Reuse verbatim in Steps inline cards; **but** the `updateSpecsEligible` flag is not yet fed from a backend payload — see §2 (needs the additive `review_gate_ready` flag). The full-panel `ReviewGatePanel.tsx:251-305` still uses literals for its labels — relocate/generalize. |
| **KAN-95** | Reject → two-step confirm + navigate-home-on-reject | `InlineGateActions.tsx:79` (two-step confirm); navigate-home wrapper at `DashboardLayout.tsx:1238-1240` | Reuse; keep the navigate-home wrapper wired |
| **KAN-100** | `isPipelineRunning` guard + terminal auto-dismiss; `approve_review`→`pipeline_not_running` | `InlineGateActions.tsx:52,138` (`if (!isPipelineRunning) return null`); backend fence `engine.py:4490-4498` + `_run_review_gate` cancel race `:4523-4529` | Reuse both halves. **Do NOT re-implement Stop-while-paused** — the cancel-aware gate wait already exists |
| **KAN-98** | `retainAgentEdit` — gate edit persisted, not echoed; client retains | `page.tsx` exposes `retainAgentEdit` **[VERIFIED: page.tsx:873]**; `ReviewGatePanel.tsx:265-273` resets edits on fresh gate | Reuse |
| **KAN-99** | Cap Steps checklist at N-1 until build truly finishes | `LIVE-STATE-CONTRACT §2d` + `STEPS-ARTIFACT-DERIVATION-CONTRACT §3` | **Implement in the Steps construction block** — final `task_progress` precedes the fix-loop; reach N only on `agent_complete` |

**Key finding:** the KAN behaviors are done in the **chat-lane inline** surface. The carry-over work is (a) making the SAME generic components render in the **Steps** inline cards, and (b) supplying the `updateSpecsEligible` flag from the backend (§2) so KAN-101 works without the literal.

---

## 5. ISS-035 (cancel-ack) + ISS-036 (runId) — exact sites + FIX-039-safe editing

### ISS-035 — no "Cancelled by you" ack
- **Root site:** `useWorkflow.ts:534-566` — the `pipeline_cancelled` case resets in-flight agents to `"idle"` and sets `isRunning:false`, `totalDuration`, `completedCount` — **but sets NO cancelled marker on `pipelineState` and pushes NO chat message** **[VERIFIED: useWorkflow.ts:534-566]**. Consequently `runLaneState` has nothing to derive `terminal`/cancelled from → falls to `idle`, violating LIVE-STATE-CONTRACT §1 (which requires "Cancelled by you" line + relaunch mode).
- **Fix shape:** add a cancelled marker to `pipelineState` (e.g. a terminal-reason field) so RunChatLane derives the existing `terminal` `RunLaneState` **[VERIFIED: RunChatLane.tsx:56]**, and surface a "Cancelled by you" transcript line + "Run again". `WorkflowStatus` already includes `"cancelled"` **[VERIFIED: types/index.ts:311]**.
- **FIX-039 safety:** the sensitive ordering is in the **`agent_start` case** (`useWorkflow.ts:280-315`) — the unconditional per-run accumulator reset that must run BEFORE `status:"running"`. The `pipeline_cancelled` case is a **different case block** and does not touch that reset, so ISS-035 edits are FIX-039-safe **as long as they stay inside the `pipeline_cancelled` case and do not reorder or duplicate the `agent_start` reset** **[VERIFIED: FIX-REGISTER FIX-039 (2026-07-07) + useWorkflow.ts:280-315]**.

### ISS-036 — runId bound to clarify-only id
- **Root site:** `page.tsx:917-918` — `useRunChat({ runId: activePipelineRunId, ... })` **[VERIFIED]**. `activePipelineRunId` is set from a clarify event's `pipeline_run_id` (`page.tsx:813`) and is **null while building** **[VERIFIED: page.tsx:158, :813]**.
- **Fix:** thread the live building run id. `pipelineState` carries `pipelineRunId` (referenced `page.tsx:813,165`) **[VERIFIED: grep]** — pass `runId: pipelineState.pipelineRunId ?? activePipelineRunId`. **Pure FE prop change.**
- **LOCK-B:** SSE stays dormant (`NEXT_PUBLIC_SSE_TRANSPORT` OFF, `RunConnectionProvider` unmounted). The fix corrects the latent bug (SSE-ON would `POST /api/runs` and spawn a new run per message) but must NOT activate SSE. The active transport remains legacy WS.

---

## 6. E2E Brittleness (SC-4)

Verify BY DELTA against the pre-existing **128-red mocked baseline** (DEF-29-06-1) — absolute-green is NOT the target.

**Brittle color/class assertions to replace (run-screen-adjacent specs):**

| File:line | Assertion | Fix |
|-----------|-----------|-----|
| `e2e/tests/ts-m.questionnaire.spec.ts:57,79,83` | `toHaveClass(/bg-\[#1B2A4A\]/)` (selected-state) | token class or `data-testid` + `data-selected` **[VERIFIED]** |
| `e2e/tests/ts-c.input-trigger.spec.ts:149,150` | `toHaveClass(/bg-\[#1B2A4A\]/)` (selected tile) | same **[VERIFIED]** |
| `e2e/tests/ts-i.agent-panels.spec.ts:100,107` | `div.bg-\[#1B2A4A\]` progress-fill locator | `data-testid` on the fill **[VERIFIED]** |
| `e2e/tests/ts-f.skills-hooks.spec.ts:95` | `toHaveClass(/bg-gray-900/)` (count pill) | token class or testid **[VERIFIED]** |
| `e2e/tests/ts-n.review-gate.spec.ts:139,183` | `locator("textarea.font-mono")` | `data-testid` on the gate textarea **[VERIFIED]** |

**Add first `data-testid`s on chat surfaces** (POR §72): the chat lane, gate/clarify inline cards, and Steps drill-down levels. Role/text selectors survive the reskin (POR §7) — prefer them; add testids only where color/class was load-bearing.

---

## Runtime State Inventory

This is a reskin + additive-endpoints phase (no rename/data-migration). For completeness against the required categories:

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None — the 3 Audit tables already exist and are engine-populated; endpoints only READ. Verified via `backend/app/models/*.py` + alembic 0016/0018. | None |
| Live service config | None — no external service config embeds run-screen state. | None |
| OS-registered state | None. | None |
| Secrets/env vars | `NEXT_PUBLIC_SSE_TRANSPORT` (must remain OFF — LOCK-B). No new secrets. | Leave OFF |
| Build artifacts | None — pure FE recompile + additive Python. `tailwind.config.ts` is vestigial (not a build source under v4). | None |

---

## Common Pitfalls

### Pitfall 1: Treating SC-001 as FE-only
`review_gate_ready` carries no analyze discriminator today (§2). A FE-only "delete the literal" leaves nothing to drive `updateSpecsEligible`. **Avoid:** add the golden-neutral backend flag first, prove the 5 goldens byte-identical, then wire FE.

### Pitfall 2: Breaking FIX-039 ordering
Editing `useWorkflow.ts` for ISS-035 near the `agent_start` reset block risks reordering the unconditional accumulator reset. **Avoid:** keep ISS-035 edits inside the `pipeline_cancelled` case only.

### Pitfall 3: Running full backend pytest
It HANGS offline (Chromium/Bedrock/Postgres-gated). **Avoid:** run only the 5 characterization goldens + targeted suites + `/opt/homebrew/bin/lint-imports`.

### Pitfall 4: Chasing absolute-green e2e
The mocked baseline is 128-red. **Avoid:** verify BY DELTA — assert your specs move, not that the suite is green.

### Pitfall 5: Rebuilding from the mock
The mock hardcodes stale rosters/8-cap composers/bool-retry. **Avoid:** reuse `AgentThinkingTab`/`WaveTreePanel`/`PreviewPanel`/`RunChatLane` (D-15 rule).

### Pitfall 6: Reskinning the whole app
370 `#1B2A4A` sites exist; only the run subtree is Phase 32. **Avoid:** touching admin/login/settings/wizard pages (Phase 35+).

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Adding `update_specs_eligible`/`artifact_kind` to `review_gate_ready.data` + `_VOLATILE_STRIP_KEYS` keeps the 5 goldens byte-identical | §2 | If wrong, INV-3 breaks — MUST run goldens before relying on it. Precedent (`redoable`) is strong. |
| A2 | `pipelineState.pipelineRunId` is populated during Building (not just clarify) | §5 ISS-036 | If null while building too, ISS-036 needs a deeper source; verify at wiring time |
| A3 | Manrope + Heebo are available via `next/font/google` | §1.1 | If unavailable, self-host; low risk (both are Google Fonts per evidence 11) |
| A4 | The "Thinking" tab is the right host to become "Steps" (vs a brand-new tab) | §1.3 | Low — restructure vs new-tab is a planning choice; both reuse the same components |

## Open Questions

1. **Does `PrototypePipelineView.tsx` survive the Steps restructure, or is it superseded?**
   - Known: it uses the 3 literals (`:389-391`) and is a prototype-only view.
   - Unclear: whether Steps L1/L2 fully replaces it.
   - Recommendation: planner decides delete-vs-generalize; if kept, generalize the literals (INV-3 no-dual-impl favors deletion if Steps covers it).

2. **New `ScopedStore.read_validation_results` vs direct app-layer ORM query for the validation-results endpoint?**
   - Both additive and import-linter-safe. Recommendation: add the reader for symmetry with the other two (`read_gate_events`/`read_exec_runs`), keeping all three audit reads on one scoped seam.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Node/npm (vitest, playwright, tsc) | FE build + tests | ✓ (assumed — repo builds today) | — | — |
| `python3.11` | backend endpoints + goldens | ✓ | 3.11 (no venv) | — |
| `/opt/homebrew/bin/lint-imports` | import-linter 4/0 gate | ✓ (memory-confirmed) | — | — |
| Chromium (render_check) | NOT needed for this phase's checks | — | — | render_check degrades to skip |
| Live Bedrock / Postgres | NOT needed offline | ✗ (SSO/interactive) | — | Live-deferred to Phase 34 |

**Missing with no fallback:** none for offline structural proof. **Live-deferred:** any visual/multimodal confirmation → Phase 34 live pass.

---

## Validation Architecture

> Nyquist enabled (no `workflow.nyquist_validation:false` found). Verify BY DELTA; never run full backend pytest.

### Test Framework
| Property | Value |
|----------|-------|
| FE unit | **vitest** `^4.1.5` — `cd frontend && npm test` (= `vitest --run`) **[VERIFIED: package.json:9,43]** |
| FE e2e | **Playwright** `^1.56.0` mocked — `npm run e2e` (`playwright test --project=mocked`) **[VERIFIED: package.json:11]** — verify BY DELTA vs 128-red baseline |
| FE types | `tsc --noEmit` identity |
| Backend | `python3.11 -m pytest` targeted (5 characterization goldens) + `/opt/homebrew/bin/lint-imports` |
| Goldens | `backend/tests/agents/test_characterization_{prototype,prototype_revision,od_ppt,od_prototype,app_builder}.py` **[VERIFIED: ls]** |

### SC → Signal → Test Map
| SC | Observable signal | Offline test |
|----|-------------------|--------------|
| SC-1 tokens | Run components resolve `#3C2CDA`/Manrope from `@theme`; no new hardcoded palette | vitest render + a grep guard "no new `#1B2A4A`/`#2563eb` in run subtree"; `tsc --noEmit` |
| SC-2 Steps drill-down | L1/L2/L3 render from real events; KAN-99 caps at N-1; gate/clarify inline | vitest unit on the Steps components with scripted event fixtures; mocked-Playwright delta on the Steps tab |
| SC-2 SC-001 flag | `review_gate_ready` carries the generic flag; goldens byte-identical | **5 characterization goldens (byte-identical)** + banned-pattern gate; vitest on InlineGateActions eligibility |
| SC-3 Audit | 3 endpoints return owner-scoped rows; IDOR→404; counters/filters/export render | backend targeted pytest on the new endpoints (owner-scope + 404); `lint-imports` 4/0; vitest on AuditTab + export |
| SC-4 cancelled/failed | `pipeline_cancelled` → "Cancelled by you" + relaunch; failed → "What went wrong" card | vitest on useWorkflow `pipeline_cancelled` reducer (asserts cancelled marker) + RunChatLane terminal render; mocked-Playwright delta |
| SC-4 e2e | brittle color assertions replaced by token/testid; specs move green | mocked-Playwright DELTA on ts-m/ts-c/ts-i/ts-f/ts-n |

### Sampling Rate
- **Per task commit:** `npm test` (vitest) + `tsc --noEmit` for FE tasks; `python3.11 -m pytest <targeted>` + `lint-imports` for backend tasks.
- **Per wave merge:** full vitest + mocked Playwright delta + 5 goldens.
- **Phase gate:** 5 goldens byte-identical + lint-imports 4/0 + e2e delta positive before `/gsd-verify-work`.

### Wave 0 Gaps
- [ ] New Audit endpoint tests (owner-scope + IDOR→404) — clone `get_hook_runs` test pattern.
- [ ] Steps drill-down component tests (scripted `task_progress`/`wave_*`/`subagent_*` fixtures; KAN-99 N-1 assertion).
- [ ] `useWorkflow` `pipeline_cancelled` reducer test (asserts the new cancelled marker) — ISS-035 regression guard.
- [ ] SC-001 backend flag: extend the goldens' `_VOLATILE_STRIP_KEYS` and re-assert byte-identity.
- [ ] Token-guard grep test (no new `#1B2A4A`/raw palette in the run subtree).
- (Framework already installed — vitest + Playwright + pytest all present.)

---

## Security Domain

> `security_enforcement` not explicitly false → included. This phase adds only READ endpoints + FE reskin.

### Applicable ASVS Categories
| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | `Depends(get_current_user)` on all 3 endpoints (existing dep) |
| V4 Access Control | **yes (primary)** | Two-layer owner check `WorkflowRun.user_id == current_user.id` → **404 (never 403)**; `owner_id`+`workspace_id` scoping on the tables (AUTHZ-01). IDOR resolves to 404, no existence oracle |
| V5 Input Validation | yes | path param is a run id (UUID); no body on GETs; export is client-side (no injection surface) |
| V6 Cryptography | no | no crypto in scope |
| V7 Error Handling / Logging | yes | `exec_runs.output_digest` is TRUNCATED (never raw secrets) — surface digest only, never raw child output |

### Known Threat Patterns for {FastAPI + SQLAlchemy owner-scoped reads}
| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| IDOR on `{run_id}` | Elevation/Info-disclosure | two-layer `user_id`-keyed filter → 404 (P13/P25) **[VERIFIED: runs.py:397-405]** |
| Cross-owner row leak | Info-disclosure | `_scope_owner_ws` / owner+ws filter on the audit tables **[VERIFIED: authz.py:119, model owner_id/workspace_id]** |
| Secret leak via exec output | Info-disclosure | `output_digest` truncated by design **[VERIFIED: models/exec_runs.py:42]** |
| SQL injection | Tampering | SQLAlchemy ORM parameterized queries (no raw SQL) |

---

## Sources

### Primary (HIGH — read/grep this session)
- Live tree at HEAD (`new-workflow-engine`): `PreviewPanel.tsx`, `RunChatLane.tsx`, `useWorkflow.ts`, `useRunChat.ts`, `InlineGateActions.tsx`, `ReviewGatePanel.tsx`, `DashboardLayout.tsx`, `AuditTab.tsx`, `AgentThinkingTab.tsx`, `WaveTreePanel.tsx`, `styles/globals.css`, `tailwind.config.ts`, `layout.tsx`, `backend/app/api/runs.py`, `run_files.py`, `backend/app/models/{gate_events,validation_results,exec_runs}.py`, `backend/agents/authz.py`, `backend/agents/execution_engine/engine.py`, `backend/pyproject.toml`, `tests/agents/characterization/_normalize.py`, e2e specs.
- `.planning/phases/28-*/contracts/LIVE-STATE-CONTRACT.md`, `STEPS-ARTIFACT-DERIVATION-CONTRACT.md`.
- `.planning/v2.0-evidence/11-cross-mock-reconciliation.md §B` (token/status source of truth).
- POR `.planning/CHAT-AND-UI-CONVERGENCE-PLAN.md §72/§95/§51/§29/§31`; `32-CONTEXT.md`; `ROADMAP.md` Phase 32 SC 1-4; `ISSUES-REGISTER.md` (ISS-035/036/037/019); `FIX-REGISTER.md` FIX-039; `backend/CLAUDE.md`.

### Secondary (MEDIUM)
- Grep counts (370 `#1B2A4A` / 54 files) — mechanical, unverified per-site classification.

### Tertiary (LOW / ASSUMED)
- Golden byte-identity of the SC-001 flag change (A1) — precedent-based, must be proven.
- `pipelineState.pipelineRunId` populated during Building (A2) — inferred from grep, verify at wiring.

## Metadata

**Confidence breakdown:**
- Reuse map / stack: HIGH — every surface file:line-verified.
- Backend endpoints: HIGH — pattern, tables, scoping, import-linter all verified; one reader-seam gap noted.
- SC-001 remediation: HIGH on the leak sites + pattern; MEDIUM on golden-neutrality (A1, must prove).
- Pitfalls / landmines: HIGH.

**Research date:** 2026-07-08
**Valid until:** ~2026-08-07 (stable brownfield; re-verify file:line if the branch advances materially).

---

## Landmines / Do-Not-Touch (enforced constraints)

- **INV-13:** no engine/runner change to the agent loop — the ONLY sanctioned backend edit is the additive golden-neutral `review_gate_ready` flag (§2) + the 3 read endpoints. `deep_agent_runner` / `create_deep_agent` untouched.
- **INV-3:** the 5 characterization goldens stay byte/event-identical. The FE reskin can't touch them by construction; the SC-001 backend flag MUST be `_VOLATILE_STRIP_KEYS`-stripped and proven byte-identical (A1).
- **FIX-039 ordering:** preserve the unconditional per-run accumulator reset in the `agent_start` case (`useWorkflow.ts:280-315`); keep ISS-035 edits in the `pipeline_cancelled` case.
- **LOCK-B:** legacy WebSocket stays the ACTIVE transport; ISS-036 wires runId correctly but must NOT activate SSE (`NEXT_PUBLIC_SSE_TRANSPORT` stays OFF).
- **Additive migrations only (Q3):** the 3 tables exist — NO migration. Every add carries `owner_id`+`workspace_id`.
- **import-linter 4/0:** endpoints app-side (`app.api`); never make `agents.* → app`.
- **SC-001:** Steps/gate/Preview keyed on GENERIC event/artifact types + declared flags, NEVER a workflow name — and FIX the existing `prototype-analyze`/`prototype-specify` leak (§2).
