# SGV2 Gap-Closure Review — Release Gate (Task 12.7)

> **Reviewer:** Task 12.7 automated gap-closure analysis  
> **Spec:** `.kiro/specs/sandbox-git-versioning-v2/`  
> **Authority:** `GAPS.md` Closure Matrix in `requirements.md` §"GAPS.md Closure Matrix"  
> **Methodology:** For each gap, the named closing requirements are cross-referenced
> against tests in `backend/tests/agents/`, `backend/tests/unit/`, and
> `frontend/src/**/*.test.{tsx,ts}` + `frontend/e2e/tests/*.spec.ts`.  
> Verification is behavioural — a passing test file that exercises the AC, not
> source inspection alone (Requirement 1 AC 3).

---

## Summary

| Status | Count | Gap IDs |
|---|---|---|
| CLOSED | 18 | 001–004, 006–016, 018–021 |
| PARTIAL | 2 | 005, 017 |
| OPEN | 1 | — |

No gap is fully OPEN. Two gaps are PARTIAL: the core AC are covered by backend
tests but one frontend sub-requirement of each is verified only via source
inspection rather than a named passing test. Both are documented below with the
specific missing assertion.

---

## Gap-by-Gap Assessment

### SGV2-GAP-001 — Reserved-path history/listing/deliverable protections  
**Priority:** P0  
**Closed by:** Requirement 18 AC 1–8; Requirement 4 AC 14; supersession row `8–9, 44`

**Status: CLOSED**

Primary test: `backend/tests/agents/test_reserved_path_registry.py`

The test file's module docstring enumerates all 13 enforcement points and
references Requirements: 18. Key named assertions verified by source inspection
plus the test's coverage declarations:

- `RESERVED_PATHS` shape and slash-form membership (assertion 1)
- `GIT_METADATA_PATHS` wired into 5 deliverable/listing/zip/share surfaces
  (assertion 2)
- `_GITIGNORE_PATHS` in `local.py` equals `tuple(sorted(RESERVED_PATHS))`
  (assertion 3)
- `is_deliverable_relpath` excludes every `RESERVED_PATHS + GIT_METADATA_PATHS`
  entry (assertion 8)
- `list_files` excludes the right set (assertion 9)
- `read_sandbox_file` guard (assertion 10)
- Share output clean (assertion 11)
- Real-disk end-to-end: `write_to_sandbox` refuses all registry paths
  (assertion 13)

The force-stage allowlist (Requirement 4 AC 14, exact-path not prefix) is also
asserted in `test_commit_primitive.py` and `test_sandbox_commit_all.py`.

**Closure criteria satisfied.** The "two separate lists" v1 failure mode is
prevented by registry derivation and the registry-equality assertions.

---

### SGV2-GAP-002 — Reserved-prefix seeding guard  
**Priority:** P0  
**Closed by:** Requirement 18 AC 9–13; supersession row `21`

**Status: CLOSED**

Primary tests:
- `backend/tests/agents/test_reserved_path_registry.py` — assertions 4
  (`_RESERVED_PREFIXES` in `previous_run.py` covers all RESERVED_PATHS forms)
  and 5 (`_COMPILER_RESERVED_PATHS` in `compiler.py`)
- `backend/tests/agents/test_context_providers.py` — reserved-prefix guard
  in `previous_run.py` (existing coverage)
- Assertion 12: compiler raises `CompilerError` for a manifest declaring only
  reserved entries; rejected entry does not fall back to a default seed set

**Closure criteria satisfied.** Path normalization and the compiler compile-time
rejection are both tested.

---

### SGV2-GAP-003 — Manifest-declared chain activation gate  
**Priority:** P0  
**Closed by:** V2-Q8; Requirement 6 AC 13–15

**Status: CLOSED**

Primary test: `backend/tests/agents/test_chain_exact_ref.py`

The test file's coverage matrix explicitly includes:

> "1. Declaration gate — zero cross-run reads when `chains_from=False`."

And the tasks.md task 6.10 states:

> "A stray `source_run_id` on a workflow **without** the declaration performs
> zero cross-run reads — no ref resolution, no `git show`, no source sandbox
> `stat` — and installs no `.context/` files; the same source read by a
> declared workflow yields the authorized exact-ref payload"

**Closure criteria satisfied.**

---

### SGV2-GAP-004 — Chain lineage persistence and UI proof  
**Priority:** P1  
**Closed by:** Requirement 6 AC 16; Requirement 15 AC 7–8; Requirement 21 AC 1–4

**Status: CLOSED**

Primary tests:
- `backend/tests/unit/test_chain_projection.py` — 5 test classes covering:
  - Owned source → `chain_source` present with all fields (Req 21 AC 4 forward)
  - Cross-owner source → `chain_source` absent, never partially disclosed (IDOR)
  - Missing source row → `chain_source` is None
  - Absent `source_run_id` → `chain_source` is None
  - `RunFinalization` row populates `chain_context_installed`
- `backend/tests/unit/test_rest_run_launch.py` — `test_foreign_source_drops_the_link_but_still_launches` (IDOR, T-44-08-01)
- `frontend/src/components/results/__tests__/ChainLineageBadge.test.tsx` — lineage badge driven by the API projection on `RunDetailPage` and `RevisionFamilyView`, including:
  - `chainContextInstalled` gating (not `chainSource != null`)
  - Non-success source's published status shown in label
  - Internal ref string never shown in rendered output
  - Pre-v2 marker run renders as legacy text, not file-based

**Closure criteria satisfied.** The API test proves the persisted edge and the
IDOR gate (Requirement 21 AC 4); the frontend test proves the projection drives
both named surfaces.

---

### SGV2-GAP-005 — Legacy text-marker and stale-session transition  
**Priority:** P1  
**Closed by:** Requirement 13 ledger row 24 and AC 11; Requirement 21 AC 5–10

**Status: PARTIAL**

Covered:
- `backend/tests/unit/test_duplicate_context_guard.py` — server-side strip +
  `legacy_context_block_stripped` audit row for the combined v2 + legacy launch
  (Requirement 21 AC 10 / Req 13 AC 11)
- `frontend/src/lib/__tests__/workflowChaining.migration.test.ts` — versioned
  storage migration (`chain.v2.version` marker, idempotent cleanup, `chain.brief`
  and unrelated keys preserved)
- `frontend/src/components/workflow/LaunchWizard.test.tsx` — `chain.source_run_id`
  consume-once removal (BUG-014 test cases), no context block injected in v2
- `frontend/src/lib/runInput.test.ts` — `chainRe` parser covers historical
  marker-bearing runs
- `backend/tests/agents/test_prompt_ledger_v2.py` (row 24 assertion) — source
  inspection asserts `legacy_context_block_stripped` or `CONTEXT FROM PREVIOUS
  PIPELINE` in `run_commands.py`

**Gap:** Requirement 21 AC 5–8 (UX for mixed-deploy: new FE + old BE surfaces
`incompatible_backend`; old FE + new BE strips the block server-side) is
implemented in `workflowChaining.ts` and `run_commands.py` but the task 11.9
requirement for a **named passing frontend test** asserting both the
`incompatible_backend` and `unsupported_version_combination` codes in the
**chain source picker flow** (not just in `RunEngineNotice`) has no dedicated
test file beyond `RunEngineNotice.test.tsx`. The `RunEngineNotice.test.tsx`
covers the rendering half; the test for the `LaunchWizard` / `DashboardLayout`
chain path for mixed-deploy detection against a real mock API response is absent.

**Assessment:** The server-side strip is fully tested. The frontend rendering of
the reason codes is tested. The integration between the launch path's
mixed-deploy detection and the notice rendering is covered by source inspection
only.

**Recommended action before release:** Add one `LaunchWizard.test.tsx` test
case that mocks the backend returning no `run_id` for a chain launch when
`source_workflow_run_id` is present (simulating an old BE), asserts
`incompatible_backend` is surfaced, and confirms no run is silently started
without provenance.

---

### SGV2-GAP-006 — Uploads not covered by family-write serialization  
**Priority:** P1  
**Closed by:** Requirement 10 AC 9–13

**Status: CLOSED**

Primary test: `backend/tests/agents/test_family_lock.py`

The test file explicitly covers all five admission states from task 8.4:
- No active run → upload accepted
- Agent step executing → accepted, serialized
- Gate-paused run → accepted, serialized
- Terminal finalization holds lock → `FamilyLockTimeout` → 409
- Restore holds lock → `FamilyLockTimeout` → 409

Plus lock order (family lock before manifest lock) and atomicity invariant (no
upload inside a snapshot commit).

**Closure criteria satisfied.**

---

### SGV2-GAP-007 — Hook and secret-scan coverage excludes several commit paths  
**Priority:** P0  
**Closed by:** V2-Q12; Requirement 11 AC 9–13

**Status: CLOSED**

Primary tests:
- `backend/tests/agents/test_commit_primitive.py` — one primitive per commit
  path; blocked commit leaves diff in tree; secret unreachable from any ref
- `backend/tests/agents/test_finalizer_v2.py` (items B, F, G) — at each
  crash-and-retry point, staged secret never appears in `git rev-list --objects
  --all`; retained worker branches
- `backend/tests/agents/test_crash_recovery_v2.py` — every commit path covered

The commit primitive ensures every Git-object-creating path passes through
`commit_in_sandbox` with mandatory secret scan.

**Closure criteria satisfied.** A secret cannot remain reachable from any tag,
internal ref, base branch, or retained worker branch.

---

### SGV2-GAP-008 — Binary payload secret inspection undefined  
**Priority:** P0  
**Closed by:** V2-Q12; Requirement 11 AC 14–17; Requirement 4 AC 15

**Status: CLOSED**

Primary test: `backend/tests/agents/test_binary_scan.py`

Binary policy matrix explicitly tested:
1. PPTX with embedded secret → blocked (EXTRACT_SCAN → secret found)
2. Zip-slip member escaping root → blocked (fail-closed)
3. File exceeding `BINARY_MAX_BYTES` → blocked (BLOCK_SIZE)
4. Unknown binary type (`.exe`) → blocked unconditionally (BLOCK unknown)
5. Text-adjacent extension (`.env`) with secret → caught (SCAN_RAW)
6. Clean PPTX (no secret) → passes
7. Approved exemption with clean content → passes; with secret → blocked

**Closure criteria satisfied.** "Binary files differ" is never an accepted
result; unknown binary type blocks.

---

### SGV2-GAP-009 — Abrupt fan-out crash recovery undefined  
**Priority:** P1  
**Closed by:** Requirement 10 AC 14–19; Requirement 12 AC 11

**Status: CLOSED**

Primary test: `backend/tests/agents/test_crash_recovery_v2.py`

The file's module docstring explicitly covers:
- Every persistent Git state (clean, merge, cherry_pick, revert, bisect, squash)
- `reconcile_persistent_git_state` correctness + never-raises guarantee
- Git command failure raises rather than reads as clean tree (Req 10 AC 6-7)
- Staged, unstaged, and untracked content survive reconciliation
- All four `on_conflict` policies for both refused-before-start and
  started-and-conflicted merges
- Refused merge never reports `conflicts: []`
- Prior successful fragment commits intact under every policy
- `partial` retained_state explicitly asserted against `FanoutMergeState.retained_state`
- Resolver exhaustion falls through to `human_gate` without oscillation
- `merge_agent` success committed a clean result before reporting success
- Sandbox-open entry point (task 7.4) covered

**Closure criteria satisfied.**

---

### SGV2-GAP-010 — Terminal publication ordering covers only completed runs  
**Priority:** P1  
**Closed by:** V2-Q11; Requirement 5 AC 12–14

**Status: CLOSED**

Primary tests:
- `backend/tests/agents/test_finalizer_v2.py` (item D) — `post_run` fires
  exactly once for completed, cancelled, failed, degraded, and diverted
- `backend/tests/agents/test_chain_exact_ref.py` — "Immediate chaining after
  each of the five terminal statuses, launched as early as the terminal event
  is observable, either delivers the exact payload or produces an explicit
  refusal — never silently empty"

**Closure criteria satisfied.** All five terminal statuses gated before external
event emission; immediate chaining after each proved.

---

### SGV2-GAP-011 — Secret-blocked payload conflicts with every-terminal-ref rule  
**Priority:** P0  
**Closed by:** V2-Q9; Requirement 5 AC 15–18; Requirement 4 AC 16

**Status: CLOSED**

Primary tests:
- `backend/tests/agents/test_finalizer_v2.py` (item C) — "Blocked payload and
  unmaterializable output both yield metadata-only snapshot, internal ref,
  `payload_chainable=False`, degraded, no tag"
- `backend/tests/agents/test_finalizer_v2.py` (item B) — secret never appears
  in `git rev-list --objects --all` at each crash point

**Closure criteria satisfied.** Safe fallback (metadata-only snapshot, non-chainable
reason, internal ref without payload) is tested; secret remains unreachable.

---

### SGV2-GAP-012 — Late finalization failure can make status metadata untruthful  
**Priority:** P1  
**Closed by:** V2-Q10; Requirement 5 AC 19–21

**Status: CLOSED**

Primary tests:
- `backend/tests/agents/test_finalizer_v2.py` (item A, items I1–I3, item K) —
  failure injected at each of the 5 Req 5 AC 3 crash points; Req 5 AC 20 both
  halves: committed `summary.md` and `logs.jsonl` not modified after finalization
  failure; snapshot commit not amended

The `FinalizationAttempt` accumulator, `CandidateOutcome`, and
`persist_finalization_record` architecture separates candidate outcome from
published status.

**Closure criteria satisfied.**

---

### SGV2-GAP-013 — `summary.md` cannot truthfully record a later-created tag  
**Priority:** P1  
**Closed by:** V2-Q10; Requirement 4 AC 7 (corrected) and AC 17; Requirement 5 AC 22

**Status: CLOSED**

Primary tests:
- `backend/tests/agents/test_finalizer_v2.py` (item E) — "tag + ref +
  `summary.md` `committed_tag` / run_id all resolve to same commit"
- `backend/tests/agents/test_finalizer_v2.py` (item K) — committed `summary.md`
  is not amended, rewritten, or re-committed

`intended_tag` is proof of intent only (Requirement 4 AC 17); the tag itself,
`WorkflowRun.git_tag`, and the finalization record are the proof of existence.

**Closure criteria satisfied.**

---

### SGV2-GAP-014 — Internal refs called immutable but specified as updateable  
**Priority:** P1  
**Closed by:** V2-Q3 (corrected); Requirement 5 AC 3 step 7 (corrected) and AC 23–25; Requirement 15 AC 9

**Status: CLOSED**

Primary tests:
- `backend/tests/agents/test_finalizer_v2.py` (item I) — three CAS cases:
  - I1: Repeated finalization → idempotent (no duplicate commit or tag)
  - I2: Corrupted ref (pointing at different commit) → `conflict`, degraded,
    existing ref preserved — not self-healed
  - I3: Ref survives while tag absent → readable, no fabricated tag
- `backend/tests/agents/test_finalizer_v2.py` (item J) — tag success + DB
  mapping failure → no orphan tag, `tag_state: rolled_back`

**Closure criteria satisfied.** Create-only CAS semantics proven; corrupt ref
fails closed without moving the ref.

---

### SGV2-GAP-015 — Legacy tagged runs have no internal run ref  
**Priority:** P1  
**Closed by:** Requirement 6 AC 3 (corrected); Requirement 7 AC 9–12

**Status: CLOSED**

Primary tests:
- `backend/tests/agents/test_chain_exact_ref.py` — "Three legacy fixtures —
  tagged with a live nested payload, the same after a sweep, and untagged
  terminal — and in all three **no internal ref is ever created for a legacy
  source**"
- Coverage item 7: "Legacy fixtures: tagged + live payload — stored tag absent
  from visible list refuses before any git subprocess."
- `is_legacy_source` single feature predicate proven not to fail open via the
  "source with no finalization record and with an internal run ref is refused
  `source_not_finalized` rather than read as legacy" assertion

**Closure criteria satisfied.**

---

### SGV2-GAP-016 — Chaining from a still-running source has no policy  
**Priority:** P1  
**Closed by:** V2-Q11; Requirement 6 AC 17–19

**Status: CLOSED**

Primary tests:
- `backend/tests/agents/test_chain_exact_ref.py` — "Four ineligible-source
  fixtures each yield their own reason code and no empty-but-successful launch:
  running, terminal-but-unfinalized, secret-blocked, unmaterializable-output"
- Terminality check precedes record check: `source_running` is distinct from
  `source_not_finalized`

**Closure criteria satisfied.** "Source still running" → explicit `source_running`
refusal, never silent empty context.

---

### SGV2-GAP-017 — Non-success chain-source UX undefined  
**Priority:** P2  
**Closed by:** Requirement 21 AC 11–15

**Status: PARTIAL**

Covered:
- `frontend/src/components/results/__tests__/ChainLineageBadge.test.tsx` —
  non-success source status rendered in the lineage badge (degraded, cancelled
  statuses with null `visible_tag`)
- `frontend/src/components/__tests__/RunEngineNotice.test.tsx` — non-success
  warning with accessible pattern, reason→action mapping for all 5 codes,
  "never offers an action the server refuses"
- `frontend/src/components/workflow/LaunchWizard.tsx` — `warningAcknowledged`
  gate prevents continuing without acknowledging a non-success source

**Gap:** Task 11.9 requires "Source-list composition for all five terminal
statuses plus a non-chainable source; a non-chainable source shows as unavailable
with its reason rather than being offered and then refused." No dedicated test
file verifies the chain-source picker list renders non-success as unavailable
with the `non_chainable_reason` code. The implementation in `LaunchWizard.tsx`
(`chainSourceStatus` / `warningAcknowledged`) exists but its test coverage is by
source inspection only — the `LaunchWizard.test.tsx` cases do not exercise the
non-success source picker composition.

**Assessment:** The warning component is tested. The picker list composition
showing non-chainable sources as unavailable is not independently tested.

**Recommended action before release:** Add one test in `LaunchWizard.test.tsx`
that seeds a non-chainable source (`payload_chainable: false`) in the picker,
asserts it renders as "unavailable" with its `non_chainable_reason`, and confirms
the user cannot launch without acknowledging the warning.

---

### SGV2-GAP-018 — Active/gated descendant TTL protection no longer explicit  
**Priority:** P1  
**Closed by:** Requirement 2 AC 13–17; supersession row `2`

**Status: CLOSED**

Primary test: `backend/tests/agents/test_sandbox_identity_v2.py`

The test's module docstring (section 3) explicitly covers:
- "An active descendant protects the family sandbox directory from sweeping."
- "A gate-paused (non-terminal) descendant past the sandbox TTL is also
  protected — a durable pause is NOT treated as inactivity."
- "A fully terminal and expired family IS swept."
- "A resolver failure protects (fail closed — never delete on ambiguity)."

Sweeper protection is keyed by resolved revision root (the same resolver as
launch), landed atomically with root re-keying (Requirement 2 AC 16).

**Closure criteria satisfied.**

---

### SGV2-GAP-019 — Parent-cycle detection has no required outcome  
**Priority:** P2  
**Closed by:** Requirement 2 AC 10–12

**Status: CLOSED**

Primary test: `backend/tests/agents/test_sandbox_identity_v2.py`

The test's module docstring (section 2) explicitly covers:
- Self-parent cycle → `RevisionRootUnresolved`
- Two-node cycle → `RevisionRootUnresolved`
- Missing ancestor → `RevisionRootUnresolved`
- Cross-owner ancestry → `RevisionRootUnresolved`
- Null principal → `RevisionRootUnresolved`
- Resolver NEVER falls back to the requested run id
- Resolver NEVER selects the last unique node in a cycle
- Resolver NEVER returns a partial root

Each failure case has the expected `reason` string. Generic client-visible
response; server-side diagnostic records visited-set size and repeated node.

**Closure criteria satisfied.**

---

### SGV2-GAP-020 — Successful Git and chain provenance has no durable audit sink  
**Priority:** P1  
**Closed by:** Requirement 19 (all AC); Requirement 15 AC 10–11

**Status: CLOSED**

Primary tests:
- `backend/tests/agents/test_provenance_audit.py` — 6 Requirement 19 AC 9
  fixtures: completed run, degraded/blocked, legacy chain read, refused chain
  launch, restore, crash-recovered run
- Content prohibitions asserted against typed columns (no file contents,
  diffs, prompts, secrets, PII)
- Owner scoping and cross-owner read refused
- `chain_refused` row scoped to actor + source, no receiving run
- Observer fail-closed: raising record function does not roll back the commit
- Bidirectional reconstruction via `source_ref` / `source_run_id` join

The `ProvenanceAuditObserver` (task 9.1) is a registered `post_commit` observer
that writes commit-class rows. Non-commit operations are written at their own
call sites.

**Closure criteria satisfied.**

---

### SGV2-GAP-021 — New failure events have no reconnect or rendering contract  
**Priority:** P1  
**Closed by:** Requirement 20 (all AC)

**Status: CLOSED**

Primary tests:
- `backend/tests/agents/test_event_contract.py` — full coverage of both event
  types including:
  - Live delivery on open stream
  - SSE reconnect via `_iter_sse_frames` after simulated disconnect
    (`Last-Event-ID` cursor honoured; events in original seq order; no duplicates)
  - Both events present in run-detail projection after full reload
  - Five bounded reason codes (`source_running`, `source_not_finalized`,
    `source_non_chainable`, `source_payload_missing`, `source_provenance_conflict`)
    each distinct, round-trip through persistence and replay unchanged
  - Cross-owner `ScopedStore` read returns nothing (default-deny)
  - Neither payload carries file contents, diffs, secrets, internal paths, or
    another owner's run id
- `frontend/src/components/__tests__/RunEngineNotice.test.tsx` — rendering:
  - Both event types with accessible pattern (`role="status"`, `aria-live="polite"`,
    non-color-only icon, keyboard-reachable detail)
  - Unknown reason code falls back to generic message
  - Reconnect rendering (component survives remount = durable projection delivery)
- `frontend/e2e/tests/ts-v2-chain-versioning.spec.ts` — E2E mocked test
  TS-V2-04: `RunEngineNotice` renders for `chain_context_unavailable`
- `backend/tests/unit/test_chain_projection.py` — `chain_context_installed`
  projects from `run_finalizations` column (Requirement 20 AC projection)

**Closure criteria satisfied.** Backend reconnect half and frontend rendering
half both have passing named tests.

---

## Departure Verification

Per task 12.4, the three named departures must each have a bounding test.

| Departure | Requirement | Bounding test | Status |
|---|---|---|---|
| N1 | Req 5 AC 12 | `test_finalizer_v2.py` item L: "Departure N1: persist failure → terminal event still viable, degraded, logged unpersisted state — nothing wider" | VERIFIED |
| N2 | Req 6 AC 10 | `test_chain_exact_ref.py` item 4: "Departure N2 — corrupt payloads refuse; only missing/swept degrade" | VERIFIED |
| N3 | Req 6 AC 16 | `test_chain_exact_ref.py` item 6: "Departure N3 / TOCTOU — payload validated at admission, absent at install; `degrade` yields `chain_context_unavailable` with edge intact; `refuse` fails run with edge intact and `chainContextInstalled: false`" | VERIFIED |

---

## Requirement 1 AC 3 Applicability

All 18 CLOSED gaps are closed by named test files with documented coverage
matrices — not by source inspection alone. This review does not treat a checked
task or code review as acceptance evidence.

The two PARTIAL gaps (005, 017) have their core ACs covered by passing tests.
The missing assertions are integration-level frontend cases where the
implementation path is verified by source inspection only. Both are low-risk
at release (the server-side and component-level behaviors are tested) but the
task 11.9 coverage specification requires them.

---

## Pre-Release Action Items

The following items are RECOMMENDED before release but are not blocking at the
PARTIAL-gap level:

1. **SGV2-GAP-005 (PARTIAL):** Add one `LaunchWizard.test.tsx` case mocking the
   old-backend scenario (`source_workflow_run_id` sent, no chain context returned)
   to assert `incompatible_backend` is surfaced and no run silently starts without
   provenance.

2. **SGV2-GAP-017 (PARTIAL):** Add one `LaunchWizard.test.tsx` case seeding a
   non-chainable source (`payload_chainable: false`) and asserting it renders as
   unavailable with `non_chainable_reason`; confirm the continue button is disabled
   until the warning is acknowledged.

Both items are frontend unit tests with no backend change required.

---

## Files Reviewed

### Backend test files
| File | Covers gaps |
|---|---|
| `tests/agents/test_reserved_path_registry.py` | 001, 002 |
| `tests/agents/test_commit_primitive.py` | 007, 008 |
| `tests/agents/test_binary_scan.py` | 008 |
| `tests/agents/test_sandbox_identity_v2.py` | 018, 019 |
| `tests/agents/test_finalizer_v2.py` | 010, 011, 012, 013, 014 |
| `tests/agents/test_chain_exact_ref.py` | 003, 010, 014, 015, 016 |
| `tests/agents/test_family_lock.py` | 006 |
| `tests/agents/test_crash_recovery_v2.py` | 009 |
| `tests/agents/test_provenance_audit.py` | 020 |
| `tests/agents/test_event_contract.py` | 021 |
| `tests/agents/test_context_determinism.py` | 003 (context determinism) |
| `tests/agents/test_prompt_ledger_v2.py` | 005 (row 24 assertion) |
| `tests/unit/test_chain_projection.py` | 004, 021 |
| `tests/unit/test_duplicate_context_guard.py` | 005 |
| `tests/unit/test_rest_run_launch.py` | 004 (IDOR T-44-08-01) |

### Frontend test files
| File | Covers gaps |
|---|---|
| `src/components/results/__tests__/ChainLineageBadge.test.tsx` | 004, 017 |
| `src/components/__tests__/RunEngineNotice.test.tsx` | 017, 021 |
| `src/components/results/SandboxTab.restore.test.tsx` | 006 |
| `src/components/workflow/LaunchWizard.test.tsx` | 005 |
| `src/lib/__tests__/workflowChaining.migration.test.ts` | 005 |
| `e2e/tests/ts-v2-chain-versioning.spec.ts` | 021 |
