---
id: BUG-014-GROUNDED-CONTEXT
type: bug
kind: event
title: BUG-014 — grounded fix spec
status: resolved
applies_to:
  phases: []
  modules:
  - DashboardLayout
  - Home
  - LaunchWizard
  - LaunchWizard.test
  - api
  - app
  globs:
  - frontend/src/components/workflow/LaunchWizard.tsx
  - DashboardLayout.tsx
  - LaunchWizard.tsx
  - page.tsx
  - LaunchWizard.test.tsx
  requirements: []
locked_constraints: []
verification:
  type: manual
  status: required
  test_files: []
compact_summary: 'LaunchWizard read chain.source_run_id from sessionStorage unconditionally and never cleared it, so a stale id turned fresh launches into hidden child runs; gated the read on isChaining, consume-once.'
last_updated: '2026-08-14'
author: 'Bilal Arshad <bilala@hexaware.com>'
author_source: applies-to-glob
---

# BUG-014 — grounded fix spec (fresh launch leaks a stale `chain.source_run_id` → every run becomes a child → live clarify/gates never surface)

> Frontend-only. Root cause found + orchestrator-verified from the user's live network trace. The PRIMARY, user-facing fix. Executable spec for a `gsd-quick`.

## The bug (VERIFIED from the user's live session)
Pressing "Build interactive prototype" FRESH from Home produces a run whose POST `/api/runs` body carries `source_workflow_run_id: "<a previously-viewed run>"` (e.g. `c530695f`, a completed user_stories run "Task Manager"). Consequences, all confirmed live:
1. Every fresh prototype launch becomes a **child** (`parent_run_id = c530695f`) — ALL of the user's runs `ccdde66e/9d3395c3/66beffe3/c69fa36a/0d259714/586f4ad4` have that same parent.
2. The live run screen never surfaces the child's **clarify questions** or **review gates** (they exist in the backend + render fine on REOPEN, but not on the live launch view), and **Stop** no-ops.
3. The run is **hidden from "My Workflows"** (it's treated as a revision/child), only visible in Home's "Jump back in".
The user must reopen the run at every gate — unacceptable. Backend is correct throughout (clarify + gates fire; answering resumes the build).

## Root cause (VERIFIED to file:line)
`frontend/src/components/workflow/LaunchWizard.tsx` `handleLaunch` (`:436`): 
```
const sourceRunId = sessionStorage.getItem("chain.source_run_id") ?? undefined;   // :438
```
reads the chain source-run id UNCONDITIONALLY and **never clears it**. Its three sibling chain keys ARE consume-once: `chain.from` → `removeItem` at `:186`/`:201`, `chain.brief` → `:200`, `chain.context_block` → `:440`. `chain.source_run_id` is the ONLY one missing its `removeItem`. It is written by `DashboardLayout.tsx:939`/`:1021` when the user chains/views a run (and only conditionally removed at `:952`/`:1032`), so once set it **persists in sessionStorage and leaks into every later launch — including a fresh Home launch that is not a chain at all**. The wizard already tracks whether THIS launch is a real chain: `isChaining = Boolean(chainFrom)` (`:176`), where `chainFrom` is seeded from `chain.from` (consumed at mount, `:183-186`) — so `isChaining` is `false` for a fresh Home entry and `true` only for a genuine chain.

## The fix (LaunchWizard.tsx:438 — gate on the real-chain flag + consume-once)
```
// before:
const sourceRunId = sessionStorage.getItem("chain.source_run_id") ?? undefined;
// after:
const sourceRunId = isChaining
  ? (sessionStorage.getItem("chain.source_run_id") ?? undefined)
  : undefined;
sessionStorage.removeItem("chain.source_run_id");   // consume-once, matching chain.from/brief/context_block — never leak into a later launch
```
Add `isChaining` to `handleLaunch`'s `useCallback` dependency array. Effect: a FRESH launch (`isChaining=false`) sends NO `source_workflow_run_id` → a normal top-level run → clarify + review gates bind + surface on the LIVE run screen, Stop works, and it shows in "My Workflows". A genuine chain (`isChaining=true`) still sends the source (revision-family linkage preserved) AND now clears the key so it can't leak into the next launch.

## Scope fences (STRICT)
- **Frontend only.** File: `LaunchWizard.tsx` (+ its test). Do NOT change `DashboardLayout.tsx` chain writers, `page.tsx`, the reducer, the SSE path, or the j1u/lb6/n2d/o6z/r7d/sml fixes. Do NOT alter the genuine-chain behavior (a real chain still passes `source_workflow_run_id`).
- Do NOT touch the other chain keys' handling (they are already correct consume-once).

## Constraints
- Branch **feat/ui-2**. NO commit trailer. NEVER push. FE cwd-sensitive (from `frontend/`; kill :3000 before mocked Playwright). SC-001: keys on sessionStorage keys / the `isChaining` flag, no workflow-name literal. The 8 pre-Phase-42 vitest reds in untouched files are NOT regressions.
- Keep at-risk green: `LaunchWizard.test.tsx`, and any revision/chain source-lock (`revisionFamilyLinkage.source`) — a genuine chain must still send `source_workflow_run_id`.

## Verification (executor)
- `npx tsc --noEmit` clean.
- **Fail-before/pass-after (LaunchWizard.test.tsx):** (a) FRESH launch — `isChaining=false` (no `chain.from` seeded) with a STALE `sessionStorage["chain.source_run_id"]` present → the emitted launch draft/`onRun` payload has **NO `sourceRunId`/`source_workflow_run_id`** (fail-before: it leaks the stale id) AND `chain.source_run_id` is removed from sessionStorage after launch. (b) GENUINE chain — enter with `chain.from`+`chain.source_run_id` set (`isChaining=true`) → the payload DOES include the `sourceRunId` (no regression to revision chaining) AND the key is cleared afterward.
- Executor does NOT run live Bedrock. **Orchestrator live-proof (the real acceptance):** press "Build interactive prototype" FRESH from Home → the created run has NO `parent_run_id`; its **clarify questions surface on the LIVE run screen** (no reopen); answer them → it builds → the **review gate surfaces LIVE** → approve → it continues; and the run appears in "My Workflows". If gates still fail to surface live for a top-level run, a separate live-binding bug (B) exists — report it, do not silently pass.
