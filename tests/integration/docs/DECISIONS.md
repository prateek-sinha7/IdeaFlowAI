# Decisions taken while you were away

Judgement calls made without asking, and the reasoning behind each. Anything here
is reversible — flag it and I will change it.

Newest first.

---

## D1 — Generated stubs are SKIPPED, never trivially passing

**2026-08-27, building out all 24 modules.**

506 scenarios needed tests. I generated one function per scenario so the
spec↔test link is complete from the start, and every generated stub carries
`@pytest.mark.skip(reason="not yet implemented")`.

**Why:** a generated test that asserts nothing but reports green is worse than no
test at all — it turns a coverage number into a lie, which is exactly the failure
this suite already made twice at spec stage (claimed 100%, measured 49%).
Skipped is honest: the link exists, the work does not.

`docs/PROGRESS.md` counts the three states separately — running, skipped, not
written — so the real figure is always visible.

**If you disagree:** the alternative is to not generate stubs at all and let
`_scenarios.py` report the gap. That loses the per-scenario ledger.

---

## D2 — One login per role, not per scenario

**Your call, implemented as asked.** Recording the mechanism.

Each role signs in **once per session through the real UI**, and Playwright's
`storage_state` replays that session into every later test. At most four logins
for a whole run.

- default: signed in as `admin`
- `@pytest.mark.role("basic")`: that seeded tier
- `@pytest.mark.anonymous`: no session at all

**The auth scenarios use `@pytest.mark.anonymous`** and drive the login form
themselves — a fixture that hides the thing under test proves nothing. So sign-in
is still genuinely exercised, just once rather than 506 times.

---

## D3 — Scenario ids are permanent, and were minted before implementation

Every scenario now carries `@S-NN-MM`, numbered by spec file and position.
`capture/_scenarios.py` enforces the link in both directions.

**Ids never change.** A reworded scenario keeps its id; that is what keeps the
link alive across edits. This is why §12 of `plan.md` (spec drift from the merge)
had to be closed *before* minting — an id minted against a wrong spec would have
been permanent.

---

## D4 — `test-runs/` is never pruned by any code

Your instruction, recorded so nobody adds a cleanup step later. Every run adds a
timestamped folder; nothing rotates or overwrites. Gitignored, so it costs disk
only.

I do clear it between my own verification runs, per your later instruction.

---

## D5 — Screenshot settling is configuration, not per-test sleeps

`framework/settings.py` holds every capture knob. `BUSY_SELECTORS` is the list
that grows: when a new spinner appears in a screenshot, it goes there rather than
a `sleep()` landing in a test.

`networkidle` is deliberately never used — the Next.js dev server holds an open
HMR websocket, so the network is never idle and that wait would burn its full
timeout on every shot.

---

## Open questions for you

Nothing blocking. These are the calls I would like confirmed:

1. **`SandboxTab` has no testids** (1354 lines, zero `data-testid`, zero
   `aria-label`). Its 11 scenarios select on visible text and are brittle by
   construction. Adding testids is an app change, so I did not make it. See
   `GAPS.md` § Workspace tab.
2. **Fixture-blocked scenarios stay skipped** with the blocker named — a
   `waiting_for_user` run, a valid handoff token, a multi-version family, a
   `hexaware` account, a second account's session. Each needs seed data that does
   not exist. `PROGRESS.md` lists exactly which.
3. **Responsive breakpoints** remain the one surface with no spec at all. Needs
   target viewports agreed before it can be written.

---

## D6 — Commits are local; push needs your credentials

`git push origin feat/integration-tests` fails with
`could not read Username for 'https://gitlab.com'`. No credential helper is
configured for this remote in this worktree, and I will not store one.

Everything is committed locally on `feat/integration-tests`. Run the push
yourself when you are back:

```
git push origin feat/integration-tests
```
