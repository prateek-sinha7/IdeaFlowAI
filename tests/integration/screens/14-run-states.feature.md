# Feature: Run lifecycle states

The run detail surface changes shape with the run's status. Sweep 1 captured only
`completed` and wrote the other states from the route contract; sweep 2 captured
them and found the shape differs more than expected.

**Screenshots:** `42`–`48`, `17`–`23`
**Statuses observed:** `completed`, `failed`, `cancelled`, `diverted`, `generating`

---

## The shape per status

| Status | Tabs | Header actions | Resume affordances |
|---|---|---|---|
| completed | 5 (Preview first) | Version, Share, Download | — |
| **failed** | **4 — no Preview** | Version, Share, Download | `Reopen & fix from the failed step`, `Edit brief & run again` |
| cancelled | 5 | Version, Share, Download | `Run Again` |
| diverted | 5 | Version, Share, Download | `Start a new run` |
| generating | 5 (forced to Steps) | `Stop` | — |

**A failed run has no Preview tab at all** — there is no deliverable to preview, so
the tab is not rendered rather than rendered empty. Any test that indexes tabs
positionally breaks on a failed run.

## Per-status detail

**failed** — a "What went wrong" panel listing the failed agents and the reason
("The model rejected this request."), then "Resume options". The version badge reads
`v1 · partial`. The lane summary reads `Run failed · <agent>` and the meta line
`23s · 1/4 agents · 37.4K tokens`.

**cancelled** — banner `CANCELLED` / "Cancelled by you" / "The run was stopped.
Click Run Again to resume from where it left off." The Preview pane reads "This run
was cancelled / The run was stopped before producing a deliverable. / **Open the
Thinking tab to view details.**" — see **D-08**, there is no Thinking tab.

**diverted** — status `Diverted`, meta `2/3 agents`, action `Start a new run`,
Preview reads "Output will appear here".

**generating** — status `Running`, a `Stop` button, the mini-map showing `1 / 4`,
and a streaming indicator `<agent> · streaming`. The deliverable shows `v1 draft`.

## Audit is richer than sweep 1 suggested

A failed run's Audit tab carries a full statistics header that a completed run's
smaller trail did not surface:

```
16 Checks · 16 Passed · 0 Warnings · 0 Blocked · 0 Denied · 1 Secret scans
Gate 15 · Security 1
0 blocked · 0 denied · 0 critical — run passed all governance gates.
```

Row sources seen: `audit logger — before step`, `— after step`, `— tool call`,
`— tool result`, `Secret scan — scanned before write`, `human <stepId>`,
`conditional <stepId>`. Categories: `All`, `Governance`, `Security`, `Activity`,
plus a `Blocked / denied only` toggle and `Export`.

---

```gherkin
Feature: Run states

  Background:
    Given I am signed in as "qa-admin@flowinqa.com"

  Scenario: A failed run explains itself and offers a way forward
    Given a run whose status is "failed"
    When I cold-load its detail URL
    Then the status reads "Failed"
    And I see a "What went wrong" panel naming the failed agents
    And I see a reason for the failure
    And I see "Reopen & fix from the failed step"
    And I see "Edit brief & run again"
    And the version badge indicates a partial result

  Scenario: A failed run has no Preview tab
    Given a run whose status is "failed"
    When I cold-load its detail URL
    Then the tab strip contains Steps, Files, Workspace and Audit
    And it does NOT contain Preview
    # There is no deliverable, so the tab is absent rather than empty. Never
    # index the run tab strip positionally — its length is status-dependent.

  Scenario: A cancelled run offers to resume
    Given a run whose status is "cancelled"
    When I cold-load its detail URL
    Then the status reads "Cancelled"
    And I am told it was cancelled by me
    And I see a "Run Again" control
    And I am told it will resume from where it left off

  @defect
  # D-08. Copy points at a tab that does not exist. The tab is labelled Steps;
  # only its testid still says thinking.
  Scenario: The cancelled empty-state names a tab that does not exist
    Given a run whose status is "cancelled"
    When I cold-load its detail URL
    Then the Preview pane reads "Open the Thinking tab to view details."
    And no tab labelled "Thinking" exists
    # Expected once fixed: the copy says "Steps".

  Scenario: A diverted run points at its continuation
    Given a run whose status is "diverted"
    When I cold-load its detail URL
    Then the status reads "Diverted"
    And I see a "Start a new run" control
    And the Preview pane reads "Output will appear here"

  Scenario: A live run streams and can be stopped
    Given a run whose status is "generating"
    When I cold-load its detail URL
    Then the status reads "Running"
    And I see a "Stop" control
    And the mini-map shows completed-of-total agents
    And the currently executing agent is marked as streaming
    And the deliverable is marked as a draft

  @defect
  # D-06. The highest-value routing defect found in sweep 2. Every tab URL of a
  # running run is overridden to /stream + Steps. The same URLs work once the run
  # completes, so the override is status-dependent, not route-dependent.
  Scenario Outline: A live run cannot deep-link any tab
    Given a run whose status is "generating"
    When I cold-load "<url>"
    Then the URL becomes "/runs/{id}/stream"
    And the selected tab is "Steps", not "<tab>"

    Examples:
      | url                  | tab       |
      | /runs/{id}/audit     | Audit     |
      | /runs/{id}/files     | Files     |
      | /runs/{id}/steps     | Steps     |
    # Expected once fixed: each URL selects its own tab while the run streams.

  Scenario: The same tab URLs work once the run finishes
    Given a run that has completed
    When I cold-load "/runs/{id}/audit"
    Then the URL stays "/runs/{id}/audit"
    And the Audit tab is selected
    # The control for the scenario above. Both must be in the suite or the
    # defect reads as "tab routing is broken" rather than "it is broken while
    # a run is live".

  Scenario: A failed run's audit reports its governance totals
    Given a run whose status is "failed"
    When I open its Audit tab
    Then I see counts for Checks, Passed, Warnings, Blocked, Denied and Secret scans
    And Passed + Warnings + Blocked + Denied equals Checks
    And the Gate and Security counts sum to Checks

  Scenario Outline: Audit categories filter the trail
    Given a completed run with governance records and no security records
    When I open its Audit tab
    And I select the category "<category>"
    Then "<result>"

    Examples:
      | category   | result                                            |
      | All        | every record is listed                            |
      | Governance | only gate records are listed                      |
      | Security   | the empty state "No records match the active filters." is shown |
      | Activity   | the empty state "No records match the active filters." is shown |

  Scenario: A secret scan appears as a security record
    Given a run whose agents wrote files
    When I open its Audit tab and select "Security"
    Then I see a "Secret scan — scanned before write" record
    And its severity is SECURITY

  Scenario Outline: Run history shows the right status chip
    Given runs in several states
    When I cold-load "/runs"
    Then a "<status>" run's row reads "<chip>"

    Examples:
      | status     | chip      |
      | completed  | Done      |
      | failed     | Failed    |
      | cancelled  | Cancelled |
      | diverted   | Diverted  |
      | generating | Running   |

  @unverified
  # NOT CAPTURED. No run in the dev database is parked at a human gate, and
  # reaching that state requires launching a real LLM run — real cost, and it
  # creates a gate a human must answer. Written from adjacent evidence: the
  # cancelled run at capture/47 still shows the clarify prompt and its
  # "Answer in Steps" affordance, so the surface is known even though the live
  # state was not reached.
  Scenario: A run parked at a human gate is answerable
    Given a run whose status is "waiting_for_user"
    When I cold-load its detail URL
    Then I see the clarification prompt
    And I see an "Answer in Steps" affordance
    When I click the Steps tab and back to Preview
    Then the prompt is STILL present and still answerable
    # This is the FIX-302 reproduction and the single most valuable scenario in
    # the whole suite. Phase 2 must create this fixture deliberately.
```

## Notes for phase 2

- **Fixture creation is the blocker here.** Four of the six states can be found in
  any populated dev database; `waiting_for_user` must be created on purpose, and
  `generating` is a race unless you launch and assert immediately.
- Never index the run tab strip positionally — a failed run has four tabs, every
  other state has five.
- The D-06 scenario and its control ("the same URLs work once finished") belong
  together. Alone, either one misdescribes the bug.
