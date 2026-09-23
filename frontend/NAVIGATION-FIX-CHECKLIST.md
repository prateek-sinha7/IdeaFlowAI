# Navigation Fix Checklist — `feat/conditional-gates`

Consolidated from `NAVIGATION-BEHAVIOR-REPORT.md` (both testing passes) into one flat
checklist: one row per click/navigation path, Old vs New destination, whether the
experience is the same, and whether anything still needs fixing. Use this to work
through fixes one by one — the **Fixed = No** rows are the ones that need work.

**Fixed column key:** `Yes` = already fixed (verified) · `No` = confirmed broken,
needs a fix · `N/A` = nothing to fix (new feature, or already identical) · `Blocked`
= can't test yet (needs an in-flight run / test data this account doesn't have) ·
`Unclear` = inconclusive, needs a second look.

## 1. My Workflows / Saved Workflows

| Path | Old | New | Same | Fixed |
|---|---|---|---|---|
| My Workflows → item → Run Workflow (list) | Canvas/Simple, correct, no URL | Canvas/Simple, correct + URL — briefly flashed Dashboard first | Yes | Yes (flash bug fixed) |
| My Workflows → item → kebab → Edit | Did not exist | Composer, pre-loaded with real saved data | N/A (new) | N/A |
| My Workflows → PPT saved item → Edit/Run | `/create/ppt` | `/create/ppt` (same, typed) | Yes | N/A (untested — no PPT-type workflow in account) |
| My Workflows → Prototype saved item → Run | `/create/prototype`-style wizard | Prototype LaunchWizard, no flash | Yes | N/A (verified working) |
| `/workflows/{id}` detail page (direct) | Did not exist | New read-only detail view | N/A (new) | N/A |
| `/workflows/{id}` detail → Edit button | Did not exist | Composer, real saved graph | N/A (new) | N/A |
| `/workflows/{id}` detail → Run button | Did not exist | Canvas, no flash | N/A (new) | N/A |
| `/workflows/{id}/edit` → Composer mounts | Blank state (bug — fetch resolved after first render) | Real saved node graph | No | Yes |
| `/create/ppt`, `/create/prototype`, `/workflows/{id}/run` for ppt/prototype saved workflow | Did not exist | LaunchWizard, staged draft | N/A (new) | N/A |

## 2. Composer / Canvas

| Path | Old | New | Same | Fixed |
|---|---|---|---|---|
| Home → "Compose a custom workflow" → Canvas | Locked 6-agent template pre-populated (bug) | Blank canvas | No | Yes |
| Canvas node → outcome/divert link | Did not exist | Confirmed via source: `ExternalPipelineCard` (`composer/CanvasNode.tsx:299`) is the intended clickable link, but it's never imported/rendered anywhere in the codebase — dead code. The on-canvas node itself is deliberately non-navigating by design (comment confirms), so right now there is genuinely no way to click through to a divert target from the canvas. | No | **No — needs a fix** (wire `ExternalPipelineCard` in, likely the node-config rail's Route/outcomes editor — needs a placement decision, not just a bug fix) |

## 3. Workflow Creation

| Path | Old | New | Same | Fixed |
|---|---|---|---|---|
| Home → "Prototype" tile | `/create/prototype` | `/create/prototype` (same) | Yes | N/A |
| Home → "PPT" tile | `/create/ppt` | `/create/ppt` (same) | Yes | N/A |
| Home → workflow-type tile (User Stories, App Builder, etc.) | Correct screen, no URL | Correct screen + URL | Yes | N/A |
| LaunchWizard → template fetch hits 401 | `/login`, no message | `/login?expired=true`, with message | No (improved) | Yes |
| LaunchWizard → successful launch | `/dashboard` | `/dashboard` (same) | Yes | **Still blocked** — attempted 2026-08-24: launched a real PPT via the wizard, but the run paused on a genuine clarify questionnaire before generation started; cancelled it to test the Cancel flow instead of completing it. Destination on success remains unverified live. |
| LaunchWizard → Back button | `/dashboard` | `/dashboard` (same) | Yes | N/A |
| Run detail (failed run) → "Edit brief & run again" | Same underlying bug, just not visible (no URL) | ~~Landed on the wrong workflow-type screen~~ **Fixed 2026-08-24**: now uses `effectiveReviseType` (the viewed run's own type) instead of stale `workflowType` state — a Custom run now correctly lands on `/create` | Yes | Yes |

## 4. Home / Dashboard shell & global navigation

| Path | Old | New | Same | Fixed |
|---|---|---|---|---|
| "Home" / back-to-home actions | Correct screen, no URL | Correct screen + URL | Yes | N/A |
| Header nav (Home, Library, History, Settings, Analytics, etc.) | Correct screen, no URL | Correct screen + URL | Yes | N/A |
| Deep link direct open (`/library`, `/runs`, `/settings/ai-model`, etc.) | Always landed on Home (bug) | Honors the URL | No | Yes |
| Browser Back / Forward | URL changed, UI didn't follow (bug) | UI follows the URL | No | Yes |
| Cancel mid-run questionnaire | Home, no URL | Home + URL | **No** | **Tested 2026-08-24, doc corrected.** Launched a real PPT, hit a genuine 4-question clarify pause, clicked "Cancel workflow" — actual behavior: stays on `/runs/{id}/stream` in-place, shows "Cancelled — Cancelled by you" with a "Run Again" button. Does NOT navigate to Home/`routes.home()` as this row claimed — that description looks like it was written from an older DashboardLayout-embedded code path; the standalone `/runs/{id}/stream` page (where this now actually renders) has its own in-place cancel handling. Not a bug — arguably better UX (you can see what got cancelled and resume) — but the row's original description was wrong. |
| Reject a human review gate | Home, no URL | Home + URL | Unknown | **Attempted 2026-08-24, could not test.** Built a minimal workflow, set its one agent's Review-gate to "human" (confirmed saved via API: `"gates":["human"]`), ran it — it completed straight through with no pause at all. No gate to reject. Either human gates don't enforce a pause for `custom`-type single-agent workflows in this build, or something else is required to trigger the pause — worth a follow-up investigation, this reads as a possible real gap, not just a blocked test. |
| "Back to History" from run/execution view | History, no URL | History + URL | Yes | N/A |
| Settings → Back | Home, no URL | Home + URL | Yes | N/A |
| `/settings/ai-model` (or any sub-tab) direct URL | Always default tab (bug) | Honors the sub-tab | No | Yes |

## 5. Run history / live run / preview tabs

| Path | Old | New | Same | Fixed |
|---|---|---|---|---|
| A run starts (SSE `pipeline_start`) | execution, no URL | execution + URL | Yes | **Yes.** Live-verified 2026-08-24: clicking Run once on a saved workflow navigated straight to `/runs/{id}/stream` live. |
| Run History → "View Running" | execution, no URL | execution + URL | Yes | **Yes.** Live-verified — notification's "View progress" landed on the active run's own `/stream` URL; header also showed an accurate "N Running" badge while pipelines were active. |
| Run History → click a past run | Opens locally, no URL | Opens + URL | Yes | N/A |
| Home → "Jump back in" chip | execution, no URL | execution + URL | Yes | N/A |
| Notification badge → "Go to Pipeline" | execution, no URL | execution + URL | Yes | **Yes.** Live-verified 2026-08-24 — notification center showed the run live ("4 of 7 agents · 57% · Building"), "View progress" click landed on its stream URL. |
| Notification → select completed/failed run | Opens locally, no URL | Opens + URL | Unclear | **Tested 2026-08-24, one finding.** Clicked a notification for a just-cancelled run — landed on `/runs` (the general list), not that run's own detail page. Could be correct-for-cancelled-runs behavior, or could be a real gap; not clean enough evidence either way, worth a second look with a completed (not cancelled) run's notification. |
| PreviewPanel tabs (Preview/Steps/Files/Audit) | Switches content, no URL | Switches + URL | Yes | N/A |
| `/runs/{id}/stream`, `/steps` etc. direct open | Did not exist | Cold-mount re-attaches (SSE or replay) | N/A (new) | N/A |
| Deep-link to a preview tab from a chat card | Wrong tab could silently win (race, bug) | Requested tab always wins | No | Yes |
| Run History → filter chips / sort | Local only, no URL | Filtered/sorted + URL persists on refresh | Yes | N/A |
| Run card → "Diverted to X" badge | Did not exist | Navigates to the linked run | N/A (new) | **Still blocked, 3 genuine attempts made 2026-08-24.** Tried to trigger `CUSTOM-sample_conditional_branch_new`'s real divert branch (Pick Language → `dutch` → `trigger:"workflow", target:"ppt"`) three ways: (1) a Dutch-language brief alone — model decided `spanish`; (2) same + editing the agent's prompt via JS to document `dutch` as an option — edit didn't take effect in the run (agent still reasoned from the original english/spanish-only prompt); (3) same edit via a proper Playwright `.fill()` this time — prompt confirmed set in the DOM, but the agent still didn't emit a clean `{"decision":"dutch"}`, defaulted to `english`. The agent's own system prompt appears to strongly anchor it to english/spanish regardless of brief content. No diverted run exists in this account still. |
| Steps overview → clicking a skipped agent's row | Clickable | Non-clickable (intentional) | No (by design) | Still blocked — same reason as above, no skipped-agent run to test against |
| A run diverts via a conditional gate → terminal state | Could fall through to complete/idle (bug) | Correctly resolves to diverted/terminal | No | Yes (code-level; still not live-verified — same reason) |
| `pipeline_diverted` / `agent_skipped` SSE events | Dropped silently (new event types) | Routed through the reducer | N/A (new) | Yes (code-level; still not live-verified) |

## 6. Library

| Path | Old | New | Same | Fixed |
|---|---|---|---|---|
| Library tab switch (Agents/Skills/Hooks) | Local only, no URL | Same content + URL | Yes | N/A |
| Library category filter chips | Local only, no URL | Filtered + URL | Yes | N/A |
| Library card click → modal opens | Modal only, no URL | Modal + URL | Yes | N/A |
| Library modal → X button closes | N/A (URL didn't exist before) | ~~URL stayed stale, refresh reopened the modal~~ **Fixed 2026-08-24**: X button now pushes `routes.library({tab, category})` instead of just clearing local state; the existing URL-sync effect does the rest | Yes | Yes |
| Library modal → browser Back closes | N/A | Closes modal AND reverts URL correctly | — | N/A (already correct) |
| `/library/{type}/{slug}` direct open | Did nothing — no modal | Opens the matching detail modal | No | Yes |
| `/library/agents`, `/library/skills`, `/library/hooks` (old routes) | Separate routes | Redirect into `/library?tab=...` | No (intentional consolidation) | N/A |

## 7. Settings & Analytics

| Path | Old | New | Same | Fixed |
|---|---|---|---|---|
| Settings tab — direct URL (`/settings/ai-model` etc.) | Always opened on Profile (bug) | Honors the URL's section | No | Yes |
| Settings tab — **clicking** a tab | N/A (gap not in original audit) | ~~URL stayed on the cold-open tab, refresh bounced you back~~ **Fixed 2026-08-24**: `AccountSettings` now owns its own `useRouter()` and calls `router.replace()` alongside `setSection` on every tab click, matching the pattern `LibraryPage`/`AnalyticsPage` already use | Yes | Yes |
| Analytics → date-range pill | Local only, no URL | Filtered + URL persists on refresh | Yes | N/A |
| Analytics → pipeline-type dropdown | Local only, no URL | Filtered + URL persists on refresh | Yes | N/A |

## 8. Auth, session expiry, and error pages

| Path | Old | New | Same | Fixed |
|---|---|---|---|---|
| Any 401 (WS, run-stream, handoff, api.ts, ppt/prototype APIs, etc.) | Inconsistent — some silent, some stranded the user | Unified → `/login?expired=true` | No | Yes |
| `/login` on session-expiry redirect | No message | Shows "Your session expired..." | No (improved) | Yes |
| Admin page → auth check fails | Immediate bare `/login` | 401 defers to the shared handler | No (improved) | Yes |
| Admin page → internal nav | `/login`, `/dashboard` (hardcoded) | Same, via typed routes | Yes | N/A |
| Standalone `/workflow` page → Close | `/dashboard` | `/dashboard` (same) | Yes | N/A |
| `/preview-fullscreen` with no data | In-page error UI | Redirects to `/runs` | No | Yes |
| `/preview-fullscreen?runId=X` | Did not exist | Redirects to `/runs/{id}/preview/full` | N/A (new) | N/A |
| `/test-preview` | Mock preview page | Route deleted — 404s | No (intentional removal) | N/A |
| `/` (root) | Always `/login`, ignored auth state | Checks auth → dashboard or login | No | Yes |
| 404 page | Framework default | Branded page w/ 3 links | N/A (new) | N/A |
| Uncaught error (route/global) | Framework default | Branded error pages | N/A (new) | Blocked (deliberately not force-tested — too invasive) |
| Logout control / login-check redirect | `/login` (hardcoded) | `/login` (typed, same) | Yes | N/A |

---

## Rows needing a fix — worklist status

1. ~~"Edit brief & run again" lands on the wrong workflow-type screen~~ — **FIXED 2026-08-24** (`DashboardLayout.tsx`, `handleEditBrief` relocated to use `effectiveReviseType`).
2. ~~Library detail modal's X button doesn't clear the URL~~ — **FIXED 2026-08-24** (`LibraryPage.tsx`, new `closeDetailModal` helper).
3. ~~Settings tab clicks don't update the URL~~ — **FIXED 2026-08-24** (`AccountSettings.tsx`, added its own `useRouter()`).
4. **Canvas divert-node link is dead code** — `ExternalPipelineCard` (`composer/CanvasNode.tsx:299`) is defined but never imported/rendered anywhere. Needs a placement decision (most likely the node-config rail's Route/outcomes editor) before it can be wired in — not fixed yet.

Also fixed in this pass, found as a side effect (not one of the 3 original bugs, but was blocking a clean `tsc`): `AppHeader.tsx`'s `currentPage` prop type was missing `"settings"`, a leftover gap from an earlier session's Settings-highlight fix.

## Live-run batch (2026-08-24) — resolved vs. still open

Ran 4 real pipelines (all fully terminal now, nothing left active — verified via `GET /api/runs` before ending this pass) to unblock the rows above that needed real run data. Resolved: `pipeline_start` SSE, "View Running", Notification→Go-to-Pipeline, and Cancel-mid-run-questionnaire (with a doc correction — see above). Newly found and worth a closer look: a `human` review gate didn't pause the run at all; a notification for a cancelled run routed to the general `/runs` list rather than that run's own page.

Still genuinely blocked despite real attempts:
- **Divert badge / skipped-agent row / divert terminal-state / `pipeline_diverted`+`agent_skipped` SSE** — 3 attempts to trigger a real divert all failed; the routing agent's own prompt anchors it to english/spanish regardless of input.
- **Reject a human review gate** — no pause occurred to reject; see the gate-not-pausing finding above.
- **LaunchWizard successful launch** — the one live PPT run hit a clarify pause before reaching generation; cancelled rather than completed.
- **PPT saved-workflow rows** — still no PPT-type saved workflow in this account (the live PPT run was cancelled before it could be saved).
- **Uncaught error page** — deliberately not forced (too invasive for a shared dev environment).
