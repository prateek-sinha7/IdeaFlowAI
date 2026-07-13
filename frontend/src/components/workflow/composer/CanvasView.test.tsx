/**
 * 41-05 — Composer Canvas view behaviour contract.
 *
 * The Canvas view is a HAND-ROLLED node-graph (D-04 / CMPUI-03): an <svg> edge
 * layer (bezier paths + arrow markers) UNDER absolute-positioned agent node divs,
 * a left→right sequential chain (Brief → agents), with NO graph/dnd library. It is
 * bound to the SAME shared data model as the Simple view (pipelineAgents order +
 * SelectionsMap + declaredCapabilities). Clicking a node opens the right config
 * rail (Model / Overrides / Custom prompt) — REUSING AdvancedExpander
 * (SelectionsMap) + AgentPromptSection (INV-3, not re-implemented) — with a docked
 * Run summary (no est. cost, ND-AG) beneath it.
 *
 * These tests pin the `<behavior>` cases:
 *   - node-per-agent + a dark Brief trigger pill
 *   - bezier edges between consecutive nodes (edge count = agent count)
 *   - click-select → config rail binds SelectionsMap (AdvancedExpander) +
 *     AgentPromptSection
 *   - + insert (edges + chain end) → the shared add-agent path; node remove →
 *     onRemoveAgent (mutates pipelineAgents)
 *   - docked Run summary: agents + review-gate counts, NO est. cost (ND-AG)
 *   - NO graph/dnd dependency is imported (source-level guard)
 *
 * `getCapabilities`/prompt fetchers are mocked so the reused AdvancedExpander +
 * AgentPromptSection render without a real /api fetch (same idiom as the
 * ComposerPage/Simple-view tests).
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, within, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import type { CapabilitiesPalette } from "@/lib/api";
import type { AgentDef, WorkflowType } from "@/types/index";
import type { SelectionsMap } from "../AgentsPopup";

const mockGetCapabilities = vi.fn();
vi.mock("@/lib/api", () => ({
  getToken: () => "test-token",
  getCapabilities: (t: string) => mockGetCapabilities(t),
  getAgentPrompt: vi.fn().mockResolvedValue({ prompt_body: "", override: null, has_override: false }),
  saveAgentPromptOverride: vi.fn(),
  deleteAgentPromptOverride: vi.fn(),
}));

import { CanvasView } from "./CanvasView";

const PALETTE: CapabilitiesPalette = {
  capabilities: [
    { kind: "validator", name: "code_test", user_allowed: true, description: "Runs the tests.", security_gated: false, config_schema: {} },
    { kind: "gate", name: "approval", user_allowed: true, description: "Human approval gate.", security_gated: false, config_schema: {} },
  ],
  model_catalog: [
    { id: "model-opus", label: "Opus 4.5", description: "Most capable.", tier: "powerful", cost_class: "premium", provider: "anthropic", context_window: 200000, user_allowed: true },
  ],
};

function mkAgent(over: Partial<AgentDef> & { id: string; name: string }): AgentDef {
  return {
    role: "Does a thing",
    description: "A capable agent.",
    pipeline_type: "custom",
    order: 1,
    icon: "",
    estimated_duration: 120,
    has_skill: false,
    ...over,
  } as AgentDef;
}

const AGENTS: AgentDef[] = [
  mkAgent({ id: "alpha", name: "Alpha Agent", role: "Plans", order: 1 }),
  mkAgent({ id: "bravo", name: "Bravo Agent", role: "Researches", order: 2 }),
  mkAgent({ id: "charlie", name: "Charlie Agent", role: "Writes", order: 3 }),
];

function renderCanvas(props: Record<string, unknown> = {}) {
  const onSelection = vi.fn();
  const onRemoveAgent = vi.fn();
  const onAddAgent = vi.fn();
  const onSaveToCatalogue = vi.fn();
  const utils = render(
    <CanvasView
      pipelineAgents={AGENTS}
      selections={{} as SelectionsMap}
      pipelineType={"custom" as WorkflowType}
      onSelection={onSelection}
      onRemoveAgent={onRemoveAgent}
      onAddAgent={onAddAgent}
      canAddMore
      gateCount={1}
      strategy="sequential"
      estDurationLabel="~6m"
      declaredCapabilities={["File system"]}
      onSaveToCatalogue={onSaveToCatalogue}
      {...props}
    />,
  );
  return { ...utils, onSelection, onRemoveAgent, onAddAgent, onSaveToCatalogue };
}

beforeEach(() => {
  vi.clearAllMocks();
  mockGetCapabilities.mockResolvedValue(PALETTE);
});

describe("CanvasView — hand-rolled node-graph (41-05)", () => {
  it("renders one node per agent, preceded by a dark Brief trigger pill", () => {
    renderCanvas();
    for (const a of AGENTS) {
      expect(screen.getByTestId(`canvas-node-${a.id}`)).toBeInTheDocument();
    }
    expect(screen.getByTestId("canvas-brief")).toBeInTheDocument();
    expect(screen.getByTestId("canvas-brief")).toHaveTextContent(/Brief/i);
  });

  it("renders bezier edges (Brief→first + between consecutive) = agent count, with arrow markers", () => {
    renderCanvas();
    // n agents → n edges: 1 Brief→node0 + (n-1) between consecutive nodes.
    expect(screen.getAllByTestId("canvas-edge").length).toBe(AGENTS.length);
    // arrow markers are defined (grey + brand) for the edge marker-end.
    expect(document.querySelector("marker#arw")).not.toBeNull();
    expect(document.querySelector("marker#arwb")).not.toBeNull();
  });

  it("clicking a node selects it and binds the config rail to SelectionsMap (AdvancedExpander) + AgentPromptSection", async () => {
    renderCanvas();
    await userEvent.click(screen.getByTestId("canvas-node-bravo"));
    // The reused AdvancedExpander renders for the selected node (SelectionsMap writer).
    await waitFor(() =>
      expect(screen.getByText(/Advanced — Bravo Agent/i)).toBeInTheDocument(),
    );
    // The reused AgentPromptSection renders (custom prompt view).
    expect(screen.getByText(/System Prompt/i)).toBeInTheDocument();
    // The selected node carries the selected marker.
    expect(screen.getByTestId("canvas-node-bravo")).toHaveAttribute("data-selected", "true");
  });

  it("editing a lever in the rail reports the per-agent SelectionsMap upward (shared state)", async () => {
    const { onSelection } = renderCanvas();
    await userEvent.click(screen.getByTestId("canvas-node-bravo"));
    await userEvent.click(await screen.findByText(/Advanced — Bravo Agent/i));
    const model = await screen.findByLabelText(/Model for Bravo Agent/i);
    await userEvent.selectOptions(model, "model-opus");
    await waitFor(() => expect(onSelection).toHaveBeenCalled());
    // The report targets the bravo agent id (bound to the shared data model).
    expect(onSelection.mock.calls.some((c) => c[0] === "bravo")).toBe(true);
  });

  it("+ insert affordances (on edges + at the chain end) call the shared add-agent path", async () => {
    const { onAddAgent } = renderCanvas();
    const inserts = screen.getAllByRole("button", { name: /Add agent/i });
    expect(inserts.length).toBeGreaterThan(0);
    await userEvent.click(inserts[0]);
    expect(onAddAgent).toHaveBeenCalled();
  });

  it("removing a node calls onRemoveAgent (mutates pipelineAgents) without selecting it", async () => {
    const { onRemoveAgent } = renderCanvas();
    await userEvent.click(screen.getByRole("button", { name: /Remove Charlie Agent/i }));
    expect(onRemoveAgent).toHaveBeenCalledWith("charlie");
  });

  it("docked Run summary shows agents + review-gate counts and NO est. cost (ND-AG)", () => {
    renderCanvas();
    const rail = screen.getByTestId("composer-summary-rail");
    expect(within(rail).getByText(String(AGENTS.length))).toBeInTheDocument();
    expect(within(rail).getByText(/Review gates/i)).toBeInTheDocument();
    expect(within(rail).getByText(/Est\. duration/i)).toBeInTheDocument();
    expect(within(rail).queryByText(/Est\. cost/i)).toBeNull();
  });
});

// ── No graph/dnd library + reuse guards (source-level) ───────────────────────────
describe("CanvasView — hand-rolled, no graph library, reuses the shared levers (D-04 / INV-3)", () => {
  const DIR = resolve(process.cwd(), "src/components/workflow/composer");
  const read = (p: string) => readFileSync(resolve(DIR, p), "utf8");

  it("imports NO graph/dnd dependency (hand-rolled SVG + absolute divs)", () => {
    const src =
      read("CanvasView.tsx") + read("CanvasNode.tsx") + read("CanvasConfigRail.tsx");
    // Banned graph/dnd libs — tokens assembled from fragments so this test file
    // itself does not trip the repo-level `grep -Er "<libs>" composer/` gate.
    const banned = [
      "react" + "flow",
      "@xy" + "flow",
      "dag" + "re",
      "elk" + "js",
      "cyto" + "scape",
      "dnd" + "-kit",
    ];
    for (const b of banned) expect(src).not.toContain(b);
    // hand-rolled: an <svg> edge layer is present.
    expect(read("CanvasView.tsx")).toMatch(/<svg/);
  });

  it("the config rail REUSES the exported levers (AdvancedExpander / AgentPromptSection / SelectionsMap), not forked", () => {
    const src = read("CanvasConfigRail.tsx");
    expect(src).toMatch(/AdvancedExpander/);
    expect(src).toMatch(/AgentPromptSection/);
    expect(src).toMatch(/SelectionsMap/);
  });
});
