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
 * WizardStepper.test.tsx); the heavy pickers are stubbed like ConfigureScreen.test.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DRAFT_SCENARIOS } from "./__fixtures__/launchContract";

const pushMock = vi.fn();
const createUserWorkflowMock = vi.fn().mockResolvedValue({ id: "wf-1" });

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock, replace: vi.fn(), prefetch: vi.fn() }),
}));
vi.mock("@/lib/api", () => ({
  getToken: () => "test-token",
  extractFileText: vi.fn(),
  createUserWorkflow: (...args: unknown[]) => createUserWorkflowMock(...args),
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
    dsSlot?: React.ReactNode;
    discoverySlot?: React.ReactNode;
  }) => (
    <div data-testid="stepper" data-mode={props.mode}>
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

const golden = (name: string) => {
  const s = DRAFT_SCENARIOS.find((x) => x.name === name);
  if (!s) throw new Error(`missing scenario ${name}`);
  return s.expected;
};

beforeEach(() => {
  sessionStorage.clear();
  pushMock.mockClear();
  createUserWorkflowMock.mockClear();
});

describe("LaunchWizard — real-component launch parity (byte-identical per mode)", () => {
  it("prototype base launch writes the golden draft + pending and routes to /dashboard", async () => {
    const user = userEvent.setup();
    render(<LaunchWizard initialMode="prototype" />);
    await user.type(await screen.findByLabelText("Brief"), "Build a kanban board");
    await user.click(screen.getByTestId("pick-web"));
    await user.click(await screen.findByTestId("pick-ds"));
    await user.click(screen.getByRole("button", { name: "Continue" }));

    const g = golden("prototype · base (template + ds + brief)");
    expect(sessionStorage.getItem("prototype.draft")).toBe(g.draftJson);
    expect(sessionStorage.getItem("od_prototype.pending")).toBe("true");
    expect(pushMock).toHaveBeenCalledWith("/dashboard");
  });

  it("prototype blank-canvas launch writes templateId:null", async () => {
    const user = userEvent.setup();
    render(<LaunchWizard initialMode="prototype" />);
    await user.type(await screen.findByLabelText("Brief"), "Build a kanban board");
    await user.click(screen.getByTestId("pick-web-blank"));
    await user.click(await screen.findByTestId("pick-ds"));
    await user.click(screen.getByRole("button", { name: "Continue" }));

    expect(sessionStorage.getItem("prototype.draft")).toBe(
      golden("prototype · blank canvas (no template)").draftJson,
    );
  });

  it("ppt base launch writes the golden draft + pending", async () => {
    const user = userEvent.setup();
    render(<LaunchWizard initialMode="ppt" />);
    await user.type(await screen.findByLabelText("Brief"), "Pitch deck");
    await user.click(screen.getByTestId("pick-deck")); // pitch → dsRequired
    await user.click(await screen.findByTestId("pick-ds"));
    await user.click(screen.getByRole("button", { name: "Continue" }));

    const g = golden("ppt · base (ds required)");
    expect(sessionStorage.getItem("ppt.draft")).toBe(g.draftJson);
    expect(sessionStorage.getItem("od_ppt.pending")).toBe("true");
  });

  it("ppt template not requiring a design system writes designSystemId:null", async () => {
    const user = userEvent.setup();
    render(<LaunchWizard initialMode="ppt" />);
    await user.type(await screen.findByLabelText("Brief"), "Pitch deck");
    await user.click(screen.getByTestId("pick-deck-onepager"));
    await user.click(screen.getByRole("button", { name: "Continue" }));

    expect(sessionStorage.getItem("ppt.draft")).toBe(
      golden("ppt · ds not required (designSystemId null)").draftJson,
    );
  });

  it("WR-06: ppt custom template launches customTemplateBody with designSystemId:null (no DS required)", async () => {
    const user = userEvent.setup();
    render(<LaunchWizard initialMode="ppt" />);
    await user.type(await screen.findByLabelText("Brief"), "Custom deck");
    // A deck custom template has no registry entry → dsRequired=false → the
    // launch must succeed WITHOUT a design-system pick and emit designSystemId:null.
    await user.click(screen.getByTestId("pick-deck-custom"));
    await user.click(screen.getByRole("button", { name: "Continue" }));

    const g = golden("ppt · custom template (customTemplateBody + designSystemId null)");
    expect(sessionStorage.getItem("ppt.draft")).toBe(g.draftJson);
    expect(sessionStorage.getItem("od_ppt.pending")).toBe("true");
  });
});

describe("LaunchWizard — SC-001 Web/Deck deliverable-mode toggle", () => {
  it("toggling to Deck switches the agent pipeline + launch target to ppt", async () => {
    const user = userEvent.setup();
    render(<LaunchWizard initialMode="prototype" />);
    expect(await screen.findByTestId("agents-pipeline")).toHaveTextContent("prototype");

    await user.click(screen.getByTestId("toggle-deck"));
    expect(screen.getByTestId("agents-pipeline")).toHaveTextContent("ppt");

    await user.type(screen.getByLabelText("Brief"), "Pitch deck");
    await user.click(screen.getByTestId("pick-deck"));
    await user.click(await screen.findByTestId("pick-ds"));
    await user.click(screen.getByRole("button", { name: "Continue" }));

    // Launch wrote the ppt contract, not prototype.
    expect(sessionStorage.getItem("ppt.draft")).toBe(golden("ppt · base (ds required)").draftJson);
    expect(sessionStorage.getItem("od_ppt.pending")).toBe("true");
    expect(sessionStorage.getItem("prototype.draft")).toBeNull();
  });

  it("WR-05: page chrome (header title + brief label + save-modal title) follows the LIVE mode after toggle", async () => {
    const user = userEvent.setup();
    render(<LaunchWizard initialMode="prototype" />);
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
    render(<LaunchWizard initialMode="prototype" />);
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
    render(<LaunchWizard initialMode="prototype" />);
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
    render(<LaunchWizard initialMode="prototype" />);
    await user.type(await screen.findByLabelText("Brief"), "No discovery");
    await user.click(screen.getByTestId("pick-web"));
    await user.click(await screen.findByTestId("pick-ds"));
    await user.click(screen.getByRole("button", { name: "Continue" }));

    expect(sessionStorage.getItem("prototype.discovery")).toBeNull();
  });

  it("example-prompt: clicking 'Use template example' fills the brief", async () => {
    const user = userEvent.setup();
    render(<LaunchWizard initialMode="prototype" />);
    await screen.findByLabelText("Brief");
    await user.click(screen.getByTestId("pick-web")); // selects kanban (has example_prompt)
    await user.click(await screen.findByRole("button", { name: /use template example/i }));
    expect((screen.getByLabelText("Brief") as HTMLTextAreaElement).value).toBe("Example brief");
  });

  it("save-workflow: composes base_pipeline_type + _wizard config", async () => {
    const user = userEvent.setup();
    render(<LaunchWizard initialMode="prototype" />);
    await user.type(await screen.findByLabelText("Brief"), "Savable");
    await user.click(screen.getByTestId("pick-web"));
    await user.click(await screen.findByTestId("pick-ds"));
    await user.click(screen.getByRole("button", { name: "Save workflow" }));
    await user.click(await screen.findByTestId("confirm-save"));

    await waitFor(() => expect(createUserWorkflowMock).toHaveBeenCalledTimes(1));
    const [, body] = createUserWorkflowMock.mock.calls[0];
    expect(body.base_pipeline_type).toBe("od_prototype");
    expect(body.selections._wizard.brief).toBe("Savable");
    expect(body.selections._wizard.templateId).toBe("kanban");
  });

  it("draft restore: hydrates the brief from a mode draft then one-shot clears it", async () => {
    sessionStorage.setItem(
      "prototype.draft",
      JSON.stringify({ templateId: "kanban", designSystemId: "midnight", brief: "restored", agentIds: [] }),
    );
    render(<LaunchWizard initialMode="prototype" />);
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
    render(<LaunchWizard initialMode="prototype" />);
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
    render(<LaunchWizard initialMode="prototype" />);
    // Brief editor is hidden when chaining; the chain banner is shown instead.
    await waitFor(() => expect(screen.queryByLabelText("Brief")).not.toBeInTheDocument());
    expect(screen.getByText(/Continuing from your/i)).toBeInTheDocument();
  });

  it("WR-07: chaining launch composes finalBrief=contextBlock and threads sourceRunId", async () => {
    const user = userEvent.setup();
    sessionStorage.setItem("chain.from", "user_stories");
    sessionStorage.setItem("chain.context_block", "PRIOR CONTEXT");
    sessionStorage.setItem("chain.source_run_id", "run-42");
    render(<LaunchWizard initialMode="prototype" />);
    // Brief editor hidden when chaining — the topic comes from the prior run.
    await waitFor(() => expect(screen.queryByLabelText("Brief")).not.toBeInTheDocument());
    // A prototype still needs a design system; pick one, then click Continue.
    await user.click(await screen.findByTestId("pick-ds"));
    await user.click(screen.getByRole("button", { name: "Continue" }));

    const draft = JSON.parse(sessionStorage.getItem("prototype.draft")!);
    expect(draft.brief).toBe("PRIOR CONTEXT"); // isChaining && contextBlock → finalBrief = contextBlock
    expect(draft.sourceRunId).toBe("run-42"); // pulled from chain.source_run_id
    expect(sessionStorage.getItem("od_prototype.pending")).toBe("true");
  });

  it("a11y: the brief and back control expose accessible names", async () => {
    render(<LaunchWizard initialMode="prototype" />);
    expect(await screen.findByLabelText("Brief")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Back to dashboard" })).toBeInTheDocument();
  });
});
