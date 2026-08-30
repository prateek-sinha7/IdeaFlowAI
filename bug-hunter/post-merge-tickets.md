# Post-merge tickets — ready to hand out

Companion to `post-merge-issues.md`, which carries the evidence and the
provenance for every claim here. This file is the work list: each ticket says
where, what, how to verify, and what not to touch.

Baseline is merge commit `90ec542a0` on `feat/conditional-gates`.

**Two rules for everyone taking a ticket:**

1. **Never bend a test to match wrong behaviour.** Every ticket below states
   which side is wrong — app or test. If you find the ticket has it backwards,
   stop and say so; do not "make it pass".
2. Run tests **one file at a time**. The full integration sweep takes 55
   minutes and needs the dev server; do not run it to check a one-line fix.

Commands used throughout:

```
# integration (from tests/integration/e2e, dev server must be up)
.venv/bin/python -m pytest <path>::<test> -q

# backend (from backend/)
../venv/bin/python -m pytest <path>::<test> -q

# frontend (from frontend/)
npx vitest --run <path>
```

---

# TIER 1 — DONE 2026-08-31 (12 failures) — kept for the record

## T1-01 · page.tsx catch-block count pin is stale
**Effort:** 2 min · **Side:** test · **From:** this merge

`frontend/src/app/[...view]/workflowDetailCatch.source.test.ts:84`

`feat/bug-hunter` added two more call sites of the narrowed pattern and left
the pin at 3. Counts verified: pre-merge 3, bug-hunter 5, merged 5.

- Change `expect(occurrences).toBe(3)` → `toBe(5)`.
- Update the comment above it (lines 81-82) to name the two new sites — grep
  `page.tsx` for `if (err instanceof ApiError && (err.status === 403 || err.status === 404)) {`
  and list all five.

**Verify:** `npx vitest --run src/app/[...view]/workflowDetailCatch.source.test.ts`

**Do NOT** change `page.tsx`. More narrowed catches is the desired direction.

---

## T1-02 · four backend count pins moved by spec 018
**Effort:** 15 min · **Side:** test · **From:** pre-existing on `feat/conditional-gates`

`playwright_smoke_test` (added by `bc0a0366e`, spec 018) is the 30th manifest
and the 25th dispatchable pipeline. Each pin's own comment records the last
bump — follow that convention and record this one the same way.

| file:line | now | should be |
|---|---|---|
| `backend/tests/agents/test_compiled_plan_runs.py:109` | `== 24` | `== 25` |
| `backend/tests/agents/test_compiled_plan_runs.py:119` | `== 24` | check — only :109 failed |
| `backend/tests/agents/test_manifest_coverage.py:66` | `== 29` | `== 30` |
| `backend/tests/agents/test_model_pricing.py:103` | `== 8` | `== 9` |
| `backend/tests/unit/test_skills_catalog_hygiene.py:62` | `== 185` | `== 186` |

For the first two, update the docstrings that read *"Went 23 -> 24 with spec
017's ``ppt_v2``"* to name spec 018's `playwright_smoke_test`.

**Before bumping each one, confirm WHAT was added.** These pins exist to make
an unnoticed addition impossible; bumping without looking defeats them. For
`test_model_pricing` and `test_skills_catalog_hygiene`, identify the 9th model
and the 186th skill by name and put it in the comment.

**Verify:** run each file individually.

---

## T1-03 · share button was renamed
**Effort:** 5 min · **Side:** test · **From:** pre-existing (`b69f25696 feat(share)`)

`tests/integration/e2e/suites/15_overlays/test_overlays.py:382`

```python
share = page.get_by_label("Copy a link to this run")   # gone
```

The button is now `aria-label="Share this run"`. Update the locator and
re-read the rest of the test — the share feature gained a real flow, so the
"copies a link rather than opening a dialog" assertion may need revisiting
against what Share actually does now.

**Verify:** `pytest suites/15_overlays/test_overlays.py::test_share_copies_a_link_rather_than_opening_a_dialog -q`

---

## T1-04 · API-key test reports a leak that did not happen
**Effort:** 15 min · **Side:** test · **From:** pre-existing

`tests/integration/e2e/suites/16_pages_outside_routes/test_pages_outside_routes.py:347`

```python
secrets = [s for s in re.findall(r"\b[A-Za-z0-9_\-]{24,}\b", shown) if name not in s]
```

The pattern matched `validator-handoff-fixture` — the *name* of a revoked key
left on the page by an earlier run — and then "found" it after reload. No
plaintext key was ever re-shown.

- Snapshot the page text BEFORE creating the key and subtract those tokens, or
- anchor on the real key shape (the plaintext starts `flowin_`; the list shows
  only the masked `flowin_t···` prefix).

Prefer the first: it cannot go stale if the prefix changes.

**Verify:** `pytest suites/16_pages_outside_routes/test_pages_outside_routes.py::test_an_api_key_is_shown_once_and_never_again -q`

**Do NOT** weaken this into "no assertion". It guards a real credential leak.

---

## T1-05 · four unescaped apostrophes
**Effort:** 2 min · **Side:** source · **From:** pre-existing

`frontend/src/app/not-found.tsx` lines 38 and 78 (two each).
Replace the bare `'` in JSX text with `&apos;`.

Takes eslint from 24 errors to 20. The other 20 are structural
(conditional hooks, refs-during-render) — **out of scope, leave them.**

**Verify:** `npx eslint src/app/not-found.tsx`

---

# TIER 2 — five bugs already fixed; retire their guards (5 failures)

**These are wins, not breakages.** `XPASS(strict)` means a test pinned to a
known-broken behaviour passed — the bug is gone. The one-line change is
removing the marker; **the actual work is proving the bug is really fixed and
not that the test drifted into passing vacuously.**

For each: read the ISS card, reproduce the original bug by hand in the browser,
confirm it no longer happens, then remove the marker and close the card.

| ticket | marker at | issue |
|---|---|---|
| T2-01 | `suites/08_library/test_iss592_agent_detail_close_preserves_filter.py:28` | ISS-592 |
| T2-02 | `suites/08_library/test_iss593_skill_detail_close_preserves_filter.py:26` | ISS-593 |
| T2-03 | `suites/08_library/test_iss594_hook_detail_back_button_loses_search.py:28` | ISS-594 |
| T2-04 | `suites/09_settings/test_settings.py:440` | ISS-320 |

Remove `@pytest.mark.xfail(reason="… unfixed", strict=True)` once confirmed.

## T2-05 · S-15-01's defect pin has outlived the defect
`suites/15_overlays/test_overlays.py` —
`test_inspecting_a_catalog_workflow_describes_it_without_launching`

The test asserts Escape does NOT close the inspect dialog. It now does. Its own
message says what to do: assert S-15-01 in full, drop `@pytest.mark.defect`,
and add the inspect dialog as a row in S-20-01 ("Escape closes any overlay").
Check `screens/15-overlays.feature.md` and `20-keyboard-and-navigation` and
update both the spec and the test.

**Verify (Tier 2):** run `suites/08_library/` and `suites/09_settings/` and
`suites/15_overlays/` one directory at a time.

---

# TIER 3 — the revision family reached these suites (7 failures)

**The pattern is already solved.** `suites/21_run_families_and_versions/test_run_families_and_versions.py`
and `framework/locators/run_history.py` were fixed for exactly this in the
merge. Read `_rows()` there first and reuse it — do not invent a second way.

**The fact behind all of it:** run history now contains one real revision
family (root `77f74563`, ISS-230 fixture). A family renders as ONE row whose
`aria-label` ends `(latest version), <status>`; clicking it opens the family's
LATEST member, not the root. So *family count ≠ run count*, and the first row's
label no longer describes the run you land on.

| ticket | test | what is wrong |
|---|---|---|
| T3-01 | `06_run_history::test_type_filter_counts_sum_to_the_total` | `49 == 50`. Chips count FAMILIES, the `N runs` headline counts RUNS. Compare against the family-row count, as S-21-05 now does — not `RH.total()`. |
| T3-02 | `06_run_history::test_opening_a_row_lands_on_that_run` | Clicks the first row (a family) and expects the root's brief. Assert on the member it actually opens, or pick a non-family row via `_rows()`. |
| T3-03 | `07_run_detail::test_switching_tabs_does_not_wipe_run_state` | `'USER STORIES' not in 'USER STORIES REVISION'`. A substring check meant to catch the empty-state fallback trips on a legitimately-named revision. Match the whole label. |
| T3-04 | `13_errors::test_a_nonexistent_artifact_version_falls_back_to_v1_without_saying_so` | Lands on the family's v2 and looks for `v1`. Needs a single-version run — same fix as S-21-11's `a_run()`. |
| T3-05 | `07_run_detail::test_workspace_lists_the_runs_files_and_starts_unselected` | The rail reports no file count on that revision run. **Check whether this is the app**, not the test — a revision with no workspace files may be a real gap. |
| T3-06 | `04_composer_canvas::test_editing_a_saved_workflow_loads_its_steps` | `3 == 4` — not a family issue. This is the `My presentation` data damage; see T5-01. |

---

# TIER 4 — real app bugs, need investigation (4 + 1)

## T4-01 · native `confirm()` is back — HIGHEST VALUE
**Side:** app · **From:** this merge (`d027f16bd`)

The product replaced native dialogs with an in-app confirm. A fixer agent in
the weekend batch reached for `window.confirm` again. `feat/conditional-gates`
had zero; `feat/bug-hunter` has four:

- `frontend/src/components/settings/AccountSettings.tsx` ×1
- `frontend/src/components/layout/DashboardLayout.tsx` ×2
- `frontend/src/components/workflow/composer/ComposerPage.tsx` ×1

Replace all four with the in-app confirm dialog used elsewhere (find it via the
destructive-delete flow that `S-19-16` covers).

**Verify:** `pytest suites/19_toasts_and_dialogs/test_toasts_and_dialogs.py::test_download_failures_are_the_only_native_dialogs_in_the_product -q`

## T4-02 · Audit tab ignores the version pin (ISS-609)
**Side:** app · `21_run_families_and_versions/test_iss_606_609_version_pin_ignored_by_agent_data.py:70`

Pinned to `/runs/{root}/versions/2/audit`, the tab fetches the ROOT run's
`gate-events` instead of the pinned revision's. The version-pin work (FIX-328 /
FIX-334) did not reach this tab. Start from `PreviewPanel`'s `eff*` values —
the locked constraint is *"every content prop a pinned-version-aware surface
consumes is the eff\* value, never the raw live/root prop."*

## T4-03 · `/library?tab=hooks` renders an empty body on hard refresh
**Side:** app · `12_shell_nav::test_every_top_level_screen_survives_a_hard_refresh`

`document.body.innerText.length` is 0 after a hard reload — only for this one
route of the five tested. Reproduce in the browser before assuming it is a
test-timing issue.

## T4-04 · Simple and Canvas disagree on deliverable type (ISS-340 regression)
**Side:** app · `04_composer_canvas/test_iss340_simple_canvas_deliverable_agree.py` ×2

Simple says `ppt — declared by this workflow` / `Single file — one file from
the workspace`; Canvas says `Streamed text — agent's raw output` for both.

## T4-05 · append refused after the final step slot
`04_composer_canvas::test_a_last_streamed_built_in_refuses_an_append_after_final_step_slot`
— locator never becomes visible. Triage whether app or test.

---

# TIER 5 — decisions, not code

## T5-01 · restore `My presentation`'s 4th agent (data)
`da92b4a4-7eff-41b5-9b9a-205cfa1616d9` lost `report-generator` when a weekend
hunt run overwrote it (`created 2026-08-25 17:44`, `updated 2026-08-29 12:17`).
It is now the plain 3-agent ppt base.

Blocks: `05_saved_workflows::test_a_saved_overrides_run_panel_reports_the_base_agent_count`
(D-05, currently skipping with this reason) and T3-06.

Adding the agent back to that saved workflow makes both run again with no test
change. **Someone must decide** whether to restore it or re-point the tests at
a different override.

## T5-02 · are there supposed to be no `ppt` runs?
Three `06_run_history` tests click the Presentation chip, which is no longer
rendered because no family buckets to `ppt`. Bucketing is correct
(`filterBucketFor` maps every type to one of 4 frameworks or `custom`), so this
is a **data fact**: the run history holds zero presentation runs.

- `test_filtering_by_type_narrows_the_list[Presentation]`
- `test_the_chip_label_and_its_url_value_are_different_words`
- `test_an_unrecognised_type_shows_an_empty_list_rather_than_an_error` — its
  own message: *"the contradiction D-15 records has gone, so re-read that
  defect before changing this test"*

**Decide first whether ppt runs should exist.** If they should, this is a
data-loss finding and the tests are right to fail. If not, the three tests need
a type that still has runs.

## T5-03 · the "Workflow versions" region no user path mounts
`21-run-families-and-versions.feature.md` S-21-07/08/09 specify a region that
lives in `RunDetailPage`, which `WorkflowHistory.handleSelectRun` never mounts
(BUG-002 routes every tap to the shared run screen). The code calls retiring
the internal detail an open INV-3 follow-up. The three scenarios are skipped
with that reason recorded. **Either the spec or the app is wrong — decide.**

---

# TIER 6 — backend clusters, one root cause each (71 failures)

All pre-existing on `feat/conditional-gates`; verified by running the eight
heaviest files against `602296cc8` (36 failed + 10 errors, identical). Detail
and per-test lists in `post-merge-issues.md` §2.

| ticket | cluster | count | one-line summary |
|---|---|---|---|
| T6-01 | B-06 | 21 | revision-analyzer endpoint 500s; the 10 "portal is not running" errors are its teardown fallout |
| T6-02 | B-01 | 15 | registry roster ≠ workflow.yaml step order for all three `prototype_*_revision` pipelines |
| T6-03 | B-05 | 7 | extra events in the terminal payload — `expected exactly one pipeline_failed`, `5 == 1`, `6 == 2` |
| T6-04 | B-07 | 6 | revision refs / lineage; retest after T6-01 and T6-02 |
| T6-05 | B-08 | 4 | **chunk sanitizer perturbs streams it must pass through byte-identically — content-loss risk, rank high** |
| T6-06 | B-02 | 4 | `playwright_smoke_test` breaks the manifest parity contract (`planner: skip`, empty `clarify.defaults`) |
| T6-07 | B-04 | 3 | FIX-323 leftovers still expecting `'Human_Gate'` |
| T6-08 | B-09 | 7 | singles — **includes alembic migration drift: a model has no migration** |

---

# Not for this list

The other 20 eslint errors (`page.tsx` ×8, `useMeasuredVirtualWindow.ts` ×7,
`CanvasConfigRail.tsx` ×2 conditional hooks, `DashboardLayout.tsx` ×2,
`LaunchWizard.tsx` ×1). Structural React-correctness rules, identical count
before the merge, and fixing them means real refactors in the largest files in
the app. They need their own scoped piece of work, not a ticket in a
post-merge cleanup.
