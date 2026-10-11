import { describe, expect, it } from "vitest";
import type { AgentDef } from "@/types/index";
import type { SelectionsMap } from "../AgentsPopup";
import { computeRootLayout, EXTERNAL_NODE_H, ROW_GAP } from "./graphLayout";

// Expected rows below are derived by hand from the layout rules, not from the
// implementation: a fan of members is stacked top-to-bottom with ROW_GAP (64)
// between them and centred on the gate's own centre; the node height is the
// larger of the measured card height (2 x rowPortOffset) and the 208px estimate;
// a workflow node is EXTERNAL_NODE_H (58) tall; finally the whole graph is
// shifted down so no row is negative.

const PORT = 104; // measured card height 208 == the estimate
const CONDITIONAL: SelectionsMap[string] = { gates: ["conditional"] };

function agent(id: string, over: Partial<AgentDef> = {}): AgentDef {
  return {
    id,
    name: id,
    role: "role",
    description: "",
    pipeline_type: "custom",
    order: 0,
    icon: "",
    estimated_duration: 0,
    has_skill: false,
    ...over,
  };
}

function routed(id: string, outcomes: Record<string, { trigger: "step" | "workflow"; target: string }>) {
  return agent(id, { route: { outcomes } });
}

describe("computeRootLayout", () => {
  it("returns empty layouts for an empty pipeline", () => {
    const { rootLayout, workflowSlots } = computeRootLayout([], {}, PORT);

    expect(rootLayout.size).toBe(0);
    expect(workflowSlots.size).toBe(0);
  });

  it("lays a plain chain out left to right on a single row", () => {
    const { rootLayout, workflowSlots } = computeRootLayout([agent("a"), agent("b"), agent("c")], {}, PORT);

    expect(Object.fromEntries(rootLayout)).toEqual({
      a: { col: 0, row: 0 },
      b: { col: 1, row: 0 },
      c: { col: 2, row: 0 },
    });
    expect(workflowSlots.size).toBe(0);
  });

  describe("conditional fans", () => {
    it("fans forward step targets symmetrically around the gate and shifts the graph to non-negative rows", () => {
      const agents = [routed("a", { x: { trigger: "step", target: "b" }, y: { trigger: "step", target: "c" } }), agent("b"), agent("c")];

      const { rootLayout } = computeRootLayout(agents, { a: CONDITIONAL }, PORT);

      // totalH = 208 + 64 + 208 = 480, stack top = 0 + 104 - 240 = -136 -> b -136, c 136; shift +136.
      expect(Object.fromEntries(rootLayout)).toEqual({
        a: { col: 0, row: 136 },
        b: { col: 1, row: 0 },
        c: { col: 1, row: 272 },
      });
    });

    it("uses the measured card height rather than the estimate when cards are taller", () => {
      const agents = [routed("a", { x: { trigger: "step", target: "b" }, y: { trigger: "step", target: "c" } }), agent("b"), agent("c")];

      const { rootLayout } = computeRootLayout(agents, { a: CONDITIONAL }, 150);

      // card height 300: totalH = 664, stack top = 150 - 332 = -182 -> b -182, c 182; shift +182.
      expect(Object.fromEntries(rootLayout)).toEqual({
        a: { col: 0, row: 182 },
        b: { col: 1, row: 0 },
        c: { col: 1, row: 364 },
      });
    });

    it("places a workflow outcome in a separate slot beside the step targets", () => {
      const agents = [
        routed("a", { w: { trigger: "workflow", target: "other-flow" }, x: { trigger: "step", target: "b" } }),
        agent("b"),
      ];

      const { rootLayout, workflowSlots } = computeRootLayout(agents, { a: CONDITIONAL }, PORT);

      // totalH = 58 + 64 + 208 = 330, stack top = 104 - 165 = -61 -> w -61, b 61; shift +61.
      expect(workflowSlots.get("a::w")).toEqual({ col: 1, row: 0 });
      expect(rootLayout.get("b")).toEqual({ col: 1, row: 122 });
      expect(rootLayout.get("a")).toEqual({ col: 0, row: 61 });
      expect(workflowSlots.size).toBe(1);
      expect(rootLayout.has("a::w")).toBe(false);
      expect(122 - 0).toBeGreaterThanOrEqual(EXTERNAL_NODE_H + ROW_GAP);
    });

    it("gives two outcomes that target the same step a single slot", () => {
      const agents = [routed("a", { x: { trigger: "step", target: "b" }, y: { trigger: "step", target: "b" } }), agent("b")];

      const { rootLayout } = computeRootLayout(agents, { a: CONDITIONAL }, PORT);

      expect(rootLayout.get("a")).toEqual({ col: 0, row: 0 });
      expect(rootLayout.get("b")).toEqual({ col: 1, row: 0 });
    });

    it("ignores outcomes that have no target", () => {
      const agents = [routed("a", { x: { trigger: "step", target: "" }, w: { trigger: "workflow", target: "" } }), agent("b")];

      const { rootLayout, workflowSlots } = computeRootLayout(agents, { a: CONDITIONAL }, PORT);

      // Nothing is wired out of the gate (so the next step gets no chain edge either)
      // and no slot is created; b shares column 0 with a and is stacked below it.
      expect(workflowSlots.size).toBe(0);
      expect(rootLayout.get("b")).toEqual({ col: 0, row: 272 });
    });

    it("keeps a backward (loop) target where the chain put it", () => {
      const agents = [agent("a"), routed("b", { again: { trigger: "step", target: "a" } })];

      const { rootLayout } = computeRootLayout(agents, { b: CONDITIONAL }, PORT);

      expect(Object.fromEntries(rootLayout)).toEqual({
        a: { col: 0, row: 0 },
        b: { col: 1, row: 0 },
      });
    });

    it("does not fan a route whose step is not a conditional gate", () => {
      const agents = [routed("a", { x: { trigger: "step", target: "b" } }), agent("b")];

      const { rootLayout } = computeRootLayout(agents, {}, PORT);

      expect(Object.fromEntries(rootLayout)).toEqual({
        a: { col: 0, row: 0 },
        b: { col: 1, row: 0 },
      });
    });

    it("resolves a route target written with the custom-agent prefix", () => {
      const agents = [
        routed("a", { x: { trigger: "step", target: "custom-agent:b" } }),
        agent("b"),
        agent("c"),
      ];

      const { rootLayout } = computeRootLayout(agents, { a: CONDITIONAL }, PORT);

      // b is a fan member of a (column 1, centred on a); c has no incoming edge so stays in column 0.
      expect(rootLayout.get("b")).toEqual({ col: 1, row: 0 });
      expect(rootLayout.get("a")).toEqual({ col: 0, row: 0 });
    });

    it("lets a step after a fan member inherit that member's lane", () => {
      const agents = [
        routed("a", { x: { trigger: "step", target: "b" }, y: { trigger: "step", target: "c" } }),
        agent("b"),
        agent("c"),
        agent("d"),
      ];

      const { rootLayout } = computeRootLayout(agents, { a: CONDITIONAL }, PORT);

      expect(rootLayout.get("c")).toEqual({ col: 1, row: 272 });
      expect(rootLayout.get("d")).toEqual({ col: 2, row: 272 });
    });

    it("separates nodes of different gates that would overlap in the same column", () => {
      const agents = [
        routed("g1", { x: { trigger: "step", target: "t1" } }),
        routed("g2", { x: { trigger: "step", target: "t2" } }),
        agent("t1"),
        agent("t2"),
      ];

      const { rootLayout } = computeRootLayout(agents, { g1: CONDITIONAL, g2: CONDITIONAL }, PORT);

      // Each pair would otherwise share a top offset of 0; the second is pushed
      // one card height (208) plus ROW_GAP (64) below the first.
      expect(rootLayout.get("g1")).toEqual({ col: 0, row: 0 });
      expect(rootLayout.get("g2")).toEqual({ col: 0, row: 272 });
      expect(rootLayout.get("t1")).toEqual({ col: 1, row: 0 });
      expect(rootLayout.get("t2")).toEqual({ col: 1, row: 272 });
    });

    it("does not add a node for a route target that is not in the pipeline", () => {
      const agents = [routed("a", { x: { trigger: "step", target: "ghost" } }), agent("b")];

      const { rootLayout } = computeRootLayout(agents, { a: CONDITIONAL }, PORT);

      expect(rootLayout.has("ghost")).toBe(false);
      expect([...rootLayout.keys()].sort()).toEqual(["a", "b"]);
    });
  });

  describe("declared dependencies", () => {
    it("places detached steps by their depends_on chain", () => {
      const agents = [
        agent("a"),
        agent("b", { detached: true, depends_on: ["a"] }),
        agent("c", { detached: true, depends_on: ["b"] }),
      ];

      const { rootLayout } = computeRootLayout(agents, {}, PORT);

      expect(rootLayout.get("a")?.col).toBe(0);
      expect(rootLayout.get("b")?.col).toBe(1);
      expect(rootLayout.get("c")?.col).toBe(2);
    });

    it("leaves a detached step with no dependencies in the first column, stacked below the step it shares it with", () => {
      const { rootLayout } = computeRootLayout([agent("a"), agent("b", { detached: true })], {}, PORT);

      expect(rootLayout.get("a")).toEqual({ col: 0, row: 0 });
      expect(rootLayout.get("b")).toEqual({ col: 0, row: 272 });
    });

    it("ignores self, unknown and empty dependencies", () => {
      const agents = [
        agent("a"),
        agent("b", { detached: true, depends_on: ["b", "nobody", ""] }),
      ];

      const { rootLayout } = computeRootLayout(agents, {}, PORT);

      // No usable dependency: b stays in column 0 (below a) instead of moving right.
      expect(rootLayout.get("b")).toEqual({ col: 0, row: 272 });
    });

    it("does not change a column when the dependency repeats an existing chain edge", () => {
      const agents = [agent("a"), agent("b", { depends_on: ["a"] })];

      const { rootLayout } = computeRootLayout(agents, {}, PORT);

      expect(rootLayout.get("b")).toEqual({ col: 1, row: 0 });
    });

    it("terminates on circular dependencies and still places every step", () => {
      const agents = [
        agent("a", { detached: true, depends_on: ["b"] }),
        agent("b", { detached: true, depends_on: ["a"] }),
      ];

      const { rootLayout } = computeRootLayout(agents, {}, PORT);

      expect(rootLayout.size).toBe(2);
      for (const slot of rootLayout.values()) {
        expect(Number.isInteger(slot.col)).toBe(true);
        expect(slot.col).toBeGreaterThanOrEqual(0);
      }
    });
  });
});
