import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderWithProviders, screen, waitFor } from "@/test/renderWithProviders";
import { PROTO_AGENTS } from "./__fixtures__/launchContract";
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
import { listDesignSystems } from "@/lib/prototype-api";

// QA-KB-081 / ISS-909 — a failed or empty design-system registry fetch must show an
// explicit message with a Retry, never a permanent animate-pulse skeleton.

const library: AgentDef[] = PROTO_AGENTS.map((id, idx) => ({
  id, name: id, role: "Test Agent", description: "d", pipeline_type: "prototype",
  order: idx + 1, icon: "zap", estimated_duration: 60, has_skill: false,
}));

function open() {
  renderWithProviders(<LaunchWizard initialMode="prototype" />, {
    preloadedState: { agents: { agents: library, totalCount: library.length, pipelines: {}, status: "succeeded" as const, error: null } },
  });
}
const skeleton = () => document.querySelector(".animate-pulse");

beforeEach(() => {
  sessionStorage.clear();
  pushMock.mockClear();
});

describe("LaunchWizard DS step on a bad registry (QA-KB-081 / ISS-909)", () => {
  it("ISS-909: a rejected registry fetch shows an error with Retry, not a skeleton", async () => {
    vi.mocked(listDesignSystems).mockRejectedValue(new Error("500"));
    open();
    await waitFor(() => expect(listDesignSystems).toHaveBeenCalled());
    expect(await screen.findByRole("button", { name: /retry/i }, { timeout: 1500 })).toBeInTheDocument();
    expect(skeleton()).toBeNull();
  });

  it("ISS-909: an empty registry shows an empty message with Retry, not a skeleton", async () => {
    vi.mocked(listDesignSystems).mockResolvedValue([]);
    open();
    await waitFor(() => expect(listDesignSystems).toHaveBeenCalled());
    expect(await screen.findByRole("button", { name: /retry/i }, { timeout: 1500 })).toBeInTheDocument();
    expect(skeleton()).toBeNull();
  });
});
