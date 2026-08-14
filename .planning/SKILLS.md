# Skills — Architecture Decision Record & History

This file is the canonical record of all decisions, additions, removals, and changes
to the global skills catalog (`backend/skills/global/`).

---

## ADR-001: Purge framework-dependent skills from global catalog

**Date:** 2025-08-05
**Status:** Accepted
**Decision maker:** bilala

### Context

The global skills catalog (`backend/skills/global/`) was bulk-migrated from the
**Everything Claude Code (ECC)** and **Superpowers** open-source skill ecosystems.
These ecosystems assumed the agent runs inside:

- **ECC** — a Claude Code plugin with its own repo, install flow, hook system,
  commands, agents directory, and `/orchestrate` dispatch surface
- **Superpowers** — a skill-loading framework with a `Skill` invocation tool,
  `superpowers:` cross-references, and `docs/superpowers/` directory conventions
- **Claude Code** — Anthropic's CLI IDE with `.claude/` config directory,
  `claude -p` pipe mode, `PreToolUse`/`PostToolUse` hooks, and `CLAUDE.md` kernel

This product (Flowin/VelocityAI) is **none of these**. It is its own AI SaaS platform
with its own agent runtime, skill attachment system, and execution engine. Skills that
reference ECC/Superpowers/Claude Code infrastructure produce broken or misleading
instructions when attached to an agent here.

### Decision

**Delete 46 skills** from `backend/skills/global/` that cannot function without their
parent framework:

- **26 PURGE** — Skills whose entire purpose IS operating within ECC/Superpowers/Claude
  Code. Zero salvageable standalone content.
- **20 REWRITABLE** — Skills with useful generic methodology buried under heavy
  framework framing. Deleted now; may be rewritten and re-added later if needed.

**Keep 198 skills:**
- 166 are completely clean (no framework references)
- 32 need minor-to-moderate text sanitization (replacing "ECC-native" with "related
  skills", removing `.claude/` paths, etc.) — tracked separately

### Skills deleted

#### PURGE (26) — entirely framework-dependent, no standalone value

| Skill | Reason for deletion |
|-------|-------------------|
| `configure-ecc` | ECC repo clone/install flow |
| `ecc-guide` | ECC repository Q&A/navigation |
| `ecc-tools-cost-audit` | ECC-Tools GitHub App billing audit |
| `hermes-imports` | Hermes→ECC workflow porting |
| `plan-orchestrate` | ECC `/orchestrate` command routing with `ECC_MODE` detection |
| `agent-sort` | ECC component classifier (skills/commands/rules/hooks → install buckets) |
| `skill-scout` | ECC skill ecosystem directory search |
| `using-superpowers` | Superpowers meta-skill for invoking `Skill` tool |
| `hookify-rules` | Claude Code `.claude/` hook rule authoring |
| `nanoclaw-repl` | ECC REPL built on `claude -p` pipe mode |
| `ck` | Claude Code context keeper (`~/.claude/skills/ck/`) |
| `claude-devfleet` | Claude Code MCP devfleet (`claude mcp add devfleet`) |
| `cost-tracking` | Claude Code session cost tracker (`~/.claude-cost-tracker/`) |
| `context-budget` | Claude Code config scanner (CLAUDE.md, agents/, skills/, .mcp.json) |
| `eval-harness` | Claude Code `.claude/evals/` evaluation system |
| `agentic-os` | Claude Code as OS architecture (CLAUDE.md kernel, `.claude/commands/`) |
| `knowledge-ops` | Claude Code project memory (`~/.claude/projects/*/memory/`) |
| `gan-style-harness` | Multi-agent via `claude -p --model opus` CLI invocations |
| `skill-comply` | Skill compliance testing via `claude -p` stream-json |
| `continuous-learning` | Hook-based pattern learning (`~/.claude/skills/learned/`) |
| `strategic-compact` | Claude Code `/compact` command + suggest-compact hook |
| `rules-distill` | ECC rules directory structure + Agent subagent dispatch |
| `writing-skills` | ECC/Superpowers skill authoring with `superpowers:` deps |
| `subagent-driven-development` | Chains 6+ `superpowers:*` skills as hard dependencies |
| `security-scan` | Claude Code `.claude/` infrastructure auditing |
| `brainstorming` | Superpowers directory paths (`docs/superpowers/specs/`) + skill deps |

#### REWRITABLE (20) — useful core content but too coupled to ship as-is

| Skill | Salvageable concept | Why deleted (for now) |
|-------|--------------------|--------------------|
| `workspace-surface-audit` | Workspace capability audit | Framed as "ECC-native coverage" comparison |
| `prompt-optimizer` | 6-phase prompt improvement | Routes to ECC commands/skills |
| `blueprint` | Multi-session planning methodology | Contains ECC repo clone/install instructions |
| `autonomous-agent-harness` | Persistent agent loop architecture | Framed as "replacing Hermes with ECC" |
| `automation-audit-ops` | Automation inventory/merge/cut | Consolidates into "one canonical ECC lane" |
| `unified-notifications-ops` | Notification routing/dedup | "ECC-native orchestration" preference |
| `autonomous-loops` | Loop patterns (sequential, continuous PR) | ECC mapping table + `/verify` command |
| `project-flow-ops` | Issue/PR triage workflow | "ECC 1.x/2.0 program lanes" |
| `frontend-design-direction` | Frontend design guidance | "ECC-specific design-direction salvage" framing |
| `gateguard` | Pre-action fact-forcing quality gate | ECC hook install as primary path |
| `dmux-workflows` | Multi-agent tmux orchestration | "ECC Helper" section as load-bearing |
| `dispatching-parallel-agents` | Parallel task decomposition | Claude Code `Task()` API dispatch |
| `documentation-lookup` | Library doc resolution | Claude Code `~/.claude.json` MCP config |
| `exa-search` | Exa web search patterns | Claude Code `~/.claude.json` MCP config |
| `codebase-onboarding` | 4-phase codebase analysis | Outputs "CLAUDE.md" (Claude Code config) |
| `requesting-code-review` | Code review request workflow | Claude Code Agent dispatch |
| `using-git-worktrees` | Git worktree isolation | Claude Code native tool detection |
| `search-first` | Research-before-coding | `~/.claude/` paths + Agent() syntax |
| `opensource-pipeline` | Fork→sanitize→package | Agent() subagent dispatch |
| `deep-research` | Multi-source parallel research | "Claude Code Task tool" dependency |

### Consequences

- Global catalog reduced from 244 → 198 skills
- All remaining skills can function when injected into any LLM agent's system prompt
  without referencing nonexistent tools or directories
- 32 of the remaining 198 still need minor text sanitization (tracked below)
- If any deleted REWRITABLE skill's methodology is needed later, it can be rewritten
  from scratch using the concept (not the ECC-specific implementation)

### Analysis methodology

Full audit documented in `backend/skills/out-of-order.md`. Searched for:
1. Body-text mentions of `ECC`, `GSD`, `Superpowers`, `OpenDesign`
2. Claude Code platform markers: `~/.claude/`, `.claude/`, `claude -p`, `CLAUDE.md`,
   `CLAUDE_PLUGIN`, `PreToolUse`, `PostToolUse`
3. `superpowers:` prefixed skill cross-references
4. MCP config paths: `~/.claude.json`, `.mcp.json`, `claude mcp add`

---

## Pending: Sanitization of remaining 32 skills

The following skills work standalone but contain minor ECC/Superpowers/Claude Code
references that should be cleaned up in a follow-up pass:

### Minor (find-replace)

- `agent-introspection-debugging` — "narrower ECC skill" → "a more specific skill"
- `coding-standards` — "narrower ECC skill" → "a more specific skill"
- `council` — "ECC 2.0" in example → "the product"
- `customer-billing-ops` — "ECC or website" → "product or website"
- `email-ops` — "ECC-native skills" → "related skills"
- `finance-billing-ops` — "ECC-native skills" → "related skills"
- `frontend-slides` — "Related ECC Skills" → "Related Skills"
- `iterative-retrieval` — remove "Agent definitions bundled with ECC" line
- `messages-ops` — "ECC-native skills" → "related skills"
- `research-ops` — "ECC-native skills" → "related skills"
- `terminal-ops` — "ECC-native skills" → "related skills"
- `safety-guard` — remove "ECC 2.0" reference line
- `click-path-audit` — remove `superpowers:` cross-ref
- `systematic-debugging` — remove `superpowers:` cross-refs
- `test-driven-development` — remove `superpowers:` cross-refs
- `canary-watch` — remove `~/.claude/canary-watch.log` line
- `repo-scan` — genericize `~/.claude/skills/repo-scan` path
- `agent-payment-x402` — `~/.claude.json` → generic config path
- `fal-ai-media` — `~/.claude.json` → generic config path
- `jira-integration` — `~/.claude.json` → generic config path

### Moderate (section removal)

- `plankton-code-quality` — remove "Pairing with ECC" + "ECC v1.8 Additions" sections
- `brand-voice` — remove "Affaan / ECC Defaults" section
- `product-capability` — strip ECC skill names from handoff routing
- `mle-workflow` — rewrite "Streamlined ECC path" table column
- `content-engine` — remove "Affaan / ECC voice" reference
- `executing-plans` — remove "Superpowers works much better..." note
- `finishing-a-development-branch` — `~/.config/superpowers/` → generic path
- `writing-plans` — remove `superpowers:` cross-references
- `receiving-code-review` — remove Superpowers-specific phrasing

### Heavy (platform-coupled implementation)

- `continuous-learning-v2` — rewrite `~/.claude/` hook system → generic
- `skill-stocktake` — rewrite `~/.claude/skills/` paths + Agent tool
- `team-builder` — rewrite `claude agents` CLI + discovery

---

---

## ADR-002: Remove non-English and off-topic skills

**Date:** 2025-08-05
**Status:** Accepted
**Decision maker:** bilala

### Context

After the ADR-001 framework purge (244 → 198), the remaining catalog still contained:

1. **Non-English skills** — Written primarily in Chinese; our platform and user base
   is English-only. Non-English skills confuse the skill browser and produce
   instructions the LLM may not handle consistently.

2. **Off-topic domain skills** — Skills for supply chain, logistics, homelab networking,
   crypto/DeFi trading, video production, social media content, investor outreach,
   personal productivity, and niche mobile platforms. VelocityAI is an enterprise AI
   platform for **software development workflows** (architecture, coding, testing,
   deployment, security). Skills outside this domain dilute the catalog and confuse
   users looking for dev-relevant capabilities.

3. **Empty placeholder skills** — Skills with broken YAML descriptions (`'>'`) that are
   just supply-chain domain stubs with no actionable content for software agents.

### Decision

**Delete 42 additional skills** that are non-English, off-topic for a software
development AI platform, or empty domain placeholders.

### Skills deleted

#### Non-English (1)

| Skill | Language | Reason |
|-------|----------|--------|
| `openclaw-persona-forge` | Chinese | Entirely in Chinese (龙虾灵魂锻造炉). Platform is English-only |

#### Off-topic: Supply chain / logistics / manufacturing (8 empty stubs)

| Skill | Reason |
|-------|--------|
| `carrier-relationship-management` | Supply chain domain, broken description, not software dev |
| `customs-trade-compliance` | International trade compliance, not software dev |
| `energy-procurement` | Energy sector procurement, not software dev |
| `inventory-demand-planning` | Warehouse/inventory domain, not software dev |
| `logistics-exception-management` | Shipping/logistics domain, not software dev |
| `production-scheduling` | Manufacturing scheduling, not software dev |
| `quality-nonconformance` | Manufacturing QA, not software dev |
| `returns-reverse-logistics` | Returns/shipping domain, not software dev |

#### Off-topic: Homelab / personal networking (5)

| Skill | Reason |
|-------|--------|
| `homelab-network-readiness` | Personal homelab setup, not enterprise software dev |
| `homelab-network-setup` | Home network planning, not enterprise software dev |
| `homelab-pihole-dns` | Pi-hole DNS blocker setup, not software dev |
| `homelab-vlan-segmentation` | Home VLAN config, not software dev |
| `homelab-wireguard-vpn` | Personal VPN setup, not software dev |

#### Off-topic: Video production (4)

| Skill | Reason |
|-------|--------|
| `video-editing` | Video editing workflows (FFmpeg, Descript), not software dev |
| `videodb` | Video ingestion/indexing platform, not software dev |
| `manim-video` | Mathematical animation tool, not software dev |
| `remotion-video-creation` | React video rendering, niche creative tool |

#### Off-topic: Social media / content marketing (7)

| Skill | Reason |
|-------|--------|
| `connections-optimizer` | LinkedIn/X network pruning, personal productivity |
| `social-graph-ranker` | Social network graph ranking, not software dev |
| `crosspost` | Multi-platform social posting, not software dev |
| `content-engine` | Social media content creation, not software dev |
| `brand-voice` | Marketing voice profiling, not software dev |
| `article-writing` | Blog/newsletter writing, not software dev |
| `lead-intelligence` | Sales lead pipeline, not software dev |

#### Off-topic: Investor relations / personal (2)

| Skill | Reason |
|-------|--------|
| `investor-materials` | Pitch decks and investor memos, not software dev |
| `investor-outreach` | Cold emails to VCs, not software dev |

#### Off-topic: Crypto / DeFi / blockchain (4)

| Skill | Reason |
|-------|--------|
| `defi-amm-security` | Solidity AMM contract security, niche blockchain |
| `evm-token-decimals` | EVM chain token decimal handling, niche blockchain |
| `llm-trading-agent-security` | Autonomous trading agent security, niche crypto |
| `agent-payment-x402` | x402 crypto payment protocol, niche blockchain |

#### Off-topic: Personal tools / niche (5)

| Skill | Reason |
|-------|--------|
| `visa-doc-translate` | Personal visa document translation, not software dev |
| `email-ops` | Personal email triage/drafting, not software dev |
| `messages-ops` | Personal text message reading, not software dev |
| `google-workspace-ops` | Google Drive/Docs operations, not software dev |
| `x-api` | X/Twitter API posting, social media not software dev |

#### Off-topic: Finance / billing (2)

| Skill | Reason |
|-------|--------|
| `finance-billing-ops` | Revenue/refund operations, business ops not software dev |
| `customer-billing-ops` | Stripe subscription management, business ops |

#### Off-topic: Niche mobile/platform (4)

| Skill | Reason |
|-------|--------|
| `ios-icon-gen` | iOS icon generation, too niche for general platform |
| `liquid-glass-design` | iOS 26 design system, too niche Apple-specific |
| `foundation-models-on-device` | Apple FoundationModels on-device, too niche Apple-specific |
| `tinystruct-patterns` | Obscure Java framework with tiny user base |

### Consequences

- Global catalog reduced from 198 → 156 skills
- All remaining skills are English-language and relevant to software development
- Catalog is focused on what VelocityAI agents actually help with: architecture,
  coding, testing, deployment, security, debugging, and dev collaboration

---

## History

| Date | Action | Count | Details |
|------|--------|-------|---------|
| 2025-08-05 | Initial catalog migration | 244 | Bulk import from ECC/Superpowers catalogs into `backend/skills/global/` |
| 2025-08-05 | Framework dependency audit | — | Full scan documented in `backend/skills/out-of-order.md` |
| 2025-08-05 | Delete PURGE skills (ADR-001) | -26 | Skills entirely dependent on ECC/Superpowers/Claude Code |
| 2025-08-05 | Delete REWRITABLE skills (ADR-001) | -20 | Useful concepts but too framework-coupled to ship |
| 2025-08-05 | Delete non-English + off-topic (ADR-002) | -42 | Non-English, supply chain, homelab, video, social, crypto, personal |
| 2025-08-05 | **Current total** | **156** | Focused software development skill catalog |
