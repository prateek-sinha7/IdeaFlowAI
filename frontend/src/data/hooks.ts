export interface HookDef {
  id: string;
  name: string;
  description: string;
  source: "ecc" | "superpowers" | "gsd";
  sourceLabel: string;
  event: "PreToolUse" | "PostToolUse" | "Stop" | "SessionStart" | "SessionEnd";
  trigger: string;
  compatible_agents: string[];
  tags: string[];
}

export const HOOKS: HookDef[] = [
  {
    id: "ecc-post-quality-gate",
    name: "Quality Gate",
    description: "Runs lint, typecheck, and test suite after every file edit. Blocks progression if quality checks fail.",
    source: "ecc",
    sourceLabel: "ECC",
    event: "PostToolUse",
    trigger: "After Edit / Write / MultiEdit",
    compatible_agents: ["app-code-compliance", "app-test-compliance", "app-code-generator", "app-feature-implementation", "mulesoft-code-compliance", "dotnet-code-compliance"],
    tags: ["lint", "typecheck", "quality", "ci"],
  },
  {
    id: "ecc-pre-config-protection",
    name: "Config Protection",
    description: "Blocks modifications to linter and formatter config files. Steers the agent to fix code instead of weakening quality gates.",
    source: "ecc",
    sourceLabel: "ECC",
    event: "PreToolUse",
    trigger: "Before Write / Edit / MultiEdit on config files",
    compatible_agents: ["app-code-compliance", "app-devops", "mulesoft-code-compliance", "dotnet-code-compliance"],
    tags: ["config", "protection", "quality", "lint"],
  },
  {
    id: "ecc-stop-format-typecheck",
    name: "Format + Typecheck on Stop",
    description: "Batch formats (Biome/Prettier) and typechecks all JS/TS files edited in the response. Runs once at Stop instead of after every edit.",
    source: "ecc",
    sourceLabel: "ECC",
    event: "Stop",
    trigger: "End of each agent response — all edited JS/TS files",
    compatible_agents: ["app-code-generator", "app-feature-implementation", "app-ux-design", "html-prototype-builder", "prototype-polisher"],
    tags: ["format", "typecheck", "typescript", "prettier", "biome"],
  },
  {
    id: "ecc-stop-console-log",
    name: "Console.log Check",
    description: "Warns about console.log statements left in modified files after each response. Keeps production code clean.",
    source: "ecc",
    sourceLabel: "ECC",
    event: "Stop",
    trigger: "End of each agent response — all edited JS/TS files",
    compatible_agents: ["app-code-generator", "app-feature-implementation", "html-prototype-builder"],
    tags: ["console", "cleanup", "code-quality"],
  },
  {
    id: "ecc-session-start",
    name: "Session Context Loader",
    description: "Loads previous session state and detects package manager on new session start. Ensures continuity across sessions.",
    source: "ecc",
    sourceLabel: "ECC",
    event: "SessionStart",
    trigger: "Every new agent session",
    compatible_agents: ["domain-analyst", "requirements-analyst", "app-user-stories", "epic-architect", "app-code-generator"],
    tags: ["session", "context", "memory", "continuity"],
  },
  {
    id: "ecc-stop-session-end",
    name: "Session State Persistence",
    description: "Persists session state after each response so context survives across sessions. Enables long-running multi-session workflows.",
    source: "ecc",
    sourceLabel: "ECC",
    event: "Stop",
    trigger: "End of each agent response",
    compatible_agents: ["domain-analyst", "requirements-analyst", "app-user-stories", "epic-architect", "app-code-generator", "app-feature-implementation"],
    tags: ["session", "persistence", "memory", "state"],
  },
  {
    id: "ecc-pre-gateguard",
    name: "GateGuard: Fact Force",
    description: "Blocks the first Edit/Write per file and demands investigation (importers, data schemas, user instructions) before allowing changes.",
    source: "ecc",
    sourceLabel: "ECC",
    event: "PreToolUse",
    trigger: "Before first Edit / Write / MultiEdit on each file",
    compatible_agents: ["app-code-generator", "app-feature-implementation", "mulesoft-feature-coding", "dotnet-feature-coding", "dotnet-modernization"],
    tags: ["safety", "investigation", "gateguard", "pre-check"],
  },
  {
    id: "ecc-post-design-quality",
    name: "Design Quality Check",
    description: "Warns when frontend edits drift toward generic template-looking UI. Keeps visual output distinctive and intentional.",
    source: "ecc",
    sourceLabel: "ECC",
    event: "PostToolUse",
    trigger: "After Edit / Write on frontend files",
    compatible_agents: ["app-ux-design", "html-prototype-builder", "prototype-polisher", "ppt-slide-architect"],
    tags: ["design", "ui", "quality", "frontend"],
  },
];

export const HOOK_EVENTS = [
  { id: "all", label: "All Events" },
  { id: "PreToolUse", label: "Pre Tool Use" },
  { id: "PostToolUse", label: "Post Tool Use" },
  { id: "Stop", label: "On Stop" },
  { id: "SessionStart", label: "Session Start" },
  { id: "SessionEnd", label: "Session End" },
] as const;
