# Phase 36: Home + History + My Workflows [B2] - Research

**Researched:** 2026-07-09
**Domain:** Frontend restructure of three list surfaces + one new run-detail page + one additive read-only backend endpoint (Next.js/React/TypeScript FE · FastAPI/SQLAlchemy BE)
**Confidence:** HIGH (every load-bearing claim grounded in file:line read this session or a command run this session)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **`WorkflowCatalog`→`HomeLaunchGrid` rename (D-11)** lands in THIS phase (deferred from 35) — the component IS the home launch grid. "Catalogue" stays reserved (never a saved-workflows label; reserved for the future shared/org marketplace).
- **Fused Home** merges the `input`/`home` views (P22 already made the catalog the home landing) — one launcher + deliverable grid + recents.
- **Preserve KAN-96** (running→live view, terminal→detail) + **KAN-92** (real async titles, not `Revision:` placeholders) — these are shipped behaviors; do NOT regress them.
- **Run-summary endpoint aggregates EXISTING data** (per-agent, KPIs, failure banner, version timeline) — additive READ-only, owner-scoped, NO new tables. Reuse the P13/P25 owner-gate pattern.
- **Reskin-look, keep-behavior (D-15):** REUSE existing components + the product's richer behavior; consume the Phase-32 tokens + Phase-35 shell; NO per-page palette fork.

### Claude's Discretion
- Auto-generated context (discuss skipped via `workflow.skip_discuss`). No explicit discretion areas were carved out; all decisions are locked to the POR §84 + D-11/D-15 + ROADMAP SC. Treat visual layout details of the fused Home / run-detail page as discretion within the D-15 "adopt mock visual language, keep product behavior" envelope.

### Deferred Ideas (OUT OF SCOPE)
- Analytics aggregations + live notifications feed (Phase 38).
- Configure/Composer/Wizard (Phase 37).
- Concierge live-wiring (Phase 34).
- Team-sharing / workflow-visibility (LOCK-E).
- Handoff screen (post-v2.0).
- The mocked-Playwright e2e run (offline webServer timeout — **live-deferred** like Phase 35; capture a baseline only).

INVARIANTS (from CONTEXT `<decisions>`): **SC-001** (list/detail surfaces keyed on generic run data, NEVER a workflow-name branch — INV-1), **INV-3** (the run-summary endpoint is additive read-only; the 5 backend goldens untouched by construction), **token authority** (consume Phase-32 `@theme` tokens + `ui/` primitives; per-file grep-clean of retired palette `#1B2A4A/#2563eb/#f5f5f0/Inter/Fraunces/JetBrains` = 0 + no stray stock palette), **owner-scoped run-summary** (two-layer `WorkflowRun.user_id == principal` → 404, NOT the nullable `owner_id`; import-linter 4/0), **additive migrations only** (Q3 — none), **a11y**, **LOCK-B** (no transport touch).
</user_constraints>

<phase_requirements>
## Phase Requirements

Source: `.planning/REQUIREMENTS.md:249-250` (SHELL-02, SHELL-03). SHELL-01 belongs to Phase 35.

| ID | Description | Research Support |
|----|-------------|------------------|
| SHELL-02 | Fused Home (launcher+grid+recents); History grouping/sort/delete; **My Workflows** rename + kebab actions; `WorkflowCatalog`→`HomeLaunchGrid`; "Catalogue" reserved for future marketplace (D-11) | Rename map (§Rename), fused-home merge (§Home), history grouping/sort/delete (§History), My Workflows label rename + kebab-already-wired (§My Workflows) |
| SHELL-03 | Run detail/reopen page off a run-summary endpoint aggregating existing data (agents, KPIs, failure banner, version timeline) | run-summary endpoint aggregation shape + owner-gate clone (§Run Detail + Endpoint); existing WorkflowHistory detail view is the reuse basis |
</phase_requirements>

## Summary

This is a **frontend-heavy restructure of three already-built, already-wired list surfaces** plus **one new run-detail page** and **one additive read-only backend endpoint**. Almost nothing here is greenfield: the launch grid (`WorkflowCatalog`), history (`WorkflowHistory`), and saved-workflows (`SavedWorkflowsPage`) all exist, fetch live data, and carry rich behavior (KAN-92 titles, KAN-96 click-branch, revision families, delete, kebab CRUD). The D-15 mandate is explicit: **adopt the mock's visual language, keep the product's richer behavior, reuse components — a face-value rebuild would REGRESS.**

The single largest correctness risk is **not** any of the four feature deliverables — it is the **token migration discipline**. `WorkflowHistory.tsx` alone carries 102 stock-Tailwind palette classes and 37 raw `#hex` literals (`grep` run this session), and all three surfaces still use the dead `var(--font-fraunces)` var (which resolves to nothing — `--font-fraunces` is defined nowhere; the live fonts are Manrope/Heebo per `src/app/layout.tsx:2,7,16`). The retired-palette grep-to-zero gate (`#1B2A4A`, `#f5f5f0`, `fraunces`) is mechanically enforceable and MUST hit 0 per file; the broader "no stray stock palette" is a reskin-quality bar over a large surface.

Two `<decisions>` claims are **already partially satisfied and must not be re-done**: (1) the AppHeader nav pill already reads **"My Workflows"** (`AppHeader.tsx:98`) — only the in-page `<h1>` heading "Workflow Catalogue" (`SavedWorkflowsPage.tsx:202`) still needs relabeling; (2) the SavedWorkflows kebab actions (Rename/Duplicate/Delete) are **already fully wired** to real `api.ts` calls (`SavedWorkflowsPage.tsx:118-186`) — the History DELETE route is also already wired (`WorkflowHistory.tsx:263-276` → `deleteWorkflow`). "Real kebab actions" and "real delete wiring" are largely **verification-and-reskin**, not net-new plumbing.

**Primary recommendation:** Sequence as a single FE-first phase — (1) grep-all-callers rename to grep-count-0; (2) fuse `input`+`home` into one landing keeping generic page-keys; (3) restructure History (grouping+sort off existing fields, verify KAN-96/KAN-92 tests stay green); (4) relabel My Workflows + verify kebab; (5) build the run-detail page over a cloned owner-gated `GET /api/runs/{id}/summary` endpoint aggregating existing columns; (6) token-migrate all touched files to grep-clean. Verify offline by delta (vitest + tsc + grep + targeted backend suites + lint-imports 4/0); mocked Playwright is live-deferred.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Component rename (`WorkflowCatalog`→`HomeLaunchGrid`) | Browser/Client (React module) | — | Pure FE module identity + import graph; no data/transport change |
| Fused Home (launcher+grid+recents) | Browser/Client (DashboardLayout view state) | API (existing `GET /api/workflows`, `/api/runs`) | View composition is client `mainView` state; rows still come from existing endpoints |
| History grouping (Today/Earlier/Older) + sort (tokens/duration) | Browser/Client | — | Grouping/sort derive from `created_at`/`token_usage`/`duration` already on each list row; pure client transform |
| History delete | API (`DELETE /api/runs/{id}` — EXISTS) | Browser/Client (wiring exists) | Real delete route already present; FE already calls it |
| My Workflows label + kebab CRUD | Browser/Client | API (`/api/user-workflows` CRUD — EXISTS) | Kebab already wired to existing CRUD; only label reskin remains |
| Run-detail page render | Browser/Client | API (new run-summary read) | Page is FE; its data spine is the new aggregation read |
| Run-summary aggregation | API/Backend (`app/api/runs.py`) | Database/Storage (existing `workflow_runs` + child tables) | Owner-scoped read over EXISTING columns; no new table |

## Standard Stack

No new dependencies. This phase extends the existing stack (CLAUDE.md: "extend, don't replace"). Verified in-repo tooling versions this session:

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Next.js / React | (in-repo) | The FE app (`frontend/src/app`, App Router) | Existing; `"use client"` component tree |
| TypeScript | (in-repo, `tsc --noEmit`) | Type identity gate | Existing project gate |
| vitest | 4.1.5 (`npx vitest --version`) | FE unit/component tests | Existing FE test runner |
| motion/react | (in-repo) | Animations (`motion.div`, `AnimatePresence`) | Already used across all three surfaces |
| lucide-react | (in-repo) | Icons | Already used across all three surfaces |
| FastAPI + SQLAlchemy | (in-repo) | Backend runs API + ORM | Existing `app/api/runs.py` pattern to clone |
| python3.11 | `/opt/homebrew/bin/python3.11` (verified present) | Backend test runtime (no venv) | Per dev-runtime memory note |

### Supporting (existing helpers to reuse — do NOT rebuild)
| Helper | Location | Purpose |
|--------|----------|---------|
| `groupRunsByFamily`, `FamilyGroupCard`, `VersionTimeline`, `baseWorkflowType` | `frontend/src/components/history/RevisionFamilyView.tsx` | Revision-family grouping + timeline (History reuse) |
| `parseFailedAgentIds`, `buildAgentNameById` | `frontend/src/lib/parseFailedAgents.ts` | Shared failed-agent parsing (live + reopen; no dual-impl) |
| `DegradedRunAffordance` | exported from `frontend/src/components/preview/PreviewPanel` | Terminal-failure affordance (shared live+history) |
| `resolveReopenMimetype` | `frontend/src/types/index` | Generic deliverable mimetype dispatch (SC-001) |
| `_compute_root_ids`, `_run_response`, `_owner_gate_or_404` | `backend/app/api/runs.py:134,215,1068` | Owner-scoped root-walk + response builder + IDOR→404 gate to CLONE |
| `@theme` token layer | `frontend/src/styles/globals.css:12-175` | The Phase-32 canonical tokens to consume |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| New `GET /api/runs/{id}/summary` aggregation endpoint | Client-side aggregation from existing `/{id}` + `/{id}/family` + `/{id}/events` | POR §84/§96 explicitly names a "run-summary endpoint"; a server aggregation is one owner-scoped round-trip and keeps the KPI math in one tested place. Recommend the endpoint. |
| Backend sort fields for History | Client-side sort over existing `token_usage`/`duration` on the list rows | Evidence 12 says "Fields exist" — `WorkflowRunResponse` already returns `token_usage` + `duration` (`runs.py:99,101`). **No backend change needed for sort.** |

**Installation:** none.

**Version verification:** No packages added. Existing runtime confirmed: vitest 4.1.5, python3.11 present, lint-imports present (`/opt/homebrew/bin/lint-imports`).

## Package Legitimacy Audit

Not applicable — this phase installs **no external packages**. All work extends in-repo modules. (Slopcheck/registry gate skipped by construction; there is nothing to install.)

## Architecture Patterns

### System Architecture Diagram

```
                         ┌─────────────────────────────────────────────┐
   User nav (AppHeader)  │  DashboardLayout  (mainView state machine)   │
   Home·Library·         │                                              │
   My Workflows ────────►│  mainView ∈ {home, library, history,         │
                         │    settings, analytics, input*, execution,   │
                         │    saved-workflows, (+run-detail?)}           │
                         └───────┬───────────┬───────────┬──────────────┘
                                 │           │           │
             ┌───────────────────┘           │           └────────────────┐
             ▼                               ▼                            ▼
   ┌───────────────────┐          ┌────────────────────┐      ┌────────────────────┐
   │  FUSED HOME       │          │  HISTORY           │      │  MY WORKFLOWS       │
   │  HomeLaunchGrid   │          │  WorkflowHistory   │      │  SavedWorkflowsPage │
   │  (was Workflow    │          │  list + detail     │      │  grid + kebab CRUD  │
   │   Catalog)        │          │                    │      │                     │
   │ + prompt launcher │          │ group Today/Earlier│      │ label→"My Workflows"│
   │   (from `input`)  │          │  /Older; sort      │      │ kebab already wired │
   │ + deliverable grid│          │  tokens/duration;  │      └─────────┬───────────┘
   │ + recents strip   │          │  delete (wired)    │                │
   └─────────┬─────────┘          │  KAN-96 click-branch│               │
             │                    └────────┬───────────┘                │
             │ GET /api/workflows           │ click terminal run        │
             │ (user_launchable)            ▼                           │
             │                    ┌────────────────────┐                │
             │                    │  RUN DETAIL (NEW)  │                │
             │                    │  Steps/Preview/    │                │
             │                    │  Files/Audit +     │                │
             │                    │  KPI/failure/      │                │
             │                    │  version timeline  │                │
             │                    └────────┬───────────┘                │
             │                             │                            │
             ▼                             ▼                            ▼
   ┌──────────────────────────────────────────────────────────────────────────┐
   │  api.ts client  (getWorkflowDefinitions, getWorkflows, getWorkflow,       │
   │   deleteWorkflow, getRunFamily, getUserWorkflows + CRUD, NEW getRunSummary)│
   └──────────────────────────────┬───────────────────────────────────────────┘
                                   ▼
   ┌──────────────────────────────────────────────────────────────────────────┐
   │  FastAPI  app/api/runs.py   (owner-scoped: WorkflowRun.user_id==principal) │
   │   EXISTING: GET "" · GET /{id} · DELETE /{id} · /{id}/events · /{id}/family │
   │   NEW (additive, read-only): GET /{id}/summary  → aggregates:              │
   │     agent_outputs(JSON) → per-agent breakdown                              │
   │     token_usage(JSON) + duration(Float) + agent_count → KPI stats          │
   │     error + status → failure banner                                        │
   │     _compute_root_ids + BFS (from /family) → version/revision timeline     │
   └──────────────────────────────┬───────────────────────────────────────────┘
                                   ▼
   ┌──────────────────────────────────────────────────────────────────────────┐
   │  PostgreSQL  workflow_runs (+ existing child tables; NO new table)         │
   └──────────────────────────────────────────────────────────────────────────┘

  * `input` view is being MERGED INTO `home` (fused launcher). Keep the page-key
    GENERIC — never branch a route on a workflow name (SC-001).
```

### Recommended Project Structure (deltas only)
```
frontend/src/components/
├── home/                       # NEW folder (D-11) — or keep catalog/ dir, rename file only
│   └── HomeLaunchGrid.tsx      # was catalog/WorkflowCatalog.tsx
│   └── HomeLaunchGrid.test.tsx # was catalog/WorkflowCatalog.test.tsx
├── history/
│   └── WorkflowHistory.tsx     # + Today/Earlier/Older grouping, token/duration sort
│   └── RunDetailPage.tsx       # NEW-BUILD (or restructure the in-panel detail view)
├── savedworkflows/
│   └── SavedWorkflowsPage.tsx  # label "Workflow Catalogue" → "My Workflows"
└── layout/
    └── DashboardLayout.tsx     # fuse input+home; repoint HomeLaunchGrid import

backend/app/api/
└── runs.py                     # + GET /{id}/summary (additive, owner-scoped read)
```
> **Rename dir decision (Claude's discretion within D-11):** the component may stay in `catalog/` or move to `home/`. Moving to `home/` better expresses intent but multiplies path-churn in the two DashboardLayout test mocks. Recommend **renaming the file within `catalog/` OR moving to `home/`** — either is acceptable; the hard gate is `grep -c "WorkflowCatalog" frontend/src == 0`. NOTE: "Catalogue"/`catalog/` dir name is a developer-facing path, not a user-facing label; the D-11 "Catalogue reserved" rule is about USER-FACING labels. Leaving the dir named `catalog/` does not violate D-11, but renaming to `home/` removes the mock↔product name trap entirely.

### Pattern 1: Owner-scoped read endpoint (CLONE for run-summary)
**What:** Every run read gates on `WorkflowRun.user_id == current_user.id` → cross-owner/missing resolves to **404, never 403** (no existence leak).
**When to use:** The new `GET /api/runs/{id}/summary` — mirror this exactly.
**Example:**
```python
# Source: backend/app/api/runs.py:1068-1085 (_owner_gate_or_404 — the P13/P25 precedent)
def _owner_gate_or_404(db: Session, workflow_id: str, user_id: str) -> WorkflowRun:
    workflow_run = (
        db.query(WorkflowRun)
        .filter(WorkflowRun.id == workflow_id, WorkflowRun.user_id == user_id)  # principal, NOT owner_id
        .first()
    )
    if not workflow_run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow run not found")
    return workflow_run
```
The summary handler: `run = _owner_gate_or_404(db, workflow_id, current_user.id)`, then parse `run.agent_outputs` (JSON) / `run.token_usage` (JSON) and reuse `_compute_root_ids` + the `/family` BFS (`runs.py:933-1018`) for the version timeline. **Use `user_id`, never the nullable backfilled `owner_id`** (`workflow.py:58` — `owner_id` is nullable).

### Pattern 2: Grep-all-callers rename (SC-001-safe)
**What:** Rename the component and repoint every importer, keeping routes/page-keys generic.
**When:** The `WorkflowCatalog`→`HomeLaunchGrid` rename.
**The exact reference inventory (verified `grep -rn "WorkflowCatalog" frontend/src` this session — 7 files):**

| File | Line(s) | Kind of ref | Edit |
|------|---------|-------------|------|
| `components/catalog/WorkflowCatalog.tsx` | 4, 44, 52, 55 | export `function WorkflowCatalog`, `interface WorkflowCatalogProps`, doc header | Rename file + symbol → `HomeLaunchGrid` / `HomeLaunchGridProps` |
| `components/catalog/WorkflowCatalog.test.tsx` | 68 (import), 139/148/186/224/234/245/254/277/305 (usages) | named import + JSX renders | Rename file + import + JSX |
| `components/layout/DashboardLayout.tsx` | 9 (import), 1429 (JSX `<WorkflowCatalog .../>`), 1413/1567 (comments) | live import + mount | Repoint import + JSX symbol + comments |
| `components/layout/DashboardLayout.catalogHome.test.tsx` | 52-53 (`vi.mock("@/components/catalog/WorkflowCatalog", … WorkflowCatalog: …)`), 129/131/134/136 (assertions) | **module-path mock** + testid | Update mock path + symbol; testid `stub-workflow-catalog` may stay or rename |
| `components/layout/DashboardLayout.waveMount.test.tsx` | 64-65 (`vi.mock(...)`) | **module-path mock** | Update mock path + symbol |
| `components/savedworkflows/SavedWorkflowsPage.tsx` | 192 | comment only ("matches WorkflowCatalog style") | Update comment |
| `lib/api.ts` | 613, 629 | comments only | Update comments |

**Load-bearing gotcha:** the two `vi.mock("@/components/catalog/WorkflowCatalog", …)` calls hard-code the **module path**. If the file moves to `home/`, these paths MUST update or the mock silently no-ops and the real component mounts (its `getToken()`→localStorage fetch then fails in jsdom). Prove `grep -c "WorkflowCatalog" frontend/src == 0` after.

### Pattern 3: Fused Home — view-state merge (keep page-keys generic)
**What:** Today `mainView="home"` renders `<WorkflowCatalog>` (`DashboardLayout.tsx:1420-1431`); `mainView="input"` renders `<IdeaInputPage>` (`:1546-1574`). Selecting a workflow from home calls `handleSelectFeature` which sets `mainView="input"` (`:807-811`). **Fusing** means the landing carries the prompt launcher + deliverable grid + recents together, so a brief can be entered without the intermediate `input` navigation for the generic path.
**When:** SHELL-02 fused Home.
**Constraints:**
- Keep `mainView` union values generic — the union is `"home" | "library" | "history" | "settings" | "analytics" | "input" | "execution" | "catalog" | "saved-workflows"` (`:173`). Never add a workflow-name-keyed view (SC-001).
- The wizard-routed types (`prototype`, `ppt`, and `CHAIN_OPTIONS.requiresWizard`) still `router.push` to their template wizards (`WorkflowCatalog.tsx:94-110`) — the fused launcher must preserve that fork.
- `recentRuns?: WorkflowRun[]` is already a DashboardLayout prop (`:68`) — the recents strip consumes it; no new fetch needed.
- The `input` view still exists for saved-workflow preload (`handleLaunchSaved` sets `mainView="input"` with `savedComposition`, `:866-879`) — do NOT delete the `input` view wholesale; fuse the launcher UI onto home while keeping `input` reachable for the preload path. (INV-3: deleting a still-referenced view would break saved-workflow launch.)

### Pattern 4: History grouping + sort (client-side, existing fields)
**What:** Add Today/Earlier/Older buckets and a tokens/duration sort over the flat run list.
**Data available on each list row (no backend change):** `WorkflowRunResponse` returns `created_at` (bucket key), `token_usage` (JSON string → the tokNum sort field), `duration` (Float seconds → the durSec sort field) — `runs.py:99,101,117`. The FE `WorkflowRun` type already surfaces `tokenUsage` and `duration` (used at `WorkflowHistory.tsx:480,485-492`).
**Reuse:** The list is grouped by family first via `groupRunsByFamily(runs)` (`WorkflowHistory.tsx:885`) then filtered. Today/Earlier/Older is an ADDITIONAL grouping layer over the family cards — apply it to `visibleFamilies` keyed on `group.root.created_at`. Sort applies within/across buckets.

### Anti-Patterns to Avoid
- **Rebuilding History/SavedWorkflows from the mock.** D-15 rule iii: the product is truth. The mock's "Catalogue" page is a naming trap (`WorkflowCatalog` shows launchable definitions; the mock "Catalogue" shows saved workflows — opposite content). Map by content, never by name (POR §9 / D-11).
- **Adding a run-summary field the model lacks.** Every field the summary needs already exists on `WorkflowRun` (`workflow.py:19-91`). Inventing a column = an unsanctioned migration (violates Q3 additive-only + the phase's "NO new tables").
- **Using `owner_id` in the owner gate.** It is nullable/backfilled (`workflow.py:58`). Use `user_id` (the principal) — the entire `runs.py` surface does (`:250,398,431,…`).
- **A per-page palette fork.** Consume the shared `@theme` tokens; do not introduce a new color for these pages (D-15 / token authority).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Revision-family grouping/timeline | Custom family walker in the new page | `groupRunsByFamily` / `VersionTimeline` (`RevisionFamilyView.tsx`) + BE `/{id}/family` (`runs.py:933`) | Owner-scoped BFS + cycle guard already correct + tested (`test_runs_api_family.py`) |
| Terminal-failure affordance | New "failed run" UI | `DegradedRunAffordance` (exported from `PreviewPanel`) | One component → live + history-reopen cannot drift (ISS-017) |
| Failed-agent id→name resolution | Re-parse the error string | `parseFailedAgentIds` + `buildAgentNameById` (`lib/parseFailedAgents.ts`) | Shared parser; no dual-impl |
| Owner gate / IDOR→404 | New auth check on the summary route | `_owner_gate_or_404` (`runs.py:1068`) | The P13/P25 precedent; 404-not-403 posture proven |
| Root/family computation | Recursive CTE or new walk | `_compute_root_ids` (`runs.py:134`) | SQLite+Postgres portable, memoized, cycle-guarded |
| Delete (run + child rows) | New delete plumbing | `DELETE /api/runs/{id}` (`runs.py:411`) + FE `deleteWorkflow` (already wired, `WorkflowHistory.tsx:269`) | Real delete ALREADY EXISTS — History delete is FE wiring only |
| Saved-workflow CRUD (rename/dup/delete) | New kebab handlers | Already wired: `handleRenameSave`/`handleDuplicate`/`handleDeleteConfirm` → `renameUserWorkflow`/`createUserWorkflow`/`deleteUserWorkflow` (`SavedWorkflowsPage.tsx:118-186`) | Kebab is already real — verify + reskin only |

**Key insight:** The "new work" in this phase is thinner than it reads. Delete, kebab CRUD, family timeline, failure affordance, and owner-gating are all shipped. The genuinely-new artifacts are: (a) the fused-home layout, (b) the Today/Earlier/Older grouping + sort transform, (c) the run-detail page composition, and (d) the additive `GET /{id}/summary` endpoint. Everything else is rename + reskin + verify-still-green.

## Runtime State Inventory

> This is a FE rename/restructure + additive BE read. There is NO stored-data rename, NO live-service config rename, NO OS-registered state, NO secret rename. But the `WorkflowCatalog`→`HomeLaunchGrid` rename has a real (compile-time) blast radius.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | **None** — no DB key, collection, user_id, or persisted string references the symbol `WorkflowCatalog`. The rename is a source-symbol + module-path change only. Verified: `grep -rn "WorkflowCatalog"` returns only `.tsx`/`.ts` source (no migrations, no seed, no config). | None |
| Live service config | **None** — no external service (n8n/Datadog/etc.) references these components; this is a client-only UI restructure. | None |
| OS-registered state | **None** — no Task Scheduler / launchd / pm2 process names involved. | None |
| Secrets / env vars | **None** — no env var or secret key names the renamed component or the new endpoint path. | None |
| Build artifacts / import graph | **2 test-file `vi.mock()` module paths** hard-code `@/components/catalog/WorkflowCatalog` (`DashboardLayout.catalogHome.test.tsx:52`, `DashboardLayout.waveMount.test.tsx:64`). A stale mock path silently mounts the real component (jsdom `getToken()` failure). Also the component's own test file + DashboardLayout's live import. | Repoint all 4 code refs (import/mock paths) + 2 comment refs; then `grep -c "WorkflowCatalog" frontend/src == 0` |

**Canonical question — after every source file is updated, what still has the old string?** Nothing runtime — but a Next.js/vitest build cache can hold a stale module. Recommend `tsc --noEmit` (proves the import graph resolves) + a full `vitest run` on the touched suites after the rename.

## Common Pitfalls

### Pitfall 1: Retired-palette grep false positives ("Inter" matches `setInterval`)
**What goes wrong:** A naive `grep -i "Inter"` on `DashboardLayout.tsx` reports 2 hits at lines 187/190 — but those are `setInterval`/`clearInterval` (`DashboardLayout.tsx:186-190`), NOT the font. A grep that counts these as retired-palette violations will never reach 0 and will send the agent chasing a non-bug.
**Why it happens:** "Inter" (font) is a substring of `setInterval`/`interval`/`interface`. Same risk: "Fraunces" vs `--font-fraunces`.
**How to avoid:** Grep the retired FONTS with a font-context anchor, e.g. `grep -nE "font-family[^;]*Inter|['\"]Inter['\"]|Fraunces|JetBrains"` — NOT a bare substring. For the retired HEXES (`#1B2A4A`, `#2563eb`, `#f5f5f0`) a plain literal grep is safe (they are unique). The exact per-surface findings this session:
- `WorkflowCatalog.tsx`: `#f5f5f0`×1 (:115), `fraunces`×1 (:131 — `var(--font-fraunces)`), `#1B2A4A`×2 (:191,200).
- `WorkflowHistory.tsx`: `#f5f5f0`×2 (:455,896), `#1B2A4A`×17 (:514,590-663,714,936,958).
- `SavedWorkflowsPage.tsx`: `#f5f5f0`×1 (:189), `fraunces`×1 (:201), `#1B2A4A`×4 (:27,271,300,332).
- `DashboardLayout.tsx`: **zero real retired-palette hits** ("Inter" ×2 are `setInterval` false positives).
**Warning signs:** A grep count that won't drop to 0 no matter how you edit → you're matching a substring in unrelated code.

### Pitfall 2: `var(--font-fraunces)` is a DEAD variable (silent visual drift)
**What goes wrong:** All three surfaces set `style={{ fontFamily: "var(--font-fraunces)" }}` on their hero `<h1>`. But `--font-fraunces` is defined **nowhere** — `src/app/layout.tsx` only exposes `--font-manrope` and `--font-heebo` (`:7,16`), and the `@theme` layer maps `--font-serif: var(--font-heebo)` (`styles/globals.css:15`). So the var resolves to empty and the heading silently falls back to inherited `--font-sans` (Manrope).
**Why it happens:** These files predate the Phase-32 font swap (Fraunces→Manrope/Heebo) and were never cleaned.
**How to avoid:** Replace `style={{ fontFamily: "var(--font-fraunces)" }}` with the token class `font-serif` (Heebo) or `font-sans` per the mock role. This both kills the `fraunces` grep hit AND makes the intended font explicit.
**Warning signs:** A heading that renders in the body font despite an explicit `fontFamily` style.

### Pitfall 3: Regressing KAN-96 / KAN-92 during the History restructure
**What goes wrong:** Reworking `handleSelectRun` or the title rendering can (a) send a *running* run to the static detail view instead of the live execution view, or (b) reintroduce `Revision:` placeholder titles.
**Why it happens:** KAN-96's click-branch lives in `handleSelectRun` (`WorkflowHistory.tsx:175-198`): `if (activeRunId && run.id === activeRunId && onViewRunningPipeline) { onViewRunningPipeline(); return; }`. KAN-92 titles come straight from `run.title` (the async-generated real title) rendered at `:477`, `:285` (search match).
**How to avoid:** Preserve the `activeRunId`/`onViewRunningPipeline` guard verbatim; keep rendering `run.title` (never re-synthesize a `Revision:` label). The `activeRunId` + `onViewRunningPipeline` props are threaded from DashboardLayout (`:1459-1460`).
**Warning signs:** Clicking an in-flight run opens a frozen detail; or a revision row shows "Revision: …" instead of the real title.

### Pitfall 4: Breaking the two DashboardLayout mock-path tests on rename
**What goes wrong:** After moving/renaming the component, `DashboardLayout.catalogHome.test.tsx` and `DashboardLayout.waveMount.test.tsx` still `vi.mock("@/components/catalog/WorkflowCatalog", …)`. The mock no-ops, the real component mounts, its `useEffect` mount fetch calls `getToken()` (localStorage — absent in jsdom), and the test either throws or asserts the wrong surface.
**How to avoid:** Update both mock paths + symbol names in lockstep with the file move. The catalogHome test also asserts the DEFAULT home landing mounts the (renamed) grid — keep that assertion meaningful (`stub-workflow-catalog` testid may stay, or rename to `stub-home-launch-grid`).
**Warning signs:** `catalogHome.test.tsx` failing with a localStorage/`getToken` error after the rename.

### Pitfall 5: Full backend `pytest` HANGS offline
**What goes wrong:** Running the whole backend suite offline hangs (Chromium/Bedrock/Postgres-gated tests).
**How to avoid:** Run ONLY the targeted runs-API suites (see Validation Architecture). Never `pytest` bare. (Offline-test-suite memory note; confirmed the suite structure at `backend/tests/unit/test_runs_api*.py`.)

## Code Examples

### Run-summary aggregation over EXISTING columns (BE, additive read)
```python
# Source pattern: backend/app/api/runs.py:1068 (_owner_gate_or_404) + :933 (family BFS) + :215 (_run_response)
# NEW: GET /api/runs/{workflow_id}/summary  — additive, read-only, owner-scoped.
@router.get("/{workflow_id}/summary")
def get_run_summary(workflow_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    run = _owner_gate_or_404(db, workflow_id, current_user.id)   # user_id gate → 404, never 403
    # per-agent breakdown — parse the EXISTING JSON column (never invent fields)
    try:
        agents = json.loads(run.agent_outputs) if run.agent_outputs else []
    except Exception:
        agents = []
    # KPI stats — from existing columns
    try:
        tokens = json.loads(run.token_usage) if run.token_usage else {}
    except Exception:
        tokens = {}
    # version/revision timeline — reuse the owner-scoped family walk (runs.py:933-1018)
    root_id = _compute_root_ids(db, current_user.id, [run])[run.id]
    # ... BFS-down over owned children (copy get_run_family body) → ordered members w/ revision_index
    return {
        "id": run.id, "title": run.title, "type": run.type, "status": run.status,
        "duration": run.duration, "agent_count": run.agent_count,
        "token_usage": tokens,                       # KPI
        "error": run.error,                          # failure banner (with status)
        "agents": agents,                            # per-agent breakdown
        "root_id": root_id,                          # version timeline anchor
        # "members": [...]  # from the /family BFS
    }
```
> This adds ZERO columns and touches NONE of the 5 backend goldens (INV-3 by construction — it only READS). Consider a Pydantic `RunSummaryResponse` for contract strength, mirroring `WorkflowRunResponse` (`runs.py:88`).

### KAN-96 click-branch to preserve (FE)
```typescript
// Source: frontend/src/components/history/WorkflowHistory.tsx:175-181 — DO NOT REGRESS
const handleSelectRun = useCallback(async (run: WorkflowRun) => {
  if (activeRunId && run.id === activeRunId && onViewRunningPipeline) {
    onViewRunningPipeline();   // running run → live execution view
    return;
  }
  // ... else open the terminal-run detail page
}, [activeRunId, onViewRunningPipeline]);
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `CreationHub.WORKFLOWS` hardcoded array as home | Data-driven `WorkflowCatalog` (`GET /api/workflows`) as default home | P22 (UXFIX-03/D-20) | The fused-home base is already data-driven + SC-001; do not reintroduce a hardcoded name list |
| Fraunces / Inter / JetBrains fonts | Manrope (sans) + Heebo (serif) via `@theme` (`styles/globals.css:14-16`) | Phase 32 | `var(--font-fraunces)` is now dead → migrate to `font-serif` |
| Navy `#1B2A4A` brand + beige `#f5f5f0` surface | One-chroma `--brand #3C2CDA` + `--surface-paper #F0EEE7` tokens | Phase 32 (`styles/globals.css:61,79`) | These pages still use the retired literals → token-migrate |
| Nav "Catalogue" | Nav "Home · Library · My Workflows" | Phase 35 (`AppHeader.tsx:96-98`) | Nav pill already relabeled — only the in-page `<h1>` remains |

**Deprecated/outdated:**
- `var(--font-fraunces)`: replaced by `font-serif`/Heebo — remove.
- `#1B2A4A`, `#f5f5f0`: replaced by `--brand` / `--surface-paper` tokens — remove.
- The mock's "Catalogue" label for saved workflows: a naming mistake (D-11) — reserved for the future marketplace; use "My Workflows".

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The run-detail page is a NEW component/view; there is no existing `/app/**/run` route (verified `find src/app` shows no run/detail dir). The current terminal-run detail is the in-panel `selectedRun` view inside `WorkflowHistory.tsx`. | Run Detail | If a hidden route exists, the "new-build" is instead a restructure — low risk (grep found none) |
| A2 | History sort needs NO backend change (token_usage + duration already on each list row). | History / Standard Stack | If the list endpoint stripped these, a BE tweak is needed — but `runs.py:99,101` returns them |
| A3 | "Real kebab actions" (My Workflows) is satisfied — the kebab is already wired (Rename/Duplicate/Delete). The remaining work is label rename + reskin. | My Workflows | If the phase intends NEW kebab actions (e.g. "Open detail", "Share"), scope expands — but POR §84 says "kebab actions real", which they are |
| A4 | The retired-palette HARD gate = the specific 6-token list (`#1B2A4A/#2563eb/#f5f5f0/Inter/Fraunces/JetBrains`) → grep 0 per file; the broader "no stray stock palette (gray-/blue-/#hex)" is a reskin-quality bar, not a mechanical 0-gate (WorkflowHistory has 102 stock classes + 37 raw hexes — a full purge is large). | Token Completeness / Validation | If the orchestrator requires ALL stock palette → 0, scope on WorkflowHistory roughly triples; recommend confirming with the Phase-35 precedent |
| A5 | Moving the component file to `home/` (vs. renaming in `catalog/`) is Claude's discretion; the dir name `catalog/` is developer-facing and does not violate the D-11 user-facing "Catalogue reserved" rule. | Rename | If the phase wants the dir gone too, add the move — low risk |

**If this table is empty:** it is not — five assumptions above need planner/user awareness. A3 and A4 are the load-bearing ones (they change scope).

## Open Questions

1. **Fused-home layout shape** — how much of `IdeaInputPage` (the launcher) folds onto the home landing vs. stays as the `input` view for the saved-workflow preload path?
   - What we know: `input` view must survive for `handleLaunchSaved` preload (`DashboardLayout.tsx:866-879`); the recents strip has data via `recentRuns` prop.
   - What's unclear: whether the fused launcher fully replaces the `input` navigation for the generic path or just adds a prompt box to home that still routes to `input`.
   - Recommendation: Add the prompt launcher + recents to `home` while KEEPING `input` reachable for preload — minimal, non-regressing. Let the planner pick the exact composition within D-15.

2. **Run-detail tab surface scope** — the mock (evidence 01) models a rich Steps/Preview/Files/Audit run screen, but Phase 32 already built much of that (RunChatLane, PreviewPanel tabs, Audit tab).
   - What we know: the WorkflowHistory in-panel detail already renders per-agent breakdown, token usage, VersionTimeline, failure affordance, and Preview/Files/Thinking/Audit tabs (`WorkflowHistory.tsx:454-872`).
   - What's unclear: whether SHELL-03 wants a NET-NEW page or a restructure of the existing detail view fed by the new summary endpoint.
   - Recommendation: Build the run-detail as a restructured/promoted version of the existing detail view, fed by `GET /{id}/summary`, reusing `VersionTimeline`/`DegradedRunAffordance`. Avoid duplicating Phase-32 surfaces.

3. **Retired-palette gate breadth** (see A4) — hard-6-list-to-0 vs. full stock-palette purge.
   - Recommendation: Treat the 6-token list as the mechanical CI-style gate (matches the orchestrator's Nyquist key); migrate stock palette to tokens opportunistically per touched file, and flag any remaining `gray-`/raw-hex that is semantically load-bearing (e.g. agent-icon color arrays) for the planner.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| vitest | FE unit/component tests | ✓ | 4.1.5 | — |
| tsc (TypeScript) | Type identity gate | ✓ (in-repo) | — | — |
| python3.11 | Backend targeted tests | ✓ | `/opt/homebrew/bin/python3.11` | — |
| lint-imports (import-linter) | 4/0 contract gate | ✓ | `/opt/homebrew/bin/lint-imports` (ran: **4 kept, 0 broken**) | — |
| Live backend (Postgres/Bedrock/Chromium) | mocked Playwright e2e, full pytest | ✗ (offline) | — | **live-deferred**; verify FE by vitest+tsc+grep, BE by targeted suites |

**Missing dependencies with no fallback:** none block execution.
**Missing dependencies with fallback:** live server — mocked Playwright webServer times out offline (Phase-35 precedent); e2e is **live-deferred**, capture a baseline only. Full `pytest` hangs offline → use targeted suites.

## Validation Architecture

> Offline-by-delta verification. `workflow.nyquist_validation` treated as enabled (not disabled in config). This is the section the orchestrator's Nyquist gate keys on.

### Test Framework
| Property | Value |
|----------|-------|
| FE framework | vitest 4.1.5 (`npx vitest --version`, verified) |
| FE config | `frontend/vitest.config.*` (existing; component tests colocated `*.test.tsx`) |
| FE quick run | `cd frontend && npx vitest run src/components/history src/components/catalog src/components/savedworkflows src/components/layout` |
| FE type gate | `cd frontend && npx tsc --noEmit` (identity by delta — no NEW errors vs. baseline) |
| BE framework | pytest via `python3.11 -m pytest` (no venv) |
| BE quick run | `cd backend && python3.11 -m pytest tests/unit/test_runs_api.py tests/unit/test_runs_api_family.py tests/unit/test_runs_api_events.py tests/unit/test_runs_api_artifacts.py -q` |
| Import contract | `cd backend && /opt/homebrew/bin/lint-imports` → must stay **4 kept, 0 broken** (baseline confirmed this session) |
| Retired-palette grep | per touched file, MUST be 0 (see below) |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SHELL-02 | Rename reaches grep-0 | grep | `! grep -rq "WorkflowCatalog" frontend/src` (expect true) | ✅ (grep) |
| SHELL-02 | Home still mounts the (renamed) default landing | unit | `npx vitest run src/components/layout/DashboardLayout.catalogHome.test.tsx` | ✅ (repoint mock path) |
| SHELL-02 | Wave mount unaffected by rename | unit | `npx vitest run src/components/layout/DashboardLayout.waveMount.test.tsx` | ✅ (repoint mock path) |
| SHELL-02 | Launch grid two-gate filter + label | unit | `npx vitest run src/components/catalog/WorkflowCatalog.test.tsx` (→ renamed) | ✅ (rename) |
| SHELL-02 | History KAN-96/KAN-92 + delete + affordance stay green | unit | `npx vitest run src/components/history/` (WorkflowHistory.test.tsx + .family/.revise/.runInput/.genericReopen) | ✅ 5 files |
| SHELL-02 | My Workflows label = "My Workflows", kebab CRUD | unit | (no test file today — **Wave 0 gap**) `npx vitest run src/components/savedworkflows` | ❌ Wave 0 |
| SHELL-03 | run-summary owner-gated → 404 cross-owner | unit | `python3.11 -m pytest tests/unit/test_runs_api.py -q` (+ add summary case) | ✅ extend |
| SHELL-03 | run-summary aggregation shape | unit | (add `test_runs_api_summary.py`) | ❌ Wave 0 |
| INV-3 | 5 backend goldens untouched | by-construction | endpoint is read-only; run existing golden suite if present | ✅ (no edit) |

### Sampling Rate
- **Per task commit:** `npx vitest run <touched suite>` + `npx tsc --noEmit` (FE) OR `python3.11 -m pytest <touched runs suite> -q` (BE) + `! grep -rq "<retired token>" <touched file>`.
- **Per wave merge:** full FE suite over the four touched dirs + `tsc --noEmit` + `lint-imports` (4/0) + BE targeted runs suites.
- **Phase gate:** all touched vitest suites green; `tsc --noEmit` no NEW errors; per-file retired-palette grep = 0; BE targeted suites green; `lint-imports` = 4 kept / 0 broken; goldens untouched by construction.

### Retired-palette grep (the token gate — run per touched file)
```bash
# HEXES (safe literal grep): expect 0 each
grep -nE '#1B2A4A|#2563eb|#f5f5f0' <file>
# FONTS (anchor to avoid setInterval/interface false positives): expect 0
grep -nE "font-family[^;]*(Inter|Fraunces|JetBrains)|['\"](Inter|Fraunces)['\"]|--font-fraunces" <file>
```
Baseline hit counts (this session): WorkflowCatalog 3+1, WorkflowHistory 19+, SavedWorkflowsPage 4+2, DashboardLayout **0 real** ("Inter"×2 = `setInterval` false positive → do NOT count).

### Wave 0 Gaps
- [ ] `frontend/src/components/savedworkflows/SavedWorkflowsPage.test.tsx` — covers SHELL-02 label="My Workflows" + kebab CRUD (no test exists today)
- [ ] `backend/tests/unit/test_runs_api_summary.py` — covers SHELL-03 owner-gate→404 + aggregation shape
- [ ] Update mock paths in `DashboardLayout.catalogHome.test.tsx` + `DashboardLayout.waveMount.test.tsx` as part of the rename task (not a new file, but a required edit)
- [ ] Rename `WorkflowCatalog.test.tsx` → `HomeLaunchGrid.test.tsx` alongside the component

### Live-deferred (do NOT run offline — mark deferred, do not hang)
- Mocked Playwright e2e (`frontend/e2e/`, `npm run e2e`) — webServer times out offline (Phase-35 precedent). Capture a baseline; verify FE by vitest+tsc+grep.
- Full `python3.11 -m pytest` (bare) — HANGS offline (Chromium/Bedrock/Postgres-gated). Use the targeted runs suites only.

## Security Domain

`security_enforcement` treated as enabled. This phase's only backend surface is one owner-scoped read endpoint.

### Applicable ASVS Categories
| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | `Depends(get_current_user)` (JWT) — every runs route uses it (`runs.py:238` etc.) |
| V3 Session Management | no | No session change |
| V4 Access Control (IDOR) | **yes** | `WorkflowRun.user_id == current_user.id` → 404-not-403 via `_owner_gate_or_404` (`runs.py:1068`). Clone verbatim for run-summary. Use `user_id`, never nullable `owner_id`. |
| V5 Input Validation | yes | FastAPI path param `workflow_id: str`; JSON parse of `agent_outputs`/`token_usage` wrapped in try/except (never trust stored JSON to be well-formed) |
| V6 Cryptography | no | No crypto |
| V7 Error/Log (secret exposure) | yes | The summary must project only summary-safe fields; do NOT echo raw child output that could carry a secret (`exec_runs` precedent uses `output_digest` as-stored, `runs.py:1181`) |

### Known Threat Patterns for this stack
| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Cross-owner run read (IDOR) | Information Disclosure | `user_id` owner filter → 404; the family walk terminates at any foreign ancestor (`_FOREIGN_ANCESTOR`, `runs.py:131`) so no foreign run metadata leaks into the version timeline |
| Malformed stored JSON crash | Denial of Service | `json.loads` in try/except → `[]`/`{}` fallback (existing pattern, `runs.py:502-506`) |
| Client-side workflow-name branch (SC-001 breach) | Tampering | Keep list/detail keyed on generic run fields; never branch a route/page-key on `run.type` name |

## Sources

### Primary (HIGH confidence — read this session)
- `.planning/phases/36-home-history-my-workflows-b2/36-CONTEXT.md` — phase decisions/invariants
- `frontend/src/components/layout/DashboardLayout.tsx` (1741 ln) — view state machine, mainView union (:173), home/input views (:1420,:1546), handleSelectFeature (:807), handleGoHome (:922), handleNavigate (:1265), WorkflowHistory mount (:1458)
- `frontend/src/components/catalog/WorkflowCatalog.tsx` — the rename target; retired palette :115,:131,:191,:200
- `frontend/src/components/history/WorkflowHistory.tsx` — KAN-96 (:175), delete (:263), family reuse (:38,:885), token/duration fields (:480,:485), retired palette (37 hexes)
- `frontend/src/components/savedworkflows/SavedWorkflowsPage.tsx` — kebab already wired (:118-186), label "Workflow Catalogue" (:202)
- `frontend/src/components/layout/AppHeader.tsx` — nav pill already "My Workflows" (:98)
- `frontend/src/components/layout/DashboardLayout.catalogHome.test.tsx` / `.waveMount.test.tsx` — mock module paths (:52,:64)
- `backend/app/api/runs.py` (1210 ln) — owner gate (:1068), family (:933), root walk (:134), response builder (:215), list/get/delete (:236,:386,:411)
- `backend/app/models/workflow.py` — WorkflowRun columns (:19-91); owner_id nullable (:58)
- `frontend/src/styles/globals.css` — `@theme` token layer (:12-175); fonts manrope/heebo (:14-16); brand/surface tokens (:61,:79)
- `frontend/src/app/layout.tsx` — font vars manrope/heebo only (:2,:7,:16); imports globals (:3)
- `.planning/v2.0-evidence/01-run-ui-teardown.md` — run-detail anatomy + data contract (§7)
- `.planning/v2.0-evidence/12-coverage-and-backend-map.md` — run-summary is Category A additive read (:41); sort fields exist (:44)
- `.planning/CHAT-AND-UI-CONVERGENCE-PLAN.md` — POR §84 (:84), D-11 (:27), D-15 (:29), §96 endpoints (:96)
- `.planning/REQUIREMENTS.md` — SHELL-02/03 (:249-250)

### Commands run this session
- `grep -rn "WorkflowCatalog" frontend/src` → 7 files (rename inventory)
- per-file retired-palette greps (counts above)
- stock-palette quantification: WorkflowHistory 102 classes + 37 hexes; SavedWorkflows 55+17; WorkflowCatalog 19+3
- `npx vitest --version` → 4.1.5; `command -v python3.11 lint-imports` → both present
- `cd backend && /opt/homebrew/bin/lint-imports` → **4 kept, 0 broken**
- `find frontend/src/app -type d` → no run/detail route (run-detail is new-build)

### Secondary / Tertiary
- None required — all claims grounded in primary in-repo sources.

## Metadata

**Confidence breakdown:**
- Standard stack / reuse map: HIGH — every helper read at file:line; no new deps
- Rename blast radius: HIGH — full grep inventory + mock-path gotcha verified
- History/My Workflows behavior (delete + kebab already wired): HIGH — read the handlers
- Run-summary endpoint shape: HIGH for the owner-gate + field availability (read the model + runs.py); MEDIUM for the exact response contract (Claude's discretion within "aggregate existing data")
- Token gate: HIGH — exact hit counts + the fraunces-is-dead + Inter-false-positive findings verified
- Validation architecture: HIGH — vitest/python3.11/lint-imports all run/verified this session

**Research date:** 2026-07-09
**Valid until:** ~2026-08-08 (stable brownfield surface; re-verify grep counts if the three files change before planning)
