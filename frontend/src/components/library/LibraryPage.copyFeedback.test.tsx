import { describe, expect, it, vi, beforeEach } from "vitest";
import { fireEvent, renderWithProviders, screen } from "@/test/renderWithProviders";
import type { GlobalSkillEntry } from "@/store/api/skills";
import type { GlobalHookEntry } from "@/store/api/hooks";

// ─────────────────────────────────────────────────────────────────
// ISS-331 / ISS-555 — the hook and skill detail modals' Copy buttons give
// zero feedback when navigator.clipboard.writeText rejects. Both
// HookDetailModal.handleCopy (LibraryPage.tsx:351-355) and
// SkillDetailModal.handleCopy (LibraryPage.tsx:201-205) `await` the write
// with no try/catch and no .catch(), so a rejection leaves the button
// stuck reading "Copy" forever with nothing shown to the user.
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

const MOCK_SKILL: GlobalSkillEntry = {
  id: "brainstorm_skill",
  name: "Brainstorming Ideas Into Designs",
  display_name: "Brainstorming Ideas Into Designs",
  description: "Brainstorm design ideas",
  content: "# Brainstorming Skill\n\nThis skill helps generate design ideas.",
  category: "planning",
  isBeta: false,
  tags: ["creative", "design"],
  compatible_agents: [],
};

const MOCK_HOOK: GlobalHookEntry = {
  id: "pretooluse_hook",
  name: "Pre Tool Use Hook",
  display_name: "Pre Tool Use Hook",
  description: "Runs before tool execution",
  content: "Hook content",
  event: "PreToolUse",
  trigger: "Before any tool is executed",
  compatible_agents: [],
  tags: ["execution"],
};

const createPreloadedState = () => ({
  agents: { agents: [], totalCount: 0, pipelines: {}, status: "succeeded" as const, error: null },
  skills: {
    skills: [MOCK_SKILL],
    totalCount: 1,
    skillCategories: [{ id: "planning", label: "Planning" }],
    status: "succeeded" as const,
    error: null,
  },
  hooks: {
    hooks: [MOCK_HOOK],
    totalCount: 1,
    hookEvents: [{ id: "PreToolUse", label: "PreToolUse" }],
    status: "succeeded" as const,
    error: null,
  },
  global: {
    workflows: [],
    workflowsStatus: "succeeded" as const,
    workflowsError: null,
    recentRuns: [],
    recentRunsStatus: "idle" as const,
    recentRunsError: null,
  },
  auth: { token: null, user: null, isAuthenticated: false },
});

beforeEach(() => {
  // Clipboard write rejects on every call — the condition both cards describe.
  Object.assign(navigator, {
    clipboard: { writeText: vi.fn().mockRejectedValue(new DOMException("denied")) },
  });
});

describe("HookDetailModal Copy button — ISS-331", () => {
  it.fails("shows a failure state when the clipboard write rejects, instead of staying silent", async () => {
    renderWithProviders(<LibraryPage />, { preloadedState: createPreloadedState() });
    fireEvent.click(screen.getByRole("tab", { name: /hooks/i }));
    fireEvent.click(screen.getByText(MOCK_HOOK.name));

    fireEvent.click(await screen.findByRole("button", { name: /^Copy$/ }));
    // Give the rejected microtask a tick to settle.
    await new Promise((r) => setTimeout(r, 0));

    // ISS-331: today nothing changes on rejection — no failure text, button
    // stays "Copy". The fixed behaviour must surface SOMETHING to the user.
    expect(screen.queryByText(/fail|error|couldn.?t/i)).toBeInTheDocument();
  });
});

describe("SkillDetailModal Copy button — ISS-555", () => {
  it.fails("shows a failure state when the clipboard write rejects, instead of staying silent", async () => {
    renderWithProviders(<LibraryPage />, { preloadedState: createPreloadedState() });
    fireEvent.click(screen.getByRole("tab", { name: /skills/i }));
    fireEvent.click(screen.getByText(MOCK_SKILL.name));

    fireEvent.click(await screen.findByRole("button", { name: /^Copy$/ }));
    await new Promise((r) => setTimeout(r, 0));

    expect(screen.queryByText(/fail|error|couldn.?t/i)).toBeInTheDocument();
  });
});
