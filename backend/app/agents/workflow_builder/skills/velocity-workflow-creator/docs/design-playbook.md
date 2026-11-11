# Design playbook

How to turn a Workflow Brief into a step graph: how many steps, which topology, where
gates go, which model runs where, and what to leave out. Patterns with ready JSON are in
`patterns.md`; field-level rules are in `field-guide.md`.

The input to this playbook is the triaged, self-audited breakdown from
`problem-decomposition.md` (mandatory, SKILL.md step 2), not the raw request. Its tier sets
the size range below, its parts become steps or phases, and its waves, gates and checkpoints
become the topology. Its §8 maps each decomposition term to a manifest field.

## 1. Size the workflow first

Pick the smallest size that meets the brief and fits the tier: SIMPLE is Tiny or Simple,
MODERATE is Simple or Standard, COMPLEX is Standard or Complex (`problem-decomposition.md`
§8.2). Every extra step costs a model call that
re-reads the whole context, adds latency and a new failure point.

| Size | Root steps | Typical shape | Use when |
|---|---|---|---|
| Tiny | 1 | one `custom-agent` | One transformation with one output ("summarize", "translate", "draft an email"). |
| Simple | 2–4 | linear chain | Distinct think → make (→ polish) stages, no review loop. |
| Standard | 4–8 | chain + one quality mechanism | A critic loop, a validator, or one human checkpoint; maybe one parallel group. |
| Complex | 8–16 | stages + parallel group or fan-out + gates | Multi-stage documents, research with several tracks, per-item processing, code with tests. |
| Large | 16+ | split it | The Composer canvas holds 16 root steps. Move repeated work into a fan-out, group stages under `subagents`, or chain two workflows. |

Sizing checks:
- Write each step's job as one sentence with one primary output. If you need "and", split it; if two steps produce the same artifact with no new decision, merge them.
- Never create N near-identical root steps for N items. Use a fan-out (`fanout_batch` or `subagents.mode: fanout`) with a task list.
- Separate thinking (analysis, planning), making (writing, building) and checking (critic, validator). Merge them only for Tiny/Simple workflows.
- Give a step its own model/tools/gate only when it needs them; that is a valid reason to split a step, too.

## 2. Decompose into steps

Start from the parts of the `problem-decomposition.md` breakdown, in wave order, with what
each produces and consumes (§4.3 Pass D). Decide for each part whether it is its own step or
a phase of a neighbouring step (§8.1). Then:

1. List the stages in data order: what each needs and what it produces.
2. Assign each stage an output: a reply (small text), a named work file (`research/market.md`,
   `build/tasks.json`) or the deliverable.
3. Mark stages that are independent of each other (parallel) and stages that repeat per item (fan-out).
4. Mark decisions: branch (forward route), loop (backward route), hand-off (workflow trigger).
5. Mark where a person must review (post-step `human`) or correct/choose (pre-step `before-human`).
6. Pick the final step: it owns the deliverable. One writer per file.
7. Give every `custom-agent` step a kebab-case `instance_id`, a readable `name` and a prompt
   written to the standard (`quick-reference.md` §8).
8. **Facts reach every step that uses them.** List the facts the deliverable needs and trace
   each one from its source (the request, the user's answers, an upload) to every step that
   writes or checks with it. The request reaches only the first step.
9. **Intake step** when the user must supply facts or the brief may lack them: it gathers
   them, asks for the missing ones and reports a facts block the later steps consume. The
   mechanism depends on the trust (`quick-reference.md` §2a, `patterns.md` §21).
10. **Reviewer/editor (QA) step** when the brief states checkable constraints (length, tone,
    required items, inclusive language, no invented facts): it consumes the facts and the
    draft, checks each constraint, fixes what fails and replies with the final document.
11. Give every step a defined behavior for missing input (stop with `NEEDS_INPUT`, ask, or
    assume and mark it). A run that lacks facts still completes, so a step without this rule
    writes placeholders.

**Agent choice.** Use `custom-agent` with a tailored prompt for almost every step: it has no
fixed contract and works in any workflow. Use a catalog agent only when its contract fits
exactly:
- Stand-alone agents (pipeline_type `custom`, no inputs): `market-research-agent`,
  `swot-analyst`, `roadmap-planner`, `security-auditor`, `test-case-generator`,
  `performance-optimizer`, `documentation-agent`, `report-generator`, `task-list-planner`.
- Pipeline agents (prototype, app_builder, user_stories, dotnet, mulesoft, ppt) expect their
  upstream agents and files. Use them only with their whole upstream chain; usually it is
  better to chain into, or trigger, the predefined workflow itself.
- Never use revision, chat, spec_kit, fixture or `sc001-*` agents in a new workflow.
- A catalog agent may appear only once per workflow (its id is the step id). Repeat work with
  several `custom-agent` steps instead.

## 3. Choose the topology

```text
Is there one transformation?                         -> Tiny: one step
Are the stages strictly sequential?                  -> Linear chain (pins: depends_on)
Are there a few fixed, independent sub-tasks?        -> Parallel sub-agents under an aggregator
Is there a list of similar items (known at run time)?-> Plan -> fan-out (fanout_batch) -> aggregate
  ...and the items depend on each other?             -> Plan -> wave_scheduler (json_tasks depends_on)
  ...and one worker must do them in order?           -> task_loop (heading_tasks)
Must output reach a quality bar?
  ...checkable by code (HTML, Python)?               -> validators + validation gate + fix
  ...judgement call?                                 -> critic -> route back (loop, max 2-3)
  ...a person's call?                                -> human gate (redoable)
Does the path depend on the input?                   -> classifier + conditional route (branch)
Does a person choose the path?                       -> placeholder + before-human + condition_agent
Should another workflow take over?                   -> route outcome trigger: workflow (+ feedback)
Should another workflow continue from this output?   -> chaining (target's chained_from)
```

Combine patterns freely, but keep each mechanism justified by a requirement.

## 4. Data flow between steps

Pick one mechanism per edge:

| Mechanism | How | Best for |
|---|---|---|
| Roster (default) | Consumer has `read_files: true` and `depends_on: ["custom-agent:<producer>"]`. Its prompt gets "Earlier steps produced: - Name → file" and the step reads those files. | Most edges between `custom-agent` steps. |
| Paste | Producer `produces: ["label"]`, consumer `consumes: ["label"]` and `tools.read_files: false`. The producer's output is pasted into the consumer's message. | Small text hand-offs with zero tool calls (cheap, fast), decision steps that judge a previous output. |
| Named work files | Producer has `write_files: true` and its prompt names the exact path (`research/market.md`); consumers' prompts name the same path. The step file then holds a one-line report. | Large or structured artifacts, several files per step, fan-out targets, files read by many later steps. |
| Chain payload | `chain_context` provider copies a source run's output into `.context/`. | Workflows that continue another workflow's result. |

Rules:
- Only the first step receives the brief in its task message (a step re-run by a backward
  route gets it again). A later step sees only what is pasted into it, its fan-out task or
  the files it reads; the brief is on disk at `.context/user-prompt.md`. Have the first step
  carry forward every fact and constraint the later steps need.
- Declare `depends_on` with compiled ids (`custom-agent:<instance_id>`). A bare instance id
  in `depends_on` is silently ignored.
- When any step declares `consumes`, pin every later root step with `depends_on`, or the
  resolver may re-sort the plan.
- One writer per file. Two steps that both write the same file make the result depend on order.

## 5. Gates: where a person or a check stops the run

| Gate | Fires | Use for |
|---|---|---|
| `human` | After the step, on its own output. Approve, reject, approve-with-edits; redo when `redoable: true`. | Sign-off on a draft, a plan, a customer-facing text, before expensive downstream work. |
| `human` on an intake step (`redoable: true`, `reply: "last_message"`) | After the intake replies with its facts and questions. Request changes re-runs it with the answers as `=== USER GUIDANCE ===`; Approve continues. | Asking the user for facts before the work on a Composer launch, where clarify cannot ask (`patterns.md` §21). |
| `before-human` | Before the step, on the previous step's output; the edit becomes this step's input. | Let a person correct a plan before building, or type a choice. |
| `validation` | After the step; runs the step's `validators` against the deliverable file. Critical findings block. | HTML prototypes (`html_static`, `html_render`), Python (`code_*`), coverage checks. |
| `conditional` | After the step; routes on a `route_decision`. | Branches, loops, hand-offs. Needs `route`. |
| `security` + `approval` | Required together on any step granting `exec`; `approval` pauses for a person. | Running code, in engineer-shipped (`file`) workflows only. |

Placement rules:
- At most one of `human`, `before-human`, `approval` per step.
- Put a `human` gate after the most consequential decision (scope, plan, spec) rather than at
  every step: a review before an expensive build saves more than one after it.
- Use at most 1–2 human gates in a workflow unless the user asks for more. Each gate blocks
  the run until someone answers.
- Keep gates off fan-out workers and parallel children; gate the planner (before work is
  spawned) or the aggregator (after it is merged). No shipped workflow gates a worker.
- Pair every `validators` list with `gates: ["validation"]` and `fix: {"max_attempts": 2}`.
  Without `fix`, the first critical finding fails the run.

## 6. Models and effort

Precedence: run override > step `model` > AGENT.md model > workflow `model` > session > global
default. Set a workflow-level `model` for the common case and override per step only where a
step differs.

| Step type | Model (EU) | Effort |
|---|---|---|
| Classification, routing decision, extraction, formatting, simple fan-out worker | `eu.anthropic.claude-haiku-5-5` (cheap) | `low` or `medium` (default `xhigh` is fine when accuracy matters) |
| Analysis, planning, writing, synthesis, code, critic | `eu.anthropic.claude-sonnet-5-5` (standard) | default `high`; `xhigh` for planning and critique |
| The single hardest reasoning step (architecture, complex trade-offs) | `eu.anthropic.claude-opus-4-6-v1` (premium, basic tier cannot launch it) | `on` (budget-mode Claude accepts `none`/`on`) |
| Non-EU frontier reasoning | `global.openai.gpt-5.6-sol` (premium, routes worldwide) | `medium`–`xhigh` |
| Non-EU cheap and fast | `global.openai.gpt-5.6-luna` (cheap, routes worldwide) | `low`–`medium` |

- Always set `model.model` when you set `effort`; the effort is validated against that model's own levels.
- Add `fallback` for long or critical steps, e.g. a Haiku step with `["eu.anthropic.claude-haiku-5-5", "eu.anthropic.claude-sonnet-5-5"]`.
- `model.max_tokens` is accepted but not applied by the current runtime; do not rely on it.
- Model ids must come from the catalog. Launch rejects unknown or non-entitled ids.

## 7. Quality strategy

Choose the cheapest mechanism that can actually decide quality:

1. **Deterministic validator** when one exists for the output type (HTML prototype, Python code, coverage).
2. **AI critic loop** for prose and plans: a critic writes notes, replies `{"decision": "pass"}` or `{"decision": "revise"}`, and routes back with `feedback`. Cap at 2–3 iterations and choose `on_loop_exhausted`: `continue` (ship best effort) or `fail` (stop).
3. **Human gate** when acceptance is subjective or high-stakes.
4. **Retry** (`retry: {max_attempts: 2, backoff_seconds: 5}`) only for throttling on long or critical steps. It does not fix bad output.

## 8. Cost and speed levers

- Fewer steps and fewer tool calls: every model call re-sends the conversation.
- Prompts that name exact paths ("read `research/market.md`") instead of letting agents `ls`/`glob`.
- Paste small hand-offs (`consumes` + `read_files: false`) instead of read tool calls.
- Cheap models on routing, extraction and workers; effort `low` where reasoning adds little.
- Parallelize independent work (`subagents.mode: parallel`, fan-out); concurrency is clamped to 5.
- No loops without a cap; no human gates the user did not ask for.

## 9. Anti-patterns

| Anti-pattern | Fix |
|---|---|
| A gate, validator, hook or skill "just in case" | Every capability must trace to a requirement; list the reason in your design summary. |
| `write_files: true` on every step | Grant writes only to steps that create files; a final `streamed_text` step must reply, not write. |
| `exec`, `secrets`, `network`, `spawn_subagents` requested without need | Remove; declarative fan-out needs no spawn grant. |
| One root step per item | Fan-out over a task list. |
| A critic loop with no cap or exit criterion | `loop_max_iterations` 2–3 and a precise decision rule in the critic prompt. |
| Decision step that writes prose before the JSON | `reply: "last_message"` and "reply with exactly one line". |
| A prompt that duplicates the next step's job | Each prompt says what NOT to do ("do not write the report; the next step does"). |
| Pipeline agents mixed into an unrelated workflow | Use `custom-agent`, or chain into / trigger the predefined workflow. |
| Mechanical `assemble_*` / `extract_prototype_ui` steps outside their workflows | They depend on that workflow's exact files and ids; use `custom-agent`. |
| Secrets, tokens or credentials in prompts | Never. Integrations use host-configured connectors. |
| Live web research | Not available; use uploads or integrations. |
| Facts only from clarify (`planner: run`, `clarify: auto`) on a Composer workflow | A Composer launch forces clarify to skip, so nothing is asked and the steps get no facts. Use an intake step with a `human` gate (`patterns.md` §21), and let the steps use the facts in the request too. |
| A final step that never sees the facts | Paste the facts block (`consumes`) into every step that writes or checks; the request reaches only the first step. |
| Prompts written to a one-line-per-section skeleton | Write the full standard (`quick-reference.md` §8): phases with rules and numbered steps, missing-input behavior, exact output, checks. The validator warns below 2,000 characters. |
