# Velocity catalog snapshot

Generated 2026-11-10T13:09:57Z from a Velocity `backend` checkout on `feature/ai-workflow` @ `56eefe4e5`. Regenerate with `scripts/refresh_catalog.py` whenever the target platform changes; `references/catalog.json` holds the same data for `validate_manifest.py`.

Counts: 96 agents, 92 capability coordinates, 13 models, 190 step skills, 39 predefined workflows.

## Trust caps (what a step's `tools` grant can resolve to)

| Cap | read | write | exec | git | network | spawn_subagents | tool_sets kept |
|---|---|---|---|---|---|---|---|
| trusted | True | True | True | True | False | True | workspace, prototype, prototype_emit_only, planning, internet, pptx, playwright, file_extract, spawn_subagents, ask_user |
| untrusted | True | True | False | False | False | False | file_extract, playwright |
| saved | True | True | False | False | False | True | file_extract, playwright, prototype_emit_only, ask_user |

Trust level to cap: `file` -> trusted, `builtin` -> trusted, `db` -> trusted, `user` -> untrusted.

Runtime security gate: `exec` passes only at `builtin`, `file` trust (with the `approval` gate); `network` and `secrets` are blocked on any step that declares the `security` gate.

## Budget limits

- Runtime defaults: `max_subagents` 8, `max_concurrency` 5, `max_depth` 2, `wall_clock_seconds` 900
- `user` trust may only lower: `max_subagents` 8, `max_depth` 2, `wall_clock_seconds` 900
- Largest values any built-in uses: `max_subagents` 200, `max_depth` 2, `wall_clock_seconds` 10800
- Subagent nesting blocks allowed: 2

## Capabilities a manifest can name

`user` = allowed in a `user`-trust manifest (inline Run once, override rows).
Everything listed is allowed for `file`, `builtin` and `db` trust.

### `strategy` (5)

| Name | user | What it does | Reads | Writes |
|---|---|---|---|---|
| `fanout_batch` | yes | Fan a task list out to parallel worker sub-agents in one batch, then merge their results. | - | - |
| `parallel_group` | yes | Run a step's declared sibling sub-agents concurrently, then run the step's own agent over their results. | - | - |
| `single_shot` | yes | Run the step's agent exactly once and emit its output (the default strategy). | - | - |
| `task_loop` | yes | Parse the step's deliverable into tasks and run one isolated sub-agent per task, with an optional bounded validation fix-loop. | - | - |
| `wave_scheduler` | yes | Schedule a structured task list into dependency-ordered waves, fanning each wave out concurrently. | - | - |

### `deliverable` (5)

| Name | user | What it does | Reads | Writes |
|---|---|---|---|---|
| `ppt` | no | Resolve the deliverable as an HTML slide-deck (PPT) read back from the run sandbox. | - | - |
| `repo_diff` | no | Resolve the deliverable as a brownfield diff-only patch against the source repo. | - | - |
| `serialized_sandbox` | yes | Resolve the deliverable as the whole run sandbox serialized into filename-block output (code-gen bundle). | - | - |
| `single_file` | yes | Resolve the deliverable as a single named file read back from the run sandbox. | - | - |
| `streamed_text` | yes | Resolve the deliverable as the agent's streamed text output (no sandbox file read). | - | - |

### `gate` (6)

| Name | user | What it does | Reads | Writes |
|---|---|---|---|---|
| `approval` | no | Require an explicit privileged approval before the step proceeds. | - | - |
| `before-human` | yes | Pause BEFORE this step runs and review the previous step's output (HITL). | - | - |
| `conditional` | yes | Branch the run to a declared step or trigger another workflow based on a step's typed decision. | - | - |
| `human` | yes | Pause AFTER this step and review its own output (HITL); supports redo. | - | - |
| `security` | no | Enforce the security posture before a privileged step (exec/network/secrets/spawn default OFF). | - | - |
| `validation` | yes | Block the run on critical validator findings; surface non-critical issues as warnings. | - | - |

### `validator` (14)

| Name | user | What it does | Reads | Writes |
|---|---|---|---|---|
| `api_prefix` | yes | Audit generated infra/app files for endpoints not under the canonical /api/v1 prefix. | - | - |
| `backlog_plan_coverage` | yes | Check that the backlog plan places every coverage item in an epic (or unassigned) and in a slice task. | - | - |
| `code_compile` | yes | Compile the generated Python via py_compile through the exec handle and surface syntax errors as issues. | - | - |
| `code_lint` | yes | Run ruff lint over the generated code via the exec handle and surface findings as issues. | - | - |
| `code_test` | yes | Run pytest over the generated code via the exec handle and surface failures as issues. | - | - |
| `design_quality` | yes | Assess design-quality heuristics on a prototype and surface findings as warnings-first issues. | - | - |
| `fragment_field_coverage` | yes | For each screens/<id>.html fragment, verify every FIELDS-table label from its journeys.md section appears in the fragment, and flag any <id>_*.html sidecar (a worker writing to the wrong target). | - | - |
| `html_element_floor` | yes | Compare the highest draft.v*.html against the previous version and flag any drop in interactive-element counts or a >60% byte-size collapse. | - | - |
| `html_render` | yes | Render a single-file HTML prototype in headless Chromium and flag nav/console-error failures. | - | - |
| `html_static` | yes | Run stdlib structural checks over a single-file HTML prototype (routes, handlers, is-active). | - | - |
| `journeys_coverage` | yes | Cross-check journeys.md against notes/doc-*.md: flag screens marked MISSING despite being documented, screens referenced but never sectioned, 'Unknown Module' stages, and screens whose field table went empty. | - | - |
| `screens_plan_coverage` | yes | Verify build/screens.json (the Architect's screen plan) covers every screen spec.md declares, naming any missing screen id(s). | - | - |
| `spec_plan_coverage` | yes | Check that every spec requirement is covered by a plan task and flag gaps as issues. | - | - |
| `task_done_when` | yes | Verify each task's declared done-when criteria are satisfied and flag unmet criteria as issues. | - | - |

### `hook` (5)

| Name | user | What it does | Reads | Writes |
|---|---|---|---|---|
| `audit_logger` | yes | Default audit-logging hook: records per-agent lifecycle events for the Audit tab. | - | - |
| `behavioral` | yes | Non-executable behavioral hook: inject user-attached output-format guidance into the prompt. | - | - |
| `otel_tracing` | yes | Non-blocking executable hook: emit OpenTelemetry traces for the run. | - | - |
| `provenance_audit` | no | Post-commit provenance audit observer: writes one run_provenance_audits row per audited commit class (snapshot_commit, recovery_commit, fragment_merge, merge_agent_commit, restore). Observation-only - never blocks the commit or the finalizer. | - | - |
| `secret_scan` | yes | Blocking executable hook: scan agent output for secrets and halt on a hit. | - | - |

### `context_provider` (6)

| Name | user | What it does | Reads | Writes |
|---|---|---|---|---|
| `chain_context` | yes | Byte-copy the chain payload from the source run's exact ref into the receiving sandbox's .context/ directory before step 1. V2 reads three flat files from an immutable Git ref; legacy reads from a validated nested .chain-legacy/ directory. Dormant (returns... | - | - |
| `conversation` | no | Surface the run's compacted chat history as sticky agent/steering context. | - | - |
| `opendesign` | yes | Inject OpenDesign template / design-system / craft context into the agent prompt. | - | - |
| `previous_run` | no | Seed the run with a prior run's outputs (e.g. revision over a parent run). | - | - |
| `repo` | no | Surface a targeted repo context pack (symbols/files) to the agent for brownfield work. | - | - |
| `uploaded_files` | no | Surface the run's uploaded document text as sticky agent context. | - | - |

### `input_provider` (2)

| Name | user | What it does | Reads | Writes |
|---|---|---|---|---|
| `pdf_pages` | yes | Attach materialised PDF page images from .extract/ as multimodal content-blocks to the agent prompt. | - | - |
| `run_images` | yes | Attach the run's user-supplied images (base64) as multimodal content-blocks to the agent prompt. | - | - |

### `task_parser` (3)

| Name | user | What it does | Reads | Writes |
|---|---|---|---|---|
| `heading_tasks` | yes | Splits the plan into tasks by its headings: one '## Task' heading is one task. Tasks run one after another, in the order written. | - | - |
| `json_tasks` | yes | Uses the task list an agent wrote as JSON, including which tasks depend on which. Independent tasks run in parallel waves; dependent ones wait their turn. | - | - |
| `screen_plan` | yes | Reads the screen list an earlier step produced and creates exactly one build task per screen. No AI decides the list, so no screen is skipped or counted twice. Each task already carries that screen's spec and the exact links to write. | - | - |

### `tool` (10)

| Name | user | What it does | Reads | Writes |
|---|---|---|---|---|
| `ask_user` | no | Privileged HITL request emitter; the engine fulfils the pause via ClarifyEngine. | - | - |
| `file_extract` | yes | Extract text from an uploaded file: extract_text / file_info / file_find / file_page_image (spec 019). ONE entry point for every type - a plain-text file (.txt, .md, .csv, .json) comes back as text in the tool result; a .pdf, .docx, .xlsx or .pptx is materi... | - | - |
| `internet` | no | Internet access stub: web_search/web_fetch always return 'internet access is not yet available.' No network egress exists yet (R-25). | - | - |
| `planning` | no | Planning tool set: the deep-planner stub tools only, with no disk access. | - | - |
| `playwright` | yes | Open HTML files in a headless browser, read the page structure, interact with elements by stable reference, capture screenshots, and inspect console output. All paths resolved inside the run sandbox, every screenshot written to the workspace. playwright_nav... | - | - |
| `pptx` | no | Build a real .pptx from PptxGenJS source and gate it on a deterministic geometry audit plus a render: render_pptx / verify_pptx_layout / extract_pptx_shapes / screenshot_pptx (spec 017), plus extract_computed_styles - a headless-render DOM walk that dumps r... | - | - |
| `prototype` | no | Prototype tool set: native filesystem tools plus the report_task_complete progress signal. | - | - |
| `prototype_emit_only` | no | Emit-only prototype tool set: same bindings as prototype (report_task_complete plus native fs). | - | - |
| `spawn_subagents` | no | Privileged fan-out request emitter; the engine fulfils spawns via the single kernel run_fanout path. | - | - |
| `workspace` | no | Code-gen workspace: native filesystem tools writing deliverables to the run sandbox. | - | - |

For tool sets the `user` column follows the `user` trust cap in the Trust caps table at the top, not the registry flag: a set that cap does not keep is silently dropped from the step.

### `mechanical` (4)

| Name | user | What it does | Reads | Writes |
|---|---|---|---|---|
| `assemble_backlog` | yes | Turns the epic/story files the Story Writers wrote into one backlog: backlog.md (the deliverable), backlog.csv (Jira import), backlog.json and a coverage report, plus build-order.md, data-model.md, schema.json, api.md, openapi.json, integrations.md and scre... | build/backlog-plan.json, build/story-tasks.json, stories/, build/solution/, build/review.json, architecture.md, solution.md, ui.md, ux.md | backlog.md, backlog.csv, backlog.json, build/coverage.json, data-model.md, schema.json, api.md, openapi.json, integrations.md, screens.md, build-order.md, gaps.md, Backlog.pdf, Backlog.zip, .gitignore |
| `assemble_prototype` | yes | Stitches the screen pages the builder agents wrote into one clickable prototype. Pure code, no AI: every screen is included, links between screens work, and a coverage report lists anything missing. Needs an earlier step that lists the screens (build/screen... | build/screens.json, parts/, build/theme.json, spec.md, .context/design/template/ | prototype.html, build/validation.json |
| `extract_prototype_ui` | yes | Reads the look and feel of the prototype a workflow is written against - a chained prototype_v2 run's prototype.html, or an uploaded HTML - by rendering it in a headless browser. Pure code, no AI. Writes build/ui/: the effective design tokens (palette by us... | .context/prototype.html, .uploads/ | build/ui/source.json, build/ui/tokens.json, build/ui/components.json, build/ui/navigation.json, build/ui/components/, build/ui/screens/, build/ui/.gitignore, .uploads/prototype.html |
| `publish` | yes | Copies the finished file onto the workflow's deliverable so it shows in Results. Pure code, no AI. Needs the step's publish pattern to match a file the run wrote. Copies the newest file matching the workflow's publish pattern, byte for byte, onto the delive... | <deliverable.publish_from_glob> | <deliverable.name> |

### `compaction` (2)

| Name | user | What it does | Reads | Writes |
|---|---|---|---|---|
| `chat_history` | no | Summarize chat turns beyond budget and keep the most-recent turns verbatim to bound the composed conversation context. | - | - |
| `html_skeleton` | no | Compact prior HTML context down to a structural skeleton to fit the model context window. | - | - |

### `post_step` (2)

| Name | user | What it does | Reads | Writes |
|---|---|---|---|---|
| `api_prefix_audit` | no | After a step, run an event-free infra audit for endpoints not under the /api/v1 prefix. | - | - |
| `revision_validation` | no | After a revision step, run the validation fix-loop over the revised deliverable. | - | - |

### `mcp_server` (6)

| Name | user | What it does | Reads | Writes |
|---|---|---|---|---|
| `filesystem` | no | Powerful filesystem MCP server (read/write disk); behind the security gate + secrets. | - | - |
| `github` | yes | Read-scoped GitHub MCP server (issues / PRs / repo metadata). | - | - |
| `gitlab` | yes | Read-scoped GitLab MCP server (issues / MRs / project metadata). | - | - |
| `jira` | yes | Read-scoped Jira MCP server (issues / projects). | - | - |
| `postgres` | no | Powerful Postgres MCP server (arbitrary SQL); behind the security gate + secrets. | - | - |
| `slack` | yes | Post-scoped Slack MCP server (post_message / list_channels - the one user-grantable write). | - | - |

### `integration_provider` (4)

| Name | user | What it does | Reads | Writes |
|---|---|---|---|---|
| `github` | yes | GitHub integration provider bridging the github catalog MCP server (github_read). | - | - |
| `gitlab` | yes | GitLab integration provider bridging the gitlab catalog MCP server (gitlab_read). | - | - |
| `jira` | yes | Jira integration provider bridging the jira catalog MCP server (jira_read). | - | - |
| `slack` | yes | Slack integration provider bridging the slack catalog MCP server (slack_post). | - | - |

## Registry kinds a manifest cannot name

The engine picks these itself (merge strategy, prompt policy, runtime, repo index and so on). They are listed for reference only: no manifest field accepts them. The `skill` kind below lists skill sources, not step skills; step skills are in the Step skills section.

### `chat` (1)

| Name | user | What it does | Reads | Writes |
|---|---|---|---|---|
| `concierge` | no | Per-run conversational orchestrator: answers run questions from real run data and emits proposal-only intents. | - | - |

### `context_pack` (1)

| Name | user | What it does | Reads | Writes |
|---|---|---|---|---|
| `default` | no | Assemble a kernel-side targeted context subset of the repo for the agent. | - | - |

### `merge` (4)

| Name | user | What it does | Reads | Writes |
|---|---|---|---|---|
| `copy_disjoint` | yes | Merge fan-out worker outputs by copying disjoint file sets (no overlap conflict resolution). | - | - |
| `git_3way` | yes | Merge overlapping fan-out worker outputs via a git three-way merge. | - | - |
| `html_fragment` | yes | Merge fan-out worker outputs by concatenating their HTML fragments into one document. | - | - |
| `json` | yes | Merge fan-out worker outputs by deep-merging their JSON documents. | - | - |

### `model_catalog` (1)

| Name | user | What it does | Reads | Writes |
|---|---|---|---|---|
| `default` | no | - | - | - |

### `prompt` (3)

| Name | user | What it does | Reads | Writes |
|---|---|---|---|---|
| `body_only` | yes | Body-only prompt policy - system prompt is exactly the agent's AGENT.md. Do NOT use for governed agents (use 'governance' to retain the Constitution). | - | - |
| `default` | yes | The default prompt-assembly policy (tool_availability, injects, guardrails, skills, hooks, constitution, body). | - | - |
| `governance` | yes | Governance prompt policy for agents with a Constitution or behavioral hooks (guardrails, hooks, constitution, body). | - | - |

### `repo_index` (1)

| Name | user | What it does | Reads | Writes |
|---|---|---|---|---|
| `tree_sitter` | no | Build an app-side symbol index of the source repo via tree-sitter (isolated). | - | - |

### `repo_inventory` (1)

| Name | user | What it does | Reads | Writes |
|---|---|---|---|---|
| `default` | no | Build a kernel-side stdlib inventory of the source repo (files/structure). | - | - |

### `runtime` (1)

| Name | user | What it does | Reads | Writes |
|---|---|---|---|---|
| `langchain_deepagents` | no | The canonical agent runtime: every agent runs on LangChain deepagents (INV-13). | - | - |

### `runtime_env` (1)

| Name | user | What it does | Reads | Writes |
|---|---|---|---|---|
| `local` | no | Local on-disk sandbox runtime environment (the ECS/container-swap seam). | - | - |

### `skill` (4)

| Name | user | What it does | Reads | Writes |
|---|---|---|---|---|
| `disk` | yes | Disk-backed skill source (inert until a disk source is wired). | - | - |
| `repo` | yes | Repo-backed skill source (inert until a repo source is wired). | - | - |
| `template` | yes | Template-bundled skill source (inert until a template source is wired). | - | - |
| `ui` | yes | Inject UI-attached skill documents (per-request capability docs) into the agent prompt. | - | - |

## Icons (`icon`)

The catalog card renders these Lucide names (frontend/src/lib/workflowIcons.ts); any other name shows the default icon: `FileText`, `Presentation`, `Layout`, `Rocket`, `Puzzle`, `GitBranch`, `MessageSquare`, `Search`, `GitPullRequest`, `Network`, `Waves`.

## Models

| Model id | Label | Cost class | Tier | Context | Reasoning | Effort levels | Default effort | Vision | Picker |
|---|---|---|---|---|---|---|---|---|---|
| `eu.anthropic.claude-haiku-5-5` | Claude Haiku 5.5 | cheap | fast | 1000000 | adaptive | none, low, medium, high, xhigh, max | xhigh | yes | yes |
| `eu.anthropic.claude-haiku-4-5-20251001-v1:0` | Claude Haiku 4.5 | cheap | fast | 200000 | budget | none, on | on | yes | yes |
| `us.anthropic.claude-haiku-4-5-20251001-v1:0` | Claude Haiku 4.5 | cheap | fast | 200000 | budget | none, on | on | yes | no (raw id only) |
| `global.openai.gpt-5.6-luna` | GPT-5.6 Luna | cheap | fast | 1000000 | effort | none, low, medium, high, xhigh, max | medium | yes | yes |
| `global.openai.gpt-5.6-sol` | GPT-5.6 Sol | premium | powerful | 1000000 | effort | none, low, medium, high, xhigh, max | medium | yes | yes |
| `eu.anthropic.claude-sonnet-4-5-20250929-v1:0` | Claude Sonnet 4.5 | standard | balanced | 200000 | budget | none, on | on | yes | yes |
| `eu.anthropic.claude-sonnet-4-6` | Claude Sonnet 4.6 | standard | balanced | 1000000 | budget | none, on | on | yes | yes |
| `us.anthropic.claude-sonnet-5` | Claude Sonnet 5 | standard | balanced | 1000000 | adaptive | none, on | on | yes | no (raw id only) |
| `eu.anthropic.claude-sonnet-5` | Claude Sonnet 5 | standard | balanced | 1000000 | adaptive | none, on | on | yes | yes |
| `eu.anthropic.claude-sonnet-5-5` | Claude Sonnet 5.5 | standard | balanced | 1000000 | adaptive | none, low, medium, high, xhigh, max | high | yes | yes |
| `eu.anthropic.claude-sonnet-4-20250514-v1:0` | Claude Sonnet 4 | standard | balanced | 200000 | budget | none, on | on | yes | yes |
| `eu.anthropic.claude-opus-4-5-20251101-v1:0` | Claude Opus 4.5 | premium | powerful | 200000 | budget | none, on | on | yes | yes |
| `eu.anthropic.claude-opus-4-6-v1` | Claude Opus 4.6 | premium | powerful | 200000 | budget | none, on | on | yes | yes |

## MCP servers (`tools.mcp: ["server.tool"]`)

| Server | user | Powerful | Exposed tools | Own scope |
|---|---|---|---|---|
| `filesystem` | no | yes | list_directory, read_file, write_file | filesystem |
| `github` | yes | no | get_issue, get_repository, list_issues, list_pull_requests | github_read |
| `gitlab` | yes | no | get_issue, get_project, list_issues, list_merge_requests | gitlab_read |
| `jira` | yes | no | get_issue, list_projects, search_issues | jira_read |
| `postgres` | no | yes | execute, query | postgres |
| `slack` | yes | no | list_channels, post_message | slack_post |

## Connectors (`tools.connectors: ["<connector>__<tool>"]`)

| Connector | Mode | Tools (`<connector>__<tool>`) |
|---|---|---|
| `github` (GitHub) | remote_mcp | found at run time (remote MCP) |
| `jira` (Jira) | native_api | `jira__add_comment`, `jira__assign_issue`, `jira__create_issue`, `jira__get_comments`, `jira__get_issue`, `jira__list_projects`, `jira__list_transitions`, `jira__search_issues`, `jira__transition_issue`, `jira__update_issue` |

## Integration scopes (`tools.integrations: ["scope"]`)

Each scope turns on the tools of one MCP server for the run. List the matching `server.tool` names in `tools.mcp`.

| Scope | Provider | MCP server | user |
|---|---|---|---|
| `github_read` | `github` | `github` | yes |
| `gitlab_read` | `gitlab` | `gitlab` | yes |
| `jira_read` | `jira` | `jira` | yes |
| `slack_post` | `slack` | `slack` | yes |

## Agents (`step.agent`)

`custom-agent` is the blank template: give each use an `instance_id` and a `prompt`. Every other id is an AGENT.md agent with a fixed prompt and contract; `used in` lists the predefined workflows that already run it.

### pipeline_type `custom`

| Agent | Role / description | Produces | Consumes | Tools | Model | Used in |
|---|---|---|---|---|---|---|
| `custom-agent` | TEMPLATE. A user-defined workflow agent | - | - | - | - | backlog, backlog_revision, ex_A1_loop, ex_A2_branch, ex_A3_b_spanish, ex_A3_c_dutch, ex_A3_divert, ex_A4_human_divert, ex_A4_human_gate, ex_publish_step, ex_test_loop_reachable_skip, ex_test_transitive_skip, ex_validation_retry, prototype_v2, prototype_v2_feature_revision, prototype_v2_revision, sample_subagents_parallel |
| `documentation-agent` | Writes clear documentation including README, API guides, and setup instructions. | documentation-agent | - | - | - | custom |
| `market-research-agent` | Analyzes your market, competitors, and industry trends to size the opportunity. | market-research-agent | - | - | - | custom |
| `performance-optimizer` | Identifies performance bottlenecks and recommends optimizations for speed. | performance-optimizer | - | - | - | custom |
| `report-generator` | Creates executive-ready reports with key metrics, insights, and recommendations. | report-generator | - | - | - | custom |
| `roadmap-planner` | Builds a phased product roadmap with milestones, priorities, and timelines. | roadmap-planner | - | - | - | custom |
| `security-auditor` | Reviews your product for security risks and provides a prioritized action plan. | security-auditor | - | - | - | custom |
| `swot-analyst` | Identifies your strengths, weaknesses, opportunities, and threats with clear actions. | swot-analyst | - | - | - | custom |
| `task-list-planner` | Fan-out Task Decomposition | task-list-planner | - | - | - | custom |
| `test-case-generator` | Creates comprehensive test scenarios covering happy paths, edge cases, and errors. | test-case-generator | - | - | - | custom |

### pipeline_type `app_builder`

| Agent | Role / description | Produces | Consumes | Tools | Model | Used in |
|---|---|---|---|---|---|---|
| `app-api-design` | Endpoint contracts, error envelopes, idempotency rules, async event contracts, versioning policy, and the OpenAPI 3.1 document. | app-api-design | material-analyzer, app-user-stories, app-system-design | - | - | app_builder |
| `app-code-compliance` | SAST/SCA tooling, SonarQube quality gates, language-specific lint config, license policy, and pre-commit/CI gates. | app-code-compliance | material-analyzer, app-code-generator, app-feature-implementation | - | - | app_builder |
| `app-code-generator` | Generates complete frontend and backend code for your application - controllers, services, models, pages, components. | app-code-generator | material-analyzer, app-system-design, app-api-design, app-database-design | workspace | - | app_builder |
| `app-database-design` | Entity model, DDL, indexing strategy, migration tooling, PII classification, backup/recovery targets, and query budgets. | app-database-design | material-analyzer, app-system-design, app-api-design | - | - | app_builder |
| `app-devops` | Branching model, CI/CD pipeline-as-code, environment promotion, OIDC secrets, DORA-metric observability, and developer-experience tooling. | app-devops | material-analyzer, app-infra-generator, app-code-generator | workspace | - | app_builder |
| `app-feature-implementation` | Fleshes out the user stories' business logic in the generated codebase - route handlers, services, integrations, and feature flags. | app-feature-implementation | app-user-stories, app-code-generator | workspace | - | app_builder |
| `app-infra-generator` | Sets up deployment configuration, tests, and infrastructure for your app. | app-infra-generator | material-analyzer, app-code-generator | workspace | - | app_builder |
| `app-sdlc-governance` | Architecture Decision Records, runbooks, SLOs/SLIs, dashboards, compliance evidence matrix, and operations handover. | app-sdlc-governance | material-analyzer, app-system-design, app-security-architecture, app-code-compliance, app-devops, app-test-compliance | - | - | app_builder |
| `app-security-architecture` | STRIDE threat model, identity/IAM design, encryption, secrets, WAF, and security gates for the application. | app-security-architecture | material-analyzer, app-system-design | - | - | app_builder |
| `app-system-design` | Detailed component decomposition, sync/async boundaries, state ownership, deployment topology, and ADRs. | app-system-design | material-analyzer, app-user-stories | - | - | app_builder |
| `app-test-compliance` | Test pyramid, coverage gates, compliance test mapping (PCI/GDPR/SOC 2), performance and chaos plans. | app-test-compliance | app-test-implementation, app-code-compliance, app-security-architecture | - | - | app_builder |
| `app-test-implementation` | Writes the test code (JUnit/xUnit/Jest/Pact/Playwright) that proves the user stories' acceptance criteria. | app-test-implementation | app-user-stories, app-code-generator, app-feature-implementation | workspace | - | app_builder |
| `app-user-stories` | Translates the architecture into epics, user stories, and Gherkin acceptance criteria the team can pick up as deliverable work. | app-user-stories | material-analyzer | - | - | app_builder |
| `app-ux-design` | Information architecture, wireframes, design tokens, component library, accessibility plan, and error/loading states. | app-ux-design | material-analyzer, app-user-stories, app-system-design | - | - | app_builder |
| `material-analyzer` | Analyzes your requirements and designs the complete application architecture. | material-analyzer | - | - | - | app_builder |

### pipeline_type `app_builder_revision`

| Agent | Role / description | Produces | Consumes | Tools | Model | Used in |
|---|---|---|---|---|---|---|
| `app-builder-revision-agent` | Makes precise, targeted edits to an existing app blueprint and codebase based on your revision request, without rewriting what already works. | app-builder-revision-agent | - | workspace | - | app_builder_revision |

### pipeline_type `chat`

| Agent | Role / description | Produces | Consumes | Tools | Model | Used in |
|---|---|---|---|---|---|---|
| `chat-discovery` | Runs a focused discovery conversation to understand your needs and determine which deliverables to generate. | - | - | - | - | chat |
| `chat-ppt` | Plans a compelling slide-by-slide presentation strategy from your topic, ready for the deck to be built. | - | - | - | - | chat |
| `chat-preview` | Assembles every phase's output into the final, structured deliverable. | - | - | - | - | chat |
| `chat-prototype` | Generates a comprehensive UI prototype definition - pages, components, and navigation - from the gathered requirements. | - | - | - | - | chat |
| `chat-requirements` | Produces a structured requirements document covering scope, functional and non-functional requirements from the discovery context. | - | - | - | - | chat |
| `chat-ui-design` | Generates design system specifications - tokens, typography, and component styles - from the requirements and prototype definition. | - | - | - | - | chat |
| `chat-user-stories` | Generates a professional, Jira-style product backlog of epics and user stories from the requirements and discovery context. | - | - | - | - | chat |

### pipeline_type `custom_revision`

| Agent | Role / description | Produces | Consumes | Tools | Model | Used in |
|---|---|---|---|---|---|---|
| `custom-revision-builder` | Executes the revision planner's revisions/<run_id>/plan.md, reconstructing the original file set on disk with only the scoped changes applied. | custom-revision-builder | custom-revision-planner | workspace | - | custom_revision |
| `custom-revision-planner` | Reads the prior composed-workflow run's output from context (not the sandbox) and writes a scoped, file-by-file revision plan for the builder to execute. | custom-revision-planner | - | workspace | - | custom_revision |

### pipeline_type `dotnet_to_azure`

| Agent | Role / description | Produces | Consumes | Tools | Model | Used in |
|---|---|---|---|---|---|---|
| `dotnet-azure-ai` | Identifies where Azure OpenAI / Document Intelligence / AI Search add measurable value and produces the C# integration code. | dotnet-azure-ai | dotnet-modernization, dotnet-feature-coding | - | - | dotnet_to_azure |
| `dotnet-azure-bicep` | Generates Bicep modules for App Service, Functions, Azure SQL, Service Bus, networking, and observability. | dotnet-azure-bicep | dotnet-azure-target-mapping, dotnet-security-architecture | workspace | - | dotnet_to_azure |
| `dotnet-azure-target-mapping` | Maps each .NET project to the right Azure service (App Service, AKS, Functions, SQL) with effort estimates. | dotnet-azure-target-mapping | dotnet-inventory, dotnet-user-stories | - | - | dotnet_to_azure |
| `dotnet-code-compliance` | SAST/SCA tooling, SonarQube quality gates, Roslyn analyzers, .editorconfig, license policy, and pre-commit/CI gates. | dotnet-code-compliance | dotnet-modernization, dotnet-feature-coding | - | - | dotnet_to_azure |
| `dotnet-feature-coding` | Implements the user stories' business logic in the modernised .NET 8 services - controllers, services, persistence, integrations. | dotnet-feature-coding | dotnet-user-stories, dotnet-modernization | workspace | - | dotnet_to_azure |
| `dotnet-inventory` | Catalogues your .NET estate - projects, frameworks, NuGet deps, auth model, and modernisation risk hotspots. | dotnet-inventory | - | - | - | dotnet_to_azure |
| `dotnet-modernization` | Translates legacy .NET Framework projects to .NET 8 with breaking-change fixes and async-by-default. | dotnet-modernization | dotnet-inventory, dotnet-azure-target-mapping | workspace | - | dotnet_to_azure |
| `dotnet-sdlc-governance` | Architecture Decision Records, runbooks, SLOs/SLIs, dashboards, compliance evidence matrix, and operations handover. | dotnet-sdlc-governance | dotnet-security-architecture, dotnet-azure-bicep, dotnet-code-compliance, dotnet-test-compliance, dotnet-validation | - | - | dotnet_to_azure |
| `dotnet-security-architecture` | STRIDE threat model, Entra ID/Key Vault design, encryption, WAF, and security gates for the target Azure architecture. | dotnet-security-architecture | dotnet-inventory, dotnet-azure-target-mapping | - | - | dotnet_to_azure |
| `dotnet-test-compliance` | Test pyramid, coverage gates, compliance test mapping (PCI/GDPR/SOC 2), perf & chaos plans. | dotnet-test-compliance | dotnet-security-architecture, dotnet-test-implementation | - | - | dotnet_to_azure |
| `dotnet-test-implementation` | Writes the xUnit + FluentAssertions + Testcontainers + Pact test code that proves the acceptance criteria. | dotnet-test-implementation | dotnet-user-stories, dotnet-feature-coding | workspace | - | dotnet_to_azure |
| `dotnet-user-stories` | Turns the inventory into epics, user stories, and Gherkin acceptance criteria for the migrated capabilities. | dotnet-user-stories | dotnet-inventory | - | - | dotnet_to_azure |
| `dotnet-validation` | Designs parity tests, shadow-traffic config, Application Insights KQL gates, and the rollback drill. | dotnet-validation | dotnet-azure-target-mapping, dotnet-test-compliance | - | - | dotnet_to_azure |

### pipeline_type `ex_playwright_smoke_test`

| Agent | Role / description | Produces | Consumes | Tools | Model | Used in |
|---|---|---|---|---|---|---|
| `playwright-smoke-test` | One-turn live check that the playwright tool set actually works | - | - | playwright | - | ex_playwright_smoke_test |

### pipeline_type `file_analyst`

| Agent | Role / description | Produces | Consumes | Tools | Model | Used in |
|---|---|---|---|---|---|---|
| `file-analyst` | Step 0 for any workflow with document uploads. Inventories every uploaded file, decides which ones the user's request actually implicates, extracts only those, and hands downstream steps an intent... | file-analyst | - | file_extract | - | - |

### pipeline_type `mulesoft_to_springboot`

| Agent | Role / description | Produces | Consumes | Tools | Model | Used in |
|---|---|---|---|---|---|---|
| `mulesoft-aws-infra` | Generates Terraform for ECS Fargate, RDS, SQS/SNS, ALB, and per-service IAM roles. | mulesoft-aws-infra | mulesoft-decomposition, mulesoft-security-architecture | workspace | - | mulesoft_to_springboot |
| `mulesoft-code-compliance` | SAST/SCA tooling, SonarQube quality gates, Checkstyle/SpotBugs/PMD config, license policy, and pre-commit/CI gates. | mulesoft-code-compliance | mulesoft-springboot-scaffold, mulesoft-feature-coding | - | - | mulesoft_to_springboot |
| `mulesoft-dataweave-translator` | Translates DataWeave scripts into MapStruct or hand-written Java mappers with unit tests. | mulesoft-dataweave-translator | mulesoft-inventory, mulesoft-springboot-scaffold | workspace | - | mulesoft_to_springboot |
| `mulesoft-decomposition` | Proposes the Spring Boot microservice split with bounded contexts and service topology. | mulesoft-decomposition | mulesoft-inventory, mulesoft-user-stories | - | - | mulesoft_to_springboot |
| `mulesoft-feature-coding` | Implements the user stories' business logic in the Spring Boot services - controllers, services, persistence, integrations. | mulesoft-feature-coding | mulesoft-user-stories, mulesoft-springboot-scaffold | workspace | - | mulesoft_to_springboot |
| `mulesoft-inventory` | Catalogues your Mulesoft estate - flows, connectors, DataWeave transforms, and migration risk hotspots. | mulesoft-inventory | - | - | - | mulesoft_to_springboot |
| `mulesoft-sdlc-governance` | Architecture Decision Records, runbooks, SLOs/SLIs, dashboards, compliance evidence matrix, and operations handover. | mulesoft-sdlc-governance | mulesoft-security-architecture, mulesoft-aws-infra, mulesoft-code-compliance, mulesoft-test-compliance, mulesoft-validation | - | - | mulesoft_to_springboot |
| `mulesoft-security-architecture` | STRIDE threat model, IAM/access design, encryption, secrets, WAF, and security gates for the target AWS architecture. | mulesoft-security-architecture | mulesoft-inventory, mulesoft-decomposition | - | - | mulesoft_to_springboot |
| `mulesoft-springboot-scaffold` | Generates a commit-ready Spring Boot 3 scaffold for each microservice. | mulesoft-springboot-scaffold | mulesoft-inventory, mulesoft-decomposition | workspace | - | mulesoft_to_springboot |
| `mulesoft-test-compliance` | Test pyramid, coverage gates, compliance test mapping (PCI/GDPR/SOC 2), perf & chaos plans. | mulesoft-test-compliance | mulesoft-security-architecture, mulesoft-test-implementation | - | - | mulesoft_to_springboot |
| `mulesoft-test-implementation` | Writes the JUnit 5 + Testcontainers + Spring Cloud Contract test code that proves the acceptance criteria. | mulesoft-test-implementation | mulesoft-user-stories, mulesoft-feature-coding | workspace | - | mulesoft_to_springboot |
| `mulesoft-user-stories` | Turns the inventory into epics, user stories, and Gherkin acceptance criteria for the migrated capabilities. | mulesoft-user-stories | mulesoft-inventory | - | - | mulesoft_to_springboot |
| `mulesoft-validation` | Designs the parallel-run harness against the legacy Mule app, cutover gates, and rollback runbook. | mulesoft-validation | mulesoft-decomposition, mulesoft-test-compliance | - | - | mulesoft_to_springboot |

### pipeline_type `ppt`

| Agent | Role / description | Produces | Consumes | Tools | Model | Used in |
|---|---|---|---|---|---|---|
| `ppt-brief-analyst` | Analyses the brief and architects the slide-by-slide plan, narrative arc, and content structure for the deck. | ppt-brief-analyst | - | workspace | - | ppt, ppt_v2 |
| `ppt-composer` | Builds the complete HTML presentation from the plan - every slide, chart, and visual element wired to the template. | ppt-composer | ppt-brief-analyst | workspace | - | ppt, ppt_v2 |
| `ppt-validator` | Validates the deck for structural integrity and presentation correctness, then packages it ready for delivery. | ppt-validator | ppt-composer | workspace | - | ppt |

### pipeline_type `ppt_revision`

| Agent | Role / description | Produces | Consumes | Tools | Model | Used in |
|---|---|---|---|---|---|---|
| `ppt-revision-agent` | Makes precise, surgical edits to an existing HTML presentation based on your revision request, without rebuilding the deck. | ppt-revision-agent | - | - | - | ppt_revision |

### pipeline_type `ppt_v2`

| Agent | Role / description | Produces | Consumes | Tools | Model | Used in |
|---|---|---|---|---|---|---|
| `ppt-code-generator` | Reads the finished HTML deck and authors PptxGenJS that builds a real, editable .pptx, revising until the geometry audit is clean. | ppt-code-generator | ppt-deck-qa-v2 | pptx | - | ppt_v2 |
| `ppt-deck-qa-v2` | Lands the composed deck in the workspace as presentation.html and fixes its structural and presentation defects. | ppt-deck-qa-v2 | ppt-composer | workspace, playwright | - | ppt_v2 |

### pipeline_type `prototype`

| Agent | Role / description | Produces | Consumes | Tools | Model | Used in |
|---|---|---|---|---|---|---|
| `prototype-analyze` | Performs a read-only Spec Kit-style cross-artifact analysis of the spec and task list - checks consistency, coverage gaps, ambiguities, duplications, and unmapped tasks before implementation starts. | prototype-analyze | prototype-specify, prototype-plan | - | - | prototype |
| `prototype-specify` | Analyses the brief and writes the specification - navigation graph, page structure, and design-system selection for the prototype. | prototype-specify | - | - | - | prototype |

### pipeline_type `prototype, prototype_feature_revision`

| Agent | Role / description | Produces | Consumes | Tools | Model | Used in |
|---|---|---|---|---|---|---|
| `prototype-plan` | Build Planning & Task Decomposition | prototype-plan | prototype-specify, prototype-revision-feature-specify | - | - | prototype, prototype_feature_revision |

### pipeline_type `prototype, prototype_large_revision, prototype_feature_revision`

| Agent | Role / description | Produces | Consumes | Tools | Model | Used in |
|---|---|---|---|---|---|---|
| `prototype-build` | Incremental HTML Construction | prototype-build | prototype-plan, prototype-revision-planner | prototype_emit_only | - | prototype, prototype_feature_revision, prototype_large_revision |

### pipeline_type `prototype, prototype_revision, prototype_large_revision, prototype_feature_revision`

| Agent | Role / description | Produces | Consumes | Tools | Model | Used in |
|---|---|---|---|---|---|---|
| `prototype-validate` | Validates the final prototype for structural integrity, navigation correctness, and delivery readiness. | prototype-validate | prototype-build, prototype-revision-agent | prototype_emit_only, playwright | - | prototype, prototype_feature_revision, prototype_large_revision, prototype_revision |

### pipeline_type `prototype_feature_revision`

| Agent | Role / description | Produces | Consumes | Tools | Model | Used in |
|---|---|---|---|---|---|---|
| `prototype-revision-feature-specify` | Feature Definition | prototype-revision-feature-specify | - | workspace | - | prototype_feature_revision |

### pipeline_type `prototype_large_revision`

| Agent | Role / description | Produces | Consumes | Tools | Model | Used in |
|---|---|---|---|---|---|---|
| `prototype-revision-planner` | Revision Task Decomposition | prototype-revision-planner | - | workspace | - | prototype_large_revision |

### pipeline_type `prototype_revision`

| Agent | Role / description | Produces | Consumes | Tools | Model | Used in |
|---|---|---|---|---|---|---|
| `prototype-revision-agent` | Targeted UI Refinement | prototype-revision-agent | - | workspace | - | prototype_revision |

### pipeline_type `prototype_revision, prototype_large_revision, prototype_feature_revision`

| Agent | Role / description | Produces | Consumes | Tools | Model | Used in |
|---|---|---|---|---|---|---|
| `prototype-revision-analyzer` | analyzer | prototype-revision-analyzer | - | - | - | prototype_feature_revision, prototype_large_revision, prototype_revision, prototype_v2_feature_revision, prototype_v2_revision |

### pipeline_type `prototype_v2, prototype`

| Agent | Role / description | Produces | Consumes | Tools | Model | Used in |
|---|---|---|---|---|---|---|
| `design-ingestor` | Ingests Figma frame exports or a custom HTML upload and produces the context/design/ filesystem structure that all downstream prototype agents expect. | - | - | spawn_subagents | - | prototype, prototype_v2 |

### pipeline_type `sc001-test-fixture`

| Agent | Role / description | Produces | Consumes | Tools | Model | Used in |
|---|---|---|---|---|---|---|
| `sc001-fixture-analyze` | Performs analysis as the first step of the SC-001 test fixture. Produces an artifact demonstrating artifact generation capability. | sc001-fixture-analysis | - | - | - | sc001-test-fixture |
| `sc001-fixture-builder` | Consumes the prior analysis step and produces a final artifact. Demonstrates artifact consumption and production in a manifest-driven workflow. | sc001-fixture-output | sc001-fixture-analysis | - | - | sc001-test-fixture |

### pipeline_type `spec_kit`

| Agent | Role / description | Produces | Consumes | Tools | Model | Used in |
|---|---|---|---|---|---|---|
| `analyze-agent` | Performs a read-only cross-artifact consistency check across the spec, plan, and tasks - flags duplication, ambiguity, underspecification, and constitution conflicts. | analysis_report | spec, plan, tasks | - | - | - |
| `clarify-agent` | Identifies ambiguities in a feature spec or brief and asks targeted clarification questions to resolve them. | clarifications | spec, brief | - | - | - |
| `constitution-agent` | Authors or updates the governing principles document - core development rules, tech constraints, and quality gates - for a project or team. | constitution | - | - | - | - |
| `deep-planner` | Analyzes your brief before a workflow starts and produces the planning context that guides every downstream agent. | planning_context | - | planning | - | - |
| `plan-agent` | Produces a detailed implementation plan - technical context, data model, and contracts - from a feature specification. | plan, data_model, contracts | spec, research | - | - | - |
| `research-agent` | Resolves technical unknowns and documents technology decisions with rationale, alternatives, and risks. | research | - | - | - | - |
| `specify-agent` | Transforms a natural-language feature description into a structured, implementation-ready specification. | spec | - | - | - | - |
| `tasks-agent` | Generates a complete, dependency-ordered task list from an implementation plan. | tasks | plan | - | - | - |

### pipeline_type `user_stories`

| Agent | Role / description | Produces | Consumes | Tools | Model | Used in |
|---|---|---|---|---|---|---|
| `backlog-compiler` | Compiles all stories into a clean, structured document ready for your team. | backlog-compiler | epic-architect, story-estimator, nfr-specialist, backlog-reviewer | - | - | user_stories |
| `backlog-reviewer` | Reviews all stories for completeness, gaps, and quality before finalizing. | backlog-reviewer | epic-architect, story-estimator, nfr-specialist | - | - | user_stories |
| `domain-analyst` | Researches your idea, identifies the target market, users, and key personas. | domain-analyst | - | - | - | user_stories |
| `epic-architect` | Writes product epics and detailed user stories with clear acceptance criteria. | epic-architect | domain-analyst | - | - | user_stories |
| `nfr-specialist` | Adds quality requirements covering performance, security, and accessibility. | nfr-specialist | story-estimator | - | - | user_stories |
| `story-estimator` | Estimates effort for each story and maps out which tasks depend on others. | story-estimator | epic-architect | - | - | user_stories |

### pipeline_type `user_stories_revision`

| Agent | Role / description | Produces | Consumes | Tools | Model | Used in |
|---|---|---|---|---|---|---|
| `user-story-revision-agent` | Makes precise, targeted refinements to an existing product backlog based on your revision request, without rewriting it. | user-story-revision-agent | - | - | - | user_stories_revision |

## Step skills (`step.skills`, 190)

A skill is staged at `/skills/<id>/SKILL.md`; the step needs `read_files: true` to open it.

| Skill id | Category | Description |
|---|---|---|
| `accessibility` | planning | Design, implement, and audit WCAG 2.2 AA accessibility for Web and native apps. Use for ARIA roles, contrast, and focus order when building or reviewing UI components. |
| `accessibility-auditor` | specialist | Web accessibility specialist for WCAG compliance, ARIA implementation, and inclusive design. Expert in semantic HTML, keyboard navigation, and assistive technology compatibility. |
| `accessibility-compliance` | security | Implement WCAG 2.2 compliant interfaces with mobile accessibility, inclusive design patterns, and assistive technology support. |
| `android-clean-architecture` | planning | Clean Architecture patterns for Android and Kotlin Multiplatform projects - module structure, dependency rules, UseCases, Repositories, and data layer patterns. |
| `angular-developer` | testing | Generate Angular code and guidance for signals, forms, DI, routing, SSR, accessibility, animations, and testing. Use when scaffolding or reviewing any Angular project or component. |
| `api-connector-builder` | testing | Build a new API connector or provider by matching the target repo's existing integration pattern exactly. Use when adding one more integration without inventing a second archite... |
| `api-design` | workflow | REST API design patterns including resource naming, status codes, pagination, filtering, error responses, versioning, and rate limiting for production APIs. |
| `architecture-decision-records` | planning | Capture architectural decisions made during a session as structured ADRs with context, alternatives, and rationale. Use when a significant tech choice is made or when asked why. |
| `auth-patterns` | security | Master authentication and authorization patterns including JWT, OAuth2, session management, and RBAC. |
| `aws-cloud-patterns` | workflow | AWS cloud patterns for Lambda, ECS, S3, DynamoDB, and Infrastructure as Code with CDK/Terraform. |
| `backend-architect` | specialist | Expert backend architect specializing in scalable API design, microservices architecture, and distributed systems. |
| `backend-patterns` | workflow | Backend architecture patterns, API design, database optimization, and server-side best practices for Node.js, Express, and Next.js API routes. |
| `benchmark` | workflow | Use this skill to measure performance baselines, detect regressions before/after PRs, and compare stack alternatives. |
| `browser-qa` | testing | Use this skill to automate visual testing and UI interaction verification using browser automation after deploying features. |
| `bun-runtime` | testing | Bun as runtime, package manager, bundler, and test runner. When to choose Bun vs Node, migration notes, and Vercel support. |
| `canary-watch` | workflow | Monitor a deployed URL for HTTP errors, console errors, SSE stream health, and performance regressions. Use after deploys, risky merges, or dependency upgrades to verify nothing... |
| `cisco-ios-patterns` | planning | Cisco IOS and IOS-XE review patterns for show commands, config hierarchy, wildcard masks, ACL placement, interface hygiene, and safe change-window verification. |
| `click-path-audit` | debugging | Trace every UI button through its full state-change sequence to find handlers that cancel each other out or leave inconsistent state. Use when debugging finds nothing but button... |
| `clickhouse-io` | planning | ClickHouse database patterns, query optimization, analytics, and data engineering best practices for high-performance analytical workloads. |
| `code-reviewer-expert` | specialist | Comprehensive code review skill for TypeScript, JavaScript, Python, Swift, Kotlin, Go. Includes automated code analysis, best practice checking, security scanning, and review ch... |
| `code-simplifier` | workflow | Simplifies and refines code for clarity, consistency, and maintainability while preserving all functionality. |
| `code-tour` | planning | Create CodeTour .tour JSON files, step-by-step walkthroughs anchored to real files and line ranges. Use for onboarding, architecture, PR, or RCA tours instead of flat Markdown s... |
| `coding-standards` | planning | Baseline cross-project coding conventions for naming, readability, immutability, and code-quality review. Use detailed frontend or backend skills for framework-specific patterns. |
| `compose-multiplatform-patterns` | planning | Compose Multiplatform and Jetpack Compose patterns for KMP projects - state management, navigation, theming, performance, and platform-specific UI. |
| `content-hash-cache-pattern` | workflow | Cache expensive file processing results using SHA-256 content hashes - path-independent, auto-invalidating, with service layer separation. |
| `cpp-coding-standards` | planning | C++ coding standards based on the C++ Core Guidelines (isocpp.github.io). Use when writing, reviewing, or refactoring C++ code to enforce modern, safe, and idiomatic practices. |
| `cpp-testing` | testing | Use only when writing/updating/fixing C++ tests, configuring GoogleTest/CTest, diagnosing failing or flaky tests, or adding coverage/sanitizers. |
| `cqrs-implementation` | planning | Implement Command Query Responsibility Segregation for scalable architectures. |
| `csharp-testing` | testing | C# and .NET testing patterns with xUnit, FluentAssertions, mocking, integration tests, and test organization best practices. |
| `dart-flutter-patterns` | testing | Production Dart/Flutter patterns: null safety, immutable state, async composition, widget architecture, BLoC/Riverpod/Provider, GoRouter, Dio, Freezed. Use when writing or revie... |
| `dashboard-builder` | workflow | Build monitoring dashboards that answer real operator questions for Grafana, SigNoz, and similar platforms. Use when turning metrics into a working dashboard instead of a vanity... |
| `data-scraper-agent` | workflow | Build a scheduled, LLM-enriched data-collection agent (Gemini Flash + GitHub Actions) that scrapes any public source into Notion/Sheets/Supabase. Use to monitor public data auto... |
| `database-architect` | specialist | Expert database architect specializing in data layer design from scratch, technology selection, schema modeling, and scalable database architectures. |
| `database-migrations` | testing | Database migration practices for schema changes, data backfills, rollbacks, and zero-downtime deploys across PostgreSQL, MySQL, and ORMs like Prisma or Django. Use when altering... |
| `database-schema-designer` | specialist | Design robust, scalable database schemas for SQL and NoSQL databases. Provides normalization guidelines, indexing strategies, migration patterns, constraint design, and performa... |
| `deployment-patterns` | workflow | Deployment workflows, CI/CD pipeline patterns, Docker containerization, health checks, rollback strategies, and production readiness checklists for web applications. |
| `design-ingestor` | workflow | Scripts for extracting design tokens and an HTML scaffold from Figma frame exports or custom HTML uploads. Includes figma_extract.py, make_ds.py, and figma_to_html.py. |
| `design-system` | debugging | Use this skill to generate or audit design systems, check visual consistency, and review PRs that touch styling. |
| `design-system-patterns` | planning | Build scalable design systems with design tokens, theming infrastructure, and component architecture patterns. |
| `devops-iac-engineer` | specialist | Implements infrastructure as code using Terraform, Kubernetes, and cloud platforms. Designs scalable architectures, CI/CD pipelines, and observability solutions with security-fi... |
| `django-celery` | testing | Django + Celery async task patterns: configuration, task design, Beat scheduling, retries, canvas workflows, monitoring, testing. Use when adding background jobs to a Django app. |
| `django-patterns` | testing | Django architecture patterns, REST API design with DRF, ORM best practices, caching, signals, middleware, and production-grade Django apps. |
| `django-security` | debugging | Django security best practices, authentication, authorization, CSRF protection, SQL injection prevention, XSS prevention, and secure deployment configurations. |
| `django-tdd` | testing | Django testing strategies with pytest-django, TDD methodology, factory_boy, mocking, coverage, and testing Django REST Framework APIs. |
| `django-verification` | testing | Verification loop for Django projects: migrations, linting, tests with coverage, security scans, and deployment readiness checks before release or PR. |
| `docker-patterns` | security | Docker and Docker Compose patterns for local development, container security, networking, volume strategies, and multi-service orchestration. |
| `dotnet-backend-expert` | specialist | Build ASP.NET Core 8+ backend services with EF Core, auth, background jobs, and production API patterns. |
| `dotnet-patterns` | planning | Idiomatic C# and .NET patterns, conventions, dependency injection, async/await, and best practices for building robust, maintainable .NET applications. |
| `e2e-testing` | testing | Playwright E2E testing patterns, Page Object Model, configuration, CI/CD integration, artifact management, and flaky test strategies. |
| `emoji` | creative | How to pick one emoji that matches a given word. Use when the task wants a single emoji as the entire output, not a sentence or a list. |
| `error-handling` | debugging | Patterns for robust error handling across TypeScript, Python, and Go. Covers typed errors, error boundaries, retries, circuit breakers, and user-facing error messages. |
| `event-sourcing-architect` | specialist | Expert in event sourcing, CQRS, and event-driven architecture patterns. Masters event store design, projection building, saga orchestration, and eventual consistency patterns. |
| `event-store-design` | planning | Design and implement event stores for event-sourced systems. |
| `fal-ai-media` | planning | Generate images, video, and audio via the fal.ai MCP server (Nano Banana, Seedance, Kling, Veo 3, CSM-1B, ThinkSound). Use when generating or editing media with AI and fal.ai MC... |
| `fastapi-patterns` | testing | FastAPI patterns for async APIs, dependency injection, Pydantic request and response models, OpenAPI docs, tests, security, and production readiness. |
| `feature-design-assistant` | planning | Turn ideas into fully formed designs and specs through structured information gathering and collaborative dialogue. |
| `file-extraction` | workflow | Read uploaded PDF, Word, Excel and PowerPoint files - inventory the uploads, extract only what the request needs, look at the page images, and cite pages honestly. |
| `finishing-a-development-branch` | workflow | Use when implementation is complete, all tests pass, and you need to decide how to integrate the work - guides completion of development work by presenting structured options fo... |
| `flox-environments` | planning | Create reproducible, declarative dev environments with Flox (built on Nix) for system-level deps, cross-platform toolchains, and local services like Postgres/Redis. Use even if... |
| `flutter-dart-code-review` | planning | Library-agnostic Flutter/Dart review checklist: widget structure, state management (BLoC/Riverpod/Provider/GetX), Dart idioms, performance, security. Use when reviewing a Flutte... |
| `frontend-patterns` | workflow | Frontend development patterns for React, Next.js, state management, performance optimization, and UI best practices. |
| `frontend-slides` | planning | Build zero-dependency, animation-rich HTML slide decks from scratch or by converting PPT/PPTX. Use for a talk/pitch deck or converting existing slides to a self-contained web pr... |
| `fsharp-testing` | testing | F# testing patterns with xUnit, FsUnit, Unquote, FsCheck property-based testing, integration tests, and test organization best practices. |
| `git-workflow` | collaboration | Git workflow patterns including branching strategies, commit conventions, merge vs rebase, conflict resolution, and collaborative development best practices for teams of all sizes. |
| `github-ops` | debugging | Manage GitHub repos via gh CLI: issue triage, PR merge readiness, CI/CD debugging, release prep, and Dependabot/security monitoring. Use for GitHub tasks beyond plain git commands. |
| `gitlab-ci-patterns` | workflow | Build GitLab CI/CD pipelines with multi-stage workflows, caching, and distributed runners for scalable automation. |
| `golang-patterns` | planning | Idiomatic Go patterns, best practices, and conventions for building robust, efficient, and maintainable Go applications. |
| `golang-testing` | testing | Go testing patterns including table-driven tests, subtests, benchmarks, fuzzing, and test coverage. Follows TDD methodology with idiomatic Go practices. |
| `healthcare-cdss-patterns` | testing | Clinical Decision Support System patterns: drug interaction checks, dose validation, NEWS2/qSOFA scoring, alert severity as pure testable functions. Use when building CDSS logic... |
| `healthcare-emr-patterns` | planning | EMR/EHR development patterns: patient encounter workflows, prescription generation, CDSS integration, accessible clinical data entry UI. Use when building patient-record features. |
| `healthcare-phi-compliance` | security | PHI/PII protection patterns: data classification, access control, audit trails, encryption, and leak vectors (HIPAA, GDPR, DISHA). Use when a feature touches patient or clinicia... |
| `hexagonal-architecture` | testing | Design, implement, and refactor Ports & Adapters systems with clear domain boundaries, dependency inversion, and testable use-case orchestration across TypeScript, Java, Kotlin,... |
| `hipaa-compliance` | security | Canonical entrypoint for US HIPAA compliance: PHI handling, covered entities, BAAs, breach posture, delegating detail to healthcare-phi-compliance. Use only when a task explicit... |
| `html-accessibility` | specialist | Minimal accessibility fixes for a generated HTML page: lang attribute, one semantic heading, accessible emoji text. Use when writing or reviewing a screen-reader friendly HTML p... |
| `html-deck-to-pptx` | uncategorized | Turn a finished HTML slide deck into a real, editable PowerPoint file with PptxGenJS - the layout contract, the five rules that break the build, and the geometry the verifier en... |
| `html-page` | workflow | How to write a single self-contained HTML page. Use when the task wants one complete page file, not a fragment or a description of one. |
| `incident-runbooks` | research | Create structured incident response runbooks with step-by-step procedures, escalation paths, and recovery actions. |
| `interaction-design` | planning | Design and implement microinteractions, motion design, transitions, and user feedback patterns for delightful user experiences. |
| `java-coding-standards` | collaboration | Java 17+ standards for Spring Boot and Quarkus: naming, immutability, Optional/streams, exceptions, generics, CDI, reactive patterns, auto-detected per framework. Use when writi... |
| `javascript-testing` | testing | Implement comprehensive testing strategies using Jest, Vitest, and Testing Library for unit, integration, and end-to-end testing. |
| `jira-integration` | testing | Use this skill when retrieving Jira tickets, analyzing requirements, updating ticket status, adding comments, or transitioning issues. Provides Jira API patterns via MCP or dire... |
| `joke` | creative | How to write a one-line joke about a given word. Use when the task wants a short joke, not a poem or a plain fact sentence. |
| `jpa-patterns` | planning | JPA/Hibernate patterns for entity design, relationships, query optimization, transactions, auditing, indexing, pagination, and pooling in Spring Boot. |
| `k6-load-testing` | testing | Comprehensive k6 load testing for API, browser, and scalability testing with realistic scenarios, CI/CD integration, and results analysis. |
| `kotlin-coroutines-flows` | testing | Kotlin Coroutines and Flow patterns for Android and KMP - structured concurrency, Flow operators, StateFlow, error handling, and testing. |
| `kotlin-exposed-patterns` | workflow | JetBrains Exposed ORM patterns including DSL queries, DAO pattern, transactions, HikariCP connection pooling, Flyway migrations, and repository pattern. |
| `kotlin-ktor-patterns` | testing | Ktor server patterns including routing DSL, plugins, authentication, Koin DI, kotlinx.serialization, WebSockets, and testApplication testing. |
| `kotlin-patterns` | planning | Idiomatic Kotlin patterns, best practices, and conventions for building robust, efficient, and maintainable Kotlin applications with coroutines, null safety, and DSL builders. |
| `kotlin-testing` | testing | Kotlin testing patterns with Kotest, MockK, coroutine testing, property-based testing, and Kover coverage. Follows TDD methodology with idiomatic Kotlin practices. |
| `kubernetes-architect` | specialist | Expert Kubernetes architect specializing in cloud-native infrastructure, advanced GitOps workflows (ArgoCD/Flux), and enterprise container orchestration. |
| `laravel-patterns` | security | Laravel architecture patterns, routing/controllers, Eloquent ORM, service layers, queues, events, caching, and API resources for production apps. |
| `laravel-plugin-discovery` | planning | Discover and evaluate Laravel packages via LaraPlugins.io MCP. Use when the user wants to find plugins, check package health, or assess Laravel/PHP compatibility. |
| `laravel-security` | security | Laravel security best practices for authn/authz, validation, CSRF, mass assignment, file uploads, secrets, rate limiting, and secure deployment. |
| `laravel-tdd` | testing | Test-driven development for Laravel with PHPUnit and Pest, factories, database testing, fakes, and coverage targets. |
| `laravel-verification` | testing | Verification loop for Laravel projects: env checks, linting, static analysis, tests with coverage, security scans, and deployment readiness. |
| `make-interfaces-feel-better` | planning | Apply design-engineering details, spacing, typography, borders, shadows, motion, hit areas, interaction states, that make an interface feel polished. Use when a UI feels flat or... |
| `market-research` | testing | Conduct market sizing, competitive analysis, investor due diligence, and technology scans with sourced, decision-oriented summaries. Use for TAM/SAM/SOM estimates or competitor... |
| `microservices-patterns` | planning | Design microservices architectures with service boundaries, event-driven communication, and resilience patterns. |
| `mle-workflow` | debugging | Production ML workflow: data contracts, reproducible training, offline/online evals, deployment, monitoring, rollback for recommender/classifier systems. Use to harden ML work b... |
| `monitoring-observability` | testing | Monitoring and observability with OpenTelemetry, Prometheus, Grafana dashboards, and structured logging. |
| `motion-advanced` | workflow | Advanced React/Next.js motion: drag & drop, gestures, text animation, SVG path drawing, custom hooks, imperative useAnimate sequences. Requires motion-foundations for basics bey... |
| `motion-foundations` | debugging | Foundational motion tokens, spring presets, performance rules, prefers-reduced-motion, and SSR-safety for React/Next.js with motion/react. Load before any animated component or... |
| `motion-patterns` | workflow | Production-ready animation patterns for React / Next.js - button, modal, toast, stagger, page transitions, exit animations, scroll, and layout - built on motion-foundations toke... |
| `motion-ui` | workflow | Production-ready UI motion system for React/Next.js. Use when implementing animations, transitions, or motion patterns. |
| `mysql-patterns` | debugging | MySQL and MariaDB schema, query, indexing, transaction, replication, and connection-pool patterns for production backends. |
| `nestjs-patterns` | testing | NestJS architecture patterns for modules, controllers, providers, DTO validation, guards, interceptors, config, and production-grade TypeScript backends. |
| `netmiko-ssh-automation` | planning | Safe Python Netmiko patterns for read-only collection, bounded batch SSH, TextFSM parsing, guarded config changes, timeouts, and network automation error handling. |
| `network-bgp-diagnostics` | collaboration | Diagnostics-only BGP troubleshooting patterns for neighbor state, route exchange, prefix policy, AS path inspection, and safe evidence collection. |
| `network-config-validation` | collaboration | Pre-deployment checks for router and switch configuration, including dangerous commands, duplicate addresses, subnet overlaps, stale references, management-plane risk, and IOS-s... |
| `network-interface-health` | workflow | Diagnose interface errors, drops, CRCs, duplex mismatches, flapping, speed negotiation issues, and counter trends on routers, switches, and Linux hosts. |
| `nextjs-turbopack` | debugging | Next.js 16+ and Turbopack - incremental bundling, FS caching, dev speed, and when to use Turbopack vs webpack. |
| `nodejs-keccak256` | collaboration | Prevent Ethereum hashing bugs in JavaScript and TypeScript. Node's sha3-256 is NIST SHA3, not Ethereum Keccak-256, and silently breaks selectors, signatures, storage slots, and... |
| `nutrient-document-processing` | security | Process, convert, OCR, extract, redact, sign, and fill documents using the Nutrient DWS API. Works with PDFs, DOCX, XLSX, PPTX, HTML, and images. |
| `nuxt4-patterns` | debugging | Nuxt 4 app patterns for hydration safety, performance, route rules, lazy loading, and SSR-safe data fetching with useFetch and useAsyncData. |
| `observability-engineer` | specialist | Build production-ready monitoring, logging, and tracing systems. Implements comprehensive observability strategies, SLI/SLO management, and incident response workflows. |
| `perl-patterns` | testing | Modern Perl 5.36+ idioms, best practices, and conventions for building robust, maintainable Perl applications. |
| `perl-security` | security | Comprehensive Perl security covering taint mode, input validation, safe process execution, DBI parameterized queries, web security (XSS/SQLi/CSRF), and perlcritic security polic... |
| `perl-testing` | testing | Perl testing patterns using Test2::V0, Test::More, prove runner, mocking, coverage with Devel::Cover, and TDD methodology. |
| `plankton-code-quality` | planning | Write-time code quality enforcement using Plankton - auto-formatting, linting, and AI-powered fixes on every file edit via hooks. |
| `playful-tone` | creative | How to write a short, punchy, casual sentence instead of a formal one. Use when a task wants informal, energetic prose rather than a poem or a neutral sentence. |
| `poet` | creative | How to write a two-line rhyming poem that ends with a given word. Use when the task calls for a couplet built around a specific word rather than a plain sentence. |
| `postgres-patterns` | security | PostgreSQL database patterns for query optimization, schema design, indexing, and security. Based on Supabase best practices. |
| `postgresql-code-review` | collaboration | PostgreSQL-specific code review focusing on best practices, anti-patterns, JSONB operations, array usage, and Row Level Security. |
| `postgresql-optimization` | testing | PostgreSQL optimization including indexes, query plans, partitioning, JSONB operations, and connection pooling. |
| `postgresql-table-design` | testing | PostgreSQL-specific schema design covering data types, indexing, constraints, performance patterns, and advanced features. |
| `postmortem-writing` | research | Write effective blameless postmortems with root cause analysis, timelines, and action items. |
| `prisma-patterns` | testing | Prisma ORM patterns for TypeScript backends: schema design, query optimization, transactions, pagination, and traps like updateMany's missing records. Use when writing or debugg... |
| `product-capability` | planning | Turn a PRD, roadmap ask, or product discussion into an implementation-ready capability plan exposing constraints, invariants, interfaces, and open decisions. Use for multi-servi... |
| `product-lens` | planning | Use this skill to validate the "why" before building, run product diagnostics, and pressure-test product direction before the request becomes an implementation contract. |
| `product-manager-toolkit` | specialist | Comprehensive toolkit for product managers including RICE prioritization, customer interview analysis, PRD templates, discovery frameworks, and go-to-market strategies. |
| `production-audit` | testing | Local-evidence production readiness audit for shipped apps, pre-launch reviews, post-merge checks, and "what breaks in prod?" questions without sending repo data to an external... |
| `projection-patterns` | planning | Build read models and projections from event streams. |
| `python-patterns` | planning | Pythonic idioms, PEP 8 standards, type hints, and best practices for building robust, efficient, and maintainable Python applications. |
| `python-testing` | testing | Python testing strategies using pytest, TDD methodology, fixtures, mocking, parametrization, and coverage requirements. |
| `pytorch-patterns` | debugging | PyTorch deep learning patterns and best practices for building robust, efficient, and reproducible training pipelines, model architectures, and data loading. |
| `quarkus-patterns` | workflow | Quarkus 3.x LTS patterns: JAX-RS/RESTEasy Reactive APIs, CDI services, Panache data access, Camel messaging, async processing for event-driven Java backends. Use for Quarkus ser... |
| `quarkus-security` | security | Quarkus Security best practices for authentication, authorization, JWT/OIDC, RBAC, input validation, CSRF, secrets management, and dependency security. |
| `quarkus-tdd` | testing | Test-driven development for Quarkus 3.x LTS using JUnit 5, Mockito, REST Assured, Camel testing, and JaCoCo. Use when adding features, fixing bugs, or refactoring event-driven s... |
| `quarkus-verification` | testing | Verification loop for Quarkus projects: build, static analysis, tests with coverage, security scans, native compilation, and diff review before release or PR. |
| `receiving-code-review` | testing | Verify code review feedback against codebase reality before implementing it rather than agreeing performatively. Use when receiving review comments that seem unclear or question... |
| `recsys-pipeline-architect` | planning | Design composable ranking/feed pipelines using the Source-Hydrator-Filter-Scorer-Selector-SideEffect framework from xAI's For You algorithm. Use for any top-K-items-for-a-user r... |
| `redis-patterns` | workflow | Redis data structure patterns, caching strategies, distributed locks, rate limiting, pub/sub, and connection management for production applications. |
| `refactor-plan` | collaboration | Create a concrete plan before starting a multi-file refactor with safe sequencing, verification steps, and rollback procedures. |
| `regex-vs-llm-structured-text` | workflow | Decision framework for choosing between regex and LLM when parsing structured text - start with regex, add LLM only for low-confidence edge cases. |
| `repo-scan` | workflow | Cross-stack source code asset audit - classifies every file, detects embedded third-party libraries, and delivers actionable four-level verdicts per module with interactive HTML... |
| `research-ops` | workflow | Evidence-first operator workflow that coordinates exa-search, deep-research, market-research, and lead-intelligence for current-state research. Use for fresh, sourced facts or m... |
| `responsive-design` | planning | Implement modern responsive layouts using container queries, fluid typography, CSS Grid, and mobile-first breakpoint strategies. |
| `rhyming` | creative | How to build a two-line couplet that actually rhymes on the final vowel sound. Use whenever a task asks for a rhyming couplet. |
| `rust-patterns` | planning | Idiomatic Rust patterns, ownership, error handling, traits, concurrency, and best practices for building safe, performant applications. |
| `rust-testing` | testing | Rust testing patterns including unit tests, integration tests, async testing, property-based testing, mocking, and coverage. Follows TDD methodology. |
| `safety-guard` | planning | Use this skill to prevent destructive operations when working on production systems or running agents autonomously. |
| `saga-orchestration` | planning | Implement saga patterns for distributed transactions and cross-aggregate workflows. |
| `scientific-db-pubmed-database` | collaboration | Direct PubMed and NCBI E-utilities search workflows for biomedical literature, MeSH queries, PMID lookup, citation retrieval, and API-backed literature monitoring. |
| `scientific-db-uspto-database` | workflow | USPTO patent and trademark data workflow for official record lookup, PatentSearch queries, TSDR checks, assignment data, and reproducible IP research logs. |
| `scientific-pkg-gget` | planning | gget CLI and Python workflow for quick genomic database queries, sequence lookup, BLAST-style searches, enrichment checks, and reproducible bioinformatics evidence logs. |
| `scientific-thinking-literature-review` | collaboration | Systematic literature-review workflow for academic, biomedical, technical, and scientific topics, including search planning, source screening, synthesis, citation checks, and ev... |
| `scientific-thinking-scholar-evaluation` | planning | Structured scholarly-work evaluation for papers, proposals, literature reviews, methods sections, evidence quality, citation support, and research-writing feedback. |
| `security-bounty-hunter` | security | Hunt for exploitable, bounty-worthy security issues in repositories. Focuses on remotely reachable vulnerabilities that qualify for real reports instead of noisy local-only find... |
| `security-compliance-expert` | specialist | Guide defense-in-depth security architecture, SOC2/ISO27001/GDPR/HIPAA compliance, threat modeling, and incident response. Use for security program design, not single-PR code re... |
| `security-review` | security | Security checklist and patterns for authentication, user input handling, secrets, new API endpoints, and payment features. Use when implementing security-sensitive code. |
| `senior-architect` | specialist | Design scalable system architecture: diagram generation, design pattern selection, tech-stack decision frameworks, and dependency analysis. Use for cross-cutting architecture de... |
| `seo` | planning | Audit and implement technical SEO, on-page optimization, structured data, Core Web Vitals, and keyword-to-URL mapping. Use for better search visibility or sitemap/robots work. |
| `springboot-patterns` | workflow | Spring Boot architecture patterns, REST API design, layered services, data access, caching, async processing, and logging. Use for Java Spring Boot backend work. |
| `springboot-security` | security | Spring Security best practices for authn/authz, validation, CSRF, secrets, headers, rate limiting, and dependency security in Java Spring Boot services. |
| `springboot-tdd` | testing | Test-driven development for Spring Boot using JUnit 5, Mockito, MockMvc, Testcontainers, and JaCoCo. Use when adding features, fixing bugs, or refactoring. |
| `springboot-verification` | testing | Verification loop for Spring Boot projects: build, static analysis, tests with coverage, security scans, and diff review before release or PR. |
| `sql-code-review` | collaboration | Universal SQL code review for security, maintainability, and quality across MySQL, PostgreSQL, SQL Server, and Oracle. |
| `swift-actor-persistence` | workflow | Thread-safe data persistence in Swift using actors - in-memory cache with file-backed storage, eliminating data races by design. |
| `swift-concurrency-6-2` | planning | Swift 6.2 Approachable Concurrency - single-threaded by default, @concurrent for explicit background offloading, isolated conformances for main actor types. |
| `swift-protocol-di-testing` | testing | Protocol-based dependency injection for testable Swift code - mock file system, network, and external APIs using focused protocols and Swift Testing. |
| `swiftui-patterns` | planning | SwiftUI architecture patterns, state management with @Observable, view composition, navigation, performance optimization, and modern iOS/macOS UI best practices. |
| `systematic-debugging` | debugging | Use when encountering any bug, test failure, or unexpected behavior, before proposing fixes |
| `tdd-workflow` | testing | Use this skill when writing new features, fixing bugs, or refactoring code. Enforces test-driven development with 80%+ coverage including unit, integration, and E2E tests. |
| `terminal-ops` | testing | Evidence-first repo execution workflow. Use when the user wants a command run, a repo checked, a CI failure debugged, or a narrow fix pushed with exact proof of what was execute... |
| `terraform-modules` | workflow | Build reusable Terraform modules for AWS, Azure, GCP, and OCI infrastructure following IaC best practices. |
| `test-driven-development` | testing | Use when implementing any feature or bugfix, before writing implementation code |
| `threat-modeling-expert` | specialist | Expert in threat modeling methodologies, security architecture review, and risk assessment. Masters STRIDE, PASTA, attack trees, and security requirement extraction. |
| `typescript-expert` | specialist | TypeScript and JavaScript expert with deep knowledge of type-level programming, performance optimization, monorepo management, migration strategies, and modern tooling. |
| `ui-demo` | testing | Record polished WebM UI demo videos with Playwright using a Discover-Rehearse-Record process with a cursor overlay and natural pacing. Use for a demo video, walkthrough, or tuto... |
| `ui-to-vue` | planning | Use when the user has UI screenshots or design exports that need batch conversion into Vue 3 components, especially with Vant, Element Plus, or Ant Design Vue. |
| `ux-researcher` | specialist | UX research and design toolkit including data-driven persona generation, journey mapping, usability testing frameworks, and research synthesis for user-centered design. |
| `velocity-design` | workflow | Active design template for this run - its purpose, required output structure, workflow, and acceptance criteria. Read it before producing any deliverable. |
| `velocity-design-system` | workflow | The design system chosen for this run (colours, type, spacing, radii, components, voice). Read it before deciding or judging how anything looks; use only its colours and fonts. |
| `verification-before-completion` | workflow | Run and confirm verification command output before claiming work is complete, fixed, or passing. Use before committing, opening a PR, or making any success claim. |
| `verification-loop` | workflow | Runs a build/lint/test verification loop before declaring work done. Use after a feature or refactor, before opening a PR, or whenever quality gates need to pass. |
| `visual-design-foundations` | planning | Apply typography, color theory, spacing systems, and iconography principles to create cohesive visual designs. |
| `vite-patterns` | debugging | Vite 8+ build tool patterns: config, plugins, HMR, env variables, dev server proxy, SSR, library mode, dependency pre-bundling. Use when working with vite.config.ts or debugging... |
| `web-component-design` | planning | Master React, Vue, and Svelte component patterns including CSS-in-JS, composition strategies, and reusable component architecture. |
| `windows-desktop-e2e` | testing | E2E testing for Windows native desktop apps (WPF, WinForms, Win32/MFC, Qt) using pywinauto and Windows UI Automation. |
| `workflow-orchestration` | workflow | Design durable workflows with Temporal for distributed systems covering workflow vs activity separation, saga patterns, state management, and determinism constraints. |

## Predefined workflows (valid `trigger: workflow` targets and `chained_from` ids)

| Id | Launchable | Beta | Steps | Planner | Deliverable | Chained from |
|---|---|---|---|---|---|---|
| `app_builder` | yes | no | 15 | run | serialized_sandbox app | prototype, ppt, user_stories |
| `app_builder_revision` | no | yes | 1 | skip | serialized_sandbox app | - |
| `backlog` | yes | no | 21 | skip | single_file Backlog.pdf | prototype_v2 |
| `backlog_revision` | no | yes | 5 | skip | single_file Backlog.pdf | - |
| `chat` | no | no | 7 | run | streamed_text chat.md | - |
| `custom` | yes | no | 9 | run | streamed_text output.md | - |
| `custom_revision` | no | yes | 2 | skip | serialized_sandbox output | - |
| `dotnet_to_azure` | yes | yes | 13 | run | serialized_sandbox azure-app | - |
| `ex_A1_loop` | yes | no | 4 | skip | single_file greeting.md | - |
| `ex_A2_branch` | yes | no | 5 | skip | single_file greeting.md | - |
| `ex_A3_b_spanish` | yes | no | 1 | skip | single_file greeting.md | - |
| `ex_A3_c_dutch` | yes | no | 1 | skip | single_file greeting.md | - |
| `ex_A3_divert` | yes | no | 3 | skip | single_file greeting.md | - |
| `ex_A4_human_divert` | yes | no | 3 | skip | single_file greeting.md | - |
| `ex_A4_human_gate` | yes | no | 5 | skip | single_file greeting.md | - |
| `ex_playwright_smoke_test` | yes | no | 1 | skip | serialized_sandbox  | - |
| `ex_publish_step` | no | yes | 2 | skip | single_file prototype.html | - |
| `ex_test_loop_reachable_skip` | no | yes | 5 | skip | single_file greeting.md | - |
| `ex_test_transitive_skip` | no | yes | 5 | skip | single_file greeting.md | - |
| `ex_validation_retry` | no | yes | 2 | skip | single_file output.md | - |
| `mulesoft_to_springboot` | yes | yes | 13 | run | serialized_sandbox springboot-app | - |
| `ppt` | yes | no | 3 | run | ppt presentation.pptx | prototype, user_stories |
| `ppt_revision` | no | yes | 1 | skip | single_file presentation.html | - |
| `ppt_v2` | yes | no | 4 | run | single_file presentation.html | - |
| `prototype` | yes | no | 6 | run | single_file prototype.html | user_stories, ppt, ppt_v2 |
| `prototype_feature_revision` | no | yes | 5 | skip | single_file prototype.html | - |
| `prototype_large_revision` | no | yes | 4 | skip | single_file prototype.html | - |
| `prototype_revision` | no | yes | 3 | skip | single_file prototype.html | - |
| `prototype_v2` | yes | no | 12 | skip | single_file prototype.html | - |
| `prototype_v2_feature_revision` | no | yes | 5 | skip | single_file prototype.html | - |
| `prototype_v2_revision` | no | yes | 3 | skip | single_file prototype.html | - |
| `reverse_engineer` | yes | yes | 0 | run | streamed_text analysis.md | - |
| `sample_brownfield` | no | yes | 2 | run | repo_diff repo_diff | - |
| `sample_fanout` | no | yes | 2 | run | serialized_sandbox  | - |
| `sample_subagents_parallel` | yes | yes | 4 | skip | single_file page.html | - |
| `sample_wave` | no | yes | 2 | run | serialized_sandbox  | - |
| `sc001-test-fixture` | no | no | 2 | run | streamed_text analysis.md | - |
| `user_stories` | yes | no | 6 | run | streamed_text user_stories.md | prototype, ppt |
| `user_stories_revision` | no | yes | 1 | skip | streamed_text user_stories.md | - |
