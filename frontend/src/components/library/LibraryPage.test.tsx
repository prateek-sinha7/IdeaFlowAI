import { describe, expect, it } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { SkillsHooksProvider } from "@/context/SkillsHooksContext";

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

// ─────────────────────────────────────────────────────────────────
// Plan 41-07 — the Library agent-detail opens as a right-side DRAWER
// (mock `drawerOpen`, Hexaware Workspace v2.dc.html :709). Clicking an
// agent card opens the restructured shared AgentCapabilitiesModal in its
// drawer form, surfacing the Overview / Skills / Hooks / Config tabs.
// This closes the Phase-40 ND-Z deferral (SHELL-04 Agent-drawer clause).
// ─────────────────────────────────────────────────────────────────

describe("LibraryPage 41-07 — agent-detail right-side drawer (ND-Z resolved)", () => {
  function openFirstAgentDrawer() {
    render(
      <SkillsHooksProvider>
        <LibraryPage />
      </SkillsHooksProvider>,
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
