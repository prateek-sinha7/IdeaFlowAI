# Feature: Errors, fallbacks and edge routes

What the product does when a URL is wrong, a resource is missing, or a session has
gone.

**Screenshot:** `39-unknown-route.png`

---

## The 404 screen

Reached by anything `parseViewPath` classifies as `unknown`.

| Region | Content |
|---|---|
| Brand | VelocityAI |
| Eyebrow | `IT HAPPENS` |
| Heading | "Page not found." |
| Body | "This URL doesn't exist. Let's get you back on track to shipping faster with your agent workforce." |
| Chips | `Lost?` `Typo?` `Moved.` |
| Code | `404` / "Not found" |
| Explanation | "The page you're looking for doesn't exist or has been moved." |
| Prompt | "Here are your options to get back on track:" |
| Actions | `Back to dashboard`, `Create a workflow`, `Sign in` |

It renders **without the app shell** and offers `Sign in` even to an
already-authenticated user — the screen does not know the auth state.

---

## Routes that parse to `unknown`

From reading `parseViewPath`, these all land on the 404 screen:

| Route | Why |
|---|---|
| ~~`/settings`~~ | parses to `unknown`, but **redirects to `/settings/profile`** — the user never sees the 404 |
| `/workflows/{id}/{anything-else}` | not `canvas`, `edit` or `run` |
| `/runs/{id}/{anything-else}` | not a known subpath |
| `/library/{type}` with < 3 segments | intercepted by `next.config.ts` redirects first |
| `/library/{unknown-type}/{slug}` | type is not agents/skills/hooks |
| anything else | the final fallthrough |

`/runs/{id}/workspace` **should** be in this list by the parser's logic — and is —
yet renders correctly anyway. That is D-02, and it is specified in
`07-run-detail.feature.md` rather than here.

---

```gherkin
Feature: Errors and fallbacks

  Scenario: An unrecognised URL shows the 404 screen
    Given I am signed in
    When I cold-load "/this-route-does-not-exist"
    Then I see "Page not found."
    And I see the code "404"
    And I see the actions "Back to dashboard", "Create a workflow" and "Sign in"
    And the main app nav is not rendered

  Scenario: The 404 offers a way back that works
    Given I am on the 404 screen
    When I click "Back to dashboard"
    Then I land on "/dashboard"

  Scenario: The 404 create action reaches the composer
    Given I am on the 404 screen
    When I click "Create a workflow"
    Then I reach a workflow creation surface

  @defect
  # Minor. The 404 screen offers "Sign in" regardless of auth state — it is
  # rendered outside the shell and does not read the session. Harmless today
  # (the link lands on /login, which bounces an authenticated user onward), but
  # it is a confusing thing to show someone who is already signed in.
  Scenario: The 404 offers Sign in to an already-authenticated user
    Given I am signed in
    When I cold-load "/this-route-does-not-exist"
    Then I see a "Sign in" action
    # Expected once fixed: an authenticated user is not offered Sign in.

  Scenario Outline: Malformed routes fall back rather than crash
    Given I am signed in
    When I cold-load "<route>"
    Then I see the 404 screen
    And no unhandled error is logged to the console

    Examples:
      | route                                  |
      | /workflows/some-id/nonsense            |
      | /runs/some-id/nonsense                 |
      | /library/widgets/some-slug             |
      | /create/                               |

  Scenario: A bare /settings redirects to Profile
    Given I am signed in
    When I cold-load "/settings"
    Then I land on "/settings/profile"
    # CORRECTED. The first sweep read parseViewPath, saw `unknown`, and wrote
    # the opposite assertion — that /settings must NOT redirect. Captured
    # directly, it does. The parser's return value and the user's destination
    # are two different things.

  Scenario: Legacy library list URLs are redirected, not 404'd
    Given I am signed in
    When I cold-load "/library/agents"
    Then I land on the library list with the Agents tab selected
    And I do NOT see the 404 screen
    # next.config.ts intercepts the legacy 2-segment shape before it reaches
    # parseViewPath, which would otherwise classify it as unknown.

  # ---- Missing and forbidden resources ----

  Scenario: A run id that does not exist falls back to the generic 404
    Given I am signed in
    When I cold-load "/runs/00000000-0000-0000-0000-000000000000"
    Then I see the generic 404 screen
    And I am not shown a blank pane or a spinner that never resolves
    # Captured: the backend answers 404 and the client renders the same
    # "Page not found." screen as an unparseable URL. The user is never told
    # the RUN is missing — only that the page is.

  Scenario: A workflow id that does not exist falls back to the generic 404
    Given I am signed in
    When I cold-load "/workflows/00000000-0000-0000-0000-000000000000"
    Then I see the generic 404 screen

  @defect
  # Three distinct failures — an unparseable URL, a missing run, a missing
  # workflow — render one byte-identical screen. A test cannot tell them apart
  # from the DOM, so every such scenario must assert on the URL it navigated
  # from. Recorded as an observation, not a demand to change it.
  Scenario: Missing-resource errors are indistinguishable from a bad URL
    Given I am signed in
    When I cold-load "/this-route-does-not-exist"
    And I cold-load "/runs/{nonexistent-uuid}"
    And I cold-load "/workflows/{nonexistent-uuid}"
    Then all three render the same "Page not found." screen
    And none of them names the resource that was missing

  @defect
  # D-12. Asking for a version that does not exist silently serves v1.
  Scenario: A nonexistent artifact version falls back to v1 without saying so
    Given a completed run whose artifact has only version 1
    When I cold-load "/runs/{id}/versions/99"
    Then the artifact is rendered
    And the version control reads "Version v1"
    And the URL still reads "/versions/99"
    And nothing tells me the version I asked for does not exist
    # Expected once fixed: either a not-found state, or a visible notice that
    # the requested version was unavailable and v1 was served instead.

  Scenario: An oversized full-screen preview explains itself
    When I cold-load "/preview-fullscreen?error=quota"
    Then I see "Project too large for full screen"
    And I am told the project exceeds the ~5MB session storage limit
    # The message names the Download ZIP button but does not link to it, and
    # the page offers no navigation at all — browser Back is the only way out.
    # There is also no heading element: match on text, not getByRole('heading').

  Scenario: Another user's run is not readable
    Given a run owned by "qa-pro@flowinqa.com"
    When I cold-load that run's URL as "qa-basic@flowinqa.com"
    Then I do not see its contents
    And I am shown a not-found or forbidden state
    # FIX-309's UI half. previous_run.py ran assert_owns AFTER
    # _seed_existing_artifact, on the belief that the helper was
    # parent-independent — the Concierge fallback had since added a
    # read_parent_file call inside it, so a parent sandbox was read before
    # ownership was established. Assert ownership from the front door too.

  Scenario: A run file cannot be fetched across an ownership boundary
    Given a run owned by another user
    When I request one of its files with my own token
    Then the response is a 403 or a 404
    And the file's contents are not returned

  # ---- Auth failure modes ----

  Scenario: A request with no credentials is answered 401, not 403
    When I call an authenticated API endpoint with no Authorization header
    Then the response status is 401
    # FIX-311. FastAPI's stock HTTPBearer raises 403 on a missing header while
    # every other auth failure in dependencies.py answers 401, so the one case
    # that meant "you never signed in" was the one that looked like "you are
    # signed in but not allowed". bearer_scheme is subclassed to fix it.

  Scenario: A request with a malformed token is answered 401
    When I call an authenticated API endpoint with a non-Bearer header
    Then the response status is 401

  Scenario: An expired session is recovered once before being surrendered
    Given my access token has expired but is refreshable
    When the app makes an authenticated request
    Then it refreshes once and the request succeeds
    And I am NOT sent to the sign-in screen
    # ADR-0024.

  Scenario: An unrefreshable session ends at sign-in with an explanation
    Given my session cannot be refreshed
    When the app makes an authenticated request
    Then I land on "/login?expired=true"
    And I see "Your session expired. Please sign in again."

  # ---- Network and backend failure ----

  Scenario: A backend outage is reported, not swallowed
    Given the backend is unreachable
    When I cold-load "/dashboard"
    Then I am shown an error state
    And the page does not sit on a spinner indefinitely

  Scenario: A failed run is presented as failed
    Given a run that failed
    When I open its detail surface
    Then its status reads as failed
    And I can still reach its Steps and Audit tabs to see why
```

## Notes for phase 2

- **Drive the auth scenarios at the API**, not through the UI. FIX-311 was a
  status-code difference that no UI assertion would have distinguished — both 401
  and 403 render the same screen.
- The cross-ownership scenarios need two accounts and a run created by each. They
  are the only authorization coverage in this suite; do not drop them for being
  slow.
- "no unhandled error is logged to the console" is worth wiring globally, not just
  in the malformed-route scenario — a console error listener on every test costs
  nothing and catches a class of bug nothing else here looks for.
