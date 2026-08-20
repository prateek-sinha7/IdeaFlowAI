/**
 * 41-04 — Full-page Composer (Simple view) behaviour contract.
 *
 * The Composer is an ADDITIVE full-page authoring surface (mainView='composer').
 * It REUSES the AgentsPopup exported sub-components (AdvancedExpander /
 * CapabilityPaletteSection / HooksTab / AgentPromptSection) and the shared
 * data model (pipelineAgents order + SelectionsMap). The AgentsPopup MODAL wrapper
 * is RETAINED for the wizard/input inline-edit flow — the Composer is NOT a dual
 * implementation (INV-3: shared sub-components, distinct entry/purpose).
 *
 * These tests pin the `<behavior>` cases:
 *   - full-page surface: eyebrow "Custom workflow · Composer" + Save affordances
 *   - Simple ⇄ Canvas toggle (Canvas active by default → node-graph, 41-05;
 *     Simple → agent rows)
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
import { renderWithProviders, screen, within, waitFor } from "@/test/renderWithProviders";
import userEvent from "@testing-library/user-event";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import type { CapabilitiesPalette } from "@/lib/api";
import type { WorkflowType } from "@/types/index";

const mockGetCapabilities = vi.fn();
const mockSaveUserWorkflow = vi.fn();
vi.mock("@/lib/api", () => ({
  getToken: () => "test-token",
  getCapabilities: (t: string) => mockGetCapabilities(t),
  saveUserWorkflow: (...a: unknown[]) => mockSaveUserWorkflow(...a),
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

const TEST_AGENTS = [
  {
    id: "domain-analyst",
    name: "Domain Discovery Agent",
    role: "Market & Persona Research",
    description: "Research market and personas",
    pipeline_type: "user_stories",
    order: 1,
    icon: "🔍",
    estimated_duration: 60,
    has_skill: false,
  },
  {
    id: "epic-architect",
    name: "Backlog Architecture Agent",
    role: "Epic Design",
    description: "Design epics",
    pipeline_type: "user_stories",
    order: 2,
    icon: "🏗️",
    estimated_duration: 60,
    has_skill: false,
  },
  {
    id: "story-estimator",
    name: "Story Estimator Agent",
    role: "Story Estimation",
    description: "Estimate stories",
    pipeline_type: "user_stories",
    order: 3,
    icon: "📊",
    estimated_duration: 50,
    has_skill: false,
  },
  {
    id: "nfr-specialist",
    name: "NFR Specialist Agent",
    role: "Non-Functional Requirements",
    description: "Add non-functional requirements",
    pipeline_type: "user_stories",
    order: 4,
    icon: "⚙️",
    estimated_duration: 40,
    has_skill: false,
  },
  {
    id: "backlog-reviewer",
    name: "Backlog Reviewer Agent",
    role: "Quality Review",
    description: "Review backlog quality",
    pipeline_type: "user_stories",
    order: 5,
    icon: "✅",
    estimated_duration: 40,
    has_skill: false,
  },
  {
    id: "backlog-compiler",
    name: "Backlog Compiler Agent",
    role: "Final Compilation",
    description: "Compile final backlog",
    pipeline_type: "user_stories",
    order: 6,
    icon: "📋",
    estimated_duration: 50,
    has_skill: false,
  },
];

function renderComposer(props: Record<string, unknown> = {}) {
  return renderWithProviders(
    <SkillsHooksProvider>
      <ComposerPage
        workflowType={"user_stories" as WorkflowType}
        onBack={() => {}}
        {...props}
      />
    </SkillsHooksProvider>,
    {
      preloadedState: {
        agents: {
          agents: TEST_AGENTS,
          totalCount: TEST_AGENTS.length,
          pipelines: {},
          status: "succeeded",
          error: null,
        },
      },
    },
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mockGetCapabilities.mockResolvedValue(PALETTE);
});

describe("ComposerPage — full-page Composer Simple view (41-04)", () => {
  it("renders as a full-page surface with the Composer eyebrow + Save affordances", () => {
    renderComposer();
    expect(screen.getByText(/User Stories · Composer/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Save workflow/i })).toBeInTheDocument();
    expect(
      screen.getAllByRole("button", { name: /Save workflow/i }).length,
    ).toBeGreaterThanOrEqual(1);
  });

  it("shows a Simple ⇄ Canvas toggle — Canvas active by default mounts the node-graph, Simple renders agent rows", async () => {
    renderComposer();
    const simple = screen.getByRole("button", { name: /^Simple$/ });
    const canvas = screen.getByRole("button", { name: /^Canvas$/ });
    expect(simple).toBeInTheDocument();
    expect(canvas).toBeInTheDocument();

    // Canvas active by default → the hand-rolled node-graph mounts (41-05);
    // the Simple agent ROWS are not present yet.
    expect(screen.getByTestId("canvas-view")).toBeInTheDocument();
    expect(screen.queryByTestId("agent-row-domain-analyst")).not.toBeInTheDocument();

    // Simple → the flat agent-row list renders, the node-graph unmounts.
    await userEvent.click(simple);
    expect(screen.getByText("Domain Discovery Agent")).toBeInTheDocument();
    expect(screen.queryByTestId("canvas-view")).not.toBeInTheDocument();
  });

  it("identity card: Name + Description are editable, Deliverable-type is READ-ONLY (ND-AH)", async () => {
    renderComposer();
    // Identity card is Simple-view content; Canvas is the default view.
    await userEvent.click(screen.getByRole("button", { name: /^Simple$/ }));
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

  it("each agent row renders index, name, role, Core badge (getRole), model picker, override chips, custom prompt + remove", async () => {
    renderComposer();
    // Agent rows are Simple-view content; Canvas is the default view.
    await userEvent.click(screen.getByRole("button", { name: /^Simple$/ }));
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
    // Configuration affordance
    expect(within(firstRow).getByText(/Configure/i)).toBeInTheDocument();
  });

  it("reorder moves an agent within pipelineAgents (Move down swaps neighbours)", async () => {
    renderComposer();
    // Agent rows are Simple-view content; Canvas is the default view.
    await userEvent.click(screen.getByRole("button", { name: /^Simple$/ }));
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

  it("Summary rail: agents + review-gate counts + strategy + LIVE est. duration, NO est. cost (ND-AG), Save-to-catalogue primary", async () => {
    renderComposer();
    // SummaryRail is Simple-view content; Canvas is the default view.
    await userEvent.click(screen.getByRole("button", { name: /^Simple$/ }));
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
    // Save and Run buttons are now in the ComposerPage header (41-04), not in the rail.
    expect(screen.getByRole("button", { name: /Save workflow/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Run once/i })).toBeInTheDocument();
  });

  it("edit-from-My-Workflows pre-loads the saved agents + name (shared data model)", async () => {
    renderComposer({
      initialAgentIds: ["domain-analyst", "epic-architect"],
      initialName: "Saved flow",
    });
    // Identity card + agent rows are Simple-view content; Canvas is the default view.
    await userEvent.click(screen.getByRole("button", { name: /^Simple$/ }));
    expect(screen.getByLabelText(/^Name$/i)).toHaveValue("Saved flow");
    expect(screen.getByTestId("agent-row-domain-analyst")).toBeInTheDocument();
    expect(screen.getByTestId("agent-row-epic-architect")).toBeInTheDocument();
    // Only the two saved agents are pre-loaded (not the full user_stories default).
    expect(screen.getAllByTestId(/^agent-row-/).length).toBe(2);
  });

  it("Save to catalogue persists via the shared saveUserWorkflow dispatch (reused NameWorkflowModal path)", async () => {
    mockSaveUserWorkflow.mockResolvedValue({ id: "wf-1" });
    renderComposer({ initialName: "Comp flow" });
    // Click the "Save workflow" button in the header
    await userEvent.click(screen.getByRole("button", { name: /Save workflow/i }));
    await waitFor(() => expect(mockSaveUserWorkflow).toHaveBeenCalled());
    // saveUserWorkflow(token, userWorkflowId, body) — no saved id yet on a fresh composer.
    const [, calledWorkflowId, payload] = mockSaveUserWorkflow.mock.calls[0] as [
      string, string | undefined, { base_pipeline_type: string; agent_ids: string[] },
    ];
    expect(calledWorkflowId).toBeUndefined();
    expect(payload.base_pipeline_type).toBe("user_stories");
    expect(payload.agent_ids.length).toBe(6);
  });

  // ── CWF-001 D1 — surface the compose-time pre-sort + unsatisfiable rejection ──

  it("surfaces the producer-first pre-sort — reorders rows on save", async () => {
    // The backend repairs a consumer-before-producer order and returns the persisted
    // producer-first agent_ids; the composer reorders its visible rows to match.
    mockSaveUserWorkflow.mockResolvedValue({
      id: "wf-1",
      agent_ids: ["domain-analyst", "epic-architect"],
    });
    renderComposer({
      initialAgentIds: ["epic-architect", "domain-analyst"],
      initialName: "Reorder flow",
    });
    // Agent rows are Simple-view content; Canvas is the default view.
    await userEvent.click(screen.getByRole("button", { name: /^Simple$/ }));
    // Before save: rows are in the sent (consumer-first) order.
    const before = screen.getAllByTestId(/^agent-row-/).map((r) => r.getAttribute("data-testid"));
    expect(before).toEqual(["agent-row-epic-architect", "agent-row-domain-analyst"]);

    // Click the "Save workflow" button in the header
    await userEvent.click(screen.getByRole("button", { name: /Save workflow/i }));
    await waitFor(() => expect(mockSaveUserWorkflow).toHaveBeenCalled());

    // After save: rows flip to the persisted producer-first order.
    await waitFor(() => {
      const after = screen.getAllByTestId(/^agent-row-/).map((r) => r.getAttribute("data-testid"));
      expect(after).toEqual(["agent-row-domain-analyst", "agent-row-epic-architect"]);
    });
  });

  it("surfaces an unsatisfiable-composition rejection inline", async () => {
    // The backend rejects a genuinely-unsatisfiable composition (422); saveUserWorkflow
    // throws with the backend detail as its message, which renders inline via saveError.
    const msg =
      "Agent 'swot-analyst' consumes 'market-research-agent' but no agent in the workflow produces it.";
    mockSaveUserWorkflow.mockRejectedValue(new Error(msg));
    renderComposer({ initialName: "Bad flow" });
    // Click the "Save workflow" button in the header
    await userEvent.click(screen.getByRole("button", { name: /Save workflow/i }));
    expect(await screen.findByText(msg)).toBeInTheDocument();
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
    // ADR-0010: SkillsHooksTab became HooksTab (skills half retired).
    expect(src).toMatch(/HooksTab/);
    expect(src).toMatch(/AgentPromptSection/);
  });
});
