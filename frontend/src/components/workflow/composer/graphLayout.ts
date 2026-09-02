/**
 * Graph layout algorithm for the canvas composer (Sugiyama layering).
 * Pure function that computes root agent positions (column/row assignments)
 * and fan member positions (external workflow nodes, route targets).
 */

import type { AgentDef } from "@/types/index";
import type { SelectionsMap } from "../AgentsPopup";
import { ROOT_H_EST } from "./treeLayout";

// Constants (mirrored from CanvasView.tsx to avoid duplication)
export const NODE_W = 260;
export const NODE_GAP = 96;
export const NODE_Y = 240;
export const START_X = 138; // BRIEF_X (20) + BRIEF_W (118) + NODE_GAP (96) - but use constant value, not computed
export const EXTERNAL_NODE_H = 58;
export const ROW_GAP = 64; // clear air between two stacked nodes' bounding boxes

export function computeRootLayout(
  pipelineAgents: AgentDef[],
  selections: SelectionsMap,
  rowPortOffset: number,
): {
  rootLayout: Map<string, { col: number; row: number }>;
  workflowSlots: Map<string, { col: number; row: number }>;
} {
  const layout = new Map<string, { col: number; row: number }>();
  // Slots for `trigger:"workflow"` outcomes, keyed `${sourceId}::${outcomeKey}`.
  // They are NOT agents — the target runs as its own WorkflowRun — so they
  // cannot live in `layout` alongside real steps. They do occupy a row in
  // their source's fan though, so R2 allocates for both kinds together;
  // otherwise a step branch and a workflow branch would be handed the same
  // row and render on top of each other.
  const wfSlots = new Map<string, { col: number; row: number }>();
  const order = new Map(pipelineAgents.map((a, i) => [a.id, i]));
  const cardH = rowPortOffset * 2;

  // Sugiyama phase 1 + 2: Cycle removal and layer assignment by topological rank.
  // Build a directed graph of parent → child edges (both chain and fan).
  const inEdges = new Map<string, Set<string>>(); // id → { predecessors }
  const outEdges = new Map<string, Set<string>>(); // id → { successors }
  const allNodeIds = new Set<string>();

  for (const agent of pipelineAgents) {
    allNodeIds.add(agent.id);
    if (!inEdges.has(agent.id)) inEdges.set(agent.id, new Set());
    if (!outEdges.has(agent.id)) outEdges.set(agent.id, new Set());
  }

  // Add chain edges — ONLY where one actually exists.
  //
  // Array adjacency is NOT an edge. The steps array is storage order, not graph
  // shape: with [intake, triage, quick-fix, done-simple, analyze, depth, ...],
  // `done-simple -> analyze` does not exist — `analyze` is a route target of
  // `triage`. Adding an edge between every consecutive pair fabricated one long
  // spine, which forced rank to increase monotonically along the array and
  // reproduced exactly the "column = array index" behaviour Sugiyama phase 2
  // exists to eliminate: sibling branches marched rightward end-to-end instead
  // of sharing a column (ISS-175).
  //
  // This mirrors CanvasView's `hasChainEdge` predicate — the same three reasons
  // a blue chain edge is not DRAWN are the reasons it does not EXIST for
  // ranking, so the drawing and the layer assignment agree by construction.
  const agentById = new Map(pipelineAgents.map((a) => [a.id, a]));
  const branchesAway = (id: string) =>
    (selections[id]?.gates ?? []).includes("conditional") &&
    Object.keys(agentById.get(id)?.route?.outcomes ?? {}).length > 0;
  // Forward step targets only — a BACKWARD (loop) target is entered normally on
  // the first pass and keeps its ordinary chain edge (see ADR-0025 / FIX-297).
  const forwardRouteTargets = new Set<string>();
  for (const agent of pipelineAgents) {
    if (!(selections[agent.id]?.gates ?? []).includes("conditional")) continue;
    const srcOrder = order.get(agent.id) ?? -1;
    for (const o of Object.values(agent.route?.outcomes ?? {})) {
      if (o.trigger !== "step" || !o.target) continue;
      if ((order.get(o.target) ?? -1) > srcOrder) forwardRouteTargets.add(o.target);
    }
  }
  const hasChainEdge = (i: number): boolean => {
    if (i === 0) return true; // Brief → first node always chains
    if (pipelineAgents[i]!.detached) return false;
    if (branchesAway(pipelineAgents[i - 1]!.id)) return false;
    return !forwardRouteTargets.has(pipelineAgents[i]!.id);
  };

  for (let i = 1; i < pipelineAgents.length; i++) {
    if (!hasChainEdge(i)) continue;
    const from = pipelineAgents[i - 1]!.id;
    const to = pipelineAgents[i]!.id;
    outEdges.get(from)!.add(to);
    inEdges.get(to)!.add(from);
  }

  // Add conditional routing edges (fan edges, both forward and backward)
  const backEdges = new Set<string>(); // track edges to reverse: "from::to"
  for (const agent of pipelineAgents) {
    for (const [, outcome] of Object.entries(agent.route?.outcomes ?? {})) {
      if (!outcome.target || outcome.trigger !== "step") continue;
      const from = agent.id;
      const to = outcome.target;
      const sourceOrder = order.get(from) ?? 0;
      const targetOrder = order.get(to) ?? -1;

      // If backward (targetOrder <= sourceOrder), mark as back-edge for reversal.
      if (targetOrder <= sourceOrder) {
        backEdges.add(`${from}::${to}`);
        // Add reversed edge for topological sort
        if (!inEdges.has(to)) {
          inEdges.set(to, new Set());
          outEdges.set(to, new Set());
          allNodeIds.add(to);
        }
        if (!inEdges.has(from)) {
          inEdges.set(from, new Set());
          outEdges.set(from, new Set());
          allNodeIds.add(from);
        }
        outEdges.get(to)!.add(from);
        inEdges.get(from)!.add(to);
      } else {
        // Forward edge: add normally
        if (!inEdges.has(to)) {
          inEdges.set(to, new Set());
          outEdges.set(to, new Set());
          allNodeIds.add(to);
        }
        if (!inEdges.has(from)) {
          inEdges.set(from, new Set());
          outEdges.set(from, new Set());
          allNodeIds.add(from);
        }
        outEdges.get(from)!.add(to);
        inEdges.get(to)!.add(from);
      }
    }
  }

  // ISS-178 — Add declared `depends_on` as a third edge source.
  //
  // Canvas-authored workflows keep array order aligned with the chain so
  // `depends_on` and adjacency agree. API-authored or hand-written YAML steps
  // can have a `depends_on` that names a predecessor NOT adjacent in the array
  // and NOT a route outcome target — the only structural edge is the explicit
  // declaration. Without this pass such a step received no incoming edge,
  // ranked at column 0 next to `start`, and rendered in the wrong column.
  //
  // ADR-0004: a declared `depends_on` OVERRIDES the inferred DAG where the two
  // disagree, so these edges carry the same weight as chain/route edges.
  //
  // Normalise the `agent:instance` form to the node id graphLayout uses
  // (custom-agent steps use instance_id as their AgentDef.id, which is also
  // what agentsToManifestSteps writes into depends_on entries via CUSTOM_AGENT_PREFIX).
  // Built-in ids are already bare strings matching AgentDef.id directly.
  for (const agent of pipelineAgents) {
    if (!agent.depends_on?.length) continue;
    for (const depId of agent.depends_on) {
      if (!depId) continue;
      const from = depId;
      const to = agent.id;
      // Skip self-loops and edges already established by the chain/route passes.
      if (from === to) continue;
      if (!allNodeIds.has(from) || !allNodeIds.has(to)) continue;
      if (inEdges.get(to)?.has(from)) continue; // already present
      outEdges.get(from)?.add(to);
      inEdges.get(to)?.add(from);
    }
  }

  // Compute topological rank for each node (longest-path from start).
  // Nodes in the same graph depth get the same column.
  const rank = new Map<string, number>();
  rank.set("__brief__", 0);

  const visited = new Set<string>();
  const compute = (id: string): number => {
    if (rank.has(id)) return rank.get(id)!;
    if (visited.has(id)) return 0; // Cycle detected; assume rank 0
    visited.add(id);

    let maxPredRank = -1;
    for (const pred of inEdges.get(id) ?? []) {
      maxPredRank = Math.max(maxPredRank, compute(pred));
    }

    const r = maxPredRank + 1;
    rank.set(id, r);
    return r;
  };

  // Compute rank for all nodes
  for (const id of allNodeIds) {
    compute(id);
  }
  for (const agent of pipelineAgents) {
    if (!rank.has(agent.id)) rank.set(agent.id, 0);
  }

  // Column = topological rank, directly (Sugiyama phase 2). No adjustment.
  //
  // A `hasOutcomesAt` pass used to bump every node sharing a rank with some
  // gate's outcomes, to stop successors landing on top of a fan. That was
  // compensation for the fabricated array-adjacency edges above: with a real
  // edge set a gate's outcomes ARE its rank+1, so the fan and any other node at
  // that rank are genuinely siblings and the fan geometry separates them. The
  // bump only pushed two nodes of equal graph depth into different columns —
  // `done-simple` and `depth` both sat at depth 3 yet rendered a column apart
  // (ISS-175). Removed with the edge fix; do not reintroduce it.
  for (const agent of pipelineAgents) {
    layout.set(agent.id, { col: rank.get(agent.id) ?? 0, row: 0 });
  }

  // Helper: get node height for size-aware separation
  // MEASURED height, not the ROOT_H_EST estimate. `cardH` is `rowPortOffset * 2`,
  // and `rowPortOffset` is the tallest DOM-measured half-height of any root card
  // (CanvasView's nodeCenterY effect); CanvasView then pushes that same height
  // onto every root card as a min-height, so all root cards really are `cardH`
  // tall. ROOT_H_EST is only an ESTIMATE — treeLayout.ts calls it "approximate
  // root card height ... exact height varies with content", and a card grows with
  // a ROUTE row or extra chips. Using it here under-separated every fan by
  // (cardH - ROOT_H_EST): real cards measured 243 against an assumed 176, so a
  // 5-wide fan produced a 240 pitch where 307 was needed and the members
  // overlapped. Fans only looked correct on shapes whose cards happened to render
  // short enough. Fall back to the estimate only before the first measurement.
  const getNodeHeight = (id: string): number => {
    const ag = pipelineAgents.find((a) => a.id === id);
    return ag ? Math.max(cardH, ROOT_H_EST) : EXTERNAL_NODE_H;
  };

  // Fan members get an explicit row below; everything else inherits from its
  // chain predecessor afterwards.
  const placedByFan = new Set<string>();

  // PASS 2: Sugiyama phase 3 & 4 — ordering and coordinate assignment within layers.
  // Collect outcome members and place with size-aware separation (spec §4).
  //
  // Walk in RANK order, not array order. A gate's fan is centred on the gate's
  // OWN row, so that row must already be final when the fan is placed — and a
  // gate's row may itself come from inheriting its chain predecessor's lane
  // (below). Iterating the array instead placed every fan against the `row: 0`
  // default, so all fans piled onto one lane regardless of which branch their
  // gate sat in. Rank order guarantees a predecessor (lower rank) is resolved
  // before any successor (higher rank) reads it.
  const byRank = [...pipelineAgents].sort(
    (a, b) => (rank.get(a.id) ?? 0) - (rank.get(b.id) ?? 0),
  );
  for (const agent of byRank) {
    // Inherit the branch lane first — degenerate median alignment: with a single
    // neighbour, the median IS that neighbour.
    if (!placedByFan.has(agent.id)) {
      const idx = order.get(agent.id) ?? 0;
      if (idx > 0 && hasChainEdge(idx)) {
        const predRow = layout.get(pipelineAgents[idx - 1]!.id)?.row;
        const slot = layout.get(agent.id);
        if (predRow !== undefined && slot) slot.row = predRow;
      }
    }
    const me = layout.get(agent.id)!;
    if (!(selections[agent.id]?.gates ?? []).includes("conditional")) continue;
    const sourceOrder = order.get(agent.id) ?? 0;

    // Collect members in declared order (preserves I6: declared outcome order)
    const members: { kind: string; id: string; height: number }[] = [];
    const addedToFan = new Set<string>();

    for (const [outcomeKey, o] of Object.entries(agent.route?.outcomes ?? {})) {
      if (!o.target) continue;
      if (o.trigger === "workflow") {
        members.push({ kind: "workflow", id: `${agent.id}::${outcomeKey}`, height: EXTERNAL_NODE_H });
      } else if ((order.get(o.target) ?? -1) > sourceOrder && !addedToFan.has(o.target)) {
        // Forward step targets only; backward targets keep their existing positions
        members.push({ kind: "step", id: o.target, height: getNodeHeight(o.target) });
        addedToFan.add(o.target);
      }
    }

    if (members.length === 0) continue;

    // Place members with size-aware separation (spec §4: sep(u,v) = (h(u)+h(v))/2 + ROW_GAP)
    // Compute row positions: place symmetrically around gate's center
    const targetCol = me.col + 1;

    // Total height needed for all members
    let totalH = 0;
    for (let i = 0; i < members.length; i++) {
      totalH += members[i]!.height;
      if (i > 0) totalH += ROW_GAP;
    }

    // Place members symmetrically (centered on gate's center)
    // Gate's center y = NODE_Y + me.row + ROOT_H_EST/2
    // Members stack vertically with size-aware gaps
    // `y` walks the TOP edge of each member, starting at the top of a stack
    // centred on the gate's centre. `slot.row` IS a top offset everywhere it
    // is consumed (`NODE_Y + slot.row` at the root-node and external-node
    // sites), so a member's row is `y` directly — adding height/2 here wrote a
    // CENTRE into a field read as a TOP, pushing every member down by its own
    // half-height. Because the members have DIFFERENT heights (a ~176px step
    // card beside a 58px external node) they were pushed down by different
    // amounts, which collapsed the gap between them and produced the overlap.
    // Gate centre uses the same MEASURED card height as getNodeHeight — mixing
    // the estimate here with a measured height there would de-centre every fan.
    let y = me.row + getNodeHeight(agent.id) / 2 - totalH / 2; // top of the stack

    for (const member of members) {
      const row = y;
      const slot = { col: targetCol, row };
      if (member.kind === "step") {
        layout.set(member.id, slot);
        placedByFan.add(member.id);
      } else wfSlots.set(member.id, slot);

      // Move to next member's center
      y += member.height + ROW_GAP;
    }
  }

  // Sugiyama phase 4 — COMPACTION within each layer.
  //
  // Fans are placed per-gate, each centred on its own gate. That guarantees no
  // collision INSIDE one fan, but says nothing about two different gates whose
  // fans land in the SAME column: with gates at rows 477 and 602, their fans
  // spanned 449..545 and 540..664 and overlapped in the middle. Separation is a
  // property of the LAYER, not of one parent's fan.
  //
  // So sweep each column top-to-bottom and enforce the separation constraint
  // between vertically adjacent occupants, whatever their parent. `row` is a TOP
  // offset, so for tops the constraint is simply
  //     top(i) >= top(i-1) + height(i-1) + ROW_GAP
  // which is the `sep(u,v) = (h(u)+h(v))/2 + ROW_GAP` rule of ADR-0025 restated
  // for top edges. Only ever pushes DOWN, in one ordered pass — this is not a
  // nudge-until-no-collision loop, which is a recorded anti-pattern here.
  {
    type Occupant = { col: number; row: number; h: number };
    const occupants: Occupant[] = [];
    for (const [id, slot] of layout) occupants.push({ ...slot, h: getNodeHeight(id) } as Occupant & { col: number });
    for (const [, slot] of wfSlots) occupants.push({ ...slot, h: EXTERNAL_NODE_H } as Occupant);
    // Keep references so a mutation lands back on the real slot objects.
    const refs = new Map<Occupant, { col: number; row: number }>();
    let k = 0;
    for (const [, slot] of layout) refs.set(occupants[k++]!, slot);
    for (const [, slot] of wfSlots) refs.set(occupants[k++]!, slot);

    const byCol = new Map<number, Occupant[]>();
    for (const o of occupants) {
      if (!byCol.has(o.col)) byCol.set(o.col, []);
      byCol.get(o.col)!.push(o);
    }
    for (const group of byCol.values()) {
      group.sort((a, b) => a.row - b.row);
      for (let i = 1; i < group.length; i++) {
        const prev = group[i - 1]!;
        const cur = group[i]!;
        const minTop = prev.row + prev.h + ROW_GAP;
        if (cur.row < minTop) {
          cur.row = minTop;
          const ref = refs.get(cur);
          if (ref) ref.row = minTop;
        }
      }
    }
  }

  // Normalize (§5): translate entire graph if any y would be negative.
  // This is done GLOBALLY after all nodes are laid out, not per-gate.
  let minY = 0;
  for (const slot of layout.values()) {
    minY = Math.min(minY, slot.row);
  }
  for (const slot of wfSlots.values()) {
    minY = Math.min(minY, slot.row);
  }
  if (minY < 0) {
    const shift = -minY;
    for (const slot of layout.values()) {
      slot.row += shift;
    }
    for (const slot of wfSlots.values()) {
      slot.row += shift;
    }
  }

  return { rootLayout: layout, workflowSlots: wfSlots };
}
