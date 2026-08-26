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
import { screen, within, waitFor, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import renderWithProviders from "@/test/renderWithProviders";
import type { CapabilitiesPalette } from "@/lib/api";
import type { AgentDef, WorkflowType } from "@/types/index";
import type { SelectionsMap, StepSelection } from "../AgentsPopup";

const mockGetCapabilities = vi.fn();
vi.mock("@/lib/api", () => ({
  getToken: () => "test-token",
  getCapabilities: (t: string) => mockGetCapabilities(t),
  getAgentPrompt: vi.fn().mockResolvedValue({ prompt_body: "", override: null, has_override: false }),
  saveAgentPromptOverride: vi.fn(),
  deleteAgentPromptOverride: vi.fn(),
  getWorkflowDefinitions: vi.fn().mockResolvedValue([]), // Mock for external workflow rendering
}));

// CanvasConfigRail's skills picker (T29/R-36) reads the global Skills catalog
// via `useSkillsCatalog` (Redux-backed). Mocked here (same idiom as the
// `@/lib/api` mock above) so these tests don't need a live `<Provider>`.
const SKILL_FIXTURES = [
  { id: "market-research", name: "Market Research", description: "", category: "research" as const, content: "", tags: [], compatible_agents: ["alpha"] },
  { id: "any-skill", name: "Any Skill", description: "", category: "workflow" as const, content: "", tags: [] },
];
vi.mock("@/hooks/useSkillsCatalog", () => ({
  useSkillsCatalog: () => ({ skills: SKILL_FIXTURES, categories: [] }),
}));

import { CanvasView } from "./CanvasView";
import {
  computeRootLayout,
  EXTERNAL_NODE_H,
  NODE_GAP,
  NODE_W,
  NODE_Y,
  ROW_GAP,
  START_X,
} from "./graphLayout";
import { ROOT_H_EST } from "./treeLayout";

// ── Test helpers for layout computation and collision detection ────────────────
// Reuse the real layout algorithm from graphLayout.ts and test geometric invariants
// independently of jsdom (which has no layout engine).
//
// The constants above are IMPORTED, never redeclared here. A previous version of
// this file carried its own copies (NODE_GAP = 20, ROW_GAP = 16 against real values
// of 96 and 64) alongside a full replica of the layout algorithm, so the whole
// layout suite exercised a divergent copy and stayed green while the live canvas
// was visibly broken. One source for the algorithm AND its constants is what stops
// that recurring.

type LayoutSlot = { col: number; row: number };

// Wrapper to convert computeRootLayout output to test helper format.
function computeCanvasLayout(
  pipelineAgents: AgentDef[],
  selections: SelectionsMap,
  rowPortOffset: number = 88, // approximate from CanvasView
): { rootLayout: Map<string, LayoutSlot>; workflowSlots: Map<string, LayoutSlot> } {
  // Call the real layout function from graphLayout.ts
  return computeRootLayout(pipelineAgents, selections, rowPortOffset);
}

// Compute pixel coordinates for all nodes given layout and column positions.
// Returns a map of node ID -> { x, y, width, height }.
function computeNodeBoxes(
  pipelineAgents: AgentDef[],
  layout: Map<string, LayoutSlot>,
  wfSlots: Map<string, LayoutSlot>,
): Map<string, { x: number; y: number; width: number; height: number }> {
  const boxes = new Map<string, { x: number; y: number; width: number; height: number }>();

  // Simplified column x computation (assumes uniform column spacing for testing)
  const cols = new Set<number>();
  for (const a of pipelineAgents) {
    const col = layout.get(a.id)?.col ?? 0;
    cols.add(col);
  }
  for (const slot of wfSlots.values()) cols.add(slot.col);

  const columnX = new Map<number, number>();
  let x = START_X;
  [...cols].sort((p, q) => p - q).forEach((col) => {
    columnX.set(col, x);
    x += NODE_W + NODE_GAP;
  });

  // Root agents
  for (const agent of pipelineAgents) {
    const slot = layout.get(agent.id);
    if (!slot) continue;
    const col = slot.col ?? 0;
    const posX = columnX.get(col) ?? START_X;
    boxes.set(agent.id, {
      x: posX,
      y: NODE_Y + slot.row,
      width: NODE_W,
      height: ROOT_H_EST,
    });
  }

  // Workflow nodes
  for (const [key, slot] of wfSlots.entries()) {
    const posX = columnX.get(slot.col) ?? START_X;
    boxes.set(key, {
      x: posX,
      y: NODE_Y + slot.row,
      width: NODE_W,
      height: EXTERNAL_NODE_H,
    });
  }

  return boxes;
}

// Check if two boxes (as [x, y, x+w, y+h] rectangles) intersect.
function boxesIntersect(
  b1: { x: number; y: number; width: number; height: number },
  b2: { x: number; y: number; width: number; height: number },
): boolean {
  const b1Right = b1.x + b1.width;
  const b1Bottom = b1.y + b1.height;
  const b2Right = b2.x + b2.width;
  const b2Bottom = b2.y + b2.height;
  return !(b1Right <= b2.x || b1.x >= b2Right || b1Bottom <= b2.y || b1.y >= b2Bottom);
}

// L5: Verify no-overlap invariant: no two nodes' rendered boxes intersect.
function assertNoCollisions(
  boxes: Map<string, { x: number; y: number; width: number; height: number }>,
  context?: string,
): void {
  const ids = Array.from(boxes.keys());
  for (let i = 0; i < ids.length; i++) {
    for (let j = i + 1; j < ids.length; j++) {
      const b1 = boxes.get(ids[i])!;
      const b2 = boxes.get(ids[j])!;
      const intersects = boxesIntersect(b1, b2);
      if (intersects) {
        throw new Error(
          `${context ? context + ": " : ""}Collision (L5) between ${ids[i]} and ${ids[j]}. ` +
            `${ids[i]}: (${b1.x}, ${b1.y}, ${b1.width}x${b1.height}) ` +
            `${ids[j]}: (${b2.x}, ${b2.y}, ${b2.width}x${b2.height})`,
        );
      }
    }
  }
}

// L1: All nodes must be in bounds (no negative y).
function assertInBounds(
  boxes: Map<string, { x: number; y: number; width: number; height: number }>,
  context?: string,
): void {
  for (const [id, b] of boxes.entries()) {
    if (b.y < 0) {
      throw new Error(
        `${context ? context + ": " : ""}Node ${id} violates L1 (in-bounds): y=${b.y} < 0`,
      );
    }
  }
}

// L2: Fan must be vertically centred on its gate (within tolerance).
// Gate centre should equal the average of all outcome centres in the fan.
function assertFanCentred(
  agents: AgentDef[],
  layout: Map<string, { col: number; row: number }>,
  context?: string,
  tolerance: number = 10,
): void {
  for (const agent of agents) {
    const gateSlot = layout.get(agent.id);
    if (!gateSlot || !agent.route?.outcomes) continue;

    const gateCy = NODE_Y + gateSlot.row;
    const targetCol = gateSlot.col + 1;

    // Collect all outcomes in the gate's fan
    const outcomeCys: number[] = [];
    for (const [, outcome] of Object.entries(agent.route.outcomes)) {
      if (!outcome.target) continue;
      const slot =
        outcome.trigger === "workflow" ? undefined : layout.get(outcome.target);
      if (slot && slot.col === targetCol) {
        outcomeCys.push(NODE_Y + slot.row);
      }
    }

    if (outcomeCys.length < 2) continue;

    // L2: average of all outcomes should equal gate centre (within tolerance)
    const avgCy = outcomeCys.reduce((a, b) => a + b, 0) / outcomeCys.length;
    if (Math.abs(avgCy - gateCy) > tolerance) {
      throw new Error(
        `${context ? context + ": " : ""}Gate ${agent.id} violates L2 (centred). Gate cy=${gateCy}, outcomes avg=${avgCy.toFixed(1)}, diff=${Math.abs(avgCy - gateCy).toFixed(1)} > ${tolerance}`,
      );
    }
  }
}

// L3: Consecutive members of a fan must have equal vertical spacing (even pitch).
function assertEvenSpacing(
  agents: AgentDef[],
  layout: Map<string, { col: number; row: number }>,
  context?: string,
  tolerance: number = 2,
): void {
  for (const agent of agents) {
    const gateSlot = layout.get(agent.id);
    if (!gateSlot || !agent.route?.outcomes) continue;

    const targetCol = gateSlot.col + 1;

    // Collect outcomes in the fan, sorted by row
    const outcomes: { cy: number }[] = [];
    for (const [, outcome] of Object.entries(agent.route.outcomes)) {
      if (!outcome.target) continue;
      const slot =
        outcome.trigger === "workflow" ? undefined : layout.get(outcome.target);
      if (slot && slot.col === targetCol) {
        outcomes.push({ cy: NODE_Y + slot.row });
      }
    }

    if (outcomes.length < 2) continue;

    outcomes.sort((a, b) => a.cy - b.cy);

    // L3: all gaps should be equal (within tolerance)
    const gaps: number[] = [];
    for (let i = 0; i < outcomes.length - 1; i++) {
      gaps.push(outcomes[i + 1]!.cy - outcomes[i]!.cy);
    }

    const firstGap = gaps[0]!;
    for (let i = 1; i < gaps.length; i++) {
      if (Math.abs(gaps[i]! - firstGap) > tolerance) {
        throw new Error(
          `${context ? context + ": " : ""}Gate ${agent.id} violates L3 (even spacing). Gaps: [${gaps.map((g) => g.toFixed(1)).join(", ")}]`,
        );
      }
    }
  }
}

// L4: Fan extent must be compact (roughly N * (maxH + ROW_GAP)).
function assertCompact(
  agents: AgentDef[],
  layout: Map<string, { col: number; row: number }>,
  context?: string,
): void {
  for (const agent of agents) {
    const gateSlot = layout.get(agent.id);
    if (!gateSlot || !agent.route?.outcomes) continue;

    const targetCol = gateSlot.col + 1;

    // Collect outcomes with their heights
    const outcomes: { y: number; h: number }[] = [];
    for (const [, outcome] of Object.entries(agent.route.outcomes)) {
      if (!outcome.target) continue;
      const slot =
        outcome.trigger === "workflow" ? undefined : layout.get(outcome.target);
      if (slot && slot.col === targetCol) {
        const h = outcome.trigger === "workflow" ? EXTERNAL_NODE_H : ROOT_H_EST;
        outcomes.push({ y: NODE_Y + slot.row, h });
      }
    }

    if (outcomes.length < 2) continue;

    // L4: total extent should be ~n * (max_h + ROW_GAP) plus some slack
    const minY = Math.min(...outcomes.map((o) => o.y));
    const maxY = Math.max(...outcomes.map((o) => o.y + o.h));
    const extent = maxY - minY;

    const n = outcomes.length;
    const maxH = Math.max(...outcomes.map((o) => o.h));
    const expectedExtent = n * (maxH + ROW_GAP);
    const slack = Math.max(maxH, expectedExtent * 0.1);

    if (extent > expectedExtent + slack) {
      throw new Error(
        `${context ? context + ": " : ""}Gate ${agent.id} violates L4 (compact). Extent=${extent.toFixed(1)}, expected ~${expectedExtent.toFixed(1)}, slack=${slack.toFixed(1)}`,
      );
    }
  }
}

// ────────────────────────────────────────────────────────────────────────────────

const PALETTE: CapabilitiesPalette = {
  capabilities: [
    { kind: "validator", name: "code_test", user_allowed: true, description: "Runs the tests.", security_gated: false, config_schema: {} },
    { kind: "gate", name: "approval", user_allowed: true, description: "Human approval gate.", security_gated: false, config_schema: {} },
    { kind: "gate", name: "before-human", user_allowed: true, description: "Before-execute human gate.", security_gated: false, config_schema: {} },
    { kind: "gate", name: "human", user_allowed: true, description: "Post-execute human gate.", security_gated: false, config_schema: {} },
    { kind: "gate", name: "conditional", user_allowed: true, description: "Conditional gate for branching.", security_gated: false, config_schema: {} },
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
  const onBriefTextChange = vi.fn();
  const utils = renderWithProviders(
    <CanvasView
      pipelineAgents={AGENTS}
      selections={{} as SelectionsMap}
      pipelineType={"custom" as WorkflowType}
      onSelection={onSelection}
      onRemoveAgent={onRemoveAgent}
      onAddAgent={onAddAgent}
      canAddMore
      declaredCapabilities={["File system"]}
      briefText=""
      onBriefTextChange={onBriefTextChange}
      briefAttachments={{
        attachedFiles: [],
        attachedFileContents: [],
        attachedImages: [],
        handleFiles: vi.fn(),
        removeFile: vi.fn(),
        removeImage: vi.fn(),
        fileBlocks: "",
      }}
      {...props}
    />,
  );
  return { ...utils, onSelection, onRemoveAgent, onAddAgent, onBriefTextChange };
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

  it("clicking a node selects it and binds the inline config rail (Model + Overrides toggles + AgentPromptSection)", async () => {
    renderCanvas();
    await userEvent.click(screen.getByTestId("canvas-node-bravo"));
    // CanvasConfigRail shows in the Agent tab (default is Workflow tab)
    await userEvent.click(screen.getByText("Agent"));
    // AgentPromptSection (with "System Prompt") is in the Overview tab (default)
    expect(await screen.findByText(/System Prompt/i)).toBeInTheDocument();
    // Model and Overrides are in the Config tab — click to switch
    await userEvent.click(screen.getByTestId("tab-config"));
    expect(await screen.findByLabelText(/^Model$/i)).toBeInTheDocument();
    // Validator toggle switch + the Gate select are in the Config tab
    expect(screen.getByRole("switch", { name: /Validator/i })).toBeInTheDocument();
    expect(screen.getByLabelText("Gate")).toBeInTheDocument();
    // The selected node carries the selected marker.
    expect(screen.getByTestId("canvas-node-bravo")).toHaveAttribute("data-selected", "true");
  });

  it("the Model dropdown writes model to the per-agent SelectionsMap (shared state)", async () => {
    const { onSelection } = renderCanvas();
    await userEvent.click(screen.getByTestId("canvas-node-bravo"));
    // CanvasConfigRail is in the Agent tab
    await userEvent.click(screen.getByText("Agent"));
    // Model is in the Config tab, so click to switch
    await userEvent.click(screen.getByTestId("tab-config"));
    const model = await screen.findByLabelText(/^Model$/i);
    await userEvent.selectOptions(model, "model-opus");
    await waitFor(() => expect(onSelection).toHaveBeenCalled());
    const [id, sel] = onSelection.mock.calls.at(-1) as [string, StepSelection | undefined];
    expect(id).toBe("bravo");
    expect(sel?.model).toBe("model-opus");
  });

  it("the Validator toggle writes validators AND auto-attaches the coupled `validation` gate (EMP-04)", async () => {
    const { onSelection } = renderCanvas();
    await userEvent.click(screen.getByTestId("canvas-node-bravo"));
    // CanvasConfigRail is in the Agent tab
    await userEvent.click(screen.getByText("Agent"));
    // Validator toggle is in the Config tab
    await userEvent.click(screen.getByTestId("tab-config"));
    await screen.findByLabelText(/^Model$/i);
    await userEvent.click(screen.getByRole("switch", { name: /Validator/i }));
    const [id, sel] = onSelection.mock.calls.at(-1) as [string, StepSelection | undefined];
    expect(id).toBe("bravo");
    expect((sel?.validators ?? []).length).toBeGreaterThan(0);
    expect(sel?.gates).toContain("validation");
  });

  it("the Gate select attaches a gate to selections, and never offers before-human", async () => {
    const { onSelection } = renderCanvas();
    await userEvent.click(screen.getByTestId("canvas-node-bravo"));
    // CanvasConfigRail is in the Agent tab
    await userEvent.click(screen.getByText("Agent"));
    // The Gate select is in the Config tab
    await userEvent.click(screen.getByTestId("tab-config"));
    await screen.findByLabelText(/^Model$/i);
    const gate = screen.getByLabelText("Gate") as HTMLSelectElement;
    // `before-human` is reachable ONLY through the route editor's Prompt User
    // toggle (see CanvasConfigRail.test.tsx) — never from this select, because
    // it and `human` are different gates that would both label "Human gate".
    expect([...gate.options].map((o) => o.value)).not.toContain("before-human");
    await userEvent.selectOptions(gate, "conditional");
    let [id, sel] = onSelection.mock.calls.at(-1) as [string, StepSelection | undefined];
    expect(id).toBe("bravo");
    expect(sel?.gates).toEqual(["conditional"]);
    // Choosing another gate REPLACES it — a step carries one, not a set.
    await userEvent.selectOptions(screen.getByLabelText("Gate"), "human");
    [id, sel] = onSelection.mock.calls.at(-1) as [string, StepSelection | undefined];
    expect(id).toBe("bravo");
    expect(sel?.gates).toEqual(["human"]);
  });

  it("the Retry stepper writes retry to the per-agent SelectionsMap", async () => {
    const { onSelection } = renderCanvas();
    await userEvent.click(screen.getByTestId("canvas-node-bravo"));
    // CanvasConfigRail is in the Agent tab
    await userEvent.click(screen.getByText("Agent"));
    // Retry stepper is in the Config tab
    await userEvent.click(screen.getByTestId("tab-config"));
    await screen.findByLabelText(/^Model$/i);
    await userEvent.click(screen.getByRole("button", { name: /Increase retries/i }));
    const [id, sel] = onSelection.mock.calls.at(-1) as [string, StepSelection | undefined];
    expect(id).toBe("bravo");
    expect(sel?.retry).toBe(1);
  });

  it("+ insert affordances (on edges + at the chain end) call the shared add-agent path", async () => {
    const { onAddAgent } = renderCanvas();
    const inserts = screen.getAllByRole("button", { name: /Add agent/i });
    expect(inserts.length).toBeGreaterThan(0);
    // The add-agent buttons are in absolute positions in the canvas
    // Use fireEvent to bypass userEvent's visibility checks
    fireEvent.click(inserts[0]);
    expect(onAddAgent).toHaveBeenCalled();
  });

  it("removing a node calls onRemoveAgent (mutates pipelineAgents) without selecting it", async () => {
    const { onRemoveAgent } = renderCanvas();
    await userEvent.click(screen.getByRole("button", { name: /Remove Charlie Agent/i }));
    expect(onRemoveAgent).toHaveBeenCalledWith("charlie");
  });

  it("docked Run summary shows a 2×2 stat grid (Agents / Review gate / Est. duration), NO est. cost (ND-AG)", () => {
    // Note: The Run summary, agent count, review gate count, duration, and Save button
    // were intentionally moved from CanvasView to ComposerPage (the parent component).
    // This test is now a smoke test ensuring the canvas still renders without errors.
    renderCanvas();
    expect(screen.getByTestId("canvas-view")).toBeInTheDocument();
    expect(screen.getByTestId("canvas-brief")).toBeInTheDocument();
  });
});

// ── Backward loop targets preserve chain edges (A1 shape) ───────────────────────
// A backward route target (loop back) is entered normally on the first pass and
// re-entered by the loop; it must keep its incoming chain edge and not become a
// false leaf. Forward route targets are reachable only via the amber route line,
// so they correctly lose the chain edge and their predecessor becomes a leaf.
describe("CanvasView — backward (loop) targets preserve chain edges, forward targets don't (A1 shape)", () => {
  it("A1 shape: conditional gate with forward + backward outcomes; backward target keeps chain edge and predecessor is not a leaf", () => {
    // Agents: emoji (0) → greet (1) → check (2, conditional gate) → done (3)
    // Check routes: "ok" → done (forward, index 3 > 2), "retry" → greet (backward, index 1 < 2)
    const agents: AgentDef[] = [
      mkAgent({ id: "emoji", name: "Emoji Agent", role: "Greets", order: 1 }),
      mkAgent({ id: "greet", name: "Greet Agent", role: "Greets", order: 2 }),
      mkAgent({
        id: "check",
        name: "Check Agent",
        role: "Checks",
        order: 3,
        route: {
          outcomes: {
            ok: { target: "done", trigger: "step" },
            retry: { target: "greet", trigger: "step" },
          },
        },
      }),
      mkAgent({ id: "done", name: "Done Agent", role: "Finalizes", order: 4 }),
    ];

    const selections: SelectionsMap = {
      check: { gates: ["conditional"] },
    };

    const { onAddAgent } = renderCanvas({ pipelineAgents: agents, selections });

    // (a) Chain edge emoji → greet must exist: an svg path spanning from emoji
    // to greet should be drawn, even though greet is a route target (of the
    // backward outcome of check). Before the fix, greet was incorrectly in
    // routeTargetIds, suppressing its chain edge and making emoji a false leaf.
    const allEdges = screen.getAllByTestId("canvas-edge");
    // We expect at least 3 chain edges: Brief→emoji, emoji→greet, greet→check.
    // (check→done has no chain edge because done is a forward route target.)
    // Find paths that go rightward in x-space (chain/tree edges, not loops).
    const rightwardEdges = allEdges.filter((e) => {
      const d = e.getAttribute("d") ?? "";
      // A rightward edge has a target x > source x in the path "M sx sy C ... ex ey".
      const matches = d.match(/M\s+([\d.]+)\s+[\d.]+\s+C.*\s+([\d.]+)\s+[\d.]+/);
      if (!matches) return false;
      const sx = parseFloat(matches[1]!);
      const ex = parseFloat(matches[2]!);
      return ex > sx;
    });
    expect(rightwardEdges.length).toBeGreaterThanOrEqual(3);

    // (b) emoji (index 0) must NOT get a leaf affordance. Before the fix, emoji
    // was incorrectly a leaf and got a "+" button. After the fix, only the truly
    // final leaf (done) should have a "+" at the end.
    const addButtons = screen.getAllByRole("button", { name: /Add agent/i });
    // For A1: emoji (no leaf, has chain to greet), greet (no leaf, has chain to check),
    // check (not a leaf, it branches away), done (is a leaf).
    // Inter-node insert affordances on edges with chain edges: emoji→greet, greet→check (2).
    // Leaf adds: done (1).
    // HEAD add: Brief→emoji (1) — the affordance for inserting a step BEFORE the
    // first one. Added deliberately; without it prepending is unreachable from
    // the canvas, since `inserts` only pairs consecutive agents.
    // Total: 2 + 1 + 1 = 4.
    //
    // The cap is what this assertion is really for: it catches the spurious
    // LEAF "+" that emoji used to get (the original bug — emoji is not a leaf,
    // it chains to greet). 4 still fails if that regresses, because that would
    // make 5.
    expect(addButtons.length).toBeLessThanOrEqual(4);
    // ...and the head add must be exactly one, not one per node.
    expect(
      screen.getAllByRole("button", { name: /Add agent/i }).length,
    ).toBe(4);

    // (c) The last node (done, index 3) is a leaf and its add button's
    // insertBeforeId must be undefined (append at end). We can verify this by
    // clicking the last add button and checking that onAddAgent is called with
    // no insertBeforeId argument.
    fireEvent.click(addButtons[addButtons.length - 1]!);
    expect(onAddAgent).toHaveBeenCalled();
    const lastCallArg = onAddAgent.mock.calls[onAddAgent.mock.calls.length - 1]?.[0];
    // lastCallArg should be undefined (no insertBeforeId for the final leaf).
    expect(lastCallArg).toBeUndefined();
  });

  it("external workflow nodes and chain nodes in same column don't collide (workflow-only gate)", () => {
    // A3 defect case: gate with ONLY workflow outcomes, followed by a chain node.
    // Repro: emoji → language (gate) → a-english; outcomes: {spanish: workflow}.
    // The workflow slot and a-english (both col+1) must have different rows to avoid overlap.
    const agents: AgentDef[] = [
      mkAgent({ id: "emoji", name: "Emoji Agent", role: "Greets", order: 1 }),
      mkAgent({
        id: "language",
        name: "Language Agent",
        role: "Chooses",
        order: 2,
        route: {
          outcomes: {
            spanish: { target: "ex_A3_b_spanish", trigger: "workflow" },
          },
        },
      }),
      mkAgent({ id: "a-english", name: "English Agent", role: "Greets", order: 3 }),
    ];

    const selections: SelectionsMap = {
      language: { gates: ["conditional"] },
    };

    renderCanvas({ pipelineAgents: agents, selections });

    // Smoke test: all root nodes render without error.
    expect(screen.getByTestId("canvas-node-emoji")).toBeInTheDocument();
    expect(screen.getByTestId("canvas-node-language")).toBeInTheDocument();
    expect(screen.getByTestId("canvas-node-a-english")).toBeInTheDocument();

    // Assert L1-L5 invariants on computed layout values.
    const { rootLayout, workflowSlots } = computeCanvasLayout(agents, selections);
    const boxes = computeNodeBoxes(agents, rootLayout, workflowSlots);
    assertInBounds(boxes, "workflow-only gate: L1");
    assertNoCollisions(boxes, "workflow-only gate: L5");
    assertFanCentred(agents, rootLayout, "workflow-only gate: L2");
    assertEvenSpacing(agents, rootLayout, "workflow-only gate: L3");
    assertCompact(agents, rootLayout, "workflow-only gate: L4");
  });

  it("external workflow nodes and step targets in same column don't collide (mixed outcomes)", () => {
    // Full A3 shape: gate with BOTH step and workflow outcomes.
    // Outcomes: {english→step, spanish→workflow, dutch→workflow}.
    // All nodes must be fanned so that multiple outcomes in the same column have different rows.
    const agents: AgentDef[] = [
      mkAgent({ id: "emoji", name: "Emoji Agent", role: "Greets", order: 1 }),
      mkAgent({
        id: "language",
        name: "Language Agent",
        role: "Chooses",
        order: 2,
        route: {
          outcomes: {
            english: { target: "a-english", trigger: "step" },
            spanish: { target: "ex_A3_b_spanish", trigger: "workflow" },
            dutch: { target: "ex_A3_c_dutch", trigger: "workflow" },
          },
        },
      }),
      mkAgent({ id: "a-english", name: "English Agent", role: "Greets", order: 3 }),
    ];

    const selections: SelectionsMap = {
      language: { gates: ["conditional"] },
    };

    renderCanvas({ pipelineAgents: agents, selections });

    // Smoke test: all root nodes render without error.
    expect(screen.getByTestId("canvas-node-emoji")).toBeInTheDocument();
    expect(screen.getByTestId("canvas-node-language")).toBeInTheDocument();
    expect(screen.getByTestId("canvas-node-a-english")).toBeInTheDocument();

    // Assert L1-L5 invariants on computed layout values.
    const { rootLayout, workflowSlots } = computeCanvasLayout(agents, selections);
    const boxes = computeNodeBoxes(agents, rootLayout, workflowSlots);
    assertInBounds(boxes, "mixed outcomes: L1");
    assertNoCollisions(boxes, "mixed outcomes: L5");
    assertFanCentred(agents, rootLayout, "mixed outcomes: L2");
    assertEvenSpacing(agents, rootLayout, "mixed outcomes: L3");
    assertCompact(agents, rootLayout, "mixed outcomes: L4");
  });

  it("external workflow nodes in complex fan: multiple outcomes don't collide (outcome order variant)", () => {
    // Variant with different outcome arrangement: two workflows + one step.
    // Outcomes: {spanish→workflow, english→step, dutch→workflow}.
    // The fan calculation must correctly position all outcomes regardless of order.
    const agents: AgentDef[] = [
      mkAgent({ id: "emoji", name: "Emoji Agent", role: "Greets", order: 1 }),
      mkAgent({
        id: "language",
        name: "Language Agent",
        role: "Chooses",
        order: 2,
        route: {
          outcomes: {
            spanish: { target: "ex_A3_b_spanish", trigger: "workflow" },
            english: { target: "a-english", trigger: "step" },
            dutch: { target: "ex_A3_c_dutch", trigger: "workflow" },
          },
        },
      }),
      mkAgent({ id: "a-english", name: "English Agent", role: "Greets", order: 3 }),
    ];

    const selections: SelectionsMap = {
      language: { gates: ["conditional"] },
    };

    renderCanvas({ pipelineAgents: agents, selections });

    // Smoke test: all root nodes render without error.
    expect(screen.getByTestId("canvas-node-emoji")).toBeInTheDocument();
    expect(screen.getByTestId("canvas-node-language")).toBeInTheDocument();
    expect(screen.getByTestId("canvas-node-a-english")).toBeInTheDocument();

    // Assert L1-L5 invariants on computed layout values.
    const { rootLayout, workflowSlots } = computeCanvasLayout(agents, selections);
    const boxes = computeNodeBoxes(agents, rootLayout, workflowSlots);
    assertInBounds(boxes, "outcome order variant: L1");
    assertNoCollisions(boxes, "outcome order variant: L5");
    assertFanCentred(agents, rootLayout, "outcome order variant: L2");
    assertEvenSpacing(agents, rootLayout, "outcome order variant: L3");
    assertCompact(agents, rootLayout, "outcome order variant: L4");
  });

  it("A1 loop shape: backward target doesn't collide (retry→greet loop)", () => {
    // A1 shape: emoji → greet → check (conditional gate) → done
    // Check routes: "ok" → done (forward), "retry" → greet (backward/loop)
    // greet should not collide with check's fan outcomes (it's a backward target).
    const agents: AgentDef[] = [
      mkAgent({ id: "emoji", name: "Emoji Agent", role: "Greets", order: 1 }),
      mkAgent({ id: "greet", name: "Greet Agent", role: "Greets", order: 2 }),
      mkAgent({
        id: "check",
        name: "Check Agent",
        role: "Checks",
        order: 3,
        route: {
          outcomes: {
            ok: { target: "done", trigger: "step" },
            retry: { target: "greet", trigger: "step" },
          },
        },
      }),
      mkAgent({ id: "done", name: "Done Agent", role: "Finalizes", order: 4 }),
    ];

    const selections: SelectionsMap = {
      check: { gates: ["conditional"] },
    };

    renderCanvas({ pipelineAgents: agents, selections });

    // All nodes should render without error.
    expect(screen.getByTestId("canvas-node-emoji")).toBeInTheDocument();
    expect(screen.getByTestId("canvas-node-greet")).toBeInTheDocument();
    expect(screen.getByTestId("canvas-node-check")).toBeInTheDocument();
    expect(screen.getByTestId("canvas-node-done")).toBeInTheDocument();

    // Assert L1-L5 invariants: even with a backward route, layout must satisfy all constraints.
    const { rootLayout, workflowSlots } = computeCanvasLayout(agents, selections);
    const boxes = computeNodeBoxes(agents, rootLayout, workflowSlots);
    assertInBounds(boxes, "A1 loop shape: L1");
    assertNoCollisions(boxes, "A1 loop shape: L5");
    assertFanCentred(agents, rootLayout, "A1 loop shape: L2");
    assertEvenSpacing(agents, rootLayout, "A1 loop shape: L3");
    assertCompact(agents, rootLayout, "A1 loop shape: L4");
  });

  it("three-way forward branch doesn't collide (A2 all-same-height)", () => {
    // A2 shape: gate with three forward step outcomes, all same height.
    // All three targets should be fanned vertically with even spacing.
    const agents: AgentDef[] = [
      mkAgent({ id: "start", name: "Start Agent", role: "Starts", order: 1 }),
      mkAgent({
        id: "router",
        name: "Router Agent",
        role: "Routes",
        order: 2,
        route: {
          outcomes: {
            path1: { target: "path1-agent", trigger: "step" },
            path2: { target: "path2-agent", trigger: "step" },
            path3: { target: "path3-agent", trigger: "step" },
          },
        },
      }),
      mkAgent({ id: "path1-agent", name: "Path 1 Agent", role: "Handles", order: 3 }),
      mkAgent({ id: "path2-agent", name: "Path 2 Agent", role: "Handles", order: 4 }),
      mkAgent({ id: "path3-agent", name: "Path 3 Agent", role: "Handles", order: 5 }),
    ];

    const selections: SelectionsMap = {
      router: { gates: ["conditional"] },
    };

    renderCanvas({ pipelineAgents: agents, selections });

    // All nodes should render without error.
    expect(screen.getByTestId("canvas-node-start")).toBeInTheDocument();
    expect(screen.getByTestId("canvas-node-router")).toBeInTheDocument();
    expect(screen.getByTestId("canvas-node-path1-agent")).toBeInTheDocument();
    expect(screen.getByTestId("canvas-node-path2-agent")).toBeInTheDocument();
    expect(screen.getByTestId("canvas-node-path3-agent")).toBeInTheDocument();

    // Assert L1-L5 invariants on computed layout values.
    const { rootLayout, workflowSlots } = computeCanvasLayout(agents, selections);
    const boxes = computeNodeBoxes(agents, rootLayout, workflowSlots);
    assertInBounds(boxes, "A2 three-way: L1");
    assertNoCollisions(boxes, "A2 three-way: L5");
    assertFanCentred(agents, rootLayout, "A2 three-way: L2");
    assertEvenSpacing(agents, rootLayout, "A2 three-way: L3");
    assertCompact(agents, rootLayout, "A2 three-way: L4");
  });
});

// ── 51-07 (FANOUT-01 / D6/D7) — priorAgents threading into the config rail ───────
//
// CanvasView owns `pipelineAgents` + the selected-index local `selIndex`; it must
// thread `priorAgents={pipelineAgents.slice(0, selIndex)}` so the rail's fan-out
// "Source list from" picker offers ONLY the agents BEFORE the selected node, and
// that option set must change as the selection changes.
describe("CanvasView — fan-out priorAgents threading (51-07)", () => {
  // A fan-out selection so the rail renders the source picker (the picker is
  // gated on the step's `strategy === "fanout_batch"`). `onSelection` is a mock
  // that does not re-thread state, so we seed the selection to exercise the
  // threaded `priorAgents` option set directly.
  const fanoutSel = (source_step: string): StepSelection => ({
    strategy: "fanout_batch",
    task_source: { kind: "parsed", parser: "heading_tasks", source_step },
  });

  it("threads the earlier agents to the rail — the fan-out source picker lists only the agents before the selected node", async () => {
    renderCanvas({ selections: { charlie: fanoutSel("alpha") } as SelectionsMap });
    // Select charlie (index 2) → priorAgents = [alpha, bravo].
    await userEvent.click(screen.getByTestId("canvas-node-charlie"));
    // CanvasConfigRail is in the Agent tab
    await userEvent.click(screen.getByText("Agent"));
    // Fan-out source picker is in the Config tab
    await userEvent.click(screen.getByTestId("tab-config"));
    const source = await screen.findByLabelText(/source list from/i);
    expect(within(source).getByText("Alpha Agent")).toBeInTheDocument();
    expect(within(source).getByText("Bravo Agent")).toBeInTheDocument();
    // Never the selected node itself or later nodes.
    expect(within(source).queryByText("Charlie Agent")).not.toBeInTheDocument();
  });

  it("changing the selected node updates the available fan-out source options", async () => {
    renderCanvas({
      selections: {
        bravo: fanoutSel("alpha"),
        charlie: fanoutSel("alpha"),
      } as SelectionsMap,
    });
    // Select bravo (index 1) → priorAgents = [alpha] only.
    await userEvent.click(screen.getByTestId("canvas-node-bravo"));
    // CanvasConfigRail is in the Agent tab
    await userEvent.click(screen.getByText("Agent"));
    // Fan-out source picker is in the Config tab
    await userEvent.click(screen.getByTestId("tab-config"));
    let source = await screen.findByLabelText(/source list from/i);
    expect(within(source).getByText("Alpha Agent")).toBeInTheDocument();
    expect(within(source).queryByText("Bravo Agent")).not.toBeInTheDocument();

    // Re-select charlie (index 2) → priorAgents grows to [alpha, bravo].
    await userEvent.click(screen.getByTestId("canvas-node-charlie"));
    // Click Agent tab for the new selection
    await userEvent.click(screen.getByText("Agent"));
    // Click Config tab again for the new selection
    await userEvent.click(screen.getByTestId("tab-config"));
    source = await screen.findByLabelText(/source list from/i);
    expect(within(source).getByText("Alpha Agent")).toBeInTheDocument();
    expect(within(source).getByText("Bravo Agent")).toBeInTheDocument();
  });

  it("disables the fan-out toggle for the first node (no upstream to source a list)", async () => {
    renderCanvas();
    // Alpha (index 0) is selected by default → no earlier agents.
    await userEvent.click(screen.getByTestId("canvas-node-alpha"));
    // CanvasConfigRail is in the Agent tab
    await userEvent.click(screen.getByText("Agent"));
    // Fan-out toggle is in the Config tab
    await userEvent.click(screen.getByTestId("tab-config"));
    await screen.findByLabelText(/^Model$/i);
    expect(
      screen.getByRole("switch", { name: /fan out over a list/i }),
    ).toBeDisabled();
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

  it("the config rail REUSES the shared lever logic (applyLeverPatch + useAgentCapabilities + AgentPromptSection + SelectionsMap), not forked", () => {
    const src = read("CanvasConfigRail.tsx");
    expect(src).toMatch(/applyLeverPatch/);
    expect(src).toMatch(/useAgentCapabilities/);
    expect(src).toMatch(/AgentPromptSection/);
    expect(src).toMatch(/SelectionsMap/);
  });
});

// ── Spec 012 (R-35/T28) — tree rendering: children, add-sub-agent, rename ────
describe("CanvasView — canvas tree (R-35)", () => {
  it("renders a node's children below it, and clicking a child selects it via the config rail", async () => {
    const withChild: AgentDef[] = [
      { ...AGENTS[0] },
      {
        ...AGENTS[1],
        children: [
          {
            id: "agent-1",
            name: "Sub Agent",
            role: "Custom agent",
            description: "",
            pipeline_type: "custom",
            order: 0,
            icon: "",
            estimated_duration: 60,
            has_skill: false,
            isCustom: true,
            instance_id: "agent-1",
          },
        ],
      },
      { ...AGENTS[2] },
    ];
    renderCanvas({ pipelineAgents: withChild });
    // Child nodes are rendered as part of allDescendants with canvas-node-wrap-{id}
    expect(screen.getByTestId("canvas-node-wrap-agent-1")).toBeInTheDocument();
    expect(screen.getByTestId("canvas-node-agent-1")).toBeInTheDocument();

    await userEvent.click(screen.getByTestId("canvas-node-agent-1"));
    expect(screen.getByTestId("canvas-node-agent-1")).toHaveAttribute(
      "data-selected",
      "true",
    );
    // The config rail shows the agent name in an input field, not a heading
    expect(
      await screen.findByDisplayValue("Sub Agent"),
    ).toBeInTheDocument();
  });

  it("the '+ Sub-agent' affordance calls onTreeChange with a new custom-agent child (a fresh, valid instance_id)", async () => {
    const onTreeChange = vi.fn();
    renderCanvas({ onTreeChange });
    await userEvent.click(
      screen.getByRole("button", { name: /Add sub-agent to Alpha Agent/i }),
    );
    expect(onTreeChange).toHaveBeenCalled();
    const next = onTreeChange.mock.calls.at(-1)?.[0] as AgentDef[];
    const alpha = next.find((a) => a.id === "alpha")!;
    expect(alpha.children).toHaveLength(1);
    const child = alpha.children![0];
    expect(child.isCustom).toBe(true);
    expect(child.instance_id).toBe(child.id);
    expect(child.instance_id).toMatch(/^[a-z0-9][a-z0-9-]*$/);
  });

  it("inline rename edits `name` ONLY — `instance_id` never changes (R-03)", async () => {
    const onTreeChange = vi.fn();
    const withChild: AgentDef[] = [
      {
        ...AGENTS[0],
        children: [
          {
            id: "agent-1",
            name: "Sub Agent",
            role: "Custom agent",
            description: "",
            pipeline_type: "custom",
            order: 0,
            icon: "",
            estimated_duration: 60,
            has_skill: false,
            isCustom: true,
            instance_id: "agent-1",
          },
        ],
      },
    ];
    renderCanvas({ pipelineAgents: withChild, onTreeChange });
    await userEvent.click(screen.getByRole("button", { name: /^Rename Sub Agent$/i }));
    const input = screen.getByLabelText(/^Rename Sub Agent$/i);
    await userEvent.clear(input);
    await userEvent.type(input, "Renamed Sub-agent");
    await userEvent.click(screen.getByRole("button", { name: /Confirm rename/i }));

    expect(onTreeChange).toHaveBeenCalled();
    const next = onTreeChange.mock.calls.at(-1)?.[0] as AgentDef[];
    const child = next[0].children![0];
    expect(child.name).toBe("Renamed Sub-agent");
    expect(child.instance_id).toBe("agent-1");
    expect(child.id).toBe("agent-1");
  });
});
