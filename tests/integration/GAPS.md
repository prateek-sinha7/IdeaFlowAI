# Gap register — every surface, and its state

> **Status after sweep 6: every gap listed below is now SPECIFIED.**
> Four new feature files (`19`–`22`) cover toasts, native dialogs, the delete-user
> confirm, keyboard, navigation edges, error boundaries, run families and versions,
> the valid-token handoff, and the gate/clarify controls.
>
> Those scenarios are tagged **`@sourced`**: selectors and copy read from the
> components, behaviour not yet confirmed in a browser. That is a weaker standard
> than the capture-verified specs, and it is marked so nobody mistakes one for the
> other. This file now records **why each is not yet captured**, not that it is
> unknown.
>
> **Sweep 7 then asked a harder question** and got a worse answer. `_coverage.py`
> checks every *addressable control* — every `data-testid`, `aria-label` and form
> `name` — against the specs. Feature-level coverage was complete; **control-level
> coverage was 49%**. 150 of 298 controls were named in no spec.
>
> A page can be fully specified and still leave most of its buttons untargetable.
> That gap is now closed: **298 of 298, 100%**, in `23-controls-inventory` plus
> additions to `01-auth`, `15-overlays` and `22-handoff-and-gates`.
>
> What it turned up, none of which any earlier sweep knew existed: an entire
> **Cognito MFA challenge flow** on the login page; **revision inputs on all five
> preview types**; agent **proposals and refinements** in the chat lane; canvas
> **conditional routing, sub-agents, retry and parallelism limits**; **audit log
> exports** (CSV/JSON/report); an analytics **model filter**; and
> `chat-terminal-degraded`, a run state no other table in this suite mentions.
>
> **Sweep 8 checked two dimensions sweep 7 had not**, because "every control" was
> still measured on attributes only:
>
> - **Controls addressable only by their visible text** — no testid, no aria-label.
>   Four were unspecified: `Reconnect` (realtime connection loss, an affordance
>   nothing else in this suite covers), `Start a run` (the empty-history CTA),
>   `Save & Send` (edits AND resends in one action), `Back to sign in`. The gate now
>   measures this dimension: **307/307**.
> - **MFA self-service and password recovery.** `/settings/security` is second-factor
>   management, and the spec described it as "not available". Email codes are a
>   toggle; the authenticator row deliberately offers **no** control even though
>   `/mfa/totp/associate` and `/verify` exist. And `01-auth` implied there is simply
>   no password recovery — the truth is `/api/auth/forgot-password` **correctly
>   refuses** when email is a second factor, because AWS disqualifies email as a
>   recovery channel in that configuration, leaving admin reset as the only path.
>
> **What is still NOT asserted: the API contract itself.** The backend exposes 108
> endpoints. Every one has a path segment that appears somewhere in these specs, but
> that is a weak signal — a shared word like `users` satisfies it. These specs are
> UI-level throughout; they assert what a user sees, not status codes, payloads or
> per-endpoint authorization. `13-errors` covers a handful of auth status codes
> deliberately, and that is the extent of it.
>
> **Two things remain genuinely uncovered:** responsive breakpoints (no scenarios
> anywhere) and endpoint-level API contract tests (out of scope for this suite as
> written — a decision, not an oversight, but state it rather than imply coverage).
>
> Run `python3 tests/integration/capture/_coverage.py` to re-check. It exits
> non-zero while any control is unspecified, which is what stops this drifting back.

---

# Original register — everything not yet specified, and why

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
| navigation (`router.push/replace/back`, `<Link>`, `window.open`, `location=`) | 100 | 33 | ✅ `20-keyboard-and-navigation` (`@sourced`) |
| overlays (portal, `role=dialog`, `aria-modal`, fixed-inset) | 51 | 21 | ✅ all 19 reachable |
| dropdowns (`role=menu`, `role=listbox`, `aria-haspopup`, `aria-expanded`) | 54 | 19 | partial |
| toasts | 54 | 5 | ✅ `19-toasts-and-dialogs` (`@sourced`) |
| keyboard shortcuts | 104 | 30 | ✅ `20-keyboard-and-navigation` (`@sourced`) |
| native dialogs (`window.alert`) | 6 | 4 | ✅ `19-toasts-and-dialogs` (`@sourced`) |
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

**Now specified** in `19-toasts-and-dialogs` — both timeouts (3500ms admin vs 7000ms
completion), every verbatim message, and the pointer-events contract that stops a
toast eating clicks. Sweep 6 also found a **delete-user confirm dialog** on `/admin`
nobody had noticed: the most destructive control in the product, previously unspecced.

**Still not captured:** dev server 500; the delete path needs a disposable fixture user.

## 2. `window.alert` — 6 calls, 4 files, zero handling

`AppBuilderPreview.tsx`, `PPTPreview.tsx`, `PreviewPanel.tsx`, `FilesTab.tsx`.

**A native dialog stalls Playwright until it is handled.** Any phase-2 test that
touches a preview or the Files tab must register a dialog handler or it will hang on
whatever condition triggers these.

**Now specified** in `19-toasts-and-dialogs`, with all six verbatim messages and a
harness scenario requiring a global dialog handler.

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

**Now specified** in `20-keyboard-and-navigation`, including the Escape matrix (9 of
10 overlays, the tenth being D-07) and `CanvasView`'s space-to-pan typing guard —
the highest-value keyboard assertion in the suite, since losing it silently stops
every canvas text field accepting spaces.

**Still not captured:** dev server 500. The modifier bindings in six files remain
`@unverified` — enumerate them before asserting.

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
app's escape hatch from a crash.

**Now specified** in `20-keyboard-and-navigation` — an outline for in-app edges, the
new-tab affordances, and the full-reload paths asserted *as* reloads.

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

**Now specified** in `21-run-families-and-versions` — family collapsing, the version
timeline, the `v3` / `"3 versions"` aria split, and both directions of the divert
link.

**Still not captured:** no multi-version run family exists. One revised run unlocks
this entire file.

## 7. The handoff feature — one page of five

`/handoff/{token}` was captured with an **invalid** token only. With a valid one it
mounts `HandoffWorkflow` → `HandoffAgentPanel`, `HandoffPreviewPanel`, `DiffView`,
`ReportViews` (`TestReportView`, `ComplianceReportView`) and `IntegrationsCard`.

That is roughly 1,400 lines of unexercised UI behind a credential-bearing feature
whose settings page is already flagged as the most security-sensitive surface in the
product.

**Now specified** in `22-handoff-and-gates` — all three states verbatim, the
`canStart = pending || failed` rule, and the deliberate vagueness of the
"Handoff not found" screen as a security property.

**Still not captured:** needs a fixture that mints a valid token.

## 8. Human-in-the-loop gate UI

`components/chat/InlineGateActions.tsx` (460 loc) and
`InlineClarifyActions.tsx` (304 loc) mount in the chat lane on `/[...view]`.

The lane capture saw only their *aftermath* — "Clarifications answered", "Review
approved — build continues". The **actual decision controls a human uses to answer a
gate have never been seen**.

**Now specified** in `22-handoff-and-gates` — every gate testid (`chat-gate-approve`,
`-request-changes`, `-redo`, `-reject`, the templated `chat-gate-choice-<value>`) and
every clarify testid, including `chat-clarify-cancel-workflow`, which **cancels the
whole run** from what reads as a question prompt and sits beside "skip all".

**Still not captured:** needs a `waiting_for_user` run — a live LLM call, and it
creates a gate only a human should answer. The spec includes a scenario stating that
no phase-2 fixture may auto-approve gates, because an auto-approver would make every
scenario in that file pass without testing anything real.

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

Everything above is now specified. What remains is **capture** — turning `@sourced`
scenarios into verified ones — in this order:

1. **Restart the dev server.** Everything browser-driven is blocked until the
   `[...view]` catch-all stops returning 500.
2. **Keyboard and toasts** — no fixture needed beyond a running app. The space-to-pan
   typing guard and the two toast timeouts are the highest-value items.
3. **The `window.alert` dialog handler** — one line in the phase-2 fixture; prevents
   a class of hangs that look like infrastructure failure.
4. **One revised run.** A single revision unlocks the whole of
   `21-run-families-and-versions` — family grouping, the version timeline, D-12's
   real test — and a completed `ex_A3_divert` run unlocks both divert-link directions.
5. **Error boundaries** — fault injection, cheapest via intercepting one required
   request and returning malformed data.

Still fixture-blocked after that: a valid handoff token, a `waiting_for_user` gate, a
second account's session, a hexaware user, a deck deliverable for `Slides`.

## The one surface with no spec at all

**Responsive breakpoints.** Every capture ran at one desktop viewport. No scenario
anywhere asserts what happens at tablet or phone width, and no source enumeration can
substitute for looking — breakpoints live in Tailwind class strings across 100+
components, and whether a layout *works* at 375px is a judgement, not a grep.

This is recorded as a known, deliberate omission rather than dressed up as covered.
Closing it means picking target breakpoints with the product owner first.
