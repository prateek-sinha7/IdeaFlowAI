# Field guide

Decision rules for every manifest field: when to set it, what value to choose, and the
trap to avoid. The schema (`../schema/workflow-manifest.schema.json`) is the authoritative
shape and describes each field; this guide adds the judgement. Names in `code` must come
from `catalog.md`.

Field order used in generated manifests (readability only; JSON order has no meaning):
`id, version, name, display_name, short_name, description, icon, user_launchable, is_beta,
launch_surface, design_mode, chained_from, planner, clarify, deliverable, context_providers,
input_providers, seed_files, allowed_workers, limits, capabilities, model, chat, steps`.
Within a step: `agent, instance_id, name, strategy, mechanical, condition, depends_on,
consumes, produces, model, tools, skills, injects, task_source, fanout, subagents, gates,
validators, fix, route, retry, reply, redoable, hooks, compaction, post_step, on_conflict,
outputs, replaces, produces_solution_plan, require_render, prompt`.

## Top level

| Field | Set when | Choose | Trap |
|---|---|---|---|
| `id` | always (required) | lower snake_case, unique, describes the job: `contract_review` | It is the run label, entitlement key and route target; do not reuse a predefined id. |
| `version` | always | `1`; bump on breaking edits | Integer only. |
| `name`, `short_name` | always | 1–3 words | Shown on chips; keep short. |
| `display_name` | always | action phrase: "Review contracts for risk" | Shown on the launch card. |
| `description` | always | one sentence, what goes in and what comes out | Without it the API invents "N-step workflow: A -> B". |
| `icon` | always | one the catalog renders: `FileText`, `Search`, `Layout`, `GitBranch`, `GitPullRequest`, `Network`, `Waves`, `Rocket`, `Puzzle`, `Presentation`, `MessageSquare` | Other Lucide names fall back to the default icon. |
| `user_launchable` | always | `true` for a catalog workflow; `false` for internal/child/revision workflows | Visibility only; never authorizes a run. |
| `is_beta` | always | `false` unless it should appear greyed out as Coming Soon | A beta card cannot be launched from the catalog. |
| `launch_surface` | template-driven launch | `"wizard"` only with `opendesign` | Presentation only. |
| `design_mode` | with `opendesign` | `"web"` (pages) or `"deck"` (slides) | Ignored without the provider. |
| `chained_from` | other workflows may continue into this one | `[{"id": "<source>", "text": "<chip label>"}]` | Goes on the TARGET. Pair with `chain_context` and `deliverable.chains_from: true`. |
| `planner` | always (required) | `"skip"` for clear or structured briefs, all revisions and every Composer workflow; `"run"` for vague briefs where intent/constraints must be inferred, and for clarify on launches that send no output type (API, wizard) | `run` adds a model call. `skip` also skips the clarifier, whatever `clarify` says. `run` asks nothing on a Composer launch. |
| `clarify` | always (required) | `{"mode": "skip", "defaults": []}` by default, and for every Composer workflow (use an intake step with a `human` gate to ask, `quick-reference.md` §2a); `{"mode": "auto", "rounds": 1-2, "defaults": [topics]}` with `planner: "run"` only for API or wizard launches | `auto` does nothing with `planner: "skip"`, and a Composer launch (it always selects an output type) forces `skip`. Questions come from the planner's missing information; `defaults` are used only when it reports none; unanswered questions get the recommended answer. The answers land in `PLANNER.md` (Explicit Constraints), never in a step's message: the first step needs `read_files: true` and a prompt that reads `PLANNER.md`. Topics are free ids (`target_audience`, `scope`, `tone_and_style`, `output_format`, `constraints`, `review_focus`); ~5 questions per round. |
| `deliverable` | always (required) | see Deliverable below | Must match what the final step actually produces. |
| `context_providers` | the run needs prepared context | `opendesign` (template/design system), `chain_context` (a chained source run), trusted only: `uploaded_files`, `previous_run`, `conversation`, `repo` | Uploads do not need `uploaded_files`; reading `.uploads/` with `file_extract` works at every trust. |
| `input_providers` | images or PDF page images must reach the model | `run_images` (user images), `pdf_pages` (page images from `.extract/`) | Only for vision work. |
| `seed_files` | rare (revision/task-loop reference files) | `{}` | No reserved paths (`.uploads`, `.context`, `skills`, ...). |
| `allowed_workers` | explicit `fanout.workers` (heterogeneous fan-out) | the worker agent ids | Parallel `subagents` children are added automatically. |
| `limits` | fan-out, long runs, cost caps | `max_subagents`, `max_depth`, `wall_clock_seconds`, `max_tokens` | `user` trust may only lower: 8 / 2 / 900. Trusted up to 200 / 2 / 10800 (largest built-in). |
| `capabilities` | never true today | `{"internet": false}` or omit | The internet tools are stubs. |
| `model` | most steps share a model | `{"model": "eu.anthropic.claude-sonnet-5-5"}` | Step `model` overrides it. |
| `chat` | the run concierge needs hints | `{"suggestions": ["..."]}` | Rare. |
| `steps` | always (required) | see Steps | At least one for Composer manifests. |

### Deliverable

| Strategy | Produces | Final step | Notes |
|---|---|---|---|
| `streamed_text` | the final step's reply | `write_files: false`, reply is the full answer | Set `name` (e.g. `answer.md`) and `mimetype` `text/markdown` so it can be saved and chained. |
| `single_file` | one named file | the leaf step is told to write `name`; if it does not, its reply is written there | Best default for documents and HTML. `text_name` + binary `name` for PDFs built by code. |
| `serialized_sandbox` | every file the run wrote, bundled | writers create the files | For code bases and multi-file output. `name` labels the bundle. |
| `ppt` | an HTML deck from the last reply | trusted only | Prefer the built-in deck workflows. |
| `repo_diff` | a diff against a bound repository | trusted only, `repo` provider | Brownfield engineering only. |

Other deliverable keys: `name` (plain file name, not `logs.jsonl`/`summary.md`),
`mimetype`, `chains_from` (needs `name`), `chain_policy` (`refuse`, the only value),
`revises_existing` (revision workflows, with `planner: skip`), `revision_context`
(`artifact` pastes the parent's deliverable; `workspace` points at the shared workspace and
enables declared human gates during a revision), `publish_from_glob` (one `*`, with a
`mechanical: publish` step).

## Steps

| Field | Set when | Choose | Trap |
|---|---|---|---|
| `agent` | always | `custom-agent` for bespoke steps; a catalog id only when its contract fits | A catalog agent may appear once per workflow. |
| `instance_id` | every `custom-agent` step | kebab-case, unique across the whole tree: `market-size` | Never rename it after saving; artifacts and routes key on it. |
| `name` | every step | readable label: "Market Size" | Free to rename. |
| `prompt` | every `custom-agent` step | full instructions (`prompt-writing.md`) | Rejected on catalog agents. |
| `strategy` | non-default execution | `single_shot` (default), `fanout_batch`, `wave_scheduler`, `task_loop` | `parallel_group` is set by the compiler for `subagents.mode: parallel`; do not write it by hand. |
| `mechanical` | a code-only step | `publish` (with `publish_from_glob`) | The other kinds only work inside their built-in workflows. No `tools` on a mechanical step. |
| `condition` | the step runs only for some launch sources | `"source_type in ['html', 'figma']"` | Evaluated against the launch source type only (catalog, html, figma). |
| `depends_on` | every step after the first in a non-trivial graph; branch steps; converging steps | compiled ids `custom-agent:<id>` | Bare ids are ignored. No cycles (use routes for loops). |
| `consumes` / `produces` | paste hand-offs; `route_decision` sources | free labels that match between producer and consumer | Paste only happens when `read_files` is false. Any `consumes` means: pin order with `depends_on`. |
| `model` | the step differs from the workflow model | `{"model": "<id>", "effort": "<level>", "fallback": [ids]}` | Set `model` with `effort`. `max_tokens` is not applied. |
| `tools` | always declare it explicitly | least privilege, see Tools below | Omitted = read only. |
| `skills` | a step needs specialist instructions | 1–2 ids from the skills catalog | Needs `read_files: true`. Unknown ids are dropped. |
| `injects` | with `opendesign` | `design_system`, `template`, `template_example`, `craft` | No effect without the provider. |
| `task_source` | `fanout_batch`, `wave_scheduler`, `task_loop`, `subagents.mode: fanout` | `{"kind": "parsed", "parser": "json_tasks", "target": "build/tasks.json", "source_step": "custom-agent:<planner>"}` | `source_step` must be earlier; `custom_path` needs `path`. |
| `fanout` | `fanout_batch`, `wave_scheduler` | `{"mode": "parallel", "max_parallel": 3-5, "agent": "self"}`; `count` caps the width | `max_parallel` is clamped to 5. Named `workers` must be in `allowed_workers`. |
| `subagents` | a fixed group of children | `mode` `parallel` / `sequential` / `fanout`, `max_parallel`, `steps` | Two levels deep at most. Children run before the parent. |
| `gates` | review, validation, routing, exec | see `design-playbook.md` §5 | One human-family gate per step. Always present as a list, even `[]`. |
| `validators` | deterministic checks exist | `html_static`, `html_render`, `design_quality`, `code_compile`, `code_test`, `code_lint`, coverage checks | Needs `gates: ["validation"]`; checks the deliverable file. |
| `fix` | with validators | `{"max_attempts": 2}` | Without it the first critical finding fails the run; after the last attempt it fails too. `mode` is not read by the engine: leave it out. |
| `route` | with `gates: ["conditional"]` | `outcomes`, `default_next`, `loop_max_iterations` (2–3 for loops), `on_loop_exhausted`, `condition_agent` | Decision source must produce `route_decision`. `trigger_max_depth` is fixed at 5; omit it. An outcome's `trigger` is `step`, `workflow` or `end` (`end` takes no target and finishes the run: use it for the decision that leaves a loop). A decision that matches no outcome and has no `default_next` fails the run. |
| `retry` | long or critical steps exposed to throttling | `{"max_attempts": 2, "backoff_seconds": 5}` | Only `transient` errors retry; it does not fix bad output. |
| `reply` | tool-using steps whose reply matters (decision, human review, streamed answer) | `"last_message"` | Default `all` includes tool-call chatter. |
| `redoable` | with a `human` gate | `true` | No effect without `human`. Request changes re-runs the step with the reviewer's text as `=== USER GUIDANCE ===` (the first step also gets the request again); this is how an intake step receives answers. Each redo gets only that round's text, not earlier rounds or the step's previous reply (the engine's one-shot steering note), so the intake asks the user to repeat earlier answers they want kept. 5 redos of one step cancel the run. |
| `hooks` | omit in almost all cases | omitted = `audit_logger` + `secret_scan` | An explicit list replaces the defaults; `[]` disables auditing. Add `otel_tracing` only when traces are required: `["audit_logger", "secret_scan", "otel_tracing"]`. |
| `compaction` | trusted, very large HTML context | `html_skeleton`, `chat_history` | Not allowed at `user` trust. |
| `post_step` | trusted | `revision_validation` (revision runs), `api_prefix_audit` (generated APIs) | Not allowed at `user` trust. |
| `on_conflict` | fan-out workers might write the same file | `human_gate` (default), `partial`, `abort`, `merge_agent` (+ `fanout.merge_agent`) | Prefer disjoint `targets` so conflicts cannot happen. |
| `outputs` + `replaces` | a re-run must remove stale files it owns | `outputs: ["screens/"]`, `replaces: true` | Rare. |
| `produces_solution_plan` | revision analyzers | `true` | Extracts a `## Solution Plan` section for later revision steps. |
| `require_render` | with `html_render` | `true` to fail when no browser is available | Leave unset unless the platform has the browser. |

### Tools

| Grant | Default | Grant when | Trust |
|---|---|---|---|
| `read_files` | `true` | the step reads earlier files, uploads, context or skills | all |
| `write_files` | `false` | the step creates or edits files (work files, the deliverable, fan-out targets) | all |
| `exec` | `false` | the step must run commands (compile/test/lint) | runs only at `file` trust (the security gate refuses it at `db`); needs gates `security` + `approval` |
| `git` | `false` | never needed (no agent git tool) | trusted only |
| `network` | `false` | never (nothing binds it; the security gate blocks it) | rejected at `user` trust |
| `secrets` | `[]` | never today (the security gate blocks it) | rejected at `user` trust |
| `spawn_subagents` | `false` | the MODEL must request extra fan-out at run time | rejected at `user` trust; declarative fan-out never needs it |
| `mcp` | `[]` | the step calls external tools: `server.tool` | read-scoped GitHub/GitLab/Jira and Slack posting at every trust; `filesystem`/`postgres` need `security` + `secrets`, which the security gate blocks |
| `connectors` | `[]` | the step calls a GitHub or Jira connector tool, named `<connector>__<tool>` (`jira__search_issues`) | `user` and `db` only; the account must have connected the app |
| `integrations` | `[]` | the step posts to Slack or uses another integration scope | all; the scope's MCP server must be listed in `tools.mcp` |
| `tool_sets` | `[]` | `file_extract` (documents), `playwright` (headless browser on run files) | at `user` trust every other set is silently dropped; trusted: `ask_user`, `pptx`, `workspace`, `prototype`, `prototype_emit_only`, `planning`, `spawn_subagents`, `internet` (stub) |

Grant `write_files: true` only to steps that must create files. A step that only reads
and replies keeps `{"read_files": true, "write_files": false}`. A step that needs no
context keeps `{"read_files": false, "write_files": false}`.
