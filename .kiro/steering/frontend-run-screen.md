---
inclusion: fileMatch
fileMatchPattern: "frontend/src/components/run/**,frontend/src/components/results/**,frontend/src/components/preview/**,frontend/src/app/dashboard/**"
---

# Frontend — Run Screen Domain

> Loaded when editing run/results/preview components or the dashboard page. See `invariants.md` for hard constraints.

---

## Run Screen Architecture (Phase 39/42)

```
DashboardLayout
├── Left column: RunChatLane (conversation + composer)
│   ├── MessageBubble (assistant turns, streaming)
│   ├── InlineGateActions (approve/reject/redo/update_specs)
│   ├── InlineClarifyActions (submit questionnaire)
│   └── ChatAttachments (paste/drag-drop/resize)
└── Right column: tabs
    ├── Preview (PreviewPanel)
    │   ├── FIRST_PARTY_RENDERERS dispatch table
    │   └── GenericDeliverablePreview (mimetype-dispatched fallback)
    ├── Steps (AgentThinkingTab)
    │   ├── StepsOverviewSpine
    │   └── AgentDetailPanel (settled artifact cards)
    ├── Files (FilesTab)
    └── Audit (AuditTab)
```

---

## Run-State Binding Rules (critical — many bugs here)

### `contentSourceRunId` / `contentSourceRunType`
- Set from `fullRun.id` / `fullRun.type` on history-open (durable thread).
- Cleared on fresh-launch reset.
- The `viewedRunType` fallback (`recentRuns.find(...)`) is gated to `!isPipelineRunning` **only** for the recents window — NOT for `contentSourceRunType` (BUG-012 / BUG-sml fix).
- `effectiveReviseType = viewedRunType ?? workflowType` — drives type chip, header pill, revise routing.

### `trackedRunIdRef`
- Synced from `activePipelineRunId ?? contentSourceRunId` as a **ref** (useCallback has stale closure).
- Foreign-run guard in `pipeline_start` / `pipeline_complete` handlers reads `trackedRunIdRef.current`.
- Do NOT write the ref during render.

### `contentSourceRunId` null = fresh launch
- `viewedRun = contentSourceRunId != null ? recentRuns.find(...) : undefined`
- Title falls through to `submittedBrief` on null (BUG-019 fix).

### Chat transcript binding
- `seedRunChatTranscript([])` on fresh non-revision launch (BUG-021 fix — inside `if (!isRevision)`).
- `seedRunChatTranscript(durableFrames)` on history-open (durable replay).
- `useRunChat.sendMessage` re-fetches after the POST completes — must `await sendCommand(...)` (BUG-017 fix).

---

## Deleted Surfaces (do NOT recreate)

| Component | Deleted in | Replacement |
|-----------|-----------|-------------|
| `ReviewGatePanel.tsx` (full-screen) | Phase 42 | `InlineGateActions` in Steps |
| `QuestionnairePanel.tsx` (full-screen) | Phase 42 | `InlineClarifyActions` in Steps |
| `AgentProgressPanel.tsx` | Phase 42 | `RunChatLane` absorbs controls |
| `WaveTreePanel.tsx` (standalone) | Phase 42 | `AgentDetailPanel` drill-down |
| `PrototypePipelineView.tsx` | Phase 42 | Generic `AgentThinkingTab` path |
| `LiveVersionChip` (tab-bar) | Phase 39 | `RunHeader` VersionMenu |
| `RendererSwitcher` (tab-bar) | Phase 39 | Extracted `RendersAsSwitch` |

---

## PreviewPanel Dispatch Rules

```
renderType → FIRST_PARTY_RENDERERS table
  user_stories → UserStoryRenderer
  od_ppt / od_ppt_revision → PPT iframe
  prototype / od_prototype → Prototype renderer
  app_builder → AppBuilder renderer
  (none matched) → GenericDeliverablePreview
```

- `GenericDeliverablePreview` dispatches on `deliverable_mimetype`:
  - `text/html` → sandboxed iframe (`sandbox="allow-scripts"`, **NO `allow-same-origin"`)
  - `text/markdown` → MarkdownPreview (NO `rehype-raw`)
  - `application/zip` → AppBuilder bundle view
  - else → download
- `workflowType={effectiveReviseType}` (not raw `workflowType`) so history-open renders correctly.

---

## AgentDetailPanel — Settled Artifact Cards (Phase 42)

Three conditional, generically-keyed cards after `SettledArtifactCards`:
- **Pages/sections card** — brittle parse of spec agent's `<spec>` `## ` headings via `parseSpecSections` (F2 follow-up: needs a structured `/artifacts?kind=sections` endpoint)
- **Tasks card** — from `task_list` artifact via `parseTasksPreview`
- **Checks card** — from `validation_results` via `AnalysisPreview` (F1 follow-up: needs `/validation-results` aggregate)

The `artifactPreview.tsx` module is the shared source for all three parsers — **never duplicate parsers** (INV-12).

---

## Files Tab Rules

- `prompt.md` — from `parseRunInput(runInput).revisionInstruction || parsed.brief` (FIX-033 — revision runs get their instruction, not blank)
- `clarifications.md` — from `getRunArtifacts(kind=clarifications)` on reopen
- Base-version section — lazy `getWorkflow(rootRunId)` via dynamic-import idiom

---

## Run Header / Version Timeline

- Version = 1-based chronological index within the family (`created_at ASC, id ASC` tie-break).
- `onSelectVersion` / `onVersionChange` prop re-syncs both the summary AND the deliverable column (H-01 fix).
- Non-empty-guard on the revision-preview quote (H-02 fix).

---

## Failed / Degraded State Rules

- Failed run: **drops Preview tab, defaults to Audit tab, red badge** (Phase 42 ND-U reversal — user ruling 2026-07-14).
- `DegradedRunAffordance` is retained on `RunDetailPage` (history/reopen) — only retired from the live run screen.
- `failed: true` marker stamped by `pipeline_failed` handler in `useWorkflow.ts`.
- `cancelled: true` marker stamped by `pipeline_cancelled` handler (ISS-035 fix, Phase 32).

---

## Auto-Tab Selection

| Run state | Auto-selected tab |
|-----------|------------------|
| `clarify` / `gate` | Steps |
| `failed` | Audit |
| default | Preview |

---

## INV-3 Impact on FE

New keys on `pipeline_complete` must be handled gracefully when absent (e.g. `deliverable_mimetype` may be null for old runs).  
Use `reopenedRunStatus` / `fullRun.type` for history-reopen context — never guess from content shape.
