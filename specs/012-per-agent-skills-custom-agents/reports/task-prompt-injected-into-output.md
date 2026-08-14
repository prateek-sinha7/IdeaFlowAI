---
slug: task-prompt-injected-into-output
status: diagnosed
trigger: |
  DATA_START
  User (same workflow as parallel-subagents-no-html, id
  76840113-63aa-4828-a6e6-93dd62b61f42, after the single_file deliverable fix):
  "I am seeing that somehow in my custom workflow task prompt is being injected
  somewhere which i don't want please find the root cause why its happening and
  how can i resolve this."
  DATA_END
created: 2026-08-13
updated: 2026-08-13
tdd_mode: false
goal: find_root_cause (diagnosis only — no fix authorized)
classification: engine context-injection defects — run brief + ghost CURRENT TASK block injected into every composed-workflow step; NOT a recurrence of the deliverable-strategy bug
---

# Custom workflow — task prompt injected into steps' input and echoed into output

## Verdict

- **This is a NEW defect family, not the already-diagnosed one.** The prior root cause
  (`streamed_text` deliverable vs `write_file` instruction — `parallel-subagents-no-html.md`)
  is FIXED and verified: post-fix run `848876d0` (Aug 13 12:51–12:58, after the 12:53 DB
  update) produced a real `output.html` in the sandbox and the run row's `output` column
  starts with `<!DOCTYPE html>`. [CONFIRMED]
- **Root cause A (primary) [CONFIRMED]**: `_compose_context_message`
  (`backend/agents/execution_engine/engine.py:8775`) unconditionally injects the raw run
  brief as `=== ORIGINAL USER REQUEST ===` — plus a Planning-Context echo of the same brief
  (`engine.py:1866` → `_default_planning_context`, `engine.py:3093-3096`, because the run
  passed `planner: "skip"`) — into **every** step's user message, including all three
  parallel children whose manifest prompts are fully self-contained ("Write one short joke
  about an apple… Do not look for files"). The persisted `agent_input` events for run
  `848876d0` show all four agents received `ORIGINAL USER REQUEST: cat` + `Inferred
  Intent: cat`. With the brief being the literal word "cat" and `read_files` granted, the
  model resolved the brief-vs-step-prompt contradiction as "the user wants to `cat` a
  file": the Apple Writer emitted "There is no file named `cat` in `/`" instead of a joke,
  and the Page Builder produced a valid-HTML page *about the Unix `cat` command* instead of
  a jokes page.
- **Root cause B (secondary, independent) [CONFIRMED]**: a ghost `=== CURRENT TASK ===
  Task N of 3 / Execute ONLY this task from the task list above === END CURRENT TASK ===`
  block — referencing a task list that does not exist — was injected into **all four**
  agents' user messages (persisted `agent_input` events). Two code defects produce it:
  (1) `run_worker` (`backend/agents/execution_engine/kernel_services.py:1084-1090`) always
  passes `task_number=worker_index+1` even though `parallel_group` deliberately sends
  `input: ""` per child (`parallel_group.py:113-118`), and the injector substitutes the
  "Execute ONLY this task from the task list above." filler when the body is empty
  (`engine.py:8935-8951`); (2) the parent — whose path passes `task_number=None` — still
  received "Task 1 of 3" because concurrent workers set/restore the **shared**
  `self._ectx.build_task_number` scratch (`kernel_services.py:1317-1354`) and the
  save/restore race leaks a worker's value into the parent's dispatch. [Leak CONFIRMED
  from persisted evidence; the exact interleaving is LIKELY — it is the only setter.]
- **The word "cat" is an amplifier, not the cause [LIKELY]**: "cat" collides with a Unix
  command while the agents hold file tools, making the derailment catastrophic; but
  brief-vs-step-prompt contention exists for any topic — `run_worker`'s own comment
  (`kernel_services.py:1041-1048`) records a prior fan-out where "one wrote the wrong
  subject entirely". A re-run with a neutral topic (e.g. "sunset") would settle severity.
- **Recommended fix (3 parts)**: suppress the ghost CURRENT TASK block for empty-input
  workers; fix the shared-scratch race; and stop injecting the raw brief (and the
  planner-skip echo of it) into steps that carry their own authored prompt — see
  Recommended fix for the design caveat (some workflows legitimately parameterize on the
  brief).

## Symptoms

- **Expected**: `output.html` = a page assembled from the three child jokes
  (apple / ball / cat).
- **Actual**: `output.html` exists and is valid HTML [CONFIRMED — deliverable mechanics
  fixed], but its content is a fabricated "cat command output" page narrating shell
  semantics ("No file named \"cat\" found in /… Bash cat behavior without filename…"),
  listing the child `.md` files as if shell-discovered. One child artifact
  (`1krppp8-gai0pd-cat.md`, the **Apple** Writer) contains "There is no file named `cat`
  in `/`…" instead of an apple joke; the other two children produced approximately correct
  jokes. [REPRODUCED — read directly from the run sandbox]
- **Exact error**: none — all steps green, no exception. Silent content corruption, same
  failure texture as the prior investigation.
- **Reproduction**: WebSocket `run_pipeline` with `pipeline_type: "custom"`,
  `message: "cat"`, `user_workflow_id: 76840113-…`, `planner: "skip"`,
  `deliverable/selections.__deliverable__: {strategy: single_file, name: output.html}`
  (payload supplied verbatim by the user). Run `848876d0-d42f-4776-bc35-1e112474d268`
  under `backend/runs/0da2ba7c-af98-4bad-8ae0-e1bf04957a10/`. [REPRODUCED]
- **Timeline**: first (and so far only) run after the deliverable DB fix (~12:53 CEST);
  ran 12:51:19–12:58 local (10:51–10:58 UTC in `.logs/*.jsonl`). The *content*-corruption
  mechanism predates the fix (ISSUES defect #1 lineage) but this specific evidence set is
  from today's run. [CONFIRMED]

### Ground-truth: the persisted `agent_input` context messages (run_events) [REPRODUCED]

All four agents (three children + parent) received exactly this user message (len 256):

```
=== ORIGINAL USER REQUEST ===
cat
=== END REQUEST ===
## Planning Context (Deep Planner Analysis)

**Inferred Intent**: cat

## End Planning Context

=== CURRENT TASK ===
Task {1|2|3} of 3
Execute ONLY this task from the task list above.
=== END CURRENT TASK ===
```

The parent (`custom-agent:1krppp8-wrx4z0`) got `Task 1 of 3` — despite its dispatch path
passing no task number. There is no task list anywhere in any of the four messages.

## Prior art

| ID | Relationship | What it tells us |
|---|---|---|
| `parallel-subagents-no-html.md` [HISTORY] | Prior session, same workflow/user | Deliverable-strategy root cause; its fix 1 (single_file) is applied and verified working in run `848876d0`. This report is the follow-on content defect that fix exposed to view. |
| `ISSUES-subagents-strategies.md` defect #1 [HISTORY] | Same family (injected boilerplate dominating weak-model output) | The "Write your deliverable to X" trailing line was echoed as a leaf's entire output on Bedrock Haiku; mitigated by the headed "## How to deliver" block (`factory.py:564-573`). Today's defect is the *user-message* sibling: injected `ORIGINAL USER REQUEST` / ghost `CURRENT TASK` text derails content the same way. |
| `kernel_services.py:1041-1048` in-code comment [HISTORY] | Same symptom recorded during the heterogeneous-fan-out fix | "three 'write one short line' workers each burned 25k-35k input tokens wandering through ls/glob/read_file, and one wrote the wrong subject entirely" — brief/step-prompt contention was observed before this session, pre-"cat". |
| FIX-054 / FIX-001b / FIX-109 [HISTORY] | Adjacent (checklist/QA boilerplate leaking into PPT deliverable body) | Established pattern: injected meta-text leaking into deliverable content is a recurring class in this codebase. |
| ADR-0009 / `parallel_group.py` [HISTORY] | Background | Parallel dispatch itself worked correctly again this run (children 10:51:19 same-second start; parent strictly after). |

## Hypotheses

| # | Hypothesis | Status | Killing/confirming evidence |
|---|---|---|---|
| H1 | Same bug as before — deliverable misrouting still broken (stale compile / wrong row) | **[RULED-OUT]** | Run `848876d0`: `output.html` exists on disk (12:58), `workflow_runs.deliverable_filename = output.html`, `output` column carries the HTML; run payload confirms `single_file` in both `deliverable` and `selections.__deliverable__`. The mechanics are fixed. |
| H2 | The "How to deliver" write_file instruction (factory.py:570-573) is leaking into the output text | **[RULED-OUT]** for this run | No artifact contains the instruction text; the parent called `write_file` correctly; only one `artifact_fallback` (gai0pd) and its content is the "no file named cat" text, not the delivery instruction. The headed-block mitigation is holding. |
| H3 | The run brief ("cat") is injected into every step's user message and competes with the steps' own prompts | **[CONFIRMED — root cause A]** | Persisted `agent_input` events show `=== ORIGINAL USER REQUEST ===\ncat` + `Inferred Intent: cat` in all four agents' messages. Code path: `kernel_services.run_agent:1331-1335` passes `self._user_message` → `engine._run_agent:3693` → `_compose_context_message:8775`. Apple Writer's output ("There is no file named `cat` in `/`") is a direct answer to that injected request, not to its own prompt. |
| H4 | Ghost CURRENT TASK block injected (empty-input workers + shared-scratch race for the parent) | **[CONFIRMED — root cause B]** | All four `agent_input` events carry the block with the "Execute ONLY this task from the task list above." filler and no task list. Children: `run_worker` passes `task_number` unconditionally (`kernel_services.py:1084-1090`) while `parallel_group` sends `input:""` (`parallel_group.py:118`); filler substituted at `engine.py:8939-8941`. Parent: only setter of `ectx.build_task_number` is `kernel_services.run_agent:1326`; parent path passes `task_number=None`, yet its message says "Task 1 of 3" → a concurrent worker's save/restore (`:1317-1354`) leaked scratch into the parent's dispatch. |
| H5 | Roster block or child filenames in the parent's system prompt prime shell role-play | **[RULED-OUT]** as cause | `_build_roster` (`engine.py:3266-3308`) emits a benign "Your sub-agents have finished. They produced: - Name → file. Read the files you need" list — no shell phrasing. The Ball Writer had the same `-cat.md` filename in its own "How to deliver" and still wrote a ball joke, so filenames alone do not derail. The parent's shell narrative quotes the injected REQUEST ("cat") and gai0pd's corrupted artifact — both downstream of H3. |
| H6 | `planner: "skip"` (payload) vs `planner: "run"` (manifest) changes prompt composition | **[RULED-OUT]** as a distinct cause | Both paths inject a Planning Context block; `skip` merely uses `_default_planning_context` (`engine.py:1866,3093-3096`) whose `inferred_intent` is the brief echoed back — so skip *adds* a second verbatim "cat" rather than any disambiguation. No separate compose path; contributory to H3's salience only. |
| H7 | Model quality alone (Bedrock Haiku) | **[RULED-OUT]** as root cause | Two of three children obeyed their prompts under the same model; the one that failed is the one whose injected "request" most contradicted its step prompt. Model weakness sets the severity, the injected contradiction sets the direction — same split as the prior report's H4. |

## Root cause

**Defect A — the run brief is injected into every step of a composed workflow.**
`backend/agents/execution_engine/engine.py:8775` (`_compose_context_message`) opens every
agent's user message with `=== ORIGINAL USER REQUEST ===\n{brief}\n=== END REQUEST ===`,
and (`:8777-8802`) appends a Planning Context block — under `planner: "skip"` that block is
`_default_planning_context`'s verbatim echo of the brief (`engine.py:3093-3096`). This is
correct for registry pipelines whose agents exist to interpret the brief, but a composed
workflow's steps carry their own complete authored prompts (`factory.py:560-561` appends
`ctx.step_prompt` to the system prompt); the injection makes every step serve two masters.

**Defect B — ghost `CURRENT TASK` injection.** Two parts:
- `backend/agents/execution_engine/kernel_services.py:1084-1090` (`run_worker`) passes
  `task_number=worker_index+1` for every fan-out worker even when the strategy sent no
  task text; `engine.py:8935-8951` then renders the block with the filler line
  "Execute ONLY this task from the task list above." — an instruction about a nonexistent
  list, for every `parallel_group` child by construction.
- `kernel_services.py:1317-1354` (`run_agent`) implements the task scratch as
  save→mutate→restore on the **shared per-run** `self._ectx` while `parallel_group` runs
  three `run_agent` invocations concurrently; the interleaved restores leave a stale
  worker value behind, so the subsequently dispatched parent (which passes
  `task_number=None`) composes with `build_task_number="1"` and receives the ghost block.

**Mechanism chain (this run)** [CONFIRMED at every step from persisted evidence]:

1. User launches with `message: "cat"`; `topic_slug` → `cat`; children's artifact names
   become `1krppp8-<child>-cat.md`.
2. Each child's user message = `ORIGINAL USER REQUEST: cat` + `Inferred Intent: cat` +
   ghost `CURRENT TASK` — while its system prompt says "Write one short joke about an
   apple/ball/cat… Do not look for files".
3. The Apple Writer (system: apple; user: "cat"; tools: read_files) treats the injected
   request as primary and answers it as a file/command query → artifact contains
   "There is no file named `cat` in `/`…" (its streamed text, written by
   `artifact_fallback` at 10:52:34).
4. The parent composes with the same injected "request cat" (+ leaked "Task 1 of 3"),
   reads the three child files per its roster, finds one asserting "no file named cat",
   and reconciles everything into a page *answering* "cat" as a shell question — valid
   HTML (its format instruction held), wrong content (its content instruction lost).
5. `single_file` resolution reads `output.html` back correctly — faithfully delivering
   the corrupted content. The prior fix moved the failure from "wrong file" to
   "wrong words", which is why the user now perceives it as "prompt injected into output".

**Why it wasn't caught**:
- The generic injector (INV-1) intentionally has no per-workflow branches, and composed
  workflows with fully-authored per-step prompts are new on this branch; no test asserts
  a composed step's context message *excludes* the brief, or that a `CURRENT TASK` block
  requires a non-empty task body. [CONFIRMED by absence]
- The ectx scratch race is invisible in every sequential path (build loop, fanout_batch
  with real slices); `parallel_group` is the first concurrent caller of
  `kernel_services.run_agent`. [CONFIRMED structurally]
- Nothing fails loudly: green run, non-empty deliverable, valid HTML.

## Blast radius

- **Every composed workflow's every step** receives the brief + planning echo regardless
  of having its own prompt — content quality of all custom workflows is hostage to
  brief/step-prompt agreement. [CONFIRMED for this run; structural for all custom runs]
- **Every `parallel_group` child** gets the ghost CURRENT TASK block (empty input by
  design). [CONFIRMED]
- **Every `parallel_group` parent** is exposed to the scratch-leak race (three concurrent
  save/restores; leak observed on the only post-fix run inspected). [CONFIRMED here;
  frequency across runs OPEN]
- Briefs that collide with command/tool vocabulary ("cat", "ls", "test", "grep"…) on
  file-tool-granted agents are the worst case; ordinary topics degrade to subtler
  drift ("wrote the wrong subject entirely", per the in-code prior art). [LIKELY]
- `fanout_batch` with real per-worker slices, the prototype build loop, and registry
  pipelines are NOT affected by defect B's filler (non-empty task bodies) and use the
  brief legitimately (defect A is by-design there). [CONFIRMED in code]

## Recommended fix

1. **Ghost block (small, safe)**: in `run_worker` (`kernel_services.py:1084-1090`), pass
   `task_number=None` when `input` is empty — or in the injector (`engine.py:8939-8941`),
   emit no block when the task body is empty instead of the filler line. Risk: minimal;
   the filler renders only in the empty-body case, which is only `parallel_group` today.
   Must keep `fanout_batch`/build-loop bytes identical (INV-3 goldens).
2. **Scratch race (small)**: stop mutating shared `self._ectx` for per-invocation task
   state — thread `task_number/total/task_block` through `_run_agent`'s signature (or a
   per-invocation ectx view). Minimal alternative: have `parallel_group` explicitly clear
   the scratch before the parent's `run_agent`. Risk: `_run_agent`'s signature is
   long-armed; the minimal alternative is a one-liner but leaves the race for future
   concurrent callers.
3. **Brief injection (design decision — needs the user/product call)**: for steps that
   carry a non-empty `step_prompt` (an INV-1-compliant, workflow-agnostic signal), either
   omit the `ORIGINAL USER REQUEST` block, or relabel/reframe it as reference material
   ("Run topic (context only — your instructions are above): …"). **Caveat**: some
   composed workflows legitimately parameterize on the brief ("write a joke about
   <brief>"); silently dropping it would break those, so reframing is the safer default
   and omission should be author-controlled. Also skip the Planning Context echo when the
   planner was skipped (`inferred_intent == brief` adds a second verbatim copy for zero
   information).
4. Do NOT touch the "How to deliver" block or the deliverable path — verified working.
   Constraints: INV-1 (no workflow/agent-name branches), INV-3
   (`test_skill_prompt_baseline.py` + 17 characterization goldens stay byte-identical —
   registry pipelines must not see a changed context message), INV-5 (prefer no new
   manifest keys; the `step_prompt`-presence gate needs none).

## Verification plan

- **Fails now**: unit-compose the context message for a `parallel_group` child
  (`input=""`) and assert it contains no `=== CURRENT TASK ===`; compose the parent after
  three concurrent child runs and assert the same; assert a step with a non-empty
  `step_prompt` gets the reframed/omitted brief per the chosen design. All fail today
  (the persisted `agent_input` events are the current-behavior fixture).
- **Passes after**: same assertions; plus a live re-run **by the user** (never run live
  LLM evals from the agent side) of workflow `76840113-…` with brief "cat" AND a neutral
  brief ("sunset") — `output.html` must be a jokes page in both, and the "cat" run is the
  regression sentinel for the command-collision case.
- **Regression**: `python3.11 -m pytest tests/agents/ tests/unit/` — especially
  `test_skill_prompt_baseline.py`, `test_compiler_subagents.py`, the characterization
  goldens, and any fanout/parallel_group suites.

## Open questions

- **[OPEN]** Product intent for defect A: should composed-workflow steps receive the run
  brief at all, and should that be per-step author-controlled? (Some workflows need it;
  this one is harmed by it.) Resolve: user decision before fix 3 is designed.
- **[OPEN]** How often the parent scratch-leak fires across runs (observed 1/1 inspected
  post-fix run; older runs predate `parallel_group`'s current form). Resolve: sweep
  `run_events.agent_input` for parents with a `CURRENT TASK` block across recent custom
  runs.
- **[OPEN]** Whether a neutral brief still measurably degrades child outputs (severity of
  defect A absent command-collision). Resolve: the user's "sunset" run, before/after fix.
- **[ASSUMED]** The user's complaint refers to this post-fix run's injected/echoed text
  (the timeline, the workflow id, and the payload they supplied all match run
  `848876d0`); no other run exists after the DB fix.
