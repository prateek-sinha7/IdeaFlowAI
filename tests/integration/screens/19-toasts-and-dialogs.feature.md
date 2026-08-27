# Feature: Toasts, native dialogs and destructive confirms

**Screenshots:** none — every surface here is transient or destructive, and the dev
server was returning HTTP 500 for the whole `[...view]` catch-all when this file was
written. Every assertion below is **derived from source**, not from a capture, and is
tagged `@sourced` for that reason.

> **`@sourced`** means: the selector and the copy are read from the component, the
> behaviour is not yet visually confirmed. Phase 2 should verify each one on first
> run and drop the tag. This is the honest state — it is not the same standard as the
> capture-verified specs elsewhere in this suite.

---

## Why this file exists at all

Toasts are the most common cause of flaky end-to-end tests anywhere. They appear
late, leave on a timer, and float over the control a test is about to click. Five
components in this product raise them and, before this file, **not one scenario
mentioned a toast**.

Native `window.alert` is worse: a browser dialog **stalls Playwright until it is
handled**. Six calls exist across four components. A phase-2 test that downloads a
file and does not register a dialog handler will hang rather than fail.

---

## Run-completion toast — `components/ui/CompletionToast.tsx`

| | |
|---|---|
| Container | `div.fixed.bottom-6.right-6.z-\[100\]` — bottom-right stack, `pointer-events-none` |
| Auto-dismiss | **7000 ms**, per toast, from mount |
| Stacking | multiple toasts stack vertically, animated with `AnimatePresence mode="popLayout"` |

| Status | Title | Extra control |
|---|---|---|
| `completed` | **"Run completed"** | `Open` → the run's preview |
| `failed` | **"`<Workflow label>` failed"** | none |

Body line is the run title, truncated. A dismiss `X` sits top-right of each toast.

The container is `pointer-events-none` and each toast re-enables
`pointer-events-auto` — so a click that misses a toast passes through to the page
beneath it.

## Admin toasts — `app/admin/page.tsx`

| | |
|---|---|
| Auto-dismiss | **3500 ms** — *different from the completion toast's 7000 ms* |
| Kinds | `success`, `error` |

Verbatim messages:

| Action | Message |
|---|---|
| Tier changed | `Tier updated to <Plan label>` |
| Admin granted | `Admin access granted` |
| Admin removed | `Admin access removed` |
| User created | `User <email> created` |
| User deleted | `User deleted` |
| Load failure | `Failed to load users` |
| Create failure | the server's error message, or `Failed to create user` |
| Delete failure | `Failed to delete user` |

**Two different auto-dismiss timeouts in one product** (3500 and 7000). Any shared
"wait for toast to clear" helper must take the timeout as a parameter.

## Delete-user confirm — an overlay no sweep captured

`/admin` has a per-row **`aria-label="Delete <email>"`** control that opens a
confirm dialog. It was missed by every sweep because the earlier enumeration looked
for `role="dialog"`, and this one is a bare `fixed inset-0` layer.

| | |
|---|---|
| Heading | **"Delete user?"** |
| Body | "This will permanently delete the user and all their data. This cannot be undone." |
| Controls | `Cancel`, `Delete` |
| Scrim | clicking it cancels |

This is **the most destructive control in the product** and it had no spec.

## Native `window.alert` — 6 calls, 4 components

| Component | Message |
|---|---|
| `preview/PPTPreview.tsx:108` | `Download failed. Please try again.` |
| `preview/PreviewPanel.tsx:1299` | `Download failed. Please try again.` |
| `preview/AppBuilderPreview.tsx:449` | `Failed to generate ZIP. Please try downloading files individually.` |
| `results/FilesTab.tsx:603` | `Failed to generate ZIP.` |
| `results/FilesTab.tsx:640` | `PPTX export failed. Try the Download PPTX button in the preview.` |
| `results/FilesTab.tsx:643` | `PPTX export failed.` |

All six are **failure paths on download or export**. None is reachable with healthy
fixtures, which is exactly why a test suite meets them unprepared.

---

```gherkin
Feature: Toasts

  @S-19-01
  @sourced
  Scenario: A completed run raises a toast with a way into the result
    Given a run I started is in progress
    When it completes
    Then a toast appears in the bottom-right
    And its title reads "Run completed"
    And its body is the run's title
    And it offers "Open"
    When I activate "Open"
    Then I land on that run's preview

  @S-19-02
  @sourced
  Scenario: A failed run names the workflow in the toast
    Given a run I started is in progress
    When it fails
    Then a toast appears titled "<Workflow label> failed"
    And it offers NO "Open" control
    # Only the success toast carries an Open affordance.

  @S-19-03
  @sourced
  Scenario: A completion toast dismisses itself after 7 seconds
    Given a completion toast is showing
    When 7 seconds pass without interaction
    Then it is gone
    # Hard-coded 7000ms. A test that waits for it must exceed that; a test that
    # asserts its presence must run within it.

  @S-19-04
  @sourced
  Scenario: A toast can be dismissed early
    Given a completion toast is showing
    When I activate its dismiss control
    Then it is gone immediately

  @S-19-05
  @sourced
  Scenario: Toasts stack rather than replace
    Given two of my runs complete close together
    Then two toasts are shown, stacked
    And dismissing one leaves the other

  @S-19-06
  @sourced
  Scenario: A toast does not block the page beneath it
    Given a toast is showing
    When I click a control in the region the toast container covers but the toast
         itself does not
    Then that control receives the click
    # The container is pointer-events-none; only each toast re-enables pointer
    # events. Worth pinning — it is what stops toasts eating clicks.

  @S-19-07
  @sourced
  Scenario Outline: Admin actions confirm themselves by toast
    Given I am signed in as an admin on "/admin"
    When I perform "<action>"
    Then a success toast reads "<message>"

    Examples:
      | action                  | message                       |
      | change a user's tier    | Tier updated to <Plan label>  |
      | grant admin access      | Admin access granted          |
      | remove admin access     | Admin access removed          |
      | create a user           | User <email> created          |
      | delete a user           | User deleted                  |

  @S-19-08
  @sourced
  Scenario: An admin failure is reported, not swallowed
    Given the backend rejects a tier change
    When I attempt it
    Then an error toast is shown carrying the server's message

  @S-19-09
  @sourced
  Scenario: The two toast families use different timeouts
    Then an admin toast clears after 3500ms
    And a run-completion toast clears after 7000ms
    # Two timeouts in one product. Any shared wait helper must be parameterised;
    # a hard-coded 7000 will make every admin assertion flaky-slow, and a
    # hard-coded 3500 will make every completion assertion flaky-fast.


Feature: Destructive confirms

  @S-19-10
  @sourced
  @destructive
  Scenario: Deleting a user requires confirmation
    Given I am signed in as an admin on "/admin"
    When I activate "Delete <email>" on a user's row
    Then a dialog headed "Delete user?" opens
    And it warns the deletion is permanent and cannot be undone
    And it offers "Cancel" and "Delete"

  @S-19-11
  @sourced
  @destructive
  Scenario: Cancelling a delete leaves the user intact
    Given the "Delete user?" dialog is open
    When I activate "Cancel"
    Then the dialog closes
    And the user is still listed

  @S-19-12
  @sourced
  @destructive
  Scenario: Clicking the scrim cancels the delete
    Given the "Delete user?" dialog is open
    When I click the scrim outside the dialog
    Then the dialog closes without deleting

  @S-19-13
  @sourced
  @destructive
  Scenario: Confirming removes the user and says so
    Given the "Delete user?" dialog is open
    When I activate "Delete"
    Then the user is removed from the table
    And a success toast reads "User deleted"
    And the TOTAL USERS count decreases by one
    # THE most destructive control in the product. It needs its own disposable
    # fixture user and must never run against a shared dev database.

  @S-19-14
  @sourced
  Scenario: An admin cannot delete themselves into lockout
    Given I am the only admin
    When I open the delete dialog for my own account
    Then I am prevented from removing the last admin
    # UNVERIFIED as a guarantee — no such guard was found in app/admin/page.tsx.
    # Written as a question for the product owner: if it does not exist, an admin
    # can delete the last admin account and lock everyone out of /admin.


Feature: Native browser dialogs

  @S-19-15
  @sourced
  Scenario Outline: A failed download reports itself through window.alert
    Given a run whose "<surface>" download will fail
    When I trigger the download
    Then a NATIVE browser alert appears reading "<message>"

    Examples:
      | surface           | message                                                        |
      | PPT preview       | Download failed. Please try again.                             |
      | preview panel     | Download failed. Please try again.                             |
      | App Builder ZIP   | Failed to generate ZIP. Please try downloading files individually. |
      | Files tab ZIP     | Failed to generate ZIP.                                        |
      | Files tab PPTX    | PPTX export failed.                                            |

  @S-19-16
  @sourced
  Scenario: Every test that can trigger a download registers a dialog handler
    Given a phase-2 test that touches a preview or the Files tab
    Then it registers a dialog handler before acting
    # NOT a product assertion — a harness requirement, recorded here because
    # this is where someone will look. Playwright BLOCKS on a native dialog until
    # it is handled: an unhandled alert hangs the run rather than failing it.
    # page.on('dialog', d => d.dismiss()) in the shared fixture is enough.

  @S-19-17
  @sourced
  Scenario: Download failures are the only native dialogs in the product
    Then no window.confirm or window.prompt is used anywhere
    # Confirmed by source enumeration: 6 alert() calls, no confirm(), no prompt().
    # Destructive confirmation is done with the in-app dialog above instead, which
    # is the better pattern — pin it so nobody reintroduces window.confirm.
```

## Notes for phase 2

- **Register a global dialog handler in the shared fixture, first.** It costs one
  line and prevents a class of hangs that look like infrastructure failure.
- Toast assertions need a **time budget, not a fixed wait**: 3500ms for admin,
  7000ms for completions. Prefer waiting for the toast to *appear* and asserting its
  text immediately, rather than reasoning about when it leaves.
- The delete-user scenarios are the only truly irreversible ones in this suite. They
  need a fixture user created in the same test and must be excluded from any run
  against a shared database.
- Every scenario here is `@sourced`. Verify on first run, then drop the tag — do not
  let source-derived assertions masquerade as capture-verified ones.
