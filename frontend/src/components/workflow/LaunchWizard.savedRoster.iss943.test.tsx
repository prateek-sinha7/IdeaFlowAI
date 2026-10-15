import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderWithProviders, screen, waitFor } from "@/test/renderWithProviders";
import { act } from "@testing-library/react";
import { combineReducers, configureStore } from "@reduxjs/toolkit";
import authReducer from "@/store/slices/authSlice";
import agentsReducer, { fetchAgentLibrary } from "@/store/slices/agentsSlice";
import skillsReducer from "@/store/slices/skillsSlice";
import hooksReducer from "@/store/slices/hooksSlice";
import globalReducer from "@/store/slices/globalSlice";
import userEvent from "@testing-library/user-event";
import { PROTO_AGENTS } from "./__fixtures__/launchContract";
import type { AgentDef } from "@/types/index";

// QA-KB-048 / ISS-943 + ISS-967 — a saved roster restored from the launch draft must
// survive to the launch draft Continue writes. Written as it.fails: red today, flip to
// plain `it` once the fix lands (vitest reports a passing it.fails as a failure).

const pushMock = vi.fn();
const createUserWorkflowMock = vi.fn().mockResolvedValue({ id: "wf-1" });
const saveUserWorkflowMock = vi.fn().mockResolvedValue({ id: "wf-1" });
const extractFileTextMock = vi.fn();
const stageRunFileMock = vi.fn();
// Held pending: the override/plan overlay never lands during these tests.
const getWorkflowDetailMock = vi.fn<(...a: unknown[]) => Promise<unknown>>(() => new Promise(() => {}));

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



const FULL_PLAN = {
  has_override: false, is_overridden: false, override_id: null,
  steps: PROTO_AGENTS.map((id, i) => ({ agent_id: id, name: id, role: "r", order: i + 1 })),
};
const NO_OVERRIDE = { has_override: false, is_overridden: false, override_id: null, steps: [] };
const draftOf = () => JSON.parse(sessionStorage.getItem("prototype.draft")!);
const seedDraft = (agentIds: string[]) =>
  sessionStorage.setItem("prototype.draft", JSON.stringify({
    templateId: "kanban", designSystemId: "midnight", brief: "Build a board", agentIds,
  }));

describe("QA-KB-048 saved roster survives plan completion / restore", () => {
  it("ISS-943 cold: library lands after the full plan -> Continue carries the saved roster", async () => {
    getWorkflowDetailMock.mockImplementation(() => Promise.resolve(FULL_PLAN));
    const store = configureStore({
      reducer: combineReducers({ auth: authReducer, agents: agentsReducer, skills: skillsReducer, hooks: hooksReducer, global: globalReducer }),
      preloadedState: preload([]),
    });
    seedDraft([PROTO_AGENTS[1]]);
    const user = userEvent.setup();
    renderWithProviders(<LaunchWizard initialMode="prototype" />, { store: store as never });
    await waitFor(() => expect(screen.getByLabelText("Brief")).toHaveValue("Build a board"));
    await act(async () => { await Promise.resolve(); });
    act(() => { store.dispatch(fetchAgentLibrary.fulfilled({ agents: agents(), total_count: agents().length, pipelines: {} } as never, "req")); });
    const cont = screen.getByRole("button", { name: "Continue" });
    await waitFor(() => expect(cont).toBeEnabled());
    await user.click(cont);
    expect(draftOf().agentIds).toEqual([PROTO_AGENTS[1]]);
  });

  it("ISS-943 warm: library preloaded, full plan lands after restore -> Continue carries the saved roster", async () => {
    getWorkflowDetailMock.mockImplementation(() => Promise.resolve(FULL_PLAN));
    seedDraft([PROTO_AGENTS[1]]);
    const user = userEvent.setup();
    renderWithProviders(<LaunchWizard initialMode="prototype" />, { preloadedState: preload(agents()) });
    await waitFor(() => expect(screen.getByLabelText("Brief")).toHaveValue("Build a board"));
    const cont = screen.getByRole("button", { name: "Continue" });
    await waitFor(() => expect(cont).toBeEnabled());
    await act(async () => { await Promise.resolve(); });
    await user.click(cont);
    expect(draftOf().agentIds).toEqual([PROTO_AGENTS[1]]);
  });

  it("ISS-967 a saved custom-pool agent is not dropped by the draft restore", async () => {
    getWorkflowDetailMock.mockImplementation(() => Promise.resolve(NO_OVERRIDE));
    const custom: AgentDef = {
      id: "custom-util-x", name: "Util X", role: "Util", description: "d", pipeline_type: "custom",
      order: 99, icon: "zap", estimated_duration: 60, has_skill: false,
    };
    seedDraft([PROTO_AGENTS[0], PROTO_AGENTS[1], "custom-util-x"]);
    const user = userEvent.setup();
    renderWithProviders(<LaunchWizard initialMode="prototype" />, { preloadedState: preload([...agents(), custom]) });
    await waitFor(() => expect(screen.getByLabelText("Brief")).toHaveValue("Build a board"));
    const cont = screen.getByRole("button", { name: "Continue" });
    await waitFor(() => expect(cont).toBeEnabled());
    await act(async () => { await Promise.resolve(); });
    await user.click(cont);
    expect(draftOf().agentIds).toEqual([PROTO_AGENTS[0], PROTO_AGENTS[1], "custom-util-x"]);
  });
});
