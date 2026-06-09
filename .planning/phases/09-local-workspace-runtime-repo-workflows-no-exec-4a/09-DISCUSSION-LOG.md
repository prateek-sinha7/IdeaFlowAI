# Phase 9: Local Workspace Runtime + Repo Workflows (no exec) [4A] - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-10
**Phase:** 09-local-workspace-runtime-repo-workflows-no-exec-4a
**Areas discussed:** Runtime port surface, tree-sitter RepoIndex, MCP client + catalog, Integration vs handoff

---

## Meta — which areas to discuss

| Option | Description | Selected |
|--------|-------------|----------|
| (multiSelect of all 4 HOW areas) | SPEC.md locks all 14 WHAT requirements; the remaining decisions are HOW-level architecture. Prior phases locked these to plan.md recommendations. | ✓ all four |

**User's choice:** Deep-dive ALL FOUR areas (Runtime port surface, tree-sitter RepoIndex, MCP client + catalog, Integration vs handoff) — a departure from the Phases 1/2/4/5/6/7/8 "lock all to recommendations" default.
**Notes:** Phase 9 is the first net-new workflow class (not a refactor), so the architecture is genuinely new and warranted explicit per-area decisions. All decisions still landed on the plan-grounded recommendation.

---

## Area 1 — Runtime port surface (RUNTIME-01/02)

### Q1: How should RuntimeEnvironment and Workspace compose?

| Option | Description | Selected |
|--------|-------------|----------|
| Provisioner + facade | RuntimeEnvironment = provisioner (create_workspace/teardown); Workspace = fs+git+exec+ExecutionPolicy facade carrying owner_id/workspace_id. Cleanest ECS seam (§27). | ✓ |
| Single merged port | One RuntimeEnvironment with all methods; no separate Workspace. Fewer types, weaker ECS seam. | |
| Workspace self-provisions | Workspace.create()/teardown() static factory; no separate RuntimeEnvironment. No clean ECS plug-in point. | |

**User's choice:** Provisioner + facade (matches plan.md §6 line 480 `Workspace.runtime: RuntimeEnvironment`).

### Q2: How should RunSandbox refold without perturbing prototype parity?

| Option | Description | Selected |
|--------|-------------|----------|
| Refold in-place | RunSandbox internals re-implement on Workspace(has_git=False, exec=off); name survives as thin alias/subtype; call sites untouched (parity-safest); bespoke disk logic deleted (INV-12). | ✓ |
| Delete + re-point callers | Remove RunSandbox; re-point every call site to Workspace directly. Cleaner type, higher parity risk/churn. | |

**User's choice:** Refold in-place.

---

## Area 2 — tree-sitter RepoIndex (REPO-02)

### Q1: How should tree-sitter grammars be sourced? (offline-CI constraint)

| Option | Description | Selected |
|--------|-------------|----------|
| Prebuilt wheels | tree-sitter-language-pack / tree-sitter-languages binary wheels for py/js/ts (+ primary langs); installs+imports fully offline, no C toolchain; tree_sitter imported only behind repo_index. | ✓ |
| Per-language packages | Individual tree-sitter-python/-javascript/-typescript; more wiring, some need a compile step. | |
| Vendored grammars | Vendor compiled .so/.wasm; max determinism, heaviest upkeep. | |

**User's choice:** Prebuilt wheels.

### Q2: What's the RepoIndex lifecycle when enabled?

| Option | Description | Selected |
|--------|-------------|----------|
| In-memory per-run | Build symbol index in-memory on opt-in / N6 threshold; discard at teardown. No new table, no invalidation. N6 = config constant + manifest opt-in. | ✓ |
| Persisted typed artifact | Lineage-track index as kind=repo_index; reusable cross-run; needs storage shape + invalidation. | |

**User's choice:** In-memory per-run.

---

## Area 3 — MCP client + catalog (MCP-01/02/03)

### Q1: How should the allow-listed MCP server catalog be declared?

| Option | Description | Selected |
|--------|-------------|----------|
| Registered capabilities | Each server is an mcp_server capability module that @registers; transport + tool allow-list + user_allowed + scope as registration data; surfaced via /api/capabilities. Matches Phase-8 discover(). | ✓ |
| Static data-file catalog | Single YAML/JSON catalog the registry loads; easy to eyeball, diverges from @register, needs its own loader. | |
| Hybrid | Registered modules + external data file for connection details; splits one concept across two homes. | |

**User's choice:** Registered capabilities.

### Q2: How should MCP-01 be proven offline?

| Option | Description | Selected |
|--------|-------------|----------|
| In-repo stdio stub server | Tiny real MCP server fixture spoken to over stdio by MultiServerMCPClient; exercises the real transport + binding end-to-end, fully offline; doubles as the contract fixture. | ✓ |
| Transport-level mock | Mock/record client responses without a real subprocess; lighter, weaker proof the live path connects. | |

**User's choice:** In-repo stdio stub server.

---

## Area 4 — Integration providers vs the handoff bypass (INTEG-01/02 + INV-12)

### Q1: How should integration_provider relate to the MCP catalog?

| Option | Description | Selected |
|--------|-------------|----------|
| MCP-backed binding | integration_provider = the permissioned bridge that takes a catalog mcp_server + an integrations scope and surfaces its tools into create_runner/deepagents. ONE external-tool mechanism; scopes gate which bind. | ✓ |
| Separate SDK path | Own SDK-backed capability (PyGithub/python-gitlab/Slack SDK) independent of MCP; each provider appears twice — two mechanisms (INV-12 smell). | |
| Per-provider mix | MCP for GitHub/GitLab, SDK for Jira/Slack; two binding paths, inconsistent story. | |

**User's choice:** MCP-backed binding.

### Q2: What happens to the GitHub handoff bypass once the unified path exists?

| Option | Description | Selected |
|--------|-------------|----------|
| Delete in-plan | Unified create_runner integration path supersedes the bypass → delete the GitHub-handoff coding-agent path this phase + ledger entry. No dual impl. Planner first confirms /flowin-handoff has no external consumers. | ✓ |
| Survive w/ justification | Keep the pipeline (if /flowin-handoff has outside consumers) + explicit ledger justification. Only if deletion breaks a real consumer. | |
| Defer the call | Land the unified path now, decide the bypass's fate later. Leaves a known dual-impl (least preferred). | |

**User's choice:** Delete in-plan (pending the planner's /flowin-handoff consumer check).

---

## Closing — ready for context?

**User's choice:** "Ready for context" — write 09-CONTEXT.md with the 8 locked decisions + recommendation-locked items (plan/wave split, repo_diff shape).

## Claude's Discretion

- Exact port method signatures + Protocol-vs-base for Workspace (D-01).
- LocalSandboxRuntime impl placement (kernel-side vs app-side) per the import-linter contract (D-01 researcher directive).
- Grammar-pack choice + the N6 threshold value (D-03/D-04).
- mcp_server registration signature + MultiServerMCPClient config from catalog data (D-05).
- The async→sync MCP binding mechanism (D-07).
- repo_inventory/context_pack kernel-side vs app-side per the heavy-dep boundary (D-10).
- Single 0017 migration vs split (D-11) — single recommended.
- Plan-task granularity within the 6-plan frame (D-12).

## Deferred Ideas

- exec + compile/test/lint validators (Phase 10/N3/4B); PR/commit push (N4); sub_sandbox/worktree isolation + fan-out (Phase 11); durable job queue (N8); ECS/EcsRuntime (§27 v2); embeddings/vector retrieval; the full §30 MCP catalog (Confluence/Notion/Linear/Sentry/Figma/Drive/web-search/Playwright); DB-backed user workflows (Q5); live external-server verification (end-of-milestone live pass); the repo-diff frontend viewer (later).
