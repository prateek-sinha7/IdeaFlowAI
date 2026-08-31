/**
 * DEPRECATED — This file is no longer used in the main codebase.
 *
 * Agents are now fetched from GET /api/agents/library (populated by the backend's
 * folder-scanned agent registry in agents/prompts/) and stored in Redux via
 * agentsSlice. The useAgentLibrary hook consumes this Redux state directly.
 *
 * This file is kept for historical reference and test fixtures only. It became
 * stale once the backend migrated to dynamic agent discovery (FIX-051/ISS-035).
 *
 * To use agent data: call useAgentLibrary() which returns Redux state from the API.
 */

import type { AgentDef } from "@/types/index";

export const LIBRARY_AGENTS: AgentDef[] = [
  // USER STORIES PIPELINE
  { id: "domain-analyst", name: "Domain Discovery Agent", role: "Market & Persona Research", description: "Researches your idea, identifies the target market, users, and key personas.", pipeline_type: "user_stories", order: 1, icon: "🔍", estimated_duration: 43, has_skill: true, gate: null },
  { id: "epic-architect", name: "Backlog Architecture Agent", role: "Epic & Story Composition", description: "Writes product epics and detailed user stories with clear acceptance criteria.", pipeline_type: "user_stories", order: 2, icon: "🏗️", estimated_duration: 86, has_skill: true, gate: null },
  { id: "story-estimator", name: "Estimation Agent", role: "Effort & Dependency Mapping", description: "Estimates effort for each story and maps out which tasks depend on others.", pipeline_type: "user_stories", order: 3, icon: "🎯", estimated_duration: 43, has_skill: true, gate: null },
  { id: "nfr-specialist", name: "Quality Requirements Agent", role: "Performance, Security & Compliance", description: "Adds quality requirements covering performance, security, and accessibility.", pipeline_type: "user_stories", order: 4, icon: "⚡", estimated_duration: 43, has_skill: true, gate: null },
  { id: "backlog-reviewer", name: "Quality Review Agent", role: "Backlog Validation & Gap Analysis", description: "Reviews all stories for completeness, gaps, and quality before finalizing.", pipeline_type: "user_stories", order: 5, icon: "✅", estimated_duration: 34, has_skill: true, gate: null },
  { id: "backlog-compiler", name: "Delivery Compilation Agent", role: "Final Backlog Synthesis", description: "Compiles all stories into a clean, structured document ready for your team.", pipeline_type: "user_stories", order: 6, icon: "📦", estimated_duration: 51, has_skill: true, gate: null },

  // PPT PIPELINE — real od_ppt agents (HTML deck pipeline). od_ppt's agent set
  // now owns the "ppt" id directly (backend AGENT.md frontmatter declares
  // pipeline_type: ppt; the legacy 3-field "ppt" workflow is archived —
  // backend/agents/workflows/.archive/ppt/). pipeline_type here matches what
  // GET /api/agents/library returns — the category key the agent-selector UI
  // filters on.
  { id: "ppt-brief-analyst", name: "Presentation Strategist Agent", role: "Slide Plan & Content Architecture", description: "Analyses the brief and architects the slide-by-slide plan, narrative arc, and content structure for the deck.", pipeline_type: "ppt", order: 1, icon: "📋", estimated_duration: 8, has_skill: true, gate: null },
  { id: "ppt-composer", name: "Deck Engineer Agent", role: "HTML Deck Construction", description: "Builds the complete HTML presentation from the plan — every slide, chart, and visual element wired to the template.", pipeline_type: "ppt", order: 2, icon: "🖥️", estimated_duration: 30, has_skill: true, gate: null },
  { id: "ppt-validator", name: "Deck QA Agent", role: "Structural Validation & Delivery", description: "Validates the deck for structural integrity and presentation correctness, then packages it ready for delivery.", pipeline_type: "ppt", order: 3, icon: "📦", estimated_duration: 10, has_skill: true, gate: null },

  // PROTOTYPE PIPELINE — real spec-kit agents. pipeline_type "prototype" is the
  // category key the agent-selector UI filters on; real ids/metadata/gate sourced
  // from backend agents.registry["prototype"] (specify → plan → analyze → build → validate).
  { id: "prototype-specify", name: "Spec Writer Agent", role: "Specification & Architecture", description: "Analyses the brief and writes the specification — navigation graph, page structure, and design-system selection for the prototype.", pipeline_type: "prototype", order: 1, icon: "📋", estimated_duration: 25, has_skill: true, gate: null },
  { id: "prototype-plan", name: "Task Planner Agent", role: "Build Planning & Task Decomposition", description: "Decomposes the spec into an ordered build plan — the full HTML shell first, then one page per task, then validation.", pipeline_type: "prototype", order: 2, icon: "🗂️", estimated_duration: 15, has_skill: true, gate: null },
  { id: "prototype-analyze", name: "Spec Kit Analyzer", role: "Cross-Artifact Quality Analysis", description: "Performs a read-only Spec Kit-style cross-artifact analysis of the spec and task list — checks consistency, coverage gaps, ambiguities, duplications, and unmapped tasks before implementation starts.", pipeline_type: "prototype", order: 3, icon: "🔍", estimated_duration: 20, has_skill: false, gate: null },
  { id: "prototype-build", name: "Build Agent", role: "Incremental HTML Construction", description: "Builds the interactive prototype incrementally, one task at a time, wiring up every page, component, and interaction.", pipeline_type: "prototype", order: 4, icon: "🏗️", estimated_duration: 60, has_skill: true, gate: null },
  { id: "prototype-validate", name: "Validation Agent", role: "Structural Validation & Delivery", description: "Validates the final prototype for structural integrity, navigation correctness, and delivery readiness.", pipeline_type: "prototype", order: 5, icon: "✅", estimated_duration: 60, has_skill: true, gate: null },

  // APP BUILDER PIPELINE — 15-agent SDLC
  { id: "material-analyzer", name: "Architecture Agent", role: "Solution & System Design", description: "Analyzes your requirements and designs the complete application architecture.", pipeline_type: "app_builder", order: 1, icon: "📋", estimated_duration: 63, has_skill: false, gate: null },
  { id: "app-user-stories", name: "User Stories Agent", role: "Requirements & Acceptance Criteria", description: "Translates the architecture into epics, user stories, and Gherkin acceptance criteria the team can pick up as deliverable work.", pipeline_type: "app_builder", order: 2, icon: "📝", estimated_duration: 95, has_skill: true, gate: null },
  { id: "app-system-design", name: "System Design Agent", role: "Detailed Architecture & Decomposition", description: "Detailed component decomposition, sync/async boundaries, state ownership, deployment topology, and ADRs.", pipeline_type: "app_builder", order: 3, icon: "🏗️", estimated_duration: 106, has_skill: true, gate: null },
  { id: "app-security-architecture", name: "Security Architecture Agent", role: "Threat Modelling & Security Controls", description: "STRIDE threat model, identity/IAM design, encryption, secrets, WAF, and security gates for the application.", pipeline_type: "app_builder", order: 4, icon: "🛡️", estimated_duration: 95, has_skill: true, gate: null },
  { id: "app-ux-design", name: "UX & UI Design Agent", role: "User Journeys, Wireframes & Design System", description: "Information architecture, wireframes, design tokens, component library, accessibility plan, and error/loading states.", pipeline_type: "app_builder", order: 5, icon: "🎨", estimated_duration: 95, has_skill: true, gate: null },
  { id: "app-api-design", name: "API Contract Agent", role: "REST/GraphQL Contracts & OpenAPI", description: "Endpoint contracts, error envelopes, idempotency rules, async event contracts, versioning policy, and the OpenAPI 3.1 document.", pipeline_type: "app_builder", order: 6, icon: "🔌", estimated_duration: 85, has_skill: true, gate: null },
  { id: "app-database-design", name: "Data Model Agent", role: "Schema, Indexes & Migrations", description: "Entity model, DDL, indexing strategy, migration tooling, PII classification, backup/recovery targets, and query budgets.", pipeline_type: "app_builder", order: 7, icon: "🗄️", estimated_duration: 85, has_skill: true, gate: null },
  { id: "app-code-generator", name: "Code Generation Agent", role: "Full-Stack Code Generation", description: "Generates complete frontend and backend code for your application — controllers, services, models, pages, components.", pipeline_type: "app_builder", order: 8, icon: "💻", estimated_duration: 158, has_skill: false, gate: null },
  { id: "app-feature-implementation", name: "Feature Implementation Agent", role: "Business Logic per User Story", description: "Fleshes out the user stories' business logic in the generated codebase — route handlers, services, integrations, and feature flags.", pipeline_type: "app_builder", order: 9, icon: "⚙️", estimated_duration: 148, has_skill: true, gate: null },
  { id: "app-infra-generator", name: "Infrastructure Agent", role: "Deployment & Platform", description: "Sets up deployment configuration, tests, and infrastructure for your app.", pipeline_type: "app_builder", order: 10, icon: "🚀", estimated_duration: 85, has_skill: false, gate: null },
  { id: "app-code-compliance", name: "Code Compliance Agent", role: "Static Analysis, Linting & Licensing", description: "SAST/SCA tooling, SonarQube quality gates, language-specific lint config, license policy, and pre-commit/CI gates.", pipeline_type: "app_builder", order: 11, icon: "🧪", estimated_duration: 85, has_skill: true, gate: null },
  { id: "app-test-implementation", name: "Test Implementation Agent", role: "Unit, Integration & Contract Test Code", description: "Writes the test code (JUnit/xUnit/Jest/Pact/Playwright) that proves the user stories' acceptance criteria.", pipeline_type: "app_builder", order: 12, icon: "🧬", estimated_duration: 127, has_skill: true, gate: null },
  { id: "app-test-compliance", name: "Test Compliance Agent", role: "Test Strategy & Coverage Gates", description: "Test pyramid, coverage gates, compliance test mapping (PCI/GDPR/SOC 2), performance and chaos plans.", pipeline_type: "app_builder", order: 13, icon: "🎯", estimated_duration: 85, has_skill: true, gate: null },
  { id: "app-devops", name: "DevOps Agent", role: "Build, Deploy, Operate & Quality Gates", description: "Branching model, CI/CD pipeline-as-code, environment promotion, OIDC secrets, DORA-metric observability, and developer-experience tooling.", pipeline_type: "app_builder", order: 14, icon: "🚦", estimated_duration: 95, has_skill: true, gate: null },
  { id: "app-sdlc-governance", name: "SDLC Governance & Handover Agent", role: "ADRs, Runbooks, SLOs & Operations Handover", description: "Architecture Decision Records, runbooks, SLOs/SLIs, dashboards, compliance evidence matrix, and operations handover.", pipeline_type: "app_builder", order: 15, icon: "📚", estimated_duration: 95, has_skill: true, gate: null },

  // MIGRATION: MULESOFT → SPRING BOOT MICROSERVICES ON AWS
  { id: "mulesoft-inventory", name: "Mulesoft Asset Inventory Agent", role: "Mule App Discovery & Cataloguing", description: "Catalogues your Mulesoft estate — flows, connectors, DataWeave transforms, and migration risk hotspots.", pipeline_type: "mulesoft_to_springboot", order: 1, icon: "📋", estimated_duration: 110, has_skill: true, gate: null },
  { id: "mulesoft-user-stories", name: "Migration User Stories Agent", role: "Requirements & Acceptance Criteria", description: "Turns the inventory into epics, user stories, and Gherkin acceptance criteria for the migrated capabilities.", pipeline_type: "mulesoft_to_springboot", order: 2, icon: "📝", estimated_duration: 124, has_skill: true, gate: null },
  { id: "mulesoft-decomposition", name: "Bounded Context Decomposition Agent", role: "Domain Modelling & Service Boundaries", description: "Proposes the Spring Boot microservice split with bounded contexts and service topology.", pipeline_type: "mulesoft_to_springboot", order: 3, icon: "🧩", estimated_duration: 137, has_skill: true, gate: null },
  { id: "mulesoft-security-architecture", name: "Security Architecture Agent", role: "Threat Modelling & Security Controls", description: "STRIDE threat model, IAM/access design, encryption, secrets, WAF, and security gates for the target AWS architecture.", pipeline_type: "mulesoft_to_springboot", order: 4, icon: "🛡️", estimated_duration: 124, has_skill: true, gate: null },
  { id: "mulesoft-springboot-scaffold", name: "Spring Boot Scaffold Agent", role: "Java Microservice Project Scaffolding", description: "Generates a commit-ready Spring Boot 3 scaffold for each microservice.", pipeline_type: "mulesoft_to_springboot", order: 5, icon: "☕", estimated_duration: 192, has_skill: true, gate: null },
  { id: "mulesoft-feature-coding", name: "Coding Agent", role: "Business Logic & Feature Code", description: "Implements the user stories' business logic in the Spring Boot services — controllers, services, persistence, integrations.", pipeline_type: "mulesoft_to_springboot", order: 6, icon: "⚙️", estimated_duration: 192, has_skill: true, gate: null },
  { id: "mulesoft-dataweave-translator", name: "DataWeave to Java Mapping Agent", role: "Transformation Logic Migration", description: "Translates DataWeave scripts into MapStruct or hand-written Java mappers with unit tests.", pipeline_type: "mulesoft_to_springboot", order: 7, icon: "🔄", estimated_duration: 137, has_skill: true, gate: null },
  { id: "mulesoft-aws-infra", name: "AWS Landing Zone Agent", role: "Target Infrastructure on AWS", description: "Generates Terraform for ECS Fargate, RDS, SQS/SNS, ALB, and per-service IAM roles.", pipeline_type: "mulesoft_to_springboot", order: 8, icon: "☁️", estimated_duration: 165, has_skill: true, gate: null },
  { id: "mulesoft-code-compliance", name: "Code Compliance Agent", role: "Static Analysis, Linting & Licensing", description: "SAST/SCA tooling, SonarQube quality gates, Checkstyle/SpotBugs/PMD config, license policy, and pre-commit/CI gates.", pipeline_type: "mulesoft_to_springboot", order: 9, icon: "🧪", estimated_duration: 110, has_skill: true, gate: null },
  { id: "mulesoft-test-implementation", name: "Test Implementation Agent", role: "Unit, Integration & Contract Test Code", description: "Writes the JUnit 5 + Testcontainers + Spring Cloud Contract test code that proves the acceptance criteria.", pipeline_type: "mulesoft_to_springboot", order: 10, icon: "🧬", estimated_duration: 165, has_skill: true, gate: null },
  { id: "mulesoft-test-compliance", name: "Test Compliance Agent", role: "Test Strategy & Coverage Gates", description: "Test pyramid, coverage gates, compliance test mapping (PCI/GDPR/SOC 2), perf & chaos plans.", pipeline_type: "mulesoft_to_springboot", order: 11, icon: "🎯", estimated_duration: 110, has_skill: true, gate: null },
  { id: "mulesoft-validation", name: "Migration Validation Agent", role: "Parallel-Run & Cutover Gates", description: "Designs the parallel-run harness against the legacy Mule app, cutover gates, and rollback runbook.", pipeline_type: "mulesoft_to_springboot", order: 12, icon: "✅", estimated_duration: 110, has_skill: true, gate: null },
  { id: "mulesoft-sdlc-governance", name: "SDLC Governance & Handover Agent", role: "ADRs, Runbooks, SLOs & Operations Handover", description: "Architecture Decision Records, runbooks, SLOs/SLIs, dashboards, compliance evidence matrix, and operations handover.", pipeline_type: "mulesoft_to_springboot", order: 13, icon: "📚", estimated_duration: 124, has_skill: true, gate: null },

  // MIGRATION: .NET FRAMEWORK → AZURE (AI-augmented)
  { id: "dotnet-inventory", name: ".NET Solution Inventory Agent", role: "Legacy App Discovery & Cataloguing", description: "Catalogues your .NET estate — projects, frameworks, NuGet deps, auth model, and modernisation risk hotspots.", pipeline_type: "dotnet_to_azure", order: 1, icon: "📋", estimated_duration: 112, has_skill: true, gate: null },
  { id: "dotnet-user-stories", name: "Migration User Stories Agent", role: "Requirements & Acceptance Criteria", description: "Turns the inventory into epics, user stories, and Gherkin acceptance criteria for the migrated capabilities.", pipeline_type: "dotnet_to_azure", order: 2, icon: "📝", estimated_duration: 126, has_skill: true, gate: null },
  { id: "dotnet-azure-target-mapping", name: "Azure Target Mapping Agent", role: "Azure Service Recommendation", description: "Maps each .NET project to the right Azure service (App Service, AKS, Functions, SQL) with effort estimates.", pipeline_type: "dotnet_to_azure", order: 3, icon: "🎯", estimated_duration: 112, has_skill: true, gate: null },
  { id: "dotnet-security-architecture", name: "Security Architecture Agent", role: "Threat Modelling & Security Controls", description: "STRIDE threat model, Entra ID/Key Vault design, encryption, WAF, and security gates for the target Azure architecture.", pipeline_type: "dotnet_to_azure", order: 4, icon: "🛡️", estimated_duration: 126, has_skill: true, gate: null },
  { id: "dotnet-modernization", name: ".NET Core Modernisation Agent", role: ".NET Framework → .NET 8 Code Conversion", description: "Translates legacy .NET Framework projects to .NET 8 with breaking-change fixes and async-by-default.", pipeline_type: "dotnet_to_azure", order: 5, icon: "🔧", estimated_duration: 195, has_skill: true, gate: null },
  { id: "dotnet-feature-coding", name: "Coding Agent", role: "Business Logic & Feature Code", description: "Implements the user stories' business logic in the modernised .NET 8 services — controllers, services, persistence, integrations.", pipeline_type: "dotnet_to_azure", order: 6, icon: "⚙️", estimated_duration: 195, has_skill: true, gate: null },
  { id: "dotnet-azure-bicep", name: "Azure Bicep Provisioning Agent", role: "Azure Infrastructure as Code", description: "Generates Bicep modules for App Service, Functions, Azure SQL, Service Bus, networking, and observability.", pipeline_type: "dotnet_to_azure", order: 7, icon: "☁️", estimated_duration: 167, has_skill: true, gate: null },
  { id: "dotnet-azure-ai", name: "Azure AI Integration Agent", role: "Cognitive & Generative AI Augmentation", description: "Identifies where Azure OpenAI / Document Intelligence / AI Search add measurable value and produces the C# integration code.", pipeline_type: "dotnet_to_azure", order: 8, icon: "🧠", estimated_duration: 140, has_skill: true, gate: null },
  { id: "dotnet-code-compliance", name: "Code Compliance Agent", role: "Static Analysis, Linting & Licensing", description: "SAST/SCA tooling, SonarQube quality gates, Roslyn analyzers, .editorconfig, license policy, and pre-commit/CI gates.", pipeline_type: "dotnet_to_azure", order: 9, icon: "🧪", estimated_duration: 112, has_skill: true, gate: null },
  { id: "dotnet-test-implementation", name: "Test Implementation Agent", role: "Unit, Integration & Contract Test Code", description: "Writes the xUnit + FluentAssertions + Testcontainers + Pact test code that proves the acceptance criteria.", pipeline_type: "dotnet_to_azure", order: 10, icon: "🧬", estimated_duration: 167, has_skill: true, gate: null },
  { id: "dotnet-test-compliance", name: "Test Compliance Agent", role: "Test Strategy & Coverage Gates", description: "Test pyramid, coverage gates, compliance test mapping (PCI/GDPR/SOC 2), perf & chaos plans.", pipeline_type: "dotnet_to_azure", order: 11, icon: "🎯", estimated_duration: 112, has_skill: true, gate: null },
  { id: "dotnet-validation", name: "Migration Validation Agent", role: "Behaviour Parity & Cutover Gates", description: "Designs parity tests, shadow-traffic config, Application Insights KQL gates, and the rollback drill.", pipeline_type: "dotnet_to_azure", order: 12, icon: "✅", estimated_duration: 112, has_skill: true, gate: null },
  { id: "dotnet-sdlc-governance", name: "SDLC Governance & Handover Agent", role: "ADRs, Runbooks, SLOs & Operations Handover", description: "Architecture Decision Records, runbooks, SLOs/SLIs, dashboards, compliance evidence matrix, and operations handover.", pipeline_type: "dotnet_to_azure", order: 13, icon: "📚", estimated_duration: 126, has_skill: true, gate: null },
];

export const CUSTOM_AGENTS: AgentDef[] = [
  { id: "market-research-agent", name: "Market Research Agent", role: "Competitive & Industry Analysis", description: "Analyzes your market, competitors, and industry trends to size the opportunity.", pipeline_type: "custom", order: 1, icon: "📈", estimated_duration: 6, has_skill: true, gate: null },
  { id: "swot-analyst", name: "Strategy Analysis Agent", role: "SWOT & Strategic Positioning", description: "Identifies your strengths, weaknesses, opportunities, and threats with clear actions.", pipeline_type: "custom", order: 2, icon: "🎯", estimated_duration: 5, has_skill: true, gate: null },
  { id: "roadmap-planner", name: "Roadmap Planning Agent", role: "Phased Delivery Strategy", description: "Builds a phased product roadmap with milestones, priorities, and timelines.", pipeline_type: "custom", order: 3, icon: "🗓️", estimated_duration: 6, has_skill: true, gate: null },
  { id: "security-auditor", name: "Security Audit Agent", role: "Risk Assessment & Mitigation", description: "Reviews your product for security risks and provides a prioritized action plan.", pipeline_type: "custom", order: 4, icon: "🛡️", estimated_duration: 5, has_skill: true, gate: null },
  { id: "test-case-generator", name: "Test Strategy Agent", role: "Scenario & Edge-Case Coverage", description: "Creates comprehensive test scenarios covering happy paths, edge cases, and errors.", pipeline_type: "custom", order: 5, icon: "🧪", estimated_duration: 6, has_skill: true, gate: null },
  { id: "performance-optimizer", name: "Performance Optimization Agent", role: "Profiling & Bottleneck Analysis", description: "Identifies performance bottlenecks and recommends optimizations for speed.", pipeline_type: "custom", order: 6, icon: "⚡", estimated_duration: 5, has_skill: true, gate: null },
  { id: "documentation-agent", name: "Documentation Agent", role: "API & Technical Writing", description: "Writes clear documentation including README, API guides, and setup instructions.", pipeline_type: "custom", order: 7, icon: "📚", estimated_duration: 7, has_skill: true, gate: null },
  { id: "report-generator", name: "Executive Reporting Agent", role: "Insights & Recommendations", description: "Creates executive-ready reports with key metrics, insights, and recommendations.", pipeline_type: "custom", order: 8, icon: "📋", estimated_duration: 5, has_skill: true, gate: null },
];

export const ALL_LIBRARY_AGENTS: AgentDef[] = [...LIBRARY_AGENTS, ...CUSTOM_AGENTS];

export const PIPELINE_CATEGORIES = [
  { key: "all", label: "All", count: 55 },
  { key: "user_stories", label: "User Stories", count: 6 },
  { key: "ppt", label: "PPT", count: 3 },
  { key: "prototype", label: "Prototype", count: 5 },
  { key: "app_builder", label: "App Builder", count: 15 },
  { key: "mulesoft_to_springboot", label: "Mulesoft → Spring Boot", count: 13 },
  { key: "dotnet_to_azure", label: ".NET → Azure", count: 13 },
  { key: "custom", label: "Custom", count: 8 },
] as const;

export const PIPELINE_COLORS: Record<string, { bg: string; text: string }> = {
  user_stories: { bg: "rgba(79, 195, 247, 0.15)", text: "#4FC3F7" },
  ppt: { bg: "rgba(255, 167, 38, 0.15)", text: "#FFA726" },
  prototype: { bg: "rgba(129, 199, 132, 0.15)", text: "#81C784" },
  app_builder: { bg: "rgba(255, 183, 77, 0.15)", text: "#FFB74D" },
  custom: { bg: "rgba(186, 104, 200, 0.15)", text: "#BA68C8" },
  mulesoft_to_springboot: { bg: "rgba(38, 166, 154, 0.15)", text: "#26A69A" },
  dotnet_to_azure: { bg: "rgba(92, 107, 192, 0.15)", text: "#5C6BC0" },
};
