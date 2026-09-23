/**
 * ReviewGatesSection component behavior — HITL gate toggle for prototype pipeline.
 *
 * Tests the component's rendering and state management:
 *   - renders one checkbox per agent
 *   - agents with gate === "Human_Gate" start CHECKED
 *   - toggling fires onChange with the updated gate set
 *   - unchecking ALL gates yields onChange([], touched=true)
 *
 * Data integrity validation (against the API-populated agent registry) is now
 * the backend's responsibility — see backend test suite for agent discovery
 * and contract validation (agents/registry, agents/loader).
 */

import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { ReviewGatesSection } from "./ReviewGatesSection";
import type { AgentDef } from "@/types/index";

// ───────────────────────────────────────────────────────────────────────────
// Shared fixtures — test data for the component behavior
// ───────────────────────────────────────────────────────────────────────────

// Mock prototype pipeline agents for component testing
const MOCK_PROTOTYPE_AGENTS: AgentDef[] = [
  { id: "prototype-specify", name: "Spec Writer Agent", role: "Specification & Architecture", description: "Writes the specification", pipeline_type: "prototype", order: 1, icon: "📋", estimated_duration: 25, has_skill: true, gate: "Human_Gate" },
  { id: "prototype-plan", name: "Task Planner Agent", role: "Build Planning & Task Decomposition", description: "Decomposes the spec into build plan", pipeline_type: "prototype", order: 2, icon: "🗂️", estimated_duration: 15, has_skill: true, gate: "Human_Gate" },
  { id: "prototype-analyze", name: "Spec Kit Analyzer", role: "Cross-Artifact Quality Analysis", description: "Analyzes spec and task list", pipeline_type: "prototype", order: 3, icon: "🔍", estimated_duration: 20, has_skill: false, gate: "Human_Gate" },
  { id: "prototype-build", name: "Build Agent", role: "Incremental HTML Construction", description: "Builds the interactive prototype", pipeline_type: "prototype", order: 4, icon: "🏗️", estimated_duration: 60, has_skill: true, gate: null },
  { id: "prototype-validate", name: "Validation Agent", role: "Structural Validation & Delivery", description: "Validates the final prototype", pipeline_type: "prototype", order: 5, icon: "✅", estimated_duration: 60, has_skill: true, gate: null },
];

const MOCK_PPT_AGENTS: AgentDef[] = [
  { id: "ppt-brief-analyst", name: "Presentation Strategist Agent", role: "Slide Plan & Content Architecture", description: "Analyzes brief and architects slide plan", pipeline_type: "ppt", order: 1, icon: "📋", estimated_duration: 8, has_skill: true, gate: null },
  { id: "ppt-composer", name: "Deck Engineer Agent", role: "HTML Deck Construction", description: "Builds the complete HTML presentation", pipeline_type: "ppt", order: 2, icon: "🖥️", estimated_duration: 30, has_skill: true, gate: null },
  { id: "ppt-validator", name: "Deck QA Agent", role: "Structural Validation & Delivery", description: "Validates the deck for structural integrity", pipeline_type: "ppt", order: 3, icon: "📦", estimated_duration: 10, has_skill: true, gate: null },
];

// The pure pre-check predicate the component encodes
const isHumanGate = (a: AgentDef): boolean => a.gate === "Human_Gate";

// ───────────────────────────────────────────────────────────────────────────
// Data validation: mock agent shapes
// ───────────────────────────────────────────────────────────────────────────

describe("Mock agent data validation", () => {
  it("prototype agents are correctly ordered", () => {
    const ids = MOCK_PROTOTYPE_AGENTS.map((a) => a.id);
    expect(ids).toEqual([
      "prototype-specify",
      "prototype-plan",
      "prototype-analyze",
      "prototype-build",
      "prototype-validate",
    ]);
  });

  it("prototype agents have correct gate assignments", () => {
    const humanGateIds = MOCK_PROTOTYPE_AGENTS.filter(isHumanGate).map((a) => a.id);
    expect(humanGateIds).toEqual([
      "prototype-specify",
      "prototype-plan",
      "prototype-analyze",
    ]);
  });

  it("all agents carry required fields", () => {
    const allAgents = [...MOCK_PROTOTYPE_AGENTS, ...MOCK_PPT_AGENTS];
    for (const a of allAgents) {
      expect(a.id).toBeDefined();
      expect(a.name).toBeDefined();
      expect(a.pipeline_type).toBeDefined();
      expect(a.order).toBeDefined();
      expect(Object.prototype.hasOwnProperty.call(a, "gate")).toBe(true);
    }
  });
});

// ───────────────────────────────────────────────────────────────────────────
// ReviewGatesSection component behavior (jsdom)
// ───────────────────────────────────────────────────────────────────────────

describe("ReviewGatesSection — prototype pipeline", () => {
  const prototypeAgents = MOCK_PROTOTYPE_AGENTS;

  /** Render with the body expanded so the checkboxes are in the DOM. */
  async function renderExpanded(onChange = vi.fn()) {
    const user = userEvent.setup();
    render(<ReviewGatesSection agents={prototypeAgents} onChange={onChange} />);
    // Open the expandable section (the header is the first button).
    await user.click(screen.getByRole("button", { name: /review gates/i }));
    return { user, onChange };
  }

  it("renders one checkbox per agent", async () => {
    await renderExpanded();
    expect(screen.getAllByRole("checkbox")).toHaveLength(prototypeAgents.length);
  });

  it("starts with NO checkboxes pre-checked", async () => {
    await renderExpanded();
    // Checkboxes render in pipeline order; none should be pre-checked.
    const checkboxes = screen.getAllByRole("checkbox") as HTMLInputElement[];
    const checkedById: Record<string, boolean> = {};
    prototypeAgents.forEach((agent, i) => {
      checkedById[agent.id] = checkboxes[i].checked;
    });
    expect(checkedById).toEqual({
      "prototype-specify": false,
      "prototype-plan": false,
      "prototype-analyze": false,
      "prototype-build": false,
      "prototype-validate": false,
    });
  });

  it("the initial checked set is empty (user opts in explicitly)", async () => {
    await renderExpanded();
    const checkboxes = screen.getAllByRole("checkbox") as HTMLInputElement[];
    const checkedIds = prototypeAgents
      .filter((_, i) => checkboxes[i].checked)
      .map((a) => a.id);
    expect(checkedIds).toEqual([]);
  });

  it("first onChange reports empty gate ids with touched=false (no pre-selection by default)", () => {
    const onChange = vi.fn();
    render(<ReviewGatesSection agents={prototypeAgents} onChange={onChange} />);
    // The initial report fires on mount (no expand needed).
    expect(onChange).toHaveBeenCalled();
    const [ids, touched] = onChange.mock.calls[onChange.mock.calls.length - 1];
    expect(ids).toEqual([]);
    expect(touched).toBe(false);
  });

  it("toggling checkboxes fires onChange with touched=true, in pipeline order", async () => {
    const { user, onChange } = await renderExpanded();
    onChange.mockClear();

    // Checked OUT of pipeline order — build (index 3) first, then specify (index 0)
    // — because the reported array is ordered by the pipeline, not by click order.
    const checkboxes = screen.getAllByRole("checkbox") as HTMLInputElement[];
    await user.click(checkboxes[3]);
    await user.click(checkboxes[0]);

    const [ids, touched] = onChange.mock.calls[onChange.mock.calls.length - 1];
    expect(touched).toBe(true);
    expect(ids).toEqual(["prototype-specify", "prototype-build"]);
  });

  // FIX-323 removed the pre-checked defaults, so there is no longer a "default
  // gate" to uncheck. The guarantee that survives — and the one this test now
  // covers — is that unchecking a gate the user checked drops it back out.
  it("unchecking a gate the user checked fires onChange(touched=true) without it", async () => {
    const { user, onChange } = await renderExpanded();

    const checkboxes = screen.getAllByRole("checkbox") as HTMLInputElement[];
    await user.click(checkboxes[0]); // check specify
    await user.click(checkboxes[1]); // check plan
    onChange.mockClear();
    await user.click(checkboxes[0]); // and uncheck specify again

    const [ids, touched] = onChange.mock.calls[onChange.mock.calls.length - 1];
    expect(touched).toBe(true);
    expect(ids).toEqual(["prototype-plan"]);
  });

  // The payload FIX-323 turns on: [] WITH touched=true. An empty selection has to
  // reach the backend as an explicit "no gates" — `touched=false` would omit
  // `gate_agent_ids` entirely and let the backend fall back to its own defaults.
  it("unchecking every gate again yields onChange([], true) — the no-gates payload", async () => {
    const { user, onChange } = await renderExpanded();

    const checkboxes = screen.getAllByRole("checkbox") as HTMLInputElement[];
    await user.click(checkboxes[0]); // check specify
    await user.click(checkboxes[1]); // check plan
    await user.click(checkboxes[2]); // check analyze
    onChange.mockClear();
    await user.click(checkboxes[0]); // then take all three back off
    await user.click(checkboxes[1]);
    await user.click(checkboxes[2]);

    const [ids, touched] = onChange.mock.calls[onChange.mock.calls.length - 1];
    expect(touched).toBe(true);
    expect(ids).toEqual([]);
  });
});

describe("ReviewGatesSection — edge cases", () => {
  it("renders nothing when the agent list is empty", () => {
    const { container } = render(
      <ReviewGatesSection agents={[]} onChange={vi.fn()} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("ppt pipeline starts with zero pre-checked gates", () => {
    const onChange = vi.fn();
    render(<ReviewGatesSection agents={MOCK_PPT_AGENTS} onChange={onChange} />);
    const [ids, touched] = onChange.mock.calls[onChange.mock.calls.length - 1];
    expect(ids).toEqual([]);
    expect(touched).toBe(false);
  });
});

// ISS-419 — checkedIds' seed (`isSeedGated`) reads ONLY the two human-review
// gate names (`human`, `before-human`) out of `selections[id].gates`. A
// `custom-agent` step has no AGENT.md and so no static `gate` field at all —
// the manifest's `gates: [...]` array is its ONLY declaration of ANY gate,
// yet a declared `approval` or `security` gate renders this checklist with
// that step unchecked and with NO other on-load indicator anywhere in the
// checklist that the step carries a gate at all. `it.fails` is vitest's
// xfail(strict=True) — it must fail now and flip to a loud failure the
// moment isSeedGated (or an equivalent indicator) starts reflecting these
// gate values, per the project's xfail-strict convention.
describe("ReviewGatesSection — ISS-419 non-human-review manifest gates", () => {
  // A custom-agent step: no AGENT.md, so `gate` is null and the manifest's
  // `selections[id].gates` is its only declaration (ISS-247/ISS-306 shape).
  const CUSTOM_AGENT_STEP: AgentDef = {
    id: "custom-agent:reviewer",
    name: "Reviewer",
    role: "Sign-off",
    description: "Custom-agent step with a manifest-declared gate.",
    pipeline_type: "custom",
    order: 1,
    icon: "🔏",
    estimated_duration: 10,
    has_skill: false,
    gate: null,
  };

  it.fails("ISS-419 — a step with a manifest-declared approval gate renders checked on fresh load", async () => {
    const user = userEvent.setup();
    render(
      <ReviewGatesSection
        agents={[CUSTOM_AGENT_STEP]}
        onChange={vi.fn()}
        selections={{ "custom-agent:reviewer": { gates: ["approval"] } }}
      />,
    );
    await user.click(screen.getByRole("button", { name: /review gates/i }));
    expect(screen.getByRole("checkbox")).toBeChecked();
  });

  it.fails("ISS-419 — a step with a manifest-declared security gate renders checked on fresh load", async () => {
    const user = userEvent.setup();
    render(
      <ReviewGatesSection
        agents={[CUSTOM_AGENT_STEP]}
        onChange={vi.fn()}
        selections={{ "custom-agent:reviewer": { gates: ["security"] } }}
      />,
    );
    await user.click(screen.getByRole("button", { name: /review gates/i }));
    expect(screen.getByRole("checkbox")).toBeChecked();
  });
});
