# Requirements Document

## Introduction

`sandbox-git-versioning-v2` is a corrective, implementation-aware delta to
`.kiro/specs/sandbox-git-versioning`. The v1 checklist is fully checked, but the
current working implementation does not satisfy several v1 contracts: revision
sandboxes are resolved through `source_run_id` instead of `parent_run_id`,
revision logs use the physical sandbox-root id rather than the logical run id,
terminal finalization happens before the final status and deliverable are known,
`.chain/` is ignored and nested, chaining reads the live tree as UTF-8 text, the
restore action is not implemented, and prompt migration is incomplete.

This document is authoritative wherever it conflicts with v1. A v1 requirement
marked **Retain** remains binding. **Amend** means v1 remains binding with the
additional or corrected conditions here. **Replace** means this document is the
sole authority for that behavior. No checked v1 task is evidence that its
acceptance criteria pass; v2 acceptance is based on executable behavior and
validation results.

The principal v2 change is a flat, Git-versioned chain payload:

```text
.chain/
  logs.jsonl
  summary.md
  {workflow_output_filename}
```

There are no run-id subdirectories and no copied agent transcripts. For a given
revision family, `v1`, `v2`, and later tags contain the same three `.chain/`
paths; the bytes differ by version. A chained workflow reads the exact immutable
ref belonging to the selected source run, never the latest working tree, and
copies those three files as bytes into its own `.context/` directory.

This revision additionally folds in the 21 coverage gaps recorded in the
`GAPS.md` handoff (`SGV2-GAP-001` … `SGV2-GAP-021`). Nothing previously binding
was weakened: every gap is closed by extending an existing requirement in its
own domain, or — where the gap names a domain this document did not previously
cover at all — by one of the four additive Requirements 18–21. Requirements 1–17
keep their numbers and their original acceptance-criteria numbering so that
existing references such as "Requirement 5 AC 3" and "Requirement 4 AC 10–13"
remain valid; newly required behavior is appended, and the four pre-existing
criteria that were internally contradictory (Requirement 4 AC 7, Requirement 5
AC 3 steps 7–8, Requirement 6 AC 3) are corrected in place without dropping any
guarantee. The **GAPS.md Closure Matrix** below is the authoritative map from
each gap id to the acceptance criteria that close it.

## Locked v2 Decisions

- **V2-Q1 — Two lineage graphs:** `parent_run_id` defines revision-family
  sandbox identity. `source_run_id` is a read-only workflow-chaining edge and
  never changes physical sandbox identity.
- **V2-Q2 — Flat tracked payload:** exactly three engine-owned files under
  `.chain/` are committed into Git history. Legacy nested payloads are retained
  outside `.chain/` for compatibility but are hidden and ignored.
- **V2-Q3 — Exact source version:** every terminal run gets an internal Git ref
  that is immutable by policy, created under create-only compare-and-set
  semantics: absent means create, present-and-identical means success, and
  present-and-different means fail closed without moving the ref. Completed runs
  additionally get the user-visible `vN` tag. Chaining reads the source run's
  exact ref, never `HEAD`, the latest tag, or another revision's payload.
- **V2-Q4 — Complete current-run log:** the source log is exactly
  `.logs/{current_run_id}.jsonl`, after the run trace has flushed. Physical
  sandbox-root identity and logical run identity are separate values.
- **V2-Q5 — Required finalization:** terminal status and output are resolved
  before payload creation. Payload commit, immutable ref, completed tag, and DB
  mapping are idempotent required operations, not an optimistic pre-terminal
  best-effort callback.
- **V2-Q6 — Compatibility without history rewriting:** v1 tags and commits are
  never rewritten. Legacy `.chain/{run_id}/` data is relocated to an ignored
  compatibility namespace and used only as an explicit fallback.
- **V2-Q7 — One canonical reserved-path registry:** a single engine-owned
  registry names every reserved path, and every enforcement point (Git ignore,
  Git staging, deliverable walk, `list_files`, zip, public share, agent tools,
  seed/context providers) derives its exclusions from that one registry. The
  three validated flat `.chain/` files are the only force-tracked exception, and
  the exception is expressed as an exact-path allowlist, never as a prefix.
  *(Closes SGV2-GAP-001 and SGV2-GAP-002.)*
- **V2-Q8 — Chain context is manifest-declared:** the chain-context provider
  activates only when the compiled workflow declares a chain capability. The
  presence of `source_run_id` alone SHALL never trigger a cross-run read.
  *(Closes SGV2-GAP-003.)*
- **V2-Q9 — A security-blocked payload yields a metadata-only,
  non-chainable snapshot:** when the secret scan blocks the chain payload, the
  terminal snapshot is created from redacted metadata only — no `logs.jsonl`, no
  output bytes, no blocked content, and no visible `vN` tag. That snapshot still
  receives an internal run ref so that finalization stays idempotent, and the
  run is recorded `degraded` with a durable non-chainable reason. Chaining from a
  non-chainable snapshot is refused at launch, not degraded to empty context.
  This resolves the V2-Q3/V2-Q5 conflict that a blocked payload previously
  created. *(Closes SGV2-GAP-011.)*
- **V2-Q10 — Candidate outcome versus published status:** the flat payload
  records the *candidate* terminal outcome and an `intended_tag`, both immutable
  once committed. The *published* status is the durable database status after
  finalization converges. A later finalization failure changes the published
  status and the durable finalization record; it never rewrites, re-commits, or
  re-tags an already-created snapshot to repair text. *(Closes SGV2-GAP-012 and
  SGV2-GAP-013.)*
- **V2-Q11 — Chain sources must be terminal and finalized:** a source run is
  eligible only once its durable finalization record reports a completed
  required sequence. Every externally visible terminal event — not just
  `completed` — follows that record. "Source still running" and "source not yet
  finalized" are explicit refusals, never silent empty context. *(Closes
  SGV2-GAP-010 and SGV2-GAP-016.)*
- **V2-Q12 — Every Git object-creating path is security-gated:** one commit
  primitive owns staging, `pre_commit`, mandatory secret scanning, commit, and
  `post_commit` for step, spawn, worker, fragment-merge, merge-agent, recovery,
  restore, and terminal payload commits. Binary payloads are scanned by content,
  not by textual diff. *(Closes SGV2-GAP-007 and SGV2-GAP-008.)*

## Glossary

- **revision root**: the first run reached by walking `parent_run_id`; all
  revisions in that family share its physical sandbox.
- **chain source**: the run named by `source_run_id`; it belongs to a separate
  revision family and supplies immutable input to a new workflow.
- **physical sandbox id**: the revision-root id used in the on-disk path.
- **logical run id**: the currently executing `WorkflowRun.id`; used for logs,
  evidence, events, refs, summaries, and persistence.
- **terminal snapshot commit**: the final commit for one terminal run, containing
  the flat `.chain/` payload and any required terminal reconciliation.
- **internal run ref**: trusted, non-user-supplied Git ref
  `refs/ideaflow/runs/{run_id}` pointing to that run's terminal snapshot.
- **visible version tag**: `v{revision_index}`, created only for a completed run.
- **legacy payload**: the v1 live-tree layout `.chain/{run_id}/...`, which was
  ignored by Git and therefore is absent from old tags.
- **payload allowlist**: `.chain/logs.jsonl`, `.chain/summary.md`, and exactly one
  safe workflow output basename.
- **reserved-path registry**: the single engine-owned set of reserved sandbox
  paths. Today's implementation set is `.uploads/`, `.logs/`, `.verify/`,
  `.browser/`, `.agents/`, `.chain/`, `.context/`, `skills/`, and
  `conversation_history/`; v2 adds `.chain-legacy/`. `.git/` and `.gitignore` are
  reserved for listing, deliverable, zip, and share purposes.
- **force-tracked exception**: the exact three payload-allowlist paths, the only
  reserved paths the engine may stage into Git.
- **declared chain capability**: the compiled manifest declaration that a
  workflow accepts chain context; the activation gate for the chain provider.
- **candidate outcome**: the terminal status and deliverable resolved before
  payload creation and recorded immutably inside the snapshot.
- **published status**: the durable `WorkflowRun` status after finalization
  converges; the single value the product surfaces to the user.
- **metadata-only terminal snapshot**: a terminal snapshot that carries the
  engine-rendered `summary.md` and no `logs.jsonl` or output bytes, used when the
  payload is security-blocked or unmaterializable. It is non-chainable.
- **intended tag**: the deterministic `v{revision_index}` name recorded in
  `summary.md` before the tag exists; proof of intent, never proof of creation.
- **finalization record**: the durable, owner-scoped record of the terminal
  finalization sequence — candidate outcome, snapshot commit, internal ref, tag
  state, published status, chainability, and failure reason.
- **legacy tagged source**: a pre-v2 run holding a visible `git_tag` but no
  internal run ref.
- **protected revision family**: a revision family with at least one non-terminal
  member, including a run durably paused at a human gate; its physical sandbox is
  exempt from TTL sweeping.

## V1 Supersession Matrix

A **Replace** disposition retires only the v1 *mechanism*, never a v1 safety
property. Where the audit found that a Replace row had silently dropped a v1
protection, the row below now names the v2 requirement that restates it.

| V1 requirement(s) | Disposition | V2 authority |
|---|---|---|
| 1, 3–5, 43 | Replace | Requirements 2, 3, 6, 10 |
| 2 | Replace with restated protection | Requirement 2 AC 13–17 (TTL protected set) |
| 6 | Retain | Initial Git commit remains required |
| 7 | Amend | Requirement 12 |
| 8–9, 44 | Replace with retained exclusions | Requirement 18 (reserved-path registry), Requirements 4 and 17 |
| 20 | Replace | Requirements 4, 5, 7 |
| 21 | Replace with restated guard | Requirement 18 AC 9–13 (reserved-prefix seeding guard) |
| 10–12, 41–42 | Amend | Requirements 5 and 11 |
| 13–14 | Replace | Requirement 5 |
| 15–17 | Retain with clarification | Requirement 9 |
| 18–19 | Replace | Requirement 9 |
| 22 | Replace | Requirements 6, 7, 18, 21 |
| 23 | Amend | Requirement 8 |
| 24 | Replace | Requirement 3 |
| 25, 28 | Amend | Requirements 11 and 12 |
| 26–27 | Amend | Requirements 5 and 10 |
| 29–31, 36, 40 | Replace | Requirements 13 and 14 |
| 32 | Amend | Requirements 5 and 15 |
| 33–34 | Retain | Stale-output declaration and name-free kernel remain binding |
| 35 | Amend | Requirements 4 and 17 |
| 37–39 | Retain | Existing deferrals remain binding |
| 45 | Retain and strengthen | Requirements 13 and 17 |
| 46 | Replace | Requirement 17 |

## GAPS.md Closure Matrix

Every gap recorded in `GAPS.md` closes against the acceptance criteria below. A
gap is closed only when its listed criteria are unambiguous and name their
intended verification; the matrix is the review checklist for that.

| Gap | Priority | Closed by | Class / domain |
|---|---:|---|---|
| SGV2-GAP-001 | P0 | Requirement 18 AC 1–8; Requirement 4 AC 14; supersession row `8–9, 44` | New domain — reserved-path registry and enforcement points |
| SGV2-GAP-002 | P0 | Requirement 18 AC 9–13; supersession row `21` | Same domain as GAP-001 — reserved prefixes |
| SGV2-GAP-003 | P0 | V2-Q8; Requirement 6 AC 13–15 | Existing — chaining activation |
| SGV2-GAP-004 | P1 | Requirement 6 AC 16; Requirement 15 AC 7–8; Requirement 21 AC 1–4 | Split — persistence (existing) plus product surface (new) |
| SGV2-GAP-005 | P1 | Requirement 13 ledger row 24 and AC 11; Requirement 21 AC 5–10 | Same class — ledger row 24 plus frontend transition |
| SGV2-GAP-006 | P1 | Requirement 10 AC 9–13 | Existing — family locking |
| SGV2-GAP-007 | P0 | V2-Q12; Requirement 11 AC 9–13 | Existing — hooks and commit gating |
| SGV2-GAP-008 | P0 | V2-Q12; Requirement 11 AC 14–17; Requirement 4 AC 15 | Existing — secret scanning |
| SGV2-GAP-009 | P1 | Requirement 10 AC 14–19; Requirement 12 AC 11 | Existing — recovery plus fan-out |
| SGV2-GAP-010 | P1 | V2-Q11; Requirement 5 AC 12–14 | Existing — finalization ordering |
| SGV2-GAP-011 | P0 | V2-Q9; Requirement 5 AC 15–18; Requirement 4 AC 16 | Existing — finalizer and security |
| SGV2-GAP-012 | P1 | V2-Q10; Requirement 5 AC 19–21 | Existing — finalizer state machine |
| SGV2-GAP-013 | P1 | V2-Q10; Requirement 4 AC 7 (corrected) and AC 17; Requirement 5 AC 22 | Existing — payload schema |
| SGV2-GAP-014 | P1 | V2-Q3 (corrected); Requirement 5 AC 3 step 7 (corrected) and AC 23–25; Requirement 15 AC 9 | Existing — Git refs |
| SGV2-GAP-015 | P1 | Requirement 6 AC 3 (corrected); Requirement 7 AC 9–12 | Existing — legacy compatibility |
| SGV2-GAP-016 | P1 | V2-Q11; Requirement 6 AC 17–19 | Existing — source eligibility |
| SGV2-GAP-017 | P2 | Requirement 21 AC 11–15 | New domain — chain-source product surface |
| SGV2-GAP-018 | P1 | Requirement 2 AC 13–17; supersession row `2` | Existing — resolver and sweeper |
| SGV2-GAP-019 | P2 | Requirement 2 AC 10–12 | Existing — resolver failure outcome |
| SGV2-GAP-020 | P1 | Requirement 19 (all AC); Requirement 15 AC 10–11 | New domain — durable provenance audit |
| SGV2-GAP-021 | P1 | Requirement 20 (all AC) | New domain — event persistence, replay, rendering |

---

## Requirements

### Requirement 1: Corrective precedence and implementation baseline

**User Story:** As a maintainer, I want the v2 contract to state exactly what it
supersedes, so that checked v1 tasks cannot hide incomplete or contradictory
behavior.

#### Acceptance Criteria

1. WHEN v1 and v2 conflict, THE implementation and review SHALL follow v2.
2. Every v1 requirement marked Retain SHALL remain mandatory.
3. A v1 checkbox SHALL NOT be used as verification evidence without a passing
   behavioral test or direct runtime observation.
4. The implementation SHALL correct the current source-based sandbox walk,
   nested live-only payload, root-id log path, early finalizer, missing restore,
   and incomplete prompt migration identified in this introduction.
5. The v2 design's component map SHALL be normative; a required change outside
   it SHALL update the map before code is changed.

---

### Requirement 2: Revision identity and workflow-chain identity are separate

**User Story:** As a developer, I want revision ancestry and workflow chaining to
be distinct graphs, so that a chained workflow never shares the source
workflow's mutable sandbox while revisions still share their own family root.

#### Acceptance Criteria

1. THE canonical revision-root resolver SHALL walk `parent_run_id` only.
2. `source_run_id` SHALL never be followed when choosing a physical sandbox.
3. A chained workflow SHALL start a new physical sandbox even when
   `source_run_id` is populated.
4. The resolver SHALL be owner-scoped by non-null `WorkflowRun.user_id`, use a
   visited-set cycle guard, and fail closed on cross-owner ancestry.
5. A missing ancestor row or database failure SHALL produce an explicit
   resolution failure for shared-environment API launches; it SHALL NOT silently
   merge an unknown run into the current directory.
6. Offline characterization harnesses MAY default the explicitly absent
   `sandbox_root_id` to the logical run id without querying the application DB.
7. One app-side resolver SHALL supply the root id to engine launch, resume,
   factory, `RunTrace`, all four file routes, sweeper protection, previous-run
   reads, restore, and family locks.
8. The duplicate current implementations that walk `source_run_id` in
   `engine.py` and `run_files.py` SHALL be removed or replaced.
9. Depth-two revisions and a chain from a depth-two revision SHALL be covered by
   tests proving that the revision shares its family root while the chained run
   receives a different root.

##### Cycle and ancestry-failure outcome *(closes SGV2-GAP-019)*

10. A detected `parent_run_id` cycle SHALL produce exactly one outcome across
    every caller: a typed fail-closed `revision_root_unresolved` resolution
    failure. The resolver SHALL NOT select the last unique node, SHALL NOT fall
    back to the requested run id, and SHALL NOT return a partial root. This
    supersedes v1 Requirement 1 AC 4.
11. `revision_root_unresolved` SHALL be the single outcome for a cycle, a missing
    ancestor row, cross-owner ancestry, and a database failure during the walk —
    the cases AC 5 already requires to fail explicitly. Callers SHALL NOT each
    choose their own fallback. Launch, revision admission, all four file routes,
    restore, previous-run reads, and family locking SHALL all refuse the
    operation; the TTL sweeper SHALL treat it as protected rather than deletable.
    AC 6 remains binding and is not a resolution failure: an offline harness with
    an explicitly absent `sandbox_root_id` performs no walk, so there is nothing
    to fail.
12. The client-visible response SHALL be a generic non-enumerating error and
    SHALL NOT expose another owner's run id, ancestry shape, or path. The
    server-side diagnostic SHALL record the visited-set size, the repeated node,
    and the failure class for support without user content. Tests SHALL cover a
    self-parent cycle, a two-node cycle, a missing ancestor, and cross-owner
    ancestry, and SHALL assert every caller refuses identically.

##### TTL sweeper protected set *(closes SGV2-GAP-018, restates v1 Requirement 2)*

13. The TTL sweeper's protected set SHALL be keyed by resolved revision root, not
    by individual run id. Every non-terminal run SHALL protect the revision root
    returned by the canonical resolver of Requirement 2 AC 1.
14. A terminal revision root with any non-terminal descendant SHALL NOT be swept.
    This explicitly includes a descendant durably paused at a human gate or a
    clarify gate for longer than the sandbox TTL; a durable pause SHALL NOT be
    treated as inactivity.
15. The protected-set query SHALL be computed from the same owner-scoped resolver
    used by launch, so the sweeper and the launch path can never disagree about
    which directory a family occupies. A resolver failure SHALL protect the
    directory (fail closed, never delete).
16. The sweeper correction SHALL land atomically with the revision-root
    re-keying of Requirement 2 AC 1–8, as required by Requirement 17 AC 2. A
    partial rollout in which paths are re-keyed but the protected set is not is
    prohibited.
17. A behavioral TTL-expiry test SHALL prove that a family whose root row is
    terminal, whose TTL has expired, and whose descendant is active or
    gate-paused still has its physical sandbox and its Git history on disk after
    a sweep, and that a fully terminal expired family is still swept.

---

### Requirement 3: Separate physical sandbox identity from logical run identity

**User Story:** As an operator, I want every run in a shared revision sandbox to
have its own unambiguous log and evidence paths, so that a v2 payload never
mislabels a cumulative family log as one run's trace.

#### Acceptance Criteria

1. `RunSandbox` SHALL carry both `sandbox_root_id` and `current_run_id`; one value
   SHALL NOT be reused for both meanings.
2. The physical path SHALL be
   `<RUNS_ROOT>/<user>/<sandbox_root_id>/`.
3. The exact current-run trace path SHALL be
   `.logs/{current_run_id}.jsonl`.
4. Validator evidence and browser artifacts SHALL remain scoped as
   `.verify/{current_run_id}/` and `.browser/{current_run_id}/`.
5. `engine.run()` and `_execute_impl()` SHALL construct the same physical root
   while retaining the logical `pipeline_run_id` for run-scoped paths.
6. `RunTrace` SHALL flush all buffered output, thinking, tool, and terminal-event
   entries before `.logs/{current_run_id}.jsonl` is copied to
   `.chain/logs.jsonl`.
7. A revision SHALL never append to `.logs/{revision_root_id}.jsonl` unless that
   revision itself is the root run.
8. Tests SHALL run a root plus two revisions in one physical sandbox and prove
   that three distinct `.logs/{run_id}.jsonl` files exist and that each chain
   snapshot contains only the selected run's trace.

---

### Requirement 4: Flat, minimal, Git-versioned `.chain/` payload

**User Story:** As a workflow author, I want every version to expose the same
small set of chain files, so that downstream workflows can consume a stable,
noise-free contract.

#### Acceptance Criteria

1. A v2 payload SHALL contain exactly three regular files and no directories:
   `.chain/logs.jsonl`, `.chain/summary.md`, and
   `.chain/{workflow_output_filename}`.
2. Agent transcripts SHALL NOT be copied into `.chain/`; `.agents/` remains the
   run-local agent-to-agent/debug channel.
3. `workflow_output_filename` SHALL be the safe basename declared by the
   compiled deliverable. It SHALL contain no separator, SHALL NOT be `.` or
   `..`, and SHALL NOT collide case-insensitively with `logs.jsonl` or
   `summary.md`.
4. A chainable workflow without a declared output name SHALL fail compilation.
   A terminal run whose resolved output cannot be materialized under that name
   SHALL become degraded and SHALL receive no visible version tag.
5. For every tag in one revision family, the `.chain/` path set SHALL be
   identical; only file bytes may differ.
6. `logs.jsonl` SHALL be a byte-for-byte copy of the fully flushed
   `.logs/{current_run_id}.jsonl`.
7. `summary.md` SHALL be engine-rendered and include schema version, run id,
   workflow id, revision root id, the **candidate** terminal status, completed
   steps, output filename, the deterministic `intended_tag` when the candidate
   outcome is `completed`, the internal run ref name, a `payload_chainable`
   flag, and a timestamp. It SHALL NOT be agent prose. Every field SHALL be
   knowable before the commit that contains it; the summary SHALL NOT assert
   that a tag or commit which does not yet exist has been created. *(Corrected
   for SGV2-GAP-013; see AC 17 and Requirement 5 AC 22.)*
8. The output file SHALL contain the exact resolved workflow deliverable bytes;
   binary outputs such as PPTX SHALL remain binary-safe.
9. The flat payload SHALL be assembled in a temporary sibling directory and
   atomically replace the previous flat payload. Stale prior output basenames
   SHALL be removed from the tracked flat allowlist.
10. `.chain/` SHALL remain engine-reserved, excluded from
    `WorkflowRun.output` and deliverable serialization, readable/listed in the
    Workspace surface, and readable at an authorized version ref.
11. Exactly the three allowlisted files SHALL be committed. `.chain/` MAY remain
    in `.gitignore` as defense-in-depth, but the engine SHALL force-stage only
    those exact validated paths; arbitrary or nested `.chain` content SHALL
    never be force-added.
12. The staged chain payload SHALL pass the normal `pre_commit` secret scan. A
    blocked payload SHALL surface the reason, degrade the run, create no visible
    tag, and remain uncommitted.
13. Ref-scoped listing and archive tests SHALL prove that each completed tag
    contains the three flat files and no `.chain` directory entries or agent
    transcripts.
14. The force-stage allowlist of AC 11 SHALL be the only exception to the
    reserved-path registry of Requirement 18. It SHALL be evaluated as three
    exact normalized repository-relative paths, never as a `.chain` prefix
    match, and any other reserved path presented for staging SHALL be refused
    even when a caller passes it explicitly. *(Closes SGV2-GAP-001 for this
    requirement's surface.)*
15. The output file of AC 8 SHALL be subject to the binary secret-inspection
    policy of Requirement 11 AC 14–17 before it enters history. "Binary-safe"
    describes byte fidelity only; it SHALL NOT be read as an exemption from
    scanning. *(Closes SGV2-GAP-008 for this requirement's surface.)*
16. WHEN the payload is blocked by the secret scan (AC 12) or the resolved output
    cannot be materialized under its declared name (AC 4), THE engine SHALL
    build a **metadata-only terminal snapshot** instead: `.chain/summary.md`
    alone, with `payload_chainable: false` and a generic machine-readable
    non-chainable reason. It SHALL contain no `logs.jsonl`, no output bytes, no
    blocked content, and no excerpt of the blocked material. The three-file rule
    of AC 1 and the identical-path-set rule of AC 5 SHALL NOT apply to a
    metadata-only snapshot, and such a snapshot SHALL receive no visible tag.
    *(Closes SGV2-GAP-011 for this requirement's surface; see V2-Q9 and
    Requirement 5 AC 15–18.)*
17. `intended_tag` SHALL be a deterministic name derived from the revision index,
    SHALL be recorded as intent only, and SHALL never be presented as proof that
    the tag exists. Tag existence SHALL be proven only by the Git tag itself, the
    persisted `WorkflowRun.git_tag`, and the finalization record. A committed
    `summary.md` SHALL NOT be amended, rewritten, or re-committed to reflect a
    tag created afterwards. *(Closes SGV2-GAP-013 for this requirement's
    surface.)*

---

### Requirement 5: Terminal finalization is ordered, idempotent, and truthful

**User Story:** As a user, I want a completed version to describe the actual final
run state, so that tags never capture an optimistic or partially finalized
result.

#### Acceptance Criteria

1. THE engine SHALL resolve the real terminal status, failed-agent set, final
   deliverable, and blocked-commit state before terminal versioning begins.
2. The current optimistic `completed` stamp before Step 5 SHALL be removed.
3. The ordered finalization sequence SHALL be:
   1. acquire the revision-family lock;
   2. reconcile/commit dirty WIP for non-success outcomes through `pre_commit`;
   3. finalize and flush the current run trace;
   4. atomically build the flat payload;
   5. force-stage the payload allowlist and run `pre_commit`;
   6. create the terminal snapshot commit;
   7. create the internal run ref under create-only compare-and-set semantics
      (AC 23);
   8. for a `completed` candidate outcome only, create `v{revision_index}` on the
      same commit and persist `WorkflowRun.git_tag`;
   9. persist the durable finalization record and the published status (AC 19);
   10. dispatch the real observation-only `post_run` hook;
   11. emit the externally visible terminal event (AC 12);
   12. remove worker worktrees while retaining branches when required, record
       metrics, and run `git gc --auto`.
4. The terminal SSE event SHALL not be externally emitted as `completed` until
   required finalization through visible-tag persistence has succeeded.
5. `cancelled`, `failed`, `degraded`, and `diverted` runs SHALL receive an
   internal run ref but no visible `vN` tag.
6. A completed run's visible tag and internal run ref SHALL resolve to the same
   terminal snapshot commit.
7. Re-entering finalization after a crash SHALL converge on the same commit,
   internal ref, tag, and DB mapping without duplicate commits or tags.
8. A process-local set SHALL NOT be the sole idempotency mechanism. Git refs and
   durable run state SHALL be inspected before repeating side effects.
9. Tag success followed by DB failure SHALL be recoverable: finalization SHALL
   retry the mapping or remove only the newly created tag before reporting a
   degraded outcome. It SHALL NOT silently leave an orphan tag.
10. A required commit/ref/tag failure SHALL emit a structured
    `run_finalization_failed` event, surface a generic client-safe reason, mark
    the run degraded, and never report a completed version.
11. The terminal snapshot commit message SHALL identify the logical run id and
    terminal status without containing user content or secrets.

##### Terminal publication ordering for every status *(closes SGV2-GAP-010)*

12. AC 4 SHALL be generalized: no externally visible terminal event for any
    status — `completed`, `cancelled`, `failed`, `degraded`, or `diverted` —
    SHALL be emitted before AC 3 steps 1–10 have succeeded for that status and
    its finalization record is durable. AC 4 remains binding as the `completed`
    case of this rule. Step 12 cleanup MAY follow the event, since worktree
    removal, metrics, and GC do not change the version a consumer can read.
13. A chain launch SHALL be admitted only against a source whose finalization
    record reports a completed required sequence (V2-Q11). Launch SHALL NOT infer
    finalization from the run's status column alone, because the status can be
    durable before the ref and payload exist.
14. Immediate chaining SHALL be tested after each of the five terminal statuses,
    launched as early as the terminal event is observable. Each test SHALL prove
    the child either received the source's exact payload or received an explicit
    refusal — never a silently empty chain payload caused by the race.

##### Security-blocked and unmaterializable payloads *(closes SGV2-GAP-011)*

15. THE `completed`-only tagging rule of AC 5 SHALL be narrowed further: a run
    whose payload was blocked or unmaterializable SHALL be published `degraded`
    and SHALL receive no visible tag even if its candidate outcome was
    `completed`.
16. A blocked or unmaterializable payload SHALL still produce a terminal snapshot
    commit and an internal run ref, built from the metadata-only snapshot of
    Requirement 4 AC 16, so that AC 7's idempotent re-entry and V2-Q3's
    every-terminal-ref rule stay satisfiable. The definition of "terminal
    snapshot commit" is satisfied by a metadata-only snapshot in this case.
17. The finalization record and `WorkflowRun` SHALL carry a durable
    `payload_chainable = false` plus a generic non-chainable reason. Requirement
    6 SHALL refuse a chain launch against such a source (Requirement 6 AC 19)
    rather than degrade to empty context.
18. Blocked content SHALL never become reachable from any commit, tree, tag,
    internal ref, base branch, retained worker branch, reflog entry created by
    finalization, or event payload. Crash-and-retry at every step of AC 3 SHALL
    be tested against a fixture whose secret must never appear in
    `git rev-list --objects --all` output for the sandbox.

##### Candidate outcome versus published status *(closes SGV2-GAP-012)*

19. The candidate outcome recorded in the snapshot (Requirement 4 AC 7) and the
    published `WorkflowRun` status SHALL be distinct values. Finalization SHALL
    persist one durable finalization record holding the candidate outcome,
    snapshot commit id, internal ref state, tag state, published status,
    chainability, and failure reason.
20. A finalization failure occurring after the snapshot commit exists SHALL
    change only the published status and the finalization record. It SHALL NOT
    amend, re-commit, force-update, or delete the existing snapshot commit, and
    SHALL NOT rewrite the committed `summary.md` or the flushed terminal log to
    match the new published status.
21. After every injected failure point in AC 3 — before commit, after commit and
    before ref, after ref and before tag, after tag and before mapping, and
    after mapping — the published status, the finalization record, the internal
    ref, and the visible tag SHALL converge to one consistent description on
    retry. Consumers SHALL read the published status from the database and the
    finalization record, never from `summary.md`. A test SHALL assert this at
    each injected point.

##### Tag and summary ordering *(closes SGV2-GAP-013)*

22. The visible tag name SHALL be deterministic and computed before the snapshot
    commit so that `intended_tag` is meaningful, and tag creation SHALL point at
    the already-created snapshot commit. Moving, deleting and recreating, or
    re-pointing a tag in order to repair summary text is prohibited. This does
    not restrict AC 9, which permits removing a tag the same finalization attempt
    had just created in order to roll back an incomplete mapping — that removes a
    tag that was never successfully published, and it never repoints a tag at a
    different commit. A test SHALL prove the tag and internal ref resolve to the
    commit whose `summary.md` names that same `intended_tag` and run id.

##### Internal run ref semantics *(closes SGV2-GAP-014)*

23. Internal run ref creation SHALL be create-only compare-and-set: absent means
    create; present and pointing at the identical commit means success and is
    idempotent; present and pointing at a different commit means fail closed. The
    finalizer SHALL NOT move, force-update, or delete an existing internal run
    ref.
24. A present-but-different internal run ref SHALL produce a
    `run_finalization_failed` outcome per AC 10, publish the run `degraded`,
    record the conflicting commit ids in the finalization record, and preserve
    the existing ref for operator inspection. Recovery SHALL be an explicit
    operator action; the engine SHALL NOT self-heal by overwriting.
25. Requirement 6 AC 3's tag-versus-ref consistency check SHALL use the same
    comparison semantics so that a source whose ref and tag disagree is refused
    rather than read. Tests SHALL cover repeated finalization, a manually
    corrupted ref, and a ref that survives while the tag is absent.

---

### Requirement 6: Chaining reads the exact immutable source run version

**User Story:** As a user, I want chaining from v1 to receive v1's payload even
when v2 or v3 exists, so that the selected source run—not the latest working
tree—defines the next workflow's context.

#### Acceptance Criteria

1. Launch SHALL resolve and authorize the exact `source_run_id` before engine
   execution using the standard two-layer owner gate; missing or cross-owner
   sources SHALL return 404.
2. The provider SHALL never use `HEAD`, the live flat `.chain/`, the latest tag,
   or a tag derived from an ordinal.
3. If the owned source row has `git_tag`, chaining SHALL read that exact tag. IF
   the source's internal run ref exists, THE reader SHALL verify the tag and the
   ref resolve to the same commit under the comparison semantics of Requirement 5
   AC 25 and SHALL refuse on disagreement. IF the internal run ref is absent, the
   source SHALL be treated as a **legacy tagged source** and handled by
   Requirement 7 AC 9–12; absence of an internal ref alone SHALL NOT be treated
   as a disagreement, a corruption, or a reason to widen the search. *(Corrected
   for SGV2-GAP-015.)*
4. If the source is untagged, chaining SHALL read its trusted internal run ref.
5. Internal refs SHALL be constructed only from a validated owned run UUID and
   SHALL never be accepted as a caller-supplied revspec.
6. The reader SHALL enumerate `.chain/` at the selected ref and accept only
   `logs.jsonl`, `summary.md`, and exactly one safe non-reserved output basename.
7. `summary.md` SHALL identify the requested source run id and output filename;
   disagreement SHALL be treated as corrupt provenance and SHALL not fall back
   to another ref.
8. Files SHALL be read and written as bounded byte streams, not UTF-8 strings.
9. The three files SHALL be copied atomically before agent 1 starts to:
   `.context/logs.jsonl`, `.context/summary.md`, and
   `.context/{workflow_output_filename}`.
10. A missing, swept, or corrupt authorized payload SHALL produce an explicit
    `chain_context_unavailable` event and allow the run to continue with no
    chain payload when the workflow policy permits graceful degradation.
11. Authorization uncertainty SHALL fail closed before disk access. The context
    provider MAY return `{}` after an app-side authorization failure has already
    prevented launch; it SHALL never read an unowned sandbox.
12. Tests SHALL chain from v1 after v3 exists, from a mid-family revision, from
    an untagged failed run, and with a binary output; each SHALL receive only the
    selected source bytes.

##### Manifest-declared activation gate *(closes SGV2-GAP-003)*

13. The chain-context provider SHALL activate only when the compiled workflow
    carries a declared chain capability. The presence of `source_run_id` on the
    run row, in the launch request, or on `ExecutionContext` SHALL NOT by itself
    authorize any cross-run read, any ref resolution, or any disk access. This is
    the same declared-gate discipline the `previous_run` provider already
    requires.
14. The declaration SHALL be a compile-time field on the compiled workflow, and
    the compiler SHALL reject a manifest that declares chain acceptance without a
    resolvable output-name contract (Requirement 4 AC 4) or that declares an
    unknown chain policy value. The kernel SHALL remain name-free: the gate SHALL
    be read from the compiled plan, never from a workflow id comparison.
15. Tests SHALL prove that a stray `source_run_id` on a workflow *without* the
    declaration performs zero cross-run reads — no ref resolution, no
    `git show`, no source sandbox `stat` — and installs no `.context/` chain
    files, while the same source read by a declared workflow yields the
    authorized exact-ref payload.

##### Lineage persistence *(closes SGV2-GAP-004, backend half)*

16. The launch transaction SHALL persist the authorized `source_run_id` onto the
    new `WorkflowRun` row atomically with run creation. Consuming the source id
    transiently is insufficient. A run that read a chain payload SHALL always
    have the corresponding persisted edge, and a run that was refused a payload
    SHALL NOT have one. The run and family API projections SHALL expose that edge
    (Requirement 15 AC 7–8) for the product surface of Requirement 21 AC 1–4.

##### Source eligibility *(closes SGV2-GAP-016)*

17. A source run SHALL be eligible only when it is terminal and its finalization
    record reports a completed required sequence (V2-Q11). A non-terminal source
    SHALL be refused at launch with an explicit, generic, retryable reason. The
    graceful-degradation rule of AC 10 SHALL NOT be reachable for this case; it
    covers only genuinely missing or corrupt payloads for an eligible source.
18. A source that is terminal but not yet finalized SHALL be refused with a
    distinct transient reason so the caller can retry. The engine MAY implement a
    bounded wait, but the ceiling SHALL be explicit and its expiry SHALL be a
    refusal, never an empty payload.
19. A source whose finalization record reports `payload_chainable = false`
    (Requirement 5 AC 17) SHALL be refused with a durable non-chainable reason
    and SHALL NOT be read from disk or from any ref. Tests SHALL cover a running
    source, a terminal-but-unfinalized source, a secret-blocked source, and an
    unmaterializable-output source, and SHALL assert that none of them yields an
    empty-but-successful chain launch.

---

### Requirement 7: Legacy nested payloads remain compatible without polluting `.chain/`

**User Story:** As an existing user, I want old nested payloads to remain
chainable where their live files still exist, without carrying their folder
noise into new Git history.

#### Acceptance Criteria

1. Before the first v2 flat payload is installed, any legacy
   `.chain/{run_id}/` directories SHALL be moved atomically to the reserved,
   ignored, non-listed `.chain-legacy/{run_id}/` namespace.
2. The move SHALL preserve bytes and SHALL remove the old directory only after
   the destination is durable. Existing `.chain-legacy/{run_id}/` content SHALL
   never be overwritten silently.
3. `.chain/` SHALL contain no directory after migration.
4. `.chain-legacy/` SHALL be excluded from Git, Workspace listing, deliverables,
   zips, agent tools, and ordinary single-file APIs.
5. For an old source whose tag lacks flat files, the reader MAY fall back in
   this order only: `.chain-legacy/{source_run_id}/`, then the unmigrated live
   `.chain/{source_run_id}/` layout.
6. The fallback SHALL validate the nested `summary.md` run id, select only the
   summary, exact run log, and declared output, and copy all bytes into the new
   flat `.context/` names. Agent transcripts SHALL be ignored.
7. The fallback SHALL emit provenance `legacy-live-nested`; it SHALL never fall
   back to live flat `.chain/`, another run's nested directory, latest tag, or
   `HEAD`.
8. Missing legacy live data SHALL degrade explicitly; old tags and Git history
   SHALL never be rewritten to manufacture payloads.

##### Legacy tagged sources without an internal run ref *(closes SGV2-GAP-015)*

9. Legacy detection SHALL be by feature, not by date or deploy flag: a source is
   legacy when it has no internal run ref, or when the `.chain/` tree at its
   selected ref carries no v2 schema version in `summary.md`. No global cutover
   timestamp SHALL be used, consistent with Requirement 17 AC 3.
10. For a legacy tagged source, authorization SHALL come from the owned
    `WorkflowRun` row and the exact stored `git_tag`. The reader SHALL NOT require
    `refs/ideaflow/runs/{source_run_id}` to exist, SHALL NOT synthesize or
    backfill that ref, and SHALL NOT substitute the latest tag, an ordinal-derived
    tag, another revision's tag, or `HEAD`. The stored tag SHALL be matched
    exactly against the owned sandbox's visible tag list before any Git
    subprocess receives it.
11. For a legacy source the eligibility rule of Requirement 6 AC 17–18 SHALL be
    satisfied by the terminal status on the owned row, because pre-v2 runs have no
    finalization record. Absence of a finalization record SHALL NOT be read as
    "not finalized" for a legacy source, and SHALL NOT make a legacy source
    eligible when its status is non-terminal.
12. Once authorized, the read SHALL use only the fallback order of AC 5 and the
    validation of AC 6, and SHALL emit provenance `legacy-live-nested` per AC 7.
    A legacy source with no recoverable nested payload SHALL degrade explicitly
    per AC 8. Tests SHALL cover a legacy completed run with a tag and live nested
    payload, the same run after its nested payload was swept, and a legacy
    untagged terminal run, and SHALL assert that no internal ref is ever created
    for a legacy source.

---

### Requirement 8: `.context/` is deterministic, inherited, and resumable

**User Story:** As an agent author, I want one deterministic context directory,
so that a revision or resumed run sees the same inputs as the original run.

#### Acceptance Criteria

1. OpenDesign files SHALL be produced by the same
   `resolve_launch_od_context` result used by launch today.
2. `.context/design/` and `.context/selections.json` SHALL be fully written
   before step 1.
3. A revision SHALL inherit its revision root's design context unchanged unless
   the revision request explicitly supplies a newly resolved design selection.
4. A chained run SHALL receive the three chain files at the `.context/` root as
   defined by Requirement 6.
5. Chain payload installation SHALL not overwrite `.context/design/` or
   `selections.json`.
6. `resume_run` SHALL rebuild `ectx.od_context` from the persisted files and
   SHALL preserve the same chain payload bytes already present.
7. `.context/` remains ignored, listed, readable to authorized agents, and
   excluded from deliverables.
8. A resumed and uninterrupted execution with the same inputs SHALL observe
   byte-identical `.context/` files.

---

### Requirement 9: Ref browsing is read-only and restore is a real locked command

**User Story:** As a user, I want to browse and restore versions safely, so that
historical reads never move HEAD and restoring creates new history rather than
rewriting old history.

#### Acceptance Criteria

1. Ref listing SHALL use `git ls-tree`, single-file reads SHALL use `git show`,
   and zip downloads SHALL use an in-memory `git archive` as appropriate.
2. Caller-provided refs SHALL be exact matches in the owned sandbox's visible
   tag list before any Git subprocess receives them.
3. Browsing SHALL never run checkout, reset, read-tree, or move HEAD.
4. A real authenticated `POST /api/runs/{run_id}/restore` REST command SHALL
   accept a visible tag and an idempotency key. It SHALL use the existing
   two-layer owner gate and return 404 for missing/cross-owner runs.
5. Restore SHALL acquire the revision-family lock, check all family members for
   non-terminal status under that same lock, and fail closed if the check or
   lock fails.
6. The UI SHALL disable restore while a family run is active and display the
   server-provided generic reason.
7. Restore SHALL materialize the selected tracked tree and create a forward
   commit `restore: {tag}`. It SHALL preserve every existing commit and tag.
8. Restore SHALL never use `reset --hard`, rewrite a tag, move a branch
   backwards, or checkout a tag into the live tree.
9. Restore SHALL reject dirty or merge-in-progress trees unless they have first
   been reconciled under Requirement 10.
10. Two concurrent restores using different idempotency keys SHALL serialize;
    repeating one idempotency key SHALL return the first result without a second
    commit.
11. A structured audit event SHALL record actor, run, revision root, source tag,
    resulting commit, and outcome without user file contents.
12. The next completed run after restore SHALL overwrite the flat `.chain/` and
    tag that new run normally; the restore commit itself SHALL not consume a
    `vN` ordinal.

---

### Requirement 10: Family locking and dirty-tree recovery cover every write entry

**User Story:** As a maintainer, I want every operation that mutates a shared
revision sandbox serialized, so that revisions, recovery, and restore cannot
race.

#### Acceptance Criteria

1. One cross-process lock keyed by `(user_id, revision_root_id)` SHALL cover
   revision admission, shared-root open, dirty recovery, restore, and terminal
   finalization.
2. The lock and active-run check SHALL be one atomic fail-closed operation; an
   LLM instruction or process-local mutex is insufficient.
3. Dirty-tree reconciliation SHALL run before any seed, context, agent, restore,
   or new-revision write both on resume and on ordinary shared-root revision
   open.
4. Recovery commits SHALL use the ordinary staged-diff and `pre_commit` hook
   path.
5. Recovery messages SHALL distinguish `cancelled`, `failed`, `degraded`,
   `crash-recovered`, and `restore-precondition`; they SHALL not label every
   outcome `cancelled`.
6. Staged, unstaged, and untracked changes SHALL be preserved. A merge-in-
   progress, index lock, corrupt repository, or Git command failure SHALL be an
   explicit failure, not interpreted as clean.
7. `commit_all()` SHALL distinguish a genuine no-change exit from all other Git
   failures and SHALL raise a typed error for the latter.
8. Crash injection after recovery commit creation and before state persistence
   SHALL prove idempotent resume with no duplicate recovery commit.

##### Uploads are a family write *(closes SGV2-GAP-006)*

9. AC 1's enumeration SHALL explicitly include `POST /api/runs/{run_id}/files`.
   The upload route SHALL root-resolve its target per Requirement 2 AC 7 and
   SHALL acquire the same `(user_id, revision_root_id)` lock as every other
   family write. The existing per-sandbox manifest lock SHALL be retained for
   within-upload deduplication but SHALL NOT be treated as the family lock.
10. Upload admission per run state SHALL be explicit and documented:
    - while the family has no active run: accepted;
    - while an agent step is executing: accepted, serialized behind the family
      lock, and made visible only as a complete file plus manifest entry;
    - while a run is paused at a human or clarify gate: accepted, same
      serialization;
    - while terminal finalization holds the lock: rejected with a generic
      retryable reason, or queued behind the lock with a bounded wait, never
      written concurrently with trace flush, payload assembly, or staging;
    - while a restore holds the lock: rejected with a generic retryable reason.
11. Lock ordering SHALL be single and documented: family lock first, then the
    per-sandbox manifest lock. No path SHALL acquire them in the opposite order.
12. An upload SHALL be atomically visible: bytes durable, then manifest entry,
    then response. A partially written upload SHALL never be observable to an
    agent, a deliverable walk, a payload assembly, or a snapshot commit. Uploads
    remain under `.uploads/`, which stays reserved and untracked per Requirement
    18.
13. Tests SHALL cover upload-versus-upload, upload-versus-active-agent,
    upload-versus-restore, and upload-versus-finalizer races, and SHALL assert
    that no upload lands inside a terminal snapshot commit and that no snapshot
    is built from a half-written upload.

##### Abrupt crash with persistent Git state *(closes SGV2-GAP-009)*

14. On sandbox open, resume, restore, and finalization entry, the runtime SHALL
    detect each persistent Git state before any write: `MERGE_HEAD` or another
    in-progress merge, a stale `index.lock`, registered worker worktrees whose
    directories are missing or orphaned, unmerged worker branches, and a corrupt
    or unreadable repository.
15. Each detected state SHALL have exactly one required outcome:
    - in-progress merge belonging to the current run's recorded merge state:
      resume the merge state machine at the recorded fragment;
    - in-progress merge with no recorded merge state: abort the merge, preserve
      all worker branches, and record a `crash-recovered` reconciliation commit;
    - stale `index.lock` with no live owning process: remove it and record the
      removal in the finalization/audit record; a live owner SHALL be an explicit
      failure, never a forced removal;
    - orphaned worktree registration: prune the registration while retaining the
      branch;
    - unmerged worker branches: retain them and surface them for operator
      inspection; never delete to reach a clean state;
    - corrupt or unreadable repository: quarantine the family, refuse all writes,
      require operator action, and never delete or reinitialize the sandbox.
16. Recovery SHALL run under the family lock of AC 1 and SHALL reuse the ordinary
    staged-diff plus `pre_commit` commit primitive of Requirement 11 AC 9. A
    recovery path SHALL NOT bypass the secret scan.
17. Recovery SHALL be idempotent. Restart at crash points before the first
    fragment merge, between fragment merges, during a fragment merge, after the
    last fragment merge and before finalization, and inside finalization SHALL
    converge without duplicate merge commits, duplicate recovery commits, or lost
    worker branches.
18. AC 6's rule that these states are explicit failures rather than "clean"
    remains binding; AC 14–17 define what happens after the explicit failure is
    detected, so a crash no longer terminates in an unrecoverable state.
19. A crash-injection suite using real Git SHALL cover each state in AC 15 and
    each restart point in AC 17, and SHALL assert the resulting reconciliation
    message class per AC 5.

---

### Requirement 11: Hook lifecycle and blocked-commit diagnostics are complete

**User Story:** As an operator, I want hook outcomes and terminal lifecycle work
to be observable and deterministic, so that security blocks and cleanup are not
silent.

#### Acceptance Criteria

1. `pre_commit` SHALL aggregate `block` if any bound hook blocks; a hook
   exception SHALL follow the existing event-specific fail policy and SHALL be
   recorded without leaking payload data.
2. `post_commit` SHALL fire only after a real commit exists and SHALL be
   observation-only.
3. A blocked commit SHALL persist and expose a generic block reason on the run,
   emit a structured warning/event, leave the diff for correction, and suppress
   completed tagging.
4. The secret scanner SHALL receive the actual staged diff, including the three
   force-staged `.chain` files; an empty placeholder payload is insufficient.
5. `post_run` SHALL be a real `_fire_hooks("post_run", ...)` lifecycle dispatch,
   not only a comment or hardcoded helper name.
6. The durable finalizer SHALL invoke `post_run` exactly once for completed,
   cancelled, failed, degraded, and diverted outcomes.
7. WIP commit, worker-worktree removal, required branch retention, payload
   snapshot, tag/ref work, metrics, and GC SHALL all be owned by the one terminal
   finalization sequence rather than scattered terminal returns.
8. A test SHALL enumerate every terminal emission path and prove it reaches one
   finalizer and one `post_run` dispatch.

##### One security-gated commit primitive for every Git object *(closes SGV2-GAP-007)*

9. Exactly one commit primitive SHALL create Git commits in a sandbox. It SHALL
   own, in order: staging the intended paths, `pre_commit` dispatch, mandatory
   secret scanning of the actual staged content, commit creation, and
   `post_commit` dispatch. No caller SHALL invoke `git commit` outside this
   primitive.
10. The primitive SHALL cover every commit-producing path, including at minimum:
    step-boundary commits, spawn-point commits, worker-branch and worktree
    commits, per-fragment merge commits, merge-agent resolution commits,
    dirty-tree and crash recovery commits (Requirement 10 AC 4 and AC 16),
    restore commits (Requirement 9 AC 7), and the terminal snapshot commit
    (Requirement 5 AC 3 step 6) including a metadata-only snapshot.
11. Scanning SHALL be per-commit, not only at a later boundary. A secret
    introduced in a worker-branch or fragment commit SHALL be blocked at that
    commit; it SHALL NOT be permitted to exist in reachable history on the
    grounds that a later boundary diff is clean.
12. A blocked commit on any path SHALL follow AC 3: generic reason persisted and
    exposed, structured event emitted, diff left for correction, and completed
    tagging suppressed. For a worker or fragment commit the fan-out step SHALL
    additionally follow the refused-merge policy of Requirement 12 AC 2 rather
    than continuing as though the fragment applied.
13. Retained branches are in scope. A retained cancelled or unmerged worker branch
    SHALL have been scanned at commit time. Real-Git tests SHALL plant a secret at
    each commit path in AC 10 and assert that after the run the secret is
    unreachable from every tag, internal ref, base branch, and retained worker
    branch — asserted via object enumeration, not only via a diff of the tip.

##### Binary payload secret inspection *(closes SGV2-GAP-008)*

14. AC 4's staged-diff input remains the contract for text content. For binary
    content it is insufficient: when staged content is binary, or when Git reports
    it as binary, the scanner SHALL inspect the staged file content itself rather
    than the textual diff.
15. The binary policy SHALL be one explicit declared outcome per content type and
    size, chosen from: content-scan the raw bytes; safe-extraction scan for
    known container formats such as PPTX, DOCX, XLSX, and ZIP with bounded
    recursion depth, bounded expanded size, and no path traversal; block by type
    or size with a generic reason; or accept under a recorded, security-approved
    exemption. The default for an unknown binary type SHALL be fail-closed
    (block), never silent acceptance.
16. Extraction SHALL be resource-bounded and SHALL treat archive contents as
    untrusted input. Extraction failure, exceeded bounds, or a malformed container
    SHALL block rather than pass.
17. A binary fixture — at minimum a PPTX carrying an embedded secret marker in
    its internal parts — SHALL be committed as a test asset. A test SHALL assert
    the marker is detected and the commit blocked under the scanning policy, or,
    if the approved policy is a recorded exemption, SHALL assert the exemption is
    explicitly recorded and the payload marked accordingly. "Binary files differ"
    SHALL never be an accepted scan result.

---

### Requirement 12: Fan-out merge outcomes are explicit and policy-complete

**User Story:** As a user, I want fan-out conflicts to follow the declared policy
without silently discarding worker output or continuing after a refused merge.

#### Acceptance Criteria

1. Compile-time `on_conflict` values SHALL be exactly `human_gate`,
   `merge_agent`, `partial`, or `abort`, defaulting to `human_gate`.
2. A refused-before-start merge SHALL be distinct from a merge that started and
   conflicted; it SHALL emit `merge_failed` and stop/degrade according to a
   documented policy, never continue as though the fragment applied.
3. A conflict SHALL write the existing owner/workspace-scoped
   `merge_conflict` artifact before emitting the `merge_conflict` event.
4. The event SHALL carry the artifact reference when persistence succeeds and
   a generic reason when it does not.
5. Prior successful fragment merge commits SHALL remain intact when a later
   fragment conflicts.
6. `partial` SHALL define exactly which non-conflicting state is retained after
   aborting the conflicting merge.
7. `merge_agent` SHALL use the manifest-declared bounded resolver, materialize a
   clean verified result, and commit it before reporting success.
8. `human_gate` SHALL persist a durable decision and resume through the same
   merge state machine.
9. Cancellation SHALL clear merge state and worktree registrations while
   retaining unmerged worker branches.
10. Real-Git tests SHALL cover conflict/refusal on first and later fragments,
    all four policies, resolver exhaustion, cancellation, and human-gate resume.
11. Fan-out SHALL record durable merge state — the fragment order, the fragment
    currently being merged, and each fragment's outcome — before each merge
    attempt, so that Requirement 10 AC 14–17 can classify an abrupt crash as
    "resume the recorded fragment" rather than "unknown merge in progress". All
    fan-out commits SHALL go through the single security-gated commit primitive of
    Requirement 11 AC 9–13, and crash restart at every fragment boundary SHALL be
    covered by the suite in Requirement 10 AC 19. *(Closes SGV2-GAP-009 for this
    requirement's surface.)*

---

### Requirement 13: Prompt migration has one complete, testable input ledger

**User Story:** As a workflow author, I want every removed prompt input to have an
explicit destination and recipient, so that file-based context does not silently
remove governance or task information.

#### Acceptance Criteria

1. Manifest prompt-policy selection SHALL default to `default` when omitted or
   empty. An unknown non-empty policy SHALL fail compilation with a clear error.
2. The body-only policy applies only to ungoverned agents. Governed agents SHALL
   retain guardrails, hooks, Constitution, and `AGENT.md`.
3. Removing the factory `skills` block SHALL NOT remove deepagents'
   `SKILLS_SYSTEM_PROMPT`; a test SHALL prove staged skills remain discoverable.
4. The user request SHALL go to agent 1 initially. The engine SHALL NOT create
   `REQUEST.md` or otherwise persist/propagate the raw request for downstream
   agents.
5. Every migrated first step SHALL produce a durable contract artifact; later
   agents SHALL read declared files and their own task.
6. The following 30-row ledger is normative and SHALL have no blank destination
   or untested migration state.

| # | Current input | V2 destination/recipient |
|---:|---|---|
| 1 | tool-availability text | Dropped; provider tool schemas remain authoritative |
| 2 | template/design/craft injection | `.context/design/` |
| 3 | guardrails | Governance system-prompt order |
| 4 | skills block | Deepagents skill prompt; staged `skills/` paths |
| 5 | behavioral hooks | Governance system-prompt order |
| 6 | Constitution | Governance system-prompt order |
| 7 | prompt body | Agent's `AGENT.md` |
| 8 | original brief | Agent 1 initial message only, except Requirement 14 retries |
| 9 | conditional retry feedback | Targeted retry control payload |
| 10 | planner analysis | `PLANNER.md`, written after clarify merge |
| 11 | active design/template material | `.context/design/` |
| 12 | upstream agent output | `.agents/{NN}-{agent_id}.md` |
| 13 | prior output on redo | `.agents/{NN}-{agent_id}-p{visit-1}.md`, named in control payload |
| 14 | HITL revise directive | Targeted redo control payload |
| 15 | prior revision spec/tasks | Shared sandbox root files |
| 16 | mid-run user guidance | Consume-once targeted control; sticky uploads remain `.uploads/` |
| 17 | revision analysis | Analyzer artifact and `.agents/01-*.md` |
| 18 | current prototype plus instruction | Prototype file; instruction follows brief-recipient rules |
| 19 | current task | Targeted task control; durable task remains in `tasks.md` |
| 20 | compacted build skeleton | Worker reads current output file from sandbox |
| 21 | template-compliance ids | `.context/selections.json`; rule in `AGENT.md` |
| 22 | multimodal blocks | Unchanged typed multimodal input |
| 23 | launch `od_context_json` | `.context/`; resume rebuilds in-memory context |
| 24 | frontend enriched chain text | Removed for new launches; exact ref payload is in `.context/`. Historical marker-bearing runs stay readable — transition governed by AC 11 and Requirement 21 AC 5–10 |
| 25 | previous-run seed/pointer | Shared revision tree; redundant seed short-circuited |
| 26 | uploaded-files context | `.uploads/` raw and extracted sidecars |
| 27 | staged skills | Unchanged `skills/` directory |
| 28 | validation-fix message | Targeted control with validation errors and file path |
| 29 | planner design-context argument | In process; rebuilt from `.context/` on resume |
| 30 | other `ectx.od_context` readers | In process; rebuilt from `.context/` on resume |

7. Each ledger row SHALL record normal, retry, redo, resume, and chained-run
   behavior in tests or an explicit not-applicable assertion.
8. Seam 2 SHALL be deleted only after every built-in workflow is inventoried,
   its first durable artifact is verified, its manifest is migrated, and its
   prompt snapshots are reviewed. `prototype` remains last.
9. The prompt viewer SHALL display the effective system prompt plus targeted
   control payload, never a misleading empty context message.
10. Prompt overrides remain replacement bodies; their API documentation SHALL
    state that truth. Production override migration remains deferred to the v1
    trigger unless product state has changed.
11. Ledger row 24 SHALL have a defined transition, not only a removal. "Removed"
    applies to *new launches*: no new run SHALL be launched with a
    frontend-assembled chain text block, and the backend SHALL reject or ignore a
    legacy chain text block on a launch that also carries an authorized
    `source_run_id` so that no run can receive the same chain context twice in two
    formats. Rendering of historical runs that already contain the marker, the
    one-time cleanup of stale client storage, and mixed-deploy behavior are
    specified in Requirement 21 AC 5–10. *(Closes SGV2-GAP-005 for this
    requirement's surface.)*

---

### Requirement 14: Retry and redo classes have explicit brief visibility

**User Story:** As an agent author, I want each retry class to receive only the
control information it needs, so that retries remain effective without restoring
broadcast prompt pollution.

#### Acceptance Criteria

1. A provider/transient retry of the same model invocation SHALL reuse the same
   already-built message and checkpoint semantics without adding a second brief.
2. A conditional-gate backward retry SHALL deliver, once to the retrying agent,
   its task, original user brief, pass number/limit, source step, source output,
   authored feedback, and previous-output file path.
3. A human-gate redo SHALL deliver the original brief and targeted rejection/
   revise directive only to the redone agent using a fresh redo checkpoint
   thread.
4. The validation-fix loop SHALL receive validation errors and the exact
   deliverable path; it SHALL not receive unrelated upstream context.
5. A merge-agent attempt SHALL receive only the owner-scoped conflict artifact,
   bounded resolution instructions, and attempt count; it SHALL not receive the
   original user brief by default.
6. Resume/replay SHALL preserve the recipient rules of the interrupted dispatch
   and SHALL not replay a consumed one-shot control payload twice.
7. All consume-once scratch state SHALL be drained unconditionally per dispatch
   iteration.
8. Full-composer tests—not source inspection or dictionary-pop simulation—SHALL
   cover every class above for first and non-first agents.

---

### Requirement 15: Persistence and ref mapping remain additive and consistent

**User Story:** As a maintainer, I want Git and database version identities to
remain consistent without unnecessary schema expansion.

#### Acceptance Criteria

1. Existing nullable `WorkflowRun.git_tag` remains the visible completed-version
   mapping; existing `source_run_id` remains the workflow-chain edge.
2. V2 SHALL add no `has_git` database field; `has_git` remains runtime-only.
3. V2 SHALL add no DB cache of repository tags.
4. Internal run refs SHALL be deterministic trusted Git refs derived from an
   owned run UUID; no new column is required unless implementation proves a
   durable mapping cannot otherwise be recovered.
5. Any new persistence discovered to be necessary SHALL be additive, nullable,
   owner/workspace-safe where applicable, and SHALL require the Alembic chain to
   have exactly one verified head before creation.
6. Visible tag, internal ref, terminal commit, summary run id, and DB `git_tag`
   SHALL be checked for consistency during finalization and source selection.
7. `WorkflowRun.source_run_id` SHALL be written in the same transaction that
   creates the chained run (Requirement 6 AC 16). It SHALL remain the only chain
   edge; it SHALL NOT alias into `parent_run_id` and SHALL NOT be mutated after
   creation.
8. The run-detail and revision-family API projections SHALL expose the chain edge
   and enough source identity for the product surface of Requirement 21 — at
   minimum the source run id, its workflow id, its published status, and its
   visible tag when one exists — scoped to the caller's ownership. A source the
   caller does not own SHALL be projected as absent rather than partially
   disclosed. *(Closes SGV2-GAP-004 for this requirement's surface.)*
9. The durable finalization record of Requirement 5 AC 19 SHALL be
   owner/workspace-scoped and additive per AC 5. Internal run refs remain
   deterministic Git refs; if the finalization record is implemented as a new
   table or column, its creation SHALL follow AC 5 and the Alembic chain SHALL
   have exactly one verified head before it is added. *(Closes SGV2-GAP-014 for
   this requirement's surface.)*
10. The provenance audit records required by Requirement 19 SHALL reuse existing
    owner/workspace-scoped persistence where it fits and SHALL otherwise be
    additive and nullable per AC 5. AC 2 and AC 3 remain binding: no `has_git`
    column and no database cache of repository tags.
11. Audit and finalization records SHALL store identifiers, statuses, and reasons
    only. They SHALL NOT store file contents, prompts, model output, diffs,
    secrets, or PII. *(Closes SGV2-GAP-020 for this requirement's surface.)*

---

### Requirement 16: Scope and non-goals are explicit

**User Story:** As a reviewer, I want clear product and file boundaries, so that a
corrective versioning change does not expand into unrelated Git or workflow
features.

#### Acceptance Criteria

1. Git history UI remains limited to the existing version selector and Workspace
   surfaces plus the restore action.
2. Push, remotes, branch management, pull requests, and `/flowin-handoff`
   behavior are out of scope.
3. Cross-tenant chaining is out of scope and prohibited by owner gates.
4. `previous_run` is short-circuited where redundant, not retired.
5. A DB cache of refs, family-level budgets, entitlement/tier gating, an
   agent-callable Git tool, a general agent delete tool, and remote-runtime
   redesign are out of scope.
6. `_extract_chain_context`'s hardcoded workflow branches SHALL not be extended;
   the file payload is their declarative replacement.
7. Existing tags and history SHALL not be rewritten. V2 does not promise to
   reconstruct swept legacy payloads.
8. The design component map SHALL identify every touched production and test
   surface and explicit no-change surfaces.
9. SC-001, INV-1, INV-3, INV-7, INV-12, the closed Workspace Protocol, additive
   migration policy, SSE/REST transport split, and existing import boundaries
   SHALL remain green.
10. Newly in scope because the gap audit found them missing, not optional: the
    canonical reserved-path registry and its enforcement points (Requirement 18),
    the durable provenance audit sink (Requirement 19), failure-event persistence
    and rendering (Requirement 20), and the chain launch/lineage product surface
    (Requirement 21). These are corrective closures of existing behavior, not new
    product features.
11. Still out of scope: an operator audit dashboard or reporting UI, log export
    pipelines, audit retention automation beyond a declared policy, a general
    binary content-inspection service beyond the payload/commit scanning of
    Requirement 11 AC 14–17, and any remote or third-party transmission of
    sandbox content.
12. Restore remains the only history-affecting user command (AC 1). Requirement 18
    SHALL NOT be used to introduce new user-facing file-visibility features; it
    only consolidates and restores existing exclusions.

---

### Requirement 17: Compatibility, rollback, and verification gate release

**User Story:** As a release owner, I want a reversible rollout with behavioral
proof, so that v2 cannot be declared complete from checkboxes or mocked source
assertions.

#### Acceptance Criteria

1. V2 SHALL land as focused changes in dependency order: baseline tests;
   reserved-path registry (Requirement 18); identity/logging together with
   sweeper protection; the security-gated commit primitive and binary scanning
   (Requirement 11 AC 9–17); flat payload/finalizer including the durable
   finalization record; exact-ref chaining including the declared activation gate;
   hooks/conflicts and crash recovery; restore/locking including uploads;
   provenance audit and failure-event contracts (Requirements 19 and 20);
   prompt migration; compatibility/UI (Requirement 21); final validation.
2. Revision-root correction and all callers SHALL land together with sweeper and
   family-lock protection; partial rollout is prohibited.
3. Flat payload writing SHALL be feature-detectable by the presence of the
   internal run ref and schema version in `summary.md`; no global date or deploy
   flag SHALL guess payload format.
4. Rollback SHALL stop producing v2 payloads without deleting tags, internal
   refs, flat tracked files, or legacy payloads. A rollback reader SHALL ignore
   unknown tracked `.chain` files rather than corrupting a run.
5. The v2 payload/finalizer change and revision-root correction SHALL be in
   separate focused commits/PRs where repository workflow permits, so each can
   be reverted independently.
6. Existing fan-out isolation tests SHALL pass or have a reviewed, recorded
   expectation change directly attributable to this spec.
7. Required behavioral tests SHALL include real Git and, where ownership or
   locks are involved, a real database: root/revision/chained identity; exact
   per-run logs; v1/v2/v3 identical paths with different bytes; older-source
   selection while HEAD is newer; binary payload; legacy fallback; finalizer
   crash replay; tag/DB partial failure; all conflict policies; restore-vs-run
   and restore-vs-restore races; dirty recovery; full prompt composers; and UI
   browse/restore behavior.
8. Source-inspection-only tests SHALL not count as acceptance for restore,
   lifecycle dispatch, locks, or prompt recipients.
9. Backend validation SHALL include targeted tests, characterization goldens
   with `SNAPSHOT_UPDATE` unset, `ruff`, `pyright`, `lint-imports`, banned-pattern
   tests, and the existing security/secret scans.
10. Frontend validation SHALL include targeted Vitest/RTL tests, lint, build, and
    mocked Playwright coverage for version browse/restore and chain launch.
11. `git status --porcelain tests/agents/characterization/golden/` SHALL be empty
    except for explicitly reviewed prompt-migration baselines.
12. Production apply/deployment remains pipeline-controlled and approved; no
    manual shared-environment mutation is part of this spec.

##### Verification added by the gap audit

13. The required behavioral test set of AC 7 SHALL additionally include: TTL
    sweep with a terminal root and an active or gate-paused descendant;
    `parent_run_id` cycle and cross-owner ancestry refusal at every caller;
    reserved-path enforcement across Git history, `list_files`, deliverable walk,
    zip, and public share; reserved-prefix seeding rejection; a stray
    `source_run_id` on an undeclared workflow performing zero cross-run reads;
    a planted secret at every commit path with object-level unreachability
    assertions; a PPTX binary fixture with an embedded secret marker; upload
    races against agent, restore, and finalizer; crash injection at each
    persistent Git state and fragment boundary; immediate chaining after each of
    the five terminal statuses; refusal for running, unfinalized, and
    non-chainable sources; a legacy tagged source with no internal run ref; a
    present-but-different internal run ref; and finalization failure injected at
    each point in Requirement 5 AC 3.
14. Security-relevant closures SHALL be verified by behavior, not by source
    inspection: reserved-path exclusion, per-commit secret scanning, binary
    inspection, non-chainable refusal, and blocked-content unreachability.
15. Reconnect-path coverage SHALL be required, not optional: every event class
    named in Requirement 20 SHALL be tested through a disconnect and reconnect,
    not only on the live stream.
16. Frontend validation of AC 10 SHALL additionally cover the chain lineage
    indicator, non-success source selection with its warning, legacy
    marker-bearing historical runs, one-time stale-storage cleanup, and rendering
    of `chain_context_unavailable` and `run_finalization_failed`.
17. Audit assertions SHALL prove the records of Requirement 19 exist, are
    owner-scoped, and contain no file contents, prompts, diffs, secrets, or PII.
18. Rollback verification (AC 4) SHALL additionally prove that a rollback reader
    ignores a v2 finalization record and a metadata-only snapshot without
    corrupting a run, and that no tag, internal ref, audit record, or legacy
    payload is deleted by rolling back.
19. A gap-closure review SHALL confirm, before release, that every row of the
    GAPS.md Closure Matrix has a passing test or an explicitly recorded
    not-applicable justification. An unreviewed row SHALL block release.

---

### Requirement 18: One reserved-path registry protects history, listings, deliverables, and seeds

**User Story:** As a security reviewer, I want every reserved sandbox path
protected by one registry at every boundary, so that replacing the v1 gitignore
mechanism does not quietly reopen leaks into Git history, the Files tab, the
deliverable zip, or a public share.

This requirement restates and consolidates v1 Requirements 8, 9, 21, and 44,
which the v2 supersession matrix had marked **Replace**. The flat `.chain/`
allowlist is the *only* narrowing v2 intends.

#### Acceptance Criteria

##### Registry and enforcement points *(closes SGV2-GAP-001)*

1. THE engine SHALL own exactly one canonical reserved-path registry. Today's
   implementation set is `.uploads/`, `.logs/`, `.verify/`, `.browser/`,
   `.agents/`, `.chain/`, `.context/`, `skills/`, and `conversation_history/`; v2
   SHALL add `.chain-legacy/`. Adding a reserved path SHALL be a single-edit
   change to that registry.
2. Every enforcement point SHALL derive its exclusions from the registry rather
   than keeping an independent literal list: the seeded `.gitignore`, Git staging,
   `serialize_sandbox_deliverable`, `count_sandbox_deliverables`, `list_files`,
   the single-file read route, the zip/archive route, the public-share output
   path, `WorkflowRun.output`, and agent-callable file tools. A test SHALL assert
   the enforcement points and the registry agree, so the v1 failure mode of "two
   separate lists" cannot recur.
3. `.git/` and `.gitignore` SHALL remain excluded from the deliverable walk,
   deliverable counting, `list_files`, zip, and public share, exactly as v1
   Requirement 9 required. `skills/` SHALL remain excluded from all of them.
4. The `.gitignore` SHALL continue to be seeded inside the same logical
   `git init` operation, before the initial commit, and SHALL cover every
   registry entry.
5. The only permitted exception SHALL be the three exact payload-allowlist paths
   of Requirement 4 AC 11, force-staged by the engine. The exception SHALL be
   matched as exact normalized paths, never as a `.chain` prefix. `.chain-legacy/`
   SHALL never be staged, listed, zipped, shared, or included in deliverables.
6. Reserved paths SHALL remain readable only through the authorized Workspace
   surfaces that already expose them by design — `.chain/` listing and
   authorized-ref reads per Requirement 4 AC 10, and `.context/` per Requirement 8
   AC 7. Read-visibility SHALL NOT imply Git-tracking, deliverable inclusion, zip
   inclusion, or share inclusion.
7. A public share SHALL expose only the deliverable projection. No registry path,
   no `.git/`, and no `.gitignore` SHALL be reachable through a share link, and a
   share of a run whose family has a `.chain/` payload SHALL NOT leak that
   payload.
8. Behavioral tests SHALL assert, after a completed run and after a restore:
   `git log --name-only` and `git show --stat` contain no registry path except
   the three allowlisted files; `list_files` and the deliverable walk contain no
   registry path, `.git/`, or `.gitignore`; the zip contains none of them; the
   public-share output contains none of them; and an agent file tool cannot read
   or write one. This restates v1 Requirement 44 as executable coverage.

##### Reserved-prefix seeding and cross-run-read guard *(closes SGV2-GAP-002)*

9. Any declared cross-run file selector — including
   `previous_run.seed_files.from_run` and any equivalent selector added later —
   SHALL reject an entry naming a registry path. Rejection SHALL match both the
   trailing-slash form and the bare name, and SHALL match nested paths beneath a
   registry entry.
10. The rejection list SHALL be derived from the registry of AC 1 so that
    `.chain-legacy/` and any future reserved path are covered automatically. The
    v1 guard's eight-prefix literal SHALL NOT remain the source of truth.
11. Rejection SHALL happen at compile time where the selector is statically
    declared, and again at runtime as defense in depth. A compile-time rejection
    SHALL be a clear manifest error naming the offending entry.
12. A rejected entry SHALL NOT silently fall back to a default seed set that
    would copy other files the manifest did not intend. The rejection SHALL be
    logged without leaking file contents.
13. Tests SHALL cover every registry entry in both slash and bare form, nested
    paths beneath each entry, a manifest that declares only reserved entries, and
    an end-to-end assertion that no reserved content is written into the receiving
    sandbox. Requirement 16 AC 4 remains binding: `previous_run` is short-circuited
    where redundant, not retired, so its guard SHALL remain active.

---

### Requirement 19: Version and chain provenance are durably auditable

**User Story:** As an operator supporting a user, I want a durable, queryable
record of what Git and chain operations actually happened, so that a version or
chain question can be answered after the SSE stream is gone.

#### Acceptance Criteria

*(closes SGV2-GAP-020)*

1. Every operation below SHALL produce a durable, owner/workspace-scoped audit
   record: terminal snapshot commit; internal run ref creation, idempotent
   no-op, or conflict; visible tag creation; `git_tag` mapping persistence;
   published-status transition during finalization; chain source selection with
   the resolved ref and provenance class; chain payload installation into
   `.context/`; chain refusal with its reason class; legacy payload migration to
   `.chain-legacy/`; recovery and crash-reconciliation commits; fragment-merge and
   merge-agent commits; blocked-commit events; and restore (already required by
   Requirement 9 AC 11).
2. Success SHALL be recorded, not only failure. An operation that only emits a
   transient event or a log line SHALL NOT be considered audited.
3. `post_commit` SHALL have at least one concrete registered observer that writes
   the audit record. AC 2 of Requirement 11 remains binding: `post_commit` stays
   observation-only and SHALL NOT alter run control flow, and an observer failure
   SHALL NOT roll back the commit.
4. Each record SHALL carry at minimum: actor identity, owner id, workspace id
   where applicable, logical run id, revision root id, workflow id, operation
   class, outcome, timestamp, and the relevant Git identifiers — commit id, ref
   name, tag name, and source ref — plus a generic reason class on failure.
5. Records SHALL contain no file contents, diffs, prompts, model output, secrets,
   or PII, per Requirement 15 AC 11. A reason SHALL be a bounded classifier, not
   free-form text carrying user content.
6. Chain provenance SHALL be reconstructable in both directions from the audit
   records plus the persisted `source_run_id`: given a run, which source ref fed
   it; given a source run, which children consumed it.
7. Audit writes SHALL reuse the existing owner-scoped store boundary and SHALL
   fail closed on an authorization error rather than writing an unscoped record.
   Persistence shape SHALL follow Requirement 15 AC 5 and AC 10.
8. A declared retention policy SHALL exist for these records, and support queries
   SHALL be scoped by owner. Cross-owner audit reads SHALL be impossible through
   any product surface.
9. Tests SHALL prove that a completed run, a degraded run with a blocked payload,
   a legacy chain read, a refused chain launch, a restore, and a crash-recovered
   run each leave the expected owner-scoped records; that no record contains
   payload bytes; and that a cross-owner read is refused.

---

### Requirement 20: Failure and provenance events survive reconnect and render accessibly

**User Story:** As a user who reconnected or came back later, I want to learn that
my chain source was omitted or that version creation failed, so that a degraded
run is never silently indistinguishable from a healthy one.

#### Acceptance Criteria

*(closes SGV2-GAP-021)*

1. `chain_context_unavailable` and `run_finalization_failed` SHALL have declared
   event schemas carrying, at minimum: event type, logical run id, a bounded
   machine-readable reason code, a client-safe human-readable message, and the
   affected artifact class. They SHALL NOT carry file contents, diffs, secrets,
   internal paths, another owner's run id, or a raw exception string.
2. Both event types SHALL be persisted with the run's durable event history and
   SHALL be replayed on SSE reconnect through the existing down-channel replay
   mechanism, in their original order relative to other run events. A user who was
   disconnected when the event fired SHALL still receive it.
3. Both event types SHALL also be projected into durable run state so they remain
   discoverable after the stream ends and after a page reload — at minimum a
   reason code and message reachable from the run-detail projection, sourced from
   the finalization record for `run_finalization_failed` and from the chain
   provenance record for `chain_context_unavailable`.
4. The chain refusal reasons introduced by Requirement 6 AC 17–19 — source
   running, source not yet finalized, source non-chainable, source payload
   missing or corrupt — SHALL be distinct reason codes so the frontend can show a
   correct and actionable message rather than one generic failure.
5. The frontend SHALL render both event types in the run surface with the run's
   existing error/warning presentation: an accessible, non-color-only indicator, a
   programmatically associated message, and keyboard-reachable detail. A degraded
   run SHALL be visually and semantically distinguishable from a completed run.
6. Each rendered failure SHALL offer the correct next action: retry for a
   transient not-yet-finalized source; choose another source for a non-chainable
   or missing source; contact-support framing plus the reason code for
   `run_finalization_failed`. The UI SHALL NOT offer an action the server will
   refuse.
7. The events SHALL NOT be rendered as a chat message from an agent, since they
   are engine facts rather than model output.
8. Rendering SHALL be resilient to an unknown reason code — the frontend SHALL
   fall back to the generic message rather than crashing or rendering an empty
   state, which also satisfies the rollback-reader tolerance of Requirement 17
   AC 4.
9. Tests SHALL cover, for each event type: live delivery; delivery via reconnect
   after a disconnect that spans the event; presence in the run-detail projection
   after a full reload; correct reason-code-to-message mapping for every reason
   code in AC 4; unknown-reason fallback; and the accessible rendering
   assertions of AC 5.

---

### Requirement 21: Chain launch, lineage, and source selection are explicit in the product surface

**User Story:** As a user chaining one workflow into another, I want to see which
run I chained from and what state it was in, so that chaining is a deliberate
choice rather than an invisible side effect.

#### Acceptance Criteria

##### Lineage is visible and proven *(closes SGV2-GAP-004, frontend half)*

1. A run launched with an authorized `source_run_id` SHALL display its chain
   relationship in the run detail and revision-family surfaces, driven by the API
   projection of Requirement 15 AC 8 rather than by client-side inference.
2. The indicator SHALL name the source workflow and the selected version — the
   visible tag when one exists, otherwise a non-guessable label such as the
   source run's short id plus its published status. It SHALL NOT display an
   internal run ref.
3. Chain lineage SHALL remain distinct from revision lineage in the UI, matching
   the two-graph rule of V2-Q1: a revision SHALL NOT be labeled chained, and a
   chained run SHALL NOT be shown inside its source's revision family.
4. A frontend test SHALL prove a chained run renders the chain relationship, and
   an API test SHALL prove the persisted edge and projection. Together they close
   the v1 Requirement 22 AC 11 acceptance test, which had never had a writer.

##### Legacy text-marker transition *(closes SGV2-GAP-005)*

5. New launches SHALL send only `source_run_id`. The frontend SHALL stop
   assembling the `=== CONTEXT FROM PREVIOUS PIPELINE ... ===` block, and no new
   run SHALL receive chain context both as `.context/` files and as an input text
   block.
6. Client-held chain state SHALL be cleaned up once: any stored chain context
   block in `sessionStorage`, `localStorage`, or in-memory launch state SHALL be
   dropped on first load of the new frontend under a versioned storage key, so a
   stale open tab cannot resubmit a legacy block. Cleanup SHALL be idempotent and
   SHALL NOT discard unrelated draft input the user still needs.
7. Historical runs whose stored input already contains the marker SHALL keep
   rendering as they do today. The input parser SHALL continue to recognize the
   marker for display of existing runs and SHALL NOT be removed while such runs
   are retained.
8. A chained run SHALL be presented as file-based chain context, not as legacy
   text context, whenever a `.context/` chain payload was installed — even if a
   legacy marker is present in historical input for an older run in the same
   family.
9. Mixed-deploy behavior SHALL be explicit: a new frontend against an older
   backend SHALL be supported by degrading to no chain context with the
   Requirement 20 AC 4 reason rather than silently launching without provenance;
   an older frontend against a new backend SHALL have its legacy text block
   rejected or ignored per Requirement 13 AC 11, never combined with the file
   payload. Any unsupported combination SHALL be named as unsupported rather than
   left undefined.
10. Tests SHALL prove a new launch sends no text context block, that a stale
    stored block is cleaned up exactly once, that a historical marker-bearing run
    still renders, and that no launch produces duplicate chain context.

##### Non-success sources are selectable but honest *(closes SGV2-GAP-017)*

11. The set of selectable chain sources SHALL be explicit. `completed` sources
    SHALL be offered normally. `failed`, `cancelled`, `degraded`, and `diverted`
    sources SHALL be offerable only when their finalization record reports
    `payload_chainable = true`; a non-chainable source SHALL be shown as
    unavailable with its reason rather than offered and then refused.
12. Selecting a non-success source SHALL surface a warning before launch stating
    the source's published status and that its output may be incomplete. The
    warning SHALL be an accessible, acknowledged element, not color alone, and
    SHALL name the status rather than a generic caution.
13. Internal run refs SHALL remain hidden from the UI. A non-success source SHALL
    be identified by its published status and short id; the absence of a `vN` tag
    SHALL be presented as "no version tag", never as an error and never by
    exposing a ref name.
14. The receiving run's surface SHALL show the source's published status as
    recorded in the installed `.context/summary.md`, so a downstream reader can
    tell that its input came from a non-success run. Agents SHALL learn the same
    fact from `summary.md` per Requirement 4 AC 7 rather than from a bespoke
    channel.
15. Tests SHALL cover source-list composition for all five terminal statuses plus
    a non-chainable source, the warning presentation and acknowledgement, absence
    of any internal ref string in the rendered output, and the receiving run's
    display of a non-success source status.
