# Post-merge backlog — `dev` → `feat/conditional-gates`

Everything deliberately **deferred out of the merge commit**, recorded at merge time so
attribution is not lost later.

Merge: `dev` (`ba608a005`) into `feat/conditional-gates` (`c9ec0149c`).
Merge base: `fd98e148e`. 40 commits incoming, 4 ours, 13 conflicted files.

State at commit: **`tsc` 0 errors**; frontend **134/137 suites, 1183/1195 tests**, stable
across two runs (byte-identical failure sets); backend **3749 passed / 107 failed / 113
skipped**.

Scope note: this list spans spec 014 (conditional gates) and spec 015 (frontend routing)
as well as the merge itself, because the merge is what surfaced most of it.

---

## 1. BLOCKER-ADJACENT — settle first

### 1.1 Baseline diff to attribute 64 backend failures
Of 107 backend failures, 43 are attributed (see §2). The remaining **64 are unattributed** —
no full backend suite was ever run on `c9ec0149c`, so "did the merge cause this?" is
currently unanswerable.

```bash
git worktree add /tmp/premerge c9ec0149c
cd /tmp/premerge/backend && python3.11 -m pytest tests/agents tests/unit tests/integration -q
# then diff the failure sets against the post-merge run
```

Note: two collection errors must be patched in the worktree too or pytest aborts and runs
nothing — see §3.1 and §3.2.

### 1.2 HITL gate cluster — possible regression in OUR engine change
Six failures, in files **neither side of the merge touched**:

```
test_gates.py                  test_raising_hitl_gate_blocks_and_stops_gate_evaluation
                                 assert ['block','block'] == ['block']
test_gates.py                  test_engine_sentinel_carries_human_gate_edit_detail
                                 assert 'pass' in []
test_declared_gate_streaming.py  duplicate review_gate_ready for already-approved
test_declared_gate_streaming.py  expected exactly one review_gate_ready per gated agent
test_declared_gate_streaming.py  test_declared_gate_rejection_cancels_the_run
test_restart_resume.py           WR-03 regressed: declared-gate rejection must end the run
```

The signature is a gate **firing twice**. Prime suspect is this branch's HITL split:
`_POST_STEP_GATES` now contains `"human"`, and `human` / `before-human` are registered on
one `HumanGate` class under two names (`agents/capabilities/gates/human.py`). A gate
evaluating in both the pre- and post-step loop would look exactly like this.

Resolve via §1.1 — if red on `c9ec0149c` it is known branch debt; if green, the merge
caused it and it is an engine regression in gating.

---

## 2. Backend failures — attributed, deferred

### 2.1 Parity traps — 33 failures — OURS, pre-existing (proven)
```
test_manifest_parity.py      15   test_planner_run_everywhere / test_clarify_defaults_match_engine
test_id_alias_resolver.py    15   test_compiled_planner_is_run_everywhere / ..._clarify_defaults...
test_compiled_plan_runs.py    3   test_dispatchable_count_is_13 + 2 param cases
```

These sweep **every** workflow on disk and require each to be declared in two allow-list
tables. We added 7 `ex_A*` fixtures without adding entries.

Proven pre-existing, not merge-caused:
- `_MANIFEST_BACKED_IDS` is disk-derived; the sweep was never widened by dev.
- `custom-agent/AGENT.md` (dated 2026-08-19, predates both branches) is what makes our
  fixtures count as "product workflows" via `_is_product_workflow`.
- Dev's edit to the test was purely additive — entries for their own two new pipelines.
- **`sc001-test-fixture` fails identically, and it is dev's fixture** — both sides made the
  same omission independently. Not the shape of a merge interaction.

Fix: add the 7 `ex_*` ids (and `sc001-test-fixture`) to `_PLANNER_SKIP_IDS` and
`_ENGINE_PIPELINE_DEFAULTS`, exactly as dev did for theirs; bump the count pin in
`test_dispatchable_count_is_13`. Semantically true — these are fixtures with no clarify
round-trip.

### 2.2 Dev's own new code — 9 failures — hand back to the dev branch owners
```
test_cognito_verifier.py               1   tampered-signature rejection
test_concierge_proposal_channels.py    3   concierge-chat-upload seam
test_admin_authorization_matrix.py     5   from get_current_user -> get_current_user_with_payload
```

### 2.3 Pending §1.1 — unattributed
```
test_nav_coverage.py            11
test_allowed_step_keys.py        4
test_phase8_live.py              4   (live — may be credential-gated)
test_update_specs_enforcement.py 3
test_wire_parity.py              2   prototype / prototype_revision golden drift
test_local_runtime.py            2
test_live_contract.py            2
test_phase5_revision_validation  2
test_revision_gating.py          2
conditional-gate fixtures        4   test_conditional_branch_route_t25,
                                     test_conditional_divert_v4_validation,
                                     test_conditional_human_gate_source_t26 (x2)
test_entitlement_parity.py       3   FE/BE tier→pipeline parity
test_workflow_resolver.py        2   assert 1 == 3
test_pipeline_workflows.py       4   every_consumes_is_satisfied_upstream
                                     [prototype{,_revision,_large_revision,_feature_revision}]
+ singles: test_manifest_coverage, test_exec_runs, test_composed_fanout,
           test_live_harness, test_restart_resume
```

`test_pipeline_workflows` is worth a close look regardless — `consumes`-satisfaction is the
resolver-reordering area (ADR-0004) from this branch, meeting dev's three new revision
workflows.

---

## 3. Fixes made OUTSIDE the merge — decide whether to keep or push upstream

These are in the working tree and will land in the merge commit unless removed. Each is
independently revertible.

### 3.1 `backend/tests/unit/test_sse_stream.py` — dev's bug, fix belongs on `dev`
Dev removed `_STREAM_TERMINAL_TYPES` from the module-scope import while keeping the
class-body `@pytest.mark.parametrize(..., sorted(_STREAM_TERMINAL_TYPES))` at line 1569.
Verified broken on `MERGE_HEAD` itself. Restored the import. **Report upstream.**

### 3.2 `backend/tests/unit/test_shutdown_reachability.py` — pre-existing, both branches
Line 204 used a nested same-type quote inside an f-string (PEP 701, Python 3.12+). This
project runs 3.11, so the file has never been collectable here. Changed the inner quotes.
Only line 204 — line 214 has an identical-looking call that is an ordinary statement and is
valid.

**Both 3.1 and 3.2 were aborting collection entirely** (`Interrupted: 2 errors during
collection`), so no backend test could run at all: 3930 collected + 2 errors → 3991
collected, 0 errors.

### 3.3 `backend/tests/agents/test_registry_capabilities.py` — OUR branch's debt
Added `("gate", "before-human")` and `("gate", "conditional")` to `_EXPECTED_NAMES`. This is
a deliberate drift guard — *"registering a new name (or dropping one) must trip this"* — and
our branch registered both gates without updating it. Updating the allow-list is the
sanctioned response, not bending the app to the test.

### 3.4 `backend/app/api/agents.py` — dev's bug, we fixed it here
`AgentResponse.pipeline_type: str` while `loader.py` now yields `str | list[str]`.
`GET /agents/pipelines/prototype` raised a pydantic `ValidationError` → 500 for
`prototype-plan` / `-build` / `-validate`. Widened to `str | list[str]`, matching what
`/agents/library` already forwards. **Report upstream.** (Went unnoticed on dev because
`getPrototypePipeline` in `store/api/agents.ts` has zero callers — dead export.)

### 3.5 `frontend/vitest.setup.ts` — infrastructure, benefits everyone
Added a `localStorage` polyfill. Root cause is **Node ≥22's own experimental `localStorage`
shadowing jsdom's** — without `--localstorage-file` it resolves to `undefined`. Three
separate workarounds already existed for this (`useNotifications.fix202.test.tsx`,
`DesignSystemPicker.reskin.test.tsx`, and `lib/api.ts`'s `getToken` guard).

Two deliberate choices, both documented in the file: installed via `Object.defineProperty`
(merely *reading* the global triggers Node's warning once per worker) and as a plain value
rather than `vi.stubGlobal` (so a test's own `vi.unstubAllGlobals()` restores it instead of
removing storage — which is what broke `api.refreshRetry.test.ts`).

---

## 4. Frontend — 12 failures, all pre-existing on this branch, none merge-caused

Stable across two full runs; failure sets byte-identical.

### 4.1 `ComposerPage.test.tsx` (7) + `CanvasView.test.tsx` (2)
Base-era tests against code this branch rewrote: `ComposerPage.tsx` +215/-16,
`CanvasView.tsx` +990/-87 — **ours alone**, dev touched neither, and neither test file was
modified by either side. The mount log makes the mismatch explicit: the test passes
`workflowType: 'user_stories'` while our code's own comment states `"custom"` is the only
type the component ever mounts for.

### 4.2 `WorkflowHistory.divertLinks.test.tsx` (3)
```
renders 'Diverted to X →' / '← Continued from X, step S'
omits the step clause when diverted_at_step_id is genuinely null
clicking the divert badge does not ALSO open the badge's own row (stopPropagation)
```
Both the test (+228) and `WorkflowHistory.tsx` (+150/-9) are ours alone and **byte-identical
to `c9ec0149c`** (`git diff HEAD` on them is empty).

Worth checking together with the migration in §5.1 — same feature (`diverted_at_step_id`),
though these fail on rendering, not schema.

---

## 5. Merge defects found and FIXED (recorded for traceability)

### 5.1 Duplicate alembic revision `0033` — real merge defect
Ours (`0033_add_diverted_at_step_id`, spec-014 divert) and dev's
(`0033_user_api_key_expiry`, Cognito) both declared `revision = "0033"`,
`down_revision = "0032"`. Alembic reported **two heads**, and dev's `0034_mfa_verified_at`
(`down_revision = "0033"`) was ambiguous between them.

The merge re-homed our `0031`→`0036` and `0032`→`0037` to make room for dev's Cognito
`0031`–`0035`, but missed this one: both sides added a *new file with a different filename*,
so git saw no conflict and landed both.

Re-homed ours to **`0038`** (`down_revision = "0037"`), documented in its docstring.
`alembic heads` → single head. `test_alembic` + `test_migrations` + `test_user_workflows`:
**51 passed, 0 failed** (was 10 failing).

### 5.2 Two files staged WITH conflict markers still in them
`AppHeader.tsx` and `IdeaInputPage.tsx` were already `git add`-ed while still containing
`<<<<<<<` markers — they would have gone straight into the commit. Both resolved.

### 5.3 Silent loss `tsc` could not see
This branch's T9/FR-004 back/forward `mainView` re-sync effect in `DashboardLayout.tsx` had
been **deleted outright** — a deleted `useEffect`, no dangling reference, no error. A comment
at line 335 still referred to it. Without it, browser back/forward changes the URL but not
the rendered screen. Restored from the merge stage, plus the matching effect for
`/settings/{tab}`.

**Lesson worth keeping: a green typecheck does not prove a merge is complete.** Deleted
effects, deleted JSX attributes, and deleted list entries leave no trace.

---

## 6. Infrastructure

### 6.1 `pytest-xdist` is unusable in this repo
`-n 2` on a single test file reproduces `INTERNALERROR ... KeyError: <WorkerController gw0>`,
caused by concurrent `Base.metadata.create_all` in `tests/conftest.py:109`
(`sqlite3.OperationalError: table users already exists` — `create_all` is
SELECT-then-CREATE, so workers race).

This contradicts the conftest, which is explicitly written *for* xdist
("One database FILE per xdist worker", `test-{worker}-{pid}.db`, "PER PROCESS, not merely
per worker"). Something is not giving each worker a distinct path. Corroborating signal:
**CI never uses `-n`** — it shards by explicit file lists across four separate jobs.

Working local equivalent (used for this run):
```bash
pytest tests/agents &   pytest tests/unit &   pytest tests/integration tests/properties tests/ci &
```
Separate processes → separate PIDs → separate DB files. `nice -n 10` to stay responsive.

### 6.2 Debug logging still in the frontend
`console.log("[wf] 1…7", …)` and the `debugLabel` prop remain in `IdeaInputPage.tsx` /
`ComposerPage.tsx`. Deliberately left in place — dropping them silently during a merge is
exactly the class of invisible edit that caused the damage in §5. Remove as its own change.

---

## 7. Pre-existing open issues (carried forward, unrelated to the merge)

- **ISS-171** — `read_files: false` not enforced at runtime; 11 `tool_call`s executed with
  `ls /` returning a real listing. Security-adjacent. Traced inside `DeepAgentRunner` past
  `factory.py:389`. This is why A1 fails.
- **ISS-170** — post-step `gate_blocked` does not halt the run; the conditional gate's
  `GATE_BLOCK` has no handling arm in the POST-step dispatch loop, so control falls through
  to `cursor + 1` and runs whichever branch is declared first. Mitigated only by
  `no gate_blocked` assertions in 8 `.http` runners.

---

## 8. Knowledge base

- Merge not yet recorded in `.knowledge/` — no cards/ADRs for the resolution decisions
  (the auth 401 ladder composition, the settings-tab seeding, the `0033`→`0038` re-homing).
- **7 DOMAIN cards flagged stale** by the pre-commit hook at `c9ec0149c`, deferred then
  because it exceeded its `--max-refresh` limit of 3:
  ```
  /velocity diagrams DOMAIN-auth-and-entitlements DOMAIN-context-assembly \
    DOMAIN-deliverables-and-artifacts DOMAIN-execution-strategies \
    DOMAIN-hitl-gating DOMAIN-run-streaming DOMAIN-workspace-isolation
  ```

---

## 9. The recurring pattern — worth one deliberate pass

Five independent instances of **spec-014/015 features landing without their tests updated**:

| # | Where | Count |
|---|---|---|
| 1 | `test_registry_capabilities` drift guard — gates registered, allow-list not updated | 1 (fixed, §3.3) |
| 2 | Parity traps — 7 `ex_*` fixtures never declared | 33 (§2.1) |
| 3 | `ComposerPage` / `CanvasView` — base-era tests vs a full rewrite | 9 (§4.1) |
| 4 | `WorkflowHistory.divertLinks` — divert-link UI | 3 (§4.2) |
| 5 | HITL gate cluster — *suspected*, pending §1.1 | 6 (§1.2) |

This matches the note made at `c9ec0149c`: *"No unit tests for any of the ~11 engine/API
changes."* Recommend one dedicated pass rather than folding it into the merge.
