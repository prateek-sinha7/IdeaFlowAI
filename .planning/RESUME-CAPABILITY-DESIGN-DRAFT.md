# Top-Tier Resume Capability — PLAN OF RECORD (milestone v3.0)

> Status: **PLAN OF RECORD (POR) for milestone v3.0 — Top-Tier Resume & Durable Execution.** All 7 design decisions LOCKED by the user (2026-07-18, §8); the LOCK-E/ND-4 supersede decision record is §8.1. Grounded in the current `feat/ui-2` code (file:line verified via deep-investigation agents, 2026-07-18). Milestone registered in `ROADMAP.md` (Phases 45–50 = R0–R5) + `REQUIREMENTS.md` (RESUME-05..18); this document is the authoritative detail the phase plans must follow — the v3.0 analogue of `CHAT-AND-UI-CONVERGENCE-PLAN.md`.
>
> **v2 (2026-07-18):** folded in the full IMPLEMENTATION-REGISTER cross-check (read to EOF, all 4043 lines) — 7 gaps closed into the design (live-chat layer on resumed runs, uploads durability, gate re-arm reality, task-identity holes, per-task capture generality, resume-endpoint mechanics, mid-wave merge re-entry) and 8 corrections (LOCK-E supersede, KAN-88 history, task-registry recommendation, immutability, ND-10, steering re-drain, INV-2, strategy-conditional completeness).
> **v2.1 (2026-07-18):** §8 converted from open questions to the user's locked decisions; §6 restructured to one milestone / six phases (R0–R5); §5.3 boundaries updated for the Q6 (uploads durable) + Q7 (generic per-task capture) decisions.
>
> **Goal (user's words):** make resume *top-tier* — **agent-level, sub-agent-level, and fan-out interruptions all resumable, agent-agnostic** (any agent can fan out), using a "read durable state, decide where to start" cursor. **Constraint:** the task list produced by the task/plan agent **can be edited, extended, or pruned by the user**, so resume must handle a *mutable* task set.

---

## 0. TL;DR of the design

- The durable per-task substrate **mostly already exists** and is the right one: `artifact_refs` (immutable, content-addressed, full inline content, `task_id`-tagged, versioned, TTL-surviving). **We do NOT build git-commit-per-task as the resume substrate** (DECIDED, Q1) — it's redundant with `artifact_refs`, and today's git/worktree path is dormant + ephemeral (§3.4). The two substrate holes are now DECIDED build items (§8): per-task capture goes **generic** — everything a task wrote, not just the declared file (Q7) — and **uploaded documents get a durable mirror** (Q6).
- Resume today is **step-granular (per-agent)**; it re-seeds only the in-memory graph, never re-materializes the on-disk deliverable, and has no per-task cursor. That's the core gap.
- The design is a **generic, agent-agnostic resume cursor at task/worker granularity, computed by the KERNEL (never by an agent)**, plus a **durable→disk re-materialization step**, plus **content-addressed task identity** (namespaced by upstream context, §5.1) so a user-edited task list reconciles cleanly. All keyed on generic `run:step:task/worker/artifact` identity — zero workflow-name in the kernel (SC-001/INV-1). Additive migrations only. Re-enters the single existing dispatch/`run_fanout` path (INV-12).
- A resumed run must also be a **first-class live run**: re-register the live-ectx + milestone-sink callbacks (§5.8) or steering/images/Concierge/narrator stay dead after resume.

---

## 1. Scope — the resume "ladder" we want to complete

| Granularity | Today | Target |
|---|---|---|
| Run (restart classify) | ✅ built | keep |
| Step / per-agent | ✅ built (skip completed, rehydrate graph, idempotent `input_hash` reuse) | keep + re-materialize disk |
| Fan-out **wave** | ⚠️ whole-in-flight-wave re-run | **per-worker skip + merge re-entry** |
| **Sub-agent / task / worker** | ❌ not reached | **build (core ask)** |
| Sequential build (`task_loop`) | ❌ no cursor + data-loss bug | **build (core ask)** |
| Paused **gate** (clarify + review) across restart | ❌ both abandoned → `failed` (KAN-88) | **make re-armable (restore pre-KAN-88 behavior, solved properly)** |
| User-resume of a **terminal-failed** run ("reopen & fix") | ❌ LOCK-E-deferred (ND-4) | **build (headline; needs explicit LOCK-E supersede — §7)** |
| **Live-chat layer on a resumed run** (steering / per-turn images / Concierge / milestone cards) | ❌ dormant — resume path never registers the callbacks | **re-register (§5.8)** |
| Within-agent (mid-token) | ~ opportunistic (Postgres checkpointer only) | out of scope (structural) |
| Cross-node / distributed | ❌ out (N8) | out of scope (single-node) |

---

## 2. Current architecture — the durable substrate (grounded)

**Durable stores (Postgres, survive restart + the 48h sandbox TTL):**
- `run_events` — append-only, monotonic `seq` per run, owner+workspace-scoped (`app/models/run_event.py`). The `0024` migration adds per-run-seq uniqueness — **any resume event emitted mid-run MUST draw `seq` from the engine's own counter** (`_stamp_resume_marker` pattern; the DEF-43-03-1 lesson), never `append_event_next_seq` (that allocator is for out-of-band chat rows only; mixing them gaps the replay log).
- `artifact_refs` — **the deliverable system of record.** `app/models/artifact_ref.py:24,40`: *"One row per Artifact version per run. Immutable — no deletes or overwrites."* Columns: `producer_step`, `producer_agent`, **`task_id` (nullable)**, **`content` (Text, full inline)**, **`content_hash`**, `location`, **`version` (monotonic per `(run_id, kind)`)**, `parents`/`derived_from` (lineage). Written via the sole path `_dual_write_artifact` (`engine.py:5451-5507`).
- `wave_runs` (migration 0020) — per-wave: `step`, `wave_index`, `task_ids (JSON)`, `status`, owner+workspace.
- `subagent_runs` (migration 0019) — per-child audit. **Lacks `task_id`/`worker_index`** — the schema gap (`app/models/subagent_run.py:33-50`; the pre-authorized CR-03-followup).
- LangGraph checkpointer — per-agent graph state, `thread_id=f"{run_id}:{agent}"` (+`:{task}`, `:redo{N}`, `:retry{n}`). A **per-agent replay optimization, NOT the resume cursor**.

**Per-task/per-worker capture already happens — with a scope caveat (v2 correction):**
- Build tasks: `persist_task_html` (`kernel_services.py:1313-1339`) → after every task (and after fix-loop edits, `task_loop.py:290-296`/`:358-366`) it persists **the declared deliverable file's current state** as an `html_file` row with `task_id=str(task_num)`. **Verified generic in filename** (07-11/CR-05: a non-prototype task_loop dual-writes its own declared file, e.g. `app.py`) **but single-file and kind-hardcoded**: only the one declared deliverable file is captured per task (`kind="html_file"` even for non-HTML content); sibling sandbox files a task wrote are NOT durably captured until the terminal `serialized_sandbox` deliverable. Multi-file task_loops therefore have a thinner substrate today — **Q7 DECIDED: build the generic per-task capture (§6 Phase R1)** so this ceases to be a limit.
- Fan-out workers: `write_fragment_artifact` (`kernel_services.py:705-761`) → each worker's output as a `file_bundle` row with `task_id=str(worker_index)`, **persisted BEFORE the merge** (partial results survive abort/cancel).

**Resume tier (built, step-granular):**
- `restore_non_terminal_runs` (`engine.py:4815-4998`), 3-way: **(a)** `waiting_for_user` → `failed` (`:4868-4886`, KAN-88 — see §5.5 history); **(b)** `_is_resumable_in_flight` → `asyncio.create_task(resume_run)`; **(c)** else → `failed`.
- `resume_run` (`:6031-6237`): re-enters the **single** `_execute_impl` dispatch loop at `_first_incomplete_step` (`:5909-6007`); skips completed steps; rehydrates completed outputs via `_hydrate_artifacts_from_store` (`:5865-5907`) — **into the in-memory graph only, never to disk**. Launch-time `selections_json` IS re-applied on resume (quick 260615-dzk, migration 0023 — already fixed).
- Idempotent step reuse: `input_hash` = sha256 over **sorted upstream `content_hash`es + resolved input, no timestamp/uuid** (`engine.py:5639-5733`). **This is the content-addressed-reuse pattern we extend to task granularity (§5.1) — including its upstream-hash namespacing, which the task key must inherit.**

---

## 3. Current architecture — isolation, git, merge, deliverable, uploads (grounded)

### 3.1 Isolation (engine-selected, INV-7)
Three modes (`fanout.py:65-67`): `shared_read`, `sub_sandbox`, `worktree`. Scope chosen **solely** from `base_workspace.has_git` (`fanout.py:226-238`); the manifest can never name it.

### 3.2 Git worktrees + per-worker commits — **fully built, but DORMANT + EPHEMERAL**
- **Dormant live:** `KernelServices.workspace=None` by default (`kernel_services.py:196`); set only on the exec-gated path (`engine.py:1988`); no workflow declares `exec`; fan-out degrades to `shared_read` (`fanout.py:322-327`).
- **Ephemeral even when it runs:** worktree + branch are DELETED at teardown (`local.py:563-587`). **Git retains no durable commit anywhere.** Real commit/PR push = `GIT-01`, v2-deferred.

### 3.3 Merge (engine-selected by scope, INV-7)
`git_3way` for worktree, `copy_disjoint` for sub_sandbox (`fanout.py:770-778`); conflicts first-class (`merge_conflict` artifact+event, `on_conflict` policies). Per-wave merge into base before the next wave. **Resume implication: a crash between fragment-persist and merge means the merge itself must be re-entered (§5.4).**

### 3.4 Workspace / RuntimeEnvironment abstraction (the ECS seam)
Hexagonal ports (`agents/runtime/base.py`); local impl `LocalSandboxRuntime`. A git-worktree-per-task model already fits this port; ECS is v2.

### 3.5 Deliverable capture vs assembly — the split
- **Live truth = the ephemeral disk sandbox** (`RunSandbox`, 48h TTL). Agents and resolvers read disk.
- **`artifact_refs` = durable mirror that is NEVER read back to disk.** No code re-materializes files from durable rows.
- Final deliverable persisted as `kind="deliverable"` **only on successful completion** (`engine.py:2415-2453`).

### 3.6 Uploads & images (v2 addition — the substrate holes)
- **Uploaded DOCUMENTS** (`POST /api/runs/{id}/files`, Phase 30) live as raw bytes + extraction sidecars + `manifest.json` under the sandbox `.uploads/` prefix — **disk only, never an `artifact_ref`**. The `uploaded_files` context provider re-reads them from disk on EVERY dispatch (sticky) and "degrades to `{}`" when missing. **A fresh sandbox loses them silently and Postgres cannot restore them.** → Gap G; **Q6 DECIDED: persist durably (§6 Phase R2)**.
- **IMAGES** are payload-transient by LOCKED design (ND-10/LOCK-E): never on disk/DB, gone on reopen. A resumed run whose remaining agents declare `injects:[images]` will not have them. **Accepted resume limitation — do not fix** (it is a locked non-goal).

---

## 4. The gaps (what "top-tier" must close)

- **Gap A — no re-materialization to disk on resume.** Durable rows have full content + `task_id` + `location`, but nothing writes them back; resolvers read disk. Fresh sandbox ⇒ deliverable lost even though the bytes are in Postgres. *(Scope caveat: true for the declared deliverable file + fragments; NOT true for uploads — Gap G.)*
- **Gap B — no per-task cursor + mis-firing completeness.** `subagent_runs` lacks `task_id`/`worker_index` ⇒ whole-wave re-run; `task_loop` restarts at task 1 (`task_loop.py:233`); `_first_incomplete_step` marks a build "complete" after its **first** task persists (`engine.py:6002`) ⇒ **partial builds silently skipped = data loss** (standalone bug — §6 Slice 0, strategy-conditional per I8).
- **Gap C — gates abandoned on restart.** Clarify AND review both hit branch (a) → `failed` (KAN-88). **Nuance (v2):** the *durable* half of gate-pendency already exists — `derive_open_gate` (KAN-94, `chat_router.py`) re-derives an open gate from `run_events`, and `run_stream.py` already re-emits `review_gate_ready` to an attaching SSE client via the D-14g `_dangling_review_gate` seam. What's missing is only the **server-side waiter/consumer** after restart — and that consumer is non-trivial because the review gate lives INSIDE `_run_agent`'s run+gate `while True:` loop (redo / update_specs / edit are loop-local consumers). See §5.5.
- **Gap D — no user-resume of a terminal-failed run** (ND-4 "reopen & fix"); only full relaunch today. **LOCK-E-deferred — reversing it needs an explicit decision record (§7).**
- **Gap E — the task list is mutable.** Tasks come from the plan agent's output but the user can edit/add/remove them (today: via the review-gate **Edit** action → a new `task_list` artifact version). Resume must reconcile the *current* task set against what already completed — positional indices are unsafe.
- **Gap F (v2) — resumed runs are dead to the live-chat layer.** `_LIVE_ECTX` registration + the `milestone_sink` narrator callback are injected only at the REST launch call-site (`run_commands.py:1355`); the resume path keeps them dormant (register: Phase 43 known-follow-ups). On a resumed run: steering no-ops, per-turn images never drain, the Concierge can't reach the run, no milestone cards emit. → §5.8.
- **Gap G (v2) — uploaded documents have no durable mirror** (§3.6). Re-materialization can't restore `.uploads/`; the sticky uploaded-doc context silently vanishes on a fresh sandbox. → **Q6 DECIDED: persist durably — becomes Phase R2 (§6).**

---

## 5. Proposed architecture

### 5.1 The unifying primitive — content-addressed **task identity** + a generic **kernel-owned resume cursor**
Extend the existing content-addressed reuse (`input_hash`, §2) **down one level** to tasks/workers, **identity-based, not positional**:

- **Task identity** `task_key = sha256(upstream_context_hash · normalized_task_content · occurrence_ordinal)`:
  - `normalized_task_content` — the task's own text (stable across reordering/insertion).
  - `upstream_context_hash` (v2 fix) — the sorted upstream `content_hash`es the step consumed (the same inputs `input_hash` uses). **Without this, editing the spec (e.g. via the shipped `update_specs` loop) then resuming would skip tasks built against the STALE spec.** Unchanged spec + unchanged task ⇒ same key; changed spec ⇒ all keys rotate ⇒ tasks re-run (or gate on Q2's cascade policy).
  - `occurrence_ordinal` (v2 fix) — disambiguates **duplicate task text** (two "Fix styling" tasks must not collapse into one key; precedent: the 12-06 WR-05 duplicate-id guard).
- **Per-task completion record** = `subagent_runs` row carrying `task_key` (+ positional `worker_index` for waves), status, pointing at its produced `artifact_refs` (tagged with the same key in `task_id`). *(Additive migration — the pre-authorized CR-03-followup shape; next head after 0025.)*
- **The cursor is generic + computed by the KERNEL resume tier** (plain code, deterministic, testable): on resume, the engine reads durable state and computes the `completed_task_keys` set for a step. **The agent never decides where to start — the kernel does**, keyed on generic identity (SC-001/INV-1). *(The agent still RECEIVES the completed work as injected context so its continuations are coherent — that part is the existing context-injection machinery, unchanged.)*
- **Task registry (v2, register-grounded — DECIDED, Q3):** the task list stays **a versioned `task_list` artifact**, not a new table. Phase 23's Redo already gives it exactly the needed discipline: v2 supersedes v1 with `derived_from` lineage, v1 kept forever, `max(version)` wins (`_latest_typed_content`, the F5 fix) — live-proven on run `97277945`. And the user's edit path already exists: the gate **Edit** action (`_apply_declared_gate_edit`, KAN-98; `edited_content` rides `POST /{id}/gate` only — WR-03). Slice 2 = extend that mechanism (an edit endpoint/affordance that mints a new `task_list` version), **not** a parallel task-CRUD (INV-12). This also respects the 12-era lock "NO new step-status table" — the only schema change stays the `subagent_runs` columns.

### 5.2 Resume reconciliation (handles the mutable task list, Gap E)
On resume OR on re-run-after-edit, the strategy reconciles the **current (max-version) task list** against `completed_task_keys`:
- key in current list **and** completed → **skip**, re-materialize its artifact (§5.3), inject as prior context.
- key in current list, **not** completed (new task, edited text, or rotated upstream hash) → **run** it.
- completed key **absent** from the current list (user removed/replaced it) → its artifact is **orphaned**: excluded from the assembled deliverable at assembly time. **Rows are NEVER deleted — `artifact_refs` is immutable by contract** (v2 clarification); orphan handling is read-side exclusion only. **(Q2 DECIDED: fully AUTOMATIC — deleted → assembly-excluded/kept-in-history, spec-edit → affected tasks auto-re-run, no confirm prompt.)**
This is the step-level `_find_reused_completion` pattern at task granularity, inheriting its hash-stability discipline (no timestamp/uuid, sorted).

### 5.3 Durable → disk re-materialization (Gap A)
Before a strategy re-enters its loop, the resume tier walks the latest durable `artifact_refs` for the run (by `location`, `max(version)`, filtered to `completed_task_keys`) and writes them back onto the fresh `RunSandbox`. This is the missing half of `_hydrate_artifacts_from_store` (graph-only today). Honest boundaries (v2):
- **Restores:** the declared deliverable file's latest per-task state, worker fragments, typed artifacts (spec/plan/task_list/clarifications), the final deliverable if present.
- **Restored via new decided work (Q6/Q7):** sibling sandbox files beyond the declared deliverable — **Q7 chose the generic per-task capture** (capture every file a task changed; Phase R1), so re-materialization becomes complete for any task_loop; uploaded documents — **Q6 chose durable persistence** of the extracted text + manifest (Phase R2), with the `uploaded_files` provider falling back to the durable mirror on a fresh sandbox. **Still not restorable by locked design:** images (ND-10, §3.6).
- **Nice-to-have (v2):** steering notes that were durably logged as `chat_message` rows but never drained before the crash can be **re-queued** onto `ectx.steering_notes` at resume — cheap, durable rows already exist.

### 5.4 Per-task / per-worker skip (Gap B) + completeness fix + merge re-entry
- Sequential `task_loop`: thread the `completed_task_keys` set into `strategy.run`; loop over the reconciled current list, skipping completed keys.
- Fan-out `wave_scheduler`: skip completed **workers** (by `worker_index`/`task_key` from `subagent_runs`) instead of re-running the whole wave — the CR-03-followup, unblocked by the schema add. (This is identity-based skip, NOT the deleted-for-cause prefix-by-count skip — 12-06 CR-03.)
- **Merge re-entry (v2, Gap-G7):** a crash between fragment-persist and the per-wave merge leaves durable fragments but no merged base. Resume must re-materialize the in-flight wave's fragments to disk and **re-run the merge step** for that wave (engine-selected strategy; in live `shared_read`/`copy_disjoint` mode this only needs the fragment files back on disk) before dispatching the remaining workers/waves.
- Replace the binary completeness check (`engine.py:6002`) with **"every task in the current list has a completed artifact" — but strategy-conditional (v2, I8):** count/identity-based ONLY for task-granular steps (keyed on the compiled `step.strategy`/`task_source`, generic); `single_shot` steps keep "any produced ref / `step_completed` event" as completeness. Must not perturb `step_reused`/`step_completed` semantics.

### 5.5 Gate resume (Gap C) — rebuilt on the existing seams (v2 rewrite; **DECIDED Q4: this re-entry route, NOT the LangGraph interrupt**)
**History first:** `waiting_for_user` runs were originally RE-ARMED on restart (the WR-05-era behavior, Phase 5/12); KAN-88 later flipped them to `failed` — almost certainly because an in-memory `asyncio.Event` genuinely cannot be re-armed without a waiter, so re-arming just hung runs forever. A pre-existing RED test still encodes the target behavior: `test_restart_resume::test_waiting_for_user_run_is_rearmed_not_driven` (register: Phase 23 §7) — **our RED→GREEN anchor**. Slice 3 is therefore a *restoration done properly*, and must answer what KAN-88 punted on: who waits, and who consumes the answer.
- **Durable pendency needs (almost) nothing new:** `derive_open_gate` (KAN-94) already derives an open gate from durable `run_events`; D-14g (`run_stream.py` `_dangling_review_gate`) already re-emits `review_gate_ready` to an attaching client. Reuse both — do NOT build a parallel pending-arm store. (The one in-memory piece, `_gate_is_pending` peeking at `store._resume_events` — the IN-02 debt — gets a public accessor as part of this.)
- **The hard part is the consumer, not the event:** the review gate lives INSIDE `_run_agent`'s run+gate `while True:` loop; its answers (`approve`/`reject`/`edit`/`redo`/`update_specs`) are consumed by loop-local logic (redo's `:redo{N}` threads, update_specs' sub-pipeline + `spec_revision_pending_output`). A restart destroys that loop. Re-arm therefore means **re-entering the step at its gate phase**: resume classifies the step as "output produced, gate unresolved" (derivable from durable events + the persisted output artifact), reconstructs the gate context (output from `artifact_refs` via §5.3, `ectx.last_streamed` from the persisted ref), and re-enters `_run_agent`'s loop AT the gate wait — so all five actions work identically post-restart. Clarify is the simpler twin (re-arm the questionnaire wait with questions replayed from the durable `questionnaire_ready` event).
- Restart branch (a) flips from *fail* → *re-arm* ONLY for compiled-manifest runs with durable state (branch-(b) gating); the WR-05 stateless/legacy path + goldens stay untouched (INV-3). FE note: `AUTO_STREAM_STATUSES` deliberately excludes parked runs (BUG-013) — a re-armed run surfaces its gate on open via D-14g, which is exactly the intended UX.

### 5.6 User-triggered resume-from-failed (Gap D, ND-4) — full mechanics (v2 expansion)
A terminal-`failed` run is untouched by `restore_non_terminal_runs`. Add **user-initiated `POST /api/runs/{id}/resume`**:
- **Ownership:** the two-layer owner check idiom (ORM `user_id` filter → `ScopedStore` default-deny; 404 never 403).
- **Overlap/idempotency guard (v2):** reject if the run is already live (`pipeline_already_running` precedent, Phase-14 CR-01) and make replayed POSTs idempotent (the Phase-33 M4 lesson: an unguarded replay re-mints work).
- **State recovery:** workspace_id from durable rows (Pitfall 2 — never mint fresh), `selections_json` (0023), completed steps/tasks via the §5.1 cursor, disk via §5.3.
- **Drive + stream wiring (v2):** re-register in `_PIPELINE_QUEUES` BEFORE the FE attaches (else the BUG-015 non-live-attach logic settles the stream disconnected); reuse the existing resume bridge (`run_engine.py:91/:100`, the relocated 12-09 machinery) — do NOT mint a third hand-copied driver next to `_drive_launch_to_queue`/`_drive_revision_to_queue` (that sanctioned duplication has bitten twice: CR-02, the D2 mislabel); the terminal status ladder must stay behaviorally identical to the just-fixed fail-safe launch driver.
- **Status transition:** failed → running (or a `resuming` marker EVENT, not a new status — INV-12 preference) so FE `AUTO_STREAM_STATUSES` auto-attaches.
- Then call the same `resume_run` at the failed step/task. The REST entry + transition + guard are the only new surface; everything else is the shared resume tier.

### 5.7 Git worktrees — stay an isolation mechanism, not the resume substrate
Resume reconstructs worktree/sandbox state from `artifact_refs` (§5.3), not from git (commits are ephemeral). **Real git output** (durable commits, per-task diffs, PR push) = `GIT-01`, a separable optional v2 layer on top of the same cursor. *(Decision point — Q1.)*

### 5.8 Live-layer re-registration on resume (Gap F — v2, new)
Every resume entry point (auto branch-(b) AND the §5.6 endpoint) must thread the same two injected callbacks the REST launch threads at `run_commands.py:1355`:
- `register_live_ectx` / unregister-in-`finally` — so `_live_ectx_for_run` resolves the resumed run (steering drain, per-turn images, Concierge live context all come back).
- `milestone_sink=persist_milestone_card` — so narrator cards emit (drawing `seq` from the engine counter, DEF-43-03-1).
Both are generic callables (no engine→app import — the Phase-43 pattern), additive, dormant on goldens. Small change, large user-visible payoff; belongs in Slice 1.

---

## 6. Phased plan — ONE milestone, six phases (DECIDED, Q5)

The user chose a **single milestone**: all phases planned and executed together (per-phase gates still apply — grounded plan, plan-check, RED→GREEN, verify), with one consolidated live pass at the end. Order = dependency × risk. **ROADMAP mapping: R0→Phase 45 · R1→Phase 46 · R2→Phase 47 · R3→Phase 48 · R4→Phase 49 · R5→Phase 50** (global numbering continues after v2.0's Phase 44).

- **Phase R0 — completeness bug fix (standalone, first):** strategy-conditional count/identity-based build completeness so a partial build is never marked "complete" and silently skipped (`engine.py:6002`; conditional per §5.4/I8). Fixes live data loss regardless of everything else.
- **Phase R1 — per-task substrate + cursor:** additive migration (`task_id`/`worker_index` on `subagent_runs`, pre-authorized CR-03-followup); **generic per-task capture (Q7)** — durably capture everything a task wrote, not just the declared file; durable→disk re-materialization incl. merge re-entry (§5.3–5.4); per-worker wave skip + sequential per-task skip; **live-layer re-registration on both resume paths (§5.8)**; steering re-drain.
- **Phase R2 — uploads durability (Q6):** persist each upload's extracted text + manifest durably (additive, owner+workspace-scoped, caps honored); `uploaded_files` provider falls back to the durable mirror when the sandbox copy is gone; re-materialize on resume.
- **Phase R3 — task identity + mutable-list reconciliation (Q2/Q3):** namespaced `task_key` (§5.1); task list stays the **versioned `task_list` artifact** edited via the extended gate-Edit mechanism; **automatic reconciliation** — deleted → assembly-excluded (kept in history), spec-edit → affected tasks auto-re-run.
- **Phase R4 — gate resume across restart (Q4):** re-entry-at-gate-phase on the derive_open_gate/D-14g seams (§5.5); flips the pre-existing red re-arm test green.
- **Phase R5 — user resume-from-failed (ND-4):** REST entry + overlap guard + status transition on the shared tier (§5.6). The "reopen & fix" headline. **Requires the LOCK-E supersede record (§7) in the ADR.**

(Process note: v2.0's formal milestone close is still pending — sequence this milestone after that close, per the register's "separate later step" decision.)

---

## 7. Constraints / guardrails (non-negotiable — from the register)
- **Agent-agnostic + kernel-owned:** key only on generic `run:step:task/worker/artifact/thread/event` identity. The skip/where-to-start decision is KERNEL code, never agent judgment. Zero `if pipeline_type ==`/`spec.id ==`/workflow-name inside `agents/execution_engine/` (banned-pattern gate). Fan-out is already agent-agnostic (SC-001-proven).
- **INV-2:** all cursor/resume state lives on `ExecutionContext` or durable rows — never the engine singleton.
- **Golden-safe (INV-3):** 5 characterization deliverables byte-identical + event-multiset parity. New resume events additive through the single `execute()` emit boundary, dormant on scripted runs or in `_VOLATILE_STRIP_KEYS`; `seq` from the engine counter (0024 + DEF-43-03-1). No re-baseline.
- **Additive-only (Q3-the-project-constraint):** cursor = nullable columns on `subagent_runs` (pre-authorized) — respecting the 12-era "no new step-status table" lock; any genuinely new table carries `owner_id`+`workspace_id` NOT NULL, free-String status, named FK, reversible single-head. Persist at creation/spawn (before the crash window) — the `selections_json`/0023 precedent.
- **No dual impl (INV-12):** re-enter the single `_execute_impl`/`run_fanout` path; reuse `resume_run`/`_apply_selections`/`_dispatch_step_with_retry`/`_stamp_resume_marker`/the `run_engine.py` bridge; extend the gate-Edit path for task edits; prefer an additive `run_resuming`-style EVENT over a new status. Never a third launch-driver copy.
- **Thin compiler (INV-5):** resume control flow in strategies + the engine resume tier, never manifest DSL. **deepagents-only (INV-13):** re-invoke via `_run_agent`/`run_fanout` → `DeepAgentRunner`.
- **Ports & adapters:** capabilities reach the kernel only via `ctx.runner`; engine reaches transport/app only via injected callbacks (`milestone_sink`/`live_ectx_register` pattern); `lint-imports 4/0`. **Ownership:** all durable reads/writes via the default-deny `ScopedStore`, keyed on `user_id` (never the nullable `owner_id`), never trusting a client payload.
- **LOCK-E supersede (v2):** Slices 3/4 REVERSE a formally locked deferral (LOCK-E / ND-4, reconfirmed in `RESOLVED-DECISIONS.md` + Phase 44). The ADR must contain an explicit supersede record with lineage (the ISS-015 → Phase 20 precedent) — never a silent contradiction.
- **Locked non-goals honored:** ND-10 image transience (no durable image storage), the engine's terminal emission untouched, `heading_tasks`/`json_tasks` parsers extended not forked.

---

## 8. Decisions (LOCKED by the user, 2026-07-18 — via AskUserQuestion; do NOT re-open without a new decision record)
1. **Git:** resume substrate = `artifact_refs` (database records) ONLY. Real git-per-task commits stay a separable future layer (GIT-01); nothing in this design blocks adding it later.
2. **Edit policy:** fully AUTOMATIC. Deleting a finished task excludes its output from the assembled deliverable (rows kept forever, never destroyed); editing the spec rotates the upstream hash and the affected tasks re-run automatically — no confirm prompt.
3. **Task registry:** the versioned `task_list` artifact + the extended gate-Edit path (P23 versioning discipline, KAN-98/WR-03 edit precedent). NO new tasks table (respects the "no new step-status table" lock).
4. **Gate survival:** re-enter-the-step-at-its-gate on the existing derive_open_gate/D-14g seams (§5.5). LangGraph native interrupt REJECTED (moves gates into the agent graph; event-shape/parity risk).
5. **Rollout:** ONE milestone containing all six phases R0–R5 (§6), planned and executed together — not shipped piecemeal.
6. **Uploads:** persist durably — extracted text + manifest get a durable owner-scoped mirror; resumed runs keep full document context (Phase R2). Images stay transient (ND-10 locked, untouched).
7. **Per-task capture:** GENERIC now — durably capture everything a task wrote, so any future multi-file task workflow resumes perfectly from day one (Phase R1), not just the declared single file.

### 8.1 Decision record — LOCK-E / ND-4 supersede (the "reopen & fix" reversal)

- **What LOCK-E said:** the v2.0 AUTONOMOUS-RUN DECISION LOCK (POR §3, transcribed in `.planning/phases/28-chat-contracts-guards-a0/contracts/RESOLVED-DECISIONS.md`) deferred **resume-from-failed-step (ND-4)** out of milestone scope; reconfirmed in Phase 44's carry-forward list ("Deferred beyond v2.0 (LOCK-E): … resume-from-failed (ND-4)").
- **What changes:** milestone **v3.0 explicitly builds it** (Phase 50 [R5], `POST /api/runs/{id}/resume`). This record SUPERSEDES the ND-4 deferral **for that scope only**. LOCK-E's other deferrals stay in force: team-sharing (ND-12), per-agent prompt-override persistence (ND-7), and **image-persistence-on-reopen (ND-10) — which this design actively relies on as a locked non-goal (§3.6)**.
- **Why now:** explicit user directive (2026-07-18, "i want the resume functionality to be top tier … resumable"), and the durable substrate the deferral implicitly awaited now exists (Phase 12 resume tier, Phase 29 durable transport, Phase 43 live-layer callbacks) and is completed by this milestone's R1.
- **Precedent for reversing a locked disposition with lineage:** ISS-015 (WONTFIX at Phase 18-05 → SHIPPED by Phase 20, recorded with full lineage in the register). This section is that lineage for ND-4.

---

## 9. Verified anchor index (file:line)
resume tier: `engine.py:4815-4998` (restore/classify), `:6031-6237` (resume_run), `:5909-6007` (first-incomplete, completeness bug `:6002`), `:5865-5907` (hydrate graph-only), `:5000-5045` (`_stamp_resume_marker`/`run_resuming`), `:5639-5733` (input_hash reuse), `:5053` (selections re-apply, dzk). deliverable: `app/models/artifact_ref.py:24,40`, `_dual_write_artifact engine.py:5451-5507`, `persist_task_html kernel_services.py:1313-1339` (declared-filename generic, single-file, kind=html_file hardcoded), `write_fragment_artifact :705-761`, resolvers `serialized_sandbox.py:45-51`/`single_file.py:66-107`, final ref `engine.py:2415-2453`, TTL `sandbox.py:163-187`. fanout/isolation/git: `fanout.py:65-67/226-238/318-327/770-778`, `kernel_services.py:196`, `engine.py:1988`, `local.py:477-511/534-549/563-587/607`, runtime ports `agents/runtime/base.py`. task loop: `task_loop.py:233/253-262/290-296/358-366/477-493`. subagent_runs (gap): `app/models/subagent_run.py:33-50` (migration 0019). gates: `engine.py:4697/4868/3068`, `store.py:42`, `deep_agent_runner.py:381/555-577`; existing seams `chat_router.py` `derive_open_gate` (KAN-94), `run_stream.py` `_dangling_review_gate` (D-14g), `_STREAM_TERMINAL_TYPES` (BUG-016). live layer: `run_commands.py:373-415` (`_LIVE_ECTX`), `:1355` (callback injection site), `engine.py:41/51` (callable aliases), `run_engine.py:91/:100` (resume bridge). uploads: `run_files.py`, `sandbox._UPLOADS_PREFIX`, `context_providers/uploaded_files.py`. task-list versioning precedent: P23 redo (`task_list` v1→v2 `derived_from`, run `97277945`), `_latest_typed_content` max-version (F5), `_apply_declared_gate_edit` (KAN-98), WR-03 (`edited_content` via `/gate` only). precedent: `WorkflowRun.selections_json` (migration 0023). deferred: CR-03-followup, ND-4/LOCK-E (supersede required), GIT-01, ECS-01/02, N8, ND-10 (locked non-goal).
