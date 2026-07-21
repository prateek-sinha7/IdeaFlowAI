import { describe, expect, it } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

// ─────────────────────────────────────────────────────────────────
// Reskin + real-controls contract for the Library page (plan 35-05).
//
// The Library is ALREADY richer than the mock (real category filtering,
// real search over local catalog constants, real detail modals). This test
// pins the wired behaviour through the token reskin so it can NEVER be
// downgraded to an inert mock, and asserts the post-reskin Tabs contract:
//   1. The Agents / Skills / Hooks tab bar exposes role=tab (Tabs primitive).
//      → RED against the pre-reskin ad-hoc <button> tab bar.
//   2. Clicking a tab switches the visible catalog section (real).
//   3. Typing in the search box filters the visible agents (real, not inert).
//   4. The tab counts reflect the local constant lengths (real data).
// ─────────────────────────────────────────────────────────────────

import { LibraryPage } from "./LibraryPage";
import { LIBRARY_AGENTS, CUSTOM_AGENTS } from "@/components/workflow/AgentLibraryData";
import { SKILLS } from "@/data/skills";
import { HOOKS } from "@/data/hooks";

const AGENT_COUNT = LIBRARY_AGENTS.length + CUSTOM_AGENTS.length;

// A known agent (user_stories pipeline) and a second agent whose name does
// NOT share the first's search substring — used to prove the filter is real.
const AGENT_A = "Domain Discovery Agent";
const AGENT_B = "Backlog Architecture Agent";
// A known skill (present only under the Skills tab).
const SKILL_A = "Brainstorming Ideas Into Designs";

describe("LibraryPage reskin — Tabs primitive + real controls preserved", () => {
  it("renders the Agents / Skills / Hooks tab bar with role=tab (Tabs primitive)", () => {
    render(<LibraryPage />);
    const tabs = screen.getAllByRole("tab");
    // Exactly the three top-level catalog tabs (sidebar categories are Pills).
    expect(tabs).toHaveLength(3);
    expect(screen.getByRole("tab", { name: /agents/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /skills/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /hooks/i })).toBeInTheDocument();
  });

  it("clicking the Skills tab switches the visible catalog section (real)", () => {
    render(<LibraryPage />);

    // Agents tab is active on mount → an agent renders, no skill yet.
    expect(screen.getByText(AGENT_A)).toBeInTheDocument();
    expect(screen.queryByText(SKILL_A)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: /skills/i }));

    // Skill section now rendered; the agent card is unmounted.
    expect(screen.getByText(SKILL_A)).toBeInTheDocument();
    expect(screen.queryByText(AGENT_A)).not.toBeInTheDocument();
  });

  it("typing in the search box filters the visible agents (real filter)", () => {
    render(<LibraryPage />);

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

  it("the tab counts reflect the local constant lengths (real data)", () => {
    render(<LibraryPage />);
    expect(screen.getByRole("tab", { name: /agents/i }).textContent).toContain(
      String(AGENT_COUNT),
    );
    expect(screen.getByRole("tab", { name: /skills/i }).textContent).toContain(
      String(SKILLS.length),
    );
    expect(screen.getByRole("tab", { name: /hooks/i }).textContent).toContain(
      String(HOOKS.length),
    );
  });

  it("renders no retired palette in the class strings", () => {
    const { container } = render(<LibraryPage />);
    const html = container.innerHTML;
    expect(html).not.toMatch(/#1B2A4A/);
    expect(html).not.toMatch(/\btext-gray-/);
    expect(html).not.toMatch(/\bbg-gray-/);
  });
});
