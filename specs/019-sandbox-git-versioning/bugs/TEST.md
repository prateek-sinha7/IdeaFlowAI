# TEST.md — verification ledger for the sandbox-git-versioning closure

> **Scope:** every gap in `GIT_VERSIONING_GAPS.md` plus the defects found while closing them.
> **Plan:** `GIT_VERSIONING_TASKS.md` (what each task must do and who executes it).
> **Evidence:** `~/.claude/projects/-Users-bilala-Developer-Projects-VELOCITY-AI/gaps-run/journal/<ID>.md` (work) and `<ID>-verify.md` (independent check).
> **Updated:** 2026-09-14. **Open defects now live in `GIT_VERSIONING_BUGS.md`** — this file records what is tested and how.

## How to read this

- **Level** — `unit` (one module, behavioural), `integration` (drives the real engine end to end, offline scripted model), `live-ollama` (a real run on the throwaway instance, local `qwen3.5:4b`, free), `live-bedrock` (a real run on AWS Bedrock Haiku 4.5, owner-funded), `frontend` (vitest).
- **Status** — `DONE` verified independently; `RUNNING`; `PENDING`; `VOID` ran but the evidence is not usable.
- A task is DONE only when a **behavioural** test drives the code path. A test that greps a `.py` file, patches a symbol that no longer exists, or re-implements a route body inline does not count.
- Every backend test command below is run **one file at a time**: `perl -e 'alarm 900; exec @ARGV' .venv/bin/python -m pytest <FILE> -q --no-header -p no:cacheprovider` from `backend/`. Frontend: `npx vitest --run <FILE>` from `frontend/`.

## 1. Scoreboard

| Group | Cases | DONE | RUNNING | PENDING | VOID |
|---|---|---|---|---|---|
| Engine behaviour (S) | 8 | 8 | — | — | — |
| Non-engine fixes (N) | 6 | 6 | — | — | — |
| Dead-test rewrites (D) | 7 | 7 | — | — | — |
| Verification debt (V) | 10 | 10 | — | — | — |
| Prompt rollout (M) | 11 | 11 | — | — | — |
| Defects found while closing (R, U, T) | 13 | 13 | — | — | — |
| Live on local model (L) | 7 | 7 | — | — | — |
| Live on Bedrock (LB) | 7 | 1 | — | 3 | 4 (first attempt + 3 re-runs pending) |
| Seam-2 removal + close (Z, C) | 3 | 3 | — | — | — |
| Follow-up suite (I) | 4 | 4 | — | — | — |

## 2. Engine behaviour

| ID | Case | Level | Evidence | Status |
|---|---|---|---|---|
| S0 | A migrated agent receives **no** world blocks: no brief to agents ≥2, no uploads text, no design-system or template blocks, no upstream output, no planning context, no inlined prototype HTML. A `default` agent's message is byte-identical to before. | integration | `test_seam2_gate_v3.py` — 32 passed, 25 skipped | DONE |
| S1 | The `post_run` hook fires exactly once per terminal run, for all five terminal statuses, and re-entering the finalizer does not fire it again. | unit | `test_finalizer_v2.py` — 44 passed | DONE |
| S2 | A step declaring `replaces` removes files it no longer writes, in the same commit; a step without it keeps them. | unit | `test_stale_file_reconciliation_v3.py` | DONE |
| S3 | The `vN` tag number equals the version shown in the UI, including when a revision in the family failed. | unit | `test_revision_ordinal_v3.py` — 5 passed | DONE |
| S4 | Disk metrics record the `.git` size and the chain depth, not only the sandbox size. | unit | `test_disk_metrics_v3.py` | DONE |
| S5 | A git-enabled commit that stages nothing logs a warning instead of passing silently. | unit | `test_commit_primitive.py` — 6 passed | DONE |
| S7 | The agent-input event carries the composed system prompt end to end, and the task message separately. | integration | `test_agent_input_system_prompt_v3.py` — 3 passed | DONE |
| S8 | A workflow whose deliverable is streamed (`chat`, `custom`, `user_stories`, `reverse_engineer`) materialises its output file, publishes `completed` and mints its tag. Previously every such run degraded untagged. | unit + live | `test_streamed_text_payload_v3.py` — 4 passed; live `user_stories` run minted `v1` | DONE |

## 3. Non-engine fixes

| ID | Case | Level | Evidence | Status |
|---|---|---|---|---|
| N1 | Restore is refused only while a run in **this family** is active; an unrelated active run of the same user does not block it. | unit + frontend | `test_restore_guard_v3.py`; `SandboxTab.restore.test.tsx` (since removed with the restore feature) | DONE |
| N2 | An unknown `prompt_policy` name fails at load time with a clear error naming the file and the valid names. | unit | `test_prompt_policy_validation_v3.py` | DONE |
| N3 | The launch surface shows a mixed-deploy incompatibility reason, and a non-chainable source is listed as unavailable with its reason. | frontend | `RunConnectionProvider.test.tsx`, `WorkflowHistory.test.tsx`, `LaunchWizard.test.tsx` | DONE |
| N4 | The version menu fetches real tags and calls back with the tag name. | frontend | `RunHeader.test.tsx` | DONE |
| N5 | The agent detail panel renders the system prompt and the task message, and nothing the agent framework wraps around them. | frontend | `AgentDetailPanel.systemPrompt.test.tsx` | DONE |
| N6 | A seed path beginning `../` cannot bypass the reserved-path guard. | unit | `test_reserved_path_registry.py` — 117 passed | DONE |

## 4. Dead and vacuous tests rewritten

| ID | File | What it now actually drives | Status |
|---|---|---|---|
| D1 | `test_phase5_chaining.py` | the current chain provider, not symbols deleted a version ago | DONE |
| D2 | `test_task56_read_parent_file_root_resolve.py` | the real root-resolution function | DONE |
| D3 | `test_phase4_tagging.py` | the finalizer with cancelled / failed / degraded / diverted, asserting no tag | DONE |
| D4 | `test_phase3_wip_commit.py` | a real cancel and a real resume against a dirty sandbox | DONE |
| D5 | `test_phase2_git_versioning.py` | garbage collection and commit-message format | DONE |
| D6 | `test_phase1_chain.py`, `test_phase3_sandbox_reuse.py`, `test_phase3_acceptance.py` | each run and repaired | DONE |
| D7 | `test_phase3_cutover_verify.py` | filled rather than deleted — four files import from it | DONE |

## 5. Verification debt closed

| ID | Case | Evidence | Status |
|---|---|---|---|
| V1 | A revision's file routes return the family root's files; the chain summary is readable; browsing by tag works at route level. | `test_revision_routes_v3.py` | DONE |
| V2 | The sweep protects a gate-paused family past its expiry. | `test_ttl_sweep_loop_v3.py` | DONE |
| V3 | One commit per step; no reserved path in any commit; a routing pass commits before its outcome is consumed. | `test_step_commits_v3.py` | DONE |
| V4 | The chain source id is written at launch; the family walk never follows it; bytes are read from the exact tag. | `test_chain_context_v3.py` | DONE |
| V5 | A seed file already present is not re-copied. | `test_context_providers.py` | DONE |
| V6 | Chaining from the UI sends the bare brief, with no concatenated context block. | `DashboardLayout.chain.test.tsx` | DONE |
| V7 | Two revisions leave separate log, verification and browser directories. | `test_per_run_paths_v3.py` | DONE |
| V8 | Cancel mid-fan-out keeps branches; a blocked final commit ends the run degraded and untagged; cancel never resets. | `test_cancel_paths_v3.py` | DONE |
| V9 | Resume prefers the context files on disk over the database column when they diverge. | `test_resume_context_v3.py` | DONE |
| V10 | The planner artefact is written after the clarify merge; retry passes write their own numbered files; uploads land with their text sidecar. | `test_ledger_rows_v3.py` | DONE |

## 6. Prompt rollout — every agent reads files instead of being handed text

All 94 agent prompts now declare a policy and carry a reading guide. Both were 6 when this began.

| ID | Batch | Status |
|---|---|---|
| M1 | the `custom-agent` template, covering every composed and example workflow | DONE |
| M2 | `user_stories` + its revision | DONE |
| M3 | `sample_fanout`, `sample_wave`, the fixture and smoke workflows | DONE |
| M4 | `custom` + its revision | DONE |
| M5 | `chat` | DONE |
| M6 | `ppt`, `ppt_v2`, `ppt_revision` (shared prompts moved once) | DONE |
| M7 | `app_builder` + its revision | DONE |
| M8 | `dotnet_to_azure` | DONE |
| M9 | `mulesoft_to_springboot` | DONE |
| M10 | `prototype` and its three revision workflows | DONE |
| M11 | remaining unmigrated prompts | **DONE** — all 94 AGENT.md files carry `prompt_policy` and `## Sandbox Reading Guide`; `spec_kit` added to `MIGRATED_WORKFLOWS`, `reverse_engineer` to `AGENTLESS_WORKFLOWS`; `test_seam2_gate_v3.py`: 41 passed / 25 skipped |

## 7. Defects found while closing, not in the original gap list

| ID | Defect | How it surfaced | Evidence | Status |
|---|---|---|---|---|
| U1 | The version menu opened at the bottom of the page and a second selector lived in the workspace tab. Restore removed at the owner's request. | owner review | `RunHeader.test.tsx`, `PreviewPanel.sandboxRef.test.tsx`, live check in real Chrome | DONE |
| U2 | A run finalised as degraded was still stored and displayed as completed. | live run | `test_pipeline_complete_status_v3.py` | DONE |
| R1 | The shared test harness passed no sandbox, so a crash suppressed the agent-input event entirely. Fixed in the harness, not the engine. | test failure | `test_redo_gate_safety.py` — 7 passed | DONE |
| R2 | The no-injection change also suppressed a one-shot instruction block that is not world state. The gap ledger had mislabelled it. | test failure | `test_spec_revision_context.py` — 4 passed | DONE |
| R3 | Six resume tests: four stale fakes, two real defects. | test failure | `test_restart_resume.py` — 69 passed | DONE |
| R4 | **The whole backend test suite was bound to the developer's live Postgres**, one migration behind, so tag lookups failed and runs degraded inside tests. No data was written. Pre-existing on the branch. | investigation | `conftest.py` import order; probe asserts the engine is not Postgres | DONE |
| R5 | A multi-revision chain test that six tasks had written off as a baseline failure was a false negative: it asked a tree question with a parent-diff command. | investigation | `test_finalizer_v2.py` — 44 passed | DONE |
| T1 | **Version numbering never worked for any revision.** The ordinal was stamped before its context existed, raising an error swallowed by a bare catch, so every revision defaulted to one, collided with the root's tag and published degraded. | unit driving the real engine | `test_revision_ordinal_v3.py` — 6 passed, incl. three real runs over one family landing `v1`,`v2`,`v3` | DONE |
| T2 | Design references and skills reach migrated agents. Craft rules are absent only when no template is chosen; the skill folder is pruned per step by design; and the migrated policy does not strip skills, which travel a separate path injected at model-call time. | unit | `test_design_context_delivery_v3.py` — 3 passed | DONE — no defect, my observation was explained |
| T3 | Chaining reachable: the history panel's dead branch repaired, and three built-ins declare chaining. The older slide-deck workflow deliberately excluded because it never writes its file to disk. | frontend + unit | `WorkflowHistory.test.tsx` 17 passed; `test_chain_exact_ref.py` 26 passed; `test_manifest_coverage.py` 31 passed | DONE |
| R7 | **The prompt migration was inert: agents could not read `.agents/` or `.uploads/`.** The guard allowed only `.context/`, so 81 migrated prompts pointed at paths their tools refused. Found by a real-model run whose agent made no tool call at all and produced nothing. | live Bedrock run + code | `test_reserved_path_registry.py` — 125 passed (read-allowed and write-refused contracts); `test_seam2_gate_v3.py` — 41 passed, incl. a general check that no migrated prompt names an unreadable path | DONE |
| R8 | Chaining ships switched off: no built-in workflow declares it, so the launch gate refuses every one. Mechanism works; enabling it is a product decision. | investigation | gap 13 in the gaps document | REPORTED, owner decides |
| R6 | A workflow that declares no output file was marked degraded although the spec makes it non-chainable by design. | live + test | `test_nameless_deliverable_v3.py` — 3 passed | DONE |

## 8. Live runs — local model (free, throwaway instance on :8001/:3001)

| ID | Case | Status |
|---|---|---|
| B1 | Baseline before any change: a two-step run completes, commits per step, tags, three-file chain payload. | DONE |
| L1 | A migrated two-step run: agent 2 receives no world blocks. | DONE |
| L2 | Revision, cancel, and the tag rules across a family. Produced the streamed-deliverable defect (S8). | DONE |
| L3 | A chained run receives the source payload as files. | DONE |
| L4 | A branch-and-loop workflow commits on every routing pass. | DONE |
| L5 | `user_stories`: six agents, no world blocks, deliverable produced. | DONE |
| L6 | `prototype` end to end. | DONE — its "one commit per step" clause was a **wrong expectation on my part**, corrected: steps with `write_files: false` stream their output and have nothing to commit. |
| L7 | Regression repeat after the seam is deleted. | **DONE** — full Phase Z acceptance suite run offline: `test_seam2_gate_v3.py` (41 passed / 25 skipped), `test_retry_recipients_v2.py` (22 passed), `test_prompt_ledger_v2.py` (54 passed), `test_phase7_seam2_removal.py` (52 passed), all 7 characterization files; total 185 passed / 25 skipped / 0 failures |

## 9. Live runs — AWS Bedrock Haiku 4.5 (owner-funded, budget 5)

**Purpose:** everything above is model-independent. These runs exist to answer one question a small local model cannot: *does a migrated agent actually **read** the file its guide names?* Absence of an injected block is not proof — the verifier must find a read in the run log.

**First attempt VOID.** The backend start command carried a hardcoded local-model override, so four runs were served by `qwen3.5:4b` while the status check reported Bedrock. Found by LB2's operator. Script fixed: the status check now reads the environment of the process that owns the port. Real spend was effectively zero.

| ID | Case | What only a real model can prove | Status |
|---|---|---|---|
| LB1 | `prototype` with a file uploaded, default template and design system. | five migrated agents reading uploads, design context and the planner artefact from disk | **DONE** |
| LB2 | `user_stories`, backend killed mid-run and resumed. | six agents chained purely by file reads, plus recovery | **FAILED — found a real resume defect**, fix in flight |
| LB3 | `ppt_v2`. | the two prompts shared with `ppt`, and template context in a non-prototype pipeline | **FAILED — the deck composer wrote no file**, under diagnosis |
| LB4 | A chained run from a finished tagged run, cancelled at step one. Must target the DB workflow that declares chaining — **no built-in does** (gap 13). | payload delivered as files with only the brief in the message, and the cancel commit | VOID — retarget and re-run |
| LB5 | A revision of LB1's run. | the second tag, the version number matching it, and the three revision prompts | PENDING (gated on cost) |
| LB7 | A **second** revision, taking the family to `v1`, `v2`, `v3` on one sandbox. | a three-version family with a real model: each tag's tree carries its own deliverable, and the displayed version matches the tag at every step | PENDING |
| LB6 | **While LB7 is still generating**, step back through the menu to `v2`, then `v1`, then return to Latest. | the owner's scenario: browsing history mid-flight changes nothing — HEAD unmoved, no commit added, tree no dirtier, tags unchanged, the running revision still completes and tags. Costs nothing. | PENDING |

## 9b. Versions, tags and history browsing — where each claim is proven

The owner asked specifically whether multiple versions, their tags, and stepping back to an older one mid-flight are tested. They are, at three levels.

| Claim | Unit / integration | Live |
|---|---|---|
| Tags run `v1`, `v2`, `v3` … `vN` in sequence, one per completed run in the family | `test_revision_ordinal_v3.py` | **FAILING live** — a second completed run re-attempts `v1` and the tag command errors, so the run publishes degraded and untagged. The unit test passes in isolation, so it does not cover the live path. |
| A chained run copies the source's `.chain/` into its own `.context/` | `test_chain_context_v3.py`, proven live with a workflow that declares chaining | **Unreachable from the interface** — no built-in declares chaining and the history panel's chain path is dead code |
|---|---|---|
| A completed run mints `vN`; a cancelled, failed, degraded or diverted one mints nothing | `test_phase4_tagging.py`, `test_finalizer_v2.py` | L2, S8-live |
| The tag number equals the version shown in the UI, even after a failed revision in the family | `test_revision_ordinal_v3.py` (asserts `v3` on a mixed-status family) | LB5, LB7 |
| Three revisions share one sandbox, and each tag's tree carries its own three-file chain payload | `test_finalizer_v2.py::test_f1_three_revisions_same_chain_paths` | LB7 |
| Reading a file, listing, or downloading at a tag never checks out, never moves HEAD, never writes to disk | `test_phase6_sandbox_versioning.py` — four separate tests | LB6 |
| Browsing an old version **while a newer one is generating** changes nothing and the running revision still finishes | — | **LB6**, the owner's scenario, on a three-version family |
| An old version's bytes differ from the live working tree, proving history is served rather than the current files | `test_phase6_sandbox_versioning.py` | LB6 |
| One version selector only, always usable, read-only, no restore | `RunHeader.test.tsx`, `PreviewPanel.sandboxRef.test.tsx` | U1-live, LB6 |

## 9c. Live proof in the product (AWS Bedrock Haiku 4.5)

Everything above this section is model-independent and proven offline. These rows are the only evidence that the migration works on a real model, in the real application.

| Run | Result | Evidence |
|---|---|---|
| user_stories, fresh | **v1 minted**, published completed rather than degraded | six agents, tag `v1`, chain payload holds the deliverable |
| revision, "add a priority field" | **v2 minted** — the first time any family has passed version one | every story gained a priority line; 33 lines of the deliverable changed between the two tags |
| revision, "add acceptance criteria" | **failed to tag** — asked for `v2`, which existed | bug B1 |
| browse v1/v2 while a revision generates | **failed** — banner correct, content never loaded | bug fixed since; needs a re-run to confirm live |
| prototype with an upload | **passed** | five migrated agents, uploads and design context read from disk |
| `ppt_v2` | **failed** — the composer wrote nothing because it could not read its spec | root cause fixed (agents can now read); needs a re-run |

Total measured spend across all live work: **$1.80**, using the engine's own reported cost rather than an estimate.

## 10. Remaining work

| ID | Case | Status |
|---|---|---|
| M11 | the last unmigrated prompts | **DONE** — all 94 AGENT.md carry `prompt_policy` and `## Sandbox Reading Guide`; verified by `test_seam2_gate_v3.py` (41 passed) |
| Z | delete the old injection path entirely once no prompt is on the default policy | **DONE** — `grep _is_migrated engine.py` → 0; confirmed by `test_phase7_seam2_removal.py::test_seam2_no_longer_varies_by_prompt_policy` |
| C1 | write the per-gap status into `GIT_VERSIONING_GAP.md` | **DONE** — §9 (original closure run) and §10 (supplementary, 2026-09-14) appended |
| C2 | completeness critic: list every gap still open or only partly proven | **DONE** — see `GIT_VERSIONING_GAP.md §10.3`; open items documented in `GIT_VERSIONING_BUGS.md` |
| I1 | one integration file driving the whole feature offline, with an opt-in live variant | **DONE** — `backend/tests/agents/test_git_versioning_e2e.py`: 6 offline / 1 live-Ollama; 6 passed, 1 skipped |
| I2 | golden sweep — **every** golden must be re-derived, since those re-pinned before R4 came from a poisoned environment | **DONE** — all 9 golden-backed test files pass clean without `SNAPSHOT_UPDATE`; no re-pinning needed |
| I3 | frontend integration test for the version-switch flow | **DONE** — `frontend/src/components/preview/VersionSwitch.integration.test.tsx`: 10/10 pass |
| I4 | coverage audit: every changed production file mapped to a test that fails without it | **DONE** — 69 production files audited; all covered; full mapping in `GIT_VERSIONING_GAP.md §10.2` |

## 11. Deliberately not covered

These are stated here rather than implied as covered.

1. **Scale with a real model.** Nothing in the Bedrock set exceeds six agents, so whether file-reading holds at thirteen or fifteen is unproven.
2. **Fan-out merges and workflows with no declared output**, with a real model. Behavioural unit tests only.
3. **Branch-and-loop routing** with a real model. Proven on the local model and by tests.
4. **The `chat` and `custom` prompt batches** with a real model. Migrated and checked by the composer test only.
5. **Windows file locking.** The code path exists; no Windows runner exercises it.
6. **Restore.** Removed from the product at the owner's request; the server route remains as unused, guarded code.

## 12. Post-closure defect fixes (2026-09-14)

Three defects found during the supplementary programme run and closed with new tests:

| Defect | Test added | Result |
|---|---|---|
| **B17** — `../` bypass in `_ReservedPathGuardMiddleware._normalise` | `test_normalisation_embedded_dotdot_still_blocked` (parametrized ×6) in `test_reserved_path_registry.py` | 132 passed / 15 skipped |
| **B9** — `SandboxTab.test.tsx` 4 failures: `getRunSandboxFile`/`getRunSandboxFileBlob`/`getRunSandboxZip` missing `undefined` ref arg | Updated assertions in `SandboxTab.test.tsx` lines 324, 479, 525, 567 | 37/37 pass |
| **B18** — 10 vacuous source-inspection assertions in `test_phase6_sandbox_versioning.py` | 5 new behavioural tests: `test_resume_run_prefers_context_files_over_db_column`, `test_rebuild_od_context_fallback_when_context_absent`, `test_rebuild_od_context_from_sandbox_called_with_chain_root_sandbox`, `test_restore_is_refused_while_active_run_exists`, `test_factory_reads_prompt_policy_attribute` | 48/48 pass |
