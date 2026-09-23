# Sandbox Git Versioning V2 — Coverage Gap Handoff

> **Status:** Open analysis handoff  
> **Scope:** Requirements and design gaps only; this is not an implementation task list.  
> **Primary target:** `.kiro/specs/sandbox-git-versioning-v2/requirements.md`  
> **Last audited:** 2026-09-09

## Purpose

This document records the behavior that remains missing, contradictory, or too
ambiguous after comparing the original sandbox Git versioning requirements, the
new v2 requirements, the canonical specification, and every report under
`specs/019-sandbox-git-versioning/reports/`.

Another agent should be able to start from this file, verify that a gap still
exists, expand the relevant requirement acceptance criteria, and then carry the
resolved contract into `design.md` and `tasks.md` without repeating the complete
blast-radius audit.

Do not treat a checked v1 task or current implementation as proof that a gap is
closed. Close a gap only when the authoritative requirement is unambiguous and
its intended verification is identified.

## Source Corpus Read

All files below were included in the audit:

- `.kiro/specs/sandbox-git-versioning/requirements.md`
- `.kiro/specs/sandbox-git-versioning-v2/requirements.md`
- `specs/019-sandbox-git-versioning/spec.md`
- `specs/019-sandbox-git-versioning/reports/00-START-HERE.md`
- `specs/019-sandbox-git-versioning/reports/01-layers.md`
- `specs/019-sandbox-git-versioning/reports/02-blast-radius.md`
- `specs/019-sandbox-git-versioning/reports/03-phasing.md`
- `specs/019-sandbox-git-versioning/reports/04-walkthrough.md`

## Interpretation Rule

The v2 introduction says:

- **Retain**: the v1 requirement remains binding.
- **Amend**: the v1 requirement remains binding with v2 additions.
- **Replace**: v2 is the sole authority for that behavior.

This matters for gaps `SGV2-GAP-001`, `002`, and `018`: useful v1 safety
criteria were marked **Replace**, so they are no longer binding unless v2
restates them.

## Priority Legend

- **P0 — ship blocker/security or contract contradiction**
- **P1 — required correctness, recovery, or user-flow closure**
- **P2 — observability, migration clarity, or lower-frequency edge case**

## Gap Index

| ID | Priority | Main layers | Summary |
|---|---:|---|---|
| SGV2-GAP-001 | P0 | Git, sandbox, API, security | Reserved-path history/listing/deliverable protections were superseded |
| SGV2-GAP-002 | P0 | Context provider, security | Reserved-prefix seeding guard was dropped |
| SGV2-GAP-003 | P0 | Compiler, provider, launch | Manifest-declared chain activation gate is missing |
| SGV2-GAP-004 | P1 | API, persistence, frontend | Chain lineage persistence and “Chained” UI proof are incomplete |
| SGV2-GAP-005 | P1 | Frontend, rollout | Legacy text-marker and stale-session transition is unspecified |
| SGV2-GAP-006 | P1 | Upload API, locking, sandbox | Uploads are not covered by family-write serialization |
| SGV2-GAP-007 | P0 | Git, hooks, fan-out, restore | Hook and secret-scan coverage does not include every commit path |
| SGV2-GAP-008 | P0 | Security, binary outputs | Diff-based scanning does not define binary payload inspection |
| SGV2-GAP-009 | P1 | Fan-out, recovery, operations | Abrupt crash recovery during a merge/worktree operation is undefined |
| SGV2-GAP-010 | P1 | Kernel, SSE, chaining | Terminal publication ordering covers only completed runs |
| SGV2-GAP-011 | P0 | Finalizer, security, refs | Secret-blocked payload conflicts with the every-terminal-ref rule |
| SGV2-GAP-012 | P1 | Finalizer, persistence | Late finalization failure can make committed status metadata untruthful |
| SGV2-GAP-013 | P1 | Payload schema, tags | `summary.md` cannot truthfully record a tag created after its commit |
| SGV2-GAP-014 | P1 | Git refs, recovery | Internal refs are called immutable but specified as updateable |
| SGV2-GAP-015 | P1 | Compatibility, chaining | Legacy tagged runs commonly have no internal run ref |
| SGV2-GAP-016 | P1 | Launch, chaining | Chaining from a still-running source has no policy |
| SGV2-GAP-017 | P2 | Frontend, history, chaining | Non-success terminal runs are chainable but have no defined UX |
| SGV2-GAP-018 | P1 | Sweeper, gates, revision family | Active/gated descendant TTL protection is no longer explicit |
| SGV2-GAP-019 | P2 | Root resolution, API | Parent-cycle detection has no required outcome |
| SGV2-GAP-020 | P1 | Audit, persistence, operations | Successful Git and chain provenance has no durable audit sink |
| SGV2-GAP-021 | P1 | SSE replay, frontend, support | New failure events have no reconnect or rendering contract |

---

## Detailed Gaps

### SGV2-GAP-001 — Reserved-path protections were superseded

**Priority / layers:** P0 — Git, sandbox, API, deliverables, public sharing,
security.

**Coverage hole**

The v2 supersession matrix marks v1 Requirements 8, 9, and 44 as **Replace**.
V2 then specifies the special force-tracked `.chain/` allowlist but does not
restate the protections for all other reserved paths. This can be interpreted as
removing the binding requirements that keep `.git/`, `.gitignore`, `skills/`,
`.uploads/`, `.logs/`, `.verify/`, `.browser/`, `.agents/`, and `.context/` out
of inappropriate history, listings, deliverables, zips, and shared output.

**Requirement/report references**

- V2 supersession matrix: `8–9, 20–21, 44 → Replace`
- V2 Requirement 4 AC 10–13; Requirement 7 AC 4; Requirement 8 AC 7
- V1 Requirements 8, 9, and 44
- Canonical `spec.md`: FR-007, FR-008, FR-008a, FR-008b, FR-035
- `reports/01-layers.md`: L2, L4, L8
- `reports/02-blast-radius.md`: L2, L4, L8, cross-cutting export paths

**Likely implementation/test surfaces**

- `backend/app/agents/runtime/local.py` — `_GITIGNORE_PATHS`, Git staging
- `backend/app/agents/sandbox.py` — deliverable exclusions and `list_files`
- `backend/app/api/run_files.py` — list/read/zip behavior
- `backend/app/main.py` and `backend/app/api/runs.py` — public share output path
- `backend/tests/agents/test_sandbox_deliverable.py`

**Required closure**

Change the supersession disposition or add v2 acceptance criteria that preserve
all prior exclusions while making exactly the three validated flat `.chain`
files the sole force-tracked exception. Require history, listing, deliverable,
zip, and public-share tests.

---

### SGV2-GAP-002 — Reserved-prefix seeding guard was dropped

**Priority / layers:** P0 — context providers, sandbox boundary, security.

**Coverage hole**

V1 Requirement 21 is marked **Replace**, but v2 does not restate the rule that
`previous_run.seed_files.from_run` must reject reserved prefixes. V2 only says
that redundant `previous_run` seeding is short-circuited; future manifests can
still accidentally request reserved engine content.

**Requirement/report references**

- V2 supersession matrix: `20–21 → Replace`
- V2 Requirement 13 ledger row 25; Requirement 16 AC 4
- V1 Requirement 21
- Canonical `spec.md`: FR-019
- `reports/01-layers.md`: L9 `previous_run` reserved-prefix guard
- `reports/02-blast-radius.md`: L9

**Likely implementation/test surfaces**

- `backend/agents/capabilities/context_providers/previous_run.py`
- `backend/agents/capabilities/context_providers/chain_context.py`
- `backend/tests/agents/test_context_providers.py`
- `backend/tests/agents/test_revision_gating.py`

**Required closure**

Restore an explicit compile/runtime rejection list covering every reserved
prefix, including `.chain/`, `.chain-legacy/`, `.context/`, `.uploads/`,
`.logs/`, `.verify/`, `.browser/`, `.agents/`, `.git/`, and `skills/` as
applicable.

---

### SGV2-GAP-003 — Manifest-declared chain activation gate is missing

**Priority / layers:** P0 — compiler, compiled workflow, context provider,
launch authorization.

**Coverage hole**

V2 defines how an exact source payload is read but never requires the workflow
to declare that it accepts chain context. The provider could therefore activate
solely because `source_run_id` is present, reopening the same accidental
cross-run-read class that the declared `previous_run` gate was designed to
prevent.

**Requirement/report references**

- V2 Requirements 2 and 6; no explicit declared activation criterion
- V1 Requirement 22 AC 3 and AC 9
- Canonical `spec.md`: FR-021 and FR-026
- `reports/01-layers.md`: L6 compiler, L9 context provider
- `reports/02-blast-radius.md`: L6 declared chain flag

**Likely implementation/test surfaces**

- `backend/agents/workflows/compiler.py`
- `backend/agents/workflows/plan.py`
- `backend/agents/workflows/*/workflow.yaml`
- `backend/agents/capabilities/context_providers/chain_context.py`
- manifest/compiler and context-provider tests

**Required closure**

Require a compiled, manifest-declared chain capability. Prove that a stray
`source_run_id` on a workflow without that declaration performs no cross-run
read, while a declared workflow receives the authorized exact-ref payload.

---

### SGV2-GAP-004 — Chain lineage persistence and UI proof are incomplete

**Priority / layers:** P1 — launch API, persistence, response schemas, frontend
history.

**Coverage hole**

V2 calls `source_run_id` the chain edge but does not explicitly require the
launch transaction to persist it or verify the existing “Chained” lineage
indicator. The implementation could consume a source id transiently and still
leave persisted lineage broken.

**Requirement/report references**

- V2 Requirement 6 AC 1; Requirement 15 AC 1
- V1 Requirement 22 AC 1, AC 2, and AC 11
- Canonical `spec.md`: FR-020
- `reports/01-layers.md`: L3–L5
- `reports/02-blast-radius.md`: L4/L5 source writer

**Likely implementation/test surfaces**

- `backend/app/api/run_commands.py` — `_launch_run_core`
- `backend/app/models/workflow.py` — `WorkflowRun.source_run_id`
- `backend/app/api/runs.py` — family/run response projection
- `frontend/src/components/history/RunDetailPage.tsx`
- `frontend/src/components/history/RevisionFamilyView.tsx`

**Required closure**

Require atomic persistence of the authorized source id at launch and an API plus
frontend test proving that the new run displays the correct chain relationship.

---

### SGV2-GAP-005 — Legacy text-marker and stale-session transition is unspecified

**Priority / layers:** P1 — frontend composition, parser, session state,
mixed-version rollout.

**Coverage hole**

V2 ledger row 24 says frontend-enriched chain text is removed, but does not say
how old `=== CONTEXT FROM PREVIOUS PIPELINE ... ===` messages, stale browser
tabs, `sessionStorage` values, or mixed frontend/backend deployments behave.
The old marker may survive, duplicate file context, or make a clean chain appear
as legacy text context.

**Requirement/report references**

- V2 Requirement 13 ledger row 24; Requirement 17 compatibility/UI phase
- V1 Requirement 22 AC 10
- Canonical `spec.md`: FR-027
- `reports/01-layers.md`: L1
- `reports/02-blast-radius.md`: L1

**Likely implementation/test surfaces**

- `frontend/src/components/layout/DashboardLayout.tsx` —
  `handleChainPipeline`, `handleChainFromHistory`
- `frontend/src/lib/runInput.ts` — `parseRunInput`
- `frontend/src/components/workflow/LaunchWizard.tsx` —
  `chain.context_block`, `chain.source_run_id`
- `frontend/src/lib/runInput.test.ts`
- `frontend/src/components/workflow/LaunchWizard.test.tsx`

**Required closure**

Specify new-launch behavior, one-time cleanup of stale storage, compatibility for
rendering historical marker-bearing runs, and supported/unsupported mixed-deploy
behavior. Add tests proving new launches never send duplicate text context.

---

### SGV2-GAP-006 — Uploads are not covered by family-write serialization

**Priority / layers:** P1 — upload API, revision-family lock, sandbox writes,
restore/finalization races.

**Coverage hole**

V2 root-resolves all file routes, but Requirement 10's lock enumeration omits
`POST /api/runs/{run_id}/files`. The current endpoint has a per-sandbox manifest
lock for concurrent upload deduplication, not the revision-family lock or a
policy for upload versus active agents, restore, trace/payload finalization, and
snapshot commits.

**Requirement/report references**

- V2 Requirement 2 AC 7; Requirement 10 AC 1–3
- Canonical `spec.md`: component map L4
- `reports/01-layers.md`: L4 four file routes
- `reports/02-blast-radius.md`: L4

**Likely implementation/test surfaces**

- `backend/app/api/run_files.py` — `upload_files`, `_manifest_lock`
- revision-family resolver/lock introduced by v2
- `backend/app/agents/sandbox.py`
- upload API, restore-race, and finalizer-race tests

**Required closure**

Decide whether uploads are accepted, queued, or rejected during each run state.
Require one lock ordering and atomic visibility rule, then test upload-vs-upload,
upload-vs-agent, upload-vs-restore, and upload-vs-finalizer races.

---

### SGV2-GAP-007 — Hook and secret-scan coverage excludes several commit paths

**Priority / layers:** P0 — Git runtime, hooks, fan-out, restore, security.

**Coverage hole**

V1 brackets step-boundary commits; v2 explicitly scans recovery and terminal
payload commits. Neither contract clearly requires `pre_commit`, mandatory
secret scanning, and `post_commit` for spawn-point commits, worker-branch
commits, per-fragment merge commits, merge-agent commits, restore commits, or
retained cancelled-worker branches. Scanning only the later boundary diff can
miss secrets already committed in reachable history.

**Requirement/report references**

- V2 Requirements 4 AC 12, 5 AC 3, 9, 10 AC 4, 11, and 12
- V1 Requirements 12, 25, and 41
- Canonical `spec.md`: FR-035, FR-052–FR-060
- `reports/01-layers.md`: L7/L8
- `reports/02-blast-radius.md`: L8 secret scanning

**Likely implementation/test surfaces**

- `backend/app/agents/runtime/local.py` — all commit/merge/restore helpers
- `backend/agents/execution_engine/fanout.py`
- `backend/agents/capabilities/merge/git_3way.py`
- `backend/agents/execution_engine/engine.py`
- `backend/agents/capabilities/hooks/secret_scan.py`
- real-Git tests for every commit type and retained branch

**Required closure**

Inventory every Git object-creating path and require one security-gated commit
primitive or equivalent mandatory scan at each path. Tests must prove a secret
cannot remain reachable from a tag, internal ref, base branch, or retained
worker branch.

---

### SGV2-GAP-008 — Binary payload secret inspection is undefined

**Priority / layers:** P0 — binary deliverables, chain payload, secret scanner.

**Coverage hole**

V2 requires byte-exact binary outputs such as PPTX and says the staged payload
passes the normal staged-diff secret scan. A Git textual diff commonly reports
only “binary files differ,” so the requirements do not prove that embedded
secrets are inspected before permanent history and cross-workflow chaining.

**Requirement/report references**

- V2 Requirement 4 AC 8 and AC 12
- V2 Requirement 6 AC 8 and AC 12
- Canonical `spec.md`: FR-035 and FR-060
- `reports/02-blast-radius.md`: L8 secret-scanning risk

**Likely implementation/test surfaces**

- `backend/agents/capabilities/hooks/secret_scan.py`
- staged-diff generation in `backend/app/agents/runtime/local.py`
- chain-payload writer/finalizer in `backend/agents/execution_engine/engine.py`
- binary PPTX chain tests

**Required closure**

Define whether binary outputs are content-scanned, blocked by type/size, scanned
through safe extraction, or explicitly excluded under an approved policy. Add a
binary fixture whose embedded marker must be detected or deliberately accepted.

---

### SGV2-GAP-009 — Abrupt fan-out crash recovery is undefined

**Priority / layers:** P1 — fan-out runtime, Git state, resume, operations.

**Coverage hole**

Cooperative cancellation is specified, and ordinary dirty-tree recovery is
specified. A process death while `MERGE_HEAD`, an index lock, registered worker
worktrees, or unmerged worker branches exist is only required to fail
explicitly; no repair/quarantine/resume state machine is defined.

**Requirement/report references**

- V2 Requirements 10 AC 6–8 and 12 AC 9–10
- Canonical `spec.md`: FR-059 and FR-062
- `reports/02-blast-radius.md`: cross-cutting crash consistency
- `reports/04-walkthrough.md`: flows not exercised

**Likely implementation/test surfaces**

- `backend/agents/execution_engine/fanout.py`
- `backend/app/agents/runtime/local.py` — merge/worktree lifecycle
- `backend/agents/execution_engine/engine.py` — resume/finalization
- run recovery startup path and crash-injection tests

**Required closure**

Define detection and recovery for each persistent Git state, including when to
abort, continue, quarantine, retain branches, or require operator action. Prove
idempotent restart at crash points before, during, and after each fragment merge.

---

### SGV2-GAP-010 — Terminal publication ordering covers only completed runs

**Priority / layers:** P1 — execution kernel, SSE, REST chain launch, race
behavior.

**Coverage hole**

V2 delays only the external `completed` event until finalization succeeds.
Cancelled, failed, degraded, and diverted runs must also receive internal refs
and are intentionally chainable, but their terminal events may be observed
before those refs and payloads exist.

**Requirement/report references**

- V2 Requirement 5 AC 3–5 and AC 10
- V2 Requirement 6 AC 4, AC 10, and AC 12
- V2 Requirement 11 AC 6–8
- Canonical `spec.md`: FR-016 and FR-061

**Likely implementation/test surfaces**

- `backend/agents/execution_engine/engine.py` — terminal event sites/finalizer
- `backend/app/api/run_engine.py`
- `backend/app/api/run_stream.py`
- `backend/app/api/run_commands.py` — chain launch
- terminal-event/immediate-chain race tests

**Required closure**

Require every externally visible terminal event to follow required terminal
snapshot/ref completion, or make chain launch wait/retry against a durable
finalization state. Test immediate chaining after every terminal status.

---

### SGV2-GAP-011 — Secret-blocked payload conflicts with every-terminal-ref

**Priority / layers:** P0 — finalizer, security policy, payload, Git refs.

**Coverage hole**

V2 says a secret-blocked `.chain` payload remains uncommitted and degrades the
run. It also says every degraded run receives an internal ref to a terminal
snapshot, whose definition includes the flat payload. Both cannot be true
without an explicit safe fallback or non-chainable terminal state.

**Requirement/report references**

- V2-Q3 and V2-Q5
- V2 terminal-snapshot glossary
- V2 Requirement 4 AC 11–12
- V2 Requirement 5 AC 5–10
- V2 Requirement 6 AC 4 and AC 10
- Canonical `spec.md`: FR-035 and FR-060

**Likely implementation/test surfaces**

- terminal finalizer in `backend/agents/execution_engine/engine.py`
- `backend/agents/capabilities/hooks/secret_scan.py`
- Git ref helper in `backend/app/agents/runtime/local.py`
- run status/error persistence

**Required closure**

Choose one explicit outcome: safe metadata-only snapshot, no internal ref plus a
non-chainable reason, correction/retry workflow, or another security-approved
model. Test crash/retry and prove the secret never becomes reachable.

---

### SGV2-GAP-012 — Late finalization failures can make status metadata untruthful

**Priority / layers:** P1 — finalizer state machine, payload schema, run
persistence.

**Coverage hole**

The flat payload is built with the run's terminal status before commit/ref/tag/DB
operations. A later required operation can change the database status from
`completed` to `degraded`, leaving an already-created terminal commit,
`summary.md`, and possibly the flushed terminal log describing the earlier
status.

**Requirement/report references**

- V2 Requirement 4 AC 7
- V2 Requirement 5 AC 1–4 and AC 9–10
- V2 Requirement 15 AC 6
- Canonical `spec.md`: FR-012, FR-014, FR-016, FR-061

**Likely implementation/test surfaces**

- `backend/agents/execution_engine/engine.py` finalizer and trace flush
- `backend/agents/execution_engine/run_log.py`
- WorkflowRun status persistence
- tag/DB/ref failure-injection tests

**Required closure**

Define candidate execution outcome separately from final published status, or
define a compensating snapshot protocol. Require DB status, summary, terminal
log, internal ref, and visible tag to converge after every failure point.

---

### SGV2-GAP-013 — `summary.md` cannot truthfully record a later-created tag

**Priority / layers:** P1 — payload schema, finalization order, tags.

**Coverage hole**

V2 Requirement 4 asks `summary.md` to include the intended/created visible tag.
Requirement 5 commits that summary before the visible tag is created. Updating
the summary afterward changes the commit the tag is meant to identify.

**Requirement/report references**

- V2 Requirement 4 AC 7
- V2 Requirement 5 AC 3 steps 4–8
- V2 Requirement 5 AC 6
- Canonical `spec.md`: FR-012, FR-013, FR-036

**Likely implementation/test surfaces**

- flat payload writer in `backend/agents/execution_engine/engine.py`
- tag/ref helpers in `backend/app/agents/runtime/local.py`
- summary schema and exact-tag tests

**Required closure**

Define separate immutable fields such as `intended_tag` and a deterministic tag
name, remove the claim that the in-commit summary proves tag creation, or choose
a different non-circular protocol. Do not move a published tag to repair text.

---

### SGV2-GAP-014 — Internal refs are called immutable but specified as updateable

**Priority / layers:** P1 — Git refs, idempotency, corruption recovery.

**Coverage hole**

V2 calls `refs/ideaflow/runs/{run_id}` immutable but orders the finalizer to
“create/update” it. It does not define behavior when the ref already exists and
points at a different commit.

**Requirement/report references**

- V2-Q3 and internal-run-ref glossary
- V2 Requirement 5 AC 3 step 7 and AC 7–8
- V2 Requirement 6 AC 3–5
- V2 Requirement 15 AC 4 and AC 6

**Likely implementation/test surfaces**

- `backend/app/agents/runtime/local.py` Git-ref helpers
- terminal finalizer
- source-ref consistency checks
- ref-collision/corruption tests

**Required closure**

Require create-only compare-and-set semantics: missing ref may be created,
existing same-target ref is idempotent, and existing different-target ref fails
closed without moving it. Specify operator/recovery behavior.

---

### SGV2-GAP-015 — Legacy tagged runs commonly have no internal run ref

**Priority / layers:** P1 — rollout compatibility, source selection, legacy
payload fallback.

**Coverage hole**

V2 requires a completed source tag to resolve to the same commit as its internal
run ref before reading. Pre-v2 runs can have a visible tag and a live nested
payload but no `refs/ideaflow/runs/{run_id}` ref. The legacy fallback is therefore
unreachable for the population it is intended to support.

**Requirement/report references**

- V2 Requirement 6 AC 3–5
- V2 Requirement 7 AC 5–8
- V2 Requirement 17 AC 3–4 and AC 7
- Canonical `spec.md`: FR-016 legacy nested shape

**Likely implementation/test surfaces**

- `backend/agents/capabilities/context_providers/chain_context.py`
- Git tag/ref helpers in `backend/app/agents/runtime/local.py`
- launch/source authorization in `backend/app/api/run_commands.py`
- legacy compatibility tests

**Required closure**

Define a feature-detected legacy branch: authorize by the owned source row,
validate its exact stored tag without requiring a nonexistent internal ref, and
then use only the specified legacy fallback. Never infer latest tag or `HEAD`.

---

### SGV2-GAP-016 — Chaining from a still-running source has no policy

**Priority / layers:** P1 — launch API, source eligibility, terminal finalization.

**Coverage hole**

V2 authorizes `source_run_id` but does not require the source to be terminal.
A running source has no terminal internal ref or complete payload; treating it
as merely “unavailable” can start a downstream run with silently empty context.

**Requirement/report references**

- V2-Q3
- V2 Requirement 5 AC 5
- V2 Requirement 6 AC 1–4 and AC 10
- `reports/04-walkthrough.md`: interaction coverage boundaries

**Likely implementation/test surfaces**

- `backend/app/api/run_commands.py` chain launch
- `backend/agents/capabilities/context_providers/chain_context.py`
- frontend chain actions in `DashboardLayout.tsx`
- source-state eligibility tests

**Required closure**

Choose reject, wait, snapshot-in-progress, or another explicit policy. The
normal graceful-degradation rule must not silently convert “source still
running” into an empty chain payload.

---

### SGV2-GAP-017 — Non-success chain-source UX is undefined

**Priority / layers:** P2 — history UI, chain launch UX, provenance warnings.

**Coverage hole**

V2 deliberately makes failed, cancelled, degraded, and diverted terminal runs
addressable through internal refs and tests chaining from an untagged failed
run. It does not say how users discover/select those runs, what warning is
shown, or how their terminal status and provenance are presented to the next
workflow.

**Requirement/report references**

- V2 Requirement 5 AC 5
- V2 Requirement 6 AC 4, AC 7, and AC 12
- V2 Requirement 16 AC 1
- V2 Requirement 17 AC 7 and AC 10

**Likely implementation/test surfaces**

- `frontend/src/components/history/RunDetailPage.tsx`
- `frontend/src/components/history/RevisionFamilyView.tsx`
- chain actions in `frontend/src/components/layout/DashboardLayout.tsx`
- run-family/source eligibility API

**Required closure**

Specify selectable statuses, warning copy/data, whether the internal ref remains
hidden, and how `summary.md` terminal status appears in the receiving run.

---

### SGV2-GAP-018 — Active/gated descendant TTL protection is no longer explicit

**Priority / layers:** P1 — sweeper, revision-family resolver, human gates.

**Coverage hole**

V1 Requirement 2 explicitly protected a shared root when the root row was
terminal but a descendant was active. V2 marks it replaced and only says the
common resolver supplies “sweeper protection.” It no longer states the
protected-set algorithm, the overnight human-gate case, or a behavioral test.

**Requirement/report references**

- V2 supersession matrix: v1 Requirements 1–5 → Replace
- V2 Requirement 2 AC 7
- V2 Requirement 17 AC 2
- V1 Requirement 2
- Canonical `spec.md`: FR-003
- `reports/02-blast-radius.md`: cross-cutting gate pause versus TTL sweeper

**Likely implementation/test surfaces**

- `backend/app/agents/sandbox.py` — `sweep_expired`
- `backend/app/main.py` — periodic sweep/protected-run query
- canonical revision-root resolver
- sweeper tests with terminal root and active/gated descendants

**Required closure**

Restate that every non-terminal descendant protects its resolved revision root,
including durable human-gate pauses. Require the sweeper fix to land atomically
with root re-keying and add a TTL-expiry behavioral test.

---

### SGV2-GAP-019 — Parent-cycle detection has no required outcome

**Priority / layers:** P2 — resolver, API error behavior, corruption handling.

**Coverage hole**

V2 requires a visited-set guard but does not say what result or error follows a
cycle. V1 selected the last unique node; other v2 ancestry failures now fail
closed. Different callers can therefore choose different roots for the same
corrupt family.

**Requirement/report references**

- V2 Requirement 2 AC 4–5
- V1 Requirement 1 AC 1 and AC 4
- Canonical `spec.md`: FR-001 and threat T-A-04
- `reports/01-layers.md`: L4 `_compute_root_ids` prior art

**Likely implementation/test surfaces**

- canonical app-side revision-root resolver introduced by v2
- `backend/app/api/runs.py` — `_compute_root_ids`
- launch, file-route, sweeper, restore, and family-lock callers
- cycle/cross-owner/missing-ancestor tests

**Required closure**

Choose one fail-closed outcome and require all callers to use it. Specify generic
client behavior and server-side diagnostics without exposing another owner's
run id.

---

### SGV2-GAP-020 — Successful Git and chain provenance has no durable audit sink

**Priority / layers:** P1 — persistence, hooks, operations, supportability.

**Coverage hole**

V2 requires a durable audit event only for restore. It does not require durable
records for step/merge/terminal commits, selected source ref, chain payload
installation, internal-ref creation, tag creation, or source-to-child chain
provenance. `post_commit` is observation-only but no concrete observer/sink is
required.

**Requirement/report references**

- V2 Requirement 5 AC 3 and AC 11
- V2 Requirement 9 AC 11
- V2 Requirement 11 AC 2 and AC 7
- V2 Requirement 15 AC 6
- Canonical `spec.md`: FR-060 `post_commit` audit/lineage use
- `reports/02-blast-radius.md`: cross-cutting observability item 7

**Likely implementation/test surfaces**

- `backend/app/models/subagent_run.py`
- `backend/app/models/wave_run.py`
- `backend/app/models/exec_runs.py`
- `backend/agents/authz.py` — owner/workspace-scoped store operations
- hook registry/observers and audit endpoints

**Required closure**

Define the minimum owner/workspace-scoped audit schema or ArtifactRef event for
each operation, with commit/ref identifiers but no file contents, prompts,
secrets, or PII. Specify retention and reconnect/support query behavior.

---

### SGV2-GAP-021 — New failure events have no reconnect or rendering contract

**Priority / layers:** P1 — SSE persistence/replay, run detail, frontend error
presentation.

**Coverage hole**

V2 introduces `chain_context_unavailable` and `run_finalization_failed`, but does
not require them to survive reconnect, appear in durable run state, or render in
the frontend. A reconnecting user may see a degraded run without learning that
the selected source was omitted or that version creation failed.

**Requirement/report references**

- V2 Requirement 5 AC 10
- V2 Requirement 6 AC 10
- V2 Requirement 17 AC 10
- `reports/01-layers.md`: L2/L3 frontend transparency and SSE surfaces
- `reports/02-blast-radius.md`: observability and transparency concerns

**Likely implementation/test surfaces**

- `backend/app/api/run_stream.py`
- `backend/app/api/run_engine.py`
- durable event/run-error persistence
- `frontend/src/hooks/useRunStream.ts`
- `frontend/src/providers/RunConnectionProvider.tsx`
- run chat/detail/error components

**Required closure**

Specify event schema, persistence/replay behavior, run-detail projection, and
accessible frontend rendering with retry/remediation guidance. Test reconnect
after each failure rather than only the live SSE path.

---

## Already Covered — Do Not Reopen Without New Evidence

The audit found these areas adequately covered by v2 or retained v1
requirements:

- Parent-only revision ancestry versus independent `source_run_id` chaining
- Separate physical sandbox root and logical current-run id
- Exact `.logs/{current_run_id}.jsonl` source
- Flat `.chain/logs.jsonl`, `.chain/summary.md`, and one workflow output file
- Byte-safe exact-ref chain copying into flat `.context/` paths
- No `HEAD` or latest-tag source selection
- Legacy nested payload relocation outside flat `.chain/`
- Final status/output resolution before normal terminal payload creation
- Read-only version browsing without moving HEAD
- Restore as a family-locked forward commit
- Four fan-out conflict policies and cooperative cancellation behavior
- Prompt-policy governance preservation and the 30-row prompt-input ledger
- Retry/redo recipient rules
- No `has_git` DB column, no ref cache, and no agent-callable Git tool
- Existing import boundaries, SSE down-channel, REST up-channel, SC-001, and
  characterization-golden safeguards

## Suggested Next-Agent Workflow

1. Re-read the v2 supersession matrix before changing any requirement.
2. Validate each gap against the current working tree because the repository has
   substantial uncommitted implementation work.
3. Add or amend acceptance criteria in
   `.kiro/specs/sandbox-git-versioning-v2/requirements.md`.
4. Resolve contradictions before writing design; do not defer contradictory
   behavior to implementation tasks.
5. Create a normative component map in `design.md` covering every code surface
   named by the resolved gaps.
6. Add focused real-Git, real-DB, frontend, reconnect, crash-injection, and
   security tests to `tasks.md` as applicable.
7. Mark a gap closed here only with the requirement/design/task references that
   replaced it; do not delete historical rationale.

## Working-Tree Caution

- The repository previously contained substantial unrelated and uncommitted v1
  implementation work. Do not reset, stash, stage broadly, or use `git add .`.
- `.kiro/*` is ignored by the root `.gitignore`; Kiro spec files may not appear
  in ordinary `git status` output.
- This handoff does not authorize commits or deployment.
