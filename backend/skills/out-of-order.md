# Out-of-Order Global Skills — Full Audit

Analysis of all **244 skills** in `backend/skills/global/` for dependencies on
**ECC** ("Everything Claude Code"), **GSD**, **Superpowers**, **OpenDesign**, and
**Claude Code** platform-specific features (`.claude/` directory, `claude -p` CLI,
hook system, Agent tool, MCP config paths) that prevent standalone operation.

This product does not run inside ECC/GSD/Superpowers/OpenDesign and is not Claude Code.
Skills that reference tools/repos/install flows/platform features that don't exist here
will produce broken or misleading instructions when attached to an agent.

## Method

1. Searched every `SKILL.md` body for: `ECC`, `GSD`, `Superpowers`, `OpenDesign`
2. Searched for Claude Code platform markers: `~/.claude/`, `.claude/`, `claude -p`,
   `CLAUDE.md`, `CLAUDE_PLUGIN`, `PreToolUse`, `PostToolUse`, `settings.json` hooks
3. Searched for `superpowers:` skill cross-references
4. Searched for MCP config paths (`~/.claude.json`, `.mcp.json`, `claude mcp add`)
5. Manually verified each flagged skill to classify severity

**Result: 78 of 244 skills are flagged. 166 are clean.**

---

## 🔴 PURGE — 26 skills (delete outright)

These skills **cannot function** without their parent framework. Their core purpose IS
operating within ECC/Superpowers/Claude Code. No salvageable standalone methodology.

| # | Skill | Reason |
|---|-------|--------|
| 1 | `configure-ecc` | Entire skill is an ECC repo clone/install flow |
| 2 | `ecc-guide` | Q&A navigation guide for ECC repository |
| 3 | `ecc-tools-cost-audit` | Audits sibling ECC-Tools GitHub App billing |
| 4 | `hermes-imports` | Ports Hermes workflows into ECC skills |
| 5 | `plan-orchestrate` | Routes plans to ECC `/orchestrate` commands with `ECC_MODE` detection |
| 6 | `agent-sort` | Classifies ECC components into install buckets |
| 7 | `skill-scout` | Searches ECC skill ecosystem directories |
| 8 | `using-superpowers` | Meta-skill for invoking Superpowers `Skill` tool |
| 9 | `hookify-rules` | Creates rules for Claude Code `.claude/` hook system |
| 10 | `nanoclaw-repl` | ECC-specific REPL built on `claude -p` |
| 11 | `ck` | Claude Code context keeper in `~/.claude/skills/ck/` |
| 12 | `claude-devfleet` | Requires `claude mcp add devfleet` + Claude Code agent spawning |
| 13 | `cost-tracking` | Claude Code session cost tracker (`~/.claude-cost-tracker/`) |
| 14 | `context-budget` | Scans Claude Code config (CLAUDE.md, agents/, skills/, .mcp.json) |
| 15 | `eval-harness` | Claude Code `.claude/evals/` evaluation system |
| 16 | `agentic-os` | Architecture built on CLAUDE.md kernel + `.claude/commands/` |
| 17 | `knowledge-ops` | Claude Code project memory (`~/.claude/projects/*/memory/`) |
| 18 | `gan-style-harness` | Multi-agent via `claude -p --model opus` CLI invocations |
| 19 | `skill-comply` | Tests skills via `claude -p` stream-json + `.claude/` conventions |
| 20 | `continuous-learning` | Hook-based learning in `~/.claude/skills/learned/` |
| 21 | `strategic-compact` | Claude Code `/compact` command + hook scripts |
| 22 | `rules-distill` | ECC rules directory structure + Agent subagent dispatch |
| 23 | `writing-skills` | ECC/Superpowers skill authoring with `superpowers:` refs |
| 24 | `subagent-driven-development` | Chains 6+ `superpowers:*` skills as dependencies |
| 25 | `security-scan` | Audits `.claude/` infrastructure (settings.json, hooks, agents/) |
| 26 | `brainstorming` | Superpowers directory paths + skill chaining deps |

---

## 🟡 REWRITABLE — 20 skills (valuable content, needs significant rework)

These have a useful generic methodology but it's currently wrapped in framework-specific
framing, commands, paths, or dispatch patterns. Worth keeping **if rewritten** to be
platform-agnostic. Otherwise, delete.

| # | Skill | Salvageable core | What must be rewritten |
|---|-------|-----------------|----------------------|
| 1 | `workspace-surface-audit` | Audit workspace capabilities/plugins | "ECC-native" recommendations → generic capability audit |
| 2 | `prompt-optimizer` | 6-phase prompt improvement pipeline | ECC command/skill routing → generic improvement steps |
| 3 | `blueprint` | Multi-session planning (DAG, adversarial review) | ECC install/clone instructions → remove |
| 4 | `autonomous-agent-harness` | Persistent agent loop architecture | "Replacing Hermes with ECC" framing → standalone architecture |
| 5 | `automation-audit-ops` | Automation inventory/merge/cut methodology | "ECC lanes" → generic "consolidate into canonical workflow" |
| 6 | `unified-notifications-ops` | Notification routing/dedup/collapse patterns | "ECC-native orchestration" → generic orchestration |
| 7 | `autonomous-loops` | Loop patterns (sequential, continuous PR, DAG) | ECC mapping table + `/verify` → generic loop patterns |
| 8 | `project-flow-ops` | Issue/PR triage + Linear coordination | "ECC 1.x/2.0 program lanes" → generic workflow lanes |
| 9 | `frontend-design-direction` | Frontend design guidance & review checklist | "ECC-specific salvage" framing → standalone design skill |
| 10 | `gateguard` | Fact-forcing pre-action quality gate | ECC hook install option → generic pre-action gate |
| 11 | `dmux-workflows` | Multi-agent tmux/dmux orchestration patterns | "ECC Helper" section → remove or genericize |
| 12 | `dispatching-parallel-agents` | Parallel task decomposition methodology | Claude Code `Task()` API → generic agent dispatch |
| 13 | `documentation-lookup` | Library doc resolution via MCP | `~/.claude.json` config → generic MCP config example |
| 14 | `exa-search` | Exa web search patterns | `~/.claude.json` → generic MCP config |
| 15 | `codebase-onboarding` | 4-phase codebase analysis workflow | "Generate CLAUDE.md" output → generic instruction file |
| 16 | `requesting-code-review` | Code review request workflow | Claude Code Agent dispatch → generic agent/tool dispatch |
| 17 | `using-git-worktrees` | Git worktree isolation for parallel work | Claude Code native tool detection → generic git workflow |
| 18 | `search-first` | Research-before-coding methodology | `~/.claude/` paths + Agent() → generic |
| 19 | `opensource-pipeline` | Fork→sanitize→package open-source workflow | Agent() subagent dispatch → generic orchestration |
| 20 | `deep-research` | Multi-source research with parallel search | "Claude Code Task tool" + MCP deps → generic |

---

## 🟢 KEEP with sanitization — 32 skills (minor to moderate text edits)

These work standalone. Need ECC/Superpowers brand mentions replaced with generic language.

### Minor cleanup (find-replace, ~1 min each)

| # | Skill | Change |
|---|-------|--------|
| 1 | `agent-introspection-debugging` | "narrower ECC skill" → "a more specific skill" |
| 2 | `coding-standards` | "narrower ECC skill" → "a more specific skill" |
| 3 | `council` | "ECC 2.0" in example → "the product" |
| 4 | `customer-billing-ops` | "ECC or website" → "product or website" |
| 5 | `email-ops` | "ECC-native skills" → "related skills" |
| 6 | `finance-billing-ops` | "ECC-native skills" → "related skills" |
| 7 | `frontend-slides` | "Related ECC Skills" header → "Related Skills" |
| 8 | `iterative-retrieval` | Remove "Agent definitions bundled with ECC" line |
| 9 | `messages-ops` | "ECC-native skills" → "related skills" |
| 10 | `research-ops` | "ECC-native skills" → "related skills" |
| 11 | `terminal-ops` | "ECC-native skills" → "related skills" |
| 12 | `safety-guard` | Remove "Pair with observability risk scoring in ECC 2.0" line |
| 13 | `click-path-audit` | Remove `superpowers:` cross-reference |
| 14 | `systematic-debugging` | Remove `superpowers:` cross-references |
| 15 | `test-driven-development` | Remove `superpowers:` cross-references |
| 16 | `canary-watch` | Remove `~/.claude/canary-watch.log` line |
| 17 | `repo-scan` | `~/.claude/skills/repo-scan` → generic skill path |
| 18 | `agent-payment-x402` | `~/.claude.json` → generic MCP config path |
| 19 | `fal-ai-media` | `~/.claude.json` → generic MCP config path |
| 20 | `jira-integration` | `~/.claude.json` → generic MCP config path |
| 21 | `ai-regression-testing` | Clean — no changes actually needed |
| 22 | `verification-before-completion` | Clean — no changes actually needed |

### Moderate cleanup (remove/rewrite a section)

| # | Skill | Change |
|---|-------|--------|
| 23 | `plankton-code-quality` | Remove "Pairing with ECC" + "ECC v1.8 Additions" sections |
| 24 | `brand-voice` | Remove "Affaan / ECC Defaults" section |
| 25 | `product-capability` | Strip ECC skill names from handoff routing |
| 26 | `mle-workflow` | Rewrite "Streamlined ECC path" table column → generic |
| 27 | `content-engine` | Remove "Affaan / ECC voice" reference line |
| 28 | `executing-plans` | Remove "Superpowers works much better..." note |
| 29 | `finishing-a-development-branch` | `~/.config/superpowers/` → generic worktree path |
| 30 | `writing-plans` | Remove `superpowers:` skill cross-references |
| 31 | `receiving-code-review` | Remove Superpowers-specific phrasing |

### Heavy cleanup (core concept OK but platform-coupled implementation)

| # | Skill | Change |
|---|-------|--------|
| 32 | `continuous-learning-v2` | Rewrite `~/.claude/` hook system → generic pattern extraction |
| 33 | `skill-stocktake` | Rewrite `~/.claude/skills/` paths + Agent tool → generic |
| 34 | `team-builder` | Rewrite `claude agents` CLI + discovery → generic dispatch |

---

## ✅ CLEAN — 166 skills (no changes needed)

These function as standalone agent instructions with zero framework dependencies.

accessibility, agent-architecture-audit, agent-eval, agent-harness-construction,
agentic-engineering, ai-first-engineering, ai-regression-testing,
android-clean-architecture, angular-developer, api-connector-builder, api-design,
architecture-decision-records, article-writing, backend-patterns, benchmark,
browser-qa, bun-runtime, carrier-relationship-management, cisco-ios-patterns,
clickhouse-io, code-tour, compose-multiplatform-patterns, connections-optimizer,
content-hash-cache-pattern, continuous-agent-loop, cost-aware-llm-pipeline,
cpp-coding-standards, cpp-testing, crosspost, csharp-testing,
customs-trade-compliance, dart-flutter-patterns, dashboard-builder,
data-scraper-agent, database-migrations, defi-amm-security, deployment-patterns,
design-system, django-celery, django-patterns, django-security, django-tdd,
django-verification, docker-patterns, dotnet-patterns, e2e-testing,
energy-procurement, enterprise-agent-ops, error-handling, evm-token-decimals,
fastapi-patterns, flox-environments, flutter-dart-code-review,
foundation-models-on-device, frontend-patterns, fsharp-testing, git-workflow,
github-ops, golang-patterns, golang-testing, google-workspace-ops,
healthcare-cdss-patterns, healthcare-emr-patterns, healthcare-eval-harness,
healthcare-phi-compliance, hexagonal-architecture, hipaa-compliance,
homelab-network-readiness, homelab-network-setup, homelab-pihole-dns,
homelab-vlan-segmentation, homelab-wireguard-vpn, inventory-demand-planning,
investor-materials, investor-outreach, ios-icon-gen, java-coding-standards,
jpa-patterns, kotlin-coroutines-flows, kotlin-exposed-patterns,
kotlin-ktor-patterns, kotlin-patterns, kotlin-testing, laravel-patterns,
laravel-plugin-discovery, laravel-security, laravel-tdd, laravel-verification,
lead-intelligence, liquid-glass-design, llm-trading-agent-security,
logistics-exception-management, make-interfaces-feel-better, manim-video,
market-research, mcp-server-patterns, motion-advanced, motion-foundations,
motion-patterns, motion-ui, mysql-patterns, nestjs-patterns,
netmiko-ssh-automation, network-bgp-diagnostics, network-config-validation,
network-interface-health, nextjs-turbopack, nodejs-keccak256,
nutrient-document-processing, nuxt4-patterns, openclaw-persona-forge,
perl-patterns, perl-security, perl-testing, postgres-patterns, prisma-patterns,
product-lens, production-audit, production-scheduling, python-patterns,
python-testing, pytorch-patterns, quality-nonconformance, quarkus-patterns,
quarkus-security, quarkus-tdd, quarkus-verification, ralphinho-rfc-pipeline,
recsys-pipeline-architect, redis-patterns, regex-vs-llm-structured-text,
remotion-video-creation, returns-reverse-logistics, rust-patterns, rust-testing,
santa-method, scientific-db-pubmed-database, scientific-db-uspto-database,
scientific-pkg-gget, scientific-thinking-literature-review,
scientific-thinking-scholar-evaluation, security-bounty-hunter, security-review,
seo, social-graph-ranker, springboot-patterns, springboot-security,
springboot-tdd, springboot-verification, swift-actor-persistence,
swift-concurrency-6-2, swift-protocol-di-testing, swiftui-patterns, tdd-workflow,
tinystruct-patterns, token-budget-advisor, ui-demo, ui-to-vue,
verification-before-completion, verification-loop, video-editing, videodb,
visa-doc-translate, vite-patterns, windows-desktop-e2e, x-api

---

## Summary

| Category | Count | Action |
|----------|-------|--------|
| 🔴 PURGE | 26 | Delete from `backend/skills/global/` |
| 🟡 REWRITABLE | 20 | Rewrite to be platform-agnostic, or delete |
| 🟢 KEEP (sanitize) | 32 | Find-replace ECC/Superpowers → generic language |
| ✅ CLEAN | 166 | Ship as-is, no changes needed |
| **Total** | **244** | |

### Quick-win shipping path

Delete 🔴 (26) + park 🟡 (20 — rewrite later or never) → **198 shippable skills**
(166 clean + 32 needing light-to-moderate text edits).

---

## Note on frontmatter `source` field

All 244 global skills carry a `source: ecc` or `source: superpowers` frontmatter field
(plus `sourceLabel: ECC` / `sourceLabel: Superpowers`). This is expected provenance
metadata from the original migration (see `backend/app/agents/skills_catalog.py`) and
is surfaced in the UI as a badge. It is **not** a body-content problem and was
intentionally excluded from this analysis. Whether that provenance label should be
renamed/hidden in the product UI is a separate product decision.

---

## Differences from original analysis (v1 → v2)

The original v1 analysis only searched for the words `ECC`, `GSD`, `Superpowers`,
`OpenDesign` in body text, finding 41 flagged skills. This v2 expanded the search to
include:

- Claude Code platform markers (`.claude/` paths, `claude -p` CLI, hook system)
- `superpowers:` prefixed skill cross-references
- MCP config paths (`~/.claude.json`)
- Manual verification of each skill's actual portability

This caught **37 additional problematic skills** not flagged in v1 — mostly Claude Code
platform-specific skills that don't mention "ECC" by name but depend on Claude Code
infrastructure that this product doesn't have.
