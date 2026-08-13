---
phase: quick-260813-as6
plan: 01
status: complete
completed_tasks: 2
total_tasks: 2
files_modified:
  - backend/tests/unit/test_rest_revisions.py
  - backend/app/api/run_commands.py
commits:
  - a5588f05 test(tests): add failing revision-driver output-column spec
  - e127684e fix(api): wire the revision driver's terminal write to output columns
gates:
  revisions_suite_isolated_red: "1 test, FAILED (row.output None where a real string expected)"
  revisions_suite_isolated_green: "1 test, PASSED"
  revisions_suite_full: "15 collected -- 13 passed, 2 failed (both pre-existing, unrelated -- see below)"
  run_launch_suite_full: "25 collected -- 23 passed, 2 failed (both pre-existing, unrelated -- see below)"
  characterization_goldens: "10 passed, 0 fixtures modified"
  lint_imports: "4 kept, 0 broken"
  live_verified: true
---

# Quick 260813-as6 -- the revision driver silently dropped 7 WorkflowRun output columns

## Status: complete. Both tasks executed, committed, every gate observed, live-verified on Bedrock.

## What was wrong

`_drive_revision_to_queue` (`backend/app/api/run_commands.py:2764`) is the app-layer dispatch
path for **every** `*_revision` pipeline run -- Concierge disposal, chat `CHANNEL_REVISION`, and
`POST /{id}/revisions` all funnel into it. Its terminal-write closure,
`_persist_terminal_status`, wrote only `status` and `completed_at`. It never called
`_apply_terminal_output_columns` (`:2237`), the function documented as "the SINGLE
event->WorkflowRun output-column mapping" and already wired into the launch driver
(`_drive_launch_to_queue`) and both resume entry points (restart auto-resume, user-resume).

This was the fourth caller `BUG-R03` / `QUICK-260719-hvn` (commit `d68b8b75`) never wired. That
fix's own investigation cleared the revision driver by grepping it for `.output`/`.agent_outputs`
**reads** and finding none -- it never checked whether the driver **wrote** them either.

Verified against the only revision that has ever completed in this database
(`8a970205-5892-466a-89b0-f613b9dd021d`): all 7 columns (`output`, `agent_outputs`,
`token_usage`, `duration`, `model_id`, `deliverable_mimetype`, `deliverable_filename`) were NULL
despite a real deliverable existing on disk and in `run_events`. The engine was not at fault:
`_handle_revision` (`agents/execution_engine/engine.py:6360-6612`) forwards every event --
including the single `pipeline_complete` emitter's full payload -- verbatim through the
caller-supplied `websocket_send_fn` at `engine.py:6612`. The data was always reaching the driver;
`_queue_send` just never accumulated it into a replayable list.

Blast radius: Analytics counted every revision as $0 cost and, as a `status=="completed"` row
with a zero-duration numerator, actively dragged down `avg_duration`. The Run Detail KPI strip
hid entirely (`if r.duration ...` gates). `GET /{id}/chain-context` returned an empty context
block for any pipeline chained off a revision. And it silently defeated FIX-249 (the Concierge
`get_token_usage` tool, shipped the same session, commit `7d39a1e1`) for every revision run --
the tool degrades to `{"available": false}` whenever `token_usage` is NULL, and for a revision it
always was.

## What changed

One driver function, mirroring the launch driver's existing pattern byte-for-byte:

- Added `raw_events: list[tuple[str, dict]] = []` and `monotonic_start = time.monotonic()`
  alongside the existing status-seen booleans in `_drive_revision_to_queue`.
- `_queue_send` now appends `(etype or "", event.get("data") or {})` to `raw_events` for **every**
  event, unconditionally -- before the existing status-flag branches.
- `_persist_terminal_status` now calls
  `_apply_terminal_output_columns(swr, raw_events, model_id=getattr(user, "preferred_model", None) or None, duration_seconds=round(time.monotonic() - monotonic_start, 1))`
  inside its existing session, after `status`/`completed_at` and before `sdb.commit()` -- one
  session, one commit, matching the launch driver exactly.
- `duration_seconds` deliberately uses the driver's **own** monotonic clock, never
  `pipeline_complete.total_duration` -- so the pre-existing ISS-150 (two disagreeing duration
  numbers) does not gain a third source.
- `_apply_terminal_output_columns`'s own docstring, which enumerates its callers, is corrected to
  name the revision driver as the fourth caller instead of claiming only launch + two resume
  entry points.

`git diff --stat` on the implementation commit:

```
 backend/app/api/run_commands.py | 24 +++++++++++++++++++---
 1 file changed, 24 insertions(+), 4 deletions(-)
```

Nothing else changed. No engine edit. `_apply_terminal_output_columns` itself is untouched code
(only its docstring), so it stays the sole writer -- no second implementation (INV-3/INV-12).

## Evidence -- every run, verbatim

### Gate 1a -- RED, isolated, against unmodified `run_commands.py`

```
tests/unit/test_rest_revisions.py::test_driver_happy_path_persists_output_columns FAILED [100%]

=================================== FAILURES ===================================
________________ test_driver_happy_path_persists_output_columns ________________
tests/unit/test_rest_revisions.py:329: in test_driver_happy_path_persists_output_columns
    assert row.output == "<html>revised</html>"
E   AssertionError: assert None == '<html>revised</html>'
E    +  where None = <app.models.workflow.WorkflowRun object at 0x10db421d0>.output
========================= 1 failed, 1 warning in 0.83s =========================
```

### Gate 1b -- GREEN, isolated, after the fix

```
tests/unit/test_rest_revisions.py::test_driver_happy_path_persists_output_columns PASSED [100%]
========================= 1 passed, 1 warning in 0.69s =========================
```

### Gate 2 -- full regression set, at the committed state (`e127684e`)

`test_rest_revisions.py`: **15 collected, 13 passed, 2 failed.**
`test_rest_run_launch.py`: **25 collected, 23 passed, 2 failed.**

All 4 failures are **pre-existing and unrelated** -- proven, not asserted. I checked out an
unmodified worktree at the pre-fix commit `48c76403` (via `git worktree add`, never `git stash`)
and ran the identical 4 tests there:

```
FAILED tests/unit/test_rest_revisions.py::test_owned_parent_mints_linked_child - AttributeError: '_FakeUser' object has no attribute 'tier'
FAILED tests/unit/test_rest_revisions.py::test_agent_count_derives_for_ppt_revision - AttributeError: '_FakeUser' object has no attribute 'tier'
FAILED tests/unit/test_rest_run_launch.py::test_unsatisfiable_custom_composition_rejected_pre_mint - AssertionError: ... assert 200 == 422
FAILED tests/unit/test_rest_run_launch.py::test_owned_source_links_the_child - AssertionError: assert None == '<uuid>'
```

Byte-identical error messages both sides. The `AttributeError: '_FakeUser' object has no
attribute 'tier'` failures are a documented, already-tracked defect class -- `.planning/ISSUES-REGISTER.md`
rows ISS-102 and ISS-119 describe the exact same stale-test-double symptom in a different test
file (`test_chat_messages_endpoint.py`), against the same KAN-161/ISS-055 entitlement-gate read of
`user.tier`. This fix touches neither `_mint_revision_row` nor any launch-side parent-linking or
custom-composition code -- `git diff --stat` on both commits confirms the diff is scoped to
exactly `test_rest_revisions.py` and `run_commands.py`'s `_drive_revision_to_queue` /
`_apply_terminal_output_columns` docstring. Worktree removed after comparison.

### Gate 3 -- characterization goldens

```
tests/agents/test_characterization_app_builder.py::test_app_builder_deliverable_byte_snapshot PASSED
tests/agents/test_characterization_app_builder.py::test_app_builder_event_snapshot PASSED
tests/agents/test_characterization_od_ppt.py::test_od_ppt_deliverable_byte_snapshot PASSED
tests/agents/test_characterization_od_ppt.py::test_od_ppt_event_snapshot PASSED
tests/agents/test_characterization_od_prototype.py::test_od_prototype_deliverable_byte_snapshot PASSED
tests/agents/test_characterization_od_prototype.py::test_od_prototype_event_snapshot PASSED
tests/agents/test_characterization_prototype_revision.py::test_prototype_revision_deliverable_byte_snapshot PASSED
tests/agents/test_characterization_prototype_revision.py::test_prototype_revision_event_snapshot PASSED
tests/agents/test_characterization_prototype.py::test_prototype_deliverable_byte_snapshot PASSED
tests/agents/test_characterization_prototype.py::test_prototype_event_snapshot PASSED
======================== 10 passed, 1 warning in 35.21s ========================
```

**10 passed.** `git status --porcelain` after: only the untracked quick-task directory --
**zero golden fixture files touched.**

### Gate 4 -- import-linter, cwd exactly `backend/`

```
kernel imports only capability ports (scaffold) KEPT
agents.workflows must not import the execution kernel or the web layer KEPT
agents.capabilities must not import the execution kernel or the web layer KEPT
agents.runtime must not import the execution kernel or the web layer KEPT

Contracts: 4 kept, 0 broken.
```

## Live verification (Bedrock, `user_stories` only -- cost ~$0.01-0.02 total)

Backend restarted first (uvicorn runs without `--reload` here) so the live pass actually exercised
the fixed code, not a stale in-memory copy. AWS SSO confirmed live via a real Bedrock model call
inside the run itself (`botocore.tokens: SSO Token refresh succeeded`, then a real Haiku 4.5
completion), not `aws sts get-caller-identity`.

**Dispatch note:** the prescribed script (`31-revise-confirm.mjs`, chat-driven via the Concierge)
was tried first and did NOT create a new revision -- the Concierge classified the chat message as
a `gate_action` proposal, not `revision` (backend log: `Concierge proposal disposed: run=...
channel=gate_action held=True`). This is unrelated to this fix (the Concierge's proposal
classification code, `run_commands.py` lines ~1009-1262, is untouched by this diff) and is most
likely live-LLM tool-selection variance rather than a deterministic bug -- not investigated
further since it is out of scope, and NOT filed as an issue on a single unreproduced data point.
Switched to the direct, deterministic `POST /{id}/revisions` REST endpoint instead -- one of the
same three entry points that funnel into the exact driver this fix touches, so it proves the fix
equally well without depending on live-model non-determinism.

**Step 1/2 -- dispatch + column proof.** `POST /api/runs/a5d059e1.../revisions` against the
existing completed `user_stories` parent (`SSEPROOFDROP`) with instruction "ISS152PROOF add an
acceptance criterion for orders placed after 5pm requiring next-day manager approval" ->
`run_id=5914e5f1-f21b-4041-9945-c4d9657b2c70`, completed in 8s. `GET /api/runs/5914e5f1...`
verbatim:

```
output: "# Staff Stationery Ordering\n...Given I submit an order at 5:15pm, When the order is
         created, Then it is marked as pending manager approval..."   (the new criterion, verbatim)
agent_outputs: [{"agent_id": "user-story-revision-agent", ..., "duration": 2.13,
                 "input_tokens": 3951, "output_tokens": 294, "total_tokens": 4245}]
token_usage: {"total_input_tokens": 3951, "total_output_tokens": 294, "total_tokens": 4245,
              "estimated_cost_usd": 0.005963, ...}
duration: 2.2
model_id: null   -- CORRECT, not a gap: getattr(user, "preferred_model", None) is None for this
                     QA user, so `None` is exactly what the launch driver would also persist for
                     the same user (parity, not a defect -- the cost estimate still uses the
                     settings.BEDROCK_INFERENCE_PROFILE_ID fallback internally, hence the real
                     non-zero estimated_cost_usd above).
deliverable_mimetype: "text/markdown"
deliverable_filename: "user_stories.md"
error: null
```

All 7 previously-NULL columns populated, mutually consistent (agent_outputs' totals == token_usage's
totals == the Concierge's later answer), matching the shape the investigation predicted for the
one pre-existing row. Disambiguated against a false-positive read: parent v1 has
`total_tokens=24016`, the old un-backfilled v2 (`8a970205`) still has `token_usage=None` -- the
"4.2K tokens" seen everywhere below is uniquely this new row's real number.

**Step 3/4 -- reopen + KPI info (screenshots `33-history-search.png`, `33-opened.png`).** History
search surfaced the family row inline showing `v3 · 4.2K` BEFORE even opening it. Opened via
History -> family defaults to latest (v3): header reads "USER STORIES REVISION · Done ·
Revision: ISS152PROOF add an acceptance criterion for orders · just now · 2s · 4.2K tokens", the
version badge shows `v3`, and the full Product Backlog renders with the new criterion verbatim.
Zero HTTP >=400 responses during the whole pass.

**Step 5 -- Concierge cost question (screenshot `33-concierge-reply.png`) -- THE FIX-249 PROOF.**
Asked in the revision run's own chat lane: *"How many tokens did this run use in total, and what
did it cost?"* Live reply, verbatim: **"This run used 4,245 total tokens and cost an estimated
$0.01."** A real number, not "I can't see that from here" -- matches the row's own
`token_usage.total_tokens=4245` / `estimated_cost_usd≈$0.01` exactly. This is the interaction
FIX-249 (commit `7d39a1e1`, shipped the same session) was defeated on for every revision before
this fix; it is now repaired.

**Step 6 -- Analytics (screenshot `33-analytics.png`).** Total: 78.6M tokens, **Est. Cost $18.28**
across 22 completed runs, non-zero and rendering without error. The "User Stories" (revision)
pipeline-type bucket shows "4 runs · 4.2K · <$0.01" -- consistent with exactly this one new
non-zero revision plus historical zero-token ones; before this fix every revision contributed a
hard `$0.00` / `0` tokens to every bucket it touched (`analytics.py:184-238`, confirmed by reading
the code, not merely inferred).

**No-regression control (screenshot `34-opened-default.png`) -- as directed, re-run post-fix.**
Reopening the family still works (covered above, defaults to the new latest v3). This did NOT
regress.

**A genuine NEW finding surfaced while running the no-regression control, NOT caused by this fix,
NOT fixed here.** Explicitly switching the in-family version picker to the OLDER, non-latest v2
(`8a970205`, deliberately never backfilled) shows an empty "Output will appear here" preview
(screenshot `34-v2-selected.png`) -- the left-column chat/KPI header still reads the v3 numbers
(stale), and the right preview pane is blank. Root cause, read directly:
`frontend/src/components/preview/PreviewPanel.tsx:528-543` `handleSelectVersion` -- switching to
any non-latest family member does `const run = await getWorkflow(token, memberId);
setViewingVersion({ id: memberId, content: run.output })` with NO fallback, so any older version
whose `.output` is null renders empty. This is a DIFFERENT code path from the one the orchestrator
tested (opening the family when `8a970205` WAS still the latest, which uses the live/default
content props, not this explicit older-version fetch) -- the two are not in tension; the
orchestrator's finding stands for the LATEST-version case, mine adds the NON-latest case, which
was structurally impossible to hit before this session (no family had 3 versions to switch
between until this fix's own live test created one). Confirmed NOT introduced by this fix: the
diff here is 100% backend (`run_commands.py`), touches no frontend file, and `8a970205`'s own data
is byte-unchanged (verified via `GET /api/runs/8a970205...` before and after -- still
`token_usage: None`) -- the gap was always latent, this session's fix is simply what first created
the 3-version family needed to expose it. Blast radius going forward is bounded: EVERY new
revision from now on gets a real `.output` (this fix), so this gap's trigger condition (a
completed revision with null `.output`) will not recur for future revisions, only for the small,
fixed, already-existing set of pre-fix rows. **Filed as a new issue, not fixed** -- see the
orchestrator-facing report for the id.

## SURFACED -- NOT DECIDED (for the orchestrator)

**(a) The `wr.error` omission.** `_persist_terminal_status` has no `error` parameter at all --
unlike the launch driver, whose failure branches always set `wr.error`. A revision that reaches
`_persist_terminal_status("failed")` (the `ValueError` branch, the generic `Exception` branch, or
the fail-safe else-branch in the happy-path status ladder) leaves `WorkflowRun.error` `NULL`. All
4 revision rows in this database that ever reached any terminal state -- including the 3 that
failed before dispatch -- carry `error IS NULL`, while failed non-revision runs carry real
messages. **Not fixed here, per the mid-fix filing rule** -- filed as its own new issue by the
bookkeeping pass that follows this SUMMARY.

**(b) The one-row backfill.** The single already-completed revision in this database
(`8a970205-5892-466a-89b0-f613b9dd021d`) could have its 7 columns backfilled losslessly from its
own `run_events` (precedent: `scripts/cutover_legacy_runs.py`; the replay was proven exact by the
investigation that preceded this fix). **Deliberately NOT performed** -- surfaced as an open
decision for the orchestrator, not silently done.

## Scope held

No engine edit. No second implementation of `_apply_terminal_output_columns`. No `wr.error` fix.
No backfill. No FIX/TEST/ISS numbers anywhere in code, comments, or commit messages --
bookkeeping is a separate pass. No `git stash` at any point (a disposable `git worktree` was used
instead, then removed). No golden regenerated.

## Self-Check: PASSED

- `backend/app/api/run_commands.py` -- FOUND, contains `_apply_terminal_output_columns` call inside `_persist_terminal_status`
- `backend/tests/unit/test_rest_revisions.py` -- FOUND, contains `test_driver_happy_path_persists_output_columns`
- commit `a5588f05` -- FOUND in `git log`
- commit `e127684e` -- FOUND in `git log`
