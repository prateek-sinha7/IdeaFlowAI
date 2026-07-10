/**
 * WR-02 — the SURF-03 WorkflowDialog is MOUNTED and REACHABLE.
 *
 * The 300-line read-only WorkflowDialog shipped in Phase 37 (37-06) but was
 * mounted by no navigator ("wiring a trigger is a follow-on integration
 * concern"). This pins the follow-on: every launchable catalog row exposes an
 * inspect affordance that opens the dialog WITHOUT launching (a sibling of the
 * launch button — never a nested button, so both stay valid focusable controls).
 *
 * Mocks mirror HomeLaunchGrid.test.tsx (api + next/navigation + the motion tag
 * proxy) and additionally stub the two WorkflowDialog seams (getWorkflowDetail /
 * getCapabilities) so the dialog renders without a real backend.
 */

import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import React from "react";
import type {
  WorkflowSummary,
  WorkflowDetail,
  CapabilitiesPalette,
} from "@/lib/api";

const mockGetWorkflowDefinitions =
  vi.fn<(token: string) => Promise<WorkflowSummary[]>>();
const mockGetUserWorkflows = vi.fn(async () => []);
const mockGetWorkflowDetail = vi.fn<(t: string, id: string) => Promise<WorkflowDetail>>();
const mockGetCapabilities = vi.fn<(t: string) => Promise<CapabilitiesPalette>>();

vi.mock("@/lib/api", () => ({
  getToken: () => "test-token",
  getWorkflowDefinitions: (t: string) => mockGetWorkflowDefinitions(t),
  getUserWorkflows: () => mockGetUserWorkflows(),
  // 38-05: the grid's mount effect now also fetches the owner-scoped history
  // average for the per-card estimate. Stub it here so the inspect-affordance
  // tests still render (agents-only estimate; no history-time assertions here).
  getAnalyticsSummary: async () => ({ type_avg_duration_sec: {} }),
  getWorkflowDetail: (t: string, id: string) => mockGetWorkflowDetail(t, id),
  getCapabilities: (t: string) => mockGetCapabilities(t),
}));

const mockPush = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush }),
}));

const STRIPPED = new Set([
  "initial", "animate", "exit", "transition", "whileHover", "whileTap",
  "whileFocus", "whileInView", "viewport", "layout", "layoutId", "drag",
  "dragConstraints", "variants", "custom",
]);
vi.mock("motion/react", () => ({
  motion: new Proxy({}, {
    get: (_t, prop: string) =>
      ({ children, ...rest }: { children?: React.ReactNode } & Record<string, unknown>) =>
        React.createElement(
          prop,
          Object.fromEntries(Object.entries(rest).filter(([k]) => !STRIPPED.has(k))),
          children,
        ),
  }),
  AnimatePresence: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
}));

import { HomeLaunchGrid } from "./HomeLaunchGrid";

const ROWS: WorkflowSummary[] = [
  {
    id: "user_stories",
    name: "raw-name",
    description: "Epics + stories.",
    step_count: 3,
    steps: [],
    user_launchable: true,
    display_name: "Generate product requirements",
    icon: null,
    launch_surface: null,
  },
];

const DETAIL: WorkflowDetail = {
  id: "user_stories",
  name: "Generate product requirements",
  description: "",
  planner: "deep_planner",
  clarify_mode: "auto",
  clarify_defaults: [],
  context_providers: ["conversation"],
  deliverable: { strategy: "x", name: "y" },
  steps: [],
};

const PALETTE: CapabilitiesPalette = { capabilities: [], model_catalog: [] };

describe("HomeLaunchGrid — WR-02 WorkflowDialog inspect affordance", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetWorkflowDefinitions.mockResolvedValue(ROWS);
    mockGetWorkflowDetail.mockResolvedValue(DETAIL);
    mockGetCapabilities.mockResolvedValue(PALETTE);
  });

  it("renders a per-row inspect affordance (distinct from the launch button)", async () => {
    render(<HomeLaunchGrid onSelectFeature={vi.fn()} userTier="enterprise" />);
    // The inspect control is present, labelled, and NOT the launch button.
    const inspect = await screen.findByRole("button", {
      name: /inspect Generate product requirements details/i,
    });
    expect(inspect).toBeInTheDocument();
  });

  it("opens the read-only WorkflowDialog on inspect WITHOUT launching", async () => {
    const onSelectFeature = vi.fn();
    render(<HomeLaunchGrid onSelectFeature={onSelectFeature} userTier="enterprise" />);

    const inspect = await screen.findByRole("button", {
      name: /inspect Generate product requirements details/i,
    });
    await userEvent.click(inspect);

    // The dialog opens and reads the compiled workflow's declared data.
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toBeInTheDocument();
    await waitFor(() =>
      expect(mockGetWorkflowDetail).toHaveBeenCalledWith("test-token", "user_stories"),
    );

    // Inspect must NOT launch: no navigation, no feature selection.
    expect(mockPush).not.toHaveBeenCalled();
    expect(onSelectFeature).not.toHaveBeenCalled();
  });
});
