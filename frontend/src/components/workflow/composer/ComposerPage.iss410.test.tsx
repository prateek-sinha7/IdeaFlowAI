/**
 * ISS-410 (QA-KB-018): a transient seed failure on /workflows/{id}/canvas leaves
 * builtinCanvasType set with no seed props, yet "Save as copy" stays enabled and
 * posts a blank copy. Guards the fix: Save as copy is disabled while
 * builtinCanvasType is set and nothing seeded it.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderWithProviders, screen } from "@/test/renderWithProviders";
import userEvent from "@testing-library/user-event";
import type { WorkflowType } from "@/types/index";
import type { ManifestStep } from "@/store/api/userWorkflows";

const mockSaveUserWorkflow = vi.fn();
vi.mock("@/lib/api", () => ({
  getToken: () => "test-token",
  getCapabilities: vi.fn().mockResolvedValue({ capabilities: [], model_catalog: [] }),
  saveUserWorkflow: (...a: unknown[]) => mockSaveUserWorkflow(...a),
  getWorkflowDetail: vi.fn().mockResolvedValue({ steps: [] }),
  getAgentPrompt: vi.fn().mockResolvedValue({ prompt_body: "", override: null, has_override: false }),
  saveAgentPromptOverride: vi.fn(),
  deleteAgentPromptOverride: vi.fn(),
}));

import { ComposerPage } from "./ComposerPage";
import { SkillsHooksProvider } from "@/context/SkillsHooksContext";

const PPT_STEPS: ManifestStep[] = [{ agent: "ppt-brief-analyst" }, { agent: "ppt-composer" }];

function ui(props: Record<string, unknown>) {
  return (
    <SkillsHooksProvider>
      <ComposerPage workflowType={"custom" as WorkflowType} onBack={() => {}} {...props} />
    </SkillsHooksProvider>
  );
}
const render = (props: Record<string, unknown>) =>
  renderWithProviders(ui(props), {
    preloadedState: {
      agents: { agents: [], totalCount: 0, pipelines: {}, status: "succeeded", error: null },
    },
  });

beforeEach(() => {
  vi.clearAllMocks();
  mockSaveUserWorkflow.mockResolvedValue({ id: "wf" });
});

describe("ComposerPage — Save as copy gated on the built-in seed (ISS-410)", () => {
  it("ISS-410: Save as copy is disabled when builtinCanvasType is set and no seed arrived", () => {
    render({ builtinCanvasType: "ppt", initialName: "my copy" });
    expect(screen.getByRole("button", { name: /Save as copy/i })).toBeDisabled();
  });

  it("ISS-410: clicking Save as copy with no seed never POSTs a blank copy", async () => {
    render({ builtinCanvasType: "ppt", initialName: "my copy" });
    await userEvent.click(screen.getByRole("button", { name: /Save as copy/i }));
    expect(mockSaveUserWorkflow).not.toHaveBeenCalled();
  });

  // Guards against over-blocking: green today and after the fix.
  it("ISS-410: Save as copy is enabled once the seed lands", () => {
    const { rerender } = render({ builtinCanvasType: "ppt", initialName: "my copy" });
    rerender(ui({ builtinCanvasType: "ppt", initialName: "my copy", initialManifestSteps: PPT_STEPS }));
    expect(screen.getByRole("button", { name: /Save as copy/i })).toBeEnabled();
  });
});
