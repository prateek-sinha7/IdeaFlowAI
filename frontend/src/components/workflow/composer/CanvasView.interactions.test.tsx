/**
 * CanvasView — viewport, drag, reparent, reorder, add-affordance and
 * Workflow-settings behaviour.
 *
 * Gap-closing companion to CanvasView.test.tsx (node/edge rendering, layout
 * invariants, config-rail levers). jsdom has no layout engine, so every
 * geometry assertion reads the component's OWN published coordinates (the
 * `left`/`top` style on `canvas-node-wrap-*` and the stage `transform`) rather
 * than hard-coding pixel values, and mouse positions are derived from them.
 *
 * Window-level `mousemove`/`mouseup` listeners and the native `wheel` listener
 * are driven with `fireEvent` because user-event does not model button-held
 * drags or wheel input.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, within, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import renderWithProviders from "@/test/renderWithProviders";
import type { CapabilitiesPalette } from "@/lib/api";
import type { AgentDef, WorkflowRunConfig, WorkflowType } from "@/types/index";
import type { SelectionsMap } from "../AgentsPopup";

const mockGetCapabilities = vi.fn();
vi.mock("@/lib/api", () => ({
  getToken: () => "test-token",
  getCapabilities: (t: string) => mockGetCapabilities(t),
  getAgentPrompt: vi.fn().mockResolvedValue({ prompt_body: "", override: null, has_override: false }),
  saveAgentPromptOverride: vi.fn(),
  deleteAgentPromptOverride: vi.fn(),
  getWorkflowDefinitions: vi.fn().mockResolvedValue([]),
}));

vi.mock("@/hooks/useSkillsCatalog", () => ({
  useSkillsCatalog: () => ({ skills: [], categories: [] }),
}));

import { CanvasView } from "./CanvasView";

const PALETTE: CapabilitiesPalette = { capabilities: [], model_catalog: [] };

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

const A = mkAgent({ id: "alpha", name: "Alpha Agent", order: 1 });
const B = mkAgent({ id: "bravo", name: "Bravo Agent", order: 2 });
const C = mkAgent({ id: "charlie", name: "Charlie Agent", order: 3 });
const AGENTS = [A, B, C];

const noAttachments = {
  attachedFiles: [],
  attachedFileContents: [],
  attachedImages: [],
  stagedUploads: [],
  handleFiles: vi.fn(),
  removeFile: vi.fn(),
  removeImage: vi.fn(),
  fileBlocks: "",
};

const RUN_CONFIG: WorkflowRunConfig = {
  deliverable: { strategy: "streamed_text", name: "output.md" },
  planner: "skip",
  clarify: { mode: "skip", defaults: [] },
};

function canvasElement(props: Record<string, unknown> = {}) {
  return (
    <CanvasView
      pipelineAgents={AGENTS}
      selections={{} as SelectionsMap}
      pipelineType={"custom" as WorkflowType}
      onSelection={vi.fn()}
      onRemoveAgent={vi.fn()}
      onAddAgent={vi.fn()}
      canAddMore
      declaredCapabilities={[]}
      briefText=""
      onBriefTextChange={vi.fn()}
      briefAttachments={noAttachments}
      {...props}
    />
  );
}

function renderCanvas(props: Record<string, unknown> = {}) {
  return renderWithProviders(canvasElement(props));
}

// ── geometry helpers (read from the DOM the component itself produced) ─────────
const canvasSurface = () => screen.getByTestId("canvas-view").firstElementChild as HTMLElement;
const wrapOf = (id: string) => screen.getByTestId(`canvas-node-wrap-${id}`);
const stageOf = () => wrapOf("alpha").parentElement as HTMLElement;

function stageTransform() {
  const m = /translate\((-?[\d.e+-]+)px,\s*(-?[\d.e+-]+)px\)\s*scale\(([\d.]+)\)/.exec(
    stageOf().style.transform,
  );
  if (!m) throw new Error(`unparseable stage transform: ${stageOf().style.transform}`);
  return { x: Number(m[1]), y: Number(m[2]), zoom: Number(m[3]) };
}

function nodeOrigin(id: string) {
  const el = screen.getByTestId(`canvas-node-wrap-${id}`);
  return { x: parseFloat(el.style.left), y: parseFloat(el.style.top) };
}

/** Client coordinates that land on stage point (x, y) given the live pan/zoom
 *  (jsdom's canvas rect is all zeros, so client = stage * zoom + pan). */
function clientAt(x: number, y: number) {
  const t = stageTransform();
  return { clientX: x * t.zoom + t.x, clientY: y * t.zoom + t.y };
}

/** Move the held mouse to `to` and release it there. */
function dropAt(to: { clientX: number; clientY: number }) {
  fireEvent.mouseMove(window, to);
  fireEvent.mouseUp(window, to);
}

beforeEach(() => {
  vi.clearAllMocks();
  mockGetCapabilities.mockResolvedValue(PALETTE);
});

describe("CanvasView — zoom and fit controls", () => {
  it("starts at the minimum fitted zoom in a layout-less environment and steps up by 10%", async () => {
    const user = userEvent.setup();
    renderCanvas();
    expect(screen.getByText("10%")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Zoom in" }));

    expect(screen.getByText("20%")).toBeInTheDocument();
    expect(stageTransform().zoom).toBe(0.2);
  });

  it("does not zoom out below 10%", async () => {
    const user = userEvent.setup();
    renderCanvas();

    await user.click(screen.getByRole("button", { name: "Zoom out" }));

    expect(screen.getByText("10%")).toBeInTheDocument();
  });

  it("caps zoom at 150%", async () => {
    const user = userEvent.setup();
    renderCanvas();
    const zoomIn = screen.getByRole("button", { name: "Zoom in" });

    for (let i = 0; i < 16; i += 1) await user.click(zoomIn);

    expect(screen.getByText("150%")).toBeInTheDocument();
  });

  it("zooms out again after zooming in", async () => {
    const user = userEvent.setup();
    renderCanvas();
    await user.click(screen.getByRole("button", { name: "Zoom in" }));
    await user.click(screen.getByRole("button", { name: "Zoom in" }));

    await user.click(screen.getByRole("button", { name: "Zoom out" }));

    expect(screen.getByText("20%")).toBeInTheDocument();
  });

  it("Fit restores the fitted zoom after the user zoomed in", async () => {
    const user = userEvent.setup();
    renderCanvas();
    await user.click(screen.getByRole("button", { name: "Zoom in" }));
    await user.click(screen.getByRole("button", { name: "Zoom in" }));
    expect(screen.getByText("30%")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Fit" }));

    expect(screen.getByText("10%")).toBeInTheDocument();
  });

  it("zooms with the trackpad wheel and swallows the default scroll", () => {
    renderCanvas();

    const notPrevented = fireEvent.wheel(canvasSurface(), { deltaY: -1000, clientX: 0, clientY: 0 });

    expect(notPrevented).toBe(false);
    expect(screen.getByText("27%")).toBeInTheDocument();
  });
});

describe("CanvasView — panning", () => {
  it("pans while Space is held and the canvas is dragged", () => {
    renderCanvas();
    const before = stageTransform();

    fireEvent.keyDown(window, { code: "Space" });
    fireEvent.mouseDown(canvasSurface(), { button: 0, clientX: 100, clientY: 100 });
    fireEvent.mouseMove(window, { clientX: 150, clientY: 130 });
    fireEvent.mouseUp(window);

    const after = stageTransform();
    expect(after.x).toBeCloseTo(before.x + 50);
    expect(after.y).toBeCloseTo(before.y + 30);
  });

  it("stops panning once the mouse is released", () => {
    renderCanvas();
    fireEvent.keyDown(window, { code: "Space" });
    fireEvent.mouseDown(canvasSurface(), { button: 0, clientX: 0, clientY: 0 });
    fireEvent.mouseMove(window, { clientX: 20, clientY: 0 });
    fireEvent.mouseUp(window);
    const settled = stageTransform();

    fireEvent.mouseMove(window, { clientX: 400, clientY: 400 });

    expect(stageTransform()).toEqual(settled);
  });

  it("pans with a middle-button drag without holding Space", () => {
    renderCanvas();
    const before = stageTransform();

    fireEvent.mouseDown(canvasSurface(), { button: 1, clientX: 10, clientY: 10 });
    fireEvent.mouseMove(window, { clientX: 40, clientY: 10 });
    fireEvent.mouseUp(window);

    expect(stageTransform().x).toBeCloseTo(before.x + 30);
  });

  it("does not pan on a plain left-button drag", () => {
    renderCanvas();
    const before = stageTransform();

    fireEvent.mouseDown(canvasSurface(), { button: 0, clientX: 10, clientY: 10 });
    fireEvent.mouseMove(window, { clientX: 90, clientY: 90 });

    expect(stageTransform()).toEqual(before);
  });

  it("ignores Space typed into the brief box, so spaces still type", () => {
    renderCanvas();
    const before = stageTransform();

    fireEvent.keyDown(screen.getByRole("textbox", { name: "Brief description" }), { code: "Space" });
    fireEvent.mouseDown(canvasSurface(), { button: 0, clientX: 0, clientY: 0 });
    fireEvent.mouseMove(window, { clientX: 70, clientY: 0 });

    expect(stageTransform()).toEqual(before);
  });

  it("stops treating Space as held after the key is released", () => {
    renderCanvas();
    const before = stageTransform();

    fireEvent.keyDown(window, { code: "Space" });
    fireEvent.keyUp(window, { code: "Space" });
    fireEvent.mouseDown(canvasSurface(), { button: 0, clientX: 0, clientY: 0 });
    fireEvent.mouseMove(window, { clientX: 70, clientY: 0 });

    expect(stageTransform()).toEqual(before);
  });
});

describe("CanvasView — free-dragging a node", () => {
  it("moves a node with the mouse, scaled by the current zoom", () => {
    renderCanvas();
    const start = nodeOrigin("alpha");
    const { zoom } = stageTransform();

    fireEvent.mouseDown(screen.getByTestId("canvas-node-alpha"), { button: 0, clientX: 100, clientY: 100 });
    fireEvent.mouseMove(window, { clientX: 110, clientY: 105 });

    const moved = nodeOrigin("alpha");
    expect(moved.x).toBeCloseTo(start.x + 10 / zoom);
    expect(moved.y).toBeCloseTo(start.y + 5 / zoom);
  });

  it("treats a tiny movement as a click, not a drag", () => {
    renderCanvas();
    const start = nodeOrigin("alpha");

    fireEvent.mouseDown(screen.getByTestId("canvas-node-alpha"), { button: 0, clientX: 100, clientY: 100 });
    fireEvent.mouseMove(window, { clientX: 102, clientY: 101 });

    expect(nodeOrigin("alpha")).toEqual(start);
  });

  it("stops following the mouse after release", () => {
    renderCanvas();
    fireEvent.mouseDown(screen.getByTestId("canvas-node-alpha"), { button: 0, clientX: 0, clientY: 0 });
    fireEvent.mouseMove(window, { clientX: 30, clientY: 0 });
    fireEvent.mouseUp(window);
    const settled = nodeOrigin("alpha");

    fireEvent.mouseMove(window, { clientX: 300, clientY: 300 });

    expect(nodeOrigin("alpha")).toEqual(settled);
  });

  it("ignores a drag started with a non-primary button", () => {
    renderCanvas();
    const start = nodeOrigin("alpha");

    fireEvent.mouseDown(screen.getByTestId("canvas-node-alpha"), { button: 2, clientX: 0, clientY: 0 });
    fireEvent.mouseMove(window, { clientX: 80, clientY: 80 });

    expect(nodeOrigin("alpha")).toEqual(start);
  });

  it("Auto-arrange puts dragged nodes back at their computed positions", async () => {
    const user = userEvent.setup();
    renderCanvas();
    const start = nodeOrigin("alpha");
    fireEvent.mouseDown(screen.getByTestId("canvas-node-alpha"), { button: 0, clientX: 0, clientY: 0 });
    fireEvent.mouseMove(window, { clientX: 60, clientY: 60 });
    fireEvent.mouseUp(window);
    expect(nodeOrigin("alpha")).not.toEqual(start);

    await user.click(screen.getByRole("button", { name: "Auto-arrange" }));

    expect(nodeOrigin("alpha")).toEqual(start);
  });

  it("snaps dragged nodes back when the parent bumps resetLayoutSignal (Save)", () => {
    const { rerender } = renderCanvas({ resetLayoutSignal: 0 });
    const start = nodeOrigin("alpha");
    fireEvent.mouseDown(screen.getByTestId("canvas-node-alpha"), { button: 0, clientX: 0, clientY: 0 });
    fireEvent.mouseMove(window, { clientX: 60, clientY: 60 });
    fireEvent.mouseUp(window);
    expect(nodeOrigin("alpha")).not.toEqual(start);

    rerender(canvasElement({ resetLayoutSignal: 1 }));

    expect(nodeOrigin("alpha")).toEqual(start);
  });
});

describe("CanvasView — dragging a connector to re-parent a sub-agent", () => {
  const kid = mkAgent({ id: "kid", name: "Kid Agent", isCustom: true, instance_id: "kid" });
  const tree = (): AgentDef[] => [{ ...A, children: [kid] }, { ...B }];

  function grabEdge() {
    const grab = screen.getByTestId("canvas-edge-grab");
    fireEvent.mouseDown(grab, { button: 0, clientX: 0, clientY: 0 });
  }

  it("nests the sub-agent under the node it is dropped on", () => {
    const onTreeChange = vi.fn();
    renderCanvas({ pipelineAgents: tree(), onTreeChange });
    onTreeChange.mockClear();
    const target = nodeOrigin("bravo");

    grabEdge();
    dropAt(clientAt(target.x + 20, target.y + 20));

    expect(onTreeChange).toHaveBeenCalledTimes(1);
    const next = onTreeChange.mock.calls[0][0] as AgentDef[];
    expect((next.find((a) => a.id === "alpha")!.children ?? []).map((c) => c.id)).toEqual([]);
    expect(next.find((a) => a.id === "bravo")!.children!.map((c) => c.id)).toEqual(["kid"]);
  });

  it("promotes the sub-agent to a root step when the line is dropped on empty canvas", () => {
    const onTreeChange = vi.fn();
    renderCanvas({ pipelineAgents: tree(), onTreeChange });
    onTreeChange.mockClear();

    grabEdge();
    dropAt(clientAt(9000, 9000));

    const next = onTreeChange.mock.calls[0][0] as AgentDef[];
    expect(next.map((a) => a.id)).toEqual(["alpha", "bravo", "kid"]);
  });

  it("promotes the sub-agent to a root step when dropped on the Brief pill", () => {
    const onTreeChange = vi.fn();
    renderCanvas({ pipelineAgents: tree(), onTreeChange });
    onTreeChange.mockClear();
    const brief = screen.getByTestId("canvas-brief");

    grabEdge();
    dropAt(clientAt(parseFloat(brief.style.left) + 10, parseFloat(brief.style.top) + 10));

    const next = onTreeChange.mock.calls[0][0] as AgentDef[];
    expect(next.map((a) => a.id)).toEqual(["alpha", "bravo", "kid"]);
  });

  it("offers no grabbable line on a flat chain with no sub-agents", () => {
    renderCanvas({ pipelineAgents: [A, B] });

    expect(screen.queryByTestId("canvas-edge-grab")).not.toBeInTheDocument();
  });
});

describe("CanvasView — attaching an unconnected step", () => {
  const orphan = { ...C, detached: true };

  function startConnectFrom(id: string) {
    const port = within(screen.getByTestId(`canvas-node-${id}`)).getByTitle(
      "Drag onto the unconnected step to attach it here",
    );
    fireEvent.mouseDown(port, { button: 0, clientX: 0, clientY: 0 });
  }

  it("offers the connector handle only on connected steps while a step is unconnected", () => {
    renderCanvas({ pipelineAgents: [A, B, orphan] });

    expect(
      within(screen.getByTestId("canvas-node-alpha")).getByTitle(/Drag onto the unconnected step/),
    ).toBeInTheDocument();
    expect(
      within(screen.getByTestId("canvas-node-charlie")).queryByTitle(/Drag onto the unconnected step/),
    ).not.toBeInTheDocument();
  });

  it("offers no connector handle when every step is connected", () => {
    renderCanvas({ pipelineAgents: [A, B, C] });

    expect(screen.queryByTitle(/Drag onto the unconnected step/)).not.toBeInTheDocument();
  });

  it("shows a 'Not connected' note on the unconnected step", () => {
    renderCanvas({ pipelineAgents: [A, B, orphan] });

    expect(screen.getByTestId("canvas-node-detached-charlie")).toHaveTextContent("Not connected");
  });

  it("shows a live preview line while dragging and places the step right after the source on drop", () => {
    const onTreeChange = vi.fn();
    renderCanvas({ pipelineAgents: [A, B, orphan], onTreeChange });
    onTreeChange.mockClear();
    const target = nodeOrigin("charlie");

    startConnectFrom("alpha");
    expect(screen.getByTestId("canvas-chain-connect-preview")).toBeInTheDocument();
    dropAt(clientAt(target.x + 20, target.y + 20));

    expect(screen.queryByTestId("canvas-chain-connect-preview")).not.toBeInTheDocument();
    const next = onTreeChange.mock.calls[0][0] as AgentDef[];
    expect(next.map((a) => a.id)).toEqual(["alpha", "charlie", "bravo"]);
    expect(next[1].detached).toBe(false);
  });

  it("ignores a drop on a step that is already connected", () => {
    const onTreeChange = vi.fn();
    renderCanvas({ pipelineAgents: [A, B, orphan], onTreeChange });
    onTreeChange.mockClear();
    const target = nodeOrigin("bravo");

    startConnectFrom("alpha");
    dropAt(clientAt(target.x + 20, target.y + 20));

    expect(onTreeChange).not.toHaveBeenCalled();
    expect(screen.queryByTestId("canvas-chain-connect-preview")).not.toBeInTheDocument();
  });

  it("ignores a drop on empty canvas", () => {
    const onTreeChange = vi.fn();
    renderCanvas({ pipelineAgents: [A, B, orphan], onTreeChange });
    onTreeChange.mockClear();

    startConnectFrom("alpha");
    dropAt(clientAt(9000, 9000));

    expect(onTreeChange).not.toHaveBeenCalled();
  });
});

describe("CanvasView — reordering and editing nodes", () => {
  it("moves a step later, keeping the order numbers contiguous", async () => {
    const user = userEvent.setup();
    const onTreeChange = vi.fn();
    renderCanvas({ onTreeChange });
    onTreeChange.mockClear();

    await user.click(screen.getByRole("button", { name: "Move Alpha Agent later" }));

    const next = onTreeChange.mock.calls[0][0] as AgentDef[];
    expect(next.map((a) => [a.id, a.order])).toEqual([
      ["bravo", 1],
      ["alpha", 2],
      ["charlie", 3],
    ]);
  });

  it("moves a step earlier", async () => {
    const user = userEvent.setup();
    const onTreeChange = vi.fn();
    renderCanvas({ onTreeChange });
    onTreeChange.mockClear();

    await user.click(screen.getByRole("button", { name: "Move Charlie Agent earlier" }));

    const next = onTreeChange.mock.calls[0][0] as AgentDef[];
    expect(next.map((a) => a.id)).toEqual(["alpha", "charlie", "bravo"]);
  });

  it("disables 'earlier' on the first step and 'later' on the last", () => {
    renderCanvas({ onTreeChange: vi.fn() });

    expect(screen.getByRole("button", { name: "Move Alpha Agent earlier" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Move Charlie Agent later" })).toBeDisabled();
  });

  it("offers no reorder controls when the host forwards no tree-change callback", () => {
    renderCanvas({ onTreeChange: undefined });

    expect(screen.queryByRole("button", { name: "Move Bravo Agent earlier" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Move Bravo Agent later" })).not.toBeInTheDocument();
  });

  it("selects a node from the keyboard with Enter", async () => {
    const user = userEvent.setup();
    renderCanvas();
    const node = screen.getByTestId("canvas-node-bravo");

    node.focus();
    await user.keyboard("{Enter}");

    expect(node).toHaveAttribute("data-selected", "true");
  });

  it("selects the Brief pill from the keyboard with Space after another node was selected", async () => {
    const user = userEvent.setup();
    renderCanvas();
    await user.click(screen.getByTestId("canvas-node-bravo"));
    const brief = screen.getByTestId("canvas-brief");
    expect(brief).toHaveAttribute("data-selected", "false");

    brief.focus();
    await user.keyboard(" ");

    expect(brief).toHaveAttribute("data-selected", "true");
  });

  it("falls back to the first step when the selected step is removed", async () => {
    const user = userEvent.setup();
    const { rerender } = renderCanvas();
    await user.click(screen.getByTestId("canvas-node-bravo"));
    expect(screen.getByTestId("canvas-node-bravo")).toHaveAttribute("data-selected", "true");

    rerender(canvasElement({ pipelineAgents: [A, C] }));

    expect(screen.getByTestId("canvas-node-alpha")).toHaveAttribute("data-selected", "true");
  });

  it("removes a sub-agent through the tree-change callback and clears the selection", async () => {
    const user = userEvent.setup();
    const onTreeChange = vi.fn();
    const kid = mkAgent({ id: "kid", name: "Kid Agent", isCustom: true, instance_id: "kid" });
    renderCanvas({ pipelineAgents: [{ ...A, children: [kid] }], onTreeChange });
    onTreeChange.mockClear();

    await user.click(screen.getByRole("button", { name: "Remove Kid Agent" }));

    const next = onTreeChange.mock.calls[0][0] as AgentDef[];
    expect(next[0].children ?? []).toEqual([]);
  });

  it("asks the host to open the agent library for a sub-agent when it can", async () => {
    const user = userEvent.setup();
    const onRequestAddSubAgent = vi.fn();
    const onTreeChange = vi.fn();
    renderCanvas({ onRequestAddSubAgent, onTreeChange });
    onTreeChange.mockClear();

    await user.click(screen.getByRole("button", { name: "Add sub-agent to Bravo Agent" }));

    expect(onRequestAddSubAgent).toHaveBeenCalledWith("bravo");
    expect(onTreeChange).not.toHaveBeenCalled();
  });

  it("blocks adding a sub-agent once a step already holds eight", () => {
    const kids = Array.from({ length: 8 }, (_, i) =>
      mkAgent({ id: `k${i}`, name: `Kid ${i}`, isCustom: true, instance_id: `k${i}` }),
    );
    renderCanvas({ pipelineAgents: [{ ...A, children: kids }] });

    expect(screen.getByRole("button", { name: "Add sub-agent to Alpha Agent" })).toBeDisabled();
  });

  it("blocks nesting deeper than three levels", () => {
    const grandkid = mkAgent({ id: "gk", name: "Grandkid", isCustom: true, instance_id: "gk" });
    const kid = mkAgent({ id: "kid", name: "Kid Agent", isCustom: true, instance_id: "kid", children: [grandkid] });
    renderCanvas({ pipelineAgents: [{ ...A, children: [kid] }] });

    expect(screen.getByRole("button", { name: "Add sub-agent to Grandkid" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Add sub-agent to Kid Agent" })).toBeEnabled();
  });
});

describe("CanvasView — add and insert affordances", () => {
  it("inserts before the first step from the head affordance", async () => {
    const user = userEvent.setup();
    const onAddAgent = vi.fn();
    renderCanvas({ onAddAgent });

    await user.click(screen.getByRole("button", { name: "Insert agent before step 1" }));

    expect(onAddAgent).toHaveBeenCalledWith("alpha");
  });

  it("appends from the end affordance with no anchor", async () => {
    const user = userEvent.setup();
    const onAddAgent = vi.fn();
    renderCanvas({ onAddAgent });

    await user.click(screen.getByRole("button", { name: "Add agent at end" }));

    expect(onAddAgent).toHaveBeenCalledWith(undefined);
  });

  it("offers a single add affordance on an empty canvas", async () => {
    const user = userEvent.setup();
    const onAddAgent = vi.fn();
    renderCanvas({ pipelineAgents: [], onAddAgent });

    expect(screen.getByText("the run input")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Add agent at end" }));

    expect(onAddAgent).toHaveBeenCalledWith(undefined);
  });

  it("disables every add affordance and explains the cap when no more root agents may be added", () => {
    renderCanvas({ canAddMore: false });

    expect(screen.getByRole("button", { name: "Add agent at end" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Insert agent before step 1" })).toBeDisabled();
    expect(screen.getAllByText("Maximum 16 root agents are allowed").length).toBeGreaterThan(0);
  });

  it("blocks appending after the last step of a built-in whose streamed output is the deliverable", () => {
    renderCanvas({ runConfig: RUN_CONFIG });

    expect(screen.getByRole("button", { name: "Add agent at end" })).toBeDisabled();
    expect(
      screen.getByText(/Adding a step after it would replace output\.md/),
    ).toBeInTheDocument();
  });

  it("allows appending to a composed chain even with a streamed deliverable", () => {
    renderCanvas({
      runConfig: RUN_CONFIG,
      pipelineAgents: [{ ...A, isCustom: true, instance_id: "alpha" }],
    });

    expect(screen.getByRole("button", { name: "Add agent at end" })).toBeEnabled();
  });

  it("blocks appending after the last step when the declared deliverable is a deck", () => {
    renderCanvas({
      runConfig: { ...RUN_CONFIG, deliverable: { strategy: "ppt", name: "deck.pptx" } },
      pipelineAgents: [{ ...A, isCustom: true, instance_id: "alpha" }],
    });

    expect(screen.getByRole("button", { name: "Add agent at end" })).toBeDisabled();
  });

  it("still lets an author insert before a step on a built-in with a locked tail", async () => {
    const user = userEvent.setup();
    const onAddAgent = vi.fn();
    renderCanvas({ runConfig: RUN_CONFIG, onAddAgent });

    await user.click(screen.getByRole("button", { name: "Insert agent before step 2" }));

    expect(onAddAgent).toHaveBeenCalledWith("bravo");
  });
});

describe("CanvasView — Brief", () => {
  it.each([
    ["", "3 more characters to enable Run"],
    ["a", "2 more characters to enable Run"],
    ["ab", "1 more character to enable Run"],
    ["  abc ", "Ready to run."],
  ])("shows the run-readiness hint for brief %j", (briefText, hint) => {
    renderCanvas({ briefText });

    expect(screen.getByText(hint)).toBeInTheDocument();
  });

  it("echoes the trimmed brief on the Brief pill", () => {
    renderCanvas({ briefText: "  Build a thing  " });

    expect(within(screen.getByTestId("canvas-brief")).getByText("Build a thing")).toBeInTheDocument();
  });

  it("focuses the brief box when the host bumps briefFocusSignal", () => {
    const { rerender } = renderCanvas({ briefFocusSignal: 0 });
    expect(screen.getByRole("textbox", { name: "Brief description" })).not.toHaveFocus();

    rerender(canvasElement({ briefFocusSignal: 1 }));

    expect(screen.getByRole("textbox", { name: "Brief description" })).toHaveFocus();
  });

  it("returns to the Brief when the host bumps briefFocusSignal while an agent is selected", async () => {
    const user = userEvent.setup();
    const { rerender } = renderCanvas({ briefFocusSignal: 0 });
    await user.click(screen.getByTestId("canvas-node-bravo"));
    expect(screen.queryByText("Brief instruction")).not.toBeInTheDocument();

    rerender(canvasElement({ briefFocusSignal: 1 }));

    expect(screen.getByTestId("canvas-brief")).toHaveAttribute("data-selected", "true");
    expect(screen.getByText("Brief instruction")).toBeInTheDocument();
  });

  it("forwards brief edits to the host", async () => {
    const user = userEvent.setup();
    const onBriefTextChange = vi.fn();
    renderCanvas({ onBriefTextChange });

    await user.type(screen.getByRole("textbox", { name: "Brief description" }), "x");

    expect(onBriefTextChange).toHaveBeenCalledWith("x");
  });

  it("shows the design summary on the Brief pill only when OpenDesign is declared", () => {
    const { rerender } = renderCanvas({
      designSummary: "Landing · Material",
      runConfig: { ...RUN_CONFIG, contextProvider: "opendesign" },
    });
    expect(within(screen.getByTestId("canvas-brief")).getByText("Landing · Material")).toBeInTheDocument();

    rerender(canvasElement({ designSummary: "Landing · Material", runConfig: RUN_CONFIG }));

    expect(screen.queryByText("Landing · Material")).not.toBeInTheDocument();
  });
});

describe("CanvasView — rail tabs", () => {
  it("opens on the Workflow tab and switches to the Agent tab when a node is clicked", async () => {
    const user = userEvent.setup();
    renderCanvas();
    expect(screen.getByText("Brief instruction")).toBeInTheDocument();

    await user.click(screen.getByTestId("canvas-node-bravo"))
    expect(screen.queryByText("Brief instruction")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Workflow" }));
    expect(screen.getByText("Brief instruction")).toBeInTheDocument();
  });

  it("can be flipped to the Agent tab by hand", async () => {
    const user = userEvent.setup();
    renderCanvas();

    await user.click(screen.getByRole("button", { name: "Agent" }));

    expect(screen.queryByText("Brief instruction")).not.toBeInTheDocument();
  });

  it("shows the declared capabilities docked under the rail", () => {
    renderCanvas({ declaredCapabilities: ["gate:human", "validator:code_test"] });

    const dock = screen.getByTestId("canvas-declared-capabilities");
    expect(within(dock).getByText("gate:human")).toBeInTheDocument();
    expect(within(dock).getByText("validator:code_test")).toBeInTheDocument();
  });

  it("shows a compact route summary on a conditional step and opens its config from the badge", async () => {
    const user = userEvent.setup();
    renderCanvas({
      selections: { alpha: { gates: ["conditional"] } },
      pipelineAgents: [
        {
          ...A,
          route: {
            outcomes: {
              yes: { trigger: "step", target: "bravo" },
              no: { trigger: "step", target: "charlie" },
            },
          },
        },
        B,
        C,
      ],
    });
    const badge = screen.getByTestId("canvas-node-route-alpha");
    expect(badge).toHaveTextContent("2 outcomes");

    await user.click(badge);

    expect(screen.getByTestId("canvas-node-alpha")).toHaveAttribute("data-selected", "true");
    expect(screen.queryByText("Brief instruction")).not.toBeInTheDocument();
  });

  it.each([
    [{}, "no outcomes yet"],
    [{ yes: { trigger: "step" as const, target: "bravo" } }, "1 outcome"],
  ])("summarises %j route outcomes as %s", (outcomes, text) => {
    renderCanvas({
      selections: { alpha: { gates: ["conditional"] } },
      pipelineAgents: [{ ...A, route: { outcomes } }, B],
    });

    expect(screen.getByTestId("canvas-node-route-alpha")).toHaveTextContent(text);
  });
});

describe("CanvasView — Workflow settings", () => {
  const withCallbacks = () => {
    const onRunConfigChange = vi.fn();
    const onCapabilitiesChange = vi.fn();
    return { onRunConfigChange, onCapabilitiesChange };
  };

  it("is read-only with an explanation when the host forwards no change callbacks", () => {
    renderCanvas({ runConfig: RUN_CONFIG });

    expect(screen.getByText(/Read-only — these run settings come from/)).toBeInTheDocument();
    expect(screen.getByRole("switch", { name: "Smart planning" })).toBeDisabled();
    expect(screen.getByRole("switch", { name: "Confirm requirements first" })).toBeDisabled();
    expect(screen.getByRole("switch", { name: "Internet access" })).toBeDisabled();
    expect(screen.getByRole("combobox", { name: "Deliverable strategy" })).toBeDisabled();
    expect(screen.getByRole("textbox", { name: "Output file name" })).toBeDisabled();
    expect(screen.getByRole("combobox", { name: "Context provider" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Reset to default" })).toBeDisabled();
  });

  it("turns smart planning on and off", async () => {
    const user = userEvent.setup();
    const cb = withCallbacks();
    const { rerender } = renderCanvas({ runConfig: RUN_CONFIG, ...cb });

    await user.click(screen.getByRole("switch", { name: "Smart planning" }));
    expect(cb.onRunConfigChange).toHaveBeenLastCalledWith({ ...RUN_CONFIG, planner: "run" });

    rerender(canvasElement({ runConfig: { ...RUN_CONFIG, planner: "run" }, ...cb }));
    await user.click(screen.getByRole("switch", { name: "Smart planning" }));
    expect(cb.onRunConfigChange).toHaveBeenLastCalledWith({ ...RUN_CONFIG, planner: "skip" });
  });

  it("turns requirement confirmation on and off", async () => {
    const user = userEvent.setup();
    const cb = withCallbacks();
    const { rerender } = renderCanvas({ runConfig: RUN_CONFIG, ...cb });

    await user.click(screen.getByRole("switch", { name: "Confirm requirements first" }));
    expect(cb.onRunConfigChange).toHaveBeenLastCalledWith({
      ...RUN_CONFIG,
      clarify: { mode: "auto", defaults: [] },
    });

    rerender(canvasElement({ runConfig: { ...RUN_CONFIG, clarify: { mode: "auto", defaults: [] } }, ...cb }));
    await user.click(screen.getByRole("switch", { name: "Confirm requirements first" }));
    expect(cb.onRunConfigChange).toHaveBeenLastCalledWith({
      ...RUN_CONFIG,
      clarify: { mode: "skip", defaults: [] },
    });
  });

  it("switches the deliverable strategy and swaps the file extension to the new strategy's default", async () => {
    const user = userEvent.setup();
    const cb = withCallbacks();
    renderCanvas({ runConfig: RUN_CONFIG, ...cb });
    const select = screen.getByRole("combobox", { name: "Deliverable strategy" });

    await user.selectOptions(select, "single_file");
    expect(cb.onRunConfigChange).toHaveBeenLastCalledWith({
      ...RUN_CONFIG,
      deliverable: { strategy: "single_file", name: "output.html" },
    });

    await user.selectOptions(select, "serialized_sandbox");
    expect(cb.onRunConfigChange).toHaveBeenLastCalledWith({
      ...RUN_CONFIG,
      deliverable: { strategy: "serialized_sandbox", name: "output.zip" },
    });
  });

  it("renames the output file while keeping the strategy and extension", async () => {
    const user = userEvent.setup();
    const cb = withCallbacks();
    renderCanvas({ runConfig: RUN_CONFIG, ...cb });

    await user.type(screen.getByRole("textbox", { name: "Output file name" }), "x");

    expect(cb.onRunConfigChange).toHaveBeenLastCalledWith({
      ...RUN_CONFIG,
      deliverable: { strategy: "streamed_text", name: "outputx.md" },
    });
  });

  it("falls back to 'output' when the file name is cleared", async () => {
    const user = userEvent.setup();
    const cb = withCallbacks();
    renderCanvas({ runConfig: RUN_CONFIG, ...cb });

    await user.clear(screen.getByRole("textbox", { name: "Output file name" }));

    expect(cb.onRunConfigChange).toHaveBeenLastCalledWith({
      ...RUN_CONFIG,
      deliverable: { strategy: "streamed_text", name: "output.md" },
    });
  });

  it("changes the output format", async () => {
    const user = userEvent.setup();
    const cb = withCallbacks();
    renderCanvas({ runConfig: RUN_CONFIG, ...cb });

    await user.selectOptions(screen.getByRole("combobox", { name: "Output format" }), ".html");

    expect(cb.onRunConfigChange).toHaveBeenLastCalledWith({
      ...RUN_CONFIG,
      deliverable: { strategy: "streamed_text", name: "output.html" },
    });
  });

  it("locks the output format when the strategy only offers one", () => {
    renderCanvas({
      runConfig: { ...RUN_CONFIG, deliverable: { strategy: "serialized_sandbox", name: "bundle.zip" } },
      ...withCallbacks(),
    });

    expect(screen.getByRole("combobox", { name: "Output format" })).toBeDisabled();
    expect(screen.getByRole("combobox", { name: "Output format" })).toHaveValue(".zip");
  });

  it("keeps a declared strategy and extension the composer cannot offer", () => {
    renderCanvas({
      runConfig: { ...RUN_CONFIG, deliverable: { strategy: "ppt", name: "presentation.pptx" } },
      ...withCallbacks(),
    });

    expect(screen.getByRole("combobox", { name: "Deliverable strategy" })).toHaveValue("ppt");
    expect(screen.getByRole("combobox", { name: "Output format" })).toHaveValue(".pptx");
    expect(screen.getByRole("option", { name: ".pptx — declared" })).toBeInTheDocument();
  });

  it("toggles internet access and preserves other capabilities", async () => {
    const user = userEvent.setup();
    const cb = withCallbacks();
    renderCanvas({ runConfig: RUN_CONFIG, capabilities: { internet: false }, ...cb });

    await user.click(screen.getByRole("switch", { name: "Internet access" }));

    expect(cb.onCapabilitiesChange).toHaveBeenCalledWith({ internet: true });
  });

  it("turns internet access off when it was on", async () => {
    const user = userEvent.setup();
    const cb = withCallbacks();
    renderCanvas({ runConfig: RUN_CONFIG, capabilities: { internet: true }, ...cb });

    await user.click(screen.getByRole("switch", { name: "Internet access" }));

    expect(cb.onCapabilitiesChange).toHaveBeenCalledWith({ internet: false });
  });

  it("declares OpenDesign as the context provider and seeds the web design mode", async () => {
    const user = userEvent.setup();
    const cb = withCallbacks();
    renderCanvas({ runConfig: RUN_CONFIG, ...cb });
    expect(screen.queryByRole("combobox", { name: "Design mode" })).not.toBeInTheDocument();

    await user.selectOptions(screen.getByRole("combobox", { name: "Context provider" }), "opendesign");

    expect(cb.onRunConfigChange).toHaveBeenLastCalledWith({
      ...RUN_CONFIG,
      contextProvider: "opendesign",
      designMode: "web",
    });
  });

  it("keeps the chosen design mode when the provider is re-selected", async () => {
    const user = userEvent.setup();
    const cb = withCallbacks();
    renderCanvas({ runConfig: { ...RUN_CONFIG, contextProvider: null, designMode: "deck" }, ...cb });

    await user.selectOptions(screen.getByRole("combobox", { name: "Context provider" }), "opendesign");

    expect(cb.onRunConfigChange).toHaveBeenLastCalledWith(
      expect.objectContaining({ contextProvider: "opendesign", designMode: "deck" }),
    );
  });

  it("clears the provider and design mode when None is chosen", async () => {
    const user = userEvent.setup();
    const cb = withCallbacks();
    renderCanvas({
      runConfig: { ...RUN_CONFIG, contextProvider: "opendesign", designMode: "deck" },
      ...cb,
    });

    await user.selectOptions(screen.getByRole("combobox", { name: "Context provider" }), "");

    expect(cb.onRunConfigChange).toHaveBeenLastCalledWith({
      ...RUN_CONFIG,
      contextProvider: null,
      designMode: undefined,
    });
  });

  it("switches the design mode between web and deck", async () => {
    const user = userEvent.setup();
    const cb = withCallbacks();
    renderCanvas({ runConfig: { ...RUN_CONFIG, contextProvider: "opendesign" }, ...cb });
    const mode = screen.getByRole("combobox", { name: "Design mode" });
    expect(mode).toHaveValue("web");

    await user.selectOptions(mode, "deck");

    expect(cb.onRunConfigChange).toHaveBeenLastCalledWith(
      expect.objectContaining({ designMode: "deck" }),
    );
  });

  it("resets run settings and internet access to their defaults", async () => {
    const user = userEvent.setup();
    const cb = withCallbacks();
    renderCanvas({
      runConfig: { ...RUN_CONFIG, planner: "run" },
      capabilities: { internet: true },
      ...cb,
    });

    await user.click(screen.getByRole("button", { name: "Reset to default" }));

    expect(cb.onRunConfigChange).toHaveBeenCalledWith({
      deliverable: { strategy: "streamed_text", name: "output.html" },
      planner: "skip",
      clarify: { mode: "skip", defaults: [] },
    });
    expect(cb.onCapabilitiesChange).toHaveBeenCalledWith({ internet: false });
  });
});
