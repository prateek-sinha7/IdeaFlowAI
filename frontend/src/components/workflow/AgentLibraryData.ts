import type { AgentDef } from "@/types/index";

export const LIBRARY_AGENTS: AgentDef[] = [
  // USER STORIES PIPELINE
  { id: "domain-analyst", name: "Domain Discovery Agent", role: "Market & Persona Research", description: "Researches your idea, identifies the target market, users, and key personas.", pipeline_type: "user_stories", order: 1, icon: "🔍", estimated_duration: 5, has_skill: true },
  { id: "epic-architect", name: "Backlog Architecture Agent", role: "Epic & Story Composition", description: "Writes product epics and detailed user stories with clear acceptance criteria.", pipeline_type: "user_stories", order: 2, icon: "🏗️", estimated_duration: 10, has_skill: true },
  { id: "story-estimator", name: "Estimation Agent", role: "Effort & Dependency Mapping", description: "Estimates effort for each story and maps out which tasks depend on others.", pipeline_type: "user_stories", order: 3, icon: "🎯", estimated_duration: 5, has_skill: true },
  { id: "nfr-specialist", name: "Quality Requirements Agent", role: "Performance, Security & Compliance", description: "Adds quality requirements covering performance, security, and accessibility.", pipeline_type: "user_stories", order: 4, icon: "⚡", estimated_duration: 5, has_skill: true },
  { id: "backlog-reviewer", name: "Quality Review Agent", role: "Backlog Validation & Gap Analysis", description: "Reviews all stories for completeness, gaps, and quality before finalizing.", pipeline_type: "user_stories", order: 5, icon: "✅", estimated_duration: 4, has_skill: true },
  { id: "backlog-compiler", name: "Delivery Compilation Agent", role: "Final Backlog Synthesis", description: "Compiles all stories into a clean, structured document ready for your team.", pipeline_type: "user_stories", order: 6, icon: "📦", estimated_duration: 6, has_skill: true },

  // PPT PIPELINE
  { id: "ppt-content-strategist", name: "Content Strategy Agent", role: "Narrative & Messaging", description: "Plans the story, key messages, and content for each slide in your presentation.", pipeline_type: "ppt", order: 1, icon: "🎯", estimated_duration: 8, has_skill: true },
  { id: "ppt-slide-architect", name: "Visual Design Agent", role: "Slide Layout & Composition", description: "Designs the visual layout, structure, and look of each slide.", pipeline_type: "ppt", order: 2, icon: "🏗️", estimated_duration: 10, has_skill: true },
  { id: "ppt-code-generator", name: "Slide Generation Agent", role: "Presentation Engineering", description: "Builds the complete presentation with all slides, charts, and visual elements.", pipeline_type: "ppt", order: 3, icon: "💻", estimated_duration: 15, has_skill: true },
  { id: "ppt-assembler", name: "Deck Assembly Agent", role: "Final Deck Compilation", description: "Packages the final presentation with preview and download ready for sharing.", pipeline_type: "ppt", order: 4, icon: "📦", estimated_duration: 12, has_skill: true },

  // PROTOTYPE PIPELINE
  { id: "requirements-analyst", name: "Experience Discovery Agent", role: "UX Flows & Navigation", description: "Plans the pages, navigation flows, and user experience for your prototype.", pipeline_type: "prototype", order: 1, icon: "📋", estimated_duration: 6, has_skill: true },
  { id: "html-prototype-builder", name: "Prototype Generation Agent", role: "Interactive HTML Engineering", description: "Builds a complete interactive prototype with all pages and navigation.", pipeline_type: "prototype", order: 2, icon: "🖥️", estimated_duration: 15, has_skill: true },
  { id: "prototype-polisher", name: "Design Refinement Agent", role: "Visual & Interaction Quality", description: "Reviews and refines the prototype for visual quality and smooth interactions.", pipeline_type: "prototype", order: 3, icon: "✨", estimated_duration: 8, has_skill: true },
  { id: "prototype-finalizer", name: "Delivery Validation Agent", role: "Final Quality Gate", description: "Validates and packages the final prototype ready for review and handoff.", pipeline_type: "prototype", order: 4, icon: "📦", estimated_duration: 5, has_skill: true },

  // APP BUILDER PIPELINE
  { id: "material-analyzer", name: "Architecture Agent", role: "Solution & System Design", description: "Analyzes your requirements and designs the complete application architecture.", pipeline_type: "app_builder", order: 1, icon: "📋", estimated_duration: 6, has_skill: false },
  { id: "app-code-generator", name: "Code Generation Agent", role: "Full-Stack Implementation", description: "Generates complete frontend and backend code for your application.", pipeline_type: "app_builder", order: 2, icon: "💻", estimated_duration: 15, has_skill: false },
  { id: "app-infra-generator", name: "Infrastructure Agent", role: "Deployment & Platform", description: "Sets up deployment configuration, tests, and infrastructure for your app.", pipeline_type: "app_builder", order: 3, icon: "🚀", estimated_duration: 8, has_skill: false },
  { id: "app-assembler", name: "Project Assembly Agent", role: "Final Compilation & Handoff", description: "Packages everything into a complete, ready-to-use project document.", pipeline_type: "app_builder", order: 4, icon: "📦", estimated_duration: 6, has_skill: false },
];

export const CUSTOM_AGENTS: AgentDef[] = [
  { id: "market-research-agent", name: "Market Research Agent", role: "Competitive & Industry Analysis", description: "Analyzes your market, competitors, and industry trends to size the opportunity.", pipeline_type: "custom", order: 1, icon: "📈", estimated_duration: 6, has_skill: true },
  { id: "swot-analyst", name: "Strategy Analysis Agent", role: "SWOT & Strategic Positioning", description: "Identifies your strengths, weaknesses, opportunities, and threats with clear actions.", pipeline_type: "custom", order: 2, icon: "🎯", estimated_duration: 5, has_skill: true },
  { id: "roadmap-planner", name: "Roadmap Planning Agent", role: "Phased Delivery Strategy", description: "Builds a phased product roadmap with milestones, priorities, and timelines.", pipeline_type: "custom", order: 3, icon: "🗓️", estimated_duration: 6, has_skill: true },
  { id: "security-auditor", name: "Security Audit Agent", role: "Risk Assessment & Mitigation", description: "Reviews your product for security risks and provides a prioritized action plan.", pipeline_type: "custom", order: 4, icon: "🛡️", estimated_duration: 5, has_skill: true },
  { id: "test-case-generator", name: "Test Strategy Agent", role: "Scenario & Edge-Case Coverage", description: "Creates comprehensive test scenarios covering happy paths, edge cases, and errors.", pipeline_type: "custom", order: 5, icon: "🧪", estimated_duration: 6, has_skill: true },
  { id: "performance-optimizer", name: "Performance Optimization Agent", role: "Profiling & Bottleneck Analysis", description: "Identifies performance bottlenecks and recommends optimizations for speed.", pipeline_type: "custom", order: 6, icon: "⚡", estimated_duration: 5, has_skill: true },
  { id: "documentation-agent", name: "Documentation Agent", role: "API & Technical Writing", description: "Writes clear documentation including README, API guides, and setup instructions.", pipeline_type: "custom", order: 7, icon: "📚", estimated_duration: 7, has_skill: true },
  { id: "report-generator", name: "Executive Reporting Agent", role: "Insights & Recommendations", description: "Creates executive-ready reports with key metrics, insights, and recommendations.", pipeline_type: "custom", order: 8, icon: "📋", estimated_duration: 5, has_skill: true },
];

export const ALL_LIBRARY_AGENTS: AgentDef[] = [...LIBRARY_AGENTS, ...CUSTOM_AGENTS];

export const PIPELINE_CATEGORIES = [
  { key: "all", label: "All", count: 20 },
  { key: "user_stories", label: "User Stories", count: 6 },
  { key: "ppt", label: "PPT", count: 4 },
  { key: "prototype", label: "Prototype", count: 4 },
  { key: "app_builder", label: "App Builder", count: 4 },
  { key: "custom", label: "Custom", count: 8 },
] as const;

export const PIPELINE_COLORS: Record<string, { bg: string; text: string }> = {
  user_stories: { bg: "rgba(79, 195, 247, 0.15)", text: "#4FC3F7" },
  ppt: { bg: "rgba(255, 167, 38, 0.15)", text: "#FFA726" },
  prototype: { bg: "rgba(129, 199, 132, 0.15)", text: "#81C784" },
  app_builder: { bg: "rgba(255, 183, 77, 0.15)", text: "#FFB74D" },
  custom: { bg: "rgba(186, 104, 200, 0.15)", text: "#BA68C8" },
};
