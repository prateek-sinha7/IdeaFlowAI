# Defects observed during the capture sweeps

Found by walking the product, not by looking for bugs. Each is reproducible from a
cold URL. **Nothing here has been fixed** — the capture phase records, it does not
repair. Each has a `@defect` scenario in `screens/` written to today's behaviour so
phase 2 has a baseline that goes red when the fix lands.

D-01…D-05 came from sweep 1 (routes). D-06…D-11 came from sweep 2 (states,
overlays, tiers).

---

## D-01 — `/create/app` launches the wrong workflow

**Severity:** high — a user who follows this URL runs a pipeline they did not pick.

`/create/app` and `/create/user-stories` render the **same screen**: `GENERATE
PRODUCT REQUIREMENTS` / "Provide the brief" / `Advanced 7 agents`. `/create/app`
should launch `app_builder`.

**Root cause** — `frontend/src/app/[...view]/page.tsx:307`:

```ts
function initialWorkflowTypeFor(parsed: ParsedView): string | undefined {
  return parsed.screen === 'create-workflow' ? parsed.pipelineType : undefined;
}
```

`initialMainViewFor` maps `create-app` and `create-user-stories` to `"input"`
(lines 123-125), which is right — but `initialWorkflowTypeFor` returns a type only
for `create-workflow`. Both named screens reach the launch panel with **no workflow
type**, and the panel falls back to its default, `user_stories`.

The open-ended branch works correctly: `/create/ex_A2_branch` renders `BRANCH BY
LANGUAGE` / `Advanced 5 agents`. The generic path is right; the two hand-written
special cases are broken.

**Fix sketch:** map `create-app` → `app_builder` and `create-user-stories` →
`user_stories`, or delete both special cases and let them fall through to
`create-workflow`.

**Evidence:** `capture/07`, `08`, `09`.

---

## D-02 — `/runs/{id}/workspace` works but is not in the routing contract

**Severity:** medium. **RESOLVED at `9b0fb8c79`.**

`routes.ts` now exposes `runWorkspace: (id) => /runs/${id}/workspace`, `ParsedView`
carries a `run-workspace` variant, and `parseViewPath`'s `runs` branch handles
`subpath === 'workspace'`. The route is now both built and parsed by `routes.ts`, as
ADR-0018 requires.

`07-run-detail.feature.md` no longer tags this `@defect`; it asserts the correct
behaviour instead, so a regression fails rather than passing quietly. The original
report is kept below because the screenshot `05-runs/p27` predates the fix.

---

Run detail has **five** tabs: Preview, Steps, Files, Workspace, Audit. Clicking
Workspace pushes `/runs/{id}/workspace`, and a cold load renders correctly with the
tab selected.

But `routes.ts` has **no `runWorkspace` builder**, and `parseViewPath`'s `runs`
branch handles only `steps`, `files`, `audit`, `stream`, `versions` and
`preview/full` before returning `{ screen: 'unknown' }`. It renders anyway because
`DashboardLayout` owns the tab independently of the parser.

ADR-0018 says every URL in the app is built and parsed by `routes.ts`. This one is
neither.

**Evidence:** `capture/40`, `41`.

---

## D-03 — `?expired=1` silently does nothing

**Severity:** low.

`/login?expired=true` renders "Your session expired. Please sign in again."
`/login?expired=1` renders **no banner** — an exact string compare against `"true"`.
`routes.login({expired:true})` always emits `true`, so only a hand-written or
external link degrades, and it degrades silently.

**Evidence:** `capture/02` vs the `expired=1` probe.

---

## D-04 — Test fixtures ship in the real catalog

**Severity:** product decision. Filed as **ISS-187**.

Seven spec-014 conditional-gate fixtures are `user_launchable: true` and entitled to
`enterprise` on both sides (`backend/app/core/entitlements.py:47-53`,
`frontend/src/lib/entitlements.ts:63-69`), so they render as ordinary catalog cards:
Retry Until It Passes, Branch by Language, Spanish Greeter, Dutch Greeter, Hand Off
to Another Workflow, Ask a Human Then Hand Off, Ask a Human Then Decide.

Their descriptions are engineer-facing, and one names an internal manifest id in
user copy: *"The plain workflow ex_A3_divert diverts into for the 'spanish' outcome."*

They also appear as **seven library categories with a count of 0** — half the agent
filters on the Library page are dead.

**Sweep 2 confirmed this reaches real users:** `qa-enterprise` (enterprise tier,
**not** an admin) sees all seven unlocked. It is not an admin-only artefact.

**Evidence:** `capture/03`, `24`, `68`.

---

## D-05 — A saved override's agent count disagrees with its launch panel

**Severity:** unconfirmed.

Saved workflow *My presentation* (base `ppt`) reports **4 agents** on `/workflows`
and `/workflows/{id}`. `/workflows/{id}/run` renders the ppt panel showing
**`Advanced 3 agents`** — the base manifest's count.

If the launch runs the override's 4 steps, the panel is mislabelled. If it runs the
base's 3, the override is ignored at launch, which would be serious. **The sweeps
did not launch a run, so which happens is unknown.** Phase 2 must settle it by
counting dispatched agents.

**Evidence:** `capture/12`, `15`.

---

## D-06 — A live run cannot deep-link any tab

**Severity:** high — shared links to a running run land on the wrong screen.

Cold-loading **any** tab URL of a run whose status is `generating` redirects to
`/runs/{id}/stream` and forces the **Steps** tab:

| Requested | Landed on | Tab selected |
|---|---|---|
| `/runs/{id}/audit` | `/runs/{id}/stream` | Steps |
| `/runs/{id}/files` | `/runs/{id}/stream` | Steps |
| `/runs/{id}/steps` | `/runs/{id}/stream` | Steps |

The same URLs work correctly once the run completes, so the override is
status-dependent rather than route-dependent.

This is the exact class of gap spec 015 set out to eliminate: a URL that is
addressable for one object state and silently not for another. Sharing "look at the
audit trail of this running job" is impossible.

**Evidence:** `capture/44`, `46`.

---

## D-07 — The add-agent modal's only close control has no accessible name

**Severity:** medium — accessibility, and it breaks the documented automation recipe.

The add-agent library modal (`workflow/AgentLibrary.tsx`, opened by
`button[aria-label="Add agent"]`) closes only via an `h-8 w-8` icon button with
**empty text, `aria-label` null, and `title` null**. A screen-reader user has no
name for it; an automated test has nothing stable to target.

Two related corrections to the `ba-browser` velocity definition, both of which its
`addAgentModalStaysOpen` quirk gets wrong:

- **Escape does NOT close this modal.** The quirk claims "Escape closes it reliably.
  Verified 2026-08-19." It did not, repeatedly, in this sweep.
- The per-card `+ Add` ambiguity the quirk works around with `clickNear` is
  unnecessary — each card carries a stable **`data-testid="library-card-<agentId>"`**.

**Evidence:** `capture/53`.

---

## D-08 — User-facing copy points at a tab that does not exist

**Severity:** low.

A cancelled run's empty Preview reads:

> This run was cancelled
> The run was stopped before producing a deliverable.
> **Open the Thinking tab to view details.**

There is no Thinking tab. The tab is labelled **Steps**. The stale name survives in
the testid (`tab-thinking`) and has leaked into user-visible copy.

**Evidence:** `capture/47`.

---

## D-09 — Locked catalog cards are shown, not hidden (spec correction)

**Severity:** none — this is a **correction to my own earlier spec**, not a product
defect. Recorded so the wrong assertion does not get written into phase 2.

Sweep 1 was captured only as `qa-admin` (enterprise), where nothing is locked, and I
wrote scenarios asserting a lower tier "does NOT see" a card. That is wrong.

Every card renders for every tier. Entitlement shows as a **lock badge**:

| Card | basic | pro | enterprise |
|---|---|---|---|
| Generate product requirements | ✅ | ✅ | ✅ |
| Pitch an idea / (v2) | Requires Pro | ✅ | ✅ |
| Build an interactive prototype | Requires Pro | ✅ | ✅ |
| Build an end-to-end application | Requires Pro | ✅ | ✅ |
| Compose a custom workflow | Requires Enterprise | Requires Enterprise | ✅ |
| the 7 `ex_A*` fixtures | Requires Enterprise | Requires Enterprise | ✅ |

Phase 2 must assert on the **badge**, not on absence.

**Evidence:** `capture/64`, `67`, `68`.

---

## D-10 — A user override changes the catalog card's agent estimate

**Severity:** unconfirmed — possibly intended.

The "Build an end-to-end application" card reports a different agent count per user:

| User | Card reads | Has an override? |
|---|---|---|
| qa-basic | `~15 agents` | no |
| qa-admin | `~1 agents · ~33m` | yes — *My app_builder*, 1 agent |

The admin's saved override appears to shadow the built-in's estimate on the catalog
card. Arguably correct — the card predicts *your* run — but it means the same card
advertises wildly different work depending on hidden per-user state, and the
duration (`~33m`) did not scale with it.

**Evidence:** `capture/03`, `64`.

---

## D-11 — Analytics shows a duplicated and a raw pipeline label

**Severity:** low.

The By Pipeline Type breakdown lists **`PROTOTYPE` twice** with different figures
(12 runs / 11.4M / $4.49 and 8 runs / 2.4M / $0.86) — two underlying types
collapsing to one display label, most likely `prototype` plus a tiered revision
manifest. It also shows **`PPT_V2`** raw and snake-cased next to properly formatted
neighbours like `PRESENTATION` and `.NET MIGRATION`.

Separately, the success-rate tile reads as exhaustive but is not: 140 completed + 33
failed = 173 against 241 total. The percentage (58%) is right; the breakdown just
omits the other 68 runs.

**Evidence:** `capture/35`.

---

## D-12 — A nonexistent artifact version silently serves v1

**Severity:** low, but it makes a URL lie.

`/runs/{id}/versions/99` on a run whose artifact has only version 1 renders the
artifact, shows `Version v1` in the picker, and returns HTTP 200. The URL still
reads `/versions/99`. Nothing anywhere on the page says the requested version does
not exist.

A shared link to a version that was later removed therefore shows the wrong content
with no indication it is the wrong content.

**Expected:** either a not-found state, or the artifact plus a visible notice that
the requested version was unavailable and v1 was served instead.

**Evidence:** `capture/p34-run-version.json`,
`screenshots/11-errors/p56-run-version-nonexistent.png`.

---

## D-13 — Forcing an incompatible preview renderer yields a blank pane

**Severity:** low.

The run preview offers `RENDERS AS: Auto | HTML | Markdown | Bundle`. On a Markdown
deliverable (`greeting.md`), choosing **HTML** renders **nothing at all** — no
content, no message, no "this file is not HTML" fallback. The pane is simply empty.

`Bundle` on the same file at least says "No files generated yet". `Auto` and
`Markdown` both render correctly. Only HTML fails silently.

**Expected:** the same courtesy Bundle already extends — say why the pane is empty.

**Evidence:** `capture/AUDIT-overlays-and-tabs.json`,
`screenshots/13-states/84-preview-renderer-html-blank.png`.

---

## D-14 — Run cards are not links, and the run history has no test hooks

**Severity:** medium — accessibility and testability, not correctness.

On `/runs`, every run card is a `div[role="button"]` with a click handler. There are
**zero anchors** to `/runs/{id}` on the page. Consequences for a real user:

- middle-click and ⌘-click do not open a run in a new tab
- right-click offers no "Open link in new tab"
- the URL is not visible on hover
- nothing is copyable as a link

Separately, `document.querySelectorAll('[data-testid]').length` is **0** for the
whole page. Every phase-2 assertion on run history must go through text or DOM
structure, both of which move with copy edits and restyling.

**Expected:** cards wrap an `<a href>` to the run, and the list carries testids.

**Evidence:** `capture/AUDIT-overlays-and-tabs.json`.

---

## D-15 — An unrecognised run-history filter shows an empty list, not an error

**Severity:** low.

The Presentation chip reads "Presentation 7" and sets `/runs?type=ppt`, which
correctly renders 7 cards. But `/runs?type=presentation` — the obvious guess, and
what a human would type or a stale link would carry — renders **"No runs match this
filter"** while the chip beside it still claims 7.

An unrecognised `type` value is treated as a filter that matches nothing, rather
than being rejected or falling back to All. A shared link with a wrong or renamed
type silently shows an empty history that looks like data loss.

**Expected:** an unknown `type` falls back to All, or says the filter is not
recognised. Not silence.

**Evidence:** `capture/AUDIT-overlays-and-tabs.json`.

---

## D-16 — A fourth tier, `hexaware`, exists in code and admin but in no spec

**Severity:** medium — it breaks the assumption every tier scenario rests on.

The admin Create-User dialog offers four plans: Basic, Pro, Enterprise and
**Hexaware**. `hexaware` is a real tier in both `backend/app/core/entitlements.py`
and `frontend/src/lib/entitlements.ts`, with `TIER_LABELS` and an `UPGRADE_PATH`
entry (`hexaware` → `enterprise`, skipping pro).

**It is not a rung on the basic → pro → enterprise ladder. It is sideways:**

| Pipeline family | basic | hexaware | pro |
|---|---|---|---|
| user_stories | ✓ | ✓ | ✓ |
| ppt | ✓ | **✗** | ✓ |
| prototype | ✗ | **✓** | ✓ |
| app_builder | ✗ | ✗ | ✓ |

So a hexaware user has prototype access that basic lacks, while **losing** the ppt
access basic has. "Upgrading" a user from basic to hexaware removes their ability to
make presentations.

The comment in `entitlements.py` says this is deliberate (KAN-161 / ISS-055 — a
scoped tier for deployments needing prototype + user_stories only). The defect is not
the tier; it is that **every tier spec, the lock matrix in `17-theme-and-tiers`, and
the whole capture sweep modelled tiers as a totally-ordered chain of three**. There
is no seeded hexaware account, no scenario, and no lock-matrix column for it.

`test_entitlement_parity` keeps the two `TIER_PIPELINES` maps in sync, so the tier is
consistently implemented — it is the specs, not the code, that are incomplete.

**Expected:** a seeded hexaware fixture, a fourth lock-matrix column, and at least
one scenario asserting the non-monotonic case — that a hexaware user is offered
prototype and is refused ppt.

**Evidence:** `capture/AUDIT-overlays-and-tabs.json`,
`screenshots/12-overlays/81-modal-admin-create-user.png`,
`backend/app/core/entitlements.py:5-27`, `frontend/src/lib/entitlements.ts:1-25`.

---

## D-17 — SkillManager is unreachable: its only host page cannot create a node

**Severity:** low as a bug, high as a signal about `/workflow`.

`SkillManager` opens from `button[aria-label="Manage skill"]` on an `AgentNode`,
rendered only while `agent.status === "idle"`. Its mount chain has exactly one root:

```
app/workflow/page.tsx:58            → WorkflowView
components/workflow/WorkflowView.tsx:493  → PipelineGraph
components/workflow/PipelineGraph.tsx:90  → AgentNode
components/workflow/AgentNode.tsx:197     → SkillManager
```

That root is `/workflow` — the orphaned legacy builder (p21) that nothing in the app
links to. And that page **cannot produce a node**: it starts with 0 agents, and its
`Add Agent` picker returns **"No agents found" for every category** — All, User
Stories, Presentation, Prototype, App Builder, Custom.

So `SkillManager` cannot be opened by any user, by any route. It is live code behind
a broken door on an unlinked page.

This is the concrete answer to the open question in `16-pages-outside-routes`
("either it works or it should be removed"): **its agent picker does not work**.

**Evidence:** `capture/AUDIT-remaining-popups.json`,
`screenshots/12-overlays/86-modal-legacy-builder-add-agent-empty.png`.

---

## D-18 — A prototype run previews the spec text instead of its validated HTML

**Severity:** medium — the deliverable is correct and the user cannot see it.

Run `d9693cbe` (Prototype, Done, 2 agents). Its **Files** tab reports:

> 4 files available · 1 deliverable — FINAL OUTPUT **`prototype.html`**,
> HTML (.html) · 11.8 KB · **validated**

Its **Preview** tab renders `Output (text format):` followed by the raw `<spec>`
markdown — the spec agent's intermediate output — as plain text. Zero iframes.
Clicking `Preview` on the `prototype.html` file row does not change it.

Because `PrototypePreview` never mounts, none of its controls exist in the DOM:
zoom in/out/reset, `Open tweaks panel`, `View source`, `Open in new tab`,
`Revision instructions` (`PrototypePreview.tsx:514-552`). An entire feature is
unreachable for this run — which is why the sweep could not capture C11.

**Expected:** the Preview tab renders the validated deliverable named by the Files
tab.

**Evidence:** `capture/AUDIT-remaining-popups.json`,
`screenshots/13-states/88-prototype-preview-renders-spec-text.png`.

---

## D-19 — Terminal runs disagree on whether the user may reply

**Severity:** low.

The concierge chat lane's composer is present or absent by run state with no visible
rule:

| Status | `chat-composer` in DOM | textarea | send |
|---|---|---|---|
| Done | ✓ | ✓ enabled | ✓ |
| **Failed** | ✓ | **✓ enabled** | ✓ |
| **Cancelled** | ✓ | **✗ absent** | ✗ |
| **Diverted** | ✓ | **✗ absent** | ✗ |

Three terminal states, two contracts. A user who cancels a run loses the ability to
ask a follow-up; a user whose run failed keeps it. Note `chat-composer` is in the DOM
for all of them — the container is not the signal, so a test asserting on it will
pass while the user has no input at all.

**Expected:** one rule, applied consistently, whatever it is.

**Evidence:** `capture/AUDIT-chat-lane.json`,
`screenshots/14-chat-lane/c02-lane-cancelled-readonly.png` vs `c03-lane-failed.png`.

---

## D-21 — The prototype run's clarification exchange appears twice

**Severity:** low.

*(D-20 is deliberately unused: `UXFIX-03`/`D-20` are upstream design-doc ticket ids
referenced in `02-home-catalog`, and reusing the number here would be ambiguous.)*

The completed prototype run's transcript contains:

```
Before I build, I need to lock a few things down.   → Answer in Steps
Clarifications answered                             → Answer in Steps
Before I build, I need to lock a few things down.   → Answer in Steps
Clarifications answered                             → Answer in Steps
Run started                                         → Open in Steps
```

Each pair has a **different `data-message-id`**, so these are genuinely two records,
not one rendered twice. Two clarification rounds would be a legitimate explanation —
but the two rounds are identical in text and offer the same action, so the lane reads
as a stutter regardless of which it is.

**Expected:** either one exchange, or two that are distinguishable from each other.

**Evidence:** `capture/AUDIT-chat-lane.json`,
`screenshots/14-chat-lane/c01-lane-completed-prototype.png`.

---

# Corrections to earlier sweeps

Not product defects — places where an earlier sweep wrote down something that
turned out to be wrong. Recorded here so the wrong claim is not quietly deleted.

| # | Claimed | Actually | Corrected in |
|---|---|---|---|
| C-1 | `/workflow/create?mode=ppt\|prototype` renders the legacy wizard in place; FR-007/T17's redirect "has not landed" | Both redirect to `/create/ppt` and `/create/prototype`. The redirect landed; the `routes.ts` comment is stale | `03-launch-panels`, `16-pages-outside-routes` |
| C-2 | A bare `/settings` shows the 404, deliberately, and must not redirect | It redirects to `/settings/profile`. `parseViewPath` does return `unknown`, but the page does not stop there | `09-settings`, `13-errors` |
| C-3 | `/` redirects to `/login` unconditionally | It branches on token presence: `/dashboard` if a token exists, `/login` if not | `MANIFEST` row A1 |
| C-4 | `/runs/{id}/versions/{v}` uncapturable — "no multi-version run exists" | It renders fine with a single-version run; only a version *switch* is unobservable | `MANIFEST` group B |
| C-5 (was D-09) | Locked catalog cards are hidden from lower tiers | They are always shown, with a "Requires &lt;Plan&gt; plan" badge. Sweep 1 was captured only as an enterprise admin, where nothing is locked | `02-home-catalog` |

**The common cause of C-1 to C-4:** all four were written from reading source —
`parseViewPath`, a `routes.ts` comment, a builder's absence — rather than from
loading the URL. The parser's return value is not the user's destination, and a
comment is not the code. Every routing claim in these specs is now backed by a
fingerprint in `capture/`.

---

## D-22 — Escape does not close the Advanced workflow modal

**Severity:** low. **Found by:** `S-03-11`, phase 2.

`Advanced <N> agents` on any launch panel opens the full workflow canvas as a
modal — `fixed inset-0 z-50`, intercepting pointer events on everything beneath
it, including the control that opened it.

**Escape does nothing.** The roster stays open. The only ways out are the
`Cancel` button and an icon-only close control (see D-23).

`20-keyboard-and-navigation` describes an Escape matrix covering every overlay in
the product. This one is not in it, and the launch panel is one of the most
frequently opened surfaces there is.

`S-03-11` asserts the current behaviour, so fixing this turns that test red
rather than letting the change pass unnoticed.

---

## D-23 — The Advanced modal's close button has no accessible name

**Severity:** low, accessibility. **Found by:** `S-03-11`, phase 2.

The icon-only control in the modal's top corner carries **no `aria-label`, no
`title`, no `data-testid` and no text**. Its only distinguishing feature is a
CSS class string.

A screen-reader user meets an unlabelled button. A test can only reach it by
matching on styling, which breaks on any restyle — so the suite uses `Cancel`
instead, and this control is currently untested.

One `aria-label="Close"` fixes both problems.

---

## D-24 — The daily-activity chart is invisible to assistive technology

**Severity:** medium, accessibility. **Found by:** `S-10-11`, phase 2.

Each bar in Analytics' Daily Activity chart is a bare `<div>`:

```html
<div data-testid="bar-chart-bar" class="w-full rounded-t-[3px] cursor-pointer"
     style="background: var(--brand); opacity: 1; height: 100%;"></div>
```

**No `aria-label`, no `title`, no text content.** The value exists only as a CSS
height percentage. A screen-reader user gets nothing from this chart, and a test
can only read a relative height — never the token figure the chart is drawing.

The chart's CONTAINER does carry `aria-label="Daily token usage for Last 30
days"`, so the chart announces its subject and then says nothing about its data.
The tiles beside it are readable, so this is the one part of the screen that is
not.

`S-10-11` therefore asserts what the markup supports — that bars are plotted and
that a zero-token day is drawn at zero rather than omitted — and this defect
records why it cannot assert the figures themselves.

**Fix sketch:** one `aria-label` per bar, e.g. `"Aug 14: 31,331,878 tokens"`.
The data is already in hand at render time; the same string would make `S-10-11`
able to check the figures.

---

## D-25 — "All fields are required" is unreachable dead code

**Severity:** low, dead code. **Found by:** `S-09-05`, phase 2.

`handleChangePassword` opens with:

```ts
if (!currentPassword || !newPassword || !confirmPassword) {
  setMessage({ type: "error", text: "All fields are required" });
  return;
}
```

The button that calls it is already `disabled={changing || !currentPassword ||
!newPassword || !confirmPassword}` — the exact same condition. The guard can
never fire through the UI, so that string can never be shown to a user.

Harmless as defence in depth, and `S-09-05` asserts the disabled button instead
(a stronger refusal than a banner). Recorded so that the string is not mistaken
for a reachable state by whoever writes the next test — and so nobody "fixes"
a test that fails to find it.

**Fix sketch:** leave the guard, delete the message, or drop the `disabled`
condition and let the banner explain the refusal. Not both.

---

## D-26 — Half the library's agents are unreachable by any category pill

**Severity:** medium, discoverability. **Found by:** `S-08-05`, phase 2.

The agent grid renders every agent (93). The category pills are built from a
different list:

```ts
...workflows.filter((w) => w.user_launchable && !w.is_beta && !["custom"].includes(w.id))
```

Counting the 93 cards by the workflow label each one displays gives 19 distinct
workflow types. Only 12 of them have a pill. The named pills account for 41
agents; the other 52 — `.NET TO AZURE` (13), `MULESOFT TO SPRING BOOT` (13),
`SPEC_KIT` (8), `CHAT` (7), and eight revision/fixture types — can be reached
only by scrolling "All".

So the spec's `S-08-05` ("the sum of the other category counts equals the All
count") is not merely unmet; it cannot hold while the two lists are derived
differently. This is the same root cause as **D-04**, seen from the other side:
D-04 is seven pills with no agents, D-26 is fifty-two agents with no pill.

`S-08-05` therefore asserts what IS invariant — the All pill equals the grid,
and no pill claims more agents than exist.

**Fix sketch:** derive the pills from the pipeline types actually present among
the rendered agents, rather than from the launchable-workflow list. That closes
both directions at once — the empty pills disappear and the orphaned agents gain
one.

---

## D-27 — Switching a library tab writes no history entry

**Severity:** low. **Found by:** `S-08-04`, phase 2.

The tab strip and the category pills both call `router.replace`, not `push`:

```ts
router.replace(routes.library({ tab, category: ... }));
```

The URL updates and is shareable, so deep links work. But Back does not return
to the previous tab — it leaves the library altogether, skipping every tab and
filter the user moved through. On a screen whose whole navigation model is
"three tabs and a row of filters", that is the one gesture most likely to be
tried.

`S-08-04` asserts today's behaviour and will fail loudly if this is changed to
`push`, which is the point: the spec's original claim was that Back returns to
Agents, and whoever makes that true should be told the test agrees again.

---

## D-28 — The saved-workflow detail view is unreachable from the UI

**Severity:** low. **Found by:** `S-05-06`, phase 2.

`/workflows/{id}` renders a read-only summary — type badge, title, description,
`4 AGENTS` and the agent roster, plus Edit and Run. Nothing links to it.

`SavedWorkflowsPage` attaches `onClick` to the actions menu and to
`Run workflow`, and to nothing else. The card body, the monogram and the title
are all inert, so the only way to reach the detail view is to type its URL —
which requires knowing an id the list never displays.

Two smaller things found alongside it, recorded here rather than as their own
cards:

- The detail view's `Edit` and `Run` are real anchors with hrefs. The
  run-history rows one screen over are `div[role="button"]` with no URL at all
  (D-14). The same product answers the same question two ways.
- `Run workflow` on a saved override's card lands on `/create/ppt` — the base
  wizard's own route, carrying no reference to the saved row. `/workflows/{id}/run`
  at least keeps the id in the URL. More evidence for **D-05**: the binding is
  dropped before the panel renders.

**Fix sketch:** make the card body open the detail view, as the library's cards
do. The menu already holds Edit; a body click has nothing to collide with.

---

## D-29 — `Run once` is not disabled while the brief is too short

**Severity:** low. **Found by:** `S-04-14`, phase 2.

The composer shows "3 more characters to enable Run" under the brief field, and
`Run once` renders with `title="Add a brief first"` — but no `disabled`
attribute. The button is focusable, clickable, and reads as available.

A `title` is a mouse affordance. A keyboard or screen-reader user meets the
button as enabled and learns otherwise only by pressing it. The hint text is
elsewhere in the DOM, not associated with the control.

`S-04-14` asserts the title and the hint, and asserts the button is NOT disabled
— so it fails the day this is fixed, which is the signal to rewrite it as the
spec's stronger version.

**Fix sketch:** add `disabled` alongside the existing title, and point
`aria-describedby` at the hint.

---

## D-30 — No node can be removed from a new custom workflow

**Severity:** high. **Found by:** `S-04-08`, phase 2.

Open `/workflows/new`, add three agents from the library, and every one of them
comes back with its Remove control like this:

```html
<button aria-label="Remove Estimation Agent" title="Core agents can't be removed"
        disabled class="… disabled:cursor-not-allowed disabled:opacity-0">
```

All three are disabled. Only ONE of the three renders a `Core` badge. Two of
them — Estimation Agent, Backlog Architecture Agent — are not core in the
user-stories pipeline they came from either, so this is not the core rule being
applied correctly to inherited steps.

The consequence is that an author composing a workflow from scratch can add
agents and then cannot take any of them out. The only recovery is to reload and
start again, losing everything else configured on the canvas.

`disabled:opacity-0` also means the control is invisible rather than greyed, so
there is nothing on screen to explain why the node cannot be removed — the
`title` only appears on hover over an element the user cannot see.

The guard itself is right where it applies: on `/workflows/ppt/canvas` every
step genuinely is core, and refusing to remove one is correct.

**Fix sketch:** the lock is reading core-ness from the wrong place for
library-added steps. It should follow the same source the `Core` badge does —
they disagree today, and the badge is the one telling the truth.

---

## D-31 — Granting a second admin locks EVERY admin out of the product

**Severity:** critical. **Found by:** `S-19-07`, phase 2 — the hard way.

The admin dashboard's "Grant admin access to \<email\>" happily promotes a second
user. The auth layer then refuses every local-admin credential:

```json
{"auth_event":"break_glass_invariant_violated",
 "reason":"unexpected_local_admin_count","local_admin_count":2}
```

> Rejected a local-admin credential: expected exactly 1 local admin
> (break-glass invariant, plan section 5.6) but found 2.

`resolve_principal` returns `None`, and `_decode_and_load_user` turns that into
a flat `401 {"detail":"Invalid token"}`. So:

- `POST /api/auth/login` still answers **200** with a perfectly valid token.
- Every authenticated request with that token answers **401**.
- The client's 401 ladder refreshes once, fails, and redirects to
  `/login?expired=true`.

The user is told their **session expired**. It did not. There is no session that
would work, for any admin, until the second admin row is removed — and removing
it needs the admin dashboard, which no admin can now reach. The only way back is
a direct database write:

```sql
update users set is_admin = false where email = '<the second admin>';
```

**Two independent problems, and both matter:**

1. The dashboard offers an action that violates an invariant the auth layer
   enforces. Either the grant should be refused with an explanation, or the
   invariant should tolerate more than one local admin.
2. The failure is reported as an expired session. Nothing anywhere — not the
   toast, not the login screen, not the API response — mentions the invariant.
   The log line exists, but only server-side.

**How this was found:** `S-19-07` granted admin to `qa-pro` to assert the
success toast. The grant succeeded; the very next request 401'd; the test's own
cleanup could not run because it needed the session the grant had just
destroyed. The whole suite stopped authenticating and stayed that way until the
row was restored by hand. Two hours were spent looking for a port collision that
was real but unrelated.

`S-19-07` now skips the grant and revoke rows for exactly this reason. **No
offline test may create a second admin.**

**Fix sketch:** refuse the grant in the API with a message naming the invariant,
and disable the control in the dashboard when a local admin already exists.

---

## D-32 — A refused admin action is applied optimistically and silently

**Severity:** medium. **Found by:** `S-19-08`, phase 2.

An admin cannot change their own tier — the backend refuses it, and S-11-08
pins that. The dashboard does not notice:

- the row immediately shows the tier that was refused (`BASIC` on an
  `ENTERPRISE` admin),
- the stat tiles one line above still count the real tier, so the screen
  contradicts itself,
- no error toast appears, and nothing else on the page reports the refusal.

A reload restores the truth, which is how you discover the change never
happened.

The scenario in the spec is titled "An admin failure is reported, not
swallowed". It is swallowed. `S-19-08` asserts the current behaviour and will
fail the day the error toast appears.

**Fix sketch:** await the response before updating the row, and surface the
server's message in the error toast the other admin actions already use.

---

## D-33 — Space-to-pan is invisible, and redundant

**Severity:** low, discoverability. **Found by:** `S-20-03` / `S-20-05`, phase 2.

The canvas prints "Hold Space + drag to pan" as on-screen guidance. Holding
Space changes nothing observable:

```js
getComputedStyle(canvas).cursor  // "auto", Space held or not
canvas.className                 // "flex h-full min-h-0", unchanged
```

No cursor, no class, no attribute. A user who holds Space has no confirmation
that anything happened, and a stuck pan mode — the exact failure a missed keyup
produces — is indistinguishable from a working canvas until they try to drag
something.

Dragging empty canvas already pans it, with or without Space. The Space binding
only changes what a drag STARTING ON A NODE does: pan instead of move. That is
the single behaviour it adds, and it is the one the hint does not describe.

`S-20-03` and `S-20-05` therefore assert the relative motion of the nodes rather
than any mode indicator — there is none to assert on.

**Fix sketch:** `cursor: grab` while Space is held, `grabbing` while dragging.
One line, and it makes both the feature and its failure visible.
