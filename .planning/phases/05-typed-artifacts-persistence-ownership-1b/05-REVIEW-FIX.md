---
phase: 05-typed-artifacts-persistence-ownership-1b
fixed_at: 2026-06-08T14:10:00Z
review_path: .planning/phases/05-typed-artifacts-persistence-ownership-1b/05-REVIEW.md
iteration: 1
fix_scope: all
findings_in_scope: 3
fixed: 2
skipped: 1
status: partial
findings:
  IN-01: fixed
  IN-02: fixed
  IN-03: skipped
supersedes: 2e36bae
---

# Phase 05: Code Review Fix Report (Info pass)

**Fixed at:** 2026-06-08T14:10:00Z
**Source review:** `.planning/phases/05-typed-artifacts-persistence-ownership-1b/05-REVIEW.md`
**Iteration:** 1
**Fix scope:** all (Info findings)

> **Supersedes the prior Critical+Warning fix report.** A previous
> `--fix --auto` run already landed 11 Critical+Warning findings across commits
> `fbc3e2f..2d72081`, and that earlier `05-REVIEW-FIX.md` (committed at
> **`2e36bae`**, preserved in git history) documented those. REVIEW.md frontmatter
> is `status: clean` (zero Critical/Warning). This pass was run explicitly with
> `--fix --all` to address the 3 documented **Info** findings (IN-01, IN-02,
> IN-03). This document overwrites the prior report; consult git `@2e36bae` for
> the Critical+Warning record.

**Summary:**
- Findings in scope: 3
- Fixed: 2 (IN-01, IN-02)
- Skipped: 1 (IN-03 — intentional Phase-3 stub, reviewer classified "no action needed")

## Fixed Issues

### IN-01: `_handle_revision` skips run-events persistence (silently) when `owner_id` is falsy

**Files modified:** `backend/agents/execution_engine/engine.py`
**Commit:** `38077bf`
**Applied fix:** Added a fail-loud `ValueError` guard at the top of
`_handle_revision` (immediately after the existing empty-instruction guard):
`if not owner_id: raise ValueError("_handle_revision requires a real owner_id (AUTHZ-03)")`.
This mirrors the existing falsy-owner `ValueError` in `ClarifyEngine.run`
(clarify_engine.py:113-116) so the contract is explicit at the seam rather than
encoded in a downstream `store.write_ref` failure. Before this change, the
sink-arm + scope-writeback were gated on `if owner_id and _rev_ws_id:`, making a
truthy `owner_id` an implicit precondition. The live WS call site always passes
`owner_id=user.id`, so this guard never fires on the production/passing path —
observable behavior for every currently-passing path is unchanged (backward-compat
/ semantic-event-parity preserved). The signature keeps its keyword default for
back-compat.

### IN-02: `set_run_scope` lookup is unscoped-by-owner by design but lacks a same-owner sanity assertion

**Files modified:** `backend/agents/authz.py`
**Commit:** `8be60ae`
**Applied fix:** Added a defensive same-owner guard inside `set_run_scope` after
the row is fetched and confirmed non-None: read the row's existing `owner_id`;
if it is non-None AND differs from the supplied `owner_id`, raise
`PermissionError` ("cross-owner re-scope is not permitted, AUTHZ-03") rather than
clobbering it. Stamping remains legal onto an unscoped row (`owner_id is None`,
the live revision-run-stamp case) or a row already owned by the same principal.
The pre-existing falsy-principal `ValueError` (lines 369-374) was NOT weakened.
On the single live call site (a freshly-created revision run whose
`owner_id == user.id == supplied owner`), the existing owner already equals the
supplied owner, so the new guard never fires — observable behavior on the passing
path is unchanged (default-deny scoping / backward-compat preserved). This turns a
future cross-owner misuse into a loud failure instead of a silent overwrite.

## Skipped Issues

### IN-03: revision `pipeline_complete` reports `total_duration: 0.0` and `agents_completed: 1` as constants

**File:** `backend/agents/execution_engine/engine.py:2843-2845`
**Reason:** skipped — intentional Phase-3 stub; deferred work, do not implement.
The reviewer explicitly classified this as **intentional, not a defect**: the
placeholder `total_duration=0.0`, `agents_completed=1`, `agents_total=1` are tied
to the not-yet-wired DeepAgent revision loop (the method comment at engine.py:2795-2797
notes the full revision loop is deferred), and the review stated "no action needed
for this phase." A genuinely trivial+safe real-elapsed-`total_duration` measurement
was considered and rejected: (a) it would change observable `pipeline_complete`
event payload values on the revision path that was *just stabilized* by the CR-01
real-DB regression fix (the new `test_revision_run_events_persist_and_resolve_on_real_db`
asserts the `pipeline_complete` `run_events` row persists/replays — churning the
payload risks regression on a freshly-stabilized path); and (b) `agents_completed`
/`agents_total` genuinely cannot be made "real" without pulling in the deferred
revision-agent loop, so a real duration alongside still-stubbed agent counts would
produce an internally-inconsistent payload. Per the "when in doubt, skip — do not
implement deferred work, do not churn the revision path" guidance, IN-03 is left as
the intentional stub. It will be replaced with measured values when the real
revision agent loop lands.

## Project-Invariant Compliance

All applied fixes respect the project invariants:
- **Kernel purity:** both edits are in `engine.py` / `authz.py` (not the
  stdlib-only `backend/agents/artifacts/` kernel package). `authz.py` keeps its
  `app.models.*` import inside the method (sanctioned pattern). No new imports
  added that would violate import-linter contracts.
- **Backward-compat (byte-identical + semantic-event-parity):** both guards are
  fail-loud checks that do NOT fire on any currently-passing/live path
  (live owner is always real; live revision-run owner always equals supplied
  owner). No observable behavior changed for prototype / od_* / PPT / code-gen /
  revision paths.
- **Default-deny scoping (AUTHZ-01/03):** IN-01 mirrors the existing AUTHZ-03
  fail-loud pattern; IN-02 hardens (never widens) the scoping seam. Nullability
  was not widened.
- **Additive-only migrations (Q3):** no migration files touched.
- **No dual implementations (INV-3/INV-12):** both fixes are in place.
- **deepagents runtime mandate (INV-13):** untouched; no agent loop edits.

## Test Results

Run with `python3.11` (no venv), tests under `backend/tests/`:

| Suite | Result |
|-------|--------|
| `tests/unit/test_revision_intelligence.py` (incl. new real-DB regression `test_revision_run_events_persist_and_resolve_on_real_db`) | **10 passed** |
| `tests/agents/test_parent_run_ownership.py` | **13 passed** |
| `tests/unit/test_run_events.py` + `test_runs_api_events.py` + `test_runs_api_artifacts.py` + `test_execution_engine.py` + `test_artifact_store.py` (combined batch) | **36 passed** |

**Total relevant: 59 passed, 0 failed.** The two suites that directly exercise the
edited code — `test_revision_intelligence.py` (`_handle_revision` + `set_run_scope`,
including the real-DB regression test) and `test_parent_run_ownership.py` (authz
scoping) — are both green, confirming no regression from the IN-01/IN-02 guards.

**Note on `test_phase5_revision_validation.py`:** this suite (build-loop revision
sandbox-seeding via scripted models) hangs in this environment on a wall-clock
block with near-zero CPU — a pre-existing test-infrastructure issue, NOT a
regression from this pass. It exercises the `execute()` build-loop revision path,
which does **not** call the edited `_handle_revision` event method or
`set_run_scope` (confirmed by source inspection: its `_execute_revision` helper
routes through `execute()`, and the suite contains no reference to `_handle_revision`
or `owner_id`). The edited code paths are fully covered by `test_revision_intelligence.py`.

---

_Fixed: 2026-06-08T14:10:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
