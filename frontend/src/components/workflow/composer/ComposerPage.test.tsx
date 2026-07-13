/**
 * 41-04 — Full-page Composer (Simple view) behaviour contract.
 *
 * The Composer is an ADDITIVE full-page authoring surface (mainView='composer').
 * It REUSES the AgentsPopup exported sub-components (AdvancedExpander /
 * CapabilityPaletteSection / SkillsHooksTab / AgentPromptSection) and the shared
 * data model (pipelineAgents order + SelectionsMap). The AgentsPopup MODAL wrapper
 * is RETAINED for the wizard/input inline-edit flow — the Composer is NOT a dual
 * implementation (INV-3: shared sub-components, distinct entry/purpose).
 *
 * These tests pin the `<behavior>` cases:
 *   - full-page surface: eyebrow "Custom workflow · Composer" + Save affordances
 *   - Simple ⇄ Canvas toggle (Simple active → agent rows; Canvas → node-graph, 41-05)
 *   - identity card: Name + Description editable, Deliverable-type READ-ONLY (ND-AH)
 *   - agent rows: index · avatar · name · Core badge (getRole) · role · inline model
 *     picker · Validator/Gate/Retry chips · Custom-prompt · remove; reorder
 *   - Summary rail: agents · review-gates · strategy · LIVE est. duration · NO cost
 *     (ND-AG) · Save-to-catalogue primary action
 *   - additive/INV-3: the modal is still imported by LaunchWizard + IdeaInputPage;
 *     the composer reuses the exported sub-components (source-level guard)
 *
 * `getCapabilities` is mocked so the reused palette/expander render without a real
 * `/api/capabilities` fetch (same idiom as CapabilityPaletteSection.test.tsx).
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, within, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import type { CapabilitiesPalette } from "@/lib/api";
import type { WorkflowType } from "@/types/index";

const mockGetCapabilities = vi.fn();
const mockCreateUserWorkflow = vi.fn();
vi.mock("@/lib/api", () => ({
  getToken: () => "test-token",
  getCapabilities: (t: string) => mockGetCapabilities(t),
  createUserWorkflow: (...a: unknown[]) => mockCreateUserWorkflow(...a),
  getWorkflowDetail: vi.fn().mockResolvedValue({ steps: [] }),
  getAgentPrompt: vi.fn().mockResolvedValue({ prompt_body: "", override: null, has_override: false }),
  saveAgentPromptOverride: vi.fn(),
  deleteAgentPromptOverride: vi.fn(),
}));

import { ComposerPage } from "./ComposerPage";
import { SkillsHooksProvider } from "@/context/SkillsHooksContext";

const PALETTE: CapabilitiesPalette = {
  capabilities: [
    {
      kind: "validator",
      name: "code_test",
      user_allowed: true,
      description: "Runs the tests.",
      security_gated: false,
      config_schema: {},
    },
    {
      kind: "gate",
      name: "approval",
      user_allowed: true,
      description: "Human approval gate.",
      security_gated: false,
      config_schema: {},
    },
  ],
  model_catalog: [
    {
      id: "model-opus",
      label: "Opus 4.5",
      description: "Most capable.",
      tier: "powerful",
      cost_class: "premium",
      provider: "anthropic",
      context_window: 200000,
      user_allowed: true,
    },
  ],
};

function renderComposer(props: Record<string, unknown> = {}) {
  return render(
    <SkillsHooksProvider>
      <ComposerPage
        workflowType={"user_stories" as WorkflowType}
        onBack={() => {}}
        {...props}
      />
    </SkillsHooksProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mockGetCapabilities.mockResolvedValue(PALETTE);
});

describe("ComposerPage — full-page Composer Simple view (41-04)", () => {
  it("renders as a full-page surface with the Composer eyebrow + Save affordances", () => {
    renderComposer();
    expect(screen.getByText(/Custom workflow · Composer/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Save draft/i })).toBeInTheDocument();
    expect(
      screen.getAllByRole("button", { name: /Save workflow/i }).length,
    ).toBeGreaterThanOrEqual(1);
  });

  it("shows a Simple ⇄ Canvas toggle — Simple active renders agent rows, Canvas mounts the node-graph", async () => {
    renderComposer();
    const simple = screen.getByRole("button", { name: /^Simple$/ });
    const canvas = screen.getByRole("button", { name: /^Canvas$/ });
    expect(simple).toBeInTheDocument();
    expect(canvas).toBeInTheDocument();

    // Simple active → the first seeded agent row is visible.
    expect(screen.getByText("Domain Discovery Agent")).toBeInTheDocument();

    // Canvas → the hand-rolled node-graph mounts (41-05); the Simple agent ROWS
    // disappear (the node-graph carries the agents as canvas nodes instead).
    await userEvent.click(canvas);
    expect(screen.getByTestId("canvas-view")).toBeInTheDocument();
    expect(screen.queryByTestId("agent-row-domain-analyst")).not.toBeInTheDocument();
  });

  it("identity card: Name + Description are editable, Deliverable-type is READ-ONLY (ND-AH)", async () => {
    renderComposer();
    // Name is an editable text control.
    const name = screen.getByLabelText(/^Name$/i);
    expect(name).toBeInTheDocument();
    await userEvent.clear(name);
    await userEvent.type(name, "My workflow");
    expect(name).toHaveValue("My workflow");

    // Description is editable.
    const desc = screen.getByLabelText(/^Description$/i);
    await userEvent.type(desc, "A brief.");
    expect(desc).toHaveValue("A brief.");

    // Deliverable-type is read-only text (ND-AH) — the resolved label shows and
    // there is NO editable deliverable control (no combobox / select for it).
    const deliverable = screen.getByTestId("composer-deliverable-type");
    expect(deliverable).toHaveTextContent("User Stories");
    expect(deliverable.querySelector("select")).toBeNull();
    expect(deliverable.querySelector("input")).toBeNull();
  });

  it("each agent row renders index, name, role, Core badge (getRole), model picker, override chips, custom prompt + remove", () => {
    renderComposer();
    const firstRow = screen.getByTestId("agent-row-domain-analyst");
    // index (01) + name + role
    expect(within(firstRow).getByText("01")).toBeInTheDocument();
    expect(within(firstRow).getByText("Domain Discovery Agent")).toBeInTheDocument();
    expect(within(firstRow).getByText(/Market & Persona Research/i)).toBeInTheDocument();
    // Core badge — domain-analyst is a locked core agent for user_stories (getRole).
    expect(within(firstRow).getByText(/^Core$/)).toBeInTheDocument();
    // inline model picker (defaults to "Default" — no override yet)
    expect(within(firstRow).getByRole("button", { name: /Model for Domain Discovery Agent/i })).toBeInTheDocument();
    // Validator / Gate / Retry override chips
    expect(within(firstRow).getByText("Validator")).toBeInTheDocument();
    expect(within(firstRow).getByText("Gate")).toBeInTheDocument();
    expect(within(firstRow).getByText("Retry")).toBeInTheDocument();
    // Custom prompt affordance
    expect(within(firstRow).getByText(/Custom prompt/i)).toBeInTheDocument();
  });

  it("reorder moves an agent within pipelineAgents (Move down swaps neighbours)", async () => {
    renderComposer();
    const namesBefore = screen.getAllByTestId(/^agent-row-/).map((r) => r.getAttribute("data-testid"));
    // The 2nd and 3rd agents (epic-architect, story-estimator) are reorderable.
    await userEvent.click(screen.getByRole("button", { name: /Move Backlog Architecture Agent down/i }));
    const namesAfter = screen.getAllByTestId(/^agent-row-/).map((r) => r.getAttribute("data-testid"));
    expect(namesAfter).not.toEqual(namesBefore);
    // epic-architect moved after story-estimator.
    expect(namesAfter.indexOf("agent-row-epic-architect")).toBeGreaterThan(
      namesAfter.indexOf("agent-row-story-estimator"),
    );
  });

  it("Summary rail: agents + review-gate counts + strategy + LIVE est. duration, NO est. cost (ND-AG), Save-to-catalogue primary", () => {
    renderComposer();
    const rail = screen.getByTestId("composer-summary-rail");
    // agent count (6 user_stories agents)
    expect(within(rail).getByText("6")).toBeInTheDocument();
    expect(within(rail).getByText(/Agents/i)).toBeInTheDocument();
    expect(within(rail).getByText(/Review gates/i)).toBeInTheDocument();
    expect(within(rail).getByText(/Strategy/i)).toBeInTheDocument();
    // Live est. duration derived from estimated_duration sum (300s → ~5m).
    expect(within(rail).getByText(/Est\. duration/i)).toBeInTheDocument();
    expect(within(rail).getByText("~5m")).toBeInTheDocument();
    // ND-AG: NO fabricated est. cost anywhere on the rail.
    expect(within(rail).queryByText(/Est\. cost/i)).toBeNull();
    // Primary action = Save to catalogue.
    expect(within(rail).getByRole("button", { name: /Save to catalogue/i })).toBeInTheDocument();
    // Run once is present but inert here (wired in 41-06).
    expect(within(rail).getByRole("button", { name: /Run once/i })).toBeInTheDocument();
  });

  it("edit-from-My-Workflows pre-loads the saved agents + name (shared data model)", () => {
    renderComposer({
      initialAgentIds: ["domain-analyst", "epic-architect"],
      initialName: "Saved flow",
    });
    expect(screen.getByLabelText(/^Name$/i)).toHaveValue("Saved flow");
    expect(screen.getByTestId("agent-row-domain-analyst")).toBeInTheDocument();
    expect(screen.getByTestId("agent-row-epic-architect")).toBeInTheDocument();
    // Only the two saved agents are pre-loaded (not the full user_stories default).
    expect(screen.getAllByTestId(/^agent-row-/).length).toBe(2);
  });

  it("Save to catalogue persists via the owner-scoped createUserWorkflow (reused NameWorkflowModal path)", async () => {
    mockCreateUserWorkflow.mockResolvedValue({ id: "wf-1" });
    renderComposer({ initialName: "Comp flow" });
    const rail = screen.getByTestId("composer-summary-rail");
    await userEvent.click(within(rail).getByRole("button", { name: /Save to catalogue/i }));
    // NameWorkflowModal opens (its "Workflow name" field); confirm via its Save.
    await screen.findByText(/Workflow name/i);
    await userEvent.click(screen.getByRole("button", { name: /^Save$/ }));
    await waitFor(() => expect(mockCreateUserWorkflow).toHaveBeenCalled());
    const payload = mockCreateUserWorkflow.mock.calls[0][1] as { base_pipeline_type: string; agent_ids: string[] };
    expect(payload.base_pipeline_type).toBe("user_stories");
    expect(payload.agent_ids.length).toBe(6);
  });
});

// ── Additive / INV-3 source-level guards ────────────────────────────────────────
describe("ComposerPage — additive, reuses the modal sub-components (INV-3)", () => {
  const FRONTEND = resolve(process.cwd(), "src/components");
  const read = (p: string) => readFileSync(resolve(FRONTEND, p), "utf8");

  it("the AgentsPopup MODAL wrapper is RETAINED — still imported by LaunchWizard + IdeaInputPage", () => {
    expect(read("workflow/LaunchWizard.tsx")).toMatch(/AgentsPopup/);
    expect(read("workflow/IdeaInputPage.tsx")).toMatch(/AgentsPopup/);
    // The exported modal wrapper still exists.
    expect(read("workflow/AgentsPopup.tsx")).toMatch(/export function AgentsPopup/);
  });

  it("the Composer REUSES the exported sub-components (not forked)", () => {
    const src = read("workflow/composer/ComposerPage.tsx") + read("workflow/composer/AgentRow.tsx");
    expect(src).toMatch(/AdvancedExpander/);
    expect(src).toMatch(/CapabilityPaletteSection/);
    expect(src).toMatch(/SkillsHooksTab/);
    expect(src).toMatch(/AgentPromptSection/);
  });
});
