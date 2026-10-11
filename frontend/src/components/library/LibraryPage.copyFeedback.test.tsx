import { describe, expect, it, vi, beforeEach } from "vitest";
import { fireEvent, renderWithProviders, screen, within } from "@/test/renderWithProviders";
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

// ISS-600: useParams must return a deep-link path (/library/{type}/{slug}) so
// LibraryPage's T15 effect seeds the matching detail modal on mount. A hoisted
// typed mock lets each test set its own deep link before rendering.
const { useParamsMock } = vi.hoisted(() => ({
  useParamsMock: vi.fn<() => { view?: string[] }>(() => ({})),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
    prefetch: vi.fn(),
  }),
  useSearchParams: () => new URLSearchParams(),
  useParams: useParamsMock,
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
  it("shows a failure state when the clipboard write rejects, instead of staying silent", async () => {
    // Arrange — deep link /library/hooks/{id} opens the hook detail modal on mount.
    useParamsMock.mockReturnValue({ view: ["library", "hooks", MOCK_HOOK.id] });
    renderWithProviders(<LibraryPage />, { preloadedState: createPreloadedState() });
    const dialog = await screen.findByRole("dialog", { name: `${MOCK_HOOK.name} hook` });

    // Act
    fireEvent.click(within(dialog).getByRole("button", { name: /^Copy$/ }));

    // Assert — findByText retries until the rejected write's state update lands.
    expect(await within(dialog).findByText(/copy failed/i)).toBeInTheDocument();
    expect(navigator.clipboard.writeText).toHaveBeenCalledTimes(1);
  });
});

describe("SkillDetailModal Copy button — ISS-555", () => {
  it("shows a failure state when the clipboard write rejects, instead of staying silent", async () => {
    // Arrange — deep link /library/skills/{id} opens the skill detail modal on mount.
    useParamsMock.mockReturnValue({ view: ["library", "skills", MOCK_SKILL.id] });
    renderWithProviders(<LibraryPage />, { preloadedState: createPreloadedState() });
    const dialog = await screen.findByRole("dialog", { name: `${MOCK_SKILL.name} skill` });

    // Act — the header "Copy content" button; the raw-block "Copy" shares the handler.
    fireEvent.click(within(dialog).getByRole("button", { name: /^Copy content$/ }));

    // Assert
    expect(await within(dialog).findByText(/copy failed/i)).toBeInTheDocument();
    expect(navigator.clipboard.writeText).toHaveBeenCalledTimes(1);
  });
});
