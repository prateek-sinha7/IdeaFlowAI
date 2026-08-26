# Defects observed during the phase-1 capture sweep

Found by walking the product, not by looking for bugs. Each is reproducible from
a cold URL. **Nothing here has been fixed** — phase 1 records, it does not repair.
Each has a `@defect` scenario in `screens/` written to today's behaviour so
phase 2 has a baseline that will go red when the fix lands.

---

## D-01 — `/create/app` launches the wrong workflow

**Severity:** high — a user who follows this URL runs a pipeline they did not pick.

`/create/app` and `/create/user-stories` render the **same screen**. Both show
`GENERATE PRODUCT REQUIREMENTS` / "Provide the brief" / `Advanced 7 agents`.
`/create/app` should launch `app_builder` ("Build an end-to-end application",
~1 agent in the catalog).

**Root cause** — `frontend/src/app/[...view]/page.tsx:307`:

```ts
function initialWorkflowTypeFor(parsed: ParsedView): string | undefined {
  return parsed.screen === 'create-workflow' ? parsed.pipelineType : undefined;
}
```

`initialMainViewFor` maps `create-app` and `create-user-stories` to `"input"`
(line 123-125), which is right — but `initialWorkflowTypeFor` returns a type only
for `create-workflow`. Both named screens therefore reach the launch panel with
**no workflow type**, and the panel falls back to its default, `user_stories`.

The open-ended `create-workflow` branch is unaffected and works correctly:
`/create/ex_A2_branch` renders `BRANCH BY LANGUAGE` with `Advanced 5 agents`.
So the generic path is right and the two hand-written special cases are the
broken ones — the opposite of the usual shape.

**Fix sketch:** extend the function to map `create-app` → `app_builder` and
`create-user-stories` → `user_stories`, or delete both special cases and let them
fall through to `create-workflow`.

**Scenario:** `03-launch-panels.feature.md` → *Cold-loading /create/app shows the
user-stories panel*.

---

## D-02 — `/runs/{id}/workspace` works but is not in the routing contract

**Severity:** medium — invisible today, breaks the moment anyone trusts `routes.ts`.

The run detail surface has **five** tabs: Preview, Steps, Files, Workspace, Audit.
Clicking Workspace pushes `/runs/{id}/workspace`, and a cold load of that URL
renders the workspace file list correctly with the tab selected.

But `routes.ts` has **no `runWorkspace` builder**, and `parseViewPath`'s `runs`
branch handles only `steps`, `files`, `audit`, `stream`, `versions` and
`preview/full` before falling through to `{ screen: 'unknown' }`. So the parser
classifies a working URL as unknown.

It renders anyway because `DashboardLayout` owns the tab state separately from the
parser. ADR-0018 says every URL in the app is built and parsed by `routes.ts`;
this one is neither.

**Why it matters:** anything that reasons about the route surface through
`parseViewPath` — analytics `screenLabel`, a future guard, a redirect — will treat
a real screen as a 404. It is also the exact class of gap that produced BUG-030.

**Fix sketch:** add `runWorkspace: (id) => `/runs/${id}/workspace``, a
`workspace` case in the parser, a `run-workspace` member of `ParsedView`, and
`execution` in `initialMainViewFor`.

**Scenario:** `07-run-detail.feature.md` → *The Workspace tab has a URL the router
does not know*.

---

## D-03 — `?expired=1` silently does nothing

**Severity:** low.

`/login?expired=true` renders the banner "Your session expired. Please sign in
again." `/login?expired=1` renders **no banner** — the page looks like a normal
sign-in.

The check is an exact string comparison against `"true"`. `routes.login({expired:
true})` always produces `expired=true`, so every in-app path is fine; only a
hand-written or externally-generated link with `=1` degrades. It fails silently,
which is the part worth recording: the user is told nothing about why they were
signed out.

**Scenario:** `01-auth.feature.md` → *An expired-session link with a non-"true"
value shows no banner*.

---

## D-04 — Test fixtures ship in the real catalog

**Severity:** product decision, not a code defect. Already filed as **ISS-187**.

Seven spec-014 conditional-gate fixtures declare `user_launchable: true` and are
entitled to the `enterprise` tier on both sides
(`backend/app/core/entitlements.py:47-53`, `frontend/src/lib/entitlements.ts:63-69`),
so they appear on the home catalog as ordinary launchable workflows:

- Retry Until It Passes (`ex_A1_loop`)
- Branch by Language (`ex_A2_branch`)
- Spanish Greeter (`ex_A3_b_spanish`)
- Dutch Greeter (`ex_A3_c_dutch`)
- Hand Off to Another Workflow (`ex_A3_divert`)
- Ask a Human, Then Hand Off (`ex_A4_human_divert`)
- Ask a Human, Then Decide (`ex_A4_human_gate`)

Their catalog descriptions are written for engineers, not users — *"Smallest
possible example of a conditional gate looping back to an earlier step"*, and
*"The plain workflow ex_A3_divert diverts into for the 'spanish' outcome"*, which
names an internal manifest id in user-facing copy.

They also appear as **library filter categories with a count of 0** — Retry Loop 0,
Language Branch 0, Spanish Greeter 0, Dutch Greeter 0, Workflow Handoff 0, Human
Handoff 0, Human Gate 0 — seven dead filters out of fourteen on the Library page.

The specs describe this as current behaviour and do not assert it is correct.

---

## D-05 — A saved override's agent count disagrees with its launch panel

**Severity:** unconfirmed — needs phase-2 verification before it is called a bug.

The saved workflow *My presentation* (base `ppt`) reports **4 agents** on
`/workflows` and on `/workflows/{id}` (report-generator, ppt-brief-analyst,
ppt-composer, ppt-validator). Opening `/workflows/{id}/run` renders the ppt launch
panel showing **`Advanced 3 agents`** — the base manifest's count, not the
override's.

If the launch then runs the override's 4 steps, the panel is merely mislabelled.
If it runs the base's 3, the override is being ignored at launch, which would be
serious. **The capture sweep did not launch a run, so which one happens is
unknown.** Phase 2 must settle it.

Related: `/workflows/{id}/edit` on that same ppt-based override renders the header
`CUSTOM · COMPOSER`, not `PRESENTATION`. That part is consistent with ISS-183's
note that `base_pipeline_type` is hardcoded to `"custom"` on the composer.

**Scenario:** `05-saved-workflows.feature.md` → *A saved override's run panel
reports the base agent count* (tagged `@unverified`).
