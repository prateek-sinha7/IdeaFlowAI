/**
 * QA-KB-062 / ISS-347 — analysis proof (throwaway, NOT a regression test).
 *
 * Mounts the REAL <LaunchWizard> (mocks copied verbatim from
 * frontend/src/components/workflow/LaunchWizard.test.tsx) with the sessionStorage state an
 * abandoned chain push leaves behind, and prints what the wizard actually does with it.
 * Assertions state the DESIRED behaviour (expect.soft, so every one is evaluated), therefore
 * they are RED at HEAD — the failure text is the evidence. Each case also console.logs the
 * observed state as one JSON line prefixed "OBSERVED".
 *
 * Mapping to the cards:
 *   R0  control          — draft only, no chain keys: the wizard behaves (this must pass)
 *   R1  ISS-347 (root)   — stale chain trio + caller-staged draft (handleEditBrief shape)
 *   R2  sibling A        — stale chain.from + chain.source_run_id + draft, NO chain.brief
 *   R3  sibling C        — stale chain.v2.source_status alone (WorkflowHistory, non-wizard target)
 *   R4  sibling B        — stale chain trio, NO draft (fresh Home open): characterisation only
 *   R5  cold mount       — stale chain.brief + draft, agent library arrives AFTER the first run
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderWithProviders, screen, waitFor } from "@/test/renderWithProviders";
import userEvent from "@testing-library/user-event";
import { act } from "@testing-library/react";
import { configureStore, combineReducers } from "@reduxjs/toolkit";
import authReducer from "@/store/slices/authSlice";
import agentsReducer from "@/store/slices/agentsSlice";
import skillsReducer from "@/store/slices/skillsSlice";
import hooksReducer from "@/store/slices/hooksSlice";
import globalReducer from "@/store/slices/globalSlice";
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

describe("QA-KB-062 analysis proof — LaunchWizard ambient chain.* state", () => {
  it("R0 control: draft only, no chain keys -> draft applied, one-shot cleared", async () => {
    stageEditBriefDraft();
    renderWithProviders(<LaunchWizard initialMode="prototype" />, { preloadedState: loadedAgents() });
    await screen.findByTestId("stepper");
    const o = observe();
    console.log("OBSERVED R0 " + JSON.stringify(o));
    expect(o.briefEditorVisible).toBe(true);
    expect(o.briefEditorValue).toBe("EDITED brief (caller staged)");
    expect(o.continuingBanner).toBe(false);
    expect(o.draftKeyStillStored).toBe(false);
  });

  it("R1 ISS-347 root: stale chain trio + caller-staged draft -> the draft must win (desired; RED at HEAD)", async () => {
    staleTrio();
    stageEditBriefDraft();
    const user = userEvent.setup();
    renderWithProviders(<LaunchWizard initialMode="prototype" />, { preloadedState: loadedAgents() });
    await screen.findByTestId("stepper");
    const o = observe();
    const l = await launch(user);
    console.log("OBSERVED R1 " + JSON.stringify({ ...o, launch: l }));
    expect.soft(o.briefEditorVisible, "brief editor visible (caller wants the user to edit the brief)").toBe(true);
    expect.soft(o.briefEditorValue, "editor holds the caller-staged brief").toBe("EDITED brief (caller staged)");
    expect.soft(o.continuingBanner, "no 'Continuing from your ...' banner for a non-chain open").toBe(false);
    expect.soft(o.draftKeyStillStored, "FIX-005 one-shot: the staged draft is consumed").toBe(false);
    expect.soft(o.chainKeysLeft, "stale chain.* keys are dropped").toEqual([]);
    expect.soft(l.draft?.brief, "the launched brief is the staged one").toBe("EDITED brief (caller staged)");
    expect.soft(l.draft?.sourceRunId, "no stale source_workflow_run_id rides into the run").toBeUndefined();
  });

  it("R2 sibling A: stale chain.from + chain.source_run_id + draft, NO chain.brief -> must not arm 'chaining' (desired; RED at HEAD)", async () => {
    sessionStorage.setItem("chain.from", "user_stories");
    sessionStorage.setItem("chain.source_run_id", "stale-run-id");
    stageEditBriefDraft();
    const user = userEvent.setup();
    renderWithProviders(<LaunchWizard initialMode="prototype" />, { preloadedState: loadedAgents() });
    await screen.findByTestId("stepper");
    const o = observe();
    const l = await launch(user);
    console.log("OBSERVED R2 " + JSON.stringify({ ...o, launch: l }));
    expect.soft(o.briefEditorVisible, "isChaining hides the brief editor").toBe(true);
    expect.soft(o.continuingBanner).toBe(false);
    expect.soft(l.draft?.sourceRunId, "stale source id must not become source_workflow_run_id").toBeUndefined();
  });

  it("R3 sibling C: stale chain.v2.source_status alone -> Continue must not be blocked with no way to acknowledge (desired; RED at HEAD)", async () => {
    sessionStorage.setItem("chain.v2.source_status", "failed");
    const user = userEvent.setup();
    renderWithProviders(<LaunchWizard initialMode="prototype" />, { preloadedState: loadedAgents() });
    await user.type(await screen.findByLabelText("Brief"), "A perfectly normal brief");
    await user.click(screen.getByTestId("pick-web"));
    await user.click(await screen.findByTestId("pick-ds"));
    const o = observe();
    console.log("OBSERVED R3 " + JSON.stringify(o));
    const blockedWithNoRemedy = o.continueDisabled && !o.ackCheckbox;
    expect.soft(blockedWithNoRemedy, "Continue disabled AND no acknowledgement checkbox rendered").toBe(false);
  });

  it("R3 control: the SAME clicks without chain.v2.source_status -> Continue is enabled (isolates the key as the cause)", async () => {
    const user = userEvent.setup();
    renderWithProviders(<LaunchWizard initialMode="prototype" />, { preloadedState: loadedAgents() });
    await user.type(await screen.findByLabelText("Brief"), "A perfectly normal brief");
    await user.click(screen.getByTestId("pick-web"));
    await user.click(await screen.findByTestId("pick-ds"));
    const o = observe();
    console.log("OBSERVED R3-control " + JSON.stringify(o));
    expect(o.continueDisabled).toBe(false);
  });

  it("R4 sibling B (characterisation): stale chain trio, NO draft (fresh open) -> what a fresh open shows today", async () => {
    staleTrio();
    renderWithProviders(<LaunchWizard initialMode="prototype" />, { preloadedState: loadedAgents() });
    await screen.findByTestId("stepper");
    const o = observe();
    console.log("OBSERVED R4 " + JSON.stringify(o));
    // No desired-behaviour assertion: what a fresh open SHOULD show depends on the scoping design
    // (ISS sibling B). Recorded so the card quotes an executed observation, not a reading.
    expect(o).toBeTruthy();
  });

  it("R6 control: a GENUINE chain (trio, no draft) still launches with the chain brief and threads the source id (must stay green after any fix)", async () => {
    sessionStorage.setItem("chain.from", "user_stories");
    sessionStorage.setItem("chain.brief", "chained brief");
    sessionStorage.setItem("chain.source_run_id", "run-42");
    const user = userEvent.setup();
    renderWithProviders(<LaunchWizard initialMode="prototype" />, { preloadedState: loadedAgents() });
    await screen.findByTestId("stepper");
    const l = await launch(user);
    console.log("OBSERVED R6 " + JSON.stringify(l));
    expect(l.draft?.brief).toBe("chained brief");
    expect(l.draft?.sourceRunId).toBe("run-42");
    expect(sessionStorage.getItem("chain.source_run_id")).toBeNull();
  });

  it("R5 cold mount: stale chain.brief + draft, agent library arrives after the first run of the restore effect", async () => {
    sessionStorage.setItem("chain.from", "user_stories");
    sessionStorage.setItem("chain.brief", "STALE chained brief");
    stageEditBriefDraft();
    const user = userEvent.setup();
    const store = configureStore({
      reducer: combineReducers({
        auth: authReducer, agents: agentsReducer, skills: skillsReducer, hooks: hooksReducer, global: globalReducer,
      }),
    });
    // @ts-expect-error store type is narrower than the real one; fine at runtime
    renderWithProviders(<LaunchWizard initialMode="prototype" />, { store });
    await screen.findByTestId("stepper");
    const before = { draftKeyStillStored: sessionStorage.getItem("prototype.draft") !== null, chainBriefLeft: sessionStorage.getItem("chain.brief") !== null };
    // The library fetch finishes: `libraryAgents` changes identity -> the restore effect re-runs (LaunchWizard.tsx:450 deps).
    await act(async () => {
      store.dispatch({ type: "agents/fetchLibrary/fulfilled", payload: { agents: agents(), total_count: agents().length, pipelines: {} } });
    });
    await waitFor(() => expect(sessionStorage.getItem("prototype.draft")).toBeNull());
    const o = observe();
    const l = await launch(user);
    console.log("OBSERVED R5 " + JSON.stringify({ before, after: o, launch: l }));
    expect(l.draft).toBeTruthy();
  });
});
