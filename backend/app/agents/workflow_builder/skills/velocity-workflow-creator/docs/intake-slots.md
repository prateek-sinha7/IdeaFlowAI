# Intake slots

The Workflow Brief (SKILL.md step 1) written as slots. The intake step fills them from the
request and the user's answers, asks about the gaps, and hands the filled slots to the
builder as the Brief. Used only when the builder's intake is switched on
(`BUILDER_INTAKE_V2_ENABLED`); with it off nothing reads this file.

The shape is `schema/intake-brief.schema.json`. The readiness rule is
`scripts/intake_readiness.py`. A worked dialogue is `docs/examples/intake-dialogue.md`.

## 1. A slot

| Field | Meaning |
|---|---|
| `value` | The fact, in one or two plain sentences. `null` when unknown. |
| `source` | Where the value came from (section 2). |
| `criticality` | `blocking`, `important` or `minor`. Fixed per slot (section 3). |
| `reason` | Why the value is what it is. Required with `not_applicable`. |

## 2. Sources

| Source | Use it when |
|---|---|
| `request` | The request states the fact, or it follows from the request with no other reading. |
| `user` | The user gave it in an answer: a chosen option or their own words. |
| `upload` | An uploaded file states it. |
| `assumed` | You chose a value the request does not state. An inference with more than one reasonable reading is an assumption, not `request`. |
| `not_applicable` | The slot has no meaning for this workflow. Allowed only for `human_approval_points`, `external_systems`, `write_destinations`, `irreversible_actions` and `input_variability`, and only with a `reason`. It counts as filled. With a write outside the run, `write_destinations` and `human_approval_points` cannot be `not_applicable`. |
| `unknown` | Nothing to go on yet. `value` is `null`. |

## 3. The slots

### Blocking: the workflow cannot be designed right without them

| Slot | What it pins down | Brief line | Typical question |
|---|---|---|---|
| `goal` | The outcome, "turn X into Y for Z". A result, not an activity. | Goal | "When a run finishes, what must exist that did not before?" |
| `deliverable` | Type and format: a text reply, one file (name and format) or a bundle. | Deliverable | "One Markdown file, one file per input, or the answer shown in the chat?" |
| `done_when` | 1-5 observable conditions that prove the goal is met. | Done when | "How will you know the output is right?" |
| `input_source` | What a run starts from: the brief, uploads (which types), a previous run, an external system. | Inputs, Trigger | "Where do the documents come from?" |
| `input_variability` | How inputs differ in ways that change the work: digital vs scanned PDF, languages, layouts, sizes. | Variation | "Are some PDFs scans that need OCR?" |
| `output_structure` | What the output must contain and keep: sections, tables, headings, images, length. | Deliverable, Constraints | "What must the Markdown keep: headings, tables, images, page numbers?" |
| `external_systems` | Systems the workflow reads or writes (Jira, GitHub, GitLab, Slack), and read or write. | Inputs | "Should it post the result anywhere, or only return it?" |
| `write_destinations` | Where each write goes: the Slack channel, Jira project, GitHub repository or email recipients, or "chosen at each launch". | Inputs | "Which Slack channel should it post to?" |
| `irreversible_actions` | Anything that cannot be undone: posts, messages, integration writes, deletions. | Quality bar | "What should it post or write, and where?" |
| `human_approval_points` | Where a person must approve, choose or answer during a run. | Quality bar | Without writes: "Should a person review the result before it is final?" With writes: "What should the person approve before it posts?" |

### Writes outside the run (posts, integration writes, exec)

The skill does not allow a step that posts or writes outside the run without a person's
gate directly before it. So when `irreversible_actions` has a value:

- `write_destinations` is a blocking sub-fact: where each write goes. It cannot be
  `not_applicable`, and a session that asks nothing about it is not ready. "Chosen at each
  launch" is a valid answer when the user gives it.
- `human_approval_points` cannot be `not_applicable`.
- The approval question takes the WHERE/WHAT form only when the request itself (or the
  user's answer) names the write: Slack, Jira, email, GitHub. For example: "What should a
  person approve before it posts? Approve the final message before it posts (recommended) /
  Approve the draft earlier; later edits still pass a confirm step before posting". No option
  may remove the person ("No", "post automatically", "without review").
- When no write is named, and a write is at most one of the options, the approval question
  asks WHETHER a person reviews, with a "No, finish without a pause" option.
- If the user then picks a write option, or writes "post automatically" or "no review" with
  a write, the slot becomes `human_approval_points = gate-before-post (platform
  requirement)`, and the builder's final reply says in one line why the gate stays.
- Every option that names a destination (Slack channel, Jira project or issue, email
  recipients, GitHub repository) carries `followup_text` and `followup_slot:
  write_destinations`, so one round settles it. Code adds a missing one and counts it as a
  repair.

Without a write, `write_destinations` is `not_applicable` (reason: nothing is written outside
the run).

### Important: assume when needed, and say so

| Slot | What it pins down | Brief line |
|---|---|---|
| `volume_scale` | How many items per run (documents, pages, screens) against the 8-worker budget. | Scale |
| `quality_bar` | Who decides "good enough": checks in the prompts, a reviewer step, a critic loop, a person. | Quality bar |
| `constraints` | Tone, length, language, format rules, things to avoid, cost or speed, EU data. | Constraints |
| `trigger` | What starts a run: a Composer launch with a brief, uploads, a chained run. | Trigger |
| `runtime_trust` | Where it runs: Run once in the Composer (`user`) or a saved workflow (`db`). | Runtime |
| `depth` | "Fast or Thorough?". Only when the deliverable matches a playbook (UI prototype, requirements document); otherwise `unknown` with `value` null. | Stages |

An important slot may be `assumed`. Each assumed important slot is shown to the user as
"Assumption: <slot> = <value> - correct me if wrong".

### Minor: decide silently, never ask

Everything that problem-decomposition §6.2 and requirements-analysis §3 call internal:
models and effort, agents and tools, step count, sizing and order, parallel group or
fan-out, step names and ids, presentation text, clarify topics, retry and loop caps, prompt
wording, file names of intermediate work, the complexity tier and the decomposition pattern.
They are not slots. List any you decided under `minor_decisions`; the builder records them
in its Decisions table.

### Missing facts: needed, not given, never a placeholder

A fact the deliverable needs that neither the request nor the user gave, and that no slot
holds (for example the release-notes URL a launch email must link to), goes in
`missing_facts` with `if_missing` `omit` or `ask_at_run_time`. It is not asked when the brief
is otherwise ready (the fully specified case). The builder is told: "Missing facts: <list>. Do
not insert placeholders. Either omit the item and say so in the deliverable, or have the step
stop with NEEDS_INPUT: <item>, per the skill." The reply's Assumptions block lists each as
"Not provided: <fact> - the workflow will <omit it | ask at run time>". The Server_Gate refuses
a draft whose prompt tells the writer to insert a bracketed placeholder for one.

### Values the user gave must reach the steps

Every concrete identifier in a slot from the request or the user (a Slack channel, a Jira
project or issue key, an email recipient, a repository, a URL, a file name) must appear
verbatim in the prompt or config of a step that uses it. The handoff lists them; the
Server_Gate refuses a draft that drops one.

## 4. Readiness

The intake is ready when every blocking slot has `source` `request`, `user` or `upload`, or
`not_applicable` on one of the five slots that allow it (with a reason, and not ruled out by
a write outside the run). An `assumed` or `unknown` blocking slot means a question.

Two things force ready with blocking slots still assumed:

1. The user's whole reply is "defaults", "you decide" or an equivalent of at most four words.
   Each open question takes its recommended option with `source: assumed`.
2. The question rounds reach `BUILDER_INTAKE_MAX_ROUNDS` (2). This is treated exactly like
   "defaults".

After a forced ready no slot is left `unknown`: each takes its recommended option, or a
default, with `source: assumed`. Code appends an Assumptions block to the builder's final
reply listing every assumed slot as "<slot> = <value> - correct me if wrong".

## 5. Questions

- Never more than 5 questions. Open blocking slots come first, ordered by impact on the
  workflow's shape: external writes and destinations, input variability, output structure,
  scale, approval, then the rest.
- In the first round, when fewer than 5 blocking slots are open, the remaining places go to
  open important slots whose answer most changes the deliverable, in this order:
  `quality_bar`, `constraints` (tone, glossary, terminology, fidelity), `volume_scale`,
  `depth`. A later round asks only what is still open (1-5).
- Each question targets one blocking or important slot, never a minor one.
- 2-4 lettered options, exactly one marked recommended, then "Not sure - use default".
- An option that needs one more fact carries `followup_text` and `followup_slot`, for
  example "b) Also posted to Slack - name the channel in your reply". The user answers
  "4b #release-notes"; the text after the code fills the follow-up slot, so the question
  settles in one round.
- When the request names a system, connector or capability the platform does not provide
  (`catalog_lookup.py mcp` lists what exists), the intake adds a `feasibility_notes` line,
  shown above the questions: "Note: there is no CRM connector on this platform. The
  options below cover what the workflow can write to." It never substitutes silently.
- Each passes the litmus test: "If the user answers differently, the workflow changes
  because ___". Write the completed sentence in `litmus`; it is not shown to the user.
- Never ask what the request already answers.
- The message ends with: Reply e.g. "1a 2c 3b", or "defaults" to accept all recommended
  options.
