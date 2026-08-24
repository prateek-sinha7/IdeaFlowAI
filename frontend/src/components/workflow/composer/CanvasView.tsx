"use client";

import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Plus, Minus, Maximize, Globe, Info, LayoutGrid } from "lucide-react";
import { CanvasNode } from "./CanvasNode";
import { CanvasConfigRail } from "./CanvasConfigRail";
import { CHILD_W, collectTreeEdges, layoutChildren, type FlatPos } from "./treeLayout";
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
const DRAG_THRESHOLD = 4; // px of mouse movement before a card-mousedown becomes a drag, not a click

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
  const [reparentDrag, setReparentDrag] = useState<{ childId: string; x: number; y: number } | null>(
    null,
  );

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
      if (el) next[a.id] = NODE_Y + el.offsetHeight / 2;
    }
    const keys = Object.keys(next);
    const changed =
      keys.length !== Object.keys(nodeCenterY).length ||
      keys.some((k) => nodeCenterY[k] !== next[k]);
    if (changed) setNodeCenterY(next);

    const briefEl = stageRef.current?.querySelector<HTMLElement>('[data-testid="canvas-brief"]');
    if (briefEl && briefEl.offsetHeight !== briefHeight) setBriefHeight(briefEl.offsetHeight);
  });
  const centerYOf = useCallback(
    (id: string) => nodeCenterY[id] ?? PORT_Y,
    [nodeCenterY],
  );
  const briefCenterY = pipelineAgents.length > 0 ? centerYOf(pipelineAgents[0].id) : PORT_Y;
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
  useEffect(() => {
    const canvasEl = canvasRef.current;
    if (!canvasEl) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const rect = canvasEl.getBoundingClientRect();
      const cursorX = e.clientX - rect.left;
      const cursorY = e.clientY - rect.top;
      const currentZoom = zoomRef.current;
      const currentPan = panRef.current;
      const factor = Math.exp(-e.deltaY * 0.001);
      const nextZoom = Math.min(1.5, Math.max(0.1, Math.round(currentZoom * factor * 100) / 100));
      setPan({
        x: cursorX - ((cursorX - currentPan.x) / currentZoom) * nextZoom,
        y: cursorY - ((cursorY - currentPan.y) / currentZoom) * nextZoom,
      });
      setZoom(nextZoom);
    };
    canvasEl.addEventListener("wheel", onWheel, { passive: false });
    return () => canvasEl.removeEventListener("wheel", onWheel);
  }, []);
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
    const nextZoom = Math.min(1, Math.max(0.1, Math.min(viewportW / contentW, viewportH / contentH)));
    const contentCenterX = (minX + maxX) / 2;
    const contentCenterY = (minY + maxY) / 2;
    setZoom(Math.round(nextZoom * 100) / 100);
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
  const foundAgent =
    !isBriefSelected && selectedId ? findAgentInTree(pipelineAgents, selectedId) : null;
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
  const handlePromptChange = (id: string, prompt: string) => {
    onTreeChange?.(mapAgentInTree(pipelineAgents, id, (a) => ({ ...a, prompt })));
  };
  const handleStrategyChange = (id: string, next: SubagentStrategy, maxParallel?: number) => {
    onTreeChange?.(
      mapAgentInTree(pipelineAgents, id, (a) => ({ ...a, strategy: next, maxParallel })),
    );
  };

  // ── Sub-agent tree layout — computed fresh from pipelineAgents every
  //    render (cheap, pure function; no DOM measurement needed for nested
  //    levels, see treeLayout.ts). Root positions come from the EXISTING
  //    nodeLeft(i)/NODE_Y + measured height (nodeCenterY), same as always. ──
  const childPositions = useMemo(() => {
    const merged = new Map<string, FlatPos>();
    pipelineAgents.forEach((agent, i) => {
      if (!agent.children || agent.children.length === 0) return;
      const rootCenterX = nodeLeft(i) + NODE_W / 2;
      const positions = layoutChildren(agent, rootCenterX, NODE_Y);
      for (const [id, pos] of positions) merged.set(id, pos);
    });
    return merged;
  }, [pipelineAgents]);

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
        const base = { x: nodeLeft(rootIndex), y: NODE_Y, width: NODE_W };
        return override ? { ...base, x: override.x, y: override.y } : base;
      }
      const pos = childPositions.get(id);
      if (!pos) return { x: 0, y: 0, width: CHILD_W };
      const base = { x: pos.x - pos.width / 2, y: pos.y, width: pos.width };
      return override ? { ...base, x: override.x, y: override.y } : base;
    },
    [dragOverrides, pipelineAgents, childPositions],
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
  const handlePortMouseDown = (childId: string) => (e: React.MouseEvent) => {
    e.stopPropagation();
    e.preventDefault();
    const { x, y } = stageXYFromClient(e.clientX, e.clientY);
    setReparentDrag({ childId, x, y });
  };
  useEffect(() => {
    if (!reparentDrag) return;
    const onMove = (e: MouseEvent) => {
      const { x, y } = stageXYFromClient(e.clientX, e.clientY);
      setReparentDrag((prev) => (prev ? { ...prev, x, y } : prev));
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
      }
      setReparentDrag(null);
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
  const actualCenterY = useCallback(
    (id: string) => positionOf(id).y + (centerYOf(id) - NODE_Y),
    [positionOf, centerYOf],
  );

  // ── Edge list — main chain (Brief→node0→…) PLUS every tree edge, all
  //    tinted brand when either endpoint is the current selection (a
  //    "what's this node connected to" hint highlight). ────────────────────
  type EdgeSpec = { key: string; sx: number; sy: number; ex: number; ey: number; curved: boolean; active: boolean };
  const chainEdges: EdgeSpec[] = pipelineAgents.map((a, i) => {
    const prevId = i === 0 ? BRIEF_ID : pipelineAgents[i - 1].id;
    const sx = i === 0 ? BRIEF_X + BRIEF_W : positionOf(prevId).x + NODE_W;
    const sy = i === 0 ? briefCenterY : actualCenterY(prevId);
    const ex = positionOf(a.id).x - ARROW_INSET;
    const ey = actualCenterY(a.id);
    return {
      key: `chain-${i}`,
      sx,
      sy,
      ex,
      ey,
      curved: false,
      active: selectedId === a.id || selectedId === prevId,
    };
  });
  const treeEdges: EdgeSpec[] = pipelineAgents.flatMap((rootAgent, i) => {
    const rootBottomY = positionOf(rootAgent.id).y + 2 * (centerYOf(rootAgent.id) - NODE_Y);
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
      };
    });
  });
  const edges = [...chainEdges, ...treeEdges];

  // Inter-node insert affordances (between consecutive ROOT nodes only,
  // matching the old canvas exactly — no insert between Brief and node0) +
  // a chain-end add.
  const inserts = pipelineAgents.slice(1).map((_, k) => {
    const i = k; // between node i and node i+1
    return {
      key: `ins-${i}`,
      x: (positionOf(pipelineAgents[i].id).x + NODE_W + positionOf(pipelineAgents[i + 1].id).x) / 2,
      y: (actualCenterY(pipelineAgents[i].id) + actualCenterY(pipelineAgents[i + 1].id)) / 2,
      // The new agent should land right BEFORE node i+1 — i.e. between i and i+1.
      insertBeforeId: pipelineAgents[i + 1].id,
    };
  });
  const chainEndX =
    pipelineAgents.length > 0
      ? positionOf(pipelineAgents[pipelineAgents.length - 1].id).x + NODE_W + NODE_GAP / 2
      : BRIEF_X + BRIEF_W + NODE_GAP / 2;
  const chainEndY =
    pipelineAgents.length > 0
      ? actualCenterY(pipelineAgents[pipelineAgents.length - 1].id)
      : briefCenterY;

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
            "radial-gradient(circle at 1px 1px, var(--line-faint) 1.2px, transparent 0) 0 0 / 22px 22px, var(--surface-paper)",
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
            </defs>
            {edges.map((e) => (
              <path
                key={e.key}
                data-testid="canvas-edge"
                data-active={e.active ? "true" : "false"}
                d={
                  e.curved
                    ? verticalEdgePath(e.sx, e.sy, e.ex, e.ey)
                    : edgePath(e.sx, e.sy, e.ex, e.ey)
                }
                fill="none"
                stroke={e.active ? "var(--brand)" : "var(--line-faint)"}
                strokeWidth={e.active ? 2 : 1.75}
                markerEnd={e.curved ? undefined : `url(#${e.active ? "arwb" : "arw"})`}
              />
            ))}
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
                onPortMouseDown={handlePortMouseDown(agent.id)}
                modelOptions={modelOptions}
                addChildDisabledReason={addChildDisabledReason(agent)}
              />
            );
          })}

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

          {/* add-agent affordance at the chain end */}
          <span
            className="absolute z-[5] -translate-x-1/2 -translate-y-1/2"
            style={{ left: chainEndX, top: chainEndY }}
          >
          <CapTip reason={canAddMore ? undefined : "Maximum 8 root agents are allowed"}>
          <button
            type="button"
            aria-label="Add agent"
            disabled={!canAddMore}
            onClick={() => onAddAgent()}
            className="grid h-[30px] w-[30px] place-items-center rounded-[8px] border border-line-control bg-surface-card text-ink-700 shadow-[0_1px_4px_rgba(17,17,20,0.14)] enabled:hover:border-brand enabled:hover:text-brand disabled:cursor-not-allowed disabled:opacity-70"
          >
            <Plus className="h-[18px] w-[18px]" />
          </button>
          </CapTip>
          </span>
        </div>

        {/* zoom / Fit / Auto-arrange controls */}
        <div className="absolute bottom-5 left-[22px] z-[6] flex gap-2">
          <div className="flex overflow-hidden rounded-[10px] border border-line-control bg-surface-card shadow-[0_1px_3px_rgba(17,17,20,0.06)]">
            <button
              type="button"
              aria-label="Zoom out"
              onClick={() => setZoom((z) => Math.max(0.1, Math.round((z - 0.1) * 10) / 10))}
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
              onClick={() => setZoom((z) => Math.min(1.5, Math.round((z + 0.1) * 10) / 10))}
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
