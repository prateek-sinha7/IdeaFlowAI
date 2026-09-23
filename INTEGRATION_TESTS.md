# Integration test failures — `tests/integration/e2e`

**Run:** 2026-09-21 08:48–10:25 · branch `feat/git-versioning` @ `864c8ec6d` (merge of `feat/pdf-workflow`)
**Command:** `sh tests/integration/scripts/run-offline-by-file.sh --headed` — one file at a time, offline tier only (`-m "not live"`), real Google Chrome
**Logs:** `/tmp/integ-by-file-20260921-084847/` · **Screenshots:** `tests/integration/test-runs/*-offline-by-file/`

| | Count |
|---|---|
| Passed | 543 |
| **Failed** | **75** (69 reported + 6 in `15_overlays`, killed before it printed a summary) |
| Skipped | 82 |
| xfail (known open bugs) | 12 |
| Total | 712 |

A second run three days earlier (2026-09-18) produced 78 failures. **65 of 68 files matched exactly**, so these results are reproducible, not noise. The three that differed are listed under [Flaky](#flaky).

---

## The headline: most failures are not broken code

| Cause | Failures | Share |
|---|---|---|
| **Dead test fixtures** — hardcoded run ids deleted from the DB | 21 | 28% |
| **Stale selectors** — element renamed or removed, app works | 20 | 27% |
| **Genuine defects** | 22 | 29% |
| **Stale test expectations** — bug fixed, test never updated | 6 | 8% |
| **Environment** — the `15_overlays` clipboard hang | 6 | 8% |

Only **22 of 75** point at something a user would actually hit.

### Why so many fixtures are dead

Four suites hardcode run UUIDs captured by an earlier sweep. **All 15 are absent from the database**, which now holds 217 runs and exactly **one** run with a parent — so no run family exists for a family test to find.

```
77f74563-fa19-4f0b-84fd-d0224f89a54a   ef86e750-bbcd-404f-855a-fb0d5bee63f5
636ff908-21d6-4c3a-9f00-0ea4f08060fc   2ac66bbd-8d76-4d59-9580-a29b1a4f6e74
8ab0ca9e-03db-4a53-b040-67791a3da520   b868a6b6-ed11-4ae9-a512-6df2b1c5ad4e
b9feac1c-ec21-4531-8ba7-bb391786993e   72e2f445-2149-4623-b39b-f85d42f24f6a
826d09f0-21b0-4b8f-a79f-843fc5c82adb   … 6 more
```

The 404s those tests hit are the app correctly refusing a run that does not exist. The suite warned about this itself — `README.md:43` describes `FIXTURES.json` as *"the live ids the sweep used, and why not to trust them"*. There is no seeding step and no skip-when-missing guard, so a pruned database reports as red tests.

**A hardcoded id is only fatal if that particular run was pruned.** `22_handoff_and_gates` hardcodes one and passes 25/25. Always check existence before blaming code:

```sql
select id, status from workflow_runs where id = '<uuid>';
```

### Category definitions

| Category | Meaning | Who fixes it |
|---|---|---|
| `FIXTURE` | Test points at a run id that no longer exists | Re-seed data, or make the test discover a run |
| `UI-CHANGED` | Selector/label/testid renamed or removed; app is fine | Update the test's selector — **never the app**, see below |
| `FLOW-CHANGED` | Step sequence changed; app is fine | Update the test's path |
| `BROKEN` | The app genuinely misbehaves | Fix the app |
| `TEST-STALE` | Test pins behaviour that deliberately changed, or has a dead `xfail` | Update/remove the marker |
| `ENV` | Infrastructure, not app behaviour | Fix the harness |

### ⚠ The test that agrees with the code for the wrong reason

Before writing or trusting `verification: passed`, ask **would this check FAIL if the bug were
present?** — not "does it pass". If nobody has answered that, the status is aspirational.

Four instances of this shape turned up in two days, each a check whose PASS is compatible with the
very defect it names:

1. **ISS-609** was marked `verification: type: test, status: passed` — by a test that compared the
   pinned view against the **root**. The bug *is* the pinned view showing root data, so the two are
   equal precisely when it is broken. Ten lines below that field, the card's own prose says
   *"Not independently browser-verified: nobody has cold-navigated to a …"*. The prose named the gap;
   the structured field above it said passed.
2. **`assert root != v2, skip if equal`** — a rewrite of that same test. The bug makes them equal, so
   the defect triggers a skip. The assertion was unreachable.
3. **`useRunStateStore.iss673`'s stale `{ fails: true }`** — kept failing after FIX-521 fixed the
   behaviour, because the marker still expected a bug that was gone.
4. **`21_run_families` hardcoding pruned run ids** — every assertion 404'd at the app, so the suite
   reported 18 failures that said nothing about versioning.

**What it cost:** two sessions accepted a wrong merge-attribution built on instance 1's status field,
and instance 4's stale selector nearly had a deliberate accessibility improvement reverted in the app
to make a test green.

**The fix in practice:** when a check cannot fail in the presence of its own defect, say `partial` and
name the gap — which is exactly what ISS-609's prose did and its frontmatter did not.

### ⚠ For every `UI-CHANGED` row, check *why* the selector changed before fixing it

"Selector no longer matches" is ambiguous between **the app regressed** and **the app improved and the test lagged**. Those need opposite fixes, and only the second is safe to fix in the test.

`git log -S'<the old selector>' <merge-base>..HEAD -- frontend/src` names the commit that changed it. Read that diff before touching anything.

**Do not change the app to make a test pass.** A bulk test-fixing pass on this repo has already produced four cases of the application being bent to match a stale test, which hid four real defects. Every non-test change in a test-fixing batch needs its direction verified separately.

---

## 21_run_families_and_versions — 18 failures

**13 are dead fixtures. This feature is *not* proven broken.**

An earlier draft of this analysis claimed the merge regressed version pinning. That was wrong and is retracted — the tests cannot reach a run, so they never exercise the feature. ISS-606…612 are all `status: resolved, verification: passed` as of 2026-08-29.

### Fixture-dependent (13) — `test_iss_230_*`, `test_iss_606_609_*`, `test_iss_607_610_611_612_*`

| Test | Symptom | Category | Why | Fix |
|---|---|---|---|---|
| `test_tab_switch_keeps_the_version_pin_in_the_url` (×2) | `Timeout waiting for [data-testid='tab-files']` | FIXTURE | `ROOT_RUN_ID` absent → page is a 404, no tabs render | Re-seed, or discover a run at runtime |
| `test_tab_switch_keeps_fetching_the_pinned_revisions_run_id` | `Locator.click timeout` | FIXTURE | same | same |
| `test_picking_a_version_in_the_menu_writes_the_pin_into_the_url` | waiting for `run-header button[aria-haspopup='listbox']` | FIXTURE | same | same |
| `test_picking_the_version_the_base_route_already_shows_drops_the_pin` | same locator | FIXTURE | same | same |
| `test_the_files_tab_shows_the_pinned_versions_own_deliverable` | `Locator expected to be visible` | FIXTURE | same | same |
| `test_steps_tab_shows_the_pinned_versions_own_agent_count` | `wait_for` timeout | FIXTURE | same | same |
| `test_audit_tab_fetches_the_pinned_versions_own_run_id` | `Audit tab pinned to v2 never fetched the pinned revision's own gate-events` | FIXTURE | same | same |
| `test_version_picker_navigates_to_revision_from_base_steps_route` | `Locator.click` timeout | FIXTURE | same | same |
| `test_chat_answer_in_steps_navigates_to_revision_from_base_route` | `Locator expected to be visible` | FIXTURE | same | same |
| `test_version_picker_noop_is_not_steps_specific` | `Locator.click` timeout | FIXTURE | same | same |
| `test_back_to_latest_from_pinned_middle_version_reaches_true_latest` | waiting for `Back to latest →` | FIXTURE | same | same |
| `test_chat_deliverable_card_deep_link_carries_the_revisions_run_id` | `Locator expected to be visible` | FIXTURE | same | same |

### Live-data (5) — `test_run_families_and_versions.py` (no hardcoded ids)

| Test | Symptom | Category | Why | Fix |
|---|---|---|---|---|
| `test_runs_sharing_a_root_collapse_into_one_family_row` | `no revised run on this page — every run is a family of one again` | FIXTURE (data) | Only 1 row in the whole DB has `parent_run_id` set | Create a run family in the test data |
| `test_the_version_badges_accessible_name_is_not_its_text` | same | FIXTURE (data) | same | same |
| `test_a_family_expands_to_show_every_version` | same | FIXTURE (data) | same | same |
| `test_the_family_counts_as_one_against_a_filter_chip` | `50 rows, 50 across the chips, 217 on All` | **BROKEN** | Chip totals disagree with the "All" count. Same defect as `06_run_history::test_type_filter_counts_sum_to_the_total` | Fix run-count/family-collapse in the `/api/runs` count query |
| `test_a_single_version_run_shows_no_timeline` | `the run reports no version at all` | **BROKEN** | Header shows no version badge for a single-version run | `RunHeader.tsx` — render the badge for unpinned runs too |

---

## 07_run_detail — 13 failures

**6 dead fixtures, 5 a real UI change, 2 genuine defects.**

| Test | Symptom | Category | Why | Fix |
|---|---|---|---|---|
| `test_preview_full_does_not_silently_substitute_audit` | `Locator expected not to have attribute 'true'` | FIXTURE | `FAILED_RUN_NO_DELIVERABLE` absent | Re-seed |
| `test_run_detail_header_token_total_matches_api` | `expected to contain 'tokens'` | FIXTURE | `MISMATCHED_TOKEN_RUN` absent | Re-seed |
| `test_toolbar_download_enabled_when_deliverable_filename_missing` | `Locator expected to be visible` | FIXTURE | `RUN_WITH_NULL_DELIVERABLE_FILENAME` absent | Re-seed |
| `test_expired_workspace_does_not_claim_deliverable_exists…` | `Locator expected to be visible` | FIXTURE | `DIVERTED_RUN_NO_DELIVERABLE` absent | Re-seed |
| `test_diverted_run_preview_is_not_the_live_waiting_placeholder` | `expected to have attribute 'true'` | FIXTURE | `DIVERTED_RUN` absent | Re-seed |
| `test_a_ppt_v2_runs_final_output_is_the_declared_deliverable…` | `GET /api/runs/b9feac1c…/sandbox → 404` | FIXTURE | run absent | Re-seed |
| `test_switching_tabs_does_not_wipe_run_state` | `Page.click` timeout on `tab-files` | UI-CHANGED | Files tab dropped from `TAB_CONFIG` (`PreviewPanel.tsx:493-506`); deep links still route to it, but no button renders | Point the test at `tab-workspace` |
| `test_browser_back_and_forward_move_between_tabs…` | same | UI-CHANGED | same | same |
| `test_clicking_a_tab_pushes_its_url[tab-files]` | same | UI-CHANGED | same | same |
| `test_every_tab_has_an_addressable_url[tab-files]` | `expected attribute 'true'` | UI-CHANGED | same | same |
| `test_header_relative_age_is_not_frozen_on_just_now…` | `inner_text` timeout on `lane-run-meta` | UI-CHANGED | same page state | Re-check after the tab fix |
| `test_fullscreen_button_reachable_at_mobile_viewport` | waiting for `button[title="Open in new tab"]` with text `Full Screen` | **BROKEN** | Button does not render at mobile viewport on `/preview/full` | Check the preview toolbar assembly |
| `test_a_fresh_deeplink_to_steps_agent_opens_that_agents_detail_pane` | `JSONDecodeError: Unterminated string at column 88690` | **BROKEN** | `/api/runs/{id}` returns malformed JSON — a serialisation defect, likely unescaped content in `agentOutputs` | Backend: audit `agentOutputs` serialisation |

---

## 04_composer_canvas — 9 failures

**Not merge-related.** The merge changed **zero** files in this area. These come from `feat/pdf-workflow`'s own Composer work: `5b3540d71` and `897fe7dbb` (both 2026-09-10).

**Verified:** `aria-label="Add agent"` now appears **0 times** anywhere in `frontend/src` (2 at the merge base and on `feat/git-versioning`, 0 on `feat/pdf-workflow` and at HEAD).

### This one is an accessibility improvement — fix the test, never the app

Commit `127b20a3d` (2026-09-01) removed the label deliberately. Two *different* buttons shared the accessible name "Add agent", so a screen reader could not tell them apart. They now say which one they are (`CanvasView.tsx:2445`, `:2508-2509`):

```jsx
aria-label={`Insert agent before step ${…}`}
aria-label={add.insertBeforeId === undefined ? "Add agent at end" : `Insert agent before step ${…}`}
```

**Correct fix — point the locator at the new names:**

```python
get_by_label("Add agent at end")                            # end-of-pipeline button
get_by_label(re.compile(r"Insert agent before step \d+"))   # insertion buttons
```

**Wrong fix:** re-adding `aria-label="Add agent"` to `CanvasView.tsx`. That would undo the improvement and restore two buttons with identical accessible names.

| Test | Symptom | Category | Why | Fix |
|---|---|---|---|---|
| `test_adding_an_agent_from_the_library_modal` | `Locator.click` timeout on `[aria-label="Add agent"]` | UI-CHANGED | Label gone from the codebase | Update `framework/locators/composer.py:35` `ADD_AGENT` |
| `test_removing_a_node_drops_it_from_the_summary` | same | UI-CHANGED | same | same |
| `test_a_last_streamed_built_in_refuses_an_append_after_final_step_slot` | `Locator.hover` timeout | UI-CHANGED | same | same |
| `test_the_blank_custom_agent_template_is_withheld…` | same | UI-CHANGED | same | same |
| `test_back_button_confirms_before_discarding_unsaved_work` | same | UI-CHANGED | same | same |
| `test_save_with_empty_name_shows_visible_error` | same | UI-CHANGED | same | same |
| `test_simple_and_canvas_agree_on_saved_custom_workflow_deliverable_type` | same | UI-CHANGED | same | same |
| `test_run_is_gated_on_a_long_enough_brief` | `assert 'Add at least one agent first' == 'Add a brief first'` | FLOW-CHANGED | Gate precedence flipped: the agent check now fires before the brief check | Confirm intent in `ComposerPage.tsx`, then update the expectation |
| `test_simple_and_canvas_agree_on_ppt_deliverable_type` | `Simple shows 'ppt — declared by this workflow' but Canvas shows 'Streamed text…'` | **BROKEN** | The two views disagree about the deliverable strategy for one unmodified workflow | Composer: one view reads a stale/hardcoded strategy |

---

## 05_saved_workflows — 6 failures

| Test | Symptom | Category | Why | Fix |
|---|---|---|---|---|
| `test_a_card_opens_its_detail_view` | `Locator expected to be visible` ("Presentation" badge; aria shows `ppt_v2`) | UI-CHANGED | Badge shows the raw workflow id instead of its display name | Map `ppt_v2` → "Presentation" in the badge |
| `test_run_opens_the_base_workflows_launch_panel` | expected "NEW PRESENTATION", got "Provide the brief" | **BROKEN** | Wrong workflow loads — a PPT saved workflow opens the product-requirements panel | Saved-workflow → launch-panel resolver |
| `test_a_saved_overrides_run_panel_reports_the_base_agent_count` | same | **BROKEN** | same | same |
| `test_running_from_a_card_starts_a_run_of_that_workflow` | `Timeout` waiting for navigation to `**/create/**` | **BROKEN** | The card's Run action never navigates | Card action handler |
| `test_the_detail_view_resolves_agent_ids_to_display_names` | `JSONDecodeError: Unterminated string at column 197491` | **BROKEN** | Malformed JSON from the user-workflows endpoint — same class as the run-detail one | Backend serialisation |
| `test_click_through_run_shows_the_saved_overrides_own_name_even_mid_race` | `[XPASS(strict)] ISS-283 unfixed` | TEST-STALE | ISS-283 is fixed; the test now passes and strict mode flags it | Remove the `xfail` marker |

---

## 18_chat_lane — 7 failures

**5 are real. 2 are dead fixtures.** `test_chat_lane.py` discovers a live run via `a_run_with_status(page, "completed")`, so its failures are genuine; `test_iss_218_edit_brief_prefill.py` hardcodes `RUN_A`/`RUN_B`, both absent.

| Test | Symptom | Category | Why | Fix |
|---|---|---|---|---|
| `test_the_lane_survives_every_tab[tab-preview]` | `the transcript changed when the tab did — assert 4 == 0` | **BROKEN** | Transcript is empty on first load of `/runs/{id}`, and only populates after navigating to a tab URL | Ensure the transcript seeds on initial run load, not just on tab nav |
| `test_the_lane_survives_every_tab[tab-thinking]` | same | **BROKEN** | same | same |
| `test_the_lane_survives_every_tab[tab-files]` | same | **BROKEN** | same | same |
| `test_the_lane_survives_every_tab[tab-workspace]` | same | **BROKEN** | same | same |
| `test_the_narrator_names_each_lifecycle_event[completed]` | `a completed run's transcript never says 'Run started'` | **BROKEN** | same root cause | same |
| `test_edit_brief_and_run_again_prefills_the_original_brief` | timeout on `chat-relaunch-secondary` | FIXTURE | `RUN_A` absent | Re-seed |
| `test_edit_brief_shows_the_currently_viewed_runs_own_brief…` | same | FIXTURE | `RUN_B` absent | Re-seed |

---

## 03_launch_panels — 5 failures

Same origin as `04_composer_canvas`: the other branch's 2026-09-10 Composer commits.

| Test | Symptom | Category | Why | Fix |
|---|---|---|---|---|
| `test_the_user_stories_panel_names_its_own_workflow` | `expected to contain '7 agents'`, panel shows `6 agents · ~6m` | UI-CHANGED | The user-stories roster went from 7 agents to 6 | Confirm the manifest is right, then update the expectation |
| `test_cold_loading_create_app_shows_the_user_stories_panel` | `D-01 appears to be FIXED` | TEST-STALE | The test documents a defect that has since been fixed | Remove the defect marker / invert the assertion |
| `test_checking_a_review_gate_sets_that_agents_gate_in_the_advanced_modal` | timeout on text `Domain Discovery Agent` | UI-CHANGED | That agent is no longer in the roster | Update the expected agent |
| `test_advanced_modal_cancel_discards_a_conditional_gate_route_edit` | timeout on `canvas-node-custom-agent:language` | UI-CHANGED | Node testid format changed — `897fe7dbb` altered route-id normalisation (bare vs `custom-agent:` prefix) | Align the testid with `nodeIdOf()` |
| `test_seeded_before_human_gate_activates_prompt_user_toggle_on_fresh_load` | timeout on `canvas-node-custom-agent:pick-language` | UI-CHANGED | same | same |

---

## 15_overlays — 6 failures, then a hang

**The only hang in the suite.** It stalled on both runs, three days apart, and was killed each time after ~6 minutes. 23 of its 29 tests never ran.

**Root cause of the hang — `test_overlays.py:392`:**

```python
copied = page.evaluate("() => navigator.clipboard.readText().catch(() => '')")
```

A clipboard read blocks on a permission prompt in a **headed** browser, and this run used `--headed`. The `.catch()` does not help: the promise never settles, so it hangs until the 180s per-test timeout.

| Test | Symptom | Category | Why | Fix |
|---|---|---|---|---|
| `test_share_copies_a_link_rather_than_opening_a_dialog` | hangs 179s, killed | **ENV** | `clipboard.readText()` never resolves headed | Grant clipboard permission in the browser context, or run this file headless |
| `test_the_add_agent_modal_lists_agents_by_category` | timeout on `[aria-label="Add agent"]` | UI-CHANGED | Label removed (see `04_composer_canvas`) | Update the selector |
| `test_each_agent_card_is_individually_addressable` | cascade from the above | UI-CHANGED | same | same |
| `test_add_agent_modal_cannot_be_closed_by_name_or_escape` | cascade | UI-CHANGED | same | same |
| `test_the_version_picker_lists_a_runs_artifact_versions` | timeout on the version-picker label | UI-CHANGED | Picker label changed (see `23_controls_inventory`) | Update the selector |
| `test_the_run_actions_menu_offers_only_delete` | no detail — hung before the summary printed | UNKNOWN | Not established | Re-run after the hang fix |

---

## Smaller suites

### 10_analytics — 3 failures

| Test | Symptom | Category | Why | Fix |
|---|---|---|---|---|
| `test_the_pipeline_breakdown_sums_to_the_totals` | `the breakdown sums to 1,915 against a total of 217 across 73 pipelines` | **BROKEN** | Per-pipeline counts total ~9× the headline run count — the breakdown double-counts | Audit the `runs_by_pipeline` query |
| `test_daily_activity_plots_one_bar_per_active_day` | `no zero-token day was plotted` | **BROKEN** | Days with no activity are omitted rather than drawn at zero, compressing the axis | Plot every day in range |
| `test_pipeline_breakdown_respects_the_model_filter_too` | `[XPASS(strict)] ISS-289 unfixed` | TEST-STALE | ISS-289 is fixed | Remove the `xfail` marker |

> The QA-PS-009 label change (`AnalyticsPage.tsx:829`, `Adaptive (effort: max)` → `Adaptive`) is **not** the cause of any of these. No failing assertion references that text.

### 06_run_history — 3 failures

| Test | Symptom | Category | Why | Fix |
|---|---|---|---|---|
| `test_header_count_reflects_the_true_total_not_the_capped_page` | `[XPASS(strict)] ISS-198 unfixed` | TEST-STALE | ISS-198 is fixed | Remove the marker |
| `test_scrolling_to_the_bottom_loads_more_runs` | `[XPASS(strict)] ISS-198 unfixed` | TEST-STALE | same | same |
| `test_type_filter_counts_sum_to_the_total` | `the named filters account for 50 of 217 families` | **BROKEN** | Type chips sum to 50 while "All" reports 217, so some families match no chip. Same defect as the `21_*` chip failure | Fix chip counting / family grouping |

### 02_home_catalog — 1 failure

| Test | Symptom | Category | Why | Fix |
|---|---|---|---|---|
| `test_a_saved_override_changes_the_catalog_cards_agent_estimate` | `both accounts now see the same estimate ({'admin': 15, 'basic': 15}) — D-10 is resolved` | TEST-STALE | Documents defect D-10, which is now fixed. Marked `@defect` but not `@xfail`, so it reports as a failure | Invert the assertion and drop the defect marker |

### 14_run_states — 1 failure

| Test | Symptom | Category | Why | Fix |
|---|---|---|---|---|
| `test_a_failed_run_has_no_preview_tab` | `a failed run is missing tab-files` | UI-CHANGED | Only `tab-thinking`, `tab-workspace`, `tab-audit` render now | Update the expected tab set |

### 19_toasts_and_dialogs — 1 failure

| Test | Symptom | Category | Why | Fix |
|---|---|---|---|---|
| `test_download_failures_are_the_only_native_dialogs_in_the_product` | `native confirm/prompt reintroduced: [AccountSettings.tsx, IntegrationsCard.tsx, DashboardLayout.tsx, SkillManager.tsx, ComposerPage.tsx]` | **BROKEN** | A source-level guard against native browser dialogs. `window.confirm` is back in 3 files | Replace with the app's dialog component |

### 20_keyboard_and_navigation — 1 failure

| Test | Symptom | Category | Why | Fix |
|---|---|---|---|---|
| `test_escape_closes_the_add_agent_modal` | timeout on `[aria-label="Add agent"]` | UI-CHANGED | Same removed label | Update the selector |

### 23_controls_inventory — 1 failure

| Test | Symptom | Category | Why | Fix |
|---|---|---|---|---|
| `test_the_artifact_version_picker_is_addressable` | timeout on `^Version .*choose version$` | UI-CHANGED | The picker's accessible name changed | Update the label pattern |

---

## Progress — 2026-09-21

**75 → 51 failures.** Verified per file by re-running each one, not by a single full-suite pass.

| Fix | Result |
|---|---|
| Clipboard permission in `conftest.py` | `15_overlays` 6F + hang → **2F, 31 passed**; 23 tests that never ran now run |
| `ADD_AGENT` → `"Add agent at end"` / `Insert agent before step N` | `20_keyboard` → **0F**, `04_composer` 6F → **3F** |
| `tab-files` dropped from the strip list | `14_run_states` → **0F**, `07_run_detail/test_run_detail` 6F → **3F** |
| 4 dead `xfail` markers removed | ISS-198 ×2, ISS-289, ISS-283 → **0F** |
| D-10 assertion inverted | `02_home_catalog` → **0F** |
| Dead fixture ids repointed to live runs | `iss285`, `iss313` → **0F**; versioning improved by 1 |
| `PIPELINE_LABEL` shared + missing v2 types added | raw `ppt_v2` no longer shown to users |

**On the badge fix.** Both `SavedWorkflowsPage` and `WorkflowDetailView` carried their own copy of
`PIPELINE_LABEL`, and both were missing the same keys — so a `ppt_v2` workflow printed the raw id in
two places. The map now lives once in `savedworkflows/pipelineLabel.ts` and both import
`pipelineLabelFor()`. A miss still falls back to the raw id, so any new pipeline type needs an entry.

It did not reduce the failure count, and that is the expected result: `test_a_card_opens_its_detail_view`
moved from `AssertionError: Locator expected to be visible` (the badge) to
`json.decoder.JSONDecodeError: Unterminated string` — it now reaches the malformed-JSON defect that was
queued behind it. A stale-UI failure became an exposed real defect. Two tests in that file now fail on
that one backend bug.

**Reverted:** the D-01 inversion in `03_launch_panels`. `/create/app` still shows the user-stories
panel; the old assertion failed only because the roster went 7 → 6. Restored to original.

### What the repoint could NOT fix

Repointing ids makes the page load; it does not make the assertions true. The tests also hardcode
the old fixture's **shape**:

```
assert m.group(1) == "2" and m.group(2) == "2"
AssertionError: Steps tab pinned to v2 (agent_count=2) shows '11 / 11 agents'
```

And three shapes do not exist in the database at all: a completed PPT run, a diverted run, and a
family with 3+ versions (only one run has a parent, so the largest possible family is 2).

---

## Plan for the remaining 51

### Phase 1 — blocked on a decision (4 failures, one line each)

Each is a one-line test edit. They are only open because "intended change" and "regression" need
opposite fixes and the tests cannot tell them apart.

| Question | If intended | Clears |
|---|---|---|
| User-stories roster went 7 agents → 6 | change the expected count | 2 (incl. D-01) |
| Composer now gates on "Add at least one agent first" before the brief check | swap the expected string | 1 |
| The run-actions menu offers more than Delete | update the expected list | 1 |

### Phase 2 — make the suite stop rotting (~16 failures)

The versioning tests fail on hardcoded counts, not ids. Two options:

1. **Rewrite them to be shape-agnostic** — read the pinned version's agent count from the run and
   assert the *relationship* ("the pinned version's count differs from the root's"), not a literal.
   Durable, and the same treatment fixes the next prune too.
2. **Recreate fixtures with the original shape** — a 5-member family and a 2-agent revision.
   Faster, but rots again on the next prune.

Option 1 is the real fix. Neither is possible for the 3 shapes that do not exist without creating
data — a real run costs money, a crafted DB row is synthetic but free. **Needs a decision.**

### 21_run_families_and_versions — 13 → 5, closed 2026-09-21

| # | Was failing | Cause | Fix |
|---|---|---|---|
| 1 | `/versions/N` resolved to the wrong run | `/family` dropped cross-type members | **product** — `runs.py` guard removed |
| 2 | Files tab pinned to v2 showed the ROOT's deliverable | `genericDeliverable` never followed the pin | **product** — `effGenericDeliverable` |
| 3 | Audit tab fetched the root's gate-events | same | same |
| 4 | Pinned view rendered with the root's renderer | `detectedType` read the shell's type | **product** — `pinnedType` wins |
| 5–6 | Version picker "did not navigate" ×2 | asked for label `Version v2`, retired by `e4eecb705` | **test** — pick what the menu offers |
| 7–8 | Chat card deep links ×2 | `get_by_text("Revision started")` → 3 matches → strict-mode violation | **test** — scope to newest card |
| 9 | `not fetched_root` | could never pass: a pinned deep link mounts the root BY DESIGN | **test** — assertion deleted, reasoning recorded |

Two product defects, both real, both with the fix verified in a browser before and after.
No unit test regressed: `vitest src/components/preview src/components/results/FilesTab` is
7F/121P/4xfail identically with and without the `PreviewPanel` change (measured by stashing it).

#### The 5 that remain — 3 are ONE missing fixture

`_a_family()` needs a run-history row carrying an `N versions` badge, and no such row exists.
This is a **data gap, not a defect** — verified, not assumed:

- `_compute_root_ids` (the list endpoint's ancestor walk) has no type filter and is correct.
- `groupRunsByFamily` re-derives the family from the rows **on the current page**, and says so:
  *"a family with members OUTSIDE the <=100-run getWorkflows list window shows fewer versions
  in this list card … by design"* (`RevisionFamilyView.tsx`).
- Page 1 holds 50 rows, cutting off at 2026-09-17 10:06. The only real family's root
  (`2708dbf1`, 2026-09-16 15:33) falls outside it; only its newest member is on the page.
- The one family that IS wholly on page 1 (`28a318c9` + `f970bb7b`) is a **divert** pair, which
  R-14/R-20 deliberately render as a divert LINK rather than a version family.

**What would clear all three:** one revision of a childless completed root that already sits
inside the newest 50 — `8ff57cca` (rank 27, `user_stories`, tag `v1`) is the candidate. The
revision lands at rank 1 and its root at ~28, so both are on page 1.

**Two attempts failed, neither wasted on the wrong thing:**
1. `custom_revision` of `c83301af` — `custom-revision-planner` looped calling `write_file` with
   `file_path` and no `content`, 75+ turns at ~51k input tokens each, ~34 min before it was
   killed. `AGENT_RECURSION_LIMIT` is 400, so nothing would have stopped it for another ~325
   turns. **Its own defect: no loop detection on a malformed repeated tool call.** Run marked
   `failed` (`5b3eef10`).
2. `user_stories_revision` of `8ff57cca` — the concierge ANSWERS a chat message inline instead
   of proposing a revision, so no confirm chip appears and no run launches. The revision path
   for this pipeline is not the chat composer. No spend.

`_NEEDS_FAMILY` deliberately uses `pytest.fail` where this file's other eight
"dataset cannot exercise this" cases use `pytest.skip`. **Left as `fail` on purpose** — the
author made it loud, and converting it would hide a real gap rather than close it.

The other 2: `test_the_family_counts_as_one_against_a_filter_chip` (chips total 50 against 220
on All — a windowed-count question, same root as above) and
`test_a_single_version_run_shows_no_timeline` (its `a_run()` now picks a run that IS a family
member, so it is asserting "no versions" against a versioned run). Neither diagnosed further.

### The version-pin defect — traced 2026-09-21, **FIXED**

> **The first trace in this section was wrong and is retained below as a worked example of how.**
> It blamed `PreviewPanel.tsx:877` and a `contentSourceRunId` guard, entirely from grepping. The
> browser disproved both in one probe. The lesson is the one already at the top of this file: a
> plausible chain read off the source is a hypothesis, not a finding.

**Symptom.** Pinned to v2, the Steps tab shows the root's roster (11 agents where the revision has 3),
the Audit tab fetches the root's gate-events, and no request for the pinned run is made at all.

**Actual root cause — backend, not frontend.** `GET /api/runs/{root}/family` returned **2 members
where the database has 3**, silently dropping `23bd9c67`. `/versions/N` resolves the pin by *index*
into that list, so a dropped member shifts every later version onto the wrong run. `/versions/2`
fetched `3839720c` (the real v3). The frontend was correct throughout.

The drop was FIX-173's cross-family guard at `runs.py:1649` — reject any child whose canonical base
type differs from the root's. FIX-173's own card records that the contamination it was written for
came from a race where `contentSourceRunId` transiently pointed at the wrong run when `postRevision`
fired. That race writes `parent_run_id` **and** `source_run_id` from the same wrong value, so they
agree — no read-path check can detect it. Verified: 0 rows in the table have them disagreeing.

Meanwhile the guard rejected two legitimate rows, the only two cross-type-parented rows that exist:

| Child | Type | Parent type | Why legitimate |
|---|---|---|---|
| `23bd9c67` | `prototype_revision` | `custom` | `DashboardLayout.tsx:2310`'s `\|\| !!prototypeContent` routes a `custom` run that produced prototype.html into `handleRevisePrototype`. The user clicked revise. |
| `f970bb7b` | `ex_A3_b_spanish` | `ex_A3_divert` | A divert runs a **different pipeline by design** — a base-type comparison can never admit it. |

The divert case is what settles it: the guard broke a shipped feature.

**Fix applied.** Guard removed; a cross-type child is now admitted and logged, so a genuine
contamination is observable rather than indistinguishable from a version that never existed.
Two regression tests added to `backend/tests/unit/test_runs_api_family.py`, both confirmed to FAIL
against the old guard before being accepted. FIX-173 was `verification: manual` with no test — which
is exactly how this survived to cost a day.

**Result: 13F → 12F**, and it exposed a second, distinct defect beneath it (next section). The
"13 failures = 1 defect" estimate was wrong; treat defect counts in this file as floors.

#### Second defect, found underneath: family grouping is page-local

Three tests now fail with *"no revised run on this page — every run is a family of one again"*.
`_compute_root_ids` is correct (pure parent-link walk, no type filter), so the grouping data is
right. The history list groups families **only within the current page**: this family's root is from
Sep 16 and falls outside page 1, while its newest member is from today and sits at the top. Related
to `test_the_family_counts_as_one_against_a_filter_chip` — *"50 rows, 50 across the chips, 220 on
All"*. Not diagnosed further.

---

<details>
<summary>Superseded trace (kept as a cautionary example — do not act on it)</summary>

1. `PreviewPanel.tsx:877` resolves the pin by **index into the family**:
   `sortedMembers[Number(pinnedVersion) - 1]?.id`
2. `sortedMembers` (line 741) comes from the `runFamily` prop.
3. `runFamily` is fetched in `DashboardLayout.tsx:701-706`, gated on `contentSourceRunId`:
   `if (!contentSourceRunId) { setRunFamily(null); return; }`

Claimed: when `contentSourceRunId` is unset the family never loads, so the pin falls back to the root.

**Both premises were false.** A browser probe showed `/family` IS fetched on a cold deep-link (the
guard never fires — `page.tsx`'s cold-mount effect calls `handleSelectWorkflowRun`, which sets
`contentSourceRunId`), and step 1 resolves correctly given correct data. The endpoint was the liar.

</details>

**The fixture that makes this provable:** family root `2708dbf1` with revisions `23bd9c67` and
`3839720c` — agent counts 11, 3 and 2. Distinct counts are what turn "the numbers disagree" into
"it rendered the root". All three rows are present in the database; the earlier claim that they were
pruned was also wrong.

### Phase 3 — the real defects (~13)

In value order. Each needs debugging, not a test edit.

1. **Chat transcript empty until you switch tabs** (5) — `test_chat_lane.py`, live-discovered runs so
   the failures are real. Sits exactly where this branch's `useRunChat`/`ResultCard` meets the
   incoming `RunChatLane`. The one seam that had never run together before the merge.
2. **Filter chips total 50 against 217 on "All"** (2) — same defect in `06_run_history` and
   `21_run_families`. One fix, two suites.
3. **Two endpoints return malformed JSON** (2) — `/api/runs/{id}` and user-workflows, both
   `Unterminated string`. Likely one serialisation bug, probably unescaped content in `agent_outputs`.
4. **Saved workflow opens the wrong launch panel** (3) — a PPT card opens the product-requirements
   panel; Run-from-card never navigates.
5. **Analytics breakdown sums to 1,915 against a 217 total** (1) — `runs_by_pipeline` double-counts.

### Phase 4 — uncovered by the fixes, needs triage (2)

Both were previously masked by timeouts in `04_composer_canvas` and only became visible once the
selector was fixed:

- `test_back_button_confirms_before_discarding_unsaved_work` — "Back discarded the unsaved workflow
  with no confirmation dialog". `ComposerPage.tsx` is also one of the 3 files still calling native
  `confirm()`, so this and the `19_toasts` guard may be the same problem.
- `test_a_last_streamed_built_in_refuses_an_append_after_final_step_slot` — the button is found now,
  but hovering it no longer shows the last-step guard tooltip.

### Phase 5 — deferred, not blocking

- Replace native `confirm()` in 3 files with the app dialog (1 failure, real UI work).
- Analytics zero-activity days omitted from the chart rather than drawn at zero (1).
- The live tier has **no offline coverage at all** — gate-defect regressions and pipeline smoke are
  fully deselected. Worth knowing; not fixable offline by definition.

---

## Original fix order (superseded by the plan above)

1. **Re-seed the fixture runs** — clears 21 failures across 4 suites, and unblocks any real defect those tests were meant to catch. Better still, make them discover a run at runtime the way `test_run_detail.py` and `test_chat_lane.py` already do.
2. **Update `ADD_AGENT` in `framework/locators/composer.py:35`** — clears ~10 failures in 3 suites (`04_composer_canvas`, `15_overlays`, `20_keyboard_and_navigation`). Use `"Add agent at end"` and `re.compile(r"Insert agent before step \d+")`. Test-side only — the app change was an a11y fix and must stand.
3. **Fix the overlays hang** — grant clipboard permission or run that file headless. Unblocks 23 tests that never ran.
4. **Drop the 6 stale markers** — ISS-198 (×2), ISS-289, ISS-283, D-01, D-10. All are fixed bugs still reported as failures.
5. **Then the 22 real defects**, worst first: chat-lane transcript seeding (5 tests), the chip-count mismatch (2 suites, same bug), analytics double-counting, the two malformed-JSON endpoints, saved-workflow launch resolving to the wrong workflow, native `confirm` dialogs.

## Flaky

Three files differed between the 2026-09-18 and 2026-09-21 runs; everything else was identical.

| File | 09-18 | 09-21 |
|---|---|---|
| `09_settings/test_settings` | 27P **1F** | 28P **0F** |
| `18_chat_lane/test_chat_lane` | 17P **7F** | 19P **5F** |
| `23_controls_inventory` | 54P 1F 3S | 53P 1F **4S** |

Treat single-run results in these three as provisional.

## Not covered

- **The live tier** — anything calling real Bedrock. `22_handoff_and_gates/test_gate_defect_regressions` (3 tests) and `25_pipeline_smoke` (5) were fully deselected, so gate-defect regressions and pipeline smoke have **no offline coverage at all**.
- **23 of 29 `15_overlays` tests**, which never ran because of the hang.
- **82 skipped tests**, not audited here.

## How this was checked

Failure symptoms come from each file's `short test summary info` block. Categories were produced by five analysts working in parallel, then **each headline claim was verified against the database and source before it was written here**. That check changed three conclusions:

1. "Versioning is broken and the merge regressed it" — wrong; the fixtures are gone. Retracted.
2. "The chat-lane cluster is dead fixtures" — wrong; 5 of its 7 use a runtime-discovered run and are real.
3. "`window.confirm` is in 5 files" — it is in 3.

Claims still carrying analyst-level confidence only, not independently re-verified: the precise internal cause of the two `JSONDecodeError` responses, and the saved-workflow launch-panel resolver.

---

# 2026-09-21/22 — the 57-failure sweep, worked to completion

The baseline was a full 68-file offline sweep: **589 passed · 57 failed · 80 skipped · 12 xfail**
(738 tests). What follows is every one of those 57, by cause. Numbers after each suite are
`sweep → final`.

## Product defects found and fixed — 9

| # | Defect | Fix |
|---|---|---|
| 1 | `GET /runs/{id}/family` silently dropped members whose pipeline type differed from the root's, so `/versions/N` — which resolves by INDEX — landed on the wrong run | `app/api/runs.py`: FIX-173's `_canonical_base` guard removed; cross-type children admitted and logged |
| 2 | A pinned version's Files and Preview tabs showed the ROOT's deliverable beside the pinned version's agent outputs | `PreviewPanel.tsx`: `effGenericDeliverable`, routed through all 13 read sites |
| 3 | A pinned version rendered through the ROOT's renderer, so it presented differently from its own page | `PreviewPanel.tsx`: `pinnedType` wins over the shell's `workflowType` |
| 4 | "Edit brief & run again" opened a BLANK composer — it read `input` off `GET /api/runs`, which deliberately omits that column | `DashboardLayout.tsx`: fetch the run individually, as the endpoint's own docstring prescribes |
| 5 | …and for a `prototype_v2` run the brief was written to a slot nothing reads (`selectWorkflowWizardPath` omits `_v2`) | `DashboardLayout.tsx`: key the draft slot off the wizard's own `STEPPER_MODE` |
| 6 | The run header undercounted tokens by **6.1M** (13.6M shown against a persisted 19.7M) — the replayed per-agent sum misses work off the top-level agent rows | `useWorkflow.ts` + `page.tsx`: the server's persisted `token_usage` wins for a settled run, in the same after-replay reconciliation that already restores status |
| 7 | A saved `ppt_v2` workflow's Run opened **"GENERATE PRODUCT REQUIREMENTS"** — a different product's panel | `page.tsx`: `WIZARD_BY_BASE` map covering `_v2`; `workflowRunWizardMode` widened to `LaunchMode` |
| 8 | A deliverable declared `output` with mimetype `application/zip` reached the UI with **no extension**, and "ZIP Archive" carried no `(.zip)` where HTML/MD/JSON all did | `FilesTab.tsx`: extension filled from the mimetype when the declared name lacks one; every format label names its extension |
| 9 | The composer's "Prompt User" toggle read OFF for every step declaring `before-human` — `condition_agent` is normalised to `custom-agent:ask` while canvas nodes are keyed bare | `CanvasConfigRail.tsx`: compare on the instance id |

Defect 8 is the user's own Decision 7 ("Download button should have the deliverable file title
and extension").

## One claim retracted

An earlier note in this file recorded "two endpoints return malformed JSON" as a backend defect.
**That was wrong.** `framework/api.py`'s `full()` slices every response at 200 000 characters, so a
large run's JSON was cut mid-string and `json.loads` raised `Unterminated string`. The servers were
correct throughout. `json_body` now raises the cap and asserts it was not hit, and the two callers
that hand-rolled `json.loads(api.full(...))` were routed through it.

## Test defects — the categories that actually recurred

- **Fixtures pinned by run id.** Six scenarios named a UUID that had since been pruned OR, worse,
  been reassigned to a different run by a reseed — `26a7e162` came to name a run whose brief and
  status were both wrong for the scenario, so it failed with `expected '10.4K', actual '13.6M'`,
  which reads exactly like the mismatch it exists to detect. All now discover at runtime.
- **A label quoted into a CSS selector.** A brief containing `"` produced
  `Unexpected token "" while parsing css selector` and took five scenarios down at once. Suite 21
  already documented this and selected by index; suites 06 and 18 had not adopted it. They do now.
- **Sampling a value that was still loading.** The chat transcript seeds one `/events` fetch per
  family member (0 messages at 2s, 14 at 5s) and the Canvas deliverable combobox sits on its
  `?? "streamed_text"` default until `runConfig` lands. Both were read on a fixed timeout. Both
  now settle first.
- **Comparing a paginated list against an account-wide total.** The history list opens on 50 of
  220 and loads more on scroll (ISS-198's sentinel is live). Four scenarios compared `len(rows)`
  against a chip count and failed at "50 of 220".
- **Assertions that could never pass.** `assert not fetched_root` in two places: a pinned deep link
  MOUNTS the family root, and `/family` is itself keyed on the root, so fetching it is how the pin
  is applied. Removed, with the reasoning recorded in place.
- **Pinning behaviour a later fix deliberately removed.** ISS-384 replaced the generic wizard title
  with the saved row's own name; a scenario asserted the generic title and so failed precisely when
  that fix worked. Same shape for ISS-622 (native `confirm` → in-app dialog) and `e4eecb705`
  (`"Version v2"` → `"v2"`).

## Self-inflicted data damage, and what it cost

Fixture runs launched earlier in the session polluted the dataset and caused failures that looked
like product regressions:

- A `custom_revision` was launched to build a family fixture. `custom-revision-planner` **looped
  calling `write_file` with `file_path` and no `content`** — 75+ turns at ~51k input tokens each,
  ~34 minutes before it was killed. `AGENT_RECURSION_LIMIT` is 400, so nothing would have stopped
  it for another ~325 turns. **This is an open product defect in its own right: there is no
  detection of an agent looping on an identical failing tool call.** The run was deleted.
- That run's status was then set to `failed` by a direct `UPDATE`. A genuinely-failed run carries a
  finalization record; this one did not, so the lane could not derive a terminal state and fell
  back to "Cancelled" with no composer — breaking five chat-lane scenarios. Deleted via the real
  DELETE endpoint.
- Two `chat_message` events were injected straight into `run_events` with hand-written
  `message_id`s (`fixture-rev-root-…`). The app only ever mints `client-{n}-{uuid}`, so a scenario
  asserting that invariant failed correctly. Deleted.

**Hand-writing run state into the database produces fixtures that satisfy a SQL query and are
structurally incomplete to the application.** Two of the three took longer to diagnose than the
work they were meant to enable.

## Data gaps that remain — skipped, not failed

Three scenarios now skip with a precise reason rather than failing:

- No completed `ppt`-family run exists at all, so the PPT preview toolbar (ISS-314) and the
  declared-deliverable-vs-tmp-scratch check (ISS-199) have nothing to mount against.
- No run currently has an expired workspace (ISS-356) — `expired` is a retention timer, so which
  runs qualify changes with the clock.

## Final: 55 of 57 — the 2 that remain

Both in `03_launch_panels`, and they are ONE open product defect, not two test problems.

### Fixed on the way there

- `canvas-node-custom-agent:language` → `canvas-node-language`. `CanvasNode` renders
  `canvas-node-{agent.id}` where `agent.id` is the bare instance id; the agent-qualified form
  no longer exists in the DOM.
- `[data-testid="tab-config"]` → `get_by_role("tab", name="Config")`. The composer's rail tabs are
  role-based and carry no testids, and a Playwright click on a selector matching NOTHING is not an
  error — so the Config panel never opened and the failure surfaced one step later.
- `get_by_label("Type")` → `get_by_label("Type", exact=True)`. `get_by_label` matches a SUBSTRING,
  and the Config tab has since gained a **"Node type"** select (AI agent / Code). `.first` resolved
  to THAT, and `select_option("Workflow")` spent 30s against a select with no such option.

### The defect underneath — an outcome's route type will not change

Measured directly in the browser on `/create/ex_A2_branch`, `language` node, Config tab:

```
before:  Type = step
action:  select_option("Workflow")      # succeeds, no error
after:   Type = step                    # reverted; all three outcomes unchanged
         workflow-target-button count: 0
```

The select is controlled by `outcome.trigger`, so a value that snaps back means the write never
reached state. The write path is wired end to end — every link exists:

```
CanvasConfigRail  updateOutcome()      -> onRouteChange?.(agent.id, applyOutcomePatch(...))
CanvasView        handleRouteChange()  -> onTreeChange?.(mapAgentInTree(pipelineAgents, id, ...))
AgentsPopup       handleTreeChange()   -> onReorder?.(next)
IdeaInputPage     handleReorderAgents  -> setPipelineAgents(reordered)
```

`applyOutcomePatch` itself is correct (it merges `{...prevOutcome, ...patch}`). Every hop is an
OPTIONAL call (`?.`), so any unwired link fails silently — but all four are wired at both mounts
(`IdeaInputPage:2149`, `LaunchWizard:1444`). **Not diagnosed past that point.** The next thing to
check is whether the `route` the rail READS comes from the same list `setPipelineAgents` writes:
`IdeaInputPage` maintains `manifestAgents` with QUALIFIED ids (`custom-agent:ask`,
`IdeaInputPage:~1199`) alongside `pipelineAgents` whose ids are bare, and `mapAgentInTree` keys on
an exact id match — the same qualified-vs-bare split that made the Prompt User toggle read OFF.

Until this is settled, **ISS-258 cannot be exercised at all**: its scenario has to MAKE a route edit
before it can test that Cancel discards it.
