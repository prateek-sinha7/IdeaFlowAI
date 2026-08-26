# Feature: Keyboard, navigation edges and error boundaries

**Screenshots:** none — see the `@sourced` note in `19-toasts-and-dialogs`. Every
assertion here is read from the component, not confirmed in a browser, except the
Escape behaviour which was verified per-overlay during sweeps 4 and 5.

---

## Keyboard

`_gaps.py` finds **104 keyboard-handler hits across 30 files**: 9 register a
**global** `window` listener, 26 attach a handler prop, and 6 read
`metaKey`/`ctrlKey`/`shiftKey`/`altKey`.

### Escape — verified, and NOT uniform

| Overlay | Escape closes it |
|---|---|
| Account menu | ✅ |
| Notifications panel | ✅ |
| Catalog inspect dialog | ✅ |
| Prototype template detail | ✅ |
| Prototype custom template | ✅ |
| Design-system detail | ✅ |
| Custom design system | ✅ |
| PPT custom template | ✅ |
| Divert workflow picker | ✅ |
| **Add-agent modal** | ❌ **D-07** |

Nine of ten. The tenth is a recorded defect, not an inconsistency to design around.

### Space-to-pan on the canvas — `composer/CanvasView.tsx:427-445`

The canvas advertises **"Hold Space + drag to pan"** in its own UI and implements it
with a global `keydown`/`keyup` pair. It is guarded:

```
isTypingTarget(e.target)  →  INPUT | TEXTAREA | isContentEditable
```

so holding Space while typing in the rail's rename or prompt fields still types a
space. `e.preventDefault()` stops the page also scrolling.

**That guard is the assertion worth having** — it is the kind of thing that breaks
silently and makes a rename field impossible to use.

## Navigation edges

100 in-app navigations exist. Every route in `PAGES.md` was reached by a **cold
`page.goto`**, which deliberately proves cold-load fidelity but proves nothing about
whether the in-app affordances land where they claim.

| Kind | Count | Files |
|---|---:|---|
| `router.push` | 47 | 13 |
| `router.replace` | 31 | 14 |
| `window.open` | 10 | 8 |
| `<Link>` | 6 | 3 |
| `location.href =` | **5** | `app/error.tsx`, `app/global-error.tsx`, `lib/api.ts` |
| `router.back()` | 1 | `DashboardLayout` |

The five `location.href` assignments are the ones that matter: they are **full page
reloads**, not SPA transitions. They reset every piece of client state — including
the theme-independent in-memory caches the run page relies on.

`<Link>` is used in only three places. Everything else navigates through a click
handler, which is why run cards are not links (**D-14**).

## Error boundaries — never rendered in any sweep

| File | Role |
|---|---|
| `app/error.tsx` | route-segment error boundary |
| `app/global-error.tsx` | root boundary, replaces the whole document |

Both recover with a hard `location.href =` reload. Neither has ever been seen. They
are reachable only by a thrown render error, which no seeded data produces.

**This is not hypothetical.** While this file was being written the dev server
returned HTTP 500 for the entire `[...view]` catch-all
(`ReferenceError: require is not defined` from the Turbopack SSR bundle) — precisely
the class of failure these boundaries exist for, and there is no test that says what
the user should see when it happens.

---

```gherkin
Feature: Keyboard

  Scenario Outline: Escape closes an overlay
    Given "<overlay>" is open
    When I press Escape
    Then it closes
    And the URL is unchanged

    Examples:
      | overlay                       |
      | the account menu              |
      | the notifications panel       |
      | the catalog inspect dialog    |
      | the prototype template detail |
      | the custom template modal     |
      | the design-system detail      |
      | the custom design system modal|
      | the divert workflow picker    |
    # Verified individually in sweeps 4 and 5. Do NOT collapse this into "Escape
    # closes any overlay" — the add-agent modal is the exception below.

  @defect
  # D-07, already filed. Restated here so the keyboard contract is in one place.
  Scenario: Escape closes the add-agent modal
    Given the add-agent modal is open on the composer
    When I press Escape
    Then it closes
    # Today it does not, and its only close control has no accessible name.

  @sourced
  Scenario: Holding Space pans the canvas
    Given I am on "/workflows/ppt/canvas"
    When I hold Space and drag
    Then the canvas pans
    And the page itself does not scroll

  @sourced
  Scenario: Space still types a space in a text field
    Given I am on "/workflows/ppt/canvas"
    And focus is in the rail's agent-name input
    When I press Space
    Then a space is typed into the field
    And the canvas does NOT enter pan mode
    # CanvasView guards on INPUT / TEXTAREA / isContentEditable. Without it the
    # rename and prompt fields become unusable — a silent, total break of an
    # editing surface. This is the highest-value keyboard assertion in the suite.

  @sourced
  Scenario: Space-to-pan releases on keyup
    Given I am holding Space on the canvas
    When I release it
    Then pan mode ends
    # Global keydown/keyup pair. A missed keyup leaves the canvas stuck in pan
    # mode with no visible cause.

  @unverified
  Scenario: Modifier shortcuts behave as advertised
    # Six files read metaKey/ctrlKey/shiftKey/altKey and NONE has been exercised:
    # ChatInput, MessageBubble, RunChatLane, WorkflowHistory, IdeaInputPage,
    # WorkflowView. Enumerate what each binds before writing assertions — this is
    # a placeholder marking known-unknown territory, not a test.

  @sourced
  Scenario: Submitting a chat message by keyboard
    Given the run chat composer has text in it
    When I press the send shortcut
    Then the message is sent
    # ChatInput and RunChatLane both read modifier keys; the exact binding
    # (Enter vs Cmd/Ctrl+Enter) was not confirmed. Establish it, then fix this
    # scenario to name the real key.


Feature: Navigation edges

  Scenario: Every route survives a cold load
    # Already covered — PAGES.md reaches all 55 URLs by page.goto. Recorded here
    # so the distinction is explicit: cold-load fidelity is proven, in-app
    # navigation is not.

  @sourced
  Scenario Outline: An in-app affordance lands where its URL claims
    Given I am on "<from>"
    When I activate "<control>"
    Then I land on "<to>"
    And I did NOT do a full page reload

    Examples:
      | from        | control                | to                     |
      | /dashboard  | a catalog card         | that workflow's launch |
      | /runs       | a run row              | that run's detail      |
      | /runs/{id}  | Open in Steps          | /runs/{id}/steps       |
      | /runs/{id}  | Open in Preview        | /runs/{id}             |
      | /workflows  | a saved workflow card  | that workflow's detail |
      | /library    | an agent card          | that agent's drawer    |
    # 47 router.push and 31 router.replace calls exist. This outline is the shape
    # for covering them; phase 2 should extend the table from _gaps.py --full
    # rather than trusting this sample.

  @sourced
  Scenario: Back returns to where I came from
    Given I opened a run from "/runs?type=custom"
    When I activate the lane's back control
    Then I return to run history
    # DashboardLayout has the product's only router.back(). Whether the type
    # filter survives is exactly the kind of thing router.back() gets wrong.

  @sourced
  Scenario Outline: A new-tab affordance opens a new tab
    Given "<surface>"
    When I activate "<control>"
    Then a new browser tab opens on "<target>"

    Examples:
      | surface                  | control            | target                |
      | a template detail modal  | Open in new tab    | the template preview  |
      | a design-system modal    | Open preview in new tab | the system preview |
      | an App Builder preview   | Full Screen        | /preview-fullscreen   |
    # 10 window.open calls across 8 files. The App Builder one deliberately omits
    # noopener so the new tab can read the opener's sessionStorage — asserting
    # noopener there would be asserting a regression (see 16-pages-outside-routes).

  @sourced
  Scenario: A session that cannot be refreshed forces a hard reload to sign-in
    Given my session cannot be refreshed
    When the app makes an authenticated request
    Then the browser performs a FULL page load of the sign-in screen
    # lib/api.ts uses location.href, not router.replace. Client state is wiped.
    # A test that asserts SPA-style navigation here will fail for the wrong
    # reason; assert the reload.


Feature: Error boundaries

  @sourced
  Scenario: A route-level render error is caught and explained
    Given a route whose render throws
    When I load it
    Then app/error.tsx renders instead of a blank page
    And I am offered a way to recover
    # NEVER RENDERED in any sweep. Reachable only by fault injection — phase 2
    # can force it by intercepting a required request and returning malformed
    # data.

  @sourced
  Scenario: Recovering from an error boundary does a full reload
    Given the error boundary is showing
    When I activate its recovery control
    Then the browser performs a full page load
    And I am no longer on the error screen
    # Both boundaries use location.href, not router.refresh(). Every piece of
    # client state is discarded — which is the point, but it must be asserted so
    # nobody "optimises" it into a soft navigation that keeps the broken state.

  @sourced
  Scenario: A root-level failure still renders something
    Given an error that escapes the route boundary
    Then app/global-error.tsx renders a complete document
    And the user is not shown a blank white page

  @sourced
  Scenario: A server 500 does not leave the user on a blank page
    Given the server returns 500 for a route
    When I load it
    Then I am shown an error state, not an empty document
    # Written after observing exactly this: the dev server returned 500 for the
    # entire [...view] catch-all with "ReferenceError: require is not defined".
    # Nothing in the suite said what the user should see. Now something does.
```

## Notes for phase 2

- **Space-to-pan's typing guard is the single highest-value keyboard assertion
  here.** If it regresses, every text field on the canvas silently stops accepting
  spaces, and nothing else in the suite would catch it.
- Enumerate the modifier bindings before writing the `@unverified` shortcut
  scenarios. `python3 tests/integration/capture/_gaps.py --full` prints every hit
  with its file and line; the six modifier files are listed under `shortcuts`.
- **`location.href` vs `router.push` is a real distinction for tests.** Five call
  sites do full reloads. Assert the reload where it happens rather than waiting for
  an SPA transition that will never come.
- The error boundaries need fault injection, not a fixture. Intercepting one required
  API call and returning malformed JSON is the cheapest route in.
