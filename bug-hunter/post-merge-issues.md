# Post-merge issue log

Merge commit `90ec542a0` — `feat/bug-hunter` → `feat/conditional-gates`
(parents `602296cc8` + `a35e8fb2a`). Swept 2026-08-30.

**Headline: the merge caused exactly ONE failure.** Everything else below was
already failing on `feat/conditional-gates` before the merge, and was verified
that way rather than assumed — see *Provenance* under each section.

| suite | result |
|---|---|
| frontend (vitest) | 1 failed · 1371 passed · 8 expected-fail · 185 files |
| backend (pytest) | 61 failed · 10 errors · 4088 passed · 116 skipped · 11m30s |
| integration (e2e) | 23 failed · 621 passed · 82 skipped · 15 xfailed · 55m22s |
| eslint | 24 errors (identical count pre-merge) |
| tsc --noEmit | clean |

---

## 1. Caused by the merge (1)

### F-01 · stale count pin on page.tsx's narrowed catch block
`frontend/src/app/[...view]/workflowDetailCatch.source.test.ts:84`
— `expected 5 to be 3`

`feat/bug-hunter` added two more call sites of

```
if (err instanceof ApiError && (err.status === 403 || err.status === 404)) {
```

to `page.tsx` and never moved the pin that counts them.

```
pre-merge 602296cc8 : 3
bug-hunter a35e8fb2a: 5   ← added the two, left the pin at 3
merged     90ec542a0: 5
```

The direction is GOOD — two more places now narrow the catch instead of
swallowing every error. **Fix: update the pin to 5 and name the two new sites
in the comment above it.** Do not "fix" page.tsx.

### F-02 · native `confirm()` reintroduced (S-19-17)
`suites/19_toasts_and_dialogs` — the product uses an in-app dialog for
destructive confirmation; S-19-17 exists purely to stop `window.confirm`
coming back. It came back, in the weekend hunt's own batch:

```
                       602296cc8   a35e8fb2a   merged
AccountSettings.tsx        0           1          1
DashboardLayout.tsx        0           2          2
ComposerPage.tsx           0           1          1
```

Added by `d027f16bd` ("close 80 bugs from the parallel batch") — a fixer agent
reached for the native dialog. **Fix: replace all four with the in-app
confirm dialog the rest of the product uses.** Ranked high: it is a real UX
regression, not a test artefact.

---

## 2. Pre-existing on `feat/conditional-gates` — backend (71)

**Provenance.** The eight files carrying the bulk of these were run against
`602296cc8` in a detached worktree: **36 failed + 10 errors**, which is
exactly what the same eight produce after the merge. The merge moved none of
them. The merge also never touched the `prototype_*_revision` manifests, and
`playwright_smoke_test` arrived earlier on `feat/conditional-gates` in
`bc0a0366e` (spec 018).

### B-01 · `prototype_*_revision` roster ↔ workflow.yaml drift (15)
The registry roster and the manifest step order disagree for all three
revision pipelines. Almost certainly ONE root cause; fix it once.

- `test_registry.py` ×7 — roster order + "registry is missing agents from yaml"
- `test_id_alias_resolver.py` ×3 — compiled agent sequence ≠ registry order
- `test_manifest_coverage.py` ×3 — "manifest step order has drifted from recorded"
- `test_wire_parity.py` ×1 — run_events→SSE projection diverged (prototype_revision)
- `test_characterization_prototype_revision.py` ×1 — normalized event stream diverged

### B-02 · `playwright_smoke_test` breaks the manifest parity contract (4)
The spec-018 workflow was added without meeting the parity rules every other
manifest obeys.

- must declare `planner: run` — declares `skip`
- `clarify.defaults` must reproduce the engine dict — is `[]`, expected
  `['target_audience', …, 'priority']`
- `test_manifest_parity.py` ×2, `test_id_alias_resolver.py` ×2

### B-03 · hardcoded count pins that new work moved (4)
Each is a one-line pin, but check WHAT was added before bumping it.

| test | pin | actual |
|---|---|---|
| `test_compiled_plan_runs.py::test_dispatchable_count_is_13` | 24 | 25 |
| `test_manifest_coverage.py::test_exactly_18_keys` | 29 | 30 |
| `test_model_pricing.py::test_pricing_covers_every_catalog_model` | 8 | 9 |
| `test_skills_catalog_hygiene.py::test_catalog_has_exactly_185_entries` | 185 | 186 |

### B-04 · FIX-323 gate removal, backend leftovers (3)
Same root cause as the three gate tests already fixed in this merge: the
prototype static gates are gone (AGENT.md *and* workflow.yaml), the user opts
in via `gate_agent_ids`. These still expect `'Human_Gate'`.

- `test_agents_api_real_registry.py` ×2 — `assert None == 'Human_Gate'`
- `test_phase6_frontend_consistency.py` ×1 — gate values diverge, frontend vs registry

### B-05 · pipeline_failed / degraded event semantics (7)
Extra events in the terminal payload — `expected exactly one pipeline_failed`,
`assert 5 == 1`, `assert 6 == 2`. Looks like one behaviour change with seven
witnesses.

- `test_pipeline_failure_semantics.py` ×5, `test_engine_runner_error_arm.py` ×2

### B-06 · revision-analyzer endpoint returns 500 (21)
`tests/integration/test_revision_analyzer_integration.py` — the endpoint 500s
where 200 is expected; the 10 `RuntimeError: This portal is not running`
entries are teardown fallout from the same failures, not separate bugs. Fix
the 500 and the errors should go with it. Biggest single cluster.

### B-07 · revision refs / lineage (6)
- `test_revision_intelligence.py` ×2 — "expected exactly one exact-kind revision ref"
- `test_run_revision_fe_contract.py` ×2 — `list index out of range` in the event payload
- `test_concierge_proposal_channels.py` ×1 — wrong tier target
- `test_revision_gating.py` ×1 — seeded artifact list mismatch

Possibly downstream of B-01/B-06 — retest after those.

### B-08 · chunk sanitizer breaks byte-identity (4)
`test_chunk_sanitizer.py` — the sanitizer perturbs streams it must pass
through untouched (tool-using agent, clean tool-less, lone `<` at a chunk
boundary, benign held tail at flush). Content-loss risk; worth ranking high.

### B-09 · singles (7)
- `test_alembic.py` — **migration drift**: `upgrade` then `check` reports
  undeclared operations. Worth its own look, it means a model has no migration.
- `test_tool_grant_invariants.py` — agents declare a filesystem tool set their
  workflow does not grant
- `test_text_only_prompt_hygiene.py` — fabricated XML not stripped
- `test_phase5_revision_validation.py` ×2 — ghost route not removed; phantom
  second agent in the fix loop
- `test_phase8_live.py` — offline chained revision output missing `<h1>Home</h1>`
- `test_workflows_api.py` — list payload's chained_from/short_name set differs

---

## 3. Pre-existing — eslint (24 errors)

Identical count on `602296cc8` (305 problems / 24 errors) and after the merge
(320 / 24); only line numbers moved. Structural React-correctness rules, not
style:

| file | errors |
|---|---|
| `src/app/[...view]/page.tsx` | 8 |
| `src/components/chat/runtime/useMeasuredVirtualWindow.ts` | 7 |
| `src/app/not-found.tsx` | 4 (trivial — unescaped `'`) |
| `src/components/workflow/composer/CanvasConfigRail.tsx` | 2 (conditional hooks) |
| `src/components/layout/DashboardLayout.tsx` | 2 |
| `src/components/workflow/LaunchWizard.tsx` | 1 |

These do NOT block a merge commit — pre-commit runs "merge-conflict files
only" — but they WILL block an ordinary commit touching those files.

---

## 4. Data damage from the weekend hunt (not a code bug)

`My presentation` (`da92b4a4-7eff-41b5-9b9a-205cfa1616d9`) lost its 4th agent
`report-generator`; a hunt run overwrote the row (`created 2026-08-25 17:44`,
`updated 2026-08-29 12:17`). It is now the plain 3-agent ppt base, so D-05 —
saved roster (4) vs launch panel (3) — cannot be observed. `S-05-10` skips
with a message naming exactly what to restore, and starts running again by
itself once the agent is back.

The same DB now holds 41 saved workflows including hunt artefacts
(`Bug Validate PPT Copy C1/C2`, `PPT Save Flow Test 2`, `QA Gate Reject Test`).

---

## 5. Open finding worth a card

The `"Workflow versions"` region that `21-run-families-and-versions.feature.md`
specifies for S-21-07/08/09 lives in `RunDetailPage`, which **no user path
mounts** — `WorkflowHistory.handleSelectRun` routes every tap to the shared run
screen (BUG-002), whose version control is `RunHeader`'s Version *menu*. The
code calls retiring the internal detail an open INV-3 follow-up. Either the
spec or the app is wrong; the three scenarios are skipped with that reason
recorded until someone decides which.


---

## 6. Integration sweep (23)

Full offline run, 2026-08-30 23:10 → 00:05, `test-runs/2026-08-30T23-10-offline`
(753 shots). Four distinct themes; only F-02 above is a genuine regression.

### I-01 · GOOD NEWS — four bugs are fixed, the xfails are stale (4)
`XPASS(strict)` means the guard passed: the bug it pins is gone. **Fix:
delete the xfail marker and let the test stand as a plain regression guard.**
Check each one by hand first — a strict XPASS is a claim, not proof.

- `test_iss592_agent_detail_close_preserves_filter.py` — ISS-592
- `test_iss593_skill_detail_close_preserves_filter.py` — ISS-593
- `test_iss594_hook_detail_back_button_loses_search.py` — ISS-594
- `test_settings.py::test_clear_constitution_requires_confirmation_before_deleting` — ISS-320

A fifth of the same kind: `test_overlays.py::test_inspecting_a_catalog_workflow_
describes_it_without_launching` reports "Escape now closes the inspect dialog"
— that defect is fixed too, so S-15-01 can be asserted in full and S-20-01
gains a row.

### I-02 · the revision family, again (7)
The same discovery that fired suite 21's tripwires: this history now holds a
real family, and the first row is the family root. Everything here follows
from that and is a TEST fix, not an app fix — the pattern is already solved in
`suites/21_run_families_and_versions` and in `RH.chip_count`, copy it.

- `test_run_history.py::test_type_filter_counts_sum_to_the_total` — `49 == 50`.
  The chips count FAMILIES, the headline counts RUNS; one family of two makes
  them differ by exactly one. Compare against the family-row count (as S-21-05
  now does), not `RH.total()`.
- `test_run_history.py::test_opening_a_row_lands_on_that_run` — clicking a
  family row opens its LATEST member, whose brief differs from the root's row
  label. Assert on the member's identity, or pick a non-family row.
- `test_run_detail.py::test_switching_tabs_does_not_wipe_run_state` —
  `'USER STORIES' not in 'USER STORIES REVISION'`. A substring check meant to
  catch the "USER STORIES" fallback trips on a legitimately-named revision.
  Match the whole label, not a substring.
- `test_errors.py::test_a_nonexistent_artifact_version_falls_back_to_v1…` —
  lands on the family's v2 and looks for "v1". Needs a single-version run.
- `test_run_detail.py::test_workspace_lists_the_runs_files_and_starts_unselected`
  — the rail reports no file count on that revision run.
- `test_composer_canvas.py::test_editing_a_saved_workflow_loads_its_steps` —
  `3 == 4`: the `My presentation` data damage in §4, not a family issue.
- `test_run_history.py` Presentation chip ×3 (see I-03).

### I-03 · no `ppt` runs left in run history (3)
The Presentation chip is not rendered at all, because no family buckets to
`ppt`. `chip_count` now returns 0 instead of burning a 30s timeout, but three
tests still *click* the chip:

- `test_filtering_by_type_narrows_the_list[Presentation]` — timeout
- `test_the_chip_label_and_its_url_value_are_different_words` — timeout
- `test_an_unrecognised_type_shows_an_empty_list_rather_than_an_error` —
  its own message says it: "the contradiction D-15 records has gone, so
  re-read that defect before changing this test"

**Decide first whether the ppt runs SHOULD be gone.** `filterBucketFor` maps
every type to one of 4 frameworks or "custom", so a ppt run would still bucket
to `ppt` — their absence is a data fact, not a bucketing bug. If ppt runs are
expected, this is a data-loss finding, not a test fix.

### I-04 · genuine app findings (5)
- `test_iss_606_609_version_pin_ignored_by_agent_data.py::test_audit_tab_
  fetches_the_pinned_versions_own_run_id` (**ISS-609**) — the Audit tab pinned
  to v2 still fetches the ROOT run's `gate-events`. The version-pin fix did not
  reach this tab. Real bug.
- `test_shell_nav.py::test_every_top_level_screen_survives_a_hard_refresh
  [/library?tab=hooks]` — `assert 0 > 0`: the page rendered an EMPTY body on a
  hard refresh. Only that one route of the five. Worth a real look.
- `test_iss340_simple_canvas_deliverable_agree.py` ×2 — Simple says
  "ppt — declared by this workflow" / "Single file", Canvas says "Streamed
  text — agent's raw output". ISS-340 regression: the two views disagree.
- `test_composer_canvas.py::test_a_last_streamed_built_in_refuses_an_append_
  after_final_step_slot` — locator never visible.

### I-05 · stale against features already on `feat/conditional-gates` (1)
- `test_overlays.py::test_share_copies_a_link_rather_than_opening_a_dialog` —
  looks for `aria-label="Copy a link to this run"`; the button is now
  `"Share this run"`. Renamed by `b69f25696 feat(share): Option B public share
  link`, which is on `feat/conditional-gates`, not from this merge. Test fix.

### I-06 · test hygiene, false positive (1)
- `test_pages_outside_routes.py::test_an_api_key_is_shown_once_and_never_again`
  — "the plaintext key was shown again: validato…". The token-shaped regex
  matched the NAME of a leftover key (`validator-handoff-fixture`) from an
  earlier run, not a plaintext secret. The key was never re-shown. Narrow the
  regex, or exclude names already on the page before the create.

### Suggested order
1. **F-02** — native `confirm()` back in 3 files (real UX regression, ours)
2. **I-04** ISS-609 audit-tab pin + the empty `/library?tab=hooks` body
3. **I-01** — delete 4 stale xfails + the S-15-01 defect pin (free wins, they
   record work already done)
4. **I-03** — settle whether the ppt runs should exist before touching tests
5. **I-02 / I-05 / I-06** — mechanical test updates
