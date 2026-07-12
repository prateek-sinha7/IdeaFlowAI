import { describe, expect, it } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

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

describe("LibraryPage 40-03 — mock composition (header leads, tab grids)", () => {
  it("renders the 'Library' h1 BEFORE the tablist (header leads, per the mock)", () => {
    render(<LibraryPage />);

    const h1 = screen.getByRole("heading", { level: 1, name: /^Library$/ });
    const tablist = screen.getByRole("tablist");

    expect(h1).toBeInTheDocument();
    expect(tablist).toBeInTheDocument();

    // h1 must precede the tablist in document order → the header leads.
    const order = h1.compareDocumentPosition(tablist);
    expect(order & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("renders an item-count line beneath the h1", () => {
    render(<LibraryPage />);
    // "N agents · M skills · K hooks" — the mock's libCountLine.
    expect(screen.getByText(/\d+ agents · \d+ skills · \d+ hooks/)).toBeInTheDocument();
  });

  it("renders the Agents card grid on mount", () => {
    render(<LibraryPage />);
    expect(screen.getByText(AGENT_A)).toBeInTheDocument();
  });

  it("renders the Skills card grid when the Skills tab is active", () => {
    render(<LibraryPage />);
    fireEvent.click(screen.getByRole("tab", { name: /skills/i }));
    expect(screen.getByText(SKILL_A)).toBeInTheDocument();
  });

  it("renders the Hooks card grid when the Hooks tab is active", () => {
    render(<LibraryPage />);
    fireEvent.click(screen.getByRole("tab", { name: /hooks/i }));
    // At least one hook event badge is visible in the hooks grid.
    expect(screen.getAllByText(/PreToolUse|PostToolUse|Stop|SessionStart|SessionEnd/).length).toBeGreaterThan(0);
  });
});
