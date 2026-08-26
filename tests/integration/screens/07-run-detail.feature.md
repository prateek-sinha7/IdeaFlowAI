# Feature: Run detail

The busiest surface in the product. A persistent chat lane on the left, a
five-tab result pane on the right, and a header that must survive remounts.

**Routes:** `/runs/{id}`, `/runs/{id}/steps`, `/runs/{id}/steps/{agentId}`,
`/runs/{id}/files`, `/runs/{id}/audit`, `/runs/{id}/stream`,
`/runs/{id}/preview/full`, `/runs/{id}/versions/{v}`, **`/runs/{id}/workspace`**
**Screenshots:** `05-runs/` — p23 preview, p24 steps, p25 agent step, p26 files, p27 workspace (D-02), p28 audit, p29 full preview, p30 stream, p34 pinned version · `12-overlays/71` version picker

---

## The chat lane (always present)

`[data-testid="execution-chat-lane"]` / `run-chat-lane`.

| Element | Testid |
|---|---|
| Back to history | `lane-back` |
| Workflow type | `lane-run-type` — e.g. `EX A4 HUMAN GATE`, `PPT V2` |
| Status | `lane-run-status` — e.g. `Done` |
| Title | `lane-run-title` — the brief excerpt |
| Meta | `lane-run-meta` — age · duration · token total |
| Transcript | `chat-lane-transcript` / `chat-transcript` / `chat-message` |
| Result card | `chat-result-card`, `chat-result-card-link` |
| Pipeline mini-map | `lane-pipeline-mini` — `PIPELINE · N AGENTS` + `Open Steps →` |
| Deliverable card | `lane-deliverable` — filename + `open in preview →` |
| Composer | `chat-composer`, `textarea[name="run-chat-message"]`, `chat-attachments`, `chat-send` |
| Adornments toggle | `lane-adornments-toggle` / `lane-adornments` |

Transcript milestones seen: "Run started", "Review approved — build continues",
"Clarifications answered", "Before I build, I need to lock a few things down.",
"Delivered — open in Preview →". A run awaiting a human shows **`Answer in Steps`**.

The mini-map renders **every** roster agent, including skipped ones. A conditional
run shows all branches; only the taken one has a duration.

## The result pane — five tabs

| Tab | Testid | URL |
|---|---|---|
| Preview | `tab-preview` | `/runs/{id}` |
| Steps | **`tab-thinking`** | `/runs/{id}/steps` |
| Files | `tab-files` | `/runs/{id}/files` |
| Workspace | `tab-workspace` | `/runs/{id}/workspace` ⚠ |
| Audit | `tab-audit` | `/runs/{id}/audit` |

The Steps tab's testid is `tab-thinking` — legacy naming, still live. Use the
testid, not the label.

Header actions: `Version v1`, `Share`, `Download`, and on a deck run `Full Screen`.

### Preview
`preview-chrome`, `preview-url`, `renders-as-switch`, `renderer-pill`,
`Open the deliverable in a new tab`. Renderer options: `Auto`, `HTML`, `Markdown`,
`Bundle` — plus `Slides` for a deck. `Copy All` copies the output.

### Steps
Header `Run complete` / `3 / 5 agents · 49s`. A `Starting point` block showing the
brief with `SHOW MORE`. Then one `steps-agent-row` per roster agent:
`Ask For Language 5s · 3.4K tok`, and for an untaken branch `Say Hello Skipped`.

**`3 / 5 agents` is correct, not a bug** — 5 in the roster, 3 dispatched, 2 skipped
by a conditional gate. FIX-308 was the opposite failure: a composed agent silently
*not* dispatched while the run reported `pipeline_complete`. Assert that dispatched
+ skipped equals the roster.

### Files
`<N> files available · <N> deliverable`, `Download All`, then three groups:
- **FINAL OUTPUT** — `greeting.md`, `Markdown (.md) · 12 B · validated`, with `Preview` and `Download`
- **AGENT OUTPUTS (N)** — "Intermediate work-in-progress from each agent in the pipeline", numbered `01-…md`, `02-…md`
- **RUN INPUT** — `prompt.md`

### Workspace
A flat list of workspace files with sizes, and an empty state "Select a file to
view it." until one is picked. See D-02: this tab's URL is not in `routes.ts`.

### Audit
`Export`, filter pills `All <n>`, `Governance <n>`, `Security <n>`, `Activity <n>`,
and a `Blocked / denied only` toggle. Rows read
`<source> <subject> · <time> GATE Passed`, e.g.
`audit logger — before step — · 12:59:36 PM GATE Passed`,
`human custom-agent:pick-language · 01:00:17 PM GATE Passed`,
`conditional custom-agent:pick-language · 01:00:20 PM GATE Passed`.

---

```gherkin
Feature: Run detail

  Background:
    Given I am signed in as "qa-admin@flowinqa.com"
    And a completed run exists that I own

  Scenario: A cold load of a run shows its header and deliverable
    When I cold-load "/runs/{id}"
    Then the lane shows the workflow type, status, title and meta
    And the pipeline mini-map reports the roster size
    And the deliverable card names the output file

  Scenario Outline: Every tab has an addressable URL
    When I cold-load "<url>"
    Then the tab "<tab>" is selected
    And that tab's content is rendered

    Examples:
      | url                      | tab       |
      | /runs/{id}               | Preview   |
      | /runs/{id}/steps         | Steps     |
      | /runs/{id}/files         | Files     |
      | /runs/{id}/workspace     | Workspace |
      | /runs/{id}/audit         | Audit     |

  Scenario Outline: Clicking a tab pushes its URL
    Given I am on "/runs/{id}"
    When I click the tab with testid "<testid>"
    Then the URL becomes "<url>"
    And the run header still shows the same workflow type and title

    Examples:
      | testid        | url                  |
      | tab-thinking  | /runs/{id}/steps     |
      | tab-files     | /runs/{id}/files     |
      | tab-workspace | /runs/{id}/workspace |
      | tab-audit     | /runs/{id}/audit     |
      | tab-preview   | /runs/{id}           |

  # ---- The regression guards. These are why this suite exists. ----

  Scenario: Switching tabs does not wipe run state
    Given I am on "/runs/{id}" and the header names the workflow correctly
    When I click through Steps, Files, Workspace, Audit and back to Preview
    Then the header still names the same workflow at every step
    And it never falls back to "USER STORIES"
    And the deliverable card is still populated
    # FIX-302. The tab-route effect re-seeded the run refs and returned early,
    # restoring WHICH run the tab drives but none of its DATA. A run parked at
    # waiting_for_user emits nothing, so the screen was left with no type, no
    # clarify panel, and no way to answer — permanently unreachable.

  Scenario: A run parked at a human gate stays answerable after a tab click
    Given a run in state "waiting_for_user"
    When I cold-load "/runs/{id}"
    Then I see the clarify prompt and an "Answer in Steps" affordance
    When I click the Steps tab
    And I click back to Preview
    Then the clarify prompt is STILL present
    And the run is still answerable
    # The exact FIX-302 reproduction. questionnaire_ready already fired before
    # the click, so nothing re-emits it — a remount that does not refetch loses
    # it for good.

  Scenario: Browser back and forward move between tabs without remounting the run
    Given I am on "/runs/{id}"
    When I click the Steps tab
    And I click the Files tab
    And I press browser Back
    Then I am on "/runs/{id}/steps"
    And the run header is unchanged
    When I press browser Forward
    Then I am on "/runs/{id}/files"
    And the run header is unchanged
    # BUG-030. Tab navigation must be a shallow pushState, not a remount.

  Scenario: A hard refresh on any tab restores that tab
    When I cold-load "/runs/{id}/audit"
    And I reload the page
    Then the Audit tab is still selected
    And the audit rows are rendered

  @defect
  # D-02. The URL works; the router does not know it. parseViewPath's `runs`
  # branch handles steps/files/audit/stream/versions/preview and falls through to
  # `unknown` for anything else, and routes.ts has no builder. It renders because
  # DashboardLayout owns the tab independently. ADR-0018 says every URL is built
  # and parsed by routes.ts — this one is neither.
  Scenario: The Workspace tab has a URL the router does not know
    When I cold-load "/runs/{id}/workspace"
    Then the Workspace tab is selected and its files are listed
    And the page does NOT render the 404 screen
    But parseViewPath(["runs", "{id}", "workspace"]) returns screen "unknown"
    And routes.ts exposes no builder for it

  # ---- Per-tab content ----

  Scenario: Steps lists every roster agent and marks the untaken branches
    Given a completed conditional run with 5 roster agents, 3 dispatched
    When I cold-load "/runs/{id}/steps"
    Then the header reports "3 / 5 agents"
    And 3 rows show a duration and a token count
    And 2 rows are marked "Skipped"
    And dispatched plus skipped equals the roster size
    # FIX-308's guard from the other direction: a composed agent that is never
    # dispatched while the run reports pipeline_complete must fail here.

  Scenario: An agent row is addressable by URL
    When I cold-load "/runs/{id}/steps/{agentId}"
    Then the Steps tab is selected
    And that agent's row is focused or expanded

  Scenario: The starting point shows the brief
    When I cold-load "/runs/{id}/steps"
    Then I see a "Starting point" block containing the run's brief
    And a "SHOW MORE" control when the brief is long

  Scenario: Files groups the deliverable apart from intermediates
    When I cold-load "/runs/{id}/files"
    Then I see a "FINAL OUTPUT" group with exactly one deliverable
    And I see an "AGENT OUTPUTS" group whose count matches its entries
    And I see a "RUN INPUT" group containing "prompt.md"
    And the file total in the header equals the number of listed files
    And I see a "Download All" control

  Scenario: The deliverable reports its own validation state
    When I cold-load "/runs/{id}/files"
    Then the final output row shows its format, its size, and "validated"

  Scenario: Workspace lists raw workspace files and starts unselected
    When I cold-load "/runs/{id}/workspace"
    Then I see the workspace files with their sizes
    And I see "Select a file to view it."
    When I click a file
    Then its content is shown

  Scenario: Audit filters by category
    When I cold-load "/runs/{id}/audit"
    Then the "All" count equals the total number of audit rows
    And the category counts sum to the "All" count
    When I click "Governance"
    Then only governance rows remain

  Scenario: Audit records the human and conditional gates of a gated run
    Given a completed run that passed a human gate and a conditional gate
    When I cold-load "/runs/{id}/audit"
    Then I see a row whose source is "human" naming the gated step
    And I see a row whose source is "conditional" naming the same step
    And each row carries a timestamp and a verdict

  Scenario: Blocked-only narrows the audit to denials
    When I cold-load "/runs/{id}/audit"
    And I enable "Blocked / denied only"
    Then every visible row is a block or a denial
    And a run with no denials shows an empty state, not a blank pane

  Scenario Outline: The preview renderer can be switched
    Given a completed run whose deliverable is "greeting.md"
    When I cold-load "/runs/{id}"
    And I select the renderer "<renderer>"
    Then the pane shows "<result>"

    Examples:
      | renderer | result                                    |
      | Auto     | the rendered markdown                     |
      | Markdown | the rendered markdown                     |
      | Bundle   | the message "No files generated yet"      |
      | HTML     | nothing at all — see the defect below     |
    # Auto resolves to Markdown for a .md. Only four modes appear on this
    # deliverable; Slides needs a deck.

  @defect
  # D-13. Forcing an incompatible renderer produces a blank pane.
  Scenario: Choosing HTML for a markdown deliverable renders nothing
    Given a completed run whose deliverable is "greeting.md"
    When I cold-load "/runs/{id}"
    And I select the renderer "HTML"
    Then the preview pane is empty
    And no message explains why
    # Bundle, on the same file, at least says "No files generated yet". HTML
    # says nothing — the user sees a blank pane and cannot tell whether the
    # deliverable is missing or the renderer is wrong.
    # Expected once fixed: the same courtesy Bundle already extends.

  Scenario: A deck run offers Slides and Full Screen
    Given a completed "ppt_v2" run whose deliverable is "presentation.html"
    When I cold-load "/runs/{id}"
    Then the renderer options include "Slides"
    And I see a "Full Screen" control

  Scenario: Full preview is its own URL
    When I cold-load "/runs/{id}/preview/full"
    Then the deliverable is rendered
    And the run header is still present

  Scenario: The run chat lane accepts a follow-up
    When I cold-load "/runs/{id}"
    Then I see a composer with a textarea named "run-chat-message"
    And I see attach and send controls
    When I type a message and send it
    Then it appears in the transcript

  Scenario: Back to history returns to the list
    When I cold-load "/runs/{id}"
    And I click "Back to history"
    Then I land on "/runs"

  @unverified
  # No run in the dev database has more than one version, so this route was
  # never reached during the capture. Written from the route contract.
  Scenario: A specific run version is addressable
    Given a run with more than one version
    When I cold-load "/runs/{id}/versions/{v}"
    Then that version's deliverable is rendered
    And the version control reports "v{v}"

  Scenario: A live run streams into the same surface
    Given a run that is currently generating
    When I cold-load "/runs/{id}/stream"
    Then I see live progress in the transcript
    And agent rows gain durations as they complete
    And the deliverable card appears once it is delivered
```

## Notes for phase 2

- **Use `tab-thinking` for the Steps tab.** The label and the testid disagree; the
  testid is the stable one.
- `GET /api/runs/{id}` returns `agent_outputs` as a **JSON-stringified array** —
  `JSON.parse` it. Each item carries `agent_id`, `name`, `role`, `output`,
  `duration`, `input_prompt`, `context_sources`, `tool_calls`, `thinking_text`,
  token counts and `model_id`. That is by far the fastest way to assert on what a
  run actually did without fighting the Steps UI.
- Every scenario tagged with a FIX id above is a **known regression**. They should
  be the first tests written in phase 2 — they have all failed in production before
  and every one of them passed its unit tests at the time.
- Do not assert on wall-clock durations or token totals. Assert on their presence
  and on relationships (dispatched + skipped = roster).
