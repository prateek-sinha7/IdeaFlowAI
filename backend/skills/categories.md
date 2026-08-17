# Global Skills Catalog — Categories & Inventory

**Total: 198 skills** across 6 categories
**Location:** `backend/skills/global/`

Skills are user-attachable to **any agent** at runtime. The `category` field determines
where the skill appears in the UI skill library browser. An agent's capabilities are
augmented by whatever skills the user attaches before launching a run.

---

## Categories Overview

| Category | Count | Purpose |
|----------|-------|---------|
| **planning** | 67 | Architecture, design, strategy, and decision-making guidance |
| **testing** | 48 | Test methodologies, TDD, verification, and quality assurance |
| **workflow** | 36 | Process automation, pipelines, content creation, and execution patterns |
| **security** | 21 | Security hardening, compliance, auditing, and threat prevention |
| **debugging** | 17 | Troubleshooting, diagnostics, and root-cause analysis |
| **collaboration** | 9 | Team coordination, communication, and knowledge sharing |

---

## Applicable Agents (84 total)

Skills can be attached to any of these agents for enhanced capabilities:

| Agent Group | Agents | Typical skill categories |
|-------------|--------|--------------------------|
| **App Builder** | app-api-design, app-code-generator, app-database-design, app-devops, app-feature-implementation, app-infra-generator, app-system-design, app-ux-design, app-builder-revision-agent | planning, testing, workflow |
| **App Compliance** | app-code-compliance, app-sdlc-governance, app-security-architecture, app-test-compliance, app-test-implementation | security, testing |
| **Chat Agents** | chat-discovery, chat-ppt, chat-preview, chat-prototype, chat-requirements, chat-ui-design, chat-user-stories | planning, workflow |
| **Prototype** | prototype-analyze, prototype-build, prototype-plan, prototype-specify, prototype-validate, prototype-revision-agent, prototype-revision-validate | planning, testing |
| **PPT** | ppt-brief-analyst, ppt-composer, ppt-validator, ppt-revision-agent, chat-ppt | planning, workflow |
| **.NET/Azure** | dotnet-azure-ai, dotnet-azure-bicep, dotnet-azure-target-mapping, dotnet-code-compliance, dotnet-feature-coding, dotnet-inventory, dotnet-modernization, dotnet-sdlc-governance, dotnet-security-architecture, dotnet-test-compliance, dotnet-test-implementation, dotnet-user-stories, dotnet-validation | planning, testing, security |
| **MuleSoft** | mulesoft-aws-infra, mulesoft-code-compliance, mulesoft-dataweave-translator, mulesoft-decomposition, mulesoft-feature-coding, mulesoft-inventory, mulesoft-sdlc-governance, mulesoft-security-architecture, mulesoft-springboot-scaffold, mulesoft-test-compliance, mulesoft-test-implementation, mulesoft-user-stories, mulesoft-validation | planning, testing, workflow |
| **Research & Analysis** | analyze-agent, research-agent, market-research-agent, domain-analyst, swot-analyst, material-analyzer | planning, collaboration |
| **Planning & Stories** | plan-agent, deep-planner, specify-agent, clarify-agent, tasks-agent, epic-architect, roadmap-planner, task-list-planner, app-user-stories, user-story-revision-agent, backlog-compiler, backlog-reviewer, story-estimator, nfr-specialist | planning |
| **Quality & Security** | security-auditor, constitution-agent, test-case-generator, performance-optimizer | security, testing |
| **Documentation** | documentation-agent, report-generator | workflow, collaboration |

---

## planning (67 skills)

Architecture, design, strategy, standards, and decision-making guidance.

| Skill | Description |
|-------|-------------|
| `accessibility` | Design, implement, and audit inclusive digital products using WCAG 2.2 Level AA |
| `android-clean-architecture` | Clean Architecture patterns for Android and Kotlin Multiplatform projects |
| `architecture-decision-records` | Capture architectural decisions as structured ADRs with context, alternatives, and rationale |
| `brand-voice` | Build a source-derived writing style profile from real posts, essays, and site copy |
| `cisco-ios-patterns` | Cisco IOS and IOS-XE review patterns for show commands, config hierarchy, and safe changes |
| `clickhouse-io` | ClickHouse database patterns, query optimization, analytics, and data engineering |
| `code-tour` | Create CodeTour `.tour` files — persona-targeted, step-by-step walkthroughs |
| `coding-standards` | Baseline cross-project coding conventions for naming, readability, and immutability |
| `compose-multiplatform-patterns` | Compose Multiplatform and Jetpack Compose patterns for KMP projects |
| `connections-optimizer` | Reorganize X and LinkedIn networks with review-first pruning and outreach |
| `content-engine` | Create platform-native content systems for X, LinkedIn, TikTok, YouTube, newsletters |
| `cpp-coding-standards` | C++ coding standards based on C++ Core Guidelines |
| `crosspost` | Multi-platform content distribution across X, LinkedIn, Threads, and Bluesky |
| `customer-billing-ops` | Operate customer billing workflows — subscriptions, refunds, churn triage |
| `customs-trade-compliance` | Customs and international trade compliance guidance |
| `dotnet-patterns` | Idiomatic C# and .NET patterns, conventions, dependency injection, async/await |
| `energy-procurement` | Energy procurement planning and strategy |
| `fal-ai-media` | Unified media generation via fal.ai MCP — image, video, and audio |
| `finance-billing-ops` | Evidence-first revenue, pricing, refunds, team-billing, and billing-model workflow |
| `flox-environments` | Create reproducible, cross-platform development environments with Flox |
| `flutter-dart-code-review` | Library-agnostic Flutter/Dart code review checklist |
| `foundation-models-on-device` | Apple FoundationModels framework for on-device LLM — text generation, tool calling |
| `frontend-slides` | Create animation-rich HTML presentations from scratch or by converting PowerPoint |
| `golang-patterns` | Idiomatic Go patterns, best practices, and conventions |
| `google-workspace-ops` | Operate across Google Drive, Docs, Sheets, and Slides as one workflow surface |
| `healthcare-emr-patterns` | EMR/EHR development patterns for healthcare applications |
| `homelab-network-readiness` | Readiness checklist for homelab VLAN segmentation and DNS filtering |
| `homelab-network-setup` | Practical home and homelab network planning for gateways, switches, access points |
| `homelab-wireguard-vpn` | WireGuard VPN server setup, peer configuration, and remote access |
| `inventory-demand-planning` | Inventory and demand planning strategy |
| `investor-materials` | Create pitch decks, one-pagers, investor memos, and accelerator applications |
| `investor-outreach` | Draft cold emails, warm intros, follow-ups for investor communications |
| `ios-icon-gen` | Generate iOS app icons as PNG imagesets for Xcode asset catalogs |
| `jpa-patterns` | JPA/Hibernate patterns for entity design, relationships, query optimization |
| `kotlin-patterns` | Idiomatic Kotlin patterns, best practices, and conventions |
| `laravel-plugin-discovery` | Discover and evaluate Laravel packages via LaraPlugins.io MCP |
| `lead-intelligence` | AI-native lead intelligence and outreach pipeline |
| `liquid-glass-design` | iOS 26 Liquid Glass design system — dynamic glass material with blur and reflection |
| `make-interfaces-feel-better` | Apply design-engineering details that make interfaces feel polished |
| `manim-video` | Build reusable Manim explainers for technical concepts and system diagrams |
| `messages-ops` | Evidence-first live messaging workflow for reading texts and DMs |
| `netmiko-ssh-automation` | Safe Python Netmiko patterns for read-only collection and bounded batch SSH |
| `plankton-code-quality` | Write-time code quality enforcement — auto-formatting, linting, and fixes |
| `product-capability` | Translate PRD intent into implementation-ready capability plans |
| `product-lens` | Validate the "why" before building — run product diagnostics and pressure-test direction |
| `production-scheduling` | Production scheduling and capacity planning |
| `python-patterns` | Pythonic idioms, PEP 8 standards, type hints, and best practices |
| `quality-nonconformance` | Quality and non-conformance management |
| `recsys-pipeline-architect` | Design composable recommendation, ranking, and feed pipelines |
| `remotion-video-creation` | Best practices for Remotion — Video creation in React (29 domain-specific rules) |
| `rust-patterns` | Idiomatic Rust patterns, ownership, error handling, traits, concurrency |
| `safety-guard` | Prevent destructive operations when working on production systems |
| `scientific-pkg-gget` | gget CLI and Python workflow for quick genomic database queries |
| `scientific-thinking-scholar-evaluation` | Structured scholarly-work evaluation for papers and proposals |
| `seo` | Audit, plan, and implement SEO improvements across technical SEO and on-page |
| `swift-concurrency-6-2` | Swift 6.2 Approachable Concurrency — single-threaded by default |
| `swiftui-patterns` | SwiftUI architecture patterns, state management with @Observable |
| `tinystruct-patterns` | Expert guidance for developing with the tinystruct Java framework |
| `ui-to-vue` | Batch conversion of UI screenshots/design exports into Vue 3 components |
| `videodb` | See, Understand, Act on video and audio — ingest, index, search, edit |

---

## testing (48 skills)

Test methodologies, TDD workflows, verification loops, and quality assurance.

| Skill | Description |
|-------|-------------|
| `angular-developer` | Generates Angular code and provides architectural guidance |
| `api-connector-builder` | Build API connectors by matching the target repo's existing patterns |
| `browser-qa` | Automate visual testing and UI interaction verification |
| `bun-runtime` | Bun as runtime, package manager, bundler, and test runner |
| `cpp-testing` | Writing/updating/fixing C++ tests with GoogleTest/CTest |
| `csharp-testing` | C# and .NET testing patterns with xUnit, FluentAssertions, mocking |
| `dart-flutter-patterns` | Production-ready Dart and Flutter patterns |
| `database-migrations` | Database migration best practices for schema changes and rollbacks |
| `django-celery` | Django + Celery async task patterns |
| `django-patterns` | Django architecture patterns with DRF, ORM best practices |
| `django-tdd` | Django testing strategies with pytest-django, TDD, factory_boy |
| `django-verification` | Verification loop for Django projects |
| `e2e-testing` | Playwright E2E testing patterns and Page Object Model |
| `fastapi-patterns` | FastAPI patterns for async APIs, dependency injection, Pydantic |
| `fsharp-testing` | F# testing patterns with xUnit, FsUnit, FsCheck |
| `golang-testing` | Go testing patterns including table-driven tests, benchmarks, fuzzing |
| `healthcare-cdss-patterns` | Clinical Decision Support System development patterns |
| `hexagonal-architecture` | Design Ports & Adapters systems with clear domain boundaries |
| `jira-integration` | Retrieve Jira tickets, analyze requirements, and track work items |
| `kotlin-coroutines-flows` | Kotlin Coroutines and Flow patterns for Android and KMP |
| `kotlin-ktor-patterns` | Ktor server patterns including routing DSL and authentication |
| `kotlin-testing` | Kotlin testing patterns with Kotest, MockK, and property-based testing |
| `laravel-tdd` | Test-driven development for Laravel with PHPUnit and Pest |
| `laravel-verification` | Verification loop for Laravel projects |
| `market-research` | Conduct market research, competitive analysis, and investor due diligence |
| `nestjs-patterns` | NestJS architecture patterns for modules, controllers, providers |
| `perl-patterns` | Modern Perl 5.36+ idioms and best practices |
| `perl-testing` | Perl testing patterns using Test2::V0 and prove runner |
| `prisma-patterns` | Prisma ORM patterns for TypeScript backends |
| `production-audit` | Local-evidence production readiness audit for shipped apps |
| `python-testing` | Python testing strategies using pytest, TDD, fixtures, mocking |
| `quarkus-tdd` | Test-driven development for Quarkus 3.x with JUnit 5 and REST Assured |
| `quarkus-verification` | Verification loop for Quarkus projects |
| `receiving-code-review` | Process for receiving code review feedback |
| `rust-testing` | Rust testing patterns including unit, integration, and async tests |
| `springboot-tdd` | Test-driven development for Spring Boot with JUnit 5, Mockito |
| `springboot-verification` | Verification loop for Spring Boot projects |
| `swift-protocol-di-testing` | Protocol-based dependency injection for testable Swift code |
| `tdd-workflow` | TDD workflow for writing new features, fixing bugs, or refactoring |
| `terminal-ops` | Evidence-first repo execution workflow — run commands and verify |
| `test-driven-development` | TDD before writing implementation code |
| `ui-demo` | Record polished UI demo videos using Playwright |
| `visa-doc-translate` | Translate visa application documents to English with bilingual PDF |
| `windows-desktop-e2e` | E2E testing for Windows native desktop apps (WPF, WinForms, Win32) |

---

## workflow (36 skills)

Process automation, content pipelines, execution patterns, and operational workflows.

| Skill | Description |
|-------|-------------|
| `api-design` | REST API design patterns — resource naming, status codes, pagination, versioning |
| `article-writing` | Write articles, guides, blog posts, tutorials, and newsletter issues |
| `backend-patterns` | Backend architecture patterns, API design, and database optimization |
| `benchmark` | Measure performance baselines and detect regressions |
| `canary-watch` | Monitor and verify deployed URLs after releases |
| `content-hash-cache-pattern` | Cache expensive file processing results using SHA-256 content hashes |
| `dashboard-builder` | Build monitoring dashboards for Grafana, SigNoz, and similar platforms |
| `data-scraper-agent` | Build fully automated AI-powered data collection agents |
| `deployment-patterns` | Deployment workflows, CI/CD, Docker, health checks, and rollback strategies |
| `email-ops` | Evidence-first mailbox triage, drafting, and send verification |
| `evm-token-decimals` | Prevent silent decimal mismatch bugs across EVM chains |
| `finishing-a-development-branch` | Complete development work — merge, PR, or cleanup options |
| `frontend-patterns` | Frontend development patterns for React, Next.js, and state management |
| `homelab-pihole-dns` | Pi-hole installation, blocklist management, and DNS-over-HTTPS setup |
| `kotlin-exposed-patterns` | JetBrains Exposed ORM patterns (DSL, DAO, HikariCP, Flyway) |
| `logistics-exception-management` | Logistics exception handling and resolution |
| `motion-advanced` | Advanced motion patterns — drag & drop, gestures, text animations, SVG |
| `motion-patterns` | Production-ready animation patterns — button, modal, toast, stagger, page |
| `motion-ui` | Production-ready UI motion system for React/Next.js |
| `network-interface-health` | Diagnose interface errors, drops, CRCs, duplex mismatches, flapping |
| `openclaw-persona-forge` | Forge complete persona solutions for OpenClaw AI agents |
| `quarkus-patterns` | Quarkus 3.x LTS architecture patterns with Camel for messaging |
| `redis-patterns` | Redis data structure patterns, caching strategies, distributed locks |
| `regex-vs-llm-structured-text` | Decision framework for choosing between regex and LLM for parsing |
| `repo-scan` | Cross-stack source code asset audit — classify every file |
| `research-ops` | Evidence-first current-state research workflow |
| `scientific-db-uspto-database` | USPTO patent and trademark data workflow |
| `social-graph-ranker` | Weighted social-graph ranking for warm intro discovery |
| `springboot-patterns` | Spring Boot architecture patterns, REST API, layered services |
| `swift-actor-persistence` | Thread-safe data persistence in Swift using actors |
| `verification-before-completion` | Run verification commands before claiming work is complete |
| `verification-loop` | Comprehensive verification system for agent sessions |
| `video-editing` | AI-assisted video editing workflows for cutting and augmenting footage |

---

## security (21 skills)

Security hardening, compliance, auditing, access control, and threat prevention.

| Skill | Description |
|-------|-------------|
| `agent-payment-x402` | Add x402 payment execution to AI agents with per-task budgets |
| `carrier-relationship-management` | Carrier relationship and compliance management |
| `defi-amm-security` | Security checklist for Solidity AMM contracts and liquidity pools |
| `docker-patterns` | Docker and Docker Compose patterns including container security |
| `healthcare-phi-compliance` | PHI and PII compliance patterns for healthcare applications |
| `hipaa-compliance` | HIPAA-specific entrypoint for healthcare privacy and security work |
| `homelab-vlan-segmentation` | Segmenting home networks into VLANs for IoT/guest/trusted traffic |
| `laravel-patterns` | Laravel architecture patterns with security considerations |
| `laravel-security` | Laravel security best practices for authn/authz, CSRF, mass assignment |
| `llm-trading-agent-security` | Security patterns for autonomous trading agents with wallet authority |
| `nutrient-document-processing` | Process, convert, OCR, extract, redact, sign, and fill documents |
| `perl-security` | Comprehensive Perl security — taint mode, input validation, safe execution |
| `postgres-patterns` | PostgreSQL patterns for query optimization, schema design, and security |
| `quarkus-security` | Quarkus Security best practices for JWT/OIDC, RBAC, input validation |
| `returns-reverse-logistics` | Returns and reverse logistics management |
| `security-bounty-hunter` | Hunt for exploitable, bounty-worthy security issues in repositories |
| `security-review` | Security checklist for auth, user input, secrets, API endpoints |
| `springboot-security` | Spring Security best practices for authn/authz, CSRF, secrets management |
| `x-api` | X/Twitter API integration for posting, reading, searching, and analytics |

---

## debugging (17 skills)

Troubleshooting, diagnostics, performance analysis, and root-cause identification.

| Skill | Description |
|-------|-------------|
| `click-path-audit` | Trace every user-facing button through its full state change sequence |
| `design-system` | Generate or audit design systems, check visual consistency |
| `django-security` | Django security diagnostics and best practices |
| `error-handling` | Patterns for robust error handling across TypeScript, Python, and Go |
| `github-ops` | GitHub repository operations, issue triage, PR management |
| `mle-workflow` | Production ML engineering workflow for data contracts and training |
| `motion-foundations` | Motion tokens, spring presets, performance rules |
| `mysql-patterns` | MySQL and MariaDB schema, query, indexing, and replication patterns |
| `nextjs-turbopack` | Next.js 16+ and Turbopack — incremental bundling, FS caching |
| `nuxt4-patterns` | Nuxt 4 patterns for hydration safety and performance |
| `pytorch-patterns` | PyTorch deep learning patterns and best practices |
| `systematic-debugging` | Systematic debugging before proposing fixes |
| `vite-patterns` | Vite build tool patterns — config, plugins, HMR, env variables |

---

## collaboration (9 skills)

Team coordination, communication protocols, and knowledge sharing.

| Skill | Description |
|-------|-------------|
| `git-workflow` | Git workflow patterns — branching strategies, commit conventions, conflict resolution |
| `java-coding-standards` | Java coding standards for Spring Boot and Quarkus services |
| `network-bgp-diagnostics` | Diagnostics-only BGP troubleshooting patterns |
| `network-config-validation` | Pre-deployment checks for router and switch configuration |
| `nodejs-keccak256` | Prevent Ethereum hashing bugs in JavaScript (Node sha3-256 ≠ Keccak-256) |
| `scientific-db-pubmed-database` | Direct PubMed and NCBI E-utilities search workflows |
| `scientific-thinking-literature-review` | Systematic literature-review workflow for academic topics |

---

## Sanitization Status

32 of these 198 skills still contain minor ECC/Superpowers/Claude Code references
that need cleanup. See `.planning/SKILLS.md` for the full sanitization checklist.
