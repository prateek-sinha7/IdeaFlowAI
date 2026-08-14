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
import type { SelectionsMap, StepSelection } from "../AgentsPopup";

const mockGetCapabilities = vi.fn();
vi.mock("@/lib/api", () => ({
  getToken: () => "test-token",
  getCapabilities: (t: string) => mockGetCapabilities(t),
  getAgentPrompt: vi.fn().mockResolvedValue({ prompt_body: "", override: null, has_override: false }),
  saveAgentPromptOverride: vi.fn(),
  deleteAgentPromptOverride: vi.fn(),
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

  it("clicking a node selects it and binds the inline config rail (Model + Overrides toggles + AgentPromptSection)", async () => {
    renderCanvas();
    await userEvent.click(screen.getByTestId("canvas-node-bravo"));
    // The inline rail renders the Model dropdown for the selected node.
    expect(await screen.findByLabelText(/^Model$/i)).toBeInTheDocument();
    // Validator + Review-gate toggle switches + the reused AgentPromptSection.
    expect(screen.getByRole("switch", { name: /Validator/i })).toBeInTheDocument();
    expect(screen.getByRole("switch", { name: /Review gate/i })).toBeInTheDocument();
    expect(screen.getByText(/System Prompt/i)).toBeInTheDocument();
    // The selected node carries the selected marker.
    expect(screen.getByTestId("canvas-node-bravo")).toHaveAttribute("data-selected", "true");
  });

  it("the Model dropdown writes model to the per-agent SelectionsMap (shared state)", async () => {
    const { onSelection } = renderCanvas();
    await userEvent.click(screen.getByTestId("canvas-node-bravo"));
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
    await screen.findByLabelText(/^Model$/i);
    await userEvent.click(screen.getByRole("switch", { name: /Validator/i }));
    const [id, sel] = onSelection.mock.calls.at(-1) as [string, StepSelection | undefined];
    expect(id).toBe("bravo");
    expect((sel?.validators ?? []).length).toBeGreaterThan(0);
    expect(sel?.gates).toContain("validation");
  });

  it("the Review-gate toggle attaches a non-validation (human) review gate", async () => {
    const { onSelection } = renderCanvas();
    await userEvent.click(screen.getByTestId("canvas-node-bravo"));
    await screen.findByLabelText(/^Model$/i);
    await userEvent.click(screen.getByRole("switch", { name: /Review gate/i }));
    const [id, sel] = onSelection.mock.calls.at(-1) as [string, StepSelection | undefined];
    expect(id).toBe("bravo");
    expect((sel?.gates ?? []).some((g) => g !== "validation")).toBe(true);
  });

  it("the Retry stepper writes retry to the per-agent SelectionsMap", async () => {
    const { onSelection } = renderCanvas();
    await userEvent.click(screen.getByTestId("canvas-node-bravo"));
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
    await userEvent.click(inserts[0]);
    expect(onAddAgent).toHaveBeenCalled();
  });

  it("removing a node calls onRemoveAgent (mutates pipelineAgents) without selecting it", async () => {
    const { onRemoveAgent } = renderCanvas();
    await userEvent.click(screen.getByRole("button", { name: /Remove Charlie Agent/i }));
    expect(onRemoveAgent).toHaveBeenCalledWith("charlie");
  });

  it("docked Run summary shows a 2×2 stat grid (Agents / Review gate / Est. duration), NO est. cost (ND-AG)", () => {
    renderCanvas();
    const sum = screen.getByTestId("canvas-run-summary");
    expect(within(sum).getByText(String(AGENTS.length))).toBeInTheDocument();
    expect(within(sum).getByText(/Review gate/i)).toBeInTheDocument();
    expect(within(sum).getByText(/Est\. duration/i)).toBeInTheDocument();
    expect(within(sum).getByText("~6m")).toBeInTheDocument();
    expect(within(sum).queryByText(/Est\. cost/i)).toBeNull();
    expect(within(sum).getByRole("button", { name: /Save to catalogue/i })).toBeInTheDocument();
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
    let source = await screen.findByLabelText(/source list from/i);
    expect(within(source).getByText("Alpha Agent")).toBeInTheDocument();
    expect(within(source).queryByText("Bravo Agent")).not.toBeInTheDocument();

    // Re-select charlie (index 2) → priorAgents grows to [alpha, bravo].
    await userEvent.click(screen.getByTestId("canvas-node-charlie"));
    source = await screen.findByLabelText(/source list from/i);
    expect(within(source).getByText("Alpha Agent")).toBeInTheDocument();
    expect(within(source).getByText("Bravo Agent")).toBeInTheDocument();
  });

  it("disables the fan-out toggle for the first node (no upstream to source a list)", async () => {
    renderCanvas();
    // Alpha (index 0) is selected by default → no earlier agents.
    await userEvent.click(screen.getByTestId("canvas-node-alpha"));
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
    expect(screen.getByTestId("canvas-children-bravo")).toBeInTheDocument();
    expect(screen.getByTestId("canvas-node-agent-1")).toBeInTheDocument();
    expect(screen.getByTestId("canvas-connector-agent-1")).toBeInTheDocument();

    await userEvent.click(screen.getByTestId("canvas-node-agent-1"));
    expect(screen.getByTestId("canvas-node-agent-1")).toHaveAttribute(
      "data-selected",
      "true",
    );
    expect(
      await screen.findByRole("heading", { level: 2, name: "Sub Agent" }),
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
