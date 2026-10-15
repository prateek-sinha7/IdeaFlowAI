import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderWithProviders, screen, waitFor } from "@/test/renderWithProviders";
import userEvent from "@testing-library/user-event";
import { PROTO_AGENTS } from "./__fixtures__/launchContract";
import type { AgentDef } from "@/types/index";

// QA-KB-011 / ISS-284 (+ sibling ISS-920) — the Save buttons (and Advanced) must
// not be live while getWorkflowDetail is still pending: handleSaveAsOverride
// would UPSERT the unsettled default roster over the real override. Written as
// it.fails: red today, flip to plain `it` once the fix lands.

const pushMock = vi.fn();
const createUserWorkflowMock = vi.fn().mockResolvedValue({ id: "wf-1" });
const saveUserWorkflowMock = vi.fn().mockResolvedValue({ id: "wf-1" });
const extractFileTextMock = vi.fn();
const stageRunFileMock = vi.fn();
// Held pending: the override/plan overlay never lands during these tests.
const getWorkflowDetailMock = vi.fn(() => new Promise(() => {}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock, replace: vi.fn(), prefetch: vi.fn() }),
}));
vi.mock("@/lib/api", () => ({
  getToken: () => "test-token",
  // ISS-321 — the wizard now reads the signed-in tier to gate an
  // unentitled launch. Entitled here, so every assertion below stays on
  // the un-gated path these tests were written for.
  getMe: vi.fn().mockResolvedValue({ id: "u1", email: "qa@flowinqa.com", tier: "enterprise" }),
  extractFileText: (...args: unknown[]) => extractFileTextMock(...args),
  stageRunFile: (...args: unknown[]) => stageRunFileMock(...args),
  createUserWorkflow: (...args: unknown[]) => createUserWorkflowMock(...args),
  saveUserWorkflow: (...args: unknown[]) => saveUserWorkflowMock(...args),
  // Spec 016 — the wizard asks whether THIS user has saved an override of the
  // built-in. Answering "no override" keeps every assertion in this file on the
  // un-overridden path, which is the point: they pin the existing behaviour as
  // unchanged for a user who has not opted in.
  getWorkflowDetail: (...args: unknown[]) => (getWorkflowDetailMock as (...a: unknown[]) => unknown)(...args),
  setWorkflowOverrideEnabled: vi.fn().mockResolvedValue({}),
}));
vi.mock("@/lib/prototype-api", () => ({
  listPrototypeTemplates: vi.fn().mockResolvedValue([
    { id: "kanban", name: "Kanban", example_prompt: "Example brief" },
  ]),
  listDesignSystems: vi.fn().mockResolvedValue([{ id: "midnight", name: "Midnight" }]),
}));
vi.mock("@/lib/ppt-api", () => ({
  listPPTTemplates: vi.fn().mockResolvedValue([
    { id: "pitch", name: "Pitch", design_system: { requires: true } },
    { id: "onepager", name: "One Pager", design_system: { requires: false } },
  ]),
}));
vi.mock("@/hooks/useSpeechRecognition", () => ({
  useSpeechRecognition: () => ({
    isListening: false, transcript: "", startListening: vi.fn(), stopListening: vi.fn(), isSupported: false,
  }),
}));

// Stub the stepper chrome: expose the render-slots + template/toggle callbacks.
vi.mock("@/components/workflow/WizardStepper", () => ({
  WizardStepper: (props: {
    mode: "web" | "deck";
    onModeChange: (m: "web" | "deck") => void;
    onWebSelect: (id: string | null) => void;
    onWebSelectCustomTemplate?: (ct: { id: string; name: string; body: string } | null) => void;
    onDeckSelect: (id: string) => void;
    onDeckSelectCustomTemplate?: (ct: { id: string; name: string; body: string } | null) => void;
    steps?: string[];
    dsSlot?: React.ReactNode;
    discoverySlot?: React.ReactNode;
  }) => (
    // data-steps exposes the `steps` prop the real stepper uses to decide which
    // tabs (and so which slots) it mounts; ds-slot is still always rendered here
    // so the older tests that pick a DS keep their shape.
    <div data-testid="stepper" data-mode={props.mode} data-steps={(props.steps ?? ["template", "design-system", "discovery"]).join(",")}>
      <button data-testid="toggle-web" onClick={() => props.onModeChange("web")}>web</button>
      <button data-testid="toggle-deck" onClick={() => props.onModeChange("deck")}>deck</button>
      <button data-testid="pick-web" onClick={() => props.onWebSelect("kanban")}>webpick</button>
      <button data-testid="pick-web-blank" onClick={() => props.onWebSelect(null)}>webblank</button>
      <button
        data-testid="pick-web-custom"
        onClick={() => props.onWebSelectCustomTemplate?.({ id: "ct1", name: "c", body: "<html>custom</html>" })}
      >webcustom</button>
      <button data-testid="pick-deck" onClick={() => props.onDeckSelect("pitch")}>deckpick</button>
      <button data-testid="pick-deck-onepager" onClick={() => props.onDeckSelect("onepager")}>deckone</button>
      <button
        data-testid="pick-deck-custom"
        onClick={() => props.onDeckSelectCustomTemplate?.({ id: "ct1", name: "c", body: "<html>custom</html>" })}
      >deckcustom</button>
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
vi.mock("@/components/workflow/ReviewGatesSection", () => ({
  ReviewGatesSection: ({ onChange }: { onChange: (ids: string[], touched: boolean) => void }) => (
    <button data-testid="gates-specify" onClick={() => onChange(["prototype-specify"], true)}>gates</button>
  ),
}));
vi.mock("@/components/workflow/AgentsPopup", () => ({
  AgentsPopup: ({ pipelineType }: { pipelineType: string }) => (
    <div data-testid="agents-pipeline">{pipelineType}</div>
  ),
}));
vi.mock("@/components/catalog/NameWorkflowModal", () => ({
  NameWorkflowModal: ({ title, onSave }: { title: string; onSave: (n: string, d: string) => void }) => (
    <div data-testid="save-modal">
      <p data-testid="save-modal-title">{title}</p>
      <button data-testid="confirm-save" onClick={() => onSave("My WF", "desc")}>save</button>
    </div>
  ),
}));

import { LaunchWizard } from "./LaunchWizard";

const agents = (): AgentDef[] =>
  PROTO_AGENTS.map((id, idx) => ({
    id, name: id, role: "Test Agent", description: "d", pipeline_type: "prototype",
    order: idx + 1, icon: "zap", estimated_duration: 60, has_skill: false,
  }));

const preload = (list: AgentDef[]) => ({
  agents: { agents: list, totalCount: list.length, pipelines: {}, status: "succeeded" as const, error: null },
});

beforeEach(() => {
  sessionStorage.clear();
  createUserWorkflowMock.mockClear();
  saveUserWorkflowMock.mockClear();
});

describe("LaunchWizard Save buttons during the override load window (QA-KB-011 / ISS-284)", () => {
  it("ISS-284: 'Save as my version' is disabled and fires no UPSERT while getWorkflowDetail is pending", async () => {
    const user = userEvent.setup();
    renderWithProviders(<LaunchWizard initialMode="prototype" />, { preloadedState: preload(agents()) });
    const btn = await screen.findByRole("button", { name: /Save as my version/ });
    await user.click(btn);
    expect(createUserWorkflowMock).not.toHaveBeenCalled();
    expect(btn).toBeDisabled();
  });

  it("ISS-284: 'Save workflow' is disabled while getWorkflowDetail is pending", async () => {
    renderWithProviders(<LaunchWizard initialMode="prototype" />, { preloadedState: preload(agents()) });
    expect(await screen.findByRole("button", { name: /Save workflow/ })).toBeDisabled();
  });

  it("ISS-284: the Advanced trigger is gated while getWorkflowDetail is pending", async () => {
    renderWithProviders(<LaunchWizard initialMode="prototype" />, { preloadedState: preload(agents()) });
    expect(await screen.findByRole("button", { name: /Advanced/ })).toBeDisabled();
  });
});

describe("LaunchWizard Continue while the draft agentIds restore waits (ISS-920)", () => {
  it("ISS-920: Continue stays disabled while the agent library is empty and a draft carries agentIds", async () => {
    sessionStorage.setItem("prototype.draft", JSON.stringify({
      templateId: "kanban", designSystemId: "midnight", brief: "Build a board", agentIds: [PROTO_AGENTS[0]],
    }));
    renderWithProviders(<LaunchWizard initialMode="prototype" />, { preloadedState: preload([]) });
    await waitFor(() => expect(screen.getByLabelText("Brief")).toHaveValue("Build a board"));
    expect(screen.getByRole("button", { name: "Continue" })).toBeDisabled();
  });
});
