/**
 * BUG-20260828-005700-workflows-ppt-canvas — "Save as copy" of a built-in
 * (and, more broadly, any Composer save with zero customized agents) silently
 * drops `runConfig` (deliverable/planner/clarify) from the persisted manifest.
 *
 * Root cause (ISS-206): two coupled ComposerPage.tsx defects.
 *  1. `needsFullManifest(pipelineAgents)` (the sole gate deciding whether Save
 *     includes `manifest: buildWorkflowManifest(...)`) only inspects per-node
 *     custom flags — never `runConfig` — so an unmodified/all-stock
 *     composition never sends `manifest` at all, regardless of what the
 *     Workflow tab shows.
 *  2. `runConfig` is seeded once via a plain `useState` initializer with no
 *     resync effect (unlike its sibling `pipelineAgents`/`selections`), so a
 *     later-arriving `initialRunConfig` prop (the real async race for a
 *     built-in canvas, since its `savedComposition.id` is always undefined
 *     and DashboardLayout's remount-by-key trick never fires) never reaches
 *     `runConfig` after first mount.
 *
 * Cards: ISS-196 (validated e2e repro), ISS-206 (root cause), ISS-203
 * (sibling built-ins), ISS-204 (sibling: any all-stock composer save),
 * ISS-205 (sibling: Run once loses its bypass on any reorder).
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderWithProviders, screen, waitFor } from "@/test/renderWithProviders";
import userEvent from "@testing-library/user-event";
import type { CapabilitiesPalette } from "@/lib/api";
import type { WorkflowType } from "@/types/index";
import type { ManifestStep } from "@/store/api/userWorkflows";

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
  capabilities: [],
  model_catalog: [],
};

// The `ppt` built-in's three stock steps (backend/agents/workflows/ppt/workflow.yaml).
const PPT_STEPS: ManifestStep[] = [
  { agent: "ppt-brief-analyst" },
  { agent: "ppt-composer" },
  { agent: "ppt-validator" },
];

function renderComposer(props: Record<string, unknown> = {}) {
  return renderWithProviders(
    <SkillsHooksProvider>
      <ComposerPage
        workflowType={"custom" as WorkflowType}
        onBack={() => {}}
        {...props}
      />
    </SkillsHooksProvider>,
    {
      preloadedState: {
        agents: {
          agents: [],
          totalCount: 0,
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

describe("ComposerPage — manifest/deliverable persistence (BUG-20260828-005700-workflows-ppt-canvas)", () => {
  // ISS-196 — validated e2e repro: Save as copy on the ppt built-in.
  it("ISS-196: Save as copy on the ppt built-in persists the real ppt deliverable, not the streamed_text default", async () => {
    renderComposer({
      builtinCanvasType: "ppt",
      initialManifestSteps: PPT_STEPS,
      initialRunConfig: {
        deliverable: { strategy: "ppt", name: "presentation.pptx" },
        planner: "skip",
        clarify: { mode: "skip", defaults: [] },
      },
      initialName: "PPT copy",
    });

    mockSaveUserWorkflow.mockResolvedValue({ id: "wf-ppt-copy" });
    await userEvent.click(screen.getByRole("button", { name: /Save as copy/i }));
    await waitFor(() => expect(mockSaveUserWorkflow).toHaveBeenCalled());

    const [, , payload] = mockSaveUserWorkflow.mock.calls[0] as [
      string,
      string | undefined,
      { manifest?: { deliverable?: { strategy: string; name: string } } },
    ];
    expect(payload.manifest).toBeTruthy();
    expect(payload.manifest?.deliverable?.strategy).toBe("ppt");
    expect(payload.manifest?.deliverable?.name).toBe("presentation.pptx");
  });

  // ISS-206 mechanism 2 — runConfig never resyncs once initialRunConfig
  // arrives on a LATER prop update (the real built-in-canvas race, since the
  // built-in's undefined savedComposition.id never changes DashboardLayout's
  // remount key).
  it("ISS-206: runConfig resyncs when initialRunConfig arrives after first mount, not just at mount", async () => {
    const { rerender } = renderComposer({
      builtinCanvasType: "ppt",
      initialManifestSteps: PPT_STEPS,
      initialName: "PPT copy",
      // No initialRunConfig yet — mirrors the built-in canvas's cold mount,
      // before GET /api/workflows/ppt resolves.
    });

    // The real manifest resolves a tick later and is handed down as a later
    // prop update (no remount — DashboardLayout's key never changes for a
    // built-in, ComposerPage.tsx / DashboardLayout.tsx:2906).
    rerender(
      <SkillsHooksProvider>
        <ComposerPage
          workflowType={"custom" as WorkflowType}
          onBack={() => {}}
          builtinCanvasType="ppt"
          initialManifestSteps={PPT_STEPS}
          initialName="PPT copy"
          initialRunConfig={{
            deliverable: { strategy: "ppt", name: "presentation.pptx" },
            planner: "skip",
            clarify: { mode: "skip", defaults: [] },
          }}
        />
      </SkillsHooksProvider>,
    );

    mockSaveUserWorkflow.mockResolvedValue({ id: "wf-ppt-copy" });
    await userEvent.click(screen.getByRole("button", { name: /Save as copy/i }));
    await waitFor(() => expect(mockSaveUserWorkflow).toHaveBeenCalled());

    const [, , payload] = mockSaveUserWorkflow.mock.calls[0] as [
      string,
      string | undefined,
      { manifest?: { deliverable?: { strategy: string; name: string } } },
    ];
    expect(payload.manifest?.deliverable?.strategy).toBe("ppt");
  });

  // ISS-203 — same loss, a different built-in with a non-default deliverable
  // (ppt_v2: single_file/presentation.html, backend/agents/workflows/ppt_v2/workflow.yaml).
  it("ISS-203: Save as copy on the ppt_v2 built-in persists its single_file/presentation.html deliverable", async () => {
    renderComposer({
      builtinCanvasType: "ppt_v2",
      initialManifestSteps: [
        { agent: "ppt-v2-brief-analyst" },
        { agent: "ppt-v2-composer" },
      ] as ManifestStep[],
      initialRunConfig: {
        deliverable: { strategy: "single_file", name: "presentation.html" },
        planner: "skip",
        clarify: { mode: "skip", defaults: [] },
      },
      initialName: "PPT v2 copy",
    });

    mockSaveUserWorkflow.mockResolvedValue({ id: "wf-pptv2-copy" });
    await userEvent.click(screen.getByRole("button", { name: /Save as copy/i }));
    await waitFor(() => expect(mockSaveUserWorkflow).toHaveBeenCalled());

    const [, , payload] = mockSaveUserWorkflow.mock.calls[0] as [
      string,
      string | undefined,
      { manifest?: { deliverable?: { strategy: string; name: string } } },
    ];
    expect(payload.manifest).toBeTruthy();
    expect(payload.manifest?.deliverable?.strategy).toBe("single_file");
    expect(payload.manifest?.deliverable?.name).toBe("presentation.html");
  });

  // ISS-204 — not built-in-specific: a from-scratch composition of only stock
  // library agents (no built-in involved at all) that only touches the
  // Workflow tab loses the same deliverable choice on Save.
  it("ISS-204: a from-scratch save of all-stock agents persists a Workflow-tab deliverable change (no built-in involved)", async () => {
    renderComposer({
      initialAgentIds: [], // genuinely from-scratch, no built-in, no manifest steps
      initialRunConfig: {
        deliverable: { strategy: "single_file", name: "report.html" },
        planner: "skip",
        clarify: { mode: "skip", defaults: [] },
      },
      initialName: "From scratch",
    });

    mockSaveUserWorkflow.mockResolvedValue({ id: "wf-scratch" });
    await userEvent.click(screen.getByRole("button", { name: /Save workflow/i }));
    await waitFor(() => expect(mockSaveUserWorkflow).toHaveBeenCalled());

    const [, , payload] = mockSaveUserWorkflow.mock.calls[0] as [
      string,
      string | undefined,
      { manifest?: { deliverable?: { strategy: string; name: string } } },
    ];
    expect(payload.manifest).toBeTruthy();
    expect(payload.manifest?.deliverable?.strategy).toBe("single_file");
    expect(payload.manifest?.deliverable?.name).toBe("report.html");
  });

  // ISS-205 — Run once loses the unmodifiedBuiltin bypass (and so is exposed
  // to the SAME stale runConfig from ISS-206 mechanism 2) the instant any
  // unrelated edit changes the agent-id order.
  it("ISS-205: Run once dispatches with the built-in's real deliverable after a pure reorder", async () => {
    const onRun = vi.fn();
    const { rerender } = renderComposer({
      onRun,
      builtinCanvasType: "ppt",
      initialManifestSteps: PPT_STEPS,
      initialName: "PPT copy",
      // Cold mount, no initialRunConfig yet — same race as the ISS-206 test.
    });
    rerender(
      <SkillsHooksProvider>
        <ComposerPage
          workflowType={"custom" as WorkflowType}
          onBack={() => {}}
          onRun={onRun}
          builtinCanvasType="ppt"
          initialManifestSteps={PPT_STEPS}
          initialName="PPT copy"
          initialRunConfig={{
            deliverable: { strategy: "ppt", name: "presentation.pptx" },
            planner: "skip",
            clarify: { mode: "skip", defaults: [] },
          }}
        />
      </SkillsHooksProvider>,
    );

    // Switch to Simple view to reorder agents and type a brief.
    await userEvent.click(screen.getByRole("button", { name: /^Simple$/ }));
    // Pure reorder — no deliverable/skill/prompt change — flips
    // `unmodifiedBuiltin` to false for the rest of the session.
    await userEvent.click(
      screen.getByRole("button", { name: /Move.*ppt-composer.*down/i }),
    );

    await userEvent.type(
      screen.getByPlaceholderText(/Describe what you want this workflow to produce/i),
      "Build the quarterly deck",
    );
    await userEvent.click(screen.getByRole("button", { name: /^Run once$/i }));

    await waitFor(() => expect(onRun).toHaveBeenCalled());
    const [, , , extraParams] = onRun.mock.calls[0] as [
      string,
      string,
      string[],
      { deliverable?: { strategy: string; name: string } } | undefined,
    ];
    expect(extraParams?.deliverable?.strategy).toBe("ppt");
  });
});
