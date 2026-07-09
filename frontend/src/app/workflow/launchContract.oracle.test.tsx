/**
 * ⭐ TRANSITIONAL launch-contract ORACLE (plan 37-07).
 *
 * Renders the REAL retired route-split pages (prototype/templates +
 * ppt/templates), drives each launch scenario through their live
 * `handleContinue`, and asserts the sessionStorage hand-off they write is
 * BYTE-IDENTICAL to the frozen golden fixtures (launchContract.ts). This proves
 * the goldens faithfully capture the old flow — the oracle for the unified
 * LaunchWizard's parity gate (launchDraft.parity.test.ts).
 *
 * This file is DELETED together with the old pages at the end of 37-07 (it
 * imports them). Its job — freezing the goldens against the real components —
 * is complete once green; the durable guard is the parity gate + goldens.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DRAFT_SCENARIOS } from "@/components/workflow/__fixtures__/launchContract";

// ── Seams — never hit the transport from a render test (LOCK-B). ────────────
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn() }),
}));
vi.mock("@/lib/api", () => ({
  getToken: () => "test-token",
  extractFileText: vi.fn(),
  createUserWorkflow: vi.fn(),
}));
vi.mock("@/lib/prototype-api", () => ({
  listPrototypeTemplates: vi.fn().mockResolvedValue([{ id: "kanban", name: "Kanban" }]),
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
    isListening: false,
    transcript: "",
    startListening: vi.fn(),
    stopListening: vi.fn(),
    isSupported: false,
  }),
}));

// ── Heavy child surfaces → observable trigger stubs (like ConfigureScreen.test). ──
vi.mock("@/components/workflow/prototype/TemplateGallery", () => ({
  TemplateGallery: ({
    onSelect,
    onSelectCustomTemplate,
  }: {
    onSelect: (id: string | null) => void;
    onSelectCustomTemplate?: (ct: { id: string; name: string; body: string } | null) => void;
  }) => (
    <div>
      <button data-testid="pick-web-template" onClick={() => onSelect("kanban")}>web</button>
      <button data-testid="pick-web-blank" onClick={() => onSelect(null)}>blank</button>
      <button
        data-testid="pick-web-custom"
        onClick={() => onSelectCustomTemplate?.({ id: "ct1", name: "Custom", body: "<html>custom</html>" })}
      >
        custom
      </button>
    </div>
  ),
}));
vi.mock("@/components/workflow/ppt/PPTTemplateGallery", () => ({
  PPTTemplateGallery: ({ onSelect }: { onSelect: (id: string) => void }) => (
    <div>
      <button data-testid="pick-deck-pitch" onClick={() => onSelect("pitch")}>pitch</button>
      <button data-testid="pick-deck-onepager" onClick={() => onSelect("onepager")}>onepager</button>
    </div>
  ),
}));
vi.mock("@/components/workflow/prototype/DesignSystemPicker", () => ({
  DesignSystemPicker: ({
    onSelect,
    onSelectCustom,
  }: {
    onSelect: (id: string | null) => void;
    onSelectCustom?: (ds: { id: string; name: string; body: string } | null) => void;
  }) => (
    <div>
      <button data-testid="pick-ds" onClick={() => onSelect("midnight")}>ds</button>
      <button
        data-testid="pick-ds-custom"
        onClick={() => onSelectCustom?.({ id: "cds1", name: "Custom DS", body: "/* custom ds */" })}
      >
        custom-ds
      </button>
    </div>
  ),
}));
vi.mock("@/components/workflow/ReviewGatesSection", () => ({
  ReviewGatesSection: ({ onChange }: { onChange: (ids: string[], touched: boolean) => void }) => (
    <div>
      <button data-testid="gates-specify" onClick={() => onChange(["prototype-specify"], true)}>g1</button>
      <button data-testid="gates-empty" onClick={() => onChange([], true)}>g0</button>
    </div>
  ),
}));
vi.mock("@/components/workflow/AgentsPopup", () => ({
  AgentsPopup: ({
    pipelineType,
    onModelOverridesChange,
    onSelectionsChange,
  }: {
    pipelineType: string;
    onModelOverridesChange?: (o: Record<string, string>) => void;
    onSelectionsChange?: (s: Record<string, Record<string, unknown>>) => void;
  }) => {
    const isProto = pipelineType === "prototype";
    const overrides: Record<string, string> = isProto
      ? { "prototype-build": "claude-sonnet" }
      : { "od-ppt-composer": "claude-x" };
    const selections: Record<string, Record<string, unknown>> = isProto
      ? { "prototype-build": { retryLimit: 2 } }
      : { "od-ppt-composer": { retryLimit: 3 } };
    return (
      <button
        data-testid="set-levers"
        onClick={() => {
          onModelOverridesChange?.(overrides);
          onSelectionsChange?.(selections);
        }}
      >
        levers
      </button>
    );
  },
}));
vi.mock("@/components/catalog/NameWorkflowModal", () => ({ NameWorkflowModal: () => null }));

// Import AFTER mocks are registered (vi.mock is hoisted, so this is safe).
import PrototypeTemplatesPage from "./prototype/templates/page";
import PPTTemplatesPage from "./ppt/templates/page";

const scenario = (name: string) => {
  const s = DRAFT_SCENARIOS.find((x) => x.name === name);
  if (!s) throw new Error(`missing scenario: ${name}`);
  return s;
};

beforeEach(() => {
  sessionStorage.clear();
});

describe("launch-contract ORACLE — prototype/templates page writes the golden hand-off", () => {
  it("base (template + ds + brief)", async () => {
    const user = userEvent.setup();
    render(<PrototypeTemplatesPage />);
    await user.type(await screen.findByPlaceholderText(/kanban board/i), "Build a kanban board");
    await user.click(screen.getByTestId("pick-web-template"));
    await user.click(screen.getByTestId("pick-ds"));
    await user.click(screen.getByRole("button", { name: "Continue" }));

    const g = scenario("prototype · base (template + ds + brief)");
    expect(sessionStorage.getItem("prototype.draft")).toBe(g.expected.draftJson);
    expect(sessionStorage.getItem("od_prototype.pending")).toBe("true");
  });

  it("blank canvas (no template)", async () => {
    const user = userEvent.setup();
    render(<PrototypeTemplatesPage />);
    await user.type(await screen.findByPlaceholderText(/kanban board/i), "Build a kanban board");
    await user.click(screen.getByTestId("pick-web-blank"));
    await user.click(screen.getByTestId("pick-ds"));
    await user.click(screen.getByRole("button", { name: "Continue" }));

    const g = scenario("prototype · blank canvas (no template)");
    expect(sessionStorage.getItem("prototype.draft")).toBe(g.expected.draftJson);
  });

  it("rich (custom bodies + chain + gates + levers)", async () => {
    const user = userEvent.setup();
    render(<PrototypeTemplatesPage />);
    await user.type(await screen.findByPlaceholderText(/kanban board/i), "Rich brief");
    await user.click(screen.getByTestId("pick-web-custom"));
    await user.click(screen.getByTestId("pick-ds-custom"));
    sessionStorage.setItem("chain.source_run_id", "run-123");
    await user.click(screen.getByTestId("gates-specify"));
    await user.click(screen.getByTestId("set-levers"));
    await user.click(screen.getByRole("button", { name: "Continue" }));

    const g = scenario("prototype · rich (custom bodies + chain + gates + levers)");
    expect(sessionStorage.getItem("prototype.draft")).toBe(g.expected.draftJson);
  });
});

describe("launch-contract ORACLE — ppt/templates page writes the golden hand-off", () => {
  it("base (ds required)", async () => {
    const user = userEvent.setup();
    render(<PPTTemplatesPage />);
    await user.type(await screen.findByPlaceholderText(/pitch deck|fundraise/i), "Pitch deck");
    await user.click(screen.getByTestId("pick-deck-pitch"));
    await user.click(await screen.findByTestId("pick-ds"));
    await user.click(screen.getByRole("button", { name: "Continue" }));

    const g = scenario("ppt · base (ds required)");
    expect(sessionStorage.getItem("ppt.draft")).toBe(g.expected.draftJson);
    expect(sessionStorage.getItem("od_ppt.pending")).toBe("true");
  });

  it("ds not required (designSystemId null)", async () => {
    const user = userEvent.setup();
    render(<PPTTemplatesPage />);
    await user.type(await screen.findByPlaceholderText(/pitch deck|fundraise/i), "Pitch deck");
    await user.click(screen.getByTestId("pick-deck-onepager"));
    await user.click(screen.getByRole("button", { name: "Continue" }));

    const g = scenario("ppt · ds not required (designSystemId null)");
    expect(sessionStorage.getItem("ppt.draft")).toBe(g.expected.draftJson);
  });

  it("rich (ds-requiring template + custom ds + chain + gates empty + levers)", async () => {
    const user = userEvent.setup();
    render(<PPTTemplatesPage />);
    await user.type(await screen.findByPlaceholderText(/pitch deck|fundraise/i), "Rich deck");
    await user.click(screen.getByTestId("pick-deck-pitch"));
    await user.click(await screen.findByTestId("pick-ds-custom"));
    sessionStorage.setItem("chain.source_run_id", "run-9");
    await user.click(screen.getByTestId("gates-empty"));
    await user.click(screen.getByTestId("set-levers"));
    await user.click(screen.getByRole("button", { name: "Continue" }));

    const g = scenario("ppt · rich (ds-requiring template + custom ds + chain + gates empty + levers)");
    expect(sessionStorage.getItem("ppt.draft")).toBe(g.expected.draftJson);
  });
});
