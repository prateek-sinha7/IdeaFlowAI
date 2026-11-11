# Workflow patterns

Each pattern lists when to use it, its shape, the JSON that implements it, and its traps.
Snippets show only the fields that matter; the platform's shipped workflows are in
`../examples/` (file trust; `catalog_lookup.py example` lists what each shows). Prompts are
abbreviated here; write full prompts to the standard (`quick-reference.md` §8, `prompt-writing.md`).

Conventions used below:
- `CA` means `"agent": "custom-agent"`.
- Compiled id of a custom step = `custom-agent:<instance_id>`. Use it in `depends_on`,
  `task_source.source_step` and `spec_step`. Route targets may use the bare `instance_id`.
- Children of a `subagents` group run **before** their parent; the parent is the aggregator.
- Only the first step in compiled order receives the brief in its message. Later steps see
  what is pasted into them, their fan-out task or the files they read; the brief is at
  `.context/user-prompt.md`.

---

## 1. Linear chain (roster hand-off)

Use for sequential stages. Each step reads the files of the steps it `depends_on`.

```text
analyze -> write -> polish
```

```json
"steps": [
  {"agent": "custom-agent", "instance_id": "analyze", "name": "Analyst", "gates": [],
   "prompt": "You are the Analyst. From the brief, list audience, goals, key messages and constraints as Markdown sections. Do not write the article."},
  {"agent": "custom-agent", "instance_id": "write", "name": "Writer", "gates": [],
   "depends_on": ["custom-agent:analyze"],
   "tools": {"read_files": true, "write_files": false},
   "prompt": "You are the Writer. Read the analysis listed under 'Earlier steps produced'. Write the full article in Markdown."},
  {"agent": "custom-agent", "instance_id": "polish", "name": "Editor", "gates": [],
   "depends_on": ["custom-agent:write"],
   "tools": {"read_files": true, "write_files": false},
   "prompt": "You are the Editor. Read the article listed under 'Earlier steps produced'. Reply with the final edited article only."}
]
```

Traps: a bare `"depends_on": ["analyze"]` is silently ignored. Keep `write_files: false`
on a final step whose reply is the `streamed_text` deliverable.

## 2. Paste chain (zero tool calls)

Use for short text hand-offs where speed and cost matter.

```json
{"agent": "custom-agent", "instance_id": "outline", "produces": ["outline"],
 "tools": {"read_files": false, "write_files": false}, "gates": [], "prompt": "..."},
{"agent": "custom-agent", "instance_id": "draft", "consumes": ["outline"], "produces": ["draft"],
 "depends_on": ["custom-agent:outline"],
 "tools": {"read_files": false, "write_files": false}, "gates": [],
 "prompt": "The outline is shown above. Write the full draft following it."}
```

Traps: paste happens only when `read_files` is `false`. Once any step declares
`consumes`, pin every later root step with `depends_on`, or the resolver may re-sort them.
A step without read access cannot open skills or uploads.

## 3. Parallel specialists -> aggregator

Use for a fixed set of independent sub-tasks. Children run concurrently (clamped to 5),
then the parent runs once and sees each child's file in its roster.

```text
            ┌ market-size ┐
 report  <- ├ competitors ├   (children first, in parallel)
            └ regulation  ┘
```

```json
{"agent": "custom-agent", "instance_id": "report", "name": "Report Writer", "gates": [],
 "tools": {"read_files": true, "write_files": false}, "reply": "last_message",
 "prompt": "Read the three research notes listed under 'Earlier steps produced' and write the report.",
 "subagents": {"mode": "parallel", "max_parallel": 3, "steps": [
   {"agent": "custom-agent", "instance_id": "market-size", "name": "Market Size", "gates": [],
    "tools": {"read_files": true, "write_files": false},
    "prompt": "Estimate the market size for the brief's product. Do not look for files from other steps; they run at the same time."},
   {"agent": "custom-agent", "instance_id": "competitors", "name": "Competitors", "gates": [], "prompt": "..."},
   {"agent": "custom-agent", "instance_id": "regulation", "name": "Regulation", "gates": [], "prompt": "..."}
 ]}}
```

Traps: siblings run at the same time, so a child must never wait for or read another
child's output. Every child counts against `limits.max_subagents` (8 under `user`
trust). No `spawn_subagents` grant is needed. The Composer shows at most 8 direct
children.

## 4. Sequential sub-steps (grouped chain)

Use when a stage has internal steps you want grouped under one node on the canvas.
`mode: sequential` chains the children in order, then runs the parent.

```json
{"agent": "custom-agent", "instance_id": "spec", "name": "Spec Writer", "gates": [], "prompt": "Combine the interview notes and the risk list into the spec.",
 "subagents": {"mode": "sequential", "steps": [
   {"agent": "custom-agent", "instance_id": "interview-notes", "name": "Interview Notes", "gates": [], "prompt": "..."},
   {"agent": "custom-agent", "instance_id": "risk-list", "name": "Risk List", "gates": [], "prompt": "..."}
 ]}}
```

## 5. Plan -> fan-out per item -> aggregate

Use when the items are discovered at run time (documents, modules, sections). A planner
writes a `json_tasks` list; one worker clone runs per task; an aggregator merges.

```json
{"agent": "custom-agent", "instance_id": "plan", "name": "Planner", "gates": [],
 "tools": {"read_files": true, "write_files": true},
 "prompt": "Write build/tasks.json: {\"tasks\": [{\"id\": \"t1\", \"title\": \"...\", \"targets\": [\"notes/t1.md\"], \"depends_on\": [], \"body\": \"...\"}], \"contract\": {\"task_count\": N}}. At most 6 tasks."},
{"agent": "custom-agent", "instance_id": "worker", "name": "Section Writer", "gates": [],
 "strategy": "fanout_batch", "depends_on": ["custom-agent:plan"],
 "task_source": {"kind": "parsed", "parser": "json_tasks", "target": "build/tasks.json", "source_step": "custom-agent:plan"},
 "fanout": {"mode": "parallel", "max_parallel": 4, "agent": "self"},
 "tools": {"read_files": true, "write_files": true},
 "prompt": "Your task is in your message. Write only the file named in its targets."},
{"agent": "custom-agent", "instance_id": "merge", "name": "Editor", "gates": [],
 "depends_on": ["custom-agent:worker"], "tools": {"read_files": true, "write_files": false},
 "prompt": "Read every file under notes/ (glob notes/*.md) and assemble the final document."}
```

Equivalent compact form: put the worker under the aggregator as
`"subagents": {"mode": "fanout", "max_parallel": 4, "task_source": {...}, "steps": [<worker>]}`.
The planner must still be an earlier root step.

Traps: the task count must fit the worker budget (8 under `user` trust, minus any other
fan-out in the run); tell the planner the maximum. Each task's `targets` must be distinct
so worker writes never collide. `source_step` must name an earlier step.

## 6. Dependency waves

Use when items depend on each other (module B needs module A). `wave_scheduler` runs
independent tasks in parallel waves and waits for dependencies.

```json
{"agent": "custom-agent", "instance_id": "modules", "name": "Module Builders", "gates": [],
 "strategy": "wave_scheduler", "depends_on": ["custom-agent:architect"],
 "task_source": {"kind": "parsed", "parser": "json_tasks", "target": "build/tasks.json", "source_step": "custom-agent:architect"},
 "fanout": {"mode": "parallel", "max_parallel": 4, "agent": "self"},
 "tools": {"read_files": true, "write_files": true}, "prompt": "..."}
```

Traps: every `depends_on` id inside the task list must exist, or the parser rejects the
plan before anything runs. Use `json_tasks` (it carries dependencies); `heading_tasks` has none.

## 7. Sequential task loop

Use when one worker must apply a plan's tasks in order (each task builds on the last).

```json
{"agent": "custom-agent", "instance_id": "builder", "name": "Builder", "gates": [],
 "strategy": "task_loop", "depends_on": ["custom-agent:plan"],
 "task_source": {"kind": "parsed", "parser": "heading_tasks", "target": "tasks.md", "source_step": "custom-agent:plan"},
 "tools": {"read_files": true, "write_files": true}, "prompt": "..."}
```

The plan uses `## Task 1: <title>` headings, numbered from 1. A task body ends at the next
`## ` heading, so tasks use `###` inside.

## 8. Quality loop (critic routes back)

Use when output must meet a bar that needs judgement. The critic writes notes, replies with a
decision, and routes back to the writer with `feedback`.

```text
requirements -> draft <-- revise --.
                  |                 |
                  v                 |
                review -- pass --> finalize
```

```json
{"agent": "custom-agent", "instance_id": "draft", "name": "Drafter", "gates": [],
 "depends_on": ["custom-agent:requirements"], "tools": {"read_files": true, "write_files": true},
 "prompt": "Write the draft to draft.md. If review-notes.md exists, revise draft.md to address every point in it."},
{"agent": "custom-agent", "instance_id": "review", "name": "Reviewer",
 "depends_on": ["custom-agent:draft"], "produces": ["route_decision"], "reply": "last_message",
 "tools": {"read_files": true, "write_files": true},
 "prompt": "Read draft.md and the requirements. Write review-notes.md. Then reply with exactly one line: {\"decision\": \"pass\"} if every requirement is met, otherwise {\"decision\": \"revise\"}.",
 "gates": ["conditional"],
 "route": {"outcomes": {
     "pass": {"trigger": "step", "target": "finalize"},
     "revise": {"trigger": "step", "target": "draft", "feedback": "Revise draft.md to address every point in review-notes.md."}},
   "loop_max_iterations": 3, "on_loop_exhausted": "continue"}},
{"agent": "custom-agent", "instance_id": "finalize", "name": "Finalizer", "gates": [],
 "depends_on": ["custom-agent:review"], "tools": {"read_files": true, "write_files": false},
 "prompt": "Read draft.md and reply with the final document only."}
```

Traps: the decision source must declare `produces: ["route_decision"]` and reply with the
JSON line only (`reply: "last_message"` drops tool-call chatter). `on_loop_exhausted:
"continue"` ships the last draft after the cap; `"fail"` stops the run. Without `feedback`
the retried step gets the same context and tends to repeat itself.

**When the critic is the LAST step** there is no `finalize` to route to. Declare the passing
decision as an end outcome, never leave it out:

```json
"route": {"outcomes": {
    "pass": {"trigger": "end"},
    "revise": {"trigger": "step", "target": "draft", "feedback": "Revise draft.md to address every point in review-notes.md."}},
  "loop_max_iterations": 2, "on_loop_exhausted": "continue"}
```

`{"trigger": "end"}` takes no `target` and no `feedback`. It finishes the run at this step and
reports any later step skipped. A decision that matches no outcome (and has no `default_next`)
FAILS the run, so a route whose outcomes all loop back can never succeed on its "pass" path;
the validator rejects that shape (`route-no-exit`).

## 9. Forward branch (classifier)

Use when the path depends on the input.

```json
{"agent": "custom-agent", "instance_id": "classify", "name": "Classifier",
 "produces": ["route_decision"], "tools": {"read_files": false, "write_files": false},
 "model": {"model": "eu.anthropic.claude-haiku-5-5", "effort": "low"},
 "prompt": "Classify the ticket in the brief. Reply with exactly one line: {\"decision\": \"bug\"}, {\"decision\": \"feature\"} or {\"decision\": \"question\"}.",
 "gates": ["conditional"],
 "route": {"outcomes": {
     "bug": {"trigger": "step", "target": "bug-report"},
     "feature": {"trigger": "step", "target": "feature-spec"},
     "question": {"trigger": "step", "target": "answer"}},
   "default_next": "answer"}},
{"agent": "custom-agent", "instance_id": "bug-report", "depends_on": ["custom-agent:classify"], "gates": [], "prompt": "..."},
{"agent": "custom-agent", "instance_id": "feature-spec", "depends_on": ["custom-agent:classify"], "gates": [], "prompt": "..."},
{"agent": "custom-agent", "instance_id": "answer", "depends_on": ["custom-agent:classify"], "gates": [], "prompt": "..."}
```

Behaviour: exactly one branch runs; the others are reported skipped. Each branch step is a
terminal (the run ends there) unless a later step depends on it. `default_next` catches an
unrecognised decision; without it an unrecognised decision FAILS the run at the classifier.
To finish the run successfully on a decision, give that decision `{"trigger": "end"}`.

**Converging branches:** add a final step that `depends_on` every branch terminal. The
untaken branches are skipped and the final step still runs.

```json
{"agent": "custom-agent", "instance_id": "summary", "gates": [],
 "depends_on": ["custom-agent:bug-report", "custom-agent:feature-spec", "custom-agent:answer"], "prompt": "..."}
```

## 10. Human review checkpoint

Use when a person must approve an output before the run continues or finishes.

```json
{"agent": "custom-agent", "instance_id": "plan", "name": "Planner",
 "gates": ["human"], "redoable": true, "reply": "last_message",
 "tools": {"read_files": true, "write_files": true},
 "prompt": "Write plan.md. Your last message calls no tool and is the plan's full text."}
```

The reviewer approves, rejects, approves with edits, or (with `redoable: true`) asks for a
redo with instructions. `reply: "last_message"` shows only the final message on the review card.
The redo text reaches the re-run as `=== USER GUIDANCE ===`. To ask the user for facts
before the work, put this gate on an intake step (§21).

## 11. Person chooses the path

Use when a person, not a model, picks the branch. The placeholder step is the slot the
person overwrites at the next step's `before-human` gate.

```json
{"agent": "custom-agent", "instance_id": "ask", "name": "Choose a path", "produces": ["route_decision"],
 "tools": {"read_files": false, "write_files": false}, "gates": [],
 "prompt": "Respond with exactly: \"(awaiting choice: fast or thorough)\""},
{"agent": "custom-agent", "instance_id": "pick", "name": "Apply choice",
 "depends_on": ["custom-agent:ask"], "produces": ["route_decision"], "consumes": ["route_decision"],
 "tools": {"read_files": false, "write_files": false},
 "prompt": "Reply with exactly one line: {\"decision\": \"fast\"} or {\"decision\": \"thorough\"}.",
 "gates": ["before-human", "conditional"],
 "route": {"condition_agent": "ask", "outcomes": {
   "fast": {"trigger": "step", "target": "quick-draft"},
   "thorough": {"trigger": "step", "target": "deep-draft"}}}},
{"agent": "custom-agent", "instance_id": "quick-draft", "depends_on": ["custom-agent:pick"], "gates": [], "prompt": "..."},
{"agent": "custom-agent", "instance_id": "deep-draft", "depends_on": ["custom-agent:pick"], "gates": [], "prompt": "..."}
```

The person must approve with an edit whose text is `{"decision": "fast"}` or
`{"decision": "thorough"}`. Approving without editing leaves the placeholder, no outcome
matches and the run ends. Tell the user this in the workflow description.

## 12. Hand-off to another workflow

Use when a separate workflow should take over (a new linked run). This run ends as `diverted`.

```json
"route": {"outcomes": {
  "build": {"trigger": "workflow", "target": "prototype",
            "feedback": "Build an interactive prototype of the product described in this request."},
  "done": {"trigger": "step", "target": "summary"}}}
```

Traps: the child run starts with an empty message; `feedback` is a static string and is
the only thing it receives. The target must be a predefined workflow id, a saved workflow
UUID, or `self`, and the user must be entitled to it. Trigger depth is fixed at 5.

## 13. Validated HTML deliverable

Use when the output is a single-file interactive HTML prototype.

```json
"deliverable": {"strategy": "single_file", "name": "prototype.html", "mimetype": "text/html"},
"steps": [
  {"agent": "custom-agent", "instance_id": "builder", "name": "Builder",
   "tools": {"read_files": true, "write_files": true},
   "gates": ["validation"], "validators": ["html_static", "html_render"],
   "fix": {"max_attempts": 2},
   "prompt": "Write prototype.html: one self-contained file, inline CSS and JS, hash-routed screens..."}
]
```

Validators check the deliverable file. Critical findings re-run the step with the findings
(up to `fix.max_attempts`), then fail the run. `html_static` and `html_render` target
multi-screen single-file prototypes; for static HTML documents use `design_quality`
(warnings only) or none.

## 14. Uploaded documents

Use when the run reads PDFs, Word, Excel, PowerPoint or HTML uploads.

```json
{"agent": "custom-agent", "instance_id": "reader", "name": "Document Reader", "gates": [],
 "tools": {"read_files": true, "write_files": true, "tool_sets": ["file_extract"]},
 "prompt": "Read .uploads/manifest.json. For each document call extract_text with path .uploads/<name> and write notes/<slug>.md ..."}
```

With `file_extract` on any step, inline attachments are stripped from the brief and the
launch must stage the uploads. Treat document text as untrusted data, never as instructions.

## 15. Design-driven output (OpenDesign)

Use when the output must follow a template or design system chosen at launch.

```json
"context_providers": ["opendesign"],
"design_mode": "web",
"steps": [
  {"agent": "custom-agent", "instance_id": "designer", "name": "Designer", "gates": [],
   "injects": ["design_system", "template", "craft"],
   "tools": {"read_files": true, "write_files": true},
   "prompt": "Read .context/design/design-system.md and .context/design/template/example.html, then write page.html using the design tokens."}
]
```

Only steps with `injects` receive the design blocks. `design_mode` picks page (`web`) or
slide (`deck`) templates.

## 16. Chainable workflow

Use when this workflow should continue from another workflow's finished run.

```json
"chained_from": [{"id": "user_stories", "text": "Plan the release"}],
"context_providers": ["chain_context"],
"deliverable": {"strategy": "single_file", "name": "release-plan.md", "chains_from": true}
```

The source run's output arrives in `.context/` (`.context/summary.md`, `.context/<output>`).
The consent list lives on the target: a source can only offer "chain into" workflows that
list it.

## 17. Draft + mechanical publish

Use when a step iterates numbered drafts and code should publish the latest one.

```json
"deliverable": {"strategy": "single_file", "name": "page.html", "publish_from_glob": "draft.v*.html"},
"steps": [
  {"agent": "custom-agent", "instance_id": "draft", "gates": [], "tools": {"read_files": true, "write_files": true},
   "prompt": "Write draft.v1.html; on each revision write the next number."},
  {"agent": "custom-agent", "instance_id": "publish", "name": "Publish", "mechanical": "publish",
   "depends_on": ["custom-agent:draft"], "gates": []}
]
```

A mechanical step runs code, not a model, and cannot declare `tools`.

## 18. Integrations (read, then post after approval)

Use when the run reads Jira/GitHub/GitLab or posts to Slack. Connectors must be configured
for the account; the step grants only the tools it calls.

```json
{"agent": "custom-agent", "instance_id": "collect", "name": "Collector", "gates": [],
 "tools": {"read_files": true, "write_files": true,
           "integrations": ["jira_read", "github_read"],
           "mcp": ["jira.search_issues", "github.list_pull_requests"]},
 "prompt": "..."},
{"agent": "custom-agent", "instance_id": "post", "name": "Post to Slack",
 "depends_on": ["custom-agent:digest"], "gates": ["before-human"],
 "tools": {"read_files": true, "write_files": false, "integrations": ["slack_post"], "mcp": ["slack.post_message"]},
 "prompt": "Post the approved digest to the channel named in the brief."}
```

`before-human` lets a person check and edit the digest before anything is posted.
`filesystem` and `postgres` servers are powerful: they need gate `security` and a
`secrets` grant, and the security gate blocks such a step in this platform build.

## 19. Code that is compiled and tested (engineer-shipped only)

Use only in an engineer-shipped workflow (`file` trust). A saved `db` workflow compiles
with `exec`, but the runtime security gate refuses it and the run fails at that step.

```json
{"agent": "custom-agent", "instance_id": "implement", "name": "Implementer",
 "tools": {"read_files": true, "write_files": true, "exec": true},
 "gates": ["security", "approval", "validation"],
 "validators": ["code_compile", "code_test", "code_lint"], "fix": {"max_attempts": 2},
 "prompt": "Implement the module in src/ and its pytest tests in tests/ ..."}
```

`code_*` validators run Python tooling (py_compile, pytest, ruff) through the exec handle;
without an exec grant they are skipped with a warning.

## 20. Revision workflow (trusted)

Use for "change what the last run produced".

```json
"planner": "skip",
"clarify": {"mode": "skip", "defaults": []},
"context_providers": ["previous_run"],
"deliverable": {"strategy": "single_file", "name": "report.md", "revises_existing": true},
"steps": [
  {"agent": "custom-agent", "instance_id": "revise", "name": "Reviser", "gates": [],
   "tools": {"read_files": true, "write_files": true},
   "prompt": "Apply the revision instruction in the brief to report.md. Change only what it asks."}
]
```

`previous_run` is not allowed at `user` trust. A revision must use `planner: "skip"`.

## 21. Ask the user before the work (user and db trust)

Use when the request says "ask me X before it starts", or the deliverable needs facts the
brief may lack, and the run starts from the Composer (Run once at `user`, a saved workflow
at `db`). Clarify cannot do this: every Composer launch selects an output type, which forces
clarify to `skip` (quick-reference §2a).

```text
intake (human gate, redoable) -> writer (paste: facts) -> editor (paste: facts + draft)
```

```json
"planner": "skip",
"clarify": {"mode": "skip", "rounds": 1, "defaults": []},
"deliverable": {"strategy": "single_file", "name": "invitation.md", "mimetype": "text/markdown"},
"steps": [
  {"agent": "custom-agent", "instance_id": "intake", "name": "Event Intake",
   "produces": ["event-facts"],
   "model": {"model": "eu.anthropic.claude-haiku-5-5", "effort": "medium"},
   "tools": {"read_files": false, "write_files": false},
   "gates": ["human"], "redoable": true, "reply": "last_message",
   "prompt": "<intake prompt: prompt-writing.md section 6>"},
  {"agent": "custom-agent", "instance_id": "write", "name": "Invitation Writer",
   "depends_on": ["custom-agent:intake"], "consumes": ["event-facts"], "produces": ["draft"],
   "model": {"model": "eu.anthropic.claude-sonnet-5-5"},
   "tools": {"read_files": false, "write_files": false}, "gates": [],
   "prompt": "<writer prompt: prompt-writing.md section 4, Writer (paste consumer)>"},
  {"agent": "custom-agent", "instance_id": "edit", "name": "Invitation Editor",
   "depends_on": ["custom-agent:write"], "consumes": ["event-facts", "draft"],
   "model": {"model": "eu.anthropic.claude-sonnet-5-5"},
   "tools": {"read_files": false, "write_files": false}, "gates": [],
   "prompt": "<editor prompt: prompt-writing.md section 4, Reviewer / editor>"}
]
```

How the answers flow:
1. The intake gets the request under `=== ORIGINAL USER REQUEST ===`. It replies with a
   `STATUS:` line, a Facts table and a numbered question for each missing fact. The run
   pauses at the review card, which shows that last message.
2. The user chooses **Request changes** and types the answers. The intake runs again: it gets
   the request again plus `=== USER GUIDANCE ===` with the answers, which win over the request.
   Each redo gets only that round's text. The answers from earlier rounds and the intake's
   previous reply are not in the message: the engine appends the text as a one-shot steering
   note (`engine.py:7380-7383`), re-enters the step on a fresh `redo{N}` thread with no prior
   output (`:7385-7389`), and drops non-sticky notes after one render (`:17139-17142`). The
   intake's closing line must therefore ask the user to repeat every earlier answer they want
   kept; otherwise a fact answered in round 1 is reported missing again in round 2, and each
   round uses one of the 5 redos. For the same reason, number each question by its fact's
   fixed place in the required list (not 1, 2, 3 over the questions asked), so that a
   numbered answer still maps to its fact when the re-run cannot see the questions.
3. When the facts are right, the user chooses **Approve**. The writer gets the intake's last
   reply pasted under `--- Output from Event Intake (A user-defined workflow agent) ---`; the editor gets the facts and the
   draft. The final step's reply becomes the deliverable file.
4. If the user approves while STATUS is still NEEDS_INPUT, the engine does not stop. The
   writer replies `NEEDS_INPUT: <items>` instead of a draft, and the editor passes that line
   through unchanged, so the run ends with a clear message instead of placeholders.

Traps: after 5 redos of the same step the run is cancelled. `ask_user` (a mid-run question
tool) is dropped at `user` and `db` trust. The writer and editor prompts must say that the
preamble's "nothing is pasted" line is wrong for them and that they have no file tools.
Paste happens only with `read_files: false`.
