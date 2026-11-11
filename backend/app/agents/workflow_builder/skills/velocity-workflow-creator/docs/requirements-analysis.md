# Requirements analysis

Turn the request into a **Workflow Brief** before you design anything. The brief is
short, but every field in it changes the manifest. Fill what the request answers,
mark the rest as unknown, then decide which unknowns need a question.

This file supplies the Velocity-specific signals, question bank and feasibility limits.
The method it serves is `problem-decomposition.md`, which is mandatory: its Step 0 (§2)
fills Goal, Trigger, Deliverable, Done when and Not in scope; its triage (§3) and
breakdown (§4-5) turn the Brief into parts; and its clarification policy (§6) decides
which unknowns are asked. Where the two files differ, `problem-decomposition.md` wins on
method and this file wins on platform facts.

## 1. The Workflow Brief

| Field | What to pin down |
|---|---|
| Goal | The outcome in one sentence: "Turn X into Y for Z." A result, not an activity. |
| Trigger | What starts a run: a Composer launch with a brief, uploads, a chained run of another workflow. |
| Done when | 1-5 observable conditions that prove the goal is met. Never guessed: if the request cannot fill it, ask. |
| Not in scope | Nice-to-have features that neither the request nor the deliverable's playbook needs. Nothing in this list becomes a step. |
| Deliverable | What comes out: a text answer, one named file (`.md`, `.html`, `.json`, `.csv`), several files (a bundle), a deck. File name and format. |
| Inputs | What a run starts from: the brief only, uploaded documents (types, count, size), images, an OpenDesign template or design system, a previous run of this workflow, a finished run of another workflow (chaining), Jira/GitHub/GitLab/Slack data. |
| Stages | The distinct transformations: understand, research, analyze, plan, generate, review, validate, assemble, publish. One stage usually becomes one step. |
| Variation | Does the path depend on the input (branch), repeat until good enough (loop), or end in another workflow (hand-off)? |
| Scale | Is there a list of independent items handled the same way (documents, screens, epics, modules)? How many at most? |
| Quality bar | Who decides "good enough": a deterministic validator, an AI critic, a person? Which outputs need sign-off before the run continues? |
| Constraints | Cost, speed, model preference, EU data residency, run-time limit, tone, format and compliance rules. |
| Runtime | Where it will run (this sets the trust level, see `trust-and-security.md`): Run once in the Composer (`user`), a saved Composer workflow (`db`), an override of a built-in (`user`), or an engineer-shipped file (`file`). |
| Presentation | Name, short name, one-sentence description, icon, launchable or hidden. |

### Requirement classes (for "Not in scope" and the coverage table)

- **Stated**: a phrase the user wrote. Always a requirement.
- **Implied by the deliverable's playbook**: a stage the playbook (`docs/playbooks/`) needs to
  make the deliverable well, for example clarification and a specification for a prototype made
  from documents. These are requirements too. Include them, and list them in the coverage table
  as "implied by playbook".
- **Nice-to-have**: neither stated nor implied by the playbook. Leave it out and name it under
  Not in scope.

"Not in scope" holds only nice-to-haves.

## 2. Signals and what they imply

| The requirement says | Design consequence |
|---|---|
| "from the attached PDFs / Word / Excel / PowerPoint" | A reading step with `tools.tool_sets: ["file_extract"]`; documents are read from `.uploads/`, so the launch must stage the uploads. |
| "for each document / screen / item" | Plan then fan out: a planner writes a `json_tasks` list, workers run as `fanout_batch` (or `subagents.mode: fanout`), an aggregator merges. Mind the worker budget (8 under `user` trust). |
| "look at these N aspects in parallel" (a fixed set) | `subagents.mode: parallel` children under an aggregator step. |
| "do A, then B, then C" | Linear chain with `depends_on` pins. |
| "until it is good / iterate / refine" | Critic step that produces `route_decision` and routes back with `feedback`; cap with `loop_max_iterations` 2–3. |
| "if X do this, otherwise that" | Classifier step + `gates: ["conditional"]` + `route.outcomes`; branch steps `depends_on` the classifier. |
| "someone approves / reviews before it continues" | `human` gate on the step whose output is reviewed (pause after it). |
| "let the user choose / correct before step N" | `before-human` gate on step N (the person edits the previous step's output). |
| "the user picks the path" | Placeholder step + next step with `before-human` + `conditional` and `route.condition_agent` pointing at the placeholder. |
| "then pass it to the prototype / backlog workflow" | `route` outcome with `trigger: workflow` and `feedback` (child run), or chaining: the target lists this workflow in `chained_from`. |
| "use our brand / template / design system" | `context_providers: ["opendesign"]`, `injects` on the steps that design, `design_mode` `web` or `deck`. |
| "from this screenshot / image" | `input_providers: ["run_images"]` (every catalog model has vision). |
| "a clickable HTML prototype" | Final step writes one `.html` file; `validators: ["html_static", "html_render"]` + `gates: ["validation"]` + `fix`. |
| "compile / run tests / lint the code" | `tools.exec` + gates `security`, `approval`, `validation` + `code_*` validators. Runs only in an engineer-shipped (`file`) workflow; Python only; every exec step waits for an approval. |
| "search the web / latest data" | Not available: the internet tools are stubs. Say so and design around uploads or model knowledge. |
| "read Jira / GitHub / GitLab", "post to Slack" | `tools.connectors` for GitHub and Jira (`jira__search_issues` style names); Slack posts use `tools.mcp` + `tools.integrations`. The account must have connected the app; put a `human` gate before any write. |
| "query our database", "write files outside the run" | Powerful MCP servers (postgres, filesystem) need a `secrets` grant behind the `security` gate, which blocks the step in this platform build. Decline and route to engineering. |
| "fast / cheap" | Fewer steps, no loops, cheap models (`eu.anthropic.claude-haiku-5-5`, effort `low`/`medium`). |
| "best possible quality" | `eu.anthropic.claude-sonnet-5-5` with effort `high`/`xhigh` on reasoning steps, a premium model on the single hardest step, a critic loop, a human gate. |
| "EU data must stay in the EU" | `eu.*` model ids only; `global.*` (GPT-5.6) requests route worldwide. |
| "ask me X before it starts", "ask me what you need first" | Choose by trust (`quick-reference.md` §2a). Composer Run once (`user`) or a saved workflow (`db`): an intake step with `gates: ["human"]`, `redoable: true`, `reply: "last_message"`, planner and clarify `skip` (`patterns.md` §21); the user answers with Request changes. API launch with no output type, or a wizard: `planner: "run"` and `clarify.mode: "auto"`; the answers land in `PLANNER.md` only. Engineer file: an `ask_user` step. |
| "no questions, just run" | `clarify.mode: "skip"`, `planner: "skip"`. |
| "revise what the last run produced" | A revision workflow: `deliverable.revises_existing`, `previous_run` provider (saved workflows only), `planner: "skip"`. |
| "a report / an answer" | `streamed_text` (the final step's reply) or `single_file` with a `.md` name. |
| "one file" | `single_file` with `name`. |
| "a codebase / many files" | `serialized_sandbox`. |
| "slides / a .pptx" | Prefer the built-in deck workflows; a custom workflow can deliver an HTML deck as `single_file`. The `pptx` tool set and `ppt` deliverable are trusted only. |
| "audit everything" | The default hooks already log and secret-scan every step; add `otel_tracing` where traces are required. |
| "big batch / long run" | Raise `limits` (trusted only) or split into chained workflows. |

## 3. Unknowns: ask or assume

Classify every unknown with `problem-decomposition.md` §6 first. **Functional** unknowns
change the outcome, the scope or a business rule: ask them. **Internal** unknowns are yours
to decide: never ask them, record each as an assumption. The lists below are the functional
and internal unknowns that come up most often in a Velocity workflow.

**Functional, design-changing** (resolve before designing; ask if the request does not answer):

1. The deliverable's type and format.
2. Whether inputs are uploaded files, and which kinds.
3. Whether a person must approve or choose anything mid-run, and where.
4. Branching criteria (the exact outcomes) and loop exit criteria.
5. The size of any item list, compared with the worker budget.
6. Anything that needs trusted capabilities (exec, `ask_user`, `uploaded_files`/`previous_run` providers, raised limits) — this decides the target trust.
7. Integrations: which systems, read or write, and whether connectors exist.

**Internal, defaultable** (never ask; choose, then list as assumptions): models and effort,
agents and tools, step count, sizing and order, parallel group or fan-out, step names and
ids, icon and catalog text, clarify topics, retry and loop caps, prompt wording, file names
for intermediate work, the complexity tier and the decomposition pattern.

## 4. Question protocol

- Ask only functional questions. Each must pass the litmus test
  (`problem-decomposition.md` §6.4): "If the user answers differently, the OUTCOME changes
  because ...". If every answer leads to the same structure, do not ask.
- Never ask what the request, the project context or an existing workflow already answers.
- At most **5 questions per round** and **2 rounds**. Batch them in one message. Needing a
  third round means the Step 0 understanding was wrong: redo the Brief instead of asking.
- Each question states why it matters, offers options, and marks a recommended default.
- If the user answers "you decide", "use defaults" or "just do it", stop asking: proceed
  with the defaults, list them in the **Decisions** table of your final response, and list
  the unanswered functional questions as risks on the Open questions line.
- If one answer makes the request impossible on the platform, say so immediately and
  offer the nearest feasible design (section 6).

Template:

```text
Before I design the workflow I need a few decisions (defaults in brackets):

1. Output — should the result be one Markdown report, or a separate file per document?
   [one report: contract-review.md]
2. Inputs — will you upload the contracts as PDF/DOCX, or paste the text into the brief?
   [upload; I'll add a document-reading step]
3. Review — should a person approve the summary before the run finishes? [yes, one approval at the end]
4. Volume — how many documents per run at most? Under the default budget a run can fan out to 8 workers. [up to 8]
5. Where will it run — Run once from the Composer, or a saved workflow? [saved workflow]
```

## 5. Question bank

| Area | Question | Default when the user says "you decide" |
|---|---|---|
| Output | One file, several files, or a chat-style answer? | One Markdown file for documents, one HTML file for UI, a bundle for code. |
| Output | Exact file name / format? | `<topic>.md` (kebab-case). |
| Output | Sections or template the output must follow? | A sensible structure stated in the final step's prompt. |
| Inputs | Uploaded files? Which types? How large? | Brief only; if files are mentioned, PDF/DOCX/XLSX/PPTX via `file_extract`. |
| Inputs | Template or design system? | None, unless the output is UI or slides. |
| Inputs | Continue from an earlier run? | No. |
| Process | Must any stage be done by a specific existing agent? | `custom-agent` steps with tailored prompts. |
| Process | Items to process independently? Maximum count? | Fan out when there are 3+ independent items; cap at the budget. |
| Process | Branches: what are the outcomes and what decides? | No branching. |
| Quality | Who checks quality: validator, AI critic, person? | AI critic loop (max 2 retries) for prose; validators for HTML/code; one human gate before a high-stakes deliverable. |
| Quality | Where does a person approve? | At most one approval, at the end. |
| Runtime | Run once or saved? Account tier? | Design for `user` trust; saved `db` only when a trusted feature is required. |
| Runtime | Cost or speed priority? | Balanced: Sonnet 5.5 for reasoning/writing, Haiku 5.5 for extraction and routing. |
| Runtime | Data residency? | EU models (`eu.*`). |
| Integrations | Which systems, read or write, connector available? | None. |
| Presentation | Name and description? | Derived from the goal. |

## 6. Feasibility check

Stop and explain, with the nearest feasible alternative, when the request needs:

| Need | Why not | Nearest feasible design |
|---|---|---|
| Live web search or fetch | The internet tools return "not yet available" | Uploaded sources, MCP integrations, or model knowledge with a disclaimer step |
| Running code from a Composer workflow | `exec` is rejected at `user` trust and refused at run time at `db` trust | Ship it as an engineer workflow (`file` trust) with `security` + `approval` gates; or generate and review code without running it |
| More than 8 parallel workers under `user` trust | `limits` may only be lowered | Batch items per worker, save the workflow (trusted limits up to 200), or split into chained runs |
| More than two nesting levels | The compiler accepts root, child, grandchild only | Flatten: use a fan-out instead of deeper nesting |
| Passing the user's free text to a triggered workflow | `feedback` is a static string | Chain instead: the target reads the source run's output via `chain_context` |
| A custom tool, validator or provider that is not registered | Manifests can only name registered capabilities | Do the work in a `custom-agent` prompt, or route to engineering to add a capability |
| Mid-step questions to the user under `user` trust | `ask_user` is dropped by the `user` cap | An intake step with a `human` gate and `redoable: true` (`patterns.md` §21), or a `before-human` gate |
| Clarify questions on a Composer launch | Every Composer launch (Run once, saved workflow) selects an output type, which forces clarify to `skip` | An intake step with a `human` gate (`patterns.md` §21) |
