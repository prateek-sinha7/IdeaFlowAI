import type { AgentDef } from "@/types/index";

// ── Sub-agent tree layout — a real two-pass algorithm (bottom-up subtree
//    width, top-down centering), replacing the old CSS-flexbox-left-aligned
//    ChildrenRow. This is the SAME idea React Flow's Dagre integration used
//    (measure-then-position), reimplemented by hand so the canvas stays
//    dependency-free — see the beta-canvas retrospective for why this,
//    not a CSS margin hack, is the correct way to center a parent over a
//    subtree wider than itself. ─────────────────────────────────────────
export const CHILD_W = 200; // narrower than the root card (260) — matches CanvasNode's old constant
const ROOT_H_EST = 176; // approximate root card height, for row spacing only (exact height varies with content)
const CHILD_H_EST = 156; // approximate nested card height
const CHILD_GAP = 24; // horizontal gap between sibling cards at the same depth
const ROW_GAP = 56; // vertical gap between a row and the next row down

export interface FlatPos {
  x: number; // CENTER x, absolute stage coordinates
  y: number; // TOP y, absolute stage coordinates
  width: number;
  depth: number; // 1 = direct child of a root agent, 2 = grandchild, ...
}

function cardWidthForDepth(depth: number): number {
  return depth === 0 ? 0 : CHILD_W; // depth 0 (the root itself) isn't sized here — see layoutChildren
}
function cardHeightForDepth(depth: number): number {
  return depth === 0 ? ROOT_H_EST : CHILD_H_EST;
}

interface SubtreeResult {
  width: number;
  /** Positions relative to this subtree's own local left edge (x=0). */
  positions: Map<string, { x: number; y: number; depth: number }>;
}

function layoutSubtree(agent: AgentDef, depth: number): SubtreeResult {
  const ownW = depth === 0 ? Math.max(CHILD_W, 1) : cardWidthForDepth(depth);
  const children = agent.children ?? [];
  if (children.length === 0) {
    return { width: ownW, positions: new Map([[agent.id, { x: ownW / 2, y: 0, depth }]]) };
  }

  const childResults = children.map((c) => layoutSubtree(c, depth + 1));
  const childrenTotalWidth =
    childResults.reduce((sum, r) => sum + r.width, 0) + CHILD_GAP * (children.length - 1);
  const subtreeWidth = Math.max(ownW, childrenTotalWidth);
  const childrenStartX = (subtreeWidth - childrenTotalWidth) / 2;

  const positions = new Map<string, { x: number; y: number; depth: number }>();
  positions.set(agent.id, { x: subtreeWidth / 2, y: 0, depth });

  const rowY = cardHeightForDepth(depth) + ROW_GAP;
  let cursor = childrenStartX;
  children.forEach((child, i) => {
    const result = childResults[i];
    for (const [id, pos] of result.positions) {
      positions.set(id, { x: cursor + pos.x, y: rowY + pos.y, depth: pos.depth });
    }
    cursor += result.width + CHILD_GAP;
  });

  return { width: subtreeWidth, positions };
}

/**
 * Absolute {x: center, y: top, width, depth} for every DESCENDANT of
 * `agent` (the root agent's OWN position is owned by the main chain layout,
 * not this — never included here), anchored so the subtree's balance point
 * lines up under `rootCenterX`/`rootTopY` (the root card's true center-x and
 * top-y, e.g. from a DOM measurement, so the trunk connector is exact).
 */
export function layoutChildren(
  agent: AgentDef,
  rootCenterX: number,
  rootTopY: number,
): Map<string, FlatPos> {
  const result = layoutSubtree(agent, 0);
  const offsetX = rootCenterX - result.width / 2;
  const positions = new Map<string, FlatPos>();
  for (const [id, pos] of result.positions) {
    if (id === agent.id) continue;
    positions.set(id, {
      x: pos.x + offsetX,
      y: pos.y + rootTopY,
      width: cardWidthForDepth(pos.depth),
      depth: pos.depth,
    });
  }
  return positions;
}

export interface TreeEdge {
  parentId: string;
  childId: string;
}

/** Every parent→child pair in `agent`'s subtree (not including a root-level
 *  main-chain edge — that's handled separately by CanvasView). */
export function collectTreeEdges(agent: AgentDef): TreeEdge[] {
  const edges: TreeEdge[] = [];
  const walk = (a: AgentDef) => {
    for (const child of a.children ?? []) {
      edges.push({ parentId: a.id, childId: child.id });
      walk(child);
    }
  };
  walk(agent);
  return edges;
}
