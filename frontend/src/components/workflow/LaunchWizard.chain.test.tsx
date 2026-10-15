/**
 * QA-KB-062 / ISS-347, ISS-1000, ISS-1002 - stale chain.* sessionStorage must not override a
 * caller-staged draft nor arm chaining / block Continue on an unrelated open.
 * Assert CORRECT behaviour; Fixed (FIX-723); was it.fails until the wizard fix landed.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderWithProviders, screen } from "@/test/renderWithProviders";
import userEvent from "@testing-library/user-event";
import { PROTO_AGENTS, PPT_AGENTS } from "@/components/workflow/__fixtures__/launchContract";
import type { AgentDef } from "@/types/index";

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
  getWorkflowDetail: vi.fn().mockResolvedValue({
    id: "ppt", steps: [], manifest_steps: null, has_override: false, is_overridden: false, override_id: null,
  }),
  setWorkflowOverrideEnabled: vi.fn().mockResolvedValue({}),
}));
vi.mock("@/lib/prototype-api", () => ({
  listPrototypeTemplates: vi.fn().mockResolvedValue([{ id: "kanban", name: "Kanban", example_prompt: "Example brief" }]),
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
vi.mock("@/components/workflow/WizardStepper", () => ({
  WizardStepper: (props: {
    mode: "web" | "deck";
    onModeChange: (m: "web" | "deck") => void;
    onWebSelect: (id: string | null) => void;
    onDeckSelect: (id: string) => void;
    steps?: string[];
    dsSlot?: React.ReactNode;
    discoverySlot?: React.ReactNode;
  }) => (
    <div data-testid="stepper" data-mode={props.mode}>
      <button data-testid="pick-web" onClick={() => props.onWebSelect("kanban")}>webpick</button>
      <button data-testid="pick-deck" onClick={() => props.onDeckSelect("pitch")}>deckpick</button>
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
  AgentsPopup: ({ pipelineType }: { pipelineType: string }) => <div data-testid="agents-pipeline">{pipelineType}</div>,
}));
vi.mock("@/components/catalog/NameWorkflowModal", () => ({
  NameWorkflowModal: () => <div data-testid="save-modal" />,
}));

import { LaunchWizard } from "@/components/workflow/LaunchWizard";

const agents = (): AgentDef[] => [
  ...PROTO_AGENTS.map((id, idx) => ({
    id, name: id, role: "Test Agent", description: "d", pipeline_type: "prototype", order: idx + 1,
    icon: "zap", estimated_duration: 60, has_skill: false,
  })),
  ...PPT_AGENTS.map((id, idx) => ({
    id, name: id, role: "Test Agent", description: "d", pipeline_type: "ppt", order: idx + 1,
    icon: "zap", estimated_duration: 60, has_skill: false,
  })),
] as AgentDef[];
const loadedAgents = () => ({
  agents: { agents: agents(), totalCount: agents().length, pipelines: {}, status: "succeeded" as const, error: null },
});

const CHAIN_KEYS = ["chain.from", "chain.brief", "chain.source_run_id", "chain.v2.source_status"] as const;

/** What a screen reader / user would perceive, plus the storage left behind. */
const observe = () => {
  const ta = screen.queryByLabelText("Brief") as HTMLTextAreaElement | null;
  return {
    briefEditorVisible: ta !== null,
    briefEditorValue: ta?.value ?? null,
    continuingBanner: screen.queryByText(/Continuing from your/i) !== null,
    ackCheckbox: screen.queryByLabelText(/I understand the output may be incomplete/i) !== null,
    continueDisabled: (screen.getByRole("button", { name: "Continue" }) as HTMLButtonElement).disabled,
    draftKeyStillStored: sessionStorage.getItem("prototype.draft") !== null,
    chainKeysLeft: CHAIN_KEYS.filter((k) => sessionStorage.getItem(k) !== null),
  };
};

/** Pick template + DS and press Continue; returns the draft the wizard hands to the dashboard. */
const launch = async (user: ReturnType<typeof userEvent.setup>) => {
  await user.click(screen.getByTestId("pick-web"));
  await user.click(await screen.findByTestId("pick-ds"));
  const btn = screen.getByRole("button", { name: "Continue" }) as HTMLButtonElement;
  if (btn.disabled) return { launched: false as const, draft: null };
  await user.click(btn);
  const raw = sessionStorage.getItem("prototype.draft");
  return { launched: true as const, draft: raw ? JSON.parse(raw) : null };
};

const staleTrio = () => {
  sessionStorage.setItem("chain.from", "user_stories");
  sessionStorage.setItem("chain.brief", "STALE chained brief");
  sessionStorage.setItem("chain.source_run_id", "stale-run-id");
};
// The exact shape DashboardLayout.handleEditBrief stages (DashboardLayout.tsx:2393).
const stageEditBriefDraft = () =>
  sessionStorage.setItem("prototype.draft", JSON.stringify({ brief: "EDITED brief (caller staged)" }));

beforeEach(() => {
  sessionStorage.clear();
  pushMock.mockClear();
});


describe("QA-KB-062 LaunchWizard ambient chain.* state", () => {
  // ISS-347
  it("ISS-347: stale chain trio + staged draft -> the staged draft wins and chain keys are cleared", async () => {
    staleTrio();
    stageEditBriefDraft();
    renderWithProviders(<LaunchWizard initialMode="prototype" />, { preloadedState: loadedAgents() });
    await screen.findByTestId("stepper");
    const o = observe();
    expect(o.briefEditorValue).toBe("EDITED brief (caller staged)");
    expect(o.continuingBanner).toBe(false);
    expect(o.draftKeyStillStored).toBe(false);
    expect(o.chainKeysLeft).toEqual([]);
  });

  // ISS-1000
  it("ISS-1000: stale chain.from + source_run_id + draft -> chaining not armed, no stale source id launched", async () => {
    sessionStorage.setItem("chain.from", "user_stories");
    sessionStorage.setItem("chain.source_run_id", "stale-run-id");
    stageEditBriefDraft();
    const user = userEvent.setup();
    renderWithProviders(<LaunchWizard initialMode="prototype" />, { preloadedState: loadedAgents() });
    await screen.findByTestId("stepper");
    expect(observe().briefEditorVisible).toBe(true);
    const l = await launch(user);
    expect(l.draft?.sourceRunId).toBeUndefined();
  });

  // ISS-1002
  it("ISS-1002: stale chain.v2.source_status alone must not leave Continue disabled with no acknowledgement checkbox", async () => {
    sessionStorage.setItem("chain.v2.source_status", "failed");
    const user = userEvent.setup();
    renderWithProviders(<LaunchWizard initialMode="prototype" />, { preloadedState: loadedAgents() });
    await user.type(await screen.findByLabelText("Brief"), "A perfectly normal brief");
    await user.click(screen.getByTestId("pick-web"));
    await user.click(await screen.findByTestId("pick-ds"));
    const o = observe();
    expect(o.continueDisabled && !o.ackCheckbox).toBe(false);
  });
});
