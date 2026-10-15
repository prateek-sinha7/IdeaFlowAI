import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderWithProviders, screen, waitFor } from "@/test/renderWithProviders";
import userEvent from "@testing-library/user-event";
import { PROTO_AGENTS } from "./__fixtures__/launchContract";
import type { AgentDef } from "@/types/index";

// QA-KB-058 / ISS-917 (+ sibling ISS-982) — the wizard's exits ask before
// discarding unsaved input, and only when the USER changed something: the async
// seeds (override overlay, FIX-103 apple auto-select) must not read as edits.
// jsdom's history.length is 1, so goBackOr takes its fallback push.

const pushMock = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock, replace: vi.fn(), prefetch: vi.fn() }),
}));
vi.mock("@/lib/api", () => ({
  getToken: () => "test-token",
  getMe: vi.fn().mockResolvedValue({ id: "u1", email: "qa@flowinqa.com", tier: "enterprise" }),
  extractFileText: vi.fn(),
  stageRunFile: vi.fn(),
  createUserWorkflow: vi.fn().mockResolvedValue({ id: "wf-1" }),
  saveUserWorkflow: vi.fn().mockResolvedValue({ id: "wf-1" }),
  // An enabled override, so the roster is rewritten after mount with no user action.
  getWorkflowDetail: () => Promise.resolve({
    has_override: true, is_overridden: true, override_id: "ov-1",
    steps: [{ agent_id: PROTO_AGENTS[0], name: "a", role: "r", order: 1 }],
  }),
  setWorkflowOverrideEnabled: vi.fn().mockResolvedValue({}),
}));
vi.mock("@/lib/prototype-api", () => ({
  listPrototypeTemplates: vi.fn().mockResolvedValue([{ id: "kanban", name: "Kanban" }]),
  // "apple" present, so FIX-103 auto-selects it once the registry lands.
  listDesignSystems: vi.fn().mockResolvedValue([{ id: "apple", name: "Apple" }, { id: "midnight", name: "Midnight" }]),
}));
vi.mock("@/lib/ppt-api", () => ({ listPPTTemplates: vi.fn().mockResolvedValue([]) }));
vi.mock("@/hooks/useSpeechRecognition", () => ({
  useSpeechRecognition: () => ({
    isListening: false, transcript: "", startListening: vi.fn(), stopListening: vi.fn(), isSupported: false,
  }),
}));
vi.mock("@/components/workflow/WizardStepper", () => ({
  WizardStepper: (props: { dsSlot?: React.ReactNode }) => <div>{props.dsSlot}</div>,
}));
vi.mock("@/components/workflow/prototype/DesignSystemPicker", () => ({
  DesignSystemPicker: ({ selectedId, onSelect }: { selectedId: string | null; onSelect: (id: string) => void }) => (
    <button data-testid="pick-ds" data-selected={selectedId ?? ""} onClick={() => onSelect("midnight")}>ds</button>
  ),
}));
vi.mock("@/components/workflow/ReviewGatesSection", () => ({ ReviewGatesSection: () => null }));
vi.mock("@/components/workflow/AgentsPopup", () => ({
  AgentsPopup: ({ agents, onOpenInCanvas }: { agents: AgentDef[]; onOpenInCanvas?: () => void }) => (
    <button data-testid="open-canvas" data-roster={agents.map((a) => a.id).join(",")} onClick={onOpenInCanvas}>canvas</button>
  ),
}));
vi.mock("@/components/catalog/NameWorkflowModal", () => ({ NameWorkflowModal: () => null }));

import { LaunchWizard } from "./LaunchWizard";

const library: AgentDef[] = PROTO_AGENTS.map((id, idx) => ({
  id, name: id, role: "Test Agent", description: "d", pipeline_type: "prototype",
  order: idx + 1, icon: "zap", estimated_duration: 60, has_skill: false,
}));

/** Render and wait until every async seed has landed. */
async function openSettled() {
  const user = userEvent.setup();
  renderWithProviders(<LaunchWizard initialMode="prototype" />, {
    preloadedState: { agents: { agents: library, totalCount: library.length, pipelines: {}, status: "succeeded" as const, error: null } },
  });
  await waitFor(() => expect(screen.getByTestId("pick-ds")).toHaveAttribute("data-selected", "apple"));
  await waitFor(() => expect(screen.getByTestId("open-canvas")).toHaveAttribute("data-roster", PROTO_AGENTS[0]));
  return user;
}

const leaveDialog = () => screen.queryByRole("dialog", { name: "Leave without saving?" });
const back = () => screen.getByRole("button", { name: "Back to dashboard" });

beforeEach(() => {
  sessionStorage.clear();
  pushMock.mockClear();
});

describe("LaunchWizard exits guard unsaved input (QA-KB-058 / ISS-917, ISS-982)", () => {
  it("an untouched wizard leaves on Back with no dialog, after the override overlay and apple auto-select", async () => {
    const user = await openSettled();
    await user.click(back());
    expect(leaveDialog()).toBeNull();
    expect(pushMock).toHaveBeenCalledWith("/dashboard");
  });

  it("a typed brief holds Back in the dialog: Stay keeps the text, Leave anyway navigates once", async () => {
    const confirmSpy = vi.spyOn(window, "confirm");
    const user = await openSettled();
    await user.type(screen.getByLabelText("Brief"), "A kanban board");
    await user.click(back());
    expect(leaveDialog()).not.toBeNull();
    expect(pushMock).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Stay" }));
    expect(leaveDialog()).toBeNull();
    expect(screen.getByLabelText("Brief")).toHaveValue("A kanban board");
    expect(pushMock).not.toHaveBeenCalled();

    await user.click(back());
    await user.click(screen.getByRole("button", { name: "Leave anyway" }));
    expect(pushMock).toHaveBeenCalledTimes(1);
    expect(pushMock).toHaveBeenCalledWith("/dashboard");
    expect(confirmSpy).not.toHaveBeenCalled();
  });

  it("a design-system pick alone, nothing typed, prompts on Back", async () => {
    const user = await openSettled();
    await user.click(screen.getByTestId("pick-ds"));
    await user.click(back());
    expect(leaveDialog()).not.toBeNull();
    expect(pushMock).not.toHaveBeenCalled();
  });

  it("ISS-982: Open in full canvas goes through the same guard", async () => {
    const user = await openSettled();
    await user.type(screen.getByLabelText("Brief"), "A kanban board");
    await user.click(screen.getByTestId("open-canvas"));
    expect(leaveDialog()).not.toBeNull();
    expect(pushMock).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Leave anyway" }));
    expect(pushMock).toHaveBeenCalledWith("/workflows/prototype/canvas");
  });

  it("Continue with a typed brief never prompts", async () => {
    const user = await openSettled();
    await user.type(screen.getByLabelText("Brief"), "A kanban board");
    await user.click(screen.getByRole("button", { name: "Continue" }));
    expect(leaveDialog()).toBeNull();
    expect(pushMock).toHaveBeenCalledWith("/dashboard");
  });
});
