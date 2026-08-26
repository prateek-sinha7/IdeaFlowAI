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

**Severity:** medium.

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
