# ESCALATIONS

Bugs from `BUGS.md` that a stage stopped on because they need a human decision. One section per
bug, heading = the bug id. Answer the "Decision needed" question, then set the row back to the
status named under "After the decision".

<!-- STATE -->
| Bug | Ledger status | Updated | Evidence |
|---|---|---|---|
| QA-PS-002 | CLOSED | 2026-09-17 | n/a |
| QA-PS-009 | CLOSED | 2026-09-22 | n/a |
| QA-PS-008 | CLOSED | 2026-09-22 | n/a |
| QA-PS-006 | CLOSED | 2026-09-17 | n/a |
| QA-PS-007 | CLOSED | 2026-09-23 | n/a |
| QA-PS-021 | CLOSED | 2026-09-23 | n/a |
| QA-PS-036 | CLOSED | 2026-09-23 | n/a |
| QA-PS-035 | CLOSED | 2026-09-23 | n/a |
| QA-PS-038 | CLOSED | 2026-09-23 | n/a |
| QA-PS-041 | CLOSED | 2026-09-23 | n/a |
| QA-PS-046 | CLOSED | 2026-09-23 | n/a |
| QA-KB-032 | ESCALATED | 2026-10-01 | missing |
| QA-KB-055 | CLOSED | 2026-10-09 | n/a |
| QA-KB-112 | ANALYZED | 2026-10-12 | n/a |
| QA-KB-114 | ESCALATED | 2026-10-09 | missing |
| QA-KB-117 | CLOSED | 2026-10-12 | n/a |
| QA-KB-121 | CLOSED | 2026-10-12 | n/a |
Last synced: 2026-10-12T08:20:13Z
<!-- /STATE -->


---

## QA-PS-002
> **Now CLOSED** (2026-09-17) — kept for the trace.

**Title:** Notification panel shows 0 of N agents and 0% for all running pipelines · **Route:** (global) · **Stage:** 5-fixer · **Date:** 2026-09-17
**Report:** [BUGS.md#qa-ps-002](BUGS.md#qa-ps-002) · **Cards:** [ISS-644](.knowledge/cards/20260917-0930-ISS-644.md), [ISS-648](.knowledge/cards/20260917-1100-ISS-648.md), [ISS-649](.knowledge/cards/20260917-1105-ISS-649.md), [ISS-658](.knowledge/cards/20260917-1302-ISS-658.md)

### Why escalated
ISS-644 identifies the wrong data path. It blames `updateProgress` in DashboardLayout.tsx:937-941 (updates notification.agentsCompleted), but DashboardLayout.tsx:2670 filters that notification out before drawing, so the panel never shows it. The panel's live "X of N agents" rows come only from AppHeader.tsx:200-211 using runAgentsCompletedMap (which shows 0 when a background run has no store entry). ISS-644's test checks the hidden notification, so fixing ISS-644 would leave the panel displaying "0 of N agents" unchanged.

### Evidence
- ISS-644 root cause (.knowledge/cards/20260917-0930-ISS-644.md) vs. ISS-658 re-read (.knowledge/cards/20260917-1302-ISS-658.md): AppHeader.tsx:190-217 (actual data source), DashboardLayout.tsx:2670 (filters out running notifications), NotificationPanel.tsx:212-214 (does not draw running items)
- backend/app/api/schema.py and types/index.ts: WorkflowRun has agentCount but no completedCount
- page.tsx:3894-3900: runAgentsCompletedMap only has entries for runs whose SSE stream reached this tab
- QA report: three concurrent runs all show 0%, which matches a missing store entry, not a frozen count

### Decision needed
Which approach should we take to find the real root cause and fix the notification panel?

### Options
- **a)** Re-analyze QA-PS-002 against AppHeader.tsx:190-217 and page.tsx:3894-3900, then rewrite ISS-644's test to check the actual rendered panel text. Mark ISS-644 superseded if the reanalysis confirms a different root. Re-run full QA sequence (test, fix, verify).
- **b)** Add a completed-agent count field to GET /api/runs (API schema change in backend/app/api/schema.py and types/index.ts), use it as AppHeader's fallback, and have the fixer implement and verify. Requires design review for API contract change.
- **c)** Client side: implement background run auto-reconnect and/or re-render triggers when a non-viewed run's SSE message arrives (useRunStateStore.ts and RunConnectionProvider.tsx changes). Only helps runs this tab can stream.

### After the decision
Set LEDGER.md Status to `ANALYZED` and LEDGER.md Route to the chosen option's path:
- Option a) → re-dispatch 3-analyzer with route /dashboard,/runs/{id} and ask them to verify ISS-644 against the actual rendered panel
- Option b) → dispatch 5-fixer with route /api/runs and the API schema spec
- Option c) → dispatch 5-fixer with route /hooks,/providers and the background-run reconnect spec

---

## QA-PS-009
> **Now CLOSED** (2026-09-22) — kept for the trace.

**Title:** Analytics model details card incorrectly shows Thinking row for Sonnet 5 · **Route:** /analytics · **Stage:** 5-fixer · **Date:** 2026-09-17
**Report:** [BUGS.md#qa-ps-009](BUGS.md#qa-ps-009) · **Cards:** [ISS-667](.knowledge/cards/20260917-1320-ISS-667.md) (root, resolved by [FIX-524](.knowledge/cards/20260917-1639-FIX-524.md)), [ISS-668](.knowledge/cards/20260917-1325-ISS-668.md) (sibling, open, the subject of this escalation)

History: the first escalation, about whether Sonnet 5's row was intended, was decided on 2026-09-17
([WONTFIX.md#qa-ps-009](WONTFIX.md#qa-ps-009)): keep the row and drop "(effort: max)". That
decision is now implemented. `AnalyticsPage.tsx:829` renders `Adaptive`
([FIX-524](.knowledge/cards/20260917-1639-FIX-524.md)), and the ISS-667 test passes.

**RESOLVED 2026-09-22.** Two corrections to the line above, which was stale: FIX-524 is **not** an
uncommitted working-tree edit — it is committed in `f3f4bbafc`. And it has now been verified:
Bilal decided QA-PS-009 is fixed, the 6-verifier confirmed the ISS-667 test green, `npm run build`
clean, and `/analytics` rendering `Adaptive` with no "(effort: max)"
(`evidence/qa-ps-009/after-sonnet5-adaptive.png`). The LEDGER row is `CLOSED`.

Caveat on that browser leg: it ran on the shared plugin Chrome profile, not an isolated lane
(`disabledMcpjsonServers` had all nine lanes switched off, so none were running). The close does
**not** rest on it — `AnalyticsPage.tsx:826-831` is a static JSX literal reading `Adaptive`, with a
passing unit test and a clean build.

**Isolated re-verify DONE 2026-09-22 09:37 — PASS.** After the session restart brought the lane
MCP servers up, a 6-verifier pinned to `mcp__lane4__*` (headed real Chrome, isolated profile
`/tmp/bughunt-lane4`, fresh sign-in) loaded `/analytics` and read the Sonnet 5 Thinking row as
exactly `Adaptive`. The string `effort: max` matched zero times anywhere on the page (exact and
regex). Zero console errors. Screenshot:
`evidence/qa-ps-009/lane4-isolated-reverify.png`. QA-PS-009's `CLOSED` now rests on an isolated
browser repro as well as the source reasoning — the shared-profile caveat above is superseded.

**ISS-668 is split off and still open** — unchanged by the above, and still needs the product
decision described below. Its test case in `AnalyticsPage.test.tsx` (~396-401) is now marked
`{ fails: true }` with a deferral comment pointing here, so the suite is honestly xfail rather
than silently red.

### Why escalated
The sibling card ISS-668 cannot be fixed without a product decision. ISS-668 says Opus 4.5 and
Opus 4.6 show "Adaptive" but get `enabled` thinking at runtime. Three things block a fix:
1. **The test and a locked constraint contradict each other.** The ISS-668 test expects the row to
   say "Enabled" for Opus 4.5 and "Adaptive" for Sonnet 5. But both catalog fixtures carry the same
   fields (`thinking_supported: true`, no thinking type). The frontend could only tell them apart
   with a model-id list of its own. FIX-491's locked constraint forbids exactly that. ISS-668's own
   proposed fix (one per-model thinking type served by `/api/capabilities`) cannot pass the test
   either, because the fixtures do not carry that field.
2. **The UX is undecided.** ISS-668 lists "hide the row" and "show Enabled" as alternatives and
   does not choose one. The test picked "Enabled" without a recorded decision.
3. **The rule reaches models nobody reported.** Five more catalog models get the same `enabled`
   thinking at runtime and show no row today. Under "show the runtime type" they would gain a row,
   which contradicts the reporter's view that Haiku 4.5 correctly has none. Under "the row means
   adaptive" the fix is removing `"opus-4"` from `_THINKING_FRAGMENTS`, which the first decision
   said not to touch.

### Evidence
- `frontend/src/components/analytics/AnalyticsPage.test.tsx:383-388` vs `:397-402`: the fixtures
  differ only in `id`, `label` and `tier`. Both are `{ ..., context_window: 200000, thinking_supported: true }`.
- `.knowledge/cards/20260907-1239-FIX-491.md:17`, locked constraint: "model metadata must come from
  /api/capabilities live catalog (INV-12 single-source; SC-001 no hardcoded model-id list on frontend)."
- `.knowledge/cards/20260917-1325-ISS-668.md` § Expected: "Either the row is not shown for Opus
  4.5/4.6 at all ..., or it shows text matching what the model actually gets ("Enabled" / budget-based)".
- `.knowledge/cards/20260917-1320-ISS-667.md` § Product decision: "do NOT change `_THINKING_FRAGMENTS`
  / `_ADAPTIVE_THINKING_MODEL_FRAGMENTS`".
- `backend/app/api/capabilities.py:169`: `_THINKING_FRAGMENTS = ("sonnet-5", "opus-5", "fable-5", "mythos-5", "opus-4")`.
  Its comment at `:165-168` says these are the models that "support adaptive thinking".
- `backend/app/agents/model_factory.py:123`: `_ADAPTIVE_THINKING_MODEL_FRAGMENTS = ("sonnet-5", "opus-5", "fable-5", "mythos-5")`.
  `:126` is `return "adaptive" if any(f in mid for f in _ADAPTIVE_THINKING_MODEL_FRAGMENTS) else "enabled"`.
  `:115` is `thinking_enabled = settings.THINKING_BUDGET_TOKENS > 0 and not disable_thinking`.
  `:196-199` builds `{"type": t_type}` and adds `budget_tokens` when the type is `enabled`.
  `grep -rn '"thinking"\]' backend --include='*.py' | grep -v /tests/` returns only
  `model_factory.py:139, 142, 200, 203`, which build the request, and `execution_engine/engine.py:8392`,
  which is an `agent_thinking` SSE event and not a request field.
- `backend/app/core/config.py:170`: `THINKING_BUDGET_TOKENS: int = 32767`.
- `backend/agents/capabilities/model_catalog.py:74, 91, 103, 115, 168`: Haiku 4.5, Haiku 3.5, Sonnet
  4.5, Sonnet 4.6 and Sonnet 4. All get `enabled` thinking at runtime, and none matches
  `_THINKING_FRAGMENTS`, so none shows a row.
- `BUGS.md#qa-ps-009` § Actual: "The Haiku 4.5 card directly above it does not show a Thinking row, which is correct."
- Test run observed by the 5-fixer, one file (`cd frontend && npx vitest --run src/components/analytics/AnalyticsPage.test.tsx`):
  7 failed / 9 passed before FIX-524, 6 failed / 10 passed after. With `-t "QA-PS-009"` after the fix:
  ISS-667 passed, and ISS-668 failed with "Unable to find an element with the text: Enabled".

### Decision needed
For models that get `enabled` (budget-based) thinking at runtime, should the Model Details panel hide
the Thinking row, or show "Thinking: Enabled"? This covers Opus 4.5 and 4.6 and, by the same code
path, Haiku 4.5, Haiku 3.5 and Sonnet 4 / 4.5 / 4.6.

### Options
- **a) Hide it: the row means "adaptive".** Remove `"opus-4"` from `_THINKING_FRAGMENTS`
  (`capabilities.py:169`). This makes it match `model_factory.py:123` and its own comment, and
  overrides the "do not change the tuples" line for this one fragment. Opus 4.5 and 4.6 lose the
  row, and every remaining row really is adaptive. It is a one-token backend change. The ISS-668
  test must be rewritten to expect no row.
- **b) Show "Enabled": the row shows the runtime type.** Serve one per-model thinking type from
  `/api/capabilities`, read by both `capabilities.py` and `model_factory.py` (ISS-668's proposed
  location). Adding the optional field does not break the API, but the tuples get refactored. Haiku
  4.5, Haiku 3.5 and Sonnet 4 / 4.5 / 4.6 then show "Thinking: Enabled" too, contrary to the
  report. Both QA-PS-009 test fixtures must carry the new field.
- **c) Show "Enabled" for Opus 4.5 and 4.6 only, from a frontend model-id list.** This is the only
  way the current ISS-668 test passes unchanged. It overrides FIX-491's locked constraint and adds a
  third hand-synced fragment list, which is the drift ISS-668 describes. Not recommended.
- **d) Split ISS-668 off.** Move it to its own register entry, or won't-fix it, and remove its
  test from `AnalyticsPage.test.tsx`. QA-PS-009 then closes on ISS-667 alone, and Opus 4.5 and 4.6
  keep showing "Adaptive" until the split entry is decided.

### After the decision
Record the decision on [ISS-668](.knowledge/cards/20260917-1325-ISS-668.md), then:
- a) or b): set the QA-PS-009 row in LEDGER.md to `ANALYZED`. The 4-test-writer rewrites the ISS-668
  test (and for b, both fixtures), then fix → verify. The FIX-524 label edit stays as it is.
- c): set the row to `TESTED` and record the FIX-491 override on ISS-668. The 5-fixer implements
  against the existing test.
- d): remove the ISS-668 test and card link from this bug, then set the row to `FIXED`. The
  6-verifier verifies FIX-524 (ISS-667 test, plus the `/analytics` Sonnet 5 reproduction in the
  browser).

---

## QA-PS-008
> **Now CLOSED** (2026-09-22) — kept for the trace.

**Title:** Version dropdown shows inflated version list and preview fails for all non-live versions · **Route:** /runs/{id} · **Stage:** 5-fixer · **Date:** 2026-09-17
**Report:** [BUGS.md#qa-ps-008](BUGS.md#qa-ps-008) · **Cards:** [ISS-652](.knowledge/cards/20260917-1244-ISS-652.md) (root), [ISS-663](.knowledge/cards/20260917-1310-ISS-663.md), [ISS-665](.knowledge/cards/20260917-1311-ISS-665.md)

### Why escalated
ISS-652 gets the source of the leaked tags wrong, and the ISS-652/ISS-663 test was written from
that wrong explanation. The card says the sandbox's own git repo holds deploy/release tags that
no family member created, and it proposes filtering `list_tags()` against the family's
`WorkflowRun.git_tag` values. That is not what happened. This family's chain-root sandbox is an
empty directory with no `.git` of its own. `LocalWorkspace` runs git with only `cwd` set
(`backend/app/agents/runtime/local.py:372-390`, plus direct `subprocess.check_output` git calls
at `local.py:1062`, `:1081`, `:1104`). So git searches upward from the sandbox and uses the
repository that contains it. Here that is the Flowin source checkout itself, because
`RUNS_ROOT=../runs` (`backend/.env:8`) is inside it. The seven "versions" QA saw are the Flowin
repo's own tags.

The test `backend/tests/unit/test_run_files_ref_family_scope.py` creates its leaked tag inside
the sandbox's own repo (line 156), which is a different situation from the one QA hit. A fix at
the real cause leaves that test XFAIL. Only the card's DB filter turns it XPASS, and that filter
leaves every other git caller still reading from the parent repo. Making the test pass would
mean bending the app to match a test built on the wrong explanation.

### Evidence
- The repro family's chain root is
  `runs/c6b9b61f-183d-4662-ae84-d7fd5a052571/2708dbf1-50d0-465d-9bed-56b651ea1abf/`. Revision
  `23bd9c67-e239-4979-b14a-cb78222795e8` shares it. The directory is empty and has no `.git`.
  `git rev-parse --show-toplevel` run there returns `/Users/bilala/Developer/Projects/VELOCITY-AI`.
  `git tag --list` run there returns `deploy-prod-20260603-012557, deploy-prod-20260603-014226,
  pre-fixes-reset, pre-rebase-safety, v0.0.1, v0.0.2, v0.2.0`, which is identical to the project
  repo's own `git tag --list`.
- On this machine, 87 of the 103 run dirs under `runs/` have no `.git`. The 16 that do have one
  hold only `v1` or no tags, and none has a deploy/release tag. The only production tag writer
  is finalize (`backend/agents/execution_engine/engine.py:2283-2285`), and it deletes the tag
  again if the DB mapping fails (`engine.py:2329`).
- The API builds the sandbox with the default `has_git=True` (`backend/app/api/run_files.py:663,
  698, 792, 889`; `backend/app/agents/sandbox.py:546`). `RunSandbox.list_tags` checks only that
  flag and never checks whether `.git` exists (`sandbox.py:896`).
- Offline probe, run in the scratchpad against a throwaway outer repo (the project repo was not
  touched): a `RunSandbox` with no `.git`, nested in an outer repo tagged `deploy-prod-host`.
  `list_tags()` returned `['deploy-prod-host']`, and
  `_ws().read_file_at_ref('deploy-prod-host', 'secretdir/config.py')` returned the outer repo's
  file bytes. So ISS-663 understates the impact:
  `GET /api/runs/{id}/sandbox/file?ref=<host tag>&path=<repo-root-relative path>` would serve
  Flowin's own source at that tag, not "sandbox content at an unrelated tag". Not tried against
  the live backend.
- Callers no card covers that reach git the same way: `backend/app/api/runs.py:2307-2330`
  `_validate_tag_for_restore` accepts the parent repo's tags. For a sandbox with no `.git`,
  `restore_version` would then run `git restore` and `commit_in_sandbox` (`git add -A` +
  `git commit`) with cwd inside the host checkout. I traced this path but did not run it.
  `sandbox.py:1846-1882` `_validate_ref_against_tags` and the diagnostic at `engine.py:2351` have
  the same problem.
- ISS-665 does not depend on any of this. `frontend/src/lib/api.ts:1175-1192`
  `resolveRunDeliverable` has no `ref` parameter, and its test
  `frontend/src/lib/api.resolveRunDeliverableRef.test.ts` is correct as written.

### Decision needed
Where should the leaked-tag fix go: stop git from searching outside the sandbox (the real cause,
covers every caller), filter the API's tag lists against the family's DB tags (the card's fix,
which the existing test checks), or both?

### Options
- **a)** Fix the root cause in `backend/app/agents/runtime/local.py`: stop git from searching
  above the sandbox, for example by setting `GIT_CEILING_DIRECTORIES` to the sandbox's parent
  in `_git` and in the three direct `check_output` calls. A sandbox with no `.git` then gets
  "not a git repository", which means no tags and every ref rejected. Consequence: one change
  fixes `/sandbox/refs`, the three ref endpoints, restore, chain exact-ref validation and the
  engine diagnostic. ISS-652/ISS-663 need a replacement card with the corrected cause, and their
  test must be rewritten to model a sandbox with no `.git` inside a tagged outer repo.
- **b)** Apply the card's fix as written: filter `/sandbox/refs` and `_validate_ref` in
  `run_files.py` against the family's `git_tag` column. Consequence: the existing test goes
  XPASS and the QA symptom disappears. But the recorded root cause stays wrong, and
  `restore_version` and `_validate_ref_against_tags` still accept the parent repo's tags and
  still run git inside the host checkout.
- **c)** Both: (a) as the fix, plus (b) as a second layer extended to `runs.py`
  `_validate_tag_for_restore`. Consequence: the biggest diff. It needs the new test from (a),
  keeps the existing test, and touches `runs.py`, which no current card's globs cover.
- Whichever option is chosen, ISS-665 (pass `ref` through `resolveRunDeliverable` into
  `FilesTab`) can be fixed by itself.

### After the decision
- Option a) or c): set `LEDGER.md` QA-PS-008 Status to `CONFIRMED`. 3-analyzer then writes a
  card that replaces ISS-652/ISS-663 with the corrected cause and full caller list (adding
  `runs.py` for c), 4-test-writer adds the nested-repo test, and 5-fixer applies the fix
  together with ISS-665.
- Option b): set Status to `TESTED` and re-dispatch 5-fixer with an explicit note that the
  card's DB filter is accepted as-is and the remaining callers will be tracked separately.

---

## QA-PS-006
> **Now CLOSED** (2026-09-17) — kept for the trace.

Backend restart confirmed FIX-520 works live; agent name now visible on review-required messages. See WONTFIX.md#qa-ps-006 for design decision context.

**Title:** "Review required" messages in concierge chat show no agent name, all look identical · **Route:** /runs/{id} · **Stage:** 6-verifier · **Date:** 2026-09-17
**Report:** [BUGS.md#qa-ps-006](BUGS.md#qa-ps-006) · **Cards:** [ISS-653](.knowledge/cards/20260917-1050-ISS-653.md) (root), [FIX-520](.knowledge/cards/20260917-1338-FIX-520.md)

### Why escalated
Same process blocker as QA-PS-004, same backend process. `frontend/src/components/chat/ResultCard.test.tsx`
is green (16/16; the two ISS-653 cases XPASSed, `xfail` marker removed, now plain passing). The
`ResultCard.tsx:148-150` code on disk does carry the fix (`message.agentName ? \`${message.agentName}
review required\` : "Review required"`). `tsc --noEmit` shows only the 6 pre-existing errors in
unrelated test files (`DashboardLayout.chain.test.tsx`, `WorkflowHistory.modelChip.test.tsx`,
`RunConnectionProvider.test.tsx`), matching FIX-520's own record; no new build error. `:3000` and
`:8000/docs` both answer.

But this fix depends on `agentName` reaching the frontend at all, which is FIX-518's backend
plumbing (`chat_narrator.py`) — the same file QA-PS-004 already found stale. Manual re-repro on
the live `github dashboard user story` run (`386d76da-53dd-4185-81d9-2fb62ea9339f`, still
`waiting_for_user`, `qa-admin@flowinqa.com`) shows the pending Domain Discovery Agent gate reading
the bare "Review required" — no agent name — exactly the pre-fix text. A sweep of every gate
`chat_reply` across the 8 most recent runs with a review gate (including two `chat_reply` on this
same run, the most recent at 11:36:54 UTC / 13:36:54 local) found `agent_name: null` on every one.

The `:8000` process (pid 97444) started 11:21:32 with no `--reload` flag; `chat_narrator.py`'s
`agent_name` stamping (FIX-518) has mtime 13:17, after the process started. It is still serving
pre-FIX-518 code as of 13:44 — 27 minutes after the file changed. This is the identical blocker
QA-PS-004 already escalated; restarting `:8000` fixes both bugs' manual repro in one action.

### Evidence
- `ps -ef -ww | grep "port 8000"`: pid 97444, started 11:21AM, no `--reload` flag
- `ls -la backend/app/agents/chat_narrator.py`: mtime 13:17, after process start
- `frontend/src/components/chat/ResultCard.test.tsx`: 16 passed (0 failed) after `xfail` removal
- Live run `386d76da-53dd-4185-81d9-2fb62ea9339f`: pending `review_gate_ready` (seq 1174) carries
  `agent_name: "Domain Discovery Agent"`; both its `chat_reply`/`gate` cards (11:34:36 and
  11:36:54 UTC) have no `agent_name` key; browser chat lane shows bare "Review required"

### Decision needed
Same as QA-PS-004: restart the `:8000` backend process, then re-run the manual repro for both
bugs together.

### After the decision
Once restarted: open (or wait for) a run with a pending review gate started after the restart,
confirm the chat lane reads "<Agent name> review required" before approval. If that holds, set
LEDGER.md Status to `CLOSED`. If it still shows the bare literal after a confirmed restart, set
Status back to `REOPENED` — the fix itself would be wrong, not just stale.

---

## QA-PS-007
> **Now CLOSED** (2026-09-23) — kept for the trace.

**Title:** PPT workflow final output file always named "presentation.html" regardless of run topic · **Route:** /runs/{id} · **Stage:** 4-test-writer · **Date:** 2026-09-17
**Report:** [BUGS.md#qa-ps-007](BUGS.md#qa-ps-007) · **Cards:** [ISS-651](.knowledge/cards/20260917-1200-ISS-651.md) (root — wontfix), [ISS-659](.knowledge/cards/20260917-1305-ISS-659.md) (sibling: prototype pipeline shares the defect — wontfix), [ISS-660](.knowledge/cards/20260917-1305-ISS-660.md) (sibling: base-version section — wontfix), [ISS-661](.knowledge/cards/20260917-1305-ISS-661.md) (sibling: header Download duplicate — wontfix, decision resolves it)

### Resolution (2026-09-23)
User decision (recorded in `FIX-STATE.md`): do not rename the deliverable — the risk to other
workflows outweighs it. A generic on-disk name is acceptable as long as Download serves the
right bytes. That answers option (a) below: the header Download button already serves the
literal on-disk/declared name, which is now the name of record by decision, so
`PreviewPanel.test.tsx:269`'s pinned assertion stays correct and ISS-661 needs no code change.
Byte-correctness (the one open item) was verified live on run
`8754cc43-f0b6-4005-b2d1-34db2eb41ad1`: header Download matched the on-disk sandbox file and
the rendered preview byte-for-byte (sha256) on both the latest version (v8) and a pinned older
version (v2). Full detail: [WONTFIX.md#qa-ps-007](WONTFIX.md#qa-ps-007).

### Why escalated
ISS-651, ISS-659 and ISS-660 all got a red test in `frontend/src/components/results/FilesTab.workspaceFilename.test.tsx` (vitest `{ fails: true }` xfail idiom, 3 of 3 observed red for the reported reason). ISS-661 — the Preview panel header Download button's own independent copy of the same defect (`handleHeaderDownload`, `PreviewPanel.tsx:1287-1290`) — genuinely resisted a test: `frontend/src/components/preview/PreviewPanel.test.tsx:269` already has a **pinned, non-xfail, currently-green** test, "Download serves the declared workspace file, not a name derived from content," which explicitly asserts `downloadBlob` is called with the literal declared name (e.g. `prototype.html`) and NOT a content-derived name, at that exact call site. Its own comment says it was written deliberately, against a prior bug where content-derived guesses served the wrong bytes. A red test asserting the opposite at the same call site would directly contradict that existing, intentional assertion — which the test-writer's boundaries forbid ("never weaken an existing test").

### Evidence
- `frontend/src/components/preview/PreviewPanel.tsx:1287-1290` — `handleHeaderDownload` builds its download name from `deliverableFile.split("/").pop()`, independently of `FilesTab.tsx`'s `withWorkspaceFile()` (`FilesTab.tsx:451-462`), the function ISS-651's fix targets.
- `frontend/src/components/preview/PreviewPanel.test.tsx:269` — pinned assertion that `handleHeaderDownload` must serve the declared on-disk name, not a content-derived one.
- Test-writer's `FilesTab.workspaceFilename.test.tsx`: 3/3 tests observed red for the correct reason (row shows `presentation.html`/`prototype.html` instead of the topic-derived name), then registered "expected fail" once marked `{ fails: true }`.
- ISS-661 left with no test filed; cards ISS-651/ISS-659/ISS-660 updated to `verification.status: failed` with `test_files: [FilesTab.workspaceFilename.test.tsx]`.

### Decision needed
Which behaviour is intended for the header Download button: should it always serve the literal on-disk file (current pinned test, matches `PreviewPanel.test.tsx:269`'s design intent), or should it serve the topic-derived name like the Files tab is being fixed to?

### Options
- **a)** Backend-only fix: interpolate the run's topic into the AGENT.md `write_file` target so the on-disk "declared" name itself becomes topic-derived. `PreviewPanel.test.tsx:269`'s existing assertion stays literally true with no change — the declared name and the topic-derived name become the same string.
- **b)** Frontend fallback: add topic-derived naming to `handleHeaderDownload` too (mirroring whatever fix lands in `withWorkspaceFile()`). This requires revisiting `PreviewPanel.test.tsx:269`'s literal expectation as part of the fix — not something a test-writer should do unilaterally.

### After the decision
- Option a): set LEDGER.md QA-PS-007 Status to `TESTED` (no frontend test change needed for ISS-661) and dispatch 5-fixer with the backend-only route.
- Option b): set LEDGER.md QA-PS-007 Status to `CONFIRMED` so a test-writer can add the ISS-661 test alongside the `PreviewPanel.test.tsx:269` rewrite, then re-run test → fix → verify.
## QA-PS-021
> **Now CLOSED** (2026-09-23) — kept for the trace.

### RE-ESCALATED 2026-09-22 (5-fixer, third dispatch) — one card FIXED, two decisions still open

**Title:** Downstream agents in a custom workflow receive no upstream artifacts and either compensate with wrong content or emit diagnostic output · **Route:** /create/custom and /runs/{id} · **Stage:** 5-fixer · **Date:** 2026-09-22
**Report:** [BUGS.md#qa-ps-021](BUGS.md#qa-ps-021)
**Cards:** [ISS-699](.knowledge/cards/20260922-1220-ISS-699.md) (**resolved**, FIX-608) · [ISS-850](.knowledge/cards/20260922-2155-ISS-850.md) (**resolved this dispatch** by [FIX-634](.knowledge/cards/20260922-2235-FIX-634.md)) · [ISS-733](.knowledge/cards/20260922-1353-ISS-733.md) (root, open — its own test is wrong) · [ISS-734](.knowledge/cards/20260922-1354-ISS-734.md) (open — decision 1) · [ISS-735](.knowledge/cards/20260922-1355-ISS-735.md) (open — decision 2)

#### What was fixed, so the remaining ask is narrow

Re-analysis narrowed this bug's root card to compensation **mode 2** and filed the residual as
ISS-850. That card IS now fixed — [FIX-634](.knowledge/cards/20260922-2235-FIX-634.md), one
branch in `backend/agents/capabilities/deliverables/_coverage.py`: a deliverable longer than
2000 characters whose DECLARED upstream source contributed no content at all now returns a
reason, and the shared completion gate degrades `status` / `degraded_reason` /
`published_status` exactly as it already does for the narration and drop signals. `engine.py`
was not touched; SC-001 and the import-linter contracts hold by construction.

#### Why the rest is escalated (not "hard", not environment)

Three cards remain, and none of them is blocked on effort:

1. **ISS-733's own test asserts the opposite of the manifest's declared design.** Not a
   product decision — a test defect, recorded here because the line keeps re-dispatching it.
2. **ISS-734** needs an API contract decision: what a `validation` gate must DO when a step's
   declared upstream artifact is missing. Its own confirm/refute experiment has still never
   been run, and the test's proposed answer (`return None`) would break every validator.
3. **ISS-735** needs a schema decision: whether a "this content was compensated" flag earns a
   `workflow_runs` column (+ alembic `0048`) at all. A schema change is explicitly outside
   5-fixer's remit and no card has ever chosen the flag's design.

#### Evidence (re-checkable, gathered this dispatch)

- **ISS-733's test contradicts the manifest.** `backend/agents/workflows/custom/workflow.yaml:17-19`:
  ```yaml
  deliverable:
    strategy: streamed_text
    name: output.md
  ```
  `streamed_text` publishes the LAST step's streamed text — a `custom` run that writes no file
  is the DECLARED happy path. `test_custom_workflow_with_no_written_artifact_is_not_reported_clean`
  (`backend/tests/agents/test_qa_ps_021_downstream_no_upstream_artifacts.py:62`) asserts
  `data.get("agents_failed")` is truthy for exactly that 9/9 run. Making it pass would make
  every clean `streamed_text` run in the product report failed agents.
- **ISS-734's `None` breaks the sole caller.** `backend/agents/capabilities/gates/validation.py:92`
  is the one production call site; the value goes straight into
  `issues = await validator.validate(target)` at `:102`. The test asserts `target is None`.
  Re-checked today: `grep -rn "produced_artifacts" --include="*.py" backend/` still matches only
  `backend/tests/agents/test_qa_ps_021_downstream_no_upstream_artifacts.py:145` and `:152` — the
  attribute the test keys its guard off does not exist in production; and `ctx.current_step` is a
  step-id string in production (`agents/capabilities/context_pack/pack.py:174`,
  `agents/capabilities/repo_inventory/inventory.py:250`), not an object with `.consumes`.
- **ISS-735 needs a migration.** `test_workflow_run_has_compensated_content_flag_for_revision_seeding`
  asserts a `compensated` / `content_compensated` / `compensated_content` column on
  `WorkflowRun` (`backend/app/models/workflow.py`). `ls backend/alembic/versions/ | tail -1`
  → `0047_run_manifest_json.py`, so this is a new `0048`. The counter-precedent in this exact
  seam is `engine.py`'s Option B / KAN-112 comment: "no new column, no migration".
- **The fix that DID land, observed.**
  `cd backend && python3.11 -m pytest tests/agents/test_qa_ps_021_downstream_no_upstream_artifacts.py -q -p no:randomly`
  → before: `1 failed, 4 xfailed`; after: `2 failed, 3 xfailed`, the new failure being
  `test_wrong_attribution_full_regeneration_is_flagged_when_upstream_missing`
  `[XPASS(strict)] ISS-850 unfixed`. Regression guards, same tier:
  `tests/agents/test_qa_ps_028_compiler_content_drop.py` → `3 passed`; goldens
  `test_characterization_{app_builder,prototype}` → `4 passed` and
  `test_characterization_{ppt,prototype_revision}` → `4 passed` (INV-3 byte parity).
  `tests/agents/test_qa_ps_027_placeholder_completion.py` → `2 failed, 2 passed`, PRE-EXISTING:
  re-running it with this fix's only code path neutralised
  (`eng.dropped_section_reason = lambda *a, **k: None`) still gives `2 failed, 2 passed`, and
  both failures are the precondition "sanity check: prototype.html must never have been
  written" — FIX-601 now grants the write tool, which is ISS-761/ISS-762's ground.

#### Decision 1 (ISS-734) — when a `gates: [validation]` step's declared upstream artifact is missing, what must the gate do?

| Option | Consequence |
|---|---|
| **(a) Nothing — retire ISS-734** | The run-level signals (FIX-612 / FIX-615 / FIX-634) already degrade the RUN. The gate keeps validating the run-level deliverable, and a validator can still pass a step whose real input never arrived. Zero code, zero risk, card closed as covered. |
| **(b) `GATE_BLOCK` on a missing declared upstream** | Honest, but it HALTS the step — on ten native pipelines, including every `prototype*` revision path. A throttle that returns empty output would turn a recoverable run into a blocked one. Needs a per-pipeline opt-in or an escape hatch, i.e. real design. |
| **(c) A new gate outcome (e.g. `GATE_DEGRADE`)** | Widens the `GateOutcome` contract every gate handler and the frontend event vocabulary share. Largest blast radius; only worth it if (b)'s halt is unacceptable but silence is too. |

Whichever is chosen, `_build_validation_target` returning `None` is NOT viable — the test must
be rewritten to the decision, not the app to the test.

#### Decision 2 (ISS-735) — does "this run's content was compensated" earn a `workflow_runs` column?

| Option | Consequence |
|---|---|
| **(a) No column — read the parent's `status` / `degraded_reason`** | Free today: `run_commands.py:769` already reconciles a degraded `pipeline_complete` onto the persisted row, and `WorkflowRun.status` carries `degraded` (`backend/app/models/workflow.py:41-45`). Requires verifying that the `custom_revision` seed path actually READS them — nobody has. Matches the "no new column, no migration" precedent. |
| **(b) Add the column + alembic `0048`** | Durable and explicit, queryable in history. Costs a migration, a model change, a write path, and a definition of what sets it — none of which any card has designed. Additive-only, so reversible in principle. |

#### What happens after the decision

- Decision 1 → 4-test-writer rewrites ISS-734's test to the chosen contract (or the card is
  retired under option (a)); 5-fixer implements it in `validation.py` only.
- Decision 2 → under (a) the card becomes a one-line verification task on the revision seed
  path and its test is rewritten; under (b) it leaves 5-fixer's remit entirely and needs a
  migration-authorised dispatch.
- Independently of both: ISS-733's test needs rewriting against a manifest whose deliverable
  strategy actually requires a file, or the card is retired as covered by FIX-608 + FIX-612 +
  FIX-615 + FIX-634.

---

> **Now TESTED** (2026-09-22) — kept for the trace.
> **WITHDRAWN by 5-fixer (2026-09-22, second dispatch) — no product decision is needed any
> more; the ledger row is back to `CONFIRMED` for re-analysis. Kept below for the trace.**
>
> **Question 1 was answered by events, not by a product owner.** Option (b) — "one detection
> layer, owned by QA-PS-027/ISS-721, keyed on content quality, not on 'no file was written'" —
> has already been built, in the exact block ISS-733 named, by two fixes that landed after these
> cards were written (cards 13:53-13:55; fixes 18:38 and 18:54):
> `engine.py:7456-7459` `placeholder_narration_reason` ([FIX-612](.knowledge/cards/20260922-1838-FIX-612.md),
> QA-PS-027/ISS-721, now `resolved`) covers compensation mode 1; `engine.py:7477-7490`
> `dropped_section_reason` ([FIX-615](.knowledge/cards/20260922-1854-FIX-615.md), QA-PS-028/ISS-730,
> `resolved`) covers mode 3; `engine.py:7511-7513` escalates `published_status` for both. Mode 2's
> trigger was removed by [FIX-608](.knowledge/cards/20260922-1820-FIX-608.md).
>
> Questions 2 and 3 no longer stand on their own either: ISS-734's and ISS-735's premises both
> shifted under the same three fixes (see each card's "Fixer re-check (second dispatch)" section),
> and both cards are explicitly *not reproduced*. Asking a product owner to choose a gate contract
> or a schema column for an unreproduced hypothesis whose parent gap has since been closed is the
> wrong ask. Re-analysis against the current tree comes first.
>
> What is NOT withdrawn: the three red tests in
> `backend/tests/agents/test_qa_ps_021_downstream_no_upstream_artifacts.py` still assert contracts
> the app does not have and must not be made to pass by changing the engine — see each card.

> **Now TESTED** (2026-09-22) — kept for the trace.

> **Now TESTED** (2026-09-22) — kept for the trace.

**Title:** Downstream agents in a custom workflow receive no upstream artifacts and either compensate with wrong content or emit diagnostic output · **Route:** /create/custom and /runs/{id} · **Stage:** 5-fixer · **Date:** 2026-09-22
**Report:** [BUGS.md#qa-ps-021](BUGS.md#qa-ps-021) · **Cards:** [ISS-699](.knowledge/cards/20260922-1220-ISS-699.md) (**resolved** by [FIX-608](.knowledge/cards/20260922-1820-FIX-608.md)), [ISS-733](.knowledge/cards/20260922-1353-ISS-733.md) (root — escalated), [ISS-734](.knowledge/cards/20260922-1354-ISS-734.md) (escalated), [ISS-735](.knowledge/cards/20260922-1355-ISS-735.md) (escalated)

### Why escalated

One of the bug's four cards is **fixed**. The reported trigger — "no upstream agent can write
files" — was ISS-698/QA-PS-019's missing `tools` overlay in `_apply_selections`, and that landed
in FIX-608 while this bug was being worked. ISS-699 is this bug's own reproduced instance of that
trigger and its test now XPASSes on the live tree (evidence below). No second edit was made:
ISS-698, ISS-732 and ISS-699 all route through one seam with a single production call site
(`engine.py:4654`), so patching it twice would have been the duplicate-guard anti-pattern.

The other three cards ask for a **second, independent layer**: engine-level DETECTION that a step
compensated for a missing input. That layer cannot be built from these cards as written. Each of
the three tests asserts behaviour that either contradicts a declared product design, invents an
API that does not exist, or requires a schema change — so implementing them would mean bending the
application to the test, which 5-fixer may not do. Each blocker below is a decision, not a
difficulty.

### Evidence

**ISS-699 is fixed — observed, not asserted.**
- `backend/agents/execution_engine/engine.py:12903-12926` — the overlay FIX-608 added inside
  `_apply_selections`'s `patch` dict:
  ```python
  if isinstance(sel.get("tools"), dict) and sel["tools"]:
      _slots = {f.name for f in dataclasses.fields(step.tools)}
      _named = {k: getattr(user_step.tools, k) for k in sel["tools"] if k in _slots}
      if _named:
          patch["tools"] = dataclasses.replace(step.tools, **_named)
  ```
- Run on the live tree, `cd backend && python3.11 -m pytest tests/agents/test_qa_ps_021_downstream_no_upstream_artifacts.py -q -p no:randomly`:
  ```
  tests/agents/test_qa_ps_021_downstream_no_upstream_artifacts.py xFxx   [100%]
  FAILED ...::test_apply_selections_carries_write_files_grant_onto_compiled_step
  [XPASS(strict)] ISS-699 unfixed
  1 failed, 3 xfailed, 1 warning in 3.94s
  ```
  The `F` is the XPASS under `xfail(strict=True)` — the pass signal for ISS-699. The same file ran
  `4 xfailed` before FIX-608 landed. The marker is left in place for 6-verifier.

**Question 1 evidence (ISS-733).**
- `backend/agents/workflows/custom/workflow.yaml:17-19`:
  ```yaml
  deliverable:
    strategy: streamed_text
    name: output.md
  ```
  `streamed_text` takes the LAST step's streamed output as the deliverable — a `custom` run that
  writes no file is the DECLARED happy path, not a failure.
- Driving the offline harness (`tests/agents/_scripted_model._drive("custom")`, no Bedrock/network)
  produced this `pipeline_complete.data` with zero file writes anywhere in the run:
  ```json
  {"agents_completed": 9, "agents_total": 9,
   "final_output": "task-list-planner default output.",
   "deliverable_filename": "output.md", "deliverable_mimetype": "text/markdown"}
  ```
  `agents_failed` is absent. `test_custom_workflow_with_no_written_artifact_is_not_reported_clean`
  (test file :62) asserts `data.get("agents_failed")` must be truthy for exactly this run.
- ISS-733's own fix direction cannot satisfy its own test: it proposes keying the guard off a
  step's declared `consumes`, and the card's Description establishes that
  `grep -n 'produces\|consumes' backend/agents/workflows/custom/workflow.yaml` returns nothing.
- The block ISS-733 targets (`engine.py:7376-7457`) is the same block
  [ISS-721](.knowledge/cards/20260922-1242-ISS-721.md) owns for **QA-PS-027** (`LEDGER.md` row 87,
  Status `TESTED`), with a different proposed mechanism.

**Question 2 evidence (ISS-734).**
- `grep -rn "produced_artifacts" --include="*.py" backend/` → only
  `tests/agents/test_qa_ps_021_downstream_no_upstream_artifacts.py:145` and `:152`. The attribute
  the test keys its guard off does not exist in production.
- `ctx.current_step` is a step-id **string** in production, not an object with `.consumes`:
  `backend/agents/capabilities/context_pack/pack.py:174` and
  `backend/agents/capabilities/repo_inventory/inventory.py:250`, both
  `producer_step=getattr(ctx, "current_step", None) or "<default>"`. The test passes
  `current_step=SimpleNamespace(consumes=["prototype_build_output"])`.
- `_build_validation_target` has exactly one production call site,
  `backend/agents/capabilities/gates/validation.py:92`, and the value goes straight into
  `issues = await validator.validate(target)` (:102). The test asserts `target is None`, which
  would hand `None` to every validator of every `gates: [validation]` step in all ten pipelines
  ISS-734 lists.

**Question 3 evidence (ISS-735).**
- The test asserts `WorkflowRun.__table__.columns` contains one of
  `{"compensated", "content_compensated", "compensated_content"}`. `WorkflowRun` is
  `backend/app/models/workflow.py:13-16` (`__tablename__ = "workflow_runs"`); the newest migration
  is `backend/alembic/versions/0047_run_manifest_json.py`, so this needs a new `0048`.
- ISS-735 proposes no fix. Its only forward-looking section is "What would confirm or refute this",
  and it opens: "**INFERRED sibling … not reproduced. Filed because the root cause implies it, not
  because it was observed.**"
- Counter-precedent in the same seam: the composer's deliverable override is carried under a
  reserved `__deliverable__` key in the existing selections map specifically to avoid a column —
  `engine.py`, Option B / KAN-112 comment: "same namespace convention as ``__workflow__`` for
  limits — no new column, no migration".

### Decision needed

Should the engine gain a second, independent "a step compensated for a missing input" detection
layer at all — and if so, on what signal, given `streamed_text` runs legitimately write no file?

### Options

- **a) No second layer; close the bug on FIX-608.** The reported trigger is gone: composed steps
  now get the `write_files` grant the user selected, so downstream steps find real upstream
  artifacts. *Consequence:* a legitimately-missing artifact (a crash, a wrong path, a fan-out race)
  still produces a silently-compensating step. ISS-733/734/735 become WONTFIX-or-later; QA-PS-027
  continues to own the completion-gate question on its own row.
- **b) One detection layer, owned by QA-PS-027/ISS-721, keyed on content quality — not on
  "no file was written".** ISS-733/734/735 fold into that row as siblings rather than being fixed
  here. *Consequence:* one mechanism in one block, no collision between two fixers editing
  `engine.py:7376-7457`; this bug closes on FIX-608 alone; the three cards are re-pointed.
- **c) Build the layer as the three tests specify.** *Consequence:* every clean `streamed_text` run
  starts reporting `agents_failed` (per the harness output above); `_build_validation_target` gains
  a `None` return its only caller cannot handle, plus a new `ctx.produced_artifacts` API; and
  `workflow_runs` gains a column via migration `0048`. This needs an explicit product sign-off on
  all three, and the three tests would need rewriting against whatever contract is chosen.

### After the decision

- Option a): set `LEDGER.md` QA-PS-021 Status to `FIXED` (FIX-608 is the fix; 6-verifier confirms
  the ISS-699 XPASS) and move ISS-733/734/735 to `WONTFIX.md` with this section as the rationale.
- Option b): set Status to `FIXED` for the same reason, and re-point ISS-733/734/735 as siblings on
  QA-PS-027 so ISS-721's fixer builds the single mechanism.
- Option c): set Status to `CONFIRMED` so 3-analyzer can specify the chosen contract and
  4-test-writer can rewrite the three tests against it — the current three cannot be made green
  without bending the app to them.

<a id="qa-ps-036"></a>

## QA-PS-036
> **Now CLOSED** (2026-09-23) — kept for the trace.

**Title:** Analytics page fires 17 API requests with heavy duplication and fetches run history and workflow data not needed on analytics · **Route:** /analytics · **Stage:** 5-fixer · **Date:** 2026-09-22
**Report:** [BUGS.md#qa-ps-036](BUGS.md#qa-ps-036) · **Cards:** [ISS-782](.knowledge/cards/20260922-1610-ISS-782.md) (root — **half fixed**, half escalated), [ISS-796](.knowledge/cards/20260922-1825-ISS-796.md) (**resolved** by [FIX-617](.knowledge/cards/20260922-1935-FIX-617.md))

### Why escalated

The bug's headline — every shared endpoint fetched twice on one cold load — is **fixed and
measured**: `/api/analytics/summary`, `/api/settings/preferences` and `/api/capabilities` now fire
exactly once each, and the sibling card ISS-796 (the composer firing `/api/capabilities` once per
`useAgentCapabilities` call site) XPASSes. That half needed no decision and is in the working tree.

The remaining half cannot be built from the card as written. ISS-782's "Expected" — and the test
written against it — require **zero** `/api/runs` and **zero** `/api/workflows` calls on
`/analytics`, on the stated premise that "neither run history nor the workflow catalog is
displayed or used anywhere on `/analytics`". That premise is false for the app shell that wraps
`/analytics`: `AppHeader` is rendered outside the view switch on every route and consumes **both**
payloads. Reaching zero therefore means deciding to take data away from a global surface, and to
reverse a deliberate, card-referenced sign-in preload the analysis never examined. That is a
product decision, not a difficulty.

Three requests remain on a cold `/analytics` load, from two mechanisms, neither named by ISS-782:

1. the Redux **sign-in preload** (`store/listenerMiddleware.ts`) — `/api/workflows` +
   `/api/runs?limit=6` (and the three `/api/*/library` calls ISS-782 also lists as unwanted);
2. `page.tsx`'s `recentRuns` fetch — `/api/runs?limit=50`, which feeds the header's live-run badge.

### Evidence

**The duplication half is fixed — measured, not asserted.** Live tree, app running on :3000/:8000,
`cd tests/integration/e2e && ./.venv/bin/python -m pytest suites/10_analytics/test_iss782_duplicate_fetches.py -x -q --runxfail`:

```
E  AssertionError: ISS-782: /analytics should never call /api/runs or /api/workflows
   (not displayed on this page), got runs=2 workflows=1:
   ['http://localhost:8000/api/runs?limit=6',
    'http://localhost:8000/api/auth/me',
    'http://localhost:8000/api/analytics/summary?range=30d',
    'http://localhost:8000/api/settings/preferences',
    'http://localhost:8000/api/capabilities',
    'http://localhost:8000/api/runs?limit=50',
    'http://localhost:8000/api/workflows',
    'http://localhost:8000/api/agents/library',
    'http://localhost:8000/api/skills/library',
    'http://localhost:8000/api/hooks/library']
```

The FIRST assertion (`summary_n == 1 and prefs_n == 1 and caps_n == 1`) passed — execution reached
line 52. ISS-782's validation measured each of those three at **x2**, plus `/api/runs?limit=50` x2
and `/api/workflows` x2: 15 requests, now 10. The test stops on the second assertion only.

**ISS-796 XPASSes** —
`./.venv/bin/python -m pytest suites/04_composer_canvas/test_iss796_capabilities_double_fetch.py -x -q`:
```
FAILED suites/04_composer_canvas/test_iss796_capabilities_double_fetch.py::test_opening_the_agent_config_tab_reuses_the_capabilities_fetch[chromium]
[XPASS(strict)] ISS-796 unfixed
```

**Source of `/api/workflows` and `/api/runs?limit=6`: the sign-in preload, fired on every route.**
`frontend/src/store/listenerMiddleware.ts:19-25`:
```
// `signedIn` fires only from the dashboard/home page's mount-time auth check
// (the app's landing route — "/" just redirects to "/login", and /dashboard
// is where it lands). Preloading here means agents/skills/workflows are
// already in the store by the time the user opens the Library or catalog
// tabs inside DashboardLayout — no fetch-on-open latency.
```
The comment's premise is wrong. `signedIn` is dispatched from
`frontend/src/app/[...view]/page.tsx:892` — `dispatch(signedIn({ token: storedToken }));` — and
`[...view]` is the catch-all route component for **every** path, so the preload runs on
`/analytics`, `/settings`, `/library` and every deep link. Its five dispatches
(`listenerMiddleware.ts:52-70`) are `fetchWorkflows()` → `GET /api/workflows`, `fetchRecentRuns()`
→ `GET /api/runs?limit=6` (`store/slices/globalSlice.ts:7` `const RECENT_RUNS_LIMIT = 6;`, used at
`:43`), `fetchAgentLibrary()`, `fetchSkills()`, `fetchHooks()` — exactly the five off-page calls
ISS-782's Evidence block recorded and could not attribute.

**Both payloads ARE consumed on `/analytics`, by the always-mounted header.**
- `frontend/src/components/layout/DashboardLayout.tsx:2715` renders `<AppHeader`; the
  `mainView === "analytics"` branch is at `:3030`, i.e. *inside* the switch the header sits above.
  The header is on screen on `/analytics`.
- `frontend/src/components/layout/AppHeader.tsx:126` — `const getWorkflowLabel = useWorkflowLabels();`
  reads `state.global.workflows`, which only `fetchWorkflows()` (`GET /api/workflows`) populates
  (`store/slices/globalSlice.ts:96`: "populated by fetchWorkflows/GET /api/workflows — so a
  workflow's display name always matches what the catalog actually calls it").
- `frontend/src/components/layout/AppHeader.tsx:176` —
  `const liveRunsFromServer = recentRuns.filter((r) => LIVE_STATUSES.has(r.status));`, fed by
  `DashboardLayout.tsx:2741` `recentRuns={recentRuns}` ← `page.tsx`'s `GET /api/runs?limit=50`.
  `AppHeader.tsx:186-187`: `const hasServerData = recentRuns.length > 0;` — with no fetch the
  badge silently degrades to the ephemeral notification list, which in a fresh tab is empty, so a
  run launched in another tab stops appearing in the header on every non-home route.

**The preload is deliberate and already carries two cards' rationale**, so reversing it is not a
cleanup. `listenerMiddleware.ts:42-52` records why the five calls fire together rather than in
sequence, citing a measured regression: "ISS-232: these two groups used to be AWAITED IN SEQUENCE
... A cold/deep-linked /library/{type}/{slug} breaks that premise ... the sequential await left
the plain listing rendered under the detail URL for as long as the home pair took (measured 12.2s
on a slow /api/workflows)." `ISS-200` is cited in the same effect for the account-switch clear.

### Decision needed

Should the app keep preloading the workflow catalog and the user's run list on **every**
authenticated route — paying ~60 KB on routes that do not display them, but keeping the global
header's live-run badge and workflow-name labels correct everywhere and Library/catalog tabs
instant — or should that data become route-scoped, accepting a degraded header and
fetch-on-open latency off the home route?

### Options

- **a) Keep the preload; narrow ISS-782's Expected to the duplication only.** The bug's measured
  204 KB → the duplication is already gone (15 requests → 10; the three x2 endpoints are x1).
  `4-test-writer` drops the `runs_n == 0 and workflows_n == 0` assertion, the test XPASSes, and
  QA-PS-036 closes. Consequence: `/analytics` still transfers the preload's ~60 KB on a cold load.
  Same answer would apply to QA-PS-035 and QA-PS-037, whose cards state the identical expectation.
- **b) Make the preload route-scoped and gate `page.tsx`'s `recentRuns` fetch.** Reaches
  `runs_n == 0, workflows_n == 0` and the test as written goes green. Consequence: reopens ISS-232
  (deep-linked `/library/...` waits for its own fetch, measured 12.2s in the worst case there), and
  on every non-home route the header's badge falls back to the empty notification list and workflow
  names fall back to raw type ids. Needs a follow-up decision about where the header should get
  live-run data instead — probably a new, small endpoint, which is a schema/API change 5-fixer may
  not make alone.
- **c) Move the header's two needs onto cheaper sources and keep the rest.** e.g. a live-runs-only
  projection for the badge and a labels-only catalog projection, both small, fetched app-wide;
  drop the 37 KB and 22 KB full payloads from non-home routes. Consequence: a real API addition
  (two new endpoints or query projections) plus backend work — out of scope for this bug line.

### What happens after the decision

- Option a): `4-test-writer` re-scopes `tests/integration/e2e/suites/10_analytics/test_iss782_duplicate_fetches.py`
  to the three-endpoint assertion; 6-verifier re-runs it and QA-PS-036 closes on FIX-617. The same
  re-scoping applies to the QA-PS-035 and QA-PS-037 tests.
- Option b) or c): back to `3-analyzer` for the replacement data path, since neither is expressible
  as an edit to the files ISS-782's `applies_to.globs` name.

---

## QA-PS-035
> **Now CLOSED** (2026-09-23) — kept for the trace.

**Title:** Account settings page makes redundant duplicate API calls and fetches run history and workflow data not needed on settings · **Route:** /settings/* · **Stage:** 5-fixer · **Date:** 2026-09-22
**Report:** [BUGS.md#qa-ps-035](BUGS.md#qa-ps-035) · **Cards:** [ISS-781](.knowledge/cards/20260922-1630-ISS-781.md) (root — **half fixed**, half escalated), [ISS-801](.knowledge/cards/20260922-1834-ISS-801.md) (**resolved** by [FIX-618](.knowledge/cards/20260922-1945-FIX-618.md)), [ISS-799](.knowledge/cards/20260922-1835-ISS-799.md) (**resolved** by FIX-618)

### Why escalated

The bug's duplication half is **fixed and measured**: `/api/auth/me`,
`/api/settings/preferences`, `/api/capabilities`, `/api/auth/mfa` and
`/api/settings/constitution` now fire exactly once each on a cold `/settings/*` load, down from
3-4x / 2x / 2x / 2x / 2x. Three of the four tests in the bug's test file XPASS. That half needed
no decision and is in the working tree.

The remaining half cannot be built from the card as written. ISS-781's "Problem 2" — and the test
written against it — require **zero** `/api/runs` and **zero** `/api/workflows` calls on
`/settings/profile`, on the stated premise that every route outside the dashboard "pays for a
50-row run-history fetch it never displays". That premise is false for the app shell that wraps
`/settings/*`: `AppHeader` renders on every `mainView`, settings included, and its "N Running"
badge resolves its run out of exactly that list. Reaching zero means deciding to take data away
from a global surface and to reverse a deliberate, card-referenced sign-in preload — a product
decision, not a difficulty.

Note that **no card's own "where the fix belongs" asks for removal.** ISS-781 and ISS-801 both
prescribe de-duplication (a shared cached source, and closing the `signedIn` listener race). The
zero-request expectation appears only in the reporter's `BUGS.md` text and in the test written
from it.

This is the same question already open for
[QA-PS-036](ESCALATIONS.md#qa-ps-036), whose section states "Same answer would apply to QA-PS-035
and QA-PS-037". One decision settles all three.

### Evidence

**1. The duplication half is fixed — measured, not asserted.** App running on :3000/:8000,
`cd tests/integration/e2e && ./.venv/bin/python -m pytest suites/09_settings/test_qa_ps_035_settings_duplicate_requests.py -q -rA`:

```
XFAIL suites/09_settings/test_qa_ps_035_settings_duplicate_requests.py::test_settings_profile_does_not_fetch_runs_or_workflows[chromium] - ISS-781 unfixed
FAILED suites/09_settings/test_qa_ps_035_settings_duplicate_requests.py::test_settings_profile_fetches_me_preferences_capabilities_once_each[chromium]
FAILED suites/09_settings/test_qa_ps_035_settings_duplicate_requests.py::test_settings_security_tab_fetches_mfa_status_once[chromium]
FAILED suites/09_settings/test_qa_ps_035_settings_duplicate_requests.py::test_settings_constitution_tab_fetches_constitution_once[chromium]

_ test_settings_profile_fetches_me_preferences_capabilities_once_each[chromium] _
[XPASS(strict)] ISS-801 unfixed
_________ test_settings_security_tab_fetches_mfa_status_once[chromium] _________
[XPASS(strict)] ISS-799 unfixed
______ test_settings_constitution_tab_fetches_constitution_once[chromium] ______
[XPASS(strict)] ISS-799 unfixed
```

Three strict-xfail tests now XPASS (the pass signal); the ISS-781 one still XFAILs.
Report: `tests/integration/test-runs/2026-09-22T19-41-local/0-report.html`.

**2. What still fires on `/settings/profile`, after the fix.** Same file, `--runxfail`, every
`localhost:8000/api/*` request the page made, counted:

```
   2 http://localhost:8000/api/runs?limit=6
   2 http://localhost:8000/api/runs?limit=50
   1 http://localhost:8000/api/workflows
```

**3. `/api/runs?limit=50` IS consumed by UI rendered on `/settings/*`.**
`frontend/src/app/[...view]/page.tsx:995` fetches it into `recentRuns`; that state is handed to
`DashboardLayout` at `page.tsx:4311`, which passes it into the header:

- `frontend/src/components/layout/DashboardLayout.tsx:2715` — `<AppHeader` opens the return,
  **before** any `mainView` branch;
- `frontend/src/components/layout/DashboardLayout.tsx:2741` — `        recentRuns={recentRuns}`;
- `frontend/src/components/layout/DashboardLayout.tsx:3013` — `          {mainView === "settings" && (` is where `AccountSettings`
  renders, i.e. *inside* the shell the header already sits above.

The header consumes it:

- `frontend/src/components/layout/AppHeader.tsx:78` — `  // When provided, these are used to drive the "N Running" badge and dropdown`
- `frontend/src/components/layout/AppHeader.tsx:328` — `                const serverRun = recentRuns.find(r => r.id === runningPipelines[0].workflowRunId);`
- `frontend/src/components/layout/AppHeader.tsx:371` — `                <span>{runningPipelines.length} Running</span>`

So ISS-781's "a 50-row run-history fetch it never displays" does not hold on this route.

**4. `/api/workflows` and `/api/runs?limit=6` are a deliberate sign-in preload.**
`frontend/src/store/listenerMiddleware.ts:18-21`:

```
// `signedIn` fires only from the dashboard/home page's mount-time auth check
// ... Preloading here means agents/skills/workflows are
// already in the store by the time the user opens the Library or catalog
// tabs inside DashboardLayout — no fetch-on-open latency.
```

and at `listenerMiddleware.ts:38-47` the ISS-232 comment records that these were deliberately made
parallel after a deep-linked `/library/{type}/{slug}` measured **12.2s** behind a sequential
`/api/workflows`. [ISS-794](.knowledge/cards/20260922-1827-ISS-794.md) independently classes this
preload as "a SEPARATE, likely-intentional behaviour, not part of the duplication defect ... an
app-wide warm-cache decision (referenced as ISS-232 in that file)" and puts it explicitly out of
scope: "a product decision, not covered here".

**5. Two residual duplications, recorded not patched** (both in
[FIX-618](.knowledge/cards/20260922-1945-FIX-618.md) § "What is deliberately NOT fixed"):

- `/api/runs?limit=50` x2 — `RunConnectionProvider.tsx:289` (boot) and `page.tsx:995` are ticks
  apart, so [FIX-616](.knowledge/cards/20260922-1923-FIX-616.md)'s in-flight-only guard misses
  them. `frontend/src/lib/api.ts:439-442` states the boundary on purpose: "Run/workflow lists
  deliberately do NOT [go through the cache]: their callers refetch precisely to observe a change
  (a cancel clearing the header's 'N Running' pill, a gate flipping a status)." Caching them is
  itself a design decision.
- `/api/runs?limit=6` x2 while `/api/workflows` under the *same* guard is x1
  (`listenerMiddleware.ts:51-56`). ISS-794 attributes the doubling to the listener `effect`
  running "async per action", but RTK invokes the effect synchronously up to its first `await`,
  which here is after both dispatches — so the stated mechanism does not explain the asymmetry.
  Left to ISS-784/793/794's own line rather than patched on a guess.

### Decision needed

Should a non-home route such as `/settings/*` still fetch the run list and workflow catalog that
the always-mounted app shell (header badge, notification run-matching, SSE live-run re-attach) and
the ISS-232 sign-in preload consume — or should those two payloads be scoped away from it, and the
shell's needs met some other way?

### Options

- **a) Accept the app-shell traffic as intended; re-scope the test to the duplication.** Assert one
  `/api/runs?limit=50`, one `/api/runs?limit=6`, one `/api/workflows` instead of zero. Consequence:
  QA-PS-035 closes on FIX-618 with 60 KB of shell data still fetched per cold settings load, and
  `BUGS.md#qa-ps-035`'s "Problem 2" is answered "working as designed". Same answer applies to
  QA-PS-036 and QA-PS-037.
- **b) Make the preload route-scoped and gate `page.tsx`'s `recentRuns` fetch.** Reaches
  `runs == 0, workflows == 0` and the test as written goes green. Consequence: reopens ISS-232
  (the 12.2s deep-link case), and on `/settings/*` the header's "N Running" badge loses its server
  run list — the badge and its dropdown fall back to notification state only. Needs a follow-up
  decision about where the header gets live-run data, likely a new endpoint, which is an API
  change 5-fixer may not make alone.
- **c) Keep the shell fed, from cheaper sources.** A live-runs-only projection for the badge and a
  labels-only catalog projection, fetched app-wide; drop the 37 KB and 22 KB full payloads from
  non-home routes. Consequence: a real API addition plus backend work — out of scope for this bug
  line.

### What happens after the decision

- Option a): `4-test-writer` re-scopes `test_settings_profile_does_not_fetch_runs_or_workflows` to
  the one-each assertion; `6-verifier` re-runs the file and QA-PS-035 closes on FIX-618. ISS-781
  moves to `resolved` with its "Problem 2" expectation corrected by supersession.
- Option b) or c): back to `3-analyzer` for the replacement data path — neither is expressible as
  an edit to the files ISS-781's `applies_to.globs` name.

---

## QA-PS-038
> **Now CLOSED** (2026-09-23) — kept for the trace.

**Title:** Opening a run detail page from history fires ~40-50 API requests — `runs?limit=50` called
12+ times as durable replay events trigger live-run refetch logic · **Route:** /runs/{id} ·
**Stage:** 5-fixer · **Date:** 2026-09-22
**Report:** [BUGS.md#qa-ps-038](BUGS.md#qa-ps-038) · **Cards:**
[ISS-785](.knowledge/cards/20260922-1620-ISS-785.md) (root — **replay half fixed**, rest escalated),
[ISS-803](.knowledge/cards/20260922-1645-ISS-803.md) (**resolved** by
[FIX-624](.knowledge/cards/20260922-2027-FIX-624.md)),
[ISS-804](.knowledge/cards/20260922-1646-ISS-804.md),
[ISS-805](.knowledge/cards/20260922-1647-ISS-805.md),
[ISS-840](.knowledge/cards/20260922-2030-ISS-840.md) (new — the reopen runs twice per click)

### Why escalated

The mechanism this bug was root-caused to is **fixed and measured**, and is in the working tree:
`handleWebSocketMessage` now takes an `isReplay` flag, and none of its eight
`getWorkflows(limit: 50)` bindings fire while a durable log is being replayed. Measured on the same
run ISS-785's own attempt 1 used, the CLICK's `runs?limit=50` calls went **3 -> 1**, and the one
that remains does not come from the replay handler at all.

What cannot be reached from here is the card's **test**. It asserts `<= 2` `/api/runs?…limit=…`
calls, but collects from before `page.goto("/dashboard")`, so its window spans three page mounts
and counts the app shell's own per-mount run-list fetches. Six remain, and every one of them is
either the Redux sign-in preload (`runs?limit=6`) or `page.tsx`'s `recentRuns` fetch that feeds the
header's "N Running" badge — the two payloads whose removal is **already the open decision in
[QA-PS-035](#qa-ps-035)**, whose own text says "Same answer applies to QA-PS-036 and QA-PS-037".
QA-PS-038 is the fourth bug waiting on that same answer. No edit to the replay path can take six
below two, and editing the test to match the code is the one thing 5-fixer may not do.

### Evidence

**The fix, in the tree** — `frontend/src/app/[...view]/page.tsx:1048-1056`:
```
const handleWebSocketMessage = useCallback((msg: StreamMessage, sourceRunId?: string, isReplay?: boolean) => {
    // ISS-785 (QA-PS-038): every recents refetch below reads its token from
    // here, never from getToken() directly. …
    const recentsToken = () => (isReplay ? null : getToken());
```
The eight bindings now read `recentsToken()` (`page.tsx:1694, 1778, 1819, 1868, 2105, 2130, 2187,
2223`); the three durable-replay loops pass `true` (`page.tsx:2836, 3084, 3643`); live SSE
(`page.tsx:2414`) passes nothing and is unchanged.

**Before/after, click phase only** — full transcript and the probe that reproduces it:
`evidence/qa-ps-038/07-fix-click-phase-before-after.txt`. Run
`8088430c-32aa-4551-ad24-f5fd806e872b` (ISS-785's attempt-1 run):

| | `/api/runs?limit=50` after the click | stack |
|---|---|---|
| gate disabled (pre-fix behaviour) | 3 | 1x `DashboardPage.useEffect`, 2x `DashboardPage.useCallback[handleWebSocketMessage]` |
| FIX-624 | 1 | `DashboardPage.useEffect` only |

**The test, as it stands** — `cd tests/integration/e2e && ./.venv/bin/python -m pytest
suites/07_run_detail/test_qa_ps_038_run_detail_duplicate_requests.py -q -rx --runxfail`:
```
E  AssertionError: opening a completed run from history should fetch runs?limit=50
   about once, saw 6: ['http://localhost:8000/api/runs?limit=6',
   'http://localhost:8000/api/runs?limit=50', 'http://localhost:8000/api/runs?limit=6',
   'http://localhost:8000/api/runs?limit=50', 'http://localhost:8000/api/runs?limit=50',
   'http://localhost:8000/api/runs?limit=50']
E  assert 6 <= 2
```
Split by navigation (same probe, phase-by-phase): `/dashboard` 2 (`limit=6` + `limit=50`), `/runs` 3
(`limit=6` + `limit=50` x2), click 1 (`limit=50`).

**Who owns the six** — `frontend/src/store/slices/globalSlice.ts:7` `const RECENT_RUNS_LIMIT = 6;`
fired by `store/listenerMiddleware.ts` on `signedIn`, once per document; and `page.tsx`'s
`isAuthenticated` mount effect, whose result feeds `AppHeader`'s badge via
`DashboardLayout.tsx:2741 recentRuns={recentRuns}`. Both are quoted at length in
[QA-PS-035](#qa-ps-035)'s own Evidence section.

**Not the replay, and not fixed here** — [ISS-840](.knowledge/cards/20260922-2030-ISS-840.md),
confirmed by stack trace (`evidence/qa-ps-038/08-reopen-runs-twice.txt`): the deep-link effect's
skip guard `if (runId === trackedRunIdRef.current)` (`page.tsx:3462`, comment: "Skipping here is
what keeps a client-side nav from /runs from double-fetching (AC3)") is defeated by the remount the
click's own `router.push` causes — the same file says so at `page.tsx:3480-3486`. So
`GET /api/runs/{id}`, `/events?after=0` and the chat-seed `/family` each run **twice** per history
click. That, with [ISS-804](.knowledge/cards/20260922-1646-ISS-804.md)'s two uncoordinated
`getRunFamily` call sites, is what produces the report's `/events` x2 and `/family` x2-4 — and it
needs the 3-analyzer, because the early return there is load-bearing for T6/T7 tab restore,
FIX-298c's `waiting_for_user` fall-through and ISS-779/780's stale-switch checks.

### Decision needed

Does the app shell's own per-mount run-list traffic count against QA-PS-038's budget — i.e. should
this bug's test be re-scoped to the reopen it is actually about, or should the shell fetch be
removed so the test can stand as written?

### Options

- **a) Re-scope the test to the click.** Start collecting after `/runs` has settled and assert
  `<= 1` `runs?limit=50`, which is what the replay fix already delivers. Consequence: QA-PS-038
  closes on FIX-624 with the shell's 2 `limit=6` + 3 `limit=50` per-document fetches accepted as
  intended — the same answer option (a) gives QA-PS-035/036/037. ISS-840 and ISS-804 stay open on
  their own merits (they are `/events` and `/family`, not the run list).
- **b) Gate the shell fetch (QA-PS-035 option b).** Reaches `<= 2` with the test untouched.
  Consequence: identical to QA-PS-035's option b — reopens ISS-232's deep-link latency case and the
  header badge loses its server run list on non-home routes, needing a new endpoint, which is an
  API change 5-fixer may not make alone.
- **c) Leave QA-PS-038 open until QA-PS-035 is answered.** Consequence: nothing is lost — FIX-624 is
  already in the tree either way — but the bug occupies the line while a decision it shares with
  three other bugs is pending.

### What happens after the decision

- Option a): `4-test-writer` moves this test's request collection to after the `/runs` load and
  drops the threshold to `<= 1`; `6-verifier` re-runs the one file and QA-PS-038 closes on FIX-624.
  ISS-785 moves to `resolved` with its `/events`//`family` expectations superseded by ISS-840 and
  ISS-804.
- Option b): back to `3-analyzer` for the header's replacement live-run data path — the same
  follow-up QA-PS-035 option b already needs, and not expressible as an edit to the files ISS-785's
  `applies_to.globs` name.
- Option c): the row stays ESCALATED and is re-dispatched with QA-PS-035's answer.

---

## QA-PS-041
> **Now CLOSED** (2026-09-23) — kept for the trace.

**Title:** My Workflows page calls GET /api/user-workflows four times and loads run history (37 KB)
not displayed on this page · **Route:** /workflows · **Stage:** 5-fixer · **Date:** 2026-09-22
**Report:** [BUGS.md#qa-ps-041](BUGS.md#qa-ps-041) · **Cards:**
[ISS-788](.knowledge/cards/20260922-1816-ISS-788.md) (root — **duplication half fixed**, runs half
escalated), [ISS-815](.knowledge/cards/20260922-1857-ISS-815.md) (**resolved** by
[FIX-627](.knowledge/cards/20260922-2050-FIX-627.md)),
[ISS-813](.knowledge/cards/20260922-1854-ISS-813.md) (**does not reproduce** — measured in
[ISS-841](.knowledge/cards/20260922-2050-ISS-841.md))

### Why escalated

The bug's **duplication half is fixed and measured**, and is in the working tree:
`GET /api/user-workflows` now fires **once** on a cold `/workflows` load, down from 2x (4x on a
client-side nav), and `GET /api/auth/me` was already down to 1x from
[FIX-618](.knowledge/cards/20260922-1945-FIX-618.md). That half needed no decision.

What cannot be built from the card is the rest of the test, which requires **zero** `/api/runs`
calls on `/workflows`. The premise — ISS-788's "every route pays for a 50-row run-history fetch"
— does not hold for the shell this route renders inside: `SavedWorkflowsPage` mounts *below* the
always-rendered `AppHeader`, whose "N Running" badge consumes exactly that run list. Reaching zero
means taking data away from a global surface and reversing the ISS-232 sign-in preload — a product
decision, not a difficulty.

This is the **same question already open as [QA-PS-035](#qa-ps-035)**, whose section says "Same
answer would apply to QA-PS-035 and QA-PS-037", and which [QA-PS-038](#qa-ps-038) also waits on.
QA-PS-041 is the fifth bug behind that one answer. No card on this bug asks for the removal — both
ISS-788's own "where the fix belongs" and ISS-815's prescribe de-duplication, which is done; the
zero-request expectation appears only in the reporter's `BUGS.md` text and the test written from it.

### Evidence

**1. The duplication half is fixed — measured, not asserted.** App on :3000/:8000,
`cd tests/integration/e2e && ./.venv/bin/python -m pytest
suites/05_saved_workflows/test_qa_ps_041_workflows_duplicate_requests.py -q -rA --runxfail
-k list_fetches`, before and after the change to `getUserWorkflows()`:

```
BEFORE: AssertionError: /workflows fetched user-workflows 2x and
        runs=['http://localhost:8000/api/runs?limit=6',
              'http://localhost:8000/api/runs?limit=50']
        assert (2 == 1)
AFTER:  AssertionError: /workflows fetched user-workflows 1x and
        runs=[… the same two …]
        assert (1 == 1 …)   ← the uw_count half of the assertion now holds
```

The full cold-load API set after the fix, from the same run: `/api/runs?limit=6` 1x,
`/api/auth/me` 1x, `/api/user-workflows` 1x, `/api/runs?limit=50` 1x, `/api/workflows` 1x.

**2. Green regression guards for that half** — `cd frontend && npx vitest run
src/lib/api.getUserWorkflowsDedup.test.ts` → `Test Files 1 passed (1) · Tests 3 passed (3)`; and
`src/components/savedworkflows/SavedWorkflowsPage.test.tsx` → `9 passed (9)`.

**3. `/api/runs?limit=50` IS consumed by UI rendered on `/workflows`.** The saved-workflows view is
nested inside the same shell the header sits above:

- `frontend/src/components/layout/DashboardLayout.tsx:2720` — `      <AppHeader` opens the return,
  **before** any `mainView` branch
- `frontend/src/components/layout/DashboardLayout.tsx:2754` — `        recentRuns={recentRuns}`
- `frontend/src/components/layout/DashboardLayout.tsx:3068` — `          {mainView === "saved-workflows" && (`
- `frontend/src/components/layout/DashboardLayout.tsx:3077` — `              <SavedWorkflowsPage onLaunchSaved={handleLaunchSaved} onCreateNew={() => handleSelectFeature("custom")} />`

The header consumes it at `frontend/src/components/layout/AppHeader.tsx:328`
(`const serverRun = recentRuns.find(...)`) and `:371` (`{runningPipelines.length} Running`) —
quoted at length in [QA-PS-035](#qa-ps-035)'s own Evidence section, which is the same shell.

**4. The cache layer already rules this class of fetch out on purpose.**
`frontend/src/lib/api.ts:404-406`: "Run/workflow lists deliberately do NOT [go through the cache]:
their callers refetch precisely to observe a change (a cancel clearing the header's 'N Running'
pill, a gate flipping a status)."

**5. ISS-813 does not reproduce, so two of the four tests are red for a non-defect.** Full capture
in [ISS-841](.knowledge/cards/20260922-2050-ISS-841.md). `/workflows/{id}` and `/workflows/{id}/edit`
each fetch their row **once** per document — with the guard ISS-813 prescribes and, identically,
with it reverted (`performance.getEntriesByType('resource')`, scoped to the current document:
`1913.4 → 2016.7ms` guarded, `1836.8 → 1958.3ms` unguarded, `1729.9 → 1832.4ms` on `/edit`). The
tests read 2x because `_collect_requests` attaches *before* `page.goto`, while the app is still on
the `/workflows/{id}/edit` page that `workflow_id()`
(`suites/05_saved_workflows/test_saved_workflows.py:65-75`) clicked into — so the previous
document's own single fetch is counted against the next one. The guard was built, measured, and
**reverted**; nothing under `frontend/src/store/api/` was changed.

**6. The Duplicate test cannot express its own race, but the defect and the fix are both real.**
Its throttle is `time.sleep(2)` inside a SYNC Playwright route handler
(`test_qa_ps_041_workflows_duplicate_requests.py:100-105`), which blocks the driver thread that is
supposed to be clicking. Replaying the identical steps through the async API
(`await asyncio.sleep(2)`, driver free): **2 POSTs with the guard reverted via `git stash`, 1 POST
with it in place.** Seeded state read back afterwards at 22 rows, zero `(copy)` rows.

### Decision needed

Should `/workflows` still fetch the run list (`/api/runs?limit=50`, plus the `?limit=6` sign-in
preload) that the always-mounted app shell consumes — or should those payloads be scoped away from
non-home routes, and the header's "N Running" badge fed some other way?

### Options

- **a) Accept the app-shell traffic as intended; re-scope the test to the duplication.** Assert one
  `/api/user-workflows`, one `/api/workflows` and allow the shell's `/api/runs` calls instead of
  zero. Consequence: QA-PS-041 closes on FIX-627 with ~37 KB of shell data still fetched per cold
  load. Identical to QA-PS-035 option a), and one answer settles QA-PS-035/036/037/038/041.
- **b) Gate the shell fetch (QA-PS-035 option b).** The test goes green as written. Consequence:
  reopens ISS-232's 12.2s deep-link case and the header badge loses its server run list on
  non-home routes — needs a new endpoint, an API change 5-fixer may not make alone.
- **c) Leave QA-PS-041 open until QA-PS-035 is answered.** Consequence: nothing is lost — FIX-627
  is in the tree either way — but a fifth bug sits on the line waiting for one decision.

### What happens after the decision

- Option a): `4-test-writer` re-scopes `test_workflows_list_fetches_user_workflows_once_and_no_run_history`
  to the one-each assertion, and — independently of the decision — fixes the two ISS-813 tests
  (attach the listener after the `/edit` page settles, or read the id from the API instead of a
  click-through) and the Duplicate test's driver-blocking sleep, per ISS-841. `6-verifier` then
  re-runs the file and QA-PS-041 closes on FIX-627. ISS-788 moves to `resolved` with its Mechanism A
  expectation corrected by supersession; ISS-813 closes as non-reproducing.
- Option b) or c): the row stays ESCALATED and is re-dispatched with QA-PS-035's answer.

---

## QA-PS-046
> **Now CLOSED** (2026-09-23) — kept for the trace.

**Title:** Custom workflow builder calls GET /api/capabilities four times (94 KB wasted) and loads
run history (37 KB) not needed on the composer · **Route:** /workflows/new · **Stage:** 5-fixer ·
**Date:** 2026-09-22
**Report:** [BUGS.md#qa-ps-046](BUGS.md#qa-ps-046) · **Cards:**
[ISS-832](.knowledge/cards/20260922-2001-ISS-832.md) (root — **capabilities half already closed by
FIX-617**, runs half escalated), [ISS-798](.knowledge/cards/20260922-1631-ISS-798.md) (validator's
3/3 reproduction, predates FIX-616/617),
[ISS-833](.knowledge/cards/20260922-2002-ISS-833.md) (**resolved** by
[FIX-629](.knowledge/cards/20260922-2105-FIX-629.md)),
[ISS-834](.knowledge/cards/20260922-2003-ISS-834.md) (**resolved** by FIX-629)

### Why escalated

Everything this bug reported as DUPLICATION is fixed and measured. `GET /api/capabilities` is one
call per cold `/workflows/new` load (FIX-617's `cachedGet`, now with a catalog-length TTL from
FIX-629 so a multi-minute compose session cannot age it out), `GET /api/auth/me` is one, and
`/api/runs` is no longer doubled. The reported 4x/2x counts do not reproduce.

What is left is a SINGLE `GET /api/runs?limit=50`, and it is not waste in the sense the cards
assume. [ISS-832](.knowledge/cards/20260922-2001-ISS-832.md)'s fix section says to "gate or remove
`page.tsx`'s `recentRuns` fetch on the routes that actually render it" on the premise that "the
composer never renders" that state. The premise does not hold: `recentRuns` is handed to
`DashboardLayout`, which renders `AppHeader` ABOVE every `mainView` branch, composer included, and
the header's "N Running" badge is computed from exactly that list. Reaching the test's zero means
deciding to take server-truth live-run data away from a global surface — a product decision, not a
difficulty.

This is the SAME question already open for [QA-PS-035](ESCALATIONS.md#qa-ps-035),
[QA-PS-036](ESCALATIONS.md#qa-ps-036), QA-PS-037, [QA-PS-038](ESCALATIONS.md#qa-ps-038) and
[QA-PS-041](ESCALATIONS.md#qa-ps-041), whose sections state "one answer settles" all of them.
QA-PS-046 is the sixth route asking it. No new decision is needed — this row just needs the
existing one.

### Evidence

**1. What actually fires on a cold `/workflows/new` load, after FIX-629.** App on :3000/:8000,
`cd tests/integration/e2e && ./.venv/bin/python -m pytest
suites/04_composer_canvas/test_qa_ps_046_composer_unneeded_runs_fetch.py -q -rA --runxfail
--run-name qa-ps-046-fix-measure`:

```
E       AssertionError: ISS-832: /workflows/new must not fetch run history (no run list is
        rendered on the composer), saw: ['http://localhost:8000/api/runs?limit=50'] —
        all /api/runs requests: ['http://localhost:8000/api/runs?limit=6',
                                 'http://localhost:8000/api/runs?limit=50']
FAILED suites/04_composer_canvas/test_qa_ps_046_composer_unneeded_runs_fetch.py::
       test_workflows_new_does_not_fetch_run_history[chromium]
```

One `limit=50` and one `limit=6`, not the 2x each
[ISS-798](.knowledge/cards/20260922-1631-ISS-798.md) validated on 2026-09-22 16:31.
Report: `tests/integration/test-runs/2026-09-22T21-02-qa-ps-046-fix-measure/0-report.html`.

**2. The `limit=50` call is `page.tsx`'s `recentRuns` fetch.**
`frontend/src/app/[...view]/page.tsx:1028`:

```tsx
    getWorkflows(currentToken, { limit: 50 })
      .then(({ runs }) => setRecentRuns(runs))
```

`getWorkflows()` builds `path = "/api/runs"` despite its name
(`frontend/src/lib/api.ts:893`), already established by ISS-781/ISS-808.

**3. That list IS consumed by UI rendered on `/workflows/new`.**

- `frontend/src/app/[...view]/page.tsx:4393` — `      recentRuns={recentRuns}` (into `DashboardLayout`)
- `frontend/src/components/layout/DashboardLayout.tsx:2720` — `      <AppHeader` opens the return,
  BEFORE any `mainView` branch
- `frontend/src/components/layout/DashboardLayout.tsx:2754` — `        recentRuns={recentRuns}`
- `frontend/src/components/layout/DashboardLayout.tsx:3118` — `          {mainView === "composer" && (`
  is where `ComposerPage` renders, i.e. INSIDE the shell the header already sits above
- `frontend/src/components/layout/AppHeader.tsx:188` —
  `const liveRunsFromServer = recentRuns.filter((r) => LIVE_STATUSES.has(r.status));`
- `frontend/src/components/layout/AppHeader.tsx:200` —
  `const hasServerData = recentRunsLoaded && recentRuns.length > 0;` — with no fetch this is false
  and the badge falls back to `runningFromNotifs`, the ephemeral notification list, so a run
  launched in another tab stops appearing in the header on the composer.

**4. The page component survives a route change, so a naive gate leaks past the composer.**
`frontend/src/app/[...view]/page.tsx:431` (`const viewPathKey = viewSegments?.join("/") ?? "";`)
exists precisely because `[...view]/page.tsx` is NOT remounted between routes — its cold-mount
effects are keyed on that string. The `recentRuns` effect's deps are `[isAuthenticated]`, so
skipping the fetch on `/workflows/new` leaves `recentRuns` empty for every screen the user visits
afterwards in that session unless the gate is also made a dependency. Any option-b implementation
has to carry that, which is why it is not a two-line change.

**5. The capabilities half needs no decision and is already closed.** FIX-629's coverage block
records both vitest files XPASSing
(`frontend/src/lib/api.sharedGetCache.test.ts`, `frontend/src/store/api/capabilities.test.ts`).

### Decision needed

Should `/workflows/new` (and every other non-home route) keep fetching the 37 KB run list that only
the always-mounted header consumes, or should that fetch become route-scoped, accepting a header
badge that no longer sees runs launched outside this tab?

### Options

- **a) Accept the header's fetch as intended; re-scope the test to the duplication.**
  `4-test-writer` changes `test_workflows_new_does_not_fetch_run_history` to assert AT MOST ONE
  `/api/runs?limit=50` instead of zero. Consequence: QA-PS-046 closes on FIX-629 with ~37 KB of
  shell data still fetched per composer load. Identical to QA-PS-035/036/041 option a) — one answer
  settles all six.
- **b) Gate `page.tsx:1028`'s fetch on the screens that render a run list.** The test goes green as
  written. Consequence: on the composer the header's badge falls back to the localStorage
  notification list (`useNotifications`, FIX-202), losing runs launched in another tab or on
  another device; the gate must also enter the effect's dependency array (Evidence 4) or the list
  stays empty for the rest of the session. QA-PS-036's option b) additionally notes this probably
  wants a new live-runs-only endpoint — an API change 5-fixer may not make alone.
- **c) Leave QA-PS-046 open until QA-PS-035 is answered.** Consequence: nothing is lost — FIX-629
  is in the tree either way — but a sixth bug waits on one decision.

### What happens after the decision

- Option a): `4-test-writer` re-scopes
  `tests/integration/e2e/suites/04_composer_canvas/test_qa_ps_046_composer_unneeded_runs_fetch.py`
  to the at-most-one assertion; `6-verifier` re-runs it plus FIX-629's two vitest files and
  QA-PS-046 closes on FIX-629. [ISS-832](.knowledge/cards/20260922-2001-ISS-832.md) and
  [ISS-798](.knowledge/cards/20260922-1631-ISS-798.md) move to `resolved` with their
  zero-request expectation corrected by supersession.
- Option b) or c): the row stays ESCALATED and is re-dispatched with QA-PS-035's answer; option b)
  goes back to `3-analyzer` for the replacement data path, since it is not expressible as an edit
  to the files ISS-832's `applies_to.globs` name.

## QA-KB-032
> **Evidence missing** — claims below are unproven.
> **Section missing** — the worker did not write its trace.

---

## QA-KB-055
> **Now CLOSED** (2026-10-09) — kept for the trace.

**Title:** Another family's finished revision hijacks the run-detail screen you are viewing · **Route:**
/runs/[id] (run detail, app/[...view]/page.tsx) · **Stage:** 5-fixer · **Date:** 2026-10-07
**Report:** [BUGS.md#qa-kb-055](BUGS.md#qa-kb-055) · **Cards:**
[ISS-745](.knowledge/cards/20260922-1400-ISS-745.md) (root, **resolved** by
[FIX-752](.knowledge/cards/20261007-2214-FIX-752.md)),
[ISS-1074](.knowledge/cards/20261007-2140-ISS-1074.md) (**resolved** by FIX-752),
[ISS-1077](.knowledge/cards/20261007-2142-ISS-1077.md) (open, the subject of this escalation)

### Why escalated

The reported bug is fixed. [FIX-752](.knowledge/cards/20261007-2214-FIX-752.md) lets a foreign revision's
completion take the screen only when the viewed run belongs to that revision's own family. The background bridge,
the content source and the Preview slots now all follow that one decision. Two of the three assertions in
`foreignRevisionHijack.qaKb055.source.test.ts` (ISS-745 and ISS-1074) went from red to green.

The third assertion (ISS-1077) cannot pass unless the Revision Families B1 contract is overturned, and another
test pins that contract:
- It requires the revise handlers to stop passing `contentSourceRunId` as the `postRevision` parent.
- `revisionFamilyLinkage.source.test.ts:28` requires exactly that call.

No code satisfies both. Each fix direction ISS-1077 offers changes product behaviour (see Options). FIX-752 has also
removed the trigger ISS-1077 relies on: the completion-time set is family-gated, and every other writer of
`contentSourceRunId` is navigation or launch.

### Evidence

**1. The two assertions contradict each other.**
`frontend/src/app/[...view]/foreignRevisionHijack.qaKb055.source.test.ts:47-49`:

```ts
  it("ISS-1077: revise/chain actions do not read the mutable contentSourceRunId as the POST parent", () => {
    expect(layout).not.toMatch(/postRevision\(getToken\(\) \?\? "", contentSourceRunId,/);
  });
```

`frontend/src/app/[...view]/revisionFamilyLinkage.source.test.ts:28`:

```ts
    expect(dashboardLayout).toContain('postRevision(getToken() ?? "", contentSourceRunId,');
```

Observed after FIX-752, one file at a time from `frontend/`:
- `npx vitest --run "src/app/[...view]/foreignRevisionHijack.qaKb055.source.test.ts"` gives
  `Tests 1 failed | 2 passed (3)`. The failure is the ISS-1077 case (`evidence/qa-kb-055/02-fix-after-qakb055-source-test.txt`).
  Before the fix it gave `Tests 3 failed (3)` (`evidence/qa-kb-055/01-fix-baseline-before-change.txt`).
- `revisionFamilyLinkage.source.test.ts` gives `Tests 4 passed (4)` (`evidence/qa-kb-055/03-fix-neighbour-tests-after.txt`).

**2. The contract the second test pins.** `frontend/src/components/layout/DashboardLayout.tsx:134-138` (identical at
HEAD `e93aa40ed` and in the working tree):

```ts
  // Revision Families (B1 / D1-D7): the reliable "run id that produced the
  // on-screen content", owned by page.tsx (pipeline_complete + reopen). Every
  // revision launch path sources parent linkage from this — replaces the fragile
  // currentWorkflowRunId heuristic (which mis-matched on double-revision types).
  contentSourceRunId?: string | null;
```

The assertion targets `void postRevision(getToken() ?? "", contentSourceRunId, {` at `DashboardLayout.tsx:1203`,
`:1286`, `:1306` and `:1325`.

**3. The card's own fix directions.** ISS-1077 § "Fix direction": "derive the parent for the revise/chain handlers
from the route-parsed run id ... rather than from mutable state, or compare the two and refuse on mismatch. Adding a
request field the server validates (an expected family root) would be an API-contract change, which is a product
decision, not an analyzer call."

**4. Why a route-derived parent conflicts with behaviour FIX-752 keeps.** FIX-752 keeps FIX-088's same-family
advance:

```ts
          if (completingRunId && (!isForeignCompletion || sameFamily)) {
            setContentSourceRunId(completingRunId);
```

That is `frontend/src/app/[...view]/page.tsx:1643-1644`. Nothing pushes a route on that set (ISS-745 analysis: "No
effect reacts to it by pushing a route"). Suppose the user opens v1 and a same-family v2 then finishes. The screen
shows v2 while the URL still names v1, so a parent taken from the URL revises v1.

**5. What can still write `contentSourceRunId`.**
`git show "HEAD:frontend/src/app/[...view]/page.tsx" | grep -n "setContentSourceRunId("` at HEAD `e93aa40ed` finds:
- `:1630`: the completion set, now family-gated by FIX-752.
- `:2801`: handleSwitchToLiveRun.
- `:2940` and `:2980`: handleSelectWorkflowRun.
- `:3528`: T7 route reopen.
- `:3623`: T11 stream route.
- `:4307`: null at a fresh launch.

### Decision needed

A completion can no longer move `contentSourceRunId` to another family. Should revise and chain keep taking their
parent from `contentSourceRunId` (Revision Families B1)? Or should the handlers guard the parent independently, which
changes either which run gets revised or what the user sees?

### Options

- **a) Keep B1 (recommended).** Retire the ISS-1077 case in `foreignRevisionHijack.qaKb055.source.test.ts`, or invert
  it into the B1 pin, and close ISS-1077 as covered by FIX-752. Consequence: there is no defence in depth. A future
  background writer of `contentSourceRunId` would again mis-parent a revision silently: FIX-173 recorded exactly that on
  2026-08-04, and `create_revision` (`backend/app/api/run_commands.py:5532`) only checks the owner.
- **b) Family-scoped guard, refuse on mismatch.** Thread the URL's run id into DashboardLayout. Revise and chain use
  `contentSourceRunId` only when it is in the URL run's family, and otherwise refuse with a visible message.
  `revisionFamilyLinkage.source.test.ts:28` gets updated. Consequence: a flow that never errors today gains an error
  state. A revise clicked while the family fetch is still in flight also needs a defined behaviour.
- **c) Route-derived parent** (the card's first direction). Consequence: after a same-family advance (URL on v1,
  screen on v2), the new revision is parented on v1. It branches from content the user is not looking at, which
  reverses what FIX-088 intended for that case.
- **d) Server-validated expected family root** on `POST /api/runs/{id}/revisions`. Consequence: the API contract
  changes (a new request field, a backend check and a client change).

### What happens after the decision

- Option a): `4-test-writer` retires or inverts the ISS-1077 case and ISS-1077 moves to `resolved`. The row is then
  set to `FIXED`, and `6-verifier` runs the cards' test files. ISS-745's Test notes give a browser repro, but it costs
  a real revision run, so it needs the owner's go.
- Options b), c) or d): set the row to `TESTED`. `4-test-writer` rewrites the ISS-1077 case for the chosen shape, and
  `5-fixer` implements it on top of FIX-752, which stays in the tree either way.


## QA-KB-112
> **Now ANALYZED** (2026-10-12) — kept for the trace.

## QA-KB-114
> **Evidence missing** — claims below are unproven.
> **Section missing** — the worker did not write its trace.

## QA-KB-117
> **Now CLOSED** (2026-10-12) — kept for the trace.

## QA-KB-121
> **Now CLOSED** (2026-10-12) — kept for the trace.
