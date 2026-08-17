---
phase: quick-260813-3wo
plan: 01
status: blocked-awaiting-live-proof
completed_tasks: 6
total_tasks: 7
blocked_on: "AWS SSO token expired — Bedrock unreachable, so Task 7's two live runs could not be performed"
files_modified:
  - backend/app/api/run_stream.py
  - backend/tests/unit/test_sse_stream.py
  - frontend/e2e/fixtures/mockSse.ts
  - frontend/e2e/tests/ts-sse-resilience.spec.ts
commits:
  - 8d9b8930 test(quick-260813-3wo) durable SSE replay must carry the row's event_id (RED)
  - 5c367839 fix(quick-260813-3wo) merge the durable row's event_id/seq onto replayed SSE frames
  - 57498dd8 test(quick-260813-3wo) a replayed identity-less narrator card renders twice (RED)
  - 2b88c6f5 fix(quick-260813-3wo) mock the fixed replay projection in the SSE e2e harness
---

# Quick 260813-3wo — SSE durable replay dropped the row's event_id

## Status: 6 of 7 tasks complete. NOT live-proven.

Tasks 1-6 are complete, committed, and evidenced below. **Task 7 (the live
double-run proof) could not be performed**: the AWS SSO token for profile
`hex-uki` has expired, so every Bedrock call from the backend fails and a
launched `user_stories` run parks without ever completing. That is an
authentication gate requiring an interactive browser login, not a code defect.
Nothing here should be treated as live-verified until the two runs in
"Outstanding" below have been executed and their two `LIVE LANE COUNTS` lines
pasted into this file.

## The change

One line of production code, `backend/app/api/run_stream.py` (durable-replay
step 1 of `_iter_sse_frames`):

```python
# before
yield _sse_frame(r.seq, r.type, r.payload_json)
# after
yield _sse_frame(
    r.seq, r.type, {**(r.payload_json or {}), "event_id": r.event_id, "seq": r.seq}
)
```

### Why it works

The replay served `payload_json` raw, discarding the row's identity COLUMNS. The
engine stamps `seq`/`event_id` into the payload at its single emit boundary, so
engine-authored rows carry identity twice and the merge is a provable no-op for
them. But four event types are persisted by the app layer with **no** identity
inside the payload — `chat_reply`, `chat_message`, `chat_usage`, `run_resuming`.
For those the columns are the only identity that exists.

The narrator's milestone card is one of them: `persist_milestone_card` writes a
payload of just `{pipeline_run_id, message_id, card_kind, text, deep_link}` and
mints the durable `event_id` column as `chat_reply:{source_event_id}`. The
frontend keys the assistant bubble on `data.event_id`, falling back to
`chat-reply:{message_id}` — a key the narrator's durable id can never equal. So
an anonymous replay produced a second, differently-keyed copy of a card the
durable REST twin (`getRunEvents`, which has merged the columns since BUG-018)
also delivers. The columns are merged LAST, so they win over any same-named
payload key and a poisoned payload cannot forge a client-visible identity.

Lines 220, 258 and 279 of `run_stream.py` are untouched, `run_commands.py` is
untouched, and no frontend production file was modified.

## Task 1 — backend RED

Baseline first, whole file in isolation:

```
======================== 43 passed, 1 warning in 3.83s =========================
```

New `TestReplayIdentityProjection` against the UNFIXED code:

```
collected 44 items

tests/unit/test_sse_stream.py ...F...................................... [ 95%]
..                                                                       [100%]

=================================== FAILURES ===================================
_ TestReplayIdentityProjection.test_replayed_identity_less_chat_reply_carries_its_row_identity _
tests/unit/test_sse_stream.py:281: in test_replayed_identity_less_chat_reply_carries_its_row_identity
    assert data.get("event_id") == row_event_id
E   AssertionError: assert None == '3ced8de1-2e70-4429-b875-5fe1e3b4597d'
E    +  where None = <built-in method get of dict object at 0x10fb35940>('event_id')
E    +    where <built-in method get of dict object at 0x10fb35940> = {'card_kind': 'deliverable', 'message_id': 'm1', 'pipeline_run_id': 'run-1', 'text': 'Delivered'}.get
=========================== short test summary info ============================
FAILED tests/unit/test_sse_stream.py::TestReplayIdentityProjection::test_replayed_identity_less_chat_reply_carries_its_row_identity
=================== 1 failed, 43 passed, 1 warning in 3.82s ====================
```

The failure is exactly the predicted one: `event_id` absent from `data`, not an
error and not a collection failure.

## Task 2 — backend GREEN

```
collected 44 items

tests/unit/test_sse_stream.py .......................................... [ 95%]
..                                                                       [100%]

======================== 44 passed, 1 warning in 3.76s =========================
```

43 baseline + 1 new, zero failures. No other test moved pass to fail — including
the far-later fan-out/pump suites and the wire-parity test.

### The line-180 reconciliation

`test_replay_from_cursor_projects_seq_frames` was RECONCILED, not deleted and not
downgraded to a subset check. It now reads the row's real persisted `event_id`
back from the DB and asserts the full merged dict:

```python
row_event_id = db_session.query(RunEvent).filter_by(run_id="run-1", seq=2).one().event_id
...
assert replay[0]["data"] == {"seq": 2, "text": "hi", "event_id": row_event_id}
```

A uuid literal would be wrong on every run — `_seed_events` mints a fresh uuid4
per row.

### Why wire-parity still holds (verified, not assumed)

`test_endpoint_frames_satisfy_wire_parity` seeds durable rows whose `event_id`
column is a random uuid4 that would now overwrite the payload's engine-stamped
value. It still passes because `seq` and `event_id` are both in
`_VOLATILE_STRIP_KEYS` (`tests/agents/characterization/_normalize.py:129-130`),
so the normalizer strips them from both sides of the compare.

## Task 3 — standing gates

Characterization goldens (5 pipelines):

```
collected 10 items
tests/agents/test_characterization_prototype.py ..                       [ 20%]
tests/agents/test_characterization_prototype_revision.py ..              [ 40%]
tests/agents/test_characterization_app_builder.py ..                     [ 60%]
tests/agents/test_characterization_od_prototype.py ..                    [ 80%]
tests/agents/test_characterization_od_ppt.py ..                          [100%]
======================== 10 passed, 1 warning in 35.08s ========================
```

`git status --porcelain` and `git diff --stat` immediately after that run were
both **empty** — ZERO golden fixture files modified or regenerated.

`lint-imports`, run FROM `backend/` (real contract output, not the
"Could not read any configuration" false pass):

```
Analyzed 215 files, 526 dependencies.
-------------------------------------

kernel imports only capability ports (scaffold) KEPT
agents.workflows must not import the execution kernel or the web layer KEPT
agents.capabilities must not import the execution kernel or the web layer KEPT
agents.runtime must not import the execution kernel or the web layer KEPT

Contracts: 4 kept, 0 broken.
```

## Task 4 — mock fidelity, and the opt-in vs global decision

**(a) Replay-catch-up modelling: OPT-IN, and removed entirely in Task 6.**
Making the identity-stripping unconditional moved three pre-existing tests from
pass to fail — `TS-SSE-RESILIENCE-01`, `-03` and `-04`, which assert
`e.data.event_id` on replayed `chat_message`/`chat_reply` frames. That is itself
a finding: **the existing suite already encodes the POST-fix wire.** So the
stripping was gated behind an off-by-default `simulatePreFixReplay` flag that
only the new spec set, and Task 6 deleted the flag and the stripping together.

**(b) The durable REST twin: GLOBAL.** Decision evidence, full mocked suite
(`--project=mocked`), failing-test lists compared by NAME as set-diffs:

| Run | Result |
|---|---|
| pre-change baseline (this machine, this session) | 34 failed / 108 passed / 43 skipped |
| with the REST twin global, stripping off | 30 failed / 112 passed / 43 skipped |
| final (Task 6 state) | 33 failed / 110 passed / 43 skipped |

Newly-failing versus the pre-change baseline: **EMPTY** in both measurements.
That is the criterion the plan set for going global, and it is met.

Corrections to earlier interim claims, recorded because they were load-bearing:

- The three `ts-t.history` rows (`:37`, `:65`, `:110`) that went green in the
  interim run are red again in the final run. They are **flaky, not fixed** by
  the REST twin. The commit message on `57498dd8` says "three pre-existing
  ts-t.history failures fixed" — that claim is wrong and is corrected here.
- The recorded 34-entry `baseline-fails.txt` and this session's fresh 34-entry
  baseline differ by two flaky rows (`ts-l.token-usage:38` in, `ts-r.cancel:117`
  out). Backend-only commits cannot affect the mocked suite, so this is
  pre-existing flake.
- The plan states the mocked suite "cannot exercise the completion-backfill path
  at all". That is not quite right: `DashboardPage.stubRunEvents`
  (`e2e/fixtures/dashboard.ts:119-126`) already serves
  `GET /api/runs/{id}/events` for `ts-live-state.spec.ts` and
  `ts-u.revisions.spec.ts`. It is a static caller-supplied stub registered later
  via `page.route`, so it takes precedence over the new tail-backed twin where
  used — no conflict, and no second implementation of the same behaviour.

## Task 5 — e2e RED, and the planning error it exposed

The plan's stated mechanism was incomplete, and the first three attempts at the
prescribed test could not be made red. `page.tsx` calls `detachRun` on
`pipeline_complete` ("no reconnect, no ~14k re-replay", BUG-015), and with only
that in view the run's stream unmounts and the anonymous replay copy is never
delivered at all — one card, every time, over settle windows up to 12 seconds.

The missing piece is in `RunConnectionProvider.tsx`, read end to end:
`liveRunIds` is `union(autoIdsRef, focusedRunIdRef)`, and `detachRun` clears
**only** the focus. A run that is also in `autoIdsRef` keeps its connection
mounted and **does** reconnect after the terminal close. `autoIdsRef` is
populated only by `refreshLiveRuns()`, which requires both an
`AUTO_STREAM_STATUSES` status from `GET /api/runs` and the run id in
`sessionStorage["tab_launched_run_ids"]`, and which runs on boot (too early) and
on `online`/`visibilitychange` — the latter being exactly what a mid-run network
blip triggers. This also explains the DROP=1 versus DROP=0 asymmetry the live
script was built around.

`TS-SSE-RESILIENCE-06` therefore launches through the real UI flow, asserts the
run id really is in `tab_launched_run_ids`, fires `online` while the run is still
running, and proves `refreshLiveRuns()` actually ran via a `GET /api/runs`
round-trip — none of it assumed. Observed RED:

```
  1) [mocked] › e2e/tests/ts-sse-resilience.spec.ts:301:7 › TS-SSE-RESILIENCE — sse-resilience transport (D-14) › TS-SSE-RESILIENCE-06 a narrator milestone card replayed after the terminal close renders exactly ONCE
    Error: expect(locator).toHaveCount(expected) failed
    Locator:  getByTestId('chat-result-card').filter({ hasText: '3WO-DELIVERED-MARKER' })
    Expected: 1
    Received: 2
    Timeout:  10000ms
    Call log:
      - Expect "toHaveCount" with timeout 10000ms
      - waiting for getByTestId('chat-result-card').filter({ hasText: '3WO-DELIVERED-MARKER' })
        24 × locator resolved to 2 elements
           - unexpected value "2"
  1 failed
  4 passed (17.6s)
```

Two cards, and the four pre-existing TS-SSE-RESILIENCE tests still pass.

## Task 6 — e2e GREEN

The temporary pre-fix modelling was removed **entirely**: the
`simulatePreFixReplay` flag, the `IDENTITY_LESS_TYPES` set, the replay/live frame
partition and the `serialize()` parameter are all deleted. No dead toggle and no
second implementation of the replay-serving path survive; the net remaining diff
for that half is a comment naming the invariant and pointing at
`backend/app/api/run_stream.py`. The REST twin stays — it is the permanent
fidelity gain.

```
Running 5 tests using 5 workers
[1/5] ... TS-SSE-RESILIENCE-01 sse-resilience: page reload resumes the transcript via native Last-Event-ID
[2/5] ... TS-SSE-RESILIENCE-06 a narrator milestone card replayed after the terminal close renders exactly ONCE
[3/5] ... TS-SSE-RESILIENCE-04 sse-resilience: mock harness shares ONE monotonic seq/event_id space across tabs (harness contract — not a backend delivery guarantee)
[4/5] ... TS-SSE-RESILIENCE-03 sse-resilience: auto-reconnect after a drop replays only past-cursor frames
[5/5] ... TS-SSE-RESILIENCE-02 sse-resilience: route-change keeps the resume cursor (app-level ownership)
  5 passed (7.7s)
```

Full mocked suite in this final state: 33 failed / 110 passed / 43 skipped, with
a set-diff against the pre-change baseline showing **zero newly failing tests**.

## Task 7 — BLOCKED (authentication gate)

The backend was correctly prepared: the local uvicorn runs without `--reload`, so
the process serving `127.0.0.1:8010` (started 02:28:23) predated the 03:04:31
edit and was running the OLD code. It was restarted at 03:35:28 with the exact
prescribed command and answered `health=200`. It is still up.

The first live run then produced:

```
LAUNCHED FIXPROOF260813A drop=true
clarify skipped t+3s
>>> offline
>>> online

LIVE LANE COUNTS (FIXPROOF260813A, drop=true): {"onRunScreen":true,"delivered":0,"openInPreview":0,"runStarted":0,"clarAnswered":1}
```

No `settled` line, and zeros across the board — the run never completed. The
backend log gives the cause unambiguously:

```
botocore.exceptions.TokenRetrievalError: Error when retrieving token from sso: Token has expired and refresh failed
agents.planner.smart_planner: SmartPlanner failed: ... Token has expired and refresh failed — using default context
agents.execution_engine.clarify_engine: ClarifyEngine LLM generation failed: ... — falling back to static library
```

Reproduced directly through the backend's own credential path:

```
AWS_PROFILE=hex-uki AWS_REGION=eu-central-1 python3.11 -c "...bedrock-runtime converse..."
BEDROCK FAIL: TokenRetrievalError Error when retrieving token from sso: Token has expired and refresh failed
```

(`aws sts get-caller-identity` succeeds from a different cached credential path,
which is why this is easy to mistake for a working session — the SSO token
itself is expired.)

Run `53889199` (`FIXPROOF260813A`) is parked at `waiting_for_user` and is idle;
it burns nothing. No `od_prototype` run was launched, resumed, gated or opened at
any point, and no run pill was ever clicked.

### Outstanding — the exact steps to finish

1. `aws sso login --profile hex-uki` (sso-session `hex-uki-sso`, start URL
   `https://d-9067839868.awsapps.com/start`) — interactive browser flow.
2. Restart the backend so it picks up the refreshed token, from `backend/`:
   `AWS_PROFILE=hex-uki AWS_REGION=eu-central-1 ENV=development ANTHROPIC_API_KEY= RUNS_ROOT=/tmp/flowin-runs DATABASE_URL="sqlite:///./dev.db" python3.11 -m uvicorn app.main:app --host 127.0.0.1 --port 8010 --timeout-graceful-shutdown 5`
3. Two runs with FRESH markers (A and B above are now burned):
   `MARK=FIXPROOF260813C DROP=1 node <scratchpad>/20-live-control.mjs`
   `MARK=FIXPROOF260813D DROP=0 node <scratchpad>/20-live-control.mjs`
4. Both must print `delivered:1`, `openInPreview:1`, `runStarted:1`,
   `clarAnswered:1`. If either shows 2, the fix is not proven. Paste both lines
   here and set `status: complete`.

## Out of scope — for a later bookkeeping pass to file as its own new issue

Recorded verbatim as required; no code or test for it lands in this change:

> `frontend/src/hooks/useRunStream.ts:301` — `if (type === "pipeline_cancelled" || type ===
> "pipeline_failed")` omits `pipeline_complete` from the terminal-frame list that ADR-0001
> (`.knowledge/cards/ADR-0001.md`) governs. ADR-0001's own "Negative consequence" predicts
> exactly this: "the terminal-frame list is maintained by hand. A new terminal frame type
> that is not added to that branch reintroduces the banner, and the symptom will look like a
> UI bug rather than a dispatcher omission." No code or test for it lands in this change.

A second candidate surfaced during Task 5 and is offered for the same pass:
`RunConnectionProvider.detachRun` clears only the sticky focus while membership
is `union(autoIdsRef, focus)`, so BUG-015's "no reconnect after a terminal" is
defeated for any run that a wake put into `autoIdsRef`. That incompleteness is
the reason this duplicate is reachable at all on the live stack.

## Threat model

`T-3wo-01` (information disclosure) accepted as planned: the rows are already
owner+workspace scoped by `ScopedStore`, and the REST twin has surfaced these
same two columns to the same principal since BUG-018. `T-3wo-02` (payload key
shadowing) is mitigated by construction — the columns are merged last and always
win. `T-3wo-03` accepted: no extra query, no extra retained object, and the
`rows = ()` / `r = None` release is untouched. `T-3wo-SC`: no npm/pip package was
installed by this change.
