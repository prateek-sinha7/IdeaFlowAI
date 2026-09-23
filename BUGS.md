# BUGS

The detail for every bug. One `##` section each.

**`LEDGER.md` is the queue** — every bug here has exactly one row there, and that row carries
its status. This file never carries a status; look it up in the ledger.

**This file is what the reporter wrote, and it stays that way.** The automated line does not
write back into it — its findings (root cause, blast radius, the fix) become knowledge cards,
linked from the `Cards` column in `LEDGER.md`.

**Append only.** Add new bugs at the bottom. Never delete or rewrite someone else's section.

See **`HOW_TO_LOG_BUGS.md`** before adding anything.

---

<!-- ── Bugs are appended below this line, newest last ─────────────────────── -->

<a id="qa-ex-001"></a>

## QA-EX-001 — Picking an older version changes the files but leaves the newest run's steps on screen

> **This is the worked example** — a real bug, reported by hand, now fixed and closed. It is
> kept here to show the shape. This is the whole entry: nothing gets appended to it later. What
> the line worked out lives in the cards listed against this bug in `LEDGER.md`. Leave this
> entry in place.

- **Page:** Run detail — version menu
- **Route:** /runs/{id}
- **Severity:** High
- **Found by:** Bilal
- **Found at:** 2026-09-15 12:36
- **User:** qa-admin@flowinqa.com

### Reproduction

1. Sign in as `qa-admin@flowinqa.com`
2. Go to `/runs` and open a completed run that has at least two versions — a run plus a
   revision of it
3. Open the version menu at the top of the run and pick **v1**
4. Look at the Steps tab underneath

### Expected

The steps, the agent list and the agent outputs all switch to the ones that produced v1 —
matching the files now on screen.

### Actual

The files switch to v1, but the steps, the agent list and the agent-output cards all still show
the newest run. It reads as "these steps produced these files", which is not true.

Opening `/runs/{id}/versions/1` directly in the address bar shows the correct steps, so it is
only the menu that is wrong.

### Browser Signals

```
Console: clean
Network: the workspace re-reads at ref=v1, but nothing re-fetches the run behind the steps
```

<a id="qa-ps-001"></a>

## QA-PS-001 — Stop and rerun skips saving the interrupted build task's agent file

- **Page:** Run detail — Files / .agents folder
- **Route:** /runs/{id}
- **Severity:** High
- **Found by:** PS
- **Found at:** 2026-09-17
- **User:** qa-admin@flowinqa.com

### Reproduction

1. Sign in as `qa-admin@flowinqa.com`
2. Go to `/runs` and start a new prototype pipeline run
3. Wait until the **Build agent, Task 2** (`04-prototype-build-t2.md`) is actively running
4. Click **Stop** to cancel the pipeline mid-run
5. Click **Run** (or rerun) to start the pipeline again from the beginning
6. Wait for the pipeline to complete
7. Open the run's `.agents` folder in the run detail view

### Expected

All build task agent files are present in the `.agents` folder, including `04-prototype-build-t2.md`, because the pipeline completed a full run.

### Actual

`04-prototype-build-t2.md` is missing. The folder jumps from `04-prototype-build-t1.md` directly to `04-prototype-build-t3.md`. The file for the task that was running at the point of the stop is never saved, even though the pipeline completed successfully on the rerun.

### Browser Signals

```
Console: clean
Network: not checked
```

<a id="qa-ps-002"></a>

## QA-PS-002 — Notification panel shows 0 of N agents and 0% progress for actively running pipelines

- **Page:** Notification panel (bell icon, top nav)
- **Route:** Any (panel is global)
- **Severity:** High
- **Found by:** PS
- **Found at:** 2026-09-17
- **User:** qa-admin@flowinqa.com

### Reproduction

1. Sign in as `qa-admin@flowinqa.com`
2. Start one or more pipeline runs (e.g. a prototype run) and wait for them to begin executing agents
3. Click the **bell icon** in the top navigation bar to open the Notifications panel
4. Observe the agent progress for any run that has been actively running for several minutes

### Expected

Each in-progress run in the notification panel shows the correct number of completed agents out of the total (e.g. "2 of 5 agents") and a matching progress percentage (e.g. 40%), updating as agents complete.

### Actual

Every actively running pipeline shows **"0 of N agents"** and **0%** regardless of how long it has been running or how many agents have already completed. The progress bar stays empty. This affects all concurrent runs simultaneously — in the screenshot three separate runs (3, 6, and 5 agents respectively) all show 0% after 3–4 minutes of running.

### Browser Signals

```
Console: not checked
Network: not checked
```

<a id="qa-ps-003"></a>

## QA-PS-003 — Concierge chat shows identical "Clarifications answered" for every round instead of a numbered message per round

- **Page:** Concierge chat (run detail, chat lane)
- **Route:** /runs/{id}
- **Severity:** Medium
- **Found by:** PS
- **Found at:** 2026-09-17
- **User:** qa-admin@flowinqa.com

### Reproduction

1. Sign in as `qa-admin@flowinqa.com`
2. Start a pipeline run that triggers **two rounds** of clarification questions (e.g. a User Stories run such as "github dashboard user story")
3. Answer the first round of clarification questions and submit
4. Observe the confirmation message that appears in the concierge chat
5. Answer the second round of clarification questions and submit
6. Observe the confirmation message that appears in the concierge chat

### Expected

After answering round 1, the chat shows: **"Clarifications round 1 answered"**
After answering round 2, the chat shows: **"Clarifications round 2 answered"**

Each message is distinct so the user can tell which round they completed.

### Actual

Both confirmation messages read **"Clarifications answered"** with no round number. The two messages are visually identical, making it impossible to distinguish round 1 from round 2 in the chat history.

### Browser Signals

```
Console: not checked
Network: not checked
```

<a id="qa-ps-004"></a>

## QA-PS-004 — Concierge chat review gate approval messages show no agent name, making all approvals look identical

- **Page:** Concierge chat (run detail, chat lane)
- **Route:** /runs/{id}
- **Severity:** High
- **Found by:** PS
- **Found at:** 2026-09-17
- **User:** qa-admin@flowinqa.com

### Reproduction

1. Sign in as `qa-admin@flowinqa.com`
2. Start a pipeline run that has **multiple review gates** (e.g. a User Stories run — "github dashboard user story" has at least 3 review gates)
3. Each time a review gate appears, approve it and allow the pipeline to continue
4. Once the run reaches **Done**, scroll back through the concierge chat history and read the approval confirmation messages

### Expected

Each approval message identifies the agent whose gate was approved, for example:
- **"Domain Discovery Agent review approved — build continues"**
- **"Story Mapping Agent review approved — build continues"**
- **"Validation Agent review approved — build continues"**

This lets the user see at a glance which agents they reviewed and in what order.

### Actual

Every approval message reads **"Review approved — build continues"** with no agent name. When a run has multiple review gates (three are visible in the screenshot) all messages are word-for-word identical, so the user cannot tell which gate each message corresponds to.

### Browser Signals

```
Console: not checked
Network: not checked
```

<a id="qa-ps-005"></a>

## QA-PS-005 — Clicking a pipeline entry in the "N Running" header dropdown sometimes does nothing

- **Page:** Global header — "N Running" active pipelines dropdown
- **Route:** Any (header is global)
- **Severity:** High
- **Found by:** PS
- **Found at:** 2026-09-17
- **User:** qa-admin@flowinqa.com

### Reproduction

1. Sign in as `qa-admin@flowinqa.com`
2. Start two or more pipeline runs so the header badge reads **"2 Running"** (or more)
3. Click the **"2 Running"** badge in the top navigation bar to open the active pipelines dropdown
4. Click on one of the pipeline entries listed in the dropdown (e.g. "Pitch an idea — lateral thinking" or "Build an interactive prototype — Github like dashboard")
5. Observe whether the app navigates to that run's detail page

### Expected

Clicking a pipeline entry in the dropdown navigates to that run's detail page every time, without fail.

### Actual

Sometimes clicking a pipeline entry does nothing — the dropdown may close but the app stays on the current page and does not navigate to the run. The behaviour is intermittent; the same entry may work on a subsequent click.

### Browser Signals

```
Console: not checked
Network: not checked
```

<a id="qa-ps-006"></a>

## QA-PS-006 — "Review required" messages in concierge chat show no agent name, making multiple review prompts indistinguishable

- **Page:** Concierge chat (run detail, chat lane)
- **Route:** /runs/{id}
- **Severity:** High
- **Found by:** PS
- **Found at:** 2026-09-17
- **User:** qa-admin@flowinqa.com

### Reproduction

1. Sign in as `qa-admin@flowinqa.com`
2. Start a pipeline run that has multiple review gates (e.g. a PPT run — "lateral thinking" triggers at least two review gates)
3. When each review gate is reached, approve it and allow the pipeline to continue
4. Once the run reaches **Done**, scroll back through the concierge chat history and read the "Review required" prompt messages

### Expected

Each review prompt identifies the agent that requires review, for example:
- **"Specify Agent review required"**
- **"Plan Agent review required"**

This lets the user know which agent's output they are being asked to review at each gate.

### Actual

Every review prompt reads **"Review required"** with no agent name. When a run has multiple review gates (two are visible in the screenshot) all messages are word-for-word identical. The user cannot tell which agent triggered each review request.

### Notes

This is the prompt-side counterpart to QA-PS-004, which covers the same missing agent name on the approval confirmation message. Both the request ("Review required") and the confirmation ("Review approved — build continues") are missing the agent name.

### Browser Signals

```
Console: not checked
Network: not checked
```

<a id="qa-ps-007"></a>

## QA-PS-007 — PPT workflow final output file is always named "presentation.html" regardless of the run topic

- **Page:** Run detail — Files tab
- **Route:** /runs/{id}/files (or /runs/{id} with Files tab selected)
- **Severity:** Medium
- **Found by:** PS
- **Found at:** 2026-09-17
- **User:** qa-admin@flowinqa.com

### Reproduction

1. Sign in as `qa-admin@flowinqa.com`
2. Go to `/runs` and open any completed PPT pipeline run (e.g. the "lateral thinking" run)
3. Click the **Files** tab
4. Look at the filename of the **Final Output** file shown at the top of the Files tab
5. Click **Download** on that file and check the downloaded filename

### Expected

The final output file is named after the run topic, for example:
- `lateral-thinking-presentation.html` for a "lateral thinking" run
- `github-dashboard-presentation.html` for a "github dashboard" run

Or at minimum a name that relates to the content of the generated presentation, so the user can identify the file after downloading.

### Actual

The final output file is always named **`presentation.html`** regardless of the run topic. Every PPT run produces a file with the same generic name, making it impossible to distinguish files from different runs once downloaded.

### Browser Signals

```
Console: not checked
Network: not checked
```

<a id="qa-ps-008"></a>

## QA-PS-008 — Version dropdown shows inflated/incorrect version list and preview fails for all non-live versions

- **Page:** Run detail — version dropdown (top of run detail view)
- **Route:** /runs/{id}
- **Severity:** High
- **Found by:** PS
- **Found at:** 2026-09-17
- **User:** qa-admin@flowinqa.com

### Reproduction

1. Sign in as `qa-admin@flowinqa.com`
2. Go to `/runs` and open any completed run that has exactly one revision (i.e. the run is at `v2` — a parent run plus one revision on top)
3. Click the version badge/dropdown at the top of the run detail view (shows `v2`)
4. Read the list of versions shown in the dropdown
5. Click any version other than **Latest (live)**
6. Observe the Preview panel

### Expected

- The dropdown should show only the versions that actually exist for this run — in this case two entries: the parent run (v1) and the revision (v2 / Latest)
- Selecting any listed version should load that version's preview in the Preview panel

### Actual

Two problems observed together across all workflows:

1. **Inflated version list:** The dropdown shows many more entries than the run actually has. For a run with one revision (v2), the dropdown lists: `Latest (live)`, `v0.2.0`, `v0.0.2`, `v0.0.1`, `deploy-prod-20260603-014226`, `deploy-prod-20260603-012557`. These appear to be git tags or deployment refs leaking into the version list rather than actual run versions.

2. **Preview stuck on loading for non-live versions:** Clicking any version other than `Latest (live)` causes the Preview panel to show a loading state indefinitely. The parent run's preview never loads regardless of which non-live version is selected.

Both problems are seen across every workflow, not just Prototype Revision.

### Browser Signals

```
Console: not checked
Network: not checked
```

<a id="qa-ps-009"></a>

## QA-PS-009 — Analytics model details card shows a "Thinking" row for Sonnet 5 which does not support extended thinking

- **Page:** Analytics — Model Details panel
- **Route:** /analytics
- **Severity:** Medium
- **Found by:** PS
- **Found at:** 2026-09-17
- **User:** qa-admin@flowinqa.com

### Reproduction

1. Sign in as `qa-admin@flowinqa.com`
2. Go to `/analytics` (or `/analytics?range=7d`)
3. Scroll to the **Model Details** panel on the right side of the page
4. Expand or locate the **Sonnet 5** model card
5. Read the rows listed under Sonnet 5

### Expected

The Sonnet 5 model details card shows only the rows that apply to Sonnet 5: Tier, Input rate, Output rate, Cache read rate, Cache write rate, and Context window. No "Thinking" row is shown because Sonnet 5 does not support extended thinking.

### Actual

The Sonnet 5 model details card includes an extra row: **Thinking: Adaptive (effort: max)**. Sonnet 5 does not support extended thinking, so this row is incorrect and should not be displayed. The Haiku 4.5 card directly above it does not show a Thinking row, which is correct.

### Browser Signals

```
Console: not checked
Network: not checked
```

<a id="qa-ps-010"></a>

## QA-PS-010 — PPT wizard shows templates tagged "Uses design system" that should be removed

- **Page:** PPT creation wizard — template selection
- **Route:** /create/ppt
- **Severity:** High
- **Found by:** PS
- **Found at:** 2026-09-17
- **User:** qa-admin@flowinqa.com

### Reproduction

1. Sign in as `qa-admin@flowinqa.com`
2. Go to `/create/ppt`
3. Browse the available PPT templates on the wizard page
4. Click on the **"Weekly Team Update"** template (or any other template tagged "Uses design system") to open its preview modal
5. Look at the tags shown at the bottom left of the modal

### Expected

Templates that require a design system input are not shown in the PPT wizard at all. The template list only contains templates the pipeline can fully generate without additional design system assets.

### Actual

Templates tagged **"Uses design system"** (e.g. "Weekly Team Update") are visible and selectable in the wizard. The tag is shown as a pill label in the template preview modal but the app has no mechanism to provide or upload a design system. Selecting such a template would lead to a pipeline that cannot complete correctly.

### Notes

At least one such template is confirmed: **"Weekly Team Update"** at `/create/ppt`. There may be others — all templates carrying the "Uses design system" tag should be audited and removed from the wizard.

### Browser Signals

```
Console: not checked
Network: not checked
```

<a id="qa-ps-011"></a>

## QA-PS-011 — Uncaught TypeError "Cannot read properties of undefined (reading 'startTime')" thrown from AgentsPopup when clicking Pitch an idea or navigating back from /create/ppt

- **Page:** Home / feature card navigation; PPT creation wizard back navigation
- **Route:** / (home) and /create/ppt (on back navigation)
- **Severity:** High
- **Found by:** PS
- **Found at:** 2026-09-17
- **User:** qa-admin@flowinqa.com

### Reproduction

**Trigger 1 — feature card click:**
1. Sign in as `qa-admin@flowinqa.com`
2. Go to the home page (`/`)
3. Click the **"Pitch an idea"** feature card
4. Open browser DevTools Console and observe errors

**Trigger 2 — back navigation from PPT wizard:**
1. Sign in as `qa-admin@flowinqa.com`
2. Go to `/create/ppt`
3. Click the browser back button or the in-app back link to return to the previous page
4. Open browser DevTools Console and observe errors

### Expected

No JavaScript errors are thrown during either navigation. The page renders correctly.

### Actual

Both triggers produce an uncaught TypeError in the browser console:

```
Uncaught TypeError: Cannot read properties of undefined (reading 'startTime')
  at et.reportAllChanges (<anonymous>:2:19429)
  at <anonymous>:2:13070
  at <anonymous>:2:331
  at d (<anonymous>:2:6141)
  at <anonymous>:2:6326
  at <anonymous>:2:2895
  at n.timeout (<anonymous>:2:5652)
```

The error originates in the `AgentsPopup` component (logged in console as `[wf] 5. AgentsPopup mount undefined • {seededSelections: {…}, agents: Array(3)}`), which appears to be trying to read `startTime` from an agent object that is `undefined` at mount time.

### Browser Signals

```
Console: Uncaught TypeError: Cannot read properties of undefined (reading 'startTime')
         [wf] 5. AgentsPopup mount undefined • {seededSelections: {…}, agents: Array(3)}
         [Fast Refresh] rebuilding
Network: not checked
```

<a id="qa-ps-012"></a>

## QA-PS-012 — Prototype template wizard shows "No template" instead of "Default Template" for the blank canvas option

- **Page:** Prototype creation wizard — template selection step
- **Route:** /create/prototype
- **Severity:** Low
- **Found by:** PS
- **Found at:** 2026-09-17
- **User:** qa-admin@flowinqa.com

### Reproduction

1. Sign in as `qa-admin@flowinqa.com`
2. Go to `/create/prototype`
3. On the **"Configure your prototype"** step, look at the first card in the template grid (top-left, currently selected by default)

### Expected

The first card is labelled **"Default Template"** with the subtitle "BLANK CANVAS", making it clear that selecting it runs the pipeline with a default blank starting point.

### Actual

The first card is labelled **"No template"** with the subtitle "BLANK CANVAS". The label "No template" is misleading — it implies that no template is applied at all, which is confusing when it is the pre-selected default option shown alongside 48 named templates.

### Browser Signals

```
Console: not checked
Network: not checked
```

<a id="qa-ps-013"></a>

## QA-PS-013 — Upload custom template "From URL" fails for some valid public URLs with "Could not reach that URL"

- **Page:** Prototype and PPT creation wizard — Upload custom template modal, "From URL" tab
- **Route:** /create/prototype and /create/ppt
- **Severity:** High
- **Found by:** PS
- **Found at:** 2026-09-17
- **User:** qa-admin@flowinqa.com

### Reproduction

1. Sign in as `qa-admin@flowinqa.com`
2. Go to `/create/prototype` (or `/create/ppt`)
3. Click **Upload custom** in the top-right of the template grid
4. In the **Upload custom template** modal, select the **From URL** tab
5. Enter `https://hexaware.com/` in the URL field
6. Click **Fetch**

### Expected

The app successfully fetches the page at the given URL and uses it as a custom template starting point. The user can then proceed with **Use this template**.

### Actual

The fetch fails and the error message **"Could not reach that URL. Check the address and try again."** is shown below the input field. The network tab shows the backend returning:

```
{"detail":"Could not reach that URL. Check the address and try again."}
```

The URL `https://hexaware.com/` is a valid, publicly reachable website, so the failure is on the backend fetcher side. The issue affects at least this URL and likely others — the full set of failing URLs is not yet known.

### Notes

This feature exists on both `/create/prototype` and `/create/ppt`. Both are affected.

### Browser Signals

```
Console: 8 errors, 2 warnings visible in DevTools
Network: fetch url?url=https%3A%2F%2F... → error response
         {"detail":"Could not reach that URL. Check the address and try again."}
```

<a id="qa-ps-014"></a>

## QA-PS-014 — Run detail page shows blank "Output will appear here" with no loading indicator while data is fetching

- **Page:** Run detail — Preview tab
- **Route:** /runs/{id}
- **Severity:** Medium
- **Found by:** PS
- **Found at:** 2026-09-17
- **User:** qa-admin@flowinqa.com

### Reproduction

1. Sign in as `qa-admin@flowinqa.com`
2. Go to `/runs` (My Workflows / run history list)
3. Click on any completed workflow run from the list
4. Observe the run detail page immediately after navigation, before the data finishes loading

### Expected

While the run data is being fetched, the page shows a loading state — for example a skeleton layout, a spinner, or a progress indicator — so the user knows content is on the way. Once loaded, the full run detail replaces the skeleton.

### Actual

The page navigates to `/runs/{id}` and immediately renders a blank Preview panel with the placeholder text **"Output will appear here"** and an empty left panel (no chat messages, no run metadata, no token count). After several seconds the full run detail loads all at once. There is no visual indication that loading is in progress during the wait — the blank state looks like an empty or failed run rather than a loading one.

### Notes

Both screenshots show the same run (`/runs/bc8da167-b496-419c-8173-71f76a11ad7a`): first the blank state, then the fully loaded state. The delay is noticeable on every run opened from the history list.

### Browser Signals

```
Console: 9 issues visible in DevTools during blank state
Network: not checked
```

<a id="qa-ps-015"></a>

## QA-PS-015 — "Chain" option on run history list opens a legacy run UI instead of the current run detail page

- **Page:** Run history list — row context menu
- **Route:** /runs (list) → opens legacy /runs view
- **Severity:** High
- **Found by:** PS
- **Found at:** 2026-09-17
- **User:** qa-admin@flowinqa.com

### Reproduction

1. Sign in as `qa-admin@flowinqa.com`
2. Go to `/runs` (My Workflows / run history list)
3. Click the **⋯** (more options) menu on any completed run row
4. Click **Chain**
5. Observe the page that opens

### Expected

The Chain option either opens the current run detail page (`/runs/{id}`) with the concierge chat lane and the standard tab set (Preview, Steps, Files, Workspace, Audit), or is removed if it is no longer a supported workflow.

### Actual

The Chain option opens a legacy run UI at `/runs` (the URL does not change to `/runs/{id}`). The legacy page has a completely different layout:
- Left panel shows **Agents** and **Timeline** tabs, no concierge chat
- Top tab set is **Preview, Files, Thinking, Audit** (missing Steps and Workspace)
- Has a **Full Screen** button not present in the current UI
- Shows **Suggested Next Steps** panel at the bottom left (Revise Presentation, App Builder, Prototype, User Stories)

This is a retired UI that should not be reachable. The current app uses `/runs/{id}` with a concierge chat lane and run-scoped versioning.

### Browser Signals

```
Console: not checked
Network: not checked
```

<a id="qa-ps-016"></a>

## QA-PS-016 — Chain-initiated revision creates a new top-level run entry instead of adding a version (v2) to the parent run

- **Page:** Run history list — Chain flow
- **Route:** /runs (list)
- **Severity:** High
- **Found by:** PS
- **Found at:** 2026-09-17
- **User:** qa-admin@flowinqa.com

### Reproduction

1. Sign in as `qa-admin@flowinqa.com`
2. Go to `/runs` and locate the **"lateral thinking"** Presentation run
3. Click the **⋯** menu on that run and click **Chain**
4. In the Chain UI, ask for a revision — e.g. "add author Prateek and company name Hexaware on title page"
5. Wait for the revision to complete
6. Return to `/runs` and observe the run history list

### Expected

The revision appears as **v2** on the existing "lateral thinking" run — the same run ID, same entry in the history list, with the version badge updated. The concierge chat on that run retains all prior messages plus the new revision exchange. No new top-level entry is created.

### Actual

A brand new top-level run entry appears at the top of the history list, titled **"add author Prateek and company name Hexaware on title page"** (the revision prompt text becomes the run title). It is shown as `Presentation (Revised) · 1 agent` — a completely separate run with its own ID. The original "lateral thinking" run is unaffected and remains as a standalone entry. The revision history and concierge chat context from the original run are not carried over.

### Notes

The correct revision behaviour is demonstrated by the Prototype Revision workflow where revisions add a `v2`, `v3` etc. to the parent run at the same run ID with the concierge chat intact. The Chain flow bypasses this and creates orphaned revision runs instead.

This bug is related to QA-PS-015 — the Chain option opens a legacy UI (QA-PS-015) which is likely why the revision is handled incorrectly rather than going through the current revision flow.

### Browser Signals

```
Console: not checked
Network: not checked
```

<a id="qa-ps-017"></a>

## QA-PS-017 — "Chain" option in run history context menu is enabled for Running and Cancelled runs, should only be active when Done

- **Page:** Run history list — row context menu
- **Route:** /runs
- **Severity:** High
- **Found by:** PS
- **Found at:** 2026-09-17
- **User:** qa-admin@flowinqa.com

### Reproduction

1. Sign in as `qa-admin@flowinqa.com`
2. Go to `/runs` and wait for any run to be in **Running** state (or cancel a run to put it in **Cancelled** state)
3. Click the **⋯** (more options) menu on the running or cancelled run row
4. Observe the **Chain** option in the dropdown

### Expected

The **Chain** option is disabled (greyed out, non-interactive) when the run status is **Running** or **Cancelled**. It is only enabled and clickable when the run status is **Done**. A tooltip explaining why it is disabled ("Available when run is complete") would be ideal but is not required.

### Actual

The **Chain** option is fully enabled and clickable regardless of run status. In the screenshot, the "Prototype" run is actively **Running** (status badge visible) yet the ⋯ menu shows Chain as an active, clickable option. Clicking it on a running or cancelled run leads to undefined behaviour.

### Notes

This is related to QA-PS-015 and QA-PS-016 — the Chain flow is already broken in other ways, but regardless of those fixes, the guard condition on run status must also be enforced so Chain is never accessible on incomplete runs.

### Browser Signals

```
Console: not checked
Network: not checked
```

<a id="qa-ps-018"></a>

## QA-PS-018 — Chain flow leaks raw sentinel string "=== EXISTING PRESENTATION CODE ===" into run title, topic display, and Steps starting point

- **Page:** Run history list; Run detail — left panel topic; Run detail — Steps tab
- **Route:** /runs (list) and /runs/{id}
- **Severity:** High
- **Found by:** PS
- **Found at:** 2026-09-17
- **User:** qa-admin@flowinqa.com

### Reproduction

1. Sign in as `qa-admin@flowinqa.com`
2. Go to `/runs` and locate the **"lateral thinking"** Presentation run (Done)
3. Click the **⋯** menu on that run and click **Chain**
4. In the Chain UI, select **Prototype** as the target workflow type
5. Complete any clarification steps and wait for the chained Prototype run to finish
6. Return to `/runs` and observe the new run entry in the history list
7. Click on that run to open the run detail page
8. Read the topic shown in the left panel header
9. Click the **Steps** tab and read the **Starting point** card

### Expected

- **Run history list:** The chained run appears with a meaningful title such as "lateral thinking → Prototype" or the user's brief for the new run — not the raw workflow type name "Prototype" alone
- **Run detail topic:** The left panel shows a human-readable topic, not an internal sentinel string
- **Steps tab — Starting point:** The starting point card shows a label like "Chained from: lateral thinking (Presentation)" with the source run linked — not the raw injected content block

### Actual

Three surfaces all show the same leaked sentinel string:

1. **Run history list:** The chained run is titled **"Prototype"** — just the workflow type, no topic or source context
2. **Run detail — left panel topic:** Displays **`=== EXISTING PRESENTATION CODE ===`** as the run topic/title
3. **Steps tab — Starting point:** The Starting point card shows **`=== EXISTING PRESENTATION CODE ===`** as the prompt brief, followed by the full raw HTML of the source presentation (collapsed behind "Show more")

The Chain flow injects the source run's output into the child pipeline's prompt using a sentinel delimiter (`=== EXISTING PRESENTATION CODE ===`). This internal marker is being stored as the run's topic/title and rendered verbatim in the UI wherever the topic or starting brief is displayed, instead of being stripped or replaced with a human-readable reference.

### Notes

This is related to QA-PS-015, QA-PS-016, and QA-PS-017 — the entire Chain feature has multiple issues. The sentinel leak is a separate data/rendering problem from the legacy UI (QA-PS-015) and the orphaned run creation (QA-PS-016), and must be fixed independently.

### Browser Signals

```
Console: not checked
Network: not checked
```

<a id="qa-sg-001"></a>

## QA-SG-001 — Notification header shows 0/5 but pipeline detail shows 0/0, progress counts are inconsistent

- **Page:** Global header notification badge + run detail pipeline panel
- **Route:** /runs/{id}
- **Severity:** High
- **Found by:** SG
- **Found at:** 2026-09-17
- **User:** qa-admin@flowinqa.com

### Reproduction

1. Sign in as `qa-admin@flowinqa.com`
2. Start a pipeline run (e.g. a prototype run with 5 agents)
3. Wait for the pipeline to begin executing
4. Click the **bell icon** in the top navigation bar to open the Notifications panel
5. Observe the progress badge shown on the notification card (e.g. it reads **"0/5"**)
6. Click on the notification or navigate to the run detail page
7. Observe the "Pipeline running" section header on the run detail page

### Expected

Both the notification panel and the run detail "Pipeline running" header show consistent progress counts. If the notification shows **"0/5 agents completed"**, the run detail should also show **"0/5"** or equivalent — not a different count.

### Actual

The notification panel shows **"0/5"** (implying 5 total agents), but the "Pipeline running" section header on the run detail page shows **"0/0"** (implying 0 total agents or an unknown total). The two UI surfaces display conflicting progress information, suggesting the pipeline total/count is not being propagated consistently between the notification subsystem and the run detail view.

### Browser Signals

```
Console: not checked
Network: not checked
```

<a id="qa-sg-002"></a>

## QA-SG-002 — Run Workflow button does not disable after clicking, remains clickable and can trigger multiple runs

- **Page:** Workflow launch / run creation page
- **Route:** /create/{workflow_type} or similar
- **Severity:** High
- **Found by:** SG
- **Found at:** 2026-09-17
- **User:** qa-admin@flowinqa.com

### Reproduction

1. Sign in as `qa-admin@flowinqa.com`
2. Navigate to a workflow creation/launch page (e.g. `/create/prototype` or similar)
3. Fill in any required fields (brief, selections, etc.)
4. Click the **Run Workflow** button
5. Observe the button state immediately after clicking

### Expected

The **Run Workflow** button should disable (become grayed out, lose hover effects, and become unclickable) while the workflow is being submitted and the run is starting. The button should remain disabled until the page navigates away or the submission completes.

### Actual

After clicking **Run Workflow**, the button remains enabled and clickable. It shows no visual change — no disabled state, no loading indicator, and no feedback that a submission is in progress. The user can click the button multiple times, potentially triggering multiple simultaneous workflow runs.

### Browser Signals

```
Console: not checked
Network: not checked
```

<a id="qa-sg-003"></a>

## QA-SG-003 — Back button navigation loops between run detail and run history pages

- **Page:** Run detail page + Run history page
- **Route:** /runs and /runs/{id}
- **Severity:** High
- **Found by:** SG
- **Found at:** 2026-09-17
- **User:** qa-admin@flowinqa.com

### Reproduction

1. Sign in as `qa-admin@flowinqa.com`
2. Navigate to `/runs` (Run History page)
3. Click on a run to open the run detail page
4. On the run detail page, click the **Back** button (or **Back to history** button)
5. Observe the navigation
6. Click the **Back** button again on the Run History page
7. Observe the navigation

### Expected

Clicking the **Back** button should navigate back one page in the browser history:
- From run detail `/runs/{id}` → back to run history `/runs`
- From run history `/runs` → back to the previous page (e.g. Home, or wherever you came from before)

The back button should move backward through the navigation stack, not loop between two pages.

### Actual

Clicking the **Back** button (or **Back to history** button) on the run detail page navigates to the Run History page. However, clicking **Back** again on the Run History page navigates back to the same run detail page instead of going further back. The user gets stuck in a loop between the run detail page and the run history page and cannot navigate away.

### Browser Signals

```
Console: not checked
Network: not checked
```

<a id="qa-sg-004"></a>

## QA-SG-004 — Switching between parallel workflow runs from notification bar is unreliable, sometimes fails or is delayed

- **Page:** Global header notification badge + run detail pages
- **Route:** /runs/{id}
- **Severity:** High
- **Found by:** SG
- **Found at:** 2026-09-18
- **User:** qa-admin@flowinqa.com

### Reproduction

1. Sign in as `qa-admin@flowinqa.com`
2. Start **six parallel workflow runs** simultaneously (by launching runs and allowing them to execute concurrently)
3. Wait for all six runs to begin executing
4. Click the **bell icon** in the top navigation bar to open the Notifications panel
5. Observe the list of active runs in the notifications
6. Click on different workflow entries in the notification panel to switch between runs
7. Repeat clicking between different runs several times, observing the behavior

### Expected

Clicking on a workflow entry in the notification panel should navigate to that run's detail page consistently and immediately every time, without delay or failure.

### Actual

When six or more parallel workflows are running, switching between runs via the notification panel becomes unreliable:
- **Sometimes fails entirely** — clicking a notification entry does nothing and the app stays on the current run's page
- **Sometimes delayed** — clicking triggers a long delay (several seconds) before the app navigates to the selected run
- **Intermittent recovery** — the same entry may work on a subsequent click, suggesting a race condition or timing issue

The problem appears to be specific to high concurrency (6+ parallel runs). With fewer concurrent runs (1–3), the notification switching usually works.

### Browser Signals

```
Console: not checked
Network: not checked
```

### Notes

This issue may be related to the existing QA-PS-005 bug ("Clicking a pipeline entry in the 'N Running' header dropdown sometimes does nothing"), but this report focuses specifically on the notification panel under high concurrency with six parallel runs.




---

<a id="qa-ps-019"></a>

## QA-PS-019 — Custom workflow "Write files" toggle has no effect — write_file tool is never granted to any custom workflow agent

- **Page:** Custom workflow composer (tool grants); any custom workflow run
- **Route:** /create/custom and /runs/{id}
- **Severity:** High
- **Found by:** PS
- **Found at:** 2026-09-17
- **User:** qa-admin@flowinqa.com

### Reproduction

1. Sign in as `qa-admin@flowinqa.com`
2. Go to `/create/custom` and open the workflow composer
3. Select any agent step, open its **Tools** tab in the right panel
4. Confirm **"Write files"** toggle is ON (the default)
5. Save the workflow and run it
6. Inspect the agent's output in the Steps tab — observe whether it was able to call `write_file`
7. Alternatively: open the run's `.logs/*.jsonl` file and check whether any `tool_call` event for `write_file` appears for any agent

### Expected

When "Write files" is toggled ON for a step in the composer, the agent executing that step receives the `write_file` and `edit_file` tools. The system prompt includes a "How to deliver: Call `write_file`" instruction block. The agent can write files to the sandbox so downstream agents can `read_file` them.

### Actual

The "Write files" toggle has no effect at runtime. The agent is never offered `write_file` or `edit_file` regardless of the toggle state. The system prompt's "How to deliver" block is suppressed. Any agent that needs to write an artifact for the next agent in the pipeline cannot do so.

### Root Cause (technical)

The tool grant flows correctly from UI → `selections.tools` → `synthesize_manifest` → `WorkflowCompiler.compile(trust="user")` → `user_step.tools.write_files = True`. However, `_apply_selections` in `engine.py` patches `validators`, `gates`, `model`, `retry`, `injects`, `skills`, `strategy`, `fanout`, `task_source` onto the running step — but has **no `tools` overlay case**. The comment at line ~11972 reads *"No `tools` overlay: … `trust=user` forces `spawn_subagents` OFF anyway"* — the justification applies only to `spawn_subagents` but the absence of a `tools` case silently drops `write_files` as well. The running step keeps the base `custom/workflow.yaml` value, which declares no `tools:` block on any step, compiling to `ToolPermissions(write_files=False)`.

The cap itself is not the blocker — the untrusted cap allows `write_files=True`. The gap is purely in the overlay not being applied.

### Browser / Log Signals

```
.logs/*.jsonl: no tool_call event with tool_name "write_file" for any custom workflow agent
factory.py: "tool_permission: … granted=read_file,ls,glob,grep" (write_file absent)
agent output: model says "write_file function isn't available to this step"
```

### Files

- `backend/agents/execution_engine/engine.py` — `_apply_selections` patch loop, missing `tools` case (~line 11972)
- `backend/agents/workflows/custom/workflow.yaml` — no `write_files` declared on any step
- `backend/agents/workflows/compiler.py` — `_compile_tool_grant` line 1433: absent `tools:` → `ToolPermissions(write_files=False)`
- `backend/agents/workflows/permission_caps.py` — `PERMISSION_TOOLS`: `write_files` gates `{write_file, edit_file}`
- `frontend/src/components/workflow/AgentsPopup.tsx` — `TOOL_GRANT_LEVERS`, `effectiveToolGrants` (UI correctly saves the grant)

---

<a id="qa-sg-005"></a>

## QA-SG-005 — UI event rendering and notification ringing becomes very slow with 8 parallel workflows running

- **Page:** Global UI + Notifications panel
- **Route:** Any (affects all pages)
- **Severity:** High
- **Found by:** SG
- **Found at:** 2026-09-18
- **User:** qa-admin@flowinqa.com

### Reproduction

1. Sign in as `qa-admin@flowinqa.com`
2. Start **eight parallel workflow runs** simultaneously (by launching runs and allowing them to execute concurrently)
3. Wait for all eight runs to begin executing
4. Observe the UI behavior during the parallel execution
5. Listen for notification sounds (bell ringing) and watch for notification panel updates
6. Interact with the UI — click buttons, navigate pages, open panels

### Expected

The UI should remain responsive and fluid with 8 concurrent runs executing. Notifications should ring and update in the notification panel with minimal latency (under 1 second). All user interactions (clicks, navigation, panel opens) should respond immediately.

### Actual

With 8 parallel workflows running, the UI becomes significantly slower:
- **Notification ringing is delayed** — notification sounds and badge updates take several seconds to appear after a workflow event completes
- **Event rendering is slow** — UI updates (progress badges, status changes, new notifications) render with noticeable lag
- **General UI sluggishness** — the interface feels unresponsive during periods of high concurrent activity
- **Perception of stalled runs** — the delays make it appear as though runs are stalled or frozen, when in fact the events are just slow to render

The performance degradation appears to be a UI rendering bottleneck rather than a backend issue — the workflows themselves may be executing fine, but the notification and event delivery to the front-end UI is slow.

### Browser Signals

```
Console: not checked
Network: not checked
```

### Notes

This performance issue emerges at high concurrency (8 parallel runs). With fewer concurrent runs (1–3), the UI remains responsive. This suggests a scaling issue with how the UI handles multiple concurrent event streams or notifications.




---

<a id="qa-ps-020"></a>

## QA-PS-020 — Any custom workflow agent that must write an output file for a downstream agent cannot do so — downstream agent finds an empty sandbox

- **Page:** Custom workflow run — Steps tab, any agent that depends on an upstream file
- **Route:** /create/custom and /runs/{id}
- **Severity:** High
- **Found by:** PS
- **Found at:** 2026-09-17
- **User:** qa-admin@flowinqa.com

### Reproduction

1. Sign in as `qa-admin@flowinqa.com`
2. Build any custom workflow where agent N is expected to write a file to the sandbox that agent N+1 reads (e.g. a spec-writer agent whose output feeds a build agent, or a planner agent whose output feeds a compiler agent)
3. Run the workflow
4. Wait for the run to complete
5. Open the **Steps tab** and click on the agent at position N+1
6. Read the **Agent Output** — observe it reports the upstream file is missing, or produced a fallback/placeholder response

**Observed example 1 (PPT pipeline in custom workflow):**
- Step 1: `ppt-brief-analyst` is supposed to write `brief-spec.md`
- Step 2: `ppt-composer` calls `read_file("brief-spec.md")` → file not found → produces 328-token question: *"The sandbox appears to be initialized but `brief-spec.md` hasn't been created yet…"*

**Observed example 2 (prototype pipeline in custom workflow):**
- Step 2: `prototype-plan` is supposed to write a task plan file
- Step 4: `prototype-build` calls `ls /` → sandbox empty → produces 145-token placeholder: *"I'm ready to help. What would you like me to do?"*

**Observed example 3 (user-stories pipeline in custom workflow):**
- Step 2: `epic-architect` is supposed to write epic/story output
- Step 3: `story-estimator` receives zero prior context (0 cache_read_tokens) → produces 108-token placeholder: *"What would you like me to do? I'm ready to estimate story points…"*

### Expected

Agent N writes its output to the sandbox using `write_file`. Agent N+1 reads that file, has full context, and produces the correct downstream output. This is how the same agents work in their native (non-custom) workflow pipelines.

### Actual

Because `write_file` is never available to any custom workflow agent (QA-PS-019 root cause), agent N can only stream text output — no file is written. Agent N+1 calls `read_file` on the expected path, finds nothing, and either produces a confused question or a "ready to help" placeholder. The engine advances the pipeline regardless.

This affects every inter-agent file dependency in every custom workflow, regardless of which agents the user selects.

### Root Cause (technical)

Direct consequence of QA-PS-019: `_apply_selections` never applies the `write_files: true` grant to custom workflow steps. All steps run with `ToolPermissions(write_files=False)`. No agent in any custom workflow can call `write_file` or `edit_file`, so no inter-agent file handoff can ever succeed.

### Browser / Log Signals

```
Any agent that reads an upstream file: tool_call read_file → file not found
Sandbox ls / → empty (no files written by any prior agent)
Downstream agent output: question or placeholder, not intended work product
cache_read_tokens for starved agents: 0 (no prior agent output in context)
```

### Files

- `backend/agents/execution_engine/engine.py` — `_apply_selections` missing `tools` overlay (QA-PS-019)
- `backend/agents/execution_engine/engine.py` — `_check_artifact_fallback`: writes fallback to engine-reserved path, not to the path the downstream agent expects
- `backend/agents/workflows/custom/workflow.yaml` — no `write_files` declared on any step

---

<a id="qa-sg-006"></a>

## QA-SG-006 — Active pipeline popup shows incorrect step number in notification when navigating from workflow run to home page

- **Page:** Home page + Notifications panel (active pipelines dropdown)
- **Route:** / (home) and notification active pipelines popup
- **Severity:** High
- **Found by:** SG
- **Found at:** 2026-09-18
- **User:** qa-admin@flowinqa.com

### Reproduction

1. Sign in as `qa-admin@flowinqa.com`
2. Start a workflow run (any workflow type, e.g. prototype, PPT, user stories)
3. Wait for the workflow to begin executing and reach an intermediate step (e.g. step 3 of 5)
4. Navigate away from the run detail page to the **home page** (e.g. click the Velocity logo or navigate to `/`)
5. Click the **bell icon** in the top navigation bar to open the Notifications panel
6. Look at the active pipelines dropdown/popup
7. Observe the step number displayed for the running workflow

### Expected

The active pipelines popup should display the **correct current step number** that matches the actual step the workflow is currently executing. For example, if the workflow is on step 3 of 5, the popup should show "Step 3 of 5" or similar.

### Actual

The active pipelines popup shows an **incorrect step number** that does not match the actual current step of the workflow. The step counter either:
- Shows a step number that is behind the actual current step (e.g. shows "Step 1 of 5" when the workflow is actually on step 3)
- Shows a step number that is ahead of the actual current step
- Does not update correctly as the workflow progresses

The step number appears to be stale or not synchronized properly when navigating away from the run detail page to the home page.

### Browser Signals

```
Console: not checked
Network: not checked
```

### Notes

This issue manifests specifically when navigating from a run detail page to the home page. The step number may be correct on the run detail page itself, but becomes incorrect in the notification popup after navigating away. This suggests a state synchronization issue between the run detail view and the global notification system.




---

<a id="qa-ps-021"></a>

## QA-PS-021 — Downstream agents in a custom workflow receive no upstream artifacts and either compensate by producing wrong content or emit diagnostic output instead of the intended deliverable

- **Page:** Custom workflow run — Steps tab, any agent downstream of a broken upstream step; Files tab; Preview tab
- **Route:** /create/custom and /runs/{id}
- **Severity:** High
- **Found by:** PS
- **Found at:** 2026-09-17
- **User:** qa-admin@flowinqa.com

### Reproduction

1. Sign in as `qa-admin@flowinqa.com`
2. Build any custom workflow with 3 or more agents where agent N produces a file that agent N+1 and agent N+2 depend on (e.g. a writer → compiler → validator chain, or a spec → build → validate chain)
3. Run the workflow
4. Wait for the run to complete
5. Open the **Steps tab** and read the output of the last agent in the chain
6. Open the **Files tab** and **Preview tab** — observe the deliverable content

### Expected

Each agent receives the upstream output it depends on, does its declared work, and produces its intended output. The final deliverable is the result of the complete pipeline executing correctly.

### Actual

Because no upstream agent can write files (QA-PS-019), later agents in the pipeline find an empty sandbox. Rather than failing cleanly, they attempt to recover by working around the gap:

- **Validator/QA-type agents** detect the missing upstream artifact, determine the pipeline is incomplete, and attempt to generate the deliverable themselves — doing the work of the upstream build/compiler agent. They may produce a working output, but it comes with reasoning prose prepended, is attributed to the wrong agent, and the run is marked degraded rather than failed with a clear error.
- **Compilation/aggregation agents** detect incomplete upstream files, silently drop content they cannot find, and produce a partial final output without flagging what was omitted.
- **All agents** that find no upstream context may emit diagnostic text explaining why they are blocked, which then becomes the deliverable content the user sees.

**Observed example 1 (PPT pipeline in custom workflow):**
`ppt-validator` ran for 102.9s (154K tokens), detected no composer output, generated the entire HTML deck itself, then reported it couldn't write it to disk. The deliverable contained reasoning prose + HTML. Run marked `degraded`.

**Observed example 2 (prototype pipeline in custom workflow):**
`prototype-validate` ran for 217s (369K tokens on Sonnet 5), detected no `prototype.html`, reconstructed the reasoning but couldn't persist the fix. Reported as blocked. Run marked `completed` despite no real deliverable.

**Observed example 3 (user-stories pipeline in custom workflow):**
`backlog-compiler` detected the estimator produced nothing, adapted, but silently dropped the entire SDK Integration Layer epic (4 stories) from the final compiled output.

### Root Cause (technical)

Downstream agents have no upstream artifact to validate or build upon because QA-PS-019 prevents any file writes. The agents' system prompts instruct them to read upstream files — when those files are absent, the model attempts to recover using whatever context it has from the `.agents/` directory (engine-recorded streamed output). This produces output outside the agent's declared role and of unpredictable quality. The engine has no contract enforcement preventing an agent from doing work outside its declared scope, and no pre-dispatch check for "required upstream artifact exists."

### Browser / Log Signals

```
Downstream agent output: compensation content, diagnostic text, or partial work — not the intended deliverable
pipeline_complete.deliverable_mimetype: may mismatch deliverable_filename (e.g. text/markdown for output.html)
pipeline_complete.published_status: "degraded" or incorrectly "completed"
Run header badge: "Degraded" or incorrectly "Done"
Preview tab: diagnostic text or reasoning prose rendered as deliverable
```

### Files

- `backend/agents/capabilities/gates/validation.py` — `_build_validation_target`: no upstream artifact existence pre-check
- `backend/agents/execution_engine/engine.py` — `_unrecovered_agents` logic: only catches exceptions, not placeholder output
- `backend/agents/execution_engine/engine.py` — `_apply_selections` missing `tools` overlay (QA-PS-019, root cause)

---

<a id="qa-sg-007"></a>

## QA-SG-007 — Changing workflow from notification tab sometimes fails to redirect to the selected workflow

- **Page:** Notifications panel (active pipelines dropdown)
- **Route:** Any page + /runs/{id}
- **Severity:** High
- **Found by:** SG
- **Found at:** 2026-09-18
- **User:** qa-admin@flowinqa.com

### Reproduction

1. Sign in as `qa-admin@flowinqa.com`
2. Start two or more parallel workflow runs
3. Wait for the runs to begin executing
4. Click the **bell icon** in the top navigation bar to open the Notifications panel
5. Observe the list of active workflows in the notification dropdown
6. Click on a workflow entry to switch to it
7. Repeat this process several times, clicking between different active workflows

### Expected

Clicking on a workflow entry in the notification tab should consistently redirect to that workflow's run detail page (`/runs/{id}`) every time, without fail.

### Actual

Sometimes clicking on a workflow entry in the notification tab does **not redirect** to the selected workflow's run detail page. The app may:
- Stay on the current page (no navigation occurs)
- Navigate to the wrong workflow
- Partially load or show incorrect content
- Take an unusually long time to redirect

The redirect failure is intermittent — the same workflow entry may work on a subsequent click, suggesting a race condition or timing issue with the notification system's workflow switching logic.

### Browser Signals

```
Console: not checked
Network: not checked
```

### Notes

This issue is similar to QA-SG-004 and QA-PS-005 but specifically focuses on the notification tab's workflow switching. The problem occurs intermittently rather than consistently, making it difficult to predict when it will fail.




---

<a id="qa-ps-022"></a>

## QA-PS-022 — Any custom workflow agent that receives no context or tools produces a placeholder response — engine treats it as a successful step completion and the pipeline continues

- **Page:** Custom workflow run — Steps tab, any agent that produced placeholder output
- **Route:** /create/custom and /runs/{id}
- **Severity:** Medium
- **Found by:** PS
- **Found at:** 2026-09-17
- **User:** qa-admin@flowinqa.com

### Reproduction

1. Sign in as `qa-admin@flowinqa.com`
2. Build any custom workflow where an agent depends on an upstream file or task context (e.g. any agent after a first agent in a multi-step pipeline)
3. Run the workflow
4. Open the **Steps tab** after the run completes
5. Click on any mid-pipeline agent — read its Agent Output and check its duration and token count

### Expected

When an agent cannot find its required input (upstream file missing, no task context injected), the step is marked as **failed**. The engine emits a clear error, the pipeline stops, and `pipeline_failed` is reported with a reason such as "required input artifact not found for step X" or "agent produced no deliverable". The user is informed of exactly what went wrong.

### Actual

Any agent in a custom workflow that receives no upstream files or task context falls back to a generic conversational response, because the model receives only its bare system prompt with no work to do:

- **Observed in PPT custom workflow:** `ppt-composer` ran 9.98s, produced 328 tokens: *"The sandbox appears to be initialized but `brief-spec.md` hasn't been created yet… Could you confirm: do you have a slide plan?"*
- **Observed in prototype custom workflow:** `prototype-build` ran 5.53s, produced 145 tokens: *"I'm ready to help. What would you like me to do?"*
- **Observed in user-stories custom workflow:** `story-estimator` ran 5.87s, produced 293 tokens: *"What would you like me to do? I'm ready to estimate story points…"*

In every case the engine emits `agent_complete`, counts the step as successful, and advances to the next agent. There is no check for whether the output is a deliverable or a conversational placeholder. The `_check_artifact_fallback` writes the placeholder text as the artifact file — so the engine sees a file "existing" at the expected path, even though its content is a question or greeting.

This pattern applies to **any agent at any position in any custom workflow** where upstream files are missing (which is always the case due to QA-PS-019).

### Root Cause (technical)

`_run_agent` in `engine.py` treats a step as complete when the agent invocation finishes without raising an exception. There is no post-completion check for:
- Whether the agent produced its declared output artifact
- Whether the output is a deliverable vs conversational text
- Whether output_length / output_tokens indicate meaningful work was done

The `_check_artifact_fallback` unconditionally writes the streamed text to the artifact path, making the artifact "exist" regardless of content quality.

### Browser / Log Signals

```
agent_complete: duration 5–10s, output_tokens 100–350 (far below what real work requires)
agent output: question or greeting, not a deliverable
No write_file tool_call from the affected agent
cache_read_tokens: 0 (no prior agent context received)
Pipeline continues to next agent without error
```

### Files

- `backend/agents/execution_engine/engine.py` — `_run_agent`: no output-quality check after agent_complete
- `backend/agents/execution_engine/engine.py` — `_check_artifact_fallback`: writes any streamed text as artifact, regardless of content

---

<a id="qa-sg-008"></a>

## QA-SG-008 — SSE events for approvals and clarifications don't sync across multiple browser sessions, require manual backend request to refresh

- **Page:** Run detail — review gates and clarification panels
- **Route:** /runs/{id}
- **Severity:** High
- **Found by:** SG
- **Found at:** 2026-09-18
- **User:** qa-admin@flowinqa.com (same user, multiple browsers)

### Reproduction

1. Sign in as `qa-admin@flowinqa.com` on **Browser A**
2. Sign in as `qa-admin@flowinqa.com` on **Browser B** (same user, different browser or tab)
3. Start a workflow run that has **review gates** and **clarification questions** (e.g. a User Stories run or PPT run)
4. In **Browser A**, navigate to the run detail page and wait for a review gate or clarification question prompt
5. In **Browser A**, **approve the review gate** or **fill in and submit clarification answers**
6. Observe the result in **Browser A** — the approval/clarification should be processed and the UI should update correctly
7. Simultaneously, observe **Browser B** (which is also on the same run's detail page)

### Expected

When an approval or clarification response is submitted in **Browser A**, the SSE event stream should notify all connected clients (including **Browser B**) about the state change. Both browsers should show:
- The review gate removed or marked as approved
- The clarification panel closed or marked as answered
- The pipeline continuing to the next step
- All state changes reflected in real-time across all sessions

### Actual

**Browser A** correctly shows the approval/clarification being processed and updates its UI immediately. However, **Browser B** does **not** receive or display the SSE event:
- The review gate or clarification panel **remains on screen** in Browser B
- The UI appears stalled — showing outdated state
- Browser B does **not** automatically update to reflect the approval or submission that occurred in Browser A

**Workaround:** To force Browser B to show the correct state, the user must manually trigger a backend request (e.g. by clicking a button, navigating, or refreshing). After the manual request, Browser B updates and shows the correct state.

This indicates that the SSE event was either:
- Not broadcast to all connected clients
- Lost or dropped before reaching Browser B
- Not properly handled by the Browser B's event stream listener

### Browser Signals

```
Console: not checked
Network: Check SSE event stream — likely missing events for approvals/clarifications
```

### Notes

This is a critical synchronization bug in the SSE event distribution system. When multiple browser sessions are logged in as the same user and watching the same run, actions in one session should immediately propagate to all other sessions via SSE. The fact that a manual backend request fixes it suggests the backend has the correct state, but the SSE broadcast is incomplete or unreliable.

This affects multi-window/multi-device workflows where a user monitors a run from multiple screens or has the same run open in multiple tabs/browsers.


<a id="qa-sg-009"></a>

## QA-SG-009 — Run detail page takes a long time to render data, causing significant delays in displaying run information

- **Page:** Run detail page
- **Route:** /runs/{id}
- **Severity:** High
- **Found by:** SG
- **Found at:** 2026-09-18
- **User:** qa-admin@flowinqa.com

### Reproduction

1. Sign in as `qa-admin@flowinqa.com`
2. Go to `/runs` (Run History page)
3. Click on any completed or in-progress run to open the run detail page
4. Observe the time it takes for the page to load and render the run data
5. Note the delay from clicking the run until the run information (steps, agents, files, chat, etc.) appears on screen

### Expected

The run detail page should load and render quickly (under 2-3 seconds) so the user can view the run information without noticeable delay. The page should display:
- Run summary and metadata
- Pipeline steps and agent progress
- Chat/concierge messages
- Files and deliverables
- Review gates and clarifications
- Other run details

All of this should be rendered responsively and the page should be interactive within a few seconds of navigation.

### Actual

The run detail page **takes significantly longer than expected** to render data. The user experiences:
- Long initial load time after clicking on a run (5+ seconds or more)
- Blank or partially rendered page while data is loading
- Delayed appearance of run information, making it appear the page is frozen or stalled
- Slow responsiveness during the initial render phase

The delay makes the app feel sluggish and unresponsive, particularly when opening runs in sequence or monitoring multiple runs.

### Browser Signals

```
Console: not checked
Network: Check for slow API calls or large data payloads being transferred
```

### Notes

This performance issue may be caused by:
- Slow API response times for fetching run data
- Large amounts of data being transferred (run events, chat history, files list, etc.)
- Inefficient front-end rendering or data processing
- Missing pagination or lazy-loading for large datasets
- Unoptimized queries on the backend

The page eventually loads correctly, suggesting this is a rendering/data-fetching performance issue rather than a functional bug.


<a id="qa-sg-010"></a>

## QA-SG-010 — Share button on run detail page displays raw JSON instead of a simple message while workflow is running

- **Page:** Run detail page — share button/tooltip
- **Route:** /runs/{id}
- **Severity:** Low
- **Found by:** SG
- **Found at:** 2026-09-18
- **User:** qa-admin@flowinqa.com

### Reproduction

1. Sign in as `qa-admin@flowinqa.com`
2. Start a workflow run (any workflow type)
3. Wait for the workflow to begin executing (while it is **actively running**)
4. Navigate to the run detail page (`/runs/{id}`)
5. Look for and click the **Share button** (typically in the header or toolbar of the run detail page)
6. Observe the message or tooltip that appears

### Expected

The share button should display a **simple, user-friendly message** such as:
- "Run shared successfully"
- "Link copied to clipboard"
- "Share link generated"
- Or similar plain-language feedback

The message should be clear and easy to understand for the end user.

### Actual

The share button displays **raw JSON** instead of a simple message. The JSON output (which appears to be the API response or internal data structure) is shown directly to the user, making it:
- Confusing and unclear what action was performed
- Not user-friendly
- Indicating a missing message translation, formatting, or UI rendering issue

This only occurs **while the workflow is running**. Once the workflow completes, the share button behavior may normalize (not verified).

### Browser Signals

```
Console: check for JSON parsing or message rendering errors
Network: not checked
```

### Notes

This is a cosmetic/UX issue rather than a functional bug. The share functionality likely works correctly (the JSON is probably being generated), but the message presentation layer is broken, exposing raw data to the user instead of rendering a friendly message.


<a id="qa-sg-011"></a>

## QA-SG-011 — Version 1 prototype shows no content in preview, preview area is blank when viewing v1

- **Page:** Run detail — Preview tab (version selector showing v1)
- **Route:** /runs/{id}
- **Severity:** High
- **Found by:** SG
- **Found at:** 2026-09-18
- **User:** qa-admin@flowinqa.com

### Reproduction

1. Sign in as `qa-admin@flowinqa.com`
2. Go to `/runs` and open a completed prototype run that has at least one revision (showing multiple versions: v1, v2, etc.)
3. Click the version dropdown at the top of the run detail page (currently showing "Latest" or "v2")
4. Select **v1** from the version list
5. Observe the Preview tab content area

### Expected

When viewing **v1**, the Preview tab should display the **prototype content for version 1**, such as:
- The rendered prototype/diagram/design
- Preview of the generated deliverable (HTML, presentation, etc.)
- The actual output that was produced for v1

The preview should be identical to what was shown when v1 was the latest version.

### Actual

When viewing **v1**, the **preview area is completely blank/empty**. The page shows:
- A yellow banner stating **"Viewing v1 read-only"** with a "Back to latest" button
- An empty preview area below with no content rendered
- No prototype/deliverable content is displayed

The preview should show the v1 prototype content, but instead shows nothing. This makes it impossible to review what was generated in version 1.

### Browser Signals

```
Console: check for failed API calls or missing data for v1 preview
Network: check if the v1 preview data is being requested and returned by the backend
```

### Notes

The v1 version selector is working (the page recognizes v1 is selected, as shown by the banner), but the preview content is not being fetched or rendered. This suggests either:
- The preview data for v1 is not being requested
- The preview data is not being returned by the backend
- The front-end is not rendering the preview even if data is received


<a id="qa-sg-012"></a>

## QA-SG-012 — Concierge chat response text is not white in night mode, hard to read with low contrast

- **Page:** Run detail — Concierge chat lane
- **Route:** /runs/{id}
- **Severity:** Medium
- **Found by:** SG
- **Found at:** 2026-09-18
- **User:** qa-admin@flowinqa.com

### Reproduction

1. Sign in as `qa-admin@flowinqa.com`
2. Enable **night mode** / dark theme in the application
3. Start a workflow run that generates concierge chat responses (e.g. a User Stories or Prototype run)
4. Wait for the workflow to complete and generate responses from agents
5. Look at the **concierge chat lane** on the run detail page
6. Observe the text color of the agent response messages

### Expected

In night mode (dark theme), concierge chat response text from agents should be **white** or a light color with sufficient contrast against the dark background, making it easy to read.

### Actual

The concierge chat response text is **not white** — it appears in a **muted gray or dim color** that blends in with the dark background, creating low contrast and making the text difficult to read. The user has to strain to read agent responses in the chat.

The text color should match the expected white/light color of other UI text in night mode for consistency and readability.

### Browser Signals

```
Console: not checked
Network: not checked
```

### Notes

This is a theming/styling issue. The chat response component is not respecting the night mode text color scheme. User responses (shown in the purple bubble at the top of the screenshot) appear to have correct styling, but agent responses (shown below) have incorrect text color.




---

<a id="qa-ps-023"></a>

## QA-PS-023 — Preview panel shows raw agent reasoning text prepended to the HTML deliverable

- **Page:** Run detail — Preview tab
- **Route:** /runs/{id}
- **Severity:** Medium
- **Found by:** PS
- **Found at:** 2026-09-17
- **User:** qa-admin@flowinqa.com

### Reproduction

1. Sign in as `qa-admin@flowinqa.com`
2. Open the completed custom PPT workflow run at `/runs/bf9f230d-6123-4d42-9089-ffde5c31d4f0` (or any custom workflow run where the last agent produced HTML)
3. Click the **Preview** tab

### Expected

The Preview tab displays only the rendered HTML presentation — the first slide of the carousel is visible immediately, with no text visible before it. The preview is clean, as if the HTML file itself were opened in a browser.

### Actual

The Preview panel shows several paragraphs of the validator agent's internal reasoning text before the presentation begins:

> *"The composer file contains no artifact. Let me check what files exist in the `.agents/` directory: Let me check the brief analyst output: Now let me read the composer file completely to find the artifact: The composer output shows that no HTML deck was generated…"*

This text appears in the rendered iframe above the actual HTML slide content. The user sees the agent's stream-of-thought diagnostic before slide 1.

### Root Cause (technical)

The `streamed_text` deliverable resolver reads `ectx`'s accumulated streamed output as `final_output`. This is the agent's entire response text — including any reasoning/diagnostic prose the model produced before (or instead of) calling `write_file`. When an agent writes clean HTML via `write_file`, the streamed output is typically just the HTML. But when an agent produces prose reasoning before the HTML (as the validator did in this run), `final_output` contains both. `page.tsx` sets `genericDeliverable.content = finalOutput` verbatim. The `GenericDeliverablePreview` component sets `<iframe srcdoc={content}>` and the browser renders the prose text nodes before the `<!DOCTYPE html>` declaration.

The correct behavior is for `final_output` to be sourced from the written artifact file (the clean HTML on disk) rather than from the raw streamed response text.

### Browser / Log Signals

```
pipeline_complete.final_output: starts with "The composer file contains no artifact..."
pipeline_complete.deliverable_filename: "output.html"
pipeline_complete.deliverable_mimetype: "text/html"
Preview iframe: renders reasoning prose as visible text before slide 1
```

### Files

- `backend/agents/execution_engine/engine.py` — `final_output = _resolver.resolve(ectx)` (~line 6721); `streamed_text` resolver reads accumulated stream, not the file
- `frontend/src/app/[...view]/page.tsx` — `setGenericDeliverable({content: finalOutput})` (~line 1553–1568)
- `frontend/src/components/results/PreviewPanel.tsx` — `GenericDeliverablePreview` iframe `srcdoc={content}`

---

<a id="qa-ps-024"></a>

## QA-PS-024 — Steps panel shows "Run failed" badge for a degraded run instead of "Run degraded"

- **Page:** Run detail — Steps tab header
- **Route:** /runs/{id} (Steps tab)
- **Severity:** Medium
- **Found by:** PS
- **Found at:** 2026-09-17
- **User:** qa-admin@flowinqa.com

### Reproduction

1. Sign in as `qa-admin@flowinqa.com`
2. Open any run that completed with `status: degraded` (e.g., the custom PPT run at `/runs/bf9f230d-6123-4d42-9089-ffde5c31d4f0`)
3. Click the **Steps** tab
4. Look at the status badge and label at the top of the Steps panel
5. Also look at the top-of-page header badge (the pill next to the version dropdown)

### Expected

Both surfaces consistently show **"Run degraded"** (amber indicator) for a `degraded` pipeline completion. A degraded run is a partial success — at least one agent completed, but some aspect of the run was not fully successful. It is distinct from a full failure and should never read as "Run failed."

### Actual

The **Steps panel** shows a red circle with an X icon and the label **"Run failed"**. The **top header badge** (in `LaneRunHeader`) correctly shows **"Degraded"** in amber. The two surfaces on the same page display contradictory statuses.

### Root Cause (technical)

In `StepsOverviewSpine.tsx`, the `failed` boolean is derived as:

```typescript
const failed = !isRunning && (pipelineState?.failed || agents.some(a => a.status === "error"));
```

The `pipeline_complete` handler in `useWorkflow.ts` correctly sets `pipelineState.degraded = true` (not `pipelineState.failed`). However, it also marks any agent listed in `agents_failed` with `status: "error"`. For a degraded run, those error-status agents make `agents.some(a => a.status === "error")` evaluate to `true`, which sets `failed = true` in StepsOverviewSpine — and the `failed ? "Run failed"` branch takes priority over the `pipelineState?.degraded ? "Run degraded"` check that follows it.

The `LaneRunHeader` correctly tests `pipelineState?.failed` first and then `pipelineState?.degraded` separately — so it shows the right label. `StepsOverviewSpine` needs the same guard: it must check `pipelineState?.failed` directly (not derive it from per-agent error status) to avoid conflating a degraded run with a hard failure.

### Browser / Log Signals

```
pipeline_complete event: status="degraded", agents_failed=[] (empty in this run — all 3 agents technically completed)
pipelineState.failed: undefined / false
pipelineState.degraded: true
agents[*].status: "done" for all three (no agent has status "error" in this specific run)
Steps panel header: "Run failed" (red X)
Lane header badge: "Degraded" (amber triangle) — correct
```

### Notes

This is a theming/styling issue. The chat response component is not respecting the night mode text color scheme. User responses (shown in the purple bubble at the top of the screenshot) appear to have correct styling, but agent responses (shown below) have incorrect text color.


<a id="qa-sg-013"></a>

## QA-SG-013 — Download button is disabled on user story run detail page, cannot download deliverable

- **Page:** Run detail page — header toolbar (user story workflow)
- **Route:** /runs/{id}
- **Severity:** High
- **Found by:** SG
- **Found at:** 2026-09-18
- **User:** qa-admin@flowinqa.com

### Reproduction

1. Sign in as `qa-admin@flowinqa.com`
2. Go to `/runs` and open a **completed user story workflow run**
3. Navigate to the run detail page (`/runs/{id}`)
4. Look at the header toolbar where the **Share** and **Download** buttons are located
5. Observe the state of the **Download** button

### Expected

The **Download** button should be **enabled** (blue/purple, clickable) on a completed user story run, allowing the user to download the generated deliverable (e.g. user stories document, requirements, etc.).

### Actual

The **Download** button is **disabled** (grayed out, not clickable) even though:
- The run is completed
- A deliverable has been generated
- The download should be available

The button appears disabled and clicking it does nothing. The user cannot download the generated user story deliverable from the run detail page.

### Browser Signals

```
Console: not checked
Network: not checked
```

### Notes

This issue is specific to user story workflow runs. Other workflow types (prototype, PPT) may have working download buttons. The button shows as disabled despite there being a valid deliverable to download, suggesting:
- The download button state is incorrectly set for user story runs
- The download endpoint or file may not be properly configured for user stories
- A permission or authorization issue preventing the download




---

<a id="qa-ps-025"></a>

## QA-PS-025 — Custom workflow agents that require task_loop strategy receive no task injection — the step runs as single_shot with no task context and produces placeholder output

- **Page:** Custom workflow run — Steps tab, any agent that depends on task injection from an upstream planner
- **Route:** /create/custom and /runs/{id}
- **Severity:** High
- **Found by:** PS
- **Found at:** 2026-09-17
- **User:** qa-admin@flowinqa.com

### Reproduction

1. Sign in as `qa-admin@flowinqa.com`
2. Build a custom workflow that includes a planner-type agent (e.g. any agent that produces a task list using `<tasks>...</tasks>` output) followed by a worker-type agent that should execute those tasks one at a time
3. Run the workflow
4. Open the **Steps tab** and click on the worker agent (the one that should have received tasks)
5. Read the Agent Output

**Observed example (prototype pipeline in custom workflow):**
- Step 2: `prototype-plan` produces a 3-task plan wrapped in `<tasks>` tags
- Step 4: `prototype-build` should receive Task 1, Task 2, Task 3 in sequence and build `prototype.html`
- **Actual:** `prototype-build` receives bare system prompt only, produces: *"I'm ready to help. What would you like me to do?"*

### Expected

When a user adds a worker agent downstream of a planner agent in the custom composer, the worker agent receives individual tasks from the planner's output (one task per agent invocation via the `task_loop` strategy). The worker executes each task and writes its output to the sandbox.

### Actual

The worker agent runs as the default `single_shot` strategy with no task context injected. It receives only its system prompt with no reference to the planner's output, no `CURRENT_TASK` block, and no task description. The agent has no work to do and produces a generic placeholder response. Zero `cache_read_tokens` confirm the prior agents' outputs are absent from its context.

This affects any custom workflow where a user intends to link a planner agent to a worker agent — the `task_loop` strategy and `task_source` configuration that make this connection work are either:
- Not exposed as configurable levers in the composer UI, or
- Not automatically inferred when the user connects a planner to a worker, or
- Not correctly saved into the workflow selections when configured

### Root Cause (technical)

In native workflows (e.g. the real prototype pipeline), the worker agent's step declaration in `workflow.yaml` includes `strategy: task_loop` and `task_source: {source_step: prototype-plan, parser: heading_tasks}`. This is what injects individual tasks from the planner's output into the worker one at a time.

When any pipeline is replicated via the custom composer, these settings are not automatically carried over. The worker step is compiled with the default `single_shot` strategy. `_apply_selections` in `engine.py` can overlay `strategy` and `task_source` IF the user explicitly configured them in the composer — but the composer does not automatically detect the planner→worker relationship and pre-populate these fields.

### Log Evidence

```
agent_complete for prototype-build (or any task_loop-dependent worker):
  duration: 5–6s (vs expected minutes for real build work)
  output_tokens: 100–200 (vs thousands for real work)
  cache_read_tokens: 0  ← planner output NOT in context
  output: "I'm ready to help" / "What would you like me to do?"
No task_loop_progress events for the worker agent
```

### Files

- `backend/agents/execution_engine/engine.py` — `_apply_selections`: `task_source` overlay exists but requires explicit user selection
- `backend/agents/workflows/custom/workflow.yaml` — no `task_loop` strategy or `task_source` on any default step
- `frontend/src/components/workflow/AgentsPopup.tsx` — composer UI: task_loop + task_source lever exposure for worker steps

---

<a id="qa-sg-014"></a>

## QA-SG-014 — Custom workflow output generates markdown instead of selected format, always produces .md files

- **Page:** Custom workflow — run detail page
- **Route:** /runs/{id}
- **Severity:** High
- **Found by:** SG
- **Found at:** 2026-09-18
- **User:** qa-admin@flowinqa.com

### Reproduction

1. Sign in as `qa-admin@flowinqa.com`
2. Create or select a **custom workflow** that supports multiple output formats (e.g. HTML, PDF, markdown, etc.)
3. Configure the workflow to generate output in a **specific format** (e.g. HTML)
4. Start the custom workflow run
5. Wait for the run to complete
6. Navigate to the run detail page and check the **Files tab** or **deliverables**
7. Observe the format of the generated output file

### Expected

The generated output file should match the **selected format** specified in the workflow configuration. For example:
- If HTML is selected, the output should be an `.html` file
- If markdown is selected, the output should be a `.md` file

The output content should also be properly formatted according to the selected output type (e.g. valid HTML markup for HTML output).

### Actual

Regardless of which output format is **selected** in the workflow configuration, the custom workflow **always generates markdown** (`.md` files). For example:
- Selecting HTML → generates `.md` file with markdown content
- Selecting PDF → generates `.md` file instead of PDF
- Selecting any other format → generates `.md` file

The output selection is not being respected. The workflow ignores the configured output format and defaults to generating markdown every time.

### Browser Signals

```
Console: not checked
Network: not checked
```

### Notes

This is a critical issue for custom workflows because users cannot get output in the format they need. The output format selection appears to be either:
- Not being passed to the backend correctly
- Being ignored by the workflow execution engine
- Using a hardcoded default (markdown) regardless of the configuration

The issue affects the usability of custom workflows significantly, as users have no way to get output in their required format.



---

<a id="qa-ps-026"></a>

## QA-PS-026 — Custom workflow validator agent runs on Sonnet 5 instead of Haiku 4.5, consuming 369K tokens and $0.28 on a single diagnostic step

- **Page:** Custom workflow run — Steps tab, agent "Validation Agent" (step 5); Audit tab
- **Route:** /runs/{id}
- **Severity:** Medium
- **Found by:** PS
- **Found at:** 2026-09-17
- **User:** qa-admin@flowinqa.com

### Reproduction

1. Sign in as `qa-admin@flowinqa.com`
2. Create or select a **custom workflow** that supports multiple output formats (e.g. HTML, PDF, markdown, etc.)
3. Configure the workflow to generate output in a **specific format** (e.g. HTML)
4. Start the custom workflow run
5. Wait for the run to complete
6. Navigate to the run detail page and check the **Files tab** or **deliverables**
7. Observe the format of the generated output file

### Expected

The generated output file should match the **selected format** specified in the workflow configuration. For example:
- If HTML is selected, the output should be an `.html` file
- If markdown is selected, the output should be a `.md` file

The output content should also be properly formatted according to the selected output type (e.g. valid HTML markup for HTML output).

### Actual

Regardless of which output format is **selected** in the workflow configuration, the custom workflow **always generates markdown** (`.md` files). For example:
- Selecting HTML → generates `.md` file with markdown content
- Selecting PDF → generates `.md` file instead of PDF
- Selecting any other format → generates `.md` file

The output selection is not being respected. The workflow ignores the configured output format and defaults to generating markdown every time.

### Browser Signals

```
Console: not checked
Network: not checked
```

### Notes

This is a critical issue for custom workflows because users cannot get output in the format they need. The output format selection appears to be either:
- Not being passed to the backend correctly
- Being ignored by the workflow execution engine
- Using a hardcoded default (markdown) regardless of the configuration

The issue affects the usability of custom workflows significantly, as users have no way to get output in their required format.

2. Run the custom prototype workflow as described in QA-PS-025
3. After the run completes, open the **Steps tab** and click **Validation Agent** (step 5)
4. Look at the model badge shown next to the agent name (visible in the screenshot: "CLAUDE HAIKU 4.5" vs what was actually used)
5. Also check the **Audit tab** for per-agent token/cost breakdown

### Expected

All agents in a custom workflow run use the same model — **Claude Haiku 4.5** (`eu.anthropic.claude-haiku-4-5-20251001-v1:0`) — unless the user explicitly overrides the model for a specific step in the composer's Config tab. No agent should silently switch to a more expensive model without the user's explicit selection.

### Actual

The Validation Agent (`prototype-validate`) ran on **`claude-sonnet-5`** — a different, significantly more expensive model — while all other 4 agents in the same run used Haiku 4.5. This caused:
- **369,410 input tokens** for a single step (vs 9K–28K for the other agents)
- **217 seconds** of execution time (vs 5–43s for others)
- Disproportionate cost: the validator alone consumed the majority of the run's token budget
- The validator's output was a diagnostic text explaining why it couldn't validate (not a validation result)

The model switch happened without any explicit user configuration in the composer.

### Root Cause (technical)

The `prototype-validate` agent's capability definition or AGENT.md likely declares a specific `model:` override pointing to Sonnet 5 (or a higher-tier model alias that resolves to Sonnet 5). When this agent is used in a custom workflow, the model override from the agent's spec file is carried through even without user selection in the composer. The custom workflow engine applies the agent's declared model preference, overriding the run-level default model.

This is a problem because:
1. The user has no visibility that one agent will run on a different, much more expensive model
2. The composer UI's Config tab model selector may not reflect or override the agent's built-in model declaration
3. A 369K-token step on Sonnet 5 (~$0.28 alone) on a run that produced no useful deliverable is pure waste

### Log Evidence

```
agent_complete for prototype-validate:
  model_id: "eu.anthropic.claude-sonnet-5"   ← different from all other agents
  input_tokens: 369,410
  output_tokens: 18,792
  cache_read_tokens: 325,210
  duration: 217.15s

All other agents:
  model_id: "eu.anthropic.claude-haiku-4-5-20251001-v1:0"
  input_tokens: 9K – 28K
  duration: 5s – 43s
```

### Browser / Log Signals

```
pipeline_complete.model_id: "eu.anthropic.claude-haiku-4-5-20251001-v1:0"  ← reflects the majority model, not Sonnet
Steps tab: agent shows model badge — should indicate which model each step used
Audit tab: token breakdown reveals the validator's outsized contribution
```

### Files

- `backend/agents/prompts/prototype-validate/AGENT.md` (if it exists) — check for `model:` declaration
- `backend/agents/execution_engine/engine.py` — `_apply_selections`: model overlay; check whether agent-declared model is preserved when no user override exists
- `backend/agents/capabilities/model_catalog.py` — model catalog; check what `claude-sonnet-5` resolves to

---

<a id="qa-ps-027"></a>

## QA-PS-027 — Custom workflow run marked as fully completed even when agents produced only placeholder output — engine only checks for exceptions, not output quality

- **Page:** Run detail — header badge; Steps tab status; Files tab
- **Route:** /create/custom and /runs/{id}
- **Severity:** High
- **Found by:** PS
- **Found at:** 2026-09-17
- **User:** qa-admin@flowinqa.com

### Reproduction

1. Sign in as `qa-admin@flowinqa.com`
2. Run any custom workflow where one or more agents produced placeholder/conversational output (this occurs in any custom workflow due to QA-PS-019 and QA-PS-025)
3. After the run completes, look at the **header badge** (shows "Done" / green check)
4. Open the **Files tab** — observe the deliverable filename and content
5. Open the **Preview tab** — observe what is rendered

**Observed example 1 (PPT custom workflow, run `bf9f230d`):**
- 3 agents all completed without exceptions
- Build agent produced a question (9.98s, 328 tokens)
- Validator generated the deliverable itself and reported it couldn't save
- `pipeline_complete.published_status: "degraded"` — at least the status was degraded here
- BUT the deliverable rendered as the validator's diagnostic text

**Observed example 2 (prototype custom workflow, run `7b00ac65`):**
- 5 agents all completed without exceptions
- Build agent produced "I'm ready to help" (5.53s, 145 tokens)
- Validator reported being blocked and unable to validate
- `pipeline_complete.published_status: "completed"` — **incorrectly marked as full success**
- Header badge shows **"Done"** (green) — should show Degraded or Failed
- Deliverable: validator's diagnostic markdown named `output.html`
- `deliverable_mimetype: "text/markdown"` for a file named `output.html` — filename/mimetype mismatch

**Observed example 3 (user-stories custom workflow, run `e2903536`):**
- 6 agents all completed without exceptions
- Estimator agent produced a placeholder (5.87s, 293 tokens)
- Compiler adapted but silently dropped the SDK epic
- `pipeline_complete.published_status: "completed"` — incorrectly marked as full success

### Expected

When any agent in a custom workflow pipeline produces only placeholder/conversational output (indicating it received no context or tools), the run should be marked as **degraded** or **failed** — not completed. The deliverable filename and mimetype should match. The user should see a clear indication that the pipeline did not produce the intended output.

### Actual

All three runs show `published_status: "completed"` (or at best `"degraded"` in one case) with a green "Done" badge, regardless of whether the pipeline actually produced its intended deliverable. The engine marks a run as complete based solely on whether agents exited without raising exceptions — it has no quality check on output content, no filename/mimetype consistency check, and no check for whether agents with very low token counts (5–10s, 100–300 tokens) actually did meaningful work.

### Root Cause (technical)

The engine's `_unrecovered_agents` set only captures agents that raised an exception. An agent that exits cleanly with a 5-second "I'm ready to help" response is counted as a successful completion. With all agents completing without exception, `_unrecovered_agents` is empty → `pipeline_complete` carries `published_status: "completed"`.

The filename/mimetype mismatch (`output.html` with `text/markdown`) is also not caught — the deliverable resolver names the file based on the declared deliverable spec without verifying the content type matches.

### Log Evidence

```
Prototype custom workflow (7b00ac65):
  pipeline_complete.agents_completed: 5
  pipeline_complete.agents_total: 5
  pipeline_complete.published_status: "completed"   ← wrong
  pipeline_complete.deliverable_filename: "output.html"
  pipeline_complete.deliverable_mimetype: "text/markdown"  ← mismatch
  final_output: "Blocked — cannot complete validation..."

User-stories custom workflow (e2903536):
  pipeline_complete.agents_completed: 6
  pipeline_complete.agents_total: 6
  pipeline_complete.published_status: "completed"   ← wrong
  deliverable_filename: "output.md"
  deliverable_mimetype: "text/markdown"
```

### Files

- `backend/agents/execution_engine/engine.py` — `_unrecovered_agents` logic: exception-only gate, no output-quality check
- `backend/agents/execution_engine/engine.py` — deliverable resolver: no filename/mimetype consistency validation
- `backend/agents/execution_engine/engine.py` — `_check_artifact_fallback`: writes any content as artifact regardless of quality

<a id="qa-ps-028"></a>

## QA-PS-028 — Custom workflow compilation/aggregation agent silently drops upstream content without flagging the omission in the final output

- **Page:** Custom workflow run — Steps tab, any compilation or aggregation agent; Preview tab; Files tab
- **Route:** /create/custom and /runs/{id}
- **Severity:** High
- **Found by:** PS
- **Found at:** 2026-09-17
- **User:** qa-admin@flowinqa.com

### Reproduction

1. Sign in as `qa-admin@flowinqa.com`
2. Build a custom workflow where a final aggregation/compilation agent is expected to combine the outputs of multiple upstream agents into a single deliverable (e.g. a backlog compiler, a doc assembler, a report generator)
3. Run the workflow — ensure one or more upstream agents either produced incomplete output or had their files missing (as occurs in any custom workflow due to QA-PS-019)
4. After the run completes with `published_status: "completed"`, open the **Files tab** and **Preview tab**
5. Read the final output and compare it against the list of upstream agents' outputs

**Observed example (user-stories custom workflow, run `e2903536`):**
- `epic-architect` (step 2) produced **4 epics**: Core Authentication, Token Management, Audit & Compliance, **SDK Integration Layer** (4 stories: Node.js SDK, Mobile SDK, Web SDK, Documentation)
- `story-estimator` (step 3) produced placeholder output (QA-PS-022)
- `nfr-specialist` (step 4) produced 4 NFR stories
- `backlog-reviewer` (step 5) reviewed the backlog and confirmed SDK stories were valid
- `backlog-compiler` (step 6): explicitly stated *"I'll compile all the agent outputs"* then produced a final backlog containing:
  - Core Authentication — ✅ present (expanded with reviewer additions)
  - Token Management — ✅ present (expanded)
  - Audit & Compliance — ✅ present (partial)
  - Non-Functional Requirements — ✅ present (from nfr-specialist)
  - **SDK Integration Layer — ❌ entirely absent (4 stories silently dropped)**
- The compiler's own summary stated "Total Epics: 4, Total Stories: 18" — the numbers matched what was produced, but gave no indication that the SDK epic was missing
- `pipeline_complete.published_status: "completed"` — run marked as full success

### Expected

When a compilation/aggregation agent in a custom workflow produces a final output that omits content present in upstream agents' outputs, it either:
1. Includes all upstream content in the final compiled output, or
2. Explicitly flags what was omitted and why (e.g. "SDK Integration Layer epic was not included because the estimator's output was incomplete")

The run status should reflect that the deliverable is partial — `published_status: "degraded"` rather than `"completed"`.

### Actual

The compilation agent silently drops entire sections of upstream content without any mention of the omission. The final output summary counts only what was included, giving the impression the output is complete. The run is marked as fully completed. The user has no way to know that content they expected to be in the deliverable was silently dropped.

This is systemic to any custom workflow where:
- A compilation/aggregation agent is the final step
- One or more upstream agents produced incomplete or missing content (which is always the case in custom workflows due to QA-PS-019/022)
- The compiler fills in what it can from available context and omits the rest without flagging it

### Root Cause (technical)

The compilation agent's LLM has no structural contract requiring it to account for every upstream input. When it encounters a missing or incomplete upstream file, it adapts by working with what is available and silently substituting or omitting the missing content. The engine has no post-completion check comparing the compiler's output against the declared upstream sources — it only checks that the agent exited without raising an exception (QA-PS-022 structural gap).

Additionally, because QA-PS-019 prevents any upstream agent from writing named files, the compiler must read from engine-reserved `.agents/NN-agent-id.md` paths. If any of those files contain placeholder text (from QA-PS-022), the compiler may interpret the placeholder as "that section has no content" and omit it entirely rather than reporting the gap.

### Log Evidence

```
agent_complete for backlog-compiler (e2903536):
  duration: 43.9s
  output_length: 19581
  output_tokens: 5093
  input_tokens: 18824   ← notably lower than nfr-specialist (57K) and reviewer (47K)
                           suggesting not all upstream content was in context

pipeline_complete:
  agents_completed: 6
  agents_total: 6
  published_status: "completed"   ← wrong — SDK epic silently dropped
  deliverable_filename: "output.md"
  deliverable_mimetype: "text/markdown"

epic-architect output (.agents/02-epic-architect.md):
  Confirmed 4 epics including SDK Integration Layer with 4 stories

backlog-compiler final output (.agents/06-backlog-compiler.md):
  4 epics present — SDK Integration Layer absent
  Summary: "Total Epics: 4, Total Stories: 18" — no mention of omission
```

### Files

- `backend/agents/execution_engine/engine.py` — `_run_agent`: no post-completion check comparing output against declared upstream sources
- `backend/agents/execution_engine/engine.py` — `_unrecovered_agents`: exception-only gate, no content-completeness check
- `backend/agents/execution_engine/engine.py` — `_apply_selections` missing `tools` overlay (QA-PS-019 root): upstream agents never write named files, so compiler reads from engine-reserved paths where placeholder content may silently substitute real content

<a id="qa-ps-029"></a>

## QA-PS-029 — Selecting an older version (v1) in the version dropdown shows "Loading v{n}…" indefinitely — no preview is ever rendered

- **Page:** Run detail — Preview tab, version dropdown
- **Route:** /runs/{id}
- **Severity:** High
- **Found by:** PS
- **Found at:** 2026-09-17
- **User:** qa-admin@flowinqa.com

### Reproduction

1. Sign in as `qa-admin@flowinqa.com`
2. Open any completed run that has at least one revision — any workflow type (PPT, Prototype, User Stories, or any custom workflow with a revision). For example: `/runs/d0ef2201-c0b1-4848-b048-d2b05c98c721` (PPT Revision)
3. Click the version dropdown at the top and select **v1** (the parent run's version)
4. Observe the Preview tab
5. Open browser DevTools Console

### Expected

Selecting v1 switches the Preview tab to show the parent run's deliverable — the output as it existed before any revision was applied. The amber "Viewing v1 (read-only)" banner appears and the preview renders the parent run's content.

### Actual

The Preview tab shows the amber "Viewing v1 (read-only)" banner and the read-only notice, but the preview area shows **"Loading v1…"** indefinitely — the content never renders. The browser console logs repeated 404 errors:

```
[version-menu] ref deliverable fetch failed Error: 404: could not read <deliverable-filename>
  at getRunSandboxFile (src/lib/api.ts:1221:11)
  at PreviewPanel.tsx:1266
```

The error fires multiple times in rapid succession. This affects all workflow types — PPT, User Stories, Prototype, and custom workflows.

### Root Cause (technical)

The ref-scoped preview path (`RefVersionPreview`) fires when `sandboxSelectedRef` is set. It requires `deliverableFile` — a real on-disk filename — to call `getRunSandboxFile(token, runId, deliverableFile, "v1")`.

`deliverableFile` is resolved by `resolveRunDeliverable` in `api.ts` which has **no `ref` parameter** (open issue ISS-665, confirmed by a failing test at `api.resolveRunDeliverableRef.test.ts`). It always calls `getRunSandbox(token, runId)` with **no ref** — reading from the live workspace tree at HEAD, not from the v1 git tag.

For workflows where the deliverable filename at HEAD differs from the filename at the selected tag (or the file simply didn't exist at v1), `getRunSandboxFile(..., "v1")` returns 404. Additionally, for `ppt`/`ppt_revision` workflows that use `strategy: ppt` (streamed output, no file written to disk), `deliverableFile` may resolve to null entirely — the `getRunSandboxFile` effect never fires and `refDeliverableContent` stays null, leaving the preview stuck on "Loading v{n}…" forever.

### Browser / Log Signals

```
Console: [version-menu] ref deliverable fetch failed Error: 404: could not read <filename> (×5–6)
Network: GET /api/runs/{id}/sandbox/file?path=<filename>&ref=v1 → 404
Preview: "Loading v1…" spinner — never resolves
```

### Files

- `frontend/src/lib/api.ts` — `resolveRunDeliverable` (line ~1175): no `ref` parameter, always queries live workspace; failing test at `api.resolveRunDeliverableRef.test.ts` (ISS-665)
- `frontend/src/components/preview/PreviewPanel.tsx` — `refDeliverableContent` effect (line ~1257): calls `getRunSandboxFile` with `deliverableFile` resolved from the live tree
- `backend/agents/workflows/ppt/workflow.yaml` and `ppt_revision/workflow.yaml` — `deliverable.strategy: ppt` (no file written to sandbox — additional failure mode for PPT-type runs)

---

<a id="qa-ps-030"></a>

## QA-PS-030 — Selecting an older version (v2 or vN) shows the parent run's deliverable content instead of that version's own content

- **Page:** Run detail — Preview tab, version dropdown
- **Route:** /runs/{id}
- **Severity:** High
- **Found by:** PS
- **Found at:** 2026-09-17
- **User:** qa-admin@flowinqa.com

### Reproduction

1. Sign in as `qa-admin@flowinqa.com`
2. Open any completed run with at least one revision — any workflow type (PPT, Prototype, User Stories). For example: `/runs/d0ef2201-c0b1-4848-b048-d2b05c98c721`
3. Ensure you are on **Latest (live)** first — confirm the preview shows the most recent revision's content
4. Click the version dropdown and select a non-latest version, e.g. **v2**
5. Observe what is rendered in the Preview tab

### Expected

Selecting v2 renders the deliverable produced by the v2 run — i.e. that specific revision's output. If v2 added "By Prateek / Hexaware" to the title page, that author text should be visible in the v2 preview.

### Actual

The Preview tab renders the **parent run's (v1) deliverable content** — the original output before any revision. For the PPT Revision example, v2 was the revision that added author "Prateek" and company "Hexawa", but selecting v2 shows the unrevised "Six Thinking Hats / By Edward de Bono" deck with no author attribution.

Selecting **Latest (live)** correctly shows the most recent content (with "Presented by Prateek / Hexaware"). Only v2 and other intermediate versions show wrong content.

This affects all revision workflow types — PPT Revision, Prototype Revision, and any other revision run where the deliverable content for non-latest versions is incorrectly stored or resolved.

### Root Cause (technical)

When a version is selected, `handleVersionMenuSelect(tag)` calls `handleSelectVersion(member.id)` → fetches `GET /api/runs/{vNMemberId}` → sets `viewingVersion`. The preview content comes from `effPptContent = viewingVersion?.content` (or equivalent for other workflow types).

The `content` field on `viewingVersion` comes from `versionViewFrom(run)` which reads the run's stored `output` field from the API response. For revision runs, the stored `output` in the DB row appears to contain the **parent run's deliverable** (the "prior output" passed to the revision agent as context), not the **revised deliverable** the revision agent produced. The revision agent's actual output is in `ctx.last_streamed` / `pipeline_complete.final_output` but is not correctly persisted to the `output` column for the revision run's DB row.

### Browser / Log Signals

```
Version chip: "Viewing v2 · read-only"
Preview: shows parent run's content (e.g. "Six Thinking Hats / By Edward de Bono" with no author)
Latest (live): correctly shows revised content ("Presented by Prateek / Hexaware")
Network: GET /api/runs/{v2MemberId} → 200, but response output field contains parent's content
```

### Files

- `frontend/src/components/preview/PreviewPanel.tsx` — `effPptContent = overrideActive && renderType === "ppt" ? overrideContent : pptContent` (line ~895); `overrideContent = viewingVersion?.content`
- `backend/app/api/runs.py` — `GET /api/runs/{id}` / `WorkflowRunResponse`: check how `output` / `deliverable_content` is populated for revision-type runs
- `backend/agents/execution_engine/engine.py` — how revision workflow `final_output` is persisted to the run's `output` column

---

<a id="qa-ps-031"></a>

## QA-PS-031 — Selecting a non-latest version shows inconsistent data across tabs — Preview shows wrong version's content while Steps shows the correct version's agents

- **Page:** Run detail — Preview tab + Steps tab, version dropdown
- **Route:** /runs/{id}
- **Severity:** High
- **Found by:** PS
- **Found at:** 2026-09-17
- **User:** qa-admin@flowinqa.com

### Reproduction

1. Sign in as `qa-admin@flowinqa.com`
2. Open any completed run with at least one revision — any workflow type (PPT, Prototype, User Stories). For example: `/runs/d0ef2201-c0b1-4848-b048-d2b05c98c721`
3. Click the version dropdown and select **v2** (or any non-latest version)
4. Look at the **Preview tab**, **Steps tab**, and **left panel** simultaneously

### Expected

All surfaces consistently show data belonging to the selected version:
- Preview: that version's deliverable
- Steps: that version's agents and their outputs
- Left panel: that version's run metadata (brief, token count, timestamps)

### Actual

The data is split across different versions. Using the PPT Revision example with v2 selected:
- **Preview tab**: shows v1 (parent) content — original presentation without revision changes (QA-PS-030 root cause)
- **Left panel**: shows v2 (revision) metadata — "Revision: Add author name 'Prateek'…"
- **Steps tab**: shows v2's revision agent ("Deck Revision Agent · Targeted HTML Deck Edits · DONE")
- **Run summary**: shows v2's data — "1 agent · six-thinking-hats.html"

The user sees the revision's agent details alongside the pre-revision presentation. The steps say the agent made changes that are not visible in the preview — the two surfaces directly contradict each other on the same screen.

This affects all workflow types with revisions. The specific split depends on which surface uses `viewingVersion.content` vs `viewingVersion.agents` — both come from the same `viewingVersion` object, but content resolution for revision runs is broken (QA-PS-030).

### Browser / Log Signals

```
Version chip: "Viewing v2 · read-only"
Left panel: shows revision run metadata (correct for v2)
Steps tab: shows revision agent (correct for v2)
Preview: shows parent run's deliverable (wrong — should show v2's revised content)
```

### Files

- `frontend/src/components/preview/PreviewPanel.tsx` — `effPptContent` vs `effAgents` derivation (lines ~895–900): both derive from `viewingVersion` but content resolution differs for revision runs (QA-PS-030 root)
- Backend run output storage for revision runs (same root cause as QA-PS-030)

---

<a id="qa-ps-032"></a>

## QA-PS-032 — Workspace tab shows 0 B for all file sizes when any version other than Latest is selected

- **Page:** Run detail — Workspace tab, version dropdown
- **Route:** /runs/{id}/workspace
- **Severity:** Medium
- **Found by:** PS
- **Found at:** 2026-09-17
- **User:** qa-admin@flowinqa.com

### Reproduction

1. Sign in as `qa-admin@flowinqa.com`
2. Open the PPT Revision run at `/runs/d0ef2201-c0b1-4848-b048-d2b05c98c721`
3. Click the version dropdown and select **v2** (or **v1**)
4. Click the **Workspace** tab
5. Observe the file size column for every file listed

### Expected

Each file in the Workspace tab shows its actual size (e.g. `18.6 KB`, `6.3 KB`, `23.4 KB`) — the same accurate sizes visible when "Latest (live)" is selected.

### Actual

Every file in the Workspace tab shows **0 B** for its size when any versioned ref (v1, v2) is selected. The file names, types and deliverable markers are correct — only the sizes are wrong.

The screenshot shows the v2 workspace listing with files: `.family.lock`, `brief-spec.md`, `presentation.html`, `logs.jsonl`, `presentation.pptx`, `summary.md`, `.gitignore`, `PLANNER.md` — all showing **0 B**.

### Root Cause (technical)

When a ref is selected, `SandboxTab` passes `selectedRef` to `getRunSandbox(token, runId, ref)` → `GET /api/runs/{id}/sandbox?ref=v2`. The backend takes the ref-scoped code path in `list_sandbox` (run_files.py ~line 700), which calls `sandbox.list_files_at_ref(safe_ref)` — this uses `git ls-tree -r <ref>` to enumerate files at that tag.

`git ls-tree` returns only file paths, not byte sizes. The backend synthesizes entries with `"size": 0` hardcoded for every file:

```python
files_payload = [
    {
        "path": p,
        "size": 0,  # ← hardcoded — git ls-tree gives no sizes
        ...
    }
    for p in raw_paths ...
]
```

Getting real sizes would require `git cat-file --batch-check` for each path. The frontend `SandboxTab` renders `formatBytes(file.size)` → `"0 B"` for every file.

The live workspace path (no ref) calls `sandbox.list_files()` which reads from the actual filesystem and returns real sizes.

### Browser / Log Signals

```
Network: GET /api/runs/{id}/sandbox?ref=v2 → 200, all files have "size": 0
Workspace tab: all file sizes show "0 B"
Network: GET /api/runs/{id}/sandbox (no ref) → 200, files have real sizes (18.6 KB etc.)
```

### Files

- `backend/app/api/run_files.py` — `list_sandbox` handler, ref-scoped path (line ~700): `"size": 0` hardcoded
- `frontend/src/components/SandboxTab.tsx` — `formatBytes(file.size)` rendering

---

<a id="qa-ps-033"></a>

## QA-PS-033 — Steps, agents and agent outputs do not switch to the selected version when the family member record has no git_tag populated

- **Page:** Run detail — Steps tab, version dropdown
- **Route:** /runs/{id}
- **Severity:** High
- **Found by:** PS
- **Found at:** 2026-09-17
- **User:** qa-admin@flowinqa.com

### Reproduction

1. Sign in as `qa-admin@flowinqa.com`
2. Open any run that is part of a revision family where the family member DB records do not have `git_tag` populated (this may affect older runs created before git tagging was added to the revision flow)
3. Click the version dropdown and select any version (e.g. v1)
4. Click the **Steps** tab
5. Observe which agents are shown

### Expected

Selecting v1 in the version dropdown switches the Steps tab (and all other tabs — agents, agent outputs, pipeline state) to show the data belonging to v1: the agents that ran for the parent run, their outputs, and the parent run's pipeline state.

### Actual

The Steps tab continues to show the **latest (live) run's** agents, outputs, and pipeline state — even though the version chip shows "Viewing v1 (read-only)". The Workspace tab correctly switches to the v1 ref, but Steps, agents and agent outputs are frozen on the live run's data.

This is the same symptom as the original QA-EX-001 bug (which was fixed for the general case) but persists when the family member's `git_tag` field is not populated in the DB.

### Root Cause (technical)

`handleVersionMenuSelect` in `PreviewPanel.tsx` resolves the selected tag to a family member via:
```ts
const member = sortedMembers.find((m) => m.git_tag === tag);
```

If `member` is `undefined` (no member has `git_tag === "v1"`), the fallback branch fires:
```ts
} else {
  // Tag not yet on any member (in-progress run, pre-tagging).
  intendedSandboxRef.current = null;
  setSandboxSelectedRef(tag);  // workspace-only; Steps stays live
}
```

`handleSelectVersion` is never called → `viewingVersion` is never set → `effAgents`, `effPipelineState`, `effAgentOutputs` all fall back to the live run's props → Steps shows the live run's agents regardless of which version the user selected.

The fix path (populating `git_tag` on all family member records) requires a backfill for runs created before the column was added, or a fallback that resolves the tag to a member by `revision_index` when `git_tag` is absent.

### Browser / Log Signals

```
Version chip: "Viewing v1 · read-only"
Workspace tab: correctly shows v1's sandbox files
Steps tab: shows latest run's agents (not v1's agents)
Left panel: shows latest run's agents and pipeline state
Network: no GET /api/runs/{v1MemberId} fetch visible — handleSelectVersion never called
```

### Files

- `frontend/src/components/preview/PreviewPanel.tsx` — `handleVersionMenuSelect` fallback branch (line ~820): `setSandboxSelectedRef(tag)` only, no `handleSelectVersion`
- `backend/app/api/runs.py` — `GET /api/runs/{id}/family`: check whether `git_tag` is populated on member records
- Database: `workflow_runs.git_tag` column — backfill needed for older revision family members

<a id="qa-ps-034"></a>

## QA-PS-034 — Run history page stuck at 50 runs — infinite scroll and "Load more" do not load additional runs, and workflow filter tabs do not load more

- **Page:** Run history list
- **Route:** /runs
- **Severity:** High
- **Found by:** PS
- **Found at:** 2026-09-17
- **User:** qa-admin@flowinqa.com

### Reproduction

1. Sign in as `qa-admin@flowinqa.com`
2. Go to `/runs` (My Workflows / Run History)
3. Observe the page header — it reads "Showing 50 of 299 runs — scroll down to load more"
4. Scroll to the bottom of the list — observe the **"Load more"** button
5. Click **"Load more"** — observe whether additional runs are loaded
6. Alternatively, scroll down past the last visible run — observe whether infinite scroll triggers
7. Click any workflow filter tab (e.g. **"User Stories 8"**, **"Prototype 12"**) — observe the run count shown

### Expected

- Clicking **"Load more"** appends the next batch of runs (e.g. runs 51–100) to the list
- Scrolling past the last visible run automatically triggers loading of the next page (infinite scroll)
- After loading, the counter updates (e.g. "Showing 100 of 299 runs")
- Clicking a filter tab (e.g. "User Stories") shows all runs of that type — if there are more than 50 user story runs, additional ones load on scroll/click

### Actual

- The page loads and correctly shows the first 50 of 299 runs with the "scroll down to load more" hint
- Scrolling to the bottom shows the "Load more" button but **clicking it does nothing** — no additional runs appear, the list stays at 50 entries
- Infinite scroll also does not trigger — scrolling past the last run shows no loading indicator and no new runs
- The total count in the header continues to show 299 but only 50 runs are accessible
- Clicking a workflow filter tab (e.g. "User Stories 8") correctly filters the visible runs to that type but still only shows the first 50 matching runs from the already-loaded page — runs 51+ are never fetched even if the filter would match them
- The page is effectively capped at 50 runs with no way to access the remaining 249

### Browser / Log Signals

```
Console: not checked
Network: no additional GET /api/runs?... request fires when Load more is clicked or on scroll
Header: "Showing 50 of 299 runs — scroll down to load more" — counter never updates
Load more button: visible but click has no effect
```

### Notes

The screenshot shows the page at `/runs` with 299 total runs, 50 shown, and a visible "Load more" button at the bottom of the list. The filter tabs show counts: User Stories 8, Presentation 7, Prototype 12, Custom 4 — these counts are derived from the already-loaded 50 runs, not the full 299, so the filter tabs also undercount the actual totals.

### Files

- `frontend/src/app/[...]/runs/` or equivalent run history page component — "Load more" click handler and infinite scroll observer
- `frontend/src/` — run list fetch / pagination logic (check `limit`, `offset`, or cursor-based pagination)
- `backend/app/api/runs.py` — `GET /api/runs` endpoint: pagination parameters (`limit`, `offset`)

<a id="qa-ps-035"></a>

## QA-PS-035 — Account settings page makes redundant duplicate API calls and fetches run history and workflow data that are not needed, causing slow UI rendering

- **Page:** Account Settings — all tabs (Profile, AI Model, Usage & Limits, Constitution, Security)
- **Route:** /settings/profile (and /settings/*)
- **Severity:** Medium
- **Found by:** PS
- **Found at:** 2026-09-17
- **User:** qa-admin@flowinqa.com

### Reproduction

1. Sign in as `qa-admin@flowinqa.com`
2. Open browser DevTools → Network tab → filter to **Fetch/XHR**
3. Click **My Workflows** in the nav → then click the profile/avatar icon or navigate to `/settings/profile`
4. Observe all XHR requests that fire on page load
5. Also click any other settings tab (AI Model, Usage & Limits, Constitution, Security) and observe the requests

### Expected

Opening the Account Settings page fires only the API requests needed to display settings content:
- `GET /api/me` — once, to get the current user profile
- `GET /api/preferences` — once, to get user preferences
- `GET /api/capabilities` — once, to populate the model picker if needed

No run history, no workflow catalog. Each endpoint called exactly once and its response shared across all components that need it.

### Actual

Opening `/settings/profile` fires **11 requests** in under 1 second:

| Request | Count | Size | Problem |
|---------|-------|------|---------|
| `GET /api/me` | **4×** | 0.4 KB each | Same data fetched 4 times — 3 redundant calls |
| `GET /api/preferences` | **2×** | 2.1 KB each | Same data fetched twice — 1 redundant call |
| `GET /api/capabilities` | **2×** | 23.6 KB each | Same data fetched twice — 1 redundant call (47.2 KB wasted) |
| `GET /api/runs?limit=50` | **1×** | 37.2 KB | **Not needed on settings** — full run history, 37 KB wasted |
| `GET /api/workflows` | **1×** | 22.6 KB | **Not needed on settings** — workflow catalog, 22 KB wasted |

Total: 11 requests, 117 KB transferred. Should be at most 3–4 requests, ~30 KB.

Two distinct problems:

**Problem 1 — Redundant duplicate calls (same endpoint fired multiple times):**
`/api/me` is called 4 times, `/api/preferences` twice, and `/api/capabilities` twice on the same page load. Multiple components in the settings page tree are each independently calling the same endpoints without sharing the response. The data does not change between calls — they should be fetched once at the layout/provider level and passed down or accessed via a shared cache.

**Problem 2 — Wrong-page requests (data not needed on settings):**
`GET /api/runs?limit=50` (37.2 KB — full run history) and `GET /api/workflows` (22.6 KB — workflow catalog) fire on every settings page load. Neither run history nor the workflow catalog is displayed or used anywhere in the Account Settings UI. These appear to be fired by a shared layout component or provider that initializes data for the run history page and mounts unconditionally on all routes.

The combined effect: the settings page is slow to render because it waits for 117 KB of mostly-redundant network traffic — including 60 KB of data (runs + workflows) that is never used on this page.

### Browser / Log Signals

```
Network (Fetch/XHR) on /settings/profile load:
  GET /api/me           × 4  (0.4 KB × 4 = 1.6 KB)
  GET /api/preferences  × 2  (2.1 KB × 2 = 4.2 KB)
  GET /api/capabilities × 2  (23.6 KB × 2 = 47.2 KB)
  GET /api/runs?limit=50 × 1 (37.2 KB)
  GET /api/workflows    × 1  (22.6 KB)
Total: 11 requests, 117 KB transferred
```

### Files

- `frontend/src/app/settings/` — settings page components: check which components independently call `getMe`, `getPreferences`, `getCapabilities`
- `frontend/src/` — shared layout or provider components (e.g. `DashboardLayout`, `RunConnectionProvider`, or similar) that fetch `runs` and `workflows` unconditionally on every route
- `frontend/src/lib/api.ts` — `getMe`, `getPreferences`, `getCapabilities` — check if results are cached/deduplicated or called fresh by each consumer

<a id="qa-ps-036"></a>

## QA-PS-036 — Analytics page fires 17 API requests with heavy duplication and fetches run history and workflow data not needed on analytics, causing slow page load

- **Page:** Analytics
- **Route:** /analytics
- **Severity:** Medium
- **Found by:** PS
- **Found at:** 2026-09-17
- **User:** qa-admin@flowinqa.com

### Reproduction

1. Sign in as `qa-admin@flowinqa.com`
2. Open browser DevTools → Network tab → filter to **Fetch/XHR**
3. Navigate to `/analytics`
4. Observe all XHR requests that fire on page load

### Expected

Opening the Analytics page fires only the requests needed to display analytics content:
- `GET /api/analytics/summary?range=30d` — once, to get the token/cost summary
- `GET /api/me` — once, to identify the current user
- `GET /api/capabilities` — once, to populate the model filter dropdown

No run history, no workflow catalog. Each endpoint called exactly once, responses shared across all components.

### Actual

Opening `/analytics` fires **17 requests** in under 2.5 seconds totalling **204 KB transferred**:

| Request | Count | Size | Problem |
|---------|-------|------|---------|
| `GET /api/analytics/summary?range=30d` | **4×** | 9.2 KB × 4 = **36.8 KB** | Same analytics data fetched 4 times |
| `GET /api/preferences` | **4×** | 2.1 KB × 4 = **8.4 KB** | Same user prefs fetched 4 times |
| `GET /api/capabilities` | **4×** | 23.6 KB × 4 = **94.4 KB** | Same capability catalog fetched 4 times — 70 KB wasted |
| `GET /api/me` | **2×** | 0.4 KB × 2 = **0.8 KB** | Duplicate — 1 wasted call |
| `GET /api/runs?limit=50` | **1×** | **37.2 KB** | **Not needed on analytics** |
| `GET /api/workflows` | **1×** | **22.6 KB** | **Not needed on analytics** |

**Total: 17 requests, 204 KB. Should be ~3 requests, ~35 KB.**

Two distinct problems:

**Problem 1 — Heavy duplication of analytics and shared data calls:**
`/api/analytics/summary?range=30d` fires 4 times, `/api/capabilities` fires 4 times, `/api/preferences` fires 4 times, `/api/me` fires twice. Each call returns identical data. Multiple components on the analytics page independently fetch the same endpoints instead of sharing a single response. The `capabilities` response alone is 23.6 KB — fetching it 4 times wastes 70 KB of bandwidth and adds ~300ms of blocking network time per duplicate.

**Problem 2 — Wrong-page fetches (same issue as QA-PS-035):**
`GET /api/runs?limit=50` (37.2 KB) and `GET /api/workflows` (22.6 KB) fire on the analytics page even though neither run history nor the workflow catalog is displayed or used anywhere on `/analytics`. These 60 KB of requests come from the same shared layout/provider component identified in QA-PS-035 that mounts unconditionally on all routes.

The combined overhead means 204 KB is transferred to render a page that needs ~35 KB of data. The cascade of parallel duplicates (visible in the waterfall — all 17 requests fire within the same 2.5-second window) causes the analytics metrics to appear slowly as the page waits for multiple rounds of identical responses.

### Browser / Log Signals

```
Network (Fetch/XHR) on /analytics load:
  GET /api/analytics/summary?range=30d × 4  (9.2 KB × 4 = 36.8 KB)
  GET /api/preferences                × 4  (2.1 KB × 4 = 8.4 KB)
  GET /api/capabilities               × 4  (23.6 KB × 4 = 94.4 KB)
  GET /api/me                         × 2  (0.4 KB × 2 = 0.8 KB)
  GET /api/runs?limit=50              × 1  (37.2 KB — wrong page)
  GET /api/workflows                  × 1  (22.6 KB — wrong page)
Total: 17 requests, 204 KB transferred
```

### Notes

This is the same two-problem pattern as QA-PS-035 (Account Settings) but more severe — the duplication count is higher (4× instead of 2–4×) and the analytics summary endpoint itself is duplicated 4 times. Both bugs share the same root causes:
1. Components independently fetching shared data without a shared cache or provider
2. A layout-level component fetching `runs` and `workflows` unconditionally on every route

### Files

- `frontend/src/app/analytics/` — analytics page components: check which components independently call `getAnalyticsSummary`, `getCapabilities`, `getPreferences`, `getMe`
- `frontend/src/` — shared layout or provider that fetches `runs?limit=50` and `workflows` unconditionally (same file as QA-PS-035)
- `frontend/src/lib/api.ts` — `getAnalyticsSummary`, `getCapabilities` — check if results are cached/deduplicated or called fresh per component

<a id="qa-ps-037"></a>

## QA-PS-037 — Run history page calls GET /api/runs?limit=50 six times on load — 5 redundant fetches waste 186 KB and cause slow content rendering

- **Page:** Run history list
- **Route:** /runs
- **Severity:** High
- **Found by:** PS
- **Found at:** 2026-09-17
- **User:** qa-admin@flowinqa.com

### Reproduction

1. Sign in as `qa-admin@flowinqa.com`
2. Open browser DevTools → Network tab → filter to **Fetch/XHR**
3. Navigate to `/runs` (My Workflows / Run History)
4. Observe all XHR requests that fire on page load

### Expected

Opening the Run History page fires the minimum necessary requests:
- `GET /api/runs?limit=50` — **once**, to load the first page of runs
- `GET /api/workflows` — once, to populate the workflow type filter tabs
- `GET /api/me` — once, to identify the current user

Total: ~3 requests, ~60 KB.

### Actual

Opening `/runs` fires **10 requests** totalling **250 KB transferred**:

| Request | Count | Size | Problem |
|---------|-------|------|---------|
| `GET /api/runs?limit=50` | **6×** | 37.2 KB × 6 = **223.2 KB** | Same run list fetched 6 times — 5 redundant calls |
| `GET /api/me` | **2×** | 0.4 KB × 2 = 0.8 KB | Duplicate — 1 wasted call |
| `GET /api/workflows` | **1×** | 22.6 KB | Expected |
| `runs?_rsc=1seny` (page nav) | **1×** | 3.5 KB | Expected |

**`GET /api/runs?limit=50` is called 6 times in parallel within ~200ms.** Each call returns the identical 37.2 KB payload — the same 50 runs. Five of the six calls are completely redundant, wasting **186 KB** of bandwidth and adding up to **181ms** of parallel network time for data the page already has from the first call.

`GET /api/me` is also duplicated — fired twice.

The result: the run list is slow to render because the page is processing 6 identical 37.2 KB responses, and the list contents may flicker or re-render up to 6 times as each response resolves.

### Root Cause (technical)

Multiple components on the run history page are each independently calling the same `getRuns(limit=50)` function without a shared fetch or deduplication layer. Likely causes:
- The page component, the filter tab component, the sort controls, and possibly layout-level providers all independently fetch the run list on mount
- No request deduplication or shared state layer exists to prevent parallel identical calls
- `GET /api/me` is called by at least two separate components that each need the current user identity

This is the most severe instance of the same duplication pattern seen in QA-PS-035 (settings) and QA-PS-036 (analytics) — but worse because `runs?limit=50` is 37 KB per call and fires 6 times instead of 2–4.

### Browser / Log Signals

```
Network (Fetch/XHR) on /runs load:
  GET /api/runs?limit=50  × 6  (37.2 KB × 6 = 223.2 KB — 5 redundant)
  GET /api/me             × 2  (0.4 KB × 2 = 0.8 KB — 1 redundant)
  GET /api/workflows      × 1  (22.6 KB — expected)
  runs?_rsc=1seny         × 1  (3.5 KB — expected)
Total: 10 requests, 250 KB transferred
```

### Files

- `frontend/src/app/runs/` or equivalent run history page — identify which components independently call `getRuns` or `getWorkflowRuns`
- `frontend/src/` — shared layout or provider components that may also call `runs?limit=50` unconditionally
- `frontend/src/lib/api.ts` — `getRuns` / `getWorkflowRuns`: no deduplication or cache layer

<a id="qa-ps-038"></a>

## QA-PS-038 — Opening a run detail page from history fires ~40-50 API requests — runs?limit=50 called 12+ times and durable replay events trigger live-run refetch logic causing cascading redundant calls

- **Page:** Run detail page (opened from run history)
- **Route:** /runs/{id}
- **Severity:** High
- **Found by:** PS
- **Found at:** 2026-09-17
- **User:** qa-admin@flowinqa.com

### Reproduction

1. Sign in as `qa-admin@flowinqa.com`
2. Open browser DevTools → Network tab → filter to **Fetch/XHR**
3. Go to `/runs` (Run History)
4. Click on any completed run to open its detail page
5. Observe all XHR requests that fire — count the `runs?limit=50` calls and total request count

### Expected

Opening a completed run's detail page fires only what is needed to display it:
- `GET /api/runs/{id}` — once, to fetch the run's details
- `GET /api/runs/{id}/events` — once, to replay the durable event log for pipeline state + chat
- `GET /api/runs/{id}/family` — once, to build the revision family timeline
- `GET /api/runs?limit=50` — once at mount, to populate the recents list/badge

Total: ~4–6 requests for a simple run, ~8–10 for a revision family.

### Actual

Opening a single completed run fires **~40–50 requests** including:

| Request | Count | Size | Problem |
|---------|-------|------|---------|
| `GET /api/runs?limit=50` | **12+ times** | 37.2 KB × 12+ = **446+ KB** | Same run list fetched 12+ times |
| `GET /api/runs/{id}/events` | **2×** | 3,877 KB × 2 = **7.7 MB** | Full SSE replay fetched twice |
| `GET /api/runs/{id}/family` | **2×** | 0.7 KB × 2 | Duplicate |
| `GET /api/runs/{id}/sandbox` | 1× | — | Expected |

Total observed: **40+ requests, 18 MB transferred** for a single completed run view.

### Root Cause (technical — two distinct problems)

**Problem 1 — `runs?limit=50` called 12+ times from 12 distinct call sites, all during durable replay of a completed run**

`page.tsx` contains 12 `getWorkflows(token, { limit: 50 })` call sites, all wired to `setRecentRuns`. These were designed to refresh the recents list/badge when SSE events arrive on a **live run** (status genuinely changes). But when a **completed** run is opened from history, `handleSelectWorkflowRun` replays all durable events through the same `handleWebSocketMessage` handler. The handler cannot distinguish a live SSE frame from a replayed historical event — so every event in the log that matches a handler triggers a `runs?limit=50` fetch:

```
pipeline_complete   → immediate refetch (page.tsx:1597)
pipeline_complete   → delayed refetch 2s later (page.tsx:1626)  ← KAN-120 race guard
questionnaire_ready → refetch (page.tsx:1996)
questionnaire_complete → refetch (page.tsx:2021)
review_gate_ready   → refetch (page.tsx:2059)
review_gate_approved → refetch (page.tsx:2089)
pipeline_failed     → refetch (page.tsx:1673)
pipeline_diverted   → refetch (page.tsx:1710)
pipeline_cancelled  → refetch (page.tsx:1759)
```

A typical run with plan → clarify → gate → approve → complete fires 5–6 of these → 5–6 page.tsx refetches.

**Plus the T38 cascade (`WorkflowHistory.tsx:248`):**
Each `setRecentRuns(newArray)` call in page.tsx creates a new array reference → triggers `WorkflowHistory`'s `useEffect([recentRuns])` → fires a **second independent** `getWorkflows(token, { limit: 50 })`. This doubles every page.tsx refetch: 6 page.tsx calls → 6 more WorkflowHistory calls = 12 total.

**Plus mount-time calls:**
- `page.tsx:968` — auth mount: 1 call
- `store/listenerMiddleware.ts:55` — `signedIn` action dispatches `fetchRecentRuns`: 1 more call
- `RunConnectionProvider.tsx:289` — `refreshLiveRuns` on boot: 1 call

Total for opening a completed run with review gate + clarify + complete: **12–15 `runs?limit=50` calls**.

**Problem 2 — `events?after=-0` fetched twice (7.7 MB)**

`handleSelectWorkflowRun` calls `getRunEvents(token, fullRun.id)` for the primary run (page.tsx:2879). For a run in a revision family, it also calls `getRunEvents` for each other family member in parallel (page.tsx:2968):

```typescript
const memberFrameArrays = await Promise.allSettled(
  otherMembers.map((m) => getRunEvents(currentToken, m.id))
);
```

A 2-member family (parent + 1 revision) fires 2× `getRunEvents`. Each call returns the full persisted event log — 3.8 MB for a large run = 7.7 MB total for a run family. This is by design for the revision transcript, but the size is significant.

**`RunConnectionProvider` also fires on tab focus:**
`RunConnectionProvider.tsx:336` fires `refreshLiveRuns()` (→ `runs?limit=50`) on every `visibilitychange` to visible and every `online` event — adding 1 more `runs?limit=50` per tab focus while the run detail is open.

### The core issue

The `handleWebSocketMessage` handler has no concept of "we are replaying historical events, not receiving live ones." All 12 SSE event → `setRecentRuns` refetch bindings fire unconditionally during durable replay of a completed run. For a live run where status changes, these refetches are justified. For a completed run opened from history, a run that terminated days ago will never change status again — none of the refetches serve any purpose.

### Browser / Log Signals

```
Network on opening completed run from history:
  runs?limit=50           × 12+  (37.2 KB × 12+ = 446+ KB)
  runs/{id}/events?after=-0 × 2  (3,877 KB × 2 = 7.75 MB)
  runs/{id}/family         × 2   (0.7 KB × 2)
  runs/{id}/sandbox        × 1   (expected)
Total: ~40-50 requests, ~18 MB transferred
```

### Files

- `frontend/src/app/[...view]/page.tsx` — 12 `getWorkflows` call sites inside `handleWebSocketMessage` (lines 1597, 1626, 1673, 1710, 1759, 1996, 2021, 2059, 2089, 4136, 968); `handleSelectWorkflowRun` (line ~2747) calling `getRunEvents` for each family member
- `frontend/src/components/history/WorkflowHistory.tsx` — T38 cascade effect (line 248): fires `getWorkflows` on every `recentRuns` reference change
- `frontend/src/providers/RunConnectionProvider.tsx` — `refreshLiveRuns` (line 289): fires `runs?limit=50` on boot, tab focus, and reconnect
- `frontend/src/store/listenerMiddleware.ts` — fires `fetchRecentRuns` on `signedIn` (parallel duplicate of page.tsx mount fetch)

<a id="qa-ps-039"></a>

## QA-PS-039 — Dashboard fires 10 API requests with analytics/summary called 4 times and runs?limit=50 called twice — 6 redundant fetches slow page rendering

- **Page:** Dashboard / Home
- **Route:** /dashboard
- **Severity:** Medium
- **Found by:** PS
- **Found at:** 2026-09-17
- **User:** qa-admin@flowinqa.com

### Reproduction

1. Sign in as `qa-admin@flowinqa.com`
2. Open browser DevTools → Network tab → filter to **Fetch/XHR**
3. Navigate to `/dashboard` (Home page)
4. Observe all XHR requests that fire on page load

### Expected

Opening the Dashboard fires only the requests needed to display its content:
- `GET /api/analytics/summary?range=all` — once, for the usage stats visible on the dashboard
- `GET /api/runs?limit=50` — once, for the "Jump back in" recents list
- `GET /api/workflows` — once, for the workflow catalog cards
- `GET /api/me` — once, to identify the current user

Total: 4 requests, ~74 KB.

### Actual

Opening `/dashboard` fires **10 requests** totalling **155 KB transferred**:

| Request | Count | Size | Problem |
|---------|-------|------|---------|
| `GET /api/analytics/summary?range=all` | **4×** | 13.4 KB × 4 = **53.6 KB** | Same analytics data fetched 4 times — 3 redundant calls |
| `GET /api/runs?limit=50` | **2×** | 37.2 KB × 2 = **74.4 KB** | Duplicate run list — 1 redundant call |
| `GET /api/me` | **2×** | 0.4 KB × 2 = 0.8 KB | Duplicate user fetch — 1 redundant call |
| `GET /api/workflows` | **1×** | 22.6 KB | Expected |
| `dashboard?_rsc=1xisf` (page nav) | **1×** | 3.5 KB | Expected |

**Total: 10 requests, 155 KB. Should be 4 requests, ~74 KB.**

The most severe issue is `analytics/summary?range=all` being called 4 times. The 4th call takes **5.63 seconds** to complete (visible in the screenshot) — meaning the dashboard's analytics content is delayed by 5+ seconds because 4 parallel identical requests compete for the same backend resources. With a single deduplicated call the response would arrive in ~2 seconds (the first call's time).

**Six redundant calls broken down:**
- `analytics/summary?range=all` × 3 extra calls — multiple dashboard components each independently fetch analytics on mount without sharing the response
- `runs?limit=50` × 1 extra call — same pattern as QA-PS-037: a layout-level fetch plus a component-level fetch for the same data
- `me` × 1 extra call — same pattern as QA-PS-035/036: multiple components fetch user identity independently

### Root Cause (technical)

Same systemic pattern as QA-PS-035 (settings), QA-PS-036 (analytics), and QA-PS-037 (runs history):
1. Multiple components on the dashboard each independently call the same endpoints on mount without a shared cache or provider
2. `analytics/summary` is called by at least 4 separate components or hooks — likely the stats card, the model details panel, the daily activity chart, and a layout-level fetch
3. No request deduplication layer prevents parallel identical requests

This is particularly costly on the dashboard because `analytics/summary` is a heavier endpoint (13.4 KB, 2–5s response time) and fetching it 4 times in parallel competes for the same backend query slot.

### Browser / Log Signals

```
Network (Fetch/XHR) on /dashboard load:
  GET /api/analytics/summary?range=all × 4 (13.4 KB × 4 = 53.6 KB; times: 2.06s, 3.77s, 4.56s, 5.63s)
  GET /api/runs?limit=50               × 2 (37.2 KB × 2 = 74.4 KB; times: 157ms, 50ms)
  GET /api/me                          × 2 (0.4 KB × 2; times: 72ms, 88ms)
  GET /api/workflows                   × 1 (22.6 KB — expected)
Total: 10 requests, 155 KB transferred
```

### Notes

This is the fifth page showing the same API duplication pattern (QA-PS-035 settings, QA-PS-036 analytics, QA-PS-037 runs, QA-PS-038 run detail, QA-PS-039 dashboard). All five share the same root causes:
1. Components independently fetching shared data without a shared provider/cache
2. `runs?limit=50` fired by a layout component on every route unconditionally

A single fix — moving shared fetches (`me`, `preferences`, `capabilities`, `runs?limit=50`) to a shared provider/store with deduplication, and memoizing page-specific fetches (`analytics/summary`) at the page level — would resolve all five bugs at once.

### Files

- `frontend/src/app/dashboard/` — dashboard page components: identify which components independently call `getAnalyticsSummary`, `getRuns`, `getMe`
- `frontend/src/` — shared layout or provider that calls `runs?limit=50` unconditionally (same as QA-PS-035/036/037)
- `frontend/src/lib/api.ts` — `getAnalyticsSummary`: no deduplication layer

<a id="qa-ps-040"></a>

## QA-PS-040 — Library page calls GET /api/me twice and loads run history (37 KB) that is not displayed or needed on the library

- **Page:** Library
- **Route:** /library
- **Severity:** Low
- **Found by:** PS
- **Found at:** 2026-09-17
- **User:** qa-admin@flowinqa.com

### Reproduction

1. Sign in as `qa-admin@flowinqa.com`
2. Open browser DevTools → Network tab → filter to **Fetch/XHR**
3. Navigate to `/library`
4. Observe all XHR requests that fire on page load

### Expected

Opening the Library page fires only what is needed to display agent/skill/hook cards:
- `GET /api/workflows` — once, for the agent/skill/hook catalog (94 agents, 187 skills, 8 hooks)
- `GET /api/me` — once, to identify the current user

Total: 2 requests, ~23 KB.

### Actual

Opening `/library` fires **5 requests** totalling **64 KB transferred**:

| Request | Count | Size | Problem |
|---------|-------|------|---------|
| `GET /api/me` | **2×** | 0.4 KB × 2 = 0.8 KB | Duplicate — 1 wasted call |
| `GET /api/runs?limit=50` | **1×** | 37.2 KB | **Not needed on library** — run history not shown here |
| `GET /api/workflows` | **1×** | 22.6 KB | Expected |
| `library?_rsc=dz4n1` | **1×** | 3.5 KB | Expected |

**Total: 5 requests, 64 KB. Should be 2 requests, ~23 KB.**

The library page shows agent cards, skill cards, and hook cards — no run history, no recents list, no "Jump back in" section. `GET /api/runs?limit=50` (37 KB) is entirely unused by this page. `GET /api/me` is called by two separate components independently.

### Notes

This is the least severe instance of the same systemic API duplication pattern affecting all pages (QA-PS-035 through QA-PS-039). The library page is actually the cleanest — no analytics duplication, no capabilities duplication — just the two calls that appear on every route: `me` ×2 and the unconditional `runs?limit=50` from the layout provider.

The `runs?limit=50` call on the library page takes 668ms (visible in screenshot) — the single longest request on this page — all of it wasted.

### Root Cause (technical)

Same root causes as QA-PS-035/036/037/038/039:
1. A shared layout component (`DashboardLayout` or equivalent) calls `getWorkflows(token, { limit: 50 })` → `setRecentRuns` unconditionally on every route, including the library where run history is never displayed
2. `GET /api/me` is called by at least two separate components without a shared identity provider/cache

### Browser / Log Signals

```
Network (Fetch/XHR) on /library load:
  GET /api/me             × 2  (0.4 KB × 2)
  GET /api/runs?limit=50  × 1  (37.2 KB — 668ms — not needed on library)
  GET /api/workflows      × 1  (22.6 KB — expected)
Total: 5 requests, 64 KB transferred
```

### Files

- `frontend/src/` — shared layout component that unconditionally fetches `runs?limit=50` on every route (same file identified in QA-PS-035 through QA-PS-039)
- `frontend/src/app/library/` — library page components: identify which two components independently call `getMe`

<a id="qa-ps-041"></a>

## QA-PS-041 — My Workflows page calls GET /api/user-workflows four times and loads run history (37 KB) not displayed on this page

- **Page:** My Workflows (saved custom workflows)
- **Route:** /workflows
- **Severity:** Medium
- **Found by:** PS
- **Found at:** 2026-09-17
- **User:** qa-admin@flowinqa.com

### Reproduction

1. Sign in as `qa-admin@flowinqa.com`
2. Open browser DevTools → Network tab → filter to **Fetch/XHR**
3. Navigate to `/workflows` (My Workflows)
4. Observe all XHR requests that fire on page load

### Expected

Opening the My Workflows page fires only what is needed to display saved custom workflows:
- `GET /api/user-workflows` — once, to list the user's saved custom workflows
- `GET /api/workflows` — once, for the workflow catalog (needed to display agent counts on each card)
- `GET /api/me` — once, for the current user

Total: 3 requests, ~30 KB.

### Actual

Opening `/workflows` fires **9 requests** totalling **77 KB transferred**:

| Request | Count | Size | Problem |
|---------|-------|------|---------|
| `GET /api/user-workflows` | **4×** | 3.3 KB × 4 = **13.2 KB** | Same saved workflows fetched 4 times — 3 redundant |
| `GET /api/me` | **2×** | 0.4 KB × 2 = 0.8 KB | Duplicate — 1 wasted call |
| `GET /api/runs?limit=50` | **1×** | 37.2 KB | **Not needed on My Workflows** — run history not displayed here |
| `GET /api/workflows` | **1×** | 22.6 KB | Expected |
| `workflows?_rsc=12qg9` | **1×** | 3.5 KB | Expected |

**Total: 9 requests, 77 KB. Should be 3 requests, ~30 KB.**

**`user-workflows` called 4 times** — the page shows only 3 saved workflows (user story, prototype, PPT) but the endpoint that lists them fires 4 separate times. Multiple components on the page independently fetch the saved workflows list on mount without sharing the response.

`GET /api/runs?limit=50` (37.2 KB, 81ms) is the most wasteful call here — the My Workflows page shows only saved workflow cards with "Run workflow" buttons. No run history, no recents, no "Jump back in" section is shown. The 37 KB run list is fetched and discarded.

### Root Cause (technical)

Same systemic pattern as QA-PS-035 through QA-PS-040:
1. Multiple components on the My Workflows page independently call `getUserWorkflows()` on mount without sharing the response — 4 calls for a list of 3 items
2. A shared layout component calls `getWorkflows(token, { limit: 50 })` unconditionally on every route including `/workflows` where run history is never shown
3. `GET /api/me` called by two separate components without a shared identity provider

### Browser / Log Signals

```
Network (Fetch/XHR) on /workflows load:
  GET /api/user-workflows × 4  (3.3 KB × 4 = 13.2 KB — times: 50ms, 58ms, 28ms, 40ms)
  GET /api/me             × 2  (0.4 KB × 2 — times: 15ms, 20ms)
  GET /api/runs?limit=50  × 1  (37.2 KB — 81ms — not needed on My Workflows)
  GET /api/workflows      × 1  (22.6 KB — 816ms — expected)
Total: 9 requests, 77 KB transferred
```

### Files

- `frontend/src/app/workflows/` — workflows page components: identify which 4 components independently call `getUserWorkflows`
- `frontend/src/` — shared layout component calling `runs?limit=50` unconditionally (same as QA-PS-035 through QA-PS-040)
- `frontend/src/lib/api.ts` — `getUserWorkflows`: no deduplication/cache layer

<a id="qa-ps-042"></a>

## QA-PS-042 — Admin page calls GET /api/me twice and GET /api/users twice — 2 redundant calls on page load

- **Page:** Admin Dashboard
- **Route:** /admin
- **Severity:** Low
- **Found by:** PS
- **Found at:** 2026-09-17
- **User:** qa-admin@flowinqa.com

### Reproduction

1. Sign in as `qa-admin@flowinqa.com`
2. Open browser DevTools → Network tab → filter to **Fetch/XHR**
3. Navigate to `/admin`
4. Observe all XHR requests that fire on page load

### Expected

Opening the Admin page fires only what is needed:
- `GET /api/me` — once, to verify the current user is an admin
- `GET /api/users` — once, to populate the user list

Total: 2 requests, ~1.7 KB.

### Actual

Opening `/admin` fires **5 requests** totalling **5.5 KB transferred**:

| Request | Count | Size | Problem |
|---------|-------|------|---------|
| `GET /api/me` | **2×** | 0.4 KB × 2 = 0.8 KB | Duplicate — 1 wasted call |
| `GET /api/users` | **2×** | 1.3 KB × 2 = 2.6 KB | Same user list fetched twice — 1 redundant call |
| `admin?_rsc=dz4n1` | **1×** | 2.0 KB | Expected |

**Total: 5 requests, 5.5 KB. Should be 3 requests, ~3.7 KB.**

### Notes

This is the lightest of all the pages with the duplication issue and the lowest severity. Notably, the admin page does **not** fetch `runs?limit=50` or `workflows` — it appears to use a separate layout (`AppHeader.tsx:569`) that does not include the main dashboard's layout-level run list fetch. The only two problems are `me` ×2 and `users` ×2, both from independent component-level fetches.

In absolute terms the wasted data is minimal (~1.7 KB) but the pattern is the same as every other page: components independently fetching shared data without a shared provider/cache.

### Root Cause (technical)

- `GET /api/me` is called by at least two separate components on the admin page — likely `AppHeader` (which already calls it at line 569 per the screenshot initiator) and the admin page component itself for the admin access check
- `GET /api/users` is called by two separate components — likely the stats card (showing "Total Users: 5", "Basic: 1", "Pro: 1", "Enterprise: 2", "Admins: 1") and the user table below, independently fetching the same endpoint

### Browser / Log Signals

```
Network (Fetch/XHR) on /admin load:
  GET /api/me    × 2  (0.4 KB × 2 — times: 21ms, 25ms)
  GET /api/users × 2  (1.3 KB × 2 — times: 35ms, 53ms)
Total: 5 requests (excl. page nav), 5.5 KB transferred
```

### Files

- `frontend/src/app/admin/` — admin page components: identify which two components independently call `getMe` and `getUsers`
- `frontend/src/components/AppHeader.tsx` (line 569) — calls `getMe` on admin page mount

<a id="qa-ps-043"></a>

## QA-PS-043 — Create User Stories wizard calls GET /api/user_stories four times and loads run history (37 KB) not needed on a workflow creation page

- **Page:** Create — Generate Product Requirements wizard
- **Route:** /create/user-stories
- **Severity:** Medium
- **Found by:** PS
- **Found at:** 2026-09-17
- **User:** qa-admin@flowinqa.com

### Reproduction

1. Sign in as `qa-admin@flowinqa.com`
2. Open browser DevTools → Network tab → filter to **Fetch/XHR**
3. Navigate to `/create/user-stories` (Generate Product Requirements wizard)
4. Observe all XHR requests that fire on page load

### Expected

Opening a workflow creation wizard fires only what is needed to display it:
- `GET /api/user_stories` (or equivalent config endpoint) — once, for workflow configuration
- `GET /api/workflows` — once, for the agent count / duration shown in "Advanced · 6 agents · ~35s"
- `GET /api/me` — once, for the current user

Total: 3 requests, ~26 KB.

### Actual

Opening `/create/user-stories` fires **9 requests** totalling **76 KB transferred**:

| Request | Count | Size | Problem |
|---------|-------|------|---------|
| `GET /api/user_stories` | **4×** | 2.9 KB × 4 = **11.6 KB** | Same config endpoint fetched 4 times — 3 redundant |
| `GET /api/me` | **2×** | 0.4 KB × 2 = 0.8 KB | Duplicate — 1 wasted call |
| `GET /api/runs?limit=50` | **1×** | 37.2 KB | **Not needed on a create/wizard page** — no run history shown |
| `GET /api/workflows` | **1×** | 22.6 KB | Expected |
| `user_stories?_rsc=dz4n1` | **1×** | 3.6 KB | Expected |

**Total: 9 requests, 76 KB. Should be 3 requests, ~26 KB.**

The create wizard page is a simple brief-entry form with no run history, no recents list, and no "Jump back in" section. `GET /api/runs?limit=50` (37.2 KB, 79ms) is fetched and completely unused. `GET /api/user_stories` is called 4 times — multiple components on the page each independently fetch this configuration endpoint on mount.

### Notes

This issue is expected to affect all workflow creation wizard pages (`/create/prototype`, `/create/ppt`, `/create/custom`, etc.) with the same pattern — the same layout-level `runs?limit=50` and the wizard-specific config endpoint called multiple times. Worth verifying across all `/create/*` routes.

### Root Cause (technical)

Same systemic pattern as QA-PS-035 through QA-PS-042:
1. Multiple components on the create wizard page independently call the same `user_stories` config endpoint on mount without sharing the response — 4 calls, 3 redundant
2. Shared layout component calls `getWorkflows(token, { limit: 50 })` unconditionally on every route including creation wizards where run history is never shown
3. `GET /api/me` called by at least two separate components

### Browser / Log Signals

```
Network (Fetch/XHR) on /create/user-stories load:
  GET /api/user_stories   × 4  (2.9 KB × 4 = 11.6 KB — times: 33ms, 59ms, 64ms, 105ms)
  GET /api/me             × 2  (0.4 KB × 2 — times: 21ms, 30ms)
  GET /api/runs?limit=50  × 1  (37.2 KB — 79ms — not needed on wizard)
  GET /api/workflows      × 1  (22.6 KB — 481ms — expected)
Total: 9 requests, 76 KB transferred
```

### Files

- `frontend/src/app/create/user-stories/` — create wizard components: identify which 4 components independently call the user_stories config endpoint
- `frontend/src/` — shared layout component calling `runs?limit=50` unconditionally (same as QA-PS-035 through QA-PS-042)
- Note: likely affects all `/create/*` routes — `/create/prototype`, `/create/ppt`, `/create/custom` should be checked

<a id="qa-ps-044"></a>

## QA-PS-044 — Create PPT wizard fires 228 total requests (8.9 MB) on page load — multiple component trees mount simultaneously, causing duplicate API calls and loading assets not needed on a creation wizard

- **Page:** Create — New Presentation wizard (Configure your presentation)
- **Route:** /create/ppt
- **Severity:** High
- **Found by:** PS
- **Found at:** 2026-09-17
- **User:** qa-admin@flowinqa.com

### Reproduction

1. Sign in as `qa-admin@flowinqa.com`
2. Open browser DevTools → Network tab → filter to **Fetch/XHR**, then **All**
3. Navigate to `/create/ppt` (Create a new presentation wizard)
4. Observe the total request count and transferred size at the bottom of the DevTools panel
5. Also note which components appear in the Initiator column

### Expected

Opening the PPT creation wizard fires only what is needed to display the brief-entry form and template picker:
- `GET /api/ppt` — once, for the PPT workflow configuration
- `GET /api/templates` — once, to populate the template carousel
- `GET /api/design-systems` — once, for design token data used by the template picker
- `GET /api/workflows` — once, for agent count ("3 agents" shown in Advanced)
- `GET /api/me` — once, for the current user

Total: ~5 API requests + template thumbnail images (expected). The page should load quickly with a contained, focused set of requests.

### Actual

Opening `/create/ppt` fires **228 total requests** transferring **8,897 KB (8.9 MB)**. The DevTools initiator column reveals multiple distinct component trees mounting simultaneously and each independently fetching:

**Duplicate API calls (Fetch/XHR):**

| Request | Count | Problem |
|---------|-------|---------|
| `GET /api/me` | **3×** | User identity fetched 3 times — 2 redundant |
| `GET /api/ppt` | **2×** | Wizard config fetched twice — 1 redundant |
| `GET /api/templates` | **2×** | Template list fetched twice — 1 redundant |
| `GET /api/runs?limit=50` | **1×** | **Not needed on create wizard** — 37 KB wasted |
| `GET /api/workflows` | **1×** | Expected |
| `GET /api/design-systems` | **1×** (33.2 KB) | Expected |

**Multiple component trees mounting simultaneously (the structural problem):**

The initiator tooltip shows all of these firing at the same time:
- `authFetch` (prototype-api.ts:41)
- `listDesignSystems` (prototype-api.ts:65)
- `LaunchWizard.tsx:554` — the PPT creation wizard component
- `DashboardPage` (page.tsx:3868) — the main dashboard page component
- `HomeLaunchGrid.tsx:223` and `HomeLaunchGrid.tsx:288` — the home page grid component
- `Promise.all` (VM1140) — parallel batch fetches

The dashboard page (`DashboardPage`) and home page grid (`HomeLaunchGrid`) components appear to be mounting **alongside** the PPT wizard instead of being replaced by it. This means the `/create/ppt` route is rendering both the wizard AND the full dashboard/home components underneath it — tripling the API calls and loading all the home page assets (template thumbnails, etc.) in addition to the wizard's own assets.

**The 8.9 MB total** is driven by this: the home page's `HomeLaunchGrid` loads template card images/assets for the home page while the wizard also loads the PPT template carousel — both asset sets load simultaneously, neither of which the other needs.

### Root Cause (technical)

The `/create/ppt` route appears to render inside the main dashboard layout without unmounting the home page component (`DashboardPage` / `HomeLaunchGrid`). Both the wizard and the underlying home page components are active simultaneously:
- `LaunchWizard` fetches what it needs (ppt config, templates, design systems)
- `DashboardPage` and `HomeLaunchGrid` independently fetch what THEY need (runs, home page assets)
- All of this happens in parallel on the same page load

This is structurally different from the other pages' duplication issues (which are about shared data fetched multiple times by sibling components). Here the issue is that **two distinct page-level components are both mounted** — the wizard overlay and the underlying home page — causing the total request count to balloon to 228.

### Browser / Log Signals

```
Network → All → /create/ppt load:
  Total requests: 228
  Total transferred: 8,897 KB (8.9 MB)

Initiators firing simultaneously:
  authFetch          @ prototype-api.ts:41
  listDesignSystems  @ prototype-api.ts:65
  LaunchWizard       @ LaunchWizard.tsx:554
  DashboardPage      @ page.tsx:3868         ← home page mounting under wizard
  HomeLaunchGrid     @ HomeLaunchGrid.tsx:223 ← home grid mounting under wizard
  HomeLaunchGrid     @ HomeLaunchGrid.tsx:288
  Promise.all        @ VM1140 (batch fetches)

Duplicate Fetch/XHR:
  GET /api/me                × 3
  GET /api/ppt               × 2
  GET /api/templates         × 2
  GET /api/runs?limit=50     × 1 (not needed on wizard)
  GET /api/design-systems    × 1 (33.2 KB — expected)
```

### Files

- `frontend/src/app/create/ppt/` or `frontend/src/components/wizard/LaunchWizard.tsx` — PPT creation wizard component (line 554)
- `frontend/src/app/[...view]/page.tsx` (line 3868) — `DashboardPage` mounting under the wizard route
- `frontend/src/components/HomeLaunchGrid.tsx` (lines 223, 288) — home page grid mounting under wizard route
- `frontend/src/` — route configuration: check whether `/create/ppt` correctly replaces the home page component or renders as an overlay on top of it

<a id="qa-ps-045"></a>

## QA-PS-045 — Create Prototype wizard fires 143 total requests (3.6 MB) with me×3, prototype×2, runs?limit=50×2, templates×2 — and PPT template assets load on a prototype page due to simultaneous home page mounting

- **Page:** Create — New Prototype wizard (Configure your prototype)
- **Route:** /create/prototype
- **Severity:** High
- **Found by:** PS
- **Found at:** 2026-09-17
- **User:** qa-admin@flowinqa.com

### Reproduction

1. Sign in as `qa-admin@flowinqa.com`
2. Open browser DevTools → Network tab → filter to **All**
3. Navigate to `/create/prototype` (Configure your prototype wizard)
4. Observe total request count and size at the bottom of DevTools
5. Note the Initiator column — observe which components fire requests simultaneously

### Expected

Opening the prototype creation wizard fires only what is needed:
- `GET /api/prototype` — once, for prototype workflow configuration
- `GET /api/templates` — once, for the prototype template carousel (48 templates shown)
- `GET /api/design-systems` — once, for design system data
- `GET /api/workflows` — once, for "5 agents" shown in Advanced
- `GET /api/me` — once, for the current user

Total: ~5 API requests + template thumbnails. No PPT assets, no run history.

### Actual

Opening `/create/prototype` fires **143 total requests** transferring **3,598 KB (3.6 MB)**:

**Duplicate and wrong-page Fetch/XHR calls:**

| Request | Count | Size | Problem |
|---------|-------|------|---------|
| `GET /api/me` | **3×** | 0.4 KB × 3 | Fetched 3 times — 2 redundant |
| `GET /api/prototype` | **2×** | 2.9 KB × 2 | Wizard config fetched twice — 1 redundant |
| `GET /api/runs?limit=50` | **2×** | 37.2 KB × 2 = **74.4 KB** | Not needed on wizard — AND called twice |
| `GET /api/templates` | **2×** | — | Template list fetched twice — 1 redundant |
| `GET /api/design-systems` | **1×** | 33.2 KB | Expected |
| `GET /api/workflows` | **1×** | 22.6 KB | Expected |
| PPT templates (`ppt_api.ts:32`) | **1×** | **44.3 KB** | **PPT template assets loading on a prototype wizard** |

**Same structural root cause as QA-PS-044 — multiple component trees mounting simultaneously:**

The initiator tooltip shows all of these firing at once:
- `apiFetch` (ppt_api.ts:32) — PPT API loading on prototype page
- `listPPTTemplates` (ppt_api.ts:48) — PPT template list loading on prototype page
- `LaunchWizard.tsx:548` — prototype wizard component
- `DashboardPage` (page.tsx:3868) — home page component mounting under the wizard
- `HomeLaunchGrid.tsx:223` and `HomeLaunchGrid.tsx:288` — home page grid mounting under the wizard
- `Promise.all` (VM1140) — parallel batch fetches

The home page (`DashboardPage` / `HomeLaunchGrid`) is mounting simultaneously with the prototype wizard, exactly as in `/create/ppt` (QA-PS-044). This causes:
1. All home page API calls to fire alongside the wizard's calls
2. PPT-specific assets (`ppt_api.ts`) to load even though this is a **prototype** wizard — the home page's PPT sections are initialising underneath

**Two additional problems vs QA-PS-044:**
- `runs?limit=50` is called **twice** here (once from the wizard's layout, once from the home page component) vs once on `/create/ppt`
- PPT templates (44.3 KB) load on a prototype page due to the home page's PPT section initialising underneath — cross-workflow asset contamination

### Root Cause (technical)

Same root cause as QA-PS-044: the `/create/prototype` route renders `LaunchWizard` as an overlay without unmounting the underlying `DashboardPage` and `HomeLaunchGrid` components. Both the wizard and the home page are active simultaneously — every API either component needs fires in parallel.

The additional `runs?limit=50` duplication (×2 vs ×1 on `/create/ppt`) suggests the prototype wizard has an extra component fetching it that the PPT wizard doesn't. The PPT asset loading on the prototype page comes from the home page's PPT launch grid initialising in the background.

### Browser / Log Signals

```
Network → All → /create/prototype load:
  Total requests: 143
  Total transferred: 3,598 KB (3.6 MB)

Initiators firing simultaneously:
  apiFetch           @ ppt_api.ts:32         ← PPT assets on prototype page
  listPPTTemplates   @ ppt_api.ts:48         ← PPT templates on prototype page
  LaunchWizard       @ LaunchWizard.tsx:548
  DashboardPage      @ page.tsx:3868         ← home page mounting under wizard
  HomeLaunchGrid     @ HomeLaunchGrid.tsx:223
  HomeLaunchGrid     @ HomeLaunchGrid.tsx:288
  Promise.all        @ VM1140

Duplicate Fetch/XHR:
  GET /api/me               × 3
  GET /api/prototype        × 2
  GET /api/runs?limit=50    × 2  (74.4 KB wasted — not needed on wizard, and duplicated)
  GET /api/templates        × 2
  ppt_api.ts:32 asset       × 1  (44.3 KB — PPT assets on wrong page)
```

### Files

- `frontend/src/components/wizard/LaunchWizard.tsx` (line 548) — prototype wizard component
- `frontend/src/app/[...view]/page.tsx` (line 3868) — `DashboardPage` mounting under wizard route
- `frontend/src/components/HomeLaunchGrid.tsx` (lines 223, 288) — home page grid mounting under wizard
- `frontend/src/lib/ppt_api.ts` (lines 32, 48) — PPT template fetches firing on prototype page
- `frontend/src/` — route configuration: `/create/prototype` should replace rather than overlay the home page (same fix as QA-PS-044)

<a id="qa-ps-046"></a>

## QA-PS-046 — Custom workflow builder calls GET /api/capabilities four times (94 KB wasted) and loads run history not needed on the composer

- **Page:** Custom workflow builder (Composer)
- **Route:** /workflows/new
- **Severity:** Medium
- **Found by:** PS
- **Found at:** 2026-09-17
- **User:** qa-admin@flowinqa.com

### Reproduction

1. Sign in as `qa-admin@flowinqa.com`
2. Open browser DevTools → Network tab → filter to **Fetch/XHR**
3. Navigate to `/workflows/new` (Create new custom workflow)
4. Observe all XHR requests that fire on page load

### Expected

Opening the custom workflow composer fires only what is needed to display the canvas and agent picker:
- `GET /api/capabilities` — once, to populate the agent/capability picker (the right-panel Agent tab and node picker)
- `GET /api/workflows` — once, for the workflow catalog
- `GET /api/me` — once, for the current user

Total: 3 requests, ~47 KB.

### Actual

Opening `/workflows/new` fires **9 requests** totalling **159 KB transferred**:

| Request | Count | Size | Problem |
|---------|-------|------|---------|
| `GET /api/capabilities` | **4×** | 23.6 KB × 4 = **94.4 KB** | Same capability catalog fetched 4 times — 3 redundant (70.8 KB wasted) |
| `GET /api/me` | **2×** | 0.4 KB × 2 = 0.8 KB | Duplicate — 1 wasted call |
| `GET /api/runs?limit=50` | **1×** | 37.2 KB | **Not needed on the workflow composer** — no run history shown |
| `GET /api/workflows` | **1×** | 22.6 KB | Expected |
| `now?_rsc=dz4n1` | **1×** | 3.5 KB | Expected |

**Total: 9 requests, 159 KB. Should be 3 requests, ~47 KB.**

The `capabilities` endpoint (23.6 KB per call) is fetched 4 times — each response is identical and contains the full catalog of agents, validators, gates, and model options used to populate the composer's right panel. Four parallel identical fetches consume 94.4 KB for data that could be shared from a single 23.6 KB response.

`GET /api/runs?limit=50` (37.2 KB, 96ms) is wasted entirely — the custom workflow composer shows a blank canvas with no run history, recents, or "Jump back in" section.

### Root Cause (technical)

Same systemic pattern as QA-PS-035 through QA-PS-045:
1. Multiple panels/components in the custom workflow composer (canvas, right-panel Agent tab, node picker, model config, validator picker) each independently call `getCapabilities()` on mount without sharing the response — 4 calls for an identical 23.6 KB payload
2. Shared layout component calls `getWorkflows(token, { limit: 50 })` unconditionally on every route including the workflow composer where run history is never shown
3. `GET /api/me` called by two separate components without a shared identity provider

The `capabilities` duplication is particularly costly here because this endpoint returns the full capability registry (agents, validators, gates, context providers, model catalog) at 23.6 KB — fetching it 4 times in parallel adds 70.8 KB of redundant data and creates 4 concurrent DB/registry reads on the backend.

### Browser / Log Signals

```
Network (Fetch/XHR) on /workflows/new load:
  GET /api/capabilities   × 4  (23.6 KB × 4 = 94.4 KB — times: 35ms, 46ms, 30ms, 38ms)
  GET /api/me             × 2  (0.4 KB × 2 — times: 51ms, 62ms)
  GET /api/runs?limit=50  × 1  (37.2 KB — 96ms — not needed on composer)
  GET /api/workflows      × 1  (22.6 KB — 1.05s — expected)
Total: 9 requests, 159 KB transferred
```

### Files

- `frontend/src/app/workflows/new/` or `frontend/src/components/workflow/` — composer components: identify which 4 components independently call `getCapabilities`
- `frontend/src/` — shared layout component calling `runs?limit=50` unconditionally (same as QA-PS-035 through QA-PS-045)
- `frontend/src/lib/api.ts` — `getCapabilities`: no deduplication/cache layer

<a id="qa-ps-047"></a>

## QA-PS-047 — Live stream page fires 49+ requests (10+ MB) with runs?limit=50 called 8-9× in real time as SSE events arrive — home page mounts under stream view and refetches fire on every live pipeline event

- **Page:** Live run stream (opened from notification badge or header "N Running" dropdown)
- **Route:** /runs/{id}/stream
- **Severity:** High
- **Found by:** PS
- **Found at:** 2026-09-17
- **User:** qa-admin@flowinqa.com

### Reproduction

1. Sign in as `qa-admin@flowinqa.com`
2. Start a pipeline run (e.g. Prototype — 5 agents)
3. While the run is in progress, click the **"N Running"** badge in the header or click the notification in the notification panel
4. Observe the page that opens (`/runs/{id}/stream`)
5. Open browser DevTools → Network tab → filter to **Fetch/XHR**
6. Watch requests fire as the run progresses over ~15 minutes

### Expected

Opening a live run stream fires only what is needed to display and stream the run:
- `GET /api/runs/{id}` — once, to fetch run details
- `GET /api/runs/{id}/events?after=0` — once, SSE event replay (then SSE stream takes over)
- `GET /api/runs/{id}/family` — once, for revision family context
- `GET /api/runs/{id}/sandbox/refs` — once, for version menu
- `GET /api/runs?limit=50` — once at mount, for recents badge
- `GET /api/workflows` — once, for workflow catalog
- `GET /api/me` — once

Total: ~7 requests at mount, then the SSE stream carries all live updates. No additional `runs?limit=50` fetches as events arrive.

### Actual

Opening `/runs/{id}/stream` fires **49+ requests** in the first 7 seconds alone, totalling **10,226 KB (10+ MB)** and continuing to grow as the run progresses over its 15-minute duration:

**Duplicate and cascading calls visible:**

| Request | Count (observed) | Size | Problem |
|---------|-----------------|------|---------|
| `GET /api/runs?limit=50` | **8-9×** (and growing) | 37.2 KB × 9 = **335 KB+** | Fires on every live SSE event — `review_gate_ready`, `review_gate_approved`, `pipeline_complete`, etc. |
| `GET /api/family` | **2×** | 0.7 KB × 2 | Duplicate family fetch |
| `GET /api/refs` | **2×** | 0.4 KB × 2 | Duplicate sandbox refs fetch |
| `GET /api/events?after=0` | **1×** | — | Expected (initial SSE replay) |
| `GET /api/events?after=11900` | **1×** | — | SSE reconnect (expected) |
| `GET /api/me` | **2×** | 0.4 KB × 2 | Duplicate |
| `GET /api/workflows` | **1×** | 22.6 KB | Expected |
| `GET /api/runs/{id}` | **1×** | — | Expected |
| `GET /api/sandbox` | **1×** | 1.1 KB | Expected |

**Two compounding problems:**

**Problem 1 — Same as QA-PS-038 but amplified by the live event stream:**

The `runs?limit=50` refetch-on-SSE-event pattern (from QA-PS-038) fires during a *live* run's actual events, not just during durable replay. As the run progresses over ~15 minutes and fires `review_gate_ready`, `review_gate_approved` (×3 visible in screenshot), `questionnaire_ready`, `questionnaire_complete`, `pipeline_complete` etc., each event triggers a `runs?limit=50` fetch. For a 5-agent run with 3 review gates + clarifications, this is **8-12 live fetches** at 37.2 KB each = **300-450 KB** of redundant run list data fetched while the user is watching their pipeline run.

The `WorkflowHistory` T38 cascade doubles each one: every `setRecentRuns(newArray)` triggers `WorkflowHistory`'s `useEffect([recentRuns])` → another independent `runs?limit=50`.

**Problem 2 — `DashboardPage` / `HomeLaunchGrid` mounting under the stream view:**

The initiator tooltip shows `page.tsx:2089`, `page.tsx:2885`, `page.tsx:3534` and `DashboardLayout.tsx:692` — the same home page component firing that was seen in QA-PS-044/045. The `/runs/{id}/stream` route (reached from the notification badge) renders the stream view as an overlay with the home page still mounted underneath, identical to the `/create/ppt` and `/create/prototype` routing issue.

**`Promise.all` (VM1140)** — the home page's parallel batch fetches are visible here too, confirming the same structural overlay issue.

### Why this is worse than QA-PS-038

QA-PS-038 (opening a *completed* run from history) fires 12+ `runs?limit=50` calls during one-time durable replay. QA-PS-047 fires them continuously throughout the run's lifetime — for a 15-minute run with multiple gates and clarifications, this generates **30+ `runs?limit=50` calls** (one per gate-ready, gate-approved, clarify-ready, clarify-complete, pipeline-complete × 2 for the T38 cascade) totalling **1+ MB of redundant run list data** fetched while the page is actively being used.

### Browser / Log Signals

```
Network screenshot 1 (first 7s, 49 requests, 10,226 KB):
  runs?limit=50           × 6+  (37.2 KB each — cascading)
  family                  × 2   (0.7 KB × 2)
  refs                    × 2
  events?after=0          × 1
  me                      × 2

Initiators firing simultaneously:
  fetchWithTimeout   @ api.ts:291
  fetchWithAuth      @ api.ts:339
  getWorkflows       @ api.ts:776
  DashboardLayout    @ DashboardLayout.tsx:692  ← home page under stream
  page.tsx:2089, 2885, 3534                     ← home page event handlers
  Promise.all        @ VM1140 <anonymous>:1

Network screenshot 2 (continuing after 100s, 50 requests, 10,263 KB):
  runs?limit=50           × 8+ more (continuing as gates fire)
  events?after=11900      × 1 (SSE reconnect)
  family                  × 2 more
  sandbox                 × 1
```

### Files

- `frontend/src/app/[...view]/page.tsx` — 12 `getWorkflows` call sites in `handleWebSocketMessage` (same as QA-PS-038) — fire on LIVE events here, not just replay
- `frontend/src/components/history/WorkflowHistory.tsx` (line 248) — T38 cascade: fires additional `runs?limit=50` for each `setRecentRuns` reference change
- `frontend/src/` — route configuration: `/runs/{id}/stream` should replace rather than overlay the home page (same fix as QA-PS-044/045)
- `frontend/src/providers/RunConnectionProvider.tsx` — `refreshLiveRuns` (line 289): fires on boot + each tab focus/reconnect

<a id="qa-ps-048"></a>

## QA-PS-048 — Clicking any run detail tab (Preview, Steps, Files, Workspace, Audit) fires multiple duplicate API calls — run data (829 KB) fetched 3× and tab-specific endpoints fetched 2-4× per tab switch

- **Page:** Run detail — all tabs (Preview, Steps, Files, Workspace, Audit)
- **Route:** /runs/{id}/preview, /runs/{id}/steps, /runs/{id}/files, /runs/{id}/workspace, /runs/{id}/audit
- **Severity:** High
- **Found by:** PS
- **Found at:** 2026-09-17
- **User:** qa-admin@flowinqa.com

### Reproduction

1. Sign in as `qa-admin@flowinqa.com`
2. Open browser DevTools → Network tab → filter to **Fetch/XHR**
3. Open any completed run from history (e.g. `/runs/02c05da3-447a-49c5-b048-5643c440cc5c`)
4. Click on different tabs one at a time: **Preview**, **Steps**, **Files**, **Workspace**, **Audit**
5. On each tab switch, observe which API requests fire and how many times the same endpoint is called

### Expected

Each tab switch fires only the requests needed to display that tab's content, called once each:
- **Preview tab**: no new fetch needed — content already loaded at initial run open
- **Steps tab**: no new fetch — agent steps already in the run's durable event replay
- **Files tab**: `GET /api/runs/{id}/sandbox` — once, to list workspace files
- **Workspace tab**: `GET /api/runs/{id}/sandbox` — once (same as files, or already cached)
- **Audit tab**: `GET /api/runs/{id}/gate-events` once, `GET /api/runs/{id}/validation-results` once, `GET /api/runs/{id}/exec-runs` once, `GET /api/runs/{id}/hook-runs` once

No re-fetching of the full run data (829 KB) on every tab switch.

### Actual

Clicking the **Audit tab** fires **61 requests / 79 total, 13,973 KB** — with the following duplicates observed:

| Request | Count | Size | Problem |
|---------|-------|------|---------|
| `GET /api/runs/{id}` (full run record) | **3×** | 829 KB × 3 = **2,487 KB** | Full run data re-fetched 3 times on Audit tab switch — 1.66 MB wasted |
| `GET /api/runs/{id}/sandbox` | **4×** | 1.1 KB × 4 = 4.4 KB | Sandbox listing fetched 4 times |
| `GET /api/runs/{id}/gate-events` | **4×** | 0.4 KB × 4 | Gate events fetched 4 times |
| `GET /api/runs/{id}/validation-results` | **2×** | 6.5 KB × 2 = 13 KB | Duplicate |
| `GET /api/runs/{id}/exec-runs` | **2×** | 0.4 KB × 2 | Duplicate |
| `GET /api/runs/{id}/hook-runs` | **2×** | 146 KB × 2 = **292 KB** | Hook runs (146 KB each) fetched twice — 146 KB wasted |
| `GET /api/workflows` | **1×** | 22.6 KB | Expected |

**The full run record (829 KB) is fetched 3 times on a single tab switch.** This is the most severe individual waste — 1.66 MB of redundant data for a record that does not change between tab switches on a completed run.

**Pattern across all tabs:**
Each tab switch appears to trigger multiple components remounting and independently re-fetching both the full run data AND the tab-specific endpoints. The run data (829 KB) should be fetched once at run open and shared across all tabs via a cache or context — instead it is re-fetched by multiple components every time any tab is clicked.

**Hook runs (146 KB × 2 = 292 KB):** The hook runs endpoint returns a large payload (146 KB) and is fetched twice on the Audit tab — a particularly wasteful duplicate given the payload size.

### Root Cause (technical)

Each tab in the run detail view appears to mount its own set of components that independently call:
1. `getWorkflow(token, runId)` — fetches the full 829 KB run record — instead of reading from a shared context/cache populated at run open time
2. Their own tab-specific endpoints (`gate-events`, `validation-results`, `exec-runs`, `hook-runs`, `sandbox`) — each called by multiple components that mount simultaneously when the tab becomes active

For tab-specific data, the issue is that multiple sibling components on the same tab each independently fetch the same endpoint on mount without a shared fetch or deduplication. For the full run data, the issue is that components don't read from the run data already fetched during `handleSelectWorkflowRun` — they trigger fresh fetches instead.

The 829 KB run record re-fetch on every tab switch is particularly problematic for large runs (this run is 2.2M tokens) — the `GET /api/runs/{id}` response grows with run size, and fetching it 3× on every tab navigation makes tab switching noticeably slow for users with large completed runs.

### Browser / Log Signals

```
Network (Fetch/XHR) on clicking Audit tab:
  GET /api/runs/{id}            × 3  (829 KB × 3 = 2,487 KB — 1.66 MB wasted)
  GET /api/runs/{id}/sandbox    × 4  (1.1 KB × 4)
  GET /api/runs/{id}/gate-events × 4  (0.4 KB × 4)
  GET /api/runs/{id}/validation-results × 2 (6.5 KB × 2 = 13 KB)
  GET /api/runs/{id}/exec-runs  × 2  (0.4 KB × 2)
  GET /api/runs/{id}/hook-runs  × 2  (146 KB × 2 = 292 KB — 146 KB wasted)
Total on Audit tab: 61/79 requests, 13,973 KB
```

### Files

- `frontend/src/components/results/` — tab components (PreviewPanel, StepsTab, FilesTab, SandboxTab, AuditTab): check which components independently call `getWorkflow(token, runId)` instead of reading from shared state
- `frontend/src/app/[...view]/page.tsx` — `handleSelectWorkflowRun`: check whether run data fetched here is shared via context/cache to tab components
- `frontend/src/components/results/AuditTab` or equivalent — check which components independently call `getGateEvents`, `getValidationResults`, `getExecRuns`, `getHookRuns` on tab mount

<a id="qa-ps-049"></a>

## QA-PS-049 — Clicking any agent in the Steps tab fetches GET /api/artifacts twice — 1 redundant call per agent click

- **Page:** Run detail — Steps tab, individual agent detail view
- **Route:** /runs/{id}/steps?agent={agent-id}
- **Severity:** Low
- **Found by:** PS
- **Found at:** 2026-09-17
- **User:** qa-admin@flowinqa.com

### Reproduction

1. Sign in as `qa-admin@flowinqa.com`
2. Open any completed run from history (e.g. `/runs/02c05da3-447a-49c5-b048-5643c440cc5c`)
3. Click the **Steps** tab
4. Open browser DevTools → Network tab → filter to **Fetch/XHR** and clear existing requests
5. Click on any agent in the steps list (e.g. "Spec Writer Agent")
6. Observe the requests that fire

### Expected

Clicking an agent in the Steps tab fires `GET /api/runs/{id}/artifacts` once to load the artifact context shown in the right panel ("Context Received" — sources fed in, e.g. `prompt.md`, `Template: process-canvas`, `Design system: apple`).

### Actual

Clicking any agent fires `GET /api/runs/{id}/artifacts` **twice** in rapid succession (24ms apart, identical 13.4 KB responses). Both calls are to the same endpoint with the same parameters and return identical data. One call is redundant.

This fires on every individual agent click. For a 5-agent run where the user clicks each agent to inspect it, that is 10 artifact fetches instead of 5 — 67 KB transferred instead of 33.5 KB.

### Root Cause (technical)

Two components in the agent detail panel independently call `getArtifacts(token, runId)` on mount:
- One for the "Context Received" sources panel (right side — shows `prompt.md`, template, design system files fed into the agent's prompt)
- One likely for the main agent output/thinking area or the "TOOL CALLS" section

Both components mount when the agent is selected and each triggers its own fetch without reading from a shared cache or prop.

### Browser / Log Signals

```
Network (Fetch/XHR) on clicking Spec Writer Agent in Steps tab:
  GET /api/runs/{id}/artifacts  × 2  (13.4 KB × 2 = 26.8 KB — 13.4 KB wasted)
  Times: 24ms, 39ms (simultaneous)
Total: 2 requests, 26.7 KB
```

### Files

- `frontend/src/components/results/StepsOverviewSpine.tsx` or equivalent agent detail panel component
- `frontend/src/components/results/AgentThinkingTab.tsx` or equivalent — check which two sub-components independently call `getArtifacts` on agent selection
- `frontend/src/lib/api.ts` — `getArtifacts` / `getRunArtifacts`: no deduplication layer

<a id="qa-ps-050"></a>

## QA-PS-050 — GET /api/runs?limit=50 is called up to 22 times per page load instead of 4 — 11 of 15 call sites fire when the run list cannot have changed, causing continuous unnecessary backend load throughout a user's session

- **Page:** All pages that render the run detail, run history, or any page with the recents badge
- **Route:** /runs/{id}, /runs/{id}/stream, /runs, and all other routes
- **Severity:** High
- **Found by:** PS
- **Found at:** 2026-09-17
- **User:** qa-admin@flowinqa.com

### Reproduction

1. Sign in as `qa-admin@flowinqa.com`
2. Open browser DevTools → Network tab → filter to **Fetch/XHR**, enable **Keep log**
3. Open any completed run from history and leave it open for 5–10 minutes
4. Periodically switch to another browser tab and switch back
5. Count how many times `runs?limit=50` appears in the network log

### Expected

`GET /api/runs?limit=50` is called in exactly **4 situations** — the only times the run list can have changed:
1. At app startup (auth mount) — once
2. After a new run is launched (`POST /api/runs` succeeds)
3. When a **live** run reaches `pipeline_complete`
4. When a **live** run is cancelled (`pipeline_cancelled`)

Total per session: 1 startup call + 1 per run launched or completed. For a normal session with 3 runs, that is ~7 calls total.

### Actual

`GET /api/runs?limit=50` fires from **15 distinct call sites** and can be called **20-22 times** just by opening one completed run. It continues firing every few minutes throughout the session regardless of whether anything changed.

**The 15 call sites broken down:**

| Call site | File:line | Fires during replay? | Status change possible? | Justified? |
|-----------|-----------|---------------------|------------------------|-----------|
| Auth mount | page.tsx:968 | — | Yes (initial load) | ✅ |
| Post-launch | page.tsx:4136 | — | Yes (new run created) | ✅ |
| `pipeline_complete` immediate | page.tsx:1597 | **Yes** | Only on live run | ⚠️ Bug during replay |
| `pipeline_complete` delayed 2s | page.tsx:1626 | **Yes** | Already fetched at :1597 | ❌ Always redundant |
| `pipeline_failed` | page.tsx:1673 | **Yes** | Only on live run | ⚠️ Bug during replay |
| `pipeline_cancelled` | page.tsx:1759 | **Yes** | Only on live run | ⚠️ Bug during replay |
| `pipeline_diverted` | page.tsx:1710 | **Yes** | Only on live run | ⚠️ Bug during replay |
| `questionnaire_ready` | page.tsx:1996 | **Yes** | Only on live run | ⚠️ Bug during replay |
| `questionnaire_complete` | page.tsx:2021 | **Yes** | Only on live run | ⚠️ Bug during replay |
| `review_gate_ready` | page.tsx:2059 | **Yes** | Only on live run | ⚠️ Bug during replay |
| `review_gate_approved` | page.tsx:2089 | **Yes** | Only on live run | ⚠️ Bug during replay |
| T38 cascade | WorkflowHistory.tsx:250 | **Yes** | No — doubles every above call | ❌ Always redundant |
| Boot + tab focus | RunConnectionProvider.tsx:289 | — | No (tab switch doesn't change runs) | ❌ Tab focus is redundant |
| `visibilitychange` / `online` | RunConnectionProvider.tsx:336 | — | Rare | ⚠️ Should be conditional |
| `signedIn` listener | listenerMiddleware.ts:55 | — | Parallel duplicate of auth mount | ❌ Duplicate of page.tsx:968 |

**Why 11 of 15 calls are bugs:**

- **Durable replay calls (8 sites):** `handleWebSocketMessage` has no `isDurableReplay` flag. Opening a completed run replays its full historical event log through the same handler used for live events. Every `pipeline_complete`, `review_gate_ready`, `review_gate_approved`, `questionnaire_ready`, `questionnaire_complete` etc. in the historical log triggers a `runs?limit=50` refetch — but a completed run's status is already persisted in the DB and will never change. The refetch cannot return different data than what was already fetched.

- **T38 cascade (WorkflowHistory.tsx:250):** Every `setRecentRuns(newArray)` call in page.tsx produces a new array reference → triggers WorkflowHistory's `useEffect([recentRuns])` → fires an independent `runs?limit=50`. This doubles every other call, including the 8 replay calls above. Added intentionally to keep the history panel fresh during live runs, but it fires unconditionally even during replay of completed runs.

- **`pipeline_complete` delayed 2s (page.tsx:1626):** KAN-120 race guard — fires a second fetch 2 seconds after the first to catch backend reconciliation. The first fetch already updated the list. The delayed duplicate is redundant in ~99% of cases.

- **Tab focus polling (RunConnectionProvider.tsx:336):** Fires `refreshLiveRuns()` (→ `runs?limit=50`) on every `visibilitychange` to visible. If the user switches browser tabs every 2 minutes, this fires every 2 minutes indefinitely for the entire session, even when no runs are active.

- **`signedIn` parallel duplicate (listenerMiddleware.ts:55):** `fetchRecentRuns` is dispatched on the `signedIn` action at the same moment `page.tsx:968`'s `useEffect([isAuthenticated])` fires — two parallel calls for the same login event.

**The T38 multiplier effect:** Each of the 8 replay calls fires `setRecentRuns(newArray)` → T38 cascade fires a 9th call → total from one durable replay = 8 × 2 = 16 calls. Plus 2 from mount + 1 from tab focus = **19-22 calls** just from opening one completed run.

**Continuous background polling:** Even on a settled completed run with no events, `visibilitychange` fires `runs?limit=50` every time the user switches back to the tab — once every few minutes for the lifetime of the session. For a developer testing the app all day, this generates hundreds of unnecessary backend requests.

### Impact

- Each `runs?limit=50` call returns 37.2 KB — 11 redundant calls per run open = **411 KB** of wasted data transfer per completed run opened
- The backend processes 15–22 DB queries for the same result that could be fetched once
- Continuous background polling (tab-focus firing) creates ongoing backend load even when nothing is happening on screen
- The cascading refetches cause the run history list to flicker/re-render multiple times as each response arrives

### Root Cause (technical)

`handleWebSocketMessage` (page.tsx) cannot distinguish live SSE frames from durable replay frames. The fix requires a single targeted change:

**Fix 1 — Pass a replay flag through the durable replay loop (page.tsx ~line 2879):**
```typescript
for (const frame of durableFrames) {
  handleWebSocketMessage(
    { ...frame, _isDurableReplay: true },  // add flag
    fullRun.id,
  );
}
```
Then gate all 8 `runs?limit=50` call sites in `handleWebSocketMessage` on `!msg._isDurableReplay`.

**Fix 2 — Debounce/gate the T38 cascade (WorkflowHistory.tsx:250):**
Replace the unconditional `useEffect([recentRuns])` with one that only fires when a run's status has actually changed (compare status fields, not array reference).

**Fix 3 — Remove the delayed duplicate (page.tsx:1626):**
The 2-second delayed refetch for KAN-120 race is redundant when Fix 1 is applied.

**Fix 4 — Condition the tab-focus call (RunConnectionProvider.tsx:336):**
Only call `refreshLiveRuns()` on `visibilitychange` if there are known live runs (`autoIdsRef.current.length > 0`). When no runs are active, tab focus should not trigger a backend query.

### Files

- `frontend/src/app/[...view]/page.tsx` — all 12 call sites: lines 968, 1597, 1626, 1673, 1710, 1759, 1996, 2021, 2059, 2089, 4136; `handleSelectWorkflowRun` durable replay loop (~line 2879)
- `frontend/src/components/history/WorkflowHistory.tsx` — T38 cascade effect (line ~250)
- `frontend/src/providers/RunConnectionProvider.tsx` — `refreshLiveRuns` (line ~289); `visibilitychange` handler (line ~336)
- `frontend/src/store/listenerMiddleware.ts` — `signedIn` handler (line ~55): duplicate of page.tsx auth mount

<a id="qa-ps-051"></a>

## QA-PS-051 — Library detail pages (agents, skills, hooks) make duplicate API calls and load run history not needed on any library detail view

- **Page:** Library — Agent detail, Skill detail, Hook detail (all tabs: Overview, Skills, Hooks, Config)
- **Route:** /library/agents/*, /library/skills/*, /library/hooks/*
- **Severity:** Medium
- **Found by:** PS
- **Found at:** 2026-09-17
- **User:** qa-admin@flowinqa.com

### Reproduction

1. Sign in as `qa-admin@flowinqa.com`
2. Open browser DevTools → Network tab → filter to **Fetch/XHR**
3. Go to `/library`, click on any agent card to open its detail panel (e.g. "Architecture Agent")
4. Observe the requests that fire on the agent detail view
5. Click the **Config** tab in the detail panel
6. Repeat for a skill and a hook

### Expected

Opening a library detail view fires only what is needed to display it:
- `GET /api/capabilities` — once, for the capability catalog (agent/skill/hook metadata, system prompt, pipeline role)
- `GET /api/workflows` — once, for the pipeline context shown in the detail panel
- `GET /api/me` — once, for the current user

Total: 3 requests, ~27 KB. No run history.

### Actual

Opening a library agent/skill/hook detail view fires **8 requests totalling 149 KB**:

| Request | Count | Size | Problem |
|---------|-------|------|---------|
| `GET /api/capabilities` | **2×** | 23.6 KB × 2 = **47.2 KB** | Same capability catalog fetched twice — 1 redundant call |
| `GET /api/runs?limit=50` | **2×** | 37.2 KB × 2 = **74.4 KB** | **Not needed on any library detail view** — run history never shown here, and called twice |
| `GET /api/me` | **2×** | 0.4 KB × 2 = 0.8 KB | Duplicate — 1 wasted call |
| `GET /api/workflows` | **1×** | 22.6 KB | Expected |
| page nav `_rsc=*` | **1×** | 3.6 KB | Expected |

**Total: 8 requests, 149 KB. Should be 3 requests, ~27 KB.**

The same pattern applies to **skill detail pages** (`/library/skills/*`) and **hook detail pages** (`/library/hooks/*`) — all three show the same duplication signature.

Two distinct problems:

**Problem 1 — Duplicate calls (`capabilities` ×2, `me` ×2, `runs` ×2):**
The detail panel and the underlying library page each independently call `getCapabilities()`, `getMe()`, and `getWorkflows(limit=50)` on mount without sharing responses. The detail panel mounts as an overlay on the library page — both the panel and the page trigger their own fetches for identical data.

**Problem 2 — `runs?limit=50` on a library page (×2):**
`GET /api/runs?limit=50` (37.2 KB) fires twice on a page that shows no run history whatsoever. The agent/skill/hook detail panels show: overview, system prompt, pipeline role, skills list, hooks list, config. None of these sections need run history. Both calls come from the layout-level run list fetch (QA-PS-050/QA-PS-040) firing unconditionally on every route.

### Notes

This is the same systemic pattern as QA-PS-035 through QA-PS-050. The library detail pages are simply the library page (QA-PS-040, `me` ×2, `runs` ×1) with an additional capability-catalog duplication from the detail panel mounting on top, and the layout's unconditional `runs?limit=50` firing a second time.

Fixing QA-PS-040 (library page) and QA-PS-050 (`runs?limit=50` call sites) together would reduce this from 8 requests to 3.

### Browser / Log Signals

```
Network (Fetch/XHR) on /library/agents/material-analyzer:
  GET /api/capabilities   × 2  (23.6 KB × 2 = 47.2 KB — times: 40ms, 51ms)
  GET /api/runs?limit=50  × 2  (37.2 KB × 2 = 74.4 KB — times: 115ms, 95ms — not needed)
  GET /api/me             × 2  (0.4 KB × 2 — times: 34ms, 44ms)
  GET /api/workflows      × 1  (22.6 KB — 1.26s — expected)
Total: 8 requests, 149 KB transferred
Initiator: LibraryPage.tsx:828
```

### Files

- `frontend/src/app/library/agents/[id]/` or `frontend/src/components/library/` — agent/skill/hook detail panel: check which components independently call `getCapabilities` and `getMe`
- `frontend/src/` — shared layout component calling `runs?limit=50` unconditionally (same as QA-PS-035–QA-PS-050)

<a id="qa-ps-052"></a>

## QA-PS-052 — Actively running workflow stream page fires 45-59 requests (1.3-2 MB) during a single run — runs?limit=50 called 10+ times during live execution, workflows fetched 3×, gate-events and gate state fetched 3× each

- **Page:** Live run stream page (actively running workflow)
- **Route:** /runs/{id}/stream
- **Severity:** High
- **Found by:** PS
- **Found at:** 2026-09-17
- **User:** qa-admin@flowinqa.com

### Reproduction

1. Sign in as `qa-admin@flowinqa.com`
2. Start a new workflow run (e.g. User Stories — "login feature")
3. Open browser DevTools → Network tab → filter to **Fetch/XHR**, enable **Keep log**
4. Observe all requests that fire while the run is actively executing (6 agents, ~5 minutes)
5. Approve review gates as they appear during the run
6. Wait for the run to complete
7. Count total requests and note duplicates

### Expected

A running workflow stream should fire only:
- `GET /api/runs/{id}` — once at open, to load run details
- `GET /api/runs/{id}/events?after=0` — once, for initial SSE replay then SSE stream takes over
- `GET /api/runs/{id}/family` — once
- `GET /api/runs/{id}/sandbox/refs` — once
- `GET /api/workflows` — once, for workflow catalog
- `GET /api/runs?limit=50` — once at open for recents badge; then once after the run completes

Total: ~7 requests at open + the SSE stream handling everything live. No repeated fetches during execution.

### Actual

The run stream fires **45–59 requests totalling 1.3–2 MB** across a 5-minute run with 6 agents and 2 review gates:

**Duplicate and unnecessary calls observed:**

| Request | Count (across 3 screenshots) | Size | Problem |
|---------|------------------------------|------|---------|
| `GET /api/runs?limit=50` | **10+ times** | 37.2 KB × 10+ = **372+ KB** | Fires on every live gate approval, `pipeline_complete`, clarification — QA-PS-050 live path |
| `GET /api/workflows` | **3×** | 22.6 KB × 3 = **67.8 KB** | Workflow catalog fetched 3 times |
| `GET /api/runs/{id}/gate-events` | **3×** | 0.4 KB × 3 | Gate events re-fetched on each gate action |
| `GET /api/gate` (gate state) | **3×** | 0.4 KB × 3 | Gate state fetched 3 times |
| `GET /api/runs/{id}` (full run record) | **3×** | ~1 KB × 3 | Run record re-fetched on gate actions |
| `GET /api/runs/{id}/family` | **2×** | 0.7 KB × 2 | Duplicate family fetch |
| `GET /api/runs/{id}/sandbox/refs` | **2×** | 0.4 KB × 2 | Duplicate refs fetch |

**Three compounding problems:**

**Problem 1 — Live path of QA-PS-050:**
Unlike opening a *completed* run (where `runs?limit=50` fires during durable replay), this is a *live* run where every real SSE event triggers a genuine refetch. Each gate approval fires `review_gate_approved` → `runs?limit=50` (page.tsx:2089). Each clarification answer fires `questionnaire_complete` → `runs?limit=50` (page.tsx:2021). `pipeline_complete` fires two refetches (immediate + delayed 2s). The T38 cascade doubles each one. For a run with 2 gates + clarifications + completion: ~10 `runs?limit=50` calls at 37.2 KB each = **372 KB** of run list data fetched while actively watching the run.

**Problem 2 — Gate action triggers redundant refetches:**
Screenshot 3 shows `postGate` (api.ts:1351) and `InlineGateActions.tsx:159` as initiators alongside `page.tsx:4176`. When the user approves a gate, `postGate` correctly sends `POST /api/runs/{id}/gate`. But the approval then triggers: `gate-events` re-fetch, `gate` state re-fetch, full `runs/{id}` record re-fetch — all independently by different components rather than relying on the incoming `review_gate_approved` SSE event that already confirms the approval.

**Problem 3 — Structural: DashboardPage mounting under stream view:**
Screenshot 2 shows `AgentThinkingTab.tsx:218`, `AgentThinkingTab.tsx:239`, `PreviewPanel.tsx:1712`, `DashboardLayout.tsx:3222`, `DashboardPage` (page.tsx:3921) all firing simultaneously — the same home page component mounting under the stream view as in QA-PS-044/045/047. `Promise.all` (VM1140) confirms the home page's parallel batch fetches are running alongside the stream view's own fetches.

`GET /api/workflows` (22.6 KB) being fetched 3 times is a consequence of this: the stream view, `AgentThinkingTab`, and the underlying `DashboardPage` each independently fetch the workflow catalog on mount.

**Total impact for a single 5-minute User Stories run:**
- Screenshot 1 (during run, 4/6 agents): 45/51 requests, 1,338 KB
- Screenshot 2 (run completing): 45/58 requests, 1,918 KB
- Screenshot 3 (run complete): 46/59 requests, 1,955 KB

Over the course of one run, the stream page generates **~2 MB of API traffic**, of which ~1.3 MB is redundant.

### Browser / Log Signals

```
Screenshot 1 (during run, 4/6 agents):
  runs?limit=50    × 3+ (visible, still accumulating)
  workflows        × 2
  gate-events      × 2
  stream (SSE)     × 1 (903 KB — 3.7 min — expected)

Screenshot 2 (run completing):
  runs?limit=50    × 4+ more  (answers, gate approvals, pipeline_complete)
  workflows        × 1 more
  gate-events      × 1 more
  runs/{id}        × 3

Screenshot 3 (post-completion):
  runs?limit=50    × 5+ more  (pipeline_complete immediate + delayed, T38 cascade)
  gate             × 3
  sandbox          × 1
  events?after=6818 × 1 (SSE reconnect — expected)
  runs?limit=50    × 5+ (continuing to cascade)

Initiators (Screenshot 2): AgentThinkingTab.tsx:218/239, PreviewPanel.tsx:1712,
  DashboardLayout.tsx:3222, DashboardPage (page.tsx:3921), Promise.all VM1140
Initiators (Screenshot 3): postGate (api.ts:1351), InlineGateActions.tsx:159,
  page.tsx:4176
```

### Files

- `frontend/src/app/[...view]/page.tsx` — 12 `getWorkflows` call sites in `handleWebSocketMessage` — fire on every live event; `page.tsx:4176` refetch after gate action
- `frontend/src/components/results/InlineGateActions.tsx` (line 159) — independently re-fetches gate state after approval instead of relying on incoming SSE
- `frontend/src/components/results/AgentThinkingTab.tsx` (lines 218, 239) — independently fetches workflow catalog
- `frontend/src/` — route configuration: `/runs/{id}/stream` should replace home page component (same fix as QA-PS-044/045/047)
- `frontend/src/components/history/WorkflowHistory.tsx` (line 250) — T38 cascade doubling every live refetch

<a id="qa-ps-053"></a>

## QA-PS-053 — Revision pipeline stream page fires 30-45 requests (2.5 MB) with duplicate API calls — family fetched 3×, SSE replay fired twice, parent run record fetched, and home page mounts under revision stream

- **Page:** Live revision run stream (started from concierge chat)
- **Route:** /runs/{revision-id}/stream
- **Severity:** High
- **Found by:** PS
- **Found at:** 2026-09-17
- **User:** qa-admin@flowinqa.com

### Reproduction

1. Sign in as `qa-admin@flowinqa.com`
2. Open any completed run that supports revision (e.g. a User Stories run)
3. In the concierge chat, type a revision instruction (e.g. "Add a Google authentication user story")
4. Open browser DevTools → Network tab → filter to **Fetch/XHR**, enable **Keep log**
5. Submit the revision — observe all requests that fire as the revision run starts and executes

### Expected

Starting a revision run from the concierge chat fires only what is needed:
- `GET /api/runs/{revision-id}` — once, to load the new revision run's details
- `GET /api/runs/{revision-id}/events?after=0` — once, for SSE replay/stream
- `GET /api/runs/{revision-id}/family` — once, for revision family context
- `GET /api/runs/{revision-id}/sandbox/refs` — once
- `GET /api/runs?limit=50` — once, to update recents badge with new revision run

Total: ~5 requests. The revision is a 1-agent run ("Backlog Revision Agent") — it should be very lightweight.

### Actual

The revision stream fires **30–45 requests totalling 2,521 KB** immediately after starting:

**Duplicate and wrong-page calls observed:**

| Request | Count | Size | Problem |
|---------|-------|------|---------|
| `GET /api/workflows` | **2×** | 22.6 KB × 2 = 45.2 KB | Workflow catalog fetched twice |
| `GET /api/gate-events` | **2×** | 0.4 KB × 2 | Duplicate |
| `GET /api/runs/{revision-id}` | **2×** | 1.4 KB × 2 | Revision run record fetched twice |
| `GET /api/runs/{parent-id}` | **1×** | **131 KB** | Full parent run record fetched as side effect |
| `GET /api/runs?limit=50` | **1×** (visible) | 37.2 KB | Live event → refetch (QA-PS-050) |
| `GET /api/events?after=0` | **2×** | 1,893 KB + small | SSE event replay fired **twice** |
| `GET /api/family` | **3×** | 0.7 KB × 3 | Family fetched 3 times — 2 redundant |
| `GET /api/me` | **2×** | 0.4 KB × 2 | Duplicate |
| `GET /api/sandbox` | **1×** | — | Expected |
| `GET /api/refs` | **1×** | — | Expected |

**Three revision-specific problems on top of the shared issues:**

**Problem 1 — SSE event replay fired twice (1,893 KB × 2):**
`GET /api/runs/{revision-id}/events?after=0` fires twice. The first is the legitimate durable replay for the revision run. The second is triggered by the `DashboardPage` component (page.tsx:3921) mounting under the stream view — the same structural issue as QA-PS-044/045/047/052. The home page mounts alongside the revision stream and independently triggers its own event replay for the same run, doubling the 1,893 KB payload. **This alone is ~1.9 MB of duplicate SSE data.**

**Problem 2 — Parent run record fetched (131 KB):**
`GET /api/runs/{d72c4822...}` (the original User Stories parent run, 131 KB) fires during the revision run's stream. This happens because the revision stream page fetches the full revision family (parent + revision member) and then loads each member's full run record. The parent run record is large (131 KB for a 352.1K token run). Fetching the full parent record is heavyweight for what the revision stream actually needs — it only needs the parent's output content, not its full run record with all metadata.

**Problem 3 — `getWorkflowDefinitions` firing (api.ts:1720):**
The full workflow definitions catalog fires from `HomeLaunchGrid` initialising under the stream view. This is part of the same home page overlay structural issue — `HomeLaunchGrid` loads the workflow card grid's data in the background while the user is watching their revision run.

**Shared problems (same as QA-PS-052):**
- `family` ×3 (only 2 members — parent + revision — but fetched 3 times)
- `workflows` ×2
- `gate-events` ×2
- `me` ×2
- `runs?limit=50` fires on live SSE events (QA-PS-050 live path)

### Why revision runs are worse than standard runs

A standard run (QA-PS-052) has one SSE event stream. A revision run has TWO streams that are relevant — the parent run's events (for the concierge chat transcript history) and the revision run's new events. Both are loaded, and with the `DashboardPage` overlay doubling each replay, the revision stream ends up fetching **2 event replays × 2 (due to overlay) = 4 replay requests** for a run that has been live for only seconds.

The parent run record (131 KB here) grows with run size — for a large prototype or user stories run with many agents, this could be 500 KB+ fetched as a background side effect every time the user starts a revision.

### Browser / Log Signals

```
Network (Fetch/XHR) immediately after revision starts:
  stream (SSE)                      × 1  (active stream — expected)
  GET /api/events?after=0           × 2  (1,893 KB × 1 — SSE replay fired twice)
  GET /api/runs/{revision-id}       × 2  (1.4 KB × 2)
  GET /api/runs/{parent-id}         × 1  (131 KB — parent run full record)
  GET /api/family                   × 3  (0.7 KB × 3)
  GET /api/workflows                × 2  (22.6 KB × 2)
  GET /api/gate-events              × 2
  GET /api/runs?limit=50            × 1+ (live SSE events trigger more)
  GET /api/me                       × 2
Total: 30/45 requests, 2,521 KB

Initiators:
  AgentThinkingTab.tsx:198, 239
  PreviewPanel.tsx:1712
  DashboardLayout.tsx:3222   ← home page under revision stream
  DashboardPage page.tsx:3921 ← home page under revision stream
  getWorkflowDefinitions api.ts:1720 ← HomeLaunchGrid loading under stream
```

### Files

- `frontend/src/app/[...view]/page.tsx` (line 3921) — `DashboardPage` mounting under revision stream route, causing double SSE replay
- `frontend/src/components/results/AgentThinkingTab.tsx` (lines 198, 239) — independently fetches workflow catalog and parent run data
- `frontend/src/components/preview/PreviewPanel.tsx` (line 1712) — triggers parent run fetch as part of family context loading
- `frontend/src/` — route configuration: `/runs/{id}/stream` should replace home page (same fix as QA-PS-044/045/047/052)
- `frontend/src/lib/api.ts` (line 1720) — `getWorkflowDefinitions` called by `HomeLaunchGrid` loading under stream

---

<a id="qa-ps-054"></a>

## QA-PS-054 — Download button serves the latest version's file while a pinned older version is on screen

- **Page:** Run detail — header Download button, while an older version is pinned
- **Route:** /runs/{id}
- **Severity:** High
- **Found by:** Source investigation during the QA-PS-007 escalation (see Notes — **not yet reproduced in a browser**)
- **Found at:** 2026-09-22
- **User:** qa-admin@flowinqa.com

### Reproduction

1. Sign in as `qa-admin@flowinqa.com`
2. Open a run that has at least two completed versions in the same family (a run plus a revision, so the Version menu lists v1 and v2)
3. Confirm the page is showing the latest version, and note the deliverable's content on screen
4. Open the **Version** menu in the run header and pin the **older** version (v1)
5. Confirm the preview updates to v1's content and the amber "viewing an older version / read-only" banner appears
6. Click the header **Download the deliverable** button (aria-label `Download the deliverable`)
7. Open the downloaded file and compare its content against what is on screen

### Expected

The downloaded file contains **v1's** content — the same version the preview is showing and the banner says you are viewing.

### Actual

The downloaded file contains the **latest version's** content (v2), not the pinned v1 that is on screen. There is no warning, no error, and no visible difference in the button's behaviour — the banner still says you are viewing an older version while the file you receive is the newer one.

The same is expected on the no-declared-file fallback path, where the button downloads a whole-workspace zip instead of a single file: that zip is also served from the latest version rather than the pinned one.

### Browser Signals

```
Expected on the request the Download button issues:
GET /api/runs/{id}/sandbox/file?path=<deliverable>     <- no `ref` query param
Compare against the request the preview issues for the same pinned version,
which does carry a `ref` for the pinned version's tag.
Console: expected clean (the bug is silent)
```

### Notes

**This bug was found by reading the source during the QA-PS-007 escalation, not by observing it on screen.** Two independent analyses reached it separately. It has **not** been reproduced in a browser yet, because no run family with usable on-disk versions was available at the time of writing — every completed PPT run in the database has no sandbox directory on disk.

Treat the reproduction steps above as **predicted, not observed**. The validator should expect to confirm or refute them from cold, and `UNREPRODUCIBLE` here is a meaningful result rather than a reporting failure.

Related: QA-PS-007 (same Download button, but that bug is about the file's *name*; this one is about the file's *content* and is the more serious of the two). QA-SG-013 (Download button disabled on user story runs) touches the same control. QA-EX-001 (version menu changed files but not steps) is in the same Version-menu area.

---

<a id="qa-ps-055"></a>

## QA-PS-055 — Pinned older version silently reverts to Latest the moment any tracked revision completes

- **Page:** Run detail — version dropdown / Preview, while an older version is pinned
- **Route:** /runs/{id}
- **Severity:** High
- **Found by:** Source analysis during the versioning audit (see Notes — **not yet reproduced in a browser**)
- **Found at:** 2026-09-22
- **User:** qa-admin@flowinqa.com

### Reproduction

1. Sign in as `qa-admin@flowinqa.com`
2. Open a run family that has several completed versions (e.g. the 6-version family rooted at `4d55165d-59b5-4571-b5ac-1ce7aebc3cbf`)
3. Pin an older version — select **v2** in the version dropdown. Confirm the Preview shows v2's content and the "viewing an older version" banner appears
4. **Leave that tab open on v2**, and from the same tab start (or have already running) a revision on that family — anything that produces a `*_revision` pipeline this tab is tracking
5. Wait for that revision to complete, without touching the dropdown
6. Observe the Preview and the version chip

### Expected

The pinned selection is the user's explicit choice and survives. v2 stays on screen, the banner stays, and the arrival of a newer version is at most an unobtrusive notice — never a silent replacement of what is being viewed.

### Actual

The instant the revision completes, the pinned view is **silently replaced by Latest**. Both `viewingVersion` and `sandboxSelectedRef` are cleared, the banner disappears, and the Preview jumps to the newest content. No warning, no undo, and the user is now looking at different content than they selected — with nothing on screen saying it changed.

Also expected to occur when the completing revision is **backgrounded** (started elsewhere, merely tracked by this tab), not only when it was started from this screen.

### Browser Signals

```
Expected: no error. The bug is silent.
The chip and banner change without any user interaction.
```

### Notes

**Found by source analysis, not by observing it on screen.** It has NOT been reproduced in a browser — the investigation was barred from launching runs. Treat the reproduction steps as predicted, not observed; `UNREPRODUCIBLE` is a meaningful outcome here.

The mechanism, for the analyzer: `page.tsx:1495-1522`'s `pipeline_complete` handler calls `setContentSourceRunId(completingRunId)` for **any** `*_revision`-typed completion the tab is tracking, because `isRevisionCompletion` (`:1509`) deliberately bypasses the foreign-run guard at `:1497-1500`. That bypass is FIX-088 (2026-07-22), which fixed an earlier "chip stuck at v1" bug and never considered pinning. `PreviewPanel.tsx:883` then resets `viewingVersion` unconditionally on the resulting prop change, with no check for an active pin.

A second, **inferred** defect sits alongside it (ISS-745): `isRevisionCompletion` checks only the type suffix and never lineage, so a concurrently-tracked revision from an *unrelated family* may be able to redirect the current screen to its content.

Related: QA-PS-030 (fixed, FIX-601), QA-PS-054 (Download ignores the pinned ref), ISS-697 (tags missing entirely).

---

<a id="qa-ps-056"></a>

## QA-PS-056 — Workspace tab serves the latest file content when an older version is selected

- **Page:** Run detail — Workspace tab, with an older version selected
- **Route:** /runs/{id}
- **Severity:** Critical
- **Found by:** Version matrix audit
- **Found at:** 2026-09-22
- **User:** qa-admin@flowinqa.com

### Reproduction

1. Sign in as `qa-admin@flowinqa.com`
2. Open a run family with several completed versions whose content genuinely differs (e.g. the family rooted at `4d55165d-59b5-4571-b5ac-1ce7aebc3cbf`, where v1 is 27,549 bytes and v6 is 13,963 bytes)
3. Select **v1** in the version dropdown. Confirm the "Viewing v1 (read-only)" banner is showing
4. Open the **Workspace** tab
5. Click `presentation.html` to open it

### Expected

The file viewer shows **v1's** content — the heading `Subsea Fibre Splice Operations`, 27,549 bytes — matching the version named in the banner.

### Actual

The viewer shows the **latest** content (`SPLICE REVISION FOUR`, 13,963 bytes) while the banner still says "Viewing v1 (read-only)". Reproduced for v1, v2, v3, v4 and v5; only v6 looks right, because v6 happens to be the current HEAD.

Confirmed at the API level: `GET /api/runs/{run_id}/sandbox/file?path=presentation.html` returns byte-identical content for all five non-head run ids in the family.

### Notes

**The backend is behaving correctly — the UI is not.** Every family member resolves to one shared sandbox, so a request with no `ref` parameter correctly serves the current working tree. Git genuinely holds the right bytes per version (`git show v1:presentation.html` returns the 27,549-byte v1 deck). The defect is that the Workspace file viewer never passes the selected `ref`.

This is the **same mechanism** as QA-PS-054 (header Download ignores the pinned version). Two separate surfaces omit `sandboxSelectedRef` while the Preview panel passes it correctly — which is why Preview switches versions properly and these two do not. Likely one fix location for both.

Related: QA-PS-054, QA-PS-032 (Workspace shows 0 B for versioned refs — sizes, not content), ISS-665 (FilesTab ref-blind resolution, open since 2026-09-17), ISS-706.

Not a regression from FIX-601: it was always broken, and only became observable once versions' bytes genuinely differed.

---

<a id="qa-ps-057"></a>

## QA-PS-057 — Steps tab "Starting point" never follows the version dropdown, while the agent list does

- **Page:** Run detail — Steps tab, "Starting point" card
- **Route:** /runs/{id}
- **Severity:** High
- **Found by:** PS (reported), reproduced 20/20 by the version matrix audit
- **Found at:** 2026-09-22
- **User:** qa-admin@flowinqa.com

### Reproduction

1. Sign in as `qa-admin@flowinqa.com`
2. Open a run family with several completed versions (e.g. the family rooted at `4d55165d-59b5-4571-b5ac-1ce7aebc3cbf`, whose v1 brief is "Subsea Fibre Splice Operations" and whose v2–v6 are revisions with their own distinct instructions)
3. Go to the **Steps** tab
4. Select **v2** in the version dropdown, then v3, v4, v5, v6
5. After each selection, compare the **agent list** against the **"Starting point"** text

### Expected

Both follow the selection. Each revision is its own run with its own brief, so selecting v3 should show v3's instruction ("Change the main heading to SPLICE REVISION THREE and make it green").

### Actual

The **agent list updates correctly every time** (3 agents for v1, a single Deck Revision Agent for v2–v6). The **"Starting point" never changes** — it keeps showing the brief of whichever run the page was originally opened at, for every version selected.

Reproduced **10/10 in an ascending sweep and 10/10 in a descending + large-jump sweep**, across two passes with no reload. It never self-corrects. Only the version the page was opened at displays correctly.

### Notes

Root cause confirmed by source trace. `VersionView` (`PreviewPanel.tsx:536-549`), the per-version snapshot built by `versionViewFrom()` on every switch, carries `agents` / `pipelineState` / `agentOutputs` / `content` / `genericDeliverable` — but has **no `runInput` field**, even though the `WorkflowRun` it is built from has `.input` available. Both version-resolution paths (`handleSelectVersion` `:808-838`, and the `/versions/{n}` URL-pin effect `:899-913`) route through that one function, so neither can produce a version-aware brief.

So `effAgents` / `effPipelineState` / `effAgentOutputs` (`:950-952`) correctly track the selection, while `runInput={runInput}` at `:1783` is the raw un-derived prop, tracing to `DashboardLayout.tsx:3313` → `submittedBrief` (`page.tsx:2243`), which is set only on opening a run or switching live run — never by the version dropdown.

**Why it looked like "stuck at v3":** it freezes on whichever run the page was last navigated to. On this family (URL rooted at v1) it always showed v1; the original report saw v3 because that was the run opened at the time. Same mechanism, different frozen value.

**This is NOT QA-PS-033.** That bug requires an *untagged* member, so `handleSelectVersion` never runs and agents freeze too. This one requires a *fully tagged* family — the handler runs correctly for everything except this one field. Mutually exclusive on any single selection. QA-PS-033 should stay UNREPRODUCIBLE as its own row.

**Fix location:** add a `runInput` field to `VersionView` + `versionViewFrom()` (`PreviewPanel.tsx:536-575`) and thread `viewingVersion?.runInput ?? runInput` at the two consumers (`:1783` Steps, `:1745` Files). One shared place, both callers.

**Fix risk:** `StartingPointCard.tsx:33` documents its `input` prop as the raw string (it parses internally), but `submittedBrief` upstream is already parsed and trimmed (`page.tsx:2728-2730`). The new field must match one shape consistently or pinned vs live views render differently — the same class of bug FIX-130 already fixed once.

### Second, separate finding from the same sweeps

The **agent list** shows a transient one-behind lag on large non-adjacent jumps (observed v6 → v2): a snapshot immediately after the click still showed v6's agent entry, self-correcting ~10s later with no user action. The network log for that transition shows a sandbox-file fetch pairing the **old run id** with the **new ref** — a stale run-id closure racing a fresh ref value. Lower severity (self-heals), but it is a real race and worth its own look.

---

<a id="qa-ps-058"></a>

## QA-PS-058 — "Latest (live)" is always offered, even on a finished run where it duplicates the newest version

- **Page:** Run detail — version dropdown
- **Route:** /runs/{id}
- **Severity:** Medium
- **Found by:** PS
- **Found at:** 2026-09-22
- **User:** qa-admin@flowinqa.com

### Reproduction

1. Sign in as `qa-admin@flowinqa.com`
2. Open a run family where every version has completed and been tagged (e.g. the family rooted at `4d55165d-59b5-4571-b5ac-1ce7aebc3cbf`, v1–v6)
3. Confirm nothing is running
4. Open the version dropdown

### Expected

`Latest (live)` has one precise meaning — **uncommitted work in progress**. It should appear only while a run in the family is in flight, and be replaced by that run's tag once it finalises:

```
v1 working      →  Latest (live)
v1 done         →  v1
v2 working      →  Latest (live), v1
v2 done         →  v1, v2
```

### Actual

`Latest (live)` is always the first option, on every run, whether or not anything is running. On a finished family it points at exactly the same bytes as the newest tag, so the menu offers the same content twice under two names.

### Notes

Not a data-correctness defect — `Latest (live)` resolves correctly. It is a meaning problem: an entry that sometimes means "work in progress" and sometimes means "the same thing as v6" cannot be reasoned about, and it is the reason the version menu reads as confusing.

**There is one case where `Latest (live)` is genuinely load-bearing and must NOT be hidden.** When a completed run's tagging silently failed (`ISS-697` — tag creation is best-effort at `engine.py:2349-2456`, and `WorkflowRun.git_tag` is written only after a successful git call), there is no tag to select and `Latest (live)` is the only way to reach that content. Confirmed live on family `2708dbf1`, whose DB rows claim v1/v2/v3 while git holds only `v3`.

So the rule is three-way, not two-way:

| State | Dropdown |
|---|---|
| a run in the family is in flight | `Latest (live)` + completed tags below |
| all done, newest member tagged | tags only, newest first |
| all done, newest member NOT tagged | `Latest (live)` + a warning that the version was never captured |

Hiding `Latest (live)` without that third branch would turn a silent tagging failure into silent data loss.

**An existing test pins the current behaviour** — `RunHeader.test.tsx:80`: *"Latest (live) is the first option, newest tag next"*. That assertion is deliberate and must be revised as part of this change, not worked around.

Related: ISS-697 (tags missing), QA-PS-030/054/055/056/057 (all fixed, ref-passing cluster).

---

<a id="qa-ps-059"></a>

## QA-PS-059 — Agent detail and Config tab call GET /api/capabilities, /api/runs?limit=50 and /api/me twice each
- **Page:** Library agent detail + Config tab
- **Route:** /library/agents/*
- **Severity:** Medium
- **Found by:** PS
- **Found at:** 2026-09-17

### Reproduction

> **Body missing.** This row was filed under the id `QA-PS-051`, which already belonged to
> [QA-PS-051](#qa-ps-051). Two different bugs shared one id and one anchor, so a stage could
> update the wrong row. The id collision is resolved here; the reproduction text was never
> written to a section of its own and is not invented.

### Actual

Agent detail and its Config tab each issue `GET /api/capabilities`, `GET /api/runs?limit=50`
and `GET /api/me` twice. Run history is not needed on an agent view at all. (Summarised from
the ledger row's own title — not a reporter-written body.)

### Notes

Likely a narrower restatement of [QA-PS-051](#qa-ps-051), which covers agent, skill and hook
detail pages. QA-PS-051 does not mention the Config tab. Whether this is a duplicate is a
validator or analyzer call and has deliberately not been decided here.
