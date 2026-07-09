/**
 * SC-001 / INV-1 — the Configure screen is a GENERIC per-run setup surface. The
 * Templates + Design System accordions render ONLY when the selected deliverable
 * DECLARES `context_providers:[opendesign]` — the SAME declared signal the Wave-1
 * backend seam keys on — NEVER a prototype-name branch. Any deliverable that
 * declares the opendesign context provider GAINS the accordions with zero
 * per-deliverable code; one that does not shows only Describe + Review Gates +
 * Workflow Settings.
 *
 * These tests render the REAL ConfigureScreen and mock only the seams: the
 * network read (`getWorkflowDetail`, which drives the declared-signal gating) and
 * the heavy child surfaces (TemplateGallery/DesignSystemPicker/AdvancedExpander)
 * which fetch live registries.
 */

import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

import { ConfigureScreen } from "./ConfigureScreen";
import type { WorkflowDetail } from "@/lib/api";

const mockGetWorkflowDetail = vi.fn();
vi.mock("@/lib/api", () => ({
  getToken: () => "test-token",
  getWorkflowDetail: (token: string, id: string) => mockGetWorkflowDetail(token, id),
}));

// The Template/DS pickers fetch live registries — stub them so the gating is what's
// under test, not the pickers themselves.
vi.mock("@/lib/prototype-api", () => ({
  listPrototypeTemplates: vi.fn().mockResolvedValue([]),
  listDesignSystems: vi.fn().mockResolvedValue([]),
}));
vi.mock("./prototype/TemplateGallery", () => ({
  TemplateGallery: () => <div data-testid="stub-template-gallery" />,
}));
vi.mock("./prototype/DesignSystemPicker", () => ({
  DesignSystemPicker: () => <div data-testid="stub-ds-picker" />,
}));
vi.mock("./AgentsPopup", () => ({
  AdvancedExpander: () => <div data-testid="stub-advanced-expander" />,
}));
vi.mock("./ReviewGatesSection", () => ({
  ReviewGatesSection: () => <div data-testid="stub-review-gates" />,
}));

function detail(contextProviders: string[]): WorkflowDetail {
  return {
    id: "any-deliverable",
    name: "Any Deliverable",
    description: "",
    planner: "deep_planner",
    clarify_mode: "auto",
    clarify_defaults: [],
    context_providers: contextProviders,
    deliverable: { strategy: "x", name: "y" },
    steps: [
      { agent_id: "a1", name: "Agent One", role: "r", order: 1, strategy: "s", gates: [], validators: [], compaction: null, task_source: null, declared_gate: null },
    ],
  };
}

describe("ConfigureScreen — declared-signal accordion gating (SC-001)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
  });

  it("renders the Templates + Design System accordions when context_providers includes 'opendesign'", async () => {
    mockGetWorkflowDetail.mockResolvedValue(detail(["opendesign"]));
    render(<ConfigureScreen workflowId="any-deliverable" />);

    await waitFor(() =>
      expect(mockGetWorkflowDetail).toHaveBeenCalledWith("test-token", "any-deliverable"),
    );

    // Always-present accordions.
    expect(await screen.findByTestId("accordion-describe")).toBeInTheDocument();
    expect(screen.getByTestId("accordion-gates")).toBeInTheDocument();
    expect(screen.getByTestId("accordion-settings")).toBeInTheDocument();

    // Declared-signal-gated accordions — present here.
    expect(screen.getByTestId("accordion-templates")).toBeInTheDocument();
    expect(screen.getByTestId("accordion-designsystem")).toBeInTheDocument();
  });

  it("HIDES the Templates + Design System accordions when 'opendesign' is NOT declared", async () => {
    mockGetWorkflowDetail.mockResolvedValue(detail([]));
    render(<ConfigureScreen workflowId="any-deliverable" />);

    expect(await screen.findByTestId("accordion-describe")).toBeInTheDocument();
    expect(screen.getByTestId("accordion-gates")).toBeInTheDocument();
    expect(screen.getByTestId("accordion-settings")).toBeInTheDocument();

    expect(screen.queryByTestId("accordion-templates")).not.toBeInTheDocument();
    expect(screen.queryByTestId("accordion-designsystem")).not.toBeInTheDocument();
  });
});
