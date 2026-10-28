/**
 * LaunchWizard (plan 37-07) — the unified prototype+ppt launch page.
 *
 * Proves (1) the REAL component's launch hand-off is byte-identical to the
 * frozen golden fixtures per mode (a component-level parity proof on top of the
 * lib-level launchDraft.parity gate), and (2) the ported behaviors: brief,
 * blank-canvas, example-prompt, review gates, out-of-band images, save-workflow,
 * draft restore, discovery, and the Web/Deck deliverable-mode toggle (SC-001).
 *
 * The WizardStepper chrome is stubbed to expose its render-slots + selection
 * callbacks directly (the stepper's own chrome/a11y is covered by
 * WizardStepper.test.tsx); the heavy pickers are stubbed at the module boundary.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderWithProviders, screen, waitFor } from "@/test/renderWithProviders";
import userEvent from "@testing-library/user-event";
import { act } from "@testing-library/react";
import { DRAFT_SCENARIOS, PROTO_AGENTS, PPT_AGENTS } from "./__fixtures__/launchContract";
import { buildLaunchDraft } from "@/lib/launchDraft";
import type { AgentDef } from "@/types/index";

const pushMock = vi.fn();
const createUserWorkflowMock = vi.fn().mockResolvedValue({ id: "wf-1" });
// AgentsPopup (rendered by LaunchWizard, always mounted) imports saveUserWorkflow
// from the same mocked module for its own footer save button — stubbed here so
// it doesn't resolve to undefined if a test ever exercises that button.
const saveUserWorkflowMock = vi.fn().mockResolvedValue({ id: "wf-1" });
const extractFileTextMock = vi.fn();
const stageRunFileMock = vi.fn();

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
  getWorkflowDetail: vi.fn().mockResolvedValue({
    id: "ppt",
    steps: [],
    manifest_steps: null,
    has_override: false,
    is_overridden: false,
    override_id: null,
  }),
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

/**
 * The golden draft as the WIZARD writes it today.
 *
 * FIX-323 made the wizard always send `gate_agent_ids` (`touched: true` from
 * mount), so an empty selection reaches the backend as an explicit "no gates"
 * instead of an absent field it would fill from its own defaults. The frozen
 * fixtures in `launchContract.ts` model the RETIRED route-split flow, where the
 * field was omitted while untouched — they are the oracle
 * `launchDraft.parity.test.ts` pins `buildLaunchDraft` against byte-for-byte, so
 * they must NOT be edited to chase the component.
 *
 * Instead, re-serialize the scenario's own inputs through that same
 * independently-pinned builder with the one field FIX-323 adds. The chain stays
 * honest: builder ≡ frozen oracle (parity suite), component ≡ builder + FIX-323
 * (here).
 */
const goldenAsWizardWrites = (name: string) => {
  const s = DRAFT_SCENARIOS.find((x) => x.name === name);
  if (!s) throw new Error(`missing scenario ${name}`);
  // Mirror the LaunchWizard's sourceType logic: customTemplateBody → "html", else → "catalog".
  // Figma frames are not exercised in these tests so "figma" is never reached here.
  const sourceType: "catalog" | "html" = s.inputs.customTemplateBody ? "html" : "catalog";
  return buildLaunchDraft(s.mode, { ...s.inputs, gatesTouched: true, gateAgentIds: [], sourceType }).draftJson;
};

// Create test agents matching the expected library
const createTestAgents = (): AgentDef[] => {
  const protoAgents: AgentDef[] = PROTO_AGENTS.map((id, idx) => ({
    id,
    name: id,
    role: "Test Agent",
    description: "Test description",
    pipeline_type: "prototype",
    order: idx + 1,
    icon: "zap",
    estimated_duration: 60,
    has_skill: false,
  }));
  const pptAgents: AgentDef[] = PPT_AGENTS.map((id, idx) => ({
    id,
    name: id,
    role: "Test Agent",
    description: "Test description",
    pipeline_type: "ppt",
    order: idx + 1,
    icon: "zap",
    estimated_duration: 60,
    has_skill: false,
  }));
  return [...protoAgents, ...pptAgents];
};

beforeEach(() => {
  sessionStorage.clear();
  pushMock.mockClear();
  createUserWorkflowMock.mockClear();
  saveUserWorkflowMock.mockClear();
  extractFileTextMock.mockReset();
  stageRunFileMock.mockReset();
});

describe("LaunchWizard — real-component launch parity (byte-identical per mode)", () => {
  it("prototype base launch writes the golden draft + pending and routes to /dashboard", async () => {
    const user = userEvent.setup();
    renderWithProviders(<LaunchWizard initialMode="prototype" />, {
      preloadedState: { agents: { agents: createTestAgents(), totalCount: createTestAgents().length, pipelines: {}, status: "succeeded" as const, error: null } },
    });
    await user.type(await screen.findByLabelText("Brief"), "Build a kanban board");
    await user.click(screen.getByTestId("pick-web"));
    await user.click(await screen.findByTestId("pick-ds"));
    await user.click(screen.getByRole("button", { name: "Continue" }));

    expect(sessionStorage.getItem("prototype.draft")).toBe(
      goldenAsWizardWrites("prototype · base (template + ds + brief)"),
    );
    expect(sessionStorage.getItem("prototype.pending")).toBe("true");
    expect(pushMock).toHaveBeenCalledWith("/dashboard");
  });

  it("prototype blank-canvas launch writes templateId:null", async () => {
    const user = userEvent.setup();
    renderWithProviders(<LaunchWizard initialMode="prototype" />, {
      preloadedState: { agents: { agents: createTestAgents(), totalCount: createTestAgents().length, pipelines: {}, status: "succeeded" as const, error: null } },
    });
    await user.type(await screen.findByLabelText("Brief"), "Build a kanban board");
    await user.click(screen.getByTestId("pick-web-blank"));
    await user.click(await screen.findByTestId("pick-ds"));
    await user.click(screen.getByRole("button", { name: "Continue" }));

    expect(sessionStorage.getItem("prototype.draft")).toBe(
      goldenAsWizardWrites("prototype · blank canvas (no template)"),
    );
  });

  it("ppt base launch writes the golden draft + pending", async () => {
    const user = userEvent.setup();
    renderWithProviders(<LaunchWizard initialMode="ppt" />, {
      preloadedState: { agents: { agents: createTestAgents(), totalCount: createTestAgents().length, pipelines: {}, status: "succeeded" as const, error: null } },
    });
    await user.type(await screen.findByLabelText("Brief"), "Pitch deck");
    await user.click(screen.getByTestId("pick-deck")); // pitch → dsRequired
    await user.click(await screen.findByTestId("pick-ds"));
    await user.click(screen.getByRole("button", { name: "Continue" }));

    const gJson = goldenAsWizardWrites("ppt · base (ds required)");
    expect(sessionStorage.getItem("ppt.draft")).toBe(gJson);
    expect(sessionStorage.getItem("ppt.pending")).toBe("true");
  });

  it("ppt template not requiring a design system writes designSystemId:null", async () => {
    const user = userEvent.setup();
    renderWithProviders(<LaunchWizard initialMode="ppt" />, {
      preloadedState: { agents: { agents: createTestAgents(), totalCount: createTestAgents().length, pipelines: {}, status: "succeeded" as const, error: null } },
    });
    await user.type(await screen.findByLabelText("Brief"), "Pitch deck");
    await user.click(screen.getByTestId("pick-deck-onepager"));
    await user.click(screen.getByRole("button", { name: "Continue" }));

    expect(sessionStorage.getItem("ppt.draft")).toBe(
      goldenAsWizardWrites("ppt · ds not required (designSystemId null)"),
    );
  });

  it("WR-06: ppt custom template launches customTemplateBody with designSystemId:null (no DS required)", async () => {
    const user = userEvent.setup();
    renderWithProviders(<LaunchWizard initialMode="ppt" />, {
      preloadedState: { agents: { agents: createTestAgents(), totalCount: createTestAgents().length, pipelines: {}, status: "succeeded" as const, error: null } },
    });
    await user.type(await screen.findByLabelText("Brief"), "Custom deck");
    // A deck custom template has no registry entry → dsRequired=false → the
    // launch must succeed WITHOUT a design-system pick and emit designSystemId:null.
    await user.click(screen.getByTestId("pick-deck-custom"));
    await user.click(screen.getByRole("button", { name: "Continue" }));

    const gJson = goldenAsWizardWrites("ppt · custom template (customTemplateBody + designSystemId null)");
    expect(sessionStorage.getItem("ppt.draft")).toBe(gJson);
    expect(sessionStorage.getItem("ppt.pending")).toBe("true");
  });
});

describe("LaunchWizard — SC-001 Web/Deck deliverable-mode toggle", () => {
  it("toggling to Deck switches the agent pipeline + launch target to ppt", async () => {
    const user = userEvent.setup();
    renderWithProviders(<LaunchWizard initialMode="prototype" />, {
      preloadedState: { agents: { agents: createTestAgents(), totalCount: createTestAgents().length, pipelines: {}, status: "succeeded" as const, error: null } },
    });
    expect(await screen.findByTestId("agents-pipeline")).toHaveTextContent("prototype");

    await user.click(screen.getByTestId("toggle-deck"));
    expect(screen.getByTestId("agents-pipeline")).toHaveTextContent("ppt");

    await user.type(screen.getByLabelText("Brief"), "Pitch deck");
    await user.click(screen.getByTestId("pick-deck"));
    await user.click(await screen.findByTestId("pick-ds"));
    await user.click(screen.getByRole("button", { name: "Continue" }));

    // Launch wrote the ppt contract, not prototype.
    expect(sessionStorage.getItem("ppt.draft")).toBe(goldenAsWizardWrites("ppt · base (ds required)"));
    expect(sessionStorage.getItem("ppt.pending")).toBe("true");
    expect(sessionStorage.getItem("prototype.draft")).toBeNull();
  });

  it("WR-05: page chrome (header title + brief label + save-modal title) follows the LIVE mode after toggle", async () => {
    const user = userEvent.setup();
    // ISS-284: Save workflow is disabled on an empty roster, so this needs a library.
    renderWithProviders(<LaunchWizard initialMode="prototype" />, {
      preloadedState: { agents: { agents: createTestAgents(), totalCount: createTestAgents().length, pipelines: {}, status: "succeeded" as const, error: null } },
    });
    // Prototype chrome initially.
    expect(await screen.findByRole("heading", { name: "Configure your prototype" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Describe what you're building" })).toBeInTheDocument();

    await user.click(screen.getByTestId("toggle-deck"));
    // Chrome must flip to the ppt copy — before the fix `cfg` was frozen to the
    // immutable initialMode, so the page read "prototype" while building a deck.
    expect(screen.getByRole("heading", { name: "Configure your presentation" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Describe your presentation" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Configure your prototype" })).not.toBeInTheDocument();

    // The save-modal title tracks the live mode too (persisted-artifact honesty).
    await user.click(screen.getByRole("button", { name: "Save workflow" }));
    expect(screen.getByTestId("save-modal-title")).toHaveTextContent("Save presentation workflow");
  });
});

describe("LaunchWizard — ported behaviors", () => {
  it("review gates: touching gates threads gateAgentIds into the draft", async () => {
    const user = userEvent.setup();
    renderWithProviders(<LaunchWizard initialMode="prototype" />);
    await user.type(await screen.findByLabelText("Brief"), "Gated brief");
    await user.click(screen.getByTestId("pick-web"));
    await user.click(await screen.findByTestId("pick-ds"));
    await user.click(screen.getByTestId("gates-specify"));
    await user.click(screen.getByRole("button", { name: "Continue" }));

    const draft = JSON.parse(sessionStorage.getItem("prototype.draft")!);
    expect(draft.gateAgentIds).toEqual(["prototype-specify"]);
  });

  it("discovery: filling a discovery answer writes prototype.discovery; empty clears it", async () => {
    const user = userEvent.setup();
    renderWithProviders(<LaunchWizard initialMode="prototype" />);
    await user.type(await screen.findByLabelText("Brief"), "Discovery brief");
    await user.click(screen.getByTestId("pick-web"));
    await user.click(await screen.findByTestId("pick-ds"));
    // The discovery slot renders the real DiscoveryForm — pick a Surface radio.
    await user.click(screen.getByRole("button", { name: "Desktop web" }));
    await user.click(screen.getByRole("button", { name: "Continue" }));

    const discovery = JSON.parse(sessionStorage.getItem("prototype.discovery")!);
    expect(discovery.surface).toBe("Desktop web");
  });

  it("discovery: no answers → no prototype.discovery key written", async () => {
    const user = userEvent.setup();
    renderWithProviders(<LaunchWizard initialMode="prototype" />);
    await user.type(await screen.findByLabelText("Brief"), "No discovery");
    await user.click(screen.getByTestId("pick-web"));
    await user.click(await screen.findByTestId("pick-ds"));
    await user.click(screen.getByRole("button", { name: "Continue" }));

    expect(sessionStorage.getItem("prototype.discovery")).toBeNull();
  });

  it("example-prompt: clicking 'Use template example' fills the brief", async () => {
    const user = userEvent.setup();
    renderWithProviders(<LaunchWizard initialMode="prototype" />);
    await screen.findByLabelText("Brief");
    await user.click(screen.getByTestId("pick-web")); // selects kanban (has example_prompt)
    await user.click(await screen.findByRole("button", { name: /use template example/i }));
    expect((screen.getByLabelText("Brief") as HTMLTextAreaElement).value).toBe("Example brief");
  });

  it("save-workflow: composes base_pipeline_type + _wizard config", async () => {
    const user = userEvent.setup();
    renderWithProviders(<LaunchWizard initialMode="prototype" />, {
      preloadedState: { agents: { agents: createTestAgents(), totalCount: createTestAgents().length, pipelines: {}, status: "succeeded" as const, error: null } },
    });
    await user.type(await screen.findByLabelText("Brief"), "Savable");
    await user.click(screen.getByTestId("pick-web"));
    await user.click(await screen.findByTestId("pick-ds"));
    await user.click(screen.getByRole("button", { name: "Save workflow" }));
    await user.click(await screen.findByTestId("confirm-save"));

    await waitFor(() => expect(createUserWorkflowMock).toHaveBeenCalledTimes(1));
    const [, body] = createUserWorkflowMock.mock.calls[0];
    expect(body.base_pipeline_type).toBe("prototype");
    expect(body.selections._wizard.brief).toBe("Savable");
    expect(body.selections._wizard.templateId).toBe("kanban");
  });

  it("draft restore: hydrates the brief from a mode draft then one-shot clears it", async () => {
    sessionStorage.setItem(
      "prototype.draft",
      JSON.stringify({ templateId: "kanban", designSystemId: "midnight", brief: "restored", agentIds: [] }),
    );
    renderWithProviders(<LaunchWizard initialMode="prototype" />);
    const briefField = (await screen.findByLabelText("Brief")) as HTMLTextAreaElement;
    await waitFor(() => expect(briefField.value).toBe("restored"));
    // FIX-005: the one-shot draft is cleared after hydration.
    expect(sessionStorage.getItem("prototype.draft")).toBeNull();
  });

  it("IN-04: a restored workflow's legacy modelOverrides is NOT re-emitted on launch (selections is the single source)", async () => {
    const user = userEvent.setup();
    sessionStorage.setItem(
      "prototype.draft",
      JSON.stringify({
        templateId: "kanban",
        designSystemId: "midnight",
        brief: "restored",
        modelOverrides: { "prototype-build": "legacy-model" },
        selections: { "prototype-build": { model: "live-model" } },
        agentIds: [],
      }),
    );
    renderWithProviders(<LaunchWizard initialMode="prototype" />);
    const briefField = (await screen.findByLabelText("Brief")) as HTMLTextAreaElement;
    await waitFor(() => expect(briefField.value).toBe("restored"));
    await user.click(screen.getByRole("button", { name: "Continue" }));

    const draft = JSON.parse(sessionStorage.getItem("prototype.draft")!);
    // The stale restored model_overrides must NOT round-trip into the launch draft.
    expect(draft.modelOverrides).toBeUndefined();
    // Model lives only in selections[id].model — the single source of truth.
    expect(draft.selections).toEqual({ "prototype-build": { model: "live-model" } });
  });

  it("chaining: pre-fills the brief and hides the brief editor (topic from prior run)", async () => {
    sessionStorage.setItem("chain.from", "user_stories");
    sessionStorage.setItem("chain.brief", "chained topic");
    renderWithProviders(<LaunchWizard initialMode="prototype" />);
    // Brief editor is hidden when chaining; the chain banner is shown instead.
    await waitFor(() => expect(screen.queryByLabelText("Brief")).not.toBeInTheDocument());
    expect(screen.getByText(/Continuing from your/i)).toBeInTheDocument();
  });

  it("WR-07: chaining launch threads sourceRunId and clears the key (v2: context block no longer injected into brief)", async () => {
    const user = userEvent.setup();
    sessionStorage.setItem("chain.from", "user_stories");
    sessionStorage.setItem("chain.source_run_id", "run-42");
    // Build input for the chaining path. DashboardLayout's chain handlers always
    // write chain.brief (FIX-217) — it is the only input the wizard reads while
    // chaining, since chainContextBlock has no writer. Without it the ISS-155
    // hasBuildInput guard keeps Continue disabled and no draft is written.
    sessionStorage.setItem("chain.brief", "chained topic");
    renderWithProviders(<LaunchWizard initialMode="prototype" />);
    // Brief editor hidden when chaining — the topic comes from the prior run.
    await waitFor(() => expect(screen.queryByLabelText("Brief")).not.toBeInTheDocument());
    // A prototype still needs a design system; pick one, then click Continue.
    await user.click(await screen.findByTestId("pick-ds"));
    const continueBtn = screen.getByRole("button", { name: "Continue" });
    expect(continueBtn).toBeEnabled();
    await user.click(continueBtn);

    const draftJson = sessionStorage.getItem("prototype.draft");
    expect(draftJson).not.toBeNull();
    const draft = JSON.parse(draftJson!);
    // v2: no context block is injected — the brief is exactly the chained topic,
    // with no legacy "=== CONTEXT FROM PREVIOUS PIPELINE ===" block prepended.
    expect(draft.brief).toBe("chained topic");
    expect(draft.brief).not.toContain("=== CONTEXT FROM PREVIOUS PIPELINE ===");
    expect(draft.sourceRunId).toBe("run-42"); // pulled from chain.source_run_id
    expect(sessionStorage.getItem("prototype.pending")).toBe("true");
  });

  it("a11y: the brief and back control expose accessible names", async () => {
    renderWithProviders(<LaunchWizard initialMode="prototype" />);
    expect(await screen.findByLabelText("Brief")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Back to dashboard" })).toBeInTheDocument();
  });
});

describe("LaunchWizard — BUG-014: chain.source_run_id must not leak into a fresh launch", () => {
  it("a fresh launch (no chain.from → isChaining=false) does not leak a stale chain.source_run_id and clears the key", async () => {
    const user = userEvent.setup();
    // A stale source id lingers from a previously-viewed/chained run — but this
    // launch is a fresh Home entry (no chain.from → isChaining=false).
    sessionStorage.setItem("chain.source_run_id", "stale-run");
    renderWithProviders(<LaunchWizard initialMode="prototype" />);
    await user.type(await screen.findByLabelText("Brief"), "Build a kanban board");
    await user.click(screen.getByTestId("pick-web"));
    await user.click(await screen.findByTestId("pick-ds"));
    await user.click(screen.getByRole("button", { name: "Continue" }));

    const draft = JSON.parse(sessionStorage.getItem("prototype.draft")!);
    // Fresh launch → top-level run → NO sourceRunId in the draft.
    expect(draft.sourceRunId).toBeUndefined();
    // Consume-once: the stale key is removed so it cannot leak into a later launch.
    expect(sessionStorage.getItem("chain.source_run_id")).toBeNull();
  });

  it("a genuine chain (chain.from + chain.source_run_id → isChaining=true) still threads the source id and clears the key", async () => {
    const user = userEvent.setup();
    sessionStorage.setItem("chain.from", "user_stories");
    sessionStorage.setItem("chain.source_run_id", "run-42");
    // Chaining build input, as DashboardLayout writes it (FIX-217); see WR-07 above.
    sessionStorage.setItem("chain.brief", "chained topic");
    renderWithProviders(<LaunchWizard initialMode="prototype" />);
    // Brief editor hidden when chaining — the topic comes from the prior run.
    await waitFor(() => expect(screen.queryByLabelText("Brief")).not.toBeInTheDocument());
    await user.click(await screen.findByTestId("pick-ds"));
    const continueBtn = screen.getByRole("button", { name: "Continue" });
    expect(continueBtn).toBeEnabled();
    await user.click(continueBtn);

    const draftJson = sessionStorage.getItem("prototype.draft");
    expect(draftJson).not.toBeNull();
    const draft = JSON.parse(draftJson!);
    // Revision-family linkage preserved: a genuine chain still carries the source id.
    expect(draft.sourceRunId).toBe("run-42");
    // Consume-once: the key is cleared afterward so it can't leak into the next launch.
    expect(sessionStorage.getItem("chain.source_run_id")).toBeNull();
  });
});

// N3 / ISSUE-001 — where the three chain-source cases live, and why.
// Full trace: gaps-run/journal/N3.md (fix attempts 1–3).
//
// Requirement 21 splits this across three components, and the wizard owns
// exactly one third of it:
//  - AC 9, mixed-deploy `incompatible_backend` → RunConnectionProvider.test.tsx
//    ("mixed-deploy chain launch"). The reason code is produced in the
//    `POST /api/runs` response handler
//    (`launchedRunId && payload.source_workflow_run_id && !body?.chain_v2_accepted`).
//    `handleLaunch` below never calls that endpoint — it writes a draft to
//    sessionStorage and navigates away, so this component is already unmounted
//    when the response lands.
//  - AC 11, a non-chainable source shown unavailable with its
//    `non_chainable_reason` → WorkflowHistory.test.tsx ("non-success chain
//    sources"). The source LIST is WorkflowHistory's "Suggested next steps"
//    panel — the only frontend reader of `payloadChainable` /
//    `nonChainableReason`. This wizard is downstream of the pick and reads
//    neither (`CHAIN_SOURCE_NON_CHAINABLE_REASON_KEY` in workflowChaining.ts
//    has no writer or reader anywhere in the frontend — dead constant).
//  - AC 12, the acknowledged pre-launch warning naming the source's published
//    status → HERE. Fed by CHAIN_SOURCE_STATUS_KEY, whose only production
//    writer is WorkflowHistory.tsx (`setItem(KEY, selectedRun.status)` with
//    status in {failed, cancelled, degraded, diverted}), so the two tests
//    below drive it with real terminal status strings — never a reason code
//    this component cannot receive.
//
// gap-closure-review.md's "recommended action" named this file for all three
// (it calls the wizard "the picker"); GIT_VERSIONING_TASKS row N3 and
// GIT_VERSIONING_GAPS §1 P0 #9 inherited that. Corrected by technical-lead
// review on 2026-09-11 — see the amended row and journal/N3.md "fix attempt 3".
describe("LaunchWizard — SGV2 11.7: non-success chain-source warning (real CHAIN_SOURCE_STATUS_KEY values)", () => {
  it("status 'failed': accessible warning names the status; Continue stays disabled while unacknowledged", async () => {
    const user = userEvent.setup();
    sessionStorage.setItem("chain.from", "user_stories");
    sessionStorage.setItem("chain.source_run_id", "run-failed-source");
    sessionStorage.setItem("chain.v2.source_status", "failed");
    renderWithProviders(<LaunchWizard initialMode="prototype" />);

    // Brief editor hidden when chaining — the topic comes from the prior run.
    await waitFor(() => expect(screen.queryByLabelText("Brief")).not.toBeInTheDocument());

    expect(screen.getByText(/Source run failed — output may be incomplete/i)).toBeInTheDocument();

    const alertContainer = screen.getByRole("alert");
    expect(alertContainer).toHaveAttribute("aria-live", "assertive");

    const acknowledgeCheckbox = screen.getByLabelText(
      /I understand the output may be incomplete and want to proceed/i,
    );
    expect(acknowledgeCheckbox).not.toBeChecked();

    // canContinue's first check is `if (chainSourceStatus && !warningAcknowledged) return false`,
    // so Continue is disabled purely on the unacknowledged warning — independent
    // of the hasBuildInput/ISS-155 gate (this test seeds no chain.brief, so that
    // gate would also hold Continue disabled; WR-07 and "genuine chain" above
    // seed chain.brief to satisfy it).
    await user.click(await screen.findByTestId("pick-ds"));
    expect(screen.getByRole("button", { name: "Continue" })).toBeDisabled();

    await user.click(acknowledgeCheckbox);
    expect(acknowledgeCheckbox).toBeChecked();
  });

  it("status 'degraded': warning names both the status and the partial-output risk; checkbox toggles both ways", async () => {
    const user = userEvent.setup();
    sessionStorage.setItem("chain.from", "user_stories");
    sessionStorage.setItem("chain.source_run_id", "run-degraded-source");
    sessionStorage.setItem("chain.v2.source_status", "degraded");
    renderWithProviders(<LaunchWizard initialMode="prototype" />);

    await waitFor(() => expect(screen.queryByLabelText("Brief")).not.toBeInTheDocument());

    expect(screen.getByText(/Source run degraded — output may be incomplete/i)).toBeInTheDocument();
    expect(screen.getByText(/run you are chaining from/i)).toBeInTheDocument();
    expect(screen.getByText(/partial or missing/i)).toBeInTheDocument();

    const acknowledgeCheckbox = screen.getByLabelText(
      /I understand the output may be incomplete and want to proceed/i,
    );
    expect(acknowledgeCheckbox).not.toBeChecked();
    await user.click(acknowledgeCheckbox);
    expect(acknowledgeCheckbox).toBeChecked();
    await user.click(acknowledgeCheckbox);
    expect(acknowledgeCheckbox).not.toBeChecked();
  });
});

describe("UPLD-05 — the wizard stages raw documents, not only inlined text", () => {
  /**
   * The wizard used to ONLY inline `extractFileText`'s capped flat text into the
   * brief. A file-reading workflow never sees that: prototype_v2's `fi-planner`
   * opens `.uploads/manifest.json` and calls `extract_text` on the real files,
   * and `.uploads/` is populated ONLY from `staged_upload_ids`. So a wizard
   * launch reached the planner with an empty `.uploads/` and died on the first
   * step — the workflow was unlaunchable from its own declared surface.
   *
   * The ids must also come back in ATTACH order: stage responses resolve
   * concurrently, so the fast one lands first. This drives the two files with
   * DELIBERATELY INVERTED resolution to prove attach order survives.
   */
  const attachDocsAndLaunch = async () => {
    const user = userEvent.setup();
    extractFileTextMock.mockImplementation((_t: unknown, f: File) =>
      Promise.resolve({ filename: f.name, text: `text of ${f.name}`, truncated: false }),
    );
    // Hand-held deferreds so resolution order is DETERMINISTIC, not a race on timers.
    const settle: Record<string, (v: { stage_id: string }) => void> = {};
    stageRunFileMock.mockImplementation(
      (_t: unknown, f: File) => new Promise<{ stage_id: string }>((resolve) => { settle[f.name] = resolve; }),
    );

    const { container } = renderWithProviders(<LaunchWizard initialMode="prototype" />, {
      preloadedState: { agents: { agents: createTestAgents(), totalCount: createTestAgents().length, pipelines: {}, status: "succeeded" as const, error: null } },
    });
    await user.type(await screen.findByLabelText("Brief"), "Build from the attached docs");
    await user.click(screen.getByTestId("pick-web"));
    await user.click(await screen.findByTestId("pick-ds"));

    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(input, [
      new File(["%PDF-1.4"], "a-first.pdf", { type: "application/pdf" }),
      // A TEXT document: read client-side for the inlined preview, but it must be
      // staged all the same — `.uploads/` is what the workflow's planner opens.
      new File(["from,to\ndispatched,travelling"], "b-second.csv", { type: "text/csv" }),
      new File(["docx"], "c-third.docx", {
        type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
      }),
    ]);
    await waitFor(() => expect(Object.keys(settle)).toHaveLength(3));
    // Resolve in REVERSE attach order — the arrival order the component actually
    // appends in, and the reverse of the order the draft must end up in.
    await act(async () => {
      settle["c-third.docx"]({ stage_id: "stage-c-third.docx" });
      settle["b-second.csv"]({ stage_id: "stage-b-second.csv" });
      settle["a-first.pdf"]({ stage_id: "stage-a-first.pdf" });
    });

    await user.click(screen.getByRole("button", { name: "Continue" }));
    return JSON.parse(sessionStorage.getItem("prototype.draft") ?? "null");
  };

  it("carries the stage ids into the launch draft, in attach order", async () => {
    const draft = await attachDocsAndLaunch();
    expect(draft.stagedUploadIds).toEqual([
      "stage-a-first.pdf", "stage-b-second.csv", "stage-c-third.docx",
    ]);
  });

  it("stages TEXT documents too — a .csv read client-side must still reach .uploads/", async () => {
    const draft = await attachDocsAndLaunch();
    expect(stageRunFileMock.mock.calls.map((c) => (c[1] as File).name)).toContain("b-second.csv");
    expect(draft.stagedUploadIds).toContain("stage-b-second.csv");
  });

  it("still inlines the extracted text — staging ADDS a path, it does not replace one", async () => {
    const draft = await attachDocsAndLaunch();
    expect(draft.brief).toContain("text of a-first.pdf");
    expect(draft.brief).toContain("text of c-third.docx");
  });

  it("omits the key entirely when nothing was attached (parity with the retired flow)", async () => {
    const user = userEvent.setup();
    renderWithProviders(<LaunchWizard initialMode="prototype" />, {
      preloadedState: { agents: { agents: createTestAgents(), totalCount: createTestAgents().length, pipelines: {}, status: "succeeded" as const, error: null } },
    });
    await user.type(await screen.findByLabelText("Brief"), "Build a kanban board");
    await user.click(screen.getByTestId("pick-web"));
    await user.click(await screen.findByTestId("pick-ds"));
    await user.click(screen.getByRole("button", { name: "Continue" }));

    expect(sessionStorage.getItem("prototype.draft")).not.toContain("stagedUploadIds");
  });
});

// ISS-189 / QA-KB-010 — a deck template with design_system.requires=true needs the DS
// step mounted, or the real stepper never shows a picker while Continue stays gated.
describe("LaunchWizard — deck design-system step (ISS-189)", () => {
  for (const mode of ["ppt", "ppt_v2"] as const) {
    it(`${mode}: a DS-requiring deck template includes the design-system step`, async () => {
      const user = userEvent.setup();
      renderWithProviders(<LaunchWizard initialMode={mode} />, {
        preloadedState: { agents: { agents: createTestAgents(), totalCount: createTestAgents().length, pipelines: {}, status: "succeeded" as const, error: null } },
      });
      await user.click(await screen.findByTestId("pick-deck")); // pitch → dsRequired
      expect(screen.getByTestId("stepper").getAttribute("data-steps")).toContain("design-system");
    });
  }
});
