import { describe, expect, it, vi } from "vitest";
import { fireEvent, renderWithProviders, screen } from "@/test/renderWithProviders";
import type { GlobalSkillEntry } from "@/store/api/skills";
import type { AgentDef } from "@/types/index";

// ISS-591 (sibling of BUG-20260828-093400-library-skills-id-r2) — LibraryPage's
// SkillDetailModal ("Formatted content" section) only recognizes #/## heading
// lines and -/*/numbered bullets; inline **bold**/`code`/[links] pass through
// as literal text instead of being rendered as HTML.

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({}),
}));

import { LibraryPage } from "./LibraryPage";

const AGENT_A: AgentDef = {
  id: "domain_discovery",
  name: "Domain Discovery Agent",
  role: "Market & Persona Research",
  description: "Discovers market opportunities and personas through research.",
  pipeline_type: "discovery",
  order: 0,
  icon: "zap",
  estimated_duration: 300,
  has_skill: true,
  prompt_body: "You are a discovery agent.",
};

const SKILL_A: GlobalSkillEntry = {
  id: "brainstorm_skill",
  name: "Brainstorming Ideas Into Designs",
  display_name: "Brainstorming Ideas Into Designs",
  description: "Brainstorm design ideas",
  content: "# Brainstorming Skill\n\n## Overview\n\nUse **bold** and `inline code` and [a link](https://example.com) here.",
  category: "planning",
  isBeta: false,
  tags: ["creative", "design"],
  compatible_agents: ["domain_discovery"],
};

function createPreloadedState() {
  return {
    agents: {
      agents: [AGENT_A],
      totalCount: 1,
      pipelines: { discovery: 1 },
      status: "succeeded" as const,
      error: null,
    },
    skills: {
      skills: [SKILL_A],
      totalCount: 1,
      skillCategories: [{ id: "planning", label: "Planning" }],
      status: "succeeded" as const,
      error: null,
    },
    hooks: {
      hooks: [],
      totalCount: 0,
      hookEvents: [],
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
    auth: {
      token: null,
      user: null,
      isAuthenticated: false,
    },
  };
}

describe("ISS-591 — LibraryPage's SkillDetailModal inline markdown", () => {
  // `it.fails` is vitest's xfail(strict=True) — observed red (literal
  // "**bold**" text with no <strong> element) before this marker was added;
  // remove once ISS-591 is fixed.
  it.fails("renders inline bold/code/link markdown as HTML in the Formatted content section, not literal markup", () => {
    renderWithProviders(<LibraryPage />, { preloadedState: createPreloadedState() });

    fireEvent.click(screen.getByRole("tab", { name: /skills/i }));
    fireEvent.click(screen.getByText(SKILL_A.name));

    const dialog = screen.getByRole("dialog", { name: `${SKILL_A.name} skill` });
    expect(dialog.querySelector("strong, b")).not.toBeNull();
    expect(/\*\*bold\*\*/.test(dialog.textContent ?? "")).toBe(false);
  });
});
