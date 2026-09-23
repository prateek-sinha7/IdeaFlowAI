# Design Document: Sandbox Git Versioning v2

## Overview

V1 shipped nine reserved paths, a git-init'd sandbox, step-boundary commits, `vN`
tags, ref-scoped reads, and a `.chain/` payload writer. All of it exists on disk.
The problem is that the pieces are wired to the wrong values, in the wrong order,
through the wrong lineage edge — so the *contracts* v1 wrote down are not the
behaviour the code produces. V2 is a corrective delta, not a new feature.

Five defects are load-bearing and everything else follows from them:

| # | Defect (verified in source) | Consequence |
|---|---|---|
| D1 | `_find_chain_root` (`engine.py:518`) walks `source_run_id`, and its docstring says `parent_run_id` "must NEVER be walked here" | Revision families are keyed by the chaining edge. A chained run **shares its source's mutable sandbox**. Meanwhile `revision_ordinal` is computed from `parent_run_id` — the directory and the version number come from two different graphs. |
| D2 | `RunSandbox` carries one id (`sandbox.py:178`); callers pass the root id *as* `run_id` | `run_log_path` → `.logs/{root_id}.jsonl`. Every revision in a family appends to the **same** log file. `.verify/{root}/` and `.browser/{root}/` collide the same way. |
| D3 | `_fire_post_run` runs from the `finally:` at `engine.py:4120`; Step 5 starts at `:4168` — *after* it. `ectx.final_status` is stamped `"completed"` optimistically at `:4163` | The payload, the tag, and the `git_tag` DB write all happen **before** the real status, the `degraded` computation (`:4468`, `:4477`), and deliverable resolution (`:4215+`). |
| D4 | `.chain/` is entry 6 of `_GITIGNORE_PATHS` (`local.py:620-630`) and nothing force-stages it | The payload is in **no commit**. `vN` points at the last step-boundary commit. Chaining therefore reads the live tree, and every tag in a family exposes an identical (payload-free) tree. |
| D5 | `pre_commit` is fired with `payload=""` (`engine.py:3568-3574`) | `scan_for_secret("")` short-circuits on its first line. The mandatory secret scan **cannot block**. It only writes a `hook_runs` row with `outcome=continue`. |

Plus two absences the requirements treat as in-scope corrections, not new work:
there is **no restore endpoint anywhere** in the backend (a regex for
`@router.(post|get|put)` × `restore|revert|rollback|checkout` over all of
`backend/**/*.py` returns zero), and **no cross-process lock** guards a shared
sandbox — `_has_active_chain_revision` (`run_commands.py:3594`) is three plain
DB reads that fail *open*.

### What is reused rather than rebuilt

| Need | Existing mechanism | What v2 adds |
|---|---|---|
| Owner-scoped cross-run read | `ScopedStore.assert_owns` + `_scope_owner_ws` (`authz.py:120`) | Nothing. Chain eligibility calls it earlier; audit writes call it too. |
| Ref-scoped read without moving HEAD | `read_file_at_ref` / `list_files_at_ref` / `archive_at_ref` (`local.py:721/742/764`) | One `resolve_ref_commit` for the ref↔tag consistency check. |
| Caller-ref safety | `_validate_ref` (`run_files.py:565`), exact match against `list_tags()`, fail-closed | Reused verbatim by restore **and by the legacy chain read**. |
| Hook dispatch | `_fire_hooks` (`engine.py:6945`), declaration-driven, permission-bound, block-aggregating | `post_run` becomes a real event; `pre_commit` gets a real payload. |
| Durable, replayable events | `_RunEventSink.persist` → `append_event_at_or_after` (`authz.py:522`); replay from `Last-Event-ID` (`run_stream.py:234`) | Two new event types. **No transport change** — every engine event is already persisted unconditionally at `engine.py:1633`. |
| Owner-scoped audit rows | `hook_runs` / `gate_events` / `validation_results` / `exec_runs` (all: run FK + `owner_id` NOT NULL + `workspace_id` NOT NULL) | Two sibling tables in the same shape. |
| Merge-conflict artifact | `KernelServices.write_merge_conflict_artifact` (`kernel_services.py:924-964`), owner/workspace-scoped | Nothing. It is written *before* the event, and it becomes the merge-agent's only input. |
| Durable HITL decision | `gate_events` + the one review gate (`_run_review_gate`) | The merge human gate persists through it rather than in memory. |
| Declared provider activation | `_seed_workflow_context` (`engine.py:11235`) resolves `compiled.context_providers` | The chain gate reads the compiled plan instead of a bare ctx field. |
| Deliverable filename | `DeliverableSpec.name` (`plan.py:336`) | Compile-time validation of it as a *safe basename*. |
| `.context/` write/rebuild | `write_od_context_to_sandbox` / `rebuild_od_context_from_sandbox` (`launch_context.py:97/114`) | Inheritance rule + chain-payload preservation on resume. |

What is genuinely new is narrow: one reserved-path registry, one commit
primitive, one internal ref namespace, one finalization record, one audit sink,
one restore command, one family lock, and durable fan-out merge state.

---

## Precedence, Supersession, and Retained v1 Obligations

*(Requirement 1; V1 Supersession Matrix)*

**V2 wins.** Where this document or `requirements.md` conflicts with
`.kiro/specs/sandbox-git-versioning`, implementation and review follow v2
(Requirement 1 AC 1). Where v2 is silent and v1 is not, v1 governs. A conflict
this design did not anticipate is resolved by escalating to the v2 requirements
document, never by a reviewer's local judgement.

**A v1 checkbox is not evidence.** No task marked complete in
`.kiro/specs/sandbox-git-versioning/tasks.md` may be cited as verification for
any v2 acceptance criterion. Acceptance requires a passing behavioural test or a
recorded direct runtime observation (Requirement 1 AC 3). The five defects in the
Overview were all covered by checked v1 tasks — that is the precedent this rule
exists to prevent repeating.

**Retained v1 obligations.** Every v1 requirement the supersession matrix marks
Retain remains mandatory (Requirement 1 AC 2). The ones this design must not
silently drop:

| V1 rows | Disposition | Where v2 keeps it |
|---|---|---|
| 6 — initial Git commit required | Retain | `git_init_sandbox` keeps its mandatory initial commit; `.gitignore` is still seeded inside the same call, before that commit (L8). Without a born HEAD every fan-out merge is refused. |
| 8–9, 44 — reserved exclusions | Replace with retained exclusions | Every v1 exclusion survives, now derived from one registry (Requirement 18). Nothing becomes *more* visible. |
| 15–17 — read-only ref browsing | Retain with clarification | `git ls-tree` / `git show` / `git archive` reads only; HEAD never moves; refs exact-matched against `list_tags()` (Requirement 9 AC 1–3). |
| 21 — reserved-prefix seeding guard | Replace with restated guard | Requirement 18 AC 9–13, registry-derived, plus path normalization. |
| 2 — TTL protection | Replace with restated protection | Requirement 2 AC 13–17, re-keyed to the revision root. |
| 33 — stale-output declaration | Retain | `Step.outputs` + `Step.replaces` stay as v1 defined them: an opt-in declared output surface for engine-side deletion reconciliation. V2 neither extends nor removes them, and the flat payload does **not** become a `replaces` target. The `.chain/` allowlist reconciliation in Requirement 4 AC 9 is a separate mechanism and must not be conflated with it. |
| 34 — name-free kernel | Retain | Invariant Compliance, SC-001 / INV-1 rows. |
| 37–39 — existing deferrals | Retain | Still deferred, still binding as deferrals: production prompt-override migration (v1 Req 37, and Requirement 13 AC 10 — the v1 trigger is unchanged unless product state has changed), and the two remaining v1 deferrals are not reopened by v2. No v2 work item may quietly consume a deferred surface. |
| 45 — golden safety | Retain and strengthen | Requirement 13 AC 7 ledger assertions plus Requirement 17 AC 9–11 gates. |

---

## Scope and Non-Goals

*(Requirement 16)*

**In scope, and bounded.** Git history UI remains exactly the existing version
selector, the Workspace surfaces, and the new restore action — nothing else
(Requirement 16 AC 1). Restore is the **only** history-affecting user command;
Requirement 18 consolidates existing exclusions and SHALL NOT be used to
introduce any new user-facing file-visibility feature (Requirement 16 AC 12).

**Newly in scope because the gap audit found them missing** — corrective
closures, not new product features (Requirement 16 AC 10): the reserved-path
registry and its enforcement points (Requirement 18), the durable provenance
audit sink (Requirement 19), failure-event persistence and rendering
(Requirement 20), and the chain launch/lineage product surface (Requirement 21).

**Out of scope — do not build:**

| Excluded | AC |
|---|---|
| Push, remotes, branch management, pull requests, `/flowin-handoff` behaviour | 16 AC 2 |
| Cross-tenant chaining (prohibited by owner gates, not merely unbuilt) | 16 AC 3 |
| A DB cache of refs or tags | 16 AC 5, 15 AC 3 |
| Family-level budgets | 16 AC 5 |
| Entitlement / tier gating | 16 AC 5 |
| An agent-callable Git tool | 16 AC 5 |
| A general agent delete tool | 16 AC 5 |
| Remote-runtime redesign | 16 AC 5 |
| Extending `_extract_chain_context`'s hardcoded workflow branches | 16 AC 6 |
| Rewriting existing tags or history; reconstructing swept legacy payloads | 16 AC 7 |
| An operator audit dashboard or reporting UI | 16 AC 11 |
| Log export pipelines | 16 AC 11 |
| Audit retention *automation* beyond the declared policy | 16 AC 11 |
| A general binary content-inspection service beyond Requirement 11 AC 14–17 | 16 AC 11 |
| Any remote or third-party transmission of sandbox content | 16 AC 11 |

**Retained, not retired.** `previous_run` stays live: its declared-intent gate,
its parent seed, and its reserved-prefix guard all remain active. It is only
*short-circuited where redundant* — per-file, when the shared revision tree
already holds the file (ledger row 25; Requirement 16 AC 4).

**Invariants that stay green** (Requirement 16 AC 9): SC-001, INV-1, INV-3,
INV-7, INV-12, the closed Workspace Protocol, additive-migration policy, the
SSE/REST transport split, and the existing import boundaries. Verified in the
Invariant Compliance table.

---

## Architecture

### Two lineage graphs (V2-Q1)

```
parent_run_id  ── revision family ──▶  PHYSICAL SANDBOX IDENTITY
                                       <RUNS_ROOT>/<user>/<revision_root_id>/
                                       shared tree, shared git history, shared tags

source_run_id  ── chain edge ───────▶  READ-ONLY INPUT
                                       new physical sandbox; reads the source's
                                       immutable ref; copies 3 files into .context/
```

The correction is a swap plus a split. `_find_chain_root` is replaced by
`resolve_revision_root`, which walks `parent_run_id`; and `RunSandbox` learns two
ids so the directory and the per-run paths stop sharing one value.

### Before → after, per defect

**Sandbox identity.** Today `RunSandbox(disk_principal, _chain_root_id)` where the
root came from a `source_run_id` walk. After: `RunSandbox(disk_principal,
sandbox_root_id=<parent_run_id root>, current_run_id=<pipeline_run_id>)`. The
resolver becomes one app-side function feeding every consumer; the two duplicate
walks (`engine.py:518`, `run_files.py:80`) are deleted.

**Payload.** Today `.chain/{run_id}/{summary.md, deliverable, logs/*}` written to
the live tree, gitignored, never committed. After: exactly three files at
`.chain/` root, force-staged by exact path, committed as the terminal snapshot,
reachable at `refs/ideaflow/runs/{run_id}` and (for a completed run) at `vN`.
Legacy nested directories relocate to the ignored `.chain-legacy/`.

**Finalization.** Today: `finally` → optimistic stamp → payload → gc → wip →
tag → *then* Step 5 computes the truth. After: Step 5 resolves the candidate
outcome and calls one ordered, idempotent finalizer; the terminal event is
emitted only after the required sequence is durable.

**Chaining.** Today: a dormant provider gated on an unassigned ctx field, reading
the live tree as UTF-8 text through `RunSandbox.read`. After: a manifest-declared
gate, an exact ref, and byte streams — with the *decision* moved above the run row.
Eligibility and provenance are both settled pre-mint, so the in-run provider only
copies bytes; a refused chain never becomes a run at all.

### Directory layout after v2

```
RUNS_ROOT/user/
  <revision_root_id>/            ← parent_run_id root. Shared by the whole family.
    .git/
    .gitignore                   ← every registry entry, one per line
    prototype.html               tracked deliverable
    spec.md  tasks.md
    .chain/                      ignored as a prefix; 3 exact paths force-staged
      logs.jsonl                 byte copy of .logs/{current_run_id}.jsonl
      summary.md                 engine-rendered, candidate outcome + intended_tag
      prototype.html             exact deliverable bytes
    .chain.staging-{run_id}/     temporary sibling; atomically swapped into .chain/
    .chain-legacy/               v1 nested payloads, relocated; never staged/listed
      {run_id}/…
    .logs/
      {root_run_id}.jsonl        ← root's own trace
      {revision_a_id}.jsonl      ← per-run, no longer colliding
      {revision_b_id}.jsonl
    .verify/{current_run_id}/    .browser/{current_run_id}/
    .agents/                     run-local transcripts; NEVER copied into .chain/
    .uploads/                    accumulates across the family by design
    .context/                    what THIS run was given
      design/  selections.json   inherited from the revision root
      logs.jsonl  summary.md  {source_output}   ← chained runs only
    .worktrees/{step}/{i}/       fan-out isolation

  <chained_run_id>/              ← a chain gets its OWN root. Never the source's.
```

### Git object graph for one revision family

```
initial ── step ── step ── SNAPSHOT(root)     ← refs/ideaflow/runs/{root}, tag v1
                              └─ step ── step ── SNAPSHOT(rev A)  ← .../{revA}, tag v2
                                                    └─ restore: v1 ── step ── SNAPSHOT(rev B)
                                                                                 ← .../{revB}, tag v3
```

Every terminal run gets an internal ref. Only `completed` gets a `vN` tag.
`v1`, `v2`, `v3` each contain the same three `.chain/` paths with different bytes.
Restore is a forward commit; it consumes no ordinal.

### Run lifecycle after v2

**Launch.** App resolves `revision_root_id` from `parent_run_id` and authorizes
`source_run_id`. A chain launch additionally settles source eligibility (terminal +
finalized + chainable) **and** payload provenance (exact ref, tag/ref agreement,
payload shape, `summary.md` identity) *before* the run row is minted, then persists
`source_run_id` and the receiving run's `chain_source_selected` audit row in the
same transaction as run creation. The family lock covers revision admission.

**Sandbox open.** `git init` + `.gitignore` from the registry (idempotent, initial
commit retained) → legacy `.chain/{run_id}/` relocation → persistent-Git-state
detection and reconciliation under the family lock → `.context/` design write or
inherit → chain payload install (only if the compiled plan declares the chain
capability).

**Per step.** Unchanged dispatch. The step-boundary commit routes through the one
commit primitive, which now computes a real staged diff for `pre_commit`.

**Terminal.** Step 5 resolves the candidate outcome, then calls the finalizer's
12-step sequence. The terminal SSE event is emitted at step 11.

---

## Components and Interfaces

This map is normative (Requirement 1 AC 5) and names every touched production
**and test** surface plus the explicit no-change surfaces (Requirement 16 AC 8).
A required change outside it updates this table first.

### L1 — Frontend chain launch and legacy transition

| Component | Change | Req |
|---|---|---|
| `DashboardLayout.tsx` `handleChainPipeline` (:1760) / `handleChainFromHistory` (:1883) | `enrichedInput = chainBrief` already carries no context block. Add the missing `source_workflow_run_id` to the two non-wizard `onStartPipeline` calls (:1870, :1958) — today the direct chain path sends **no lineage at all**. | 21 AC 5, 6 AC 16 |
| `lib/workflowChaining.ts` (:33-38) | Add a versioned storage namespace (`chain.v2.*`). Give `chain.context_block` a constant, then drop the legacy key on first load under the version key. Cleanup covers `sessionStorage`, `localStorage`, and in-memory launch state; is idempotent; and must not discard `chain.brief` or unrelated draft input. | 21 AC 6 |
| `LaunchWizard.tsx` (:830-834) | Stop reading `chain.context_block`; keep the consume-once removal of `chain.source_run_id`. | 21 AC 5-6 |
| `lib/runInput.ts` `parseRunInput` `chainRe` (:61) | **No change.** The marker parser stays for historical runs. | 13 AC 11, 21 AC 7 |
| Chain-context presentation precedence (new rule, consumed by the run surface) | A run is presented as **file-based** chain context iff a `.context/` chain payload was actually installed — even when a legacy marker exists in historical input for an older run in the same family. The discriminator is the new `chainContextInstalled` projection flag, **not** `chainSource != null`: `source_run_id` predates v2 (migration 0014), so a pre-v2 marker-bearing run can carry the edge with no payload, and a `source_payload_missing` + `chain_policy: degrade` run keeps its edge deliberately without one. Keying on the edge would flip both to file-based and break AC 7. | 21 AC 8 |
| Chain lineage label composition | Name the source workflow plus the **selected version**: the visible tag when one exists, otherwise a non-guessable label — the source run's **short id** plus its published status. Never an internal ref name. | 21 AC 2, 13 |
| Mixed-deploy handling (new) | New FE + older BE: the launch degrades to no chain context and surfaces the Requirement 20 AC 4 reason rather than launching without provenance. Older FE + new BE: the legacy text block is rejected/ignored per Requirement 13 AC 11. Any other combination is **named as unsupported** in the launch error, never left undefined. | 21 AC 9 |
| `HomeLaunchGrid.tsx` (:382) | The `(Chained)` text stays as the recents affordance. | 21 AC 1 |
| `RunDetailPage.tsx` (:457) / `RevisionFamilyView.tsx` (:796) | **Render the chain lineage indicator here** — these are the run-detail and revision-family surfaces the requirement names. Driven by the `chainSource` projection, not client inference. Also add "no version tag" for a terminal-untagged run, and the source's status for a chained run. | 21 AC 1-2, 13-14 |
| Chain-vs-revision distinctness (both surfaces) | A revision SHALL NOT be labelled chained. A chained run SHALL NOT appear inside its source's revision family list — the family view is built from the `parent_run_id` family projection, which structurally excludes chains. | 21 AC 3 |
| Chain-source picker (new, in the chain menu) | Offer `completed` normally; offer non-success only when `payload_chainable`; show non-chainable as unavailable with its reason. Pre-launch warning is accessible and acknowledged, not color-alone, and states **both** the source's published status **and** that its output may be incomplete. | 21 AC 11-12 |

### L2 — Frontend run surface and event rendering

| Component | Change | Req |
|---|---|---|
| `useWorkflow.ts` `handlePipelineMessage` (`switch` at :403, `default: return false` at :1347) | Add `chain_context_unavailable` and `run_finalization_failed` cases. Today both fall through the silent default. | 20 AC 5-8 |
| New `RunEngineNotice` component | Engine-fact presentation, **not** a chat message from an agent. Non-color-only indicator, programmatically associated message, keyboard-reachable detail, unknown-reason-code fallback. `role="alert"` exists exactly once in the tree today (`AgentsPopup.tsx:2670`) — this establishes the convention; the `role="log" aria-live="polite"` transcript (`ChatPanel.tsx:283`) announces it. | 20 AC 5, 7-8 |
| Degraded-run status treatment (run header + family chip) | A `degraded` run is **visually and semantically** distinguishable from `completed`: distinct label text, distinct non-color indicator, and a status announced to assistive tech. Not a colour variant of the success state. | 20 AC 5 |
| Reason→action mapping | retry (`source_not_finalized`) · choose another source (`source_non_chainable`, `source_payload_missing`, `source_provenance_conflict`) · retry-later (`source_running`) · contact support + reason code (`run_finalization_failed`). Never offer an action the server refuses. | 20 AC 6 |
| `RunHeader.tsx` `VersionMenu` (:30-127) | Fix the live defect: it passes a **tag name** to `onSelectVersion`, but `PreviewPanel.handleSelectVersion` (:669) treats it as a **run id** → `findIndex` returns -1 and `getWorkflow("v2")` fails into a `console.warn`. Wire it to `SandboxTab`'s `selectedRef`. | 9 AC 1-3 |
| `SandboxTab.tsx` (:948-951, :1184-1215) | Working ref picker — keep. Add the restore action, disabled while any family member is non-terminal, showing the server's generic reason. `.chain-legacy/` must not appear in the listing. | 9 AC 4-6, 18 AC 2 |

### L3 — Frontend data layer

| Component | Change | Req |
|---|---|---|
| `lib/api.ts` `getRunSandbox*` (:1156-1231) | `ref` threading is complete. Add `postRestoreRun(token, runId, {tag, idempotency_key})`. | 9 AC 4 |
| `lib/api.ts` `RawWorkflowRun` (:676) + `normalizeWorkflowRun` (:703) | Add the chain-source projection plus `payload_chainable`, `non_chainable_reason`, `chain_context_installed`, `chain_unavailable_reason` (from the chain provenance record, per Requirement 20 AC 3), and the finalization reason code/message. | 15 AC 8, 20 AC 3, 21 AC 8 |
| `types/index.ts` `WorkflowRun` (:375) / `FamilyMember` (:429) | Add `chainSource` (id, **shortId**, workflowId, publishedStatus, visibleTag \| null), `chainContextInstalled`, `payloadChainable`, `nonChainableReason`, `chainUnavailableReason`, `finalizationReason`. **No internal ref field ever.** | 20 AC 3, 21 AC 2, 8, 13 |

### L4 — API routes

| Component | Change | Req |
|---|---|---|
| `run_files.py` `_resolve_chain_root` (:80) | **Delete.** Replaced by the one app-side `resolve_revision_root` (walks `parent_run_id`, typed failure). | 2 AC 1, 7-8 |
| `run_files.py` all five routes (:189, :605, :633, :720, :823) | Root-resolve via the new resolver; refuse on `revision_root_unresolved` with a generic non-enumerating error. | 2 AC 11-12 |
| `run_files.py` `upload_files` (:189) | Acquire the **family lock** before the manifest lock (documented single order). Admission per the five-state table in Key Algorithms. Bytes → manifest → response. | 10 AC 9-12 |
| `run_files.py` `_manifest_lock` (:416) | Retained for within-upload dedupe only — explicitly **not** the family lock. Note: `fcntl is None` on Windows makes it a silent no-op, so the family lock must not be built on the same mechanism. | 10 AC 9, 11 |
| `run_files.py` single-file read guard (:864-867) | Two literals (`.uploads/`, raw `".logs/"`) → derive from the registry. Add `.chain-legacy/`. | 18 AC 2 |
| `run_files.py` zip route (:720) | The non-ref branch derives its entry set from the registry, not from `list_files`' independent literals. The ref branch stays `git archive` (tracked content only, which the registry already governs via `.gitignore`). | 18 AC 2-3 |
| **New** `POST /api/runs/{run_id}/restore` | Authenticated REST command, visible tag + idempotency key, two-layer owner gate → 404. Family lock + under-lock non-terminal check. Materialize tracked tree, forward commit `restore: {tag}` through the commit primitive. Never `reset --hard`, never checkout, never rewrite a tag. | 9 AC 4-12 |
| `run_commands.py` `_mint_revision_row` (:3650) / `_launch_run_core` (:2415) | Admission under the family lock as one atomic fail-closed operation (today: three fail-*open* reads, `run_commands.py:3594`). Persist the authorized `source_run_id` **and** write the receiving run's `chain_source_selected` audit row in the same transaction, so the edge and the row explaining it cannot diverge. Chain launch gains the eligibility **and** provenance gate, returning **404** for a missing or cross-owner source and a typed refusal for an ineligible one. | 10 AC 1-2; 6 AC 1, 16-19; 19 AC 1, 6 |
| **New** `run_commands.py` `admit_chain_launch` / `open_or_refuse` / `select_source_payload` / `select_legacy_payload` / `is_legacy_source` | The pre-mint chain gate. Eligibility **and** provenance validation both run here, above the run row, so every non-degradable refusal predates the persisted edge (Requirement 6 AC 16). Produces the `SourceSelection` the in-run provider copies without re-deciding. | 6 AC 1-3, 6-7, 16-19; 7 AC 5-12 |
| `run_commands.py` `_revision_chain_root_id` (:3551) | Fold into the canonical resolver — it already walks `parent_run_id` correctly; it is simply not the one everyone else uses. | 2 AC 7-8 |
| `run_commands.py` `LaunchCommand` ingress + `_launch_run_core` | **The backend half of the duplicate-context guard.** A launch carrying an authorized `source_workflow_run_id` **and** a legacy `=== CONTEXT FROM PREVIOUS PIPELINE … ===` block in its input has the block **stripped and the strip recorded**, so no run can receive chain context twice in two formats. This must live server-side: an older frontend cannot be trusted to stop sending it. | 13 AC 11, 21 AC 9 |
| **New** `ProvenanceAuditObserver` registered on `post_commit` | The concrete registered observer that writes commit-class audit rows. Two-surface registration (`_KNOWN` + `discover()`), observation-only, exception-isolated at the dispatch site. | 19 AC 3 |
| `runs.py` `_extract_chain_context` (:611) + `GET /{id}/chain-context` (:821) | **Do not extend.** The seven hardcoded `pipeline_type` branches stay frozen; the endpoint keeps serving `ctx.brief` for display. | 16 AC 6 |
| `runs.py` `WorkflowRunResponse` (:89) / `FamilyMemberResponse` (:1120) | Additive chain-source + finalization projection, ownership-scoped; a source the caller does not own projects as **absent**, never partially disclosed. `chain_context_installed` is projected from `run_finalizations.chain_context_installed` on the *receiving* run — the same durable-record pattern Requirement 20 AC 3 uses for `chain_context_unavailable`, never inferred from `source_run_id`. | 15 AC 8, 21 AC 8 |
| `runs.py` `_compute_root_ids` (:211) | Already a correct owner-scoped `parent_run_id` walk with a `_FOREIGN_ANCESTOR` sentinel — the reference implementation the canonical resolver adopts, plus the non-null `user_id` condition. | 2 AC 1, 4 |
| `runs.py` `POST/DELETE /{id}/share` (:1644/:1693) + `/s/{token}` | Share serves the deliverable projection only. Add the registry-derived assertion so no reserved path, `.git/`, or `.gitignore` is ever reachable. | 18 AC 7 |
| `main.py` `_sandbox_sweep_loop` (~:195-250) | Protected set is built from `_find_chain_root` (a `source_run_id` walk) — re-key to the canonical `parent_run_id` resolver. A gate-paused **or active** descendant protects the family. Resolver failure ⇒ protected. | 2 AC 13-17 |
| `launch_context.py` (:41, :97, :114) | `resolve_launch_od_context` remains the sole producer of OpenDesign files. `write_od_context_to_sandbox` gains the inheritance guard; `rebuild_od_context_from_sandbox` becomes the resume source of truth. Chain install must not overwrite `design/` or `selections.json`. | 8 AC 1-6 |

### L5 — Persistence

| Component | Change | Req |
|---|---|---|
| `WorkflowRun.git_tag` (`workflow.py:150`, migration 0041) | Unchanged. Remains the visible completed-version mapping. | 15 AC 1 |
| `WorkflowRun.source_run_id` (:76, migration 0014) | Unchanged shape. Written at creation only; never mutated; never aliased into `parent_run_id`. | 15 AC 7 |
| **New** `WorkflowRun.payload_chainable` + `WorkflowRun.non_chainable_reason` | Two additive nullable columns. Requirement 5 AC 17 requires the durable flag and reason on `WorkflowRun` itself, not only on the finalization record. NULL on every legacy row ⇒ treated as "unknown", which the eligibility gate resolves from the finalization record. | 5 AC 17, 15 AC 5 |
| **New** `run_finalizations` table | Owner/workspace-scoped, additive. Columns match `FinalizationRecord` field-for-field: candidate status, snapshot commit, `internal_ref` + `internal_ref_state`, `visible_tag` + `tag_state`, published status, `required_sequence_complete`, `payload_chainable`, `non_chainable_reason`, `failure_reason`, `conflicting_commit`, `chain_context_installed`. **Every column is nullable and `run_id` is UNIQUE** — the row can be created before agent 1 by the chain installer, when no finalization fact exists yet, and completed at step 9 by an upsert on that key. Same shape as `hook_runs`/`gate_events`. | 5 AC 19, 24; 15 AC 9; 21 AC 8 |
| **New** `run_provenance_audits` table | Owner/workspace-scoped audit sink. Identifiers, statuses, bounded reason classifiers **only** — no contents, diffs, prompts, output, secrets, PII. Carries a nullable `idempotency_key` with a partial unique index on `(owner_id, operation, idempotency_key) WHERE idempotency_key IS NOT NULL` — the durable home for Requirement 9 AC 10's restore replay key, reused rather than given its own table (Requirement 15 AC 10). | 19 AC 1-8, 15 AC 10-11; 9 AC 10 |
| **New** `fanout_merge_states` table (or an additive column set on `wave_runs`) | Durable fragment order, current fragment, and per-fragment outcome. Owner/workspace-scoped like every other audit table. Prefer extending `wave_runs` if its scope fits — Requirement 15 AC 10 asks for reuse before a new table. | 12 AC 11 |
| `gate_events` (`gate_events.py:26`) | Reused unchanged as the durable store for the merge human-gate decision. No new table. | 12 AC 8, 15 AC 10 |
| `artifact_refs` (`artifact_ref.py:23`) | Reused unchanged for the `merge_conflict` artifact. No new table. | 12 AC 3, 15 AC 10 |
| Alembic | Head is **0041** (`0041_add_git_tag_to_workflow_run.py:22`), single linear chain, no branch labels. *(`.kiro/steering/project-index.md` says 0037 — stale; correct it.)* Verify exactly one head before adding anything. Every new table/column carries `owner_id` + `workspace_id` where applicable. | 15 AC 5 |
| No `has_git` column, no tag cache | Explicitly excluded. `has_git` stays runtime-only. | 15 AC 2-3 |
| No column for the internal run ref | The ref is deterministic from an owned run UUID; `run_finalizations.internal_ref_state` records state, not the ref. Nothing needs the column: the one question that looks like it needs one — "does this run have an internal ref?", asked by legacy detection — is answered from Git by `has_internal_run_ref`, against the source sandbox the admission path already opens. No column unless implementation proves the mapping is otherwise unrecoverable. | 15 AC 4 |

### L6 — Compiler and plan

| Component | Change | Req |
|---|---|---|
| `plan.py` `DeliverableSpec.chains_from` (:343) | Compiled since v1 with **zero consumers**. Becomes the declared chain capability the provider gates on. | 6 AC 13-14 |
| **New** `plan.py` `DeliverableSpec.chain_policy` | `refuse` (default) \| `degrade`. The runtime consumer of Requirement 6 AC 10's "when the workflow policy permits graceful degradation". An unknown value fails compilation. | 6 AC 10, 14 |
| `plan.py` `DeliverableSpec.name` (:336) | Becomes a validated safe basename: no separator, not `.`/`..`, no case-insensitive collision with `logs.jsonl`/`summary.md`. | 4 AC 3 |
| `compiler.py` `_compile_deliverable` (~:1436-1473) | Pure pass-through today (INV-5 keeps the compiler thin). Add *validation only*: a chainable workflow without a resolvable output name, or an unknown chain policy value, fails compilation. No defaulting. | 4 AC 4, 6 AC 14 |
| `compiler.py` provider validation (:281-285) | Extend with the registry-derived reserved-prefix rejection for declared cross-run selectors. The error names the offending entry. | 18 AC 9-13 |
| `plan.py` `Step.on_conflict` | Values stay exactly `human_gate` \| `merge_agent` \| `partial` \| `abort`, default `human_gate`; a fifth value already raises `CompilerError`. | 12 AC 1 |
| `plan.py` `Step.outputs` / `Step.replaces` | **No change.** V1's stale-output declaration stays exactly as declared; the flat payload is not a `replaces` target. | Supersession row 33 |
| `factory.py` prompt policy selection | Reads the policy name from the manifest; omitted/empty ⇒ `default`; unknown non-empty ⇒ compile error. | 13 AC 1 |

### L7 — Execution kernel

| Component | Change | Req |
|---|---|---|
| `engine.py` `_find_chain_root` (:518-580) | **Delete.** Its docstring's "never walk `parent_run_id`" is exactly inverted from V2-Q1. | 2 AC 1-2, 8 |
| `engine.py` `RunTrace` site (:1575-1576) | Root-resolve for the directory, but build the log path from `current_run_id`. Also fix the principal: it uses the literal `user_id or "anon"` while the real sandbox at `:1808` uses `disk_principal` — if those differ the trace lands under a different user segment. | 3 AC 3, 2 AC 7 |
| `engine.py` `_execute_impl` sandbox (:1808-1811) | Two-id `RunSandbox`. `git_init_sandbox` failure must flip `has_git=False` — today it only logs (`:1819-1827`), leaving `has_git=True` with no `.git/` reachable. | 3 AC 1-2, 5 |
| `engine.py` `resume_run` (~:10644) | Root-resolve via the canonical resolver; rebuild `ectx.od_context` from `.context/`; preserve an installed chain payload byte-for-byte. | 2 AC 7, 8 AC 6 |
| `factory.py` `create_runner` (:293) | Root-resolve rather than trusting an inherited `ctx.run_id`. Named explicitly because Requirement 2 AC 7 lists the factory as a consumer. | 2 AC 7 |
| `engine.py` `context_sources` probe (~:8816-8821) | `_RS(_disk_p, _run_id)` does **not** root-resolve. Fix. | 2 AC 7 |
| `engine.py` ordinal walks (:1831-1856 and :452-470) | Two walks that disagree — one counts only `completed` ancestors, the other every hop, so the tag name can differ from the ordinal written into `summary.md`. Collapse to one. | 5 AC 22, 4 AC 17 |
| `engine.py` `_write_chain_payload` (:189-311) | Rewrite as the flat atomic builder with temp-sibling staging and stale-basename reconciliation. Drop the `.agents/` transcript copy (step 5). Fix the id mismatch: it reads `sandbox.run_log_path` (root id) and writes `logs/{run_id}.jsonl` (logical id). | 4 AC 1-2, 6, 9 |
| `engine.py` `_fire_post_run` (:325-511) + `_post_run_fired` (:322) | Replaced by the ordered finalizer. The process-local set may remain a fast path but **must not** be the sole idempotency mechanism — Git refs and durable state are inspected first. | 5 AC 3, 7-8 |
| `engine.py` optimistic stamp (:4156-4165) | **Delete.** The candidate outcome is resolved in Step 5 and passed in. | 5 AC 1-2 |
| `engine.py` terminal emission sites — the ten: bare return (:3261), pre-agent cancel (~:3274), gate-reject cancel (:3363), gate block (~:3411), `CancelledError`, `BudgetExceeded`, `FanoutWorkerFailed` (:4102-4119), unhandled exception / `GeneratorExit`, Step-5 total collapse (~:4185), Step-5 normal (~:4489) | All ten route through the one finalizer and emit their terminal event only after the required sequence is durable. | 5 AC 3, 12; 11 AC 7-8 |
| **New** `engine.py` `commit_in_sandbox(...)` | The single commit primitive: stage exact paths → `pre_commit` → **mandatory** secret scan of real staged content → commit → `post_commit`. No caller invokes `git commit` outside it. Message content is engine-rendered and carries no user content. | 11 AC 9-13, 5 AC 11 |
| `engine.py` step-boundary commit (:3568-3596) | Route through the primitive. Replace `payload=""` with the real staged diff. The `has_git=False` branch at `:3596` currently fires **no hooks at all** — unify. | 11 AC 4, 9 |
| `engine.py` spawn-point commit path | Named explicitly by Requirement 11 AC 10. Today `spawn_point_commit` only *reads* `git rev-parse HEAD`; if any spawn boundary is ever made to create a commit it goes through the primitive. If it remains read-only, the design records that as an explicit not-applicable closure rather than an omission. | 11 AC 10 |
| `engine.py` resume dirty commit (:3213-3229) + terminal wip (:404-431) | Through the primitive. Unify the two divergent message formats and the two different ways of deriving the step id. | 10 AC 4-5, 11 AC 10 |
| `engine.py` `restore_non_terminal_runs` (:7944-8235) | Purely DB-driven today, touches no Git state. Add persistent-Git-state detection (merge in progress, stale `index.lock`, orphan worktrees, unmerged branches, corrupt repo, Git command failure). | 10 AC 14-19 |
| `engine.py` `_fire_hooks` (:6945-7010) | Dispatch contract unchanged. `post_run` becomes a real registered event fired exactly once per terminal run, for all five statuses. | 11 AC 5-6 |
| `engine.py` `_compose_context_message` (~:11261) | Seam 2 removal per workflow; brief to agent 1 only except the Requirement 14 retry classes; retry block targeted at the retrying agent. | 13 AC 4, 14 AC 2-3 |
| `fanout.py` worker commit (:497-503) + `merge/git_3way.py` (:76-82) | Both call `commit_all` directly, bypassing hooks and the scan. Route through the primitive — a secret must be blocked at *that* commit, not at a later clean boundary. A blocked worker/fragment commit follows the refused-merge policy. | 11 AC 10-12 |
| `fanout.py` `fragments_meta` (:399, :526-533) | In-memory `list[dict]`. Persist durable merge state before each attempt so a crash classifies as "resume the recorded fragment". | 12 AC 11 |
| `fanout.py` `_merge_fragments` (:910-1000) | Keep the artifact-before-event ordering (`write_merge_conflict_artifact` then `merge_conflict`); the event carries the artifact ref on success and a generic reason on persistence failure. | 12 AC 3-4 |
| `fanout.py` `_resolve_conflict` (:1023-1065) | A refused-before-start merge (`MergeRefusedError`) must be distinct from a started-and-conflicted merge; emit `merge_failed` and apply the documented per-policy outcome. Never continue as though the fragment applied. `partial` retains a defined set; `merge_agent` is bounded, verified, and commits before reporting success; `human_gate` persists a durable decision. | 12 AC 2, 6-8 |
| `fanout.py` teardown (:702-725) | Branch retention on cancel is correct — keep. Additionally clear durable merge state and worktree registrations on cancel, since v2 introduces state this teardown predates. | 12 AC 9 |
| `kernel_services.py` `read_parent_file` (:1627) | Root-resolve through the canonical resolver. | 2 AC 7 |
| `kernel_services.py` `list_chain_source_files` (:1656) / `read_chain_source_file` (:1717) | **Replace** with `open_source_sandbox` + ref-scoped **byte** readers. Both read the live tree as text today, and both resolve through `_find_chain_root` on the wrong edge. The replacement root-resolves the **source** id and returns a `ReadOnlySandbox` — the receiving run's own sandbox holds none of the source's Git objects, so reading through it would make the Requirement 6 AC 3 tag-versus-ref check compare `None` to `None` and pass having checked nothing. | 6 AC 2, 3, 8, 11; 2 AC 7 |
| `kernel_services.py` `write_to_sandbox` (:1735) | No path validation, no reserved-prefix check. Derive the refusal set from the registry. The payload force-stage exception is **engine-only and does not apply here** — this is an agent-reachable write path, so a registry path is refused unconditionally, including `.chain/summary.md` (which the chain reader validates as provenance). | 18 AC 2, 5, 8 |
| `kernel_services.py` `write_merge_conflict_artifact` (:924-964) | **No change.** Already owner/workspace-scoped; becomes the merge-agent's sole context input. | 12 AC 3, 14 AC 5 |
| `context.py` `chain_source_run_id` (:156) | Populate it app-side at launch — declared since v1, **never assigned** outside tests. | 6 AC 13, 16 |
| **New** `context.py` `chain_selection` | The `SourceSelection` admission validated, carried one-way from launch to the provider so provenance is decided once, above the run row. Derived, not authoritative: ignored entirely unless the compiled plan declares chaining, and every read it drives still goes through an owner-scoped `ReadOnlySandbox`. | 6 AC 2-3, 13, 16 |
| `context.py` `final_status` / `git_tag` | Dynamic attrs today (`final_status` stamped at `:4163`; `git_tag` only ever *read*, never written). Replace with an explicit typed candidate-outcome value object. | 4 AC 7, 5 AC 19 |
| `context.py` retry/redo scratch fields | Consume-once, drained unconditionally per dispatch iteration; never replayed twice on resume. | 14 AC 6-7 |

### L8 — Runtime and workspace

| Component | Change | Req |
|---|---|---|
| **New** `sandbox.py` `RESERVED_PATHS` registry | One canonical set. Today's nine prefixes + `.chain-legacy/`. Adding a reserved path is a single edit. | 18 AC 1 |
| `sandbox.py` `is_deliverable_relpath` (:745) | Derive from the registry. | 18 AC 2 |
| `sandbox.py` `serialize_sandbox_deliverable` (:821) / `count_sandbox_deliverables` (:889) | Named explicitly: both derive their exclusions from the registry through `is_deliverable_relpath`; neither may carry its own literal list. `WorkflowRun.output` is the output of the former, so it inherits the same exclusions. | 18 AC 2-3 |
| `sandbox.py` `list_files` (:344-358) | Raw literals covering only `.uploads/`, `.logs/`, `.git*`, `skills*`. Derive from the registry; keep the deliberate read-visibility of `.chain/`/`.context/`; exclude `.chain-legacy/`. | 18 AC 2-3, 6; 7 AC 4 |
| `local.py` `_GITIGNORE_PATHS` (:620-630) | Derive from the registry. It is the only list containing `conversation_history/` — proof of the drift. Add `.chain-legacy/`. Seeding stays inside `git_init_sandbox`, before the initial commit, which remains mandatory. | 18 AC 1, 4; Supersession row 6 |
| `local.py` `commit_all` (:669) | `git add -A` with **no** exclusion logic and a `CalledProcessError`→`""` swallow. Add explicit-path staging plus the three-path force-add allowlist (exact normalized paths, **never** a `.chain` prefix), and distinguish a genuine no-change exit from every other Git failure by raising a typed `GitCommandError`. | 4 AC 11, 14; 10 AC 7; 18 AC 5 |
| **New** `local.py` `create_run_ref` / `resolve_ref_commit` / `has_internal_run_ref` | `refs/ideaflow/runs/{run_id}` via create-only compare-and-set. No `git update-ref` and no `refs/ideaflow/*` exists anywhere today. | 5 AC 23-25, 7 AC 9 |
| **New** `local.py` / `sandbox.py` byte + index helpers | `read_bytes_at_ref` (the Requirement 6 AC 8 byte reader — the existing `read_file_at_ref` already returns bytes, so this is its ref-scoped sibling for a bounded stream), `read_bytes`, `list_prefix`, `staged_entries`, `stage_exact`, `head_commit`, `reset_index`, `git_rm_cached`, `tracked_chain_paths`, `atomic_replace_dir`, `atomic_context_install`. Named here because Requirement 1 AC 5 makes this map normative and the algorithms use them. | 4 AC 9, 6 AC 8, 10 AC 7 |
| **New** `ReadOnlySandbox` (`sandbox.py`) | A read-only handle on **another** run's revision-root sandbox, used only by the chain reader. No write surface at all, so the provider cannot write into a source it merely reads. | 6 AC 2, 8, 11 |
| `local.py` `create_tag` (:686) / `list_tags` (:703) | Unchanged. Tag creation stays raising (visible failure) and points at the already-created snapshot commit. | 5 AC 3, 22 |
| `local.py` `read_file_at_ref` / `list_files_at_ref` / `archive_at_ref` (:721/742/764) | **No change.** Read-only; HEAD never moves. No `checkout`, `reset`, or `read-tree` is added to any browse path. | 9 AC 1, 3 |
| `local.py` `merge_worktree` (:865) | The `MERGE_HEAD` classification at `:896` is correct — keep it; it is what makes "refused" distinguishable. | 12 AC 2 |
| **New** `local.py` `detect_persistent_git_state` / `reconcile_persistent_git_state` | `MERGE_HEAD`, stale `index.lock` (no handling anywhere today), orphan worktree registrations, unmerged worker branches, corrupt repo → quarantine, and a Git command failure as its own explicit state. Preserves staged, unstaged, and untracked content. | 10 AC 6, 14-19 |
| **New** `local.py` `materialize_tree_at_ref` | Restore's forward materialization. Never checkout, never move a branch backwards. | 9 AC 7-8 |
| `sandbox.py` `sweep_expired` (:600) | Protection keyed by `run_dir.name` is fine; the *caller's* set must come from the canonical resolver. Fail-closed on resolver error. | 2 AC 13-17 |
| **New** `sandbox.py` family lock | Cross-process lock keyed `(user_id, revision_root_id)`. The only cross-process lock today is a POSIX `flock` that no-ops on Windows — the family lock needs a mechanism that holds on both platforms. Lock order: family → manifest. | 10 AC 1-2, 9, 11 |
| `secret_scan.py` (`hooks/secret_scan.py:73-107`) | Add binary handling: content-scan raw bytes, or bounded safe-extraction for PPTX/DOCX/XLSX/ZIP with no path traversal, or block by type/size, or a **security-approved recorded** exemption. Unknown binary type ⇒ **block**. "Binary files differ" is never an accepted result. | 11 AC 14-17 |
| `tools/providers.py` (:67-70) | Returns `([], exclude_builtin=False)` — native deepagents fs tools write **unguarded**. Add the registry-derived guard: **no writes** to any registry path, and **reads permitted only for `AGENT_READABLE_RESERVED`, i.e. `.context/` alone**. `.chain/` is read-visible through the Workspace listing and authorized-ref reads, never through an agent tool (Requirement 18 AC 6, AC 8). | 18 AC 2, 6, 8; 8 AC 7 |
| `context_providers/chain_context.py` | Rewrite: manifest-declared activation gate, byte-stream copy of the admitted selection into `.context/` atomically before agent 1, the `chain_context_unavailable` degradation path, and the `chain_context_installed` write. Provenance decisions move **out** of here to the pre-mint selector. | 6 AC 8-11, 13; 21 AC 8 |
| `context_providers/previous_run.py` `_RESERVED_PREFIXES` (:56-67) | Derive from the registry. Add path normalization — the guard is prefix-string only, so `./.chain/x` and `..` forms slip through. A rejected entry must not fall back to a default seed set. | 18 AC 9-13; 16 AC 4 |
| **New** legacy relocation helper | Atomic `.chain/{run_id}/` → `.chain-legacy/{run_id}/`, bytes preserved, source removed only after the destination is durable, never overwriting silently. | 7 AC 1-3 |
| `skill_staging.py` `skills/` | **No change.** Still staged, still registry-excluded from deliverable/listing/zip/share. | 18 AC 3 |

### L9 — Prompt assembly

Detailed in "Prompt Assembly and the 30-Row Input Ledger" below.

| Component | Change | Req |
|---|---|---|
| `capabilities/prompt/policy.py` | Body-only order and governance order registered; governed agents keep guardrails, hooks, Constitution, `AGENT.md`. | 13 AC 2 |
| `factory.py` `_compose_injection` (the `skills` block) | Removing this block removes the factory's own rendering only. Deepagents' `SKILLS_SYSTEM_PROMPT` is supplied by the runtime adapter and **is not touched**; `skill_staging.py` keeps staging `skills/`. | 13 AC 3 |
| `engine.py` `_compose_context_message` — no `REQUEST.md` | **Never created.** The engine does not write the raw user request to disk and does not propagate it downstream, except to the Requirement 14 retry classes. | 13 AC 4 |
| First durable artifact per migrated workflow — `agents/workflows/*/workflow.yaml` first step + its `deliverable`/artifact declaration | Every migrated first step declares and produces one durable contract artifact (`PLANNER.md`, a spec file, or a declared typed artifact — whichever the workflow already produces); later agents read declared files plus their own task. Verified per workflow before Seam 2 is deleted for it. | 13 AC 5, 8 |
| `run_commands.py` validation-fix dispatch + `capabilities/post_step/revision_validation` | The fix-loop control payload carries validation errors and the exact deliverable path, and nothing else. | 14 AC 4 |
| `AgentThinkingTab.tsx` / `AgentDetailPanel.tsx` prompt viewer | Displays the effective system prompt plus the targeted control payload — never a misleading empty-context message. | 13 AC 9 |
| `prompt_overrides.py` + its API docstring | Overrides remain replacement bodies; the API documentation states that. Production override migration stays deferred to the v1 trigger. | 13 AC 10 |
| Seam 2 removal | Per workflow, only after: inventory, first-durable-artifact verification, manifest migration, and prompt-snapshot review. `prototype` last. | 13 AC 8 |

### L10 — Test surfaces

Named because Requirement 16 AC 8 requires the map to identify test surfaces, and
Requirement 17 AC 8 bars source inspection as acceptance for these.

| Test surface | Scope |
|---|---|
| `tests/agents/test_sandbox_identity_v2.py` | Resolver, two-id sandbox, per-run logs, depth-two revision + chain (real DB) |
| `tests/agents/test_reserved_path_registry.py` | Registry↔enforcement-point agreement; every entry in slash and bare form; nested paths; receiving-sandbox end-to-end |
| `tests/agents/test_commit_primitive.py` | One primitive per commit path; blocked-commit handling; planted-secret object unreachability |
| `tests/agents/test_binary_scan.py` | Binary policy matrix; PPTX fixture with embedded marker; zip-slip; bounds |
| `tests/agents/test_finalizer_v2.py` | 12-step order, five injection points, CAS, tag/ref/`summary.md` triple consistency |
| `tests/agents/test_chain_exact_ref.py` | Activation gate, exact-ref selection, byte fidelity, all five refusal codes, legacy fallback; **every non-degradable refusal asserts no run row and no persisted edge**; a record-less v2 source is refused rather than read as legacy; the payload deleted between admission and install exercises both `chain_policy` arms of the TOCTOU narrowing |
| `tests/agents/test_family_lock.py` | Admission atomicity, upload races, restore races, lock order, restore replay-key collapse, and a step-12 lock timeout still returning the finalization record |
| `tests/agents/test_crash_recovery_v2.py` | Every persistent Git state, every restart point, message classes |
| `tests/agents/test_provenance_audit.py` | Record presence, owner scoping, content prohibitions, bidirectional reconstruction |
| `tests/agents/test_prompt_ledger_v2.py` | 30 rows × five modes (full composer, not dictionary-pop) |
| `tests/agents/test_retry_recipients_v2.py` | Requirement 14's five classes, first and non-first agents |
| `tests/agents/characterization/golden/` | **No change expected** except reviewed prompt-migration baselines |
| `tests/agents/test_banned_patterns.py` | **No change.** 11 tests stay green |
| `frontend/src/**/*.test.tsx` | Lineage indicator, storage cleanup, source picker, event rendering, restore |
| `frontend/e2e/tests/*.spec.ts` (`mocked`) | Version browse, restore, chain launch |

---

## Data Models

### Two-id sandbox

```python
class RunSandbox:
    def __init__(
        self,
        user_id: str,
        sandbox_root_id: str,          # revision root — the DIRECTORY
        *,
        current_run_id: str | None = None,   # logical run — the PATHS
        runs_root: str | None = None,
        has_git: bool = True,
    ) -> None:
        self.sandbox_root_id = sandbox_root_id
        self.current_run_id = current_run_id or sandbox_root_id
        self.root = (base / _safe_segment(user_id) / _safe_segment(sandbox_root_id))

    @property
    def run_log_path(self) -> Path:
        return self.root / ".logs" / f"{self.current_run_id}.jsonl"

    @property
    def verify_dir(self) -> Path:
        return self.root / ".verify" / self.current_run_id

    @property
    def browser_dir(self) -> Path:
        return self.root / ".browser" / self.current_run_id
```

`current_run_id` defaults to the root so the root run and every offline
characterization harness are byte-identical (Requirement 2 AC 6). An offline
harness constructs the sandbox with an explicitly absent `sandbox_root_id`, in
which case the logical run id is used directly and **no DB walk happens at all** —
there is no resolver call to fail.

### One reserved-path registry

```python
# sandbox.py — THE registry. Every enforcement point derives from this one set.
RESERVED_PATHS: frozenset[str] = frozenset({
    ".uploads/", ".logs/", ".verify/", ".browser/", ".agents/",
    ".chain/", ".context/", "skills/", "conversation_history/",
    ".chain-legacy/",                     # v2 addition
})

# Excluded from listing / deliverable / deliverable counting / zip / share,
# but not a "reserved subtree" in the registry sense.
GIT_METADATA_PATHS: frozenset[str] = frozenset({".git/", ".gitignore"})

# The ONLY reserved prefix an authorized AGENT TOOL may READ: `.context/`, because
# Requirement 8 AC 7 requires it ("readable to authorized agents"). `.chain/` is
# deliberately NOT here — Requirement 4 AC 10 and Requirement 18 AC 6 grant it
# read-visibility through the authorized *Workspace surfaces* (listing + reads at an
# authorized version ref), not through agent tools, and Requirement 18 AC 8 requires
# the test to prove an agent tool cannot reach it. Writes to any registry path are
# refused unconditionally.
AGENT_READABLE_RESERVED: frozenset[str] = frozenset({".context/"})

def payload_allowlist(output_basename: str) -> frozenset[str]:
    """The ONLY paths the engine may force-stage. Exact normalized paths —
    never a `.chain` prefix match (Requirement 4 AC 14)."""
    return frozenset({
        ".chain/logs.jsonl",
        ".chain/summary.md",
        f".chain/{output_basename}",
    })
```

Enforcement points, all derived — never an independent literal list
(Requirement 18 AC 2, V2-Q7):

| Point | Symbol |
|---|---|
| Seeded `.gitignore` | `local.py::_write_gitignore` |
| Git staging | `local.py::commit_all` (+ the allowlist exception) |
| Deliverable serialization | `sandbox.py::serialize_sandbox_deliverable` |
| Deliverable counting | `sandbox.py::count_sandbox_deliverables` |
| Deliverable predicate | `sandbox.py::is_deliverable_relpath` |
| Workspace listing | `sandbox.py::list_files` |
| Single-file read route | `run_files.py::read_sandbox_file` |
| Zip / archive route | `run_files.py::download_sandbox_zip` |
| Public share output | `runs.py::/s/{token}` |
| `WorkflowRun.output` | inherited from `serialize_sandbox_deliverable` |
| Agent-callable file tools | `tools/providers.py` + `kernel_services.write_to_sandbox` |
| Cross-run seed selectors | `previous_run.py::_is_reserved` (+ compile-time twin) |

### Flat payload

```python
@dataclass(frozen=True)
class Payload:
    """What the builder produced, and whether it may be chained from."""
    allowlist: frozenset[str]          # the exact paths to force-stage
    built: bool                        # a snapshot exists (flat OR metadata-only)
    materialized: bool                 # the DECLARED OUTPUT was written — never
                                       # overloaded to mean "something was built"
    chainable: bool
    non_chainable_reason: str | None   # ALWAYS set when chainable is False
```

`built` and `materialized` are separate because the metadata-only snapshot is built
*and* has no output. Collapsing them would either loop the finalizer's
`if not payload.materialized` guard back into the metadata-only builder or make
`materialized` mean two things. `built` is read by
`FinalizationAttempt.record_payload`, which refuses a payload no builder wrote.

```
.chain/
  logs.jsonl                    byte copy of .logs/{current_run_id}.jsonl, post-flush
  summary.md                    engine-rendered
  {workflow_output_filename}    exact deliverable bytes (binary-safe)
```

Three regular files, no directories, identical path set across every tag in a
family. A metadata-only snapshot is `summary.md` alone.

### `summary.md` fields (all knowable before the commit that contains them)

```
schema_version: 2
run_id / workflow_id / revision_root_id
candidate_status: completed | cancelled | failed | degraded | diverted
completed_steps
output_filename
intended_tag: v{revision_index}        # only when candidate_status == completed
internal_run_ref: refs/ideaflow/runs/{run_id}
payload_chainable: true | false
non_chainable_reason: <bounded classifier>   # only when false
written_at
```

`intended_tag` is proof of *intent*. Tag existence is proven only by the Git tag,
`WorkflowRun.git_tag`, and the finalization record. A committed `summary.md` is
never amended to reflect a tag created afterwards (Requirement 4 AC 17).

**Derived invariant that resolves the candidate-vs-published reading conflict.**
Requirement 4 AC 7 puts the *candidate* status in `summary.md`; Requirement 5
AC 21 forbids reading the *published* status from it; Requirement 21 AC 14 asks
the receiving surface and the agent to learn the source's published status from
the installed `.context/summary.md`. These reconcile through one rule:

> **When the published status diverges from the candidate status, finalization
> sets `payload_chainable = false`.**

A divergence only happens when finalization fails after the snapshot commit
exists — exactly the case that must not be chained from anyway. So for every
*chainable* source, `candidate_status == published_status`, and reading
`candidate_status` out of the installed `summary.md` **is** reading the published
status. No snapshot is ever rewritten, and no consumer reads a stale status.

### Candidate outcome vs published status

```python
@dataclass(frozen=True)
class CandidateOutcome:
    """Resolved BEFORE payload creation. Immutable once committed.

    Deliberately carries no `output_materialized`: whether the declared output can
    be written under its declared basename is only knowable by attempting the copy,
    so `Payload.materialized` owns that fact (INV-12 — one fact, one owner)."""
    status: str                  # the real terminal status
    failed_agents: tuple[str, ...]
    output_basename: str | None
    commit_blocked: bool
    intended_tag: str | None
```

```python
@dataclass(frozen=True)
class FinalizationRecord:
    """Durable, owner/workspace-scoped. The single thing consumers read."""
    owner_id: str                # NOT NULL — the scoping columns every audit-shape
    workspace_id: str | None     # table in this codebase carries (authz.py:120)
    run_id: str
    candidate_status: str
    snapshot_commit: str | None
    internal_ref: str | None     # the resolved ref NAME, read by the chain reader
    internal_ref_state: str      # created | idempotent | conflict | absent
    visible_tag: str | None      # the resolved tag NAME, or None when suppressed
    tag_state: str               # created | suppressed | rolled_back | absent
    published_status: str        # what the product surfaces
    required_sequence_complete: bool
    payload_chainable: bool
    non_chainable_reason: str | None    # why THIS run cannot be chained FROM
    failure_reason: str | None          # the finalization failure reason class,
                                        # = outcome.reason_class when degraded
    conflicting_commit: str | None      # the OTHER sha on a ref conflict (Req 5 AC 24)
    chain_context_installed: bool = False   # set on the RECEIVING run once the
                                            # three .context/ files are installed;
                                            # the Req 21 AC 8 discriminator's source
```

**The row has three states; this dataclass models only one of them.** Every column
in `run_finalizations` is nullable, and the row's lifecycle is:

| Row state | How it arises | What `read_finalization_record` returns |
|---|---|---|
| **absent** | Legacy run, or a v2 run before its chain install and before step 9 | `None` |
| **partial** | `mark_chain_context_installed` created it before agent 1. `chain_context_installed` is set; every finalization column is still NULL | `None` — the loader treats `published_status IS NULL` as not-yet-finalized |
| **complete** | `persist_finalization_record` filled it at step 9 | A `FinalizationRecord` |

`FinalizationRecord` is therefore the **complete** projection only, which is what
lets `candidate_status`, `published_status`, `tag_state`, `internal_ref_state`,
`required_sequence_complete`, and `payload_chainable` be non-optional. Chain
admission relies on exactly that: `record is None` means "no finalization facts
exist", and it must be true for a partial row too, or a chained run whose own
installer created the row would look finalized to a downstream chain.

`chain_context_installed` is the one field readable from a partial row, so the
Requirement 21 AC 8 projection reads that column directly rather than through this
dataclass — which it must, since a run that never finalizes still needs to report
whether it received a chain payload.

**Where the two chain reasons live, and why they are not both here.**
`non_chainable_reason` is on this record because it describes *this run as a chain
source* — a property finalization establishes. The receiving-side reason (why this
run did not get the chain input it asked for) is **not** on this record: Requirement
20 AC 3 names the chain provenance record as its source, so it is read from the
`chain_refused` / `chain_payload_installed` audit row for the run and projected as
`chainUnavailableReason`. One fact, one home — putting it on `run_finalizations`
too would create the second source of truth Requirement 15 AC 2–3 exist to avoid.

`internal_ref` and `visible_tag` are the resolved **names**, not a durable mapping
that could drift: the ref is deterministic from the owned run UUID and the tag is
the same value written to `WorkflowRun.git_tag`, so recording them here is a
projection convenience, not a second source of truth (Requirement 15 AC 4).
`chain_context_installed` is what the run-detail projection exposes as
`chainContextInstalled`; it is set by `install_chain_context` on success, which is
also what writes the `chain_payload_installed` audit row.

A failure after the snapshot commit exists changes **only** the published status
and this record. It never amends, re-commits, force-updates, or deletes the
snapshot, and never rewrites the committed `summary.md` **or the flushed terminal
log** (Requirement 5 AC 20).

### Durable fan-out merge state

```python
@dataclass(frozen=True)
class FanoutMergeState:
    """Recorded BEFORE each merge attempt so a crash is classifiable."""
    run_id: str; step_id: str
    fragment_order: tuple[str, ...]        # declared order, not arrival order
    current_fragment: str | None           # in flight right now
    outcomes: dict[str, str]               # fragment -> applied|conflicted|refused|dropped
    retained_state: tuple[str, ...]        # what `partial` kept (Req 12 AC 6)
```

### Provenance audit record

```python
@dataclass(frozen=True)
class ProvenanceAudit:
    actor_id: str; owner_id: str; workspace_id: str | None
    run_id: str; revision_root_id: str; workflow_id: str
    operation: str        # snapshot_commit | run_ref_created | run_ref_idempotent |
                          # run_ref_conflict | tag_created | tag_mapped |
                          # status_published | chain_source_selected |
                          # chain_payload_installed | chain_refused |
                          # legacy_migrated | recovery_commit | fragment_merge |
                          # merge_agent_commit | commit_blocked | restore |
                          # legacy_context_block_stripped
    outcome: str
    commit_id: str | None; ref_name: str | None
    tag_name: str | None; source_ref: str | None
    reason_class: str | None      # bounded classifier, never free text
    idempotency_key: str | None   # restore replay key (Req 9 AC 10); partial-unique
    created_at: datetime
```

`run_id` is the run the row **explains**: the receiving run for the chain
operations, the run being finalized or restored for the rest. The one exception is
`chain_refused` raised before a row was minted, which has no receiving run and is
scoped to `actor_id` plus the source id in `source_ref`. There is no free-form
`detail` blob — `commit_id`, `ref_name`, `tag_name`, `source_ref`, `reason_class`,
and `idempotency_key` are the whole vocabulary, which is what keeps "identifiers
and classifiers only" structurally true rather than a convention someone can break
by stuffing a dict.

Identifiers, statuses, and classifiers only. No contents, diffs, prompts, model
output, secrets, or PII (Requirement 15 AC 11, Requirement 19 AC 5). Success is
recorded, not only failure — a transient event or a log line is **not** an audit
record (Requirement 19 AC 2).

**Retention policy (declared, per Requirement 19 AC 8; automation is out of
scope per Requirement 16 AC 11).** Provenance audit rows and finalization records
are retained for **13 months**, then deleted by an operator-run job. Rows are
readable through owner-scoped support queries and — for the one field the product
needs (`chainUnavailableReason`, Requirement 20 AC 3) — the owner-scoped run-detail
projection. There is no cross-owner read
path on any product surface. Retention is deliberately longer than the sandbox
TTL so a version question outlives the directory it refers to.

**Bidirectional reconstruction (Requirement 19 AC 6).** Forward: given a run, its
own `chain_source_selected` row names the ref that fed it in `source_ref` — which
works only because that row is scoped to the *receiving* run and written in the
mint transaction, not to the source at selection time. Reverse: given a source run,
its children are `WorkflowRun.source_run_id == source`, joined to those rows for the
ref each child actually read. Both directions are owner-scoped; the reverse query
needs an index on `(owner_id, source_ref)`.

### Event schemas

```python
CHAIN_REFUSAL_REASONS = (
    "source_running",               # non-terminal            → retry later
    "source_not_finalized",         # terminal, unfinalized   → retryable
    "source_non_chainable",         # payload_chainable=False → choose another
    "source_payload_missing",       # missing/swept, eligible → may degrade
    "source_provenance_conflict",   # tag/ref or summary mismatch → REFUSE, never degrade
)

# chain_context_unavailable / run_finalization_failed
{
  "type": str,
  "pipeline_run_id": str,
  "reason_code": str,            # bounded
  "message": str,                # client-safe
  "artifact_class": str,
}
```

`source_provenance_conflict` is separate from `source_payload_missing` on
purpose: Requirement 6 AC 3 and AC 7 require a corrupt-provenance disagreement to
be **refused**, while Requirement 6 AC 10 allows a genuinely missing payload to
degrade. One shared code would let a corrupt payload silently degrade to empty
context.

**Named narrowing of Requirement 6 AC 10.** AC 10 lists three degradable
conditions — missing, swept, *or corrupt*. This design degrades on the first two
and **refuses** on corrupt, splitting AC 10's set along the boundary AC 3 and AC 7
draw. The reason is that "corrupt" in AC 10 and "disagreement" in AC 3/AC 7 name the
same observations: a `summary.md` whose run id or output filename does not match, a
tag and ref resolving to different commits, a `.chain/` tree that is not exactly
three files. AC 3 and AC 7 say those SHALL be refused and SHALL NOT fall back; AC 10
says a corrupt payload MAY degrade. Refusing is the reading that keeps the stronger
guarantee, because degrading on a structural mismatch means starting a workflow on
bytes whose provenance was disproved — the outcome AC 7 exists to prevent. So
`chain_policy: degrade` covers absence, not disproof, and a workflow author cannot
opt into reading a payload that failed provenance. Listed as **N2** in "Named
Departures from the Requirements" so it is reviewable rather than discovered later as
an unexplained refusal.

Neither event carries file contents, diffs, secrets, internal paths, another
owner's run id, or a raw exception string. Both persist through the existing
`_RunEventSink.persist` path (all engine events already persist unconditionally
at `engine.py:1633`), so reconnect replay is free and ordering relative to other
run events is preserved by the single append/replay path. Both are additionally
projected into durable run state: `run_finalization_failed` from the finalization
record, `chain_context_unavailable` from the chain provenance audit row
(Requirement 20 AC 3).

### Internal ref namespace

```
refs/ideaflow/runs/{run_id}     one per terminal run, create-only CAS
refs/tags/v{revision_index}     completed runs only, user-visible
refs/heads/fanout/{step}/{i}    existing worker branches (unchanged)
```

Constructed only from a validated owned run UUID; never accepted as a
caller-supplied revspec. The user-visible surface stays tags-only —
`_validate_ref` (`run_files.py:565`) already confines callers to `list_tags()`.

---

## Key Algorithms

### Canonical revision-root resolution

```python
class RevisionRootUnresolved(Exception):
    """The ONE outcome for a cycle, a missing ancestor, cross-owner ancestry,
    or a DB failure during the walk (Requirement 2 AC 10-11)."""

def resolve_revision_root(db, run_id: str, user_id: str) -> str:
    """Walk parent_run_id ONLY. source_run_id is never followed."""
    if not user_id:                      # non-null owner is a precondition
        raise RevisionRootUnresolved("null_principal")
    visited: set[str] = set()
    current = run_id
    while True:
        if current in visited:
            raise RevisionRootUnresolved("cycle", visited_size=len(visited),
                                         repeated_node=current)
        visited.add(current)
        try:
            row = (db.query(WorkflowRun.parent_run_id)
                     .filter(WorkflowRun.id == current,
                             WorkflowRun.user_id == user_id,       # owner-scoped
                             WorkflowRun.user_id.isnot(None))      # non-null (AC 4)
                     .first())
        except SQLAlchemyError as exc:
            raise RevisionRootUnresolved("db_error") from exc
        if row is None:
            raise RevisionRootUnresolved("missing_or_cross_owner")
        if row.parent_run_id is None:
            return current
        current = row.parent_run_id
```

`WorkflowRun.user_id` is NOT NULL in the schema, but the filter states the
condition explicitly so the ownership predicate the whole fail-closed story rests
on cannot be weakened by a future nullable-column change (Requirement 2 AC 4).

**Every consumer** (Requirement 2 AC 7): engine launch, `resume_run`,
`factory.create_runner`, `RunTrace` setup, all four file routes, upload, sweeper
protection, `read_parent_file` previous-run reads, restore, family locking, and
`open_source_sandbox` (the chain reader resolves the **source's** revision root, not
the receiving run's).
All refuse identically on `RevisionRootUnresolved`; the TTL sweeper treats it as
**protected** rather than deletable. The client sees a generic non-enumerating
error; the server-side diagnostic records visited-set size, repeated node, and
failure class (Requirement 2 AC 12).

This replaces v1's "cycle → use the last unique node", which silently produced a
*plausible but wrong* directory.

### Terminal finalization (Requirement 5 AC 3)

The sequence has **exactly one exit**. Every failure, every degradation, and every
crash-replay convergence funnels through the same tail, because the defect class
this replaces — a terminal path that skips `post_run` or the terminal event — is
produced entirely by early returns.

```python
async def finalize_terminal_run(ectx, sandbox, candidate: CandidateOutcome) -> FinalizationRecord:
    outcome = FinalizationAttempt(candidate)      # accumulates state; never returns early
    try:
        with family_lock(ectx.owner_id, ectx.revision_root_id):       # 1
            state = detect_persistent_git_state(sandbox)               # 1b (Req 10 AC 14)
            if state.needs_reconcile:
                reconcile_persistent_git_state(sandbox, message_class="crash-recovered")

            if candidate.status != "completed":                       # 2
                wip = commit_in_sandbox(sandbox, ALL_TRACKED_AND_UNTRACKED, ectx=ectx,
                                        message=reconcile_message(candidate.status),
                                        audit_operation="recovery_commit")
                if wip.blocked:                  # a blocked WIP must not poison step 5
                    sandbox.reset_index()
                    outcome.note_blocked_reconcile(wip.reason)

            run_trace.write_terminal_entry(candidate)                 # 3
            run_trace.flush()                     # output + thinking + tool + terminal

            # 4 — build in a temporary sibling, then atomically swap into .chain/.
            payload = build_flat_payload(sandbox, ectx, candidate)
            if not payload.materialized:          # Req 4 AC 4/16, Req 5 AC 15-16
                payload = build_metadata_only_snapshot(
                    sandbox, ectx, candidate,
                    reason=("output_undeclared" if candidate.output_basename is None
                            else "output_unmaterializable"))

            commit = commit_in_sandbox(sandbox, payload.allowlist,     # 5 + 6
                                       ectx=ectx,          # the primitive stages
                                       message=snapshot_message(ectx, candidate),
                                       audit_operation="snapshot_commit")
            if commit.blocked:
                sandbox.reset_index()             # MANDATORY — note 1 below
                payload = build_metadata_only_snapshot(
                    sandbox, ectx, candidate, reason="payload_blocked")
                commit = commit_in_sandbox(sandbox, payload.allowlist, ectx=ectx,
                                           message=snapshot_message(ectx, candidate),
                                           audit_operation="snapshot_commit")
                if commit.blocked:                # engine-rendered content cannot
                    raise SnapshotUnrecoverable(commit.reason)   # block; defensive only
            outcome.record_payload(payload)
            if not payload.chainable:             # blocked OR unmaterializable
                outcome.degrade(payload.non_chainable_reason)   # → published degraded

            # A crash-replay whose snapshot is already committed returns no_change.
            # Converge on the EXISTING commit rather than a null sha (Req 5 AC 7-8).
            snapshot_sha = commit.sha if not commit.no_change else sandbox.head_commit()
            outcome.record_commit(snapshot_sha)

            ref = create_run_ref(sandbox, ectx.run_id, snapshot_sha)   # 7  create-only CAS
            outcome.record_ref(ref)
            if ref.state == "conflict":
                outcome.degrade("internal_ref_conflict")
            elif candidate.status == "completed" and payload.chainable:
                try:                                                   # 8
                    outcome.record_tag(
                        create_tag_and_map(sandbox, candidate.intended_tag,
                                           snapshot_sha, ectx.run_id))
                except TagOrMappingFailed as exc:
                    outcome.degrade(exc.reason_class)

            record = persist_finalization_record(outcome)               # 9

    except BaseException as exc:                  # NOT a narrow tuple — see note 4
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        outcome.degrade(reason_class_of(exc))     # Git, DB, authz, lock, or unknown
        record = persist_finalization_record_safe(outcome)              # 9, best-effort

    try:
        await fire_hooks("post_run", ectx)                              # 10
    except Exception:                             # observation-only; a raising hook
        log_hook_failure(ectx)                    # must never skip steps 11-12

    if outcome.degraded:                          # the SINGLE emission point
        await emit_event("run_finalization_failed", ectx, outcome.reason_class)
    await emit_terminal_event(ectx, record.published_status)            # 11
    try:
        with family_lock(ectx.owner_id, ectx.revision_root_id):         # 12
            cleanup_worktrees_and_gc(sandbox)     # re-acquired: worktree removal and
    except Exception:                             # `git gc` mutate a SHARED sandbox
        log_cleanup_failure(ectx)                 # housekeeping only — see note below
    return record                                 # THE single exit
```

Step 12 re-acquires the family lock. Requirement 5 AC 12 permits step 12 to follow
the terminal *event*, but Requirement 10 AC 1 puts terminal finalization inside the
family lock, and `git gc --auto` plus worktree removal mutate a directory the whole
revision family shares. Running them unlocked would be the one unserialized write in
an otherwise fully serialized design. The event still precedes them, so a consumer
never waits on GC.

It is also guarded, and that guard is load-bearing rather than defensive habit.
Step 12 sits *outside* the main `try/except BaseException` by construction — the
terminal event has already fired, so it cannot be rolled into a block whose handler
degrades and re-publishes. Left unguarded, a `FamilyLockTimeout` there would
propagate out of `finalize_terminal_run` and skip `return record`, so a caller that
just received a clean terminal event would see an exception instead of the record —
which is precisely the "exactly one exit" property this restructure exists to
provide. Worktree cleanup and GC are housekeeping: the sweeper reclaims what they
miss, so a failure is logged and swallowed, never surfaced as a finalization
outcome.

```python
@dataclass
class FinalizationAttempt:
    """Mutable accumulator for ONE finalization pass. Never returns early; the
    finalizer's single tail reads it. Not persisted — `FinalizationRecord` is."""
    candidate: CandidateOutcome
    payload: Payload | None = None
    snapshot_commit: str | None = None
    ref: RefResult | None = None
    tag: str | None = None
    degraded: bool = False
    reason_class: str | None = None

    def record_payload(self, payload):
        """The one reader of `Payload.built`. Asserts a snapshot really exists on
        disk before the accumulator adopts it, so step 5 can never force-stage an
        allowlist for a directory that was never written."""
        assert payload.built
        self.payload = payload
    def record_commit(self, sha): ...
    def record_ref(self, ref): ...
    def record_tag(self, tag): ...
    def note_blocked_reconcile(self, reason):
        """A blocked dirty-WIP commit at step 2. Records the reason and degrades:
        the reconciliation the non-success outcome required did not happen, so the
        published status must say so."""
        self.degrade(reason)
    def degrade(self, reason_class):
        """First reason wins — the earliest failure is the actionable one."""
        if not self.degraded:
            self.degraded, self.reason_class = True, reason_class
```

`run_trace` is `ectx.run_trace`, the per-run tracer bound at `execute()`; it is
written as a bare name above only for readability.

```python
def persist_finalization_record(outcome) -> FinalizationRecord:
    """The ONLY writer of the finalization record. Called on every path, including
    every failure path — which is what makes `published_status` and
    `payload_chainable` durable rather than best-effort.

    Sets, in this order:
      published_status           = "degraded" if outcome.degraded else candidate.status
      required_sequence_complete = not outcome.degraded
      payload_chainable          = (outcome.payload is not None
                                    and outcome.payload.chainable
                                    and not outcome.degraded)
      non_chainable_reason       = outcome.reason_class when not chainable
      failure_reason             = outcome.reason_class when outcome.degraded
      visible_tag                = outcome.tag           (None when suppressed)
      internal_ref               = outcome.ref.name      (None when absent)
      internal_ref_state         = outcome.ref.state, else "absent"
      tag_state                  = "created"     when outcome.tag is set
                                   "rolled_back" when outcome.reason_class is the
                                                 AC-9 mapping-rollback class
                                   "suppressed"  when the step-8 gate declined
                                                 (not completed, or not chainable)
                                   "absent"      when step 8 was never reached
      conflicting_commit         = outcome.ref.existing on a "conflict" state
      chain_context_installed    PRESERVED — never overwritten; its writer is
                                 mark_chain_context_installed at install time
    Also mirrors payload_chainable + non_chainable_reason onto WorkflowRun
    (Requirement 5 AC 17) in the same transaction as the published status.
    """

def persist_finalization_record_safe(outcome) -> FinalizationRecord:
    """Failure-path twin. Attempts the write; on a second failure returns an
    in-memory record so the tail can still emit a terminal event, and logs the
    unpersisted state for operator recovery. A run must never hang terminal-less
    because its record could not be written."""
```

Two things this pins down. The `and not outcome.degraded` conjunction enforces the
divergence invariant the `summary.md` reading rule depends on: any path that
publishes `degraded` while the candidate said otherwise also marks the payload
non-chainable, so no chainable source can carry a status that diverged. And the
**One named relaxation of Requirement 5 AC 12.** AC 12 requires the terminal event
to follow a *durable* finalization record. If the record cannot be written even on
the retry, this design emits the terminal event anyway: the alternative is a run
that never reports a terminal state and an SSE stream that never closes, which is
strictly worse for the user. The relaxation is bounded to that one case, the
unpersisted state is logged for operator recovery, and the run publishes `degraded`
with the DB-failure reason class. Listed as **N1** in "Named Departures from the
Requirements" so a reviewer sees the trade instead of discovering it.

The record carries the resolved `visible_tag` and `internal_ref` **names**, not only
their state strings — the chain reader and legacy detection both read them, so
state alone would not be enough.

Steps 1–10 must succeed before step 11 for **every** status, not just
`completed` (Requirement 5 AC 12). Step 12 may follow the event — worktree
removal, metrics, and GC cannot change the version a consumer can read.

Seven things in that listing are load-bearing:

1. **`sandbox.reset_index()` after a blocked commit is mandatory.** The primitive's
   blocked path leaves the diff in the working tree *and the index*, because
   Requirement 11 AC 3 requires the diff to survive for correction. Committing the
   metadata-only snapshot without first clearing the index would sweep the blocked
   `logs.jsonl` and output bytes into the very snapshot that exists to exclude
   them — violating V2-Q9 and Requirement 5 AC 18. The reset clears the index
   only; the working tree keeps the diff. The same reset runs after a blocked
   step-2 reconcile commit, so a blocked WIP diff cannot ride into the payload
   staging at step 5.
2. **Unmaterializable output routes to the metadata-only snapshot too**, with
   reason `output_unmaterializable`. Both triggers named by Requirement 4 AC 16
   reach the same construct, and both end `payload_chainable = false`, which
   suppresses the tag through the step-8 gate and publishes `degraded`
   (Requirement 5 AC 15).
3. **`post_run` fires on every terminal path** — success, degradation, and raised
   failure alike. Requirement 11 AC 6 requires exactly one dispatch for completed,
   cancelled, failed, degraded, and diverted; there is no branch that skips it.
4. **A raised failure is not an escape hatch.** `GitCommandError`,
   `SnapshotUnrecoverable`, and a lock failure are caught, degraded, recorded,
   announced as `run_finalization_failed`, and still emit a terminal event — which
   is what Requirement 5 AC 10 and AC 12 require.
5. **`no_change` is handled, not ignored.** A second finalization pass over an
   already-committed snapshot returns `no_change=True`; the sequence converges on
   the existing HEAD commit so the CAS at step 7 sees the identical sha and
   reports `idempotent`. Passing a null sha would have broken exactly the
   crash-replay convergence Requirement 5 AC 7–8 demand.
6. **`persist_finalization_record` runs on every path.** It is the single writer of
   the published status, and it mirrors chainability onto `WorkflowRun`. Skipping
   it on a failure path would leave the run's durable state describing an outcome
   that did not happen.
7. **Persistent-Git-state detection runs at finalization entry** (step 1b), not
   only at sandbox open, resume, and restore. Otherwise the finalizer can take the
   lock and immediately commit onto a repo holding `MERGE_HEAD` or a stale
   `index.lock` (Requirement 10 AC 14).

Requirement 5 AC 3's steps 5 and 6 — force-stage the allowlist and run `pre_commit`,
then create the snapshot commit — are one call here because the commit primitive
owns both in that order. The ordering the AC requires is preserved inside
`commit_in_sandbox`; it is not collapsed away. Every commit in the sequence passes
`audit_operation`, which is how the `post_commit` observer classifies the audit row
without guessing from the staged path set.

**Commit message content (Requirement 5 AC 11).** `snapshot_message` and
`reconcile_message` are engine-rendered from a fixed template carrying the logical
run id and the terminal status only:

```
snapshot: run {run_id} status {candidate_status}
wip: {status_class} at step {step_id}
restore: {tag}
```

No user content, no agent output, no file content, no secret, and no free text
reaches a commit message. This matters because a commit message is permanent,
reachable from every tag, and **not** part of the staged content `scan_staged`
inspects.

### Flat payload assembly (Requirement 4 AC 9)

**A workflow with no declared output name.** Requirement 4 AC 4's compile-time guard
fires only for *chainable* workflows, so a non-chainable workflow may legitimately
reach finalization with `output_basename is None`. That is not an error: it gets a
**metadata-only snapshot** with reason `output_undeclared`, a snapshot commit, an
internal run ref, and no visible tag if its candidate was `completed` — the same
shape as any other non-chainable terminal run. It is never a three-file payload, so
`payload_allowlist(None)` is never constructed.

```python
def build_flat_payload(sandbox, ectx, candidate) -> Payload:
    """Assemble in a temporary sibling, then atomically replace .chain/."""
    if candidate.output_basename is None:        # non-chainable workflow, no output
        return Payload(allowlist=frozenset(), built=False, materialized=False,
                       chainable=False, non_chainable_reason="output_undeclared")
    staging = sandbox.root / f".chain.staging-{ectx.run_id}"     # sibling, ignored
    staging.mkdir(parents=True, exist_ok=True)
    write_bytes(staging / "logs.jsonl", sandbox.run_log_path.read_bytes())
    write_text(staging / "summary.md", render_summary(ectx, candidate))
    materialized = copy_declared_output(sandbox, staging, candidate.output_basename)
    atomic_replace_dir(sandbox.root / ".chain", staging)          # swap, then unlink old

    # Reconcile the tracked allowlist: a renamed deliverable must not leave the
    # previous basename tracked forever, which would break AC 1 (exactly three
    # files) and AC 5 (identical path set across the family).
    for stale in tracked_chain_paths(sandbox) - payload_allowlist(candidate.output_basename):
        sandbox.git_rm_cached(stale)
    chainable = materialized and not candidate.commit_blocked
    return Payload(allowlist=payload_allowlist(candidate.output_basename),
                   built=True, materialized=materialized,
                   chainable=chainable,
                   # never None when not chainable — the finalizer degrades on it
                   non_chainable_reason=None if chainable else (
                       "output_unmaterializable" if not materialized
                       else "payload_blocked"))


def build_metadata_only_snapshot(sandbox, ectx, candidate, *, reason) -> Payload:
    """summary.md ALONE. Requirement 4 AC 16 is unconditional, so this must also
    UNTRACK the other two allowlist paths — otherwise the snapshot's tree inherits
    the previous run's `logs.jsonl` and output bytes from the parent commit, and
    "no logs.jsonl, no output bytes" would hold only for a family's first run."""
    staging = sandbox.root / f".chain.staging-{ectx.run_id}"
    reset_dir(staging)
    write_text(staging / "summary.md",
               render_summary(ectx, candidate, chainable=False, non_chainable_reason=reason))
    atomic_replace_dir(sandbox.root / ".chain", staging)
    for path in tracked_chain_paths(sandbox) - {".chain/summary.md"}:
        sandbox.git_rm_cached(path)          # untrack logs.jsonl + any output basename
    return Payload(allowlist=frozenset({".chain/summary.md"}),
                   # `built=True` satisfies record_payload's assertion — a snapshot
                   # DOES exist on disk. `materialized` stays FALSE because the
                   # declared output genuinely was not written; the finalizer's
                   # `if not payload.materialized` guard therefore cannot loop back
                   # into this builder (one fact, one meaning).
                   built=True, materialized=False,
                   chainable=False, non_chainable_reason=reason)
```

Stale-basename removal is `git rm --cached` — it untracks the superseded path
without touching history. This is a distinct mechanism from v1's `Step.replaces`
output reconciliation (supersession row 33), which stays as v1 defined it.

`materialized` is computed here, by attempting the copy, because whether the
declared output can actually be written under its declared basename is not knowable
before the attempt. `CandidateOutcome` therefore carries no `output_materialized`
field — one fact, one owner (INV-12).

**`atomic_replace_dir` vs `atomic_context_install`.** The payload builder swaps a
whole directory, because `.chain/` is engine-owned and its entire contents are
replaced every terminal run. `atomic_context_install` (used by the chain reader) is
the opposite: a **per-file atomic write into an existing directory**, never a
directory swap. Swapping `.context/` would destroy `design/` and
`selections.json`, breaking Requirement 8 AC 5 and AC 8.

### Run-trace flush (Requirement 3 AC 6)

Step 3 writes the candidate terminal entry into the trace and *then* flushes all
four buffered classes — streamed output, thinking, tool payloads, and the terminal
entry — so `logs.jsonl` is complete before step 4 copies it. The externally
visible SSE terminal event at step 11 is the *published* event and is deliberately
not part of the copied trace: it cannot be, because it does not exist until the
snapshot it would describe is already committed. `RunTrace.flush` (`run_log.py:204`)
already drains output and thinking; tool entries are written inline by `observe`;
the terminal entry is the new one.

### Internal run ref: create-only compare-and-set (Requirement 5 AC 23-25)

```python
@dataclass(frozen=True)
class RefResult:
    state: str                   # created | idempotent | conflict
    name: str                    # refs/ideaflow/runs/{run_id}
    sha: str                     # the sha finalization WANTED to point at
    existing: str | None = None  # the sha the ref already held (conflict only)
```

```python
def create_run_ref(ws, run_id: str, commit_sha: str) -> RefResult:
    ref = f"refs/ideaflow/runs/{_validated_uuid(run_id)}"
    existing = ws.resolve_ref_commit(ref)          # None when absent
    if existing is None:
        ws._git("update-ref", ref, commit_sha)     # absent → create
        return RefResult("created", ref, commit_sha)
    if existing == commit_sha:
        return RefResult("idempotent", ref, commit_sha)   # crash-replay converges
    return RefResult("conflict", ref, commit_sha, existing=existing)
```

`sha` is always the sha finalization wanted; `existing` is only populated on a
conflict and is what `FinalizationRecord.conflicting_commit` stores. Requirement 5
AC 24's "record the conflicting commit ids" is therefore both ids:
`snapshot_commit` (wanted) and `conflicting_commit` (found).

A conflict is never self-healed. The existing ref is preserved for operator
inspection, the run publishes `degraded`, both commit ids go into the
finalization record, and recovery is an explicit operator action.

### Exact-ref chain read (Requirement 6)

The work splits across **two actors**, and which check lives where is load-bearing.
Requirement 6 AC 11 says so directly — "the context provider MAY return `{}` after
an app-side authorization failure has already prevented launch" — so the design
must not put the same gate in both places.

| Actor | When | Owns |
|---|---|---|
| **`admit_chain_launch`** (app-side, `run_commands.py`) | Before the run row is minted | The declaration gate, `assert_owns` → 404, terminality, finalization record, `required_sequence_complete`, `payload_chainable`, legacy eligibility — **and then** payload selection and provenance validation via `select_source_payload`. Every refusal here means **no run row and no persisted edge**. |
| **`install_chain_context`** (provider, in-run) | Sandbox open, before agent 1 | Re-checks only the declaration (its own activation gate), then copies the bytes of the selection admission already validated. The only failure it can originate is the payload vanishing between the two phases. |

**Two sandboxes, two handles.** This is easy to get wrong and fails *open* if you
do. A chained run has its own physical sandbox (V2-Q1), which contains none of the
source's Git objects, refs, or tags. So the reader needs a **second, read-only
handle on the source's own revision-root sandbox**:

```python
class KernelServices:                       # may import app.* — the provider may not
    def open_source_sandbox(self, source_id, owner_id) -> ReadOnlySandbox:
        """The SOURCE's revision-root sandbox — a different directory from
        `ctx.sandbox`. Root-resolved through the canonical resolver on the SOURCE id
        (Requirement 2 AC 7 lists chain-source reads as a consumer), opened
        read-only, and never written to. `ctx.sandbox` stays the receiving run's
        write target.

        Lives on KernelServices, not in `chain_context`, because it needs a DB
        session: the provider package keeps importing only stdlib + the registry,
        and every sandbox and persistence fact it needs arrives through
        `ctx.services` (see the import-boundary row in Invariant Compliance)."""
        root = resolve_revision_root(self._db, source_id, owner_id)
        return ReadOnlySandbox(self._disk_principal, sandbox_root_id=root)
```

`RevisionRootUnresolved` out of that resolver is a **refusal, not a degradation**:
if the source's history cannot be located at all, its provenance cannot be
established, so both call sites map it to `source_provenance_conflict` — the
"choose another source" class, never degradable. `read_finalization_record`,
`mark_chain_context_installed`, and `write_provenance_audit` reach the database the
same way, as `ctx.services` methods; the code below writes them bare for
readability.

Reads (`resolve_ref_commit`, `list_files_at_ref`, `read_bytes_at_ref`,
`list_prefix`, `read_bytes`, `_validate_ref`) go to `src`; the install writes to
`ctx.sandbox`. And a ref that does not resolve is a **refusal, not a pass**:

```python
def resolved_or_refuse(src, ref) -> str:
    sha = src.resolve_ref_commit(ref)
    if sha is None:                     # absent ref, wrong sandbox, swept objects
        raise ChainRefused("source_provenance_conflict")
    return sha
```

Without that, the Requirement 6 AC 3 tag-versus-ref agreement check would compare
`None` to `None`, find them equal, and pass having verified nothing — the worst
possible failure mode for a provenance gate.

**Where provenance is settled: pre-mint, not in-run.** This is the second thing
that is easy to get wrong. Requirement 6 AC 16 requires that "a run that was
refused a payload SHALL NOT have" a persisted `source_run_id` edge, while AC 16's
first sentence requires that edge to be written *atomically with run creation*.
Those two together mean **every non-degradable payload verdict has to be reachable
before the row is minted** — tag/ref disagreement, unresolvable ref, bad payload
shape, summary identity mismatch. If any of them fired in-run instead, the row
would already exist and would carry an edge for a payload the run was refused.

So admission does not stop at *eligibility*; it goes on to **select and validate
the payload**, and hands the resolved selection forward. The in-run provider is
reduced to copying the already-validated bytes.

```python
def admit_chain_launch(db, services, ctx_spec, source_id, user) -> ChainAdmission:
    """App-side, pre-mint. A refusal here creates NO run row, so a refused chain
    never leaves a persisted `source_run_id` edge (Requirement 6 AC 16)."""
    if not compiled_declares_chain(ctx_spec):    # V2-Q8 — checked HERE TOO, first,
        return ChainAdmission(active=False)      # so a stray source_run_id triggers
                                                 # ZERO cross-run reads (Req 6 AC 13)
    if not source_id:
        return ChainAdmission(active=False)
    source_row = owned_run_row(db, source_id, user.id)   # the authorization source
    if source_row is None:                               # of truth, reused below
        raise HTTPException(404)                  # missing OR cross-owner (Req 6 AC 1)
    await scoped_store.assert_owns(source_id)

    # Terminality FIRST: a running source has no finalization record by definition,
    # so checking the record first would report every running source as
    # `source_not_finalized` and make `source_running` unreachable — collapsing two
    # codes V2-Q11 and Requirement 20 AC 4 require to stay distinct.
    if not source_is_terminal(db, source_id):
        raise ChainRefused("source_running")

    record = read_finalization_record(source_id)
    # ORDER MATTERS, twice over. The record gates run BEFORE any sandbox handle is
    # opened, because Requirement 6 AC 19 says a non-chainable source is not read
    # from disk or from any ref at all — so the refusal has to be decidable from the
    # record alone, and it is. It must also precede legacy detection: a v2 run that
    # degraded before step 7 has no internal ref and would satisfy legacy disjunct
    # (a), so checking legacy first would route a non-chainable v2 source to the
    # legacy reader, where it could degrade to empty context.
    if record is not None:
        if not record.required_sequence_complete:
            raise ChainRefused("source_not_finalized")      # retryable
        if not record.payload_chainable:
            raise ChainRefused("source_non_chainable")      # zero disk/ref access

    # Only now is a source-sandbox handle justified.
    src = open_or_refuse(services, source_id, user.id)  # the SOURCE's read-only handle
    if record is None and not is_legacy_source(src, source_id, record=None):
        raise ChainRefused("source_not_finalized")          # v2 run, not yet finalized

    # Eligibility is settled. Now SELECT AND VALIDATE the payload — still pre-mint.
    selection = select_source_payload(
        src, source_row, record,
        declared_output_basename=ctx_spec.deliverable.name)
    return ChainAdmission(active=True, source_id=source_id,
                          record=record, selection=selection)
```

**Where the selection audit row goes.** Not here. `chain_source_selected` must be
scoped to the **receiving** run — that is the whole point of Requirement 19 AC 6's
forward direction, "given a run, which ref fed it?" — and the receiving run id does
not exist until the row is minted. So the launch handler writes it immediately after
`_mint_revision_row`, inside the same transaction that persists the edge:

```python
admission = admit_chain_launch(db, services, ctx_spec, source_id, user)
with db.begin():
    run = _mint_revision_row(..., source_run_id=admission.source_id)   # AC 16 edge
    if admission.active:
        write_provenance_audit(user, operation="chain_source_selected",
                               run_id=run.id,            # the RECEIVING run
                               source_ref=admission.selection.ref
                                          if admission.selection else None)
```

One transaction, so the edge and the row that explains it cannot diverge. It carries
the **resolved** ref for both the v2 and the legacy class, which makes forward
reconstruction answerable for every chained run — legacy included, and including a
run whose later install fails.

A `chain_refused` row is the mirror case and is filed differently *because there is
no receiving run*: it is scoped to the actor and the source id. That asymmetry is the
audit trail's own statement of Requirement 6 AC 16 — a refusal has no run to hang
off, which is exactly what "SHALL NOT have one" means.

```python
def open_or_refuse(services, source_id, owner_id) -> ReadOnlySandbox:
    """One handle, opened once at admission and threaded through every pre-mint
    check, so legacy detection and payload selection cannot disagree about which
    sandbox they read."""
    try:
        return services.open_source_sandbox(source_id, owner_id)
    except RevisionRootUnresolved:
        raise ChainRefused("source_provenance_conflict")   # cannot locate history


def select_source_payload(src, source_row, record,
                          *, declared_output_basename) -> SourceSelection:
    """Pre-mint. Resolves the ONE exact ref and proves the payload's provenance.
    Every refusal it raises therefore predates the run row. Returns a
    discriminated selection the in-run provider copies without re-deciding.

    `source_row` is the owned `WorkflowRun` admission already authorized — passed
    in rather than re-queried, so there is exactly one authorization read and the
    read-only sandbox handle never needs a DB session."""
    source_id = source_row.id
    if is_legacy_source(src, source_id, record):          # FEATURE detection
        return select_legacy_payload(src, source_row, declared_output_basename)

    # ── Exact ref — never HEAD, never the latest tag, never an ordinal tag ────
    ref = record.visible_tag or record.internal_ref
    if record.visible_tag and record.internal_ref:
        if (resolved_or_refuse(src, record.visible_tag)
                != resolved_or_refuse(src, record.internal_ref)):
            raise ChainRefused("source_provenance_conflict")   # refuse, never degrade

    # A swept payload for an ELIGIBLE source is the one degradable case (Req 6 AC 10).
    # Anything structurally wrong is a provenance conflict, not a miss.
    try:
        entries = src.list_files_at_ref(ref, prefix=".chain/")
        if not entries:
            raise ChainRefused("source_payload_missing")   # swept / never committed
        basename = validate_exactly_three(entries)   # returns the one safe basename
        summary = src.read_bytes_at_ref(ref, ".chain/summary.md")
    except GitObjectMissing:
        raise ChainRefused("source_payload_missing")        # honours chain_policy
    except PayloadShapeInvalid:
        raise ChainRefused("source_provenance_conflict")    # never degradable

    provenance = parse_summary(summary)
    if provenance.run_id != source_id or provenance.output_filename != basename:
        raise ChainRefused("source_provenance_conflict")    # no other ref is tried
    return V2Selection(ref=ref, basename=basename)
```

Every `ChainRefused` above reaches the launch handler, which writes one
`chain_refused` audit row carrying the reason class — so a refusal is audited
exactly like a success (Requirement 19 AC 2) — and then splits on the reason:

| Reason class | Handler outcome |
|---|---|
| `source_running`, `source_not_finalized`, `source_non_chainable`, `source_provenance_conflict` | Refuse. No run row, no edge. Never consults `chain_policy` — Requirement 6 AC 17 puts these outside AC 10's reach. |
| `source_payload_missing` | Consults the compiled `chain_policy`. `refuse` (default) → refuse, no row, no edge. `degrade` → mint **with** the edge and `selection=None`; the provider emits `chain_context_unavailable` and agent 1 starts with no payload (AC 10). The edge is correct here: this source *was* authorized and eligible, and the projection's `chainContextInstalled: false` records that no bytes arrived. |

```python
async def install_chain_context(ctx) -> None:
    """In-run, before agent 1. Eligibility AND provenance were settled at launch;
    this only copies the admitted bytes. Re-checks the declaration (its activation
    gate), so the provider is safe to call unconditionally."""
    if not compiled_declares_chain(ctx):        # V2-Q8 — the ACTIVATION gate
        return                                  # a stray source_run_id reads NOTHING
    source_id = ctx.chain_source_run_id
    if not source_id:
        return                                  # nothing admitted; Req 6 AC 11's {}
    if ctx.chain_selection is None:             # admitted under `degrade` with no bytes
        return emit_chain_context_unavailable(ctx, "source_payload_missing")
    src = ctx.services.open_source_sandbox(source_id, ctx.owner_id)
    sel = ctx.chain_selection
    try:
        if sel.is_legacy:
            install_legacy_chain_context(ctx, src, sel)
        else:
            with atomic_context_install(ctx.sandbox) as staging:   # RECEIVING sandbox
                for name in (".chain/logs.jsonl", ".chain/summary.md",
                             f".chain/{sel.basename}"):
                    staging.write_bytes(name.replace(".chain/", ".context/"),
                                        src.read_bytes_at_ref(sel.ref, name))  # BYTES
    except (GitObjectMissing, RevisionRootUnresolved):
        # The ONLY in-run payload failure left: the bytes were validated at
        # admission and vanished before the install (sweeper, disk loss). See the
        # named narrowing below.
        return resolve_install_toctou(ctx, "source_payload_missing")
    mark_chain_context_installed(ctx.run_id, source_ref=sel.ref)  # Req 21 AC 8 producer
    write_provenance_audit(ctx, operation="chain_payload_installed",
                           source_ref=sel.ref,
                           reason_class=sel.reason_class if sel.is_legacy else None)
```

**Named narrowing of Requirement 6 AC 16 — the one TOCTOU window.** Between
admission and install, an authorized payload can still disappear. Under
`chain_policy: degrade` this is exactly AC 10 and needs no exception: emit
`chain_context_unavailable`, continue, keep the edge. Under `chain_policy: refuse`
the run must fail — and its row already carries the edge, which AC 16 read
literally forbids. Rolling that edge back is worse: AC 16's own first sentence
requires the edge to be written atomically with run creation, and deleting it would
erase the only durable record of which source was authorized for a run that is
about to be reported as a chain failure. So the design accepts the edge on that
failed run and makes the distinction queryable instead: **`chain_context_installed`
is the discriminator between "read a payload" and "was refused one."** It is
`false` on exactly these runs, and the run's terminal status is `failed`, so it can
never itself become a chain source. This is a deliberate narrowing, listed in "Named
Departures from the Requirements" and covered by a test that kills the payload
between the two phases.

`mark_chain_context_installed` is the one writer of the Requirement 21 AC 8 flag.
It **upserts** the receiving run's `run_finalizations` row with
`chain_context_installed = true` at install time — before agent 1, long before
step 9 — and `persist_finalization_record` preserves an already-set value rather
than overwriting it. That is the one field on the record not owned exclusively by
the finalizer, and the exception is deliberate: the fact is established at install
time and must survive to the projection even if the run never finalizes cleanly.

Three corrections to today's provider: the gate moves from a ctx field to the
compiled plan; the read moves from the live tree to an exact ref; and text I/O
becomes byte streams, which is what makes a PPTX payload survive at all.

The two helpers the TOCTOU branch names are thin, and both live on the provider so
the degrade and refuse arms cannot drift apart:

```python
def emit_chain_context_unavailable(ctx, reason_class) -> None:
    """Requirement 6 AC 10's explicit event. Agent 1 starts with no chain payload;
    `chain_context_installed` stays false."""
    emit_event(ctx, "chain_context_unavailable", reason_class=reason_class)
    write_provenance_audit(ctx, operation="chain_refused", reason_class=reason_class)

def resolve_install_toctou(ctx, reason_class) -> None:
    """The admitted bytes vanished between selection and install."""
    if ctx.compiled.deliverable.chain_policy == "degrade":   # compiled, never a name
        return emit_chain_context_unavailable(ctx, reason_class)
    write_provenance_audit(ctx, operation="chain_refused", reason_class=reason_class)
    raise RunFailed(reason_class)          # terminal; edge kept, installed=false
```

Both arms write `operation="chain_refused"`, and that is not sloppiness about the
degrade/refuse distinction — it is what makes the Requirement 20 AC 3 projection
work. A `chain_refused` row *scoped to a run* means exactly one thing: that run did
not receive the payload it asked for, and `reason_class` says why. That is the
durable source `chainUnavailableReason` reads. The degrade/refuse difference is
visible in the run's own terminal status, not in the audit operation, and a refusal
that happened *before* the row existed has no run to scope to — it is attached to the
actor and the source id instead. One operation, two scopes, no ambiguity.

`ChainAdmission.selection is None` while `active` is True carries no reason field
because only one reason can reach that state: `source_payload_missing` is the sole
degradable class (see the handler-outcome table), so the provider names it directly
rather than plumbing a value that can only hold one thing.

**Missing source vs refused source (Requirement 6 AC 1, AC 16).** A missing or
cross-owner `source_run_id` returns **404** at launch, before any run row exists,
matching the IDOR→404 posture used everywhere else. Because eligibility *and*
provenance are settled before the row is minted, a refused chain launch creates no
run and therefore no persisted edge — which is what "a run that was refused a
payload SHALL NOT have one" requires, for every reason class except the single
TOCTOU narrowing named above. A degradation (`source_payload_missing` under
`chain_policy: degrade`) keeps the edge, correctly: that source *was* authorized and
eligible; only its bytes went missing, and the audit row plus the
`chain_context_unavailable` event record that.

### Legacy chain read (Requirement 7 AC 5-12)

Detection is by **feature**, in exactly the two disjuncts Requirement 7 AC 9 names.
Both must be checked — gating only on "no finalization record" would miss a source
that has a record but whose committed payload predates the v2 schema.

**One predicate, not two.** An earlier draft had a launch-side twin that answered
disjunct (a) from the database as `not internal_run_ref_exists_for(db, source_id)`.
That cannot work, and it fails *open*. Per Requirement 15 AC 4 the internal ref is
deliberately **not** mirrored into a column — `refs/ideaflow/runs/{run_id}` is its
only durable record — so the DB has nothing to answer with. The twin was also
reached only when `record is None`, meaning it would have re-tested its own branch
condition, returned `True` unconditionally, and admitted every record-less v2 run as
legacy; `is_legacy_source` would then have returned `False` in-run (its `record is
None` disjunct is scoped) and dereferenced `record.visible_tag` on a null record.
Because admission now opens the source sandbox anyway, both disjuncts are answered
by the single predicate below, from Git, in one place.

```python
def is_legacy_source(src, source_id, record) -> bool:
    """A source is legacy when EITHER:
      (a) it has NO finalization record at all AND no internal run ref, OR
      (b) the `.chain/` tree at its selected ref carries no v2 schema_version.
    No global cutover timestamp, no deploy flag (Req 7 AC 9, Req 17 AC 3).

    Disjunct (a) is scoped to `record is None` deliberately. A v2 run that degraded
    before the ref was created also has no ref, but it is NOT legacy — it is a v2
    run that must be refused as non-chainable. The caller's ordering enforces that;
    this scoping means the predicate cannot misclassify it either.

    A v2 run whose record write failed under the Requirement 5 AC 12 relaxation has
    a ref and no record, so disjunct (a) returns False for it and admission refuses
    it `source_not_finalized` — correct: it is a v2 run, not a legacy one."""
    if record is None:
        return not src.has_internal_run_ref(source_id)            # disjunct (a)
    ref = record.visible_tag or record.internal_ref
    if ref is None:
        return False                                  # v2 run, no readable ref
    try:
        summary = src.read_bytes_at_ref(ref, ".chain/summary.md")
    except GitObjectMissing:
        return True                                   # no v2 payload at that ref
    return parse_summary(summary).schema_version is None   # disjunct (b)
```

The legacy path splits the same way the v2 path does: **selection pre-mint,
byte copy in-run.** `declared_output_basename` is the *receiving* workflow's
declared output name, threaded in from the compiled plan, because a pre-v2
`summary.md` may not name one.

```python
def select_legacy_payload(src, row, declared_output_basename) -> LegacySelection:
    """Pre-mint. A pre-v2 source: no internal run ref, or no v2 schema_version in
    summary.md. Detection is by FEATURE, never by date or deploy flag
    (Req 7 AC 9, Req 17 AC 3). `src` is the SOURCE's read-only sandbox; `row` is the
    owned `WorkflowRun` — the authorization source of truth, already fetched."""
    source_id = row.id
    # AC 11's eligibility rule — terminal status on the owned row, NOT the absence of
    # a finalization record — is already satisfied by the `source_is_terminal` gate in
    # admission, which runs before legacy detection for every source class. No second
    # terminality decision here: two gates that must agree is the defect class this
    # design is removing, not adding.
    if row.git_tag:
        # AC 10: exact-match the STORED tag against the SOURCE sandbox's visible
        # tag list BEFORE any git subprocess sees it. Same gate restore uses.
        _validate_ref(row.git_tag, src)            # refuse on mismatch
    # AC 5: this fallback order ONLY. Never live flat .chain/, never another run's
    # directory, never the latest tag, never an ordinal-derived tag, never HEAD.
    for base in (f".chain-legacy/{source_id}/", f".chain/{source_id}/"):
        if not src.list_prefix(base):
            continue
        summary = src.read_bytes(f"{base}summary.md")
        if parse_summary(summary).run_id != source_id:      # AC 6: validate run id
            continue                                        # corrupt — try next base
        return LegacySelection(                             # AC 6: only these three
            ref=row.git_tag, base=base, reason_class="legacy-live-nested",
            files={
                "summary.md":             f"{base}summary.md",
                "logs.jsonl":             f"{base}logs/{source_id}.jsonl",
                declared_output_basename: f"{base}{declared_output_basename}",
            })                    # {base}logs/*.md agent transcripts IGNORED (AC 6)
    # AC 8: missing legacy live data degrades EXPLICITLY. Old tags and Git history
    # are never rewritten to manufacture a payload.
    raise ChainRefused("source_payload_missing")   # honours chain_policy


def install_legacy_chain_context(ctx, src, sel: LegacySelection) -> None:
    """In-run byte copy of an already-validated legacy selection.
    `src` is the SOURCE's read-only sandbox; `ctx.sandbox` is the receiving one."""
    with atomic_context_install(ctx.sandbox) as staging:
        for flat_name, src_path in sel.files.items():
            staging.write_bytes(f".context/{flat_name}",
                                src.read_bytes(src_path))          # ALL BYTES
    emit_provenance(ctx, sel.reason_class)                         # AC 7
```

Three things this fixes relative to an earlier draft: a legacy **untagged** terminal
run is eligible (the `git_tag` check is conditional, not a precondition), which is
what Requirement 7 AC 11–12 require; the stored tag passes through `_validate_ref`
before reaching Git, closing the ref-injection hole that scoping that helper to
restore alone would have left open; and because selection is pre-mint,
`chain_source_selected` and `chain_payload_installed` are both written for legacy
chains too — the earlier draft returned out of the installer before the selection
audit row, leaving Requirement 19 AC 1 and AC 6's forward direction unanswerable
for exactly the runs most likely to need reconstruction. The
`mark_chain_context_installed` and `chain_payload_installed` writes are the shared
tail of `install_chain_context`, so both classes get them on exactly one path.

`LegacySelection.ref` is the stored `git_tag`, which may legitimately be `None` for
an untagged legacy source; the audit rows and the projection carry `source_ref:
null` in that case, and `reason_class` (`legacy-live-nested`) is what identifies the
provenance. Both selection types satisfy `SourceSelection`, which the in-run
provider discriminates on `is_legacy`:

```python
@dataclass(frozen=True)
class V2Selection:
    ref: str                      # tag or refs/ideaflow/runs/{id} — never HEAD
    basename: str                 # the one validated safe output basename
    is_legacy: bool = False

@dataclass(frozen=True)
class LegacySelection:
    ref: str | None               # stored git_tag; None for untagged legacy
    base: str                     # .chain-legacy/{id}/ or .chain/{id}/
    files: dict[str, str]         # flat .context/ name → source path
    reason_class: str             # "legacy-live-nested"
    is_legacy: bool = True

SourceSelection = V2Selection | LegacySelection

@dataclass(frozen=True)
class ChainAdmission:
    """What the launch handler carries from admission into run creation."""
    active: bool
    source_id: str | None = None
    record: FinalizationRecord | None = None
    selection: SourceSelection | None = None   # None + active ⇒ admitted under
                                               # `degrade` with no payload
```

**How the selection reaches the provider.** `ChainAdmission.selection` is
serialized onto the launch payload the engine receives and surfaces as
`ExecutionContext.chain_selection` — the same one-way path `chain_source_run_id`
already takes. It is *derived, not authoritative*: the provider trusts it only
because it was produced above the authorization boundary in the same transaction
that minted the row, and it still cannot widen access, since every read it drives
goes through a `ReadOnlySandbox` re-resolved from the owner-scoped resolver. A
`chain_selection` present without `compiled_declares_chain` is ignored, exactly like
a stray `source_run_id` (Requirement 6 AC 13).

### The one security-gated commit primitive (Requirement 11 AC 9-13)

```python
def commit_in_sandbox(sandbox, paths, *, message, ectx,
                      audit_operation: str | None, audit_detail: dict | None = None,
                      step=None) -> CommitResult:
    """`audit_operation` is REQUIRED (explicitly, possibly None), never inferred:
    restore and a recovery commit both stage ALL_TRACKED, so the observer cannot
    classify from the path set.

    `None` means "not an audited class" — the step-boundary and spawn-point commits,
    which Requirement 19 AC 1 does not list. The observer no-ops on None rather than
    inventing an enum value, so per-step commits do not flood the audit table.

    `audit_detail` carries operation-specific identifiers the observer cannot derive
    from the commit alone — for restore, the source tag Requirement 9 AC 11 requires."""
    stage_exact(sandbox, paths)                          # registry-gated; allowlist exception
    staged = sandbox.staged_entries()                    # paths + real content
    outcome = fire_hooks("pre_commit", step, ectx, payload=staged.hook_payload)
    scan = scan_staged(staged)                           # MANDATORY — not hook-dependent
    if outcome == HOOK_BLOCK or scan.blocked:
        persist_block_reason(ectx, scan.generic_reason)
        emit_commit_blocked_event(ectx, scan.generic_reason)
        write_provenance_audit(ectx, operation="commit_blocked",
                               reason_class=scan.generic_reason)
        return CommitResult(blocked=True, reason=scan.generic_reason)  # diff left in tree
    try:
        sha = sandbox.commit(message)                    # raises GitCommandError
    except NoChangeToCommit:
        return CommitResult(sha=None, no_change=True)    # distinct, not an error
    try:
        fire_hooks("post_commit", step, ectx,             # observation-only
                   commit_sha=sha, audit_operation=audit_operation,
                   audit_detail=audit_detail or {})      # reaches the observer's row
    except Exception:                        # Req 19 AC 3: an observer failure must
        log_observer_failure(ectx, sha)      # NOT roll back the commit or alter
                                             # control flow. Isolated here, at the
                                             # one place post_commit is dispatched.
    return CommitResult(sha=sha)
```

**The audit observer (Requirement 19 AC 3).** Every **commit-class** audit row —
`snapshot_commit`, `recovery_commit`, `fragment_merge`, `merge_agent_commit`, and
`restore` — is written by a **registered `post_commit` observer**,
`ProvenanceAuditObserver`, not by an inline call at each commit site. That is what
makes "success is recorded" hold for a commit path someone adds later. It declares
`events = ["post_commit"]`, is registered in both registry surfaces (INV-12's
two-surface rule), and writes through the owner-scoped store.

The operation class comes from an explicit `audit_operation` argument the caller
passes to `commit_in_sandbox`, **not** inferred from the staged path set — restore
and a recovery commit both stage `ALL_TRACKED` and would be indistinguishable
otherwise. Each commit therefore produces exactly one commit-class row; the
`operation="restore"` row in `restore_version` is the observer's row, not a second
inline one. `audit_detail` rides the same dispatch, and the observer maps its keys
onto the row's typed columns (`tag_name`, `source_ref`, `idempotency_key`) — which is
the only way Requirement 9 AC 11's "record the source tag" is reachable, since the
commit itself carries no trace of which tag was restored from. Keys outside that
allowlist are dropped, so the argument cannot become a smuggling route for content.

The observer stays observation-only: it cannot block, and the `try/except` around
the dispatch guarantees a raising observer cannot abort the commit or the finalizer.

Audit rows for operations where **no commit happens** — `run_ref_created`,
`run_ref_idempotent`, `run_ref_conflict`, `tag_created`, `tag_mapped`,
`status_published`, `chain_source_selected`, `chain_payload_installed`,
`chain_refused`, `legacy_migrated`, `commit_blocked`, and
`legacy_context_block_stripped` (the Requirement 13 AC 11 server-side strip) — are
written at their own call sites.

Three things matter here. The scan is **not** delegated to whether a manifest
declared `secret_scan` — a declared hook can add policy but cannot remove the
mandatory scan. It runs per commit, so a secret introduced on a worker branch is
blocked at that commit rather than tolerated because a later boundary diff happens
to be clean. And `staged.hook_payload` is the real staged content, not `""` — for
a binary-only staging set the textual diff is empty, so the payload falls back to
a content digest plus per-entry metadata so `pre_commit` hooks still see something
meaningful; `scan_staged` is unaffected either way because it reads entries
directly.

**Typed commit outcomes (Requirement 10 AC 7).** `commit_all` today returns `""`
for both "nothing to commit" and every `CalledProcessError`. V2 splits them:
`NoChangeToCommit` is a normal outcome surfaced as `no_change=True`; anything else
raises `GitCommandError`. A failed Git invocation must never be indistinguishable
from a clean tree, because that is what would let finalization proceed to ref, tag,
and published status on top of a reconciliation commit that never happened.

```python
def scan_staged(staged) -> ScanResult:
    for entry in staged.entries:
        if entry.is_binary:                              # Requirement 11 AC 14-16
            policy = binary_policy_for(entry.content_type, entry.size)
            if policy == "content_scan":
                result = scan_bytes(entry.raw)
            elif policy == "extract":                    # PPTX/DOCX/XLSX/ZIP
                result = scan_container(
                    entry.raw,
                    max_depth=EXTRACT_MAX_DEPTH,
                    max_bytes=EXTRACT_MAX_BYTES,
                    reject_traversal=True,               # no zip-slip: refuse any
                )                                        # member path with .. or an
                                                         # absolute/drive prefix
            elif policy == "block":
                return ScanResult(blocked=True, reason="binary_blocked")
            elif policy == "exempt":
                result = apply_recorded_exemption(entry)  # security-approved only;
                                                          # the approval id is stored
            else:
                return ScanResult(blocked=True, reason="binary_unknown_type")
        else:
            result = scan_text(entry.text)
        if result.blocked:
            return result
    return ScanResult(blocked=False)
```

Unknown binary type is fail-closed. Extraction treats archive contents as
untrusted, rejects any member whose normalized path escapes the extraction root,
and blocks on failure, exceeded bounds, or a malformed container. The `exempt`
branch is not a free pass: it requires a recorded, security-approved exemption id,
and the payload is marked accordingly so the exemption is visible in the audit.

### Family lock (Requirement 10)

```python
@contextmanager
def family_lock(user_id: str, revision_root_id: str,
                *, timeout: float = FAMILY_LOCK_TIMEOUT_S):
    """Cross-process, keyed (user_id, revision_root_id). Lock + active-run check
    are ONE atomic fail-closed operation. Order: family lock FIRST, then the
    per-sandbox manifest lock. Never the reverse.

    `timeout` defaults to the settings-backed `FAMILY_LOCK_TIMEOUT_S` so no call
    site can acquire without a ceiling; expiry raises `FamilyLockTimeout`, never
    proceeds unlocked. Only the bounded-wait upload arm of the Requirement 10 AC 10
    table overrides it, with a shorter ceiling, so a queued upload gives up well
    before the request itself does."""
```

Covers revision admission, shared-root open, dirty recovery, upload, restore, and
terminal finalization. Today none of these are serialized:
`_has_active_chain_revision` reads then mints with the whole function as the race
window, and the only cross-process lock in the codebase is a POSIX `flock` that
silently no-ops on Windows — so the family lock cannot reuse that mechanism.

**Upload admission per run state (Requirement 10 AC 10), documented in full:**

| Family state | Outcome |
|---|---|
| No active run | Accepted. |
| An agent step executing | Accepted, serialized behind the family lock, visible only as a complete file plus manifest entry. |
| Paused at a human or clarify gate | Accepted, same serialization. |
| Terminal finalization holds the lock | Rejected with a generic retryable reason, **or** queued behind the lock with a bounded wait. Never written concurrently with trace flush, payload assembly, or staging. |
| A restore holds the lock | Rejected with a generic retryable reason. |

Uploads stay under `.uploads/`, which remains reserved and untracked
(Requirement 10 AC 12).

### Restore (Requirement 9)

Restore is a REST command with no `ExecutionContext`, so it constructs a minimal
**`AuditContext`** — owner id, workspace id, run id, revision root id, and
`actor_id = user.id` — and passes that where the in-run paths pass `ectx`. That is
also the answer to where `ProvenanceAudit.actor_id` comes from generally: for an
engine-driven commit the actor is the run's owning principal
(`ectx.owner_id`); for a user command it is the authenticated caller.

```python
async def restore_version(run_id, tag, idempotency_key, user, db) -> RestoreResult:
    run = two_layer_owner_gate(run_id, user)                 # missing/cross-owner → 404
    root = resolve_revision_root(db, run_id, user.id)        # refuse on unresolved
    with family_lock(user.id, root):
        # Idempotency FIRST, before the active-family guard. A retried restore whose
        # first attempt already succeeded must return that same answer even if a new
        # run has since started in the family — otherwise the replay would be refused
        # `family_run_active` and the caller could not tell "your restore happened"
        # from "your restore was rejected."
        if prior := lookup_idempotent(db, user.id, idempotency_key):
            return prior                                     # no second commit
        if any_family_member_non_terminal(root, user.id):    # under the SAME lock
            raise Refused("family_run_active")               # generic reason to client
        safe_tag = validate_ref(tag, sandbox)                # exact match in list_tags()
        state = detect_persistent_git_state(sandbox)
        if state.dirty or state.merge_in_progress:
            reconcile_persistent_git_state(
                sandbox, message_class="restore-precondition")   # Req 10 AC 5
        materialize_tree_at_ref(sandbox, safe_tag)           # tracked tree only
        # The audit row is written by the post_commit observer from
        # audit_operation="restore" — NOT inline here, or a restore would leave two.
        audit_ctx = AuditContext(user, run_id, root)
        commit = commit_in_sandbox(sandbox, ALL_TRACKED, ectx=audit_ctx,
                                   message=f"restore: {safe_tag}",
                                   audit_operation="restore",
                                   # Req 9 AC 11 needs the SOURCE TAG, which the
                                   # observer cannot derive from the commit.
                                   audit_detail={"tag_name": safe_tag,
                                                 "source_ref": safe_tag,
                                                 # WRITES the replay key (Req 9 AC 10)
                                                 "idempotency_key": idempotency_key})
        if commit.blocked:              # a scan-blocked restore did NOT restore
            raise Refused("restore_blocked", reason=commit.reason)
        if commit.no_change:            # the tag's tree already IS the live tree
            # No commit ⇒ no post_commit ⇒ no observer row. Audit the no-op here,
            # or an honest no-op restore would leave no record at all.
            write_provenance_audit(audit_ctx, operation="restore",
                                   outcome="no_op", tag_name=safe_tag,
                                   idempotency_key=idempotency_key)
            return RestoreResult(commit=None, tag=safe_tag, no_op=True)
    return RestoreResult(commit=commit.sha, tag=safe_tag)
```

Both non-commit outcomes are explicit rather than reported as success. A blocked
restore is a refusal (Requirement 11 AC 12 applies on every commit path, restore
included). A `no_change` restore is an honest no-op — the requested tag's tracked
tree is already the live tree, so Requirement 9 AC 7's forward commit has nothing
to record, and the response says so rather than returning a null commit id as
though a commit happened.

**Where the idempotency key lives (Requirement 9 AC 10).** Both paths that *change
something* record the key, so both are replayable:

```python
def lookup_idempotent(db, owner_id, key) -> RestoreResult | None:
    """Reads the run_provenance_audits row the previous attempt wrote. The key is
    stored there rather than in its own table (Requirement 15 AC 10 reuse-first),
    under a partial unique index on (owner_id, operation, idempotency_key), which
    is also what makes two concurrent replays collapse instead of double-committing."""
    row = db.query(RunProvenanceAudit).filter_by(
        owner_id=owner_id, operation="restore", idempotency_key=key).one_or_none()
    if row is None:
        return None
    return RestoreResult(commit=row.commit_id, tag=row.tag_name,
                         no_op=row.outcome == "no_op")
```

Both values it needs are already typed columns on the row — no `detail` blob is
involved. The successful path supplies them through `audit_detail`, which the
`post_commit` observer maps onto `tag_name`, `source_ref`, and `idempotency_key`;
the no-op path writes them inline, because no commit means no observer dispatch. A **blocked** restore deliberately does *not* record the
key: nothing was restored, the block may be transient once the offending content is
removed, and burning the key would make a legitimate retry return a stale refusal.

Forward-only: every existing commit and tag survives. No `reset --hard`, no tag
rewrite, no branch moved backwards, no tag checked out into the live tree. The
restore commit consumes no `vN` ordinal — the next completed run overwrites the
flat payload and tags normally. `restore-precondition` is the fifth
reconciliation message class, alongside `cancelled`, `failed`, `degraded`, and
`crash-recovered` (Requirement 10 AC 5).

### Legacy relocation (Requirement 7 AC 1-3)

```python
def relocate_legacy_payloads(sandbox) -> list[str]:
    """Before the first v2 flat payload. Atomic per directory; bytes preserved;
    source removed only after the destination is durable; existing
    .chain-legacy/{run_id}/ is NEVER overwritten silently."""
```

After migration `.chain/` contains no directory. `.chain-legacy/` is excluded from
Git, Workspace listing, deliverables, zips, agent tools, and the ordinary
single-file API — all derived from the one registry.

---

## Fan-Out Merge Outcomes

*(Requirement 12)*

`on_conflict` stays exactly four compile-validated values, defaulting to
`human_gate`. What v2 adds is a documented outcome for each, durable state behind
the sequence, and a hard separation between *refused* and *conflicted*.

### Refused vs conflicted (AC 2)

`merge_worktree` already distinguishes them correctly via `MERGE_HEAD`
(`local.py:896`): a `CalledProcessError` with no `MERGE_HEAD` means Git never
started, so `MergeRefusedError` is raised and `conflicts: []` is never returned.
V2 fixes what the *caller* does with that distinction:

| Situation | Event | Documented outcome |
|---|---|---|
| Refused before start | `merge_failed` | Per `on_conflict`: `abort` → fail the run; `partial` → retain the applied set, mark this fragment failed, continue; `merge_agent` → do **not** invoke the resolver (there is no conflict to resolve) and fall through to `human_gate`; `human_gate` → pause for a decision. Never continue as though the fragment applied. |
| Started and conflicted | `merge_conflict` | Per `on_conflict`, below. |
| Strategy raised | `merge_failed` | Fan-out continues; the run is degraded. Never reported as `merge_completed`. |
| Commit blocked by the scan | `merge_failed` | Treated as a refusal for policy purposes (Requirement 11 AC 12) — the fragment did **not** apply, so it follows the refused-merge row above rather than continuing. |

That last row is the linkage Requirement 11 AC 12 demands: a worker or fragment
commit blocked by the secret scan must not let fan-out proceed as though the
fragment landed.

### Conflict artifact before event (AC 3-4)

`KernelServices.write_merge_conflict_artifact` (`kernel_services.py:924-964`) is
already owner/workspace-scoped and is already called before the event is emitted
in `_merge_fragments` (`fanout.py:~985`). V2 keeps that ordering and pins the
event contract: `merge_conflict.data.artifact_ref` carries the ref when
persistence succeeded, and a **generic reason** when it did not. No new table
(Requirement 15 AC 10) — the artifact rides `artifact_refs`.

### The four policies (AC 6-9)

**Cross-policy invariant (AC 5).** Under *every* policy, and for both a refusal and
a started-and-conflicted merge, **prior successful fragment merge commits stay
intact**. Nothing in the conflict path may unwind an already-committed fragment —
which is exactly the v1 defect where `git merge --abort` destroyed fragment 1's
work after fragment 2 was refused.

| Policy | Definition |
|---|---|
| `abort` | Raise `FanoutError`; the run fails. |
| `partial` | **Retained state is defined as: every fragment whose merge already committed, plus nothing from the conflicting fragment.** The conflicting merge is aborted (`git merge --abort`), its fragment is marked `dropped` in the durable state, and its per-file fragment artifacts remain in `artifact_refs` for recovery. Subsequent fragments continue. The retained set is recorded in `FanoutMergeState.retained_state` so it is inspectable rather than implied. |
| `merge_agent` | The manifest-declared resolver, bounded at `MERGE_AGENT_MAX_ATTEMPTS` (`budget.py:58`, = 2). Each attempt must materialize a **clean, verified** result — no conflict markers, and the step's declared validators pass — and that result is **committed through the commit primitive before success is reported**. An unresolved bound falls through to `human_gate`; no oscillation past the bound. Its only context input is the owner-scoped conflict artifact plus bounded instructions and the attempt count (Requirement 14 AC 5). |
| `human_gate` | Routes through the one durable HITL (`runner.run_human_gate` → `_run_review_gate`). The decision is persisted in **`gate_events`** — not held in memory — so a resume re-enters the same merge state machine at the recorded fragment. |

### Durable merge state (AC 11)

`fragments_meta` is an in-memory `list[dict]` today (`fanout.py:399`), so an
abrupt crash mid-merge is unclassifiable — which is why Requirement 10 AC 15 could
not distinguish "resume the recorded fragment" from "unknown merge in progress".
V2 records `FanoutMergeState` **before each merge attempt**: declared fragment
order, the fragment currently in flight, and each fragment's outcome. All fan-out
commits go through the commit primitive.

### Cancellation (AC 9)

Existing teardown already retains unmerged worker branches while removing worktree
directories (`fanout.py:702-725`, `delete_branch=not _cancel_active`) — keep that.
V2 adds what the new state requires: cancellation **clears the durable merge state
and the worktree registrations**, so a later resume does not attempt to continue a
merge that was abandoned. Retaining the branches while clearing the state is the
correct pair: no work is lost, and no stale in-flight fragment is replayed.

---

## `.context/` Determinism, Inheritance, and Resume

*(Requirement 8)*

`.context/` is one directory per physical sandbox, so a revision family shares it.
That is deliberate — it is what makes a revision see the same design inputs as the
run it revises — but it means inheritance and overwrite rules have to be explicit.

**Producer (AC 1-2).** OpenDesign files come from the same
`resolve_launch_od_context` result launch already uses; `write_od_context_to_sandbox`
writes `.context/design/` and `.context/selections.json` fully before step 1.

**Inheritance (AC 3).** A revision opens the revision root's sandbox, where
`.context/design/` and `selections.json` already exist. The writer is
inheritance-aware:

```python
def write_od_context_to_sandbox(sandbox, od_context, *, explicit_selection: bool):
    """A revision INHERITS the root's design context unchanged unless the revision
    request explicitly supplied a newly resolved design selection."""
    if context_already_present(sandbox) and not explicit_selection:
        return                      # inherit — do not rewrite, do not re-resolve
    _write_od_context_to_sandbox(sandbox, od_context)
```

`explicit_selection` is true only when the revision request carried a resolved
template/design-system choice. Without it, a revision must not silently re-resolve
and overwrite the family's design inputs.

**Chain payload (AC 4-5).** A chained run receives the three files at the
`.context/` root. Installation never touches `.context/design/` or
`selections.json`; the atomic install writes only the three flat names.

**Resume (AC 6).** `resume_run` rebuilds `ectx.od_context` from the persisted files
via `rebuild_od_context_from_sandbox` (`launch_context.py:114`), which already
wins over the `od_context_json` DB column. V2 adds the chain half: an already
installed `.context/` chain payload is **preserved byte-for-byte** — resume does
not re-read the source ref, does not re-copy, and does not overwrite. Re-installing
would be observable (a source tag could have been swept between the original run
and the resume) and would break AC 8.

**Visibility (AC 7).** `.context/` stays gitignored, listed in the Workspace
surface, excluded from deliverables — and **readable to authorized agents**. That
last clause is why the registry carries `AGENT_READABLE_RESERVED`, containing
`.context/` and nothing else: the agent-tool guard refuses *writes* to every
registry path and permits *reads* of `.context/` only. `.chain/` is read-visible
through the Workspace listing and authorized-ref reads (Requirement 4 AC 10), not
through agent tools — Requirement 18 AC 6 scopes reserved read-visibility to "the
authorized Workspace surfaces", and Requirement 18 AC 8 requires the test to prove
an agent file tool can neither read nor write it. Widening the agent read set to
`.chain/` would make something *more* visible than v1, which the supersession
matrix's "retained exclusions" row forbids.

**Determinism (AC 8).** A resumed and an uninterrupted execution with the same
inputs observe byte-identical `.context/` files. Three mechanisms deliver it:
the design writer is deterministic given one `od_context`; the inheritance guard
prevents a second write from producing different bytes; and the chain payload is
preserved rather than re-fetched.

---

## Prompt Assembly and the 30-Row Input Ledger

*(Requirement 13)*

### Policy and governance

Manifest prompt-policy selection defaults to `default` when omitted or empty; an
unknown non-empty policy fails compilation with a clear error (AC 1). The body-only
policy applies **only to ungoverned agents** — a governed agent keeps its
guardrails, behavioural hooks, Constitution, and `AGENT.md` (AC 2).

Three prohibitions that are easy to violate while "simplifying" the prompt:

- **`SKILLS_SYSTEM_PROMPT` survives (AC 3).** Removing the factory `skills` block
  removes the *factory's* rendering of it, not deepagents' own skill prompt.
  Staged skills stay discoverable, and a test proves it.
- **`REQUEST.md` is never created (AC 4).** The user request goes to agent 1's
  initial message. The engine does not write it to disk and does not propagate it
  to downstream agents — with the sole exception of the Requirement 14 retry
  classes, which deliver it to one targeted agent.
- **Every migrated first step produces a durable contract artifact (AC 5).** Later
  agents read declared files plus their own task. This is a precondition for
  deleting Seam 2 (AC 8), not an afterthought.

### The 30-row ledger (AC 6) — normative, no blank destinations

Reproduced here rather than deferred to v1. V1's copy cannot be relied on: its
row 24 destination ("`.context/` carries copied `.chain/{run_id}/`") describes the
nested layout V2-Q2 retires and Requirement 7 relocates; its row 8 lacks the
Requirement 14 retry exception; and its fourth column cites v1 requirement numbers
that the supersession matrix marks Replace or Amend.

| # | Current input | V2 destination / recipient | V2 req |
|---:|---|---|---|
| 1 | tool-availability text | Dropped; provider tool schemas remain authoritative | 13 |
| 2 | template/design/craft injection | `.context/design/` | 8 |
| 3 | guardrails | Governance system-prompt order | 13 AC 2 |
| 4 | skills block | Deepagents skill prompt; staged `skills/` paths | 13 AC 3 |
| 5 | behavioural hooks | Governance system-prompt order | 13 AC 2 |
| 6 | Constitution | Governance system-prompt order | 13 AC 2 |
| 7 | prompt body | Agent's `AGENT.md` | 13 |
| 8 | original brief | Agent 1 initial message only, **except the Requirement 14 retry classes** | 13 AC 4, 14 |
| 9 | conditional retry feedback | Targeted retry control payload | 14 AC 2 |
| 10 | planner analysis | `PLANNER.md`, written after clarify merge | 13 |
| 11 | active design/template material | `.context/design/` | 8 |
| 12 | upstream agent output | `.agents/{NN}-{agent_id}.md` | 13 |
| 13 | prior output on redo | `.agents/{NN}-{agent_id}-p{visit-1}.md`, named in the control payload | 14 AC 2 |
| 14 | HITL revise directive | Targeted redo control payload | 14 AC 3 |
| 15 | prior revision spec/tasks | Shared sandbox root files | 3, 8 |
| 16 | mid-run user guidance | Consume-once targeted control; sticky uploads stay `.uploads/` | 14 AC 7 |
| 17 | revision analysis | Analyzer artifact and `.agents/01-*.md` | 13 |
| 18 | current prototype plus instruction | Prototype file; instruction follows brief-recipient rules | 13, 14 |
| 19 | current task | Targeted task control; durable task stays in `tasks.md` | 13 |
| 20 | compacted build skeleton | Worker reads the current output file from the sandbox | 13 |
| 21 | template-compliance ids | `.context/selections.json`; rule in `AGENT.md` | 8 |
| 22 | multimodal blocks | Unchanged typed multimodal input | — |
| 23 | launch `od_context_json` | `.context/`; resume rebuilds in-memory context | 8 AC 6 |
| 24 | frontend enriched chain text | **Removed for new launches**; the exact-ref payload is in `.context/`. Historical marker-bearing runs stay readable — transition governed by 13 AC 11 and 21 AC 5–10 | 13 AC 11, 21 |
| 25 | previous-run seed/pointer | Shared revision tree; redundant seed short-circuited (provider retained) | 16 AC 4 |
| 26 | uploaded-files context | `.uploads/` raw and extracted sidecars | 10 AC 12 |
| 27 | staged skills | Unchanged `skills/` directory | 18 AC 3 |
| 28 | validation-fix message | Targeted control with validation errors and the file path | 14 AC 4 |
| 29 | planner design-context argument | In process; rebuilt from `.context/` on resume | 8 AC 6 |
| 30 | other `ectx.od_context` readers | In process; rebuilt from `.context/` on resume | 8 AC 6 |

Each row records normal, retry, redo, resume, and chained-run behaviour in tests,
or carries an explicit not-applicable assertion (AC 7). Rows 22 and 27 are the
expected not-applicable cases.

### Seam 2 removal preconditions (AC 8)

Per workflow, and only after all four hold: the workflow is inventoried, its first
durable artifact is verified to exist, its manifest is migrated, and its prompt
snapshots are reviewed. `prototype` is last.

### Prompt viewer and overrides (AC 9-10)

The prompt viewer displays the effective system prompt **plus** the targeted
control payload. It must never show a misleading empty-context message — with
file-based context the human message is legitimately short, and a viewer that
renders that as "no context" would hide the migration's actual behaviour.

Prompt overrides remain replacement bodies, and the API documentation says so
rather than implying composition. Production override migration stays deferred to
the v1 trigger unless product state has changed (supersession rows 37–39).

---

## Retry and Redo Recipient Matrix

*(Requirement 14)*

Retries are where broadcast prompt pollution comes back, because the honest fix for
"the agent does not know why it was sent back" is to re-inject everything. The
ledger's row 8 exception exists for exactly these five classes and no others.

| Class | Delivered to | Payload | Not delivered |
|---|---|---|---|
| **Provider / transient retry** of the same model invocation (AC 1) | Nobody new | The **same already-built message**, same checkpoint semantics | No second brief, no additional block |
| **Conditional-gate backward retry** (AC 2) | The retrying agent, **once** | Its task, the original user brief, pass number and limit, source step, source output, authored feedback, previous-output file path | Any other agent |
| **Human-gate redo** (AC 3) | The redone agent only | Original brief + the targeted rejection/revise directive, on a **fresh redo checkpoint thread** | Any other agent; the base thread is not reused |
| **Validation-fix loop** (AC 4) | The fixing agent | Validation errors + the exact deliverable path | Unrelated upstream context |
| **Merge-agent attempt** (AC 5) | The merge worker | Owner-scoped conflict artifact, bounded resolution instructions, attempt count | The original user brief, by default |

**Resume and replay (AC 6).** A resumed dispatch preserves the recipient rules of
the interrupted dispatch. A consume-once control payload already delivered is
**not** replayed — the durable record of the dispatch, not the in-memory scratch,
decides whether it was consumed.

That durable record is **the existing per-agent invocation row, not new
persistence**: a redo is already keyed by its fresh `{run_id}:{agent}:redo{N}`
checkpoint thread, and a conditional-gate retry pass is already identifiable from
the durable artifact/`gate_events` history for that step. Resume therefore derives
"was this control payload already delivered?" from the highest recorded
redo/pass index for the step, exactly as `resume_completed_task_ids` derives its
skip cursor from durable rows today. No new table and no new column: Requirement 15
AC 10 asks for reuse before addition, and inventing a "dispatch consumption" table
would duplicate state the checkpoint thread and the gate history already carry.
If implementation proves the index is not recoverable from those rows, the fallback
is an additive nullable column per Requirement 15 AC 5 — and that decision must
update this map first (Requirement 1 AC 5).

**Draining (AC 7).** All consume-once scratch is drained **unconditionally** every
dispatch iteration, on the empty-output, errored, and non-retry paths alike. The
existing F3 pattern (set around the compose call, clear immediately after,
regardless of outcome) is the mechanism; the failure mode it prevents is a redo
directive leaking onto the next agent.

**Verification (AC 8).** Full-composer tests, for every class above, for a first
agent and a non-first agent. Neither source inspection nor a dictionary-pop
simulation counts — the composer must actually run and its output be asserted.

---

## Error Handling

**`revision_root_unresolved`.** One typed failure for a null principal, a cycle, a
missing ancestor, cross-owner ancestry, and a DB error. Every caller refuses; the
sweeper protects. Client gets a generic non-enumerating error; the server logs
visited-set size, repeated node, and failure class. No caller invents its own
fallback — which is precisely how v1's "use the last unique node" produced a wrong
directory that looked right.

**Blocked payload (V2-Q9).** The metadata-only snapshot resolves the conflict
between "every terminal run gets a ref" and "a blocked payload is not committed":
`summary.md` alone, `payload_chainable: false`, a generic reason, no `logs.jsonl`,
no output bytes, no excerpt of the blocked material. It still gets a snapshot
commit and an internal ref so re-entry stays idempotent, and it gets **no** visible
tag. The index is reset before the metadata-only commit — without that, the blocked
bytes staged for the first attempt would be swept into the snapshot built to
exclude them. Blocked content never becomes reachable from any commit, tree, tag,
ref, base branch, retained worker branch, reflog entry created by finalization, or
event payload.

**Unmaterializable output.** Same construct, different trigger: reason
`output_unmaterializable`, `payload_chainable: false`, published `degraded`, no
visible tag. Requirement 4 AC 16 names both triggers; both reach the same code
path.

**Present-but-different internal ref.** `run_finalization_failed`, published
`degraded`, both commit ids recorded, existing ref preserved, `post_run` still
fired. Never overwritten, never self-healed.

**Required commit or tag failure.** A commit that *fails* (as opposed to being
blocked) and a tag-or-mapping failure both emit `run_finalization_failed`, publish
`degraded`, and never report a completed version — the same treatment as a ref
conflict (Requirement 5 AC 10).

**Tag created then DB mapping fails.** Retry the mapping; if it still fails, remove
*only* the tag this attempt just created and report degraded. That removes a tag
that was never successfully published — it is not a repoint, and it is the one
exception to the no-tag-mutation rule (Requirement 5 AC 9, AC 22).

**Chain source ineligible.** Five distinct reason codes.
`source_running` and `source_not_finalized` are retryable;
`source_non_chainable`, `source_payload_missing`, and
`source_provenance_conflict` are not retryable by the same choice. Degradation to
empty context is reachable **only** for `source_payload_missing` on an *eligible*
source **and** only when the compiled `chain_policy` is `degrade`. Ineligibility
and provenance conflict never degrade. All of it is decided **pre-mint**, so a
refusal leaves no run row and no persisted edge — with the single named TOCTOU
exception (**N3**), where the validated payload disappears before the install and a
`refuse` policy fails the already-created run with `chain_context_installed = false`.

**Crash with persistent Git state.** Each detected state has exactly one outcome:
recorded merge state → resume at the recorded fragment; unrecorded merge → abort,
retain all worker branches, `crash-recovered` reconciliation commit; stale
`index.lock` with no live owner → remove and record (a live owner is an explicit
failure, never a forced removal); orphan worktree registration → prune, retain the
branch; unmerged worker branches → retain and surface for operator inspection;
corrupt or unreadable repo → quarantine the family, refuse all writes, require
operator action, never delete or reinitialize; any other Git command failure → an
explicit typed failure, never interpreted as clean. Staged, unstaged, and untracked
changes are all preserved by the reconciliation commit — which is why the non-success
reconcile at finalizer step 2 stages tracked **and** untracked content rather than
tracked only.

**Refused vs conflicted merge.** `MergeRefusedError` (no `MERGE_HEAD`) is a
refusal — `merge_failed`, then the documented per-policy outcome. It never
continues as though the fragment applied, and never reports `conflicts: []`. Prior
successful fragment commits stay intact. A scan-blocked worker or fragment commit
takes the same path.

**Upload during finalization.** Rejected with a generic retryable reason, or queued
behind the family lock with a bounded wait. Never written concurrently with trace
flush, payload assembly, or staging. An upload is atomically visible: bytes durable
→ manifest entry → response.

**Rejected reserved seed entry.** A `seed_files.from_run` entry naming a registry
path is rejected at compile time with a manifest error **naming the offending
entry**, and again at runtime as defence in depth. The rejection does **not** fall
back to a default seed set — falling back would copy files the manifest never
intended, which is the leak this guard exists to prevent. The rejection is logged
without leaking file contents (Requirement 18 AC 11-12).

**Unknown reason code (frontend).** Falls back to the generic message rather than
crashing or rendering empty — which also satisfies the rollback-reader tolerance of
Requirement 17 AC 4.

**Mixed deploy.** New frontend against an older backend degrades to no chain
context and surfaces the Requirement 20 AC 4 reason rather than launching without
provenance. Older frontend against a new backend has its legacy text block
rejected or ignored, never combined with the file payload. Any other combination is
named as unsupported in the error rather than left undefined.

---

## Invariant Compliance

| Invariant | Mechanism | Status |
|---|---|---|
| **SC-001** — zero engine edits for a new workflow | The chain gate is read from the compiled plan (`deliverable.chains_from` + `chain_policy`), never a workflow id. `_extract_chain_context`'s seven hardcoded branches stay frozen in the API layer and are not extended. `grep "if pipeline_type ==" agents/execution_engine/` stays 0; `grep 'spec\.id ==' agents/execution_engine/` stays 0. | Pass |
| **INV-1** — name-free kernel | Every new gate is a generic ctx field, a compiled declaration, or a registry lookup. | Pass |
| **INV-3** — byte-identical goldens | New reserved path, internal refs, finalization records, and audit rows are dormant on golden runs. `current_run_id` defaults to the root id, so a root-only golden produces the identical `.logs/` path. Prompt-migration baselines are the only reviewed re-baseline. | Pass with reviewed re-baseline |
| **INV-7** — engine-decided isolation | `_select_isolation_scope` still keys solely on `has_git`. Unchanged. | Pass |
| **INV-12** — no dual implementations | The whole point: eight reserved-path lists → one registry; two root walks → one resolver; six commit paths → one primitive; two ordinal walks → one; in-memory merge state → one durable record. | Pass |
| Workspace port stays shut | `create_run_ref`, `resolve_ref_commit`, `materialize_tree_at_ref`, `detect_persistent_git_state` land on `LocalWorkspace` via `getattr` duck-typing, as `create_tag`/`list_tags` already do. Three import-linter contracts stay green. | Pass |
| Additive migrations only | Two new tables (`run_finalizations`, `run_provenance_audits`), two new nullable `WorkflowRun` columns, plus durable fan-out merge state as either an additive column set on `wave_runs` (preferred, per Requirement 15 AC 10's reuse-first rule) or a third table if that scope does not fit. No column removed or renamed. Verify one Alembic head (currently **0041**) before creating anything. | Pass |
| SSE/REST transport split | Two new event types on the existing down-channel; restore is a REST up-channel command. No WebSocket touched; `/ws/handoff` untouched. | Pass |
| Import boundaries | `chain_context` keeps importing only stdlib + registry. Every sandbox, ref, and persistence fact it needs arrives through the `ctx.services` (`KernelServices`) handle the runner already injects — `open_source_sandbox`, `read_finalization_record`, `mark_chain_context_installed`, `write_provenance_audit` are all methods there. `KernelServices` may import `app.*`; the provider still may not. Selection and validation run app-side in `run_commands.py`, which is above the boundary anyway. | Pass |
| Closed Workspace Protocol | No new method is added to the `Workspace` Protocol in `agents/runtime/base.py`. | Pass |

---

## Named Departures from the Requirements

Three places where this design does not do exactly what an acceptance criterion
says, each because two criteria pull against each other or because the literal
reading produces a worse outcome. They are collected here so review can accept or
reject them explicitly rather than discover them in code.

| # | Criterion | What the design does instead | Why |
|---|---|---|---|
| N1 | **Req 5 AC 12** — the terminal event follows a *durable* finalization record | If the record cannot be written even on the retry, the terminal event fires anyway; the run publishes `degraded` with the DB-failure reason class and the unpersisted state is logged for operator recovery | The literal reading leaves a run with no terminal state and an SSE stream that never closes. Bounded to the double-write-failure case only. |
| N2 | **Req 6 AC 10** — a missing, swept, *or corrupt* payload may degrade | Missing and swept degrade; **corrupt refuses**, as `source_provenance_conflict` | AC 3 and AC 7 say a provenance disagreement SHALL be refused and SHALL NOT fall back. Degrading on disproved provenance is the outcome AC 7 exists to prevent, so `chain_policy: degrade` covers absence, not disproof. |
| N3 | **Req 6 AC 16** — a run refused a payload SHALL NOT carry the persisted edge | Holds for every reason class except one: the payload validated at admission and deleted before the install, under `chain_policy: refuse`. That run fails with the edge intact and `chain_context_installed = false` | AC 16's own first sentence requires the edge to be written atomically with run creation, so it cannot be rolled back without destroying the record of which source was authorized. `chain_context_installed` is the durable discriminator instead. |

Each is covered by a test that asserts the departure's *bounded* form, so a future
change cannot widen it silently.

---

## Requirement Traceability

Requirement-level map. The acceptance criteria this design had to introduce new
structure for are named individually.

| Req | Primary design element |
|---|---|
| 1 | "Precedence, Supersession, and Retained v1 Obligations" — v2-wins rule (AC 1), Retain table (AC 2), no-checkbox-evidence rule (AC 3), normative component map (AC 5). AC 4's six corrections: four are Overview defect rows (D1 source-based walk, D2 root-id log path, D3 early finalizer, D4 ignored/nested payload); the fifth, missing restore, is an *absence* rather than a defect row and is designed in "Restore"; the sixth, incomplete prompt migration, is covered in L9 and "Prompt Assembly and the 30-Row Input Ledger". D5 (`pre_commit` fired with an empty payload) is a seventh defect this design found beyond AC 4's list, closed by the one commit primitive |
| 2 | `resolve_revision_root` + `RevisionRootUnresolved`; non-null principal (AC 4); harness no-DB path (AC 6); all nine AC 7 consumers, plus upload and the chain-source read this design adds (AC 7); sweeper re-key (AC 13-17) |
| 3 | Two-id `RunSandbox`; `RunTrace` fix; four-class flush at finalizer step 3 (AC 6) |
| 4 | Flat payload; `payload_allowlist`; `summary.md` schema; temp-sibling assembly + stale-basename reconciliation (AC 9); metadata-only snapshot for both triggers (AC 16) |
| 5 | `finalize_terminal_run` 12 steps with exactly one exit; `CandidateOutcome` vs `FinalizationRecord` (complete projection only, over an all-nullable row with three states); ref CAS; commit-message content rule (AC 11); `WorkflowRun` chainability columns (AC 17); one named relaxation of AC 12 (**N1**) |
| 6 | `admit_chain_launch` + `select_source_payload` (pre-mint, so AC 16's "refused ⇒ no edge" holds for every non-degradable class) and `install_chain_context` (byte copy only); compiled activation gate (AC 13-15); terminality-before-record ordering (AC 17-19); output-filename provenance (AC 7); `chain_policy` (AC 10, with the corrupt-payload narrowing named); 404 for missing source (AC 1); one TOCTOU narrowing of AC 16 named and tested |
| 7 | `relocate_legacy_payloads`; `select_legacy_payload` + `install_legacy_chain_context` with the full content rules (AC 6), `_validate_ref` on the stored tag (AC 10), untagged-legacy eligibility (AC 11); `is_legacy_source` as the single feature predicate for both AC 9 disjuncts, answered from Git |
| 8 | "`.context/` Determinism, Inheritance, and Resume" — inheritance guard (AC 3), resume rebuild + payload preservation (AC 6), `AGENT_READABLE_RESERVED` (AC 7), determinism mechanisms (AC 8) |
| 9 | `POST /{id}/restore`; `materialize_tree_at_ref`; browse-path prohibitions (AC 3); the replay key on `run_provenance_audits` with `lookup_idempotent` ordered ahead of the active-family guard (AC 10); the source tag carried to the audit row via `audit_detail` (AC 11) |
| 10 | `family_lock`; five-state upload admission table (AC 10); `detect_persistent_git_state` incl. Git-command-failure (AC 6); typed `commit_all` outcomes (AC 7) |
| 11 | `commit_in_sandbox`; real `pre_commit` payload; `scan_staged` with zip-slip guard and approved exemptions (AC 15); `post_run` on all five outcomes (AC 6) |
| 12 | "Fan-Out Merge Outcomes" — refused-vs-conflicted table (AC 2), artifact-before-event (AC 3-4), four policy definitions (AC 6-8), cancel clears state (AC 9), `FanoutMergeState` (AC 11) |
| 13 | "Prompt Assembly and the 30-Row Input Ledger" — full ledger (AC 6), `SKILLS_SYSTEM_PROMPT` (AC 3), no `REQUEST.md` (AC 4), first-step artifact (AC 5), viewer (AC 9), overrides (AC 10) |
| 14 | "Retry and Redo Recipient Matrix" — five classes, resume rules, unconditional draining, full-composer verification |
| 15 | Two additive owner-scoped tables + two nullable columns; chain-edge projection; finalization consistency check (AC 6); no `has_git` column, no tag cache |
| 16 | "Scope and Non-Goals" — bounded UI (AC 1), all excluded items (AC 2, 5, 11), retained `previous_run` (AC 4), frozen `_extract_chain_context` (AC 6), L10 test surfaces (AC 8), restore-only history command (AC 12) |
| 17 | Rollout order with the family lock in the identity stage (AC 2); named required tests (AC 7, 13); pipeline-controlled apply (AC 12); rollback verification (AC 18) |
| 18 | `RESERVED_PATHS` + the twelve-point enforcement table; no-default-fallback rejection (AC 12) |
| 19 | `ProvenanceAudit` (typed columns only, no `detail` blob) + registered `post_commit` observer (AC 3); `chain_source_selected` scoped to the receiving run in the mint transaction and `chain_refused` scoped to the actor, which is what makes bidirectional reconstruction answerable (AC 1, 6); fail-closed writes (AC 7); 13-month retention (AC 8) |
| 20 | Event schemas; five reason codes; `RunEngineNotice`; degraded-vs-completed distinguishability (AC 5); dual projection sources (AC 3) |
| 21 | Indicator on run-detail and revision-family (AC 1); chain-vs-revision distinctness (AC 3); presentation precedence (AC 8); mixed deploy (AC 9); warning content (AC 12); status via the chainable invariant (AC 14) |

| Gap | Design element |
|---|---|
| 001 | `RESERVED_PATHS` + all twelve enforcement points incl. `serialize_sandbox_deliverable`, `count_sandbox_deliverables`, `WorkflowRun.output`, zip; the agreement test |
| 002 | Registry-derived selector guard, path normalization, named-entry compile error, no default-seed fallback |
| 003 | Compiled `chains_from` activation gate |
| 004 | `source_run_id` in the launch transaction + projection + indicator on both named surfaces |
| 005 | Ledger row 24 transition, versioned storage cleanup, marker parser retained, presentation precedence, mixed deploy |
| 006 | Upload under the family lock; documented order; five-state admission |
| 007 / 008 | `commit_in_sandbox`; `scan_staged` binary policy with traversal rejection |
| 009 | `detect_persistent_git_state` at four entry points; `FanoutMergeState` |
| 010 / 016 | Eligibility gate; terminality-first ordering; publication ordering for all five statuses |
| 011 | Metadata-only snapshot for **both** triggers, with the index reset |
| 012 / 013 | `CandidateOutcome` vs `FinalizationRecord`; `intended_tag` as intent; the chainable-divergence invariant |
| 014 | `create_run_ref` CAS; `run_finalizations`; `source_provenance_conflict` as its own code |
| 015 | Feature-based detection; legacy tagged **and untagged** sources; `_validate_ref` on the stored tag |
| 017 | Chain-source picker with status + incompleteness warning |
| 018 / 019 | Sweeper re-key with active-or-paused protection; `revision_root_unresolved` |
| 020 | `ProvenanceAudit` + observer + retention + bidirectional queries |
| 021 | Event schemas + reconnect replay + accessible rendering + degraded distinguishability |

---

## Testing Strategy

Source inspection does not count as acceptance for restore, lifecycle dispatch,
locks, or prompt recipients (Requirement 17 AC 8). Security closures are verified
by behaviour, not by reading code (Requirement 17 AC 14).

### Identity and lineage (real DB)

Root plus two revisions in one physical sandbox produce three distinct
`.logs/{run_id}.jsonl` files, and each chain snapshot contains only the selected
run's trace. A depth-two revision shares its family root while a chain from that
revision gets a different root. Self-parent cycle, two-node cycle, missing
ancestor, cross-owner ancestry, and a null principal each refuse identically at
**every** caller — launch, revision admission, all four file routes, upload,
restore, previous-run reads, family locking, resume, and the factory. TTL sweep:
a family whose root row is terminal and whose descendant is **active** still has
its sandbox and Git history after a sweep; the same with a **gate-paused**
descendant past TTL; a fully terminal expired family is still swept; a resolver
failure protects the directory.

### Payload and refs (real Git)

`v1`/`v2`/`v3` expose the identical three `.chain/` paths with different bytes, and
no `.chain` directory entries or agent transcripts. **Ref-scoped archive**: a
completed tag's `git archive` output contains exactly the three flat files and no
registry path. Chaining from `v1` after `v3` exists yields `v1`'s bytes. Chaining
from a mid-family revision, from an untagged failed run, and with a binary output
each receive only the selected source bytes. A renamed deliverable leaves no stale
tracked basename in `.chain/`. Repeated finalization, a manually corrupted ref, and
a ref that survives while the tag is absent all behave per the CAS contract. The
tag, the internal ref, and the commit whose `summary.md` names that same
`intended_tag` and run id all resolve to one commit (Requirement 5 AC 22).

### Finalization (real Git + real DB)

Failure injected at each of the five points in Requirement 5 AC 3 — before commit,
after commit before ref, after ref before tag, after tag before mapping, after
mapping — converges on retry to one consistent description of published status,
record, ref, and tag. At **each** of those crash-and-retry points, a fixture whose
staged content carries a secret is asserted never to appear in
`git rev-list --objects --all` for the sandbox (Requirement 5 AC 18). A blocked
payload and an unmaterializable output each produce a metadata-only snapshot, an
internal ref, `payload_chainable=false`, `degraded`, and no tag. `post_run` fires
exactly once for completed, cancelled, failed, degraded (including
degraded-by-ref-conflict), and diverted. Every terminal emission path is
enumerated and proven to reach one finalizer and one `post_run` dispatch
(Requirement 11 AC 8). Immediate chaining after each of the five terminal statuses,
launched as early as the terminal event is observable, either delivers the exact
payload or produces an explicit refusal — never silently empty. A commit message is
asserted to contain the run id and status and no user content.

### Chaining refusals and legacy (real Git + real DB)

Four ineligible-source fixtures, each asserted to yield its own reason code and no
empty-but-successful launch: a **running** source, a **terminal-but-unfinalized**
source, a **secret-blocked** source, and an **unmaterializable-output** source
(Requirement 6 AC 19). A tag/ref disagreement and a `summary.md` run-id or
output-filename mismatch each refuse as `source_provenance_conflict` and never
degrade. **Every one of those refusals additionally asserts that no `WorkflowRun`
row was created and no `source_run_id` edge persisted** — the behavioural form of
Requirement 6 AC 16, and the only way to prove the provenance checks really run
before the mint rather than in-run. A source with no finalization record and *with*
an internal run ref is refused `source_not_finalized` rather than read as legacy,
which is the assertion that keeps the legacy predicate from failing open. The single
permitted exception is exercised directly: with the payload validated at admission
and then deleted before the install, `chain_policy: degrade` yields
`chain_context_unavailable` with the edge intact, and `chain_policy: refuse` fails
the run with the edge intact and `chainContextInstalled: false` — and no other
fixture is allowed to reach that state. Three legacy fixtures: a legacy completed run with a tag and a live nested
payload; the same run after its nested payload was swept; a legacy **untagged**
terminal run — and in all three, **no internal ref is ever created for a legacy
source** (Requirement 7 AC 12). A legacy stored tag that is not in the owned
sandbox's visible tag list is refused before any Git subprocess runs. Legacy
fallback order is asserted: `.chain-legacy/` first, then the unmigrated live
`.chain/{run_id}/`, and never live flat `.chain/`, another run's directory, the
latest tag, or `HEAD`; provenance is `legacy-live-nested`.

### Security (behavioural)

After a completed run and after a restore: `git log --name-only` and
`git show --stat` contain no registry path except the three allowlisted files;
`list_files`, the deliverable walk, deliverable counting, the zip, `WorkflowRun.output`,
and the public-share output contain none of them, nor `.git/`, nor `.gitignore`; an
agent file tool cannot **write** any registry path, cannot **read** any registry path
except `.context/`, and specifically cannot read `.chain/` (Requirement 18 AC 8) —
whose read-visibility is the Workspace listing and authorized-ref reads only. A
dedicated test asserts the **enforcement points and
the registry agree** — enumerating each point's effective exclusion set and
comparing it to `RESERVED_PATHS`, so the v1 "two separate lists" failure mode
cannot recur (Requirement 18 AC 2).

Every registry entry is tested in both slash and bare form plus nested paths
beneath it, including a manifest declaring only reserved entries, plus an
end-to-end assertion that **no reserved content is written into the receiving
sandbox** and that a rejected entry does not fall back to a default seed set
(Requirement 18 AC 13).

A planted secret at each commit path in Requirement 11 AC 10 is unreachable from
every tag, internal ref, base branch, and **retained worker branch** — asserted by
`git rev-list --objects --all` object enumeration, not a tip diff. A committed PPTX
fixture with an embedded secret marker in its internal parts is detected and its
commit blocked (or the exemption is explicitly recorded with its approval id). A
container whose member path escapes the extraction root is blocked. "Binary files
differ" is never accepted.

A stray `source_run_id` on a workflow **without** the chain declaration performs
zero cross-run reads: no ref resolution, no `git show`, no source sandbox `stat`,
no `.context/` chain files — asserted at both the launch gate and the provider gate.

The chain reader is proven to read the **source's** sandbox, not the receiving run's:
a test chains into a brand-new sandbox and asserts the payload still arrives, and a
negative test plants a tag name that resolves in neither sandbox and asserts the
tag-versus-ref check **refuses** rather than passing on two `None`s.

### Concurrency and recovery (real Git)

Upload versus upload, versus active agent, versus restore, versus finalizer: no
upload lands inside a terminal snapshot commit and no snapshot is built from a
half-written upload. All five upload-admission states are asserted. Restore versus
run and restore versus restore serialize; a repeated idempotency key returns the
first result with no second commit. Crash injection at each persistent Git state
and at each restart point — before the first fragment merge, between fragment
merges, during a fragment merge, **after a recovery commit and before state
persistence**, after the last fragment merge and before finalization, and inside
finalization — converges with no duplicate merge commits, no duplicate recovery
commits, and no lost worker branches, with the reconciliation message class
asserted for all five classes including `restore-precondition`. Staged, unstaged,
and untracked content all survive reconciliation. A Git command failure is proven
to raise rather than read as a clean tree.

### Fan-out (real Git)

Conflict and refusal on the **first** fragment and on a **later** fragment. All
four `on_conflict` policies, with `partial`'s retained set asserted explicitly.
Under every policy, and for both a refusal and a conflict, an already-committed
prior fragment is asserted still present. Resolver exhaustion falls through to
`human_gate` without oscillation; a `merge_agent` success is proven to have
committed a clean verified result before reporting success. The `merge_conflict`
artifact is written before the event and the event carries its ref — **and the
persistence-failure branch is asserted too**: with the artifact write forced to
fail, the event carries a generic reason and no ref, and the run still follows the
policy. Cancellation retains unmerged worker branches while
clearing durable merge state and worktree registrations. Human-gate resume
re-enters at the recorded fragment from `gate_events`. A scan-blocked fragment
commit follows the refused-merge policy and does not continue as applied. Existing
fan-out isolation tests pass, or carry a reviewed, recorded expectation change
attributable to this spec (Requirement 17 AC 6).

### Prompt migration and retry recipients

Every one of the 30 ledger rows is asserted for normal, retry, redo, resume, and
chained-run behaviour, or carries an explicit not-applicable assertion. Full
**composer** tests — not source inspection, not a dictionary-pop simulation —
cover all five Requirement 14 classes for a first agent and a non-first agent.
Staged skills remain discoverable after the factory `skills` block is removed. No
`REQUEST.md` is created and the raw request reaches no downstream agent outside the
retry classes. A migrated workflow's first step produces its durable contract
artifact. A governed agent does not lose its Constitution when its workflow
migrates. The prompt viewer shows the effective system prompt plus the control
payload and never an empty-context message. A consumed one-shot control payload is
not replayed on resume.

### Audit and events

A completed run, a degraded run with a blocked payload, a legacy chain read, a
refused chain launch, a restore, and a crash-recovered run each leave the expected
owner-scoped records. Records are asserted to contain **no file contents, prompts,
diffs, model output, secrets, or PII** — not merely no payload bytes
(Requirement 17 AC 17). A cross-owner audit read is refused, and an audit write
under an authorization error fails closed rather than writing an unscoped row.
Chain provenance is reconstructed in **both** directions: given a run, its source
ref; given a source, its consuming children. The `post_commit` observer is proven
registered, and an observer failure is proven not to roll back the commit.

Both new event types are tested live, through a disconnect that spans the event,
and present in the run-detail projection after a full reload — reconnect coverage
is required, not optional (Requirement 17 AC 15). Every reason code maps to its
message; an unknown code falls back.

### `.context/` determinism (real Git + real DB)

A run interrupted after `.context/` is written and then resumed observes
**byte-identical** `.context/` files versus the same run executed without
interruption — asserted file-by-file, including `design/`, `selections.json`, and
an installed chain payload (Requirement 8 AC 8). A revision opened on a family
whose root already wrote `.context/design/` inherits it unchanged; the same
revision launched *with* an explicit new design selection overwrites it. A chain
install is asserted not to touch `design/` or `selections.json`, and
`atomic_context_install` is asserted to be a per-file write — a test plants a
sentinel file under `.context/design/` and proves it survives the install.

### Frontend (Vitest + RTL, Playwright `mocked`)

Chain lineage indicator renders on **run detail and the revision-family surface**
from the API projection, not client inference; an **API test** proves the persisted
edge and the projection, including that an unowned source projects as absent
(Requirement 21 AC 4). The label names the source workflow plus the
visible tag, falling back to the source's short id and published status when there
is no tag. A revision is not labelled chained, and a chained run does not appear in
its source's family list. A new launch sends no text context block, and **no launch
produces duplicate chain context** — including a server-side test where an older
client sends both `source_workflow_run_id` and a legacy marker block, and the
backend is proven to strip the block and record the strip. Presentation precedence
is asserted on the flag, not the edge: a pre-v2 marker-bearing run that happens to
carry `source_run_id` still renders as legacy text, and a `chain_policy: degrade`
run that kept its edge without a payload does too. A stale stored block is cleaned
up exactly once across `sessionStorage`, `localStorage`, and in-memory launch
state, and unrelated draft input survives. A historical marker-bearing run still
renders, and a run with an installed `.context/` payload is presented as
file-based even when a family sibling carries a legacy marker. Source-list
composition is asserted for all five terminal statuses plus a non-chainable source.
Non-success source selection shows its accessible, acknowledged, not-color-alone
warning naming the published status **and** that output may be incomplete. The
receiving run's surface displays the source's status. No internal ref string
appears in any rendered output. A degraded run is visually and semantically
distinguishable from a completed one. `chain_context_unavailable` and
`run_finalization_failed` render with the accessible pattern and the correct next
action. Version browse, restore, and **chain launch** are covered in the `mocked`
Playwright project (Requirement 17 AC 10).

### Rollback verification (Requirement 17 AC 18)

A rollback build is exercised against a sandbox that already holds v2 artifacts and
asserted to: stop producing v2 payloads; delete no tag, internal ref, tracked flat
file, audit record, or legacy payload; ignore unknown tracked `.chain` files; and
ignore a v2 finalization record and a metadata-only snapshot without corrupting the
run.

### Gates

`pytest tests/agents/test_characterization_*.py` with `SNAPSHOT_UPDATE` unset;
`git status --porcelain tests/agents/characterization/golden/` empty except
reviewed prompt-migration baselines; `ruff`, `pyright`, `lint-imports`,
banned-pattern tests, and the existing security/secret scans all green;
`test_banned_patterns.py` (11 tests) passing; `cd backend && alembic heads`
printing exactly one head. Frontend: `npm run lint`, `npm run build`,
`npm run test` (single-pass). A gap-closure review confirms every row of the
GAPS.md matrix has a passing test or a recorded not-applicable justification — an
unreviewed row blocks release (Requirement 17 AC 19).

---

## Rollout

### Order (Requirement 17 AC 1-2)

1. Baseline tests.
2. Reserved-path registry (Requirement 18).
3. **Identity + logging + sweeper protection + family lock — one atomic change.**
   Requirement 17 AC 2 requires the revision-root correction to land together with
   both sweeper protection *and* family-lock protection; a partial rollout is
   prohibited. The family lock therefore ships here, not with restore. Restore and
   upload *consume* the lock later, but the lock itself must exist the moment the
   sandbox is re-keyed — otherwise the window between re-key and lock is exactly the
   unserialized shared-sandbox state v2 exists to close.
4. Security-gated commit primitive + binary scanning (Requirement 11 AC 9-17).
5. Flat payload + finalizer + durable finalization record.
6. Exact-ref chaining + the declared activation gate.
7. Hooks / conflict policies / crash recovery.
8. Restore + uploads (consuming the lock from step 3).
9. Provenance audit + failure-event contracts (Requirements 19 and 20).
10. Prompt migration.
11. Compatibility / UI (Requirement 21).
12. Final validation.

The payload/finalizer change and the revision-root correction ship as separate
revertible commits or PRs where repository workflow permits (Requirement 17 AC 5).

### Feature detection and rollback (Requirement 17 AC 3-4)

Flat-payload writing is feature-detectable by the presence of the internal run ref
and the `schema_version` in `summary.md`. **No global date or deploy flag** guesses
the payload format. Rollback stops producing v2 payloads without deleting tags,
internal refs, tracked flat files, audit records, or legacy payloads, and a
rollback reader ignores unknown tracked `.chain` files rather than corrupting a run.

### Deployment (Requirement 17 AC 12)

Production apply and deployment remain pipeline-controlled and approved. No manual
shared-environment mutation is part of this spec: no operator applies a migration,
creates a ref, moves a tag, or edits a sandbox by hand on a shared environment. The
one explicitly operator-driven action in the design — recovery from an internal-ref
conflict — is an inspection-and-decision step, and any resulting write goes through
the pipeline.
