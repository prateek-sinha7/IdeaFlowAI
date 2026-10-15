/**
 * ISS-371 (QA-KB-014) — the baseline moves the unsaved-work guard needs beyond
 * IdeaInputPage.iss371.test.tsx: a roster that lands AFTER mount (cold library,
 * steps from GET /api/workflows/{id}) is not a user edit, a successful Save is
 * not unsaved work, and unmount reports clean. A baseline taken once at mount
 * fails the first; one Save never moves fails the second.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import { renderWithProviders, screen, waitFor } from "@/test/renderWithProviders";

import { IdeaInputPage } from "./IdeaInputPage";
import type { WorkflowDetail } from "@/lib/api";

vi.mock("@/hooks/useSpeechRecognition", () => ({
  useSpeechRecognition: () => ({
    isListening: false,
    transcript: "",
    startListening: vi.fn(),
    stopListening: vi.fn(),
    isSupported: false,
  }),
}));
vi.mock("./AgentsPopup", () => ({ AgentsPopup: () => null }));
vi.mock("./ReviewGatesSection", () => ({ ReviewGatesSection: () => null }));

const mockGetWorkflowDetail = vi.fn();
const mockCreateUserWorkflow = vi.fn();
vi.mock("@/lib/api", () => ({
  getToken: () => "test-token",
  isNotFoundError: () => false,
  getWorkflowDetail: (token: string, id: string) => mockGetWorkflowDetail(token, id),
  createUserWorkflow: (token: string, body: unknown) => mockCreateUserWorkflow(token, body),
}));

const DETAIL: WorkflowDetail = {
  id: "user_stories",
  name: "User Stories",
  description: "",
  planner: "deep_planner",
  clarify_mode: "auto",
  clarify_defaults: [],
  context_providers: [],
  deliverable: { strategy: "single_file", name: "stories.md" },
  steps: [
    { agent_id: "domain-analyst", name: "Domain Analyst", role: "Discovery Lead", order: 1, strategy: "single_shot", gates: [], validators: [] },
  ],
};

// No preloaded agents: the library is empty at mount, as on a cold load, so the
// roster (and the Save button it enables) only appears once the detail resolves.
function renderPage() {
  const onUnsavedChange = vi.fn();
  const view = renderWithProviders(
    <IdeaInputPage
      workflowType="user_stories"
      workflowId="user_stories"
      onBack={vi.fn()}
      onRun={vi.fn()}
      onUnsavedChange={onUnsavedChange}
    />,
  );
  return { onUnsavedChange, unmount: view.unmount };
}

const rosterSeeded = () =>
  waitFor(() => expect(screen.getByRole("button", { name: /save workflow/i })).toBeEnabled());

describe("ISS-371 — the unsaved-work baseline follows seeds and saves", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetWorkflowDetail.mockResolvedValue(DETAIL);
    mockCreateUserWorkflow.mockResolvedValue({ id: "wf-1" });
  });

  it("a roster that arrives after mount is not unsaved work", async () => {
    const { onUnsavedChange } = renderPage();
    await rosterSeeded();
    expect(onUnsavedChange).toHaveBeenCalled();
    expect(onUnsavedChange).not.toHaveBeenCalledWith(true);
  });

  it("a successful Save is not unsaved work", async () => {
    const user = userEvent.setup();
    const { onUnsavedChange } = renderPage();
    await rosterSeeded();
    await user.type(screen.getByRole("textbox"), "Build a thing");
    expect(onUnsavedChange).toHaveBeenLastCalledWith(true);

    await user.click(screen.getByRole("button", { name: /save workflow/i }));
    await user.type(screen.getByLabelText(/workflow name/i), "Mine");
    await user.click(screen.getByRole("button", { name: /^save$/i }));

    await waitFor(() => expect(onUnsavedChange).toHaveBeenLastCalledWith(false));
    expect(mockCreateUserWorkflow).toHaveBeenCalledTimes(1);
  });

  it("unmount reports clean", async () => {
    const user = userEvent.setup();
    const { onUnsavedChange, unmount } = renderPage();
    await rosterSeeded();
    await user.type(screen.getByRole("textbox"), "x");
    expect(onUnsavedChange).toHaveBeenLastCalledWith(true);
    unmount();
    expect(onUnsavedChange).toHaveBeenLastCalledWith(false);
  });
});
