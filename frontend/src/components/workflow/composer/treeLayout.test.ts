import { describe, expect, it } from "vitest";
import type { AgentDef } from "@/types/index";
import {
  CHILD_H_EST,
  CHILD_W,
  ROOT_H_EST,
  TREE_ROW_GAP,
  collectTreeEdges,
  layoutChildren,
} from "./treeLayout";

function agent(id: string, children?: AgentDef[]): AgentDef {
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
    ...(children ? { children } : {}),
  };
}

const CHILD_GAP = 24; // horizontal gap between sibling cards (private constant in treeLayout.ts)

describe("layoutChildren", () => {
  it("returns nothing for an agent without children", () => {
    expect(layoutChildren(agent("root"), 500, 100).size).toBe(0);
  });

  it("centres a single child under the root, one row below", () => {
    const positions = layoutChildren(agent("root", [agent("a")]), 500, 100);

    expect(positions.size).toBe(1);
    expect(positions.get("a")).toEqual({
      x: 500,
      y: 100 + ROOT_H_EST + TREE_ROW_GAP,
      width: CHILD_W,
      depth: 1,
    });
  });

  it("spreads siblings symmetrically around the root's centre", () => {
    const positions = layoutChildren(agent("root", [agent("a"), agent("b")]), 500, 0);

    // Two cards plus one gap: total 2*200 + 24 = 424, starting at 500 - 212.
    const left = positions.get("a")!;
    const right = positions.get("b")!;
    expect(left.x).toBe(500 - 212 + CHILD_W / 2);
    expect(right.x).toBe(left.x + CHILD_W + CHILD_GAP);
    expect(left.y).toBe(right.y);
  });

  it("is not the root's own position that is returned", () => {
    const positions = layoutChildren(agent("root", [agent("a")]), 0, 0);

    expect(positions.has("root")).toBe(false);
  });

  it("stacks grandchildren a nested row below their parent and centres them on it", () => {
    const tree = agent("root", [agent("a", [agent("g1"), agent("g2")])]);

    const positions = layoutChildren(tree, 500, 0);

    const a = positions.get("a")!;
    const g1 = positions.get("g1")!;
    const g2 = positions.get("g2")!;
    expect(a.depth).toBe(1);
    expect(g1.depth).toBe(2);
    expect(g2.depth).toBe(2);
    expect(g1.y).toBe(a.y + CHILD_H_EST + TREE_ROW_GAP);
    expect(g2.y).toBe(g1.y);
    expect((g1.x + g2.x) / 2).toBe(a.x);
  });

  it("keeps a narrow parent centred over a wider set of children", () => {
    const tree = agent("root", [agent("a", [agent("g1"), agent("g2"), agent("g3")]), agent("b")]);

    const positions = layoutChildren(tree, 0, 0);

    // a's subtree is three cards wide (3*200 + 2*24 = 648) so b sits to its right
    // with one gap between the subtrees.
    const g1 = positions.get("g1")!;
    const g3 = positions.get("g3")!;
    const a = positions.get("a")!;
    const b = positions.get("b")!;
    expect(a.x).toBe((g1.x + g3.x) / 2);
    expect(b.x - a.x).toBe(648 / 2 + CHILD_GAP + CHILD_W / 2);
  });
});

describe("collectTreeEdges", () => {
  it("returns no edges for a leaf", () => {
    expect(collectTreeEdges(agent("root"))).toEqual([]);
  });

  it("returns an edge for every parent-child pair, depth first and in declared order", () => {
    const tree = agent("root", [agent("a", [agent("a1")]), agent("b")]);

    expect(collectTreeEdges(tree)).toEqual([
      { parentId: "root", childId: "a" },
      { parentId: "a", childId: "a1" },
      { parentId: "root", childId: "b" },
    ]);
  });
});
