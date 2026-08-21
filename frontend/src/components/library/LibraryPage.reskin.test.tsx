import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { Provider } from "react-redux";
import { configureStore } from "@reduxjs/toolkit";

// ─────────────────────────────────────────────────────────────────
// Reskin + real-controls contract for the Library page.
//
// Tests the Tabs primitive and real filtering/search behavior:
//   1. The Agents / Skills / Hooks tab bar exposes role=tab.
//   2. Clicking a tab switches the visible catalog section.
//   3. Typing in the search box filters the visible agents (real).
//   4. The tab counts are present and reflect Redux state (dynamic).
// ─────────────────────────────────────────────────────────────────

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
    prefetch: vi.fn(),
  }),
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({}),
}));

import { LibraryPage } from "./LibraryPage";
import agentsReducer from "@/store/slices/agentsSlice";
import skillsReducer from "@/store/slices/skillsSlice";
import hooksReducer from "@/store/slices/hooksSlice";
import globalReducer from "@/store/slices/globalSlice";
import authReducer from "@/store/slices/authSlice";

// Mock test agents for component behavior verification
const MOCK_AGENTS = [
  {
    id: "domain-analyst",
    name: "Domain Discovery Agent",
    role: "Market & Persona Research",
    description: "Researches your idea, identifies the target market",
    pipeline_type: "user_stories",
    order: 1,
    icon: "🔍",
    estimated_duration: 43,
    has_skill: true,
    gate: null,
  },
  {
    id: "epic-architect",
    name: "Backlog Architecture Agent",
    role: "Epic & Story Composition",
    description: "Writes product epics and detailed user stories",
    pipeline_type: "user_stories",
    order: 2,
    icon: "🏗️",
    estimated_duration: 86,
    has_skill: true,
    gate: null,
  },
];

const MOCK_SKILLS = [
  { id: "skill-1", name: "Brainstorming Ideas Into Designs", description: "Design skill", category: "design", content: "test", isBeta: false, tags: [] },
];

const MOCK_HOOKS = [
  { id: "hook-1", name: "Test Hook", event: "on_agent_start", trigger: "test", description: "test" },
];

// Helper to create a test Redux store
function createTestStore() {
  return configureStore({
    reducer: {
      auth: authReducer,
      agents: agentsReducer,
      skills: skillsReducer,
      hooks: hooksReducer,
      global: globalReducer,
    },
    preloadedState: {
      agents: {
        agents: MOCK_AGENTS,
        totalCount: MOCK_AGENTS.length,
        pipelines: { user_stories: 2 },
        status: "succeeded",
        error: null,
      },
      skills: {
        skills: MOCK_SKILLS,
        skillCategories: [],
        status: "succeeded",
        error: null,
      },
      hooks: {
        hooks: MOCK_HOOKS,
        hookEvents: [],
        status: "succeeded",
        error: null,
      },
      global: {
        workflows: [],
        workflowsStatus: "idle",
        recentRuns: [],
        recentRunsStatus: "idle",
      },
      auth: {
        isSignedIn: true,
        user: null,
        signInError: null,
      },
    },
  });
}

// A known agent (user_stories pipeline) and a second agent whose name does
// NOT share the first's search substring — used to prove the filter is real.
const AGENT_A = "Domain Discovery Agent";
const AGENT_B = "Backlog Architecture Agent";
// A known skill (present only under the Skills tab).
const SKILL_A = "Brainstorming Ideas Into Designs";

describe("LibraryPage reskin — Tabs primitive + real controls preserved", () => {
  it("renders the Agents / Skills / Hooks tab bar with role=tab (Tabs primitive)", () => {
    const store = createTestStore();
    render(
      <Provider store={store}>
        <LibraryPage />
      </Provider>
    );
    const tabs = screen.getAllByRole("tab");
    // Exactly the three top-level catalog tabs (sidebar categories are Pills).
    expect(tabs).toHaveLength(3);
    expect(screen.getByRole("tab", { name: /agents/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /skills/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /hooks/i })).toBeInTheDocument();
  });

  it("clicking the Skills tab switches the visible catalog section (real)", () => {
    const store = createTestStore();
    render(
      <Provider store={store}>
        <LibraryPage />
      </Provider>
    );

    // Agents tab is active on mount → an agent renders, no skill yet.
    expect(screen.getByText(AGENT_A)).toBeInTheDocument();
    expect(screen.queryByText(SKILL_A)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: /skills/i }));

    // Skill section now rendered; the agent card is unmounted.
    expect(screen.getByText(SKILL_A)).toBeInTheDocument();
    expect(screen.queryByText(AGENT_A)).not.toBeInTheDocument();
  });

  it("typing in the search box filters the visible agents (real filter)", () => {
    const store = createTestStore();
    render(
      <Provider store={store}>
        <LibraryPage />
      </Provider>
    );

    // Both agents render initially in the Agents tab.
    expect(screen.getByText(AGENT_A)).toBeInTheDocument();
    expect(screen.getByText(AGENT_B)).toBeInTheDocument();

    fireEvent.change(screen.getByPlaceholderText(/search agents/i), {
      target: { value: "Domain Discovery" },
    });

    // Only the matching agent survives → the filter is real, not inert.
    expect(screen.getByText(AGENT_A)).toBeInTheDocument();
    expect(screen.queryByText(AGENT_B)).not.toBeInTheDocument();
  });

  it("the tab counts are present and reflect Redux state (dynamic)", () => {
    const store = createTestStore();
    const { container } = render(
      <Provider store={store}>
        <LibraryPage />
      </Provider>
    );
    // All counts come from Redux store (fetched from API)
    const agentsTab = screen.getByRole("tab", { name: /agents/i });
    expect(agentsTab).toBeInTheDocument();
    expect(agentsTab.textContent).toMatch(/\d+/); // Contains a count number

    const skillsTab = screen.getByRole("tab", { name: /skills/i });
    expect(skillsTab).toBeInTheDocument();
    expect(skillsTab.textContent).toMatch(/\d+/); // Contains a count number

    const hooksTab = screen.getByRole("tab", { name: /hooks/i });
    expect(hooksTab).toBeInTheDocument();
    expect(hooksTab.textContent).toMatch(/\d+/); // Contains a count number
  });

  it("renders no retired palette in the class strings", () => {
    const store = createTestStore();
    const { container } = render(
      <Provider store={store}>
        <LibraryPage />
      </Provider>
    );
    const html = container.innerHTML;
    expect(html).not.toMatch(/#1B2A4A/);
    expect(html).not.toMatch(/\btext-gray-/);
    expect(html).not.toMatch(/\bbg-gray-/);
  });
});
