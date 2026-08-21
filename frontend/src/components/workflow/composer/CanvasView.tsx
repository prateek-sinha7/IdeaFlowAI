"use client";

import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Plus, Minus, Maximize, Globe, Info, LayoutGrid } from "lucide-react";
import {
  CanvasNode,
  ExternalWorkflowNode,
  EXTERNAL_NODE_W,
  useWorkflowPickerOptions,
} from "./CanvasNode";
import { CanvasConfigRail } from "./CanvasConfigRail";
import {
  CHILD_W,
  CHILD_H_EST,
  ROOT_H_EST,
  TREE_ROW_GAP,
  collectTreeEdges,
  layoutChildren,
  type FlatPos,
} from "./treeLayout";
import { useAgentCapabilities, type SelectionsMap, type StepSelection } from "../AgentsPopup";
import { BriefAttachBox, type BriefAttachments } from "../IdeaInputPage";
import type {
  AgentDef,
  SubagentStrategy,
  WorkflowCapabilities,
  WorkflowRunConfig,
  WorkflowType,
} from "@/types/index";
import {
  addChildInTree,
  collectAgentIds,
  findAgentInTree,
  generateInstanceId,
  mapAgentInTree,
  removeAgentInTree,
} from "@/store/api/userWorkflows";

// ── Hand-rolled layout constants (px, shared by the nodes + the SVG edge layer;
//    both live in the same `.stage` coordinate space so they align — D-04). ──────
// 260, not 220: longer agent names (e.g. "Backlog Architecture Agent") were
// truncating mid-word against 220 even at the title's already-small 13px —
// widening the card reads better than shrinking the text further. Sub-agent
// cards use the narrower CHILD_W from treeLayout.ts.
const NODE_W = 260;
// Wide enough that the edge reads as a clear "--+-->" (card edge, gap, the
// insert "+", gap, arrowhead, gap, next card) instead of everything crammed
// against the card borders.
const NODE_GAP = 96;
const NODE_Y = 240;
const PORT_Y = 306; // vertical centre of the node ports (and every edge)
const BRIEF_X = 20;
const BRIEF_W = 118;
// Same rhythm as NODE_GAP — the Brief→first-node gap used to be a much
// tighter, unrelated 32px constant, which read as cramped next to the wider
// spacing between agent nodes.
const START_X = BRIEF_X + BRIEF_W + NODE_GAP;
const ARROW_INSET = 8; // stop the edge just short of the target port
// Rendered height of an ExternalWorkflowNode (eyebrow row + name row + padding).
// A constant, not a measurement: the node has fixed content, so there is nothing
// to measure and no reason to add another layout-effect feedback path.
const EXTERNAL_NODE_H = 58;
const DRAG_THRESHOLD = 4; // px of mouse movement before a card-mousedown becomes a drag, not a click

// ── Dot-grid ────────────────────────────────────────────────────────────────
// The background lattice, in CANVAS units. It scales with zoom so it stays a
// spatial reference rather than a fixed screen texture.
const GRID_UNIT = 22;
// …but only within a legible band. Zoom runs 0.1–1.5 here, and a naive
// GRID_UNIT * zoom is 2.2px at the low end — a solid grey wash, not a grid. So
// double the lattice until it clears GRID_MIN_PX, the same power-of-two
// level-of-detail step an infinite canvas normally uses. Coarser grid, same
// alignment: every dot of the zoomed-out lattice is still a dot of the
// zoomed-in one.
const GRID_MIN_PX = 12;
/** On-screen dot spacing for a given zoom, LOD-stepped. */
function gridSpacingFor(zoom: number): number {
  let spacing = GRID_UNIT * zoom;
  // Bounded loop: `spacing` at least doubles each pass, so it clears the
  // threshold in ~log2 steps even for a pathological zoom near 0.
  while (spacing > 0 && spacing < GRID_MIN_PX) spacing *= 2;
  return spacing || GRID_UNIT;
}

/** Sentinel id for the Brief "node" — not a real agent, so it never collides
 *  with a minted instance id (those are always lowercase-hyphen shaped). */
const BRIEF_ID = "__brief__";

const nodeLeft = (i: number) => START_X + i * (NODE_W + NODE_GAP);

/** A smooth horizontal cubic bezier between two points on the same baseline
 *  (the main left→right chain). */
function edgePath(sx: number, sy: number, ex: number, ey: number): string {
  const dx = Math.max(20, (ex - sx) * 0.5);
  return `M ${sx} ${sy} C ${sx + dx} ${sy}, ${ex - dx} ${ey}, ${ex} ${ey}`;
}

/** A smooth VERTICAL cubic bezier (parent bottom → child top) — the
 *  sub-agent tree's connector curve, replacing the old 90°-elbow SVG path. */
function verticalEdgePath(sx: number, sy: number, ex: number, ey: number): string {
  const dy = Math.max(20, (ey - sy) * 0.5);
  return `M ${sx} ${sy} C ${sx} ${sy + dy}, ${ex} ${ey - dy}, ${ex} ${ey}`;
}

/** Loop (back-edge) path: TOP of the source, up and over, down into the TOP of
 *  the target. Vertical tangents at both ends, so it leaves and arrives
 *  straight up/down and the arrowhead points down into the target. `lift` is
 *  how far above the higher of the two tops the arc crests — staggered per loop
 *  so two loop-backs over the same span don't sit on each other. */
function loopArcPath(sx: number, sy: number, ex: number, ey: number, lift: number): string {
  const crest = Math.min(sy, ey) - lift;
  return `M ${sx} ${sy} C ${sx} ${crest}, ${ex} ${crest}, ${ex} ${ey}`;
}

function isDescendant(node: AgentDef, targetId: string): boolean {
  for (const child of node.children ?? []) {
    if (child.id === targetId) return true;
    if (isDescendant(child, targetId)) return true;
  }
  return false;
}

/** Re-parents `id` (with its whole subtree, wherever it currently lives) to
 *  become a child of `newParentId` — or, if `newParentId` is the Brief
 *  sentinel, DETACHES it back to a top-level root step. Powers the canvas's
 *  drag-a-connector-to-a-different-node gesture. No-ops on a self-parent or
 *  a cycle (dropping a node onto its own descendant). */
function moveAgentInTree(agents: AgentDef[], id: string, newParentId: string): AgentDef[] {
  if (id === newParentId) return agents;
  const node = findAgentInTree(agents, id);
  if (!node) return agents;
  if (isDescendant(node, newParentId)) return agents;
  const without = removeAgentInTree(agents, id);
  if (newParentId === BRIEF_ID) return [...without, node];
  return addChildInTree(without, newParentId, node);
}

function flattenDescendants(agent: AgentDef): AgentDef[] {
  const out: AgentDef[] = [];
  const walk = (a: AgentDef) => {
    for (const child of a.children ?? []) {
      out.push(child);
      walk(child);
    }
  };
  walk(agent);
  return out;
}

/**
 * 41-05 — the Composer's CANVAS view: a HAND-ROLLED node-graph visual designer
 * (D-04 / CMPUI-03), design-matched to `composer-canvas-proposal.html` (ND-AJ —
 * a design-match gate, not a `.dc.html` mock-fidelity gate). No graph/dnd
 * library — hand-rolled SVG (bezier edges) + absolute-positioned divs.
 *
 * A left→right root chain plus a balanced sub-agent tree hanging below any
 * node with children (laid out by treeLayout.ts). Nodes are freely draggable
 * (session-only, see "Auto-arrange"); dragging a node's incoming connector
 * re-parents it. Selecting a node binds it to the right config rail via the
 * shared `SelectionsMap`. `+` insert and remove call the SAME add/remove path
 * as the Simple view — both bind to the same shared data model.
 */
export function CanvasView({
  pipelineAgents,
  selections,
  pipelineType,
  onSelection,
  onRemoveAgent,
  onAddAgent,
  canAddMore,
  declaredCapabilities,
  onTreeChange,
  onRequestAddSubAgent,
  capabilities,
  onCapabilitiesChange,
  runConfig,
  onRunConfigChange,
  briefText,
  onBriefTextChange,
  briefFocusSignal,
  resetLayoutSignal,
  briefAttachments,
}: {
  pipelineAgents: AgentDef[];
  selections: SelectionsMap;
  pipelineType: WorkflowType;
  onSelection: (agentId: string, sel: StepSelection | undefined) => void;
  onRemoveAgent: (id: string) => void;
  /** Opens the add-agent picker. `insertBeforeId` (from a mid-chain "+")
   *  requests the new node land right before that root agent instead of
   *  appending at the chain end. */
  onAddAgent: (insertBeforeId?: string) => void;
  canAddMore: boolean;
  declaredCapabilities: string[];
  /** Spec 012 (R-35/T30) — reports the node tree after an add-sub-agent,
   *  rename, skills, prompt, or strategy edit. Wired to the parent's
   *  `setPipelineAgents` so every canvas edit round-trips through the SAME
   *  state Save persists. */
  onTreeChange?: (agents: AgentDef[]) => void;
  /** Opens the agent library in "add as sub-agent of <parentId>" mode. When
   *  omitted the "+ Sub-agent" affordance mints a blank custom node instead. */
  onRequestAddSubAgent?: (parentId: string) => void;
  /** Spec 012 (R-37) — workflow-level capability switches (internet toggle). */
  capabilities?: WorkflowCapabilities;
  onCapabilitiesChange?: (next: WorkflowCapabilities) => void;
  /** Workflow-level run settings (deliverable/planner/clarify) — same
   *  always-visible, workflow-scoped surface as `capabilities` above. */
  runConfig?: WorkflowRunConfig;
  onRunConfigChange?: (next: WorkflowRunConfig) => void;
  /** The run's "what to build" instruction — owned by ComposerPage (Run once
   *  reads it directly), rendered here as the Brief node's rail box so it's
   *  always visible instead of living behind a modal. */
  briefText: string;
  onBriefTextChange: (v: string) => void;
  /** Bumped by ComposerPage's Run button every time it's clicked while
   *  `briefText` is too short — selects the Brief node and focuses its box. */
  briefFocusSignal?: number;
  /** Bumped by the parent's Save button — clears free-drag overrides at the
   *  moment of saving. Position is NEVER persisted anywhere in this app, so
   *  this just snaps the view back to the clean auto-layout that reopening
   *  the workflow would show anyway. */
  resetLayoutSignal?: number;
  /** Same attach/PDF-extract state the Simple view's Brief card uses (KAN-91 /
   *  Image-input Wave 2) — passed in (not created locally) so switching
   *  between Simple ⇄ Canvas shows the SAME attached files, not two
   *  independent sets. */
  briefAttachments: BriefAttachments;
}) {
  // The Brief is selected by default — including the moment an EXISTING
  // workflow's canvas mounts — so opening a saved workflow always starts by
  // showing "what to build" rather than an arbitrary first agent.
  // Lifted here (not called per-node) so every CanvasNode's model pill reads
  // the SAME fetched catalog instead of each node firing its own
  // `/api/capabilities` request.
  const { modelOptions } = useAgentCapabilities();

  const [selectedId, setSelectedId] = useState<string | null>(BRIEF_ID);
  const [zoom, setZoom] = useState(1);
  // On-screen dot spacing for the canvas background — see gridSpacingFor.
  const gridSpacing = gridSpacingFor(zoom);

  // Names for the external-workflow nodes. `useWorkflowPickerOptions` caches
  // its fetch in a module-scoped promise shared with CanvasConfigRail's copy,
  // so calling it here costs one extra subscription, not a second request.
  const needsWorkflowNames = pipelineAgents.some((a) =>
    Object.values(a.route?.outcomes ?? {}).some((o) => o.trigger === "workflow" && o.target),
  );
  const { workflows: canvasWorkflowOptions } = useWorkflowPickerOptions(needsWorkflowNames);
  const workflowNameById = useMemo(
    () => new Map((canvasWorkflowOptions ?? []).map((w) => [w.id, w.name])),
    [canvasWorkflowOptions],
  );
  const workflowKindById = useMemo(
    () => new Map((canvasWorkflowOptions ?? []).map((w) => [w.id, w.kind])),
    [canvasWorkflowOptions],
  );
  const workflowShortNameById = useMemo(
    () => new Map((canvasWorkflowOptions ?? []).map((w) => [w.id, w.shortName])),
    [canvasWorkflowOptions],
  );
  // Pan offset (screen px), applied ahead of `zoom` in the stage transform —
  // without this the stage was pinned at its layout origin (BRIEF_X/NODE_Y)
  // with no way to reach nodes that scrolled past the viewport edge as the
  // chain grew, other than zooming out to the 40% floor.
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [spacePressed, setSpacePressed] = useState(false);
  const [isPanning, setIsPanning] = useState(false);
  const canvasRef = useRef<HTMLDivElement>(null);
  const stageRef = useRef<HTMLDivElement>(null);
  const panStart = useRef({ x: 0, y: 0, panX: 0, panY: 0 });
  const briefInputRef = useRef<HTMLTextAreaElement>(null);

  // ── Free-drag position overrides — SESSION-ONLY, never persisted (nothing
  //    about position is saved anywhere in this app). Keyed by node id (root
  //    or nested); a node with no entry uses its computed layout position. ──
  const [dragOverrides, setDragOverrides] = useState<Record<string, { x: number; y: number }>>({});
  const dragState = useRef<{
    id: string;
    startClientX: number;
    startClientY: number;
    startX: number;
    startY: number;
    moved: boolean;
  } | null>(null);

  // ── Edge-drag-to-reparent — mousedown on a child's TOP port starts this;
  //    a dashed line follows the cursor to `reparentDrag.x/y` (stage space)
  //    until mouseup, which hit-tests against every node's rendered rect. ──
  // Bumped when a node's Gate chip / Route badge is clicked, so the config rail
  // jumps straight to its Config tab (where the gate + route controls live)
  // instead of leaving the author on Overview.
  const [openConfigSignal, setOpenConfigSignal] = useState(0);
  const openNodeConfig = useCallback((id: string) => {
    setSelectedId(id);
    setOpenConfigSignal((n) => n + 1);
  }, []);

  //    `fromEdge` marks a drag that started by grabbing the drawn parent→child
  //    LINE rather than the child's port. Only that variant treats an
  //    empty-space drop as "detach" (promote the child back to the root chain);
  //    a plain port drag that misses stays a no-op, as it always has.
  const [reparentDrag, setReparentDrag] = useState<{
    childId: string;
    x: number;
    y: number;
    fromEdge?: boolean;
  } | null>(null);

  // The node a live drag is currently over. Drives the drop-target ring, so a
  // connector drag says WHERE it will land instead of leaving you to guess from
  // the ghost line's endpoint.
  const [dropHoverId, setDropHoverId] = useState<string | null>(null);

  // ── Chain-connect drag — offered ONLY while some step is detached. Dragging
  //    from a node's right circle onto an orphan re-attaches it: the orphan
  //    moves to sit immediately after the source in the array and its
  //    `detached` flag clears. Position IS the structural connection here
  //    (`depends_on` is derived from it at serialise time), so "connect A → O"
  //    is exactly "put O straight after A" — no new edge field required.
  const [chainConnectDrag, setChainConnectDrag] = useState<{
    sourceId: string;
    x: number;
    y: number;
  } | null>(null);

  // ComposerPage bumps briefFocusSignal every time Run is clicked while the
  // brief is too short — select the Brief node and put the cursor in its box.
  useEffect(() => {
    if (briefFocusSignal === undefined || briefFocusSignal === 0) return;
    setSelectedId(BRIEF_ID);
    briefInputRef.current?.focus();
  }, [briefFocusSignal]);

  // Save bumps resetLayoutSignal — snap every dragged node back to its
  // computed position.
  useEffect(() => {
    if (resetLayoutSignal === undefined || resetLayoutSignal === 0) return;
    setDragOverrides({});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resetLayoutSignal]);

  // Each root card's TRUE vertical center (NODE_Y + its own rendered height /
  // 2), measured from the DOM rather than assumed — a card grows taller than
  // the base layout the moment it has skill chips or override chips, so a
  // single fixed PORT_Y constant drifts off the actual port dot. No deps
  // array: re-measures after every render/commit, but only writes state (and
  // triggers the one extra re-render) when a value actually changed.
  const [nodeCenterY, setNodeCenterY] = useState<Record<string, number>>({});
  // See the backstop in the measuring effect below.
  const MAX_REMEASURE = 20;
  const remeasureCount = useRef(0);
  // The Brief pill's TOP is DERIVED, not fixed: its center is pinned to
  // node0's center (falling back to a sane default height before the first
  // measurement, or once there are no nodes at all) so the Brief→node0 edge
  // is always perfectly horizontal by construction.
  const [briefHeight, setBriefHeight] = useState(96);
  useLayoutEffect(() => {
    const next: Record<string, number> = {};
    for (const a of pipelineAgents) {
      const el = stageRef.current?.querySelector<HTMLElement>(
        `[data-testid="canvas-node-${a.id}"]`,
      );
      // The card's NATURAL content height, summed from its in-flow children
      // rather than read off the box. `offsetHeight`/`scrollHeight` both report
      // the box AFTER the row-wide `min-height` we push back onto it, so either
      // one makes this a feedback loop: taller box → taller max → taller
      // min-height → taller box, until React's update-depth limit trips.
      // Children give the unconstrained height; absolutely-positioned ones (the
      // port dots, the rename/remove cluster) contribute nothing to flow.
      if (el) {
        let contentBottom = 0;
        for (const child of Array.from(el.children) as HTMLElement[]) {
          if (getComputedStyle(child).position === "absolute") continue;
          contentBottom = Math.max(contentBottom, child.offsetTop + child.offsetHeight);
        }
        const padBottom = parseFloat(getComputedStyle(el).paddingBottom) || 0;
        // Rounded: sub-pixel churn would re-trigger this effect forever.
        next[a.id] = NODE_Y + Math.round((contentBottom + padBottom) / 2);
      }
    }
    const keys = Object.keys(next);
    const changed =
      keys.length !== Object.keys(nodeCenterY).length ||
      keys.some((k) => nodeCenterY[k] !== next[k]);
    // Backstop. This effect has no dependency array, so it runs after every
    // commit and writes state — one bad measurement that never settles takes
    // the whole canvas down with "Maximum update depth exceeded" (which is
    // exactly what a min-height derived from a min-height-constrained read
    // did). The measurement above is now feedback-free, but a layout loop
    // must degrade into a slightly-off diagram, never a crashed page: after
    // MAX_REMEASURE consecutive writes we stop and keep the last values. The
    // counter resets whenever a render settles without a change, so ordinary
    // editing re-measures freely.
    if (changed && remeasureCount.current < MAX_REMEASURE) {
      remeasureCount.current += 1;
      setNodeCenterY(next);
    } else if (!changed) {
      remeasureCount.current = 0;
    }

    const briefEl = stageRef.current?.querySelector<HTMLElement>('[data-testid="canvas-brief"]');
    if (briefEl && briefEl.offsetHeight !== briefHeight) setBriefHeight(briefEl.offsetHeight);
  });
  // ONE shared port height for every root card, not each card's own half-
  // height. Cards are not all the same height (a conditional step carries an
  // extra Route badge, a step with skills carries chips), so per-card centers
  // put neighbouring ports at different heights and every left→right edge came
  // out sloped. Anchoring the whole spine to the tallest card's center makes a
  // same-row chain edge exactly horizontal, which is the point of the
  // arrangement — and `portTop`, below, moves the port dots to match so the
  // line still starts and ends on them.
  const rowPortOffset = useMemo(() => {
    const measured = pipelineAgents
      .map((a) => nodeCenterY[a.id])
      .filter((v): v is number => typeof v === "number");
    return measured.length > 0 ? Math.max(...measured) - NODE_Y : PORT_Y - NODE_Y;
  }, [pipelineAgents, nodeCenterY]);
  const briefCenterY = pipelineAgents.length > 0 ? NODE_Y + rowPortOffset : PORT_Y;
  // Push the row's tallest natural height back onto every root card, so each
  // card's own centre — where its ports sit — lands on the shared edge line.
  const rowCardHeight = rowPortOffset * 2;
  const briefTop = briefCenterY - briefHeight / 2;

  // Space-to-pan (Figma/Miro convention). Guarded against typing targets so
  // holding Space in the rail's rename/prompt fields still types a space.
  useEffect(() => {
    const isTypingTarget = (t: EventTarget | null) => {
      const el = t as HTMLElement | null;
      return !!el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.isContentEditable);
    };
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.code === "Space" && !isTypingTarget(e.target)) {
        e.preventDefault(); // don't also scroll the page
        setSpacePressed(true);
      }
    };
    const onKeyUp = (e: KeyboardEvent) => {
      if (e.code === "Space") setSpacePressed(false);
    };
    window.addEventListener("keydown", onKeyDown);
    window.addEventListener("keyup", onKeyUp);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("keyup", onKeyUp);
    };
  }, []);

  const handleCanvasMouseDown = (e: React.MouseEvent) => {
    // Space+drag anywhere, or a plain middle-mouse drag, pans — never a plain
    // left-click (that still needs to select nodes / hit the + affordances).
    if (!spacePressed && e.button !== 1) return;
    e.preventDefault();
    panStart.current = { x: e.clientX, y: e.clientY, panX: pan.x, panY: pan.y };
    setIsPanning(true);
  };

  // Two-finger trackpad scroll zooms (no ctrl/pinch required), centred on the
  // cursor so the point under it stays put.
  //
  // MUST be a native, non-passive listener, not React's `onWheel` prop.
  // React 17+ attaches wheel listeners at the root as passive by default, so
  // `e.preventDefault()` inside a React onWheel handler silently no-ops — the
  // browser still scrolls the page underneath while this handler ALSO pans
  // the stage, and the two fights ("dancing": the canvas visibly jumps/settles
  // instead of tracking the gesture smoothly).
  const zoomRef = useRef(zoom);
  const panRef = useRef(pan);
  useEffect(() => {
    zoomRef.current = zoom;
  }, [zoom]);
  useEffect(() => {
    panRef.current = pan;
  }, [pan]);
  /** Zoom to `nextZoom` while keeping the canvas point under (anchorX, anchorY)
   *  — viewport coordinates — pinned in place.
   *
   *  The stage's transformOrigin is `0 0`, so changing `zoom` on its own always
   *  zooms about the viewport's top-left CORNER: the content lunges toward that
   *  corner on zoom-out and away from it on zoom-in. Every zoom entry point has
   *  to move `pan` in the opposite direction to compensate, which is what this
   *  does. The wheel handler had this math inline; the +/- buttons never had it
   *  at all, which is why zooming out with them threw the graph off-screen.
   *  Sharing one helper is what stops the two paths drifting apart again. */
  const zoomAbout = useCallback((nextZoom: number, anchorX: number, anchorY: number) => {
    const currentZoom = zoomRef.current;
    const currentPan = panRef.current;
    if (nextZoom === currentZoom) return;
    setPan({
      x: anchorX - ((anchorX - currentPan.x) / currentZoom) * nextZoom,
      y: anchorY - ((anchorY - currentPan.y) / currentZoom) * nextZoom,
    });
    setZoom(nextZoom);
  }, []);

  /** The +/- buttons: same compensation as the wheel, anchored on the viewport
   *  CENTRE since a button press has no cursor position to zoom about. */
  const zoomByStep = useCallback(
    (delta: number) => {
      const rect = canvasRef.current?.getBoundingClientRect();
      const next = Math.min(1.5, Math.max(0.1, Math.round((zoomRef.current + delta) * 10) / 10));
      zoomAbout(next, (rect?.width ?? 0) / 2, (rect?.height ?? 0) / 2);
    },
    [zoomAbout],
  );

  useEffect(() => {
    const canvasEl = canvasRef.current;
    if (!canvasEl) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const rect = canvasEl.getBoundingClientRect();
      const factor = Math.exp(-e.deltaY * 0.001);
      const nextZoom = Math.min(
        1.5,
        Math.max(0.1, Math.round(zoomRef.current * factor * 100) / 100),
      );
      zoomAbout(nextZoom, e.clientX - rect.left, e.clientY - rect.top);
    };
    canvasEl.addEventListener("wheel", onWheel, { passive: false });
    return () => canvasEl.removeEventListener("wheel", onWheel);
  }, [zoomAbout]);
  useEffect(() => {
    if (!isPanning) return;
    const onMove = (e: MouseEvent) => {
      setPan({
        x: panStart.current.panX + (e.clientX - panStart.current.x),
        y: panStart.current.panY + (e.clientY - panStart.current.y),
      });
    };
    const onUp = () => setIsPanning(false);
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
  }, [isPanning]);

  // Fit — measures the ACTUAL rendered content (every node card + the Brief
  // pill), not the fixed layout constants, so a wide sub-agent tree still
  // fits. `offsetLeft/offsetTop/offsetWidth/offsetHeight` reflect the
  // element's un-transformed layout box (CSS `transform: scale()` on the
  // stage doesn't affect them), so they're readable directly as stage-space
  // coordinates regardless of the current zoom/pan.
  const fitToContent = useCallback(() => {
    const canvasEl = canvasRef.current;
    const stageEl = stageRef.current;
    if (!canvasEl || !stageEl) return;
    const children = stageEl.querySelectorAll<HTMLElement>(
      '[data-testid="canvas-brief"], [data-testid^="canvas-node-wrap-"]',
    );
    if (children.length === 0) return;
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    children.forEach((el) => {
      minX = Math.min(minX, el.offsetLeft);
      minY = Math.min(minY, el.offsetTop);
      maxX = Math.max(maxX, el.offsetLeft + el.offsetWidth);
      maxY = Math.max(maxY, el.offsetTop + el.offsetHeight);
    });
    const PAD = 48;
    const contentW = maxX - minX + PAD * 2;
    const contentH = maxY - minY + PAD * 2;
    const viewportW = canvasEl.clientWidth;
    const viewportH = canvasEl.clientHeight;
    // Round ONCE, then use that same value for both. Rounding only `zoom` while
    // deriving `pan` from the unrounded ratio centres the content for a zoom
    // that is never applied, leaving it a few px off after every Fit.
    const nextZoom =
      Math.round(
        Math.min(1, Math.max(0.1, Math.min(viewportW / contentW, viewportH / contentH))) * 100,
      ) / 100;
    const contentCenterX = (minX + maxX) / 2;
    const contentCenterY = (minY + maxY) / 2;
    setZoom(nextZoom);
    setPan({
      x: viewportW / 2 - contentCenterX * nextZoom,
      y: viewportH / 2 - contentCenterY * nextZoom,
    });
  }, []);

  // Re-fit whenever the chain's length changes (an add/remove can otherwise
  // push a node past the viewport with the pan/zoom left where they were).
  useEffect(() => {
    fitToContent();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pipelineAgents.length]);

  // Re-fit whenever the canvas panel itself resizes — the length-only effect
  // above computes pan/zoom against canvasRef's size at that instant, which can
  // still be mid-transition (e.g. the modal's open animation). Without this,
  // content centers for a viewport size that never actually applies, and no
  // recompute ever follows since pipelineAgents.length hasn't changed.
  useEffect(() => {
    const canvasEl = canvasRef.current;
    if (!canvasEl) return;
    const observer = new ResizeObserver(() => fitToContent());
    observer.observe(canvasEl);
    return () => observer.disconnect();
  }, [fitToContent]);

  // Effective selection — searches the WHOLE tree (root + nested, R-35), not
  // just the root array, and falls back to the first root node if the
  // selected one was removed, so the rail always reflects an existing node.
  // The Brief is NOT an agent (BRIEF_ID never appears in pipelineAgents), so
  // it's carved out here rather than falling through to that "first node"
  // fallback — that fallback exists for a removed SELECTION, not for Brief.
  const isBriefSelected = selectedId === BRIEF_ID;
  // Selecting an external-workflow node resolves to the STEP that routes to it.
  // Its id is `${sourceId}::${outcomeKey}`, which is not an agent, so a plain
  // lookup would blank the rail on click. Showing the owning gate instead is
  // both non-empty and the thing you'd actually want to edit from there.
  const selectedAgentId = selectedId?.includes("::") ? selectedId.split("::")[0] : selectedId;
  const foundAgent =
    !isBriefSelected && selectedAgentId
      ? findAgentInTree(pipelineAgents, selectedAgentId)
      : null;
  const selAgent = isBriefSelected ? null : foundAgent ?? pipelineAgents[0] ?? null;
  // Root-array index — only meaningful when the selected node IS a root node
  // (drives the fan-out rail's `priorAgents`); -1 for a nested selection.
  const selIndex = selAgent ? pipelineAgents.findIndex((a) => a.id === selAgent.id) : -1;

  // ── Rail tabs (Workflow | Agent) — separate from canvas SELECTION above.
  const [railTab, setRailTab] = useState<"workflow" | "agent">("workflow");
  useEffect(() => {
    if (selectedId === BRIEF_ID) setRailTab("workflow");
    else if (selectedId) setRailTab("agent");
  }, [selectedId]);
  const agentTabAgent = foundAgent ?? pipelineAgents[0] ?? null;
  const agentTabIndex = agentTabAgent
    ? pipelineAgents.findIndex((a) => a.id === agentTabAgent.id)
    : -1;

  // ── Spec 012 tree-edit handlers (R-35) — every edit round-trips through
  //    `onTreeChange`, the SAME `pipelineAgents` state Save persists. ────────
  const handleAddChild = (parentId: string) => {
    if (onRequestAddSubAgent) {
      onRequestAddSubAgent(parentId);
      return;
    }
    const newId = generateInstanceId(collectAgentIds(pipelineAgents));
    const child: AgentDef = {
      id: newId,
      name: "New agent",
      role: "Custom agent",
      description: "",
      pipeline_type: pipelineType,
      order: 0,
      icon: "🤖",
      estimated_duration: 60,
      has_skill: false,
      isCustom: true,
      instance_id: newId,
    };
    onTreeChange?.(addChildInTree(pipelineAgents, parentId, child));
    setSelectedId(newId);
  };
  const handleRename = (id: string, name: string) => {
    onTreeChange?.(mapAgentInTree(pipelineAgents, id, (a) => ({ ...a, name })));
  };
  const handleRemoveId = (id: string) => {
    onTreeChange?.(removeAgentInTree(pipelineAgents, id));
    if (selectedId === id) setSelectedId(null);
  };
  const handleSkillsChange = (id: string, skills: string[]) => {
    onTreeChange?.(mapAgentInTree(pipelineAgents, id, (a) => ({ ...a, skills })));
  };
  // T35 (spec 014 / R-02) — the route-editor write-through CanvasNode's
  // `onRouteChange` docstring flagged as missing. Same shape as every other
  // tree-edit handler above: round-trips through `onTreeChange` into the SAME
  // `pipelineAgents` state Save persists (ComposerPage.tsx `buildWorkflowManifest`
  // reads `agent.route` off this).
  /** Recompute every root step's `detached` flag from the tree.
   *
   *  A step is detached when NOTHING feeds it — no route outcome points at it
   *  AND it has no structural predecessor. It keeps an incoming edge when:
   *    • it is nested (a sub-agent always has its parent), or
   *    • it is the first root step (the Brief always feeds it), or
   *    • its chain predecessor does not branch away, in which case the plain
   *      structural edge — suppressed only WHILE it was a route target —
   *      simply comes back.
   *
   *  DERIVED, not sticky. Losing a route does not by itself orphan a step, so
   *  attaching a condition to a step that already had a parent and then
   *  removing it no longer flags a perfectly connected step. Derivation also
   *  catches the mirror case a diff missed: turning a gate ON suppresses its
   *  successor's chain edge, which orphans that successor just as really.
   *
   *  This does NOT reintroduce the silent auto-reconnect the flag exists to
   *  prevent — the reconnect it allows is a real predecessor that was only ever
   *  hidden by the route, never an arbitrary array neighbour behind a branch. */
  const reconcileDetached = (tree: AgentDef[]): AgentDef[] => {
    const routeTargets = new Set<string>();
    const walk = (list: AgentDef[]) => {
      for (const a of list) {
        for (const o of Object.values(a.route?.outcomes ?? {})) {
          if (o.trigger === "step" && o.target) routeTargets.add(o.target);
        }
        if (a.children?.length) walk(a.children);
      }
    };
    walk(tree);
    const branches = (a: AgentDef) =>
      (selections[a.id]?.gates ?? []).includes("conditional") &&
      Object.keys(a.route?.outcomes ?? {}).length > 0;

    let out = tree;
    tree.forEach((a, i) => {
      const fed = routeTargets.has(a.id) || i === 0 || !branches(tree[i - 1]);
      if (!!a.detached !== !fed) {
        out = mapAgentInTree(out, a.id, (n) => ({ ...n, detached: !fed }));
      }
    });
    return out;
  };

  // Reconcile after ANY change that can alter reachability, not just a route
  // edit: toggling the `conditional` gate lives in `selections` (not the tree),
  // and adding/removing/reordering steps changes who precedes whom. Safe as an
  // effect because `reconcileDetached` returns the SAME array reference when
  // nothing needs changing, so this settles in one pass and cannot loop.
  useEffect(() => {
    const next = reconcileDetached(pipelineAgents);
    if (next !== pipelineAgents) onTreeChange?.(next);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pipelineAgents, selections]);

  const handleRouteChange = (id: string, route: AgentDef["route"]) => {
    const next = reconcileDetached(mapAgentInTree(pipelineAgents, id, (a) => ({ ...a, route })));
    onTreeChange?.(next);
  };
  const handlePromptChange = (id: string, prompt: string) => {
    onTreeChange?.(mapAgentInTree(pipelineAgents, id, (a) => ({ ...a, prompt })));
  };
  const handleStrategyChange = (id: string, next: SubagentStrategy, maxParallel?: number) => {
    onTreeChange?.(
      mapAgentInTree(pipelineAgents, id, (a) => ({ ...a, strategy: next, maxParallel })),
    );
  };

  // Branch auto-arrange. A branch is a FAN, not a staircase:
  //
  //            ┌──▶ C
  //   A ─▶ B ──┼──▶ D          (3 targets: the middle one sits level with B)
  //            └──▶ E
  //
  // so every target of one conditional step shares ONE column immediately
  // right of its source, and the group is spread vertically symmetric about
  // the source's own row. The earlier version only offset Y and left X on the
  // flat array-order staircase, which put each target in its own column —
  // a diagonal, not a fan.
  //
  // Columns are assigned by walking the root array once: a node not already
  // claimed by some branch group takes the next free column; a group's members
  // are all pinned to `source.col + 1`, so the nodes AFTER a group resume at
  // the column just past it rather than leaving N-1 empty columns behind.
  // Backward/loop targets are excluded — a loop target is a real EARLIER node
  // with an established position, and re-placing it would fight that.
  const ROW_GAP = 64; // clear air between two stacked nodes' bounding boxes

  // How much room each root node really occupies, INCLUDING its sub-agent fan.
  // Measured once at a neutral origin (layoutChildren is pure), so it can feed
  // the column/row solver below without the solver feeding back into it.
  // Without this the layout was index-based: a node with three sub-agents
  // spans ~900px, but the next column still started one NODE_W+GAP along, so a
  // branch target landed on top of the previous step's children.
  const subtreeExtent = useMemo(() => {
    const m = new Map<string, { halfWidth: number; below: number }>();
    for (const a of pipelineAgents) {
      if (!a.children || a.children.length === 0) {
        m.set(a.id, { halfWidth: NODE_W / 2, below: 0 });
        continue;
      }
      let left = -NODE_W / 2;
      let right = NODE_W / 2;
      let bottom = 0;
      for (const [, p] of layoutChildren(a, 0, 0)) {
        left = Math.min(left, p.x - p.width / 2);
        right = Math.max(right, p.x + p.width / 2);
        bottom = Math.max(bottom, p.y + CHILD_H_EST);
      }
      m.set(a.id, { halfWidth: Math.max(right, -left), below: bottom });
    }
    return m;
  }, [pipelineAgents]);

  // ── THE ARRANGEMENT CONTRACT ────────────────────────────────────────────
  //
  //  Two axes, no exceptions:
  //    • step → step  is HORIZONTAL (180°). The main flow is one straight line.
  //    • step → sub-agent is VERTICAL (90°). Fans drop straight down.
  //
  //  R1 — THE SPINE IS STRAIGHT. Every node that is not a branch target sits at
  //       row 0. The left→right path is therefore always dead horizontal.
  //
  //  R2 — BRANCH ROWS. For a conditional source S with n forward targets, stack
  //       the targets one card apart:
  //           top(i) = i * (cardH + ROW_GAP)
  //           H      = n*cardH + (n-1)*ROW_GAP
  //       then anchor the stack against S:
  //           n ODD  → the middle target m=(n-1)/2 is LEVEL with S:
  //                    delta = row(S) - top(m)          → flow continues at 180°
  //           n EVEN → no middle exists, so centre the stack on S:
  //                    delta = row(S) + cardH/2 - H/2   → symmetric about S
  //           row(Tᵢ) = top(i) + delta
  //       n=1 puts the one target on the spine; n=3 and n=5 keep their middle on
  //       it; n=2, n=4 and n=6 split evenly above and below with nothing on it.
  //       One formula, every n. `delta` is relative to row(S), so a branch whose
  //       target is itself conditional nests correctly with no special case.
  //
  //  R3 — THE SUB-AGENT BAND (see `childBandTop`). Every fan in the workflow
  //       starts at ONE y, below the lowest root node. That is what keeps fans
  //       off branch targets — moving the fans down rather than shoving the
  //       columns apart, which would spread the diagram for no reason. With no
  //       branches every row is 0 and the band lands directly under the spine,
  //       exactly where it always was.
  //
  //  R4 — COLUMN X (see `columnX`). Because fans live in their own band, a
  //       column only has to clear the NEXT column's fan, never its node:
  //           x(c+1) = x(c) + max(NODE_W + NODE_GAP, fanW(c) + fanW(c+1) + NODE_GAP)
  //       For a workflow with no sub-agents this reduces to the plain uniform
  //       NODE_W + NODE_GAP — it only widens where two adjacent fans genuinely
  //       would have collided.
  //
  //  Columns themselves are assigned by one walk of the root array: an unclaimed
  //  node takes the next free column; a group's members all pin to source.col+1,
  //  so nodes after a group resume just past it rather than leaving n-1 columns
  //  empty. Backward/loop targets are skipped — they are real earlier nodes with
  //  positions of their own.
  const { rootLayout, workflowSlots } = useMemo(() => {
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
    let nextFreeCol = 0;
    for (const agent of pipelineAgents) {
      if (!layout.has(agent.id)) layout.set(agent.id, { col: nextFreeCol, row: 0 });
      const me = layout.get(agent.id)!;
      nextFreeCol = Math.max(nextFreeCol, me.col + 1);
      if (!(selections[agent.id]?.gates ?? []).includes("conditional")) continue;
      const sourceOrder = order.get(agent.id) ?? 0;
      const group: ({ kind: "step"; id: string } | { kind: "workflow"; key: string })[] = [];
      for (const [outcomeKey, o] of Object.entries(agent.route?.outcomes ?? {})) {
        if (!o.target) continue;
        if (o.trigger === "workflow") {
          group.push({ kind: "workflow", key: `${agent.id}::${outcomeKey}` });
        } else if ((order.get(o.target) ?? -1) > sourceOrder && !layout.has(o.target)) {
          // Forward step targets only — a backward/loop target is a real
          // earlier node that already has a position. `!layout.has` keeps the
          // first group if a node is somehow targeted twice.
          group.push({ kind: "step", id: o.target });
        }
      }
      if (group.length === 0) continue;
      const n = group.length;
      const step = cardH + ROW_GAP;
      const stackH = n * cardH + (n - 1) * ROW_GAP;
      const delta =
        n % 2 === 1
          ? me.row - ((n - 1) / 2) * step // odd: middle target level with S
          : me.row + cardH / 2 - stackH / 2; // even: stack centred on S
      group.forEach((member, i) => {
        const slot = { col: me.col + 1, row: i * step + delta };
        if (member.kind === "step") layout.set(member.id, slot);
        else wfSlots.set(member.key, slot);
      });
      nextFreeCol = Math.max(nextFreeCol, me.col + 2);
    }
    return { rootLayout: layout, workflowSlots: wfSlots };
  }, [pipelineAgents, selections, rowPortOffset]);

  // R3 — the single y every sub-agent fan starts at: below the lowest root node
  // in the whole graph. `layoutChildren` drops its first child row by
  // ROOT_H_EST + TREE_ROW_GAP from the `rootTopY` it is handed, so hand it a
  // top that makes that landing point the band.
  const childBandTop = useMemo(() => {
    const cardH = rowPortOffset * 2;
    let lowest = 0;
    for (const a of pipelineAgents) lowest = Math.max(lowest, rootLayout.get(a.id)?.row ?? 0);
    return NODE_Y + lowest + Math.max(cardH, ROOT_H_EST) + ROW_GAP - ROOT_H_EST - TREE_ROW_GAP;
  }, [pipelineAgents, rootLayout, rowPortOffset]);

  // R4 — cumulative column x, widened only where adjacent fans would touch.
  const columnX = useMemo(() => {
    const fanW = new Map<number, number>();
    for (const a of pipelineAgents) {
      const col = rootLayout.get(a.id)?.col ?? 0;
      fanW.set(
        col,
        Math.max(fanW.get(col) ?? NODE_W / 2, subtreeExtent.get(a.id)?.halfWidth ?? NODE_W / 2),
      );
    }
    const cols = [...fanW.keys()].sort((p, q) => p - q);
    const xs = new Map<number, number>();
    let x = START_X;
    cols.forEach((col, i) => {
      xs.set(col, x);
      const next = cols[i + 1];
      if (next === undefined) return;
      x += Math.max(
        NODE_W + NODE_GAP,
        (fanW.get(col) ?? NODE_W / 2) + (fanW.get(next) ?? NODE_W / 2) + NODE_GAP,
      );
    });
    return xs;
  }, [pipelineAgents, rootLayout, subtreeExtent]);

  // Base (pre-drag) geometry of every external-workflow node, keyed
  // `${sourceId}::${outcomeKey}`. Defined here, above `positionOf`, because
  // positionOf has to resolve these ids too — they are draggable nodes, and the
  // drag gesture reads its start position through positionOf.
  const externalSlotById = useMemo(() => {
    const m = new Map<
      string,
      { x: number; y: number; sourceId: string; outcomeKey: string; target: string }
    >();
    for (const agent of pipelineAgents) {
      for (const [outcomeKey, o] of Object.entries(agent.route?.outcomes ?? {})) {
        if (o.trigger !== "workflow" || !o.target) continue;
        const key = `${agent.id}::${outcomeKey}`;
        const slot = workflowSlots.get(key);
        if (!slot) continue;
        m.set(key, {
          x: columnX.get(slot.col) ?? START_X,
          y: NODE_Y + slot.row,
          sourceId: agent.id,
          outcomeKey,
          target: o.target,
        });
      }
    }
    return m;
  }, [pipelineAgents, workflowSlots, columnX]);

  // ── Sub-agent tree layout — computed fresh from pipelineAgents every
  //    render (cheap, pure function; no DOM measurement needed for nested
  //    levels, see treeLayout.ts). Root positions come from the EXISTING
  //    nodeLeft(i)/NODE_Y + measured height (nodeCenterY), same as always. ──
  const childPositions = useMemo(() => {
    const merged = new Map<string, FlatPos>();
    pipelineAgents.forEach((agent, i) => {
      if (!agent.children || agent.children.length === 0) return;
      // Follow the branch layout's column/row, not the raw array index — a
      // fanned-out branch target moves, and its sub-agents have to move with it.
      const slot = rootLayout.get(agent.id);
      const rootCenterX = (columnX.get(slot?.col ?? i) ?? nodeLeft(slot?.col ?? i)) + NODE_W / 2;
      // R3: every fan starts at the SHARED band, not under its own row —
      // that is what keeps a fan clear of a branch target below the spine.
      const positions = layoutChildren(agent, rootCenterX, childBandTop);
      for (const [id, pos] of positions) merged.set(id, pos);
    });
    return merged;
  }, [pipelineAgents, rootLayout, columnX, childBandTop]);

  const allDescendants = useMemo(
    () => pipelineAgents.flatMap((a) => flattenDescendants(a)),
    [pipelineAgents],
  );

  // Only 3 levels of nesting: root (depth 0) → depth 1 → depth 2 (which may
  // not have its own children). Each parent holds at most 8 direct sub-agents
  // (mirrors the root chain's own MAX_OPTIONAL=8, owned by ComposerPage).
  const MAX_SUBAGENTS = 8;
  const depthOf = useCallback(
    (id: string) => childPositions.get(id)?.depth ?? 0,
    [childPositions],
  );
  const addChildDisabledReason = useCallback(
    (agent: AgentDef): string | undefined => {
      if (depthOf(agent.id) >= 2) return "Maximum 3 levels of nesting are allowed";
      if ((agent.children?.length ?? 0) >= MAX_SUBAGENTS) return "Maximum 8 sub-agents are allowed";
      return undefined;
    },
    [depthOf],
  );


  // Effective position of ANY node (root or nested), with free-drag override
  // applied on top.
  const positionOf = useCallback(
    (id: string): { x: number; y: number; width: number } => {
      const override = dragOverrides[id];
      const rootIndex = pipelineAgents.findIndex((a) => a.id === id);
      if (rootIndex >= 0) {
        const slot = rootLayout.get(id);
        const base = {
          x: columnX.get(slot?.col ?? rootIndex) ?? nodeLeft(slot?.col ?? rootIndex),
          y: NODE_Y + (slot?.row ?? 0),
          width: NODE_W,
        };
        return override ? { ...base, x: override.x, y: override.y } : base;
      }
      // External-workflow nodes are not agents and have no childPositions
      // entry, but they ARE draggable, so positionOf has to resolve them too —
      // handleCardMouseDown reads the current position through this.
      const wf = externalSlotById.get(id);
      if (wf) {
        const base = { x: wf.x, y: wf.y, width: EXTERNAL_NODE_W };
        return override ? { ...base, x: override.x, y: override.y } : base;
      }
      const pos = childPositions.get(id);
      if (!pos) return { x: 0, y: 0, width: CHILD_W };
      const base = { x: pos.x - pos.width / 2, y: pos.y, width: pos.width };
      return override ? { ...base, x: override.x, y: override.y } : base;
    },
    [dragOverrides, pipelineAgents, childPositions, rootLayout, columnX, externalSlotById],
  );

  // ── Free-drag (any node) ────────────────────────────────────────────────
  const handleCardMouseDown = (id: string) => (e: React.MouseEvent) => {
    if (e.button !== 0 || spacePressed) return;
    const pos = positionOf(id);
    dragState.current = {
      id,
      startClientX: e.clientX,
      startClientY: e.clientY,
      startX: pos.x,
      startY: pos.y,
      moved: false,
    };
  };
  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      const st = dragState.current;
      if (!st) return;
      const dxClient = e.clientX - st.startClientX;
      const dyClient = e.clientY - st.startClientY;
      if (!st.moved && Math.hypot(dxClient, dyClient) < DRAG_THRESHOLD) return;
      st.moved = true;
      // Live feedback during the drag, not just on drop — divide by zoom so
      // the card tracks the cursor 1:1 regardless of current zoom level.
      setDragOverrides((prev) => ({
        ...prev,
        [st.id]: { x: st.startX + dxClient / zoomRef.current, y: st.startY + dyClient / zoomRef.current },
      }));
    };
    const onUp = () => {
      dragState.current = null;
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
  }, []);
  const handleAutoArrange = useCallback(() => setDragOverrides({}), []);

  // ── Edge-drag-to-reparent (mousedown on a child's top port) ─────────────
  const stageXYFromClient = useCallback((clientX: number, clientY: number) => {
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect) return { x: 0, y: 0 };
    return {
      x: (clientX - rect.left - panRef.current.x) / zoomRef.current,
      y: (clientY - rect.top - panRef.current.y) / zoomRef.current,
    };
  }, []);
  /** The node whose rendered rect contains (x, y), excluding `exceptId`.
   *  The SAME 180px-tall box both drags already hit-test against on mouseup —
   *  factored out so the highlight shown mid-drag and the drop actually taken
   *  on release can never disagree. */
  const hitTestNodeAt = useCallback(
    (x: number, y: number, exceptId?: string): string | null => {
      for (const candidate of [...pipelineAgents, ...allDescendants]) {
        if (candidate.id === exceptId) continue;
        const pos = positionOf(candidate.id);
        if (x >= pos.x && x <= pos.x + pos.width && y >= pos.y && y <= pos.y + 180) {
          return candidate.id;
        }
      }
      return null;
    },
    [pipelineAgents, allDescendants, positionOf],
  );

  const hasOrphan = pipelineAgents.some((a) => a.detached);
  const handleChainConnectMouseDown = (sourceId: string) => (e: React.MouseEvent) => {
    e.stopPropagation();
    e.preventDefault();
    const { x, y } = stageXYFromClient(e.clientX, e.clientY);
    setChainConnectDrag({ sourceId, x, y });
  };
  useEffect(() => {
    if (!chainConnectDrag) return;
    const onMove = (e: MouseEvent) => {
      const { x, y } = stageXYFromClient(e.clientX, e.clientY);
      setChainConnectDrag((prev) => (prev ? { ...prev, x, y } : prev));
      const over = hitTestNodeAt(x, y, chainConnectDrag.sourceId);
      // Only an ORPHAN is a legal drop here, so only an orphan lights up.
      setDropHoverId(over && findAgentInTree(pipelineAgents, over)?.detached ? over : null);
    };
    const onUp = (e: MouseEvent) => {
      const { x, y } = stageXYFromClient(e.clientX, e.clientY);
      const targetId = hitTestNodeAt(x, y, chainConnectDrag.sourceId);
      const target = targetId ? findAgentInTree(pipelineAgents, targetId) : null;
      if (target?.detached) {
        const without = pipelineAgents.filter((a) => a.id !== targetId);
        const at = without.findIndex((a) => a.id === chainConnectDrag.sourceId);
        const next = [...without];
        next.splice(at + 1, 0, { ...target, detached: false });
        onTreeChange?.(next);
      }
      setChainConnectDrag(null);
      setDropHoverId(null);
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chainConnectDrag?.sourceId, pipelineAgents]);

  const handlePortMouseDown = (childId: string, fromEdge = false) => (e: React.MouseEvent) => {
    e.stopPropagation();
    e.preventDefault();
    const { x, y } = stageXYFromClient(e.clientX, e.clientY);
    setReparentDrag({ childId, x, y, fromEdge });
  };
  useEffect(() => {
    if (!reparentDrag) return;
    const onMove = (e: MouseEvent) => {
      const { x, y } = stageXYFromClient(e.clientX, e.clientY);
      setReparentDrag((prev) => (prev ? { ...prev, x, y } : prev));
      setDropHoverId(hitTestNodeAt(x, y, reparentDrag!.childId));
    };
    const onUp = (e: MouseEvent) => {
      const { x, y } = stageXYFromClient(e.clientX, e.clientY);
      // Hit-test: is (x,y) inside the Brief pill, or inside any node's
      // rendered rect (excluding the dragged child and its own descendants
      // — moveAgentInTree also guards this, but checking here avoids
      // flashing an invalid drop as if it worked)?
      const draggedNode = findAgentInTree(pipelineAgents, reparentDrag!.childId);
      const draggedHasChildren = (draggedNode?.children?.length ?? 0) > 0;
      const without = removeAgentInTree(pipelineAgents, reparentDrag!.childId);
      const briefRect = { x: BRIEF_X, y: briefTop, w: BRIEF_W, h: briefHeight };
      // Same 3-level-nesting + 8-sibling cap the "+ Sub-agent" button enforces
      // (addChildDisabledReason) — applied here too so dragging a connector
      // can't bypass it and create a forbidden 4th ("sub-child") level.
      const isValidTarget = (candidateId: string): boolean => {
        const targetDepth = candidateId === BRIEF_ID ? 0 : depthOf(candidateId) + 1;
        if (targetDepth > 2) return false;
        if (targetDepth === 2 && draggedHasChildren) return false;
        const siblingCount =
          candidateId === BRIEF_ID
            ? without.length
            : (findAgentInTree(without, candidateId)?.children?.length ?? 0);
        return siblingCount < MAX_SUBAGENTS;
      };
      let newParentId: string | null = null;
      if (
        x >= briefRect.x && x <= briefRect.x + briefRect.w &&
        y >= briefRect.y && y <= briefRect.y + briefRect.h &&
        isValidTarget(BRIEF_ID)
      ) {
        newParentId = BRIEF_ID;
      } else {
        const candidates = [...pipelineAgents, ...allDescendants];
        for (const candidate of candidates) {
          if (candidate.id === reparentDrag!.childId) continue;
          if (draggedNode && isDescendant(draggedNode, candidate.id)) continue;
          if (!isValidTarget(candidate.id)) continue;
          const pos = positionOf(candidate.id);
          if (x >= pos.x && x <= pos.x + pos.width && y >= pos.y && y <= pos.y + 180) {
            newParentId = candidate.id;
            break;
          }
        }
      }
      if (newParentId) {
        onTreeChange?.(moveAgentInTree(pipelineAgents, reparentDrag!.childId, newParentId));
      } else if (reparentDrag!.fromEdge && depthOf(reparentDrag!.childId) > 0) {
        // Grabbed the drawn parent→child line and let go over empty canvas:
        // that IS the "delete this line" gesture. The tree has no way to
        // express a parentless sub-agent, so detaching means promoting the
        // child back onto the root chain (BRIEF_ID) — the same target the
        // Brief-pill drop above uses.
        onTreeChange?.(moveAgentInTree(pipelineAgents, reparentDrag!.childId, BRIEF_ID));
      }
      setReparentDrag(null);
      setDropHoverId(null);
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reparentDrag?.childId, pipelineAgents, allDescendants, briefTop, briefHeight]);

  // Actual on-screen center-Y of a root node, honoring any free-drag
  // override — `centerYOf` alone only ever encodes a DOM-measured height
  // offset from the fixed NODE_Y baseline, so it silently drifted from a
  // dragged node's real position (D-04 follow-up: edges must track drags).
  //  Uses the SHARED rowPortOffset, not this card's own measured center, so
  //  two nodes on the same row always yield the same Y — a flat edge.
  const actualCenterY = useCallback(
    (id: string) => positionOf(id).y + rowPortOffset,
    [positionOf, rowPortOffset],
  );

  // The positioned external-workflow nodes (spec 014 / R-22) — one per
  // `trigger:"workflow"` outcome that has a target, placed in the row slot R2
  // allocated for it. These are references to a SEPARATE run, not steps of this
  // one, which is why they render as their own smaller node kind rather than
  // the target workflow's steps inlined here.
  const externalWorkflowNodes = [...externalSlotById.entries()].map(([key, slot]) => {
    const live = positionOf(key);
    return { key, ...slot, x: live.x, y: live.y };
  });

  // ── Edge list — main chain (Brief→node0→…) PLUS every tree edge, all
  //    tinted brand when either endpoint is the current selection (a
  //    "what's this node connected to" hint highlight). ────────────────────
  // `childId` is set on TREE edges only — it is what makes the drawn line
  // grabbable (re-parent) and droppable-into-empty-space (detach). Chain edges
  // leave it undefined: their order IS the array order, so there is no field a
  // "delete this line" gesture could write to.
  type EdgeSpec = { key: string; sx: number; sy: number; ex: number; ey: number; curved: boolean; active: boolean; childId?: string };
  // A step that BRANCHES has no structural successor: its outgoing edges are
  // the amber route lines, one per outcome. Drawing the blue chain edge too
  // put a brown AND a blue line on the same branch point, implying a
  // sequential hand-off that will never happen (the run jumps to whichever
  // outcome matched). This mirrors `deriveDependsOn`, which already drops the
  // chain-predecessor `depends_on` edge for a route target.
  const branchesAway = (id: string) =>
    (selections[id]?.gates ?? []).includes("conditional") &&
    Object.keys(findAgentInTree(pipelineAgents, id)?.route?.outcomes ?? {}).length > 0;
  // Every node that some conditional step routes INTO. Such a node already has
  // exactly one incoming line — the brown route edge — so it must not also
  // receive the blue chain edge from whatever happens to precede it in the
  // array. Without this, the second target of a 2-way branch got a brown line
  // from the gate AND a blue line from its sibling: two parents for one node.
  // Same rule `deriveDependsOn` applies to the persisted `depends_on`, so the
  // drawing and the compiled graph agree.
  const routeTargetIds = new Set(
    [...pipelineAgents, ...allDescendants]
      .filter((a) => (selections[a.id]?.gates ?? []).includes("conditional"))
      .flatMap((a) =>
        Object.values(a.route?.outcomes ?? {})
          .filter((o) => o.trigger === "step" && o.target)
          .map((o) => o.target as string),
      ),
  );
  const hasChainEdge = (i: number) => {
    if (i === 0) return true; // Brief → first node always draws
    // A detached node has no incoming edge at all — that is the whole point of
    // the flag. Drawing the chain edge here is exactly the auto-reconnect it
    // exists to prevent.
    if (pipelineAgents[i].detached) return false;
    if (branchesAway(pipelineAgents[i - 1].id)) return false;
    return !routeTargetIds.has(pipelineAgents[i].id);
  };
  const chainEdges: EdgeSpec[] = pipelineAgents.flatMap((a, i) => {
    const prevId = i === 0 ? BRIEF_ID : pipelineAgents[i - 1].id;
    if (!hasChainEdge(i)) return [];
    const sx = i === 0 ? BRIEF_X + BRIEF_W : positionOf(prevId).x + NODE_W;
    const sy = i === 0 ? briefCenterY : actualCenterY(prevId);
    const ex = positionOf(a.id).x - ARROW_INSET;
    const ey = actualCenterY(a.id);
    return [{
      key: `chain-${i}`,
      sx,
      sy,
      ex,
      ey,
      curved: false,
      active: selectedId === a.id || selectedId === prevId,
    }];
  });
  const treeEdges: EdgeSpec[] = pipelineAgents.flatMap((rootAgent, i) => {
    // The card's real bottom. Root cards are all padded to the row height
    // (`minCardHeight`), so that — not this card's own natural height — is
    // where the trunk to its sub-agents leaves from.
    const rootBottomY = positionOf(rootAgent.id).y + rowPortOffset * 2;
    return collectTreeEdges(rootAgent).map(({ parentId, childId }) => {
      const parentPos = positionOf(parentId);
      const childPos = positionOf(childId);
      const parentIsRoot = parentId === rootAgent.id;
      const sx = parentPos.x + parentPos.width / 2;
      const sy = parentIsRoot ? rootBottomY : parentPos.y + 156; // CHILD_H_EST from treeLayout.ts
      const ex = childPos.x + childPos.width / 2;
      const ey = childPos.y;
      return {
        key: `tree-${parentId}-${childId}`,
        sx,
        sy,
        ex,
        ey,
        curved: true,
        active: selectedId === parentId || selectedId === childId,
        childId,
      };
    });
  });
  const edges = [...chainEdges, ...treeEdges];

  // ── Route edges (spec 014 / R-23, T45) — an ADDITIVE layer drawn on top of
  //    the unchanged chainEdges/treeEdges above (no node x/y repositioning):
  //    one new edge per trigger:step outcome of a `gates:[conditional]` step,
  //    resolved by instance_id against the SAME positionOf/actualCenterY the
  //    structural edges already use. trigger:workflow outcomes are skipped —
  //    ExternalPipelineCard (T36) already represents those inline on the
  //    node, so a duplicate in-canvas edge would be redundant. ────────────
  const stepOrderIndex = useMemo(() => {
    const order = new Map<string, number>();
    let i = 0;
    const walk = (list: AgentDef[]) => {
      for (const a of list) {
        order.set(a.id, i++);
        if (a.children?.length) walk(a.children);
      }
    };
    walk(pipelineAgents);
    return order;
  }, [pipelineAgents]);

  // A nested node has no DOM-measured height (unlike a root card, via
  // nodeCenterY) — CHILD_H_EST/2 mirrors the same fixed estimate
  // treeLayout.ts already assumes for that card's own row spacing.
  const routeAnchorY = useCallback(
    (id: string) => {
      const isRoot = pipelineAgents.some((a) => a.id === id);
      return isRoot ? actualCenterY(id) : positionOf(id).y + 78;
    },
    [pipelineAgents, actualCenterY, positionOf],
  );

  type RouteEdgeSpec = {
    key: string;
    sourceId: string;
    targetId?: string;
    outcomeKey: string;
    sx: number;
    sy: number;
    ex: number;
    ey: number;
    backward: boolean;
    loopStagger: number; // only meaningful when backward — R-23's "stagger per edge index"
    label: string; // the condition value this outcome fires on
  };
  // Fan-out origin: a conditional node's outgoing port IS the diamond
  // (CanvasNode's `port` helper renders the right port as one instead of a
  // circle), and EVERY outcome's edge starts at that single point — the same
  // spot the circular port occupies on a non-branching node. An earlier
  // version offset alternate edges to the diamond's top/bottom tips, which
  // made three branches look like they sprouted from three different places.
  const routeEdges: RouteEdgeSpec[] = [];
  let loopIndex = 0;
  for (const agent of [...pipelineAgents, ...allDescendants]) {
    // Gates live on the SelectionsMap lever (mirrors CanvasNode's own
    // `conditionalOn` check) — `route` itself is the AgentDef field.
    if (!(selections[agent.id]?.gates ?? []).includes("conditional")) continue;
    const stepOutcomes = Object.entries(agent.route?.outcomes ?? {}).filter(
      ([, o]) => o.trigger === "step" && o.target && stepOrderIndex.has(o.target),
    );
    const sourcePos = positionOf(agent.id);
    const sourceCenterY = routeAnchorY(agent.id);
    const sourceOrder = stepOrderIndex.get(agent.id) ?? 0;
    for (const [outcomeKey, outcome] of stepOutcomes) {
      const targetPos = positionOf(outcome.target);
      const ey = routeAnchorY(outcome.target);
      const targetOrder = stepOrderIndex.get(outcome.target) ?? 0;
      // The loop case (R-23): a target at or before the source's own order —
      // the same "ancestor" relationship isDescendant/moveAgentInTree guard
      // against for a plain reparent, except a route edge MUST be able to
      // target it.
      const backward = targetOrder <= sourceOrder;
      if (backward) loopIndex += 1;
      // A LOOP leaves the TOP of the source and enters the TOP of the target,
      // arcing over everything in between. Anchoring it on the sides like a
      // forward branch drags it back through the whole main flow line, which is
      // exactly what a back-edge should stay clear of. Top-to-top is also how a
      // loop reads at a glance: up, back, down.
      //
      // A FORWARD branch keeps the side anchors — it leaves the diamond on the
      // source's right edge and enters the target's left.
      const facingRight = targetPos.x >= sourcePos.x;
      const geom = backward
        ? {
            sx: sourcePos.x + sourcePos.width / 2,
            sy: positionOf(agent.id).y,
            ex: targetPos.x + targetPos.width / 2,
            ey: targetPos.y,
          }
        : {
            sx: facingRight ? sourcePos.x + sourcePos.width : sourcePos.x,
            sy: sourceCenterY,
            ex: facingRight ? targetPos.x : targetPos.x + targetPos.width,
            ey,
          };
      routeEdges.push({
        key: `route-${agent.id}-${outcomeKey}`,
        sourceId: agent.id,
        targetId: outcome.target,
        outcomeKey,
        ...geom,
        backward,
        loopStagger: backward ? loopIndex - 1 : 0,
        // A loop edge names its cap: "dutch ↺5". The bound exists either way
        // (engine default 5) — showing it stops a loop reading as unbounded.
        label: backward
          ? `${outcomeKey} ↺${agent.route?.loop_max_iterations ?? 5}`
          : outcomeKey,
      });
    }
  }
  // …and one edge per external-workflow node, so a `trigger:"workflow"` outcome
  // is as visible on the canvas as a `trigger:"step"` one. Always forward (the
  // node is placed in the source's own fan, one column right), so it draws with
  // the same horizontal cubic as every other forward route edge.
  for (const wf of externalWorkflowNodes) {
    const sourcePos = positionOf(wf.sourceId);
    routeEdges.push({
      key: `route-wf-${wf.key}`,
      sourceId: wf.sourceId,
      outcomeKey: wf.outcomeKey,
      sx: sourcePos.x + sourcePos.width,
      sy: routeAnchorY(wf.sourceId),
      ex: wf.x - ARROW_INSET,
      ey: wf.y + EXTERNAL_NODE_H / 2,
      backward: false,
      loopStagger: 0,
      label: wf.outcomeKey,
    });
  }

  // Inter-node insert affordances (between consecutive ROOT nodes only,
  // matching the old canvas exactly — no insert between Brief and node0) +
  // a chain-end add.
  const inserts = pipelineAgents.slice(1).flatMap((_, k) => {
    const i = k; // between node i and node i+1
    // An insert affordance sits ON a chain edge, so it only exists where one
    // does — same predicate, plus a guard against two siblings of one branch
    // group (same column: the midpoint would land on top of them rather than
    // between them).
    if (!hasChainEdge(i + 1)) return [];
    if (rootLayout.get(pipelineAgents[i].id)?.col === rootLayout.get(pipelineAgents[i + 1].id)?.col)
      return [];
    return [{
      key: `ins-${i}`,
      x: (positionOf(pipelineAgents[i].id).x + NODE_W + positionOf(pipelineAgents[i + 1].id).x) / 2,
      y: (actualCenterY(pipelineAgents[i].id) + actualCenterY(pipelineAgents[i + 1].id)) / 2,
      // The new agent should land right BEFORE node i+1 — i.e. between i and i+1.
      insertBeforeId: pipelineAgents[i + 1].id,
    }];
  });
  // Every LEAF gets its own "+" on its right, not just one at the end of the
  // array. Branching means there is no single tail any more: a 2-way gate
  // leaves two dead ends, and each of them needs somewhere to continue from.
  // A leaf is a root step with no outgoing edge of either colour — it does not
  // branch away (no amber route lines) and nothing draws a blue chain edge
  // from it. The insert lands directly after that leaf in array order.
  const leafAdds = pipelineAgents
    .map((a, i) => ({ a, i }))
    .filter(({ a, i }) => {
      if (branchesAway(a.id)) return false;
      return !(i + 1 < pipelineAgents.length && hasChainEdge(i + 1));
    })
    .map(({ a, i }) => ({
      key: `leaf-add-${a.id}`,
      x: positionOf(a.id).x + NODE_W + NODE_GAP / 2,
      y: actualCenterY(a.id),
      insertBeforeId: pipelineAgents[i + 1]?.id,
    }));
  // Empty canvas: one "+" just right of the Brief pill.
  const emptyAdd =
    pipelineAgents.length === 0
      ? { x: BRIEF_X + BRIEF_W + NODE_GAP / 2, y: briefCenterY }
      : null;

  // ── Spec 012 (R-07/R-37) — workflow-level settings (deliverable/planner/
  //    clarify/internet). These apply to the whole run, not a single node, so
  //    they live under the Brief instruction (the workflow-level selection),
  //    not the per-node rail. ─────────────────────────────────────────────
  const Toggle = ({
    on,
    label,
    disabled = false,
    onToggle,
  }: {
    on: boolean;
    label: string;
    disabled?: boolean;
    onToggle: () => void;
  }) => (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      aria-label={label}
      disabled={disabled}
      onClick={onToggle}
      className={`relative h-5 w-[34px] flex-none rounded-full transition-colors disabled:opacity-40 ${
        on ? "bg-brand" : "bg-line-faint"
      }`}
    >
      <span
        className={`absolute top-0.5 h-4 w-4 rounded-full bg-surface-white shadow-sm transition-all ${
          on ? "left-[16px]" : "left-0.5"
        }`}
      />
    </button>
  );

  const InfoHint = ({ children }: { children: ReactNode }) => (
    <span className="group relative inline-flex flex-none">
      <Info className="h-3.5 w-3.5 cursor-help text-ink-300 hover:text-ink-500" />
      <span
        role="tooltip"
        className="pointer-events-none absolute left-0 top-full z-20 mt-1.5 w-[260px] max-w-[80vw] rounded-[8px] border border-line-control bg-surface-card px-2.5 py-2 font-sans text-[11px] normal-case tracking-normal leading-relaxed text-ink-700 opacity-0 shadow-lg transition-opacity group-hover:opacity-100"
      >
        {children}
      </span>
    </span>
  );
  // Same styled hover-tooltip box as InfoHint above, reused for a disabled
  // add/insert button's cap reason instead of a plain native `title=`.
  const CapTip = ({ reason, children }: { reason?: string; children: ReactNode }) => (
    <span className="group relative inline-flex">
      {children}
      {reason && (
        <span
          role="tooltip"
          className="pointer-events-none absolute left-1/2 top-full z-20 mt-1.5 w-[190px] -translate-x-1/2 rounded-[8px] border border-line-control bg-surface-card px-2.5 py-2 text-center font-sans text-[11px] normal-case tracking-normal leading-relaxed text-ink-700 opacity-0 shadow-lg transition-opacity group-hover:opacity-100"
        >
          {reason}
        </span>
      )}
    </span>
  );
  const OnOffHint = ({ on, off }: { on: string; off: string }) => (
    <InfoHint>
      <div>
        <span className="font-semibold text-ink-900">ON</span> — {on}
      </div>
      <div className="mt-1">
        <span className="font-semibold text-ink-900">OFF</span> — {off}
      </div>
    </InfoHint>
  );

  const deliverableStrategy = runConfig?.deliverable?.strategy ?? "streamed_text";
  const deliverableName = runConfig?.deliverable?.name ?? "output.md";
  const plannerOn = (runConfig?.planner ?? "skip") === "run";
  const clarifyOn = (runConfig?.clarify?.mode ?? "skip") === "auto";
  const patchRunConfig = (patch: Partial<WorkflowRunConfig>) =>
    onRunConfigChange?.({ ...runConfig, ...patch });

  const FORMAT_OPTIONS: Record<string, { value: string; label: string }[]> = {
    streamed_text: [
      { value: ".md", label: "Markdown (.md)" },
      { value: ".html", label: "HTML (.html)" },
    ],
    single_file: [
      { value: ".html", label: "HTML (.html)" },
      { value: ".md", label: "Markdown (.md)" },
    ],
    serialized_sandbox: [{ value: ".zip", label: "Zip archive (.zip)" }],
  };
  const formatOptions = FORMAT_OPTIONS[deliverableStrategy] ?? FORMAT_OPTIONS.streamed_text;
  const currentExt = deliverableName.slice(deliverableName.lastIndexOf("."));
  const currentFormat = formatOptions.some((f) => f.value === currentExt)
    ? currentExt
    : formatOptions[0].value;
  const withExtension = (name: string, ext: string) => {
    const base = name.includes(".") ? name.slice(0, name.lastIndexOf(".")) : name;
    return `${base || "output"}${ext}`;
  };
  const deliverableBaseName = deliverableName.includes(".")
    ? deliverableName.slice(0, deliverableName.lastIndexOf("."))
    : deliverableName;
  const formatLocked = formatOptions.length <= 1;

  const workflowSettingsSection = (
    <div className="flex flex-col gap-3.5 border-t border-line-divider px-[18px] py-3.5">
      <div className="flex items-center justify-between">
        <span className="flex items-center gap-1.5 font-sans text-[12.5px] font-semibold text-ink-900">
          <OnOffHint
            on="Runs a planning agent that breaks the brief into a task plan before the workflow's agents start."
            off="Agents start directly from the brief, with no planning pass."
          />
          Smart planning
        </span>
        <Toggle
          on={plannerOn}
          label="Smart planning"
          disabled={!onRunConfigChange}
          onToggle={() => patchRunConfig({ planner: plannerOn ? "skip" : "run" })}
        />
      </div>
      <div className="flex items-center justify-between">
        <span className="flex items-center gap-1.5 font-sans text-[12.5px] font-semibold text-ink-900">
          <OnOffHint
            on="Pauses the run to ask clarifying questions about the brief, then uses your answers to fill in missing details."
            off="Runs immediately with the brief as written."
          />
          Confirm requirements first
        </span>
        <Toggle
          on={clarifyOn}
          label="Confirm requirements first"
          disabled={!onRunConfigChange}
          onToggle={() =>
            patchRunConfig({
              clarify: clarifyOn ? { mode: "skip", defaults: [] } : { mode: "auto", defaults: [] },
            })
          }
        />
      </div>

      <div>
        <div className="mb-1.5 flex items-center gap-1.5 font-sans text-[12.5px] font-semibold text-ink-900">
          <InfoHint>
            <div>
              <span className="font-semibold text-ink-900">Streamed text</span> — uses the agent&apos;s raw output.
            </div>
            <div className="mt-1">
              <span className="font-semibold text-ink-900">Single file</span> — reads back one named file from the
              workspace.
            </div>
            <div className="mt-1">
              <span className="font-semibold text-ink-900">Serialized sandbox</span> — zips the whole workspace.
            </div>
          </InfoHint>
          Deliverable
        </div>
        <select
          aria-label="Deliverable strategy"
          name="deliverable-strategy"
          value={deliverableStrategy}
          disabled={!onRunConfigChange}
          onChange={(e) => {
            const strategy = e.target.value;
            const nextExt = (FORMAT_OPTIONS[strategy] ?? FORMAT_OPTIONS.streamed_text)[0].value;
            patchRunConfig({
              deliverable: { strategy, name: withExtension(deliverableName, nextExt) },
            });
          }}
          className="w-full rounded-[8px] border border-line-control bg-surface-white px-2 py-1.5 font-sans text-[11.5px] text-ink-900 focus:border-brand focus:outline-none"
        >
          <option value="streamed_text">Streamed text — agent&apos;s raw output</option>
          <option value="single_file">Single file — one file from the workspace</option>
          <option value="serialized_sandbox">Serialized sandbox — zip the workspace</option>
        </select>

        <div className="mt-2 flex items-center gap-2">
          <input
            type="text"
            aria-label="Output file name"
            name="output-filename"
            value={deliverableBaseName}
            disabled={!onRunConfigChange}
            onChange={(e) =>
              patchRunConfig({
                deliverable: {
                  strategy: deliverableStrategy,
                  name: withExtension(e.target.value, currentFormat),
                },
              })
            }
            placeholder="output"
            className="flex-1 rounded-[8px] border border-line-control bg-surface-white px-2 py-1.5 font-sans text-[11.5px] text-ink-900 focus:border-brand focus:outline-none"
          />
          <select
            aria-label="Output format"
            name="output-format"
            value={currentFormat}
            disabled={!onRunConfigChange || formatLocked}
            onChange={(e) =>
              patchRunConfig({
                deliverable: {
                  strategy: deliverableStrategy,
                  name: withExtension(deliverableName, e.target.value),
                },
              })
            }
            className="w-[132px] flex-none rounded-[8px] border border-line-control bg-surface-white px-2 py-1.5 font-sans text-[11.5px] text-ink-900 focus:border-brand focus:outline-none disabled:opacity-60"
          >
            {formatOptions.map((f) => (
              <option key={f.value} value={f.value}>
                {f.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="flex items-center justify-between border-t border-line-divider pt-3.5">
        <div className="flex min-w-0 items-center gap-2">
          <Globe className="h-3.5 w-3.5 flex-none text-ink-300" />
          <span className="font-sans text-[12.5px] font-semibold text-ink-900">Internet access</span>
        </div>
        <Toggle
          on={!!capabilities?.internet}
          label="Internet access"
          disabled={!onCapabilitiesChange}
          onToggle={() =>
            onCapabilitiesChange?.({ ...capabilities, internet: !capabilities?.internet })
          }
        />
      </div>
    </div>
  );

  return (
    <div data-testid="canvas-view" className="flex h-full min-h-0">
      {/* ── Canvas (dot-grid) ─────────────────────────────────────────────── */}
      <div
        ref={canvasRef}
        onMouseDown={handleCanvasMouseDown}
        className={`relative flex-1 overflow-hidden ${
          isPanning ? "cursor-grabbing" : spacePressed ? "cursor-grab" : ""
        }`}
        style={{
          background:
            "radial-gradient(circle at 1px 1px, var(--line-faint) 1.2px, transparent 0), var(--surface-paper)",
          // The grid belongs to the CANVAS, not the screen. This element is
          // never transformed (the stage below carries translate+scale), so the
          // lattice has to be scaled by hand — otherwise the dots keep a fixed
          // 22px screen spacing while the nodes grow and shrink around them,
          // and the grid stops being a spatial reference at any zoom but 100%.
          // Translation was already handled; only the size was missing.
          backgroundSize: `${gridSpacing}px ${gridSpacing}px`,
          backgroundPosition: `${pan.x}px ${pan.y}px`,
        }}
      >
        {/* hint — solid card so it reads clearly over the dot-grid canvas
            instead of the dots showing through the text. */}
        <div className="absolute left-[22px] top-4 z-[4] flex items-center gap-3.5 rounded-[9px] border border-line-control bg-surface-card px-3 py-1.5 font-sans text-[11.5px] text-ink-300 shadow-[0_1px_3px_rgba(17,17,20,0.06)]">
          <span>
            <b className="font-semibold text-ink-500">Click</b> a node to configure
          </span>
          <span>
            <b className="font-semibold text-ink-500">Drag</b> to move · drag a top port to reparent
          </span>
          <span>
            Hold <b className="font-semibold text-ink-500">Space</b> + drag to pan
          </span>
        </div>

        {/* stage — the nodes + the SVG edge layer share this coordinate space */}
        <div
          ref={stageRef}
          className="absolute inset-0"
          style={{
            transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`,
            transformOrigin: "0 0",
          }}
        >
          {/* edges UNDER the nodes */}
          <svg className="pointer-events-none absolute inset-0 h-full w-full overflow-visible">
            <defs>
              <marker id="arw" markerWidth="9" markerHeight="9" refX="6.5" refY="4.5" orient="auto">
                <path d="M1 1 L7 4.5 L1 8 Z" fill="var(--ink-300)" />
              </marker>
              <marker id="arwb" markerWidth="9" markerHeight="9" refX="6.5" refY="4.5" orient="auto">
                <path d="M1 1 L7 4.5 L1 8 Z" fill="var(--brand)" />
              </marker>
              {/* Route-edge arrowhead (T45, redesigned) — amber for every
                  route edge, forward or backward: brown lines now behave
                  like the blue structural edges above (solid, one
                  consistent style) rather than backward getting a separate
                  dashed/red "loop warning" treatment. */}
              <marker id="arw-route" markerWidth="9" markerHeight="9" refX="6.5" refY="4.5" orient="auto">
                <path d="M1 1 L7 4.5 L1 8 Z" fill="var(--status-amber)" />
              </marker>
              {/* Resting (unselected) route arrowhead — neutral, matching the
                  structural edges' resting colour. */}
              <marker id="arw-route-dim" markerWidth="9" markerHeight="9" refX="6.5" refY="4.5" orient="auto">
                <path d="M1 1 L7 4.5 L1 8 Z" fill="var(--line-faint)" />
              </marker>
            </defs>
            {edges.map((e) => {
              const d = e.curved
                ? verticalEdgePath(e.sx, e.sy, e.ex, e.ey)
                : edgePath(e.sx, e.sy, e.ex, e.ey);
              return (
                <g key={e.key}>
                  {/* Wide invisible grab band under the hairline — same
                      pattern the amber route edges use. Only TREE edges get
                      one: dragging it re-parents the child (drop on a node) or
                      detaches it back to the root chain (drop on empty canvas). */}
                  {e.childId && (
                    <path
                      data-testid="canvas-edge-grab"
                      d={d}
                      fill="none"
                      stroke="transparent"
                      strokeWidth={14}
                      style={{ pointerEvents: "stroke", cursor: "grab" }}
                      onMouseDown={handlePortMouseDown(e.childId, true)}
                    />
                  )}
                  <path
                    data-testid="canvas-edge"
                    data-active={e.active ? "true" : "false"}
                    d={d}
                    fill="none"
                    stroke={e.active ? "var(--brand)" : "var(--line-faint)"}
                    strokeWidth={e.active ? 2 : 1.75}
                    markerEnd={e.curved ? undefined : `url(#${e.active ? "arwb" : "arw"})`}
                  />
                </g>
              );
            })}
            {/* Route edges (T45, redesigned) — a forward target dips
                modestly above/below the row (alternating per the diamond's
                top/bottom origin); a backward/loop target arcs further
                above it, staggered per loop index so overlapping loop-backs
                don't sit on top of one another. Both render the SAME solid
                amber style now ("brown lines behave like blue lines" — no
                separate dashed/red loop treatment), and each carries a
                label naming the condition value that fires it. */}
            {routeEdges.map((e) => {
              // A FORWARD route now draws with the very same horizontal cubic
              // the blue chain edges use, so a branch reads as the same kind of
              // connector in a different colour — leaves the diamond
              // horizontally, enters the target's left edge horizontally. The
              // old quadratic "bulge" arc bowed off the row and met the target
              // at an angle, which is what made brown lines look unlike blue.
              //
              // BACKWARD (loop) targets arc over the top instead — see
              // `loopArcPath`. Anchored top-to-top, so it never cuts back
              // through the main flow line.
              const lift = 70 + e.loopStagger * 46;
              const path = e.backward
                ? loopArcPath(e.sx, e.sy, e.ex, e.ey, lift)
                : edgePath(e.sx, e.sy, e.ex, e.ey);
              // Label anchor: the curve's own midpoint. Both shapes are cubics
              // whose t=0.5 is 1/8·P0 + 3/8·P1 + 3/8·P2 + 1/8·P3; with each
              // one's control points that reduces to the values below.
              const labelX = (e.sx + e.ex) / 2;
              const labelY = e.backward
                ? (e.sy + e.ey) / 8 + 0.75 * (Math.min(e.sy, e.ey) - lift)
                : (e.sy + e.ey) / 2;
              // Dash carries the meaning — "conditional: may or may not run" —
              // so colour is free to carry SELECTION instead, exactly like the
              // blue structural edges. At rest the line is neutral; it goes
              // amber only when one of its endpoints is the selected node.
              const active = selectedId === e.sourceId || selectedId === e.targetId;
              const routeStroke = active ? "var(--status-amber)" : "var(--line-faint)";
              return (
                <g key={e.key}>
                  <path
                    data-testid="canvas-route-edge"
                    data-direction={e.backward ? "backward" : "forward"}
                    data-active={active ? "true" : "false"}
                    d={path}
                    fill="none"
                    stroke={routeStroke}
                    strokeWidth={2}
                    strokeDasharray="6 4"
                    markerEnd={`url(#${active ? "arw-route" : "arw-route-dim"})`}
                  />
                  <text
                    data-testid="canvas-route-edge-label"
                    x={labelX}
                    y={labelY - 4}
                    textAnchor="middle"
                    className="font-sans text-[9.5px] font-semibold"
                    fill={active ? "var(--status-amber)" : "var(--ink-300)"}
                  >
                    {e.label}
                  </text>
                </g>
              );
            })}
            {/* live ghost line while dragging a connector to reparent */}
            {reparentDrag &&
              (() => {
                const childPos = positionOf(reparentDrag.childId);
                return (
                  <path
                    d={verticalEdgePath(
                      childPos.x + childPos.width / 2,
                      childPos.y,
                      reparentDrag.x,
                      reparentDrag.y,
                    )}
                    fill="none"
                    stroke="var(--brand)"
                    strokeWidth={2}
                    strokeDasharray="4 4"
                  />
                );
              })()}
            {/* live preview line while dragging a chain-connect handle */}
            {chainConnectDrag &&
              (() => {
                const pos = positionOf(chainConnectDrag.sourceId);
                return (
                  <path
                    data-testid="canvas-chain-connect-preview"
                    d={edgePath(
                      pos.x + pos.width,
                      actualCenterY(chainConnectDrag.sourceId),
                      chainConnectDrag.x,
                      chainConnectDrag.y,
                    )}
                    fill="none"
                    stroke="var(--brand)"
                    strokeWidth={2}
                    strokeDasharray="4 4"
                  />
                );
              })()}
          </svg>

          {/* Brief trigger pill (dark) — clickable/selectable like any node;
              selects into the rail's Brief Instruction box below. */}
          <div
            role="button"
            tabIndex={0}
            data-testid="canvas-brief"
            data-selected={isBriefSelected ? "true" : "false"}
            onClick={() => setSelectedId(BRIEF_ID)}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                setSelectedId(BRIEF_ID);
              }
            }}
            style={{ left: BRIEF_X, top: briefTop, width: BRIEF_W }}
            className={`absolute z-[3] cursor-pointer rounded-[11px] border bg-surface-near-black px-3 py-2.5 shadow-[0_2px_8px_rgba(17,17,20,0.12)] transition-shadow ${
              isBriefSelected
                ? "border-brand shadow-[0_0_0_3px_var(--brand-fill),0_8px_22px_rgba(60,44,218,0.14)]"
                : reparentDrag
                  ? "border-brand/50"
                  : "border-transparent"
            }`}
          >
            <div className="font-sans text-[9px] font-bold uppercase tracking-[0.12em] text-brand-on-dark">
              Brief
            </div>
            <div className="mt-0.5 font-sans text-[12px] font-semibold text-surface-white">
              What to build
            </div>
            <div className="mt-0.5 truncate font-serif text-[10px] text-ink-300">
              {briefText.trim() || "the run input"}
            </div>
            <span
              className={`absolute top-1/2 -right-[6px] h-[11px] w-[11px] -translate-y-1/2 rounded-full border-2 bg-surface-near-black ${
                isBriefSelected ? "border-brand" : "border-ink-700"
              }`}
            />
          </div>

          {/* root agent nodes */}
          {pipelineAgents.map((agent, i) => {
            const pos = positionOf(agent.id);
            return (
              <CanvasNode
                key={agent.id}
                agent={agent}
                pipelineType={pipelineType}
                selection={selections[agent.id]}
                selected={agent.id === selAgent?.id}
                isChild={false}
                hasChildren={(agent.children?.length ?? 0) > 0}
                cardWidth={NODE_W}
                left={pos.x}
                top={pos.y}
                onSelect={() => setSelectedId(agent.id)}
                onRemove={() => onRemoveAgent(agent.id)}
                onAddChild={handleAddChild}
                onRename={handleRename}
                onSkillsChange={handleSkillsChange}
                onCardMouseDown={handleCardMouseDown(agent.id)}
                onOpenConfig={() => openNodeConfig(agent.id)}
                dropTarget={dropHoverId === agent.id}
                onChainConnectMouseDown={
                  hasOrphan && !agent.detached ? handleChainConnectMouseDown(agent.id) : undefined
                }
                minCardHeight={rowCardHeight}
                modelOptions={modelOptions}
                addChildDisabledReason={addChildDisabledReason(agent)}
              />
            );
          })}

          {/* nested (sub-agent) nodes — flat, laid out by treeLayout.ts */}
          {allDescendants.map((agent) => {
            const pos = positionOf(agent.id);
            return (
              <CanvasNode
                key={agent.id}
                agent={agent}
                pipelineType={pipelineType}
                selection={undefined}
                selected={agent.id === selAgent?.id}
                isChild
                hasChildren={(agent.children?.length ?? 0) > 0}
                cardWidth={pos.width}
                left={pos.x}
                top={pos.y}
                onSelect={() => setSelectedId(agent.id)}
                onRemove={() => handleRemoveId(agent.id)}
                onAddChild={handleAddChild}
                onRename={handleRename}
                onSkillsChange={handleSkillsChange}
                onCardMouseDown={handleCardMouseDown(agent.id)}
                onOpenConfig={() => openNodeConfig(agent.id)}
                dropTarget={dropHoverId === agent.id}
                onChainConnectMouseDown={
                  hasOrphan && !agent.detached ? handleChainConnectMouseDown(agent.id) : undefined
                }
                onPortMouseDown={handlePortMouseDown(agent.id)}
                modelOptions={modelOptions}
                addChildDisabledReason={addChildDisabledReason(agent)}
              />
            );
          })}

          {/* External-workflow reference nodes (spec 014 / R-22) — the target
              of a `trigger:"workflow"` outcome. A reference to a SEPARATE run,
              never that workflow's steps inlined here. */}
          {externalWorkflowNodes.map((wf) => (
            <ExternalWorkflowNode
              key={wf.key}
              workflowId={wf.target}
              workflowNameById={workflowNameById}
              workflowShortNameById={workflowShortNameById}
              workflowKindById={workflowKindById}
              left={wf.x}
              top={wf.y}
              selected={selectedId === wf.key}
              onSelect={() => setSelectedId(wf.key)}
              onMouseDown={handleCardMouseDown(wf.key)}
            />
          ))}

          {/* insert affordances ON the edges (between consecutive root nodes) —
              solid card + darker icon so the dot-grid canvas doesn't show
              through and wash it out; the disabled state stays legible
              (opacity-70, not 40) and explains WHY instead of just fading
              into the background looking broken. */}
          {inserts.map((ins) => (
            <span
              key={ins.key}
              className="absolute z-[5] -translate-x-1/2 -translate-y-1/2"
              style={{ left: ins.x, top: ins.y }}
            >
              <CapTip reason={canAddMore ? undefined : "Maximum 8 root agents are allowed"}>
                <button
                  type="button"
                  aria-label="Add agent"
                  disabled={!canAddMore}
                  onClick={() => onAddAgent(ins.insertBeforeId)}
                  className="grid h-[24px] w-[24px] place-items-center rounded-[7px] border border-line-control bg-surface-card text-[15px] leading-none text-ink-700 shadow-[0_1px_4px_rgba(17,17,20,0.14)] enabled:hover:border-brand enabled:hover:text-brand disabled:cursor-not-allowed disabled:opacity-70"
                >
                  <Plus className="h-3.5 w-3.5" />
                </button>
              </CapTip>
            </span>
          ))}

          {/* add-agent affordance on EVERY leaf's right (plus the empty-canvas
              case) — see `leafAdds`. */}
          {[
            ...leafAdds,
            ...(emptyAdd ? [{ key: "leaf-add-empty", ...emptyAdd, insertBeforeId: undefined }] : []),
          ].map((add) => (
            <span
              key={add.key}
              className="absolute z-[5] -translate-x-1/2 -translate-y-1/2"
              style={{ left: add.x, top: add.y }}
            >
              <CapTip reason={canAddMore ? undefined : "Maximum 8 root agents are allowed"}>
                <button
                  type="button"
                  aria-label="Add agent"
                  disabled={!canAddMore}
                  onClick={() => onAddAgent(add.insertBeforeId)}
                  className="grid h-[30px] w-[30px] place-items-center rounded-[8px] border border-line-control bg-surface-card text-ink-700 shadow-[0_1px_4px_rgba(17,17,20,0.14)] enabled:hover:border-brand enabled:hover:text-brand disabled:cursor-not-allowed disabled:opacity-70"
                >
                  <Plus className="h-[18px] w-[18px]" />
                </button>
              </CapTip>
            </span>
          ))}

        </div>

        {/* zoom / Fit / Auto-arrange controls */}
        <div className="absolute bottom-5 left-[22px] z-[6] flex gap-2">
          <div className="flex overflow-hidden rounded-[10px] border border-line-control bg-surface-card shadow-[0_1px_3px_rgba(17,17,20,0.06)]">
            <button
              type="button"
              aria-label="Zoom out"
              onClick={() => zoomByStep(-0.1)}
              className="grid place-items-center border-r border-line-faint-row px-2.5 py-2 text-ink-500 hover:text-ink-900"
            >
              <Minus className="h-3.5 w-3.5" />
            </button>
            <span className="grid place-items-center px-2.5 py-2 font-sans text-[12px] font-semibold tabular-nums text-ink-500">
              {Math.round(zoom * 100)}%
            </span>
            <button
              type="button"
              aria-label="Zoom in"
              onClick={() => zoomByStep(0.1)}
              className="grid place-items-center border-l border-line-faint-row px-2.5 py-2 text-ink-500 hover:text-ink-900"
            >
              <Plus className="h-3.5 w-3.5" />
            </button>
          </div>
          <button
            type="button"
            onClick={fitToContent}
            className="flex items-center gap-1.5 rounded-[10px] border border-line-control bg-surface-card px-3 py-2 font-sans text-[12px] font-semibold text-ink-500 shadow-[0_1px_3px_rgba(17,17,20,0.06)] hover:text-ink-900"
          >
            <Maximize className="h-3.5 w-3.5" />
            Fit
          </button>
          <button
            type="button"
            onClick={handleAutoArrange}
            title="Reset all dragged positions back to the auto-computed layout"
            className="flex items-center gap-1.5 rounded-[10px] border border-line-control bg-surface-card px-3 py-2 font-sans text-[12px] font-semibold text-ink-500 shadow-[0_1px_3px_rgba(17,17,20,0.06)] hover:text-ink-900"
          >
            <LayoutGrid className="h-3.5 w-3.5" />
            Auto-arrange
          </button>
        </div>
      </div>

      {/* ── Right rail: selected-node config + docked Run summary ──────────── */}
      <aside className="flex w-[344px] flex-none flex-col border-l border-line-divider bg-surface-card">
        <div className="flex items-center justify-between gap-2 border-b border-line-divider px-[18px] py-2.5">
          <div className="flex items-center gap-1 rounded-[8px] border border-line-control bg-surface-warm p-0.5">
            <button
              type="button"
              onClick={() => setRailTab("workflow")}
              className={`rounded-[6px] px-2.5 py-1 font-sans text-[11.5px] font-semibold transition-colors ${
                railTab === "workflow" ? "bg-surface-white text-ink-900 shadow-sm" : "text-ink-400 hover:text-ink-700"
              }`}
            >
              Workflow
            </button>
            <button
              type="button"
              onClick={() => setRailTab("agent")}
              className={`rounded-[6px] px-2.5 py-1 font-sans text-[11.5px] font-semibold transition-colors ${
                railTab === "agent" ? "bg-surface-white text-ink-900 shadow-sm" : "text-ink-400 hover:text-ink-700"
              }`}
            >
              Agent
            </button>
          </div>
          {railTab === "workflow" && (
            <button
              type="button"
              onClick={() => {
                onRunConfigChange?.({
                  deliverable: { strategy: "streamed_text", name: "output.html" },
                  planner: "skip",
                  clarify: { mode: "skip", defaults: [] },
                });
                onCapabilitiesChange?.({ ...capabilities, internet: false });
              }}
              disabled={!onRunConfigChange && !onCapabilitiesChange}
              className="flex-none font-sans text-[11px] font-semibold text-ink-400 transition-colors hover:text-ink-700 disabled:opacity-40"
            >
              Reset to default
            </button>
          )}
        </div>

        {railTab === "workflow" ? (
          <div className="flex flex-col overflow-y-auto">
            <div className="flex flex-col gap-2.5 border-b border-line-divider px-[18px] py-4">
              <div>
                <p className="flex items-center gap-1.5 font-sans text-[13px] font-semibold text-ink-900">
                  <InfoHint>
                    The instruction sent to the workflow&apos;s first agent when this run starts — describe what
                    you want built.
                  </InfoHint>
                  Brief instruction
                </p>
                <p className="mt-0.5 font-serif text-[11px] text-ink-400">
                  What should this run build? Sent as the run&apos;s input.
                </p>
              </div>
              <div className="rounded-[10px] border border-line-control bg-surface-white overflow-hidden">
                <BriefAttachBox
                  value={briefText}
                  onChange={onBriefTextChange}
                  placeholder="Describe what you want this workflow to produce…"
                  attachments={briefAttachments}
                  textareaRef={briefInputRef}
                  rows={5}
                />
              </div>
              <p className="font-serif text-[10px] text-ink-300">
                {briefText.trim().length < 3
                  ? `${3 - briefText.trim().length} more character${3 - briefText.trim().length === 1 ? "" : "s"} to enable Run`
                  : "Ready to run."}
              </p>
            </div>
            {workflowSettingsSection}
          </div>
        ) : (
          <CanvasConfigRail
            agent={agentTabAgent}
            index={agentTabIndex >= 0 ? agentTabIndex : 0}
            total={pipelineAgents.length}
            selection={agentTabAgent ? selections[agentTabAgent.id] : undefined}
            onSelection={onSelection}
            priorAgents={agentTabIndex >= 0 ? pipelineAgents.slice(0, agentTabIndex) : []}
            onSkillsChange={handleSkillsChange}
            onPromptChange={handlePromptChange}
            onStrategyChange={handleStrategyChange}
            onRename={handleRename}
            onRouteChange={handleRouteChange}
            openConfigSignal={openConfigSignal}
            allSteps={[...pipelineAgents, ...allDescendants]}
          />
        )}

        {/* declared-capability chips — the agent/gate/duration stats and the
            Save/Run actions moved to the shared top bar (ComposerPage), so
            this canvas-specific supplement is the only thing left docked here. */}
        {declaredCapabilities.length > 0 && (
          <div
            data-testid="canvas-declared-capabilities"
            className="flex-none border-t border-line-divider bg-surface-warm px-[18px] py-3.5"
          >
            <p className="mb-2 font-sans text-[10px] font-semibold uppercase tracking-[0.1em] text-ink-300">
              Declared capabilities
            </p>
            <div className="flex flex-wrap gap-1.5">
              {declaredCapabilities.map((c) => (
                <span
                  key={c}
                  className="rounded-[6px] border border-brand-border bg-brand-fill px-[7px] py-[3px] font-sans text-[10.5px] font-semibold text-brand"
                >
                  {c}
                </span>
              ))}
            </div>
          </div>
        )}
      </aside>
    </div>
  );
}
