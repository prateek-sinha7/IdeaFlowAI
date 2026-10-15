/**
 * ISS-923 (QA-KB-060): a transient seed failure on /workflows/{id}/edit leaves
 * ComposerPage with no row id, so Save workflow takes the create branch and POSTs a
 * new row. The fix threads a URL-derived `expectedUserWorkflowId`; Save is disabled
 * while it is set and no row id arrived.
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

describe("ComposerPage — Save workflow gated on the /edit seed (ISS-923)", () => {
  it("ISS-923: Save workflow is disabled when an edit id was expected but no row arrived", () => {
    render({ expectedUserWorkflowId: "wf-123", initialName: "renamed" });
    expect(screen.getByRole("button", { name: /Save workflow/i })).toBeDisabled();
  });

  it("ISS-923: clicking Save workflow with no seeded row never POSTs a new workflow", async () => {
    render({ expectedUserWorkflowId: "wf-123", initialName: "renamed", initialManifestSteps: PPT_STEPS });
    await userEvent.click(screen.getByRole("button", { name: /Save workflow/i }));
    expect(mockSaveUserWorkflow).not.toHaveBeenCalled();
  });

  // Guards against over-blocking: green today and after the fix.
  it("ISS-923: Save workflow is enabled once the row id arrives", () => {
    const { rerender } = render({ expectedUserWorkflowId: "wf-123", initialName: "renamed" });
    // `key`: the seed arrives by DashboardLayout's key flip (a remount); a plain rerender never re-runs useState initializers.
    rerender(ui({ key: "wf-123", expectedUserWorkflowId: "wf-123", initialUserWorkflowId: "wf-123", initialName: "renamed", initialManifestSteps: PPT_STEPS }));
    expect(screen.getByRole("button", { name: /Save workflow/i })).toBeEnabled();
  });
});
