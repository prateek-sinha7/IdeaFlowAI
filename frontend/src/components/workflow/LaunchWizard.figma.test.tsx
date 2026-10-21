/**
 * LaunchWizard — Figma frames branching tests.
 *
 * Covers the hasFigmaFrames logic added in FEAT-002:
 *   - DS step hidden when Figma frames are uploaded to prototype_v2
 *   - DS step visible when no Figma frames present
 *   - steps prop excludes design-system when frames present
 *   - canContinue requires only brief (no DS) when hasFigmaFrames
 *   - canContinue requires DS when no frames
 *   - Figma tab badge shows frame count
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderWithProviders, screen, waitFor } from "@/test/renderWithProviders";
import userEvent from "@testing-library/user-event";
import type { AgentDef } from "@/types/index";
import type { FigmaFrame } from "@/components/workflow/prototype/FigmaUploadSection";

// ─────────────────────────────────────────────────────────────────
// Mocks
// ─────────────────────────────────────────────────────────────────

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn() }),
}));

vi.mock("@/lib/api", () => ({
  getToken: () => "mock-token",
  getMe: vi.fn().mockResolvedValue({ id: "u1", email: "qa@test.com", tier: "enterprise" }),
  extractFileText: vi.fn(),
  stageRunFile: vi.fn(),
  createUserWorkflow: vi.fn().mockResolvedValue({ id: "wf-1" }),
  saveUserWorkflow: vi.fn().mockResolvedValue({ id: "wf-1" }),
  getWorkflowDetail: vi.fn().mockResolvedValue({
    id: "prototype_v2",
    steps: [],
    manifest_steps: null,
    has_override: false,
    is_overridden: false,
    override_id: null,
  }),
  setWorkflowOverrideEnabled: vi.fn().mockResolvedValue({}),
}));

vi.mock("@/lib/prototype-api", () => ({
  listPrototypeTemplates: vi.fn().mockResolvedValue([
    { id: "kanban", name: "Kanban", example_prompt: null, has_preview: true, has_thumbnail: false },
  ]),
  listDesignSystems: vi.fn().mockResolvedValue([{ id: "midnight", name: "Midnight" }]),
  uploadFigmaFrames: vi.fn().mockResolvedValue({ run_id: "r1", files: [] }),
}));

vi.mock("@/lib/ppt-api", () => ({
  listPPTTemplates: vi.fn().mockResolvedValue([]),
}));

vi.mock("@/hooks/useSpeechRecognition", () => ({
  useSpeechRecognition: () => ({
    isListening: false, transcript: "", startListening: vi.fn(), stopListening: vi.fn(), isSupported: false,
  }),
}));

vi.mock("@/components/workflow/ReviewGatesSection", () => ({
  ReviewGatesSection: () => <div data-testid="review-gates" />,
}));

vi.mock("@/components/workflow/AgentsPopup", () => ({
  AgentsPopup: ({ pipelineType }: { pipelineType: string }) => (
    <div data-testid="agents-popup">{pipelineType}</div>
  ),
}));

vi.mock("@/components/catalog/NameWorkflowModal", () => ({
  NameWorkflowModal: () => <div data-testid="save-modal" />,
}));

vi.stubGlobal("IntersectionObserver", class {
  observe() {}
  disconnect() {}
  unobserve() {}
});

// WizardStepper stub: exposes figmaFrames/onFigmaFramesChange so tests can inject frames.
vi.mock("@/components/workflow/WizardStepper", () => ({
  WizardStepper: (props: {
    mode: "web" | "deck";
    onModeChange: (m: "web" | "deck") => void;
    onWebSelect: (id: string | null) => void;
    steps?: string[];
    dsSlot?: React.ReactNode;
    discoverySlot?: React.ReactNode;
    figmaFrames?: FigmaFrame[];
    onFigmaFramesChange?: (frames: FigmaFrame[]) => void;
  }) => (
    <div
      data-testid="stepper"
      data-mode={props.mode}
      data-steps={(props.steps ?? ["template", "design-system", "discovery"]).join(",")}
      data-figma-count={props.figmaFrames?.length ?? 0}
    >
      <button data-testid="pick-web" onClick={() => props.onWebSelect("kanban")}>webpick</button>
      <button
        data-testid="add-figma-frame"
        onClick={() => {
          const f: FigmaFrame = {
            file: new File([new Uint8Array(100)], "frame.png", { type: "image/png" }),
            description: "",
            previewUrl: "blob:http://localhost/mock",
          };
          props.onFigmaFramesChange?.([...(props.figmaFrames ?? []), f]);
        }}
      >
        add figma frame
      </button>
      <div data-testid="ds-slot">{props.dsSlot}</div>
      <div data-testid="discovery-slot">{props.discoverySlot}</div>
    </div>
  ),
}));

vi.mock("@/components/workflow/prototype/DesignSystemPicker", () => ({
  DesignSystemPicker: ({ onSelect }: { onSelect: (id: string) => void }) => (
    <button data-testid="pick-ds" onClick={() => onSelect("midnight")}>ds</button>
  ),
}));

// ─────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────

import React from "react";
import { LaunchWizard } from "./LaunchWizard";

const makeAgents = (): AgentDef[] =>
  [
    "fi-planner", "fi-reader-01", "prototype-builder",
    "ppt-planner", "ppt-deck-generator",
  ].map((id, idx) => ({
    id,
    name: id,
    role: "Agent",
    description: "",
    pipeline_type: id.startsWith("ppt") ? "ppt" : "prototype_v2",
    order: idx + 1,
    icon: "zap",
    estimated_duration: 60,
    has_skill: false,
  }));

const stateWith = (agents: AgentDef[]) => ({
  agents: {
    agents,
    totalCount: agents.length,
    pipelines: {},
    status: "succeeded" as const,
    error: null,
  },
});

beforeEach(() => {
  sessionStorage.clear();
  vi.clearAllMocks();
});

// ─────────────────────────────────────────────────────────────────
// Tests
// ─────────────────────────────────────────────────────────────────

describe("LaunchWizard — Figma frames branching (FEAT-002)", () => {
  it("design_system_step_visible_when_prototype_v2_has_no_figma_frames", async () => {
    renderWithProviders(<LaunchWizard initialMode="prototype_v2" />, {
      preloadedState: stateWith(makeAgents()),
    });
    // Wait for component to settle
    await screen.findByTestId("stepper");
    // DS slot should contain the picker (dsVisible=true, no figma frames)
    await waitFor(() => {
      const dsSlot = screen.getByTestId("ds-slot");
      // dsSlot contains either the picker or the loading pulse — either way it is rendered
      expect(dsSlot.children.length).toBeGreaterThan(0);
    });
    // steps should include design-system
    const stepper = screen.getByTestId("stepper");
    expect(stepper.getAttribute("data-steps")).toContain("design-system");
  });

  it("design_system_pill_hidden_when_figma_frames_uploaded_to_prototype_v2", async () => {
    const user = userEvent.setup();
    renderWithProviders(<LaunchWizard initialMode="prototype_v2" />, {
      preloadedState: stateWith(makeAgents()),
    });
    await screen.findByTestId("stepper");

    // Simulate adding a Figma frame
    await user.click(screen.getByTestId("add-figma-frame"));

    // The DS pill ("Pick a design system") should now be hidden
    await waitFor(() => {
      expect(screen.queryByText("Pick a design system")).toBeNull();
    });
  });

  it("steps_array_excludes_design_system_when_figma_frames_present", async () => {
    const user = userEvent.setup();
    renderWithProviders(<LaunchWizard initialMode="prototype_v2" />, {
      preloadedState: stateWith(makeAgents()),
    });
    await screen.findByTestId("stepper");

    // Add a frame
    await user.click(screen.getByTestId("add-figma-frame"));

    await waitFor(() => {
      const stepper = screen.getByTestId("stepper");
      const steps = stepper.getAttribute("data-steps") ?? "";
      expect(steps).not.toContain("design-system");
      expect(steps).toContain("template");
      expect(steps).toContain("discovery");
    });
  });

  it("continue_button_enabled_with_brief_only_when_figma_frames_uploaded", async () => {
    const user = userEvent.setup();
    renderWithProviders(<LaunchWizard initialMode="prototype_v2" />, {
      preloadedState: stateWith(makeAgents()),
    });
    // Wait for brief textarea
    const brief = await screen.findByLabelText("Describe what you're building");
    await user.type(brief, "Build a dashboard prototype");

    // Add Figma frame — DS should no longer be required
    await user.click(screen.getByTestId("add-figma-frame"));

    // Continue should become enabled without selecting a DS
    await waitFor(() => {
      const btn = screen.getByRole("button", { name: "Continue" });
      expect(btn).not.toBeDisabled();
    });
  });

  it("continue_button_disabled_without_ds_when_no_figma_frames", async () => {
    const user = userEvent.setup();
    renderWithProviders(<LaunchWizard initialMode="prototype_v2" />, {
      preloadedState: stateWith(makeAgents()),
    });
    const brief = await screen.findByLabelText("Describe what you're building");
    await user.type(brief, "Build a dashboard prototype");
    // No Figma frames, no DS selected → Continue must be disabled
    const btn = screen.getByRole("button", { name: "Continue" });
    expect(btn).toBeDisabled();
  });

  it("figma_tab_shows_frame_count_badge_when_frames_present", async () => {
    const user = userEvent.setup();
    renderWithProviders(<LaunchWizard initialMode="prototype_v2" />, {
      preloadedState: stateWith(makeAgents()),
    });
    await screen.findByTestId("stepper");

    // Add a frame and check the data-figma-count attribute on the stepper stub
    await user.click(screen.getByTestId("add-figma-frame"));

    await waitFor(() => {
      const stepper = screen.getByTestId("stepper");
      expect(stepper.getAttribute("data-figma-count")).toBe("1");
    });
  });
});
