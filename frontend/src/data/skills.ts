export interface SkillDef {
  id: string;
  name: string;
  description: string;
  source: "ecc" | "superpowers" | "gsd";
  sourceLabel: string;
  category: "testing" | "debugging" | "planning" | "collaboration" | "security" | "workflow" | "meta";
  content: string;
  compatible_agents: string[];
  tags: string[];
}

export const SKILLS: SkillDef[] = [
  // ── SUPERPOWERS ──────────────────────────────────────────────────────────
  {
    id: "sp-brainstorming",
    name: "Brainstorming",
    description: "Explores user intent and requirements through collaborative dialogue before any implementation. Forces design approval before writing code.",
    source: "superpowers",
    sourceLabel: "Superpowers",
    category: "planning",
    content: `# Brainstorming
Use before any creative work. Ask clarifying questions one at a time, propose 2-3 approaches with trade-offs, present design sections for approval, then write a spec doc before invoking any implementation skill.
Key rules:
- One question per message
- YAGNI ruthlessly — remove unnecessary features
- Present design, get approval before moving on
- Write spec to docs/specs/YYYY-MM-DD-<topic>-design.md`,
    compatible_agents: ["requirements-analyst", "domain-analyst", "app-user-stories", "epic-architect"],
    tags: ["design", "spec", "planning", "requirements"],
  },
  {
    id: "sp-tdd",
    name: "Test-Driven Development",
    description: "Enforces RED-GREEN-REFACTOR cycle. Write failing test first, watch it fail, write minimal code to pass. No production code without a failing test.",
    source: "superpowers",
    sourceLabel: "Superpowers",
    category: "testing",
    content: `# Test-Driven Development
The Iron Law: NO PRODUCTION CODE WITHOUT A FAILING TEST FIRST.
Cycle: RED (write failing test) → verify it fails → GREEN (minimal code) → verify it passes → REFACTOR → repeat.
- Delete any code written before the test. No exceptions.
- Watch the test fail before implementing — proves it tests the right thing.
- Write minimal code to pass. Don't add features beyond the test.`,
    compatible_agents: ["app-test-implementation", "app-code-generator", "app-feature-implementation", "mulesoft-test-implementation", "dotnet-test-implementation", "mulesoft-feature-coding", "dotnet-feature-coding"],
    tags: ["tdd", "testing", "red-green-refactor", "quality"],
  },
  {
    id: "sp-writing-plans",
    name: "Writing Plans",
    description: "Breaks approved designs into bite-sized implementation tasks (2-5 min each) with exact file paths, complete code, and verification steps.",
    source: "superpowers",
    sourceLabel: "Superpowers",
    category: "planning",
    content: `# Writing Plans
After design approval, break work into tasks small enough for a fresh subagent context.
Each task must have: exact file paths, complete code snippets, verification steps.
Emphasise TDD, YAGNI, DRY. Tasks should be independently executable.`,
    compatible_agents: ["epic-architect", "app-user-stories", "app-system-design"],
    tags: ["planning", "tasks", "implementation", "decomposition"],
  },
  {
    id: "sp-subagent-driven-dev",
    name: "Subagent-Driven Development",
    description: "Dispatches a fresh subagent per task with two-stage review: spec compliance then code quality. Fast iteration with human checkpoints.",
    source: "superpowers",
    sourceLabel: "Superpowers",
    category: "workflow",
    content: `# Subagent-Driven Development
Dispatch one fresh subagent per task. Each subagent gets: the plan task, relevant context only, two review stages.
Stage 1: Does output match the spec?
Stage 2: Is the code quality acceptable?
Human checkpoint after each batch. Continue only on approval.`,
    compatible_agents: ["app-code-generator", "app-feature-implementation", "mulesoft-springboot-scaffold", "mulesoft-feature-coding", "dotnet-modernization", "dotnet-feature-coding"],
    tags: ["subagents", "orchestration", "parallel", "workflow"],
  },
  {
    id: "sp-systematic-debugging",
    name: "Systematic Debugging",
    description: "4-phase root cause process: reproduce, isolate, hypothesise, verify. Evidence over guessing. Never fix without understanding the cause.",
    source: "superpowers",
    sourceLabel: "Superpowers",
    category: "debugging",
    content: `# Systematic Debugging
Phase 1 — Reproduce: get a reliable, minimal reproduction.
Phase 2 — Isolate: narrow to the smallest failing unit.
Phase 3 — Hypothesise: form one hypothesis at a time, test it.
Phase 4 — Verify: confirm fix doesn't break other tests.
Never guess. Evidence first. Write a failing test before fixing.`,
    compatible_agents: ["app-code-compliance", "app-test-compliance", "mulesoft-validation", "dotnet-validation"],
    tags: ["debugging", "root-cause", "systematic", "quality"],
  },
  {
    id: "sp-code-review",
    name: "Requesting Code Review",
    description: "Pre-review checklist before submitting. Reviews against plan, reports issues by severity. Critical issues block progress.",
    source: "superpowers",
    sourceLabel: "Superpowers",
    category: "collaboration",
    content: `# Requesting Code Review
Before review: run all tests, check coverage, verify no lint errors.
Review against: the plan spec, security checklist, test coverage.
Severity levels: Critical (blocks), Major (should fix), Minor (nice to have).
Critical issues must be resolved before proceeding.`,
    compatible_agents: ["app-code-compliance", "backlog-reviewer", "app-test-compliance", "mulesoft-code-compliance", "dotnet-code-compliance"],
    tags: ["review", "quality", "checklist", "collaboration"],
  },
  {
    id: "sp-finishing-branch",
    name: "Finishing a Development Branch",
    description: "Verifies all tests pass, presents merge/PR/keep/discard options, cleans up worktree. Structured branch completion workflow.",
    source: "superpowers",
    sourceLabel: "Superpowers",
    category: "workflow",
    content: `# Finishing a Development Branch
1. Run full test suite — all must pass.
2. Check coverage meets threshold.
3. Review diff for unintended changes.
4. Options: merge to main, open PR, keep branch, discard.
5. Clean up git worktree if used.
6. Tag release if milestone complete.`,
    compatible_agents: ["app-devops", "app-sdlc-governance", "mulesoft-sdlc-governance", "dotnet-sdlc-governance"],
    tags: ["git", "branch", "merge", "pr", "devops"],
  },

  // ── EVERYTHING CLAUDE CODE (ECC) ─────────────────────────────────────────
  {
    id: "ecc-tdd-workflow",
    name: "TDD Workflow",
    description: "Full TDD with 80%+ coverage requirement. Unit, integration, and E2E tests. Git checkpoints after each RED/GREEN/REFACTOR stage.",
    source: "ecc",
    sourceLabel: "ECC",
    category: "testing",
    content: `# TDD Workflow (ECC)
Always write tests first. Coverage minimum: 80% (unit + integration + E2E).
Steps: write user journeys → generate test cases → run (they fail) → implement → run (they pass) → refactor → verify coverage.
Git checkpoint after RED, after GREEN, after REFACTOR.
Test types: Unit (Jest/Vitest), Integration (API/DB), E2E (Playwright).`,
    compatible_agents: ["app-test-implementation", "app-code-generator", "app-feature-implementation", "mulesoft-test-implementation", "dotnet-test-implementation"],
    tags: ["tdd", "coverage", "jest", "playwright", "e2e"],
  },
  {
    id: "ecc-security-review",
    name: "Security Review",
    description: "OWASP Top 10 audit, secrets detection, permission auditing, injection analysis. Comprehensive security checklist for every release.",
    source: "ecc",
    sourceLabel: "ECC",
    category: "security",
    content: `# Security Review (ECC)
Checklist: OWASP Top 10, secrets in code/config, SQL injection, XSS, CSRF, auth/authz gaps, dependency vulnerabilities, insecure defaults.
Run: SAST scan, dependency audit (npm audit / pip audit), secrets scan.
Block release on: critical CVEs, hardcoded secrets, missing auth checks.`,
    compatible_agents: ["app-security-architecture", "security-auditor", "mulesoft-security-architecture", "dotnet-security-architecture", "app-code-compliance"],
    tags: ["security", "owasp", "sast", "secrets", "audit"],
  },
  {
    id: "ecc-backend-patterns",
    name: "Backend Patterns",
    description: "API design, database patterns, caching strategies, error handling, and service layer best practices for production backends.",
    source: "ecc",
    sourceLabel: "ECC",
    category: "workflow",
    content: `# Backend Patterns (ECC)
API: RESTful conventions, consistent error envelopes, pagination, idempotency keys.
Database: connection pooling, query budgets, index strategy, migration tooling.
Caching: cache-aside pattern, TTL strategy, cache invalidation.
Error handling: structured errors, retry with backoff, circuit breaker.`,
    compatible_agents: ["app-code-generator", "app-feature-implementation", "app-api-design", "app-database-design", "mulesoft-feature-coding", "dotnet-feature-coding"],
    tags: ["api", "database", "caching", "backend", "patterns"],
  },
  {
    id: "ecc-frontend-patterns",
    name: "Frontend Patterns",
    description: "React/Next.js patterns, component architecture, state management, accessibility, and performance best practices.",
    source: "ecc",
    sourceLabel: "ECC",
    category: "workflow",
    content: `# Frontend Patterns (ECC)
Components: single responsibility, composition over inheritance, controlled vs uncontrolled.
State: local state first, lift only when needed, avoid prop drilling with context.
Performance: code splitting, lazy loading, memoisation only when measured.
Accessibility: semantic HTML, ARIA labels, keyboard navigation, colour contrast.`,
    compatible_agents: ["app-ux-design", "html-prototype-builder", "prototype-polisher", "app-code-generator"],
    tags: ["react", "nextjs", "components", "accessibility", "frontend"],
  },
  {
    id: "ecc-api-design",
    name: "API Design",
    description: "REST API design patterns, OpenAPI 3.1 contracts, pagination, error responses, versioning policy, and async event contracts.",
    source: "ecc",
    sourceLabel: "ECC",
    category: "workflow",
    content: `# API Design (ECC)
REST conventions: nouns not verbs, plural resources, nested for ownership.
Error envelope: { error: { code, message, details } } — consistent across all endpoints.
Pagination: cursor-based for large sets, offset for small.
Versioning: URL path (/v1/) for breaking changes, headers for minor.
OpenAPI 3.1: document every endpoint, request/response schema, error codes.`,
    compatible_agents: ["app-api-design", "app-code-generator", "mulesoft-decomposition"],
    tags: ["api", "openapi", "rest", "contracts", "versioning"],
  },
  {
    id: "ecc-deployment-patterns",
    name: "Deployment Patterns",
    description: "CI/CD pipeline design, Docker best practices, health checks, rollback strategies, and zero-downtime deployment.",
    source: "ecc",
    sourceLabel: "ECC",
    category: "workflow",
    content: `# Deployment Patterns (ECC)
CI/CD: lint → test → build → security scan → deploy to staging → smoke test → promote to prod.
Docker: multi-stage builds, non-root user, minimal base image, health check endpoint.
Rollback: blue/green or canary, feature flags for gradual rollout.
Health checks: /health (liveness), /ready (readiness), structured JSON response.`,
    compatible_agents: ["app-devops", "app-infra-generator", "mulesoft-aws-infra", "dotnet-azure-bicep"],
    tags: ["cicd", "docker", "deployment", "rollback", "devops"],
  },
  {
    id: "ecc-e2e-testing",
    name: "E2E Testing",
    description: "Playwright E2E patterns, Page Object Model, critical user flow coverage, and CI integration for browser automation.",
    source: "ecc",
    sourceLabel: "ECC",
    category: "testing",
    content: `# E2E Testing (ECC)
Use Playwright. Page Object Model for reusable selectors.
Cover: critical user flows, auth flows, payment flows, error states.
Selectors: prefer data-testid, then ARIA roles, avoid CSS classes.
CI: run on every PR, fail fast on critical flow failures.
Parallelise across browsers: chromium, firefox, webkit.`,
    compatible_agents: ["app-test-implementation", "app-test-compliance", "mulesoft-test-implementation", "dotnet-test-implementation"],
    tags: ["playwright", "e2e", "browser", "automation", "testing"],
  },
  {
    id: "ecc-search-first",
    name: "Search First",
    description: "Research-before-coding workflow. Always look up current docs, existing patterns, and prior art before writing new code.",
    source: "ecc",
    sourceLabel: "ECC",
    category: "workflow",
    content: `# Search First (ECC)
Before writing any code: search for existing solutions, check official docs, look for prior art in the codebase.
Steps: 1) Define what you need. 2) Search docs/codebase. 3) Evaluate options. 4) Only then implement.
Avoids reinventing the wheel, outdated patterns, and security anti-patterns.`,
    compatible_agents: ["domain-analyst", "market-research-agent", "app-system-design", "mulesoft-inventory", "dotnet-inventory"],
    tags: ["research", "docs", "discovery", "workflow"],
  },
  {
    id: "ecc-springboot-patterns",
    name: "Spring Boot Patterns",
    description: "Java Spring Boot 3 architecture patterns, dependency injection, JPA/Hibernate, REST controllers, and production-ready configuration.",
    source: "ecc",
    sourceLabel: "ECC",
    category: "workflow",
    content: `# Spring Boot Patterns (ECC)
Architecture: layered (controller → service → repository), avoid fat controllers.
DI: constructor injection only, avoid field injection.
JPA: use projections for read-heavy queries, avoid N+1 with @EntityGraph.
Config: externalise all config via application.yml + env vars, never hardcode.
Actuator: expose /health, /info, /metrics for observability.`,
    compatible_agents: ["mulesoft-springboot-scaffold", "mulesoft-feature-coding", "mulesoft-test-implementation"],
    tags: ["java", "spring-boot", "jpa", "microservices", "backend"],
  },
  {
    id: "ecc-continuous-learning",
    name: "Continuous Learning",
    description: "Automatically extracts reusable patterns from sessions into skills. Builds institutional knowledge over time.",
    source: "ecc",
    sourceLabel: "ECC",
    category: "meta",
    content: `# Continuous Learning (ECC)
After each session: identify patterns that worked well, extract as reusable skill snippets.
Store in skills/ directory with YAML frontmatter.
Review periodically: promote high-confidence patterns, prune outdated ones.
Share across team via skills repository.`,
    compatible_agents: ["domain-analyst", "epic-architect", "app-user-stories", "requirements-analyst"],
    tags: ["learning", "patterns", "knowledge", "meta"],
  },

  // ── GET SHIT DONE (GSD) ──────────────────────────────────────────────────
  {
    id: "gsd-new-project",
    name: "GSD: New Project",
    description: "Questions → research → requirements → roadmap. Structured project kickoff that produces PROJECT.md, REQUIREMENTS.md, and ROADMAP.md.",
    source: "gsd",
    sourceLabel: "GSD",
    category: "planning",
    content: `# GSD: New Project
Run at project start. Produces: PROJECT.md (vision), REQUIREMENTS.md (scope), ROADMAP.md (phases).
Process: ask clarifying questions → research → draft requirements → propose roadmap → get approval.
Output files survive session boundaries — every new session loads them for context.`,
    compatible_agents: ["domain-analyst", "requirements-analyst", "epic-architect"],
    tags: ["kickoff", "requirements", "roadmap", "planning"],
  },
  {
    id: "gsd-plan-phase",
    name: "GSD: Plan Phase",
    description: "Research + plan + verify loop for a single roadmap phase. Each plan is small enough to execute in a fresh 200k-token context window.",
    source: "gsd",
    sourceLabel: "GSD",
    category: "planning",
    content: `# GSD: Plan Phase
For phase N: research → create plan → verify plan passes quality checks → iterate until approved.
Each plan task: small enough for one subagent context, has clear success criteria.
Output: PHASES/<N>/PLAN.md with atomic tasks ready for execution.`,
    compatible_agents: ["epic-architect", "app-user-stories", "app-system-design"],
    tags: ["phase", "planning", "tasks", "decomposition"],
  },
  {
    id: "gsd-execute-phase",
    name: "GSD: Execute Phase",
    description: "Runs plans in parallel waves. Each executor gets a fresh context. Each task gets its own atomic commit. Main context stays clean.",
    source: "gsd",
    sourceLabel: "GSD",
    category: "workflow",
    content: `# GSD: Execute Phase
Execute tasks from PLAN.md in parallel waves where possible.
Each task: fresh subagent context, atomic git commit on completion.
Main context window stays at 30-40% — heavy work in subagents.
On failure: diagnose, create fix plan, re-execute. Don't debug manually.`,
    compatible_agents: ["app-code-generator", "app-feature-implementation", "mulesoft-feature-coding", "dotnet-feature-coding"],
    tags: ["execution", "parallel", "subagents", "commits"],
  },
  {
    id: "gsd-verify-work",
    name: "GSD: Verify Work",
    description: "Walk through what was built. Broken items get a diagnosed fix plan ready for immediate re-execution. No manual debugging.",
    source: "gsd",
    sourceLabel: "GSD",
    category: "testing",
    content: `# GSD: Verify Work
After execution: walk through each task's output against its success criteria.
For failures: diagnose root cause, write fix plan, mark for re-execution.
Don't debug manually — generate a fix plan and run execute again.
Output: PHASES/<N>/VERIFY.md with pass/fail per task and fix plans.`,
    compatible_agents: ["app-test-compliance", "backlog-reviewer", "mulesoft-validation", "dotnet-validation"],
    tags: ["verification", "quality", "testing", "acceptance"],
  },
  {
    id: "gsd-ship",
    name: "GSD: Ship",
    description: "Create PR from verified phase work. Archive milestone, tag release, start next milestone fresh with clean context.",
    source: "gsd",
    sourceLabel: "GSD",
    category: "workflow",
    content: `# GSD: Ship
After verify passes: create PR with phase summary, link to VERIFY.md.
PR description: what was built, what was tested, known limitations.
On merge: archive phase artifacts, tag release, update STATE.md.
Start next milestone with /gsd-new-milestone for clean context.`,
    compatible_agents: ["app-devops", "app-sdlc-governance", "mulesoft-sdlc-governance", "dotnet-sdlc-governance"],
    tags: ["pr", "release", "ship", "milestone", "git"],
  },
];

export const SKILL_CATEGORIES = [
  { id: "all", label: "All" },
  { id: "planning", label: "Planning" },
  { id: "testing", label: "Testing" },
  { id: "workflow", label: "Workflow" },
  { id: "security", label: "Security" },
  { id: "debugging", label: "Debugging" },
  { id: "collaboration", label: "Collaboration" },
  { id: "meta", label: "Meta" },
] as const;

export const SKILL_SOURCES = [
  { id: "all", label: "All Sources" },
  { id: "ecc", label: "ECC" },
  { id: "superpowers", label: "Superpowers" },
  { id: "gsd", label: "GSD" },
] as const;
