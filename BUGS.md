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

<a id="qa-kb-001"></a>

## QA-KB-001 — Footer animation ignores prefers-reduced-motion accessibility setting

- **Page:** /runs/{id}
- **Route:** /runs/{id}
- **Severity:** High
- **Found by:** knowledge-base sweep (open card BUG-018-GROUNDED-CONTEXT)
- **Found at:** 2026-10-01 20:50
- **Reproduction mode:** Static — reproduce by the check below (read/grep/short script). No browser needed.

### Reproduction

1. In browser DevTools, enable 'Prefers reduced motion' emulation (or add @media (prefers-reduced-motion:reduce) { ... } to CSS)
2. Navigate to a completed run at /runs/{id}
3. Click 'Run summary' toggle to expand/collapse the footer strip
4. Observe animation plays over ~220ms despite reduced-motion preference

### Expected

When prefers-reduced-motion:reduce is active, footer opens/closes instantly without animation (duration 0).

### Actual

Footer strip animates with 220ms transition even when user has reduced-motion accessibility preference enabled.

### Notes

Logged from the existing open knowledge card [BUG-018-GROUNDED-CONTEXT](.knowledge/cards/20260717-1903-BUG-018-GROUNDED-CONTEXT.md), which already holds the root cause.
Link that card from the ledger row and update it when this closes; do not mint a duplicate root card.
Agreed minimal fix (two independent reviewers, static read of the current code): In /frontend/src/components/chat/RunChatLane.tsx, change the import at line 35 to `import { motion, useReducedMotion } from "motion/react";`. At the top of SettledSummaryStrip (~line 790) add `const reduce = useReducedMotion();`. At line 829 change the transition to `transition={reduce ? { duration: 0 } : { duration: 0.22, ease: "easeOut" }}`. Do not use `MotionConfig reducedMotion="user"`, because it only disables transform and layout animations, not height or opacity. Optionally add one test in RunChatLane.test.tsx that mocks `matchMedia` for reduce, clicks the toggle, and asserts `aria-expanded` is true with no error.

<a id="qa-kb-002"></a>

## QA-KB-002 — App creation URL renders user-stories workflow instead of app_builder

- **Page:** /create/app
- **Route:** /create/app
- **Severity:** High
- **Found by:** knowledge-base sweep (open card BUG-023)
- **Found at:** 2026-10-01 20:50
- **Reproduction mode:** Browser — reproduce from the URL below.

### Reproduction

1. Navigate to /create/app
2. Observe the launch panel that opens
3. The workflow type shows GENERATE PRODUCT BACKLOG (user_stories default) instead of GENERATE APP BLUEPRINT

### Expected

The /create/app URL displays the app_builder workflow type in the launch panel

### Actual

The /create/app URL displays the user_stories workflow type (the default fallback) in the launch panel

### Notes

Logged from the existing open knowledge card [BUG-023](.knowledge/cards/20260827-BUG-023.md), which already holds the root cause.
Link that card from the ledger row and update it when this closes; do not mint a duplicate root card.
Agreed minimal fix (two independent reviewers, static read of the current code): In page.tsx initialWorkflowTypeFor, replace the single ternary with a switch. It should return "app_builder" for "create-app", "user_stories" for "create-user-stories", and parsed.pipelineType for "create-workflow". Otherwise return undefined. Optionally add a small unit test asserting the two mappings.

**Interrupted fix (2026-10-01 22:40):** the first fixer for this bug was killed by an API limit mid-edit. It may have left a PARTIAL change in: frontend/src/app/[...view]/page.tsx, tests/integration/e2e/suites/03_launch_panels/test_launch_panels.py and the integration docs (MANIFEST.md, PAGES.md, DEFECTS-OBSERVED.md, screens/03-launch-panels.feature.md). Before editing, read `git diff` for those files, keep only the hunks that belong to this bug's fix and complete them; never revert hunks that belong to other QA-KB bugs (other bugs share some of these files).

<a id="qa-kb-003"></a>

## QA-KB-003 — status.py reports card text as commit SHA in branch line and JSON

- **Page:** n/a (code-level)
- **Route:** n/a (code-level)
- **Severity:** High
- **Found by:** knowledge-base sweep (open card BUG-128)
- **Found at:** 2026-10-01 20:50
- **Reproduction mode:** Test — reproduce by running the command below; it should fail (or misbehave) as described. No browser needed.

### Reproduction

1. cd /Users/bilala/Developer/Projects/VELOCITY-AI-worktrees/feat-user-stories-v2
2. python3 tools/knowledge/status.py
3. Observe branch line shows '---' where SHA should be
4. python3 tools/knowledge/status.py --json | head -20
5. Observe 'head' field contains ~2000 chars of markdown instead of commit SHA

### Expected

Branch line shows commit SHA (8 chars), e.g. 'branch: feat-branch @ a1b2c3d4'. JSON head field is an 8-character commit SHA.

### Actual

Branch line shows '---' (card frontmatter delimiter) or first 8 chars of card text. JSON head field contains 2000+ characters of DOMAIN card markdown.

### Notes

Logged from the existing open knowledge card [BUG-128](.knowledge/cards/20260918-BUG-128.md), which already holds the root cause.
Link that card from the ledger row and update it when this closes; do not mint a duplicate root card.
Agreed minimal fix (two independent reviewers, static read of the current code): In tools/knowledge/status.py, rename the loop variable at :319 to `text`, and change its use in the regex call at :321 from `head` to `text`. Leave :144, :342 and :355 untouched.

<a id="qa-kb-004"></a>

## QA-KB-004 — VirtualEnv filter uses exact name match, misses .venv312 variants

- **Page:** n/a (code-level)
- **Route:** n/a (code-level)
- **Severity:** High
- **Found by:** knowledge-base sweep (open card BUG-129)
- **Found at:** 2026-10-01 20:50
- **Reproduction mode:** Static — reproduce by the check below (read/grep/short script). No browser needed.

### Reproduction

1. Grep for PY_EXCLUDE in tools/knowledge/build_architecture.py; observe it lists exact names: '.venv', 'venv', '__pycache__', etc.
2. Note that '.venv312' and other version-suffixed variants (.venv-3.13, .venv311, etc.) are not listed
3. Verify line 159 uses set intersection (PY_EXCLUDE & set(path.parts)) — exact-name matching only, not prefix test

### Expected

All virtualenv directories (.venv, .venv312, .venv-3.13, venv) are excluded from source scans so modules.json contains only VELOCITY source

### Actual

Only hardcoded exact names (.venv, venv) match; version-suffixed variants escape, allowing site-packages files into modules.json (e.g. pip, langsmith internals from .venv312/lib/python3.12/site-packages/)

### Notes

Logged from the existing open knowledge card [BUG-129](.knowledge/cards/20260918-BUG-129.md), which already holds the root cause.
Link that card from the ledger row and update it when this closes; do not mint a duplicate root card.
Agreed minimal fix (two independent reviewers, static read of the current code): In build_architecture.py, add a helper `_is_venv(part) = part == "venv" or part.startswith(".venv")`. Change the line 159 condition to `if PY_EXCLUDE & set(parts) or any(_is_venv(x) for x in parts): continue`. Leave "tests", "runs" and the caches exact. Optionally apply the same test at line 362. Then regenerate modules.json and MOD-backend.md, which is a bookkeeping step the card already names.

<a id="qa-kb-005"></a>

## QA-KB-005 — hook_run reducer loses payload, defaults to audit_logger/continue

- **Page:** n/a (code-level)
- **Route:** n/a (code-level)
- **Severity:** High
- **Found by:** knowledge-base sweep (open card ISS-107)
- **Found at:** 2026-10-01 20:50
- **Reproduction mode:** Test — reproduce by running the command below; it should fail (or misbehave) as described. No browser needed.

### Reproduction

1. Trigger a hook_run message with payload { hook: 'secret_scan', outcome: 'block', ... }
2. Inspect the Redux state hookRuns array or add a debug log in useWorkflow.ts:1703
3. Observe: entry shows hook='audit_logger', outcome='continue' instead of actual payload values

### Expected

hookRuns entries reflect actual hook type and outcome from message payload (e.g., secret_scan/block)

### Actual

hookRuns entries always show hook='audit_logger', outcome='continue'; real payload is lost

### Notes

Logged from the existing open knowledge card [ISS-107](.knowledge/cards/20260812-1400-ISS-107.md), which already holds the root cause.
Link that card from the ledger row and update it when this closes; do not mint a duplicate root card.
Agreed minimal fix (two independent reviewers, static read of the current code): In frontend/src/hooks/useWorkflow.ts:1703 change `const hookData = (msg.data as Record<string, unknown>) || {};` to `const hookData = (msg.data as Record<string, unknown>) || (msg as Record<string, unknown>);`. Add one vitest case that dispatches a flat `{type:"hook_run", hook, event, outcome:"block"}` and asserts hookRuns[0].outcome === "block". Optional: strip `type` from detail.

<a id="qa-kb-006"></a>

## QA-KB-006 — Gate rejection persists audit record with action='approve' instead of action='reject'

- **Page:** n/a (code-level)
- **Route:** n/a (code-level)
- **Severity:** High
- **Found by:** knowledge-base sweep (open card ISS-128)
- **Found at:** 2026-10-01 20:50
- **Reproduction mode:** Test — reproduce by running the command below; it should fail (or misbehave) as described. No browser needed.

### Reproduction

1. cd backend && python3.11 -m pytest tests/unit/api/test_rest_gate_commands.py -v
2. Or: send a gate rejection via /api/runs/{run_id}/gate-response (action=reject) and query store to inspect the persisted record; action will read as 'approve' instead of 'reject'

### Expected

When a gate is rejected, the audit record persists action='reject' to accurately reflect the user's decision

### Actual

All three gate reject branches omit action= when calling set_review_response, so the store defaults to action='approve' (from store.py:143), falsely labeling rejections as approvals in the durable audit row

### Notes

Logged from the existing open knowledge card [ISS-128](.knowledge/cards/20260812-2046-ISS-128.md), which already holds the root cause.
Link that card from the ledger row and update it when this closes; do not mint a duplicate root card.
Agreed minimal fix (two independent reviewers, static read of the current code): In backend/app/api/run_commands.py, add action="reject" to the three reject-branch calls. At ~:326 use set_review_response(gate_key, approved=False, action="reject", edited_content=body.edited_content). At ~:1599 use art_store.set_review_response(gate_key, approved=False, action="reject"). At ~:1965 use art_store.set_review_response(_gk, approved=False, action="reject"). Then add a unit assertion that get_review_response(...)["action"] == "reject". The card's test_files path backend/tests/unit/test_rest_gate_commands.py does not exist, so locate the real gate-command test file first.

<a id="qa-kb-007"></a>

## QA-KB-007 — payload_json.seq diverges from run_events.seq after retry in append_event_at_or_after

- **Page:** n/a (code-level)
- **Route:** n/a (code-level)
- **Severity:** High
- **Found by:** knowledge-base sweep (open card ISS-135)
- **Found at:** 2026-10-01 20:50
- **Reproduction mode:** Test — reproduce by running the command below; it should fail (or misbehave) as described. No browser needed.

### Reproduction

1. cd backend
2. python3.11 -m pytest tests/ -k 'append_event' -v (or write a test that)
3. 1. Triggers a seq conflict by simulating two writers targeting the same seq
4. 2. Calls append_event_at_or_after with a conflicting seq
5. 3. Queries the resulting run_events row from the database
6. 4. Verifies that row.seq != JSON.parse(row.payload_json)['seq']

### Expected

payload_json['seq'] value matches the database row's seq column after any retry

### Actual

After a retry due to seq conflict, the row is persisted with seq=N but payload_json['seq']=N-1, causing data divergence

### Notes

Logged from the existing open knowledge card [ISS-135](.knowledge/cards/20260813-0005-ISS-135.md), which already holds the root cause.
Link that card from the ledger row and update it when this closes; do not mint a duplicate root card.
Agreed minimal fix (two independent reviewers, static read of the current code): In authz.py `append_event_at_or_after`, in the `except IntegrityError` branch after `attempt_seq = tail + 1`, add `if isinstance(payload_json, dict) and "seq" in payload_json: payload_json = {**payload_json, "seq": attempt_seq}`. The retry then persists a payload whose seq matches `row.seq`, and the caller's existing re-stamp (engine.py:4208, 15885) keeps the live frame in agreement. Callers without a seq key, such as the `run_resuming` marker at engine.py:13056, are untouched. Add one test that forces a collision at seq N and asserts the stored `payload_json["seq"]` equals `row.seq`.

<a id="qa-kb-008"></a>

## QA-KB-008 — Pipeline reconnect ignores 'degraded' status, leaves run showing as running

- **Page:** /runs/{id}
- **Route:** /runs/{id}
- **Severity:** High
- **Found by:** knowledge-base sweep (open card ISS-136)
- **Found at:** 2026-10-01 20:50
- **Reproduction mode:** Test — reproduce by running the command below; it should fail (or misbehave) as described. No browser needed.

### Reproduction

1. cd frontend && npm test -- useWorkflow.reconnect.test.ts
2. Extend test to send pipeline_reconnected with live:false status: 'degraded'
3. Observe: the handler fails to resolve isRunning to false because 'degraded' is not in TERMINAL_STATUSES

### Expected

The TERMINAL_STATUSES in useWorkflow.ts should include 'degraded', matching backend and other FE definitions, so reconnect events resolve terminal runs correctly.

### Actual

TERMINAL_STATUSES contains 'error' (never sent by backend) and omits 'degraded' (canonical backend status), causing reconnect to misclassify degraded runs as still running.

### Notes

Logged from the existing open knowledge card [ISS-136](.knowledge/cards/20260813-0005-ISS-136.md), which already holds the root cause.
Link that card from the ledger row and update it when this closes; do not mint a duplicate root card.
Agreed minimal fix (two independent reviewers, static read of the current code): In frontend/src/hooks/useWorkflow.ts:1505 add "degraded" to the TERMINAL_STATUSES array. Keep "error" in the list; do not replace it. Add one test next to the "failed" case in frontend/src/hooks/useWorkflow.reconnect.test.ts: pipeline_reconnected with live:false and status:"degraded" expects isRunning=false and sessionStorage active_pipeline_run_id cleared.

<a id="qa-kb-009"></a>

## QA-KB-009 — Concierge revision fails with pipeline_not_entitled on revision-run parents

- **Page:** n/a (code-level)
- **Route:** n/a (code-level)
- **Severity:** High
- **Found by:** knowledge-base sweep (open card ISS-160)
- **Found at:** 2026-10-01 20:50
- **Reproduction mode:** Test — reproduce by running the command below; it should fail (or misbehave) as described. No browser needed.

### Reproduction

1. cd backend && python3.11 -m pytest tests/unit/test_v2_revision_routing.py::test_concierge_nested_v2_revision_parent_keeps_v2_base -xvs

### Expected

Revision succeeds with target_artifact_type='prototype_v2_output' when parent is 'prototype_v2_feature_revision'

### Actual

Pipeline type becomes 'prototype_v2_feature_revision_revision' (duplicate suffix), causes 403 pipeline_not_entitled because it doesn't exist in TIER_PIPELINES

### Notes

Logged from the existing open knowledge card [ISS-160](.knowledge/cards/20260813-1300-ISS-160.md), which already holds the root cause.
Link that card from the ledger row and update it when this closes; do not mint a duplicate root card.
Agreed minimal fix (two independent reviewers, static read of the current code): In backend/app/api/run_commands.py, extract the base_type derivation from the disposal path (:1640-1650: prototype_large_revision and prototype_feature_revision map to prototype, prototype_v2_feature_revision maps to prototype_v2, otherwise removesuffix("_revision")) into a small helper such as `_revision_base_type(wr_type)`. Call it from both the disposal path and the CHANNEL_REVISION branch, so :2018 becomes `dispatch.target_artifact_type or f"{_revision_base_type(wr_type)}_output"`. Add one unit test in backend/tests/unit/test_rest_revisions.py: a user_stories_revision parent posting a plain text turn mints `user_stories_revision`, not a 403.

<a id="qa-kb-010"></a>

## QA-KB-010 — PPT wizard design system requirement blocks Continue

- **Page:** /create/ppt
- **Route:** /create/ppt
- **Severity:** High
- **Found by:** knowledge-base sweep (open card ISS-189)
- **Found at:** 2026-10-01 20:50
- **Reproduction mode:** Browser — reproduce from the URL below.

### Reproduction

1. Navigate to /dashboard, then /create/ppt (fresh page load)
2. Sign in as admin@velocity.ai if not already
3. Select 'Investment Banking Pitch Book' or 'Weekly Team Update' template from gallery
4. Click 'Use this template' in preview modal
5. Observe 'Pick a design system' pill appears in unmet requirements
6. Observe Continue button is disabled
7. Fill brief textarea with content
8. Observe Continue button remains disabled

### Expected

Selecting a valid template with a non-empty brief satisfies the wizard requirements and enables Continue, matching the behavior of other PPT templates without design-system requirements (e.g. Investor Pitch Deck).

### Actual

A 'Pick a design system' requirement pill appears with no corresponding UI control to satisfy it. Continue remains permanently disabled regardless of valid template and brief content.

### Notes

Logged from the existing open knowledge card [ISS-189](.knowledge/cards/20260828-1457-ISS-189.md), which already holds the root cause.
Link that card from the ledger row and update it when this closes; do not mint a duplicate root card.
Agreed minimal fix (two independent reviewers, static read of the current code): In /Users/bilala/Developer/Projects/VELOCITY-AI-worktrees/feat-user-stories-v2/frontend/src/components/workflow/LaunchWizard.tsx:1298, change `steps={isDeck ? ["template"] : [...]}` to `steps={isDeck ? (dsRequired ? ["template", "design-system"] : ["template"]) : ["template", "design-system", "discovery"]}`. The existing dsSlot/DesignSystemPicker then renders for DS-requiring deck templates and the user picks a DS. Optionally add a small test that a deck template with design_system.requires=true shows the picker step. Do not add the :668 auto-select.

<a id="qa-kb-011"></a>

## QA-KB-011 — Save buttons persist default agents during override load race

- **Page:** /workflows/{id}/run
- **Route:** /workflows/{id}/run
- **Severity:** High
- **Found by:** knowledge-base sweep (open card ISS-284)
- **Found at:** 2026-10-01 20:50
- **Reproduction mode:** Browser — reproduce from the URL below.

### Reproduction

1. Go to a saved workflow override at /workflows/{id}/run
2. Click 'Save as my version' immediately before override finishes loading
3. Check the saved override's agent_ids — they will be the defaults, not the override

### Expected

Save buttons should be disabled until the override fetch completes, preventing saves during the loading window.

### Actual

Save buttons are always enabled, allowing saves before getWorkflowDetail resolves. Saving during this window persists the default roster over the real override.

### Notes

Logged from the existing open knowledge card [ISS-284](.knowledge/cards/20260828-1906-ISS-284.md), which already holds the root cause.
Link that card from the ledger row and update it when this closes; do not mint a duplicate root card.
Agreed minimal fix (two independent reviewers, static read of the current code): In LaunchWizard.tsx add `const [overrideSettled, setOverrideSettled] = useState(false)`. In the override-fetch effect (after the `if (!token) return`), call setOverrideSettled(false) with the other resets. Add `.finally(() => { if (!cancelled) setOverrideSettled(true); })` after the existing .catch. Then add `disabled={!overrideSettled}` plus the matching disabled:* classes to both the "Save workflow" and "Save as my version" buttons. Optionally add an early `if (!overrideSettled) return;` in handleSaveAsOverride and handleSaveWorkflow. Edge case: when there is no token, initialise settled as true, or set it true before the early return, so the buttons are not stuck disabled.

**Interrupted fix (2026-10-01 22:40):** the first fixer for this bug was killed by an API limit mid-edit. It may have left a PARTIAL change in: frontend/src/components/workflow/LaunchWizard.tsx. Before editing, read `git diff` for those files, keep only the hunks that belong to this bug's fix and complete them; never revert hunks that belong to other QA-KB bugs (other bugs share some of these files).

<a id="qa-kb-012"></a>

## QA-KB-012 — Navigating to /login/<sub-path> renders dashboard under incorrect URL

- **Page:** /login/{sub-path}
- **Route:** /login/{sub-path}
- **Severity:** High
- **Found by:** knowledge-base sweep (open card ISS-348)
- **Found at:** 2026-10-01 20:50
- **Reproduction mode:** Browser — reproduce from the URL below.

### Reproduction

1. Sign in as admin@velocity.ai
2. Navigate to https://localhost:3001/login/anything in the address bar
3. Observe: the address bar shows /login/anything but the authenticated dashboard renders (Home, workflows, etc.)

### Expected

An authenticated user hitting a nonexistent sub-path under /login should receive a 404/not-found response, or be redirected to an appropriate page. The URL and rendered content should agree.

### Actual

The address bar shows /login/<sub-path> while the authenticated dashboard content silently renders underneath, identical to /login/anything showing the Home screen with no indication of an error.

### Notes

Logged from the existing open knowledge card [ISS-348](.knowledge/cards/20260828-2102-ISS-348.md), which already holds the root cause.
Link that card from the ledger row and update it when this closes; do not mint a duplicate root card.
Agreed minimal fix (two independent reviewers, static read of the current code): In frontend/src/lib/routes.ts:224 change `if (head === 'login') {` to `if (head === 'login' && segments.length === 1) {`, with a short ISS-348 comment mirroring the register one at lines 263-266. Optionally add a routes unit assertion that parseViewPath(['login','x']) returns { screen: 'unknown' }.

<a id="qa-kb-013"></a>

## QA-KB-013 — Navigating to /admin/<subpath> renders dashboard instead of 404

- **Page:** /admin/{subpath}
- **Route:** /admin/{subpath}
- **Severity:** High
- **Found by:** knowledge-base sweep (open card ISS-349)
- **Found at:** 2026-10-01 20:50
- **Reproduction mode:** Browser — reproduce from the URL below.

### Reproduction

1. Navigate to /admin/nonexistent in the browser (authenticated as any user)
2. Observe dashboard renders with the invalid URL in the address bar

### Expected

Should display a 404 or not-found error when accessing an undefined /admin/<subpath>

### Actual

Dashboard renders at /admin/<subpath>, with the address bar showing the invalid URL

### Notes

Logged from the existing open knowledge card [ISS-349](.knowledge/cards/20260828-2102-ISS-349.md), which already holds the root cause.
Link that card from the ledger row and update it when this closes; do not mint a duplicate root card.
Agreed minimal fix (two independent reviewers, static read of the current code): In frontend/src/lib/routes.ts:480 change to `if (head === 'admin' && segments.length === 1) {`. Optionally add a routes unit assertion that `parseViewPath(['admin','x'])` returns `{screen:'unknown'}`. The unguarded `login` branch at routes.ts:256 has the same shape but is not part of this card.

<a id="qa-kb-014"></a>

## QA-KB-014 — Idea-input Back button silently discards unsaved brief and agents

- **Page:** /workflows/new
- **Route:** /workflows/new
- **Severity:** High
- **Found by:** knowledge-base sweep (open card ISS-371)
- **Found at:** 2026-10-01 20:50
- **Reproduction mode:** Browser — reproduce from the URL below.

### Reproduction

1. Navigate to /workflows/new
2. Type text in the idea brief textarea
3. Click 'Add agents' and select at least one agent
4. Click the Back button (top-left arrow, aria-label='Back to dashboard')
5. Confirm the brief text and agent selections are gone with no confirmation dialog shown

### Expected

Before navigating away via Back, show a confirmation dialog: 'You have unsaved changes. Leave anyway? Your work will be lost.' with options to stay or leave.

### Actual

Back button navigates away immediately, discarding all unsaved ideaInput and pipelineAgents state with no warning prompt.

### Notes

Logged from the existing open knowledge card [ISS-371](.knowledge/cards/20260828-2140-ISS-371.md), which already holds the root cause.
Link that card from the ledger row and update it when this closes; do not mint a duplicate root card.
Agreed minimal fix (two independent reviewers, static read of the current code): 1) IdeaInputPage.tsx: add `onUnsavedChange?: (dirty: boolean) => void` to IdeaInputPageProps (:775) and to the destructured args (:956). Add a baseline ref plus an effect that mirrors ComposerPage.tsx:375-379: `const snap = ideaInput + "\0" + pipelineAgents.map(a => a.id).join(","); useEffect(() => { if (base.current === null) base.current = snap; onUnsavedChange?.(snap !== base.current); return () => onUnsavedChange?.(false); }, [snap, onUnsavedChange]);`. 2) DashboardLayout.tsx ~:3161: add `onUnsavedChange={handleUnsavedChange}` to the `<IdeaInputPage>` props. 3) Optionally add a small test in the IdeaInputPage tests. A baseline snapshot keeps a seeded pendingHomeBrief or saved composition from counting as dirty. The cleanup resets the flag on unmount, so running or saving does not leave a stale dirty state.

**Interrupted fix (2026-10-01 22:40):** the first fixer for this bug was killed by an API limit mid-edit. It may have left a PARTIAL change in: frontend/src/components/layout/DashboardLayout.tsx, frontend/src/components/workflow/IdeaInputPage.tsx. Before editing, read `git diff` for those files, keep only the hunks that belong to this bug's fix and complete them; never revert hunks that belong to other QA-KB bugs (other bugs share some of these files).

<a id="qa-kb-015"></a>

## QA-KB-015 — AccountSettings Back button discards unsaved password/model fields without confirmation

- **Page:** /settings
- **Route:** /settings
- **Severity:** High
- **Found by:** knowledge-base sweep (open card ISS-372)
- **Found at:** 2026-10-01 20:50
- **Reproduction mode:** Browser — reproduce from the URL below.

### Reproduction

1. Navigate to /settings (or /dashboard/settings/profile for Account Settings)
2. Type a value into the Current password field
3. Click the header Back button (top-left arrow icon)
4. Observe: No confirmation dialog; navigation happens immediately
5. Return to /settings and confirm the password field is empty

### Expected

Leaving Account Settings via the Back control while unsaved password fields are present (or pendingModel differs from selectedModel) should show a confirmation dialog before discarding, matching the fix for ISS-275 (ComposerPage).

### Actual

The Back button navigates away immediately with no confirmation prompt, silently discarding any typed passwords or model preference changes not yet saved.

### Notes

Logged from the existing open knowledge card [ISS-372](.knowledge/cards/20260828-2141-ISS-372.md), which already holds the root cause.
Link that card from the ledger row and update it when this closes; do not mint a duplicate root card.
Agreed minimal fix (two independent reviewers, static read of the current code): 1) AccountSettings.tsx: add `onUnsavedChange?: (dirty: boolean) => void` to the props (:31), destructure it (:87), and add `const dirty = !!(currentPassword || newPassword || confirmPassword) || pendingModel !== selectedModel; useEffect(() => { onUnsavedChange?.(dirty); return () => onUnsavedChange?.(false); }, [dirty, onUnsavedChange]);` Check that selectedModel and pendingModel are both initialised from prefs.preferred_model at :149, so the initial null state does not read as dirty. 2) DashboardLayout.tsx:3117: pass `onUnsavedChange={handleUnsavedChange}`. Optionally also OR in the constitution dirty flag.

<a id="qa-kb-016"></a>

## QA-KB-016 — ConfigLeversFlat missing Tools section in agent config modal

- **Page:** /library (agent detail drawer) or workflow composer
- **Route:** /library (agent detail drawer) or workflow composer
- **Severity:** High
- **Found by:** knowledge-base sweep (open card ISS-378)
- **Found at:** 2026-10-01 20:50
- **Reproduction mode:** Browser — reproduce from the URL below.

### Reproduction

1. Navigate to /library and click on any agent card to open the detail drawer
2. Click the Config tab on the modal
3. Observe the rendered levers: Model, Effort (if applicable), Validator, Gates (pre/post), Retry
4. Note: no Tools grants section is rendered (expected: Read files / Write files checkboxes)

### Expected

The Config tab displays all per-agent lever groups: Model, Effort, Validator, Gates (pre/post), Tools grants (Read files and Write files checkboxes), and Retry — matching AdvancedExpander's full set.

### Actual

The Config tab displays Model, Effort, Validator, Gates, and Retry only. No Tools grants section is rendered, even though the underlying SelectionsMap.tools field exists and is passed through applyLeverPatch like the other levers.

### Notes

Logged from the existing open knowledge card [ISS-378](.knowledge/cards/20260828-2006-ISS-378.md), which already holds the root cause.
Link that card from the ledger row and update it when this closes; do not mint a duplicate root card.
Agreed minimal fix (two independent reviewers, static read of the current code): In ConfigLeversFlat in frontend/src/components/workflow/AgentsPopup.tsx, add `const grants = effectiveToolGrants(sel);`. After the Retry ConfigLeverRow, render a "Tool grants" section by mapping TOOL_GRANT_LEVERS to labelled checkboxes. Each checkbox uses checked={grants[key]}, aria-label={`${label} for ${agentName}`} and onChange={(e) => updateLever({ tools: { ...grants, [key]: e.target.checked } })}. Add the disabled, unchecked "Execute commands" row as in AdvancedExpander (use a local id prefix instead of `region`). Add one small test that the Config tab shows the Tool grants rows, in the style of composer/AgentRow.toolsVisibility.test.tsx.

<a id="qa-kb-017"></a>

## QA-KB-017 — Model override allows premium models to basic-tier accounts

- **Page:** /canvas
- **Route:** /canvas
- **Severity:** High
- **Found by:** knowledge-base sweep (open card ISS-398)
- **Found at:** 2026-10-01 20:50
- **Reproduction mode:** Browser — reproduce from the URL below.

### Reproduction

1. Sign in as basic-tier account (qa-basic@flowinqa.com)
2. Navigate to composer/workflow canvas
3. Create or edit a workflow and set model_overrides to map an agent to a premium model (eu.anthropic.claude-opus-4-6-v1)
4. Save the workflow — currently accepts 200/201; should reject
5. If saved, launch the workflow and verify it runs against the premium model instead of being rejected

### Expected

Model override validation should reject premium models for basic-tier accounts with a validation error

### Actual

Model override validation accepts any model from the full catalog regardless of user tier, allowing cost abuse

### Notes

Logged from the existing open knowledge card [ISS-398](.knowledge/cards/20260828-2106-ISS-398.md), which already holds the root cause.
Link that card from the ledger row and update it when this closes; do not mint a duplicate root card.
Agreed minimal fix (two independent reviewers, static read of the current code): 1. Add a `user_tier: str` parameter to both `_validate_model_overrides` copies (`run_engine.py:544` and `user_workflows.py:348`). After the `model_id not in allowed_model_ids` check in each loop, add `ok, why = can_use_model(user_tier, model_id)` and `if not ok: return why`, importing `can_use_model` from `app.core.entitlements`.
2. Pass the effective tier at the call sites. At `user_workflows.py:729` use the `effective_tier(current_user, principal)` already computed near line 703. At `run_commands.py:3733` use the effective tier already derived in that launch function (around line 4676).
3. The PATCH handler at `user_workflows.py:972` depends only on `get_current_user`, so switch it to `get_current_principal`, as the create route does at line 669, and pass `effective_tier(...)`.
4. Add a unit test in `tests/unit/app/test_run_pipeline_validation.py`: a basic tier with an Opus override is rejected, and a pro tier is accepted.
5. Update the existing test calls at lines 558-581 to pass a tier.
Caveat: launches from saved workflows (the `USER_WORKFLOW_MANIFEST` source) skip the validator at `run_commands.py:3731`, so the save and PATCH checks cover that path. That leaves a downgrade-after-save edge, which is out of scope here.

**Interrupted fix (2026-10-01 22:40):** the first fixer for this bug was killed by an API limit mid-edit. It may have left a PARTIAL change in: (no source edits were made yet). Before editing, read `git diff` for those files, keep only the hunks that belong to this bug's fix and complete them; never revert hunks that belong to other QA-KB bugs (other bugs share some of these files).

<a id="qa-kb-018"></a>

## QA-KB-018 — Transient fetch failure enables unwanted duplicate save on real workflow

- **Page:** /workflows/{id}/canvas
- **Route:** /workflows/{id}/canvas
- **Severity:** High
- **Found by:** knowledge-base sweep (open card ISS-410)
- **Found at:** 2026-10-01 20:50
- **Reproduction mode:** Browser — reproduce from the URL below.

### Reproduction

1. In Chrome DevTools, set Network throttling to 'Slow 3G'
2. Navigate to /workflows/<existing-id>/canvas for a real workflow
3. While the /api/workflows/{id} fetch is in flight, open DevTools and abort the request
4. In the canvas composer, type a workflow name
5. Click 'Save as copy'
6. Verify in the workflows list that a new unwanted duplicate workflow was created

### Expected

A transient fetch failure (5xx, timeout, etc.) should be distinguished from 404 (not found), and Save button should be blocked or error shown while manifest is unresolved.

### Actual

Transient errors set initialSavedComposition=null (enabling copy-mode) without setting builtinCanvasAccessDenied, so Save button remains enabled and creates an unwanted new workflow.

### Notes

Logged from the existing open knowledge card [ISS-410](.knowledge/cards/20260828-2344-ISS-410.md), which already holds the root cause.
Link that card from the ledger row and update it when this closes; do not mint a duplicate root card.
Agreed minimal fix (two independent reviewers, static read of the current code): In frontend/src/components/workflow/composer/ComposerPage.tsx:1383 change `disabled={saving}` to `disabled={saving || (!!builtinCanvasType && !initialManifestSteps?.length && !initialAgentIds?.length)}`. Save as copy then stays unreachable until the built-in's manifest has seeded, which covers both the loading gap and a transient failure. Optionally add a title or tooltip, and add one test asserting the button is disabled when builtinCanvasType is set and nothing is seeded. Do not retry or add error UI in page.tsx.

<a id="qa-kb-019"></a>

## QA-KB-019 — Marker stripping fails for filenames containing "]" or ", "

- **Page:** n/a (code-level)
- **Route:** n/a (code-level)
- **Severity:** High
- **Found by:** knowledge-base sweep (open card ISS-579)
- **Found at:** 2026-10-01 20:50
- **Reproduction mode:** Test — reproduce by running the command below; it should fail (or misbehave) as described. No browser needed.

### Reproduction

1. const file = new File(['content'], 'my].txt'); attach it in the test
2. Remove the attachment chip
3. Call handleRun and verify onStartPipeline receives the message
4. Assert message does not contain '[Attached: my].txt]'

### Expected

When a user removes an attachment and runs, the brief message sent to onStartPipeline should not contain the removed file's marker, even for filenames with special characters like "]" or ", "

### Actual

The stripAttachmentMarker function uses a regex [^\]]* that stops at the first ] in a filename, and splits on ", " which fails if a filename contains that substring. Filenames like 'report].pdf' or 'file, more.txt' are not properly matched and removed, leaving stale [Attached: ...] markers in the message.

### Notes

Logged from the existing open knowledge card [ISS-579](.knowledge/cards/20260829-0234-ISS-579.md), which already holds the root cause.
Link that card from the ledger row and update it when this closes; do not mint a duplicate root card.
Agreed minimal fix (two independent reviewers, static read of the current code): In WorkflowView.tsx, make stripAttachmentMarker match the literal filename instead of splitting the marker contents. For example, find the marker with a non-greedy `\[Attached: (.*?)\](?=\n\n|$)` and remove `filename` from it by exact, boundary-aware match (start or ", " before, ", " or end after). Alternatively, replace "]" and "," in the names at write time (line 354). Add one test case to WorkflowView.attachmentRemove.test.tsx with a name like "a, b].txt".

<a id="qa-kb-020"></a>

## QA-KB-020 — Review gate approval resolves wrong run's gate in family transcripts

- **Page:** /runs/{id}
- **Route:** /runs/{id}
- **Severity:** High
- **Found by:** knowledge-base sweep (open card ISS-654)
- **Found at:** 2026-10-01 20:50
- **Reproduction mode:** Browser — reproduce from the URL below.

### Reproduction

1. 1. Create a run that opens a review gate — leave it pending (waiting_for_user)
2. 2. From the same family, start a revision/child run that opens its own gate before the parent's is approved
3. 3. In the UI, approve the child run's gate
4. 4. Check: the parent's gate card ALSO flips to 'Review approved — build continues', but backend still reports parent blocked in waiting_for_user

### Expected

An approval event resolves only the ONE gate card it corresponds to (matched by run + agent identity), regardless of how many runs share the transcript.

### Actual

Approving a gate in one run can flip a DIFFERENT run's still-open gate to the resolved rendering in the UI, while that other run's actual gate remains blocked server-side.

### Notes

Logged from the existing open knowledge card [ISS-654](.knowledge/cards/20260917-1250-ISS-654.md), which already holds the root cause.
Link that card from the ledger row and update it when this closes; do not mint a duplicate root card.
Agreed minimal fix (two independent reviewers, static read of the current code): In useRunChat.ts `case "review_gate_approved"` (~L575), read `const rid = typeof data.pipeline_run_id === "string" ? data.pipeline_run_id : undefined;`. Change the `.find` predicate to `m.cardKind === "gate" && !m.resolved && (!rid || !m.runId || m.runId === rid)`. The fallback to the old positional match when either runId is missing keeps current behavior for cards without an id. Optionally add one vitest case with two unresolved gate cards of different runIds, approving the earlier run's id and asserting only that card flips.

**Interrupted fix (2026-10-01 22:40):** the first fixer for this bug was killed by an API limit mid-edit. It may have left a PARTIAL change in: frontend/src/app/[...view]/page.tsx, frontend/src/hooks/useRunChat.ts. Before editing, read `git diff` for those files, keep only the hunks that belong to this bug's fix and complete them; never revert hunks that belong to other QA-KB bugs (other bugs share some of these files).

<a id="qa-kb-021"></a>

## QA-KB-021 — Manifest top-level keys lost on cold-mount save (limits, input_providers, seed_files)

- **Page:** /workflows/{id}/edit
- **Route:** /workflows/{id}/edit
- **Severity:** High
- **Found by:** knowledge-base sweep (open card ISS-682)
- **Found at:** 2026-10-01 20:50
- **Reproduction mode:** Test — reproduce by running the command below; it should fail (or misbehave) as described. No browser needed.

### Reproduction

1. Run pdfToPrototypeManifestRoundTrip.test.ts which has an input_providers assertion that passes only when sourceManifest is provided to buildWorkflowManifest
2. Observe that the test passes because ComposerPage's save path (line 903) passes initialManifest (fifth parameter)
3. Note that the two cold-mount paths at /workflows/{id}/edit (line 3776) and /workflows/{id}/run (line 3978) do NOT pass manifest to setInitialSavedComposition, so when a workflow is loaded and saved from those routes, buildWorkflowManifest receives no sourceManifest and drops the top-level keys

### Expected

Manifest top-level keys (id, display_name, limits, input_providers, seed_files, etc.) survive a load-and-save round trip from both /workflows/{id}/edit and /workflows/{id}/run cold mounts, same as they do in ComposerPage's regular save path.

### Actual

Top-level manifest keys are dropped when a saved workflow is loaded via cold-mount (/workflows/{id}/edit or /workflows/{id}/run), edited, and saved because setInitialSavedComposition does not pass the manifest field to ComposerPage, so buildWorkflowManifest has no sourceManifest to preserve them.

### Notes

Logged from the existing open knowledge card [ISS-682](.knowledge/cards/20260904-ISS-682.md), which already holds the root cause.
Link that card from the ledger row and update it when this closes; do not mint a duplicate root card.
Agreed minimal fix (two independent reviewers, static read of the current code): In frontend/src/app/[...view]/page.tsx, add `manifest: (saved.manifest as Record<string, unknown> | undefined) ?? null,` to the object literals passed to setInitialSavedComposition at ~3776 (/workflows/{id}/edit) and ~3978 (/run), next to `manifestSteps: saved.manifest?.steps`. Leave the built-in canvas call at ~521 alone, since it is copy-only. Add one assertion that a cold-mount edit then Save preserves `limits`.

<a id="qa-kb-022"></a>

## QA-KB-022 — Deliverable readback overwrites output of all post-build agents with HTML file

- **Page:** n/a (code-level)
- **Route:** n/a (code-level)
- **Severity:** High
- **Found by:** knowledge-base sweep (open card ISS-683)
- **Found at:** 2026-10-01 20:50
- **Reproduction mode:** Test — reproduce by running the command below; it should fail (or misbehave) as described. No browser needed.

### Reproduction

1. Run a workflow with a build step (producing prototype.html) followed by a validator/reviewer step
2. Inspect the reviewer/validator agent's recorded output in the run record or artifact graph
3. Verify the output is the HTML file instead of the validator's text result

### Expected

Each agent's output is its own streamed result. The reviewer/validator produces text describing its findings, not the prototype HTML.

### Actual

After the build step writes prototype.html, any subsequent validator/reviewer/reporter agent's text output is replaced with the HTML file (if larger than the text output), rendering those agents' results unreadable.

### Notes

Logged from the existing open knowledge card [ISS-683](.knowledge/cards/20260904-ISS-683.md), which already holds the root cause.
Link that card from the ledger row and update it when this closes; do not mint a duplicate root card.
Agreed minimal fix (two independent reviewers, static read of the current code): In engine.py `_run_agent`, read `sandbox.read(deliverable.name or "prototype.html")` into a variable just before the agent runs. At the readback block (:10623), add `and file_from_disk != pre_step_file` to the condition, so a step's output is replaced only if that step actually wrote or edited the file. The final deliverable is unaffected because the resolver still reads the file from disk at run end (engine.py:7830). Add one test with a build step followed by a reviewer step, asserting the reviewer's output is kept. Known edge: parallel fan-out workers writing the same file could be misattributed to each other.

<a id="qa-kb-023"></a>

## QA-KB-023 — Mechanical step without engine dispatch branch silently runs model on empty prompt

- **Page:** n/a (code-level)
- **Route:** n/a (code-level)
- **Severity:** High
- **Found by:** knowledge-base sweep (open card ISS-684)
- **Found at:** 2026-10-01 20:50
- **Reproduction mode:** Test — reproduce by running the command below; it should fail (or misbehave) as described. No browser needed.

### Reproduction

1. Run: cd backend && python3.11 -m pytest tests/unit/test_execution_engine.py::test_mechanical_engine_parity -q (will fail—test does not exist yet)
2. Or: Inspect engine.py:6438-6490 and compiler.py _ALLOWED_MECHANICAL_KINDS; notice assemble_backlog/extract_prototype_ui in compiler but missing from both registry._KNOWN and engine dispatch branches

### Expected

Every mechanical kind in compiler._ALLOWED_MECHANICAL_KINDS must have an engine dispatch branch. If a step has mechanical: <kind> with no branch, engine raises naming the kind.

### Actual

assemble_backlog and extract_prototype_ui are in compiler._ALLOWED_MECHANICAL_KINDS but absent from registry._KNOWN (registry parity test only covers 2 kinds, not all 4). Engine else clause at 6489 falls through to _registry.resolve(strategy_name) with default single_shot, running a model on empty prompt and billing tokens.

### Notes

Logged from the existing open knowledge card [ISS-684](.knowledge/cards/20260918-ISS-684.md), which already holds the root cause.
Link that card from the ledger row and update it when this closes; do not mint a duplicate root card.
Agreed minimal fix (two independent reviewers, static read of the current code): 1) In engine.py, insert `elif getattr(step, "mechanical", None): raise ValueError(f"mechanical kind {step.mechanical!r} has no engine dispatch branch")` just before the final `else:` at ~6489. The existing handler for unhandled step exceptions (~7589) should turn the raise into a run failure, but check that when implementing.
2) Add a test next to test_compiler.py:575. It calls `registry.discover()` and, for each `("mechanical", name)` in `registry._KNOWN`, asserts `f'== "{name}"'` appears in the source of engine.py. It reads the file with `inspect.getsource` or `Path.read_text()`. This is a source-grep parity check, so it is brittle by design; that is acceptable here.

<a id="qa-kb-024"></a>

## QA-KB-024 — Resume reconcilers parse wrong input, causing task key mismatches and re-execution

- **Page:** n/a (code-level)
- **Route:** n/a (code-level)
- **Severity:** High
- **Found by:** knowledge-base sweep (open card ISS-685)
- **Found at:** 2026-10-01 20:50
- **Reproduction mode:** Test — reproduce by running the command below; it should fail (or misbehave) as described. No browser needed.

### Reproduction

1. cd backend
2. Run a test that exercises resume with wave_scheduler or fanout step using json_tasks parser, then resume the run
3. Inspect task_loop boundary reconciler (engine.py:14889) and wave orphan allowset (engine.py:14971) — they will compute different task keys than the strategy persisted, causing mis-set boundaries or missing allowsets

### Expected

Resume reconcilers should compute task keys from the same input source (task_source.target file) that strategies used, ensuring key consistency across persist and reconcile

### Actual

Resume reconcilers at fanout_batch.py:92 and engine.py:14889/14971/15202 call parser.parse(reply) instead of parse_preferring_target(reply, sandbox, target), computing keys from potentially truncated/narrated/unavailable model output rather than the persisted task file

### Notes

Logged from the existing open knowledge card [ISS-685](.knowledge/cards/20260918-ISS-685.md), which already holds the root cause.
Link that card from the ledger row and update it when this closes; do not mint a duplicate root card.
Agreed minimal fix (two independent reviewers, static read of the current code): At each of the four sites, replace `parser.parse(X)` with the same probe the strategies use. For `fanout_batch.py:92`, take `target = getattr(task_source, "target", None)` and `sandbox = getattr(runner, "sandbox", None)`. In the three engine sites, take them from `getattr(step.task_source, "target", None)` and `getattr(getattr(ectx, "runner", None), "sandbox", None)`. The probe is:

if hasattr(parser, "parse_preferring_target"): tasks = parser.parse_preferring_target(X, sandbox=sandbox, target=target)
else: tasks = parser.parse(X)

At `engine.py:15202` wrap it as `len(...)`. For `wave_scheduler` steps with `task_source.kind == "custom_path"` (the wave strategy now reads that path), either mirror the `read_custom_path` branch in the 14971 reconciler or skip it. Add one test per site that asserts keys are computed from the on-disk file, not from narrated reply text.

<a id="qa-kb-025"></a>

## QA-KB-025 — New task parser in dropdown saves manifest pointing to previous parser's file

- **Page:** /workflows/{id}
- **Route:** /workflows/{id}
- **Severity:** High
- **Found by:** knowledge-base sweep (open card ISS-686)
- **Found at:** 2026-10-01 20:50
- **Reproduction mode:** Browser — reproduce from the URL below.

### Reproduction

1. Register a new task parser in backend (beyond json_tasks/screen_plan/heading_tasks)
2. Go to workflow editor and create/edit a wave step
3. Click the 'Task source type' dropdown — new parser appears (from /api/capabilities)
4. Select the new parser and save the workflow
5. Run the workflow and inspect the manifest — it points to previous parser's target file (e.g. build/tasks.json)

### Expected

Manifest points to the newly selected parser's configured target file (from config_schema in @register)

### Actual

Manifest points to previous parser's target file because CanvasConfigRail.tsx:1694 falls back to sel.task_source?.target when parser is unmapped

### Notes

Logged from the existing open knowledge card [ISS-686](.knowledge/cards/20260918-ISS-686.md), which already holds the root cause.
Link that card from the ledger row and update it when this closes; do not mint a duplicate root card.
Agreed minimal fix (two independent reviewers, static read of the current code): 1. In json_tasks.py and screen_plan.py, add to @register `config_schema={"target": {"type": "string", "default": "build/tasks.json"}}` (screen_plan uses DEFAULT_TARGET). Leave heading_tasks without one.
2. In CanvasConfigRail.tsx, delete PARSER_TARGET and add a one-line helper `const parserTarget = (name) => taskParserOptions.find(p => p.name === name)?.config_schema?.target?.default`.
3. Use parserTarget(parser) at :1559, :1612, :1642 and :1694.
4. At :1694, drop the `?? sel.task_source?.target` fallback so an unmapped parser saves no target.
5. Check whether the frontend capability type needs `config_schema` typed. Update any composer test that asserts the target.

**Interrupted fix (2026-10-01 22:40):** the first fixer for this bug was killed by an API limit mid-edit. It may have left a PARTIAL change in: backend/agents/capabilities/task_parsers/json_tasks.py, screen_plan.py, backend/tests/unit/api/test_capabilities_api.py, frontend/src/components/workflow/AgentsPopup.tsx, composer/CanvasConfigRail.tsx and its test. Before editing, read `git diff` for those files, keep only the hunks that belong to this bug's fix and complete them; never revert hunks that belong to other QA-KB bugs (other bugs share some of these files).

<a id="qa-kb-026"></a>

## QA-KB-026 — Domain prose check reports OK when rebuild is overdue

- **Page:** n/a (code-level)
- **Route:** n/a (code-level)
- **Severity:** High
- **Found by:** knowledge-base sweep (open card ISS-693)
- **Found at:** 2026-10-01 20:50
- **Reproduction mode:** Static — reproduce by the check below (read/grep/short script). No browser needed.

### Reproduction

1. Run: cd /Users/bilala/Developer/Projects/VELOCITY-AI-worktrees/feat-user-stories-v2 && python3 tools/knowledge/status.py
2. Observe that when 'source files covered' is STALE, 'domain prose' still reports OK despite having stale input

### Expected

When 'source files covered' is STALE, 'domain prose' should also be STALE or UNKNOWN, indicating that the signature comparison cannot be trusted.

### Actual

'domain prose' reports OK even when 'source files covered' shows rebuild is overdue (e.g. 14/14 OK alongside 39 commits behind).

### Notes

Logged from the existing open knowledge card [ISS-693](.knowledge/cards/20260918-ISS-693.md), which already holds the root cause.
Link that card from the ledger row and update it when this closes; do not mint a duplicate root card.
Agreed minimal fix (two independent reviewers, static read of the current code): In tools/knowledge/status.py, before the `domain prose` append at :329, read the covered row's verdict with `cov_stale = any(c[0] == "source files covered" and c[3] == "STALE" for c in checks)`. Change the verdict at :332 to `"STALE" if (stale_domains or unauthored_domains) else ("UNKNOWN" if cov_stale else "OK")`. UNKNOWN keeps the row out of the `stale` list at :335, so the report still fixes via the existing "source files covered" row and does not print an empty "domain cards needing a pass" line. To use STALE instead, replace "UNKNOWN" with "STALE"; the :380-382 block already handles an empty `stale_domains`. Optionally add one assertion in the status tests for the case where covered != on_disk and the signatures are equal, which must not return OK.

<a id="qa-kb-027"></a>

## QA-KB-027 — Workspace file content correctness under pinned ref — edge cases untested

- **Page:** /runs/{id}
- **Route:** /runs/{id}
- **Severity:** High
- **Found by:** knowledge-base sweep (open card ISS-724)
- **Found at:** 2026-10-01 20:50
- **Reproduction mode:** Test — reproduce by running the command below; it should fail (or misbehave) as described. No browser needed.

### Reproduction

1. Create a test for user_stories_revision with a pinned ref, open/download a file, verify content matches that revision, not stale
2. Create a test for ppt_revision on a parent without presentation.html (fresh sandbox), attempt to access file in Workspace tab under a pinned ref, verify no silent staleness or 500
3. Run pytest on the test suite filtering for Workspace-tab / sandbox / pinned-ref coverage — will fail or show no coverage

### Expected

Workspace tab consistently shows correct, version-specific file content for all revision workflows (ppt_revision, user_stories_revision) and edge cases (fresh parent, no deliverable yet written) under any pinned ref; no silent staleness.

### Actual

Main fix verified via ISS-723; user_stories_revision behavior unconfirmed; fresh sandbox edge case unverified; no regression guard test exists; card still open.

### Notes

Logged from the existing open knowledge card [ISS-724](.knowledge/cards/20260922-1246-ISS-724.md), which already holds the root cause.
Link that card from the ledger row and update it when this closes; do not mint a duplicate root card.
Agreed minimal fix (two independent reviewers, static read of the current code): Add one test in backend/tests/agents/test_iss720_ref_scoped_sizes.py (or a sibling file) that builds a tmp_path git repo with presentation.html committed as "v1" bytes and tagged v1, then "v2" bytes and tagged v2. Assert rf.read_sandbox_file(run_id, path="presentation.html", ref="v2") returns the v2 bytes and ref="v1" returns the v1 bytes. Assert rf.download_sandbox_zip(run_id, ref="v2") contains the v2 bytes. Then flip the card's status to resolved, with FIX-601 plus this test as evidence.

<a id="qa-kb-028"></a>

## QA-KB-028 — Test no longer proves single-flight refresh — shared cache collapses concurrent calls

- **Page:** n/a (code-level)
- **Route:** n/a (code-level)
- **Severity:** High
- **Found by:** knowledge-base sweep (open card ISS-824)
- **Found at:** 2026-10-01 20:50
- **Reproduction mode:** Test — reproduce by running the command below; it should fail (or misbehave) as described. No browser needed.

### Reproduction

1. cd frontend
2. npx vitest run src/lib/api.refreshRetry.test.ts
3. Observe: 'coalesces concurrent 401s' test passes
4. Temporarily comment out refreshOnce() memoization (or remove inFlightRefresh guard) in api.ts:428-434
5. npx vitest run src/lib/api.refreshRetry.test.ts again
6. Observe: test still passes (should fail if it properly validates single-flight behavior)

### Expected

Disabling refreshOnce() memoization causes the test to fail, proving it validates the single-flight guard

### Actual

Test passes regardless, because three concurrent getMe(STALE(5)) calls now share one cached promise, producing one /api/auth/me request and one 401 — the burst never materializes to test the guard

### Notes

Logged from the existing open knowledge card [ISS-824](.knowledge/cards/20260922-1947-ISS-824.md), which already holds the root cause.
Link that card from the ledger row and update it when this closes; do not mint a duplicate root card.
Agreed minimal fix (two independent reviewers, static read of the current code): In the coalesce test in api.refreshRetry.test.ts, drive the burst with three different uncached authenticated calls (e.g. getChats(STALE(5)), getRunSandboxZip-like or any non-cachedGet endpoint, plus login-free ones that send the bearer), with fetchMock returning 401 for the stale bearer and ok JSON for the fresh one (adjust the response body per URL); keep the refreshCalls toHaveLength(1) assertion. Optionally assert the three /api/... 401 calls count is 3 so the burst is proven.

<a id="qa-kb-029"></a>

## QA-KB-029 — ArtifactNode TypeScript types disagree with backend wire format on three fields

- **Page:** n/a (code-level)
- **Route:** n/a (code-level)
- **Severity:** Medium
- **Found by:** knowledge-base sweep (open card ISS-077)
- **Found at:** 2026-10-01 20:50
- **Reproduction mode:** Static — reproduce by the check below (read/grep/short script). No browser needed.

### Reproduction

1. Open frontend/src/store/api/runs.ts:40-54 (ArtifactNode interface)
2. Compare to backend/app/models/artifact_ref.py:39-45 (ArtifactRef columns)
3. Run backend at app/api/runs.py:1383-1391 to see wire format returned by _node()

### Expected

TypeScript declarations match the actual runtime wire format from the backend

### Actual

task_id declared as string but returns null; derived_from declared as string[] but returns string|null; children declared as string[] but returns ArtifactNode[]

### Notes

Logged from the existing open knowledge card [ISS-077](.knowledge/cards/20260812-0212-ISS-077.md), which already holds the root cause.
Link that card from the ledger row and update it when this closes; do not mint a duplicate root card.
Agreed minimal fix (two independent reviewers, static read of the current code): In both frontend/src/lib/api.ts (~1497) and frontend/src/store/api/runs.ts (~40) change the ArtifactNode fields to `task_id: string | null; derived_from: string | null; children: ArtifactNode[];`. In api.ts also fix the docstring ref from `runs.py:590-608` to the current `_node` location (backend/app/api/runs.py ~1377-1393). Optionally add `retention: string` since the backend sends it. Verify with `tsc --noEmit`.

<a id="qa-kb-030"></a>

## QA-KB-030 — Task-loop gates broken; missing runs_agent_inline declaration

- **Page:** n/a (code-level)
- **Route:** n/a (code-level)
- **Severity:** Medium
- **Found by:** knowledge-base sweep (open card ISS-132)
- **Found at:** 2026-10-01 20:50
- **Reproduction mode:** Test — reproduce by running the command below; it should fail (or misbehave) as described. No browser needed.

### Reproduction

1. cd backend && python3.11 -m pytest tests/unit/agents/test_fanout.py::test_something 544 -xvs
2. cd backend && python3.11 -m pytest tests/unit/agents/workflows/test_merge_conflict.py::test_something 591 -xvs

### Expected

Step-boundary human gates fire when declared on a task-loop step; the engine's dedupe logic correctly knows inline gates won't fire.

### Actual

Step-boundary human gates are skipped even when declared, because the engine's dedupe logic incorrectly predicts inline gates will fire (default runs_agent_inline=True). The fix (invocation_gated=False) suppresses per-task gates, but TaskLoopStrategy doesn't declare runs_agent_inline=False, breaking the step-boundary gate deduplication in _evaluate_gates.

### Notes

Logged from the existing open knowledge card [ISS-132](.knowledge/cards/20260812-2116-ISS-132.md), which already holds the root cause.
Link that card from the ledger row and update it when this closes; do not mint a duplicate root card.
Agreed minimal fix (two independent reviewers, static read of the current code): In backend/agents/capabilities/strategies/task_loop.py, add `runs_agent_inline = False` as a class attribute on TaskLoopStrategy (line 149), with a comment citing ISS-132. Optionally add a one-line assertion test next to the existing strategy tests in backend/tests/unit/agents/test_strategies.py that checks `TaskLoopStrategy.runs_agent_inline is False`. Then mark ISS-132 as fixed.

<a id="qa-kb-031"></a>

## QA-KB-031 — Test marked xfail(strict=True) will XPASS now that ISS-228 code fix is in place

- **Page:** n/a (code-level)
- **Route:** n/a (code-level)
- **Severity:** Medium
- **Found by:** knowledge-base sweep (open card ISS-228)
- **Found at:** 2026-10-01 20:50
- **Reproduction mode:** Test — reproduce by running the command below; it should fail (or misbehave) as described. No browser needed.

### Reproduction

1. cd backend
2. python3.11 -m pytest tests/integration/e2e/suites/05_saved_workflows/test_iss228_launch_panel_override_binding.py::test_cold_launch_panel_shows_the_saved_overrides_own_name -q

### Expected

Test passes without the xfail marker, confirming the race condition is fixed.

### Actual

Test passes but xfail(strict=True) marks it as XPASS, which fails strict mode because a formerly-broken test is now passing.

### Notes

Logged from the existing open knowledge card [ISS-228](.knowledge/cards/20260828-1758-ISS-228.md), which already holds the root cause.
Link that card from the ledger row and update it when this closes; do not mint a duplicate root card.
Agreed minimal fix (two independent reviewers, static read of the current code): In /Users/bilala/Developer/Projects/VELOCITY-AI-worktrees/feat-user-stories-v2/tests/integration/e2e/suites/05_saved_workflows/test_iss228_launch_panel_override_binding.py, delete the `@pytest.mark.xfail(reason="ISS-228 unfixed", strict=True)` line at :41. Also change the :48 wait to `expect(page.get_by_role("heading", name=PROTO_NAME)).to_be_visible()`, since the generic title is no longer shown for a saved override. Once the test is green, the card status can be closed.

<a id="qa-kb-032"></a>

## QA-KB-032 — Fullscreen preview silently redirects to Run History on missing or corrupt sessionStorage

- **Page:** /preview-fullscreen
- **Route:** /preview-fullscreen
- **Severity:** Medium
- **Found by:** knowledge-base sweep (open card ISS-407)
- **Found at:** 2026-10-01 20:50
- **Reproduction mode:** Browser — reproduce from the URL below.

### Reproduction

1. Open /preview-fullscreen directly or when sessionStorage data is missing/corrupt
2. Observe: page silently redirects to /runs without any error message

### Expected

Display an error message explaining the session data is missing or invalid, with an option to return or dismiss

### Actual

Silently redirects to /runs (Run History) with no explanation to the user

### Notes

Logged from the existing open knowledge card [ISS-407](.knowledge/cards/20260828-2343-ISS-407.md), which already holds the root cause.
Link that card from the ledger row and update it when this closes; do not mint a duplicate root card.
Agreed minimal fix (two independent reviewers, static read of the current code): In page.tsx, add "missing" to the PageState type (line 14). In giveUp() (lines 57-63), replace router.replace(routes.runHistory()) with setState("missing"). Add a "missing" render block like the quota block, with an AlertCircle, a "Preview not available" heading, a short "preview data expired or was not found" line, and a Link to routes.runHistory(). Update the docblock at lines 27-29 to match.

<a id="qa-kb-033"></a>

## QA-KB-033 — Whole-file idiom count assertion is fragile; test will fail on any new legitimate 403/404 catch narrowing outside T30

- **Page:** n/a (code-level)
- **Route:** n/a (code-level)
- **Severity:** Medium
- **Found by:** knowledge-base sweep (open card ISS-442)
- **Found at:** 2026-10-01 20:50
- **Reproduction mode:** Test — reproduce by running the command below; it should fail (or misbehave) as described. No browser needed.

### Reproduction

1. cd frontend && vitest --run src/app/[...view]/workflowDetailCatch.source.test.ts
2. Test passes at line 87 (expects 5, finds 5), but review lines 81–85 comment: idiom count covers entire 3,900-line file, not just T30 effect
3. Reason brittleness persists: the four preceding assertions (lines 45–76) correctly scope to T30; this final count assertion reverts to whole-file scope, defeating the audit's point

### Expected

Test passes and remains robust when a new catch block elsewhere in page.tsx adopts the same 403/404 idiom for a separate feature (e.g., a new T-series effect)

### Actual

Test passes with count bumped to 5, but the whole-file assertion locks in that count forever; next legitimate idiom use in an unrelated catch will break the test, requiring another bump

### Notes

Logged from the existing open knowledge card [ISS-442](.knowledge/cards/20260829-0106-ISS-442.md), which already holds the root cause.
Link that card from the ledger row and update it when this closes; do not mint a duplicate root card.
Agreed minimal fix (two independent reviewers, static read of the current code): In workflowDetailCatch.source.test.ts, replace `expect(occurrences).toBe(5)` with `expect(occurrences).toBeGreaterThanOrEqual(3)`. That keeps the "a drop means a catch went back to swallowing errors" guard but allows more call sites. Update the comment above it to match. Alternatively, delete the test, since the t30Effect-scoped assertions already lock the T30 behaviour.

<a id="qa-kb-034"></a>

## QA-KB-034 — Silent roster expansion makes partial-roster bugs hard to debug

- **Page:** n/a (code-level)
- **Route:** n/a (code-level)
- **Severity:** Medium
- **Found by:** knowledge-base sweep (open card ISS-634)
- **Found at:** 2026-10-01 20:50
- **Reproduction mode:** Static — reproduce by the check below (read/grep/short script). No browser needed.

### Reproduction

1. Read engine.py:5005-5007 — when a partial roster is passed, it's silently replaced with the full plan
2. Search for any log line around that replacement — there is none
3. Trace a caller passing agents=[spec]: they get the full plan silently, with no indication why

### Expected

When ExecutionEngine.execute() receives a partial roster and expands it to the full plan, a debug log line records the expansion (agent IDs requested vs. agent IDs executed).

### Actual

No log line is emitted. A caller passing agents=[spec] gets the full plan silently, with no way to debug why their roster was enlarged. Test workaround uses compiled_override= to bypass the expansion entirely, but this is not the intended design — just a test-specific escape hatch.

### Notes

Logged from the existing open knowledge card [ISS-634](.knowledge/cards/20260831-0115-ISS-634.md), which already holds the root cause.
Link that card from the ledger row and update it when this closes; do not mint a duplicate root card.
Agreed minimal fix (two independent reviewers, static read of the current code): In backend/agents/execution_engine/engine.py, inside `if compiled.steps and (not agents or _roster_is_partial):` (line ~5006), only when `_roster_is_partial` is true, add `logger.info("roster expanded from plan: run=%s passed=%d plan=%d", pipeline_run_id, len(agents), len(_plan_ids))` before `agents = self._specs_from_plan(compiled.steps)`. Do not log when `not agents`, since that is the normal path. Then mark the card resolved.

<a id="qa-kb-035"></a>

## QA-KB-035 — Background run cancel/fail clears viewed run's clarify state

- **Page:** /runs/{id}
- **Route:** /runs/{id}
- **Severity:** Medium
- **Found by:** knowledge-base sweep (open card ISS-676)
- **Found at:** 2026-10-01 20:50
- **Reproduction mode:** Browser — reproduce from the URL below.

### Reproduction

1. Sign in as admin@velocity.ai and navigate to a run details page (/runs/{id}) in clarification state
2. Launch a new background run from the dashboard (stay on the viewed run's page)
3. Confirm the viewed run displays clarification questions (laneClarifyOpen is true)
4. Cancel the background run via API: POST /api/runs/{background-run-id}/cancel
5. Observe the viewed run's page: clarify state is cleared, lane switches to 'building' or 'running' instead of paused

### Expected

Viewed run remains paused in clarification. Its clarify state, questionnaire data, and activePipelineRunId persist regardless of other background runs' cancel/fail events.

### Actual

Background run cancel/fail triggers lines 1834-1836 unconditionally for all !isForeignFrame runs. Page state (activePipelineRunId, questionnaireData, reviewGateData) is cleared for the viewed run when any launched-background run terminates.

### Notes

Logged from the existing open knowledge card [ISS-676](.knowledge/cards/20260917-1447-ISS-676.md), which already holds the root cause.
Link that card from the ledger row and update it when this closes; do not mint a duplicate root card.
Agreed minimal fix (two independent reviewers, static read of the current code): In page.tsx, wrap only the three page-level setters (setReviewGateData(null), setQuestionnaireData(null), setActivePipelineRunId(null)) in `if (!frameRunId || !trackedRunIdRef.current || frameRunId === trackedRunIdRef.current) { ... }`. Leave the per-run runStore.update(frameRunId, { questionnaireData: null }) call, the setBackgroundRunTransition call, and the setLastCancelledRunId/detachRunRef/patchRecentRunStatus calls unconditional.

<a id="qa-kb-036"></a>

## QA-KB-036 — Dead degraded variable and mislabeled comment confuse status reconciliation

- **Page:** n/a (code-level)
- **Route:** n/a (code-level)
- **Severity:** Medium
- **Found by:** knowledge-base sweep (open card ISS-689)
- **Found at:** 2026-10-01 20:50
- **Reproduction mode:** Static — reproduce by the check below (read/grep/short script). No browser needed.

### Reproduction

1. cd backend && grep -n 'FIX-247' app/api/run_commands.py to locate the comment at line 840
2. grep -n 'degraded_current.*any' app/api/run_commands.py to find the actual logic at line 933
3. Verify: between lines 855 and 960, grep 'degraded' matches only degraded_* variables, not the bare degraded local

### Expected

One mechanism decides the degraded verdict: FIX-484's reattempt-boundary scan via degraded_current, correctly cited in its explanation.

### Actual

Two mechanisms both claim to own the verdict—the dead degraded local (line 850-855) with a 10-line comment citing FIX-247 (a clarify-gate repaint card), and the actual logic using degraded_current (line 945). The bare degraded variable is assigned but never read.

### Notes

Logged from the existing open knowledge card [ISS-689](.knowledge/cards/20260918-ISS-689.md), which already holds the root cause.
Link that card from the ledger row and update it when this closes; do not mint a duplicate root card.
Agreed minimal fix (two independent reviewers, static read of the current code): In backend/app/api/run_commands.py `_reconcile_terminal_status`, delete the 11-line "FIX-247" comment and the `_latest_complete` / `degraded = bool(...)` assignment (about lines 840-855). Keep `completes` and everything after, including FIX-484's `degraded_current`. Optionally fix the docstring line ~805 ("LATEST pipeline_complete") to say "any degraded completion at or after the last reattempt boundary".

<a id="qa-kb-037"></a>

## QA-KB-037 — Rapid version switches transiently display stale agent data

- **Page:** /runs/{id}
- **Route:** /runs/{id}
- **Severity:** Medium
- **Found by:** knowledge-base sweep (open card ISS-758)
- **Found at:** 2026-10-01 20:50
- **Reproduction mode:** Browser — reproduce from the URL below.

### Reproduction

1. Open a run with multiple versions (v1–v6+)
2. Click version menu and rapidly jump between distant versions (e.g., v6 then v2)
3. Observe agent panel briefly showing old version's agents/tokens before correcting (~10s)

### Expected

Agent panel always shows the selected version's current data immediately.

### Actual

When network latency delivers an older fetch after a newer one, that older version's agents/pipeline/tokens display transiently before self-correcting once the latest response arrives.

### Notes

Logged from the existing open knowledge card [ISS-758](.knowledge/cards/20260922-1421-ISS-758.md), which already holds the root cause.
Link that card from the ledger row and update it when this closes; do not mint a duplicate root card.
Agreed minimal fix (two independent reviewers, static read of the current code): In /Users/bilala/Developer/Projects/VELOCITY-AI-worktrees/feat-user-stories-v2/frontend/src/components/preview/PreviewPanel.tsx, add `const selectGen = useRef(0);` near `intendedSandboxRef`. At the top of `handleSelectVersion` (before the early returns at ~:896-910) add `const gen = ++selectGen.current;`. Bumping it on every call, including the live-return and `onOpenLiveRun` paths, also invalidates older in-flight fetches. After `await getWorkflow(...)`, change the apply line to `if (gen === selectGen.current) setViewingVersion(versionViewFrom(run));`. In the catch block, guard `setViewingVersion(null)` the same way. The latest call always passes the check, so normal switching is unchanged. Optionally add one frontend test that resolves two getWorkflow promises out of order and asserts the later selection wins.

<a id="qa-kb-038"></a>

## QA-KB-038 — test_migration_ledger F1 guard false positive on image block assembly in pdf_pages.py

- **Page:** n/a (code-level)
- **Route:** n/a (code-level)
- **Severity:** Medium
- **Found by:** knowledge-base sweep (open card ISS-858)
- **Found at:** 2026-10-01 20:50
- **Reproduction mode:** Test — reproduce by running the command below; it should fail (or misbehave) as described. No browser needed.

### Reproduction

1. cd backend && python3.11 -m pytest tests/unit/agents/test_migration_ledger.py::test_deleted_pattern_absent_from_backend -k 'F1-blocks' -v

### Expected

F1 banned-pattern guard returns no matches in backend/ (pattern 'blocks.append' guards deleted prompt-assembly code)

### Actual

Guard matches pdf_pages.py:202 where blocks.append() appends image content blocks to a local list, triggering a false positive that looks identical to an active regression

### Notes

Logged from the existing open knowledge card [ISS-858](.knowledge/cards/20260923-0148-ISS-858.md), which already holds the root cause.
Link that card from the ledger row and update it when this closes; do not mint a duplicate root card.
Agreed minimal fix (two independent reviewers, static read of the current code): In backend/agents/capabilities/input_providers/pdf_pages.py, rename the local list in `_blocks_for_document` (declared at line 130, appended to at line 202, returned at line 224) to `images`, so line 202 becomes `images.append(`. Do not use `page_blocks`, because `page_blocks.append` still contains the substring `blocks.append` and would match the F1 regex. No test change is needed.

<a id="qa-kb-039"></a>

## QA-KB-039 — Test fixture loops infinitely until GraphRecursionError; needs second scripted turn to stop graph cleanly

- **Page:** n/a (code-level)
- **Route:** n/a (code-level)
- **Severity:** Medium
- **Found by:** knowledge-base sweep (open card ISS-860)
- **Found at:** 2026-10-01 20:50
- **Reproduction mode:** Test — reproduce by running the command below; it should fail (or misbehave) as described. No browser needed.

### Reproduction

1. cd backend && python3.11 -m pytest backend/tests/agents/test_qa_ps_027_placeholder_completion.py::test_native_prototype_pipeline_placeholder_output_not_marked_completed -v

### Expected

The test completes cleanly with build agent reporting task_complete and the graph terminating normally.

### Actual

The single _ScriptedTurn causes the model to replay the tool-call turn in a loop for 1000 steps, resulting in GraphRecursionError and the run marked failed.

### Notes

Logged from the existing open knowledge card [ISS-860](.knowledge/cards/20260923-0229-ISS-860.md), which already holds the root cause.
Link that card from the ledger row and update it when this closes; do not mint a duplicate root card.
Agreed minimal fix (two independent reviewers, static read of the current code): In `_prototype_placeholder_scripts` (test_qa_ps_027_placeholder_completion.py:138-153), append a second turn after the `report_task_complete` turn: `_ScriptedTurn(texts=["Task complete."], usage=(5, 3))`. The model then ends on a text-only turn and the graph stops cleanly. Keep the validate script streaming PLACEHOLDER_TEXT, since branch 3 reads `ctx.last_streamed` from the last agent to run, which is validate (see the comment at lines 154-157). Then re-run only this test file to confirm the `final_output` and `published_status` assertions still hold.

<a id="qa-kb-040"></a>

## QA-KB-040 — useWorkflow.waveWorkers.test: toEqual checks exact equality but objects have 30 properties

- **Page:** n/a (code-level)
- **Route:** n/a (code-level)
- **Severity:** Medium
- **Found by:** knowledge-base sweep (open card ISS-863)
- **Found at:** 2026-10-01 20:50
- **Reproduction mode:** Test — reproduce by running the command below; it should fail (or misbehave) as described. No browser needed.

### Reproduction

1. cd frontend
2. npm test -- useWorkflow.waveWorkers.test.ts

### Expected

Both test assertions at lines 37-39 and 52-54 pass, verifying wave-worker structure is captured correctly.

### Actual

Tests fail: toEqual() requires exact equality; WaveWorkerEntry objects created by upsertWaveWorker have ~30 properties (many undefined) while test expectations are partial objects with 5 properties.

### Notes

Logged from the existing open knowledge card [ISS-863](.knowledge/cards/20260929-1021-ISS-863.md), which already holds the root cause.
Link that card from the ledger row and update it when this closes; do not mint a duplicate root card.
Agreed minimal fix (two independent reviewers, static read of the current code): In frontend/src/hooks/useWorkflow.waveWorkers.test.ts lines 37 and 52, change `expect(state.agents[0].waveWorkers).toEqual([...])` to `.toMatchObject([...])`. The expected objects keep their `taskId`, `status`, `workerIndex`, `waveIndex` and `waveTotal` fields. Optionally, once confirmed, set the card to resolved.

<a id="qa-kb-041"></a>

## QA-KB-041 — Escape key does not close workflow actions dropdown in some browsers

- **Page:** /workflows
- **Route:** /workflows
- **Severity:** Low
- **Found by:** knowledge-base sweep (open card BUG-104)
- **Found at:** 2026-10-01 20:50
- **Reproduction mode:** Browser — reproduce from the URL below.

### Reproduction

1. Navigate to /workflows
2. Click the ⋮ (Workflow actions) button on any saved workflow card
3. Press Escape key
4. Observe: in Safari or Firefox on macOS, the menu may remain open with aria-expanded still true

### Expected

Escape key dismisses the dropdown menu and returns focus to the trigger button, consistent with standard dropdown behavior and outside-click handling.

### Actual

Escape key has no effect when the trigger button was not focused by the click (common in Safari/Firefox on macOS); menu stays open and aria-expanded remains true.

### Notes

Logged from the existing open knowledge card [BUG-104](.knowledge/cards/20260829-1508-BUG-104.md), which already holds the root cause.
Link that card from the ledger row and update it when this closes; do not mint a duplicate root card.
Agreed minimal fix (two independent reviewers, static read of the current code): In KebabMenu (frontend/src/components/savedworkflows/SavedWorkflowsPage.tsx ~line 100), add `useEffect(() => { if (!isOpen) return; const h = (e: KeyboardEvent) => { if (e.key === "Escape") { onClose(); triggerRef.current?.focus(); } }; document.addEventListener("keydown", h); return () => document.removeEventListener("keydown", h); }, [isOpen, onClose]);`. Then delete the wrapper onKeyDown/handleKeyDown, or keep it with stopPropagation. Add a test in SavedWorkflowsPage.test.tsx that opens the menu without focusing the trigger, e.g. via fireEvent.click, then fires keydown Escape on document.body and expects aria-expanded="false".

**Interrupted fix (2026-10-01 22:40):** the first fixer for this bug was killed by an API limit mid-edit. It may have left a PARTIAL change in: frontend/src/app/admin/page.tsx, history/RevisionFamilyView.tsx, layout/AppHeader.tsx, savedworkflows/SavedWorkflowsPage.tsx, ui/NotificationPanel.tsx. Before editing, read `git diff` for those files, keep only the hunks that belong to this bug's fix and complete them; never revert hunks that belong to other QA-KB bugs (other bugs share some of these files).

<a id="qa-kb-042"></a>

## QA-KB-042 — Line citations in shutdown comments point to wrong code locations

- **Page:** n/a (code-level)
- **Route:** n/a (code-level)
- **Severity:** Low
- **Found by:** knowledge-base sweep (open card ISS-104)
- **Found at:** 2026-10-01 20:50
- **Reproduction mode:** Test — reproduce by running the command below; it should fail (or misbehave) as described. No browser needed.

### Reproduction

1. cd backend && python3.11 -m pytest tests/unit/test_run_shutdown_stale_citations.py -q
2. Observe: test fails because citations at run_shutdown.py:99-100 and line 275 do not match actual code locations

### Expected

All line citations in shutdown-path comments reference the correct current locations of the code they describe

### Actual

Citations have drifted: run_shutdown.py:99 cites run_commands.py:1401 (actual code at 2407); :100 cites :1356 (actual code at 2256); :275 cites outdated offsets for CancelledError handlers. Test fails on all four stale citations.

### Notes

Logged from the existing open knowledge card [ISS-104](.knowledge/cards/20260812-1312-ISS-104.md), which already holds the root cause.
Link that card from the ledger row and update it when this closes; do not mint a duplicate root card.
Agreed minimal fix (two independent reviewers, static read of the current code): Replace each stale cite with its current location. In docker-entrypoint.sh:27 use docker-compose.yml:75. In run_shutdown.py use the current NON_TERMINAL line in engine.py, and re-grep run_commands.py for the "NEVER cancel it on" comment, the type="chat_reply" write and the CancelledError handlers for the :99 and :284 cites. Then update the line numbers in test_run_shutdown_stale_citations.py to match, remove the strict xfail markers, and set the card to fixed. Line numbers keep drifting, so the better fix is to cite symbol names instead of line numbers.

<a id="qa-kb-043"></a>

## QA-KB-043 — Snapshot _PIPELINE_QUEUES while SSE subscriber-detach in flight — no race test

- **Page:** n/a (code-level)
- **Route:** n/a (code-level)
- **Severity:** Low
- **Found by:** knowledge-base sweep (open card ISS-105)
- **Found at:** 2026-10-01 20:50
- **Reproduction mode:** Static — reproduce by the check below (read/grep/short script). No browser needed.

### Reproduction

1. Static reading: run_shutdown.py:147-152 (step 2 snapshots _PIPELINE_QUEUES.keys()) occurs while run_stream.py SSE generators may still be in finally/subscriber-detach
2. Concurrent mutation path: a pump's finally still running when shutdown takes the snapshot

### Expected

Shutdown completes without error even if subscribers are detaching concurrently; snapshot operations are tolerant.

### Actual

Shutdown logic handles the race (never raises), but no regression test verifies snapshot tolerance to concurrent mutation per the card's explicit fix requirement.

### Notes

Logged from the existing open knowledge card [ISS-105](.knowledge/cards/20260812-1312-ISS-105.md), which already holds the root cause.
Link that card from the ledger row and update it when this closes; do not mint a duplicate root card.
Agreed minimal fix (two independent reviewers, static read of the current code): Add one async test to backend/tests/unit/app/test_run_shutdown.py, next to TestShutdownDrainsPumpTasks and reusing its `_isolate_registries` fixture. Seed `_PIPELINE_QUEUES` and `_PUMP_TASKS` with a few entries. Start a task that pops those entries and calls `_cleanup_pipeline` (run_engine.py:120), the same teardown a detaching SSE subscriber triggers, and let it interleave with `shutdown_run_infrastructure()` using `asyncio.gather` and `await asyncio.sleep(0)`. Assert the call does not raise, `summary["errors"] == []`, and the counters are consistent. Optionally add a one-line comment above run_shutdown.py:147 saying the snapshots are synchronous and so safe against concurrent detach.

<a id="qa-kb-044"></a>

## QA-KB-044 — Older completed revision with null output shows generic empty placeholder instead of distinct message

- **Page:** /runs/{id}
- **Route:** /runs/{id}
- **Severity:** Low
- **Found by:** knowledge-base sweep (open card ISS-154)
- **Found at:** 2026-10-01 20:50
- **Reproduction mode:** Browser — reproduce from the URL below.

### Reproduction

1. Navigate to a run with multiple versions (e.g., /runs/{id})
2. Open the Version menu (header dropdown)
3. Click an older, completed revision marked as v1 or earlier
4. Observe the preview pane

### Expected

A distinct message indicating this revision's output was not captured or backfilled, not the neutral 'Output will appear here' which reads as if the run never produced anything.

### Actual

Shows generic 'Output will appear here' placeholder, identical to a run still streaming or waiting to produce output.

### Notes

Logged from the existing open knowledge card [ISS-154](.knowledge/cards/20260813-0819-ISS-154.md), which already holds the root cause.
Link that card from the ledger row and update it when this closes; do not mint a duplicate root card.
Agreed minimal fix (two independent reviewers, static read of the current code): In /Users/bilala/Developer/Projects/VELOCITY-AI-worktrees/feat-user-stories-v2/frontend/src/components/preview/PreviewPanel.tsx, in the `!hasContent ? (...)` branch (~line 1825), change the text to `{overrideActive ? "No deliverable was saved for this version" : "Output will appear here"}`. `overrideActive` (`viewingVersion != null`, line 1056) is already in scope. By that point the failure, diverted, still-running and loading branches have already been taken, so only a terminal, non-failed older version reaches it. Then drop `it.fails` to `it` in PreviewPanel.olderVersionNullOutput.test.tsx.

**Interrupted fix (2026-10-01 22:40):** the first fixer for this bug was killed by an API limit mid-edit. It may have left a PARTIAL change in: frontend/src/components/preview/PreviewPanel.tsx. Before editing, read `git diff` for those files, keep only the hunks that belong to this bug's fix and complete them; never revert hunks that belong to other QA-KB bugs (other bugs share some of these files).

<a id="qa-kb-045"></a>

## QA-KB-045 — resume_run and _replay_clarify_run scan entire durable log instead of using bounded aggregate

- **Page:** n/a (code-level)
- **Route:** n/a (code-level)
- **Severity:** Low
- **Found by:** knowledge-base sweep (open card ISS-639)
- **Found at:** 2026-10-01 20:50
- **Reproduction mode:** Static — reproduce by the check below (read/grep/short script). No browser needed.

### Reproduction

1. Inspect backend/agents/execution_engine/engine.py:15682-15683 (resume_run)
2. Inspect backend/agents/execution_engine/engine.py:16152-16153 (_replay_clarify_run)
3. Both contain: await tail_store.read_events(run_id, after_seq=0) + max((r.seq for r in existing))+1
4. Compare to line 13058 which uses: await store._max_event_seq(run_id) + 1

### Expected

Seq seed calls tail_store._max_event_seq(run_id) for bounded aggregate over uq_run_events_scope_seq index

### Actual

Seq seed calls tail_store.read_events(run_id, after_seq=0) which materializes all run_events rows (26k-36k per the card) to derive a single integer

### Notes

Logged from the existing open knowledge card [ISS-639](.knowledge/cards/20260831-1645-ISS-639.md), which already holds the root cause.
Link that card from the ledger row and update it when this closes; do not mint a duplicate root card.
Agreed minimal fix (two independent reviewers, static read of the current code): In /Users/bilala/Developer/Projects/VELOCITY-AI-worktrees/feat-user-stories-v2/backend/agents/execution_engine/engine.py, at the two sites (~15682 and ~16152), replace the two lines `existing = await tail_store.read_events(run_id, after_seq=0)` and `start = max((r.seq for r in existing), default=0) + 1` with `start = (await tail_store._max_event_seq(run_id)) + 1`. Leave the surrounding try/except fallback to start=1. Optionally add a test next to backend/tests/agents/test_resume_marker_seq_allocation.py asserting read_events is not called from these two paths.

<a id="qa-kb-046"></a>

## QA-KB-046 — Remove stale xfail marker from test_revision_gating.py

- **Page:** n/a (code-level)
- **Route:** n/a (code-level)
- **Severity:** Low
- **Found by:** knowledge-base sweep (open card ISS-642)
- **Found at:** 2026-10-01 20:50
- **Reproduction mode:** Test — reproduce by running the command below; it should fail (or misbehave) as described. No browser needed.

### Reproduction

1. cd /Users/bilala/Developer/Projects/VELOCITY-AI-worktrees/feat-user-stories-v2/backend
2. python3 -m pytest tests/unit/agents/test_revision_gating.py::test_declared_revision_with_parent_seeds_after_assert_owns -v
3. Observe XPASS status (expected to fail but passed)
4. Remove xfail marker at test_revision_gating.py:186
5. Re-run test; should show PASSED

### Expected

Test should pass because production now reads .uploads/manifest.json, matching the test's expectations.

### Actual

Test is marked xfail (expected failure), so it shows XPASS when run, causing the suite to fail under strict=True.

### Notes

Logged from the existing open knowledge card [ISS-642](.knowledge/cards/20260831-1842-ISS-642.md), which already holds the root cause.
Link that card from the ledger row and update it when this closes; do not mint a duplicate root card.
Agreed minimal fix (two independent reviewers, static read of the current code): In backend/tests/unit/agents/test_revision_gating.py, delete line 186 (`@pytest.mark.xfail(reason="ISS-633 unfixed", strict=True)`). Keep the `@pytest.mark.issue("ISS-633")` marker. Then close ISS-642.

<a id="qa-kb-047"></a>

## QA-KB-047 — docker-compose.prod.yml missing though terraform filemd5 and EC2 bootstrap require it

- **Page:** n/a (code-level)
- **Route:** n/a (code-level)
- **Severity:** High
- **Found by:** knowledge-base sweep 2 (open card ISS-179)
- **Found at:** 2026-10-02 02:55
- **Reproduction mode:** Static — reproduce by the check below (read/grep/short script). No browser needed.

### Reproduction

1. From the repo root run: ls docker-compose.prod.yml (No such file).
2. Read infra/terraform/app/main.tf lines 196-199: aws_s3_object source and filemd5() point at ../../../docker-compose.prod.yml.
3. Read infra/scripts/bootstrap-ec2.sh lines 633-636 and 1326-1329: the S3 copy and every compose command use the prod override file.

### Expected

docker-compose.prod.yml exists at the repo root so terraform can hash and upload it and bootstrap can run docker compose with the prod override.

### Actual

The file was deleted by 215b911e0 ("removed screenshots") and never restored. Terraform filemd5 fails on the missing file and bootstrap would have no prod override to fetch.

### Notes

Logged from the existing open knowledge card [ISS-179](.knowledge/cards/20260825-1600-ISS-179.md), which already holds the root cause.
Link that card from the ledger row and update it when this closes; do not mint a duplicate root card.
Triage fix sketch (static read of the current code, not binding on the analyzer): Restore the file with: git show 215b911e0^:docker-compose.prod.yml > docker-compose.prod.yml (35 lines, repo root). README.md, docker-compose.yml and app.env.example are already back, so they need no change.

<a id="qa-kb-048"></a>

## QA-KB-048 — Saved workflow with removed agents launches the full built-in roster (plan completion overwrites restore)

- **Page:** /workflows/{id}/run
- **Route:** /workflows/{id}/run
- **Severity:** High
- **Found by:** knowledge-base sweep 2 (open card ISS-943)
- **Found at:** 2026-10-02 02:55
- **Reproduction mode:** Test — reproduce by running the command below; it should fail as described. No browser needed.

### Reproduction

1. From the repo root, add a component test for LaunchWizard like the card's probe (evidence/qa-kb-011/10-fix-scratch-plan-completion.test.tsx.txt): set sessionStorage prototype.draft with agentIds ["prototype-plan"], mock getWorkflowDetail to return five prototype steps, mount LaunchWizard.
2. Run it with: cd frontend && npx vitest run <that test file>
3. Click Continue and read the launch draft agentIds.

### Expected

The launch draft carries the saved roster ["prototype-plan"].

### Actual

The launch draft carries all five ids: prototype-specify, prototype-plan, prototype-analyze, prototype-build, prototype-validate. Both the cold path (library lands after the detail) and the warm path (library preloaded) behave this way.

### Notes

Logged from the existing open knowledge card [ISS-943](.knowledge/cards/20261002-0037-ISS-943.md), which already holds the root cause.
Link that card from the ledger row and update it when this closes; do not mint a duplicate root card.
Triage fix sketch (static read of the current code, not binding on the analyzer): In frontend/src/components/workflow/LaunchWizard.tsx add a ref (e.g. savedRosterRef = useRef(false)). Set it to true at :432 when `restored.length > 0` is applied. In the completion effect (:481-495), return prev at the top of the functional updater when savedRosterRef.current is true. Keep the existing length/tree guard for the non-restored case so partial library rosters (ppt_v2) are still completed. Add the card's two cases (cold and warm) as a regression test.

<a id="qa-kb-049"></a>

## QA-KB-049 — Cold-loading /runs/{id}/audit, /files or /steps of a generating run redirects to /stream (Steps tab)

- **Page:** /runs/{id}/audit (also /files, /steps) for a generating run
- **Route:** /runs/{id}/audit (also /files, /steps) for a generating run
- **Severity:** Medium
- **Found by:** knowledge-base sweep 2 (open card BUG-024)
- **Found at:** 2026-10-02 02:55
- **Reproduction mode:** Static — reproduce by the check below (read/grep/short script). No browser needed.

### Reproduction

1. Sign in as admin@velocity.ai and start a run that stays in status generating.
2. Copy its /runs/{id}/audit URL.
3. Open that URL in a fresh tab (cold load).
4. The URL becomes /runs/{id}/stream and the Steps tab shows. After the run completes, the same URL stays on Audit.

### Expected

The requested URL and tab survive a cold load while the run is generating. Only a fresh launch lands on /stream.

### Actual

The URL is rewritten to /stream and the Steps tab is forced.

### Notes

Logged from the existing open knowledge card [BUG-024](.knowledge/cards/20260827-BUG-024.md), which already holds the root cause.
Link that card from the ledger row and update it when this closes; do not mint a duplicate root card.
Triage fix sketch (static read of the current code, not binding on the analyzer): In frontend/src/components/layout/DashboardLayout.tsx:855, skip the router.push(routes.runStream(incomingRunId)) when window.location.pathname already starts with /runs/{incomingRunId}/ (or use usePathname). A fresh launch, where the path is not yet a run URL, still pushes /stream. Then check that page.tsx's T11 effect (about 3567-3750) still attaches the stream only on the /stream screen, and add a source test beside the existing *.source.test.ts files.

<a id="qa-kb-050"></a>

## QA-KB-050 — Library-added agents on /workflows/new get an invisible disabled Remove though most are not core

- **Page:** /workflows/new
- **Route:** /workflows/new
- **Severity:** Medium
- **Found by:** knowledge-base sweep 2 (open card BUG-025)
- **Found at:** 2026-10-02 02:55
- **Reproduction mode:** Static — reproduce by the check below (read/grep/short script). No browser needed.

### Reproduction

1. Read frontend/src/components/workflow/composer/ComposerPage.tsx:1430 and :1629: pipelineType is passed from the shared workflowType prop (DashboardLayout.tsx:3214).
2. Read AgentsPopup.tsx:210-225: with a stale non-custom workflowType (e.g. user_stories) and a library agent such as epic-architect, getRole returns required.
3. Read CanvasNode.tsx:478-480 and :638-644: required gives no Core badge (badge needs locked) and removable is false, so Remove is disabled with disabled:opacity-0 (invisible).

### Expected

On /workflows/new (a custom composition) every library-added agent is removable, and the Remove control only locks, visibly, for agents that are really core in the canvas's own pipeline (e.g. /workflows/ppt/canvas). The lock and the Core badge agree.

### Actual

Added agents show a disabled, invisible Remove titled "Core agents can't be removed", though only one shows a Core badge. The author cannot remove them without reloading and losing the canvas.

### Notes

Logged from the existing open knowledge card [BUG-025](.knowledge/cards/20260827-BUG-025.md), which already holds the root cause.
Link that card from the ledger row and update it when this closes; do not mint a duplicate root card.
Triage fix sketch (static read of the current code, not binding on the analyzer): 1) ComposerPage.tsx:1430, :1629 and :669/:672: replace workflowType with a derived canvasPipelineType = (builtinCanvasType as WorkflowType) ?? "custom" for getRole and the pipelineType props, so getRole returns optional for custom compositions and the real type for built-in canvases. 2) CanvasNode.tsx:478-480 and AgentRow.tsx:84-86: make the badge and the Remove lock read the same predicate (role !== "optional" shows Core and locks), keeping the guard. 3) CanvasNode.tsx:644 and AgentRow.tsx:200: swap disabled:opacity-0 for a greyed state (e.g. disabled:opacity-40) so the title is reachable. Update CanvasNode/ComposerPage tests accordingly.

<a id="qa-kb-051"></a>

## QA-KB-051 — Knowledge rebuild crashes under python3 3.9: write_text(newline=) in build_context leaves .knowledge half-applied

- **Page:** n/a (code-level)
- **Route:** n/a (code-level)
- **Severity:** Medium
- **Found by:** knowledge-base sweep 2 (open card BUG-127)
- **Found at:** 2026-10-02 02:55
- **Reproduction mode:** Test — reproduce by running the command below; it should fail as described. No browser needed.

### Reproduction

1. From the repo root run: /usr/bin/python3 tools/knowledge/rebuild_knowledge.py --skip-architecture
2. The index stage rewrites INDEX.md and state.yaml.
3. The context stage then raises TypeError: write_text() got an unexpected keyword argument 'newline'.
4. CONTEXT.md is left stale and the validate stage is never reached.

### Expected

The rebuild completes under the interpreter the docs name (bare python3), or fails without leaving state.yaml and INDEX.md advanced ahead of CONTEXT.md.

### Actual

The context stage dies with a TypeError after index has already written INDEX.md and state.yaml. CONTEXT.md is stale and validate is skipped.

### Notes

Logged from the existing open knowledge card [BUG-127](.knowledge/cards/20260918-BUG-127.md), which already holds the root cause.
Link that card from the ledger row and update it when this closes; do not mint a duplicate root card.
Triage fix sketch (static read of the current code, not binding on the analyzer): 1) tools/knowledge/build_context.py:431: drop newline='\n' so the call is OUT_PATH.write_text(body, encoding='utf-8'). POSIX text mode already writes '\n'. 2) Optionally make the ordering survivable in tools/knowledge/rebuild_knowledge.py (run_stage around :82, _run around :165): snapshot INDEX.md and state.yaml before the index stage and restore them if context or validate fails.

<a id="qa-kb-052"></a>

## QA-KB-052 — /create/app Input panel is fully interactive for a tier without app_builder; no lock state

- **Page:** /create/app
- **Route:** /create/app
- **Severity:** Medium
- **Found by:** knowledge-base sweep 2 (open card ISS-472)
- **Found at:** 2026-10-02 02:55
- **Reproduction mode:** Browser — reproduce from the URL below.

### Reproduction

1. Open http://localhost:3000 and sign in as admin@velocity.ai (or a basic-tier account such as qa-basic@flowinqa.com if admin has a higher tier)
2. Navigate directly to http://localhost:3000/create/app (same for /create/user-stories)
3. Observe the brief textarea, agent picker and Run button are enabled with no lock or upgrade indication
4. Type a brief and click Run; only the backend 403 from _require_tier_entitlement rejects it

### Expected

A tier lacking the pipeline sees the same locked/upgrade state the dashboard catalog card shows, and Run is blocked client-side.

### Actual

IdeaInputPage renders ungated for an unentitled pipeline type; only the backend rejects the run after the user composes a brief.

### Notes

Logged from the existing open knowledge card [ISS-472](.knowledge/cards/20260829-0110-ISS-472.md), which already holds the root cause.
Link that card from the ledger row and update it when this closes; do not mint a duplicate root card.
Triage fix sketch (static read of the current code, not binding on the analyzer): Mirror LaunchWizard.tsx:905-911. In DashboardLayout.tsx:3159 pass userTier={userTier} to IdeaInputPage. In IdeaInputPage.tsx accept userTier, compute locked = !canRunPipeline(userTier, workflowType) and getUpgradeTier(userTier, workflowType) (import from @/lib/entitlements), then disable Run and show the same upgrade banner LaunchWizard shows when locked. Optionally add a vitest case for IdeaInputPage locked state.

<a id="qa-kb-053"></a>

## QA-KB-053 — Files tab names/sizes/downloads a pinned version's deliverable from the live tree, not its ref

- **Page:** /runs/{id}/versions/1 (Files tab)
- **Route:** /runs/{id}/versions/1 (Files tab)
- **Severity:** Medium
- **Found by:** knowledge-base sweep 2 (open card ISS-665)
- **Found at:** 2026-10-02 02:55
- **Reproduction mode:** Test — reproduce by running the command below; it should fail as described. No browser needed.

### Reproduction

1. From repo root: cd frontend && npx vitest run src/lib/api.resolveRunDeliverableRef.test.ts
2. The it.fails case passes only because resolveRunDeliverable takes no 4th ref argument and requests /sandbox without ref=v1.
3. Static: grep resolveRunDeliverable in frontend/src/components/results/FilesTab.tsx (lines 535 and 563) and see no ref is passed.

### Expected

With an older family member pinned, the Files tab row (and the From v{n-1} section) takes name and size from that version's own ref snapshot, and Download serves bytes at that ref.

### Actual

The row is named and sized from the live tree, and Download returns live bytes under the older version's label.

### Notes

Logged from the existing open knowledge card [ISS-665](.knowledge/cards/20260917-1311-ISS-665.md), which already holds the root cause.
Link that card from the ledger row and update it when this closes; do not mint a duplicate root card.
Triage fix sketch (static read of the current code, not binding on the analyzer): 1) api.ts:1606 add optional ref?: string param and use getRunSandbox(token, runId, ref) at :1621. 2) FilesTab.tsx: add a selectedRef prop; pass it at the :563 call with effect deps [runId, isRunning, selectedRef]; add ref to the workspace descriptor (:168, :486) and pass it to getRunSandboxFileBlob at :740. For the :535 base-version call, resolve the parent's own ref if known, else leave live. 3) PreviewPanel.tsx:1922 pass selectedRef={sandboxSelectedRef}; also pass it at :1437 (ISS-677 overlap). 4) Remove it.fails in api.resolveRunDeliverableRef.test.ts and update FilesTab.workspaceFilename.test.tsx mock signature.

<a id="qa-kb-054"></a>

## QA-KB-054 — Launch 400s "Invalid agent_ids" when a custom-agent file workflow's roster is sent as agent_ids

- **Page:** POST launch_run (file-pipeline launch of custom-agent workflows such as prototype_v2)
- **Route:** POST launch_run (file-pipeline launch of custom-agent workflows such as prototype_v2)
- **Severity:** Medium
- **Found by:** knowledge-base sweep 2 (open card ISS-687)
- **Found at:** 2026-10-02 02:55
- **Reproduction mode:** Static — reproduce by the check below (read/grep/short script). No browser needed.

### Reproduction

1. Read backend/app/api/run_commands.py:3520-3550 and backend/agents/registry.py allowed_custom_agent_ids: the allowed ids come from AGENT.md frontmatter only.
2. Run: grep -rln 'agent: custom-agent' backend/agents/workflows/*/workflow.yaml. It lists 14 of the 36 file workflows, and their compiled ids are custom-agent:<instance_id> with no AGENT.md.
3. Read frontend/src/app/[...view]/page.tsx:536 and :2530. Both forward the unfiltered roster as agentIds, so a prototype_v2 launch with those ids is rejected with invalid_agent_ids.

### Expected

A file workflow launch whose agent_ids are only compiled custom-agent:* ids succeeds, using the compiled plan as the roster.

### Actual

The launch returns 400 invalid_agent_ids for every sender except LaunchWizard, which filters the ids client-side.

### Notes

Logged from the existing open knowledge card [ISS-687](.knowledge/cards/20260918-ISS-687.md), which already holds the root cause.
Link that card from the ledger row and update it when this closes; do not mint a duplicate root card.
Triage fix sketch (static read of the current code, not binding on the analyzer): In backend/app/api/run_commands.py at about line 3520, when launch_source is FILE_PIPELINE only, drop ids starting with CUSTOM_AGENT_PREFIX from agent_ids before the allow-list check. If the list is then empty, set agent_ids to None so the existing else branch compiles the plan. Do not touch allowed_custom_agent_ids (KAN-75). Do not strip for USER_WORKFLOW_FLAT, because the ISS-182 stale-override error there is intentional. Optionally add a backend test that launches prototype_v2 with custom-agent:fi-planner in agent_ids.

<a id="qa-kb-055"></a>

## QA-KB-055 — Another family's finished revision hijacks the run-detail screen you are viewing

- **Page:** /runs/[id] (run detail, app/[...view]/page.tsx)
- **Route:** /runs/[id] (run detail, app/[...view]/page.tsx)
- **Severity:** Medium
- **Found by:** knowledge-base sweep 2 (open card ISS-745)
- **Found at:** 2026-10-02 02:55
- **Reproduction mode:** Static — reproduce by the check below (read/grep/short script). No browser needed.

### Reproduction

1. Read frontend/src/app/[...view]/page.tsx:1605-1629.
2. Note isRevisionCompletion tests only the pipeline_type suffix and the OR at :1629 bypasses isForeignCompletion.
3. Scenario: in one tab launch a *_revision on family A, open family B's run detail, let A's revision complete; setContentSourceRunId(A's run id) fires and DashboardLayout refetches family A.

### Expected

A *_revision completion advances contentSourceRunId only when the completing run belongs to the family currently viewed; otherwise it is treated as a background completion (setBackgroundCompletedRunId) and the screen is untouched.

### Actual

Any tracked *_revision completion, from any family, calls setContentSourceRunId, switching the viewed screen to the other family's content.

### Notes

Logged from the existing open knowledge card [ISS-745](.knowledge/cards/20260922-1400-ISS-745.md), which already holds the root cause.
Link that card from the ledger row and update it when this closes; do not mint a duplicate root card.
Triage fix sketch (static read of the current code, not binding on the analyzer): page.tsx:1617-1629. Make isRevisionCompletion require lineage. Either carry parent_run_id on the pipeline_complete data (engine.py, where pipeline_run_id is emitted; the family-root walk is near engine.py:1008), or record revisionParent[newRunId]=trackedRunIdRef.current at revision launch. Then set isRevisionCompletion = suffix match AND completing run's parent equals trackedRunIdRef.current (or shares its family root). Non-matching revision completions fall through to the setBackgroundCompletedRunId branch at :1625. Add a frontend test with two families' run ids.

<a id="qa-kb-056"></a>

## QA-KB-056 — Materialized streamed_text payload keeps artifact wrapper/preamble the Preview strips

- **Page:** n/a (code-level)
- **Route:** n/a (code-level)
- **Severity:** Medium
- **Found by:** knowledge-base sweep 2 (open card ISS-791)
- **Found at:** 2026-10-02 02:55
- **Reproduction mode:** Test — reproduce by running the command below; it should fail as described. No browser needed.

### Reproduction

1. From backend/, build an ectx stub with last_streamed='Thinking...\n<artifact><!DOCTYPE html><html></html></artifact>' and a streamed_text deliverable with a nominal output name.
2. Call build_flat_payload (engine.py ~1337-1650) from a short script, or add a case to backend/tests/unit/agents/test_deliverable_resolvers.py and run: cd backend && python -m pytest tests/unit/agents/test_deliverable_resolvers.py
3. Compare the materialized file bytes with StreamedTextResolver().resolve(ectx).

### Expected

The materialized payload file equals the resolver output: no artifact wrapper and no pre-document prose.

### Actual

The payload file holds the raw last_streamed bytes, including the wrapper and preamble. Git versioning and the chain admission gate ingest those bytes.

### Notes

Logged from the existing open knowledge card [ISS-791](.knowledge/cards/20260922-1823-ISS-791.md), which already holds the root cause.
Link that card from the ledger row and update it when this closes; do not mint a duplicate root card.
Triage fix sketch (static read of the current code, not binding on the analyzer): backend/agents/execution_engine/engine.py:1489-1491: replace the raw assignment with the resolver output, e.g. `_resolved = _CAPABILITY_REGISTRY.resolve("deliverable", "streamed_text").resolve(ectx)`, then `if _resolved: _streamed_text = _resolved` (this also covers coerce_to_declared_format). Minimal alternative: `_streamed_text = strip_pre_document_prose(unwrap_artifact(_raw_streamed))` using the same imports the ppt block uses at ~1516. Add a regression test with a wrapped and prefixed last_streamed. Then run the single test files that touch build_flat_payload (tests/agents/test_nameless_deliverable_v3.py, tests/agents/test_finalizer_v2.py) to check that none pins the raw bytes.

<a id="qa-kb-057"></a>

## QA-KB-057 — Duplicate-context guard API tests fail 8/8: missing principal override, then stale source run seed

- **Page:** n/a (code-level)
- **Route:** n/a (code-level)
- **Severity:** Medium
- **Found by:** knowledge-base sweep 2 (open card ISS-905)
- **Found at:** 2026-10-02 02:55
- **Reproduction mode:** Test — reproduce by running the command below; it should fail as described. No browser needed.

### Reproduction

1. From the repo root, run: cd backend && python -m pytest tests/integration/api/test_duplicate_context_guard_api.py -x -q
2. Observe 401 {"detail":"Not authenticated"} on every test (8 failed).
3. With the principal override added, 6 tests then fail with 422 source_payload_missing.

### Expected

All 8 tests pass and guard the legacy_context_block_stripped behaviour in _launch_run_core.

### Actual

All 8 tests fail with 401. After the principal override is added, 6 of them fail with 422 source_payload_missing because the source run has no committed .chain payload.

### Notes

Logged from the existing open knowledge card [ISS-905](.knowledge/cards/20261001-2149-ISS-905.md), which already holds the root cause.
Link that card from the ledger row and update it when this closes; do not mint a duplicate root card.
Triage fix sketch (static read of the current code, not binding on the analyzer): 1) In backend/tests/integration/api/test_duplicate_context_guard_api.py near line 101, import get_current_principal and tests.fakes.principal.principal_for, and add app.dependency_overrides[get_current_principal] = lambda: (state['user'], principal_for(state['user'])), mirroring test_rest_run_launch_api.py:115-130. 2) Rewrite _seed_source_run (lines 133-152) to build a finalized v2 source: a sandbox with the flat .chain/ payload committed, a tag or internal ref, and the finalization record the selector reads at run_commands.py:4930-4995. Reuse the helpers in backend/tests/agents/test_chain_exact_ref.py or test_finalizer_v2.py. Do not relax the 422 or the principal dependency. 3) Update the comment at frontend/e2e/tests/ts-v2-chain-versioning.spec.ts:8 to the new path backend/tests/integration/api/test_duplicate_context_guard_api.py.

<a id="qa-kb-058"></a>

## QA-KB-058 — Launch wizard Back silently discards typed brief, template/design-system picks and attachments

- **Page:** /create/prototype
- **Route:** /create/prototype
- **Severity:** Medium
- **Found by:** knowledge-base sweep 2 (open card ISS-917)
- **Found at:** 2026-10-02 02:55
- **Reproduction mode:** Browser — reproduce from the URL below.

### Reproduction

1. Open http://localhost:3000/create/prototype and sign in as admin@velocity.ai.
2. Type text in the brief field and pick a template or design system.
3. Click the header Back button ([aria-label="Back to dashboard"]).
4. Observe immediate navigation with no [role=dialog].
5. Reopen /create/prototype and see the brief and picks are gone.

### Expected

With unsaved input, Back opens the in-app "Leave without saving?" dialog with Stay and Leave anyway. No native confirm() (S-19-17 bans it). Launch never prompts.

### Actual

Back navigates away at once and all typed input is lost.

### Notes

Logged from the existing open knowledge card [ISS-917](.knowledge/cards/20261001-2220-ISS-917.md), which already holds the root cause.
Link that card from the ledger row and update it when this closes; do not mint a duplicate root card.
Triage fix sketch (static read of the current code, not binding on the analyzer): 1) Extract the dialog markup from DashboardLayout.tsx:3478-3517 into a small shared component and use it in both places. 2) In LaunchWizard.tsx add a user-has-edited latch ref set in the user-driven handlers for brief, template, design system, attachments and discovery answers; do not diff against a mount snapshot because the draft restore (:405-438), library re-seed (:460-465) and plan merge (:472-486) rewrite state without user action. 3) At the Back onClick (:1078), if the latch is set open the dialog and call goBackOr only on Leave anyway; leave handleLaunch (:985/:1038) unguarded. 4) Add an e2e in suite 03_launch_panels modelled on test_iss786_launch_wizard_back_loop.py using L.BACK_TO_DASHBOARD.

<a id="qa-kb-059"></a>

## QA-KB-059 — Save as my version enabled while override fetch is pending, overwriting override with library roster

- **Page:** /create/user_stories
- **Route:** /create/user_stories
- **Severity:** Medium
- **Found by:** knowledge-base sweep 2 (open card ISS-919)
- **Found at:** 2026-10-02 02:55
- **Reproduction mode:** Test — reproduce by running the command below; it should fail as described. No browser needed.

### Reproduction

1. Add a vitest to frontend/src/components/workflow/IdeaInputPage.declaredCapabilities.test.tsx: mock getWorkflowDetail with a never-resolving deferred, preload library agents, render IdeaInputPage for user_stories.
2. Assert the 'Save as my version' and 'Save workflow' buttons are disabled while the deferred is pending.
3. Run from repo root: cd frontend && npx vitest run src/components/workflow/IdeaInputPage.declaredCapabilities.test.tsx
4. Today the assertion fails: both buttons are enabled because pipelineAgents holds the library roster.

### Expected

Both Save buttons stay disabled until getWorkflowDetail has settled, so only a roster the user has seen can be saved.

### Actual

Both buttons enable as soon as the library roster fills pipelineAgents. Clicking Save as my version POSTs overrides_pipeline_type plus the system roster, and the server replaces the user's real override row.

### Notes

Logged from the existing open knowledge card [ISS-919](.knowledge/cards/20261001-2221-ISS-919.md), which already holds the root cause.
Link that card from the ledger row and update it when this closes; do not mint a duplicate root card.
Triage fix sketch (static read of the current code, not binding on the analyzer): In IdeaInputPage.tsx add a detailSettled state (false initially, reset on workflowId change), set true in the getWorkflowDetail .then at ~:1159 (success only, not .finally, since the .catch degrades to an empty declaration); also true when there is no jwt or no workflowId. Add !detailSettled to the disabled expressions at :1983 (Save workflow, not-loading) and :1998 (Save as my version, success only), keeping the existing length===0 and migration terms.

<a id="qa-kb-060"></a>

## QA-KB-060 — Transient GET failure on /workflows/{id}/edit leaves Save workflow creating a new row instead of updating

- **Page:** /workflows/{id}/edit
- **Route:** /workflows/{id}/edit
- **Severity:** Medium
- **Found by:** knowledge-base sweep 2 (open card ISS-923)
- **Found at:** 2026-10-02 02:55
- **Reproduction mode:** Static — reproduce by the check below (read/grep/short script). No browser needed.

### Reproduction

1. Sign in as admin@velocity.ai.
2. Abort GET /api/user-workflows/<id> with page.route (a 5xx or a network failure, not 401/403/404).
3. Open /workflows/<existing-id>/edit.
4. Type a name and add one agent.
5. Click Save workflow and watch for POST /api/user-workflows instead of a PATCH.

### Expected

The load failure is shown (error or retry), or Save is unavailable until the row has loaded. Save never creates a different row than the one being edited.

### Actual

The composer mounts blank in create mode and Save workflow POSTs a new workflow. It returns 201 when the name differs from the saved one and at least one agent is added.

### Notes

Logged from the existing open knowledge card [ISS-923](.knowledge/cards/20261001-2223-ISS-923.md), which already holds the root cause.
Link that card from the ledger row and update it when this closes; do not mint a duplicate root card.
Triage fix sketch (static read of the current code, not binding on the analyzer): 1) page.tsx near :3790-3828: add a workflowEditSeed state of "idle", "loading", "ready" or "failed" for /edit routes. Set "ready" only in the .then, and "failed" in the catch for any non-401 error, never in a .finally. 2) DashboardLayout.tsx: forward it to ComposerPage as a prop (for example seedPending / seedFailed) next to initialUserWorkflowId at :3251. 3) ComposerPage.tsx: when the prop is set, disable the Save workflow button (around :1387) and guard handleSave (:919). Show a "failed to load, reload" banner like IdeaInputPage's loadError.

<a id="qa-kb-061"></a>

## QA-KB-061 — Revision launched via REST with source_workflow_run_id gets no parent_run_id (admission gate zeroes source)

- **Page:** POST /api/runs/launch (pipeline_type ending _revision, with source_workflow_run_id)
- **Route:** POST /api/runs/launch (pipeline_type ending _revision, with source_workflow_run_id)
- **Severity:** Medium
- **Found by:** knowledge-base sweep 2 (open card ISS-949)
- **Found at:** 2026-10-02 02:55
- **Reproduction mode:** Test — reproduce by running the command below; it should fail as described. No browser needed.

### Reproduction

1. From repo root run: cd backend && DATABASE_URL=sqlite:///:memory: .venv/bin/python -m pytest tests/integration/api/test_rest_run_launch_api.py -k test_owned_source_links_the_child
2. Observe assert None == parent id on child.parent_run_id
3. Static cause: run_commands.py:3855 uses the admission source_id, which is None for workflows without chains_from (5293-5297)

### Expected

A user_stories_revision launch with an owned source_workflow_run_id creates a child whose parent_run_id equals the source run id.

### Actual

parent_run_id is None, because the declaration gate zeroes the source id before _launch_run_core resolves the revision parent.

### Notes

Logged from the existing open knowledge card [ISS-949](.knowledge/cards/20261002-0107-ISS-949.md), which already holds the root cause.
Link that card from the ledger row and update it when this closes; do not mint a duplicate root card.
Triage fix sketch (static read of the current code, not binding on the analyzer): In backend/app/api/run_commands.py:3033-3037, resolve the revision parent from (request_source_workflow_run_id or source_workflow_run_id) via _resolve_owned_parent_run_id, so revision pipelines keep the owner-checked link even when the chain gate zeroes the source. Leave source_run_id and chain behaviour untouched. Separately, update the stale tests: expect 404 for foreign/unknown sources on chains_from workflows, and add agent_id to the driver-test events in test_rest_run_launch_api.py (about lines 543-660 and 907-972) and test_rest_revisions_api.py::test_driver_happy_path_persists_output_columns.

<a id="qa-kb-062"></a>

## QA-KB-062 — Stale chain.brief overrides the brief a caller staged in ppt.draft/prototype.draft in LaunchWizard

- **Page:** n/a (code-level)
- **Route:** n/a (code-level)
- **Severity:** Low
- **Found by:** knowledge-base sweep 2 (open card ISS-347)
- **Found at:** 2026-10-02 02:55
- **Reproduction mode:** Static — reproduce by the check below (read/grep/short script). No browser needed.

### Reproduction

1. Read frontend/src/components/workflow/LaunchWizard.tsx:404-414 and confirm the early return after chain.brief.
2. Read DashboardLayout.tsx:2393, :1685 and :1712 and confirm they stage a draft without clearing chain.* keys.
3. Scenario, not reproduced live: leave chain.brief set from an abandoned chain push, then use Edit brief and run again; the wizard shows the chained brief and the Continuing-from banner.

### Expected

A brief staged by the caller (ppt.draft or prototype.draft) wins; a chain hand-off applies only to the navigation that wrote it.

### Actual

An unconsumed chain.brief wins over the staged draft, and a stale chain.context_block is appended to the next unrelated run.

### Notes

Logged from the existing open knowledge card [ISS-347](.knowledge/cards/20260828-2058-ISS-347.md), which already holds the root cause.
Link that card from the ledger row and update it when this closes; do not mint a duplicate root card.
Triage fix sketch (static read of the current code, not binding on the analyzer): In LaunchWizard.tsx:404-414, read the mode's draft key first. If a draft exists, ignore chain.brief and remove chain.brief, chain.from, chain.context_block and chain.source_run_id so no stale chain state rides into the run. Fall back to chain.brief only when no draft exists. Add a LaunchWizard.test.tsx case with both chain.brief and a draft set, asserting the draft brief wins.

<a id="qa-kb-063"></a>

## QA-KB-063 — E2E clarify specs assert round-less "Clarifications answered"; S-23-45 skips, S-18-08 will fail

- **Page:** n/a (code-level)
- **Route:** n/a (code-level)
- **Severity:** Low
- **Found by:** knowledge-base sweep 2 (open card ISS-662)
- **Found at:** 2026-10-02 02:55
- **Reproduction mode:** Static — reproduce by the check below (read/grep/short script). No browser needed.

### Reproduction

1. grep -n 'Clarifications' tests/integration/e2e/suites/23_controls_inventory/test_controls_inventory.py tests/integration/e2e/suites/18_chat_lane/test_chat_lane.py tests/integration/screens/18-chat-lane.feature.md
2. sed -n 160,175p backend/app/agents/chat_narrator.py to see the numbered text now emitted

### Expected

E2E probes match the numbered text ("Clarifications round N answered"), so S-23-45 asserts instead of skipping and S-18-08 checks distinct numbered round cards.

### Actual

Probes search the exact old string "Clarifications answered". On post-fix runs S-23-45 skips, and the S-18-08 D-21 guard fails with "D-21 is fixed; rewrite this".

### Notes

Logged from the existing open knowledge card [ISS-662](.knowledge/cards/20260917-1307-ISS-662.md), which already holds the root cause.
Link that card from the ledger row and update it when this closes; do not mint a duplicate root card.
Triage fix sketch (static read of the current code, not binding on the analyzer): 1) test_controls_inventory.py:643-645: match regex r"Clarifications( round \d+)? answered" against body. 2) test_chat_lane.py:34 and :295-304: rewrite S-18-08 to assert one numbered "Clarifications round N answered" and one "Round N: Before I build..." card per round, with distinct text and ids (drop the "repeats" assertion). 3) 18-chat-lane.feature.md:59 and :212-223: update the Gherkin to say each round shows a distinct numbered card.

<a id="qa-kb-064"></a>

## QA-KB-064 — API-built RunSandbox assumes has_git=True without a real .git, so restore can raise CalledProcessError

- **Page:** n/a (code-level)
- **Route:** n/a (code-level)
- **Severity:** Low
- **Found by:** knowledge-base sweep 2 (open card ISS-678)
- **Found at:** 2026-10-02 02:55
- **Reproduction mode:** Static — reproduce by the check below (read/grep/short script). No browser needed.

### Reproduction

1. Read backend/app/agents/sandbox.py:564 and :614: has_git defaults to True and is stored as-is.
2. Grep 'RunSandbox(' in backend/app/api/: none of the construction sites pass has_git.
3. Read backend/app/api/runs.py:2511: the restore endpoint builds the sandbox this way, then calls commit_all. On a sandbox directory with no .git, git add -A fails.

### Expected

A sandbox with no .git has has_git=False. Git delegations return their documented non-git results, and restore takes the 'not a git repo' branch instead of raising.

### Actual

The sandbox claims has_git=True. Git subprocesses are spawned that cannot succeed (FIX-522's ceiling makes them fail closed), and commit_all raises a raw CalledProcessError.

### Notes

Logged from the existing open knowledge card [ISS-678](.knowledge/cards/20260917-1449-ISS-678.md), which already holds the root cause.
Link that card from the ledger row and update it when this closes; do not mint a duplicate root card.
Triage fix sketch (static read of the current code, not binding on the analyzer): Do not change the constructor default, because the engine builds sandboxes before git_init_sandbox. Instead, at the API-only construction sites (backend/app/api/run_files.py:280,353,431,905,940,1043,1155; backend/app/api/run_figma_export.py:735; backend/app/api/runs.py:2511), set sandbox.has_git = (sandbox.root / ".git").is_dir() right after construction. A small helper or classmethod such as RunSandbox.for_existing(...) in backend/app/agents/sandbox.py, used by those sites, avoids repeating it. Then add one test file that builds a sandbox over a temp dir with no .git, asserts has_git is False and commit_all returns "".

<a id="qa-kb-065"></a>

## QA-KB-065 — Unhandled mechanical kind falls through to single_shot and bills a model on an empty prompt

- **Page:** n/a (code-level)
- **Route:** n/a (code-level)
- **Severity:** Low
- **Found by:** knowledge-base sweep 2 (open card ISS-684)
- **Found at:** 2026-10-02 02:55
- **Reproduction mode:** Static — reproduce by the check below (read/grep/short script). No browser needed.

### Reproduction

1. Open backend/agents/execution_engine/engine.py:6446-6498 and read the if/elif chain over step.mechanical.
2. Note the final else at line 6498 resolves strategy_name (default single_shot) with no check on step.mechanical.
3. Compare with compiler._ALLOWED_MECHANICAL_KINDS (compiler.py:206-207). A new kind added there has no engine branch and runs as a model step.

### Expected

A step whose mechanical kind has no engine dispatch branch fails with an error naming the kind. A test fails when a registered or compiler-allowed mechanical kind lacks an engine branch.

### Actual

The step silently runs the single_shot model strategy on an empty prompt and bills tokens. No test covers engine parity.

### Notes

Logged from the existing open knowledge card [ISS-684](.knowledge/cards/20260918-ISS-684.md), which already holds the root cause.
Link that card from the ledger row and update it when this closes; do not mint a duplicate root card.
Triage fix sketch (static read of the current code, not binding on the analyzer): 1) In engine.py, change the else at line 6497-6498 to: `elif getattr(step, "mechanical", None): raise ValueError(f"mechanical kind {step.mechanical!r} has no engine dispatch branch")`, followed by `else: strategy = _registry.resolve("strategy", strategy_name)`. Make sure the raise is handled as a single pipeline failure, as the AssembleStepFailed handling is. 2) Add a test, for example in backend/tests/unit/agents/execution_engine/test_compiler.py next to line 576, that parses the engine.py source, collects the `== "<kind>"` literals from the mechanical chain, and asserts they equal compiler._ALLOWED_MECHANICAL_KINDS. Alternative: replace the chain with a dict of kind to adapter class and test the dict keys against _ALLOWED_MECHANICAL_KINDS.

<a id="qa-kb-066"></a>

## QA-KB-066 — Steps/Files clarify rounds stay on the page run's rounds after pinning a different version

- **Page:** n/a (code-level)
- **Route:** n/a (code-level)
- **Severity:** Low
- **Found by:** knowledge-base sweep 2 (open card ISS-755)
- **Found at:** 2026-10-02 02:55
- **Reproduction mode:** Static — reproduce by the check below (read/grep/short script). No browser needed.

### Reproduction

1. Read frontend/src/components/preview/PreviewPanel.tsx:1075 and :1958 (effPipelineState is version-aware).
2. Read :1922 and :1966, which use the raw pipelineState?.clarifications.
3. Pin an older version of a run whose page-level pipelineState.clarifications is non-empty: the Steps clarify card still shows the page run's rounds.

### Expected

When a version is pinned, the Steps and Files clarify rounds follow that version (its own rounds, or none).

### Actual

The raw top-level pipelineState.clarifications shadows the version-aware state, so the page run's rounds show under the pinned version.

### Notes

Logged from the existing open knowledge card [ISS-755](.knowledge/cards/20260922-1415-ISS-755.md), which already holds the root cause.
Link that card from the ledger row and update it when this closes; do not mint a duplicate root card.
Triage fix sketch (static read of the current code, not binding on the analyzer): In PreviewPanel.tsx:1922 and :1966, change `clarifications ?? pipelineState?.clarifications` to `clarifications ?? effPipelineState?.clarifications`. That yields none for a pinned version unless VersionView later carries its own clarifications. Optionally add `clarifications` to VersionView and versionViewFrom (about :573-650) and use `viewingVersion?.clarifications ?? ...`. Add a case to the PreviewPanel tests, which already exist for refSurfaces.

<a id="qa-kb-067"></a>

## QA-KB-067 — History click on a completed run runs the whole reopen twice (run, events and family fetched twice)

- **Page:** /runs/{id}
- **Route:** /runs/{id}
- **Severity:** Low
- **Found by:** knowledge-base sweep 2 (open card ISS-840)
- **Found at:** 2026-10-02 02:55
- **Reproduction mode:** Static — reproduce by the check below (read/grep/short script). No browser needed.

### Reproduction

1. Read frontend/src/app/[...view]/page.tsx:3469-3483: the effect guard compares against trackedRunIdRef.current.
2. Read frontend/src/components/layout/DashboardLayout.tsx:2836-2839: the History click calls onSelectWorkflowRun(run) and then router.push(routes.runStream(run.id)).
3. Note the push remounts page.tsx (the comment at page.tsx:3480-3488 says so), so trackedRunIdRef is null and the deep-link effect re-invokes handleSelectWorkflowRun({ id: runId }).
4. Check that a completed run is not in runConnection.liveRunIds, so the guard misses and the whole reopen runs a second time.

### Expected

One reopen per history click: one GET /api/runs/{id}, one events replay, and one family fetch per call site.

### Actual

Every history click on a completed run runs handleSelectWorkflowRun twice, so /api/runs/{id} and events are fetched 2x and /family 4x.

### Notes

Logged from the existing open knowledge card [ISS-840](.knowledge/cards/20260922-2030-ISS-840.md), which already holds the root cause.
Link that card from the ledger row and update it when this closes; do not mint a duplicate root card.
Triage fix sketch (static read of the current code, not binding on the analyzer): In page.tsx, add a module-scope `let reopenClaimRunId: string | null` next to switchGeneration (about :96-121). Set it to run.id at the top of handleSelectWorkflowRun (about :2915), where beginSwitchGeneration(run.id) is called. In the deep-link effect (about :3469), after the liveRunIds branch and before the `handleSelectWorkflowRun({ id: runId })` call at about :3552, check `if (reopenClaimRunId === runId)`. If it matches, clear it, apply the tab via runTabDeepLink.requestOpenTab as the existing early-return branch does, and return. Clear the claim on a different run's claim so a stale marker cannot suppress a later cold open. Add a source test beside page.qaSg004.test.tsx.

### Verify note (2026-10-07, validate-bugs after FIX-753)

The completion-toast path for a CACHED run is not covered by the fix. In DashboardLayout.tsx (`CompletionToast` `onViewResults`, about line 3462), the cached branch still calls `onSelectWorkflowRun(completedRun)` and then `router.push(routes.runStream(id))`, so the remounted page's T11 effect opens the run a second time. The History row and bell paths are fixed. Verify must cover the cached toast too: route it through the same no-fetch path as the bell (primeRunOpen), or show that T11 skips a run that is already selected.

<a id="qa-kb-068"></a>

## QA-KB-068 — ArtifactStore.forget_run leaves review:{run_id}:* responses in _questionnaire_responses after run end

- **Page:** n/a (code-level)
- **Route:** n/a (code-level)
- **Severity:** Low
- **Found by:** knowledge-base sweep 2 (open card ISS-868)
- **Found at:** 2026-10-02 02:55
- **Reproduction mode:** Test — reproduce by running the command below; it should fail as described. No browser needed.

### Reproduction

1. From repo root, run a python snippet: s = ArtifactStore(); asyncio.run(s.set_review_response('run-x:agent-a:0', approved=False)); s.forget_run('run-x'); print(s.get_review_response('run-x:agent-a:0'))
2. Observe the response is still returned (not None) while the event key is gone.

### Expected

After forget_run('run-x'), get_review_response('run-x:agent-a:0') returns None, and other runs' review keys survive.

### Actual

The review response stays in _questionnaire_responses until process exit.

### Notes

Logged from the existing open knowledge card [ISS-868](.knowledge/cards/20261001-2106-ISS-868.md), which already holds the root cause.
Link that card from the ledger row and update it when this closes; do not mint a duplicate root card.
Triage fix sketch (static read of the current code, not binding on the analyzer): backend/agents/artifact_store/store.py:~224 in forget_run: after the _resume_events loop, add a loop over list(self._questionnaire_responses) popping keys where k == f"review:{run_id}" or k.startswith(review_prefix). Add a unit test in backend/tests/unit/app/test_artifact_store.py: set_review_response("run-1:a:0") plus another run's key, forget_run("run-1"), assert the first is None and the other survives.

<a id="qa-kb-069"></a>

## QA-KB-069 — AgentDetailPanel.artifactVersions.test.tsx fails 10/10: @/lib/api mock lacks getCapabilities

- **Page:** n/a (code-level)
- **Route:** n/a (code-level)
- **Severity:** Low
- **Found by:** knowledge-base sweep 2 (open card ISS-895)
- **Found at:** 2026-10-02 02:55
- **Reproduction mode:** Test — reproduce by running the command below; it should fail as described. No browser needed.

### Reproduction

1. From the repo root run: cd frontend && npx vitest run src/components/results/AgentDetailPanel.artifactVersions.test.tsx
2. Observe 10 failures: No getCapabilities export is defined on the @/lib/api mock

### Expected

The 10 per-artifact version viewing tests run and pass against the current AgentDetailPanel.

### Actual

All 10 throw at AgentDetailPanel.tsx:1325 because the mock factory does not export getCapabilities.

### Notes

Logged from the existing open knowledge card [ISS-895](.knowledge/cards/20261001-2126-ISS-895.md), which already holds the root cause.
Link that card from the ledger row and update it when this closes; do not mint a duplicate root card.
Triage fix sketch (static read of the current code, not binding on the analyzer): In frontend/src/components/results/AgentDetailPanel.artifactVersions.test.tsx:16-19, add `getCapabilities: async () => ({ capabilities: [], model_catalog: [] }),` to the vi.mock("@/lib/api") factory (as AgentDetailPanel.modelChip.test.tsx:37-41 does). Then re-run the file and fix any assertions that drifted from the current panel.

<a id="qa-kb-070"></a>

## QA-KB-070 — No test pins task_loop per-task invocation_gated=False; revert would add a gate per task unnoticed

- **Page:** n/a (code-level)
- **Route:** n/a (code-level)
- **Severity:** Low
- **Found by:** knowledge-base sweep 2 (open card ISS-897)
- **Found at:** 2026-10-02 02:55
- **Reproduction mode:** Static — reproduce by the check below (read/grep/short script). No browser needed.

### Reproduction

1. Open backend/agents/capabilities/strategies/task_loop.py:364 and see invocation_gated=False.
2. Open backend/tests/unit/agents/test_strategies.py:168-188 and see _FakeRunner.run_agent never records invocation_gated.
3. Delete the kwarg at task_loop.py:364 mentally: no existing test fails.

### Expected

Removing invocation_gated=False at task_loop.py:364 makes a test fail.

### Actual

No test fails; N-task step would get N+1 gates.

### Notes

Logged from the existing open knowledge card [ISS-897](.knowledge/cards/20261001-2127-ISS-897.md), which already holds the root cause.
Link that card from the ledger row and update it when this closes; do not mint a duplicate root card.
Triage fix sketch (static read of the current code, not binding on the analyzer): In backend/tests/unit/agents/test_strategies.py:~183 add "invocation_gated": invocation_gated to the dict appended to self.run_agent_calls; then add a task_loop test (in test_strategies.py or test_task_loop_declared_gate_iss132.py) that runs a multi-task step and asserts all(c["invocation_gated"] is False for c in runner.run_agent_calls). Optional pairing guard is not needed.

<a id="qa-kb-071"></a>

## QA-KB-071 — ISS-126 source-lock test fails 5 of 9: stale anchors after ISS-304 added tokenUsage args

- **Page:** n/a (code-level)
- **Route:** n/a (code-level)
- **Severity:** Low
- **Found by:** knowledge-base sweep 2 (open card ISS-898)
- **Found at:** 2026-10-02 02:55
- **Reproduction mode:** Test — reproduce by running the command below; it should fail as described. No browser needed.

### Reproduction

1. cd frontend
2. ./node_modules/.bin/vitest --run 'src/app/[...view]/terminalReopenReconcile.source.test.ts'
3. Observe 5 failed | 4 passed in the ISS-126 source-lock block

### Expected

All 9 cases in the ISS-126 source-lock block pass, since the reopen reconciliation behaviour still holds.

### Actual

5 cases fail because the test greps for 'applyTerminalStatus(prev, fullRun.status)' and 'reconcileTerminalStatus(fullRun.status);', which no longer appear in page.tsx.

### Notes

Logged from the existing open knowledge card [ISS-898](.knowledge/cards/20261001-2128-ISS-898.md), which already holds the root cause.
Link that card from the ledger row and update it when this closes; do not mint a duplicate root card.
Triage fix sketch (static read of the current code, not binding on the analyzer): In frontend/src/app/[...view]/terminalReopenReconcile.source.test.ts, replace the anchors with prefixes that survive extra args: lines 38, 60, 70, 77, 85 use "applyTerminalStatus(prev, fullRun.status" (no closing paren), and line 48 uses "reconcileTerminalStatus(fullRun.status". Card's scratch experiment showed 9/9 pass. Do not touch page.tsx.

<a id="qa-kb-072"></a>

## QA-KB-072 — test_non_redoable_declared_gate_unaffected_by_redo_action times out at 60 s: it never approves after its refused redo

- **Page:** n/a (code-level)
- **Route:** n/a (code-level)
- **Severity:** Low
- **Found by:** knowledge-base sweep 2 (open card ISS-899)
- **Found at:** 2026-10-02 02:55
- **Reproduction mode:** Test — reproduce by running the command below; it should fail as described. No browser needed.

### Reproduction

1. cd backend
2. ./.venv/bin/python -m pytest tests/agents/test_declared_gate_redo.py -q
3. Observe test_non_redoable_declared_gate_unaffected_by_redo_action fails after about 60 s with CancelledError at the await event.wait() in _run_review_gate

### Expected

The test posts a redo, sees it refused, approves the gate, and the drive ends with one agent_start and one review_gate_ready.

### Actual

The refused redo leaves the gate open. Nothing approves it, so _drive hits _EVENT_TIMEOUT_S (60 s) and the test fails.

### Notes

Logged from the existing open knowledge card [ISS-899](.knowledge/cards/20261001-2129-ISS-899.md), which already holds the root cause.
Link that card from the ledger row and update it when this closes; do not mint a duplicate root card.
Triage fix sketch (static read of the current code, not binding on the analyzer): In backend/tests/agents/test_declared_gate_redo.py, edit _on_ready (about lines 205-211). After set_review_response(..., action="redo", ...), poll store.review_event_pending(gate_key) until the gate is re-armed, using the _wait_until pattern from test_redoable_eligibility_fence.py:129-135. Then call set_review_response(gate_key, approved=True). Keep the existing assertions: agent_start count is 1 and readies has length 1. A second review_gate_ready is not emitted, since the refused redo does not re-emit the ready event.

<a id="qa-kb-073"></a>

## QA-KB-073 — test_driver_happy_path_persists_output_columns red: stub agent_chunk/agent_complete lack agent_id

- **Page:** n/a (code-level)
- **Route:** n/a (code-level)
- **Severity:** Low
- **Found by:** knowledge-base sweep 2 (open card ISS-900)
- **Found at:** 2026-10-02 02:55
- **Reproduction mode:** Test — reproduce by running the command below; it should fail as described. No browser needed.

### Reproduction

1. From repo root run: backend/.venv/bin/python -m pytest backend/tests/integration/api/test_rest_revisions_api.py -k test_driver_happy_path_persists_output_columns
2. It fails at test_rest_revisions_api.py:412 with TypeError from json.loads(None) because row.agent_outputs is NULL.

### Expected

agent_outputs holds one row with agent_id user-stories-revision-agent, as the test asserts.

### Actual

agent_outputs is NULL because the stub's agent_chunk and agent_complete events have no agent_id, so the collector never appends the row.

### Notes

Logged from the existing open knowledge card [ISS-900](.knowledge/cards/20261001-2132-ISS-900.md), which already holds the root cause.
Link that card from the ledger row and update it when this closes; do not mint a duplicate root card.
Triage fix sketch (static read of the current code, not binding on the analyzer): In backend/tests/integration/api/test_rest_revisions_api.py add "agent_id": "user-stories-revision-agent" to the data dict of the agent_chunk event (line 373) and the agent_complete event (lines 376-383) in _rich, matching what the real engine emits. No change to run_commands.py.

<a id="qa-kb-074"></a>

## QA-KB-074 — Three docstrings still say append_event_next_seq reads the whole run log (removed by FIX-688)

- **Page:** n/a (code-level)
- **Route:** n/a (code-level)
- **Severity:** Low
- **Found by:** knowledge-base sweep 2 (open card ISS-901)
- **Found at:** 2026-10-02 02:55
- **Reproduction mode:** Static — reproduce by the check below (read/grep/short script). No browser needed.

### Reproduction

1. From the repo root run: grep -n -A2 'append_event_next_seq' backend/agents/authz.py | sed -n 1,12p
2. Read backend/agents/authz.py:592-599 (_max_event_seq docstring)
3. Read backend/agents/execution_engine/engine.py:13058-13066 (_stamp_resume_marker docstring)

### Expected

Docstrings describe append_event_next_seq's current cost: one keyed event_id lookup plus one _max_event_seq probe per attempt, and no read_events call.

### Actual

Three docstrings still claim append_event_next_seq re-reads every row of the run log, a cost FIX-688 removed. A reader could re-file that cost.

### Notes

Logged from the existing open knowledge card [ISS-901](.knowledge/cards/20261001-2140-ISS-901.md), which already holds the root cause.
Link that card from the ledger row and update it when this closes; do not mint a duplicate root card.
Triage fix sketch (static read of the current code, not binding on the analyzer): Prose-only rewrites. (1) authz.py:476-478, read_events_of_types: remove "and this class's own append_event_next_seq seq allocation" from the list of read_events callers. (2) authz.py:595-598, _max_event_seq: replace the "and is why the engine sink cannot allocate through append_event_next_seq" clause with the current reason (it would add two index probes per event against the sink's in-memory counter), or drop it. (3) engine.py:13061-13064, _stamp_resume_marker: drop the "re-reads EVERY row ... 36k-row run" cost claim and keep the reason that the marker mints a fresh event_id and never needs the idempotent no-op. No test needed.

<a id="qa-kb-075"></a>

## QA-KB-075 — Test comments explain degraded verdict with dead latest-completion-wins rule (test_restart_resume_db.py)

- **Page:** n/a (code-level)
- **Route:** n/a (code-level)
- **Severity:** Low
- **Found by:** knowledge-base sweep 2 (open card ISS-902)
- **Found at:** 2026-10-02 02:55
- **Reproduction mode:** Static — reproduce by the check below (read/grep/short script). No browser needed.

### Reproduction

1. From the repo root run: sed -n '4318,4319p;4334,4335p;4377p' backend/tests/integration/agents/test_restart_resume_db.py
2. The output shows the LATEST pipeline_complete wording, the latest-wins wording, and the ..._latest_completion_only name.

### Expected

Comments describe the live FIX-484 rule: a degraded pipeline_complete at or after the last run_resuming / pipeline_start decides the verdict.

### Actual

Comments say the latest pipeline_complete by seq decides (latest-wins), which is the rule ISS-689 deleted from _reconcile_terminal_status. A reader who trusts them is misled.

### Notes

Logged from the existing open knowledge card [ISS-902](.knowledge/cards/20261001-2144-ISS-902.md), which already holds the root cause.
Link that card from the ledger row and update it when this closes; do not mint a duplicate root card.
Triage fix sketch (static read of the current code, not binding on the analyzer): Edit backend/tests/integration/agents/test_restart_resume_db.py only. At lines 4318-4319, replace "The LATEST pipeline_complete must decide, not 'was ANY completion ever degraded'" with "Only a degraded pipeline_complete at or after the last attempt boundary (run_resuming / pipeline_start, FIX-484) counts, not 'was ANY completion ever degraded'". At lines 4334-4335, replace the latest-wins wording with "a clean completion, then a LATER degraded one in the last attempt: the boundary scan reads degraded too". Keep the test name unchanged, because renaming breaks -k selections and the pytest ids quoted in 5 cards. No behaviour change.

<a id="qa-kb-076"></a>

## QA-KB-076 — Citation guard misses bare/spaced/other-module line cites; test_shutdown_reachability.py keeps stale cites

- **Page:** n/a (code-level)
- **Route:** n/a (code-level)
- **Severity:** Low
- **Found by:** knowledge-base sweep 2 (open card ISS-903)
- **Found at:** 2026-10-02 02:55
- **Reproduction mode:** Static — reproduce by the check below (read/grep/short script). No browser needed.

### Reproduction

1. From the repo root, run: grep -nE 'main.py:238|pool_leak.py:196' backend/tests/unit/services/test_shutdown_reachability.py (hits at lines 23, 67, 84).
2. Read backend/tests/unit/test_run_shutdown_stale_citations.py:25-28 and see that bare ':1734' or 'run_engine.py :399' style cites do not match _LINE_CITE.

### Expected

The guard fails on any file-line cite (name.ext:N, name.ext :N, or bare :NNN) in the scanned files, and test_shutdown_reachability.py has no stale cites.

### Actual

The guard only matches ten named modules followed by .py or .yml and a colon with no space. test_shutdown_reachability.py still cites main.py:238 (twice) and test_run_stream_pool_leak.py:196-238, names its own path wrongly, and carries a duplicated banner block.

### Notes

Logged from the existing open knowledge card [ISS-903](.knowledge/cards/20261001-2145-ISS-903.md), which already holds the root cause.
Link that card from the ledger row and update it when this closes; do not mint a duplicate root card.
Triage fix sketch (static read of the current code, not binding on the analyzer): 1) backend/tests/unit/test_run_shutdown_stale_citations.py:25-28: widen _LINE_CITE to r"[\w./-]+\.(?:py|yml|sh) ?:\d+|(?<![\w/.]):\d{3,}"; run that one file and convert any pre-existing hits in the scanned files to symbol names. 2) backend/tests/unit/services/test_shutdown_reachability.py: line 1 change the self-path to tests/unit/services/; line 23 name the in-process uvicorn.Server( test in test_run_stream_pool_leak.py instead of 196-238; lines 67 and 84 replace main.py:238 with "restore_non_terminal_runs() in app.main lifespan"; delete the first copy of the duplicated "1. Reachability" block (lines 64-~79). Comments only.

<a id="qa-kb-077"></a>

## QA-KB-077 — Stale test_iss401_reset_password_message.py errors at setup; it tests the deleted local break-glass account

- **Page:** n/a (code-level)
- **Route:** n/a (code-level)
- **Severity:** Low
- **Found by:** knowledge-base sweep 2 (open card ISS-904)
- **Found at:** 2026-10-02 02:55
- **Reproduction mode:** Test — reproduce by running the command below; it should fail as described. No browser needed.

### Reproduction

1. From backend/: .venv/bin/python -m pytest tests/unit/test_iss401_reset_password_message.py -q
2. Observe 1 error (UnitIsolationError from tests/unit/conftest.py:91).

### Expected

Every test file in tests/unit collects and runs, and each test covers behaviour that still exists.

### Actual

The file errors at setup. Past that guard it would fail on the removed auth_provider and password_hash kwargs, and it targets a 409 branch that was deleted in migration 0038.

### Notes

Logged from the existing open knowledge card [ISS-904](.knowledge/cards/20261001-2149-ISS-904.md), which already holds the root cause.
Link that card from the ledger row and update it when this closes; do not mint a duplicate root card.
Triage fix sketch (static read of the current code, not binding on the analyzer): Delete backend/tests/unit/test_iss401_reset_password_message.py, since the local-account 409 it guards has no subject left. Then mark ISS-904 resolved. If any part of ISS-401 is still wanted for the Cognito reset path, write a new test against cognito_admin.reset_password via backend/app/api/admin.py:502-530 instead of reviving this one.

<a id="qa-kb-078"></a>

## QA-KB-078 — app_builder characterization goldens still expect .family.lock block; both contract tests fail

- **Page:** n/a (code-level)
- **Route:** n/a (code-level)
- **Severity:** Low
- **Found by:** knowledge-base sweep 2 (open card ISS-906)
- **Found at:** 2026-10-02 02:55
- **Reproduction mode:** Test — reproduce by running the command below; it should fail as described. No browser needed.

### Reproduction

1. From the repo root run: cd backend && python -m pytest tests/contract/agents/test_characterization_app_builder.py
2. Observe 2 failures: deliverable byte snapshot (len now=88, golden=120) and event snapshot (diff at pipeline_complete final_output).

### Expected

Both app_builder SAFE-01 and SAFE-02 characterization tests pass, with goldens matching the deliverable without .family.lock.

### Actual

Goldens still start with a ".family.lock" file block that sandbox.py:68 excludes, so both tests fail.

### Notes

Logged from the existing open knowledge card [ISS-906](.knowledge/cards/20261001-2200-ISS-906.md), which already holds the root cause.
Link that card from the ledger row and update it when this closes; do not mint a duplicate root card.
Triage fix sketch (static read of the current code, not binding on the analyzer): Regenerate the goldens with SNAPSHOT_UPDATE=1 on backend/tests/contract/agents/test_characterization_app_builder.py. Confirm the only diff is the dropped .family.lock block in backend/tests/agents/characterization/golden/app_builder.txt (line 1 and its blank line), app_builder.events.json and app_builder.wsframes.json. Do not touch sandbox.py.

<a id="qa-kb-079"></a>

## QA-KB-079 — Payload-seq test does not guard copy-not-mutate, 2-hop re-stamp or exhaustion

- **Page:** n/a (code-level)
- **Route:** n/a (code-level)
- **Severity:** Low
- **Found by:** knowledge-base sweep 2 (open card ISS-907)
- **Found at:** 2026-10-02 02:55
- **Reproduction mode:** Test — reproduce by running the command below; it should fail as described. No browser needed.

### Reproduction

1. Swap in an in-place payload_json["seq"] = attempt_seq in backend/agents/authz.py append_event_at_or_after (scratch mutant).
2. From backend/ run: python -m pytest tests/integration/repositories/test_run_events_payload_seq_db.py
3. Both tests still pass even though the caller's dict now carries the landed seq.

### Expected

The test file fails when the caller's dict is mutated, when only the first hop re-stamps, or when exhaustion alters the caller's dict.

### Actual

Both existing tests pass under an in-place mutation and under a first-hop-only copy.

### Notes

Logged from the existing open knowledge card [ISS-907](.knowledge/cards/20261001-2200-ISS-907.md), which already holds the root cause.
Link that card from the ledger row and update it when this closes; do not mint a duplicate root card.
Triage fix sketch (static read of the current code, not binding on the analyzer): Add three tests to backend/tests/integration/repositories/test_run_events_payload_seq_db.py, using the scratch checks in evidence/qa-kb-007/05-fix-tests-and-constraint-checks.txt as a template. (1) Keep a reference to the dict passed in, retry once, and assert it still reads its original seq. (2) 2-hop case: pre-seed rows, monkeypatch the first _max_event_seq to return a stale tail, assert landed seq 4 and stored payload seq 4. (3) Exhaustion case: _max_attempts=1 into a collision, assert IntegrityError, no row stored, caller's dict unchanged. No source change.

<a id="qa-kb-080"></a>

## QA-KB-080 — ISS-098 Stop-mid-wave test dies on TypeError: fake run_fanout rejects event_queue kwarg

- **Page:** n/a (code-level)
- **Route:** n/a (code-level)
- **Severity:** Low
- **Found by:** knowledge-base sweep 2 (open card ISS-908)
- **Found at:** 2026-10-02 02:55
- **Reproduction mode:** Test — reproduce by running the command below; it should fail as described. No browser needed.

### Reproduction

1. cd backend
2. .venv/bin/python -m pytest tests/agents/test_wave_scheduler_cancel_row.py -q -p no:cacheprovider

### Expected

test_cancelled_error_mid_wave_marks_row_terminal reaches the injected CancelledError and asserts the wave_runs row is flipped terminal.

### Actual

TypeError: _CancelMidWaveRunner.run_fanout() got an unexpected keyword argument 'event_queue' at _fanout_wave_stream.py:71, so the ISS-098 guard exercises nothing.

### Notes

Logged from the existing open knowledge card [ISS-908](.knowledge/cards/20261001-2204-ISS-908.md), which already holds the root cause.
Link that card from the ledger row and update it when this closes; do not mint a duplicate root card.
Triage fix sketch (static read of the current code, not binding on the analyzer): backend/tests/agents/test_wave_scheduler_cancel_row.py:40 change signature to `async def run_fanout(self, requests, ctx, *, step=None, event_queue=None):`. Test-only; then run the file to confirm the CancelledError path asserts.

<a id="qa-kb-081"></a>

## QA-KB-081 — LaunchWizard DS step is an endless skeleton when the design-system registry fails or is empty

- **Page:** /create/prototype
- **Route:** /create/prototype
- **Severity:** Low
- **Found by:** knowledge-base sweep 2 (open card ISS-909)
- **Found at:** 2026-10-02 02:55
- **Reproduction mode:** Test — reproduce by running the command below; it should fail as described. No browser needed.

### Reproduction

1. In frontend/src/components/workflow/LaunchWizard.test.tsx add a case that mocks listDesignSystems with mockRejectedValue(new Error('500')), and a second with mockResolvedValue([]).
2. Render with initialMode='prototype' and open the Design System step.
3. Assert an error or empty message is shown and no animate-pulse placeholder is present (it fails today).
4. Run from the repo root: cd frontend && npx vitest run src/components/workflow/LaunchWizard.test.tsx

### Expected

A failed or empty registry fetch shows an explicit error (with a retry) in the DS step, distinguishable from loading.

### Actual

The .catch at LaunchWizard.tsx:685 is silent, and an empty list renders a permanent animate-pulse skeleton (:1329-1330). Continue stays disabled with only the "Pick a design system" pill.

### Notes

Logged from the existing open knowledge card [ISS-909](.knowledge/cards/20261001-2216-ISS-909.md), which already holds the root cause.
Link that card from the ledger row and update it when this closes; do not mint a duplicate root card.
Triage fix sketch (static read of the current code, not binding on the analyzer): In frontend/src/components/workflow/LaunchWizard.tsx, add `systemsLoaded` and `systemsError` state next to `systems` (:245). In the effect (:670-685), set systemsLoaded=true in .then, and in .catch set systemsError=err.message and systemsLoaded=true. In the dsSlot (:1328-1330), render the skeleton only while !systemsLoaded. If systemsError, or the list is empty after loading, render a StepNote or error with a Retry button that re-runs the fetch (extract the fetch into a callback). Mirror the web-template pattern (:635, :1290) and composer/DesignPickerModal.tsx:117-120.

<a id="qa-kb-082"></a>

## QA-KB-082 — Wrong-shape __app_preview__ payload crashes preview-fullscreen at render instead of falling back

- **Page:** /preview-fullscreen
- **Route:** /preview-fullscreen
- **Severity:** Low
- **Found by:** knowledge-base sweep 2 (open card ISS-915)
- **Found at:** 2026-10-02 02:55
- **Reproduction mode:** Browser — reproduce from the URL below.

### Reproduction

1. Open the web app URL and sign in as admin@velocity.ai.
2. In devtools console run: sessionStorage.setItem('__app_preview__', JSON.stringify({files:'abc',projectName:'x'}))
3. Navigate to /preview-fullscreen.
4. Repeat with {files:[null]} and {files:[{}]}.

### Expected

Any payload that is not a non-empty array of objects with a string path takes the giveUp() exit (redirect to run history).

### Actual

AppBuilderPreview.buildTree throws a TypeError during render; the page try/catch does not catch it, so the app error boundary (error.tsx) is shown.

### Notes

Logged from the existing open knowledge card [ISS-915](.knowledge/cards/20261001-2219-ISS-915.md), which already holds the root cause.
Link that card from the ledger row and update it when this closes; do not mint a duplicate root card.
Triage fix sketch (static read of the current code, not binding on the analyzer): In frontend/src/app/preview-fullscreen/page.tsx:71 replace `!data.files?.length` with `!Array.isArray(data.files) || !data.files.length || !data.files.every(f => typeof f?.path === "string")` so giveUp() stays the single exit.

<a id="qa-kb-083"></a>

## QA-KB-083 — Settings model gate reads advisory users.tier instead of effective_tier(user, principal)

- **Page:** /api/settings/preferences
- **Route:** /api/settings/preferences
- **Severity:** Low
- **Found by:** knowledge-base sweep 2 (open card ISS-937)
- **Found at:** 2026-10-02 02:55
- **Reproduction mode:** Test — reproduce by running the command below; it should fail as described. No browser needed.

### Reproduction

1. Add a unit test in tests/integration/e2e/suites/09_settings/test_settings.py (or a small new unit test file).
2. Override get_current_principal with a principal whose cognito:groups say basic, and use a fake user whose tier column says pro.
3. PUT /api/settings/preferences with a premium model id.
4. Run: python -m pytest tests/integration/e2e/suites/09_settings/test_settings.py (using ./venv/bin/python).

### Expected

Premium model is refused (403) and GET marks it allowed=false, since the effective tier comes from the token groups (basic).

### Actual

The premium model is allowed, because the gate reads the user.tier column (pro). In the ordinary case _sync_role_projection keeps the column equal to the effective tier; the gap is a stale-but-valid token after a group change made outside the admin API.

### Notes

Logged from the existing open knowledge card [ISS-937](.knowledge/cards/20261001-2231-ISS-937.md), which already holds the root cause.
Link that card from the ledger row and update it when this closes; do not mint a duplicate root card.
Triage fix sketch (static read of the current code, not binding on the analyzer): In backend/app/api/settings.py, import get_current_principal from app.core.dependencies and effective_tier from app.core.identity. On get_preferences (:332) and update_preferences (:353), add principal = Depends(get_current_principal) while keeping user. Replace user.tier with effective_tier(user, principal) at :341, :374 and :388. Add the unit test described in the card.

<a id="qa-kb-084"></a>

## QA-KB-084 — /runs/{id}/versions parses to run-version with no version; pinned stream/preview-full drop the pin

- **Page:** /runs/{id}/versions
- **Route:** /runs/{id}/versions
- **Severity:** Low
- **Found by:** knowledge-base sweep 2 (open card ISS-941)
- **Found at:** 2026-10-02 02:55
- **Reproduction mode:** Static — reproduce by the check below (read/grep/short script). No browser needed.

### Reproduction

1. Read frontend/src/lib/routes.ts lines 374-380: `segments.length <= 4` lets ['runs','r1','versions'] through with segments[3] undefined.
2. Read lines 421-428: the run-stream and run-preview-full arms return without `version`, so ['runs','r1','versions','2','stream'] returns run-stream without the pin.

### Expected

/runs/{id}/versions parses to unknown. /runs/{id}/versions/{v}/stream and /runs/{id}/versions/{v}/preview/full also parse to unknown, since no builder emits them. The URL then agrees with the content rendered.

### Actual

The bare /versions path returns run-version with version undefined, which violates the required `version: string` in ParsedView. The pinned stream and full-preview paths silently render the un-pinned screens under a pinned URL.

### Notes

Logged from the existing open knowledge card [ISS-941](.knowledge/cards/20261001-2240-ISS-941.md), which already holds the root cause.
Link that card from the ledger row and update it when this closes; do not mint a duplicate root card.
Triage fix sketch (static read of the current code, not binding on the analyzer): In frontend/src/lib/routes.ts, change line 376 to `if (segments.length === 4) return { screen: 'run-version', runId, version: segments[3] };`. Add `if (segments.length === 3) return { screen: 'unknown' };` before it. In the stream arm (~:421) and the preview/full arm (~:426), add `&& version === undefined` to the conditions so pinned forms fall through to unknown. Optionally add the three cases to the existing routes unit test.

<a id="qa-kb-085"></a>

## QA-KB-085 — runTabShallowNav test fails: slice end anchor stale after pinnedVersion dep added to tab handler

- **Page:** n/a (code-level)
- **Route:** n/a (code-level)
- **Severity:** Low
- **Found by:** knowledge-base sweep 2 (open card ISS-942)
- **Found at:** 2026-10-02 02:55
- **Reproduction mode:** Test — reproduce by running the command below; it should fail as described. No browser needed.

### Reproduction

1. From frontend/ run: npx vitest --run 'src/app/[...view]/runTabShallowNav.test.ts'
2. Observe 1 failed | 2 passed: the 'tab handler pushes history directly' case fails with expected body not to contain 'router.push'

### Expected

All 3 cases pass. The tab handler slice contains window.history.pushState and no router.push.

### Actual

1 of 3 cases fails. The slice runs from :516 to :737 and includes handleOpenLiveRun's router.push at :561.

### Notes

Logged from the existing open knowledge card [ISS-942](.knowledge/cards/20261001-2241-ISS-942.md), which already holds the root cause.
Link that card from the ledger row and update it when this closes; do not mint a duplicate root card.
Triage fix sketch (static read of the current code, not binding on the analyzer): In frontend/src/app/[...view]/runTabShallowNav.test.ts:28, change the end anchor to the handler's own closing. Use indexOf("\n  }, [", start), or the literal "}, [contentSourceRunId, pinnedVersion]);". The first option survives future dependency changes. Do not touch DashboardLayout.tsx.

<a id="qa-kb-086"></a>

## QA-KB-086 — IdeaInputPage designPicker test fails: asserts extraParams undefined but gate_agent_ids: [] is always sent

- **Page:** n/a (code-level)
- **Route:** n/a (code-level)
- **Severity:** Low
- **Found by:** knowledge-base sweep 2 (open card ISS-944)
- **Found at:** 2026-10-02 02:55
- **Reproduction mode:** Test — reproduce by running the command below; it should fail as described. No browser needed.

### Reproduction

1. From the repo root: cd frontend && npx vitest run src/components/workflow/IdeaInputPage.designPicker.test.tsx
2. Observe the test 'does not offer the picker for a workflow that never declares opendesign' fails at :159 with AssertionError: expected { gate_agent_ids: [] } to be undefined

### Expected

The test passes, since it checks that no template_id or design_system_id is sent when the workflow never declares opendesign.

### Actual

The test fails because extraParams is { gate_agent_ids: [] }, which the app has sent by design since 602296cc8.

### Notes

Logged from the existing open knowledge card [ISS-944](.knowledge/cards/20261002-0040-ISS-944.md), which already holds the root cause.
Link that card from the ledger row and update it when this closes; do not mint a duplicate root card.
Triage fix sketch (static read of the current code, not binding on the analyzer): In frontend/src/components/workflow/IdeaInputPage.designPicker.test.tsx:159, replace expect(extraParams).toBeUndefined() with expect(extraParams ?? {}).not.toHaveProperty("template_id") and expect(extraParams ?? {}).not.toHaveProperty("design_system_id"). Optionally also update the stale comment at IdeaInputPage.tsx:1034-1038 ("Untouched => we omit gate_agent_ids"). Do not change the app default.

<a id="qa-kb-087"></a>

## QA-KB-087 — ISS-921 Constitution dirty-state test times out waiting on fetch that the mocked load never calls

- **Page:** n/a (code-level)
- **Route:** n/a (code-level)
- **Severity:** Low
- **Found by:** knowledge-base sweep 2 (open card ISS-945)
- **Found at:** 2026-10-02 02:55
- **Reproduction mode:** Test — reproduce by running the command below; it should fail as described. No browser needed.

### Reproduction

1. From the repo root run: cd frontend && npx vitest run src/components/settings/AccountSettings.iss372.test.tsx
2. Temporarily remove the it.fails marker on the ISS-921 case (line 80). It fails at line 83 with AssertionError: expected vi.fn() to be called at least once, after about 1.3s.

### Expected

The case reaches its two real assertions and passes once ISS-921 is fixed in the app, which FIX-704 is said to do.

### Actual

The case always throws at line 83, whatever the app does. Under it.fails it reads "expected fail" even though the app is fixed, so it can never show the XPASS that marks ISS-921 fixed.

### Notes

Logged from the existing open knowledge card [ISS-945](.knowledge/cards/20261002-0053-ISS-945.md), which already holds the root cause.
Link that card from the ledger row and update it when this closes; do not mint a duplicate root card.
Triage fix sketch (static read of the current code, not binding on the analyzer): In frontend/src/components/settings/AccountSettings.iss372.test.tsx, delete line 83 (the waitFor on fetch); the findByRole("textbox") at line 82 already waits for the load. Then change it.fails( at line 80 to it(, since FIX-704 makes the case pass. Confirm by running that file once.

<a id="qa-kb-088"></a>

## QA-KB-088 — Spec-016 override round-trip tests error at setup (UnitIsolationError) and would 401 on principal auth

- **Page:** n/a (code-level)
- **Route:** n/a (code-level)
- **Severity:** Low
- **Found by:** knowledge-base sweep 2 (open card ISS-947)
- **Found at:** 2026-10-02 02:55
- **Reproduction mode:** Test — reproduce by running the command below; it should fail as described. No browser needed.

### Reproduction

1. From the repo root run: cd backend && DATABASE_URL=sqlite:///:memory: .venv/bin/python -m pytest tests/unit/test_workflow_override_e2e.py
2. Observe 7 errors at fixture setup: UnitIsolationError raised from tests/unit/conftest.py:81

### Expected

The 7 override round-trip tests run and pass (save an override of ppt, read it back, toggle it off via PATCH).

### Actual

All 7 tests error at setup because the unit guard refuses the fixture's SQLite engine. Once past that, create and PATCH would return 401 because get_current_principal is not overridden.

### Notes

Logged from the existing open knowledge card [ISS-947](.knowledge/cards/20261002-0107-ISS-947.md), which already holds the root cause.
Link that card from the ledger row and update it when this closes; do not mint a duplicate root card.
Triage fix sketch (static read of the current code, not binding on the analyzer): Move backend/tests/unit/test_workflow_override_e2e.py to backend/tests/integration/api/test_workflow_override_e2e.py. In the api fixture (around line 43), also set app.dependency_overrides[get_current_principal] = lambda: (state["user"], principal_for(state["user"])), copying the pattern in tests/integration/api/test_user_workflows_api.py:81-104. Change only the test harness.

<a id="qa-kb-089"></a>

## QA-KB-089 — Route contract test fails: public share route GET /s/{token} missing from allow-list

- **Page:** n/a (code-level)
- **Route:** n/a (code-level)
- **Severity:** Low
- **Found by:** knowledge-base sweep 2 (open card ISS-948)
- **Found at:** 2026-10-02 02:55
- **Reproduction mode:** Test — reproduce by running the command below; it should fail as described. No browser needed.

### Reproduction

1. From backend/: python -m pytest tests/security/test_route_contract.py::test_all_routes_are_protected_or_allowlisted

### Expected

Test passes; the intentionally public share route is allow-listed with a reason.

### Actual

AssertionError: endpoints with no authentication dependency and not allow-listed: GET /s/{token}

### Notes

Logged from the existing open knowledge card [ISS-948](.knowledge/cards/20261002-0107-ISS-948.md), which already holds the root cause.
Link that card from the ledger row and update it when this closes; do not mint a duplicate root card.
Triage fix sketch (static read of the current code, not binding on the analyzer): Add one line to backend/tests/security/public_routes_allowlist.txt (new section after the auth entry points): "GET /s/{token}  # ADR-0035 share link: the opaque 30-day token is the credential; serves the deliverable only, 404 on a missing or expired token".

<a id="qa-kb-090"></a>

## QA-KB-090 — resume_run logs "step offset 1/1" and "all steps complete" for a manifest-less 3-step prototype_v2_revision resume

- **Page:** n/a (code-level)
- **Route:** n/a (code-level)
- **Severity:** Low
- **Found by:** knowledge-base sweep 2 (open card ISS-950)
- **Found at:** 2026-10-02 02:55
- **Reproduction mode:** Test — reproduce by running the command below; it should fail as described. No browser needed.

### Reproduction

1. Add a test under backend/tests/agents/ using the _patch_db pattern from backend/tests/agents/test_phase3_wip_commit.py:255. It drives resume_run for a workflow_runs row of type prototype_v2_revision with no manifest_json.
2. Seed a durable state that yields resume offset 1, and stop the drive right after the offset log.
3. From the repo root run: cd backend && ./venv/bin/python -m pytest tests/agents/<new_test_file>.py
4. Inspect the caplog records for the 'resuming pipeline=... at step offset' line.

### Expected

The log reads "at step offset 1/3" (plan step count) and no "all steps complete" record is emitted while steps remain.

### Actual

The log reads "at step offset 1/1" (or 2/1) and "all steps complete — nothing to re-drive" is logged, because len(agents) is the registry roster of 1. Only the log is wrong; execution is unaffected.

### Notes

Logged from the existing open knowledge card [ISS-950](.knowledge/cards/20261002-0134-ISS-950.md), which already holds the root cause.
Link that card from the ledger row and update it when this closes; do not mint a duplicate root card.
Triage fix sketch (static read of the current code, not binding on the analyzer): In backend/agents/execution_engine/engine.py around :15677, after the `if not agents` fallback, also complete a partial roster from the plan when len(agents) < len(compiled.steps), using the same length rule as launch_run (never a workflow name, INV-1). Compile via compile_for_run(pipeline_type) in try/except so a failure keeps the existing roster. Then the :15718-15730 log and the all-complete test use the plan length. Add the caplog test from the repro steps.

<a id="qa-kb-091"></a>

## QA-KB-091 — Empty pinned version under a cancelled/failed/diverted shell run shows the shell's copy or loses Preview tab

- **Page:** /runs/{member}/versions/{n}
- **Route:** /runs/{member}/versions/{n}
- **Severity:** Low
- **Found by:** knowledge-base sweep 2 (open card ISS-952)
- **Found at:** 2026-10-02 02:55
- **Reproduction mode:** Test — reproduce by running the command below; it should fail as described. No browser needed.

### Reproduction

1. Add a case to frontend/src/components/preview/PreviewPanel.olderVersionNullOutput.test.tsx: pin a completed version with output null via the pinnedVersion prop and pass reopenedRunStatus cancelled, then failed, then diverted on the shell.
2. From frontend/: npx vitest run src/components/preview/PreviewPanel.olderVersionNullOutput.test.tsx
3. Observe: cancelled shell shows 'This run was cancelled'; failed shell drops the Preview tab and defaults to Audit; diverted shell shows 'did not complete successfully'.

### Expected

A pinned empty version shows its own status copy (No deliverable was saved for this version for a completed pin; cancelled/failed copy for a pin that ended badly) and keeps the Preview tab, whatever the shell run's status.

### Actual

The shell run's status wins: cancelled copy, diverted copy, or no Preview tab for a pinned completed version.

### Notes

Logged from the existing open knowledge card [ISS-952](.knowledge/cards/20261002-0147-ISS-952.md), which already holds the root cause.
Link that card from the ledger row and update it when this closes; do not mint a duplicate root card.
Triage fix sketch (static read of the current code, not binding on the analyzer): In frontend/src/components/preview/PreviewPanel.tsx add `!overrideActive &&` to showFailureAffordance (:1142) and showDivertedAffordance (:1154); terminalFailureNoDeliverable (:1164) and showCancelledAffordance (:1167) follow from showFailureAffordance. Also review headerFailed (:1215) and the FilesTab runStatus prop (:1922) so the header does not show failed for a pinned completed version. The existing pinned branch at :1835 then supplies the copy. Add tests for cancelled/failed/diverted shells with a pinned completed null-output version, plus an unpinned control.

<a id="qa-kb-092"></a>

## QA-KB-092 — WorkflowHistory.test.tsx asserts the removed run-actions Chain menu item, one red test per run

- **Page:** n/a (code-level)
- **Route:** n/a (code-level)
- **Severity:** Low
- **Found by:** knowledge-base sweep 2 (open card ISS-953)
- **Found at:** 2026-10-02 02:55
- **Reproduction mode:** Test — reproduce by running the command below; it should fail as described. No browser needed.

### Reproduction

1. From the repo root: cd frontend && npx vitest run src/components/history/WorkflowHistory.test.tsx
2. Observe 1 failed | 16 passed: the Chain menu action case fails with Unable to find role=menuitem and name /chain/i

### Expected

The file passes 17 of 17, and the test describes the post-FIX-584 contract: the run-actions menu offers only Delete.

### Actual

The test opens Run actions and expects a Chain menuitem that no longer exists, so it fails.

### Notes

Logged from the existing open knowledge card [ISS-953](.knowledge/cards/20261002-0154-ISS-953.md), which already holds the root cause.
Link that card from the ledger row and update it when this closes; do not mint a duplicate root card.
Triage fix sketch (static read of the current code, not binding on the analyzer): Test-only change in frontend/src/components/history/WorkflowHistory.test.tsx, case at :371-392. Rewrite it to open "Run actions" and assert queryByRole("menuitem", { name: /chain/i }) is absent and that Delete is the only menuitem. Drop the onChainPipeline and suggested-next-steps assertions, since other cases cover the chain panel via renderAndOpenRun. Update the stale comment at ~:345-352 to say FIX-584 removed the Chain item. No app change.

<a id="qa-kb-093"></a>

## QA-KB-093 — Live run header undercounts tokens on runs where an agent runs more than once

- **Page:** Run detail — live stream header
- **Route:** /runs/{id}/stream
- **Severity:** High
- **Found by:** validate-bugs smoke test (another session)
- **Found at:** 2026-10-02 03:00
- **Reproduction mode:** Browser — reproduce from the URL below.

### Reproduction

1. Sign in as `admin@velocity.ai`
2. Launch the `ex_A1_loop` engine example from the canvas ("Run once") with the brief "Greet me warmly", so the retry loop runs `greet` and `check` twice
3. Watch the header token total on `/runs/{id}/stream` until the run completes
4. Reload the page

### Expected

The live total at completion equals the total after reload and the backend total: the sum of every `agent_complete` event.

### Actual

On run d091ed54-18c7-49fb-8d6f-5d3466f27f1b the live header showed "13.3K tokens" at completion and "19.8K tokens" after a reload. The backend total is 19815, the sum of all 6 agent_complete events (3181+3188+3324+3449+3366+3307). 13303 is exactly the LAST pass of each agent (3181+3449+3366+3307), so the live tally replaces an agent's tokens on a re-run instead of adding them.

### Notes

Reporter's suggestion: accumulate per agent_complete event, or take pipeline_complete's total, so the live value matches the reload value. It is not yet known whether this predates today's QA-KB-001..046 fixes; the analyzer should say.

<a id="qa-kb-094"></a>

## QA-KB-094 — ex_A4 human-gate .http script answers the conditional gate with a bare word, so the gate always blocks

- **Page:** n/a (developer tooling)
- **Route:** n/a (code-level)
- **Severity:** Low
- **Found by:** validate-bugs smoke test (another session)
- **Found at:** 2026-10-02 03:00
- **Reproduction mode:** Static — reproduce by the check below (read/grep). No browser needed.

### Reproduction

1. Open `tools/api/runs/run.ex_A4_human_gate_auto.http`
2. Find the human-gate answer: it sends `edited_content="spanish"` (a bare word)
3. Compare with how the conditional gate reads `ask` via `condition_agent`: it only accepts JSON `{"decision": ...}`

### Expected

The script's gate answer is a JSON decision the conditional route accepts, so the scripted run reaches its next step.

### Actual

The bare word never matches a route outcome, so the run always blocks with "no matching route outcome".

### Notes

Test tooling only; not caused by the QA-KB-001..046 changes.

<a id="qa-kb-095"></a>

## QA-KB-095 — Run page requests sandbox ref v1 for a run that has no refs, and gets 400

- **Page:** Run detail
- **Route:** /runs/{id}
- **Severity:** Medium
- **Found by:** validate-bugs page sweep (another session)
- **Found at:** 2026-10-07 17:40
- **Reproduction mode:** Browser + API

### Reproduction

1. `GET /api/runs/0f62f7bc-d3a2-4748-8004-0b534e1741ae/sandbox/refs` (old prototype_v2 run) returns `{"refs":[]}`
2. Open `/runs/0f62f7bc-d3a2-4748-8004-0b534e1741ae` in the UI
3. Watch the network tab: the page calls `GET /api/runs/0f62f7bc…/sandbox?ref=v1`

### Expected

With no refs, the UI leaves out `?ref` or falls back to the unpinned tree. No 4xx.

### Actual

`400 {"detail":"invalid ref"}`.

### Notes

Not yet checked whether the visible preview breaks. Reproduces on feat/stale-bug-fixes.

<a id="qa-kb-096"></a>

## QA-KB-096 — Pinned v1 tree lacks the run's deliverable, so every run page fires a 404 for it

- **Page:** Run detail (all tabs)
- **Route:** /runs/{id}
- **Severity:** Medium
- **Found by:** validate-bugs page sweep (another session)
- **Found at:** 2026-10-07 17:40
- **Reproduction mode:** Browser + API

### Reproduction

1. Run `78e185fb-c032-4154-8552-774781b6e5df` (backlog) has `deliverable_filename` `Backlog.pdf`
2. Open any of its pages (detail, steps, files, workspace, audit, stream)
3. The page calls `GET /api/runs/78e185fb…/sandbox/file?path=Backlog.pdf&ref=v1`

### Expected

The deliverable resolves for the pinned version, or the UI falls back to the unpinned file.

### Actual

`404 "File not found"`. The v1 tree has no `Backlog.pdf`. The likely cause is that the PDF was backfilled after the v1 ref was cut.

### Notes

Not yet checked whether the visible preview breaks. Reproduces on feat/stale-bug-fixes.

<a id="qa-kb-097"></a>

## QA-KB-097 — Resume is broken: a wave worker is skipped, a failed run can't resume, clarification answers are dropped

- **Page:** n/a (engine / resume)
- **Route:** n/a (code-level)
- **Severity:** High
- **Found by:** validate-bugs per-bug validation (another session), from card ISS-1061
- **Found at:** 2026-10-07 19:15
- **Reproduction mode:** Tests. Each file run alone. Reproduced on a clean export of 14a675db4, so not caused by the 2026-10-07 bug line.

### Reproduction

Run `backend/tests/integration/agents/test_restart_resume_db.py`. Four tests are red:

1. `test_midwave_resume_does_not_reinvoke_completed_workers`: on resume, wave-1 worker `c` never re-runs (`{'a': 2, 'b': 2}`).
2. `test_failed_run_resumes_skips_completed_tasks` / `test_user_resume_persists_output_columns`: a user resume of a failed run stays `failed` instead of reconciling to `completed`. The log says "Cannot transition run … from terminal state 'failed' to 'generating'".
3. `test_resume_dispatch_carries_rehydrated_planning_context`: a resumed dispatch drops the user's clarification answers (`D2`, `SPINNAKER-SENTINEL` missing).

Every run also logs `update_wave_run_merge_state … 'ScopedStore' object has no attribute '_acquire'`, which looks like a real AttributeError at `kernel_services.py:754`.

### Expected

A resume re-runs only the unfinished wave workers, a user resume of a failed run proceeds and reconciles, the resumed dispatch carries the clarification answers, and there is no AttributeError.

### Actual

As above.

### Notes

Card ISS-1061 has this as "minor". These are functional resume defects, so it is logged here as High.

<a id="qa-kb-098"></a>

## QA-KB-098 — test_revision_browser_dir_writer_driven fails on a module global that no longer exists

- **Page:** n/a (test code)
- **Route:** n/a (code-level)
- **Severity:** Low
- **Found by:** validate-bugs (another session), from card ISS-1063
- **Found at:** 2026-10-07 21:19
- **Reproduction mode:** Run `backend/tests/agents/test_per_run_paths_v3.py::test_revision_browser_dir_writer_driven` alone.

### Expected

The test passes. It should patch whatever the browser tool now uses for its sandbox root.

### Actual

It fails: it saves and restores `playwright_tools._SANDBOX`, which no longer exists. It was already red at 14a675db4.

<a id="qa-kb-099"></a>

## QA-KB-099 — test_sigterm_reaches_the_lifespan_shutdown_half_while_a_stream_is_live errors with UnitIsolationError

- **Page:** n/a (test code)
- **Route:** n/a (code-level)
- **Severity:** Low
- **Found by:** validate-bugs (another session) while validating QA-KB-076
- **Found at:** 2026-10-07 23:10
- **Reproduction mode:** Run `backend/tests/unit/services/test_shutdown_reachability.py::test_sigterm_reaches_the_lifespan_shutdown_half_while_a_stream_is_live` alone.

### Expected

The test runs. A test that spawns a uvicorn subprocess belongs in `tests/integration/`, or must be marked `@pytest.mark.allow_io`.

### Actual

`UnitIsolationError`: it spawns a uvicorn subprocess inside `tests/unit`. It fails the same way at 9ef547e74^, so QA-KB-076 did not cause it.

<a id="qa-kb-100"></a>

## QA-KB-100 — A user-saved workflow override can carry a gate users are not allowed to use (security)

- **Page:** Workflow override save (POST /api/user-workflows), workflow listing (GET /api/workflows/{type})
- **Route:** /api/user-workflows, /api/workflows/ppt
- **Severity:** High (security)
- **Found by:** validate-bugs (another session) while validating QA-KB-088, from card ISS-1093
- **Found at:** 2026-10-07 23:45
- **Reproduction mode:** Test plus API. `backend/tests/unit/test_workflow_override.py::test_a_not_user_allowed_gate_is_rejected` fails. The QA-KB-088 probe (`evidence/qa-kb-088/09-analyze-merge-override-trust-probe-output.txt`) shows it end to end.

### Expected

Saving an override that adds a `user_allowed=False` gate (for example the "security" gate) is rejected. Such a gate is never served or run from a user override.

### Actual

`merge_override_steps` compiles the override at `trust="db"`, so the user_allowed check is skipped. The override is saved, served by GET /api/workflows/ppt, and run.

### Notes

It was pre-existing: it fails at 1d49a7c2f^ too, where a unit-guard setup error hid it.

<a id="qa-kb-101"></a>

## QA-KB-101 — test_list_carries_launchable_flags asserts a stale workflow label

- **Page:** n/a (test code)
- **Route:** n/a (code-level)
- **Severity:** Low
- **Found by:** validate-bugs (another session), from card ISS-1094
- **Found at:** 2026-10-07 23:45
- **Reproduction mode:** Run `backend/tests/integration/api/test_workflows_api.py::test_list_carries_launchable_flags` alone.

### Expected

The test asserts the current label.

### Actual

It expects "Build an interactive prototype", but the list now says "Build an interactive prototype (Fast)". It was pre-existing, hidden behind a setup error until QA-KB-088 relocated the file.

<a id="qa-kb-102"></a>

## QA-KB-102 — A user resume that dies before its first dispatch ends silently

- **Page:** Run detail (Resume)
- **Route:** /runs/{id}
- **Severity:** Medium
- **Found by:** QA-KB-097 analysis (ISS-1103)
- **Found at:** 2026-10-08 00:45
- **Reproduction mode:** Code-level. See `evidence/qa-kb-097/analysis-15-swallowed-resume-durable-state.txt`.

### Expected

A resume that fails before its first dispatch marks the run failed and tells the user, so the run never sits silently in a resumed state.

### Actual

`_drive_resumed_stream` swallows the exception, and `resume_run` has four silent early exits. The run ends with no error to the user and no failed status.

<a id="qa-kb-103"></a>

## QA-KB-103 — Saving "my version" of 8 built-ins from the canvas now returns 422 (regression from QA-KB-100)

- **Page:** Composer canvas (save my version of a built-in)
- **Route:** /api/user-workflows (POST / PATCH)
- **Severity:** High
- **Found by:** validate-bugs (another session), from card ISS-1118 (FIX-766 follow-up)
- **Found at:** 2026-10-08 14:55
- **Reproduction mode:** Open app_builder or prototype on the canvas, save "my version" without changing anything, and watch the save request.

### Expected

Saving an unchanged or lightly edited override of a built-in succeeds. FIX-766's trust="user" check still refuses any engineer-only key the user actually added or changed.

### Actual

The canvas sends the built-in's engineer-only step keys back unchanged, and the shared compile_override_steps check (trust="user") rejects them with 422. Eight built-ins are affected, including app_builder and prototype. See evidence/qa-kb-100/analysis-04.

<a id="qa-kb-104"></a>

## QA-KB-104 — sync-from-file skips the tier entitlement check (security)

- **Page:** n/a (API)
- **Route:** POST /api/user-workflows/{id}/sync-from-file
- **Severity:** High
- **Found by:** validate-bugs (another session), from card ISS-1117 (split from ISS-1112)
- **Found at:** 2026-10-08 14:55
- **Reproduction mode:** As a basic-tier user, call sync-from-file with an enterprise-only pipeline_type on a row you own.

### Expected

The endpoint refuses a pipeline_type the caller is not entitled to run (the can_run_pipeline check), the same way launch does.

### Actual

No entitlement check runs, so any tier can copy an enterprise-only workflow's manifest into a row it owns.

<a id="qa-kb-105"></a>

## QA-KB-105 — A resume that ends on the workflow_unsatisfiable frame still ends silently

- **Page:** Run detail (Resume)
- **Route:** /runs/{id}
- **Severity:** Medium
- **Found by:** QA-KB-102 fixer (card ISS-1125); validate-bugs asked for it to be fixed before the smoke test
- **Found at:** 2026-10-08 16:08
- **Reproduction mode:** Code-level. Resume a run whose _execute_impl yields the workflow_unsatisfiable error frame and returns.

### Expected

The resume is recorded through _fail_resume: one pipeline_failed with the reason, the run marked failed, and a live frame.

### Actual

The stream returns normally, so FIX-768's funnel never fires. There is no terminal event and the run stays non-terminal. This is the same silent-resume symptom as QA-KB-102.

<a id="qa-kb-106"></a>

## QA-KB-106 — A rejected launch is silent: no message, and Run stays disabled

- **Page:** Composer canvas (Run once), and likely the /create wizards
- **Route:** /workflows/{id}/canvas → POST /api/runs
- **Severity:** Medium
- **Found by:** validate-bugs smoke test (SMOKE-1)
- **Found at:** 2026-10-09 01:48
- **Reproduction mode:** Open /workflows/ex_A1_loop/canvas, enter a brief, and click "Run once" while POST /api/runs is rejected (e.g. 503 model_provider_unavailable, 403 tier_not_entitled or 422 manifest error). Evidence: /tmp/bughunt-lane2-out/smoke-runonce-503.png and /tmp/bughunt-lane2-out/console-2026-10-08T23-48-07-524Z.log lines 11-13.

### Expected

The user sees the API error message (error or detail) in a toast or inline, and the Run button is enabled again.

### Actual

The page stays on the canvas with no message, and Run once stays disabled. The onLaunch .catch in frontend/src/app/[...view]/page.tsx (around lines 4453-4467) only resets state and logs to the console in dev. Only host_capacity_exhausted gets UI (via ServiceBusyProvider). Fix it once in that catch, then check that the /create wizards use the same path.

<a id="qa-kb-107"></a>

## QA-KB-107 — preflight_check_provider refuses the launch on an expired Bedrock token even with USE_LOCAL_OLLAMA=1

- **Page:** n/a (launch preflight)
- **Route:** POST /api/runs
- **Severity:** Low (dev-only)
- **Found by:** validate-bugs smoke test (SMOKE-2)
- **Found at:** 2026-10-09 01:48
- **Reproduction mode:** Set USE_LOCAL_OLLAMA=1 with an expired AWS_BEARER_TOKEN_BEDROCK, then launch any run.

### Expected

With USE_LOCAL_OLLAMA=1 the run never touches Bedrock, so the preflight skips the Bedrock token check, as it already does for ANTHROPIC_API_KEY.

### Actual

preflight_check_provider (backend model_factory.py, around line 105) returns 503 model_provider_unavailable over the expired Bedrock token, which blocks the Ollama fallback.

<a id="qa-kb-108"></a>

## QA-KB-108 — Login returns a raw 500 (no CORS header) when the AWS SSO credentials are expired

- **Page:** /login
- **Route:** POST /api/auth/login
- **Severity:** Medium
- **Found by:** validate-bugs smoke test (SMOKE-3)
- **Found at:** 2026-10-09 03:46
- **Reproduction mode:** With the AWS SSO session expired, sign in as any user. Backend log: /private/tmp/velocity-8000.log around line 11799 (botocore TokenRetrievalError "Token has expired and refresh failed" at app/api/auth.py:342 in login).

### Expected

A provider or credentials failure during sign-in maps to a handled 503 with a clear message (e.g. "Sign-in service unavailable"), as the launch preflight does for Bedrock. The response carries the normal CORS headers, so the login page can show the message.

### Actual

An unhandled exception gives a raw 500 with no CORS header. The browser reports a CORS block, and the login page shows only "An unexpected error occurred. Please try again."


<a id="qa-kb-109"></a>

## QA-KB-109 — Admin users table shows Delete on the admin's own row

- **Page/Route:** /admin/users
- **Severity:** Medium
- **Found by:** validate-bugs full smoke + offline e2e on :8001/:3001 (2026-10-09). Logged under the frozen scope and not scheduled.
- **Found at:** 2026-10-09 13:17
- **Reproduction mode:** e2e 11_admin test_an_admin_cannot_delete_their_own_account; 19 test_an_admin_cannot_delete_themselves_into_lockout. Rerun-confirmed logs are in validate-bugs' scratchpad e2e/rerun/*.log.

### Actual

The admin's own row renders "Delete admin@velocity.ai". The server refuses with 400, so this is UI-only. Regression from b2a621f84, which removed currentUserId.


<a id="qa-kb-110"></a>

## QA-KB-110 — "Edit brief and run again" on a failed run pre-fills an empty brief

- **Page/Route:** /runs/{id}
- **Severity:** Medium
- **Found by:** validate-bugs full smoke + offline e2e on :8001/:3001 (2026-10-09). Logged under the frozen scope and not scheduled.
- **Found at:** 2026-10-09 13:17
- **Reproduction mode:** e2e 18_chat_lane test_edit_brief_and_run_again_prefills_the_original_brief. Rerun-confirmed logs are in validate-bugs' scratchpad e2e/rerun/*.log.

### Actual

The composer is pre-filled with '' instead of the failed run's original brief.


<a id="qa-kb-111"></a>

## QA-KB-111 — Version pinning: the tabs and picker never fetch the pinned revision's run id

**Parked 2026-10-12** (user hard stop, "get done in 1 hour and park rest"). Was UNREPRODUCIBLE: 3 cold loads plus a soft-nav sweep on 2026-10-12 all fetched the pinned v2 run, but validate-bugs had reproduced it on 2026-10-09. Next: re-run the repro on a freshly restarted :3000/:3001 with the build commit recorded. If it is still clean, close as UNREPRODUCIBLE.

- **Page/Route:** /runs/{id}/versions/N
- **Severity:** High
- **Found by:** validate-bugs full smoke + offline e2e on :8001/:3001 (2026-10-09). Logged under the frozen scope and not scheduled.
- **Found at:** 2026-10-09 13:17
- **Reproduction mode:** 9 failures in e2e 21_run_families_and_versions. Rerun-confirmed logs are in validate-bugs' scratchpad e2e/rerun/*.log.

### Actual

/runs/{id}/versions/N shows the wrong revision. Check against QA-KB-055's page.tsx change.

### Repro detail (validate-bugs, rerun-confirmed)

Family run 2708dbf1-50d0-465d-9bed-56b651ea1abf; v2 = revision 23bd9c67-e239-4979-b14a-cb78222795e8. On /runs/2708dbf1…/versions/2/files and …/versions/2/audit, the page never requests the revision's own data (no /api/runs/23bd9c67…/gate-events or artifacts call). Tests: test_tab_switch_keeps_fetching_the_pinned_revisions_run_id, test_audit_tab_fetches_the_pinned_versions_own_run_id. "FINAL OUTPUT" never appears within 20 s on the pinned files tab, and [data-testid='tab-thinking'] never appears on the pinned Steps tab.
Harness causes to separate out: (a) 3 tests time out waiting for [data-testid="run-header"] button[aria-haspopup='listbox'] (the version picker); check whether the selector or markup changed before calling it a regression. (b) 2 chat deep-link tests fail with "no 'Revision started' card — this run has no revision". That is fixture data, not the app.
Log: validate-bugs scratchpad e2e/rerun/21_run_families_and_versions.log

### Reopened 2026-10-09 (validate-bugs live repro, current code, cold load each URL)

Family root 78e185fb-c032-4154-8552-774781b6e5df; v2 = 80054fbc-71cc-42de-adeb-ae2db82eb2f2.
- /runs/78e185fb…/versions/2/files is OK: it fetches /api/runs/80054fbc… plus artifacts, sandbox, sandbox/refs, sandbox/file and events.
- /runs/78e185fb…/versions/2/steps is wrong: the only run requests are for the ROOT (/api/runs/78e185fb…, artifacts, family, sandbox/refs, events). Nothing is requested for 80054fbc, so the v2 URL shows v1's steps.
- /runs/78e185fb…/versions/2/audit is the same: root-only requests, with no gate-events or hook-runs for 80054fbc.
So the Files tab honours the pin, and the Steps and Audit tabs ignore it on a cold load. The first validation saw 80054fbc requests at around 12-15 s. Separate the late, incidental fetch from what the Steps and Audit tab bodies actually render (v1 vs v2 content). The stale e2e fixture IDs (2708dbf1 / 23bd9c67) belong to QA-KB-122.

<a id="qa-kb-112"></a>

## QA-KB-112 — Admin sees the MFA enrollment wall on /settings/security and gets a new TOTP secret on every visit

**Parked 2026-10-12** (user hard stop, "get done in 1 hour and park rest"). Was ANALYZED: root ISS-1203, siblings ISS-1204 to 1206; owner decision 112a (keep the enrolment page, test-only fix). Next: write the failing tests, then align the e2e 09 settings suite, the spec and velocity.json with the /settings/security enrolment page.

- **Page/Route:** /settings/security
- **Severity:** Medium
- **Found by:** validate-bugs full smoke + offline e2e on :8001/:3001 (2026-10-09). Logged under the frozen scope and not scheduled.
- **Found at:** 2026-10-09 13:17
- **Reproduction mode:** 8 failures in e2e 09_settings. Rerun-confirmed logs are in validate-bugs' scratchpad e2e/rerun/*.log.

### Actual

The Account Settings Security tab is replaced by the enrollment wall, and every visit mints a fresh TOTP secret. Came from b2a621f84. It may be intended; that is the user's decision.

### Owner decision

Owner decision 2026-10-09: option a, keep as is. /settings/security stays the TOTP enrollment page (b2a621f84). Test-only fix: update velocity.json (`/settings/security` no longer the tab-security route) and the 8 failing 09_settings e2e tests to the enrollment-page behaviour. No app change.

<a id="qa-kb-113"></a>

## QA-KB-113 — Composer agent config sub-tabs missing (no "Agent · step 1 of N")

- **Page/Route:** /workflows/{id}/canvas
- **Severity:** Medium
- **Found by:** validate-bugs full smoke + offline e2e on :8001/:3001 (2026-10-09). Logged under the frozen scope and not scheduled.
- **Found at:** 2026-10-09 13:17
- **Reproduction mode:** e2e 04_composer_canvas. Rerun-confirmed logs are in validate-bugs' scratchpad e2e/rerun/*.log.

### Actual

The per-agent config sub-tabs do not render.

### Repro detail (validate-bugs, rerun-confirmed)

Test: 04_composer_canvas test_the_config_rails_agent_tab_has_five_sub_tabs_of_its_own. After selecting an agent in the canvas config rail, /Agent · step 1 of \d/ never shows. Rerun the single node id on :3000. Log: e2e/rerun/04_composer_canvas.log

<a id="qa-kb-114"></a>

## QA-KB-114 — Composer shows the blank "Custom Agent" template while authoring an override

**Parked 2026-10-12** (user hard stop, "get done in 1 hour and park rest"). Was ESCALATED: the owner has not chosen yet; the recommendation is option c (hide the Custom Agent tile only in "Save as my version"). Next: owner picks a, b or c, then analyze and fix.

- **Page/Route:** /workflows/{id}/canvas
- **Severity:** Low
- **Found by:** validate-bugs full smoke + offline e2e on :8001/:3001 (2026-10-09). Logged under the frozen scope and not scheduled.
- **Found at:** 2026-10-09 13:17
- **Reproduction mode:** e2e 04_composer_canvas. Rerun-confirmed logs are in validate-bugs' scratchpad e2e/rerun/*.log.

### Actual

The blank template appears in override authoring mode.

### Repro detail (validate-bugs, rerun-confirmed)

Test: 04_composer_canvas test_the_blank_custom_agent_template_is_withheld_when_authoring_an_override. The exact text "Custom Agent" has count 1 and is expected 0 while authoring a built-in override (e.g. from "Save as my version"). Log: e2e/rerun/04_composer_canvas.log

<a id="qa-kb-115"></a>

## QA-KB-115 — Composer fetches capabilities twice

- **Page/Route:** /workflows/{id}/canvas
- **Severity:** Low
- **Found by:** validate-bugs full smoke + offline e2e on :8001/:3001 (2026-10-09). Logged under the frozen scope and not scheduled.
- **Found at:** 2026-10-09 13:17
- **Reproduction mode:** e2e 04_composer_canvas (ISS-796 test). Rerun-confirmed logs are in validate-bugs' scratchpad e2e/rerun/*.log.

### Actual

Duplicate capabilities fetch (ISS-796 regression test).

### Repro detail (validate-bugs, rerun-confirmed)

Test: test_iss796_capabilities_double_fetch::test_opening_the_agent_config_tab_reuses_the_capabilities_fetch. The capabilities endpoint is requested twice when the Agent config tab opens. Log: e2e/rerun/04_composer_canvas.log

<a id="qa-kb-116"></a>

## QA-KB-116 — Checking a review gate in the Advanced modal times out

- **Page/Route:** /runs/{id}
- **Severity:** Low
- **Found by:** validate-bugs full smoke + offline e2e on :8001/:3001 (2026-10-09). Logged under the frozen scope and not scheduled.
- **Found at:** 2026-10-09 13:17
- **Reproduction mode:** e2e 03 test_checking_a_review_gate_sets_that_agents_gate_in_the_advanced_modal. Rerun-confirmed logs are in validate-bugs' scratchpad e2e/rerun/*.log.

### Actual

Clicking the gate checkbox in the advanced modal times out.


<a id="qa-kb-117"></a>

## QA-KB-117 — Deliverable access hides "Branch on a decision"

- **Page/Route:** /settings (deliverable access)
- **Severity:** Low
- **Found by:** validate-bugs full smoke + offline e2e on :8001/:3001 (2026-10-09). Logged under the frozen scope and not scheduled.
- **Found at:** 2026-10-09 13:17
- **Reproduction mode:** e2e 17 test_deliverable_access_omits_workflows_the_catalog_offers. Rerun-confirmed logs are in validate-bugs' scratchpad e2e/rerun/*.log.

### Actual

A workflow the catalog offers is missing from deliverable access.

### Owner decision

Owner decision 2026-10-09: option 2, plus a rule: every example workflow that delivers something is listed under Deliverable access. Add the entitled engine-example workflows (or an "Engine examples" group listing them) to the Deliverable access grid, driven by the same entitlement list as the home catalog rather than a hand-kept map, so the two surfaces agree. Update e2e S-17-08 (test_deliverable_access_omits_workflows_the_catalog_offers), which pins the old omission.

<a id="qa-kb-118"></a>

## QA-KB-118 — Opening an agent in the Steps tab fetches artifacts twice

- **Page/Route:** /runs/{id} (Steps tab)
- **Severity:** Low
- **Found by:** validate-bugs full smoke + offline e2e on :8001/:3001 (2026-10-09). Logged under the frozen scope and not scheduled.
- **Found at:** 2026-10-09 13:17
- **Reproduction mode:** e2e 07 test_opening_an_agent_in_steps_tab_fetches_artifacts_once. Rerun-confirmed logs are in validate-bugs' scratchpad e2e/rerun/*.log.

### Actual

Duplicate artifacts fetch.


<a id="qa-kb-119"></a>

## QA-KB-119 — GET /api/runs/{id}/events with no params returns 53 MB in 13 s

- **Page/Route:** GET /api/runs/{id}/events
- **Severity:** Medium
- **Found by:** validate-bugs full smoke + offline e2e on :8001/:3001 (2026-10-09). Logged under the frozen scope and not scheduled.
- **Found at:** 2026-10-09 13:17
- **Reproduction mode:** validate-bugs smoke, run 78e185fb. Rerun-confirmed logs are in validate-bugs' scratchpad e2e/rerun/*.log.

### Actual

Unbounded replay with no paging default (run 78e185fb).


<a id="qa-kb-120"></a>

## QA-KB-120 — A failed run's finalize logs CalledProcessError on git add for missing .chain files

- **Page/Route:** n/a (finalizer)
- **Severity:** Low
- **Found by:** validate-bugs full smoke + offline e2e on :8001/:3001 (2026-10-09). Logged under the frozen scope and not scheduled.
- **Found at:** 2026-10-09 13:17
- **Reproduction mode:** validate-bugs smoke, run eb1d7551. Rerun-confirmed logs are in validate-bugs' scratchpad e2e/rerun/*.log.

### Actual

git add is called on .chain files that do not exist (run eb1d7551).


<a id="qa-kb-121"></a>

## QA-KB-121 — Launch preflight passes a Bedrock key that Bedrock rejects (AccessDenied "API Key invalid")

- **Page/Route:** POST /api/runs
- **Severity:** Medium
- **Found by:** validate-bugs full smoke + offline e2e on :8001/:3001 (2026-10-09). Logged under the frozen scope and not scheduled.
- **Found at:** 2026-10-09 13:17
- **Reproduction mode:** validate-bugs, direct converse call. Rerun-confirmed logs are in validate-bugs' scratchpad e2e/rerun/*.log.

### Actual

AWS_BEARER_TOKEN_BEDROCK decodes as valid until 19:06Z, but Bedrock rejects it. The preflight only checks expiry, so the launch is accepted and then fails (cleanly). A direct converse call confirmed it.

### Owner decision

Owner decision 2026-10-09: option a. Keep the expiry-only, no-network preflight (no live Bedrock probe). Improve the failure the user sees when Bedrock rejects the key at the first model call (AccessDenied "API Key invalid"): a clear message that the Bedrock API key is invalid or revoked and must be rotated, not a generic provider error. Owner context: only local dev uses the temporary rotated key. Production uses a persisted key, so keep this change small and dev-friendly.

<a id="qa-kb-122"></a>

## QA-KB-122 — Stale e2e tests after intentional app changes

- **Page/Route:** n/a (e2e tests)
- **Severity:** Low
- **Found by:** validate-bugs full smoke + offline e2e on :8001/:3001 (2026-10-09). Logged under the frozen scope and not scheduled.
- **Found at:** 2026-10-09 13:17
- **Reproduction mode:** validate-bugs triage e2e/rerun/triage.txt. Rerun-confirmed logs are in validate-bugs' scratchpad e2e/rerun/*.log.

### Actual

12 tests POST /api/admin/users with "password" (422 extra_forbidden after QA-KB-077); "Pitch an idea (Detailed)" should be "(Depth)" in framework/locators/home_catalog.py; 24 test_the_reserved_subtrees_are_never_listed vs the deliberate f9df3737c; 4 strict-XPASS markers to remove (ISS-923, ISS-1033 in 05, ISS-213 in 06, ISS-190 in 12).

### Added 2026-10-09: also stale (from validating QA-KB-111, 113 and 115)

- test_composer_canvas.py:271 regex /Agent · step 1 of \d/ should be /AI agent · step 1 of \d/, and framework/locators/composer.py:52 AGENT_SUBTABS should have "Data" instead of "Hooks" (wording from 911547c7d). See UNREPRODUCIBLE.md#qa-kb-113.
- test_iss796_capabilities_double_fetch.py:22: remove the strict xfail, because ISS-796 is resolved (FIX-617). See UNREPRODUCIBLE.md#qa-kb-115.
- test_iss_230_version_pin_survives_tab_switch.py:23-24 hard-codes family 2708dbf1 / revision 23bd9c67, which no longer exist.

<a id="qa-kb-123"></a>

## QA-KB-123 — e2e test data lacks a v1 "prototype" run

**Parked 2026-10-12** (user hard stop, "get done in 1 hour and park rest"). Was TESTED: root ISS-1194 has a strict-xfail test in backend/tests/unit/test_e2e_tier_drift.py; siblings ISS-1207 to 1209 are open. Next: fix the e2e chip callers to skip absent chips and seed the missing v1 prototype run.

- **Page/Route:** n/a (test data)
- **Severity:** Low
- **Found by:** validate-bugs full smoke + offline e2e on :8001/:3001 (2026-10-09). Logged under the frozen scope and not scheduled.
- **Found at:** 2026-10-09 13:17
- **Reproduction mode:** validate-bugs triage e2e/rerun/triage.txt. Rerun-confirmed logs are in validate-bugs' scratchpad e2e/rerun/*.log.

### Actual

4 tests need a v1 prototype run, but the DB only has prototype_v2.

<a id="qa-kb-124"></a>

## QA-KB-124 — ex_A1_loop "Run once" on Bedrock Haiku fails: check's gate has nowhere to route

- **Page/Route:** /workflows/ex_A1_loop/canvas → Run once
- **Severity:** Medium
- **Found by:** validate-bugs Bedrock smoke on :8001/:3001 (2026-10-09). Logged under the frozen scope and not scheduled.
- **Found at:** 2026-10-09 13:43
- **Reproduction mode:** Launch ex_A1_loop from the canvas on Bedrock Haiku (run 9a931a7a-54dc-4f4f-a316-b5ac1dbe3822). The same canvas run completed on local Ollama (run 32bbde34).

### Actual

The run ends degraded with "Check's conditional gate had nowhere to route: no matching outcome and no default_next". custom-agent:check answered in prose ("The greeting contains no joke.") instead of the required {"decision": "retry"} line. Either Haiku does not follow the prompt, or the canvas copy loses check's exact-format prompt. Fix the prompt first (user rule: prompt fix before code).

<a id="qa-kb-125"></a>

## QA-KB-125 — In-app previews run agent HTML with allow-scripts allow-same-origin on the app origin (security)

- **Page/Route:** prototype preview and OD deck preview (Results / Preview, "Open in new tab")
- **Severity:** High
- **Found by:** FIX-745 fixer (card ISS-1067). The owner approved logging and fixing it on 2026-10-09.
- **Found at:** 2026-10-07 20:30
- **Reproduction mode:** See .knowledge/cards/20261007-2030-ISS-1067.md.

### Expected

Agent-generated HTML never runs with same-origin access to the app (the exposure FIX-745 already removed from the share link).

### Actual

The in-app prototype and OD deck previews use sandbox="allow-scripts allow-same-origin" on the app origin, and "Open in new tab" loads the HTML with no sandbox at all.

<a id="qa-kb-126"></a>

## QA-KB-126 — The enterprise-only Composer gate keys on a caller-chosen field, so a basic user gets exec (security)

- **Page/Route:** POST /api/user-workflows, then launch by user_workflow_id
- **Severity:** High
- **Found by:** QA-KB-100 analysis (card ISS-1114). The owner approved logging and fixing it on 2026-10-09.
- **Found at:** 2026-10-08 14:15
- **Reproduction mode:** See .knowledge/cards/20261008-1415-ISS-1114.md. As a basic-tier user, save a manifest-backed row with base_pipeline_type=ppt and no override flag, then launch it by id.

### Expected

A basic-tier user cannot obtain exec or spawn_subagents grants through a saved row.

### Actual

The enterprise-only Composer gate keys on base_pipeline_type, which the caller picks. The trust="db" launch compile then grants exec and spawn_subagents.

<a id="qa-kb-127"></a>

## QA-KB-127 — Design-system preview frames generated HTML on the app origin with allow-same-origin (security)

**Parked 2026-10-12** (user hard stop, "get done in 1 hour and park rest"). Was LOGGED (security, High), never validated. Next: validate, then apply the QA-KB-125 pattern (lib/agentHtml.ts, AGENT_HTML_SANDBOX allow-scripts only) to DesignSystemDetailModal.

- **Page/Route:** prototype design-system picker → design system detail modal
- **Severity:** High
- **Found by:** validate-bugs while validating FIX-775 (QA-KB-125). Logged under the frozen scope; needs the owner's go to schedule.
- **Found at:** 2026-10-09 16:35
- **Reproduction mode:** frontend/src/components/workflow/prototype/DesignSystemDetailModal.tsx:61-67 and :218. When `!system.has_preview`, it builds HTML from `detail.body` (generateDesignSystemPreviewHtml), wraps it in a blob: URL on the app origin, and frames it with sandbox="allow-scripts allow-same-origin". openInNewTab (:100) also window.opens that blob as a top-level page. The has_preview path loads the :8000 backend URL (cross-origin) but still uses allow-same-origin.

### Expected

It goes through lib/agentHtml.ts (AGENT_HTML_SANDBOX, frameableAgentHtml, openAgentHtmlInNewTab), the same as every other agent-HTML surface after FIX-775.

### Actual

The ISS-1067 pattern applies if design-system body or DESIGN.md content can be user- or agent-authored (to be confirmed at validate).

<a id="qa-kb-128"></a>

## QA-KB-128 — Preview "open in new tab" opens non-HTML deliverables as a top-level blob of their declared mimetype (security)

**Parked 2026-10-12** (user hard stop, "get done in 1 hour and park rest"). Was LOGGED (security, Medium), never validated. Next: validate, then route non-HTML deliverables through a download or script-free wrapper instead of a top-level blob.

- **Page/Route:** Preview chrome open-in-new button
- **Severity:** Medium
- **Found by:** the FIX-775 fixer (found during QA-KB-125), confirmed by validate-bugs. Logged under the frozen scope; needs the owner's go to schedule.
- **Found at:** 2026-10-09 16:35
- **Reproduction mode:** PreviewPanel handlePreviewOpen. A deliverable whose declared mimetype is not text/html (e.g. image/svg+xml) is opened as `window.open(blob:)` of that type.

### Expected

Only inert types open as a top-level blob. Script-capable types (SVG, XML/XHTML) go through the sandboxed wrapper or are downloaded.

### Actual

An image/svg+xml deliverable would run its script on the app origin.
