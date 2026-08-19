/**
 * SURF-03 (live-path wiring) — opening a launchable/saved workflow with a known
 * backend workflow id fetches its compiled per-step capability projection
 * (GET /api/workflows/{id}) and surfaces it in the composer as the AgentsPopup
 * "Declared by this workflow" strip, sourced from the projection (not a hardcoded
 * description).
 *
 * This is the LIVE-PATH test the SURF-03 verification gap demanded: unlike the
 * isolated `CapabilityPaletteSection.test.tsx` (which injects fixture
 * `declaredCapabilities` directly into the exported sub-component), this renders
 * the REAL `IdeaInputPage` + REAL `AgentsPopup` and only mocks the network seam
 * (`@/lib/api`). It proves the prop is actually POPULATED on the production path:
 *   - `getWorkflowDetail(token, workflowId)` is invoked when a `workflowId` is present;
 *   - the fetched projection maps to per-step declared capabilities; and
 *   - opening the AgentsPopup renders the "Declared by this workflow" strip with them.
 *
 * The no-id (from-scratch) case is also pinned: no fetch, no strip.
 */

import { describe, expect, it, vi, beforeEach } from "vitest";
import { renderWithProviders, screen, waitFor } from "@/test/renderWithProviders";
import userEvent from "@testing-library/user-event";

import { IdeaInputPage } from "./IdeaInputPage";
import { SkillsHooksProvider } from "@/context/SkillsHooksContext";
import type { WorkflowDetail, CapabilitiesPalette } from "@/lib/api";

vi.mock("@/hooks/useSpeechRecognition", () => ({
  useSpeechRecognition: () => ({
    isListening: false,
    transcript: "",
    startListening: vi.fn(),
    stopListening: vi.fn(),
    isSupported: false,
  }),
}));

// Mock ONLY the network seam — the real IdeaInputPage and real AgentsPopup render.
const mockGetWorkflowDetail = vi.fn();
const mockGetCapabilities = vi.fn();
vi.mock("@/lib/api", () => ({
  getToken: () => "test-token",
  // IdeaInputPage uses these two; AgentsPopup's palette/model picker fetch the rest.
  getWorkflowDetail: (token: string, id: string) => mockGetWorkflowDetail(token, id),
  getCapabilities: (token: string) => mockGetCapabilities(token),
  createUserWorkflow: vi.fn(),
}));

vi.mock("./ReviewGatesSection", () => ({
  ReviewGatesSection: () => null,
}));

// The compiled-plan projection the BE (GET /api/workflows/{id}) returns — the
// per-step DECLARED capabilities sourced from the ExecutionPlan (SURF-03).
const PROJECTION: WorkflowDetail = {
  id: "prototype",
  name: "Prototype",
  description: "Build an interactive prototype.",
  planner: "deep_planner",
  clarify_mode: "auto",
  clarify_defaults: [],
  context_providers: [],
  deliverable: { strategy: "prototype_html", name: "prototype.html" },
  steps: [
    {
      agent_id: "prototype-build",
      name: "Prototype Builder",
      role: "Builds the prototype",
      order: 2,
      strategy: "per_task_subagent",
      gates: [],
      validators: ["render_check", "static_check"],
      compaction: null,
      task_source: { kind: "tasks_md", parser: null, target: null },
      declared_gate: null,
    },
  ],
};

const EMPTY_PALETTE: CapabilitiesPalette = { capabilities: [], model_catalog: [] };

function renderPage(workflowId?: string) {
  renderWithProviders(
    <SkillsHooksProvider>
      <IdeaInputPage
        workflowType="prototype"
        onBack={vi.fn()}
        onRun={vi.fn()}
        workflowId={workflowId}
      />
    </SkillsHooksProvider>,
  );
}

describe("IdeaInputPage — SURF-03 declared-capabilities live wiring", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetWorkflowDetail.mockResolvedValue(PROJECTION);
    mockGetCapabilities.mockResolvedValue(EMPTY_PALETTE);
  });

  it("fetches the compiled projection by id and renders the 'Declared by this workflow' strip", async () => {
    const user = userEvent.setup();
    renderPage("prototype");

    // The live path fetches the compiled-plan projection for the opened id.
    await waitFor(() =>
      expect(mockGetWorkflowDetail).toHaveBeenCalledWith("test-token", "prototype"),
    );

    // Open the composer (AgentsPopup) via the Advanced control.
    await user.click(screen.getByRole("button", { name: /advanced/i }));

    // The capabilities strip lives on the AgentsPopup "Workflow" tab (Skills /
    // Hooks / Capabilities), not the default "Agents" tab — switch to it.
    await user.click(screen.getAllByRole("button", { name: /^workflow/i })[0]);

    // The SURF-03 strip renders, sourced from the fetched projection — the step
    // name + its per-step declared capabilities (validators) appear.
    await waitFor(() =>
      expect(screen.getByText("Declared by this workflow")).toBeInTheDocument(),
    );
    expect(screen.getByText("Prototype Builder")).toBeInTheDocument();
    expect(
      screen.getByText(/validator:render_check/),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/validator:static_check/),
    ).toBeInTheDocument();
    expect(screen.getByText(/strategy:per_task_subagent/)).toBeInTheDocument();
  });

  it("does NOT fetch or render the strip for a from-scratch composition (no id)", async () => {
    const user = userEvent.setup();
    renderPage(undefined);

    await user.click(screen.getByRole("button", { name: /advanced/i }));
    // Navigate to the same "Workflow" tab the strip would render on, so the
    // absence assertion is meaningful (not merely "wrong tab").
    await user.click(screen.getAllByRole("button", { name: /^workflow/i })[0]);

    // No id ⇒ no projection fetch and the strip never renders.
    expect(mockGetWorkflowDetail).not.toHaveBeenCalled();
    await waitFor(() =>
      expect(screen.queryByText("Declared by this workflow")).not.toBeInTheDocument(),
    );
  });
});
