# Feature: Pages outside the routing contract

Five Next.js pages exist that `routes.ts` does not describe. Four were missing from
the first inventory entirely — they were found by enumerating `app/**/page.tsx`
rather than by reading `routes.ts`.

**Screenshots:** `04-workflows/p21` legacy builder · `03-create/` — p13, p14 (legacy wizard redirects) · `10-handoff/` — p49 settings, p50 invalid token · `11-errors/` — p54 quota, p55 bare redirect

```
frontend/src/app/workflow/page.tsx            → /workflow
frontend/src/app/workflow/create/page.tsx     → /workflow/create
frontend/src/app/preview-fullscreen/page.tsx  → /preview-fullscreen
frontend/src/app/handoff/settings/page.tsx    → /handoff/settings
frontend/src/app/handoff/[token]/page.tsx     → /handoff/{token}
```

All five return HTTP 200. ADR-0018 states every URL in the app is built and parsed
by `routes.ts`; only `/workflow/create` is, via the `workflowCreateLegacy` builder.

---

## `/workflow` — a second, older workflow builder

Heading **"VelocityAI — Agent Workflows"**. Its own shell: `Agent Library`, `Back`,
`Close`, `Browse Library`, `Add Agent`, `Run Workflow`, a brief `textarea` and a
file input. Shows `User Stories / 0 agents • ~0 min` and `Workflow Agents (0)`.

This is a **parallel implementation** of the composer with different chrome and
different controls. Nothing in the app links to it. It is reachable by URL by
anyone, and it is not covered by any test.

**Sweep 5 closed the open question about it: the page is broken.** Its `Add Agent`
picker returns "No agents found" for all six categories, so the builder can never
hold a node and `Run Workflow` can never run anything (D-17). It also strands
`SkillManager`, whose only mount root is this page's `AgentNode` — that overlay
cannot be opened by any user, by any route.

## `/preview-fullscreen` — two callers, one path

Documented in its own source comment. It serves:

1. `?runId=...` → redirects to `/runs/{id}/preview/full` (deep-linkable, no opener needed)
2. The App Builder "Full Screen" button, which opens the **bare** path and passes
   files through `sessionStorage["__app_preview__"]`. `window.open` is deliberately
   called *without* `noopener` so the new tab shares the opener's context and can
   read that key.

With neither a `runId` nor a payload it redirects to `/runs`. With `?error=quota` it
renders: **"Project too large for full screen / The generated project exceeds the
browser session storage limit (~5MB). Use the Download ZIP button in the preview
panel to get all files."**

## `/handoff/settings` — an entire uncovered feature

Heading **"Handoff integrations"**. Three sections:

| Section | Contents |
|---|---|
| Install the `/flowin-handoff` slash command | a `curl … \| bash` one-liner + `Copy`; "Idempotent — safe to re-run" |
| GitHub access token | `input[name="github-pat"]`, `Save`; "Needs repo scope. Encrypted at rest, never returned by any API." |
| VelocityAI API keys | `input[name="api-key-name"]`, `Create key`; "Plaintext shown once." |

**This is the most security-sensitive surface in the product** — it stores a GitHub
PAT and mints API keys — and it had no spec, no test and no entry in any inventory
before this sweep.

## `/handoff/{token}` — the IDE handoff landing page

With an invalid token: heading **"Handoff not found"**, body "Handoff not found",
and a `Back to dashboard` link. A valid token was not available to the sweep.

---

```gherkin
Feature: Pages outside routes.ts

  Background:
    Given I am signed in as "qa-admin@flowinqa.com"

  # ---------- /workflow ----------

  @S-16-01
  Scenario: The legacy workflow builder is reachable by URL
    When I cold-load "/workflow"
    Then I see the heading "VelocityAI — Agent Workflows"
    And I see "Browse Library", "Add Agent" and "Run Workflow"
    And I see a brief textarea
    # Nothing in the app links here. It is a parallel implementation of the
    # composer with its own chrome. Recorded so a decision gets made about it
    # rather than it rotting unnoticed.

  @S-16-02
  Scenario: The legacy builder is not the composer
    When I cold-load "/workflow"
    Then I do NOT see the composer header "CUSTOM · COMPOSER"
    And I do NOT see the Simple / Canvas view toggle
    And I do NOT see a "Save workflow" control

  @S-16-03
  @defect
  # D-17. ANSWERED: it does not work. The open question from sweep 2 is closed.
  Scenario: The legacy builder cannot add an agent
    When I cold-load "/workflow"
    And I click "Add Agent"
    Then the picker lists at least one agent
    # Today it returns "No agents found" for EVERY category — All, User Stories,
    # Presentation, Prototype, App Builder, Custom. The builder starts at 0
    # agents and there is no way to add one, so "Run Workflow" can never run
    # anything.
    #
    # This also strands SkillManager, whose only mount root is this page's
    # AgentNode: no node, no "Manage skill" button, so that overlay is
    # unreachable by any route (see 15-overlays).
    #
    # Written as it SHOULD be, so the scenario turns green if the page is fixed
    # and can simply be deleted if the page is removed.

  # ---------- /workflow/create ----------

  @S-16-04
  Scenario Outline: The legacy wizard path redirects to the named create route
    When I cold-load "/workflow/create?mode=<mode>"
    Then I land on "/create/<mode>"
    And I see the wizard for that mode

    Examples:
      | mode      |
      | ppt       |
      | prototype |
    # CORRECTED. The first sweep asserted the legacy path renders the wizard in
    # place, quoting the routes.ts comment that FR-007/T17's redirect was "kept
    # as a builder until that redirect lands". Re-capture with a settle shows the
    # redirect HAS landed and both modes land on the named route. The routes.ts
    # comment is stale; the code is not.

  # ---------- /preview-fullscreen ----------

  @S-16-05
  Scenario: A runId deep-link redirects to the run's full preview
    Given a completed run with a deliverable
    When I cold-load "/preview-fullscreen?runId={id}"
    Then I land on "/runs/{id}/preview/full"
    And the deliverable is rendered

  @S-16-06
  Scenario: The bare path with no payload falls back to run history
    Given sessionStorage has no "__app_preview__" key
    When I cold-load "/preview-fullscreen"
    Then I land on "/runs"
    And I am not left on a blank screen

  @S-16-07
  Scenario: An oversized project explains itself and offers a way out
    When I cold-load "/preview-fullscreen?error=quota"
    Then I see "Project too large for full screen"
    And I am told the project exceeds the ~5MB session storage limit
    And I am directed to the Download ZIP button in the preview panel

  @S-16-08
  @live
  # live: needs an App Builder run with an open preview, so it cannot run in the offline tier.
  @unverified
  Scenario: The App Builder full-screen button hands files over in sessionStorage
    Given an App Builder run whose preview is open
    When I click "Full Screen"
    Then a new tab opens on "/preview-fullscreen"
    And it renders the project from the opener's sessionStorage
    # window.open is called WITHOUT noopener on purpose so the new tab can read
    # the opener's storage. A test that asserts noopener would be asserting a
    # regression.

  # ---------- /handoff/settings ----------

  @S-16-09
  Scenario: Handoff settings offers the install command
    When I cold-load "/handoff/settings"
    Then I see the heading "Handoff integrations"
    And I see an install one-liner for the "/flowin-handoff" slash command
    And I see a "Copy" control for it
    And I am told the install is idempotent and safe to re-run

  @S-16-10
  Scenario: A GitHub token can be saved and is never read back
    When I cold-load "/handoff/settings"
    Then I see a GitHub token field named "github-pat"
    And I am told it needs repo scope
    And I am told it is encrypted at rest and never returned by any API
    And when no token is saved I am told so explicitly

  @S-16-11
  @destructive
  Scenario: A saved GitHub token is not echoed to the client
    Given I save a GitHub token
    When I reload "/handoff/settings"
    Then I am shown that a token exists
    And the token value itself is NOT present anywhere in the response
    # The page claims the token is never returned by any API. Assert it, at the
    # network layer — this is the whole security promise of the field.

  @S-16-12
  @destructive
  Scenario: An API key is shown once and never again
    When I cold-load "/handoff/settings"
    And I create an API key with a name
    Then the plaintext key is shown to me once
    When I reload the page
    Then the key is listed but its plaintext is NOT shown

  @S-16-13
  Scenario: Handoff settings requires authentication
    Given I have no auth token
    When I cold-load "/handoff/settings"
    Then I do not see any token or API key field
    And I end up on the sign-in screen

  @S-16-14
  Scenario: One user cannot see another's handoff credentials
    Given "qa-pro@flowinqa.com" has saved a GitHub token and created an API key
    When I cold-load "/handoff/settings" as "qa-basic@flowinqa.com"
    Then I see no token and no API keys
    # This surface stores a credential that grants repo access. Cross-account
    # isolation is the assertion that matters most in this whole file.

  # ---------- /handoff/{token} ----------

  @S-16-15
  Scenario: An invalid handoff token is refused clearly
    When I cold-load "/handoff/invalid-token"
    Then I see "Handoff not found"
    And I see a way back to the dashboard
    And no handoff content is rendered

  @S-16-16
  @unverified
  Scenario: A valid handoff token opens the handoff workflow
    Given a valid handoff token issued for one of my runs
    When I cold-load "/handoff/{token}"
    Then I see the handoff workflow for that run
    # No valid token was available during the capture sweep. Phase 2 needs a
    # fixture that mints one.

  @S-16-17
  Scenario: A handoff token belonging to another user is refused
    Given a handoff token issued to another user
    When I cold-load it as myself
    Then I do not see that run's contents
```

## Notes for phase 2

- **`/handoff/settings` is the priority in this file.** It stores a GitHub PAT with
  repo scope and mints API keys, and until this sweep it appeared in no inventory,
  no spec and no test. Its three security scenarios (token not echoed, key shown
  once, cross-account isolation) should be written before anything else here.
- `/workflow` needs a product decision, not a test. Either it is a supported
  surface, in which case it needs full coverage, or it is dead and reachable, in
  which case it should be removed. Recorded so the question gets asked.
- `/preview-fullscreen` deliberately omits `noopener`. Do not "fix" that.
