import type { AgentDef } from "@/types/index";

/**
 * Static agent library data matching the backend registry.
 * 6 User Story agents + 6 PPT agents + 4 Prototype agents + others.
 */
export const LIBRARY_AGENTS: AgentDef[] = [
  // ============================================================
  // USER STORIES PIPELINE — 6 Agents (focused, high-quality)
  // ============================================================
  {
    id: "domain-analyst",
    name: "Domain & Persona Analyst",
    role: "Product Strategist",
    description: "Analyzes the idea, identifies the domain, target users, and key personas.",
    pipeline_type: "user_stories",
    order: 1,
    icon: "🔍",
    estimated_duration: 5,
    has_skill: true,
  },
  {
    id: "epic-architect",
    name: "Epic & Story Architect",
    role: "Principal Product Manager",
    description: "Creates epics and breaks them into detailed user stories with acceptance criteria.",
    pipeline_type: "user_stories",
    order: 2,
    icon: "🏗️",
    estimated_duration: 10,
    has_skill: true,
  },
  {
    id: "story-estimator",
    name: "Estimator & Dependency Mapper",
    role: "Technical Lead",
    description: "Assigns story points and maps dependencies between stories.",
    pipeline_type: "user_stories",
    order: 3,
    icon: "🎯",
    estimated_duration: 5,
    has_skill: true,
  },
  {
    id: "nfr-specialist",
    name: "NFR & Quality Specialist",
    role: "Solution Architect",
    description: "Adds non-functional requirements as stories (performance, security, accessibility).",
    pipeline_type: "user_stories",
    order: 4,
    icon: "⚡",
    estimated_duration: 5,
    has_skill: true,
  },
  {
    id: "backlog-reviewer",
    name: "Backlog Reviewer",
    role: "Agile Coach",
    description: "Reviews the backlog for INVEST compliance, gaps, and quality.",
    pipeline_type: "user_stories",
    order: 5,
    icon: "✅",
    estimated_duration: 4,
    has_skill: true,
  },
  {
    id: "backlog-compiler",
    name: "Backlog Compiler",
    role: "Principal PM",
    description: "Compiles the final complete user stories document in structured markdown.",
    pipeline_type: "user_stories",
    order: 6,
    icon: "📦",
    estimated_duration: 6,
    has_skill: true,
  },

  // ============================================================
  // PPT GENERATION PIPELINE — 3 Agents (Claude-native HTML + pptxgenjs)
  // ============================================================
  { id: "audience-analyst", name: "Content & Design Planner", role: "Presentation Strategist", description: "Plans slide content, visual design, and data for the presentation.", pipeline_type: "ppt", order: 1, icon: "🎯", estimated_duration: 6, has_skill: true },
  { id: "export-formatter", name: "Presentation Generator", role: "Senior Frontend Engineer", description: "Generates a complete HTML slide presentation with embedded PPTX export.", pipeline_type: "ppt", order: 2, icon: "📦", estimated_duration: 15, has_skill: true },
  { id: "slide-polisher", name: "Presentation Polisher", role: "Design QA", description: "Reviews and polishes the HTML presentation for visual quality.", pipeline_type: "ppt", order: 3, icon: "✨", estimated_duration: 8, has_skill: true },

  // ============================================================
  // PROTOTYPE GENERATION PIPELINE — 4 Agents (focused on HTML output)
  // ============================================================
  {
    id: "requirements-analyst",
    name: "Requirements & UX Planner",
    role: "Product Designer",
    description: "Analyzes the idea and plans pages, navigation, and user flows.",
    pipeline_type: "prototype",
    order: 1,
    icon: "📋",
    estimated_duration: 6,
    has_skill: true,
  },
  {
    id: "html-prototype-builder",
    name: "HTML Prototype Builder",
    role: "Senior Frontend Engineer",
    description: "Generates a complete multi-page HTML prototype with navigation and interactions.",
    pipeline_type: "prototype",
    order: 2,
    icon: "🖥️",
    estimated_duration: 15,
    has_skill: true,
  },
  {
    id: "prototype-polisher",
    name: "Prototype Polisher",
    role: "UI/UX Engineer",
    description: "Reviews and enhances the HTML prototype for visual polish and interactions.",
    pipeline_type: "prototype",
    order: 3,
    icon: "✨",
    estimated_duration: 8,
    has_skill: true,
  },
  {
    id: "prototype-finalizer",
    name: "Prototype Finalizer",
    role: "Tech Lead",
    description: "Final validation and output of the HTML prototype.",
    pipeline_type: "prototype",
    order: 4,
    icon: "📦",
    estimated_duration: 5,
    has_skill: true,
  },

  // === APP BUILDER PIPELINE (4 agents) ===
  { id: "material-analyzer", name: "Material Analyzer & Architect", role: "Solutions Architect", description: "Analyzes input materials and designs the complete app architecture.", pipeline_type: "app_builder", order: 1, icon: "📋", estimated_duration: 6, has_skill: false },
  { id: "app-code-generator", name: "Full-Stack Code Generator", role: "Senior Full-Stack Developer", description: "Generates complete frontend and backend code for the app.", pipeline_type: "app_builder", order: 2, icon: "💻", estimated_duration: 15, has_skill: false },
  { id: "app-infra-generator", name: "Infrastructure & Tests Generator", role: "DevOps Engineer", description: "Generates Docker, CI/CD, tests, and deployment configuration.", pipeline_type: "app_builder", order: 3, icon: "🚀", estimated_duration: 8, has_skill: false },
  { id: "app-assembler", name: "Project Assembler", role: "Tech Lead", description: "Compiles everything into a final structured project document.", pipeline_type: "app_builder", order: 4, icon: "📦", estimated_duration: 6, has_skill: false },

  // === REVERSE ENGINEER PIPELINE (4 agents) ===
  { id: "repo-scanner", name: "Codebase Scanner & Architect", role: "Solutions Architect", description: "Scans the codebase and maps architecture, tech stack, and structure.", pipeline_type: "reverse_engineer", order: 1, icon: "🔍", estimated_duration: 6, has_skill: false },
  { id: "deep-analyzer", name: "Deep Analysis & Risk Auditor", role: "Staff Engineer", description: "Analyzes dependencies, data models, APIs, technical debt, and security risks.", pipeline_type: "reverse_engineer", order: 2, icon: "🛡️", estimated_duration: 10, has_skill: false },
  { id: "modernization-planner", name: "Modernization & Roadmap Planner", role: "Engineering Manager", description: "Creates a prioritized modernization roadmap with actionable phases.", pipeline_type: "reverse_engineer", order: 3, icon: "📋", estimated_duration: 6, has_skill: false },
  { id: "documentation-generator", name: "Documentation Compiler", role: "Technical Writer", description: "Compiles the final comprehensive codebase documentation.", pipeline_type: "reverse_engineer", order: 4, icon: "📝", estimated_duration: 8, has_skill: false },
];


// ============================================================
// CUSTOM / UTILITY AGENTS — Can be added to any pipeline
// ============================================================
// CUSTOM UTILITY AGENTS — Can be added to any pipeline
// ============================================================

export const CUSTOM_AGENTS: AgentDef[] = [
  { id: "market-research-agent", name: "Market Research Agent", role: "Market Analyst", description: "Analyzes competitors, market size (TAM/SAM/SOM), and industry trends.", pipeline_type: "custom", order: 1, icon: "📈", estimated_duration: 6, has_skill: true },
  { id: "swot-analyst", name: "SWOT Analyst", role: "Strategy Consultant", description: "Generates SWOT analysis with actionable recommendations.", pipeline_type: "custom", order: 2, icon: "🎯", estimated_duration: 5, has_skill: true },
  { id: "roadmap-planner", name: "Roadmap Planner", role: "Product Director", description: "Builds phased product roadmaps with milestones and priorities.", pipeline_type: "custom", order: 3, icon: "🗓️", estimated_duration: 6, has_skill: true },
  { id: "security-auditor", name: "Security Auditor", role: "Security Engineer", description: "Reviews for OWASP vulnerabilities and generates a threat model.", pipeline_type: "custom", order: 4, icon: "🛡️", estimated_duration: 5, has_skill: true },
  { id: "test-case-generator", name: "Test Case Generator", role: "QA Engineer", description: "Creates comprehensive test scenarios with edge cases.", pipeline_type: "custom", order: 5, icon: "🧪", estimated_duration: 6, has_skill: true },
  { id: "performance-optimizer", name: "Performance Optimizer", role: "Performance Engineer", description: "Identifies bottlenecks and suggests optimization strategies.", pipeline_type: "custom", order: 6, icon: "⚡", estimated_duration: 5, has_skill: true },
  { id: "documentation-agent", name: "Documentation Writer", role: "Technical Writer", description: "Creates README, API docs, setup guides, and ADRs.", pipeline_type: "custom", order: 7, icon: "📚", estimated_duration: 7, has_skill: true },
  { id: "report-generator", name: "Executive Report Generator", role: "Business Analyst", description: "Creates executive reports with metrics, trends, and recommendations.", pipeline_type: "custom", order: 8, icon: "📋", estimated_duration: 5, has_skill: true },
];

/** Combined library — all agents including custom */
export const ALL_LIBRARY_AGENTS: AgentDef[] = [...LIBRARY_AGENTS, ...CUSTOM_AGENTS];

/** Pipeline category labels */
export const PIPELINE_CATEGORIES = [
  { key: "all", label: "All", count: 23 },
  { key: "user_stories", label: "User Stories", count: 6 },
  { key: "ppt", label: "PPT", count: 3 },
  { key: "prototype", label: "Prototype", count: 4 },
  { key: "app_builder", label: "App Builder", count: 4 },
  { key: "reverse_engineer", label: "Reverse Engineer", count: 4 },
  { key: "custom", label: "Custom", count: 8 },
] as const;

/** Pipeline badge colors */
export const PIPELINE_COLORS: Record<string, { bg: string; text: string }> = {
  user_stories: { bg: "rgba(79, 195, 247, 0.15)", text: "#4FC3F7" },
  ppt: { bg: "rgba(255, 167, 38, 0.15)", text: "#FFA726" },
  prototype: { bg: "rgba(129, 199, 132, 0.15)", text: "#81C784" },
  app_builder: { bg: "rgba(255, 183, 77, 0.15)", text: "#FFB74D" },
  reverse_engineer: { bg: "rgba(240, 98, 146, 0.15)", text: "#F06292" },
  custom: { bg: "rgba(186, 104, 200, 0.15)", text: "#BA68C8" },
};
