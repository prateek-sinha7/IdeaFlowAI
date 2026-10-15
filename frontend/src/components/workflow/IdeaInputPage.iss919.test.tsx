/**
 * ISS-919 (QA-KB-059) — IdeaInputPage Save workflow / Save as my version / Advanced stay enabled
 * while GET /api/workflows/{id} is pending, so a click UPSERTs the library roster over the real
 * override. Siblings: ISS-984 (rejected GET leaves Save as my version enabled), ISS-983 (edit in the
 * window is re-seeded away). Each test is `it.fails` while unfixed: it asserts CORRECT behaviour, so
 * it goes green-by-inversion today and turns RED once the fix lands (remove `.fails` then).
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import { renderWithProviders, screen, waitFor } from "@/test/renderWithProviders";

import { IdeaInputPage } from "@/components/workflow/IdeaInputPage";
import type { AgentDef } from "@/types/index";

vi.mock("@/hooks/useSpeechRecognition", () => ({
  useSpeechRecognition: () => ({
    isListening: false,
    transcript: "",
    startListening: vi.fn(),
    stopListening: vi.fn(),
    isSupported: false,
  }),
}));

const mockGetWorkflowDetail = vi.fn();
const mockCreateUserWorkflow = vi.fn();
const mockIsNotFound = vi.fn(() => false);
vi.mock("@/lib/api", () => ({
  getToken: () => "test-token",
  isNotFoundError: () => mockIsNotFound(),
  getWorkflowDetail: (t: string, id: string) => mockGetWorkflowDetail(t, id),
  createUserWorkflow: (t: string, b: unknown) => mockCreateUserWorkflow(t, b),
  setWorkflowOverrideEnabled: vi.fn(),
  extractFileText: vi.fn(),
  stageRunFile: vi.fn(),
  getCapabilities: vi.fn().mockResolvedValue({ capabilities: [], model_catalog: [] }),
}));

// Popup stub: shows the roster it was handed and lets a test make an in-popup edit
// through the SAME host callback the real popup uses (onReorder -> handleReorderAgents).
vi.mock("@/components/workflow/AgentsPopup", () => ({
  AgentsPopup: (p: { agents: { id: string }[]; onReorder?: (a: { id: string }[]) => void }) => (
    <div>
      <span data-testid="popup-agents">{p.agents.map((a) => a.id).join(",")}</span>
      <button data-testid="popup-drop-last" onClick={() => p.onReorder?.(p.agents.slice(0, -1))}>
        drop-last
      </button>
    </div>
  ),
}));
vi.mock("@/components/workflow/ReviewGatesSection", () => ({ ReviewGatesSection: () => null }));

const IDS = ["domain-analyst", "epic-architect", "story-estimator", "nfr-specialist"];
const libraryAgents = (): AgentDef[] =>
  IDS.map((id, i) => ({
    id,
    name: id,
    role: "r",
    description: "d",
    pipeline_type: "user_stories",
    order: i + 1,
    icon: "zap",
    estimated_duration: 60,
    has_skill: false,
  }));
const preload = (list: AgentDef[]) => ({
  agents: { agents: list, totalCount: list.length, pipelines: {}, status: "succeeded" as const, error: null },
});

function renderPage() {
  return renderWithProviders(
    <IdeaInputPage workflowType="user_stories" workflowId="user_stories" onBack={vi.fn()} onRun={vi.fn()} />,
    { preloadedState: preload(libraryAgents()) },
  );
}

const NO_OVERRIDE_DETAIL = {
  id: "user_stories",
  name: "User Stories",
  description: "",
  planner: "deep_planner",
  clarify_mode: "auto",
  clarify_defaults: [],
  context_providers: [],
  deliverable: { strategy: "single_file", name: "stories.md" },
  steps: [],
  has_override: false,
  is_overridden: false,
  override_id: null,
};

beforeEach(() => {
  vi.clearAllMocks();
  mockIsNotFound.mockReturnValue(false);
  mockCreateUserWorkflow.mockResolvedValue({ id: "wf-scratch" });
});

describe("QA-KB-059 scratch: IdeaInputPage while GET /api/workflows/user_stories is PENDING", () => {
  it("ISS-919 T1 both Save buttons should be disabled (red today = defect observed)", async () => {
    mockGetWorkflowDetail.mockReturnValue(new Promise(() => {})); // never settles
    renderPage();
    const saveAs = await screen.findByRole("button", { name: /Save as my version/ });
    const save = screen.getByRole("button", { name: /Save workflow/ });
    const advanced = screen.getByRole("button", { name: /Advanced/ });
    console.log(
      "[T1] pending window: saveAsMyVersion.disabled=%s saveWorkflow.disabled=%s advanced.disabled=%s advancedLabel=%j",
      (saveAs as HTMLButtonElement).disabled,
      (save as HTMLButtonElement).disabled,
      (advanced as HTMLButtonElement).disabled,
      advanced.textContent,
    );
    expect.soft(saveAs).toBeDisabled();
    expect.soft(save).toBeDisabled();
    expect.soft(advanced).toBeDisabled();
  });

  it("ISS-919 T2 clicking Save as my version while pending sends the library roster as an override UPSERT", async () => {
    const user = userEvent.setup();
    mockGetWorkflowDetail.mockReturnValue(new Promise(() => {}));
    renderPage();
    await user.click(await screen.findByRole("button", { name: /Save as my version/ }));
    console.log("[T2] createUserWorkflow calls while detail pending:", mockCreateUserWorkflow.mock.calls.length);
    const body = (mockCreateUserWorkflow.mock.calls[0]?.[1] ?? {}) as Record<string, unknown>;
    console.log(
      "[T2] POST body: %s",
      JSON.stringify({
        overrides_pipeline_type: body.overrides_pipeline_type,
        base_pipeline_type: body.base_pipeline_type,
        agent_ids: body.agent_ids,
      }),
    );
    expect(mockCreateUserWorkflow).not.toHaveBeenCalled(); // red today
  });
});

describe("QA-KB-059 scratch: the FAILED-fetch window (adjacent state)", () => {
  it("ISS-984 T3 a rejected GET leaves Save as my version enabled and shows no error", async () => {
    mockGetWorkflowDetail.mockRejectedValue(new Error("503 upstream"));
    renderPage();
    await waitFor(() => expect(mockGetWorkflowDetail).toHaveBeenCalled());
    await new Promise((r) => setTimeout(r, 60)); // let .catch run and state flush
    const saveAs = screen.getByRole("button", { name: /Save as my version/ });
    const banner = screen.queryByText(/Failed to load this workflow/);
    console.log(
      "[T3] after rejected GET: saveAsMyVersion.disabled=%s errorBannerShown=%s",
      (saveAs as HTMLButtonElement).disabled,
      Boolean(banner),
    );
    expect.soft(saveAs).toBeDisabled(); // red today
  });
});

describe("QA-KB-059 scratch: an edit made in the window vs the late overlay (Advanced trigger)", () => {
  // Per ISS-983 "For the test-writer": once the trigger is gated the in-window edit cannot be made,
  // so assert the trigger (disabled while pending, enabled once the detail lands), not the popup.
  it("ISS-983 T4 the Advanced trigger is disabled while the detail is pending and enabled once it lands", async () => {
    let resolveDetail!: (d: unknown) => void;
    mockGetWorkflowDetail.mockReturnValue(new Promise((r) => { resolveDetail = r; }));
    renderPage();
    await screen.findByRole("button", { name: /Save as my version/ });
    const advanced = () => screen.getByRole("button", { name: /Advanced/ }) as HTMLButtonElement;
    const pending = advanced().disabled;
    resolveDetail(NO_OVERRIDE_DETAIL); // overlay lands
    await waitFor(() => expect(advanced()).toBeEnabled());
    console.log("[T4] advanced.disabled pending=%s settled=%s", pending, advanced().disabled);
    expect(pending).toBe(true); // red today = the window is open to an edit the overlay re-seeds away
  });
});

// The controls ISS-919 lists for this file: the settled states a literal reading of the triage sketch
// gets wrong. A success-only flag on both Save buttons kills Save workflow after any failed GET
// (migration's 404s by design); a `.finally` flag re-enables the UPSERT after one. Plain tests.
describe("QA-KB-059 controls: once the detail has settled", () => {
  const button = (name: RegExp) => screen.getByRole("button", { name }) as HTMLButtonElement;

  it("resolved with no override: Save as my version, Save workflow and Advanced are enabled", async () => {
    mockGetWorkflowDetail.mockResolvedValue(NO_OVERRIDE_DETAIL);
    renderPage();
    await waitFor(() => expect(button(/Save as my version/)).toBeEnabled());
    expect(button(/Save workflow/)).toBeEnabled();
    expect(button(/Advanced/)).toBeEnabled();
  });

  it.each([
    ["503", false],
    ["404, the migration shape", true],
  ])("rejected (%s): Save as my version disabled with a reason, Save workflow and Advanced enabled", async (_label, notFound) => {
    mockIsNotFound.mockReturnValue(notFound);
    mockGetWorkflowDetail.mockRejectedValue(new Error("rejected"));
    renderPage();
    await waitFor(() => expect(button(/Save workflow/)).toBeEnabled());
    expect(button(/Advanced/)).toBeEnabled();
    expect(button(/Save as my version/)).toBeDisabled();
    expect(button(/Save as my version/).title).toMatch(/Couldn't check for your saved version/);
  });

  it("empty library and steps []: both Save buttons stay disabled (the length === 0 term)", async () => {
    mockGetWorkflowDetail.mockResolvedValue(NO_OVERRIDE_DETAIL);
    renderWithProviders(
      <IdeaInputPage workflowType="user_stories" workflowId="user_stories" onBack={vi.fn()} onRun={vi.fn()} />,
      { preloadedState: preload([]) },
    );
    await waitFor(() => expect(button(/Advanced/)).toBeEnabled());
    expect(button(/Save workflow/)).toBeDisabled();
    expect(button(/Save as my version/)).toBeDisabled();
  });

  it("no workflowId: nothing to fetch, Save workflow and Advanced enabled", () => {
    renderWithProviders(<IdeaInputPage workflowType="user_stories" onBack={vi.fn()} onRun={vi.fn()} />, {
      preloadedState: preload(libraryAgents()),
    });
    expect(button(/Save workflow/)).toBeEnabled();
    expect(button(/Advanced/)).toBeEnabled();
    expect(mockGetWorkflowDetail).not.toHaveBeenCalled();
  });
});
