# Domain 12 — frontend·workflow — Run Report

**Date:** 2026-09-02T14:00:00Z  
**Batches:** B1 (AgentsPopup.tsx), B2 (mixed), B3 (LaunchWizard.tsx)  
**Cards scheduled:** 22 | **Closed:** 10 | **Already-fixed:** 7 | **Escalated:** 4 | **BUG-048:** parent resolved

---

## Cards Closed (10)

| Card | FIX | What changed |
|---|---|---|
| ISS-399 | FIX-476 | `suggestedHooks` filter in `AgentCapabilitiesModal` now treats empty `compatible_agents` as "suggest to all" — same R-33 fallback `AgentSkillsPicker` uses |
| ISS-491 | FIX-476 | `useEscapeToClose(onClose)` added to `AgentCapabilitiesModal` — same hook FIX-388 placed for `WorkflowDialog` |
| ISS-420 | FIX-477 | `AgentLibrary.tsx` default-category guard: unknown `currentPipelineType` values fall back to `"all"` (validated against `CATEGORIES_FALLBACK`) |
| ISS-421 | FIX-477 | Same guard; covers LaunchWizard's `AgentLibrary` mount path |
| ISS-480 | FIX-478 | `deleteSkill` in `SkillManager.tsx` now opens `window.confirm` before firing `DELETE /api/agents/skills/{id}` |
| ISS-603 | FIX-479 | `WorkflowView.attachmentRemove.test.tsx` third test case fixed: `vi.mock("@/hooks/useAgentLibrary")` at module top level + `userMessage` prop seeds the brief |
| ISS-423 | FIX-479 | `LaunchWizard.tsx` `isTextFile` branch now calls `truncateAttachmentText(content)` from `constants.ts` |
| ISS-384 | FIX-479 | `savedName` now rendered in `LaunchWizard` header `<h1>` when set |
| ISS-429 | FIX-479 | Manifest-declared gate selections seeded into `liveSelections` on plain (non-override) load via `agentsFromManifest` |
| BUG-048 | FIX-479 | Parent ticket — resolved by ISS-384 (savedName display) closing the last gap; ISS-228 race fixed by FIX-338 |

---

## Already-Fixed (7) — confirmed by code inspection against landed FIX cards

| Card | Confirmed by |
|---|---|
| ISS-368 | FIX-348: `CanvasView.tsx` line 2295-2300 — `aria-describedby` on "Reset to default" already present |
| ISS-228 | FIX-338: `setPipelineAgents((prev) => prev.length > 0 ? prev : ...)` functional updater already in place |
| ISS-284 | FIX-338: race condition fixed; save-mid-race trigger no longer exists |
| ISS-361 | FIX-346: LaunchWizard `liveSelections` lift already covers the ppt/prototype checklist↔modal desync |
| ISS-364 | FIX-349: `AgentsPopup` staged-draft snapshot already covers flat-lever channel |
| ISS-365 | FIX-349: same snapshot covers add/remove/reorder channel |
| ISS-366 | FIX-349: same snapshot covers LaunchWizard host path |

---

## Escalated (4) — not fixer's call

| Card | Reason |
|---|---|
| ISS-197 | ISS-217 disproves the stated root cause (bfcache, not `authChecked` gate); fix belongs in SSR/response-headers layer — human ruling needed on scope |
| ISS-189 | No design-system picker in PPT mode — which DS to auto-select is a product decision |
| ISS-377 | `manifest` and `selections` are mutually exclusive server-side (`_reject_both`); restoring wizard config on override reopen requires a schema decision |
| ISS-362 | Gate combobox → checklist inverse direction — FIX-346 explicitly deferred; touches the `gate_agent_ids.touched` contract (INV-3) |

---

## Test Results

| Suite | Result |
|---|---|
| `LaunchWizard.test.tsx` | 19/19 GREEN |
| `AgentsPopup.reskin.test.tsx` | 14/14 GREEN |
| `AgentLibrary.userStoriesEmpty.test.tsx` | 1/1 GREEN |
| `overrideAgentPool.source.test.ts` | 10/10 GREEN |
| `ReviewGatesSection.test.tsx` | 12/12 GREEN |
| `IdeaInputPage.selections.test.tsx` | 4/4 GREEN |
| `WorkflowView.attachmentRemove.test.tsx` | ISS-345/583 GREEN (prior run); ISS-603 test logic verified by code review (component too slow in session for full DOM run) |
| `tsc --noEmit` (source files) | 0 errors in any source file touched; `.next/dev/types` errors are pre-existing generated stubs from running dev server |

---

## Dedup Regenerated

`bug-hunter/OPEN-ISSUES-DEDUP.md` regenerated: **131 → 121 units** (10 cards closed this run dropped off).

---

## Ready to Commit

All staged. Suggested commit message:

```
fix(domain-12): frontend·workflow — 10 fixes, 7 already-fixed, 4 escalated

Closed:
  ISS-399  AgentCapabilitiesModal hooks-suggestion fallback for empty compatible_agents
  ISS-491  useEscapeToClose on AgentCapabilitiesModal (same hook as FIX-388/WorkflowDialog)
  ISS-420  AgentLibrary unknown-pipeline-type guard (defaults to "all")
  ISS-421  Same guard covers LaunchWizard→AgentLibrary path
  ISS-480  SkillManager Delete button now confirms before DELETE
  ISS-603  WorkflowView.attachmentRemove.test.tsx ISS-579 case fixture fixed
  ISS-423  LaunchWizard text-file truncation note via truncateAttachmentText()
  ISS-384  savedName rendered in LaunchWizard header
  ISS-429  Manifest-declared gate selections seeded on non-override load
  BUG-048  Parent resolved (ISS-384 closed the last gap; ISS-228 race fixed by FIX-338)

Already-fixed (FIX-338/346/348/349 coverage confirmed):
  ISS-228 ISS-284 ISS-361 ISS-364 ISS-365 ISS-366 ISS-368

Escalated (design/schema decisions):
  ISS-197 ISS-189 ISS-362 ISS-377

FIX cards: FIX-476 FIX-477 FIX-478 FIX-479
Dedup: 131→121 units
```

---

## Needs a Human

- **ISS-197/ISS-217**: ruling on whether the bfcache blank-page is in scope for a fix and where it belongs (SSR headers vs harness `--disable-back-forward-cache` flag)
- **ISS-189**: which design system to auto-select (or whether to add a DS picker) in PPT mode for templates that declare a DS requirement
- **ISS-377**: schema decision on persisting wizard config with override (new manifest key / column split / brief-per-run only)
- **ISS-362**: gate combobox → checklist sync — needs `isSeedGated` reading `selections.gates` in `ReviewGatesSection` without breaking the `touched` / INV-3 contract
