# Skills Import List — VelocityAI Aligned (Final)

Generated: 2026-08-05  
Source Root: `/Users/bilala/Developer/Learning/AI/placeholder/repos/`  
Target Root: `VELOCITY-AI/backend/skills/global/`

## IsCompatible Criteria

- **1** = Standalone knowledge/patterns SKILL.md. No external tools, MCP servers, CLI commands, or platform-specific hooks. Can be injected as system prompt context to any VelocityAI agent.
- **0** = Requires Claude Code CLI, MCP servers, SubAgent dispatch, API keys, webhooks, or platform wiring that VelocityAI doesn't natively support. Needs adaptation before import.

---

## Supported Workflows + Proposed Future Workflows

### Current Workflows

| Workflow | Purpose |
|----------|---------|
| `app_builder` | Generate full-stack applications |
| `prototype` | Generate interactive HTML prototypes |
| `ppt` | Generate presentations from briefs |
| `dotnet_to_azure` | .NET modernization + Azure migration |
| `mulesoft_to_springboot` | MuleSoft → Spring Boot migration |
| `user_stories` | Generate user stories from requirements |
| `chat` | Guided discovery, requirements, UI design |
| `reverse_engineer` | Analyze existing codebases |
| `custom` | Flexible enterprise workflows |

### Proposed Future Workflows

| Proposed Workflow | Purpose | Skills Required |
|----------|---------|---|
| `security_audit` | Full codebase security review | Threat Modeling, Security Review, Auth Patterns |
| `test_generation` | Generate test suites from code | TDD, E2E, Load Testing, JS/Python Testing |
| `api_modernization` | Monolith → microservices | Microservices, CQRS, Event Sourcing, API Design |
| `documentation` | Generate architecture docs, ADRs | ADR Framework, Codebase Onboarding |
| `performance_review` | Analyze + optimize performance | Load Testing, Observability, Benchmarking |
| `code_review` | Multi-dimensional code review | Code Review, Refactoring, Code Simplification |
| `cloud_migration` | AWS/Azure/GCP infra generation | Terraform, Kubernetes, AWS Patterns |
| `sdlc_governance` | Full SDLC compliance audit | SDLC Governance, Compliance, Audit |

---

## Categories

| Category | After Import | Purpose |
|----------|---:|---------|
| **planning** | ~50 | Architecture, design, strategy |
| **testing** | ~60 | TDD, verification, QA, load testing |
| **workflow** | ~45 | Automation, pipelines, execution |
| **security** | ~28 | Hardening, compliance, auditing |
| **debugging** | ~20 | Troubleshooting, diagnostics |
| **collaboration** | ~12 | Team coordination, code review |
| **research** (NEW) | ~7 | Codebase analysis, market research |
| **specialist** (NEW) | ~15 | Tech-specific deep expertise roles |

---

## §1 — App Builder & Code Generation

| Skill | Category | Source | Destination | Agent Groups | IsCompatible |
|---|---|---|---|---|:---:|
| FastAPI Patterns | testing | `repos/ecc/skills/fastapi-patterns/` | `backend/skills/global/fastapi-patterns/` | App Builder, App Compliance | 1 |
| React Patterns | testing | `repos/ecc/skills/react-patterns/` | `backend/skills/global/react-patterns/` | App Builder, Prototype | 1 |
| Next.js + Turbopack | debugging | `repos/ecc/skills/nextjs-turbopack/` | `backend/skills/global/nextjs-turbopack/` | App Builder, Prototype | 1 |
| TypeScript Advanced | planning | `repos/awesome-claude-code-toolkit/skills/typescript-advanced/` | `backend/skills/global/typescript-advanced/` | App Builder, Prototype | 1 |
| Hexagonal Architecture | testing | `repos/ecc/skills/hexagonal-architecture/` | `backend/skills/global/hexagonal-architecture/` | App Builder | 1 |
| API Design | workflow | `repos/ecc/skills/api-design/` | `backend/skills/global/api-design/` | App Builder, MuleSoft | 1 |
| Backend Patterns | workflow | `repos/ecc/skills/backend-patterns/` | `backend/skills/global/backend-patterns/` | App Builder | 1 |
| PostgreSQL Patterns | security | `repos/ecc/skills/postgres-patterns/` | `backend/skills/global/postgres-patterns/` | App Builder | 1 |
| Database Migrations | testing | `repos/ecc/skills/database-migrations/` | `backend/skills/global/database-migrations/` | App Builder | 1 |
| Docker Patterns | security | `repos/ecc/skills/docker-patterns/` | `backend/skills/global/docker-patterns/` | App Builder, App Compliance | 1 |
| Python Patterns | planning | `repos/ecc/skills/python-patterns/` | `backend/skills/global/python-patterns/` | App Builder, .NET/Azure, MuleSoft | 1 |
| Domain-Driven Design | planning | *fallback: `~/.agents/skills/eng-domain-driven-design/`* | `backend/skills/global/domain-driven-design/` | App Builder | 1 |
| Microservices Patterns | planning | `repos/wshobson-agents/plugins/backend-development/skills/microservices-patterns/` | `backend/skills/global/microservices-patterns/` | App Builder | 1 |
| CQRS Implementation | planning | `repos/wshobson-agents/plugins/backend-development/skills/cqrs-implementation/` | `backend/skills/global/cqrs-implementation/` | App Builder | 1 |
| Workflow Orchestration | workflow | `repos/wshobson-agents/plugins/backend-development/skills/workflow-orchestration-patterns/` | `backend/skills/global/workflow-orchestration/` | App Builder, MuleSoft | 1 |
| Event Store Design | planning | `repos/wshobson-agents/plugins/backend-development/skills/event-store-design/` | `backend/skills/global/event-store-design/` | App Builder | 1 |
| Error Handling Patterns | debugging | `repos/ecc/skills/error-handling/` | `backend/skills/global/error-handling/` | App Builder, .NET/Azure, MuleSoft | 1 |
| Saga Orchestration | planning | `repos/wshobson-agents/plugins/backend-development/skills/saga-orchestration/` | `backend/skills/global/saga-orchestration/` | App Builder, MuleSoft | 1 |
| Projection Patterns | planning | `repos/wshobson-agents/plugins/backend-development/skills/projection-patterns/` | `backend/skills/global/projection-patterns/` | App Builder | 1 |

## §2 — Security & Compliance

| Skill | Category | Source | Destination | Agent Groups | IsCompatible |
|---|---|---|---|---|:---:|
| Security Review | security | `repos/ecc/skills/security-review/` | `backend/skills/global/security-review/` | App Compliance, Quality & Security | 1 |
| Security Hardening | security | `repos/awesome-claude-code-toolkit/skills/security-hardening/` | `backend/skills/global/security-hardening/` | App Compliance, .NET/Azure, MuleSoft | 1 |
| Threat Model Analyst | security | `repos/awesome-copilot/skills/threat-model-analyst/` | `backend/skills/global/threat-model-repo/` | Quality & Security | 1 |
| Production Audit | testing | `repos/ecc/skills/production-audit/` | `backend/skills/global/production-audit/` | App Compliance | 1 |
| Kubernetes Patterns | security | `repos/ecc/skills/kubernetes-patterns/` | `backend/skills/global/kubernetes-patterns/` | App Builder, App Compliance | 1 |
| GitHub Actions Hardening | security | *fallback: `~/.agents/skills/sec-github-actions-hardening/`* | `backend/skills/global/gh-actions-hardening/` | App Builder | 1 |
| Auth Implementation Patterns | security | `repos/wshobson-agents/plugins/developer-essentials/skills/auth-implementation-patterns/` | `backend/skills/global/auth-patterns/` | App Compliance, .NET/Azure, MuleSoft | 1 |

## §3 — Testing & Quality

| Skill | Category | Source | Destination | Agent Groups | IsCompatible |
|---|---|---|---|---|:---:|
| Python Testing | testing | `repos/ecc/skills/python-testing/` | `backend/skills/global/python-testing/` | App Compliance | 1 |
| React Testing | testing | `repos/ecc/skills/react-testing/` | `backend/skills/global/react-testing/` | App Compliance, Prototype | 1 |
| TDD Workflow | testing | `repos/ecc/skills/tdd-workflow/` | `backend/skills/global/tdd-workflow/` | App Compliance, .NET/Azure, MuleSoft | 1 |
| E2E Testing | testing | `repos/ecc/skills/e2e-testing/` | `backend/skills/global/e2e-testing/` | App Compliance, Prototype | 1 |
| Benchmark Methodology | debugging | `repos/ecc/skills/benchmark-methodology/` | `backend/skills/global/benchmark-methodology/` | Quality & Security | 1 |
| k6 Load Testing | testing | `repos/claude-code-templates/...` | `backend/skills/global/k6-load-testing/` | Quality & Security | 1 |
| JavaScript Testing Patterns | testing | `repos/wshobson-agents/...` | `backend/skills/global/javascript-testing/` | App Compliance, Prototype | 1 |
| PostgreSQL Table Design | testing | `repos/wshobson-agents/...` | `backend/skills/global/postgresql-table-design/` | App Builder | 1 |
| PostgreSQL Optimization | testing | `repos/claude-code-templates/...` | `backend/skills/global/postgresql-optimization/` | App Builder | 1 |
| Monitoring & Observability | testing | `repos/awesome-claude-code-toolkit/skills/monitoring-observability/` | `backend/skills/global/monitoring-observability/` | App Builder | 1 |
| Harness Engineering | testing | `repos/awesome-copilot/...` | `backend/skills/global/harness-engineering/` | App Compliance | 0 |

## §4 — Prototype & UI Design

| Skill | Category | Source | Destination | Agent Groups | IsCompatible |
|---|---|---|---|---|:---:|
| Frontend Design Direction | planning | `repos/ecc/skills/frontend-design-direction/` | `backend/skills/global/frontend-design-direction/` | Chat Agents, Prototype, PPT | 1 |
| React Performance | debugging | `repos/ecc/skills/react-performance/` | `backend/skills/global/react-performance/` | Prototype, App Builder | 1 |
| Brainstorming | planning | `repos/superpowers/skills/brainstorming/` | `backend/skills/global/brainstorming/` | Chat Agents, Planning & Stories | 1 |
| Make Interfaces Feel Better | planning | `repos/ecc/skills/make-interfaces-feel-better/` | `backend/skills/global/make-interfaces-feel-better/` | Chat Agents, Prototype, PPT | 1 |
| Responsive Design | planning | `repos/wshobson-agents/plugins/ui-design/skills/responsive-design/` | `backend/skills/global/responsive-design/` | Prototype, Chat Agents | 1 |
| Design System Patterns | planning | `repos/wshobson-agents/plugins/ui-design/skills/design-system-patterns/` | `backend/skills/global/design-system-patterns/` | Prototype, App Builder | 1 |
| Interaction Design | planning | `repos/wshobson-agents/plugins/ui-design/skills/interaction-design/` | `backend/skills/global/interaction-design/` | Prototype, Chat Agents | 1 |
| Visual Design Foundations | planning | `repos/wshobson-agents/plugins/ui-design/skills/visual-design-foundations/` | `backend/skills/global/visual-design-foundations/` | Prototype, PPT | 1 |
| Accessibility Compliance | security | `repos/wshobson-agents/plugins/ui-design/skills/accessibility-compliance/` | `backend/skills/global/accessibility-compliance/` | Prototype, App Compliance | 1 |
| Web Component Design | planning | `repos/wshobson-agents/plugins/ui-design/skills/web-component-design/` | `backend/skills/global/web-component-design/` | Prototype, App Builder | 1 |

## §5 — DevOps & Cloud Infrastructure

| Skill | Category | Source | Destination | Agent Groups | IsCompatible |
|---|---|---|---|---|:---:|
| Deployment Patterns | workflow | `repos/ecc/skills/deployment-patterns/` | `backend/skills/global/deployment-patterns/` | App Builder | 1 |
| Automation Audit Ops | workflow | `repos/ecc/skills/automation-audit-ops/` | `backend/skills/global/automation-audit-ops/` | App Builder | 0 |
| Terraform Module Library | workflow | `repos/wshobson-agents/...` | `backend/skills/global/terraform-modules/` | App Builder | 1 |
| AWS Cloud Patterns | workflow | `repos/awesome-claude-code-toolkit/skills/aws-cloud-patterns/` | `backend/skills/global/aws-cloud-patterns/` | App Builder, .NET/Azure | 1 |
| GitLab CI Patterns | workflow | `repos/wshobson-agents/...` | `backend/skills/global/gitlab-ci-patterns/` | App Builder | 1 |

## §6 — Code Quality & Refactoring

| Skill | Category | Source | Destination | Agent Groups | IsCompatible |
|---|---|---|---|---|:---:|
| Refactor Plan | collaboration | `repos/awesome-copilot/skills/refactor-plan/` | `backend/skills/global/refactor-plan/` | App Builder, Research & Analysis | 1 |
| Code Review (PostgreSQL) | collaboration | `repos/awesome-copilot/skills/postgresql-code-review/` | `backend/skills/global/postgresql-code-review/` | App Builder, Quality & Security | 1 |
| Code Review (SQL) | collaboration | `repos/awesome-copilot/skills/sql-code-review/` | `backend/skills/global/sql-code-review/` | App Builder, Quality & Security | 1 |
| Code Simplifier | workflow | *fallback: `~/.agents/skills/eng-code-simplifier/`* | `backend/skills/global/code-simplifier/` | App Builder, Research & Analysis | 1 |

## §7 — Planning & User Stories

| Skill | Category | Source | Destination | Agent Groups | IsCompatible |
|---|---|---|---|---|:---:|
| Product Capability | planning | `repos/ecc/skills/product-capability/` | `backend/skills/global/product-capability/` | Planning & Stories | 1 |
| Product Lens | planning | `repos/ecc/skills/product-lens/` | `backend/skills/global/product-lens/` | Planning & Stories, Chat Agents | 1 |
| Blueprint | planning | `repos/ecc/skills/blueprint/` | `backend/skills/global/blueprint/` | Planning & Stories | 0 |
| Feature Design Assistant | planning | *fallback: `~/.agents/skills/role-feature-design-assistant/`* | `backend/skills/global/feature-design-assistant/` | Chat Agents, Planning & Stories | 1 |

## §8 — Research & Documentation

| Skill | Category | Source | Destination | Agent Groups | IsCompatible |
|---|---|---|---|---|:---:|
| Architecture Decision Records | planning | `repos/ecc/skills/architecture-decision-records/` | `backend/skills/global/architecture-decision-records/` | Research & Analysis, Documentation | 1 |
| Codebase Onboarding | planning | `repos/ecc/skills/codebase-onboarding/` | `backend/skills/global/codebase-onboarding/` | Research & Analysis | 1 |
| Market Research | research | `repos/ecc/skills/market-research/` | `backend/skills/global/market-research/` | Research & Analysis | 1 |
| Research Ops | research | `repos/ecc/skills/research-ops/` | `backend/skills/global/research-ops/` | Research & Analysis | 1 |
| Systematic Debugging | debugging | `repos/ecc/skills/systematic-debugging/` | `backend/skills/global/systematic-debugging/` | Research & Analysis | 1 |
| Postmortem Writing | research | `repos/wshobson-agents/plugins/incident-response/skills/postmortem-writing/` | `backend/skills/global/postmortem-writing/` | Documentation | 1 |
| Incident Runbook Templates | research | `repos/wshobson-agents/plugins/incident-response/skills/incident-runbook-templates/` | `backend/skills/global/incident-runbooks/` | Documentation | 1 |

## §9 — .NET Modernization

| Skill | Category | Source | Destination | Agent Groups | IsCompatible |
|---|---|---|---|---|:---:|
| .NET Patterns | planning | `repos/ecc/skills/dotnet-patterns/` | `backend/skills/global/dotnet-patterns/` | .NET/Azure | 1 |
| C# Testing | testing | `repos/ecc/skills/csharp-testing/` | `backend/skills/global/csharp-testing/` | .NET/Azure | 1 |
| Spring Boot Patterns | workflow | `repos/ecc/skills/springboot-patterns/` | `backend/skills/global/springboot-patterns/` | .NET/Azure, MuleSoft | 1 |
| Spring Boot Security | security | `repos/ecc/skills/springboot-security/` | `backend/skills/global/springboot-security/` | .NET/Azure, MuleSoft | 1 |
| .NET Backend (ASP.NET Core) | specialist | *fallback: `~/.agents/skills/role-dotnet-backend-agent.../`* | `backend/skills/global/dotnet-backend-expert/` | .NET/Azure | 1 |

## §10 — MuleSoft Migration

| Skill | Category | Source | Destination | Agent Groups | IsCompatible |
|---|---|---|---|---|:---:|
| Quarkus Patterns | workflow | `repos/ecc/skills/quarkus-patterns/` | `backend/skills/global/quarkus-patterns/` | MuleSoft | 1 |
| Quarkus Security | security | `repos/ecc/skills/quarkus-security/` | `backend/skills/global/quarkus-security/` | MuleSoft | 1 |
| Quarkus TDD | testing | `repos/ecc/skills/quarkus-tdd/` | `backend/skills/global/quarkus-tdd/` | MuleSoft | 1 |
| Java Coding Standards | collaboration | `repos/ecc/skills/java-coding-standards/` | `backend/skills/global/java-coding-standards/` | MuleSoft, .NET/Azure | 1 |

## §11 — Specialist Roles (NEW category)

| Skill | Category | Source | Destination | Agent Groups | IsCompatible |
|---|---|---|---|---|:---:|
| TypeScript Expert | specialist | `repos/claude-code-templates/...` | `backend/skills/global/typescript-expert/` | ALL | 1 |
| Senior Architect | specialist | `repos/claude-code-templates/...` | `backend/skills/global/senior-architect/` | ALL | 1 |
| Backend Architect | specialist | `repos/claude-code-templates/...` | `backend/skills/global/backend-architect/` | App Builder, MuleSoft | 1 |
| Database Architect | specialist | `repos/claude-code-templates/...` | `backend/skills/global/database-architect/` | App Builder | 1 |
| Database Schema Designer | specialist | `repos/claude-code-templates/...` | `backend/skills/global/database-schema-designer/` | App Builder | 1 |
| UX Researcher & Designer | specialist | `repos/claude-code-templates/...` | `backend/skills/global/ux-researcher/` | Prototype, Chat Agents | 1 |
| DevOps IaC Engineer | specialist | `repos/claude-code-templates/...` | `backend/skills/global/devops-iac-engineer/` | App Builder | 1 |
| Kubernetes Architect | specialist | `repos/claude-code-templates/...` | `backend/skills/global/kubernetes-architect/` | App Builder | 1 |
| Security & Compliance Expert | specialist | `repos/claude-code-templates/...` | `backend/skills/global/security-compliance-expert/` | App Compliance | 1 |
| Threat Modeling Expert | specialist | `repos/claude-code-templates/...` | `backend/skills/global/threat-modeling-expert/` | Quality & Security | 1 |
| Observability Engineer | specialist | `repos/claude-code-templates/...` | `backend/skills/global/observability-engineer/` | App Builder | 1 |
| Code Reviewer | specialist | `repos/claude-code-templates/...` | `backend/skills/global/code-reviewer-expert/` | ALL | 1 |
| Accessibility Auditor | specialist | `repos/claude-code-templates/...` | `backend/skills/global/accessibility-auditor/` | Prototype, App Compliance | 1 |
| Product Manager Toolkit | specialist | `repos/claude-code-templates/...` | `backend/skills/global/product-manager-toolkit/` | Planning & Stories | 1 |
| Event Sourcing Architect | specialist | `repos/claude-code-templates/...` | `backend/skills/global/event-sourcing-architect/` | App Builder | 1 |

---

## Velocity-Dev-Work-Focused (Platform Engineering)

| Skill | Category | Source | Destination | Component | IsCompatible |
|---|---|---|---|---|:---:|
| LangChain & LangGraph | ai-agents | `repos/wshobson-agents/plugins/llm-application-dev/skills/langchain-architecture/` | `backend/skills/global/langchain-langgraph/` | execution_engine | 1 |
| PydanticAI | ai-agents | `repos/claude-code-templates/cli-tool/components/skills/ai-research/pydantic-ai/` | `backend/skills/global/pydanticai-agents/` | factory.py | 1 |
| RAG Implementation | ai-agents | `repos/wshobson-agents/plugins/llm-application-dev/skills/rag-implementation/` | `backend/skills/global/rag-implementation/` | context_providers | 1 |
| Eval Harness | ai-agents | `repos/ecc/skills/eval-harness/` | `backend/skills/global/eval-harness/` | evals/ | 0 |
| Subagent-Driven Dev | ai-agents | `repos/superpowers/skills/subagent-driven-development/` | `backend/skills/global/subagent-driven-dev/` | fanout.py | 0 |
| Context Budget | ai-agents | `repos/ecc/skills/context-budget/` | `backend/skills/global/context-budget/` | compaction/ | 0 |
| Prompt Engineering | ai-agents | `repos/awesome-claude-code-toolkit/skills/prompt-engineering/` | `backend/skills/global/prompt-engineering/` | prompts/* | 1 |

---

## Summary

| Metric | Count |
|---|---|
| Total skills in import list | **101** |
| IsCompatible = 1 (ready to import) | **95** |
| IsCompatible = 0 (needs adaptation) | **6** |
| New skills (not in global/ yet) | ~50 |
| Already present (verify/skip) | ~58 |

### Skills marked IsCompatible = 0 (need wiring)

| Skill | Issue | Adaptation needed |
|---|---|---|
| Harness Engineering | References Claude Code hooks/PreToolUse patterns | Strip hook-specific instructions, keep test harness knowledge |
| Blueprint | References Claude Code `/blueprint` slash command | Rewrite as generic planning methodology |
| Automation Audit Ops | References MCP servers, GitHub Actions hooks | Strip MCP-specific inventory, keep audit methodology |
| Eval Harness | References Claude Code session eval, ECC-specific | Adapt to VelocityAI's eval infrastructure |
| Subagent-Driven Dev | 36 refs to Claude Code SubAgent dispatch | Rewrite using VelocityAI's fanout/execution engine terminology |
| Context Budget | References Claude Code context window mechanics | Adapt to VelocityAI's compaction capability |
