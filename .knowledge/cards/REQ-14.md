---
id: REQ-14
type: req
status: done
area: [sse, workflow, agents, runtime]
summary: >-
  Agent Runtime, Skills, Hooks, MCP & Integrations (§30; lands across Phases 1B/3/4+)
source: .planning/REQUIREMENTS.md#agent-runtime-skills-hooks-mcp-integrations-30-l
---

### Agent Runtime, Skills, Hooks, MCP & Integrations (§30; lands across Phases 1B/3/4+)

- [x] **HOOK-01**: `HookHandler` executable lifecycle/tool-call hooks bound to events (before/after run·step·tool_call·write, post_task, pre/post_commit, on_validation, before/after_merge, or `*`); outcome continue|warn|block; blocking hooks halt the offending action (N12 / §30)
- [x] **HOOK-02**: Canonical hooks — `secret_scan` (before_write/pre_commit, blocking), `otel_tracing`/logging (`*`, non-blocking → observability), pre/post_commit, post_task (§30/§23)
- [x] **HOOK-03**: Hooks are permissioned (a command-running hook needs `exec`, a git hook needs `git`, a scanner needs `read_files`); engineer-registered, users attach allow-listed only (INV-9/§30)
- [x] **HOOK-04**: Every hook firing → a `hook_runs` row for replay/debug; legacy prompt-only hook survives as a `kind: behavioral` non-executable sub-type (§18/§30)
- [x] **MCP-01**: `McpClientAdapter` (e.g. `langchain-mcp-adapters` `MultiServerMCPClient`) connects to external MCP servers (stdio/SSE/HTTP), lists tools/resources/prompts, binds allowed ones into the agent tool set (N13 / §30)
- [x] **MCP-02**: Allow-listed famous-server catalog (GitHub, GitLab, Jira/Atlassian, Confluence, Slack, Notion, Linear, Sentry, Figma, Filesystem, Postgres, Google Drive, web-search, Playwright, …), each with transport + exposed tools + scoped per-owner creds + `user_allowed` (§30)
- [x] **MCP-03**: `McpCapabilityRegistry` — compiler validates `tools.mcp` only names tools from servers the step + owner may reach; unknown `server.tool` → compile error (§7/§30)
- [x] **MCP-04**: Powerful servers (Filesystem/Postgres/write/network) sit behind the `security` gate + scoped creds + `secrets` permission (R13/§30)
- [x] **INTEG-01**: `integration_provider` capabilities (GitHub/GitLab/Jira/Slack/Confluence/Figma/OpenDesign) make repo/GitHub reachable from the unified `create_runner` path, not only the handoff pipeline (§30)
- [x] **INTEG-02**: `integrations` tool-permission scopes (e.g. `gitlab_read`, `jira_read`) default none; scoped per-owner creds (§8/§30/R13)
- [x] **SKILL-01**: `skill_provider` capabilities (ui · disk · template · repo) with a provider interface + versioning replace the flattened skill content list (§30)
- [x] **CAPRUN-01**: `run_capabilities` persistence records the active runtime + resolved skill/hook/integration/MCP names + versions + `model_overrides` per run for replay/debug (§18/§30)
