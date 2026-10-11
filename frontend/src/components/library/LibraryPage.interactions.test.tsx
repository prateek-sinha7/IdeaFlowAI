import { Component, act, type ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import { renderWithProviders, screen, waitFor, within } from "@/test/renderWithProviders";
import type { GlobalSkillEntry } from "@/store/api/skills";
import type { GlobalHookEntry } from "@/store/api/hooks";
import type { AgentDef } from "@/types/index";

// ─────────────────────────────────────────────────────────────────
// Interaction + branch coverage for LibraryPage: category/search filtering and
// the URL write-through, the loading / failed / empty grid states, beta
// ("Coming Soon") gating, keyboard activation of cards, the skill and hook
// detail modals, and /library/{type}/{slug} deep links.
//
// next/navigation is the only boundary mocked. It is backed by a tiny in-memory
// URL so router.push/replace change what useParams()/useSearchParams() report —
// the same round trip the real catch-all route performs — which is what lets
// the page's URL-driven modal open/close effects run for real.
// ─────────────────────────────────────────────────────────────────

const nav = vi.hoisted(() => {
  let url = "/library";
  const listeners = new Set<() => void>();
  return {
    getUrl: () => url,
    setUrl: (next: string) => {
      url = next;
      listeners.forEach((listener) => listener());
    },
    subscribe: (listener: () => void) => {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    push: vi.fn<(target: string) => void>(),
    replace: vi.fn<(target: string) => void>(),
  };
});

vi.mock("next/navigation", async () => {
  const { useSyncExternalStore } = await import("react");
  const parsed = new Map<string, { params: { view: string[] }; search: URLSearchParams }>();
  const parse = (url: string) => {
    let entry = parsed.get(url);
    if (!entry) {
      const { pathname, search } = new URL(url, "http://localhost");
      entry = {
        params: { view: pathname.split("/").filter(Boolean) },
        search: new URLSearchParams(search),
      };
      parsed.set(url, entry);
    }
    return entry;
  };
  const router = { push: nav.push, replace: nav.replace, prefetch: vi.fn() };
  const useCurrentUrl = () => useSyncExternalStore(nav.subscribe, nav.getUrl, nav.getUrl);
  return {
    useRouter: () => router,
    useSearchParams: () => parse(useCurrentUrl()).search,
    useParams: () => parse(useCurrentUrl()).params,
    notFound: () => {
      throw new Error("NEXT_NOT_FOUND");
    },
  };
});

import { LibraryPage } from "./LibraryPage";

// ─── Fixtures ────────────────────────────────────────────────────

const agent = (overrides: Partial<AgentDef> & Pick<AgentDef, "id" | "name">): AgentDef => ({
  role: "Role",
  description: "Description",
  pipeline_type: "user_stories",
  order: 0,
  icon: "zap",
  estimated_duration: 60,
  has_skill: false,
  prompt_body: "",
  ...overrides,
});

const DISCOVERY = agent({
  id: "domain_discovery",
  name: "Domain Discovery Agent",
  role: "Market Research",
  description: "Researches the target market",
  order: 1,
});
const BACKLOG = agent({
  id: "backlog_architect",
  name: "Backlog Architecture Agent",
  role: "Epic Composition",
  description: "Writes epics and stories",
  order: 2,
});
const PLANNER = agent({
  id: "prototype_planner",
  name: "Prototype Planner Agent",
  role: "UI Planning",
  description: "Plans screens",
  pipeline_type: ["prototype", "user_stories"],
});
const CUSTOM = agent({
  id: "custom_helper",
  name: "Custom Helper Agent",
  role: "Helper",
  description: "A user-defined helper",
  pipeline_type: "custom",
});
const BETA_AGENT = agent({
  id: "legacy_revision",
  name: "Legacy Revision Agent",
  role: "Revision",
  description: "Revises decks",
  pipeline_type: "ppt_revision",
});
const AGENTS = [DISCOVERY, BACKLOG, PLANNER, CUSTOM, BETA_AGENT];

const SKILL_PLANNING: GlobalSkillEntry = {
  id: "brainstorm_skill",
  name: "Brainstorm",
  display_name: "Brainstorming Ideas Into Designs",
  description: "Brainstorm design ideas",
  content: "# Brainstorming\n\nGenerate design ideas.",
  category: "planning",
  isBeta: false,
  tags: ["creative", "design", "ideas", "overflow"],
  compatible_agents: [],
};
const SKILL_SECURITY: GlobalSkillEntry = {
  id: "security_audit",
  name: "Security Audit Checklist",
  display_name: "",
  description: "Audit code for vulnerabilities",
  content: "Check every input.",
  category: "security",
  isBeta: false,
  tags: ["audit"],
  compatible_agents: [],
};
const SKILL_BETA: GlobalSkillEntry = {
  id: "telemetry_beta",
  name: "Advanced Telemetry",
  display_name: "",
  description: "Trace everything",
  content: "Beta content",
  category: "research",
  isBeta: true,
  tags: ["tracing"],
  compatible_agents: [],
};
const SKILLS = [SKILL_PLANNING, SKILL_SECURITY, SKILL_BETA];
const SKILL_CATEGORIES = [
  { id: "all", label: "All" },
  { id: "planning", label: "Planning", icon: "planning" },
  { id: "security", label: "Security" },
];

const hook = (overrides: Partial<GlobalHookEntry> & Pick<GlobalHookEntry, "id" | "name">): GlobalHookEntry => ({
  display_name: overrides.name,
  description: "Description",
  content: "content",
  event: "PreToolUse",
  trigger: "Trigger",
  compatible_agents: [],
  tags: [],
  ...overrides,
});
const HOOK_PRE = hook({
  id: "pre_hook",
  name: "Pre Tool Use Hook",
  description: "Runs before tool execution",
  event: "PreToolUse",
  trigger: "Before any tool is executed",
  compatible_agents: ["domain_discovery", "backlog_architect"],
  tags: ["execution"],
});
const HOOK_POST = hook({
  id: "post_hook",
  name: "Post Tool Use Hook",
  description: "Validates output afterwards",
  event: "PostToolUse",
  trigger: "After a tool completes",
  compatible_agents: ["a1", "a2", "a3", "a4"],
  tags: ["validation"],
});
const HOOK_CUSTOM = hook({
  id: "custom_hook",
  name: "Custom Event Hook",
  description: "Reacts to a bespoke event",
  event: "CustomEvent",
  trigger: "On the custom event",
  compatible_agents: ["a1"],
  tags: ["custom"],
});
const HOOKS = [HOOK_PRE, HOOK_POST, HOOK_CUSTOM];
const HOOK_EVENTS = [
  { id: "all", label: "All" },
  { id: "PreToolUse", label: "PreToolUse" },
  { id: "PostToolUse", label: "PostToolUse" },
  { id: "CustomEvent", label: "CustomEvent" },
];

const workflow = (id: string, overrides: Record<string, unknown> = {}) => ({
  id,
  name: id,
  display_name: id,
  short_name: id,
  description: "",
  step_count: 1,
  steps: [],
  user_launchable: true,
  is_beta: false,
  ...overrides,
});

type Status = "idle" | "loading" | "succeeded" | "failed";
interface StateOptions {
  agents?: AgentDef[];
  skills?: GlobalSkillEntry[];
  hooks?: GlobalHookEntry[];
  agentsStatus?: Status;
  skillsStatus?: Status;
  hooksStatus?: Status;
}

function buildState({
  agents = AGENTS,
  skills = SKILLS,
  hooks = HOOKS,
  agentsStatus = "succeeded",
  skillsStatus = "succeeded",
  hooksStatus = "succeeded",
}: StateOptions = {}) {
  return {
    agents: { agents, totalCount: agents.length, pipelines: {}, status: agentsStatus, error: null },
    skills: {
      skills,
      totalCount: skills.length,
      skillCategories: SKILL_CATEGORIES,
      status: skillsStatus,
      error: null,
    },
    hooks: { hooks, totalCount: hooks.length, hookEvents: HOOK_EVENTS, status: hooksStatus, error: null },
    global: {
      workflows: [
        workflow("user_stories", { name: "User Stories" }),
        workflow("prototype", { name: "", display_name: "Prototype Studio" }),
        workflow("ppt", { name: "", display_name: null }),
        workflow("ppt_revision", { name: "PPT Revision", is_beta: true }),
        workflow("chat", { name: "Chat", user_launchable: false }),
      ],
      workflowsStatus: "succeeded" as const,
      workflowsError: null,
      recentRuns: [],
      recentRunsStatus: "idle" as const,
      recentRunsError: null,
    },
    auth: { token: null, user: null, isAuthenticated: false },
  };
}

type PreloadedState = NonNullable<NonNullable<Parameters<typeof renderWithProviders>[1]>["preloadedState"]>;

function renderLibrary(url = "/library", options: StateOptions = {}) {
  nav.setUrl(url);
  return renderWithProviders(<LibraryPage />, {
    preloadedState: buildState(options) as PreloadedState,
  });
}

// Stand-in for Next's not-found boundary: notFound() throws, the boundary shows its fallback.
class NotFoundBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    return this.state.failed ? <p>boundary: not found</p> : this.props.children;
  }
}

function renderLibraryInBoundary(url: string, options: StateOptions = {}) {
  nav.setUrl(url);
  return renderWithProviders(
    <NotFoundBoundary>
      <LibraryPage />
    </NotFoundBoundary>,
    { preloadedState: buildState(options) as PreloadedState },
  );
}

const searchBox = (name: RegExp) => screen.getByRole("textbox", { name });

beforeEach(() => {
  nav.push.mockReset();
  nav.replace.mockReset();
  nav.push.mockImplementation((target) => nav.setUrl(target));
  nav.replace.mockImplementation((target) => nav.setUrl(target));
  nav.setUrl("/library");
});

afterEach(() => {
  vi.restoreAllMocks();
});

// ─── Header + URL seeding ────────────────────────────────────────

describe("LibraryPage header and URL seeding", () => {
  it("shows the combined item count under the heading", () => {
    renderLibrary();
    expect(
      screen.getByText("5 agents · 3 skills · 3 hooks · tap any item to see its capabilities"),
    ).toBeInTheDocument();
  });

  it("opens the Skills tab when the URL carries ?tab=skills", () => {
    renderLibrary("/library?tab=skills");
    expect(screen.getByRole("tab", { name: /skills/i })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText("Brainstorming Ideas Into Designs")).toBeInTheDocument();
    expect(screen.queryByText(DISCOVERY.name)).not.toBeInTheDocument();
  });

  it("opens the Hooks tab when the URL carries ?tab=hooks", () => {
    renderLibrary("/library?tab=hooks");
    expect(screen.getByRole("tab", { name: /hooks/i })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText(HOOK_PRE.name)).toBeInTheDocument();
  });

  it("stays on the Agents tab when ?tab= is not a known tab", () => {
    renderLibrary("/library?tab=bogus");
    expect(screen.getByRole("tab", { name: /agents/i })).toHaveAttribute("aria-selected", "true");
  });

  it("seeds the agent category and search text from the URL", () => {
    renderLibrary("/library?category=user_stories&search=backlog");
    expect(searchBox(/search agents/i)).toHaveValue("backlog");
    expect(screen.getByText(BACKLOG.name)).toBeInTheDocument();
    expect(screen.queryByText(DISCOVERY.name)).not.toBeInTheDocument();
  });

  it("seeds the skill category and search text from the URL", () => {
    renderLibrary("/library?tab=skills&category=security&search=audit");
    expect(searchBox(/search skills/i)).toHaveValue("audit");
    expect(screen.getByText(SKILL_SECURITY.name)).toBeInTheDocument();
    expect(screen.queryByText("Brainstorming Ideas Into Designs")).not.toBeInTheDocument();
  });

  it("seeds the hook event and search text from the URL", () => {
    renderLibrary("/library?tab=hooks&category=PreToolUse&search=before");
    expect(searchBox(/search hooks/i)).toHaveValue("before");
    expect(screen.getByText(HOOK_PRE.name)).toBeInTheDocument();
    expect(screen.queryByText(HOOK_POST.name)).not.toBeInTheDocument();
  });
});

// ─── Tabs ────────────────────────────────────────────────────────

describe("LibraryPage tab switching", () => {
  it("writes the newly active tab to the URL when switching tabs", async () => {
    const user = userEvent.setup();
    renderLibrary();

    await user.click(screen.getByRole("tab", { name: /skills/i }));
    expect(nav.replace).toHaveBeenLastCalledWith("/library?tab=skills");

    await user.click(screen.getByRole("tab", { name: /hooks/i }));
    expect(nav.replace).toHaveBeenLastCalledWith("/library?tab=hooks");
  });

  it("restores the agents category in the URL when returning to the Agents tab", async () => {
    const user = userEvent.setup();
    renderLibrary();

    await user.click(screen.getByRole("button", { name: /^User Stories\s*3$/ }));
    await user.click(screen.getByRole("tab", { name: /skills/i }));
    await user.click(screen.getByRole("tab", { name: /agents/i }));

    expect(nav.replace).toHaveBeenLastCalledWith("/library?category=user_stories");
  });

  it("carries the skills category in the URL when switching to the Skills tab", async () => {
    const user = userEvent.setup();
    renderLibrary("/library?tab=skills&category=security");

    await user.click(screen.getByRole("tab", { name: /hooks/i }));
    await user.click(screen.getByRole("tab", { name: /skills/i }));

    expect(nav.replace).toHaveBeenLastCalledWith("/library?tab=skills&category=security");
  });
});

// ─── Agents grid ─────────────────────────────────────────────────

describe("LibraryPage agents grid", () => {
  it("labels category chips from workflow name, display name, or id and excludes beta and non-launchable workflows", () => {
    renderLibrary();
    expect(screen.getByRole("button", { name: /^All\s*5$/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^User Stories\s*3$/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Prototype Studio\s*1$/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^ppt\s*0$/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Custom\s*1$/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /PPT Revision/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Chat/ })).not.toBeInTheDocument();
  });

  it("filters agents to a category and writes it to the URL when a chip is clicked", async () => {
    const user = userEvent.setup();
    renderLibrary();

    await user.click(screen.getByRole("button", { name: /^Custom\s*1$/ }));

    expect(screen.getByText(CUSTOM.name)).toBeInTheDocument();
    expect(screen.queryByText(DISCOVERY.name)).not.toBeInTheDocument();
    expect(nav.replace).toHaveBeenLastCalledWith("/library?category=custom");
  });

  it("matches multi-pipeline agents under each pipeline they declare", async () => {
    const user = userEvent.setup();
    renderLibrary();

    await user.click(screen.getByRole("button", { name: /^Prototype Studio\s*1$/ }));

    expect(screen.getByText(PLANNER.name)).toBeInTheDocument();
    expect(screen.queryByText(BACKLOG.name)).not.toBeInTheDocument();
  });

  it("drops the category from the URL when the All chip is selected again", async () => {
    const user = userEvent.setup();
    renderLibrary("/library?category=custom");

    await user.click(screen.getByRole("button", { name: /^All\s*5$/ }));

    expect(nav.replace).toHaveBeenLastCalledWith("/library");
    expect(screen.getByText(DISCOVERY.name)).toBeInTheDocument();
  });

  it.each([
    ["name", "backlog architecture", BACKLOG.name],
    ["description", "researches the target", DISCOVERY.name],
    ["role", "ui planning", PLANNER.name],
  ])("finds an agent by its %s regardless of case", async (_field, query, expectedName) => {
    const user = userEvent.setup();
    renderLibrary();

    await user.type(searchBox(/search agents/i), query);

    expect(screen.getByText(expectedName)).toBeInTheDocument();
    expect(screen.queryByText(DISCOVERY.name === expectedName ? BACKLOG.name : DISCOVERY.name)).not.toBeInTheDocument();
  });

  it("writes the search text to the URL as the user types", async () => {
    const user = userEvent.setup();
    renderLibrary();

    await user.type(searchBox(/search agents/i), "plan");

    expect(nav.replace).toHaveBeenLastCalledWith("/library?search=plan");
  });

  it("shows a no-match message and restores the list when the search is cleared", async () => {
    const user = userEvent.setup();
    renderLibrary();

    await user.type(searchBox(/search agents/i), "zzz");
    expect(screen.getByText("No agents match “zzz”")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Clear search" }));

    expect(searchBox(/search agents/i)).toHaveValue("");
    expect(screen.getByText(DISCOVERY.name)).toBeInTheDocument();
    expect(nav.replace).toHaveBeenLastCalledWith("/library");
  });

  it("shows a plain empty message without a clear button when there are no agents", () => {
    renderLibrary("/library", { agents: [] });
    expect(screen.getByText("No agents found")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Clear search" })).not.toBeInTheDocument();
  });

  it("shows an error message instead of the grid when the agents fetch failed", () => {
    renderLibrary("/library", { agentsStatus: "failed" });
    expect(screen.getByText("Failed to load agents. Please refresh and try again.")).toBeInTheDocument();
    expect(screen.queryByText(DISCOVERY.name)).not.toBeInTheDocument();
  });

  it("shows neither cards nor empty or error text while agents are loading", () => {
    renderLibrary("/library", { agentsStatus: "loading" });
    expect(screen.queryByText(DISCOVERY.name)).not.toBeInTheDocument();
    expect(screen.queryByText(/No agents/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Failed to load/)).not.toBeInTheDocument();
  });

  it("sorts beta agents to the end and marks them Coming Soon without making them actionable", async () => {
    const user = userEvent.setup();
    renderLibrary();

    const beta = screen.getByText(BETA_AGENT.name);
    const lastActive = screen.getByText(CUSTOM.name);
    expect(lastActive.compareDocumentPosition(beta) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.getByText("Coming Soon")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: new RegExp(BETA_AGENT.name) })).not.toBeInTheDocument();

    await user.click(beta);

    expect(nav.push).not.toHaveBeenCalled();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("opens the agent drawer and navigates to the agent URL when a card is clicked", async () => {
    const user = userEvent.setup();
    renderLibrary("/library?category=user_stories");

    await user.click(screen.getByRole("button", { name: new RegExp(DISCOVERY.name) }));

    expect(nav.push).toHaveBeenCalledWith("/library/agents/domain_discovery?category=user_stories");
    expect(await screen.findByRole("dialog", { name: `${DISCOVERY.name} details` })).toBeInTheDocument();
  });

  it.each([
    ["Enter", "{Enter}"],
    ["Space", " "],
  ])("opens an agent card from the keyboard with %s", async (_label, keys) => {
    const user = userEvent.setup();
    renderLibrary();

    screen.getByRole("button", { name: new RegExp(DISCOVERY.name) }).focus();
    await user.keyboard(keys);

    expect(nav.push).toHaveBeenCalledWith("/library/agents/domain_discovery");
  });

  it("ignores other keys on a focused card", async () => {
    const user = userEvent.setup();
    renderLibrary();

    screen.getByRole("button", { name: new RegExp(DISCOVERY.name) }).focus();
    await user.keyboard("a");

    expect(nav.push).not.toHaveBeenCalled();
  });

  it("closes the agent drawer with Escape and returns to the list URL with the active filters", async () => {
    const user = userEvent.setup();
    renderLibrary("/library?category=user_stories&search=discovery");

    await user.click(screen.getByRole("button", { name: new RegExp(DISCOVERY.name) }));
    await screen.findByRole("dialog", { name: `${DISCOVERY.name} details` });
    await user.keyboard("{Escape}");

    expect(nav.push).toHaveBeenLastCalledWith("/library?category=user_stories&search=discovery");
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });
});

// ─── Skills grid ─────────────────────────────────────────────────

describe("LibraryPage skills grid", () => {
  it("shows the first three tags on a card and omits the rest", () => {
    renderLibrary("/library?tab=skills");
    expect(screen.getByText("ideas")).toBeInTheDocument();
    expect(screen.queryByText("overflow")).not.toBeInTheDocument();
  });

  it("falls back to the raw skill name when no display name exists", () => {
    renderLibrary("/library?tab=skills");
    expect(screen.getByText("Security Audit Checklist")).toBeInTheDocument();
  });

  it("filters skills by category chip and writes the category to the URL", async () => {
    const user = userEvent.setup();
    renderLibrary("/library?tab=skills");

    await user.click(screen.getByRole("button", { name: "Security" }));

    expect(screen.getByText(SKILL_SECURITY.name)).toBeInTheDocument();
    expect(screen.queryByText("Brainstorming Ideas Into Designs")).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Coming Soon" })).not.toBeInTheDocument();
    expect(nav.replace).toHaveBeenLastCalledWith("/library?tab=skills&category=security");
  });

  it("drops the category from the URL when the All skills chip is selected", async () => {
    const user = userEvent.setup();
    renderLibrary("/library?tab=skills&category=security");

    await user.click(screen.getByRole("button", { name: "All" }));

    expect(nav.replace).toHaveBeenLastCalledWith("/library?tab=skills");
    expect(screen.getByText("Brainstorming Ideas Into Designs")).toBeInTheDocument();
  });

  it("finds a skill by its description", async () => {
    const user = userEvent.setup();
    renderLibrary("/library?tab=skills");

    await user.type(searchBox(/search skills/i), "vulnerabilities");

    expect(screen.getByText(SKILL_SECURITY.name)).toBeInTheDocument();
    expect(screen.queryByText("Brainstorming Ideas Into Designs")).not.toBeInTheDocument();
    expect(nav.replace).toHaveBeenLastCalledWith("/library?tab=skills&search=vulnerabilities");
  });

  it("keeps the search and category in the URL together", async () => {
    const user = userEvent.setup();
    renderLibrary("/library?tab=skills&category=security");

    await user.type(searchBox(/search skills/i), "a");

    expect(nav.replace).toHaveBeenLastCalledWith("/library?tab=skills&category=security&search=a");
  });

  it("lists beta skills under Coming Soon without making them actionable", async () => {
    const user = userEvent.setup();
    renderLibrary("/library?tab=skills");

    expect(screen.getByRole("heading", { name: "Coming Soon" })).toBeInTheDocument();
    expect(screen.getByText(SKILL_BETA.name)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: new RegExp(SKILL_BETA.name) })).not.toBeInTheDocument();

    await user.click(screen.getByText(SKILL_BETA.name));

    expect(nav.push).not.toHaveBeenCalled();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("shows the Coming Soon list instead of a no-match message when only beta skills match", async () => {
    const user = userEvent.setup();
    renderLibrary("/library?tab=skills");

    await user.type(searchBox(/search skills/i), "trace");

    expect(screen.getByText(SKILL_BETA.name)).toBeInTheDocument();
    expect(screen.queryByText(/No skills/)).not.toBeInTheDocument();
  });

  it("shows a no-match message and clears the skills search on request", async () => {
    const user = userEvent.setup();
    renderLibrary("/library?tab=skills");

    await user.type(searchBox(/search skills/i), "zzz");
    expect(screen.getByText("No skills match “zzz”")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Clear search" }));

    expect(searchBox(/search skills/i)).toHaveValue("");
    expect(nav.replace).toHaveBeenLastCalledWith("/library?tab=skills");
  });

  it("shows a plain empty message when there are no skills", () => {
    renderLibrary("/library?tab=skills", { skills: [] });
    expect(screen.getByText("No skills found")).toBeInTheDocument();
  });

  it("shows an error message when the skills fetch failed", () => {
    renderLibrary("/library?tab=skills", { skillsStatus: "failed" });
    expect(screen.getByText("Failed to load skills. Please refresh and try again.")).toBeInTheDocument();
  });

  it("hides category chips, cards, and the Coming Soon list while skills are loading", () => {
    renderLibrary("/library?tab=skills", { skillsStatus: "loading" });
    expect(screen.queryByRole("button", { name: "Security" })).not.toBeInTheDocument();
    expect(screen.queryByText(SKILL_SECURITY.name)).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Coming Soon" })).not.toBeInTheDocument();
    expect(screen.queryByText(/No skills|Failed to load/)).not.toBeInTheDocument();
  });
});

// ─── Skill detail modal ──────────────────────────────────────────

describe("LibraryPage skill detail modal", () => {
  async function openSkill(user: ReturnType<typeof userEvent.setup>) {
    await user.click(screen.getByRole("button", { name: /Brainstorming Ideas Into Designs/ }));
    return screen.findByRole("dialog", { name: "Brainstorming Ideas Into Designs skill" });
  }

  it("opens from a card click, navigates to the skill URL, and moves focus into the dialog", async () => {
    const user = userEvent.setup();
    renderLibrary("/library?tab=skills");

    const dialog = await openSkill(user);

    expect(nav.push).toHaveBeenCalledWith("/library/skills/brainstorm_skill?tab=skills");
    expect(within(dialog).getByRole("heading", { name: "Brainstorming Ideas Into Designs" })).toBeInTheDocument();
    expect(within(dialog).getByText("overflow")).toBeInTheDocument();
    expect(dialog).toContainElement(document.activeElement as HTMLElement);
  });

  it.each([
    ["Enter", "{Enter}"],
    ["Space", " "],
  ])("opens a skill card from the keyboard with %s", async (_label, keys) => {
    const user = userEvent.setup();
    renderLibrary("/library?tab=skills");

    screen.getByRole("button", { name: /Brainstorming Ideas Into Designs/ }).focus();
    await user.keyboard(keys);

    expect(await screen.findByRole("dialog", { name: "Brainstorming Ideas Into Designs skill" })).toBeInTheDocument();
  });

  it("copies the skill content from both copy buttons and confirms it", async () => {
    const user = userEvent.setup();
    renderLibrary("/library?tab=skills");
    const dialog = await openSkill(user);

    await user.click(within(dialog).getByRole("button", { name: "Copy content" }));

    expect(await within(dialog).findByRole("button", { name: "Copied!" })).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Copied" })).toBeInTheDocument();
    expect(await navigator.clipboard.readText()).toBe(SKILL_PLANNING.content);
  });

  it("copies from the raw-content Copy button as well", async () => {
    const user = userEvent.setup();
    renderLibrary("/library?tab=skills");
    const dialog = await openSkill(user);

    await user.click(within(dialog).getByRole("button", { name: "Copy" }));

    expect(await within(dialog).findByRole("button", { name: "Copied!" })).toBeInTheDocument();
    expect(await navigator.clipboard.readText()).toBe(SKILL_PLANNING.content);
  });

  it("closes on Escape and returns to the skills list URL", async () => {
    const user = userEvent.setup();
    renderLibrary("/library?tab=skills&category=planning");
    await openSkill(user);

    await user.keyboard("{Escape}");

    expect(nav.push).toHaveBeenLastCalledWith("/library?tab=skills&category=planning");
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("closes when the backdrop is clicked but not when the panel is clicked", async () => {
    const user = userEvent.setup();
    renderLibrary("/library?tab=skills");
    const dialog = await openSkill(user);
    nav.push.mockClear();

    await user.click(within(dialog).getByRole("heading", { name: "Brainstorming Ideas Into Designs" }));
    expect(nav.push).not.toHaveBeenCalled();

    await user.click(dialog);
    expect(nav.push).toHaveBeenCalledWith("/library?tab=skills");
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("closes when the browser navigates back to the list URL", async () => {
    const user = userEvent.setup();
    renderLibrary("/library?tab=skills");
    await openSkill(user);

    act(() => nav.setUrl("/library?tab=skills"));

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });
});

// ─── Hooks grid ──────────────────────────────────────────────────

describe("LibraryPage hooks grid", () => {
  it("filters hooks by event chip and writes the event to the URL", async () => {
    const user = userEvent.setup();
    renderLibrary("/library?tab=hooks");

    await user.click(screen.getByRole("button", { name: "PostToolUse" }));

    expect(screen.getByText(HOOK_POST.name)).toBeInTheDocument();
    expect(screen.queryByText(HOOK_PRE.name)).not.toBeInTheDocument();
    expect(nav.replace).toHaveBeenLastCalledWith("/library?tab=hooks&category=PostToolUse");
  });

  it("drops the event from the URL when the All hooks chip is selected", async () => {
    const user = userEvent.setup();
    renderLibrary("/library?tab=hooks&category=PostToolUse");

    await user.click(screen.getByRole("button", { name: "All" }));

    expect(nav.replace).toHaveBeenLastCalledWith("/library?tab=hooks");
    expect(screen.getByText(HOOK_PRE.name)).toBeInTheDocument();
  });

  it("finds a hook by its description", async () => {
    const user = userEvent.setup();
    renderLibrary("/library?tab=hooks");

    await user.type(searchBox(/search hooks/i), "afterwards");

    expect(screen.getByText(HOOK_POST.name)).toBeInTheDocument();
    expect(screen.queryByText(HOOK_PRE.name)).not.toBeInTheDocument();
    expect(nav.replace).toHaveBeenLastCalledWith("/library?tab=hooks&search=afterwards");
  });

  it("shows a no-match message and clears the hooks search on request", async () => {
    const user = userEvent.setup();
    renderLibrary("/library?tab=hooks");

    await user.type(searchBox(/search hooks/i), "zzz");
    expect(screen.getByText("No hooks match “zzz”")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Clear search" }));

    expect(searchBox(/search hooks/i)).toHaveValue("");
    expect(nav.replace).toHaveBeenLastCalledWith("/library?tab=hooks");
  });

  it("shows a plain empty message when there are no hooks", () => {
    renderLibrary("/library?tab=hooks", { hooks: [] });
    expect(screen.getByText("No hooks found")).toBeInTheDocument();
  });

  it("shows an error message when the hooks fetch failed", () => {
    renderLibrary("/library?tab=hooks", { hooksStatus: "failed" });
    expect(screen.getByText("Failed to load hooks. Please refresh and try again.")).toBeInTheDocument();
  });

  it("hides event chips and cards while hooks are loading", () => {
    renderLibrary("/library?tab=hooks", { hooksStatus: "loading" });
    expect(screen.queryByRole("button", { name: "PostToolUse" })).not.toBeInTheDocument();
    expect(screen.queryByText(HOOK_PRE.name)).not.toBeInTheDocument();
    expect(screen.queryByText(/No hooks|Failed to load/)).not.toBeInTheDocument();
  });
});

// ─── Hook detail modal ───────────────────────────────────────────

describe("LibraryPage hook detail modal", () => {
  async function openHook(user: ReturnType<typeof userEvent.setup>, name: string) {
    await user.click(screen.getByRole("button", { name: new RegExp(name) }));
    return screen.findByRole("dialog", { name: `${name} hook` });
  }

  it("explains a known event, lists the trigger, and navigates to the hook URL", async () => {
    const user = userEvent.setup();
    renderLibrary("/library?tab=hooks");

    const dialog = await openHook(user, HOOK_PRE.name);

    expect(nav.push).toHaveBeenCalledWith("/library/hooks/pre_hook?tab=hooks");
    expect(within(dialog).getByText("Runs before a tool is executed. Can inspect or block the operation.")).toBeInTheDocument();
    expect(within(dialog).getByText("Before any tool is executed")).toBeInTheDocument();
    expect(dialog).toContainElement(document.activeElement as HTMLElement);
  });

  it("falls back to a generic description for an unrecognised event", async () => {
    const user = userEvent.setup();
    renderLibrary("/library?tab=hooks");

    const dialog = await openHook(user, HOOK_CUSTOM.name);

    expect(within(dialog).getByText("Triggered by the specified event.")).toBeInTheDocument();
  });

  it("lists every compatible agent when three or fewer exist", async () => {
    const user = userEvent.setup();
    renderLibrary("/library?tab=hooks");

    const dialog = await openHook(user, HOOK_PRE.name);

    expect(within(dialog).getByText("Best suited for: domain_discovery, backlog_architect.")).toBeInTheDocument();
  });

  it("truncates the best-suited list to three agents and adds 'and more' beyond that", async () => {
    const user = userEvent.setup();
    renderLibrary("/library?tab=hooks");

    const dialog = await openHook(user, HOOK_POST.name);

    expect(within(dialog).getByText("Best suited for: a1, a2, a3 and more.")).toBeInTheDocument();
    expect(within(dialog).getByText("a4")).toBeInTheDocument();
  });

  it("copies a readable summary of the hook and confirms it", async () => {
    const user = userEvent.setup();
    renderLibrary("/library?tab=hooks");
    const dialog = await openHook(user, HOOK_PRE.name);

    await user.click(within(dialog).getByRole("button", { name: "Copy" }));

    expect(await within(dialog).findByRole("button", { name: "Copied!" })).toBeInTheDocument();
    expect(await navigator.clipboard.readText()).toBe(
      "Hook: Pre Tool Use Hook\nEvent: PreToolUse\nTrigger: Before any tool is executed\n\nRuns before tool execution\n\nTags: execution",
    );
  });

  it("closes on Escape and returns to the hooks list URL with the active event", async () => {
    const user = userEvent.setup();
    renderLibrary("/library?tab=hooks&category=PreToolUse");
    await openHook(user, HOOK_PRE.name);

    await user.keyboard("{Escape}");

    expect(nav.push).toHaveBeenLastCalledWith("/library?tab=hooks&category=PreToolUse");
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("opens a hook card from the keyboard", async () => {
    const user = userEvent.setup();
    renderLibrary("/library?tab=hooks");

    screen.getByRole("button", { name: new RegExp(HOOK_POST.name) }).focus();
    await user.keyboard("{Enter}");

    expect(await screen.findByRole("dialog", { name: `${HOOK_POST.name} hook` })).toBeInTheDocument();
  });
});

// ─── Deep links ──────────────────────────────────────────────────

describe("LibraryPage deep links", () => {
  it("opens the agent drawer on a cold mount of /library/agents/{slug}", async () => {
    renderLibrary("/library/agents/domain_discovery");
    expect(await screen.findByRole("dialog", { name: `${DISCOVERY.name} details` })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /agents/i })).toHaveAttribute("aria-selected", "true");
  });

  it("opens the skill modal on a cold mount of /library/skills/{slug} and selects the Skills tab", async () => {
    renderLibrary("/library/skills/security_audit");
    expect(await screen.findByRole("dialog", { name: `${SKILL_SECURITY.name} skill` })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /skills/i })).toHaveAttribute("aria-selected", "true");
  });

  it("opens the hook modal on a cold mount of /library/hooks/{slug} and selects the Hooks tab", async () => {
    renderLibrary("/library/hooks/post_hook");
    expect(await screen.findByRole("dialog", { name: `${HOOK_POST.name} hook` })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /hooks/i })).toHaveAttribute("aria-selected", "true");
  });

  it("redirects a beta agent deep link to the list instead of opening a drawer", () => {
    renderLibrary("/library/agents/legacy_revision");
    expect(nav.replace).toHaveBeenCalledWith("/library");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("redirects a beta skill deep link to the skills list instead of opening a modal", () => {
    renderLibrary("/library/skills/telemetry_beta");
    expect(nav.replace).toHaveBeenCalledWith("/library?tab=skills");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it.each([
    ["agent", "/library/agents/missing"],
    ["skill", "/library/skills/missing"],
    ["hook", "/library/hooks/missing"],
  ])("renders the not-found boundary for an unknown %s slug once its catalog has loaded", (_type, url) => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    renderLibraryInBoundary(url);
    expect(screen.getByText("boundary: not found")).toBeInTheDocument();
  });

  it.each([
    ["agent", "/library/agents/missing", { agentsStatus: "loading" as const }],
    ["skill", "/library/skills/missing", { skillsStatus: "loading" as const }],
    ["hook", "/library/hooks/missing", { hooksStatus: "loading" as const }],
  ])("does not report not-found for an unknown %s slug while its catalog is still loading", (_type, url, options) => {
    renderLibraryInBoundary(url, options);
    expect(screen.queryByText("boundary: not found")).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Library" })).toBeInTheDocument();
  });
});
