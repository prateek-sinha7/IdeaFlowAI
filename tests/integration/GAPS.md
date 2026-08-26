# Gap register — everything not yet specified, and why

Sweeps 1–5 kept discovering surfaces the previous sweep had not known existed. This
register exists so that stops: it enumerates **every interaction surface in the
frontend from source**, marks what is specified, and gives every gap a reason.

A gap here is a decision. A surface *missing* from here is the actual failure mode.

Regenerate the raw inputs:

```
python3 tests/integration/capture/_gaps.py        # every interaction surface, by kind
python3 tests/integration/capture/_gaps.py --full # with file:line for each hit
python3 tests/integration/capture/_deadcode.py    # component files nothing imports
python3 tests/integration/capture/_uncovered.py   # components named in no spec
python3 tests/integration/capture/_enumerate.py   # pages, screens, overlays
python3 tests/integration/capture/_verify.py      # docs are internally consistent
```

---

## Why the earlier sweeps kept missing things

`_enumerate.py` looked for `fixed inset-0` and `role="dialog"`. That net was too
coarse in both directions — it counted an inline rail panel as an overlay (C12) and
the same component twice (C6/C20) — and it caught **no dropdown, no toast, no
keyboard shortcut and no navigation edge at all**.

`_gaps.py` widens it to eight categories. Current counts:

| Category | Hits | Files | Specified? |
|---|---:|---:|---|
| navigation (`router.push/replace/back`, `<Link>`, `window.open`, `location=`) | 100 | 33 | partial — see below |
| overlays (portal, `role=dialog`, `aria-modal`, fixed-inset) | 51 | 21 | ✅ all 19 reachable |
| dropdowns (`role=menu`, `role=listbox`, `aria-haspopup`, `aria-expanded`) | 54 | 19 | partial |
| toasts | 54 | 5 | ❌ **none** |
| keyboard shortcuts | 104 | 30 | partial — Escape only |
| native dialogs (`window.alert`) | 6 | 4 | ❌ **none** |
| uploads / drop zones / clipboard | 44 | 19 | partial |
| empty / error / loading branches | 733 | 104 | partial |

---

## 1. Toasts — no coverage at all

Five files raise transient notifications, and **not one scenario mentions them**:

| File | Trigger |
|---|---|
| `components/ui/CompletionToast.tsx` | a run finishes |
| `app/admin/page.tsx` | user created / plan or role changed |
| `components/layout/DashboardLayout.tsx` | app-level notices |
| `components/chat/ChatInput.tsx` | send failures |
| `components/handoff/HandoffWorkflow.tsx` | handoff actions |

Toasts are the single most common source of flaky E2E tests: they appear late,
disappear on a timer, and overlay the controls a test is about to click. Specifying
them is worth more than another static page.

**Blocked on:** nothing for the admin toast (creating a user is cheap and reversible
— it just needs an explicit decision to write to the dev DB). `CompletionToast`
needs a run to finish, so it needs a live LLM run.

## 2. `window.alert` — 6 calls, 4 files, zero handling

`AppBuilderPreview.tsx`, `PPTPreview.tsx`, `PreviewPanel.tsx`, `FilesTab.tsx`.

**A native dialog stalls Playwright until it is handled.** Any phase-2 test that
touches a preview or the Files tab must register a dialog handler or it will hang on
whatever condition triggers these. Nothing in the specs warns about it today.

## 3. Keyboard — Escape verified, the rest not

Nine files register a **global** key listener:

```
components/history/WorkflowHistory.tsx
components/workflow/composer/CanvasView.tsx
components/workflow/composer/WorkflowPickerModal.tsx
components/workflow/ppt/PPTTemplateGallery.tsx
components/workflow/prototype/CustomDesignSystemModal.tsx
components/workflow/prototype/CustomTemplateModal.tsx
+ 2 more
```

Escape was checked per-overlay and is **not uniform** (it closes every gallery modal
but not the add-agent modal — D-07). Six files also read `metaKey`/`ctrlKey`/`shiftKey`,
so modifier shortcuts exist and **none have been exercised**. `CanvasView` in
particular advertises "Hold Space + drag to pan" in its own UI.

**Blocked on:** nothing. This is mechanical and should be the next increment.

## 4. Navigation edges — 100, spot-checked

Every route was reached by cold `page.goto`. What is *not* systematically verified is
that each of the 100 in-app navigation edges lands where it claims:

- **47** `router.push` across 13 files
- **31** `router.replace` across 14 files
- **10** `window.open` across 8 files — new tabs, including the deliberate
  no-`noopener` App Builder handoff
- **6** `<Link>` — only in `not-found`, `HandoffWorkflow`, `CustomTemplateModal`
- **5** `location.href =` in `error.tsx`, `global-error.tsx`, `lib/api.ts` — **full
  page reloads**, which reset client state and will break any test that assumes SPA
  navigation
- **1** `router.back()` in `DashboardLayout`

The `location.href` assignments in the error boundaries matter most: they are the
app's escape hatch from a crash and nothing tests them.

## 5. Error boundaries — never rendered

`app/error.tsx` and `app/global-error.tsx` exist and both do a hard
`location.href =` reload. **Neither has ever been rendered in a sweep.** Reaching
them needs a deliberately thrown error — a route-level fault injection phase 2 can
do, but no seeded data will produce.

*(As of this sweep the dev server is in fact returning 500 for the whole `[...view]`
catch-all — see "Known blocker" below — which is exactly the class of failure these
boundaries exist for.)*

## 6. Run-history family and version UI

`components/history/RevisionFamilyView.tsx` (811 loc) is live — `WorkflowHistory`
imports `groupRunsByFamily`, `FamilyGroupCard`, `bucketAndSortFamilies`,
`buildDivertLinks`, and `RunDetailPage` imports `VersionTimeline`.

Captured screenshots show a flat list. **Family grouping, the version timeline and
the divert badge/links are unspecified.** Given D-12 (a nonexistent version silently
serves v1) and the diverted-run lane giving no link to its target, this is the area
where the specs are thinnest relative to how much logic exists.

**Blocked on:** a run family with more than one version — the dev DB has none.

## 7. The handoff feature — one page of five

`/handoff/{token}` was captured with an **invalid** token only. With a valid one it
mounts `HandoffWorkflow` → `HandoffAgentPanel`, `HandoffPreviewPanel`, `DiffView`,
`ReportViews` (`TestReportView`, `ComplianceReportView`) and `IntegrationsCard`.

That is roughly 1,400 lines of unexercised UI behind a credential-bearing feature
whose settings page is already flagged as the most security-sensitive surface in the
product.

**Blocked on:** a fixture that mints a valid handoff token.

## 8. Human-in-the-loop gate UI

`components/chat/InlineGateActions.tsx` (460 loc) and
`InlineClarifyActions.tsx` (304 loc) mount in the chat lane on `/[...view]`.

The lane capture saw only their *aftermath* — "Clarifications answered", "Review
approved — build continues". The **actual decision controls a human uses to answer a
gate have never been seen**.

**Blocked on:** a `waiting_for_user` run. This needs a live LLM run, and it creates a
gate that only a human should answer — flagged rather than spent, consistently with
every earlier sweep.

## 9. Unmountable components — code, not coverage

`_deadcode.py` finds **8 component files no other source file imports** (matching
exported symbols, with comments stripped — a filename-only check wrongly calls
`RevisionFamilyView` dead, and comment-matching wrongly calls `AgentModelPicker`
live):

| File | LOC | Note |
|---|---:|---|
| `components/sidebar/Sidebar.tsx` | 280 | a whole sidebar, mounted nowhere |
| `components/workflow/AgentModelPicker.tsx` | 167 | **deliberately** dead — `AgentsPopup.reskin.test.tsx` INV-3 asserts it is neither imported nor mounted |
| `components/workflow/prototype/TemplateCard.tsx` | 165 | |
| `components/chat/runtime/tool-renderers.tsx` | 160 | may be dispatched dynamically — verify before deleting |
| `components/results/ValidatorIssuePanel.tsx` | 134 | referenced only in a `types/index.ts` comment |
| `components/sidebar/ChatSessionItem.tsx` | 132 | pairs with `Sidebar` |
| `components/home/CreationHub.tsx` | 129 | **deliberately** dead — `DashboardLayout.catalogHome.test.tsx` asserts the home view does NOT mount it (superseded by `HomeLaunchGrid` in the `UXFIX-03`/`D-20` redesign) |
| `components/workflow/WorkflowControls.tsx` | 85 | |

~1,250 lines. **These are not coverage gaps — do not write scenarios for them.**
Two are deliberately retired with unit tests pinning that fact. The other six have
no such record, and `Sidebar` + `ChatSessionItem` together imply a chat-session
sidebar that was either removed or never finished.

Add `SkillManager` (D-17) to the list in spirit: it *is* imported, but its only host
page cannot produce the node that opens it, so no user can reach it either.

---

## Known blocker — the dev server is failing

At the time of writing, `http://localhost:3000` returns **HTTP 500 for the entire
`[...view]` catch-all** (`/dashboard`, `/create/*`, `/runs/*`, `/library`,
`/settings/*` — most of the app):

```
ReferenceError: require is not defined
  at doRender (.next/dev/server/chunks/ssr/…app-page.js?page=/[...view]/page…)
```

This is a Turbopack/Next dev-server bundle fault in the **main checkout**
(`~/Developer/Projects/VELOCITY-AI/frontend`), not in this worktree, and it is not
caused by anything in this suite. It needs a dev-server restart.

Every browser-driven item above is blocked until then. Everything in this register
was derived from source, which is why it could still be written.

---

## Priority for the next increment

1. **Keyboard shortcuts** — unblocked, mechanical, 9 global listeners plus modifiers.
2. **Toasts** — unblocked for the admin path; the highest-value flake source in E2E.
3. **`window.alert` handling** — a one-line note in the phase-2 harness prevents a
   class of hangs.
4. **Navigation edge assertions** — 100 edges, currently only spot-checked.
5. **Error boundaries** — needs fault injection, but the app is *currently* in the
   state they exist for.

Everything else waits on a fixture: a valid handoff token, a multi-version run
family, a `waiting_for_user` gate, a second account's session, or a hexaware user.
