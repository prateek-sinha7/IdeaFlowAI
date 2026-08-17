---
phase: quick-260812-jn9
plan: 01
status: complete
requirements: [ISS-083]
branch: bugfix/spec-revision-context-loss
base_commit: f12d99ae
commit: 0312a0af
files_changed: 3
tasks_completed: 3
duration_min: 14
completed: 2026-08-12
---

# quick-260812-jn9 — Delete the dormant `cycle` prop from ResultCard (ISS-083)

**One-liner:** The spec-revision "cycle N" number now has one producer — the backend narrator's
own text — after deleting the `ResultCard` header's contradicting `cycle ?? 1` FE default and the
prop no production caller ever passed (INV-12 dual implementation removed, nothing wired).

## What changed

| File | Change |
|---|---|
| `frontend/src/components/chat/ResultCard.tsx` | Deleted the `cycle?: number` prop + its doc block, dropped `cycle` from the destructure, replaced the `kind === "spec_revision" ? \`Revising spec — cycle ${cycle ?? 1}\`` ternary with the static `const title = spec?.title ?? "Update";` (S3), corrected the stale file-header doc (S4) |
| `frontend/src/components/chat/ResultCard.test.tsx` | Rewrote the `cycle={3}` self-feeding test into T1 (single-render proof) + T1b (static-header lock), appended T2 (source guard), corrected the `:13` header comment (S5) |
| `frontend/e2e/tests/ts-chat-cards.spec.ts` | Landmine removal (S6): the injected narrator text now carries the cycle number, and the assertion became `toContainText("Revising spec — cycle 2")` + `not.toContainText("cycle 1")`; test name + doc line de-staled |

The header now falls back to `CARD_SPECS.spec_revision.title` (`"Revising spec"`, already at `:83`).
`spec_revision` remains excluded from the inline-render branch, so the card keeps its box chrome
and the header `<p>`.

## Task 1 — the fail-first record (VERBATIM)

Run at base commit `f12d99ae` with **only the test file edited** (`git diff --stat` = 1 file);
`ResultCard.tsx` was untouched. Command: `npx vitest run src/components/chat/ResultCard.test.tsx`
from `frontend/`.

```
 ❯ src/components/chat/ResultCard.test.tsx (13 tests | 4 failed) 47ms
     × labels the deliverable output 'Deliverable' (LOCK-F) and links to Preview 6ms
     × renders the revision cycle exactly once, from the narrator text (ISS-083) 5ms
     × locks the spec_revision header to the static CARD_SPECS title (ISS-083) 2ms
     × holds no dormant `cycle` prop (ISS-083) 1ms

⎯⎯⎯⎯⎯⎯⎯ Failed Tests 4 ⎯⎯⎯⎯⎯⎯⎯
⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯[1/4]⎯

 FAIL  src/components/chat/ResultCard.test.tsx > ResultCard > renders the revision cycle exactly once, from the narrator text (ISS-083)
AssertionError: expected [ <p …(1)></p>, <p></p> ] to have a length of 1 but got 2

- Expected
+ Received

- 1
+ 2

 ❯ src/components/chat/ResultCard.test.tsx:68:18
     66|     );
     67|     const hits = screen.getAllByText(/Revising spec — cycle \d+/);
     68|     expect(hits).toHaveLength(1);
       |                  ^
     69|     expect(hits[0]).toHaveTextContent("Revising spec — cycle 2");
     70|   });
⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯[2/4]⎯

 FAIL  src/components/chat/ResultCard.test.tsx > ResultCard > locks the spec_revision header to the static CARD_SPECS title (ISS-083)
TestingLibraryElementError: Unable to find an element with the text: Revising spec. This could be because the text is broken up by multiple elements. In this case, you can provide a function for your text matcher to make your matcher more flexible.
[... rendered-DOM dump elided ...]
 ❯ src/components/chat/ResultCard.test.tsx:79:19
⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯[3/4]⎯

 FAIL  src/components/chat/ResultCard.test.tsx > ResultCard > holds no dormant `cycle` prop (ISS-083)
AssertionError: expected '"use client";\n\n/**\n * ResultCard —…' not to match /cycle\?:\s*number/

- Expected:
/cycle\?:\s*number/

+ Received:
"\"use client\";
[... full source dump elided ...]
 ❯ src/components/chat/ResultCard.test.tsx:161:21
⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯[4/4]⎯

 Test Files  1 failed (1)
      Tests  4 failed | 9 passed (13)
```

(The `[1/4]` slot in the raw output is the pre-existing deliverable/LOCK-F red — the same
`TestingLibraryElementError: Unable to find an element with the text: Deliverable` throwing at
`:56` that the base commit already had. It is reproduced in the test list above; its DOM dump is
elided here for length.)

**The hard-stop gate cleared, not tripped.** T1's received length was **exactly 2** — the header's
`?? 1` copy plus the narrator body copy. That is the dual-copy model confirmed by execution, which
is the entire evidentiary basis for the deletion. Had it been 0, 1, or a throw, the plan required a
stop; it did not occur. The em dash was verified as U+2014 in every new line before the run
(`ResultCard.tsx:119`, `chat_narrator.py:157` and all authored test lines share the codepoint), so
the length-2 result is not a matcher artefact.

## Gate table — compared by FAILING TEST ID, not by count

| gate | base `f12d99ae` | after `0312a0af` | verdict |
|---|---|---|---|
| ResultCard vitest | `1 failed \| 10 passed (11)` — red = `labels the deliverable output 'Deliverable' (LOCK-F) and links to Preview`, throwing at `:56` | `1 failed \| 12 passed (13)` — **same failing test ID**, same `getByText("Deliverable")` throw, now at `:57` | MATCH (permitted delta; line shift explained below) |
| ts-chat-cards e2e | 3 failed: `:31` / `:57` / `:69`, all in the shared `beforeEach` at `:27`, `getByTestId('run-chat-lane')` element(s) not found | 3 failed: **same 3 test IDs** (`:31` / `:57` / `:75`), same `beforeEach` at `:27`, same locator, same `element(s) not found` | IDENTITY HELD — see below |
| typecheck | 2 errors: `NotificationPanel.fix195.test.tsx(60,7) TS2322`, `useNotifications.fix202.test.tsx(200,13) TS2339` | the **same 2 errors**, byte-identical, no third | MATCH |
| reducer specs (4 files) | 63 passed | 63 passed | MATCH |
| goldens | 10 passed | 10 passed | MATCH |
| import-linter | 4 kept / 0 broken | 4 kept / 0 broken | MATCH |
| narrator backend | 36 passed | 36 passed | MATCH |

I measured the base ResultCard vitest baseline myself before editing (`1 failed | 10 passed (11)`,
throw at `:56`) — it reproduced the plan's recorded value exactly. The goldens and narrator suites
were run separately (not only in the plan's combined form) so both counts are observed, not
inferred from the combined 46.

**The reducer specs holding at 63 passed is the affirmative evidence that we deleted rather than
wired** — `deriveSpecRevisionCount`, `useRunStateStore` and `specRevisionCount` are absent from the
diff, as the rejected proposal required them to be.

## e2e: UNVERIFIABLE-GREEN by execution

Green is unreachable in `ts-chat-cards.spec.ts` regardless of this change: all three tests die in
the shared `beforeEach` at `:27` waiting for `getByTestId('run-chat-lane')`, which is pre-existing
and registered as ISS-076. TS-CHAT-CARDS-02 **never reaches its assertion**. So this gate is
**UNVERIFIABLE-GREEN by execution**, and the honest gate is a before/after identity check.

**Both sides were executed by me, not inherited.** After committing, I restored the three files to
the parent commit (`git checkout HEAD~1 -- <3 files>`, verified by `cycle ??` reappearing at
`ResultCard.tsx:119` and `cycle 1` at e2e `:65`), ran the before-measurement, then restored the
committed state (`git checkout HEAD -- <3 files>`) and confirmed `git status --porcelain` clean.
No `git stash` at any point. This used exactly the two permitted runs of the single permitted
command, `npx playwright test --project=mocked e2e/tests/ts-chat-cards.spec.ts`.

Before (pre-change files on disk):

```
  ✘  3 …ts-chat-cards.spec.ts:31:7 › … TS-CHAT-CARDS-01 a deliverable card is labeled 'Deliverable' …
  ✘  1 …ts-chat-cards.spec.ts:57:7 › … TS-CHAT-CARDS-02 a spec_revision card reads 'Revising spec — cycle N' …
  ✘  2 …ts-chat-cards.spec.ts:69:7 › … TS-CHAT-CARDS-03 a picked file renders a chat-attach-chip …
    Locator: getByTestId('run-chat-lane')
    Error: element(s) not found
    > 27 |     await expect(dashboard.page.getByTestId("run-chat-lane")).toBeVisible();
  3 failed
```

After (committed state):

```
  ✘  2 …ts-chat-cards.spec.ts:31:7 › … TS-CHAT-CARDS-01 a deliverable card is labeled 'Deliverable' …
  ✘  1 …ts-chat-cards.spec.ts:57:7 › … TS-CHAT-CARDS-02 a spec_revision card renders the narrator's revision text …
  ✘  3 …ts-chat-cards.spec.ts:75:7 › … TS-CHAT-CARDS-03 a picked file renders a chat-attach-chip …
    Error: expect(locator).toBeVisible() failed
    Locator: getByTestId('run-chat-lane')
    Expected: visible
    Timeout: 10000ms
    Error: element(s) not found
    > 27 |     await expect(dashboard.page.getByTestId("run-chat-lane")).toBeVisible();
  3 failed
```

**Identity confirmed:** same three tests, same failure site (`beforeEach` `:27`), same locator, same
`element(s) not found`, same count. **No new failure mode** — in particular no syntax or type error
from the S6 edit, which is what this run was there to catch. The only textual differences are the
TS-CHAT-CARDS-02 title (deliberately de-staled) and TS-CHAT-CARDS-03's declaration line moving
`:69 → :75`, a mechanical consequence of S6 adding 6 lines above it. Worker-number ordering differs
between runs; that is scheduler non-determinism, not a result change.

## Deviations from plan

None of substance. Every snippet (S1–S6) was applied verbatim; the fix was not re-derived and the
rejected store-wiring was not revisited. Two line-number expectations in the plan are arithmetically
unsatisfiable given the plan's own snippets — recorded under Findings, not worked around.

One process ordering note: the plan's Task 3 lists "re-measure, then commit". I ran every gate
including the after-e2e **before** committing (so a broken S6 could not reach a commit), committed,
and only then took the before-e2e measurement — because after the commit, reverting and restoring
the three files is exactly reversible and risked nothing. The alternative would have made the
before-measurement either impossible or dependent on `git stash`, which is prohibited.

## Findings for the orchestrator to file

**(a) The mocked e2e suite CAN fabricate the `spec_revision` card client-side.** `mockSse.chatReply({
cardKind: "spec_revision", … })` injects the narrator turn in the browser, bypassing the backend
narrator entirely. So "the backend never emits this card" does **not** imply "no test exercises it" —
which is precisely why a stale assertion could have sat in `ts-chat-cards.spec.ts` asserting a value
only the deleted FE default could produce. Any future reasoning about the dormant card kind must
account for the client-side mock path.

**(b) The pre-existing deliverable/LOCK-F red is open and unowned.**
`ResultCard.test.tsx` → `labels the deliverable output 'Deliverable' (LOCK-F) and links to Preview`
throws `Unable to find an element with the text: Deliverable` (now at `:57`). Cause: KAN-154 moved
`deliverable` into the inline-render branch at `ResultCard.tsx:141`, and that branch renders
`message.content` with no title element, so the LOCK-F label no longer appears anywhere in the DOM.
It matches no row in `ISSUES-REGISTER.md`. Left unrepaired deliberately, per plan. Note this is a
genuine product question, not just a test bug: if LOCK-F requires the run output to be *labelled*
"Deliverable", the inline branch currently violates it.

**(c) New — two plan line-number expectations are self-contradicting.** See Findings below; worth
folding into the planning checklist since both would have read as failures to a literal executor.

## Findings on the plan itself

1. **Task 2 `<done>` and `<hard_prohibitions>` require the pre-existing red at the "same line"
   (`:56`), but the plan's own S5 snippet makes that impossible.** S5 replaces the single comment
   line `:13` with **two** lines, shifting everything below by +1, so the deliverable red lands at
   `:57`. Evidence: base run `❯ …ResultCard.test.tsx:56:19`; after run `❯ …ResultCard.test.tsx:57:19`;
   both `TestingLibraryElementError: Unable to find an element with the text: Deliverable` from the
   identical `expect(screen.getByText("Deliverable")).toBeInTheDocument();`. Test **ID** is identical,
   which is the criterion the plan itself says to use ("compare by FAILING TEST ID, never by count") —
   so I treated the ID as authoritative and the line as derived.

2. **Task 3 requires the e2e to show "the SAME 3 failures (`:31`, `:57`, `:69`)", which S6 also makes
   impossible.** S6 adds 6 lines to TS-CHAT-CARDS-02 (4 comment lines, a changed assertion, plus the
   `not.toContainText`), pushing TS-CHAT-CARDS-03's declaration from `:69` to `:75`. Verified by
   executing both states: before = `:31`/`:57`/`:69`, after = `:31`/`:57`/`:75`, same three test names,
   same `beforeEach` `:27` error. Identity holds by test ID and failure site.

3. Everything else in the plan checked out under execution: the `:96-100` / `:103` / `:117-120` /
   `:16-19` line map was exact; `cycle={` had exactly one repo-wide hit (the rewritten test); the
   em dash is U+2014 in `ResultCard.tsx:119` and `chat_narrator.py:157`; T1's predicted RED length of
   2 was observed; and `frontend/e2e/.report/` is gitignored, so the Playwright runs left the tree
   clean.

## Verification

- `ResultCard.tsx` contains **no** `cycle` prop, **no** destructured `cycle`, **no** `cycle ??`.
  `grep -n cycle` returns only two prose lines (`:19`, `:114`) inside the S3/S4 comments. T2 makes any
  re-introduction a permanent test failure.
- The spec_revision card renders the cycle number exactly once (T1) and its header is the static
  `CARD_SPECS` title (T1b) — both green after the change, both observed red before it.
- The pre-existing deliverable/LOCK-F red is still red, same test ID, unrepaired. ISS-076's
  `beforeEach` is untouched and the 3 e2e failures remain.
- SC-001 guard passes: no workflow-name literal added (greps for `"prototype"`, `od_ppt`,
  `app_builder`, `user_stories`, `ppt_revision` in `ResultCard.tsx` return nothing).
- INV-3 / INV-1 proven, not assumed: goldens 10 passed, import-linter 4 kept / 0 broken, narrator 36
  passed, and `git status --porcelain backend/tests/agents/characterization/golden/` is empty.
- Zero backend files, zero new dependencies, zero `.planning/` register edits, no `git stash`, no
  live/Bedrock run, no full-suite or `--project=live` Playwright run.

## Self-Check: PASSED

- `frontend/src/components/chat/ResultCard.tsx` — FOUND, contains `const title = spec?.title ?? "Update";`
- `frontend/src/components/chat/ResultCard.test.tsx` — FOUND, 13 tests
- `frontend/e2e/tests/ts-chat-cards.spec.ts` — FOUND, asserts `cycle 2` / not `cycle 1`
- Commit `0312a0af` — FOUND in `git log`, contains exactly the 3 files
- `git status --porcelain` — only the untracked `.planning/quick/260812-jn9-…/` docs directory
  (this SUMMARY + the PLAN), which is the orchestrator's to commit
