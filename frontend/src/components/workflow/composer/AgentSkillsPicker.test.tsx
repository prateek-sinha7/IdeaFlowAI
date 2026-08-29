import { describe, expect, it } from "vitest";
import { fireEvent, renderWithProviders, screen } from "@/test/renderWithProviders";
import type { AgentDef } from "@/types/index";
import type { GlobalSkillEntry } from "@/store/api/skills";

import { AgentSkillsPicker } from "./AgentSkillsPicker";

// BUG-20260828-093400-library-skills-id-r2 — the "View details" modal on a
// skill card renders the raw markdown source instead of formatted HTML.

const AGENT: AgentDef = {
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
  skills: [],
};

const SKILL: GlobalSkillEntry = {
  id: "windows_desktop_e2e",
  name: "Windows Desktop E2E Testing",
  display_name: "Windows Desktop E2E Testing",
  description: "Automates Windows desktop UI tests.",
  content: "# Windows Desktop E2E Testing\n\n## When to Use\n\nUse **bold** and `code` here.",
  category: "testing",
  isBeta: false,
  tags: ["desktop"],
  compatible_agents: ["domain_discovery"],
};

function preloadedState() {
  return {
    skills: {
      skills: [SKILL],
      totalCount: 1,
      skillCategories: [{ id: "testing", label: "Testing" }],
      status: "succeeded" as const,
      error: null,
    },
  };
}

describe("ISS-359 — AgentSkillsPicker 'View details' modal", () => {
  it("renders the skill markdown as formatted HTML, not raw source (Canvas mount, readOnly=false)", () => {
    renderWithProviders(<AgentSkillsPicker agent={AGENT} onSkillsChange={() => {}} />, {
      preloadedState: preloadedState(),
    });

    fireEvent.click(screen.getByRole("button", { name: `View ${SKILL.name} details` }));

    const dialog = screen.getByRole("dialog", { name: `${SKILL.name} details` });
    expect(dialog.querySelectorAll("h1,h2,h3,h4").length).toBeGreaterThan(0);
    expect(/^#{1,3} /m.test(dialog.textContent ?? "")).toBe(false);
  });
});

describe("ISS-590 — same broken modal reached from a readOnly mount (Library drawer / Add-agent popup)", () => {
  it.fails("still shows the raw markdown when readOnly=true, since the Info button carries no readOnly gate", () => {
    renderWithProviders(<AgentSkillsPicker agent={AGENT} readOnly />, {
      preloadedState: preloadedState(),
    });

    fireEvent.click(screen.getByRole("button", { name: `View ${SKILL.name} details` }));

    const dialog = screen.getByRole("dialog", { name: `${SKILL.name} details` });
    expect(dialog.querySelectorAll("h1,h2,h3,h4").length).toBeGreaterThan(0);
    expect(/^#{1,3} /m.test(dialog.textContent ?? "")).toBe(false);
  });
});
