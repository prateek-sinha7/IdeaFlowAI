import { describe, expect, it } from "vitest";
import { fireEvent, renderWithProviders, screen, within } from "@/test/renderWithProviders";
import { SkillsHooksProvider } from "@/context/SkillsHooksContext";
import type { GlobalSkillEntry } from "@/store/api/skills";
import type { GlobalHookEntry } from "@/store/api/hooks";
import type { AgentDef } from "@/types/index";

// ─────────────────────────────────────────────────────────────────
// Shell-fidelity contract for the Library page (plan 40-03).
//
// The mock (Hexaware Workspace v2.dc.html :300) leads the Library surface
// with a "Library" h1 + item-count line + search, THEN the Agents/Skills/Hooks
// tab chrome, THEN each tab's card grid. This test pins the mock composition:
//   1. The "Library" h1 renders BEFORE the tablist in DOM order (header leads).
//   2. The item-count line renders under the h1.
//   3. Each of the three tabs renders its card grid (agents/skills/hooks).
// The pre-restyle tabs-lead layout is RED against assertion (1).
// ─────────────────────────────────────────────────────────────────

import { LibraryPage } from "./LibraryPage";

const AGENT_A = "Domain Discovery Agent";
const SKILL_A = "Brainstorming Ideas Into Designs";

// Mock data fixtures for tests
const MOCK_AGENT_A: AgentDef = {
  id: "domain_discovery",
  name: AGENT_A,
  role: "Market & Persona Research",
  description: "Discovers market opportunities and personas through research.",
  pipeline_type: "discovery",
  order: 0,
  icon: "zap",
  estimated_duration: 300,
  has_skill: true,
  prompt_body: "You are a discovery agent.",
};

const MOCK_SKILL_A: GlobalSkillEntry = {
  id: "brainstorm_skill",
  name: SKILL_A,
  display_name: SKILL_A,
  description: "Brainstorm design ideas",
  content: "# Brainstorming Skill\n\nThis skill helps generate design ideas.",
  category: "planning",
  isBeta: false,
  tags: ["creative", "design"],
  compatible_agents: ["domain_discovery"],
};

const MOCK_HOOK_A: GlobalHookEntry = {
  id: "pretooluse_hook",
  name: "Pre Tool Use Hook",
  display_name: "Pre Tool Use Hook",
  description: "Runs before tool execution",
  content: "Hook content",
  event: "PreToolUse",
  trigger: "Before any tool is executed",
  compatible_agents: ["domain_discovery"],
  tags: ["execution"],
};

const MOCK_HOOK_B: GlobalHookEntry = {
  id: "posttooluse_hook",
  name: "Post Tool Use Hook",
  display_name: "Post Tool Use Hook",
  description: "Runs after tool execution",
  content: "Hook content",
  event: "PostToolUse",
  trigger: "After tool completes",
  compatible_agents: ["domain_discovery"],
  tags: ["execution"],
};

const MOCK_WORKFLOW = {
  id: "discovery",
  name: "Discovery Workflow",
  display_name: "Discovery Workflow",
  short_name: "Discovery",
  description: "Market discovery",
  step_count: 1,
  steps: [{ agent_id: "domain_discovery", name: AGENT_A, gate: null }],
  user_launchable: true,
  is_beta: false,
};

describe("LibraryPage 40-03 — mock composition (header leads, tab grids)", () => {
  const createPreloadedState = () => ({
    agents: {
      agents: [MOCK_AGENT_A],
      totalCount: 1,
      pipelines: { discovery: 1 },
      status: "succeeded" as const,
      error: null,
    },
    skills: {
      skills: [MOCK_SKILL_A],
      totalCount: 1,
      skillCategories: [{ id: "planning", label: "Planning" }],
      status: "succeeded" as const,
      error: null,
    },
    hooks: {
      hooks: [MOCK_HOOK_A, MOCK_HOOK_B],
      totalCount: 2,
      hookEvents: [
        { id: "PreToolUse", label: "PreToolUse" },
        { id: "PostToolUse", label: "PostToolUse" },
      ],
      status: "succeeded" as const,
      error: null,
    },
    global: {
      workflows: [MOCK_WORKFLOW],
      workflowsStatus: "succeeded" as const,
      workflowsError: null,
      recentRuns: [],
      recentRunsStatus: "idle" as const,
      recentRunsError: null,
    },
    auth: {
      token: null,
      user: null,
      isAuthenticated: false,
    },
  });

  it("renders the 'Library' h1 BEFORE the tablist (header leads, per the mock)", () => {
    renderWithProviders(<LibraryPage />, { preloadedState: createPreloadedState() });

    const h1 = screen.getByRole("heading", { level: 1, name: /^Library$/ });
    const tablist = screen.getByRole("tablist");

    expect(h1).toBeInTheDocument();
    expect(tablist).toBeInTheDocument();

    // h1 must precede the tablist in document order → the header leads.
    const order = h1.compareDocumentPosition(tablist);
    expect(order & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("renders an item-count line beneath the h1", () => {
    renderWithProviders(<LibraryPage />, { preloadedState: createPreloadedState() });
    // "N agents · M skills · K hooks" — the mock's libCountLine.
    expect(screen.getByText(/\d+ agents · \d+ skills · \d+ hooks/)).toBeInTheDocument();
  });

  it("renders the Agents card grid on mount", () => {
    renderWithProviders(<LibraryPage />, { preloadedState: createPreloadedState() });
    expect(screen.getByText(AGENT_A)).toBeInTheDocument();
  });

  it("renders the Skills card grid when the Skills tab is active", () => {
    renderWithProviders(<LibraryPage />, { preloadedState: createPreloadedState() });
    fireEvent.click(screen.getByRole("tab", { name: /skills/i }));
    expect(screen.getByText(SKILL_A)).toBeInTheDocument();
  });

  it("renders the Hooks card grid when the Hooks tab is active", () => {
    renderWithProviders(<LibraryPage />, { preloadedState: createPreloadedState() });
    fireEvent.click(screen.getByRole("tab", { name: /hooks/i }));
    // At least one hook event badge is visible in the hooks grid.
    expect(screen.getAllByText(/PreToolUse|PostToolUse|Stop|SessionStart|SessionEnd/).length).toBeGreaterThan(0);
  });
});

// ─────────────────────────────────────────────────────────────────
// Plan 41-07 — the Library agent-detail opens as a right-side DRAWER
// (mock `drawerOpen`, Hexaware Workspace v2.dc.html :709). Clicking an
// agent card opens the restructured shared AgentCapabilitiesModal in its
// drawer form, surfacing the Overview / Skills / Hooks / Config tabs.
// This closes the Phase-40 ND-Z deferral (SHELL-04 Agent-drawer clause).
// ─────────────────────────────────────────────────────────────────

describe("LibraryPage 41-07 — agent-detail right-side drawer (ND-Z resolved)", () => {
  const createPreloadedState = () => ({
    agents: {
      agents: [MOCK_AGENT_A],
      totalCount: 1,
      pipelines: { discovery: 1 },
      status: "succeeded" as const,
      error: null,
    },
    skills: {
      skills: [MOCK_SKILL_A],
      totalCount: 1,
      skillCategories: [{ id: "planning", label: "Planning" }],
      status: "succeeded" as const,
      error: null,
    },
    hooks: {
      hooks: [MOCK_HOOK_A, MOCK_HOOK_B],
      totalCount: 2,
      hookEvents: [
        { id: "PreToolUse", label: "PreToolUse" },
        { id: "PostToolUse", label: "PostToolUse" },
      ],
      status: "succeeded" as const,
      error: null,
    },
    global: {
      workflows: [MOCK_WORKFLOW],
      workflowsStatus: "succeeded" as const,
      workflowsError: null,
      recentRuns: [],
      recentRunsStatus: "idle" as const,
      recentRunsError: null,
    },
    auth: {
      token: null,
      user: null,
      isAuthenticated: false,
    },
  });

  function openFirstAgentDrawer() {
    renderWithProviders(
      <SkillsHooksProvider>
        <LibraryPage />
      </SkillsHooksProvider>,
      { preloadedState: createPreloadedState() },
    );
    // Click the first agent card (the mock's agent-detail affordance).
    fireEvent.click(screen.getByText(AGENT_A));
    return screen.getByTestId("agent-drawer");
  }

  it("opens the agent-detail as a right-side drawer panel on agent-select", () => {
    const drawer = openFirstAgentDrawer();
    expect(drawer).toBeInTheDocument();
    // The panel is a labelled dialog for the selected agent.
    expect(drawer).toHaveAttribute("role", "dialog");
    expect(drawer).toHaveAccessibleName(new RegExp(AGENT_A, "i"));
  });

  it("presents exactly the four tabs Overview / Skills / Hooks / Config in the drawer", () => {
    const drawer = openFirstAgentDrawer();
    const tabs = within(drawer);
    expect(tabs.getByRole("tab", { name: /overview/i })).toBeInTheDocument();
    expect(tabs.getByRole("tab", { name: /skills/i })).toBeInTheDocument();
    expect(tabs.getByRole("tab", { name: /hooks/i })).toBeInTheDocument();
    expect(tabs.getByRole("tab", { name: /config/i })).toBeInTheDocument();
    expect(tabs.getAllByRole("tab")).toHaveLength(4);
  });

  it("Overview body matches the mock: 'What it does', Role-in-pipeline with the ROLE NAME, and a skill-support chip (bound to real data)", () => {
    const drawer = openFirstAgentDrawer();
    const body = within(drawer);
    // Change 1: mock heading label.
    expect(body.getByText(/what it does/i)).toBeInTheDocument();
    // Change 2: "Role in pipeline" shows the agent's ROLE NAME (not "Step N").
    // AGENT_A ("Domain Discovery Agent") has role "Market & Persona Research" —
    // it appears in the header AND the Overview role-in-pipeline block.
    expect(body.getByText(/role in pipeline/i)).toBeInTheDocument();
    expect(body.getAllByText("Market & Persona Research").length).toBeGreaterThanOrEqual(2);
    expect(body.queryByText(/^Step \d+$/)).toBeNull();
    // Change 3: AGENT_A declares has_skill → the Skill-support chip renders.
    expect(body.getByText(/skill support/i)).toBeInTheDocument();
  });

  it("Overview surfaces the system prompt READ-ONLY (ND-7/LOCK-E): no textarea, no Save/Reset", () => {
    const drawer = openFirstAgentDrawer();
    const body = within(drawer);
    // Change 4: the shared read-only System Prompt surface (AgentPromptSection
    // surfaceOnly) is present in the Overview.
    expect(body.getByText(/system prompt/i)).toBeInTheDocument();
    // Surface-only stance: no editable field and no write affordances.
    expect(drawer.querySelector("textarea")).toBeNull();
    expect(body.queryByRole("button", { name: /save (override|agent)/i })).toBeNull();
    expect(body.queryByRole("button", { name: /revert to default/i })).toBeNull();
  });
});
